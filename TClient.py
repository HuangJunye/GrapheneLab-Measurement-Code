#!/usr/bin/python
# -*- coding: utf-8 -*-

"""

Sub programs for operation of the PicoWatt and Leiden TCS to control temperature

author : Eoin O'Farrell
email : phyoec@nus.edu.sg
last edited : August 2013


	The daemon listens for commands to change the control loop or setpoint
	The daemon broadcasts the current temperature

ToDo:
	
	Listen
	Broadcast
	Initialize
	ReadPico
	CalcPID
	SetTCS

"""

import asyncore
import logging
import visa as visa
import VisaSubs as VisaSubs
import string as string
import re as res
import time
import SocketUtils as SocketUtils



#import asyncore
import logging
import numpy as np
#import socket


if __name__ == '__main__':

	logging.basicConfig(level=logging.DEBUG,format='%(name)s: %(message)s',)

	client = SocketUtils.SockClient('localhost', 18871)
	#handler = server.handler
	#asyncore.loop()
	TCurrent = "0"
	TStatus = "-1"

	for i in range(10):
		asyncore.loop(count=1,timeout=0.001)
		TString = client.received_data
		if TString:
			TString = TString.split(",")[-1]
			TString = TString.split(" ")
			TCurrent = TString[0]
			TStatus = TString[1]
		else:
			TCurrent = TCurrent
			TStatus = TStatus
	
		time.sleep(1)

	time.sleep(1)
	client.to_send = "SET 1000"
	asyncore.loop(count=1,timeout=0.001)
	time.sleep(1)
	client.to_send = "-"

	for i in range(10):
		asyncore.loop(count=1,timeout=0.001)
		TString = client.received_data
		if TString:
			TString = TString.split(",")[-1]
			TString = TString.split(" ")
			TCurrent = TString[0]
			TStatus = TString[1]
		else:
			TCurrent = TCurrent
			TStatus = TStatus
		print TCurrent, TStatus
		time.sleep(1)
	
	client.close()


