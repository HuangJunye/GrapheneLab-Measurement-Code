#!/usr/bin/python
# -*- coding: utf-8 -*-

"""

Sub programs for operating some Keithley instruments

author : Eoin O'Farrell
email : phyoec@nus.edu.sg
last edited : Oct 2014

Classes for:
	6430
	
	InitializeInstruments
	ScanInstruments
	InitializeDataFile
	WriteDataFile
	CloseDataFile
	GraphData

"""

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
		self.Visa = VisaSubs.InitializeGPIB(address,0)
		
		# Other 6430 properties #Added 11 Aug by Rosti, because this version didn't have Trigger in initialization in InitializeCurrent
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
				Median = 0,Repetition =1,
				Moving= 1,
				Integration=1,Delay=0.0,Trigger=0,
				RampStep = 0.1,Range=105e-9,
				AutoRange = False, AutoFilter = False,
				AutoDelay = False):

		self.ColumnNames = "V (V), I (A)"
		self.Data = [0.0, 0.0]
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
		self.Output = False
		self.Visa.write(":OUTP 0")
		self.Trigger = Trigger

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
		
                self.Visa.write(":SENS:CURR:PROT:LEV %.3e" % self.Compliance)	
		if AutoRange:
			self.Visa.write(":SENS:CURR:RANG:AUTO 1")
		else:
			self.Visa.write(":SENS:CURR:RANG %.2e" % self.Range)
                
	
#		# Set some filters
		
		if AutoFilter:
			self.Visa.write(":SENS:AVER:AUTO ON")
		else:
			self.Visa.write(":SENS:CURR:NPLC %.2f" % self.Integration)
			self.Visa.write(":SENS:AVER:REP:COUN %d" % self.Repetition)
			self.Visa.write(":SENS:AVER:COUN %d" % self.Moving)
			self.Visa.write(":SENS:MED:RANK %d" % self.Median)
		
		
		if AutoDelay:
			self.Visa.write(":SOUR:DEL:AUTO ON")
		else:
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
		self.Visa.write(":SYST:BEEP:STAT 0")
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
		
		self.Visa.write(":SENS:VOLT:PROT:LEV %.3e" % self.Compliance)

		if AutoRange:
			self.Visa.write(":SENS:VOLT:RANG:AUTO 1")
		else:
			self.Visa.write(":SENS:VOLT:RANG %.2e" % self.Range)
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
		self.Visa = VisaSubs.InitializeGPIB(address,0)

	######################################
	# Initializate as voltage source
	#######################################

	def InitializeVoltage(self,Compliance = 105e-9,
			RampStep = 0.1,AutoRange = False,
			reset = True, SourceRange = 21):

		self.Source = "VOLT"
		self.RampStep = RampStep
		self.ColumnNames = "V (V), I (A)"
		self.DataColumn = 1
		self.Source = "VOLT"
		self.Sense = "CURR"
		self.Data = [0.0 ,0.0]

		if reset:
			self.Compliance = Compliance
			self.Output = False
			self.Visa.write(":OUTP 0")
					# A bunch of commands to configure the 6430
			self.Visa.write("*RST")
			self.Visa.write(":SYST:BEEP:STAT 0")
			time.sleep(.1)
			self.Visa.write(":SOUR:FUNC:MODE VOLT")
			self.Visa.write(":SOUR:VOLT:RANG %d" % SourceRange)
			# Configure the auto zero (reference)
			self.Visa.write(":SYST:AZER:STAT ON")
			self.Visa.write(":SYST:AZER:CACH:STAT 1")
			self.Visa.write(":SYST:AZER:CACH:RES")
			# Disable concurrent mode, measure I and V (not R)
			self.Visa.write(":SENS:FUNC:CONC 1")
			self.Visa.write(":SENS:FUNC:ON \"VOLT\",\"CURR\"")
			self.Visa.write(":FORM:ELEM VOLT,CURR")
			if AutoRange:
				self.Visa.write(":SENS:CURR:RANG:AUTO 0")
			else:
				self.Visa.write(":SENS:CURR:RANG 105e-9")
			self.Visa.write(":SENS:CURR:PROT:LEV %.3e" % self.Compliance)
		else:
			self.Output = bool(int(self.Visa.ask(":OUTP:STAT?")))
			self.Compliance = float(self.Visa.ask(":SENS:CURR:PROT:LEV?"))
			self.ReadData()
	
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
		self.Visa = VisaSubs.InitializeGPIB(address,0)
		# Other 6430 properties
		# Query the output state
		self.Output = False
		Reply = self.Visa.ask(":OUTP:STAT?")
		Reply = int(Reply)
		self.Output = bool(Reply)
		if self.Output:
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
	# Initializate as voltage source
	#######################################

	def InitializeWave(self,Compliance = 0.1,RampStep = 1e-9,AutoRange = True,
				Frequency = 9.2,
				Offset=0.0,Phase=0.0):

		self.ColumnNames = "I (A)"
		self.DataColumn = 0
		self.Source = "CURR"
		# A bunch of commands to configure the 6430
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
		self.Visa.write(":SOUR:WAVE:AMPL %.4e" % Level)
		pass

	#################################################
	# Switch the output
	###############################################

	def SwitchOutput(self):
		self.Output = not self.Output
		if self.Output:
			self.Visa.write(":SOUR:WAVE:ARM")
			self.Visa.write(":SOUR:WAVE:INIT")
		else:
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


