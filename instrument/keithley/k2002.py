import time

from .sourcemeter import Keithley


class K2002(Keithley):
    def __init__(self, address):
        super().__init__(address)
        self.name = 'Keithley 2002'

        # Special variables for 2002
        self.channel = 1
        self.relative = False
        self.filter = True
        self.count = 5
        self.sense_range = 2.
        self.auto_sense_range = False
        self.relative_value = 0.

    def description(self):
        """Print a description string to data file"""

        description_string = (
            f'{super().description()}, '
            f'sense={self.sense}, '
            f'sense range={self.sense_range}, '
            f'relative={self.relative}, '
            f'relative value={self.relative_value}, '
            '\n'
        )
        return description_string

    def initialize(
            self, a_cal=False, relative=False, filter=True,
            count=5, sense_range=2., auto_sense_range=False
    ):

        self.column_names = 'V (V)'
        self.data = [0.0]
        self.data_column = 0
        self.sense = 'VOLT'

        # Special variables for 2002
        self.relative = relative
        self.filter = filter
        self.count = count
        self.sense_range = sense_range
        self.auto_sense_range = auto_sense_range

        # A bunch of commands to configure the 2002
        self.visa.write('*RST')
        time.sleep(.1)
        self.visa.write(':SENS:FUNC \'VOLT:DC\'')
        self.visa.query(':READ?')

        if self.auto_sense_range:
            self.auto_sense_range = True
            self.visa.write("".join((':SENS:', self.sense, ':RANG:AUTO 1')))
        else:
            self.sense_range = sense_range
            self.auto_sense_range = False
            self.visa.write("".join((':SENS:', self.sense, ':RANG ', '%.2e' % sense_range)))

        if self.filter:
            self.visa.write(':SENS:VOLT:AVER:STAT 1')
            self.visa.write(':SENS:VOLT:AVER:COUN %d' % count)
        else:
            self.visa.write(':SENS:VOLT:AVER:STAT 0')

        self.visa.query(':READ?')

        self.visa.write(':SENS:VOLT:REF:STAT 0')
        if relative:
            self.visa.write(':SENS:VOLT:REF:ACQ')
            self.visa.write(':SENS:VOLT:REF:STAT 1')
            reply = self.visa.query(':SENS:VOLT:REF?')
            print(reply)
            self.relative_value = float(reply)

        pass

    def read_data(self):
        self.visa.write(':INIT')
        reply = self.visa.query(':FETC?')
        self.data = [float(reply)]
        pass
