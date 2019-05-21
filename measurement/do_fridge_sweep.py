import shutil
import time
from datetime import datetime
from sys import exit

import numpy as np

import utils.measurement_subs as measurement_subs


def do_fridge_sweep(
        graph_proc, rpg, data_file, read_inst,
        set_inst=[], set_value=[], pre_value=[], finish_value=[],
        fridge_sweep="B", fridge_set=0.0,
        sweep_start=0.0, sweep_stop=1.0, sweep_rate=1.0, sweep_finish=0.0,  # Either T/min or mK/min
        persist=False,  # Magnet final state
        delay=0.0, sample=1,
        timeout=-1, wait=0.5, max_over_time=5,
        return_data=False, socket_data_number=2,
        comment="No comment!", network_dir="Z:\\DATA",
        ignore_magnet=False
):
    """sweep T or B"""

    # Bind sockets
    m_client, m_socket, t_client, t_socket = measurement_subs.initialize_sockets()

    if fridge_sweep == "B":
        b_sweep = True
        if ignore_magnet:
            print("Error cannot ignore magnet for BSweep! Exiting!")
            exit(0)
    else:
        b_sweep = False

    num_of_inst = len(read_inst)

    set_time = datetime.now()

    if b_sweep:
        b_set = [sweep_start, sweep_stop]
        t_set = [fridge_set]
        start_persist = False
    else:
        b_set = [fridge_set]
        t_set = [sweep_start, sweep_stop]
        start_persist = persist

    # Tell the magnet daemon to go to the initial field and set the temperature
    msg = " ".join(("SET", "%.2f" % t_set[0]))
    measurement_subs.socket_write(t_client, msg)
    print("Wrote message to temperature socket \"%s\"" % msg)

    msg = " ".join(("SET", "%.4f" % b_set[0], "%d" % int(not start_persist)))
    measurement_subs.socket_write(m_client, msg)
    print("Wrote message to Magnet socket \"%s\"" % msg)
    time.sleep(5)

    # give precedence to the magnet and wait for the timeout
    t_socket = measurement_subs.socket_read(t_client, t_socket)
    m_socket = measurement_subs.socket_read(m_client, m_socket)
    if not ignore_magnet:
        while m_socket[1] != 1:
            print("Waiting for magnet!")
            time.sleep(15)
            t_socket = measurement_subs.socket_read(t_client, t_socket)
            m_socket = measurement_subs.socket_read(m_client, m_socket)

    now_time = datetime.now()
    remaining = timeout * 60.0 - float((now_time - set_time).seconds)
    while (t_socket[1] != 1) and (remaining > 0):
        now_time = datetime.now()
        remaining = timeout * 60.0 - float((now_time - set_time).seconds)
        print("Waiting for temperature ... time remaining = %.2f minutes" % (remaining / 60.0))
        t_socket = measurement_subs.socket_read(t_client, t_socket)
        m_socket = measurement_subs.socket_read(m_client, m_socket)
        time.sleep(15)

    # Setup L plot windows
    graph_window = rpg.GraphicsWindow(title="Fridge sweep...")
    plot_data = graph_proc.transfer([])
    graph_window.resize(500, 150 * num_of_inst)
    plot = []
    curve = []
    for i in range(num_of_inst):
        plot.append(graph_window.addPlot())
        curve.append(plot[i].plot(pen='y'))
        graph_window.nextRow()

    if set_inst:
        for set_val in [pre_value, set_value]:
            if set_val:
                if len(set_inst) != len(set_val):
                    if len(set_val) > len(set_inst):
                        set_val = set_val[0:len(set_inst)]
                    else:
                        set_val = set_val + [0] * (len(set_inst) - len(set_val))
                for i, v in enumerate(set_inst):
                    print("Ramping %s to %.2e" % (v.name, set_val[i]))
                    v.ramp(set_val[i])

    if wait >= 0.0:
        print("Waiting %.2f minute!" % wait)
        wait_time = datetime.now()
        remaining = wait * 60.0
        while remaining > 0:
            now_time = datetime.now()
            remaining = wait * 60.0 - float((now_time - wait_time).seconds)
            print("Waiting ... time remaining = %.2f minutes" % (remaining / 60.0))
            t_socket = measurement_subs.socket_read(t_client, t_socket)
            m_socket = measurement_subs.socket_read(m_client, m_socket)
            time.sleep(15)
    print("Starting measurement!")

    start_time = datetime.now()

    writer, file_path, net_dir = measurement_subs.open_csv_file(
        data_file, start_time, read_inst, set_inst=set_inst,
        comment=comment, network_dir=network_dir
    )

    # This is the main measurement loop

    start_column, data_vector = measurement_subs.generate_data_vector(
        socket_data_number, read_inst, sample, set_value=set_value
    )

    if b_sweep:
        msg = " ".join(("SWP", "%.4f" % b_set[1], "%.4f" % sweep_rate, "%d" % int(not persist)))
        measurement_subs.socket_write(m_client, msg)
        print("Wrote message to magnet socket \"%s\"" % msg)
    else:
        msg = " ".join(("SWP", "%.4f" % t_set[1], "%.4f" % sweep_rate, "%.2f" % max_over_time))
        measurement_subs.socket_write(t_client, msg)
        print("Wrote message to temperature socket \"%s\"" % msg)

    t_socket = measurement_subs.socket_read(t_client, t_socket)
    m_socket = measurement_subs.socket_read(m_client, m_socket)
    if b_sweep:
        fridge_status = m_socket[-1]
    else:
        fridge_status = t_socket[-1]

    while fridge_status != 0:
        time.sleep(1)
        # print fridge_status
        t_socket = measurement_subs.socket_read(t_client, t_socket)
        m_socket = measurement_subs.socket_read(m_client, m_socket)
        if b_sweep:
            fridge_status = m_socket[-1]
        else:
            fridge_status = t_socket[-1]

    sweep_time_length = abs(sweep_start - sweep_stop) / sweep_rate  # In minutes
    sweep_time_length = sweep_time_length + max_over_time
    # print sweep_time_length
    start_time = datetime.now()
    sweep_timeout = False

    # print Field
    while fridge_status == 0 and (not sweep_timeout):

        t_socket = measurement_subs.socket_read(t_client, t_socket)
        m_socket = measurement_subs.socket_read(m_client, m_socket)
        if b_sweep:
            fridge_status = m_socket[-1]
        else:
            fridge_status = t_socket[-1]

        data_vector[:, 0] = m_socket[0]
        data_vector[:, 1:socket_data_number] = t_socket[0]

        for j in range(sample):

            for i, v in enumerate(read_inst):
                v.read_data()
                data_vector[j, start_column[i]:start_column[i + 1]] = v.data

            # Sleep
            time.sleep(delay)

        # Save the data
        for j in range(sample):
            writer.writerow(data_vector[j, :])

        to_plot = np.empty((num_of_inst + 1))
        if b_sweep:
            to_plot[0] = data_vector[-1, 0]
        else:
            to_plot[0] = data_vector[-1, 1]
        for j in range(num_of_inst):
            to_plot[j + 1] = data_vector[-1, start_column[j] + read_inst[j].data_column]

        # Pass data to the plots
        plot_data.extend(to_plot, _callSync="off")
        for j in range(num_of_inst):
            curve[j].setData(x=plot_data[0::(num_of_inst + 1)], y=plot_data[j + 1::(num_of_inst + 1)], _callSync="off")

        if not b_sweep:
            d_temp = datetime.now() - start_time
            d_temp_min = d_temp.seconds / 60.0
            sweep_timeout = d_temp_min > sweep_time_length
        else:
            sweep_timeout = False

    # Loop is finished
    if set_inst:
        if len(finish_value) != len(set_inst):
            if len(finish_value) > len(set_inst):
                finish_value = finish_value[0:len(set_inst)]
            else:
                finish_value = finish_value + set_value[len(finish_value):len(set_inst)]
        for i, v in enumerate(set_inst):
            print("Ramping %s to %.2e" % (v.name, finish_value[i]))
            v.ramp(finish_value[i])

    if return_data:
        data_list = [None] * (num_of_inst + 1)
        data_list[0] = plot_data[0::num_of_inst + 1]
        for i in range(1, num_of_inst + 1):
            data_list[i] = plot_data[i::num_of_inst + 1]

    if b_sweep:
        msg = " ".join(("SET", "%.4f" % sweep_finish, "%d" % int(not persist)))
        measurement_subs.socket_write(m_client, msg)
        print("Wrote message to Magnet socket \"%s\"" % msg)
    else:
        msg = " ".join(("SET", "%.2f" % sweep_finish))
        measurement_subs.socket_write(t_client, msg)
        print("Wrote message to temperature socket \"%s\"" % msg)

    # Copy the file to the network
    time.sleep(5)
    try:
        shutil.copy(file_path, net_dir)
    except IOError:
        pass

    # We are finished, now ramp the Keithley to the finish voltage
    graph_window.close()
    m_client.close()
    t_client.close()

    if return_data:
        return data_list
    else:
        return
