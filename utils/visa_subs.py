#!/usr/bin/python
# -*- coding: utf-8 -*-

"""

Sub programs for communication using PyVisa

author : Eoin O'Farrell
email : phyoec@nus.edu.sg
last edit : January 2015

Edited to support PyVisa 1.6

Functions written:
	InitializeGPIB
	InitialIzeSerial

"""
import visa as visa
rm = visa.ResourceManager()


def initialize_gpib(address, board, query_id=True, read_termination="LF", **kwargs):
	""" Initalize GPIB devices using PyVisa """

	gpib_name = f"GPIB{board}::{address}::INSTR"
	try:
		gpib_visa = rm.open_resource(gpib_name)
		if read_termination == "LF":
			gpib_visa.read_termination = "\n"
			gpib_visa.write_termination = "\n"
		elif read_termination == "CR":
			gpib_visa.read_termination = "\r"
			gpib_visa.write_termination = "\r"
		elif read_termination == "CRLF":
			gpib_visa.read_termination = "\r\n"
			gpib_visa.write_termination = "\r\n"
		for kw in list(kwargs.keys()):
			tmp = "".join(("gpib_visa.", kw, "=", kwargs[kw]))
			exec(tmp)
		if query_id:
			print(gpib_visa.query("*IDN?"))
	except Exception:
		print("Failed opening GPIB address %d\n" % address)
		gpib_visa = None
	return gpib_visa


def initialize_serial(name, idn="*IDN?", read_termination="LF", **kwargs):
	""" Initialize Serial devices using PyVisa """

	try:
		serial_visa = rm.open_resource(name)
		if read_termination == "LF":
			serial_visa.read_termination = "\n"
		elif read_termination == "CR":
			serial_visa.read_termination = "\r"
		elif read_termination == "CRLF":
			serial_visa.read_termination = "\r\n"
		for kw in list(kwargs.keys()):
			tmp = "".join(("serial_visa.", kw, "=", kwargs[kw]))
			exec(tmp)
		print(serial_visa.query(idn))
	except Exception:
		print("Failed opening serial port %s\n" % name)
		serial_visa = None
	return serial_visa
