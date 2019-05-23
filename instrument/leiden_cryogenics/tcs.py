import numpy as np

import utils.visa_subs as visa_subs
from ..generic_instrument import Instrument


class TripleCurrentSource(Instrument):

    def __init__(self):
        self.visa = visa_subs.initialize_serial(address=6, idn='ID?')

        self.heater = [0, 0, 0]
        self.range = [1, 1, 1]
        self.current = [0, 0, 0]
        
        self.max_current = 35000

    def set_current(self, source, current):
        if current < 0:
            current = 0
        elif current > self.max_current:
            current = self.max_current
        # current in microAmp
        # print current
        source = source + 1
        command = ' '.join(('SETDAC', '%d' % source, '0', '%d' % current))

        self.visa.query(command)
        return

    def read_current(self):
        answer = self.visa.query('STATUS?')
        reply = answer.split('\t')[1]
        reply = reply.split(',')
        sensor_range = reply[1::4]
        current = reply[2::4]
        heaters = reply[3::4]
        tmp = [1, 10, 100, 1000]
        for i in range(3):
            self.heater[i] = int(heaters[i])
        for i in range(3):
            self.current[i] = int(current[i]) * tmp[int(sensor_range[i]) - 1]
        return

    def switch_heater(self, heater):
        command_vector = np.zeros((12,))
        command_vector[2 + heater * 4] = 1
        command_string = 'SETUP '
        print('Heater %d Switched %d' % (heater, int(not self.heater[heater])))
        for i in command_vector:
            command_string = "".join((command_string, '%d,' % i))
        command_string = command_string[:-1]
        reply = self.visa.query(command_string)
        return
