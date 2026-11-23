import time
from datetime import datetime
import logging
from scripts.utils.communication import Communication

# Add parent directory to path to import Communication
# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'utils')))

def decode_response(packet):
    try:
        if len(packet) >= 15:
            port_id = packet[9]
            # Extract uint32_t payload from indexes 12 to 13
            payload_bytes = packet[12:14][::-1]
            version = int.from_bytes(payload_bytes, byteorder='big')
            logging.info(f"Parsed response: {version}")
            logging.info(f"Port ID: {port_id}")
            logging.info(f"Cmd Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            return version
        else:
            logging.debug("❌ Packet too short to decode version.")
            logging.debug("Packet too short to decode version.")
            return None
    except Exception as e:
        logging.error(f"Failed to decode response error: {e}")
        return None

def calib_led_test(serial_port):
    tx_data = bytes([
        0xaa, 0x01, 0xff, 0xe5, 0xc9,
        0xff, 0xff, 0xff, 0xff,
        0x04, 0x04, 0x03, 0xff, 0xe5, 0x00,
        0x2a, 0x9f
    ])
    com = Communication(serial_port)
    try:
        if not com.open():
            return None

        if com.send_data(tx_data, fixed_packet_len=15): # Expecting 15 bytes response
            time.sleep(0.1)  # Allow some time for the response to be processed
            response = com.read_response(timeout=5)
            if response:
                return decode_response(response)
            else:
                return None
    finally:
        com.close()

    return None

def lcd_led_test(serial_port):
    tx_data = bytes([
        0xaa, 0x01, 0xff, 0xe7, 0xc9,
        0xff, 0xff, 0xff, 0xff,
        0x04, 0x04, 0x03, 0xff, 0xe7, 0x00,
        0x4a, 0x17
    ])

    com = Communication(serial_port)
    try:
        if not com.open():
            return None

        if com.send_data(tx_data, fixed_packet_len=15): # Expecting 15 bytes response
            time.sleep(0.1)  # Allow some time for the response to be processed
            response = com.read_response(timeout=5)
            if response:
                return decode_response(response)
            else:
                return None
    finally:
        com.close()

    return None

# Run LCD LED Test
def run_lcd_led_test(serial_port):
    lcd_led_test_status = 0
    lcd_led_test_status = lcd_led_test(serial_port)
    logging.info(f"LCD LED Test result, Status: {lcd_led_test_status}, COM: {serial_port}")
    if lcd_led_test_status is not None:
        return lcd_led_test_status
    else:
        logging.info(f"Failed to get LCD LED Test Status, COM: {serial_port}")
        return None

# Run Calibration Test
def run_calib_led_test(serial_port):
    calib_led_test_status = 0
    calib_led_test_status = calib_led_test(serial_port)
    if calib_led_test_status is not None:
        logging.info(f"Calibration Test result, Status: {calib_led_test_status}, COM: {serial_port}")
        return calib_led_test_status
    else:
        logging.info(f"Failed to get Calibration Test Status, COM: {serial_port}")
        return None
