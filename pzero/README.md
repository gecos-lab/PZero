# PZero Core Modules

This folder contains the core Python modules for the PZero project. These files implement the main logic, data structures, and algorithms used throughout the application.

## File Overview

- `project_window.py`  
  Main window class for the PZero application, integrating the UI and core logic. Handles project creation, opening, saving, import/export of various geological data formats, entity management, and connections to all main collections and legends. Provides the central hub for user interaction and workflow orchestration.

- `entities_factory.py`  
  Defines the main geometric and geological entity classes used throughout the project, including polylines, triangulated surfaces, point clouds, voxets, images, wells, and related data structures. Provides Pythonic wrappers around VTK and PyVista objects, exposing data as NumPy arrays and offering methods for deep copying, property management, and geometric operations. Supports both geological and non-geological objects, and integrates with orientation analysis utilities.

- `legend_manager.py`  
  Manages the legend system for geological, fluid, background, well, and other entity collections. Provides utilities for updating the legend widget, handling color, line thickness, point size, opacity, and sequence changes, and synchronizing legend data with the UI and project dataframes. Integrates with PySide6 and pandas for interactive legend editing and visualization.

- `properties_manager.py`  
  Manages property colormaps and legends for geological, DOM, mesh3d, and related collections. Provides utilities for updating property colormap tables, synchronizing with project data, and handling user interactions for property visualization. Integrates with PySide6, matplotlib, colorcet, cmocean, and PyVista for colormap management and display.

- `two_d_lines.py`  
  Functions and tools for creating, editing, and manipulating 2D lines, including digitizing, editing, splitting, merging, snapping, and resampling lines. Integrates with the application's map and cross-section views.

- `three_d_surfaces.py`  
  Tools and algorithms for creating, editing, and processing 3D surfaces and meshes. Includes Delaunay triangulation, Poisson surface reconstruction, implicit modeling with LoopStructural, surface smoothing, mesh decimation, subdivision, intersection, projection, and retopology. Integrates with VTK, PyVista, and LoopStructural libraries.

- `point_clouds.py`  
  Functions and tools for processing, segmenting, and analyzing point cloud data. Includes utilities for normal calculation, region extraction, segmentation by dip and dip direction, decimation, cutting, calibration, and conversion to geological features. Integrates with VTK, PyVista, matplotlib, seaborn, and NumPy for advanced point cloud operations and visualization.

- `orientation_analysis.py`  
  Functions for orientation analysis, including conversions between geological orientation measurements (strike, dip, dip direction, plunge, trend), calculation of normal and lineation vectors, and utilities for setting normals on geological entities and point clouds. Integrates with NumPy and project-specific entity classes.

## Sub-modules

- `collections/`  
  Manages grouped data structures and collections of geological entities, such as layers, surfaces, wells, and other domain-specific objects.

- `helpers/`  
  Utility modules for dialogs, widgets, and general helper functions used across the application.

- `imports/`  
  Modules and utilities for importing, parsing, and converting external geological data formats into the application's internal structures.

- `processing/`  
  Implements core data processing algorithms, computational routines, and utilities for geological modeling, mesh operations, and advanced analysis.

- `ui/`  
  Contains user interface components, custom widgets, dialogs, and Qt Designer `.ui` files used to build the application's graphical interface.

- `views/`  
  Contains the main view classes for the application's GUI, including map and cross-section windows.
