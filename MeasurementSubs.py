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


def TempSocketRead(Client,OldTemp,Status):
	asyncore.loop(count=1,timeout=0.001)
	TString = Client.received_data
	Temp = OldTemp
	if TString:
		TString = TString.split(",")[-1]
		TString = TString.split(" ")
		if len(TString)==2:
			NewTemp = TString[0]
			Status = TString[1]
			try:
				Temp = float(NewTemp)
			except:
				pass

	return Temp, Status

def TempSocketWrite(Client,Msg):
	Client.to_send = Msg
	asyncore.loop(count=1,timeout=0.001)
	time.sleep(2)
	Client.to_send = "-"
	asyncore.loop(count=1,timeout=0.001)


def OpenCSVFile(FileName,StartTime,Lockins,Kths,comment = "No comment!\n"):
	
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

	
	for k in Kths:
		csvfile.write(k.Description())
		ColumnString = "".join((k.Source,", ",k.Sense))
	
	ColumnString = "".join((ColumnString,", B (T), T (mK)"))
	for k in Lockins:
		csvfile.write(k.Description())
		ColumnString = "".join((ColumnString,", X, Y, R, Theta"))

	ColumnString = "".join((ColumnString,"\n"))
	csvfile.write(comment)
	csvfile.write("\n")
	csvfile.write(ColumnString)

	print "Writing to data file %s\n" % File
	return FileWriter, File, NetDir

#################################################
############# Vg SWEEP
#################################################
	
def DoVgSweep(GraphProc,rpg,DataFile, Magnet, Lias, Kthly,
		Field=0 ,
		Start = 0, Stop = 0, Step = 1, Finish = 0.0,
		Delay = 0, Samples = 1,
		Timeout = -1, SetTemp = -1, ReturnData = False,
		comment = "No comment!",Persist=True,
		Wait = 0.0, IgnoreMagnet = False,
		ReadKeithley = False, **kwargs):

	# Bind to the Temperature socket 
	TClient = SocketUtils.SockClient('localhost', 18871)
	TCurrent = "0"
	TStatus = "-1"
	# Wait for the connection
	time.sleep(5)

	# Set the source voltages

	if "mid" in kwargs.keys():
		Source = Kthly.RunSweep(Start,Stop,Step,Delay,mid=kwargs["mid"])
	else:
		Source = Kthly.RunSweep(Start,Stop,Step,Delay)
		
	SetTime = datetime.now()

	# Go to the specified field and finish in persistent mode
	if SetTemp > 0:
		TempSocketWrite(TClient," ".join(("SET","%.2f" % SetTemp)))
		time.sleep(5)

	if not IgnoreMagnet:
		Magnet.root.MagnetGoToSet(Field, int(not Persist), rate = 2.2)

	# Wait for the timeout
	NowTime = datetime.now()
	Remaining = Timeout*60.0 - float((NowTime-SetTime).seconds)
	TCurrent, TStatus = TempSocketRead(TClient, TCurrent, TStatus)
	while (TStatus != "1") and (Remaining > 0):
		NowTime = datetime.now()
		Remaining = Timeout*60.0 - float((NowTime-SetTime).seconds)
		print "Time remaining = %.2f minutes" % (Remaining/60.0)
		TCurrent, TStatus = TempSocketRead(TClient, TCurrent, TStatus)
		time.sleep(10)
	
	time.sleep(Wait*60.0)

	# Setup L plot windows
	NLias = len(Lias)
	GraphWin = rpg.GraphicsWindow(title="Vg Sweep")
	PlotData = GraphProc.transfer([])
	GraphWin.resize(500,150+150*NLias)
	Plot = []
	Curve = []
	for i in range(NLias+1):
		Plot.append(GraphWin.addPlot())
		Curve.append(Plot[i].plot(pen='y'))
		GraphWin.nextRow()
	

	StartTime = datetime.now()

	Writer, FilePath, NetDir = OpenCSVFile(DataFile,StartTime,Lias,[Kthly],comment = comment)
	
	if Start != 0:
		Kthly.Ramp(Start)
	else:
		Kthly.SetSource(0)

	if not Kthly.Output:
		Kthly.SwitchOutput()
	
	Kthly.ReadData()	
	
	time.sleep(30)
	print "Starting measurement!"

	# This is the main measurement loop
	
	for i in xrange(len(Source)):
		DataList = np.zeros((Samples,4+NLias*4))
		
		# Set the Keithley
		Kthly.SetSource(Source[i])
		for j in range(Samples):
		
			# Read the Keithley
			if ReadKeithley:
				Kthly.ReadData()
				DataList[j,0:2] = Kthly.Data
			else:
				DataList[j,0] = Source[i]
				DataList[j,1] = Kthly.Data[1]
			
			# Read the magnet
			if not IgnoreMagnet:
				Field = Magnet.root.MagnetReadField()
			else:
				Field = 0.0
			DataList[j,2] = Field

			# Read the temperature
			TCurrent, TStatus = TempSocketRead(TClient, TCurrent, TStatus)
			DataList[j,3] = TCurrent
			
			# Read the Lockins
			for k,inst in enumerate(Lias):
				inst.ReadData()
				DataList[j,((k+1)*4):((k+2)*4)] = inst.Data

			# Sleep
			time.sleep(Delay)
		
		#DataList = np.reshape(DataList,[Samples,len(DataList)/Samples])
		
		# Save the data
		for j in xrange(Samples):
			Writer.writerow(DataList[j,:])
		
		# Package the data and send it for plotting
		XData = DataList[:,0]
		YData = np.empty([Samples,NLias+1])
		YData[:,1:] = DataList[:,4:NLias*4+2:4]
		YData[:,0] = DataList[:,1]
		
		# Pass data to the plots
		PlotData.extend(np.hstack([np.mean(XData),np.mean(YData,0)]),_callSync = "off")
		for i in range(NLias+1):
			Curve[i].setData(x=PlotData[0::NLias+2],y=PlotData[i+1::NLias+2],_callSync = "off")
		
	# We are finished, now ramp the Keithley to the finish voltage
	if Stop != Finish:
		Kthly.Ramp(Finish)

	# if the finish is zero switch it off
	if Finish == 0.0:
		Kthly.SwitchOutput()
	
	if ReturnData:
		DataList = [None]*(NLias+1)
		DataList[0] = PlotData[0::NLias+2]
		for i in range(1,NLias+1):
			DataList[i]=PlotData[i+1::NLias+2]
		

	# Copy the file to the network
	time.sleep(5)
	try:
		shutil.copy(FilePath,NetDir)
	except OSError:
		pass

	GraphWin.close()

	if ReturnData:
		return FilePath, DataList
	else:
		return FilePath


