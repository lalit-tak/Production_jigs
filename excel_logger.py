import logging
import os
import shutil
from datetime import datetime

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

import station_config as cfg
from test_sequence import TEST_SEQUENCE

PASS_FILL = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
FAIL_FILL = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
OTHER_FILL = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")

METADATA_COLUMNS = ["Timestamp", "Station", "Serial Number", "Start Time", "End Time", "Total Test Time (s)"]

# Most tests get two columns: "<label>" holds the PASS/FAIL/... status
# (colored, same as before) and "<label> (Value)" holds what that test
# actually measured or returned - e.g. the real voltage reading for a
# range-checked test, the decoded payload for a protocol test.
#
# station_config.STATUS_ONLY_TESTS (the staticDO-driven tests, plus
# serial_scan and fw_download) get a Status column only, no "(Value)" column.
#
# What a test was graded against gets columns of its own, right after its
# Value column, instead of being folded into the value text:
#   * voltage tests (station_config.has_limits) -> "(Min)" and "(Max)"
#   * tests checked against an expected response
#     (station_config.has_expected)            -> "(Expected)"
# Filled from station_config at log time - the same numbers the test itself
# was graded against (including serial_config.enc overrides) - so they are
# there even for a test that timed out or was never run.
#
# Every test also gets a "(Duration (s))" column, last in its block - the
# wall-clock seconds worker.py's StationWorker spent on that one test (see
# results[key]["duration_seconds"]). 0 for a test that never actually ran
# (stopped by the operator, or skipped after an earlier test in the same
# station already failed).
#
# COLUMNS holds (key, label, extras) for every test in TEST_SEQUENCE order;
# extras is the ordered list of cell kinds after the status cell, so
# log_result can walk it to place each cell in the right column.
def _extra_columns(key):
    if key in cfg.STATUS_ONLY_TESTS:
        extras = []
    else:
        extras = ["value"]
        if cfg.has_limits(key):
            extras += ["min", "max"]
        elif cfg.has_expected(key):
            extras.append("expected")
    extras.append("duration")
    return extras


_EXTRA_HEADERS = {
    "value": "Value", "min": "Min", "max": "Max", "expected": "Expected", "duration": "Duration (s)",
}

COLUMNS = [(key, label, _extra_columns(key)) for key, label in TEST_SEQUENCE]

TEST_COLUMNS = []
for _key, _label, _extras in COLUMNS:
    TEST_COLUMNS.append(_label)
    TEST_COLUMNS.extend(f"{_label} ({_EXTRA_HEADERS[e]})" for e in _extras)

EXPECTED_HEADERS = METADATA_COLUMNS + TEST_COLUMNS + ["Overall Result"]


