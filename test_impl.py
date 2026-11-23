"""
Real test implementations - the bridge between TEST_SEQUENCE and the scripts
under scripts/.

Each function here takes a TestContext and returns the dict the worker and
the Excel logger expect:

    {"status": "PASS" | "FAIL", "value": "<what to show in the tooltip/log>"}

The scripts under scripts/ speak in raw decoded payloads and return None when
the meter does not answer; the adapters below turn that into PASS/FAIL and a
human-readable value, using the limits and expectations in station_config.

Timeouts are NOT applied here - test_sequence.get_test_function() wraps every
callable in the timeout runner, so a hung hardware call is bounded no matter
which adapter it came from.
"""

import logging
import random
import time

import station_config as cfg
from scripts.utils.daq_io import DaqUnavailable, read_ai_channel, read_di_port, write_do_port

# from scripts.energy_test import run_omkar_energy_test  # BLE test disabled
from shared_fw import grade_flash_report, run_mode_aware_firmware_flash
from scripts.lcd_led_test import run_calib_led_test, run_lcd_led_test
from scripts.memory_test import run_memory_test, run_flash_test, run_eeprom_test
from scripts.nic_detect_test import (
    run_4g_detect_test, run_4g_power_enable_test, run_rf_detect_test,
)
from scripts.relay_test import run_relay_off_test, run_relay_on_test
from scripts.rtc_calibration import get_rtc_calibration_result, run_rtc_calibration_test
from scripts.rx_tx_test import run_rx_tx_test
from scripts.scan_serialnumber import SerialScanner
from scripts.version_check import run_int_version_check, run_live_version_check


# --------------------------------------------------------------- helpers --

def _pass(value=""):
    return {"status": "PASS", "value": str(value)}


def _fail(value=""):
    return {"status": "FAIL", "value": str(value)}


def _simulated(what):
    """Only reachable with cfg.ALLOW_SIMULATION on - keeps the UI usable on a
    machine with no jig attached."""
    logging.warning(f"[SIM] {what} - hardware not present, reporting simulated PASS")
    return {"status": "PASS", "value": f"SIMULATED ({what})"}


def _wait(ctx, seconds, reason, test_type = 'sleep'):
    """time.sleep(seconds), but tells the GUI's bottom-left status bar why
    the station looks idle first - see TestContext.notify."""
    if test_type == 'sleep':
        ctx.notify(f"Waiting {seconds}s - {reason}...")
        time.sleep(seconds)
    else:
        ctx.notify(f"Waiting - {reason}...")


def _require_com_port(ctx):
    """Returns an error result if the station has no COM port configured."""
    if ctx.com_port:
        return None
    return _fail(f"No COM port configured for station {ctx.station_num} (see station_config.py)")


def _require_calibrator_port(ctx):
    """Returns an error result if the station has no RTC calibrator COM port
    configured (station_config.STATION_CALIBRATOR_PORTS, overridden by
    serial_config.enc's CALIBRATOR_COM<n>)."""
    if ctx.calibrator_port:
        return None
    return _fail(f"No RTC calibrator COM port configured for station {ctx.station_num} (see station_config.py)")


def _format_rtc_result(result):
    """dict -> "k=v, k=v, ..." for the Excel Value column - every field
    scripts.rtc_calibration.run_rtc_calibration_test/get_rtc_calibration_result
    returns, in the order they return it."""
    return ", ".join(f"{k}={v}" for k, v in result.items())


def _check_value(key, value, label):
    """
    Shared PASS/FAIL rule for the protocol tests.

    The scripts return None when the meter did not answer, so any decoded
    response counts as a PASS unless station_config.EXPECTED_VALUES pins the
    key to a specific set of payload values.
    """
    if value is None:
        return _fail("No response from meter")

    # The expected set itself goes to its own Excel column (station_config.
    # get_expected) - the value is just what the meter answered.
    expected = cfg.EXPECTED_VALUES.get(key)
    if expected is None:
        return _fail(f"{value} (no expected value configured)")
    if value not in expected:
        return _fail(f"{value}")

    return _pass(f"{value}")


def _protocol_test(ctx, key, func, label, *args):
    """Run one COM-port protocol test and grade its decoded payload."""
    error = _require_com_port(ctx)
    if error:
        return error
    return _check_value(key, func(ctx.com_port, *args), label)


# ----------------------------------------------------------- DO / AI steps --

