import argparse
from colorama import Fore, Style
import queue
import logging
import factory_mode
import wirepas_provisioning
from struct import pack, unpack
import sys

from wirepas_provisioning import WirepasProvisioning
from threading import Thread, Event
from struct import pack, unpack
from enum import Enum, IntEnum
from time import sleep
import time
from threading import Timer


class SignalAcceptanceCriteria:
    RSRP_MIN_DBM = -95
    RSRQ_MIN_DB = -20


class WirepasParams:
    KEY_SIZE = 16
    MINIMUM_NETWORK_ADDRESS = 1
    MAXIMUM_NETWORK_ADDRESS = 0xFFFFFF
    MINIMUM_NETWORK_CHANNEL = 1
    MAXIMUM_NETWORK_CHANNEL = 12
    MINIMUM_NODE_ADDRESS = 1
    MAXIMUM_NODE_ADDRESS = 0xFFFFFFFB

    def validate_key(key: str) -> bytes:
        byte_data = bytes.fromhex(key)
        if len(byte_data) != WirepasParams.KEY_SIZE:
            raise argparse.ArgumentTypeError(
                "Given key must be " + str(WirepasParams.KEY_SIZE) + " bytes long"
            )
        return byte_data

    def validate_network_address(network_address: str) -> int:
        network_address = int(network_address, 0)
        if network_address not in range(
            WirepasParams.MINIMUM_NETWORK_ADDRESS,
            WirepasParams.MAXIMUM_NETWORK_ADDRESS + 1,
        ):
            raise argparse.ArgumentTypeError("Given Network Address is out of range")
        return network_address

    def validate_network_channel(network_channel: str) -> int:
        network_channel = int(network_channel, 0)
        if network_channel not in range(
            WirepasParams.MINIMUM_NETWORK_CHANNEL,
            WirepasParams.MAXIMUM_NETWORK_CHANNEL + 1,
        ):
            raise argparse.ArgumentTypeError("Given Network Channel is out of range")
        return network_channel

    def validate_node_address(node_address: str) -> int:
        node_address = int(node_address, 0)
        if (
            node_address < WirepasParams.MINIMUM_NODE_ADDRESS
            or node_address > WirepasParams.MAXIMUM_NODE_ADDRESS
        ):
            raise argparse.ArgumentTypeError("Given Node Address is out of range")

        if (node_address & 0xFF000000) == 0x80000000:
            raise argparse.ArgumentTypeError(
                "Given Node Address is in the multicast address range"
            )

        return node_address


class SimParams:
    SIM_USER_MAX_LEN = 64
    SIM_PWD_MAX_LEN = 64
    SIM_APN_MAX_LEN = 64
    SIM_PIN_LENGTH = 10
    SIM_PUK_LENGTH = 10

    IMEI_LENGTH = 16
    IMSI_LENGTH = 16


class SimId(Enum):
    SIM1 = 0
    SIM2 = 1


class TestStatus(IntEnum):
    SUCCESS = 0
    UNTESTED = 1
    FAILED = 2


RX_RSSI_THRESHOLD_DBM = -75
TX_RSSI_THRESHOLD_DBM = -75

# Constants for cellular test retry logic
CELLULAR_TEST_MAX_RETRIES = 3
RESET_WAIT_TIME_S = 0.5


class TestSummary:
    def __init__(self, test_name, status, duration, rx_rssi=None, tx_rssi=None):
        self.test_name = test_name
        self.status = status
        self.duration = duration
        self.rx_rssi = rx_rssi
        self.tx_rssi = tx_rssi
        self.retry_count = 0  # Track number of retries

    def set_status(self, status: TestStatus):
        self.status = status

    def print_summary(self):
        retry_info = f" (after {self.retry_count} retries)" if self.retry_count > 0 else ""
        result_str = f"{'✅ Success ✅' if self.status == TestStatus.SUCCESS else '❌ Failed ❌'}{retry_info} (took {self.duration:.2f}s)"
        # Calculate the padding needed to right-justify at 80 characters
        justified_result = result_str.rjust(
            80 - len(self.test_name) - 7
        )  # 7 accounts for " Test: "
        print(f"{self.test_name} Test: {justified_result}")

        # Print RSSI values if available
        if self.rx_rssi is not None and self.tx_rssi is not None:
            print(f"\t├ RX RSSI: {self.rx_rssi} dBm")
            print(f"\t└ TX RSSI: {self.tx_rssi} dBm")


