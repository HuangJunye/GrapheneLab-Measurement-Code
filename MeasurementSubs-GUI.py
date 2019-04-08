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
	
import rpyc
import visa as visa
import VisaSubs as VisaSubs
import string as string
import re as re
import time
import SrsLia as LIA
import Keithleys as keithley
import multiprocessing
import numpy as np
#import GraphSubs as MyGraphs
import pyqtgraph as pg
import pyqtgraph.multiprocess as mp
from datetime import datetime
import os
import csv
import subprocess


def OpenCSVFile(FileName,StartTime,Lockins,Kths,comment = "No comment!\n"):
	
	# Try to make a directory called Data in the CWD
	CurrentDir = os.getcwd()
	DataDir = "".join((CurrentDir,"\\Data"))
	try:
		os.mkdir(DataDir)
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
	for k in Lockins:
		csvfile.write(k.Description())
		ColumnString = "".join((ColumnString,", X, Y, R, \u03B8"))

	ColumnString = "".join((ColumnString,", B (T), T (mK)\n"))
	csvfile.write(ColumnString)


	return FileWriter

	
def DoVgSweep(GraphProc,rpg,DataFile, Magnet, Lias, Kthly, Start, Stop, Step, Delay = 1, Samples = 1,**kwargs):

	# Set the source voltages

	if "mid" in kwargs.keys():
		Source = Kthly.RunSweep(Start,Stop,Step,Delay,mid=kwargs["mid"])
	else:
		Source = Kthly.RunSweep(Start,Stop,Step,Delay)

	if "comment" in kwargs.keys():
		FileComment =  kwargs["comment"]
	else:
		FileComment = "No comment!"
		
		

	# Setup L plot windows
	NLias = len(Lias)


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

	Writer = OpenCSVFile(DataFile,StartTime,Lias,[Kthly],comment = FileComment)
	
	Kthly.SwitchOutput()
	
	for i in xrange(len(Source)):
		DataList = []
		# Set the Keithley
		Kthly.SetSource(Source[i])
		for j in xrange(Samples):
			# Read the Keithley
			Kthly.ReadData()
			DataList = np.hstack([DataList,Kthly.Data])
			# Read the Lockins
			for inst in Lias:
				inst.ReadData()
				DataList = np.hstack([DataList,inst.Data])
			# Read the magnet
			Field = Magnet.root.MagnetReadField()
			#print Field
			DataList = np.hstack([DataList,Field])
			# Sleep
			time.sleep(Delay)
		DataList = np.reshape(DataList,[Samples,len(DataList)/Samples])
		# Save the data
		for j in xrange(Samples):
			Writer.writerow(DataList[j,:])
		# Package the data and send it for plotting
		XData = DataList[:,0]
		YData = np.empty([Samples,NLias+1])
		YData[:,1:] = DataList[:,2:NLias*4+2:4]
		YData[:,0] = DataList[:,1]
		# Pass data to the plots
		PlotData.extend(np.hstack([np.mean(XData),np.mean(YData,0)]),_callSync = "off")
		for i in range(NLias+1):
			Curve[i].setData(x=PlotData[0::NLias+2],y=PlotData[i+1::NLias+2],_callSync = "off")
		
	Kthly.SwitchOutput()


def DoBSweep(GraphProc,rpg,DataFile, Magnet, Lias, Kthly, Vg = 0, Start = 0, Stop = 0, FinishHeater = 0, Rate = 2.2, Delay = 1,**kwargs):
	
	if "comment" in kwargs.keys():
		FileComment = kwargs["comment"]
	else:
		FileComment = "No comment!"
	
	# Go to the start field with switch heater on as the final stage
	# This process is done synchronously for the moment and we hang
	# on it's output, Note rate is set to be 2.2 A/m

	Magnet.root.MagnetGoToSet(Start, 1, rate = 2.2)

	# Turn on the Keithley and then wait for a bit
	Kthly.SetSource(Vg)
	Kthly.SwitchOutput()
	time.sleep(30)	

	# Setup L plot windows for each LIA
	NLias = len(Lias)
	
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
	
	# Open the data file
	Writer = OpenCSVFile(DataFile,StartTime,Lias,[Kthly],comment = FileComment)

	# Start the sweep
	Magnet.root.MagnetGoToSet(Stop, 1, rate = Rate, sweep = 1)	

	Field = Magnet.root.MagnetReadField()
	#print Field
	while abs(Field - Stop) >= 0.01:
		DataList = []
		
		# Read the Keithley
		Kthly.ReadData()
		DataList = np.hstack([DataList,Kthly.Data])
		
		# Read the Lockins
		for inst in Lias:
			inst.ReadData()
			DataList = np.hstack([DataList,inst.Data])
		
		# Read the magnet
		Field = Magnet.root.MagnetReadField()
		#print Field
		DataList = np.hstack([DataList,Field])
		
		# Save the data
		Writer.writerow(DataList)
		# Package the data and send it for plotting

		XData = DataList[-1]
		YData = np.empty([NLias+1])
		YData[1:] = DataList[2:NLias*4+2:4]
		YData[0] = DataList[1]
		# Pass data to the plots
		PlotData.extend(np.hstack([XData,YData]),_callSync = "off")
		for i in range(NLias+1):
			Curve[i].setData(x=PlotData[0::NLias+2],y=PlotData[i+1::NLias+2],_callSync = "off")
		# Sleep
		time.sleep(Delay)
		
	Kthly.SwitchOutput()


	if FinishHeater == 0:
		Magnet.root.MagnetGoToSet(Stop, 0)
		

