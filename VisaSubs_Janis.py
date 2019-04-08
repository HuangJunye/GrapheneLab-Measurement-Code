#!/usr/bin/python
# -*- coding: utf-8 -*-

"""

Sub programs for communication using PyVisa

author : Eoin O'Farrell
email : phyoec@nus.edu.sg
last edited : July 2013

Functions written:
	InitializeGPIB
	InitialIzeSerial

"""
import visa as visa

# initalize GPIB devices using PyVisa

def InitializeGPIB(address, board, QueryID=True, **kwargs):
	try:
		GPIBVisa = visa.GpibInstrument(address,board)
		for kw in kwargs.keys():
			tmp = "".join(("GPIBVisa.",kw,"=\"",kwargs[kw],"\""))
			exec(tmp)
		if QueryID:
			print GPIBVisa.ask("*IDN?")
	except Exception:
		print "Failed opening GPIB address %d\n" % address
		GPIBVisa = None

	return GPIBVisa

# initialize Serial devices using PyVisa

def InitializeSerial(name,idn="*IDN?", **kwargs):
	try:
		SerialVisa = visa.SerialInstrument(name)
		for kw in kwargs.keys():
			tmp = "".join(("SerialVisa.",kw,"=\"",kwargs[kw],"\""))
			exec(tmp)
		print SerialVisa.ask(idn)
	except Exception:
		print "Failed opening serial port %s\n" % name
		SerialVisa = None

	return SerialVisa
        

