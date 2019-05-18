#!/usr/bin/python
# -*- coding: utf-8 -*-

"""

Sub programs for operation of the PicoWatt and Leiden TCS to control temperature

original author : Eoin O'Farrell
current author : Huang Junye
last edited : Apr 2019


	The daemon listens for commands to change the control loop or setpoint
	The daemon broadcasts the current temperature

"""

import numpy as np
import asyncore
import time
from datetime import datetime

import utils.SocketUtils as SocketUtils
import utils.VisaSubs as VisaSubs
import utils.PIDControl as PIDControl

class TControl():

	""" Initialization call, initialize visas for the TCS, Picowatt and the
	Server, server always runs at 18871
	"""

	def __init__(self):

		self.PicoVisa = VisaSubs.InitializeGPIB(20,0,query_delay="0.04")
		self.PicoVisa.write("HDR0")
		self.PicoVisa.write("ARN 1")
		self.PicoVisa.write("REM 1")
		self.TCSVisa = VisaSubs.InitializeSerial("ASRL6::INSTR",idn="ID?")

		address = ('localhost',18871)
		self.Server = SocketUtils.SockServer(address)

		self.Resistance = 1.0
		self.Temperature = 0.0
		self.DeltaTemp = 1.0
		
		self.PicoChannel = 0
		self.PicoRange = 0
		
		self.SetTemp = -1.0

		self.TCSHeater = [0,0,0]
		self.TCSRange = [1,1,1]
		self.TCSCurrent = [0,0,0]
		
		self.MaxSetTemp = 10000.0
		self.MaxCurrent = 35000

		# Acceptable temperature error as a factor e.g. 100 * 0.005 = 0.5mK
		self.ErrorTemp = 0.01 # The acceptable error in temperature
		self.ErrorDeltaTemp = 0.005 # The acceptable stability

		# Sweep description
		self.SweepFinish = 0.0
		self.SweepStart = 0.0
		self.SweepRate = 1.0 # As received from socket in mK/min
		self.SweepRateSec = 1.0/60.0
		self.SweepTime = 0.0 # seconds
		self.SweepDirection = 1.0
		self.SweepStartTime = 0.0
		self.SweepTimeLength = 0.0
		self.SweepMaxOverTime = 15.0 # minutes

		# Status parameters
		self.AtSet = False
		self.SweepMode = False
		self.StatusMsg = 0 # not ready
		self.TempHistory = deque(np.zeros((60,)))

		# Status events
		self.StatusInterval = 1.0
		self.LastStatusTime = datetime.now()
		self.Sensor = "CERNOX"

		# Initialize a pid controller
		self.pid = PIDControl.PID(P=20.,I=.5,D=0,Derivator=0,Integrator=0,Integrator_max=60000,Integrator_min=-2000)

		return

	def SetTCS(self,Source,Current):
		if Current < 0:
			Current = 0
		elif Current > self.MaxCurrent:
			Current = self.MaxCurrent
		# Current in microAmp
		# print Current
		Source = Source + 1
		command = " ".join(("SETDAC","%d" % Source,"0","%d" % Current))
		
		self.TCSVisa.ask(command)
		return

	def ReadPico(self):
		# Get the resistance of the current channel of the picowatt
		self.PicoVisa.write("ADC")
		time.sleep(0.45)
		Answer = self.PicoVisa.ask("RES?")
		Answer = Answer.strip()
		try:
			self.Resistance = float(Answer)
		except:			
			self.Resistance = self.Resistance
			pass
		return

	def ReadPicoRange(self):
		Answer = self.PicoVisa.ask("RAN?")
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
		self.PicoChannel = Channel
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

	def CalcTemperature(self,Calibration,factor=0.0):
		logR = np.log10(self.Resistance)-factor
		RPoly = np.ones((len(Calibration),))
		OldT = self.Temperature
		for i in range(1,len(RPoly)):
			RPoly[i] = logR * RPoly[i-1]
		self.Temperature = np.power(10,(np.sum(np.multiply(RPoly,Calibration))))
		self.DeltaTemp = self.Temperature - OldT

		self.TempHistory.pop()
		self.TempHistory.appendleft(self.Temperature)
		return

	# Update the parameter AtSet for the probe
	def UpdateAtSet(self):
		Set = False
		# The stability measure is v crude
		Stable = False
		# 1 = Sweep
		ErrorFactor = abs(self.Temperature - self.SetTemp)/self.Temperature
		DeltaTempFactor = abs(np.std(self.TempHistory))/self.Temperature
		if ErrorFactor < self.ErrorTemp:
			Set = True
		if DeltaTempFactor < self.ErrorDeltaTemp:
			Stable = True
		self.AtSet = Set and Stable
		return

	# Interpret a message from the socket, current possible messages are
	# SET ...  -  set probe the temperature
	# SWP ...  -  sweep the probe temperature 
	def ReadMsg(self,Msg):
		Msg = Msg.split(" ")
		
		if Msg[0] == "SET":
			try:
				NewSet = float(Msg[1])
				# Only interpret new setpoints if the change is >50mK
				if abs(self.SetTemp-NewSet) > 0.05:
					self.SetTemp = NewSet
					if self.PicoChannel == 5:
						pass
					#elif self.SetTemp > 800:
					#	self.pid.setKp(20.)
					#else:
					#	self.pid.setKp(10.)
					self.pid.setPoint(self.SetTemp)
					# Set at set to be false and write the new set point
					self.AtSet = False
					self.SweepMode = False
					print("Got probe set point from socket %.2f\n" % self.SetTemp)
			except:
				pass

		if Msg[0] == "SWP":
			try:
				self.SweepFinish = float(Msg[1])
				if abs(self.SweepFinish - self.SetTemp) > 0.05:
					self.SweepStart = self.SetTemp
					self.pid.setPoint(self.SetTemp)
					self.SweepRate = abs(float(Msg[2]))
					self.SweepRateSec = self.SweepRate/60.0
					self.SweepMaxOverTime = abs(float(Msg[3]))
					# Check if the sweep is up or down
					if self.SweepFinish >= self.SetTemp:
						self.SweepDirection = 1.0
					else:
						self.SweepDirection = -1.0
					# Put the LS340 into ramp mode
					self.AtSet = False
					self.SweepTimeLength = abs(self.SetTemp - self.SweepFinish)/self.SweepRate
					print("Got temperature sweep to %.2f K at %.2f K/min... Sweep takes %.2f minutes, maximum over time is %.2f" % (self.SweepFinish, self.SweepRate, self.SweepTimeLength, self.SweepMaxOverTime))
					# Write the finish temp
					# Write the setpoint to start the ramp
					self.SweepMode = True
					self.SweepStartTime = datetime.now()
					print("Starting the sweep\n")
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

		return

	def SweepControl(self):
		
		# We are sweeping so check if the sweep is finished
		dT = datetime.now() - self.SweepStartTime
		dTMin = dT.seconds/60.0

		if dTMin > (self.SweepTimeLength + self.SweepMaxOverTime):
			# The sweep ran out of time, stop it
			SweepFinished = True
			print("Sweep over time... Finishing...")
		elif (self.Temperature - self.SweepFinish)*self.SweepDirection > 0.0:
			SweepFinished = True
			print("Final temperature reached... Finishing...")
		else:
			SweepFinished = False

		if SweepFinished:
			self.SweepMode = False
		else:
			OldSet = self.SetTemp
			self.SetTemp = self.SweepStart + self.SweepRateSec * dT.seconds * self.SweepDirection
			
			if self.PicoChannel == 5:
				pass
			#elif (OldSet < 800.) and (self.SetTemp > 800.):
			#	self.pid.setKp(20.)
			#elif (OldSet > 800.) and (self.SetTemp < 800.):
			#	self.pid.setKp(10.)
			self.pid.setPoint(self.SetTemp,reset=False)

		return



	def UpdateStatusMsg(self):
		# TDaemon status messages:
		# 0 = Not ready
		# 1 = Ready

		if self.AtSet and not self.SweepMode:
			Status = 1 # Ready
		else:
			Status = 0 # Not ready
			
		self.StatusMsg = Status
		return

	def PrintStatus(self):
		StatusString = "%s = %.2f K; PID output = %d; " % (self.Sensor,self.Temperature,self.PIDOut)
		StatusString += "Status message = %d; " % self.StatusMsg
		StatusString += "P = %.2f, I = %.2f, D = %.2f\n" % (self.pid.P_value,self.pid.I_value,self.pid.D_value)	
		print(StatusString)
		self.LastStatusTime = datetime.now()
		return

	def TCSSwitchHeater(self,Heater):
		CommandVec = np.zeros((12,))
		CommandVec[2+Heater*4] = 1
		CommandStr = "SETUP "
		print("Heater %d Switched %d" % (Heater,int(not self.TCSHeater[Heater])))
		for i in CommandVec:
			CommandStr = "".join((CommandStr, "%d," % i))
		CommandStr = CommandStr[:-1]
		reply = self.TCSVisa.ask(CommandStr)
		return


