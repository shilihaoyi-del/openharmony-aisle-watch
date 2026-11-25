#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>

#include "cmsis_os2.h"
#include "iot_errno.h"
#include "iot_gpio.h"
#include "ohos_init.h"
#include "pinctrl.h"

#define USER_CONTACT_GPIO 13
#define SAMPLE_MS 10
#define DEBOUNCE_SAMPLES 3
#define HEARTBEAT_SAMPLES (1000 / SAMPLE_MS)

static void ContactTask(void *unused)
{
    (void)unused;
    const uint32_t ticks_per_second = osKernelGetTickFreq();
    if (ticks_per_second == 0) {
        return;
    }
    const uint32_t period = (ticks_per_second * SAMPLE_MS + 999) / 1000;
    uint32_t tick = osKernelGetTickCount();
    uint64_t uptime_ticks = tick;
    uint32_t sequence = 0;
    unsigned repeats = 0;
    unsigned quiet_samples = HEARTBEAT_SAMPLES;
    int candidate = -1;
    int stable = -1;

    while (1) {
        const uint32_t now = osKernelGetTickCount();
        uptime_ticks += (uint32_t)(now - tick);
        tick = now;
        IotGpioValue value;
        if (IoTGpioGetInputVal(USER_CONTACT_GPIO, &value) == IOT_SUCCESS) {
            const int closed = value == IOT_GPIO_VALUE0;
            if (candidate != closed) {
                candidate = closed;
                repeats = 1;
            } else if (repeats < DEBOUNCE_SAMPLES) {
                ++repeats;
            }
            if (repeats >= DEBOUNCE_SAMPLES) {
                const int changed = stable != candidate;
                if (changed || quiet_samples >= HEARTBEAT_SAMPLES) {
                    stable = candidate;
                    const uint64_t time_ms = uptime_ticks * 1000 / ticks_per_second;
                    printf("WS63_CONTACT_V1 {\"seq\":%" PRIu32 ",\"t_ms\":%" PRIu64
                           ",\"closed\":%d,\"event\":%d}\n", sequence++, time_ms,
                           stable, changed);
                    quiet_samples = 0;
                }
            }
        } else {
            candidate = -1;
            repeats = 0;
        }
        if (quiet_samples < HEARTBEAT_SAMPLES) {
            ++quiet_samples;
        }
        osDelay(period);
    }
}

static void ContactStart(void)
{
    const pin_t pin = (pin_t)USER_CONTACT_GPIO;
    if (IoTGpioInit(pin) != IOT_SUCCESS || uapi_pin_set_mode(pin, 0) != ERRCODE_SUCC ||
        uapi_pin_set_pull(pin, PIN_PULL_TYPE_UP) != ERRCODE_SUCC ||
        IoTGpioSetDir(pin, IOT_GPIO_DIR_IN) != IOT_SUCCESS) {
        puts("WS63_CONTACT_ERROR gpio_init");
        return;
    }
    const osThreadAttr_t attributes = {
        .name = "ContactSense",
        .stack_size = 4096,
        .priority = osPriorityNormal,
    };
    puts("WS63_CONTACT_BOOT OpenHarmony mini nearlink_dk_3863");
    if (osThreadNew(ContactTask, NULL, &attributes) == NULL) {
        puts("WS63_CONTACT_ERROR thread_start");
    }
}

APP_FEATURE_INIT(ContactStart);