def run_do_step(ctx, key):
    """
    Drive one DO step.

    Every remaining DO_STEPS key (station_config.SHARED_DO_STEPS) acts on a
    single physical circuit common to both stations - the real write happens
    once per batch, via ctx.shared_do (shared_do.SharedDoRunner), no matter
    which station's thread reaches it first, and both stations report that
    one result. (battery_control and power_enable used to be DO steps here;
    both are voltage reads now - see run_voltage_test and
    station_config.VOLTAGE_TESTS.)
    """
    step = cfg.DO_STEPS.get(key)
    if step is None:
        return _fail(f"No DO mapping for '{key}' (see station_config.DO_STEPS)")

    if key in cfg.SHARED_DO_STEPS and ctx.shared_do is not None:
        value = cfg.SHARED_DO_VALUES.get(key)
        if value is None:
            return _fail(f"No literal DO value configured for '{key}' (see station_config.SHARED_DO_VALUES)")
        result = ctx.shared_do.run_step(key, value, ctx.daq_device)
        _wait(ctx, cfg.DO_SETTLE_SECONDS, "DO settle time")
        return result

    if step.get("clear_all"):
        mask = 0
    else:
        mask = ctx.do_mask
        for bit in step.get("set", []):
            mask |= 1 << bit
        for bit in step.get("clear", []):
            mask &= ~(1 << bit)

    try:
        write_do_port(ctx.daq_device, ctx.do_port, mask)
    except DaqUnavailable as exc:
        if cfg.ALLOW_SIMULATION:
            ctx.do_mask = mask
            return _simulated(f"DO port {ctx.do_port} <- 0x{mask:02X}")
        return _fail(str(exc))

    ctx.do_mask = mask
    _wait(ctx, cfg.DO_SETTLE_SECONDS, "DO settle time")
    return _pass(f"DO port {ctx.do_port} = 0x{mask:02X}")


def run_do_all_off_safety(shared_do, daq_device):
    """
    Safety-net "all DO off" write, run once after the WHOLE BATCH finishes,
    only if any station in it failed - see MainWindow.on_station_finished().
    A FAIL abandons every remaining test for that station, including its own
    "DO0,1,2,3,4 OFF" step (do_all_off, near the end of TEST_SEQUENCE), which
    could otherwise leave that station's DO lines energized. Not a visible
    test: no task row, no Excel column, no ctx.notify - the caller only logs
    it to the text log.

    Same underlying write as run_do_step's SHARED_DO_STEPS branch;
    shared_do.SharedDoRunner caches by key per batch, so this is a no-op if
    do_all_off already ran for real (every station in the batch PASSed up to
    and including that step).
    """
    if shared_do is None:
        return
    value = cfg.SHARED_DO_VALUES.get("do_all_off")
    if value is None:
        logging.error("No literal DO value configured for 'do_all_off' (see station_config.SHARED_DO_VALUES)")
        return
    shared_do.run_step("do_all_off", value, daq_device)


def run_voltage_test(ctx, key):
    """
    Read one analog channel and check it against its configured window.

    Both stations' AI channels sit on one shared DAQ card - if ctx.shared_ai
    is set (a real batch run), the read goes through shared_ai.SharedAiRunner,
    which reads all 16 channels once per snapshot group per batch (shared
    between both stations AND between every test key in the same group)
    instead of once per channel per station. station_config.SHARED_AI_GROUPS
    groups test_6v..mcu_vcc under "_pre_fw_rails" and efuse/power_enable
    under "_post_fw_rails" (no DO step or FW download changes hardware state
    within either group); every other key (main_battery_voltage) gets its
    own fresh snapshot, keyed by itself.

    The channel itself is normally ai_base_channel + VOLTAGE_TESTS[key]
    ["channel"] (one shared offset for both stations); station_config.
    VOLTAGE_TEST_ABSOLUTE_CHANNELS overrides that with a direct per-station
    channel for any key that doesn't fit that shared-offset pattern
    (main_battery_voltage: AI3 for station 1, AI9 for station 2 - not the
    same offset from each station's base channel).
    """
    if key in "test_6v":
        _wait(ctx, 5, "6V rail settle time")
    if key in "main_battery_voltage":
        _wait(ctx, 3, "battery voltage settle time")
    spec = cfg.VOLTAGE_TESTS.get(key)
    if spec is None:
        return _fail(f"No analog channel mapped for '{key}' (see station_config.VOLTAGE_TESTS)")

    absolute_channels = cfg.VOLTAGE_TEST_ABSOLUTE_CHANNELS.get(key)
    if absolute_channels is not None:
        channel = absolute_channels.get(ctx.station_num)
        if channel is None:
            return _fail(f"No AI channel mapped for '{key}' on station {ctx.station_num}")
    else:
        channel = ctx.ai_base_channel + spec["channel"]

    try:
        if ctx.shared_ai is not None:
            snapshot_key = cfg.SHARED_AI_GROUPS.get(key, key)
            voltage = ctx.shared_ai.read_channel(snapshot_key, channel, ctx.daq_device)
        else:
            voltage = read_ai_channel(ctx.daq_device, channel)
    except DaqUnavailable as exc:
        if cfg.ALLOW_SIMULATION:
            return _simulated(f"AI ch{channel}")
        return _fail(str(exc))

    low, high = spec["min"], spec["max"]
    # Min/max go to their own Excel columns (station_config.get_limits) -
    # the value is just the reading; channel and limits stay in the text log.
    reading = f"{voltage:.3f} V"
    in_range = low <= voltage <= high
    logging.info(
        f"Station {ctx.station_num}: {key} = {reading} on ch{channel}, "
        f"limits {low}-{high} V -> {'PASS' if in_range else 'OUT OF RANGE'}"
    )
    if in_range:
        return _pass(reading)
    return _fail(reading)


