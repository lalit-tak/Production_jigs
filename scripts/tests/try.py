import serial
from pprint import pprint
import serial.tools.list_ports
import time
import threading

trigger_command = b'*T'
port = 'COM77'
is_retry = True
baud_rate = 9600
scan_results = {}
scan_lock = threading.Lock()



retry_text = " (RETRY)" if is_retry else ""

try:
    # logging.info(f"[Station {station_num}] Scanning port {port}{retry_text}")
    with serial.Serial(port, baud_rate, timeout=3) as ser:
        ser.write(trigger_command)
        # logging.debug(f"[Station {station_num}] Sent trigger command to {port}{retry_text}")
        
        time.sleep(1)
        scanned_data = ser.readline().decode('utf-8', errors='ignore').strip()
        
        # scanned_data = "ABC-123E2"

        with threading.Lock():
            if scanned_data:
                scan_results[1] = {
                    'serial': scanned_data,
                    'port': port,
                    'status': 'success',
                    'retry_attempt': is_retry
                }
            else:
                scan_results[1] = {
                    'serial': None,
                    'port': port,
                    'status': 'no_data',
                    'retry_attempt': is_retry
                }
                
except serial.SerialException as e:
    with scan_lock:
        scan_results[1] = {
            'serial': None,
            'port': port,
            'status': 'error',
            'error': str(e),
            'retry_attempt': is_retry
        }
        
except Exception as e:
    with scan_lock:
        scan_results[1] = {
            'serial': None,
            'port': port,
            'status': 'error',
            'error': str(e),
            'retry_attempt': is_retry
        }

print(scan_results)