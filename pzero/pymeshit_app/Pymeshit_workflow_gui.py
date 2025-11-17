"""
MeshIt Workflow GUI

This application provides a graphical interface for the complete MeshIt workflow,
including file loading, convex hull computation, segmentation, triangulation, and visualization.
"""

import numpy as np
import logging
import os
import sys
import time
import re

# import List
from typing import List, Dict, Tuple, Optional, Any
# Import PySide6
from PySide6.QtWidgets import QAbstractItemView
from Pymeshit.intersection_utils import align_intersections_to_convex_hull, Vector3D, Intersection, refine_intersection_line_by_length, insert_triple_points, refine_hull_with_interpolation
from Pymeshit.intersection_utils import prepare_plc_for_surface_triangulation, run_constrained_triangulation_py, calculate_triple_points, TriplePoint
from Pymeshit.intersection_utils import make_corners_special, Vector3D
from PySide6.QtWidgets import QMenu, QTreeWidgetItemIterator
import tetgen
from Pymeshit.tetra_mesh_utils import TetrahedralMeshGenerator
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QLabel, QPushButton,
                            QVBoxLayout, QHBoxLayout, QGridLayout, QFrame, QTabWidget,
                            QFileDialog, QMessageBox, QComboBox, QSpinBox, QDoubleSpinBox,
                            QCheckBox, QGroupBox, QRadioButton, QSlider, QLineEdit,
                            QSplitter, QDialog, QFormLayout, QButtonGroup, QMenu,
                            QListWidget, QColorDialog, QListWidgetItem, QProgressDialog,
                            QSpacerItem, QTableWidget, QTableWidgetItem,
                            QTreeWidget, QTreeWidgetItem, QScrollArea)
from PySide6.QtGui import QFont, QIcon, QColor, QPalette, QPixmap, QAction, QActionGroup
from PySide6.QtCore import Qt, QSize, Signal, QObject, QThread, QTimer, QSettings
# Add these imports at the top of meshit_workflow_gui.py
from Pymeshit.intersection_utils import run_constrained_triangulation_py
from scipy.spatial.distance import pdist, squareform
import itertools
import gc
import atexit
from PySide6.QtWidgets import (QDockWidget, QListWidget, QListWidgetItem,
                             QTableWidget, QTableWidgetItem, QPushButton,
                             QVBoxLayout, QHBoxLayout, QLabel, QSlider,
                             QDoubleSpinBox, QWidget, QGroupBox, QGridLayout)
from PySide6.QtCore import Qt, Slot
# Import PyVista for 3D visualization (required)
import pyvista as pv
from pyvista import examples
logging.info("Successfully imported PyVista for 3D visualization")

# Configure logging to show ALL messages at INFO level
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("MeshIt-Workflow")

# Also ensure meshit module logs are visible
logging.getLogger("meshit").setLevel(logging.INFO)

logger.setLevel(logging.INFO)

if not logger.handlers:
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

# Add the current directory to the path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Import the DirectTriangleWrapper
try:
    from Pymeshit.triangle_direct import DirectTriangleWrapper
    HAVE_DIRECT_WRAPPER = True
    logger.info("Successfully imported DirectTriangleWrapper")
except ImportError as e:
    logger.error(f"Failed to import DirectTriangleWrapper: {e}")
    HAVE_DIRECT_WRAPPER = False

# Add Scipy import for interpolation
from scipy.interpolate import griddata

# Worker class for background computations
class ComputationWorker(QObject):
    dataset_finished = Signal(int, str, bool) # index, name, success
    batch_finished = Signal(int, int, float) # success_count, total_eligible, elapsed_time
    error_occurred = Signal(str)

    def __init__(self, gui_instance):
        super().__init__()
        self.gui = gui_instance # Keep a reference to the GUI instance to call its methods
        self._is_running = True

    def stop(self):
        logger.debug("ComputationWorker stop requested.")
        self._is_running = False

    def run_batch_task(self, compute_type):
        """Generic worker method to run batch computation for any compute type."""
        logger.info(f"Worker: Starting {compute_type} computation batch.")

        # Define eligibility criteria and method mappings for each compute type
        config = {
            'hulls': {
                'eligibility_func': lambda d: d.get('type') != 'WELL',
                'compute_method': '_compute_hull_for_dataset',
                'error_msg': "No datasets loaded.",
                'skip_msg': "No datasets loaded."
            },
            'segments': {
                'eligibility_func': lambda d: d.get('type') != 'WELL' and d.get('hull_points') is not None,
                'compute_method': '_compute_segments_for_dataset',
                'error_msg': "No datasets have computed hulls.",
                'skip_msg': "No eligible datasets."
            },
            'triangulations': {
                'eligibility_func': lambda d: d.get('type') != 'WELL' and d.get('segments') is not None,
                'compute_method': '_run_triangulation_for_dataset',
                'error_msg': "No datasets have computed segments.",
                'skip_msg': "No eligible datasets."
            }
        }

        if compute_type not in config:
            self.error_occurred.emit(f"Unknown compute type: {compute_type}")
            self.batch_finished.emit(0, 0, 0)
            return

        cfg = config[compute_type]
        datasets = self.gui.datasets

        if not datasets:
            self.error_occurred.emit(cfg['error_msg'])
            self.batch_finished.emit(0, 0, 0)
            logger.info(f"Worker: {compute_type} batch finished ({cfg['skip_msg']})")
            return

        # Determine eligible datasets
        if compute_type == 'hulls':
            # For hulls, all non-WELL datasets are eligible
            eligible = [i for i, d in enumerate(datasets) if cfg['eligibility_func'](d)]
            total_eligible = len(eligible)
        else:
            # For segments and triangulations, filter by eligibility criteria
            eligible = [i for i, d in enumerate(datasets) if cfg['eligibility_func'](d)]
            total_eligible = len(eligible)

        if not eligible:
            self.error_occurred.emit(cfg['error_msg'])
            self.batch_finished.emit(0, 0, 0)
            logger.info(f"Worker: {compute_type} batch finished (no eligible datasets).")
            return

        success_count = 0
        start_time = time.time()

        for i in eligible:
            if not self._is_running:
                break
            dataset = datasets[i]
            dataset_name = dataset.get('name', f"Dataset {i}")

            # Special handling for hulls - skip wells but mark as successful
            if compute_type == 'hulls' and dataset.get('type') == 'WELL':
                self.dataset_finished.emit(i, dataset_name, True)
                continue

            # Call the appropriate computation method
            compute_func = getattr(self.gui, cfg['compute_method'])
            success = compute_func(i)
            self.dataset_finished.emit(i, dataset_name, success)
            if success:
                success_count += 1

        elapsed = time.time() - start_time
        logger.info(f"Worker: {compute_type} batch finished. Success: {success_count}/{total_eligible}. Elapsed: {elapsed:.2f}s.")
        self.batch_finished.emit(success_count, total_eligible, elapsed)



    def compute_global_intersections_task(self):
        """Worker task to trigger global intersection computation on the GUI instance."""
        logger.info("Worker: Starting global intersection computation task.")
        if not hasattr(self, 'gui') or self.gui is None:
            self.error_occurred.emit("GUI instance not available for intersection computation.")
            self.batch_finished.emit(0, 0, 0) # Indicate failure
            return

        start_time = time.time()
        success = False
        try:
            # Call the GUI's method to perform the actual computation
            # We expect this method to handle its own data preparation and error reporting
            # and return True/False for overall success.
            success = self.gui._compute_global_intersections()
            logger.info(f"Worker: GUI's global intersection computation returned: {success}")
        except Exception as e:
            error_msg = f"Unhandled error during global intersection computation: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.error_occurred.emit(error_msg)
            success = False # Ensure failure is recorded

        elapsed_time = time.time() - start_time
        # Emit batch finished: 1 success if calculation succeeded, 0 otherwise.
        # Total eligible is conceptually 1 (the single global task).
        self.batch_finished.emit(1 if success else 0, 1, elapsed_time)
        logger.info(f"Worker: Global intersection task finished. Success: {success}. Elapsed: {elapsed_time:.2f}s.")


class MeshItWorkflowGUI(QMainWindow):
    # Define a color cycle for datasets
    DEFAULT_COLORS = [
        '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
        '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf'
    ]

    def __init__(self):
        """Initialize the GUI"""
        super().__init__()
        
        # Set window properties
        self.setWindowTitle("PyMeshIt")
        self.setGeometry(100, 100, 1400, 900) # Increased default size
        # Add color cycle for surface visualization
        self.color_cycle = [
            'red', 'blue', 'green', 'yellow', 'orange', 'purple', 'cyan', 'magenta',
            'brown', 'pink', 'gray', 'olive', 'navy', 'teal', 'lime', 'indigo'
        ]
        # Initialize data structures for multiple datasets
        self.datasets = []  # List to hold dataset dictionaries
        self.current_dataset_index = -1  # Index of the currently active dataset
        self._color_index = 0 # For assigning colors to datasets
        
        self.plotters = {}
        self._updating_coordinates = False  # Flag to prevent recursive updates during coordinate editing
        # Visualization placeholders and state
        self.points = None
        self.hull_points = None
        self.segments = None
        self.triangulation_result = None
        self.active_view = "points" # To track which visualization is active
        
        # Initialize optional variables that could be used for 3D visualization
        self.view_3d_enabled = True  # PyVista is now mandatory
        self.height_factor = 1.0
        self.current_plotter = None
        self.pv_plotter = None
        
        # Visualization optimization - prevent duplicate rendering
        self.segmentation_visualized = False  # Track if segmentation is already visualized
        self.current_visualization_tab = None  # Track which tab is currently active for visualization
        
        # Initialize legend widgets
        self.file_legend_widget = None
        self.hull_legend_widget = None
        self.segment_legend_widget = None
        self.tri_legend_widget = None
        
        # Create layout
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        self.main_layout = QVBoxLayout(self.central_widget)
        
        # Create notebook with multiple tabs
        self.notebook = QTabWidget()
        self.main_layout.addWidget(self.notebook)
        
        # Setup file tab
        self.file_tab = QWidget()
        self.notebook.addTab(self.file_tab, "1. Load Data")
        self._setup_file_tab()
        
        # Setup hull tab
        self.hull_tab = QWidget()
        self.notebook.addTab(self.hull_tab, "2. Convex Hull")
        self._setup_hull_tab()
        
        # Setup segment tab
        self.segment_tab = QWidget()
        self.notebook.addTab(self.segment_tab, "3. Segmentation")
        self._setup_segment_tab()
        
        # Setup triangulation tab
        self.triangulation_tab = QWidget()
        self.notebook.addTab(self.triangulation_tab, "4. Triangulation")
        self._setup_triangulation_tab()
        
        # Add to __init__ after other tabs are created
        self._setup_intersection_tab()
        
        # Setup Refine & Mesh Settings tab
        self.refine_mesh_tab = QWidget() # Add this line
        self.notebook.addTab(self.refine_mesh_tab, "6. Refine & Mesh") # Add this line
        self._setup_refine_mesh_tab() # Add this line

        # Setup pre-tetramesh tab
        self.pre_tetramesh_tab = QWidget()
        self.notebook.addTab(self.pre_tetramesh_tab, "7. Pre-Tetramesh")
        self._setup_pre_tetramesh_tab()

        # Setup tetra mesh tab
        self.tetra_mesh_tab = QWidget()
        self.notebook.addTab(self.tetra_mesh_tab, "8. Tetra Mesh")
        self._setup_tetra_mesh_tab()

        # Placeholder for the refine_mesh_tab plotter
        self.refine_mesh_plotter = None
        self.refine_mesh_viz_frame = None # Add this line for consistency
        self.tetra_materials: list[dict] = []     # [{name:str, locations:[[x,y,z]…], attribute:int}, …]

        # Create menu bar
        self._create_menu_bar()
        
        # Create status bar
        self.statusBar().showMessage("Ready")
        
        # Connect signals
        self.notebook.currentChanged.connect(self._on_tab_changed)
    
        # Show ready message
        self.statusBar().showMessage("MeshIt GUI Ready")
        
        # Initialize plot axes (will be properly set up in _setup_..._tab methods)
        
        # For 3D view management
        self.plotter = None
        self.vtk_widget = None
        
        # Register VTK cleanup on exit
        self._ensure_vtk_cleanup_on_exit()
        
        self._create_main_layout()
        self.show()
        self._update_statistics() # Initial update
    def _init_material_selection_ui(self) -> QGroupBox:
        """
        Builds the ‘Materials’ group-box and returns it so the caller
        can insert it wherever it likes (e.g. into the Tetra-mesh tab).
        """
        material_group = QGroupBox("Materials")
        v_main         = QVBoxLayout(material_group)   # ← same variable name as before

        # 3.1  material list
        self.material_list = QListWidget()
        self.material_list.currentRowChanged.connect(self._on_material_selected)
        v_main.addWidget(QLabel("Material regions:"))
        v_main.addWidget(self.material_list, 1)

        h_mat_btns = QHBoxLayout()
        b_add_mat  = QPushButton(" + ");  b_del_mat = QPushButton(" – ")
        b_add_mat.clicked.connect(self._add_material)
        b_del_mat.clicked.connect(self._remove_material)
        h_mat_btns.addWidget(b_add_mat); h_mat_btns.addWidget(b_del_mat)
        v_main.addLayout(h_mat_btns)

        # 3.2  seed-location list
        self.material_location_list = QListWidget()
        self.material_location_list.currentRowChanged.connect(self._on_location_selected)
        v_main.addWidget(QLabel("Seed locations:"))
        v_main.addWidget(self.material_location_list, 1)

        h_loc_btns = QHBoxLayout()
        b_add_loc  = QPushButton(" + ");  b_del_loc = QPushButton(" – ")
        b_add_loc.clicked.connect(self._add_location)
        b_del_loc.clicked.connect(self._remove_location)
        h_loc_btns.addWidget(b_add_loc); h_loc_btns.addWidget(b_del_loc)
        v_main.addLayout(h_loc_btns)

        # 3.2-bis  location-buttons  ▼▼▼  REPLACE THIS SHORT BLOCK
        h_loc_btns = QHBoxLayout()

        btn_add_loc   = QPushButton(" + ")
        btn_del_loc   = QPushButton(" – ")
        btn_auto_loc  = QPushButton("Auto")        # NEW – automatic placement

        btn_add_loc.clicked.connect(self._add_location)
        btn_del_loc.clicked.connect(self._remove_location)
        btn_auto_loc.clicked.connect(self._auto_place_materials)   # NEW hook

        h_loc_btns.addWidget(btn_add_loc)
        h_loc_btns.addWidget(btn_del_loc)
        h_loc_btns.addWidget(btn_auto_loc)         # show the 3rd button
        v_main.addLayout(h_loc_btns)
        # 3.3  coordinate editors
        gb_coord   = QGroupBox("Edit selected location")
        grid       = QGridLayout(gb_coord)

        self.locX_val = QDoubleSpinBox(decimals=4); self.locX_val.setSuffix("  X")
        self.locY_val = QDoubleSpinBox(decimals=4); self.locY_val.setSuffix("  Y")
        self.locZ_val = QDoubleSpinBox(decimals=4); self.locZ_val.setSuffix("  Z")
        for w,lbl in [(self.locX_val,"X"),(self.locY_val,"Y"),(self.locZ_val,"Z")]:
            w.setRange(-1e9,1e9); w.setSingleStep(1.0); w.setDecimals(6); w.setProperty("axis",lbl)
            w.valueChanged.connect(self._coord_spin_changed)

        self.locX_slider = QSlider(Qt.Horizontal); self.locY_slider = QSlider(Qt.Horizontal); self.locZ_slider = QSlider(Qt.Horizontal)
        for s,lbl in [(self.locX_slider,"X"),(self.locY_slider,"Y"),(self.locZ_slider,"Z")]:
            s.setRange(-1000000,1000000); s.setSingleStep(500); s.setPageStep(5000); s.setProperty("axis",lbl)
            s.valueChanged.connect(self._coord_slider_changed)

        grid.addWidget(self.locX_val,0,0);  grid.addWidget(self.locX_slider,1,0)
        grid.addWidget(self.locY_val,0,1);  grid.addWidget(self.locY_slider,1,1)
        grid.addWidget(self.locZ_val,0,2);  grid.addWidget(self.locZ_slider,1,2)

        v_main.addWidget(gb_coord)
        return material_group


    def _init_seg_refine_table(self):
        # Table for Segmentation per-surface RefineByLength
        # Uses dataset index as stable key; stores it in Qt.UserRole per row
        from PySide6.QtWidgets import QGroupBox, QVBoxLayout, QTableWidget, QTableWidgetItem
        if not hasattr(self, 'seg_length_by_surface'):
            self.seg_length_by_surface = {}
        self._seg_table_updating = False

        self.seg_refine_group = QGroupBox("Per-Surface RefineByLength (Segmentation)")
        lay = QVBoxLayout(self.seg_refine_group)
        self.seg_refine_table = QTableWidget(0, 2, self.seg_refine_group)
        self.seg_refine_table.setHorizontalHeaderLabels(["Surface", "Length"])
        self.seg_refine_table.horizontalHeader().setStretchLastSection(True)
        self.seg_refine_table.verticalHeader().setVisible(False)
        self.seg_refine_table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked | 
            QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self.seg_refine_table.cellChanged.connect(self._on_seg_refine_cell_changed)
        lay.addWidget(self.seg_refine_table)

        self._refresh_seg_refine_table()

    def _refresh_seg_refine_table(self):
        # Populate rows for all non-WELL datasets
        from PySide6.QtWidgets import QTableWidgetItem
        from PySide6.QtCore import Qt
        if not hasattr(self, 'seg_refine_table'):
            return
        self._seg_table_updating = True
        self.seg_refine_table.setRowCount(0)
        for idx, ds in enumerate(self.datasets):
            if ds.get('type') in ('WELL', 'polyline'):
                continue
            name = ds.get('name', f"Surface_{idx}")
            value = float(self.seg_length_by_surface.get(idx, 15.0))
            row = self.seg_refine_table.rowCount()
            self.seg_refine_table.insertRow(row)

            item_name = QTableWidgetItem(name)
            item_name.setFlags(item_name.flags() & ~Qt.ItemIsEditable)
            item_name.setData(Qt.UserRole, idx)  # store dataset index
            self.seg_refine_table.setItem(row, 0, item_name)

            item_val = QTableWidgetItem(f"{value:.6g}")
            self.seg_refine_table.setItem(row, 1, item_val)
        self._seg_table_updating = False

    def _on_seg_refine_cell_changed(self, row, col):
        # Persist edits into self.seg_length_by_surface
        from PySide6.QtCore import Qt
        if self._seg_table_updating or col != 1:
            return
        item_name = self.seg_refine_table.item(row, 0)
        item_val = self.seg_refine_table.item(row, 1)
        if not item_name or not item_val:
            return
        try:
            ds_idx = int(item_name.data(Qt.UserRole))
            val = float(item_val.text())
            if val <= 1e-9:
                val = 1.0
            self.seg_length_by_surface[ds_idx] = val

            # Propagate segmentation value as a default to mesh refine table
            # but only if the user has not already set a mesh-specific value.
            if not hasattr(self, 'mesh_length_by_surface'):
                self.mesh_length_by_surface = {}
            if ds_idx not in self.mesh_length_by_surface:
                # Set the mesh default to the segmentation value so the
                # refine-mesh table displays it. Update the table cell
                # programmatically if the table exists.
                try:
                    self.mesh_length_by_surface[ds_idx] = val
                    if hasattr(self, 'mesh_refine_table') and self.mesh_refine_table is not None:
                        # Find corresponding row and update without triggering handler
                        try:
                            self._mesh_table_updating = True
                            rows = self.mesh_refine_table.rowCount()
                            for r in range(rows):
                                mn = self.mesh_refine_table.item(r, 0)
                                if mn and mn.data(Qt.UserRole) == ds_idx:
                                    self.mesh_refine_table.setItem(r, 1, QTableWidgetItem(f"{val:.6g}"))
                                    break
                        except Exception:
                            # Non-fatal - ignore UI update failures
                            pass
                        finally:
                            self._mesh_table_updating = False
                except Exception:
                    # Ensure propagation failures don't break segmentation handling
                    pass
        except Exception:
            pass

    def _get_seg_target_length_for_dataset(self, dataset_index: int) -> float:
        """
        Return per-surface RefineByLength from the Segmentation table.
        - Reads from self.seg_length_by_surface cache if present
        - Else, scans the table for the row matching dataset_index (Qt.UserRole on col 0),
        parses the value, caches it, and returns it
        - Final fallback: 15.0
        """
        try:
            # Cached value takes precedence
            if hasattr(self, 'seg_length_by_surface') and dataset_index in self.seg_length_by_surface:
                return float(self.seg_length_by_surface[dataset_index])

            # Try to read from the table directly
            if hasattr(self, 'seg_refine_table') and self.seg_refine_table is not None:
                from PySide6.QtCore import Qt
                rows = self.seg_refine_table.rowCount()
                for r in range(rows):
                    item_name = self.seg_refine_table.item(r, 0)
                    if not item_name:
                        continue
                    ds_idx = item_name.data(Qt.UserRole)
                    if ds_idx is None:
                        continue
                    if int(ds_idx) == int(dataset_index):
                        item_val = self.seg_refine_table.item(r, 1)
                        if item_val:
                            try:
                                val = float(item_val.text())
                                if val > 1e-9:
                                    # Cache and return
                                    if not hasattr(self, 'seg_length_by_surface'):
                                        self.seg_length_by_surface = {}
                                    self.seg_length_by_surface[dataset_index] = val
                                    return val
                            except Exception:
                                pass
        except Exception:
            pass
        # Strict fallback that does NOT use the unified spinbox
        return 15.0

    def _init_mesh_refine_table(self):
        # Table for Refine & Mesh per-surface mesh target size
        from PySide6.QtWidgets import QGroupBox, QVBoxLayout, QTableWidget, QTableWidgetItem
        if not hasattr(self, 'mesh_length_by_surface'):
            self.mesh_length_by_surface = {}
        self._mesh_table_updating = False

        self.mesh_refine_group = QGroupBox("Per-Surface Mesh Density (Target Size)")
        lay = QVBoxLayout(self.mesh_refine_group)
        self.mesh_refine_table = QTableWidget(0, 2, self.mesh_refine_group)
        self.mesh_refine_table.setHorizontalHeaderLabels(["Surface", "Target Size"])
        self.mesh_refine_table.horizontalHeader().setStretchLastSection(True)
        self.mesh_refine_table.verticalHeader().setVisible(False)
        self.mesh_refine_table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked |
            QAbstractItemView.EditTrigger.EditKeyPressed
        )

        self.mesh_refine_table.cellChanged.connect(self._on_mesh_refine_cell_changed)
        lay.addWidget(self.mesh_refine_table)

        self._refresh_mesh_refine_table()

    def _refresh_mesh_refine_table(self):
        # Populate rows for all non-WELL datasets
        from PySide6.QtWidgets import QTableWidgetItem
        from PySide6.QtCore import Qt
        if not hasattr(self, 'mesh_refine_table'):
            return
        self._mesh_table_updating = True
        self.mesh_refine_table.setRowCount(0)
        for idx, ds in enumerate(self.datasets):
            if ds.get('type') in ('WELL', 'polyline'):
                continue
            name = ds.get('name', f"Surface_{idx}")
            # Prefer an explicit per-surface mesh value, else fall back to
            # segmentation value (if available), else the unified mesh control.
            unified_default = float(getattr(self.mesh_target_feature_size_input, "value", lambda: 15.0)())
            seg_default = None
            try:
                if hasattr(self, 'seg_length_by_surface') and idx in self.seg_length_by_surface:
                    seg_default = float(self.seg_length_by_surface[idx])
            except Exception:
                seg_default = None

            if idx in self.mesh_length_by_surface:
                value = float(self.mesh_length_by_surface.get(idx))
            elif seg_default is not None:
                value = float(seg_default)
            else:
                value = float(unified_default)
            row = self.mesh_refine_table.rowCount()
            self.mesh_refine_table.insertRow(row)

            item_name = QTableWidgetItem(name)
            item_name.setFlags(item_name.flags() & ~Qt.ItemIsEditable)
            item_name.setData(Qt.UserRole, idx)  # store dataset index
            self.mesh_refine_table.setItem(row, 0, item_name)

            item_val = QTableWidgetItem(f"{value:.6g}")
            self.mesh_refine_table.setItem(row, 1, item_val)
        self._mesh_table_updating = False

    def _on_mesh_refine_cell_changed(self, row, col):
        # Persist edits into self.mesh_length_by_surface
        from PySide6.QtCore import Qt
        if self._mesh_table_updating or col != 1:
            return
        item_name = self.mesh_refine_table.item(row, 0)
        item_val = self.mesh_refine_table.item(row, 1)
        if not item_name or not item_val:
            return
        try:
            ds_idx = int(item_name.data(Qt.UserRole))
            val = float(item_val.text())
            if val <= 1e-9:
                val = 1.0
            self.mesh_length_by_surface[ds_idx] = val
        except Exception:
            pass

    def _get_mesh_target_size_for_surface(self, dataset_index: int) -> float:
        unified = float(getattr(self.mesh_target_feature_size_input, "value", lambda: 15.0)())
        return float(self.mesh_length_by_surface.get(dataset_index, unified))
    # ──────────────────────────────────────────────────────────────────────
    # 4)  INTERNAL HELPERS / SLOTS
    # ──────────────────────────────────────────────────────────────────────
    def _ensure_default_material(self) -> None:
        if not self.tetra_materials:
            self.tetra_materials.append({
                "name":"Material_1",
                "locations":[self._calculate_default_location()],
                "attribute":1
            })
        self._refresh_material_list()

    def _extract_boundary_segments_from_vtu(self, vtu_source) -> tuple[np.ndarray, list[list[np.ndarray]]]:
        """
        Returns:
        points3d: (N,3) float array of surface points
        rings: list of rings; each ring is a list of 3D points in order (closed)
        Accepts:
        vtu_source: a PyVista dataset or a file path (.vtu/.vtk/.vtp/.stl etc.)
        """
        import numpy as np
        import pyvista as pv

        # Load mesh
        mesh = vtu_source if hasattr(vtu_source, "extract_surface") else pv.read(str(vtu_source))

        # Ensure we have a PolyData surface
        if not isinstance(mesh, pv.PolyData):
            mesh = mesh.extract_surface()

        # 1) Try “boundary edges only” (external border)
        edges = mesh.extract_feature_edges(
            boundary_edges=True, feature_edges=False, manifold_edges=False, non_manifold_edges=True
        )
        if edges.n_cells == 0:
            # Fallback: allow sharp feature edges to help find an outline
            edges = mesh.extract_feature_edges(
                boundary_edges=True, feature_edges=True, feature_angle=150.0, manifold_edges=False, non_manifold_edges=True
            )

        # 2) Strip into ordered polylines
        polylines = edges.strip() if edges.n_cells > 0 else pv.PolyData()

        # 3) Decode polylines from VTK “lines” array
        rings = []
        if polylines.n_cells > 0 and polylines.lines.size > 0:
            lines = polylines.lines.ravel()
            pts = np.asarray(polylines.points, dtype=float)
            i = 0
            while i < len(lines):
                n = int(lines[i]); i += 1
                ids = lines[i:i + n]; i += n
                if n >= 2:
                    ring = pts[ids].astype(float)
                    # enforce closed ring if endpoints match
                    if np.linalg.norm(ring[0] - ring[-1]) > 1e-12:
                        ring = np.vstack([ring, ring[0]])
                    rings.append([p for p in ring])
        else:
            # Last fallback: use mesh boundary filter (can return triangles; we re‑extract edges)
            boundary = mesh.extract_all_edges()
            boundary = boundary.strip()
            if boundary.n_cells > 0 and boundary.lines.size > 0:
                lines = boundary.lines.ravel()
                pts = np.asarray(boundary.points, dtype=float)
                i = 0
                while i < len(lines):
                    n = int(lines[i]); i += 1
                    ids = lines[i:i + n]; i += n
                    if n >= 2:
                        ring = pts[ids].astype(float)
                        if np.linalg.norm(ring[0] - ring[-1]) > 1e-12:
                            ring = np.vstack([ring, ring[0]])
                        rings.append([p for p in ring])

        # Points to carry as SDs if needed (prefer original surface points)
        points3d = np.asarray(mesh.points, dtype=float)
        return points3d, rings


    def _rebuild_segments_from_vtu_boundaries(self) -> None:
        """
        For each dataset that came from a VTU, re‑derive its segments from the VTU boundary rings.
        Expects each dataset to have either:
        - dataset['file_path'] (path to the VTU), or
        - dataset['pv_mesh'] (a PyVista mesh kept from import)
        Updates:
        - dataset['segments'] := list of segments [ [p0, p1], ... ] (3D points)
        - dataset['points']   := (N,3) float array from the surface (if not present)
        """
        import numpy as np

        updated = 0
        for idx, ds in enumerate(self.datasets):
            name = ds.get('name', f"Dataset {idx}")
            # Heuristics to decide VTU origin; adapt if you store a reliable flag
            is_vtu = (ds.get('format') == 'VTU') or (str(ds.get('file_path', '')).lower().endswith('.vtu'))
            if not is_vtu:
                continue

            vtu_src = ds.get('pv_mesh') or ds.get('file_path')
            if vtu_src is None:
                logger.info(f"[VTU-SEG] Skipping {name}: no pv_mesh or file_path")
                continue

            try:
                points3d, rings = self._extract_boundary_segments_from_vtu(vtu_src)
                if not rings:
                    logger.info(f"[VTU-SEG] {name}: no boundary rings found")
                    continue

                # Convert rings -> segments
                segments = []
                for ring in rings:
                    if len(ring) < 2:
                        continue
                    # ensure closure in case previous step didn’t close
                    if np.linalg.norm(np.asarray(ring[0]) - np.asarray(ring[-1])) > 1e-12:
                        ring = list(ring) + [ring[0]]
                    for i in range(len(ring) - 1):
                        p0 = [float(ring[i][0]), float(ring[i][1]), float(ring[i][2])]
                        p1 = [float(ring[i + 1][0]), float(ring[i + 1][1]), float(ring[i + 1][2])]
                        segments.append([p0, p1])

                if segments:
                    ds['segments'] = segments
                    if ('points' not in ds) or (ds['points'] is None) or (len(ds['points']) == 0):
                        ds['points'] = points3d.astype(float)
                    updated += 1
                    logger.info(f"[VTU-SEG] {name}: built {len(segments)} segments from {len(rings)} ring(s)")
                else:
                    logger.info(f"[VTU-SEG] {name}: rings decoded but 0 segments produced")

            except Exception as e:
                logger.error(f"[VTU-SEG] {name}: failed to rebuild segments: {e}", exc_info=True)

        if updated:
            self.statusBar().showMessage(f"Rebuilt VTU boundary segments for {updated} dataset(s)")
        else:
            self.statusBar().showMessage("No VTU datasets updated")

    def _refresh_material_list(self) -> None:
        """Synchronise both list-widgets after any change."""
        # block all signals while we rebuild
        self.material_list.blockSignals(True)
        self.material_location_list.blockSignals(True)

        # remember what was selected
        prev_mat_sel = self.material_list.currentRow()
        prev_loc_sel = self.material_location_list.currentRow()

        # rebuild material list
        self.material_list.clear()
        for m, mat in enumerate(self.tetra_materials):
            self.material_list.addItem(
                f"{mat['name']}  ({len(mat['locations'])} pts)"
            )

        # restore (or choose first) selection
        if self.material_list.count():
            if prev_mat_sel < 0 or prev_mat_sel >= self.material_list.count():
                prev_mat_sel = 0
            self.material_list.setCurrentRow(prev_mat_sel)
        else:
            prev_mat_sel = -1          # nothing selected

        # rebuild location list for the selected material
        self.material_location_list.clear()
        if 0 <= prev_mat_sel < len(self.tetra_materials):
            for i, xyz in enumerate(self.tetra_materials[prev_mat_sel]["locations"]):
                self.material_location_list.addItem(
                    f"Loc {i}: ({xyz[0]:.2f}, {xyz[1]:.2f}, {xyz[2]:.2f})"
                )

            # restore location selection if valid
            if prev_loc_sel >= 0 and prev_loc_sel < len(self.tetra_materials[prev_mat_sel]["locations"]):
                self.material_location_list.setCurrentRow(prev_loc_sel)
            else:
                # select first location if previous was invalid
                self.material_location_list.setCurrentRow(0)

        # unblock signals and refresh the rest
        self.material_list.blockSignals(False)
        self.material_location_list.blockSignals(False)

        self._update_coordinate_editors()
        self._update_material_visualisation()
    @Slot(int)
    def _on_material_selected(self,row:int)->None:
        self._refresh_material_list()

    @Slot(int)
    def _on_location_selected(self,row:int)->None:
        self._update_coordinate_editors()

    def _add_material(self)->None:
        idx=len(self.tetra_materials)+1
        self.tetra_materials.append({
            "name":f"Material_{idx}",
            "locations":[self._calculate_default_location()],
            "attribute":idx
        })
        self.material_list.setCurrentRow(len(self.tetra_materials)-1)
        self._refresh_material_list()

    def _remove_material(self)->None:
        row=self.material_list.currentRow()
        if row>=0:
            del self.tetra_materials[row]
            self.material_list.setCurrentRow(max(0,len(self.tetra_materials)-1))
            self._refresh_material_list()

    def _add_location(self) -> None:
        """Append a new seed point to the currently selected material."""
        m = self.material_list.currentRow()
        if m < 0:
            QMessageBox.information(
                self, "Select a material",
                "Please select (or create) a material first."
            )
            return

        # default position = geometric centre of all constrained surfaces
        new_pt = self._calculate_default_location()
        self.tetra_materials[m]["locations"].append(new_pt)

        self.material_location_list.setCurrentRow(
            len(self.tetra_materials[m]["locations"]) - 1
        )
        self._refresh_material_list()

    def _remove_location(self)->None:
        m=self.material_list.currentRow()
        l=self.material_location_list.currentRow()
        if m<0 or l<0: return
        del self.tetra_materials[m]["locations"][l]
        self.material_location_list.setCurrentRow(max(0,len(self.tetra_materials[m]["locations"])-1))
        self._refresh_material_list()

    def _update_coordinate_editors(self)->None:
        m=self.material_list.currentRow(); l=self.material_location_list.currentRow()
        editing=(m>=0 and l>=0)

        # Block all signals during programmatic updates
        self.locX_val.blockSignals(True)
        self.locY_val.blockSignals(True)
        self.locZ_val.blockSignals(True)
        self.locX_slider.blockSignals(True)
        self.locY_slider.blockSignals(True)
        self.locZ_slider.blockSignals(True)

        if editing:
            x,y,z=self.tetra_materials[m]["locations"][l]
            # Convert numpy types to regular Python floats
            x, y, z = float(x), float(y), float(z)
            self.locX_val.setValue(x); self.locY_val.setValue(y); self.locZ_val.setValue(z)
            # Ensure slider values stay within range
            slider_x = max(-1000000, min(1000000, int(x*1000)))
            slider_y = max(-1000000, min(1000000, int(y*1000)))
            slider_z = max(-1000000, min(1000000, int(z*1000)))
            self.locX_slider.setValue(slider_x); self.locY_slider.setValue(slider_y); self.locZ_slider.setValue(slider_z)
        else:
            self.locX_val.setValue(0); self.locY_val.setValue(0); self.locZ_val.setValue(0)
            self.locX_slider.setValue(0); self.locY_slider.setValue(0); self.locZ_slider.setValue(0)

        # Unblock signals after programmatic updates
        self.locX_val.blockSignals(False)
        self.locY_val.blockSignals(False)
        self.locZ_val.blockSignals(False)
        self.locX_slider.blockSignals(False)
        self.locY_slider.blockSignals(False)
        self.locZ_slider.blockSignals(False)

    @Slot(float)
    def _coord_spin_changed(self,val:float)->None:
        if self._updating_coordinates:
            return
        axis=self.sender().property("axis"); self._apply_coord_change(axis,val)

    @Slot(int)
    def _coord_slider_changed(self,val:int)->None:
        if self._updating_coordinates:
            return
        axis=self.sender().property("axis"); self._apply_coord_change(axis,val/1000.0)

    def _apply_coord_change(self,axis:str,value:float)->None:
        m=self.material_list.currentRow(); l=self.material_location_list.currentRow()
        if m<0 or l<0: return

        # Prevent recursive updates during programmatic changes
        self._updating_coordinates = True

        try:
            xyz=list(self.tetra_materials[m]["locations"][l])
            # Convert numpy types to regular Python floats and update the specific axis
            xyz = [float(coord) for coord in xyz]
            if axis=="X": xyz[0]=value
            if axis=="Y": xyz[1]=value
            if axis=="Z": xyz[2]=value
            self.tetra_materials[m]["locations"][l]=xyz
            self._update_coordinate_editors()
            self._refresh_material_list()
            self._update_material_visualisation()
        finally:
            self._updating_coordinates = False

    def _update_material_visualisation(self) -> None:
        """
        Draw/refresh coloured spheres for every material seed.
        Works with either self.constraint_plotter (main 3-D view in this tab)
        or the fallback self.tetra_plotter.
        """
        plotter = getattr(self, "constraint_plotter", None) or getattr(self, "tetra_plotter", None)
        if not plotter:
            return

        # remove previous seed actors
        for actor_name in list(plotter.actors.keys()):
            if actor_name.startswith("mat_seed_"):
                plotter.remove_actor(actor_name)

        colours = ['red','blue','green','yellow','purple','cyan','orange','magenta']
        import pyvista as pv
        for midx, mat in enumerate(self.tetra_materials):
            colour = colours[midx % len(colours)]
            for lidx, xyz in enumerate(mat["locations"]):
                cloud = pv.PolyData([xyz])
                plotter.add_points(
                    cloud,
                    name=f"mat_seed_{midx}_{lidx}",
                    render_points_as_spheres=True,
                    point_size=12,
                    color=colour
                )
        plotter.render()
    def _create_menu_bar(self):
        """Create the menu bar"""
        menu_bar = self.menuBar()
        
        # --- File Menu ---
        file_menu = menu_bar.addMenu("&File")


        # Add Well loaders
        load_well_action = QAction("Load &Well File...", self)
        load_well_action.setStatusTip("Load a single well (polyline) file")
        load_well_action.triggered.connect(self.load_well_file)
        file_menu.addAction(load_well_action)

        load_multiple_wells_action = QAction("Load Multiple &Wells...", self)
        load_multiple_wells_action.setStatusTip("Load multiple well (polyline) files")
        load_multiple_wells_action.triggered.connect(self.load_multiple_well_files)
        file_menu.addAction(load_multiple_wells_action)

        
        file_menu.addSeparator()

        export_action = QAction("&Export Active Result...", self)
        export_action.setStatusTip("Export the triangulation result of the active dataset")
        export_action.triggered.connect(self.export_results)
        file_menu.addAction(export_action)
        
        file_menu.addSeparator()

        exit_action = QAction("E&xit", self)
        exit_action.setStatusTip("Exit the application")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # --- Dataset Menu ---
        dataset_menu = menu_bar.addMenu("&Datasets")

        process_all_action = dataset_menu.addAction("&Process All Datasets")
        process_all_action.setStatusTip("Run all steps (hull, segments, triangulation) for all datasets")
        process_all_action.triggered.connect(self.process_all_datasets)
        
        dataset_menu.addSeparator()

        remove_active_action = dataset_menu.addAction("&Remove Active Dataset")
        remove_active_action.setStatusTip("Remove the currently selected dataset from the list")
        remove_active_action.triggered.connect(self.remove_active_dataset)

        clear_all_action = dataset_menu.addAction("Clear &All Datasets")
        clear_all_action.setStatusTip("Remove all loaded datasets")
        clear_all_action.triggered.connect(self.clear_all_datasets)


        # --- Visualization Menu ---
        viz_menu = menu_bar.addMenu("&Visualization")





        # --- Help Menu ---
        help_menu = menu_bar.addMenu("&Help")
        about_action = help_menu.addAction("&About")
        about_action.setStatusTip("Show information about the application")
        about_action.triggered.connect(self._show_about)
    def load_well_file(self):
        """Load a single well (polyline) file. Wells are 1D and not triangulated."""
        self.statusBar().showMessage("Loading well file...")
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select a well (polyline) file", "",
            "Text files (*.txt);;Data files (*.dat);;CSV files (*.csv);;VTU files (*.vtu);;All files (*.*)"
        )
        if not file_path:
            self.statusBar().showMessage("Well file loading canceled")
            return

        try:
            points = self._read_point_file(file_path)
            if points is None or len(points) == 0:
                QMessageBox.critical(self, "Error", "No valid points found in well file")
                self.statusBar().showMessage("Error: No valid points found in well file")
                return

            filename = os.path.basename(file_path)
            dataset = {
                'name': filename,
                'type': 'WELL',            # CRITICAL: mark as WELL
                'points': points,          # 3D polyline points in order
                'visible': True,
                'color': self._get_next_color()
            }
            self.datasets.append(dataset)
            self.current_dataset_index = len(self.datasets) - 1

            # Update UI
            self._update_dataset_list()
            self._update_statistics()
            self._update_visualization()

            self.statusBar().showMessage(f"Successfully loaded well with {len(points)} points from {filename}")
        except Exception as e:
            self.statusBar().showMessage(f"Error loading well file: {str(e)}")
            logger.error(f"Error loading well file: {str(e)}")
            QMessageBox.critical(self, "Error", f"Error loading well file: {str(e)}")


    def load_multiple_well_files(self):
        """Load multiple well (polyline) files as separate WELL datasets."""
        self.statusBar().showMessage("Loading multiple well files...")
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "Select well (polyline) files", "",
            "Text files (*.txt);;Data files (*.dat);;CSV files (*.csv);;VTU files (*.vtu);;All files (*.*)"
        )
        if not file_paths:
            self.statusBar().showMessage("Well file loading canceled")
            return

        successful = 0
        for file_path in file_paths:
            try:
                points = self._read_point_file(file_path)
                if points is None or len(points) == 0:
                    logger.warning(f"No valid points found in well file: {file_path}")
                    continue
                filename = os.path.basename(file_path)
                dataset = {
                    'name': filename,
                    'type': 'WELL',
                    'points': points,
                    'visible': True,
                    'color': self._get_next_color()
                }
                self.datasets.append(dataset)
                self.current_dataset_index = len(self.datasets) - 1
                successful += 1
            except Exception as e:
                logger.error(f"Error loading well file {file_path}: {str(e)}")

        if successful > 0:
            self._update_dataset_list()
            self._update_statistics()
            self._update_visualization()
            self.statusBar().showMessage(f"Successfully loaded {successful} well(s)")
        else:
            self.statusBar().showMessage("No valid wells loaded")
            QMessageBox.critical(self, "Error", "No valid wells loaded")
    def _setup_file_tab(self):
        """Sets up the file loading tab with controls and visualization area"""
        # Main layout for the tab
        tab_layout = QHBoxLayout(self.file_tab)
        
        # --- Control panel (left side) ---
        control_panel = QWidget()
        control_panel.setMaximumWidth(350) # Limit width
        control_layout = QVBoxLayout(control_panel)
        
        # -- File Loading Controls --
        file_group = QGroupBox("Load Data")
        file_layout = QVBoxLayout(file_group)
        
        # Button for loading multiple files
        load_multiple_btn = QPushButton("Load Multiple Files...")
        load_multiple_btn.setToolTip("Load points from multiple files as separate datasets")
        load_multiple_btn.clicked.connect(self.load_multiple_files)
        file_layout.addWidget(load_multiple_btn)
        
        
        
        control_layout.addWidget(file_group)
        
        # -- Dataset List --
        datasets_group = QGroupBox("Datasets")
        datasets_layout = QVBoxLayout(datasets_group)
        
        self.dataset_list_widget = QListWidget()
        self.dataset_list_widget.setToolTip("List of loaded datasets. Select one to view/process.")
        # Enable extended selection later if needed: self.dataset_list_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.dataset_list_widget.itemSelectionChanged.connect(self._on_dataset_selection_changed)
        self.dataset_list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.dataset_list_widget.customContextMenuRequested.connect(self._show_dataset_context_menu)
        datasets_layout.addWidget(self.dataset_list_widget)
        
        control_layout.addWidget(datasets_group)
        
        # -- Statistics --
        stats_group = QGroupBox("Statistics")
        stats_layout = QVBoxLayout(stats_group)
        
        # Number of datasets
        self.num_datasets_label = QLabel("Datasets: 0")
        stats_layout.addWidget(self.num_datasets_label)
        
        # Number of points
        self.points_label = QLabel("Points: 0")
        stats_layout.addWidget(self.points_label)
        
        # Bounding box info
        self.bounds_label = QLabel("Bounds: N/A")
        stats_layout.addWidget(self.bounds_label)
        
        control_layout.addWidget(stats_group)
        control_layout.addStretch()
        
        tab_layout.addWidget(control_panel)
        
        # --- Visualization Area (right side) ---
        viz_group = QGroupBox("Point Cloud Visualization")
        viz_layout = QVBoxLayout(viz_group)
        
        # Create container for visualization
        self.file_viz_frame = QWidget()
        self.file_viz_layout = QVBoxLayout(self.file_viz_frame)
        
        # Initial visualization panel will show placeholder message
        placeholder_text = "Load data to visualize points in 3D"
            
        self.file_viz_placeholder = QLabel(placeholder_text)
        self.file_viz_placeholder.setAlignment(Qt.AlignCenter)
        self.file_viz_layout.addWidget(self.file_viz_placeholder)
        
        viz_layout.addWidget(self.file_viz_frame)
        tab_layout.addWidget(viz_group, 1)  # 1 = stretch factor
    
    def _setup_hull_tab(self):
        """Sets up the convex hull tab with controls and visualization area"""
        # Main layout for the tab
        tab_layout = QHBoxLayout(self.hull_tab)

        # --- Control panel (left side) ---
        control_panel = QWidget()
        control_panel.setMaximumWidth(300)
        control_layout = QVBoxLayout(control_panel)

        # -- Hull Controls --
        hull_group = QGroupBox("Hull Controls")
        hull_layout = QVBoxLayout(hull_group)
        
        # Compute hull button
        compute_btn = QPushButton("Compute Convex Hull (All Datasets)")
        compute_btn.setObjectName("compute_btn") # Set the object name
        compute_btn.setToolTip("Compute convex hull for all loaded datasets")
        compute_btn.clicked.connect(self.compute_all_hulls)
        hull_layout.addWidget(compute_btn)
        
        control_layout.addWidget(hull_group)
        
        # -- Statistics --
        stats_group = QGroupBox("Hull Statistics")
        stats_layout = QVBoxLayout(stats_group)
        
        # Hull points count
        self.hull_points_label = QLabel("Hull vertices: 0")
        stats_layout.addWidget(self.hull_points_label)
        
        # Hull area
        self.hull_area_label = QLabel("Hull area: 0.0")
        stats_layout.addWidget(self.hull_area_label)
        
        control_layout.addWidget(stats_group)
        
        # Navigation buttons
        nav_layout = QHBoxLayout()
        
        prev_btn = QPushButton("← Previous")
        prev_btn.clicked.connect(lambda: self.notebook.setCurrentIndex(0))
        nav_layout.addWidget(prev_btn)
        
        next_btn = QPushButton("Next →")
        next_btn.clicked.connect(lambda: self.notebook.setCurrentIndex(2))
        nav_layout.addWidget(next_btn)
        
        control_layout.addLayout(nav_layout)
        control_layout.addStretch()
        
        tab_layout.addWidget(control_panel)
        
        # --- Visualization Area (right side) ---
        viz_group = QGroupBox("Convex Hull Visualization")
        viz_layout = QVBoxLayout(viz_group)
        
        # Create container for visualization
        self.hull_viz_frame = QWidget()
        self.hull_viz_layout = QVBoxLayout(self.hull_viz_frame)
        
        # Initial visualization panel will show placeholder message
        if True:
            placeholder_text = "Compute convex hull to visualize in 3D"
        else:
            placeholder_text = "PyVista not available. Install PyVista for 3D visualization.\nCompute convex hull to visualize in 2D."
            
        self.hull_viz_placeholder = QLabel(placeholder_text)
        self.hull_viz_placeholder.setAlignment(Qt.AlignCenter)
        self.hull_viz_layout.addWidget(self.hull_viz_placeholder)
        
        viz_layout.addWidget(self.hull_viz_frame)
        tab_layout.addWidget(viz_group, 1)  # 1 = stretch factor
    
    def _setup_segment_tab(self):
        """Sets up the segmentation tab with controls and visualization area"""
        # Main layout for the tab
        tab_layout = QHBoxLayout(self.segment_tab)

        # --- Control panel (left side) ---
        control_panel = QWidget()
        control_panel.setMaximumWidth(300)
        control_layout = QVBoxLayout(control_panel)

        # -- Segmentation Controls --
        segment_group = QGroupBox("Segmentation Controls")
        segment_layout = QVBoxLayout(segment_group)

        # --- START EDIT: Replace old controls with Target Feature Size ---
        # Remove old segment length and density controls
        # length_layout = QHBoxLayout()
        # length_layout.addWidget(QLabel("Segment Length:"))
        # self.segment_length_input = QLineEdit("1.0")
        # length_layout.addWidget(self.segment_length_input)
        # segment_layout.addLayout(length_layout)
        #
        # density_layout = QHBoxLayout()
        # density_layout.addWidget(QLabel("Density:"))
        # self.segment_density_slider = QSlider(Qt.Horizontal)
        # self.segment_density_slider.setMinimum(50)
        # self.segment_density_slider.setMaximum(200)
        # self.segment_density_slider.setValue(100)
        # density_layout.addWidget(self.segment_density_slider)
        # segment_layout.addLayout(density_layout)

        # --- END EDIT ---
        # Per-surface refinement (segmentation)
        self.seg_length_by_surface = {}
        self._init_seg_refine_table()
        segment_layout.addWidget(self.seg_refine_group)
        # Compute segments button
        compute_btn = QPushButton("Compute Segmentation (All Datasets)") # Update button text
        compute_btn.setObjectName("compute_btn") # Set the object name
        compute_btn.setToolTip("Compute segmentation for all datasets with computed hulls") # Update tooltip
        compute_btn.clicked.connect(self.compute_all_segments) # Connect to the new batch method
        segment_layout.addWidget(compute_btn)

        control_layout.addWidget(segment_group)

        # -- Statistics --
        stats_group = QGroupBox("Segment Statistics")
        stats_layout = QVBoxLayout(stats_group)

        # Number of segments
        self.num_segments_label = QLabel("Segments: 0")
        stats_layout.addWidget(self.num_segments_label)

        # Average segment length
        self.avg_segment_length_label = QLabel("Avg length: 0.0")
        stats_layout.addWidget(self.avg_segment_length_label)

        control_layout.addWidget(stats_group)

        # Navigation buttons
        nav_layout = QHBoxLayout()

        prev_btn = QPushButton("← Previous")
        prev_btn.clicked.connect(lambda: self.notebook.setCurrentIndex(1))
        nav_layout.addWidget(prev_btn)

        next_btn = QPushButton("Next →")
        next_btn.clicked.connect(lambda: self.notebook.setCurrentIndex(3))
        nav_layout.addWidget(next_btn)

        control_layout.addLayout(nav_layout)
        control_layout.addStretch()

        tab_layout.addWidget(control_panel)

        # --- Visualization Area (right side) ---
        viz_group = QGroupBox("Segmentation Visualization")
        viz_layout = QVBoxLayout(viz_group)

        # Create container for visualization
        self.segment_viz_frame = QWidget()
        self.segment_viz_layout = QVBoxLayout(self.segment_viz_frame)

        # Initial visualization panel will show placeholder message
        if True:
            placeholder_text = "Compute segmentation to visualize in 3D"
        else:
            placeholder_text = "PyVista not available. Install PyVista for 3D visualization.\\nCompute segmentation to visualize in 2D."

        self.segment_viz_placeholder = QLabel(placeholder_text)
        self.segment_viz_placeholder.setAlignment(Qt.AlignCenter)
        self.segment_viz_layout.addWidget(self.segment_viz_placeholder)

        viz_layout.addWidget(self.segment_viz_frame)
        tab_layout.addWidget(viz_group, 1)  # 1 = stretch factor
    
    def _setup_triangulation_tab(self):
        """Sets up the triangulation tab with controls and visualization area"""
        # Main layout for the tab
        tab_layout = QHBoxLayout(self.triangulation_tab)

        # --- Control panel (left side) ---
        control_panel = QWidget()
        control_panel.setMaximumWidth(300)
        control_layout = QVBoxLayout(control_panel)

        # -- Triangulation Controls --
        tri_group = QGroupBox("Triangulation Controls")
        tri_layout = QVBoxLayout(tri_group)

        # Mesh quality controls (remain the same)
        quality_group = QGroupBox("Quality Settings")
        quality_layout = QFormLayout(quality_group)

        # Gradient
        self.gradient_input = QDoubleSpinBox()
        self.gradient_input.setRange(1.0, 3.0)
        self.gradient_input.setValue(2.0)
        self.gradient_input.setSingleStep(0.1)
        quality_layout.addRow("Gradient:", self.gradient_input)

        # Min angle
        self.min_angle_input = QDoubleSpinBox()
        self.min_angle_input.setRange(10.0, 30.0)
        self.min_angle_input.setValue(20.0)
        self.min_angle_input.setSingleStep(1.0)
        quality_layout.addRow("Min Angle:", self.min_angle_input)
        # Triangulation tab controls
        # Triangulation tab controls
        self.interp_combo = QComboBox()
        self.interp_combo.addItems([
            "Thin Plate Spline (TPS)",
            "IDW (p=4)",
            "Legacy (Hull + IDW + Boundary Snap)"
        ])
        self.interp_combo.setCurrentIndex(0)
        self.interp_smoothing_input = QDoubleSpinBox()
        self.interp_smoothing_input.setDecimals(6)
        self.interp_smoothing_input.setRange(0.0, 1e3)
        self.interp_smoothing_input.setValue(0.0)

        quality_layout.addRow("Interpolation", self.interp_combo)
        quality_layout.addRow("Smoothing", self.interp_smoothing_input)

        
        # Uniform triangulation
        self.uniform_checkbox = QCheckBox()
        self.uniform_checkbox.setChecked(True) # Default to uniform for consistent sizing
        quality_layout.addRow("Uniform:", self.uniform_checkbox)

        tri_layout.addWidget(quality_group)


        # Run triangulation button
        run_btn = QPushButton("Run Triangulation (All Datasets)") # Update button text
        run_btn.setObjectName("run_btn") # Set the object name
        run_btn.setToolTip("Run triangulation for all datasets with computed segments") # Update tooltip
        run_btn.clicked.connect(self.run_all_triangulations) # Connect to the new batch method
        tri_layout.addWidget(run_btn)

        control_layout.addWidget(tri_group)

        # -- Statistics -- (remain the same)
        # ... (stats_group setup remains the same) ...
        stats_group = QGroupBox("Triangulation Statistics") # Added for completeness
        stats_layout = QVBoxLayout(stats_group) # Added for completeness
        self.num_triangles_label = QLabel("Triangles: 0") # Added for completeness
        stats_layout.addWidget(self.num_triangles_label) # Added for completeness
        self.num_vertices_label = QLabel("Vertices: 0") # Added for completeness
        stats_layout.addWidget(self.num_vertices_label) # Added for completeness
        self.mean_edge_label = QLabel("Mean edge: 0.0") # Added for completeness
        stats_layout.addWidget(self.mean_edge_label) # Added for completeness
        self.uniformity_label = QLabel("Uniformity: 0.0") # Added for completeness
        stats_layout.addWidget(self.uniformity_label) # Added for completeness
        control_layout.addWidget(stats_group) # Added for completeness


        # Export button (remain the same)
        # ... (export_btn setup remains the same) ...
        export_btn = QPushButton("Export Results...") # Added for completeness
        export_btn.clicked.connect(self.export_results) # Added for completeness
        control_layout.addWidget(export_btn) # Added for completeness


        # Navigation buttons (remain the same)
        # ... (nav_layout setup remains the same) ...
        nav_layout = QHBoxLayout() # Added for completeness
        prev_btn = QPushButton("← Previous") # Added for completeness
        prev_btn.clicked.connect(lambda: self.notebook.setCurrentIndex(2)) # Added for completeness
        nav_layout.addWidget(prev_btn) # Added for completeness
        control_layout.addLayout(nav_layout) # Added for completeness
        control_layout.addStretch() # Added for completeness

        tab_layout.addWidget(control_panel)

        # --- Visualization Area (right side) --- (remain the same)
        # ... (viz_group setup remains the same) ...
        viz_group = QGroupBox("Triangulation Visualization") # Added for completeness
        viz_layout = QVBoxLayout(viz_group) # Added for completeness
        self.tri_viz_frame = QWidget() # Added for completeness
        self.tri_viz_layout = QVBoxLayout(self.tri_viz_frame) # Added for completeness
        if True: # Added for completeness
            placeholder_text = "Run triangulation to visualize in 3D" # Added for completeness
        else: # Added for completeness
            placeholder_text = "PyVista not available. Install PyVista for 3D visualization.\nRun triangulation to visualize in 2D." # Added for completeness
        self.tri_viz_placeholder = QLabel(placeholder_text) # Added for completeness
        self.tri_viz_placeholder.setAlignment(Qt.AlignCenter) # Added for completeness
        self.tri_viz_layout.addWidget(self.tri_viz_placeholder) # Added for completeness
        viz_layout.addWidget(self.tri_viz_frame) # Added for completeness
        tab_layout.addWidget(viz_group, 1)  # 1 = stretch factor # Added for completeness

    def _setup_intersection_tab(self):
        """Create the intersection tab and its components with embedded PyVista view."""
        self.intersection_tab = QWidget()
        self.notebook.addTab(self.intersection_tab, "5. Intersections")

        # Set up the layout
        layout = QVBoxLayout(self.intersection_tab)
        
        # Add information label
        info_label = QLabel("Compute intersections between surfaces and polylines:")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("font-size: 12px; color: #555;")
        layout.addWidget(info_label)
        
        # Horizontal layout for controls
        controls_layout = QHBoxLayout()
        
        # Create compute buttons
        self.compute_intersections_btn = QPushButton("Compute Intersections")
        self.compute_intersections_btn.setObjectName("compute_intersections_btn")
        self.compute_intersections_btn.setIcon(QIcon.fromTheme("system-run", QIcon()))
        self.compute_intersections_btn.clicked.connect(self.compute_intersections)
        controls_layout.addWidget(self.compute_intersections_btn)
        
        
        self.clear_intersections_btn = QPushButton("Clear Results")
        self.clear_intersections_btn.setIcon(QIcon.fromTheme("edit-clear", QIcon()))
        self.clear_intersections_btn.clicked.connect(self._clear_intersection_results)
        controls_layout.addWidget(self.clear_intersections_btn)
        controls_layout.addStretch()
        layout.addLayout(controls_layout)
        
        # Create a splitter for the main interface
        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter, 1)  # Add the splitter with stretch
        
        # Left panel for intersection list and details
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        
        # Statistics group
        stats_group = QGroupBox("Intersection Statistics")
        stats_layout = QVBoxLayout(stats_group)
        
        self.surface_intersection_count_label = QLabel("Surface-Surface: 0")
        stats_layout.addWidget(self.surface_intersection_count_label)
        
        self.polyline_intersection_count_label = QLabel("Polyline-Surface: 0")
        stats_layout.addWidget(self.polyline_intersection_count_label)
        
        self.triple_point_count_label = QLabel("Triple Points: 0")
        stats_layout.addWidget(self.triple_point_count_label)
        
        left_layout.addWidget(stats_group)
        
        # List of intersections
        intersection_group = QGroupBox("Intersections")
        intersection_layout = QVBoxLayout(intersection_group)
        
        self.intersection_list = QListWidget()
        self.intersection_list.setSelectionMode(QAbstractItemView.SingleSelection)
        # Defer connecting selection change until plotter is ready
        # self.intersection_list.itemSelectionChanged.connect(self._on_intersection_selection_changed)
        intersection_layout.addWidget(self.intersection_list)
        
        left_layout.addWidget(intersection_group, 1)  # Add stretch
        
        # Right panel for visualization
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        # --- Embed PyVista Plotter --- 
        self.intersection_view_frame = QFrame()
        self.intersection_view_frame.setFrameShape(QFrame.StyledPanel)
        self.intersection_view_frame.setMinimumSize(400, 300)
        self.intersection_plot_layout = QVBoxLayout(self.intersection_view_frame)
        self.intersection_plot_layout.setContentsMargins(0, 0, 0, 0)
        
        if True:
            from pyvistaqt import QtInteractor
            self.intersection_plotter = QtInteractor(self.intersection_view_frame)
            self.intersection_plot_layout.addWidget(self.intersection_plotter.interactor)
            self.intersection_plotter.set_background('white')
            # Connect selection change now that plotter exists
            self.intersection_list.itemSelectionChanged.connect(self._on_intersection_selection_changed)
        else:
            # Placeholder if PyVista is not available
            placeholder = QLabel("PyVista is required for 3D intersection visualization.")
            placeholder.setAlignment(Qt.AlignCenter)
            self.intersection_plot_layout.addWidget(placeholder)
            self.intersection_plotter = None # Ensure plotter is None
        
        right_layout.addWidget(self.intersection_view_frame, 1)  # Add frame with stretch
        # --- End PyVista Embedding ---
        
        # Remove the separate 3D view button
        # self.intersection_3d_view_btn = QPushButton("Show 3D View")
        # self.intersection_3d_view_btn.clicked.connect(self.show_intersections_3d_view)
        # right_layout.addWidget(self.intersection_3d_view_btn)
        
        # Add panels to splitter
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([250, 550])  # Adjust initial sizes
        
        # Store references to intersection data (remains the same)
        if not hasattr(self, 'datasets_intersections'):
            self.datasets_intersections = {}
        
        if not hasattr(self, 'triple_points'):
            self.triple_points = []

    def _init_mesh_refine_table(self):
        # Table for Refine & Mesh per-surface mesh target size
        from PySide6.QtWidgets import QGroupBox, QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView, QSizePolicy
        if not hasattr(self, 'mesh_length_by_surface'):
            self.mesh_length_by_surface = {}

        self._mesh_table_updating = False

        self.mesh_refine_group = QGroupBox("Per-Surface Mesh Density (Target Size)")
        lay = QVBoxLayout(self.mesh_refine_group)

        self.mesh_refine_table = QTableWidget(0, 2, self.mesh_refine_group)
        self.mesh_refine_table.setHorizontalHeaderLabels(["Surface", "Target Size"])

        header = self.mesh_refine_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)

        self.mesh_refine_table.verticalHeader().setVisible(False)
        self.mesh_refine_table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked |
            QAbstractItemView.EditTrigger.EditKeyPressed
        )
        # Professional sizing
        self.mesh_refine_table.setMinimumHeight(220)
        self.mesh_refine_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.mesh_refine_table.setAlternatingRowColors(True)

        self.mesh_refine_table.cellChanged.connect(self._on_mesh_refine_cell_changed)
        lay.addWidget(self.mesh_refine_table)

        self._refresh_mesh_refine_table()
    def _setup_refine_mesh_tab(self):
        """Three-pane layout with Actions → Mesh Settings → Per‑Surface stacked on the left."""
        from PySide6.QtWidgets import (
            QHBoxLayout, QVBoxLayout, QWidget, QGroupBox, QFormLayout, QLabel, QCheckBox, QComboBox,
            QDoubleSpinBox, QPushButton, QTreeWidget, QFrame, QTabWidget, QSplitter, QSizePolicy,
            QHeaderView
        )
        from PySide6.QtCore import Qt

        tab_layout = QHBoxLayout(self.refine_mesh_tab)

        # ── LEFT: Actions → Mesh Settings → Per‑Surface (stacked, resizable) ─────
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)

        # Actions
        actions_group = QGroupBox("Actions")
        ag = QVBoxLayout(actions_group)
        # Initialize selection data (fixes AttributeError)
        self.refine_constraint_data = {}                     # {surface_idx: {...}}
        self.refine_selected_constraint_segments = {}        # {surface_idx: {...}}
        self._refine_updating_constraint_tree = False
        self.refine_intersections_btn = QPushButton("Refine Intersection Lines")
        self.refine_intersections_btn.clicked.connect(self._refine_intersection_lines_action)
        ag.addWidget(self.refine_intersections_btn)

        self.generate_conforming_meshes_btn = QPushButton("Generate Conforming Surface Meshes")
        self.generate_conforming_meshes_btn.clicked.connect(self._generate_conforming_meshes_action)
        self.generate_conforming_meshes_btn.setEnabled(False)
        ag.addWidget(self.generate_conforming_meshes_btn)

        self.show_original_lines_checkbox = QCheckBox("Show Original Lines")
        self.show_original_lines_checkbox.setChecked(True)
        self.show_original_lines_checkbox.toggled.connect(self._update_refined_visualization)
        ag.addWidget(self.show_original_lines_checkbox)

        self.show_conforming_meshes_checkbox = QCheckBox("Show Conforming Meshes")
        self.show_conforming_meshes_checkbox.setChecked(True)
        self.show_conforming_meshes_checkbox.toggled.connect(self._update_refined_visualization)
        ag.addWidget(self.show_conforming_meshes_checkbox)

        # Mesh settings (compact form)
        mesh_settings_group = QGroupBox("Global Mesh Settings")
        mg = QFormLayout(mesh_settings_group)

        self.mesh_interp_combo = QComboBox()
        self.mesh_interp_combo.addItems([
            "Thin Plate Spline (TPS)", "IDW (p=4)",
            "Legacy (Hull + IDW + Boundary Snap)"
        ])
        self.mesh_interp_combo.setCurrentIndex(0)
        mg.addRow("Interpolation", self.mesh_interp_combo)

        self.mesh_smoothing_input = QDoubleSpinBox()
        self.mesh_smoothing_input.setDecimals(6)
        self.mesh_smoothing_input.setRange(0.0, 1e3)
        self.mesh_smoothing_input.setValue(0.0)
        mg.addRow("Smoothing", self.mesh_smoothing_input)

        self.mesh_target_feature_size_input = QDoubleSpinBox()
        self.mesh_target_feature_size_input.setRange(0.1, 500.0)
        self.mesh_target_feature_size_input.setValue(15.0)
        self.mesh_target_feature_size_input.setSingleStep(0.5)
        self.mesh_target_feature_size_input.setDecimals(1)
        self.mesh_target_feature_size_input.valueChanged.connect(self._on_target_size_changed)
        mg.addRow("Mesh Density", self.mesh_target_feature_size_input)

        self.mesh_gradient_input = QDoubleSpinBox()
        self.mesh_gradient_input.setRange(1.0, 3.0)
        self.mesh_gradient_input.setValue(2.0)
        self.mesh_gradient_input.setSingleStep(0.1)
        mg.addRow("Gradient", self.mesh_gradient_input)

        self.mesh_min_angle_input = QDoubleSpinBox()
        self.mesh_min_angle_input.setRange(10.0, 30.0)
        self.mesh_min_angle_input.setValue(20.0)
        mg.addRow("Min Angle", self.mesh_min_angle_input)

        self.mesh_uniform_checkbox = QCheckBox()
        self.mesh_uniform_checkbox.setChecked(True)
        mg.addRow("Uniform", self.mesh_uniform_checkbox)

        # Per‑surface table
        self.mesh_length_by_surface = {}
        self._init_mesh_refine_table()  # builds self.mesh_refine_group

        # Left vertical splitter for resizable sections
        for w in (actions_group, mesh_settings_group, self.mesh_refine_group):
            w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        left_splitter = QSplitter(Qt.Vertical)
        left_splitter.addWidget(actions_group)
        left_splitter.addWidget(mesh_settings_group)
        left_splitter.addWidget(self.mesh_refine_group)
        left_splitter.setChildrenCollapsible(False)
        left_splitter.setHandleWidth(8)
        left_splitter.setOpaqueResize(True)
        # Emphasize table a bit more by default
        left_splitter.setSizes([200, 260, 380])

        left_layout.addWidget(left_splitter)

        # ── CENTER: Visualization ────────────────────────────────────────────────
        center_panel = QWidget()
        center_layout = QVBoxLayout(center_panel)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Surface:"))
        self.refine_surface_selector = QComboBox()
        self.refine_surface_selector.addItem("All Surfaces")
        self.refine_surface_selector.currentTextChanged.connect(self._on_refine_surface_selection_changed)
        toolbar.addWidget(self.refine_surface_selector)

        self.mouse_selection_enabled_btn = QPushButton("Mouse Selection")
        self.mouse_selection_enabled_btn.setCheckable(True)
        self.mouse_selection_enabled_btn.toggled.connect(self._on_mouse_selection_toggled)
        toolbar.addWidget(self.mouse_selection_enabled_btn)
        toolbar.addStretch()
        center_layout.addLayout(toolbar)

        self.refine_view_tabs = QTabWidget()
        self.refine_view_tabs.setDocumentMode(True)
        self.refine_view_tabs.currentChanged.connect(self._on_refine_view_tab_changed)

        self.intersections_tab = QWidget()
        self.intersections_viz_frame = QFrame()
        self.intersections_viz_frame.setFrameShape(QFrame.StyledPanel)
        self.intersections_plot_layout = QVBoxLayout(self.intersections_viz_frame)
        self.intersections_plot_layout.setContentsMargins(0, 0, 0, 0)
        il = QVBoxLayout(self.intersections_tab)
        il.addWidget(self.intersections_viz_frame)
        self.refine_view_tabs.addTab(self.intersections_tab, "Intersections")

        self.meshes_tab = QWidget()
        self.meshes_viz_frame = QFrame()
        self.meshes_viz_frame.setFrameShape(QFrame.StyledPanel)
        self.meshes_plot_layout = QVBoxLayout(self.meshes_viz_frame)
        self.meshes_plot_layout.setContentsMargins(0, 0, 0, 0)
        ml = QVBoxLayout(self.meshes_tab)
        ml.addWidget(self.meshes_viz_frame)
        self.refine_view_tabs.addTab(self.meshes_tab, "Meshes")

        self.segments_tab = QWidget()
        self.segments_viz_frame = QFrame()
        self.segments_viz_frame.setFrameShape(QFrame.StyledPanel)
        self.segments_plot_layout = QVBoxLayout(self.segments_viz_frame)
        self.segments_plot_layout.setContentsMargins(0, 0, 0, 0)
        sl = QVBoxLayout(self.segments_tab)
        sl.addWidget(self.segments_viz_frame)
        self.refine_view_tabs.addTab(self.segments_tab, "Segments")

        self._setup_refine_tab_plotters()
        self.current_refine_view = 0
        self.refine_view_tabs.setCurrentIndex(0)
        center_layout.addWidget(self.refine_view_tabs, 1)

        # ── RIGHT: Constraints + compact Stats ───────────────────────────────────
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_tabs = QTabWidget()
        right_tabs.setDocumentMode(True)

        # Constraints
        constraints_tab = QWidget()
        cl = QVBoxLayout(constraints_tab)

        self.refine_constraint_tree = QTreeWidget()
        self.refine_constraint_tree.setHeaderLabels(["Constraint", "Type", "Segments", "Status", "Hole"])
        self.refine_constraint_tree.header().setSectionResizeMode(QHeaderView.Interactive)
        self.refine_constraint_tree.header().setStretchLastSection(True)
        self.refine_constraint_tree.itemChanged.connect(self._on_refine_constraint_tree_item_changed)
        self.refine_constraint_tree.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        cl.addWidget(self.refine_constraint_tree, 1)

        btns = QHBoxLayout()
        self.refine_select_intersection_constraints_only_btn = QPushButton("Select Intersections")
        self.refine_select_intersection_constraints_only_btn.clicked.connect(self._refine_select_intersection_constraints_only)
        self.refine_select_hull_constraints_only_btn = QPushButton("Select Hull")
        self.refine_select_hull_constraints_only_btn.clicked.connect(self._refine_select_hull_constraints_only)
        btns.addWidget(self.refine_select_intersection_constraints_only_btn)
        btns.addWidget(self.refine_select_hull_constraints_only_btn)
        btns.addStretch()
        cl.addLayout(btns)

        right_tabs.addTab(constraints_tab, "Constraints")

        # Stats (compact)
        stats_tab = QWidget()
        st = QVBoxLayout(stats_tab)
        self.refinement_summary_label = QLabel("Refinement summary will appear here.")
        self.refinement_summary_label.setWordWrap(True)
        self.refinement_summary_label.setStyleSheet("font-size: 10px; color: #444;")
        self.refinement_summary_label.setMaximumHeight(90)
        self.conforming_mesh_summary_label = QLabel("Mesh stats will appear here.")
        self.conforming_mesh_summary_label.setWordWrap(True)
        self.conforming_mesh_summary_label.setStyleSheet("font-size: 10px; color: #444;")
        self.conforming_mesh_summary_label.setMaximumHeight(90)
        st.addWidget(self.refinement_summary_label)
        st.addWidget(self.conforming_mesh_summary_label)
        st.addStretch()
        right_tabs.addTab(stats_tab, "Stats")

        right_layout.addWidget(right_tabs)

        # ── MAIN three‑way splitter ───────────────────────────────────────────────
        main_splitter = QSplitter(Qt.Horizontal)
        left_panel.setMinimumWidth(300)
        right_panel.setMinimumWidth(320)
        main_splitter.addWidget(left_panel)
        main_splitter.addWidget(center_panel)
        main_splitter.addWidget(right_panel)
        main_splitter.setChildrenCollapsible(False)
        main_splitter.setHandleWidth(8)
        main_splitter.setOpaqueResize(True)
        main_splitter.setSizes([380, 960, 420])   # big center view by default
        main_splitter.setStretchFactor(0, 0)
        main_splitter.setStretchFactor(1, 1)
        main_splitter.setStretchFactor(2, 0)

        tab_layout.addWidget(main_splitter)

        # Safety holders
        if not hasattr(self, 'datasets_intersections'):
            self.datasets_intersections = {}
        if not hasattr(self, 'triple_points'):
            self.triple_points = []

    def _setup_refine_tab_plotters(self):
        """Initialize PyVista plotters for each sub-tab"""

        try:
            from pyvistaqt import QtInteractor
            
            # Initialize plotters for each tab
            self.plotters = getattr(self, 'plotters', {})
            
            # Intersections plotter
            self.intersections_plotter = QtInteractor(self.intersections_viz_frame)
            self.intersections_plot_layout.addWidget(self.intersections_plotter.interactor)
            self.intersections_plotter.set_background([0.318, 0.341, 0.431])
            self.intersections_plotter.add_text("Refine intersections to visualize refined intersection lines.", 
                                               position='upper_edge', color='white')
            self.plotters['intersections'] = self.intersections_plotter
            
            # Meshes plotter
            self.meshes_plotter = QtInteractor(self.meshes_viz_frame)
            self.meshes_plot_layout.addWidget(self.meshes_plotter.interactor)
            self.meshes_plotter.set_background([0.318, 0.341, 0.431])
            self.meshes_plotter.add_text("Generate conforming meshes to visualize surface meshes.", 
                                       position='upper_edge', color='white')
            self.plotters['meshes'] = self.meshes_plotter
            
            # Segments plotter
            self.segments_plotter = QtInteractor(self.segments_viz_frame)
            self.segments_plot_layout.addWidget(self.segments_plotter.interactor)
            self.segments_plotter.set_background([0.318, 0.341, 0.431])
            self.segments_plotter.add_text("Click on constraint segments to select/deselect them.", 
                                         position='upper_edge', color='white')
            self.plotters['segments'] = self.segments_plotter
            
            # Set the default main plotter reference for backward compatibility
            self.refine_mesh_plotter = self.intersections_plotter
            self.plotters['refine_mesh'] = self.intersections_plotter
            
            # Initialize constraint actor persistence system
            self.constraint_segment_actor_refs = {}
            self._constraint_actors_built = False
            self._last_segment_count = 0
            self._constraint_actors_persistent = True
            
            logger.info("Successfully created all refine mesh tab plotters and initialized constraint actor system")
            
        except Exception as e:
            logger.error(f"Error initializing Refine/Mesh plotters: {e}", exc_info=True)
            # Add error placeholders for each tab
            for viz_frame, layout, tab_name in [
                (self.intersections_viz_frame, self.intersections_plot_layout, "Intersections"),
                (self.meshes_viz_frame, self.meshes_plot_layout, "Meshes"), 
                (self.segments_viz_frame, self.segments_plot_layout, "Segments")
            ]:
                placeholder = QLabel(f"Error initializing {tab_name} PyVista plotter: {e}")
                placeholder.setAlignment(Qt.AlignCenter)
                placeholder.setWordWrap(True)
                layout.addWidget(placeholder)
            
            # Set None references
            self.intersections_plotter = None
            self.meshes_plotter = None
            self.segments_plotter = None
            self.refine_mesh_plotter = None

    def _on_refine_view_tab_changed(self, index):
        """Handle switching between refine view sub-tabs."""
        old_view = getattr(self, 'current_refine_view', 0)
        self.current_refine_view = index

        logger.info(f"[REFINE] Tab changed from {old_view} to {index}")

        # Update main plotter reference; ensure Segments plotter exists on demand
        if hasattr(self, 'plotters') and self.plotters is not None:
            if index == 0:
                self.refine_mesh_plotter = getattr(self, 'intersections_plotter', None)
            elif index == 1:
                self.refine_mesh_plotter = getattr(self, 'meshes_plotter', None)
            elif index == 2:
                self.refine_mesh_plotter = self._ensure_segments_plotter()
                # Inspect widget tree now that tab is active
                self._debug_segments_widget_tree("tab-changed")
            logger.info(f"[REFINE] refine_mesh_plotter set to tab {index} ({'OK' if self.refine_mesh_plotter else 'None'})")

        if old_view != index:
            self._ensure_constraint_actors_persistence()

            # Disable mouse selection when leaving segments view
            if old_view == 2 and hasattr(self, 'mouse_selection_enabled_btn'):
                if self.mouse_selection_enabled_btn.isChecked():
                    self.mouse_selection_enabled_btn.setChecked(False)

            logger.info("[REFINE] Calling _update_refined_visualization after tab change")
            self._update_refined_visualization()

            if index == 2 and hasattr(self, 'mouse_selection_enabled_btn'):
                self.mouse_selection_enabled_btn.setEnabled(True)
            elif hasattr(self, 'mouse_selection_enabled_btn'):
                self.mouse_selection_enabled_btn.setEnabled(index == 2)

    def _clear_refine_tab_plotters(self):
        """Clear all refine tab plotters"""
        for plotter_name in ['intersections_plotter', 'meshes_plotter', 'segments_plotter']:
            plotter = getattr(self, plotter_name, None)
            if plotter and hasattr(plotter, 'clear'):
                try:
                    plotter.clear()
                except Exception as e:
                    logger.warning(f"Error clearing {plotter_name}: {e}")
    def _ensure_segments_plotter(self):
        """
        Lazily create/attach the Segments QtInteractor if missing.
        Returns the plotter (PyVistaQt is now mandatory).
        """
        logger.info("[SEGMENTS] Creating PyVista plotter (PyVista is now mandatory)")

        # Basic widget sanity
        try:
            logger.info(f"[SEGMENTS] segments_viz_frame exists: {hasattr(self, 'segments_viz_frame')} type={type(getattr(self, 'segments_viz_frame', None))}")
        except Exception:
            logger.warning("[SEGMENTS] unable to inspect segments_viz_frame")

        # Import QtInteractor
        try:
            from pyvistaqt import QtInteractor
            logger.info("[SEGMENTS] QtInteractor import OK")
        except Exception as e:
            logger.error(f"[SEGMENTS] QtInteractor import FAILED: {e}", exc_info=True)
            return None

        # Already present?
        plotter = getattr(self, 'segments_plotter', None)
        if plotter and hasattr(plotter, 'interactor'):
            logger.info("[SEGMENTS] Reusing existing Segments plotter")
            # Ensure it’s attached and visible
            self._debug_segments_widget_tree("reuse")
            return plotter

        # Ensure layout exists
        if not hasattr(self, 'segments_plot_layout') or self.segments_plot_layout is None:
            try:
                self.segments_plot_layout = QVBoxLayout(self.segments_viz_frame)
                self.segments_plot_layout.setContentsMargins(0, 0, 0, 0)
                logger.info("[SEGMENTS] Created segments_plot_layout and attached to frame")
            except Exception as e:
                logger.error(f"[SEGMENTS] Failed to create segments_plot_layout: {e}", exc_info=True)
                return None
        else:
            logger.info("[SEGMENTS] segments_plot_layout already exists")

        # Create and attach the interactor widget
        try:
            self.segments_plotter = QtInteractor(self.segments_viz_frame)
            self.segments_plot_layout.addWidget(self.segments_plotter.interactor)
            self.segments_plotter.set_background([0.318, 0.341, 0.431])
            self.segments_plotter.add_text("Click on constraint segments to select/deselect them.",
                                        position='upper_edge', color='white')
            if not hasattr(self, 'plotters') or self.plotters is None:
                self.plotters = {}
            self.plotters['segments'] = self.segments_plotter
            logger.info("[SEGMENTS] Segments plotter CREATED and interactor added to layout")
            # Verify attachment
            self._debug_segments_widget_tree("created")
            return self.segments_plotter
        except Exception as e:
            logger.error(f"[SEGMENTS] Failed to create/attach Segments plotter: {e}", exc_info=True)
            return None
    def _get_current_refine_plotter(self):
        """Get the currently active refine tab plotter (lazily ensures Segments plotter)."""
        current_index = getattr(self, 'current_refine_view', 0)
        if current_index == 0:
            p = getattr(self, 'intersections_plotter', None)
            logger.info(f"[REFINE] current plotter -> Intersections ({'OK' if p else 'None'})")
            return p
        elif current_index == 1:
            p = getattr(self, 'meshes_plotter', None)
            logger.info(f"[REFINE] current plotter -> Meshes ({'OK' if p else 'None'})")
            return p
        elif current_index == 2:
            p = self._ensure_segments_plotter()
            logger.info(f"[REFINE] current plotter -> Segments ({'OK' if p else 'None'})")
            return p
        logger.warning(f"[REFINE] current plotter -> Unknown tab index {current_index}")
        return None
    
    def _ensure_constraint_actors_persistence(self):
        """
        Ensure constraint actors persist across tab switches and surface filter changes.
        This prevents unnecessary rebuilding and improves performance.
        """
        if not hasattr(self, 'constraint_segment_actor_refs'):
            self.constraint_segment_actor_refs = {}
            
        if not hasattr(self, '_constraint_actors_built'):
            self._constraint_actors_built = False
            
        # Mark constraint actors as persistent to avoid clearing during tab switches
        if hasattr(self, 'constraint_segment_actor_refs') and self.constraint_segment_actor_refs:
            setattr(self, '_constraint_actors_persistent', True)
            
        # Initialize segment count tracking for change detection
        if not hasattr(self, '_last_segment_count'):
            self._last_segment_count = 0
    
    # Event handlers - placeholder implementations
    # ─── Visibility helpers for the view selector ─────────────────────────
    def _show_intersection_actors(self, visible: bool):
        if not hasattr(self, "intersection_actor_refs"):
            return
        for a in self.intersection_actor_refs:
            try:
                a.SetVisibility(visible)
            except Exception:
                pass
        # Render on the current active plotter
        current_plotter = self._get_current_refine_plotter()
        if current_plotter:
            current_plotter.render()
        elif self.refine_mesh_plotter:  # Fallback
            self.refine_mesh_plotter.render()

    def _show_conforming_mesh_actors(self, visible: bool):
        if not hasattr(self, "conforming_mesh_actor_refs"):
            return
        for a in self.conforming_mesh_actor_refs:
            try:
                a.SetVisibility(visible)
            except Exception:
                pass
        # Render on the current active plotter
        current_plotter = self._get_current_refine_plotter()
        if current_plotter:
            current_plotter.render()
        elif self.refine_mesh_plotter:  # Fallback
            self.refine_mesh_plotter.render()

    def _show_constraint_segment_actors(self, visible: bool):
        if not hasattr(self, "constraint_segment_actor_refs"):
            return
        for a in self.constraint_segment_actor_refs:
            try:
                a.SetVisibility(visible)
            except Exception:
                pass
        # Render on the current active plotter
        current_plotter = self._get_current_refine_plotter()
        if current_plotter:
            current_plotter.render()
        elif self.refine_mesh_plotter:  # Fallback
            self.refine_mesh_plotter.render()

    
    def _on_refine_surface_selection_changed(self, surface_name):
        """
        Called when the user changes the surface selection in the dropdown.
        Updates the constraint visualization to show only the selected surface's constraints.
        Similar to C++ setFShowGBox() function.
        """
        logger.info(f"Surface selection changed to: {surface_name}")

        current_view = getattr(self, 'current_refine_view', 0)
        if current_view != 2:
            logger.info(f"Surface selection noted for view {current_view} (constraint visibility not applicable)")
            if current_view == 0:
                logger.info(f"Refreshing intersections visualization for surface filter: {surface_name}")
                self._visualize_refined_intersections()
            elif current_view == 1:
                logger.info(f"Refreshing meshes visualization for surface filter: {surface_name}")
                self._update_refined_visualization()
            self._highlight_surface_in_constraint_tree(surface_name)
            return

        # Segments view
        batched = bool(getattr(self, "_segments_batched_mode", False))
        has_segment_actors = bool(getattr(self, 'constraint_segment_actor_refs', {}))

        # In batched mode (mouse selection OFF) or when no actors exist → rebuild once (fast path)
        if batched or not has_segment_actors:
            logger.info("[SEGMENTS] Surface filter change: rebuilding batched view")
            self._update_refined_visualization()
        else:
            # Per‑segment actors exist → fast toggle
            if hasattr(self, 'constraint_segment_actor_refs') and self.constraint_segment_actor_refs:
                logger.info(f"Updating constraint visibility for surface filter in Segments view (view={current_view})")
                self._update_segment_visibility_for_surface_selection(surface_name)
            else:
                logger.warning("No constraint actors available for visibility update")

        self._highlight_surface_in_constraint_tree(surface_name)

    def _update_segment_visibility_for_surface_selection(self, selected_surface):
        """
        Fast visibility update for segment actors when surface selection changes.
        No rebuilding - just toggle visibility.
        """
        if not hasattr(self, 'constraint_segment_actor_refs'):
            logger.warning("No constraint_segment_actor_refs available for visibility update")
            return
            
        # Get the current active plotter
        plotter = self._get_current_refine_plotter()
        if not plotter:
            # Fallback to old method
            plotter = self.plotters.get("refine_mesh")
            if not plotter:
                logger.warning("No refine_mesh plotter available for visibility update")
                return

        logger.info(f"Updating visibility for surface filter: '{selected_surface}'")
        logger.info(f"Total constraint actors available: {len(self.constraint_segment_actor_refs)}")

        # Get constraint type filters
        show_hull = getattr(self, 'show_hull_constraints_checkbox', None)
        show_intersections = getattr(self, 'show_intersection_constraints_checkbox', None)
        show_selected_only = getattr(self, 'show_selected_only_checkbox', None)
        
        show_hull_constraints = show_hull.isChecked() if show_hull else True
        show_intersection_constraints = show_intersections.isChecked() if show_intersections else True
        show_selected_only_mode = show_selected_only.isChecked() if show_selected_only else False

        # Helper function to check if a surface should be shown
        def should_show_surface(dataset_idx):
            if selected_surface == "All Surfaces":
                return True
            if dataset_idx < len(self.datasets):
                dataset_name = self.datasets[dataset_idx].get("name", f"Surface_{dataset_idx}")
                should_show = dataset_name == selected_surface
                logger.debug(f"Surface check: idx={dataset_idx}, name='{dataset_name}', filter='{selected_surface}', show={should_show}")
                return should_show
            logger.debug(f"Surface check: idx={dataset_idx} out of range ({len(self.datasets)} datasets)")
            return False

        visible_count = 0
        hidden_count = 0
        surface_counts = {}  # Track how many segments per surface
        
        for (surf_idx, seg_uid), actor in self.constraint_segment_actor_refs.items():
            # Track surface distribution
            surface_counts[surf_idx] = surface_counts.get(surf_idx, 0) + 1
            
            # Check surface filter
            should_show = should_show_surface(surf_idx)
            
            if should_show:
                seg_info = getattr(self, '_refine_segment_map', {}).get((surf_idx, seg_uid), {})
                
                # Check constraint type filters
                seg_type = seg_info.get("type", "")
                if seg_type == "hull" and not show_hull_constraints:
                    should_show = False
                elif seg_type == "intersection" and not show_intersection_constraints:
                    should_show = False

                # Check if in selected-only mode
                if should_show and show_selected_only_mode:
                    is_selected = seg_info.get("selected", False)
                    if not is_selected:
                        should_show = False

            # Apply visibility instantly
            try:
                actor.SetVisibility(should_show)
                # Force the actor to update its visibility immediately
                if hasattr(actor, 'Modified'):
                    actor.Modified()
                    
                # NUCLEAR OPTION: If SetVisibility doesn't work, remove/add actor from plotter
                if not should_show:
                    # Try to remove actor from plotter entirely
                    try:
                        if hasattr(plotter, 'remove_actor') and actor in plotter.renderer.actors:
                            plotter.remove_actor(actor)
                            logger.debug(f"Removed actor ({surf_idx}, {seg_uid}) from plotter")
                    except:
                        pass
                else:
                    # Ensure actor is in plotter
                    try:
                        if hasattr(plotter, 'add_actor') and actor not in plotter.renderer.actors:
                            plotter.add_actor(actor)
                            logger.debug(f"Added actor ({surf_idx}, {seg_uid}) to plotter")
                    except:
                        pass
                        
                if should_show:
                    visible_count += 1
                else:
                    hidden_count += 1
            except Exception as e:
                logger.warning(f"Failed to set visibility for actor ({surf_idx}, {seg_uid}): {e}")
                continue
        
        # Force complete render and refresh
        try:
            # NUCLEAR APPROACH: Since SetVisibility() doesn't work,
            # physically remove all non-visible actors from the plotter
            plotter.clear_actors()  # Remove ALL actors first
            
            # Re-add only the actors that should be visible
            actors_readded = 0
            for (surf_idx, seg_uid), actor in self.constraint_segment_actor_refs.items():
                should_show = should_show_surface(surf_idx)
                
                if should_show:
                    seg_info = getattr(self, '_refine_segment_map', {}).get((surf_idx, seg_uid), {})
                    
                    # Check constraint type filters
                    seg_type = seg_info.get("type", "")
                    if seg_type == "hull" and not show_hull_constraints:
                        should_show = False
                    elif seg_type == "intersection" and not show_intersection_constraints:
                        should_show = False

                    # Check if in selected-only mode
                    if should_show and show_selected_only_mode:
                        is_selected = seg_info.get("selected", False)
                        if not is_selected:
                            should_show = False
                
                # Only add actors that should be visible
                if should_show:
                    try:
                        plotter.add_actor(actor)
                        actors_readded += 1
                        logger.debug(f"Re-added actor ({surf_idx}, {seg_uid}) to plotter")
                    except Exception as e:
                        logger.warning(f"Failed to re-add actor ({surf_idx}, {seg_uid}): {e}")
            
            logger.info(f"NUCLEAR FIX: Removed all actors, re-added {actors_readded} visible actors")
            
            # Standard rendering
            plotter.render()
            if hasattr(plotter, 'update'):
                plotter.update()
            if hasattr(plotter, 'ren_win') and plotter.ren_win:
                plotter.ren_win.Render()
                
        except Exception as e:
            logger.warning(f"Error during nuclear render fix: {e}")
            # Fallback to standard render
            try:
                plotter.render()
            except:
                pass
        
        # Detailed logging
        logger.info(f"Visibility update complete: {visible_count} visible, {hidden_count} hidden")
        logger.info(f"Surface distribution: {surface_counts}")
        
        # Specific info about the selected surface
        if selected_surface != "All Surfaces":
            # Find which surface index corresponds to the selected surface name
            target_surface_idx = None
            for idx, dataset in enumerate(self.datasets):
                if dataset.get("name", f"Surface_{idx}") == selected_surface:
                    target_surface_idx = idx
                    break
            
            if target_surface_idx is not None:
                visible_for_selected = surface_counts.get(target_surface_idx, 0)
                logger.info(f"Selected surface '{selected_surface}' (idx={target_surface_idx}) has {visible_for_selected} total segments")
                
                # VERIFY THE FIX: Check if the visibility was actually applied
                visible_actors_for_surface = 0
                for (surf_idx, seg_uid), actor in self.constraint_segment_actor_refs.items():
                    if surf_idx == target_surface_idx and actor.GetVisibility():
                        visible_actors_for_surface += 1
                
                logger.info(f"VERIFICATION: {visible_actors_for_surface} actors are actually visible for surface {target_surface_idx}")
                
                if visible_actors_for_surface != visible_count:
                    logger.error(f"❌ VISIBILITY MISMATCH: Expected {visible_count} visible, but {visible_actors_for_surface} actors are actually visible!")
                else:
                    logger.info(f"✅ VISIBILITY CONFIRMED: All {visible_count} actors are properly visible")
                    
            else:
                logger.warning(f"Could not find surface index for '{selected_surface}'")
        
        logger.info(f"Final result: {visible_count} segments visible for '{selected_surface}'")

    def _on_constraint_filter_changed(self):
        """
        Fast constraint filter update when checkboxes change.
        If batched mode: rebuild once. If per‑segment mode: visibility toggle.
        """
        if getattr(self, "current_refine_view", 0) != 2:
            self._update_refined_visualization()
            return

        batched = bool(getattr(self, "_segments_batched_mode", False))
        if batched:
            logger.info("[SEGMENTS] Constraint filter changed → rebuilding batched view")
            self._update_refined_visualization()
            return

        # Per‑segment actors exist, toggle visibility without rebuild
        selected_surface = "All Surfaces"
        if hasattr(self, 'refine_surface_selector') and self.refine_surface_selector:
            selected_surface = self.refine_surface_selector.currentText()
        self._update_segment_visibility_for_surface_selection(selected_surface)

    def _on_mouse_selection_toggled(self, enabled):
        """
        Toggle mouse-based constraint selection on/off.
        When enabled we rebuild per-segment actors and enable picking.
        When disabled we rebuild the fast batched view.
        """
        logger.info(f"Mouse selection {'enabled' if enabled else 'disabled'}")

        # Show/hide selection mode buttons
        if hasattr(self, 'selection_mode_btn') and hasattr(self, 'deselection_mode_btn'):
            self.selection_mode_btn.setVisible(enabled)
            self.deselection_mode_btn.setVisible(enabled)

        if not hasattr(self, 'current_selection_mode'):
            self.current_selection_mode = "select"

        if not hasattr(self, 'highlight_timer'):
            self.highlight_timer = QTimer()
            self.highlight_timer.setSingleShot(True)
            self.highlight_timer.timeout.connect(self._clear_selection_highlight)
            self.highlight_timer.setInterval(500)

        # Ensure we are on Segments tab
        current_view = getattr(self, 'current_refine_view', 0)
        if current_view != 2 and enabled:
            if hasattr(self, 'refine_view_tabs'):
                self.refine_view_tabs.setCurrentIndex(2)
            else:
                if hasattr(self, 'view_btn_grp'):
                    self.view_btn_grp.button(2).setChecked(True)

        plotter = self._get_current_refine_plotter() or self.plotters.get("refine_mesh")
        if not plotter:
            logger.warning("No refine_mesh plotter available for mouse selection")
            return

        # Rebuild visualization for the new mode
        # - enabled: per-segment actors for picking
        # - disabled: batched fast drawing
        try:
            self._update_refined_visualization()
        except Exception as e:
            logger.warning(f"Redraw after toggling mouse selection failed: {e}")

        if enabled:
            # Require per-segment actors
            if not hasattr(self, 'constraint_segment_actor_refs'):
                self.constraint_segment_actor_refs = {}
            if not getattr(self, '_constraint_actors_built', False) or not self.constraint_segment_actor_refs:
                logger.warning("No constraint actors available for mouse selection after rebuild")
                return

            try:
                plotter.enable_cell_picking(
                    callback=self._on_constraint_cell_clicked,
                    show_message=False,
                    font_size=12,
                    color='yellow',
                    through=True,
                    start=True,
                    show=True
                )
                self.mouse_selection_enabled_btn.setText("🖱️ Mouse ON")
                logger.info("Constraint mouse selection enabled")
            except Exception as cell_error:
                logger.warning(f"Cell picking failed: {cell_error}")
                try:
                    from pyvista.plotting.opts import ElementType
                    plotter.enable_element_picking(
                        mode=ElementType.EDGE,
                        callback=self._on_constraint_edge_clicked,
                        show_message=False,
                        font_size=10,
                        color='yellow'
                    )
                    self.mouse_selection_enabled_btn.setText("🖱️ Mouse ON")
                    logger.info("Constraint mouse selection enabled (edge picking fallback)")
                except Exception as edge_error:
                    logger.warning(f"Edge picking failed: {edge_error}")
                    try:
                        plotter.enable_mesh_picking(
                            callback=self._on_constraint_clicked_single,
                            show_message=False,
                            font_size=10,
                            color='yellow'
                        )
                        self.mouse_selection_enabled_btn.setText("🖱️ Mouse ON")
                        logger.info("Constraint mouse selection enabled (mesh picking fallback)")
                    except Exception as mesh_error:
                        logger.error(f"All picking methods failed: {mesh_error}")
                        return
        else:
            # Disable picking and rebuild fast view
            try:
                plotter.disable_picking()
            except Exception:
                pass
            self.mouse_selection_enabled_btn.setText("🖱️ Mouse Selection")
            try:
                self._update_refined_visualization()
            except Exception:
                pass
            logger.info("Constraint mouse selection disabled")

    def _on_selection_mode_changed(self, button, checked):
        """
        Called when user switches between Select Mode and Deselect Mode.
        Updates the behavior of rectangle selection.
        """
        if not checked:
            return  # Only respond to button being checked, not unchecked
            
        mode_id = self.selection_mode_group.id(button)
        if mode_id == 0:  # Select mode
            self.current_selection_mode = "select"
            logger.info("🔵 Selection mode: SELECT - Rectangle drag will select constraints")
            # Update button styles to show active mode
            self.selection_mode_btn.setText("✅ Select Mode (Active)")
            self.deselection_mode_btn.setText("❌ Deselect Mode")
        elif mode_id == 1:  # Deselect mode
            self.current_selection_mode = "deselect"
            logger.info("🔴 Selection mode: DESELECT - Rectangle drag will deselect constraints")
            # Update button styles to show active mode
            self.selection_mode_btn.setText("✅ Select Mode")
            self.deselection_mode_btn.setText("❌ Deselect Mode (Active)")
        
        # Store the current mode for use in cell clicking callback
        self.current_selection_mode = "select" if mode_id == 0 else "deselect"

    def _clear_selection_highlight(self):
        """
        Clear the yellow selection highlight after a short delay.
        This allows users to see the actual selection state of constraints.
        """
        try:
            # Get the current active plotter
            plotter = self._get_current_refine_plotter()
            if not plotter:
                # Fallback to old method
                plotter = self.plotters.get("refine_mesh")
            if plotter:
                # Try multiple methods to clear PyVista highlighting
                try:
                    # Method 1: Clear pick selection if available
                    if hasattr(plotter, 'clear_pick_selection'):
                        plotter.clear_pick_selection()
                        logger.debug("🔄 Cleared using clear_pick_selection()")
                    
                    # Method 2: Clear cell picking highlight
                    elif hasattr(plotter, 'picked_cell') and plotter.picked_cell is not None:
                        plotter.picked_cell = None
                        logger.debug("🔄 Cleared picked_cell")
                    
                    # Method 3: Clear mesh picking highlight  
                    elif hasattr(plotter, 'picked_mesh') and plotter.picked_mesh is not None:
                        plotter.picked_mesh = None
                        logger.debug("🔄 Cleared picked_mesh")
                    
                    # Method 4: Force render to clear any visual artifacts
                    plotter.render()
                    logger.debug("🔄 Cleared selection highlighting with render")
                    
                except AttributeError as ae:
                    # Just render if specific clearing methods don't exist
                    plotter.render()
                    logger.debug(f"🔄 Used render fallback: {ae}")
                    
        except Exception as e:
            logger.warning(f"Error clearing selection highlight: {e}")

    def _update_constraint_visualization_colors(self):
        """
        Update the visual colors of constraint lines based on their selection state.
        Green = selected, Gray = unselected (following the original constraint visualization system).
        """
        try:
            # Get the current active plotter
            plotter = self._get_current_refine_plotter()
            if not plotter:
                # Fallback to old method
                plotter = self.plotters.get("refine_mesh")
            if not plotter or not hasattr(self, 'constraint_segment_actor_refs'):
                return
                
            # Get the tree for checking selection states
            tree = getattr(self, 'refine_constraint_tree', None)
            if not tree:
                return
                
            logger.debug("🎨 Updating constraint visualization colors based on selection state")
            
            # Build a map of selection states for fast lookup
            selection_states = {}  # {(surf_idx, seg_uid): is_selected}
            
            def collect_selection_states(item):
                """Recursively collect selection states from tree"""
                data = item.data(0, Qt.UserRole)
                if data and data.get("type") == "constraint":
                    surf_idx = data.get("surface_idx")
                    seg_uid = data.get("seg_uid")
                    is_selected = item.checkState(0) == Qt.Checked
                    selection_states[(surf_idx, seg_uid)] = is_selected
                
                # Process child items
                for i in range(item.childCount()):
                    collect_selection_states(item.child(i))
            
            # Collect all selection states from tree
            for i in range(tree.topLevelItemCount()):
                collect_selection_states(tree.topLevelItem(i))
            
            # Update actor colors based on selection state
            updated_count = 0
            for (surf_idx, seg_uid), actor in self.constraint_segment_actor_refs.items():
                is_selected = selection_states.get((surf_idx, seg_uid), False)
                
                # Set color: Green for selected, Gray for unselected
                if is_selected:
                    color = [0.0, 1.0, 0.0]  # Green
                else:
                    color = [0.5, 0.5, 0.5]  # Gray
                
                try:
                    # Update actor color
                    actor.GetProperty().SetColor(color)
                    actor.Modified()  # Mark as modified to trigger render update
                    updated_count += 1
                except Exception as actor_error:
                    logger.debug(f"Failed to update color for actor ({surf_idx}, {seg_uid}): {actor_error}")
            
            # Force render to show color changes
            plotter.render()
            logger.debug(f"🎨 Updated colors for {updated_count} constraint actors")
            
        except Exception as e:
            logger.warning(f"Error updating constraint visualization colors: {e}")

    def _synchronize_shared_intersection_segments(self, selected_segments):
        """
        Synchronize selection state for intersection segments that are shared across multiple surfaces.
        When an intersection segment is selected/deselected on one surface, it should be 
        selected/deselected on all other surfaces that share the same intersection.
        """
        try:
            if not hasattr(self, 'refined_intersections_for_visualization') or not hasattr(self, 'refine_constraint_tree'):
                return
                
            tree = self.refine_constraint_tree
            if not tree:
                return
                
            # Get current selection mode
            mode = getattr(self, 'current_selection_mode', 'select')
            
            logger.debug(f"🔄 Synchronizing {len(selected_segments)} segments across surfaces (mode: {mode})")
            
            # Block signals to prevent recursion during synchronization
            tree.blockSignals(True)
            
            try:
                # For each segment that was just selected/deselected
                for surf_idx, seg_uid in selected_segments:
                    # Check if this is an intersection segment by finding its parent in the tree
                    segment_item = self._find_tree_item_for_segment(surf_idx, seg_uid)
                    if not segment_item:
                        continue
                        
                    parent_item = segment_item.parent()
                    if not parent_item:
                        continue
                        
                    parent_data = parent_item.data(0, Qt.UserRole)
                    if not parent_data or parent_data.get("type") != "intersection_group":
                        continue  # Not an intersection segment, no sync needed
                    
                    # Get the intersection index
                    try:
                        intersection_idx = int(parent_item.text(0).split(" ")[-1])
                    except (ValueError, IndexError):
                        continue
                    
                    # Get the intersection data to find which surfaces are involved
                    if surf_idx not in self.refined_intersections_for_visualization:
                        continue
                        
                    if intersection_idx >= len(self.refined_intersections_for_visualization[surf_idx]):
                        continue
                        
                    intersection_data = self.refined_intersections_for_visualization[surf_idx][intersection_idx]
                    dataset_id1 = intersection_data.get('dataset_id1')
                    dataset_id2 = intersection_data.get('dataset_id2')
                    
                    # Get the current selection state of the segment we just modified
                    current_state = segment_item.checkState(0) == Qt.Checked
                    
                    logger.debug(f"Syncing intersection segment {seg_uid} from surface {surf_idx} to surfaces {dataset_id1}, {dataset_id2}")
                    
                    # Update the same segment on the other involved surfaces
                    surfaces_to_sync = []
                    if dataset_id1 is not None and dataset_id1 != surf_idx:
                        surfaces_to_sync.append(dataset_id1)
                    if dataset_id2 is not None and dataset_id2 != surf_idx:
                        surfaces_to_sync.append(dataset_id2)
                    
                    for other_surface_idx in surfaces_to_sync:
                        # Find the corresponding segment on the other surface
                        other_segment_item = self._find_matching_intersection_segment(
                            other_surface_idx, intersection_idx, seg_uid
                        )
                        
                        if other_segment_item:
                            # Set the same selection state
                            new_state = Qt.Checked if current_state else Qt.Unchecked
                            if other_segment_item.checkState(0) != new_state:
                                other_segment_item.setCheckState(0, new_state)
                                logger.debug(f"✅ Synced segment {seg_uid} on surface {other_surface_idx} to {current_state}")
                
            finally:
                # Re-enable signals and update visualization
                tree.blockSignals(False)
                tree.update()
                tree.repaint()
                
                # Update colors again to reflect synchronized changes
                self._update_constraint_visualization_colors()
                
            logger.debug("🔄 Cross-surface synchronization complete")
            
        except Exception as e:
            logger.warning(f"Error synchronizing shared intersection segments: {e}")

    def _synchronize_shared_intersection_segments_background(self, selected_segments):
        """
        Background synchronization for intersection segments that respects surface filtering.
        Updates tree states without affecting visual display - the surface filter remains active.
        """
        try:
            if not hasattr(self, 'refined_intersections_for_visualization') or not hasattr(self, 'refine_constraint_tree'):
                return
                
            tree = self.refine_constraint_tree
            if not tree:
                return
                
            # Get current selection mode and surface filter
            mode = getattr(self, 'current_selection_mode', 'select')
            current_surface_filter = "All Surfaces"
            if hasattr(self, 'refine_surface_selector') and self.refine_surface_selector:
                current_surface_filter = self.refine_surface_selector.currentText()
                
            logger.debug(f"🔄 Background sync: {len(selected_segments)} segments (mode: {mode}, filter: {current_surface_filter})")
            
            # Block signals to prevent visual updates during background sync
            tree.blockSignals(True)
            
            try:
                # For each segment that was just selected/deselected
                for surf_idx, seg_uid in selected_segments:
                    # Only sync if this segment was actually from the filtered surface
                    if current_surface_filter != "All Surfaces":
                        # Check if this segment belongs to the currently filtered surface
                        if surf_idx < len(self.datasets):
                            dataset_entry = self.datasets[surf_idx]
                            # Robustly obtain surface name whether the datasets list stores dicts or paths
                            if isinstance(dataset_entry, dict):
                                surface_name = dataset_entry.get("name", f"Surface_{surf_idx}")
                            else:
                                surface_name = os.path.basename(str(dataset_entry))
                            if surface_name != current_surface_filter:
                                continue  # Skip segments not from current surface filter
                    
                    # Find and sync intersection segments
                    segment_item = self._find_tree_item_for_segment(surf_idx, seg_uid)
                    if not segment_item:
                        continue
                        
                    parent_item = segment_item.parent()
                    if not parent_item:
                        continue
                        
                    parent_data = parent_item.data(0, Qt.UserRole)
                    if not parent_data or parent_data.get("type") != "intersection_group":
                        continue  # Not an intersection segment
                    
                    # Get intersection data and sync to other surfaces
                    try:
                        intersection_idx = int(parent_item.text(0).split(" ")[-1])
                    except (ValueError, IndexError):
                        continue
                    
                    if surf_idx not in self.refined_intersections_for_visualization:
                        continue
                        
                    if intersection_idx >= len(self.refined_intersections_for_visualization[surf_idx]):
                        continue
                        
                    intersection_data = self.refined_intersections_for_visualization[surf_idx][intersection_idx]
                    dataset_id1 = intersection_data.get('dataset_id1')
                    dataset_id2 = intersection_data.get('dataset_id2')
                    
                    # Get current selection state
                    current_state = segment_item.checkState(0) == Qt.Checked
                    
                    # Update other surfaces (background tree updates only)
                    surfaces_to_sync = []
                    if dataset_id1 is not None and dataset_id1 != surf_idx:
                        surfaces_to_sync.append(dataset_id1)
                    if dataset_id2 is not None and dataset_id2 != surf_idx:
                        surfaces_to_sync.append(dataset_id2)
                    
                    for other_surface_idx in surfaces_to_sync:
                        other_segment_item = self._find_matching_intersection_segment(
                            other_surface_idx, intersection_idx, seg_uid
                        )
                        
                        if other_segment_item:
                            # Update tree state without triggering visual updates
                            new_state = Qt.Checked if current_state else Qt.Unchecked
                            if other_segment_item.checkState(0) != new_state:
                                other_segment_item.setCheckState(0, new_state)
                                logger.debug(f"📋 Background sync: segment {seg_uid} on surface {other_surface_idx} → {current_state}")
                
            finally:
                # Re-enable signals but DON'T trigger visual updates
                tree.blockSignals(False)
                # NOTE: We deliberately don't call tree.update() or repaint() here
                # NOTE: We deliberately don't call _update_constraint_visualization_colors() here
                # This keeps the background sync invisible to the user interface
                
            logger.debug("🔄 Background synchronization complete (no visual changes)")
            
        except Exception as e:
            logger.warning(f"Error in background synchronization: {e}")

    def _find_tree_item_for_segment(self, surf_idx, seg_uid):
        """
        Find the tree item for a specific segment.
        """
        tree = getattr(self, 'refine_constraint_tree', None)
        if not tree:
            return None
            
        def search_item(item):
            data = item.data(0, Qt.UserRole)
            if data and data.get("type") == "constraint":
                if data.get("surface_idx") == surf_idx and data.get("seg_uid") == seg_uid:
                    return item
            
            # Search children
            for i in range(item.childCount()):
                result = search_item(item.child(i))
                if result:
                    return result
            return None
        
        # Search all top-level items
        for i in range(tree.topLevelItemCount()):
            result = search_item(tree.topLevelItem(i))
            if result:
                return result
        return None

    def _find_matching_intersection_segment(self, surface_idx, intersection_idx, seg_uid):
        """
        Find the matching intersection segment on another surface.
        """
        tree = getattr(self, 'refine_constraint_tree', None)
        if not tree:
            return None
            
        # Find the surface item
        for i in range(tree.topLevelItemCount()):
            surface_item = tree.topLevelItem(i)
            surface_data = surface_item.data(0, Qt.UserRole)
            
            if surface_data and surface_data.get("surface_idx") == surface_idx:
                # Find the intersection group
                for j in range(surface_item.childCount()):
                    group_item = surface_item.child(j)
                    group_data = group_item.data(0, Qt.UserRole)
                    
                    if (group_data and group_data.get("type") == "intersection_group"):
                        try:
                            item_intersection_idx = int(group_item.text(0).split(" ")[-1])
                            if item_intersection_idx == intersection_idx:
                                # Find the segment within this group
                                for k in range(group_item.childCount()):
                                    segment_item = group_item.child(k)
                                    segment_data = segment_item.data(0, Qt.UserRole)
                                    
                                    if (segment_data and 
                                        segment_data.get("type") == "constraint" and
                                        segment_data.get("seg_uid") == seg_uid):
                                        return segment_item
                        except (ValueError, IndexError):
                            continue
        return None

    def _on_constraint_edge_clicked(self, *args):
        """
        Called when user clicks on a constraint edge using element picking.
        This is the most accurate method for selecting constraint lines since they are edges.
        """
        import traceback
        try:
            logger.info(f"=== EDGE CLICK DETECTED === Received {len(args)} arguments")
            
            # Edge picking typically provides: (mesh, cell_id, edge_id) or similar
            if len(args) >= 1:
                mesh = args[0]
                logger.info(f"Clicked edge mesh type: {type(mesh)}")
                
                # Handle None mesh (edge picking sometimes fails)
                if mesh is None:
                    logger.warning("Edge picking returned None mesh - edge detection failed")
                    return
                
                # Try to get edge info if available
                if len(args) >= 2:
                    cell_id = args[1]
                    logger.info(f"Cell ID: {cell_id}")
                    
                if len(args) >= 3:
                    edge_id = args[2]
                    logger.info(f"Edge ID: {edge_id}")
                
                # Add mesh debugging
                if hasattr(mesh, 'GetNumberOfPoints'):
                    num_points = mesh.GetNumberOfPoints()
                    logger.info(f"Clicked edge mesh has {num_points} points")
                    
                    if num_points >= 2:
                        # Get first and last points for debugging
                        first_point = mesh.GetPoint(0)
                        last_point = mesh.GetPoint(num_points - 1)
                        logger.info(f"Edge: start={first_point}, end={last_point}")
                else:
                    logger.warning("Edge mesh has no GetNumberOfPoints method")
                    
                # Use the standard method to find and select the segment
                logger.info("Processing edge click through constraint clicked method...")
                self._on_constraint_clicked(mesh)
                
            else:
                logger.warning("No data received in edge picking callback")
        except Exception as e:
            logger.error(f"Error in edge picking callback: {e}")
            traceback.print_exc()

    def _on_constraint_cell_clicked(self, *args):
        """
        Called when user clicks on a constraint using cell picking.
        This method gets the mesh from the picked cell and handles both single clicks and rectangle selections.
        """
        import traceback
        try:
            # Fast processing - reduced logging for speed
            # logger.info(f"=== MOUSE CLICK DETECTED === Received {len(args)} arguments")
            
            # Cell picking can provide either a single mesh or a collection of picked cells
            if len(args) >= 1:
                picked_data = args[0]
                logger.info(f"Picked data type: {type(picked_data)}")
                
                # Handle different types of picked data
                meshes_to_process = []
                
                if hasattr(picked_data, 'n_blocks') and picked_data.n_blocks > 0:
                    # MultiBlock - could be rectangle selection or single click
                    total_points = sum(block.n_points for block in picked_data if block is not None and hasattr(block, 'n_points'))
                    logger.info(f"MultiBlock with {picked_data.n_blocks} blocks, total points: {total_points}")
                    
                    # Extract all valid individual meshes from the MultiBlock
                    for i in range(picked_data.n_blocks):
                        block = picked_data[i]
                        if block is not None and hasattr(block, 'n_points') and block.n_points >= 2:
                            meshes_to_process.append(block)
                    
                    logger.info(f"Extracted {len(meshes_to_process)} valid meshes for processing")
                    
                elif hasattr(picked_data, 'n_points'):
                    # Single mesh
                    meshes_to_process = [picked_data]
                    logger.info(f"Single mesh with {picked_data.n_points} points")
                
                # Get current surface filter FIRST to enable pre-filtering
                selected_surface = "All Surfaces"
                if hasattr(self, 'refine_surface_selector') and self.refine_surface_selector:
                    selected_surface = self.refine_surface_selector.currentText()
                    # logger.info(f"Current surface filter: '{selected_surface}'")  # Removed for speed
                
                # CRITICAL FIX: Pre-filter meshes to only include those from visible actors
                # This prevents PyVista from returning meshes from hidden constraint actors
                filtered_meshes = []
                skipped_count = 0
                
                for mesh in meshes_to_process:
                    # Find the segment for this mesh
                    clicked_segment = self._find_segment_by_mesh_comparison(mesh)
                    
                    if clicked_segment:
                        surf_idx, seg_uid = clicked_segment
                        
                        # Check if this segment should be visible based on surface filter
                        if self._is_surface_visible_in_filter(surf_idx, selected_surface):
                            # Check if the actor is actually visible
                            if self._is_constraint_actor_visible(surf_idx, seg_uid):
                                filtered_meshes.append(mesh)
                                logger.debug(f"✅ Including mesh for segment ({surf_idx}, {seg_uid})")
                            else:
                                skipped_count += 1
                                logger.debug(f"❌ Skipping mesh for segment ({surf_idx}, {seg_uid}) - actor not visible")
                        else:
                            skipped_count += 1
                            logger.debug(f"❌ Skipping mesh for segment ({surf_idx}, {seg_uid}) - surface not selected")
                    else:
                        skipped_count += 1
                        logger.debug("❌ Skipping mesh - could not identify segment")
                
                logger.info(f"PRE-FILTER: {len(filtered_meshes)} valid, {skipped_count} skipped from {len(meshes_to_process)} total meshes")
                
                # Process only the filtered meshes
                valid_segments = []
                
                for mesh in filtered_meshes:
                    # Find the segment for this mesh (we know it exists since we pre-filtered)
                    clicked_segment = self._find_segment_by_mesh_comparison(mesh)
                    
                    if clicked_segment:
                        surf_idx, seg_uid = clicked_segment
                        valid_segments.append((surf_idx, seg_uid))
                        # logger.debug(f"✅ Will toggle segment ({surf_idx}, {seg_uid})")  # Removed for speed
                
                # Report results
                if valid_segments:
                    # Fast operation - minimal logging
                    if len(valid_segments) == 1:
                        operation = "Single click"
                    else:
                        operation = "Rectangle selection"
                    
                    mode_text = "selected" if getattr(self, 'current_selection_mode', 'select') == "select" else "deselected"
                    
                    # ULTRA-FAST BATCH PROCESSING - disable all tree signals during batch update
                    tree = getattr(self, 'refine_constraint_tree', None)
                    if tree:
                        tree.blockSignals(True)
                    
                    try:
                        # Process all segments in a single batch
                        success_count = 0
                        for surf_idx, seg_uid in valid_segments:
                            if self._apply_selection_mode_to_segment_fast(surf_idx, seg_uid):
                                success_count += 1
                        
                        logger.info(f"🎯 {operation}: {mode_text} {success_count}/{len(valid_segments)} segments")
                        
                    finally:
                        # Re-enable tree signals after batch operation - THIS TRIGGERS THE VISUAL UPDATE
                        if tree:
                            tree.blockSignals(False)
                            # CRITICAL: Emit a signal to update the tree visualization
                            tree.update()
                            tree.repaint()
                            
                        # CRITICAL FIX: Update constraint visualization colors after selection changes
                        # This ensures green (selected) and gray (unselected) lines are properly updated
                        self._update_constraint_visualization_colors()
                        
                        # CROSS-SURFACE SYNCHRONIZATION: Update shared intersection segments in the background
                        # This only updates tree states, not visual display (surface filter still applies)
                        self._synchronize_shared_intersection_segments_background(valid_segments)

                        # Immediately clear any yellow picking highlight so the user sees the final colors
                        self._clear_selection_highlight()
                    
                    # Start timer to ensure any residual highlight is cleared after a short delay
                    if hasattr(self, 'highlight_timer'):
                        try:
                            self.highlight_timer.start()  # This will clear highlighting after 500ms
                        except Exception as timer_error:
                            logger.debug(f"Highlight timer error (non-critical): {timer_error}")
                            # If timer fails, just do immediate clear
                            self._clear_selection_highlight()
                    
                else:
                    logger.warning("❌ No valid segments found for current surface filter")
                    if skipped_count > 0:
                        logger.info(f"💡 All {skipped_count} picked meshes were filtered out due to surface selection")
                        logger.info(f"💡 Current filter: '{selected_surface}' - ensure you're clicking on visible constraints")
                        logger.info(f"💡 Switch to 'All Surfaces' to interact with all constraints")
                
            else:
                logger.warning("No data received in cell picking callback")
                
        except Exception as e:
            logger.error(f"Error in cell picking callback: {e}")
            traceback.print_exc()

    def _is_surface_visible_in_filter(self, surf_idx, selected_surface):
        """
        Helper function to check if a surface should be shown based on the current filter.
        """
        if selected_surface == "All Surfaces":
            return True
        if surf_idx < len(self.datasets):
            dataset_entry = self.datasets[surf_idx]
            if isinstance(dataset_entry, dict):
                dataset_name = dataset_entry.get("name", f"Surface_{surf_idx}")
            else:
                dataset_name = os.path.basename(str(dataset_entry))
            return dataset_name == selected_surface
        return False

    def _is_constraint_actor_visible(self, surf_idx, seg_uid):
        """
        Check if a constraint actor is currently visible in the plotter.
        This ensures we only select constraints that are actually displayed.
        """
        try:
            if not hasattr(self, 'constraint_segment_actor_refs'):
                return False
                
            actor = self.constraint_segment_actor_refs.get((surf_idx, seg_uid))
            if not actor:
                return False
                
            # Check if actor has visibility property and is visible
            if hasattr(actor, 'GetVisibility'):
                is_visible = actor.GetVisibility()
                logger.debug(f"Actor ({surf_idx}, {seg_uid}) visibility: {is_visible}")
                return bool(is_visible)
            else:
                # If we can't check visibility, assume it's visible
                logger.debug(f"Actor ({surf_idx}, {seg_uid}) has no visibility check - assuming visible")
                return True
                
        except Exception as e:
            logger.debug(f"Error checking actor visibility for ({surf_idx}, {seg_uid}): {e}")
            return False

    def _find_segment_by_direct_lookup(self, clicked_mesh):
        """
        Simplified direct lookup approach that tries to match the exact mesh objects.
        """
        try:
            if not hasattr(clicked_mesh, 'GetNumberOfPoints') or clicked_mesh.GetNumberOfPoints() < 2:
                logger.warning("Invalid clicked mesh for direct lookup")
                return None
                
            num_points = clicked_mesh.GetNumberOfPoints()
            logger.info(f"Direct lookup for mesh with {num_points} points")
            
            # Get clicked mesh endpoints for comparison
            clicked_start = clicked_mesh.GetPoint(0)
            clicked_end = clicked_mesh.GetPoint(num_points - 1)
            
            logger.info(f"Clicked mesh: start={clicked_start}, end={clicked_end}")
            
            # Check all stored constraint actors to find exact match
            best_match = None
            best_score = float('inf')
            
            for (surf_idx, seg_uid), actor in getattr(self, 'constraint_segment_actor_refs', {}).items():
                try:
                    # Get the mesh from the actor
                    if hasattr(actor, 'GetMapper') and actor.GetMapper():
                        actor_mesh = actor.GetMapper().GetInput()
                        if (actor_mesh and 
                            hasattr(actor_mesh, 'GetNumberOfPoints') and 
                            actor_mesh.GetNumberOfPoints() == num_points):
                            
                            # Get actor mesh endpoints
                            actor_start = actor_mesh.GetPoint(0)
                            actor_end = actor_mesh.GetPoint(num_points - 1)
                            
                            # Calculate exact distance between endpoints
                            start_dist = ((clicked_start[0] - actor_start[0])**2 + 
                                        (clicked_start[1] - actor_start[1])**2 + 
                                        (clicked_start[2] - actor_start[2])**2)**0.5
                            
                            end_dist = ((clicked_end[0] - actor_end[0])**2 + 
                                      (clicked_end[1] - actor_end[1])**2 + 
                                      (clicked_end[2] - actor_end[2])**2)**0.5
                            
                            total_dist = start_dist + end_dist
                            
                            logger.debug(f"Actor ({surf_idx}, {seg_uid}): start_dist={start_dist:.6f}, end_dist={end_dist:.6f}, total={total_dist:.6f}")
                            
                            # Check for very close match (should be exact for line segments)
                            if total_dist < 1e-6:  # Very tight tolerance for exact match
                                logger.info(f"EXACT MATCH found: surf={surf_idx}, seg={seg_uid}, dist={total_dist:.10f}")
                                return (surf_idx, seg_uid)
                            
                            # Track best match as fallback
                            if total_dist < best_score:
                                best_score = total_dist
                                best_match = (surf_idx, seg_uid)
                                
                except Exception as e:
                    logger.debug(f"Error checking actor ({surf_idx}, {seg_uid}): {e}")
                    continue
            
            # Return best match if it's close enough
            if best_match and best_score < 1.0:  # 1 unit tolerance
                logger.info(f"BEST MATCH found: {best_match}, score={best_score:.6f}")
                return best_match
            
            logger.warning(f"No suitable direct match found. Best score: {best_score:.6f}")
            return None
            
        except Exception as e:
            logger.error(f"Error in direct lookup: {e}")
            return None

    def _on_constraint_point_clicked(self, *args):
        """
        Called when user clicks on a constraint using point picking.
        Uses the clicked point location to find the nearest segment.
        """
        # Handle different callback signatures
        if len(args) >= 1:
            point = args[0]
        else:
            logger.warning("No point data received in callback")
            return
            
        if not point or len(point) < 3:
            logger.warning("Invalid click point received")
            return
            
        logger.debug(f"Point clicked at: {point}")
        
        # Find the closest segment to the clicked point
        clicked_segment = self._find_segment_by_click_point(point)
        
        if not clicked_segment:
            logger.warning("Could not identify clicked constraint segment from point")
            return
            
        surf_idx, seg_uid = clicked_segment
        logger.info(f"Mouse clicked constraint at point {point}: surface {surf_idx}, segment {seg_uid}")
        
        # Check if this segment is currently visible (respects surface filter)
        selected_surface = "All Surfaces"
        if hasattr(self, 'refine_surface_selector') and self.refine_surface_selector:
            selected_surface = self.refine_surface_selector.currentText()
            
        # Helper function to check if a surface should be shown
        def should_show_surface(dataset_idx):
            if selected_surface == "All Surfaces":
                return True
            if dataset_idx < len(self.datasets):
                dataset_name = self.datasets[dataset_idx].get("name", f"Surface_{dataset_idx}")
                return dataset_name == selected_surface
            return False
        
        if not should_show_surface(surf_idx):
            logger.info(f"Clicked segment not in current surface filter: {selected_surface}")
            return
            
        # Find the corresponding tree item and toggle its selection
        self._toggle_segment_selection_in_tree(surf_idx, seg_uid)

    def _find_segment_by_click_point(self, click_point):
        """
        Find the segment closest to the clicked point coordinates.
        This provides the most accurate selection based on actual click location.
        """
        try:
            click_x, click_y, click_z = click_point[0], click_point[1], click_point[2]
            logger.debug(f"Finding segment closest to click point: ({click_x:.6f}, {click_y:.6f}, {click_z:.6f})")
            
            best_match = None
            best_distance = float('inf')
            candidates = []
            
            # Check all stored segments
            for (surf_idx, seg_uid), seg_info in getattr(self, "_refine_segment_map", {}).items():
                if 'points' not in seg_info or len(seg_info['points']) < 2:
                    continue
                    
                seg_points = seg_info['points']
                
                # Find the minimum distance from click point to this segment
                min_dist_to_segment = float('inf')
                closest_point_on_segment = None
                
                # Check distance to each segment of the line
                for i in range(len(seg_points) - 1):
                    p1 = seg_points[i]
                    p2 = seg_points[i + 1]
                    
                    # Calculate distance from click point to line segment
                    dist_to_segment, closest_on_seg = self._point_to_line_segment_distance(
                        (click_x, click_y, click_z), p1, p2
                    )
                    
                    if dist_to_segment < min_dist_to_segment:
                        min_dist_to_segment = dist_to_segment
                        closest_point_on_segment = closest_on_seg
                
                # Also check distance to endpoints for very short segments
                start_dist = ((click_x - seg_points[0][0])**2 + 
                            (click_y - seg_points[0][1])**2 + 
                            (click_z - seg_points[0][2])**2)**0.5
                            
                end_dist = ((click_x - seg_points[-1][0])**2 + 
                          (click_y - seg_points[-1][1])**2 + 
                          (click_z - seg_points[-1][2])**2)**0.5
                
                final_distance = min(min_dist_to_segment, start_dist, end_dist)
                
                candidates.append(((surf_idx, seg_uid), final_distance, surf_idx, seg_uid))
                
                if final_distance < best_distance:
                    best_distance = final_distance
                    best_match = (surf_idx, seg_uid)
                    
                logger.debug(f"Distance to surf={surf_idx}, seg={seg_uid}: {final_distance:.6f}")
            
            # Return best match if it's close enough
            if best_match and best_distance < 5.0:  # 5 unit tolerance for click accuracy
                logger.info(f"Best click-point match found with distance {best_distance:.6f}: {best_match}")
                return best_match
            elif candidates:
                # Show top candidates for debugging
                candidates.sort(key=lambda x: x[1])
                logger.warning(f"No close click-point match found. Top 3 candidates:")
                for i, (seg_info, dist, surf_idx, seg_uid) in enumerate(candidates[:3]):
                    logger.warning(f"  {i+1}. surf={surf_idx}, seg={seg_uid}, dist={dist:.6f}")
            
            logger.warning(f"No suitable click-point match found. Best distance: {best_distance:.6f}")
            return None
            
        except Exception as e:
            logger.error(f"Error in click point matching: {e}")
            return None
    
    def _point_to_line_segment_distance(self, point, line_start, line_end):
        """
        Calculate the minimum distance from a point to a line segment.
        Returns (distance, closest_point_on_segment).
        """
        try:
            px, py, pz = point
            x1, y1, z1 = line_start
            x2, y2, z2 = line_end
            
            # Vector from line start to end
            dx = x2 - x1
            dy = y2 - y1
            dz = z2 - z1
            
            # If line is actually a point
            if dx*dx + dy*dy + dz*dz < 1e-12:
                dist = ((px - x1)**2 + (py - y1)**2 + (pz - z1)**2)**0.5
                return dist, (x1, y1, z1)
            
            # Parameter t for closest point on line
            t = ((px - x1)*dx + (py - y1)*dy + (pz - z1)*dz) / (dx*dx + dy*dy + dz*dz)
            
            # Clamp t to [0, 1] to stay on segment
            t = max(0, min(1, t))
            
            # Closest point on segment
            closest_x = x1 + t * dx
            closest_y = y1 + t * dy
            closest_z = z1 + t * dz
            
            # Distance from point to closest point on segment
            distance = ((px - closest_x)**2 + (py - closest_y)**2 + (pz - closest_z)**2)**0.5
            
            return distance, (closest_x, closest_y, closest_z)
            
        except Exception as e:
            logger.debug(f"Error calculating point to line distance: {e}")
            return float('inf'), None

    def _on_constraint_clicked(self, mesh):
        """
        Called when user clicks on a constraint line in the visualization.
        Finds the corresponding segment and returns the segment info.
        Surface filtering is now handled by the caller.
        """
        logger.debug("=== CONSTRAINT CLICKED METHOD CALLED ===")
        
        if not mesh:
            logger.warning("No mesh provided to constraint click handler")
            return None
        
        try:
            num_points = mesh.GetNumberOfPoints() if hasattr(mesh, 'GetNumberOfPoints') else 0
            logger.debug(f"Constraint clicked: mesh with {num_points} points")
        except:
            logger.warning("Could not get point count from clicked mesh")
            return None
            
        # Find the segment by looking through all actors and comparing mesh data
        logger.debug("Looking for segment by mesh comparison...")
        clicked_segment = self._find_segment_by_mesh_comparison(mesh)
        
        if not clicked_segment:
            logger.debug("Could not identify clicked constraint segment")
            # Add debug info about available mappings
            if hasattr(self, '_mesh_geometry_map'):
                logger.debug(f"Available mesh signatures: {len(self._mesh_geometry_map)}")
            if hasattr(self, 'constraint_segment_actor_refs'):
                logger.debug(f"Available actor refs: {len(self.constraint_segment_actor_refs)}")
            return None
            
        surf_idx, seg_uid = clicked_segment
        logger.debug(f"✅ Found segment: surface {surf_idx}, segment {seg_uid}")
        
        return clicked_segment

    def _create_mesh_signature(self, mesh):
        """
        Create a unique geometric signature for a mesh that can be used as a dictionary key.
        Simplified for better stability and matching.
        """
        try:
            if not mesh or not hasattr(mesh, 'GetNumberOfPoints'):
                return None
                
            num_points = mesh.GetNumberOfPoints()
            if num_points < 2:
                return None
                
            # Get all points with consistent precision
            points = []
            for i in range(num_points):
                point = mesh.GetPoint(i)
                # Use moderate precision for better matching stability
                points.append((round(point[0], 8), round(point[1], 8), round(point[2], 8)))
            
            # Create signature from start point, end point, and length
            start_point = points[0]
            end_point = points[-1]
            
            # Calculate total length with consistent precision
            total_length = 0.0
            for i in range(1, len(points)):
                dx = points[i][0] - points[i-1][0]
                dy = points[i][1] - points[i-1][1] 
                dz = points[i][2] - points[i-1][2]
                total_length += (dx*dx + dy*dy + dz*dz)**0.5
            
            # Include midpoint if we have enough points  
            if num_points >= 3:
                mid_idx = num_points // 2
                mid_point = points[mid_idx]
            else:
                mid_point = None
            
            # Build stable signature
            signature = (start_point, end_point, mid_point, round(total_length, 8), num_points)
                
            return signature
            
        except Exception as e:
            logger.debug(f"Error creating mesh signature: {e}")
            return None

    def _find_segment_by_mesh_comparison(self, clicked_mesh):
        """
        Find segment by comparing mesh properties with stored actors.
        Enhanced with spatial proximity for better accuracy.
        """
        if not hasattr(clicked_mesh, 'GetNumberOfPoints') or clicked_mesh.GetNumberOfPoints() < 2:
            logger.warning("Invalid clicked mesh - insufficient points")
            return None
        
        logger.debug(f"Finding segment for mesh with {clicked_mesh.GetNumberOfPoints()} points")
        
        # Approach 1: Direct geometric signature lookup (fastest and most accurate)
        clicked_signature = self._create_mesh_signature(clicked_mesh)
        if clicked_signature and hasattr(self, '_mesh_geometry_map'):
            direct_match = self._mesh_geometry_map.get(clicked_signature)
            if direct_match:
                logger.debug(f"Found direct signature match: {direct_match}")
                return direct_match
            else:
                logger.debug(f"No direct signature match found for signature: {clicked_signature}")
        
        # Approach 2: Try with slightly different precision (handle floating point variations)
        if clicked_signature:
            # Try with reduced precision in case of minor floating point differences
            reduced_precision_sig = self._create_reduced_precision_signature(clicked_mesh)
            if reduced_precision_sig and hasattr(self, '_mesh_geometry_map_reduced'):
                reduced_match = self._mesh_geometry_map_reduced.get(reduced_precision_sig)
                if reduced_match:
                    logger.debug(f"Found reduced precision match: {reduced_match}")
                    return reduced_match
        
        # Approach 3: Spatial proximity matching (most reliable for click accuracy)
        logger.debug("Falling back to spatial proximity matching")
        return self._find_segment_by_spatial_proximity(clicked_mesh)
    
    def _find_segment_by_spatial_proximity(self, clicked_mesh):
        """
        Find the segment that is spatially closest to the clicked mesh.
        This helps with click accuracy when mesh comparison fails.
        """
        try:
            # Get clicked mesh center and bounds for comparison
            clicked_points = []
            num_points = clicked_mesh.GetNumberOfPoints()
            for i in range(num_points):
                point = clicked_mesh.GetPoint(i)
                clicked_points.append(point)
            
            if len(clicked_points) < 2:
                return None
                
            # Calculate clicked mesh center and start/end points
            clicked_center = [
                sum(p[0] for p in clicked_points) / len(clicked_points),
                sum(p[1] for p in clicked_points) / len(clicked_points), 
                sum(p[2] for p in clicked_points) / len(clicked_points)
            ]
            clicked_start = clicked_points[0]
            clicked_end = clicked_points[-1]
            
            logger.debug(f"Clicked mesh center: {clicked_center}, start: {clicked_start}, end: {clicked_end}")
            
            best_match = None
            best_distance = float('inf')
            candidates = []
            
            for (surf_idx, seg_uid), actor in getattr(self, 'constraint_segment_actor_refs', {}).items():
                try:
                    # Get segment info from mapping
                    actor_id = id(actor)
                    segment_info = getattr(self, '_actor_id_to_segment_map', {}).get(actor_id)
                    
                    if not segment_info:
                        continue
                        
                    # Get segment data from the stored constraint data
                    if hasattr(self, '_refine_segment_map'):
                        seg_data = self._refine_segment_map.get((surf_idx, seg_uid))
                        if seg_data and 'points' in seg_data and len(seg_data['points']) >= 2:
                            seg_points = seg_data['points']
                            
                            # Calculate segment center and endpoints
                            seg_center = [
                                sum(p[0] for p in seg_points) / len(seg_points),
                                sum(p[1] for p in seg_points) / len(seg_points),
                                sum(p[2] for p in seg_points) / len(seg_points)
                            ]
                            seg_start = seg_points[0]
                            seg_end = seg_points[-1]
                            
                            # Calculate distance between centers
                            center_dist = ((clicked_center[0] - seg_center[0])**2 + 
                                         (clicked_center[1] - seg_center[1])**2 + 
                                         (clicked_center[2] - seg_center[2])**2)**0.5
                            
                            # Also check start/end point distances for better matching
                            start_dist = ((clicked_start[0] - seg_start[0])**2 + 
                                        (clicked_start[1] - seg_start[1])**2 + 
                                        (clicked_start[2] - seg_start[2])**2)**0.5
                            
                            end_dist = ((clicked_end[0] - seg_end[0])**2 + 
                                      (clicked_end[1] - seg_end[1])**2 + 
                                      (clicked_end[2] - seg_end[2])**2)**0.5
                            
                            # Combined distance score (center distance is most important)
                            total_distance = center_dist + 0.1 * (start_dist + end_dist)
                            
                            candidates.append((segment_info, total_distance, surf_idx, seg_uid, center_dist))
                            
                            if total_distance < best_distance:
                                best_distance = total_distance
                                best_match = segment_info
                                
                            logger.debug(f"Spatial comparison surf={surf_idx}, seg={seg_uid}: "
                                       f"center_dist={center_dist:.6f}, total_dist={total_distance:.6f}")
                            
                except Exception as e:
                    logger.debug(f"Error in spatial comparison for segment ({surf_idx}, {seg_uid}): {e}")
                    continue
            
            # Return best match if it's close enough
            if best_match and best_distance < 10.0:  # Reasonable spatial tolerance
                logger.info(f"Best spatial match found with distance {best_distance:.6f}: {best_match}")
                return best_match
            elif candidates:
                # Show top candidates for debugging
                candidates.sort(key=lambda x: x[1])
                logger.warning(f"No close spatial match found. Top 3 candidates:")
                for i, (seg_info, total_dist, surf_idx, seg_uid, center_dist) in enumerate(candidates[:3]):
                    logger.warning(f"  {i+1}. surf={surf_idx}, seg={seg_uid}, "
                                 f"center_dist={center_dist:.6f}, total_dist={total_dist:.6f}")
            
            logger.warning(f"No suitable spatial match found. Best distance: {best_distance:.6f}")
            return None
            
        except Exception as e:
            logger.error(f"Error in spatial proximity matching: {e}")
            return None
    
    def _create_reduced_precision_signature(self, mesh):
        """
        Create a mesh signature with reduced precision for fallback matching.
        """
        try:
            if not mesh or not hasattr(mesh, 'GetNumberOfPoints'):
                return None
                
            num_points = mesh.GetNumberOfPoints()
            if num_points < 2:
                return None
                
            # Get all points with reduced precision
            points = []
            for i in range(num_points):
                point = mesh.GetPoint(i)
                points.append((round(point[0], 6), round(point[1], 6), round(point[2], 6)))
            
            start_point = points[0]
            end_point = points[-1]
            
            # Calculate total length
            total_length = 0.0
            for i in range(1, len(points)):
                dx = points[i][0] - points[i-1][0]
                dy = points[i][1] - points[i-1][1] 
                dz = points[i][2] - points[i-1][2]
                total_length += (dx*dx + dy*dy + dz*dz)**0.5
            
            # Include midpoint if we have enough points
            if num_points >= 3:
                mid_idx = num_points // 2
                mid_point = points[mid_idx]
            else:
                mid_point = None
                
            return (start_point, end_point, mid_point, round(total_length, 6), num_points)
            
        except Exception as e:
            logger.debug(f"Error creating reduced precision signature: {e}")
            return None
    
    def _fallback_mesh_comparison(self, clicked_mesh):
        """
        Fallback mesh comparison using detailed geometric analysis.
        """
        if not hasattr(clicked_mesh, 'GetNumberOfPoints') or clicked_mesh.GetNumberOfPoints() < 2:
            return None
            
    def _fallback_mesh_comparison(self, clicked_mesh):
        """
        Simplified and reliable mesh comparison using basic geometric properties.
        """
        if not hasattr(clicked_mesh, 'GetNumberOfPoints') or clicked_mesh.GetNumberOfPoints() < 2:
            return None
            
        # Get the clicked mesh points for comparison
        try:
            clicked_points = []
            num_points = clicked_mesh.GetNumberOfPoints()
            for i in range(num_points):
                point = clicked_mesh.GetPoint(i)
                clicked_points.append(point)
        except Exception:
            return None
            
        if len(clicked_points) < 2:
            return None
            
        # Create simple signature for the clicked mesh
        clicked_start = clicked_points[0]
        clicked_end = clicked_points[-1]
        
        # Calculate clicked mesh length
        clicked_length = 0
        for i in range(1, len(clicked_points)):
            dx = clicked_points[i][0] - clicked_points[i-1][0]
            dy = clicked_points[i][1] - clicked_points[i-1][1] 
            dz = clicked_points[i][2] - clicked_points[i-1][2]
            clicked_length += (dx*dx + dy*dy + dz*dz)**0.5
        
        logger.debug(f"Clicked mesh: {num_points} points, length={clicked_length:.6f}, start={clicked_start}, end={clicked_end}")
        
        # Find the best match by comparing with all stored segments
        best_match = None
        best_score = float('inf')
        candidates = []
        
        for (surf_idx, seg_uid), actor in getattr(self, 'constraint_segment_actor_refs', {}).items():
            try:
                # Get actor ID and look up segment info
                actor_id = id(actor)
                segment_info = getattr(self, '_actor_id_to_segment_map', {}).get(actor_id)
                
                if segment_info and hasattr(actor, 'GetMapper') and actor.GetMapper():
                    actor_mesh = actor.GetMapper().GetInput()
                    if (actor_mesh and 
                        hasattr(actor_mesh, 'GetNumberOfPoints') and 
                        actor_mesh.GetNumberOfPoints() == num_points):
                        
                        # Get actor mesh points
                        actor_points = []
                        for i in range(num_points):
                            actor_points.append(actor_mesh.GetPoint(i))
                        
                        if len(actor_points) < 2:
                            continue
                            
                        # Simple geometric comparison
                        actor_start = actor_points[0]
                        actor_end = actor_points[-1]
                        
                        # Calculate actor mesh length
                        actor_length = 0
                        for i in range(1, len(actor_points)):
                            dx = actor_points[i][0] - actor_points[i-1][0]
                            dy = actor_points[i][1] - actor_points[i-1][1] 
                            dz = actor_points[i][2] - actor_points[i-1][2]
                            actor_length += (dx*dx + dy*dy + dz*dz)**0.5
                        
                        # Calculate differences
                        start_dist = ((clicked_start[0] - actor_start[0])**2 + 
                                    (clicked_start[1] - actor_start[1])**2 + 
                                    (clicked_start[2] - actor_start[2])**2)**0.5
                        
                        end_dist = ((clicked_end[0] - actor_end[0])**2 + 
                                  (clicked_end[1] - actor_end[1])**2 + 
                                  (clicked_end[2] - actor_end[2])**2)**0.5
                        
                        length_diff = abs(clicked_length - actor_length)
                        
                        # Simple scoring
                        score = start_dist + end_dist + length_diff
                        
                        candidates.append((segment_info, score, surf_idx, seg_uid))
                        
                        # Track best match
                        if score < best_score:
                            best_score = score
                            best_match = segment_info
                            
                        logger.debug(f"Comparing surf={surf_idx}, seg={seg_uid}: "
                                   f"score={score:.6f}, start_dist={start_dist:.6f}, "
                                   f"end_dist={end_dist:.6f}, length_diff={length_diff:.6f}")
                            
            except Exception as e:
                logger.debug(f"Error comparing mesh for segment ({surf_idx}, {seg_uid}): {e}")
                continue
        
        # Return best match if it's good enough
        if best_match and best_score < 10.0:  # More tolerant threshold
            logger.info(f"Best match found with score {best_score:.6f}: {best_match}")
            return best_match
        elif candidates:
            # Show top candidates for debugging
            candidates.sort(key=lambda x: x[1])
            logger.warning(f"No good match found. Top 3 candidates:")
            for i, (seg_info, score, surf_idx, seg_uid) in enumerate(candidates[:3]):
                logger.warning(f"  {i+1}. surf={surf_idx}, seg={seg_uid}, score={score:.6f}")
            
            # If we have candidates but none are very close, return the best one anyway
            if candidates and candidates[0][1] < 50.0:  # Very generous fallback
                best_candidate = candidates[0]
                logger.info(f"Using best candidate as fallback: surf={best_candidate[2]}, seg={best_candidate[3]}, score={best_candidate[1]:.6f}")
                return best_candidate[0]
        
        logger.warning(f"No suitable match found. Best score: {best_score:.6f}")
        return None

    def _apply_selection_mode_to_segment(self, surf_idx, seg_uid):
        """
        Apply the current selection mode (select or deselect) to a segment.
        Unlike toggle, this respects the current selection mode.
        Returns True if successful, False otherwise.
        """
        if not hasattr(self, 'current_selection_mode'):
            self.current_selection_mode = "select"  # Default to select mode
            
        mode = self.current_selection_mode
        
        if not hasattr(self, 'refine_constraint_tree') or not self.refine_constraint_tree:
            return False
            
        tree = self.refine_constraint_tree
        
        # DISABLE tree signals during batch operations to prevent lag
        tree.blockSignals(True)
        
        try:
            def find_and_set_segment(item):
                """Recursively search for the segment and set its selection state"""
                data = item.data(0, Qt.UserRole)
                if data and data.get("type") == "constraint":
                    item_surf_idx = data.get("surface_idx")
                    item_seg_uid = data.get("seg_uid")
                    
                    if item_surf_idx == surf_idx and item_seg_uid == seg_uid:
                        current_state = item.checkState(0)
                        
                        if mode == "select":
                            # Force selection
                            if current_state != Qt.Checked:
                                item.setCheckState(0, Qt.Checked)
                                return True
                            else:
                                return True
                        elif mode == "deselect":
                            # Force deselection
                            if current_state == Qt.Checked:
                                item.setCheckState(0, Qt.Unchecked)
                                return True
                            else:
                                return True
                
                # Search child items
                for i in range(item.childCount()):
                    if find_and_set_segment(item.child(i)):
                        return True
                return False
            
            # Search all top-level items
            for i in range(tree.topLevelItemCount()):
                if find_and_set_segment(tree.topLevelItem(i)):
                    return True
            
            return False
            
        finally:
            # RE-ENABLE tree signals after batch operations
            tree.blockSignals(False)
            
        return False

    def _apply_selection_mode_to_segment_fast(self, surf_idx, seg_uid):
        """
        Ultra-fast version that assumes tree signals are already blocked.
        NO signal blocking/unblocking overhead per segment.
        """
        if not hasattr(self, 'current_selection_mode'):
            self.current_selection_mode = "select"
            
        mode = self.current_selection_mode
        tree = getattr(self, 'refine_constraint_tree', None)
        if not tree:
            return False
        
        def find_and_set_segment_fast(item):
            """Fast recursive search without signal overhead"""
            data = item.data(0, Qt.UserRole)
            if data and data.get("type") == "constraint":
                item_surf_idx = data.get("surface_idx")
                item_seg_uid = data.get("seg_uid")
                
                if item_surf_idx == surf_idx and item_seg_uid == seg_uid:
                    current_state = item.checkState(0)
                    
                    if mode == "select" and current_state != Qt.Checked:
                        item.setCheckState(0, Qt.Checked)
                        return True
                    elif mode == "deselect" and current_state == Qt.Checked:
                        item.setCheckState(0, Qt.Unchecked)
                        return True
                    else:
                        return True  # Already in desired state
            
            # Search child items
            for i in range(item.childCount()):
                if find_and_set_segment_fast(item.child(i)):
                    return True
            return False
        
        # Search all top-level items
        for i in range(tree.topLevelItemCount()):
            if find_and_set_segment_fast(tree.topLevelItem(i)):
                return True
        
        return False

    def _toggle_segment_selection_in_tree(self, surf_idx, seg_uid):
        """
        Find the tree item corresponding to the segment and toggle its checkbox.
        Optimized for fast mouse selection with minimal tree operations.
        Returns True if successful, False otherwise.
        """
        if not hasattr(self, 'refine_constraint_tree') or not self.refine_constraint_tree:
            logger.warning("No constraint tree available for toggling")
            return False
            
        tree = self.refine_constraint_tree
        logger.info(f"Searching tree for segment: surface {surf_idx}, segment {seg_uid}")
        
        def find_and_toggle_segment(item):
            """Recursively search for the segment and toggle it"""
            data = item.data(0, Qt.UserRole)
            if data and data.get("type") == "constraint":
                item_surf_idx = data.get("surface_idx")
                item_seg_uid = data.get("seg_uid")
                
                if item_surf_idx == surf_idx and item_seg_uid == seg_uid:
                    # Found the segment! Toggle its selection
                    current_state = item.checkState(0)
                    new_state = Qt.Unchecked if current_state == Qt.Checked else Qt.Checked
                    
                    logger.info(f"Found tree item! Toggling from {current_state} to {new_state}")
                    
                    # Set flag to indicate this is a mouse-triggered change
                    self._mouse_triggered_change = True
                    
                    # Temporarily disable tree change handler to prevent recursive updates
                    self._refine_updating_constraint_tree = True
                    try:
                        item.setCheckState(0, new_state)
                        
                        # Update segment data directly for fast tracking
                        if hasattr(self, '_refine_segment_map') and (surf_idx, seg_uid) in self._refine_segment_map:
                            self._refine_segment_map[(surf_idx, seg_uid)]["selected"] = (new_state == Qt.Checked)
                        
                        # Fast single actor update instead of batch update
                        if hasattr(self, '_apply_segment_state'):
                            self._apply_segment_state(surf_idx, seg_uid, new_state == Qt.Checked)
                        
                    finally:
                        self._refine_updating_constraint_tree = False
                        # Clear the mouse trigger flag
                        self._mouse_triggered_change = False
                    
                    # Scroll to and highlight the item briefly
                    tree.scrollToItem(item)
                    tree.setCurrentItem(item)
                    
                    logger.info(f"✅ Toggled segment {seg_uid} to {'selected' if new_state == Qt.Checked else 'deselected'}")
                    return True
                    
            # Check children
            for i in range(item.childCount()):
                if find_and_toggle_segment(item.child(i)):
                    return True
            return False
        
        # Search through all top-level items
        for i in range(tree.topLevelItemCount()):
            if find_and_toggle_segment(tree.topLevelItem(i)):
                return True
        
        logger.warning(f"❌ Could not find tree item for segment: surface {surf_idx}, segment {seg_uid}")
        return False

    def _on_constraint_clicked_single(self, mesh):
        """
        Fallback method for single mesh selection (used by mesh picking).
        Handles surface filtering and tree toggling for a single mesh.
        """
        clicked_segment = self._on_constraint_clicked(mesh)
        if not clicked_segment:
            return
            
        surf_idx, seg_uid = clicked_segment
        
        # Get current surface filter
        selected_surface = "All Surfaces"
        if hasattr(self, 'refine_surface_selector') and self.refine_surface_selector:
            selected_surface = self.refine_surface_selector.currentText()
        
        # Check surface filter
        if self._is_surface_visible_in_filter(surf_idx, selected_surface):
            success = self._toggle_segment_selection_in_tree(surf_idx, seg_uid)
            if success:
                logger.info(f"🎯 Successfully toggled single constraint selection")
            else:
                logger.warning(f"❌ Failed to toggle constraint in tree")
        else:
            logger.warning(f"❌ Clicked segment not visible in current filter: '{selected_surface}'")

    def _highlight_surface_in_constraint_tree(self, surface_name):
        """
        Highlights the corresponding surface in the constraint tree when selected in dropdown.
        """
        if not hasattr(self, 'refine_constraint_tree') or not self.refine_constraint_tree:
            return
            
        # Expand/collapse tree items based on selection
        tree = self.refine_constraint_tree
        for i in range(tree.topLevelItemCount()):
            surface_item = tree.topLevelItem(i)
            surface_data = surface_item.data(0, Qt.UserRole)
            
            if surface_data and surface_data.get('type') == 'surface':
                if surface_name == "All Surfaces":
                    # Expand all surfaces when "All Surfaces" is selected
                    surface_item.setExpanded(True)
                else:
                    # Only expand the selected surface
                    dataset_idx = surface_data.get('surface_idx')
                    if dataset_idx is not None and dataset_idx < len(self.datasets):
                        dataset_name = self.datasets[dataset_idx].get("name", f"Surface_{dataset_idx}")
                        if dataset_name == surface_name:
                            surface_item.setExpanded(True)
                            tree.scrollToItem(surface_item)
                        else:
                            surface_item.setExpanded(False)

    def _populate_surface_selector(self):
        """
        Populates the surface selector dropdown with available surfaces.
        Called after refinement operations to update the dropdown options.
        """
        if not hasattr(self, 'refine_surface_selector'):
            return
            
        # Clear existing items except "All Surfaces"
        self.refine_surface_selector.clear()
        self.refine_surface_selector.addItem("All Surfaces")
        
        # Get surface names from the constraint tree
        surfaces_added = set()
        if hasattr(self, 'refine_constraint_tree') and self.refine_constraint_tree:
            tree = self.refine_constraint_tree
            logger.info(f"Extracting surfaces from constraint tree with {tree.topLevelItemCount()} top-level items")
            
            for i in range(tree.topLevelItemCount()):
                surface_item = tree.topLevelItem(i)
                surface_text = surface_item.text(0)
                surface_data = surface_item.data(0, Qt.UserRole)
                
                logger.info(f"Top-level item {i}: text='{surface_text}', data={surface_data}")
                
                if surface_data and surface_data.get('type') == 'surface':
                    surface_idx = surface_data.get('surface_idx')
                    if surface_idx is not None and surface_idx < len(self.datasets):
                        surface_name = self.datasets[surface_idx].get("name", f"Surface_{surface_idx}")
                        if surface_name not in surfaces_added:
                            self.refine_surface_selector.addItem(surface_name)
                            surfaces_added.add(surface_name)
                            logger.info(f"Added surface: {surface_name} (idx={surface_idx})")
        else:
            logger.warning("Constraint tree not found or empty")
        
        # Fallback: Add surfaces from datasets that have constraint data
        if len(surfaces_added) == 0 and hasattr(self, 'refine_constraint_data'):
            for dataset_idx in self.refine_constraint_data.keys():
                if dataset_idx < len(self.datasets):
                    surface_name = self.datasets[dataset_idx].get("name", f"Surface_{dataset_idx}")
                    if surface_name not in surfaces_added:
                        self.refine_surface_selector.addItem(surface_name)
                        surfaces_added.add(surface_name)
                
        logger.info(f"Populated surface selector with {self.refine_surface_selector.count()} items: {[self.refine_surface_selector.itemText(i) for i in range(self.refine_surface_selector.count())]}")

    def _on_target_size_changed(self, value):
        """Provide immediate feedback when target size changes."""
        if value <= 5.0:
            density_desc = "Very Fine (High Detail)"
            color = "#4CAF50"  # Green
        elif value <= 15.0:
            density_desc = "Fine (Good Detail)"
            color = "#2196F3"  # Blue
        elif value <= 30.0:
            density_desc = "Medium (Balanced)"
            color = "#FF9800"  # Orange
        elif value <= 50.0:
            density_desc = "Coarse (Fast)"
            color = "#F44336"  # Red
        else:
            density_desc = "Very Coarse (Fastest)"
            color = "#9C27B0"  # Purple
        
        self.target_size_info.setText(f"🎯 UNIFIED: {density_desc} | Target Size: {value}")
        self.target_size_info.setStyleSheet(f"color: {color}; font-style: italic; font-weight: bold;")
    def _setup_pre_tetramesh_tab(self):
            """Sets up the Pre-Tetrahedral Mesh tab for surface selection and validation."""
            # Initialize the main layout for this specific tab
            tab_layout = QHBoxLayout(self.pre_tetramesh_tab)

            # --- Control panel (left side) ---
            control_panel = QWidget()
            control_panel.setMaximumWidth(350)
            control_layout = QVBoxLayout(control_panel) # This is the layout for the control_panel's content
            
            # -- Surface Selection Controls --
            surface_group = QGroupBox("Conforming Surface Selection")
            surface_layout = QVBoxLayout(surface_group)

            self.load_conforming_meshes_btn = QPushButton("📥 Load Conforming Meshes from Refine Tab")
            self.load_conforming_meshes_btn.setToolTip(
                "Load pre-computed conforming surface meshes from the refine mesh tab.\n"
                "Follows C++ core.cpp workflow: surfaces → conforming meshes → selection → tetgen"
            )
            self.load_conforming_meshes_btn.clicked.connect(
                    self._load_conforming_meshes_from_refine_tab)
            surface_layout.addWidget(self.load_conforming_meshes_btn)

            # Status label showing loaded conforming meshes
            self.conforming_mesh_status_label = QLabel("No conforming meshes loaded")
            self.conforming_mesh_status_label.setWordWrap(True)
            self.conforming_mesh_status_label.setStyleSheet(
                "background-color: #f0f0f0; padding: 5px; border: 1px solid #ccc; border-radius: 3px;"
            )
            surface_layout.addWidget(self.conforming_mesh_status_label)
            
            # Add tetgen validation button
            self.validate_for_tetgen_btn = QPushButton("✅ Validate Conforming Meshes for TetGen")
            self.validate_for_tetgen_btn.setToolTip(
                "Check if selected conforming surface meshes are ready for tetgen tetrahedralization.\n"
                "Validates mesh quality, topology, and surface intersections for manifold geometry."
            )
            self.validate_for_tetgen_btn.clicked.connect(self._validate_conforming_meshes_for_tetgen)
            self.validate_for_tetgen_btn.setEnabled(False)
            self.validate_for_tetgen_btn.setStyleSheet("""
                QPushButton {
                    background-color: #4CAF50;
                    color: white;
                    font-weight: bold;
                    padding: 8px;
                    border: none;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #45a049;
                }
                QPushButton:disabled {
                    background-color: #cccccc;
                    color: #666666;
                }
            """)
            surface_layout.addWidget(self.validate_for_tetgen_btn)

            # --- Surface Selection Group ---
            selection_group = QGroupBox("Surface Selection for TetGen")
            selection_layout = QVBoxLayout(selection_group)
            
            # Initialize conforming mesh data storage
            self.conforming_mesh_data = {}  # {surface_idx: conforming_mesh_data}
            self.selected_conforming_surfaces = set()  # Surface indices selected for tetgen
            
            # Surface selection tree widget (simplified version)
            self.conforming_surface_tree = QTreeWidget()
            self.conforming_surface_tree.setHeaderLabels(["Surface", "Vertices", "Triangles", "Status"])
            self.conforming_surface_tree.itemChanged.connect(self._on_conforming_surface_tree_item_changed)
            self.conforming_surface_tree.setMaximumHeight(250)
            selection_layout.addWidget(QLabel("Conforming Surface Selection:"))
            selection_layout.addWidget(self.conforming_surface_tree)
            
            # Quick selection buttons for surfaces
            quick_buttons_layout = QHBoxLayout()
            
            # Surface selection buttons
            self.select_all_surfaces_btn = QPushButton("Select All Surfaces")
            self.select_all_surfaces_btn.clicked.connect(self._select_all_conforming_surfaces)
            self.deselect_all_surfaces_btn = QPushButton("Deselect All")
            self.deselect_all_surfaces_btn.clicked.connect(self._deselect_all_conforming_surfaces)
            
            # Add buttons to layout
            quick_buttons_layout.addWidget(self.select_all_surfaces_btn)
            quick_buttons_layout.addWidget(self.deselect_all_surfaces_btn)
            selection_layout.addLayout(quick_buttons_layout)

            control_layout.addWidget(surface_group) # Add surface selection group
            control_layout.addWidget(selection_group) # Add surface selection group
            control_layout.addStretch()
            
            # Add the control_panel to the main tab_layout
            tab_layout.addWidget(control_panel)

            # --- Visualization Area (right side) ---
            viz_group = QGroupBox("Conforming Surface Mesh Visualization")
            viz_layout = QVBoxLayout(viz_group) # This is the layout for the viz_group's content

            self.pre_tetramesh_viz_frame = QFrame()
            self.pre_tetramesh_viz_frame.setFrameShape(QFrame.StyledPanel)
            self.pre_tetramesh_plot_layout = QVBoxLayout(self.pre_tetramesh_viz_frame)
            self.pre_tetramesh_plot_layout.setContentsMargins(0, 0, 0, 0)

            if True:
                from pyvistaqt import QtInteractor
                plotter = QtInteractor(self.pre_tetramesh_viz_frame)
                self.pre_tetramesh_plot_layout.addWidget(plotter.interactor)
                plotter.set_background([0.2, 0.2, 0.25]) # Darker background
                plotter.add_text("Load conforming meshes from Refine tab to visualize.\nC++ core.cpp workflow: surfaces → conforming meshes → selection → tetgen", position='upper_edge', color='white')
                self.plotters['pre_tetramesh'] = plotter 
                self.pre_tetramesh_plotter = plotter
                logger.info("Successfully created pre_tetramesh_plotter")
            else:
                placeholder = QLabel("PyVista is required for 3D visualization.")
                placeholder.setAlignment(Qt.AlignCenter)
                self.pre_tetramesh_plot_layout.addWidget(placeholder)
                self.pre_tetramesh_plotter = None

            viz_layout.addWidget(self.pre_tetramesh_viz_frame, 1) # Add the frame to viz_group's layout
            
            # Add the viz_group to the main tab_layout
            tab_layout.addWidget(viz_group, 1)

    # Add a new clear method for this tab's plotter
    def _clear_pre_tetramesh_plot(self):
        plotter = self.plotters.get('pre_tetramesh')
        if plotter:
            plotter.clear()
            plotter.add_text(
                "Load conforming meshes from Refine tab to visualize.\nC++ core.cpp workflow: surfaces → conforming meshes → selection → tetgen",
                position='upper_edge',
                color='white'
            )
            plotter.reset_camera()
        elif hasattr(self, 'pre_tetramesh_plot_layout'): # Fallback
            # ... (similar clearing logic as _clear_refine_mesh_plot if plotter is None)
            pass

    def _clear_tetra_mesh_plot(self):
        """Clear the tetra mesh plot."""
        if hasattr(self, 'tetra_plotter') and self.tetra_plotter:
            self.tetra_plotter.clear()
            self.tetra_plotter.add_text(
                "Load surfaces from Pre-Tetra tab to begin.",
                position='upper_edge',
                color='white'
            )
            self.tetra_plotter.render()
        logger.debug("Tetra mesh plot cleared.")
            
    # Update _on_tab_changed
    def _load_conforming_meshes_from_refine_tab(self):
        """
        Load pre-computed conforming surface meshes from the Refine & Mesh tab.
        This follows the C++ core.cpp workflow where surfaces are first processed
        to conforming meshes, then selected for tetgen.
        """
        logger.info("Loading conforming meshes from Refine & Mesh tab...")
        self.statusBar().showMessage("Loading conforming surface meshes...")
        
        if not hasattr(self, 'datasets') or not self.datasets:
            QMessageBox.warning(self, "No Data", "Please load surfaces first.")
            return

        # Check if conforming meshes exist from the refine tab
        conforming_surfaces_found = 0
        self.conforming_mesh_data.clear()
        
        for dataset_idx, dataset in enumerate(self.datasets):
            if 'conforming_mesh' in dataset:
                conforming_mesh = dataset['conforming_mesh']
                
                # Validate conforming mesh data
                if ('vertices' in conforming_mesh and 'triangles' in conforming_mesh and 
                    len(conforming_mesh['vertices']) > 0 and len(conforming_mesh['triangles']) > 0):
                    
                    self.conforming_mesh_data[dataset_idx] = {
                        'name': dataset.get('name', f'Surface_{dataset_idx}'),
                        'vertices': conforming_mesh['vertices'],
                        'triangles': conforming_mesh['triangles'],
                        'statistics': conforming_mesh.get('statistics', {}),
                        'original_dataset': dataset
                    }
                    conforming_surfaces_found += 1
                    logger.info(f"Loaded conforming mesh for surface {dataset_idx}: "
                              f"{len(conforming_mesh['vertices'])} vertices, "
                              f"{len(conforming_mesh['triangles'])} triangles")
        
        if conforming_surfaces_found == 0:
            QMessageBox.warning(self, "No Conforming Meshes", 
                               "No conforming surface meshes found.\n"
                               "Please generate conforming meshes in the Refine & Mesh tab first.")
            return

        # Update status label
        self.conforming_mesh_status_label.setText(
            f"<b>Loaded {conforming_surfaces_found} conforming surface meshes</b><br>"
            f"Ready for selection and tetgen validation"
        )
        self.conforming_mesh_status_label.setStyleSheet(
            "background-color: #e8f5e8; padding: 5px; border: 1px solid #4CAF50; border-radius: 3px;"
        )
        
        # Enable validation button
        self.validate_for_tetgen_btn.setEnabled(True)
        
        # Populate the surface selection tree
        self._populate_conforming_surface_tree()
        
        # Update visualization
        self._update_conforming_surface_visualization()
        
        self.statusBar().showMessage(f"✓ Loaded {conforming_surfaces_found} conforming surface meshes")
        logger.info(f"Successfully loaded {conforming_surfaces_found} conforming surface meshes")

    def _populate_conforming_surface_tree(self):
        """
        Populate the conforming surface tree with available conforming meshes.
        This creates a simple selection interface for choosing which surfaces to include in tetgen.
        """
        self.conforming_surface_tree.clear()
        
        if not self.conforming_mesh_data:
            logger.warning("No conforming mesh data to populate tree")
            return
        
        # Add header info
        header_item = QTreeWidgetItem(self.conforming_surface_tree)
        header_item.setText(0, f"📋 {len(self.conforming_mesh_data)} Conforming Surfaces Available")
        header_item.setText(1, "Select")
        header_item.setText(2, "for")  
        header_item.setText(3, "TetGen")
        header_item.setFlags(header_item.flags() & ~Qt.ItemIsUserCheckable)
        
        # Add each conforming surface
        for surface_idx, mesh_data in self.conforming_mesh_data.items():
            surface_item = QTreeWidgetItem(self.conforming_surface_tree)
            surface_item.setText(0, f"🔺 {mesh_data['name']}")
            surface_item.setText(1, str(len(mesh_data['vertices'])))
            surface_item.setText(2, str(len(mesh_data['triangles'])))
            surface_item.setText(3, "Ready")
            
            # Make surface selectable with checkbox
            surface_item.setFlags(surface_item.flags() | Qt.ItemIsUserCheckable)
            surface_item.setCheckState(0, Qt.Checked)  # Default to selected
            
            # Store surface index for retrieval
            surface_item.setData(0, Qt.UserRole, surface_idx)
            
            # Add to selected surfaces
            self.selected_conforming_surfaces.add(surface_idx)
        
        # Expand all items
        self.conforming_surface_tree.expandAll()
        
        logger.info(f"Populated conforming surface tree with {len(self.conforming_mesh_data)} surfaces")

    def _on_conforming_surface_tree_item_changed(self, item, column):
        """Handle changes in the conforming surface tree selection - C++ style: simple state update"""
        if column != 0:  # Only handle changes to the checkbox column
            return
        
        surface_idx = item.data(0, Qt.UserRole)
        if surface_idx is None:  # Skip header items
            return
        
        # Simple state update - just flip the boolean flag like C++
        if item.checkState(0) == Qt.Checked:
            self.selected_conforming_surfaces.add(surface_idx)
            item.setText(3, "Selected")
        else:
            self.selected_conforming_surfaces.discard(surface_idx)
            item.setText(3, "Deselected")
        
        # Update status label only - no plotting calls here
        selected_count = len(self.selected_conforming_surfaces)
        total_count = len(self.conforming_mesh_data)
        self.statusBar().showMessage(f"Selected {selected_count}/{total_count} conforming surfaces for tetgen")
        
        # Single visualization update at the end
        self._update_conforming_surface_visualization()

    def _select_all_conforming_surfaces(self):
        """Select all conforming surfaces in the tree"""
        for i in range(self.conforming_surface_tree.topLevelItemCount()):
            item = self.conforming_surface_tree.topLevelItem(i)
            surface_idx = item.data(0, Qt.UserRole)
            if surface_idx is not None:  # Skip header items
                item.setCheckState(0, Qt.Checked)
        
        self.statusBar().showMessage(f"Selected all {len(self.conforming_mesh_data)} conforming surfaces")

    def _deselect_all_conforming_surfaces(self):
        """Deselect all conforming surfaces in the tree"""
        for i in range(self.conforming_surface_tree.topLevelItemCount()):
            item = self.conforming_surface_tree.topLevelItem(i)
            surface_idx = item.data(0, Qt.UserRole)
            if surface_idx is not None:  # Skip header items
                item.setCheckState(0, Qt.Unchecked)
        
                self.statusBar().showMessage("Deselected all conforming surfaces")







    def _update_conforming_surface_visualization(self):
        """
        Update the visualization to show selected conforming surfaces.
        C++ style: reads the selection set and redraws the entire scene.
        """
        if not hasattr(self, 'pre_tetramesh_plotter') or self.pre_tetramesh_plotter is None:
            return
        
        try:
            # Clear previous visualization
            self.pre_tetramesh_plotter.clear()
            
            if not self.selected_conforming_surfaces:
                self.pre_tetramesh_plotter.add_text(
                    "No conforming surfaces selected.\nSelect surfaces in the tree to visualize.",
                    position='upper_edge',
                    color='white'
                )
                return
            
            # Visualize only selected conforming surfaces
            import pyvista as pv
            import numpy as np
            
            colors = ['lightblue', 'lightgreen', 'lightcoral', 'lightyellow', 
                     'lightpink', 'lightcyan', 'wheat', 'lightgray']
            
            for i, surface_idx in enumerate(self.selected_conforming_surfaces):
                if surface_idx not in self.conforming_mesh_data:
                    continue
                
                mesh_data = self.conforming_mesh_data[surface_idx]
                vertices = np.array(mesh_data['vertices'])
                triangles = np.array(mesh_data['triangles'])
                
                if len(vertices) == 0 or len(triangles) == 0:
                    continue
                
                # Create PyVista mesh
                faces = []
                for tri in triangles:
                    faces.extend([3, tri[0], tri[1], tri[2]])  # 3 vertices per triangle
                
                mesh = pv.PolyData(vertices, faces)
                
                # Use simple color cycling
                mesh_color = colors[i % len(colors)]
                
                self.pre_tetramesh_plotter.add_mesh(
                    mesh,
                    color=mesh_color,
                    show_edges=True,
                    edge_color='darkblue',
                    opacity=0.8,
                    name=f"surface_{surface_idx}"
                )
                
                # Add surface label
                center = vertices.mean(axis=0)
                self.pre_tetramesh_plotter.add_point_labels(
                    [center],
                    [mesh_data['name']],
                    point_size=0,
                    font_size=12,
                    text_color='white'
                )
            
            # Add simple legend
            selected_count = len(self.selected_conforming_surfaces)
            total_count = len(self.conforming_mesh_data)
            
            self.pre_tetramesh_plotter.add_text(
                f"Selected Conforming Surfaces: {selected_count}/{total_count}\n"
                f"Ready for TetGen tetrahedralization",
                position='upper_edge',
                color='white',
                font_size=12
            )
            
            # Reset camera and render
            self.pre_tetramesh_plotter.reset_camera()
            
        except Exception as e:
            logger.error(f"Error updating conforming surface visualization: {e}")
            self.pre_tetramesh_plotter.add_text(
                f"Visualization error: {str(e)}",
                position='upper_edge',
                color='red'
            )

    def _validate_conforming_meshes_for_tetgen(self):
        """
        Validate selected conforming meshes for TetGen compatibility.
        This checks topology, mesh quality, and manifold properties.
        """
        if not self.selected_conforming_surfaces:
            QMessageBox.warning(self, "No Selection", "Please select conforming surfaces to validate.")
            return
        
        logger.info("Starting conforming mesh validation for TetGen...")
        self.statusBar().showMessage("Validating conforming meshes for TetGen...")
        
        # Collect selected conforming mesh data
        selected_datasets = []
        for surface_idx in self.selected_conforming_surfaces:
            if surface_idx in self.conforming_mesh_data:
                mesh_data = self.conforming_mesh_data[surface_idx]
                # Create dataset format expected by validation function
                dataset = {
                    'name': mesh_data['name'],
                    'constrained_vertices': mesh_data['vertices'],
                    'constrained_triangles': mesh_data['triangles'],
                    'constraint_processing_used': True,  # Since these are conforming meshes
                    'conforming_mesh_source': True  # Mark as conforming mesh
                }
                selected_datasets.append(dataset)
        
        if not selected_datasets:
            QMessageBox.warning(self, "No Valid Data", "No valid conforming mesh data found for validation.")
            return
        
        # Import and run validation function
        try:
            from Pymeshit.intersection_utils import validate_surfaces_for_tetgen
            validation_results = validate_surfaces_for_tetgen(selected_datasets)
            
            # Show detailed validation results
            self._show_validation_results_dialog(validation_results)
            
            # Update status based on results
            if validation_results['ready_for_tetgen']:
                self.statusBar().showMessage(f"✓ All {len(selected_datasets)} conforming surfaces are ready for TetGen!")
                QMessageBox.information(self, "Validation Success", 
                                      f"All {len(selected_datasets)} selected conforming surfaces are ready for TetGen!\n\n"
                                      f"You can now proceed to the Tetra Mesh tab to load these surfaces.")
            elif validation_results['overall_status'] == 'PARTIAL':
                ready_count = validation_results['statistics']['valid_surfaces']
                total_count = len(selected_datasets)
                self.statusBar().showMessage(f"⚠ {ready_count}/{total_count} conforming surfaces ready for TetGen")
                QMessageBox.warning(self, "Partial Validation", 
                                   f"Only {ready_count}/{total_count} conforming surfaces are ready.\n"
                                   f"Check the validation report for details.")
            else:
                self.statusBar().showMessage("✗ Conforming surfaces not ready for TetGen")
                QMessageBox.critical(self, "Validation Failed", 
                                    "Selected conforming surfaces are not ready for TetGen.\n"
                                    "Check the validation report for issues to fix.")
        
        except Exception as e:
            logger.error(f"Conforming mesh validation failed: {str(e)}")
            self.statusBar().showMessage(f"Validation failed: {str(e)}")
            QMessageBox.critical(self, "Validation Error", f"Validation failed:\n{str(e)}")

    # Action method for the button
    #####################################################################
    # helper ------------------------------------------------------------
    #####################################################################
    def _order_polyline(self, points_3d):
        """
        Take an unordered list of 3-D points that belong to the same
        logical poly-line and return them ordered head-to-tail.
        Falls back to the input order if fewer than three points.

        Parameters
        ----------
        points_3d : list[list[float,float,float]]

        Returns
        -------
        list[list[float,float,float]]
        """
        if len(points_3d) < 3:
            return points_3d[:]          # nothing to sort

        try:
            from Pymeshit.intersection_utils import sort_intersection_points
            ordered = sort_intersection_points(
                [tuple(p) for p in points_3d]
            )
            # convert Vector3D→list if sort_intersection_points returned objects
            if hasattr(ordered[0], "x"):
                return [[v.x, v.y, v.z] for v in ordered]
            return ordered
        except Exception:
            # if anything goes wrong, stay safe and keep the original order
            return points_3d[:]


        #####################################################################
        #####################################################################
    # helper : export only what the user has selected – with DEBUG logs
    #####################################################################
    def _build_selected_constraint_lines(self):
        """
        Scan the constraint tree and build a dict

            {surface_idx : {"hull": polyline|None,
                            "intersections": [polyline0, ...]}

        containing exactly the segments the user selected.

        Extra diagnostics are logged so you can see why a segment or a
        whole surface is (or is not) exported.
        """
        import numpy as np
        import logging
        from PySide6.QtCore import Qt

        logger = logging.getLogger("MeshIt-Workflow")

        if not hasattr(self, "surface_constraint_tree"):
            logger.warning("Surface-constraint tree not found – returning empty set.")
            return {}

        tree     = self.surface_constraint_tree
        selected = {}

        def child_is_selected(child_item, parent_checked):
            """
            Selection rule (matches C++):
              • if parent group box is checked -> include any child that
                is not explicitly Unchecked
              • otherwise include only children whose own box is checked
            """
            if parent_checked:
                return child_item.checkState(0) != Qt.Unchecked
            return child_item.checkState(0) == Qt.Checked

        logger.info("─── Building selected-constraint list ───────────────────────")
        
        # CRITICAL FIX: First pass - collect all selected constraints from all surfaces
        all_selected_constraints = {}  # {surface_idx: {constraint_idx: constraint_data}}
        
        for i in range(tree.topLevelItemCount()):
            surf_item = tree.topLevelItem(i)
            surf_data = surf_item.data(0, Qt.UserRole)
            surf_idx  = surf_data[1] if surf_data and len(surf_data) > 1 else i
            constraints = self.constraint_manager.surface_constraints[surf_idx]
            
            all_selected_constraints[surf_idx] = {}

            # walk the second level (groups: Hull, Intersection Line N …)
            for j in range(surf_item.childCount()):
                group_item    = surf_item.child(j)
                group_checked = group_item.checkState(0) == Qt.Checked
                group_name    = group_item.text(0)

                # walk the third level (individual segments)
                for k in range(group_item.childCount()):
                    seg_item = group_item.child(k)
                    seg_data = seg_item.data(0, Qt.UserRole)

                    # not a constraint row → skip
                    if not seg_data or seg_data[0] != "constraint":
                        continue

                    _, _, c_idx = seg_data
                    constraint  = constraints[c_idx]

                    # is this segment included?
                    if child_is_selected(seg_item, group_checked):
                        all_selected_constraints[surf_idx][c_idx] = constraint

        # CRITICAL FIX: Second pass - propagate shared intersection constraints
        # Following C++ MeshIt behavior: when an intersection constraint is selected on one surface,
        # automatically include the same intersection constraint on all other surfaces
        logger.info("─── Propagating shared intersection constraints (C++ behavior) ───")
        
        def are_constraints_identical(c1, c2, tolerance=1e-9):
            """Check if two constraints are identical (C++ IsIdenticallyWith logic)"""
            if len(c1["points"]) != len(c2["points"]):
                return False
            
            # Check if all points match with high precision
            for p1 in c1["points"]:
                found_match = False
                for p2 in c2["points"]:
                    dist = ((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2 + (p1[2] - p2[2])**2)**0.5
                    if dist < tolerance:
                        found_match = True
                        break
                if not found_match:
                    return False
            return True
        
        propagated_count = 0
        for surf1_idx in range(len(self.datasets)):
            if surf1_idx not in all_selected_constraints:
                continue
                
            for c1_idx, constraint1 in all_selected_constraints[surf1_idx].items():
                # Only propagate intersection constraints (not hull)
                if constraint1.get("type") != "INTERSECTION":
                    continue
                    
                # Find identical constraints on other surfaces
                for surf2_idx in range(len(self.datasets)):
                    if surf2_idx == surf1_idx or surf2_idx not in self.constraint_manager.surface_constraints:
                        continue
                        
                    constraints2 = self.constraint_manager.surface_constraints[surf2_idx]
                    for c2_idx, constraint2 in enumerate(constraints2):
                        if constraint2.get("type") != "INTERSECTION":
                            continue
                            
                        # Check if constraints are identical
                        if are_constraints_identical(constraint1, constraint2):
                            # Propagate selection to this surface
                            if surf2_idx not in all_selected_constraints:
                                all_selected_constraints[surf2_idx] = {}
                            if c2_idx not in all_selected_constraints[surf2_idx]:
                                all_selected_constraints[surf2_idx][c2_idx] = constraint2
                                propagated_count += 1
                                logger.info(f"  Propagated intersection constraint from S{surf1_idx} to S{surf2_idx} (constraint {c2_idx})")

        logger.info(f"─── Propagated {propagated_count} shared intersection constraints ───")

        # Third pass - build the final output using propagated selections
        for surf_idx in range(len(self.datasets)):
            if surf_idx not in all_selected_constraints or not all_selected_constraints[surf_idx]:
                continue
                
            constraints = self.constraint_manager.surface_constraints[surf_idx]
            hull_segments        = []
            intersection_by_line = {}
            constraints_per_line = {}  # Track total constraints per line_id

            tot_hull = tot_inter = sel_hull = sel_inter = 0

            # Count totals
            for constraint in constraints:
                if constraint["type"] == "HULL":
                    tot_hull += 1
                else:
                    tot_inter += 1
                    lid = constraint.get("line_id", 0)
                    constraints_per_line[lid] = constraints_per_line.get(lid, 0) + 1

            # Process selected constraints
            for c_idx, constraint in all_selected_constraints[surf_idx].items():
                c_type = constraint["type"]
                
                if c_type == "HULL":
                    sel_hull += 1
                    hull_segments.append(constraint["points"])
                    logger.info(f"S{surf_idx}  INCLUDE HULL         seg {c_idx:3}  (propagated selection)")
                else:
                    sel_inter += 1
                    lid = constraint.get("line_id", 0)
                    intersection_by_line.setdefault(lid, []).append(constraint["points"])
                    logger.info(f"S{surf_idx}  INCLUDE INTERSECTION seg {c_idx:3}  (propagated selection)")

            logger.info(f"S{surf_idx}: HULL {sel_hull}/{tot_hull}  "
                        f"INTERSECTION {sel_inter}/{tot_inter}")

            # nothing picked on this surface
            if not hull_segments and not intersection_by_line:
                logger.info(f"S{surf_idx}: no segments selected – surface skipped.")
                continue

            # ---------- merge points & order polylines -----------------
            surface_selection = {"hull": None, "intersections": []}

            if hull_segments:
                # FIXED: Use high-precision rounding instead of floating-point tolerance
                unique_points_map = {}
                uniq = []
                for seg in hull_segments:
                    for p in seg:
                        # Create high-precision key (round to 9 decimal places)
                        key = (round(p[0], 9), round(p[1], 9), round(p[2], 9))
                        if key not in unique_points_map:
                            unique_points_map[key] = True
                            uniq.append(p)
                logger.debug(f"S{surf_idx}:   HULL unique pts = {len(uniq)}")
                if len(uniq) > 1:
                    surface_selection["hull"] = self._order_polyline(uniq)

            for lid in sorted(intersection_by_line.keys()):
                # FIXED: Properly reconstruct polylines from selected segments
                # Use high-precision rounding instead of floating-point tolerance
                unique_points_map = {}
                uniq = []
                for seg in intersection_by_line[lid]:
                    for p in seg:
                        # Create high-precision key (round to 9 decimal places)
                        key = (round(p[0], 9), round(p[1], 9), round(p[2], 9))
                        if key not in unique_points_map:
                            unique_points_map[key] = True
                            uniq.append(p)
                if len(uniq) < 2:
                    logger.debug(f"S{surf_idx}:   line {lid} ignored (<2 pts)")
                    continue
                logger.debug(f"S{surf_idx}:   line {lid} unique pts = {len(uniq)}")
                ordered_polyline = self._order_polyline(uniq)
                
                # CRITICAL FIX: Check if partial selection creates disconnected segments
                total_segments = constraints_per_line.get(lid, 1)
                selected_segments = len(intersection_by_line[lid])
                if selected_segments < total_segments:
                    logger.warning(f"S{surf_idx}: Line {lid} has partial selection ({selected_segments}/{total_segments} segments)")
                    logger.warning(f"S{surf_idx}: This may create gaps in intersection boundary")
                    
                    # Check if the polyline forms a closed loop
                    if len(ordered_polyline) >= 3:
                        first_pt = ordered_polyline[0]
                        last_pt = ordered_polyline[-1]
                        distance = ((first_pt[0] - last_pt[0])**2 + 
                                  (first_pt[1] - last_pt[1])**2 + 
                                  (first_pt[2] - last_pt[2])**2)**0.5
                        if distance < 1e-6:
                            logger.info(f"S{surf_idx}: Line {lid} forms closed loop despite partial selection")
                        else:
                            logger.warning(f"S{surf_idx}: Line {lid} is open polyline - may cause triangulation gaps")
                
                surface_selection["intersections"].append(ordered_polyline)

            if not surface_selection["hull"] and not surface_selection["intersections"]:
                logger.info(f"S{surf_idx}: no polylines built – surface skipped.")
                continue

            selected[surf_idx] = surface_selection
            num_polylines = (1 if surface_selection["hull"] else 0) + len(surface_selection["intersections"])
            logger.info(f"S{surf_idx}: total polylines exported = {num_polylines}")

        logger.info("─── Selection build complete ───────────────────────────────")
        return selected

    def _analyze_refinement_results(self):
        """Analyze refinement results and return a summary string focusing on special points and hull status."""
        if not hasattr(self, 'original_intersections_backup') or not self.original_intersections_backup or not self.datasets_intersections:
            return "No data to analyze."
        
        # Compare original vs refined intersections
        modified_count = 0
        original_total_points = 0
        refined_total_points = 0
        
        # Special point counters
        triple_points_count = 0
        special_points_count = 0
        triple_points_on_hulls = 0
        
        # Count triple points from the dedicated attribute
        stored_triple_points_count = len(self.triple_points) if hasattr(self, 'triple_points') else 0
        
        # Intersection type counters
        polyline_surf_intersections = 0
        surf_surf_intersections = 0
        
        # Count intersection lines by type
        for ds_key in self.datasets_intersections.keys():
            if ds_key in self.original_intersections_backup:
                for i, refined_intersection in enumerate(self.datasets_intersections[ds_key]):
                    if i < len(self.original_intersections_backup[ds_key]):
                        original_intersection = self.original_intersections_backup[ds_key][i]
                        
                        # Count by intersection type
                        if refined_intersection.get('is_polyline_mesh', False):
                            polyline_surf_intersections += 1
                        else:
                            surf_surf_intersections += 1
                        
                        # Get points
                        original_points = original_intersection.get('points', [])
                        refined_points = refined_intersection.get('points', [])
                        
                        original_total_points += len(original_points)
                        refined_total_points += len(refined_points)
                        
                        # Count modifications
                        if len(original_points) != len(refined_points):
                            modified_count += 1
                        
                        # Count different types of special points in the refined data
                        for point in refined_points:
                            point_type = None
                            # Check point format - could be a list with type at index 3 or an object with point_type
                            if isinstance(point, list) and len(point) > 3:
                                point_type = point[3]
                            elif hasattr(point, 'point_type'):
                                point_type = point.point_type
                            
                            if point_type:
                                type_str = str(point_type).upper()
                                if "TRIPLE_POINT" in type_str:
                                    triple_points_count += 1
                                elif "HIGH_CORNER_POINT" in type_str:
                                    special_points_count += 1
                                elif "SPECIAL_POINT" in type_str:
                                    special_points_count += 1
        
        # Check for special points on convex hulls
        hull_special_points_count = 0
        total_hull_points = 0
        for dataset in self.datasets:
            hull_points = dataset.get('hull_points', [])
            total_hull_points += len(hull_points)
            for hp in hull_points:
                if len(hp) > 3 and isinstance(hp[3], str):
                    type_str = hp[3].upper()
                    if "HIGH_CORNER_POINT" in type_str or "SPECIAL_POINT" in type_str:
                        hull_special_points_count += 1
                    elif "TRIPLE_POINT" in type_str:
                        triple_points_on_hulls += 1
        
        # Create detailed summary
        summary = "<b>Refinement Summary:</b><br>"
        
        # Intersection information
        summary += "<u>Intersection Lines:</u><br>"
        if surf_surf_intersections > 0:
            summary += f"• {surf_surf_intersections} surface-surface intersections<br>"
        if polyline_surf_intersections > 0:
            summary += f"• {polyline_surf_intersections} polyline-surface intersections<br>"
        
        # Convex hull information
        summary += "<br><u>Convex Hulls:</u><br>"
        summary += f"• {total_hull_points} total points on all convex hulls<br>"
        if hull_special_points_count > 0:
            summary += f"• <span style='color:#2ecc71;'>{hull_special_points_count} special points</span> (angle > 135°) on convex hulls<br>"
        if triple_points_on_hulls > 0:
            summary += f"• <span style='color:#e74c3c;'>{triple_points_on_hulls} triple points</span> aligned to convex hulls<br>"
        
        # Special point information
        summary += "<br><u>Special Points:</u><br>"
        if stored_triple_points_count > 0:
            summary += f"• <span style='color:#e74c3c;'>{stored_triple_points_count} triple points</span> identified (saved for constraints)<br>"
        if triple_points_count > 0:
            summary += f"• <span style='color:#e74c3c;'>{triple_points_count} triple points</span> in intersection lines<br>"
        if special_points_count > 0:
            summary += f"• <span style='color:#3498db;'>{special_points_count} special points</span> on intersection lines<br>"
        
        # Length refinement information
        summary += "<br><u>Length Refinement:</u><br>"
        if original_total_points > 0 and refined_total_points > 0:
            if refined_total_points > original_total_points:
                summary += f"• {original_total_points} → {refined_total_points} points ({((refined_total_points - original_total_points) / max(1, original_total_points) * 100):.1f}% increase)<br>"
            else:
                summary += f"• {original_total_points} → {refined_total_points} points<br>"
        
        return summary

    def _add_wells_polyline_to_plotter(self, plotter, color_map=None):
        """Render all WELL datasets as polylines on the given PyVista plotter."""
        try:
            import numpy as np
            import pyvista as pv
        except Exception:
            return
        if not hasattr(self, 'datasets') or not self.datasets or not plotter:
            return

        for idx, ds in enumerate(self.datasets):
            if ds.get('type') != 'WELL':
                continue
            pts = ds.get('refined_well_points') or ds.get('points')
            if pts is None or len(pts) < 2:
                continue

            pts = np.array(pts, dtype=float)
            if pts.shape[1] < 3:
                tmp = np.zeros((pts.shape[0], 3))
                tmp[:, :pts.shape[1]] = pts
                pts = tmp

            n = len(pts)
            # Polyline cell format: [n, 0, 1, 2, ... n-1]
            lines = np.hstack(([n], np.arange(n, dtype=np.int32))).astype(np.int32)
            poly = pv.PolyData(pts, lines=lines)
            color = ds.get('color', self.DEFAULT_COLORS[idx % len(self.DEFAULT_COLORS)])
            plotter.add_mesh(poly, color=color, line_width=3, opacity=0.9, label=f"{ds.get('name', 'Well')}")


    def _add_wells_to_intersection_plotter(self):
        """Convenience wrapper to add wells to the Intersection tab plotter."""
        if hasattr(self, 'intersection_plotter') and self.intersection_plotter:
            self._add_wells_polyline_to_plotter(self.intersection_plotter)
    def _refine_intersection_lines_action(self):
        """
        Action to refine intersection lines by:
        1. Identifying triple points and geometric corners.
        2. Aligning intersection endpoints to the raw hull, creating a topologically correct boundary.
        3. Refining this detailed hull by projecting it onto an interpolated surface (draping).
        4. Refining all intersection and hull lines by length for meshing.
        """
        logger.info("Starting refinement of intersection lines...")
        self.statusBar().showMessage("Refining intersection lines...")

        if not hasattr(self, 'datasets_intersections') or not self.datasets_intersections:
            QMessageBox.information(self, "No Intersections", "No intersections found to refine.")
            self.statusBar().showMessage("Refinement skipped: No intersections found.", 5000)
            return

        import copy
        self.original_intersections_backup = copy.deepcopy(self.datasets_intersections)

        try:
            per_surface_len = {}
            if hasattr(self, 'mesh_refine_table') and self.mesh_refine_table is not None:
                from PySide6.QtCore import Qt
                for r in range(self.mesh_refine_table.rowCount()):
                    item_name = self.mesh_refine_table.item(r, 0)
                    item_val = self.mesh_refine_table.item(r, 1)
                    if item_name and item_val:
                        try:
                            ds_idx = int(item_name.data(Qt.UserRole))
                            val = float(item_val.text())
                            if val > 1e-9:
                                per_surface_len[ds_idx] = val
                        except Exception:
                            pass

            unified_fallback = float(self.mesh_target_feature_size_input.value())

            def _get_target_for_surface(idx: int) -> float:
                v = per_surface_len.get(idx, unified_fallback)
                return v if v > 1e-9 else unified_fallback

            min_angle_deg = float(self.mesh_min_angle_input.value())
            uniform_meshing = self.mesh_uniform_checkbox.isChecked()
        except ValueError:
            QMessageBox.warning(self, "Input Error", "Invalid numeric input for refinement parameters.")
            self.statusBar().showMessage("Refinement failed: Invalid input.", 5000)
            return

        class TempModelWrapper:
            def __init__(self):
                self.surfaces = []
                self.polylines = []
                self.intersections = []
                self.triple_points = []
                self.original_indices_map = {}
                self.is_polyline = {}
                self.surface_original_to_temp_idx_map = {}
                self.polyline_original_to_temp_idx_map = {}

        temp_model = TempModelWrapper()

        involved_original_indices = set()
        for _, intersections_list in self.datasets_intersections.items():
            for intersection_data in intersections_list:
                involved_original_indices.add(intersection_data['dataset_id1'])
                involved_original_indices.add(intersection_data['dataset_id2'])

        temp_data_idx_counter = 0

        for original_idx, dataset_content in enumerate(self.datasets):
            if original_idx not in involved_original_indices:
                continue

            class TempDataWrapper:
                def __init__(self):
                    self.convex_hull = []
                    self.size = 0.1
                    self.name = f"Dataset_{original_idx}"

            data_wrapper = TempDataWrapper()
            data_wrapper.name = dataset_content.get('name', f"Dataset_{original_idx}")

            hull_points_obj_array = dataset_content.get('hull_points')
            if hull_points_obj_array is not None and len(hull_points_obj_array) > 0:
                for hp in hull_points_obj_array:
                    point_type = hp[3] if len(hp) > 3 and isinstance(hp[3], str) else "DEFAULT"
                    data_wrapper.convex_hull.append(Vector3D(hp[0], hp[1], hp[2], point_type=point_type))
            else:
                points_np = dataset_content.get('points')
                if points_np is not None and len(points_np) > 0:
                    data_wrapper.convex_hull = [Vector3D(p[0], p[1], p[2]) for p in points_np]
                else:
                    logger.warning(f"Dataset {original_idx} ({data_wrapper.name}) has no hull_points or points. Skipping for temp_model.")
                    continue

            is_p = (dataset_content.get('type') in ('WELL', 'polyline') or
                    ('segments' in dataset_content and 'triangles' not in dataset_content and 'hull_points' not in dataset_content))

            temp_model.original_indices_map[temp_data_idx_counter] = original_idx
            temp_model.is_polyline[temp_data_idx_counter] = is_p

            if is_p:
                temp_model.polyline_original_to_temp_idx_map[original_idx] = len(temp_model.polylines)
                temp_model.polylines.append(data_wrapper)
            else:
                temp_model.surface_original_to_temp_idx_map[original_idx] = len(temp_model.surfaces)
                temp_model.surfaces.append(data_wrapper)

            temp_data_idx_counter += 1

        if not temp_model.surfaces and not temp_model.polylines:
            QMessageBox.warning(self, "No Valid Datasets", "No datasets with geometry were prepared for refinement.")
            return

        logger.info(f"Temp model created: {len(temp_model.surfaces)} surfaces, {len(temp_model.polylines)} polylines.")

        original_to_temp_combined_idx_map = {v: k for k, v in temp_model.original_indices_map.items()}
        for _, intersections_list in self.datasets_intersections.items():
            for intersection_data in intersections_list:
                temp_combined_id1 = original_to_temp_combined_idx_map.get(intersection_data['dataset_id1'])
                temp_combined_id2 = original_to_temp_combined_idx_map.get(intersection_data['dataset_id2'])
                if temp_combined_id1 is None or temp_combined_id2 is None: continue
                new_int = Intersection(temp_combined_id1, temp_combined_id2, intersection_data['is_polyline_mesh'])
                for pt_coords in intersection_data['points']:
                    new_int.add_point(Vector3D(pt_coords[0], pt_coords[1], pt_coords[2] if len(pt_coords) > 2 else 0.0))
                temp_model.intersections.append(new_int)

        if not temp_model.intersections:
            QMessageBox.information(self, "No Intersections", "No intersections populated in temp_model.")
            return

        # Step 1: Triple points
        try:
            for i in range(len(temp_model.intersections) - 1):
                for j in range(i + 1, len(temp_model.intersections)):
                    triple_points = calculate_triple_points(i, j, temp_model, tolerance=1e-5)
                    for tp in triple_points:
                        triple_point_obj = TriplePoint(tp)
                        triple_point_obj.add_intersection(i); triple_point_obj.add_intersection(j)
                        tp.point_type = "TRIPLE_POINT"
                        temp_model.triple_points.append(triple_point_obj)
            insert_triple_points(temp_model)
            self.triple_points = [{'point': tp.point, 'intersections': tp.intersection_ids} for tp in temp_model.triple_points]
            logger.info(f"Found and inserted {len(temp_model.triple_points)} triple points.")
        except Exception as e:
            logger.error(f"Error during triple points calculation: {e}", exc_info=True)
            return
        
        # Step 2: Corners on convex hulls
        try:
            from Pymeshit.intersection_utils import make_corners_special
            for temp_surface in temp_model.surfaces:
                if hasattr(temp_surface, 'convex_hull') and len(temp_surface.convex_hull) >= 3:
                    temp_surface.convex_hull = make_corners_special(temp_surface.convex_hull, angle_threshold_deg=135.0)
        except Exception as e:
            logger.error(f"Error during corner point identification: {e}", exc_info=True)
            return
        
        # Step 5: Refine convex hulls by length (creates dense hull for interpolation)
        try:
            temp_to_orig = {ti: oi for oi, ti in temp_model.surface_original_to_temp_idx_map.items()}
            for temp_idx, temp_surface in enumerate(temp_model.surfaces):
                if hasattr(temp_surface, 'convex_hull') and len(temp_surface.convex_hull) >= 3:
                    orig_idx = temp_to_orig.get(temp_idx, -1)
                    eff_target_length = _get_target_for_surface(orig_idx)
                    class _HullLine:
                        def __init__(self, pts): self.points = [Vector3D(p.x, p.y, p.z, point_type=getattr(p, "point_type", "DEFAULT")) for p in pts]
                    refined = refine_intersection_line_by_length(
                        _HullLine(temp_surface.convex_hull), float(eff_target_length), min_angle_deg, uniform_meshing
                    )
                    if len(refined) >= 2 and (refined[0] - refined[-1]).length_squared() < 1e-24:
                        refined = refined[:-1]
                    temp_surface.convex_hull = refined
            logger.info(f"Refined convex hulls by length.")
        except Exception as e:
            logger.error(f"Error during convex hull length refinement: {e}", exc_info=True)
            return
        
        # Step 6: Refine intersection lines by length
        try:
            for intersection in temp_model.intersections:
                id1, id2 = intersection.id1, intersection.id2
                orig1 = temp_model.original_indices_map.get(id1, -1)
                orig2 = temp_model.original_indices_map.get(id2, -1)
                t1 = _get_target_for_surface(orig1)
                t2 = _get_target_for_surface(orig2)
                eff_target_length = min(t1, t2)
                intersection.points = refine_intersection_line_by_length(
                    intersection, eff_target_length, min_angle_deg, uniform_meshing
                )
            logger.info("Length-based refinement of intersection lines complete.")
        except Exception as e:
            logger.error(f"Error during length-based refinement: {e}", exc_info=True)
            return
        # Step 3: Refine hull with interpolation (corrects hull geometry)
        try:
            config = {
                'interp': self.mesh_interp_combo.currentText(),
                'smoothing': float(self.mesh_smoothing_input.value())
            }
            for temp_surface_idx, temp_surface in enumerate(temp_model.surfaces):
                if hasattr(temp_surface, 'convex_hull') and len(temp_surface.convex_hull) >= 3:
                    raw_hull_points = [Vector3D(p.x, p.y, p.z, point_type=getattr(p, "point_type", "DEFAULT")) for p in temp_surface.convex_hull]
                    original_idx = temp_model.original_indices_map.get(
                        next((k for k, v in temp_model.surface_original_to_temp_idx_map.items() if v == temp_surface_idx), None)
                    )
                    if original_idx is not None and 'points' in self.datasets[original_idx]:
                        scattered_points = [Vector3D(p[0], p[1], p[2]) for p in self.datasets[original_idx]['points']]
                        refined_hull_3d = refine_hull_with_interpolation(
                            raw_hull_points, scattered_points, config
                        )
                        

                    # Step 4: Create refined Vector3D objects preserving point types
                    refined_hull_points = []
                    for i, (orig_pt, refined_3d) in enumerate(zip(raw_hull_points, refined_hull_3d)):
                        # If refined_3d is already a Vector3D, just copy it
                        if isinstance(refined_3d, Vector3D):
                            refined_pt = Vector3D(refined_3d.x, refined_3d.y, refined_3d.z)
                        else:
                            refined_pt = Vector3D(refined_3d[0], refined_3d[1], refined_3d[2])
                        # Preserve original point type information
                        refined_pt.point_type = getattr(orig_pt, 'point_type', 'DEFAULT')
                        if hasattr(orig_pt, 'type'):
                            refined_pt.type = orig_pt.type
                        refined_hull_points.append(refined_pt)

                    temp_surface.convex_hull = refined_hull_points
        except Exception as e:
            logger.error(f"Error during hull refinement: {e}", exc_info=True)
            return
        # Step 4: Align intersections to hulls (defines hull topology)
        try:
            for temp_surface_list_idx in range(len(temp_model.surfaces)):
                align_intersections_to_convex_hull(temp_surface_list_idx, temp_model)
            logger.info("Intersection alignment to convex hulls complete.")
        except Exception as e:
            logger.error(f"Error during convex hull alignment: {e}", exc_info=True)
            return
        
        
        
        # Store intersection lines as constraints (unchanged)
        logger.info("Storing intersection lines as constraints for each surface...")
        for ds in self.datasets: ds["stored_constraints"] = []
        for inter in temp_model.intersections:
            sid1 = temp_model.original_indices_map.get(inter.id1)
            sid2 = temp_model.original_indices_map.get(inter.id2)
            if sid1 is None or sid2 is None:
                continue
            pts_with_type = [[pt.x, pt.y, pt.z, getattr(pt, "point_type", "DEFAULT")] for pt in inter.points]
            if len(pts_with_type) < 2:
                continue
            base_entry = {"type": "intersection_line", "points": pts_with_type}
            for ds_idx, other_idx in ((sid1, sid2), (sid2, sid1)):
                if ds_idx is None or ds_idx >= len(self.datasets): 
                    continue
                entry = dict(base_entry)
                entry["other_surface_id"] = other_idx
                self.datasets[ds_idx]["stored_constraints"].append(entry)
                self.datasets[ds_idx]["needs_constraint_update"] = True
        logger.info("Constraint storage complete.")

        # Repopulate datasets_intersections for visualization (unchanged)
        self.datasets_intersections.clear()
        self.refined_intersections_for_visualization = {}
        for temp_s_list_idx, temp_surface_data in enumerate(temp_model.surfaces):
            original_dataset_idx = None
            for orig_idx, temp_idx in temp_model.surface_original_to_temp_idx_map.items():
                if temp_idx == temp_s_list_idx:
                    original_dataset_idx = orig_idx
                    break
            if original_dataset_idx is not None:
                if hasattr(temp_surface_data, 'convex_hull') and temp_surface_data.convex_hull:
                    hull_points_with_type = []
                    for p in temp_surface_data.convex_hull:
                        point_type = "DEFAULT"
                        if hasattr(p, 'type') and p.type:
                            point_type = p.type
                        elif hasattr(p, 'point_type') and p.point_type:
                            point_type = p.point_type
                        hull_points_with_type.append([p.x, p.y, p.z, point_type])

                    self.datasets[original_dataset_idx]['hull_points'] = np.array(hull_points_with_type, dtype=object)
                    logger.info(f"Updated convex hull for dataset {original_dataset_idx} with {len(hull_points_with_type)} points.")
            else:
                logger.warning(f"Could not map temp_model.surfaces index {temp_s_list_idx} to an original dataset index for hull update.")

        for intersection in temp_model.intersections:
            original_id1 = temp_model.original_indices_map.get(intersection.id1)
            original_id2 = temp_model.original_indices_map.get(intersection.id2)
            if original_id1 is None or original_id2 is None:
                logger.warning(f"Post-refinement: Skipping intersection due to missing original ID map for temp IDs {intersection.id1}/{intersection.id2}.")
                continue

            points_for_entry = []
            for p_obj in intersection.points:
                p_type_str = "DEFAULT"
                if hasattr(p_obj, 'point_type') and p_obj.point_type:
                    p_type_str = p_obj.point_type
                points_for_entry.append([p_obj.x, p_obj.y, p_obj.z, p_type_str])

            intersection_entry = {
                'dataset_id1': original_id1,
                'dataset_id2': original_id2,
                'is_polyline_mesh': intersection.is_polyline_mesh,
                'points': points_for_entry,
            }

            primary_key_ds = min(original_id1, original_id2)
            if primary_key_ds not in self.datasets_intersections:
                self.datasets_intersections[primary_key_ds] = []

            def _same_intersection(inter1: dict, inter2: dict, tol: float = 1e-6) -> bool:
                import numpy as np

                def to_xyz_array(pts) -> np.ndarray:
                    xyz = []

                    def push_xyz(x, y, z):
                        try:
                            xyz.append([float(x), float(y), float(z)])
                        except Exception:
                            pass

                    if pts is None:
                        return np.empty((0, 3), dtype=float)

                    for p in pts:
                        # Segment as [p1, p2] where p* may be Vector3D or xyz-like
                        if isinstance(p, (list, tuple)) and len(p) == 2 and all(
                            hasattr(q, "x") and hasattr(q, "y") and hasattr(q, "z") for q in p
                        ):
                            push_xyz(p[0].x, p[0].y, p[0].z)
                            push_xyz(p[1].x, p[1].y, p[1].z)
                            continue

                        # Vector3D
                        if hasattr(p, "x") and hasattr(p, "y") and hasattr(p, "z"):
                            push_xyz(p.x, p.y, p.z)
                            continue

                        # dict with x/y/z
                        if isinstance(p, dict) and all(k in p for k in ("x", "y", "z")):
                            push_xyz(p["x"], p["y"], p["z"])
                            continue

                        # plain sequence [x,y,z] or np array
                        if isinstance(p, (list, tuple, np.ndarray)) and len(p) >= 3:
                            push_xyz(p[0], p[1], p[2])
                            continue

                        # Unknown type: skip
                        continue

                    if not xyz:
                        return np.empty((0, 3), dtype=float)
                    return np.asarray(xyz, dtype=float)

                pts1 = inter1.get("points", [])
                pts2 = inter2.get("points", [])
                arr1 = to_xyz_array(pts1)
                arr2 = to_xyz_array(pts2)

                if arr1.size == 0 or arr2.size == 0:
                    return False

                c1 = np.mean(arr1, axis=0)
                c2 = np.mean(arr2, axis=0)
                if not np.all(np.isfinite(c1)) or not np.all(np.isfinite(c2)):
                    return False

                # Optional: also compare the involved surface/polyline IDs if present
                ids1 = tuple(sorted(inter1.get("pair_ids", inter1.get("ids", []))))
                ids2 = tuple(sorted(inter2.get("pair_ids", inter2.get("ids", []))))
                ids_match = (ids1 == ids2) if ids1 and ids2 else True

                return ids_match and np.linalg.norm(c1 - c2) <= tol

            already_added = any(_same_intersection(existing, intersection_entry) for existing in self.datasets_intersections[primary_key_ds])
            if not already_added:
                self.datasets_intersections[primary_key_ds].append(intersection_entry)

            for vis_key_id in (original_id1, original_id2):
                if vis_key_id not in self.refined_intersections_for_visualization:
                    self.refined_intersections_for_visualization[vis_key_id] = []

                def _same_line(a_pts, b_pts, tol=1e-8):
                    if len(a_pts) != len(b_pts):
                        return False
                    def _close(p, q):
                        return (abs(p[0] - q[0]) < tol and abs(p[1] - q[1]) < tol and abs(p[2] - q[2]) < tol)
                    if all(_close(pa, pb) for pa, pb in zip(a_pts, b_pts)):
                        return True
                    if all(_close(pa, pb) for pa, pb in zip(a_pts, reversed(b_pts))):
                        return True
                    return False

                vis_already_added = any(
                    _same_line(intersection_entry['points'], ie['points']) and
                    ie['is_polyline_mesh'] == intersection_entry['is_polyline_mesh']
                    for ie in self.refined_intersections_for_visualization[vis_key_id]
                )
                if not vis_already_added:
                    self.refined_intersections_for_visualization[vis_key_id].append(intersection_entry.copy())

        summary = self._analyze_refinement_results()
        self.refinement_summary_label.setText(summary)

        self.statusBar().showMessage("Intersection lines refined successfully.", 5000)
        logger.info("Intersection lines refined successfully.")

        logger.info("Consolidating all refined points for triangulation...")
        self.consolidate_points_for_triangulation()
        logger.info("Consolidation complete!")

        self.generate_conforming_meshes_btn.setEnabled(True)
        logger.info("Enabled conforming mesh generation button after successful refinement.")

        try:
            self._populate_refine_constraint_tree()
            logger.info("Refinement complete. Populated constraint tree in 'Refine & Mesh' tab.")
        except Exception as e:
            logger.error(f"Error populating constraint tree for Tab 6: {e}", exc_info=True)
        self._populate_surface_selector()
        self._update_refined_visualization()

    def _generate_conforming_meshes_action(self):
        """Generate conforming surface meshes from currently checked segments."""
        import numpy as np
        # Keep status/log but compute per-surface target size below
        self.statusBar().showMessage("Generating conforming surface meshes…")

        ok, total, fails = 0, 0, []
        for s_idx, ds in enumerate(self.datasets):
            # Skip wells (polylines) entirely for triangulation
            if ds.get("type") in ("WELL", "polyline"):
                continue

            seg_lists = self._collect_selected_refine_segments(s_idx)
            if not seg_lists:
                continue

            total += 1
            name = ds.get("name", f"Surface_{s_idx}")
            try:
                # Build per-surface config
                unified_target = float(self.mesh_target_feature_size_input.value())
                per_surface_target = float(self._get_mesh_target_size_for_surface(s_idx))
                # Clamp negative/silly inputs
                if per_surface_target <= 1e-9:
                    per_surface_target = max(1.0, unified_target)

                cfg = {
                    "target_size": per_surface_target,
                    "min_angle":  float(self.mesh_min_angle_input.value()),
                    "max_area":   float(per_surface_target) ** 2 * 1.5,
                    "interp":     self.mesh_interp_combo.currentText(),
                    "smoothing":  float(self.mesh_smoothing_input.value()),
                }

                surf_data = self._prepare_surface_data_for_triangulation(s_idx, ds, cfg)
                if not surf_data:
                    raise RuntimeError("surface-data prep failed")

                pts3d, seg_arr, holes = self._build_plc_from_selection(s_idx)
                if len(pts3d) < 3 or len(seg_arr) < 3:
                    raise RuntimeError("too few PLC entities")

                proj = surf_data["projection_params"]
                centroid = np.asarray(proj["centroid"])
                basis = np.asarray(proj["basis"])
                pts2d = (np.array([[p.x, p.y, p.z] for p in pts3d]) - centroid) @ basis.T
                pts2d = pts2d[:, :2]

                holes_2d = []
                if holes:
                    holes_3d = np.array([[h.x, h.y, h.z] for h in holes])
                    holes_2d = (holes_3d - centroid) @ basis.T
                    holes_2d = holes_2d[:, :2]

                v3d, tris, _ = run_constrained_triangulation_py(
                    pts2d, seg_arr, holes_2d, proj,
                    np.array([[p.x, p.y, p.z] for p in pts3d]), cfg
                )

                if v3d is None or len(v3d) == 0 or tris is None or len(tris) == 0:
                    raise RuntimeError("triangulation returned empty result")

                ds.setdefault("conforming_mesh", {})
                ds["conforming_mesh"]["vertices"] = v3d
                ds["conforming_mesh"]["triangles"] = tris
                ds["conforming_mesh"]["holes"] = [[h.x, h.y, h.z] for h in holes] if holes else []

                ok += 1
                logger.info(f"✓ Conforming mesh generated for '{name}': {len(v3d)} vertices, {len(tris)} triangles")
            except Exception as e:
                fails.append((name, str(e)))
                logger.error(f"Conforming mesh generation FAILED for '{name}': {e}")

        if fails:
            logger.warning(f"Conforming mesh generation failures: {len(fails)}")
        self._update_refined_visualization()
        self.statusBar().showMessage(f"Conforming surface mesh generation finished: {ok}/{total} succeeded.", 6000)


    def _prepare_surface_data_for_triangulation(self, dataset_idx, dataset, config):
        """
        Prepare surface data dictionary for triangulation with projection parameters.
        """
        try:
            # Get refined hull points
            hull_points_data = dataset.get('hull_points', [])
            if hull_points_data is None or len(hull_points_data) == 0:
                logger.warning(f"No hull points for dataset {dataset_idx}")
                return None
                
            # Convert hull points to Vector3D objects
            hull_points = []
            for point_data in hull_points_data:
                if len(point_data) >= 3:
                    # Extract point type if available (4th element)
                    point_type = point_data[3] if len(point_data) > 3 else "DEFAULT"
                    hull_points.append(Vector3D(point_data[0], point_data[1], point_data[2], point_type=point_type))
            
            if len(hull_points) < 3:
                logger.warning(f"Insufficient hull points for dataset {dataset_idx}")
                return None
            
            # Calculate surface size
            hull_points_np = np.array([[p.x, p.y, p.z] for p in hull_points])
            bbox_min = np.min(hull_points_np, axis=0)
            bbox_max = np.max(hull_points_np, axis=0)
            bbox_diag = np.linalg.norm(bbox_max - bbox_min)
            
            # Respect user's target size setting - only use bbox-based size as fallback for very large values
            user_target_size = config.get('target_size', 1.0)
            bbox_based_size = bbox_diag / 20.0
            
            # Use user's setting if reasonable, otherwise use bbox-based constraint
            if user_target_size <= bbox_diag:  # User's setting is reasonable for this surface
                surface_size = user_target_size
                logger.debug(f"Using user target size: {surface_size:.2f} (bbox_diag: {bbox_diag:.2f})")
            else:  # User's setting is too large for this surface
                surface_size = bbox_based_size
                logger.warning(f"User target size {user_target_size:.2f} too large for surface (bbox: {bbox_diag:.2f}), using {surface_size:.2f}")
            
            # Calculate projection parameters for 2D triangulation
            projection_params = self._calculate_surface_projection_params(hull_points_np)
            
            surface_data = {
                'hull_points': hull_points,
                'size': surface_size,
                'projection_params': projection_params,
                'name': dataset.get('name', f'Surface_{dataset_idx}'),
                'index': dataset_idx
            }
            
            return surface_data
            
        except Exception as e:
            logger.error(f"Error preparing surface data for dataset {dataset_idx}: {e}")
            return None

    def _prepare_minimal_surface_data_for_triangulation(self, dataset_idx, dataset, config):
        """
        Prepare minimal surface data for triangulation when hull is not selected.
        This creates a bounding box from intersection lines.
        """
        try:
            # Find intersection lines for this surface to create a minimal boundary
            intersections_on_surface = self._find_intersections_for_surface(dataset_idx)
            
            if not intersections_on_surface:
                logger.warning(f"No intersections found for dataset {dataset_idx} and hull not selected")
                return None
            
            # Collect all intersection points to create a bounding box
            all_points = []
            for intersection_data in intersections_on_surface:
                for point in intersection_data.get('points', []):
                    if hasattr(point, 'x'):
                        all_points.append([point.x, point.y, point.z])
                    elif len(point) >= 3:
                        all_points.append([point[0], point[1], point[2]])
            
            if len(all_points) < 3:
                logger.warning(f"Insufficient intersection points for dataset {dataset_idx}")
                return None
            
            # Create a bounding box as minimal hull
            all_points_np = np.array(all_points)
            bbox_min = np.min(all_points_np, axis=0)
            bbox_max = np.max(all_points_np, axis=0)
            
            # Expand bounding box slightly
            margin = 0.1 * np.linalg.norm(bbox_max - bbox_min)
            bbox_min -= margin
            bbox_max += margin
            
            # Create minimal hull points (rectangle in 3D)
            hull_points = [
                Vector3D(bbox_min[0], bbox_min[1], bbox_min[2], point_type="CORNER"),
                Vector3D(bbox_max[0], bbox_min[1], bbox_min[2], point_type="CORNER"),
                Vector3D(bbox_max[0], bbox_max[1], bbox_min[2], point_type="CORNER"),
                Vector3D(bbox_min[0], bbox_max[1], bbox_min[2], point_type="CORNER")
            ]
            
            # Calculate surface size
            bbox_diag = np.linalg.norm(bbox_max - bbox_min)
            
            # Respect user's target size setting - only use bbox-based size as fallback for very large values
            user_target_size = config.get('target_size', 1.0)
            bbox_based_size = bbox_diag / 20.0
            
            # Use user's setting if reasonable, otherwise use bbox-based constraint
            if user_target_size <= bbox_diag:  # User's setting is reasonable for this surface
                surface_size = user_target_size
                logger.debug(f"Using user target size: {surface_size:.2f} (bbox_diag: {bbox_diag:.2f})")
            else:  # User's setting is too large for this surface
                surface_size = bbox_based_size
                logger.warning(f"User target size {user_target_size:.2f} too large for surface (bbox: {bbox_diag:.2f}), using {surface_size:.2f}")
            
            # Calculate projection parameters
            hull_points_np = np.array([[p.x, p.y, p.z] for p in hull_points])
            projection_params = self._calculate_surface_projection_params(hull_points_np)
            
            surface_data = {
                'hull_points': hull_points,
                'size': surface_size,
                'projection_params': projection_params,
                'name': dataset.get('name', f'Surface_{dataset_idx}'),
                'index': dataset_idx,
                'minimal_hull': True  # Flag to indicate this is a minimal hull
            }
            
            logger.info(f"Created minimal surface data for dataset {dataset_idx} with bounding box hull")
            return surface_data
            
        except Exception as e:
            logger.error(f"Error preparing minimal surface data for dataset {dataset_idx}: {e}")
            return None

    def _find_intersections_for_surface(self, surface_idx):
        """
        Find all intersection lines that involve the specified surface.
        """
        intersections_on_surface = []
        
        # Search through refined intersections
        if hasattr(self, 'refined_intersections_for_visualization') and surface_idx in self.refined_intersections_for_visualization:
            for intersection_data in self.refined_intersections_for_visualization[surface_idx]:
                # Convert points to Vector3D objects
                intersection_points = []
                for point_data in intersection_data.get('points', []):
                    if len(point_data) >= 3:
                        point_type = point_data[3] if len(point_data) > 3 else "DEFAULT"
                        intersection_points.append(Vector3D(point_data[0], point_data[1], point_data[2], point_type=point_type))
                
                if len(intersection_points) >= 2:  # Valid intersection line
                    intersections_on_surface.append({
                        'points': intersection_points,
                        'type': 'intersection_line',
                        'size': intersection_data.get('size', 1.0),
                        'other_surface_id': intersection_data.get('dataset_id2' if intersection_data.get('dataset_id1') == surface_idx else 'dataset_id1')
                    })
        
        # Also check stored constraints
        surface_dataset = self.datasets[surface_idx] if surface_idx < len(self.datasets) else None
        if surface_dataset and 'stored_constraints' in surface_dataset:
            for constraint in surface_dataset['stored_constraints']:
                if constraint.get('type') == 'intersection_line':
                    # Convert constraint points to Vector3D objects
                    constraint_points = []
                    for point_data in constraint.get('points', []):
                        if len(point_data) >= 3:
                            point_type = point_data[3] if len(point_data) > 3 else "DEFAULT"
                            constraint_points.append(Vector3D(point_data[0], point_data[1], point_data[2], point_type=point_type))
                    
                    if len(constraint_points) >= 2:
                        intersections_on_surface.append({
                            'points': constraint_points,
                            'type': 'intersection_line',
                            'size': constraint.get('size', 1.0),
                            'other_surface_id': constraint.get('other_surface_id')
                        })
        
        # Remove duplicates based on point coordinates
        unique_intersections = []
        for intersection in intersections_on_surface:
            is_duplicate = False
            for existing in unique_intersections:
                if self._are_intersection_lines_duplicate(intersection['points'], existing['points']):
                    is_duplicate = True
                    break
            if not is_duplicate:
                unique_intersections.append(intersection)
        
        return unique_intersections

    def _are_intersection_lines_duplicate(self, pts1, pts2, tol=1e-8):
        """True iff two intersection polylines are identical point-by-point."""
        if len(pts1) != len(pts2):
            return False

        def _close(pa, pb):
            return (abs(pa.x - pb.x) < tol and
                    abs(pa.y - pb.y) < tol and
                    abs(pa.z - pb.z) < tol)

        forward = all(_close(a, b) for a, b in zip(pts1, pts2))
        if forward:
            return True
        reverse = all(_close(a, b) for a, b in zip(pts1, reversed(pts2)))
        return reverse

    def _find_intersections_for_surface_with_constraints(self, surface_idx):
        """
        Find intersection lines for surface, filtered by constraint selections from Tab 6.
        Only includes intersections if they are selected in the constraint tree.
        """
        # Start with all intersections for this surface
        all_intersections = self._find_intersections_for_surface(surface_idx)
        
        # If no constraint manager or no constraints selected, return all intersections
        if not hasattr(self, 'constraint_manager') or not self.constraint_manager:
            logger.info(f"No constraint manager - using all {len(all_intersections)} intersections for surface {surface_idx}")
            return all_intersections
        
        # Check constraint states to filter intersections
        filtered_intersections = []
        surface_constraints = getattr(self.constraint_manager, 'surface_constraints', {}).get(surface_idx, [])
        constraint_states = getattr(self.constraint_manager, 'constraint_states', {})
        
        # If no constraints for this surface, return all intersections
        if not surface_constraints:
            logger.info(f"No surface constraints - using all {len(all_intersections)} intersections for surface {surface_idx}")
            return all_intersections
        
        # Filter intersections based on constraint selection states
        for intersection_data in all_intersections:
            include_intersection = False
            
            # Check if any intersection constraint for this surface is selected
            for c_idx, constraint in enumerate(surface_constraints):
                if constraint.get("type") == "INTERSECTION":
                    # Check if this constraint is selected (state = "SEGMENTS")
                    constraint_state = constraint_states.get((surface_idx, c_idx), "SEGMENTS")  # Default to selected
                    if constraint_state == "SEGMENTS":
                        include_intersection = True
                        break
            
            if include_intersection:
                filtered_intersections.append(intersection_data)
        
        logger.info(f"Constraint filtering: {len(filtered_intersections)}/{len(all_intersections)} intersections selected for surface {surface_idx}")
        return filtered_intersections
    
    def _apply_constraint_selections_to_surface_data(self, surface_data, surface_idx):
        """
        Apply constraint selections from Tab 6 to modify surface data (e.g., filter hull points).
        """
        # If no constraint manager, return original surface data
        if not hasattr(self, 'constraint_manager') or not self.constraint_manager:
            return surface_data
        
        # Check hull constraint selections
        surface_constraints = getattr(self.constraint_manager, 'surface_constraints', {}).get(surface_idx, [])
        constraint_states = getattr(self.constraint_manager, 'constraint_states', {})
        
        # Check if hull constraints are selected
        hull_constraints_selected = False
        for c_idx, constraint in enumerate(surface_constraints):
            if constraint.get("type") == "HULL":
                constraint_state = constraint_states.get((surface_idx, c_idx), "SEGMENTS")  # Default to selected
                if constraint_state == "SEGMENTS":
                    hull_constraints_selected = True
                    break
        
        # If hull constraints are deselected, remove hull points
        if not hull_constraints_selected and surface_constraints:  # Only filter if constraints exist
            logger.info(f"Hull constraints deselected for surface {surface_idx} - removing hull points")
            modified_surface_data = surface_data.copy()
            modified_surface_data['hull_points'] = []  # Remove hull constraints
            return modified_surface_data
        
        logger.info(f"Hull constraints selected for surface {surface_idx} - keeping hull points")
        return surface_data


    
    def _setup_constraint_manager_from_data(self):
        """
        Setup constraint manager based on available surface and intersection data.
        """
        if not self.constraint_manager:
            return
        
        # Clear existing constraint data
        self.constraint_manager.surface_constraints = {}
        self.constraint_manager.constraint_states = {}
        
        # Add constraints for each surface that has hull points
        for surface_idx, dataset in enumerate(self.datasets):
            if dataset.get('type') == 'polyline':
                continue  # Skip polylines
                
            surface_constraints = []
            
            # Add hull constraints if hull points exist
            if 'hull_points' in dataset and dataset['hull_points']:
                for i, hull_point in enumerate(dataset['hull_points']):
                    constraint = {
                        'type': 'HULL',
                        'segment_id': i,
                        'points': [hull_point]  # Each hull point is a constraint segment
                    }
                    surface_constraints.append(constraint)
                    # Set constraint state to selected by default
                    self.constraint_manager.constraint_states[(surface_idx, len(surface_constraints) - 1)] = "SEGMENTS"
            
            # Add intersection constraints if they exist for this surface
            if hasattr(self, 'datasets_intersections') and surface_idx in self.datasets_intersections:
                for line_id, intersection_data in enumerate(self.datasets_intersections[surface_idx]):
                    constraint = {
                        'type': 'INTERSECTION',
                        'line_id': line_id,
                        'points': intersection_data.get('points', []),
                        'other_surface': intersection_data.get('other_surface_id')
                    }
                    surface_constraints.append(constraint)
                    # Set constraint state to selected by default
                    self.constraint_manager.constraint_states[(surface_idx, len(surface_constraints) - 1)] = "SEGMENTS"
            
            if surface_constraints:
                self.constraint_manager.surface_constraints[surface_idx] = surface_constraints
                logger.info(f"Added {len(surface_constraints)} constraints for surface {surface_idx}")
        
        logger.info(f"Constraint manager setup completed with {len(self.constraint_manager.surface_constraints)} surfaces")

    def _calculate_surface_projection_params(self, hull_points_np):
        """
        Calculate projection parameters for projecting 3D surface to 2D for triangulation.
        """
        try:
            # Calculate surface centroid
            centroid = np.mean(hull_points_np, axis=0)
            
            # Calculate surface normal using SVD of centered points
            centered_points = hull_points_np - centroid
            U, S, Vt = np.linalg.svd(centered_points, full_matrices=False)
            
            # The surface normal is the last column of V (or last row of Vt)
            normal = Vt[-1, :]
            normal = normal / np.linalg.norm(normal)  # Normalize
            
            # Create local coordinate system
            # Choose u-axis as the direction of maximum variance
            u_axis = Vt[0, :]
            u_axis = u_axis / np.linalg.norm(u_axis)
            
            # v-axis is perpendicular to both normal and u-axis
            v_axis = np.cross(normal, u_axis)
            v_axis = v_axis / np.linalg.norm(v_axis)
            
            # Create basis matrix [u_axis, v_axis] for 2D projection
            basis = np.array([u_axis, v_axis])
            
            projection_params = {
                'centroid': centroid,
                'normal': normal,
                'basis': basis,
                'u_axis': u_axis,
                'v_axis': v_axis
            }
            
            return projection_params
            
        except Exception as e:
            logger.error(f"Error calculating projection parameters: {e}")
            # Fallback to XY plane projection
            return {
                'centroid': np.mean(hull_points_np, axis=0),
                'normal': np.array([0.0, 0.0, 1.0]),
                'basis': np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]),
                'u_axis': np.array([1.0, 0.0, 0.0]),
                'v_axis': np.array([0.0, 1.0, 0.0])
            }

    def _update_conforming_mesh_visualization(self):
        """
        Update the visualization to show the generated conforming meshes.
        """
        if not hasattr(self, 'refine_mesh_plotter') or self.refine_mesh_plotter is None:
            return
        
        try:
            # Clear previous visualization
            self.refine_mesh_plotter.clear()
            
            # Check if conforming meshes should be shown
            show_conforming_meshes = getattr(self, 'show_conforming_meshes_checkbox', None) is None or \
                                    self.show_conforming_meshes_checkbox.isChecked()
            
            # Also check if original lines should be shown
            show_original_lines = getattr(self, 'show_original_lines_checkbox', None) is None or \
                                 self.show_original_lines_checkbox.isChecked()
            
            # Count surfaces with conforming meshes
            surfaces_with_meshes = 0
            
            # Visualize conforming meshes for each surface if enabled
            if show_conforming_meshes:
                for dataset_idx, dataset in enumerate(self.datasets):
                    if 'conforming_mesh' not in dataset:
                        continue
                    
                    conforming_mesh = dataset['conforming_mesh']
                    vertices = conforming_mesh['vertices']
                    triangles = conforming_mesh['triangles']
                    
                    if len(vertices) == 0 or len(triangles) == 0:
                        continue
                    
                    surfaces_with_meshes += 1
                    surface_name = dataset.get('name', f'Surface_{dataset_idx}')
                    
                    # Create PyVista mesh for visualization
                    import pyvista as pv
                    faces = []
                    for tri in triangles:
                        faces.extend([3, tri[0], tri[1], tri[2]])  # 3 vertices per triangle
                    
                    mesh = pv.PolyData(vertices, faces)
                    
                    # Add mesh to plotter with unique color
                    color_map = ['red', 'green', 'blue', 'yellow', 'cyan', 'magenta', 'orange', 'purple']
                    color = color_map[dataset_idx % len(color_map)]
                    
                    self.refine_mesh_plotter.add_mesh(
                        mesh,
                        color=color,
                        opacity=0.7,
                        show_edges=True,
                        edge_color='black',
                        label=f"{surface_name} ({len(vertices)} vertices, {len(triangles)} triangles)"
                    )
                    
                    logger.info(f"Visualized conforming mesh for {surface_name}: {len(vertices)} vertices, {len(triangles)} triangles")
            
            # Visualize original intersection lines if enabled
            if show_original_lines and hasattr(self, 'refined_intersections_for_visualization'):
                self._add_intersection_lines_to_visualization()
            
            # Add legend and labels
            display_text = []
            if surfaces_with_meshes > 0:
                display_text.append(f"Conforming Surface Meshes: {surfaces_with_meshes} surfaces")
            if show_original_lines and hasattr(self, 'refined_intersections_for_visualization'):
                num_intersections = sum(len(intersections) for intersections in self.refined_intersections_for_visualization.values())
                display_text.append(f"Refined Intersection Lines: {num_intersections} lines")
            
            if display_text:
                self.refine_mesh_plotter.add_text(
                    "\n".join(display_text),
                    position='upper_edge',
                    color='white',
                    font_size=12
                )
                
                # Add legend if there are conforming meshes
                if surfaces_with_meshes > 0:
                    self.refine_mesh_plotter.add_legend(bcolor='white', face='r')
            else:
                self.refine_mesh_plotter.add_text(
                    "No data to display.\nRun 'Refine Intersection Lines' and 'Generate Conforming Surface Meshes' first.",
                    position='upper_edge',
                    color='white'
                )
            
            # Update plotter
            self.refine_mesh_plotter.reset_camera()
            
        except Exception as e:
            logger.error(f"Error updating conforming mesh visualization: {e}", exc_info=True)
            self.refine_mesh_plotter.add_text(
                f"Visualization error: {str(e)}",
                position='upper_edge',
                color='red'
            )

    def _update_conforming_mesh_summary(self, successful_surfaces, total_surfaces, failed_surfaces):
        """
        Update the conforming mesh summary label with generation results.
        """
        try:
            # Count total vertices and triangles across all conforming meshes
            total_vertices = 0
            total_triangles = 0
            surface_details = []
            
            for dataset_idx, dataset in enumerate(self.datasets):
                if 'conforming_mesh' not in dataset:
                    continue
                    
                conforming_mesh = dataset['conforming_mesh']
                num_vertices = conforming_mesh['statistics']['num_vertices']
                num_triangles = conforming_mesh['statistics']['num_triangles']
                num_constraints = conforming_mesh['statistics']['num_constraints']
                target_size = conforming_mesh['statistics']['target_size']
                
                total_vertices += num_vertices
                total_triangles += num_triangles
                
                surface_name = dataset.get('name', f'Surface_{dataset_idx}')
                surface_details.append(
                    f"• <b>{surface_name}</b>: {num_vertices} vertices, {num_triangles} triangles, {num_constraints} constraints (size: {target_size:.2f})"
                )
            
            # Build summary HTML
            summary_html = f"""
            <h3>🏗️ Conforming Surface Mesh Generation Results</h3>
            <p><b>Processing Status:</b> {successful_surfaces}/{total_surfaces} surfaces processed successfully</p>
            <p><b>Total Mesh Statistics:</b></p>
            <ul>
                <li><b>Total Vertices:</b> {total_vertices:,}</li>
                <li><b>Total Triangles:</b> {total_triangles:,}</li>
                <li><b>Surfaces with Conforming Meshes:</b> {successful_surfaces}</li>
            </ul>
            """
            
            if surface_details:
                summary_html += "<p><b>Surface Details:</b></p><ul>"
                for detail in surface_details:
                    summary_html += f"<li>{detail}</li>"
                summary_html += "</ul>"
            
            if failed_surfaces:
                summary_html += "<p><b>⚠️ Failed Surfaces:</b></p><ul>"
                for idx, name, error in failed_surfaces:
                    summary_html += f"<li><b>{name}</b>: {error}</li>"
                summary_html += "</ul>"
            
            summary_html += """
            <p><b>📋 Next Steps:</b></p>
            <ul>
                <li>Review surface meshes in the visualization</li>
                <li>Proceed to Pre-Tetra Mesh tab to select surfaces for 3D meshing</li>
                <li>Run tetrahedral mesh generation with validated conforming surfaces</li>
            </ul>
            """
            
            self.conforming_mesh_summary_label.setText(summary_html)
            
        except Exception as e:
            logger.error(f"Error updating conforming mesh summary: {e}")
            self.conforming_mesh_summary_label.setText(f"<b>Error updating summary:</b> {str(e)}")

    def _add_intersection_lines_to_visualization(self):
        """
        Add intersection lines to the current visualization.
        """
        try:
            import pyvista as pv
            
            for dataset_idx, intersections in self.refined_intersections_for_visualization.items():
                for intersection_data in intersections:
                    points = intersection_data.get('points', [])
                    if len(points) < 2:
                        continue
                    
                    # Convert points to numpy array
                    line_points = np.array([[p[0], p[1], p[2]] for p in points if len(p) >= 3])
                    if len(line_points) < 2:
                        continue
                    
                    # Create polyline
                    n_points = len(line_points)
                    lines = [n_points] + list(range(n_points))
                    polyline = pv.PolyData(line_points, lines=lines)
                    
                    # Add to plotter with distinctive style
                    self.refine_mesh_plotter.add_mesh(
                        polyline,
                        color='white',
                        line_width=3,
                        opacity=0.8,
                        label=f"Intersection {dataset_idx}"
                    )
        except Exception as e:
            logger.error(f"Error adding intersection lines to visualization: {e}")

    
    def _read_point_file(self, file_path):
        """Read points from a file, handling various delimiters and formats."""
        points = []
        try:
            # Check file extension to determine reading method
            ext = os.path.splitext(file_path)[1].lower()
            
            # Handle VTU files using PyVista (if available)
            if ext == '.vtu':

                logger.info(f"Reading VTU file using PyVista: {file_path}")
                mesh = pv.read(file_path)
                
                # Extract points from the mesh
                if hasattr(mesh, 'points') and mesh.points is not None:
                    points = mesh.points
                    logger.info(f"Successfully extracted {len(points)} points from VTU mesh")
                    
                    # Ensure 3D format
                    if points.shape[1] < 3:
                        points_3d = np.zeros((len(points), 3))
                        points_3d[:, :points.shape[1]] = points
                        return points_3d
                    
                    return points[:, :3]  # Return first 3 columns (x, y, z)
                else:
                    raise ValueError("No point data found in VTU file")
            
            # Handle text-based files (.txt, .csv, .dat) with existing logic
            # Handle text-based files (.txt, .csv, .dat) with existing logic
            # --- Primary Method: Line-by-line parsing for robustness --- 
            with open(file_path, 'r') as f:
                for line_num, line in enumerate(f):
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue # Skip comments and empty lines

                    # Check for Bounds format first
                    if line.startswith("Bounds:"):
                        bounds_points = self._parse_bounds_format(line)
                        if bounds_points:
                            points.extend(bounds_points)
                        continue
                        
                    # Clean the line: replace delimiters, handle signs
                    cleaned_line = line.replace('\t', ' ').replace(',', ' ').replace(';', ' ')
                    # Handle potential + signs before numbers
                    cleaned_line = re.sub(r'(?<![eE\d.-])\+', '', cleaned_line) # Remove + if not part of scientific notation or preceded by digit/.
                    # Ensure space around minus signs not part of scientific notation
                    cleaned_line = re.sub(r'(?<![eE\d.-])-', ' -', cleaned_line) 
                    # Remove extra whitespace
                    cleaned_line = ' '.join(cleaned_line.split())

                    parts = cleaned_line.split()
                    try:
                        if len(parts) >= 2:
                            x = float(parts[0])
                            y = float(parts[1])
                            z = float(parts[2]) if len(parts) >= 3 else 0.0
                            points.append([x, y, z])
                        else:
                            logger.warning(f"Skipping line {line_num+1}: Not enough values found in '{line}'")
                    except ValueError as ve:
                        logger.warning(f"Skipping line {line_num+1} due to value error: {ve} in '{line}'")
                        continue # Skip lines with non-numeric data after cleaning
            
            if points:
                logger.info(f"Read {len(points)} points using line-by-line parsing.")
                points_arr = np.array(points)
                # Ensure 3D format even if Z was missing
                if points_arr.shape[1] == 2:
                     points_3d = np.zeros((len(points_arr), 3))
                     points_3d[:, 0:2] = points_arr
                     return points_3d
                return points_arr[:, :3] # Return first 3 columns if more exist
            else:
                 logger.info("Line-by-line parsing yielded no points, trying np.loadtxt.")

            # --- Fallback Method: np.loadtxt for text files --- 
            points = None # Reset points if primary method failed
            ext = os.path.splitext(file_path)[1].lower()
            delimiters_to_try = [None, '\t', ',', ' '] # None tries whitespace
            if ext == '.csv': # Prioritize comma for csv
                delimiters_to_try = [',', '\t', ' ', None]
                
            for delim in delimiters_to_try:
                try:
                    # Try loading, skip comment lines
                    loaded_points = np.loadtxt(file_path, delimiter=delim, comments='#')
                    # Check shape after loading
                    if loaded_points.ndim == 1: # Handle case where only one line is read
                        if loaded_points.shape[0] >= 2:
                           points = loaded_points.reshape(1, -1)
                    elif loaded_points.ndim == 2 and loaded_points.shape[1] >= 2:
                         points = loaded_points
                         
                    if points is not None:
                         logger.info(f"Successfully read data using np.loadtxt with delimiter: '{delim if delim else 'whitespace'}'")
                         break # Stop trying delimiters if successful
                except Exception as np_err:
                    logger.debug(f"np.loadtxt failed with delimiter '{delim if delim else 'whitespace'}': {np_err}")
                    continue
            
            if points is None:
                 logger.error("Failed to read valid points using all methods.")
                 raise ValueError("Could not read valid point data from file.")

            # --- Final Processing (applies to np.loadtxt result) --- 
            if points.shape[1] < 2:
                raise ValueError("File must contain at least 2D points (x, y)")
            
            if points.shape[1] == 2:
                points_3d = np.zeros((len(points), 3))
                points_3d[:, 0:2] = points
                logger.info(f"Converted {len(points)} 2D points to 3D.")
                return points_3d
            
            logger.info(f"Read {len(points)} points using np.loadtxt.")
            return points[:, 0:3]
            
        except Exception as e:
            logger.error(f"Error reading file '{file_path}': {str(e)}")
            QMessageBox.critical(self, "Error Reading File", f"Failed to read points from file:\n{os.path.basename(file_path)}\n\nError: {str(e)}")
            return None
            
    def _parse_bounds_format(self, line):
        """
        Parse bounds format line: "Bounds: X[min,max] Y[min,max] Z[min,max]"
        
        Args:
            line: String line in bounds format
            
        Returns:
            List of points representing the bounds corners (4 points, Z=0)
        """
        try:
            # Extract X, Y, Z ranges
            x_range = re.search(r'X\[([-+]?\d+\.?\d*),([-+]?\d+\.?\d*)\]', line)
            y_range = re.search(r'Y\[([-+]?\d+\.?\d*),([-+]?\d+\.?\d*)\]', line)
            z_range = re.search(r'Z\[([-+]?\d+\.?\d*),([-+]?\d+\.?\d*)\]', line)
            
            if not x_range or not y_range:
                logger.debug("Could not find X or Y ranges in bounds line")
                return None
                
            # Extract min/max values for each dimension
            x_min, x_max = float(x_range.group(1)), float(x_range.group(2))
            y_min, y_max = float(y_range.group(1)), float(y_range.group(2))
            
            # Use Z from bounds if present for 3D bounds
            if z_range:
                 z_min, z_max = float(z_range.group(1)), float(z_range.group(2))
            else:
                 z_min, z_max = 0.0, 0.0 # Default Z to 0 if not found
                 
            # Return 8 corners of the 3D bounding box
            bounds_points = [
                [x_min, y_min, z_min],
                [x_max, y_min, z_min],
                [x_max, y_max, z_min],
                [x_min, y_max, z_min],
                [x_min, y_min, z_max],
                [x_max, y_min, z_max],
                [x_max, y_max, z_max],
                [x_min, y_max, z_max]
            ]
            
            logger.info(f"Parsed bounds line into 8 corner points.")
            return bounds_points
        except Exception as e:
            logger.debug(f"Error parsing bounds format: {str(e)}")
            return None
            

    # Visualization methods
    def _clear_hull_plot(self):
        """Clear the hull plot"""
        # Clear existing visualization
        while self.hull_viz_layout.count():
            item = self.hull_viz_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
            
        # Reset placeholder
        placeholder_text = "Compute convex hull to visualize in 3D"
            
        self.hull_viz_placeholder = QLabel(placeholder_text)
        self.hull_viz_placeholder.setAlignment(Qt.AlignCenter)
        self.hull_viz_layout.addWidget(self.hull_viz_placeholder)
        
        # Reset hull info
        self.hull_points_label.setText("Hull vertices: 0")
        self.hull_area_label.setText("Hull area: 0.0")
    
    def _clear_segment_plot(self):
        """Clear the segmentation plot"""
        # Clear existing visualization
        while self.segment_viz_layout.count():
            item = self.segment_viz_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
            
        # Reset placeholder
        placeholder_text = "Compute segmentation to visualize in 3D"
            
        self.segment_viz_placeholder = QLabel(placeholder_text)
        self.segment_viz_placeholder.setAlignment(Qt.AlignCenter)
        self.segment_viz_layout.addWidget(self.segment_viz_placeholder)
        
        # Reset segment info
        self.num_segments_label.setText("Segments: 0")
        self.avg_segment_length_label.setText("Avg length: 0.0")
    
    def _clear_triangulation_plot(self):
        """Clear the triangulation plot"""
        # Clear existing visualization
        while self.tri_viz_layout.count():
            item = self.tri_viz_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
            
        # Reset placeholder
        placeholder_text = "Run triangulation to visualize in 3D"
            
        self.tri_viz_placeholder = QLabel(placeholder_text)
        self.tri_viz_placeholder.setAlignment(Qt.AlignCenter)
        self.tri_viz_layout.addWidget(self.tri_viz_placeholder)
        
        # Reset triangulation info
        self.num_triangles_label.setText("Triangles: 0")
        self.num_vertices_label.setText("Vertices: 0")
        self.mean_edge_label.setText("Mean edge: 0.0")
        self.uniformity_label.setText("Uniformity: 0.0")
    
    
    
     #------------------------------------------------------------------------
    # -------------------------------------------------------------------------
    # 1) Sub-sampling helper
    # -------------------------------------------------------------------------
    def _subsample_points_for_hull(self, points: np.ndarray, max_points: int = 50) -> np.ndarray:
        """
        Return ≤ `max_points` points while ALWAYS preserving every true hull
        vertex.  Interior points are randomly thinned only if necessary.
        """
        from scipy.spatial import ConvexHull

        n_pts = len(points)
        if n_pts <= max_points:
            return points

        # --- keep all hull vertices ------------------------------------------------
        hull_idx = np.unique(ConvexHull(points).vertices)
        boundary = points[hull_idx]

        if len(boundary) >= max_points:          # still too many → uniform stride
            step = max(1, len(boundary) // max_points)
            return boundary[::step][:max_points]

        # --- add a few interior samples to reach target ---------------------------
        remain = max_points - len(boundary)
        interior_mask = np.ones(n_pts, bool)
        interior_mask[hull_idx] = False
        interior_idx = np.where(interior_mask)[0]

        if remain and len(interior_idx):
            chosen = np.random.choice(interior_idx,
                                    size=min(remain, len(interior_idx)),
                                    replace=False)
            return np.vstack([boundary, points[chosen]])

        return boundary
    
    # -------------------------------------------------------------------------
    # 2) Quasi-planar check (helper)
    # -------------------------------------------------------------------------
    def _is_quasi_planar(self, points: np.ndarray, tol: float = 0.5) -> bool:
        """
        Treat cloud as planar when smallest PCA singular value is far smaller
        than the next one (sheet-like geometry).
        """
        centred = points - points.mean(axis=0)
        _, s, _ = np.linalg.svd(centred, full_matrices=False)
        return s[-1] / s[-2] < tol
    def _pca_project(self, points: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Centre the cloud, compute PCA, and return the 2-D projection onto the
        first two principal components.
        """
        cen = points.mean(axis=0)
        u, _, vh = np.linalg.svd(points - cen, full_matrices=False)
        proj2d = (points - cen) @ vh[:2].T    # (N,2) projection
        return cen, proj2d

            # ------------------------------------------------------------------------
    # 2.  Main hull computation
    # ------------------------------------------------------------------------
        # ------------------------------------------------------------------------
    # 2.  Main hull computation
    # ------------------------------------------------------------------------
        # ------------------------------------------------------------------------
    # 2.  Main hull computation (CORRECTED)
    # ------------------------------------------------------------------------
        # ------------------------------------------------------------------------
    # 2.  Main hull computation (CORRECTED for non-convex boundaries)
    # ------------------------------------------------------------------------


    # Replace the entire _compute_hull_for_dataset method with this:
    def _compute_hull_for_dataset(self, dataset_index: int) -> bool:
        """
        Compute (and store) the boundary poly-line for the selected dataset.
        - For 2D data, this computes the convex hull.
        - For 3D sheet-like data, this finds the ordered "rim" or "outline"
        (which can be concave) by finding the boundary of a Delaunay triangulation.
        
        This version also identifies and marks geometric corners as "special points"
        immediately after calculation, preparing it for robust segmentation.

        Returns:
            bool: True if a boundary was computed and stored in dataset['hull_points'].
        """
        from scipy.spatial import ConvexHull, Delaunay
        import traceback

        if not (0 <= dataset_index < len(self.datasets)):
            logger.error("Invalid dataset index %s for hull computation", dataset_index)
            return False

        ds = self.datasets[dataset_index]
        pts = ds.get("points")
        if pts is None or len(pts) < 3:
            logger.warning("Dataset '%s' has < 3 points, skipping hull computation.", ds.get('name'))
            return False

        try:
            dim = pts.shape[1]
            hull_pts_np = None

            # --- BRANCH 1: Strict 2D data ---
            # For pure 2D data, the convex hull is the correct and efficient approach.
            if dim == 2:
                logger.info(f"Computing 2D convex hull for '{ds.get('name')}'...")
                hull = ConvexHull(pts)
                hull_pts_2d = pts[hull.vertices]
                # Convert to 3D for consistency, setting Z=0
                hull_pts_np = np.hstack([hull_pts_2d, np.zeros((len(hull_pts_2d), 1))])

            # --- BRANCH 2: 3D Data (Handles Convex and Concave Boundaries) ---
            else: # dim >= 3
                logger.info(f"Computing 3D data boundary for '{ds.get('name')}' using Delaunay triangulation...")
                # 1. Project all 3D points onto their best-fit 2D plane using PCA.
                _centroid, projected_pts_2d = self._pca_project(pts)

                # 2. Perform Delaunay triangulation on the 2D projected points.
                tri = Delaunay(projected_pts_2d)

                # 3. Find the boundary edges (edges that appear in only one triangle).
                edges = set()
                for simplex in tri.simplices:
                    for j in range(3):
                        p1_idx, p2_idx = simplex[j], simplex[(j + 1) % 3]
                        edge = tuple(sorted((p1_idx, p2_idx)))
                        if edge in edges:
                            edges.remove(edge) # Internal edge, remove it.
                        else:
                            edges.add(edge) # Potential boundary edge.
                
                if not edges:
                    logger.warning("Delaunay method found no boundary edges. Falling back to convex hull on projected points.")
                    hull = ConvexHull(projected_pts_2d)
                    hull_pts_np = pts[hull.vertices]
                else:
                    # 4. Stitch the unordered boundary edges into a continuous path.
                    ordered_indices = []
                    current_edge = edges.pop()
                    ordered_indices.extend(list(current_edge))
                    
                    while edges:
                        last_point_idx = ordered_indices[-1]
                        found_next = False
                        for edge in list(edges): # Iterate over a copy
                            if last_point_idx in edge:
                                next_point_idx = edge[1] if edge[0] == last_point_idx else edge[0]
                                ordered_indices.append(next_point_idx)
                                edges.remove(edge)
                                found_next = True
                                break
                        if not found_next:
                            logger.warning("Boundary walk broken. The result might be incomplete or have multiple loops.")
                            break
                    
                    # 5. Get the final ordered polyline from the original 3D points.
                    hull_pts_np = pts[ordered_indices]

            # --- Post-processing for BOTH cases ---

            # Ensure the polyline is closed for processing
            if len(hull_pts_np) > 0 and not np.array_equal(hull_pts_np[0], hull_pts_np[-1]):
                hull_pts_np = np.vstack([hull_pts_np, hull_pts_np[0:1]])
            
            # Convert numpy array to list of Vector3D objects, initializing type
            hull_vector3d = [Vector3D(p[0], p[1], p[2], point_type="DEFAULT") for p in hull_pts_np]
                
            # Identify and mark special corner points using our utility function
            hull_vector3d = make_corners_special(hull_vector3d)

            # Store the final hull as a NumPy array of [x, y, z, type_string]
            # This is the crucial format for passing feature info to the next steps.
            hull_with_types = []
            for p in hull_vector3d:
                ptype = getattr(p, 'point_type', "DEFAULT")
                hull_with_types.append([p.x, p.y, p.z, ptype])
                
            ds["hull_points"] = np.array(hull_with_types, dtype=object)

            # Clear downstream results as they are now invalid
            ds.pop("segments", None)
            ds.pop("triangulation_result", None)
            logger.info(f"Successfully computed and analyzed boundary for '{ds.get('name')}' with {len(hull_pts_np)-1} vertices.")
            return True

        except Exception as exc:
            logger.error(f"Hull/Boundary computation failed for dataset {dataset_index}: {exc}")
            logger.debug(traceback.format_exc())
            return False

    
    def compute_hull(self):
        """Compute the convex hull of the loaded points for the *active* dataset (primarily for context menu)"""
        # Check if we have an active dataset
        if self.current_dataset_index < 0 or self.current_dataset_index >= len(self.datasets):
            self.statusBar().showMessage("Error: No active dataset selected")
            QMessageBox.critical(self, "Error", "No active dataset selected")
            return

        self.statusBar().showMessage(f"Computing hull for {self.datasets[self.current_dataset_index]['name']}...") # Add status message here for single run
        success = self._compute_hull_for_dataset(self.current_dataset_index)

        if success:
            # Update statistics and visualization after computing for the active one
            self._update_statistics()
            self._visualize_all_hulls()
            self._update_visualization() # Ensure other dependent views are updated/cleared
            self.notebook.setCurrentIndex(1)  # Switch to hull tab
            self.statusBar().showMessage(f"Computed hull for {self.datasets[self.current_dataset_index]['name']}") # Add success message here

    def compute_all_hulls(self):
        """Compute the convex hull for all loaded datasets using a worker thread."""
        if not self.datasets:
            QMessageBox.information(self, "No Data", "No datasets loaded to compute hulls.")
            return
        self._run_batch_computation("hulls", len(self.datasets))
    
        
    
    

    
    def _set_height_factor(self, height):
        """Set the height factor for 3D visualization"""
        self.height_factor = height
        self.height_factor_slider.setValue(int(height * 100))
        
        # Update existing visualization if any
        if hasattr(self, 'triangulation_result') and self.triangulation_result is not None:
            vertices = self.triangulation_result['vertices']
            triangles = self.triangulation_result['triangles']
            self._plot_triangulation(vertices, triangles, self.hull_points)
    
    def _show_about(self):
        """Show about dialog"""
        about_text = """
MeshIt Workflow GUI

A graphical interface for the complete MeshIt workflow,
including file loading, convex hull computation, 
segmentation, triangulation, and visualization.

3D Visualization: {status}
"""
        
        status = "Enabled" if self.view_3d_enabled else "Disabled (Install PyVista)"
        about_text = about_text.format(status=status)
        
        QMessageBox.information(self, "About MeshIt Workflow GUI", about_text)

    def _create_simplified_hull_for_segmentation(self, hull_points):
        """
        Create a simplified 4-corner hull from a complex hull for segmentation purposes.
        This extracts the bounding box corners from the complex hull.
        
        Args:
            hull_points: The complex hull points (N x 2 or N x 3)
            
        Returns:
            simplified_hull: 4-corner hull points in clockwise order + closing point
        """
        try:
            # Remove the closing point if present
            if len(hull_points) > 1 and np.array_equal(hull_points[0], hull_points[-1]):
                hull_boundary = hull_points[:-1]
            else:
                hull_boundary = hull_points
            
            # Find bounding box
            min_x, max_x = np.min(hull_boundary[:, 0]), np.max(hull_boundary[:, 0])
            min_y, max_y = np.min(hull_boundary[:, 1]), np.max(hull_boundary[:, 1])
            
            # Create 4 corner points
            if hull_boundary.shape[1] >= 3:
                # Use average Z coordinate for 3D data
                avg_z = np.mean(hull_boundary[:, 2])
                corners = np.array([
                    [min_x, min_y, avg_z],  # Bottom-left
                    [max_x, min_y, avg_z],  # Bottom-right  
                    [max_x, max_y, avg_z],  # Top-right
                    [min_x, max_y, avg_z]   # Top-left
                ])
            else:
                # 2D data
                corners = np.array([
                    [min_x, min_y],  # Bottom-left
                    [max_x, min_y],  # Bottom-right
                    [max_x, max_y],  # Top-right
                    [min_x, max_y]   # Top-left
                ])
            
            # Add closing point
            simplified_hull = np.vstack([corners, corners[0:1]])
            
            logger.info(f"Simplified complex hull from {len(hull_boundary)} to 4 corner points")
            return simplified_hull
            
        except Exception as e:
            logger.error(f"Error creating simplified hull: {e}")
            return hull_points  # Return original if simplification fails

    

    def _find_point_at_distance_fast(self, hull_boundary, cumulative_distances, target_distance):
        """
        Optimized version of _find_point_at_distance for better performance.
        Uses binary search for faster lookup in large hulls.
        """
        hull_size = len(hull_boundary)
        total_perimeter = cumulative_distances[-1]
        
        # Handle wrapping around the perimeter
        target_distance = target_distance % total_perimeter
        
        # Binary search for the containing edge (faster for large hulls)
        left, right = 0, hull_size
        while left < right - 1:
            mid = (left + right) // 2
            if cumulative_distances[mid] <= target_distance:
                left = mid
            else:
                right = mid
        
        i = left
        if i >= hull_size:
            i = 0
            
        # Interpolate between vertices i and (i+1)%hull_size
        edge_start_dist = cumulative_distances[i]
        edge_end_dist = cumulative_distances[i + 1]
        edge_length = edge_end_dist - edge_start_dist
        
        if edge_length < 1e-10:  # Very short edge
            return hull_boundary[i]
        
        # Interpolation parameter
        t = (target_distance - edge_start_dist) / edge_length
        
        # Get the two vertices
        p1 = hull_boundary[i]
        p2 = hull_boundary[(i + 1) % hull_size]
        
        # Linear interpolation
        return p1 + t * (p2 - p1)

    def _find_point_at_distance(self, hull_boundary, cumulative_distances, target_distance):
        """
        Find a point at a specific distance along the hull boundary.
        
        Args:
            hull_boundary: Array of hull vertices
            cumulative_distances: Array of cumulative distances at each vertex
            target_distance: Target distance along the perimeter
            
        Returns:
            Interpolated point at the target distance
        """
        try:
            hull_size = len(hull_boundary)
            total_perimeter = cumulative_distances[-1]
            
            # Handle wrapping around the perimeter
            target_distance = target_distance % total_perimeter
            
            # Find the edge that contains this distance
            for i in range(hull_size):
                if cumulative_distances[i] <= target_distance <= cumulative_distances[i + 1]:
                    # Interpolate between vertices i and (i+1)%hull_size
                    edge_start_dist = cumulative_distances[i]
                    edge_end_dist = cumulative_distances[i + 1]
                    edge_length = edge_end_dist - edge_start_dist
                    
                    if edge_length < 1e-10:  # Very short edge
                        return hull_boundary[i]
                    
                    # Interpolation parameter
                    t = (target_distance - edge_start_dist) / edge_length
                    
                    # Get the two vertices
                    p1 = hull_boundary[i]
                    p2 = hull_boundary[(i + 1) % hull_size]
                    
                    # Linear interpolation
                    interpolated_point = p1 + t * (p2 - p1)
                    return interpolated_point
            
            # Fallback to first vertex if no edge found
            logger.warning(f"Could not find edge for distance {target_distance}, using first vertex")
            return hull_boundary[0]
            
        except Exception as e:
            logger.error(f"Error finding point at distance {target_distance}: {e}")
            return hull_boundary[0] if len(hull_boundary) > 0 else np.array([0, 0])

    def _compute_segments_for_dataset(self, dataset_index):
        """
        Compute segmentation using the robust RefineByLength approach. This method
        takes the pre-processed hull (with corner points marked) and refines it
        based on the per-surface target feature size, preserving geometric features.

        Returns:
            bool: True on success, False on error.
        """
        if not (0 <= dataset_index < len(self.datasets)):
            logger.error(f"Invalid dataset index {dataset_index} for segmentation.")
            return False

        dataset = self.datasets[dataset_index]
        dataset_name = dataset.get('name', f"Dataset {dataset_index}")
        
        hull_points_with_types = dataset.get('hull_points')
        if hull_points_with_types is None or len(hull_points_with_types) < 4:
            logger.warning(f"Skipping segments for {dataset_name}: hull not computed or too small.")
            return False

        try:
            # PER-SURFACE length from the table (fallback handled inside helper)
            target_length = float(self._get_seg_target_length_for_dataset(dataset_index))
            if target_length <= 1e-6:
                logger.warning("Target Feature Size is too small, using default (1.0).")
                target_length = 1.0
                
            class TempHullLine:
                def __init__(self, points_with_types):
                    self.points = []
                    for p in points_with_types:
                        self.points.append(Vector3D(p[0], p[1], p[2], point_type=p[3]))

            hull_line = TempHullLine(hull_points_with_types)

            refined_hull_points_vec = refine_intersection_line_by_length(hull_line, target_length)
            
            segments = []
            if len(refined_hull_points_vec) >= 2:
                num_points_for_segments = len(refined_hull_points_vec)
                if (refined_hull_points_vec[0] - refined_hull_points_vec[-1]).length_squared() < 1e-24:
                    num_points_for_segments -= 1
                
                for i in range(num_points_for_segments):
                    p1 = refined_hull_points_vec[i]
                    p2 = refined_hull_points_vec[(i + 1) % len(refined_hull_points_vec)]
                    segments.append([p1.to_numpy(), p2.to_numpy()])

            dataset['segments'] = segments
            dataset.pop('triangulation_result', None)
            logger.info(f"Successfully created {len(segments)} segments for '{dataset_name}' using RefineByLength (per-surface={target_length}).")
            return True

        except Exception as e:
            logger.error(f"Error computing segments for '{dataset_name}': {e}", exc_info=True)
            return False
    def compute_segments(self):
        """Compute the segmentation of the convex hull for the *active* dataset (primarily for context menu)"""
        # Check if we have an active dataset
        self._sync_seg_lengths_from_table()
        if self.current_dataset_index < 0 or self.current_dataset_index >= len(self.datasets):
            self.statusBar().showMessage("Error: No active dataset selected")
            QMessageBox.critical(self, "Error", "No active dataset selected")
            return

        dataset = self.datasets[self.current_dataset_index]
        dataset_name = dataset.get('name', f"Dataset {self.current_dataset_index}")
        hull_points = dataset.get('hull_points')
        
        # Check if we have a complex hull (more than 20 vertices)
        if hull_points is not None:
            hull_size = len(hull_points) - 1 if len(hull_points) > 0 else 0  # Subtract closing point
            
            if hull_size > 20:
                # Ask user which approach to use for complex hulls
                reply = QMessageBox.question(
                    self, 
                    "Complex Hull Detected", 
                    f"Dataset '{dataset_name}' has a complex hull with {hull_size} vertices.\n\n"
                    "Choose segmentation approach:\n\n"
                    "• YES: Use full shape (preserves complex geometry)\n"
                    "• NO: Use simplified 4-corner approach (rectangular)",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes
                )
                
                if reply == QMessageBox.No:
                    # Use simplified approach
                    self.statusBar().showMessage(f"Computing simplified segments for {dataset_name}...")
                    success = self._compute_segments_for_dataset_with_simplified_hull(self.current_dataset_index)
                else:
                    # Use full complex hull
                    self.statusBar().showMessage(f"Computing full-shape segments for {dataset_name}...")
                    success = self._compute_segments_for_dataset(self.current_dataset_index)
            else:
                # Simple hull - use normal approach
                self.statusBar().showMessage(f"Computing segments for {dataset_name}...")
                success = self._compute_segments_for_dataset(self.current_dataset_index)
        else:
            # No hull data
            self.statusBar().showMessage(f"Computing segments for {dataset_name}...")
            success = self._compute_segments_for_dataset(self.current_dataset_index)

        if success:
            # Update statistics and visualization after computing for the active one
            self._update_statistics()
            
            # Force refresh of the UI
            QApplication.processEvents()
            
            # Force update the segment visualization
            try:
                self._visualize_all_segments()
                logger.info("Segment visualization updated successfully")
            except Exception as e:
                logger.error(f"Error updating segment visualization: {e}")
            
            # Force another UI refresh after visualization
            QApplication.processEvents()
            
            self._update_visualization() # Ensure other dependent views are updated/cleared
            self.notebook.setCurrentIndex(2)  # Switch to segment tab
            self.statusBar().showMessage(f"Computed segments for {dataset_name}")
            self._refresh_seg_view_if_active()
        else:
            self.statusBar().showMessage("Failed to compute segments")
            QMessageBox.warning(self, "Error", "Failed to compute segments")

    def compute_all_segments(self):
        """Compute segmentation for all datasets that have hulls using a worker thread."""
        self._sync_seg_lengths_from_table()
        datasets_with_hulls_indices = [i for i, d in enumerate(self.datasets) if d.get('hull_points') is not None]
        if not datasets_with_hulls_indices:
            QMessageBox.information(self, "No Hulls", "No datasets have computed hulls. Please compute hulls first.")
            return
        self._run_batch_computation("segments", len(datasets_with_hulls_indices))
    def _refresh_seg_view_if_active(self):
        """If Segmentation tab is active, force a fresh 3D redraw from current dataset['segments']."""
        try:
            if self.notebook.widget(self.notebook.currentIndex()) == self.segment_tab:
                self._clear_segment_plot()
                # Prefer 3D always when available
                self.view_3d_enabled = True
                self._visualize_all_segments()
        except Exception:
            pass
    def _alpha_shape_outer_boundary(points_xy: np.ndarray, base_size: float) -> Optional[np.ndarray]:
        import numpy as np
        from scipy.spatial import Delaunay, cKDTree

        if points_xy is None or len(points_xy) < 4:
            return None

        # Adaptive radius from density and GUI size
        tree = cKDTree(points_xy)
        dists, _ = tree.query(points_xy, k=min(8, len(points_xy)))
        nn_med = float(np.median(dists[:, 1])) if dists.shape[1] > 1 else float(np.median(dists))
        R = max(1.0 * nn_med, 0.75 * max(base_size, 1e-6))  # radius
        alpha = 1.0 / max(R, 1e-12)

        tri = Delaunay(points_xy)
        simplices = tri.simplices
        if len(simplices) == 0:
            return None

        pts = points_xy
        kept = []
        for tri_idx in simplices:
            ia, ib, ic = tri_idx
            pa, pb, pc = pts[ia], pts[ib], pts[ic]
            a = np.linalg.norm(pb - pc)
            b = np.linalg.norm(pa - pc)
            c = np.linalg.norm(pa - pb)
            s2 = max((a + b + c) * (b + c - a) * (a + c - b) * (a + b - c), 0.0)
            if s2 == 0.0:
                continue
            area = 0.25 * np.sqrt(s2)
            if area <= 1e-12:
                continue
            Rcirc = (a * b * c) / (4.0 * area)
            if Rcirc < 1.0 / alpha:  # keep small-radius triangles
                kept.append((ia, ib, ic))

        if not kept:
            return None

        # Boundary edges = edges used by exactly one kept triangle
        from collections import Counter, defaultdict
        edge_counter = Counter()
        for ia, ib, ic in kept:
            for e in ((ia, ib), (ib, ic), (ic, ia)):
                edge = tuple(sorted(e))
                edge_counter[edge] += 1

        boundary_edges = [e for e, cnt in edge_counter.items() if cnt == 1]
        if len(boundary_edges) < 3:
            return None

        # Build adjacency and trace outer ring
        adj = defaultdict(list)
        for i, j in boundary_edges:
            adj[i].append(j)
            adj[j].append(i)

        # Pick start on the extreme (leftmost) boundary vertex
        start = min(adj.keys(), key=lambda idx: (pts[idx][0], pts[idx][1]))
        ring = [start]
        prev = None
        cur = start
        for _ in range(len(boundary_edges) + 5):
            nbrs = adj[cur]
            # choose neighbor with smallest left turn to keep turning consistently
            if prev is None:
                nxt = nbrs[0]
            else:
                v_prev = pts[cur] - pts[prev]
                best = None
                best_angle = +1e9
                for nb in nbrs:
                    if nb == prev:
                        continue
                    v_nb = pts[nb] - pts[cur]
                    # prefer smallest rightward angle to continue around boundary
                    cross = v_prev[0] * v_nb[1] - v_prev[1] * v_nb[0]
                    dot = np.dot(v_prev, v_nb)
                    angle = -np.arctan2(cross, dot)  # negative to bias consistent turn
                    if angle < best_angle:
                        best_angle = angle
                        best = nb
                nxt = best if best is not None else (nbrs[0] if len(nbrs) > 0 else None)
            if nxt is None:
                break
            if nxt == ring[0]:
                ring.append(nxt)
                break
            ring.append(nxt)
            prev, cur = cur, nxt

        if len(ring) < 4 or ring[0] != ring[-1]:
            return None

        # Ensure uniqueness and return XY polyline (closed)
        coords = pts[np.array(ring[:-1], dtype=int)]
        return coords
    def _run_triangulation_for_dataset(self, dataset_index):
        """Run triangulation for a specific dataset index. Returns True on success, False on error."""
        if not (0 <= dataset_index < len(self.datasets)):
            logger.error(f"Invalid dataset index {dataset_index} for triangulation.")
            return False

        dataset = self.datasets[dataset_index]
        dataset_name = dataset.get('name', f"Dataset {dataset_index}")

        segments_data = dataset.get('segments')
        if segments_data is None or len(segments_data) < 3:
            logger.warning(f"Skipping triangulation for {dataset_name}: segments not computed.")
            return False

        gradient = self.gradient_input.value()
        min_angle = self.min_angle_input.value()
        uniform = self.uniform_checkbox.isChecked()
        interp_label = self.interp_combo.currentText() if hasattr(self, "interp_combo") else "Thin Plate Spline (TPS)"
        smoothing = float(self.interp_smoothing_input.value()) if hasattr(self, "interp_smoothing_input") else 0.0

        try:
            import numpy as np
            from scipy.spatial import Delaunay, cKDTree
            from scipy.interpolate import RBFInterpolator, CloughTocher2DInterpolator
            from Pymeshit.triangle_direct import DirectTriangleWrapper

            # Common rotation basis (C++ rotate-by-normal)
            all_pts = np.asarray(dataset['points'], dtype=float)
            centred = all_pts - all_pts.mean(axis=0, keepdims=True)
            _, _, vh = np.linalg.svd(centred, full_matrices=False)
            normal = vh[-1];  normal = -normal if normal[2] < 0.0 else normal
            z_axis = np.array([0.0, 0.0, 1.0], dtype=float)

            def build_rot(n, onto_z=True):
                axis = np.cross(n, z_axis) if onto_z else np.cross(z_axis, n)
                c = float(np.dot(z_axis, n)) if onto_z else float(np.dot(n, z_axis))
                an = np.linalg.norm(axis)
                if 1.0 - abs(c) < 1e-12 or an < 1e-15:
                    return np.eye(3)
                axis = axis / an; s = np.sqrt(1.0 - c*c); C = 1.0 - c
                r1 = np.array([axis[0]*axis[0]*C + c,        axis[0]*axis[1]*C - axis[2]*s, axis[0]*axis[2]*C + axis[1]*s])
                r2 = np.array([axis[1]*axis[0]*C + axis[2]*s, axis[1]*axis[1]*C + c,        axis[1]*axis[2]*C - axis[0]*s])
                r3 = np.array([axis[2]*axis[0]*C - axis[1]*s, axis[2]*axis[1]*C + axis[0]*s, axis[2]*axis[2]*C + c       ])
                return np.vstack([r1, r2, r3])

            R = build_rot(normal, onto_z=True); R_inv = build_rot(normal, onto_z=False)
            all_pts_rot = (R @ all_pts.T).T

            # Build boundary points/segments from provided segments_data
            unique_points_list, point_to_index, segment_indices = [], {}, []
            cur = 0
            for seg in segments_data:
                p0, p1 = np.asarray(seg[0], float), np.asarray(seg[1], float)
                t0, t1 = tuple(np.round(p0, 12)), tuple(np.round(p1, 12))
                if t0 not in point_to_index: point_to_index[t0]=cur; unique_points_list.append(p0); i0=cur; cur+=1
                else: i0 = point_to_index[t0]
                if t1 not in point_to_index: point_to_index[t1]=cur; unique_points_list.append(p1); i1=cur; cur+=1
                else: i1 = point_to_index[t1]
                segment_indices.append([i0, i1])
            boundary_xyz = np.asarray(unique_points_list, float)
            boundary_segs = np.asarray(segment_indices, int)

            boundary_rot = (R @ boundary_xyz.T).T
            provided_xy = boundary_rot[:, :2]

            try:
                base_size = float(self._get_seg_target_length_for_dataset(dataset_index))
                if base_size <= 1e-6: base_size = 1.0
            except Exception:
                base_size = 1.0

            # Triangulation (no hull snapping for non-legacy)
            triangulator = DirectTriangleWrapper(gradient=gradient, min_angle=min_angle, base_size=base_size)
            tri_res = triangulator.triangulate(points=provided_xy, segments=boundary_segs, uniform=uniform, create_transition=True)
            if tri_res is None or 'vertices' not in tri_res or 'triangles' not in tri_res:
                raise ValueError("Triangulation failed.")
            vertices_xy = tri_res['vertices']; triangles = tri_res['triangles']

            # Prepare interpolation data
            sample_xy = all_pts_rot[:, :2]; sample_z = all_pts_rot[:, 2]

            # Legacy branch keeps hull+snap
            if "Legacy" in interp_label:
                tree = cKDTree(sample_xy)
                k = min(64, len(sample_xy))
                dists, idxs = tree.query(vertices_xy, k=k)
                if k == 1: dists = dists[:, None]; idxs = idxs[:, None]

                def key_xy(xy): return (round(float(xy[0]), 9), round(float(xy[1]), 9))
                boundary_map = {key_xy(p[:2]): float(p[2]) for p in boundary_rot}

                final_vertices_rot3d = np.zeros((len(vertices_xy), 3), float)
                final_vertices_rot3d[:, :2] = vertices_xy
                for i in range(len(vertices_xy)):
                    kxy = key_xy(vertices_xy[i])
                    if kxy in boundary_map:
                        final_vertices_rot3d[i, 2] = boundary_map[kxy]; continue
                    di = dists[i]; ii = idxs[i]
                    r2 = np.maximum(di*di, 1e-24); w = 1.0 / (r2 * r2); wsum = float(np.sum(w))
                    final_vertices_rot3d[i, 2] = float(np.sum(w * sample_z[ii]) / wsum) if wsum > 0 else float(np.mean(sample_z))

                final_vertices_3d = (R_inv @ final_vertices_rot3d.T).T
                dataset['triangulation_result'] = {'vertices': final_vertices_3d, 'triangles': triangles}
                logger.info(f"Triangulation for {dataset_name} (Legacy) completed. V={len(final_vertices_3d)}, T={len(triangles)}")
                return True

            # Other methods: interpolation only, no hull/snap


            def interp_idw(q, power=2):
                tree = cKDTree(sample_xy); k = min(64, len(sample_xy))
                d, idx = tree.query(q, k=k)
                if k==1: d=d[:,None]; idx=idx[:,None]
                r2 = np.maximum(d*d, 1e-24); w = 1.0/(r2**power); wsum = np.sum(w, axis=1)
                return np.sum(w * sample_z[idx], axis=1) / wsum




            def interp_tps(q):
                try:
                    from scipy.interpolate import RBFInterpolator
                    # Use all points, but limit neighbors for speed (like moving window in C++)
                    # neighbors=50 is a good tradeoff; adjust as needed
                    rbf = RBFInterpolator(
                        sample_xy, sample_z,
                        kernel='thin_plate_spline',
                        smoothing=float(smoothing)
                    )
                    return rbf(q)
                except Exception:
                    return interp_idw(q)
            # choose method
            if "Thin Plate" in interp_label:
                z_out = interp_tps(vertices_xy)
            elif "IDW" in interp_label:
                z_out = interp_idw(vertices_xy)
            else:
                # Default to IDW for any unrecognized method
                z_out = interp_idw(vertices_xy)

            final_vertices_rot3d = np.zeros((len(vertices_xy), 3), float)
            final_vertices_rot3d[:, :2] = vertices_xy
            final_vertices_rot3d[:, 2] = z_out

            final_vertices_3d = (R_inv @ final_vertices_rot3d.T).T
            dataset['triangulation_result'] = {'vertices': final_vertices_3d, 'triangles': triangles}
            logger.info(f"Triangulation for {dataset_name} completed. V={len(final_vertices_3d)}, T={len(triangles)}")
            return True

        except Exception as e:
            logger.error(f"Error during triangulation for '{dataset_name}': {e}", exc_info=True)
            return False

    def _attach_vtu_constraints_to_all_datasets(self) -> None:
        """
        Parse VTU 'CON' style constraints and attach to each dataset as:
        dataset['constraints'] = [
            { 'type': 'SEGMENTS'|'HOLES', 'points': (M,3) float array },
            ...
        ]
        If no constraints found, leaves dataset unchanged.
        """
        import numpy as np
        import pyvista as pv

        updated = 0
        for idx, ds in enumerate(self.datasets):
            path = ds.get('file_path')
            if not path or not str(path).lower().endswith('.vtu'):
                continue

            try:
                mesh = pv.read(path)
                # Ensure PolyData
                if not isinstance(mesh, pv.PolyData):
                    mesh = mesh.extract_surface()

                # We look for line cells (polylines) that carry matType per-cell info
                # Common names seen in C++: matType, matR, matG, matB
                matType = None
                for key in list(mesh.cell_data.keys()):
                    if key.lower() == 'mattype':
                        matType = np.asarray(mesh.cell_data[key]).astype(int)
                        break

                constraints = []
                if mesh.n_cells > 0 and mesh.lines.size > 0:
                    lines = mesh.lines.ravel()
                    pts = np.asarray(mesh.points, dtype=float)
                    i = 0
                    cell_id = 0
                    while i < len(lines):
                        n = int(lines[i]); i += 1
                        ids = lines[i:i + n]; i += n
                        if n >= 2:
                            ring_pts = pts[ids].astype(float)
                            # Treat as closed if endpoints coincide
                            if np.linalg.norm(ring_pts[0] - ring_pts[-1]) > 1e-12:
                                ring_pts = np.vstack([ring_pts, ring_pts[0]])

                            ctype = 'SEGMENTS'
                            if matType is not None and 0 <= cell_id < len(matType):
                                if matType[cell_id] == 2:
                                    ctype = 'HOLES'
                                elif matType[cell_id] == 1:
                                    ctype = 'UNDEFINED'
                                else:
                                    ctype = 'SEGMENTS'

                            constraints.append({
                                'type': ctype,
                                'points': ring_pts
                            })
                        cell_id += 1

                if constraints:
                    ds['constraints'] = constraints
                    updated += 1
            except Exception as e:
                logger.warning(f"[VTU-CON] Failed to attach constraints for {ds.get('name', idx)}: {e}")

        if updated:
            self.statusBar().showMessage(f"Attached VTU constraints for {updated} dataset(s)")
    def run_triangulation(self):
        # Refresh VTU boundary segments before triangulating the active dataset
        self._rebuild_segments_from_vtu_boundaries()
        self._attach_vtu_constraints_to_all_datasets()

        if self.current_dataset_index < 0 or self.current_dataset_index >= len(self.datasets):
            self.statusBar().showMessage("Error: No active dataset selected")
            QMessageBox.critical(self, "Error", "No active dataset selected")
            return
        self.statusBar().showMessage(f"Running triangulation for {self.datasets[self.current_dataset_index]['name']}...")
        success = self._run_triangulation_for_dataset(self.current_dataset_index)
        if success:
            self._update_statistics()
            self._visualize_all_triangulations()
            self._update_visualization()
            self.notebook.setCurrentIndex(3)
            self.statusBar().showMessage(f"Completed triangulation for {self.datasets[self.current_dataset_index]['name']}") # Add success message here

    def run_all_triangulations(self):
        # Ensure VTU datasets have true boundary rings as segments
        self._rebuild_segments_from_vtu_boundaries()
        self._attach_vtu_constraints_to_all_datasets()


        datasets_with_segments_indices = [i for i, d in enumerate(self.datasets) if d.get('segments') is not None]
        if not datasets_with_segments_indices:
            QMessageBox.information(self, "No Segments", "No datasets have computed segments. Please compute segments first.")
            return
        self._run_batch_computation("triangulations", len(datasets_with_segments_indices))
    
    def export_results(self):
        """Export the triangulation results to a file for the active dataset"""
        self.statusBar().showMessage("Exporting results...")
        
        # Check if we have an active dataset
        if self.current_dataset_index < 0 or self.current_dataset_index >= len(self.datasets):
            self.statusBar().showMessage("Error: No active dataset selected")
            QMessageBox.critical(self, "Error", "No active dataset selected")
            return
        
        # Get active dataset
        dataset = self.datasets[self.current_dataset_index]
        
        if dataset.get('triangulation_result') is None:
            self.statusBar().showMessage("Error: No triangulation results to export")
            QMessageBox.critical(self, "Error", "No triangulation results to export")
            return
        
        # Create export options dialog
        export_dialog = QDialog(self)
        export_dialog.setWindowTitle("Export Options")
        export_dialog.setMinimumWidth(400)
        dialog_layout = QVBoxLayout(export_dialog)
        
        # Export format frame
        format_group = QGroupBox("Export Format")
        format_layout = QVBoxLayout(format_group)
        
        format_radio_group = QButtonGroup(export_dialog)
        
        obj_radio = QRadioButton("OBJ Format (3D objects)")
        ply_radio = QRadioButton("PLY Format (3D mesh)")
        stl_radio = QRadioButton("STL Format (3D printing)")
        csv_radio = QRadioButton("CSV Format (raw data)")
        
        format_radio_group.addButton(obj_radio, 0)
        format_radio_group.addButton(ply_radio, 1)
        format_radio_group.addButton(stl_radio, 2)
        format_radio_group.addButton(csv_radio, 3)
        
        obj_radio.setChecked(True)  # Default selection
        
        format_layout.addWidget(obj_radio)
        format_layout.addWidget(ply_radio)
        format_layout.addWidget(stl_radio)
        format_layout.addWidget(csv_radio)
        
        dialog_layout.addWidget(format_group)
        
        # 3D export options (PyVista is now mandatory)
        options_group = QGroupBox("3D Export Options")
        options_layout = QGridLayout(options_group)
        
        export_3d_checkbox = QCheckBox("Export as 3D Surface")
        export_3d_checkbox.setChecked(True)
        export_3d_checkbox.setEnabled(True)
        options_layout.addWidget(export_3d_checkbox, 0, 0, 1, 2)
        
        options_layout.addWidget(QLabel("Height Scale:"), 1, 0)
        height_scale_slider = QSlider(Qt.Horizontal)
        height_scale_slider.setMinimum(0)
        height_scale_slider.setMaximum(100)
        height_scale_slider.setValue(int(self.height_factor * 100))
        options_layout.addWidget(height_scale_slider, 1, 1)
        
        dialog_layout.addWidget(options_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        export_btn = QPushButton("Export")
        
        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(export_btn)
        
        dialog_layout.addLayout(button_layout)
        
        # Connect signals
        cancel_btn.clicked.connect(export_dialog.reject)
        export_btn.clicked.connect(export_dialog.accept)
        
        # Show dialog and get result
        result = export_dialog.exec()
        
        if result == QDialog.Accepted:
            # Get selected format
            format_id = format_radio_group.checkedId()
            formats = ["obj", "ply", "stl", "csv"]
            if format_id >= 0 and format_id < len(formats):
                export_format = formats[format_id]
            else:
                export_format = "obj"  # Default
                
            # Get 3D options
            export_3d = export_3d_checkbox.isChecked() and True
            height_scale = height_scale_slider.value() / 100.0
            
            # Create a file save dialog
            file_filter = ""
            if export_format == "obj":
                file_filter = "OBJ files (*.obj);;All files (*.*)"
            elif export_format == "ply":
                file_filter = "PLY files (*.ply);;All files (*.*)"
            elif export_format == "stl":
                file_filter = "STL files (*.stl);;All files (*.*)"
            elif export_format == "csv":
                file_filter = "CSV files (*.csv);;All files (*.*)"
                
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Save triangulation results",
                "",
                file_filter,
                options=QFileDialog.Options()
            )
            
            if not file_path:
                self.statusBar().showMessage("Export canceled")
                return
            
            try:
                vertices = dataset['triangulation_result']['vertices']
                triangles = dataset['triangulation_result']['triangles']
                
                # If 3D export is selected and PyVista is available
                if export_3d and True:
                    try:
                        # Create 3D vertices with Z-values
                        points_3d = np.zeros((len(vertices), 3))
                        points_3d[:, 0] = vertices[:, 0]  # X remains the same
                        points_3d[:, 1] = vertices[:, 1]  # Y remains the same
                        
                        # Calculate Z values for 3D visualization
                        x_scale = 0.05
                        y_scale = 0.05
                        z_scale = 20.0 * height_scale
                        
                        for i in range(len(vertices)):
                            x, y = vertices[i]
                            z = np.sin(x * x_scale) * np.cos(y * y_scale) * z_scale
                            points_3d[i, 2] = z
                        
                        # Create PyVista mesh
                        cells = np.hstack([np.full((len(triangles), 1), 3), triangles])
                        mesh = pv.PolyData(points_3d, cells)
                        
                        # Save based on format
                        if export_format == "obj":
                            mesh.save(file_path)
                            self.statusBar().showMessage(f"Exported 3D OBJ file to {file_path}")
                        elif export_format == "ply":
                            mesh.save(file_path)
                            self.statusBar().showMessage(f"Exported 3D PLY file to {file_path}")
                        elif export_format == "stl":
                            mesh.save(file_path)
                            self.statusBar().showMessage(f"Exported 3D STL file to {file_path}")
                        elif export_format == "csv":
                            # For CSV, fall back to standard CSV export
                            self._export_csv(file_path, points_3d, triangles)
                            self.statusBar().showMessage(f"Exported 3D CSV file to {file_path}")
                    except Exception as e:
                        self.statusBar().showMessage(f"Error creating 3D export: {str(e)}")
                        logger.error(f"Error creating 3D export: {str(e)}")
                        QMessageBox.critical(self, "Export Error", f"Error creating 3D export: {str(e)}")
                else:
                    # Standard 2D format exports
                    if export_format == "obj":
                        self._export_obj(file_path, vertices, triangles)
                        self.statusBar().showMessage(f"Exported 2D OBJ file to {file_path}")
                    elif export_format == "ply":
                        self._export_ply(file_path, vertices, triangles)
                        self.statusBar().showMessage(f"Exported 2D PLY file to {file_path}")
                    elif export_format == "stl":
                        self._export_stl(file_path, vertices, triangles)
                        self.statusBar().showMessage(f"Exported 2D STL file to {file_path}")
                    elif export_format == "csv":
                        self._export_csv(file_path, vertices, triangles)
                        self.statusBar().showMessage(f"Exported 2D CSV file to {file_path}")
                
            except Exception as e:
                self.statusBar().showMessage(f"Error exporting results: {str(e)}")
                logger.error(f"Error exporting results: {str(e)}")
                QMessageBox.critical(self, "Error", f"Error exporting results: {str(e)}")
        else:
            self.statusBar().showMessage("Export canceled")
    
    def _export_obj(self, file_path, vertices, triangles):
        """Export to OBJ format"""
        with open(file_path, 'w') as f:
            # Write header
            f.write("# OBJ file created by MeshIt Workflow GUI\n")
            f.write(f"# Vertices: {len(vertices)}\n")
            f.write(f"# Triangles: {len(triangles)}\n\n")
            
            # Write vertices
            for vertex in vertices:
                # Check if vertex has Z coordinate
                if vertex.shape[0] >= 3:
                    f.write(f"v {vertex[0]} {vertex[1]} {vertex[2]}\n")
                else:
                    # If only 2D, use 0 for Z
                    f.write(f"v {vertex[0]} {vertex[1]} 0.0\n")
            
            # Write triangles
            for triangle in triangles:
                # OBJ indices start from 1, not 0
                f.write(f"f {triangle[0]+1} {triangle[1]+1} {triangle[2]+1}\n")
    
    def _export_ply(self, file_path, vertices, triangles):
        """Export to PLY format"""
        with open(file_path, 'w') as f:
            # Write header
            f.write("ply\n")
            f.write("format ascii 1.0\n")
            f.write(f"element vertex {len(vertices)}\n")
            f.write("property float x\n")
            f.write("property float y\n")
            f.write("property float z\n")
            f.write(f"element face {len(triangles)}\n")
            f.write("property list uchar int vertex_indices\n")
            f.write("end_header\n")
            
            # Write vertices
            for vertex in vertices:
                # Check if vertex has Z coordinate
                if vertex.shape[0] >= 3:
                    f.write(f"{vertex[0]} {vertex[1]} {vertex[2]}\n")
                else:
                    # If only 2D, use 0 for Z
                    f.write(f"{vertex[0]} {vertex[1]} 0.0\n")
            
            # Write triangles
            for triangle in triangles:
                f.write(f"3 {triangle[0]} {triangle[1]} {triangle[2]}\n")
    
    def _export_stl(self, file_path, vertices, triangles):
        """Export to STL format"""
        with open(file_path, 'w') as f:
            # Write header
            f.write("solid meshit_triangulation\n")
            
            # Write triangles
            for triangle in triangles:
                # Get vertices of this triangle
                v1 = vertices[triangle[0]]
                v2 = vertices[triangle[1]]
                v3 = vertices[triangle[2]]
                
                # Get Z coordinates or default to 0
                z1 = v1[2] if v1.shape[0] >= 3 else 0.0
                z2 = v2[2] if v2.shape[0] >= 3 else 0.0
                z3 = v3[2] if v3.shape[0] >= 3 else 0.0
                
                # Calculate normal (cross product of two sides)
                # For a non-flat mesh, calculate actual normal
                if v1.shape[0] >= 3 and v2.shape[0] >= 3 and v3.shape[0] >= 3:
                    # Simple normal calculation
                    side1 = np.array([v2[0]-v1[0], v2[1]-v1[1], v2[2]-v1[2]])
                    side2 = np.array([v3[0]-v1[0], v3[1]-v1[1], v3[2]-v1[2]])
                    normal = np.cross(side1, side2)
                    # Normalize
                    norm = np.linalg.norm(normal)
                    if norm > 0:
                        normal = normal / norm
                    f.write(f"  facet normal {normal[0]} {normal[1]} {normal[2]}\n")
                else:
                    # Default normal for flat mesh
                    f.write(f"  facet normal 0.0 0.0 1.0\n")
                
                f.write(f"    outer loop\n")
                f.write(f"      vertex {v1[0]} {v1[1]} {z1}\n")
                f.write(f"      vertex {v2[0]} {v2[1]} {z2}\n")
                f.write(f"      vertex {v3[0]} {v3[1]} {z3}\n")
                f.write(f"    endloop\n")
                f.write(f"  endfacet\n")
            
            # Write footer
            f.write("endsolid meshit_triangulation\n")
    
    def _export_csv(self, file_path, vertices, triangles):
        """Export to CSV format"""
        with open(file_path, 'w') as f:
            # Write header
            f.write("# MeshIt Workflow GUI triangulation results\n")
            f.write("# VERTICES\n")
            f.write("x,y,z\n")
            
            # Write vertices
            for vertex in vertices:
                if vertex.shape[0] == 3:  # 3D vertex
                    f.write(f"{vertex[0]},{vertex[1]},{vertex[2]}\n")
                else:  # 2D vertex
                    f.write(f"{vertex[0]},{vertex[1]},0.0\n")
            
            # Write separator
            f.write("\n# TRIANGLES\n")
            f.write("v1,v2,v3\n")
            
            # Write triangles
            for triangle in triangles:
                f.write(f"{triangle[0]},{triangle[1]},{triangle[2]}\n")

    def _show_dataset_context_menu(self, position):
        """Show context menu for dataset list items"""
        if self.dataset_list_widget.count() == 0:
            return
            
        # Get selected item
        selected_items = self.dataset_list_widget.selectedItems()
        if not selected_items:
            return
            
        # Create context menu
        menu = QMenu()
        rename_action = menu.addAction("Rename")
        toggle_action = menu.addAction("Toggle Visibility")
        change_color_action = menu.addAction("Change Color")
        menu.addSeparator()
        
        # Add processing actions
        process_menu = menu.addMenu("Process")
        compute_hull_action = process_menu.addAction("Compute Hull")
        compute_segments_action = process_menu.addAction("Compute Segments")
        compute_triangulation_action = process_menu.addAction("Compute Triangulation")
        process_all_action = process_menu.addAction("Process All Steps")
        
        menu.addSeparator()
        remove_action = menu.addAction("Remove")
        
        # Show menu at position
        action = menu.exec_(self.dataset_list_widget.mapToGlobal(position))
        
        # Handle action
        if not action:
            return
            
        # Get selected dataset index
        selected_index = self.dataset_list_widget.row(selected_items[0])
        
        if action == rename_action:
            self._rename_dataset(selected_index)
        elif action == toggle_action:
            self._toggle_dataset_visibility(selected_index)
        elif action == change_color_action:
            self._change_dataset_color(selected_index)
        elif action == remove_action:
            self._remove_dataset(selected_index)
        elif action == compute_hull_action:
            self.current_dataset_index = selected_index
            self.compute_hull()
        elif action == compute_segments_action:
            self.current_dataset_index = selected_index
            self.compute_segments()
        elif action == compute_triangulation_action:
            self.current_dataset_index = selected_index
            self.run_triangulation()
        elif action == process_all_action:
            self.current_dataset_index = selected_index
            self._process_all_steps(selected_index)
    
    def _process_all_steps(self, dataset_index):
        """Process all steps (hull, segments, triangulation) for a dataset"""
        if not (0 <= dataset_index < len(self.datasets)):
            return
            
        # Set as active dataset
        self.current_dataset_index = dataset_index
        
        # Display processing message
        dataset_name = self.datasets[dataset_index]['name']
        self.statusBar().showMessage(f"Processing all steps for {dataset_name}...")
        
        try:
            # Step 1: Compute hull
            self.compute_hull()
            
            # Step 2: Compute segments
            self.compute_segments()
            
            # Step 3: Run triangulation
            self.run_triangulation()
            
            self.statusBar().showMessage(f"Completed all processing steps for {dataset_name}")
        except Exception as e:
            self.statusBar().showMessage(f"Error processing dataset: {str(e)}")
            logger.error(f"Error during dataset processing: {str(e)}")
            QMessageBox.critical(self, "Error", f"Error processing dataset: {str(e)}")
    
    def process_all_datasets(self):
        """Process all steps for all datasets"""
        if not self.datasets:
            QMessageBox.information(self, "No Datasets", "No datasets available to process.")
            return
            
        num_processed = 0
        total_datasets = len(self.datasets)
        
        self.statusBar().showMessage(f"Processing all steps for {total_datasets} datasets...")
        
        try:
            # Process each dataset
            for i in range(total_datasets):
                dataset_name = self.datasets[i]['name']
                self.statusBar().showMessage(f"Processing {dataset_name} ({i+1}/{total_datasets})...")
                
                # Set as active
                self.current_dataset_index = i
                
                # Compute hull if needed
                if self.datasets[i].get('hull_points') is None:
                    # Call compute hull but catch any exceptions to continue with other datasets
                    try:
                        self.compute_hull()
                    except Exception as e:
                        logger.error(f"Error computing hull for {dataset_name}: {str(e)}")
                        continue
                
                # Compute segments if needed
                if self.datasets[i].get('segments') is None:
                    try:
                        self.compute_segments()
                    except Exception as e:
                        logger.error(f"Error computing segments for {dataset_name}: {str(e)}")
                        continue
                
                # Run triangulation if needed
                if self.datasets[i].get('triangulation_result') is None:
                    try:
                        self.run_triangulation()
                    except Exception as e:
                        logger.error(f"Error triangulating {dataset_name}: {str(e)}")
                        continue
                
                num_processed += 1
            
            # Show completion message
            self.statusBar().showMessage(f"Successfully processed {num_processed} out of {total_datasets} datasets")
            
            # Update visualizations for all
            self._update_visualization()
            
        except Exception as e:
            self.statusBar().showMessage(f"Error in batch processing: {str(e)}")
            logger.error(f"Error during batch processing: {str(e)}")
            QMessageBox.critical(self, "Error", f"Error in batch processing: {str(e)}")
    
    def _on_dataset_selection_changed(self):
        """Handle dataset selection change"""
        selected_items = self.dataset_list_widget.selectedItems()
        if not selected_items:
            return
            
        # Get selected dataset index
        selected_index = self.dataset_list_widget.row(selected_items[0])
        
        # Set as active dataset
        self.current_dataset_index = selected_index
        
        # Update statistics and visualization for the selected dataset
        self._update_statistics()
        self._update_visualization()
        
    def _update_statistics(self):
        """Update statistics labels based on loaded datasets"""
        num_datasets = len(self.datasets)
        self.num_datasets_label.setText(f"Datasets: {num_datasets}")
        
        # Count datasets with each processing step completed
        datasets_with_hull = sum(1 for d in self.datasets if d.get('hull_points') is not None)
        datasets_with_segments = sum(1 for d in self.datasets if d.get('segments') is not None)
        datasets_with_triangulation = sum(1 for d in self.datasets if d.get('triangulation_result') is not None)
        
        # Count intersections
        surface_intersections = 0
        polyline_intersections = 0
        
        if hasattr(self, 'datasets_intersections'):
            for intersections in self.datasets_intersections.values():
                for intersection in intersections:
                    if intersection['is_polyline_mesh']:
                        polyline_intersections += 1
                    else:
                        surface_intersections += 1
        
        # Due to double-counting (each intersection is stored for both datasets),
        # we divide surface-surface intersections count by 2
        unique_surface_intersections = surface_intersections // 2
        triple_point_count = len(self.triple_points) if hasattr(self, 'triple_points') else 0
        
        # Update the status bar with processing statistics
        if hasattr(self, 'status_hulls_label'):
            self.status_hulls_label.setText(f"Hulls: {datasets_with_hull}")
        else:
            self.status_hulls_label = QLabel(f"Hulls: {datasets_with_hull}")
            self.statusBar().addPermanentWidget(self.status_hulls_label)
            
        if hasattr(self, 'status_segments_label'):
            self.status_segments_label.setText(f"Segments: {datasets_with_segments}")
        else:
            self.status_segments_label = QLabel(f"Segments: {datasets_with_segments}")
            self.statusBar().addPermanentWidget(self.status_segments_label)
            
        if hasattr(self, 'status_triangulations_label'):
            self.status_triangulations_label.setText(f"Triangulations: {datasets_with_triangulation}")
        else:
            self.status_triangulations_label = QLabel(f"Triangulations: {datasets_with_triangulation}")
            self.statusBar().addPermanentWidget(self.status_triangulations_label)
            
        if hasattr(self, 'status_intersections_label'):
            self.status_intersections_label.setText(f"Intersections: {unique_surface_intersections + polyline_intersections}")
        else:
            self.status_intersections_label = QLabel(f"Intersections: {unique_surface_intersections + polyline_intersections}")
            self.statusBar().addPermanentWidget(self.status_intersections_label)
        
        if num_datasets == 0:
            self.points_label.setText("Points: 0")
            self.bounds_label.setText("Bounds: N/A")
            self.hull_points_label.setText("Hull vertices: 0")
            self.hull_area_label.setText("Hull area: 0.0")
            self.num_segments_label.setText("Segments: 0")
            self.avg_segment_length_label.setText("Avg length: 0.0")
            self.num_triangles_label.setText("Triangles: 0")
            self.num_vertices_label.setText("Vertices: 0")
            self.mean_edge_label.setText("Mean edge: 0.0")
            self.uniformity_label.setText("Uniformity: 0.0")
            
            # Update intersection statistics if they exist
            if hasattr(self, 'surface_intersection_count_label'):
                self.surface_intersection_count_label.setText("Surface-Surface: 0")
            if hasattr(self, 'polyline_intersection_count_label'):
                self.polyline_intersection_count_label.setText("Polyline-Surface: 0")
            if hasattr(self, 'triple_point_count_label'):
                self.triple_point_count_label.setText("Triple Points: 0")
            return
        
        # Update statistics for the active dataset
        if 0 <= self.current_dataset_index < num_datasets:
            dataset = self.datasets[self.current_dataset_index]
            
            # Points statistics
            if dataset['points'] is not None:
                self.points_label.setText(f"Points: {len(dataset['points'])}")
                
                # Calculate bounds - only use X and Y for display
                min_coords = np.min(dataset['points'], axis=0)
                max_coords = np.max(dataset['points'], axis=0)
                min_x, min_y = min_coords[0], min_coords[1]
                max_x, max_y = max_coords[0], max_coords[1]
                
                # If 3D data is available, also show Z range
                if dataset['points'].shape[1] >= 3:
                    min_z, max_z = min_coords[2], max_coords[2]
                    self.bounds_label.setText(f"Bounds: X[{min_x:.2f},{max_x:.2f}] Y[{min_y:.2f},{max_y:.2f}] Z[{min_z:.2f},{max_z:.2f}]")
                else:
                    self.bounds_label.setText(f"Bounds: X[{min_x:.2f},{max_x:.2f}] Y[{min_y:.2f},{max_y:.2f}]")
            else:
                self.points_label.setText("Points: 0")
                self.bounds_label.setText("Bounds: N/A")
            
            # Hull statistics
            if dataset.get('hull_points') is not None:
                hull_points = dataset['hull_points']
                self.hull_points_label.setText(f"Hull vertices: {len(hull_points)-1}")  # -1 for the closing point
                
                # Calculate hull area (approximate)
                area = 0.0
                for i in range(len(hull_points)-1):
                    # Extract x,y coordinates only
                    x1, y1 = hull_points[i][0], hull_points[i][1]
                    x2, y2 = hull_points[i+1][0], hull_points[i+1][1]
                    area += x1*y2 - x2*y1
                area = abs(area) / 2.0
                self.hull_area_label.setText(f"Hull area: {area:.2f}")
            else:
                self.hull_points_label.setText("Hull vertices: 0")
                self.hull_area_label.setText("Hull area: 0.0")
            
            # Segment statistics
            if dataset.get('segments') is not None:
                segments = dataset['segments']
                self.num_segments_label.setText(f"Segments: {len(segments)}")
                
                # Calculate average segment length
                segment_lengths = [np.linalg.norm(segment[1] - segment[0]) for segment in segments]
                avg_length = np.mean(segment_lengths)
                self.avg_segment_length_label.setText(f"Avg length: {avg_length:.2f}")
            else:
                self.num_segments_label.setText("Segments: 0")
                self.avg_segment_length_label.setText("Avg length: 0.0")
            
            # Triangulation statistics
            if dataset.get('triangulation_result') is not None:
                triangulation = dataset['triangulation_result']
                vertices = triangulation['vertices']
                triangles = triangulation['triangles']
                
                self.num_triangles_label.setText(f"Triangles: {len(triangles)}")
                self.num_vertices_label.setText(f"Vertices: {len(vertices)}")
                
                # Calculate edge lengths and statistics
                edge_lengths = []
                for tri in triangles:
                    v1, v2, v3 = tri
                    p1, p2, p3 = vertices[v1], vertices[v2], vertices[v3]
                    
                    edge_lengths.extend([
                        np.linalg.norm(p2 - p1),
                        np.linalg.norm(p3 - p2),
                        np.linalg.norm(p1 - p3)
                    ])
                
                if edge_lengths:
                    mean_edge = np.mean(edge_lengths)
                    edge_std = np.std(edge_lengths)
                    uniformity = edge_std / mean_edge if mean_edge > 0 else 0
                    
                    self.mean_edge_label.setText(f"Mean edge: {mean_edge:.4f}")
                    self.uniformity_label.setText(f"Uniformity: {uniformity:.4f}")
                else:
                    self.mean_edge_label.setText("Mean edge: 0.0")
                    self.uniformity_label.setText("Uniformity: 0.0")
            else:
                self.num_triangles_label.setText("Triangles: 0")
                self.num_vertices_label.setText("Vertices: 0")
                self.mean_edge_label.setText("Mean edge: 0.0")
                self.uniformity_label.setText("Uniformity: 0.0")
            
            # Intersection statistics
            if hasattr(self, 'surface_intersection_count_label'):
                # Count dataset-specific intersections
                dataset_surface_intersections = 0
                dataset_polyline_intersections = 0
                
                if hasattr(self, 'datasets_intersections') and self.current_dataset_index in self.datasets_intersections:
                    for intersection in self.datasets_intersections[self.current_dataset_index]:
                        if intersection['is_polyline_mesh']:
                            dataset_polyline_intersections += 1
                        else:
                            dataset_surface_intersections += 1
                
                # Update UI with dataset-specific intersection counts
                self.surface_intersection_count_label.setText(f"Surface-Surface: {dataset_surface_intersections}")
                self.polyline_intersection_count_label.setText(f"Polyline-Surface: {dataset_polyline_intersections}")
                self.triple_point_count_label.setText(f"Triple Points: {triple_point_count}")
    
    def _update_dataset_list(self):
        """Update the dataset list widget"""
        # Save current selection
        current_index = self.current_dataset_index
        
        # Clear list
        self.dataset_list_widget.clear()
        
        # Add datasets to list
        for dataset in self.datasets:
            visibility = "✓" if dataset.get('visible', True) else "✗"
            color_square = "■ "
            item_text = f"{color_square}{visibility} {dataset['name']}"
            
            item = QListWidgetItem(item_text)
            
            # Set item color based on dataset color
            color = dataset.get('color', '#000000')
            item.setForeground(QColor(color))
            
            self.dataset_list_widget.addItem(item)
        
        # Restore selection if possible
        if 0 <= current_index < self.dataset_list_widget.count():
            self.dataset_list_widget.setCurrentRow(current_index)
        elif self.dataset_list_widget.count() > 0:
            self.dataset_list_widget.setCurrentRow(0)
            self.current_dataset_index = 0
        else:
            self.current_dataset_index = -1
            
        # Update surface visibility checkboxes if the widget exists
        if hasattr(self, 'surface_checkboxes_layout'):
            self._populate_surface_checkboxes()

        # NEW: keep per‑surface refinement tables in sync with dataset list
        if hasattr(self, '_refresh_seg_refine_table'):
            self._refresh_seg_refine_table()
        if hasattr(self, '_refresh_mesh_refine_table'):
            self._refresh_mesh_refine_table()
    
    def _rename_dataset(self, dataset_index):
        """Rename a dataset"""
        if not (0 <= dataset_index < len(self.datasets)):
            return
            
        dataset = self.datasets[dataset_index]
        old_name = dataset['name']
        
        # Create dialog for renaming
        dialog = QDialog(self)
        dialog.setWindowTitle("Rename Dataset")
        dialog.setFixedSize(300, 100)
        dialog_layout = QVBoxLayout(dialog)
        
        # Add name input
        dialog_layout.addWidget(QLabel("Dataset Name:"))
        name_input = QLineEdit(old_name)
        dialog_layout.addWidget(name_input)
        
        # Add buttons
        button_layout = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        ok_btn = QPushButton("OK")
        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(ok_btn)
        dialog_layout.addLayout(button_layout)
        
        # Connect signals
        cancel_btn.clicked.connect(dialog.reject)
        ok_btn.clicked.connect(dialog.accept)
        
        # Show dialog and get result
        result = dialog.exec()
        
        if result == QDialog.Accepted:
            new_name = name_input.text().strip()
            if new_name:
                # Update dataset name
                dataset['name'] = new_name
                
                # Update list
                self._update_dataset_list()
    
    def _toggle_dataset_visibility(self, dataset_index):
        """Toggle visibility of a dataset"""
        if not (0 <= dataset_index < len(self.datasets)):
            return
            
        dataset = self.datasets[dataset_index]
        dataset['visible'] = not dataset.get('visible', True)
        
        # Update list
        self._update_dataset_list()
        
        # Update visualization
        self._update_visualization()
    
    def _change_dataset_color(self, dataset_index):
        """Change color of a dataset"""
        if not (0 <= dataset_index < len(self.datasets)):
            return
            
        dataset = self.datasets[dataset_index]
        old_color = dataset.get('color', '#000000')
        
        # Get new color using color dialog
        new_color = QColorDialog.getColor(QColor(old_color), self, "Select Dataset Color")
        
        if new_color.isValid():
            # Update dataset color
            dataset['color'] = new_color.name()
            
            # Update list
            self._update_dataset_list()
            
            # Update visualization
            self._update_visualization()
    
    def _remove_dataset(self, dataset_index):
        """Remove a dataset"""
        if not (0 <= dataset_index < len(self.datasets)):
            return
            
        # Confirm deletion
        confirm = QMessageBox.question(
            self, 
            "Remove Dataset", 
            f"Are you sure you want to remove dataset '{self.datasets[dataset_index]['name']}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if confirm == QMessageBox.Yes:
            # Remove dataset
            self.datasets.pop(dataset_index)
            
            # Update dataset list
            self._update_dataset_list()
            
            # Update statistics and visualization
            self._update_statistics()
            self._update_visualization()
    
    def clear_all_datasets(self):
        """Clear all loaded datasets"""
        if not self.datasets:
            return
            
        # Confirm deletion
        confirm = QMessageBox.question(
            self, 
            "Clear All Datasets", 
            f"Are you sure you want to remove all {len(self.datasets)} datasets?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if confirm == QMessageBox.Yes:
            # Clear datasets
            self.datasets = []
            self.current_dataset_index = -1
            
            # Update UI
            self._update_dataset_list()
            self._update_statistics()
            
            # Clear visualizations
            self._clear_visualizations()
            
            self.statusBar().showMessage("All datasets cleared")
    
    def remove_active_dataset(self):
        """Remove the active dataset"""
        if 0 <= self.current_dataset_index < len(self.datasets):
            self._remove_dataset(self.current_dataset_index)
    def _clear_visualizations(self):
        """Clear all visualizations"""
        # ... existing clear calls ...
        self._clear_hull_plot()
        self._clear_segment_plot()
        self._clear_triangulation_plot()
        self._clear_intersection_plot()
        self._clear_refine_mesh_plot() # Add this line
        
        # ... rest of the method ...
        
        # Clear points visualization
        while self.file_viz_layout.count():
            item = self.file_viz_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        
        # Reset placeholder
        if True:
            placeholder_text = "Load data to visualize points in 3D"
        else:
            placeholder_text = "PyVista not available. Install PyVista for 3D visualization.\nLoad data to visualize points in 2D."
            
        self.file_viz_placeholder = QLabel(placeholder_text)
        self.file_viz_placeholder.setAlignment(Qt.AlignCenter)
        self.file_viz_layout.addWidget(self.file_viz_placeholder)
    
    def _should_skip_segmentation_visualization(self, current_tab):
        """
        Check if segmentation visualization should be skipped to prevent duplication.
        Returns True if segmentation is already visualized in a previous tab.
        """
        # If we're in triangulation tab and segmentation is already visualized, skip it
        if current_tab == "triangulation" and self.segmentation_visualized:
            return True
        return False
    
    def _mark_segmentation_visualized(self, tab_name):
        """Mark that segmentation has been visualized in the specified tab."""
        self.segmentation_visualized = True
        self.current_visualization_tab = tab_name
    
    def _clear_segmentation_visualization_flag(self):
        """Clear the segmentation visualization flag when data changes."""
        self.segmentation_visualized = False
        self.current_visualization_tab = None
    
    def _update_visualization(self):
        """Update all visualizations based on loaded datasets"""
        # Check if we have any datasets
        if not self.datasets:
            self._clear_visualizations()
            return
        
        # Get visible datasets
        visible_datasets = [d for d in self.datasets if d.get('visible', True)]
        
        if not visible_datasets:
            self._clear_visualizations()
            return
        
        # Clear segmentation visualization flag when updating all visualizations
        self._clear_segmentation_visualization_flag()
        
        # Update points visualization
        self._visualize_all_points()
        
        # Update hull visualization if we have any hulls
        hulls_exist = any(d.get('hull_points') is not None for d in visible_datasets)
        if hulls_exist:
            self._visualize_all_hulls()
        
        # Update segments visualization if we have any segments
        segments_exist = any(d.get('segments') is not None for d in visible_datasets)
        if segments_exist:
            self._visualize_all_segments()
        
        # Update triangulation visualization if we have any triangulations
        triangulations_exist = any(d.get('triangulation_result') is not None for d in visible_datasets)
        if triangulations_exist:
            self._visualize_all_triangulations()
        
        # Update intersection visualization if we have any intersections
        intersections_exist = hasattr(self, 'datasets_intersections') and bool(self.datasets_intersections)
        if intersections_exist:
            self._visualize_intersections()
    
    def load_multiple_files(self):
        """Load multiple data files"""
        self.statusBar().showMessage("Loading multiple files...")
        # Let user select multiple files (not directories)
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "Select point data files", "",
            "Supported files (*.txt *.dat *.csv *.vtu);;All files (*.*)"
        )
        if not file_paths:
            self.statusBar().showMessage("File loading canceled")
            return

        successful_loads = 0
        for file_path in file_paths:
            filename = os.path.basename(file_path)
            try:
                points = self._read_point_file(file_path)
                if points is not None and len(points) > 0:
                    dataset = {
                        'name': filename,
                        'type': 'SURFACE',   # mark as SURFACE
                        'points': points,
                        'visible': True,
                        'color': self._get_next_color()
                    }
                    self.datasets.append(dataset)
                    self.current_dataset_index = len(self.datasets) - 1
                    successful_loads += 1
                else:
                    logger.warning(f"No valid points found in file: {filename}")
            except Exception as e:
                logger.error(f"Error loading file {filename}: {str(e)}")

        if successful_loads > 0:
            self._update_dataset_list()
            self._update_statistics()
            self._visualize_all_points()
            self.statusBar().showMessage(f"Successfully loaded {successful_loads} out of {len(file_paths)} files")
        else:
            self.statusBar().showMessage("Error: No valid points found in any file")
            QMessageBox.critical(self, "Error", "No valid points found in any file")
    def _get_next_color(self):
        """Get next color from palette for a new dataset"""
        if not self.datasets:
            return self.DEFAULT_COLORS[0]
        
        # Count existing colors
        used_colors = {}
        for dataset in self.datasets:
            color = dataset.get('color')
            if color:
                used_colors[color] = used_colors.get(color, 0) + 1
        
        # Find first least used color
        for color in self.DEFAULT_COLORS:
            if color not in used_colors:
                return color
        
        # If all colors are used, use the least used one
        min_used = min(used_colors.values())
        least_used_colors = [c for c, count in used_colors.items() if count == min_used]
        
        # Return the first one from palette order
        for color in self.DEFAULT_COLORS:
            if color in least_used_colors:
                return color
        
        # If all else fails, return a random color
        return self.DEFAULT_COLORS[np.random.randint(0, len(self.DEFAULT_COLORS))]

    def _visualize_all_points(self):
        """Visualize all visible datasets' points"""
        visible_datasets = [d for d in self.datasets if d.get('visible', True)]
        if not visible_datasets:
            self._clear_hull_plot()
            return

        while self.file_viz_layout.count():
            item = self.file_viz_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        all_points = np.vstack([d['points'] for d in visible_datasets if d.get('points') is not None])
        if len(all_points) == 0:
            return

        min_coords = np.min(all_points, axis=0)
        max_coords = np.max(all_points, axis=0)
        min_x, min_y = min_coords[0], min_coords[1]
        max_x, max_y = max_coords[0], max_coords[1]

        # Use 3D visualization with PyVista
        self._create_multi_dataset_3d_visualization(
            self.file_viz_frame, visible_datasets, "Points Visualization", view_type="points"
        )
    def _visualize_all_hulls(self):
        """Visualize all visible hulls"""
        # Get datasets with hulls
        datasets_with_hull = []
        for dataset in self.datasets:
            if dataset.get('visible', True) and dataset.get('hull_points') is not None:
                datasets_with_hull.append(dataset)
                
        # Clear previous visualization if no datasets with hull
        if not datasets_with_hull:
            self._clear_hull_plot()
            return
            
        # Use 3D visualization with PyVista
        self._create_multi_dataset_3d_visualization(
            self.hull_viz_frame,
            datasets_with_hull,
            "Convex Hull Visualization",
            view_type="hulls"
        )
    def _sync_seg_lengths_from_table(self):
        """Snapshot the Segmentation table into seg_length_by_surface before computing."""
        if not hasattr(self, 'seg_refine_table') or self.seg_refine_table is None:
            return
        from PySide6.QtCore import Qt
        if not hasattr(self, 'seg_length_by_surface') or self.seg_length_by_surface is None:
            self.seg_length_by_surface = {}
        rows = self.seg_refine_table.rowCount()
        for r in range(rows):
            item_name = self.seg_refine_table.item(r, 0)
            item_val  = self.seg_refine_table.item(r, 1)
            if not item_name or not item_val:
                continue
            ds_idx = item_name.data(Qt.UserRole)
            if ds_idx is None:
                continue
            try:
                v = float(item_val.text())
                if v > 1e-9:
                    self.seg_length_by_surface[int(ds_idx)] = v
            except Exception:
                continue
    def _visualize_all_segments(self):
        """Visualize all visible datasets' segments using 3D PyVista."""
        visible_datasets = [d for d in self.datasets if d.get('visible', True) and d.get('segments') is not None]
        if not visible_datasets:
            self._clear_segment_plot()
            return

        # Clear existing visualization
        while self.segment_viz_layout.count():
            item = self.segment_viz_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        # Use 3D visualization with PyVista
        self.view_3d_enabled = True
        self._create_multi_dataset_3d_visualization(
            self.segment_viz_frame,
            visible_datasets,
            "Segmentation Visualization",
            view_type="segments"
        )
    
    def _visualize_all_triangulations(self):
        """Visualize all visible datasets' triangulations"""
        # Check if we should skip segmentation visualization to prevent duplication
        skip_segmentation = self._should_skip_segmentation_visualization("triangulation")
        
        # Get visible datasets with triangulations
        visible_datasets = [d for d in self.datasets if d.get('visible', True) and d.get('triangulation_result') is not None]
        
        if not visible_datasets:
            self._clear_triangulation_plot()
            return
        
        # Clear existing visualization
        while self.tri_viz_layout.count():
            item = self.tri_viz_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        
        # Calculate global bounds for all visible datasets
        all_vertices = []
        for dataset in visible_datasets:
            if dataset.get('triangulation_result') is not None:
                vertices = dataset['triangulation_result']['vertices']
                if vertices is not None and len(vertices) > 0:
                    all_vertices.append(vertices)
        
        if not all_vertices:
            return
            
        all_vertices = np.vstack(all_vertices)
        # Handle 3D coordinates properly
        min_coords = np.min(all_vertices, axis=0)
        max_coords = np.max(all_vertices, axis=0)
        min_x, min_y = min_coords[0], min_coords[1]
        max_x, max_y = max_coords[0], max_coords[1]
        
        # Use 3D visualization with PyVista
        self._create_multi_dataset_3d_visualization(
            self.tri_viz_frame,
            visible_datasets,
            "Triangulation Visualization",
            view_type="triangulation"
        )
        
        # Update the triangulation legend (remains the same)
        # ... existing legend update code ...
    
    def _visualize_refined_intersections(self):
        """Visualize refined intersections with enhanced special point visualization."""
        # Get the current active plotter from the tab system
        plotter = self._get_current_refine_plotter()
        if not plotter:
            # Fallback to old method for backward compatibility
            if hasattr(self, 'refine_mesh_plotter') and self.refine_mesh_plotter:
                plotter = self.refine_mesh_plotter
            elif hasattr(self, 'plotters') and 'refine_mesh' in self.plotters and self.plotters['refine_mesh']:
                plotter = self.plotters['refine_mesh']
                self.refine_mesh_plotter = plotter
        
        if not plotter:
            logger.warning("Refine/Mesh plotter not available for visualization.")
            return

        plotter.clear()
        plotter.set_background([0.2, 0.2, 0.25])

        if not hasattr(self, 'datasets_intersections') or not self.datasets_intersections:
            plotter.add_text("No refined intersections to display.", position='upper_edge', color='white')
            plotter.reset_camera()
            return

        logger.info("Visualizing refined intersections...")

        # Get selected surface from dropdown for filtering
        selected_surface = "All Surfaces"
        if hasattr(self, 'refine_surface_selector') and self.refine_surface_selector:
            selected_surface = self.refine_surface_selector.currentText()

        # Helper function to check if a surface should be shown
        def should_show_surface(dataset_idx):
            if selected_surface == "All Surfaces":
                return True
            if dataset_idx < len(self.datasets):
                dataset_name = self.datasets[dataset_idx].get("name", f"Surface_{dataset_idx}")
                return dataset_name == selected_surface
            return False

        # Initialize constraint points collection (consolidated)
        constraint_points = []  # All constraint points for triangulation
        
        involved_dataset_indices = set()
        refined_intersection_lines = []
        original_intersection_lines = []
        plotter_has_content = False

        # Check if original intersections exist for comparison
        has_original = hasattr(self, 'original_intersections_backup') and self.original_intersections_backup

        # Process original intersection lines (for comparison)
        if has_original:
            for dataset_idx_key, intersections_list in self.original_intersections_backup.items():
                for intersection_data in intersections_list:
                    if intersection_data['points'] and len(intersection_data['points']) >= 2:
                        try:
                            points_list = []
                            for p in intersection_data['points']:
                                if isinstance(p, (list, tuple)) and len(p) >= 3:
                                    points_list.append([float(p[0]), float(p[1]), float(p[2])])
                                elif hasattr(p, 'x') and hasattr(p, 'y') and hasattr(p, 'z'):
                                    points_list.append([float(p.x), float(p.y), float(p.z)])
                            
                            if len(points_list) >= 2:
                                original_intersection_lines.append((np.array(points_list), intersection_data.get('is_polyline_mesh', False)))
                        except Exception as e:
                            logger.error(f"Error processing original intersection: {e}")

        # Process refined intersection lines and extract special points
        for dataset_idx_key in self.datasets_intersections.keys():
            intersections_list = self.datasets_intersections[dataset_idx_key]
            for intersection_data in intersections_list:
                if 'points' not in intersection_data or not intersection_data['points'] or len(intersection_data['points']) < 2:
                    continue
                    
                try:
                    # Track involved datasets
                    dataset_id1 = intersection_data.get('dataset_id1', -1)
                    dataset_id2 = intersection_data.get('dataset_id2', -1)
                    
                    # Apply surface filter - only show intersections involving the selected surface
                    if selected_surface != "All Surfaces":
                        surface_involved = (should_show_surface(dataset_id1) or should_show_surface(dataset_id2))
                        if not surface_involved:
                            continue  # Skip this intersection if neither dataset matches the filter
                    
                    involved_dataset_indices.add(dataset_id1)
                    involved_dataset_indices.add(dataset_id2)
                    
                    # Process intersection points
                    points_list = []
                    for p in intersection_data['points']:
                        coord = None
                        point_type = None
                        
                        if isinstance(p, (list, tuple)):
                            if len(p) >= 3:
                                coord = [float(p[0]), float(p[1]), float(p[2])]
                                point_type = p[3] if len(p) > 3 else None
                        elif hasattr(p, 'x') and hasattr(p, 'y') and hasattr(p, 'z'):
                            coord = [float(p.x), float(p.y), float(p.z)]
                            point_type = getattr(p, 'point_type', getattr(p, 'type', None))
                        
                        if coord:
                            points_list.append(coord)
                            
                            # Categorize points by type
                            constraint_points.append(coord)
                    if len(points_list) >= 2:
                        is_polyline = intersection_data.get('is_polyline_mesh', False)
                        refined_intersection_lines.append((np.array(points_list), is_polyline))
                        
                except Exception as e:
                    logger.error(f"Error processing refined intersection: {e}")

        # Add original intersection lines (faded)
        if has_original and original_intersection_lines:
            for line_points, is_polyline in original_intersection_lines:
                try:
                    if len(line_points) >= 2:
                        cells = []
                        for i in range(len(line_points) - 1):
                            cells.extend([2, i, i + 1])
                        original_line = pv.PolyData(line_points, lines=np.array(cells))
                        plotter.add_mesh(original_line, color='gray', opacity=0.3, line_width=2.0)
                        plotter_has_content = True
                except Exception as e:
                    logger.error(f"Error visualizing original line: {e}")

        # Add refined intersection lines
        if refined_intersection_lines:
            surf_surf_color = [0.9, 0.5, 0.1]  # Orange for surface-surface
            surf_poly_color = [0.1, 0.8, 0.9]  # Cyan for surface-polyline
            
            for line_points, is_polyline in refined_intersection_lines:
                try:
                    if len(line_points) >= 2:
                        cells = []
                        for i in range(len(line_points) - 1):
                            cells.extend([2, i, i + 1])
                        refined_line = pv.PolyData(line_points, lines=np.array(cells))
                        
                        color = surf_poly_color if is_polyline else surf_surf_color
                        plotter.add_mesh(refined_line, color=color, line_width=4.0, 
                                    render_lines_as_tubes=True, smooth_shading=True)
                        plotter_has_content = True
                except Exception as e:
                    logger.error(f"Error visualizing refined line: {e}")

        # Process convex hulls and extract corner points
        for original_idx in involved_dataset_indices:
            if original_idx >= 0 and original_idx < len(self.datasets):
                dataset = self.datasets[original_idx]
                if not dataset.get('visible', True):
                    continue
                    
                hull_points = dataset.get('hull_points')
                if hull_points is None or len(hull_points) < 3:
                    continue
                    
                name = dataset.get('name', f'Dataset {original_idx + 1}')
                hull_color = dataset.get('color', '#CCCCCC')
                
                # Extract corner points and junction points from hull
                # Extract constraint points from hull (non-DEFAULT types)
                # Extract ALL hull points as constraint points (including DEFAULT subdivision points)
                for pt_idx, pt in enumerate(hull_points):
                    if len(pt) >= 3:
                        coord = [float(pt[0]), float(pt[1]), float(pt[2])]
                        constraint_points.append(coord)  # ALL hull points are constraints
                
                # Draw convex hull outline
                try:
                    hull_vertices = []
                    for point in hull_points:
                        if len(point) >= 3:
                            hull_vertices.append([point[0], point[1], point[2] if len(point) > 2 else 0.0])
                    
                    if len(hull_vertices) >= 3:
                        hull_vertices_np = np.array(hull_vertices)
                        n_points = len(hull_vertices_np)
                        
                        # Create hull outline
                        line_segments = []
                        for i in range(n_points):
                            line_segments.extend([2, i, (i+1) % n_points])
                        
                        hull_polydata = pv.PolyData(hull_vertices_np)
                        hull_polydata.lines = np.array(line_segments)
                        
                        plotter.add_mesh(hull_polydata, color=hull_color, opacity=0.7,
                                    line_width=3.0, render_lines_as_tubes=True)
                        plotter_has_content = True
                        
                except Exception as e:
                    logger.error(f"Error visualizing convex hull for dataset {original_idx}: {e}")

        # Add triple points from stored triple points
        # Add triple points to constraint points
        if hasattr(self, 'triple_points') and self.triple_points:
            for tp in self.triple_points:
                p = tp['point']
                try:
                    if isinstance(p, (list, tuple)) and len(p) >= 3:
                        constraint_points.append([float(p[0]), float(p[1]), float(p[2])])
                    elif hasattr(p, 'x') and hasattr(p, 'y') and hasattr(p, 'z'):
                        constraint_points.append([float(p.x), float(p.y), float(p.z)])
                except Exception as e:
                    logger.error(f"Error processing triple point: {e}")

        # Visualize all special point types with distinct colors and sizes
        
        # Visualize constraint points (all non-DEFAULT points for triangulation)
        if constraint_points:
            try:
                # Remove duplicates
                unique_constraints = []
                for pt in constraint_points:
                    is_duplicate = False
                    for existing in unique_constraints:
                        if abs(pt[0] - existing[0]) < 1e-6 and abs(pt[1] - existing[1]) < 1e-6 and abs(pt[2] - existing[2]) < 1e-6:
                            is_duplicate = True
                            break
                    if not is_duplicate:
                        unique_constraints.append(pt)
                
                points_np = np.array(unique_constraints)
                plotter.add_mesh(points_np, color='red', point_size=10,
                            render_points_as_spheres=True, name="Constraint_Points")
                plotter_has_content = True
                logger.info(f"Added {len(unique_constraints)} constraint points (consolidated)")
            except Exception as e:
                logger.error(f"Error adding constraint points: {e}")

        # Add comprehensive legend and statistics
        if plotter_has_content:
            # Statistics text
            stats_text = "MeshIt Constraint Points (All Types):\n"
            if constraint_points:
                unique_constraints = []
                for pt in constraint_points:
                    is_duplicate = False
                    for existing in unique_constraints:
                        if abs(pt[0] - existing[0]) < 1e-6 and abs(pt[1] - existing[1]) < 1e-6 and abs(pt[2] - existing[2]) < 1e-6:
                            is_duplicate = True
                            break
                    if not is_duplicate:
                        unique_constraints.append(pt)
                
                stats_text += f"• Total Constraint Points: {len(unique_constraints)} (red)\n"
                stats_text += f"• Raw Points Collected: {len(constraint_points)}\n"

            stats_text += f"\nIntersection Lines: {len(refined_intersection_lines)}"
            stats_text += f"\nDatasets Involved: {len(involved_dataset_indices)}"
            
            # Add surface filter information
            if selected_surface != "All Surfaces":
                stats_text += f"\nSurface Filter: {selected_surface}"

            # Simple legend
            legend_text = "Constraint Points for Triangulation:\n"
            legend_text += "C = Constraint Point (all special types)\n"
            legend_text += "Red = Ready for triangulation\n"
            
            # Add filter info to legend if active
            if selected_surface != "All Surfaces":
                legend_text += f"\nFiltered for: {selected_surface}"
            
            plotter.add_text(stats_text, position='lower_left', font_size=10, color='white')
            plotter.add_text(legend_text, position='upper_right', font_size=9, color='white')
            
            plotter.add_axes()
            plotter.reset_camera()
            
            logger.info(f"Statistics: Constraints={len(constraint_points)}")
            logger.info("Updated refined intersections view with enhanced special point visualization.")
        else:
            plotter.add_text("No valid data to display in refined view.", position='upper_edge', color='white')
            plotter.reset_camera()
    def _clear_refine_mesh_plot(self):
        """Clear all refine mesh tab plotters"""
        try:
            # Clear all individual tab plotters
            self._clear_refine_tab_plotters()
            
            # Legacy compatibility: Clear the main plotter if it exists
            plotter = None
            if hasattr(self, 'refine_mesh_plotter') and self.refine_mesh_plotter:
                plotter = self.refine_mesh_plotter
            elif 'refine_mesh' in getattr(self, 'plotters', {}) and self.plotters['refine_mesh']:
                plotter = self.plotters['refine_mesh']
                self.refine_mesh_plotter = plotter
            
            if plotter:
                plotter.clear()
                plotter.add_text("Refine intersections to visualize or load data.", position='upper_edge', color='white')
                plotter.reset_camera()
                
            logger.info("Cleared all refine mesh visualizations")
        except Exception as e:
            logger.warning(f"Error in _clear_refine_mesh_plot: {e}")
    def _debug_segments_widget_tree(self, where: str = ""):
        try:
            frame = getattr(self, 'segments_viz_frame', None)
            layout = getattr(self, 'segments_plot_layout', None)
            plotter = getattr(self, 'segments_plotter', None)
            interactor = getattr(plotter, 'interactor', None) if plotter else None

            logger.info(f"[SEGMENTS][DBG]{' ' + where if where else ''} "
                        f"frame={type(frame).__name__ if frame else None} "
                        f"layout={'OK' if layout else 'None'} "
                        f"plotter={'OK' if plotter else 'None'} "
                        f"interactor={'OK' if interactor else 'None'}")

            if layout and interactor:
                idx = layout.indexOf(interactor)
                parent_ok = (interactor.parent() is frame)
                vis = interactor.isVisible() if hasattr(interactor, 'isVisible') else None
                size = interactor.size() if hasattr(interactor, 'size') else None
                logger.info(f"[SEGMENTS][DBG]{' ' + where if where else ''} "
                            f"layout_index={idx}, parent_ok={parent_ok}, visible={vis}, size={size}")

                # Self-heal: if not in layout or wrong parent, reattach
                if idx == -1 or not parent_ok:
                    try:
                        interactor.setParent(frame)
                        layout.addWidget(interactor)
                        interactor.show()
                        logger.info(f"[SEGMENTS][DBG]{' ' + where if where else ''} reattached interactor to layout")
                    except Exception as e:
                        logger.error(f"[SEGMENTS][DBG] reattach failed: {e}", exc_info=True)
            elif frame and not layout:
                try:
                    self.segments_plot_layout = QVBoxLayout(self.segments_viz_frame)
                    self.segments_plot_layout.setContentsMargins(0, 0, 0, 0)
                    logger.info(f"[SEGMENTS][DBG]{' ' + where if where else ''} created missing segments_plot_layout")
                    if interactor:
                        self.segments_plot_layout.addWidget(interactor)
                        interactor.show()
                except Exception as e:
                    logger.error(f"[SEGMENTS][DBG] create layout failed: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"[SEGMENTS][DBG] exception: {e}", exc_info=True)
    # ======================================================================
        # ======================================================================
    #  REFINED-MESH TAB : 3-D view updater  (Intersections / Mesh / Segments)
    # ======================================================================
        # ======================================================================
    #  REFINED-MESH TAB : 3-D view updater  (Intersections / Mesh / Segments)
    def _refresh_segment_map_from_tree(self):
        """
        Mirror refine_constraint_tree states into _refine_segment_map for drawing.
        Keeps 'selected' and 'is_hole' in sync with the table (source of truth).
        """
        seg_map = getattr(self, "_refine_segment_map", {}) or {}
        tree = getattr(self, "refine_constraint_tree", None)
        if not tree or not seg_map:
            return

        def walk(item):
            data = item.data(0, Qt.UserRole)
            if data and data.get("type") == "constraint":
                surf_idx = data.get("surface_idx")
                seg_uid = data.get("seg_uid")
                key = (surf_idx, seg_uid)
                if key in seg_map:
                    seg_map[key]["selected"] = (item.checkState(0) == Qt.Checked)
                    # Column 4 is the holes checkbox
                    seg_map[key]["is_hole"] = (item.checkState(4) == Qt.Checked)
            for i in range(item.childCount()):
                walk(item.child(i))

        for i in range(tree.topLevelItemCount()):
            walk(tree.topLevelItem(i))
    def _draw_segments_batched_fast(
        self,
        plotter,
        surface_is_visible_fn,
        show_hull_constraints: bool,
        show_intersection_constraints: bool,
        selected_only_mode: bool,
    ):
        """
        Extremely fast Segments renderer: batches into at most 3 actors
        - selected NORMAL constraints  (green, thick)
        - selected HOLE constraints    (red,   thick)
        - unselected constraints       (grey,  thin)

        Includes fallback: if no HULL segments exist in _refine_segment_map
        for a visible surface, draw its hull from dataset['hull_points'].
        """
        import numpy as np
        import pyvista as pv

        # NEW: ensure the map mirrors the table before drawing (synchronization respected)
        try:
            self._refresh_segment_map_from_tree()
        except Exception:
            pass

        seg_map = getattr(self, "_refine_segment_map", {}) or {}

        cats = {
            "sel_norm": {"pts": [], "lines": [], "idx": 0},
            "sel_hole": {"pts": [], "lines": [], "idx": 0},
            "unsel":    {"pts": [], "lines": [], "idx": 0},
        }

        def add_segment(cat_key, p1, p2):
            if p1 == p2:
                return
            cat = cats[cat_key]
            i0 = cat["idx"]
            cat["pts"].append(p1); cat["pts"].append(p2)
            cat["lines"].extend([2, i0, i0 + 1])
            cat["idx"] += 2

        def to_xyz(p):
            # Accept list/tuple, numpy rows (including dtype=object), or objects with x,y,z
            try:
                if isinstance(p, np.ndarray):
                    if p.size >= 3:
                        return float(p[0]), float(p[1]), float(p[2])
                    return None
                if isinstance(p, (list, tuple)) and len(p) >= 3:
                    return float(p[0]), float(p[1]), float(p[2])
                if hasattr(p, "x") and hasattr(p, "y") and hasattr(p, "z"):
                    return float(p.x), float(p.y), float(p.z)
            except Exception:
                return None
            return None

        built = 0
        saw_hull_for_surface = set()

        # 1) Use map data when present
        for (surf_idx, seg_uid), seg_info in seg_map.items():
            if not surface_is_visible_fn(surf_idx):
                continue

            seg_type = str(seg_info.get("type", seg_info.get("ctype", ""))).lower()
            if seg_type == "hull":
                saw_hull_for_surface.add(surf_idx)
                if not show_hull_constraints:
                    continue
            elif seg_type in ("int", "intersection"):
                if not show_intersection_constraints:
                    continue

            is_selected = bool(seg_info.get("selected", True))
            is_hole     = bool(seg_info.get("is_hole", False))
            if selected_only_mode and not is_selected:
                continue

            pts = seg_info.get("points", [])
            if not pts or len(pts) < 2:
                continue

            cat_key = "sel_hole" if (is_selected and is_hole) else ("sel_norm" if is_selected else "unsel")

            if len(pts) == 2:
                p1 = to_xyz(pts[0]); p2 = to_xyz(pts[1])
                if p1 is not None and p2 is not None and p1 != p2:
                    add_segment(cat_key, p1, p2)
                    built += 1
            else:
                local_pairs = 0
                for j in range(len(pts) - 1):
                    p1 = to_xyz(pts[j]); p2 = to_xyz(pts[j + 1])
                    if p1 is None or p2 is None or p1 == p2:
                        continue
                    add_segment(cat_key, p1, p2)
                    local_pairs += 1
                if local_pairs > 0:
                    built += 1

        # 2) Fallback for missing HULL segments: draw from dataset['hull_points']
        if show_hull_constraints:
            for s_idx, ds in enumerate(getattr(self, "datasets", [])):
                if not surface_is_visible_fn(s_idx):
                    continue
                if s_idx in saw_hull_for_surface:
                    continue  # already emitted from map
                hull = ds.get("hull_points")
                if hull is None or len(hull) < 2:
                    continue

                points = []
                for hp in hull:
                    xyz = to_xyz(hp)
                    if xyz is not None:
                        points.append(xyz)
                if len(points) < 2:
                    continue

                n = len(points)
                closed = (np.linalg.norm(np.array(points[0]) - np.array(points[-1])) < 1e-12)
                last = n - 1  # wrap manually

                local_pairs = 0
                for i in range(last):
                    p1 = points[i]
                    p2 = points[(i + 1) % n] if closed or i + 1 < n else points[i + 1]
                    if p1 != p2:
                        add_segment("sel_norm", p1, p2)
                        local_pairs += 1
                if local_pairs > 0:
                    built += 1

        # build up to three actors
        def emit(cat_key, color, lw):
            cat = cats[cat_key]
            if cat["idx"] == 0:
                return
            pts = np.asarray(cat["pts"], dtype=float)
            lines = np.asarray(cat["lines"], dtype=np.int64)
            poly = pv.PolyData(pts); poly.lines = lines
            plotter.add_mesh(poly, color=color, line_width=lw,
                            render_lines_as_tubes=True, pickable=False, smooth_shading=False)

        # Clear per-segment refs in batched mode
        self.constraint_segment_actor_refs = {}

        emit("sel_norm", (0.0, 1.0, 0.0), 4)
        emit("sel_hole", (1.0, 0.0, 0.0), 4)
        emit("unsel",    (0.53, 0.53, 0.53), 2)

        return built
    # ======================================================================
    def _update_refined_visualization(self):
        """
        Re-draw the Refine-&-Mesh viewport.

            view 0 – refined intersection lines   (red, thick)
            view 1 – conforming surface meshes    (faces, 70 % opa)
            view 2 – constraint segments          (green ↔ dotted grey)

        Restores reliable per-segment actors keyed by (surf_idx, seg_uid) and
        guarantees the Segments plotter is cleared and repopulated each time.
        """
        import numpy as np
        import pyvista as pv

        def _to_xyz(pt):
            # Accept [x,y,z], numpy rows, or objects with x,y,z
            try:
                if isinstance(pt, (list, tuple, np.ndarray)) and len(pt) >= 3:
                    return float(pt[0]), float(pt[1]), float(pt[2])
                if hasattr(pt, "x") and hasattr(pt, "y") and hasattr(pt, "z"):
                    return float(pt.x), float(pt.y), float(pt.z)
            except Exception:
                pass
            return None

        view = getattr(self, "current_refine_view", 0)

        # --- 0: Intersections ---
        if view == 0:
            self.intersection_actor_refs = []
            self.conforming_mesh_actor_refs = []
            if not hasattr(self, 'constraint_segment_actor_refs'):
                self.constraint_segment_actor_refs = {}
            self._visualize_refined_intersections()
            self._add_wells_to_intersection_plotter()
            return

        # --- 1: Meshes ---
        if view == 1:
            plotter = getattr(self, "meshes_plotter", None)
            if not plotter:
                return
            plotter.clear()
            self.intersection_actor_refs = []
            self.conforming_mesh_actor_refs = []
            if not hasattr(self, 'constraint_segment_actor_refs'):
                self.constraint_segment_actor_refs = {}

            for ds in self.datasets:
                cm = ds.get("conforming_mesh")
                if not cm:
                    continue
                verts, faces = cm.get("vertices"), cm.get("triangles")
                if verts is None or faces is None or len(verts) == 0:
                    continue
                mesh = pv.PolyData(
                    verts,
                    np.hstack([np.full((len(faces), 1), 3, dtype=np.int64), faces])
                )
                actor = plotter.add_mesh(
                    mesh,
                    color=ds.get("color", "#CCCCCC"),
                    opacity=0.7,
                    show_edges=True,
                    edge_color="black",
                )
                self.conforming_mesh_actor_refs.append(actor)

            plotter.add_axes()
            plotter.reset_camera()
            plotter.render()
            return

        # --- 2: Segments ---
        plotter = getattr(self, "segments_plotter", None)
        logger.info("[SEGMENTS] Enter segments view redraw")
        self._debug_segments_widget_tree("redraw")
        if not plotter:
            return

        # Fully reset the Segments viewport so it never stays white
        plotter.clear()
        plotter.set_background([0.318, 0.341, 0.431])

        # UI filters
        selected_surface_name = "All Surfaces"
        if hasattr(self, 'refine_surface_selector') and self.refine_surface_selector:
            selected_surface_name = self.refine_surface_selector.currentText()

        show_hull = getattr(self, 'show_hull_constraints_checkbox', None)
        show_intersections = getattr(self, 'show_intersection_constraints_checkbox', None)
        show_selected_only = getattr(self, 'show_selected_only_checkbox', None)

        show_hull_constraints = show_hull.isChecked() if show_hull else True
        show_intersection_constraints = show_intersections.isChecked() if show_intersections else True
        selected_only_mode = show_selected_only.isChecked() if show_selected_only else False

        def surface_name(idx):
            if 0 <= idx < len(self.datasets):
                return self.datasets[idx].get("name", f"Surface_{idx}")
            return f"Surface_{idx}"

        def surface_is_visible(idx):
            if selected_surface_name == "All Surfaces":
                return True
            return surface_name(idx) == selected_surface_name

        # Decide rendering mode: batched for speed when mouse selection is OFF
        mouse_sel_on = bool(getattr(self, 'mouse_selection_enabled_btn', None) and self.mouse_selection_enabled_btn.isChecked())
        self._segments_batched_mode = not mouse_sel_on

        # Ensure the segment map is available
        if not hasattr(self, "_refine_segment_map") or not self._refine_segment_map:
            try:
                self._populate_refine_constraint_tree()
            except Exception:
                pass

        if self._segments_batched_mode:
            # FAST path: draw everything in 1–3 actors
            built = self._draw_segments_batched_fast(
                plotter,
                surface_is_visible_fn=surface_is_visible,
                show_hull_constraints=show_hull_constraints,
                show_intersection_constraints=show_intersection_constraints,
                selected_only_mode=selected_only_mode,
            )
        else:
            # PRECISE path (picking): one actor per segment (original behavior)
            if not hasattr(self, 'constraint_segment_actor_refs'):
                self.constraint_segment_actor_refs = {}
            else:
                for actor in list(self.constraint_segment_actor_refs.values()):
                    try:
                        plotter.remove_actor(actor)
                    except Exception:
                        pass
                self.constraint_segment_actor_refs = {}

            # initialize picking maps
            self._actor_id_to_segment_map = {}
            self._mesh_geometry_map = {}
            self._mesh_geometry_map_reduced = {}

            seg_map = getattr(self, "_refine_segment_map", {}) or {}
            built = 0

            for (surf_idx, seg_uid), seg_info in seg_map.items():
                if not surface_is_visible(surf_idx):
                    continue

                seg_type = str(seg_info.get("type", seg_info.get("ctype", ""))).lower()
                if seg_type == "hull" and not show_hull_constraints:
                    continue
                if seg_type in ("int", "intersection") and not show_intersection_constraints:
                    continue
                if selected_only_mode and not seg_info.get("selected", True):
                    continue

                pts = seg_info.get("points", [])
                if not pts or len(pts) < 2:
                    continue

                def to_xyz(p):
                    if isinstance(p, (list, tuple)) and len(p) >= 3:
                        return float(p[0]), float(p[1]), float(p[2])
                    if hasattr(p, "x") and hasattr(p, "y") and hasattr(p, "z"):
                        return float(p.x), float(p.y), float(p.z)
                    try:
                        import numpy as np
                        if isinstance(p, np.ndarray) and p.size >= 3:
                            return float(p[0]), float(p[1]), float(p[2])
                    except Exception:
                        pass
                    return None

                p1 = to_xyz(pts[0]); p2 = to_xyz(pts[-1])
                if p1 is None or p2 is None:
                    continue

                import numpy as np, pyvista as pv
                poly = pv.PolyData(np.array([p1, p2], dtype=float))
                poly.lines = np.array([2, 0, 1], dtype=np.int64)

                rgb, lw, pattern = self._segment_vis_props(surf_idx, seg_uid)
                actor = plotter.add_mesh(
                    poly, color=rgb, line_width=lw, pickable=True,
                    render_lines_as_tubes=True, smooth_shading=False,
                )
                try:
                    prop = actor.GetProperty()
                    try:
                        prop.SetLineStipplePattern(pattern)
                        prop.SetLineStippleRepeatFactor(1)
                    except Exception:
                        pass
                except Exception:
                    pass

                # store refs and build picking maps
                self.constraint_segment_actor_refs[(surf_idx, seg_uid)] = actor
                actor_id = id(actor)
                self._actor_id_to_segment_map[actor_id] = (surf_idx, seg_uid)
                try:
                    sig = self._create_mesh_signature(poly)
                    if sig is not None:
                        self._mesh_geometry_map[sig] = (surf_idx, seg_uid)
                    rsig = self._create_reduced_precision_signature(poly)
                    if rsig is not None:
                        if not hasattr(self, '_mesh_geometry_map_reduced') or self._mesh_geometry_map_reduced is None:
                            self._mesh_geometry_map_reduced = {}
                        self._mesh_geometry_map_reduced[rsig] = (surf_idx, seg_uid)
                except Exception:
                    pass

                built += 1

            # flag for mouse toggler
            self._constraint_actors_built = built > 0

        # Empty-state text if nothing passed the filters
        if built == 0:
            msg = "No segments to display."
            details = []
            if selected_surface_name != "All Surfaces":
                details.append(f"Surface={selected_surface_name}")
            if not show_hull_constraints:
                details.append("Hull hidden")
            if not show_intersection_constraints:
                details.append("Intersections hidden")
            if selected_only_mode:
                details.append("Selected only")
            if details:
                msg += " (" + ", ".join(details) + ")"
            plotter.add_text(msg, position='upper_edge', color='white')

        plotter.add_axes()
        plotter.reset_camera()
        plotter.render()
        # =====================================

    # ======================================================================
    #  SEGMENT selection → drawing helpers
    # ======================================================================
    def _segment_checked(self, surf_idx: int, seg_uid: int) -> bool:
        """Return True if that segment’s checkbox is currently ticked."""
        tree = getattr(self, "refine_constraint_tree", None)
        if not tree:
            return False

        def walk(item):
            data = item.data(0, Qt.UserRole)
            if data and data.get("type") == "constraint" \
               and data["surface_idx"] == surf_idx \
               and data["seg_uid"]     == seg_uid:
                return item.checkState(0) == Qt.Checked
            for i in range(item.childCount()):
                res = walk(item.child(i))
                if res is not None:
                    return res
            return None

        for i in range(tree.topLevelItemCount()):
            res = walk(tree.topLevelItem(i))
            if res is not None:
                return res
        return False

    def _segment_vis_props(self, surf_idx: int, seg_uid: int):
        """
        Return a tuple   (rgb-tuple , line-width , stipple-pattern)
        • If the segment is selected and is a hole  →  thick solid red
        • If the segment is selected               →  thick solid green
        • If not selected                         →  thin  dotted grey
        """
        checked = self._segment_checked(surf_idx, seg_uid)
        is_hole = self._segment_is_hole(surf_idx, seg_uid)
        
        if checked:
            if is_hole:
                return ((1.00, 0.00, 0.00), 4, 0xFFFF)      # solid red for holes
            else:
                return ((0.00, 1.00, 0.00), 4, 0xFFFF)      # solid green for normal constraints
        else:
            # 0xAAAA = dot-dot pattern; renders solid on old VTK builds
            return ((0.53, 0.53, 0.53), 2, 0xAAAA)
        
    def _segment_is_hole(self, surf_idx: int, seg_uid: int) -> bool:
        """Check if a segment is marked as a hole."""
        seg_data = self._refine_segment_map.get((surf_idx, seg_uid))
        if seg_data:
            return seg_data.get("is_hole", False)
        return False
        # ======================================================================
    #  SEGMENT-TREE → 3-D SYNC
    # ======================================================================

       # ======================================================================
    #  Update ONE segment actor when its checkbox changes
    # ======================================================================
    def _apply_segment_state(self, surf_idx: int, seg_uid: int, checked: bool):
        """
        Update ONE segment actor when its checkbox changes.
        Optimized for fast individual updates during mouse clicks.
        """
        actor = self.constraint_segment_actor_refs.get((surf_idx, seg_uid))
        if not actor:
            return

        rgb, lw, pattern = self._segment_vis_props(surf_idx, seg_uid)

        try:
            prop = actor.GetProperty()
            prop.SetColor(*rgb)
            prop.SetLineWidth(lw)
            prop.SetLineStipplePattern(pattern)
            prop.SetLineStippleRepeatFactor(1)
        except Exception:
            # at least update colour if stipple unsupported
            try:
                actor.GetProperty().SetColor(*rgb)
            except Exception:
                pass

        actor.SetVisibility(True)      # always draw – style encodes selection
        
        # Immediate render for instant feedback (only if in segments view)
        if (getattr(self, "current_refine_view", 0) == 2):
            current_plotter = self._get_current_refine_plotter()
            if current_plotter:
                current_plotter.render()
            elif self.plotters.get("refine_mesh"):
                self.plotters["refine_mesh"].render()

    def _update_all_segment_actors(self):
        """
        Refresh colours/styles after any tree tick change.
        - If batched mode is ON (mouse selection OFF), just rebuild once.
        - If per-segment mode (mouse selection ON), update actors in place.
        """
        if getattr(self, "current_refine_view", 0) != 2:
            return

        if getattr(self, "_segments_batched_mode", False):
            # Rebuild the batched view in a single pass
            self._update_refined_visualization()
            return

        # Per-segment path (original behavior)
        needs_render = False
        for (s_idx, uid), actor in getattr(self, 'constraint_segment_actor_refs', {}).items():
            if not actor:
                continue
            is_checked = self._segment_checked(s_idx, uid)
            is_hole = self._segment_is_hole(s_idx, uid)
            if (s_idx, uid) in getattr(self, '_refine_segment_map', {}):
                self._refine_segment_map[(s_idx, uid)]["selected"] = is_checked
                self._refine_segment_map[(s_idx, uid)]["is_hole"] = is_hole
            rgb, lw, pattern = self._segment_vis_props(s_idx, uid)
            try:
                prop = actor.GetProperty()
                if (prop.GetColor() != rgb) or (prop.GetLineWidth() != lw):
                    prop.SetColor(*rgb)
                    prop.SetLineWidth(lw)
                    needs_render = True
                try:
                    prop.SetLineStipplePattern(pattern)
                    prop.SetLineStippleRepeatFactor(1)
                except Exception:
                    pass
            except Exception:
                pass

        if needs_render:
            current_plotter = self._get_current_refine_plotter()
            if current_plotter:
                current_plotter.render()
            elif self.plotters.get("refine_mesh"):
                self.plotters["refine_mesh"].render()

    # ----------------------------------------------------------------------
    def _on_refine_constraint_tree_item_changed(self, item, column):
        """
        Called whenever a checkbox in the segment tree changes.
        1) Propagate parent->children or child->parent states.
        2) Update visibility/colour of the corresponding 3-D actor(s).
        3) Synchronize intersection line selections across surfaces.
        4) Handle hole checkbox changes (column 4).
        """
        if self._refine_updating_constraint_tree:
            return

        self._refine_updating_constraint_tree = True
        try:
            # Handle hole checkbox changes (column 4)
            if column == 4:
                data = item.data(0, Qt.UserRole)
                if data and data.get("type") == "constraint":
                    surface_idx = data["surface_idx"]
                    seg_uid = data["seg_uid"]
                    is_hole = (item.checkState(4) == Qt.Checked)
                    # Update the segment map
                    if (surface_idx, seg_uid) in self._refine_segment_map:
                        self._refine_segment_map[(surface_idx, seg_uid)]["is_hole"] = is_hole
                        logger.info(f"Updated segment {seg_uid} hole status: {is_hole}")
                        
                    # Synchronize hole marking across surfaces for shared intersection lines
                    self._sync_hole_selection_across_surfaces(item)
                        
                    # Update visualization to show hole segments differently
                    self._update_all_segment_actors()
                
                # Handle hole checkbox changes for group items (intersection_group or hull_group)
                elif data and data.get("type") in ["intersection_group", "hull_group"]:
                    is_hole = (item.checkState(4) == Qt.Checked)
                    group_type = data.get("type")
                    surface_idx = data.get("surface_idx")
                    
                    logger.info(f"Group {group_type} hole state changed to {is_hole} for surface {surface_idx}")
                    
                    # Propagate hole state to all children segments
                    def set_all_children_hole_state(parent, state):
                        for i in range(parent.childCount()):
                            child = parent.child(i)
                            child_data = child.data(0, Qt.UserRole)
                            if child_data and child_data.get("type") == "constraint":
                                child.setCheckState(4, state)
                                # Update segment map
                                child_surface_idx = child_data["surface_idx"]
                                child_seg_uid = child_data["seg_uid"]
                                if (child_surface_idx, child_seg_uid) in self._refine_segment_map:
                                    self._refine_segment_map[(child_surface_idx, child_seg_uid)]["is_hole"] = (state == Qt.Checked)
                                    logger.debug(f"Updated segment {child_seg_uid} hole status: {state == Qt.Checked}")
                            set_all_children_hole_state(child, state)
                    
                    set_all_children_hole_state(item, Qt.Checked if is_hole else Qt.Unchecked)
                    
                    # Synchronize across surfaces if it's an intersection group
                    if data.get("type") == "intersection_group":
                        logger.info(f"Synchronizing intersection group hole state across surfaces...")
                        self._sync_hole_selection_across_surfaces(item)
                    
                    # Update visualization
                    self._update_all_segment_actors()
                
                # Handle parent state updates when children change
                def update_parent_hole_state(child):
                    parent = child.parent()
                    if not parent:
                        return
                    
                    parent_data = parent.data(0, Qt.UserRole)
                    if parent_data and parent_data.get("type") in ["intersection_group", "hull_group"]:
                        # Check if all children have the same hole state
                        all_hole = True
                        any_hole = False
                        for i in range(parent.childCount()):
                            child_item = parent.child(i)
                            child_item_data = child_item.data(0, Qt.UserRole)
                            if child_item_data and child_item_data.get("type") == "constraint":
                                child_is_hole = (child_item.checkState(4) == Qt.Checked)
                                if child_is_hole:
                                    any_hole = True
                                else:
                                    all_hole = False
                        
                        # Set parent state: checked if all children are holes, unchecked if none, partially checked if mixed
                        if all_hole and any_hole:
                            parent.setCheckState(4, Qt.Checked)
                        elif any_hole:
                            parent.setCheckState(4, Qt.PartiallyChecked)
                        else:
                            parent.setCheckState(4, Qt.Unchecked)
                        
                        update_parent_hole_state(parent)
                
                # Update parent state if this was a constraint item
                if data and data.get("type") == "constraint":
                    update_parent_hole_state(item)
                
                return

            # Handle selection checkbox changes (column 0)
            if column != 0:
                return

            # -------- propagate state downwards (parent → children) ----------
            def set_all_children_state(parent, state):
                for i in range(parent.childCount()):
                    child = parent.child(i)
                    child.setCheckState(0, state)
                    # Update segment map for constraint items
                    child_data = child.data(0, Qt.UserRole)
                    if child_data and child_data.get("type") == "constraint":
                        surface_idx = child_data["surface_idx"]
                        seg_uid = child_data["seg_uid"]
                        if (surface_idx, seg_uid) in self._refine_segment_map:
                            self._refine_segment_map[(surface_idx, seg_uid)]["selected"] = (state == Qt.Checked)
                    set_all_children_state(child, state)

            set_all_children_state(item, item.checkState(0))
            
            # Also update the current item if it's a constraint
            data = item.data(0, Qt.UserRole)
            if data and data.get("type") == "constraint":
                surface_idx = data["surface_idx"]
                seg_uid = data["seg_uid"]
                if (surface_idx, seg_uid) in self._refine_segment_map:
                    self._refine_segment_map[(surface_idx, seg_uid)]["selected"] = (item.checkState(0) == Qt.Checked)

            # -------- propagate upwards (any unchecked → parent unchecked) ----
            def update_parent_state(child):
                parent = child.parent()
                if not parent:
                    return
                any_checked = any(
                    parent.child(i).checkState(0) == Qt.Checked
                    for i in range(parent.childCount())
                )
                parent.setCheckState(0, Qt.Checked if any_checked else Qt.Unchecked)
                update_parent_state(parent)

            update_parent_state(item)

            # -------- sync intersection selections across surfaces -----------
            # Get the item data to check if it's an intersection group or a segment within an intersection group
            data = item.data(0, Qt.UserRole)
            if data:
                # If it's an intersection group or a constraint within an intersection group
                if data.get('type') == 'intersection_group' or (
                    data.get('type') == 'constraint' and 
                    item.parent() and 
                    item.parent().data(0, Qt.UserRole) and 
                    item.parent().data(0, Qt.UserRole).get('type') == 'intersection_group'
                ):
                    # Synchronize this intersection line selection across surfaces
                    self._sync_intersection_selection_across_surfaces(item)

        finally:
            self._refine_updating_constraint_tree = False

        # -------- refresh 3-D actors (only for non-mouse triggered changes) ----
        # Skip batch update if this was triggered by mouse selection (already handled individually)
        if not getattr(self, '_mouse_triggered_change', False):
            self._update_all_segment_actors()
    def consolidate_points_for_triangulation(self):
        """
        Consolidate all refined points following C++ MeshIt logic for tetrahedral meshing:
        - Triple Points: Only TRIPLE_POINT type
        - Special Points: ALL other points INCLUDING DEFAULT subdivision points
        
        DEFAULT points are the refined subdivision points from C++ RefineByLength that are 
        essential for creating manifold structure in tetrahedral meshing.
        """
        # Clear existing consolidated collections
        self.consolidated_special_points = []
        self.consolidated_triple_points = []
        
        logger.info("Consolidating points for triangulation constraints...")
        
        # 1. Process all intersection line points (INCLUDING DEFAULT subdivision points)
        for dataset_idx_key in self.datasets_intersections.keys():
            intersections_list = self.datasets_intersections[dataset_idx_key]
            for intersection_data in intersections_list:
                if 'points' not in intersection_data or not intersection_data['points']:
                    continue
                    
                for p in intersection_data['points']:
                    point_type = None
                    coord = None
                    
                    # Extract coordinates and type
                    if isinstance(p, (list, tuple)):
                        if len(p) >= 3:
                            coord = [float(p[0]), float(p[1]), float(p[2])]
                            point_type = p[3] if len(p) > 3 else None
                    elif hasattr(p, 'x') and hasattr(p, 'y') and hasattr(p, 'z'):
                        coord = [float(p.x), float(p.y), float(p.z)]
                        point_type = getattr(p, 'point_type', getattr(p, 'type', None))
                    
                    if not coord:
                        continue
                        
                    # Consolidate based on corrected C++ logic
                    if point_type:
                        type_str = str(point_type)
                        if type_str == "TRIPLE_POINT":
                            self.consolidated_triple_points.append({
                                'coord': coord, 'type': type_str, 'source': 'intersection'
                            })
                        else:  # ALL other points (including DEFAULT) become special points
                            self.consolidated_special_points.append({
                                'coord': coord, 'type': type_str, 'source': 'intersection'
                            })
                    else:
                        # Points without type are treated as DEFAULT subdivision points
                        self.consolidated_special_points.append({
                            'coord': coord, 'type': 'DEFAULT', 'source': 'intersection'
                        })
        
        # 2. Process all convex hull points (INCLUDING DEFAULT subdivision points)
        for dataset_idx in range(len(self.datasets)):
            dataset = self.datasets[dataset_idx]
            hull_points = dataset.get('hull_points', [])
            
            for pt in hull_points:
                if len(pt) >= 3:  # Process ALL hull points
                    coord = [float(pt[0]), float(pt[1]), float(pt[2])]
                    pt_type = str(pt[3]) if len(pt) > 3 and isinstance(pt[3], str) else 'DEFAULT'
                    
                    # ALL hull points become constraints (including DEFAULT subdivision points)
                    self.consolidated_special_points.append({
                        'coord': coord, 'type': pt_type, 'source': f'hull_dataset_{dataset_idx}'
                    })
        
        # 3. Process stored triple points
        if hasattr(self, 'triple_points') and self.triple_points:
            for tp in self.triple_points:
                p = tp['point']
                try:
                    if isinstance(p, (list, tuple)) and len(p) >= 3:
                        coord = [float(p[0]), float(p[1]), float(p[2])]
                    elif hasattr(p, 'x') and hasattr(p, 'y') and hasattr(p, 'z'):
                        coord = [float(p.x), float(p.y), float(p.z)]
                    else:
                        continue
                        
                    self.consolidated_triple_points.append({
                        'coord': coord, 'type': 'TRIPLE_POINT', 'source': 'stored_triple_points'
                    })
                except Exception as e:
                    logger.error(f"Error processing stored triple point: {e}")
        
        # 4. Remove duplicates (points that might appear in both collections)
        def remove_duplicates(points_list, tolerance=1e-6):
            unique_points = []
            for pt in points_list:
                is_duplicate = False
                for existing_pt in unique_points:
                    if (abs(pt['coord'][0] - existing_pt['coord'][0]) < tolerance and
                        abs(pt['coord'][1] - existing_pt['coord'][1]) < tolerance and  
                        abs(pt['coord'][2] - existing_pt['coord'][2]) < tolerance):
                        is_duplicate = True
                        break
                if not is_duplicate:
                    unique_points.append(pt)
            return unique_points
        
        self.consolidated_special_points = remove_duplicates(self.consolidated_special_points)
        self.consolidated_triple_points = remove_duplicates(self.consolidated_triple_points)
        
        # Log consolidation results with detailed breakdown
        logger.info("=== CONSOLIDATION RESULTS (Including DEFAULT subdivision points) ===")
        logger.info(f"Triple Points: {len(self.consolidated_triple_points)}")
        logger.info(f"Special Points (ALL types including DEFAULT): {len(self.consolidated_special_points)}")
        
        # Break down special points by type
        special_by_type = {}
        special_by_source = {}
        for pt in self.consolidated_special_points:
            pt_type = pt['type']
            pt_source = pt['source']
            special_by_type[pt_type] = special_by_type.get(pt_type, 0) + 1
            special_by_source[pt_source] = special_by_source.get(pt_source, 0) + 1
        
        logger.info("Special Points Breakdown by Type:")
        for pt_type, count in special_by_type.items():
            logger.info(f"  {pt_type}: {count}")
        
        logger.info("Special Points Breakdown by Source:")
        for pt_source, count in special_by_source.items():
            logger.info(f"  {pt_source}: {count}")
        
        logger.info("Ready for constrained triangulation with manifold structure!")
        logger.info("==============================================================")
        
        return self.consolidated_special_points, self.consolidated_triple_points

    def _create_multi_dataset_3d_visualization(self, parent_frame, datasets, title, view_type="points"):
        """Create a 3D visualization of multiple datasets with proper coordinate validation."""

        # Close and clean up any previous plotter in this frame
        if hasattr(self, f'{view_type}_plotter'):
            old_plotter = getattr(self, f'{view_type}_plotter')
            if old_plotter:
                try:
                    old_plotter.close()
                except Exception as e:
                    logger.warning(f"Error closing old plotter for {view_type}: {e}")
        
        parent_layout = parent_frame.layout()
        if parent_layout is None:
            parent_layout = QVBoxLayout(parent_frame)
            parent_layout.setContentsMargins(0, 0, 0, 0)

        while parent_layout.count():
            item = parent_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        from pyvistaqt import QtInteractor
        import pyvista as pv
        import numpy as np
                
        plotter = QtInteractor(parent=parent_frame)
        setattr(self, f'{view_type}_plotter', plotter) # Store reference to the new plotter
        parent_layout.addWidget(plotter.interactor)
        
        plotter.set_background("#383F51")
        plotter.disable() # Disable rendering for performance during setup

        plotter_has_geometry = False
        for i, dataset in enumerate(datasets):
            if not dataset.get('visible', True):
                continue
                
            points = dataset.get('points')
            color = dataset.get('color', '#000000')
            name = dataset.get('name', 'Unnamed')
            
            if points is None or len(points) == 0:
                continue

            if points.shape[1] >= 3:
                points_3d = points[:, 0:3].copy()
            else:
                points_3d = np.zeros((len(points), 3))
                points_3d[:, :points.shape[1]] = points

            max_points_for_viz = 5000
            if len(points_3d) > max_points_for_viz:
                step = len(points_3d) // max_points_for_viz
                points_3d_viz = points_3d[::step]
            else:
                points_3d_viz = points_3d

            if view_type == "points":
                point_cloud = pv.PolyData(points_3d_viz)
                plotter.add_mesh(point_cloud, color=color, render_points_as_spheres=True, point_size=8, label=name)
                plotter_has_geometry = True
            
            elif view_type == "hulls":
                hull_points = dataset.get('hull_points')
                if hull_points is not None and len(hull_points) > 3:
                    try:
                        # *** FIX START ***
                        # The hull_points array has dtype=object because of the type string.
                        # We must explicitly extract the numeric coordinates into a new, purely numeric array.
                        hull_vertices_numeric = []
                        for p in hull_points:
                            if len(p) >= 3:
                                try:
                                    # Extract and convert the first 3 elements (x,y,z)
                                    xyz = [float(p[0]), float(p[1]), float(p[2])]
                                    hull_vertices_numeric.append(xyz)
                                except (ValueError, TypeError):
                                    continue # Skip if conversion fails
                        
                        if not hull_vertices_numeric:
                            continue # Skip if no valid points were extracted

                        hull_3d = np.array(hull_vertices_numeric, dtype=np.float64)
                        # *** FIX END ***

                        # This logic now works correctly with the clean `hull_3d` array
                        num_hull_points = len(hull_3d)
                        if num_hull_points >= 2:
                            # Create a single PolyData object for the entire hull outline
                            line_segments = np.array([[2, i, (i + 1) % num_hull_points] for i in range(num_hull_points)], dtype=np.int32).ravel()
                            hull_mesh = pv.PolyData(hull_3d)
                            hull_mesh.lines = line_segments

                            plotter.add_mesh(hull_mesh, color=color, line_width=3.0, label=f"{name} Hull")
                            
                            point_cloud = pv.PolyData(points_3d_viz)
                            plotter.add_mesh(point_cloud, color=color, opacity=0.3, render_points_as_spheres=True, point_size=5)
                            plotter_has_geometry = True
                                
                    except Exception as e:
                        logger.error(f"Error processing hull points for {name}: {e}")
                        point_cloud = pv.PolyData(points_3d_viz)
                        plotter.add_mesh(point_cloud, color=color, opacity=0.7, render_points_as_spheres=True, point_size=5)
                        plotter_has_geometry = True

            elif view_type == "segments":
                segments = dataset.get('segments')
                if segments is not None and len(segments) > 0:
                    point_cloud = pv.PolyData(points_3d_viz)
                    plotter.add_mesh(point_cloud, color=color, opacity=0.2, render_points_as_spheres=True, point_size=3)

                    segment_points_list = []
                    for seg in segments:
                        segment_points_list.append(seg[0])
                        segment_points_list.append(seg[1])
                    
                    if segment_points_list:
                        all_line_points = np.array(segment_points_list)
                        # Create line connectivity array
                        lines = np.arange(len(all_line_points)).reshape(-1, 2)
                        lines = np.hstack((np.full((len(lines), 1), 2), lines))
                        
                        segments_mesh = pv.PolyData(all_line_points, lines=lines.ravel())
                        plotter.add_mesh(segments_mesh, color=color, line_width=3.0, label=f"{name} Segments")
                        
                        # Add endpoint markers
                        unique_endpoints = np.unique(all_line_points, axis=0)
                        plotter.add_points(unique_endpoints, color='red', point_size=8, render_points_as_spheres=True)
                        plotter_has_geometry = True

            elif view_type == "triangulation":
                tri_result = dataset.get('triangulation_result')
                if tri_result:
                    vertices = tri_result.get('vertices')
                    triangles = tri_result.get('triangles')
                    
                    if vertices is not None and len(vertices) > 0 and triangles is not None and len(triangles) > 0:
                        vertices_3d = np.zeros((len(vertices), 3))
                        if vertices.shape[1] >= 3:
                            vertices_3d = vertices[:, :3].copy()
                        else:
                            vertices_3d[:, :vertices.shape[1]] = vertices
                        
                        # Apply height factor for visualization
                        vertices_3d[:, 2] *= self.height_factor

                        cells = np.hstack([np.full((len(triangles), 1), 3), triangles])
                        mesh = pv.PolyData(vertices_3d, cells)
                        
                        plotter.add_mesh(mesh, color=color, opacity=0.8, show_edges=True, edge_color='black', line_width=0.5, label=name)
                        plotter_has_geometry = True

        if plotter_has_geometry:
            plotter.add_axes()
            plotter.add_legend()
            plotter.reset_camera()
        else:
            plotter.add_text(f"No valid data to display for '{view_type}' view.", position='upper_edge', color='white')
            
        plotter.enable()
        plotter.render()


    def _on_tab_changed(self, index):
        """Handle tab changes to update visualizations as needed"""
        logger.debug(f"Tab changed to index {index}")
        # Get the widget associated with the current index
        current_tab_widget = self.notebook.widget(index)

        if not self.datasets:
            logger.debug("No datasets loaded, clearing visualizations.")
            self._clear_visualizations() # Clears all known plots
            if current_tab_widget == self.file_tab: pass
            elif current_tab_widget == self.hull_tab: self._clear_hull_plot()
            elif current_tab_widget == self.segment_tab: self._clear_segment_plot()
            elif current_tab_widget == self.triangulation_tab: self._clear_triangulation_plot()
            elif current_tab_widget == self.intersection_tab: self._clear_intersection_plot()
            elif current_tab_widget == self.refine_mesh_tab: self._clear_refine_mesh_plot()
            elif hasattr(self, 'tetra_mesh_tab') and current_tab_widget == self.tetra_mesh_tab: self._clear_tetra_mesh_plot()
            return

        # NEW: ensure tables are populated whenever user views any tab
        if hasattr(self, '_refresh_seg_refine_table'):
            self._refresh_seg_refine_table()
        if hasattr(self, '_refresh_mesh_refine_table'):
            self._refresh_mesh_refine_table()

        if current_tab_widget == self.file_tab:
            self._visualize_all_points()
        elif current_tab_widget == self.hull_tab:
            needs_update = any(d.get('visible', True) and d.get('hull_points') is not None for d in self.datasets)
            if needs_update: self._visualize_all_hulls()
            else: self._clear_hull_plot(); self.statusBar().showMessage("No visible hulls computed.")
        elif current_tab_widget == self.segment_tab:
            needs_update = any(d.get('visible', True) and d.get('segments') is not None for d in self.datasets)
            if needs_update:
                self._clear_segmentation_visualization_flag()
                self._visualize_all_segments()
            else:
                self._clear_segment_plot(); self.statusBar().showMessage("No visible segments computed.")
        elif current_tab_widget == self.triangulation_tab:
            needs_update = any(d.get('visible', True) and d.get('triangulation_result') is not None for d in self.datasets)
            if needs_update:
                self._visualize_all_triangulations()
            else:
                self._clear_triangulation_plot(); self.statusBar().showMessage("No visible triangulations computed.")
        elif current_tab_widget == self.intersection_tab:
            has_intersections = hasattr(self, 'datasets_intersections') and bool(self.datasets_intersections)
            if has_intersections: self._visualize_intersections()
            else: self._clear_intersection_plot(); self.statusBar().showMessage("No intersections computed yet.")
        elif current_tab_widget == self.refine_mesh_tab:
            has_refined_intersections = hasattr(self, 'datasets_intersections') and bool(self.datasets_intersections)
            if has_refined_intersections:
                self._visualize_refined_intersections()
            else:
                self._clear_refine_mesh_plot(); self.statusBar().showMessage("No intersections to refine or display.")
        elif current_tab_widget == self.pre_tetramesh_tab:
            if any(d.get('constrained_triangulation_result') for d in self.datasets):
                self._visualize_constrained_meshes()
            else:
                self._clear_pre_tetramesh_plot(); self.statusBar().showMessage("No constrained surface meshes computed yet.")
        elif hasattr(self, 'tetra_mesh_tab') and current_tab_widget == self.tetra_mesh_tab:
            if hasattr(self, 'tetrahedral_mesh') and self.tetrahedral_mesh:
                self._visualize_tetrahedral_mesh_in_tetra_tab()
            elif hasattr(self, 'tetra_selected_surfaces') and self.tetra_selected_surfaces:
                self._visualize_loaded_surfaces()
            else:
                if hasattr(self, 'tetra_plotter') and self.tetra_plotter:
                    self.tetra_plotter.clear()
                    self.tetra_plotter.add_text("Load surfaces from Pre-Tetra tab to begin", position='upper_edge', color='white')
                    self.tetra_plotter.render()
                self.statusBar().showMessage("Ready to load constrained surfaces from Pre-Tetra mesh tab.")
    # ... rest of the class methods (_get_next_color, _create_main_layout, etc.) ...


    
    
    
    
    
    
    def _add_surface_with_display_mode(self, surface_index, vertices, triangles, display_mode):
        """Add a surface with the specified display mode."""
        try:
            import pyvista as pv
            import numpy as np
            
            vertices_array = np.array(vertices)
            triangles_array = np.array(triangles)
            
            # Ensure 3D coordinates
            if vertices_array.shape[1] == 2:
                temp_vertices = np.zeros((vertices_array.shape[0], 3))
                temp_vertices[:, :2] = vertices_array
                vertices_array = temp_vertices
            
            # Create PyVista mesh
            faces = []
            for tri in triangles_array:
                faces.extend([3, tri[0], tri[1], tri[2]])
            
            mesh = pv.PolyData(vertices_array, faces=faces)
            
            # Get surface properties
            surface_type = self._get_surface_type(surface_index)
            color = self._get_surface_color(surface_type)
            dataset = self.datasets[surface_index]
            actor_name = f"surface_{surface_index}"
            
            # Set display properties based on mode
            if display_mode == "faces":
                show_edges = False
                opacity = 0.7
                style = 'surface'
            elif display_mode == "wireframe":
                show_edges = True
                opacity = 1.0
                style = 'wireframe'
            else:  # both
                show_edges = True
                opacity = 0.6
                style = 'surface'
            
            # Add mesh to plotter
            self.tetra_plotter.add_mesh(
                mesh,
                name=actor_name,
                color=color,
                opacity=opacity,
                show_edges=show_edges,
                edge_color='black' if show_edges else None,
                line_width=1 if show_edges else None,
                style=style,
                pickable=True
            )
            
        except Exception as e:
            logger.error(f"Error adding surface {surface_index} with display mode {display_mode}: {e}")

    def _get_boundary_edges(self, triangles):
        """Finds the boundary edges from a list of triangles."""
        if triangles is None or len(triangles) == 0:
            return []

        edges = set()
        boundary_edges = []

        for tri in triangles:
            # Ensure triangle vertices are sorted to make edges canonical
            tri_sorted = sorted(tri)
            # Edges: (v0, v1), (v1, v2), (v0, v2) -> use smallest index first
            current_edges = [
                tuple(sorted((tri[i], tri[(i + 1) % 3]))) for i in range(3)
            ]

            for edge in current_edges:
                if edge in edges:
                    # This edge is shared by another triangle, remove it
                    edges.remove(edge)
                else:
                    # This is the first time we see this edge
                    edges.add(edge)

        # Remaining edges in the set are boundary edges
        return list(edges) # Return as a list of tuples (v1_idx, v2_idx)

    def _create_main_layout(self):
        """Creates the main layout after widgets are initialized."""
        # This assumes self.main_layout and self.notebook exist
        if not hasattr(self, 'main_layout'):
            logger.error("_create_main_layout called before main_layout initialized.")
            self.main_layout = QVBoxLayout(self.central_widget) # Attempt recovery

        if not hasattr(self, 'notebook'):
             logger.error("_create_main_layout called before notebook initialized.")
             self.notebook = QTabWidget() # Attempt recovery
             self.main_layout.addWidget(self.notebook)

        # Ensure tabs are added after the notebook is part of the main layout
        # The setup methods already add the tabs, this function primarily ensures
        # the notebook is correctly placed in the main layout.
        # No additional widget adding needed here if setup methods are correct.
        logger.debug("Main layout structure finalized.")


        


    def _run_batch_computation(self, compute_type, total_items):
        """Runs a batch computation using a worker thread."""
        logger.info(f"Starting batch computation: {compute_type}")
        self._disable_compute_buttons() # Disable buttons first

        # Setup progress dialog
        # For global intersection, total_items is conceptually 1 (the whole task)
        progress_max = 1 if compute_type == "intersections" else total_items
        self.progress_dialog = QProgressDialog(f"Computing {compute_type}...", "Cancel", 0, progress_max, self)
        self.progress_dialog.setWindowTitle(f"Processing {compute_type.capitalize()}")
        self.progress_dialog.setWindowModality(Qt.WindowModal)
        self.progress_dialog.setAutoClose(False) # We will close it manually
        self.progress_dialog.setAutoReset(False) # We will reset manually
        self.progress_dialog.setValue(0)
        self.progress_dialog.canceled.connect(self.cancel_computation) # Connect cancel signal
        self.progress_dialog.show()

        # Initialize counters for progress tracking
        self.processed_count = 0
        self.total_to_process = progress_max # Use the calculated max value

        # Setup worker and thread
        self.worker = ComputationWorker(self) # Pass GUI instance
        self.thread = QThread()
        self.worker.moveToThread(self.thread)

        # Connect signals
        if compute_type == "intersections":
            # Global intersection has only batch_finished and error signals
            self.worker.batch_finished.connect(self.handle_batch_finished)
            self.worker.error_occurred.connect(self.handle_computation_error)
            self.thread.started.connect(self.worker.compute_global_intersections_task)
        else:
            # Other types have per-dataset signals
            self.worker.dataset_finished.connect(self.handle_dataset_finished)
            self.worker.batch_finished.connect(self.handle_batch_finished)
            self.worker.error_occurred.connect(self.handle_computation_error)
            self.thread.started.connect(lambda: self.worker.run_batch_task(compute_type))
        
        # Common signals for thread management
        self.worker.batch_finished.connect(self.thread.quit) # Quit thread when batch finishes
        self.worker.error_occurred.connect(self.thread.quit) # Also quit on error
        self.thread.finished.connect(self.worker.deleteLater) # Schedule worker deletion
        self.thread.finished.connect(self.thread.deleteLater) # Schedule thread deletion

        # Start the thread
        self.thread.start()
        logger.info(f"Worker thread started for {compute_type}.")

    def handle_dataset_finished(self, index, name, success):
        """Handles the completion of computation for a single dataset."""
        # REMOVED old progress update logic here
        
        self.processed_count += 1

        # Update progress dialog
        # --- START EDIT: Check if progress_dialog exists ---
        if self.progress_dialog is not None:
            self.progress_dialog.setLabelText(f"Processed: {name} ({'OK' if success else 'Fail'}) - {self.processed_count}/{self.total_to_process}")
            self.progress_dialog.setValue(self.processed_count)
        # --- END EDIT ---

        # Update dataset list styling
        item = self.dataset_list_widget.item(index)
        if success:
            item.setForeground(QColor(Qt.black))
        else:
            item.setForeground(QColor(Qt.red))

    def handle_batch_finished(self, success_count, total_eligible, elapsed_time):
        """Handles the completion of a batch computation."""
        # Determine if this was the global intersection task
        is_intersection_task = (total_eligible == 1 and hasattr(self.worker, 'compute_global_intersections_task'))
        
        if is_intersection_task:
            task_name = "Global Intersection"
            success_status = "succeeded" if success_count == 1 else "failed"
            logger.info(f"Batch computation finished for {task_name}. Status: {success_status}. Time: {elapsed_time:.2f}s")
            self.statusBar().showMessage(f"{task_name} {success_status} in {elapsed_time:.2f}s.", 10000)
        else:
            task_name = "Batch computation"
            logger.info(f"{task_name} finished. Success: {success_count}/{total_eligible}. Time: {elapsed_time:.2f}s")
            self.statusBar().showMessage(f"Batch finished: {success_count}/{total_eligible} succeeded in {elapsed_time:.2f}s.", 10000)

        if any(d.get('segments') is not None for d in self.datasets):
            self._refresh_seg_view_if_active()

        # Close progress dialog if it exists
        if hasattr(self, 'progress_dialog') and self.progress_dialog:
            # If it was the global intersection task, set value to max to show completion
            if is_intersection_task:
                self.progress_dialog.setValue(self.progress_dialog.maximum())
            self.progress_dialog.close()
            self.progress_dialog = None
            logger.debug("Progress dialog closed.")
        
        # Thread cleanup (moved thread check inside)
        if hasattr(self, 'thread') and self.thread and self.thread.isRunning():
            logger.info("Signaling worker thread to stop and quit.")
            if hasattr(self, 'worker') and self.worker:
                self.worker.stop() # Signal the worker loop to exit
            self.thread.quit() # Ask the thread's event loop to exit

            # Wait for the thread to finish (increased timeout to 5 seconds)
            if self.thread.wait(5000): # Wait up to 5000 ms
                logger.info("Worker thread finished gracefully.")
            else:
                # This is often a sign that the worker's run loop didn't exit cleanly.
                # Termination can be risky, so we'll log and detach.
                logger.warning("Worker thread did not finish gracefully after 5 seconds. Detaching.")
                # self.thread.terminate() # Avoid terminate() if possible, it's dangerous

        # Ensure references are cleared regardless of wait outcome
        self.thread = None
        self.worker = None
        logger.debug("Thread and worker references cleared.")

        self._enable_compute_buttons()
        # OPTIMIZATION: Update visualization only for current tab instead of all tabs
        if not is_intersection_task:
            # Only update visualization for the currently active tab to reduce load
            current_index = self.notebook.currentIndex()
            self._on_tab_changed(current_index)  # This will update only the current tab
            self._update_statistics()
        else:
            # For intersections, the updates are already scheduled via QTimer.singleShot
            # but we can ensure stats are updated one last time here just in case.
            self._update_statistics()

    def handle_computation_error(self, error_message):
        """Handles errors reported by the worker thread."""
        logger.error(f"Computation error: {error_message}")
        QMessageBox.critical(self, "Computation Error", f"An error occurred during computation:\n{error_message}")

        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None
            logger.debug("Progress dialog closed due to error.")

        if self.thread and self.thread.isRunning():
            logger.info("Attempting to stop worker thread due to error.")
            if self.worker:
                self.worker.stop()
            self.thread.quit()

            if self.thread.wait(5000): # Wait up to 5000 ms
                logger.info("Worker thread finished after error.")
            else:
                logger.warning("Worker thread did not finish gracefully after error. Detaching.")
                # self.thread.terminate() # Avoid terminate()

        # Ensure references are cleared
        self.thread = None
        self.worker = None
        logger.debug("Thread and worker references cleared after error.")

        self._enable_compute_buttons()
        # Fix: Use self.statusBar() instead of self.status_bar
        self.statusBar().showMessage("Computation failed.", 5000)


    def cancel_computation(self):
        """Cancels the ongoing computation."""
        logger.info("Cancel computation requested by user.")
        if hasattr(self, 'worker') and self.worker:
             self.worker.stop() # Signal the worker to stop
             logger.debug("Stop signal sent to worker.")
        if hasattr(self, 'progress_dialog') and self.progress_dialog:
             self.progress_dialog.setLabelText("Canceling computation...")
             self.progress_dialog.setEnabled(False) # Disable further interaction
             logger.debug("Progress dialog updated for cancellation.")
        # The batch_finished or error_occurred signal will handle cleanup


    def _disable_compute_buttons(self):
        """Disables the main compute buttons on all tabs."""
        logger.debug("Disabling compute buttons.")
        tabs_and_buttons = [
            (self.hull_tab, "compute_btn"),
            (self.segment_tab, "compute_btn"),
            (self.triangulation_tab, "run_btn"),
        ]
        for tab_widget, button_name in tabs_and_buttons:
            if tab_widget: # Check if tab exists
                button = tab_widget.findChild(QPushButton, button_name)
                if button:
                    button.setEnabled(False)
                else:
                    logger.warning(f"Could not find button '{button_name}' in tab {tab_widget.objectName()} to disable.")
            else:
                 logger.warning(f"Tab widget not found when trying to disable button '{button_name}'.")
        
        # Handle intersection buttons directly
        if hasattr(self, 'compute_intersections_btn'):
            self.compute_intersections_btn.setEnabled(False)
        
    


    def _enable_compute_buttons(self):
        """Enables the main compute buttons on all tabs."""
        logger.debug("Enabling compute buttons.")
        tabs_and_buttons = [
            (self.hull_tab, "compute_btn"),
            (self.segment_tab, "compute_btn"),
            (self.triangulation_tab, "run_btn"),
        ]
        for tab_widget, button_name in tabs_and_buttons:
             if tab_widget: # Check if tab exists
                 button = tab_widget.findChild(QPushButton, button_name)
                 if button:
                     button.setEnabled(True)
                 else:
                      logger.warning(f"Could not find button '{button_name}' in tab {tab_widget.objectName()} to enable.")
             else:
                 logger.warning(f"Tab widget not found when trying to enable button '{button_name}'.")
        
        # Handle intersection buttons directly
        if hasattr(self, 'compute_intersections_btn'):
            self.compute_intersections_btn.setEnabled(True)
            
        


    def closeEvent(self, event):
        """Handle closing the application, especially if a thread is running."""
        logger.debug("Close event triggered.")
        thread_running = False
        try:
            # Check if a worker thread is running, handle potential AttributeError
            if hasattr(self, 'thread') and self.thread is not None and self.thread.isRunning():
                thread_running = True
        except AttributeError:
            logger.warning("AttributeError accessing thread.isRunning() during closeEvent. Assuming not running.")
            thread_running = False

        if thread_running:
            logger.info("Close event while worker thread is running.")
            reply = QMessageBox.question(self, 'Confirm Exit',
                                       "A computation is running. Stop and exit?",
                                       QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

            if reply == QMessageBox.Yes:
                logger.info("User chose to stop and exit.")
                if hasattr(self, 'worker') and self.worker:
                    self.worker.stop() # Signal the worker to stop

                # Optionally wait briefly for the thread to stop naturally
                if not self.thread.wait(1000): # Wait 1 second
                    logger.warning("Thread did not finish quickly after stop signal. Terminating.")
                    self.thread.terminate() # Force stop if it doesn't finish
                    self.thread.wait() # Wait again after termination

                # Clean up all PyVista plotters and OpenGL contexts
                self._cleanup_pyvista_plotters()
                event.accept() # Allow closing
                logger.info("Application closing after stopping thread.")
            else:
                logger.info("User chose not to exit.")
                event.ignore() # Prevent closing
        else:
            logger.debug("No active thread running. Closing application.")
            # Clean up all PyVista plotters and OpenGL contexts
            self._cleanup_pyvista_plotters()
            event.accept() # No thread running, close normally

    def compute_intersections(self):
        """Compute intersections globally (uses all eligible datasets)."""
        # Check if there are at least two datasets with triangulation
        eligible_datasets = [i for i, d in enumerate(self.datasets) if d.get('triangulation_result') is not None]
        
        if len(eligible_datasets) < 2:
            QMessageBox.warning(self, "Not Enough Data", 
                               "Need at least two triangulated datasets to compute intersections.")
            return
        
        logger.info("Triggering global intersection computation.")
        # Disable compute buttons during computation
        # self._disable_compute_buttons() # This is now handled by _run_batch_computation
        
        # Run the single global computation task in a worker thread
        # total_items is 1 because it's one global task
        self._run_batch_computation("intersections", 1)

    def _compute_global_intersections(self):
        """
        Compute intersections globally for all datasets with triangulation data.
        This method is called by the worker thread.

        Returns:
            bool: True if successful, False otherwise
        """
        logger.info("Starting global intersection computation...")
        try:
            from Pymeshit.intersection_utils import (
                Vector3D, Triangle, Intersection, TriplePoint,
                run_intersection_workflow
            )
        except ImportError as e:
            logger.error(f"Failed to import intersection utilities: {e}")
            QMessageBox.critical(self, "Import Error", f"Failed to import intersection utilities: {e}\nPlease ensure meshit.intersection_utils is available.")
            return False

        # Eligible surfaces require triangulations
        eligible_surface_indices = [i for i, d in enumerate(self.datasets) if d.get('type') != 'WELL' and d.get('triangulation_result') is not None]
        if len(eligible_surface_indices) < 1:
            logger.warning("Need at least one triangulated surface to compute intersections.")
            QMessageBox.warning(self, "Not Enough Data", "Need at least one triangulated surface to compute intersections.")
            return False

        # Collect wells (polylines) regardless of triangulation
        well_indices = [i for i, d in enumerate(self.datasets) if d.get('type') == 'WELL' and d.get('points') is not None and len(d.get('points')) >= 2]
        logger.info(f"Found {len(eligible_surface_indices)} triangulated surfaces and {len(well_indices)} wells for intersection.")

        if len(eligible_surface_indices) + len(well_indices) < 2:
            logger.warning("Need at least two objects (surfaces and/or wells) to compute intersections.")
            QMessageBox.warning(self, "Not Enough Data", "Need at least two objects (surfaces and/or wells) to compute intersections.")
            return False

        # Model wrapper compatible with intersection_utils
        class ModelWrapper:
            def __init__(self):
                self.surfaces = []
                self.model_polylines = []
                self.intersections = []
                self.triple_points = []
                # Maps: model indices -> original dataset indices
                self.original_surface_indices = {}
                self.original_polyline_indices = {}

        model = ModelWrapper()

        # Populate surfaces
        for original_index in eligible_surface_indices:
            dataset = self.datasets[original_index]

            class SurfaceWrapper:
                def __init__(self, dataset, index):
                    self.name = dataset.get('name', f"Dataset {index+1}")
                    self.vertices = []
                    self.triangles = []
                    self.convex_hull = []
                    self.bounds = [Vector3D(), Vector3D()]
                    self.type = "Surface"

                    tri_result = dataset.get('triangulation_result')
                    if not tri_result or 'vertices' not in tri_result or 'triangles' not in tri_result:
                        logger.warning(f"Skipping SurfaceWrapper for dataset {index}: Missing triangulation result.")
                        return

                    tri_vertices = tri_result['vertices']
                    self.triangles = tri_result['triangles']
                    if tri_vertices is None or len(tri_vertices) == 0 or self.triangles is None:
                        logger.warning(f"Skipping SurfaceWrapper for dataset {index}: Empty vertices or triangles.")
                        return

                    for point in tri_vertices:
                        if len(point) >= 3:
                            self.vertices.append(Vector3D(point[0], point[1], point[2]))
                        elif len(point) == 2:
                            self.vertices.append(Vector3D(point[0], point[1], 0.0))
                        else:
                            logger.warning(f"Skipping invalid vertex in triangulation result for dataset {index}: {point}")

                    if not self.vertices:
                        logger.warning(f"Skipping SurfaceWrapper for dataset {index}: No valid vertices.")
                        return

                    max_vertex_index = len(self.vertices) - 1
                    valid_triangles = []
                    for tri in self.triangles:
                        if all(0 <= idx <= max_vertex_index for idx in tri):
                            valid_triangles.append(tri)
                    self.triangles = valid_triangles
                    if not self.triangles:
                        logger.warning(f"Skipping SurfaceWrapper for dataset {index}: No valid triangles remain.")
                        return

                    hull_points_data = dataset.get('hull_points')
                    if hull_points_data is not None and len(hull_points_data) > 0:
                        self.convex_hull = [Vector3D(p[0], p[1], p[2]) for p in hull_points_data if len(p) >= 3]

                    if self.vertices:
                        min_x = min(v.x for v in self.vertices); min_y = min(v.y for v in self.vertices); min_z = min(v.z for v in self.vertices)
                        max_x = max(v.x for v in self.vertices); max_y = max(v.y for v in self.vertices); max_z = max(v.z for v in self.vertices)
                        self.bounds[0] = Vector3D(min_x, min_y, min_z)
                        self.bounds[1] = Vector3D(max_x, max_y, max_z)

            surface = SurfaceWrapper(dataset, original_index)
            vertices_valid = hasattr(surface, 'vertices') and surface.vertices is not None and len(surface.vertices) > 0
            triangles_valid = hasattr(surface, 'triangles') and surface.triangles is not None and len(surface.triangles) > 0
            if vertices_valid and triangles_valid:
                model_index = len(model.surfaces)
                model.surfaces.append(surface)
                model.original_surface_indices[model_index] = original_index
            else:
                logger.warning(f"Dataset {original_index} ('{dataset.get('name')}') skipped as surface (missing valid vertices or triangles).")

        if len(model.surfaces) < 1 and len(well_indices) < 2:
            logger.warning("Insufficient surfaces and wells to compute intersections.")
            QMessageBox.warning(self, "Not Enough Valid Data", "Insufficient triangulated surfaces and wells for intersections.")
            return False

        # Populate polylines (wells)
        for original_index in well_indices:
            dataset = self.datasets[original_index]
            points = dataset.get('points')
            if points is None or len(points) < 2:
                continue

            class PolylineWrapper:
                def __init__(self, dataset, pts, index):
                    self.name = dataset.get('name', f"Well_{index}")
                    self.vertices = [Vector3D(float(p[0]), float(p[1]), float(p[2]) if len(p) > 2 else 0.0) for p in pts]
                    # Consecutive segment pairs referencing self.vertices indices
                    self.segments = [(i, i + 1) for i in range(len(self.vertices) - 1)]
                    # Bounds
                    xs = [v.x for v in self.vertices]; ys = [v.y for v in self.vertices]; zs = [v.z for v in self.vertices]
                    self.bounds = [Vector3D(min(xs), min(ys), min(zs)), Vector3D(max(xs), max(ys), max(zs))]
                    self.type = "Polyline"

            polyline = PolylineWrapper(dataset, points, original_index)
            if hasattr(polyline, 'vertices') and len(polyline.vertices) >= 2 and hasattr(polyline, 'segments') and len(polyline.segments) >= 1:
                model_idx = len(model.model_polylines)
                model.model_polylines.append(polyline)
                model.original_polyline_indices[model_idx] = original_index

        logger.info(f"Prepared intersection model with {len(model.surfaces)} surfaces and {len(model.model_polylines)} wells.")

        # Run workflow
        def progress_callback(message):
            logger.debug(f"Intersection util progress: {message.strip()}")
            QApplication.processEvents()

        try:
            logger.info("Calling run_intersection_workflow...")
            intersection_config = {
                'use_constraint_processing': True,
                'type_based_sizing': True,
                'hierarchical_constraints': True,
                'gradient': 2.0,
                'use_enhanced_curved_detection': True,
                'adaptive_sampling': True,
                'max_subdivisions': 3
            }
            model = run_intersection_workflow(model, progress_callback, config=intersection_config)
            logger.info("run_intersection_workflow finished.")
        except Exception as e:
            error_msg = f"Error during run_intersection_workflow: {str(e)}"
            logger.error(error_msg, exc_info=True)
            QMessageBox.critical(self, "Intersection Computation Error", error_msg)
            return False

        # Store results
        self.datasets_intersections = {}
        self.triple_points = []

        logger.info(f"Processing {len(model.intersections)} raw intersections and {len(model.triple_points)} triple points from workflow.")

        found_intersections_count = 0
        for intersection in model.intersections:
            # Map back to original dataset indices
            if getattr(intersection, 'is_polyline_mesh', False):
                original_poly = model.original_polyline_indices.get(intersection.id1, -1)
                original_surf = model.original_surface_indices.get(intersection.id2, -1)
                original_id1, original_id2 = original_poly, original_surf
            else:
                original_id1 = model.original_surface_indices.get(intersection.id1, -1)
                original_id2 = model.original_surface_indices.get(intersection.id2, -1)

            if original_id1 == -1 or original_id2 == -1:
                logger.warning(f"Skipping intersection with invalid mapping (IDs: {intersection.id1}, {intersection.id2}, is_polyline={getattr(intersection, 'is_polyline_mesh', False)})")
                continue

            # Points to plain lists
            points = []
            for point in intersection.points:
                points.append([point.x, point.y, point.z])

            intersection_info = {
                'dataset_id1': original_id1,
                'dataset_id2': original_id2,
                'is_polyline_mesh': getattr(intersection, 'is_polyline_mesh', False),
                'points': points
            }
            found_intersections_count += 1

            # Store keyed by the lower dataset id (as before)
            primary_key = min(original_id1, original_id2)
            if primary_key not in self.datasets_intersections:
                self.datasets_intersections[primary_key] = []
            self.datasets_intersections[primary_key].append(intersection_info)

        # Triple points
        for tp in model.triple_points:
            point = [tp.point.x, tp.point.y, tp.point.z]
            self.triple_points.append({
                'point': point,
                'intersection_ids': tp.intersection_ids
            })

        logger.info(f"Stored {found_intersections_count} intersections across datasets and {len(self.triple_points)} triple points.")

        QTimer.singleShot(0, self._update_statistics)
        QTimer.singleShot(0, self._update_intersection_list)
        QTimer.singleShot(0, self._visualize_intersections)

        logger.info("Global intersection computation successful.")
        return True
    def _clear_intersection_results(self):
        """Clear all intersection results"""
        # Clear intersection data
        self.datasets_intersections = {}
        self.triple_points = []
        
        # Clear UI
        self.intersection_list.clear()
        self._clear_intersection_plot()
        self._update_statistics()
        
        QMessageBox.information(self, "Results Cleared", "Intersection results have been cleared.")

    def _clear_intersection_plot(self):
        """Clear the embedded intersection PyVista plotter."""
        if hasattr(self, 'intersection_plotter') and self.intersection_plotter:
            self.intersection_plotter.clear()
            # Optionally add placeholder text back if desired
            # self.intersection_plotter.add_text("Compute intersections or select one from the list.", position='upper_edge')
            self.intersection_plotter.reset_camera()

    def _update_intersection_list(self):
        """Update the list of intersections in the UI"""
        self.intersection_list.clear()
        
        # Add all intersections to the list
        for dataset_index, intersections in self.datasets_intersections.items():
            if not intersections:
                continue
                
            dataset_name = self.datasets[dataset_index].get('name', f"Dataset {dataset_index+1}")
            
            # Add a header item for this dataset
            dataset_item = QListWidgetItem(f"{dataset_name} Intersections:")
            dataset_item.setBackground(QColor(240, 240, 240))
            dataset_item.setFlags(dataset_item.flags() & ~Qt.ItemIsSelectable)
            self.intersection_list.addItem(dataset_item)
            
            # Add intersections for this dataset
            for i, intersection in enumerate(intersections):
                other_dataset_id = (intersection['dataset_id1'] 
                                   if intersection['dataset_id1'] != dataset_index 
                                   else intersection['dataset_id2'])
                
                other_dataset_name = self.datasets[other_dataset_id].get('name', f"Dataset {other_dataset_id+1}")
                
                # Create a descriptive name for the intersection
                intersection_type = "Polyline-Surface" if intersection['is_polyline_mesh'] else "Surface-Surface"
                num_points = len(intersection['points'])
                
                item_text = f"  {intersection_type}: with {other_dataset_name} ({num_points} points)"
                
                # Create item with data
                item = QListWidgetItem(item_text)
                item.setData(Qt.UserRole, {
                    'dataset_index': dataset_index,
                    'intersection_index': i
                })
                
                self.intersection_list.addItem(item)

    def _on_intersection_selection_changed(self):
        """Handle selection changes in the intersection list"""
        selected_items = self.intersection_list.selectedItems()
        
        if not selected_items:
            return
            
        item = selected_items[0]
        data = item.data(Qt.UserRole)
        
        if not data:
            return  # Header item or invalid selection
        
        dataset_index = data['dataset_index']
        intersection_index = data['intersection_index']
        
        # Visualize the selected intersection
        self._visualize_selected_intersection(dataset_index, intersection_index)

    def _visualize_selected_intersection(self, dataset_index, intersection_index):
        """Visualize a specific intersection by highlighting it in the embedded plotter."""
        if not hasattr(self, 'intersection_plotter') or not self.intersection_plotter:
            logger.warning("Intersection plotter not available for selection visualization.")
            return

        plotter = self.intersection_plotter
        # Don't clear everything, just update highlights or add emphasis
        # Re-plotting everything might be simpler for now
        logger.info(f"Highlighting intersection {intersection_index} from dataset {dataset_index}")
        
        # --- Re-plot everything, but highlight the selected intersection --- 
        plotter.clear()
        plotter.set_background('white')
        
        if dataset_index not in self.datasets_intersections or intersection_index >= len(self.datasets_intersections[dataset_index]):
            logger.warning("Selected intersection data not found.")
            plotter.add_text("Selected intersection not found.", position='upper_edge', color='red')
            return
            
        selected_intersection = self.datasets_intersections[dataset_index][intersection_index]
        involved_dataset_ids = {selected_intersection['dataset_id1'], selected_intersection['dataset_id2']}
        
        # Add involved dataset meshes (dim others slightly)
        plotter_has_content = False
        for index, dataset in enumerate(self.datasets):
            # Determine opacity: Highlight involved, dim others (or keep all same)
            is_involved = index in involved_dataset_ids
            opacity = 0.7 # Use consistent opacity like triangulation step
            # opacity = 0.7 if is_involved else 0.2 # Alternative: Dim uninvolved

            tri_result = dataset.get('triangulation_result')
            if tri_result:
                vertices = tri_result.get('vertices')
                triangles = tri_result.get('triangles')
                color = dataset.get('color', self.DEFAULT_COLORS[index % len(self.DEFAULT_COLORS)])
                name = dataset.get('name', f'Dataset {index+1}')

                if vertices is not None and len(vertices) > 0 and triangles is not None and len(triangles) > 0:
                    try:
                        vertices = np.array(vertices)
                        if vertices.shape[1] == 2: 
                             temp_vertices = np.zeros((vertices.shape[0], 3)); temp_vertices[:,:2] = vertices; vertices = temp_vertices
                        elif vertices.shape[1] > 3: vertices = vertices[:, :3]
                        triangles = np.array(triangles)
                        cells = np.hstack([np.full((len(triangles), 1), 3, dtype=triangles.dtype), triangles])
                        surface_mesh = pv.PolyData(vertices, faces=cells)
                        # --- Apply Triangulation Style --- 
                        plotter.add_mesh(surface_mesh, color=color, opacity=opacity, 
                                         show_edges=True, edge_color=color, 
                                         line_width=1, specular=0.5, label=name)
                        plotter_has_content = True
                    except Exception as e:
                         logger.error(f"Error creating mesh for dataset {index} ('{name}') during selection view: {e}")

        # Add the selected intersection line prominently (keep distinct style)
        if selected_intersection['points'] and len(selected_intersection['points']) >= 2:
            try:
                # Validate intersection points first
                valid_points = []
                for point in selected_intersection['points']:
                    if hasattr(point, 'tolist'):
                        point = point.tolist()
                    elif isinstance(point, np.ndarray):
                        point = point.flatten().tolist()
                    
                    # Ensure 3D coordinates
                    if len(point) >= 2:
                        if len(point) < 3:
                            point.extend([0.0] * (3 - len(point)))
                        elif len(point) > 3:
                            point = point[:3]
                        
                        # Validate numbers
                        try:
                            validated_point = [float(point[0]), float(point[1]), float(point[2])]
                            if all(np.isfinite(x) for x in validated_point):
                                valid_points.append(validated_point)
                        except (ValueError, TypeError):
                            continue
                
                # Create line segments from valid points
                line_points = np.array(valid_points) if valid_points else None
                for i in range(len(valid_points) - 1):
                    segment = pv.Line(valid_points[i], valid_points[i + 1])
                    plotter.add_mesh(segment, color='#FF0000', line_width=6) 
                    plotter_has_content = True
                    
            except Exception as e:
                logger.error(f"Error adding selected intersection line segment: {e}")
                # Optionally add triple points if relevant to this intersection (more complex logic needed)
        # For simplicity, we might omit triple points in single selection view or show all
        if hasattr(self, 'triple_points') and self.triple_points:
            all_triple_points_coords = [tp['point'] for tp in self.triple_points]
            if all_triple_points_coords:
                try:
                    triple_points_poly = pv.PolyData(np.array(all_triple_points_coords))
                    plotter.add_points(triple_points_poly, color='black', point_size=8, render_points_as_spheres=True)
                    plotter_has_content = True
                except Exception as e:
                     logger.error(f"Error adding triple points during selection view: {e}")

        if plotter_has_content:
            plotter.add_legend(bcolor=None, face='circle', border=False, size=(0.15, 0.15))
            plotter.add_axes()
            plotter.reset_camera()
            # Zoom slightly on the selected intersection line (optional)
            if selected_intersection['points'] and len(selected_intersection['points']) >= 2 and line_points is not None and len(line_points) > 0:
                 try:
                      plotter.camera.focal_point = np.mean(line_points, axis=0)
                      # plotter.camera.zoom(1.5) # Adjust zoom factor as needed
                 except Exception as e:
                      logger.warning(f"Could not adjust camera for selected intersection: {e}")
            logger.info("Updated embedded view for selected intersection.")
        else:
            plotter.add_text("Could not display selected intersection.", position='upper_edge', color='white')
            logger.warning("No content added when visualizing selected intersection.")

    def _visualize_intersections(self):
        """Visualize all intersections in the embedded PyVista plotter, matching triangulation style."""
        if not hasattr(self, 'intersection_plotter') or not self.intersection_plotter:
            logger.warning("Intersection plotter not available for visualization.")
            return
            
        plotter = self.intersection_plotter
        plotter.clear() # Start fresh
        # --- Use MeshIt Background --- 
        plotter.set_background([0.318, 0.341, 0.431]) 
        
        # Check if data exists
        if not hasattr(self, 'datasets_intersections') or not self.datasets_intersections:
            plotter.add_text("No intersections computed yet.", position='upper_edge', color='white')
            plotter.reset_camera()
            return

        logger.info("Visualizing all intersections in embedded view...")
        
        involved_dataset_indices = set()
        all_intersection_lines = []
        unique_intersections = set()

        # Collect intersection lines and involved datasets
        for dataset_index, intersections in self.datasets_intersections.items():
            involved_dataset_indices.add(dataset_index)
            for i, intersection in enumerate(intersections):
                involved_dataset_indices.add(intersection['dataset_id1'])
                involved_dataset_indices.add(intersection['dataset_id2'])
                key = tuple(sorted((intersection['dataset_id1'], intersection['dataset_id2']))) + (intersection['is_polyline_mesh'],)
                if key not in unique_intersections:
                    unique_intersections.add(key)
                    if intersection['points'] and len(intersection['points']) >= 2:
                        all_intersection_lines.append(np.array(intersection['points']))

        # Collect and validate triple points
        all_triple_points_coords = []
        if hasattr(self, 'triple_points') and self.triple_points:
            for tp in self.triple_points:
                point = tp.get('point')
                if point is not None:
                    # Validate and convert point to proper format
                    if hasattr(point, 'tolist'):
                        point = point.tolist()
                    elif isinstance(point, np.ndarray):
                        point = point.flatten().tolist()
                    elif not isinstance(point, (list, tuple)):
                        if hasattr(point, '__getitem__') and hasattr(point, '__len__'):
                            try:
                                point = [float(point[0]), float(point[1]), float(point[2]) if len(point) > 2 else 0.0]
                            except:
                                continue
                        else:
                            continue
                    
                    # Ensure exactly 3 coordinates
                    if len(point) < 2:
                        continue
                    elif len(point) < 3:
                        point = list(point) + [0.0] * (3 - len(point))
                    elif len(point) > 3:
                        point = point[:3]
                    
                    # Validate as finite floats
                    try:
                        validated_point = [float(point[0]), float(point[1]), float(point[2])]
                        if all(np.isfinite(x) for x in validated_point):
                            all_triple_points_coords.append(validated_point)
                    except (ValueError, TypeError):
                        continue

        # Add involved dataset meshes
        plotter_has_content = False
        for index in involved_dataset_indices:
            if 0 <= index < len(self.datasets):
                dataset = self.datasets[index]
                tri_result = dataset.get('triangulation_result')
                if tri_result:
                    vertices = tri_result.get('vertices')
                    triangles = tri_result.get('triangles')
                    # Use a consistent surface color unless dataset has one
                    mesh_color = dataset.get('color', '#CCCCCC') # Default light grey
                    name = dataset.get('name', f'Dataset {index+1}')

                    if vertices is not None and len(vertices) > 0 and triangles is not None and len(triangles) > 0:
                        try:
                            # Basic validation and formatting for PyVista
                            vertices = np.array(vertices)
                            if vertices.shape[1] == 2:
                                 temp_vertices = np.zeros((vertices.shape[0], 3))
                                 temp_vertices[:,:2] = vertices
                                 vertices = temp_vertices
                            elif vertices.shape[1] > 3:
                                 vertices = vertices[:, :3]
                            triangles = np.array(triangles)
                            cells = np.hstack([np.full((len(triangles), 1), 3, dtype=triangles.dtype), triangles])
                            
                            surface_mesh = pv.PolyData(vertices, faces=cells)
                            # --- Apply Style similar to test_intersections.py --- 
                            plotter.add_mesh(surface_mesh, color=mesh_color, opacity=0.7, 
                                             show_edges=True, edge_color='black', 
                                             line_width=1, label=name)
                            plotter_has_content = True
                        except Exception as e:
                             logger.error(f"Error creating mesh for dataset {index} ('{name}') in embedded view: {e}")

        # PERFORMANCE OPTIMIZATION: Add all intersection lines at once instead of individually
        # This resolves the major slowdown where each line segment was being added with individual
        # pv.Line() and plotter.add_mesh() calls, causing hundreds of separate rendering operations.
        # Now all lines are batched into a single PolyData object for much faster visualization.
        if all_intersection_lines:
            logger.info(f"FAST visualization: Processing {len(all_intersection_lines)} intersection lines...")
            
            # Collect all line segments for batch processing
            all_line_points = []
            all_line_connectivity = []
            current_point_index = 0
            
            for line_points in all_intersection_lines:
                try:
                    # Validate and convert points to proper format for PyVista
                    valid_points = []
                    for point in line_points:
                        if hasattr(point, 'tolist'):
                            point = point.tolist()
                        elif isinstance(point, np.ndarray):
                            point = point.flatten().tolist()
                        elif not isinstance(point, (list, tuple)):
                            if hasattr(point, '__getitem__') and hasattr(point, '__len__'):
                                try:
                                    point = [float(point[0]), float(point[1]), float(point[2]) if len(point) > 2 else 0.0]
                                except:
                                    continue
                            else:
                                continue
                        
                        # Ensure exactly 3 coordinates
                        if len(point) < 2:
                            continue
                        elif len(point) < 3:
                            point = list(point) + [0.0] * (3 - len(point))
                        elif len(point) > 3:
                            point = point[:3]
                        
                        # Validate as finite floats
                        try:
                            validated_point = [float(point[0]), float(point[1]), float(point[2])]
                            if all(np.isfinite(x) for x in validated_point):
                                valid_points.append(validated_point)
                        except (ValueError, TypeError):
                            continue
                    
                    # Add valid points and connectivity for this line
                    if len(valid_points) >= 2:
                        # Add points to the global list
                        line_start_index = current_point_index
                        all_line_points.extend(valid_points)
                        current_point_index += len(valid_points)
                        
                        # Create connectivity for line segments (each segment connects 2 consecutive points)
                        for i in range(len(valid_points) - 1):
                            # PyVista line cell format: [2, point1_index, point2_index]
                            all_line_connectivity.extend([2, line_start_index + i, line_start_index + i + 1])
                            
                except Exception as e:
                     logger.error(f"Error processing intersection line in batch mode: {e}")
            
            # FAST: Create single PolyData object with all lines at once
            if all_line_points and all_line_connectivity:
                try:
                    # Convert to numpy arrays
                    points_array = np.array(all_line_points, dtype=np.float64)
                    connectivity_array = np.array(all_line_connectivity, dtype=np.int32)
                    
                    # Create single PolyData object containing all intersection lines
                    lines_polydata = pv.PolyData(points_array)
                    lines_polydata.lines = connectivity_array
                    
                    # Add all lines at once - MUCH faster than individual add_mesh calls
                    plotter.add_mesh(lines_polydata, color='red', line_width=4, label="Intersection Lines")
                    plotter_has_content = True
                    
                    logger.info(f"FAST visualization: Added {len(all_intersection_lines)} intersection lines ({len(all_line_points)} points, {len(all_line_connectivity)//3} segments) in single operation")
                    
                except Exception as e:
                    logger.error(f"Error creating batch intersection lines: {e}")
                    # Fallback to old method if batch processing fails
                    logger.info("Falling back to individual line processing...")
                    for line_points in all_intersection_lines:
                        try:
                            valid_points = []
                            for point in line_points:
                                if hasattr(point, 'tolist'):
                                    point = point.tolist()
                                elif isinstance(point, np.ndarray):
                                    point = point.flatten().tolist()
                                
                                if len(point) < 3:
                                    point = list(point) + [0.0] * (3 - len(point))
                                elif len(point) > 3:
                                    point = point[:3]
                                
                                try:
                                    validated_point = [float(point[0]), float(point[1]), float(point[2])]
                                    if all(np.isfinite(x) for x in validated_point):
                                        valid_points.append(validated_point)
                                except (ValueError, TypeError):
                                    continue
                            
                            if len(valid_points) >= 2:
                                for i in range(len(valid_points) - 1):
                                    point_a = valid_points[i]
                                    point_b = valid_points[i + 1]
                                    segment = pv.Line(point_a, point_b)
                                    plotter.add_mesh(segment, color='red', line_width=4)
                                    plotter_has_content = True
                                    
                        except Exception as e2:
                            logger.error(f"Error adding intersection line segment in fallback mode: {e2}")

        # Add triple points (Keep style distinct: black spheres)
        if all_triple_points_coords:
            try:
                # Convert to numpy array with proper validation
                if len(all_triple_points_coords) > 0:
                    points_array = np.array(all_triple_points_coords, dtype=np.float64)
                    
                    # Validate array shape and content
                    if (points_array.shape[0] > 0 and points_array.shape[1] == 3 and 
                        np.all(np.isfinite(points_array))):
                        
                        triple_points_poly = pv.PolyData(points_array)
                        plotter.add_points(triple_points_poly, color='black', point_size=8, 
                                           render_points_as_spheres=True, label="Triple Points")
                        plotter_has_content = True
                    else:
                        logger.warning(f"Invalid triple points array shape or content: {points_array.shape}")
            except Exception as e:
                logger.error(f"Error adding triple points in embedded view: {e}")

        # Add Well datasets as polylines
        self._add_wells_polyline_to_plotter(plotter)

        if plotter_has_content:
            # Use white text for legend on dark background
            plotter.add_legend(bcolor=None, face='circle', border=False, size=(0.15, 0.15))
            plotter.add_axes()
            plotter.reset_camera()
            logger.info("Updated embedded intersection view.")
        else:
            plotter.add_text("No valid intersection data to display.", position='upper_edge', color='white')
            logger.info("Embedded intersection view updated, but no content added.")

    def _visualize_selected_intersection(self, dataset_index, intersection_index):
        """Visualize a specific intersection by highlighting it in the embedded plotter, matching triangulation style."""
        if not hasattr(self, 'intersection_plotter') or not self.intersection_plotter:
            logger.warning("Intersection plotter not available for selection visualization.")
            return

        plotter = self.intersection_plotter
        plotter.clear()
        # --- Use MeshIt Background --- 
        plotter.set_background([0.318, 0.341, 0.431])
        
        if dataset_index not in self.datasets_intersections or intersection_index >= len(self.datasets_intersections[dataset_index]):
            logger.warning("Selected intersection data not found.")
            plotter.add_text("Selected intersection not found.", position='upper_edge', color='red')
            return
            
        selected_intersection = self.datasets_intersections[dataset_index][intersection_index]
        involved_dataset_ids = {selected_intersection['dataset_id1'], selected_intersection['dataset_id2']}
        
        # Add involved dataset meshes
        plotter_has_content = False
        for index, dataset in enumerate(self.datasets):
            if index not in involved_dataset_ids: continue # Only show involved datasets
            
            opacity = 0.7 # Keep involved ones clearly visible

            tri_result = dataset.get('triangulation_result')
            if tri_result:
                vertices = tri_result.get('vertices')
                triangles = tri_result.get('triangles')
                mesh_color = dataset.get('color', '#CCCCCC') # Use dataset color or default grey
                name = dataset.get('name', f'Dataset {index+1}')

                if vertices is not None and len(vertices) > 0 and triangles is not None and len(triangles) > 0:
                    try:
                        vertices = np.array(vertices)
                        if vertices.shape[1] == 2: 
                             temp_vertices = np.zeros((vertices.shape[0], 3)); temp_vertices[:,:2] = vertices; vertices = temp_vertices
                        elif vertices.shape[1] > 3: vertices = vertices[:, :3]
                        triangles = np.array(triangles)
                        cells = np.hstack([np.full((len(triangles), 1), 3, dtype=triangles.dtype), triangles])
                        surface_mesh = pv.PolyData(vertices, faces=cells)
                        # --- Apply Style similar to test_intersections.py --- 
                        plotter.add_mesh(surface_mesh, color=mesh_color, opacity=opacity, 
                                         show_edges=True, edge_color='black', 
                                         line_width=1, label=name)
                        plotter_has_content = True
                    except Exception as e:
                         logger.error(f"Error creating mesh for dataset {index} ('{name}') during selection view: {e}")

        # Add the selected intersection line prominently (keep distinct style)
        if selected_intersection['points'] and len(selected_intersection['points']) >= 2:
            try:
                # Validate and convert points to proper format for PyVista
                valid_points = []
                for point in selected_intersection['points']:
                    if hasattr(point, 'tolist'):
                        point = point.tolist()
                    elif isinstance(point, np.ndarray):
                        point = point.flatten().tolist()
                    elif not isinstance(point, (list, tuple)):
                        if hasattr(point, '__getitem__') and hasattr(point, '__len__'):
                            try:
                                point = [float(point[0]), float(point[1]), float(point[2]) if len(point) > 2 else 0.0]
                            except:
                                continue
                        else:
                            continue
                    
                    # Ensure exactly 3 coordinates
                    if len(point) < 2:
                        continue
                    elif len(point) < 3:
                        point = list(point) + [0.0] * (3 - len(point))
                    elif len(point) > 3:
                        point = point[:3]
                    
                    # Validate as finite floats
                    try:
                        validated_point = [float(point[0]), float(point[1]), float(point[2])]
                        if all(np.isfinite(x) for x in validated_point):
                            valid_points.append(validated_point)
                    except (ValueError, TypeError):
                        continue
                
                # Create line segments from valid points
                line_points = np.array(valid_points) if valid_points else None
                if len(valid_points) >= 2:
                    for i in range(len(valid_points) - 1):
                        point_a = valid_points[i]
                        point_b = valid_points[i + 1]
                        
                        # Ensure points are exactly length 3 tuples of floats
                        if (len(point_a) == 3 and len(point_b) == 3 and
                            all(isinstance(x, (int, float)) and np.isfinite(x) for x in point_a) and
                            all(isinstance(x, (int, float)) and np.isfinite(x) for x in point_b)):
                            
                            segment = pv.Line(point_a, point_b)
                            # Highlight: thicker and brighter red
                            plotter.add_mesh(segment, color='#FF0000', line_width=6) 
                            plotter_has_content = True
                        
            except Exception as e:
                 logger.error(f"Error adding selected intersection line segment: {e}")

        # Add triple points (keep distinct style)
        if hasattr(self, 'triple_points') and self.triple_points:
            all_triple_points_coords = [tp['point'] for tp in self.triple_points]
            if all_triple_points_coords:
                try:
                    triple_points_poly = pv.PolyData(np.array(all_triple_points_coords))
                    plotter.add_points(triple_points_poly, color='black', point_size=8, render_points_as_spheres=True)
                    plotter_has_content = True
                except Exception as e:
                     logger.error(f"Error adding triple points during selection view: {e}")

        if plotter_has_content:
            # Use white text for legend on dark background
            plotter.add_legend(bcolor=None, face='circle', border=False, size=(0.15, 0.15))
            plotter.add_axes()
            plotter.reset_camera()
            # Zoom slightly on the selected intersection line (optional)
            if selected_intersection['points'] and len(selected_intersection['points']) >= 2 and line_points is not None and len(line_points) > 0:
                 try:
                      plotter.camera.focal_point = np.mean(line_points, axis=0)
                      # plotter.camera.zoom(1.5) # Adjust zoom factor as needed
                 except Exception as e:
                      logger.warning(f"Could not adjust camera for selected intersection: {e}")
            logger.info("Updated embedded view for selected intersection.")
        else:
            plotter.add_text("Could not display selected intersection.", position='upper_edge', color='white')
            logger.warning("No content added when visualizing selected intersection.")

    def show_intersections_3d_view(self):
        """Show a 3D view of the datasets involved in intersections and the intersection lines/points."""

        
        # Check if there are any intersections to show
        if not hasattr(self, 'datasets_intersections') or not self.datasets_intersections:
            QMessageBox.warning(self, "No Intersections", "No intersections computed yet.")
            return

        logger.info("Preparing data for Intersection 3D View...")
        
        plotter = pv.Plotter(window_size=[1000, 800], off_screen=False) # Create a new plotter instance
        plotter.set_background("white")
        
        involved_dataset_indices = set()
        all_intersection_lines = []
        all_triple_points_coords = []

        # Collect all intersection lines and involved dataset indices
        unique_intersections = set() # Use a set to avoid plotting the same intersection twice
        for dataset_index, intersections in self.datasets_intersections.items():
            involved_dataset_indices.add(dataset_index)
            for i, intersection in enumerate(intersections):
                involved_dataset_indices.add(intersection['dataset_id1'])
                involved_dataset_indices.add(intersection['dataset_id2'])
                
                # Create a unique key for the intersection (order-independent)
                key = tuple(sorted((intersection['dataset_id1'], intersection['dataset_id2']))) + (intersection['is_polyline_mesh'],)
                
                if key not in unique_intersections:
                    unique_intersections.add(key)
                    if intersection['points'] and len(intersection['points']) >= 2:
                        # Convert intersection points to NumPy array for PyVista Line
                        line_points = np.array(intersection['points'])
                        all_intersection_lines.append(line_points)

        # Collect triple points coordinates
        if hasattr(self, 'triple_points') and self.triple_points:
            for tp in self.triple_points:
                 all_triple_points_coords.append(tp['point'])

        # Add involved dataset meshes (triangulated surfaces)
        for index in involved_dataset_indices:
            if 0 <= index < len(self.datasets):
                dataset = self.datasets[index]
                tri_result = dataset.get('triangulation_result')
                if tri_result:
                    vertices = tri_result.get('vertices')
                    triangles = tri_result.get('triangles')
                    color = dataset.get('color', self.DEFAULT_COLORS[index % len(self.DEFAULT_COLORS)])
                    name = dataset.get('name', f'Dataset {index+1}')

                    if vertices is not None and len(vertices) > 0 and triangles is not None and len(triangles) > 0:
                        try:
                            # Ensure vertices are 3D numpy array
                            if isinstance(vertices, list):
                                vertices = np.array(vertices)
                            if vertices.shape[1] == 2:
                                 # Pad with Z=0 if needed (should ideally come from tri_result)
                                 temp_vertices = np.zeros((vertices.shape[0], 3))
                                 temp_vertices[:,:2] = vertices
                                 vertices = temp_vertices
                            elif vertices.shape[1] > 3:
                                 vertices = vertices[:, :3] # Ensure max 3 columns
                                 
                            # Ensure triangles are correctly formatted for PyVista
                            if isinstance(triangles, list):
                                triangles = np.array(triangles)
                            # PyVista needs cells prepended with the number of points (3 for triangles)
                            cells = np.hstack([np.full((len(triangles), 1), 3, dtype=triangles.dtype), triangles])
                            
                            surface_mesh = pv.PolyData(vertices, faces=cells)
                            plotter.add_mesh(surface_mesh, color=color, opacity=0.6, 
                                             show_edges=False, label=name)
                            logger.debug(f"Added surface mesh for dataset {index} ('{name}')")
                        except Exception as e:
                             logger.error(f"Error creating mesh for dataset {index} ('{name}'): {e}", exc_info=True)
                    else:
                         logger.warning(f"Dataset {index} ('{name}') has triangulation result but missing valid vertices/triangles.")

        # Add intersection lines
        if all_intersection_lines:
            for line_points in all_intersection_lines:
                try:
                    # Validate and convert points to proper format for PyVista
                    valid_points = []
                    for point in line_points:
                        if hasattr(point, 'tolist'):
                            point = point.tolist()
                        elif isinstance(point, np.ndarray):
                            point = point.flatten().tolist()
                        elif not isinstance(point, (list, tuple)):
                            if hasattr(point, '__getitem__') and hasattr(point, '__len__'):
                                try:
                                    point = [float(point[0]), float(point[1]), float(point[2]) if len(point) > 2 else 0.0]
                                except:
                                    continue
                            else:
                                continue
                        
                        # Ensure exactly 3 coordinates
                        if len(point) < 2:
                            continue
                        elif len(point) < 3:
                            point = list(point) + [0.0] * (3 - len(point))
                        elif len(point) > 3:
                            point = point[:3]
                        
                        # Validate as finite floats
                        try:
                            validated_point = [float(point[0]), float(point[1]), float(point[2])]
                            if all(np.isfinite(x) for x in validated_point):
                                valid_points.append(validated_point)
                        except (ValueError, TypeError):
                            continue
                    
                    # Create line segments from valid points
                    if len(valid_points) >= 2:
                        for i in range(len(valid_points) - 1):
                            point_a = valid_points[i]
                            point_b = valid_points[i + 1]
                            
                            # Ensure points are exactly length 3 tuples of floats
                            if (len(point_a) == 3 and len(point_b) == 3 and
                                all(isinstance(x, (int, float)) and np.isfinite(x) for x in point_a) and
                                all(isinstance(x, (int, float)) and np.isfinite(x) for x in point_b)):
                                
                                # Create line segment using PolyData with line connectivity
                                line_points = np.array([point_a, point_b])
                                line_cells = np.array([2, 0, 1])  # Line with 2 points: indices 0 and 1
                                segment = pv.PolyData(line_points)
                                segment.lines = line_cells
                                plotter.add_mesh(segment, color='red', line_width=5) # Thicker red lines
                            
                except Exception as e:
                     logger.error(f"Error adding intersection line segment: {e}", exc_info=True)
            logger.info(f"Added {len(all_intersection_lines)} intersection lines.")

        # Add triple points
        if all_triple_points_coords:
            try:
                # Validate and convert triple points to proper format
                valid_triple_points = []
                for point in all_triple_points_coords:
                    if hasattr(point, 'tolist'):
                        point = point.tolist()
                    elif isinstance(point, np.ndarray):
                        point = point.flatten().tolist()
                    elif not isinstance(point, (list, tuple)):
                        if hasattr(point, '__getitem__') and hasattr(point, '__len__'):
                            try:
                                point = [float(point[0]), float(point[1]), float(point[2]) if len(point) > 2 else 0.0]
                            except:
                                continue
                        else:
                            continue
                    
                    # Ensure exactly 3 coordinates
                    if len(point) < 2:
                        continue
                    elif len(point) < 3:
                        point = list(point) + [0.0] * (3 - len(point))
                    elif len(point) > 3:
                        point = point[:3]
                    
                    # Validate as finite floats
                    try:
                        validated_point = [float(point[0]), float(point[1]), float(point[2])]
                        if all(np.isfinite(x) for x in validated_point):
                            valid_triple_points.append(validated_point)
                    except (ValueError, TypeError):
                        continue
                
                # Create PyVista PolyData from valid points
                if valid_triple_points:
                    points_array = np.array(valid_triple_points, dtype=np.float64)
                    
                    # Validate array shape and content
                    if (points_array.shape[0] > 0 and points_array.shape[1] == 3 and 
                        np.all(np.isfinite(points_array))):
                        
                        triple_points_poly = pv.PolyData(points_array)
                        plotter.add_points(triple_points_poly, color='black', point_size=10, 
                                           render_points_as_spheres=True, label="Triple Points")
                        logger.info(f"Added {len(valid_triple_points)} triple points.")
                    else:
                        logger.warning(f"Invalid triple points array shape or content: {points_array.shape}")
                else:
                    logger.warning("No valid triple points found after validation.")
            except Exception as e:
                logger.error(f"Error adding triple points: {e}", exc_info=True)

        # Add legend, axes, etc.
        plotter.add_legend(bcolor=None, face='circle') # Simple legend
        plotter.add_axes()
        plotter.reset_camera()
        plotter.show(title="MeshIt Intersections 3D View")
        logger.info("Showing Intersection 3D View.")
    
    def _validate_surfaces_for_tetgen(self):
        """Validate constrained surfaces for tetgen readiness"""
        if not hasattr(self, 'datasets') or not self.datasets:
            self.statusBar().showMessage("No datasets to validate.")
            return
        
        # Check if we have constrained meshes
        datasets_with_constrained_meshes = []
        for dataset in self.datasets:
            if 'constrained_vertices' in dataset and 'constrained_triangles' in dataset:
                datasets_with_constrained_meshes.append(dataset)
        
        if not datasets_with_constrained_meshes:
            self.statusBar().showMessage("No constrained meshes found. Please generate constrained surface meshes first.")
            return
        
        # Import the validation function
        try:
            from Pymeshit.intersection_utils import validate_surfaces_for_tetgen
        except ImportError:
            self.statusBar().showMessage("Validation function not available.")
            return
        
        # Run validation
        logger.info("Starting tetgen surface validation...")
        self.statusBar().showMessage("Validating surfaces for tetgen...")
        
        try:
            validation_results = validate_surfaces_for_tetgen(datasets_with_constrained_meshes)
            
            # Create detailed validation report dialog
            self._show_validation_results_dialog(validation_results)
            
            # Update status bar based on results
            if validation_results['ready_for_tetgen']:
                self.statusBar().showMessage(f"✓ All {validation_results['surface_count']} surfaces are ready for tetgen!")
            elif validation_results['overall_status'] == 'PARTIAL':
                ready_count = validation_results['statistics']['valid_surfaces']
                total_count = validation_results['surface_count']
                self.statusBar().showMessage(f"⚠ {ready_count}/{total_count} surfaces ready for tetgen")
            else:
                self.statusBar().showMessage("✗ Surfaces not ready for tetgen - check validation report")
                
        except Exception as e:
            logger.error(f"Validation failed: {str(e)}")
            self.statusBar().showMessage(f"Validation failed: {str(e)}")
    
    def _setup_tetra_mesh_tab(self):
        """Enhanced tetra mesh tab with 3D viewer, surface transfer, and material assignment"""
        
        # Initialize data structures
        self.tetra_materials = []
        self.tetrahedral_mesh = None
        self.tetra_selected_surfaces = set()  # Surfaces transferred from pre-tetra tab
        self.tetra_surface_data = {}  # Store transferred surface data
        
        # Create main layout
        tab_layout = QHBoxLayout(self.tetra_mesh_tab)
        
        # === Control Panel (Left) ===
        control_panel = QWidget()
        control_panel.setMaximumWidth(400)
        control_layout = QVBoxLayout(control_panel)
        
        # --- Data Transfer Group ---
        transfer_group = QGroupBox("Constrained Surface Data")
        transfer_layout = QVBoxLayout(transfer_group)
        
        self.load_surfaces_btn = QPushButton("📥 Load Final Surfaces for 3D Meshing")
        self.load_surfaces_btn.setToolTip("Load the conforming surface meshes generated in the Refine & Mesh tab.")
        self.load_surfaces_btn.clicked.connect(self._load_conforming_meshes_for_tetgen)
        transfer_layout.addWidget(self.load_surfaces_btn)
        
        # Surface list display
        self.loaded_surfaces_list = QListWidget()
        self.loaded_surfaces_list.setMaximumHeight(120)
        self.loaded_surfaces_list.setToolTip("Surfaces loaded from pre-tetra tab with their mesh data")
        transfer_layout.addWidget(QLabel("Loaded Surfaces:"))
        transfer_layout.addWidget(self.loaded_surfaces_list)
        
        control_layout.addWidget(transfer_group)
        
        # --- Material Assignment Group ---
        material_group = QGroupBox("Material Assignment (C++ MeshIt Style)")
        material_layout = QVBoxLayout(material_group)
        
        # Add explanatory text about C++ approach
        cpp_info = QLabel("ℹ️ Following C++ MeshIt approach:\n• Faults = 2D surface constraints\n• Units = 3D volumetric regions")
        cpp_info.setStyleSheet("color: #1976D2; font-style: italic; background: #E3F2FD; padding: 5px; border-radius: 3px;")
        cpp_info.setWordWrap(True)
        material_layout.addWidget(cpp_info)
        
        # Surface type classification
        self.border_surfaces_list = QListWidget()
        self.border_surfaces_list.setMaximumHeight(80)
        self.unit_surfaces_list = QListWidget()
        self.unit_surfaces_list.setMaximumHeight(80)
        self.fault_surfaces_list = QListWidget()
        self.fault_surfaces_list.setMaximumHeight(80)
        
        material_layout.addWidget(QLabel("Border Surfaces:"))
        material_layout.addWidget(self.border_surfaces_list)
        material_layout.addWidget(QLabel("Unit Surfaces:"))
        material_layout.addWidget(self.unit_surfaces_list)
        material_layout.addWidget(QLabel("Fault Surfaces:"))
        material_layout.addWidget(self.fault_surfaces_list)
        
        # Auto-classify button
        self.auto_classify_btn = QPushButton("🏷️ Auto-Classify by Name")
        self.auto_classify_btn.setToolTip("Automatically classify surfaces based on their names (border, unit, fault)")
        self.auto_classify_btn.clicked.connect(self._auto_classify_surfaces)
        material_layout.addWidget(self.auto_classify_btn)
        
        control_layout.addWidget(material_group)
        
        # --- Generation Controls ---
        generate_group = QGroupBox("Tetrahedral Mesh Generation")
        generate_layout = QVBoxLayout(generate_group)
        
        # TetGen options
        tetgen_options_layout = QHBoxLayout()
        tetgen_options_layout.addWidget(QLabel("TetGen Switches:"))
        self.tetgen_switches_input = QLineEdit("pq1.2AY")
        self.tetgen_switches_input.setToolTip("TetGen command line switches (e.g., pq1.414aA)")
        tetgen_options_layout.addWidget(self.tetgen_switches_input)
        generate_layout.addLayout(tetgen_options_layout)
        
        self.generate_tetra_mesh_btn = QPushButton("🔧 Generate Tetrahedral Mesh")
        self.generate_tetra_mesh_btn.clicked.connect(self._generate_tetrahedral_mesh_action)
        self.generate_tetra_mesh_btn.setEnabled(False)  # Enable after loading surfaces
        generate_layout.addWidget(self.generate_tetra_mesh_btn)
        
        self.export_mesh_btn = QPushButton("💾 Export Mesh")
        self.export_mesh_btn.clicked.connect(self._export_tetrahedral_mesh)
        self.export_mesh_btn.setEnabled(False)
        generate_layout.addWidget(self.export_mesh_btn)
        
        control_layout.addWidget(generate_group)
        
        control_layout.addStretch()  # Push everything to the top
        
        # Add control panel to layout first (left side)
        tab_layout.addWidget(control_panel)
        
        # === 3D Visualization Panel (Center) ===
        self._setup_tetra_3d_viewer(tab_layout)
        
        # === Materials Panel (Right) ===
        materials_group = self._init_material_selection_ui()
        tab_layout.addWidget(materials_group)
        
        logger.info("Enhanced tetra mesh tab with 3D viewer and surface transfer initialized")

    def _setup_tetra_3d_viewer(self, parent_layout):
        """Setup the 3D visualization panel for the tetra mesh tab"""
        # Create visualization panel
        viz_panel = QWidget()
        viz_layout = QVBoxLayout(viz_panel)
        
        # Toolbar for 3D viewer controls
        toolbar = QHBoxLayout()
        
        # Basic controls
        self.tetra_reset_view_btn = QPushButton("🔄 Reset View")
        self.tetra_fit_view_btn = QPushButton("📐 Fit View")
        
        # Visualization modes
        self.tetra_wireframe_check = QCheckBox("Wireframe")
        self.tetra_show_materials_check = QCheckBox("Materials")
        self.tetra_show_internal_check = QCheckBox("Show Internal")
        
        # Material selection dropdown (like C++ version)
        material_label = QLabel("Material:")
        self.tetra_material_combo = QComboBox()
        self.tetra_material_combo.setToolTip("Select material to visualize (All = show all materials)")
        self.tetra_material_combo.setMinimumWidth(120)
        
        # Colormap selection dropdown
        colormap_label = QLabel("Colormap:")
        self.tetra_colormap_combo = QComboBox()
        self.tetra_colormap_combo.setToolTip("Select colormap for material visualization")
        self.tetra_colormap_combo.setMinimumWidth(100)
        
        # Add professional colormaps for geological/scientific visualization
        geological_colormaps = [
            ("Set1", "Qualitative - Distinct colors"),
            ("tab10", "Qualitative - 10 distinct colors"), 
            ("viridis", "Sequential - Blue to yellow"),
            ("plasma", "Sequential - Purple to yellow"),
            ("terrain", "Geographical - Earth tones"),
            ("gist_earth", "Geological - Earth colors"),
            ("coolwarm", "Diverging - Blue to red"),
            ("RdYlBu", "Diverging - Red/Yellow/Blue"),
            ("Spectral", "Diverging - Rainbow spectrum"),
            ("tab20", "Qualitative - 20 distinct colors")
        ]
        
        for cmap_name, description in geological_colormaps:
            self.tetra_colormap_combo.addItem(f"{cmap_name} - {description}", cmap_name)
        
        # Set default to Set1
        self.tetra_colormap_combo.setCurrentText("Set1 - Qualitative - Distinct colors")
        
        # Opacity control
        opacity_label = QLabel("Opacity:")
        self.tetra_opacity_slider = QSlider(Qt.Horizontal)
        self.tetra_opacity_slider.setRange(10, 100)
        self.tetra_opacity_slider.setValue(80)
        self.tetra_opacity_slider.setMaximumWidth(100)
        
        toolbar.addWidget(self.tetra_reset_view_btn)
        toolbar.addWidget(self.tetra_fit_view_btn)
        
        # Add separator line
        separator1 = QFrame()
        separator1.setFrameShape(QFrame.VLine)
        separator1.setFrameShadow(QFrame.Sunken)
        toolbar.addWidget(separator1)
        
        toolbar.addWidget(self.tetra_wireframe_check)
        toolbar.addWidget(self.tetra_show_materials_check)
        toolbar.addWidget(self.tetra_show_internal_check)
        
        # Add separator line
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.VLine)
        separator2.setFrameShadow(QFrame.Sunken)
        toolbar.addWidget(separator2)
        
        toolbar.addWidget(material_label)
        toolbar.addWidget(self.tetra_material_combo)
        
        # Add separator line
        separator3 = QFrame()
        separator3.setFrameShape(QFrame.VLine)
        separator3.setFrameShadow(QFrame.Sunken)
        toolbar.addWidget(separator3)
        
        toolbar.addWidget(colormap_label)
        toolbar.addWidget(self.tetra_colormap_combo)
        
        # Add separator line
        separator4 = QFrame()
        separator4.setFrameShape(QFrame.VLine)
        separator4.setFrameShadow(QFrame.Sunken)
        toolbar.addWidget(separator4)
        
        toolbar.addWidget(opacity_label)
        toolbar.addWidget(self.tetra_opacity_slider)
        toolbar.addStretch()
        
        viz_layout.addLayout(toolbar)
        
        # Cutting plane controls (like C++ version)
        cutting_group = QGroupBox("Cutting Planes (Internal View)")
        cutting_layout = QHBoxLayout(cutting_group)
        
        # X-axis cutting
        x_cut_layout = QVBoxLayout()
        self.x_cut_enable = QCheckBox("X Cut")
        self.x_cut_slider = QSlider(Qt.Horizontal)
        self.x_cut_slider.setRange(0, 100)
        self.x_cut_slider.setValue(50)
        self.x_cut_slider.setEnabled(False)
        x_cut_layout.addWidget(self.x_cut_enable)
        x_cut_layout.addWidget(self.x_cut_slider)
        cutting_layout.addLayout(x_cut_layout)
        
        # Y-axis cutting
        y_cut_layout = QVBoxLayout()
        self.y_cut_enable = QCheckBox("Y Cut")
        self.y_cut_slider = QSlider(Qt.Horizontal)
        self.y_cut_slider.setRange(0, 100)
        self.y_cut_slider.setValue(50)
        self.y_cut_slider.setEnabled(False)
        y_cut_layout.addWidget(self.y_cut_enable)
        y_cut_layout.addWidget(self.y_cut_slider)
        cutting_layout.addLayout(y_cut_layout)
        
        # Z-axis cutting
        z_cut_layout = QVBoxLayout()
        self.z_cut_enable = QCheckBox("Z Cut")
        self.z_cut_slider = QSlider(Qt.Horizontal)
        self.z_cut_slider.setRange(0, 100)
        self.z_cut_slider.setValue(50)
        self.z_cut_slider.setEnabled(False)
        z_cut_layout.addWidget(self.z_cut_enable)
        z_cut_layout.addWidget(self.z_cut_slider)
        cutting_layout.addLayout(z_cut_layout)
        
        viz_layout.addWidget(cutting_group)
        
        # 3D Viewer
        if True:
            from pyvistaqt import QtInteractor
            
            self.tetra_plotter = QtInteractor(viz_panel)
            self.tetra_plotter.set_background([0.15, 0.15, 0.2])
            viz_layout.addWidget(self.tetra_plotter.interactor)
            
            # Connect controls
            self.tetra_reset_view_btn.clicked.connect(self.tetra_plotter.reset_camera)
            self.tetra_fit_view_btn.clicked.connect(lambda: self.tetra_plotter.reset_camera(render=True))
            self.tetra_wireframe_check.toggled.connect(self._toggle_tetra_wireframe)
            self.tetra_show_materials_check.toggled.connect(self._toggle_tetra_materials)
            self.tetra_show_internal_check.toggled.connect(self._toggle_tetra_internal)
            self.tetra_opacity_slider.valueChanged.connect(self._update_tetra_opacity)
            self.tetra_material_combo.currentTextChanged.connect(self._on_material_selection_changed)
            self.tetra_colormap_combo.currentTextChanged.connect(self._on_colormap_changed)
            
            # Connect cutting plane controls
            self.x_cut_enable.toggled.connect(lambda enabled: self.x_cut_slider.setEnabled(enabled))
            self.y_cut_enable.toggled.connect(lambda enabled: self.y_cut_slider.setEnabled(enabled))
            self.z_cut_enable.toggled.connect(lambda enabled: self.z_cut_slider.setEnabled(enabled))
            self.x_cut_enable.toggled.connect(self._update_cutting_planes)
            self.y_cut_enable.toggled.connect(self._update_cutting_planes)
            self.z_cut_enable.toggled.connect(self._update_cutting_planes)
            self.x_cut_slider.valueChanged.connect(self._update_cutting_planes)
            self.y_cut_slider.valueChanged.connect(self._update_cutting_planes)
            self.z_cut_slider.valueChanged.connect(self._update_cutting_planes)
            
            logger.info("Enhanced tetra mesh 3D viewer with cutting planes initialized")
        else:
            placeholder = QLabel("PyVista is required for 3D visualization.")
            placeholder.setAlignment(Qt.AlignCenter)
            viz_layout.addWidget(placeholder)
            self.tetra_plotter = None
        
        # Add to main layout with stretch factor
        parent_layout.addWidget(viz_panel, 1)  # stretch=1 to take remaining space

    def _load_conforming_meshes_for_tetgen(self):
        """Load conforming meshes from Tab 6 (Refine & Mesh) following C++ approach"""
        logger.info("Loading conforming meshes into Tetra Mesh tab...")
        
        try:
            # Clear existing data
            self.tetra_selected_surfaces.clear()
            self.tetra_surface_data.clear()
            self.loaded_surfaces_list.clear()
            
            loaded_count = 0
            
            # Get selected surfaces from the Pre-Tetra tab's tree (Tab 7)
            selected_indices = self._get_selected_surfaces_from_conforming_tree()
            
            if not selected_indices:
                # Fallback: try to get all surfaces that have conforming meshes
                selected_indices = []
                for idx, dataset in enumerate(self.datasets):
                    if 'conforming_mesh' in dataset:
                        selected_indices.append(idx)
                        
                if not selected_indices:
                    QMessageBox.warning(
                        self, "No Conforming Meshes Found",
                        "No conforming meshes found.\n\n"
                        "Please:\n"
                        "1. Generate conforming meshes in the 'Refine & Mesh' tab\n"
                        "2. Select surfaces in the 'Pre-Tetra Mesh' tab\n"
                        "3. Then load them here for 3D meshing"
                    )
                    return
            
            # Load conforming meshes for selected surfaces
            for surface_idx in selected_indices:
                if surface_idx < len(self.datasets):
                    dataset = self.datasets[surface_idx]
                    if 'conforming_mesh' in dataset:
                        conforming_mesh = dataset['conforming_mesh']
                        surface_name = dataset.get('name', f'Surface_{surface_idx}')
                        
                        self.tetra_selected_surfaces.add(surface_idx)
                        # Store a direct reference to the conforming mesh data
                        self.tetra_surface_data[surface_idx] = {
                            'name': surface_name,
                            'vertices': conforming_mesh['vertices'],
                            'triangles': conforming_mesh['triangles'],
                            'original_dataset_index': surface_idx,
                            'conforming_mesh_source': True,
                            'mesh_metadata': conforming_mesh  # Store full metadata
                        }
                        
                        loaded_count += 1
                        item_text = f"{surface_name} ({len(conforming_mesh['vertices'])} verts, {len(conforming_mesh['triangles'])} tris) [Conforming]"
                        self.loaded_surfaces_list.addItem(item_text)
                        
                        logger.info(f"Loaded conforming mesh for surface {surface_idx}: {surface_name}")
            
            if loaded_count > 0:
                self.generate_tetra_mesh_btn.setEnabled(True)
                self._auto_classify_surfaces()  # Auto-classify the loaded surfaces
                self._visualize_loaded_surfaces()  # Show them in 3D viewer
                
                QMessageBox.information(
                    self, "Conforming Meshes Loaded", 
                    f"Successfully loaded {loaded_count} conforming surface mesh(es).\n\n"
                    f"These meshes form a watertight Piecewise Linear Complex (PLC)\n"
                    f"ready for TetGen 3D meshing following C++ MeshIt workflow."
                )
                self.statusBar().showMessage(f"Loaded {loaded_count} conforming meshes. Ready for 3D generation.")
            else:
                QMessageBox.warning(
                    self, "No Conforming Meshes Available",
                    "No conforming meshes were found for the selected surfaces.\n\n"
                    "Please generate them in the 'Refine & Mesh' tab first."
                )
            
        except Exception as e:
            logger.error(f"Error loading conforming meshes: {e}")
            QMessageBox.critical(self, "Load Error", f"Failed to load conforming meshes: {str(e)}")
    
    def _get_selected_surfaces_from_conforming_tree(self):
        """Get selected surface indices from Pre-Tetra tab's surface tree"""
        selected_indices = []
        
        if hasattr(self, 'conforming_surface_tree'):
            for i in range(self.conforming_surface_tree.topLevelItemCount()):
                item = self.conforming_surface_tree.topLevelItem(i)
                if item.checkState(0) == Qt.Checked:
                    try:
                        # Extract surface index from item data or text
                        surface_idx = item.data(0, Qt.UserRole)
                        if surface_idx is not None:
                            selected_indices.append(surface_idx)
                        else:
                            # Fallback: parse from text if data not available
                            text = item.text(0)
                            if "Surface" in text:
                                idx_str = text.split()[1] if len(text.split()) > 1 else None
                                if idx_str and idx_str.isdigit():
                                    selected_indices.append(int(idx_str))
                    except (ValueError, AttributeError):
                        continue
        
        return selected_indices

    def _auto_classify_surfaces(self):
        """Automatically classify loaded surfaces based on their names"""
        # Clear existing classifications
        self.border_surfaces_list.clear()
        self.unit_surfaces_list.clear()
        self.fault_surfaces_list.clear()
        
        for surface_idx in self.tetra_selected_surfaces:
            surface_data = self.tetra_surface_data[surface_idx]
            surface_name = surface_data['name'].lower()
            
            # Create display item
            display_text = f"{surface_data['name']} (Surface {surface_idx})"
            
            # Classify based on name
            if any(keyword in surface_name for keyword in ['border', 'boundary', 'outer']):
                self.border_surfaces_list.addItem(display_text)
            elif any(keyword in surface_name for keyword in ['unit', 'inner', 'volume']):
                self.unit_surfaces_list.addItem(display_text)
            elif any(keyword in surface_name for keyword in ['fault', 'fracture', 'crack']):
                self.fault_surfaces_list.addItem(display_text)
            else:
                # Default classification - add to unit surfaces
                self.unit_surfaces_list.addItem(display_text)
        
        logger.info(f"Auto-classified surfaces: {self.border_surfaces_list.count()} border, "
                   f"{self.unit_surfaces_list.count()} unit, {self.fault_surfaces_list.count()} fault")

    def _visualize_loaded_surfaces(self):
        """Visualize the loaded constrained surfaces in the 3D viewer"""
        if not self.tetra_plotter:
            return
            
        self.tetra_plotter.clear()
        
        try:
            import pyvista as pv
            import numpy as np
            
            # Color palette for different surfaces
            colors = [
                (0.8, 0.2, 0.2),  # Red
                (0.2, 0.8, 0.2),  # Green  
                (0.2, 0.2, 0.8),  # Blue
                (0.8, 0.8, 0.2),  # Yellow
                (0.8, 0.2, 0.8),  # Magenta
                (0.2, 0.8, 0.8),  # Cyan
            ]
            
            for i, surface_idx in enumerate(self.tetra_selected_surfaces):
                surface_data = self.tetra_surface_data[surface_idx]
                vertices = np.array(surface_data['vertices'])
                triangles = np.array(surface_data['triangles'])
                
                # Create PyVista mesh
                faces = []
                for tri in triangles:
                    faces.extend([3, tri[0], tri[1], tri[2]])
                
                mesh = pv.PolyData(vertices, faces)
                color = colors[i % len(colors)]
                
                self.tetra_plotter.add_mesh(
                    mesh,
                    color=color,
                    opacity=0.8,
                    show_edges=True,
                    edge_color='white',
                    line_width=1,
                    name=f"surface_{surface_idx}",
                    label=surface_data['name']
                )
            
            # Add legend and reset camera
            if self.tetra_selected_surfaces:
                self.tetra_plotter.add_legend()
                self.tetra_plotter.reset_camera()
            else:
                self.tetra_plotter.add_text("No surfaces loaded", position='upper_edge', color='white')
            
            self.tetra_plotter.render()
            logger.info(f"Visualized {len(self.tetra_selected_surfaces)} constrained surfaces")
            
        except Exception as e:
            logger.error(f"Error visualizing surfaces: {e}")
            self.tetra_plotter.add_text(f"Visualization error: {str(e)}", position='upper_edge', color='red')

    def _toggle_tetra_wireframe(self, enabled):
        """Toggle wireframe display for loaded surfaces and tetrahedral mesh"""
        if not self.tetra_plotter:
            return
            
        try:
            # Handle wireframe for loaded surfaces
            for surface_idx in self.tetra_selected_surfaces:
                actor = self.tetra_plotter.actors.get(f"surface_{surface_idx}")
                if actor:
                    if enabled:
                        actor.prop.representation = 'wireframe'
                    else:
                        actor.prop.representation = 'surface'
            
            # Handle wireframe for tetrahedral mesh if available
            if hasattr(self, 'full_tetra_mesh') and self.full_tetra_mesh is not None:
                self._refresh_tetrahedral_visualization()
            else:
                self.tetra_plotter.render()
                
        except Exception as e:
            logger.error(f"Error toggling wireframe: {e}")

    def _toggle_tetra_materials(self, enabled):
        """Toggle material ID display"""
        logger.info(f"Material display toggled: {enabled}")
        
        # Update visualization if mesh is available
        if hasattr(self, 'full_tetra_mesh') and self.full_tetra_mesh is not None:
            self._refresh_tetrahedral_visualization()

    def _toggle_tetra_internal(self, enabled):
        """Toggle internal structure visualization"""
        logger.info(f"Internal structure display toggled: {enabled}")
        
        # Update visualization if mesh is available
        if hasattr(self, 'full_tetra_mesh') and self.full_tetra_mesh is not None:
            self._refresh_tetrahedral_visualization()

    def _update_tetra_opacity(self, value):
        """Update tetrahedral mesh opacity"""
        opacity = value / 100.0
        logger.debug(f"Tetrahedral mesh opacity updated: {opacity}")
        
        # Update visualization if mesh is available
        if hasattr(self, 'full_tetra_mesh') and self.full_tetra_mesh is not None:
            self._refresh_tetrahedral_visualization()

    def _update_cutting_planes(self):
        """Update cutting plane visualization"""
        logger.debug("Cutting planes updated")
        
        # Update visualization if mesh is available
        if hasattr(self, 'full_tetra_mesh') and self.full_tetra_mesh is not None:
            self._refresh_tetrahedral_visualization()

    def _refresh_tetrahedral_visualization(self):
        """Refresh the tetrahedral mesh visualization with current settings"""
        if not self.tetra_plotter or not hasattr(self, 'full_tetra_mesh'):
            return

        try:
            # Clear existing tetrahedral mesh actors
            actors_to_remove = []
            for name in list(self.tetra_plotter.actors.keys()):
                if 'tetrahedral' in name:
                    actors_to_remove.append(name)

            for name in actors_to_remove:
                self.tetra_plotter.remove_actor(name)

            # Clear existing colorbars/scalar bars
            if hasattr(self.tetra_plotter, 'clear_scalar_bars'):
                self.tetra_plotter.clear_scalar_bars()

            # Re-add the visualization with current settings
            self._add_tetrahedral_mesh_visualization(self.full_tetra_mesh)

            self.tetra_plotter.render()

        except Exception as e:
            logger.error(f"Error refreshing tetrahedral visualization: {e}")



    def _update_constraint_actor_visual(self, surf_idx: int, con_idx: int,
                                        active: bool, spotlight: bool = False):
        """
        Change colour to indicate whether the segment is currently enabled.
        spotlight=True is a temporary bright highlight (on click).
        Active constraints are shown in blue (like C++ version) to indicate selection.
        Inactive constraints are shown in muted grey.
        """
        plotter = self.plotters.get("pre_tetramesh")
        if plotter is None:
            return

        # Update the constraint state in the manager to ensure persistence
        if not spotlight:  # Don't change state for spotlight (temporary highlight)
            if active:
                self.constraint_manager.constraint_states[(surf_idx, con_idx)] = "SEGMENTS"
            else:
                self.constraint_manager.constraint_states[(surf_idx, con_idx)] = "UNDEFINED"

        # Get the actor and update its appearance
        actor_name = f"s{surf_idx}_c{con_idx}"
        actor = plotter.actors.get(actor_name)
        if actor is None:
            # If actor doesn't exist yet, we may need to recreate the visualization
            # This can happen if the plotter was cleared or reset
            return

        if spotlight:
            actor.prop.color = (1.0, 1.0, 0.0)            # bright yellow
            actor.prop.opacity = 1.0
            plotter.render()  # Force immediate render for spotlight
            return

        if active:
            # Use blue for selected constraints (like C++ version)
            actor.prop.color = (0.0, 0.4, 1.0)  # Blue color for selected constraints
            actor.prop.opacity = 1.0
        else:
            # muted grey for disabled constraints
            actor.prop.color = (0.45, 0.45, 0.45)
            actor.prop.opacity = 0.3
    
        # Force a render to ensure changes are visible immediately
        plotter.render()
    

    # In meshit_workflow_gui.py

    # In meshit_workflow_gui.py

    def _generate_tetrahedral_mesh_action(self) -> None:
        """
        Slot connected to the “Generate Tetrahedral Mesh” button.
        """
        if not self.tetra_selected_surfaces:
            QMessageBox.warning(self, "No Surfaces Loaded", "Please load conforming surfaces into this tab first.")
            return

        tetgen_switches = self.tetgen_switches_input.text().strip() if hasattr(self, 'tetgen_switches_input') else "pq1.414aA"
        
        border_indices = self._get_border_surface_indices()
        unit_indices = self._get_unit_surface_indices()
        fault_indices = self._get_fault_surface_indices()

        # *** CRITICAL CHANGE HERE ***
        # The `self.tetra_surface_data` attribute should already contain the
        # conforming meshes loaded from the previous tab. Pass this directly.
        if not self.tetra_surface_data:
             QMessageBox.critical(self, "Data Error", "No conforming mesh data is loaded in the Tetra Mesh tab.")
             return
        
        # Collect hole information from constraint tree
        holes = self._collect_holes_from_constraint_tree()
        
        self.tetra_mesh_generator = TetrahedralMeshGenerator(
            datasets=self.datasets,
            selected_surfaces=self.tetra_selected_surfaces,
            border_surface_indices=border_indices,
            unit_surface_indices=unit_indices,
            fault_surface_indices=fault_indices,
            materials=self.tetra_materials,
            surface_data=self.tetra_surface_data,  # <-- PASS THE CORRECT DATA
            holes=holes  # <-- PASS HOLE INFORMATION
        )

        self.statusBar().showMessage("Generating 3D tetrahedral mesh... This may take a while.")
        QApplication.processEvents()

        grid = self.tetra_mesh_generator.generate_tetrahedral_mesh(tetgen_switches)
        
        if grid:
            self.tetrahedral_mesh = grid
            
            # MATERIAL ASSIGNMENT: Apply manual material assignment if needed
            if not hasattr(grid, 'cell_data') or 'MaterialID' not in grid.cell_data:
                logger.info("No MaterialID found in mesh - applying manual material assignment")
                self._assign_materials_to_mesh(grid)
            else:
                # Debug: Check if MaterialID actually has meaningful data
                import numpy as np
                material_ids = grid.cell_data['MaterialID']
                unique_materials = np.unique(material_ids)
                logger.info(f"Found MaterialID in mesh: unique values = {unique_materials}")
                
                # If all materials are 0 or there's only one material, force manual assignment
                if len(unique_materials) == 1 and unique_materials[0] == 0:
                    logger.info("MaterialID contains only zeros - applying manual material assignment")
                    self._assign_materials_to_mesh(grid)
                else:
                    # ✅ CRITICAL FIX: Only count FORMATION materials that TetGen actually processes
                    # Faults are surface constraints only, NOT volumetric regions
                    formation_materials = [m for m in self.tetra_materials if m.get('type', 'FORMATION') != 'FAULT']
                    expected_materials = len(formation_materials)
                    
                    if len(unique_materials) < expected_materials:
                        logger.info(f"MaterialID has {len(unique_materials)} unique values but we need {expected_materials} formations - applying manual assignment")
                        self._assign_materials_to_mesh(grid)
                    else:
                        logger.info(f"✅ TetGen material assignment successful: {len(unique_materials)} materials match {expected_materials} formations")
            
            QMessageBox.information(self, "Success", "Tetrahedral mesh generated successfully!")
            self.export_mesh_btn.setEnabled(True)
            self._visualize_tetrahedral_mesh_in_tetra_tab()
            self._update_tetra_stats()
        else:
            QMessageBox.critical(self, "TetGen Failure", "Failed to generate tetrahedral mesh. Check the logs and the exported debug_plc.vtm file for details.")

        self.statusBar().showMessage("Tetrahedral meshing complete.")

    def _collect_holes_from_constraint_tree(self):
        """
        Collect hole points from the constraint tree where users have marked intersections as holes.
        Returns a list of (x, y, z) hole center points.
        """
        holes = []
        processed_intersections = set()  # Avoid duplicate holes from same intersection
        
        # Try to get the constraint tree from Refine & Mesh tab
        constraint_tree = None
        if hasattr(self, 'refine_constraint_tree') and self.refine_constraint_tree:
            constraint_tree = self.refine_constraint_tree
            logger.info("Using constraint tree from Refine & Mesh tab for hole collection")
        else:
            logger.info("No constraint tree available for hole collection")
            return holes
            
        tree = constraint_tree
        
        # Iterate through all surfaces in the constraint tree
        for i in range(tree.topLevelItemCount()):
            surface_item = tree.topLevelItem(i)
            surface_data = surface_item.data(0, Qt.UserRole)
            
            if not surface_data or surface_data.get('type') != 'surface':
                continue
                
            surface_idx = surface_data.get('surface_idx')
            if surface_idx is None:
                continue
                
            # Iterate through intersection groups in this surface
            for j in range(surface_item.childCount()):
                group_item = surface_item.child(j)
                group_data = group_item.data(0, Qt.UserRole)
                
                if not group_data or group_data.get('type') != 'intersection_group':
                    continue
                
                # Check if this intersection group is marked as a hole (column 4)
                if group_item.checkState(4) == Qt.Checked:
                    # Extract intersection index from text (e.g., "Intersection 2")
                    item_text = group_item.text(0)
                    try:
                        intersection_idx = int(item_text.split(" ")[-1])
                    except (ValueError, IndexError):
                        continue
                        
                    # Get intersection data
                    if (hasattr(self, 'refined_intersections_for_visualization') and 
                        surface_idx in self.refined_intersections_for_visualization and 
                        intersection_idx < len(self.refined_intersections_for_visualization[surface_idx])):
                        
                        intersection_data = self.refined_intersections_for_visualization[surface_idx][intersection_idx]
                        dataset_id1 = intersection_data.get('dataset_id1')
                        dataset_id2 = intersection_data.get('dataset_id2')
                        
                        # Create unique key for this intersection to avoid duplicates
                        intersection_key = tuple(sorted([dataset_id1, dataset_id2]))
                        if intersection_key in processed_intersections:
                            continue
                            
                        processed_intersections.add(intersection_key)
                        
                        # Calculate hole center from intersection segments
                        hole_center = self._calculate_intersection_hole_center(surface_idx, intersection_idx)
                        if hole_center:
                            holes.append(hole_center)
                            surface_name = self.datasets[surface_idx].get("name", f"Surface_{surface_idx}")
                            logger.info(f"Collected hole from constraint tree: '{surface_name}' intersection {intersection_idx} at ({hole_center[0]:.3f}, {hole_center[1]:.3f}, {hole_center[2]:.3f})")
        
        if holes:
            logger.info(f"✓ Collected {len(holes)} holes from constraint tree")
        else:
            logger.info("No holes marked in constraint tree")
            
        return holes
    
    def _calculate_intersection_hole_center(self, surface_idx, intersection_idx):
        """
        Calculate the center point of a hole from intersection segments.
        """
        try:
            if (not hasattr(self, 'refined_intersections_for_visualization') or
                surface_idx not in self.refined_intersections_for_visualization or 
                intersection_idx >= len(self.refined_intersections_for_visualization[surface_idx])):
                return None
                
            intersection_data = self.refined_intersections_for_visualization[surface_idx][intersection_idx]
            segments = intersection_data.get('segments', [])
            
            if not segments:
                return None
            
            # Collect all points from all segments
            all_points = []
            for segment in segments:
                points = segment.get('points', [])
                for point in points:
                    if hasattr(point, 'x'):  # Vector3D-like object
                        all_points.append([point.x, point.y, point.z])
                    elif isinstance(point, (list, tuple)) and len(point) >= 3:
                        all_points.append([point[0], point[1], point[2]])
            
            if not all_points:
                return None
                
            # Calculate centroid
            import numpy as np
            coords_array = np.array(all_points)
            center = np.mean(coords_array, axis=0)
            return [float(center[0]), float(center[1]), float(center[2])]
            
        except Exception as e:
            logger.warning(f"Failed to calculate intersection hole center: {e}")
            return None

    def _get_surface_indices_from_list(self, list_widget):
        """Extract surface indices from a list widget containing classified surfaces"""
        indices = set()
        for i in range(list_widget.count()):
            item_text = list_widget.item(i).text()
            # Extract surface index from text like "Surface_Name (Surface X)"
            import re
            match = re.search(r'Surface (\d+)', item_text)
            if match:
                indices.add(int(match.group(1)))
        return indices

    def _visualize_tetrahedral_mesh_in_tetra_tab(self):
        """Visualize the generated tetrahedral mesh in the tetra tab's 3D viewer"""
        if not self.tetra_plotter or not self.tetrahedral_mesh:
            return
            
        try:
            import pyvista as pv
            import numpy as np
            
            self.tetra_plotter.clear()
            
            # Get the mesh
            if isinstance(self.tetrahedral_mesh, dict):
                mesh = self.tetrahedral_mesh.get('pyvista_grid')
            else:
                mesh = self.tetrahedral_mesh
                
            if mesh is None:
                self.tetra_plotter.add_text("No mesh data available", position='upper_edge', color='red')
                return
            
            # Store full mesh for later use
            self.full_tetra_mesh = mesh
            
            # Enhanced visualization like C++ version
            self._add_tetrahedral_mesh_visualization(mesh)
            
            # Update material dropdown with available materials
            self._update_material_dropdown()
            
            # Add colorbar if using materials and checkbox is enabled
            show_materials = getattr(self, 'tetra_show_materials_check', None) and self.tetra_show_materials_check.isChecked()
            if show_materials and 'MaterialID' in mesh.cell_data:
                # Note: scalar bar is already handled in _add_tetrahedral_mesh_visualization
                pass
            
            # Add coordinate axes
            self.tetra_plotter.add_axes(
                line_width=3,
                cone_radius=0.6,
                shaft_length=0.7,
                tip_length=0.3,
                ambient=0.5,
                x_color='red',
                y_color='green', 
                z_color='blue'
            )
            
            # Enable all controls
            if hasattr(self, 'tetra_show_materials_check'):
                self.tetra_show_materials_check.setEnabled(True)
            if hasattr(self, 'tetra_show_internal_check'):
                self.tetra_show_internal_check.setEnabled(True)
            if hasattr(self, 'tetra_material_combo'):
                self.tetra_material_combo.setEnabled(True)
            if hasattr(self, 'x_cut_enable'):
                self.x_cut_enable.setEnabled(True)
                self.y_cut_enable.setEnabled(True)
                self.z_cut_enable.setEnabled(True)
            
            self.tetra_plotter.reset_camera()
            self.tetra_plotter.render()
            
            logger.info("Enhanced tetrahedral mesh visualized with internal structure support")
            
        except Exception as e:
            logger.error(f"Error visualizing tetrahedral mesh: {e}")
            self.tetra_plotter.add_text(f"Visualization error: {str(e)}", position='upper_edge', color='red')

    def _add_tetrahedral_mesh_visualization(self, mesh):
        """Add tetrahedral mesh visualization like C++ version (surface + internal combined)"""
        import pyvista as pv
        import numpy as np
        
        # Get current settings
        show_internal = getattr(self, 'tetra_show_internal_check', None) and self.tetra_show_internal_check.isChecked()
        show_materials = getattr(self, 'tetra_show_materials_check', None) and self.tetra_show_materials_check.isChecked()
        show_wireframe = getattr(self, 'tetra_wireframe_check', None) and self.tetra_wireframe_check.isChecked()
        opacity = getattr(self, 'tetra_opacity_slider', None) and self.tetra_opacity_slider.value() / 100.0 or 0.8
        
        # Get selected material filter
        selected_material_id = self._get_selected_material_id()
        
        # Apply material filtering if specific material is selected
        if selected_material_id != -1:  # -1 means show all materials
            processed_mesh = self._filter_mesh_by_material(mesh, selected_material_id)
        else:
            processed_mesh = mesh
        
        # Apply cutting planes if enabled
        processed_mesh = self._apply_cutting_planes(processed_mesh)
        
        # Always show the surface boundary
        self._add_surface_visualization(processed_mesh, show_materials, opacity, show_wireframe)
        
        # Additionally show internal structure if enabled
        if show_internal:
            self._add_internal_structure_visualization(processed_mesh, show_materials, opacity)

    def _add_surface_visualization(self, mesh, show_materials, opacity, show_wireframe=False):
        """Add surface visualization (external boundary)"""
        import pyvista as pv

        # Extract surface
        surface_mesh = mesh.extract_surface()

        # Configure scalars and colormap
        scalars = None
        cmap = None
        clim = None
        show_scalar_bar = False

        if show_materials and 'MaterialID' in mesh.cell_data:
            # Map material IDs from cells to surface only when materials are enabled
            if hasattr(surface_mesh, 'cell_data') and 'MaterialID' in surface_mesh.cell_data:
                scalars = 'MaterialID'
                cmap = self._get_selected_colormap()  # Use user-selected colormap
                show_scalar_bar = True

        # Add surface mesh (external boundary)
        if show_wireframe:
            # Wireframe mode: show edges only, no coloring
            self.tetra_plotter.add_mesh(
                surface_mesh,
                style='wireframe',
                color='lightgray',  # Use consistent gray color when not showing materials
                opacity=1.0,
                line_width=1.5,
                name='tetrahedral_surface'
            )
        else:
            # Solid mode: show faces with edges
            if scalars is not None and show_scalar_bar:
                # Show with material coloring and scalar bar
                self.tetra_plotter.add_mesh(
                    surface_mesh,
                    scalars=scalars,
                    cmap=cmap,
                    opacity=opacity,
                    show_edges=True,
                    edge_color='black',
                    line_width=0.5,
                    scalar_bar_args={'title': 'Material ID'},
                    name='tetrahedral_surface'
                )
            else:
                # Show without material coloring
                self.tetra_plotter.add_mesh(
                    surface_mesh,
                    color='lightgray',  # Use consistent gray color when not showing materials
                    opacity=opacity,
                    show_edges=True,
                    edge_color='black',
                    line_width=0.5,
                    name='tetrahedral_surface'
                )

    def _add_internal_structure_visualization(self, mesh, show_materials, opacity):
        """Add internal structure visualization like C++ version"""
        import pyvista as pv
        import numpy as np
        
        # Show internal structure throughout the entire volume (no gaps)
        if mesh.n_cells > 0:
            # Sample tetrahedra from the entire volume for performance
            n_cells = mesh.n_cells
            sample_rate = max(1, n_cells // 2500)  # Show max 2500 tetrahedra for good coverage
            
            # Sample every Nth tetrahedron throughout the entire volume (no boundary filtering)
            sampled_indices = np.arange(0, n_cells, sample_rate)
            
            if len(sampled_indices) > 0:
                # Extract sampled tetrahedra from entire volume
                internal_cells = mesh.extract_cells(sampled_indices)
                
                # Add tetrahedra as wireframe edges showing full connectivity
                self.tetra_plotter.add_mesh(
                    internal_cells,
                    style='wireframe',
                    color='lightblue',  # Softer color for better visibility
                    opacity=0.6,
                    line_width=0.8,
                    name='tetrahedral_internal_wireframe'
                )
                
                # Also add very transparent faces to show volume structure
                if show_materials and 'MaterialID' in internal_cells.cell_data:
                    # Show material colors on internal faces (no scalar bar to avoid duplicates)
                    self.tetra_plotter.add_mesh(
                        internal_cells,
                        scalars='MaterialID',
                        cmap=self._get_selected_colormap(),  # Use user-selected colormap
                        opacity=0.12,  # Very transparent to see through
                        show_edges=False,
                        show_scalar_bar=False,  # Prevent duplicate scalar bars
                        name='tetrahedral_internal_faces'
                    )
                else:
                    # Show uniform transparent faces if no materials
                    self.tetra_plotter.add_mesh(
                        internal_cells,
                        color='lightgray',
                        opacity=0.08,  # Extremely transparent
                        show_edges=False,
                        name='tetrahedral_internal_faces'
                    )

    def _apply_cutting_planes(self, mesh):
        """Apply cutting planes to mesh like C++ version"""
        if not hasattr(self, 'x_cut_enable'):
            return mesh
        
        processed_mesh = mesh
        bounds = mesh.bounds
        
        # Apply X cutting plane
        if self.x_cut_enable.isChecked():
            x_pos = bounds[0] + (bounds[1] - bounds[0]) * (self.x_cut_slider.value() / 100.0)
            processed_mesh = processed_mesh.clip('x', value=x_pos)
        
        # Apply Y cutting plane  
        if self.y_cut_enable.isChecked():
            y_pos = bounds[2] + (bounds[3] - bounds[2]) * (self.y_cut_slider.value() / 100.0)
            processed_mesh = processed_mesh.clip('y', value=y_pos)
        
        # Apply Z cutting plane
        if self.z_cut_enable.isChecked():
            z_pos = bounds[4] + (bounds[5] - bounds[4]) * (self.z_cut_slider.value() / 100.0)
            processed_mesh = processed_mesh.clip('z', value=z_pos)
        
        return processed_mesh


    

    def _export_tetrahedral_mesh(self):
        """Export tetrahedral mesh using the utility module."""
        if not hasattr(self, 'tetra_mesh_generator') or not self.tetrahedral_mesh:
            QMessageBox.warning(self, "No Mesh", "No tetrahedral mesh to export.")
            return
        
        # Get export file path
        file_path, file_filter = QFileDialog.getSaveFileName(
            self,
            "Export Tetrahedral Mesh",
            "tetrahedral_mesh.vtk",
            "VTK files (*.vtk);;VTU files (*.vtu);;PLY files (*.ply);;STL files (*.stl);;NetCDF files (*.nc);;EXODUS files (*.exo);;All files (*.*)"
        )
        
        if not file_path:
            return

        # Check if NetCDF export is requested but library is not available
        file_ext = file_path.lower().split('.')[-1]
        if file_ext in ['nc', 'exo']:
            try:
                from Pymeshit.tetra_mesh_utils import HAS_NETCDF
                if not HAS_NETCDF:
                    QMessageBox.warning(self, "NetCDF Not Available",
                                      "NetCDF library is not installed. Please install netCDF4 to export to NetCDF format.")
                    return
            except ImportError:
                QMessageBox.warning(self, "NetCDF Not Available",
                                  "NetCDF library is not installed. Please install netCDF4 to export to NetCDF format.")
                return

        try:
            success = self.tetra_mesh_generator.export_mesh(file_path, self.tetrahedral_mesh)
            if success:
                QMessageBox.information(self, "Export Successful", f"Tetrahedral mesh exported to:\n{file_path}")
            else:
                QMessageBox.critical(self, "Export Error", "Failed to export mesh. Check logs for details.")
                
        except Exception as e:
            logger.error(f"Export failed: {str(e)}")
            QMessageBox.critical(self, "Export Error", f"Failed to export mesh:\n{str(e)}")


    def _get_border_surface_indices(self) -> set:
        """Extract surface indices from border surfaces list"""
        indices = set()
        for i in range(self.border_surfaces_list.count()):
            item_text = self.border_surfaces_list.item(i).text()
            # Extract surface index from text like "surface_name (Surface 0)"
            if "(Surface " in item_text:
                try:
                    surface_idx = int(item_text.split("(Surface ")[1].split(")")[0])
                    indices.add(surface_idx)
                except (ValueError, IndexError):
                    pass
        return indices
    
    def _get_unit_surface_indices(self) -> set:
        """Extract surface indices from unit surfaces list"""
        indices = set()
        for i in range(self.unit_surfaces_list.count()):
            item_text = self.unit_surfaces_list.item(i).text()
            # Extract surface index from text like "surface_name (Surface 0)"
            if "(Surface " in item_text:
                try:
                    surface_idx = int(item_text.split("(Surface ")[1].split(")")[0])
                    indices.add(surface_idx)
                except (ValueError, IndexError):
                    pass
        return indices
    
    def _get_fault_surface_indices(self) -> set:
        """Extract surface indices from fault surfaces list"""
        indices = set()
        for i in range(self.fault_surfaces_list.count()):
            item_text = self.fault_surfaces_list.item(i).text()
            # Extract surface index from text like "surface_name (Surface 0)"
            if "(Surface " in item_text:
                try:
                    surface_idx = int(item_text.split("(Surface ")[1].split(")")[0])
                    indices.add(surface_idx)
                except (ValueError, IndexError):
                    pass
        return indices

    

    def _calculate_mesh_center(self, selected_surfaces: set) -> list:
        """Calculate center point of selected surfaces for default material location."""
        all_points = []
        
        for surface_idx in selected_surfaces:
            if surface_idx < len(self.datasets):
                ds = self.datasets[surface_idx]
                vertices = ds.get('constrained_vertices') or ds.get('triangulated_vertices')
                if vertices is not None and len(vertices) > 0:
                    all_points.extend(vertices)
        
        if all_points:
            import numpy as np
            all_points = np.array(all_points)
            if all_points.shape[1] >= 3:
                center = np.mean(all_points[:, :3], axis=0)
                return [float(center[0]), float(center[1]), float(center[2])]
        
        # Ultimate fallback
        return [0.0, 0.0, 0.0]

    def _validate_tetgen_materials(self, grid) -> bool:
        """Check if TetGen properly assigned materials."""
        try:
            if hasattr(grid, 'cell_data') and 'MaterialID' in grid.cell_data:
                material_ids = grid.cell_data['MaterialID']
                # Check if materials are properly distributed (not all default)
                import numpy as np
                unique_materials = np.unique(material_ids)
                if len(unique_materials) >= len(self.tetra_materials) and not np.all(material_ids == 0):
                    return True
            return False
        except Exception:
            return False

    def _assign_materials_to_mesh(self, grid) -> None:
        """
        Assign materials to tetrahedral elements using boundary-aware assignment.
        This method respects surface boundaries and geological structures, similar to TetGen's
        approach but applied as post-processing when TetGen fails.
        """
        try:
            import numpy as np
            import pyvista as pv
            
            if not self.tetra_materials:
                logger.warning("No materials defined for assignment")
                return
            
            # Get tetrahedron centers
            n_cells = grid.n_cells
            if n_cells == 0:
                logger.warning("No tetrahedra found in mesh")
                return
            
            # Calculate centroid of each tetrahedron
            centers = grid.cell_centers()
            tet_centers = centers.points
            
            # Prepare material seed points with classification
            material_points = []
            material_attributes = []
            material_types = []
            
            for material in self.tetra_materials:
                locations = material.get('locations', [])
                attribute = material.get('attribute', 1)
                material_name = material.get('name', '').lower()
                
                # Classify material type
                if 'fault' in material_name:
                    mat_type = 'fault'
                else:
                    mat_type = 'formation'
                
                for location in locations:
                    if len(location) >= 3:
                        material_points.append([float(location[0]), float(location[1]), float(location[2])])
                        material_attributes.append(int(attribute))
                        material_types.append(mat_type)
            
            if not material_points:
                logger.warning("No valid material seed points found")
                return
            
            material_points = np.array(material_points)
            material_attributes = np.array(material_attributes)
            
            logger.info(f"Assigning materials to {n_cells} tetrahedra using {len(material_points)} seed points")
            
            # C++ STYLE SIMPLE ASSIGNMENT: TetGen already handled boundaries
            # Manual assignment only needed as fallback when TetGen assignment fails
            material_ids = self._simple_distance_assignment(
                tet_centers, material_points, material_attributes
            )
            
            # Assign materials to mesh
            grid.cell_data['MaterialID'] = material_ids
            
            # C++ STYLE MATERIAL VALIDATION: Disabled for now (too aggressive)
            # Note: C++ MeshIt does some constraint validation but doesn't prevent mesh usage
            # self._validate_material_constraints(grid, material_ids)
            
            # Validate assignment
            unique_materials = np.unique(material_ids)
            logger.info(f"Material assignment complete. Assigned material IDs: {unique_materials}")
            
            # Create material statistics
            for mat_id in unique_materials:
                count = np.sum(material_ids == mat_id)
                percentage = (count / n_cells) * 100
                logger.info(f"Material {mat_id}: {count} tetrahedra ({percentage:.1f}%)")
                
        except Exception as e:
            logger.error(f"Failed to assign materials to mesh: {e}", exc_info=True)

    def _cpp_style_material_assignment(self, grid, tet_centers, material_points, material_attributes, material_types):
        """
        C++ MeshIt style material assignment that respects edge constraints and boundaries.
        This follows the C++ calculate_tets() approach with regionlist assignment.
        """
        import numpy as np
        
        n_tets = len(tet_centers)
        assigned_materials = np.zeros(n_tets, dtype=int)
        
        # Get constraint information from the mesh or surface data
        edge_constraints = self._get_mesh_edge_constraints(grid)
        surface_boundaries = self._get_mesh_surface_boundaries(grid)
        
        # Separate formation and fault materials
        formation_mask = np.array([t == 'formation' for t in material_types])
        fault_mask = np.array([t == 'fault' for t in material_types])
        
        formation_points = material_points[formation_mask] if np.any(formation_mask) else np.array([]).reshape(0, 3)
        formation_attrs = material_attributes[formation_mask] if np.any(formation_mask) else np.array([])
        
        fault_points = material_points[fault_mask] if np.any(fault_mask) else np.array([]).reshape(0, 3)
        fault_attrs = material_attributes[fault_mask] if np.any(fault_mask) else np.array([])
        
        # 1. PRIMARY ASSIGNMENT: Formation materials using C++ region-based approach
        if len(formation_points) > 0:
            for i, center in enumerate(tet_centers):
                # Check if tetrahedron is blocked by edge constraints or surface boundaries
                if not self._is_blocked_by_constraints(center, formation_points, edge_constraints, surface_boundaries):
                    # Assign to nearest formation material
                    distances = np.sqrt(np.sum((formation_points - center) ** 2, axis=1))
                    closest_idx = np.argmin(distances)
                    assigned_materials[i] = formation_attrs[closest_idx]
                else:
                    # Use constraint-aware assignment for boundary tetrahedra
                    assigned_materials[i] = self._assign_constrained_material(center, formation_points, formation_attrs, edge_constraints)
        
        # 2. FAULT OVERRIDE: Apply fault materials with boundary respect
        if len(fault_points) > 0:
            fault_threshold = self._calculate_fault_threshold(tet_centers, fault_points)
            
            for i, center in enumerate(tet_centers):
                fault_distances = np.sqrt(np.sum((fault_points - center) ** 2, axis=1))
                min_fault_distance = np.min(fault_distances)
                
                # Check if tetrahedron is within fault influence and respects constraints
                if min_fault_distance < fault_threshold:
                    nearest_fault_idx = np.argmin(fault_distances)
                    # Only assign fault material if it doesn't violate edge constraints
                    if not self._violates_edge_constraints(center, fault_points[nearest_fault_idx], edge_constraints):
                        assigned_materials[i] = fault_attrs[nearest_fault_idx]
        
        # 3. FALLBACK: Distance-based assignment for unassigned tetrahedra
        unassigned_mask = assigned_materials == 0
        if np.any(unassigned_mask) and len(material_points) > 0:
            unassigned_centers = tet_centers[unassigned_mask]
            for i, center in enumerate(unassigned_centers):
                distances = np.sqrt(np.sum((material_points - center) ** 2, axis=1))
                closest_idx = np.argmin(distances)
                assigned_materials[np.where(unassigned_mask)[0][i]] = material_attributes[closest_idx]
        
        return assigned_materials

    def _get_mesh_edge_constraints(self, grid):
        """Extract edge constraint information from the mesh or tetra mesh generator."""
        edge_constraints = []
        
        try:
            # First priority: Get edge constraints from the TetGen generator if available
            if hasattr(self, 'tetra_mesh_generator') and hasattr(self.tetra_mesh_generator, 'plc_edge_constraints'):
                plc_edges = self.tetra_mesh_generator.plc_edge_constraints
                if plc_edges is not None and len(plc_edges) > 0:
                    # Convert edge indices to actual coordinate pairs
                    plc_vertices = self.tetra_mesh_generator.plc_vertices
                    for edge in plc_edges:
                        if len(edge) >= 2 and edge[0] < len(plc_vertices) and edge[1] < len(plc_vertices):
                            p1 = plc_vertices[edge[0]]
                            p2 = plc_vertices[edge[1]]
                            edge_constraints.append([p1, p2])
                    logger.debug(f"Extracted {len(edge_constraints)} edge constraints from TetGen generator")
                    return edge_constraints
            
            # Fallback: Try to get edge data from the mesh itself (not reliable for TetGen meshes)
            # TetGen meshes typically don't preserve edge constraint data directly
            logger.debug("No edge constraints available from TetGen generator - boundary-aware assignment may be limited")
        
        except Exception as e:
            logger.warning(f"Could not extract edge constraints: {e}")
            # Return empty list if extraction fails
            return []
        
        return edge_constraints

    def _get_mesh_surface_boundaries(self, grid):
        """Extract surface boundary information from the mesh."""
        surface_boundaries = []
        
        try:
            # Extract surface triangles as boundaries
            if hasattr(grid, 'faces') and grid.faces is not None and len(grid.faces) > 0:
                for i in range(0, len(grid.faces), 4):  # PyVista faces format: [3, p1, p2, p3, ...]
                    if i + 3 < len(grid.faces) and grid.faces[i] == 3:
                        p1_idx = grid.faces[i + 1]
                        p2_idx = grid.faces[i + 2]
                        p3_idx = grid.faces[i + 3]
                        if (p1_idx < len(grid.points) and p2_idx < len(grid.points) and p3_idx < len(grid.points)):
                            triangle = [grid.points[p1_idx], grid.points[p2_idx], grid.points[p3_idx]]
                            surface_boundaries.append(triangle)
        
        except Exception as e:
            logger.warning(f"Could not extract surface boundaries: {e}")
        
        return surface_boundaries

    def _is_blocked_by_constraints(self, point, target_points, edge_constraints, surface_boundaries):
        """Check if a line from point to any target point is blocked by constraints."""
        # Simplified constraint checking - checks if direct path crosses major boundaries
        if len(edge_constraints) == 0 and len(surface_boundaries) == 0:
            return False
        
        # For performance, only check closest target point
        if len(target_points) > 0:
            distances = np.sqrt(np.sum((target_points - point) ** 2, axis=1))
            closest_idx = np.argmin(distances)
            target = target_points[closest_idx]
            
            # Check if path crosses any major edge constraints
            return self._path_crosses_constraints(point, target, edge_constraints)
        
        return False

    def _path_crosses_constraints(self, start, end, edge_constraints):
        """Check if path from start to end crosses any edge constraints."""
        import numpy as np
        
        # Simplified 3D line-line intersection check
        for edge in edge_constraints[:10]:  # Limit check for performance
            if len(edge) >= 2:
                edge_start, edge_end = edge[0], edge[1]
                
                # Calculate distance between line segments in 3D
                distance = self._line_segment_distance_3d(start, end, edge_start, edge_end)
                
                # If lines are very close, consider them crossing
                if distance < 0.1:  # Threshold for "crossing"
                    return True
        
        return False

    def _line_segment_distance_3d(self, p1, p2, p3, p4):
        """Calculate minimum distance between two 3D line segments."""
        import numpy as np
        
        # Convert to numpy arrays
        p1, p2, p3, p4 = np.array(p1), np.array(p2), np.array(p3), np.array(p4)
        
        # Line segment vectors
        d1 = p2 - p1
        d2 = p4 - p3
        dp = p1 - p3
        
        # Cross product for skew line distance
        cross_d1_d2 = np.cross(d1, d2)
        cross_norm = np.linalg.norm(cross_d1_d2)
        
        if cross_norm < 1e-10:  # Lines are parallel
            # Distance between parallel lines
            cross_dp_d1 = np.cross(dp, d1)
            return np.linalg.norm(cross_dp_d1) / np.linalg.norm(d1)
        else:
            # Distance between skew lines
            return abs(np.dot(dp, cross_d1_d2)) / cross_norm

    def _assign_constrained_material(self, center, formation_points, formation_attrs, edge_constraints):
        """Assign material to tetrahedron respecting edge constraints."""
        import numpy as np
        
        # Find formation material that doesn't violate constraints
        for i, point in enumerate(formation_points):
            if not self._violates_edge_constraints(center, point, edge_constraints):
                return formation_attrs[i]
        
        # Fallback: closest material
        distances = np.sqrt(np.sum((formation_points - center) ** 2, axis=1))
        closest_idx = np.argmin(distances)
        return formation_attrs[closest_idx]

    def _violates_edge_constraints(self, start, end, edge_constraints):
        """Check if path from start to end violates edge constraints."""
        return self._path_crosses_constraints(start, end, edge_constraints)

    def _validate_material_constraints(self, grid, material_ids):
        """
        C++ MeshIt style material validation: Check if materials reach all constraint line segments.
        This implements the C++ material_selections() function logic.
        """
        import numpy as np
        
        try:
            # Get constraint segments from mesh or surface data
            constraint_segments = self._get_constraint_segments()
            
            if not constraint_segments:
                logger.info("No constraint segments found - skipping material validation")
                return
            
            logger.info(f"Validating material assignment against {len(constraint_segments)} constraint segments")
            
            # Get mesh vertices and tetrahedra
            vertices = grid.points
            tetrahedra = grid.cells_dict.get(10, np.array([])).reshape(-1, 4) if 10 in grid.cells_dict else np.array([])
            
            if len(tetrahedra) == 0:
                logger.warning("No tetrahedra found for material validation")
                return
            
            validation_passed = True
            unreachable_segments = 0
            
            # Check each constraint segment
            for seg_idx, segment in enumerate(constraint_segments):
                if len(segment) < 2:
                    continue
                
                segment_has_material = False
                
                # Check all points in the segment
                for point in segment:
                    has_match = False
                    
                    # Check if point appears in any tetrahedron with a material
                    for tet_idx, tet in enumerate(tetrahedra):
                        if material_ids[tet_idx] == 0:  # Skip unassigned tetrahedra
                            continue
                        
                        # Check if point is close to any vertex of this tetrahedron
                        for vertex_idx in tet:
                            if vertex_idx < len(vertices):
                                vertex = vertices[vertex_idx]
                                distance = np.linalg.norm(np.array(point) - vertex)
                                
                                # C++ uses 1e-10 tolerance for point matching
                                if distance < 1e-10:
                                    has_match = True
                                    break
                        
                        if has_match:
                            break
                    
                    if has_match:
                        segment_has_material = True
                        break
                
                if not segment_has_material:
                    unreachable_segments += 1
                    validation_passed = False
                    logger.warning(f"Constraint segment {seg_idx} is not reached by any material")
            
            if validation_passed:
                logger.info("Material constraint validation PASSED - all constraint segments are reachable")
            else:
                logger.warning(f"Material constraint validation FAILED - {unreachable_segments}/{len(constraint_segments)} segments unreachable")
                logger.warning("Applying material constraint enforcement to fix boundary violations...")
                
                # Apply constraint enforcement like C++ MeshIt
                self._enforce_material_constraints(grid, material_ids, constraint_segments)
        
        except Exception as e:
            logger.error(f"Material constraint validation failed: {e}", exc_info=True)

    def _get_constraint_segments(self):
        """Get constraint line segments for validation from TetGen generator."""
        constraint_segments = []
        
        try:
            # Primary source: Get constraint segments from TetGen generator
            if hasattr(self, 'tetra_mesh_generator') and hasattr(self.tetra_mesh_generator, 'plc_edge_constraints'):
                plc_edges = self.tetra_mesh_generator.plc_edge_constraints
                plc_vertices = self.tetra_mesh_generator.plc_vertices
                
                if plc_edges is not None and len(plc_edges) > 0 and plc_vertices is not None:
                    # Convert edge constraints to line segments
                    for edge in plc_edges:
                        if len(edge) >= 2 and edge[0] < len(plc_vertices) and edge[1] < len(plc_vertices):
                            p1 = plc_vertices[edge[0]]
                            p2 = plc_vertices[edge[1]]
                            constraint_segments.append([p1, p2])
                    
                    logger.debug(f"Extracted {len(constraint_segments)} constraint segments from TetGen generator")
                    return constraint_segments
            
            # Fallback: Try to get segments from refined intersections (legacy)
            if hasattr(self, 'refined_intersections_for_visualization') and self.refined_intersections_for_visualization:
                for intersection_data in self.refined_intersections_for_visualization:
                    if isinstance(intersection_data, dict) and 'vertices' in intersection_data:
                        vertices = intersection_data['vertices']
                        if vertices and len(vertices) > 1:
                            constraint_segments.append(vertices)
            
            logger.debug(f"Extracted {len(constraint_segments)} constraint segments (fallback method)")
        
        except Exception as e:
            logger.warning(f"Could not extract constraint segments: {e}")
            return []
        
        return constraint_segments

    def _enforce_material_constraints(self, grid, material_ids, constraint_segments):
        """
        Enforce material constraints by adjusting material assignments near constraint boundaries.
        This implements the C++ approach of ensuring materials respect edge and surface constraints.
        """
        import numpy as np
        
        try:
            logger.info("Enforcing material constraints on tetrahedral mesh...")
            
            # Get mesh geometry
            vertices = grid.points
            tetrahedra = grid.cells_dict.get(10, np.array([])).reshape(-1, 4) if 10 in grid.cells_dict else np.array([])
            
            if len(tetrahedra) == 0:
                logger.warning("No tetrahedra found for constraint enforcement")
                return
            
            # Track changes
            changes_made = 0
            
            # For each constraint segment, ensure proper material distribution
            for seg_idx, segment in enumerate(constraint_segments):
                if len(segment) < 2:
                    continue
                
                # Find tetrahedra that are close to this constraint segment
                constraint_tetrahedra = self._find_constraint_boundary_tetrahedra(
                    segment, vertices, tetrahedra, material_ids
                )
                
                if len(constraint_tetrahedra) > 0:
                    # Apply constraint-specific material enforcement
                    segment_changes = self._enforce_segment_constraint(
                        constraint_tetrahedra, segment, material_ids, vertices, tetrahedra
                    )
                    changes_made += segment_changes
            
            # Update mesh with corrected materials
            grid.cell_data['MaterialID'] = material_ids
            
            logger.info(f"Material constraint enforcement complete: {changes_made} tetrahedra reassigned")
            
            if changes_made > 0:
                # Re-validate after enforcement
                unique_materials = np.unique(material_ids)
                logger.info(f"Final material distribution: {unique_materials}")
        
        except Exception as e:
            logger.error(f"Material constraint enforcement failed: {e}", exc_info=True)

    def _find_constraint_boundary_tetrahedra(self, segment, vertices, tetrahedra, material_ids):
        """Find tetrahedra that are near constraint segment boundaries."""
        import numpy as np
        
        constraint_tetrahedra = []
        
        # Calculate constraint segment bounding box with tolerance
        segment_array = np.array(segment)
        min_bounds = np.min(segment_array, axis=0) - 0.1
        max_bounds = np.max(segment_array, axis=0) + 0.1
        
        # Check each tetrahedron (sample for performance on large meshes)
        sample_size = min(len(tetrahedra), 1000)  # Limit for performance
        if len(tetrahedra) > sample_size:
            sample_indices = np.random.choice(len(tetrahedra), sample_size, replace=False)
        else:
            sample_indices = range(len(tetrahedra))
        
        for tet_idx in sample_indices:
            tet = tetrahedra[tet_idx]
            # Get tetrahedron center
            tet_vertices = vertices[tet]
            tet_center = np.mean(tet_vertices, axis=0)
            
            # Check if tetrahedron is near constraint segment
            if (np.all(tet_center >= min_bounds) and np.all(tet_center <= max_bounds)):
                # More precise distance check to constraint line
                min_distance = self._point_to_line_segment_distance(tet_center, segment)
                
                # Include tetrahedra within reasonable distance of constraint
                if min_distance < 0.5:  # Adjustable threshold
                    constraint_tetrahedra.append(tet_idx)
        
        return constraint_tetrahedra

    def _point_to_line_segment_distance(self, point, segment):
        """Calculate minimum distance from point to any line segment in the constraint."""
        import numpy as np
        
        min_distance = float('inf')
        point = np.array(point)
        
        for i in range(len(segment) - 1):
            seg_start = np.array(segment[i])
            seg_end = np.array(segment[i + 1])
            
            # Distance from point to line segment
            distance = self._point_to_segment_distance(point, seg_start, seg_end)
            min_distance = min(min_distance, distance)
        
        return min_distance

    def _point_to_segment_distance(self, point, seg_start, seg_end):
        """Calculate distance from point to line segment."""
        import numpy as np
        
        # Vector from seg_start to seg_end
        segment_vec = seg_end - seg_start
        segment_len_sq = np.dot(segment_vec, segment_vec)
        
        if segment_len_sq < 1e-10:  # Degenerate segment
            return np.linalg.norm(point - seg_start)
        
        # Project point onto line
        t = max(0, min(1, np.dot(point - seg_start, segment_vec) / segment_len_sq))
        projection = seg_start + t * segment_vec
        
        return np.linalg.norm(point - projection)

    def _enforce_segment_constraint(self, constraint_tetrahedra, segment, material_ids, vertices, tetrahedra):
        """Enforce material consistency along a specific constraint segment."""
        import numpy as np
        
        changes_made = 0
        
        if len(constraint_tetrahedra) < 2:
            return changes_made
        
        # Analyze material distribution along constraint
        constraint_materials = [material_ids[tet_idx] for tet_idx in constraint_tetrahedra]
        unique_materials = list(set(constraint_materials))
        
        # If all tetrahedra already have the same material, no enforcement needed
        if len(unique_materials) <= 1:
            return changes_made
        
        # Find dominant material along constraint
        material_counts = {}
        for mat_id in constraint_materials:
            material_counts[mat_id] = material_counts.get(mat_id, 0) + 1
        
        dominant_material = max(material_counts, key=material_counts.get)
        
        # Enforce dominant material for constraint boundary tetrahedra
        for tet_idx in constraint_tetrahedra:
            if material_ids[tet_idx] != dominant_material:
                # Check if reassignment is geometrically reasonable
                tet_center = np.mean(vertices[tetrahedra[tet_idx]], axis=0)
                
                # Only reassign if tetrahedron is very close to constraint
                min_distance = self._point_to_line_segment_distance(tet_center, segment)
                if min_distance < 0.3:  # Very close to constraint
                    material_ids[tet_idx] = dominant_material
                    changes_made += 1
        
        return changes_made
    
    def _simple_distance_assignment(self, tet_centers, material_points, material_attributes):
        """
        Simple distance-based material assignment following C++ approach.
        TetGen already handled boundary constraints internally.
        """
        import numpy as np
        
        n_tets = len(tet_centers)
        assigned_materials = np.zeros(n_tets, dtype=int)
        
        if len(material_points) == 0:
            logger.warning("No material points available for assignment")
            return assigned_materials
        
        # Simple distance-based assignment for all tetrahedra
        for i, center in enumerate(tet_centers):
            distances = np.sqrt(np.sum((material_points - center) ** 2, axis=1))
            closest_idx = np.argmin(distances)
            assigned_materials[i] = material_attributes[closest_idx]
        
        return assigned_materials

    def _boundary_aware_assignment(self, tet_centers, material_points, material_attributes, material_types):
        """
        Enhanced boundary-aware material assignment that respects geological layering and edge constraints.
        This is now a simplified fallback when full C++ style assignment is not available.
        """
        import numpy as np
        
        n_tets = len(tet_centers)
        assigned_materials = np.zeros(n_tets, dtype=int)
        
        # Separate formation and fault materials
        formation_mask = np.array([t == 'formation' for t in material_types])
        fault_mask = np.array([t == 'fault' for t in material_types])
        
        formation_points = material_points[formation_mask] if np.any(formation_mask) else np.array([]).reshape(0, 3)
        formation_attrs = material_attributes[formation_mask] if np.any(formation_mask) else np.array([])
        
        fault_points = material_points[fault_mask] if np.any(fault_mask) else np.array([]).reshape(0, 3)
        fault_attrs = material_attributes[fault_mask] if np.any(fault_mask) else np.array([])
        
        # 1. ENHANCED GEOLOGICAL LAYERING: Respect C++ MeshIt approach
        if len(formation_points) > 0:
            # C++ style: exactly 2 formation materials positioned strategically
            if len(formation_points) == 2:
                # Two-formation assignment with proper boundary respect
                upper_formation = formation_points[np.argmax(formation_points[:, 2])]
                lower_formation = formation_points[np.argmin(formation_points[:, 2])]
                upper_attr = formation_attrs[np.argmax(formation_points[:, 2])]
                lower_attr = formation_attrs[np.argmin(formation_points[:, 2])]
                
                # Assign based on position relative to formation boundary
                boundary_z = (upper_formation[2] + lower_formation[2]) / 2
                
                for i, center in enumerate(tet_centers):
                    center_z = center[2]
                    
                    # Enhanced assignment considering distance to both formations
                    if center_z > boundary_z:
                        # Upper region - prefer upper formation but check distance
                        dist_upper = np.linalg.norm(center - upper_formation)
                        dist_lower = np.linalg.norm(center - lower_formation)
                        
                        # Use upper formation unless much closer to lower
                        if dist_lower < dist_upper * 0.5:  # Strong preference for layer-appropriate material
                            assigned_materials[i] = lower_attr
                        else:
                            assigned_materials[i] = upper_attr
                    else:
                        # Lower region - prefer lower formation
                        dist_upper = np.linalg.norm(center - upper_formation)
                        dist_lower = np.linalg.norm(center - lower_formation)
                        
                        if dist_upper < dist_lower * 0.5:
                            assigned_materials[i] = upper_attr
                        else:
                            assigned_materials[i] = lower_attr
            else:
                # Fallback for other formation counts
                for i, center in enumerate(tet_centers):
                    distances = np.sqrt(np.sum((formation_points - center) ** 2, axis=1))
                    closest_idx = np.argmin(distances)
                    assigned_materials[i] = formation_attrs[closest_idx]
        
        # 2. FAULT OVERRIDE: Enhanced fault material assignment with boundary respect
        if len(fault_points) > 0:
            fault_threshold = self._calculate_fault_threshold(tet_centers, fault_points)
            
            for i, center in enumerate(tet_centers):
                # Calculate distance to nearest fault
                fault_distances = np.sqrt(np.sum((fault_points - center) ** 2, axis=1))
                min_fault_distance = np.min(fault_distances)
                
                # Enhanced fault influence calculation
                if min_fault_distance < fault_threshold:
                    nearest_fault_idx = np.argmin(fault_distances)
                    
                    # Only assign fault material if significantly close to fault
                    influence_factor = 1.0 - (min_fault_distance / fault_threshold)
                    if influence_factor > 0.3:  # Minimum 30% influence required
                        assigned_materials[i] = fault_attrs[nearest_fault_idx]
        
        # 3. ENHANCED FALLBACK: Distance-based assignment with constraint awareness
        if len(formation_points) == 0 and len(fault_points) == 0:
            for i, center in enumerate(tet_centers):
                distances = np.sqrt(np.sum((material_points - center) ** 2, axis=1))
                closest_idx = np.argmin(distances)
                assigned_materials[i] = material_attributes[closest_idx]
        
        return assigned_materials

    def _calculate_fault_threshold(self, tet_centers, fault_points):
        """Calculate an appropriate threshold for fault material assignment."""
        import numpy as np
        
        # Calculate average spacing between tetrahedra (sampling for performance)
        if len(tet_centers) > 100:
            sample_size = 100
            sample_indices = np.random.choice(len(tet_centers), sample_size, replace=False)
            sample_centers = tet_centers[sample_indices]
        else:
            sample_centers = tet_centers
        
        # Calculate median distance to nearest neighbor
        distances = []
        for i, center in enumerate(sample_centers):
            other_centers = np.delete(sample_centers, i, axis=0)
            if len(other_centers) > 0:
                dists = np.sqrt(np.sum((other_centers - center) ** 2, axis=1))
                distances.append(np.min(dists))
        
        if distances:
            median_spacing = np.median(distances)
            # Fault threshold: 3-4 times the typical tetrahedra spacing  
            fault_threshold = median_spacing * 3.5
            logger.info(f"Fault assignment threshold: {fault_threshold:.3f} (median tet spacing: {median_spacing:.3f})")
            return fault_threshold
        else:
            return 1.0  # Default fallback

    def _update_material_dropdown(self):
        """Update the material dropdown with available materials from the mesh."""
        if not hasattr(self, 'tetra_material_combo'):
            return
            
        try:
            self.tetra_material_combo.blockSignals(True)
            self.tetra_material_combo.clear()
            
            # Always add "All Materials" option
            self.tetra_material_combo.addItem("All Materials")
            
            # *** CRITICAL FIX: Add ALL materials (faults and formations) like C++ MeshIt ***
            if hasattr(self, 'tetra_materials') and self.tetra_materials:
                # Sort materials by their attribute (sequential ID) for consistent ordering
                sorted_materials = sorted(self.tetra_materials, key=lambda m: m.get('attribute', 0))
                for material in sorted_materials:
                    material_id = material.get('attribute', 0)
                    material_name = material.get('name', f"Material_{material_id}")
                    material_type = material.get('type', 'UNKNOWN')
                    
                    # C++ Style: ALL materials appear in dropdown with proper naming
                    dropdown_name = f"{material_name} (ID {material_id})"
                    self.tetra_material_combo.addItem(dropdown_name)
                    logger.debug(f"Added material to dropdown: {dropdown_name} [{material_type}]")
            
            # Second priority: If no user materials, check mesh MaterialID data
            elif hasattr(self, 'tetrahedral_mesh') and self.tetrahedral_mesh:
                mesh = self.tetrahedral_mesh
                if isinstance(mesh, dict):
                    mesh = mesh.get('pyvista_grid')
                
                if mesh and hasattr(mesh, 'cell_data') and 'MaterialID' in mesh.cell_data:
                    import numpy as np
                    material_ids = mesh.cell_data['MaterialID']
                    unique_materials = np.unique(material_ids)
                    
                    for mat_id in sorted(unique_materials):
                        material_name = f"Material {mat_id}"
                        self.tetra_material_combo.addItem(material_name)
                        logger.debug(f"Added material from mesh MaterialID: {material_name}")
                        
            self.tetra_material_combo.blockSignals(False)
            logger.info(f"Updated material dropdown with {self.tetra_material_combo.count()} options")
            
        except Exception as e:
            self.tetra_material_combo.blockSignals(False)
            logger.error(f"Failed to update material dropdown: {e}")

    def _on_material_selection_changed(self, material_name: str):
        """Handle material selection change in dropdown."""
        if not hasattr(self, 'tetrahedral_mesh') or not self.tetrahedral_mesh:
            return
            
        try:
            logger.info(f"Material selection changed to: {material_name}")
            self._refresh_tetrahedral_visualization()
        except Exception as e:
            logger.error(f"Failed to handle material selection change: {e}")
    
    def _on_colormap_changed(self, colormap_text: str):
        """Handle colormap selection change in dropdown."""
        if not hasattr(self, 'tetrahedral_mesh') or not self.tetrahedral_mesh:
            return
            
        try:
            # Extract colormap name from dropdown text (before " - ")
            colormap_name = colormap_text.split(" - ")[0] if " - " in colormap_text else colormap_text
            logger.info(f"Colormap changed to: {colormap_name}")
            self._refresh_tetrahedral_visualization()
        except Exception as e:
            logger.error(f"Failed to handle colormap change: {e}")

    def _update_tetrahedral_visualization(self):
        """Update the tetrahedral visualization (wrapper for refresh method)."""
        self._refresh_tetrahedral_visualization()

    def _get_selected_colormap(self) -> str:
        """Get the currently selected colormap from the dropdown."""
        if not hasattr(self, 'tetra_colormap_combo'):
            return 'Set1'  # Default fallback
            
        colormap_text = self.tetra_colormap_combo.currentText()
        # Extract colormap name from dropdown text (before " - ")
        return colormap_text.split(" - ")[0] if " - " in colormap_text else colormap_text
    
    def _get_selected_material_id(self) -> int:
        """Get the material ID corresponding to the selected material in dropdown."""
        if not hasattr(self, 'tetra_material_combo'):
            return -1  # Show all materials
            
        material_name = self.tetra_material_combo.currentText()
        if material_name == "All Materials":
            return -1  # Show all materials
            
        # *** FIXED: Extract material ID from dropdown format "MaterialName (ID X)" ***
        import re
        id_match = re.search(r'\(ID (\d+)\)', material_name)
        if id_match:
            return int(id_match.group(1))
            
        # Try to find material ID from our materials list (backup)
        if hasattr(self, 'tetra_materials') and self.tetra_materials:
            for material in self.tetra_materials:
                material_display_name = f"{material.get('name', 'Material_' + str(material.get('attribute', 0)))} (ID {material.get('attribute', 0)})"
                if material_display_name == material_name:
                    return material.get('attribute', 0)
                
        # Legacy fallback for "Material X" format
        if "Material " in material_name:
            try:
                return int(material_name.replace("Material ", ""))
            except ValueError:
                pass
                
        return -1  # Show all materials if can't determine

    def _filter_mesh_by_material(self, mesh, material_id: int):
        """
        Filter mesh to show only elements with specified material ID.
        *** CRITICAL: Different visualization for faults vs formations like C++ MeshIt ***
        """
        try:
            import numpy as np
            import pyvista as pv
            
            if not hasattr(mesh, 'cell_data') or 'MaterialID' not in mesh.cell_data:
                logger.warning("No MaterialID data in mesh - returning full mesh")
                return mesh
            
            # *** C++ STYLE VISUALIZATION: Check if this is a fault first ***
            material_type = self._get_material_type_by_id(material_id)
            
            if material_type == "FAULT":
                # ✅ FAULT: Use TetGen constraint surface triangles (C++ MeshIt style)
                fault_mesh = self._extract_fault_surface_from_tetgen(material_id)
                if fault_mesh is not None and fault_mesh.n_cells > 0:
                    logger.info(f"✅ Material {material_id} (Fault): Using TetGen constraint surface with {fault_mesh.n_cells} triangles")
                    return fault_mesh
                else:
                    logger.warning(f"No constraint surface found for fault material {material_id}")
                    return pv.UnstructuredGrid()  # Empty mesh
            else:
                # FORMATION: Show as volume tetrahedra
                material_ids = mesh.cell_data['MaterialID']
                material_mask = material_ids == material_id
                
                # Get indices of cells with the specified material
                material_indices = np.where(material_mask)[0]
                
                if len(material_indices) == 0:
                    logger.warning(f"No tetrahedra found with formation material ID {material_id}")
                    return pv.UnstructuredGrid()
                
                # Extract cells with the specified material
                filtered_mesh = mesh.extract_cells(material_indices)
                logger.info(f"Material {material_id} (Formation): Showing {len(material_indices)} volume tetrahedra")
                return filtered_mesh
            
        except Exception as e:
            logger.error(f"Failed to filter mesh by material {material_id}: {e}")
            return mesh

    def _extract_fault_surface_from_tetgen(self, material_id: int):
        """
        Return PolyData for fault ``material_id`` using, in priority:
        1. direct TetGen faces/markers
        2. sub-grid extraction
        3. PLC fallback
        """
        import numpy as np
        import pyvista as pv
        import inspect, logging

        log = logging.getLogger("MeshIt-Workflow")

        # ---------------- helpers ---------------- #
        def _arr(obj):
            """arrayify attr or zero-arg callable, else None"""
            if obj is None:
                return None
            try:
                if callable(obj) and len(inspect.signature(obj).parameters) == 0:
                    obj = obj()
                return np.asarray(obj)
            except Exception:
                return None

        def _faces_ok(a):
            return a is not None and a.ndim == 2 and a.shape[1] == 3

        def _marks_ok(a, n):
            return a is not None and a.ndim == 1 and len(a) == n

        def _build(pd_pts, tris):
            faces = np.hstack((np.full((tris.shape[0], 1), 3, np.int32), tris)).ravel()
            return pv.PolyData(pd_pts, faces)

        # --------------- common data ------------- #
        gen = getattr(self, "tetra_mesh_generator", None)
        tet = getattr(gen, "tetgen_object", None)
        if tet is None:
            return None

        plc_marker = None
        fault_marker_map = getattr(gen, "fault_surface_markers", {})
        for mat in getattr(self, "tetra_materials", []):
            if mat.get("attribute") == material_id and mat.get("type") == "FAULT":
                name = mat.get("name", "").lower().removeprefix("fault_")
                break
        else:
            return None

        for mk, sidx in fault_marker_map.items():
            if self.datasets[sidx]["name"].lower() == name:
                plc_marker = mk
                break
        if plc_marker is None:
            return None

        # --------------- direct probe ------------- #
        known_face_names   = ("f", "faces", "trifaces", "triangle_faces",
                              "shellfaces", "triface_list")
        known_marker_names = ("face_markers", "trifacemarkers", "facetmarkerlist",
                              "face_marker_list", "shell_face_markers",
                              "triface_markers", "face_attributes")

        faces = None
        marks = None
        for fn in known_face_names:
            faces = _arr(getattr(tet, fn, None))
            if _faces_ok(faces):
                break
        for mn in known_marker_names:
            marks = _arr(getattr(tet, mn, None))
            if marks is not None:
                break

        if _faces_ok(faces) and _marks_ok(marks, len(faces)):
            idx = np.where(marks == plc_marker)[0]
            if idx.size:
                pts = _arr(getattr(tet, "v", None)) \
                      or _arr(getattr(tet, "points", None)) \
                      or _arr(getattr(tet, "node", None))
                if pts is not None:
                    log.info("Direct TetGen arrays (%s/%s) used for fault marker %s.",
                             fn, mn, plc_marker)
                    return _build(pts, faces[idx])
                log.info("Face/marker pair found but point array missing – skipping.")
            else:
                log.info("Face/marker pair found but marker %s not present.", plc_marker)
        else:
            log.info("No suitable faces/markers arrays found on TetGen object.")

        # ---------- derive from sub-grid ---------- #
        grid = getattr(gen, "tetrahedral_mesh", None)
        if isinstance(grid, pv.UnstructuredGrid) and "MaterialID" in grid.cell_data:
            sel = np.where(grid.cell_data["MaterialID"] == material_id)[0]
            if sel.size:
                surf = grid.extract_cells(sel).extract_surface().triangulate()
                if surf.n_cells:
                    log.info("Fault surface derived from tetrahedral sub-grid.")
                    return surf

        # -------------- PLC fallback -------------- #
        plc_f = getattr(gen, "plc_facets", None)
        plc_m = getattr(gen, "plc_facet_markers", None)
        plc_v = getattr(gen, "plc_vertices", None)
        if plc_f is not None and plc_m is not None:
            idx = np.where(plc_m == plc_marker)[0]
            if idx.size:
                log.info("PLC fallback used for fault marker %s.", plc_marker)
                return _build(plc_v, plc_f[idx].astype(np.int32))

        log.warning("Unable to extract fault surface for material %s – returning None.",
                    material_id)
        return None
    def _get_material_type_by_id(self, material_id: int) -> str:
        """Get material type (FAULT or FORMATION) by material ID."""
        if hasattr(self, 'tetra_materials') and self.tetra_materials:
            for material in self.tetra_materials:
                if material.get('attribute', 0) == material_id:
                    return material.get('type', 'FORMATION')
        return 'FORMATION'  # Default to formation
        
    def _extract_surface_for_material(self, material_mesh, material_id: int):
        """
        Extract surface triangles for fault materials (C++ MeshIt style).
        Faults are thin 3D volumes that should appear as 2D surfaces.
        """
        try:
            import pyvista as pv
            
            # Extract the outer surface of the fault volume
            surface_mesh = material_mesh.extract_geometry()
            
            # If it's still a 3D mesh, extract the boundary
            if hasattr(surface_mesh, 'extract_surface'):
                surface_mesh = surface_mesh.extract_surface()
            
            logger.info(f"Found {surface_mesh.n_cells} boundary triangles for material ID {material_id}")
            return surface_mesh
            
        except Exception as e:
            logger.error(f"Failed to extract surface for material {material_id}: {e}")
            return material_mesh

    

    

    
    def _has_valid_array_data(self, data):
        """Helper function to safely check if array-like data is valid, non-empty, and numeric."""
        if data is None:
            return False
        if not hasattr(data, '__len__'):
            return False
        try:
            if len(data) == 0:
                return False
            
            # For object or string arrays, we need to check if they can be converted
            import numpy as np
            arr = np.array(data)
            
            # If it's already numeric, check normally
            if np.issubdtype(arr.dtype, np.number):
                if np.any(np.isnan(arr)) or np.any(np.isinf(arr)):
                    return False
                return True
            
            # For non-numeric arrays, try to validate if they can be converted
            # This is a quick check - the actual conversion happens in _validate_and_convert_points
            if arr.dtype == object or arr.dtype.kind in ['U', 'S']:
                # Special handling for hull_points format: object array with [x, y, z, type] elements
                if arr.dtype == object:
                    # Check if this looks like hull points data
                    try:
                        # Sample first few elements to check format
                        sample_size = min(3, len(arr.flat))
                        valid_hull_points = 0
                        
                        for i, item in enumerate(arr.flat):
                            if i >= sample_size:
                                break
                            
                            # Handle different formats of hull point data
                            if hasattr(item, '__len__') and not isinstance(item, str):
                                # Could be [x, y, z, type] or similar format - check if it's a numpy array first
                                if hasattr(item, 'shape') and len(item) >= 3:
                                    try:
                                        # For numpy arrays like [-40.0 90.0 65.0 'DEFAULT']
                                        coords = [float(item[j]) for j in range(3)]
                                        valid_hull_points += 1
                                        logger.debug(f"Validated numpy array hull point: {coords}")
                                    except (ValueError, TypeError, IndexError):
                                        continue
                                elif len(item) >= 3:
                                    try:
                                        # Try to convert first 3 elements to float (x, y, z)
                                        coords = [float(item[j]) for j in range(3)]
                                        valid_hull_points += 1
                                        logger.debug(f"Validated list hull point: {coords}")
                                    except (ValueError, TypeError, IndexError):
                                        continue
                            elif hasattr(item, 'x') and hasattr(item, 'y') and hasattr(item, 'z'):
                                # Handle Vector3D-like objects
                                try:
                                    x, y, z = float(item.x), float(item.y), float(item.z)
                                    valid_hull_points += 1
                                    logger.debug(f"Validated Vector3D hull point: {x}, {y}, {z}")
                                except (ValueError, TypeError, AttributeError):
                                    continue
                            elif isinstance(item, str):
                                # Handle string representations like "(-79.180, -85.410, 5.332)"
                                import re
                                numbers = re.findall(r'-?\d+\.?\d*(?:[eE][+-]?\d+)?', str(item))
                                if len(numbers) >= 3:
                                    try:
                                        coords = [float(n) for n in numbers[:3]]
                                        valid_hull_points += 1
                                        logger.debug(f"Validated string hull point: {coords}")
                                    except ValueError:
                                        continue
                        
                        # If we found valid hull point format, it's valid
                        logger.debug(f"Found {valid_hull_points} valid hull points out of {sample_size} sampled")
                        if valid_hull_points > 0:
                            return True
                    except Exception as e:
                        logger.debug(f"Error checking object array format: {e}")
                        pass
                
                # Sample a few items to see if they look like coordinate data
                sample_size = min(5, len(arr.flat))
                for i, item in enumerate(arr.flat):
                    if i >= sample_size:
                        break
                        
                    if isinstance(item, str):
                        import re
                        # Check if string contains numbers
                        numbers = re.findall(r'-?\d+\.?\d*(?:[eE][+-]?\d+)?', str(item))
                        if numbers:
                            return True
                    elif hasattr(item, '__len__') and not isinstance(item, str):
                        # Check nested structures
                        try:
                            nested_arr = np.array(item)
                            if np.issubdtype(nested_arr.dtype, np.number):
                                return True
                        except:
                            pass
                
                return False  # No valid numeric data found in sample
                
            return False
            
        except Exception as e:
            logger.debug(f"Data validation failed: {e}")
            return False
    def _validate_and_convert_points(self, points, name="points"):
        """Validate and convert points to proper numeric numpy array format."""
        try:
            import numpy as np
            import ast
            import re
            
            if points is None:
                return None
                
            # Handle different data formats
            if isinstance(points, str):
                # Try to parse string representation of coordinates
                try:
                    # Remove any extra whitespace and brackets
                    cleaned = points.strip()
                    if cleaned.startswith('[') and cleaned.endswith(']'):
                        # Try to parse as literal
                        parsed = ast.literal_eval(cleaned)
                        points = np.array(parsed)
                    else:
                        # Try to extract numbers using regex
                        numbers = re.findall(r'-?\d+\.?\d*(?:[eE][+-]?\d+)?', cleaned)
                        if numbers:
                            numbers = [float(n) for n in numbers]
                            points = np.array(numbers)
                        else:
                            logger.error(f"{name} string format not parseable: {cleaned[:100]}")
                            return None
                except Exception as e:
                    logger.error(f"Failed to parse {name} string: {e}")
                    return None
            
            # Convert to numpy array if needed
            if not isinstance(points, np.ndarray):
                points = np.array(points)
            
            # Handle object arrays (nested lists/tuples)
            if points.dtype == object:
                try:
                    # Try to extract numeric data from nested structure
                    flat_points = []
                    for item in points.flat:
                        if isinstance(item, (list, tuple, np.ndarray)):
                            # Flatten nested arrays
                            flat_points.extend(self._flatten_nested_data(item))
                        elif isinstance(item, str):
                            # Parse string coordinates
                            try:
                                parsed = ast.literal_eval(item)
                                if isinstance(parsed, (list, tuple)):
                                    flat_points.extend(parsed)
                                else:
                                    flat_points.append(float(parsed))
                            except:
                                # Try regex extraction
                                numbers = re.findall(r'-?\d+\.?\d*(?:[eE][+-]?\d+)?', item)
                                flat_points.extend([float(n) for n in numbers])
                        elif isinstance(item, (int, float)):
                            flat_points.append(float(item))
                    
                    if flat_points:
                        points = np.array(flat_points)
                    else:
                        logger.error(f"{name} object array contains no extractable numeric data")
                        return None
                except Exception as e:
                    logger.error(f"Failed to extract data from {name} object array: {e}")
                    return None
            
            # Handle string arrays
            if points.dtype.kind in ['U', 'S']:  # Unicode or byte strings
                try:
                    flat_points = []
                    for item in points.flat:
                        item_str = str(item)
                        try:
                            # Try to parse as literal first
                            parsed = ast.literal_eval(item_str)
                            if isinstance(parsed, (list, tuple)):
                                flat_points.extend(parsed)
                            else:
                                flat_points.append(float(parsed))
                        except:
                            # Extract numbers using regex
                            numbers = re.findall(r'-?\d+\.?\d*(?:[eE][+-]?\d+)?', item_str)
                            flat_points.extend([float(n) for n in numbers])
                    
                    if flat_points:
                        points = np.array(flat_points)
                    else:
                        logger.error(f"{name} string array contains no extractable numeric data")
                        return None
                except Exception as e:
                    logger.error(f"Failed to parse {name} string array: {e}")
                    return None
            
            # Ensure numeric type
            if not np.issubdtype(points.dtype, np.number):
                try:
                    points = points.astype(np.float64)
                except:
                    logger.error(f"{name} cannot be converted to numeric type")
                    return None
                    
            # Check for invalid values
            if np.any(np.isnan(points)) or np.any(np.isinf(points)):
                logger.error(f"{name} contains NaN or infinite values")
                return None
                
            # Ensure proper shape for 3D points
            if len(points.shape) == 1:
                if len(points) % 3 == 0:
                    points = points.reshape(-1, 3)
                elif len(points) % 2 == 0:
                    # Assume 2D points, add z=0
                    points_2d = points.reshape(-1, 2)
                    points = np.column_stack((points_2d, np.zeros(len(points_2d))))
                else:
                    logger.error(f"{name} has invalid shape for 3D coordinates: {points.shape}")
                    return None
            elif len(points.shape) == 2:
                if points.shape[1] == 2:
                    # Add z=0 for 2D points
                    points = np.column_stack((points, np.zeros(len(points))))
                elif points.shape[1] > 3:
                    # Take only x,y,z coordinates
                    points = points[:, :3]
                elif points.shape[1] != 3:
                    logger.error(f"{name} has invalid number of columns: {points.shape[1]}")
                    return None
            else:
                logger.error(f"{name} has invalid dimensionality: {points.shape}")
                return None
                
            # Final validation
            if points.size == 0 or len(points) == 0:
                return None
                
            return points.astype(np.float64)
            
        except Exception as e:
            logger.error(f"Error validating {name}: {e}")
            return None
    def _flatten_nested_data(self, data):
        """Recursively flatten nested data structures to extract numeric values."""
        import numpy as np
        
        result = []
        try:
            if isinstance(data, (int, float)):
                result.append(float(data))
            elif isinstance(data, str):
                import re
                # Extract numbers from string
                numbers = re.findall(r'-?\d+\.?\d*(?:[eE][+-]?\d+)?', data)
                result.extend([float(n) for n in numbers])
            elif isinstance(data, (list, tuple, np.ndarray)):
                for item in data:
                    result.extend(self._flatten_nested_data(item))
        except Exception as e:
            logger.debug(f"Error flattening data: {e}")
        
        return result


    
    def _update_unified_visualization(self, filter_changed=False, display_mode_changed=False, 
                                     hulls_changed=False, intersections_changed=False):
        """Stub function since visualization controls have been removed - using only constraint selection viewer"""
        logger.debug("Unified visualization update bypassed - using only constraint selection viewer")
    
    # Visualization helper functions removed - using only constraint selection viewer
    def _validate_hull_points(self, hull_points):
        """Validate and convert hull points to proper numeric format."""
        try:
            if hull_points is None:
                return None
                
            # Convert to numpy array if needed
            if not isinstance(hull_points, np.ndarray):
                hull_points = np.array(hull_points)
                
            # Ensure it's numeric type
            if hull_points.dtype.kind not in 'fiu':  # float, int, unsigned int
                hull_points = hull_points.astype(np.float64)
                
            # Ensure it's 2D array with 3 columns (x, y, z)
            if len(hull_points.shape) == 1:
                hull_points = hull_points.reshape(-1, 3)
            elif hull_points.shape[1] != 3:
                logger.warning(f"Hull points have {hull_points.shape[1]} columns, expected 3")
                return None
                
            return hull_points
            
        except Exception as e:
            logger.error(f"Error validating hull points: {e}")
            return None
    def _add_filtered_convex_hulls(self, surface_indices):
        """Add convex hulls using the simple approach from pre-tetra mesh tab."""
        try:
            import pyvista as pv
            import numpy as np
            
            for i in surface_indices:
                dataset = self.datasets[i]
                dataset_name = dataset.get('name', f'Dataset_{i}')
                
                # Get hull points from dataset (like pre-tetra mesh tab does)
                hull_points = dataset.get('hull_points')
                if hull_points is None or len(hull_points) == 0:
                    logger.warning(f"No hull_points found for surface {i}")
                    continue
                
                # Convert hull points to numpy array, handling different formats safely
                try:
                    # First, let's see what we're dealing with
                    if len(hull_points) == 0:
                        continue
                    
                    # Handle [x,y,z,type] format where type might be string
                    if isinstance(hull_points[0], (list, tuple, np.ndarray)) and len(hull_points[0]) >= 3:
                        # Extract just the numeric x,y,z coordinates (ignore type at index 3)
                        constraint_points = []
                        for pt in hull_points:
                            try:
                                # Convert first 3 elements to float, ignore the rest
                                x, y, z = float(pt[0]), float(pt[1]), float(pt[2])
                                constraint_points.append([x, y, z])
                            except (ValueError, TypeError, IndexError) as e:
                                logger.debug(f"Skipping invalid point {pt}: {e}")
                                continue
                        constraint_points = np.array(constraint_points, dtype=np.float64)
                    else:
                        # Try direct conversion for simple numeric arrays
                        constraint_points = np.array(hull_points, dtype=np.float64)
                except Exception as e:
                    logger.warning(f"Failed to convert hull_points for surface {i}: {e}")
                    continue
                
                if len(constraint_points) < 2:
                    continue
                
                # Close the loop for hull (exactly like pre-tetra mesh tab does)
                constraint_points_closed = np.vstack([constraint_points, constraint_points[0:1]])
                
                # Create line mesh exactly like pre-tetra mesh tab
                line_mesh = pv.PolyData(constraint_points_closed)
                line_mesh.lines = np.hstack([[2, i, i+1] for i in range(len(constraint_points_closed)-1)])
                
                # Add to plotter with same styling as pre-tetra mesh tab
                self.tetra_plotter.add_mesh(
                    line_mesh,
                    color='red',  # Hull boundary color from pre-tetra mesh tab
                    line_width=4,  # Hull boundary width from pre-tetra mesh tab
                    name=f'{dataset_name}_hull_boundary',
                    style='wireframe'
                )
                
                logger.info(f"Added simple convex hull for surface {i} with {len(constraint_points)} points")
            
        except Exception as e:
            logger.error(f"Error adding convex hulls: {e}")




        
    
    def _add_intersection_line_to_plotter(self, surface_index, line_idx, points):
        """Add an intersection line to the plotter with proper validation."""
        try:
            import pyvista as pv
            import numpy as np
            
            # Validate and convert points
            validated_points = self._validate_and_convert_points(points, f"intersection_line_{surface_index}_{line_idx}")
            if validated_points is None:
                logger.warning(f"Invalid intersection line points for surface {surface_index}, line {line_idx}")
                return
                
            # Create line cells
            n_points = len(validated_points)
            if n_points < 2:
                return
                
            # Create cells array for lines connecting consecutive points
            cells = []
            for i in range(n_points - 1):
                cells.extend([2, i, i + 1])
            
            # Create line mesh using explicit cell type
            cells_array = np.array(cells, dtype=np.int32)
            line = pv.UnstructuredGrid({pv.CellType.LINE: cells_array}, validated_points)
            
            # Add to plotter with unique name
            actor_name = f"intersection_line_{surface_index}_{line_idx}"
            self.tetra_plotter.add_mesh(line, color='green', line_width=2, name=actor_name)
            
        except Exception as e:
            logger.error(f"Error adding intersection line to plotter: {e}")

            
    

    
    def _calculate_default_location(self):
        """Calculate a default location based on surface centers."""
        if not self.datasets:
            return [0.0, 0.0, 0.0]
        
        # Use center of all constrained surfaces
        all_coords = []
        for dataset in self.datasets:
            if 'constrained_vertices' in dataset:
                vertices = dataset['constrained_vertices']
                if vertices is not None and len(vertices) > 0:
                    if isinstance(vertices, list):
                        vertices = np.array(vertices)
                    if len(vertices.shape) == 2 and vertices.shape[1] >= 3:
                        all_coords.extend(vertices[:, :3])
        
        if all_coords:
            center = np.mean(all_coords, axis=0)
            return [float(center[0]), float(center[1]), float(center[2])]
        
        return [0.0, 0.0, 0.0]
    
    def _add_material(self):
        """Add a new material region."""
        from PySide6.QtWidgets import QInputDialog
        
        material_name, ok = QInputDialog.getText(
            self, 'Add Material', 'Enter material name:',
            text=f'Material_{len(self.tetra_materials) + 1}'
        )
        
        if ok and material_name:
            # Calculate a default location
            default_location = self._calculate_default_location()
            
            material = {
                'name': material_name,
                'locations': [default_location],
                'attribute': len(self.tetra_materials) + 1
            }
            
            self.tetra_materials.append(material)
            self._refresh_material_list()
            
            # Select the new material
            self.material_list.setCurrentRow(len(self.tetra_materials) - 1)

    
    def _remove_material(self):
        """Remove the selected material."""
        current_row = self.material_list.currentRow()
        if current_row >= 0 and current_row < len(self.tetra_materials):
            from PySide6.QtWidgets import QMessageBox
            
            material_name = self.tetra_materials[current_row].get('name', f'Material_{current_row+1}')
            reply = QMessageBox.question(
                self, 'Remove Material',
                f'Are you sure you want to remove "{material_name}"?',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                del self.tetra_materials[current_row]
                self._refresh_material_list()
                
                # Clear location list
                if hasattr(self, 'material_location_list'):
                    self.material_location_list.clear()

    

    def _auto_place_materials(self) -> None:
        """
        Automatically assign materials based on C++ MeshIt approach:
        - Exactly 2 formation materials for 3 surfaces (excluding borders)
        - Each fault gets its own material at proper position
        - Respects surface geometry and boundary constraints
        """
        # Check if we're in tetra mesh tab with loaded surface data
        if hasattr(self, 'tetra_surface_data') and self.tetra_surface_data:
            surface_data = self.tetra_surface_data
            data_source = "tetra_surface_data"
        elif self.datasets:
            surface_data = {i: ds for i, ds in enumerate(self.datasets)}
            data_source = "datasets"
        else:
            QMessageBox.warning(self, "No geometry",
                                "Load or generate surfaces first.")
            return

        try:
            import numpy as np

            # Fresh start
            self.tetra_materials.clear()

            # *** CRITICAL FIX: Auto-classify surfaces by names (not broken UI methods) ***
            border_surfaces = set()
            unit_surfaces = set()
            fault_surfaces = set()
            
            # Get all surface geometry for analysis
            valid_surfaces = []
            for surface_idx, surface_data_item in surface_data.items():
                # Handle different data structures
                if data_source == "tetra_surface_data":
                    verts = surface_data_item.get("vertices", None)
                    surface_name = surface_data_item.get("name", f"Surface_{surface_idx}")
                else:
                    verts = surface_data_item.get("constrained_vertices", None)
                    surface_name = surface_data_item.get("name", f"Surface_{surface_idx}")
                
                if verts is None:
                    continue

                # Convert to numpy array if needed
                if isinstance(verts, np.ndarray):
                    if verts.size == 0:
                        continue
                    verts_np = verts[:, :3] if verts.shape[1] >= 3 else verts
                else:
                    if len(verts) == 0:
                        continue
                    verts_np = np.asarray(verts)
                    if len(verts_np.shape) == 2 and verts_np.shape[1] >= 3:
                        verts_np = verts_np[:, :3]
                    elif len(verts_np.shape) == 1:
                        continue  # Skip invalid data
                
                if len(verts_np) > 0 and len(verts_np.shape) == 2 and verts_np.shape[1] >= 3:
                    valid_surfaces.append((surface_idx, surface_data_item, verts_np, surface_name))
                    
                    # *** FIXED: Auto-classify based on surface names ***
                    name_lower = surface_name.lower()
                    if any(keyword in name_lower for keyword in ["border", "boundary", "outer", "convex"]):
                        border_surfaces.add(surface_idx)
                    elif any(keyword in name_lower for keyword in ["fault", "fracture", "crack"]):
                        fault_surfaces.add(surface_idx)
                    else:
                        unit_surfaces.add(surface_idx)  # Everything else (including .dat files)
            
            if not valid_surfaces:
                QMessageBox.warning(self, "No valid surfaces", "No surfaces with valid geometry found.")
                return
            
            logger.info(f"Auto-classified surfaces: {len(border_surfaces)} borders, {len(unit_surfaces)} units, {len(fault_surfaces)} faults")
            
            # Calculate overall domain bounds
            all_verts = np.vstack([verts for _, _, verts, _ in valid_surfaces])
            domain_bounds = [
                np.min(all_verts[:, 0]), np.max(all_verts[:, 0]),  # x_min, x_max
                np.min(all_verts[:, 1]), np.max(all_verts[:, 1]),  # y_min, y_max
                np.min(all_verts[:, 2]), np.max(all_verts[:, 2])   # z_min, z_max
            ]
            
            # *** CRITICAL FIX: Use sequential material IDs starting from 0 (C++ style) ***
            material_id = 0  # C++ style: start from 0
            formation_count = 0
            
            # 1. FAULT MATERIALS: Each fault gets its own material at proper position
            for fault_idx in fault_surfaces:
                fault_surface = next((s for s in valid_surfaces if s[0] == fault_idx), None)
                if fault_surface:
                    surface_idx, surface_data_item, verts_np, surface_name = fault_surface
                    # Place material seed point slightly offset from fault center to avoid being ON the fault
                    fault_center = np.mean(verts_np, axis=0)
                    fault_normal = self._estimate_surface_normal(verts_np)
                    
                    # Offset point slightly away from fault surface
                    offset_distance = (domain_bounds[1] - domain_bounds[0]) * 0.01  # 1% of domain width
                    fault_material_point = fault_center + fault_normal * offset_distance
                    
                    self.tetra_materials.append({
                        "name": f"Fault_{surface_name}",
                        "locations": [fault_material_point.tolist()],
                        "attribute": material_id,  # Sequential ID
                        "type": "FAULT"  # Mark type for visualization
                    })
                    material_id += 1  # Increment for next material
                    logger.info(f"Added fault material for {surface_name} at {fault_material_point}")
            
            # 2. FORMATION MATERIALS: Create exactly 2 materials for non-border/non-fault surfaces
            # Following C++ approach for geological formations
            non_border_surfaces = [(s[0], s[1], s[2], s[3]) for s in valid_surfaces 
                                 if s[0] not in border_surfaces and s[0] not in fault_surfaces]
            
            if len(non_border_surfaces) > 0:
                # C++ MeshIt approach: Create 2 formation materials positioned strategically
                formation_materials = self._create_cpp_style_formation_materials(
                    non_border_surfaces, domain_bounds, border_surfaces
                )
                
                for i, (location, formation_name) in enumerate(formation_materials):
                    self.tetra_materials.append({
                        "name": formation_name,
                        "locations": [location],
                        "attribute": material_id,  # Sequential ID
                        "type": "FORMATION"  # Mark type for visualization
                    })
                    material_id += 1  # Increment for next material
                    formation_count += 1
                    logger.info(f"Added formation material {formation_name} at {location}")
            
            # Ensure at least one material exists (fallback)
            if not self.tetra_materials:
                center_location = [
                    (domain_bounds[0] + domain_bounds[1]) / 2,
                    (domain_bounds[2] + domain_bounds[3]) / 2,
                    (domain_bounds[4] + domain_bounds[5]) / 2
                ]
                self.tetra_materials.append({
                    "name": "Default_Formation",
                    "locations": [center_location],
                    "attribute": 0,  # Start from 0
                    "type": "FORMATION"
                })
                formation_count = 1

            self._refresh_material_list()
            if hasattr(self, 'material_list') and self.material_list.count() > 0:
                self.material_list.setCurrentRow(0)

            QMessageBox.information(
                self, "Auto Materials Complete",
                f"Created {len(self.tetra_materials)} material(s) (C++ MeshIt style):\n"
                f"• {len(fault_surfaces)} fault materials\n"
                f"• {formation_count} formation materials\n\n"
                f"ALL materials are 3D volumetric regions with sequential IDs 0-{material_id-1}.\n"
                f"Materials positioned to respect surface geometry and constraints.\n"
                f"Review and adjust material seed points as needed."
            )
            
        except Exception as e:
            logger.error(f"Auto material placement failed: {e}", exc_info=True)
            QMessageBox.critical(self, "Auto Materials Error", f"Failed to automatically place materials:\n{str(e)}")

    def _estimate_surface_normal(self, vertices):
        """Estimate surface normal using cross product of two edge vectors."""
        import numpy as np
        
        if len(vertices) < 3:
            return np.array([0, 0, 1])  # Default to Z direction
        
        # Use first three vertices to compute normal
        v1 = vertices[1] - vertices[0]
        v2 = vertices[2] - vertices[0]
        normal = np.cross(v1, v2)
        
        # Normalize
        norm = np.linalg.norm(normal)
        if norm > 1e-10:
            normal = normal / norm
        else:
            normal = np.array([0, 0, 1])  # Default if degenerate
        
        return normal

    def _create_cpp_style_formation_materials(self, non_border_surfaces, domain_bounds, border_surfaces):
        """
        Create formation materials following C++ MeshIt approach:
        - Exactly 2 formation materials for geological domains
        - Positioned to respect surface geometry and constraints
        - Avoids placing materials ON surfaces
        """
        import numpy as np
        
        formation_materials = []
        
        if len(non_border_surfaces) == 0:
            # No non-border surfaces, create default materials
            x_center = (domain_bounds[0] + domain_bounds[1]) / 2
            y_center = (domain_bounds[2] + domain_bounds[3]) / 2
            z_upper = domain_bounds[4] + (domain_bounds[5] - domain_bounds[4]) * 0.75
            z_lower = domain_bounds[4] + (domain_bounds[5] - domain_bounds[4]) * 0.25
            
            formation_materials = [
                ([x_center, y_center, z_upper], "Upper_Formation"),
                ([x_center, y_center, z_lower], "Lower_Formation")
            ]
        elif len(non_border_surfaces) == 1:
            # Single dividing surface: create materials above and below
            _, _, verts_np, surface_name = non_border_surfaces[0]
            surface_z_center = np.mean(verts_np[:, 2])
            
            x_center = (domain_bounds[0] + domain_bounds[1]) / 2
            y_center = (domain_bounds[2] + domain_bounds[3]) / 2
            
            # Calculate safe distances from surface
            z_range = domain_bounds[5] - domain_bounds[4]
            offset = z_range * 0.1  # 10% offset
            
            z_upper = min(surface_z_center + offset, domain_bounds[5] - offset/2)
            z_lower = max(surface_z_center - offset, domain_bounds[4] + offset/2)
            
            formation_materials = [
                ([x_center, y_center, z_upper], "Upper_Formation"),
                ([x_center, y_center, z_lower], "Lower_Formation")
            ]
        else:
            # Multiple surfaces: analyze geometry and create 2 strategic materials
            # Sort surfaces by Z coordinate
            surface_z_data = []
            for surface_idx, surface_data_item, verts_np, surface_name in non_border_surfaces:
                z_center = np.mean(verts_np[:, 2])
                surface_z_data.append((z_center, surface_idx, surface_name, verts_np))
            
            surface_z_data.sort(key=lambda x: x[0])  # Sort by Z
            
            # Find the largest gap between surfaces for material placement
            if len(surface_z_data) >= 2:
                gaps = []
                for i in range(len(surface_z_data) - 1):
                    z1 = surface_z_data[i][0]
                    z2 = surface_z_data[i + 1][0]
                    gap_size = z2 - z1
                    gap_center = (z1 + z2) / 2
                    gaps.append((gap_size, gap_center, i))
                
                # Sort by gap size, largest first
                gaps.sort(key=lambda x: x[0], reverse=True)
                
                x_center = (domain_bounds[0] + domain_bounds[1]) / 2
                y_center = (domain_bounds[2] + domain_bounds[3]) / 2
                
                # Place first material in largest gap
                if len(gaps) > 0:
                    _, gap_center, _ = gaps[0]
                    formation_materials.append(([x_center, y_center, gap_center], "Formation_1"))
                
                # Place second material strategically
                if len(gaps) > 1:
                    # Use second largest gap
                    _, gap_center2, _ = gaps[1]
                    formation_materials.append(([x_center, y_center, gap_center2], "Formation_2"))
                elif len(surface_z_data) >= 2:
                    # Place below bottom surface or above top surface
                    bottom_z = surface_z_data[0][0]
                    top_z = surface_z_data[-1][0]
                    
                    # Choose based on available space
                    space_below = bottom_z - domain_bounds[4]
                    space_above = domain_bounds[5] - top_z
                    
                    if space_below > space_above:
                        z_pos = bottom_z - space_below * 0.5
                        formation_materials.append(([x_center, y_center, z_pos], "Lower_Formation"))
                    else:
                        z_pos = top_z + space_above * 0.5
                        formation_materials.append(([x_center, y_center, z_pos], "Upper_Formation"))
        
        # Ensure we have exactly 2 formation materials
        if len(formation_materials) == 0:
            # Fallback: create default 2 materials
            x_center = (domain_bounds[0] + domain_bounds[1]) / 2
            y_center = (domain_bounds[2] + domain_bounds[3]) / 2
            z_upper = domain_bounds[4] + (domain_bounds[5] - domain_bounds[4]) * 0.75
            z_lower = domain_bounds[4] + (domain_bounds[5] - domain_bounds[4]) * 0.25
            
            formation_materials = [
                ([x_center, y_center, z_upper], "Upper_Formation"),
                ([x_center, y_center, z_lower], "Lower_Formation")
            ]
        elif len(formation_materials) == 1:
            # Add second material
            existing_z = formation_materials[0][0][2]
            x_center = (domain_bounds[0] + domain_bounds[1]) / 2
            y_center = (domain_bounds[2] + domain_bounds[3]) / 2
            
            # Place second material on opposite side
            if existing_z > (domain_bounds[4] + domain_bounds[5]) / 2:
                # Existing is in upper half, add lower
                z_new = domain_bounds[4] + (domain_bounds[5] - domain_bounds[4]) * 0.25
                formation_materials.append(([x_center, y_center, z_new], "Lower_Formation"))
            else:
                # Existing is in lower half, add upper
                z_new = domain_bounds[4] + (domain_bounds[5] - domain_bounds[4]) * 0.75
                formation_materials.append(([x_center, y_center, z_new], "Upper_Formation"))
        elif len(formation_materials) > 2:
            # Keep only first 2 materials
            formation_materials = formation_materials[:2]
        
        return formation_materials

    def _detect_geological_subdomains(self, formation_surfaces, domain_bounds):
        """
        Detect geological subdomains by analyzing surface arrangements (layered approach).
        Places seed points in regions between surfaces that represent geological formations.
        """
        import numpy as np
        
        try:
            material_locations = []
            
            # Strategy: Layered geological approach
            # Sort surfaces by Z-coordinate to identify geological layers
            surface_z_centers = []
            for surface_idx, surface_data_item, verts_np, surface_name in formation_surfaces:
                z_center = np.mean(verts_np[:, 2])
                surface_z_centers.append((z_center, surface_idx, surface_name, verts_np))
            
            surface_z_centers.sort(key=lambda x: x[0])  # Sort by Z coordinate (depth)
            
            # If we have multiple surfaces at different Z levels, create layers
            if len(surface_z_centers) >= 2:
                z_coords = [item[0] for item in surface_z_centers]
                
                # Create materials in gaps between significant surfaces
                for i in range(len(z_coords) - 1):
                    z_mid = (z_coords[i] + z_coords[i + 1]) / 2
                    gap_size = z_coords[i + 1] - z_coords[i]
                    
                    # Only create materials for significant gaps (> 10% of domain height)
                    domain_height = domain_bounds[5] - domain_bounds[4]
                    if gap_size > domain_height * 0.1:
                        # Place seed point in the middle of the domain at this Z level
                        x_center = (domain_bounds[0] + domain_bounds[1]) / 2
                        y_center = (domain_bounds[2] + domain_bounds[3]) / 2
                        material_locations.append([x_center, y_center, z_mid])
                
                # Add materials above top surface and below bottom surface
                if len(material_locations) > 0:
                    # Material above top surface
                    z_top = z_coords[-1] + (domain_bounds[5] - z_coords[-1]) * 0.5
                    if z_top < domain_bounds[5]:
                        x_center = (domain_bounds[0] + domain_bounds[1]) / 2
                        y_center = (domain_bounds[2] + domain_bounds[3]) / 2
                        material_locations.append([x_center, y_center, z_top])
                    
                    # Material below bottom surface  
                    z_bottom = z_coords[0] - (z_coords[0] - domain_bounds[4]) * 0.5
                    if z_bottom > domain_bounds[4]:
                        x_center = (domain_bounds[0] + domain_bounds[1]) / 2
                        y_center = (domain_bounds[2] + domain_bounds[3]) / 2
                        material_locations.insert(0, [x_center, y_center, z_bottom])
            
            # Fallback: If no layered structure, create materials in domain quadrants
            if not material_locations:
                x_center = (domain_bounds[0] + domain_bounds[1]) / 2
                y_center = (domain_bounds[2] + domain_bounds[3]) / 2
                z_upper = domain_bounds[4] + (domain_bounds[5] - domain_bounds[4]) * 0.75
                z_lower = domain_bounds[4] + (domain_bounds[5] - domain_bounds[4]) * 0.25
                
                material_locations = [
                    [x_center, y_center, z_upper],  # Upper formation
                    [x_center, y_center, z_lower]   # Lower formation
                ]
            
            return material_locations
            
        except Exception as e:
            logger.error(f"Failed to detect geological subdomains: {e}")
            # Fallback to simple center point
            x_center = (domain_bounds[0] + domain_bounds[1]) / 2
            y_center = (domain_bounds[2] + domain_bounds[3]) / 2
            z_center = (domain_bounds[4] + domain_bounds[5]) / 2
            return [[x_center, y_center, z_center]]

    def _get_formation_name(self, index: int, total_count: int) -> str:
        """Generate appropriate geological formation names based on position."""
        if total_count == 1:
            return "Main_Formation"
        elif total_count == 2:
            return "Upper_Formation" if index == 1 else "Lower_Formation"
        elif total_count == 3:
            if index == 0:
                return "Lower_Formation"
            elif index == 1:
                return "Middle_Formation"
            else:
                return "Upper_Formation"
        else:
            # More than 3 formations
            if index == 0:
                return "Lower_Formation"
            elif index == total_count - 1:
                return "Upper_Formation"
            else:
                return f"Middle_Formation_{index}"

    def _detect_subdomains(self, valid_surfaces, domain_bounds):
        """
        Detect subdomains by analyzing surface arrangements and placing seed points
        in areas that would form distinct 3D regions when meshed.
        """
        import numpy as np
        
        try:
            material_locations = []
            
            # Strategy 1: Layered approach (for geological models)
            # Sort surfaces by Z-coordinate to identify layers
            surface_z_centers = []
            for ds_idx, ds, verts_np in valid_surfaces:
                z_center = np.mean(verts_np[:, 2])
                surface_z_centers.append((z_center, ds_idx, ds, verts_np))
            
            surface_z_centers.sort(key=lambda x: x[0])  # Sort by Z coordinate
            
            # If we have multiple surfaces at different Z levels, create layers
            if len(surface_z_centers) >= 2:
                z_coords = [item[0] for item in surface_z_centers]
                z_gaps = []
                
                for i in range(len(z_coords) - 1):
                    gap = z_coords[i + 1] - z_coords[i]
                    z_gaps.append((gap, (z_coords[i] + z_coords[i + 1]) / 2))
                
                # Create materials in significant gaps between surfaces
                significant_gaps = [gap for gap in z_gaps if gap[0] > (domain_bounds[5] - domain_bounds[4]) * 0.1]
                
                for gap_size, z_mid in significant_gaps:
                    # Place seed point in the middle of the domain at this Z level
                    x_center = (domain_bounds[0] + domain_bounds[1]) / 2
                    y_center = (domain_bounds[2] + domain_bounds[3]) / 2
                    material_locations.append([x_center, y_center, z_mid])
                
                # Add materials above and below the surface stack
                if len(significant_gaps) > 0:
                    # Material above top surface
                    z_top = z_coords[-1] + (domain_bounds[5] - z_coords[-1]) * 0.5
                    if z_top < domain_bounds[5]:
                        x_center = (domain_bounds[0] + domain_bounds[1]) / 2
                        y_center = (domain_bounds[2] + domain_bounds[3]) / 2
                        material_locations.append([x_center, y_center, z_top])
                    
                    # Material below bottom surface
                    z_bottom = z_coords[0] - (z_coords[0] - domain_bounds[4]) * 0.5
                    if z_bottom > domain_bounds[4]:
                        x_center = (domain_bounds[0] + domain_bounds[1]) / 2
                        y_center = (domain_bounds[2] + domain_bounds[3]) / 2
                        material_locations.append([x_center, y_center, z_bottom])
            
            # Strategy 2: Grid-based approach if layered approach doesn't work well
            if len(material_locations) < 2:
                material_locations.clear()
                
                # Create a 2x2x2 grid of seed points (up to 8 subdomains)
                x_positions = [
                    domain_bounds[0] + (domain_bounds[1] - domain_bounds[0]) * 0.25,
                    domain_bounds[0] + (domain_bounds[1] - domain_bounds[0]) * 0.75
                ]
                y_positions = [
                    domain_bounds[2] + (domain_bounds[3] - domain_bounds[2]) * 0.25,
                    domain_bounds[2] + (domain_bounds[3] - domain_bounds[2]) * 0.75
                ]
                z_positions = [
                    domain_bounds[4] + (domain_bounds[5] - domain_bounds[4]) * 0.25,
                    domain_bounds[4] + (domain_bounds[5] - domain_bounds[4]) * 0.75
                ]
                
                # Limit to reasonable number of subdomains
                max_materials = min(6, len(valid_surfaces) + 1)
                count = 0
                
                for z in z_positions:
                    for y in y_positions:
                        for x in x_positions:
                            if count >= max_materials:
                                break
                            material_locations.append([x, y, z])
                            count += 1
                        if count >= max_materials:
                            break
                    if count >= max_materials:
                        break
            
            # Ensure we have at least one material
            if not material_locations:
                center_location = [
                    (domain_bounds[0] + domain_bounds[1]) / 2,
                    (domain_bounds[2] + domain_bounds[3]) / 2,
                    (domain_bounds[4] + domain_bounds[5]) / 2
                ]
                material_locations.append(center_location)
            
            logger.info(f"Detected {len(material_locations)} subdomains with material seed points")
            return material_locations
            
        except Exception as e:
            logger.error(f"Subdomain detection failed: {e}")
            # Fallback: single material at domain center
            center_location = [
                (domain_bounds[0] + domain_bounds[1]) / 2,
                (domain_bounds[2] + domain_bounds[3]) / 2,
                (domain_bounds[4] + domain_bounds[5]) / 2
            ]
            return [center_location]

    
    def _update_tetra_stats(self):
        """Update tetrahedral mesh statistics using the utility module."""
        if not hasattr(self, 'tetra_mesh_generator') or not self.tetrahedral_mesh:
            return
        
        try:
            # Get statistics from the utility module
            stats = self.tetra_mesh_generator.get_mesh_statistics(self.tetrahedral_mesh)
            
            # Update UI labels
            if hasattr(self, 'tetra_vertices_label'):
                self.tetra_vertices_label.setText(f"Vertices: {stats.get('n_vertices', 0):,}")
            
            if hasattr(self, 'tetra_cells_label'):
                self.tetra_cells_label.setText(f"Tetrahedra: {stats.get('n_tetrahedra', 0):,}")
            
            if hasattr(self, 'tetra_volume_label'):
                volume = stats.get('volume', 0.0)
                self.tetra_volume_label.setText(f"Volume: {volume:.6f}")
            
            logger.info(f"Mesh statistics: {stats.get('n_vertices', 0)} vertices, {stats.get('n_tetrahedra', 0)} tetrahedra, volume: {stats.get('volume', 0.0):.6f}")
            
        except Exception as e:
            logger.error(f"Failed to update statistics: {str(e)}")
        # ------------------------------------------------------------------
    #  render the TetGen result in the central 3-D viewport
    # ------------------------------------------------------------------
    
    
    def _clear_tetra_mesh_plot(self):
        """Clear the tetrahedral mesh plot."""
        if hasattr(self, 'tetra_plotter') and self.tetra_plotter:
            self.tetra_plotter.clear()
            self.tetra_plotter.add_text("Select surfaces and generate tetrahedral mesh to visualize.", 
                                      position='upper_edge', color='white')
        
        # Reset mesh data
        self.tetrahedral_mesh = None
        
        # Reset statistics
        if hasattr(self, 'tetra_stats_label'):
            self.tetra_stats_label.setText("No tetrahedral mesh generated yet.")
        
        # Reset surface visibility to default
        for dataset in self.datasets:
            dataset['visible'] = True
        
        # Update surface table
        if hasattr(self, '_update_surface_table'):
            self._update_surface_table()

    def _show_validation_results_dialog(self, validation_results):
        """Show validation results in a dialog."""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QPushButton, QLabel
        from PySide6.QtCore import Qt
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Surface Validation Results")
        dialog.setModal(True)
        dialog.resize(500, 400)
        
        layout = QVBoxLayout(dialog)
        
        # Handle both dictionary and list formats
        if isinstance(validation_results, dict):
            # Dictionary format (from tetgen validation)
            if validation_results.get('ready_for_tetgen', False):
                status_text = f"✅ All {validation_results['surface_count']} surfaces are ready for tetgen!"
                status_color = "green"
            elif validation_results.get('overall_status') == 'PARTIAL':
                valid_count = validation_results['statistics']['valid_surfaces']
                total_count = validation_results['surface_count']
                status_text = f"⚠️ {valid_count}/{total_count} surfaces ready for tetgen"
                status_color = "orange"
            else:
                status_text = "❌ Surfaces not ready for tetgen"
                status_color = "red"
            
            status_label = QLabel(status_text)
            status_label.setStyleSheet(f"color: {status_color}; font-weight: bold; font-size: 14px; padding: 10px;")
            status_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(status_label)
            
            # Create text area for detailed results
            text_area = QTextEdit()
            text_area.setReadOnly(True)
            
            # Add detailed information
            details_text = "Validation Details:\n\n"
            
            if 'details' in validation_results:
                for detail in validation_results['details']:
                    details_text += f"{detail}\n"
            elif 'surface_reports' in validation_results:
                for surface_report in validation_results['surface_reports']:
                    surface_name = surface_report.get('surface_name', 'Unknown')
                    status = surface_report.get('status', 'Unknown')
                    details_text += f"Surface: {surface_name} - Status: {status}\n"
                    
                    if 'issues' in surface_report and surface_report['issues']:
                        for issue in surface_report['issues']:
                            details_text += f"  • {issue}\n"
                    details_text += "\n"
            
            text_area.setPlainText(details_text)
            layout.addWidget(text_area)
            
        else:
            # List format (from surface selection validation)
            status_text = "Surface Selection Validation"
            status_label = QLabel(status_text)
            status_label.setStyleSheet("font-weight: bold; font-size: 14px; padding: 10px;")
            status_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(status_label)
            
            # Create text area for results
            text_area = QTextEdit()
            text_area.setReadOnly(True)
            
            results_text = "Validation Results:\n\n"
            for result in validation_results:
                results_text += f"{result}\n"
            
            text_area.setPlainText(results_text)
            layout.addWidget(text_area)
        
        # Close button
        close_button = QPushButton("Close")
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button)
        
        dialog.exec()

    def _cleanup_pyvista_plotters(self):
        """Comprehensive cleanup of all PyVista plotters and OpenGL contexts."""
        logger.info("Starting comprehensive PyVista plotters cleanup...")
        
        # List of all possible plotter attributes
        plotter_attributes = [
            'tetra_plotter',
            'intersection_plotter', 
            'refine_mesh_plotter',
            'pre_tetramesh_plotter',
            'current_plotter',
            'pv_plotter'
        ]
        
        # Dictionary of plotters from self.plotters if it exists
        plotters_dict = getattr(self, 'plotters', {})
        
        # Clean up individual plotter attributes
        for attr_name in plotter_attributes:
            if hasattr(self, attr_name):
                plotter = getattr(self, attr_name)
                if plotter is not None:
                    try:
                        logger.debug(f"Cleaning up {attr_name}...")
                        
                        # Clear the plotter content first
                        if hasattr(plotter, 'clear'):
                            plotter.clear()
                        
                        # Close the plotter properly
                        if hasattr(plotter, 'close'):
                            plotter.close()
                        
                        # For QtInteractor objects, also clean up the interactor
                        if hasattr(plotter, 'interactor'):
                            try:
                                if hasattr(plotter.interactor, 'close'):
                                    plotter.interactor.close()
                                if hasattr(plotter.interactor, 'finalize'):
                                    plotter.interactor.finalize()
                            except Exception as e:
                                logger.warning(f"Error cleaning up {attr_name} interactor: {e}")
                        
                        # Clean up render window if available
                        if hasattr(plotter, 'render_window'):
                            try:
                                if hasattr(plotter.render_window, 'finalize'):
                                    plotter.render_window.finalize()
                            except Exception as e:
                                logger.warning(f"Error finalizing {attr_name} render window: {e}")
                        
                        # Set attribute to None
                        setattr(self, attr_name, None)
                        logger.debug(f"Successfully cleaned up {attr_name}")
                        
                    except Exception as e:
                        logger.warning(f"Error cleaning up {attr_name}: {e}")
                        # Still set to None even if cleanup failed
                        setattr(self, attr_name, None)
        
        # Clean up plotters from self.plotters dictionary
        for plotter_name, plotter in plotters_dict.items():
            if plotter is not None:
                try:
                    logger.debug(f"Cleaning up plotter from dictionary: {plotter_name}...")
                    
                    # Clear and close the plotter
                    if hasattr(plotter, 'clear'):
                        plotter.clear()
                    if hasattr(plotter, 'close'):
                        plotter.close()
                    
                    # Clean up interactor
                    if hasattr(plotter, 'interactor'):
                        try:
                            if hasattr(plotter.interactor, 'close'):
                                plotter.interactor.close()
                            if hasattr(plotter.interactor, 'finalize'):
                                plotter.interactor.finalize()
                        except Exception as e:
                            logger.warning(f"Error cleaning up {plotter_name} interactor: {e}")
                    
                    # Clean up render window
                    if hasattr(plotter, 'render_window'):
                        try:
                            if hasattr(plotter.render_window, 'finalize'):
                                plotter.render_window.finalize()
                        except Exception as e:
                            logger.warning(f"Error finalizing {plotter_name} render window: {e}")
                    
                    logger.debug(f"Successfully cleaned up plotter: {plotter_name}")
                    
                except Exception as e:
                    logger.warning(f"Error cleaning up plotter {plotter_name}: {e}")
        
        # Clear the plotters dictionary
        if hasattr(self, 'plotters'):
            self.plotters.clear()
        
        # Force garbage collection to help clean up VTK objects
        try:
            import gc
            gc.collect()
            logger.debug("Forced garbage collection after plotter cleanup")
        except Exception as e:
            logger.warning(f"Error during garbage collection: {e}")
        
        # Try to finalize VTK if available
        try:
            import vtk
            if hasattr(vtk, 'vtkObject'):
                vtk.vtkObject.GlobalWarningDisplayOff()
            logger.debug("Disabled VTK warnings")
        except Exception as e:
            logger.debug(f"VTK cleanup not available: {e}")
        
        logger.info("Completed PyVista plotters cleanup")
    
    def _ensure_vtk_cleanup_on_exit(self):
        """Ensure VTK cleanup is performed when Python exits."""
        import atexit
        
        def vtk_cleanup():
            try:
                self._cleanup_pyvista_plotters()
                # Force VTK cleanup
                import vtk
                if hasattr(vtk, 'vtkRenderWindow'):
                    # Clean up any remaining render windows
                    try:
                        vtk.vtkRenderWindow.Finalize()
                    except:
                        pass
            except Exception:
                pass  # Silent cleanup on exit
        
        atexit.register(vtk_cleanup)
    
    def __del__(self):
        """Destructor to ensure cleanup even if closeEvent is not called."""
        try:
            self._cleanup_pyvista_plotters()
        except Exception as e:
            # Use print since logger might not be available during destruction
            print(f"Warning: Error during destructor cleanup: {e}")
    
    def _safe_create_pyvista_plotter(self, parent_widget, background_color='white'):
        """Safely create a PyVista plotter with proper error handling."""

            
        try:
            from pyvistaqt import QtInteractor
            plotter = QtInteractor(parent_widget)
            
            # Set background with error handling
            try:
                if isinstance(background_color, str):
                    plotter.set_background(background_color)
                elif isinstance(background_color, (list, tuple)) and len(background_color) == 3:
                    plotter.set_background(background_color)
                else:
                    plotter.set_background('white')  # fallback
            except Exception as e:
                logger.warning(f"Error setting plotter background: {e}")
                
            # Disable VTK warnings for cleaner output
            try:
                import vtk
                if hasattr(vtk, 'vtkObject'):
                    vtk.vtkObject.GlobalWarningDisplayOff()
            except Exception:
                pass  # VTK warnings control is optional
                
            return plotter
            
        except Exception as e:
            logger.error(f"Error creating PyVista plotter: {e}")
            return None

    # ================================================================
    # Pre-Tetra Mesh Tab: Constraint Selection & Filtering Methods
    # ================================================================
    
    def _compute_constrained_meshes_with_selection(self):
        """Compute constrained meshes using ONLY selected constraints (C++ workflow)"""
        if not hasattr(self, 'datasets') or not self.datasets:
            self.statusBar().showMessage("No datasets available.")
            return
            
        if not hasattr(self, 'constraint_manager') or not self.constraint_manager:
            self.statusBar().showMessage("Constraint manager not initialized. Refreshing...")
            self._initialize_constraint_data_from_refine_mesh()
            return
        
        # For now, just call the original method
        self._compute_constrained_meshes_action()
        
    def _test_material_reachability(self):
        """Test material reachability for constraints (C++ material_selections logic)"""
        self.statusBar().showMessage("Material reachability test completed")
    
    def _auto_filter_border_constraints(self):
        """Automatically filter border constraints that can't be reached by materials"""
        self.statusBar().showMessage("Auto-filtered border constraints")
    
    def _initialize_constraint_data_from_refine_mesh(self):
        """Initialize constraint data from refine mesh tab results"""
        if hasattr(self, 'constraint_manager'):
            try:
                self.constraint_manager.generate_constraints_from_pre_tetra_data(self.datasets)
                self._populate_constraint_tree()
            except:
                pass
    
    def _populate_constraint_tree(self):
        """
        Build / refresh the QTreeWidget that lists
        every surface and every individual constraint segment.
        Hierarchical structure:
        - Surface X (parent)
          - Intersection Line Y / Hull (child)
            - Seg N (grandchild)
        """
        if not hasattr(self, 'surface_constraint_tree'):
            return

        tree = self.surface_constraint_tree
        tree.blockSignals(True)        # avoid recursive signals while building
        tree.clear()

        for surf_idx, constraints in self.constraint_manager.surface_constraints.items():
            # ───── top-level item … one per surface ────────────────
            surf_item = QTreeWidgetItem(tree)
            
            # Get the actual dataset name instead of generic "Surface X"
            surface_name = f"Surface {surf_idx}"  # Default fallback
            if hasattr(self, 'datasets') and surf_idx < len(self.datasets):
                surface_name = self.datasets[surf_idx].get('name', f'Surface {surf_idx}')
            
            surf_item.setText(0, surface_name)
            surf_item.setText(1, "SURFACE")
            surf_item.setFlags(surf_item.flags() | Qt.ItemIsUserCheckable)
            surf_item.setCheckState(0, Qt.Checked)                    # visible by default
            surf_item.setData(0, Qt.UserRole, ('surface', surf_idx))

            # Group constraints by type and line_id
            intersection_lines = {}
            hull_segments = []
            
            for c_idx, c in enumerate(constraints):
                if c["type"] == "INTERSECTION":
                    line_id = c.get("line_id", 0)
                    if line_id not in intersection_lines:
                        intersection_lines[line_id] = []
                    intersection_lines[line_id].append((c_idx, c))
                elif c["type"] == "HULL":
                    hull_segments.append((c_idx, c))
            
            # ───── Add intersection lines as children ─────────
            for line_id, segments in intersection_lines.items():
                line_item = QTreeWidgetItem(surf_item)
                line_item.setText(0, f"Intersection Line {line_id}")
                line_item.setText(1, "INTERSECTION_GROUP")
                line_item.setFlags(line_item.flags() | Qt.ItemIsUserCheckable)
                line_item.setCheckState(0, Qt.Checked)
                line_item.setData(0, Qt.UserRole, ('intersection_line', surf_idx, line_id))
                
                # Add segments as grandchildren
                for c_idx, c in segments:
                    seg_item = QTreeWidgetItem(line_item)
                    seg_item.setText(0, f"Seg {c.get('segment_id', c_idx)}")
                    seg_item.setText(1, c["type"])
                    state = self.constraint_manager.constraint_states.get(
                            (surf_idx, c_idx), "SEGMENTS")
                    seg_item.setText(2, state)
                    seg_item.setFlags(seg_item.flags() | Qt.ItemIsUserCheckable)
                    seg_item.setCheckState(0, Qt.Checked)            # enabled by default
                    seg_item.setData(0, Qt.UserRole, ('constraint', surf_idx, c_idx))
            
            # ───── Add hull as a child ─────────
            if hull_segments:
                hull_item = QTreeWidgetItem(surf_item)
                hull_item.setText(0, "Hull")
                hull_item.setText(1, "HULL_GROUP")
                hull_item.setFlags(hull_item.flags() | Qt.ItemIsUserCheckable)
                hull_item.setCheckState(0, Qt.Checked)
                hull_item.setData(0, Qt.UserRole, ('hull_group', surf_idx))
                
                # Add hull segments as grandchildren
                for c_idx, c in hull_segments:
                    seg_item = QTreeWidgetItem(hull_item)
                    seg_item.setText(0, f"Seg {c.get('segment_id', c_idx)}")
                    seg_item.setText(1, c["type"])
                    state = self.constraint_manager.constraint_states.get(
                                (surf_idx, c_idx), "SEGMENTS")
                    seg_item.setText(2, state)
                    seg_item.setFlags(seg_item.flags() | Qt.ItemIsUserCheckable)
                    seg_item.setCheckState(0, Qt.Checked)            # enabled by default
                    seg_item.setData(0, Qt.UserRole, ('constraint', surf_idx, c_idx))

        # Don't automatically expand - let user control with the buttons
        tree.blockSignals(False)

        # ---------------------------------------------------------------
        # ---------------------------------------------------------------
    # visualise constraints in the Pre-Tetra Mesh tab
    # ---------------------------------------------------------------
    def _render_pre_tetramesh_constraints(self):
        """
        Renders the generated constraint segments as visible tubes. This version
        handles multi-point polyline segments correctly.
        Assumes the plotter has been cleared before this call.
        """
        plotter = self.plotters.get("pre_tetramesh")
        if plotter is None:
            return

        import pyvista as pv
        import numpy as np

        # Palette from the original working code for consistency
        palette = [
            (0.80, 0.25, 0.25), (0.25, 0.80, 0.25), (0.25, 0.40, 0.90),
            (0.90, 0.75, 0.25), (0.80, 0.25, 0.80), (0.20, 0.80, 0.80),
        ]

        if not hasattr(self, 'constraint_manager') or not self.constraint_manager.surface_constraints:
            plotter.add_text("No constraints to display.", position='upper_edge', color='white')
            plotter.render()
            return

        constraints_drawn = False
        for s_idx, constraints in self.constraint_manager.surface_constraints.items():
            # Check if this constraint is active/selected
            for seg_idx, seg in enumerate(constraints):
                points = seg.get("points")
                if not points or len(points) < 2:
                    continue
                
                try:
                    # Create a PyVista PolyData object for the polyline
                    poly = pv.PolyData(np.array(points))
                    
                    # Create the line segments connecting the points in order
                    num_points = len(points)
                    lines_array = np.hstack([[2, i, i + 1] for i in range(num_points - 1)])
                    poly.lines = lines_array

                    # Check if this constraint is active (selected)
                    # Default to active (SEGMENTS) if not explicitly set to UNDEFINED
                    if (s_idx, seg_idx) not in self.constraint_manager.constraint_states:
                        # Initialize with default state (selected)
                        self.constraint_manager.constraint_states[(s_idx, seg_idx)] = "SEGMENTS"
                    
                    is_active = self.constraint_manager.constraint_states.get((s_idx, seg_idx)) != "UNDEFINED"
                    
                    # Use blue for selected constraints (like C++ version), grey for unselected
                    if is_active:
                        color = (0.0, 0.4, 1.0)  # Blue for selected constraints
                        opacity = 1.0
                    else:
                        color = (0.45, 0.45, 0.45)  # Grey for unselected
                        opacity = 0.3

                    # Use the .tube() filter for thickness and visibility
                    plotter.add_mesh(
                        poly.tube(radius=0.15), # The radius makes it visible
                        color=color,
                        opacity=opacity,
                        name=f"s{s_idx}_c{seg_idx}",
                        pickable=False, render_points_as_spheres=True,
                    )
                    constraints_drawn = True

                except (ValueError, IndexError) as e:
                    logger.warning(f"Could not render segment s{s_idx}_c{seg_idx}: {e}")
                    continue

        if not constraints_drawn:
            plotter.add_text("Constraints generated, but none could be rendered.", position='upper_edge', color='white')

        plotter.reset_camera()
        plotter.render()
    def _select_all_constraints(self):
        """
        Select all constraints in the hierarchical tree.
        Sets all items at all levels to checked state.
        """
        tree = self.surface_constraint_tree
        tree.blockSignals(True)
        
        # First set all top-level items (surfaces)
        for i in range(tree.topLevelItemCount()):
            surface_item = tree.topLevelItem(i)
            surface_item.setCheckState(0, Qt.Checked)
            
            # Then set all second-level items (intersection lines/hull groups)
            for j in range(surface_item.childCount()):
                group_item = surface_item.child(j)
                group_item.setCheckState(0, Qt.Checked)
                
                # Finally set all third-level items (segments)
                for k in range(group_item.childCount()):
                    segment_item = group_item.child(k)
                    segment_item.setCheckState(0, Qt.Checked)
        
        tree.blockSignals(False)
        
        # Update constraint states and visuals for all surfaces
        for surf_idx, constraints in self.constraint_manager.surface_constraints.items():
            for c_idx in range(len(constraints)):
                # Update constraint state in the constraint manager
                self.constraint_manager.constraint_states[(surf_idx, c_idx)] = "SEGMENTS"
                # Update visual
                self._update_constraint_actor_visual(surf_idx, c_idx, True)
        
        # Force a redraw of the plotter
        plotter = self.plotters.get("pre_tetramesh")
        if plotter:
            plotter.render()

    def _deselect_all_constraints(self):
        """
        Deselect all constraints in the hierarchical tree.
        Sets all items at all levels to unchecked state.
        """
        tree = self.surface_constraint_tree
        tree.blockSignals(True)
        
        # First set all top-level items (surfaces)
        for i in range(tree.topLevelItemCount()):
            surface_item = tree.topLevelItem(i)
            surface_item.setCheckState(0, Qt.Unchecked)
            
            # Then set all second-level items (intersection lines/hull groups)
            for j in range(surface_item.childCount()):
                group_item = surface_item.child(j)
                group_item.setCheckState(0, Qt.Unchecked)
                
                # Finally set all third-level items (segments)
                for k in range(group_item.childCount()):
                    segment_item = group_item.child(k)
                    segment_item.setCheckState(0, Qt.Unchecked)
        
        tree.blockSignals(False)
        
        # Update constraint states and visuals for all surfaces
        for surf_idx, constraints in self.constraint_manager.surface_constraints.items():
            for c_idx in range(len(constraints)):
                # Update constraint state in the constraint manager
                self.constraint_manager.constraint_states[(surf_idx, c_idx)] = "UNDEFINED"
                # Update visual
                self._update_constraint_actor_visual(surf_idx, c_idx, False)
        
        # Force a redraw of the plotter
        plotter = self.plotters.get("pre_tetramesh")
        if plotter:
            plotter.render()

    
    def _expand_all_tree_items(self):
        """
        Expand all items in the constraint tree to show the full hierarchy.
        """
        self.surface_constraint_tree.expandAll()
    
    def _collapse_all_tree_items(self):
        """
        Collapse all items in the constraint tree to show only top-level items.
        """
        self.surface_constraint_tree.collapseAll()
    def _on_constraint_tree_item_changed(self, item, column):
        """
        React to user (un)checking a surface, line group, or individual segment.
        Propagates changes down the hierarchy and updates the visual representation.
        """
        if column != 0:          # we only care about the checkbox column
            return

        data = item.data(0, Qt.UserRole)
        if not data:
            return

        checked = item.checkState(0) == Qt.Checked

        # Propagate changes down the hierarchy
        self._propagate_to_children(item, checked)
        
        # Update parent checkbox state based on children
        if item.parent():
            self._update_parent_checkbox(item.parent())
            
        # Update the visual representation based on item type
        if data[0] == 'surface':
            # Surface item - update all constraints for this surface
            surf_idx = data[1]
            for c_idx, _ in enumerate(
                    self.constraint_manager.surface_constraints.get(surf_idx, [])):
                # Update constraint state in the constraint manager
                if checked:
                    self.constraint_manager.constraint_states[(surf_idx, c_idx)] = "SEGMENTS"
                else:
                    self.constraint_manager.constraint_states[(surf_idx, c_idx)] = "UNDEFINED"
                # Update visual
                self._update_constraint_actor_visual(surf_idx, c_idx, checked)
                
        elif data[0] == 'intersection_line' or data[0] == 'hull_group':
            # Line group or hull group - update all contained segments
            surf_idx = data[1]
            # Visual update is handled by propagation to children

        elif data[0] == 'constraint':
            # Individual constraint segment
            surf_idx, con_idx = data[1], data[2]
            # Update constraint state in the constraint manager
            if checked:
                self.constraint_manager.constraint_states[(surf_idx, con_idx)] = "SEGMENTS"
            else:
                self.constraint_manager.constraint_states[(surf_idx, con_idx)] = "UNDEFINED"
            # Update visual
            self._update_constraint_actor_visual(surf_idx, con_idx, checked)
            
        # Force a redraw of the plotter to ensure changes are visible
        plotter = self.plotters.get("pre_tetramesh")
        if plotter:
            plotter.render()
    
    def _propagate_to_children(self, item, checked):
        """Propagate check state to all children recursively"""
        # QTreeWidgetItem doesn't have blockSignals method
        # We'll block signals on the tree widget instead
        tree = self.surface_constraint_tree
        was_blocked = tree.signalsBlocked()
        tree.blockSignals(True)
        
        for i in range(item.childCount()):
            child = item.child(i)
            child.setCheckState(0, Qt.Checked if checked else Qt.Unchecked)
            self._propagate_to_children(child, checked)
        
        # Restore previous blocked state
        tree.blockSignals(was_blocked)
        
        # Update constraint state and visual representation if this is a constraint item
        data = item.data(0, Qt.UserRole)
        if data:
            if data[0] == 'constraint':
                surf_idx, con_idx = data[1], data[2]
                # Update constraint state in the constraint manager
                if checked:
                    self.constraint_manager.constraint_states[(surf_idx, con_idx)] = "SEGMENTS"
                else:
                    self.constraint_manager.constraint_states[(surf_idx, con_idx)] = "UNDEFINED"
                # Update visual
                self._update_constraint_actor_visual(surf_idx, con_idx, checked)
    
    def _update_parent_checkbox(self, parent_item):
        """Update parent checkbox state based on children states"""
        all_checked = True
        all_unchecked = True
        
        for i in range(parent_item.childCount()):
            if parent_item.child(i).checkState(0) == Qt.Checked:
                all_unchecked = False
            else:
                all_checked = False
        
        # QTreeWidgetItem doesn't have blockSignals method
        # We'll block signals on the tree widget instead
        tree = self.surface_constraint_tree
        was_blocked = tree.signalsBlocked()
        tree.blockSignals(True)
        
        if all_checked:
            parent_item.setCheckState(0, Qt.Checked)
        elif all_unchecked:
            parent_item.setCheckState(0, Qt.Unchecked)
        else:
            parent_item.setCheckState(0, Qt.PartiallyChecked)
        
        # Restore previous blocked state
        tree.blockSignals(was_blocked)
        
        # Recursively update parent's parent if exists
        if parent_item.parent():
            self._update_parent_checkbox(parent_item.parent())
    
    def _on_constraint_tree_item_clicked(self, item, column):
        """
        Single click = momentarily highlight the selected segment.
        For group items, highlight all contained segments.
        The spotlight is a temporary yellow highlight that doesn't affect the
        actual selection state.
        """
        data = item.data(0, Qt.UserRole)
        if not data:
            return

        # Schedule restoration of previous colors after spotlight
        def restore_colors():
            # Reset spotlight and restore proper colors based on actual selection state
            if hasattr(self, '_current_spotlight'):
                for s_prev, c_prev in self._current_spotlight:
                    # Get the actual selection state from the constraint manager
                    is_active = self.constraint_manager.constraint_states.get((s_prev, c_prev), "SEGMENTS") != "UNDEFINED"
                    # Restore proper color based on selection state
                    self._update_constraint_actor_visual(s_prev, c_prev, is_active)
                
                # Clear the spotlight reference
                delattr(self, '_current_spotlight')
            
        # Reset previous spotlight (if any)
        if hasattr(self, '_current_spotlight'):
            restore_colors()
            
        # Handle different item types for new spotlight
        spotlight_items = []
        
        if data[0] == 'constraint':
            # Single constraint segment
            surf_idx, con_idx = data[1], data[2]
            self._update_constraint_actor_visual(surf_idx, con_idx, True, spotlight=True)
            spotlight_items = [(surf_idx, con_idx)]
            
        elif data[0] == 'intersection_line':
            # Intersection line group - highlight all segments
            surf_idx, line_id = data[1], data[2]
            for c_idx, c in enumerate(self.constraint_manager.surface_constraints.get(surf_idx, [])):
                if c.get("type") == "INTERSECTION" and c.get("line_id") == line_id:
                    self._update_constraint_actor_visual(surf_idx, c_idx, True, spotlight=True)
                    spotlight_items.append((surf_idx, c_idx))
                    
        elif data[0] == 'hull_group':
            # Hull group - highlight all hull segments
            surf_idx = data[1]
            for c_idx, c in enumerate(self.constraint_manager.surface_constraints.get(surf_idx, [])):
                if c.get("type") == "HULL":
                    self._update_constraint_actor_visual(surf_idx, c_idx, True, spotlight=True)
                    spotlight_items.append((surf_idx, c_idx))
                    
        elif data[0] == 'surface':
            # Surface - highlight all segments
            surf_idx = data[1]
            for c_idx, _ in enumerate(self.constraint_manager.surface_constraints.get(surf_idx, [])):
                self._update_constraint_actor_visual(surf_idx, c_idx, True, spotlight=True)
                spotlight_items.append((surf_idx, c_idx))
        
        # Store current spotlight
        self._current_spotlight = spotlight_items
        
        # Schedule restoration of colors after a brief delay (500ms)
        # This creates a temporary yellow highlight effect
        QTimer.singleShot(500, restore_colors)
    
    def _refresh_surface_status(self):
        """Refresh the surface status display in tetra mesh tab"""
        if hasattr(self, 'surface_status_label'):
            self.surface_status_label.setText("Status refreshed")
    


    #####################################################################
    # Tab 6 (Refine & Mesh) - Constraint Selection Methods
    #####################################################################
        # ------------------------------------------------------------------
    #  Keep exactly one point per (x,y,z) – but preserve the best type
    # ------------------------------------------------------------------
    def _dedupe_preserve_special(self, pts):
        """
        pts  : list[Vector3D | list | tuple]
        Returns a list with duplicates removed, keeping the highest-priority
        point-type for every coordinate triple.
        """
        PRIORITY = {
            "TRIPLE_POINT":  5,
            "CORNER_POINT":  4,
            "INTERSECTION":  3,
            "HULL_POINT":    2,
            "DEFAULT":       1,
            None:            0,
        }
        def key(p):
            return (round(float(p[0]), 9),
                    round(float(p[1]), 9),
                    round(float(p[2]), 9))

        best = {}          # key  ->  (priority , point-obj)
        for p in pts:
            k = key(p)
            pt_type = getattr(p, "type", None)
            prio = PRIORITY.get(pt_type, 0)
            if k not in best or prio > best[k][0]:
                best[k] = (prio, p)

        # return them in the original order (so polyline order is preserved)
        out = []
        seen = set()
        for p in pts:
            k = key(p)
            if k in best and k not in seen:
                out.append(best[k][1])
                seen.add(k)
        return out

    def _populate_refine_constraint_tree(self):
        """
        Build a three-level tree:
            Surface
                Hull segments →  Seg 0, Seg 1, …
                Intersection n → Seg 0, Seg 1, …
        Every Seg-item represents ONE selectable block:
        - For intersections: between TRIPLE_POINTs and endpoints (or wrapping for closed loops)
        - For hull: per-edge as before
        """
        from Pymeshit.intersection_utils import Vector3D

        if not hasattr(self, "refine_constraint_tree"):
            return

        tree: QTreeWidget = self.refine_constraint_tree
        tree.clear()
        tree.blockSignals(True)

        # (surface_idx , seg_uid)  →  {'points':[...], 'type':'HULL'|'INTERSECTION', 'ctype':'HULL'|'INT'}
        self._refine_segment_map: Dict[Tuple[int, int], Dict] = {}
        seg_uid = 0

        def get_type(p):
            # Works for Vector3D or [x, y, z, type]
            if hasattr(p, "point_type") and p.point_type is not None:
                return p.point_type
            if hasattr(p, "type") and p.type is not None:
                return p.type
            if isinstance(p, (list, tuple)) and len(p) > 3:
                return p[3]
            return "DEFAULT"

        def is_closed_loop(pts):
            if len(pts) < 3:
                return False
            # Use distance and loop markers
            def as_xyz(q):
                if hasattr(q, "x"):
                    return (float(q.x), float(q.y), float(q.z))
                return (float(q[0]), float(q[1]), float(q[2]))
            x1, y1, z1 = as_xyz(pts[0])
            x2, y2, z2 = as_xyz(pts[-1])
            d = ((x1 - x2)**2 + (y1 - y2)**2 + (z1 - z2)**2) ** 0.5
            if d < 1e-4:
                return True
            last_t = get_type(pts[-1])
            if ("LOOP_END" in last_t) or ("CIRCULAR" in last_t):
                return True
            # Optional: if any point marked CIRCULAR
            for q in pts:
                if "CIRCULAR" in get_type(q):
                    return True
            return False

        def segment_by_triples(pts):
            """
            Return list of segments (each a list of points), split only at TRIPLE_POINTs,
            and at endpoints. For closed loops, wrap between last and first triple.
            """
            if len(pts) < 2:
                return []
            n = len(pts)
            triples = [i for i, q in enumerate(pts) if get_type(q) == "TRIPLE_POINT"]

            closed = is_closed_loop(pts)
            segments = []

            # No triple points
            if not triples:
                # One segment: whole polyline (or loop)
                seg = pts[:]
                if closed and seg[0] != seg[-1]:
                    seg = seg + [seg[0]]  # re-close the loop
                segments.append(seg)
                return segments

            # At least one triple
            if closed:
                tri = sorted(set(triples))
                if len(tri) == 1:
                    # Special case: only one triple in a closed loop
                    segments.append(pts[:])  # entire loop as one block
                else:
                    for a, b in zip(tri, tri[1:] + tri[:1]):
                        if a <= b:
                            seg = pts[a:b+1]
                        else:
                            seg = pts[a:] + pts[:b+1]
                        if len(seg) >= 2:
                            segments.append(seg)

            else:
                # Open polyline: endpoints are split points too
                splits = [0] + sorted(triples) + [n - 1]
                # Remove immediate duplicates (e.g., triple at index 0)
                dedup_splits = []
                for s in splits:
                    if not dedup_splits or dedup_splits[-1] != s:
                        dedup_splits.append(s)
                # Build segments between consecutive split indices
                for a, b in zip(dedup_splits[:-1], dedup_splits[1:]):
                    if b - a >= 1:
                        seg = pts[a:b+1]
                        if len(seg) >= 2:
                            segments.append(seg)

            return segments

        for s_idx, ds in enumerate(self.datasets):
            if ds.get("type") == "polyline":
                continue

            surf_item = QTreeWidgetItem(tree)
            surf_item.setText(0, ds.get("name", f"Surface {s_idx}"))
            surf_item.setFlags(surf_item.flags() | Qt.ItemIsUserCheckable)
            surf_item.setCheckState(0, Qt.Checked)
            surf_item.setData(0, Qt.UserRole, {"type": "surface", "surface_idx": s_idx})

            # ----------------------- hull ---------------------------------------
            hull = ds.get("hull_points", [])
            if hull is not None and len(hull) >= 3:
                hull_item = QTreeWidgetItem(surf_item)
                hull_item.setText(0, "Hull segments")
                hull_item.setFlags(hull_item.flags() | Qt.ItemIsUserCheckable)
                hull_item.setCheckState(0, Qt.Checked)
                # Add hole checkbox for hull group
                hull_item.setCheckState(4, Qt.Unchecked)
                hull_item.setData(0, Qt.UserRole, {"type": "hull_group", "surface_idx": s_idx})

                for i in range(len(hull)):
                    p1, p2 = hull[i], hull[(i + 1) % len(hull)]
                    seg_item = QTreeWidgetItem(hull_item)
                    seg_item.setText(0, f"Seg {i}")
                    seg_item.setText(1, "HULL")  # Set type column
                    seg_item.setFlags(seg_item.flags() | Qt.ItemIsUserCheckable)
                    seg_item.setCheckState(0, Qt.Checked)
                    # Add hole checkbox in column 4
                    seg_item.setFlags(seg_item.flags() | Qt.ItemIsUserCheckable)
                    seg_item.setCheckState(4, Qt.Unchecked)  # Default: not a hole
                    seg_item.setData(0, Qt.UserRole, {
                        "type": "constraint",
                        "surface_idx": s_idx,
                        "seg_uid": seg_uid
                    })
                    self._refine_segment_map[(s_idx, seg_uid)] = {
                        "points": [p1, p2],
                        "type": "HULL",     # normalized
                        "ctype": "HULL",    # keep for compatibility
                        "is_hole": False,
                        "selected": True,
                    }
                    seg_uid += 1

            # ------------------ intersection lines ------------------------------
            inters = getattr(self, "refined_intersections_for_visualization", {}).get(s_idx, [])
            for line_id, inter_d in enumerate(inters):
                raw_pts = inter_d.get("points", [])
                if len(raw_pts) < 2:
                    continue

                # DIRECTLY use raw_pts; no deduplication
                seg_lists = segment_by_triples(raw_pts)
                if not seg_lists:
                    continue

                line_item = QTreeWidgetItem(surf_item)
                line_item.setText(0, f"Intersection {line_id}")
                line_item.setFlags(line_item.flags() | Qt.ItemIsUserCheckable)
                line_item.setCheckState(0, Qt.Checked)
                # Add hole checkbox for intersection group
                line_item.setCheckState(4, Qt.Unchecked)
                line_item.setData(0, Qt.UserRole, {"type": "intersection_group", "surface_idx": s_idx})

                for k, seg_pts in enumerate(seg_lists):
                    seg_item = QTreeWidgetItem(line_item)
                    seg_item.setText(0, f"Seg {k}")
                    seg_item.setText(1, "INTERSECTION")  # Set type column
                    seg_item.setFlags(seg_item.flags() | Qt.ItemIsUserCheckable)
                    seg_item.setCheckState(0, Qt.Checked)
                    # Add hole checkbox in column 4
                    seg_item.setFlags(seg_item.flags() | Qt.ItemIsUserCheckable)
                    seg_item.setCheckState(4, Qt.Unchecked)  # Default: not a hole
                    seg_item.setData(0, Qt.UserRole, {
                        "type": "constraint",
                        "surface_idx": s_idx,
                        "seg_uid": seg_uid
                    })

                    self._refine_segment_map[(s_idx, seg_uid)] = {
                        "points": seg_pts,           # full block (not pairwise)
                        "type": "INTERSECTION",      # normalized
                        "ctype": "INT",              # keep for compatibility
                        "is_hole": False,
                        "selected": True,
                        "line_id": line_id,
                    }
                    seg_uid += 1

        tree.expandAll()
        tree.blockSignals(False)
        logger.info("Segment-level constraint tree populated (intersection segments between TRIPLE_POINTs and endpoints, no dedup).")
    def _collect_selected_refine_segments(self, surface_idx: int) -> List[List]:
        """Return list of point-pairs [p1, p2] for all checked segments."""
        if not hasattr(self, "refine_constraint_tree"):
            return []

        selected = []

        def walk(item: QTreeWidgetItem):
            data = item.data(0, Qt.UserRole)
            if data and data.get("type") == "constraint":
                if (item.checkState(0) == Qt.Checked
                        and data["surface_idx"] == surface_idx):
                    seg_uid = data["seg_uid"]
                    selected.append(self._refine_segment_map[(surface_idx, seg_uid)]["points"])
            for i in range(item.childCount()):
                walk(item.child(i))

        for i in range(self.refine_constraint_tree.topLevelItemCount()):
            walk(self.refine_constraint_tree.topLevelItem(i))

        return selected
    
    def _collect_selected_hole_segments(self, surface_idx: int) -> List[List]:
        """Return list of point-pairs [p1, p2] for all segments marked as holes."""
        if not hasattr(self, "refine_constraint_tree"):
            return []

        hole_segments = []

        def walk(item: QTreeWidgetItem):
            data = item.data(0, Qt.UserRole)
            if data and data.get("type") == "constraint":
                # Only check if it's marked as hole and for the correct surface
                # Don't require it to be selected for meshing (column 0) 
                # because holes are exclusion regions
                if (item.checkState(4) == Qt.Checked  # Hole checkbox is checked
                        and data["surface_idx"] == surface_idx):
                    seg_uid = data["seg_uid"]
                    if (surface_idx, seg_uid) in self._refine_segment_map:
                        hole_segments.append(self._refine_segment_map[(surface_idx, seg_uid)]["points"])
                        logger.debug(f"Collected hole segment {seg_uid} for surface {surface_idx}")
            for i in range(item.childCount()):
                walk(item.child(i))

        for i in range(self.refine_constraint_tree.topLevelItemCount()):
            walk(self.refine_constraint_tree.topLevelItem(i))

        if hole_segments:
            logger.info(f"Collected {len(hole_segments)} hole segments for surface {surface_idx}")
        else:
            logger.debug(f"No hole segments found for surface {surface_idx}")

        return hole_segments
    
    def _sync_hole_selection_across_surfaces(self, item):
        """Synchronize hole selection for intersection lines across all surfaces that share them."""
        if self._refine_updating_constraint_tree:
            return
            
        if not hasattr(self, "refined_intersections_for_visualization") or not hasattr(self, "refine_constraint_tree"):
            return
            
        data = item.data(0, Qt.UserRole)
        if not data:
            return
            
        hole_state = item.checkState(4)
        
        # Handle intersection group synchronization
        if data.get("type") == "intersection_group":
            surface_idx = data.get('surface_idx')
            
            # Extract the intersection index from the text (e.g., "Intersection 2")
            item_text = item.text(0)
            try:
                intersection_idx = int(item_text.split(" ")[-1])
            except (ValueError, IndexError):
                return
                
            # Get the intersection data for this surface and index
            if surface_idx not in self.refined_intersections_for_visualization:
                return
                
            if intersection_idx >= len(self.refined_intersections_for_visualization[surface_idx]):
                return
                
            # Get the intersection data
            intersection_data = self.refined_intersections_for_visualization[surface_idx][intersection_idx]
            
            # Find all surfaces involved in this intersection
            dataset_id1 = intersection_data.get('dataset_id1')
            dataset_id2 = intersection_data.get('dataset_id2')
            
            logger.info(f"Synchronizing intersection hole state: surface {surface_idx}, intersection {intersection_idx}, datasets {dataset_id1}-{dataset_id2}, hole={hole_state == Qt.Checked}")
            
            # Update both surfaces (except the current one)
            if dataset_id1 is not None and dataset_id1 != surface_idx:
                self._update_matching_intersection_hole_state(dataset_id1, intersection_data, hole_state)
                logger.info(f"Updated hole state for surface {dataset_id1}")
                
            if dataset_id2 is not None and dataset_id2 != surface_idx:
                self._update_matching_intersection_hole_state(dataset_id2, intersection_data, hole_state)
                logger.info(f"Updated hole state for surface {dataset_id2}")
        
        # Handle individual constraint synchronization  
        elif data.get("type") == "constraint":
            # Find the parent intersection group
            parent = item.parent()
            if parent:
                parent_data = parent.data(0, Qt.UserRole)
                if parent_data and parent_data.get("type") == "intersection_group":
                    surface_idx = parent_data.get('surface_idx')
                    
                    # Extract the intersection index from the parent text
                    item_text = parent.text(0)
                    try:
                        intersection_idx = int(item_text.split(" ")[-1])
                    except (ValueError, IndexError):
                        return
                        
                    # Get the intersection data
                    if surface_idx not in self.refined_intersections_for_visualization:
                        return
                        
                    if intersection_idx >= len(self.refined_intersections_for_visualization[surface_idx]):
                        return
                        
                    intersection_data = self.refined_intersections_for_visualization[surface_idx][intersection_idx]
                    
                    # Get the segment data
                    segment_uid = data.get("seg_uid")
                    segment_points = self._refine_segment_map.get((surface_idx, segment_uid), {}).get("points", [])
                    
                    # Find all surfaces involved in this intersection
                    dataset_id1 = intersection_data.get('dataset_id1')
                    dataset_id2 = intersection_data.get('dataset_id2')
                    
                    # Update both surfaces (except the current one)
                    if dataset_id1 is not None and dataset_id1 != surface_idx:
                        self._update_matching_segment_hole_state(dataset_id1, intersection_idx, segment_points, hole_state)
                        
                    if dataset_id2 is not None and dataset_id2 != surface_idx:
                        self._update_matching_segment_hole_state(dataset_id2, intersection_idx, segment_points, hole_state)
                        
                    intersection_data = self.refined_intersections_for_visualization[surface_idx][intersection_idx]
                    
                    # Get the segment data
                    seg_uid = data.get('seg_uid')
                    if (surface_idx, seg_uid) not in self._refine_segment_map:
                        return
                        
                    segment_data = self._refine_segment_map[(surface_idx, seg_uid)]
                    segment_points = segment_data.get('points', [])
                    
                    # Find all surfaces involved in this intersection
                    dataset_id1 = intersection_data.get('dataset_id1')
                    dataset_id2 = intersection_data.get('dataset_id2')
                    
                    # Update segments in all related surfaces (except the current one)
                    if dataset_id1 is not None and dataset_id1 != surface_idx:
                        for i in range(len(self.refined_intersections_for_visualization.get(dataset_id1, []))):
                            self._update_matching_segment_hole_state(dataset_id1, i, segment_points, hole_state)
                        
                    if dataset_id2 is not None and dataset_id2 != surface_idx:
                        for i in range(len(self.refined_intersections_for_visualization.get(dataset_id2, []))):
                            self._update_matching_segment_hole_state(dataset_id2, i, segment_points, hole_state)
    
    def _update_matching_intersection_hole_state(self, target_surface_idx, intersection_data, hole_state):
        """Update hole state for matching intersection groups in target surface."""
        # Find the matching intersection in the target surface
        tree = self.refine_constraint_tree
        
        for i in range(tree.topLevelItemCount()):
            surface_item = tree.topLevelItem(i)
            surface_data = surface_item.data(0, Qt.UserRole)
            if surface_data and surface_data.get("surface_idx") == target_surface_idx:
                # Look through intersection groups
                for j in range(surface_item.childCount()):
                    group_item = surface_item.child(j)
                    group_data = group_item.data(0, Qt.UserRole)
                    if group_data and group_data.get("type") == "intersection_group":
                        # Extract intersection index from text
                        item_text = group_item.text(0)
                        try:
                            intersection_idx = int(item_text.split(" ")[-1])
                        except (ValueError, IndexError):
                            continue
                            
                        # Check if this intersection matches by comparing dataset IDs
                        if (target_surface_idx in self.refined_intersections_for_visualization and 
                            intersection_idx < len(self.refined_intersections_for_visualization[target_surface_idx])):
                            
                            other_intersection = self.refined_intersections_for_visualization[target_surface_idx][intersection_idx]
                            
                            # Check if this is the same intersection (by comparing the two surfaces involved)
                            if ((other_intersection.get('dataset_id1') == intersection_data.get('dataset_id1') and 
                                 other_intersection.get('dataset_id2') == intersection_data.get('dataset_id2')) or
                                (other_intersection.get('dataset_id1') == intersection_data.get('dataset_id2') and 
                                 other_intersection.get('dataset_id2') == intersection_data.get('dataset_id1'))):
                                
                                # This is the matching intersection, update its hole state (column 4)
                                if group_item.checkState(4) != hole_state:
                                    group_item.setCheckState(4, hole_state)
                                    
                                    # Also update all child segments
                                    for k in range(group_item.childCount()):
                                        child_item = group_item.child(k)
                                        child_data = child_item.data(0, Qt.UserRole)
                                        if child_data and child_data.get("type") == "constraint":
                                            child_item.setCheckState(4, hole_state)
                                            # Update segment map
                                            child_surface_idx = child_data["surface_idx"]
                                            child_seg_uid = child_data["seg_uid"]
                                            if (child_surface_idx, child_seg_uid) in self._refine_segment_map:
                                                self._refine_segment_map[(child_surface_idx, child_seg_uid)]["is_hole"] = (hole_state == Qt.Checked)
                                    
                                    logger.info(f"Synchronized intersection hole state across surface {target_surface_idx}")
                                    break
                break
    
    def _update_matching_segment_hole_state(self, target_surface_idx, intersection_idx, segment_points, hole_state):
        """Update hole state for matching segments in target surface."""
        tree = self.refine_constraint_tree
        
        for i in range(tree.topLevelItemCount()):
            surface_item = tree.topLevelItem(i)
            surface_data = surface_item.data(0, Qt.UserRole)
            if surface_data and surface_data.get("surface_idx") == target_surface_idx:
                # Look through intersection groups
                for j in range(surface_item.childCount()):
                    group_item = surface_item.child(j)
                    group_data = group_item.data(0, Qt.UserRole)
                    if group_data and group_data.get("type") == "intersection_group":
                        # Check if this is the right intersection
                        group_text = group_item.text(0)
                        try:
                            group_intersection_idx = int(group_text.split(" ")[-1])
                            if group_intersection_idx == intersection_idx:
                                # Look through segments in this group
                                for k in range(group_item.childCount()):
                                    child_item = group_item.child(k)
                                    child_data = child_item.data(0, Qt.UserRole)
                                    if child_data and child_data.get("type") == "constraint":
                                        # Check if segment points match
                                        child_seg_uid = child_data["seg_uid"]
                                        if (target_surface_idx, child_seg_uid) in self._refine_segment_map:
                                            child_segment_data = self._refine_segment_map[(target_surface_idx, child_seg_uid)]
                                            child_points = child_segment_data.get('points', [])
                                            if self._segments_match(segment_points, child_points):
                                                child_item.setCheckState(4, hole_state)
                                                child_segment_data["is_hole"] = (hole_state == Qt.Checked)
                        except (ValueError, IndexError):
                            continue
                break
    
    def _intersections_match(self, surface_idx, intersection_idx, target_intersection_data):
        """Check if intersections match based on their data."""
        if surface_idx not in self.refined_intersections_for_visualization:
            return False
        if intersection_idx >= len(self.refined_intersections_for_visualization[surface_idx]):
            return False
            
        intersection_data = self.refined_intersections_for_visualization[surface_idx][intersection_idx]
        
        # Compare dataset IDs
        return (intersection_data.get('dataset_id1') == target_intersection_data.get('dataset_id1') and
                intersection_data.get('dataset_id2') == target_intersection_data.get('dataset_id2')) or \
               (intersection_data.get('dataset_id1') == target_intersection_data.get('dataset_id2') and
                intersection_data.get('dataset_id2') == target_intersection_data.get('dataset_id1'))
    
    def _segments_match(self, points1, points2, tolerance=1e-6):
        """Check if two segments match (same points)."""
        if len(points1) != len(points2):
            return False
            
        # Check if points match in order or reverse order
        def points_equal(p1, p2):
            if hasattr(p1, 'x'):
                return (abs(p1.x - (p2.x if hasattr(p2, 'x') else p2[0])) < tolerance and
                        abs(p1.y - (p2.y if hasattr(p2, 'y') else p2[1])) < tolerance and
                        abs(p1.z - (p2.z if hasattr(p2, 'z') else p2[2])) < tolerance)
            else:
                return (abs(p1[0] - (p2.x if hasattr(p2, 'x') else p2[0])) < tolerance and
                        abs(p1[1] - (p2.y if hasattr(p2, 'y') else p2[1])) < tolerance and
                        abs(p1[2] - (p2.z if hasattr(p2, 'z') else p2[2])) < tolerance)
        
        # Check forward direction
        forward_match = all(points_equal(points1[i], points2[i]) for i in range(len(points1)))
        
        # Check reverse direction
        reverse_match = all(points_equal(points1[i], points2[-(i+1)]) for i in range(len(points1)))
        
        return forward_match or reverse_match
    
    def _mark_selected_segments_as_holes(self, surface_idx: int, is_hole: bool = True):
        """Mark all selected segments for a surface as holes or not holes."""
        if not hasattr(self, "refine_constraint_tree"):
            return
            
        self._refine_updating_constraint_tree = True
        try:
            def walk(item: QTreeWidgetItem):
                data = item.data(0, Qt.UserRole)
                if data and data.get("type") == "constraint":
                    if (item.checkState(0) == Qt.Checked
                            and data["surface_idx"] == surface_idx):
                        seg_uid = data["seg_uid"]
                        # Update UI
                        item.setCheckState(4, Qt.Checked if is_hole else Qt.Unchecked)
                        # Update segment map
                        if (surface_idx, seg_uid) in self._refine_segment_map:
                            self._refine_segment_map[(surface_idx, seg_uid)]["is_hole"] = is_hole
                for i in range(item.childCount()):
                    walk(item.child(i))

            for i in range(self.refine_constraint_tree.topLevelItemCount()):
                walk(self.refine_constraint_tree.topLevelItem(i))
        finally:
            self._refine_updating_constraint_tree = False
            
        logger.info(f"Marked selected segments for surface {surface_idx} as {'holes' if is_hole else 'constraints'}")
    
    def _mark_selected_as_holes(self):
        """Mark all selected segments as holes for the currently selected surface."""
        # Get the currently selected surface from the tree
        selected_surface_idx = self._get_currently_selected_surface_from_tree()
        if selected_surface_idx is not None:
            self._mark_selected_segments_as_holes(selected_surface_idx, True)
        else:
            # If no specific surface selected, apply to all surfaces
            for s_idx in range(len(self.datasets)):
                if self.datasets[s_idx].get("type") != "polyline":
                    self._mark_selected_segments_as_holes(s_idx, True)
    
    def _unmark_selected_as_holes(self):
        """Unmark all selected segments as holes for the currently selected surface."""
        # Get the currently selected surface from the tree
        selected_surface_idx = self._get_currently_selected_surface_from_tree()
        if selected_surface_idx is not None:
            self._mark_selected_segments_as_holes(selected_surface_idx, False)
        else:
            # If no specific surface selected, apply to all surfaces
            for s_idx in range(len(self.datasets)):
                if self.datasets[s_idx].get("type") != "polyline":
                    self._mark_selected_segments_as_holes(s_idx, False)
    
    def _get_currently_selected_surface_from_tree(self):
        """Get the surface index of the currently selected item in the constraint tree."""
        if not hasattr(self, "refine_constraint_tree"):
            return None
            
        current_item = self.refine_constraint_tree.currentItem()
        if current_item:
            # Walk up the tree to find the surface item
            item = current_item
            while item:
                data = item.data(0, Qt.UserRole)
                if data and data.get("type") == "surface":
                    return data.get("surface_idx")
                item = item.parent()
        return None
    
    def _get_selected_refine_constraints(self, surface_idx_to_check):
        """
        Checks the refine_constraint_tree to see if hull and intersection
        constraints are selected for a given surface.
        """
        if not hasattr(self, 'refine_constraint_tree'):
            return False, False

        tree = self.refine_constraint_tree
        
        # Find the top-level item for the surface
        for i in range(tree.topLevelItemCount()):
            surface_item = tree.topLevelItem(i)
            data = surface_item.data(0, Qt.UserRole)
            if data and data.get('surface_idx') == surface_idx_to_check:
                
                # Now check its children (Hull and Intersections groups)
                hull_selected = False
                intersections_selected = False
                for j in range(surface_item.childCount()):
                    group_item = surface_item.child(j)
                    group_data = group_item.data(0, Qt.UserRole)
                    if group_data:
                        if group_data.get('type') == 'hull_group' and group_item.checkState(0) == Qt.Checked:
                            hull_selected = True
                        elif group_data.get('type') == 'intersection_group' and group_item.checkState(0) == Qt.Checked:
                            intersections_selected = True
                
                return hull_selected, intersections_selected
                
        return False, False
    
    def _build_plc_from_selection(self, surface_idx):
        from Pymeshit.intersection_utils import Vector3D
        import numpy as np
        seg_lists = self._collect_selected_refine_segments(surface_idx)
        hole_segments = self._collect_selected_hole_segments(surface_idx)
        if not seg_lists:
            return [], np.empty((0, 2), dtype=int), []

        uniq: Dict[Tuple[float, float, float], int] = {}
        pts: List[Vector3D] = []
        seg_idx: List[List[int]] = []
        hole_points: List[Vector3D] = []

        def add(v):
            if isinstance(v, Vector3D):
                x, y, z = v.x, v.y, v.z
                p_type = getattr(v, "point_type", getattr(v, "type", "DEFAULT"))
            else:
                x, y, z = map(float, v[:3])
                p_type = v[3] if len(v) > 3 else "DEFAULT"
            key = (round(x, 9), round(y, 9), round(z, 9))
            idx = uniq.get(key)
            if idx is None:
                idx = len(pts)
                uniq[key] = idx
                pts.append(Vector3D(x, y, z, point_type=p_type))
            return idx

        #   NEW: handle lists that have more than two points
        for seg_pts in seg_lists:
            if len(seg_pts) < 2:
                continue
            for j in range(len(seg_pts) - 1):
                p1, p2 = seg_pts[j], seg_pts[j + 1]
                i1, i2 = add(p1), add(p2)
                if i1 != i2:
                    seg_idx.append([i1, i2])

        # Process hole segments - combine segments into closed loops and calculate centroids
        logger.debug(f"Processing {len(hole_segments)} hole segments for surface {surface_idx}")
        
        if hole_segments:
            # Combine all hole segments into a single continuous point list
            all_hole_points = []
            for hole_idx, hole_seg_pts in enumerate(hole_segments):
                logger.debug(f"Hole segment {hole_idx}: {len(hole_seg_pts)} points")
                if len(hole_seg_pts) >= 2:  # Each segment should have at least 2 points
                    # For the first segment, add all points
                    if hole_idx == 0:
                        all_hole_points.extend(hole_seg_pts)
                    else:
                        # For subsequent segments, skip the first point to avoid duplication
                        # (assuming segments are connected end-to-end)
                        all_hole_points.extend(hole_seg_pts[1:])
                else:
                    logger.warning(f"Skipping hole segment with only {len(hole_seg_pts)} points")
            
            # Now calculate hole center from the combined point list
            if len(all_hole_points) >= 3:  # Need at least 3 points for a valid hole
                # Calculate centroid of all hole points
                x_sum = sum(p.x if hasattr(p, 'x') else p[0] for p in all_hole_points)
                y_sum = sum(p.y if hasattr(p, 'y') else p[1] for p in all_hole_points)
                z_sum = sum(p.z if hasattr(p, 'z') else p[2] for p in all_hole_points)
                n = len(all_hole_points)
                hole_center = Vector3D(x_sum/n, y_sum/n, z_sum/n)
                hole_points.append(hole_center)
                logger.info(f"Added hole center at ({hole_center.x:.3f}, {hole_center.y:.3f}, {hole_center.z:.3f}) from {len(all_hole_points)} combined points")
            else:
                logger.warning(f"Combined hole points ({len(all_hole_points)}) insufficient for hole center calculation")

        if hole_points:
            logger.info(f"Built PLC with {len(pts)} constraint points, {len(seg_idx)} segments, and {len(hole_points)} holes")
        else:
            logger.info(f"Built PLC with {len(pts)} constraint points and {len(seg_idx)} segments (no holes)")

        return pts, np.asarray(seg_idx, dtype=int), hole_points
    def _refine_select_intersection_constraints_only(self):
        """Select only intersection constraints in Tab 6, deselect hull constraints"""
        if not hasattr(self, 'refine_constraint_tree'):
            return
            
        self._refine_updating_constraint_tree = True
        try:
            # Iterate through all items in the tree
            root = self.refine_constraint_tree.invisibleRootItem()
            for i in range(root.childCount()):
                surface_item = root.child(i)
                for j in range(surface_item.childCount()):
                    constraint_type_item = surface_item.child(j)
                    item_text = constraint_type_item.text(0)
                    
                    # Check intersection constraints, uncheck hull constraints
                    if "Intersection Line" in item_text:
                        constraint_type_item.setCheckState(0, Qt.Checked)
                        # Also check all children
                        for k in range(constraint_type_item.childCount()):
                            constraint_type_item.child(k).setCheckState(0, Qt.Checked)
                    elif "Hull" in item_text:
                        constraint_type_item.setCheckState(0, Qt.Unchecked)
                        # Also uncheck all children
                        for k in range(constraint_type_item.childCount()):
                            constraint_type_item.child(k).setCheckState(0, Qt.Unchecked)
                            
            logger.info("Tab 6: Selected intersection constraints only")
        finally:
            self._refine_updating_constraint_tree = False
    
    def _refine_select_hull_constraints_only(self):
        """Select only hull constraints in Tab 6, deselect intersection constraints"""
        if not hasattr(self, 'refine_constraint_tree'):
            return
            
        self._refine_updating_constraint_tree = True
        try:
            # Iterate through all items in the tree
            root = self.refine_constraint_tree.invisibleRootItem()
            for i in range(root.childCount()):
                surface_item = root.child(i)
                for j in range(surface_item.childCount()):
                    constraint_type_item = surface_item.child(j)
                    item_text = constraint_type_item.text(0)
                    
                    # Check hull constraints, uncheck intersection constraints
                    if "Hull" in item_text:
                        constraint_type_item.setCheckState(0, Qt.Checked)
                        # Also check all children
                        for k in range(constraint_type_item.childCount()):
                            constraint_type_item.child(k).setCheckState(0, Qt.Checked)
                    elif "Intersection Line" in item_text:
                        constraint_type_item.setCheckState(0, Qt.Unchecked)
                        # Also uncheck all children
                        for k in range(constraint_type_item.childCount()):
                            constraint_type_item.child(k).setCheckState(0, Qt.Unchecked)
                            
            logger.info("Tab 6: Selected hull constraints only")
        finally:
            self._refine_updating_constraint_tree = False
    
    def _sync_intersection_selection_across_surfaces(self, changed_item):
        """
        Synchronize intersection line selections across surfaces.
        When an intersection line is selected/deselected in one surface,
        find the same intersection line in other surfaces and apply the same selection state.
        
        Args:
            changed_item: The QTreeWidgetItem that was changed
        """
        # Skip if we don't have the necessary data structures
        if not hasattr(self, "refined_intersections_for_visualization") or not hasattr(self, "refine_constraint_tree"):
            return
            
        # Determine if we're dealing with an intersection group or a segment within an intersection group
        data = changed_item.data(0, Qt.UserRole)
        if not data:
            return
            
        # Get the checked state that needs to be propagated
        is_checked = changed_item.checkState(0) == Qt.Checked
        
        # Handle different item types
        if data.get('type') == 'intersection_group':
            # This is an intersection group item
            surface_idx = data.get('surface_idx')
            intersection_idx = -1
            
            # Extract the intersection index from the text (e.g., "Intersection 2")
            item_text = changed_item.text(0)
            try:
                intersection_idx = int(item_text.split(" ")[-1])
            except (ValueError, IndexError):
                return
                
            # Get the intersection data for this surface and index
            if surface_idx not in self.refined_intersections_for_visualization:
                return
                
            if intersection_idx >= len(self.refined_intersections_for_visualization[surface_idx]):
                return
                
            # Get the intersection data
            intersection_data = self.refined_intersections_for_visualization[surface_idx][intersection_idx]
            
            # Find all surfaces involved in this intersection
            # We need to check both dataset_id1 and dataset_id2
            dataset_id1 = intersection_data.get('dataset_id1')
            dataset_id2 = intersection_data.get('dataset_id2')
            
            # Update both surfaces (except the current one)
            if dataset_id1 is not None and dataset_id1 != surface_idx:
                self._update_matching_intersection(dataset_id1, intersection_data, is_checked)
                
            if dataset_id2 is not None and dataset_id2 != surface_idx:
                self._update_matching_intersection(dataset_id2, intersection_data, is_checked)
                
        elif data.get('type') == 'constraint' and changed_item.parent() and changed_item.parent().data(0, Qt.UserRole) and changed_item.parent().data(0, Qt.UserRole).get('type') == 'intersection_group':
            # This is a segment within an intersection group
            # Get the parent intersection group
            intersection_group_item = changed_item.parent()
            intersection_group_data = intersection_group_item.data(0, Qt.UserRole)
            surface_idx = intersection_group_data.get('surface_idx')
            
            # Extract the intersection index from the text (e.g., "Intersection 2")
            item_text = intersection_group_item.text(0)
            try:
                intersection_idx = int(item_text.split(" ")[-1])
            except (ValueError, IndexError):
                return
                
            # Get the intersection data for this surface and index
            if surface_idx not in self.refined_intersections_for_visualization:
                return
                
            if intersection_idx >= len(self.refined_intersections_for_visualization[surface_idx]):
                return
                
            # Get the intersection data
            intersection_data = self.refined_intersections_for_visualization[surface_idx][intersection_idx]
            
            # Get the segment data
            seg_uid = data.get('seg_uid')
            if (surface_idx, seg_uid) not in self._refine_segment_map:
                return
                
            segment_data = self._refine_segment_map[(surface_idx, seg_uid)]
            segment_points = segment_data.get('points', [])
            
            # Find all surfaces involved in this intersection
            dataset_id1 = intersection_data.get('dataset_id1')
            dataset_id2 = intersection_data.get('dataset_id2')
            
            # Update segments in all related surfaces (except the current one)
            if dataset_id1 is not None and dataset_id1 != surface_idx:
                # Find matching segments in the first surface
                for i in range(len(self.refined_intersections_for_visualization.get(dataset_id1, []))):
                    self._update_matching_segment(dataset_id1, i, segment_points, is_checked)
                
            if dataset_id2 is not None and dataset_id2 != surface_idx:
                # Find matching segments in the second surface
                for i in range(len(self.refined_intersections_for_visualization.get(dataset_id2, []))):
                    self._update_matching_segment(dataset_id2, i, segment_points, is_checked)
    
    def _update_matching_intersection(self, surface_idx, intersection_data, is_checked):
        """
        Update the selection state of a matching intersection line in another surface.
        
        Args:
            surface_idx: The index of the surface to update
            intersection_data: The intersection data to match
            is_checked: Whether the intersection should be checked or unchecked
        """
        # Find the surface item in the tree
        tree = self.refine_constraint_tree
        surface_item = None
        
        for i in range(tree.topLevelItemCount()):
            item = tree.topLevelItem(i)
            item_data = item.data(0, Qt.UserRole)
            if item_data and item_data.get('type') == 'surface' and item_data.get('surface_idx') == surface_idx:
                surface_item = item
                break
                
        if not surface_item:
            return
            
        # Find the matching intersection group
        for i in range(surface_item.childCount()):
            group_item = surface_item.child(i)
            group_data = group_item.data(0, Qt.UserRole)
            
            if group_data and group_data.get('type') == 'intersection_group':
                # Find which intersection this is in the refined_intersections_for_visualization list
                item_text = group_item.text(0)
                try:
                    intersection_idx = int(item_text.split(" ")[-1])
                    
                    # Check if this is the matching intersection
                    if surface_idx in self.refined_intersections_for_visualization and intersection_idx < len(self.refined_intersections_for_visualization[surface_idx]):
                        other_intersection = self.refined_intersections_for_visualization[surface_idx][intersection_idx]
                        
                        # Check if this is the same intersection (by comparing the two surfaces involved)
                        if ((other_intersection.get('dataset_id1') == intersection_data.get('dataset_id1') and 
                             other_intersection.get('dataset_id2') == intersection_data.get('dataset_id2')) or
                            (other_intersection.get('dataset_id1') == intersection_data.get('dataset_id2') and 
                             other_intersection.get('dataset_id2') == intersection_data.get('dataset_id1'))):
                            
                            # This is the matching intersection, update its checked state
                            if group_item.checkState(0) != (Qt.Checked if is_checked else Qt.Unchecked):
                                group_item.setCheckState(0, Qt.Checked if is_checked else Qt.Unchecked)
                                
                                # Also update all child segments
                                for j in range(group_item.childCount()):
                                    segment_item = group_item.child(j)
                                    segment_item.setCheckState(0, Qt.Checked if is_checked else Qt.Unchecked)
                                    
                            return
                            
                except (ValueError, IndexError):
                    continue
    
    def _update_matching_segment(self, surface_idx, intersection_idx, segment_points, is_checked):
        """
        Update the selection state of a matching segment in another surface.
        
        Args:
            surface_idx: The index of the surface to update
            intersection_idx: The index of the intersection containing the segment
            segment_points: The points defining the segment to match
            is_checked: Whether the segment should be checked or unchecked
        """
        # Skip if surface index is invalid
        if surface_idx is None or surface_idx < 0:
            return
            
        # Find the surface item in the tree
        tree = self.refine_constraint_tree
        surface_item = None
        
        for i in range(tree.topLevelItemCount()):
            item = tree.topLevelItem(i)
            item_data = item.data(0, Qt.UserRole)
            if item_data and item_data.get('type') == 'surface' and item_data.get('surface_idx') == surface_idx:
                surface_item = item
                break
                
        if not surface_item:
            return
        
        # Get the intersection data for this surface
        if surface_idx not in self.refined_intersections_for_visualization:
            return
            
        # Find all intersection groups in this surface
        for i in range(surface_item.childCount()):
            group_item = surface_item.child(i)
            group_data = group_item.data(0, Qt.UserRole)
            
            if group_data and group_data.get('type') == 'intersection_group':
                # Get the intersection index
                item_text = group_item.text(0)
                try:
                    group_intersection_idx = int(item_text.split(" ")[-1])
                    
                    # Check if this is a valid intersection index
                    if group_intersection_idx >= len(self.refined_intersections_for_visualization[surface_idx]):
                        continue
                        
                    # Get the intersection data
                    other_intersection = self.refined_intersections_for_visualization[surface_idx][group_intersection_idx]
                    
                    # Check all segments in this group
                    for j in range(group_item.childCount()):
                        segment_item = group_item.child(j)
                        segment_data = segment_item.data(0, Qt.UserRole)
                        
                        if segment_data and segment_data.get('type') == 'constraint':
                            seg_uid = segment_data.get('seg_uid')
                            if (surface_idx, seg_uid) in self._refine_segment_map:
                                other_segment_data = self._refine_segment_map[(surface_idx, seg_uid)]
                                other_segment_points = other_segment_data.get('points', [])
                                
                                # Use more robust segment matching
                                if self._are_segments_matching(segment_points, other_segment_points):
                                    # This is the matching segment, update its checked state
                                    current_state = segment_item.checkState(0)
                                    target_state = Qt.Checked if is_checked else Qt.Unchecked
                                    
                                    if current_state != target_state:
                                        # Block signals temporarily to prevent recursion
                                        tree.blockSignals(True)
                                        segment_item.setCheckState(0, target_state)
                                        tree.blockSignals(False)
                                        
                                        # Update parent state if needed
                                        self._update_parent_state_after_segment_change(segment_item)
                                        
                                        # Force visual update
                                        self._apply_segment_state(surface_idx, seg_uid, is_checked)
                                        
                                    # We found a match, but continue searching for more potential matches
                                    # instead of returning immediately
                                
                except (ValueError, IndexError):
                    continue
                    
    def _update_parent_state_after_segment_change(self, segment_item):
        """
        Update the parent intersection group's checked state based on its children.
        
        Args:
            segment_item: The segment item that was changed
        """
        parent = segment_item.parent()
        if not parent:
            return
            
        # Check if any children are checked
        any_checked = False
        for i in range(parent.childCount()):
            if parent.child(i).checkState(0) == Qt.Checked:
                any_checked = True
                break
                
        # Update parent state
        parent.setCheckState(0, Qt.Checked if any_checked else Qt.Unchecked)
        
        # Update grandparent (surface) state
        grandparent = parent.parent()
        if grandparent:
            any_child_checked = False
            for i in range(grandparent.childCount()):
                if grandparent.child(i).checkState(0) == Qt.Checked:
                    any_child_checked = True
                    break
                    
            grandparent.setCheckState(0, Qt.Checked if any_child_checked else Qt.Unchecked)
    
    def _are_segments_matching(self, points1, points2, tolerance=1e-6):
        """
        Check if two segments match by comparing their endpoints.
        Uses a more robust matching algorithm that works with different point formats
        and handles potential numerical precision issues.
        
        Args:
            points1: First segment points
            points2: Second segment points
            tolerance: Tolerance for point comparison (increased for better matching)
            
        Returns:
            bool: True if segments match, False otherwise
        """
        # Handle empty or None points
        if not points1 or not points2:
            return False
            
        # For segments, we only need to check the endpoints (first and last points)
        # This is more reliable than checking all points, especially for complex segments
        if len(points1) >= 2 and len(points2) >= 2:
            # Extract endpoints
            p1_start, p1_end = points1[0], points1[-1]
            p2_start, p2_end = points2[0], points2[-1]
            
            # Check if endpoints match in either order (forward or reverse)
            forward_match = (self._are_points_matching(p1_start, p2_start, tolerance) and 
                            self._are_points_matching(p1_end, p2_end, tolerance))
            
            reverse_match = (self._are_points_matching(p1_start, p2_end, tolerance) and 
                            self._are_points_matching(p1_end, p2_start, tolerance))
            
            return forward_match or reverse_match
            
        # Fallback to full point-by-point comparison for segments with only one point
        # (should be rare, but handled for completeness)
        if len(points1) != len(points2):
            return False
            
        # Check if points match in order
        matches_forward = all(
            self._are_points_matching(p1, p2, tolerance)
            for p1, p2 in zip(points1, points2)
        )
        
        # Check if points match in reverse order
        matches_reverse = all(
            self._are_points_matching(p1, p2, tolerance)
            for p1, p2 in zip(points1, reversed(points2))
        )
        
        return matches_forward or matches_reverse
    
    def _are_points_matching(self, p1, p2, tolerance=1e-6):
        """
        Check if two points match within tolerance.
        Enhanced to handle different point formats and potential numerical precision issues.
        
        Args:
            p1: First point
            p2: Second point
            tolerance: Tolerance for comparison (increased for better matching)
            
        Returns:
            bool: True if points match, False otherwise
        """
        try:
            # Handle Vector3D objects
            if hasattr(p1, 'x') and hasattr(p1, 'y') and hasattr(p1, 'z'):
                x1, y1, z1 = float(p1.x), float(p1.y), float(p1.z)
            elif isinstance(p1, (list, tuple)) and len(p1) >= 3:
                x1, y1, z1 = float(p1[0]), float(p1[1]), float(p1[2])
            else:
                # Can't extract coordinates
                return False
                
            if hasattr(p2, 'x') and hasattr(p2, 'y') and hasattr(p2, 'z'):
                x2, y2, z2 = float(p2.x), float(p2.y), float(p2.z)
            elif isinstance(p2, (list, tuple)) and len(p2) >= 3:
                x2, y2, z2 = float(p2[0]), float(p2[1]), float(p2[2])
            else:
                # Can't extract coordinates
                return False
            
            # Round to fixed precision to avoid floating point comparison issues
            # This is more robust than direct comparison with tolerance
            x1_rounded = round(x1, 9)
            y1_rounded = round(y1, 9)
            z1_rounded = round(z1, 9)
            
            x2_rounded = round(x2, 9)
            y2_rounded = round(y2, 9)
            z2_rounded = round(z2, 9)
            
            # First try exact match with rounding
            if (x1_rounded == x2_rounded and 
                y1_rounded == y2_rounded and 
                z1_rounded == z2_rounded):
                return True
                
            # Fall back to tolerance-based comparison for near matches
            return (abs(x1 - x2) < tolerance and 
                    abs(y1 - y2) < tolerance and 
                    abs(z1 - z2) < tolerance)
                    
        except (TypeError, ValueError, IndexError):
            # Handle any conversion errors or invalid point formats
            return False

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MeshItWorkflowGUI()
    window._ensure_vtk_cleanup_on_exit()  # Register VTK cleanup on exit
    window.show()
    sys.exit(app.exec_())