# -------------------------------------------------------------- the tests --

def _check_serial_length(serial_number):
    """None if `serial_number`'s length matches cfg.SERIAL_NUMBER_LENGTH
    exactly (or no required length is configured), else the FAIL value to
    report - too short and too long both fail, not just too long."""
    required_len = cfg.SERIAL_NUMBER_LENGTH
    if required_len is not None and len(serial_number) != required_len:
        return _fail(f"Serial number length {len(serial_number)} != required {required_len}: {serial_number}")
    return None


def run_serial_scan(ctx):
    """
    First test in the sequence: trigger the barcode scanner on the station's
    scanner port and adopt the serial it reads, so Run Test / Enter can be
    used with the Serial Number box left empty. A station with a scanner
    port configured must get a successful scan every run - a failed scan or
    no barcode presented FAILs this test outright, even if the box already
    holds a serial number from a previous run/batch; it never silently
    reuses that old value as a PASS. (Only a station with NO scanner port
    configured at all - pure manual entry - falls back to whatever the
    operator already typed into the box.)

    ctx.serial_number is updated on a successful scan and the PASS value is
    always the clean serial number (never scanner error detail tacked on) -
    the UI shows it in the Serial Number box as soon as this test finishes,
    and every later test/Excel row/text log line uses ctx.serial_number.

    Either way, a serial number whose length doesn't exactly match
    cfg.SERIAL_NUMBER_LENGTH (serial_config.enc's "Serial_Number_Length") -
    too short or too long - fails this test instead of passing -
    ctx.serial_number is still set so the Excel row/Serial Number box
    reflect what was actually entered/scanned.
    """
    if not ctx.scanner_port:
        if ctx.serial_number:
            return _check_serial_length(ctx.serial_number) or _pass(ctx.serial_number)
        return _fail("No serial number entered and no scanner port configured")

    scanner = SerialScanner({ctx.station_num: ctx.scanner_port})
    scanner.scan_single_port(ctx.station_num, ctx.scanner_port)
    result = scanner.scan_results.get(ctx.station_num, {})

    if result.get("status") == "success" and result.get("serial"):
        ctx.serial_number = result["serial"]
        return _check_serial_length(ctx.serial_number) or _pass(ctx.serial_number)

    reason = result.get("error") or result.get("status") or "no data"
    # Clear it rather than leaving whatever stale value ctx.serial_number
    # started this run with (the box's text at Run Test time) - otherwise
    # the UI would keep showing an old serial next to a FAIL, looking like
    # nothing happened. See main.py's on_task_finished, which writes
    # ctx.serial_number straight back into the box, blank or not.
    ctx.serial_number = ""
    return _fail(f"Scan failed on {ctx.scanner_port}: {reason}")


def run_fw_download(ctx):
    """
    Flash the meter through the gang programmer and check its slot.

    Runs once per batch via ctx.shared_fw (shared_fw.SharedFwRunner): the
    first station's thread to reach this test flashes every station's
    adapter in turn (still one run_firmware_flash() call per adapter, not a
    confirmed single "flash all" call), then every station - including
    itself - reads its own adapter's graded result from that one pass.
    """
    _wait(ctx, 25, "FW download", 'wait')
    if ctx.shared_fw is not None:
        return ctx.shared_fw.run(ctx.station_num)

    flash_firmware = cfg.get_flash_firmware_file()
    report = run_mode_aware_firmware_flash(
        flash_firmware, cfg.get_bootloader_files(), cfg.FIRMWARE_CONFIG, ctx.fpa_index,
    )
    return grade_flash_report(report, ctx.fpa_index, flash_firmware)


