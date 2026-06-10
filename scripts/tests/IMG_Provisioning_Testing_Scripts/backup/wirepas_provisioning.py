# Copyright 2024 Wirepas Ltd licensed under Apache License, Version 2.0
#
# See file LICENSE for full license details.
#
import cbor2
import logging
from enum import IntEnum


class NodeProvisioningDataIds(IntEnum):
    WIREPAS_ENCRYPTION_KEY =   0             # PROV_DATA_ID_ENC_KEY
    WIREPAS_AUTHENTICATION_KEY =   1         # PROV_DATA_ID_AUTH_KEY
    WIREPAS_NETWORK_ADDRESS =   2            # PROV_DATA_ID_NET_ADDR
    WIREPAS_NETWORK_CHANNEL =   3            # PROV_DATA_ID_NET_CHAN
    WIREPAS_NODE_ADDRESS =   4               # PROV_DATA_ID_NODE_ADDR
    WIREPAS_NODE_ROLE =   5                  # PROV_DATA_ID_NODE_ROLE
    WIREPAS_GW_KEY_ENC_KEY = 128            # PROV_DATA_ID_GW_KEY_ENC_KEY
    WIREPAS_MTR_AUTH_KEY = 129               # PROV_DATA_ID_MTR_AUTH_KEY
    WIREPAS_MTR_ENC_KEY = 130                # PROV_DATA_ID_MTR_ENC_KEY
    WIREPAS_MTR_MR_SECRET = 131              # PROV_DATA_ID_MTR_MR_SECRET
    WIREPAS_MTR_US_SECRET = 132              # PROV_DATA_ID_MTR_US_SECRET
    WIREPAS_MTR_FU_SECRET = 133              # PROV_DATA_ID_MTR_FU_SECRET
    WIREPAS_RESERVED = 134                   # PROV_DATA_ID_RESERVED
    WIREPAS_MTR_BAUD_RATE = 135              # PROV_DATA_ID_MTR_BAUD_RATE
    WIREPAS_MTR_DLMS_MODE = 136              # PROV_DATA_ID_MTR_DLMS_MODE
    WIREPAS_GW_ID = 137                      # PROV_DATA_ID_GW_ID
    WIREPAS_SINK_ADDRESS = 138               # PROV_DATA_ID_SINK_ADDR
    WIREPAS_SIM1_APN = 139                   # PROV_DATA_ID_SIM1_APN
    WIREPAS_SIM1_USERNAME = 140              # PROV_DATA_ID_SIM1_USERNAME
    WIREPAS_SIM1_PASSWORD = 141              # PROV_DATA_ID_SIM1_PASSWORD
    WIREPAS_SIM1_PDP_TYPE = 142              # PROV_DATA_ID_SIM1_PDP_TYPE
    WIREPAS_SIM1_PIN = 143                   # PROV_DATA_ID_SIM1_PIN
    WIREPAS_SIM1_PUK = 144                   # PROV_DATA_ID_SIM1_PUK
    WIREPAS_SIM2_APN = 145                   # PROV_DATA_ID_SIM2_APN
    WIREPAS_SIM2_USERNAME = 146              # PROV_DATA_ID_SIM2_USERNAME
    WIREPAS_SIM2_PASSWORD = 147              # PROV_DATA_ID_SIM2_PASSWORD
    WIREPAS_SIM2_PDP_TYPE = 148              # PROV_DATA_ID_SIM2_PDP_TYPE
    WIREPAS_SIM2_PIN = 149                   # PROV_DATA_ID_SIM2_PIN
    WIREPAS_SIM2_PUK = 150                   # PROV_DATA_ID_SIM2_PUK
    WIREPAS_MQTT_HOSTNAME = 151              # PROV_DATA_ID_MQTT_HOSTNAME
    WIREPAS_MQTT_PORT = 152                  # PROV_DATA_ID_MQTT_PORT
    WIREPAS_MQTT_USERNAME = 153              # PROV_DATA_ID_MQTT_USERNAME
    WIREPAS_MQTT_PASSWORD = 154              # PROV_DATA_ID_MQTT_PASSWORD
    WIREPAS_MQTT_UNSECURE = 155              # PROV_DATA_ID_MQTT_UNSECURE
    WIREPAS_CELLULAR_INFO_DIAG_INTVL = 156   # PROV_DATA_ID_CELLULAR_INFO_DIAG_INTVL
    WIREPAS_GATEWAY_INFO_DIAG_INTVL = 157    # PROV_DATA_ID_GATEWAY_INFO_DIAG_INTVL
    WIREPAS_NETWORK_INFO_DIAG_INTVL = 158    # PROV_DATA_ID_NETWORK_INFO_DIAG_INTVL
    WIREPAS_NTP_ADDR = 159                   # PROV_DATA_ID_NTP_ADDR
    WIREPAS_TZ_OFFSET_MIN = 160              # PROV_DATA_ID_TZ_OFFSET_MIN
    WIREPAS_KEEPALIVE_INTVL_S = 161          # PROV_DATA_ID_KEEPALIVE_INTVL_S
    WIREPAS_RESET_HOUR = 162                 # PROV_DATA_ID_RESET_HOUR
    WIREPAS_RESET_MINUTE = 163               # PROV_DATA_ID_RESET_MINUTE
    WIREPAS_GW_ROLE_SWITCH = 164             # PROV_DATA_ID_GW_ROLE_SWITCH

