from .k_meter import Keithley


class K2400(Keithley):

    def __init__(self, address):
        super().__init__(address)
        self.name = "Keithley 2400"
