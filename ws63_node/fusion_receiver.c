#include <stdbool.h>
#include <stdio.h>
#include <string.h>

#include "cmsis_os2.h"
#include "fusion.h"
#include "fusion_sle.h"
#include "ohos_init.h"
#include "sle_connection_manager.h"
#include "sle_device_discovery.h"
#include "sle_ssap_client.h"
#include "uart.h"

enum { NO_CONNECTION = 0xffff, RADIO_START_DELAY_MS = 1800, MTU_REQUEST = 300, MTU_RETRY_MS = 160 };

typedef struct {
    uint16_t size;
    uint16_t connection;
    unsigned generation;
    uint8_t bytes[FUSION_FRAME_MAX];
} Report;

/* The SDK serializes SLE callbacks. The CMSIS queue transfers reports to the UART task. */
static sle_addr_t g_peer;
static uint8_t g_client;
static uint16_t g_connection = NO_CONNECTION;
static unsigned g_generation;
static uint16_t g_property;
static bool g_found;
static osMessageQueueId_t g_reports;

static bool CheckReceiver(const char *operation, errcode_t result)
{
    if (result == ERRCODE_SUCC) {
        return true;
    }
    printf("WS63_FUSION_RX_ERROR %s rc=0x%lx\n", operation, (unsigned long)result);
    return false;
}

static void Seek(void)
{
    g_found = false;
    g_property = 0;
    (void)CheckReceiver("start_seek", sle_start_seek());
}

static void Enabled(errcode_t result)
{
    sle_seek_param_t parameters = {
        .seek_phys = 1, .seek_interval = { 100 }, .seek_window = { 70 },
    };
    sle_uuid_t app_uuid = FusionSleUuid(4);
    if (CheckReceiver("enable_callback", result) &&
        CheckReceiver("register_client", ssapc_register_client(&app_uuid, &g_client)) &&
        CheckReceiver("set_seek_param", sle_set_seek_param(&parameters))) {
        printf("WS63_FUSION_RX_CLIENT id=%u\n", (unsigned)g_client);
        Seek();
    }
}

static void SeekEnabled(errcode_t result)
{
    if (CheckReceiver("seek_enabled", result)) {
        printf("WS63_FUSION_RX_SCANNING %s\n", FUSION_SLE_NAME);
    }
}

static void SeekResult(sle_seek_result_info_t *result)
{
    const char name[] = FUSION_SLE_NAME;
    if (!result || !result->data || g_found) {
        return;
    }
    const uint8_t *p = result->data;
    size_t remaining = result->data_length;
    while (remaining && p[0] && p[0] < remaining) {
        const size_t field = p[0];
        if (field == sizeof(name) && p[1] == SLE_AD_LOCAL_NAME &&
            memcmp(p + 2, name, sizeof(name) - 1) == 0) {
            g_peer = result->addr;
            g_found = true;
            if (!CheckReceiver("stop_seek", sle_stop_seek())) {
                g_found = false;
            }
            return;
        }
        p += field + 1;
        remaining -= field + 1;
    }
}

static void SeekStopped(errcode_t result)
{
    if (g_found && (!CheckReceiver("seek_stopped", result) ||
                    !CheckReceiver("connect", sle_connect_remote_device(&g_peer)))) {
        Seek();
    }
}

static void ScheduleExchange(uint16_t connection)
{
    Report request = {
        .connection = connection, .generation = __atomic_load_n(&g_generation, __ATOMIC_ACQUIRE),
    };
    if (osMessageQueuePut(g_reports, &request, 0, 0) != osOK) {
        printf("WS63_FUSION_RX_ERROR queue_mtu_request conn=%u\n", (unsigned)connection);
    }
}

