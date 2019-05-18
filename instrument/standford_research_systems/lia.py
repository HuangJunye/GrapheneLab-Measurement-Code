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

	data from these processes can also be accessed through named pipes

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

import numpy as np

import utils.visa_subs as visa_subs


class LockInAmplifier:
	def __init__(self, address):
		self.address = address
		self.visa = visa_subs.initialize_gpib(address, 0)
		# Other LIA properties
		self.source = "VOLT"
		self.name = "Lock in"
		self.excitation = []
		self.frequency = []
		self.harmonic = []
		self.internal_excitation = []
		self.sensitivity = []
		self.sensitivity_max = 1.
		self.phase = []
		self.tau = []
		self.expand = []
		self.offset = []
		self.data = [0.0, 0.0, 0.0, 0.0]
		self.data_column = 0
		self.output = True
		self.auto_range = False

	# Read one of the numeric parameters
	def read_numeric(self, command):
		reply = self.visa.query("".join((command, "?")))
		answer = float(reply)
		return answer

	# Read data (X, Y, R, phase)
	def ReadData(self):
		reply = self.visa.query("SNAP?1,2,3,4")
		self.data = [float(i) for i in reply.split(",")]

		if self.auto_range:
			oldRange = self.sensitivity
			if self.data[2] > .9 * self.sensitivity_max:
				self.sensitivity = self.sensitivity + 3
				if self.sensitivity > 26:
					self.sensitivity = 26
			elif self.data[2] < .01 * self.sensitivity_max:
				self.sensitivity = self.sensitivity - 3
				if self.sensitivity < 0:
					self.sensitivity = 0

			if self.sensitivity != oldRange:
				self.visa.write("SENS %d" % self.sensitivity)
				self.CalcSensMax()

		pass

	# Initialization for the LIA consists of reading the measurement parameters
	def Initialize(self,autorange=False):
		self.excitation = self.read_numeric("SLVL")
		self.frequency = self.read_numeric("FREQ")
		self.harmonic = self.read_numeric("HARM")
		self.sensitivity = int(self.read_numeric("SENS"))
		self.phase = self.read_numeric("PHAS")
		self.tau = self.read_numeric("OFLT")
		self.internal_excitation = self.read_numeric("FMOD")
		self.expand = np.empty(2)
		self.offset = np.empty(2)
		self.ReadOffset()
		self.auto_range = autorange
		self.ColumnNames = "X (V), Y (V), R (V), phase (Deg)"
		self.CalcSensMax()
		pass

	def CalcSensMax(self):
		RangeVec = [2.,5.,10.]
		Lev = self.sensitivity/3 - 9
		self.sensitivity_max = RangeVec[self.sensitivity%3] * 10**Lev
		pass

	def SetOutput(self,Level):
		self.visa.write("SLVL %.3f" % Level)
		pass

	def Ramp(self,VFinish):
		VStart = self.read_numeric("SLVL")
		if abs(VStart-VFinish) > 0.002:
			N = abs((VFinish-VStart)/0.01)
			VSweep = np.linspace(VStart,VFinish,num=np.ceil(N),endpoint=True)

			for i in range(len(VSweep)):
				self.SetOutput(VSweep[i])
				time.sleep(0.01)

			self.excitation = VFinish
		
		return

	# Read the offsets
	def ReadOffset(self,**kwargs):
		
		# set the offsets to zero
		if "auto" in list(kwargs.keys()):
			self.visa.write("OEXP 1,0,0")
			self.visa.write("OEXP 2,0,0")
			time.sleep(1)

			# auto set the offsets
			self.visa.write("AOFF 1")
			self.visa.write("AOFF 2")

		# Read the offsets
		for i in range(2):
			reply = self.visa.query("".join(("OEXP? ","%d" % (i+1))))
			reply = reply.split(",")
			self.offset[i] = float(reply[0])
			self.expand[i] = float(reply[1])

		if "auto" in list(kwargs.keys()):
			self.visa.write("".join(("OEXP 1,","%.2f," % self.offset[0],"%d" % kwargs["auto"])))
			self.visa.write("".join(("OEXP 2,","%.2f," % self.offset[1],"%d" % kwargs["auto"])))
			self.expand[0] = kwargs["auto"]
			self.expand[1] = kwargs["auto"]

		pass

	# Print a description string 
	def Description(self):
		DescriptionString = "SrsLia"
		for item in list(vars(self).items()):
			if item[0] == "tau" or item[0] == "excitation" or item[0] == "frequency" or item[0] == "harmonic" or item[0] == "address" or item[0] == "phase" or item[0] == "sensitivity" or item[0] == "internal_excitation":
				DescriptionString = ", ".join((DescriptionString,"%s = %.3f" % item))
			#elif item[0] == "expand" or item[0] == "offset":
			#	DescriptionString = ", ".join((DescriptionString,"%s = %.3f, %.3f" % item))

		DescriptionString = "".join((DescriptionString,"\n"))
		return DescriptionString



