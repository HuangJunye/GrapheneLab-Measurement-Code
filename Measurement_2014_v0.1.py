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
from scipy import interpolate

import VisaSubs as VisaSubs
import SrsLia as LIA
import Keithley_2014_v0_2 as keithley
import SocketUtils as SocketUtils
import MeasurementSubs_2014 as MeasurementUtils

from itertools import cycle

#################################################
#            Device Sweep
#################################################
	
def DoDeviceSweep(GraphProc,rpg,DataFile,SweepInst,ReadInst,
		SetInst = [], SetValue = [], FinishValue = [], PreValue = [],
		BSet = 0. , Persist = True, IgnoreMagnet = False,
		SweepStart = 0., SweepStop = 0., SweepStep = 1., SweepFinish = 0.0, SweepMid = [],
		Delay = 0, Sample = 1,
		TSet = -1,
		Timeout = -1, Wait = 1.0,
		ReturnData = False,SocketDataNumber = 5,
		Comment = "No comment!"):

	# Bind sockets 
	MClient, MSocket, TClient, TSocket = MeasurementUtils.InitializeSockets()

	NRead = len(ReadInst)

	# Set the sweep voltages

	Sweep = MeasurementUtils.GenerateDeviceSweep(SweepStart,SweepStop,SweepStep,Mid=SweepMid)
	SetTime = datetime.now()


	# Go to the set temperature and magnetic field and finish in persistent mode 4.52046,  0.000369189
	if TSet > 0:
		Msg = " ".join(("SET","%.2f" % TSet))
		MeasurementUtils.SocketWrite(TClient,Msg)
		print "Wrote message to temperature socket \"%s\"" % Msg
	if not IgnoreMagnet:
		Msg = " ".join(("SET","%.3f" % BSet,"%d" % int(not Persist)))
		MeasurementUtils.SocketWrite(MClient,Msg)
		print "Wrote message to Magnet socket \"%s\"" % Msg
	time.sleep(5)

	# give precedence to the magnet and wait for the timeout
	TSocket = MeasurementUtils.SocketRead(TClient, TSocket)
	MSocket = MeasurementUtils.SocketRead(MClient, MSocket)
	if (not IgnoreMagnet):
		while MSocket[1] != 1:
			print "Waiting for magnet!"
			time.sleep(15)
			TSocket = MeasurementUtils.SocketRead(TClient, TSocket)
			MSocket = MeasurementUtils.SocketRead(MClient, MSocket)
	
	NowTime = datetime.now()
	Remaining = Timeout*60.0 - float((NowTime-SetTime).seconds)
	while (TSocket[1] != 1) and (Remaining > 0):
		NowTime = datetime.now()
		Remaining = Timeout*60.0 - float((NowTime-SetTime).seconds)
		print "Waiting for temperature ... time remaining = %.2f minutes" % (Remaining/60.0)
		TSocket = MeasurementUtils.SocketRead(TClient, TSocket)
		MSocket = MeasurementUtils.SocketRead(MClient, MSocket)	
		time.sleep(15)
	

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

	if SetInst:
		for Set in [PreValue, SetValue]:
			if Set:
				if len(SetInst) != len(Set):
					if len(Set) > len(SetInst):
						Set = Set[0:len(SetInst)]
					else:
						Set = Set + [0]*(len(SetInst)-len(Set))
				for i,v in enumerate(SetInst):
					print "Ramping %s to %.2e" % (v.Name, Set[i])
					v.Ramp(Set[i])

	if SweepStart != 0:
		SweepInst.Ramp(SweepStart)
	else:
		SweepInst.SetOutput(0)

	if not SweepInst.Output:
		SweepInst.SwitchOutput()
	
	SweepInst.ReadData()

	if Wait >= 0.0:
		WaitTime = datetime.now()
		print "Waiting %.2f minute!" % Wait
		Remaining = Wait*60.0
		while Remaining > 0.0:
			NowTime = datetime.now()
			Remaining = Wait*60.0 - float((NowTime-WaitTime).seconds)
			print "Waiting ... time remaining = %.2f minutes" % (Remaining/60.0)
			TSocket = MeasurementUtils.SocketRead(TClient, TSocket)
			MSocket = MeasurementUtils.SocketRead(MClient, MSocket)	
			time.sleep(15)
	print "Starting measurement!"

	StartTime = datetime.now()

	Writer, FilePath, NetDir = MeasurementUtils.OpenCSVFile(DataFile,StartTime,
						ReadInst,SweepInst=[SweepInst],SetInst=SetInst,
						Comment=Comment)

	# This is the main measurement loop

	StartColumn, DataVector = MeasurementUtils.GenerateDataVector(SocketDataNumber,ReadInst,Sample,
							SweepInst=True,SetValue = SetValue)
	
	for i,v in enumerate(Sweep):
		
		# Set the Keithley
		SweepInst.SetOutput(v)

		TSocket = MeasurementUtils.SocketRead(TClient, TSocket)
		MSocket = MeasurementUtils.SocketRead(MClient, MSocket)
		
		DataVector[:,0] = MSocket[0]
		#print TSocket
        	DataVector[:,1:SocketDataNumber] = TSocket[0]
		DataVector[:,SocketDataNumber] = v

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
		ToPlot[0] = DataVector[-1,SocketDataNumber]
		for j in range(NRead):
			ToPlot[j+1] = DataVector[-1,StartColumn[j]+ReadInst[j].DataColumn]
	
		# Pass data to the plots
		PlotData.extend(ToPlot,_callSync = "off")
		for j in range(NRead):
			Curve[j].setData(x=PlotData[0::(NRead+1)],y=PlotData[j+1::(NRead+1)],_callSync = "off")

	SweepInst.Ramp(SweepFinish)

	# if the finish is zero switch it off
	if SweepFinish == 0.0:
		SweepInst.SwitchOutput()

	if SetInst:
		if len(FinishValue) != len(SetInst):
			if len(FinishValue) > len(SetInst):
				FinishValue = FinishValue[0:len(SetInst)]
			else:
				FinishValue = FinishValue + SetValue[len(FinishValue):len(SetInst)]
		for i,v in enumerate(SetInst):
			print "Ramping %s to %.2e" % (v.Name, FinishValue[i])
			v.Ramp(FinishValue[i])
			if FinishValue[i] == 0.0:
				v.SwitchOutput()
	
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
		return DataList
	else:
		return

