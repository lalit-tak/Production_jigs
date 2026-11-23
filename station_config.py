"""
All jig wiring lives here: which COM port and DAQ line belongs to which
station, what counts as a pass, how long each test may take, and what result
to report when it overruns.

Nothing else in the tool hard-codes a port number, a channel index or a
timeout - change a value here and the UI, the worker and the Excel log follow.

>>> CONFIRM BEFORE PRODUCTION USE <<<
The COM ports, DAQ channel numbers and DO bit assignments below are the
wiring this tool assumes. They are placeholders derived from the test names,
not measured from the bench. Check every entry marked CONFIRM against the
actual harness before trusting a PASS.
"""


import base64
import json
import logging
import os
import sys

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# ---------------------------------------------------------------- stations --

# Meter COM port per station - the port the test protocol (memory, version,
# relay, NIC ... ) talks over. CONFIRM.
STATION_COM_PORTS = {
    1: "COM3",
    2: "COM4",
}

# Barcode-scanner COM port per station. Set to None to skip scanning and use
# whatever the operator typed into the Serial Number box. CONFIRM.
STATION_SCANNER_PORTS = {
    1: None,
    2: None,
}

# RTC/PPM frequency-calibrator COM port per station (the external counter
# scripts/rtc_calibration.py's read_frames() reads ticks/drift frames from -
# NOT the meter's own optical port). None until serial_config.enc's
# CALIBRATOR_COM<n> is loaded (see load_serial_config() below); a station
# with no calibrator configured fails "RTC Calibration/PPM Calibration" and
# "Verify RTC Calibration" with a clear message instead of guessing a port.
# CONFIRM.
STATION_CALIBRATOR_PORTS = {
    1: None,
    2: None,
}

# Advantech DAQ card. The bench is one card driving both stations, so both
# stations name the same device and differ by DO port / AI channel below.
# CONFIRM against Advantech Navigator ("USB-4716,BID#0").
STATION_DAQ_DEVICES = {
    1: "USB-4716,BID#0",
    2: "USB-4716,BID#0",
}

# Digital-output port used for each station's relay bank. CONFIRM.
STATION_DO_PORTS = {
    1: 0,
    2: 1,
}

# Digital-INPUT port the relay contacts' physical feedback lines are wired
# back into - one shared port read by both stations (same DAQ card as
# STATION_DO_PORTS above), used to physically confirm "Relay off test" /
# "Relay on test" (test_impl._run_relay_test) once the meter's own protocol
# status check has already passed. CONFIRM.
DI_PORT = 0

# Bit within DI_PORT that reads 1 when that station's relay is physically ON,
# 0 when OFF (the other bit of that station's pair, bit+1, is just the
# inverse/NC contact and is not read). Derived from bench data:
#   relay on (both):            Port 0 = 0xF5 -> DI0=1, DI2=1
#   st-2 off / st-1 on:         Port 0 = 0xF9 -> DI0=1, DI2=0
#   st-1 off / st-2 on:         Port 0 = 0xF6 -> DI0=0, DI2=1
#   relay off (both):           Port 0 = 0xFA -> DI0=0, DI2=0
# CONFIRM against the actual harness before trusting a PASS.
STATION_RELAY_DI_BIT = {
    1: 0,
    2: 2,
}

# First analog-input channel belonging to each station; the per-test channel
# numbers in VOLTAGE_TESTS are offsets from this. Per the confirmed DAQ AI
# map (ch0-5 = station 1, ch6-11 = station 2: TP2/VCC:6V, TP10/VCC:3V6,
# TP13/VCC:3V3, TP05/Mains Detect, TP15/Battery Control, VCC_UC/MCU VCC).
# power_enable (ch12/13) and efuse (ch14/15) sit outside this block - see
# VOLTAGE_TEST_ABSOLUTE_CHANNELS below.
STATION_AI_BASE_CHANNEL = {
    1: 0,
    2: 6,
}

# Per-station SOCKET number on the ONE shared gang-programmer adapter (used
# to grade each station's own "#N" slot in run_firmware_flash()'s report -
# shared_fw.grade_flash_report) - NOT the adapter instance itself. Only one
# physical adapter box serves both stations (confirmed: F_OpenInstancesAndFPAs
# reports "Connected adapters: 1"), so the adapter instance passed to
# F_Set_FPA_index()/F_Clear_Locked_Device() is always 1, regardless of these
# values - see shared_fw.SharedFwRunner._do_flash(). CONFIRM these socket
# numbers against which physical socket each station's meter is wired to.
STATION_FPA_INDEX = {
    1: 1,
    2: 2,
}

