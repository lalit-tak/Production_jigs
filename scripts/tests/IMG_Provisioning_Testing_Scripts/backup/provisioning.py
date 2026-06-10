# Copyright 2024 Wirepas Ltd licensed under Apache License, Version 2.0
#
# See file LICENSE for full license details.
#

import argparse
from colorama import Fore
import queue
import logging
import wirepas_provisioning
import serial
import sys
import threading
import os
from wirepas_provisioning import WirepasProvisioning
from threading import Thread, Event
from struct import pack, unpack
from enum import Enum
from time import sleep
import time
from threading import Timer
import subprocess

from yahdlc import (
    FRAME_ACK,
    FRAME_DATA,
    FRAME_NACK,
    FCSError,
    MessageError,
    frame_data,
    get_data,
    get_data_reset,
)


class ExitCodes(Enum):
    SUCCESS = 0
    SENDING_FAILED = 1
    RECEPTION_TIMEOUT = 2
    INVALID_PARAMETERS = 3
    MISSING_PARAMETERS = 4
    HDLC_PACKET_TOO_LARGE = 5
    CALL_TO_MAIN = 6
    SERIAL_ERROR = 7


class MessageType(Enum):
    PROVISIONING_WRITE_REQUEST = 0
    PROVISIONING_WRITE_RESPONSE = 1
    PROVISIONING_READ_REQUEST = 2
    PROVISIONING_READ_RESPONSE = 3
    PROVISIONING_REBOOT_REQUEST = 4
    EXIT_FACTORY_MODE = 5


PROVISIONING_CHALLENGE = b"WPP\n"
PROVISIONING_CHALLENGE_RESP = b"OK\n"
PROVISIONING_CHALLENGE_PERIOD_S = 0.090  # Every 90 ms
PROVISIONING_RESET_INTERVAL_S = 0.5  # 500ms
PROVISIONING_STOP_RX_WAIT_S = 1.0  # 1s
SOFT_RESET_SEQUENCE_QUERY = b"[SOFT_RESET_SEQUENCE_QUERY]"

class Communication:
    SERIAL_BAUDRATE = 9600
    ACK_NACK_TIMEOUT_S = 2.000
    MAX_TX_ATTEMPT = 8
    DRY_RUN_RECEIVE_TIMEOUT_S = 2
    READ_PARAMETERS_TIMEOUT_S = 2
    EMBEDDED_HDLC_BUFFER_MAX_SIZE = 2048

    ser = serial.Serial()

    hdlc_decode = Event()
    tx_seq = 0
    
    # Add a stop event for the rx thread
    rx_thread_stop = threading.Event()
    rx_thread = None

    tx_queue = queue.Queue(MAX_TX_ATTEMPT)
    rx_challenge_queue = queue.Queue()
    rx_ftype_queue = queue.Queue()
    provisioning_success_queue = queue.Queue()
    read_parameters_queue = queue.Queue()

# Managing the communication with the NIC
nic_com = Communication()


def error_print_and_exit(message: str, error_code: ExitCodes):
    logging.error(Fore.RED + message + Fore.RESET)
    exit(error_code.value)


def error_print(message):
    logging.error(Fore.RED + message + Fore.RESET)

def success_print(message):
    logging.info(Fore.GREEN + message + Fore.RESET)


def send_raw_hdlc_data(com: Communication, data: bytes):
    hdlc_frame = frame_data(data, FRAME_DATA, com.tx_seq)

    if len(hdlc_frame) > com.EMBEDDED_HDLC_BUFFER_MAX_SIZE:
        error_print_and_exit(
            "Length of the HDLC packet cannot be processed by the embedded application!",
            ExitCodes.HDLC_PACKET_TOO_LARGE,
        )

    for _ in range(com.MAX_TX_ATTEMPT):
        com.tx_queue.put_nowait(hdlc_frame)

    # Cleaning any remaining items stored in the rx_ftype queue
    with com.rx_ftype_queue.mutex:
        com.rx_ftype_queue.queue.clear()

    ret = False
    try:
        while com.tx_queue.empty() is False:
            packet = com.tx_queue.get()
            logging.debug(
                "Sending %d bytes long data frame: %s with seq: %d",
                len(packet),
                packet.hex(),
                com.tx_seq,
            )
            com.ser.write(packet)
            try:
                ftype = com.rx_ftype_queue.get(timeout=com.ACK_NACK_TIMEOUT_S)
            except queue.Empty:
                logging.warning("Timeout detected!")
                continue

            if ftype != FRAME_ACK:
                ret = False
                continue
            else:
                with com.tx_queue.mutex:
                    com.tx_queue.queue.clear()
                ret = True

        com.tx_seq += 1
        com.tx_seq %= 7

        return ret

    except serial.SerialException as e:
        error_print_and_exit(f"Serial connection problem: {str(e)}", ExitCodes.SERIAL_ERROR)


