import time
from datetime import datetime
import logging
from scripts.utils.communication import Communication

# Add parent directory to path to import Communication
# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'utils')))

# def decode_response(packet):
#     try:
#         if len(packet) >= 26:
#             port_id = packet[9]
#             # Extract uint32_t payload from indexes 12 to 13
#             AA 00 00 06 93 01 FF EB C9 13 04 0C 43 30 34 41 30 45 42 46 34 38 31 36 00 88
#             C0:4A:0E:BF:48:16
#             payload_bytes = packet[12:13]
#             version = int.from_bytes(payload_bytes, byteorder='big')
#             logging.info(f"Parsed response: {version}")
#             logging.info(f"Port ID: {port_id}")
#             logging.info(f"Cmd Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
#             return version
#         else:
#             logging.debug("❌ Packet too short to decode version.")
#             logging.debug("Packet too short to decode version.")
#             return None
#     except Exception as e:
#         logging.error(f"Failed to decode response error: {e}")
#         return None

def decode_response(packet):
    try:
        if len(packet) >= 26:
            port_id = packet[9]
            # Extract MAC address from bytes 12-23
            mac_text = packet[12:24].decode("ascii")
            mac = ":".join(mac_text[i:i + 2] for i in range(0, 12, 2))
            logging.info(f"Parsed MAC: {mac}")
            logging.info(f"Port ID: {port_id}")
            logging.info(f"Cmd Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            return mac
        else:
            logging.debug("Packet too short to decode MAC.")
            return None
    except Exception as e:
        logging.error(f"Failed to decode response error: {e}")
        return None

def omkar_energy_test(serial_port):
    tx_data = bytes([
        0xaa, 0x01, 0xff, 0xeb, 0xc9,
        0xff, 0xff, 0xff, 0xff,
        0x04, 0x04, 0x02, 0xff, 0xeb,
        0x6f, 0xb2
    ])
    com = Communication(serial_port)
    try:
        if not com.open():
            return None

        if com.send_data(tx_data, fixed_packet_len=26): # Expecting 15 bytes response
            time.sleep(0.1)  # Allow some time for the response to be processed
            response = com.read_response(timeout=5)
            if response:
                return decode_response(response)
            else:
                return None
    finally:
        com.close()

    return None

# Run Rx/Tx Test
def run_omkar_energy_test(serial_port):
    omkar_energy_test_status = 0
    omkar_energy_test_status = omkar_energy_test(serial_port)
    if omkar_energy_test_status is not None:
        logging.info(f"RX/TX Test result, Status: {omkar_energy_test_status}, COM: {serial_port}")
        return omkar_energy_test_status
    else:
        logging.info(f"Failed to get RX/TX Test Status, COM: {serial_port}")
        return None
