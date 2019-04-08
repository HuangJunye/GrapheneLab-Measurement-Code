#!/usr/bin/python
# -*- coding: utf-8 -*-

"""

Sub programs for operation of Oxford Mercury iPS

author : Eoin O'Farrell
email : phyoec@nus.edu.sg
last edited : August 2013


	The daemon listens for commands to change the control loop or setpoint
	The daemon broadcasts the current temperature

ToDo:
	
	Listen
	Broadcast
	Initialize
	ReadPico
	CalcPID
	SetTCS

"""

import SocketUtils as SocketUtils
import logging
import visa as visa
import VisaSubs as VisaSubs
import string as string
import re as res
import time
import numpy as np
import asyncore
import PIDControl

class MControl():

	# Initialization call, initialize visas for the TCS, Picowatt and the
	# Server, server always runs at 18871
	def __init__(self):
		self.Visa = VisaSubs.InitializeSerial("ASRL8", term_chars = "\\n")
		
		self.Field = 0.0

		self.TCSVisa = VisaSubs.InitializeSerial("ASRL5",idn="ID?",term_chars="\\n")
		address = ('localhost',18871)
		self.Server = SocketUtils.SockServer(address)
		self.ResThermometer = 1
		self.Temperature = 0
		self.PicoChannel = 0
		self.PicoRange = 0
		self.SetTemp = -1
		self.Status = -1
		self.TCSHeater = [0,0,0]
		self.TCSRange = [1,1,1]
		self.TCSCurrent = [0,0,0]
		self.DeltaTemp = 0
		self.MaxTemp = 5000
		self.MaxCurrent = 10000
		self.ErrorTemp = 10 # The acceptable error in temperature
		self.ErrorDeltaTemp = 10 # The acceptable stability
		return

	############################################
	# Function to read one of the numeric signals
	###########################################

	def ReadNumeric(self, Command):
		# Form the query string (Now only for GRPZ)
		Query = "".join(("READ:DEV:GRPZ:PSU:SIG:",Command))
		Reply = self.Visa.ask(Query)
		# Find the useful part of the response
		Answer = string.rsplit(Reply,":",1)[1]
	
		# Some regex to get rid of the appended units
		Answer = re.split("[a-zA-Z]",Answer,1)[0]
		Answer = float(Answer)
	
		return Answer

	#########################################
	# Read one of the numeric configs
	########################################

	def ReadConfNumeric(self, Command):
		# Form the query string (Now only for GRPZ)
		Query = "".join(("READ:DEV:GRPZ:PSU:",Command))
		Reply = self.Visa.ask(Query)
		# Find the useful part of the response
		Answer = string.rsplit(Reply,":",1)[1]
		
		# Some regex to get rid of the appended units
		Answer = re.split("[a-zA-Z]",Answer,1)[0]
		Answer = float(Answer)

		return Answer

	############################################
	# Function to read the field in Tesla specifically
	###########################################

	def ReadField(self):
		# Form the query string (Now only for GRPZ)
		Query = "READ:DEV:GRPZ:PSU:SIG:FLD"
		Reply = self.Visa.ask(Query)
		# Find the useful part of the response
		Answer = string.rsplit(Reply,":",1)[1]
		
		# Some regex to get rid of the appended units
		Answer = re.split("[a-zA-Z]",Answer,1)[0]
		Answer = float(Answer)

		return Answer

	################################################
	# Function to set one of the numeric signals
	#############################################


	def MagnetSetNumeric(self, Command, Value):
		# Form the query string (Now only for GRPZ)
		writeCmd = "SET:DEV:GRPZ:PSU:SIG:%s:%.4f" % (Command, float(Value))
		Reply = self.Visa.ask(writeCmd)

		Answer = string.rsplit(Reply,":",1)[1]
		if Answer == "VALID":
			Valid = 1
		elif Answer == "INVALID":
			Valid = 0
		else:
			Valid = -1

		return Valid

	################################################
	# Function to set one of the numeric signals
	#############################################

	def MagnetSetNumeric(self, Command, Value):
		# Form the query string (Now only for GRPZ)
		writeCmd = "SET:DEV:GRPZ:PSU:SIG:%s:%.4f" % (Command, float(Value))
		Reply = self.Visa.ask(writeCmd)

		Answer = string.rsplit(Reply,":",1)[1]
		if Answer == "VALID":
			Valid = 1
		elif Answer == "INVALID":
			Valid = 0
		else:
			Valid = -1

		return Valid

	#############################################################
	# Function to read the switch heater state returns boolean
	###########################################################

	def MagnetReadHeater(self):
		Reply = self.Visa.ask("READ:DEV:GRPZ:PSU:SIG:SWHT")
		Answer = string.rsplit(Reply,":",1)[1]
		if Answer == "ON":
			Valid = 1
		elif Answer == "OFF":
			Valid = 0
		else:
			Valid = -1

		return Valid

	##################################################
	# Turn the switch heater ON (1) or OFF (0)
	####################################################

	def MagnetSetHeater(self, State):
		
		HeaterBefore = self.MagnetReadHeater()
		if State == 1:
			Reply = self.Visa.ask("SET:DEV:GRPZ:PSU:SIG:SWHT:ON")	
		elif State == 0:
			Reply = self.Visa.ask("SET:DEV:GRPZ:PSU:SIG:SWHT:OFF")
		else:
			print "Error cannot set switch heater\n"

		Answer = string.rsplit(Reply,":",1)[1]
		if Answer == "VALID":
			Heater = 1
		elif Answer == "INVALID":
			Heater = 0
		else:
			Heater = -1

		HeaterAfter = self.MagnetReadHeater()	
		if HeaterAfter != HeaterBefore:
			print "Heater Switched! Waiting 4 min\n"
			time.sleep(240)
			print "Finished wait!\n"

		return Heater

	#######################################################
	# Read the current magnet action e.g. HOLD, RTOZ etc.
	##########################################################

	def MagnetReadAction(self):
		
		Reply = self.Visa.ask("READ:DEV:GRPZ:PSU:ACTN")
		Answer = string.rsplit(Reply,":",1)[1]
		return Answer

	########################################################
	# Set the action for the magnet
	######################################################

	def MagnetSetAction(self, Command):
		
		Reply = self.Visa.ask("".join(("SET:DEV:GRPZ:PSU:ACTN:",Command)))	

		Answer = string.rsplit(Reply,":",1)[1]
		if Answer == "VALID":
			Valid = 1
		elif Answer == "INVALID":
			Valid = 0
		else:
			Valid = -1

		return Valid

	##########################################################
	# Check if it is safe to switch the switch heater
	#######################################################

	def MagnetCheckSwitchable(self):
		
		Heater = self.MagnetReadHeater()
		SourceCurrent = self.exposed_MagnetReadNumeric("CURR")
		PersistCurrent = self.exposed_MagnetReadNumeric("PCUR")

		if Heater == 1:
			Switchable = 1
		elif Heater == 0 and abs(SourceCurrent - PersistCurrent) <= 0.05:
			Switchable = 1
		elif Heater == 0 and abs(SourceCurrent - PersistCurrent) >= 0.05:
			Switchable = 0

		Action = self.MagnetReadAction()
		if Action == "RTOZ" or Action == "RTOS":
			Switchable = 0
	
		return Heater, Switchable

	##########################################################
	# Set the leads current, ignore the switch heater state
	##########################################################

	def MagnetGoCurrent(self, CSet, **kwargs):
		## Accepted keyword arguments are rate and sweep
		self.MagnetSetNumeric("CSET",CSet)
		# If a rate is defined set it
		QueryRate = kwargs.get("rate",False)
		if QueryRate:
			self.MagnetSetNumeric("RCST", QueryRate)
		
		SetRate = self.exposed_MagnetReadNumeric("RCST")

		self.MagnetSetAction("RTOS")
		print "Ramping source to %.4f A at %.4f A/m\n" % (CSet,SetRate)
		QuerySweep = kwargs.get("sweep",False)
		if not QuerySweep:
			# Job is not a sweep so track the magnet until done and then hold
			while abs(self.exposed_MagnetReadNumeric("CURR")-CSet) >= 0.05:
				time.sleep(3)
			self.MagnetSetAction("HOLD")
		else:
			print "Sweep started, exiting!\n"

	##########################################################
	# Set the coil, and begin a sweep if required
	########################################################

	def exposed_MagnetGoToSet(self, BSet, FinishHeater, **kwargs):

		# FinishHeater = 0 or 1
		# Accepted kwargs are rate and sweep
		print "Go to set call received!\n"

		self.MagnetSetAction("HOLD")

		QueryRate = kwargs.get("rate",False)
		QuerySweep = kwargs.get("sweep",False)

		# Check if the magnet is persistent and the current in the coil
		MagnetState = self.MagnetCheckSwitchable()

		BConversion = self.MagnetReadConfNumeric("ATOB")
		ISet = BSet * BConversion

		if MagnetState[0] == 1:
			ICoil = self.exposed_MagnetReadNumeric("CURR")
		
		elif MagnetState[0] == 0:
			ICoil = self.exposed_MagnetReadNumeric("PCUR")

		#################################

		if abs(ICoil - ISet) <= 0.05 and FinishHeater == MagnetState[0]:
			# The current is correct and the SW heater is correct, done!
			Status = 1
		
		elif abs(ICoil - ISet) <= 0.05 and FinishHeater != MagnetState[0]:
			# The current is correct but the heater is not
			if MagnetState[1] == 1:
				# magnet is switchable, switch it and then wait 4 min!
				self.MagnetSetHeater(FinishHeater)
				Status = 1

			elif MagnetState[1] == 0:
				# magnet is not switchable, set the leads current and ramp to set
				self.MagnetGoCurrent(ICoil)
				# Check the state
				Switchable = self.MagnetCheckSwitchable()
				if Switchable[1] == 1:
					self.MagnetSetHeater(FinishHeater)
					Status = 1
				else:
					Status = -1

		elif abs(ICoil - ISet) > 0.05:
			# The current is not correct
			if MagnetState[0] == 1:
				# Heater is on, go to set
				self.MagnetGoCurrent(ISet,rate = QueryRate,sweep = QuerySweep)
				Status = 1

			elif MagnetState[0] == 0:
				# Heater is not on, recursive call to switch it on
				self.exposed_MagnetGoToSet(ICoil/BConversion,1) 
				self.MagnetGoCurrent(ISet,rate = QueryRate,Sweep = QuerySweep)
				Status = 1

			# if the final heater state is for the heater to be off, turn it off
		if FinishHeater == 0 and not QuerySweep:
			Switchable = self.MagnetCheckSwitchable()
			if Switchable[1] == 1:
				self.MagnetSetHeater(FinishHeater)
				Status = 1
				# Ramp the source down
				self.MagnetGoCurrent(0)
			else:
				Status = -1

		# Check if the magnet is already at the set
		return Status
		

	def SetTCS(self,Source,Current):
		if Current < 0:
			Current = 0
		elif Current > self.MaxCurrent:
			Current = self.MaxCurrent
		# Current in microAmp
		command = " ".join(("SETDAC","%d" % Source,"0","%d" % Current))
		
		NEWPID = pid.update(control.Temperature)
		NEWPID = int(NEWPID)
		self.TCSVisa.ask(command)
		return

	def ReadPico(self):
		# Get the resistance of the current channel of the picowatt
		self.PicoVisa.write("ADC")
		time.sleep(0.4)
		Answer = self.PicoVisa.ask("RES ?")
		Answer = Answer.strip()
		try:
			self.ResThermometer = float(Answer)
		except:			
			self.ResThermometer = self.ResThermometer
			pass
		return

	def ReadPicoRange(self):
		Answer = self.PicoVisa.ask("RAN ?")
		Answer = Answer.strip()
		self.PicoRange = int(Answer)
		return

	def SetPicoChannel(self,Channel):
		self.PicoVisa.write("INP 0")
		Command = "".join(("MUX ","%d" % Channel))
		self.PicoVisa.write(Command)
		time.sleep(3)
		self.PicoVisa.write("INP 1")
		time.sleep(10)
		return

	def ReadTCS(self):
		Answer = self.TCSVisa.ask("STATUS?")
		Reply = Answer.split("\t")[1]
		Reply = Reply.split(",")
		Range = Reply[1::4]
		Current = Reply[2::4]
		Heaters = Reply[3::4]
		TMP = [1,10,100,1000]
		for i in range(3):
			self.TCSHeater[i] = int(Heaters[i])
		for i in range(3):
			self.TCSCurrent[i] = int(Current[i])*TMP[int(Range[i])-1]
		return

	def CalcTemperature(self,Calibration,factor=0):
		logR = np.log10(self.ResThermometer)-factor
		RPoly = np.ones((len(Calibration),))
		OldT = self.Temperature
		for i in range(1,len(RPoly)):
			RPoly[i] = logR * RPoly[i-1]
		self.Temperature = np.power(10,(np.sum(np.multiply(RPoly,Calibration))))
		self.DeltaTemp = abs(self.Temperature - OldT)
		return

	def UpdateStatus(self):
		OldStatus = self.Status
		if self.SetTemp <= 0:
			# There is no set point
			self.Status = -1
		elif (abs(self.SetTemp - self.Temperature) < self.ErrorTemp) and abs(self.DeltaTemp) <= self.ErrorDeltaTemp:
			# We are at the set point
			self.Status = 1
		else:
			# Going to Set
			self.Status = 0
		return

	# Interpret a message from the socket
	def ReadMsg(self,Msg):
		Msg = Msg.split(" ")
		GotSet = False
		if Msg[0] == "SET":
			try:
				NewSet = float(Msg[1])
				if abs(self.SetTemp-NewSet) > 5:
					if NewSet <= self.MaxTemp:
						self.SetTemp = NewSet
						GotSet = True
					else:
						self.SetTemp = self.MaxTemp
						GotSet = True
					print "Got new set point from socket %.2f" % self.SetTemp
			except:
				pass
		if Msg[0] == "T_ERROR":
			try:
				self.ErrorTemp = float(Msg[1])
			except:
				pass
		if Msg[0] == "DT_ERROR":
			try:
				self.ErrorDeltaTemp = float(Msg[1])
			except:
				pass
	
		return GotSet

	def TCSSwitchHeater(self,Heater):
		CommandVec = np.zeros((12,))
		CommandVec[2+Heater*4] = 1
		CommandStr = ""
		print "Heater %d Switched" % Heater
		for i in CommandVec:
			CommandStr = "".join((CommandStr, "%d," % i))
		CommandStr = CommandStr[:-1]
		self.TCSVisa.ask(" ".join(("SETUP",CommandStr)))
		return


