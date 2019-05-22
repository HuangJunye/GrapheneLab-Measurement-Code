import time

import numpy as np

import utils.measurement_subs as measurement_subs
import utils.socket_subs as socket_subs
from .do_fridge_sweep import do_fridge_sweep
from .do_device_sweep import do_device_sweep


def device_fridge_2d(
        graph_proc, rpg, data_file,
        read_inst, sweep_inst=[], set_inst=[],
        set_value=[], pre_value=[], finish_value=[],
        fridge_sweep='B', fridge_set=0.0,
        device_start=0.0, device_stop=1.0, device_step=0.1, device_finish=0.0,
        device_mid=[],
        fridge_start=0.0, fridge_stop=1.0, fridge_rate=0.1,
        delay=0, sample=1,
        timeout=-1, wait=0.0,
        comment='No comment!', network_dir='Z:\\DATA',
        persist=True, x_custom=[]
):
    """2D data acquisition either by sweeping a device parameter
    or by sweepng a fridge parameter
    The program decides which of these to do depending on if the
    the variable 'sweep_inst' is assigned.
    i.e. if 'sweep_inst' is assigned the device is swept and the
    fridge parameter is stepped.
    If the device is being swept the variable 'fridge_rate' is the size
    of successive steps of either T or B.
    If the fridge is being swept the first set_inst is stepped by the
    'device_step'

    For the case of successive B sweeps the fridge will be swept
    forwards and backwards
    e.g.	Vg = -60 V B = -9 --> +9 T
            Vg = -50 V B = +9 --> -9 T
            etc ...
    Note that in this case the first 'set_value' will be overwritten
    therefore a dummy e.g. 0.0 should be written in the case that there
    are additional set_inst
    """

    if sweep_inst:
        sweep_device = True
    else:
        sweep_device = False

    if fridge_sweep == 'B':
        b_sweep = True
    else:
        b_sweep = False

    if not finish_value:
        finish_value = list(set_value)

    # We step over the x variable and sweep over the y

    if sweep_device:
        x_vec = np.hstack((np.arange(fridge_start, fridge_stop, fridge_rate), fridge_stop))
        y_start = device_start
        y_stop = device_stop
        y_step = device_step
    else:
        x_vec = np.hstack((np.arange(device_start, device_stop, device_step), device_stop))
        y_start = fridge_start
        y_stop = fridge_stop
        y_step = fridge_rate

    if not not x_custom:
        x_vec = x_custom

        if sweep_device:
            y_len = len(measurement_subs.generate_device_sweep(
                device_start, device_stop, device_step, mid=device_mid))
        else:
            y_len = abs(y_start - y_stop) / y_step + 1

    num_of_inst = len(read_inst)
    plot_2d_window = [None] * num_of_inst
    view_box = [None] * num_of_inst
    image_view = [None] * num_of_inst
    z_array = [np.zeros((len(x_vec), y_len)) for i in range(num_of_inst)]

    if sweep_device:
        for i in range(num_of_inst):
            plot_2d_window[i] = rpg.QtGui.QMainWindow()
            plot_2d_window[i].resize(500, 500)
            view_box[i] = rpg.ViewBox(invertY=True)
            image_view[i] = rpg.ImageView(view=rpg.PlotItem(viewBox=view_box[i]))
            plot_2d_window[i].setCentralWidget(image_view[i])
            plot_2d_window[i].setWindowTitle('read_inst %d' % i)
            plot_2d_window[i].show()
            view_box[i].setAspectLocked(False)

            y_scale = y_step
            x_scale = (x_vec[-2] - x_vec[0]) / np.float(len(x_vec) - 1)

            for j in range(num_of_inst):
                image_view[j].setImage(z_array[j], scale=(x_scale, y_scale), pos=(x_vec[0], y_start))

    for i, v in enumerate(x_vec):

        if sweep_device:
            # sweep the device and fix T or B
            if b_sweep:

                data_list = do_device_sweep(
                    graph_proc, rpg, data_file,
                    sweep_inst, read_inst, set_inst=set_inst, set_value=set_value,
                    finish_value=finish_value, pre_value=pre_value, b_set=v, persist=False,
                    sweep_start=device_start, sweep_stop=device_stop, sweep_step=device_step,
                    sweep_finish=device_finish, sweep_mid=device_mid,
                    delay=delay, sample=sample, t_set=fridge_set,
                    timeout=timeout, wait=wait, return_data=True, make_plot=False,
                    comment=comment, network_dir=network_dir
                )
            else:
                data_list = do_device_sweep(
                    graph_proc, rpg, data_file,
                    sweep_inst, read_inst, set_inst=set_inst, set_value=set_value,
                    finish_value=finish_value, pre_value=pre_value, b_set=fridge_set, persist=True,
                    sweep_start=device_start, sweep_stop=device_stop, sweep_step=device_step,
                    sweep_mid=device_mid,
                    delay=delay, sample=sample, t_set=v,
                    timeout=timeout, wait=wait, return_data=True, make_plot=False,
                    comment=comment, network_dir=network_dir
                )

        else:

            set_value[0] = v
            if i == len(x_vec) - 1:
                finish_value[0] = 0.0
            else:
                finish_value[0] = x_vec[i + 1]

            # Fix the device and sweep T or B
            if b_sweep:
                data_list = do_fridge_sweep(
                    graph_proc, rpg, data_file,
                    read_inst, set_inst=set_inst, set_value=set_value,
                    finish_value=finish_value, pre_value=pre_value,
                    fridge_sweep='B', fridge_set=fridge_set,
                    sweep_start=fridge_start, sweep_stop=fridge_stop,
                    sweep_rate=fridge_rate, sweep_finish=fridge_stop,
                    persist=False,
                    delay=delay, sample=sample,
                    timeout=timeout, wait=wait,
                    return_data=True,
                    comment=comment, network_dir=network_dir)

                tmp_sweep = [fridge_start, fridge_stop]
                fridge_start = tmp_sweep[1]
                fridge_stop = tmp_sweep[0]

            else:
                data_list = do_fridge_sweep(
                    graph_proc, rpg, data_file,
                    read_inst, set_inst=set_inst, set_value=set_value,
                    finish_value=finish_value, pre_value=pre_value,
                    fridge_sweep='T', fridge_set=fridge_set,
                    sweep_start=fridge_start, sweep_stop=fridge_stop,
                    sweep_rate=fridge_rate, sweep_finish=fridge_stop,
                    persist=True,
                    delay=delay, sample=sample,
                    timeout=timeout, wait=wait,
                    return_data=True,
                    comment=comment, network_dir=network_dir)

                if sweep_device:
                    for j in range(num_of_inst):
                        z_array[j][i, :] = data_list[j + 1]
                        image_view[j].setImage(z_array[j], pos=(x_vec[0], y_start), scale=(x_scale, y_scale))

    m_client = socket_subs.SockClient('localhost', 18861)
    time.sleep(2)
    measurement_subs.socket_write(m_client, 'SET 0.0 0')
    time.sleep(2)
    m_client.close()

    time.sleep(2)

    return
