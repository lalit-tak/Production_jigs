# IMG Stage 1 – Smart Manufacturing Suite (Deck 1)

Production-jig software for Stage 1 testing of the IMG (Intelligent Meter Gateway) card. A tkinter GUI drives up to **4 stations** in parallel: it scans each PCB's serial number, powers/measures the board through an Advantech DAQ card, flashes firmware, reads back the version parameters over the optical port, then logs results to Excel/text and uploads them to S3.

- Application version (UI header): `V1.0.0.6`
- Platform: **Windows only** (uses `win32gui`, `win32com`, the Gang programmer DLL and `ResearchDownload.exe`)
- Python: 3.12

## Test flow (per station)

Task names follow the result columns written to the EMS text file:

1. BOOT mode initialization / BOOT mode on
2. Power rail checks – Buck output, LDO output, 1V8, Super-cap voltage (min/max limits from config)
3. IMG SINK programming (Gang programmer, `FirmwareFlash.py`)
4. N58 modem programming (`ResearchDownload` with the `.pac` image)
5. BOOT mode off, module supply on
6. Version check over optical port – GW Core / Main / Sink App / Modem firmware / Meter Lib versions
7. Module supply off, super-cap discharge and discharged-voltage check

Overall PASS/FAIL is recorded per serial number.

## Directory layout

