#!/usr/bin/python
# -*- coding: utf-8 -*-

"""

Sub programs for operation of Oxford Mercury iPS

author : Eoin O'Farrell
email : phyoec@nus.edu.sg
last edited :  Feb 2014


	The daemon listens for commands to change the field etc
	The daemon broadcasts the Field and a status message
	The daemon is assigned to port 18861
	The status messages are as follows:
	0 = Not ready
    1 = Ready

    The definition of ready is that the magnet daemon has completed the most recent task from the socket and can accept new tasks.

    The daemon always processes the most recent task from the socket, i.e., a new task overwrites previous tasks.
"""

import SocketUtils as SocketUtils
import logging
import visa as visa
import VisaSubs as VisaSubs
import string as string
import re as re
import time
import numpy as np
import asyncore
from datetime import datetime

class MControl():

	# Initialization call, initialize visas for the Mercury IPS and perform some startup
	# queries on the instrument
	# Server, server always runs at 18861
	# Important parameters
	# Field
	# The target current either as part of a sweep or going to a fixed value
	# Mode: Sweep or Set (including set to zero)
	
	def __init__(self):
		# Connect visa to the magnet
		self.Visa = visa.instrument("GPIB::12::INSTR")
		address = ('localhost', 18861)
		self.Server = SocketUtils.SockServer(address)
		#Gauss units
		self.Visa.write("UNIT 1")

		# Define some important parameters for the magnet
		self.Field = 0.0

		# The magnet actions are defined by the following parameters.
		# The daemon tries to reach the target field and then put the heater into the target state
		self.TargetField = 0.0
		self.SweepNow = False
		self.Ready = 1 # Ready message which is also broadcast to the listener
		self.StatusMsg = 0
		self.StatusInterval = 0.1 # minutes
		self.LastStatusTime = datetime.now()
		return
    
    #!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    # COMMUNICATION PROGRAMS
    #!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
      
    ############################################
    # Function to read the field in Gauss specifically
    ###########################################
	
	def MagnetReadField(self):
		Query = "RDGFIELD?"
		Reply = self.Visa.ask(Query)
		Answer = float(Reply)
		self.Field = Answer
		return
   
    
    ##########################################################
    # On start get parameters
    ##########################################################

	def MagnetOnStartUp(self):
		# Take care of the field sourcecurrent and magnetcurrent
		self.MagnetReadField()
		self.TargetField = self.Field
		print "Connected to magnet... Field is %.3f" % ( self.Field)
		return

	def QueryAtTarget(self):
		if abs(self.TargetField) < 1.0:
			if abs(self.Field - self.TargetField) < 0.004:
				AtTarget = True
			else:
				AtTarget = False
		else:
			if (abs((self.Field - self.TargetField)/self.TargetField) <= 0.0035):
				AtTarget = True
			else:
				AtTarget = False
		return AtTarget

	def WriteSetpoint(self):
		self.Visa.write("".join(("CSETP ","%.3f" % self.TargetField)))
		return
		
	def UpdateReady(self):        
		if self.QueryAtTarget():
			# The system is at target and ready
			self.Ready = 1
		else:
			# Idle
			self.Ready = 0   
		self.StatusMsg = self.Ready		
		return

	def PrintStatus(self):
		StatusString = ""
		StatusString += "%.3f G; " % self.Field

		StatusString += "Status message = %d\n" % self.StatusMsg
		print StatusString
		self.LastStatusTime = datetime.now()
		return
		
	# Interpret a message from the socket
	def ReadMsg(self,Msg):
		# There are two possible actionable calls to the daemon
		# 1. "SET" go to set point
		# 2. "SWP" sweep from the current field to a target
		Msg = Msg.split(" ")
		if Msg[0] == "SET":
			# Set message has form "SET TargetField"
			try:
				if (NewField != self.TargetField):
					self.TargetField = NewField
					#self.Rate = self.MaxRate
					self.UpdateReady()
					self.WriteSetpoint()
					if not self.Ready:
						print "Got new set point from socket %.2f G" % self.TargetField
			except:
				pass

		if Msg[0] == "SWP":
			# Message has form "SWP TargetField Rate"
			#print Msg
			try:
				NewField = float(Msg[1])
				self.Rate = float(Msg[2])
				if (NewField != self.TargetField):
					self.TargetField = NewField
					self.WriteSetpoint()
					self.UpdateReady()
					if not self.Ready:
						print "Got new sweep point from socket to %.2f G" % (self.TargetField)
			except:
				pass            
		return
        
if __name__ == '__main__':

	# Initialize a daemon instance and runs startup codes
	control = MControl()
	control.MagnetOnStartUp()
	# A flag to control the source behavior
	SourceFlag = False
    
	while 1:

		# Read the field and update the ready message
		control.MagnetReadField()
		StatusMsg = control.UpdateReady()
		
		print "Field %.5f G, Ready = %d" % (control.Field, control.Ready)
		# Push the reading to clients
		for j in control.Server.handlers:
			j.to_send = ",%.5f %d" % (control.Field, control.Ready)
			SocketMsg = j.received_data
			if SocketMsg:
				control.ReadMsg(SocketMsg)
		asyncore.loop(count=1,timeout=0.001)
	
		UpdateTime = datetime.now() - control.LastStatusTime
		if UpdateTime.seconds/60.0 >= control.StatusInterval:
			control.PrintStatus()
			
		time.sleep(0.8)
