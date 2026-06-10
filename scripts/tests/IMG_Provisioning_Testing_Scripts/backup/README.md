# README.md

## Requirements installation

These scripts need some external modules.

First move to [gateway/factory_mode/scripts/](gateway/factory_mode/scripts/)

To install them please use:

```Python
pip install -r requirements.txt
```

## Files

|File|Explanation / Usage|
|-|-|
|[`provisioning.py`](/gateway/factory_mode/scripts/provisioning.py)|Manages the communication with the NIC. **Must not be used directly!**|
|[`wirepas_provisioning.py`](/gateway/factory_mode/scripts/wirepas_provisioning.py)|Manages the generation, encoding and decoding of the data that are used in the provisioning and reading processes. **Must not be used directly!**|
|[`provision_img_parameters.py`](/gateway/factory_mode/scripts/provision_img_parameters.py)|This script will apply the parameters provided to the NIC and read them back.|
|[`read_img_parameters.py`](/gateway/factory_mode/scripts/read_img_parameters.py)|This script will read the parameters currently stored on the NIC.|

## General information

### Communication

The communication is performed through the meter port at a configurable baudrate (default: 9600 bauds).

### Behavior

The NIC will open a 100 ms window after every boot, during which it's possible to provision or read parameters. After this 100 ms window, it's not possible to provision or read the NIC parameters anymore.

The scripts automatically handle device reset and factory mode entry by continuously sending:
- Reset commands every 500ms (no response required)
- Challenge commands every 50ms until a challenge response is received

### Setup

It is required to have the following to provision a NIC or read its parameters:

- A PC, Running the Python Script
- A Serial USB Converter, that will connect the PC to the NIC's Meter Port
- A NIC

Then, the process to provision is the following

1. Connect the PC to the NIC using the Serial USB Converter
2. Launch the script with the right parameters
3. Wait until the provisioning is successfully performed

If anything goes wrong (e.g. missing NIC Parameters, Serial Error, etc.), the script will print an error and exit.

## `provision_img_parameters.py`

### Script help

To access the scripts' help please use the following command:

```Python
python3 provision_img_parameters.py -h
```

### Required parameters

Without this parameter, the `provision_img_parameters.py` script cannot be launched.

|Parameter|Description|Example|
|-|-|-|
|`--serial_port`|Serial port used to communicate with the NIC.|`--serial_port /dev/ttyUSB0`|

### Optional Parameters

These are optional parameters, please specify them if they are missing.

Note: At least one of the provisioning parameters must be set to be able to launch the script.

#### Serial Communication Parameters

|Parameter|Description|Example|
|-|-|-|
|`--baudrate`|Serial port baudrate (default: 9600).|`--baudrate 115200`|

#### Wirepas Network Parameters

|Parameter|Description|Example|
|-|-|-|
|`--node_address`|Virtual Node Address used by the meter for the Wirepas Network.|`--node_address 0x12347678` or `--node_address 305419896`|
|`--sink_address`|Sink Address used by the NIC for the Wirepas Network.|`--sink_address 0x1` or `--sink_address 1`|
|`--encryption_key`|Encryption Key used by the NIC for the Wirepas Network. Must be specified as a 16 bytes value.|`--encryption_key AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA`|
|`--authentication_key`|Authentication Key used by the NIC for the Wirepas Network. Must be specified as a 16 bytes value.|`--authentication_key BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB`|
|`--network_address`|Network address used by the NIC for the Wirepas Network.|`--network_address 0x123476` or `--network_address 1193046`|
|`--network_channel`|Network channel used by the NIC for the Wirepas Network.|`--network_channel 1`|
|`--node_role`|Node Role used by the sink.|`--node_role 0x11`|

#### Gateway Parameters

|Parameter|Description|Example|
|-|-|-|
|`--gateway_id`|Gateway ID string.|`--gateway_id "gateway-001"`|
|`--cellular_info_diag_interval`|Cellular info diagnostic interval in seconds.|`--cellular_info_diag_interval 60`|
|`--network_info_diag_interval`|Network info diagnostic interval in seconds.|`--network_info_diag_interval 300`|
|`--gateway_info_diag_interval`|Gateway info diagnostic interval in seconds.|`--gateway_info_diag_interval 300`|

#### Meter Interface Parameters

|Parameter|Description|Example|
|-|-|-|
|`--gw_key_enc_key`|GW Key Encryption Key. Must be specified as a 16 bytes value.|`--gw_key_enc_key CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC`|
|`--mtr_auth_key`|Meter Authentication Key. Must be specified as a 16 bytes value.|`--mtr_auth_key DDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDD`|
|`--mtr_enc_key`|Meter Encryption Key. Must be specified as a 16 bytes value.|`--mtr_enc_key EEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE`|
|`--mtr_mr_secret`|Meter MR Secret password.|`--mtr_mr_secret "meter_mr_password"`|
|`--mtr_us_secret`|Meter US Secret password.|`--mtr_us_secret "meter_us_password"`|
|`--mtr_fu_secret`|Meter FU Secret password.|`--mtr_fu_secret "meter_fu_password"`|
|`--mtr_baud_rate`|Meter communication baud rate.|`--mtr_baud_rate 9600`|
|`--mtr_dlms_mode`|Meter DLMS interface mode.|`--mtr_dlms_mode "hdlc" or --mtr_dlms_mode "wrapper"`|

