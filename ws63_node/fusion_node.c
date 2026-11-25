#include <stdbool.h>
#include <stdio.h>

#include "cmsis_os2.h"
#include "fusion.h"
#include "ohos_init.h"
#include "uart.h"

enum { RX_RING = 1024, RADIO_START_DELAY_MS = 1800 };

static Fusion g_fusion;
static uint8_t g_rx_driver[128];
static uint8_t g_rx_ring[RX_RING];
static unsigned g_head;
static unsigned g_tail;

void FusionSleStart(void);
void FusionSlePoll(void);
void FusionSleSend(const uint8_t *data, size_t length);

static void Receive(const void *buffer, uint16_t length, bool error)
{
    if (error) {
        return;
    }
    const uint8_t *bytes = buffer;
    unsigned head = __atomic_load_n(&g_head, __ATOMIC_RELAXED);
    const unsigned tail = __atomic_load_n(&g_tail, __ATOMIC_ACQUIRE);
    for (uint16_t i = 0; i < length && head - tail < RX_RING; ++i) {
        g_rx_ring[head++ % RX_RING] = bytes[i];
    }
    __atomic_store_n(&g_head, head, __ATOMIC_RELEASE);
}

static void Send(const uint8_t *data, size_t length)
{
    (void)uapi_uart_write(UART_BUS_0, data, length, 0);
    if (data[2] == 0x81 || data[2] == WATCH_REPORT) {
        FusionSleSend(data, length);
    }
}

static void FusionTask(void *unused)
{
    (void)unused;
    /* The onboard USB bridge shares UART0 with the firmware boot console. */
    const uart_pin_config_t pins = { .tx_pin = 15, .rx_pin = 14, .cts_pin = PIN_NONE, .rts_pin = PIN_NONE };
    const uart_attr_t config = {
        .baud_rate = 115200, .data_bits = UART_DATA_BIT_8, .stop_bits = UART_STOP_BIT_1, .parity = UART_PARITY_NONE,
    };
    uart_buffer_config_t buffer = { .rx_buffer = g_rx_driver, .rx_buffer_size = sizeof(g_rx_driver) };
    (void)uapi_uart_deinit(UART_BUS_0);
    if (uapi_uart_init(UART_BUS_0, &pins, &config, NULL, &buffer) != ERRCODE_SUCC ||
        uapi_uart_register_rx_callback(UART_BUS_0, UART_RX_CONDITION_FULL_OR_SUFFICIENT_DATA_OR_IDLE,
                                       16, Receive) != ERRCODE_SUCC) {
        puts("WS63_FUSION_ERROR uart_init");
        return;
    }
    FusionInit(&g_fusion, Send);
    puts("WS63_FUSION_BOOT v1 UART0");
    const uint32_t frequency = osKernelGetTickFreq();
    if (frequency == 0) {
        return;
    }
    uint32_t previous = osKernelGetTickCount();
    uint64_t elapsed_ticks = previous;
    const uint32_t started_at = (uint32_t)(elapsed_ticks * 1000 / frequency);
    bool radio_started = false;
    while (1) {
        const uint32_t tick = osKernelGetTickCount();
        elapsed_ticks += tick - previous;
        previous = tick;
        const uint32_t now = (uint32_t)(elapsed_ticks * 1000 / frequency);
        const unsigned head = __atomic_load_n(&g_head, __ATOMIC_ACQUIRE);
        unsigned tail = __atomic_load_n(&g_tail, __ATOMIC_RELAXED);
        FusionPoll(&g_fusion, now);
        while (tail != head) {
            const uint8_t byte = g_rx_ring[tail++ % RX_RING];
            __atomic_store_n(&g_tail, tail, __ATOMIC_RELEASE);
            FusionReceive(&g_fusion, byte, now);
        }
        if (!radio_started && now - started_at >= RADIO_START_DELAY_MS) {
            /* The SDK's platform task finishes RF calibration after scheduler startup. */
            radio_started = true;
            FusionSleStart();
        }
        FusionSlePoll();
        osDelay(1);
    }
}

static void FusionStart(void)
{
    const osThreadAttr_t attributes = {
        .name = "FusionSense", .stack_size = 4096, .priority = osPriorityNormal,
    };
    if (osThreadNew(FusionTask, NULL, &attributes) == NULL) {
        puts("WS63_FUSION_ERROR thread_start");
    }
}

APP_FEATURE_INIT(FusionStart);
