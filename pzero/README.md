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
- Ctrl+A selects all in a table or a tree; in the graphics of a view it selects the entities shown and deselects the hidden ones of that view (hiding alone does not deselect); Ctrl+Shift+A deselects all (Cmd on macOS);
- selected entities are highlighted in all VTK views (yellow outer border for surfaces, DEMs/DOMs and images, yellow lines and points, bounding box for point clouds and volumes);
- while a tool is running (`freeze_gui_on` / `freeze_gui_onoff`), selection by the user in tables and trees is frozen.

`collection.selected_uids` and `ProjectWindow.selected_uids` (collection of the tab in front) read from this store; `view.selected_uids` is the project selection restricted to the entities shown in that view.

### Which entities each tool uses

Tools that work on selected entities are decorated with `@uses_selection(...)` (`helpers/helper_functions.py`), which calls `ProjectWindow.restrict_selection_for_tool()` before the tool runs:

- **Mixed collections** (`cross_collection=True`): tools that modify or derive each entity independently, or cut entities with another one, use the usable entities of **all** the accepted collections together; **each output stays in the collection of its input** (e.g. moving geology and fluid lines together leaves each in its collection; a fluid line cut by a boundary entity gives fluid pieces). They read the uids with `tool_uids(self)` and the collection of each one with `entity_collection(self, uid)`.
- **One collection**: tools whose single output is built from several inputs (weld, merge to multipart, interpolations) use only one collection: the one of the tab in front if it contains usable entities, otherwise the one of the last selected usable entity. They read it with `active_collection(self)`.
- only entities of the accepted topologies are used; tools that work on a single entity use the **last selected** one;
- all other entities are **deselected**, and a message reports it; the tab of the collection of the last used entity is brought to front;
- if not enough usable entities are selected, the tool does not run and the selection is unchanged;
- for tools running in a view, entities not shown in that view are not usable;
- new entities created by split tools (split line by line, split at point, split surface, split multipart) and newly drawn lines are added to the selection; all parts of a split line are named with the `_split` suffix, and a welded line with `_weld`;
- tools whose inputs and outputs must belong to one cross-section (`same_parent=True`: merge to multipart, weld, snap) use only entities with the `parent_uid` of the last selected usable entity.

Outputs are stored in the collection of their input, with metadata copied by `derived_entity_dict()` / `entity_metadata_input_dict()` only for the fields that collection has (e.g. boundaries have no role and feature).