class k2182a:
	def __init__(self,address):
		self.Name = "Keithley 2182A"
		self.Address = address
		self.Visa = VisaSubs.InitializeGPIB(address,0)

	######################################
	# Initializate as voltage source
	#######################################

	def InitializeVoltage(self,Channel=1,ACal=False,
				Relative=False,AFilt=False,
				DFilt=True,Count=5,
				Range=1.,
				AutoRange = False):

		self.ColumnNames = "V (V)"
		self.Data = [0.0]
		self.DataColumn = 0
		self.Sense = "VOLT"
		# Special variables for 2182
		self.Channel = Channel
		self.Relative = Relative
		self.AFilt = AFilt
		self.DFilt = DFilt
		self.Count = Count
		self.Range = Range
		self.AutoRange = AutoRange

		# A bunch of commands to configure the 2182
		self.Visa.write("*RST")
		time.sleep(.1)
		self.Visa.write(":SENS:FUNC \'VOLT\'")
		self.Visa.write(":SENS:CHAN %d" % Channel)

		if ACal:
			self.Visa.write(":CAL:UNPR:ACAL:INIT")
			time.sleep(1.0)
			Reply = self.Visa.ask(":CAL:UNPR:ACAL:TEMP?")
			time.sleep(10.)
				#Reply = 1
				#Reply = self.Visa.ask("*OPC?")
			self.Visa.write(":CAL:UNPR:ACAL:DONE")

		# Disable concurrent mode, measure I and V (not R)
		self.SetRange(Range=Range,AutoRange=AutoRange)

		# Set some filters
		if AFilt:
			self.Visa.write(":SENS:VOLT:LPAS 1")
		else:
			self.Visa.write(":SENS:VOLT:LPAS 0")


		if DFilt:
			self.Visa.write(":SENS:VOLT:DFIL 1")
			self.Visa.write(":SENS:VOLT:DFIL:COUN %d" % Count)
		else:
			self.Visa.write(":SENS:VOLT:DFIL 0")

		self.Visa.ask(":READ?")

		self.Visa.write(":SENS:VOLT:REF:STAT 0")
		if Relative:
			self.Visa.write(":SENS:VOLT:REF:ACQ")
			self.Visa.write(":SENS:VOLT:REF:STAT 1")
			Reply = self.Visa.ask(":SENS:VOLT:REF?")
			print Reply
			self.RelativeValue = float(Reply)
		
		pass


	###########################################
	# Set the range and compliance
	#######################################
	
	def SetRange(self, Range = 0.1, AutoRange = False):

		if AutoRange:
			self.AutoRange = True
			self.Visa.write("".join((":SENS:",self.Sense,":RANG:AUTO 1")))
		else:
			self.Range = Range
			self.AutoRange = False
			self.Visa.write("".join((":SENS:",self.Sense,":RANG ","%.2e" % Range)))
		
		pass

	##################################################
	# Read data
	################################################

	def ReadData(self):
		Reply = self.Visa.ask(":READ?")
		self.Data = [float(Reply)]
		pass
	
	###############################################
	# Print a description string 
	################################################
	
	def Description(self):
		DescriptionString = "Keithley2182"
		for item in vars(self).items():
			if item[0] == "Address":
				DescriptionString = ", ".join((DescriptionString,"%s = %.3f" % item))
			elif item[0] == "Sense" or item[0] == "Range" or item[0] == "Relative" or item[0] == "RelativeValue":
				DescriptionString = ", ".join((DescriptionString,"%s = %s" % item))

		DescriptionString = "".join((DescriptionString,"\n"))
		return DescriptionString