# Set True to let tests fall back to simulated PASS results when the DAQ
# driver or a COM port is not present (useful for UI work on a dev machine).
# Leave False on the bench so missing hardware is reported as a failure.
ALLOW_SIMULATION = False

# ----------------------------------------------------- serial_config.enc --

# Encrypted COM port config checked in next to this file (16-byte salt +
# Fernet-encrypted JSON: SCANNER_COM<n> = barcode scanner port, OPTICAL_COM<n>
# = the optical-probe port the protocol tests talk over). Overrides
# STATION_SCANNER_PORTS and STATION_COM_PORTS for stations 1-2 above when
# present and decryptable - load_serial_config() must be called once, after
# logging is configured, to apply it (see main.py). Falls back to the
# hardcoded dicts above, and leaves the tool usable, if the file is missing
# or fails to decrypt.
#
# sys.argv[0]-based, NOT __file__: under a PyInstaller --onefile build this
# module is imported from a temp extraction folder, so __file__ would point
# there instead of next to the built .exe - where serial_config.enc is
# actually checked in/edited per station (same reasoning as main.py's own
# BASE_DIR).
SERIAL_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "serial_config.enc")

_SERIAL_CONFIG_PASSWORD = b"Polaris@1234"
_SERIAL_CONFIG_ITERATIONS = 390000

# Defaults, overridden by Flash_Firmware / Gang_Programming_Code_File in
# serial_config.enc when load_serial_config() finds them.
FIRMWARE_FILE = "17404_T0005.bin"
BOOTLOADER_FILE = "gp_1p_bootloader_PCB78_V001_Generic_4.8_BM_2.0_KM35_flash.bin"
FIRMWARE_CONFIG = "img_lastused_gparm.cfg"
FIRMWARE_VERSION = "0.0.0.0"
DEFAULT_TIMEOUT = 20.0
LIVE_VERSION = 17404
TOOL_VERSION = 5

# EMS flashes the "Test FW" image, FACTORY flashes the "Main FW" image
# (test_plan.xlsx rows 12 and 18) - None until load_serial_config() finds
# Flash_Firmware_EMS / Flash_Firmware_FACTORY in serial_config.enc. Read
# through get_flash_firmware_file() below, never directly, so a station
# whose .enc hasn't been updated with these two keys yet just keeps flashing
# FIRMWARE_FILE for both modes exactly as before this setting existed.
FIRMWARE_FILE_EMS = None
FIRMWARE_FILE_FACTORY = None


def get_flash_firmware_file():
    """
    The firmware image run_fw_download/SharedFwRunner should flash for the
    current TEST_MODE: FIRMWARE_FILE_EMS under "EMS", FIRMWARE_FILE_FACTORY
    under "FACTORY" - falling back to the generic FIRMWARE_FILE when TEST_MODE
    is None (no Mode configured) or the mode-specific key isn't set in
    serial_config.enc.
    """
    if TEST_MODE == "EMS" and FIRMWARE_FILE_EMS:
        return FIRMWARE_FILE_EMS
    if TEST_MODE == "FACTORY" and FIRMWARE_FILE_FACTORY:
        return FIRMWARE_FILE_FACTORY
    return FIRMWARE_FILE

# EMS flashes ONE bootloader (FirmwareFlash.run_firmware_flash); FACTORY
# flashes TWO, each merged at its own memory offset
# (MainFirmwareFlash.run_firmware_flash - see that module for the offsets).
# None until load_serial_config() finds ONE "Boot_Loader_Firmware" key in
# serial_config.enc - a JSON list of file names (also accepts a single
# comma-separated string, for a hand-edited config), parsed by
# _parse_file_list() below. Whichever mode is active decides how many entries
# that list must have - exactly 1 for EMS, exactly 2 for FACTORY - and
# load_serial_config() logs an error and leaves the corresponding
# BOOTLOADER_FILES_* at its previous value (empty the first time) if the
# count doesn't match. Read through get_bootloader_files(), never directly,
# so a station whose .enc hasn't been updated with this key yet just keeps
# flashing the single generic BOOTLOADER_FILE for both modes exactly as
# before this setting existed.
BOOTLOADER_FILES_EMS = []
BOOTLOADER_FILES_FACTORY = []


