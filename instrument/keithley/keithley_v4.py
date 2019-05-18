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

import time

import numpy as np

import utils.visa_subs as visa_subs


class K6430:
	def __init__(self, address):
		self.name = "Keithley 6430"
		self.address = address
		self.visa = visa_subs.initialize_gpib(address, 0)

	######################################
	# Initialize as voltage source
	#######################################

	def initialize_voltage(
			self, compliance=105e-9, median=0, repetition=1, moving=1,
			integration=1, delay=0.0, trigger=0, ramp_step=0.1, sense_range=105e-9,
			auto_range=False, auto_filter=False, auto_delay=False
	):

		self.column_names = "V (V), I (A)"
		self.data = [0.0, 0.0]
		self.data_column = 1
		self.source_column = 0
		self.source = "VOLT"
		self.sense = "CURR"
		self.moving = moving
		# Special variables for 6430
		self.median = median
		self.repetition = repetition
		self.integration = integration
		self.delay = delay
		self.compliance = compliance
		self.ramp_step = ramp_step
		self.sense_range = sense_range
		self.output = False
		self.visa.write(":OUTP 0")
		self.trigger = trigger

		# A bunch of commands to configure the 6430
		self.visa.write("*RST")
		time.sleep(.1)
		self.visa.write(":SOUR:FUNC:MODE VOLT")
		# Configure the auto zero (reference)
		self.visa.write(":SYST:AZER:STAT ON")
		self.visa.write(":SYST:AZER:CACH:STAT 1")
		self.visa.write(":SYST:AZER:CACH:RES")

		# Disable concurrent mode, measure I and V (not R)
		self.visa.write(":SENS:FUNC:CONC 1")

		self.visa.write(":SENS:FUNC:ON \"VOLT\",\"CURR\"")
		self.visa.write(":FORM:ELEM VOLT,CURR")

		self.visa.write(":SENS:CURR:PROT:LEV %.3e" % self.compliance)
		if auto_range:
			self.visa.write(":SENS:CURR:RANG:AUTO 1")
		else:
			self.visa.write(":SENS:CURR:RANG %.2e" % self.sense_range)

		# Set some filters
		
		if auto_filter:
			self.visa.write(":SENS:AVER:AUTO ON")
		else:
			self.visa.write(":SENS:CURR:NPLC %.2f" % self.integration)
			self.visa.write(":SENS:AVER:REP:COUN %d" % self.repetition)
			self.visa.write(":SENS:AVER:COUN %d" % self.moving)
			self.visa.write(":SENS:MED:RANK %d" % self.median)
		
		if auto_delay:
			self.visa.write(":SOUR:DEL:AUTO ON")
		else:
			self.visa.write(":SOUR:DEL %.4f" % self.delay)
		
		self.visa.write(":TRIG:DEL %.4f" % self.trigger)
		
		pass

	######################################
	# Initialize as current source
	#######################################

	def initialize_current(
			self, compliance=1.0,
			median=0, repetition=1,
			integration=1, delay=0.0, trigger=0,
			ramp_step=0.1, sense_range=1.0, auto_range=False):

		self.column_names = "V (V), I (A)"
		self.data_column = 0
		self.source_column = 1
		self.source = "CURR"
		self.sense = "VOLT"
		# Special variables for 6430
		self.median = median
		self.repetition = repetition
		self.integration = integration
		self.delay = delay
		self.compliance = compliance
		self.ramp_step = ramp_step
		self.sense_range = sense_range
		self.trigger = trigger

		# A bunch of commands to configure the 6430
		self.visa.write("*RST")
		self.visa.write(":SYST:BEEP:STAT 0")
		time.sleep(.1)
		self.visa.write(":SOUR:FUNC:MODE CURR")
		# Configure the auto zero (reference)
		self.visa.write(":SYST:AZER:STAT ON")
		self.visa.write(":SYST:AZER:CACH:STAT 1")
		self.visa.write(":SYST:AZER:CACH:RES")

		# Disable concurrent mode, measure I and V (not R)
		self.visa.write(":SENS:FUNC:CONC 1")

		self.visa.write(":SENS:FUNC:ON \"VOLT\",\"CURR\"")
		self.visa.write(":FORM:ELEM VOLT,CURR")
		
		self.visa.write(":SENS:VOLT:PROT:LEV %.3e" % self.compliance)

		if auto_range:
			self.visa.write(":SENS:VOLT:RANG:AUTO 1")
		else:
			self.visa.write(":SENS:VOLT:RANG %.2e" % self.sense_range)
		# Set some filters
		self.visa.write(":SENS:CURR:NPLC %.2f" % self.integration)
	
		self.visa.write(":SENS:AVER:REP:COUN %d" % self.repetition)
		self.visa.write(":SENS:MED:RANK %d" % self.median)
		
		self.visa.write(":SOUR:DEL %.4f" % self.delay)
		self.visa.write(":TRIG:DEL %.4f" % self.trigger)
		
		pass

	###########################################
	# Set the range and compliance
	#######################################
	
	def set_range_compliance(self, sense_range=105, compliance=105):

		self.compliance = compliance
		self.visa.write("".join((":SENS:", self.sense, ":PROT:LEV %.3e" % self.compliance)))
		
		if sense_range:
			self.visa.write("".join((":SENS:", self.sense, ":RANG ", "%.2e" % sense_range)))
		else:
			self.visa.write("".join((":SENS:", self.sense, ":RANG:AUTO 1")))
		
		pass

	##################################################
	# Read data
	################################################

	def read_data(self):
		reply = self.visa.ask(":READ?")
		self.data = [float(i) for i in reply.split(",")[0:2]]
		pass
	
	##################################################
	# Set source
	##################################################

	def set_output(self, level):
		self.visa.write("".join((":SOUR:", self.source, " %.4e" % level)))
		pass

	#################################################
	# Switch the output
	###############################################

	def switch_output(self):
		self.output = not self.output		
		self.visa.write("".join((":OUTP:STAT ", "%d" % self.output)))
		pass
	
	#################################################
	# Configure a sweep
	###############################################

	def configure_sweep(self, start, stop, step, soak=0):
		self.visa.write("".join((":SOUR:", self.source, ":START %.4e" % start)))
		self.visa.write("".join((":SOUR:", self.source, ":STOP %.4e" % stop)))
		self.visa.write("".join((":SOUR:", self.source, ":STEP %.4e" % step)))
		count = int(1+abs(stop - start)/step)
		self.visa.write(":SOUR:SOAK %.4e" % soak)
		self.visa.write("TRIG:COUN %d" % count)
		pass

	###################################################
	# Begin sweep, this doesn't work so well, not recommended
	#################################################

	def run_configured_sweep(self):
		self.visa.write(":SOUR:VOLT:MODE SWE")
		self.visa.write(":SOUR:SWE:SPAC LIN")
		self.visa.write(":SOUR:SWE:RANG AUTO")
		self.visa.write(":SOUR:DEL %0.4e" % self.delay)
		self.switch_output()
		pass

	###################################################
	# Print a description string 
	################################################
	
	def description(self):
		description_string = "Keithley6430"
		for item in list(vars(self).items()):
			if item[0] == "address":
				description_string = ", ".join((description_string, "%s = %.3f" % item))
			elif item[0] == "source" or item[0] == "sense" or item[0] == "compliance":
				description_string = ", ".join((description_string, "%s = %s" % item))

		description_string = "".join((description_string, "\n"))
		return description_string

	############################################
	# ramp the source to a final value
	#########################################
	
	def ramp(self, v_finish):
		if self.output:
			self.read_data()
		v_start = self.data[self.source_column]
		if abs(v_start-v_finish) > self.ramp_step:	
			n = abs((v_finish-v_start)/self.ramp_step)
			v_sweep = np.linspace(v_start, v_finish, num=np.ceil(n), endpoint=True)

			if not self.output:
				self.switch_output()

			for i in range(len(v_sweep)):
				self.set_output(v_sweep[i])
				time.sleep(0.01)

			self.read_data()
		return


