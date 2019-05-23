import time

import utils.visa_subs as visa_subs
from ..generic_instrument import Instrument


class AVS47B(Instrument):

    def __init__(self):
        self.visa = visa_subs.initialize_gpib(address=20, board=0, query_delay='0.04')
        self.visa.write('HDR0')
        self.visa.write('ARN 1')
        self.visa.write('REM 1')

        self.channel = 0
        self.range = 0
        self.resistance = 1.0
        self.sensor = 'CERNOX'

    def read_resistance(self):
        # Get the resistance of the current channel of the picowatt
        self.visa.write('ADC')
        time.sleep(0.45)
        answer = self.visa.query('RES?')
        answer = answer.strip()
        try:
            self.resistance = float(answer)
        except:
            self.resistance = self.resistance
            pass
        return

    def read_range(self):
        answer = self.visa.query('RAN?')
        answer = answer.strip()
        self.range = int(answer)
        return

    def set_channel(self, channel):
        self.visa.write('INP 0')
        command = "".join(('MUX ', '%d' % channel))
        self.visa.write(command)
        time.sleep(3)
        self.visa.write('INP 1')
        time.sleep(10)
        self.channel = channel
        return