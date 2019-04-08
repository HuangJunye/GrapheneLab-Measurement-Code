#!/usr/bin/python
# -*- coding: utf-8 -*-

"""

Sub programs for operating some Keithley instruments

author : Eoin O'Farrell
email : phyoec@nus.edu.sg
last edited : July 2013

Classes for:
	6430
	
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
from collections import namedtuple
import time
import math
import numpy as np
import threading
import Queue

######################################################
# At the moment each of the instruments we use is a
# seperate class
#####################################################

class k6430:
	def __init__(self,address, compliance = 105e-9, median = 0,repetition =1, integration = 1,source = "VOLT",delay = 0.1, trigger = 0):
		self.Address = address
		self.Visa = VisaSubs.InitializeGPIB(address,0,term_chars = "\\n")
		# Other 6430 properties
		self.Compliance = compliance
		self.Source = source
		self.Integration = integration # Defaults to 1
		self.Median = median # Defaults to 0 (no medianing)
		self.Repetition = repetition # Defaults to 1 (no averaging)
		self.Delay = delay # Defaults to 0 (second)
		self.Trigger = trigger # Trigger delay (defaults to 0)
		self.Output = False
		self.Visa.write(":OUTP 0")
		self.Data = [0.0 ,0.0]
		self.Sense = []
		self.RampStep = 0.1

	######################################
	# Initialization i.e. writing a load of SCPI
	#######################################

	def Initialize(self,SkipCompliance = False,SkipMath = False):

		# A bunch of commands to configure the 6430
		self.Visa.write("*RST")
		time.sleep(.1)
		self.Visa.write("".join((":SOUR:FUNC:MODE ",self.Source)))
		# Configure the auto zero (reference)
		self.Visa.write(":SYST:AZER:STAT ON")
		self.Visa.write(":SYST:AZER:CACH:STAT 1")
		self.Visa.write(":SYST:AZER:CACH:RES")

		# Disable concurrent mode, measure I and V (not R)
		self.Visa.write(":SENS:FUNC:CONC 1")	
		if self.Source == "VOLT":
			self.Sense = "CURR"
		elif self.Source == "CURR":
			self.Sense = "VOLT"

		self.Visa.write("".join((":SENS:FUNC:ON ","\"%s\"," % self.Source,"\"%s\"" % self.Sense)))
		self.Visa.write("".join((":FORM:ELEM ","%s," % self.Source,"%s" % self.Sense)))
		self.Visa.write("".join((":SENS:",self.Sense,":RANG:AUTO 0")))
		
		# Set the complicance
		if not SkipCompliance:
			self.Visa.write("".join((":SENS:",self.Sense,":RANG 105e-9")))
			self.Visa.write("".join((":SENS:",self.Sense,":PROT:LEV %.3e" % self.Compliance)))

#		# Set some filters
		self.Visa.write("".join((":SENS:",self.Sense,":NPLC %.2f" % self.Integration)))
		if not SkipMath:
			self.Visa.write(":SENS:AVER:REP:COUN %d" % self.Repetition)
			self.Visa.write(":SENS:MED:RANK %d" % self.Median)
		
		self.Visa.write(":SOUR:DEL %.4f" % self.Delay)
		self.Visa.write(":TRIG:DEL %.4f" % self.Trigger)
		
		pass
	
	###########################################
	# Set the range and compliance
	#######################################
	
	def SetRangeCompliance(self, Range = 105, Compliance = 105):

		self.Compliance = Compliance
		self.Visa.write("".join((":SENS:",self.Sense,":PROT:LEV %.3e" % self.Compliance)))
		
		if Range:
			self.Visa.write("".join((":SENS:",self.Sense,":RANG ","%.2e" % Range)))
		else:
			self.Visa.write("".join((":SENS:",self.Sense,":RANG:AUTO 1")))
		
		pass

	##################################################
	# Read data
	################################################

	def ReadData(self):
		Reply = self.Visa.ask(":READ?")
		self.Data = [float(i) for i in Reply.split(",")[0:2]]
		pass
	

	##################################################
	# Set source
	##################################################

	def Set(self,Level):
		self.Visa.write("".join((":SOUR:",self.Source," %.4e" % Level)))
		pass

	#################################################
	# Switch the output
	###############################################

	def SwitchOutput(self):
		self.Output = not self.Output		
		self.Visa.write("".join((":OUTP:STAT ","%d" % self.Output)))
		pass
	
	#################################################
	# Configure a sweep
	###############################################

	def ConfigureSweep(self,Start,Stop,Step,Soak = 0):
		self.Visa.write("".join((":SOUR:",self.Source,":START %.4e" % Start)))
		self.Visa.write("".join((":SOUR:",self.Source,":STOP %.4e" % Stop)))
		self.Visa.write("".join((":SOUR:",self.Source,":STEP %.4e" % Step)))		
		Count = int(1+abs(Stop - Start)/Step)
		self.Visa.write(":SOUR:SOAK %.4e" % Soak)
		self.Visa.write("TRIG:COUN %d" % Count)
		pass

	###################################################
	# Begin sweep, this doesn't work so well, not recommended
	#################################################

	def RunConfiguredSweep(self):
		self.Visa.write(":SOUR:VOLT:MODE SWE")
		self.Visa.write(":SOUR:SWE:SPAC LIN")
		self.Visa.write(":SOUR:SWE:RANG AUTO")
		self.Visa.write(":SOUR:DEL %0.4e" % self.Delay)
		self.SwitchOutput()
		pass


	######################################################
	# Manual sweep, this sweep will be run as a separate process
	# so it doesn't block the program
	##################################################

	def RunSweep(self,Start,Stop,Step,Wait,Mode = "linear",**kwargs):
		#self.Visa.write("".join((":SOUR:",self.Source,":MODE FIX")))
		
		Targets = [Start, Stop]
		
		for kw in kwargs.keys():
			if kw == "mid":
				Mid = kwargs[kw]
				for i in Mid:
					Targets.insert(len(Targets)-1,i)

		Voltage = [Start]
		
		for i in range(1,len(Targets)):
			Points = int(1+abs(Targets[i]-Targets[i-1])/Step)
			if Mode == "linear":
				Voltage = np.hstack([Voltage,np.linspace(Targets[i-1],Targets[i],num = Points)[1:Points]])
			if Mode == "log":
				Voltage = np.hstack([Voltage,np.linspace(Targets[i-1],Targets[i],num = Points)[1:Points]])

		

#		self.Visa.write("".join((":SOUR:",self.Source," %.4e" % Voltage[0])))
		
		return Voltage


	###################################################
	# Print a description string 
	################################################
	
	def Description(self):
		DescriptionString = "Keithley6430"
		for item in vars(self).items():
			if item[0] == "Repetition" or item[0] == "Median" or item[0] == "Integration" or item[0] == "Address":
				DescriptionString = ", ".join((DescriptionString,"%s = %.3f" % item))
			elif item[0] == "Source" or item[0] == "Sense" or item[0] == "Compliance":
				DescriptionString = ", ".join((DescriptionString,"%s = %s" % item))


		DescriptionString = "".join((DescriptionString,"\n"))
		return DescriptionString

	############################################
	######### Ramp the source to a final value
	#########################################
	
	def Ramp(self,VFinish):
		if self.Output:
			self.ReadData()
		VStart = self.Data[0]
		N = abs((VFinish-VStart)/self.RampStep)
		VSweep = np.linspace(VStart,Finish,num=N,endpoint=True)

		if not self.Output:
			self.SwitchOutput()

		for i in range(len(VSweep)):
			self.SetSource(VSweep[i])

		self.ReadData()
		return