#################################################
############# T SWEEP
#################################################
	
def DoTempSweep(GraphProc,rpg,DataFile, Magnet, Lias, Kthly, Field=0 ,
		TempStart = 0, TempFinish = 0, TempRate = 1, TempFinal =0.0,
		Delay = 1, VgMeas = 0.0, FinishGate = 0.0,
		Timeout = -1,
		comment = "No comment!",Persist=True,ReadKeithley=False,**kwargs):

	# Bind to the Temperature socket 
	TClient = SocketUtils.SockClient('localhost', 18871)
	TCurrent = "0"
	TStatus = "-1"
	# Wait for the connection
	time.sleep(5)
		
	SetTime = datetime.now()

	# Go to the specified field and finish in persistent mode

	TempSocketWrite(TClient," ".join(("SET","%.2f" % TempStart)))
	Magnet.root.MagnetGoToSet(Field, int(not Persist), rate = 2.2)
	time.sleep(5)
	
	# Wait for the timeout
	NowTime = datetime.now()
	Remaining = Timeout*60.0 - (NowTime-SetTime).seconds
	TCurrent, TStatus = TempSocketRead(TClient, TCurrent, TStatus)

	while (TStatus != "1") and (Remaining > 0):
		NowTime = datetime.now()
		Remaining = Timeout*60.0 - float((NowTime-SetTime).seconds)
		print "Time remaining = %.2f minutes" % (Remaining/60.0)
		TCurrent, TStatus = TempSocketRead(TClient, TCurrent, TStatus)
		time.sleep(10)

	# Setup L plot windows
	NLias = len(Lias)
	NGraph = NLias
	GraphWin = rpg.GraphicsWindow(title="Vg Sweep")
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
		DataList = []
		
		# Read the Keithley
		if ReadKeithley:
			Kthly.ReadData()
		DataList = np.hstack([DataList,Kthly.Data])

		# Read the magnet
		Field = Magnet.root.MagnetReadField()
		DataList = np.hstack([DataList,Field])

		# Read the temperature
		TCurrent, TStatus = TempSocketRead(TClient, TCurrent, TStatus)
		DataList = np.hstack([DataList,TCurrent])
		
		# Read the Lockins
		for inst in Lias:
			inst.ReadData()
			DataList = np.hstack([DataList,inst.Data])


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
	
	
	Kthly.Ramp(FinishGate)

	if Kthly.Output and FinishGate == 0.0:
		Kthly.SwitchOutput()

	TempSocketWrite(TClient," ".join(("SET","%.2f" % TempFinal)))
	# Copy the file to the network
	time.sleep(5)
	try:
		shutil.copy(FilePath,NetDir)
	except OSError:
		pass

	return FilePath

