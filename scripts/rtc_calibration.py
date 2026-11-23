"""
RTC Calibration / PPM Calibration - BYPASS placeholder.

test_plan.xlsx's "RTC Calibration/PPM Calibration" group (Reset RTC / Get
temperature / Set & Calibrate RTC, rows 23-25, run over the meter's optical
COM port) is not implemented yet. run_rtc_calibration_test() always reports
success without talking to the meter, so the "RTC Calibration/PPM
Calibration" row can sit in the sequence and be exercised end-to-end while
the real protocol (tx/rx byte layout, decode, expected response) is worked
out - see scripts/memory_test.py or scripts/version_check.py for the pattern
the real implementation should probably follow (Communication.open() /
send_data() / read_response(), then a decode_*_response() for the payload).

test_impl.run_rtc_calibration is the only caller; nothing else needs to
change when this gets its real implementation.
"""

import time
from datetime import datetime
import logging
from scripts.utils.communication import Communication
import serial
import binascii

HEADER = b"\x68\x0B\x68"
FRAME_LEN = 14

def calculate_crc(data: bytes) -> bytes:
    da = bytearray()
    ba_len = len(data)

    for i in range(ba_len):
        da.append(data[i])

    # If odd length, append 0x00
    if (ba_len % 2) != 0:
        da.append(0x00)

    # CRC16 XMODEM
    c = binascii.crc_hqx(bytes(da), 0)
    # print("CRC:", hex(c))
    # print("CRC High Byte:", c // 256)
    # print("CRC Low Byte:", c % 256)
    return c

def parse_frame(f):
    if f[:3] != HEADER or f[12:14] != b"\r\n":
        return None
    if (-sum(f[1:11])) & 0xFF != f[11]:          # checksum check
        return None
    raw = int.from_bytes(f[5:9], "big")
    return {
        "serial":    int.from_bytes(f[3:5], "big"),
        "ticks":     raw,                           # e.g. 1000015
        "freq_hz":   raw / 1_000_000,               # e.g. 1.000015
        "drift_ppm": int.from_bytes(f[9:11], "big", signed=True),
    }

def read_frames(port):
    ser = serial.Serial(port, 9600, bytesize=8, parity="N", stopbits=1, timeout=2)
    ser.dtr = True                    # Docklight shows DTR ON, jig is wired to DTR
    ser.reset_input_buffer()
    buf = bytearray()
    try:
        while True:
            buf += ser.read(ser.in_waiting or 1)   # blocks till at least 1 byte
            while True:
                i = buf.find(HEADER)
                if i < 0:
                    del buf[:-2]                   # keep possible partial header
                    break
                if len(buf) - i < FRAME_LEN:
                    del buf[:i]                    # wait for rest of frame
                    break
                frame = bytes(buf[i:i + FRAME_LEN])
                result = parse_frame(frame)
                if result:
                    del buf[:i + FRAME_LEN]
                    yield frame, result
                else:
                    del buf[:i + 1]                # bad frame, resync
            # break
    finally:
        ser.close()

