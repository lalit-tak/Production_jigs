# Copyright 2024 Wirepas Ltd licensed under Apache License, Version 2.0
#
# See file LICENSE for full license details.
#

import argparse
import logging
import provisioning
import shlex  # For parsing shell-like syntax with quoted strings

from wirepas_provisioning import SIM_SELECTION_OPTIONS

# 0 is used to indicate no band lock
MIN_N58_SUPPORTED_LTE_BAND = 0
MAX_N58_SUPPORTED_LTE_BAND = 41

# Default serial communication settings
DEFAULT_BAUDRATE = 9600

SECRET_MAX_SIZE = 32
KEY_SIZE = 16
FLAG_ID_LENGTH = 3
MINIMUM_NETWORK_ADDRESS = 1
MAXIMUM_NETWORK_ADDRESS = 0xFFFFFF
MINIMUM_NETWORK_CHANNEL = 1
MAXIMUM_NETWORK_CHANNEL = 12
MINIMUM_NODE_ADDRESS = 1
# 0x0xFFFFFFFE => APP_ADDR_ANYSINK
# 0x0xFFFFFFFF => APP_ADDR_BROADCAST
MAXIMUM_NODE_ADDRESS = 0xFFFFFFFD

def validate_node_role(node_role: str) -> int:
    node_role = int(node_role, 0)
    if node_role < 0 or node_role > 255:
        raise argparse.ArgumentTypeError("Node role must be between 0 and 255")
    return node_role

def validate_key(key: str) -> bytes:
    byte_data = bytes.fromhex(key)
    if len(byte_data) != KEY_SIZE:
        raise argparse.ArgumentTypeError(
            "Given key must be " + str(KEY_SIZE) + " bytes long"
        )
    return byte_data

def validate_password(password: str) -> str:
    if len(password) > SECRET_MAX_SIZE:
        raise argparse.ArgumentTypeError(
            "Password must be " + str(SECRET_MAX_SIZE) + " characters long maximum"
        )
    return password

def validate_network_address(network_address: str) -> int:
    network_address = int(network_address, 0)
    if network_address not in range(
        MINIMUM_NETWORK_ADDRESS, MAXIMUM_NETWORK_ADDRESS + 1
    ):
        raise argparse.ArgumentTypeError("Given Network Address is out of range")
    return network_address

def validate_network_channel(network_channel: str) -> int:
    network_channel = int(network_channel, 0)
    if network_channel not in range(
        MINIMUM_NETWORK_CHANNEL, MAXIMUM_NETWORK_CHANNEL + 1
    ):
        raise argparse.ArgumentTypeError("Given Network Channel is out of range")
    return network_channel

def validate_node_address(node_address: str) -> int:
    node_address = int(node_address, 0)
    if node_address < MINIMUM_NODE_ADDRESS or node_address > MAXIMUM_NODE_ADDRESS:
        raise argparse.ArgumentTypeError("Given Node Address is out of range")

    # Checking we are not in the multicast space
    if (node_address & 0xFF000000) == 0x80000000:
        raise argparse.ArgumentTypeError("Given Node Address is in the multicast address range")

    return node_address

def validate_sink_address(sink_address: str) -> int:
    sink_address = int(sink_address, 0)
    if sink_address < MINIMUM_NODE_ADDRESS or sink_address > MAXIMUM_NODE_ADDRESS:
        raise argparse.ArgumentTypeError("Given Node Address is out of range")

    # Checking we are not in the multicast space
    if (sink_address & 0xFF000000) == 0x80000000:
        raise argparse.ArgumentTypeError("Given Sink Address is in the multicast address range")

    return sink_address

def validate_port(port: str) -> int:
    port = int(port, 0)
    if port < 1 or port > 65535:
        raise argparse.ArgumentTypeError("Port must be between 1 and 65535")
    return port

def validate_hour(hour: str) -> int:
    hour = int(hour, 0)
    if hour < 0 or hour > 23:
        raise argparse.ArgumentTypeError("Hour must be between 0 and 23")
    return hour

def validate_minute(minute: str) -> int:
    minute = int(minute, 0)
    if minute < 0 or minute > 59:
        raise argparse.ArgumentTypeError("Minute must be between 0 and 59")
    return minute

def validate_timezone_offset(offset: str) -> int:
    offset = int(offset, 0)
    # Valid timezone offsets range from -12*60 to 14*60 minutes
    if offset < -720 or offset > 840:
        raise argparse.ArgumentTypeError("Timezone offset must be between -720 and 840 minutes")
    return offset

def validate_interval(interval: str) -> int:
    interval = int(interval, 0)
    if interval < 0:
        raise argparse.ArgumentTypeError("Interval must be a positive value")
    return interval