##################### Calibrations
Calibrations={"SO703":[7318.782092,-13274.53584,10276.68481,
	-4398.202411,1123.561007,-171.3095557,14.43456504,-0.518534965],
		"SO914":[5795.148097375,-11068.032226486,9072.821104899,
			-4133.466851312,1129.955799406,-185.318021359,16.881907269,-0.658939155],
		"MATS56":[19.68045382,-20.19660902,10.13318296,-2.742724207,0.385556989,-0.022178276],
		"CERNOX":[4.62153,-1.17709,-0.222229,-2.3114e-11]}


if __name__ == '__main__':

	# Initialize a PID controller

	control = TControl()

	control.SetPicoChannel(5) #ch5 for CERNOX. Do not use below 1K
	control.Sensor = "CERNOX"

	# Main loop
	control.ReadTCS()

	while True:
		
		# Read the picowatt and calculate the temperature
		control.ReadPico()
		control.CalcTemperature(Calibrations[control.Sensor])
		control.UpdateAtSet()		
		control.UpdateStatusMsg()
		
		# Push the reading to clients
		for j in control.Server.handlers:
			j.to_send = ",%.3f %d" % (control.Temperature, control.StatusMsg)
			SocketMsg = j.received_data
			if SocketMsg:
				control.ReadMsg(SocketMsg)
		asyncore.loop(count=1,timeout=0.001)
		
		# if we are sweeping we do some things specific to the sweep
		if control.SweepMode:
			control.SweepControl()

		# check if we should send an update
		UpdateTime = datetime.now() - control.LastStatusTime
		if UpdateTime.seconds/60.0 >= control.StatusInterval:
			control.PrintStatus()
	
		NEWPID = control.pid.update(control.Temperature)
		try:
			control.PIDOut = int(NEWPID)
		except:
			control.PIDOut = 0
			pass

		if control.PIDOut < 0:
			control.PIDOut = 0
		elif control.PIDOut > control.MaxCurrent:
			control.PIDOut = control.MaxCurrent

		if control.PIDOut > 0 and control.TCSHeater[2] == 0:
			# status is go to set and heater is off --> turn it on
			control.SetTCS(2,control.PIDOut)
			control.TCSSwitchHeater(2)
			control.ReadTCS()
		elif control.PIDOut <= 0 and control.TCSHeater[2] == 1:
			# status is go to set and heater is off --> turn it on
			control.TCSSwitchHeater(2)
			control.SetTCS(2,0)			
			control.ReadTCS()
		elif control.PIDOut >= 0 and control.TCSHeater[2] == 1:
			control.SetTCS(2,control.PIDOut)
			control.TCSCurrent[2] = control.PIDOut

		time.sleep(0.5)

	control.TCSVisa.close()