class NicInfoDataIds(IntEnum):
    DEV_EUI64 = 224               # NIC_INFO_DEV_EUI64
    APP_VER = 225                 # NIC_INFO_APP_VER
    STACK_VER = 226               # NIC_INFO_STACK_VER
    GW_IMEI = 227                 # NIC_INFO_GW_IMEI
    GW_CORE_VER = 228             # NIC_INFO_GW_CORE_VER
    GW_MAIN_VER = 229             # NIC_INFO_GW_MAIN_VER
    GW_SINK_APP_VER = 230         # NIC_INFO_GW_SINK_APP_VER
    GW_MODEM_FIRMWARE_VER = 231   # NIC_INFO_GW_MODEM_FIRMWARE_VER

class ProvisioningDataReturnCode(IntEnum):
    SUCCESS = 0
    INVALID_STATE = 1
    INVALID_PARAMETER = 2
    INVALID_DATA = 3
    JOINING_LIB_ERROR = 4
    INTERNAL_ERROR = 5


class WirepasProvisioning:
    """
    Class storing parameters
    """

    def __init__(
        self,
        encryption_key=None,
        authentication_key=None,
        network_address=None,
        network_channel=None,
        node_address=None,
        node_role=None,
        gw_key_enc_key=None,
        mtr_auth_key=None,
        mtr_enc_key=None,
        mtr_mr_secret=None,
        mtr_us_secret=None,
        mtr_fu_secret=None,
        mtr_baud_rate=None,
        mtr_dlms_mode=None,
        gateway_id=None,
        sink_address=None,
        sim1_apn=None,
        sim1_username=None,
        sim1_password=None,
        sim1_pdp_type=None,
        sim1_pin=None,
        sim1_puk=None,
        mqtt_hostname=None,
        mqtt_port=None,
        mqtt_username=None,
        mqtt_password=None,
        mqtt_unsecure=None,
        cellular_info_diag_intvl=None,
        network_info_diag_intvl=None,
        gateway_info_diag_intvl=None,
        ntp_addr=None,
        tz_offset_min=None,
        keepalive_intvl_s=None,
        reset_hour=None,
        reset_minute=None,
    ):
        self.encryption_key = encryption_key
        self.authentication_key = authentication_key
        self.network_address = network_address
        self.network_channel = network_channel
        self.node_address = node_address
        self.node_role = node_role
        self.gw_key_enc_key = gw_key_enc_key
        self.mtr_auth_key = mtr_auth_key
        self.mtr_enc_key = mtr_enc_key
        self.mtr_mr_secret = mtr_mr_secret
        self.mtr_us_secret = mtr_us_secret
        self.mtr_fu_secret = mtr_fu_secret
        self.mtr_baud_rate = mtr_baud_rate
        self.mtr_dlms_mode = mtr_dlms_mode        
        self.gateway_id = gateway_id
        self.sink_address = sink_address
        self.sim1_apn = sim1_apn
        self.sim1_username = sim1_username
        self.sim1_password = sim1_password
        self.sim1_pdp_type = sim1_pdp_type
        self.sim1_pin = sim1_pin
        self.sim1_puk = sim1_puk
        self.mqtt_hostname = mqtt_hostname
        self.mqtt_port = mqtt_port
        self.mqtt_username = mqtt_username
        self.mqtt_password = mqtt_password
        self.mqtt_unsecure = mqtt_unsecure
        self.cellular_info_diag_intvl = cellular_info_diag_intvl
        self.network_info_diag_intvl = network_info_diag_intvl
        self.gateway_info_diag_intvl = gateway_info_diag_intvl
        self.ntp_addr = ntp_addr
        self.tz_offset_min = tz_offset_min
        self.keepalive_intvl_s = keepalive_intvl_s
        self.reset_hour = reset_hour
        self.reset_minute = reset_minute
        
    def _generate_provisioning_dict(self) -> dict:
        prov_dict = {
            NodeProvisioningDataIds.WIREPAS_ENCRYPTION_KEY.value: self.encryption_key,
            NodeProvisioningDataIds.WIREPAS_AUTHENTICATION_KEY.value: self.authentication_key,
            NodeProvisioningDataIds.WIREPAS_NETWORK_ADDRESS.value: self.network_address,
            NodeProvisioningDataIds.WIREPAS_NETWORK_CHANNEL.value: self.network_channel,
            NodeProvisioningDataIds.WIREPAS_NODE_ADDRESS.value: self.node_address,
            NodeProvisioningDataIds.WIREPAS_NODE_ROLE.value: self.node_role,
            NodeProvisioningDataIds.WIREPAS_GW_KEY_ENC_KEY.value: self.gw_key_enc_key,
            NodeProvisioningDataIds.WIREPAS_MTR_AUTH_KEY.value: self.mtr_auth_key,
            NodeProvisioningDataIds.WIREPAS_MTR_ENC_KEY.value: self.mtr_enc_key,
            NodeProvisioningDataIds.WIREPAS_MTR_MR_SECRET.value: self.mtr_mr_secret,
            NodeProvisioningDataIds.WIREPAS_MTR_US_SECRET.value: self.mtr_us_secret,
            NodeProvisioningDataIds.WIREPAS_MTR_FU_SECRET.value: self.mtr_fu_secret,
            NodeProvisioningDataIds.WIREPAS_MTR_BAUD_RATE.value: self.mtr_baud_rate,
            NodeProvisioningDataIds.WIREPAS_MTR_DLMS_MODE.value: self.mtr_dlms_mode,
            NodeProvisioningDataIds.WIREPAS_GW_ID.value: self.gateway_id,
            NodeProvisioningDataIds.WIREPAS_SINK_ADDRESS.value: self.sink_address,
            NodeProvisioningDataIds.WIREPAS_SIM1_APN.value: self.sim1_apn,
            NodeProvisioningDataIds.WIREPAS_SIM1_USERNAME.value: self.sim1_username,
            NodeProvisioningDataIds.WIREPAS_SIM1_PASSWORD.value: self.sim1_password,
            NodeProvisioningDataIds.WIREPAS_SIM1_PDP_TYPE.value: self.sim1_pdp_type,
            NodeProvisioningDataIds.WIREPAS_SIM1_PIN.value: self.sim1_pin,
            NodeProvisioningDataIds.WIREPAS_SIM1_PUK.value: self.sim1_puk,
            NodeProvisioningDataIds.WIREPAS_MQTT_HOSTNAME.value: self.mqtt_hostname,
            NodeProvisioningDataIds.WIREPAS_MQTT_PORT.value: self.mqtt_port,
            NodeProvisioningDataIds.WIREPAS_MQTT_USERNAME.value: self.mqtt_username,
            NodeProvisioningDataIds.WIREPAS_MQTT_PASSWORD.value: self.mqtt_password,
            NodeProvisioningDataIds.WIREPAS_MQTT_UNSECURE.value: self.mqtt_unsecure,
            NodeProvisioningDataIds.WIREPAS_CELLULAR_INFO_DIAG_INTVL.value: self.cellular_info_diag_intvl,
            NodeProvisioningDataIds.WIREPAS_NETWORK_INFO_DIAG_INTVL.value: self.network_info_diag_intvl,
            NodeProvisioningDataIds.WIREPAS_GATEWAY_INFO_DIAG_INTVL.value: self.gateway_info_diag_intvl,
            NodeProvisioningDataIds.WIREPAS_NTP_ADDR.value: self.ntp_addr,
            NodeProvisioningDataIds.WIREPAS_TZ_OFFSET_MIN.value: self.tz_offset_min,
            NodeProvisioningDataIds.WIREPAS_KEEPALIVE_INTVL_S.value: self.keepalive_intvl_s,
            NodeProvisioningDataIds.WIREPAS_RESET_HOUR.value: self.reset_hour,
            NodeProvisioningDataIds.WIREPAS_RESET_MINUTE.value: self.reset_minute,
        }
        print(prov_dict,'--------')

        # Removing parameters with "None" value in the provisioning dictionary
        return {k: v for k, v in prov_dict.items() if v is not None}

    def get_provisioning_packet(self) -> bytes:
        prov_dict = self._generate_provisioning_dict()
        return cbor2.dumps(prov_dict)


