"""
Every remaining DO_STEPS key (station_config.SHARED_DO_STEPS: Mains on,
DO 2 ON, DO 2&3 ON, DO 4 ON, DO0,1,2,3,4 OFF) acts on one physical circuit
shared by both stations, and goes out through scripts/tests/staticDO.py's
raw single-port write with a fixed literal input value per key
(station_config.SHARED_DO_VALUES), not a bitmask computed from DO_STEPS'
set/clear entries. battery_control and power_enable are not DO steps at all
any more - both are voltage reads (see test_impl.run_voltage_test).

SharedDoRunner makes sure that write happens exactly once per batch, no
matter which station's thread reaches the step first: the first caller
performs the real staticDO.py call and caches the result; every other
caller for the same key this batch (the other station, or a retry) just
gets that cached result back. A station running solo never waits on a
station that isn't running at all - there's nothing to wait for, it just
runs and caches its own result.

Guarded by daq_io.DAQ_LOCK, not a private lock of its own: staticDO.py opens
the physical DAQ card directly, same as InstantAI.py (shared_ai.py). Both
have to serialize on the exact same lock, or they can end up opening the
card at once, which the Advantech driver refuses ("device is not opened" /
busy errors).
"""

from scripts.tests.staticDO import run_staticDO
from scripts.utils.daq_io import DAQ_LOCK

_DO_COMPLETE_TEXT = "do output completed!"


class SharedDoRunner:
    """
    One instance per batch run - create fresh in MainWindow.run_test() and
    hand the same instance to every StationWorker started in that batch.
    """

    def __init__(self):
        self._results = {}

    def run_step(self, key, value, device):
        """
        value is the literal input station_config.SHARED_DO_VALUES[key]
        sends to run_staticDO() - not computed from bits. Returns the same
        {"status", "value"} dict to every caller for this key, this batch.
        """
        with DAQ_LOCK:
            if key in self._results:
                return self._results[key]

            ans = run_staticDO(value, device)
            if ans.lower() == _DO_COMPLETE_TEXT:
                result = {"status": "PASS", "value": f"{ans} (input 0x{value:02X})"}
            else:
                result = {"status": "FAIL", "value": ans or "No response from staticDO.py"}

            self._results[key] = result
            return result
