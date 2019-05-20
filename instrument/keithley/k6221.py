import time

from .sourcemeter import Keithley


class K6221(Keithley):
    # The 6221 operates only as a source, these functions configure it as an AC source (WAVE mode)
    # and the measurement is made by the Lockin

    def __init__(self, address):
        super().__init__(address)
        self.name = "Keithley 6221"

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

    def description(self):
        """ Print a description string to data file"""

        description_string = (
            f"{super().description()}, "
            f"amplitude={self.amplitude}, "
            f"frequency={self.frequency}, "
            f"compliance={self.compliance}"
            "\n"
        )
        return description_string

    def initialize(
            self, compliance=0.1, ramp_step=1e-9, auto_sense_range=True,
            frequency=9.2, offset=0.0, phase=0.0
    ):

        self.column_names = "I (A)"
        self.data_column = 0
        self.source = "CURR"

        # A bunch of commands to configure the 6221
        if not self.output:
            self.compliance = compliance
            self.ramp_step = ramp_step
            self.frequency = frequency
            self.offset = offset
            self.phase = phase
            self.visa.write("*RST")
            time.sleep(.1)

            self.visa.write(":SOUR:WAVE:FUNC SIN")
            if auto_sense_range:
                self.visa.write(":SOUR:WAVE:RANG BEST")
            else:
                self.visa.write(":SOUR:WAVE:RANG FIX")

            self.visa.write(":TRIG:OLIN 4")
            self.visa.write(f":SOUR:WAVE:PMAR:OLIN {self.trigger_pin}")
            self.visa.write(":SOUR:WAVE:PMAR:STAT ON")
            self.visa.write(f":SOUR:WAVE:PMAR {self.phase:.1f}")

            self.visa.write(f":SOUR:CURR:COMP {self.compliance:.3e}")
            self.visa.write(f":SOUR:WAVE:FREQ {self.frequency:.3e}")
            self.visa.write(f":SOUR:WAVE:OFFS {self.offset:.3e}")
            self.visa.write(f":SOUR:WAVE:AMPL {self.ramp_step:.3e}%")

        return

    def set_output(self, level):
        self.visa.write(f":SOUR:WAVE:AMPL {level:.4e}")
        pass

    def switch_output(self):
        self.output = not self.output
        if self.output:
            self.visa.write(":SOUR:WAVE:ARM")
            self.visa.write(":SOUR:WAVE:INIT")
        else:
            self.visa.write(":SOUR:WAVE:ABOR")

        pass

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