def run_memory(ctx):
    """RUN Memory test - one UI row / Excel column, backed by three protocol
    calls in sequence: memory_test, then flash_test, then eeprom_test. Each is
    graded against its own station_config.EXPECTED_VALUES entry; PASS only if
    all three pass, and the Value column shows all three results."""
    _wait(ctx, 15, "PCBA settle time after FW download")
    error = _require_com_port(ctx)
    if error:
        return error

    memory_result = _check_value("memory_test", run_memory_test(ctx.com_port), "memory")
    flash_result = _check_value("flash_test", run_flash_test(ctx.com_port), "flash")
    eeprom_result = _check_value("eeprom_test", run_eeprom_test(ctx.com_port), "eeprom")

    value = (f"memory={memory_result['value']}, "
             f"flash={flash_result['value']}, "
             f"eeprom={eeprom_result['value']}")
    all_pass = (memory_result["status"] == "PASS"
                and flash_result["status"] == "PASS"
                and eeprom_result["status"] == "PASS")
    return _pass(value) if all_pass else _fail(value)


def run_live_version(ctx):
    """Read the live firmware version and compare it to cfg.LIVE_VERSION."""
    if "factory" in cfg.TEST_MODE.lower():
        _wait(ctx, 10, "PCBA settle time after FW download")
    error = _require_com_port(ctx)
    if error:
        return error

    version = run_live_version_check(ctx.com_port, cfg.LIVE_VERSION)
    logging.info(f"Station {ctx.station_num}: live firmware version = {version}, comport = {ctx.com_port}")
    if version is None:
        return _fail("No response from meter")

    ctx.data["live_version"] = version
    if cfg.LIVE_VERSION is not None and version != cfg.LIVE_VERSION:
        return _fail(f"{version}")
    return _pass(f"{version}")


def run_tool_version(ctx):
    """Read the internal ('tool') firmware version and compare it to cfg.TOOL_VERSION."""
    error = _require_com_port(ctx)
    if error:
        return error

    version = run_int_version_check(ctx.com_port, cfg.TOOL_VERSION)
    if version is None:
        return _fail("No response from meter")

    ctx.data["int_version"] = version
    if cfg.TOOL_VERSION is not None and version != cfg.TOOL_VERSION:
        return _fail(f"{version}")
    return _pass(f"{version}")


def _confirm_visual_check(ctx, label, result):
    """
    Gate a visual-inspection test's PASS on the operator's own eyes, not just
    the protocol response: only asked when the protocol check itself already
    passed (a protocol FAIL is reported as-is - nothing to visually confirm).
    Blocks this test until the operator answers the popup (see
    worker.StationWorker.confirm); skipped entirely when ctx.confirm is None
    (no popup mechanism available, e.g. a standalone TestContext).
    """
    if result["status"] != "PASS" or ctx.confirm is None:
        return result

    confirmed = ctx.confirm(
        label,
        f"{label}: protocol check passed ({result['value']}).\n\n"
        f"Did it look correct on the meter?",
    )
    if confirmed:
        return _pass(f"{result['value']} (operator confirmed)")
    return _fail(f"{result['value']} - operator rejected (clicked No)")


def run_lcd_backlight(ctx):
    result = _protocol_test(ctx, "lcd_backlight_check", run_lcd_led_test, "lcd")
    return _confirm_visual_check(ctx, "LCD & Backlight Check", result)


def run_calib_led(ctx):
    """One combined calibration LED check (the KVAR and KWH LEDs answer the
    same protocol command) - protocol response, then the operator's look."""
    result = _protocol_test(ctx, "calib_led", run_calib_led_test, "calib")
    return _confirm_visual_check(ctx, "Calibration LED test", result)


