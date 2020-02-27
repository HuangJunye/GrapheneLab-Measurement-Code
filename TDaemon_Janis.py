#!/usr/bin/python
# -*- coding: utf-8 -*-

"""

Sub programs for operation of the PicoWatt and Leiden TCS to control temperature

original author : Eoin O'Farrell
current author : Huang Junye
last edited : Apr 2019


	The daemon listens for commands to change the control loop or setpoint
	The daemon broadcasts the current temperature

	!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
	temperature units are Kelvin
	!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

ToDo:
	Listen
	Broadcast
	Initialize
	ReadPico
	CalcPID
	setTCS

"""
import asyncore
import logging
import visa as visa
import string as string
import re as res
import time
from scipy import interpolate
from datetime import datetime

import numpy as np
import utils.pid_control as pid_control
import utils.socket_subs as socket_subs
import utils.visa_subs as visa_subs

class TControl():

	# Initialization call, initialize LS340 visa and start the server
	# server always runs at 18871
	def __init__(self):
		self.visa = visa_subs.initialize_gpib(address=27, board=0)
		# start the server
		address = ('localhost', 18871)
		self.server = socket_subs.SockServer(address)
		self.temperature = np.zeros((2,))
		self.sensor_name = ["Probe", "VTI"]
		self.sensor_location = ["A","B"]
		self.set_temp = np.zeros((2,))
		self.status = -1
		self.loop_number = [1,2]
		self.zone_control = [False, False]
		self.loop_enable = [False, False]
		self.pid_vals = np.empty((3,3))
		self.heater_command = ["HTR?"]
		self.heater_current = np.zeros((3,))
		self.delta_temp = np.zeros((2,))
		self.max_set_temp = np.array([400.0,400.0,400.0])

		# The acceptable error in temperature as a factor of the
		# set temperature e.g. 2.0 K x 0.005 = 0.01 K
		self.error_temp = 0.001
		# The acceptable stability as a factor of the error
		self.error_delta_temp = 0.001
		# We maintain the VTI slightly below the probe
		self.delta_probe = 0.0
		# Sweep description, temperature denotes probe temperatures
		self.sweep_finish = 0.0
		self.sweep_rate = 0. # rate in K/min
		self.sweep_time = 0. # in seconds
		self.sweep_direction = 1.0
		self.sweep_start_time = []
		self.sweep_time_length = 0.0
		self.sweep_max_over_time = 60.0 # minutes
		# status Parameters
		# Modes are 0: set, 1: sweep
		self.at_set = False
		self.sweep_mode = False
		self.status_msg = 0
		# status events, every so often we push a status to the terminal
		self.status_interval = 0.1 # minutes
		self.last_status_time = datetime.now()
		# Turn off ramp mode
		self.visa.write("RAMP 1,0,0")
		return

	# The ls340 often formats replies X,Y,Z -> return selection of values
	def ls_340_query_multi(self,Query,Return):
		reply = self.visa.query(Query)
		reply = reply.split(",")
		answer = list()
		for i in Return:
			answer.append(reply[i])
		return answer

	# Get the loop paramters: enabled, control mode, PID, setpoints
	def get_loop_params(self):
		for i,v in enumerate(self.loop_number):
			# enabled?
			reply = self.ls_340_query_multi(" ".join(("Cset?","%d" % v)),[2])
			self.loop_enable[i] = bool(int(reply[0]))
			# Control mode
			reply = self.visa.query(" ".join(("CMODE?","%d" % v)))
			if reply == "2":
				self.zone_control[i] = True
			else:
				self.zone_control[i] = False
			# PIDs
			reply = self.ls_340_query_multi(" ".join(("PID?","%d" % v)),[0,1,2])
			for j,u in enumerate(reply):
				self.pid_vals[j,i] = float(u)
			# setpoints
			reply = self.visa.query(" ".join(("setP?","%d" % (i+1))))
			self.set_temp[i] = float(reply)
		return

	def read_temp_heater(self):
		# read the temperature and heater outputs
		old_temp = self.temperature
		for i,v in enumerate(self.sensor_location):
			# temperature
			reply = self.visa.query(" ".join(("KRDG?","%s" % v)))
			self.temperature[i] = float(reply)
		self.delta_temp = self.temperature - old_temp
		# read the heaters
		for i,v in enumerate(self.heater_command):
			reply = self.visa.query(v)
			self.heater_current[i] = float(reply)
		return

	# write set points to the instrument for the probe
	def update_temp(self,set_temp):
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
			self.visa.write("".join(("setP ","%d," % v, "%.3f" % self.set_temp[i])))
		return

	# Interpret a message from the socket, current possible messages are
	# set ...  -  set probe the temperature
	# SWP ...  -  sweep the probe temperature
	def read_msg(self,msg):
		tindex = 0
		msg = msg.decode().split(" ")
		if msg[0] == "SET":
			try:
				new_set = float(msg[1])
				# Only interpret new setpoints if the change is >50mK
				if abs(self.set_temp[tindex]-new_set) > 0.05:
					if self.sweep_mode:
						# We are sweeping so kill the sweep
						print("Killing sweep...")
						self.visa.write("RAMP 1,0,0")
					self.update_temp(new_set)
					# set at set to be false and write the new set point
					self.at_set = False
					self.sweep_mode = False
					self.write_set_point()
					print("Got probe set point from socket %.2f\n" % self.set_temp[tindex])
			except:
				pass
		if msg[0] == "SWP":
			print("Got temperature sweep")
			tindex = 0
			try:
				self.sweep_finish = float(msg[1])
				if abs(self.sweep_finish - self.set_temp[tindex]) > 0.05:
					print("set_temp = %.3f\t " % self.set_temp[tindex])
					self.sweep_rate = abs(float(msg[2]))
					# Check if the sweep is up or down
					print("%.3f" % self.sweep_finish)
					print("%.3f" % self.set_temp[tindex])
					if self.sweep_finish >= self.set_temp[tindex]:
						self.sweep_direction = 1.0
					else:
						self.sweep_direction = -1.0
					print("==============sweep_direction = %.3f\t " % self.sweep_direction)
					# Put the LS340 into ramp mode
					repl = self.visa.query("RAMP?1")
					print("%s" % repl)
					self.visa.write("RAMP 1,1,%.3f" % self.sweep_rate)
					repl = self.visa.query("RAMP?1")
					print("%s" % repl)

					#update all ZONE parameters using a new ramp rate
					zone_msg = "".join("ZONE 1,1,+07.000,+0050.0,+0040.0,+000.0,+000.00,1,0,+00%s" % self.sweep_rate)
					self.visa.write(zone_msg)
					zone_msg = "".join("ZONE 1,2,+20.000,+0050.0,+0040.0,+000.0,+000.00,2,0,+00%s" % self.sweep_rate)
					self.visa.write(zone_msg)
					zone_msg = "".join("ZONE 1,3,+310.00,+0050.0,+0020.0,+000.0,+000.00,3,0,+00%s" % self.sweep_rate)
					self.visa.write(zone_msg)
					zone_msg = "".join("ZONE 1,4,+410.00,+0050.0,+0020.0,+000.0,+000.00,3,0,+00%s" % self.sweep_rate)
					self.visa.write(zone_msg)

					self.at_set = False
					self.sweep_time_length = abs(self.set_temp[tindex] - self.sweep_finish)/self.sweep_rate
					print("Got temperature sweep to %.2f K at %.2f K/min... Sweep takes %.2f minutes, maximum over time is %.2f" % (self.sweep_finish, self.sweep_rate, self.sweep_time_length, self.sweep_max_over_time))
					# Write the finish temp
					self.update_temp(self.sweep_finish)
					# Write the setpoint to start the ramp
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
		if msg[0] == "dt_ERROR":
			try:
				self.error_delta_temp = float(msg[1])
			except:
				pass
		return

	# Update the parameter at_set for the probe
	def update_at_set(self):
		tindex = 0
		set = False
		# The stability measure is v crude
		stable = False
		# 1 = Sweep
		error_Factor = abs(self.temperature[tindex] - self.set_temp[tindex])/self.temperature[tindex]
		delta_temp_factor = abs(self.delta_temp[tindex])/self.temperature[tindex]
		if error_Factor < self.error_temp:
			set = True
		if delta_temp_factor < self.error_delta_temp:
			stable = True
		self.at_set = set and stable
		return

	def sweep_control(self):
		# We are sweeping so check if the sweep is finished
		dt = datetime.now() - self.sweep_start_time
		dt = dt.seconds/60.0
		tindex = 0
		if dt > (self.sweep_time_length + self.sweep_max_over_time):
			# The sweep ran out of time, stop it
			sweep_finished = True
			print("Sweep over time... Finishing...")
		elif (self.temperature[tindex] - self.sweep_finish)*self.sweep_direction > 0.0:
			sweep_finished = True
			print("Final temperature reached... Finishing...")
		else:
			sweep_finished = False
		if sweep_finished:
			# The sweep is finished stop ramping and change the mode
			self.visa.write("RAMP 1,0,0")
			# Write the setpoint to the current temperature
			self.update_temp(self.temperature[tindex])
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
		for i,v in enumerate(self.temperature):
			status_string += "%s = %.3f K; " % (self.sensor_name[i],self.temperature[i])

		status_string += "status message = %d\n" % self.status_msg
		print(status_string)
		self.last_status_time = datetime.now()
		return


if __name__ == '__main__':

	# Initialize a PID controller for the 4He Pot
	pid = pid_control.PID(p=500,i=3,d=0,derivator=0,integrator=0,integrator_max=250,integrator_min=-50)

	control = TControl()

	control.get_loop_params()
	control.read_temp_heater()
	control.print_status()

	while 1:
		# Read the picowatt and calculate the temperature
		control.read_temp_heater()
		control.update_at_set()
		control.update_status_msg()

		#Push the readings to clients and read messages
		#Sensor B (VTI) temperature, Sample or Sensor A (Probe)  temperature, Loop 2 (VTI heater power), Loop 1 (Sample power)
		#For the sample power there are three scales low, middle and high power which are not shown in the data
		for j in control.server.handlers:
			j.to_send = ",%.4f %.4f %.4f %.4f %d" % (control.temperature[1], control.temperature[0], control.heater_current[1], control.heater_current[0], control.status_msg)
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

		time.sleep(0.8)

	control.visa.close()
