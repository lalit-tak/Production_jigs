import ctypes
import logging
import os
import sys
import threading
from datetime import datetime

from PyQt5.QtCore import QEvent, Qt, QTimer
from PyQt5.QtGui import QFont, QKeySequence
from PyQt5.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton,
    QShortcut, QStatusBar, QVBoxLayout, QWidget,
)

import station_config as cfg

BASE_DIR = os.path.dirname(os.path.realpath(sys.argv[0]))
RESULT_DIR = os.path.join(BASE_DIR, "Test Result Excel File")
LOG_DIR = os.path.join(BASE_DIR, "Log files")
os.makedirs(RESULT_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

CURRENT_DATE = datetime.now().strftime("%Y-%m-%d")
PROGRAM_LOG_FILENAME = f"{CURRENT_DATE}_program_log.txt"
logging.basicConfig(
    filename=os.path.join(LOG_DIR, PROGRAM_LOG_FILENAME),
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    encoding="utf-8",
)

# Overrides cfg.STATION_SCANNER_PORTS / cfg.STATION_COM_PORTS, and sets
# cfg.TEST_MODE ("EMS"/"FACTORY"/None) and cfg.SERIAL_NUMBER_LENGTH, from
# serial_config.enc when present - must run after logging.basicConfig (above)
# so the outcome is captured in today's program log, and before MainWindow is
# defined (its NUM_STATIONS reads cfg.STATION_COM_PORTS at class-body time)
# AND before the test_sequence import below (and before excel_logger,
# station_panel and worker, which import test_sequence themselves) - that
# module filters its TEST_SEQUENCE by cfg.TEST_MODE at import time, so
# importing it before this call would build the unfiltered list instead.
cfg.load_serial_config()

import s3_uploader
import test_impl
from excel_logger import ExcelLogger
from shared_ai import SharedAiRunner
from shared_di import SharedDiRunner
from shared_do import SharedDoRunner
from shared_fw import SharedFwRunner
from shared_step import SharedStepSync
from station_panel import StationPanel
from test_sequence import TEST_SEQUENCE
from worker import NOT_RUN_VALUE, StationWorker

BTN_STYLE = """
    QPushButton {{
        background-color: {bg};
        color: white;
        font-weight: bold;
        padding: 8px 20px;
        border: none;
        border-radius: 3px;
    }}
    QPushButton:hover {{ background-color: {hover}; }}
    QPushButton:disabled {{ background-color: #b0bec5; color: #eceff1; }}
"""

BADGE_STYLE = "background-color: {bg}; color: {fg}; font-weight: bold; padding: 3px 12px; border-radius: 3px;"

# Tests that still run and still get logged, but whose row is hidden from
# the task list - "serial_scan" duplicates the Serial Number field above it.
HIDDEN_TEST_KEYS = {"serial_scan"}
HIDDEN_TEST_INDICES = [i for i, (key, _label) in enumerate(TEST_SEQUENCE) if key in HIDDEN_TEST_KEYS]

KEY_TO_INDEX = {key: i for i, (key, _label) in enumerate(TEST_SEQUENCE)}

# "Serial Number scanning" is test #1 in the sequence: on Enter/Run Test it
# reads the barcode itself (via scan_serialnumber.SerialScanner, see
# test_impl.run_serial_scan) when the station has a scanner port configured,
# so the operator does not have to pre-fill the Serial Number box by hand.
SERIAL_SCAN_INDEX = KEY_TO_INDEX["serial_scan"]


class MainWindow(QMainWindow):
    # One panel per station defined in station_config.
    NUM_STATIONS = len(cfg.STATION_COM_PORTS)

    def __init__(self):
        super().__init__()
        # [BADGEFIX-20261012] temporary marker in the title - confirms which
        # main.py copy is actually running (there are several on this
        # machine: Better_Meter_Main_Combined, "jig tool", "jig tool - Copy",
        # "jig tool - Copy/backup", "jig tool - Copy (2)" - only this one has
        # the station-finished repaint fix). Safe to remove once confirmed.
        self.setWindowTitle(
            f"Smart Manufacturing Suite - Better Meter JIG({cfg.TEST_MODE or 'ALL'})"
        )
        self.resize(1300, 850)

        self.workers = {}
        # Live references to currently-open confirm popups (see
        # on_confirm_popup_requested) - shown non-modal, so nothing else
        # keeps the Python wrapper alive while the operator hasn't answered.
        self._open_confirm_boxes = set()
        # Stations started this batch whose overall result hasn't reached
        # on_station_finished yet - the batch is over once this is empty.
        self.batch_pending = set()
        self.station_progress = {}
        self.total_pass = 0
        self.total_fail = 0
        # Lifetime totals - every station result and every completed batch
        # since this window opened, never reset by Run Test / New Batch (see
        # on_station_finished). total_pass/total_fail above are the current
        # batch's counts only and do reset each run.
        self.lifetime_pass = 0
        self.lifetime_fail = 0
        self.lifetime_batches = 0
        self.batch_seconds = 0

        central = QWidget()
        central.setStyleSheet("background-color: #eef1f4;")
        self.excel_logger = ExcelLogger(
            os.path.join(RESULT_DIR, f"{CURRENT_DATE}_TEST_RESULT.xlsx")
        )

        # One-time sweep of old (not today's) text logs up to S3 - only on
        # open, not after every batch, since a finalized log from a previous
        # day never changes mid-session.
        # s3_uploader.upload_old_text_logs_async(LOG_DIR, PROGRAM_LOG_FILENAME)

        self.batch_timer = QTimer(self)
        self.batch_timer.timeout.connect(self._tick_batch_timer)

        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._build_header())
        outer.addWidget(self._build_toolbar())

        stations_row = QHBoxLayout()
        stations_row.setContentsMargins(16, 16, 16, 16)
        stations_row.setSpacing(16)
        self.station_panels = {}
        for i in range(1, self.NUM_STATIONS + 1):
            panel = StationPanel(i)
            for idx in HIDDEN_TEST_INDICES:
                panel.task_rows[idx].setVisible(False)
            # Scanning/typing a serial number and hitting Enter starts the
            # run, same as clicking "Run Test" - the field is disabled while
            # a station is running (StationPanel.set_running), so Qt won't
            # deliver this while a run is already in progress.
            panel.serial_edit.returnPressed.connect(self.run_test)
            stations_row.addWidget(panel, 1)
            self.station_panels[i] = panel
        stations_wrap = QWidget()
        stations_wrap.setLayout(stations_row)
        outer.addWidget(stations_wrap, 1)

        self._build_status_bar()

        # Enter/Return runs the test from anywhere in the window, not just
        # while a serial_edit specifically has focus (that field's own
        # returnPressed above already covers that case) - e.g. after
        # clicking a station panel or tabbing away from the serial box.
        # Guarded the same way the Run button already is (isEnabled()),
        # since this fires even mid-run - not being tied to any one widget's
        # enabled state - and must not start a second batch on top of one
        # that's already going.
        for key in (Qt.Key_Return, Qt.Key_Enter):
            QShortcut(QKeySequence(key), self, activated=self._run_test_via_enter)

    # ---------- UI construction ----------

    def _build_header(self):
        header = QWidget()
        header.setStyleSheet("background-color: #1565C0;")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(18, 12, 18, 12)

        logo = QLabel("POLARIS")
        logo.setStyleSheet("color: white; font-size: 22px; font-weight: 900; letter-spacing: 1px;")
        title = QLabel("Smart Manufacturing Suite")
        title.setStyleSheet("color: white; font-size: 20px; font-weight: bold; padding-left: 18px;")
        version = QLabel(f"Better Meter JIG({cfg.TEST_MODE or 'ALL'}) |  08-10-2024")
        version.setStyleSheet("color: #cfe3fb; font-size: 12px; padding-left: 12px;")

        layout.addWidget(logo)
        layout.addWidget(title)
        layout.addWidget(version)
        layout.addStretch()

        stage = QLabel(f"V1.0.0.0")
        stage.setStyleSheet("color: white; font-size: 17px; font-weight: bold;")
        layout.addWidget(stage)

        return header

    def _build_toolbar(self):
        toolbar = QWidget()
        toolbar.setStyleSheet("background-color: #29B6F6;")
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(18, 8, 18, 8)
        layout.setSpacing(10)

        self.run_btn = QPushButton("\u25B6  Run Test")
        self.run_btn.setStyleSheet(BTN_STYLE.format(bg="#4CAF50", hover="#388E3C"))
        self.run_btn.clicked.connect(self.run_test)

        self.stop_btn = QPushButton("\u25A0  Stop")
        self.stop_btn.setStyleSheet(BTN_STYLE.format(bg="#F44336", hover="#D32F2F"))
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_test)

        self.new_batch_btn = QPushButton("New Batch")
        self.new_batch_btn.setStyleSheet(BTN_STYLE.format(bg="#455A64", hover="#37474F"))
        self.new_batch_btn.clicked.connect(self.new_batch)

        layout.addWidget(self.run_btn)
        layout.addWidget(self.stop_btn)
        layout.addWidget(self.new_batch_btn)
        layout.addStretch()

        return toolbar

    def _build_status_bar(self):
        bar = QStatusBar()
        bar.setStyleSheet("background-color: #eceff1;")

        self.status_msg_label = QLabel("Ready")

        # Placeholders - wire to real deck/firmware info once available.
        self.deck_label = QLabel(f"Daq Card Count: 1 - 16 CH")
        self.fw_label = QLabel(f"Current Firmware version: - {cfg.LIVE_VERSION}_{cfg.TOOL_VERSION}")
        for lbl in (self.deck_label, self.fw_label):
            lbl.setStyleSheet("color: #555; padding: 0 12px;")

        self.pass_count_label = QLabel("Pass: 0")
        self.pass_count_label.setStyleSheet("color: #2e7d32; font-weight: bold; padding: 0 10px;")
        self.pass_count_label.setToolTip("Stations passed in the current batch")
        self.fail_count_label = QLabel("Fail: 0")
        self.fail_count_label.setStyleSheet("color: #c62828; font-weight: bold; padding: 0 10px;")
        self.fail_count_label.setToolTip("Stations failed in the current batch")

        # Lifetime totals - every batch run since this window opened, not
        # just the current one (self.lifetime_pass/lifetime_fail/
        # lifetime_batches, updated alongside the per-batch counts above -
        # see _update_counts).
        self.lifetime_pass_label = QLabel("Total Pass: 0")
        self.lifetime_pass_label.setStyleSheet("color: #1b5e20; font-weight: bold; padding: 0 10px;")
        self.lifetime_pass_label.setToolTip("Stations passed since this window was opened")
        self.lifetime_fail_label = QLabel("Total Fail: 0")
        self.lifetime_fail_label.setStyleSheet("color: #8e0000; font-weight: bold; padding: 0 10px;")
        self.lifetime_fail_label.setToolTip("Stations failed since this window was opened")
        self.lifetime_batches_label = QLabel("Batches: 0")
        self.lifetime_batches_label.setStyleSheet("color: #37474f; font-weight: bold; padding: 0 10px;")
        self.lifetime_batches_label.setToolTip("Batches completed since this window was opened")

        self.link_status_label = QLabel("OFFLINE")
        self._set_link_status(False)

        self.batch_time_label = QLabel("BATCH TIME: 00:00:00")
        self.batch_time_label.setStyleSheet(BADGE_STYLE.format(bg="#43A047", fg="white"))

        bar.addWidget(self.status_msg_label, 1)
        bar.addPermanentWidget(self.deck_label)
        bar.addPermanentWidget(self.fw_label)
        bar.addPermanentWidget(self.pass_count_label)
        bar.addPermanentWidget(self.fail_count_label)
        bar.addPermanentWidget(self.lifetime_pass_label)
        bar.addPermanentWidget(self.lifetime_fail_label)
        bar.addPermanentWidget(self.lifetime_batches_label)
        bar.addPermanentWidget(self.link_status_label)
        bar.addPermanentWidget(self.batch_time_label)
        self.setStatusBar(bar)

    def _set_link_status(self, online):
        if online:
            self.link_status_label.setText("ONLINE")
            self.link_status_label.setStyleSheet(BADGE_STYLE.format(bg="#43A047", fg="white"))
        else:
            self.link_status_label.setText("OFFLINE")
            self.link_status_label.setStyleSheet(BADGE_STYLE.format(bg="#FDD835", fg="#333"))

    # ---------- Test control ----------

    def _run_test_via_enter(self):
        """The window-level Enter/Return shortcut's target - only runs if
        the Run button itself would accept a click right now, so Enter can't
        kick off a second batch while one is already running."""
        if self.run_btn.isEnabled():
            self.run_test()

    def run_test(self):
        """
        Starts every station that either already has a serial number
        entered, or has a scanner COM port configured so the "Serial Number
        scanning" test (test #1) can read the barcode itself once the
        sequence starts. A station with neither is skipped.
        """
        started_any = False

        # Create today's result workbook now if it isn't there yet (never
        # run today, or deleted/moved by hand since the app started) -
        # nothing is written to disk until the operator actually clicks Run.
        self.excel_logger.ensure_exists()

        # Which stations are actually going to run this batch, decided up
        # front.
        starting_stations = [
            station_num for station_num, panel in self.station_panels.items()
            if panel.serial_edit.text().strip() or cfg.STATION_SCANNER_PORTS.get(station_num)
        ]

        # Every configured station's gang-programmer adapter, not just the
        # ones actually starting this batch - as soon as ANY station reaches
        # "FW Download", SharedFwRunner flashes every adapter here in one
        # pass (see shared_fw.py). This pre-flashes a station that isn't
        # running yet (no serial number entered this batch) so it doesn't
        # need its own separate FW Download run later.
        fpa_indices = dict(cfg.STATION_FPA_INDEX)

        # One set of runners for the whole batch, shared by every
        # StationWorker started below - station_config.SHARED_DO_STEPS and
        # every voltage test only hit the real hardware once per key, and FW
        # Download flashes every configured station's adapter once in total
        # (see shared_fw.py) - shared_step keeps the stations in lockstep, so
        # every running station has reached FW Download before it starts.
        shared_do = SharedDoRunner()
        shared_ai = SharedAiRunner()
        # Barrier + single shared read for "Relay off test"/"Relay on test"'s
        # DI-port confirmation - station_config.DI_PORT carries both
        # stations' relay-confirm bits in the same register, so it's only
        # read once both stations' own relay commands have finished, and
        # read exactly once per transition, not once per station. See
        # shared_di.py.
        shared_di = SharedDiRunner(starting_stations)
        # Every starting station runs each test at the same time as the
        # others (lockstep) - the DO circuit is shared, see shared_step.py.
        shared_step = SharedStepSync(starting_stations)
        # get_flash_firmware_file()/get_bootloader_files() pick the EMS or
        # FACTORY firmware/bootloader file(s) per cfg.TEST_MODE (falling back
        # to the generic FIRMWARE_FILE/BOOTLOADER_FILE if the mode-specific
        # ones aren't set in serial_config.enc) - see station_config.py.
        shared_fw = SharedFwRunner(
            fpa_indices, cfg.get_flash_firmware_file(), cfg.get_bootloader_files(), cfg.FIRMWARE_CONFIG,
        )

        # Kept for the batch-end "all DO off" safety net (see
        # on_station_finished) - one physical DAQ card drives every station,
        # so any starting station's configured device reaches it.
        self.batch_shared_do = shared_do
        self.batch_pending = set()
        self.batch_daq_device = (
            cfg.STATION_DAQ_DEVICES.get(starting_stations[0]) if starting_stations else None
        )

        for station_num, panel in self.station_panels.items():
            serial_number = panel.serial_edit.text().strip()
            scanner_port = cfg.STATION_SCANNER_PORTS.get(station_num)
            if not serial_number and not scanner_port:
                logging.info(
                    f"Station {station_num}: skipped - no serial number entered and no scanner "
                    f"COM port configured (station_config.STATION_SCANNER_PORTS)"
                )
                continue

            panel.reset_rows()
            panel.set_running(True)
            self.station_progress[station_num] = 0

            com_port = cfg.STATION_COM_PORTS.get(station_num)
            if not com_port:
                logging.error(f"Station {station_num}: no COM port in station_config, skipping")
                panel.set_running(False)
                shared_step.leave(station_num)
                shared_di.leave(station_num)
                continue

            worker = StationWorker(
                station_num, com_port, serial_number,
                shared_do=shared_do, shared_ai=shared_ai, shared_fw=shared_fw,
                shared_di=shared_di, shared_step=shared_step,
            )
            worker.task_started.connect(lambda idx, n=station_num: self.on_task_started(n, idx))
            worker.task_finished.connect(
                lambda idx, status, value, n=station_num: self.on_task_finished(n, idx, status, value)
            )
            worker.station_finished.connect(lambda result, n=station_num: self.on_station_finished(n, result))
            worker.log_message.connect(logging.info)
            worker.status_message.connect(self.on_status_message)
            worker.confirm_popup_requested.connect(self.on_confirm_popup_requested)
            self.workers[station_num] = worker
            self.batch_pending.add(station_num)
            worker.start()
            started_any = True

        if not started_any:
            self.status_msg_label.setText(
                "Enter a serial number, or configure a scanner COM port, on at least one station before running."
            )
            return

        self.total_pass = 0
        self.total_fail = 0
        self._update_counts()
        self.batch_seconds = 0
        self.batch_time_label.setText("BATCH TIME: 00:00:00")
        self.batch_timer.start(1000)
        self._set_link_status(True)
        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.status_msg_label.setText("Running...")

    def stop_test(self):
        for worker in self.workers.values():
            if worker.isRunning():
                worker.request_stop()
        self.status_msg_label.setText("Stopping...")

    def new_batch(self):
        for worker in self.workers.values():
            if worker.isRunning():
                worker.request_stop()
                worker.wait(2000)
        self.workers.clear()
        self.batch_pending.clear()

        for panel in self.station_panels.values():
            panel.serial_edit.clear()
            panel.reset_rows()
            panel.set_running(False)

        self.station_progress.clear()
        self.total_pass = 0
        self.total_fail = 0
        self._update_counts()

        self.batch_seconds = 0
        self.batch_time_label.setText("BATCH TIME: 00:00:00")
        self.batch_timer.stop()

        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._set_link_status(False)
        self.status_msg_label.setText("Ready")

    # ---------- Worker signal handlers ----------

    def _tick_batch_timer(self):
        self.batch_seconds += 1
        h, rem = divmod(self.batch_seconds, 3600)
        m, s = divmod(rem, 60)
        self.batch_time_label.setText(f"BATCH TIME: {h:02d}:{m:02d}:{s:02d}")

    def _update_counts(self):
        self.pass_count_label.setText(f"Pass: {self.total_pass}")
        self.fail_count_label.setText(f"Fail: {self.total_fail}")
        self.lifetime_pass_label.setText(f"Total Pass: {self.lifetime_pass}")
        self.lifetime_fail_label.setText(f"Total Fail: {self.lifetime_fail}")
        self.lifetime_batches_label.setText(f"Batches: {self.lifetime_batches}")

    def on_task_started(self, station_num, index):
        panel = self.station_panels[station_num]
        panel.task_rows[index].set_status("running")
        panel.show_row(index)

    def on_status_message(self, station_num, message):
        """StationWorker.status_message - a test is blocked in a meaningful
        time.sleep() (settle time, protocol backoff, ...); show why in the
        bottom-left corner of the status bar instead of leaving it on the
        stale "Running..." text. Status only, no "Station N:" prefix - which
        station is idle-waiting is already visible from its own panel."""
        self.status_msg_label.setText(message)

    def on_task_finished(self, station_num, index, status, value):
        if index == SERIAL_SCAN_INDEX:
            # Show the actual scanned/typed serial number in the box
            # regardless of PASS or FAIL - not `value`, which on FAIL is a
            # human-readable reason (e.g. a length mismatch), not the bare
            # serial - so the operator always sees what the station read.
            # textChanged (already wired - see StationPanel._validate_
            # serial_length) flags the box red on its own the moment this
            # text's length doesn't match cfg.SERIAL_NUMBER_LENGTH, which is
            # exactly why "Serial Number scanning" just failed.
            # Always set it, even blank: test_impl.run_serial_scan clears
            # ctx.serial_number to "" when a scanner-equipped station fails
            # to get a fresh scan, specifically so the box doesn't keep
            # showing an old serial next to a FAIL and looking like nothing
            # happened - skipping setText() here on a falsy value would
            # undo that and leave the box's old (untouched) text in place.
            worker = self.workers.get(station_num)
            ctx = getattr(worker, "ctx", None)
            scanned = getattr(ctx, "serial_number", "") if ctx is not None else ""
            self.station_panels[station_num].serial_edit.setText(scanned)

        self.station_panels[station_num].task_rows[index].set_status(status, value)

        # Show a real failure in the bottom-left corner as soon as it
        # happens, not just once the whole station finishes - skip the
        # "not run" cascade rows that follow it so they don't bury the
        # actual failure under repeats of the same message.
        if status == "FAIL" and value != NOT_RUN_VALUE:
            label = TEST_SEQUENCE[index][1]
            self.status_msg_label.setText(f"Station {station_num}: {label} FAILED - {value}")

        self.station_progress[station_num] = self.station_progress.get(station_num, 0) + 1
        self.station_panels[station_num].set_progress(self.station_progress[station_num])

    def on_confirm_popup_requested(self, station_num, title, message, payload):
        """
        Slot for StationWorker.confirm_popup_requested - runs on the GUI
        thread (Qt auto-queues the cross-thread signal). Shown non-modal
        (show(), never exec_()) and centered over that station's own panel
        (both horizontally and vertically), so if both stations hit a
        confirm popup around the same time the operator can tell them apart
        at a glance and answer either one, in either order - exec_() would
        make the box application-modal and force the two popups to be
        answered strictly one at a time, whichever opened last on top.
        Unblocks the worker thread waiting in StationWorker.confirm() once
        the operator clicks Yes/No, by setting the event it's holding.
        """
        event, response = payload
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle(f"Station {station_num}: {title}")
        box.setText(message)
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.setDefaultButton(QMessageBox.Yes)
        box.setWindowModality(Qt.NonModal)
        box.setAttribute(Qt.WA_DeleteOnClose)

        panel = self.station_panels.get(station_num)
        if panel is not None:
            # adjustSize() first so width()/height() reflect this box's real
            # size (title/message/buttons) before we position it - a
            # freshly-constructed QMessageBox reports (0, 0) otherwise.
            box.adjustSize()
            panel_top_left = panel.mapToGlobal(panel.rect().topLeft())
            x = panel_top_left.x() + (panel.width() - box.width()) // 2
            y = panel_top_left.y() + (panel.height() - box.height()) // 2
            box.move(x, y)

        def _on_finished(result):
            response["yes"] = (result == QMessageBox.Yes)
            event.set()
            self._open_confirm_boxes.discard(box)

        box.finished.connect(_on_finished)
        # Keep a live reference - this method returns immediately (show(),
        # not exec_()), so without this PyQt would garbage-collect the
        # Python wrapper out from under the still-open window.
        self._open_confirm_boxes.add(box)
        box.show()
        box.raise_()
        box.activateWindow()

    def on_station_finished(self, station_num, result):
        panel = self.station_panels[station_num]
        panel.set_running(False)
        badge_state = result["overall"] if result["overall"] in ("PASS", "FAIL") else "STOPPED"
        panel.result_indicator.set_state(badge_state)
        self.excel_logger.log_result(result)
        self.status_msg_label.setText(
            f"Station {station_num}: {result['overall']} ({result['serial_number']})"
        )

        # Pass/Fail in the status bar counts stations (one overall result
        # each), not individual test cases - STOPPED counts toward neither.
        # Lifetime totals mirror the same rule but are never reset (see
        # run_test/new_batch), so they keep tallying across every batch run
        # for as long as this window stays open.
        if badge_state == "PASS":
            self.total_pass += 1
            self.lifetime_pass += 1
        elif badge_state == "FAIL":
            self.total_fail += 1
            self.lifetime_fail += 1
        self._update_counts()

        # Tracked explicitly rather than via QThread.isRunning(): this slot is
        # queued from inside the worker's run(), so the last station's own
        # thread can still report running here and the batch end would be
        # missed.
        self.batch_pending.discard(station_num)
        if not self.batch_pending:
            self.lifetime_batches += 1
            self._update_counts()
            self.batch_timer.stop()
            self.run_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self._set_link_status(False)

            # Whole batch is done - force the whole window to redraw here,
            # exactly once, so every station's own set_state() call above
            # (this station's and, if it finished first, the other
            # station's too) actually reaches the screen. This must happen
            # only here, after batch_pending is confirmed empty - NOT once
            # per station inside this same handler: with two stations
            # finishing within milliseconds of each other on separate
            # threads, an earlier attempt that repainted per-station (plus
            # QApplication.processEvents() to force it through) could
            # re-enter this very handler for the OTHER station's queued
            # signal while the first call's repaint() was still in progress,
            # and Qt does not handle a repaint() being re-entered on the
            # same top-level window well.
            #
            # On at least one bench machine, self.repaint() alone was NOT
            # enough to make this reliable even with the reentrancy above
            # fixed - the only thing confirmed (by hand) to always work was
            # minimizing then restoring the window, which makes Windows
            # throw away the window's cached backing store and redraw it
            # from scratch. A literal hide()+show() reproduced that same
            # "recreate the surface and redraw everything" effect, but it
            # visibly blinked the whole window - too disruptive for an
            # operator watching it happen on every single batch. Ask Windows
            # directly to redraw instead (see _force_redraw): no hide, no
            # blink, same "throw away whatever was cached and redraw now".
            self._force_redraw()

            if self.total_fail > 0:
                # A FAIL abandons every remaining test for that station,
                # including its own "DO0,1,2,3,4 OFF" step, which could
                # otherwise leave DO lines energized. Hidden step: no task
                # row, no Excel column, text log only (see
                # run_do_all_off_safety). Badges are already painted (see
                # _force_redraw() above) before the hardware write below runs.
                threading.Thread(target=self._run_batch_do_all_off_safety, daemon=True).start()

            # Whole batch is done (every started station has finished) -
            # upload today's Excel result workbook to S3. Runs on a
            # background thread (see s3_uploader) so it never blocks the UI.
            # s3_uploader.upload_excel_log_async(self.excel_logger.file_path)
            if self.status_msg_label.text().startswith("Station"):
                self.status_msg_label.setText("Ready")

    def _run_batch_do_all_off_safety(self):
        test_impl.run_do_all_off_safety(self.batch_shared_do, self.batch_daq_device)
        logging.info("all dac off after test completed")

    def _force_redraw(self):
        """
        Ask Windows to redraw this window right now, bypassing Qt's own
        dirty-region tracking entirely - see on_station_finished for why
        this is needed: on at least one bench machine, neither
        QWidget.update() nor QWidget.repaint() reliably got a station's
        freshly-set PASS/FAIL badge on screen once a test run's rapid burst
        of row repaints was happening (both stations failing within
        milliseconds of each other). Minimizing then restoring the window
        by hand always fixed it; RedrawWindow with RDW_INVALIDATE |
        RDW_UPDATENOW | RDW_ALLCHILDREN reproduces that same "throw away
        whatever was cached and redraw everything now" effect directly,
        without the visible blink a literal hide()+show() caused.
        """
        try:
            hwnd = int(self.winId())
            RDW_INVALIDATE = 0x0001
            RDW_UPDATENOW = 0x0100
            RDW_ALLCHILDREN = 0x0080
            ctypes.windll.user32.RedrawWindow(
                hwnd, None, None, RDW_INVALIDATE | RDW_UPDATENOW | RDW_ALLCHILDREN
            )
        except Exception:
            # Should never happen on Windows with a real native window
            # handle, but this is purely a paint-reliability belt-and-
            # braces - never let it take the batch-finish handler down.
            logging.exception("_force_redraw failed")
            self.repaint()

    def closeEvent(self, event):
        for worker in self.workers.values():
            if worker.isRunning():
                worker.request_stop()
                worker.wait(2000)
        event.accept()

    def changeEvent(self, event):
        """Start maximized; if the user minimizes and then restores the
        window, drop back to a normal (smaller) size instead of snapping
        back to maximized/full screen."""
        if event.type() == QEvent.WindowStateChange:
            was_minimized = bool(event.oldState() & Qt.WindowMinimized)
            is_minimized = bool(self.windowState() & Qt.WindowMinimized)
            if was_minimized and not is_minimized:
                self.showNormal()
        super().changeEvent(event)


def main():
    app = QApplication(sys.argv)
    # Every stylesheet in the UI sizes its text in px, but widgets without
    # one (buttons, status bar, popups) default to a pt font, which Windows
    # scales by its display-scaling setting (100% / 125% / 150% ...). Mixing
    # the two made the layout look different on every PC. Pin the default
    # font in px too - 13px is what the default font rendered at on the
    # bench PC this was designed on (1920x1080, 125%).
    font = QFont(app.font())
    font.setPixelSize(13)
    app.setFont(font)
    window = MainWindow()
    window.showMaximized()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()