def run_rtc_calibration(ctx):
    """
    RTC Calibration/PPM Calibration (test_plan.xlsx rows 23-25: Reset RTC /
    Get temperature / Set & Calibrate RTC) - resets the meter's RTC over its
    optical COM port, reads its temperature-compensated tick count, reads the
    frequency calibrator's drift over the station's calibrator COM port, and
    writes that back as the meter's new PPM/RTC calibration. See
    scripts/rtc_calibration.py for the protocol; "Verify RTC Calibration"
    (run_verify_rtc_calibration below) re-reads the calibrator afterwards to
    confirm the write took.
    """
    error = _require_com_port(ctx)
    if error:
        return error
    error = _require_calibrator_port(ctx)
    if error:
        return error

    _wait(ctx, 25, " 25 sec for RTC calibration start settle time", 'wait')

    result = run_rtc_calibration_test(ctx.com_port, ctx.calibrator_port)
    if result is None:
        return _fail("No response from meter")

    value = _format_rtc_result(result)
    if result.get("set_rtc_calibration"):
        return _pass(value)
    return _fail(value)


def run_verify_rtc_calibration(ctx):
    """
    Verify RTC Calibration - follows "RTC Calibration/PPM Calibration" in the
    FACTORY sequence. Re-reads the frequency calibrator
    (scripts.rtc_calibration.get_rtc_calibration_result) and PASSes only if
    the post-calibration drift is within +-10 ppm.
    """
    error = _require_com_port(ctx)
    if error:
        return error
    error = _require_calibrator_port(ctx)
    if error:
        return error

    _wait(ctx, 10, "RTC calibration verify settle time")

    result = get_rtc_calibration_result(ctx.com_port, ctx.calibrator_port)
    if result is None:
        return _fail("No response from calibrator")

    value = _format_rtc_result(result)
    if result.get("set_rtc_calibration"):
        return _pass(value)
    return _fail(value)


def run_nic_4g(ctx):
    _wait(ctx, 1, "4G NIC settle time")
    return _protocol_test(ctx, "nic_4g_detection", run_4g_detect_test, "4g")


def run_power_enable_4g(ctx):
    _wait(ctx, 1, "4G power-enable settle time")
    return _protocol_test(ctx, "power_enable_4g", run_4g_power_enable_test, "4g_pwr")


def run_nic_detection(ctx):
    """NIC detection right after DO 2 OFF - same detect command as the 4G/RF
    tests, graded against station_config.EXPECTED_VALUES["nic_detection"]."""
    _wait(ctx, 10, "NIC settle time (after DO 2 OFF)")
    return _protocol_test(ctx, "nic_detection", run_rf_detect_test, "nic")


def run_nic_rf(ctx):
    """RF NIC detection - waits 10s before talking to the meter (settle time
    after the preceding DO 2&3 ON step)."""
    _wait(ctx, 5, "RF NIC settle time (after DO 2&3 ON)")
    return _protocol_test(ctx, "rf_nic_detection", run_rf_detect_test, "rf")


def run_rx_tx(ctx):
    return _protocol_test(ctx, "rx_tx", run_rx_tx_test, "rx_tx")


# BLE test disabled - uncomment this, the import above, its TEST_FUNCTIONS
# entry below, and its entries in test_sequence.py / station_config.py to
# bring it back.
# def run_ble(ctx):
#     """BLE / Omkar energy board - the response is the module's MAC address."""
#     error = _require_com_port(ctx)
#     if error:
#         return error
#
#     mac = run_omkar_energy_test(ctx.com_port)
#     if not mac:
#         return _fail("No response from BLE module")
#
#     ctx.data["ble_mac"] = mac
#     return _pass(f"{mac}")


def _check_relay_di(ctx, key, expected_bit):
    """
    Background physical confirmation on top of the meter's own relay-status
    report: station_config.DI_PORT is ONE shared register that carries BOTH
    stations' relay-contact feedback bits (station_config.
    STATION_RELAY_DI_BIT says which bit is this station's - 1 means that
    station's relay physically reads ON, 0 means OFF). Not a separate test
    case/Excel column - folded into _run_relay_test's own PASS/FAIL below,
    same as the meter's own status check.

    Because the port is shared, it is only read through ctx.shared_di
    (shared_di.SharedDiRunner): that blocks until every active station has
    also reached `key` (its own protocol check already passed), then reads
    station_config.DI_PORT exactly once for both of them - reading before
    the other station's relay has actually finished switching would catch
    its bit mid-flight. ctx.shared_di is None outside a real batch run (a
    standalone/test TestContext), where there's no other station to wait on
    - reads directly in that case.
    """
    bit = cfg.STATION_RELAY_DI_BIT.get(ctx.station_num)
    if bit is None:
        return _fail(f"No relay DI bit configured for station {ctx.station_num} (see station_config.STATION_RELAY_DI_BIT)")

    try:
        if ctx.shared_di is not None:
            port_value = ctx.shared_di.read_port(key, ctx.station_num, ctx.daq_device, cfg.DI_PORT)
        else:
            port_value = read_di_port(ctx.daq_device, cfg.DI_PORT)
    except DaqUnavailable as exc:
        if cfg.ALLOW_SIMULATION:
            return _simulated(f"DI port {cfg.DI_PORT} bit {bit}")
        return _fail(str(exc))

    actual_bit = (port_value >> bit) & 1
    detail = f"DI port {cfg.DI_PORT}=0x{port_value:02X} bit{bit}={actual_bit}"
    if actual_bit != expected_bit:
        return _fail(f"relay DI mismatch - {detail}, expected {expected_bit}")
    return _pass(detail)


