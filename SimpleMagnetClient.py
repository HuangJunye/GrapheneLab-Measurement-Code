#!/usr/bin/python
# -*- coding: utf-8 -*-

"""

Sub programs for doing the measurements

author : Eoin O'Farrell
email : phyoec@nus.edu.sg
last edited : July 2013

Explantion:

	There are 3 variables in our instrument:
	1 Temperature
	2 Field
	3 Device parameter; e.g. Backgate V, Topgate V, Current, Angle (one day)

	Typically a measurement will fix two of these and vary the other.
	The controls for temperature and field are controlled by external
	services that can be called by the measurement. The measurement
	invokes a localhost for each of these services and can then
	access certain methods
	
	The generic ports for these are
	Magnet: 18861
	Temperature: 18871

	Data from these processes can also be accessed through named pipes

	Device parameters are so far controlled in situ in the measurement
	loop. This should probably also be changed to be consistent

ToDo:
	
	InitializeInstruments
	ScanInstruments
	InitializeDataFile
	WriteDataFile
	CloseDataFile
	GraphData

"""
	

import time

import asyncore
import SocketUtils as SocketUtils


def MagSocketRead(Client,OldField,Status):
	asyncore.loop(count=1,timeout=0.001)
	MString = Client.received_data
	Field = OldField
	if MString:
		MString = MString.split(",")[-1]
		MString = MString.split(" ")
		if len(MString)==2:
			NewField = MString[0]
			Status = MString[1]
			try:
				Field = float(NewField)
				Status = int(Status)
			except:
				pass

	return Field, Status

def SocketWrite(Client,Msg):
	Client.to_send = Msg
	asyncore.loop(count=1,timeout=0.001)
	time.sleep(2)
	Client.to_send = "-"
	asyncore.loop(count=1,timeout=0.001)

if __name__ == '__main__':

	MClient = SocketUtils.SockClient('localhost', 18861)
	time.sleep(5)

	SocketWrite(MClient,"SET 0.0 0")
	

	Field =0.0
	MStatus = 0
	Field, MStatus = MagSocketRead(MClient, Field, MStatus)
	print Field, MStatus

	while MStatus == 0:
		Field, MStatus = MagSocketRead(MClient, Field, MStatus)
		print Field, MStatus
		time.sleep(4)


