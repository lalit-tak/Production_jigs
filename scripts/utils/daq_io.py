"""
Thin DAQ wrapper used by the test layer.

scripts/tests/staticDO.py and scripts/tests/InstantAI.py are the Advantech
sample programs: they hard-code port 0, channel 0-15 and a profile path that
only resolves when you run them from inside scripts/tests. The bench needs a
specific DO port and a specific AI channel per station, so the two calls are
reimplemented here against the same BDaq API, with the profile path resolved
from the running app's own directory instead of the working directory.

Every function raises DaqUnavailable when the Advantech driver or card is not
present, so the caller can decide whether that is a failure or a cue to
simulate.
"""

import logging
import os
import sys
import threading

# sys.argv[0]-based, NOT __file__: under a PyInstaller --onefile build this
# module runs from a temp extraction folder, so __file__ would point there
# instead of next to the built .exe - where scripts/profile/DemoDevice.xml is
# actually shipped (see main.py's own BASE_DIR, same reasoning).
PROFILE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(sys.argv[0])), "scripts", "profile", "DemoDevice.xml"
)

# The BDaq API is not thread-safe and both stations share one card, so all
# DAQ traffic is serialised - including scripts/tests/staticDO.py and
# InstantAI.py's own raw calls (see shared_do.py / shared_ai.py), which open
# the same physical device independently and would otherwise race this
# module's own opens ("device is not opened" / busy errors from opening the
# same card twice at once). Public so those two modules can share this exact
# lock instead of using their own.
DAQ_LOCK = threading.Lock()


class DaqUnavailable(Exception):
    """Raised when the Advantech driver/card cannot be reached."""


def _import_bdaq():
    try:
        from scripts.Automation.BDaq import ErrorCode
        from scripts.Automation.BDaq.BDaqApi import AdxEnumToString, BioFailed
        from scripts.Automation.BDaq.InstantAiCtrl import InstantAiCtrl
        from scripts.Automation.BDaq.InstantDoCtrl import InstantDoCtrl
        from scripts.Automation.BDaq.InstantDiCtrl import InstantDiCtrl
    except Exception as exc:  # driver DLL missing, import-time failure, ...
        raise DaqUnavailable(f"Advantech BDaq unavailable: {exc}") from exc
    return ErrorCode, AdxEnumToString, BioFailed, InstantAiCtrl, InstantDoCtrl, InstantDiCtrl


def _load_profile(ctrl):
    """Best effort - the card works on its defaults if no profile matches."""
    try:
        ctrl.loadProfile = PROFILE_PATH
    except Exception as exc:
        logging.debug(f"DAQ profile not loaded ({PROFILE_PATH}): {exc}")


def _fail_text(AdxEnumToString, ret):
    return "error %#x [%s]" % (ret.value, AdxEnumToString("ErrorCode", ret.value, 256))


def write_do_port(device_description, port, value):
    """Write one 8-bit digital-output port. Returns the value written."""
    _, AdxEnumToString, BioFailed, _, InstantDoCtrl, _ = _import_bdaq()

    with DAQ_LOCK:
        try:
            ctrl = InstantDoCtrl(device_description)
        except Exception as exc:
            raise DaqUnavailable(f"cannot open {device_description}: {exc}") from exc
        try:
            _load_profile(ctrl)
            ret = ctrl.writeAny(port, 1, [value & 0xFF])
            if BioFailed(ret):
                raise DaqUnavailable(f"DO write to port {port} failed: {_fail_text(AdxEnumToString, ret)}")
        finally:
            ctrl.dispose()

    logging.info(f"DO write {device_description} port {port} <- 0x{value & 0xFF:02X}")
    return value & 0xFF


def read_ai_channel(device_description, channel):
    """Read one analog-input channel and return it in volts."""
    _, AdxEnumToString, BioFailed, InstantAiCtrl, _, _ = _import_bdaq()

    with DAQ_LOCK:
        try:
            ctrl = InstantAiCtrl(device_description)
        except Exception as exc:
            raise DaqUnavailable(f"cannot open {device_description}: {exc}") from exc
        try:
            _load_profile(ctrl)
            ret, scaled = ctrl.readDataF64(channel, 1)
            if BioFailed(ret):
                raise DaqUnavailable(f"AI read of channel {channel} failed: {_fail_text(AdxEnumToString, ret)}")
        finally:
            ctrl.dispose()

    voltage = float(scaled[0])
    logging.info(f"AI read {device_description} ch{channel} = {voltage:.4f} V")
    return voltage


def read_di_port(device_description, port):
    """Read one 8-bit digital-input port and return its raw byte value
    (bit0 = DI0 of that port, same bit order write_do_port uses for DO)."""
    _, AdxEnumToString, BioFailed, _, _, InstantDiCtrl = _import_bdaq()

    with DAQ_LOCK:
        try:
            ctrl = InstantDiCtrl(device_description)
        except Exception as exc:
            raise DaqUnavailable(f"cannot open {device_description}: {exc}") from exc
        try:
            _load_profile(ctrl)
            ret, data = ctrl.readAny(port, 1)
            if BioFailed(ret):
                raise DaqUnavailable(f"DI read of port {port} failed: {_fail_text(AdxEnumToString, ret)}")
        finally:
            ctrl.dispose()

    value = data[0] & 0xFF
    logging.info(f"DI read {device_description} port {port} = 0x{value:02X}")
    return value
