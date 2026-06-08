#!/usr/bin/python
# -*- coding:utf-8 -*-


"""
/*******************************************************************************
Copyright (c) 1983-2021 Advantech Co., Ltd.
********************************************************************************
THIS IS AN UNPUBLISHED WORK CONTAINING CONFIDENTIAL AND PROPRIETARY INFORMATION
WHICH IS THE PROPERTY OF ADVANTECH CORP., ANY DISCLOSURE, USE, OR REPRODUCTION,
WITHOUT WRITTEN AUTHORIZATION FROM ADVANTECH CORP., IS STRICTLY PROHIBITED.

================================================================================
REVISION HISTORY
--------------------------------------------------------------------------------
$Log:  $

--------------------------------------------------------------------------------
$NoKeywords:  $
*/

/******************************************************************************
*
* Windows Example:
*    StaticDO.py
*
* Example Category:
*    DIO
*
* Description:
*    This example demonstrates how to use Static DO function.
*
* Instructions for Running:
*    1. Set the 'deviceDescription' for opening the device.
*    2. Set the 'profilePath' to save the profile path of being initialized device.
*    3. Set the 'startPort'as the first port for Do .
*    4. Set the 'portCount'to decide how many sequential ports to operate Do.
*
* I/O Connections Overview:
*    Please refer to your hardware reference manual.
*
******************************************************************************/
"""
import sys, os
# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir)))

# from scripts.Automation.BDaq import *
from scripts.Automation.BDaq import *
from scripts.Automation.BDaq.InstantDoCtrl import InstantDoCtrl
from scripts.Automation.BDaq.BDaqApi import AdxEnumToString, BioFailed
import argparse

# deviceDescription = "DemoDevice,BID#0"

# deviceDescription = "USB-4704,BID#0" # Replace with actual identifier

profilePath = u"../../profile/DemoDevice.xml"
startPort = 0
portCount = 1

def AdvInstantDO(inputVal, deviceDescription):
    ans = ""
    ret = ErrorCode.Success

    # Step 1: Create a instantDoCtrl for DO function.
    # Select a device by device number or device description and specify the access mode.
    # In this example we use ModeWrite mode so that we can fully control the device,
    # including configuring, sampling, etc.
    instantDoCtrl = InstantDoCtrl(deviceDescription)
    for _ in range(1):
        instantDoCtrl.loadProfile = profilePath

        # Step 2: Write DO ports
        dataBuffer = [0] * portCount
        for i in range(startPort, portCount + startPort):
            if not isinstance(inputVal, int):
                inputVal = int(inputVal, 16)

            dataBuffer[i-startPort] = inputVal

        ret = instantDoCtrl.writeAny(startPort, portCount, dataBuffer)
        if BioFailed(ret):
            break
        # print("DO output completed!")
        ans = "DO output completed!"

    # Step 3: Close device and release any allocated resource.
    instantDoCtrl.dispose()

    # If something wrong in this execution, print the error code on screen for tracking.
    if BioFailed(ret):
        enumStr = AdxEnumToString("ErrorCode", ret.value, 256)
        # print("Some error occurred. And the last error code is %#x. [%s]" % (ret.value, enumStr))
        ans = "Some error occurred. And the last error code is %#x. [%s]" % (ret.value, enumStr)
    return ans


# if __name__ == "__main__":
def run_staticDO(inputVal = 0, deviceDescription = "USB-4716,BID#0"):
    # ans = "Some error occurred"
    # print("static file called")
    # parser = argparse.ArgumentParser()
    # parser.add_argument("--inputVal", required=True, help="Input value passed from parent script")
    
    
    # args = parser.parse_args()
    # inputVal = args.inputVal 
    
    # Access the passed value
    print("Received input:", inputVal)
    print("Dec Card ID: ", deviceDescription)

    # print("DO output completed! dack card")
    # return "DO output completed!"
    ans = AdvInstantDO(inputVal, deviceDescription)
    return ans