class K2400:
	def __init__(self, address):
		self.name = "Keithley 2400"
		self.address = address
		self.visa = visa_subs.initialize_gpib(address, 0)

	######################################
	# Initializate as voltage source
	#######################################

	def initialize_voltage(
			self, compliance=105e-9,
			ramp_step=0.1, auto_range=False,
			reset=True, source_range=21):

		self.source = "VOLT"
		self.ramp_step = ramp_step
		self.column_names = "V (V), I (A)"
		self.data_column = 1
		self.source = "VOLT"
		self.sense = "CURR"
		self.data = [0.0, 0.0]

		if reset:
			self.compliance = compliance
			self.output = False
			self.visa.write(":OUTP 0")
			# A bunch of commands to configure the 6430
			self.visa.write("*RST")
			self.visa.write(":SYST:BEEP:STAT 0")
			time.sleep(.1)
			self.visa.write(":SOUR:FUNC:MODE VOLT")
			self.visa.write(":SOUR:VOLT:RANG %d" % source_range)
			# Configure the auto zero (reference)
			self.visa.write(":SYST:AZER:STAT ON")
			self.visa.write(":SYST:AZER:CACH:STAT 1")
			self.visa.write(":SYST:AZER:CACH:RES")
			# Disable concurrent mode, measure I and V (not R)
			self.visa.write(":SENS:FUNC:CONC 1")
			self.visa.write(":SENS:FUNC:ON \"VOLT\",\"CURR\"")
			self.visa.write(":FORM:ELEM VOLT,CURR")
			if auto_range:
				self.visa.write(":SENS:CURR:RANG:AUTO 0")
			else:
				self.visa.write(":SENS:CURR:RANG 105e-9")
			self.visa.write(":SENS:CURR:PROT:LEV %.3e" % self.compliance)
		else:
			self.output = bool(int(self.visa.ask(":OUTP:STAT?")))
			self.compliance = float(self.visa.ask(":SENS:CURR:PROT:LEV?"))
			self.read_data()
	
		return
	
	###########################################
	# Set the range and compliance
	#######################################
	
	def set_range_compliance(self, sense_range=105e-9, compliance=105e-9):

		self.compliance = compliance
		self.visa.write("".join((":SENS:", self.sense, ":PROT:LEV %.3e" % self.compliance)))
		
		if sense_range:
			self.visa.write("".join((":SENS:", self.sense, ":RANG ", "%.3e" % sense_range)))
		else:
			self.visa.write("".join((":SENS:", self.sense, ":RANG:AUTO 1")))
		
		pass

	##################################################
	# Read data
	################################################

	def read_data(self):
		reply = self.visa.ask(":READ?")
		self.data = [float(i) for i in reply.split(",")[0:2]]
		pass
	
	##################################################
	# Set source
	##################################################

	def set_output(self, level):
		self.visa.write("".join((":SOUR:", self.source, " %.4e" % level)))
		pass

	#################################################
	# Switch the output
	###############################################

	def switch_output(self):
		self.output = not self.output		
		self.visa.write("".join((":OUTP:STAT ", "%d" % self.output)))
		pass

	###################################################
	# Print a description string 
	################################################
	
	def description(self):
		description_string = "Keithley2400"
		for item in list(vars(self).items()):
			if item[0] == "address":
				description_string = ", ".join((description_string, "%s = %.3f" % item))
			elif item[0] == "source" or item[0] == "sense" or item[0] == "compliance":
				description_string = ", ".join((description_string, "%s = %s" % item))

		description_string = "".join((description_string, "\n"))
		return description_string

	############################################
	# ramp the source to a final value
	#########################################
	
	def ramp(self, v_finish):
		if self.output:
			self.read_data()
		v_start = self.data[0]
		if abs(v_start-v_finish) > self.ramp_step:
			n = abs((v_finish-v_start)/self.ramp_step)
			v_sweep = np.linspace(v_start, v_finish, num=np.ceil(n), endpoint=True)

			if not self.output:
				self.switch_output()

			for i in range(len(v_sweep)):
				self.set_output(v_sweep[i])
				time.sleep(0.01)

			self.read_data()
		
		return


