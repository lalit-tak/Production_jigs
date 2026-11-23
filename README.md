# Better Meter Jig - Production Test Tool

A PyQt5 desktop application that runs the production test sequence on Better Meter
units. It drives **two stations in parallel** from one Advantech DAQ card and one
gang-programmer adapter: it scans the serial number, powers the meter, checks
voltage rails, flashes firmware, runs protocol tests over the optical COM port,
calibrates the RTC, checks the relays, and logs every result to Excel (with
optional upload to S3).

## Project layout

| Path | Purpose |
|---|---|
| `main.py` | Application entry point and main window (start here) |
| `station_config.py` | **All wiring and limits**: COM ports, DAQ channels, DO bits, voltage windows, expected values, timeouts |
| `serial_config.enc` | Encrypted per-bench overrides of `station_config.py` (see [Configuration](#configuration)) |
| `test_sequence.py` | Ordered list of tests, filtered by EMS/FACTORY mode, wrapped with timeouts |
| `test_impl.py` | Real implementations of each test |
| `test_stubs.py` | Simulated tests (used when `ALLOW_SIMULATION = True`) |
| `test_timeout.py` | Per-test deadline runner |
| `worker.py` | Per-station worker thread that executes the sequence |
| `station_panel.py` | Per-station UI panel |
| `shared_ai.py`, `shared_di.py`, `shared_do.py` | Shared DAQ runners (one read/write serves both stations) |
| `shared_fw.py`, `shared_step.py` | Shared firmware-flash runner and step synchronisation |
| `FirmwareFlash.py`, `MainFirmwareFlash.py` | EMS (1 bootloader) and FACTORY (2 bootloaders, merged) flashing |
| `excel_logger.py` | Excel result workbook writer |
| `s3_uploader.py` | Uploads Excel and text logs to S3 |
| `scripts/` | Meter protocol tests (memory, version, relay, NIC, RTC, ...), `utils/` (serial, DAQ), `Automation/BDaq` (Advantech SDK wrapper) |
| `firmware_flash_files/` | Firmware/bootloader images, gang-programmer DLLs and `.cfg`/`.ini` |
| `Document/` | Test plan (`BETTER_METER_TEST_PLAN_R00.xlsx`) |
| `Build/` | Built standalone `.exe` |
| `main_old.py`, `station_panel_old.py` | Previous versions, kept for reference |

## Prerequisites

- Windows 10/11 (the gang-programmer DLLs and DAQ driver are Windows-only)
- Python 3.8+
- **Advantech DAQNavi driver** with the USB-4716 visible in Advantech Navigator
  (default device string `USB-4716,BID#0`)
- Gang programmer USB adapter connected (`GangProARM-FPAsel.dll` in `firmware_flash_files/`)
- Meter optical probes and (optionally) barcode scanners and RTC calibrators on COM ports

## Installation

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## Running

```powershell
python main.py
```

Logs go to `Log files/<date>_program_log.txt`; Excel results go to
`Test Result Excel File/`. Both folders are created next to the script (or next to
the `.exe` when built).

### Building the .exe

```powershell
pip install pyinstaller
pyinstaller --onefile --noconsole main.py
```

Place `serial_config.enc`, `firmware_flash_files/` and `scripts/profile/` next to the
built `.exe`. `serial_config.enc` is located relative to the executable, not the
PyInstaller temp folder.

## Configuration

Configuration has two layers. Values in `station_config.py` are the defaults;
`serial_config.enc` overrides them at startup via `load_serial_config()`. If the file
is missing or fails to decrypt, the tool logs a message and keeps the defaults.

> Entries marked `CONFIRM` in `station_config.py` are bench-wiring assumptions.
> Verify them against the actual harness before trusting a PASS.

### 1. `serial_config.enc` (per-bench overrides)

An encrypted JSON file: a 16-byte salt followed by Fernet-encrypted JSON (key derived
with PBKDF2-SHA256). The app only decrypts it. To change values, edit the JSON and
re-encrypt it with `station_config.encrypt_serial_config(config, path)`.

Example (decrypted) content:

```json
{
  "Mode": "EMS",
  "OPTICAL_COM1": "COM3",
  "OPTICAL_COM2": "COM4",
  "SCANNER_COM1": "COM5",
  "SCANNER_COM2": "COM6",
  "CALIBRATOR_COM1": "COM7",
  "CALIBRATOR_COM2": "COM8",
  "DAC_COM": "USB-4716,BID#0",
  "Gang_Programming_Station_Map": { "Station1": "#1", "Station2": "#2" },
  "Gang_Programming_Code_File": "2_4_better_GangConfig.cfg",
  "Flash_Firmware_Main": "17404_T0005.bin",
  "Boot_Loader_Firmware": ["gp_1p_bootloader_PCB78_V001_Generic_4.8_BM_2.0_KM35_flash.bin"],
  "Firmware_version": "0.0.0.0",
  "Live_version": 17404,
  "Tool_version": 5,
  "TEST_TIMEOUT": 20.0,
  "Serial_Number_Length": 12,
  "VOLTAGE_TESTS": {
    "test_6v": { "min": 5.70, "max": 6.30 },
    "test_3_3v": { "min": 3.135, "max": 3.465 }
  }
}
```

(Values above are illustrative; use the real ones for your bench.)

| Key | Overrides | Notes |
|---|---|---|
| `Mode` | `TEST_MODE` | `EMS` or `FACTORY`; filters the test sequence. Missing/invalid runs every test |
| `OPTICAL_COM<n>` | `STATION_COM_PORTS` | Meter protocol port for station *n* |
| `SCANNER_COM<n>` | `STATION_SCANNER_PORTS` | Barcode scanner; empty skips scanning and uses the typed serial number |
| `CALIBRATOR_COM<n>` | `STATION_CALIBRATOR_PORTS` | RTC/PPM frequency counter; without it the RTC tests fail with a clear message |
| `DAC_COM` | `STATION_DAQ_DEVICES` | One Advantech device shared by both stations |
| `Gang_Programming_Station_Map` | `STATION_FPA_INDEX` | Socket (`"#1"`...) per station on the shared gang-programmer adapter |
| `Gang_Programming_Code_File` | `FIRMWARE_CONFIG` | `.cfg` file in `firmware_flash_files/` |
| `Flash_Firmware_Main` | `FIRMWARE_FILE` | Firmware image in `firmware_flash_files/` |
| `Boot_Loader_Firmware` | `BOOTLOADER_FILES_*` | List (or comma-separated string): **exactly 1 file for EMS, exactly 2 for FACTORY**; a wrong count is logged and ignored |
| `Firmware_version` | `FIRMWARE_VERSION` | Reference version string |
| `Live_version` / `Tool_version` | `LIVE_VERSION` / `TOOL_VERSION` | Expected version codes reported by the meter |
| `TEST_TIMEOUT` | `DEFAULT_TIMEOUT` | Seconds, for tests without an entry in `TEST_TIMEOUTS` |
| `Serial_Number_Length` | `SERIAL_NUMBER_LENGTH` | Exact length required (too short or too long fails) |
| `VOLTAGE_TESTS` | `VOLTAGE_TESTS` min/max | Only `min`/`max` can be overridden; channels stay hardcoded. Unknown keys are skipped with a warning |

### 2. `station_config.py` (defaults, edited in code)

| Setting | Meaning |
|---|---|
| `STATION_COM_PORTS`, `STATION_SCANNER_PORTS`, `STATION_CALIBRATOR_PORTS` | COM ports per station (1 and 2) |
| `STATION_DAQ_DEVICES` | DAQ device per station (default `USB-4716,BID#0`) |
| `STATION_DO_PORTS` | Digital-output port driving each station's relay bank |
| `DI_PORT`, `STATION_RELAY_DI_BIT` | Digital-input port and per-station bit used to physically confirm relay state |
| `STATION_AI_BASE_CHANNEL` | First analog channel per station (ch0-5 station 1, ch6-11 station 2) |
| `VOLTAGE_TESTS` | Per-test channel offset and accepted min/max volts |
| `VOLTAGE_TEST_ABSOLUTE_CHANNELS` | Absolute channels for `power_enable` (12/13), `efuse` (14/15), `main_battery_voltage` (**unconfirmed**) |
| `SHARED_AI_GROUPS` | Tests that share one analog snapshot |
| `DO_STEPS`, `SHARED_DO_STEPS`, `SHARED_DO_VALUES` | Digital-output steps and the literal port values written (active-low) |
| `DO_SETTLE_SECONDS` | Wait after a DO write before reading voltages |
| `EXPECTED_LIVE_VERSION`, `EXPECTED_INT_VERSION` | Version codes the meter must report |
| `EXPECTED_VALUES` | Payload values each protocol test must return to PASS |
| `TEST_TIMEOUTS`, `DEFAULT_TIMEOUT_RESULT`, `TEST_TIMEOUT_RESULTS` | Per-test deadlines and the result reported on overrun (default FAIL, which stops the station) |
| `ALLOW_SIMULATION` | `True` falls back to simulated PASS results when hardware is absent. **Keep `False` on the bench** |

### Firmware files (`firmware_flash_files/`)

Firmware, bootloader and `.cfg` file names configured above are resolved inside this
folder. `FPAs-setup.ini` and the gang-programmer DLLs also live here.

## Test modes

| Mode | Bootloaders | Behaviour |
|---|---|---|
| `EMS` | 1 | Flashes the test firmware image |
| `FACTORY` | 2 (merged at separate offsets) | Flashes the main firmware image |
| *(unset)* | generic `BOOTLOADER_FILE` | Runs the full sequence |

`TEST_MODE` is read when `test_sequence.py` is imported, so `load_serial_config()` must
run first (`main.py` already does this).

## S3 log upload

`s3_uploader.py` uploads each batch's Excel workbook and previous days' text logs to
the configured bucket under `Excel_log/` and `text_log/`.

> **Security warning:** `s3_uploader.py` currently contains AWS access keys in
> plain text, and `station_config.py` contains the `serial_config.enc` password.
> Rotate the AWS key, move credentials to environment variables or an AWS profile,
> and do not share this folder or commit it to a repository as is.

## Troubleshooting

- **`serial_config.enc not found` / `Could not decrypt`** in the log: the tool is running on the defaults in `station_config.py`.
- **DAQ unavailable**: check the USB-4716 in Advantech Navigator and that `STATION_DAQ_DEVICES` matches its name.
- **Test shows `TIMEOUT - no response`**: raise its entry in `TEST_TIMEOUTS`, and check the COM port and cabling.
- **Wrong tests shown**: check `Mode` in `serial_config.enc`.