#########################################################################
########  B SWEEP ###########
#####################################################

def DoBSweep(GraphProc,rpg,DataFile, Magnet, Lias, Kthly, Vg = 0,
		Start = 0, Stop = 0, FinishHeater = 0, Rate = 1.6,
		Delay = 1.0, Timeout = -1, SetTemp = -1, VPreRamp = [],
		HeaterConst = [], CycleGate = 0, CycleDelay = 0.05,
		GateStep = 0.1, FinishGate = 0.0, ReadKeithley = False,
		comment = "No comment!"):
	
	# Bind to the Temperature socket 
	TClient = SocketUtils.SockClient('localhost', 18871)
	TCurrent = "0"
	TStatus = "-1"
	time.sleep(5)
	
	# Go to the start field with switch heater on as the final stage
	# This process is done synchronously for the moment and we hang
	# on it's output, Note rate is set to be 2.2 A/m

	SetTime = datetime.now()

	# Go to the specified field and finish in persistent mode
	if SetTemp > 0:
		TempSocketWrite(TClient," ".join(("SET","%.2f" % SetTemp)))
	if HeaterConst:
		TempSocketWrite(TClient," ".join(("CST","%.2f" % HeaterConst)))	
	Magnet.root.MagnetGoToSet(Start, 1, rate = 2.2)

	# Wait for the timeout
	NowTime = datetime.now()
	Remaining = Timeout*60.0 - (NowTime-SetTime).seconds
	TCurrent, TStatus = TempSocketRead(TClient, TCurrent, TStatus)
	while TStatus == "0" and Remaining > 0:
		NowTime = datetime.now()
		Remaining = Timeout*60.0 - (NowTime-SetTime).seconds*1.0
		print "Time remaining = %.2f minutes" % (Remaining/60.0)
		TCurrent, TStatus = TempSocketRead(TClient, TCurrent, TStatus)
		time.sleep(10)
	

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

	
	GraphWin = rpg.GraphicsWindow(title="B Sweep")
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
	Magnet.root.MagnetGoToSet(Stop, 1, rate = Rate, sweep = 1)	

	Field = Magnet.root.MagnetReadField()
	#print Field
	while abs(Field - Stop) >= 0.01:
		DataList = np.zeros((4+NLias*4,))
		
		# Read the Keithley
		if ReadKeithley:
			Kthly.ReadData()
		DataList[0:2] = Kthly.Data
			
		# Read the magnet
		Field = Magnet.root.MagnetReadField()
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

	# Copy the file to the network
	time.sleep(5)
	try:
		shutil.copy(FilePath,NetDir)
	except OSError:
		pass

	if FinishHeater == 0:
		Magnet.root.MagnetGoToSet(Stop, 0)

	return FilePath

###########################################
###########################################

