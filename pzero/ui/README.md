# UI

This folder contains user interface (UI) modules for the PZero project. These modules define the graphical and interactive components of the application using PySide6. Generally the UI files are created with Designer and converted to Python code.

## File Overview

- `project_window_ui.py`  
  Auto-generated Python code from a Qt Designer `.ui` file for the main project window.  
  Defines the layout, menus, actions, and widgets for the main application interface, including tables, tabs, and toolbars for managing geology, fluids, backgrounds, DEMs/DOMs, images, meshes, boundaries, cross-sections, wells, legends, properties, and a terminal.

- `preview_window_ui.py`  
  Auto-generated Python code from a Qt Designer `.ui` file for the preview window.  
  Defines the layout and widgets for a preview dialog, including options, a preview button, OK/Cancel buttons, and a preview display area.

- `navigator_window_ui.py`  
  Auto-generated Python code from a Qt Designer `.ui` file for the navigator window.  
  Provides a minimal navigation interface with forward/back buttons and a section label, typically used for navigating between sections or steps in the application.

- `import_window_ui.py`  
  Auto-generated Python code from a Qt Designer `.ui` file for the import options window.  
  Defines the layout and widgets for importing data, including data preview, assignment tables, file path selection, separator options, and import controls.

- `dock_view_ui.py`  
  Auto-generated Python code from a Qt Designer `.ui` file for the dockable view window.  
  Provides a split interface with a toolbox for navigating geology, topology, cross-sections, boundaries, meshes, DEMs/DOMs, wells, fluids, backgrounds, and images, alongside a main view frame for displaying content.

- `base_view_window_ui.py`  
  Auto-generated Python code from a Qt Designer `.ui` file for the base view window.  
  Defines a main window with a horizontal splitter: a main view frame and a toolbox for navigating geology, fluids, backgrounds, DEMs/DOMs, images, meshes, boundaries, cross-sections, and wells. Includes a menu bar and status bar.

- `assign_ui.py`  
  Auto-generated Python code from a Qt Designer `.ui` file for the assign data window.  
  Provides a main window with a table for data assignment and a dialog button box for confirming or closing the assignment.

- `__init__.py`  
  Marks the folder as a Python package.  
  May contain package-level imports or initialization code (often empty).
