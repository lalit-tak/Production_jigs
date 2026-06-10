import serial
import threading
import queue
from datetime import datetime
import sys
import os

# Add parent directory to path to import Communication
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'utils')))
from communication import Communication

def decode_push_button1_status(packet):
    try:
        if len(packet) >= 15:
            status = packet[12]
            print(f"Receive Port ID : {packet[9]}")
            print(f"Cmd Time        : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"Push Button 1   : {'Not Pressed' if status == 1 else 'Pressed'} (value={status})")
            return status
        else:
            print("❌ Packet too short to decode Push Button 1 status.")
            return None
    except Exception as e:
        print(f"❌ Failed to decode Push Button 1 status: {e}")
        return None

def get_push_button1_status(serial_port):
    tx_data = bytes([
        0xAA, 0x1, 0x4E, 0x47, 0xC9,
        0xFF, 0xFF, 0xFF, 0xFF,
        0x4, 0x4, 0x2, 0xF2, 0x37,
        0x64, 0xCB
    ])

    com = Communication(serial_port)
    try:
        if not com.open():
            return None

        if com.send_data(tx_data, fixed_packet_len=15): # Expecting 15 bytes response
            response = com.read_response(timeout=5)
            if response:
                return decode_push_button1_status(response)
    finally:
        com.close()

    return None

# Example usage
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial_port", type=str, required=True, help="Serial port name (e.g., COM5)")
    args = parser.parse_args()

    print("\n--- Checking Push Button 1 Status ---")
    status = get_push_button1_status(args.serial_port)
    if status is not None:
        print(f"\n Push Button 1: {'✅ Not Pressed' if status == 1 else '🔴 Pressed'}")
    else:
        print("❌ Failed to retrieve Push Button 1 status.")
