import time

from ..generic_instrument import Instrument


class LS475Gaussmeter(Instrument):
    """Lake Shore Model 475 DSP Gaussmeter driver

    """

    def __init__(self, address):
        super().__init__(address)

        self.name = 'LS475 Gaussmeter'

        self.source = 'Field'
        self.sense = ""
        self.column_names = 'B (G)'
        self.data = [0.0]
        self.data_column = 0
        self.source_column = 1

        self.output = False

    def initialize(self):
        self.visa.write('UNIT 1')
        self.visa.write('CMODE 1')
        self.visa.write('CPARAM 15.0, 5.0, 3000.0, 40.0 ')
        pass

    def read_data(self):
        """ Read magnetic field """
        reply = self.visa.ask(':RDGFIELD?')
        self.data = [reply]
        pass

    def set_output(self, level):
        self.visa.write(f'CSETP {level:.4e}')
        time.sleep(4.0)
        pass

    def switch_output(self):
        self.output = not self.output
        pass

    def ramp(self, finish_value):
        time1 = float(self.visa.ask(':RDGFIELD?'))
        time2 = 4 * abs(finish_value - time1) / 50
        self.set_output(finish_value)
        print('Ramping to Field Value')
        time.sleep(time2)
        return
