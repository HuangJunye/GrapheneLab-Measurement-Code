import asyncore
import re as re
import time
from datetime import datetime

import numpy as np

import utils.socket_subs as socket_subs
import utils.visa_subs as visa_subs


class MControl:
    """
    Initialization call, initialize visas for the Mercury IPS and perform some startup
    queries on the instrument
    server, server always runs at 18861
    Important parameters
    field
    heater
    a_to_b (amps to tesla)
    lock - lock the deamon from performing actions, typically if the heater has just been
    switched
    The target current either as part of a sweep or going to a fixed value
    Mode: Sweep or Set (including set to zero)
    TODO: modify codes to allow X, Y Z axes
    """

    def __init__(self):
        # Connect visa to the magnet
        self.visa = visa_subs.initialize_serial("ASRL11::INSTR")
        # Add Timeout to 200s
        self.visa.timeout = 200000
        # Open the socket
        address = ('localhost', 18861)
        self.server = socket_subs.SockServer(address)

        # Define some important parameters for the magnet
        self.field = 0.0
        self.source_current = 0.0
        self.heater = False
        self.magnet_current = 0.0
        self.a_to_b = 0.0
        self.rate = 2.19
        self.max_rate = 2.19
        self.current_limit = 0.0

        # Set up the lock for the switch heater
        self.lock = False
        self.lock_time = 0.0

        # The magnet actions are defined by the following parameters.
        # The daemon tries to reach the target field and then put the heater into the target state
        self.target_field = 0.0
        self.target_heater = False

        self.sweep_now = False
        self.ready = 1  # ready message which is also broadcast to the listener

        return

    def magnet_read_numeric(self, command):
        """Function to read one of the numeric signals"""

        # Form the query string (Now only for GRPZ)
        query = "".join(("READ:DEV:GRPZ:PSU:SIG:", command))
        reply = self.visa.query(query)

        # Find the useful part of the response
        answer = str.rsplit(reply, ":", 1)[1]

        # Some regex to get rid of the appended units
        answer = re.split("[a-zA-Z]", answer, 1)[0]
        answer = float(answer)

        return answer

    def magnet_read_field(self):
        """Function to read the field in Tesla specifically"""

        # Form the query string (Now only for GRPZ)
        if self.heater:
            query = "READ:DEV:GRPZ:PSU:SIG:FLD"
        else:
            # For some reason the command PFLD doesn't work
            query = "READ:DEV:GRPZ:PSU:SIG:PCUR"

        reply = self.visa.query(query)

        # Find the useful part of the response
        answer = str.rsplit(reply, ":", 1)[1]
        # Some regex to get rid of the appended units
        answer = re.split("[a-zA-Z]", answer, 1)[0]
        answer = float(answer)

        if self.heater:
            self.source_current = answer * self.a_to_b
            self.magnet_current = self.source_current
        else:
            self.magnet_current = answer
            answer = answer / self.a_to_b

        self.field = answer

        return

    def magnet_read_conf_numeric(self, command):
        """Read one of the numeric configs"""

        # Form the query string (Now only for GRPZ)
        query = "".join(("READ:DEV:GRPZ:PSU:", command))
        reply = self.visa.query(query)

        # Find the useful part of the response
        answer = str.rsplit(reply, ":", 1)[1]

        # Some regex to get rid of the appended units
        answer = re.split("[a-zA-Z]", answer, 1)[0]
        answer = float(answer)

        return answer

    def magnet_set_numeric(self, command, value):
        """Function to set one of the numeric signals"""

        # Form the query string (Now only for GRPZ)
        write_command = "SET:DEV:GRPZ:PSU:SIG:%s:%.4f" % (command, value)
        reply = self.visa.query(write_command)

        answer = str.rsplit(reply, ":", 1)[1]
        if answer == "VALID":
            valid = 1
        elif answer == "INVALID":
            valid = 0
        else:
            valid = -1

        return valid

    def magnet_read_heater(self):
        """Function to read the switch heater state returns boolean"""

        reply = self.visa.query("READ:DEV:GRPZ:PSU:SIG:SWHT")
        answer = str.rsplit(reply, ":", 1)[1]

        if answer == "ON":
            valid = 1
            self.heater = True
        elif answer == "OFF":
            valid = 0
            self.heater = False
        else:
            valid = -1

        return valid

    def magnet_set_heater(self, state):
        """Turn the switch heater ON (1) or OFF (0)"""

        self.magnet_set_action("HOLD")
        heater_before = self.heater
        if state:
            reply = self.visa.query("SET:DEV:GRPZ:PSU:SIG:SWHT:ON")
        else:
            reply = self.visa.query("SET:DEV:GRPZ:PSU:SIG:SWHT:OFF")

        answer = str.rsplit(reply, ":", 1)[1]

        valid = 0
        if answer == "VALID":
            valid = 1
        elif answer == "INVALID":
            valid = 0
        time.sleep(5.)
        self.magnet_read_heater()
        heater_after = self.heater
        if heater_after != heater_before:
            print("heater switched ... locking for 2 minutes...")
            self.lock = True
            self.lock_time = datetime.now()

        return valid

    def magnet_read_action(self):
        """ Read the current magnet action e.g. HOLD, RTOZ etc."""

        reply = self.visa.query("READ:DEV:GRPZ:PSU:ACTN")
        answer = str.rsplit(reply, ":", 1)[1]
        return answer

    def magnet_set_action(self, command):
        """Set the action for the magnet"""

        reply = self.visa.query("".join(("SET:DEV:GRPZ:PSU:ACTN:", command)))

        answer = str.rsplit(reply, ":", 1)[1]
        if answer == "VALID":
            valid = 1
        elif answer == "INVALID":
            valid = 0
        else:
            valid = -1

        return valid

    def magnet_check_switchable(self):
        """Check if it is safe to switch the switch heater"""

        self.magnet_read_heater()
        self.source_current = self.magnet_read_numeric("CURR")
        self.magnet_current = self.magnet_read_numeric("PCUR")

        switchable = False
        if self.heater:
            switchable = True
        elif abs(self.source_current - self.magnet_current) <= 0.1:
            switchable = True
        elif self.heater == 0 and abs(self.source_current - self.magnet_current) >= 0.1:
            switchable = False

        action = self.magnet_read_action()
        if action == "RTOZ" or action == "RTOS":
            switchable = False

        return switchable

    def magnet_on_start_up(self):
        """On start get parameters"""

        # Check the heater
        self.magnet_read_heater()
        self.a_to_b = self.magnet_read_conf_numeric("ATOB")

        # Take care of the field sourcecurrent and magnetcurrent
        self.magnet_read_field()
        self.current_limit = self.magnet_read_conf_numeric("CLIM")
        self.target_field = self.field
        self.target_heater = self.heater

        if self.heater:
            heater_string = "ON"
        else:
            heater_string = "OFF"

        print(
            f"Connected to magnet... heater is {heater_string}, field is {self.field:.4f}, "
            f"Magnet conversion = {self.a_to_b:.4f} A/T, Maximum current = {self.current_limit:.3f}"
        )

        return

    def set_source(self, new_set):
        """Set the leads current, ignore the switch heater state, busy etc"""

        if abs(new_set) <= self.current_limit:
            c_set = new_set
        else:
            c_set = np.copysign(self.current_limit, new_set)

        self.magnet_set_numeric("CSET", c_set)

        # If the heater is on set the rate
        if self.heater:
            if self.rate >= self.max_rate:
                self.rate = self.max_rate
            self.magnet_set_numeric("RCST", self.rate)

        set_rate = self.magnet_read_numeric("RCST")
        self.magnet_set_action("RTOS")
        print(f"Ramping source to {c_set:.4f} A at {set_rate:.4f} A/m\n")
        return

    def query_at_target(self):

        if abs(self.target_field) < 1.0:
            if abs(self.field - self.target_field) < 0.0003:
                at_target = True
            else:
                at_target = False
        else:
            if abs((self.field - self.target_field) / self.target_field) <= 0.00015:
                at_target = True
            else:
                at_target = False
        return at_target

    def update_ready(self):

        if self.query_at_target() and (self.heater == self.target_heater):
            # The system is at target and ready
            self.ready = 1
        else:
            # Idle
            self.ready = 0
        return

    def read_msg(self, msg):
        """Interpret a message from the socket
        There are two possible actionable calls to the daemon
        1. "SET" go to set point
        2. "SWP" sweep from the current field to a target
        """
        msg = msg.decode()  # change in python 3
        msg = msg.split(" ")
        if msg[0] == "SET":
            # Set message has form "SET target_field target_heater"
            try:
                new_field = float(msg[1])
                new_heater = int(msg[2])
                new_heater = bool(new_heater)
                if (new_field != self.target_field) or (new_heater != self.target_heater):
                    self.target_field = new_field
                    self.target_heater = new_heater
                    self.rate = self.max_rate
                    self.update_ready()
                    if not self.ready:
                        print(f"Got new set point from socket {self.target_field:.4f} T")
            except:
                pass

        if msg[0] == "SWP":
            # Message has form "SWP target_field rate target_heater"
            # print msg
            try:
                new_field = float(msg[1])
                new_heater = int(msg[3])
                new_heater = bool(new_heater)
                self.rate = float(msg[2]) * self.a_to_b
                if (new_field != self.target_field) or (new_heater != self.target_heater):
                    self.target_field = new_field
                    self.target_heater = new_heater
                    self.update_ready()
                    if not self.ready:
                        print(
                            f"Got new sweep point from socket to {self.target_field:.4f} T"
                            f" at {self.rate / self.a_to_b:.4f} T/min"
                        )
            except:
                pass

            return