def send_factory_mode_message(com: Communication, data: bytes, type: MessageType) -> bool:
    # Generating header
    header = pack("<BB", 0, type.value)
    message = header + data

    return send_raw_hdlc_data(com, message)


def parse_message_received(com: Communication, data: bytes):
    # parse header
    version, type = unpack("<BB", data[0:2])
    if version != 0:
        logging.warning("Not a valid protocol version")
        return

    # Convert to enum
    type = MessageType(type)

    # Remove header from received data
    data = data[2:]

    if type == MessageType.PROVISIONING_WRITE_RESPONSE:
        if wirepas_provisioning.is_provisioning_dry_run_successful(data) is True:
            logging.debug("Dry Run Successful! Sending reboot request")
            com.provisioning_success_queue.put(True)
        else:
            logging.debug("Dry Run returned an error! No reboot request sent!")
            com.provisioning_success_queue.put(False)
    elif type == MessageType.PROVISIONING_READ_RESPONSE:
        logging.debug("Read Request Response Received")
        com.read_parameters_queue.put(data)

    else:
        logging.warning("Unknown type received: %s", type)  


def rx_callback(com: Communication):
    buffer = bytes()
    while not com.rx_thread_stop.is_set():
        try:
            # Check if there's data available or wait briefly
            if com.ser.in_waiting == 0:
                sleep(0.01)  # Small delay to prevent busy waiting
                continue
                
            # Read available data
            new_data = com.ser.read(com.ser.in_waiting or 1)
            
            if com.hdlc_decode.is_set():
                # HDLC Reading mode
                buffer += new_data
                
                # Process buffer until no more complete frames
                while True:
                    try:
                        # Reset decoder state before attempting to decode
                        get_data_reset()
                        
                        # Try to extract a frame
                        data, ftype, seq_no = get_data(buffer)
                        
                        # Log successful frame reception
                        logging.debug(f"HDLC frame received - Type: {ftype}, Seq: {seq_no}, Data: {data.hex()}")
                        
                        # Handle the frame based on its type
                        com.rx_ftype_queue.put(ftype)
                        if ftype == FRAME_DATA:
                            # Send ACK for data frames
                            com.ser.write(frame_data("", FRAME_ACK, seq_no))
                            parse_message_received(com, data)
                        
                        # Find the end flag position to remove processed data
                        # The +1 is to include the end flag itself
                        end_pos = buffer.find(b'\x7e', 1) + 1
                        if end_pos > 0:
                            buffer = buffer[end_pos:]
                        else:
                            buffer = bytes()
                            
                    except MessageError:
                        # No complete frame in buffer yet
                        break
                        
                    except FCSError:
                        logging.warning(f"Bad FCS in frame: {buffer.hex()}")
                        # Find next flag and continue from there
                        next_flag = buffer.find(b'\x7e', 1)
                        if next_flag > 0:
                            buffer = buffer[next_flag:]
                        else:
                            buffer = bytes()
                        
                # Prevent buffer from growing too large
                if len(buffer) > com.EMBEDDED_HDLC_BUFFER_MAX_SIZE * 2:
                    # Keep only data after the last flag
                    last_flag = buffer.rfind(b'\x7e')
                    if last_flag >= 0:
                        buffer = buffer[last_flag:]
                    else:
                        buffer = bytes()
                    logging.warning("Buffer overflow, truncated to last flag")
                    
            else:
                # Serial Reading (No protocol) - Challenge response mode
                buffer += new_data
                if PROVISIONING_CHALLENGE_RESP in buffer:
                    com.rx_challenge_queue.put(True)
                    buffer = bytes()
                    
        except (serial.SerialException, OSError) as e:
            # Handle serial port errors (including closed port)
            if not com.rx_thread_stop.is_set():
                logging.warning(f"Serial error in rx_callback: {e}")
            break
        except Exception as e:
            logging.error(f"Unexpected error in rx_callback: {e}")
            break
    
    logging.debug("rx_callback thread stopped")

