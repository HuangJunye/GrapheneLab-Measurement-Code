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
		self.Temperature = np.zeros((2,)) 		
		self.SensorName = ["Probe", "VTI"]
		self.SensorLocation = ["A","B"]		
		self.SetTemp = np.zeros((2,))
		self.Status = -1		
		self.LoopNumber = [1,2]
		self.ZoneControl = [False, False]
		self.LoopEnable = [False, False]
		self.PIDVals = np.empty((3,3))
		self.HeaterCommand = ["HTR?"]
		self.HeaterCurrent = np.zeros((3,))
		self.DeltaTemp = np.zeros((2,))
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
		self.SweepMaxOverTime = 60.0 # minutes
		# Status Parameters
		# Modes are 0: set, 1: sweep
		self.AtSet = False
		self.SweepMode = False
		self.StatusMsg = 0
		# Status events, every so often we push a status to the terminal
		self.StatusInterval = 0.1 # minutes
		self.LastStatusTime = datetime.now()
		# Turn off ramp mode
		self.Visa.write("RAMP 1,0,0")
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
			Reply = self.Visa.ask(" ".join(("KRDG?","%s" % v)))
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
			self.Visa.write("".join(("SETP ","%d," % v, "%.3f" % self.SetTemp[i])))
		return

	# Interpret a message from the socket, current possible messages are
	# SET ...  -  set probe the temperature
	# SWP ...  -  sweep the probe temperature 
	def ReadMsg(self,Msg):
		Tindex = 0
		Msg = Msg.split(" ")
		if Msg[0] == "SET":
			try:
				NewSet = float(Msg[1])
				# Only interpret new setpoints if the change is >50mK
				if abs(self.SetTemp[Tindex]-NewSet) > 0.05:
					if self.SweepMode:
						# We are sweeping so kill the sweep
						print "Killing sweep..."
						self.Visa.write("RAMP 1,0,0")
					self.UpdateSetTemp(NewSet)
					# Set at set to be false and write the new set point
					self.AtSet = False
					self.SweepMode = False
					self.WriteSetpoint()
					print "Got probe set point from socket %.2f\n" % self.SetTemp[Tindex]
			except:
				pass
		if Msg[0] == "SWP":
			print "Got temperature sweep"
			Tindex = 0
			try:
				self.SweepFinish = float(Msg[1])
				if abs(self.SweepFinish - self.SetTemp[Tindex]) > 0.05:
					print "SetTemp = %.3f\t " % self.SetTemp[Tindex]					
					self.SweepRate = abs(float(Msg[2]))					
					# Check if the sweep is up or down
					print "%.3f" % self.SweepFinish
					print "%.3f" % self.SetTemp[Tindex]
					if self.SweepFinish >= self.SetTemp[Tindex]:
						self.SweepDirection = 1.0
					else:
						self.SweepDirection = -1.0
					print "==============SweepDirection = %.3f\t " % self.SweepDirection
					# Put the LS340 into ramp mode
					repl = self.Visa.ask("RAMP?1")
					print "%s" % repl					
					self.Visa.write("RAMP 1,1,%.3f" % self.SweepRate)
					repl = self.Visa.ask("RAMP?1")
					print "%s" % repl
					self.AtSet = False
					self.SweepTimeLength = abs(self.SetTemp[Tindex] - self.SweepFinish)/self.SweepRate
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
		Tindex = 0
		Set = False
		# The stability measure is v crude
		Stable = False
		# 1 = Sweep
		ErrorFactor = abs(self.Temperature[Tindex] - self.SetTemp[Tindex])/self.Temperature[Tindex]
		DeltaTempFactor = abs(self.DeltaTemp[Tindex])/self.Temperature[Tindex]		
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
		Tindex = 0
		if dT > (self.SweepTimeLength + self.SweepMaxOverTime):
			# The sweep ran out of time, stop it
			SweepFinished = True
			print "Sweep over time... Finishing..."
		elif (self.Temperature[Tindex] - self.SweepFinish)*self.SweepDirection > 0.0:
			SweepFinished = True
			print "Final temperature reached... Finishing..."
		else:
			SweepFinished = False
		if SweepFinished:
			# The sweep is finished stop ramping and change the mode
			self.Visa.write("RAMP 1,0,0")
			# Write the setpoint to the current temperature
			self.UpdateSetTemp(self.Temperature[Tindex])
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

	while 1:		
		# Read the picowatt and calculate the temperature
		control.ReadTempHeater()
		control.UpdateAtSet()
		control.UpdateStatusMsg()
		
		#Push the readings to clients and read messages
		#Sensor B (VTI) temperature, Sample or Sensor A (Probe)  temperature, Loop 2 (VTI heater power), Loop 1 (Sample power)
		#For the sample power there are three scales low, middle and high power which are not shown in the data
		for j in control.Server.handlers:
			j.to_send = ",%.4f %.4f %.4f %.4f %d" % (control.Temperature[1], control.Temperature[0], control.HeaterCurrent[1], control.HeaterCurrent[0], control.StatusMsg)
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
	
		time.sleep(0.8)

	control.Visa.close()

