import time

import numpy as np

import utils.visa_subs as visa_subs


class Instrument:
    """ Implement a generic instrument which does the following:

    initialize
    read_data
    set_output
    switch_output
    description
    ramp

    """

    def __init__(self, address):
        self.name = "Instrument Name"
        self.address = address
        self.visa = visa_subs.initialize_gpib(address, 0)

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

    def description(self):
        description_string = self.name
        for item in list(vars(self).items()):
            if item[0] == "address":
                description_string = ", ".join((description_string, "%s = %.3f" % item))
            elif item[0] == "source" or item[0] == "sense" or item[0] == "compliance":
                description_string = ", ".join((description_string, "%s = %s" % item))

        description_string = "".join((description_string, "\n"))
        return description_string

    def read_data(self):
        reply = self.visa.query(":READ?")
        self.data = [float(i) for i in reply.split(",")[0:2]]
        pass

    def set_output(self, level):
        self.visa.write("".join((":SOUR:", self.source, " %.4e" % level)))
        pass

    def switch_output(self):
        self.output = not self.output
        self.visa.write("".join((":OUTP:STAT ", "%d" % self.output)))
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
