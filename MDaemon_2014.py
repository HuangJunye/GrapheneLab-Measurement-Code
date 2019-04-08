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
        self.Visa = VisaSubs.InitializeSerial("ASRL5", term_chars = "\\n")
        # Open the socket
        address = ('localhost',18861)
        self.Server = SocketUtils.SockServer(address)
        
        # Define some important parameters for the magnet
        self.Field = 0.0
        self.SourceCurrent = 0.0
        self.Heater = False
        self.MagnetCurrent = 0.0
        self.AToB = 0.0
        self.Rate = 2.19
        self.MaxRate = 2.19
        self.CurrentLimit = 0.0
        
        # Set up the lock for the switch heater
        self.Lock = False
        self.LockTime = 0.0
        
        # The magnet actions are defined by the following parameters.
        # The daemon tries to reach the target field and then put the heater into the target state
        self.TargetField = 0.0
        self.TargetHeater = False
        
        self.SweepNow = False
        self.Ready = 1 # Ready message which is also broadcast to the listener
        
        return
    
    #!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    # COMMUNICATION PROGRAMS
    #!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    
    ############################################
    # Function to read one of the numeric signals
    ###########################################
    
    def MagnetReadNumeric(self, Command):
        # Form the query string (Now only for GRPZ)
        Query = "".join(("READ:DEV:GRPZ:PSU:SIG:",Command))
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
    
    def MagnetReadField(self):
        
        # Form the query string (Now only for GRPZ)
        if self.Heater:
            Query = "READ:DEV:GRPZ:PSU:SIG:FLD"
        else:
            # For some reason the command PFLD doesn't work
            Query = "READ:DEV:GRPZ:PSU:SIG:PCUR"
        
        Reply = self.Visa.ask(Query)
        # Find the useful part of the response
        Answer = string.rsplit(Reply,":",1)[1]
        # Some regex to get rid of the appended units
        Answer = re.split("[a-zA-Z]",Answer,1)[0]
        Answer = float(Answer)
        if self.Heater:
            self.SourceCurrent = Answer * self.AToB
            self.MagnetCurrent = self.SourceCurrent
        else:
            self.MagnetCurrent = Answer
            Answer = Answer / self.AToB
            		
        self.Field = Answer
        
        return
    
    #########################################
    # Read one of the numeric configs
    ########################################
    
    def MagnetReadConfNumeric(self, Command):
        # Form the query string (Now only for GRPZ)
        Query = "".join(("READ:DEV:GRPZ:PSU:",Command))
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
        writeCmd = "SET:DEV:GRPZ:PSU:SIG:%s:%.4f" % (Command, Value)
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
            self.Heater = True
        elif Answer == "OFF":
            Valid = 0
            self.Heater = False
        else:
            Valid = -1
        
        return Valid
    
    ##################################################
    # Turn the switch heater ON (1) or OFF (0)
    ####################################################
    
    def MagnetSetHeater(self, State):
       
	self.MagnetSetAction("HOLD")
        HeaterBefore = self.Heater
        if State:
            Reply = self.Visa.ask("SET:DEV:GRPZ:PSU:SIG:SWHT:ON")
        else:
            Reply = self.Visa.ask("SET:DEV:GRPZ:PSU:SIG:SWHT:OFF")
            
        Answer = string.rsplit(Reply,":",1)[1]
        if Answer == "VALID":
            Valid = 1
        elif Answer == "INVALID":
            Valid = 0
        self.MagnetReadHeater()
        if self.Heater != HeaterBefore:
            print "Heater switched ... locking for 2 minutes..."
            self.Lock = True
            self.LockTime = datetime.now()
            
        return Valid
    
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
        
        self.MagnetReadHeater()
        self.SourceCurrent = self.MagnetReadNumeric("CURR")
        self.MagnetCurrent = self.MagnetReadNumeric("PCUR")
        
        if self.Heater:
            Switchable = True
        elif abs(self.SourceCurrent - self.MagnetCurrent) <= 0.1:
            Switchable = True
        elif self.Heater == 0 and abs(self.SourceCurrent - self.MagnetCurrent) >= 0.1:
            Switchable = False
            
        Action = self.MagnetReadAction()
        if Action == "RTOZ" or Action == "RTOS":
            Switchable = False
        
        return Switchable
    
    ##########################################################
    # On start get parameters
    ##########################################################
    
    def MagnetOnStartUp(self):
        
        # Check the heater
        self.MagnetReadHeater()
        self.AToB = self.MagnetReadConfNumeric("ATOB")
        # Take care of the field sourcecurrent and magnetcurrent
        self.MagnetReadField()
        self.CurrentLimit = self.MagnetReadConfNumeric("CLIM")
        self.TargetField = self.Field
	self.TargetHeater = self.Heater
        
        if self.Heater:
            HeaterString = "ON"
        else:
            HeaterString = "OFF"
        
        print "Connected to magnet... Heater is %s, Field is %.3f, Magnet conversion = %.3f A/T, Maximum current = %.3f" % (HeaterString, self.Field, self.AToB, self.CurrentLimit)
        
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
        1. We are locked, waiting for the switch heater -> delay any actions
        2. Go to the target field
        3. Go to the target heater
        4. ... just chill out! """
        
        if control.Lock:
            # Check if we can release the lock
            Wait = datetime.now() - control.LockTime
            if Wait.seconds >= 120.0:
                # Unlock
                control.Lock = False
                print "Unlocking..."



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
