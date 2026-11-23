from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit,
    QProgressBar, QScrollArea, QVBoxLayout, QWidget,
)

import station_config as cfg
from test_sequence import TEST_SEQUENCE

STATION_HEADER_BLUE = "#1E88E5"

SERIAL_EDIT_STYLE = """
    QLineEdit {
        padding: 6px 8px;
        border: 1px solid #c6c6c6;
        border-radius: 4px;
        font-size: 13px;
    }
    QLineEdit:focus { border: 1px solid #2196F3; }
    QLineEdit:disabled { background-color: #f0f0f0; color: #888; }
"""

# Applied instead of SERIAL_EDIT_STYLE while the box's length doesn't match
# cfg.SERIAL_NUMBER_LENGTH - see StationPanel._validate_serial_length.
SERIAL_EDIT_ERROR_STYLE = """
    QLineEdit {
        padding: 6px 8px;
        border: 2px solid #c62828;
        border-radius: 4px;
        font-size: 13px;
        background-color: #FDECEA;
    }
    QLineEdit:focus { border: 2px solid #c62828; }
    QLineEdit:disabled { background-color: #f0f0f0; color: #888; }
"""

ICON_STYLES = {
    # state: (symbol, color)
    "pending": ("\u23F1", "#9e9e9e"),   # stopwatch
    "running": ("\u27F3", "#2196F3"),   # circular arrow
    "PASS": ("\u2713", "#2e7d32"),      # check
    "FAIL": ("\u2715", "#c62828"),      # cross
    "SKIPPED": ("\u2013", "#b28900"),   # dash
    "STOPPED": ("\u25A0", "#757575"),   # square
}

# Overall station result - icon + label + color. This is a RESULT
# INDICATOR, not a timer: it reflects the station's current/overall
# outcome (idle / running / passed / failed), not elapsed time.
RESULT_STYLES = {
    "IDLE": ("\u23F3", "IDLE", "#78909C"),
    "RUNNING": ("\u27F3", "RUNNING", "#FB8C00"),
    "PASS": ("\u2713", "PASS", "#43A047"),
    "FAIL": ("\u2715", "FAIL", "#E53935"),
    "STOPPED": ("\u25A0", "STOPPED", "#78909C"),
}


class StepIcon(QLabel):
    """Small round icon showing a test's current state."""

    def __init__(self, size=18, parent=None):
        super().__init__(parent)
        self._size = size
        self._state = "pending"
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignCenter)
        self.set_state("pending")

    def set_state(self, state):
        self._state = state
        symbol, color = ICON_STYLES.get(state, ICON_STYLES["pending"])
        self.setText(symbol)
        self.setStyleSheet(f"""
            QLabel {{
                background-color: #eeeeee;
                color: {color};
                border-radius: {self._size // 2}px;
                font-size: {int(self._size * 0.55)}px;
                font-weight: bold;
            }}
        """)

    def set_size(self, size):
        """Resize the icon in place, keeping its current state/color."""
        if size == self._size:
            return
        self._size = size
        self.setFixedSize(size, size)
        self.set_state(self._state)


