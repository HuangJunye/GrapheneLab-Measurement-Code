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
	
import rpyc
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

import VisaSubs as VisaSubs
import SrsLia as LIA
import Keithleys as keithley
import SocketUtils as SocketUtils

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


def OpenCSVFile(FileName,StartTime,ReadInst,SweepInst=[],SetInst=[],SetValue=[],Comment = "No comment!\n"):
	
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
	
	NetworkDir = "Z:\\DATA"
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

	ColumnString = "T (mK), B (T)"
	
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

	print "Writing to data file %s\n" % File
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

#################################################
############# Vg SWEEP
#################################################
	
def DoDeviceSweep(GraphProc,rpg,DataFile,SweepInst,ReadInst,
		SetInst = [], SetValue = [],
		BSet = 0. , Persist = True, IgnoreMagnet = False,
		SweepStart = 0., SweepStop = 0., SweepStep = 1., SweepFinish = 0.0,SweepMid = [],
		Delay = 0, Sample = 1,
		TSet = -1,
		Timeout = -1, Wait = 0.0,
		ReturnData = False,
		comment = "No comment!",
		**kwargs):

	# Bind sockets 
	MClient, MSocket, TClient, TSocket = InitializeSockets()

	NRead = len(ReadInst)

	if SetInst:
		if len(SetInst) != len(SetValue):
			if len(SetValue) > len(SetInst):
				SetValue = SetValue[0:len(SetInst)]
			else:
				SetValue.append([0]*(len(SetInst)-len(SetValue)))
		for i,v in enumerate(SetInst):
			SetInst.Ramp(SetValue[i])
	
	# Set the sweep voltages

	Sweep = GenerateDeviceSweep(SweepStart,SweepStop,SweepStep,Mid=SweepMid)
		
	SetTime = datetime.now()

	# Go to the set temperature and magnetic field and finish in persistent mode
	if TSet > 0:
		Msg = " ".join(("SET","%.2f" % SetTemp))
		SocketWrite(TClient,Msg)
		print "Wrote message to temperature socket \"%s\"" % Msg
	if not IgnoreMagnet:
		Msg = " ".join(("SET","%.3f" % SetField,"%d" % int(not Persist)))
		SocketWrite(MClient,Msg)
		print "Wrote message to Magnet socket \"%s\"" % Msg
	time.sleep(5)

	# give precedence to the magnet and wait for the timeout
	TSocket = SocketRead(TClient, TSocket)
	MSocket = SocketRead(MClient, MSocket)
	while MSocket[1] != 1:
		print "Waiting for magnet!"
		time.sleep(15)
		TSocket = SocketRead(TClient, TSocket)
		MSocket = SocketRead(MClient, MSocket)
	
	NowTime = datetime.now()
	Remaining = Timeout*60.0 - float((NowTime-SetTime).seconds)
	while (TSocket[1] != 1) and (Remaining > 0):
		NowTime = datetime.now()
		Remaining = Timeout*60.0 - float((NowTime-SetTime).seconds)
		print "Waiting for temperature ... time remaining = %.2f minutes" % (Remaining/60.0)
		TSocket = SocketRead(TClient, TSocket)
		MSocket = SocketRead(MClient, MSocket)	
		time.sleep(15)
	
	time.sleep(Wait*60.0)

	# Setup L plot windows
	GraphWin = rpg.GraphicsWindow(title="Device Sweep...")
	PlotData = GraphProc.transfer([])
	GraphWin.resize(500,150*NRead)
	Plot = []
	Curve = []
	for i in range(NRead):
		Plot.append(GraphWin.addPlot())
		Curve.append(Plot[i].plot(pen='y'))
		GraphWin.nextRow()
	

	StartTime = datetime.now()

	Writer, FilePath, NetDir = OpenCSVFile(DataFile,SweepInst,ReadInst,SetInst=SetInst,SetValue=SetValue,Comment=comment)
	print "Ramping to start!"

	if SweepStart != 0:
		SweepInst.Ramp(SweepStart)
	else:
		SweepInst.SetSource(0)

	if not SweepInst.Output:
		SweepInst.SwitchOutput()
	
	SweepInst.ReadData()	
	
	print "Waiting 1 minute!"
	time.sleep(60)
	print "Starting measurement!"

	# This is the main measurement loop

	StartColumn, DataVector = GenerateDataVector(2,ReadInst,Sample,SweepInst=SweepInst,SetValue = SetValue)
	
	for i,v in enumerate(Sweep):
		
		# Set the Keithley
		SweepInst.Set(v)

		TSocket = SocketRead(TClient, TSocket)
		MSocket = SocketRead(MClient, MSocket)

		DataVector[:,0] = MSocket[0]
		DataVector[:,1] = TSocket[0]
		DataVector[:,2] = v

		for j in range(Sample):
		
			for i,v in enumerate(ReadInst):
				v.ReadData()
				DataVector[j,StartColumn[i]:StartColumn[i+1]] = v.Data

			# Sleep
			time.sleep(Delay)
		
		# Save the data
		for j in range(Sample):
			Writer.writerow(DataVector[j,:])
		
		# Package the data and send it for plotting
		
		ToPlot = np.empty((NRead+1))
		ToPlot[0] = DataVector[-1,2]
		for j in range(NRead):
			ToPlot[j+1] = DataVector[-1,StartColumn[j]]
	
		# Pass data to the plots
		PlotData.extend(ToPlot,_callSync = "off")
		for j in range(NRead):
			Curve[j].setData(x=PlotData[0::(NRead+1)],y=PlotData[j+1::(NRead+1)],_callSync = "off")

	SweepInst.Ramp(SweepFinish)

	# if the finish is zero switch it off
	if SweepFinish == 0.0:
		SweepInst.SwitchOutput()
	
	if ReturnData:
		DataList = [None]*(NRead+1)
		DataList[0] = PlotData[0::NRead+1]
		for i in range(1,NRead+1):
			DataList[i]=PlotData[i::NRead+1]
		

	# Copy the file to the network
	time.sleep(5)
	try:
		shutil.copy(FilePath,NetDir)
	except IOError:
		pass
	
	# We are finished, now ramp the Keithley to the finish voltage
	GraphWin.close()
	MClient.close()
	TClient.close()

	if ReturnData:
		return FilePath, DataList
	else:
		return FilePath


