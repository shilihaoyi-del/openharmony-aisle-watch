#include "fusion.h"

#include <limits.h>
#include <string.h>

enum {
    SCAN = 1, IMU = 2, ODOM = 3, RESET = 4, REPORT = 0x81, READY = 0x84,
    WAIT_MS = 80, IMU_WINDOW_MS = 40, ODOM_WINDOW_MS = 80,
};

static uint32_t Read(const uint8_t *data, size_t size)
{
    uint32_t value = 0;
    for (size_t i = 0; i < size; ++i) {
        value |= (uint32_t)data[i] << (i * 8);
    }
    return value;
}

static void Write(uint8_t **out, uint32_t value, size_t size)
{
    for (size_t i = 0; i < size; ++i) {
        *(*out)++ = (uint8_t)value;
        value >>= 8;
    }
}

static uint16_t Crc(const uint8_t *bytes, size_t length)
{
    uint16_t crc = 0xffff;
    while (length--) {
        crc ^= (uint16_t)*bytes++ << 8;
        for (unsigned i = 0; i < 8; ++i) {
            crc = (uint16_t)((crc << 1) ^ ((crc & 0x8000) ? 0x1021 : 0));
        }
    }
    return crc;
}

static void Send(Fusion *node, uint8_t kind, uint8_t *frame, uint8_t *end)
{
    frame[0] = 0xa5;
    frame[1] = 0x5a;
    frame[2] = kind;
    frame[3] = (uint8_t)(end - frame - 4);
    const uint16_t crc = Crc(frame + 2, (size_t)(end - frame - 2));
    Write(&end, crc, 2);
    node->send(frame, (size_t)(end - frame));
}

static void EmitWatch(Fusion *node, uint8_t event, uint32_t now)
{
    ChangeWatch *watch = &node->watch;
    const WatchSector evidence = event ? watch->evidence : (WatchSector){0, 0};
    const unsigned samples = evidence.count < WATCH_EVIDENCE ? evidence.count : WATCH_EVIDENCE;
    uint8_t frame[FUSION_FRAME_MAX];
    uint8_t *out = frame + 4;
    Write(&out, node->test, 1);
    Write(&out, event, 1);
    Write(&out, watch->state, 1);
    Write(&out, event ? watch->event_fresh : watch->fresh, 1);
    Write(&out, watch->session, 4);
    Write(&out, watch->sequence++, 4);
    Write(&out, watch->event_id, 4);
    Write(&out, event ? watch->event_stamp : watch->stamp, 4);
    Write(&out, now, 4);
    Write(&out, watch->scans, 4);
    Write(&out, watch->reference_count, 1);
    Write(&out, watch->observed, 1);
    Write(&out, watch->roi.first, 1);
    Write(&out, watch->roi.count, 1);
    Write(&out, evidence.first, 1);
    Write(&out, evidence.count, 1);
    Write(&out, samples, 1);
    for (unsigned i = 0; i < samples; ++i) {
        Write(&out, watch->evidence_before[i], 2);
        Write(&out, watch->evidence_after[i], 2);
    }
    watch->last_report = now;
    Send(node, WATCH_REPORT, frame, out);
}

static const FusionSample *Nearest(const FusionHistory *history, uint32_t stamp, int32_t limit)
{
    const FusionSample *best = NULL;
    int32_t best_distance = limit + 1;
    for (unsigned i = 0; i < history->count; ++i) {
        const FusionSample *sample = &history->samples[i];
        const int32_t offset = (int32_t)(sample->stamp - stamp);
        if (offset >= -limit && offset <= limit) {
            const int32_t distance = offset < 0 ? -offset : offset;
            if (distance < best_distance) {
                best = sample;
                best_distance = distance;
            }
        }
    }
    return best;
}

static void Emit(Fusion *node)
{
    const uint32_t stamp = node->scan.stamp;
    const FusionSample *imu = Nearest(&node->imu, stamp, IMU_WINDOW_MS);
    const FusionSample *odom = Nearest(&node->odom, stamp, ODOM_WINDOW_MS);
    uint8_t frame[FUSION_FRAME_MAX];
    uint8_t *out = frame + 4;
    Write(&out, node->test, 1);
    Write(&out, (imu ? 1U : 0U) | (odom ? 2U : 0U), 1);
    Write(&out, node->sequence++, 4);
    Write(&out, stamp, 4);
    Write(&out, node->scan.received, 4);
    Write(&out, (uint32_t)node->scan.angle, 4);
    Write(&out, (uint32_t)node->scan.step, 4);
    Write(&out, node->scan.duration, 2);
    Write(&out, node->scan.count, 1);
    Write(&out, node->scan.valid, 1);
    for (unsigned i = 0; i < node->scan.count; ++i) {
        Write(&out, node->scan.ranges[i], 2);
    }
    if (imu) {
        Write(&out, imu->stamp, 4);
        for (size_t i = 0; i < 6; ++i) {
            Write(&out, (uint32_t)imu->values[i], 4);
        }
    }
    if (odom) {
        Write(&out, odom->stamp, 4);
        for (size_t i = 0; i < 5; ++i) {
            Write(&out, (uint32_t)odom->values[i], 4);
        }
    }
    node->scan.count = 0;
    Send(node, REPORT, frame, out);
}

static void Push(FusionHistory *history, uint32_t stamp, const uint8_t *data, size_t count, int filter)
{
    const FusionSample *previous = &history->samples[(history->next + FUSION_HISTORY - 1) % FUSION_HISTORY];
    const int32_t elapsed = (int32_t)(stamp - previous->stamp);
    if (history->count && elapsed <= 0) {
        return;
    }
    FusionSample *sample = &history->samples[history->next];
    sample->stamp = stamp;
    for (size_t i = 0; i < count; ++i) {
        const int32_t value = (int32_t)Read(data + 4 * i, 4);
        sample->values[i] = filter && history->count && elapsed <= 100
            ? (int32_t)(((int64_t)previous->values[i] + value) / 2) : value;
    }
    history->next = (history->next + 1) % FUSION_HISTORY;
    if (history->count < FUSION_HISTORY) {
        ++history->count;
    }
}

