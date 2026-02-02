#!/usr/bin/env python
from vtkmodules.all import *
import sys


lib_dict = globals()

input_name = sys.argv[1]

if input_name in lib_dict:
    module = lib_dict[input_name]
    print(f"from {module.__module__} import {module.__name__}")
else:
    print("No module found")