class K6221:
	# The 6221 operates only as a source, these functions configure it as an AC source (WAVE mode)
	# and the measurement is made by the Lockin

	def __init__(self, address):
		self.name = "Keithley 6221"
		self.address = address
		self.visa = visa_subs.initialize_gpib(address, 0)
		# Other 6430 properties
		# Query the output state
		self.output = False
		reply = self.visa.ask(":OUTP:STAT?")
		reply = int(reply)
		self.output = bool(reply)
		if self.output:
			self.compliance = self.read_numeric(":SOUR:CURR:COMP?")
			self.frequency = self.read_numeric(":SOUR:WAVE:FREQ?")
			self.amplitude = self.read_numeric(":SOUR:WAVE:AMPL?")
			self.offset = self.read_numeric(":SOUR:WAVE:OFFS?")
			self.phase = self.read_numeric(":SOUR:WAVE:PMAR?")
			self.trigger_pin = 2
		else:
			self.compliance = 0.0
			self.frequency = 9.2
			self.amplitude = 0.0  # Amperes
			self.offset = 0.0
			self.phase = 0.0  # position of the phase marker
			self.trigger_pin = 2  # pin to write the trigger
			self.visa.write(":SOUR:CLE:IMM")
		self.ramp_step = 10e-9
		self.source = "CURR"
		self.column_names = "I (A)"
		self.data_column = 0
		self.data = [self.amplitude]  # Amperes
		# Move the trigger pin so we can set the phase marker to line 2

	######################################
	# Initialize as voltage source
	#######################################

	def initialize_wave(
			self, compliance=0.1, ramp_step=1e-9, auto_range=True,
			frequency=9.2, offset=0.0, phase=0.0
	):

		self.column_names = "I (A)"
		self.data_column = 0
		self.source = "CURR"
		# A bunch of commands to configure the 6430
		if not self.output:
			self.compliance = compliance
			self.ramp_step = ramp_step
			self.frequency = frequency
			self.offset = offset
			self.phase = phase
			self.visa.write("*RST")
			time.sleep(.1)
			# self.visa.write(":OUTP:LTE ON")
			self.visa.write(":SOUR:WAVE:FUNC SIN")
			if auto_range:
				self.visa.write(":SOUR:WAVE:RANG BEST")
			else:
				self.visa.write(":SOUR:WAVE:RANG FIX")
	
			self.visa.write(":TRIG:OLIN 4")
			self.visa.write(":SOUR:WAVE:PMAR:OLIN %d" % self.trigger_pin)
			self.visa.write(":SOUR:WAVE:PMAR:STAT ON")
			self.visa.write(":SOUR:WAVE:PMAR %.1f" % self.phase)
	
			self.visa.write(":SOUR:CURR:COMP %.3e" % self.compliance)
			self.visa.write(":SOUR:WAVE:FREQ %.3e" % self.frequency)
			self.visa.write(":SOUR:WAVE:OFFS %.3e" % self.offset)
			self.visa.write(":SOUR:WAVE:AMPL %.3e" % self.ramp_step)

		return

	##################################################
	# Read numeric
	################################################

	def read_numeric(self, command):
		reply = self.visa.ask(command)
		answer = float(reply)
		return answer

	##################################################
	# Set source
	##################################################

	def set_output(self, level):
		self.visa.write(":SOUR:WAVE:AMPL %.4e" % level)
		pass

	#################################################
	# Switch the output
	###############################################

	def switch_output(self):
		self.output = not self.output
		if self.output:
			self.visa.write(":SOUR:WAVE:ARM")
			self.visa.write(":SOUR:WAVE:INIT")
		else:
			self.visa.write(":SOUR:WAVE:ABOR")

		pass

	###################################################
	# Print a description string 
	################################################
	
	def description(self):
		description_string = "Keithley6221"
		for item in list(vars(self).items()):
			if item[0] == "address" or item[0] == "amplitude" or item[0] == "frequency":
				description_string = ", ".join((description_string, "%s = %.3f" % item))
			elif item[0] == "Compliance":
				description_string = ", ".join((description_string, "%s = %s" % item))

		description_string = "".join((description_string, "\n"))
		return description_string

	############################################
	# ramp the source to a final value
	#########################################
	
	def ramp(self, v_finish):
		v_start = self.amplitude
		if abs(v_start-v_finish) > self.ramp_step:

			if self.output:
				self.switch_output()

			self.set_output(v_finish)
			self.switch_output()

			self.amplitude = v_finish
			self.data[0] = v_finish
		
		return


