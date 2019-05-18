import time

import utils.visa_subs as visa_subs


class K6221:
    # The 6221 operates only as a source, these functions configure it as an AC source (WAVE mode)
    # and the measurement is made by the Lockin

    def __init__(self, address):
        self.name = "Keithley 6221"
        self.address = address
        self.visa = visa_subs.initialize_gpib(address, 0)
        # Other 6430 properties
        # Query the output state
        self.output = False
        reply = self.visa.query(":OUTP:STAT?")
        reply = int(reply)
        self.output = bool(reply)
        if self.output:
            self.compliance = self.read_numeric(":SOUR:CURR:COMP?")
            self.frequency = self.read_numeric(":SOUR:WAVE:FREQ?")
            self.amplitude = self.read_numeric(":SOUR:WAVE:AMPL?")
            self.offset = self.read_numeric(":SOUR:WAVE:OFFS?")
            self.phase = self.read_numeric(":SOUR:WAVE:PMAR?")
            self.trigger_pin = 2
        else:
            self.compliance = 0.0
            self.frequency = 9.2
            self.amplitude = 0.0  # Amperes
            self.offset = 0.0
            self.phase = 0.0  # position of the phase marker
            self.trigger_pin = 2  # pin to write the trigger
            self.visa.write(":SOUR:CLE:IMM")
        self.ramp_step = 10e-9
        self.source = "CURR"
        self.column_names = "I (A)"
        self.data_column = 0
        self.data = [self.amplitude]  # Amperes

    # Move the trigger pin so we can set the phase marker to line 2

    ######################################
    # Initialize as voltage source
    #######################################

    def initialize_wave(
            self, compliance=0.1, ramp_step=1e-9, auto_range=True,
            frequency=9.2, offset=0.0, phase=0.0
    ):

        self.column_names = "I (A)"
        self.data_column = 0
        self.source = "CURR"
        # A bunch of commands to configure the 6430
        if not self.output:
            self.compliance = compliance
            self.ramp_step = ramp_step
            self.frequency = frequency
            self.offset = offset
            self.phase = phase
            self.visa.write("*RST")
            time.sleep(.1)
            # self.visa.write(":OUTP:LTE ON")
            self.visa.write(":SOUR:WAVE:FUNC SIN")
            if auto_range:
                self.visa.write(":SOUR:WAVE:RANG BEST")
            else:
                self.visa.write(":SOUR:WAVE:RANG FIX")

            self.visa.write(":TRIG:OLIN 4")
            self.visa.write(":SOUR:WAVE:PMAR:OLIN %d" % self.trigger_pin)
            self.visa.write(":SOUR:WAVE:PMAR:STAT ON")
            self.visa.write(":SOUR:WAVE:PMAR %.1f" % self.phase)

            self.visa.write(":SOUR:CURR:COMP %.3e" % self.compliance)
            self.visa.write(":SOUR:WAVE:FREQ %.3e" % self.frequency)
            self.visa.write(":SOUR:WAVE:OFFS %.3e" % self.offset)
            self.visa.write(":SOUR:WAVE:AMPL %.3e" % self.ramp_step)

        return

    ##################################################
    # Read numeric
    ################################################

    def read_numeric(self, command):
        reply = self.visa.query(command)
        answer = float(reply)
        return answer

    ##################################################
    # Set source
    ##################################################

    def set_output(self, level):
        self.visa.write(":SOUR:WAVE:AMPL %.4e" % level)
        pass

    #################################################
    # Switch the output
    ###############################################

    def switch_output(self):
        self.output = not self.output
        if self.output:
            self.visa.write(":SOUR:WAVE:ARM")
            self.visa.write(":SOUR:WAVE:INIT")
        else:
            self.visa.write(":SOUR:WAVE:ABOR")

        pass

    ###################################################
    # Print a description string
    ################################################

    def description(self):
        description_string = "Keithley6221"
        for item in list(vars(self).items()):
            if item[0] == "address" or item[0] == "amplitude" or item[0] == "frequency":
                description_string = ", ".join((description_string, "%s = %.3f" % item))
            elif item[0] == "Compliance":
                description_string = ", ".join((description_string, "%s = %s" % item))

        description_string = "".join((description_string, "\n"))
        return description_string

    ############################################
    # ramp the source to a final value
    #########################################

    def ramp(self, v_finish):
        v_start = self.amplitude
        if abs(v_start - v_finish) > self.ramp_step:

            if self.output:
                self.switch_output()

            self.set_output(v_finish)
            self.switch_output()

            self.amplitude = v_finish
            self.data[0] = v_finish

        return