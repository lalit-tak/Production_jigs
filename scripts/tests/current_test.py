import serial
import threading
import queue
import time
from datetime import datetime
import sys
import os

# Add parent directory to path to import Communication
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'utils')))
from communication import Communication

def decode_3p_current(packet):
    try:
        if len(packet) >= 29:
            # Payload starts at index 12, next 16 bytes = 4 values (4 × 4 bytes)
            r_bytes = packet[12:16]
            y_bytes = packet[16:20]
            b_bytes = packet[20:24]
            n_bytes = packet[24:28]

            r_current = int.from_bytes(r_bytes, byteorder='big') / 1000.0
            y_current = int.from_bytes(y_bytes, byteorder='big') / 1000.0
            b_current = int.from_bytes(b_bytes, byteorder='big') / 1000.0
            n_current = int.from_bytes(n_bytes, byteorder='big') / 1000.0

            print(f"Receive Port ID : {packet[9]}")
            print(f"Cmd Time       : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"R_Current      : {r_current:.3f} A")
            print(f"Y_Current      : {y_current:.3f} A")
            print(f"B_Current      : {b_current:.3f} A")
            print(f"Neutral Current: {n_current:.3f} A")

            return {
                'R': r_current,
                'Y': y_current,
                'B': b_current,
                'N': n_current
            }
        else:
            print("❌ Packet too short to decode 3-phase current.")
            return None
    except Exception as e:
        print(f"❌ Failed to decode 3-phase current: {e}")
        return None

def get_3p_current(serial_port):
    tx_data = bytes([
        0xAA, 0x1, 0x4E, 0x47, 0xC9,
        0xFF, 0xFF, 0xFF, 0xFF,
        0x4, 0x4, 0x2, 0xF2, 0x34,
        0x31, 0x98
    ])

    com = Communication(serial_port)
    try:
        if not com.open():
            return None

        if com.send_data(tx_data, fixed_packet_len=29): # Expecting 29 bytes response
            response = com.read_response(timeout=7)
            if response:
                return decode_3p_current(response)
    finally:
        com.close()

    return None

# Example usage
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial_port", type=str, required=True, help="Serial port name (e.g., COM5)")
    args = parser.parse_args()

    print("\n--- Checking 3-Phase Current ---")
    currents = get_3p_current(args.serial_port)
    if currents:
        print(f"\n✅ Final Current Values:")
        for phase, current in currents.items():
            label = "Neutral" if phase == 'N' else f"Phase {phase}"
            print(f"  {label}: {current:.3f} A")
    else:
        print("❌ Failed to retrieve 3-phase current.")