class K2182a:
	def __init__(self, address):
		self.name = "Keithley 2182A"
		self.address = address
		self.visa = visa_subs.initialize_gpib(address, 0)

	######################################
	# Initializate as voltage source
	#######################################

	def initialize_voltage(
			self, channel=1, a_cal=False, relative=False, a_filt=False,
			d_filt=True, count=5, sense_range=1., auto_range=False
	):

		self.column_names = "V (V)"
		self.data = [0.0]
		self.data_column = 0
		self.sense = "VOLT"
		# Special variables for 2182
		self.channel = channel
		self.relative = relative
		self.a_filt = a_filt
		self.d_filt = d_filt
		self.count = count
		self.sense_range = sense_range
		self.auto_range = auto_range

		# A bunch of commands to configure the 2182
		self.visa.write("*RST")
		time.sleep(.1)
		self.visa.write(":SENS:FUNC \'VOLT\'")
		self.visa.write(":SENS:CHAN %d" % channel)

		if a_cal:
			self.visa.write(":CAL:UNPR:ACAL:INIT")
			time.sleep(1.0)
			reply = self.visa.ask(":CAL:UNPR:ACAL:TEMP?")
			time.sleep(10.)
			self.visa.write(":CAL:UNPR:ACAL:DONE")

		# Disable concurrent mode, measure I and V (not R)
		self.set_sense_range(sense_range=sense_range, auto_range=auto_range)

		# Set some filters
		if a_filt:
			self.visa.write(":SENS:VOLT:LPAS 1")
		else:
			self.visa.write(":SENS:VOLT:LPAS 0")

		if d_filt:
			self.visa.write(":SENS:VOLT:DFIL 1")
			self.visa.write(":SENS:VOLT:DFIL:COUN %d" % count)
		else:
			self.visa.write(":SENS:VOLT:DFIL 0")

		self.visa.ask(":READ?")

		self.visa.write(":SENS:VOLT:REF:STAT 0")
		if relative:
			self.visa.write(":SENS:VOLT:REF:ACQ")
			self.visa.write(":SENS:VOLT:REF:STAT 1")
			reply = self.visa.ask(":SENS:VOLT:REF?")
			print(reply)
			self.relative_value = float(reply)
		
		pass

	###########################################
	# Set the range and compliance
	#######################################
	
	def set_sense_range(self, sense_range=0.1, auto_range=False):

		if auto_range:
			self.auto_range = True
			self.visa.write("".join((":SENS:", self.sense, ":RANG:AUTO 1")))
		else:
			self.sense_range = sense_range
			self.auto_range = False
			self.visa.write("".join((":SENS:", self.sense, ":RANG ", "%.2e" % sense_range)))
		
		pass

	##################################################
	# Read data
	################################################

	def read_data(self):
		reply = self.visa.ask(":READ?")
		self.data = [float(reply)]
		pass
	
	###############################################
	# Print a description string 
	################################################
	
	def description(self):
		description_string = "Keithley2182"
		for item in list(vars(self).items()):
			if item[0] == "address":
				description_string = ", ".join((description_string, "%s = %.3f" % item))
			elif item[0] == "sense" or item[0] == "sense_range" or item[0] == "relative" or item[0] == "relative_value":
				description_string = ", ".join((description_string, "%s = %s" % item))

		description_string = "".join((description_string, "\n"))
		return description_string


