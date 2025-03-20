# PZero Architecture

PZero has 4 fundamental levels:

  - Entities
    Topo-geometrical objects (points, lines, surfaces, images).
		They are based on VTK classes.
    They are defined in pzero/entities_factory.py

  - Collections
    Sets of entities and metadata logically organized from a geological modelling point of view.
		They are Pandas dataframes.
		They are defined in pzero/collections/*
		See pzero/collections/README.md for more detail

	- Project window
		Main application window.
		Based on Qt (Pyside6).
		Implemented in pzero/project_window.py
		See pzero/ui/README.md.
		The graphics and actions are mostly designed using Designer
		with sources being pzero/gui/project_window.ui
		See GUI.md

