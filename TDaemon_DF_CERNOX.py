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
import asyncore
import time
from collections import deque
from datetime import datetime

import numpy as np

import utils.pid_control as pid_control
import utils.socket_utils as socket_utils
import utils.visa_subs as visa_subs


class TControl:

	""" Initialization call, initialize visas for the TCS, Picowatt and the
	Server, server always runs at 18871
	"""

	def __init__(self):

		self.pico_visa = visa_subs.initialize_gpib(20, 0, query_delay="0.04")
		self.pico_visa.write("HDR0")
		self.pico_visa.write("ARN 1")
		self.pico_visa.write("REM 1")
		self.tcs_visa = visa_subs.initialize_serial("ASRL6::INSTR", idn="ID?")

		address = ('localhost', 18871)
		self.server = socket_utils.SockServer(address)

		self.resistance = 1.0
		self.temperature = 0.0
		self.delta_temp = 1.0

		self.pico_channel = 0
		self.pico_range = 0

		self.set_temp = -1.0

		self.tcs_heater = [0, 0, 0]
		self.tcs_range = [1, 1, 1]
		self.tcs_current = [0, 0, 0]

		self.max_set_temp = 10000.0
		self.max_current = 35000

		# Acceptable temperature error as a factor e.g. 100 * 0.005 = 0.5mK
		self.error_temp = 0.01  # The acceptable error in temperature
		self.error_delta_temp = 0.005  # The acceptable stability

		# Sweep description
		self.sweep_finish = 0.0
		self.sweep_start = 0.0
		self.sweep_rate = 1.0  # As received from socket in mK/min
		self.sweep_rate_sec = 1.0/60.0
		self.sweep_time = 0.0  # seconds
		self.sweep_direction = 1.0
		self.sweep_start_time = 0.0
		self.sweep_time_length = 0.0
		self.sweep_max_over_time = 15.0  # minutes

		# Status parameters
		self.at_set = False
		self.sweep_mode = False
		self.status_msg = 0  # not ready
		self.temp_history = deque(np.zeros((60,)))

		# Status events
		self.status_interval = 1.0
		self.last_status_time = datetime.now()
		self.sensor = "CERNOX"

		# Initialize a pid controller
		self.pid = pid_control.PID(
			P=20., I=.5, D=0, Derivator=0, Integrator=0,
			Integrator_max=60000, Integrator_min=-2000)

		return

	def set_tcs(self, source, current):
		if current < 0:
			current = 0
		elif current > self.max_current:
			current = self.max_current
		# current in microAmp
		# print current
		source = source + 1
		command = " ".join(("SETDAC", "%d" % source, "0", "%d" % current))

		self.tcs_visa.query(command)
		return

	def read_pico(self):
		# Get the resistance of the current channel of the picowatt
		self.pico_visa.write("ADC")
		time.sleep(0.45)
		answer = self.pico_visa.query("RES?")
		answer = answer.strip()
		try:
			self.resistance = float(answer)
		except:
			self.resistance = self.resistance
			pass
		return

	def read_pico_range(self):
		answer = self.pico_visa.query("RAN?")
		answer = answer.strip()
		self.pico_range = int(answer)
		return

	def set_pico_channel(self, channel):
		self.pico_visa.write("INP 0")
		command = "".join(("MUX ", "%d" % channel))
		self.pico_visa.write(command)
		time.sleep(3)
		self.pico_visa.write("INP 1")
		time.sleep(10)
		self.pico_channel = channel
		return

	def read_tcs(self):
		answer = self.tcs_visa.query("STATUS?")
		reply = answer.split("\t")[1]
		reply = reply.split(",")
		sensor_range = reply[1::4]
		current = reply[2::4]
		heaters = reply[3::4]
		tmp = [1,10,100,1000]
		for i in range(3):
			self.tcs_heater[i] = int(heaters[i])
		for i in range(3):
			self.tcs_current[i] = int(current[i])*tmp[int(sensor_range[i])-1]
		return

	def calc_temperature(self, calibration, factor=0.0):
		log_resistance = np.log10(self.resistance)-factor
		r_poly = np.ones((len(calibration),))
		old_temperature = self.temperature
		for i in range(1,len(r_poly)):
			r_poly[i] = log_resistance * r_poly[i-1]
		self.temperature = np.power(10,(np.sum(np.multiply(r_poly,calibration))))
		self.delta_temp = self.temperature - old_temperature

		self.temp_history.pop()
		self.temp_history.appendleft(self.temperature)
		return

	# Update the parameter at_set for the probe
	def update_at_set(self):
		is_set = False
		# The stability measure is v crude
		is_stable = False
		# 1 = Sweep
		error_factor = abs(self.temperature - self.set_temp)/self.temperature
		delta_temp_factor = abs(np.std(self.temp_history))/self.temperature
		if error_factor < self.error_temp:
			is_set = True
		if delta_temp_factor < self.error_delta_temp:
			is_stable = True
		self.at_set = is_set and is_stable
		return

	# Interpret a message from the socket, current possible messages are
	# SET ...  -  set probe the temperature
	# SWP ...  -  sweep the probe temperature
	def read_msg(self, msg):
		msg = msg.split(" ")

		if msg[0] == "SET":
			try:
				new_set_temperature = float(msg[1])
				# Only interpret new setpoints if the change is >50mK
				if abs(self.set_temp-new_set_temperature) > 0.05:
					self.set_temp = new_set_temperature
					if self.pico_channel == 5:
						pass
					#elif self.set_temp > 800:
					#	self.pid.setKp(20.)
					#else:
					#	self.pid.setKp(10.)
					self.pid.initialize_set_point(self.set_temp)
					# Set at set to be false and write the new set point
					self.at_set = False
					self.sweep_mode = False
					print("Got probe set point from socket %.2f\n" % self.set_temp)
			except:
				pass

		if msg[0] == "SWP":
			try:
				self.sweep_finish = float(msg[1])
				if abs(self.sweep_finish - self.set_temp) > 0.05:
					self.sweep_start = self.set_temp
					self.pid.initialize_set_point(self.set_temp)
					self.sweep_rate = abs(float(msg[2]))
					self.sweep_rate_sec = self.sweep_rate/60.0
					self.sweep_max_over_time = abs(float(msg[3]))
					# Check if the sweep is up or down
					if self.sweep_finish >= self.set_temp:
						self.sweep_direction = 1.0
					else:
						self.sweep_direction = -1.0
					# Put the LS340 into ramp mode
					self.at_set = False
					self.sweep_time_length = abs(self.set_temp - self.sweep_finish)/self.sweep_rate
					print("Got temperature sweep to %.2f K at %.2f K/min... Sweep takes %.2f minutes, maximum over time is %.2f" % (self.sweep_finish, self.sweep_rate, self.sweep_time_length, self.sweep_max_over_time))
					# Write the finish temp
					# Write the setpoint to start the ramp
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
		d_temp_in_seconds = datetime.now() - self.sweep_start_time
		d_temp_in_minutes = d_temp_in_seconds.seconds/60.0

		if d_temp_in_minutes > (self.sweep_time_length + self.sweep_max_over_time):
			# The sweep ran out of time, stop it
			sweep_finished = True
			print("Sweep over time... Finishing...")
		elif (self.temperature - self.sweep_finish)*self.sweep_direction > 0.0:
			sweep_finished = True
			print("Final temperature reached... Finishing...")
		else:
			sweep_finished = False

		if sweep_finished:
			self.sweep_mode = False
		else:
			old_set_temperature = self.set_temp
			self.set_temp = self.sweep_start + self.sweep_rate_sec * d_temp_in_seconds.seconds * self.sweep_direction

			if self.pico_channel == 5:
				pass
			#elif (old_set_temperature < 800.) and (self.set_temp > 800.):
			#	self.pid.setKp(20.)
			#elif (old_set_temperature > 800.) and (self.set_temp < 800.):
			#	self.pid.setKp(10.)
			self.pid.initialize_set_point(self.set_temp, reset=False)

		return

	def update_status_msg(self):
		# TDaemon status messages:
		# 0 = Not ready
		# 1 = Ready

		if self.at_set and not self.sweep_mode:
			status = 1  # Ready
		else:
			status = 0  # Not ready

		self.status_msg = status
		return

	def print_status(self):
		status_string = "%s = %.2f K; PID output = %d; " % (self.sensor, self.temperature, self.pid_output)
		status_string += "Status message = %d; " % self.status_msg
		status_string += "P = %.2f, I = %.2f, D = %.2f\n" % (self.pid.P_value, self.pid.I_value, self.pid.D_value)
		print(status_string)
		self.last_status_time = datetime.now()
		return

	def tcs_switch_heater(self, heater):
		command_vector = np.zeros((12,))
		command_vector[2+heater*4] = 1
		command_string = "SETUP "
		print("Heater %d Switched %d" % (heater, int(not self.tcs_heater[heater])))
		for i in command_vector:
			command_string = "".join((command_string, "%d," % i))
		command_string = command_string[:-1]
		reply = self.tcs_visa.query(command_string)
		return