class ExcelLogger:
    """One workbook per batch; one row appended per station run in that
    batch. MainWindow.run_test() builds a brand-new ExcelLogger (a new
    uniquely time-stamped file_path) at the start of every batch, so each
    instance only ever gets this one batch's row(s) logged into it - see
    run_test's own comment for why (keeps each batch's S3 upload and
    post-upload local delete from ever colliding with another batch's file).

    The file itself is not created until ensure_exists() is called - see
    MainWindow.run_test(), which calls it right when the operator clicks Run,
    so nothing is written to disk unless a test actually starts. This also
    recreates the file if it was deleted or moved away (e.g. by hand) after
    ensure_exists() already ran for this batch.
    """

    def __init__(self, file_path):
        self.file_path = file_path
        if os.path.exists(self.file_path):
            self._migrate_if_needed()

    def ensure_exists(self):
        """Creates the workbook (with headers) if it's missing. Safe to call
        every time Run is clicked - a no-op once the file is there."""
        if not os.path.exists(self.file_path):
            self._init_workbook()
        else:
            self._migrate_if_needed()

    def _init_workbook(self):
        wb = Workbook()
        ws = wb.active
        ws.title = "Test Results"
        ws.append(EXPECTED_HEADERS)
        for cell in ws[1]:
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal="center")
        wb.save(self.file_path)

    def _migrate_if_needed(self):
        """
        Guard against an already-existing file from an older column layout
        (a different set/order of Status and Value columns). Appending
        today's rows straight onto a mismatched header row would silently
        shift every value into the wrong column. Instead, the old file is
        preserved untouched under a "_old" name and a fresh workbook with
        the current headers is started at the original path.
        """
        try:
            wb = load_workbook(self.file_path)
            ws = wb["Test Results"]
            existing_headers = [cell.value for cell in ws[1]]
        except Exception as exc:
            logging.warning(f"Could not read existing Excel log {self.file_path} ({exc}); starting a new one")
            existing_headers = None

        if existing_headers == EXPECTED_HEADERS:
            return

        base, ext = os.path.splitext(self.file_path)
        backup_path = f"{base}_old_{datetime.now().strftime('%H%M%S')}{ext}"
        try:
            shutil.move(self.file_path, backup_path)
            logging.warning(
                f"Excel log column layout changed - moved existing file to "
                f"{backup_path} and started a new one at {self.file_path}"
            )
        except Exception as exc:
            logging.error(f"Could not preserve old Excel log {self.file_path} ({exc}); it will be overwritten")

        self._init_workbook()

    def log_result(self, station_result):
        # Recreate the file if it was deleted/moved after ensure_exists() ran
        # but before this station finished - a run in progress should still
        # get its result logged rather than crash the worker's finish signal.
        self.ensure_exists()
        wb = load_workbook(self.file_path)
        ws = wb["Test Results"]

        # Wall-clock seconds this station spent on this batch run, start to
        # finish (PASS, FAIL or STOPPED) - station_result["start_time"]/
        # ["end_time"] bracket the whole _run_sequence() call in worker.py,
        # so this also covers lockstep waiting between tests, not just the
        # sum of each test's own "Duration (s)" column. Same meaning under
        # both EMS and FACTORY mode - TEST_SEQUENCE is already filtered by
        # cfg.TEST_MODE before either start_time or end_time is recorded.
        total_test_time = (station_result["end_time"] - station_result["start_time"]).total_seconds()

        row = [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            station_result["station_num"],
            station_result["serial_number"],
            station_result["start_time"].strftime("%Y-%m-%d %H:%M:%S"),
            station_result["end_time"].strftime("%Y-%m-%d %H:%M:%S"),
            round(total_test_time, 2),
        ]

        results = station_result["results"]
        status_col_offsets = []  # 0-based offset of each test's status cell within the test block
        offset = 0
        for key, _label, extras in COLUMNS:
            test_result = results.get(key, {})
            row.append(test_result.get("status", ""))
            status_col_offsets.append(offset)
            offset += 1
            low, high = cfg.get_limits(key)
            for extra in extras:
                if extra == "value":
                    row.append(test_result.get("value", ""))
                elif extra == "min":
                    row.append(low)
                elif extra == "max":
                    row.append(high)
                elif extra == "duration":
                    row.append(round(test_result.get("duration_seconds", 0.0), 2))
                else:
                    row.append(cfg.get_expected(key))
                offset += 1
        row.append(station_result["overall"])

        ws.append(row)
        new_row_idx = ws.max_row
        start_col = len(METADATA_COLUMNS) + 1

        for i, (key, _label, extras) in enumerate(COLUMNS):
            status = results.get(key, {}).get("status", "")
            if status == "PASS":
                fill = PASS_FILL
            elif status == "FAIL":
                fill = FAIL_FILL
            elif status:
                fill = OTHER_FILL
            else:
                continue

            status_col = start_col + status_col_offsets[i]
            ws.cell(row=new_row_idx, column=status_col).fill = fill
            if "value" in extras:
                ws.cell(row=new_row_idx, column=status_col + 1).fill = fill

        overall_col = start_col + len(TEST_COLUMNS)
        overall_cell = ws.cell(row=new_row_idx, column=overall_col)
        overall_cell.fill = PASS_FILL if station_result["overall"] == "PASS" else FAIL_FILL

        wb.save(self.file_path)
