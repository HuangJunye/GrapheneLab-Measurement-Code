import time

import utils.visa_subs as visa_subs


class K2182:
    def __init__(self, address):
        self.name = "Keithley 2182A"
        self.address = address
        self.visa = visa_subs.initialize_gpib(address, 0)

    ######################################
    # Initializate as voltage source
    #######################################

    def initialize_voltage(
            self, channel=1, a_cal=False, relative=False, a_filt=False,
            d_filt=True, count=5, sense_range=1., auto_range=False
    ):

        self.column_names = "V (V)"
        self.data = [0.0]
        self.data_column = 0
        self.sense = "VOLT"
        # Special variables for 2182
        self.channel = channel
        self.relative = relative
        self.a_filt = a_filt
        self.d_filt = d_filt
        self.count = count
        self.sense_range = sense_range
        self.auto_range = auto_range

        # A bunch of commands to configure the 2182
        self.visa.write("*RST")
        time.sleep(.1)
        self.visa.write(":SENS:FUNC \'VOLT\'")
        self.visa.write(":SENS:CHAN %d" % channel)

        if a_cal:
            self.visa.write(":CAL:UNPR:ACAL:INIT")
            time.sleep(1.0)
            reply = self.visa.query(":CAL:UNPR:ACAL:TEMP?")
            time.sleep(10.)
            self.visa.write(":CAL:UNPR:ACAL:DONE")

        # Disable concurrent mode, measure I and V (not R)
        self.set_sense_range(sense_range=sense_range, auto_range=auto_range)

        # Set some filters
        if a_filt:
            self.visa.write(":SENS:VOLT:LPAS 1")
        else:
            self.visa.write(":SENS:VOLT:LPAS 0")

        if d_filt:
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

    ###########################################
    # Set the range and compliance
    #######################################

    def set_sense_range(self, sense_range=0.1, auto_range=False):

        if auto_range:
            self.auto_range = True
            self.visa.write("".join((":SENS:", self.sense, ":RANG:AUTO 1")))
        else:
            self.sense_range = sense_range
            self.auto_range = False
            self.visa.write("".join((":SENS:", self.sense, ":RANG ", "%.2e" % sense_range)))

        pass

    ##################################################
    # Read data
    ################################################

    def read_data(self):
        reply = self.visa.query(":READ?")
        self.data = [float(reply)]
        pass

    ###############################################
    # Print a description string
    ################################################

    def description(self):
        description_string = "Keithley2182"
        for item in list(vars(self).items()):
            if item[0] == "address":
                description_string = ", ".join((description_string, "%s = %.3f" % item))
            elif item[0] == "sense" or item[0] == "sense_range" or item[0] == "relative" or item[0] == "relative_value":
                description_string = ", ".join((description_string, "%s = %s" % item))

        description_string = "".join((description_string, "\n"))
        return description_string