class TestResults:
    def __init__(self):
        self.cellular_results_sim1 = None
        self.cellular_results_sim2 = None
        self.gpio_result = None
        self.ext_flash_result = None
        self.rf_result = None

        self.cellular_sim_1_success = False
        self.cellular_sim_2_success = False
        self.gpio_success = False
        self.ext_flash_success = False
        self.rf_success = False

        self.cellular_summary_sim_1 = TestSummary("Cellular SIM1", TestStatus.UNTESTED, 0)
        self.cellular_summary_sim_2 = TestSummary("Cellular SIM2", TestStatus.UNTESTED, 0)
        self.gpio_summary = TestSummary("GPIO", TestStatus.UNTESTED, 0)
        self.ext_flash_summary = TestSummary("External Flash", TestStatus.UNTESTED, 0)
        self.rf_summary = TestSummary("RF", TestStatus.UNTESTED, 0)

    def print_results(self):
        print("_" * 80)
        print("Test Results Summary".center(80))
        print()

        # Cellular SIM 1 Test Results
        self.cellular_summary_sim_1.print_summary()
        if self.cellular_results_sim1:
            self.cellular_results_sim1.print_details()

        # Cellular SIM 2 Test Results
        self.cellular_summary_sim_2.print_summary()
        if self.cellular_results_sim2:
            self.cellular_results_sim2.print_details()

        # GPIO Test Results
        self.gpio_summary.print_summary()

        # External Flash Test Results
        self.ext_flash_summary.print_summary()

        # RF Test Results
        self.rf_summary.print_summary()


class Communication:
    TIMEOUT_RSP_TESTING_CELLULAR_S = 50
    TIMEOUT_RSP_TESTING_EXT_FLASH_S = 10
    TIMEOUT_RSP_TESTING_GPIO_S = 6
    TIMEOUT_RSP_TESTING_RF_S = 55
    READ_PARAMETERS_TIMEOUT_S = 2

    fm = factory_mode.FactoryMode()

    cellular_testing_queue = queue.Queue()
    sim_testing_queue = queue.Queue()
    gpio_testing_queue = queue.Queue()
    ext_flash_testing_queue = queue.Queue()
    rf_testing_queue = queue.Queue()
    read_parameters_queue = queue.Queue()


nic_com = Communication()


def parse_message_received(type: factory_mode.MessageType, data: bytes):
    if type == factory_mode.MessageType.TESTING_CELLULAR_RESPONSE:
        logging.debug("Cellular testing received!")
        nic_com.cellular_testing_queue.put_nowait(data)
    elif type == factory_mode.MessageType.TESTING_GPIO_RESPONSE:
        logging.debug("GPIO testing received!")
        nic_com.gpio_testing_queue.put_nowait(data)
    elif type == factory_mode.MessageType.TESTING_EXT_FLASH_RESPONSE:
        logging.debug("External flash testing received!")
        nic_com.ext_flash_testing_queue.put_nowait(data)
    elif type == factory_mode.MessageType.TESTING_RF_RESPONSE:
        logging.debug("RF testing received!")
        nic_com.rf_testing_queue.put_nowait(data)
    elif type == factory_mode.MessageType.PROVISIONING_READ_RESPONSE:
        logging.debug("Read Request Response Received")
        nic_com.read_parameters_queue.put_nowait(data)
    else:
        logging.warning("Unknown type received: %s", type)


def filter_version_info(nic_params: dict) -> dict:
    """Filter parameters to only include version information (NicInfoDataIds)"""
    version_keys = [
        "DEV_EUI64",
        "APP_VER",
        "STACK_VER",
        "GW_IMEI",
        "GW_CORE_VER",
        "GW_MAIN_VER",
        "GW_SINK_APP_VER",
        "GW_MODEM_FIRMWARE_VER",
        "GW_METER_LIB_VER"
    ]

    version_info = {}
    for key, value in nic_params.items():
        if key in version_keys:
            version_info[key] = value

    return version_info