def validate_reboot_time(reboot_time_s: str) -> int:
    reboot_time_s = int(reboot_time_s, 0)
    if reboot_time_s < 0:
        raise argparse.ArgumentTypeError("Reboot time must be a positive value or 0 to apply and reboot")
    return reboot_time_s

def validate_boolean(value: str) -> bool:
    value = value.lower()
    if value in ('yes', 'true', 't', 'y', '1'):
        return True
    elif value in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError("Boolean value expected (yes/no, true/false, y/n, 1/0)")

def validate_cellular_band_lock(band_lock: str) -> str:
    bands = band_lock.split(',')
    if len(bands) > 5:
        raise argparse.ArgumentTypeError("A maximum of 5 bands can be specified.")

    band_bits = 0
    for band in bands:
        band = band.strip().lower().replace('b', '')
        if not band.isdigit():
            raise argparse.ArgumentTypeError(f"Invalid band format: {band}")
        
        band_number = int(band)
        if band_number < MIN_N58_SUPPORTED_LTE_BAND or band_number > MAX_N58_SUPPORTED_LTE_BAND:
            raise argparse.ArgumentTypeError(f"Band number {band_number} is out of range ({MIN_N58_SUPPORTED_LTE_BAND}-{MAX_N58_SUPPORTED_LTE_BAND}).")
        
        if band_number == 0:
            band_bits = 0
            break
        
        band_bits |= (1 << (band_number - 1))

    return f"{band_bits:x}"

def validate_sim_selection(value):
    if value.lower() not in SIM_SELECTION_OPTIONS:
        raise argparse.ArgumentTypeError(
            f"Invalid SIM selection. Must be one of: {', '.join(SIM_SELECTION_OPTIONS)}"
        )
    
    return value.lower()

# Argument parser to set argument and value on the same line, handle comments and ""
class CustomArgumentParser(argparse.ArgumentParser):
    def convert_arg_line_to_args(self, arg_line):
        # Skip empty lines and comments
        if not arg_line.strip() or arg_line.strip().startswith('#'):
            return []
        
        # Use shlex to properly handle quoted strings
        try:
            # This will preserve quoted empty strings like ""
            return shlex.split(arg_line, posix=True)
        except ValueError as e:
            # Handle potential errors in the line format
            logging.warning(f"Error parsing argument line: {arg_line}")
            logging.warning(f"Error details: {str(e)}")
            # Return the line split by whitespace as a fallback
            return arg_line.strip().split()


