#ifndef WS63_FUSION_H
#define WS63_FUSION_H

#include <stddef.h>
#include <stdint.h>
#include "change_watch.h"

#define FUSION_MAX_BINS WATCH_BINS
#define FUSION_PAYLOAD_MAX 224
#define FUSION_FRAME_MAX (FUSION_PAYLOAD_MAX + 6)
#define FUSION_HISTORY 32

typedef void (*FusionSend)(const uint8_t *data, size_t length);

typedef struct {
    uint32_t stamp;
    int32_t values[6];
} FusionSample;

typedef struct {
    FusionSample samples[FUSION_HISTORY];
    uint8_t next;
    uint8_t count;
} FusionHistory;

typedef struct {
    FusionHistory imu;
    FusionHistory odom;
    ChangeWatch watch;
    struct {
        uint32_t stamp;
        uint32_t received;
        int32_t angle;
        int32_t step;
        uint16_t duration;
        uint16_t ranges[FUSION_MAX_BINS];
        uint8_t count;
        uint8_t valid;
    } scan;
    uint32_t sequence;
    uint8_t test;
    uint8_t frame[FUSION_FRAME_MAX];
    size_t used;
    FusionSend send;
} Fusion;

void FusionInit(Fusion *node, FusionSend send);
void FusionReceive(Fusion *node, uint8_t byte, uint32_t now);
void FusionPoll(Fusion *node, uint32_t now);

#endif
