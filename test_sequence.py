"""
Single source of truth for the test list and its order.

Each entry is (key, label):
  - key   -> stable internal id, used for dict lookups / Excel columns /
             wiring a real implementation into test_impl.TEST_FUNCTIONS.
  - label -> exactly what the user asked for, shown in the UI.

To add/reorder/remove a test, edit _FULL_TEST_SEQUENCE and give the new key
an entry in TEST_CATEGORIES. Everything else (UI rows, worker loop, Excel
columns) is generated from the filtered TEST_SEQUENCE below.

This module is also where every test gets its deadline: get_test_function()
hands back a callable that is already wrapped in the timeout runner, so no
individual test has to remember to bound itself.

TEST_SEQUENCE is _FULL_TEST_SEQUENCE filtered down to whichever tests apply
to station_config.TEST_MODE ("EMS" or "FACTORY", set by
cfg.load_serial_config() from serial_config.enc's "Mode" key - see main.py,
which must call that before this module is first imported). TEST_MODE is
None (no filter, every test runs) by default, so an un-configured station
behaves exactly as before this setting existed.
"""

import functools
import logging
import time

import station_config as cfg
from test_impl import TEST_FUNCTIONS as REAL_TEST_FUNCTIONS
from test_stubs import TEST_FUNCTIONS as STUB_TEST_FUNCTIONS, generic_stub_test
from test_timeout import ORPHAN_SETTLE_SECONDS, run_with_timeout

_FULL_TEST_SEQUENCE = [
    ("serial_scan",           "Serial Number scanning"),
    ("mains_on",               "Mains on"),
    ("test_6v",                 "6V Power Supply Voltage"),
    # ("test_3_6v",               "3.6V Power Supply Voltage"),  # 3.6V test disabled - not run, logged or shown
    ("test_3_3v",               "3.3V Power Supply Voltage"),
    ("mains_detection",        "Mains Detection Voltage"),
    ("battery_control",        "Battery control Voltage"),
    ("mcu_vcc",                 "MCU VCC Voltage"),
    ("fw_download",             "FW Download"),
    ("memory_test",             "RUN Memory test"),
    ("live_version_test",      "Live Version test"),
    ("tool_version_test",      "Tool version test"),
    ("lcd_backlight_check",    "LCD & backlight Test"),
    ("calib_led",               "Calibration LED test"),
    ("efuse",                   "E-Fuse (6V)"),
    ("power_enable",            "Power Enable(3.3V)"),
    ("rtc_calibration",         "RTC Calibration/PPM Calibration"),
    ("verify_rtc_calibration",  "Verify RTC Calibration"),
    ("do2_on",                  "Short 4G & GND"),
    ("nic_4g_detection",       "4G NIC Detection"),
    ("power_enable_4g",        "4G Module Power Enable"),
    ("do2_off",                 "Remove 4G & GND Short"),
    ("nic_detection",          "NIC Detection"),
    ("do2_3_on",                "Short 4G, RF & GND"),
    ("rf_nic_detection",       "RF NIC Detection"),
    ("do4_on",                  "Short RX & TX"),
    ("rx_tx",                   "RX & TX"),
    # ("ble_test",                "BLE test"),  # BLE test disabled - not run, logged or shown
    ("relay_off_1",             "Relay off test"),
    ("relay_on_1",              "Relay on test"),
    ("do_all_off",              "Supply off"),
    ("main_battery_voltage",   "Main Battery Voltage"),
]

# Sanity check at import time: keys must be unique (used as dict keys / Excel columns).
_keys = [k for k, _ in _FULL_TEST_SEQUENCE]
assert len(_keys) == len(set(_keys)), "Duplicate test key in _FULL_TEST_SEQUENCE"

# Which of "EMS" / "FACTORY" each test belongs to, taken from the
# "EMS/FACTORY" column of test_plan.xlsx. A key tagged with both runs (and
# shows in the UI) under either mode; a key missing from this map entirely
# defaults to both, logged once below, rather than silently vanishing from
# the sequence when a new test is added here but not categorized yet.
_EMS_FACTORY = frozenset({"EMS", "FACTORY"})
_EMS_ONLY = frozenset({"EMS"})
_FACTORY_ONLY = frozenset({"FACTORY"})

