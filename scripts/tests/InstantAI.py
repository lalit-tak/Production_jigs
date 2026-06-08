#!/usr/bin/python
# -*- coding:utf-8 -*-

import sys, os
# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir)))

import time
from scripts.Automation.BDaq import *
from scripts.Automation.BDaq.InstantAiCtrl import InstantAiCtrl
from scripts.Automation.BDaq.BDaqApi import AdxEnumToString, BioFailed
import argparse

# deviceDescription = "USB-4704,BID#0"
profilePath = u"../../profile/DemoDevice.xml"

channelCount = 8
startChannel = 0

def AdvInstantAI(deviceDescription):
    voltage_output = {}
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


# if __name__ == '__main__':
def run_instantAi(deviceDescription = "USB-4704,BID#0"):
    daq0_output = {}
    # return daq0_output
    daq0_output = AdvInstantAI(deviceDescription)
    # daq1_output.update(daq0_output)
    return daq0_output
