import time

import utils.visa_subs as visa_subs


class LS475Gaussmeter:
    def __init__(self, address):
        self.name = "Lake Shore 475 DSP"
        self.address = address
        self.visa = visa_subs.initialize_gpib(address, 0)
        self.output = False
        self.source = "Field"
        self.data = [0.0]
        self.sense = []
        self.column_names = "(Gauss)"
        self.data_column = 0
        self.source_column = 1

    ######################################
    # Initializate as voltage source
    #######################################

    def initialize_gauss(self):
        self.visa.write("UNIT 1")
        self.visa.write("CMODE 1")
        self.visa.write("CPARAM 15.0, 5.0, 3000.0, 40.0 ")
        pass

    ##################################################
    # Read data
    ################################################

    def read_data(self):
        reply = self.visa.ask(":RDGFIELD?")
        self.data = [reply]
        pass

    ##################################################
    # Set source
    ##################################################

    def set_output(self, level):
        self.visa.write("CSETP %.4e" % level)
        time.sleep(4.0)
        pass

    #################################################
    # Switch the output
    ###############################################

    def switch_ouptput(self):
        self.output = not self.output
        pass

    ###################################################
    # Print a description string
    ################################################

    def description(self):
        description_string = "Lake Shore Gaussmeter"
        for item in list(vars(self).items()):
            if item[0] == "address":
                description_string = ", ".join((description_string, "%s = %.3f" % item))
            elif item[0] == "source" or item[0] == "sense" or item[0] == "Compliance":
                description_string = ", ".join((description_string, "%s = %s" % item))

        description_string = "".join((description_string, "\n"))
        return description_string

    ############################################
    # ramp the source to a final value
    #########################################

    def ramp(self, v_finish):
        time1 = float(self.visa.ask(":RDGFIELD?"))
        time2 = 4 * abs(v_finish - time1) / 50
        self.visa.write("CSETP %.4e" % v_finish)
        print("Ramping to Field Value")
        time.sleep(time2)

        return
