#!/usr/bin/python
# -*- coding: utf-8 -*-

"""

Sub programs for operation of the PicoWatt and Leiden TCS to control temperature

author : Eoin O'Farrell
email : phyoec@nus.edu.sg
last edited : August 2013


	The daemon listens for commands to change the control loop or set_point
	The daemon broadcasts the current temperature
"""
import asyncore
import logging
import visa as visa
import string as string
import re as res
import time
from datetime import datetime

import numpy as np
import utils.pid_control as pid_control
import utils.socket_subs as socket_subs
import utils.visa_subs as visa_subs

logging.basicConfig(filename='temp.log', filemode='a', format='%(asctime)s,%(message)s', level=logging.DEBUG)

class TControl:

	# Initialization call, initialize LS340 visa and start the server
	# server always runs at 18871
	def __init__(self):
		self.visa = visa_subs.instrument("GPIB::12::INSTR")
		# start the server
		address = ('localhost',18871)
		self.server = socket_subs.SockServer(address)

		self.temperature = np.zeros((7,))
		# for the 9T there are 4 temperatures VTI, probe, 1st stage, He Pot
		# but we only set temperatures for VTI, probe and 4He pot
		# and there are only 2 loops...
		# It's a bit confusing so for the most part we ignore the 1st stage temp
		# We just push it to the terminal once every hour so that the user
		# can keep an eye on it.
		# For simplicity we define the temperature array to hold
		self.sensor_name = ["VTI", "Probe", "PTC Stage 1", "PTC Stage 2", "Magnet", "Switch", "He Pot"]
		self.sensor_location = ["A", "B", "C1", "C2", "C3", "C4", "D"]
		# there are 3 set temps
		self.set_temp = np.zeros((3,))
		self.status = -1
		# but there are only 2 loops :(
		self.loop_number = [1,2]
		self.zone_control = [False, False]
		self.loop_enable = [False, False]
		self.pid_vals = np.empty((3,3))

		# For 9T there are 3 heater outputs main heater = VTI, Analog 1 = 4He Pot
		# Analog 2 = Probe
		# so we have the commands to read the heaters
		self.heater_command = ["HTR?", "AOUT? 2", "AOUT? 1"]
		self.heater_current = np.zeros((3,))
		self.delta_temp = np.zeros((4,))
		self.max_set_temp = np.array([300.0,310.0,10.0])

		# The acceptable error in temperature as a factor of the
		# set temperature e.g. 2.0 K x 0.005 = 0.01 K
		self.error_temp = 0.005
		# The acceptable stability as a factor of the error
		self.error_delta_temp = 0.001
		# We maintain the VTI slightly below the probe
		self.delta_probe = 2.0

		# Sweep description, temperature denotes probe temperatures
		self.sweep_finish = 0.0
		self.sweep_rate = 0. # rate in K/min
		self.sweep_time = 0. # in seconds
		self.sweep_direction = 1.0
		self.sweep_start_time = []
		self.sweep_time_length = 0.0
		self.sweep_max_over_time = 15.0 # minutes

		# Status Parameters
		# Modes are 0: set, 1: sweep
		self.at_set = False
		self.sweep_mode = False
		self.status_msg = 0

		# Status events, every so often we push a status to the terminal
		self.status_interval = 1 # minutes
		self.last_status_time = datetime.now()

		# Turn off ramp mode
		self.visa.write("RAMP 1,0,0")
		#self.visa.write("RAMP 2,1,1.0")
		self.visa.write("RAMP 2,0.0,0.0")

		return

	# The ls340 often formats replies X,Y,Z -> return selection of values
	def ls_340_ask_multi(self,Query,Return):
		reply = self.visa.ask(Query)
		reply = reply.split(",")
		answer = list()
		for i in Return:
			answer.append(reply[i])

		return answer

	# Get the loop paramters: enabled, control mode, PID, set_points
	def get_loop_params(self):

		for i,v in enumerate(self.loop_number):
			# enabled?
			reply = self.ls_340_ask_multi(" ".join(("CSET?","%d" % v)),[2])
			self.loop_enable[i] = bool(int(reply[0]))
			# Control mode
			reply = self.visa.ask(" ".join(("CMODE?","%d" % v)))
			if reply == "2":
				self.zone_control[i] = True
			else:
				self.zone_control[i] = False
			# PIDs
			reply = self.ls_340_ask_multi(" ".join(("PID?","%d" % v)),[0,1,2])
			for j,u in enumerate(reply):
				self.pid_vals[j,i] = float(u)
			# set_points
			reply = self.visa.ask(" ".join(("SETP?","%d" % (i+1))))
			self.set_temp[i] = float(reply)

		return


	def read_temp_heater(self):
		# read the temperature and heater outputs
		old_temp = self.temperature
		for i,v in enumerate(self.sensor_location):
			# temperature
			reply = self.visa.ask(" ".join(("KRDG?","%s" % v)))
			try:
				self.temperature[i] = float(reply)
			except ValueError:
				self.temperature[i] = old_temp[i]
		self.delta_temp = self.temperature - old_temp

		# read the heaters
		for i,v in enumerate(self.heater_command):
			htr_reply = self.visa.ask(v)
			try:
				self.heater_current[i] = float(htr_reply)
			except ValueError:
				self.heater_current[i] = 0.0

		return

	# write set points to the instrument for the probe
	def update_set_temp(self,set_temp):

		set_temp = [set_temp - self.delta_probe, set_temp]
		for i,v in enumerate(set_temp):
			if (v < self.max_set_temp[i]) and (v >= 0.0):
				self.set_temp[i] = v
			elif (v < 0.0):
				self.set_temp[i] = 0.0
			else:
				self.set_temp[i] = self.max_set_temp[i]

		return


	def write_set_point(self):

		for i,v in enumerate(self.loop_number):
			self.visa.write("".join(("SETP ","%d," % v, "%.3f" % self.set_temp[i])))

		return

	# Update the parameter at_set for the probe
	def update_at_set(self):
		set = False
		# The stability measure is v crude
		stable = False
		# 1 = Sweep
		error_factor = abs(self.temperature[1] - self.set_temp[1])/self.temperature[1]
		delta_temp_factor = abs(self.delta_temp[1])/self.temperature[1]
		if error_factor < self.error_temp:
			set = True
		if delta_temp_factor < self.error_delta_temp:
			stable = True
		self.at_set = set and stable
		return

	# Interpret a message from the socket, current possible messages are
	# SET ...  -  set probe the temperature
	# SWP ...  -  sweep the probe temperature
	def read_msg(self,msg):
		msg = msg.split(" ")

		if msg[0] == "SET":
			try:
				new_set = float(msg[1])
				# Only interpret new set_points if the change is >50mK
				if abs(self.set_temp[1]-new_set) > 0.05:
					if self.sweep_mode:
						# We are sweeping so kill the sweep
						print("Killing sweep...")
						self.visa.write("RAMP 1,0,0")
						self.visa.write("RAMP 2,1,3.0")
					self.update_set_temp(new_set)
					# Set at set to be false and write the new set point
					self.at_set = False
					self.sweep_mode = False
					self.write_set_point()
					print("Got probe set point from socket %.2f\n" % self.set_temp[1])
			except:
				pass

		if msg[0] == "SWP":
			try:
				self.sweep_finish = float(msg[1])
				if abs(self.sweep_finish - self.set_temp[1]) > 0.05:
					self.sweep_rate = abs(float(msg[2]))
					self.sweep_max_over_time = abs(float(msg[3]))
					# Check if the sweep is up or down
					if self.sweep_finish >= self.set_temp[1]:
						self.sweep_direction = 1.0
					else:
						self.sweep_direction = -1.0
					# Put the LS340 into ramp mode
					self.visa.write("RAMP 1,1,%.3f" % self.sweep_rate)
					self.visa.write("RAMP 2,1,%.3f" % self.sweep_rate)
					self.at_set = False
					self.sweep_time_length = abs(self.set_temp[1] - self.sweep_finish)/self.sweep_rate
					print("Got temperature sweep to %.2f K at %.2f K/min... Sweep takes %.2f minutes, maximum over time is %.2f"
						% (self.sweep_finish, self.sweep_rate, self.sweep_time_length, self.sweep_max_over_time))
					# Write the finish temp
					self.update_set_temp(self.sweep_finish)
					# Write the set_point to start the ramp
					self.write_set_point()
					self.sweep_mode = True
					self.sweep_start_time = datetime.now()
					print("Starting the sweep\n")
			except:
				pass

		if msg[0] == "T_ERROR":
			try:
				self.error_temp = float(msg[1])
			except:
				pass

		if msg[0] == "DT_ERROR":
			try:
				self.error_delta_temp = float(msg[1])
			except:
				pass

		return


	def sweep_control(self):

		# We are sweeping so check if the sweep is finished
		dt = datetime.now() - self.sweep_start_time
		dt = dt.seconds/60.0

		if dt > (self.sweep_time_length + self.sweep_max_over_time):
			# The sweep ran out of time, stop it
			sweep_finished = True
			print("Sweep over time... Finishing...")
		elif (self.temperature[1] - self.sweep_finish)*self.sweep_direction > 0.0:
			sweep_finished = True
			print("Final temperature reached... Finishing...")
		else:
			sweep_finished = False

		if sweep_finished:
			# The sweep is finished stop ramping and change the mode
			self.visa.write("RAMP 1,0,0")
			self.visa.write("RAMP 2,1,3.0")
			# Write the set_point to the current temperature
			self.update_set_temp(self.temperature[1])
			self.write_set_point()
			self.sweep_mode = False

		return



	def update_status_msg(self):
		# TDaemon status messages:
		# 0 = Not ready
		# 1 = Ready

		if self.at_set and not self.sweep_mode:
			status = 1 # Ready
		else:
			status = 0 # Not ready

		self.status_msg = status
		return

	def print_status(self):
		status_string = ""
		temp_string = ""
		for i,v in enumerate(self.temperature):
			status_string += "%s = %.3f K; " % (self.sensor_name[i],self.temperature[i])
			temp_string += "%.3f," % (self.temperature[i])

		status_string += "Status message = %d\n" % self.status_msg

		print(status_string)
		logging.debug(temp_string) # log temperature reading to 'temp.log'
		self.last_status_time = datetime.now()
		return


