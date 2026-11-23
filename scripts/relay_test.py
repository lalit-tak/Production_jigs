import time
from datetime import datetime
import logging
from scripts.utils.communication import Communication

# Add parent directory to path to import Communication
# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'utils')))

def decode_relay_status_response(packet):
    try:
        if len(packet) >= 18:
            port_id = packet[9]
            # Extract uint32_t payload from indexes 12 to 14
            contrl_mode = int.from_bytes(packet[12:13], byteorder='big')
            contrl_state = int.from_bytes(packet[13:14], byteorder='big')
            output_state = int.from_bytes(packet[14:15], byteorder='big')
            off_reason = int.from_bytes(packet[15:16], byteorder='big')
            logging.info(f"Parsed response, Control_mode: {contrl_mode}, Control_state: {contrl_state}, Output_state: {output_state}, Off_state: {off_reason}")            
            logging.info(f"Port ID: {port_id}")
            logging.info(f"Cmd Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            return (contrl_mode, contrl_state, output_state, off_reason)
        else:
            logging.debug("❌ Packet too short to decode version.")
            logging.debug("Packet too short to decode version.")
            return (None, None, None, None)
    except Exception as e:
        logging.error(f"Failed to decode response error: {e}")
        return None

def decode_relay_on_off_response(packet):
    try:
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

def relay_off_test(serial_port):
    tx_data = bytes([
        0xaa, 0x01, 0x27, 0x1b, 0xc9,
        0xff, 0xff, 0xff, 0xff,
        0x04, 0x04, 0x03, 0x27, 0x1b, 0x00,
        0x1a, 0x7d
    ])
    
    com = Communication(serial_port)
    try:
        if not com.open():
            return None

        if com.send_data(tx_data, fixed_packet_len=16): # Expecting 15 bytes response
            time.sleep(0.1)  # Allow some time for the response to be processed
            response = com.read_response(timeout=5)
            if response:
                return decode_relay_on_off_response(response)
            else:
                return None
    finally:
        com.close()

    return None

def relay_status_test(serial_port):
    tx_data = bytes([
        0xaa, 0x01, 0x2a, 0xf8, 0xc9,
        0xff, 0xff, 0xff, 0xff,
        0x04, 0x04, 0x02, 0x2a, 0xf8,
        0x3c, 0x33
    ])

    com = Communication(serial_port)
    try:
        if not com.open():
            return None

        if com.send_data(tx_data, fixed_packet_len=18): # Expecting 15 bytes response
            time.sleep(0.1)  # Allow some time for the response to be processed
            response = com.read_response(timeout=5)
            if response:
                return decode_relay_status_response(response)
            else:
                return None
    finally:
        com.close()

    return None

def relay_on_test(serial_port):
    tx_data = bytes([
        0xaa, 0x01, 0x27, 0x1c, 0xc9,
        0xff, 0xff, 0xff, 0xff,
        0x04, 0x04, 0x03, 0x27, 0x1c, 0x00,
        0x8B, 0xa1
    ])

    com = Communication(serial_port)
    try:
        if not com.open():
            return None

        if com.send_data(tx_data, fixed_packet_len=16): # Expecting 15 bytes response
            time.sleep(0.1)  # Allow some time for the response to be processed
            response = com.read_response(timeout=5)
            if response:
                return decode_relay_on_off_response(response)
            else:
                return None
    finally:
        com.close()

    return None

# # Run Relay Off Test
# def run_relay_off_test(serial_port):
#     relay_off_test_status = 0
#     relay_off_test_status = relay_off_test(serial_port)
#     if relay_off_test_status is not None:
#         logging.info(f"Relay Off Test Status: {relay_off_test_status}, COM: {serial_port}")
#         return relay_off_test_status
#     else:
#         logging.info(f"Failed to get Relay Off Test Status, COM: {serial_port}")
#         return None

# # Run Relay On Test
# def run_relay_on_test(serial_port):
#     relay_on_test_status = 0
#     relay_on_test_status = relay_on_test(serial_port)
#     if relay_on_test_status is not None:
#         logging.info(f"Relay On Test Status: {relay_on_test_status}, COM: {serial_port}")
#         return relay_on_test_status
#     else:
#         logging.info(f"Failed to get Relay On Test Status, COM: {serial_port}")
#         return None

# Check Relay Status
def run_relay_status_check(serial_port):
    contrl_mode, contrl_state, output_state, off_reason = "none", "none", "none", "none"
    relay_test_status_dict = {
        "control_mode": "mode 5",
        "control_state": "connected",
        "output_state": "on",
        "off_reason": "none"
        }
    contrl_mode, contrl_state, output_state, off_reason = relay_status_test(serial_port)
    relay_test_status_dict["control_mode"] = contrl_mode
    relay_test_status_dict["control_state"] = contrl_state
    relay_test_status_dict["output_state"] = output_state
    relay_test_status_dict["off_reason"] = off_reason
    if relay_test_status_dict:
        logging.info(f"Relay Test Status: {relay_test_status_dict}, COM: {serial_port}")
        return relay_test_status_dict
    else:
        logging.info(f"Failed to get Relay Test Status, COM: {serial_port}")
        return None


# Run Relay Off Test
def run_relay_off_test(serial_port):
    relay_off_test_status = 0
    initial_get_relay_status = run_relay_status_check(serial_port)
    if initial_get_relay_status is not None:
        if initial_get_relay_status["output_state"] == 0:
            logging.info(f"Relay Status Check Passed, COM: {serial_port}")
            return (1003, 'pass')
        else:
            relay_off_test_status = relay_off_test(serial_port)
            if relay_off_test_status is not None:
                logging.info(f"Relay Off Test Status: {relay_off_test_status}, COM: {serial_port}")
                if relay_off_test_status == 1003:
                    logging.info(f"Relay Off Test Passed, COM: {serial_port}")
                    logging.info(f"Checking Relay Status, COM: {serial_port}")
                    get_relay_status = run_relay_status_check(serial_port)
                    logging.info(f"Relay Status: {get_relay_status}, COM: {serial_port}")
                    if get_relay_status is not None:
                        if get_relay_status["output_state"] == 0:
                            logging.info(f"Relay Status Check Passed, COM: {serial_port}")
                            return (relay_off_test_status, 'pass')
                        else:
                            logging.info(f"Relay Status Check Failed, COM: {serial_port}")
                            return (relay_off_test_status, 'fail')
                    else:
                        logging.info(f"Failed to get Relay Status, COM: {serial_port}")
                        return (relay_off_test_status, 'fail')
                return (relay_off_test_status, 'fail')
            else:
                logging.info(f"Failed to get Relay Off Test Status, COM: {serial_port}")
                return None
        
    else:
        logging.info(f"Failed to get Relay Status, COM: {serial_port}")
        return ('', 'fail')


# Run Relay On Test
def run_relay_on_test(serial_port):
    relay_on_test_status = 0
    initial_get_relay_status = run_relay_status_check(serial_port)
    if initial_get_relay_status is not None:
        if initial_get_relay_status["output_state"] == 1:
            logging.info(f"Relay Status Check Passed, COM: {serial_port}")
            return (1005, 'pass')
        else:
            relay_on_test_status = relay_on_test(serial_port)
            if relay_on_test_status is not None:
                logging.info(f"Relay On Test Status: {relay_on_test_status}, COM: {serial_port}")
                if relay_on_test_status == 1005:
                    logging.info(f"Relay On Test Passed, COM: {serial_port}")
                    logging.info(f"Checking Relay Status, COM: {serial_port}")
                    get_relay_status = run_relay_status_check(serial_port)
                    logging.info(f"Relay Status: {get_relay_status}, COM: {serial_port}")
                    if get_relay_status is not None:
                        if get_relay_status["output_state"] == 1:
                            logging.info(f"Relay Status Check Passed, COM: {serial_port}")
                            return (relay_on_test_status, 'pass')
                        else:
                            logging.info(f"Relay Status Check Failed, COM: {serial_port}")
                            return (relay_on_test_status, 'fail')
                    else:
                        logging.info(f"Failed to get Relay Status, COM: {serial_port}")
                        return (relay_on_test_status, 'fail')
                return (relay_on_test_status, 'fail')
            else:
                logging.info(f"Failed to get Relay On Test Status, COM: {serial_port}")
                return None
        
    else:
        logging.info(f"Failed to get Relay Status, COM: {serial_port}")
        return ('', 'fail')