def print_version_summary(version_info: dict):
    """Print version summary using the same format as read_parameters"""
    summary = "\n\n\tNIC Version Information Summary:\n"
    summary += "_" * 80 + "\n"
    summary += "\n".join("{!r}: {!r}".format(k, v) for k, v in version_info.items())
    summary += "\n" + "_" * 80 + "\n"
    logging.info(summary)


def read_nic_version_info_for_testing(com: Communication):
    """Read only NIC version information using the existing factory mode connection"""
    try:
        logging.info("Sending request to read NIC Parameters")
        if (
            factory_mode.send_factory_mode_message(
                com.fm, bytes(), factory_mode.MessageType.PROVISIONING_READ_REQUEST
            )
            is False
        ):
            logging.error("Sending Read Parameters Request not successful!")
            return

        try:
            nic_parameters_data = com.read_parameters_queue.get(
                timeout=com.READ_PARAMETERS_TIMEOUT_S
            )
        except queue.Empty:
            logging.error("Read Parameters response was not received in the given timeout!")
            return

        # Decode the full parameter data
        nic_parameters_data = wirepas_provisioning.decode_prov_dict(nic_parameters_data)

        # Filter to show only version information
        version_info = filter_version_info(nic_parameters_data)

        if version_info:
            print_version_summary(version_info)
        else:
            logging.warning("No version information found in device response!")

    except Exception as e:
        logging.error(f"Failed to read NIC version information: {e}")

def reset_device_and_reenter_factory_mode(com: Communication, serial_port: str, baudrate: int):
    """Reset the device and re-enter factory mode"""
    logging.info("🔄 Resetting device and re-entering factory mode...")

    try:
        # First, try to exit factory mode to reset the device
        if hasattr(com.fm.ser, 'is_open') and com.fm.ser.is_open:
            try:
                # Send EXIT_FACTORY_MODE to reset the device
                factory_mode.send_factory_mode_message(
                    com.fm, bytes(), factory_mode.MessageType.EXIT_FACTORY_MODE
                )
                logging.debug("Sent EXIT_FACTORY_MODE command")
                sleep(1.0)  # Give time for the device to exit and reset
            except Exception as e:
                logging.debug(f"Could not send EXIT_FACTORY_MODE command: {e}")

        # Reinitialize the serial connection (this handles stopping threads and closing ports)
        factory_mode.serial_initialization(serial_port, com.fm, baudrate)

        # Wait for the device to fully reset and boot up
        sleep(RESET_WAIT_TIME_S)

        # Re-enter factory mode with the challenge/response loop
        factory_mode.wait_for_challenge_response_with_reset_loop(com.fm)

        logging.info("✅ Successfully re-entered factory mode")
        return True

    except Exception as e:
        logging.error(f"❌ Failed to reset device and re-enter factory mode: {e}")
        return False

class CellularTestingResult:
    def __init__(self, imei, imsi, rsrp, rsrq, valid_measurements):
        self.imei = imei
        self.imsi = imsi
        self.rsrp = rsrp
        self.rsrq = rsrq
        self.valid_measurements = valid_measurements

    @classmethod
    def from_bytes(cls, data):
        format_str = f"{SimParams.IMEI_LENGTH}s{SimParams.IMSI_LENGTH}shh?"
        unpacked_data = unpack(format_str, data)
        imei = unpacked_data[0].decode("utf-8").rstrip("\x00")
        imsi = unpacked_data[1].decode("utf-8").rstrip("\x00")
        return cls(imei, imsi, *unpacked_data[2:])

    def print_details(self):
        print(f"\t├ IMEI: {self.imei}")
        print(f"\t├ IMSI: {self.imsi}")
        print(f"\t├ RSRP: {self.rsrp} dBm")
        print(f"\t├ RSRQ: {self.rsrq} dB")
        print(
            f"\t└ Valid Signal Measurements: {'Yes' if self.valid_measurements else 'No'}"
        )


