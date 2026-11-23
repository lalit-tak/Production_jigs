import logging
import os
import sys
import ctypes
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

def run_firmware_flash(flash_firmware=None, bootloader_firmware = None, config_path='img_lastused_gparm.cfg', fpa_index=1):
    """
    This script is used to flash the firmware on the device using the GangProARM-FPAsel.dll library. It performs the following steps:
    1. Loads the library and initializes the device.
    2. Reads the firmware file path from a configuration file.
    3. Configures the device using a configuration file.
    4. Programs the device with the firmware.
    5. Resets the target device and checks for successful programming.
    """
    result_dict = {'#1': 'failed', '#2': 'failed', '#3': 'failed', '#4': 'failed', '#5': 'failed', '#6': 'failed', '#7': 'failed', '#8': 'failed', "done": "failed"}
    try:
        if (sys.platform == "win32"):
            # Absolute, so flashing does not depend on the working directory.
            libname = os.path.join(base_dir, "firmware_flash_files", "GangProARM-FPAsel.dll")
        else:
            libname = os.path.join(base_dir, "libmultigparm.so")
        # config_file_path = bytes(f'firmware_flash_files\\{config_path}', 'utf-8')
        config_file_path = bytes(os.path.join(base_dir, "firmware_flash_files",config_path),'utf-8')
            
        # init_file = bytes('firmware_flash_files\\FPAs-setup.ini', 'utf-8')
        init_file = bytes(os.path.join(base_dir, "firmware_flash_files","FPAs-setup.ini"),'utf-8')
        

        if flash_firmware:
            firmware_path = os.path.join(base_dir, "firmware_flash_files", flash_firmware)
            bootloader_file_path = os.path.join(base_dir, "firmware_flash_files", bootloader_firmware)
            merged_path = os.path.join(base_dir, "firmware_flash_files", "merged_test_firmware.bin")
            
        else:
            logging.error("Error: no firmware file given to run_firmware_flash()")
            return result_dict

        logging.debug(f"Using library: {libname}")
        logging.debug(f"Using config file path: {config_file_path}")
        logging.debug(f"Using firmware file path: {firmware_path}")

        if not os.path.exists(libname):
            raise Exception(f"DLL not found: {libname}")
        
        if not os.path.exists(firmware_path):
            raise Exception(f"Firmware not found: {firmware_path}")


        # Memory offset info from PDF
        bootloader_offset = 0x0000
        main_fw_offset = 0x2800
        full_flash_size = 0x40000  # 256 KB

        def merge_bin_to_memory_layout():
            flash_image = bytearray([0xFF] * full_flash_size)

            with open(bootloader_file_path, 'rb') as bf:
                boot_data = bf.read()
                flash_image[bootloader_offset:bootloader_offset+len(boot_data)] = boot_data

            with open(firmware_path, 'rb') as mf:
                main_data = mf.read()
                flash_image[main_fw_offset:main_fw_offset+len(main_data)] = main_data

            with open(merged_path, 'wb') as out:
                out.write(flash_image)

            logging.debug(f"Created merged firmware with bootloader at 0x{bootloader_offset:X}, main firmware at 0x{main_fw_offset:X}")

        merge_bin_to_memory_layout()

        #Load library
        lib = ctypes.cdll.LoadLibrary(libname)

        # Get number of connected adapters
        instances = lib.F_OpenInstancesAndFPAs(init_file)
        logging.debug(f"Connected adapters: {instances}")

        # Init all adapters
        result = lib.F_Set_FPA_index(0)
        logging.debug(f"F_Set_FPA_index(0): {result}")

        result = lib.F_Initialization()
        logging.debug(f"F_Initialization: {result}")

        # Get adapters serial numbers
        serials = []
        for instance in range(1, instances+1):
            serials.append(lib.F_Get_FPA_SN(instance))
        logging.debug(f"Adapter serial numbers: {serials}")

        result = lib.F_Reset_Target()
        logging.debug(f"F_Reset_Target: {result}")


        result = lib.F_ConfigFileLoad(config_file_path)
        logging.debug(f"F_ConfigFileLoad: {result}")

        code_file_path = bytes(merged_path, "utf-8")
        result = lib.F_ReadCodeFile(code_file_path)
        logging.debug(f"F_ReadCodeFile: {result}")

        # Select the adapter wired to this station
        result = lib.F_Set_FPA_index(fpa_index)
        logging.debug(f"F_Set_FPA_index({fpa_index}): {result}")


        # After F_Clear_Locked_Device
        result = lib.F_Clear_Locked_Device(fpa_index)
        logging.debug(f"F_Clear_Locked_Device({fpa_index}): {result}")

        # 🔧 Add delay before access
        time.sleep(1.0)

        # Verify Access
        result = lib.F_Verify_Access_to_MCU()
        logging.debug(f"F_Verify_Access_to_MCU: {result}")

        # 🔧 Add delay before AutoProgram
        time.sleep(1.0)

        # Auto Program
        result = lib.F_AutoProgram(0)
        logging.debug(f"F_AutoProgram: {result}")

        result = lib.F_Reset_Target()
        logging.debug(f"F_Reset_Target: {result}")

        # Print Auto Program text output (same as GUI)
        # max length REPORT_MESSAGE_MAX_SIZE 2000
        report_s   = ctypes.create_string_buffer(4000)
        lib.F_ReportMessage(report_s)
        s = report_s.value.decode()


        logging.debug(f"Auto Program output: {s}")

        if "D O N E" not in s:
            result_dict = {'#1': 'failed', '#2': 'failed', '#3': 'failed', '#4': 'failed', '#5': 'failed', '#6': 'failed', '#7': 'failed', '#8': 'failed', "done": "failed"}
        else:
            result_dict = check_firmware_log(s)
            result_dict["done"] = "passed"
        # Close library instances to avoid cleanup delay
        lib.F_CloseInstances()

        # Force unload the DLL
        del lib
        logging.debug(result_dict)
        return result_dict
    except Exception as e:
        logging.error(f"Error during firmware flash: {e}")
        return result_dict


# run_firmware_flash("17404_T0005.bin", "gp_1p_bootloader_PCB78_V001_Generic_4.8_BM_2.0_KM35_flash.bin", "2_4_better_GangConfig.cfg")