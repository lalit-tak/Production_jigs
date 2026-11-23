"""
Keeps every station in a batch on the same test at the same time.

The DO outputs are ONE physical circuit shared by both stations
(station_config.SHARED_DO_STEPS), so the stations must not drift apart: if
station 1 is already at "DO 2&3 ON" while station 2 is still reading "NIC
Detection" (which expects DO 2 OFF), station 2 reads the wrong hardware state
and fails a good meter. That drift happens naturally - the operator answers
one station's LCD / Calibration LED popup before the other's, one meter
answers a protocol command a bit slower, and so on.

SharedStepSync is a lockstep gate: before starting test N, a station waits
until every other ACTIVE station has also finished test N-1 and reached N.
A station that fails or is stopped calls leave() and stops counting, so the
remaining station carries on alone instead of waiting for it.
"""

import threading

# How often a waiting station re-checks whether it was asked to stop.
_POLL_SECONDS = 0.2


class SharedStepSync:
    """
    One instance per batch run - create fresh in MainWindow.run_test() with
    the stations actually starting, and hand the same instance to every
    StationWorker started in that batch.
    """

    def __init__(self, stations):
        self._cond = threading.Condition()
        self._active = set(stations)
        self._reached = {}  # station_num -> index of the test it is waiting to start

    def wait_for_step(self, station_num, index, should_abort=lambda: False):
        """
        Blocks until every active station has reached test `index`. Returns
        False if should_abort() turned true while waiting (operator pressed
        Stop), True otherwise.
        """
        with self._cond:
            self._reached[station_num] = index
            self._cond.notify_all()
            while not all(self._reached.get(s, -1) >= index for s in self._active):
                if should_abort():
                    return False
                self._cond.wait(timeout=_POLL_SECONDS)
            return True

    def leave(self, station_num):
        """This station is done with the batch (failed, stopped or finished) -
        nobody waits for it any more."""
        with self._cond:
            self._active.discard(station_num)
            self._cond.notify_all()
