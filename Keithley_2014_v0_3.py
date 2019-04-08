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
	def __init__(self,address):
		self.Name = "Keithley 6430"
		self.Address = address
		self.Visa = VisaSubs.InitializeGPIB(address,0,term_chars = "\\n")
		# Other 6430 properties
		self.Compliance = 0.0
		self.Integration = 1 # Defaults to 1
		self.Median = 0 # Defaults to 0 (no medianing)
		self.Repetition = 1 # Defaults to 1 (no averaging)
		self.Delay = 0 # Defaults to 0 (second)
		self.Trigger = 0
		self.Source = "VOLT"
		self.Output = False
		self.Visa.write(":OUTP 0")
		self.Data = [0.0 ,0.0]
		self.Sense = []
		self.RampStep = 0.1
		self.ColumnNames = "V (V), I (A)"
		self.DataColumn = 0
		self.SourceColumn = 1
		self.Range = 105e-9

	######################################
	# Initializate as voltage source
	#######################################

	def InitializeVoltage(self,Compliance = 105e-9,
				Median = 0,Repetition =1, Moving= 1,
				Integration=1,Delay=0.0,Trigger=0,
				RampStep = 0.1,Range=105e-9,AutoRange = False, AutoFilter = False):

		self.ColumnNames = "V (V), I (A)"
		self.DataColumn = 1
		self.SourceColumn = 0
		self.Source = "VOLT"
		self.Sense = "CURR"
		self.Moving = Moving
		# Special variables for 6430
		self.Median = Median
		self.Repetition = Repetition
		self.Integration = Integration
		self.Delay = Delay
		self.Compliance = Compliance
		self.RampStep = RampStep
		self.Range = Range

		# A bunch of commands to configure the 6430
		self.Visa.write("*RST")
		time.sleep(.1)
		self.Visa.write(":SOUR:FUNC:MODE VOLT")
		# Configure the auto zero (reference)
		self.Visa.write(":SYST:AZER:STAT ON")
		self.Visa.write(":SYST:AZER:CACH:STAT 1")
		self.Visa.write(":SYST:AZER:CACH:RES")

		# Disable concurrent mode, measure I and V (not R)
		self.Visa.write(":SENS:FUNC:CONC 1")

		self.Visa.write(":SENS:FUNC:ON \"VOLT\",\"CURR\"")
		self.Visa.write(":FORM:ELEM VOLT,CURR")
		
		if AutoRange:
			self.Visa.write(":SENS:CURR:RANG:AUTO 1")
		else:
			self.Visa.write(":SENS:CURR:RANG %.2e" % self.Range)

		self.Visa.write(":SENS:CURR:PROT:LEV %.3e" % self.Compliance)

#		# Set some filters
		
		if AutoFilter:
			self.Visa.write(":SENS:AVER:AUTO ON")
		else:
			self.Visa.write(":SENS:CURR:NPLC %.2f" % self.Integration)
			self.Visa.write(":SENS:AVER:REP:COUN %d" % self.Repetition)
			self.Visa.write(":SENS:AVER:COUN %d" % self.Moving)
			self.Visa.write(":SENS:MED:RANK %d" % self.Median)
		
		
		self.Visa.write(":SOUR:DEL %.4f" % self.Delay)
		self.Visa.write(":TRIG:DEL %.4f" % self.Trigger)
		
		pass

	######################################
	# Initializate as current source
	#######################################

	def InitializeCurrent(self,Compliance = 1.0,
				Median = 0,Repetition =1,
				Integration=1,Delay=0.0,Trigger=0,
				RampStep = 0.1,Range=1.0,AutoRange = False):

		self.ColumnNames = "V (V), I (A)"
		self.DataColumn = 0
		self.SourceColumn = 1
		self.Source = "CURR"
		self.Sense = "VOLT"
		# Special variables for 6430
		self.Median = Median
		self.Repetition = Repetition
		self.Integration = Integration
		self.Delay = Delay
		self.Compliance = Compliance
		self.RampStep = RampStep
		self.Range = Range

		# A bunch of commands to configure the 6430
		self.Visa.write("*RST")
		time.sleep(.1)
		self.Visa.write(":SOUR:FUNC:MODE CURR")
		# Configure the auto zero (reference)
		self.Visa.write(":SYST:AZER:STAT ON")
		self.Visa.write(":SYST:AZER:CACH:STAT 1")
		self.Visa.write(":SYST:AZER:CACH:RES")

		# Disable concurrent mode, measure I and V (not R)
		self.Visa.write(":SENS:FUNC:CONC 1")

		self.Visa.write(":SENS:FUNC:ON \"VOLT\",\"CURR\"")
		self.Visa.write(":FORM:ELEM VOLT,CURR")
		
		if AutoRange:
			self.Visa.write(":SENS:VOLT:RANG:AUTO 1")
		else:
			self.Visa.write(":SENS:VOLT:RANG %.2e" % self.Range)

		self.Visa.write(":SENS:VOLT:PROT:LEV %.3e" % self.Compliance)

