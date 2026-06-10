import os
import sys
import ctypes
import time
import json
import re
import logging

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


def run_firmware_flash(bootloader_file_name = None, main_firmware_name = None, config_path='firmware_flash_files\\5_6_3Ph_GangConfig.cfg'):
    """
    This script is used to flash the firmware on the device using the GangProARM-FPAsel.dll library. It performs the following steps:
    1. Loads the library and initializes the device.
    2. Reads the firmware file path from a configuration file.
    3. Configures the device using a configuration file.
    4. Programs the device with the firmware.
    5. Resets the target device and checks for successful programming.
    """
    try:
        s = ""
        result_dict = {'#1': 'failed', '#2': 'failed', '#3': 'failed', '#4': 'failed', '#5': 'failed', '#6': 'failed', '#7': 'failed', '#8': 'failed', "done": "failed"}

        if sys.platform == "win32":
            libname = os.path.join(base_dir, "firmware_flash_files", "GangProARM-FPAsel.dll")
            libname = "./firmware_flash_files/GangProARM-FPAsel.dll"
        else:
            libname = "libmultigparm.so"
            libname = os.path.join(base_dir, "firmware_flash_files", "libmultigparm.so")


        code_file_path = config_path

        # config_file_path = bytes(f'{config_path}', 'utf-8')
        config_file_path = bytes(config_path, 'utf-8')
        init_file = bytes('firmware_flash_files\\FPAs-setup.ini', 'utf-8')

        # Read bootloader and firmware file names
        bootloader_file = bootloader_file_name
        main_firmware = main_firmware_name

        if not bootloader_file or not main_firmware:
            print("Bootloader or Main firmware not found in config file")
            logging.info("Bootloader or Main firmware not found in config file")
            sys.exit(1)

        bootloader_path = os.path.join("firmware_flash_files", bootloader_file_name)
        main_firmware_path = os.path.join( "firmware_flash_files", main_firmware_name)
        merged_path = os.path.join("firmware_flash_files", "merged_firmware.bin")

        # Memory offset info from PDF
        bootloader_offset = 0x0000
        main_fw_offset = 0x2800
        full_flash_size = 0x40000  # 256 KB

        # Merge .bin files into correct memory locations
        def merge_bin_to_memory_layout():
            flash_image = bytearray([0xFF] * full_flash_size)

            with open(bootloader_path, 'rb') as bf:
                boot_data = bf.read()
                flash_image[bootloader_offset:bootloader_offset+len(boot_data)] = boot_data

            with open(main_firmware_path, 'rb') as mf:
                main_data = mf.read()
                flash_image[main_fw_offset:main_fw_offset+len(main_data)] = main_data

            with open(merged_path, 'wb') as out:
                out.write(flash_image)

            print(f"Created merged firmware with bootloader at 0x{bootloader_offset:X}, main firmware at 0x{main_fw_offset:X}")
            logging.info(f"Created merged firmware with bootloader at 0x{bootloader_offset:X}, main firmware at 0x{main_fw_offset:X}")

        merge_bin_to_memory_layout()
        print("1")
        # Begin flashing process
        lib = ctypes.cdll.LoadLibrary(libname)
        print("2")
        instances = lib.F_OpenInstancesAndFPAs(init_file)
        print(f"Connected adapters: {instances}")
        logging.info(f"Connected adapters: {instances}")

        lib.F_Set_FPA_index(0)
        lib.F_Initialization()

        serials = [lib.F_Get_FPA_SN(i) for i in range(1, instances + 1)]
        print(f"Adapter Serial Numbers: {serials}")
        logging.info(f"Adapter Serial Numbers: {serials}")

        lib.F_Reset_Target()
        lib.F_ConfigFileLoad(config_file_path)
  

        code_file_path = bytes(merged_path, 'utf-8')
        lib.F_ReadCodeFile(code_file_path)

        lib.F_Set_FPA_index(1)
        lib.F_Clear_Locked_Device(1)
        time.sleep(1.0)

        lib.F_Verify_Access_to_MCU()
        time.sleep(1.0)

        result = lib.F_AutoProgram(0)
        print(f"F_AutoProgram: {result}")
        logging.info(f"F_AutoProgram: {result}")

        lib.F_Reset_Target()

        report_s = ctypes.create_string_buffer(4000)
        lib.F_ReportMessage(report_s)
        s = report_s.value.decode()

        print(s)
        logging.info(s)

        if "D O N E" not in s:
            result_dict = {'#1': 'failed', '#2': 'failed', '#3': 'failed', '#4': 'failed', '#5': 'failed', '#6': 'failed', '#7': 'failed', '#8': 'failed', 'done': 'failed'}
        else:
            result_dict = check_firmware_log(s)
            result_dict["done"] = "passed"

        lib.F_CloseInstances()
        del lib
        logging.info(f"Main Firmware status: {result_dict}")
        return result_dict
    except Exception as e:
        print("error: ", e)