| Path | Purpose |
|-|-|
| `SmartManufacturingSuite.py` | Main application (GUI, test orchestration, logging) – **entry point** |
| `FirmwareFlash.py` | Gang programmer (`GangProARM-FPAsel.dll`) wrapper via `ctypes`; flashes up to 8 channels |
| `s3_uploader.py` | Uploads batch Excel workbooks and daily text logs to S3 |
| `serial_config.enc` | **Encrypted** runtime configuration (see [Configuration](#configuration)) |
| `firmware_flash_files/` | Gang programmer DLLs, `FPAs-setup.ini`, `img_lastused_gparm*.cfg`, the `.hex` sink image and the N58 `.pac` image |
| `firmware_flash_files/dependency/RESEARCHDOWNLOAD_R22.19.1701/` | Vendor ResearchDownload tool used for N58 modem flashing |
| `scripts/Automation/BDaq/` | Advantech BDaq Python wrapper |
| `scripts/profile/` | Advantech device profiles (`DemoDevice.xml`, `PCI-*.xml`) |
| `scripts/tests/InstantAI.py`, `staticDO.py` | DAQ analog-input readings and digital-output control (default device `USB-4716,BID#0`) |
| `scripts/tests/IMG_Provisioning_Testing_Scripts/` | NIC provisioning / parameter read scripts (has its own README and requirements) |
| `Production_jigs/` | Git metadata only (incomplete clone) |

Folders created automatically at runtime next to the app:

| Folder | Content |
|-|-|
| `Log files/Log_file_<YYYY-MM-DD>/` | `<date>_program_log.txt` (DEBUG) and `action_log.txt` |
| `Test Result Excel File/Test_Result_<date>/` | Per-batch `<date>_<time>_IMG_TEST_RESULT.xlsx` (deleted after a successful S3 upload) |
| `EMS Test Result/<date>/` | `<serial>_<RESULT>.txt` per board |

## Prerequisites

1. Windows 10/11 and Python 3.12.
2. Advantech **DAQNavi** driver and the **USB-4716** DAQ device (device id `USB-4716,BID#0`).
3. USB-serial adapters for barcode scanners and optical probes (4 each).
4. Gang programmer hardware (FPA adapters) with `GangProARM-FPAsel.dll` – 64/32-bit must match the Python interpreter.
5. Network access to AWS S3 (region `ap-south-1`) for log upload.

## Installation

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Running

```powershell
python SmartManufacturingSuite.py
```

Run from this directory – config and firmware paths are relative to it (`firmware_flash_files\...`). On start-up the app loads `serial_config.enc`, uploads any pending logs from previous days, then waits for serial numbers to be scanned. Use **Run**, **Stop** and **New Batch** in the toolbar.

`FirmwareFlash.py` is imported by the suite (`run_firmware_flash(flash_firmware, config_path)`); it returns a dict like `{"#1": "OK"/"failed", ..., "done": "passed"/"failed"}`.

## Configuration

All jig settings live in **`serial_config.enc`**: a Fernet-encrypted JSON file. Layout: first 16 bytes = PBKDF2 salt, remainder = Fernet token. Key derivation is PBKDF2-HMAC-SHA256 (390000 iterations) from a passphrase defined in `SmartManufacturingSuite.py` (`self.PASSWORD`). To change a setting, decrypt, edit the JSON, and re-encrypt with the same scheme.

### Keys

| Key | Type | Description |
|-|-|-|
| `SCANNER_COM1` … `SCANNER_COM4` | string | COM port of the barcode scanner for stations 1–4 (e.g. `"COM5"`) |
| `OPTICAL_COM1` … `OPTICAL_COM4` | string | COM port of the optical probe for stations 1–4 |
| `DAC_COM` | string | Advantech device description, default `USB-4716,BID#0` |
| `Firmware_version` | string | Expected firmware version shown in the UI (default `0.0.0.0`) |
| `Flash_Firmware` | string | Sink firmware file name inside `firmware_flash_files/` (e.g. the `.hex`) |
| `Gang_Programming_Code_File` | string | Gang programmer code file name |
| `core_ver`, `main_ver`, `sink_app_ver`, `modem_firmware_ver`, `meter_lib_ver` | string | Expected versions checked at "Version Check" (default `N/A`) |
| `min_buck_voltage` / `max_buck_voltage` | float | Buck output limits (V) |
| `min_ldo_output` / `max_ldo_output` | float | LDO output limits (V) |
| `min_v8_voltage` / `max_v8_voltage` | float | 1V8 rail limits (V) |
| `min_super_cap_voltage` / `max_super_cap_voltage` | float | Super-cap charged voltage limits (V) |
| `min_super_cap_discharge_voltage` / `max_super_cap_discharge_voltage` | float | Super-cap discharged voltage limits (V) |
| `TEST_TIMEOUT` | int | Per-test timeout in seconds (default `30`) |
| `Gang_Programming_Station_Map` | object | Maps `Station1`…`Station4` to Gang channels (defaults `#1`, `#2`, `#4`, `#5`) |

### Example (decrypted) content

```json
{
  "SCANNER_COM1": "COM3",
  "SCANNER_COM2": "COM4",
  "SCANNER_COM3": "COM5",
  "SCANNER_COM4": "COM6",
  "OPTICAL_COM1": "COM7",
  "OPTICAL_COM2": "COM8",
  "OPTICAL_COM3": "COM9",
  "OPTICAL_COM4": "COM10",
  "DAC_COM": "USB-4716,BID#0",
  "Firmware_version": "4.2.0.0",
  "Flash_Firmware": "final_image_emb_gw_sink_app_v_4.2.0.0.hex",
  "Gang_Programming_Code_File": "combine_polaris_IMG_file_v2.5.4_release.pac",
  "core_ver": "<expected>",
  "main_ver": "<expected>",
  "sink_app_ver": "<expected>",
  "modem_firmware_ver": "<expected>",
  "meter_lib_ver": "<expected>",
  "min_buck_voltage": 0.0,
  "max_buck_voltage": 0.0,
  "min_ldo_output": 0.0,
  "max_ldo_output": 0.0,
  "min_v8_voltage": 0.0,
  "max_v8_voltage": 0.0,
  "min_super_cap_voltage": 0.0,
  "max_super_cap_voltage": 0.0,
  "min_super_cap_discharge_voltage": 0.0,
  "max_super_cap_discharge_voltage": 0.0,
  "TEST_TIMEOUT": 30,
  "Gang_Programming_Station_Map": {
    "Station1": "#1",
    "Station2": "#2",
    "Station3": "#4",
    "Station4": "#5"
  }
}
```

The file names, COM ports and `<expected>`/0.0 values above are placeholders – the real values are in your `serial_config.enc`.

### Other fixed settings (in code)

| Setting | Where | Value |
|-|-|-|
| Optical/serial baud rate | `SmartManufacturingSuite.py` (`self.baudrate`) | 19200 |
| Scanner baud rate / trigger | `SerialScanner` | 9600, `*T` |
| Gang config file | `firmware_flash_files/img_lastused_gparm.cfg` | per-channel programming options |
| Gang adapter setup | `firmware_flash_files/FPAs-setup.ini` | FPA adapter list |
| S3 region / bucket | `s3_uploader.py` | `ap-south-1` / `po-production-sms-unit` |
| S3 key prefix | `s3_uploader.py` (`S3_KEY_PREFIX`) | `SURBHI/IMG_JIG/STAGE_01/…` |

### S3 upload

`s3_uploader.py` uploads the batch workbook after every batch and sweeps old daily text logs at start-up (archived to `Log files/Uploaded/`). Keys include the PC name so multiple jigs don't overwrite each other.

> **Security warning:** `s3_uploader.py` currently has the AWS access key and secret **hard-coded**, and the config passphrase is hard-coded in `SmartManufacturingSuite.py`. Move them to environment variables or an AWS profile / secrets store, rotate the exposed key, and don't share this folder or commit it to Git as-is.

## Troubleshooting

| Symptom | Check |
|-|-|
| "Error while decrypting serial_config.enc" | Wrong passphrase / corrupted file; the app then starts with empty COM ports |
| `DLL not found` / `Firmware not found` | Files missing in `firmware_flash_files/`; run from the project directory |
| All channels `failed` after flash | No "D O N E" in programmer report – check FPA adapters, power, `.cfg` |
| DAQ errors | DAQNavi driver installed; device name matches `DAC_COM` |
| S3 upload failures | Network/credentials; workbooks stay on disk and retry at next batch/start-up |