#		# Set some filters
		self.Visa.write(":SENS:CURR:NPLC %.2f" % self.Integration)
	
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

	def SetOutput(self,Level):
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


	###################################################
	# Print a description string 
	################################################
	
	def Description(self):
		DescriptionString = "Keithley6430"
		for item in vars(self).items():
			if item[0] == "Address":
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
		VStart = self.Data[self.SourceColumn]
		if abs(VStart-VFinish) > self.RampStep:	
			N = abs((VFinish-VStart)/self.RampStep)
			VSweep = np.linspace(VStart,VFinish,num=np.ceil(N),endpoint=True)

			if not self.Output:
				self.SwitchOutput()

			for i in range(len(VSweep)):
				self.SetOutput(VSweep[i])
				time.sleep(0.01)

			self.ReadData()
		return


class k2400:
	def __init__(self,address):
		self.Name = "Keithley 2400"
		self.Address = address
		self.Visa = VisaSubs.InitializeGPIB(address,0,term_chars = "\\n")
		# Other 6430 properties
		self.Compliance = 0.0
		self.Source = "VOLT"
		self.Output = False
		self.Visa.write(":OUTP 0")
		self.Data = [0.0 ,0.0]
		self.Sense = []
		self.RampStep = 0.1
		self.ColumnNames = "V (V), I (A)"
		self.DataColumn = 0

	######################################
	# Initializate as voltage source
	#######################################

	def InitializeVoltage(self,Compliance = 105e-9,RampStep = 0.1,AutoRange = False, SourceRange = 0.0):

		self.Compliance = Compliance
		self.RampStep = RampStep
		self.ColumnNames = "V (V), I (A)"
		self.DataColumn = 1
		self.Source = "VOLT"
		self.Sense = "CURR"
		# A bunch of commands to configure the 6430
		self.Visa.write("*RST")
		time.sleep(.1)
		self.Visa.write(":SOUR:FUNC:MODE VOLT")
		# Configure the auto zero (reference)
		self.Visa.write(":SYST:AZER:STAT ON")
		self.Visa.write(":SYST:AZER:CACH:STAT 1")
		self.Visa.write(":SYST:AZER:CACH:RES")

		# Disable concurrent mode, measure I and V (not R)
		self.Visa.write(":SENS:FUNC:CONC 1")

		self.Visa.write(":SENS:FUNC:ON \"VOLT\",\"CURR\"")
		self.Visa.write(":FORM:ELEM VOLT,CURR")
		
		self.Visa.write(":SOUR:VOLT:RANG:AUTO 0")

		if AutoRange:
			self.Visa.write(":SENS:CURR:RANG:AUTO 0")
		else:
			self.Visa.write(":SENS:CURR:RANG 105e-9")
	
		self.Visa.write(":SENS:CURR:PROT:LEV %.3e" % self.Compliance)
		
		return
	
	###########################################
	# Set the range and compliance
	#######################################
	
	def SetRangeCompliance(self, Range = 105e-9, Compliance = 0.1):

		self.Compliance = Compliance
		self.Visa.write("".join((":SENS:",self.Sense,":PROT:LEV %.3e" % self.Compliance)))
		
		if Range:
			self.Visa.write("".join((":SENS:",self.Sense,":RANG ","%.3e" % Range)))
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

	def SetOutput(self,Level):
		self.Visa.write("".join((":SOUR:",self.Source," %.4e" % Level)))
		pass

	#################################################
	# Switch the output
	###############################################

	def SwitchOutput(self):
		self.Output = not self.Output		
		self.Visa.write("".join((":OUTP:STAT ","%d" % self.Output)))
		pass


	###################################################
	# Print a description string 
	################################################
	
	def Description(self):
		DescriptionString = "Keithley2400"
		for item in vars(self).items():
			if item[0] == "Address":
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
		if abs(VStart-VFinish) > self.RampStep:
			N = abs((VFinish-VStart)/self.RampStep)
			VSweep = np.linspace(VStart,VFinish,num=np.ceil(N),endpoint=True)

			if not self.Output:
				self.SwitchOutput()

			for i in range(len(VSweep)):
				self.SetOutput(VSweep[i])
				time.sleep(0.01)

			self.ReadData()
		
		return


