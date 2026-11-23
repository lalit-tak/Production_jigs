"""
TestContext plus the fallback stub.

Real implementations now live in test_impl.py and are registered per test key
there. Anything in TEST_SEQUENCE without an entry in either registry falls
back to generic_stub_test(), so the whole sequence stays runnable while a new
test is being written.

To wire a new test in:

    1. Write run_<key>(ctx) in test_impl.py (real hardware/COM-port/DO call).
    2. Add "<key>": run_<key> to test_impl.TEST_FUNCTIONS.
    3. Give it a deadline in station_config.TEST_TIMEOUTS.
    4. Done - the worker, the UI and the Excel log pick it up automatically.
"""

import logging
import time

import station_config as cfg


class TestContext:
    """
    Everything a test needs to reach one station's hardware.

    The wiring (COM port, DAQ device, DO port, analog base channel, gang
    programmer index) is read from station_config by station number, so no
    test has to know where anything is plugged in. `com_port` can be passed
    explicitly to override the configured one.
    """

    def __init__(self, station_num, com_port=None, serial_number="", shared_do=None, shared_ai=None, shared_fw=None, shared_di=None, confirm=None, notify=None):
        self.station_num = station_num
        self.serial_number = serial_number

        self.com_port = com_port or cfg.STATION_COM_PORTS.get(station_num)
        self.scanner_port = cfg.STATION_SCANNER_PORTS.get(station_num)
        self.calibrator_port = cfg.STATION_CALIBRATOR_PORTS.get(station_num)
        self.daq_device = cfg.STATION_DAQ_DEVICES.get(station_num)
        self.do_port = cfg.STATION_DO_PORTS.get(station_num, 0)
        self.ai_base_channel = cfg.STATION_AI_BASE_CHANNEL.get(station_num, 0)
        self.fpa_index = cfg.STATION_FPA_INDEX.get(station_num, 1)

        # shared_do.SharedDoRunner / shared_ai.SharedAiRunner / shared_fw.
        # SharedFwRunner for this batch - shared with the other station's
        # TestContext so station_config.SHARED_DO_STEPS, every voltage test
        # and FW Download only ever hit the real hardware once (per key, for
        # DO/AI; once total, covering every adapter, for FW Download). None
        # outside a real batch run (e.g. a standalone/test TestContext) -
        # run_do_step/run_voltage_test/run_fw_download fall back to the
        # per-station path in that case.
        self.shared_do = shared_do
        self.shared_ai = shared_ai
        self.shared_fw = shared_fw
        # shared_di.SharedDiRunner - the relay tests' shared DI-port barrier
        # read/cache for this batch (station_config.DI_PORT carries both
        # stations' relay-confirm bits). None outside a real batch run - see
        # test_impl._check_relay_di's direct-read fallback in that case.
        self.shared_di = shared_di

        # worker.StationWorker.confirm - callable(title, message) -> bool,
        # shows a Yes/No popup on the GUI thread and blocks this test's
        # thread for the answer. None outside a real batch run; tests that
        # use it (LCD/backlight, calibration LEDs) skip the popup entirely
        # when it's None, same fallback pattern as the shared_* runners.
        self.confirm = confirm

        # worker.StationWorker._notify - callable(message), tells the GUI's
        # bottom-left status bar what this station is waiting on (e.g. a
        # settle-time time.sleep()) so it doesn't look hung. No-op outside a
        # real batch run (e.g. a standalone/test TestContext).
        self.notify = notify or (lambda message: None)

        # Cumulative digital-output mask for this station, so a later DO step
        # does not drop the lines an earlier one asserted.
        self.do_mask = 0

        # Scratch space shared between tests in one run (scanned serial,
        # firmware versions, BLE MAC, ...).
        self.data = {}


def generic_stub_test(ctx: TestContext, test_key: str, test_label: str):
    """
    Default placeholder for any test without a dedicated implementation.
    Simulates work and always PASSes so the full sequence can be exercised
    end-to-end before its hardware call exists.
    """
    logging.info(
        f"[STUB] Station {ctx.station_num}: running '{test_label}' ({test_key})"
    )
    time.sleep(0.25)
    return {"status": "PASS", "value": "STUB"}


# Kept as a fallback registry. test_impl.TEST_FUNCTIONS takes priority over
# anything listed here.
TEST_FUNCTIONS = {}
