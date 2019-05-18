#!/usr/bin/python
# -*- coding: utf-8 -*-

"""

Sub programs for doing the measurements

original author : Eoin O'Farrell
current author : Huang Junye
last edited : Apr 2019

Explantion:

	There are 3 variables in our instrument:
	1 Temperature
	2 Field
	3 Device parameter; e.g. Backgate V, Topgate V, Current, Angle (one day)

	Typically a measurement will fix two of these and vary the other.
	The controls for temperature and field are controlled by external
	services that can be called by the measurement. The measurement
	invokes a localhost for each of these services and can then
	access certain methods
	
	The generic ports for these are
	Magnet: 18861
	Temperature: 18871

	Data from these processes can also be accessed through named pipes

	Device parameters are so far controlled in situ in the measurement
	loop. This should probably also be changed to be consistent

"""
	
import shutil
import time
from datetime import datetime
from sys import exit

import numpy as np
import pyqtgraph as pg

import utils.measurement_subs_dilfridge as measurement_utils
import utils.socket_utils as socket_utils

pg.setConfigOption("useWeave", False)

#################################################
# Device sweep
#################################################


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
		socket_data_number=2,					# 5 for 9T, 2 for Dilution fridge
		comment="No comment!", network_dir="Z:\\DATA"
):

	# Bind sockets 
	m_client, m_socket, t_client, t_socket = measurement_utils.initialize_sockets()

	num_of_inst = len(read_inst)

	# set the sweep voltages

	sweep = measurement_utils.generate_device_sweep(sweep_start, sweep_stop, sweep_step, mid=sweep_mid)
	set_time = datetime.now()

	# Go to the set temperature and magnetic field and finish in persistent mode
	if t_set > 0:
		msg = " ".join(("SET", "%.2f" % t_set))
		measurement_utils.socket_write(t_client, msg)
		print("Wrote message to temperature socket \"%s\"" % msg)
	if not ignore_magnet:
		msg = " ".join(("SET", "%.4f" % b_set, "%d" % int(not persist)))
		measurement_utils.socket_write(m_client, msg)
		print("Wrote message to Magnet socket \"%s\"" % msg)
	time.sleep(5)

	# give precedence to the magnet and wait for the timeout
	t_socket = measurement_utils.socket_read(t_client, t_socket)
	m_socket = measurement_utils.socket_read(m_client, m_socket)
	if not ignore_magnet:
		while m_socket[1] != 1:
			print("Waiting for magnet!")
			time.sleep(15)
			t_socket = measurement_utils.socket_read(t_client, t_socket)
			m_socket = measurement_utils.socket_read(m_client, m_socket)
	
	now_time = datetime.now()
	remaining = timeout*60.0 - float((now_time-set_time).seconds)
	while (t_socket[1] != 1) and (remaining > 0):
		now_time = datetime.now()
		remaining = timeout*60.0 - float((now_time-set_time).seconds)
		print("Waiting for temperature ... time remaining = %.2f minutes" % (remaining/60.0))
		t_socket = measurement_utils.socket_read(t_client, t_socket)
		m_socket = measurement_utils.socket_read(m_client, m_socket)	
		time.sleep(15)
	
	# Setup L plot windows
	if make_plot:
		graph_window = rpg.GraphicsWindow(title="Device sweep...")
		graph_window.resize(500, 150*num_of_inst)
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
						set_val = set_val + [0]*(len(set_inst)-len(set_val))
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
		remaining = wait*60.0
		while remaining > 0:
			now_time = datetime.now()
			remaining = wait*60.0 - float((now_time-wait_time).seconds)
			print("Waiting ... time remaining = %.2f minutes" % (remaining/60.0))
			t_socket = measurement_utils.socket_read(t_client, t_socket)
			m_socket = measurement_utils.socket_read(m_client, m_socket)	
			time.sleep(15)
	print("Starting measurement!")

	start_time = datetime.now()

	writer, file_path, net_dir = measurement_utils.open_csv_file(
		data_file, start_time, read_inst, sweep_inst=[sweep_inst], 
		set_inst=set_inst, comment=comment, network_dir=network_dir
	)

	# This is the main measurement loop
	start_column, data_vector = measurement_utils.generate_data_vector(
		socket_data_number, read_inst, sample,
		sweep_inst=True, set_value=set_value
	)
	
	for i, v in enumerate(sweep):
		sweep_inst.set_output(v)

		t_socket = measurement_utils.socket_read(t_client, t_socket)
		m_socket = measurement_utils.socket_read(m_client, m_socket)

		data_vector[:, 0] = m_socket[0]
		data_vector[:, 1:socket_data_number] = t_socket[0]
		data_vector[:, socket_data_number] = v

		for j in range(sample):

			for i, v in enumerate(read_inst):
				v.read_data()
				data_vector[j, start_column[i]:start_column[i+1]] = v.data
	
			# Sleep
			if delay >= 0.0:
				time.sleep(delay)
		
		# Save the data
		for j in range(sample):
			writer.writerow(data_vector[j, :])

		# Package the data and send it for plotting
		
		if make_plot or return_data:
			to_plot = np.empty((num_of_inst+1))
			to_plot[0] = data_vector[-1, socket_data_number]
			for j in range(num_of_inst):
				to_plot[j+1] = data_vector[-1, start_column[j]+read_inst[j].DataColumn]
	
			# Pass data to the plots
			plot_data.extend(to_plot, _callSync="off")
		if make_plot:
			for j in range(num_of_inst):
				curve[j].setData(x=plot_data[0::(num_of_inst+1)], y=plot_data[j+1::(num_of_inst+1)], _callSync = "off")

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
		data_list = [None]*(num_of_inst+1)
		data_list[0] = plot_data[0::num_of_inst+1]
		for i in range(1, num_of_inst+1):
			data_list[i] = plot_data[i::num_of_inst+1]
		
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