def _parse_file_list(value):
    """["a.bin", "b.bin"] or "a.bin, b.bin" -> ["a.bin", "b.bin"]; "" or None -> []."""
    if not value:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    return [v.strip() for v in str(value).split(",") if v.strip()]


def get_bootloader_files():
    """
    The bootloader file name(s) to flash for the current TEST_MODE, in flash
    order: BOOTLOADER_FILES_EMS (1 file) under "EMS", BOOTLOADER_FILES_FACTORY
    (2 files) under "FACTORY" - falling back to [BOOTLOADER_FILE] (the
    generic single bootloader) when TEST_MODE is None or that mode's list
    isn't configured.
    """
    if TEST_MODE == "EMS" and BOOTLOADER_FILES_EMS:
        return list(BOOTLOADER_FILES_EMS)
    if TEST_MODE == "FACTORY" and BOOTLOADER_FILES_FACTORY:
        return list(BOOTLOADER_FILES_FACTORY)
    return [BOOTLOADER_FILE]

# key -> analog channel (offset from the station's base channel) and the
# accepted window in volts. CONFIRM every channel number; min/max are
# overridden by serial_config.enc's VOLTAGE_TESTS block when present (see
# load_serial_config() below) - the channel number always stays hardcoded.
VOLTAGE_TESTS = {
    "test_6v":              {"channel": 0, "min": 5.70, "max": 6.30},
    # "test_3_6v":            {"channel": 1, "min": 3.3, "max": 3.78},  # 3.6V test disabled
    "test_3_3v":            {"channel": 2, "min": 3.135, "max": 3.465},
    "mains_detection":      {"channel": 3, "min": 2.85, "max": 3.3},
    "battery_control":      {"channel": 4, "min": 3.135, "max": 3.465},
    "mcu_vcc":              {"channel": 5, "min": 3.135, "max": 3.465},
    # power_enable and efuse don't fit the shared base+offset pattern - they
    # sit outside the ch0-11 per-station block. "channel" here is unused -
    # see VOLTAGE_TEST_ABSOLUTE_CHANNELS below.
    "power_enable":         {"channel": None, "min": 3.135, "max": 3.465},
    "efuse":                {"channel": None, "min": 5.7, "max": 6.3},
    # main_battery_voltage has NO channel in the confirmed 16-channel AI map
    # (ch0-15 are fully accounted for by the other 8 functions x 2 stations)
    # - CONFIRM what this should actually read before trusting this test.
    "main_battery_voltage": {"channel": None, "min": 3.352, "max": 3.78},
}

# power_enable, efuse and main_battery_voltage don't fit the shared
# base-channel + offset pattern every other VOLTAGE_TESTS key uses -
# run_voltage_test uses this absolute per-station channel map directly for
# any key listed here, instead of ai_base_channel + offset.
#
# power_enable (ch12/13) and efuse (ch14/15) are confirmed from the DAQ AI
# map. main_battery_voltage is NOT in that map at all - ch3/ch10 below are
# UNCONFIRMED and collide with mains_detection (ch3, station 1) and
# battery_control (ch10, station 2). CONFIRM the real channel before
# trusting main_battery_voltage's result.
VOLTAGE_TEST_ABSOLUTE_CHANNELS = {
    "power_enable": {1: 12, 2: 13},
    "efuse": {1: 14, 2: 15},
    "main_battery_voltage": {1: 5, 2: 11},
}

# VOLTAGE_TESTS key -> snapshot group. Keys in the same group share ONE
# InstantAI read instead of one read each - test_6v .. mcu_vcc all run
# back-to-back right after mains_on, before FW Download, with nothing
# changing hardware state between them; efuse/power_enable are the same
# story right after Calibration LED (both firmware-driven rails, nothing
# changes hardware state between the two of them either). See
# shared_ai.SharedAiRunner and test_impl.run_voltage_test.
# Any key NOT listed here gets its own fresh InstantAI read, keyed by
# itself - just main_battery_voltage, which runs much later, after
# do_all_off.
SHARED_AI_GROUPS = {
    "test_6v":         "_pre_fw_rails",
    # "test_3_6v":       "_pre_fw_rails",  # 3.6V test disabled
    "test_3_3v":       "_pre_fw_rails",
    "mains_detection": "_pre_fw_rails",
    "battery_control": "_pre_fw_rails",
    "mcu_vcc":         "_pre_fw_rails",
    "efuse":           "_post_fw_rails",
    "power_enable":    "_post_fw_rails",
}

