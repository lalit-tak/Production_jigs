"""
FW Download programs both stations' meters through ONE shared gang-programmer
adapter (confirmed: F_OpenInstancesAndFPAs reports "Connected adapters: 1") -
each station's meter is wired to a different SOCKET on that one adapter
(station_config.STATION_FPA_INDEX: station 1 = socket #2, station 2 = socket
#4 in this bench's serial_config.enc). One call to
scripts.FirmwareFlash.run_firmware_flash() programs every socket that
actually has a target connected, in a single pass - F_AutoProgram(0) covers
all of them, not just one - and its report already contains a result per
socket (#1-#8, see FirmwareFlash.check_firmware_log()).

The adapter INSTANCE passed to F_Set_FPA_index()/F_Clear_Locked_Device() (see
_do_flash below) is a different number from a station's socket, and must
always be 1 - the one connected adapter's own instance index - never a
station's socket number: passing socket 2 or 4 there selects a nonexistent
second/fourth adapter INSTANCE, which is why F_Clear_Locked_Device,
F_Verify_Access_to_MCU and F_AutoProgram used to all fail with -1 and an
empty report despite the flash otherwise looking fine.

Calling run_firmware_flash() a second time (once per station) is not just
redundant: it reopens the DLL/adapter handles a second time before the first
pass's are fully released, which causes a resource allocation conflict.

SharedFwRunner runs "FW Download" exactly once per batch: the first
station's thread to get here makes the single run_firmware_flash() call
(under a lock) and grades every configured station's own slot out of that
one report; every other station just reads its own result from that cache.

No barrier is needed to make sure every station is plugged in and ready
first - shared_step.SharedStepSync already holds every running station at
the start of each test until all of them have reached it, so by the time
anyone calls run() here, every station still in the batch has finished
MCU VCC. A station that failed earlier has left the lockstep and is simply
not waited for (it used to make the other station sit at a Barrier for 90s
and then FAIL a good meter).
"""

import logging
import threading

import station_config as cfg
from FirmwareFlash import run_firmware_flash as run_ems_firmware_flash
from MainFirmwareFlash import run_firmware_flash as run_factory_firmware_flash

# The one physical gang-programmer adapter's own instance index (F_Set_FPA_
# index's argument) - not a station's socket number (station_config.
# STATION_FPA_INDEX). CONFIRM if a second adapter is ever added to the bench.
GANG_PROGRAMMER_ADAPTER_INDEX = 1


def run_mode_aware_firmware_flash(flash_firmware, bootloader_firmwares, config_path, fpa_index):
    """
    Dispatches to MainFirmwareFlash.run_firmware_flash (FACTORY - two
    bootloaders, each merged at its own memory offset) or
    FirmwareFlash.run_firmware_flash (EMS, or no Mode configured - one
    bootloader), per cfg.TEST_MODE.

    `bootloader_firmwares` is station_config.get_bootloader_files()'s list -
    1 entry for EMS/no-mode, 2 for FACTORY.
    """
    if cfg.TEST_MODE == "FACTORY":
        boot_1 = bootloader_firmwares[0] if len(bootloader_firmwares) > 0 else None
        boot_2 = bootloader_firmwares[1] if len(bootloader_firmwares) > 1 else None
        if not boot_1 or not boot_2:
            logging.error(
                f"FACTORY firmware flash needs two bootloader files (Boot_Loader_Firmware_FACTORY in "
                f"serial_config.enc) - got {bootloader_firmwares!r}"
            )
        return run_factory_firmware_flash(
            flash_firmware=flash_firmware,
            bootloader_firmware_1=boot_1,
            bootloader_firmware_2=boot_2,
            config_path=config_path,
            fpa_index=fpa_index,
        )

    boot = bootloader_firmwares[0] if bootloader_firmwares else None
    return run_ems_firmware_flash(
        flash_firmware=flash_firmware,
        bootloader_firmware=boot,
        config_path=config_path,
        fpa_index=fpa_index,
    )

def grade_flash_report(report, fpa_index, flash_firmware):
    """Turn one run_firmware_flash() report into {"status", "value"} for one
    station's socket (fpa_index here is a socket number, not the adapter
    instance - see the module docstring)."""
    if report.get("done") != "passed":
        failed = sorted(
            slot for slot, state in report.items() if slot != "done" and state != "OK"
        )
        return {
            "status": "FAIL",
            "value": f"Flash failed ({flash_firmware}); slots not OK: {', '.join(failed) or 'all'}",
        }

    slot = f"#{fpa_index}"
    slot_status = report.get(slot)
    if slot_status != "OK":
        return {
            "status": "FAIL",
            "value": f"Flash reported {slot}={slot_status!r} (expected OK)",
        }
    return {"status": "PASS", "value": f"{flash_firmware} programmed ({slot}=OK)"}


class SharedFwRunner:
    """
    One instance per batch run - create fresh in MainWindow.run_test() and
    hand the same instance to every StationWorker started in that batch.
    """

    def __init__(self, fpa_indices, flash_firmware, bootloader_firmwares, config_path):
        self._lock = threading.Lock()
        self._results = None  # set by _do_flash, the first time run() is called
        self._fpa_indices = fpa_indices  # {station_num: fpa_index}
        self._flash_firmware = flash_firmware
        # 1 entry (EMS/no mode) or 2 entries (FACTORY) - see
        # station_config.get_bootloader_files().
        self._bootloader_firmwares = bootloader_firmwares
        self._config_path = config_path

    def _do_flash(self):
        """
        The one flash pass for the whole batch - only ever called from run()
        with self._lock held, so it can't overlap with another call.
        """
        if not self._fpa_indices:
            self._results = {}
            return
        # GANG_PROGRAMMER_ADAPTER_INDEX, always - NOT a station's socket
        # number from self._fpa_indices (see the module docstring for why
        # that distinction matters). F_AutoProgram(0) itself covers every
        # socket that has a target connected, regardless of which one was
        # selected to get there.
        report = run_mode_aware_firmware_flash(
            self._flash_firmware, self._bootloader_firmwares, self._config_path, GANG_PROGRAMMER_ADAPTER_INDEX,
        )
        self._results = {
            num: grade_flash_report(report, fpa_index, self._flash_firmware)
            for num, fpa_index in self._fpa_indices.items()
        }

    def run(self, station_num):
        """
        Returns this station's own {"status", "value"} result from the one
        shared flash pass - flashing first if no station has yet this batch.
        """
        with self._lock:
            if self._results is None:
                self._do_flash()

        return self._results.get(
            station_num,
            {"status": "FAIL", "value": f"No gang-programmer socket configured for station {station_num}"},
        )
