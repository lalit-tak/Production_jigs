from datetime import datetime
import serial
import threading
import queue
import time
import sys
import os
import logging

print(f"[{datetime.now()}] [BOOT] Starting memory_test.py", flush=True)
print(f"[{datetime.now()}] [INFO] memory_test.py script STARTED", flush=True)

# Add parent directory to path to import Communication
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'utils')))
from communication import Communication

def decode_memory_result(packet):
    """Decode memory test result with enhanced error handling"""
    try:
        if len(packet) >= 16:
            port_id = packet[9]
            eeprom = packet[12]
            flash = packet[13]
            print(f"🔌 Receive Port ID : {port_id}", flush=True)
            print(f"🕒 Cmd Time        : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
            print(f"💾 EEPROM Test     : {'PASS' if eeprom == 1 else 'FAIL'}", flush=True)
            print(f"💡 Flash Test      : {'PASS' if flash == 1 else 'FAIL'}", flush=True)
            return (eeprom, flash)
        else:
            print(f"❌ Packet too short to decode memory result. Length: {len(packet)}", flush=True)
            return None
    except Exception as e:
        print(f"❌ Failed to decode memory result: {e}", flush=True)
        return None

def safe_open_with_timeout(com, timeout=15):
    """Enhanced COM port opening with strict timeout and better error handling"""
    print(f"[{datetime.now()}] [INFO] Attempting to open COM port with timeout: {timeout} seconds", flush=True)
    
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ValueError("Timeout must be a positive number")
    
    result = [False]
    error_msg = [None]
    done = threading.Event()
    
    def attempt_open():
        try:
            print(f"[{datetime.now()}] [DEBUG] Thread starting COM port open attempt...", flush=True)
            result[0] = com.open()
            if result[0]:
                print(f"[{datetime.now()}] [DEBUG] COM port opened successfully in thread", flush=True)
            else:
                print(f"[{datetime.now()}] [DEBUG] COM port open returned False in thread", flush=True)
                error_msg[0] = "COM port open returned False"
        except Exception as e:
            print(f"[{datetime.now()}] [DEBUG] Exception in COM port open thread: {e}", flush=True)
            error_msg[0] = str(e)
            result[0] = False
        finally:
            print(f"[{datetime.now()}] [DEBUG] Signaling done event", flush=True)
            done.set()

    open_thread = threading.Thread(target=attempt_open, daemon=True)
    open_thread.start()
    
    # Wait for completion with timeout
    finished_in_time = done.wait(timeout)
    
    if not finished_in_time:
        print(f"❌ COM port open timed out after {timeout} seconds", flush=True)
        return False, "Timeout during COM port open"
    
    if error_msg[0]:
        print(f"❌ COM port open failed: {error_msg[0]}", flush=True)
        return False, error_msg[0]
    
    return result[0], None

def run_memory_test_with_enhanced_timeout(serial_port):
    """Enhanced memory test with comprehensive timeout handling and error recovery"""
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
    print(f"🚀 [{datetime.now()}] Memory test started on port: {serial_port}", flush=True)

    tx_run_test = bytes([
        0xAA, 0x01, 0x4E, 0x47, 0xC9,
        0xFF, 0xFF, 0xFF, 0xFF,
        0x04, 0x04, 0x03, 0xF2, 0x31, 0x00, 0xB8, 0xD9
    ])

    tx_get_result = bytes([
        0xAA, 0x01, 0x4E, 0x47, 0xC9,
        0xFF, 0xFF, 0xFF, 0xFF,
        0x04, 0x04, 0x02, 0xF2, 0x32, 0x9B, 0x3E
    ])

    com = Communication(serial_port)
    max_retries = 2
    
    for attempt in range(max_retries + 1):
        try:
            is_retry = attempt > 0
            if is_retry:
                print(f"🔄 Retry attempt {attempt} for memory test on {serial_port}", flush=True)
                time.sleep(2)  # Brief delay before retry
            
            print(f"[{datetime.now()}] 🛠 About to call com.open() (attempt {attempt + 1})", flush=True)

            # Enhanced COM port opening with timeout
            open_success, open_error = safe_open_with_timeout(com, timeout=15)
            if not open_success:
                error_msg = f"Failed to open COM port: {open_error or 'Unknown error'}"
                print(f"❌ {error_msg}", flush=True)
                
                if attempt < max_retries:
                    print(f"🔄 Will retry opening COM port (attempt {attempt + 1}/{max_retries + 1})", flush=True)
                    continue
                else:
                    print("❌ All retry attempts exhausted for COM port opening.", flush=True)
                    print("EEPROM_RESULT:FAIL", flush=True)
                    print("FLASH_RESULT:FAIL", flush=True)
                    return None

            print("✅ COM port opened successfully", flush=True)

            print("\n🧪 Running display memory test...", flush=True)
            print("Sending memory test command...", flush=True)
            time.sleep(0.5)

            # Send memory test command with timeout
            send_success = False
            try:
                send_success = com.send_data(tx_run_test, fixed_packet_len=16)
            except Exception as e:
                print(f"❌ Exception during send_data: {e}", flush=True)
                send_success = False

            if not send_success:
                print("❌ Failed to send memory test command.", flush=True)
                com.close()
                
                if attempt < max_retries:
                    print(f"🔄 Will retry sending command (attempt {attempt + 1}/{max_retries + 1})", flush=True)
                    continue
                else:
                    print("EEPROM_RESULT:FAIL", flush=True)
                    print("FLASH_RESULT:FAIL", flush=True)
                    return None

            # Read response with enhanced timeout handling
            response1 = None
            try:
                response1 = com.read_response(timeout=10)
            except Exception as e:
                print(f"❌ Exception during read_response: {e}", flush=True)
                response1 = None

            if not response1:
                print("❌ No response to memory test command.", flush=True)
                com.close()
                
                if attempt < max_retries:
                    print(f"🔄 Will retry memory test command (attempt {attempt + 1}/{max_retries + 1})", flush=True)
                    continue
                else:
                    print("EEPROM_RESULT:FAIL", flush=True)
                    print("FLASH_RESULT:FAIL", flush=True)
                    return None

            print("\n📥 Fetching memory test result...", flush=True)
            time.sleep(2)

            # Send get result command with timeout
            send_success = False
            try:
                send_success = com.send_data(tx_get_result, fixed_packet_len=16)
            except Exception as e:
                print(f"❌ Exception during send get result: {e}", flush=True)
                send_success = False

            if not send_success:
                print("❌ Failed to send memory result fetch command.", flush=True)
                com.close()
                
                if attempt < max_retries:
                    print(f"🔄 Will retry get result command (attempt {attempt + 1}/{max_retries + 1})", flush=True)
                    continue
                else:
                    print("EEPROM_RESULT:FAIL", flush=True)
                    print("FLASH_RESULT:FAIL", flush=True)
                    return None

            # Read final response with enhanced timeout handling
            response2 = None
            try:
                response2 = com.read_response(timeout=10)
            except Exception as e:
                print(f"❌ Exception during final read_response: {e}", flush=True)
                response2 = None

            if response2:
                result = decode_memory_result(response2)
                com.close()
                return result
            else:
                print("❌ No response received for memory result.", flush=True)
                com.close()
                
                if attempt < max_retries:
                    print(f"🔄 Will retry get result (attempt {attempt + 1}/{max_retries + 1})", flush=True)
                    continue
                else:
                    print("EEPROM_RESULT:FAIL", flush=True)
                    print("FLASH_RESULT:FAIL", flush=True)
                    return None

        except Exception as ex:
            error_msg = f"Exception during memory test attempt {attempt + 1}: {ex}"
            print(f"❌ {error_msg}", flush=True)
            
            try:
                com.close()
            except:
                pass
            
            if attempt < max_retries:
                print(f"🔄 Will retry due to exception (attempt {attempt + 1}/{max_retries + 1})", flush=True)
                continue
            else:
                print("❌ All retry attempts exhausted due to exceptions.", flush=True)
                print("EEPROM_RESULT:FAIL", flush=True)
                print("FLASH_RESULT:FAIL", flush=True)
                return None

    # Should not reach here, but just in case
    print("❌ Unexpected end of retry loop.", flush=True)
    print("EEPROM_RESULT:FAIL", flush=True)
    print("FLASH_RESULT:FAIL", flush=True)
    return None

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial_port", type=str, required=True, help="Serial port name (e.g., COM5)")
    print("\n--- Memory Test Sequence ---", flush=True)
    print("This script will run a memory test on the connected device.", flush=True)
    args = parser.parse_args()

    result = run_memory_test_with_enhanced_timeout(args.serial_port)
    if result:
        eeprom, flash = result
        print(f"\n✅ Final Result → EEPROM: {'PASS' if eeprom == 1 else 'FAIL'}, Flash: {'PASS' if flash == 1 else 'FAIL'}", flush=True)
        print(f"EEPROM_RESULT:{'PASS' if eeprom == 1 else 'FAIL'}", flush=True)
        print(f"FLASH_RESULT:{'PASS' if flash == 1 else 'FAIL'}", flush=True)
    else:
        print("\n❌ Memory test failed or timed out", flush=True)
        print("EEPROM_RESULT:FAIL", flush=True)
        print("FLASH_RESULT:FAIL", flush=True)
