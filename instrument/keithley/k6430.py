import time

from .sourcemeter import Keithley


class K6430(Keithley):

    def __init__(self, address):
        super().__init__(address)
        self.name = 'Keithley 6430'