#################################################
#            Time Sweep
#################################################
def DoTimeSweep(GraphProc,rpg,DataFile,SweepInst,ReadInst,
		SetInst = [], SetValue = [], FinishValue = [], PreValue = [],
		BSet = 0. , Persist = True, IgnoreMagnet = True,
		SweepStart = 0., SweepStop = 0., SweepStep = 1., SweepFinish = 0.0,SweepMid = [],
		Delay = 0, Sample = 1,
		TSet = -1,
		Timeout = -1, Wait = 1.0,
		ReturnData = False,SocketDataNumber = 5,
		Comment = "No comment!"):

	# Bind sockets 
	MClient, MSocket, TClient, TSocket = MeasurementUtils.InitializeSockets()

	NRead = len(ReadInst)

	# Set the sweep voltages

	Sweep = MeasurementUtils.GenerateDeviceSweep(SweepStart,SweepStop,SweepStep,Mid=SweepMid)
	SetTime = datetime.now()


	# Go to the set temperature and magnetic field and finish in persistent mode 4.52046,  0.000369189
	if TSet > 0:
		Msg = " ".join(("SET","%.2f" % TSet))
		MeasurementUtils.SocketWrite(TClient,Msg)
		print "Wrote message to temperature socket \"%s\"" % Msg
	if not IgnoreMagnet:
		Msg = " ".join(("SET","%.3f" % BSet,"%d" % int(not Persist)))
		MeasurementUtils.SocketWrite(MClient,Msg)
		print "Wrote message to Magnet socket \"%s\"" % Msg
	time.sleep(5)

	# give precedence to the magnet and wait for the timeout
	TSocket = MeasurementUtils.SocketRead(TClient, TSocket)
	MSocket = MeasurementUtils.SocketRead(MClient, MSocket)
	if (not IgnoreMagnet):
		while MSocket[1] != 1:
			print "Waiting for magnet!"
			time.sleep(15)
			TSocket = MeasurementUtils.SocketRead(TClient, TSocket)
			MSocket = MeasurementUtils.SocketRead(MClient, MSocket)
	
	NowTime = datetime.now()
	Remaining = Timeout*60.0 - float((NowTime-SetTime).seconds)
	while (TSocket[1] != 1) and (Remaining > 0):
		NowTime = datetime.now()
		Remaining = Timeout*60.0 - float((NowTime-SetTime).seconds)
		print "Waiting for temperature ... time remaining = %.2f minutes" % (Remaining/60.0)
		TSocket = MeasurementUtils.SocketRead(TClient, TSocket)
		MSocket = MeasurementUtils.SocketRead(MClient, MSocket)	
		time.sleep(15)
	

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

	if SetInst:
		for Set in [PreValue, SetValue]:
			if Set:
				if len(SetInst) != len(Set):
					if len(Set) > len(SetInst):
						Set = Set[0:len(SetInst)]
					else:
						Set = Set + [0]*(len(SetInst)-len(Set))
				for i,v in enumerate(SetInst):
					print "Ramping %s to %.2e" % (v.Name, Set[i])
					v.Ramp(Set[i])

	if SweepStart != 0:
		SweepInst.Ramp(SweepStart)
	else:
		SweepInst.SetOutput(0)

	if not SweepInst.Output:
		SweepInst.SwitchOutput()
	
	SweepInst.ReadData()

	if Wait >= 0.0:
		WaitTime = datetime.now()
		print "Waiting %.2f minute!" % Wait
		Remaining = Wait*60.0
		while Remaining > 0.0:
			NowTime = datetime.now()
			Remaining = Wait*60.0 - float((NowTime-WaitTime).seconds)
			print "Waiting ... time remaining = %.2f minutes" % (Remaining/60.0)
			TSocket = MeasurementUtils.SocketRead(TClient, TSocket)
			MSocket = MeasurementUtils.SocketRead(MClient, MSocket)	
			time.sleep(15)
	print "Starting measurement!"

	StartTime = datetime.now()

	Writer, FilePath, NetDir = MeasurementUtils.OpenCSVFile(DataFile,StartTime,
						ReadInst,SweepInst=[SweepInst],SetInst=SetInst,
						Comment=Comment)

	# This is the main measurement loop

	StartColumn, DataVector = MeasurementUtils.GenerateDataVector(SocketDataNumber,ReadInst,Sample,
							SweepInst=True,SetValue = SetValue)
	
	for i,v in enumerate(Sweep):
		
		# Set the Keithley
		SweepInst.SetOutput(v)

		TSocket = MeasurementUtils.SocketRead(TClient, TSocket)
		MSocket = MeasurementUtils.SocketRead(MClient, MSocket)
		
		DataVector[:,0] = MSocket[0]
		#print TSocket
        	DataVector[:,1:SocketDataNumber] = TSocket[0]
		DataVector[:,SocketDataNumber] = v

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
		ToPlot[0] = DataVector[-1,SocketDataNumber]
		for j in range(NRead):
			ToPlot[j+1] = DataVector[-1,StartColumn[j]+ReadInst[j].DataColumn]
	
		# Pass data to the plots
		PlotData.extend(ToPlot,_callSync = "off")
		for j in range(NRead):
			Curve[j].setData(x=PlotData[0::(NRead+1)],y=PlotData[j+1::(NRead+1)],_callSync = "off")

	SweepInst.Ramp(SweepFinish)

	# if the finish is zero switch it off
	if SweepFinish == 0.0:
		SweepInst.SwitchOutput()

	if SetInst:
		if len(FinishValue) != len(SetInst):
			if len(FinishValue) > len(SetInst):
				FinishValue = FinishValue[0:len(SetInst)]
			else:
				FinishValue = FinishValue + SetValue[len(FinishValue):len(SetInst)]
		for i,v in enumerate(SetInst):
			print "Ramping %s to %.2e" % (v.Name, FinishValue[i])
			v.Ramp(FinishValue[i])
			if FinishValue[i] == 0.0:
				v.SwitchOutput()
	
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
		SweepStart = 0.0, SweepStop = 1.0, SweepRate = 1.0, SweepFinish = 0.0, # Either A/min or mK/min
		Persist = False, IgnoreMagnet = False, # Magnet final state
		Delay = 0.0, Sample = 1,
		Timeout = -1, Wait = 1.0,
		ReturnData = False,SocketDataNumber=5,
		Comment = "No comment!"):

	# Bind sockets 
	MClient, MSocket, TClient, TSocket = MeasurementUtils.InitializeSockets()

	if FridgeSweep == "B":
		BSweep = True
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
	print "Wrote message to temperature socket \"%s\"" % Msg

	Msg = " ".join(("SET","%.3f" % BSet[0],"%d" % int(not StartPersist)))
	MeasurementUtils.SocketWrite(MClient,Msg)
	print "Wrote message to Magnet socket \"%s\"" % Msg
	time.sleep(5)

	# give precedence to the magnet and wait for the timeout
	TSocket = MeasurementUtils.SocketRead(TClient, TSocket)
	MSocket = MeasurementUtils.SocketRead(MClient, MSocket)
	if not IgnoreMagnet:
		while MSocket[1] != 1:
			print "Waiting for magnet!"
			time.sleep(15)
			TSocket = MeasurementUtils.SocketRead(TClient, TSocket)
			MSocket = MeasurementUtils.SocketRead(MClient, MSocket)
	
	NowTime = datetime.now()
	Remaining = Timeout*60.0 - float((NowTime-SetTime).seconds)
	while (TSocket[1] != 1) and (Remaining > 0):
		NowTime = datetime.now()
		Remaining = Timeout*60.0 - float((NowTime-SetTime).seconds)
		print "Waiting for temperature ... time remaining = %.2f minutes" % (Remaining/60.0)
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
					print "Ramping %s to %.2e" % (v.Name, Set[i])
					v.Ramp(Set[i])
	
	if Wait >= 0.0:
		WaitTime = datetime.now()
		print "Waiting %.2f minute!" % Wait
		Remaining = Wait*60.0
		while Remaining > 0.0:
			NowTime = datetime.now()
			Remaining = Wait*60.0 - float((NowTime-WaitTime).seconds)
			print "Waiting ... time remaining = %.2f minutes" % (Remaining/60.0)
			TSocket = MeasurementUtils.SocketRead(TClient, TSocket)
			MSocket = MeasurementUtils.SocketRead(MClient, MSocket)	
			time.sleep(15)
	print "Starting measurement!"

	StartTime = datetime.now()

	Writer, FilePath, NetDir = MeasurementUtils.OpenCSVFile(DataFile,StartTime,
						ReadInst,SetInst=SetInst,
						Comment=Comment)

	# This is the main measurement loop

	StartColumn, DataVector = MeasurementUtils.GenerateDataVector(SocketDataNumber,ReadInst,Sample,
							SetValue = SetValue)

	if BSweep:
		Msg = " ".join(("SWP","%.3f" % BSet[1], "%.3f" % SweepRate,"%d" % int(not Persist)))
		MeasurementUtils.SocketWrite(MClient,Msg)
		print "Wrote message to magnet socket \"%s\"" % Msg
	else:
		Msg = " ".join(("SWP","%.3f" % TSet[1], "%.3f" % SweepRate))
		MeasurementUtils.SocketWrite(TClient,Msg)
		print "Wrote message to temperature socket \"%s\"" % Msg	

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
	
	#print Field
	while FridgeStatus == 0:
		
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
			ToPlot[0] = DataVector[-1,2]
		for j in range(NRead):
			ToPlot[j+1] = DataVector[-1,StartColumn[j]+ReadInst[j].DataColumn]
	
		# Pass data to the plots
		PlotData.extend(ToPlot,_callSync = "off")
		for j in range(NRead):
			Curve[j].setData(x=PlotData[0::(NRead+1)],y=PlotData[j+1::(NRead+1)],_callSync = "off")

	# Loop is finished
	if SetInst:
		if len(FinishValue) != len(SetInst):
			if len(FinishValue) > len(SetInst):
				FinishValue = FinishValue[0:len(SetInst)]
			else:
				FinishValue = FinishValue + SetValue[len(FinishValue):len(SetInst)]
		for i,v in enumerate(SetInst):
			print "Ramping %s to %.2e" % (v.Name, FinishValue[i])
			v.Ramp(FinishValue[i])
			if FinishValue[i] == 0.0:
				v.SwitchOutput()
	
	if ReturnData:
		DataList = [None]*(NRead+1)
		DataList[0] = PlotData[0::NRead+1]
		for i in range(1,NRead+1):
			DataList[i]=PlotData[i::NRead+1]
	
	if BSweep:
		Msg = " ".join(("SET","%.3f" % SweepFinish,"%d" % int(not Persist)))
		MeasurementUtils.SocketWrite(MClient,Msg)
		print "Wrote message to Magnet socket \"%s\"" % Msg
	else:
		Msg = " ".join(("SET","%.2f" % SweepFinish))
		MeasurementUtils.SocketWrite(TClient,Msg)
		print "Wrote message to temperature socket \"%s\"" % Msg

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