def wait_for_challenge_response_with_reset_loop(com: Communication):
    # Disable HDLC Serial Reading initially
    com.hdlc_decode.clear()
    
    logging.info("Sending Soft Reset sequence and Provisioning Challenge in loop...")
    
    last_reset_time = 0
    last_challenge_time = 0
    
    # Clear any existing challenge responses
    with com.rx_challenge_queue.mutex:
        com.rx_challenge_queue.queue.clear()
    
    start_time = time.time()
    
    while com.rx_challenge_queue.empty():
        current_time = time.time()
        
        # Send soft reset sequence periodically
        if current_time - last_reset_time >= PROVISIONING_RESET_INTERVAL_S:
            try:
                com.ser.write(SOFT_RESET_SEQUENCE_QUERY)
                logging.debug("Soft reset sequence query sent")
                last_reset_time = current_time
            except serial.SerialException as e:
                error_print_and_exit(f"Serial connection problem during soft reset: {str(e)}", ExitCodes.SERIAL_ERROR)
        
        # Send challenge periodically
        if current_time - last_challenge_time >= PROVISIONING_CHALLENGE_PERIOD_S:
            try:
                com.ser.write(PROVISIONING_CHALLENGE)
                logging.debug("Challenge sent")
                last_challenge_time = current_time
            except serial.SerialException as e:
                error_print_and_exit(f"Serial connection problem during challenge: {str(e)}", ExitCodes.SERIAL_ERROR)
        
        sleep(0.01)
    
    # Clear any remaining challenge responses
    with com.rx_challenge_queue.mutex:
        com.rx_challenge_queue.queue.clear()
    
    # Enable HDLC Serial Reading for normal operation
    com.hdlc_decode.set()
    logging.info("Received Provisioning Challenge Response!")

def perform_parameters_provisioning(com: Communication, wp_prov: WirepasProvisioning):
    provisioning_packet = wp_prov.get_provisioning_packet()

    logging.debug(f"Provisioning packet size: {len(provisioning_packet)} bytes")
    logging.debug(f"Provisioning packet hex: {provisioning_packet.hex()}")

    logging.info("Sending Provisioning Packet")
    if (
        send_factory_mode_message(com, provisioning_packet, MessageType.PROVISIONING_WRITE_REQUEST)
        is False
    ):
        error_print_and_exit(
            "Sending Provisioning Packet isn't successful!", ExitCodes.SENDING_FAILED
        )

    try:
        validation_run_success = com.provisioning_success_queue.get(
            timeout=com.DRY_RUN_RECEIVE_TIMEOUT_S
        )
    except queue.Empty:
        error_print_and_exit(
            "Provisioning validation run return code not received in the given timeout!",
            ExitCodes.RECEPTION_TIMEOUT,
        )

    if validation_run_success is False:
        error_print_and_exit(
            "Provisioning validation run was not successful!",
            ExitCodes.INVALID_PARAMETERS,
        )

    logging.info("Applying parameters to the NIC")

    if send_factory_mode_message(com, bytes(), MessageType.PROVISIONING_REBOOT_REQUEST) is False:
        error_print_and_exit(
            "Sending Device Reboot Request not successful!", ExitCodes.SENDING_FAILED
        )


