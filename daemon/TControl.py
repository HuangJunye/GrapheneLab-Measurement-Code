from collections import deque
from datetime import datetime

import numpy as np

import utils.pid_control as pid_control
import utils.socket_subs as socket_subs
from instrument.picowatt.avs47b import AVS47B
from instrument.leiden_cryogenics.tcs import TripleCurrentSource


class TControl:
    """ Initialization call, initialize visas for the TCS, Picowatt and the
    Server, server always runs at 18871
    """

    def __init__(self):

        address = ('localhost', 18871)
        self.server = socket_subs.SockServer(address)

        self.pico = AVS47B()
        self.tcs = TripleCurrentSource()
        # Initialize a pid controller
        self.pid = pid_control.PID(
            p=20., i=.5, d=0, derivator=0, integrator=0,
            integrator_max=60000, integrator_min=-2000)
        self.pid_output = None

        self.temperature = 0.0
        self.delta_temp = 1.0

        self.set_temp = -1.0

        self.max_set_temp = 10000.0
        
        # Acceptable temperature error as a factor e.g. 100 * 0.005 = 0.5mK
        self.error_temp = 0.01  # The acceptable error in temperature
        self.error_delta_temp = 0.005  # The acceptable stability

        # Sweep description
        self.sweep_finish = 0.0
        self.sweep_start = 0.0
        self.sweep_rate = 1.0  # As received from socket in mK/min
        self.sweep_rate_sec = 1.0 / 60.0
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

        return

    def calc_temperature(self, calibration, factor=0.0):
        log_resistance = np.log10(self.pico.resistance) - factor
        r_poly = np.ones((len(calibration),))
        old_temperature = self.temperature
        for i in range(1, len(r_poly)):
            r_poly[i] = log_resistance * r_poly[i - 1]
        self.temperature = np.power(10, (np.sum(np.multiply(r_poly, calibration))))
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
        error_factor = abs(self.temperature - self.set_temp) / self.temperature
        delta_temp_factor = abs(np.std(self.temp_history)) / self.temperature
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

        msg = msg.decode()  # change in python 3
        msg = msg.split(' ')

        if msg[0] == 'SET':
            try:
                new_set_temperature = float(msg[1])
                # Only interpret new setpoints if the change is >50mK
                if abs(self.set_temp - new_set_temperature) > 0.05:
                    self.set_temp = new_set_temperature
                    if self.pico.channel == 5:
                        pass
                    self.pid.initialize_set_point(self.set_temp)
                    # Set at set to be false and write the new set point
                    self.at_set = False
                    self.sweep_mode = False
                    print('Got probe set point from socket %.2f\n' % self.set_temp)
            except:
                pass

        if msg[0] == 'SWP':
            try:
                self.sweep_finish = float(msg[1])
                if abs(self.sweep_finish - self.set_temp) > 0.05:
                    self.sweep_start = self.set_temp
                    self.pid.initialize_set_point(self.set_temp)
                    self.sweep_rate = abs(float(msg[2]))
                    self.sweep_rate_sec = self.sweep_rate / 60.0
                    self.sweep_max_over_time = abs(float(msg[3]))
                    # Check if the sweep is up or down
                    if self.sweep_finish >= self.set_temp:
                        self.sweep_direction = 1.0
                    else:
                        self.sweep_direction = -1.0
                    # Put the LS340 into ramp mode
                    self.at_set = False
                    self.sweep_time_length = abs(self.set_temp - self.sweep_finish) / self.sweep_rate
                    print(
                        'Got temperature sweep to %.2f K at %.2f K/min... Sweep takes %.2f minutes, maximum over time is %.2f' % (
                            self.sweep_finish, self.sweep_rate, self.sweep_time_length, self.sweep_max_over_time))
                    # Write the finish temp
                    # Write the setpoint to start the ramp
                    self.sweep_mode = True
                    self.sweep_start_time = datetime.now()
                    print('Starting the sweep\n')
            except:
                pass

        if msg[0] == 'T_ERROR':
            try:
                self.error_temp = float(msg[1])
            except:
                pass

        if msg[0] == 'DT_ERROR':
            try:
                self.error_delta_temp = float(msg[1])
            except:
                pass

        return

    def sweep_control(self):

        # We are sweeping so check if the sweep is finished
        d_temp_in_seconds = datetime.now() - self.sweep_start_time
        d_temp_in_minutes = d_temp_in_seconds.seconds / 60.0

        if d_temp_in_minutes > (self.sweep_time_length + self.sweep_max_over_time):
            # The sweep ran out of time, stop it
            sweep_finished = True
            print('Sweep over time... Finishing...')
        elif (self.temperature - self.sweep_finish) * self.sweep_direction > 0.0:
            sweep_finished = True
            print('Final temperature reached... Finishing...')
        else:
            sweep_finished = False

        if sweep_finished:
            self.sweep_mode = False
        else:
            old_set_temperature = self.set_temp
            self.set_temp = self.sweep_start + self.sweep_rate_sec * d_temp_in_seconds.seconds * self.sweep_direction

            if self.pico.channel == 5:
                pass
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
        status_string = '%s = %.2f K; PID output = %d; ' % (self.pico.sensor, self.temperature, self.pid_output)
        status_string += 'Status message = %d; ' % self.status_msg
        status_string += 'P = %.2f, I = %.2f, D = %.2f\n' % (self.pid.p_value, self.pid.i_value, self.pid.d_value)
        print(status_string)
        self.last_status_time = datetime.now()
        return