#########################################################################
#              SWEEP One of the fridge parameters T or B
#              For sweeping the fridge the first if the SetInst
# 	       is stepped the length of SetValue shouls still equal
#              SetInst but the first value is ignored
########################################################################

def DeviceFridge2D(GraphProc, rpg, DataFile,
		ReadInst, SweepInst = [], SetInst=[],
		SetValue = [], PreValue = [], FinishValue = [],
		FridgeSweep = "B", FridgeSet = 0.0,
		DeviceStart = 0.0, DeviceStop = 1.0, DeviceStep = 0.1,
		FridgeStart = 0.0, FridgeStop = 1.0, FridgeRate = 0.1,
		Delay = 0, Sample = 1,
		Timeout = -1, Wait = 0.0,
		Comment = "No comment!",
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
		YStart = DeviceStart+0.01*(DeviceStop-DeviceStart) 
		YStop = DeviceStart+0.99*(DeviceStop-DeviceStart)
		YVec = np.linspace(YStart,YStop,num=2048)
	else:
		XVec = np.hstack((np.arange(DeviceStart,DeviceStop,DeviceStep),DeviceStop))
		YStart = FridgeStart+0.01*(FridgeStop-FridgeStart) 
		YStop = FridgeStart+0.99*(FridgeStop-FridgeStart)
		YVec = np.linspace(YStart,YStop,num=2048)

	if any(XCustom):
		XVec = XCustom

	NRead = len(ReadInst) 
	#Plt2DWin = [None]*NRead
	VwBox = [None]*NRead
	Imv = [None]*NRead
	ZArray = [np.zeros((len(XVec),len(YVec))) for i in range(NRead)]
	
	YScale = (YVec[-1]-YVec[0])/len(YVec)
	XScale = (XVec[-1]-XVec[0])/len(XVec)

	Plt2DWin = rpg.GraphicsView()
	Layout = rpg.GraphicsLayout(border=(100,100,100))
	Plt2DWin.setCentralItem(Layout)
	Plt2DWin.resize(500*NRead,500)

	for i in range(NRead):
		VwBox[i] = Layout.addViewBox(invertY = True)
		Imv[i] = rpg.ImageItem(ZArray[i],pos=[XVec[0],YVec[0]],scale=[XScale,YScale])
		VwBox[i].addItem(Imv[i])
	
	Plt2DWin.setWindowTitle("ReadInst")# %d" % i)
	Plt2DWin.show()

	#for i in range(NRead):
	#	Imv[i].setImage(ZArray[i],pos=([XVec[0],YVec[0]]),scale=([XScale,YScale]))

	for i,v in enumerate(XVec):
	
		if SweepDevice:
			#Sweep the device and fix T or B
			if BSweep:

				DataList = DoDeviceSweep(GraphProc,rpg,DataFile,
						SweepInst,ReadInst,SetInst = SetInst,SetValue = SetValue,
						FinishValue = FinishValue, PreValue = PreValue,
						BSet = v, Persist = False,
						SweepStart = DeviceStart, SweepStop = DeviceStop,
						SweepStep = DeviceStep,
						Delay = Delay, Sample = Sample,
						TSet = FridgeSet,
						Timeout = Timeout, Wait = Wait,
						ReturnData = True,
						Comment = Comment)
			else:
				DataList = DoDeviceSweep(GraphProc,rpg,DataFile,
						SweepInst,ReadInst,SetInst = SetInst,SetValue = SetValue,
						FinishValue = FinishValue, PreValue = PreValue,
						BSet = FridgeSet, Persist = True,
						SweepStart = DeviceStart, SweepStop = DeviceStop,
						SweepStep = DeviceStep,
						Delay = Delay, Sample = Sample,
						TSet = v,
						Timeout = Timeout, Wait = Wait,
						ReturnData = True,
						Comment = Comment)

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
							Comment = Comment)

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
							Comment = Comment)
							

		Ydata = DataList[0]

		for j in range(NRead):
			ZItp = interpolate.interp1d(Ydata,DataList[j+1],bounds_error=False,fill_value=0.0)
			ZArray[j][i,:] = ZItp(YVec)
			Imv[j].setImage(ZArray[j],scale=(XScale,YScale),pos=(XVec[0],YVec[0]))

	MClient = SocketUtils.SockClient('localhost', 18861)
	time.sleep(2)
	MeasurementUtils.SocketWrite(MClient,"SET 0.0 0")
	time.sleep(2)
	MClient.close()

	for i in range(NRead):
		VwBox[i].close()
		Plt2DWin.close()
	
	time.sleep(2)

	return


	
