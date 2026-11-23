"""
station_config.DI_PORT carries BOTH stations' relay-contact feedback bits
(station_config.STATION_RELAY_DI_BIT) in the SAME 8-bit register, so reading
it is only meaningful once every station that is about to grade itself
against it has actually finished its own relay command - read it too early
and a still-mid-flight station's bit in that snapshot is stale, failing a
relay that in fact just hadn't switched yet.

SharedDiRunner is a barrier + single shared read, one per relay transition
per batch ("relay_off_1" and "relay_on_1" each get their own key): a station
calls read_port() once its OWN protocol-level relay status check
(scripts.relay_test.run_relay_off_test / run_relay_on_test) has already
passed, and blocks there until every other ACTIVE station has also called it
for the same key. Only once everyone has arrived does the ONE real DAQ read
happen - so "Relay off test"/"Relay on test" reads station_config.DI_PORT
exactly once per batch for the off transition and once for the on
transition, never once per station, and every station grades its own bit
from that one shared snapshot. Same failure (DaqUnavailable) is re-raised to
every caller for that key, not just whichever thread did the real read.

A station running solo never waits on a station that isn't running this
batch - there's nothing to wait for, it just reads and caches its own
snapshot, same as shared_step.SharedStepSync's lockstep gate.
"""

import threading

from scripts.utils.daq_io import DaqUnavailable, read_di_port

# How often a waiting station re-checks whether every other active station
# has reached this key - same cadence shared_step.SharedStepSync polls at.
_POLL_SECONDS = 0.2


class SharedDiRunner:
    """
    One instance per batch run - create fresh in MainWindow.run_test() with
    the stations actually starting, and hand the same instance to every
    StationWorker started in that batch.
    """

    def __init__(self, stations):
        self._cond = threading.Condition()
        self._active = set(stations)
        self._ready = {}    # key -> set of station_nums that have called read_port() for it
        self._results = {}  # key -> (True, raw_port_value) | (False, error_text)

    def read_port(self, key, station_num, device, port):
        """
        Blocks until every active station has called this for `key`, then
        returns the one shared raw DI port byte for all of them. Raises
        DaqUnavailable (same message to every caller) if the one real read
        failed.
        """
        with self._cond:
            while True:
                if key in self._results:
                    ok, payload = self._results[key]
                    if ok:
                        return payload
                    raise DaqUnavailable(payload)

                ready = self._ready.setdefault(key, set())
                ready.add(station_num)
                self._cond.notify_all()

                if not all(s in ready for s in self._active):
                    self._cond.wait(timeout=_POLL_SECONDS)
                    continue

                # Every active station has reached this key and nobody has
                # read yet - this thread performs the one real read for
                # everybody waiting on it.
                try:
                    value = read_di_port(device, port)
                except DaqUnavailable as exc:
                    self._results[key] = (False, str(exc))
                    self._cond.notify_all()
                    raise
                self._results[key] = (True, value)
                self._cond.notify_all()
                return value

    def leave(self, station_num):
        """This station is done with the batch (failed, stopped or
        finished) - nobody waits for it at this barrier any more."""
        with self._cond:
            self._active.discard(station_num)
            self._cond.notify_all()
