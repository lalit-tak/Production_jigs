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

def decode_3p_voltage(packet):
    try:
        if len(packet) >= 26:
            # Payload starts at index 12, next 12 bytes are 3 values of 4 bytes each
            r_bytes = packet[12:16]
            y_bytes = packet[16:20]
            b_bytes = packet[20:24]

            r_voltage = int.from_bytes(r_bytes, byteorder='big') / 1000.0
            y_voltage = int.from_bytes(y_bytes, byteorder='big') / 1000.0
            b_voltage = int.from_bytes(b_bytes, byteorder='big') / 1000.0

            print(f"Receive Port ID : {packet[9]}")
            print(f"Cmd Time       : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"R_Voltage     : {r_voltage:.3f} V")
            print(f"Y_Voltage     : {y_voltage:.3f} V")
            print(f"B_Voltage     : {b_voltage:.3f} V")

            return {
                'R': r_voltage,
                'Y': y_voltage,
                'B': b_voltage
            }
        else:
            print("❌ Packet too short to decode 3-phase voltage.")
            return None
    except Exception as e:
        print(f"❌ Failed to decode 3-phase voltage: {e}")
        return None

def get_3p_voltage(serial_port):
    tx_data = bytes([
        0xAA, 0x1, 0x4E, 0x47, 0xC9,
        0xFF, 0xFF, 0xFF, 0xFF,
        0x4, 0x4, 0x2, 0xF2, 0x33,
        0xA8, 0x0F
    ])

    com = Communication(serial_port)
    try:
        if not com.open():
            return None

        if com.send_data(tx_data, fixed_packet_len=26): # Expecting 26 bytes response
            response = com.read_response(timeout=7)
            if response:
                return decode_3p_voltage(response)
    finally:
        com.close()

    return None

# Example usage
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial_port", type=str, required=True, help="Serial port name (e.g., COM5)")
    args = parser.parse_args()

    print("\n--- Checking 3-Phase Voltage ---")
    voltages = get_3p_voltage(args.serial_port)
    if voltages:
        print(f"\n✅ Final Voltage Values:")
        for phase, voltage in voltages.items():
            print(f"  Phase {phase}: {voltage:.3f} V")
    else:
        print("❌ Failed to retrieve 3-phase voltage.")
