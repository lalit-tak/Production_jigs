import serial
import threading
import queue
from datetime import datetime
import sys
import os

# Add parent directory to path to import Communication
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'utils')))
from communication import Communication

def decode_MDreset_button_status(packet):
    try:
        if len(packet) >= 15:
            port_id = packet[9]
            button_status = packet[12]
            print(f"🔌 Receive Port ID : {port_id}")
            print(f"🕒 Cmd Time        : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"🔘 Button Status   : {'Pressed' if button_status else 'Released'} (value={button_status})")
            return button_status
        else:
            print("❌ Packet too short to decode button status.")
            return None
    except Exception as e:
        print(f"❌ Failed to decode button status: {e}")
        return None

def get_MDreset_button_status(serial_port):
    tx_data = bytes([
        0xAA, 0x01, 0x4E, 0x47, 0xC9,
        0xFF, 0xFF, 0xFF, 0xFF,
        0x04, 0x04, 0x02, 0xF2, 0x3B,
        0x21, 0xA6
    ])

    com = Communication(serial_port)
    try:
        if not com.open():
            return None

        if com.send_data(tx_data):
            response = com.read_response(timeout=5)
            if response:
                return decode_MDreset_button_status(response)
    finally:
        com.close()

    return None

# Example usage
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial_port", type=str, required=True, help="Serial port name (e.g., COM5)")
    args = parser.parse_args()

    print("\n--- Checking MD Reset Button Status ---")
    status = get_MDreset_button_status(args.serial_port)
    if status is not None:
        print(f"MD Reset Button Status: {'Released' if status else 'Pressed'} (value={status})")
    else:
        print("❌ Failed to retrieve MD reset button status.")
