import os
import sys
import ctypes
import signal
import time
import json

if (sys.platform == "win32"):
   libname = "./GangProARM-FPAsel.dll"
else:
   libname = "libmultigparm.so"

if len(sys.argv) > 1:
    config_file_path = bytes(sys.argv[1], 'utf-8')
else:
    # Fallback if no argument is passed
    with open("firmwareflash_config.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    code_file_path = data.get('codefile', '')
    config_file_path = bytes(f'ConfigFiles\\{code_file_path}', 'utf-8')

init_file = bytes('FPAs-setup.ini', 'utf-8')

# Read firmware file to get the Flash_firmware
firmware_file_path = "CodeFiles\\Firmware_files.txt"
flash_firmware = None

try:
    with open(firmware_file_path, 'r') as f:
        for line in f:
            if line.startswith("Flash_firmware="):
                flash_firmware = line.split("=")[1].strip()
                print(flash_firmware)
                break  # Stop reading after finding the flash firmware
except FileNotFoundError:
    print(f"Error: {firmware_file_path} not found.")
    sys.exit(1)

if flash_firmware:
    code_file_path = bytes(f"CodeFiles\\{flash_firmware}", 'utf-8')
else:
    print("Error: Flash_firmware not found in Firmware_files.txt")
    sys.exit(1)

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
# print("F_ReadCodeFile: {}".format(result))

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


# Close library instances to avoid cleanup delay
lib.F_CloseInstances()

# Force unload the DLL
del lib