static void Exchange(const Report *request)
{
    const uint32_t ticks = (osKernelGetTickFreq() * MTU_RETRY_MS + 999) / 1000;
    ssap_exchange_info_t mtu = { .mtu_size = MTU_REQUEST, .version = 1 };
    /* Let the SDK finish publishing its connection state before entering SSAP. */
    for (unsigned attempt = 1; attempt <= 4; ++attempt) {
        osDelay(ticks);
        if (request->generation != __atomic_load_n(&g_generation, __ATOMIC_ACQUIRE)) {
            return;
        }
        const errcode_t result = ssapc_exchange_info_req(g_client, request->connection, &mtu);
        if (result == ERRCODE_SUCC) {
            printf("WS63_FUSION_RX_MTU_REQUEST conn=%u attempt=%u\n", (unsigned)request->connection, attempt);
            return;
        }
        (void)CheckReceiver("exchange_mtu_request", result);
    }
}

static void ConnectionChanged(uint16_t connection, const sle_addr_t *address, sle_acb_state_t state,
                              sle_pair_state_t pair, sle_disc_reason_t reason)
{
    if (state == SLE_ACB_STATE_CONNECTED || state == SLE_ACB_STATE_DISCONNECTED) {
        /* Only this serialized SDK callback advances the generation. */
        const unsigned generation = __atomic_load_n(&g_generation, __ATOMIC_RELAXED);
        __atomic_store_n(&g_generation, generation + 1, __ATOMIC_RELEASE);
    }
    if (state == SLE_ACB_STATE_CONNECTED) {
        g_connection = connection;
        if (address) {
            g_peer = *address;
        }
        printf("WS63_FUSION_RX_CONNECTED conn=%u pair=%u\n", (unsigned)connection, (unsigned)pair);
        if (pair == SLE_PAIR_PAIRED) {
            ScheduleExchange(connection);
        } else if (pair == SLE_PAIR_NONE && !CheckReceiver("pair_request", sle_pair_remote_device(&g_peer))) {
            (void)sle_disconnect_remote_device(&g_peer);
        }
    } else if (state == SLE_ACB_STATE_DISCONNECTED) {
        printf("WS63_FUSION_RX_DISCONNECTED reason=0x%x\n", (unsigned)reason);
        g_connection = NO_CONNECTION;
        Seek();
    }
}

static void Paired(uint16_t connection, const sle_addr_t *address, errcode_t result)
{
    (void)address;
    if (connection == g_connection) {
        if (CheckReceiver("pair_complete", result)) {
            printf("WS63_FUSION_RX_PAIRED conn=%u\n", (unsigned)connection);
            ScheduleExchange(connection);
        } else {
            (void)sle_disconnect_remote_device(&g_peer);
        }
    }
}

static void Exchanged(uint8_t client, uint16_t connection, ssap_exchange_info_t *info, errcode_t result)
{
    /* WS63 1.10.101 reports client ID 0 in callbacks even when registration assigns 1. */
    (void)client;
    if (connection != g_connection) {
        return;
    }
    ssapc_find_structure_param_t properties = {
        .type = SSAP_FIND_TYPE_PROPERTY, .start_hdl = 1, .end_hdl = 0xffff,
    };
    const uint32_t mtu = info ? info->mtu_size : 0;
    printf("WS63_FUSION_RX_MTU %lu\n", (unsigned long)mtu);
    if (!CheckReceiver("exchange_mtu_complete", result) || mtu < FUSION_FRAME_MAX + 5 ||
        !CheckReceiver("find_property", ssapc_find_structure(g_client, connection, &properties))) {
        (void)sle_disconnect_remote_device(&g_peer);
    }
}

static void PropertyFound(uint8_t client, uint16_t connection, ssapc_find_property_result_t *property,
                          errcode_t result)
{
    (void)client;
    const sle_uuid_t expected = FusionSleUuid(3);
    if (result == ERRCODE_SUCC && connection == g_connection && property &&
        property->uuid.len == expected.len && memcmp(property->uuid.uuid, expected.uuid, expected.len) == 0) {
        g_property = property->handle;
    }
}

