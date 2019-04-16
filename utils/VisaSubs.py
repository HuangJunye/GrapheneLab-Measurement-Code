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

# initalize GPIB devices using PyVisa

def InitializeGPIB(address, board, QueryID=True, ReadTermination = "LF"
                    , **kwargs):
    rm = visa.ResourceManager()
    GPIBName = "GPIB%d::%d::INSTR" % (board,address)
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
        for kw in list(kwargs.keys()):
            tmp = "".join(("GPIBVisa.",kw,"=",kwargs[kw]))
            exec(tmp)
        if QueryID:
            print(GPIBVisa.ask("*IDN?"))
    except Exception:
        print("Failed opening GPIB address %d\n" % address)
        GPIBVisa = None
    return GPIBVisa

# initialize Serial devices using PyVisa

def InitializeSerial(name,idn="*IDN?",ReadTermination="LF", **kwargs):
    rm = visa.ResourceManager()        
    try:
        SerialVisa = rm.open_resource(name)
        if ReadTermination == "LF":
            SerialVisa.read_termination = "\n"
        elif ReadTermination == "CR":
            SerialVisa.read_termination = "\r"
        elif ReadTermination == "CRLF":
            SerialVisa.read_termination = "\r\n"
        for kw in list(kwargs.keys()):
            tmp = "".join(("SerialVisa.",kw,"=",kwargs[kw]))
            exec(tmp)
        print(SerialVisa.ask(idn))
    except Exception:
        print("Failed opening serial port %s\n" % name)
        SerialVisa = None
    return SerialVisa