class k6221:
	# The 6221 operates only as a source, these functions configure it as an AC source (WAVE mode)
	# and the measurement is made by the Lockin

	def __init__(self,address):
		self.Name = "Keithley 6221"
		self.Address = address
		self.Visa = VisaSubs.InitializeGPIB(address,0,term_chars = "\\n")
		# Other 6430 properties
		# Query the output state
		self.Output = False
		self.Wave =  False
		ReplyOutp = self.Visa.ask(":OUTP:STAT?")
		ReplyOutp = int(ReplyOutp)
		self.Output = bool(ReplyOutp)
		
		ReplyWave = self.Visa.ask(":SOUR:WAVE?")
		ReplyWave = int(ReplWave)
		self.Wave = bool(ReplyWave)
		
		if ( self.Output and self.Wave ):
			self.Compliance = self.ReadNumeric(":SOUR:CURR:COMP?")
			self.Frequency = self.ReadNumeric(":SOUR:WAVE:FREQ?")
			self.Amplitude = self.ReadNumeric(":SOUR:WAVE:AMPL?")
			self.Offset = self.ReadNumeric(":SOUR:WAVE:OFFS?")
			self.Phase = self.ReadNumeric(":SOUR:WAVE:PMAR?")
			self.TriggerPin = 2
		else:
			self.Compliance = 0.0
			self.Frequency = 9.2
			self.Amplitude = 0.0 # Amperes
			self.Offset = 0.0
			self.Phase = 0.0 # position of the phase marker
			self.TriggerPin = 2 # pin to write the trigger
			self.Visa.write(":SOUR:CLE:IMM")
	
			
		self.RampStep = 10e-9
		self.Source = "CURR"
		self.ColumnNames = "I (A)"
		self.DataColumn = 0
		self.Data = [self.Amplitude] # Amperes
		# Move the trigger pin so we can set the phase marker to line 2
		

	######################################
	# Initializate as current WAVE source
	#######################################

	def InitializeWave(self,Compliance = 0.1,RampStep = 1e-9,AutoRange = True,
				Frequency = 9.2,
				Offset=0.0,Phase=0.0):

		self.Wave = True
		self.ColumnNames = "I (A)"
		self.DataColumn = 0
		self.Source = "CURR"
		# A bunch of commands to configure the 6221
		if not self.Output:
			self.Compliance = Compliance
			self.RampStep = RampStep
			self.Frequency = Frequency
			self.Offset = Offset
			self.Phase = Phase
			self.Visa.write("*RST")
			time.sleep(.1)
			#self.Visa.write(":OUTP:LTE ON")
			self.Visa.write(":SOUR:WAVE:FUNC SIN")
			if AutoRange:
				self.Visa.write(":SOUR:WAVE:RANG BEST")
			else:
				self.Visa.write(":SOUR:WAVE:RANG FIX")
	
			self.Visa.write(":TRIG:OLIN 4")
			self.Visa.write(":SOUR:WAVE:PMAR:OLIN %d" % self.TriggerPin)	
			self.Visa.write(":SOUR:WAVE:PMAR:STAT ON")
			self.Visa.write(":SOUR:WAVE:PMAR %.1f" % self.Phase)
	
			self.Visa.write(":SOUR:CURR:COMP %.3e" % self.Compliance)
			self.Visa.write(":SOUR:WAVE:FREQ %.3e" % self.Frequency)
			self.Visa.write(":SOUR:WAVE:OFFS %.3e" % self.Offset)
			self.Visa.write(":SOUR:WAVE:AMPL %.3e" % self.RampStep)

		
		return


	######################################
	# Initializate as current DELTA source
	#######################################

	def InitializeDelta(self,Compliance = 0.1,RampStep = 1e-9, AutoRange = True, Range= 0.1,
				Counts = 1000, Delay = 0.1):

		self.Wave = False 
		self.ColumnNames = "I (A)"
		self.DataColumn = 0
		self.Source = "CURR"
		# A bunch of commands to configure the 6221
		self.Compliance = Compliance
		self.RampStep = RampStep
		self.Counts = Counts
		self.Delay = Delay
		self.Visa.write("*RST")
		time.sleep(.1)
		self.Visa.write(":SOUR:DEL:NVPR 1")
		self.Visa.write(":SOUR:DEL:CAB OFF")
		if AutoRange:
			self.Visa.write(":SOUR:CURR:RANG:AUTO 1")
		else:
			self.Visa.write(":SOUR:CURR:RANG %.4e" % self.Range)
	
		self.Visa.write(":SOUR:CURR:COMP %.3e" % self.Compliance)

		
		return

	
	###########################################
	# Set the range and compliance
	#######################################
	
	#def SetRangeCompliance(self, Range = 105e-9, Compliance = 105e-9):
