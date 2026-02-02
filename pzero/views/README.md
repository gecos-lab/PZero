# PZero Views Module

This directory contains the view classes for the PZero application.

## Class Hierarchy

- `BaseView` (abstract_base_view.py): The base class for all views
  - `ViewMPL` (abstract_mpl_view.py): Base class for Matplotlib-based views
    - `ViewStereoplot` (view_stereoplot.py): Stereoplot view using Matplotlib
  - `ViewVTK` (abstract_vtk_view.py): Base class for VTK/PyVista-based views
    - `View3D` (view_3d.py): 3D view using VTK/PyVista
    - `View2D` (abstract_view_2d.py): Base class for 2D views using VTK/PyVista
      - `ViewXsection` (view_xsection.py): Cross-section view
      - `ViewMap` (view_map.py): Map view