def perform_parameters_reading(com: Communication):
    logging.info("Sending request to read NIC Parameters")
    if send_factory_mode_message(com, bytes(), MessageType.PROVISIONING_READ_REQUEST) is False:
        error_print_and_exit(
            "Sending Read Parameters Request not successful!", ExitCodes.SENDING_FAILED
        )

    try:
        nic_parameters_data = com.read_parameters_queue.get(
            timeout=com.READ_PARAMETERS_TIMEOUT_S
        )
    except queue.Empty:
        error_print_and_exit(
            "Read Parameters response was not received in the given timeout!",
            ExitCodes.RECEPTION_TIMEOUT,
        )

    nic_parameters_data = wirepas_provisioning.decode_prov_dict(nic_parameters_data)

    wirepas_provisioning.print_provisioning_summary(nic_parameters_data)

    prov_sucess = wirepas_provisioning.get_provisioning_status(nic_parameters_data)

    if prov_sucess is True:
        success_print("NIC is successfully provisioned!")
    else:
        error_print("Missing parameters in the device!")


def exit_factory_mode(com: Communication):
    logging.info("Sending request to exit factory mode")
    if send_factory_mode_message(com, bytes(), MessageType.EXIT_FACTORY_MODE) is False:
        error_print_and_exit(
            "Sending Exit Factory Mode Packet isn't successful!",
            ExitCodes.SENDING_FAILED,
        )

def serial_initialization(serial_port: str, com: Communication, baudrate: int):
    # Stop existing rx thread if running
    if com.rx_thread is not None and com.rx_thread.is_alive():
        logging.debug("Stopping existing rx thread")
        com.rx_thread_stop.set()
        com.rx_thread.join(timeout=PROVISIONING_STOP_RX_WAIT_S)  # Wait for thread to stop
        if com.rx_thread.is_alive():
            logging.warning("rx thread did not stop gracefully")
    
    # Close existing serial connection if open
    if hasattr(com.ser, 'is_open') and com.ser.is_open:
        com.ser.close()
    
    com.SERIAL_BAUDRATE = baudrate
    
    logging.info(
        "Connecting to " + serial_port + " at " + str(com.SERIAL_BAUDRATE) + " bauds"
    )
    
    # Reset the stop event for the new thread
    com.rx_thread_stop.clear()
    
    try:
        com.ser = serial.Serial(serial_port, com.SERIAL_BAUDRATE, timeout=1)
    except serial.SerialException as e:
        if "could not open port" in str(e).lower() or "no such file or directory" in str(e).lower():
            error_print_and_exit(
                f"Serial port '{serial_port}' is not available or does not exist. "
                f"Please check the port name and ensure the device is connected.\n"
                f"Error details: {str(e)}", 
                ExitCodes.SERIAL_ERROR
            )
        elif "permission denied" in str(e).lower():
            error_print_and_exit(
                f"Permission denied accessing serial port '{serial_port}'. "
                f"Please check user permissions or try running with sudo.\n"
                f"Error details: {str(e)}", 
                ExitCodes.SERIAL_ERROR
            )
        else:
            error_print_and_exit(
                f"Failed to open serial port '{serial_port}': {str(e)}", 
                ExitCodes.SERIAL_ERROR
            )
    except Exception as e:
        error_print_and_exit(
            f"Unexpected error opening serial port '{serial_port}': {str(e)}", 
            ExitCodes.SERIAL_ERROR
        )

    com.rx_thread = Thread(
        target=rx_callback,
        daemon=True,
        args=(com,),
    )
    com.rx_thread.start()

def switch_baudrate_if_needed(com: Communication, serial_port: str, new_baudrate: int):
    """Switch serial baudrate if different from current"""
    if new_baudrate != com.SERIAL_BAUDRATE:
        logging.info(f"Switching baudrate from {com.SERIAL_BAUDRATE} to {new_baudrate}")
        
        # Reinitialize with new baudrate (this handles thread management)
        serial_initialization(serial_port, com, new_baudrate)
        
        # Small delay to ensure clean initialization
        sleep(0.2)
        
        return True
    return False

