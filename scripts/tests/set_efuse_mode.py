import serial
import threading
import queue
from datetime import datetime
import argparse
import crcmod
import sys
import os

# Add parent directory to path to import Communication
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'utils')))
from communication import Communication

# -----------------------------
# CRC Calculation (XMODEM)
# -----------------------------
crc16_xmodem = crcmod.predefined.mkCrcFun('xmodem')


def calculate_crc(data: bytes) -> bytes:
    crc = crc16_xmodem(data)
    return crc.to_bytes(2, byteorder='big')  # XMODEM expects big endian


# -----------------------------
# Set Efuse Mode (Enable = 1, Disable = 0)
# -----------------------------
def set_efuse_mode(serial_port, enable):
    print("\n--- Set eFuse Mode ---")
    print(f"\n➡️ Setting eFuse Mode to {'Enable' if enable else 'Disable'}...")

    com = Communication(serial_port)
    try:
        if not com.open():
            return False

        # Frame without CRC
        body = bytes([
            0xAA, 0x01, 0x4E, 0x47, 0xC9,
            0xFF, 0xFF, 0xFF, 0xFF,
            0x04, 0x04, 0x03,  # header
            0xF2, 0x3C,         # command ID
            enable              # argument
        ])

        crc = calculate_crc(body[1:])  # Skip 0xAA
        tx_data = body + crc

        if com.send_data(tx_data, expected_payload_len=2): # Expecting 2 bytes payload, fixed_packet_len=16
            response = com.read_response(timeout=5)
            if response and len(response) >= 16:
                print("🛠️ Set Efuse Mode: SUCCESS")
                print(f"🕒 Cmd Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                return True
            else:
                print("❌ Failed to set eFuse mode.")
    finally:
        com.close()

    return False


# -----------------------------
# Main
# -----------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial_port", type=str, required=True, help="Serial port name (e.g., COM5)")
    parser.add_argument("--enable", type=int, choices=[0, 1], required=True, help="Set eFuse mode (0 = Disable, 1 = Enable)")
    args = parser.parse_args()

    success = set_efuse_mode(args.serial_port, args.enable)
    if success:
        print(f"\n✅ Efuse mode {'enabled' if args.enable else 'disabled'} successfully.")
    else:
        print("❌ Operation failed.")
