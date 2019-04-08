#!/usr/bin/python
# -*- coding: utf-8 -*-

"""

Sub programs for operation of the PicoWatt and Leiden TCS to control temperature

author : Eoin O'Farrell
email : phyoec@nus.edu.sg
last edited : August 2013


	The daemon listens for commands to change the control loop or setpoint
	The daemon broadcasts the current temperature
	
	!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
	Temperature units are Kelvin
	!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

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
from datetime import datetime

class TControl():

	# Initialization call, initialize LS340 visa and start the server
	# server always runs at 18871
	def __init__(self):
		self.Visa = visa.instrument("GPIB::27::INSTR")
		# start the server
		address = ('localhost',18871)
		self.Server = SocketUtils.SockServer(address)
		
		self.Temperature = np.zeros((4,)) 
		# for the 9T there are 4 temperatures VTI, probe, 1st stage, He Pot		
		# but we only set temperatures for VTI, probe and 4He pot
		# and there are only 2 loops...
		# It's a bit confusing so for the most part we ignore the 1st stage temp
		# We just push it to the terminal once every hour so that the user
		# can keep an eye on it.
		# For simplicity we define the temperature array to hold
		self.SensorName = ["VTI", "Probe", "4He pot","PTC Stage 1"]
		self.SensorLocation = [0,1,3,2]
		# there are 3 set temps
		self.SetTemp = np.zeros((3,))
		self.Status = -1
		# but there are only 2 loops :(
		self.LoopNumber = [1,2]
		self.ZoneControl = [False, False]
		self.LoopEnable = [False, False]
		self.PIDVals = np.empty((3,3))

		# For 9T there are 3 heater outputs main heater = VTI, Analog 1 = 4He Pot
		# Analog 2 = Probe
		# so we have the commands to read the heaters
		self.HeaterCommand = ["HTR?", "AOUT?2", "AOUT?1"]
		self.HeaterCurrent = np.zeros((3,))
		self.DeltaTemp = np.zeros((4,))
		self.MaxSetTemp = np.array([400.0,400.0,400.0])
		
		# The acceptable error in temperature as a factor of the
		# set temperature e.g. 2.0 K x 0.005 = 0.01 K
		self.ErrorTemp = 0.005
		# The acceptable stability as a factor of the error
		self.ErrorDeltaTemp = 0.1
		# We maintain the VTI slightly below the probe
		self.DeltaProbe = 0.0
		
		# Sweep description, temperature denotes probe temperatures
		self.SweepFinish = 0.0
		self.SweepRate = 0. # rate in K/min
		self.SweepTime = 0. # in seconds
		self.SweepDirection = 1.0
		self.SweepStartTime = []
		self.SweepTimeLength = 0.0
		self.SweepMaxOverTime = 15.0 # minutes

		# Status Parameters
		# Modes are 0: set, 1: sweep
		self.AtSet = False
		self.SweepMode = False
		self.StatusMsg = 0

		# Status events, every so often we push a status to the terminal
		self.StatusInterval = 0.1 # minutes
		self.LastStatusTime = datetime.now()
		
		# Turn off ramp mode
		self.Visa.write("RAMP 1,1,0")
		self.Visa.write("RAMP 2,0,0")

		return

	# The ls340 often formats replies X,Y,Z -> return selection of values
	def ls340AskMulti(self,Query,Return):
		Reply = self.Visa.ask(Query)
		Reply = Reply.split(",")
		Answer = list()
		for i in Return:
			Answer.append(Reply[i])

		return Answer

	# Get the loop paramters: enabled, control mode, PID, setpoints
	def GetLoopParams(self):
		
		for i,v in enumerate(self.LoopNumber):
			# enabled?
			Reply = self.ls340AskMulti(" ".join(("CSET?","%d" % v)),[2])
			self.LoopEnable[i] = bool(int(Reply[0]))
			# Control mode
			Reply = self.Visa.ask(" ".join(("CMODE?","%d" % v)))
			if Reply == "2":
				self.ZoneControl[i] = True
			else:
				self.ZoneControl[i] = False
			# PIDs
			Reply = self.ls340AskMulti(" ".join(("PID?","%d" % v)),[0,1,2])
			for j,u in enumerate(Reply):
				self.PIDVals[j,i] = float(u)
			# setpoints
			Reply = self.Visa.ask(" ".join(("SETP?","%d" % (i+1))))
			self.SetTemp[i] = float(Reply)

		return


	def ReadTempHeater(self):
		# read the temperature and heater outputs
		OldTemp = self.Temperature
		for i,v in enumerate(self.SensorLocation):
			# temperature
			Reply = self.Visa.ask(" ".join(("KRDG?","%d" % v)))
			self.Temperature[i] = float(Reply)
		self.DeltaTemp = self.Temperature - OldTemp

		# read the heaters
		for i,v in enumerate(self.HeaterCommand):
			Reply = self.Visa.ask(v)
			self.HeaterCurrent[i] = float(Reply)

		return

	# write set points to the instrument for the probe
	def UpdateSetTemp(self,SetTemp):

		SetTemp = [SetTemp - self.DeltaProbe, SetTemp]
		for i,v in enumerate(SetTemp):
			if (v < self.MaxSetTemp[i]) and (v >= 0.0):
				self.SetTemp[i] = v
			elif (v < 0.0):
				self.SetTemp[i] = 0.0
			else:
				self.SetTemp[i] = self.MaxSetTemp[i]

		return


	def WriteSetpoint(self):

		
		for i,v in enumerate(self.LoopNumber):
			#self.Visa.write("SETP 1, %.3e" %self.SetTemp[i])
			self.Visa.write("".join(("SETP ","%d," % v, "%.3f" % self.SetTemp[i])))
		
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
				if abs(self.SetTemp[1]-NewSet) > 0.05:
					if self.SweepMode:
						# We are sweeping so kill the sweep
						print "Killing sweep..."
						self.Visa.write("RAMP 1,0,0")
						self.Visa.write("RAMP 2,0,0")
					self.UpdateSetTemp(NewSet)
					# Set at set to be false and write the new set point
					self.AtSet = False
					self.SweepMode = False
					self.WriteSetpoint()
					print "Got probe set point from socket %.2f\n" % self.SetTemp[1]
			except:
				pass

		if Msg[0] == "SWP":
			print "Got temperature sweep"
			try:
				self.SweepFinish = float(Msg[1])
				if abs(self.SweepFinish - self.SetTemp[1]) > 0.05:
					self.SweepRate = abs(float(Msg[2]))
					self.SweepMaxOverTime = abs(float(Msg[3]))
					# Check if the sweep is up or down
					if self.SweepFinish >= self.SetTemp[1]:
						self.SweepDirection = 1.0
					else:
						self.SweepDirection = -1.0
					# Put the LS340 into ramp mode
					self.Visa.write("RAMP 1,1,%.3f" % self.SweepRate)
					self.Visa.write("RAMP 2,1,%.3f" % self.SweepRate)
					self.AtSet = False
					self.SweepTimeLength = abs(self.SetTemp[1] - self.SweepFinish)/self.SweepRate
					print "Got temperature sweep to %.2f K at %.2f K/min... Sweep takes %.2f minutes, maximum over time is %.2f" % (self.SweepFinish, self.SweepRate, self.SweepTimeLength, self.SweepMaxOverTime)
					# Write the finish temp
					self.UpdateSetTemp(self.SweepFinish)
					# Write the setpoint to start the ramp
					self.WriteSetpoint()
					self.SweepMode = True
					self.SweepStartTime = datetime.now()
					print "Starting the sweep\n"
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


	# Update the parameter AtSet for the probe
	def UpdateAtSet(self):
		Set = False
		# The stability measure is v crude
		Stable = False
		# 1 = Sweep
		ErrorFactor = abs(self.Temperature[1] - self.SetTemp[1])/self.Temperature[1]
		DeltaTempFactor = abs(self.DeltaTemp[1])/self.Temperature[1]
		if ErrorFactor < self.ErrorTemp:
			Set = True
		if DeltaTempFactor < self.ErrorDeltaTemp:
			Stable = True
		self.AtSet = Set and Stable
		return

	def SweepControl(self):
		
		# We are sweeping so check if the sweep is finished
		dT = datetime.now() - self.SweepStartTime
		dT = dT.seconds/60.0

		if dT > (self.SweepTimeLength + self.SweepMaxOverTime):
			# The sweep ran out of time, stop it
			SweepFinished = True
			print "Sweep over time... Finishing..."
		elif (self.Temperature[1] - self.SweepFinish)*self.SweepDirection > 0.0:
			SweepFinished = True
			print "Final temperature reached... Finishing..."
		else:
			SweepFinished = False

		if SweepFinished:
			# The sweep is finished stop ramping and change the mode
			self.Visa.write("RAMP 1,0,0")
			self.Visa.write("RAMP 2,0,0")
			# Write the setpoint to the current temperature
			self.UpdateSetTemp(self.Temperature[1])
			self.WriteSetpoint()
			self.SweepMode = False

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
		StatusString = ""
		for i,v in enumerate(self.Temperature):
			StatusString += "%s = %.3f K; " % (self.SensorName[i],self.Temperature[i])

		StatusString += "Status message = %d\n" % self.StatusMsg
		print StatusString
		self.LastStatusTime = datetime.now()
		return


if __name__ == '__main__':

	# Initialize a PID controller for the 4He Pot
	pid = PIDControl.PID(P=500,I=3,D=0,Derivator=0,Integrator=0,Integrator_max=250,Integrator_min=-50)

	control = TControl()

	control.GetLoopParams()
	control.ReadTempHeater()
	control.PrintStatus()

	control.SetTemp[2] = 3.7 # Set temperature for the He Pot
	pid.setPoint(control.SetTemp[2])

	while 1:
		
		# Read the picowatt and calculate the temperature
		control.ReadTempHeater()
		control.UpdateAtSet()
		control.UpdateStatusMsg()
		
		# Push the readings to clients and read messages
		for j in control.Server.handlers:
			j.to_send = ",%.4f %.4f %.4f %.4f %d" % (control.Temperature[0], control.Temperature[1], control.HeaterCurrent[0], control.HeaterCurrent[1], control.StatusMsg)
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

		# Now we do some PID stuff in software to control the He Pot
		NEWPID = pid.update(control.Temperature[2])
		#print "%.3f, %.3f" % (control.Temperature[2],NEWPID)
		if NEWPID > 60.0:
			NEWPID = 60.0
		elif NEWPID < 0.0:
			NEWPID = 0.0
		control.Visa.write("".join(("ANALOG 1,0,2,,,,,%.2f" % NEWPID)))
		
		time.sleep(0.8)

	control.Visa.close()