def _run_relay_test(ctx, key, test_fn, expected_di_bit):
    """
    Relay check-act-check flow (scripts.relay_test.run_relay_off_test /
    run_relay_on_test): each already reads the current relay status, flips it
    only if needed, reads the status back, and returns (code, 'pass'/'fail').

    Once that protocol status check passes, _check_relay_di additionally
    confirms the relay physically switched (station_config.DI_PORT /
    STATION_RELAY_DI_BIT) - this test only counts as a PASS when both the
    meter's own report AND the DI confirmation agree. One test case/Excel
    column still covers the whole flow.
    """
    error = _require_com_port(ctx)
    if error:
        return error

    result = test_fn(ctx.com_port)
    if result is None:
        return _fail("No response to relay command")

    code, status = result
    if status != 'pass':
        return _fail(code)

    di_result = _check_relay_di(ctx, key, expected_di_bit)
    if di_result["status"] != "PASS":
        return _fail(f"{code}; {di_result['value']}")
    return _pass(f"{code}; {di_result['value']}")


def run_relay_off_1(ctx):
    return _run_relay_test(ctx, "relay_off_1", run_relay_off_test, expected_di_bit=0)


def run_relay_on_1(ctx):
    return _run_relay_test(ctx, "relay_on_1", run_relay_on_test, expected_di_bit=1)


# ----------------------------------------------------------- the registry --

def _do(key):
    """Bind a DO step key to a callable(ctx)."""
    def step(ctx, _key=key):
        return run_do_step(ctx, _key)
    step.__name__ = f"do_step_{key}"
    return step


def _voltage(key):
    """Bind an analog-input test key to a callable(ctx)."""
    def measure(ctx, _key=key):
        return run_voltage_test(ctx, _key)
    measure.__name__ = f"voltage_{key}"
    return measure


# Every key in TEST_SEQUENCE that has a real implementation. Anything absent
# still falls back to the generic stub, so the sequence always runs.
TEST_FUNCTIONS = {
    "serial_scan":          run_serial_scan,
    "mains_on":             _do("mains_on"),
    "test_6v":              _voltage("test_6v"),
    # "test_3_6v":            _voltage("test_3_6v"),  # 3.6V test disabled
    "test_3_3v":            _voltage("test_3_3v"),
    "mains_detection":      _voltage("mains_detection"),
    "battery_control":      _voltage("battery_control"),
    "mcu_vcc":              _voltage("mcu_vcc"),
    "fw_download":          run_fw_download,
    "memory_test":          run_memory,
    "live_version_test":    run_live_version,
    "tool_version_test":    run_tool_version,
    "lcd_backlight_check":  run_lcd_backlight,
    "calib_led":            run_calib_led,
    "efuse":                _voltage("efuse"),
    "power_enable":         _voltage("power_enable"),
    "rtc_calibration":      run_rtc_calibration,
    "verify_rtc_calibration": run_verify_rtc_calibration,
    "do2_on":               _do("do2_on"),
    "nic_4g_detection":     run_nic_4g,
    "power_enable_4g":      run_power_enable_4g,
    "do2_off":              _do("do2_off"),
    "nic_detection":        run_nic_detection,
    "do2_3_on":             _do("do2_3_on"),
    "rf_nic_detection":     run_nic_rf,
    "do4_on":               _do("do4_on"),
    "rx_tx":                run_rx_tx,
    # "ble_test":             run_ble,  # BLE test disabled
    "relay_off_1":          run_relay_off_1,
    "relay_on_1":           run_relay_on_1,
    "do_all_off":           _do("do_all_off"),
    "main_battery_voltage": _voltage("main_battery_voltage"),
}