def is_provisioning_dry_run_successful(return_code_frame: bytes) -> bool:
    return_code = cbor2.loads(return_code_frame)

    try:
        return_code = ProvisioningDataReturnCode(return_code)
    except:
        logging.warning("Unknown return code!")
        return False

    logging.info("Provisioning Packet Dry Run Return Code: " + return_code.name)
    if return_code != ProvisioningDataReturnCode.SUCCESS:
        return False

    return True


def format_version(version_int):
    major = (version_int >> 24) & 0xFF
    minor = (version_int >> 16) & 0xFF
    maint = (version_int >> 8) & 0xFF
    dev = version_int & 0xFF
    return f"{major}.{minor}.{maint}.{dev}"


def decode_prov_dict(prov_read_data: bytes) -> bool:
    try:
        prov_dict = cbor2.loads(prov_read_data)

        # Check if prov_dict is a dictionary
        if not isinstance(prov_dict, dict):
            logging.error(f"Received CBOR data is not a dictionary but a {type(prov_dict).__name__}: {prov_dict}")
            return {"ERROR": f"Invalid data format: {type(prov_dict).__name__} instead of dictionary"}

        nic_params = dict()
        for key in prov_dict:
            if key in [item.value for item in NodeProvisioningDataIds]:
                try:
                    new_key = NodeProvisioningDataIds(key).name
                    nic_params[new_key] = prov_dict[key]
                except ValueError:
                    # If the key doesn't match any enum value, use a generic name
                    new_key = f"UNKNOWN_PARAM_{key}"
                    nic_params[new_key] = prov_dict[key]
                    logging.error(f"Unknown parameter ID: {key}, value: {prov_dict[key]}")
            elif key in [item.value for item in NicInfoDataIds]:
                try:
                    new_key = NicInfoDataIds(key).name
                    nic_params[new_key] = prov_dict[key]
                except ValueError:
                    # If the key doesn't match any enum value, use a generic name
                    new_key = f"UNKNOWN_INFO_{key}"
                    nic_params[new_key] = prov_dict[key]
                    logging.error(f"Unknown info ID: {key}, value: {prov_dict[key]}")
            else:
                # For any other keys not in our enums
                new_key = f"PARAM_{key}"
                nic_params[new_key] = prov_dict[key]
                logging.error(f"Unknown ID: {key}, value: {prov_dict[key]}")

        # Process key fields - only if they exist
        if NodeProvisioningDataIds.WIREPAS_ENCRYPTION_KEY.name in nic_params:
            nic_params[NodeProvisioningDataIds.WIREPAS_ENCRYPTION_KEY.name] = update_key_value(
                nic_params[NodeProvisioningDataIds.WIREPAS_ENCRYPTION_KEY.name]
            )
        if NodeProvisioningDataIds.WIREPAS_AUTHENTICATION_KEY.name in nic_params:
            nic_params[NodeProvisioningDataIds.WIREPAS_AUTHENTICATION_KEY.name] = update_key_value(
                nic_params[NodeProvisioningDataIds.WIREPAS_AUTHENTICATION_KEY.name]
            )
        if NodeProvisioningDataIds.WIREPAS_GW_KEY_ENC_KEY.name in nic_params:
            nic_params[NodeProvisioningDataIds.WIREPAS_GW_KEY_ENC_KEY.name] = update_key_value(
                nic_params[NodeProvisioningDataIds.WIREPAS_GW_KEY_ENC_KEY.name]
            )
        if NodeProvisioningDataIds.WIREPAS_MTR_AUTH_KEY.name in nic_params:
            nic_params[NodeProvisioningDataIds.WIREPAS_MTR_AUTH_KEY.name] = update_key_value(
                nic_params[NodeProvisioningDataIds.WIREPAS_MTR_AUTH_KEY.name]
            )
        if NodeProvisioningDataIds.WIREPAS_MTR_ENC_KEY.name in nic_params:
            nic_params[NodeProvisioningDataIds.WIREPAS_MTR_ENC_KEY.name] = update_key_value(
                nic_params[NodeProvisioningDataIds.WIREPAS_MTR_ENC_KEY.name]
            )
        
        # Process password fields - add asterisks to indicate hidden parts
        if NodeProvisioningDataIds.WIREPAS_MQTT_PASSWORD.name in nic_params:
            nic_params[NodeProvisioningDataIds.WIREPAS_MQTT_PASSWORD.name] = update_password_value(
                nic_params[NodeProvisioningDataIds.WIREPAS_MQTT_PASSWORD.name]
            )
        if NodeProvisioningDataIds.WIREPAS_SIM1_PASSWORD.name in nic_params:
            nic_params[NodeProvisioningDataIds.WIREPAS_SIM1_PASSWORD.name] = update_password_value(
                nic_params[NodeProvisioningDataIds.WIREPAS_SIM1_PASSWORD.name]
            )
        if NodeProvisioningDataIds.WIREPAS_MTR_MR_SECRET.name in nic_params:
            nic_params[NodeProvisioningDataIds.WIREPAS_MTR_MR_SECRET.name] = update_password_value(
                nic_params[NodeProvisioningDataIds.WIREPAS_MTR_MR_SECRET.name]
            )
        if NodeProvisioningDataIds.WIREPAS_MTR_US_SECRET.name in nic_params:
            nic_params[NodeProvisioningDataIds.WIREPAS_MTR_US_SECRET.name] = update_password_value(
                nic_params[NodeProvisioningDataIds.WIREPAS_MTR_US_SECRET.name]
            )
        if NodeProvisioningDataIds.WIREPAS_MTR_FU_SECRET.name in nic_params:
            nic_params[NodeProvisioningDataIds.WIREPAS_MTR_FU_SECRET.name] = update_password_value(
                nic_params[NodeProvisioningDataIds.WIREPAS_MTR_FU_SECRET.name]
            )
        if NodeProvisioningDataIds.WIREPAS_NETWORK_ADDRESS.name in nic_params:
            nic_params[NodeProvisioningDataIds.WIREPAS_NETWORK_ADDRESS.name] = hex(
                nic_params[NodeProvisioningDataIds.WIREPAS_NETWORK_ADDRESS.name]
            )
        if NodeProvisioningDataIds.WIREPAS_NODE_ROLE.name in nic_params:
            nic_params[NodeProvisioningDataIds.WIREPAS_NODE_ROLE.name] = hex(
                nic_params[NodeProvisioningDataIds.WIREPAS_NODE_ROLE.name]
            )
        
        if NicInfoDataIds.DEV_EUI64.name in nic_params:
            nic_params[NicInfoDataIds.DEV_EUI64.name] = hex(
                nic_params[NicInfoDataIds.DEV_EUI64.name]
            )
        
        if NicInfoDataIds.APP_VER.name in nic_params:
            nic_params[NicInfoDataIds.APP_VER.name] = format_version(
                nic_params[NicInfoDataIds.APP_VER.name]
            )
        
        if NicInfoDataIds.STACK_VER.name in nic_params:
            nic_params[NicInfoDataIds.STACK_VER.name] = format_version(
                nic_params[NicInfoDataIds.STACK_VER.name]
            )
        
        return nic_params
    
    except Exception as e:
        logging.error(f"Error decoding provisioning data: {str(e)}")
        logging.debug(f"Raw data: {prov_read_data.hex()}")
        import traceback
        logging.debug(f"Exception traceback: {traceback.format_exc()}")
        return {"ERROR": f"Failed to decode data: {str(e)}"}


