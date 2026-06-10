#!/usr/bin/python
# -*- coding:utf-8 -*-

import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir)))

import time
from Automation.BDaq import *
from Automation.BDaq.InstantAiCtrl import InstantAiCtrl
from Automation.BDaq.BDaqApi import AdxEnumToString, BioFailed
import argparse

# deviceDescription = "USB-4704,BID#0"
profilePath = u"../../profile/DemoDevice.xml"

channelCount = 12


def AdvInstantAI(deviceDescription, startChannel):
    voltage_output = {}
    # print(deviceDescription)
    ret = ErrorCode.Success

    # Step 1: Create a 'instantAiCtrl' for InstantAI function
    instanceAiObj = InstantAiCtrl(deviceDescription)

    try:
        instanceAiObj.loadProfile = profilePath   # Loads a profile to initialize the device

        # Step 2: Read samples once and print
        ret, scaledData = instanceAiObj.readDataF64(startChannel, channelCount)
        if BioFailed(ret):
            enumStr = AdxEnumToString("ErrorCode", ret.value, 256)
            print("Some error occurred. And the last error code is %#x. [%s]" % (ret.value, enumStr))
            return -1

        for i in range(startChannel, startChannel + channelCount):
            voltage_output["Channel " + str(i) + " data"] = scaledData[i - startChannel]
            # print("Channel %d data: %10.6f" % (i, scaledData[i - startChannel]))

    finally:
        # Always release the device
        instanceAiObj.dispose()

    return voltage_output


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--deviceDescription", required=True, help="Input value passed from parent script")
    args = parser.parse_args()
    deviceDescription = ""
    deviceDescription = args.deviceDescription
    daq1 = deviceDescription + "0"
    daq1_output = AdvInstantAI(daq1, startChannel = 0)
    # daq2_output = AdvInstantAI(daq2, startChannel = 8)
    # daq1_output.update(daq2_output)
    # print(daq1_output)
    print(daq1_output)

