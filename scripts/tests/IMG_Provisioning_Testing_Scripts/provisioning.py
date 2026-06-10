# Copyright 2024 Wirepas Ltd licensed under Apache License, Version 2.0
#
# See file LICENSE for full license details.
#

import argparse
import queue
import logging
import wirepas_provisioning
import sys
import factory_mode

from wirepas_provisioning import WirepasProvisioning

class Communication:
    DRY_RUN_RECEIVE_TIMEOUT_S = 2
    READ_PARAMETERS_TIMEOUT_S = 2

    fm = factory_mode.FactoryMode()

    provisioning_success_queue = queue.Queue()
    read_parameters_queue = queue.Queue()


nic_com = Communication()


def parse_message_received(type: factory_mode.MessageType, data: bytes):
    if type == factory_mode.MessageType.PROVISIONING_WRITE_RESPONSE:
        if wirepas_provisioning.is_provisioning_dry_run_successful(data) is True:
            logging.debug("Dry Run Successful! Sending reboot request")
            nic_com.provisioning_success_queue.put(True)
        else:
            logging.debug("Dry Run returned an error! No reboot request sent!")
            nic_com.provisioning_success_queue.put(False)
    elif type == factory_mode.MessageType.PROVISIONING_READ_RESPONSE:
        logging.debug("Read Request Response Received")
        nic_com.read_parameters_queue.put(data)
    else:
        logging.warning("Unknown type received: %s", type)


def perform_parameters_provisioning(com: Communication, wp_prov: WirepasProvisioning):
    provisioning_packet = wp_prov.get_provisioning_packet()

    logging.debug(f"Provisioning packet size: {len(provisioning_packet)} bytes")
    logging.debug(f"Provisioning packet hex: {provisioning_packet.hex()}")

    logging.info("Sending Provisioning Packet")
    if (
        factory_mode.send_factory_mode_message(
            com.fm,
            provisioning_packet,
            factory_mode.MessageType.PROVISIONING_WRITE_REQUEST,
        )
        is False
    ):
        factory_mode.error_print_and_exit(
            "Sending Provisioning Packet isn't successful!",
            factory_mode.ExitCodes.SENDING_FAILED,
        )

    try:
        validation_run_success = com.provisioning_success_queue.get(
            timeout=com.DRY_RUN_RECEIVE_TIMEOUT_S
        )
    except queue.Empty:
        factory_mode.error_print_and_exit(
            "Provisioning validation run return code not received in the given timeout!",
            factory_mode.ExitCodes.RECEPTION_TIMEOUT,
        )

    if validation_run_success is False:
        factory_mode.error_print_and_exit(
            "Provisioning validation run was not successful!",
            factory_mode.ExitCodes.INVALID_PARAMETERS,
        )

    logging.info("Applying parameters to the NIC")

    if (
        factory_mode.send_factory_mode_message(
            com.fm, bytes(), factory_mode.MessageType.PROVISIONING_REBOOT_REQUEST
        )
        is False
    ):
        factory_mode.error_print_and_exit(
            "Sending Device Reboot Request not successful!",
            factory_mode.ExitCodes.SENDING_FAILED,
        )


def perform_parameters_reading(com: Communication):
    logging.info("Sending request to read NIC Parameters")
    if (
        factory_mode.send_factory_mode_message(
            com.fm, bytes(), factory_mode.MessageType.PROVISIONING_READ_REQUEST
        )
        is False
    ):
        factory_mode.error_print_and_exit(
            "Sending Read Parameters Request not successful!",
            factory_mode.ExitCodes.SENDING_FAILED,
        )

    try:
        nic_parameters_data = com.read_parameters_queue.get(
            timeout=com.READ_PARAMETERS_TIMEOUT_S
        )
    except queue.Empty:
        factory_mode.error_print_and_exit(
            "Read Parameters response was not received in the given timeout!",
            factory_mode.ExitCodes.RECEPTION_TIMEOUT,
        )

    nic_parameters_data = wirepas_provisioning.decode_prov_dict(nic_parameters_data)

    wirepas_provisioning.print_provisioning_summary(nic_parameters_data)

    prov_sucess = wirepas_provisioning.get_provisioning_status(nic_parameters_data)

    if prov_sucess is True:
        factory_mode.success_print("NIC is successfully provisioned!")
    else:
        factory_mode.error_print("Missing parameters in the devsice!")


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