##################################################
# sweep T or B
###################################################

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
		ignore_magnet=False):

	# Bind sockets 
	m_client, m_socket, t_client, t_socket = measurement_utils.initialize_sockets()

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
	
	# Tell the magnet daemon to go to the inital field and set the temperature
	msg = " ".join(("SET", "%.2f" % t_set[0]))
	measurement_utils.socket_write(t_client, msg)
	print("Wrote message to temperature socket \"%s\"" % msg)

	msg = " ".join(("SET", "%.4f" % b_set[0], "%d" % int(not start_persist)))
	measurement_utils.socket_write(m_client, msg)
	print("Wrote message to Magnet socket \"%s\"" % msg)
	time.sleep(5)

	# give precedence to the magnet and wait for the timeout
	t_socket = measurement_utils.socket_read(t_client, t_socket)
	m_socket = measurement_utils.socket_read(m_client, m_socket)
	if not ignore_magnet:
		while m_socket[1] != 1:
			print("Waiting for magnet!")
			time.sleep(15)
			t_socket = measurement_utils.socket_read(t_client, t_socket)
			m_socket = measurement_utils.socket_read(m_client, m_socket)
	
	now_time = datetime.now()
	remaining = timeout*60.0 - float((now_time-set_time).seconds)
	while (t_socket[1] != 1) and (remaining > 0):
		now_time = datetime.now()
		remaining = timeout*60.0 - float((now_time-set_time).seconds)
		print("Waiting for temperature ... time remaining = %.2f minutes" % (remaining/60.0))
		t_socket = measurement_utils.socket_read(t_client, t_socket)
		m_socket = measurement_utils.socket_read(m_client, m_socket)	
		time.sleep(15)
	
	# Setup L plot windows
	graph_window = rpg.GraphicsWindow(title="Fridge sweep...")
	plot_data = graph_proc.transfer([])
	graph_window.resize(500, 150*num_of_inst)
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
						set_val = set_val + [0]*(len(set_inst)-len(set_val))
				for i, v in enumerate(set_inst):
					print("Ramping %s to %.2e" % (v.name, set_val[i]))
					v.ramp(set_val[i])
	
	if wait >= 0.0:
		print("Waiting %.2f minute!" % wait)		
		wait_time = datetime.now()
		remaining = wait*60.0
		while remaining > 0:
			now_time = datetime.now()
			remaining = wait*60.0 - float((now_time-wait_time).seconds)
			print("Waiting ... time remaining = %.2f minutes" % (remaining/60.0))
			t_socket = measurement_utils.socket_read(t_client, t_socket)
			m_socket = measurement_utils.socket_read(m_client, m_socket)	
			time.sleep(15)
	print("Starting measurement!")

	start_time = datetime.now()

	writer, file_path, net_dir = measurement_utils.open_csv_file(
		data_file, start_time, read_inst, set_inst=set_inst,
		comment=comment, network_dir=network_dir
	)

	# This is the main measurement loop

	start_column, data_vector = measurement_utils.generate_data_vector(
		socket_data_number, read_inst, sample, set_value=set_value
	)

	if b_sweep:
		msg = " ".join(("SWP", "%.4f" % b_set[1], "%.4f" % sweep_rate, "%d" % int(not persist)))
		measurement_utils.socket_write(m_client, msg)
		print("Wrote message to magnet socket \"%s\"" % msg)
	else:
		msg = " ".join(("SWP", "%.4f" % t_set[1], "%.4f" % sweep_rate, "%.2f" % max_over_time))
		measurement_utils.socket_write(t_client, msg)
		print("Wrote message to temperature socket \"%s\"" % msg)	

	t_socket = measurement_utils.socket_read(t_client, t_socket)
	m_socket = measurement_utils.socket_read(m_client, m_socket)
	if b_sweep:
		fridge_status = m_socket[-1]
	else:
		fridge_status = t_socket[-1]

	while fridge_status != 0: 
		time.sleep(1)
		# print fridge_status
		t_socket = measurement_utils.socket_read(t_client, t_socket)
		m_socket = measurement_utils.socket_read(m_client, m_socket)
		if b_sweep:
			fridge_status = m_socket[-1]
		else:
			fridge_status = t_socket[-1]

	sweep_time_length = abs(sweep_start-sweep_stop)/sweep_rate  # In minutes
	sweep_time_length = sweep_time_length + max_over_time
	# print sweep_time_length
	start_time = datetime.now()
	sweep_timeout = False
	
	# print Field
	while fridge_status == 0 and (not sweep_timeout):
		
		t_socket = measurement_utils.socket_read(t_client, t_socket)
		m_socket = measurement_utils.socket_read(m_client, m_socket)
		if b_sweep:
			fridge_status = m_socket[-1]
		else:
			fridge_status = t_socket[-1]

		data_vector[:, 0] = m_socket[0]
		data_vector[:, 1:socket_data_number] = t_socket[0]

		for j in range(sample):
		
			for i, v in enumerate(read_inst):
				v.read_data()
				data_vector[j, start_column[i]:start_column[i+1]] = v.data

			# Sleep
			time.sleep(delay)
		
		# Save the data
		for j in range(sample):
			writer.writerow(data_vector[j, :])

		to_plot = np.empty((num_of_inst+1))
		if b_sweep:
			to_plot[0] = data_vector[-1, 0]
		else:
			to_plot[0] = data_vector[-1, 1]
		for j in range(num_of_inst):
			to_plot[j+1] = data_vector[-1, start_column[j]+read_inst[j].DataColumn]
	
		# Pass data to the plots
		plot_data.extend(to_plot, _callSync="off")
		for j in range(num_of_inst):
			curve[j].setData(x=plot_data[0::(num_of_inst+1)], y=plot_data[j+1::(num_of_inst+1)], _callSync="off")
		
		if not b_sweep:
			d_temp = datetime.now() - start_time
			d_temp_min = d_temp.seconds/60.0
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
		data_list = [None]*(num_of_inst+1)
		data_list[0] = plot_data[0::num_of_inst+1]
		for i in range(1, num_of_inst+1):
			data_list[i] = plot_data[i::num_of_inst+1]
	
	if b_sweep:
		msg = " ".join(("SET", "%.4f" % sweep_finish, "%d" % int(not persist)))
		measurement_utils.socket_write(m_client, msg)
		print("Wrote message to Magnet socket \"%s\"" % msg)
	else:
		msg = " ".join(("SET", "%.2f" % sweep_finish))
		measurement_utils.socket_write(t_client, msg)
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


