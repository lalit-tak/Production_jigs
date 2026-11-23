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
            payload_bytes = packet[12:13]
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

def decode_memory_response(packet):
    try:
        logging.info(f"Memory test response: {packet}")
        if len(packet) >= 16:
            port_id = packet[9]
            # Extract uint32_t payload from indexes 12 to 14
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

def memory_test(serial_port):
    tx_data = bytes([
        0xaa, 0x01, 0xff, 0xdf, 0xc9,
        0xff, 0xff, 0xff, 0xff,
        0x04, 0x04, 0x03, 0xff, 0xdf,
        0x00 ,0x84, 0x73
    ])
    # AA 01 FF DF C9 FF FF FF FF 04 04 03 FF DF 00 84 73
    

    com = Communication(serial_port)
    try:
        if not com.open():
            return None
        logging.info(f"Send byte array for memory test: {tx_data}")

        if com.send_data(tx_data, fixed_packet_len=16): # Expecting 15 bytes response
            time.sleep(0.1)  # Allow some time for the response to be processed
            response = com.read_response(timeout=5)
            if response:
                return decode_memory_response(response)
            else:
                return None
    finally:
        com.close()

    return None

def flash_test(serial_port):
    tx_data = bytes([
        0xaa, 0x01, 0xff, 0xdd, 0xc9,
        0xff, 0xff, 0xff, 0xff,
        0x04, 0x04, 0x02, 0xff, 0xdd, 0x92,
        0x4f
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

def eeprom_test(serial_port):
    tx_data = bytes([
        0xaa, 0x01, 0xff, 0xdc, 0xc9,
        0xff, 0xff, 0xff, 0xff,
        0x04, 0x04, 0x02, 0xff, 0xdc,
        0xa2, 0x0b
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

# Run Memory Test
def run_memory_test(serial_port):
    memory_test_status = 0
    memory_test_status = memory_test(serial_port)
    if memory_test_status is not None:
        logging.info(f"Memory Test result: {memory_test_status}, COM: {serial_port}")
        return memory_test_status
    else:
        logging.info(f"Failed to get Memory Test Status, COM: {serial_port}")
        return None

# Run Flash Test
def run_flash_test(serial_port):
    flash_test_status = 0
    flash_test_status = flash_test(serial_port)
    if flash_test_status is not None:
        logging.info(f"Flash Test result: {flash_test_status}, COM: {serial_port}")
        return flash_test_status
    else:
        logging.info(f"Failed to get Flash Test Status, COM: {serial_port}")
        return None

# Run EEPROM Test
def run_eeprom_test(serial_port):
    eeprom_test_status = 0
    eeprom_test_status = eeprom_test(serial_port)
    if eeprom_test_status is not None:
        logging.info(f"EEPROM Test result: {eeprom_test_status}, COM: {serial_port}")
        return eeprom_test_status
    else:
        logging.info(f"Failed to get EEPROM Test Status, COM: {serial_port}")
        return None