def exit_factory_mode(com: Communication):
    logging.info("Sending request to exit factory mode")
    if (
        factory_mode.send_factory_mode_message(
            com.fm, bytes(), factory_mode.MessageType.EXIT_FACTORY_MODE
        )
        is False
    ):
        factory_mode.error_print_and_exit(
            "Sending Exit Factory Mode Packet isn't successful!",
            factory_mode.ExitCodes.SENDING_FAILED,
        )


def create_cellular_testing_payload(sim_id, user, pwd, apn, pin, puk):
    user = user.encode("utf-8").ljust(SimParams.SIM_USER_MAX_LEN, b"\0")
    pwd = pwd.encode("utf-8").ljust(SimParams.SIM_PWD_MAX_LEN, b"\0")
    apn = apn.encode("utf-8").ljust(SimParams.SIM_APN_MAX_LEN, b"\0")
    pin = pin.encode("utf-8").ljust(SimParams.SIM_PIN_LENGTH, b"\0")
    puk = puk.encode("utf-8").ljust(SimParams.SIM_PUK_LENGTH, b"\0")

    payload = pack(
        f"<B{SimParams.SIM_USER_MAX_LEN}s{SimParams.SIM_PWD_MAX_LEN}s{SimParams.SIM_APN_MAX_LEN}s{SimParams.SIM_PIN_LENGTH}s{SimParams.SIM_PUK_LENGTH}s",
        sim_id,
        user,
        pwd,
        apn,
        pin,
        puk,
    )
    return payload


def perform_single_cellular_test(
    com: Communication,
    sim_id: SimId,
    user: str,
    pwd: str,
    apn: str,
    pin: str,
    puk: str,
) -> tuple[bool, CellularTestingResult]:
    """Perform a single cellular test attempt"""
    logging.info("📶 Starting Cellular Testing on %s 📶", sim_id.name)

    payload = create_cellular_testing_payload(sim_id.value, user, pwd, apn, pin, puk)
    logging.debug(payload)

    if not factory_mode.send_factory_mode_message(
        com.fm, payload, factory_mode.MessageType.TESTING_CELLULAR_REQUEST
    ):
        logging.error("Failed to send cellular testing message")
        return False, None

    try:
        cellular_test_data = com.cellular_testing_queue.get(
            timeout=com.TIMEOUT_RSP_TESTING_CELLULAR_S
        )
    except queue.Empty:
        logging.error("RSP_TEST_CELLULAR was not received in the given timeout!")
        return False, None

    cellular_test_result = CellularTestingResult.from_bytes(cellular_test_data)
    return cellular_test_result.valid_measurements, cellular_test_result


def perform_cellular_testing(
    com: Communication,
    sim_id: SimId,
    user: str,
    pwd: str,
    apn: str,
    pin: str,
    puk: str,
    results: TestResults,
    serial_port: str,
    baudrate: int,
) -> bool:
    """Perform cellular testing with retry logic"""
    start_time = time.time()

    success = False
    cellular_test_result = None
    retry_count = 0

    for attempt in range(CELLULAR_TEST_MAX_RETRIES):
        if attempt > 0:
            logging.info(f"🔄 Cellular test attempt {attempt + 1}/{CELLULAR_TEST_MAX_RETRIES}")
            retry_count = attempt

            # Reset device and re-enter factory mode for retry attempts
            if not reset_device_and_reenter_factory_mode(com, serial_port, baudrate):
                logging.error(f"Failed to reset device for retry attempt {attempt + 1}")
                continue

        # Clear any existing messages in the queue before the test
        with com.cellular_testing_queue.mutex:
            com.cellular_testing_queue.queue.clear()

        # Perform the cellular test
        success, cellular_test_result = perform_single_cellular_test(
            com, sim_id, user, pwd, apn, pin, puk
        )

        if success:
            logging.info(f"✅ Cellular test succeeded on {sim_id.name} (attempt {attempt + 1})")
            break
        else:
            logging.warning(f"❌ Cellular test failed on {sim_id.name} (attempt {attempt + 1})")
            if attempt < CELLULAR_TEST_MAX_RETRIES - 1:
                logging.info("Will retry after device reset...")

    # Store results
    if sim_id == SimId.SIM1:
        results.cellular_results_sim1 = cellular_test_result
        results.cellular_summary_sim_1.duration = time.time() - start_time
        results.cellular_summary_sim_1.retry_count = retry_count
        results.cellular_summary_sim_1.status = (
            TestStatus.SUCCESS if success else TestStatus.FAILED
        )
    else:
        results.cellular_results_sim2 = cellular_test_result
        results.cellular_summary_sim_2.duration = time.time() - start_time
        results.cellular_summary_sim_2.retry_count = retry_count
        results.cellular_summary_sim_2.status = (
            TestStatus.SUCCESS if success else TestStatus.FAILED
        )

    if not success:
        logging.error(f"❌ Cellular test failed after {CELLULAR_TEST_MAX_RETRIES} attempts")

    return success


