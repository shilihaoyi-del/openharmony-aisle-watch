#include "change_watch.h"

#include <string.h>

enum {
    MIN_BASE_FRAMES = 5, BASE_SPAN_MM = 150, OCCUPANCY_MM = 250,
    RECOVERY_MM = 150, CONFIRM_FRAMES = 3, MISSING_FRAMES = 4, MIN_CLUSTER = 3, MOVING_CLUSTER = 5,
    STALE_MS = 1500,
};

void ChangeWatchStart(ChangeWatch *watch, uint32_t session, uint32_t now, WatchSector roi,
                      uint16_t limit)
{
    memset(watch, 0, sizeof(*watch));
    watch->enabled = true;
    watch->session = session;
    watch->last_report = now;
    watch->roi = roi;
    watch->limit = limit;
}

static uint8_t Commit(ChangeWatch *watch, uint8_t state, uint8_t event, WatchSector sector,
                      const uint16_t ranges[WATCH_BINS])
{
    watch->state = state;
    watch->event = event;
    watch->event_stamp = watch->stamp;
    watch->event_fresh = watch->fresh;
    ++watch->event_id;
    watch->repeats = 2;
    watch->consecutive = 0;
    watch->evidence = sector;
    const unsigned count = sector.count < WATCH_EVIDENCE ? sector.count : WATCH_EVIDENCE;
    for (unsigned i = 0; i < count; ++i) {
        watch->evidence_before[i] = watch->reference[sector.first + i];
        watch->evidence_after[i] = ranges ? ranges[sector.first + i] : 0;
    }
    return event;
}

static uint16_t LearnBin(const ChangeWatch *watch, unsigned bin)
{
    uint16_t sorted[WATCH_BASE_FRAMES];
    unsigned count = 0;
    for (unsigned i = 0; i < WATCH_BASE_FRAMES; ++i) {
        const uint16_t value = watch->learning[i][bin];
        if (!value) continue;
        unsigned index = count++;
        while (index && sorted[index - 1] > value) {
            sorted[index] = sorted[index - 1];
            --index;
        }
        sorted[index] = value;
    }
    for (unsigned first = 0; first + MIN_BASE_FRAMES <= count; ++first) {
        if (sorted[first + MIN_BASE_FRAMES - 1] - sorted[first] <= BASE_SPAN_MM) {
            return sorted[first + MIN_BASE_FRAMES / 2];
        }
    }
    return 0;
}

static void TrackRun(WatchSector *best, WatchSector *run, unsigned bin, bool hit)
{
    if (!hit) {
        run->count = 0;
        return;
    }
    if (!run->count) run->first = (uint8_t)bin;
    ++run->count;
    if (run->count > best->count) *best = *run;
}

static bool Overlaps(WatchSector a, WatchSector b)
{
    return a.count && b.count && a.first < b.first + b.count && b.first < a.first + a.count;
}

