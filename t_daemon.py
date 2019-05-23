import asyncore
import time
from datetime import datetime

from daemon.TControl import TControl


# calibration parameters for temperature sensors
calibrations = {
    'S0703': [7318.782092, -13274.53584, 10276.68481, -4398.202411, 1123.561007, -171.3095557, 14.43456504, -0.518534965],
    'S0914': [
        5795.148097375, -11068.032226486, 9072.821104899, -4133.466851312,
        1129.955799406, -185.318021359, 16.881907269, -0.658939155
    ],
    'MATS56': [19.68045382, -20.19660902, 10.13318296, -2.742724207, 0.385556989, -0.022178276],
    'CERNOX': [4.62153, -1.17709, -0.222229, -2.3114e-11]
}


if __name__ == '__main__':

    # Initialize a PID controller

    control = TControl()

    control.pico.set_pico_channel(5)  # ch5 for CERNOX. Do not use below 1K
    control.pico.sensor = 'CERNOX'

    # Main loop
    control.tcs.read_current()

    while True:

        # Read the picowatt and calculate the temperature
        control.pico.read_resistance()
        control.calc_temperature(calibrations[control.pico.sensor])
        control.update_at_set()
        control.update_status_msg()

        # Push the reading to clients
        for j in control.server.handlers:
            j.to_send = f'{control.temperature:.3f} {control.status_msg:d}'.encode()
            socket_msg = j.received_data
            if socket_msg:
                control.read_msg(socket_msg)
        asyncore.loop(count=1, timeout=0.001)

        # if we are sweeping we do some things specific to the sweep
        if control.sweep_mode:
            control.sweep_control()

        # check if we should send an update
        update_time = datetime.now() - control.last_status_time
        if update_time.seconds/60.0 >= control.status_interval:
            control.print_status()

        new_pid = control.pid.update(control.temperature)
        try:
            control.pid_output = int(new_pid)
        except:
            control.pid_output = 0
            pass

        if control.pid_output < 0:
            control.pid_output = 0
        elif control.pid_output > control.tcs.max_current:
            control.pid_output = control.tcs.max_current

        if control.pid_output > 0 and control.tcs.heater[2] == 0:
            # status is go to set and heater is off --> turn it on
            control.tcs.set_current(2, control.pid_output)
            control.tcs.switch_heater(2)
            control.tcs.read_current()
        elif control.pid_output <= 0 and control.tcs.heater[2] == 1:
            # status is go to set and heater is off --> turn it on
            control.tcs.switch_heater(2)
            control.tcs.set_current(2, 0)
            control.tcs.read_current()
        elif control.pid_output >= 0 and control.tcs.heater[2] == 1:
            control.tcs.set_current(2, control.pid_output)
            control.tcs.tcs_current[2] = control.pid_output

        time.sleep(0.5)

    control.tcs_visa.close()