#################################################
############# T SWEEP
#################################################
	
def DoTempSweep(GraphProc,rpg,DataFile,
		Magnet, Lias, Kthly,
		SetField=0 ,
		TempStart = 0, TempFinish = 0, TempRate = 1, TempFinal =0.0,
		Delay = 1, VgMeas = 0.0, FinishGate = 0.0,
		Timeout = -1,
		comment = "No comment!",
		Persist = True, IgnoreMagnet = False,
		ReadKeithley=False,**kwargs):

	# Bind to the Temperature socket 
	TClient = SocketUtils.SockClient('localhost', 18871)
	TCurrent = "0"
	TStatus = "-1" # Unset
	# Bind to the Magnet socket 
	MClient = SocketUtils.SockClient('localhost', 18861)
	Field = "0"
	MStatus = "1" # Busy
	# Wait for the connection
	TCurrent, TStatus = TempSocketRead(TClient, TCurrent, TStatus)
	Field, MStatus = MagSocketRead(MClient, Field, MStatus)
	time.sleep(5)
		
	SetTime = datetime.now()

	# Go to the specified field and finish in persistent mode

	SocketWrite(TClient," ".join(("SET","%.2f" % TempStart)))
	print "Wrote message to temperature socket \"SET %.2f\"" % TempStart
	if not IgnoreMagnet:
		SocketWrite(MClient," ".join(("SET","%.3f" % SetField,"%d" % int(not Persist))))
		print "Wrote message to Magnet socket \"SET %.3f %d\"" % (SetField, int(not Persist))
	time.sleep(5)

	# give precedence to the magnet and wait for the timeout
	TCurrent, TStatus = TempSocketRead(TClient, TCurrent, TStatus)
	Field, MStatus = MagSocketRead(MClient, Field, MStatus)
	while MStatus != "0":
		print "Waiting for magnet!"
		time.sleep(15)
		TCurrent, TStatus = TempSocketRead(TClient, TCurrent, TStatus)
		Field, MStatus = MagSocketRead(MClient, Field, MStatus)	
	
	NowTime = datetime.now()
	Remaining = Timeout*60.0 - float((NowTime-SetTime).seconds)
	while (TStatus != "1") and (Remaining > 0):
		NowTime = datetime.now()
		Remaining = Timeout*60.0 - float((NowTime-SetTime).seconds)
		print "Waiting for temperature ... time remaining = %.2f minutes" % (Remaining/60.0)
		TCurrent, TStatus = TempSocketRead(TClient, TCurrent, TStatus)
		Field, MStatus = MagSocketRead(MClient, Field, MStatus)		
		time.sleep(15)

	# Setup L plot windows
	NLias = len(Lias)
	NGraph = NLias
	GraphWin = rpg.GraphicsWindow(title="Temperature sweep...")
	PlotData = GraphProc.transfer([])
	GraphWin.resize(500,200*NLias)
	Plot = []
	Curve = []
	for i in range(NLias+1):
		Plot.append(GraphWin.addPlot())
		Curve.append(Plot[i].plot(pen='y'))
		GraphWin.nextRow()
	

	StartTime = datetime.now()

	Writer, FilePath, NetDir = OpenCSVFile(DataFile,StartTime,Lias,[Kthly],comment = comment)
	
	if VgMeas != 0:
		Kthly.Ramp(VgMeas)
	else:
		Kthly.SetSource(0)

	if not Kthly.Output:
		Kthly.SwitchOutput()

	Kthly.ReadData()
	
	time.sleep(60)
	print "Starting measurement!"

	TempSocketWrite(TClient," ".join(("SWP","%.2f" % TempStart,"%.2f" % TempFinish,"%.4f" % (TempRate/60.0))))
	TStatus = "2"
	time.sleep(2)
	# This is the main measurement loop
	
	while TStatus == "2":
		DataList = np.zeros((4+NLias*4,))
		
		# Read the Keithley
		if ReadKeithley:
			Kthly.ReadData()
		DataList[0:2] = Kthly.Data
			
		# Read the magnet
		if not IgnoreMagnet:
			Field, MStatus = MagSocketRead(MClient, Field, MStatus)
		else:
			Field = 0.0
		DataList[j,2] = Field

		# Read the temperature
		TCurrent, TStatus = TempSocketRead(TClient, TCurrent, TStatus)
		DataList[3] = TCurrent
			
		# Read the Lockins
		for k,inst in enumerate(Lias):
			inst.ReadData()
			DataList[((k+1)*4):((k+2)*4)] = inst.Data

		# Save the data
		Writer.writerow(DataList)
		# Package the data and send it for plotting

		XData = DataList[3]
		YData = np.empty([NGraph+1])
		YData[1:NLias+1] = DataList[4:NLias*4+2:4]
		YData[0] = DataList[1]

		# Pass data to the plots
		PlotData.extend(np.hstack([XData,YData]),_callSync = "off")
		for i in range(NGraph+1):
			Curve[i].setData(x=PlotData[0::NGraph+2],y=PlotData[i+1::NGraph+2],_callSync = "off")
		# Sleep and cycle the gate if necessary
		time.sleep(Delay)
	
	
	Kthly.Ramp(FinishGate)

	if Kthly.Output and FinishGate == 0.0:
		Kthly.SwitchOutput()

	TempSocketWrite(TClient," ".join(("SET","%.2f" % TempFinal)))
	# Copy the file to the network
	time.sleep(5)
	
	# We are finished, now ramp the Keithley to the finish voltage
	GraphWin.close()
	MClient.close()
	TClient.close()
	
	try:
		shutil.copy(FilePath,NetDir)
	except OSError:
		pass

	return FilePath