class k2002:
	def __init__(self,address):
		self.Name = "Keithley 2002"
		self.Address = address
		self.Visa = VisaSubs.InitializeGPIB(address,0)

	######################################
	# Initializate as voltage source
	#######################################

	def InitializeVoltage(self,ACal=False,
				Relative=False,
				Filt=True,Count=5,
				Range=2.,
				AutoRange = False):

		self.ColumnNames = "V (V)"
		self.Data = [0.0]
		self.DataColumn = 0
		self.Sense = "VOLT"
		# Special variables for 2002
		self.Relative = Relative
		self.Filt = Filt
		self.Count = Count
		self.Range = Range
		self.AutoRange = AutoRange

		# A bunch of commands to configure the 2182
		self.Visa.write("*RST")
		time.sleep(.1)
		self.Visa.write(":SENS:FUNC \'VOLT:DC\'")
		#self.Visa.write(":SENS:CHAN %d" % Channel)

#		if ACal:
#			self.Visa.write(":CAL:UNPR:ACAL:INIT")
#			time.sleep(1.0)
#			Reply = self.Visa.ask(":CAL:UNPR:ACAL:TEMP?")
#			time.sleep(10.)
#				#Reply = 1
#				#Reply = self.Visa.ask("*OPC?")
#			self.Visa.write(":CAL:UNPR:ACAL:DONE")

		self.Visa.ask(":READ?")
		# Disable concurrent mode, measure I and V (not R)
		self.SetRange(Range=Range,AutoRange=AutoRange)

		# Set some filters
#		if AFilt:
#			self.Visa.write(":SENS:VOLT:LPAS 1")
#		else:
#			self.Visa.write(":SENS:VOLT:LPAS 0")


		if self.Filt:
			self.Visa.write(":SENS:VOLT:AVER:STAT 1")
			self.Visa.write(":SENS:VOLT:AVER:COUN %d" % Count)
		else:
			self.Visa.write(":SENS:VOLT:AVER:STAT 0")

		self.Visa.ask(":READ?")

		self.Visa.write(":SENS:VOLT:REF:STAT 0")
		if Relative:
			self.Visa.write(":SENS:VOLT:REF:ACQ")
			self.Visa.write(":SENS:VOLT:REF:STAT 1")
			Reply = self.Visa.ask(":SENS:VOLT:REF?")
			print Reply
			self.RelativeValue = float(Reply)
		
		pass


	###########################################
	# Set the range and compliance
	#######################################
	
	def SetRange(self, Range = 0.1, AutoRange = False):

		if AutoRange:
			self.AutoRange = True
			self.Visa.write("".join((":SENS:",self.Sense,":RANG:AUTO 1")))
		else:
			self.Range = Range
			self.AutoRange = False
			self.Visa.write("".join((":SENS:",self.Sense,":RANG ","%.2e" % Range)))
		
		pass

	##################################################
	# Read data
	################################################

	def ReadData(self):
		self.Visa.write(":INIT")
		Reply = self.Visa.ask(":FETC?")
		self.Data = [float(Reply)]
		pass
	
	###############################################
	# Print a description string 
	################################################
	
	def Description(self):
		DescriptionString = "Keithley2002"
		for item in vars(self).items():
			if item[0] == "Address":
				DescriptionString = ", ".join((DescriptionString,"%s = %.3f" % item))
			elif item[0] == "Sense" or item[0] == "Range" or item[0] == "Relative" or item[0] == "RelativeValue":
				DescriptionString = ", ".join((DescriptionString,"%s = %s" % item))

		DescriptionString = "".join((DescriptionString,"\n"))
		return DescriptionString




