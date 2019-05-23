# GrapheneLab Measurement Code

This is a Python-based transport measurement code used in GrapheneLab in National University of Singapore. The code was originally developed by Eoin O'Farrell and currently maintained by Huang Junye.


## There is QCoDeS why would I want to use gcodes?

QCoDeS is comprehensive, flexible but difficult to use. gcodes is designed to be simple and easy to use for simpler transport measurements.
# Features
## Use PyVisa to talk to instruments. 

Currently supported instruments include:

Measurement instruments:
- Keithley 2002
- Keithley 2182A
- Keithley 2400
- Keithley 6221
- Keithley 6430
- SRS SR830
- SRS SR850

Temperature and Magnet controllers:
- Picowatt AVS-47B resistance bridge (for Leiden Cryogenics Dilution Refrigerators)
- Leiden Cryogenics Triple Current Source
- LakeShore 335 temperature controller
- LakeShore 340 temperature controller
- LakeShore 475 DSP Gaussmeter
- Oxford Mercury iPS magnet power supply

## Live plotting using PyQtGraph
Measurement results are plotted live using PyQtGraph.
