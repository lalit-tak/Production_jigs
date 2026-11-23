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

def run_firmware_flash(flash_firmware=None, bootloader_firmware_1=None, bootloader_firmware_2=None,
                       config_path='img_lastused_gparm.cfg', fpa_index=1):
    """
    FACTORY's "Main FW Download" - like FirmwareFlash.run_firmware_flash
    (EMS's "Test FW Download", one bootloader), but merges TWO bootloaders
    plus the main firmware into one flash image before programming it
    through the same GangProARM-FPAsel.dll adapter:
    1. Loads the library and initializes the device.
    2. Reads the firmware file path from a configuration file.
    3. Configures the device using a configuration file.
    4. Programs the device with the firmware.
    5. Resets the target device and checks for successful programming.
    """
    # return {'#2': 'OK', '#4': 'OK', 'done': 'passed'}
    result_dict = {'#1': 'failed', '#2': 'failed', '#3': 'failed', '#4': 'failed', '#5': 'failed', '#6': 'failed', '#7': 'failed', '#8': 'failed', "done": "failed"}
    try:
        if (sys.platform == "win32"):
            # Absolute, so flashing does not depend on the working directory.
            libname = os.path.join(base_dir, "firmware_flash_files", "GangProARM-FPAsel.dll")
        else:
            libname = os.path.join(base_dir, "libmultigparm.so")
        # Absolute, same reason as libname above - the DLL resolves a
        # relative path against the process's current working directory at
        # call time, not against this script's location, which does not
        # reliably match when launched via main.py instead of run standalone.
        config_file_path = bytes(os.path.join(base_dir, "firmware_flash_files", config_path), 'utf-8')

        init_file = bytes(os.path.join(base_dir, "firmware_flash_files", "FPAs-setup.ini"), 'utf-8')

        if flash_firmware and bootloader_firmware_1 and bootloader_firmware_2:
            firmware_path = os.path.join(base_dir, "firmware_flash_files", flash_firmware)
            bootloader_path_1 = os.path.join(base_dir, "firmware_flash_files", bootloader_firmware_1)
            bootloader_path_2 = os.path.join(base_dir, "firmware_flash_files", bootloader_firmware_2)
            merged_path = os.path.join(base_dir, "firmware_flash_files", "merged_main_firmware.bin")
        else:
            logging.error("Error: flash_firmware, bootloader_firmware_1 and bootloader_firmware_2 are all required for the FACTORY flash")
            return result_dict

        logging.debug(f"Using library: {libname}")
        logging.debug(f"Using config file path: {config_file_path.decode()}")
        logging.debug(f"Using init file path: {init_file.decode()}")
        logging.debug(f"Using firmware file path: {firmware_path}")
        logging.debug(f"Using bootloader #1 path: {bootloader_path_1}")
        logging.debug(f"Using bootloader #2 path: {bootloader_path_2}")

        if not os.path.exists(libname):
            raise Exception(f"DLL not found: {libname}")

        if not os.path.exists(firmware_path):
            raise Exception(f"Firmware not found: {firmware_path}")

        if not os.path.exists(bootloader_path_1):
            raise Exception(f"Bootloader #1 not found: {bootloader_path_1}")

        if not os.path.exists(bootloader_path_2):
            raise Exception(f"Bootloader #2 not found: {bootloader_path_2}")


        # Memory offset info from PDF
        bootloader_offset1 = 0x0000
        bootloader_offset2 = 0x4000
        main_fw_offset = 0x8000
        full_flash_size = 0x80000  # 512 KB

        def merge_bin_to_memory_layout():
            flash_image = bytearray([0xFF] * full_flash_size)

            with open(bootloader_path_1, 'rb') as bf1:
                boot_data_1 = bf1.read()
                flash_image[bootloader_offset1:bootloader_offset1+len(boot_data_1)] = boot_data_1

            with open(bootloader_path_2, 'rb') as bf2:
                boot_data_2 = bf2.read()
                flash_image[bootloader_offset2:bootloader_offset2+len(boot_data_2)] = boot_data_2

            with open(firmware_path, 'rb') as mf:
                main_data = mf.read()
                flash_image[main_fw_offset:main_fw_offset+len(main_data)] = main_data

            with open(merged_path, 'wb') as out:
                out.write(flash_image)

            logging.debug(
                f"Created merged firmware with bootloader #1 at 0x{bootloader_offset1:X}, "
                f"bootloader #2 at 0x{bootloader_offset2:X}, main firmware at 0x{main_fw_offset:X}"
            )

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
            result_dict = {'#1': 'OK', '#2': 'OK', 'done': 'passed'}
        else:
            result_dict = check_firmware_log(s)
            result_dict["done"] = "passed"
        # Close library instances to avoid cleanup delay
        lib.F_CloseInstances()

        # Force unload the DLL
        del lib
        print(result_dict)
        return result_dict
    except Exception as e:
        logging.error(f"Error during firmware flash: {e}")
        return result_dict