#### SIM Parameters

|Parameter|Description|Example|
|-|-|-|
|`--sim1_apn`|SIM1 APN.|`--sim1_apn "internet"`|
|`--sim1_username`|SIM1 username.|`--sim1_username "user"`|
|`--sim1_password`|SIM1 password.|`--sim1_password "password"`|
|`--sim1_pdp_type`|SIM1 PDP type.|`--sim1_pdp_type "IPv6"`|
|`--sim1_pin`|SIM1 PIN.|`--sim1_pin "1234"`|
|`--sim1_puk`|SIM1 PUK.|`--sim1_puk "12345678"`|

#### MQTT Parameters

|Parameter|Description|Example|
|-|-|-|
|`--mqtt_hostname`|MQTT hostname.|`--mqtt_hostname "someinstance.prod-wirepas.com"`|
|`--mqtt_port`|MQTT port.|`--mqtt_port 8883`|
|`--mqtt_username`|MQTT username.|`--mqtt_username "mosquittouser"`|
|`--mqtt_password`|MQTT password.|`--mqtt_password "mosquittouser_password"`|
|`--mqtt_unsecure`|MQTT unsecure flag (true/false).|`--mqtt_unsecure false`|

#### Reset Parameters

|Parameter|Description|Example|
|-|-|-|
|`--reset_hour`|Reset hour (0-23).|`--reset_hour 21`|
|`--reset_minute`|Reset minute (0-59).|`--reset_minute 30`|

#### Others Parameters

|Parameter|Description|Example|
|-|-|-|
|`--ntp_addr`|NTP server address.|`--ntp_addr "2.in.pool.ntp.org"`|
|`--tz_offset_min`|Timezone offset in minutes (signed).|`--tz_offset_min 300`|
|`--keepalive_interval`|Keepalive interval in seconds.|`--keepalive_interval 300`|

### Launching the script (with minimum parameters)

```Python
python3 provision_img_parameters.py --serial_port /dev/ttyUSB0 --node_address 0x12345678 --sink_address 0x1 --gateway_id gateway-001
```

#### Advanced script launching

It's possible to create a file that stores these parameters to avoid having to write them every time.

**However, we advise not to specify the node address, sink_address & gateway_id in it, as they shall be unique.**

**We also advise not to specify the serial port inside it, if there are multiple Serial USB Converters in use to communicate with different NICs.**

Here's what the file could look like:

Name of the file: `params`

```txt
# parameters to write to the IMG for provisioning
#--serial_port /dev/ttyUSB0
#--baudrate 19200
--encryption_key 11223344556677881122334455667788
--authentication_key 11223344556677881122334455667788
--network_address 0xABABAB
--network_channel 1
#--node_address 12321
--node_role 0x11
--gw_key_enc_key 11223344556677881122334455667788
--mtr_auth_key 11223344556677881122334455667788
--mtr_enc_key 11223344556677881122334455667788
--mtr_mr_secret mr_password
--mtr_us_secret us_password
--mtr_fu_secret fu_password
--mtr_baud_rate 9600
--mtr_dlms_mode hdlc
#--gateway_id gateway-001
#--sink_address 1
--sim1_apn internet
--sim1_username user
--sim1_password password
--sim1_pdp_type IPv6
--sim1_pin 1234
--sim1_puk 12345678
--mqtt_hostname someinstance.prod-wirepas.com
--mqtt_port 8883
--mqtt_username mosquittouser
--mqtt_password mosquittouser_password
--mqtt_unsecure false
--cellular_info_diag_interval 60
--network_info_diag_interval 300
--gateway_info_diag_interval 300
--ntp_addr 2.in.pool.ntp.org
--tz_offset_min 330
--keepalive_interval 300
--reset_hour 21
--reset_minute 30
```

Then, the script can be executed like this:

```Python
python3 provision_img_parameters.py @params --serial_port /dev/ttyUSB0 --node_address 0x12345678 --sink_address 0x1
```

## `read_img_parameters.py`

### Script help

To access the scripts' help please use the following command:

```Python
python3 read_img_parameters.py -h
```

#### Required parameters

Without this parameter, the `read_img_parameters.py` script cannot be launched.

|Parameter|Description|Example|
|-|-|-|
|`--serial_port`|Serial port used to communicate with the NIC.|`--serial_port /dev/ttyUSB0`|

#### Optional parameters

|Parameter|Description|Example|
|-|-|-|
|`--baudrate`|Serial port baudrate (default: 9600).|`--baudrate 19200`|

### Launching the script

```Python
python3 read_img_parameters.py --serial_port /dev/ttyUSB0
```

### Launching the script with custom baudrate

```Python
python3 read_img_parameters.py --serial_port /dev/ttyUSB0 --baudrate 115200
```

## Security Notes

- Encryption keys and passwords are partially masked in logs for security
- Only the last few characters of sensitive data are displayed in output