class TaskRow(QWidget):
    """One line in a station's test list: icon + test name. The result
    value/error (if any) is available as a tooltip rather than inline text,
    to keep the list clean. Row size (icon, font, vertical margin) is set
    dynamically by StationPanel._rescale_rows so the full list always fits
    its panel, regardless of screen resolution/DPI - see set_row_size."""

    _LABEL_COLORS = {
        "running": ("#1565C0", 700),
        "PASS": ("#2e7d32", 700),
        "FAIL": ("#c62828", 700),
        "SKIPPED": ("#b28900", 700),
    }
    _DEFAULT_LABEL_COLOR = ("#333", 600)

    def __init__(self, label, parent=None):
        super().__init__(parent)
        self._base_label = label
        self._state = "pending"
        self._font_px = 14
        self.setAutoFillBackground(True)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(10, 2, 10, 2)
        self._layout.setSpacing(9)

        self.icon = StepIcon(18)
        self.name_label = QLabel(label)
        # A QLabel's minimumSizeHint defaults to its full, un-wrapped text
        # width - with ~30 rows' worth of these stacked in a layout, the
        # longest one (e.g. "3.6V Power Supply Voltage") sets a hard floor
        # under the whole window's minimum width. That floor is font-metric
        # dependent, so it can land well past a smaller/lower-DPI screen's
        # actual width on one machine even though it's fine on another -
        # Windows then can't honor the window's minimum size at all (see
        # QWindowsWindow::setGeometry warnings in main.py's console output).
        # 1, not 0: Qt's qSmartMinSize only honors an explicit minimumSize()
        # when it's > 0 - 0 is treated as "unset" and falls straight back to
        # sizeHint()/minimumSizeHint(), i.e. the full text width again, a
        # no-op. 1 lets the layout shrink this label below its natural text
        # width when genuinely squeezed, instead of refusing to; it never
        # affects normal-size rendering; sizeHint (preferred size) is
        # unchanged.
        self.name_label.setMinimumWidth(1)

        self._layout.addWidget(self.icon)
        self._layout.addWidget(self.name_label, 1)

        self._apply_background("pending")
        self._apply_label_style()

    def _apply_background(self, state):
        if state == "running":
            bg = "#E3F2FD"
        elif state == "PASS":
            bg = "#F1F8F2"
        elif state == "FAIL":
            bg = "#FDECEA"
        else:
            bg = "white"
        self.setStyleSheet(f"background-color: {bg};")

    def _apply_label_style(self):
        color, weight = self._LABEL_COLORS.get(self._state, self._DEFAULT_LABEL_COLOR)
        self.name_label.setStyleSheet(
            f"background: transparent; font-size: {self._font_px}px; "
            f"font-weight: {weight}; color: {color};"
        )

    def set_status(self, state, value=""):
        self._state = state
        self.icon.set_state(state)
        self._apply_background(state)
        self.setToolTip(f"{self._base_label}: {value}" if value else "")
        self._apply_label_style()

    def set_row_size(self, icon_size, font_px, v_margin):
        """Resize this row in place - called by StationPanel._rescale_rows
        whenever the panel's available height changes."""
        self.icon.set_size(icon_size)
        self._font_px = font_px
        self._layout.setContentsMargins(10, v_margin, 10, v_margin)
        self._apply_label_style()


class _AutoFitScrollArea(QScrollArea):
    """QScrollArea that reports every resize to a callback, so its content
    can be rescaled to fit the new viewport instead of relying on a
    scrollbar."""

    def __init__(self, on_resize, parent=None):
        super().__init__(parent)
        self._on_resize = on_resize

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._on_resize()


class BigResultIndicator(QLabel):
    """Large overall-result icon docked on the right side of each station,
    vertically centered - shows the station's pass/fail outcome at a
    glance (correct/wrong), not elapsed time."""

    def __init__(self, size=130, parent=None):
        super().__init__(parent)
        self._size = size
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignCenter)
        self.setTextFormat(Qt.RichText)
        self.set_state("IDLE")

    def set_state(self, state):
        icon, text, color = RESULT_STYLES.get(state, RESULT_STYLES["IDLE"])
        self.setText(
            f"<div style='font-size:46px; line-height:1;'>{icon}</div>"
            f"<div style='font-size:13px; font-weight:700; margin-top:8px;'>{text}</div>"
        )
        self.setStyleSheet(f"""
            QLabel {{
                border: 5px solid {color};
                border-radius: {self._size // 2}px;
                background-color: white;
                color: {color};
            }}
        """)
        # Force an IMMEDIATE, synchronous repaint - not just update(), which
        # only schedules one on the event queue. The parent StationPanel
        # carries a QGraphicsDropShadowEffect, and when a burst of other
        # repaints is competing for the same event-loop pass (every test row
        # flipping to FAIL at once on an instant failure), a queued update()
        # on this deeply-nested child has been observed to never actually
        # reach the screen - the badge's text/style do change internally
        # (confirmed via geometry/text introspection), it just never gets
        # painted, until something forces a full redraw (e.g. minimize then
        # restore the window, which is what made it "fix itself").
        self.repaint()