##################### calibrations
calibrations={"SO703":[7318.782092,-13274.53584,10276.68481,
	-4398.202411,1123.561007,-171.3095557,14.43456504,-0.518534965],
		"SO914":[5795.148097375,-11068.032226486,9072.821104899,
			-4133.466851312,1129.955799406,-185.318021359,16.881907269,-0.658939155],
		"MATS56":[19.68045382,-20.19660902,10.13318296,-2.742724207,0.385556989,-0.022178276],
		"CERNOX":[4.62153,-1.17709,-0.222229,-2.3114e-11]}


if __name__ == '__main__':

	# Initialize a PID controller

	control = TControl()

	control.set_pico_channel(5) #ch5 for CERNOX. Do not use below 1K
	control.sensor = "CERNOX"

	# Main loop
	control.read_tcs()

	while True:

		# Read the picowatt and calculate the temperature
		control.read_pico()
		control.calc_temperature(calibrations[control.sensor])
		control.update_at_set()
		control.update_status_msg()

		# Push the reading to clients
		for j in control.server.handlers:
			j.to_send = ",%.3f %d" % (control.temperature, control.status_msg)
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

		new_pid = control.pid.update(control.temperature)
		try:
			control.pid_output = int(new_pid)
		except:
			control.pid_output = 0
			pass

		if control.pid_output < 0:
			control.pid_output = 0
		elif control.pid_output > control.max_current:
			control.pid_output = control.max_current

		if control.pid_output > 0 and control.tcs_heater[2] == 0:
			# status is go to set and heater is off --> turn it on
			control.set_tcs(2,control.pid_output)
			control.tcs_switch_heater(2)
			control.read_tcs()
		elif control.pid_output <= 0 and control.tcs_heater[2] == 1:
			# status is go to set and heater is off --> turn it on
			control.tcs_switch_heater(2)
			control.set_tcs(2,0)
			control.read_tcs()
		elif control.pid_output >= 0 and control.tcs_heater[2] == 1:
			control.set_tcs(2,control.pid_output)
			control.tcs_current[2] = control.pid_output

		time.sleep(0.5)

	control.tcs_visa.close()
