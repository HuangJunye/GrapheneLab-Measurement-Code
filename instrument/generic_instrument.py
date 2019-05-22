import utils.visa_subs as visa_subs


class Instrument:
    """Implement a generic instrument which does the following:

    description
    """

    def __init__(self, mode="gpib", address=0):
        self.name = "Instrument Name"
        self.address = address
        self.visa = visa_subs.initialize(mode=mode, address=address)

    def description(self):
        """ Print a description string to data file"""

        return f"{self.name}: address={self.address}"
