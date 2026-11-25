#include <stdio.h>
#include <string.h>

#include "fusion.h"
#include "fusion_sle.h"
#include "sle_device_discovery.h"
#include "sle_connection_manager.h"
#include "sle_ssap_server.h"

enum { ANNOUNCE_ID = 1, NO_CONNECTION = 0xffff, SSAP_OVERHEAD = 5 };
enum { CONFIGURE_ANNOUNCE = 1, RESTART_ANNOUNCE };

static uint8_t g_server;
static uint16_t g_service;
static uint16_t g_property;
static unsigned g_connection = NO_CONNECTION;
static unsigned g_mtu;
static unsigned g_enabled;
static unsigned g_advertise;

static bool CheckSle(const char *operation, errcode_t result)
{
    if (result == ERRCODE_SUCC) {
        return true;
    }
    printf("WS63_FUSION_SLE_ERROR %s rc=0x%lx\n", operation, (unsigned long)result);
    return false;
}

static void SleEnabled(errcode_t result)
{
    if (CheckSle("enable_callback", result)) {
        __atomic_store_n(&g_enabled, 1, __ATOMIC_RELEASE);
    }
}

static void ServiceStarted(uint8_t server, uint16_t service, errcode_t result)
{
    (void)server;
    (void)service;
    if (CheckSle("service_started", result)) {
        __atomic_store_n(&g_advertise, CONFIGURE_ANNOUNCE, __ATOMIC_RELEASE);
    }
}

static void AnnounceEnabled(uint32_t announce_id, errcode_t result)
{
    if (announce_id == ANNOUNCE_ID && CheckSle("announce_enabled", result)) {
        printf("WS63_FUSION_SLE_ADVERTISING %s\n", FUSION_SLE_NAME);
    }
}

static void ConnectionChanged(uint16_t connection, const sle_addr_t *address, sle_acb_state_t state,
                              sle_pair_state_t pair, sle_disc_reason_t reason)
{
    (void)address;
    (void)pair;
    if (state == SLE_ACB_STATE_CONNECTED) {
        __atomic_store_n(&g_mtu, 0, __ATOMIC_RELEASE);
        __atomic_store_n(&g_connection, connection, __ATOMIC_RELEASE);
        printf("WS63_FUSION_SLE_CONNECTED conn=%u\n", (unsigned)connection);
    } else if (state == SLE_ACB_STATE_DISCONNECTED &&
               __atomic_load_n(&g_connection, __ATOMIC_ACQUIRE) == connection) {
        __atomic_store_n(&g_connection, NO_CONNECTION, __ATOMIC_RELEASE);
        __atomic_store_n(&g_advertise, RESTART_ANNOUNCE, __ATOMIC_RELEASE);
        printf("WS63_FUSION_SLE_DISCONNECTED reason=0x%x\n", (unsigned)reason);
    }
}

static void MtuChanged(uint8_t server, uint16_t connection, ssap_exchange_info_t *info, errcode_t result)
{
    /* In the WS63 1.10.101 SDK this connection-level event reports server ID 0. */
    (void)server;
    if (result == ERRCODE_SUCC && info &&
        connection == __atomic_load_n(&g_connection, __ATOMIC_ACQUIRE)) {
        __atomic_store_n(&g_mtu, info->mtu_size, __ATOMIC_RELEASE);
        printf("WS63_FUSION_SLE_MTU %lu\n", (unsigned long)info->mtu_size);
    }
}

static void RegisterService(void)
{
    sle_uuid_t application = FusionSleUuid(1);
    sle_uuid_t service = FusionSleUuid(2);
    uint8_t initial = 0;
    uint8_t notify[2] = { 1, 0 };
    ssaps_property_info_t property = {
        .uuid = FusionSleUuid(3), .permissions = SSAP_PERMISSION_READ,
        .operate_indication = SSAP_OPERATE_INDICATION_BIT_READ | SSAP_OPERATE_INDICATION_BIT_NOTIFY,
        .value = &initial, .value_len = sizeof(initial),
    };
    ssaps_desc_info_t descriptor = {
        .type = SSAP_DESCRIPTOR_CLIENT_CONFIGURATION,
        .permissions = SSAP_PERMISSION_READ | SSAP_PERMISSION_WRITE,
        .operate_indication = SSAP_OPERATE_INDICATION_BIT_READ | SSAP_OPERATE_INDICATION_BIT_WRITE,
        .value = notify, .value_len = sizeof(notify),
    };
    ssap_exchange_info_t mtu = { .mtu_size = FUSION_SLE_MTU, .version = 1 };
    if (!CheckSle("register_server", ssaps_register_server(&application, &g_server))) {
        return;
    }
    if (!CheckSle("add_service", ssaps_add_service_sync(g_server, &service, 1, &g_service)) ||
        !CheckSle("add_property", ssaps_add_property_sync(g_server, g_service, &property, &g_property)) ||
        !CheckSle("add_cccd", ssaps_add_descriptor_sync(g_server, g_service, g_property, &descriptor)) ||
        !CheckSle("set_mtu", ssaps_set_info(g_server, &mtu)) ||
        !CheckSle("start_service", ssaps_start_service(g_server, g_service))) {
        (void)ssaps_unregister_server(g_server);
    }
}

