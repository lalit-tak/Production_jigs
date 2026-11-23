"""
Time-bounded execution of a single test.

Hardware calls (serial reads, DAQ reads, the firmware-flash DLL) can hang for
far longer than the operator is willing to wait, or never return at all. Every
test therefore runs through `run_with_timeout()`: the call is executed on a
daemon worker thread and joined with a deadline. If the deadline passes, the
test's configured default result is returned immediately and the sequence
carries on.

Caveat worth knowing: Python cannot kill a thread. A timed-out call keeps
running in the background until it finishes on its own. That matters most for
COM-port work, because the orphan still holds the port. Two things keep this
manageable:

  * `Communication` opens and closes the port inside each call, and its own
    internal timeouts (read_response(timeout=5), inter-byte 3 s) mean an
    orphan almost always unwinds within a few seconds.
  * Per-test timeouts in station_config are set comfortably above those
    internal timeouts, so a timeout here means "really stuck", not "slow".

`run_with_timeout` also reports whether the port is likely still busy, so the
caller can pause briefly before the next test on the same station.
"""

import logging
import threading

# How long to let an orphaned worker thread unwind before the next test on the
# same station starts. Only applied after an actual timeout.
ORPHAN_SETTLE_SECONDS = 2.0


class TimeoutResult:
    """Marker returned in place of a real result when a test overran."""

    def __init__(self, seconds):
        self.seconds = seconds

    def __repr__(self):
        return f"<TimeoutResult after {self.seconds}s>"


def run_with_timeout(func, timeout, default, *args, name=None, **kwargs):
    """
    Run `func(*args, **kwargs)` with a deadline.

    Returns (value, timed_out):
      * finished in time           -> (return value, False)
      * raised                     -> exception is re-raised to the caller
      * still running at deadline  -> (default, True)

    `default` may be a callable; it is invoked (with no arguments) only if the
    deadline is actually hit, so each timeout gets a fresh object. `name` is
    used for the worker thread and the log line; it defaults to the
    function's own name.
    """
    box = {}

    def target():
        try:
            box["value"] = func(*args, **kwargs)
        except BaseException as exc:  # noqa: BLE001 - re-raised on the caller's thread
            box["error"] = exc

    name = name or getattr(func, "__name__", repr(func))
    thread = threading.Thread(target=target, name=f"test:{name}", daemon=True)
    thread.start()
    thread.join(timeout)

    if thread.is_alive():
        logging.warning(f"'{name}' did not respond within {timeout}s - using default result")
        return (default() if callable(default) else default), True

    if "error" in box:
        raise box["error"]

    return box.get("value"), False
