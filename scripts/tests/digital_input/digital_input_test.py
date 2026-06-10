import serial
import threading
import queue
from datetime import datetime
import sys
import os
import logging

# Add parent directory to path to import Communication
# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'utils')))
from scripts.utils.communication import Communication
# from communication import Communication

# -----------------------------
# Get Digital Input Status
# -----------------------------
def decode_digital_input_status(packet):
    try:
        if len(packet) >= 15:
            port_id = packet[9]
            status = packet[12]
            print(f"📥 Receive Port ID : {port_id}")
            print(f"🕒 Cmd Time        : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"🧮 Digital Input   : {status} (Binary: {bin(status)})")

            logging.info(f"Receive Port ID : {port_id}")
            logging.info(f"Cmd Time        : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            logging.info(f"Digital Input   : {status} (Binary: {bin(status)})")
            return status
        else:
            print("❌ Packet too short to decode digital input status.")
            logging.info("Packet too short to decode digital input status.")
            return None
    except Exception as e:
        print(f"❌ Failed to decode digital input status: {e}")
        logging.info(f"Failed to decode digital input status: {e}")
        return None

def get_digital_input_status(serial_port):
    tx_data = bytes([
        0xAA, 0x01, 0x4E, 0x47, 0xC9,
        0xFF, 0xFF, 0xFF, 0xFF,
        0x04, 0x04, 0x02, 0x75, 0x5A,
        0xA7, 0x77
    ])
    

    com = Communication(serial_port)
    try:
        if not com.open():
            return None

        if com.send_data(tx_data, expected_payload_len=1):  # 1 byte payload, fixed_packet_len=15
            response = com.read_response(timeout=5)
            if response:
                return decode_digital_input_status(response)
    finally:
        com.close()

    return None

# -----------------------------
# Main Function
# -----------------------------
# if __name__ == "__main__":
def run_digital_input(serial_port):

    print("\n--- Checking Digital Input Status ---")
    logging.info("\n--- Checking Digital Input Status ---")
    status = get_digital_input_status(serial_port)
    if status is not None:
        print(f"\n🧾 Digital Input Status: {status} (Binary: {bin(status)})")
        logging.info(f"\nDigital Input Status: {status} (Binary: {bin(status)}), COM: {serial_port}")
        return int(status)
    else:
        print("❌ Failed to retrieve digital input status.")
        logging.info(f"Failed to retrieve digital input status, COM: {serial_port}")
        return None


if __name__ == "__main__":
    print(run_digital_input("COM4"))