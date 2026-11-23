# IMG Stage 2 – 16 Channel Production Jig (Smart Manufacturing Suite)

Windows desktop application (Tkinter) that runs production tests on up to 16 IMG units in parallel. It uses barcode scanners and optical probes over serial COM ports, and an Advantech USB-4704 DAQ card for analog and digital I/O. Results are logged to a daily Excel file.

## Project Structure

```
.
├── SmartManufacturingSuite.py      # Main application (UI, test orchestration, Excel logging)
├── serial_config.json              # Plain-text config (source for the encrypted config)
├── serial_config.enc               # Encrypted config actually loaded by the app
├── requirements.txt                # Python dependencies
├── scripts/
│   ├── tests/
│   │   ├── InstantAI.py            # Analog input (voltage) tests
│   │   └── staticDO.py             # Digital output control
│   ├── Automation/BDaq/            # Advantech BDaq Python wrapper
│   └── profile/                    # Advantech device profile XML files
└── BUILD/
    ├── IMG_STAGE_2_V1.0.0.4_16_CH_DEC.exe   # Packaged executable
    ├── serial_config.json
    └── serial_config.enc
```

## Requirements

- Windows 10/11
- Python 3.12 or 3.13 (the repo contains `.pyc` files for both)
- Advantech DAQNavi / BioDAQ driver installed (needed by `scripts/Automation/BDaq`)
- Advantech USB-4704 connected (device string `USB-4704,BID#0`)
- Serial scanners and optical probes connected and visible as COM ports

Install the Python dependencies:

```bash
pip install -r requirements.txt
```

## Running

From source:

```bash
python SmartManufacturingSuite.py
```

Or run the packaged build: `BUILD/IMG_STAGE_2_V1.0.0.4_16_CH_DEC.exe`. Keep `serial_config.enc` in the same folder as the executable.

## Configuration

The app loads `serial_config.enc` at startup (`CONFIG_FILE_NAME_ENC` in `SmartManufacturingSuite.py`). The file is encrypted with Fernet, using a PBKDF2-derived key. `serial_config.json` is the readable version for editing. If the `.enc` file is missing, the app shows an error asking you to create it.

### Current `serial_config.json`

```json
{
    "SCANNER_COM1": "COM136",
    "SCANNER_COM2": "COM134",
    "SCANNER_COM3": "COM133",
    "SCANNER_COM4": "COM135",
    "OPTICAL_COM1": "COM136",
    "OPTICAL_COM2": "COM134",
    "OPTICAL_COM3": "COM133",
    "OPTICAL_COM4": "COM135",
    "DAC_COM": "USB-4704,BID#0",
    "MAX_RETRIE": 2,
    "TEST_TIMEOUT": 15,
    "RETRY_DELA": 2,
    "Firmware_version": "4.2.0.0",
    "min_Boost_voltage": 3.65,
    "max_Boost_voltage": 4.2,
    "min_Dis_super_cap_voltage": -0.2,
    "max_Dis_super_cap_voltage": 0.5,
    "min_super_cap_voltage": 1.6,
    "max_super_cap_voltage": 2.7,
    "min_Discharge_voltage": 0,
    "max_Discharge_voltage": 3.0
}
```

### Config parameters

| Key | Value | Description |
|---|---|---|
| `SCANNER_COM1` – `SCANNER_COM4` | `COM136`, `COM134`, `COM133`, `COM135` | COM ports of the barcode scanners |
| `OPTICAL_COM1` – `OPTICAL_COM4` | `COM136`, `COM134`, `COM133`, `COM135` | COM ports of the optical probes. They currently use the same ports as the scanners. |
| `DAC_COM` | `USB-4704,BID#0` | Advantech DAQ device description (model, board ID) |
| `MAX_RETRIE` | `2` | Maximum retries per test. The key is spelled this way in the file. |
| `TEST_TIMEOUT` | `15` | Per-test timeout in seconds |
| `RETRY_DELA` | `2` | Delay between retries in seconds. The key is spelled this way in the file. |
| `Firmware_version` | `4.2.0.0` | Expected firmware version. It is shown in the UI and used for the firmware download and version tests. |
| `min_Boost_voltage` / `max_Boost_voltage` | `3.65` / `4.2` V | Pass range for the boost voltage |
| `min_Dis_super_cap_voltage` / `max_Dis_super_cap_voltage` | `-0.2` / `0.5` V | Pass range for the super-cap voltage after discharge |
| `min_super_cap_voltage` / `max_super_cap_voltage` | `1.6` / `2.7` V | Pass range for the charged super-cap voltage |
| `min_Discharge_voltage` / `max_Discharge_voltage` | `0` / `3.0` V | Pass range for the discharge voltage |

### Updating the config

1. Edit `serial_config.json`. Change the COM ports to match Device Manager.
2. Regenerate `serial_config.enc` from it with the project's encryption routine. The app reads only the `.enc` file.
3. Copy the updated `.enc` file next to the executable in `BUILD/`.

Keep the COM port names and `serial_config.json` private. Do not share them outside the production team.

## Output

- A daily results workbook named `<date>_IMG_TEST_RESULT.xlsx` is written to the Excel folder defined in the script.
- Application logs are written through Python `logging`.

## Tests

The test names visible in the app include Test Firmware Download, NIC Status Test, Memory Test and Live Version Test. Voltage checks are in `scripts/tests/InstantAI.py`, and digital output control is in `scripts/tests/staticDO.py`.

## Troubleshooting

- **"Please create serial_config.enc"**: the encrypted config is missing. Place it next to the app.
- **COM port errors**: check the port numbers in Device Manager and update the config.
- **DAQ not found**: install the Advantech driver and check that `DAC_COM` matches the connected device.
