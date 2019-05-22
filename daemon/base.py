import utils.socket_subs as socket_subs
import utils.visa_subs as visa_subs


class Control:
    """Base class for TControl and MControl"""

    def __init__(self, socket_address):
        self.socket_address = socket_address
        self.server = socket_subs.SockServer(self.socket_address)



