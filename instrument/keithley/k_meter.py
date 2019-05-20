import time

import numpy as np

from ..generic_instrument import Instrument


class Keithley(Instrument):
    """ Implement a generic keitheley sourcemeter for k6430, k2400 and k2002
    Based on generic Instrument class, add the following methods:

    initialize
    ramp

    """
    def __init__(self, address):
        super().__init__(address)
        self.mode = ""
        self.column_names = ""
        self.data = [0.0, 0.0]
        self.source_column = 0
        self.data_column = 1
        self.source = ""
        self.sense = ""
        self.compliance = 0
        self.ramp_step = 0
        self.source_range = 0
        self.sense_range = 0
        self.output = False

    def description(self):
        """ Print a description string to data file"""

        description_string = (
            f"{super().description()}, "
            f"source={self.source}, "
            f"sense={self.sense}, "
            f"compliance={self.compliance}"
            "\n"
        )
        return description_string

    def initialize(
            self, mode="VOLT", source_range=21, sense_range=105e-9, compliance=105e-9,
            ramp_step=0.1, auto_sense_range=False, reset=True
    ):
        """Initialize Keithley sourcemeter with specified mode, and other parameters"""

        self.mode = mode

        if self.mode == "VOLT":
            self.source = "VOLT"
            self.sense = "CURR"
            self.source_column = 0
            self.data_column = 1
        elif self.mode == "CURR":
            self.source = "CURR"
            self.sense = "VOLT"
            self.source_column = 1
            self.data_column = 0
        else:
            raise ValueError("This mode does exist! Please input 'VOLT' or 'CURR' only.")

        self.column_names = "V (V),I (A)"
        self.source_range = source_range
        self.sense_range = sense_range
        self.ramp_step = ramp_step
        self.data = [0.0, 0.0]

        if reset:
            self.output = False
            self.visa.write(":OUTP 0")
            self.visa.write("*RST")
            self.visa.write(":SYST:BEEP:STAT 0")
            time.sleep(.1)

            self.visa.write(f":SOUR:FUNC:MODE {self.source}")
            self.visa.write(f":SOUR:{self.source}:RANG {self.source_range:.2e}")
            if auto_sense_range:
                self.visa.write(":SENS:CURR:RANG:AUTO 0")
            else:
                self.visa.write(f":SENS:{self.sense}:RANG {self.sense_range:.2e}")
            
            self.compliance = compliance
            self.visa.write(f":SENS:{self.sense}:PROT:LEV {self.compliance:.3e}")

            # Configure the auto zero (reference)
            self.visa.write(":SYST:AZER:STAT ON")
            self.visa.write(":SYST:AZER:CACH:STAT 1")
            self.visa.write(":SYST:AZER:CACH:RES")

            # Disable concurrent mode, measure I and V (not R)
            self.visa.write(":SENS:FUNC:CONC 1")
            self.visa.write(":SENS:FUNC:ON \"VOLT\",\"CURR\"")
            self.visa.write(":FORM:ELEM VOLT,CURR")

        else:
            self.output = bool(int(self.visa.query(":OUTP:STAT?")))
            self.compliance = float(self.visa.query(":SENS:CURR:PROT:LEV?"))
            self.read_data()

        return

    def read_data(self):
        reply = self.visa.query(":READ?")
        self.data = [float(i) for i in reply.split(",")[0:2]]
        pass

    def set_output(self, level):
        self.visa.write(f":SOUR:{self.source} {level:.4e}")
        pass

    def switch_output(self):
        self.output = not self.output
        self.visa.write(f":OUTP:STAT {self.output}")
        pass

    def ramp(self, finish_value):
        """ A method to ramp the instrument"""
        if self.output:
            self.read_data()
        start_value = self.data[self.source_column]
        if abs(start_value - finish_value) > self.ramp_step:
            step_num = abs((finish_value - start_value) / self.ramp_step)
            sweep_value = np.linspace(start_value, finish_value, num=np.ceil(int(step_num)), endpoint=True)

            if not self.output:
                self.switch_output()

            for i in range(len(sweep_value)):
                self.set_output(sweep_value[i])
                time.sleep(0.01)

            self.read_data()
        return
