import time

import numpy as np

import utils.visa_subs as visa_subs


class K2400:
    def __init__(self, address):
        self.name = "Keithley 2400"
        self.address = address
        self.visa = visa_subs.initialize_gpib(address, 0)

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

    ###########################################
    # Set the range and compliance
    #######################################

    def set_range_compliance(self, sense_range=105e-9, compliance=105e-9):

        self.compliance = compliance
        self.visa.write("".join((":SENS:", self.sense, ":PROT:LEV %.3e" % self.compliance)))

        if sense_range:
            self.visa.write("".join((":SENS:", self.sense, ":RANG ", "%.3e" % sense_range)))
        else:
            self.visa.write("".join((":SENS:", self.sense, ":RANG:AUTO 1")))

        pass

    ##################################################
    # Read data
    ################################################

    def read_data(self):
        reply = self.visa.query(":READ?")
        self.data = [float(i) for i in reply.split(",")[0:2]]
        pass

    ##################################################
    # Set source
    ##################################################

    def set_output(self, level):
        self.visa.write("".join((":SOUR:", self.source, " %.4e" % level)))
        pass

    #################################################
    # Switch the output
    ###############################################

    def switch_output(self):
        self.output = not self.output
        self.visa.write("".join((":OUTP:STAT ", "%d" % self.output)))
        pass

    ###################################################
    # Print a description string
    ################################################

    def description(self):
        description_string = "Keithley2400"
        for item in list(vars(self).items()):
            if item[0] == "address":
                description_string = ", ".join((description_string, "%s = %.3f" % item))
            elif item[0] == "source" or item[0] == "sense" or item[0] == "compliance":
                description_string = ", ".join((description_string, "%s = %s" % item))

        description_string = "".join((description_string, "\n"))
        return description_string

    ############################################
    # ramp the source to a final value
    #########################################

    def ramp(self, v_finish):
        if self.output:
            self.read_data()
        v_start = self.data[0]
        if abs(v_start - v_finish) > self.ramp_step:
            n = abs((v_finish - v_start) / self.ramp_step)
            v_sweep = np.linspace(v_start, v_finish, num=np.ceil(n), endpoint=True)

            if not self.output:
                self.switch_output()

            for i in range(len(v_sweep)):
                self.set_output(v_sweep[i])
                time.sleep(0.01)

            self.read_data()

        return
