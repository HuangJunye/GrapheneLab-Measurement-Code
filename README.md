# GrapheneLab Measurement Code

This is a Python-based transport measurement code used in GrapheneLab in National University of Singapore. The code was originally developed by Eoin O'Farrell and currently maintained by Huang Junye and Hu Zihao.


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

## Installation instructions
1. Download or clone the `master` branch of the repository
1. Unzip and copy folder to Documents folder
1. Rename folder from "GraphenLab-Measurement-Code-master" to "GraphenLab-Measurement-Code"
1. Install [Anaconda](https://www.anaconda.com/) and [NI-VISA](https://www.ni.com/en-sg/support/downloads/drivers/download.ni-visa.html#305862)
1. After installation of Anaconda and NI-VISA, you can open Anaconda Prompt to install two python packages: PyVisa and PyQtGraph. Type in Anaconda Prompt to install PyVisa: 
```pip install pyvisa```
When the installation of PyVisa finishes, install PyQtGraph:
```pip install pygtgraph```
1. If you don't need temperature and magnetic field control, you can check `example notebook` folder to start measurements.
1. If you need temperature control and/or magnetic field control, you need to configure `t_daemon` and/or `m_daemon` to work with your temperature controller and/or magnet controller. If you are unsure how to do that, raise an issue or contact Huang Junye for assistance: [h.jun.ye@gmail.com](mailto:h.jun.ye@gmail.com)

## Future work
- Deploy to Janis, 9T, 12T and 16 system
- Modular design for TDaemon and MDaemon to allow more robust support of vairous systems.
- Support vector magnet
- Variable step size in do_device_sweep and do_fridge_sweep
- Logging to file in TDaemon and MDaemon
- Fix the bug of jumping temperature when PicoWatt resistance bridge change range.
