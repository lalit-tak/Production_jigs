import logging
import threading
import time
from datetime import datetime

from PyQt5.QtCore import QThread, pyqtSignal

from test_sequence import TEST_SEQUENCE, get_test_function
from test_stubs import TestContext

# Value used for every row after the one that actually failed - main.py
# checks against this to avoid re-showing "not run" cascade rows in the
# bottom-left status bar in place of the real failure.
NOT_RUN_VALUE = "Not run - a previous test failed"


class StationWorker(QThread):
    """
    Runs the full TEST_SEQUENCE for one station in a background thread so the
    UI never blocks. On the first FAIL, the station stops: every remaining
    test is reported as FAIL (cross icon, red row, counted in the Fail
    tally) without being run, so the row list, the overall station result,
    the Excel log and the text log all agree the station failed.

    Each test is time-bounded: get_test_function() wraps it in the timeout
    runner, so a hardware call that never answers is abandoned at its
    deadline and reported with its configured default result rather than
    hanging the station.
    """

    task_started = pyqtSignal(int)              # test_index
    task_finished = pyqtSignal(int, str, str)    # test_index, status, value
    station_finished = pyqtSignal(dict)          # full result payload
    log_message = pyqtSignal(str)
    # station_num, message - a test is blocked in a meaningful time.sleep()
    # (settle time, protocol backoff, ...) and wants the operator to see why
    # the station looks idle instead of hung. See TestContext.notify /
    # _notify below, and MainWindow.on_status_message for the UI side.
    status_message = pyqtSignal(int, str)
    # station_num, title, message, (threading.Event, dict) - MainWindow shows
    # a Yes/No box on the GUI thread and sets the event when the operator
    # answers; see confirm() below, which is what a test blocks on.
    confirm_popup_requested = pyqtSignal(int, str, str, object)

    def __init__(self, station_num, com_port, serial_number, shared_do=None, shared_ai=None, shared_fw=None,
                 shared_di=None, shared_step=None, parent=None):
        super().__init__(parent)
        self.station_num = station_num
        self.com_port = com_port
        self.serial_number = serial_number
        self.shared_do = shared_do
        self.shared_ai = shared_ai
        self.shared_fw = shared_fw
        # shared_di.SharedDiRunner - the relay tests' shared DI-port barrier
        # read (station_config.DI_PORT carries both stations' relay-confirm
        # bits); None runs this station free-running (no barrier to wait on).
        self.shared_di = shared_di
        # shared_step.SharedStepSync - keeps both stations on the same test
        # (the DO circuit is shared); None runs this station free-running.
        self.shared_step = shared_step
        self._stop_requested = False

    def request_stop(self):
        self._stop_requested = True

    def confirm(self, title, message):
        """
        Ask the operator a Yes/No question and block THIS worker thread
        (never the GUI thread) until they answer. Emitting a signal from a
        background QThread to a MainWindow slot is automatically queued by
        Qt, so confirm_popup_requested.emit() returns immediately; the
        QMessageBox itself is built and shown on the main thread once it
        processes that queued call, and event.wait() here blocks until that
        slot calls event.set() after the click.
        """
        event = threading.Event()
        response = {}
        self.confirm_popup_requested.emit(self.station_num, title, message, (event, response))
        event.wait()
        return response.get("yes", False)

    def _notify(self, message):
        """ctx.notify(...) - tell the GUI thread what this worker thread is
        waiting on (queued signal, safe to call from here)."""
        self.status_message.emit(self.station_num, message)

    def run(self):
        try:
            self._run_sequence()
        finally:
            # However this station ends, the other one must not keep
            # waiting for it at the next step - or at the shared DI-port
            # barrier mid relay test (shared_di.SharedDiRunner), which would
            # otherwise block forever waiting for a station that already
            # left the batch.
            if self.shared_step is not None:
                self.shared_step.leave(self.station_num)
            if self.shared_di is not None:
                self.shared_di.leave(self.station_num)

    def _leave_lockstep(self):
        if self.shared_step is not None:
            self.shared_step.leave(self.station_num)
        if self.shared_di is not None:
            self.shared_di.leave(self.station_num)

    def _run_sequence(self):
        ctx = TestContext(
            self.station_num, self.com_port, self.serial_number,
            self.shared_do, self.shared_ai, self.shared_fw, self.shared_di, self.confirm,
            notify=self._notify,
        )
        # Stashed so the GUI thread can read ctx.serial_number straight back
        # out of on_task_finished (see main.py) - the scanned/typed serial
        # itself, as opposed to task_finished's "value" for "serial_scan",
        # which is a human-readable PASS/FAIL message, not always the bare
        # serial number (e.g. a length-mismatch FAIL explains why it failed).
        self.ctx = ctx
        results = {}
        start_time = datetime.now()
        station_failed = False

        for index, (key, label) in enumerate(TEST_SEQUENCE):
            # Lockstep: start this test only once every other station still
            # running has finished the previous one - see shared_step.py.
            if not self._stop_requested and not station_failed and self.shared_step is not None:
                self.shared_step.wait_for_step(
                    self.station_num, index, should_abort=lambda: self._stop_requested
                )

            if self._stop_requested:
                self._leave_lockstep()
                value = "Stopped by operator"
                # 0.0 - never actually ran, so there is no time to report.
                results[key] = {"label": label, "status": "STOPPED", "value": value, "duration_seconds": 0.0}
                self.task_finished.emit(index, "STOPPED", value)
                self.log_message.emit(f"Station {self.station_num} - {label}: STOPPED {value}")
                continue

            if station_failed:
                # Not run - an earlier test already failed the station. Still
                # reported as FAIL (not a separate SKIPPED state) so the row
                # gets the cross icon, counts toward the Fail tally, and logs
                # to Excel and the text log exactly like a real failure.
                value = NOT_RUN_VALUE
                # 0.0 - never actually ran, so there is no time to report.
                results[key] = {"label": label, "status": "FAIL", "value": value, "duration_seconds": 0.0}
                self.task_finished.emit(index, "FAIL", value)
                self.log_message.emit(f"Station {self.station_num} - {label}: FAIL {value}")
                continue

            self.task_started.emit(index)
            test_start = time.monotonic()
            try:
                test_func = get_test_function(key, label)
                outcome = test_func(ctx) or {}
                status = outcome.get("status", "FAIL")
                value = str(outcome.get("value", ""))
            except Exception as exc:
                logging.exception(f"Station {self.station_num}: '{label}' raised an exception")
                status, value = "FAIL", f"Error: {exc}"
            # Wall-clock time this test actually took, including any timeout
            # wrapper overhead (get_test_function already bounds it at its
            # configured deadline - see test_sequence.py) - this is what ends
            # up in the Excel log's per-test "Duration (s)" column.
            duration_seconds = time.monotonic() - test_start

            results[key] = {
                "label": label, "status": status, "value": value, "duration_seconds": duration_seconds,
            }
            self.task_finished.emit(index, status, value)
            self.log_message.emit(
                f"Station {self.station_num} - {label}: {status} {value} ({duration_seconds:.2f}s)"
            )

            if status == "FAIL":
                station_failed = True
                self._leave_lockstep()

        end_time = datetime.now()
        if self._stop_requested:
            overall = "STOPPED"
        else:
            overall = "PASS" if all(r["status"] == "PASS" for r in results.values()) else "FAIL"

        self.station_finished.emit({
            "station_num": self.station_num,
            # ctx.serial_number, never falling back to self.serial_number
            # (the box's stale text from before this run started): the
            # barcode scan step may have replaced what the operator typed,
            # and deliberately blanks it back out on a failed/no-data scan
            # (test_impl.run_serial_scan) so a failed station's Excel row
            # and final status line don't keep showing an old serial number.
            "serial_number": ctx.serial_number,
            "results": results,
            "start_time": start_time,
            "end_time": end_time,
            "overall": overall,
        })
