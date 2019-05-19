#!/usr/bin/python
# -*- coding: utf-8 -*-

import time

import numpy as np

import utils.visa_subs as visa_subs


class LockInAmplifier:
	""" Implement a generic lock-in amplifier class	"""

	def __init__(self, address):
		self.address = address
		self.visa = visa_subs.initialize_gpib(address, 0)
		# Other LIA properties
		self.source = "VOLT"
		self.name = "Lock in"
		self.excitation = []
		self.frequency = []
		self.harmonic = []
		self.internal_excitation = []
		self.sensitivity = []
		self.sensitivity_max = 1.
		self.phase = []
		self.tau = []
		self.expand = []
		self.offset = []
		self.data = [0.0, 0.0, 0.0, 0.0]
		self.data_column = 0
		self.output = True
		self.auto_range = False

	# Read one of the numeric parameters
	def read_numeric(self, command):
		reply = self.visa.query("".join((command, "?")))
		answer = float(reply)
		return answer

	# Read data (X, Y, R, phase)
	def read_data(self):
		reply = self.visa.query("SNAP?1,2,3,4")
		self.data = [float(i) for i in reply.split(",")]

		if self.auto_range:
			old_range = self.sensitivity
			if self.data[2] > .9 * self.sensitivity_max:
				self.sensitivity = self.sensitivity + 3
				if self.sensitivity > 26:
					self.sensitivity = 26
			elif self.data[2] < .01 * self.sensitivity_max:
				self.sensitivity = self.sensitivity - 3
				if self.sensitivity < 0:
					self.sensitivity = 0

			if self.sensitivity != old_range:
				self.visa.write("SENS %d" % self.sensitivity)
				self.calc_sens_max()

		pass

	# Initialization for the LIA consists of reading the measurement parameters
	def initialize(self, auto_range=False):
		self.excitation = self.read_numeric("SLVL")
		self.frequency = self.read_numeric("FREQ")
		self.harmonic = self.read_numeric("HARM")
		self.sensitivity = int(self.read_numeric("SENS"))
		self.phase = self.read_numeric("PHAS")
		self.tau = self.read_numeric("OFLT")
		self.internal_excitation = self.read_numeric("FMOD")
		self.expand = np.empty(2)
		self.offset = np.empty(2)
		self.read_offset()
		self.auto_range = auto_range
		self.column_names = "X (V), Y (V), R (V), phase (Deg)"
		self.calc_sens_max()
		pass

	def calc_sens_max(self):
		range_vec = [2., 5., 10.]
		lev = self.sensitivity/3 - 9
		self.sensitivity_max = range_vec[self.sensitivity % 3] * 10**lev
		pass

	def set_output(self, level):
		self.visa.write("SLVL %.3f" % level)
		pass

	def ramp(self, v_finish):
		v_start = self.read_numeric("SLVL")
		if abs(v_start-v_finish) > 0.002:
			n = abs((v_finish-v_start)/0.01)
			v_sweep = np.linspace(v_start, v_finish, num=np.ceil(n), endpoint=True)

			for i in range(len(v_sweep)):
				self.set_output(v_sweep[i])
				time.sleep(0.01)

			self.excitation = v_finish
		
		return

	# Read the offsets
	def read_offset(self, **kwargs):
		
		# set the offsets to zero
		if "auto" in list(kwargs.keys()):
			self.visa.write("OEXP 1,0,0")
			self.visa.write("OEXP 2,0,0")
			time.sleep(1)

			# auto set the offsets
			self.visa.write("AOFF 1")
			self.visa.write("AOFF 2")

		# Read the offsets
		for i in range(2):
			reply = self.visa.query("".join(("OEXP? ", "%d" % (i+1))))
			reply = reply.split(",")
			self.offset[i] = float(reply[0])
			self.expand[i] = float(reply[1])

		if "auto" in list(kwargs.keys()):
			self.visa.write("".join(("OEXP 1,", "%.2f," % self.offset[0], "%d" % kwargs["auto"])))
			self.visa.write("".join(("OEXP 2,", "%.2f," % self.offset[1], "%d" % kwargs["auto"])))
			self.expand[0] = kwargs["auto"]
			self.expand[1] = kwargs["auto"]

		pass

	# Print a description string 
	def description(self):
		description_string = "SR830"
		for item in list(vars(self).items()):
			if item[0] == "tau" or item[0] == "excitation" or item[0] == "frequency" \
					or item[0] == "harmonic" or item[0] == "address" or item[0] == "phase" \
					or item[0] == "sensitivity" or item[0] == "internal_excitation":

				description_string = ", ".join((description_string, "%s = %.3f" % item))

		description_string = "".join((description_string, "\n"))
		return description_string