static bool ConfigureAdvertising(void)
{
    /* Discovery Level, Access Mode and Complete Local Name advertising data. */
    uint8_t data_bytes[7 + sizeof(FUSION_SLE_NAME)] = {
        2, 0x01, SLE_ANNOUNCE_LEVEL_NORMAL, 2, 0x02, 0, sizeof(FUSION_SLE_NAME), SLE_AD_LOCAL_NAME,
    };
    memcpy(data_bytes + 8, FUSION_SLE_NAME, sizeof(FUSION_SLE_NAME) - 1);
    uint8_t seek_response[] = { 2, 0x0c, 0 };
    const sle_announce_data_t data = {
        .announce_data = data_bytes, .announce_data_len = sizeof(data_bytes),
        .seek_rsp_data = seek_response, .seek_rsp_data_len = sizeof(seek_response),
    };
    sle_announce_param_t param = {
        .announce_mode = SLE_ANNOUNCE_MODE_CONNECTABLE_SCANABLE,
        .announce_handle = ANNOUNCE_ID, .announce_gt_role = SLE_ANNOUNCE_ROLE_T_CAN_NEGO,
        .announce_level = SLE_ANNOUNCE_LEVEL_NORMAL, .announce_channel_map = 7,
        .announce_interval_min = 400, .announce_interval_max = 400,
        .conn_interval_min = 100, .conn_interval_max = 200, .conn_supervision_timeout = 500,
    };
    return CheckSle("get_address", sle_get_local_addr(&param.own_addr)) &&
           CheckSle("set_announce_param", sle_set_announce_param(ANNOUNCE_ID, &param)) &&
           CheckSle("set_announce_data", sle_set_announce_data(ANNOUNCE_ID, &data));
}

void FusionSleStart(void)
{
    static sle_announce_seek_callbacks_t discovery = {
        .sle_enable_cb = SleEnabled, .announce_enable_cb = AnnounceEnabled,
    };
    static sle_connection_callbacks_t connection = { .connect_state_changed_cb = ConnectionChanged };
    static ssaps_callbacks_t ssap = { .start_service_cb = ServiceStarted, .mtu_changed_cb = MtuChanged };
    if (CheckSle("register_discovery", sle_announce_seek_register_callbacks(&discovery)) &&
        CheckSle("register_connection", sle_connection_register_callbacks(&connection)) &&
        CheckSle("register_ssap", ssaps_register_callbacks(&ssap))) {
        (void)CheckSle("enable", enable_sle());
    }
}

void FusionSlePoll(void)
{
    if (__atomic_load_n(&g_enabled, __ATOMIC_ACQUIRE)) {
        __atomic_store_n(&g_enabled, 0, __ATOMIC_RELEASE);
        RegisterService();
    }
    const unsigned announce = __atomic_load_n(&g_advertise, __ATOMIC_ACQUIRE);
    if (announce) {
        __atomic_store_n(&g_advertise, 0, __ATOMIC_RELEASE);
        if (announce != CONFIGURE_ANNOUNCE || ConfigureAdvertising()) {
            (void)CheckSle("start_announce", sle_start_announce(ANNOUNCE_ID));
        }
    }
}

void FusionSleSend(const uint8_t *data, size_t length)
{
    const unsigned connection = __atomic_load_n(&g_connection, __ATOMIC_ACQUIRE);
    const unsigned mtu = __atomic_load_n(&g_mtu, __ATOMIC_ACQUIRE);
    if (connection == NO_CONNECTION || length + SSAP_OVERHEAD > mtu) {
        return;
    }
    ssaps_ntf_ind_t notification = {
        .handle = g_property, .type = SSAP_PROPERTY_TYPE_VALUE,
        .value_len = (uint16_t)length, .value = (uint8_t *)data,
    };
    (void)CheckSle("notify", ssaps_notify_indicate(g_server, (uint16_t)connection, &notification));
}
