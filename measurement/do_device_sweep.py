import shutil
import time
from datetime import datetime

import numpy as np

import utils.measurement_subs as measurement_subs


def do_device_sweep(
        graph_proc, rpg, data_file, sweep_inst, read_inst,
        set_inst=[], set_value=[], finish_value=[], pre_value=[],
        b_set=0., persist=True, ignore_magnet=False,
        sweep_start=0., sweep_stop=0., sweep_step=1.,
        sweep_finish=0.0, sweep_mid=[],
        delay=0., sample=1,
        t_set=-1,
        timeout=-1, wait=0.5,
        return_data=False, make_plot=True,
        socket_data_number=2,  # 5 for 9T, 2 for Dilution fridge
        comment="No comment!", network_dir="Z:\\DATA"
):
    """Device sweep"""

    # Bind sockets
    m_client, m_socket, t_client, t_socket = measurement_subs.initialize_sockets()

    num_of_inst = len(read_inst)

    # set the sweep voltages

    sweep = measurement_subs.generate_device_sweep(sweep_start, sweep_stop, sweep_step, mid=sweep_mid)
    set_time = datetime.now()

    # Go to the set temperature and magnetic field and finish in persistent mode
    if t_set > 0:
        msg = " ".join(("SET", "%.2f" % t_set))
        measurement_subs.socket_write(t_client, msg)
        print("Wrote message to temperature socket \"%s\"" % msg)
    if not ignore_magnet:
        msg = " ".join(("SET", "%.4f" % b_set, "%d" % int(not persist)))
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
    if make_plot:
        graph_window = rpg.GraphicsWindow(title="Device sweep...")
        graph_window.resize(1000, 800)
        plot = [None] * num_of_inst
        curve = [None] * num_of_inst
        for i in range(num_of_inst):
            plot[i] = graph_window.addPlot()
            curve[i] = plot[i].plot(pen='y')
            if i < num_of_inst - 1:
                graph_window.nextRow()

    if return_data or make_plot:
        plot_data = graph_proc.transfer([])

    if set_inst:
        for set_val in [pre_value, set_value]:
            if set_val:
                "Pre and set ramps"
                if len(set_inst) != len(set_val):
                    if len(set_val) > len(set_inst):
                        set_val = set_val[0:len(set_inst)]
                    else:
                        set_val = set_val + [0] * (len(set_inst) - len(set_val))
                for i, v in enumerate(set_inst):
                    print("Ramping %s to %.2e" % (v.name, set_val[i]))
                    v.ramp(set_val[i])

    if sweep_start != 0:
        sweep_inst.ramp(sweep_start)
    else:
        sweep_inst.set_output(0)

    if not sweep_inst.output:
        sweep_inst.switch_output()

    sweep_inst.read_data()

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

    writer, file_path, net_dir, csv_file = measurement_subs.open_csv_file(
        data_file, start_time, read_inst, sweep_inst=[sweep_inst],
        set_inst=set_inst, comment=comment, network_dir=network_dir
    )

    # This is the main measurement loop
    start_column, data_vector = measurement_subs.generate_data_vector(
        socket_data_number, read_inst, sample,
        sweep_inst=True, set_value=set_value
    )

    for i, v in enumerate(sweep):
        sweep_inst.set_output(v)

        t_socket = measurement_subs.socket_read(t_client, t_socket)
        m_socket = measurement_subs.socket_read(m_client, m_socket)

        data_vector[:, 0] = m_socket[0]
        data_vector[:, 1:socket_data_number] = t_socket[0]
        data_vector[:, socket_data_number] = v

        for j in range(sample):

            for i, v in enumerate(read_inst):
                v.read_data()
                data_vector[j, start_column[i]:start_column[i + 1]] = v.data

            # Sleep
            if delay >= 0.0:
                time.sleep(delay)

        # Save the data
        for j in range(sample):
            writer.writerow(data_vector[j, :])
            csv_file.flush()

        # Package the data and send it for plotting

        if make_plot or return_data:
            to_plot = np.empty((num_of_inst + 1))
            to_plot[0] = data_vector[-1, socket_data_number]
            for j in range(num_of_inst):
                to_plot[j + 1] = data_vector[-1, start_column[j] + read_inst[j].data_column]

            # Pass data to the plots
            plot_data.extend(to_plot, _callSync="off")
        if make_plot:
            for j in range(num_of_inst):
                curve[j].setData(x=plot_data[0::(num_of_inst + 1)], y=plot_data[j + 1::(num_of_inst + 1)],
                                 _callSync="off")

    sweep_inst.ramp(sweep_finish)

    # if the finish is zero switch it off
    if sweep_finish == 0.0:
        sweep_inst.switch_output()

    if set_inst:
        if len(finish_value) != len(set_inst):
            print("Warning: len(set_inst) != len(finish_value)")
            # print set_inst, finish_value
            if len(finish_value) > len(set_inst):
                finish_value = finish_value[0:len(set_inst)]
            else:
                finish_value = finish_value + set_value[len(finish_value):len(set_inst)]
        # Final ramps
        for i, v in enumerate(set_inst):
            print("Ramping %s to %.2e" % (v.name, finish_value[i]))
            v.ramp(finish_value[i])

    if return_data:
        data_list = [None] * (num_of_inst + 1)
        data_list[0] = plot_data[0::num_of_inst + 1]
        for i in range(1, num_of_inst + 1):
            data_list[i] = plot_data[i::num_of_inst + 1]

    # Copy the file to the network
    time.sleep(5)
    try:
        shutil.copy(file_path, net_dir)
    except IOError:
        pass

    m_client.close()
    t_client.close()

    if return_data:
        return data_list
    else:
        return
