# Smart Manufacturing Suite – IMG Stage 2 (8-CH, DEC)

Production-jig test application (Tkinter GUI) for IMG Stage 2. It scans device serial numbers via barcode scanners on COM ports, drives an Advantech DAQ card (USB-4704) for digital output / analog input tests, validates voltages against limits, and logs results to Excel.

## Folder layout

```
SmartManufacturingSuite.py   Main application
serial_config.json           Plain-text config (editable source)
serial_config.enc            Encrypted config actually read by the app
scripts/tests/               staticDO.py, InstantAI.py (DAQ tests)
scripts/Automation/BDaq/     Advantech BioDAQ Python wrapper
scripts/profile/             Advantech device profile XMLs
BUILD/                       Packaged .exe + config (IMG_STAGE_2_V1.0.0.4_8_CH_DEC.exe)
```

Generated at runtime next to the script/exe:
- `Test Result Excel File/Test_Result_<date>/<date>_IMG_TEST_RESULT.xlsx`
- `Log files/Log_file_<date>/` (`action_log.txt`, `<date>_program_log.txt`)

## Requirements

- Windows 10/11, Python 3.12
- Advantech DAQNavi / BioDAQ driver installed (needed for the USB-4704 card)
- USB barcode scanners / optical ports exposed as COM ports

```
pip install -r requirements.txt
python SmartManufacturingSuite.py
```

Or just run the prebuilt exe in `BUILD/` (keep `serial_config.enc` in the same folder).

## Configuration

The app reads **`serial_config.enc`** from the same folder as the script/exe (not the working directory). `serial_config.json` is the readable version of the same settings. If the `.enc` file is missing or cannot be decrypted, the app shows an error / uses defaults.

### Keys

| Key | Example | Description |
|---|---|---|
| `SCANNER_COM1`–`SCANNER_COM4` | `COM136` | COM port of the barcode scanner for stations 1–4 (9600 baud, trigger `*T`) |
| `OPTICAL_COM1`–`OPTICAL_COM4` | `COM136` | COM port of the optical probe for stations 1–4 |
| `DAC_COM` | `USB-4704,BID#0` | Advantech DAQ device description (card model, board ID) |
| `MAX_RETRIE` | `3` | Max scan retries (key spelled as in code) |
| `TEST_TIMEOUT` | `15` | Per-test timeout in seconds (monitor cancels after timeout + 10 s) |
| `RETRY_DELA` | `2` | Delay between retries in seconds (key spelled as in code) |
| `Firmware_version` | `4.2.0.0` | Expected firmware version |
| `min_/max_Boost_voltage` | `3.65` / `4.2` | Boost voltage pass range (V) |
| `min_/max_super_cap_voltage` | `1.6` / `2.7` | Super-cap voltage range after charge (V) |
| `min_/max_Dis_super_cap_voltage` | `-0.2` / `0.5` | Super-cap voltage range after discharge (V) |
| `min_/max_Discharge_voltage` | `0` / `3.0` | Discharge output voltage range (V) |

Note: the key names `MAX_RETRIE` and `RETRY_DELA` are intentionally truncated; the code looks them up with exactly these names.

### Current values (`serial_config.json`)

```json
{
    "SCANNER_COM1": "COM136", "SCANNER_COM2": "COM134",
    "SCANNER_COM3": "COM133", "SCANNER_COM4": "COM135",
    "OPTICAL_COM1": "COM136", "OPTICAL_COM2": "COM134",
    "OPTICAL_COM3": "COM133", "OPTICAL_COM4": "COM135",
    "DAC_COM": "USB-4704,BID#0",
    "MAX_RETRIE": 2,
    "TEST_TIMEOUT": 15,
    "RETRY_DELA": 2,
    "Firmware_version": "4.2.0.0",
    "min_Boost_voltage": 3.65,   "max_Boost_voltage": 4.2,
    "min_Dis_super_cap_voltage": -0.2, "max_Dis_super_cap_voltage": 0.5,
    "min_super_cap_voltage": 1.6, "max_super_cap_voltage": 2.7,
    "min_Discharge_voltage": 0,  "max_Discharge_voltage": 3.0
}
```

### Encrypted file format

`serial_config.enc` = 16-byte random salt + Fernet token of the JSON text. The key is derived with PBKDF2-HMAC-SHA256 (390,000 iterations) from the passphrase defined in `SmartManufacturingSuite.py` (`PASSWORD`). To change settings: edit `serial_config.json`, then re-encrypt it with the same scheme and replace `serial_config.enc` (in both the project root and `BUILD/`).

## Station mapping

Each station uses two DAQ analog channels: `Channel (station-1)*2` = super-cap voltage, `Channel (station-1)*2+1` = boost / discharge voltage. Out-of-range readings raise connectivity / discharge alarms for operator confirmation before retry.

## Troubleshooting

- **Config error on start**: `serial_config.enc` missing from the exe/script folder, or encrypted with a different passphrase.
- **Scanner not responding**: check COM numbers in Device Manager and update `SCANNER_COMx`.
- **DAQ not found**: confirm DAQNavi driver is installed and `DAC_COM` matches the card name/board ID.