def _derive_key(password, salt):
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=_SERIAL_CONFIG_ITERATIONS,
    )
    return base64.urlsafe_b64encode(kdf.derive(password))

def _decrypt_serial_config(path):
    with open(path, "rb") as f:
        salt = f.read(16)
        encrypted_data = f.read()
    key = _derive_key(_SERIAL_CONFIG_PASSWORD, salt)
    decrypted = Fernet(key).decrypt(encrypted_data)
    return json.loads(decrypted.decode("utf-8"))


def encrypt_serial_config(config, path=SERIAL_CONFIG_PATH):
    """
    Writes `config` (a dict) to `path` in the same 16-byte-salt +
    Fernet-encrypted-JSON format _decrypt_serial_config() reads - a fresh
    random salt every call, same password/iterations as decryption. Not used
    by the running tool (main.py only ever decrypts); this is the tool for
    regenerating serial_config.enc after editing serial_config.json.
    """
    salt = os.urandom(16)
    key = _derive_key(_SERIAL_CONFIG_PASSWORD, salt)
    encrypted = Fernet(key).encrypt(json.dumps(config).encode("utf-8"))
    with open(path, "wb") as f:
        f.write(salt)
        f.write(encrypted)

def load_serial_config(path=SERIAL_CONFIG_PATH):
    """
    Decrypts serial_config.enc and overrides, for stations 1-2: the scanner
    and meter COM ports, the shared DAQ device, the gang-programmer adapter
    index, the firmware image/config file names, the default test timeout,
    the EMS/FACTORY test mode, and the required serial number length. Leaves every
    value as its hardcoded default above if the file is missing, fails to
    decrypt, or a key is absent, so the tool still starts and runs with the
    placeholders.
    """
    global FIRMWARE_FILE, FIRMWARE_FILE_EMS, FIRMWARE_FILE_FACTORY, BOOTLOADER_FILE, BOOTLOADER_FILES_EMS, BOOTLOADER_FILES_FACTORY, FIRMWARE_CONFIG, DEFAULT_TIMEOUT, FIRMWARE_VERSION, LIVE_VERSION, TOOL_VERSION, TEST_MODE, SERIAL_NUMBER_LENGTH

    if not os.path.exists(path):
        logging.warning(f"serial_config.enc not found at {path}; keeping hardcoded config")
        return

    try:
        config = _decrypt_serial_config(path)
    except (InvalidToken, ValueError, OSError, json.JSONDecodeError) as exc:
        logging.error(f"Could not decrypt {path}: {exc}; keeping hardcoded config")
        return

    for station in (1, 2):
        STATION_SCANNER_PORTS[station] = config.get(f"SCANNER_COM{station}") or None

        meter_port = config.get(f"OPTICAL_COM{station}")
        if meter_port:
            STATION_COM_PORTS[station] = meter_port

        calibrator_port = config.get(f"CALIBRATOR_COM{station}")
        if calibrator_port:
            STATION_CALIBRATOR_PORTS[station] = calibrator_port

        # One DAQ card drives every station on this bench - the config
        # carries a single DAC_COM value, applied to all of them.
        daq_device = config.get("DAC_COM")
        if daq_device:
            STATION_DAQ_DEVICES[station] = daq_device

        fpa_label = config.get("Gang_Programming_Station_Map", {}).get(f"Station{station}")
        if fpa_label:
            try:
                STATION_FPA_INDEX[station] = int(str(fpa_label).lstrip("#"))
            except ValueError:
                logging.error(
                    f"Station {station}: bad Gang_Programming_Station_Map entry "
                    f"{fpa_label!r}, keeping fpa_index {STATION_FPA_INDEX[station]}"
                )

    # Resolved before the bootloader-file block below, which needs to know
    # whether to expect 1 (EMS) or 2 (FACTORY) file names.
    mode = config.get("Mode")
    normalized_mode = str(mode).strip().upper() if mode else None
    if mode is not None and normalized_mode not in VALID_TEST_MODES:
        logging.warning(
            f"serial_config.enc: Mode {mode!r} is not one of {sorted(VALID_TEST_MODES)}; "
            f"running the full test sequence (no EMS/FACTORY filter)"
        )
    else:
        TEST_MODE = normalized_mode

    FIRMWARE_FILE = config.get("Flash_Firmware_Main", FIRMWARE_FILE)
    FIRMWARE_FILE_EMS = config.get("Flash_Firmware_Main", FIRMWARE_FILE)
    FIRMWARE_FILE_FACTORY = config.get("Flash_Firmware_Main", FIRMWARE_FILE)

    # ONE "Boot_Loader_Firmware" list in serial_config.enc, shared by both
    # modes - whoever edits the config puts 1 file name in it to run EMS, or
    # 2 to run FACTORY, matching whatever "Mode" is also set to. A count that
    # doesn't match the active mode is a config mistake: log it and leave
    # that mode's bootloader list exactly as it was (empty the first time),
    # so get_bootloader_files() falls back to the single generic
    # BOOTLOADER_FILE instead of flashing the wrong file count.
    bootloader_files = _parse_file_list(config.get("Boot_Loader_Firmware"))
    if bootloader_files:
        if TEST_MODE.lower() == "factory":
            if len(bootloader_files) == 2:
                BOOTLOADER_FILES_FACTORY = bootloader_files
            else:
                logging.error(
                    f"serial_config.enc: FACTORY mode needs exactly 2 file names in "
                    f"Boot_Loader_Firmware, got {len(bootloader_files)} ({bootloader_files!r}) - "
                    f"keeping previous FACTORY bootloader files {BOOTLOADER_FILES_FACTORY!r}"
                )
        else:
            # EMS, or no/invalid Mode configured - same single-bootloader
            # fallback as always ran before FACTORY mode existed.
            if len(bootloader_files) == 1:
                BOOTLOADER_FILES_EMS = bootloader_files
            else:
                logging.error(
                    f"serial_config.enc: EMS mode needs exactly 1 file name in "
                    f"Boot_Loader_Firmware, got {len(bootloader_files)} ({bootloader_files!r}) - "
                    f"keeping previous EMS bootloader files {BOOTLOADER_FILES_EMS!r}"
                )

    FIRMWARE_CONFIG = config.get("Gang_Programming_Code_File", FIRMWARE_CONFIG)
    DEFAULT_TIMEOUT = config.get("TEST_TIMEOUT", DEFAULT_TIMEOUT)
    FIRMWARE_VERSION = config.get("Firmware_version", FIRMWARE_VERSION)
    LIVE_VERSION = config.get("Live_version", LIVE_VERSION)
    TOOL_VERSION = config.get("Tool_version", TOOL_VERSION)

    length = config.get("Serial_Number_Length")
    if length is not None:
        try:
            length = int(length)
            if length <= 0:
                raise ValueError("must be positive")
        except (TypeError, ValueError):
            logging.warning(
                f"serial_config.enc: Serial_Number_Length {length!r} is not a positive integer; "
                f"serial numbers of any length are accepted"
            )
        else:
            SERIAL_NUMBER_LENGTH = length

    # Only overrides a VOLTAGE_TESTS key that already exists above - the
    # channel number stays whatever's hardcoded, just min/max move. A key in
    # config.VOLTAGE_TESTS with no matching entry here (no test/channel for
    # it yet) is logged and skipped rather than silently ignored.
    for key, limits in config.get("VOLTAGE_TESTS", {}).items():
        if key not in VOLTAGE_TESTS:
            logging.warning(f"serial_config.enc VOLTAGE_TESTS has unknown key '{key}' - no matching test/channel, skipped")
            continue
        VOLTAGE_TESTS[key]["min"] = limits["min"]
        VOLTAGE_TESTS[key]["max"] = limits["max"]

    logging.info(f"Loaded scanner ports from serial_config.enc: {STATION_SCANNER_PORTS}")
    logging.info(f"Loaded meter (optical) ports from serial_config.enc: {STATION_COM_PORTS}")
    logging.info(f"Loaded RTC calibrator ports from serial_config.enc: {STATION_CALIBRATOR_PORTS}")
    logging.info(f"Loaded DAQ devices from serial_config.enc: {STATION_DAQ_DEVICES}")
    logging.info(f"Loaded gang-programmer indices from serial_config.enc: {STATION_FPA_INDEX}")
    logging.info(f"Loaded firmware file from serial_config.enc: {FIRMWARE_FILE}")
    logging.info(f"Loaded EMS/FACTORY firmware files from serial_config.enc: EMS={FIRMWARE_FILE_EMS}, FACTORY={FIRMWARE_FILE_FACTORY}")
    logging.info(f"Loaded EMS/FACTORY bootloader files from serial_config.enc: EMS={BOOTLOADER_FILES_EMS}, FACTORY={BOOTLOADER_FILES_FACTORY}")
    logging.info(f"Generic fallback bootloader file (no mode / bad Boot_Loader_Firmware count): {BOOTLOADER_FILE}")
    logging.info(f"Loaded gang-programming config file from serial_config.enc: {FIRMWARE_CONFIG}")
    logging.info(f"Loaded Live version from serial_config.enc: {LIVE_VERSION}")
    logging.info(f"Loaded Tool version from serial_config.enc: {TOOL_VERSION}")
    logging.info(f"Loaded default test timeout from serial_config.enc: {DEFAULT_TIMEOUT}s")
    logging.info(f"Loaded reference firmware version from serial_config.enc: {FIRMWARE_VERSION}")
    logging.info(f"Loaded voltage test limits from serial_config.enc: {VOLTAGE_TESTS}")
    logging.info(f"Test mode from serial_config.enc: {TEST_MODE or '(none - running every test)'}")
    logging.info(f"Required serial number length from serial_config.enc: {SERIAL_NUMBER_LENGTH or '(none - no check)'}")