def provision_nic_parameters(args: argparse):
    global nic_com
    logging.info("Starting NIC Provisioning")

    if getattr(sys, 'frozen', False):
            python_exe = os.path.join(os.path.dirname(sys.executable), "python.exe")
    else:
        python_exe = sys.executable

    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config_edit.py")
    cmd = [
        python_exe,
        script_path
    ]
    result = subprocess.run(
        cmd, capture_output=True, text=True, check=True,
        cwd=os.path.dirname(script_path),
        creationflags=subprocess.CREATE_NO_WINDOW)
    output = result.stdout
    error = result.stderr
    lines = output.strip().splitlines()

    for line in lines:
        if line.startswith("current_gateway:"):
            gateway_id_value = line.split(":", 1)[1].strip()
        elif line.startswith("current_sink:"):
            sink_address_value = int(line.split(":", 1)[1].strip())

    # Get all argument attributes except serial_port and baudrate (which are always set)
    provisioning_params = {k: v for k, v in vars(args).items() 
                          if k not in ['serial_port', 'baudrate']}
    
    # Check if all provisioning parameters are None
    if all(value is None for value in provisioning_params.values()):
        logging.error("No parameters specified for provisioning! All parameters are NULL!")
        logging.error("At least one parameter must be specified.")
        sys.exit(ExitCodes.MISSING_PARAMETERS.value)


    # Create WirepasProvisioning object with all parameters from args
    wp_prov = WirepasProvisioning(
        encryption_key=args.encryption_key,
        authentication_key=args.authentication_key,
        network_address=args.network_address,
        network_channel=args.network_channel,
        node_address=args.node_address,
        node_role=args.node_role,
        gw_key_enc_key=args.gw_key_enc_key,
        mtr_auth_key=args.mtr_auth_key,
        mtr_enc_key=args.mtr_enc_key,
        mtr_mr_secret=args.mtr_mr_secret,
        mtr_us_secret=args.mtr_us_secret,
        mtr_fu_secret=args.mtr_fu_secret,
        mtr_baud_rate=args.mtr_baud_rate,
        mtr_dlms_mode=args.mtr_dlms_mode,
        gateway_id=gateway_id_value,
        sink_address=sink_address_value,
        sim1_apn=args.sim1_apn,
        sim1_username=args.sim1_username,
        sim1_password=args.sim1_password,
        sim1_pdp_type=args.sim1_pdp_type,
        sim1_pin=args.sim1_pin,
        sim1_puk=args.sim1_puk,
        mqtt_hostname=args.mqtt_hostname,
        mqtt_port=args.mqtt_port,
        mqtt_username=args.mqtt_username,
        mqtt_password=args.mqtt_password,
        mqtt_unsecure=args.mqtt_unsecure,
        cellular_info_diag_intvl=args.cellular_info_diag_interval,
        network_info_diag_intvl=args.network_info_diag_interval,
        gateway_info_diag_intvl=args.gateway_info_diag_interval,
        ntp_addr=args.ntp_addr,
        tz_offset_min=args.tz_offset_min,
        keepalive_intvl_s=args.keepalive_interval,
        reset_hour=args.reset_hour,
        reset_minute=args.reset_minute,
    )

    # Check if at least one parameter is provided
    if not any(value is not None for value in vars(wp_prov).values()):
        logging.error("No parameters specified for provisioning! All parameters are NULL!")
        logging.error("At least one parameter must be specified.")
        sys.exit(ExitCodes.MISSING_PARAMETERS.value)

    wait_for_challenge_response_with_reset_loop(nic_com)
    perform_parameters_provisioning(nic_com, wp_prov)

    # Waiting for NIC to reboot before asking the parameters
    logging.info("Waiting for NIC to reboot...")

    # Check if mtr_baud_rate was provisioned and switch baudrate if needed
    if args.mtr_baud_rate is not None:
        switch_baudrate_if_needed(nic_com, args.serial_port, args.mtr_baud_rate)

    wait_for_challenge_response_with_reset_loop(nic_com)
    perform_parameters_reading(nic_com)

    exit_factory_mode(nic_com)

    sys.exit(ExitCodes.SUCCESS.value)

def read_nic_parameters(args: argparse):
    global nic_com
    wait_for_challenge_response_with_reset_loop(nic_com)
    perform_parameters_reading(nic_com)
    
    exit_factory_mode(nic_com)

    sys.exit(ExitCodes.SUCCESS.value)

if __name__ == "__main__":
    error_print_and_exit(
        "Unavailable. Please use 'provision_nic_parameters.py' or 'read_nic_parameters.py'",
        ExitCodes.CALL_TO_MAIN,
    )
