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
    # Heater
    # AToB (amps to tesla)
    # Lock - Lock the deamon from performing actions, typically if the heater has just been
    # switched
    # The target current either as part of a sweep or going to a fixed value
    # Mode: Sweep or Set (including set to zero)
    
    def __init__(self):
        # Connect visa to the magnet
        self.Visa = VisaSubs.InitializeGPIB("12")
        # Open the socket
        address = ('localhost',18861)
        self.Server = SocketUtils.SockServer(address)
        
        # Define some important parameters for the magnet
        self.Field = 0.0
       
    
    #!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    # COMMUNICATION PROGRAMS
    #!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    
    
    ############################################
    # Function to read the field in Tesla specifically
    ###########################################
    
    def MagnetReadField(self):
        		
		Answer=self.Visa.ask("RDGFIELD?")
        self.Field = Answer
        
        return
    
    ##########################################################
    # On start get parameters
    ##########################################################
    
    def MagnetOnStartUp(self):
        
		Field=self.MagnetReadField()
        print "Connected to magnet...Field is %.3f" % (Field)
        
        return
                pass
            
            return
    ##########################################################
    # Set the leads current, ignore the switch heater state, busy etc
    ##########################################################
    
    def SetSource(self,NewSet):
        
        if abs(NewSet) <= self.CurrentLimit:
            CSet = NewSet
        else:
            CSet = np.copysign(self.CurrentLimit,NewSet)
            
        self.MagnetSetNumeric("CSET",CSet)
        
        # If the heater is on set the rate
        
        if self.Heater:
            if self.Rate >= self.MaxRate:
                self.Rate = self.MaxRate
            self.MagnetSetNumeric("RCST", self.Rate)
            
        SetRate = self.MagnetReadNumeric("RCST")
        self.MagnetSetAction("RTOS")
        print "Ramping source to %.4f A at %.4f A/m\n" % (CSet,SetRate)
        return
	
    def QueryAtTarget(self):
    	if abs(self.TargetField) < 1.0:
	    if abs(self.Field-self.TargetField) < 0.004:
	        AtTarget = True
	    else:
		AtTarget = False
        else:
            if (abs((self.Field-self.TargetField)/self.TargetField) <= 0.0035):
                AtTarget = True
            else:
                AtTarget = False
        return AtTarget

    
    def UpdateReady(self):
        
        if self.QueryAtTarget() and (self.Heater == self.TargetHeater):
            # The system is at target and ready
            self.Ready = 1
        else:
            # Idle
            self.Ready = 0
            
        return

    # Interpret a message from the socket
    def ReadMsg(self,Msg):
        # There are two possible actionable calls to the daemon
        # 1. "SET" go to set point
        # 2. "SWP" sweep from the current field to a target
        Msg = Msg.split(" ")
        if Msg[0] == "SET":
            # Set message has form "SET TargetField TargetHeater"
            try:
                NewField = float(Msg[1])
		NewHeater = int(Msg[2])
                NewHeater = bool(NewHeater)
                if (NewField != self.TargetField) or (NewHeater != self.TargetHeater):
                    self.TargetField = NewField
                    self.TargetHeater = NewHeater
                    self.Rate = self.MaxRate
                    self.UpdateReady()
                    if not self.Ready:
                        print "Got new set point from socket %.2f T" % self.TargetField
            except:
                pass
            
        if Msg[0] == "SWP":
            # Message has form "SWP TargetField Rate TargetHeater"
            #print Msg
            try:
                NewField = float(Msg[1])
		NewHeater = int(Msg[3])
                NewHeater = bool(NewHeater)
                self.Rate = float(Msg[2])
                if (NewField != self.TargetField) or (NewHeater != self.TargetHeater):
                    self.TargetField = NewField
                    self.TargetHeater = NewHeater
                    self.UpdateReady()
                    if not self.Ready:
                        print "Got new sweep point from socket to %.2f T at %.2f A/min" % (self.TargetField,self.TargetRate)
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

        #print control.TargetField, control.TargetHeater, control.Ready, control.Lock

        # Push the reading to clients
        for j in control.Server.handlers:
            j.to_send = ",%.5f %d" % (control.Field, control.Ready)
            SocketMsg = j.received_data
            if SocketMsg and SocketMsg != "-":
                control.ReadMsg(SocketMsg)
        asyncore.loop(count=1,timeout=0.001)
                
        """ Now we should do stuff depending on the socket and what we 
        were doing before reading the socket
        :browse confirm saveas
        In order of precedence
        2. Go to the target field
        4. ... just chill out! """
        
        if not control.Lock and not control.Ready:
            """ The magnet is not locked and not ready
            We now try to go to the TargetField and
            set the TargetHeater """
            
            if not control.QueryAtTarget():
                # System is not at the target field
                if not control.Heater:
                    # The heater is not on
                    if control.MagnetCheckSwitchable():
                        # The switch heater can be switched ON --> so switch it ON
                        control.MagnetSetHeater(True) # this will set the lock so we need to get out of the loop without doing anything else
                    else:
                        # The switch heater is not on
                        Action = control.MagnetReadAction()
                        if Action != "RTOS":
                            # The source is not ramping --> Ramp it to the magnet current so it can be switched
                            control.SetSource(control.MagnetCurrent)
                else:
                    # The heater is on --> so go to the target
                    Action = control.MagnetReadAction()
		    SetCurrent = control.MagnetReadNumeric("CSET")
                    if Action != "RTOS" or abs(SetCurrent - control.TargetField * control.AToB) > 0.005:
                        # The source is not ramping --> Ramp it to the magnet current so it can be switched
                        TargetCurrent = control.TargetField * control.AToB
                        control.SetSource(TargetCurrent)
            
            elif control.Heater != control.TargetHeater:
                """ The magnet is at the target field but the heater is not in the target state
                There are two possibilities
                1. The heater is now ON --> turn it off and ramp the source down
                2. The heater is OFF --> Set the source to magnet current and turn it on """
                if control.Heater:
                    # The heater is on
                    if control.MagnetCheckSwitchable():
                        control.MagnetSetHeater(False)
                        # Set the source flag to tell the source to ramp to zero
                        SourceFlag = True

                else:
                    # The heater is not on
                    if control.MagnetCheckSwitchable():
                        # The switch heater can be switched ON --> so switch it ON
                        control.MagnetSetHeater(True) # this will set the lock so we need to get out of the loop without doing anything else
                    else:
                        # The switch heater is not on
                        Action = control.MagnetReadAction()
                        if Action != "RTOS":
                            # The source is not ramping --> Ramp it to the magnet current so it can be switched
                            control.SetSource(control.MagnetCurrent)

        if not control.Lock and SourceFlag:
            # The SourceFlag has been set ramp the source to zero and unset the flag
            control.MagnetSetAction("RTOZ")
            SourceFlag = False
            
        time.sleep(0.4)
