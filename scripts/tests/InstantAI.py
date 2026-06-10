#!/usr/bin/python
# -*- coding:utf-8 -*-

import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir)))

import time
from Automation.BDaq import *
from Automation.BDaq.InstantAiCtrl import InstantAiCtrl
from Automation.BDaq.BDaqApi import AdxEnumToString, BioFailed

deviceDescription = "USB-4704,BID#0"
profilePath = u"../../profile/DemoDevice.xml"

channelCount = 16
startChannel = 0

def AdvInstantAI():
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
            print("Channel %d data: %10.6f" % (i, scaledData[i - startChannel]))

    finally:
        # Always release the device
        instanceAiObj.dispose()

    return 0


if __name__ == '__main__':
    # print("hiiii")
    AdvInstantAI()