def decode_get_temperature_response(packet):
    try:
        if len(packet) >= 24:
            port_id = packet[9]
            # Extract uint32_t payload from indexes 12 to 22
            temperature = int.from_bytes(packet[12:16], byteorder='big')
            compensated_ppm = int.from_bytes(packet[16:20], byteorder='big')
            ticks = int.from_bytes(packet[20:21], byteorder='big')
            interval = int.from_bytes(packet[21:22], byteorder='big')
            logging.info(f"Parsed response, Temperature: {temperature}, Compensated PPM: {compensated_ppm}, Output_state: {ticks}, Off_state: {interval}")            
            logging.info(f"Port ID: {port_id}")
            logging.info(f"Cmd Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            return (temperature, compensated_ppm, ticks, interval)
        else:
            logging.debug("❌ Packet too short to decode version.")
            logging.debug("Packet too short to decode version.")
            return (None, None, None, None)
    except Exception as e:
        logging.error(f"Failed to decode response error: {e}")
        return None

def decode_reset_rtc_response(packet):
    try:
        if len(packet) >= 16:
            port_id = packet[9]
            # Extract uint32_t payload from indexes 12 to 14
            payload_bytes = packet[12:14][::-1]
            version = int.from_bytes(payload_bytes, byteorder='big')
            logging.info(f"Parsed response: {version}")
            logging.info(f"Port ID: {port_id}")
            logging.info(f"Cmd Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            return version
        else:
            logging.debug("❌ Packet too short to decode version.")
            logging.debug("Packet too short to decode version.")
            return None
    except Exception as e:
        logging.error(f"Failed to decode response error: {e}")
        return None

def reset_rtc_test(serial_port):
    logging.info(f"--- Reset RTC Test --- for COM: {serial_port}")
    tx_data = bytes([
        0xaa, 0x01, 0x4E, 0xBE, 0xc9,
        0xff, 0xff, 0xff, 0xff,
        0x04, 0x04, 0x03, 0x4E, 0xBE, 0x00,
        0x0E, 0x2D
    ])
    
    com = Communication(serial_port)
    try:
        if not com.open():
            return None

        if com.send_data(tx_data, fixed_packet_len=16): # Expecting 15 bytes response
            time.sleep(0.1)  # Allow some time for the response to be processed
            response = com.read_response(timeout=5)
            if response:
                return decode_reset_rtc_response(response)
            else:
                return None
    finally:
        com.close()

    return None

def get_temperature_test(serial_port):
    tx_data = bytes([
        0xaa, 0x01, 0x4E, 0xBC, 0xc9,
        0xff, 0xff, 0xff, 0xff,
        0x04, 0x04, 0x02, 0x4E, 0xBC, 0x18,
        0x11
    ])

    com = Communication(serial_port)
    try:
        if not com.open():
            return None

        if com.send_data(tx_data, fixed_packet_len=24): # Expecting 24 bytes response
            time.sleep(0.1)  # Allow some time for the response to be processed
            response = com.read_response(timeout=5)
            if response:
                return decode_get_temperature_response(response)
            else:
                return None
    finally:
        com.close()

    return None

def get_rtc_ticks_drift_test(calibrator_port):
    calibrator_reading = {
        "ppm": None,
        "drift": None
    }
    try:
        for frame, r in read_frames(calibrator_port):
            print(f"{frame.hex(' ').upper()} | SN={r['serial']} "
                    f"F={r['freq_hz']:.6f} Hz Drift={r['drift_ppm']:+d} ppm")
            calibrator_reading["ppm"] = r['ticks']
            calibrator_reading["drift"] = f"{r['drift_ppm']:+d}"
            return calibrator_reading
    except KeyboardInterrupt:
        return calibrator_reading

def set_ppm_rtc(serial_port, ppm_value, temp_value):
    tx_data = bytes([0xaa, 0x01, 0x4E, 0xBD, 0xC9, 0xFF, 0xFF, 0xFF, 0xFF, 0x04, 0x04, 0x0A, 0x4E, 0xBD])
    temp_bytes = temp_value.to_bytes(4, "big")
    ppm_bytes = ppm_value.to_bytes(4, "big")
    
    tx_data = tx_data + ppm_bytes + temp_bytes 

    crc = calculate_crc(tx_data[1:])  # Calculate CRC for the payload
    logging.info(f"Calculated CRC: {crc >> 8:02X},{crc & 0xFF:02X} for com: {serial_port}")
    tx_data += crc.to_bytes(2, "big")
    logging.info(f"Final TX Data: {tx_data.hex(' ').upper()} for com: {serial_port}")
    
    com = Communication(serial_port)
    try:
        if not com.open():
            return None

        if com.send_data(tx_data, fixed_packet_len=16): # Expecting 16 bytes response
            time.sleep(0.1)  # Allow some time for the response to be processed
            response = com.read_response(timeout=5)
            if response:
                return decode_reset_rtc_response(response)
            else:
                return None
    finally:
        com.close()

    return None

def run_rtc_calibration_test(serial_port, calibrator_port):
    """
    BYPASS - always returns a fixed success value instead of actually
    resetting/reading/calibrating the meter's RTC over `serial_port`.
    """
    set_rtc_calibration_result = {
        'reset_rtc': None,
        'set_temperature': None,
        'get_rtc_ticks': None,
        'get_rtc_interval': None,
        'calibrator_ppm': None,
        'calibrator_drift': None,
        "set_rtc_calibration": False
    }
    try:
        logging.info(f"RTC Calibration/PPM Calibration - COM: {serial_port}")
        reset_rtc_result = reset_rtc_test(serial_port)
        set_rtc_calibration_result['reset_rtc'] = reset_rtc_result
        if reset_rtc_result != 1000:
            return set_rtc_calibration_result
        else:
            time.sleep(25)
            get_temp_result = get_temperature_test(serial_port)
            set_rtc_calibration_result['set_temperature'] = get_temp_result[0]
            set_rtc_calibration_result['get_rtc_ticks'] = get_temp_result[1]
            set_rtc_calibration_result['get_rtc_interval'] = get_temp_result[2]

            if (get_temp_result is None) or (None in get_temp_result):
                logging.info(f"Failed to get temperature, COM: {serial_port}")
                return set_rtc_calibration_result
            else:
                set_temperature = get_temp_result[0]//1000
                logging.info(f"Set temperature, COM: {serial_port}")

                # time.sleep(8)
                get_rtc_ticks_result = get_rtc_ticks_drift_test(calibrator_port)
                set_rtc_calibration_result['calibrator_ppm'] = get_rtc_ticks_result.get('ppm', None)
                set_rtc_calibration_result['calibrator_drift'] = get_rtc_ticks_result.get('drift', None)
                logging.info(f"Fetched Calibrator values: {get_rtc_ticks_result}, COM: {serial_port}")
                
                if (get_rtc_ticks_result.get('drift', None) is None) or (get_rtc_ticks_result.get('ppm', None) is None) or (str(get_rtc_ticks_result.get('ppm', None)) == "0"):
                    logging.info(f"Failed to get RTC ticks, COM: {serial_port}")
                    return set_rtc_calibration_result
                else:
                    set_ppm_rtc_result = set_ppm_rtc(serial_port, ppm_value=get_rtc_ticks_result.get('ppm', None), temp_value=set_temperature)
                    logging.info(f"Set PPM/RTC result: {set_ppm_rtc_result}, COM: {serial_port}")
                    if set_ppm_rtc_result != 1000:
                        logging.info(f"Failed to set PPM/RTC, COM: {serial_port}")
                        set_rtc_calibration_result["set_rtc_calibration"] = False
                        return set_rtc_calibration_result
                    else:
                        logging.info(f"Set PPM/RTC successfully, COM: {serial_port}")
                        set_rtc_calibration_result["set_rtc_calibration"] = True
                        return set_rtc_calibration_result
    except Exception as e:
        logging.error(f"Exception occurred during RTC Calibration/PPM Calibration: {e}, COM: {serial_port}")
        return set_rtc_calibration_result

def get_rtc_calibration_result(serial_port, calibrator_port):
    """
    BYPASS - always returns a fixed success value instead of actually
    resetting/reading/calibrating the meter's RTC over `serial_port`.
    """
    calibrator_reading = {
        'calibrator_ppm': None,
        'calibrator_drift': None,
        "set_rtc_calibration": False
    }
    post_set_calibrtor_result = get_rtc_ticks_drift_test(calibrator_port)
    calibrator_reading['calibrator_ppm'] = post_set_calibrtor_result.get('ppm', None)
    calibrator_reading['calibrator_drift'] = post_set_calibrtor_result.get('drift', None)
    logging.info(f"Fetched Calibrator values after calibration: {post_set_calibrtor_result}, COM: {serial_port}")

    if (post_set_calibrtor_result.get('drift', None) is None) or (post_set_calibrtor_result.get('ppm', None) is None):
        logging.info(f"Failed to get RTC ticks after calibration, COM: {serial_port}")
        calibrator_reading["set_rtc_calibration"] = False
        return calibrator_reading
    else:
        logging.info(f"Fetched Calibrator values after calibration: {post_set_calibrtor_result}, COM: {serial_port}")
        if (abs(int(calibrator_reading['calibrator_drift'])) <= 10):
            calibrator_reading["set_rtc_calibration"] = True
        else:
            calibrator_reading["set_rtc_calibration"] = False
        return calibrator_reading
