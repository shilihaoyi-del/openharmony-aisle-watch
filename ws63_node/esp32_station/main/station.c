#include <inttypes.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "driver/gpio.h"
#include "driver/rmt_tx.h"
#include "driver/usb_serial_jtag.h"
#include "esp_err.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

enum mode { OFFLINE, IDLE, PENDING, CONFIRMED };

static const gpio_num_t button = GPIO_NUM_0;
static rmt_channel_handle_t rgb;
static rmt_encoder_handle_t rgb_encoder;
static enum mode station_mode;
static uint32_t event_session, event_id;
static TickType_t last_state;

static void send_line(const char *line)
{
    usb_serial_jtag_write_bytes(line, strlen(line), pdMS_TO_TICKS(20));
}

static void configure_rgb(void)
{
    const rmt_tx_channel_config_t channel = {
        .gpio_num = CONFIG_AISLE_STATION_RGB_GPIO, .clk_src = RMT_CLK_SRC_DEFAULT,
        .resolution_hz = 10000000, .mem_block_symbols = 64, .trans_queue_depth = 1,
    };
    const rmt_bytes_encoder_config_t timings = {
        .bit0 = {.level0 = 1, .duration0 = 3, .level1 = 0, .duration1 = 9},
        .bit1 = {.level0 = 1, .duration0 = 9, .level1 = 0, .duration1 = 3},
        .flags.msb_first = true,
    };
    ESP_ERROR_CHECK(rmt_new_tx_channel(&channel, &rgb));
    ESP_ERROR_CHECK(rmt_new_bytes_encoder(&timings, &rgb_encoder));
    ESP_ERROR_CHECK(rmt_enable(rgb));
}

static void show_mode(enum mode mode)
{
    static uint8_t grb[] = {0, 0, 0};
    static int displayed = -1;
    if ((int)mode == displayed) return;
    grb[0] = mode == IDLE ? 10 : 0;
    grb[1] = mode == PENDING ? 26 : 0;
    grb[2] = mode == CONFIRMED ? 20 : 0;
    const rmt_transmit_config_t tx = {0};
    if (rmt_transmit(rgb, rgb_encoder, grb, sizeof(grb), &tx) == ESP_OK &&
        rmt_tx_wait_all_done(rgb, 20) == ESP_OK) {
        displayed = mode;
    }
}

static void receive_line(const char *line)
{
    uint32_t session, id;
    char mode[12], extra;
    if (!strcmp(line, "AW1 PING")) {
        send_line("AW1 READY\n");
        return;
    }
    if (sscanf(line, "AW1 STATE %" SCNu32 " %" SCNu32 " %11s %c", &session, &id, mode, &extra) != 3) return;
    if (!strcmp(mode, "offline")) station_mode = OFFLINE;
    else if (!strcmp(mode, "idle")) station_mode = IDLE;
    else if (session && id && !strcmp(mode, "pending")) station_mode = PENDING;
    else if (session && id && !strcmp(mode, "confirmed")) station_mode = CONFIRMED;
    else return;
    event_session = session;
    event_id = id;
    last_state = xTaskGetTickCount();
    send_line("AW1 READY\n");
}

void app_main(void)
{
    usb_serial_jtag_driver_config_t usb = {.tx_buffer_size = 256, .rx_buffer_size = 256};
    const gpio_config_t input = {.pin_bit_mask = 1ULL << button, .mode = GPIO_MODE_INPUT,
                                 .pull_up_en = GPIO_PULLUP_ENABLE};
    ESP_ERROR_CHECK(usb_serial_jtag_driver_install(&usb));
    ESP_ERROR_CHECK(gpio_config(&input));
    configure_rgb();
    char line[96];
    unsigned used = 0;
    bool discard = false;
    int stable = 0, level = gpio_get_level(button);
    TickType_t changed = xTaskGetTickCount();
    while (true) {
        char bytes[32];
        int length = usb_serial_jtag_read_bytes(bytes, sizeof(bytes), pdMS_TO_TICKS(10));
        for (int i = 0; i < length; ++i) {
            if (bytes[i] == '\n') {
                line[used] = '\0';
                if (!discard) receive_line(line);
                used = 0;
                discard = false;
            } else if (bytes[i] != '\r' && !discard) {
                if (used == sizeof(line) - 1) discard = true;
                else line[used++] = bytes[i];
            }
        }
        const TickType_t now = xTaskGetTickCount();
        if (now - last_state > pdMS_TO_TICKS(1800)) station_mode = OFFLINE;
        show_mode(station_mode);
        const int observed = gpio_get_level(button);
        if (observed != level) {
            level = observed;
            changed = now;
        } else if (level != stable && now - changed >= pdMS_TO_TICKS(40)) {
            stable = level;
            if (!stable && station_mode == PENDING) {
                char ack[64];
                snprintf(ack, sizeof(ack), "AW1 ACK %" PRIu32 " %" PRIu32 "\n", event_session, event_id);
                send_line(ack);
            }
        }
        if (length > 0) vTaskDelay(1);
    }
}