# ------------------------------------------- EMS/FACTORY mode, serial number length --

# Both loaded from serial_config.enc by load_serial_config() below, same as
# every other setting in this block - no separate config file.

VALID_TEST_MODES = {"EMS", "FACTORY"}

# None = no filtering, every test in test_sequence._FULL_TEST_SEQUENCE runs
# and shows in the UI (the behavior before this setting existed, and the
# fallback whenever serial_config.enc is absent/undecryptable or its "Mode"
# key is absent/invalid). Set to "EMS" or "FACTORY" by load_serial_config()
# below - always upper-case, regardless of how the config spelled it - once a
# valid Mode is found. test_sequence.py reads this at import time, so
# load_serial_config() must run before test_sequence (or anything that
# imports it - excel_logger, station_panel, worker) is imported. See main.py.
# See test_plan.xlsx's "EMS/FACTORY" column - that is where
# test_sequence.TEST_CATEGORIES' per-test assignment comes from.
TEST_MODE = None

# None = no check (the fallback whenever serial_config.enc is
# absent/undecryptable or "Serial_Number_Length" is absent/invalid, so an
# un-configured station behaves exactly as before this setting existed). Set
# to a positive int by load_serial_config() below - the EXACT length a
# serial number (typed or scanned) must be. test_impl.run_serial_scan fails
# the "Serial Number scanning" test, and station_panel's Serial Number box
# flags itself red, the moment the entered/scanned text's length is
# anything other than this - too short as well as too long.
SERIAL_NUMBER_LENGTH = None

