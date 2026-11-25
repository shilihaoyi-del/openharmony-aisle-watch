#ifndef WS63_CHANGE_WATCH_H
#define WS63_CHANGE_WATCH_H

#include <stdbool.h>
#include <stdint.h>

enum { WATCH_BINS = 72, WATCH_BASE_FRAMES = 7, WATCH_EVIDENCE = 16 };
enum { WATCH_DEFAULT_RANGE_MM = 3000 };
enum { WATCH_CONFIG = 5, WATCH_REPORT = 0x82, WATCH_READY = 0x85 };
enum { WATCH_CALIBRATING, WATCH_CLEAR, WATCH_OCCUPIED, WATCH_UNKNOWN };
enum { WATCH_HEARTBEAT, WATCH_BASELINE, WATCH_INTRUSION, WATCH_RESTORED, WATCH_BLIND };

typedef struct {
    uint8_t first;
    uint8_t count;
} WatchSector;

typedef struct {
    uint32_t session;
    uint32_t sequence;
    uint32_t event_id;
    uint32_t event_stamp;
    uint32_t stamp;
    uint32_t latest_rx;
    uint32_t scans;
    uint32_t last_report;
    int32_t angle;
    int32_t step;
    uint16_t limit;
    uint16_t reference[WATCH_BINS];
    uint8_t near_streak[WATCH_BINS];
    uint16_t learning[WATCH_BASE_FRAMES][WATCH_BINS];
    uint16_t evidence_before[WATCH_EVIDENCE];
    uint16_t evidence_after[WATCH_EVIDENCE];
    WatchSector roi;
    WatchSector active;
    WatchSector occupied;
    WatchSector candidate;
    WatchSector moving_candidate;
    WatchSector evidence;
    uint8_t state;
    uint8_t candidate_state;
    uint8_t consecutive;
    uint8_t moving_consecutive;
    uint8_t learned;
    uint8_t reference_count;
    uint8_t observed;
    uint8_t event;
    uint8_t repeats;
    bool enabled;
    bool fresh;
    bool event_fresh;
    bool active_localized;
} ChangeWatch;

void ChangeWatchStart(ChangeWatch *watch, uint32_t session, uint32_t now, WatchSector roi,
                      uint16_t limit);
uint8_t ChangeWatchScan(ChangeWatch *watch, uint32_t stamp, uint32_t now,
                        int32_t angle, int32_t step, const uint16_t ranges[WATCH_BINS]);
uint8_t ChangeWatchMissing(ChangeWatch *watch, uint32_t now);

#endif