static void DiscoveryComplete(uint8_t client, uint16_t connection, ssapc_find_structure_result_t *data,
                              errcode_t result)
{
    (void)client;
    (void)data;
    if (connection != g_connection) {
        return;
    }
    if (!CheckReceiver("find_property_complete", result) || !g_property) {
        printf("WS63_FUSION_RX_PROPERTY handle=%u\n", (unsigned)g_property);
        (void)sle_disconnect_remote_device(&g_peer);
        return;
    }
    uint8_t value[] = { 1, 0 };
    ssapc_write_param_t config = {
        .handle = g_property, .type = SSAP_DESCRIPTOR_CLIENT_CONFIGURATION,
        .data_len = sizeof(value), .data = value,
    };
    printf("WS63_FUSION_RX_PROPERTY handle=%u\n", (unsigned)g_property);
    (void)CheckReceiver("subscribe", ssapc_write_req(g_client, connection, &config));
}

static void Subscribed(uint8_t client, uint16_t connection, ssapc_write_result_t *data, errcode_t result)
{
    (void)client;
    if (connection == g_connection && data && data->handle == g_property &&
        CheckReceiver("subscribe_complete", result)) {
        printf("WS63_FUSION_RX_SUBSCRIBED handle=%u\n", (unsigned)data->handle);
    }
}

static void Notification(uint8_t client, uint16_t connection, ssapc_handle_value_t *data, errcode_t result)
{
    (void)client;
    if (result != ERRCODE_SUCC || !data || connection != g_connection || !g_property ||
        data->handle != g_property || !data->data || data->data_len < 6 || data->data_len > FUSION_FRAME_MAX ||
        data->data[0] != 0xa5 || data->data[1] != 0x5a ||
        (data->data[2] != 0x81 && data->data[2] != WATCH_REPORT) ||
        data->data[3] + 6U != data->data_len) {
        return;
    }
    Report report = { .size = data->data_len };
    memcpy(report.bytes, data->data, report.size);
    (void)osMessageQueuePut(g_reports, &report, 0, 0);
}

static void ReceiverTask(void *unused)
{
    (void)unused;
    static sle_announce_seek_callbacks_t discovery = {
        .sle_enable_cb = Enabled, .seek_enable_cb = SeekEnabled,
        .seek_result_cb = SeekResult, .seek_disable_cb = SeekStopped,
    };
    static sle_connection_callbacks_t connection = {
        .connect_state_changed_cb = ConnectionChanged, .pair_complete_cb = Paired,
    };
    static ssapc_callbacks_t ssap = {
        .exchange_info_cb = Exchanged, .ssapc_find_property_cbk = PropertyFound,
        .find_structure_cmp_cb = DiscoveryComplete, .write_cfm_cb = Subscribed, .notification_cb = Notification,
    };
    osDelay((uint32_t)(((uint64_t)osKernelGetTickFreq() * RADIO_START_DELAY_MS + 999) / 1000));
    g_reports = osMessageQueueNew(4, sizeof(Report), NULL);
    if (!g_reports || sle_announce_seek_register_callbacks(&discovery) != ERRCODE_SUCC ||
        sle_connection_register_callbacks(&connection) != ERRCODE_SUCC ||
        ssapc_register_callbacks(&ssap) != ERRCODE_SUCC || enable_sle() != ERRCODE_SUCC) {
        puts("WS63_FUSION_RX_ERROR start");
        return;
    }
    puts("WS63_FUSION_RX_BOOT v1");
    while (1) {
        Report report;
        if (osMessageQueueGet(g_reports, &report, NULL, osWaitForever) == osOK) {
            if (report.size) {
                (void)uapi_uart_write(UART_BUS_0, report.bytes, report.size, 0);
            } else {
                Exchange(&report);
            }
        }
    }
}

static void ReceiverStart(void)
{
    const osThreadAttr_t attributes = {
        .name = "FusionReceiver", .stack_size = 4096, .priority = osPriorityNormal,
    };
    if (!osThreadNew(ReceiverTask, NULL, &attributes)) {
        puts("WS63_FUSION_RX_ERROR thread_start");
    }
}

APP_FEATURE_INIT(ReceiverStart);
