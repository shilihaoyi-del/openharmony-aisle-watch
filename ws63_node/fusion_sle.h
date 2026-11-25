#ifndef WS63_FUSION_SLE_H
#define WS63_FUSION_SLE_H

#include "sle_ssap_stru.h"

#define FUSION_SLE_NAME "WS63-FUSION"
#define FUSION_SLE_MTU 247
#define SLE_AD_LOCAL_NAME 0x0b

static inline sle_uuid_t FusionSleUuid(uint8_t id)
{
    const sle_uuid_t uuid = {
        .len = 16,
        .uuid = { 0xb1, 0xa2, 0xf3, 0x11, 0xfb, 0x41, 0x4d, 0xa7,
                  0xa0, 0xbf, 0x45, 0x6a, 0x75, 0x61, 0x18, id },
    };
    return uuid;
}

#endif
