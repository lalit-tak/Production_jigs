import serial
import threading
import queue
from datetime import datetime
import sys
import os

# Add parent directory to path to import Communication
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'utils')))
from communication import Communication

def decode_rx_tx_status(packet):
    try:
        if len(packet) >= 15:
            status = packet[12]
            print(f"Receive Port ID : {packet[9]}")
            print(f"Cmd Time        : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"RX/TX Status    : {status} - {'Working' if status else 'Not Communicated'}")
            return status
        else:
            print("❌ Packet too short to decode RX/TX status.")
            return None
    except Exception as e:
        print(f"❌ Failed to decode RX/TX status: {e}")
        return None

def get_rx_tx_status(serial_port):
    tx_data = bytes([
        0xAA, 0x1, 0x4E, 0x47, 0xC9,
        0xFF, 0xFF, 0xFF, 0xFF,
        0x4, 0x4, 0x2, 0xF2, 0x3A,
        0x12, 0x97
    ])

    com = Communication(serial_port)
    try:
        if not com.open():
            return None

        if com.send_data(tx_data, fixed_packet_len=15): # Expecting 15 bytes response
            response = com.read_response(timeout=5)
            if response:
                return decode_rx_tx_status(response)
    finally:
        com.close()

    return None

# Example usage
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial_port", type=str, required=True, help="Serial port name (e.g., COM5)")
    args = parser.parse_args()

    print("\n--- Checking RX/TX Communication Status ---")
    status = get_rx_tx_status(args.serial_port)
    if status is not None:
        print(f"\n RX/TX Communication: {'✅ Working' if status else '❌ Not Communicated'}")
    else:
        print("❌ Failed to retrieve RX/TX status.")
