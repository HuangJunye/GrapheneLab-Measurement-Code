#!/usr/bin/python
# -*- coding: utf-8 -*-

"""

Sub programs for time sweep

author : Alexander Mayorov
email : mayorov@gmail.com
last edited : Feb 2016


"""

#import rpyc
import string as string
import re as re
from collections import namedtuple
import time
import math
import numpy as np
import threading
import Queue

######################################################
# Timer class
#####################################################

class Timer:
	def __init__(self, address):
		self.Name = "Timer"
		self.Address = address		#It is an arbitrary number
		self.Data = [0.0]
		self.InitTime = time.time()
		self.RampStep = 1
		self.Output = False
		self.Source = "SECONDS"
		self.ColumnNames = "Time (s)"
		self.SourceColumn = 0
	
	##################################################
	# Read data
	################################################

	#def Time(self):
	#	Reply = time.time();
	#	pass
	
	def ReadData(self):
		Reply = time.time()-self.InitTime		
		self.Data = [Reply]
		pass
	
	def Initialize(self):
		self.InitTime = time.time()
		print "Initialize timer"
		pass
		
	def SetOutput(self,Level):
		#self.Visa.write("".join((":SOUR:",self.Source," %.4e" % Level)))
		pass
		
	def SwitchOutput(self):
		#self.Visa.write("".join((":OUTP:STAT ","%d" % self.Output)))
		pass
		
	def Ramp(self,VFinish):
		if self.Output:
			self.ReadData()
		VStart = self.Data[self.SourceColumn]
		if abs(VStart-VFinish) > self.RampStep:	
			N = abs((VFinish-VStart)/self.RampStep)
			VSweep = np.linspace(VStart,VFinish,num=np.ceil(N),endpoint=True)

			if not self.Output:
				self.SwitchOutput()

			for i in range(len(VSweep)):
				self.SetOutput(VSweep[i])
				time.sleep(0.01)

			self.ReadData()
		return
		
	###################################################
	# Print a description string 
	################################################
	
	def Description(self):
		DescriptionString = "Timer"		
		DescriptionString = "".join((DescriptionString,"\n"))
		return DescriptionString

