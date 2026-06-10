import serial
import time
import struct
import crcmod
from datetime import datetime
import sys
import os
import logging

# Add parent directory to path to import Communication
# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir)))

from scripts.utils.communication import Communication

# Define the CRC function (XMODEM)
crc16_xmodem = crcmod.predefined.mkCrcFun('xmodem')

# Function to calculate CRC for a given data byte array
def calculate_crc(data: bytes) -> bytes:
    crc = crc16_xmodem(data)
    return crc.to_bytes(2, byteorder='big')  # XMODEM expects big endian

# Function to get RTC PPM and Temperature from Meter
def get_rtc_ppm(serial_port: str) -> dict:
    print("\n--- Get RTC PPM and Temperature ---")
    logging.info(f"\n--- Get RTC PPM and Temperature COM: {serial_port}")
    com = Communication(serial_port)
    
    try:
        if not com.open():
            return None

        # Frame to send the command to get RTC PPM and Temperature
        body = bytes([
            0xAA, 0x01, 0x4E, 0x47, 0xC9,
            0xFF, 0xFF, 0xFF, 0xFF,
            0x04, 0x04, 0x02, 0xDE, 0xA9, 0xAC, 0x88
        ])
        
        # Calculate the CRC and append to the body
        crc = calculate_crc(body[1:])
        tx_data = body + crc

        # Send the data
        com.send_data(tx_data, expected_payload_len=2)
        
        # Wait for response
        response = com.read_response(timeout=5)

        if response and len(response) >= 24:
            print("🛠️ RTC PPM and Temperature: SUCCESS")
            logging.info(f"RTC PPM and Temperature: SUCCESS, COM{serial_port}")
            print(f"🕒 Cmd Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            # Parse response
            temperature = struct.unpack(">H", response[14:16])[0]  # Temperature (in Celsius)
            compensated_ppm = struct.unpack(">H", response[18:20])[0]  # Compensated PPM
            ticks = struct.unpack(">b", response[20:21])[0]  # Ticks
            interval = struct.unpack(">B", response[22:23])[0]  # Interval
            
            return {
                "temperature": temperature,
                "compensated_ppm": compensated_ppm,
                "ticks": ticks,
                "interval": interval
            }
        else:
            print("❌ Failed to get RTC PPM and Temperature.")
            logging.info(f"Failed to get RTC PPM and Temperature, COM{serial_port}")
            return None
    finally:
        com.close()

# Function to set the PPM and Temperature values in the Meter
def set_ppm_rtc(serial_port: str, ppm: int, temperature: int):
    print("\n--- Set PPM and Temperature in Meter ---")
    logging.info(f"\n--- Set PPM and Temperature in Meter, COM:{serial_port}")
    com = Communication(serial_port)

    try:
        if not com.open():
            return False
        
        # Construct the frame to set the PPM and Temperature (Fixed PPM = 1000000 and Temperature = 27)
        body = bytes([
            0xAA, 0x01, 0x4E, 0x47, 0xC9,
            0xFF, 0xFF, 0xFF, 0xFF,
            0x04, 0x04, 0x0A, 0xDE, 0xAA,
            0x00, 0x0F, 0x42, 0x40, 0x00, 0x00, 0x00,
            0x1B, 0xD4, 0x39  # Calculate CRC for the payload
        ])
        
        # CRC calculation
        crc = calculate_crc(body[1:])
        tx_data = body + crc
        
        # Send the data
        com.send_data(tx_data, expected_payload_len=2)
        
        # Wait for the response
        response = com.read_response(timeout=5)

        if response and len(response) >= 16:
            print("🛠️ Set PPM and Temperature: SUCCESS")
            print(f"🕒 Cmd Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            logging.info(f"Set PPM and Temperature: SUCCESS, COM: {serial_port}")
            return True
        else:
            print("❌ Failed to set PPM and Temperature.")
            logging.info(f"Failed to set PPM and Temperature, COM:{serial_port}")
            return False
    finally:
        com.close()

# Function to verify the PPM value in Meter
def verify_ppm_rtc(serial_port: str):
    print("\n--- Verify PPM Value in Meter ---")
    comp_result = {
        "temperature": None,
        "compensated_ppm": None,
        "ticks": None,
        "interval": None,
        'rtc_result': "fail"
    }
    
    com = Communication(serial_port)

    try:
        if not com.open():
            return False
        
        # Frame to get RTC PPM again to verify
        body = bytes([
            0xAA, 0x01, 0x4E, 0x47, 0xC9,
            0xFF, 0xFF, 0xFF, 0xFF,
            0x04, 0x04, 0x02, 0xDE, 0xA9, 0xAC, 0x88
        ])
        
        # Calculate the CRC and append
        crc = calculate_crc(body[1:])
        tx_data = body + crc
        
        # Send the data
        com.send_data(tx_data, expected_payload_len=2)
        
        # Wait for the response
        response = com.read_response(timeout=5)
        
        if response and len(response) >= 24:
            print("🛠️ RTC PPM Verification: SUCCESS")
            print(f"🕒 Cmd Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            # Parse the response
            temperature = struct.unpack(">H", response[14:16])[0]
            compensated_ppm = struct.unpack(">H", response[17:19])[0]
            ticks = struct.unpack(">b", response[20:21])[0]
            interval = struct.unpack(">B", response[21:22])[0]
            print(f"Temperature: {temperature // 1000}°C, Compensated PPM: {compensated_ppm}, Ticks: {ticks}, Interval: {interval}")
            comp_result["temperature"] = temperature//1000
            comp_result["compensated_ppm"] = compensated_ppm
            comp_result["interval"] = interval
            comp_result["ticks"] = ticks
            # Check conditions
            if compensated_ppm == 0 and ticks == 0 and interval == 1 :
                comp_result["rtc_result"] = "pass"
                print("✅ Calibration Successful")
                return comp_result, True
            else:
                comp_result["rtc_result"] = "fail"
                print("❌ Calibration Failed")
                return comp_result, False
        else:
            print("❌ Failed to verify RTC PPM.")
            return comp_result, False
    finally:
        com.close()

# Main function to execute the complete flow
def rtc_calibration(serial_port: str):
    # Step 1: Get RTC PPM and Temperature
    comp_result = {
        "temperature": None,
        "compensated_ppm": None,
        "ticks": None,
        "interval": None,
        'rtc_result': "fail"
    }
    comp_status = False
    data = get_rtc_ppm(serial_port)

    if data:
        temperature = data["temperature"] // 1000  # Divide by 1000 and take integer part
        ppm = 1000000  # Fixed value for PPM
        
        # Step 2: Set PPM and Temperature
        if set_ppm_rtc(serial_port, ppm, temperature):
            # Step 3: Verify PPM value
            comp_result, comp_status = verify_ppm_rtc(serial_port)
            if comp_status:
                print("\n✅ RTC Calibration Passed")
                logging.info(f"\nRTC Calibration Passed, COM{serial_port}, Result: {comp_result}")
                return True, comp_result
            else:
                print("\n❌ RTC Calibration Failed")
                logging.info(f"\nRTC Calibration Failed, COM{serial_port}, Result: {comp_result}")
                return False, comp_result
        else:
            print("\n❌ Failed to set PPM and Temperature.")
            logging.info(f"\nFailed to set PPM and Temperature, COM:{serial_port}, Result: {comp_result}")
            return False, comp_result
    else:
        print("\n❌ Failed to get RTC PPM and Temperature.")
        logging.info(f"\nFailed to get RTC PPM and Temperature, COM:{serial_port}, Result: {comp_result}")
        return False, comp_result

def run_rtc_calib(serial_port):
    comp_result = {
        "temperature": None,
        "compensated_ppm": None,
        "ticks": None,
        "interval": None,
        'rtc_result': "fail"
    }
    comp_status = False
    comp_status, comp_result  = rtc_calibration(serial_port)
    print(comp_result, comp_status)
    if comp_status:
        return (comp_result, 'pass')
    else:
        return (comp_result, 'fail')


# if __name__ == "__main__":
#     print(run_rtc_calib("COM131"),'------------')
