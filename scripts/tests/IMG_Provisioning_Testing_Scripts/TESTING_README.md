# TESTING_README.md

## Introduction

This Python Script handles the Embedded Gateway Testing (Cellular, SIM, GPIOs, External Flash and RF).

The focus here is on the script usage.

## Requirements

### Python modules

This script needs some external modules.

First move to [/factory_mode/scripts](/factory_mode/scripts)

To install them please use:

```Python
pip install -r requirements.txt
```

### `test_router_app`

The Wirepas `test_router_app` must be flashed onto a separate NIC to be able to perform the RF testing of the Embedded Gateway.

For more information, please have a look at the `test_router_app`'s `README.md` file.

## General information

### Communication

The communication is performed through the meter port by default at 9600 bauds (it is configurable when launching the script).

### Setup

It is required to have the following to perform the Embedded Gateway testing:

- A PC, Running the Python Script
- A Serial USB Converter, that will connect the PC to the Embedded Gateway's Meter Port
- An Embedded Gateway

Then, the process to test the Embedded Gateway is the following

1. Connect the `Event pin` and the `Power Fail pin` using a wire, for the GPIOs testing
2. Insert the 2 SIM cards in the Embedded Gateway
3. Connect the power supply to the Embedded Gateway
4. Flash a node with the `test_router_app` application and configure it properly
5. Flash the Embedded Gateway's sink with the `emb_gw_sink_app` application
6. Flash the Embedded Gateway with its firmware
7. Connect the PC to the Embedded Gateway using the Serial USB Converter
8. Launch the script with the correct parameters
9. Wait until the testing summary is printed

## `testing.py`

### Script help

To access the scripts' help please use the following command:

```Python
python3 testing.py -h
```

### Required Parameters

|Parameter|Description|Example|
|-|-|-|
| `--serial_port` | Serial port used to communicate with the NIC.|`--serial_port /dev/ttyUSB0`|
| `--test_router_address` | Test Router Address.|`--test_router_address 0x12347678` or `--test_router_address 305419896`|
| `--network_address` | Network address used by the NIC during the RF testing.|`--network_address 0x123476` or `--network_address 1193046`|
| `--network_channel` | Network channel used by the NIC during the RF testing.|`--network_channel 1`|
| `--encryption_key` | Encryption Key used by the NIC during the RF testing. Must be specified as a 16 bytes value.|`--encryption_key AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA`|
| `--authentication_key` | Authentication Key used by the NIC during the RF testing. Must be specified as a 16 bytes value.|`--authentication_key BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB`|

### Optional Parameters

These parameters are optional, but must be set if needed.

| Parameter         | Description                                                  | Example                                      |
|-------------------|--------------------------------------------------------------|----------------------------------------------|
| `--baudrate`      | Baudrate used to communicate with the NIC.                  | `--baudrate 19200`                            |
| `--sim1_user`     | SIM1 user name.                                              | `--sim1_user myusername`                     |
| `--sim1_pwd`      | SIM1 password.                                               | `--sim1_pwd mypassword`                      |
| `--sim1_apn`      | SIM1 APN.                                                    | `--sim1_apn internet`                        |
| `--sim1_pin`      | SIM1 PIN.                                                    | `--sim1_pin 1234`                            |
| `--sim1_puk`      | SIM1 PUK.                                                    | `--sim1_puk 12345678`                        |
| `--sim2_user`     | SIM2 user name.                                              | `--sim2_user myusername`                     |
| `--sim2_pwd`      | SIM2 password.                                               | `--sim2_pwd mypassword`                      |
| `--sim2_apn`      | SIM2 APN.                                                    | `--sim2_apn internet`                        |
| `--sim2_pin`      | SIM2 PIN.                                                    | `--sim2_pin 5678`                            |
| `--sim2_puk`      | SIM2 PUK.                                                    | `--sim2_puk 87654321`                        |

### Launching the script (with the required parameters)

```Python
python3 testing.py --serial_port /dev/ttyUSB0  --encryption_key 33333333333333333333333333333333 --authentication_key 44444444444444444444444444444444 --network_address 0xF0EE0F --network_channel 1 --test_router_address 1
```

#### Advanced script launching

It's possible to create a file that stores these parameters to avoid having to write them every time.

**However, we advise not to specify the serial port inside it, if there are multiple Serial USB Converters in use to communicate with different Embedded Gateways.**

Here's what the file could look like:

Name of the file: `testing_parameters`

```txt
--encryption_key
33333333333333333333333333333333
--authentication_key
44444444444444444444444444444444
--network_address
0xF0EE0F
--network_channel
1
--test_router_address
1
```

Then, the script can be executed like this:

```Python
python3 testing.py --serial_port /dev/ttyUSB0 @testing_parameters
```