def perform_ext_flash_testing(com: Communication, results: TestResults) -> bool:
    start_time = time.time()
    logging.info("💾 Starting External Flash Testing 💾")

    if not factory_mode.send_factory_mode_message(
        com.fm, bytes(), factory_mode.MessageType.TESTING_EXT_FLASH_REQUEST
    ):
        factory_mode.error_print_and_exit(
            "Failed to send external flash testing message",
            factory_mode.ExitCodes.SENDING_FAILED,
        )

    try:
        ext_flash_data = com.ext_flash_testing_queue.get(
            timeout=com.TIMEOUT_RSP_TESTING_EXT_FLASH_S
        )
    except queue.Empty:
        results.ext_flash_summary.duration = time.time() - start_time
        factory_mode.error_print_and_exit(
            "RSP_TEST_EXT_FLASH was not received in the given timeout!",
            factory_mode.ExitCodes.RECEPTION_TIMEOUT,
        )

    (ext_flash_res,) = unpack(">B", ext_flash_data)
    results.ext_flash_result = ext_flash_res
    results.ext_flash_summary.duration = time.time() - start_time
    results.ext_flash_summary.status = (
        TestStatus.SUCCESS if ext_flash_res else TestStatus.FAILED
    )
    return ext_flash_res


def perform_gpio_testing(com: Communication, results: TestResults) -> bool:
    start_time = time.time()
    logging.info("📍 Starting GPIO Testing 📍")

    if not factory_mode.send_factory_mode_message(
        com.fm, bytes(), factory_mode.MessageType.TESTING_GPIO_REQUEST
    ):
        factory_mode.error_print_and_exit(
            "Failed to send GPIO testing message",
            factory_mode.ExitCodes.SENDING_FAILED,
        )

    try:
        gpio_test_data = com.gpio_testing_queue.get(
            timeout=com.TIMEOUT_RSP_TESTING_GPIO_S
        )
    except queue.Empty:
        results.gpio_summary.duration = time.time() - start_time
        factory_mode.error_print_and_exit(
            "RSP_TEST_GPIO was not received in the given timeout!",
            factory_mode.ExitCodes.RECEPTION_TIMEOUT,
        )

    (gpio_res,) = unpack(">B", gpio_test_data)
    results.gpio_result = gpio_res
    results.gpio_summary.duration = time.time() - start_time
    results.gpio_summary.status = TestStatus.SUCCESS if gpio_res else TestStatus.FAILED
    return gpio_res


def create_rf_testing_payload(
    test_router_addr: int, net_addr: int, net_chan: int, enc_key: bytes, auth_key: bytes
):
    return pack(
        "<LLB16s16sbb",
        test_router_addr,
        net_addr,
        net_chan,
        enc_key,
        auth_key,
        TX_RSSI_THRESHOLD_DBM,
        RX_RSSI_THRESHOLD_DBM,
    )


