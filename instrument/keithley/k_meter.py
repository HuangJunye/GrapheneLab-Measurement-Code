import time

from ..generic_instrument import Instrument


class Keithley(Instrument):
    """ Implement a generic keitheley sourcemeter for k6430, k2400 and k2002
    Based on generic Instrument class, add the following methods:

    initialize_voltage
    initialize_current
    set_range_compliance

    """
    def __init__(self, address):
        super().__init__(address)

    def initialize_voltage(
            self, source_range=21, sense_range=105e-9, compliance=105e-9,
            ramp_step=0.1, auto_sense_range=False, reset=True
    ):

        self.source = "VOLT"
        self.sense = "CURR"
        self.ramp_step = ramp_step
        self.column_names = "V (V),I (A)"
        self.data_column = 1
        self.data = [0.0, 0.0]

        if reset:
            self.output = False
            self.visa.write(":OUTP 0")
            self.visa.write("*RST")
            self.visa.write(":SYST:BEEP:STAT 0")
            time.sleep(.1)

            self.visa.write(":SOUR:FUNC:MODE VOLT")
            self.visa.write(":SOUR:VOLT:RANG %d" % source_range)
            self.visa.write("".join((":SENS:", self.sense, ":RANG ", "%.2e" % self.sense_range)))
            self.visa.write(f":SENS:{}")
            self.compliance = compliance
            self.visa.write("".join((":SENS:", self.sense, ":PROT:LEV %.3e" % self.compliance)))

            # Configure the auto zero (reference)
            self.visa.write(":SYST:AZER:STAT ON")
            self.visa.write(":SYST:AZER:CACH:STAT 1")
            self.visa.write(":SYST:AZER:CACH:RES")

            # Disable concurrent mode, measure I and V (not R)
            self.visa.write(":SENS:FUNC:CONC 1")
            self.visa.write(":SENS:FUNC:ON \"VOLT\",\"CURR\"")
            self.visa.write(":FORM:ELEM VOLT,CURR")

            if auto_sense_range:
                self.visa.write(":SENS:CURR:RANG:AUTO 0")
            else:
                self.visa.write(":SENS:CURR:RANG 105e-9")
            self.visa.write(":SENS:CURR:PROT:LEV %.3e" % self.compliance)
        else:
            self.output = bool(int(self.visa.query(":OUTP:STAT?")))
            self.compliance = float(self.visa.query(":SENS:CURR:PROT:LEV?"))
            self.read_data()

        return

    def initialize_current(
            self, compliance=1.0,
            median=0, repetition=1,
            integration=1, delay=0.0, trigger=0,
            ramp_step=0.1, sense_range=1.0, auto_sense_range=False
    ):

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

        if auto_sense_range:
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

    def set_range_compliance(self, sense_range=105, compliance=105):

        self.compliance = compliance
        self.visa.write("".join((":SENS:", self.sense, ":PROT:LEV %.3e" % self.compliance)))

        if sense_range:
            self.visa.write("".join((":SENS:", self.sense, ":RANG ", "%.2e" % sense_range)))
        else:
            self.visa.write("".join((":SENS:", self.sense, ":RANG:AUTO 1")))

        pass

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
