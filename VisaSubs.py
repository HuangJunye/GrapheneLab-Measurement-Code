#!/usr/bin/python
# -*- coding: utf-8 -*-

"""

Sub programs for communication using PyVisa

author : Eoin O'Farrell
email : phyoec@nus.edu.sg
last edited : July 2013

Functions written:
	InitializeGPIB
	InitializeSerial

"""
import visa as visa

# initalize GPIB devices using PyVisa
def InitializeGPIB(address, board, QueryID=True, ReadTermination = "LF"
                    , **kwargs):
	rm = visa.ResourceManager()
        GPIBName = "GPIB%d::%d::INSTR" % (board,address)
       # print GPIBName
        try:
		GPIBVisa = rm.open_resource(GPIBName)
                if ReadTermination == "LF":
                   GPIBVisa.read_termination = "\n"
                   GPIBVisa.write_termination = "\n"                    
                elif ReadTermination == "CR":
                    GPIBVisa.read_termination = "\r"
                    GPIBVisa.write_termination = "\r"
                elif ReadTermination == "CRLF":
                    GPIBVisa.read_termination = "\r\n"
                    GPIBVisa.write_termination = "\r\n"
		for kw in kwargs.keys():
			tmp = "".join(("GPIBVisa.",kw,"=\"",kwargs[kw],"\""))
			exec(tmp)
		if QueryID:
			print GPIBVisa.query("*IDN?")
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
		print SerialVisa.query(idn)
	except Exception:
		print "Failed opening serial port %s\n" % name
		SerialVisa = None

	return SerialVisa
        

