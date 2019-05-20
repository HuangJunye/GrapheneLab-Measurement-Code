import time

from .sourcemeter import Keithley


class K2182(Keithley):
    def __init__(self, address):
        super().__init__(address)
        self.name = "Keithley 2182A"
        
        # Special variables for 2182
        self.channel = 1
        self.relative = False
        self.a_filter = False
        self.d_filter = True
        self.count = 5
        self.sense_range = 1.
        self.auto_sense_range = False
        self.relative_value = 0.

    def description(self):
        """Print a description string to data file"""

        description_string = (
            f"{super().description()}, "
            f"sense={self.sense}, "
            f"sense range={self.sense_range}, "
            f"relative={self.relative}, "
            f"relative value={self.relative_value}, "
            "\n"
        )
        return description_string

    def initialize(
            self, channel=1, a_cal=False, relative=False, a_filter=False,
            d_filter=True, count=5, sense_range=1., auto_sense_range=False
    ):

        self.column_names = "V (V)"
        self.data = [0.0]
        self.data_column = 0
        self.sense = "VOLT"
        
        # Special variables for 2182
        self.channel = channel
        self.relative = relative
        self.a_filter = a_filter
        self.d_filter = d_filter
        self.count = count
        self.sense_range = sense_range
        self.auto_sense_range = auto_sense_range

        # A bunch of commands to configure the 2182
        self.visa.write("*RST")
        time.sleep(.1)
        self.visa.write(":SENS:FUNC \'VOLT\'")
        self.visa.write(":SENS:CHAN %d" % channel)
        
        if auto_sense_range:
            self.auto_sense_range = True
            self.visa.write("".join((":SENS:", self.sense, ":RANG:AUTO 1")))
        else:
            self.sense_range = sense_range
            self.auto_sense_range = False
            self.visa.write("".join((":SENS:", self.sense, ":RANG ", "%.2e" % sense_range)))

        if a_cal:
            self.visa.write(":CAL:UNPR:ACAL:INIT")
            time.sleep(1.0)
            reply = self.visa.query(":CAL:UNPR:ACAL:TEMP?")
            time.sleep(10.)
            self.visa.write(":CAL:UNPR:ACAL:DONE")

        # Set some filters
        if a_filter:
            self.visa.write(":SENS:VOLT:LPAS 1")
        else:
            self.visa.write(":SENS:VOLT:LPAS 0")

        if d_filter:
            self.visa.write(":SENS:VOLT:DFIL 1")
            self.visa.write(":SENS:VOLT:DFIL:COUN %d" % count)
        else:
            self.visa.write(":SENS:VOLT:DFIL 0")

        self.visa.query(":READ?")

        self.visa.write(":SENS:VOLT:REF:STAT 0")
        if relative:
            self.visa.write(":SENS:VOLT:REF:ACQ")
            self.visa.write(":SENS:VOLT:REF:STAT 1")
            reply = self.visa.query(":SENS:VOLT:REF?")
            print(reply)
            self.relative_value = float(reply)

        pass

    def read_data(self):
        reply = self.visa.query(":READ?")
        self.data = [float(reply)]
        pass