static void ReceiveScan(Fusion *node, const uint8_t *p, size_t length, uint32_t stamp, uint32_t now)
{
    if (length < 20 || p[19] == 0 || p[19] > FUSION_MAX_BINS || length != 20U + 2U * p[19]) {
        return;
    }
    const uint16_t minimum = (uint16_t)Read(p + 15, 2);
    const uint16_t maximum = (uint16_t)Read(p + 17, 2);
    if (maximum < minimum || maximum == 0 || Read(p + 9, 4) == 0) {
        return;
    }
    if (node->watch.enabled) {
        if (p[19] != WATCH_BINS) return;
        uint16_t ranges[WATCH_BINS];
        for (unsigned i = 0; i < WATCH_BINS; ++i) {
            const uint16_t range = (uint16_t)Read(p + 20 + i * 2, 2);
            ranges[i] = range >= minimum && range <= maximum ? range : 0;
        }
        const uint8_t event = ChangeWatchScan(&node->watch, stamp, now,
            (int32_t)Read(p + 5, 4), (int32_t)Read(p + 9, 4), ranges);
        if (event) EmitWatch(node, event, now);
        return;
    }
    if (node->scan.count) {
        Emit(node);
    }
    node->scan.stamp = stamp;
    node->scan.received = now;
    node->scan.angle = (int32_t)Read(p + 5, 4);
    node->scan.step = (int32_t)Read(p + 9, 4);
    node->scan.duration = (uint16_t)Read(p + 13, 2);
    node->scan.count = p[19];
    node->scan.valid = 0;
    for (unsigned i = 0; i < node->scan.count; ++i) {
        const uint16_t range = (uint16_t)Read(p + 20 + i * 2, 2);
        node->scan.ranges[i] = range >= minimum && range <= maximum ? range : 0;
        node->scan.valid += node->scan.ranges[i] != 0;
    }
}

static void ReceiveFrame(Fusion *node, uint32_t now)
{
    const uint8_t kind = node->frame[2];
    const size_t length = node->frame[3];
    const uint8_t *p = node->frame + 4;
    if (kind == RESET && length == 5 && p[0] <= 1) {
        node->test = p[0];
        node->sequence = 0;
        node->scan.count = 0;
        node->watch.enabled = false;
        memset(&node->imu, 0, sizeof(node->imu));
        memset(&node->odom, 0, sizeof(node->odom));
        uint8_t frame[11];
        memcpy(frame + 4, p, 5);
        Send(node, READY, frame, frame + 9);
        return;
    }
    if (length < 5 || p[0] != node->test) {
        return;
    }
    const uint32_t stamp = Read(p + 1, 4);
    if (kind == WATCH_CONFIG && (length == 7 || length == 9) && p[6] >= 3 && p[5] + p[6] <= WATCH_BINS) {
        const uint16_t limit = length == 9 ? (uint16_t)Read(p + 7, 2) : WATCH_DEFAULT_RANGE_MM;
        if (!limit) return;
        node->scan.count = 0;
        if (!node->watch.enabled || node->watch.session != stamp || node->watch.limit != limit ||
            node->watch.roi.first != p[5] || node->watch.roi.count != p[6]) {
            ChangeWatchStart(&node->watch, stamp, now, (WatchSector){p[5], p[6]}, limit);
        }
        uint8_t frame[15];
        memcpy(frame + 4, p, length);
        Send(node, WATCH_READY, frame, frame + 4 + length);
    } else if (kind == SCAN) {
        ReceiveScan(node, p, length, stamp, now);
    } else if (kind == IMU && length == 29) {
        Push(&node->imu, stamp, p + 5, 6, 1);
    } else if (kind == ODOM && length == 25) {
        Push(&node->odom, stamp, p + 5, 5, 0);
    }
}

void FusionInit(Fusion *node, FusionSend send)
{
    memset(node, 0, sizeof(*node));
    node->send = send;
}

void FusionReceive(Fusion *node, uint8_t byte, uint32_t now)
{
    node->frame[node->used++] = byte;
    for (;;) {
        uint8_t *frame = node->frame;
        const size_t used = node->used;
        if (used == 0) {
            return;
        }
        if (frame[0] == 0xa5 && (used == 1 || frame[1] == 0x5a)) {
            if (used < 4) {
                return;
            }
            const size_t payload = frame[3];
            const size_t total = payload + 6;
            if (payload <= FUSION_PAYLOAD_MAX) {
                if (used < total) {
                    return;
                }
                if (Crc(frame + 2, payload + 2) == Read(frame + total - 2, 2)) {
                    ReceiveFrame(node, now);
                    node->used -= total;
                    memmove(frame, frame + total, node->used);
                    continue;
                }
            }
        }
        --node->used;
        memmove(frame, frame + 1, node->used);
    }
}

void FusionPoll(Fusion *node, uint32_t now)
{
    if (node->watch.enabled) {
        uint8_t event = ChangeWatchMissing(&node->watch, now);
        if (event) {
            EmitWatch(node, event, now);
        } else if (now - node->watch.last_report >= 1000) {
            if (node->watch.repeats) {
                --node->watch.repeats;
                event = node->watch.event;
            }
            EmitWatch(node, event, now);
        }
        return;
    }
    if (node->scan.count && now - node->scan.received >= WAIT_MS) {
        Emit(node);
    }
}