| Tools | Function(s) | Collections per run | Accepts |
|---|---|---|---|
| Line editing in 2D views: edit, extend, split at point (one line) | `two_d_lines.start_checked_line_tool` | Mixed | Last selected PolyLine/XsPolyLine in Geology, Fluids or Backgrounds |
| Copy parallel / kink / similar (one copy of each selected line, in its collection; the copies replace the lines in the selection) | `two_d_lines.copy_parallel`, `copy_kink`, `copy_similar` | Mixed | PolyLine/XsPolyLine in Geology, Fluids or Backgrounds; in cross-section views only lines of that section, in map views lines of any section |
| Line editing in 2D views: sort, move, rotate, resample, simplify | `two_d_lines.start_checked_line_tool` | Mixed | PolyLine/XsPolyLine in Geology, Fluids or Backgrounds |
| Split line by line (the last selected line cuts the others) | `two_d_lines.split_line_line` | Mixed | PolyLine/XsPolyLine in Geology, Fluids or Backgrounds; pieces stay in the collection of their line |
| Snap | `two_d_lines.snap_line` | Mixed | PolyLine/XsPolyLine in Geology, Fluids or Backgrounds, of the same cross-section (parent_uid) as the last selected line |
| Weld lines | `two_d_lines.merge_lines` | One | PolyLine/XsPolyLine in Geology, Fluids or Backgrounds, of the same cross-section as the last selected line |
| Smoothing, decimation (pro, quadric), subdivision, retopology | `surface_smoothing`, `decimation_pro_resampling`, `decimation_quadric_resampling`, `subdivision_resampling`, `retopo`, `smooth_dialog`, `subd_res_dialog`, `retopologize_surface` | Mixed | TriSurf in any collection |
| Retriangulate (one only) | `retriangulate_surface_dialog` | One | Last selected TriSurf in any collection |
| Split surface (at least 2, the last one cuts the others) | `split_surf` | Mixed | TriSurf in any collection; split surfaces stay in their collection |
| Delaunay 2D and Poisson interpolation | `interpolation_delaunay_2d`, `poisson_interpolation` | One | Points, lines and TriSurfs of one collection |
| Regularized grid surface (one only) | `regularized_grid_surface_interpolation` | One | Points, lines and TriSurfs in any collection |
| Implicit model (LoopStructural) | `implicit_model_loop_structural` | One | Points, lines and TriSurfs in Geology (age is needed) |
| Extrusion (View3D > Create), optional densification with internal sample lines | `linear_extrusion` | One | Last selected PolyLine/XsPolyLine in any collection |
| Intersection with cross-section (PolyLine/XsPolyLine → XsVertexSet, TriSurf → XsPolyLine, DEM/TSDom → DomXs, Voxet → XsVoxet) | `intersection_xs` | Mixed | PolyLine/XsPolyLine, TriSurf, DEM, TSDom, Voxet in any collection; boundary lines give no output (Boundaries cannot store points); TetraSolid is a placeholder, not implemented yet |
| Project to DEM/surface (vertical) onto a DEM, DOM surface or TriSurf of any collection; project to cross-section. Outputs become the selection | `project_2_dem`, `project_2_xs` | Mixed | Points and lines in Geology, Fluids, Backgrounds; lines in Boundaries; wells |
| Connected parts, split multipart | `connected_parts`, `split_multipart` | Mixed | PolyLine and TriSurf in any collection; DOM point clouds |
| Merge to multipart (Entities menu, at least 2; the merged entity is selected) | `entities_merge` | One | PolyData of one topology (VertexSet, XsVertexSet, PolyLine, XsPolyLine, TriSurf, PCDom, TSDom), with the same parent_uid (cross-section) as the last selected entity |
| Calculate normals (Properties menu): point sets from their dip/direction properties, TriSurfs, XsPolyLines and point clouds from geometry | `normals_calculate` → `orientation_analysis.set_normals` | Mixed | VertexSet, XsVertexSet, TriSurf, XsPolyLine, PCDom in any collection (not DEMs) |
| Calculate Dip/Direction (Properties menu): dip and dip direction point properties from point normals (0-90 for upright planes, > 90 for overturned planes) | `point_clouds.normals2dd` | Mixed | Any entity with the Normals point property |
| Invert normals (Properties menu): Normals n -> -n and/or dip -> 180 - dip, direction -> direction + 180 (both consistently if both present); TriSurf triangle order reversed so that Calculate Normals keeps it | `orientation_analysis.invert_polarity` | Mixed | Any entity with Normals and/or dip and dip direction point properties |
| Add / remove property | `property_add`, `property_remove` | Mixed | Any entity except cross-sections, which have no properties (remove offers only properties present on all selected entities) |
| Add / remove texture | `texture_add`, `texture_remove` | One | DOMs |
| Build octree (Point Clouds menu) | `build_octree` | One | DOM point clouds (PCDom) |
| Point-cloud tools in the 3D view: cut, segment, auto-pick, threshold, decimate (one each) | `cut_pc`, `segment_pc`, `auto_pick`, `thresh_filt`, `decimate_selected_pc` | One | Last selected DOM point cloud (PCDom) |
| Point-cloud calibration in the 3D view | `calibration_pc` | One | DOM point clouds (PCDom) |
| Planar facets from PC clusters (Interpolation menu): one planar facet per ClusterId, output in Geology | `point_clouds.facets_pc` | One | Last selected DOM point cloud (PCDom) with ClusterId |
| Decimate point cloud (project window) | `decimate_pc_dialog` | One | DOM point clouds (PCDom) |
| Remove, clone (any number and type of entities, including cross-sections; each clone in its own collection; the clones replace the originals in the selection), info, export VTK, CRS transform | `entity_remove`, `entity_clone`, `show_info_on_entities`, `export_vtk`, `CRS_transform_selected` | Mixed | Any entity |
| Export CSV | `export_csv` | One | Geology entities |
| Export CAD | `export_cad` | — | Not a selection tool (exports collections; GOCAD and OBJ use the selection of the tab in front) |

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
