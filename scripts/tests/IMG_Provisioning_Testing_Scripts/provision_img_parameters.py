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

if __name__ == "__main__":
    logging.basicConfig(
        format="%(levelname)s %(asctime)s %(message)s", level=logging.INFO
    )

    parser = CustomArgumentParser(fromfile_prefix_chars="@")
    # Serial parameters
    parser.add_argument(
        "--serial_port",
        type=str,
        help="Serial port used to communicate with the NIC.",
        required=True,
    )
    parser.add_argument(
        "--baudrate",
        type=int,
        help=f"Serial port baudrate (default: {DEFAULT_BAUDRATE}).",
        default=DEFAULT_BAUDRATE,
    )

    # Wirepas parameters
    parser.add_argument(
        "--encryption_key",
        type=validate_key,
        help="Encryption Key used by the NIC. Must be specified as a 16 bytes value.",
        default=None,
    )
    parser.add_argument(
        "--authentication_key",
        type=validate_key,
        help="Authentication Key used by the NIC. Must be specified as a 16 bytes value.",
        default=None,
    )
    parser.add_argument(
        "--network_address",
        type=validate_network_address,
        help="Network address used by the NIC.",
        default=None,
    )
    parser.add_argument(
        "--network_channel",
        type=validate_network_channel,
        help="Network channel used by the NIC.",
        default=None,
    )
    parser.add_argument(
        "--node_address",
        type=validate_node_address,
        help="Node Address used by the NIC.",
        default=None,
    )
    parser.add_argument(
        "--sink_address",
        type=validate_sink_address,
        help="Sink Address used by the NIC.",
        default=None,
    )
    parser.add_argument(
        "--node_role",
        type=validate_node_role,
        help="Node Role used by the sink.",
        default=None,
    )
    
    # Gateway parameters
    parser.add_argument(
        "--gateway_id",
        type=str,
        help="Gateway ID",
        default=None,
    )
    parser.add_argument(
        "--cellular_info_diag_interval",
        type=validate_interval,
        help="Cellular info diagnostic interval in seconds",
        default=None,
    )
    parser.add_argument(
        "--network_info_diag_interval",
        type=validate_interval,
        help="Network info diagnostic interval in seconds",
        default=None,
    )
    parser.add_argument(
        "--gateway_info_diag_interval",
        type=validate_interval,
        help="Gateway info diagnostic interval in seconds",
        default=None,
    )

    # Meter parameters
    parser.add_argument(
        "--gw_key_enc_key",
        type=validate_key,
        help="GW Key Encryption Key. Must be specified as a 16 bytes value.",
        default=None,
    )
    parser.add_argument(
        "--mtr_auth_key",
        type=validate_key,
        help="Meter Authentication Key. Must be specified as a 16 bytes value.",
        default=None,
    )
    parser.add_argument(
        "--mtr_enc_key",
        type=validate_key,
        help="Meter Encryption Key. Must be specified as a 16 bytes value.",
        default=None,
    )
    parser.add_argument(
        "--mtr_mr_secret",
        type=validate_password,
        help="Meter MR Secret password",
        default=None,
    )
    parser.add_argument(
        "--mtr_us_secret",
        type=validate_password,
        help="Meter US Secret password",
        default=None,
    )
    parser.add_argument(
        "--mtr_fu_secret",
        type=validate_password,
        help="Meter FU Secret password",
        default=None,
    )
    parser.add_argument(
        "--mtr_baud_rate",
        type=int,
        help="Meter baud rate",
        default=None,
    )
    parser.add_argument(
        "--mtr_dlms_mode",
        type=str,
        help="Meter DLMS mode/interface",
        default=None,
    )

    # SIM1 parameters
    parser.add_argument(
        "--sim1_apn",
        type=str,
        help="SIM1 APN",
        default=None,
    )
    parser.add_argument(
        "--sim1_username",
        type=str,
        help="SIM1 username",
        default=None,
    )
    parser.add_argument(
        "--sim1_password",
        type=str,
        help="SIM1 password",
        default=None,
    )
    parser.add_argument(
        "--sim1_pdp_type",
        type=str,
        help="SIM1 PDP type",
        default=None,
    )
    parser.add_argument(
        "--sim1_pin",
        type=str,
        help="SIM1 PIN",
        default=None,
    )
    parser.add_argument(
        "--sim1_puk",
        type=str,
        help="SIM1 PUK",
        default=None,
    )

    # SIM2 parameters
    parser.add_argument(
        "--sim2_apn",
        type=str,
        help="SIM2 APN",
        default=None,
    )
    parser.add_argument(
        "--sim2_username",
        type=str,
        help="SIM2 username",
        default=None,
    )
    parser.add_argument(
        "--sim2_password",
        type=str,
        help="SIM2 password",
        default=None,
    )
    parser.add_argument(
        "--sim2_pdp_type",
        type=str,
        help="SIM2 PDP type",
        default=None,
    )
    parser.add_argument(
        "--sim2_pin",
        type=str,
        help="SIM2 PIN",
        default=None,
    )
    parser.add_argument(
        "--sim2_puk",
        type=str,
        help="SIM2 PUK",
        default=None,
    )

    # MQTT parameters
    parser.add_argument(
        "--mqtt_hostname",
        type=str,
        help="MQTT hostname",
        default=None,
    )
    parser.add_argument(
        "--mqtt_port",
        type=validate_port,
        help="MQTT port",
        default=None,
    )
    parser.add_argument(
        "--mqtt_username",
        type=str,
        help="MQTT username",
        default=None,
    )
    parser.add_argument(
        "--mqtt_password",
        type=str,
        help="MQTT password",
        default=None,
    )
    parser.add_argument(
        "--mqtt_unsecure",
        type=validate_boolean,
        help="MQTT unsecure flag (true/false)",
        default=None,
    )

    # Reset parameters
    parser.add_argument(
        "--reset_hour",
        type=validate_hour,
        help="Reset hour (0-23)",
        default=None,
    )
    parser.add_argument(
        "--reset_minute",
        type=validate_minute,
        help="Reset minute (0-59)",
        default=None,
    )

    # Time parameters
    parser.add_argument(
        "--ntp_addr",
        type=str,
        help="NTP server address",
        default=None,
    )
    parser.add_argument(
        "--tz_offset_min",
        type=validate_timezone_offset,
        help="Timezone offset in minutes (signed)",
        default=None,
    )
    parser.add_argument(
        "--keepalive_interval",
        type=validate_interval,
        help="Keepalive interval in seconds",
        default=None,
    )
    parser.add_argument(
        "--cellular_band_lock",
        type=validate_cellular_band_lock,
        help="Indicates which cellular bands the gateway can use. Maximum 5 bands can be set. Format: b1,b2,b41. Set to b0 to enable all bands.",
        default="b0",
    )
    parser.add_argument(
        "--sim_selection",
        type=validate_sim_selection,
        help=f"SIM selection mode: {', '.join(SIM_SELECTION_OPTIONS)}",
        default=None,
    )
    args = parser.parse_args()

    provisioning.provision_nic_parameters(args)