def perform_rf_testing(
    com: Communication,
    test_router_addr: int,
    net_addr: int,
    net_chan: int,
    enc_key: bytes,
    auth_key: bytes,
    results: TestResults,
) -> bool:
    start_time = time.time()
    logging.info("📶 Starting RF Testing 📶")

    payload = create_rf_testing_payload(
        test_router_addr, net_addr, net_chan, enc_key, auth_key
    )
    logging.debug(payload)

    if not factory_mode.send_factory_mode_message(
        com.fm, payload, factory_mode.MessageType.TESTING_RF_REQUEST
    ):
        results.rf_summary.duration = time.time() - start_time
        factory_mode.error_print_and_exit(
            "Failed to send RF testing message", factory_mode.ExitCodes.SENDING_FAILED
        )

    try:
        rf_test_data = com.rf_testing_queue.get(timeout=com.TIMEOUT_RSP_TESTING_RF_S)
    except queue.Empty:
        results.rf_summary.duration = time.time() - start_time
        factory_mode.error_print_and_exit(
            "TESTING_RF_RESPONSE was not received in the given timeout!",
            factory_mode.ExitCodes.RECEPTION_TIMEOUT,
        )

    results.rf_summary.duration = time.time() - start_time

    (
        results.rf_summary.rx_rssi,
        results.rf_summary.tx_rssi,
        results.rf_summary.status,
    ) = unpack(">bbB", rf_test_data)

    return results.rf_summary.status == TestStatus.SUCCESS


def validate_length_and_alnum(value, max_length, name):
    if len(value) > max_length:
        raise argparse.ArgumentTypeError(
            f"{name} exceeds maximum length of {max_length}"
        )
    if len(value) and not value.isalnum():
        raise argparse.ArgumentTypeError(
            f"{name} must contain only alphanumeric characters"
        )
    return value


def print_overall_test_result(total_duration, overall_success):
    print("_" * 80)
    print(f"\nTotal Testing Time: {total_duration:.2f} seconds")

    result_color = Fore.GREEN if overall_success else Fore.RED
    result_emoji = "✅" if overall_success else "❌"

    print(
        f"\nOverall Test Result: {result_color}{result_emoji} "
        + ("SUCCESS" if overall_success else "FAIL")
        + f" {result_emoji}{Style.RESET_ALL}"
    )
    print("\n")


def test_gateway(args: argparse):
    # Managing the communication with the NIC
    global nic_com
    nic_com.fm.parse_message_callback = parse_message_received

    factory_mode.serial_initialization(args.serial_port, nic_com.fm, args.baudrate)
    factory_mode.wait_for_challenge_response_with_reset_loop(nic_com.fm)

    # Read NIC version information before testing
    read_nic_version_info_for_testing(nic_com)

    test_results = TestResults()

    start_time = time.time()

    test_results.cellular_sim_1_success = perform_cellular_testing(
        nic_com,
        SimId.SIM1,
        args.sim1_user,
        args.sim1_pwd,
        args.sim1_apn,
        args.sim1_pin,
        args.sim1_puk,
        test_results,
        args.serial_port,
        args.baudrate,
    )

    test_results.cellular_sim_2_success = perform_cellular_testing(
        nic_com,
        SimId.SIM2,
        args.sim2_user,
        args.sim2_pwd,
        args.sim2_apn,
        args.sim2_pin,
        args.sim2_puk,
        test_results, 
        args.serial_port,
        args.baudrate,
    )

    test_results.gpio_success = perform_gpio_testing(nic_com, test_results)
    test_results.ext_flash_success = perform_ext_flash_testing(nic_com, test_results)
    test_results.rf_success = perform_rf_testing(
        nic_com,
        args.test_router_address,
        args.network_address,
        args.network_channel,
        args.encryption_key,
        args.authentication_key,
        test_results,
    )

    total_duration = time.time() - start_time

    test_results.print_results()

    overall_success = (
        test_results.cellular_sim_1_success
        and test_results.cellular_sim_2_success
        and test_results.gpio_success
        and test_results.ext_flash_success
        and test_results.rf_success
    )

    print_overall_test_result(total_duration, overall_success)

    exit_factory_mode(nic_com)


