import time
from datetime import datetime
import logging
from scripts.utils.communication import Communication

# Add parent directory to path to import Communication
# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'utils')))


def decode_int_version(packet):
    try:
        if len(packet) >= 16:
            port_id = packet[9]
            # Extract uint32_t payload from indexes 12 to 15
            payload_bytes = packet[12:14]
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
        if len(packet) >= 18:
            port_id = packet[9]
            # Extract uint32_t payload from indexes 12 to 16
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
    0xaa, 0x01, 0xd3, 0x12, 0xc9,
    0xff, 0xff, 0xff, 0xff,
    0x04, 0x04, 0x02, 0xd3, 0x12,
    0x20, 0x1f
    ])

    com = Communication(serial_port)
    try:
        if not com.open():
            return None

        if com.send_data(tx_data, fixed_packet_len=16): # Expecting 16 bytes response
            time.sleep(0.1)  # Allow some time for the response to be processed
            response = com.read_response(timeout=5)
            if response:
                return decode_int_version(response)
    finally:
        com.close()

    return None

def get_live_version(serial_port):
    tx_data = bytes([
        0xaa, 0x01, 0x4e, 0x47, 0xc9,
        0xff, 0xff, 0xff, 0xff,
        0x4, 0x4, 0x2, 0x4e, 0x47,
        0xe7, 0xc
    ])

    com = Communication(serial_port)
    try:
        if not com.open():
            return None

        if com.send_data(tx_data, fixed_packet_len=18): # Expecting 18 bytes response
            time.sleep(0.1)  # Allow some time for the response to be processed
            response = com.read_response(timeout=5)
            if response:
                return decode_live_version(response)
    finally:
        com.close()

    return None

def run_live_version_check(serial_port, curr_live_version):
    live_version = "0000"
    live_version = get_live_version(serial_port)
    logging.info(f"Fetched Live Version: {live_version}, current version: {curr_live_version}, COM: {serial_port}")
    if live_version is not None:
        logging.info(f"Fetched Live Version: {live_version}, current version: {curr_live_version}, COM: {serial_port}")
        return live_version
    else:
        logging.info(f"Failed to get Live Version, COM: {serial_port}")
        return None

def encode_version_to_int(version_str, num_bytes):
    """
    Turn a dotted version string like "4.2.0.0" into the same big-endian
    integer decode_live_version()/decode_int_version() would produce for it -
    one byte (0-255) per dot-separated part, most-significant part first.
    Raises ValueError if version_str doesn't have exactly num_bytes parts or
    any part is out of byte range.
    """
    parts = version_str.strip().split(".")
    if len(parts) != num_bytes:
        raise ValueError(f"expected {num_bytes} dot-separated parts, got {len(parts)} in {version_str!r}")
    values = [int(p) for p in parts]
    if any(v < 0 or v > 255 for v in values):
        raise ValueError(f"version part out of byte range (0-255) in {version_str!r}")
    return int.from_bytes(bytes(values), byteorder="big")


def format_version_int(version_int, num_bytes):
    """Inverse of encode_version_to_int() - render a decoded packet int as a dotted string."""
    return ".".join(str(b) for b in version_int.to_bytes(num_bytes, byteorder="big"))


def run_int_version_check(serial_port, curr_int_version):
    int_version = '00'
    int_version = get_int_version(serial_port)
    if int_version is not None:
        logging.info(f"Fetched Internal Version: {int_version}, current version: {curr_int_version}, COM: {serial_port}")
        return int_version
    else:
        logging.info(f"Failed to get Live Version, COM: {serial_port}")
        return None

