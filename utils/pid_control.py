class PID:
	"""
	Discrete PID control
	"""

	def __init__(self, p=2.0, i=0.0, d=1.0, derivator=0, integrator=0, integrator_max=500, integrator_min=-500):

		self.k_p = p
		self.k_i = i
		self.k_d = d
		self.derivator = derivator
		self.integrator = integrator
		self.integrator_max = integrator_max
		self.integrator_min = integrator_min

		self.p_value = 0
		self.i_value = 0
		self.d_value = 0

		self.set_point = 0.0
		self.error = 0.0

	def update(self, current_value):
		"""
		Calculate PID output value for given reference input and feedback
		"""

		self.error = self.set_point - current_value

		self.p_value = self.k_p * self.error
		self.d_value = self.k_d * ( self.error - self.derivator)
		self.derivator = self.error

		self.integrator = self.integrator + self.error

		if self.integrator > self.integrator_max:
			self.integrator = self.integrator_max
		elif self.integrator < self.integrator_min:
			self.integrator = self.integrator_min

		self.i_value = self.integrator * self.k_i

		pid_value = self.p_value + self.i_value + self.d_value

		return pid_value

	def initialize_set_point(self, set_point, reset=True):
		"""
		Initilize the setpoint of PID
		"""
		self.set_point = set_point
		if reset:
			self.integrator = 0
			self.derivator = 0
		else:
			pass

	def set_integrator(self, integrator):
		self.integrator = integrator

	def set_derivator(self, derivator):
		self.derivator = derivator

	def set_k_p(self, p):
		self.k_p = p

	def set_k_i(self, i):
		self.k_i = i

	def set_k_d(self, d):
		self.k_d = d

	def get_point(self):
		return self.set_point

	def get_error(self):
		return self.error

	def get_integrator(self):
		return self.integrator

	def get_derivator(self):
		return self.derivator