#########################################################################
########  B SWEEP ###########
#####################################################

def DoBSweep(GraphProc,rpg,DataFile,
		Lias, Kthly, Vg = 0,
		Start = 0, Stop = 0, FinishHeater = 0, Rate = 1.6,
		Delay = 1.0, Timeout = -1, SetTemp = -1, VPreRamp = [],
		HeaterConst = [], CycleGate = 0, CycleDelay = 0.05,
		GateStep = 0.1,
		FinishGate = 0.0, ReadKeithley = False,
		comment = "No comment!"):
	
	# Bind to the Temperature socket 
	TClient = SocketUtils.SockClient('localhost', 18871)
	TCurrent = "0"
	TStatus = "-1" # Unset
	# Bind to the Magnet socket 
	MClient = SocketUtils.SockClient('localhost', 18861)
	Field = "0"
	MStatus = "1" # Busy
	# Wait for the connection
	TCurrent, TStatus = TempSocketRead(TClient, TCurrent, TStatus)
	Field, MStatus = MagSocketRead(MClient, Field, MStatus)
	time.sleep(5)
	
	# Tell the magnet daemon to go to the inital field and set the temperature
	if SetTemp > 0:
		SocketWrite(TClient," ".join(("SET","%.2f" % SetTemp)))
		print "Wrote message to temperature socket \"SET %.2f\"" % SetTemp
	if HeaterConst:
		TempSocketWrite(TClient," ".join(("CST","%.2f" % HeaterConst)))	
	SocketWrite(MClient," ".join(("SET","%.3f" % Start,"1")))
	print "Wrote message to Magnet socket \"SET %.3f 1\"" % Start
	time.sleep(5)
	SetTime = datetime.now()

	# Wait for the temperature timeout
	NowTime = datetime.now()
	Remaining = Timeout*60.0 - (NowTime-SetTime).seconds
	TCurrent, TStatus = TempSocketRead(TClient, TCurrent, TStatus)
	Field, MStatus = MagSocketRead(MClient, Field, MStatus)		
	while TStatus == "0" and Remaining > 0:
		NowTime = datetime.now()
		Remaining = Timeout*60.0 - (NowTime-SetTime).seconds*1.0
		print "Time remaining = %.2f minutes" % (Remaining/60.0)
		TCurrent, TStatus = TempSocketRead(TClient, TCurrent, TStatus)
		Field, MStatus = MagSocketRead(MClient, Field, MStatus)
		time.sleep(15)
	
	# Wait more for the magnet if necessary
	while MStatus != "0":
		print "Waiting for magnet!"
		time.sleep(15)
		TCurrent, TStatus = TempSocketRead(TClient, TCurrent, TStatus)
		Field, MStatus = MagSocketRead(MClient, Field, MStatus)	

	# Turn on the Keithley and then wait for a bit
	#Kthly.SetSource(0)
	if VPreRamp:
		for i in VPreRamp:
			Kthly.Ramp(i)
	Kthly.Ramp(Vg-CycleGate)
	Kthly.ReadData()

	if CycleGate:
		GateRange = np.hstack((np.arange(Vg-CycleGate,Vg+CycleGate,GateStep),np.arange(Vg+CycleGate,Vg-CycleGate,-1*GateStep)))
		GateCycle = cycle(GateRange)


	# Setup L plot windows for each LIA
	NLias = len(Lias)

	
	GraphWin = rpg.GraphicsWindow(title="B Sweep...")
	PlotData = GraphProc.transfer([])
	GraphWin.resize(500,150+150*NLias)
	Plot = []
	Curve = []
	for i in range(NLias+1):
		Plot.append(GraphWin.addPlot())
		Curve.append(Plot[i].plot(pen='y'))
		GraphWin.nextRow()
	
	time.sleep(120)

	StartTime = datetime.now()
	
	# Open the data file
	Writer, FilePath, NetDir = OpenCSVFile(DataFile,StartTime,Lias,[Kthly],comment = comment)

	# Start the sweep
	SocketWrite(MClient," ".join(("SWP","%.3f" % Start,"%.3f" % Stop,"%d" % FinishHeater)))

	while MStatus != "2":
		time.sleep(1)
		TCurrent, TStatus = TempSocketRead(TClient, TCurrent, TStatus)
		Field, MStatus = MagSocketRead(MClient, Field, MStatus)	
	
	#print Field
	while MStatus == "2":
		DataList = np.zeros((4+NLias*4,))
		
		# Read the Keithley
		if ReadKeithley:
			Kthly.ReadData()
		DataList[0:2] = Kthly.Data
			
		# Read the magnet
		Field, MStatus = MagSocketRead(MClient, Field, MStatus)		
		DataList[2] = Field

		# Read the temperature
		TCurrent, TStatus = TempSocketRead(TClient, TCurrent, TStatus)
		DataList[3] = TCurrent
			
		# Read the Lockins
		for k,inst in enumerate(Lias):
			inst.ReadData()
			DataList[((k+1)*4):((k+2)*4)] = inst.Data

		# Save the data
		Writer.writerow(DataList)
		# Package the data and send it for plotting

		XData = DataList[2]
		YData = np.empty([NLias+1])
		YData[1:NLias+1] = DataList[4:NLias*4+2:4]
		YData[0] = DataList[1]
		# YData[-1] = DataList[-2]
		# Pass data to the plots
		PlotData.extend(np.hstack([XData,YData]),_callSync = "off")
		for i in range(NLias+1):
			Curve[i].setData(x=PlotData[0::NLias+2],y=PlotData[i+1::NLias+2],_callSync = "off")

        # Sleep and cycle the gate if necessary
		if CycleGate:
			LoopTime = time.time() + Delay
			while True:
				if time.time() > LoopTime:
					break
				Kthly.SetSource(GateCycle.next())
				time.sleep(CycleDelay)
		else:
			time.sleep(Delay)
	
	
	Kthly.Ramp(FinishGate)

	if Kthly.Output and FinishGate == 0.0:
		Kthly.SwitchOutput()
	
	# We are finished
	GraphWin.close()
	MClient.close()
	TClient.close()

	# Copy the file to the network
	time.sleep(5)
	try:
		shutil.copy(FilePath,NetDir)
	except OSError:
		pass

	return FilePath

