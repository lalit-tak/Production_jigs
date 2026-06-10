import serial
import threading
import queue
from datetime import datetime
import sys
import os

# Add parent directory to path to import Communication
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'utils')))
from communication import Communication

# -----------------------------
# Decode eFuse Mode Status
# -----------------------------
def decode_efuse_mode(packet):
    try:
        if len(packet) >= 15:
            port_id = packet[9]
            status = packet[12]
            print(f"📥 Receive Port ID : {port_id}")
            print(f"🕒 Cmd Time        : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"🧮 Efuse Mode      : {'Enabled' if status == 1 else 'Disabled'} (value={status})")
            return status
        else:
            print("❌ Packet too short to decode Efuse mode.")
            return None
    except Exception as e:
        print(f"❌ Failed to decode Efuse mode: {e}")
        return None

def get_efuse_mode(serial_port):
    tx_data = bytes([
        0xAA, 0x01, 0x4E, 0x47, 0xC9,
        0xFF, 0xFF, 0xFF, 0xFF,
        0x04, 0x04, 0x02, 0xF2, 0x3D,
        0x8B, 0x00
    ])

    com = Communication(serial_port)
    try:
        if not com.open():
            return None

        if com.send_data(tx_data, expected_payload_len=1):  # 1-byte payload, fixed_packet_len=15
            response = com.read_response(timeout=5)
            if response:
                return decode_efuse_mode(response)
    finally:
        com.close()

    return None

# -----------------------------
# Main Function
# -----------------------------
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial_port", type=str, required=True, help="Serial port name (e.g., COM5)")
    args = parser.parse_args()

    print("\n--- Checking eFuse Mode ---")
    status = get_efuse_mode(args.serial_port)
    if status is not None:
        print(f"\n🧾 Efuse Mode: {'✅ Enabled' if status == 1 else '🚫 Disabled'}")
    else:
        print("❌ Failed to retrieve Efuse mode.")