# --------------------------------------------------------- digital outputs --

# Each DO step names the bits it asserts and the bits it releases. The runner
# keeps a cumulative mask per station, so "DO 2 ON" does not drop mains.
# "clear_all" wins over both and writes 0x00.
#
# CONFIRM: bits 2, 3 and 4 come straight from the test labels. The bit for
# "Mains on" is inferred. "battery_control" and "power_enable" are NOT DO
# steps - test_impl.TEST_FUNCTIONS routes both through _voltage() (they read
# an AI channel, "BAT_Ctrl" and Power Enable's own rail), not _do().
DO_STEPS = {
    "mains_on":        {"set": [0], "clear": []},
    "do2_on":          {"set": [2], "clear": []},
    "do2_off":         {"set": [], "clear": [2]},
    "do2_3_on":        {"set": [2, 3], "clear": []},
    "do4_on":          {"set": [4], "clear": []},
    "do_all_off":      {"set": [], "clear": [0, 1, 2, 3, 4], "clear_all": True},
}

# Every remaining DO_STEPS key acts on one physical circuit shared by both
# stations - a single scripts/tests/staticDO.py write covers both, and both
# stations report that one result (see shared_do.SharedDoRunner, used from
# test_impl.run_do_step).
SHARED_DO_STEPS = {"mains_on", "do2_on", "do2_off", "do2_3_on", "do4_on", "do_all_off"}

