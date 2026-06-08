import os
import sys
import ctypes
import signal
import time
import re


base_dir = os.path.dirname(os.path.abspath(sys.argv[0]))

def check_firmware_log(output):
    """Extract verification results from firmware flash output"""
    pattern = r"#(\d+):\s+\.\.\s+(OK|failed)"
    matches = re.findall(pattern, output)
    ret_dict = {f"#{num}": status for num, status in matches}
    l = ['#1','#2','#3','#4','#5','#6','#7','#8']
    for num in l:
        if num not in ret_dict.keys():
            ret_dict[num] = 'failed'
    return ret_dict

def run_firmware_flash(flash_firmware=None, config_path='firmware_flash_files\\img_lastused_gparm.cfg'):
    """
    This script is used to flash the firmware on the device using the GangProARM-FPAsel.dll library. It performs the following steps:
    1. Loads the library and initializes the device.
    2. Reads the firmware file path from a configuration file.
    3. Configures the device using a configuration file.
    4. Programs the device with the firmware.
    5. Resets the target device and checks for successful programming.
    """
    result_dict = {'#1': 'failed', '#2': 'failed', '#3': 'failed', '#4': 'failed', '#5': 'failed', '#6': 'failed', '#7': 'failed', '#8': 'failed', "done": "failed"}

    if (sys.platform == "win32"):
        libname = os.path.join(base_dir, "firmware_flash_files", "GangProARM-FPAsel.dll")
        libname = "./firmware_flash_files/GangProARM-FPAsel.dll"
    else:
        # libname = "libmultigparm.so"
        libname = os.path.join(base_dir, "libmultigparm.so")
    config_file_path = bytes(f'firmware_flash_files\\{config_path}', 'utf-8')
        
    # config_file_path = bytes(config_path, 'utf-8')
    init_file = bytes('firmware_flash_files\\FPAs-setup.ini', 'utf-8')

    if flash_firmware:
        firmware_path = os.path.join(base_dir, "firmware_flash_files", flash_firmware)
        code_file_path = bytes(firmware_path, "utf-8")
    else:
        print("Error: Flash_firmware not found in Firmware_files.txt")
        sys.exit(1)

    print(f"Using library: {libname}")
    print(f"Using config file path:", os.path.join(base_dir, config_path))
    print(f"Using firmware file path:", firmware_path)

    if not os.path.exists(libname):
        raise Exception(f"DLL not found: {libname}")
    
    if not os.path.exists(firmware_path):
        raise Exception(f"Firmware not found: {firmware_path}")

    #Load library
    lib = ctypes.cdll.LoadLibrary(libname)

    # Get number of connected adapters
    instances = lib.F_OpenInstancesAndFPAs(init_file)
    print("Connected adapters: {}".format(instances))

    # Init all adapters
    result = lib.F_Set_FPA_index(0)
    print("F_Set_FPA_index(0): {}".format(result))

    result = lib.F_Initialization()
    print("F_Initialization: {}".format(result))

    # Get adapters serial numbers
    serials = []
    for instance in range(1, instances+1):
        serials.append(lib.F_Get_FPA_SN(instance))
    print(serials)

    result = lib.F_Reset_Target()
    print("F_Reset_Target: {}".format(result))


    result = lib.F_ConfigFileLoad(config_file_path)
    print("F_ConfigFileLoad: {}".format(result))
    result = lib.F_ReadCodeFile(code_file_path)
    print("F_ReadCodeFile: {}".format(result))

    # Select one adapter
    result = lib.F_Set_FPA_index(1)
    print("F_Set_FPA_index(1): {}".format(result))


    # After F_Clear_Locked_Device
    result = lib.F_Clear_Locked_Device(1)
    print("F_Clear_Locked_Device: {}".format(result))

    # 🔧 Add delay before access
    time.sleep(1.0)

    # Verify Access
    result = lib.F_Verify_Access_to_MCU()
    print("F_Verify_Access_to_MCU: {}".format(result))

    # 🔧 Add delay before AutoProgram
    time.sleep(1.0)

    # Auto Program
    result = lib.F_AutoProgram(0)
    print("F_AutoProgram: {}".format(result))


    result = lib.F_Reset_Target()
    print("F_Reset_Target: {}".format(result))

    # Print Auto Program text output (same as GUI)
    # max length REPORT_MESSAGE_MAX_SIZE 2000
    report_s   = ctypes.create_string_buffer(4000)
    lib.F_ReportMessage(report_s)
    s = report_s.value.decode()


    print(s)

    if "D O N E" not in s:
        result_dict = {'#1': 'failed', '#2': 'failed', '#3': 'failed', '#4': 'failed', '#5': 'failed', '#6': 'failed', '#7': 'failed', '#8': 'failed', 'done': 'failed'}
    else:
        result_dict = check_firmware_log(s)
        result_dict["done"] = "passed"
    # Close library instances to avoid cleanup delay
    lib.F_CloseInstances()

    # Force unload the DLL
    del lib
    return result_dict