def provision_nic_parameters(args: argparse):
    # Managing the communication with the NIC
    global nic_com
    nic_com.fm.parse_message_callback = parse_message_received

    factory_mode.serial_initialization(args.serial_port, nic_com.fm, args.baudrate)

    logging.info("Starting NIC Provisioning")

    # Get all argument attributes except serial_port and baudrate (which are always set)
    provisioning_params = {
        k: v for k, v in vars(args).items() if k not in ["serial_port", "baudrate"]
    }

    # Check if all provisioning parameters are None
    if all(value is None for value in provisioning_params.values()):
        logging.error(
            "No parameters specified for provisioning! All parameters are NULL!"
        )
        logging.error("At least one parameter must be specified.")
        sys.exit(factory_mode.ExitCodes.MISSING_PARAMETERS.value)

    # Create WirepasProvisioning object with all parameters from args
    wp_prov = WirepasProvisioning(
        encryption_key=args.encryption_key,
        authentication_key=args.authentication_key,
        network_address=args.network_address,
        network_channel=args.network_channel,
        node_address=args.node_address,
        node_role=args.node_role,
        gw_key_enc_key=args.gw_key_enc_key,
        mtr_auth_key=args.mtr_auth_key,
        mtr_enc_key=args.mtr_enc_key,
        mtr_mr_secret=args.mtr_mr_secret,
        mtr_us_secret=args.mtr_us_secret,
        mtr_fu_secret=args.mtr_fu_secret,
        mtr_baud_rate=args.mtr_baud_rate,
        mtr_dlms_mode=args.mtr_dlms_mode,
        gateway_id=args.gateway_id,
        sink_address=args.sink_address,
        sim1_apn=args.sim1_apn,
        sim1_username=args.sim1_username,
        sim1_password=args.sim1_password,
        sim1_pdp_type=args.sim1_pdp_type,
        sim1_pin=args.sim1_pin,
        sim1_puk=args.sim1_puk,
        sim2_apn=args.sim2_apn,
        sim2_username=args.sim2_username,
        sim2_password=args.sim2_password,
        sim2_pdp_type=args.sim2_pdp_type,
        sim2_pin=args.sim2_pin,
        sim2_puk=args.sim2_puk,
        mqtt_hostname=args.mqtt_hostname,
        mqtt_port=args.mqtt_port,
        mqtt_username=args.mqtt_username,
        mqtt_password=args.mqtt_password,
        mqtt_unsecure=args.mqtt_unsecure,
        cellular_info_diag_intvl=args.cellular_info_diag_interval,
        network_info_diag_intvl=args.network_info_diag_interval,
        gateway_info_diag_intvl=args.gateway_info_diag_interval,
        ntp_addr=args.ntp_addr,
        tz_offset_min=args.tz_offset_min,
        keepalive_intvl_s=args.keepalive_interval,
        reset_hour=args.reset_hour,
        reset_minute=args.reset_minute,
        band_lock=args.cellular_band_lock,
        sim_selection=args.sim_selection,
    )

    # Check if at least one parameter is provided
    if not any(value is not None for value in vars(wp_prov).values()):
        logging.error(
            "No parameters specified for provisioning! All parameters are NULL!"
        )
        logging.error("At least one parameter must be specified.")
        sys.exit(factory_mode.ExitCodes.MISSING_PARAMETERS.value)

    factory_mode.wait_for_challenge_response_with_reset_loop(nic_com.fm)
    perform_parameters_provisioning(nic_com, wp_prov)

    # Waiting for NIC to reboot before asking the parameters
    logging.info("Waiting for NIC to reboot...")

    # Check if mtr_baud_rate was provisioned and switch baudrate if needed
    if args.mtr_baud_rate is not None:
        factory_mode.switch_baudrate_if_needed(
            nic_com.fm, args.serial_port, args.mtr_baud_rate
        )

    factory_mode.wait_for_challenge_response_with_reset_loop(nic_com.fm)
    perform_parameters_reading(nic_com)

    exit_factory_mode(nic_com)

    sys.exit(factory_mode.ExitCodes.SUCCESS.value)


def read_nic_parameters(args: argparse):
    # Managing the communication with the NIC
    global nic_com
    nic_com.fm.parse_message_callback = parse_message_received

    factory_mode.serial_initialization(args.serial_port, nic_com.fm, args.baudrate)

    factory_mode.wait_for_challenge_response_with_reset_loop(nic_com.fm)
    perform_parameters_reading(nic_com)

    exit_factory_mode(nic_com)

    sys.exit(factory_mode.ExitCodes.SUCCESS.value)


if __name__ == "__main__":
    factory_mode.error_print_and_exit(
        "Unavailable. Please use 'provision_img_parameters.py' or 'read_img_parameters.py'",
        factory_mode.ExitCodes.CALL_TO_MAIN,
    )