if __name__ == '__main__':

	# Initialize a PID controller for the 4He Pot
	# 7/9/2014 p=300 i=1 unstable
	# 20/10/2015 p=60 i=1
	pid = pid_control.PID(p=75.0,i=.5,d=0,derivator=0,integrator=0,integrator_max=500,integrator_min=-50)

	control = TControl()

	control.get_loop_params()
	control.read_temp_heater()
	control.print_status()

	control.set_temp[2] = 3.7 # Set temperature for the He Pot
	pid.set_point(control.set_temp[2])

	while 1:

		# Read the picowatt and calculate the temperature
		control.read_temp_heater()
		control.update_at_set()
		control.update_status_msg()

		# Push the readings to clients and read messages
		for j in control.server.handlers:
			j.to_send = ",%.4f %.4f %.4f %.4f %d" % (control.temperature[0], control.temperature[1], control.heater_current[0], control.heater_current[1], control.status_msg)
			socket_msg = j.received_data
			if socket_msg:
				control.read_msg(socket_msg)
		asyncore.loop(count=1,timeout=0.001)


		# if we are sweeping we do some things specific to the sweep
		if control.sweep_mode:
			control.sweep_control()

		# check if we should send an update
		update_time = datetime.now() - control.last_status_time
		if update_time.seconds/60.0 >= control.status_interval:
			control.print_status()
		#	print "%.3f, %.3f" % (pid.P_value,pid.I_value)

		# Now we do some PID stuff in software to control the He Pot
		new_pid = pid.update(control.temperature[2])

		if new_pid > 120.0:
			new_pid = 120.0
		elif new_pid < 0.0:
			new_pid = 0.0
		control.visa.write("".join(("ANALOG 1,0,2,,,,,%.2f" % new_pid)))

		time.sleep(0.4)