TEST_CATEGORIES = {
    "serial_scan":          _EMS_FACTORY,
    "mains_on":             _EMS_FACTORY,
    "test_6v":              _EMS_FACTORY,
    # "test_3_6v":            _EMS_FACTORY,  # 3.6V test disabled
    "test_3_3v":            _EMS_FACTORY,
    "mains_detection":      _EMS_FACTORY,
    "battery_control":      _EMS_FACTORY,
    "mcu_vcc":              _EMS_FACTORY,
    "fw_download":          _EMS_FACTORY,  # "Test FW downloading" (EMS) / "Main FW downloading" (FACTORY)
    "memory_test":          _EMS_ONLY,
    "live_version_test":    _EMS_FACTORY,  # EMS's "LiveVersion test" / FACTORY's "FW version check"
    "tool_version_test":    _EMS_FACTORY,  # EMS's "tool version test" / FACTORY's "FW version check"
    # EMS-only - operator Yes/No visual checks, not run under FACTORY.
    "lcd_backlight_check":  _EMS_ONLY,
    "calib_led":            _EMS_ONLY,
    "efuse":                _EMS_FACTORY,
    "power_enable":         _EMS_FACTORY,
    # FACTORY-only per test_plan.xlsx ("RTC Calibration/PPM Calibration"
    # group, rows 23-25) - see scripts/rtc_calibration.py for the real
    # reset/get-temperature/set-calibration protocol calls.
    "rtc_calibration":      _FACTORY_ONLY,
    # Re-reads the frequency calibrator after "rtc_calibration" and grades the
    # resulting drift (scripts.rtc_calibration.get_rtc_calibration_result) -
    # confirms the calibration that was just set actually took.
    "verify_rtc_calibration": _FACTORY_ONLY,
    "do2_on":               _EMS_ONLY,
    "nic_4g_detection":     _EMS_ONLY,
    "power_enable_4g":      _EMS_ONLY,
    "do2_off":              _EMS_ONLY,
    "nic_detection":        _EMS_ONLY,
    "do2_3_on":             _EMS_ONLY,
    "rf_nic_detection":     _EMS_ONLY,
    "do4_on":               _EMS_ONLY,
    "rx_tx":                _EMS_ONLY,
    # "ble_test":             _EMS_ONLY,  # BLE test disabled
    "relay_off_1":          _EMS_ONLY,
    "relay_on_1":           _EMS_ONLY,
    "do_all_off":           _EMS_FACTORY,
    "main_battery_voltage": _FACTORY_ONLY,  # removed from EMS
}


def _filter_for_mode(sequence, mode):
    """`sequence` restricted to tests tagged with `mode` ("EMS"/"FACTORY");
    `sequence` unchanged if `mode` is None (no filter configured)."""
    if mode is None:
        return list(sequence)

    filtered = []
    for key, label in sequence:
        categories = TEST_CATEGORIES.get(key)
        if categories is None:
            logging.warning(f"test_sequence: '{key}' has no TEST_CATEGORIES entry - defaulting to EMS/FACTORY (both)")
            categories = _EMS_FACTORY
        if mode in categories:
            filtered.append((key, label))
    return filtered


# The list every other module (station_panel, worker, excel_logger, main)
# actually imports - already filtered down to cfg.TEST_MODE.
TEST_SEQUENCE = _filter_for_mode(_FULL_TEST_SEQUENCE, cfg.TEST_MODE)

# Real implementations win over the stub registry.
TEST_REGISTRY = {**STUB_TEST_FUNCTIONS, **REAL_TEST_FUNCTIONS}


def get_implementation(key, label):
    """
    The raw, unbounded callable(ctx) for one test.

    Uses the registered implementation from test_impl when there is one, and
    falls back to the generic stub so the whole sequence still runs
    end-to-end while hardware calls are filled in one test at a time.
    """
    if key in TEST_REGISTRY:
        return TEST_REGISTRY[key]
    return functools.partial(generic_stub_test, test_key=key, test_label=label)


def get_test_function(key, label):
    """
    Returns a callable(ctx) -> {"status": "PASS"/"FAIL", "value": ...} that is
    guaranteed to return within the test's configured deadline.

    If the implementation does not answer in time, the test's default result
    from station_config is returned instead and the sequence carries on. The
    abandoned call keeps running on its own thread, so a short settle pause
    follows to give it a chance to release the COM port before the next test
    on the same station opens it.
    """
    impl = get_implementation(key, label)
    timeout = cfg.get_timeout(key)

    def timed_test(ctx):
        result, timed_out = run_with_timeout(
            impl, timeout, lambda: cfg.get_timeout_result(key), ctx, name=key
        )
        if timed_out:
            logging.error(
                f"Station {ctx.station_num}: '{label}' timed out after {timeout}s "
                f"- reporting default result {result}"
            )
            time.sleep(ORPHAN_SETTLE_SECONDS)
        return result

    timed_test.__name__ = f"timed_{key}"
    return timed_test