def print_provisioning_summary(nic_params: dict):
    summary = "\n\n\tProvisioned NIC Parameters Summary:\n"

    summary += "_" * 80 + "\n"
    summary += "\n".join("{!r}: {!r}".format(k, v) for k, v in nic_params.items())
    summary += "\n" + "_" * 80 + "\n"
    logging.info(summary)


def get_provisioning_status(nic_params: dict) -> bool:
    # Define critical parameters that must be set
    critical_params = [
        "WIREPAS_ENCRYPTION_KEY",
        "WIREPAS_AUTHENTICATION_KEY",
        "WIREPAS_NETWORK_ADDRESS",
        "WIREPAS_NETWORK_CHANNEL",
        "WIREPAS_NODE_ADDRESS"
    ]
    
    bad_parameters_counter = 0
    for param in critical_params:
        if param not in nic_params or nic_params[param] in ("Not set", 0, "0x0", "", "\x00\x00\x00", "UNDEFINED"):
            logging.error(f"{param} field is invalid or missing!")
            bad_parameters_counter += 1

    return bad_parameters_counter < 1


def hide_security_keys(last_2_bytes: bytes):
    return (14 * "* ") + "{0:02x} {1:02x}".format(last_2_bytes[0], last_2_bytes[1])


def update_key_value(key: bytes) -> bytes:
    if key != b"":
        key = hide_security_keys(key)
    else:
        key = "Not set"

    return key

def update_password_value(password: str) -> str:
    if password != "":
        # Add asterisks at the beginning to indicate hidden parts
        password = "* * * * * * * * * * * * " + password
    else:
        password = "Not set"

    return password
