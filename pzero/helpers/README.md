# Helpers

This folder contains utility classes and functions that support interactive widgets, color management, signal handling, dialogs, and general helper routines for the PZero project.

## File Overview

- `helper_widgets.py`  
  Provides interactive VTK-based widgets for tracing, vector drawing, editing, and cutting lines in 3D scenes.  
  **Main classes:**  
  - `Tracer`: For drawing freehand lines.  
  - `Vector`: For drawing and measuring vectors (length, azimuth, dip).  
  - `Editor`: For editing and extending polylines interactively.  
  - `Scissors`: For interactively cutting lines.

- `helper_colors.py`  
  Utilities for color conversion, palette management, and color-related helpers.

- `helper_functions.py`  
  General-purpose helper functions for profiling, math, geometry, and data manipulation.  
  **Main functions:**  
  - `profiler`: Decorator for profiling function execution time.  
  - `angle_wrapper`: Wraps angles to \[0, 2π\].  
  - `PCA`: Principal Component Analysis on data arrays.  
  - `best_fitting_plane`: Computes the best fitting plane for a set of 3D points.  
  - `gen_frame`: Generates transparent frames for GIFs.  
  - `rotate_vec_along`: Rotates a vector along a specified axis.  
  - `srf`: Computes the mean resultant length of vectors.  
  - `freeze_gui`: Decorator to freeze GUI during processing.

- `helper_widgets_qt.py`  
  Qt-based widget helpers for integrating custom controls and dialogs into the GUI.

- `helper_signals.py`  
  Utilities for managing Qt signals, such as disconnecting all signals from a list.  
  **Main function:**  
  - `disconnect_all_signals(signals)`: Disconnects all signals of a QObject.

- `helper_dialogs.py`  
  Dialog utilities for user input, file selection, progress, and data preview.  
  **Main functions/classes:**  
  - `options_dialog`, `input_text_dialog`, `input_combo_dialog`, `open_file_dialog`, etc.: Various input and message dialogs.  
  - `multiple_input_dialog`, `general_input_dialog`, `input_checkbox_dialog`: Flexible dialogs for multiple or custom inputs.  
  - `progress_dialog`: Progress bar dialog for long-running tasks.  
  - `PCDataModel`: Qt table model for displaying pandas DataFrames.  
  - `import_dialog`: Window for importing and previewing data files.  
  - `NavigatorWidget`, `PreviewWidget`: Widgets for navigation and previewing data/meshes.