###########################################
###########################################

def Vg2D(GraphProc, rpg, DataFile,
		Lias, Kthly,
		SetTemp = -1,
		VgStart = -10, VgStop = 10, VgStep = 1,
		VgSamples = 1, VgFinish=0.0,
		Delay = 0,
		BStart = -1, BStop = 1, BStep = 0.25,
		Timeout = -1, comment = "No comment!",
		Persist=True, **kwargs):

	if VgStop < VgStart:
		VgSet = [VgStop, VgStart]
	else:
		VgSet = [VgStart, VgStop]

	if "BCustom" in kwargs.keys():
		BVec = kwargs["BCustom"]
	else:
		BVec = np.hstack((np.arange(BStart,BStop,BStep),BStop))

	NLIAS = len(Lias) 
	Plt2DWin = [None]*NLIAS
	VwBox = [None]*NLIAS
	Imv = [None]*NLIAS
	Z= [[] for _ in range(NLIAS)]
	ZArray = [None] * NLIAS
	#Exporter = [None] * NLIAS
	#ImageTitle = [None] * NLIAS
	
	for i in range(NLIAS):
		Plt2DWin[i] = rpg.QtGui.QMainWindow()
		Plt2DWin[i].resize(500,500)
		VwBox[i] = rpg.ViewBox(invertY = True)
		Imv[i] = rpg.ImageView(view=rpg.PlotItem(viewBox=VwBox[i]))
		Plt2DWin[i].setCentralWidget(Imv[i])
		#ImageTitle[i] = "LIA %d" % i
		Plt2DWin[i].setWindowTitle("2D Plot")
		Plt2DWin[i].show()
		#Exporter[i] = rpg.exporters.ImageExporter.ImageExporter(Imv[i].imageItem)


	X = BVec
	LenB = len(X)

	for i in range(len(X)):

		
		FileName, DataList = DoVgSweep(GraphProc,
				rpg,DataFile,
				Lias,Kthly,
				Start=VgSet[0],Stop=VgSet[1],Step=VgStep,
				Samples=VgSamples,Finish = VgFinish,
				Timeout=Timeout,Delay=Delay,
				SetTemp=SetTemp,
				SetField = X[i],
				Persist = Persist,
				ReturnData=True, comment = comment)

		if i == 0:
			Y = DataList[0]

		for j in range(NLIAS):
			Z[j].append(DataList[j+1])

		if i >= 1:
			YScale = abs(Y[-1]-Y[0])/float(len(Y))
			XScale = abs(X[i]-X[0])/float(i)
			#XScale = abs(i-0)/float(i)			
			for j in range(NLIAS):
				ZArray[j] = np.array(Z[j])
		#		print np.shape(ZArray[i])
				ZArray[j] = np.reshape(ZArray[j],(i+1,-1))
				Imv[j].setImage(ZArray[j],scale=(XScale,YScale),pos=(X[0],Y[0]))
				VwBox[j].autoRange()
				if i == LenB-1:
				# export to hdf5
					outFile = h5py.File("".join((DataFile,"-%d" % j,".hdf5")),"w")
					ZSet = outFile.create_dataset("Z",data=ZArray[j])
					YSet = outFile.create_dataset("V",data=Y)
					XSet = outFile.create_dataset("B",data=X)
					outFile.close()
				#Exporter[j].export("".join((ImageTitle[i],".png")))

	# Finished, ramp the keithley to zero and switch it off  if not done
	if Finish != 0.0:
		Kthly.Ramp(0)

	# if the finish is zero switch it off
	Kthly.SwitchOutput()

	for i in range(NLIAS):
		Imv[i].close()
		VwBox[i].close()
		Plt2DWin[i].close()
	
	return

