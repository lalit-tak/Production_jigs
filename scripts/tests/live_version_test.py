import serial
import threading
import queue
import time
from datetime import datetime
import sys
import os
import logging

# Add parent directory to path to import Communication
# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'utils')))

from scripts.utils.communication import Communication

def decode_int_version(packet):
    try:
        if len(packet) >= 17:
            port_id = packet[9]
            # Extract uint32_t payload from indexes 13 to 16
            payload_bytes = packet[12:16]
            print(payload_bytes.hex(' '))
            version = int.from_bytes(payload_bytes, byteorder='big')
            print(f"✅ Parsed Internal Version: {version}")
            print(f"🛠️  Port ID: {port_id}")
            logging.info(f"Parsed Internal Version: {version}")
            logging.info(f"Port ID: {port_id}")
            print(f"🕒 Cmd Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            return version
        else:
            print("❌ Packet too short to decode version.")
            logging.info("Packet too short to decode version.")
            return None
    except Exception as e:
        print(f"❌ Failed to decode Internal version: {e}")
        logging.info(f"Failed to decode Internal version: {e}")
        return None

def decode_live_version(packet):
    try:
        if len(packet) >= 17:
            port_id = packet[9]
            # Extract uint32_t payload from indexes 13 to 16
            payload_bytes = packet[12:16]
            print(payload_bytes.hex(' '))
            version = int.from_bytes(payload_bytes, byteorder='big')
            print(f"✅ Parsed Live Version: {version}")
            print(f"🛠️  Port ID: {port_id}")
            logging.info(f"Parsed Live Version: {version}")
            logging.info(f"Port ID: {port_id}")
            print(f"🕒 Cmd Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            return version
        else:
            print("❌ Packet too short to decode version.")
            logging.info("Packet too short to decode version.")
            return None
    except Exception as e:
        print(f"❌ Failed to decode live version: {e}")
        logging.info(f"Failed to decode live version: {e}")
        return None

def get_int_version(serial_port):
    tx_data = bytes([
    0xaa, 0x1, 0x4e, 0x47, 0xc9,
    0xff, 0xff, 0xff, 0xff,
    0x4, 0x4, 0x2, 0xd3, 0x12,
    0x2c, 0x2e
    ])

    com = Communication(serial_port)
    try:
        if not com.open():
            return None

        if com.send_data(tx_data, fixed_packet_len=17): # Expecting 17 bytes response
            time.sleep(0.1)  # Allow some time for the response to be processed
            response = com.read_response(timeout=5)
            if response:
                return decode_int_version(response)
    finally:
        com.close()

    return None

def get_live_version(serial_port):
    tx_data = bytes([
        0xAA, 0x1, 0x4E, 0x47, 0xC9,
        0xFF, 0xFF, 0xFF, 0xFF,
        0x4, 0x4, 0x2, 0x4E, 0x47,
        0xE7, 0xC
    ])

    com = Communication(serial_port)
    try:
        if not com.open():
            return None

        if com.send_data(tx_data, fixed_packet_len=17): # Expecting 17 bytes response
            time.sleep(0.1)  # Allow some time for the response to be processed
            response = com.read_response(timeout=5)
            if response:
                return decode_live_version(response)
    finally:
        com.close()

    return None

# Example usage
# if __name__ == "__main__":
def run_live_version_check(serial_port):
    version_dict = {}
    
    version = get_live_version(serial_port)
    int_version = get_int_version(serial_port)
    latest_version = f"{version}_{int_version}"

    version_dict["live_version"] = version
    version_dict["internal_version"] = int_version
    logging.info(f"GET Live and Internal Version Values: {version_dict}, COM: {serial_port}")
    return version_dict


# if __name__ == "__main__":
#     import argparse
#     parser = argparse.ArgumentParser()
#     parser.add_argument("--serial_port", type=str, required=True, help="Serial port name (e.g., COM5)")
#     args = parser.parse_args()

#     version_info = run_live_version_check(args.serial_port)
#     if version_info:
#         print(f"\n📊 Version Information: {version_info}")
#     else:
#         print("❌ Failed to retrieve version information.")