"""
	2D data acquisition either by sweeping a device parameter
	or by sweepng a fridge parameter
	The program decides which of these to do depending on if the
	the variable "sweep_inst" is assigned.
	i.e. if "sweep_inst" is assigned the device is swept and the
	fridge parameter is stepped.
	If the device is being swept the variable "fridge_rate" is the size
	of successive steps of either T or B.
	If the fridge is being swept the first set_inst is stepped by the
	"device_step"
	
	For the case of successive B sweeps the fridge will be swept
	forwards and backwards
	e.g.	Vg = -60 V B = -9 --> +9 T
		Vg = -50 V B = +9 --> -9 T
		etc ...
	Note that in this case the first "set_value" will be overwritten
	therefore a dummy e.g. 0.0 should be written in the case that there
	are additional set_inst
"""


def device_fridge_2d(
		graph_proc, rpg, data_file,
		read_inst, sweep_inst=[], set_inst=[],
		set_value=[], pre_value=[], finish_value=[],
		fridge_sweep="B", fridge_set=0.0,
		device_start=0.0, device_stop=1.0, device_step=0.1, device_finish=0.0,
		device_mid=[],
		fridge_start=0.0, fridge_stop=1.0, fridge_rate=0.1,
		delay=0, sample=1,
		timeout=-1, wait=0.0,
		comment="No comment!", network_dir="Z:\\DATA",
		persist=True, x_custom=[]
):

	if sweep_inst:
		sweep_device = True
	else:
		sweep_device = False

	if fridge_sweep == "B":
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
			y_len = len(measurement_utils.generate_device_sweep(
				device_start, device_stop, device_step, mid=device_mid))
		else:
			y_len = abs(y_start-y_stop)/y_step+1

	num_of_inst = len(read_inst) 
	plot_2d_window = [None]*num_of_inst
	view_box = [None]*num_of_inst
	image_view = [None]*num_of_inst
	z_array = [np.zeros((len(x_vec), y_len)) for i in range(num_of_inst)]
	
	if sweep_device:
		for i in range(num_of_inst):
			plot_2d_window[i] = rpg.QtGui.QMainWindow()
			plot_2d_window[i].resize(500, 500)
			view_box[i] = rpg.ViewBox(invertY=True)
			image_view[i] = rpg.ImageView(view=rpg.PlotItem(viewBox=view_box[i]))
			plot_2d_window[i].setCentralWidget(image_view[i])
			plot_2d_window[i].setWindowTitle("read_inst %d" % i)
			plot_2d_window[i].show()
			view_box[i].setAspectLocked(False)

			y_scale = y_step
			x_scale = (x_vec[-2]-x_vec[0])/np.float(len(x_vec)-1)

			for j in range(num_of_inst):
				image_view[j].setImage(z_array[j], scale=(x_scale, y_scale), pos=(x_vec[0], y_start))

	for i, v in enumerate(x_vec):
	
		if sweep_device:
			# sweep the device and fix T or B
			if b_sweep:

				data_list = do_device_sweep(
					graph_proc, rpg, data_file,
					sweep_inst, read_inst, set_inst=set_inst, set_value = set_value,
					finish_value=finish_value, pre_value=pre_value, b_set=v, persist=False,
					sweep_start=device_start, sweep_stop=device_stop, sweep_step=device_step,
					sweep_finish=device_finish, sweep_mid = device_mid,
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
			if i == len(x_vec)-1:
				finish_value[0] = 0.0
			else:
				finish_value[0] = x_vec[i+1]
			
			# Fix the device and sweep T or B
			if b_sweep:
				data_list = do_fridge_sweep(
					graph_proc, rpg, data_file,
					read_inst, set_inst=set_inst, set_value=set_value,
					finish_value=finish_value, pre_value=pre_value,
					fridge_sweep="B", fridge_set=fridge_set,
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
					fridge_sweep="T", fridge_set=fridge_set,
					sweep_start=fridge_start, sweep_stop=fridge_stop,
					sweep_rate=fridge_rate, sweep_finish=fridge_stop,
					persist=True,
					delay=delay, sample=sample,
					timeout=timeout, wait=wait,
					return_data=True,
					comment=comment, network_dir=network_dir)
						
				if sweep_device:
					for j in range(num_of_inst):
						z_array[j][i, :] = data_list[j+1]
						image_view[j].setImage(z_array[j], pos=(x_vec[0], y_start), scale=(x_scale, y_scale))

	m_client = socket_utils.SockClient('localhost', 18861)
	time.sleep(2)
	measurement_utils.socket_write(m_client, "SET 0.0 0")
	time.sleep(2)
	m_client.close()
	
	time.sleep(2)

	return

#########################################################################
# SWEEP two device parameters e.g. backgate bias, one is stepped
# the other is swept
########################################################################

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

	if not finish_value:
		finish_value = list(set_value)

	# We step over the x variable and sweep over the y
	
	set_inst_list = list(set_inst) 
	set_inst_list.append(step_inst)

	# X is the step axis
	# Y is the sweep axis
	x_vec = np.hstack((np.arange(step_start, step_stop+step_step, step_step), step_finish))
	y_vec = measurement_utils.generate_device_sweep(sweep_start, sweep_stop, sweep_step, mid=sweep_mid)
	y_max = np.max(y_vec)
	y_min = np.min(y_vec)

	if x_custom:
		x_vec = x_custom

	num_of_inst = len(read_inst) 
	plot_2d_window = [None]*num_of_inst
	view_box = [None]*num_of_inst
	image_view = [None]*num_of_inst
	z_array = [np.zeros((len(x_vec)-1, len(y_vec))) for i in range(num_of_inst)]
	
	for i in range(num_of_inst):
		plot_2d_window[i] = rpg.QtGui.QMainWindow()
		plot_2d_window[i].resize(500, 500)
		view_box[i] = rpg.ViewBox()
		view_box[i].enableAutoRange()
		image_view[i] = rpg.ImageView(view=rpg.PlotItem(viewBox=view_box[i]))
		plot_2d_window[i].setCentralWidget(image_view[i])
		plot_2d_window[i].setWindowTitle("read_inst %d" % i)
		plot_2d_window[i].show()
		view_box[i].invertY(True)
		view_box[i].setAspectLocked(False)

	y_scale = (y_max-y_min)/np.float(len(y_vec))
	x_scale = (x_vec[-2]-x_vec[0])/np.float(len(x_vec)-1)

	# print x_scale
	# print y_scale
	for j in range(num_of_inst):
		image_view[j].setImage(z_array[j], pos=(x_vec[0], y_min), scale=(x_scale, y_scale))

	sets = [None] * (len(set_value)+1)
	if len(set_value) > 0:
		sets[:-1] = set_value[:]
	finishs = [None] * (len(finish_value)+1)
	if len(finish_value) > 0:
		finishs[:-1] = finish_value[:]

	for i, v in enumerate(x_vec[:-1]):
		sets[-1] = v
		finishs[-1] = x_vec[i+1]

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
			z_array[j][i, :] = data_list[j+1]
			image_view[j].setImage(z_array[j], pos=(x_vec[0], y_min), scale=(x_scale, y_scale))

	m_client = socket_utils.SockClient('localhost', 18861)
	time.sleep(2)
	measurement_utils.socket_write(m_client, "SET 0.0 0")
	time.sleep(2)
	m_client.close()

	time.sleep(2)

	return
