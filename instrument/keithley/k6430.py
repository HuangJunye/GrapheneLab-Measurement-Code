import time

import numpy as np

import utils.visa_subs as visa_subs


class K6430:
    def __init__(self, address):
        self.name = "Keithley 6430"
        self.address = address
        self.visa = visa_subs.initialize_gpib(address, 0)

    ######################################
    # Initialize as voltage source
    #######################################

    def initialize_voltage(
            self, compliance=105e-9, median=0, repetition=1, moving=1,
            integration=1, delay=0.0, trigger=0, ramp_step=0.1, sense_range=105e-9,
            auto_range=False, auto_filter=False, auto_delay=False
    ):

        self.column_names = "V (V), I (A)"
        self.data = [0.0, 0.0]
        self.data_column = 1
        self.source_column = 0
        self.source = "VOLT"
        self.sense = "CURR"
        self.moving = moving
        # Special variables for 6430
        self.median = median
        self.repetition = repetition
        self.integration = integration
        self.delay = delay
        self.compliance = compliance
        self.ramp_step = ramp_step
        self.sense_range = sense_range
        self.output = False
        self.visa.write(":OUTP 0")
        self.trigger = trigger

        # A bunch of commands to configure the 6430
        self.visa.write("*RST")
        time.sleep(.1)
        self.visa.write(":SOUR:FUNC:MODE VOLT")
        # Configure the auto zero (reference)
        self.visa.write(":SYST:AZER:STAT ON")
        self.visa.write(":SYST:AZER:CACH:STAT 1")
        self.visa.write(":SYST:AZER:CACH:RES")

        # Disable concurrent mode, measure I and V (not R)
        self.visa.write(":SENS:FUNC:CONC 1")

        self.visa.write(":SENS:FUNC:ON \"VOLT\",\"CURR\"")
        self.visa.write(":FORM:ELEM VOLT,CURR")

        self.visa.write(":SENS:CURR:PROT:LEV %.3e" % self.compliance)
        if auto_range:
            self.visa.write(":SENS:CURR:RANG:AUTO 1")
        else:
            self.visa.write(":SENS:CURR:RANG %.2e" % self.sense_range)

        # Set some filters

        if auto_filter:
            self.visa.write(":SENS:AVER:AUTO ON")
        else:
            self.visa.write(":SENS:CURR:NPLC %.2f" % self.integration)
            self.visa.write(":SENS:AVER:REP:COUN %d" % self.repetition)
            self.visa.write(":SENS:AVER:COUN %d" % self.moving)
            self.visa.write(":SENS:MED:RANK %d" % self.median)

        if auto_delay:
            self.visa.write(":SOUR:DEL:AUTO ON")
        else:
            self.visa.write(":SOUR:DEL %.4f" % self.delay)

        self.visa.write(":TRIG:DEL %.4f" % self.trigger)

        pass

    ######################################
    # Initialize as current source
    #######################################

    def initialize_current(
            self, compliance=1.0,
            median=0, repetition=1,
            integration=1, delay=0.0, trigger=0,
            ramp_step=0.1, sense_range=1.0, auto_range=False):

        self.column_names = "V (V), I (A)"
        self.data_column = 0
        self.source_column = 1
        self.source = "CURR"
        self.sense = "VOLT"
        # Special variables for 6430
        self.median = median
        self.repetition = repetition
        self.integration = integration
        self.delay = delay
        self.compliance = compliance
        self.ramp_step = ramp_step
        self.sense_range = sense_range
        self.trigger = trigger

        # A bunch of commands to configure the 6430
        self.visa.write("*RST")
        self.visa.write(":SYST:BEEP:STAT 0")
        time.sleep(.1)
        self.visa.write(":SOUR:FUNC:MODE CURR")
        # Configure the auto zero (reference)
        self.visa.write(":SYST:AZER:STAT ON")
        self.visa.write(":SYST:AZER:CACH:STAT 1")
        self.visa.write(":SYST:AZER:CACH:RES")

        # Disable concurrent mode, measure I and V (not R)
        self.visa.write(":SENS:FUNC:CONC 1")

        self.visa.write(":SENS:FUNC:ON \"VOLT\",\"CURR\"")
        self.visa.write(":FORM:ELEM VOLT,CURR")

        self.visa.write(":SENS:VOLT:PROT:LEV %.3e" % self.compliance)

        if auto_range:
            self.visa.write(":SENS:VOLT:RANG:AUTO 1")
        else:
            self.visa.write(":SENS:VOLT:RANG %.2e" % self.sense_range)
        # Set some filters
        self.visa.write(":SENS:CURR:NPLC %.2f" % self.integration)

        self.visa.write(":SENS:AVER:REP:COUN %d" % self.repetition)
        self.visa.write(":SENS:MED:RANK %d" % self.median)

        self.visa.write(":SOUR:DEL %.4f" % self.delay)
        self.visa.write(":TRIG:DEL %.4f" % self.trigger)

        pass

    ###########################################
    # Set the range and compliance
    #######################################

    def set_range_compliance(self, sense_range=105, compliance=105):

        self.compliance = compliance
        self.visa.write("".join((":SENS:", self.sense, ":PROT:LEV %.3e" % self.compliance)))

        if sense_range:
            self.visa.write("".join((":SENS:", self.sense, ":RANG ", "%.2e" % sense_range)))
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

    #################################################
    # Configure a sweep
    ###############################################

    def configure_sweep(self, start, stop, step, soak=0):
        self.visa.write("".join((":SOUR:", self.source, ":START %.4e" % start)))
        self.visa.write("".join((":SOUR:", self.source, ":STOP %.4e" % stop)))
        self.visa.write("".join((":SOUR:", self.source, ":STEP %.4e" % step)))
        count = int(1 + abs(stop - start) / step)
        self.visa.write(":SOUR:SOAK %.4e" % soak)
        self.visa.write("TRIG:COUN %d" % count)
        pass

    ###################################################
    # Begin sweep, this doesn't work so well, not recommended
    #################################################

    def run_configured_sweep(self):
        self.visa.write(":SOUR:VOLT:MODE SWE")
        self.visa.write(":SOUR:SWE:SPAC LIN")
        self.visa.write(":SOUR:SWE:RANG AUTO")
        self.visa.write(":SOUR:DEL %0.4e" % self.delay)
        self.switch_output()
        pass

    ###################################################
    # Print a description string
    ################################################

    def description(self):
        description_string = "Keithley6430"
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
        v_start = self.data[self.source_column]
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
