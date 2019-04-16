#!/usr/bin/python
# -*- coding: utf-8 -*-

"""

Sub programs for doing the measurements

original author : Eoin O'Farrell
current author : Huang Junye
last edited : Apr 2019

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
pg.setConfigOption("useWeave", False)
import pyqtgraph.multiprocess as mp
from pyqtgraph.Qt import QtCore, QtGui

from datetime import datetime
import os
import csv
import subprocess
import shutil
import asyncore
import h5py
from scipy import interpolate

# Import sub routines files
import utils.SocketUtils as SocketUtils
import utils.MeasurementSubs_DF as MeasurementUtils

from itertools import cycle
from sys import exit

#################################################
#			Device Sweep
#################################################
	
def DoDeviceSweep(GraphProc,rpg,DataFile,SweepInst,ReadInst,
		SetInst = [], SetValue = [], FinishValue = [], PreValue = [],
		BSet = 0. , Persist = True, IgnoreMagnet = False,
		SweepStart = 0., SweepStop = 0., SweepStep = 1.,
		SweepFinish = 0.0,SweepMid = [],
		Delay = 0., Sample = 1,
		TSet = -1,
		Timeout = -1, Wait = 0.5,
		ReturnData = False,MakePlot=True,
		SocketDataNumber=2,					# 5 for 9T, 2 for Dilution fridge
		Comment = "No comment!", NetworkDir = "Z:\\DATA"):

	# Bind sockets 
	MClient, MSocket, TClient, TSocket = MeasurementUtils.InitializeSockets()

	NRead = len(ReadInst)

	# Set the sweep voltages

	Sweep = MeasurementUtils.GenerateDeviceSweep(SweepStart,SweepStop,SweepStep,Mid=SweepMid)
	SetTime = datetime.now()


	# Go to the set temperature and magnetic field and finish in persistent mode
	if TSet > 0:
		Msg = " ".join(("SET","%.2f" % TSet))
		MeasurementUtils.SocketWrite(TClient,Msg)
		print("Wrote message to temperature socket \"%s\"" % Msg)
	if not IgnoreMagnet:
		Msg = " ".join(("SET","%.4f" % BSet,"%d" % int(not Persist)))
		MeasurementUtils.SocketWrite(MClient,Msg)
		print("Wrote message to Magnet socket \"%s\"" % Msg)
	time.sleep(5)

	# give precedence to the magnet and wait for the timeout
	TSocket = MeasurementUtils.SocketRead(TClient, TSocket)
	MSocket = MeasurementUtils.SocketRead(MClient, MSocket)
	if not IgnoreMagnet:
		while MSocket[1] != 1:
			print("Waiting for magnet!")
			time.sleep(15)
			TSocket = MeasurementUtils.SocketRead(TClient, TSocket)
			MSocket = MeasurementUtils.SocketRead(MClient, MSocket)
	
	NowTime = datetime.now()
	Remaining = Timeout*60.0 - float((NowTime-SetTime).seconds)
	while (TSocket[1] != 1) and (Remaining > 0):
		NowTime = datetime.now()
		Remaining = Timeout*60.0 - float((NowTime-SetTime).seconds)
		print("Waiting for temperature ... time remaining = %.2f minutes" % (Remaining/60.0))
		TSocket = MeasurementUtils.SocketRead(TClient, TSocket)
		MSocket = MeasurementUtils.SocketRead(MClient, MSocket)	
		time.sleep(15)
	

	# Setup L plot windows
	if MakePlot:
		GraphWin = rpg.GraphicsWindow(title="Device Sweep...")
		GraphWin.resize(500,150*NRead)
		Plot = [None] * NRead
		Curve = [None] * NRead
		for i in range(NRead):
			Plot[i] = GraphWin.addPlot()
			Curve[i] = Plot[i].plot(pen='y')
			if i < NRead - 1:
				GraphWin.nextRow()

	if ReturnData or MakePlot:
		PlotData = GraphProc.transfer([])		

	if SetInst:
		for Set in [PreValue, SetValue]:
			if Set:
				"Pre and Set ramps"
				if len(SetInst) != len(Set):
					if len(Set) > len(SetInst):
						Set = Set[0:len(SetInst)]
					else:
						Set = Set + [0]*(len(SetInst)-len(Set))
				for i,v in enumerate(SetInst):
					print("Ramping %s to %.2e" % (v.Name, Set[i]))
					v.Ramp(Set[i])

	if SweepStart != 0:
		SweepInst.Ramp(SweepStart)
	else:
		SweepInst.SetOutput(0)

	if not SweepInst.Output:
		SweepInst.SwitchOutput()
	
	SweepInst.ReadData()

	if Wait >= 0.0:
		print("Waiting %.2f minute!" % Wait)		
		WaitTime = datetime.now()
		Remaining = Wait*60.0
		while (Remaining > 0):
			NowTime = datetime.now()
			Remaining = Wait*60.0 - float((NowTime-WaitTime).seconds)
			print("Waiting ... time remaining = %.2f minutes" % (Remaining/60.0))
			TSocket = MeasurementUtils.SocketRead(TClient, TSocket)
			MSocket = MeasurementUtils.SocketRead(MClient, MSocket)	
			time.sleep(15)
	print("Starting measurement!")

	StartTime = datetime.now()

	Writer, FilePath, NetDir = MeasurementUtils.OpenCSVFile(DataFile,StartTime,
						ReadInst,SweepInst=[SweepInst],SetInst=SetInst,
						Comment=Comment, NetworkDir=NetworkDir)

	# This is the main measurement loop

	StartColumn, DataVector = MeasurementUtils.GenerateDataVector(SocketDataNumber,ReadInst,Sample,
							SweepInst=True,SetValue = SetValue)
	
	for i,v in enumerate(Sweep):

		# Set the Keithley
		SweepInst.SetOutput(v)

		TSocket = MeasurementUtils.SocketRead(TClient, TSocket)
		MSocket = MeasurementUtils.SocketRead(MClient, MSocket)

		DataVector[:,0] = MSocket[0]
		DataVector[:,1:SocketDataNumber] = TSocket[0]
		DataVector[:,SocketDataNumber] = v

		for j in range(Sample):

			for i,v in enumerate(ReadInst):
				v.ReadData()
				DataVector[j,StartColumn[i]:StartColumn[i+1]] = v.Data
	
			# Sleep
			if Delay >= 0.0:
				time.sleep(Delay)
		
		# Save the data
		for j in range(Sample):
			Writer.writerow(DataVector[j,:])

		# Package the data and send it for plotting
		
		if MakePlot or ReturnData:
			ToPlot = np.empty((NRead+1))
			ToPlot[0] = DataVector[-1,SocketDataNumber]
			for j in range(NRead):
				ToPlot[j+1] = DataVector[-1,StartColumn[j]+ReadInst[j].DataColumn]
	
			# Pass data to the plots
			PlotData.extend(ToPlot,_callSync = "off")
		if MakePlot:
			for j in range(NRead):
				Curve[j].setData(x=PlotData[0::(NRead+1)],y=PlotData[j+1::(NRead+1)],_callSync = "off")

	SweepInst.Ramp(SweepFinish)

	# if the finish is zero switch it off
	if SweepFinish == 0.0:
		SweepInst.SwitchOutput()

	if SetInst:
		if len(FinishValue) != len(SetInst):
			print("Warning: len(SetInst) != len(FinishValue)")
			#print SetInst, FinishValue
			if len(FinishValue) > len(SetInst):
				FinishValue = FinishValue[0:len(SetInst)]
			else:
				FinishValue = FinishValue + SetValue[len(FinishValue):len(SetInst)]
		"Final ramps"
		for i,v in enumerate(SetInst):
			print("Ramping %s to %.2e" % (v.Name, FinishValue[i]))
			v.Ramp(FinishValue[i])
	
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
#	if MakePlot:
#		GraphWin.close()
	MClient.close()
	TClient.close()

	if ReturnData:
		return DataList
	else:
		return

##################################################
# Sweep T or B
###################################################

def DoFridgeSweep(GraphProc,rpg,DataFile,
		ReadInst,
		SetInst = [], SetValue = [], PreValue = [], FinishValue = [],
		FridgeSweep = "B", FridgeSet = 0.0,
		SweepStart = 0.0, SweepStop = 1.0, SweepRate = 1.0, SweepFinish = 0.0, # Either T/min or mK/min
		Persist = False, # Magnet final state
		Delay = 0.0, Sample = 1,
		Timeout = -1, Wait = 0.5, MaxOverTime = 5,
		ReturnData = False, SocketDataNumber = 2,
		Comment = "No comment!", NetworkDir = "Z:\\DATA",
		IgnoreMagnet = False):

	# Bind sockets 
	MClient, MSocket, TClient, TSocket = MeasurementUtils.InitializeSockets()

	if FridgeSweep == "B":
		BSweep = True
		if IgnoreMagnet:
			print("Error cannot ignore magnet for BSweep! Exiting!")
			exit(0)
	else:
		BSweep = False

	NRead = len(ReadInst)

	SetTime = datetime.now()

	if BSweep:
		BSet = [SweepStart, SweepStop]
		TSet = [FridgeSet]
		StartPersist = False
	else:
		BSet = [FridgeSet]
		TSet = [SweepStart, SweepStop]
		StartPersist = Persist
	
	# Tell the magnet daemon to go to the inital field and set the temperature
	Msg = " ".join(("SET","%.2f" % TSet[0]))
	MeasurementUtils.SocketWrite(TClient,Msg)
	print("Wrote message to temperature socket \"%s\"" % Msg)

	Msg = " ".join(("SET","%.4f" % BSet[0],"%d" % int(not StartPersist)))
	MeasurementUtils.SocketWrite(MClient,Msg)
	print("Wrote message to Magnet socket \"%s\"" % Msg)
	time.sleep(5)

	# give precedence to the magnet and wait for the timeout
	TSocket = MeasurementUtils.SocketRead(TClient, TSocket)
	MSocket = MeasurementUtils.SocketRead(MClient, MSocket)
	if not IgnoreMagnet:
		while MSocket[1] != 1:
			print("Waiting for magnet!")
			time.sleep(15)
			TSocket = MeasurementUtils.SocketRead(TClient, TSocket)
			MSocket = MeasurementUtils.SocketRead(MClient, MSocket)
	
	NowTime = datetime.now()
	Remaining = Timeout*60.0 - float((NowTime-SetTime).seconds)
	while (TSocket[1] != 1) and (Remaining > 0):
		NowTime = datetime.now()
		Remaining = Timeout*60.0 - float((NowTime-SetTime).seconds)
		print("Waiting for temperature ... time remaining = %.2f minutes" % (Remaining/60.0))
		TSocket = MeasurementUtils.SocketRead(TClient, TSocket)
		MSocket = MeasurementUtils.SocketRead(MClient, MSocket)	
		time.sleep(15)
	
	# Setup L plot windows
	GraphWin = rpg.GraphicsWindow(title="Fridge Sweep...")
	PlotData = GraphProc.transfer([])
	GraphWin.resize(500,150*NRead)
	Plot = []
	Curve = []
	for i in range(NRead):
		Plot.append(GraphWin.addPlot())
		Curve.append(Plot[i].plot(pen='y'))
		GraphWin.nextRow()

	# Turn on the Keithley and then wait for a bit

	if SetInst:
		for Set in [PreValue, SetValue]:
			if Set:
				if len(SetInst) != len(Set):
					if len(Set) > len(SetInst):
						Set = Set[0:len(SetInst)]
					else:
						Set = Set + [0]*(len(SetInst)-len(Set))
				for i,v in enumerate(SetInst):
					print("Ramping %s to %.2e" % (v.Name, Set[i]))
					v.Ramp(Set[i])
	
	if Wait >= 0.0:
		print("Waiting %.2f minute!" % Wait)		
		WaitTime = datetime.now()
		Remaining = Wait*60.0
		while (Remaining > 0):
			NowTime = datetime.now()
			Remaining = Wait*60.0 - float((NowTime-WaitTime).seconds)
			print("Waiting ... time remaining = %.2f minutes" % (Remaining/60.0))
			TSocket = MeasurementUtils.SocketRead(TClient, TSocket)
			MSocket = MeasurementUtils.SocketRead(MClient, MSocket)	
			time.sleep(15)
	print("Starting measurement!")

	StartTime = datetime.now()

	Writer, FilePath, NetDir = MeasurementUtils.OpenCSVFile(DataFile,StartTime,
						ReadInst,SetInst=SetInst,
						Comment=Comment, NetworkDir = NetworkDir)

	# This is the main measurement loop

	StartColumn, DataVector = MeasurementUtils.GenerateDataVector(SocketDataNumber,ReadInst,Sample,
							SetValue = SetValue)

	if BSweep:
		Msg = " ".join(("SWP","%.4f" % BSet[1], "%.4f" % SweepRate,"%d" % int(not Persist)))
		MeasurementUtils.SocketWrite(MClient,Msg)
		print("Wrote message to magnet socket \"%s\"" % Msg)
	else:
		Msg = " ".join(("SWP","%.4f" % TSet[1], "%.4f" % SweepRate, "%.2f" % MaxOverTime))
		MeasurementUtils.SocketWrite(TClient,Msg)
		print("Wrote message to temperature socket \"%s\"" % Msg)	

	TSocket = MeasurementUtils.SocketRead(TClient, TSocket)
	MSocket = MeasurementUtils.SocketRead(MClient, MSocket)
	if BSweep:
		FridgeStatus = MSocket[-1]
	else:
		FridgeStatus = TSocket[-1]


	while FridgeStatus != 0: 
		time.sleep(1)
		#print FridgeStatus
		TSocket = MeasurementUtils.SocketRead(TClient, TSocket)
		MSocket = MeasurementUtils.SocketRead(MClient, MSocket)
		if BSweep:
			FridgeStatus = MSocket[-1]
		else:
			FridgeStatus = TSocket[-1]

	SweepTimeLength = abs(SweepStart-SweepStop)/SweepRate # In minutes
	SweepTimeLength = SweepTimeLength + MaxOverTime
	#print SweepTimeLength
	StartTime = datetime.now()
	SweepTimeout = False
	
	#print Field
	while FridgeStatus == 0 and (not SweepTimeout):
		
		TSocket = MeasurementUtils.SocketRead(TClient, TSocket)
		MSocket = MeasurementUtils.SocketRead(MClient, MSocket)
		if BSweep:
			FridgeStatus = MSocket[-1]
		else:
			FridgeStatus = TSocket[-1]

		DataVector[:,0] = MSocket[0]
		DataVector[:,1:SocketDataNumber] = TSocket[0]

		for j in range(Sample):
		
			for i,v in enumerate(ReadInst):
				v.ReadData()
				DataVector[j,StartColumn[i]:StartColumn[i+1]] = v.Data

			# Sleep
			time.sleep(Delay)
		
		# Save the data
		for j in range(Sample):
			Writer.writerow(DataVector[j,:])

		ToPlot = np.empty((NRead+1))
		if BSweep:
			ToPlot[0] = DataVector[-1,0]
		else:
			ToPlot[0] = DataVector[-1,1]
		for j in range(NRead):
			ToPlot[j+1] = DataVector[-1,StartColumn[j]+ReadInst[j].DataColumn]
	
		# Pass data to the plots
		PlotData.extend(ToPlot,_callSync = "off")
		for j in range(NRead):
			Curve[j].setData(x=PlotData[0::(NRead+1)],y=PlotData[j+1::(NRead+1)],_callSync = "off")
		
		if not BSweep:
			dT = datetime.now() - StartTime
			dTMin = dT.seconds/60.0
			SweepTimeout = dTMin > SweepTimeLength
		else:
			SweepTimeout = False


	# Loop is finished
	if SetInst:
		if len(FinishValue) != len(SetInst):
			if len(FinishValue) > len(SetInst):
				FinishValue = FinishValue[0:len(SetInst)]
			else:
				FinishValue = FinishValue + SetValue[len(FinishValue):len(SetInst)]
		for i,v in enumerate(SetInst):
			print("Ramping %s to %.2e" % (v.Name, FinishValue[i]))
			v.Ramp(FinishValue[i])
	
	if ReturnData:
		DataList = [None]*(NRead+1)
		DataList[0] = PlotData[0::NRead+1]
		for i in range(1,NRead+1):
			DataList[i]=PlotData[i::NRead+1]
	
	if BSweep:
		Msg = " ".join(("SET","%.4f" % SweepFinish,"%d" % int(not Persist)))
		MeasurementUtils.SocketWrite(MClient,Msg)
		print("Wrote message to Magnet socket \"%s\"" % Msg)
	else:
		Msg = " ".join(("SET","%.2f" % SweepFinish))
		MeasurementUtils.SocketWrite(TClient,Msg)
		print("Wrote message to temperature socket \"%s\"" % Msg)

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
		return DataList
	else:
		return

"""
	2D data acquisition either by sweeping a device parameter
	or by sweepng a fridge parameter
	 The program decides which of these to do depending on if the
	the variable "SweepInst" is assigned.
	i.e. if "SweepInst" is assigned the device is swept and the
	fridge parameter is stepped.
	If the device is being swept the variable "FridgeRate" is the size
	of successive steps of either T or B.
	If the fridge is being swept the first SetInst is stepped by the
	"DeviceStep"
	
	For the case of successive B sweeps the fridge will be swept
	forwards and backwards
	e.g.	Vg = -60 V B = -9 --> +9 T
		Vg = -50 V B = +9 --> -9 T
		etc ...
	Note that in this case the first "SetValue" will be overwritten
	therefore a dummy e.g. 0.0 should be written in the case that there
	are additional SetInst