def run_provisioning(provisioning_dict):
    logging.basicConfig(
        format="%(levelname)s %(asctime)s %(message)s", level=logging.INFO
    )
    nic_parameters_data = {}
    prov_sucess = False
    summary = ""

    parser = CustomArgumentParser(fromfile_prefix_chars="@")
    # Serial parameters
    args = argparse.Namespace(
    # Serial parameters
    serial_port=str(provisioning_dict['serial_port']),
    baudrate=int(provisioning_dict['baudrate']) if provisioning_dict['baudrate'] else DEFAULT_BAUDRATE,

    # Factory mode control parameter
    reboot_time = validate_reboot_time(provisioning_dict['reboot_time']) if provisioning_dict['reboot_time'] else 0,

    # Wirepas parameters
    encryption_key=validate_key(provisioning_dict['encryption_key']) if provisioning_dict['encryption_key'] else None,
    authentication_key=validate_key(provisioning_dict['authentication_key']) if provisioning_dict['authentication_key'] else None,
    network_address=validate_network_address(provisioning_dict['network_address']) if provisioning_dict['network_address'] else None,
    network_channel=validate_network_channel(provisioning_dict['network_channel']) if provisioning_dict['network_channel'] else None,
    node_address=validate_node_address(provisioning_dict['node_address']) if provisioning_dict['node_address'] else None,
    sink_address=validate_sink_address(provisioning_dict['sink_address']) if provisioning_dict['sink_address'] else None,
    node_role=validate_node_role(provisioning_dict['node_role']) if provisioning_dict['node_role'] else None,

    # Gateway parameters
    gateway_id=str(provisioning_dict['gateway_id']) if provisioning_dict['gateway_id'] else None,
    cellular_info_diag_interval=validate_interval(provisioning_dict['cellular_info_diag_interval']) if provisioning_dict['cellular_info_diag_interval'] else None,
    network_info_diag_interval=validate_interval(provisioning_dict['network_info_diag_interval']) if provisioning_dict['network_info_diag_interval'] else None,
    gateway_info_diag_interval=validate_interval(provisioning_dict['gateway_info_diag_interval']) if provisioning_dict['gateway_info_diag_interval'] else None,

    # Meter parameters
    gw_key_enc_key=validate_key(provisioning_dict['gw_key_enc_key']) if provisioning_dict['gw_key_enc_key'] else None,
    mtr_auth_key=validate_key(provisioning_dict['mtr_auth_key']) if provisioning_dict['mtr_auth_key'] else None,
    mtr_enc_key=validate_key(provisioning_dict['mtr_enc_key']) if provisioning_dict['mtr_enc_key'] else None,
    mtr_mr_secret=validate_password(provisioning_dict['mtr_mr_secret']) if provisioning_dict['mtr_mr_secret'] else None,
    mtr_us_secret=validate_password(provisioning_dict['mtr_us_secret']) if provisioning_dict['mtr_us_secret'] else None,
    mtr_fu_secret=validate_password(provisioning_dict['mtr_fu_secret']) if provisioning_dict['mtr_fu_secret'] else None,
    mtr_baud_rate=int(provisioning_dict['mtr_baud_rate']) if provisioning_dict['mtr_baud_rate'] else None,
    mtr_dlms_mode=str(provisioning_dict['mtr_dlms_mode']) if provisioning_dict['mtr_dlms_mode'] else None,

    # SIM1 parameters
    sim1_apn=str(provisioning_dict['sim1_apn']) if provisioning_dict['sim1_apn'] else None,
    sim1_username=str(provisioning_dict['sim1_username']) if provisioning_dict['sim1_username'] else None,
    sim1_password=str(provisioning_dict['sim1_password']) if provisioning_dict['sim1_password'] else None,
    sim1_pdp_type=str(provisioning_dict['sim1_pdp_type']) if provisioning_dict['sim1_pdp_type'] else None,
    sim1_pin=str(provisioning_dict['sim1_pin']) if provisioning_dict['sim1_pin'] else None,
    sim1_puk=str(provisioning_dict['sim1_puk']) if provisioning_dict['sim1_puk'] else None,
    sim1_band_lock=validate_cellular_band_lock(provisioning_dict['sim1_band_lock']) if provisioning_dict['sim1_band_lock'] else "b0",

    # SIM2 parameters
    sim2_apn=str(provisioning_dict['sim2_apn']) if provisioning_dict['sim2_apn'] else None,
    sim2_username=str(provisioning_dict['sim2_username']) if provisioning_dict['sim2_username'] else None,
    sim2_password=str(provisioning_dict['sim2_password']) if provisioning_dict['sim2_password'] else None,
    sim2_pdp_type=str(provisioning_dict['sim2_pdp_type']) if provisioning_dict['sim2_pdp_type'] else None,
    sim2_pin=str(provisioning_dict['sim2_pin']) if provisioning_dict['sim2_pin'] else None,
    sim2_puk=str(provisioning_dict['sim2_puk']) if provisioning_dict['sim2_puk'] else None,
    sim2_band_lock=validate_cellular_band_lock(provisioning_dict['sim2_band_lock']) if provisioning_dict['sim2_band_lock'] else "b0",

    # MQTT parameters
    mqtt_hostname=str(provisioning_dict['mqtt_hostname']) if provisioning_dict['mqtt_hostname'] else None,
    mqtt_port=validate_port(provisioning_dict['mqtt_port']) if provisioning_dict['mqtt_port'] else None,
    mqtt_username=str(provisioning_dict['mqtt_username']) if provisioning_dict['mqtt_username'] else None,
    mqtt_password=str(provisioning_dict['mqtt_password']) if provisioning_dict['mqtt_password'] else None,
    mqtt_unsecure=validate_boolean(provisioning_dict['mqtt_unsecure']) if provisioning_dict['mqtt_unsecure'] else None,

    # Reset parameters
    reset_hour=validate_hour(provisioning_dict['reset_hour']) if provisioning_dict['reset_hour'] else None,
    reset_minute=validate_minute(provisioning_dict['reset_minute']) if provisioning_dict['reset_minute'] else None,

    # Time parameters
    ntp_addr=str(provisioning_dict['ntp_addr']) if provisioning_dict['ntp_addr'] else None,
    tz_offset_min=validate_timezone_offset(provisioning_dict['tz_offset_min']) if provisioning_dict['tz_offset_min'] else None,
    keepalive_interval=validate_interval(provisioning_dict['keepalive_interval']) if provisioning_dict['keepalive_interval'] else None,
    sim_selection = validate_sim_selection(provisioning_dict['sim_selection']) if provisioning_dict['sim_selection'] else None
    )
    
    nic_parameters_data, prov_sucess, summary = provisioning.provision_nic_parameters(args)
    return nic_parameters_data, prov_sucess, summary

