import sys, os
import time
from scripts.Automation.BDaq import *
from scripts.Automation.BDaq.InstantAiCtrl import InstantAiCtrl
from scripts.Automation.BDaq.BDaqApi import AdxEnumToString, BioFailed
import argparse
import logging

profilePath = u"../../profile/DemoDevice.xml"

channelCount = 16
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

    finally:
        # Always release the device
        instanceAiObj.dispose()

    return voltage_output


def run_instantAi(deviceDescription = "USB-4716,BID#0"):
    daq0_output = {}
    daq0_output = AdvInstantAI(deviceDescription)
    logging.info(f"fetched InstantAi voltage: {daq0_output}")
    # daq0_output = {'Channel 0 data': 5.87833251953125, 'Channel 1 data': 3.51861572265625, 'Channel 2 data': 3.37528076171875, 'Channel 3 data': 3.3200439453125, 'Channel 4 data': 3.51448974609375, 'Channel 5 data': 3.3556884765625,'Channel 6 data': 5.94805908203125, 'Channel 7 data': 5.9483642578125, 'Channel 8 data': 3.61451416015625, 'Channel 9 data': 3.38643798828125, 'Channel 10 data': 3.38582763671875, 'Channel 11 data': 3.5806396484375, 'Channel 12 data': 3.4060302734375, 'Channel 13 data': 5.80145263671875, 'Channel 14 data': 1.95465087890625, 'Channel 15 data': 1.7578125}
    return daq0_output
