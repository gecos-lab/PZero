# Processing

This folder contains modules for data processing and standardization tasks within the PZero project, including SEG-Y seismic data standardization and coordinate reference system (CRS) utilities.

## File Overview

- `segy_standardizer.py`  
  Utility functions for standardizing SEG-Y files to ensure PZero compatibility.  
  **Main functions:**  
  - `analyze_segy_parameters(input_file)`: Extracts standard SEG-Y parameters (samples, interval, format, etc.).  
  - `standardize_segy_for_pzero(input_file, output_file, print_fn=print)`: Converts a SEG-Y file to a standardized format for PZero, updating headers and trace data as needed.  
  - `convert_to_standard_segy(input_file, output_file, print_fn=print)`: Main entry point for SEG-Y conversion.

- `CRS.py`  
  Utilities for handling coordinate reference systems (CRS) and spatial transformations, based on PROJ.  
  **Typical contents:**  
  - Functions and/or classes for parsing, converting, and applying CRS definitions to spatial data.
