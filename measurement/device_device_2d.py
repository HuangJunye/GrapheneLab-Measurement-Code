import time

import numpy as np

import utils.measurement_subs as measurement_subs
import utils.socket_subs as socket_subs
from .do_device_sweep import do_device_sweep


def device_device_2d(
        graph_proc, rpg, data_file,
        read_inst, sweep_inst=[], step_inst=[],
        set_inst=[], set_value=[], pre_value=[], finish_value=[],
        fridge_set_b=0.0, fridge_set_t=0.0,
        sweep_start=0.0, sweep_stop=1.0, sweep_step=0.1, sweep_finish=0.0, sweep_mid=[],
        step_start=0.0, step_stop=1.0, step_step=0.1, step_finish=0.0,
        delay=0, sample=1, make_plot=False,
        timeout=-1, wait=0.0,
        comment="No comment!", network_dir="Z:\\DATA",
        persist=True, x_custom=[], ignore_magnet=False
):
    """SWEEP two device parameters
    e.g. backgate bias, one is stepped, the other is swept
    """

    if not finish_value:
        finish_value = list(set_value)

    # We step over the x variable and sweep over the y

    set_inst_list = list(set_inst)
    set_inst_list.append(step_inst)

    # X is the step axis
    # Y is the sweep axis
    x_vec = np.hstack((np.arange(step_start, step_stop + step_step, step_step), step_finish))
    y_vec = measurement_subs.generate_device_sweep(sweep_start, sweep_stop, sweep_step, mid=sweep_mid)
    y_max = np.max(y_vec)
    y_min = np.min(y_vec)

    if x_custom:
        x_vec = x_custom

    num_of_inst = len(read_inst)
    plot_2d_window = [None] * num_of_inst
    view_box = [None] * num_of_inst
    image_view = [None] * num_of_inst
    z_array = [np.zeros((len(x_vec) - 1, len(y_vec))) for i in range(num_of_inst)]

    for i in range(num_of_inst):
        plot_2d_window[i] = rpg.QtGui.QMainWindow()
        plot_2d_window[i].resize(800, 800)
        view_box[i] = rpg.ViewBox()
        view_box[i].enableAutoRange()
        image_view[i] = rpg.ImageView(view=rpg.PlotItem(viewBox=view_box[i]))
        plot_2d_window[i].setCentralWidget(image_view[i])
        plot_2d_window[i].setWindowTitle("read_inst %d" % i)
        plot_2d_window[i].show()
        view_box[i].invertY(True)
        view_box[i].setAspectLocked(False)

    y_scale = (y_max - y_min) / np.float(len(y_vec))
    x_scale = (x_vec[-2] - x_vec[0]) / np.float(len(x_vec) - 1)

    # print x_scale
    # print y_scale
    for j in range(num_of_inst):
        image_view[j].setImage(z_array[j], pos=(x_vec[0], y_min), scale=(x_scale, y_scale))

    sets = [None] * (len(set_value) + 1)
    if len(set_value) > 0:
        sets[:-1] = set_value[:]
    finishs = [None] * (len(finish_value) + 1)
    if len(finish_value) > 0:
        finishs[:-1] = finish_value[:]

    for i, v in enumerate(x_vec[:-1]):
        sets[-1] = v
        finishs[-1] = x_vec[i + 1]

        data_list = do_device_sweep(
            graph_proc, rpg, data_file,
            sweep_inst, read_inst, set_inst=set_inst_list, set_value=sets,
            finish_value=finishs,
            b_set=fridge_set_b, t_set=fridge_set_t, persist=persist,
            sweep_start=sweep_start, sweep_stop=sweep_stop,
            sweep_step=sweep_step, sweep_finish=sweep_finish,
            sweep_mid=sweep_mid,
            delay=delay, sample=sample,
            timeout=timeout, wait=wait,
            return_data=True, make_plot=make_plot,
            comment=comment, network_dir=network_dir,
            ignore_magnet=ignore_magnet
        )

        for j in range(num_of_inst):
            z_array[j][i, :] = data_list[j + 1]
            image_view[j].setImage(z_array[j], pos=(x_vec[0], y_min), scale=(x_scale, y_scale))

    m_client = socket_subs.SockClient('localhost', 18861)
    time.sleep(2)
    measurement_subs.socket_write(m_client, "SET 0.0 0")
    time.sleep(2)
    m_client.close()

    time.sleep(2)

    return
