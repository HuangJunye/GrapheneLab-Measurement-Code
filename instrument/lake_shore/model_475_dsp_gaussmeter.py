import time

import utils.visa_subs as visa_subs


class LakeShore475DSPGaussmeter:
    def __init__(self, address):
        self.Name = "Lakeshore 475 DSP"
        self.Address = address
        self.Visa = VisaSubs.InitializeGPIB(address, 0, term_chars="\\n")
        # Other 6430 properties
        self.Output = False
        self.Source = "Field"
        self.Data = [0.0]
        self.Sense = []
        self.ColumnNames = "(Gauss)"
        self.DataColumn = 0
        self.SourceColumn = 1

    ######################################
    # Initializate as voltage source
    #######################################

    def InitializeGauss(self):
        self.Visa.write("UNIT 1")
        self.Visa.write("CMODE 1")
        self.Visa.write("CPARAM 15.0, 5.0, 3000.0, 40.0 ")
        pass

    ###########################################
    # Set the range and compliance
    #######################################

    def SetRangeCompliance(self, Range=105, Compliance=105):

        pass

    ##################################################
    # Read data
    ################################################

    def ReadData(self):
        Reply = self.Visa.ask(":RDGFIELD?")
        self.Data = [Reply]
        pass

    ##################################################
    # Set source
    ##################################################

    def SetOutput(self, Level):
        self.Visa.write("CSETP %.4e" % Level)
        time.sleep(4.0)
        pass

    #################################################
    # Switch the output
    ###############################################

    def SwitchOutput(self):
        self.Output = not self.Output
        pass

    #################################################
    # Configure a sweep
    ###############################################

    def ConfigureSweep(self, Start, Stop, Step, Soak=0):

        pass

    ###################################################
    # Begin sweep, this doesn't work so well, not recommended
    #################################################

    def RunConfiguredSweep(self):
        pass

    ###################################################
    # Print a description string
    ################################################

    def Description(self):
        DescriptionString = "Lake Shore Gaussmeter"
        for item in list(vars(self).items()):
            if item[0] == "Address":
                DescriptionString = ", ".join((DescriptionString, "%s = %.3f" % item))
            elif item[0] == "Source" or item[0] == "Sense" or item[0] == "Compliance":
                DescriptionString = ", ".join((DescriptionString, "%s = %s" % item))

        DescriptionString = "".join((DescriptionString, "\n"))
        return DescriptionString

    ############################################
    ######### Ramp the source to a final value
    #########################################

    def Ramp(self, VFinish):
        time1 = float(self.Visa.ask(":RDGFIELD?"))
        time2 = 4 * abs(VFinish - time1) / 50
        self.Visa.write("CSETP %.4e" % VFinish)
        print("Ramping to Field Value")
        time.sleep(time2)

        return