################################################
################################################

def DoBSeq(GraphProc,rpg,DataFile,
		Lias, Kthly,
		VgStart = 0, VgStop = 0, VgStep = 0,
		Start = 0, Stop = 0, Rate = 1.6,
		Delay = 1, Timeout = -1,
		SetTemp = -1, comment = "No comment!",VPreRamp=[],
		CycleGate = 0.0, GateStep = 0.1, **kwargs):

	if "VCustom" in kwargs.keys():
		Source = kwargs["VCustom"]
	elif "mid" in kwargs.keys():
		Source = Kthly.RunSweep(VgStart,VgStop,
				VgStep,Delay,mid=kwargs["mid"])
	else:
		Source = Kthly.RunSweep(VgStart,VgStop,VgStep,Delay)

	Source = np.hstack((Source,[0.0]))

	# No need to swap these
	#if Start > Stop:
	#	BLim = [Stop,Start]
	#else:
	BLim = [Start,Stop]

	for i,VGate in enumerate(Source[:-1]):
		DoBSweep(GraphProc,rpg,DataFile,
				Lias, Kthly, Vg = VGate,
				Start = BLim[0], Stop = BLim[1],
				FinishHeater = 1, Rate = Rate,
				Delay = Delay, Timeout = Timeout,
				SetTemp = SetTemp, VPreRamp = VPreRamp,
				CycleGate = CycleGate,
				FinishGate = Source[i+1], comment = comment)
		BLim = BLim[::-1]

	MClient = SocketUtils.SockClient('localhost', 18861)
	time.sleep(5)
	SocketWrite(MClient,"SET 0.0 0")
	time.sleep(5)
	MClient.close()
	

	return


	