def Vg2D(GraphProc, rpg, DataFile, Magnet, Lias, Kthly,
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
				rpg,DataFile,Magnet,Lias,Kthly,
				Start=VgSet[0],Stop=VgSet[1],Step=VgStep,
				Samples=VgSamples,Finish = VgFinish,
				Timeout=Timeout,Delay=Delay,
				SetTemp=SetTemp,
				Field = X[i],
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
	if VgFinish != 0.0:
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
		Magnet,Lias, Kthly,
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
		DoBSweep(GraphProc,rpg,DataFile, Magnet,
				Lias, Kthly, Vg = VGate,
				Start = BLim[0], Stop = BLim[1],
				FinishHeater = 1, Rate = Rate,
				Delay = Delay, Timeout = Timeout,
				SetTemp = SetTemp, VPreRamp = VPreRamp,
				CycleGate = CycleGate,
				FinishGate = Source[i+1], comment = comment)
		BLim = BLim[::-1]

	Magnet.root.MagnetGoToSet(0,0,rate=2.2)

################################################
################################################

def DoVISweep(GraphProc, rpg, DataFile, Magnet, KthMeas, KthGate,
		Field = 0, Persist = True, VStart = 0, VStop = 0, VStep = 1e-4,
		VGate=0, SetTemp=-1, ReturnData = False, Delay = 0,
		Samples = 1, Timeout = -1, comment = "No comment!", **kwargs):

	# Bind to the Temperature socket 
	TClient = SocketUtils.SockClient('localhost', 18871)
	TCurrent = "0.0"
	TStatus = "-1"
	# Wait for the connection
	time.sleep(5)

	# Set the source voltages
	
	if "VCustom" in kwargs.keys():
		Source = kwargs["VCustom"]
	elif "mid" in kwargs.keys():
		Source = KthMeas.RunSweep(VStart,VStop,VStep,Delay,mid=kwargs["mid"])
	else:
		Source = KthMeas.RunSweep(VStart,VStop,VStep,Delay)
		
	SetTime = datetime.now()

	# Go to the specified field and finish in persistent mode
	if SetTemp > 0:
		TempSocketWrite(TClient," ".join(("SET","%.2f" % SetTemp)))
	Magnet.root.MagnetGoToSet(Field, int(not Persist), rate = 2.2)

	# Wait for the timeout
	NowTime = datetime.now()
	Remaining = Timeout*60.0 - (NowTime-SetTime).seconds
	TCurrent, TStatus = TempSocketRead(TClient, TCurrent, TStatus)
	while TStatus == "0" and Remaining > 0:
		NowTime = datetime.now()
		Remaining = Timeout*60.0 - float((NowTime-SetTime).seconds)
		print "Time remaining = %.2f minutes" % (Remaining/60.0)
		TCurrent, TStatus = TempSocketRead(TClient, TCurrent, TStatus)
		time.sleep(10)
	
	# Setup plot windows
	GraphWin = rpg.GraphicsWindow(title="Vg Sweep")
	PlotData = GraphProc.transfer([])
	GraphWin.resize(500,500)
	Plot = []
	Curve = []
	for i in range(2):
		Plot.append(GraphWin.addPlot())
		Curve.append(Plot[i].plot(pen='y'))
		GraphWin.nextRow()
	
	StartTime = datetime.now()

	Writer, FilePath, NetDir = OpenCSVFile(DataFile,
			StartTime,[],[KthMeas],comment = comment)

	if VGate != 0:
		KthGate.Ramp(VGate)
	else:
		KthGate.SetSource(0)

	if not KthGate.Output:
		KthGate.SwitchOutput()
	
	KthMeas.Ramp(Source[0])

	if not KthMeas.Output:
		KthMeas.SwitchOutput()

	time.sleep(10)
	print "Starting measurement!"

	for i in xrange(len(Source)):
		DataList = []
		
		# Set the Keithley
		KthMeas.SetSource(Source[i])
		for j in xrange(Samples):
		
			# Read the Keithley
			KthGate.ReadData()
			DataList = np.hstack([DataList,KthGate.Data])

			# Read the magnet
			Field = Magnet.root.MagnetReadField()
			DataList = np.hstack([DataList,Field])

			# Read the temperature
			TCurrent, TStatus = TempSocketRead(TClient, TCurrent, TStatus)
			DataList = np.hstack([DataList,TCurrent])
			
			# Read the Keithley
			KthMeas.ReadData()
			DataList = np.hstack([DataList,KthMeas.Data])

			# Sleep
			time.sleep(Delay)
		
		DataList = np.reshape(DataList,[Samples,len(DataList)/Samples])
		
		# Save the data
		for j in xrange(Samples):
			Writer.writerow(DataList[j,:])
		
		# Package the data and send it for plotting
		Data = DataList[:,[0,1,4,5]]
		# Pass data to the plots
		PlotData.extend(np.mean(Data,0),_callSync = "off")
		for i in range(2):
			Curve[i].setData(x=PlotData[0+2*i::4],y=PlotData[1+2*i::4],_callSync = "off")

	# We are finished, now switch off the Keithley
	if VStop != 0:
		KthMeas.Ramp(0)
	else:
		KthMeas.SetSource(0)

	KthMeas.SwitchOutput()
	
	KthGate.Ramp(0)
	KthGate.SwitchOutput()
		

	# Copy the file to the network
	time.sleep(5)
	try:
		shutil.copy(FilePath,NetDir)
	except OSError:
		pass

	GraphWin.close()

	if ReturnData:
		return FilePath, DataList
	else:
		return FilePath
	
