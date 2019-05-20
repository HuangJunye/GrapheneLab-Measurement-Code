import utils.visa_subs as visa_subs


class Instrument:
    """ Implement a generic instrument which does the following:

    description
    read_data
    set_output
    switch_output
    """

    def __init__(self, address):
        self.name = "Instrument Name"
        self.address = address
        self.visa = visa_subs.initialize_gpib(address, 0)

        self.column_names = ""
        self.data = [0.0, 0.0]
        self.data_column = 1
        self.source_column = 0
        self.source = ""
        self.sense = ""
        self.compliance = 0
        self.ramp_step = 0
        self.source_range = 0
        self.sense_range = 0
        self.output = False

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
        self.visa.write(f":SOUR:{self.source} {level:.4e}")
        pass

    def switch_output(self):
        self.output = not self.output
        self.visa.write(f":OUTP:STAT {self.output}")
        pass

