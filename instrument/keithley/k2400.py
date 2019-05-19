import time

import numpy as np

import utils.visa_subs as visa_subs
from .k_meter import Keithley


class K2400(Keithley):
    def __init__(self, address):
        super().__init__(address)
        self.name = "Keithley 2400"

    ######################################
    # Initializate as voltage source
    #######################################

    def initialize_voltage(
            self, compliance=105e-9,
            ramp_step=0.1, auto_range=False,
            reset=True, source_range=21
    ):

        self.source = "VOLT"
        self.ramp_step = ramp_step
        self.column_names = "V (V), I (A)"
        self.data_column = 1
        self.source = "VOLT"
        self.sense = "CURR"
        self.data = [0.0, 0.0]

        if reset:
            self.compliance = compliance
            self.output = False
            self.visa.write(":OUTP 0")
            # A bunch of commands to configure the 6430
            self.visa.write("*RST")
            self.visa.write(":SYST:BEEP:STAT 0")
            time.sleep(.1)
            self.visa.write(":SOUR:FUNC:MODE VOLT")
            self.visa.write(":SOUR:VOLT:RANG %d" % source_range)
            # Configure the auto zero (reference)
            self.visa.write(":SYST:AZER:STAT ON")
            self.visa.write(":SYST:AZER:CACH:STAT 1")
            self.visa.write(":SYST:AZER:CACH:RES")
            # Disable concurrent mode, measure I and V (not R)
            self.visa.write(":SENS:FUNC:CONC 1")
            self.visa.write(":SENS:FUNC:ON \"VOLT\",\"CURR\"")
            self.visa.write(":FORM:ELEM VOLT,CURR")
            if auto_range:
                self.visa.write(":SENS:CURR:RANG:AUTO 0")
            else:
                self.visa.write(":SENS:CURR:RANG 105e-9")
            self.visa.write(":SENS:CURR:PROT:LEV %.3e" % self.compliance)
        else:
            self.output = bool(int(self.visa.query(":OUTP:STAT?")))
            self.compliance = float(self.visa.query(":SENS:CURR:PROT:LEV?"))
            self.read_data()

        return

    def description(self):
        description_string = "Keithley2400"
        for item in list(vars(self).items()):
            if item[0] == "address":
                description_string = ", ".join((description_string, "%s = %.3f" % item))
            elif item[0] == "source" or item[0] == "sense" or item[0] == "compliance":
                description_string = ", ".join((description_string, "%s = %s" % item))

        description_string = "".join((description_string, "\n"))
        return description_string