class StationPanel(QFrame):
    """Card-style station panel: header (title plus this station's wired
    COM ports - see _ports_text), a slim progress bar, serial entry, the
    full test list on the left (every test visible at once - row
    height/font scale to whatever vertical space is available, so the list
    fits any screen size/resolution/DPI without a scrollbar), and a big
    overall-result icon docked on the right, vertically centered."""

    def __init__(self, station_num, parent=None):
        super().__init__(parent)
        self.station_num = station_num
        self.task_rows = []

        self.setObjectName("stationPanel")
        self.setStyleSheet("""
            QFrame#stationPanel {
                background-color: white;
                border: 1px solid #dcdcdc;
                border-radius: 10px;
            }
        """)
        # No QGraphicsDropShadowEffect here (previously used for a soft card
        # shadow): on this app's real hardware-failure path - a station's
        # ~30 rows all flipping red within the same tick, cross-thread, both
        # stations at once - Qt's cached effect pixmap for this panel was
        # observed to stop repainting the big PASS/FAIL badge altogether
        # (confirmed via geometry/text introspection: its state DID update
        # internally, it just never reached the screen) until something
        # forced a full redraw, e.g. minimizing then restoring the window.
        # Neither update() nor repaint() on the badge/panel reliably fixed
        # it, so the effect itself is removed rather than worked around -
        # the panel keeps its border, just without the drop shadow.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ---- Header: title only ----
        header = QWidget()
        header.setObjectName("stationHeader")
        header.setStyleSheet(f"""
            QWidget#stationHeader {{
                background-color: {STATION_HEADER_BLUE};
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
            }}
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 9, 16, 9)

        title = QLabel(f"Test Station {station_num}")
        title.setStyleSheet("background: transparent; color: white; font-size: 15px; font-weight: 700;")
        header_layout.addWidget(title)
        header_layout.addStretch()

        ports_label = QLabel(self._ports_text(station_num))
        ports_label.setStyleSheet("background: transparent; color: #E3F2FD; font-size: 11px; font-weight: 600;")
        ports_label.setMinimumWidth(1)  # see TaskRow.name_label above (1, not 0)
        header_layout.addWidget(ports_label)
        self.ports_label = ports_label

        outer.addWidget(header)

        # ---- Slim progress bar under the header ----
        self.progress = QProgressBar()
        self.progress.setMaximum(len(TEST_SEQUENCE))
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(5)
        self.progress.setStyleSheet("""
            QProgressBar { border: none; background-color: #e6e6e6; }
            QProgressBar::chunk { background-color: #2196F3; }
        """)
        outer.addWidget(self.progress)

        # ---- Body ----
        body = QVBoxLayout()
        body.setContentsMargins(16, 8, 16, 8)
        body.setSpacing(4)

        sn_row = QHBoxLayout()
        sn_label = QLabel("Serial Number:")
        sn_label.setStyleSheet("font-size: 13px; color: #333; font-weight: 600;")
        self.serial_edit = QLineEdit()
        self.serial_edit.setPlaceholderText("Enter serial number")
        self.serial_edit.setStyleSheet(SERIAL_EDIT_STYLE)
        self.serial_edit.textChanged.connect(self._validate_serial_length)
        sn_row.addWidget(sn_label)
        sn_row.addWidget(self.serial_edit, 1)
        body.addLayout(sn_row)

        # Left: every test row, no scroll area. Right: big result icon,
        # vertically centered in the remaining body height.
        content_row = QHBoxLayout()
        content_row.setSpacing(14)

        task_list = QWidget()
        task_list.setStyleSheet("background: transparent;")
        self.task_layout = task_layout = QVBoxLayout(task_list)
        task_layout.setSpacing(1)
        task_layout.setContentsMargins(0, 0, 0, 0)
        for i, (_key, label) in enumerate(TEST_SEQUENCE):
            row = TaskRow(label)
            task_layout.addWidget(row)
            self.task_rows.append(row)
        task_layout.addStretch()

        # Row height/font/icon size are recalculated on every resize (see
        # _rescale_rows) to exactly fill whatever vertical space is
        # available, so all rows always fit - independent of screen
        # resolution or Windows display scaling. AsNeeded stays as a safety
        # net only: it can still trigger at the clamped minimum row size on
        # an unreasonably short viewport.
        task_scroll = self.task_scroll = _AutoFitScrollArea(self._rescale_rows)
        task_scroll.setWidget(task_list)
        task_scroll.setWidgetResizable(True)
        task_scroll.setFrameShape(QFrame.NoFrame)
        task_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        task_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        task_scroll.viewport().setAutoFillBackground(False)

        icon_col = QVBoxLayout()
        icon_col.addStretch()
        self.result_indicator = BigResultIndicator(130)
        icon_col.addWidget(self.result_indicator, alignment=Qt.AlignHCenter)
        icon_col.addStretch()

        content_row.addWidget(task_scroll, 1)
        content_row.addLayout(icon_col)
        body.addLayout(content_row, 1)

        outer.addLayout(body, 1)

    def _rescale_rows(self):
        """Fit all rows exactly into the scroll area's current viewport
        height, clamped to a readable/clickable range. Called on every
        resize of task_scroll (panel resize, window resize/maximize,
        different screen/DPI, ...), so the list never needs to scroll on
        any reasonably sized screen."""
        n = len(self.task_rows)
        if not n:
            return
        viewport_h = self.task_scroll.viewport().height()
        if viewport_h <= 0:
            return

        spacing = self.task_layout.spacing()
        total_spacing = spacing * (n - 1)
        row_h = (viewport_h - total_spacing) / n
        row_h = max(16, min(30, row_h))

        icon_size = int(max(12, min(20, row_h - 4)))
        font_px = int(max(10, min(15, round(row_h * 0.5))))
        v_margin = max(0, int((row_h - icon_size) / 2))

        for row in self.task_rows:
            row.set_row_size(icon_size, font_px, v_margin)

    @staticmethod
    def _ports_text(station_num):
        """Header text for this station's wired COM ports: the meter's
        optical port and the barcode scanner port always; the RTC
        frequency-calibrator port too, but only under FACTORY mode (the only
        mode "RTC Calibration/PPM Calibration" and "Verify RTC Calibration"
        - the two tests that use it - actually run in). "-" for any port not
        configured (see station_config.py / serial_config.enc)."""
        optical = cfg.STATION_COM_PORTS.get(station_num) or "-"
        scanner = cfg.STATION_SCANNER_PORTS.get(station_num) or "-"
        parts = [f"Optical: {optical}", f"Scanner: {scanner}"]
        if cfg.TEST_MODE == "FACTORY":
            calibrator = cfg.STATION_CALIBRATOR_PORTS.get(station_num) or "-"
            parts.append(f"Calibrator: {calibrator}")
        return "    ".join(parts)

    def _validate_serial_length(self, text):
        """Flags the Serial Number box red whenever its length doesn't
        exactly match cfg.SERIAL_NUMBER_LENGTH (serial_config.enc's
        "Serial_Number_Length") - too short or too long - lets the operator
        see/fix it before Run Test even starts. test_impl.run_serial_scan
        enforces the same rule for the "Serial Number scanning" test itself,
        in case a barcode scan slips one past this (e.g. a scanner wired to
        a real COM port instead of typing into this box)."""
        required_len = cfg.SERIAL_NUMBER_LENGTH
        if required_len is not None and text and len(text) != required_len:
            self.serial_edit.setStyleSheet(SERIAL_EDIT_ERROR_STYLE)
            self.serial_edit.setToolTip(f"Serial number is {len(text)} characters - must be exactly {required_len}")
        else:
            self.serial_edit.setStyleSheet(SERIAL_EDIT_STYLE)
            self.serial_edit.setToolTip("")

    def reset_rows(self):
        for row in self.task_rows:
            row.set_status("pending", "")
        self.progress.setValue(0)

    def show_row(self, index):
        """Scroll the running test into view (no-op when the list fits)."""
        self.task_scroll.ensureWidgetVisible(self.task_rows[index])

    def set_running(self, running):
        self.serial_edit.setEnabled(not running)
        self.result_indicator.set_state("RUNNING" if running else "IDLE")

    def set_progress(self, completed):
        self.progress.setValue(completed)