import sys
import os
import time
from datetime import datetime

# Import Communication from utils directory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'utils')))
from communication import Communication

def send_clear_event_by_category(com):
    tx_data = bytes([
        0xAA, 0x01, 0x4E, 0x47, 0xC9,
        0xFF, 0xFF, 0xFF, 0xFF,
        0x04, 0x04, 0x03,
        0xCB, 0x47, 0x05, 0x11, 0xB7
    ])
    
    print("\n--- Sending Cover Open Record Clear Command ---")
    if com.send_data(tx_data, fixed_packet_len=16):
        response = com.read_response(timeout=5)
        if response:
            port_id = response[9]
            print(f"✅ Cover Open Clear ACK received from Port ID: {port_id}")
            print(f"🕒 Cmd Time : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            return True
    print("❌ Failed to receive ACK for Cover Open Record Clear.")
    return False

def decode_cover_open_status(packet):
    try:
        if len(packet) >= 15:
            port_id = packet[9]
            cover_status = packet[12]
            print(f"\n--- Cover Open Status Response ---")
            print(f"📍 Port ID       : {port_id}")
            print(f"🕒 Cmd Time      : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"🧾 Cover Status  : {'Closed' if cover_status else 'Open'} (value={cover_status})")
            return cover_status
        else:
            print("❌ Packet too short to decode cover open status.")
            return None
    except Exception as e:
        print(f"❌ Failed to decode cover open status: {e}")
        return None

def get_cover_open_status(com):
    tx_data = bytes([
        0xAA, 0x1, 0x4E, 0x47, 0xC9,
        0xFF, 0xFF, 0xFF, 0xFF,
        0x4, 0x4, 0x2,
        0xF2, 0x39, 0x47, 0xC4
    ])
    
    print("\n--- Sending Get Cover Open Status Command ---")
    if com.send_data(tx_data, fixed_packet_len=15):  # ✅ Corrected length
        response = com.read_response(timeout=5)
        if response:
            return decode_cover_open_status(response)
    print("❌ Failed to receive response for Cover Open Status.")
    return None

# Main execution
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial_port", type=str, required=True, help="Serial port name (e.g., COM11)")
    args = parser.parse_args()

    print("\n=== Cover Open Test ===")

    com = Communication(args.serial_port)
    try:
        if com.open():
            if send_clear_event_by_category(com):
                time.sleep(3.0)  # Give hardware time to settle
                status = get_cover_open_status(com)
                if status is not None:
                    print(f"\n✅ Final Cover Open Status: {'OPEN' if status else 'CLOSED'}")
                    print("COVER_STATUS_RESULT:PASS")
                    print(f"COVER_STATUS_VALUE:{status}")
                else:
                    print("❌ Failed to get Cover Open status.")
                    print("COVER_STATUS_RESULT:FAIL")
                    print("COVER_STATUS_VALUE:N/A")
            else:
                print("❌ Failed to clear Cover Open event.")
                print("COVER_STATUS_RESULT:FAIL")
                print("COVER_STATUS_VALUE:N/A")
    finally:
        print(f"[{datetime.now()}] [CLOSING] COM port: {args.serial_port}", flush=True)
        com.close()