if __name__ == "__main__":
    logging.basicConfig(
        format="%(levelname)s %(asctime)s %(message)s", level=logging.DEBUG
    )

    logging.info("Starting testing...")

    parser = argparse.ArgumentParser(fromfile_prefix_chars="@")

    # Serial parameters
    parser.add_argument(
        "--serial_port",
        type=str,
        help="Serial port used to communicate with the gateway.",
        required=True,
    )
    parser.add_argument(
        "--baudrate",
        type=int,
        help="Baudrate used to communicate with the gateway.",
        default=9600,
    )

    # Cellular testing parameters
    parser.add_argument(
        "--sim1_user",
        type=lambda x: validate_length_and_alnum(
            x, SimParams.SIM_USER_MAX_LEN, "--sim1_user"
        ),
        help="SIM1 user name.",
        default="",
    )
    parser.add_argument(
        "--sim1_pwd",
        type=lambda x: validate_length_and_alnum(
            x, SimParams.SIM_PWD_MAX_LEN, "--sim1_pwd"
        ),
        help="SIM1 password.",
        default="",
    )
    parser.add_argument(
        "--sim1_apn",
        type=lambda x: validate_length_and_alnum(
            x, SimParams.SIM_APN_MAX_LEN, "--sim1_apn"
        ),
        help="SIM1 APN.",
        default="",
    )
    parser.add_argument(
        "--sim1_pin",
        type=lambda x: validate_length_and_alnum(
            x, SimParams.SIM_PIN_LENGTH, "--sim1_pin"
        ),
        help="SIM1 PIN.",
        default="",
    )
    parser.add_argument(
        "--sim1_puk",
        type=lambda x: validate_length_and_alnum(
            x, SimParams.SIM_PUK_LENGTH, "--sim1_puk"
        ),
        help="SIM1 PUK.",
        default="",
    )
    parser.add_argument(
        "--sim2_user",
        type=lambda x: validate_length_and_alnum(
            x, SimParams.SIM_USER_MAX_LEN, "--sim2_user"
        ),
        help="SIM2 user name.",
        default="",
    )
    parser.add_argument(
        "--sim2_pwd",
        type=lambda x: validate_length_and_alnum(
            x, SimParams.SIM_PWD_MAX_LEN, "--sim2_pwd"
        ),
        help="SIM2 password.",
        default="",
    )
    parser.add_argument(
        "--sim2_apn",
        type=lambda x: validate_length_and_alnum(
            x, SimParams.SIM_APN_MAX_LEN, "--sim2_apn"
        ),
        help="SIM2 APN.",
        default="",
    )
    parser.add_argument(
        "--sim2_pin",
        type=lambda x: validate_length_and_alnum(
            x, SimParams.SIM_PIN_LENGTH, "--sim2_pin"
        ),
        help="SIM2 PIN.",
        default="",
    )
    parser.add_argument(
        "--sim2_puk",
        type=lambda x: validate_length_and_alnum(
            x, SimParams.SIM_PUK_LENGTH, "--sim2_puk"
        ),
        help="SIM2 PUK.",
        default="",
    )

    # Testing Router parameters
    parser.add_argument(
        "--test_router_address",
        type=WirepasParams.validate_node_address,
        help="Test Router Address to communicate to during the RF testing.",
        required=True,
    )
    parser.add_argument(
        "--network_address",
        type=WirepasParams.validate_network_address,
        help="Network address used by the NIC during the RF testing.",
        required=True,
    )
    parser.add_argument(
        "--network_channel",
        type=WirepasParams.validate_network_channel,
        help="Network channel used by the NIC during the RF testing.",
        required=True,
    )
    parser.add_argument(
        "--encryption_key",
        type=WirepasParams.validate_key,
        help="Encryption Key used by the NIC during the RF testing. Must be specified as a 16 bytes value.",
        required=True,
    )
    parser.add_argument(
        "--authentication_key",
        type=WirepasParams.validate_key,
        help="Authentication Key used by the NIC during the RF testing. Must be specified as a 16 bytes value.",
        required=True,
    )

    args = parser.parse_args()

    test_gateway(args)
