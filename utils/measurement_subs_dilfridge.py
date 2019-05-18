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

"""
	
import visa as visa
import string as string
import re as re
import time
import multiprocessing
import numpy as np 

import pyqtgraph as pg
import pyqtgraph.multiprocess as mp
from pyqtgraph.Qt import QtCore, QtGui

from datetime import datetime
import os
import csv
import subprocess
import shutil
import asyncore
import h5py

import utils.visa_subs as VisaSubs
import utils.socket_utils as SocketUtils

from itertools import cycle

def InitializeSockets():
	# Bind to the temperature and magnet sockets and try to read them
	TClient = SocketUtils.SockClient('localhost', 18871)
	MClient = SocketUtils.SockClient('localhost', 18861)
	time.sleep(4)
	MSocket = [0.0, 0]
	TSocket = [0.0, 0]
	TSocket = SocketRead(TClient, TSocket)
	MSocket = SocketRead(MClient, MSocket)
	
	return MClient, MSocket, TClient, TSocket

def SocketRead(Client,OldSocket = []):
	# Read the socket and parse the reply, the reply has 2 parts the message and the status
	asyncore.loop(count=1,timeout=0.001)
	SocketString = Client.received_data
	Socket = OldSocket
	if SocketString:
		SocketString = SocketString.split(",")[-1]
		SocketString = SocketString.split(" ")
		if len(SocketString)==2:
			Value = SocketString[:-1]
			Status = SocketString[-1]
			try:
				for i,v in enumerate(Value):
					Value[i] = float(v)
				Status = int(Status)
				Socket[0] = Value
				Socket[1] = Status
			except:
				pass

	return Socket

def SocketWrite(Client,Msg):
	Client.to_send = Msg
	asyncore.loop(count=1,timeout=0.001)
	time.sleep(2)
	Client.to_send = "-"
	asyncore.loop(count=1,timeout=0.001)

def OpenCSVFile(FileName,StartTime,ReadInst,
		SweepInst=[],SetInst=[],Comment = "No comment!\n",
		NetworkDir = "Z:\\DATA"):
	
	# Setup the directories
	# Try to make a directory called Data in the CWD
	CurrentDir = os.getcwd()
	DataDir = "".join((CurrentDir,"\\Data"))
	try:
		os.mkdir(DataDir)
	except OSError:
		pass

	# Try to make a directory with the current director name in the
	# network drive
	
	NetworkDir = NetworkDir
	DirName = os.path.basename(CurrentDir)
	NetDir = "".join((NetworkDir,"\\",DirName))
	if not os.path.exists(NetDir):
		try:
			os.mkdir(NetDir)
		except OSError:
			pass

	# Try to make a file called ...-0.dat in data else ...-1.dat etc.
	i = 0
	while True:
		File = "".join((DataDir,"\\",FileName,"-","%d" % i,".dat"))
		try:
			os.stat(File)
			i = i+1
			pass
		except OSError:
			csvfile = open(File,"w")
			FileWriter = csv.writer(csvfile,delimiter = ',')
			break

	
	# Write the starttime and a description of each of the instruments
	FileWriter.writerow([StartTime])

	ColumnString = "B (T), T(mK) "
	
	for Inst in SweepInst:
		csvfile.write("".join(("SWEEP: ",Inst.Description())))
		ColumnString = "".join((ColumnString,", ",Inst.Source))

	for Inst in SetInst:
		csvfile.write("".join(("SET: ",Inst.Description())))
		ColumnString = "".join((ColumnString,", ",Inst.Source))

	for Inst in ReadInst:
		csvfile.write("".join(("READ: ",Inst.Description())))
		ColumnString = "".join((ColumnString,", ",Inst.ColumnNames))


	ColumnString = "".join((ColumnString,"\n"))
	csvfile.write(Comment)
	csvfile.write("\n")
	csvfile.write(ColumnString)

	print("Writing to data file %s\n" % File)
	return FileWriter, File, NetDir
	
def GenerateDeviceSweep(Start,Stop,Step,Mid = []):
		#self.Visa.write("".join((":SOUR:",self.Source,":MODE FIX")))
	Targets = Mid
	Targets.insert(0,Start)
	Targets.append(Stop)

	Sweep = [Targets[0]]
	for i in range(1,len(Targets)):
		Points = int(1+abs(Targets[i]-Targets[i-1])/Step)
		Sweep = np.hstack([Sweep,np.linspace(Targets[i-1],Targets[i],num = Points)[1:Points]])
	return Sweep

def GenerateDataVector(LFridgeParam, ReadInst, Sample, SweepInst = False, SetValue = []):

	LSet = len(SetValue)
	if SweepInst:
		LSweep = 1
	else:
		LSweep = 0
	LRead = 0
	StartColumn = [0] * (len(ReadInst)+1)
	StartColumn[0] = LFridgeParam + LSweep + LSet
	for i,v in enumerate(ReadInst):
		StartColumn[i+1] = StartColumn[i] + len(v.Data)

	DataVector = np.zeros((Sample,StartColumn[-1]))

	for i in range(LSet):
		DataVector[:,i+LFridgeParam+LSweep] = SetValue[i]

	return StartColumn, DataVector

	
