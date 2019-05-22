import asyncore
import time
from datetime import datetime

from instrument.oxford.mercury_ips import MercuryiPS


if __name__ == '__main__':

    # Initialize a daemon instance and runs startup codes
    magnet = MercuryiPS(address=11)
    magnet.on_start_up()
    # A flag to control the source behavior
    source_flag = False

    while 1:

        # Read the field and update the ready message
        magnet.read_field()

        # Push the reading to clients
        for j in magnet.server.handlers:
            j.to_send = f",{magnet.field:.5f} {magnet.ready:d}".encode()
            socket_msg = j.received_data
            if socket_msg and socket_msg != "-":
                magnet.read_msg(socket_msg)
        asyncore.loop(count=1, timeout=0.001)

        """ Now we should do stuff depending on the socket and what we 
        were doing before reading the socket
        In order of precedence
        1. We are locked, waiting for the switch heater -> delay any actions
        2. Go to the target field
        3. Go to the target heater
        4. ... just chill out! 
        """

        if magnet.lock:
            # Check if we can release the lock
            wait = datetime.now() - magnet.lock_time
            if wait.seconds >= 120.0:
                # Unlock
                magnet.lock = False
                print("Unlocking...")

        if not magnet.lock and not magnet.ready:
            """ The magnet is not locked and not ready
            We now try to go to the target_field and
            set the target_heater 
            """

            if not magnet.query_at_target():
                # System is not at the target field
                if not magnet.heater:
                    # The heater is not on
                    if magnet.check_switchable():
                        # The switch heater can be switched ON --> so switch it ON
                        magnet.set_heater(True)
                    # this will set the lock so we need to get out of the loop without doing anything else
                    else:
                        # The switch heater is not on
                        action = magnet.read_action()
                        if action != "RTOS":
                            # The source is not ramping --> Ramp it to the magnet current so it can be switched
                            magnet.set_source(magnet.magnet_current)
                else:
                    # The heater is on --> so go to the target
                    action = magnet.read_action()
                    set_current = magnet.read_numeric("CSET")
                    if action != "RTOS" or abs(set_current - magnet.target_field * magnet.a_to_b) > 0.005:
                        # The source is not ramping --> Ramp it to the magnet current so it can be switched
                        target_current = magnet.target_field * magnet.a_to_b
                        magnet.set_source(target_current)

            elif magnet.heater != magnet.target_heater:
                """ The magnet is at the target field but the heater is not in the target state
                There are two possibilities
                1. The heater is now ON --> turn it off and ramp the source down
                2. The heater is OFF --> Set the source to magnet current and turn it on 
                """
                if magnet.heater:
                    # The heater is on
                    if magnet.check_switchable():
                        magnet.set_heater(False)
                        # Set the source flag to tell the source to ramp to zero
                        source_flag = True

                else:
                    # The heater is not on
                    if magnet.check_switchable():
                        # The switch heater can be switched ON --> so switch it ON
                        magnet.set_heater(True)
                    # this will set the lock so we need to get out of the loop without doing anything else
                    else:
                        # The switch heater is not on
                        action = magnet.read_action()
                        if action != "RTOS":
                            # The source is not ramping --> Ramp it to the magnet current so it can be switched
                            magnet.set_source(magnet.magnet_current)

        if not magnet.lock and source_flag:
            # The source_flag has been set ramp the source to zero and unset the flag
            magnet.set_action("RTOZ")
            source_flag = False

        time.sleep(0.4)
