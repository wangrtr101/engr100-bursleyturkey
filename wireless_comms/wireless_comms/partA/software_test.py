'''
The purpose of this script is a sanity check
to see if this system has all the required Python packages to run the ENGR 100-400 software.
'''

import sys # System handling

# First detect whether a virtual environment is active
def is_venv_active():
    return sys.prefix != sys.base_prefix


if is_venv_active():
    try:
        import curses # keyboard package, should be automatically installed on all modern OSes
        import socket # network package, used to connect to ESP32's access point
        import time # timing package, used to test code latency
        import numpy # common scientific computing package, includes many good signal processing functions
        import scipy # another scientfic computing package, doubly useful for image processing
        import imutils # Image manipulation package, used in displaying video from ESP32
        import cv2 # OpenCV package
        import ultralytics # YOLO/ML package. Used for complex object detection

    except ImportError as e:
        print(f"Test failed on package {e.name}. Make sure to install it in your virtual environment!")
        sys.exit(1)

    print("All ENGR100-400 relevant Python packages successfully found.")

else:
    print("No virtual environment active. Make sure to activate it with the command \'source <name_of_env>/bin/active\' prior to running scripts.")