# The literal input value each shared DO step sends to
# scripts/tests/staticDO.py's run_staticDO() - confirmed from the bench, NOT
# computed from DO_STEPS' set/clear bits above (which don't reproduce these;
# DO_STEPS is kept only for the per-station fallback path when no
# SharedDoRunner is available, e.g. a standalone TestContext).
SHARED_DO_VALUES = {
    "mains_on":     0xFC,
    "do2_on":       0xFA,
    # CONFIRM on the bench: do2_on (0xFA) with DO2 released (active-low, so
    # bit 2 back to 1) - not measured yet like the values around it.
    "do2_off":      0xFE,
    "do2_3_on":     0xF2,
    "do4_on":       0xE2,
    "do_all_off":   0xFF,
}

# Tests that only need a PASS/FAIL Status column in the Excel log - no
# separate Value column:
#   * every DO step (above) just asserts an output mask, nothing measured
#   * "serial_scan" - its value duplicates the Serial Number metadata column
#   * "fw_download" - per-slot detail is already summarized by PASS/FAIL
STATUS_ONLY_TESTS = set(DO_STEPS) | {"serial_scan", "fw_download"}

# Seconds to wait after a DO write before the next test reads a voltage, so
# rails have time to settle.
DO_SETTLE_SECONDS = 0.5

# Firmware versions the meter must report. None means "log whatever it
# reports and PASS as long as it answers". Values are literal decoded packet
# integers (see scripts/version_check.py) - not derived from FIRMWARE_VERSION,
# whose dotted-string format ("4.2.0.0") does not match these codes.
EXPECTED_LIVE_VERSION = 17404
EXPECTED_INT_VERSION = 5

# Payload values a protocol test must return to count as a PASS. A key absent
# from here passes on any decoded response (the scripts already return None
# when the meter does not answer). "memory_test" is left out - CONFIRM the
# actual passing code (its packet decodes a 2-byte payload, unlike the others
# below, which are all 1 byte and use 1 = PASS).
EXPECTED_VALUES = {
    "memory_test": {1000},
    # CONFIRM on the bench: flash_test/eeprom_test decode through the generic
    # 1-byte decode_response (scripts/memory_test.py), same convention as
    # nic_4g_detection/power_enable_4g/rx_tx below - 1 = PASS assumed.
    "flash_test": {1},
    "eeprom_test": {1},
    "lcd_backlight_check": {1000},
    "calib_led": {1000},
    "nic_4g_detection": {1},
    "power_enable_4g": {1},
    # CONFIRM: NIC Detection runs right after DO 2 OFF, so no NIC should be
    # selected - assumed to answer 0 ("none"). Change once seen on the bench.
    "nic_detection": {0},
    "rf_nic_detection": {2},
    "rx_tx": {1},
    "relay_on": {1005},
    "relay_off": {1003},
}

# ------------------------------------------------- limits for the Excel log --

def _format_expected_value(value):
    """Set/list/tuple -> sorted comma-joined text, else plain str(). "" for None."""
    if value is None:
        return ""
    if isinstance(value, (set, frozenset, list, tuple)):
        return ", ".join(str(v) for v in sorted(value))
    return str(value)


# Tests whose expected response lives somewhere other than EXPECTED_VALUES
# under their own key. Read lazily (lambdas) because load_serial_config()
# replaces LIVE_VERSION / TOOL_VERSION after this module is imported.
_EXPECTED_SOURCES = {
    "live_version_test":  lambda: LIVE_VERSION,
    "tool_version_test":  lambda: TOOL_VERSION,
    "relay_off_1":        lambda: EXPECTED_VALUES.get("relay_off"),
    "relay_on_1":         lambda: EXPECTED_VALUES.get("relay_on"),
    # "RUN Memory test" is one Excel column backed by three protocol calls
    # (test_impl.run_memory) - show all three's expected values together.
    "memory_test": lambda: (
        f"memory={_format_expected_value(EXPECTED_VALUES.get('memory_test'))}, "
        f"flash={_format_expected_value(EXPECTED_VALUES.get('flash_test'))}, "
        f"eeprom={_format_expected_value(EXPECTED_VALUES.get('eeprom_test'))}"
    ),
}