##################### Calibrations
SO703 = [7318.782092,-13274.53584,10276.68481,-4398.202411,1123.561007,-171.3095557,14.43456504,-0.518534965]
SO914 = [5795.148097375,-11068.032226486,9072.821104899,-4133.466851312,1129.955799406,-185.318021359,16.881907269,-0.658939155]

if __name__ == '__main__':

	# Initialize a PID controller

	pid = PIDControl.PID(P=5,I=10,D=0,Derivator=0,Integrator=0,Integrator_max=10000,Integrator_min=-2000)

	control = TControl()
	control.SetPicoChannel(3)

	# Main loop
	control.ReadTCS()

	while 1:
		
		# Read the picowatt and calculate the temperature
		control.ReadPico()
		control.CalcTemperature(SO703)
		# Push the reading to clients
		for j in control.Server.handlers:
			j.to_send = ",%.3f %d" % (control.Temperature, control.Status)
			SocketMsg = j.received_data
			if SocketMsg:
				GotSet = control.ReadMsg(SocketMsg)
				if GotSet:
					pid.setPoint(control.SetTemp)
		asyncore.loop(count=1,timeout=0.001)
		
		# Now we should do some PID stuff
		control.UpdateStatus()

		NEWPID = pid.update(control.Temperature)
		NEWPID = int(NEWPID)
		if NEWPID < 0:
			NEWPID = 0
		if NEWPID > 10000:
			NEWPID = 10000

		if control.Status < 0 and control.TCSHeater[2] == 1:
			# if status is unset and the heater is on turn it off
			control.TCSSwitchHeater(2)
			control.ReadTCS()
		elif control.Status >= 0 and control.TCSHeater[2] == 0:
			# if status is set and heater is off turn it on
			control.TCSSwitchHeater(2)
			control.ReadTCS()
		elif control.Status >= 0 and control.TCSHeater[2] == 1:
			control.SetTCS(3,NEWPID)
			control.TCSCurrent[2] = NEWPID

		time.sleep(0.4)

	control.TCSVisa.close()

