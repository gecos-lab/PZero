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

## Selection and tools

### Selection model

The selection of entities is stored once, at project level, in `ProjectWindow` (an ordered dictionary `{uid: collection_name}`, in click order). Every change goes through `ProjectWindow.set_selection()`, which emits `signals.selection_modified(added, removed, collections, source)`. The project tables, the trees of every view and the graphics of every view mirror it:

- selecting in a table, in a view tree or by picking in a view updates all the others;
- selecting from a view or a view tree brings the table tab of that collection to front;
- selected entities are highlighted in all VTK views (yellow outer border for surfaces, DEMs/DOMs and images, yellow lines and points, bounding box for point clouds and volumes);
- while a tool is running (`freeze_gui_on` / `freeze_gui_onoff`), selection by the user in tables and trees is frozen.

`collection.selected_uids` and `ProjectWindow.selected_uids` (collection of the tab in front) read from this store; `view.selected_uids` is the project selection restricted to the entities shown in that view.

### Which entities each tool uses

Tools that work on selected entities are decorated with `@uses_selection(...)` (`helpers/helper_functions.py`), which calls `ProjectWindow.restrict_selection_for_tool()` before the tool runs:

- the tool works on **one collection**: the one of the tab in front if it contains usable entities, otherwise the one of the last selected usable entity, whose tab is brought to front;
- only entities of the accepted topologies are used; tools that work on a single entity use the **last selected** one;
- all other entities are **deselected**, and a message reports it;
- if not enough usable entities are selected, the tool does not run and the selection is unchanged;
- for tools running in a view, entities not shown in that view are not usable.

Tools read the collection with `active_collection(self)` and store their output in the same collection, with metadata copied by `derived_entity_dict()` / `entity_metadata_input_dict()` only for the fields that collection has (e.g. boundaries have no role and feature).

| Tools | Function(s) | Accepts |
|---|---|---|
| Line editing in 2D views: edit, extend, split at point, copy parallel/kink/similar (one line) | `two_d_lines.start_checked_line_tool` | Last selected PolyLine/XsPolyLine in Geology, Fluids or Backgrounds |
| Line editing in 2D views: sort, move, rotate, split line/line, weld, snap, resample, simplify | `two_d_lines.start_checked_line_tool` | PolyLine/XsPolyLine in Geology, Fluids or Backgrounds |
| Smoothing, decimation (pro, quadric), subdivision, retopology | `surface_smoothing`, `decimation_pro_resampling`, `decimation_quadric_resampling`, `subdivision_resampling`, `retopo`, `smooth_dialog`, `subd_res_dialog`, `retopologize_surface` | TriSurf in any collection |
| Retriangulate (one only) | `retriangulate_surface_dialog` | TriSurf in any collection |
| Split surface (at least 2, the last one cuts the others) | `split_surf` | TriSurf in any collection |
| Delaunay 2D and Poisson interpolation | `interpolation_delaunay_2d`, `poisson_interpolation` | Points, lines and TriSurfs in any collection |
| Regularized grid surface (one only) | `regularized_grid_surface_interpolation` | Points, lines and TriSurfs in any collection |
| Implicit model (LoopStructural) | `implicit_model_loop_structural` | Points, lines and TriSurfs in Geology (age is needed) |
| Extrusion (View3D > Create), optional densification with internal sample lines | `linear_extrusion` | Last selected PolyLine/XsPolyLine in any collection |
| Intersection with cross-section (output in the source collection: PolyLine/XsPolyLine → XsVertexSet, TriSurf → XsPolyLine, DEM/TSDom → DomXs, Voxet → XsVoxet) | `intersection_xs` | PolyLine/XsPolyLine, TriSurf, DEM, TSDom, Voxet in any collection; boundary lines give no output (Boundaries cannot store points); TetraSolid is a placeholder, not implemented yet |
| Project to DEM, project to cross-section | `project_2_dem`, `project_2_xs` | Points and lines in Geology, Fluids, Backgrounds; lines in Boundaries; wells |
| Connected parts, split multipart | `connected_parts`, `split_multipart` | PolyLine and TriSurf in any collection; DOM point clouds |
| Merge to multipart (at least 2) | `entities_merge` | PolyLine/XsPolyLine in any collection |
| Calculate normals (Properties menu) | `normals_calculate` → `orientation_analysis.set_normals` | Geology entities and DOMs |
| Add / remove property | `property_add`, `property_remove` | Any entity (remove offers only properties present on all selected entities) |
| Add / remove texture | `texture_add`, `texture_remove` | DOMs |
| Build octree (Point Clouds menu) | `build_octree` | DOM point clouds (PCDom) |
| Point-cloud tools in the 3D view: cut, segment, auto-pick, threshold, decimate (one each) | `cut_pc`, `segment_pc`, `auto_pick`, `thresh_filt`, `decimate_selected_pc` | Last selected DOM point cloud (PCDom) |
| Point-cloud calibration in the 3D view | `calibration_pc` | DOM point clouds (PCDom) |
| Calculate Dip/Direction (Properties menu): dip and dip direction point properties from point normals (-90 < dip < 90, negative for overturned surfaces; standard dip direction) | `point_clouds.normals2dd` | Any entity with the Normals point property |
| Planar facets from PC clusters (Interpolation menu): one planar facet per ClusterId, output in Geology | `point_clouds.facets_pc` | Last selected DOM point cloud (PCDom) with ClusterId |
| Decimate point cloud (project window) | `decimate_pc_dialog` | DOM point clouds (PCDom) |
| Remove, clone, info, export (CAD, VTK, CSV), CRS transform | `entity_remove`, `entity_clone`, `show_info_on_entities`, `export_cad`, `export_vtk`, `export_csv`, `CRS_transform_selected` | Any entity |

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