"""

def DeviceFridge2D(GraphProc, rpg, DataFile,
		ReadInst, SweepInst = [], SetInst=[],
		SetValue = [], PreValue = [], FinishValue = [],
		FridgeSweep = "B", FridgeSet = 0.0,
		DeviceStart = 0.0, DeviceStop = 1.0, DeviceStep = 0.1, DeviceFinish = 0.0,
		DeviceMid = [],
		FridgeStart = 0.0, FridgeStop = 1.0, FridgeRate = 0.1,
		Delay = 0, Sample = 1,
		Timeout = -1, Wait = 0.0,
		Comment = "No comment!", NetworkDir = "Z:\\DATA",
		Persist=True, XCustom = []):


	if SweepInst:
		SweepDevice = True
	else:
		SweepDevice = False

	if FridgeSweep == "B":
		BSweep = True
	else:
		BSweep = False

	if not FinishValue:
		FinishValue = list(SetValue)

	# We step over the x variable and sweep over the y

	if SweepDevice:
		XVec = np.hstack((np.arange(FridgeStart,FridgeStop,FridgeRate),FridgeStop))
		YStart = DeviceStart
		YStop = DeviceStop
				YStep = DeviceStep
	else:
		XVec = np.hstack((np.arange(DeviceStart,DeviceStop,DeviceStep),DeviceStop))
		YStart = FridgeStart
		YStop = FridgeStop
				YStep = FridgeRate

	if not not(XCustom):
		XVec = XCustom

		if SweepDevice:
				YLen = len(MeasurementUtils.GenerateDeviceSweep(DeviceStart,
									DeviceStop,DeviceStep,Mid=DeviceMid))
		else:
				YLen = abs(YStart-YStop)/YStep+1

	NRead = len(ReadInst) 
	Plt2DWin = [None]*NRead
	VwBox = [None]*NRead
	Imv = [None]*NRead
	ZArray = [np.zeros((len(XVec),YLen)) for i in range(NRead)]
	
		if SweepDevice:
			for i in range(NRead):
				Plt2DWin[i] = rpg.QtGui.QMainWindow()
				Plt2DWin[i].resize(500,500)
				VwBox[i] = rpg.ViewBox(invertY = True)
				Imv[i] = rpg.ImageView(view=rpg.PlotItem(viewBox=VwBox[i]))
				Plt2DWin[i].setCentralWidget(Imv[i])
				Plt2DWin[i].setWindowTitle("ReadInst %d" % i)
				Plt2DWin[i].show()
				VwBox[i].setAspectLocked(False)


			YScale = YStep
			XScale = (XVec[-2]-XVec[0])/np.float(len(XVec)-1)

			for j in range(NRead):
				Imv[j].setImage(ZArray[j],scale=(XScale,YScale),pos=(XVec[0],YStart))

	for i,v in enumerate(XVec):
	
		if SweepDevice:
			#Sweep the device and fix T or B
			if BSweep:

				DataList = DoDeviceSweep(GraphProc,rpg,DataFile,
						SweepInst,ReadInst,SetInst = SetInst,
						SetValue = SetValue,
						FinishValue = FinishValue,
						PreValue = PreValue,
						BSet = v,
						Persist = False,
						SweepStart = DeviceStart,
						SweepStop = DeviceStop,
						SweepStep = DeviceStep,
						SweepFinish = DeviceFinish,
						SweepMid = DeviceMid,
						Delay = Delay, Sample = Sample,
						TSet = FridgeSet,
						Timeout = Timeout, Wait = Wait,
						ReturnData = True, MakePlot = False,
						Comment = Comment, NetworkDir = NetworkDir)
			else:
				DataList = DoDeviceSweep(GraphProc,rpg,DataFile,
						SweepInst,ReadInst,SetInst = SetInst,
						SetValue = SetValue,
						FinishValue = FinishValue, PreValue = PreValue,
						BSet = FridgeSet, Persist = True,
						SweepStart = DeviceStart, SweepStop = DeviceStop,
						SweepStep = DeviceStep,
						SweepMid = DeviceMid,
						Delay = Delay, Sample = Sample,
						TSet = v,
						Timeout = Timeout, Wait = Wait,
						ReturnData = True, MakePlot = False,
						Comment = Comment, NetworkDir = NetworkDir)

		else:

			SetValue[0] = v
			if i == len(XVec)-1:
				FinishValue[0] = 0.0
			else:
				FinishValue[0] = XVec[i+1]
			
			# Fix the device and sweep T or B
			if BSweep:
				DataList = DoFridgeSweep(GraphProc,rpg,DataFile,
							ReadInst,SetInst = SetInst, SetValue = SetValue,
							FinishValue = FinishValue, PreValue = PreValue,
							FridgeSweep = "B", FridgeSet = FridgeSet,
							SweepStart = FridgeStart, SweepStop = FridgeStop,
							SweepRate = FridgeRate, SweepFinish = FridgeStop,
							Persist = False,
							Delay = Delay, Sample = Sample,
							Timeout = Timeout, Wait = Wait,
							ReturnData = True,
							Comment = Comment, NetworkDir = NetworkDir)

				TmpSweep = [FridgeStart, FridgeStop]
				FridgeStart = TmpSweep[1]
				FridgeStop = TmpSweep[0]

			else:
				DataList = DoFridgeSweep(GraphProc,rpg,DataFile,
							ReadInst,SetInst = SetInst, SetValue = SetValue,
							FinishValue = FinishValue, PreValue = PreValue,
							FridgeSweep = "T", FridgeSet = FridgeSet,
							SweepStart = FridgeStart, SweepStop = FridgeStop,
							SweepRate = FridgeRate, SweepFinish = FridgeStop,
							Persist = True,
							Delay = Delay, Sample = Sample,
							Timeout = Timeout, Wait = Wait,
							ReturnData = True,
							Comment = Comment, NetworkDir = NetworkDir)
							

#		Ydata = DataList[0]
				if SweepDevice:
					for j in range(NRead):
					ZArray[j][i,:] = DataList[j+1]
					Imv[j].setImage(ZArray[j],pos=(XVec[0],YStart),scale=(XScale,YScale))

	MClient = SocketUtils.SockClient('localhost', 18861)
	time.sleep(2)
	MeasurementUtils.SocketWrite(MClient,"SET 0.0 0")
	time.sleep(2)
	MClient.close()

#	for i in range(NRead):
#		Imv[i].close()
#		VwBox[i].close()
#		Plt2DWin[i].close()
	
	time.sleep(2)

	return

#########################################################################
#			  SWEEP two device parameters e.g. backgate bias, one is stepped
#		the other is swept
########################################################################

def DeviceDevice2D(GraphProc, rpg, DataFile,
		ReadInst, SweepInst = [], StepInst = [],
		SetInst=[], SetValue = [], PreValue = [], FinishValue = [],
		FridgeSetB = 0.0, FridgeSetT = 0.0,
		SweepStart = 0.0, SweepStop = 1.0, SweepStep = 0.1, SweepFinish = 0.0, SweepMid = [],
		StepStart = 0.0, StepStop = 1.0, StepStep = 0.1, StepFinish = 0.0,
		#FridgeStart = 0.0, FridgeStop = 1.0, FridgeRate = 0.1,
		Delay = 0, Sample = 1,MakePlot=False,
		Timeout = -1, Wait = 0.0,
		Comment = "No comment!", NetworkDir = "Z:\\DATA",
		Persist=True, XCustom = [],IgnoreMagnet=False):


	if not FinishValue:
		FinishValue = list(SetValue)

	# We step over the x variable and sweep over the y
	
	setInst = list(SetInst) 
	setInst.append(StepInst)

	# X is the step axis
	# Y is the sweep axis

	XVec = np.hstack((np.arange(StepStart,StepStop+StepStep,StepStep),StepFinish))
	YVec = MeasurementUtils.GenerateDeviceSweep(SweepStart,SweepStop,SweepStep,Mid=SweepMid)
	YMax = np.max(YVec)
	YMin = np.min(YVec)
	#print YMax,YMin

	if XCustom:
		XVec = XCustom

	NRead = len(ReadInst) 
	Plt2DWin = [None]*NRead
	VwBox = [None]*NRead
	Imv = [None]*NRead
	ZArray = [np.zeros((len(XVec)-1,len(YVec))) for i in range(NRead)]
	
	for i in range(NRead):
		Plt2DWin[i] = rpg.QtGui.QMainWindow()
		Plt2DWin[i].resize(500,500)
		VwBox[i] = rpg.ViewBox()
		#VwBox[i] = rpg.PlotItem()
		VwBox[i].enableAutoRange()
		Imv[i] = rpg.ImageView(view=rpg.PlotItem(viewBox=VwBox[i]))
		#Imv[i] = rpg.ImageView(view=VwBox[i])
		Plt2DWin[i].setCentralWidget(Imv[i])
		Plt2DWin[i].setWindowTitle("ReadInst %d" % i)
		Plt2DWin[i].show()
		VwBox[i].invertY(True)
		VwBox[i].setAspectLocked(False)

	#YScale = (YVec[-1]-YVec[0])/len(YVec)
	YScale = (YMax-YMin)/np.float(len(YVec))
	XScale = (XVec[-2]-XVec[0])/np.float(len(XVec)-1)

	#print XScale
	#print YScale

	for j in range(NRead):
		Imv[j].setImage(ZArray[j],pos=(XVec[0],YMin),scale=(XScale,YScale))

	sets = [None] * (len(SetValue)+1)
	if len(SetValue) > 0:
		sets[:-1] = SetValue[:]
	finishs = [None] * (len(FinishValue)+1)
	if len(FinishValue) > 0:
		finishs[:-1] = FinishValue[:]

	for i,v in enumerate(XVec[:-1]):
	
		sets[-1] = v
		finishs[-1] = XVec[i+1]
		#print finishs
		#print setInst
		#pres = PreValue + [v]

		DataList = DoDeviceSweep(GraphProc,rpg,DataFile,
					SweepInst,ReadInst,SetInst = setInst,SetValue = sets,
					FinishValue = finishs,
					BSet = FridgeSetB, TSet = FridgeSetT, Persist = Persist,
					SweepStart = SweepStart, SweepStop = SweepStop,
					SweepStep = SweepStep, SweepFinish = SweepFinish,
					SweepMid = SweepMid,
					Delay = Delay, Sample = Sample,
					Timeout = Timeout, Wait = Wait,
					ReturnData = True,MakePlot=MakePlot,
					Comment = Comment, NetworkDir = NetworkDir,
					IgnoreMagnet=IgnoreMagnet)
						

#		Ydata = DataList[0]

		for j in range(NRead):
#			ZItp = interpolate.interp1d(Ydata,DataList[j+1],bounds_error=False,fill_value=0.0)
#			ZArray[j][i,:] = ZItp(YVec)
			ZArray[j][i,:] = DataList[j+1]
			Imv[j].setImage(ZArray[j],pos=(XVec[0],YMin),scale=(XScale,YScale))

	MClient = SocketUtils.SockClient('localhost', 18861)
	time.sleep(2)
	MeasurementUtils.SocketWrite(MClient,"SET 0.0 0")
	time.sleep(2)
	MClient.close()

#	for i in range(NRead):
#		Imv[i].close()
#		VwBox[i].close()
#		Plt2DWin[i].close()
	
	time.sleep(2)

	return
	