uint8_t ChangeWatchScan(ChangeWatch *watch, uint32_t stamp, uint32_t now,
                        int32_t angle, int32_t step, const uint16_t ranges[WATCH_BINS])
{
    if (watch->scans && ((int32_t)(stamp - watch->stamp) <= 0 || angle != watch->angle || step != watch->step)) {
        return WATCH_HEARTBEAT;
    }
    watch->angle = angle;
    watch->step = step;
    watch->stamp = stamp;
    if (watch->scans && now - watch->latest_rx >= STALE_MS) {
        watch->consecutive = 0;
        watch->moving_consecutive = 0;
        memset(watch->near_streak, 0, sizeof(watch->near_streak));
        if (watch->state == WATCH_CALIBRATING) watch->learned = 0;
    }
    watch->latest_rx = now;
    watch->fresh = true;
    ++watch->scans;

    if (watch->state == WATCH_CALIBRATING) {
        memcpy(watch->learning[watch->learned++], ranges, sizeof(watch->reference));
        if (watch->learned < WATCH_BASE_FRAMES) return WATCH_HEARTBEAT;
        watch->learned = 0;
        watch->reference_count = 0;
        for (unsigned i = watch->roi.first; i < watch->roi.first + watch->roi.count; ++i) {
            watch->reference[i] = LearnBin(watch, i);
            watch->reference_count += watch->reference[i] != 0;
        }
        if (3U * watch->reference_count < 2U * watch->roi.count) return WATCH_HEARTBEAT;
        watch->observed = watch->reference_count;
        return Commit(watch, WATCH_CLEAR, WATCH_BASELINE, (WatchSector){0, 0}, NULL);
    }

    WatchSector near = {0, 0}, near_run = {0, 0}, stable = {0, 0}, stable_run = {0, 0};
    WatchSector missing = {0, 0}, missing_run = {0, 0};
    unsigned affected = 0, visible = 0, recovered = 0;
    watch->observed = 0;
    for (unsigned i = watch->roi.first; i < watch->roi.first + watch->roi.count; ++i) {
        const uint16_t reference = watch->reference[i];
        const uint16_t distance = ranges[i];
        const bool measured = reference && distance;
        const bool closer = measured && distance <= watch->limit && distance + OCCUPANCY_MM <= reference;
        if (!closer) {
            watch->near_streak[i] = 0;
        } else if (watch->near_streak[i] < CONFIRM_FRAMES) {
            ++watch->near_streak[i];
        }
        TrackRun(&near, &near_run, i, closer);
        TrackRun(&stable, &stable_run, i, watch->near_streak[i] == CONFIRM_FRAMES);
        TrackRun(&missing, &missing_run, i, reference && !distance);
        watch->observed += measured;
        bool in_active = i >= watch->active.first && i < watch->active.first + watch->active.count;
        bool in_occupied = i >= watch->occupied.first && i < watch->occupied.first + watch->occupied.count;
        if (reference && ((watch->active_localized && in_active) || in_occupied)) {
            ++affected;
            visible += distance != 0;
            recovered += distance && (distance + RECOVERY_MM >= reference ||
                                      distance > (unsigned)watch->limit + RECOVERY_MM);
        }
    }

    if (near.count < MOVING_CLUSTER) {
        watch->moving_consecutive = 0;
    } else if (!watch->moving_consecutive || !Overlaps(near, watch->moving_candidate)) {
        watch->moving_consecutive = 1;
    } else if (watch->moving_consecutive < CONFIRM_FRAMES) {
        ++watch->moving_consecutive;
    }
    watch->moving_candidate = near;

    if (stable.count >= MIN_CLUSTER || watch->moving_consecutive == CONFIRM_FRAMES) {
        const WatchSector confirmed = stable.count >= MIN_CLUSTER ? stable : near;
        watch->consecutive = 0;
        watch->occupied = confirmed;
        watch->active = confirmed;
        watch->active_localized = true;
        if (watch->state != WATCH_OCCUPIED) {
            return Commit(watch, WATCH_OCCUPIED, WATCH_INTRUSION, confirmed, ranges);
        }
        return WATCH_HEARTBEAT;
    }
    if (near.count >= MIN_CLUSTER) {
        watch->consecutive = 0;
        return WATCH_HEARTBEAT;
    }

    uint8_t decision = WATCH_CLEAR;
    WatchSector sector = watch->active;
    if (missing.count >= MIN_CLUSTER || 4U * watch->observed < 3U * watch->reference_count ||
        3U * visible < 2U * affected) {
        decision = WATCH_UNKNOWN;
        sector = missing.count >= MIN_CLUSTER ? missing : watch->active;
        if (!sector.count) sector = watch->roi;
    } else if (3U * recovered < 2U * affected) {
        watch->consecutive = 0;
        return WATCH_HEARTBEAT;
    }

    if (decision == watch->state) {
        watch->consecutive = 0;
        return WATCH_HEARTBEAT;
    }
    if (!watch->consecutive || decision != watch->candidate_state ||
        (decision != WATCH_CLEAR && !Overlaps(sector, watch->candidate))) {
        watch->consecutive = 0;
    }
    watch->candidate_state = decision;
    watch->candidate = sector;
    if (++watch->consecutive < (decision == WATCH_UNKNOWN ? MISSING_FRAMES : CONFIRM_FRAMES)) {
        return WATCH_HEARTBEAT;
    }

    const uint8_t kind = decision == WATCH_UNKNOWN ? WATCH_BLIND : WATCH_RESTORED;
    if (decision == WATCH_CLEAR) watch->occupied.count = 0;
    watch->active = decision == WATCH_CLEAR ? (WatchSector){0, 0} : sector;
    watch->active_localized = decision == WATCH_UNKNOWN && (missing.count >= MIN_CLUSTER || affected != 0);
    return Commit(watch, decision, kind, sector, ranges);
}

uint8_t ChangeWatchMissing(ChangeWatch *watch, uint32_t now)
{
    if (!watch->fresh || now - watch->latest_rx < STALE_MS) return WATCH_HEARTBEAT;
    watch->fresh = false;
    watch->observed = 0;
    watch->consecutive = 0;
    watch->moving_consecutive = 0;
    memset(watch->near_streak, 0, sizeof(watch->near_streak));
    if (watch->state == WATCH_CALIBRATING || watch->state == WATCH_UNKNOWN) return WATCH_HEARTBEAT;
    if (!watch->active.count) {
        watch->active = watch->roi;
        watch->active_localized = false;
    }
    return Commit(watch, WATCH_UNKNOWN, WATCH_BLIND, watch->active, NULL);
}