class K2002:
	def __init__(self, address):
		self.name = "Keithley 2002"
		self.address = address
		self.visa = visa_subs.initialize_gpib(address, 0)

	######################################
	# Initializate as voltage source
	#######################################

	def initialize_voltage(
			self, a_cal=False, relative=False, filt=True,
			count=5, sense_range=2., auto_range=False
	):

		self.column_names = "V (V)"
		self.data = [0.0]
		self.data_column = 0
		self.sense = "VOLT"
		# Special variables for 2002
		self.relative = relative
		self.filt = filt
		self.count = count
		self.sense_range = sense_range
		self.auto_range = auto_range

		# A bunch of commands to configure the 2182
		self.visa.write("*RST")
		time.sleep(.1)
		self.visa.write(":SENS:FUNC \'VOLT:DC\'")
		self.visa.ask(":READ?")
		# Disable concurrent mode, measure I and V (not R)
		self.set_sense_range(sense_range=sense_range, auto_range=auto_range)

		if self.filt:
			self.visa.write(":SENS:VOLT:AVER:STAT 1")
			self.visa.write(":SENS:VOLT:AVER:COUN %d" % count)
		else:
			self.visa.write(":SENS:VOLT:AVER:STAT 0")

		self.visa.ask(":READ?")

		self.visa.write(":SENS:VOLT:REF:STAT 0")
		if relative:
			self.visa.write(":SENS:VOLT:REF:ACQ")
			self.visa.write(":SENS:VOLT:REF:STAT 1")
			reply = self.visa.ask(":SENS:VOLT:REF?")
			print(reply)
			self.relative_value = float(reply)
		
		pass

	###########################################
	# Set the range and compliance
	#######################################
	
	def set_sense_range(self, sense_range=0.1, auto_range=False):

		if auto_range:
			self.auto_range = True
			self.visa.write("".join((":SENS:", self.sense, ":RANG:AUTO 1")))
		else:
			self.sense_range = sense_range
			self.auto_range = False
			self.visa.write("".join((":SENS:", self.sense, ":RANG ", "%.2e" % sense_range)))
		
		pass

	##################################################
	# Read data
	################################################

	def read_data(self):
		self.visa.write(":INIT")
		reply = self.visa.ask(":FETC?")
		self.data = [float(reply)]
		pass
	
	###############################################
	# Print a description string 
	################################################
	
	def description(self):
		description_string = "Keithley2002"
		for item in list(vars(self).items()):
			if item[0] == "address":
				description_string = ", ".join((description_string, "%s = %.3f" % item))
			elif item[0] == "sense" or item[0] == "sense_range" or item[0] == "relative" or item[0] == "relative_value":
				description_string = ", ".join((description_string, "%s = %s" % item))

		description_string = "".join((description_string, "\n"))
		return description_string
