import time

import numpy as np

from ..generic_instrument import Instrument


class LockInAmplifier(Instrument):
	""" Implement a generic lock-in amplifier class	"""

	def __init__(self, address):
		super().__init__(address)

		self.mode = "A-B"  # TODO: implement A, A-B, I modes

		self.excitation = 0
		self.frequency = 0
		self.harmonic = 0
		self.internal_excitation = 0
		self.sensitivity = 0
		self.sensitivity_max = 1.
		self.phase = 0
		self.tau = 0
		self.expand = 0
		self.offset = 0
		self.ramp_step = 0.01

		self.data = [0.0, 0.0, 0.0, 0.0]
		self.data_column = 0

		self.output = True
		self.auto_range = False

	def description(self):
		""" Print a description string to data file"""

		description_string = (
			f"{super().description()}, "
			f"excitation={self.excitation}, "
			f"frequency={self.frequency}, "
			f"harmonic={self.harmonic}, "
			f"sensitivity={self.sensitivity}, "
			f"phase={self.phase}"
			"\n"
		)
		return description_string

	def initialize(self, auto_range=False):
		"""Initialization for the LIA consists of reading the measurement parameters"""

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
		self.column_names = "X (V),Y (V),R (V),phase (Deg)"
		self.calc_sens_max()
		pass

	def read_numeric(self, command):
		""" Read one of the numeric parameters"""

		reply = self.visa.query("".join((command, "?")))
		answer = float(reply)
		return answer

	def read_data(self):
		""" Read data (X, Y, R, Phase) and implement auto range function"""

		reply = self.visa.query("SNAP?1,2,3,4")
		self.data = [float(i) for i in reply.split(",")]

		if self.auto_range:
			old_range = self.sensitivity
			if self.data[2] > .9 * self.sensitivity_max:
				self.sensitivity = self.sensitivity + 3
				if self.sensitivity > 26:  # 26 correspond to 1V, maximum sensitivity range
					self.sensitivity = 26
			elif self.data[2] < .01 * self.sensitivity_max:
				self.sensitivity = self.sensitivity - 3
				if self.sensitivity < 0:   # 0 correspond to 2nV, minimum sensitivity range
					self.sensitivity = 0

			if self.sensitivity != old_range:
				self.visa.write("SENS %d" % self.sensitivity)
				self.calc_sens_max()
		pass

	def calc_sens_max(self):
		""" Calculate the maximum sensitivity
		TODO: Modify to calculate all sensitivity
		"""

		range_vec = [2., 5., 10.]
		lev = self.sensitivity/3 - 9
		self.sensitivity_max = range_vec[self.sensitivity % 3] * 10**lev
		pass

	def set_output(self, level):
		self.visa.write(f"SLVL {level:.3f}")
		pass

	def ramp(self, finish_value):
		""" A method to ramp the instrument """
		start_value = self.read_numeric("SLVL")
		if abs(start_value - finish_value) > self.ramp_step:
			step_num = abs((finish_value - start_value) / self.ramp_step)
			sweep_value = np.linspace(start_value, finish_value, num=np.ceil(int(step_num)), endpoint=True)

			for i in range(len(sweep_value)):
				self.set_output(sweep_value[i])
				time.sleep(0.01)

			self.excitation = finish_value
		return

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



