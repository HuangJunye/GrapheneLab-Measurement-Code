#!/usr/bin/python
# -*- coding: utf-8 -*-

"""

Sub programs for doing the measurements

author : Eoin O'Farrell
email : phyoec@nus.edu.sg
last edited : July 2013

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

import asyncore
import csv
import os
import time

import numpy as np

import utils.socket_utils as socket_utils


def initialize_sockets():
	# Bind to the temperature and magnet sockets and try to read them
	t_client = socket_utils.SockClient('localhost', 18871)
	m_client = socket_utils.SockClient('localhost', 18861)
	time.sleep(4)
	m_socket = [0.0, 0]
	t_socket = [0.0, 0]
	m_socket = socket_read(m_client, m_socket)
	t_socket = socket_read(t_client, t_socket)
	
	return m_client, m_socket, t_client, t_socket


def socket_read(client, old_socket=[]):
	# Read the socket and parse the reply, the reply has 2 parts the message and the status
	asyncore.loop(count=1, timeout=0.001)
	socket_string = client.received_data
	socket = old_socket
	if socket_string:
		socket_string = socket_string.split(",")[-1]
		socket_string = socket_string.split(" ")
		if len(socket_string) == 2:
			value = socket_string[:-1]
			status = socket_string[-1]
			try:
				for i, v in enumerate(value):
					value[i] = float(v)
				status = int(status)
				socket[0] = value
				socket[1] = status
			except:
				pass

	return socket


def socket_write(client, msg):
	client.to_send = msg
	asyncore.loop(count=1, timeout=0.001)
	time.sleep(2)
	client.to_send = "-"
	asyncore.loop(count=1, timeout=0.001)


def open_csv_file(
		file_name, start_time, read_inst,
		sweep_inst=[], set_inst=[], comment="No comment!\n",
		network_dir="Z:\\DATA"
):
	
	# Setup the directories
	# Try to make a directory called Data in the CWD
	current_dir = os.getcwd()
	data_dir = "".join((current_dir, "\\Data"))
	try:
		os.mkdir(data_dir)
	except OSError:
		pass

	# Try to make a directory with the current director name in the
	# network drive
	
	network_dir = network_dir
	dir_name = os.path.basename(current_dir)
	net_dir = "".join((network_dir, "\\", dir_name))
	if not os.path.exists(net_dir):
		try:
			os.mkdir(net_dir)
		except OSError:
			pass

	# Try to make a file called ...-0.dat in data else ...-1.dat etc.
	i = 0
	while True:
		file = "".join((data_dir, "\\", file_name, "-", "%d" % i, ".dat"))
		try:
			os.stat(file)
			i = i+1
			pass
		except OSError:
			csv_file = open(file, "w")
			file_writer = csv.writer(csv_file, delimiter=',')
			break
	
	# Write the starttime and a description of each of the instruments
	file_writer.writerow([start_time])

	column_string = "B (T), T(mK) "
	
	for inst in sweep_inst:
		csv_file.write("".join(("SWEEP: ", inst.Description())))
		column_string = "".join((column_string, ", ", inst.Source))

	for inst in set_inst:
		csv_file.write("".join(("SET: ", inst.Description())))
		column_string = "".join((column_string, ", ", inst.Source))

	for inst in read_inst:
		csv_file.write("".join(("READ: ", inst.Description())))
		column_string = "".join((column_string, ", ", inst.ColumnNames))

	column_string = "".join((column_string, "\n"))
	csv_file.write(comment)
	csv_file.write("\n")
	csv_file.write(column_string)

	print("Writing to data file %s\n" % file)
	return file_writer, file, net_dir


def generate_device_sweep(start, stop, step, mid=[]):
	# self.Visa.write("".join((":SOUR:",self.Source,":MODE FIX")))
	targets = mid
	targets.insert(0, start)
	targets.append(stop)

	sweep = [targets[0]]
	for i in range(1, len(targets)):
		points = int(1+abs(targets[i]-targets[i-1])/step)
		sweep = np.hstack([sweep, np.linspace(targets[i-1], targets[i], num=points)[1:points]])
	return sweep


def generate_data_vector(L_fridge_param, read_inst, sample, sweep_inst=False, set_value=[]):

	L_set = len(set_value)
	if sweep_inst:
		L_sweep = 1
	else:
		L_sweep = 0
	L_read = 0
	start_column = [0] * (len(read_inst)+1)
	start_column[0] = L_fridge_param + L_sweep + L_set
	for i, v in enumerate(read_inst):
		start_column[i+1] = start_column[i] + len(v.data)

	data_vector = np.zeros((sample, start_column[-1]))

	for i in range(L_set):
		data_vector[:, i+L_fridge_param+L_sweep] = set_value[i]

	return start_column, data_vector
