import serial
import time
import argparse
import threading
import queue
import re
import os
import logging
import concurrent.futures
from datetime import datetime

class Communication:
    SERIAL_BAUDRATE = 19200
    TIMEOUT =  7 #5-second timeout

    def __init__(self, serial_port):
        self.serial_port = serial_port
        self.ser = None
        self.response_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.thread = None

    def open(self):
        try:
            if self.ser is None or not self.ser.is_open:
                #print(f"Opening COM port {self.serial_port}...")
                self.ser = serial.Serial(
                    self.serial_port,
                    self.SERIAL_BAUDRATE,
                    timeout=self.TIMEOUT
                )
                self.stop_event.clear()
                self.thread = threading.Thread(target=self._read_thread, daemon=True)
                self.thread.start()
        except serial.SerialException as e:
            #print(f"❌ Failed to open COM port: {e}")
            return False
        return True

    def _read_thread(self):
        packet = bytearray()
        while not self.stop_event.is_set():
            try:
                byte = self.ser.read(1)  # Read one byte at a time
                if byte:
                    packet.append(byte[0])
                    print(f"Received byte --> {byte.hex()}")

                    # Check for start of packet (0x7E)
                    if packet[0] != 0x7E:
                        packet.clear()
                        continue
                    
                    # Check for end of packet (0x7E)
                    if len(packet) > 1 and packet[-1] == 0x7E:
                        print(f"Complete packet received --> {packet.hex(' ')}")

                        # Validate the 10th byte (index 9) is 0x00 and 11th byte (index 10) is 0x15
                        if len(packet) > 10 and packet[4] == 0x15:
                            print("✅ Valid packet received.")
                            self.response_queue.put(packet)

                            # ✅ Break the loop once a valid packet is received
                            self.stop_event.set()
                            break
                        else:
                            print("❌ Invalid packet received (10th byte is not 0x15). Ignoring...")
                            packet.clear()

                else:
                    print("No response received (timeout).")

            except serial.SerialException as e:
                print(f"❌ Serial read error: {e}")
                self.stop_event.set()


    def send_data(self, data):
        if not self.ser or not self.ser.is_open:
            if not self.open():
                return False
        try:
            self.ser.write(data)
           # print(f"Sent --> {data.hex(' ')}")
            return True
        except serial.SerialException as e:
            print(f"❌ Failed to send data: {e}")
            return False

    def read_response(self, timeout=10):
        try:
            return self.response_queue.get(timeout=timeout)
        except queue.Empty:
            print("❌ No response received within timeout.")
            return None

    def close(self):
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join()
        if self.ser and self.ser.is_open:
            self.ser.close()
            #print("COM port closed.")

def load_expected_firmware_version(file_path):
    try:
        with open(file_path, 'r') as file:
            version = file.read().strip()
            return tuple(map(int, version.split('.')))
    except Exception as e:
        print(f"❌ Error reading firmware config: {e}")
        return None

def extract_firmware_version(response):
    if len(response) >= 15:
        fw_major = response[5]
        fw_minor = response[6]
        fw_patch = response[7]
        fw_build = response[8]
        return (fw_major, fw_minor, fw_patch, fw_build)
    return None

# Function to check firmware version for a single device
def check_firmware_version(com_port, serial_number, firmware_config):
    """Check firmware version for a single device and return the result."""
    try:
        expected_version = load_expected_firmware_version(firmware_config)
        if not expected_version:
           # print(f"❌ Failed to load expected firmware version for {serial_number}.")
            return serial_number, False, None, None
        
        com = Communication(com_port)
        result = False
        version_str = None
        expected_str = '.'.join(map(str, expected_version))
        
        if not com.open():
            return serial_number, False, None, expected_str
        
        try:
            send_data = bytes.fromhex('7E FF 12 00 14 84 5F 7E')
            if com.send_data(send_data):
                response = com.read_response(timeout=5)
                if response:
                    firmware_version = extract_firmware_version(response)
                    if firmware_version:
                        version_str = '.'.join(map(str, firmware_version))
                        print(f"✅ Firmware Version for {serial_number} --> {version_str}")
                        if firmware_version == expected_version:
                            #print(f"✅ Firmware version matches expected version for {serial_number}!")
                            result = True
                        else:
                            print(f"❌ Firmware version mismatch for {serial_number}! Actual: {version_str} Expected: {expected_str}")
                    else:
                        print(f"❌ Failed to extract firmware version from response for {serial_number}.")
                else:
                    print(f"❌ No response received for {serial_number}.")
            else:
                print(f"❌ Failed to send data to {serial_number}.")
        finally:
            com.close()
        
        return serial_number, result, version_str, expected_str
    except Exception as e:
        print(f"❌ Error checking firmware version for {serial_number}: {e}")
        return serial_number, False, None, None

# Test the module
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial_port", type=str, required=True, help="Serial port used to communicate with the device.")
    parser.add_argument("--firmware_config", type=str, required=True, help="Path to firmware version config file.")
    parser.add_argument("--serial_number", type=str, required=True, help="Serial number of the device.")
    args = parser.parse_args()
    
    serial_number, result, version, expected = check_firmware_version(args.serial_port, args.serial_number, args.firmware_config)
    print(f"Test result: {'PASS' if result else 'FAIL'}")
    print(f"Version: {version}, Expected: {expected}")