def has_limits(key):
    """True for tests graded against a min/max window (VOLTAGE_TESTS)."""
    return key in VOLTAGE_TESTS


def get_limits(key):
    """(min, max) in volts for a VOLTAGE_TESTS key, else (None, None)."""
    spec = VOLTAGE_TESTS.get(key)
    if spec is None:
        return None, None
    return spec["min"], spec["max"]


def has_expected(key):
    """True for tests graded against an expected response value."""
    return key in _EXPECTED_SOURCES or key in EXPECTED_VALUES


def get_expected(key):
    """The expected response for `key` as display text ("" if none is set)."""
    source = _EXPECTED_SOURCES.get(key)
    expected = source() if source else EXPECTED_VALUES.get(key)
    return _format_expected_value(expected)

# ---------------------------------------------------------------- timeouts --

# Every test is killed off at its deadline and reported with its default
# result. Values are seconds and must stay above what the underlying layer
# already waits internally: Communication.open() retries 3x2 s and
# read_response() waits 5 s, so ~15 s is the floor for a protocol test.


TEST_TIMEOUTS = {
    "serial_scan":           15.0,
    "mains_on":              10.0,
    "test_6v":               10.0,
    # "test_3_6v":             10.0,  # 3.6V test disabled
    "test_3_3v":             10.0,
    "mains_detection":       10.0,
    "battery_control":       10.0,
    "mcu_vcc":               10.0,
    "fw_download":           60.0,   # gang programmer - shared, may flash both stations' adapters in turn (2 x 300s)
    "memory_test":           70.0,  # runs memory_test + flash_test + eeprom_test in sequence
    "live_version_test":     25.0,
    "tool_version_test":     25.0,
    "lcd_backlight_check":   180.0,  # includes waiting on the operator's Yes/No popup
    "calib_led":             180.0,  # includes waiting on the operator's Yes/No popup
    "efuse":                 10.0,
    "power_enable":          10.0,
    "rtc_calibration":       60.0,   # reset/get temp/calibrator read/set, plus the 2-5s pre-settle delay
    "verify_rtc_calibration": 45.0,  # 10-15s pre-settle delay, then one calibrator frame read
    "do2_on":                10.0,
    "nic_4g_detection":      30.0,
    "power_enable_4g":       30.0,
    "do2_off":               10.0,
    "nic_detection":         30.0,
    "do2_3_on":              10.0,
    "rf_nic_detection":      40.0,   # includes the 10s settle sleep before the protocol call
    "do4_on":                10.0,
    "rx_tx":                 25.0,
    # "ble_test":              30.0,  # BLE test disabled
    "relay_off_1":           40.0,   # full check-act-check flow (run_relay_off_test)
    "relay_on_1":            40.0,   # full check-act-check flow (run_relay_on_test)
    "do_all_off":            10.0,
    "main_battery_voltage":  15.0,
}

# Result reported when a test overruns its timeout. FAIL is the default
# because a meter that stops answering is a real failure - and because
# worker.py stops the station on the first FAIL, which is what you want when
# the DUT has gone unresponsive. Override a key with
# {"status": "SKIPPED", ...} to let the sequence continue past it instead.
DEFAULT_TIMEOUT_RESULT = {"status": "FAIL", "value": "TIMEOUT - no response"}

TEST_TIMEOUT_RESULTS = {}


def get_timeout(key):
    """Deadline in seconds for one test."""
    return TEST_TIMEOUTS.get(key, DEFAULT_TIMEOUT)


def get_timeout_result(key):
    """The default result to report when `key` overruns its deadline."""
    result = dict(TEST_TIMEOUT_RESULTS.get(key, DEFAULT_TIMEOUT_RESULT))
    result["value"] = f"{result.get('value', 'TIMEOUT')} ({get_timeout(key):g}s)"
    return result
