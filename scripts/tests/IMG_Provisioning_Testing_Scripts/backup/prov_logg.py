import logging
import sys
import os
import re
import subprocess
from datetime import datetime
import argparse
import json

def update_gateway_id():
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
    return gateway_id_value

def RF_test_perform(serial_port, baudrate, test_router_address, network_address, network_channel, encryption_key, authentication_key):

    try:
        if getattr(sys, 'frozen', False):
            python_exe = os.path.join(os.path.dirname(sys.executable), "python.exe")
        else:
            python_exe = sys.executable

        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "testing.py")
        cmd = [
            python_exe,
            script_path,
            "--serial_port", serial_port,
            "--baudrate", baudrate,
            "--encryption_key", encryption_key,
            "--authentication_key", authentication_key,
            "--network_address", network_address,
            "--network_channel", network_channel,
            "--test_router_address", test_router_address
        ]
        logging.debug(f"RF Test command: {cmd}")

        try:
            print("in subprocess call")
            result = subprocess.run(
                cmd, capture_output=True, text=True, check=True,
                cwd=os.path.dirname(script_path),
                creationflags=subprocess.CREATE_NO_WINDOW,
                encoding="utf-8"
            )
            error = result.stderr
            output = result.stdout
        except subprocess.CalledProcessError as e:
            output = e.stderr
        print(output)

        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        clean_output = ansi_escape.sub('', output)
        
        gateway_number = update_gateway_id()
        today = datetime.now().strftime("%d_%m_%Y")


        Action = f"{output}"
        logging.info(f"Results - Gatewway Number: {gateway_number}, output status : {clean_output}", encoding="utf-8")

        # Save result to file
        result_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Detailed Test Result")
        os.makedirs(result_folder, exist_ok=True)
        result_file_name = f"{today}_{gateway_number}.txt"
        result_file_path = os.path.join(result_folder, result_file_name)

        mode = 'a' if os.path.exists(result_file_path) else 'w'
        with open(result_file_path, mode , encoding="utf-8") as result_file:
            if mode == 'a':
                result_file.write("\n--- Updated at {} ---\n".format(datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            result_file.write(clean_output)

        return gateway_number

    except Exception as e:
        logging.error(f"Unexpected error during RF Test for Serial Number {gateway_number}: {e}")
        return gateway_number

if __name__ == "__main__":
    parser = argparse.ArgumentParser(fromfile_prefix_chars="@")
       # Serial parameters
    parser.add_argument(
        "--serial_port",
        type=str,
        help="Serial port used to communicate with the gateway.",
        required=True,
    )
    args = parser.parse_args()

    with open("Load_channel_data.json", "r", encoding="utf-8") as f:
        json_data = json.load(f)
    print(args.serial_port, json_data['BAUDRATE'], json_data['TEST_ROUTER_ADDRESS'], json_data['NETWORK_ADDRESS'], json_data['NETWORK_CHANNEL'], json_data['ENCRYPTION_KEY'], json_data['AUTHENTICATION_KEY'])
    
    
    # RF_test_perform(args.serial_port, json_data['BAUDRATE'], json_data['TEST_ROUTER_ADDRESS'], json_data['NETWORK_ADDRESS'], json_data['NETWORK_CHANNEL'], json_data['ENCRYPTION_KEY'], json_data['AUTHENTICATION_KEY'])