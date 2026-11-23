"""
All the analog-input voltage tests (station_config.VOLTAGE_TESTS) read from
one physical DAQ card shared by both stations - scripts/tests/InstantAI.py's
run_instantAi() reads all 16 channels in a single call, which already covers
both stations' channel ranges (STATION_AI_BASE_CHANNEL: station 1 = 0-7,
station 2 = 8-15).

SharedAiRunner makes that one read happen once per SNAPSHOT GROUP per batch
(station_config.SHARED_AI_GROUPS), not once per test key per station: the
first test (any key, either station) to reach a given group reads all 16
channels and caches that snapshot under the group name; every other
key/station combination in the same group just looks its own channel up in
it. test_6v..mcu_vcc share "_pre_fw_rails" (right after mains_on, before FW
Download) and efuse/power_enable share "_post_fw_rails" (right after
Calibration LED) - nothing changes hardware state within either run of
back-to-back tests, so one shared read covers all of them. A key with no
group (main_battery_voltage) takes its own fresh snapshot, keyed by itself -
voltage tests are interleaved with DO steps in TEST_SEQUENCE, so reusing a
snapshot across a DO change would hand a later test a stale reading from
before it. A station running solo never waits on a station that isn't
running - there's nothing to wait for, it just reads and caches its own
snapshot.
"""

import threading

from scripts.tests.InstantAI import run_instantAi
from scripts.utils.daq_io import DaqUnavailable



class SharedAiRunner:
    """
    One instance per batch run - create fresh in MainWindow.run_test() and
    hand the same instance to every StationWorker started in that batch.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._snapshots = {}  # test_key -> {"Channel N data": volts, ...}

    def read_channel(self, test_key, channel, device):
        """
        Returns the voltage (float) on `channel`, from the shared 16-channel
        snapshot taken for `test_key` (read once per batch, the first time
        either station asks for this key). Raises DaqUnavailable on any read
        failure, same as daq_io.read_ai_channel, so callers don't need to
        know which path they went through.
        """
        with self._lock:
            snapshot = self._snapshots.get(test_key)
            if snapshot is None:
                try:
                    snapshot = run_instantAi(device)
                except Exception as exc:
                    raise DaqUnavailable(f"InstantAI read failed: {exc}") from exc
                if not isinstance(snapshot, dict):
                    raise DaqUnavailable(f"InstantAI read failed: {snapshot}")
                self._snapshots[test_key] = snapshot

            channel_key = f"Channel {channel} data"
            if channel_key not in snapshot:
                raise DaqUnavailable(f"InstantAI read did not include channel {channel}")
            return float(snapshot[channel_key])