#
	#	self.Compliance = Compliance
	#	self.Visa.write("".join((":SENS:",self.Sense,":PROT:LEV %.3e" % self.Compliance)))
	#	
	#	if Range:
	#		self.Visa.write("".join((":SENS:",self.Sense,":RANG ","%.3e" % Range)))
	#	else:
	#		self.Visa.write("".join((":SENS:",self.Sense,":RANG:AUTO 1")))
	#	
	#	pass

	##################################################
	# Read numeric
	################################################

	def ReadNumeric(self,Command):
		Reply = self.Visa.ask(Command)
		Answer = float(Reply)
		return Answer
	

	##################################################
	# Set source
	##################################################

	def SetOutput(self,Level):
		if self.Wave:
			self.Visa.write(":SOUR:WAVE:AMPL %.4e" % Level)
		else:
			self.Visa.write(":SOUR:DEL:HIGH %.4e" % Level)
			self.Visa.write(":SOUR:DEL:LOW %.4e" % -Level)
		pass

	#################################################
	# Switch the output
	###############################################

	def SwitchOutput(self):
		self.Output = not self.Output
		if (self.Output and self.Wave):
			self.Visa.write(":SOUR:WAVE:ARM")
			self.Visa.write(":SOUR:WAVE:INIT")
		elif (self.Wave and self.Output = :
			self.Visa.write(":SOUR:WAVE:ABOR")

		pass


	###################################################
	# Print a description string 
	################################################
	
	def Description(self):
		DescriptionString = "Keithley6221"
		for item in vars(self).items():
			if item[0] == "Address" or item[0] == "Amplitude" or item[0] == "Frequency":
				DescriptionString = ", ".join((DescriptionString,"%s = %.3f" % item))
			elif item[0] == "Compliance":
				DescriptionString = ", ".join((DescriptionString,"%s = %s" % item))

		DescriptionString = "".join((DescriptionString,"\n"))
		return DescriptionString

	############################################
	######### Ramp the source to a final value
	#########################################
	
	def Ramp(self,VFinish):
		VStart = self.Amplitude
		if abs(VStart-VFinish) > self.RampStep:

			if self.Output:
				self.SwitchOutput()

			self.SetOutput(VFinish)
			self.SwitchOutput()

			self.Amplitude = VFinish
			self.Data[0] = VFinish
		
		return

