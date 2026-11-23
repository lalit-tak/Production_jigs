# Copyright 2024 Wirepas Ltd licensed under Apache License, Version 2.0
#
# See file LICENSE for full license details.
#

import argparse
import logging
from scripts.tests.IMG_Provisioning_Testing_Scripts import provisioning
# import provisioning

# Default serial communication settings
DEFAULT_BAUDRATE = 9600

# if __name__ == "__main__":
def run_read_img_parameters(serial_port, baudrate = DEFAULT_BAUDRATE):
    img_param = {}
    img_prov_sucess = False
    img_param, img_prov_sucess = provisioning.read_nic_parameters(serial_port, baudrate)
    
    return img_param, img_prov_sucess
