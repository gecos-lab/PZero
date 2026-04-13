"""view_interpretation.py
PZero© Andrea Bistacchi"""

# PySide6 imports
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QComboBox, QSlider, QSpinBox, QVBoxLayout, QCheckBox,
    QDialog, QDockWidget, QDoubleSpinBox, QRadioButton, QButtonGroup, QGroupBox, 
    QGridLayout, QFormLayout, QPushButton, QMessageBox
)
from PySide6.QtCore import Qt, QTimer

# VTK/PyVista imports
import pyvista as pv
import numpy as np
from copy import deepcopy
import heapq
from shapely.geometry import LineString as shp_linestring
from scipy import ndimage
from scipy.optimize import linear_sum_assignment
from pandas import DataFrame as pd_DataFrame
from pandas import concat as pd_concat
from shiboken6 import isValid as shiboken_is_valid

# VTK imports
from vtk import (
    vtkCellArray, vtkIntArray, vtkPoints, vtkStringArray, vtkIdList, vtkPolyData
)

# PZero imports
from .view_map import ViewMap
from ..entities_factory import Seismics, PolyLine
from ..helpers.helper_dialogs import (
    message_dialog,
    multiple_input_dialog,
    input_one_value_dialog,
    options_dialog,
    progress_dialog,
)
from ..helpers.helper_widgets import Editor, Tracer
from ..helpers.helper_functions import freeze_gui_off, freeze_gui_on

class ViewInterpretation(ViewMap):
    def add_all_entities(self):
        """
        Override BaseView bootstrap so slice-aware multipart geology is not added as a
        raw full actor before interpretation-specific filtering is ready.
        """


        for collection_name in self.tree_collection_dict.values():
            try:
                collection = getattr(self.parent, collection_name)
                uid_list = collection.df.query(self.view_filter)["uid"].tolist()
                prgs_bar = progress_dialog(
                    max_value=len(uid_list),
                    title_txt="Opening view",
                    label_txt=f"Adding objects from {collection_name}...",
                    cancel_txt=None,
                    parent=self,
                )
                for uid in uid_list:
                    skip_raw_actor = False
                    if collection_name == "geol_coll":
                        try:
                            vtk_obj = collection.get_uid_vtk_obj(uid)
                            cell_data = vtk_obj.GetCellData() if vtk_obj is not None else None
                            field_data = vtk_obj.GetFieldData() if vtk_obj is not None else None
                            skip_raw_actor = bool(
                                (cell_data is not None and cell_data.HasArray("slice_index"))
                                or (
                                    field_data is not None
                                    and field_data.HasArray("single_slice_index")
                                    and field_data.HasArray("single_slice_axis")
                                )
                            )
                        except Exception:
                            skip_raw_actor = False

                    if skip_raw_actor:
                        this_actor = None
                    else:
                        this_actor = self.show_actor_with_property(
                            uid=uid,
                            coll_name=collection_name,
                            show_property=None,
                            visible=True,
                        )

                    self.actors_df = pd_concat(
                        [
                            self.actors_df,
                            pd_DataFrame(
                                [
                                    {
                                        "uid": uid,
                                        "actor": this_actor,
                                        "show": True,
                                        "collection": collection_name,
                                        "show_property": None,
                                    }
                                ]
                            ),
                        ],
                        ignore_index=True,
                    )
                    prgs_bar.add_one()
            except Exception:
                self.print_terminal(f"ERROR in add_all_entities: {collection_name}")
                pass

    def __init__(self, *args, **kwargs):
        super(ViewInterpretation, self).__init__(*args, **kwargs)
        self.setWindowTitle("Interpretation Window")

        # Current state
        self.current_seismic_uid = None
        self.current_axis = 'Inline' # Inline, Crossline, Z-slice
        self.current_slice_index = 0
        self.slice_actor = None

        # Store current slice position for snapping drawn lines
        self.current_slice_position = 0.0

        # Store current slice bounds for picking plane
        self.current_slice_bounds = None

        # Scalar range for consistent colormapping
        self.scalar_range = None

        # Camera initialization flag - reset on axis/volume change
        self._camera_initialized = False

        # Track UIDs that should NOT be displayed as full volumes (only as slices)
        self.seismic_uids_to_hide = set()

        # Track interpretation lines and their associated slice info
        # Format: {uid: {'seismic_uid': str, 'axis': str, 'slice_index': int}}
        self.interpretation_lines = {}

        # Spatial Index for fast lookup: {(seismic_uid, axis, slice_index): set(line_uids)}
        self.interpretation_lines_by_slice = {}
        
        # Track multipart horizons (efficient single-entity containing multiple slices)
        # Format: {uid: {'seismic_uid': str, 'axis': str, 'slice_indices': list, 'slice_to_cell_index': dict}}
        self.multipart_horizons = {}
        self.multipart_faults = {}
        
        # Flag to batch updates during propagation
        self._is_propagating = False

        # Flag to track if initialization has been done
        self._initialized = False

        # Setup specific UI controls
        self.setup_controls()

        # Override default view to something neutral initially
        self.plotter.view_xy()

        # Use trackball style instead of image style to allow proper 3D views
        # Image style forces XY view which breaks Inline/Crossline views
        # self.plotter.enable_trackball_style()

    @staticmethod
    def _build_control_tooltip(summary, low_text=None, high_text=None):
        """Build a consistent tooltip for propagation controls."""
        parts = [summary]
        if low_text or high_text:
            parts.append("")
            if low_text:
                parts.append(f"Low: {low_text}")
            if high_text:
                parts.append(f"High: {high_text}")
        return "\n".join(parts)

    def _apply_control_tooltip(self, widget, summary, low_text=None, high_text=None):
        """Apply the same tooltip text to widgets and labels."""
        if widget is None:
            return
        tooltip = self._build_control_tooltip(
            summary=summary,
            low_text=low_text,
            high_text=high_text,
        )
        widget.setToolTip(tooltip)
        try:
            widget.setWhatsThis(tooltip)
        except Exception:
            pass

    def _make_control_label(self, text, summary, low_text=None, high_text=None):
        """Create a QLabel with the same tooltip used by its paired control."""
        label = QLabel(text)
        self._apply_control_tooltip(
            label,
            summary=summary,
            low_text=low_text,
            high_text=high_text,
        )
        return label

    def _resolve_interpretation_actor_uid(self, actor_name=None):
        """Map slice-filtered actor names back to the real geology uid."""
        if not actor_name:
            return None
        for prefix in ("multipart_slice_", "multipart_fault_slice_"):
            if actor_name.startswith(prefix):
                return actor_name[len(prefix) :]
        return actor_name

    def get_uid_from_actor(self, actor=None):
        """Resolve picked interpretation actors to their source entity uid."""
        actor_name = super().get_uid_from_actor(actor=actor)
        return self._resolve_interpretation_actor_uid(actor_name=actor_name)

    def get_actor_by_uid(self, uid: str = None):
        """Return the visible actor for a uid, including slice-filtered aliases."""
        actors = getattr(self.plotter.renderer, "actors", {})
        for actor_name in (
            uid,
            f"multipart_slice_{uid}",
            f"multipart_fault_slice_{uid}",
            f"geol_coll_{uid}",
            f"geo_{uid}",
        ):
            if actor_name in actors:
                return actors[actor_name]
        return super().get_actor_by_uid(uid)

    def showEvent(self, event):
        """Override Qt showEvent to initialize the view when first shown."""
        super().showEvent(event)
        if not self._initialized:
            self._initialized = True
            # Use QTimer to defer initialization until window is fully rendered
            QTimer.singleShot(0, self._initialize_view)

    def _initialize_view(self):
        """Initialize the slice view after window is shown."""
        self.print_terminal("Initializing interpretation view...")
        # Clear any inherited volumetric actors
        self.clear_seismic_volumes()
        # Reset initialization flag used for indexing
        self._lines_indexed = False
        #Refresh volume list and create initial slice
        self.refresh_volume_list()
        
        # Scan and index existing horizons if we have a volume selected
        # Note: on_volume_changed (triggered by refresh_volume_list) already handles this,
        # but we call it again here as a safety net for edge cases
        if self.current_seismic_uid:
            # Ensure cache is populated before scanning
            self._populate_seismic_cache()
            self.scan_and_index_existing_horizons()
            self._suppress_full_multipart_actors()
        
    def show_actor_with_property(self, uid=None, coll_name=None, show_property=None, visible=None):
        """Override to prevent showing full seismic volumes and full multipart horizons - we only show slices."""
        # Check if this is a seismic entity that we're slicing
        if coll_name == 'image_coll' and uid:
            try:
                topology = self.parent.image_coll.get_uid_topology(uid)
                if topology == 'Seismics':
                    # Don't show the full seismic volume - we show slices instead
                    self.print_terminal(f"Skipping full volume display for seismic: {uid}")
                    self.seismic_uids_to_hide.add(uid)
                    return
            except:
                pass
        
        # Check if this is a multipart horizon - NEVER show the full version
        if coll_name == 'geol_coll' and uid:
            try:
                vtk_obj = self.parent.geol_coll.get_uid_vtk_obj(uid)
                cell_data = vtk_obj.GetCellData() if vtk_obj is not None else None
                # During BaseView bootstrap the interpretation-specific state is not ready yet.
                # Block raw multipart actors from being added by the abstract view.
                if (
                    cell_data
                    and cell_data.HasArray("slice_index")
                    and (
                        not hasattr(self, "current_seismic_uid")
                        or not hasattr(self, "current_axis")
                        or not hasattr(self, "current_slice_index")
                    )
                ):
                    return
                if cell_data and cell_data.HasArray("slice_index"):
                    # Reconstruct multipart metadata before the raw actor is added.
                    self.scan_and_index_single_horizon(uid)
            except Exception:
                pass

            if hasattr(self, 'multipart_horizons') and uid in self.multipart_horizons:
                # Don't show the full multipart horizon - we show filtered slices instead
                # Just update the visibility of our filtered version
                self.update_multipart_horizon_visibility(uid)
                return
            if hasattr(self, 'multipart_faults') and uid in self.multipart_faults:
                # Don't show the full multipart fault - we show filtered slices instead
                self.update_multipart_fault_visibility(uid)
                return
        
        # For all other entities, use normal display
        super().show_actor_with_property(uid=uid, coll_name=coll_name, show_property=show_property, visible=visible)
        # After showing, increase line width for interpretation lines
        if coll_name == 'geol_coll' and uid:
            try:
                # Check if this is an interpretation line (not multipart - those are handled above)
                is_interp_line = uid in self.interpretation_lines if hasattr(self, 'interpretation_lines') else False
                
                if is_interp_line:
                    # Get the actor and increase line width significantly for better visibility
                    if uid in self.plotter.renderer.actors:
                        actor = self.plotter.renderer.actors[uid]
                        if actor and hasattr(actor, 'GetProperty'):
                            # Use thicker lines for multipart horizons (6) vs regular interpretation lines (4)
                            line_width = 6 if is_multipart else 4
                            actor.GetProperty().SetLineWidth(line_width)
            except:
                pass

    def set_orientation_widget(self):
        """Override ViewMap's North Arrow with a Seismic Axes widget."""
        self.plotter.add_axes(
            xlabel='IL',
            ylabel='XL', 
            zlabel='Z',
            line_width=2,
            interactive=False,
            color='white',
            viewport=(0, 0, 0.3, 0.3)
        )
        
    def setup_controls(self):
        """Add controls for slicing to the layout"""
        # Main widget
        control_widget = QWidget()
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(5, 5, 5, 5)
        control_widget.setLayout(main_layout)
        
        # --- Top Row: Slicing Controls ---
        top_layout = QHBoxLayout()
        main_layout.addLayout(top_layout)
        
        # Seismic Volume Selector
        top_layout.addWidget(QLabel("Volume:"))
        self.combo_volume = QComboBox()
        self.combo_volume.currentIndexChanged.connect(self.on_volume_changed)
        top_layout.addWidget(self.combo_volume)
        
        # Slice Type Selector
        top_layout.addWidget(QLabel("View:"))
        self.combo_view = QComboBox()
        self.combo_view.addItems(["Inline", "Crossline", "Z-slice"])
        self.combo_view.currentTextChanged.connect(self.on_view_type_changed)
        top_layout.addWidget(self.combo_view)
        
        # Slice Index Slider
        top_layout.addWidget(QLabel("Slice:"))
        self.slider_slice = QSlider(Qt.Horizontal)
        self.slider_slice.valueChanged.connect(self.on_slider_changed)
        top_layout.addWidget(self.slider_slice)
        
        # Slice Index SpinBox
        self.spin_slice = QSpinBox()
        self.spin_slice.valueChanged.connect(self.on_spin_changed)
        top_layout.addWidget(self.spin_slice)
        
        # --- Bottom Row: Toggles ---
        bot_layout = QHBoxLayout()
        main_layout.addLayout(bot_layout)
        
        # Grid Toggle
        self.chk_grid = QCheckBox("Grid")
        self.chk_grid.setChecked(False)
        self.chk_grid.stateChanged.connect(self._on_annotation_toggle_changed)
        bot_layout.addWidget(self.chk_grid)

        # Title Toggle
        self.chk_title = QCheckBox("Title")
        self.chk_title.setChecked(True)
        self.chk_title.stateChanged.connect(self._on_annotation_toggle_changed)
        bot_layout.addWidget(self.chk_title)
        
        # Directions Toggle
        self.chk_dirs = QCheckBox("NS/EW")
        self.chk_dirs.setChecked(True)
        self.chk_dirs.stateChanged.connect(self._on_annotation_toggle_changed)
        bot_layout.addWidget(self.chk_dirs)

        # Axes Widget Toggle
        self.chk_axes = QCheckBox("Axes")
        self.chk_axes.setChecked(True)
        self.chk_axes.stateChanged.connect(self.toggle_orientation_widget)
        bot_layout.addWidget(self.chk_axes)
        
        # Spacer to push checks to left? Or just let them flow.
        bot_layout.addStretch()

        # Auto-refresh volume list on startup
        self.refresh_volume_list()
        
        # Add to main layout
        # Using a QDockWidget for controls to ensure it doesn't interfere with the render window
        self.controls_dock = QDockWidget("Interpretation Controls", self)
        self.controls_dock.setWidget(control_widget)
        self.controls_dock.setAllowedAreas(Qt.TopDockWidgetArea | Qt.BottomDockWidgetArea)
        self.addDockWidget(Qt.TopDockWidgetArea, self.controls_dock)

    def _on_annotation_toggle_changed(self):
        """Handle annotation toggle changes and render."""
        self.update_grid_annotations()
        self.plotter.render()

    def toggle_orientation_widget(self, state):
        """Toggle visibility of the orientation widget."""
        if state == 2: # Checked
            # Re-enable/Re-add. 
            # PyVista add_axes adds it. If we hide it, we might remove it.
            # remove_axes() ?
            self.set_orientation_widget()
        else:
            self.plotter.hide_axes()
        
    def on_entities_added(self, uids, collection):
        """Called when new entities are added to any collection"""
        # Skip visual updates if we are batching (e.g. during propagation)
        if hasattr(self, '_is_propagating') and self._is_propagating:
            return

        # Check if it's the image collection (where seismics live)
        if collection == self.parent.image_coll:
            self.print_terminal("New entities added to image collection, refreshing volume list...")
            self.refresh_volume_list()
        # Check if it's the geological collection (where lines live)
        elif collection == self.parent.geol_coll:
            self.print_terminal(f"New geological entities added: {uids}")
            # Display the new entities in this view
            for uid in uids:
                try:
                    # Check if this is an interpretation line we're tracking
                    if uid in self.interpretation_lines:
                        # Only show if it matches current slice
                        slice_info = self.interpretation_lines[uid]
                        matches_current_slice = (
                            slice_info['seismic_uid'] == self.current_seismic_uid and
                            slice_info['axis'] == self.current_axis and
                            slice_info['slice_index'] == self.current_slice_index
                        )
                        self.show_actor_with_property(uid=uid, coll_name='geol_coll', visible=matches_current_slice)
                        self.print_terminal(f"Added interpretation line {uid}, visible={matches_current_slice}")
                        continue
                    else:
                        # NEW: Try to classify it immediately if we have a volume loaded
                        # This handles undo/redo or external adds
                        classified_as_multipart_horizon = False
                        classified_as_multipart_fault = False
                        if self.current_seismic_uid:
                            self.scan_and_index_single_horizon(uid)
                            if uid in self.interpretation_lines:
                                # It was fully classified
                                slice_info = self.interpretation_lines[uid]
                                matches_current_slice = (
                                    slice_info['seismic_uid'] == self.current_seismic_uid and
                                    slice_info['axis'] == self.current_axis and
                                    slice_info['slice_index'] == self.current_slice_index
                                )
                                self.show_actor_with_property(uid=uid, coll_name='geol_coll', visible=matches_current_slice)
                                continue

                            classified_as_multipart_horizon = (
                                hasattr(self, 'multipart_horizons') and
                                uid in self.multipart_horizons
                            )
                            classified_as_multipart_fault = (
                                hasattr(self, 'multipart_faults') and
                                uid in self.multipart_faults
                            )

                        # For multipart interpretation entities, always force filtered-by-slice rendering.
                        if classified_as_multipart_horizon:
                            self.show_actor_with_property(uid=uid, coll_name='geol_coll', visible=False)
                            self.update_multipart_horizon_visibility(uid)
                            continue

                        if classified_as_multipart_fault:
                            self.show_actor_with_property(uid=uid, coll_name='geol_coll', visible=False)
                            self.update_multipart_fault_visibility(uid)
                            continue

                        # Not a tracked interpretation line, show normally
                        self.show_actor_with_property(uid=uid, coll_name='geol_coll', visible=True)
                except Exception as e:
                    self.print_terminal(f"Error displaying new entity {uid}: {e}")
        
    def refresh_volume_list(self):
        """Refresh the list of available seismic volumes"""
        # Guard: Check if combo_volume exists (may not during early initialization)
        if not hasattr(self, 'combo_volume') or self.combo_volume is None:
            self.print_terminal("refresh_volume_list: combo_volume not yet initialized")
            return
            
        self.print_terminal("Refreshing seismic volume list...")
        self.combo_volume.blockSignals(True)
        
        # Remember current selection if any
        previous_uid = self.current_seismic_uid
        
        self.combo_volume.clear()
        
        # Find all Seismics entities in image_coll - use the same approach as mesh slicer
        candidates = []
        try:
            if hasattr(self.parent, 'image_coll') and self.parent.image_coll is not None:
                # Get all UIDs from the collection using the property
                all_uids = self.parent.image_coll.get_uids
                self.print_terminal(f"image_coll has {len(all_uids)} entities (UIDs)")
                
                for uid in all_uids:
                    topology = self.parent.image_coll.get_uid_topology(uid)
                    name = self.parent.image_coll.get_uid_name(uid)
                    self.print_terminal(f"  Entity: {name}, topology: {topology}, uid: {uid}")
                    
                    if topology == 'Seismics':
                        candidates.append((name, uid))
                        self.print_terminal(f"  -> Found Seismics: {name} ({uid})")
                        
                self.print_terminal(f"Total Seismics found: {len(candidates)}")
            else:
                self.print_terminal("No image_coll found on parent!")
        except Exception as e:
            self.print_terminal(f"Error getting seismic volumes: {e}")
            self.print_terminal(traceback_format_exc())
                    
        for name, uid in candidates:
            self.combo_volume.addItem(name, uid)
            
        self.combo_volume.blockSignals(False)
        
        if self.combo_volume.count() > 0:
            # Try to restore previous selection, otherwise select first
            restored = False
            if previous_uid:
                for i in range(self.combo_volume.count()):
                    if self.combo_volume.itemData(i) == previous_uid:
                        self.combo_volume.setCurrentIndex(i)
                        restored = True
                        break
            
            if not restored:
                self.combo_volume.setCurrentIndex(0)
            
            self.current_seismic_uid = self.combo_volume.currentData()
            self.print_terminal(f"Selected volume UID: {self.current_seismic_uid}")
            self.update_slice_limits()
            self.update_camera_orientation()
            self.update_slice()
        else:
            self.current_seismic_uid = None
            self.print_terminal("No seismic volumes found in image_coll!")
        
    def on_volume_changed(self, index):
        if index < 0:
            return
        self.current_seismic_uid = self.combo_volume.itemData(index)
        if self.current_seismic_uid:
            self.print_terminal(f"Volume changed to: {self.combo_volume.currentText()} ({self.current_seismic_uid})")
            
            # Reset indexing on volume change to re-scan for the new volume
            self._lines_indexed = False
            self.interpretation_lines.clear()
            self.interpretation_lines_by_slice.clear()
            # Also clear multipart horizons tracking when volume changes
            self.multipart_horizons.clear()
            self.multipart_faults.clear()
            
            self._camera_initialized = False  # Reset camera on volume change
            self.scalar_range = None  # Reset scalar range
            # Clear cached seismic data and scalar range when volume changes
            if hasattr(self, '_cached_seismic'):
                del self._cached_seismic
            if hasattr(self, '_cached_scalar_range'):
                del self._cached_scalar_range
            
            # Pre-populate the seismic cache BEFORE scanning horizons
            # This is needed because scan_and_index_single_horizon uses _cached_bounds/_cached_dims
            self._populate_seismic_cache()
            
            self.update_slice_limits()
            self.update_camera_orientation()
            # Scan for existing horizons compatible with this volume
            self.scan_and_index_existing_horizons()
            self._suppress_full_multipart_actors()
            self.update_slice()
        
    def on_view_type_changed(self, text):
        self.current_axis = text
        self._camera_initialized = False  # Reset camera on axis change
        self.update_slice_limits()
        self.update_camera_orientation()
        self.update_slice()
        
    def on_slider_changed(self, value):
        self.spin_slice.blockSignals(True)
        self.spin_slice.setValue(value)
        self.spin_slice.blockSignals(False)
        self.current_slice_index = value
        self.update_slice()
        
    def on_spin_changed(self, value):
        self.slider_slice.blockSignals(True)
        self.slider_slice.setValue(value)
        self.slider_slice.blockSignals(False)
        self.current_slice_index = value
        self.update_slice()

    def update_slice_limits(self):
        if not self.current_seismic_uid:
            return
            
        # Get vtk object
        seismic = self.parent.image_coll.get_uid_vtk_obj(self.current_seismic_uid)
        if not seismic:
            return
            
        # dimensions are (nx, ny, nz) - use VTK method
        dims = seismic.GetDimensions()
        
        max_idx = 0
        if self.current_axis == 'Inline': # X-axis usually? or Y? 
            # In SegyStandardizer/segy2vtk:
            # Inline is usually associated with segyfile.ilines
            # StructuredGrid dimensions correspond to shape.
            # We need to assume standard orientation or check.
            # Let's assume dims[0] is Inline/X, dims[1] is Crossline/Y, dims[2] is Time/Z
            max_idx = dims[0] - 1
        elif self.current_axis == 'Crossline':
            max_idx = dims[1] - 1
        elif self.current_axis == 'Z-slice':
            max_idx = dims[2] - 1
            
        self.slider_slice.setRange(0, max_idx)
        self.spin_slice.setRange(0, max_idx)
        
        # Reset if out of bounds
        if self.current_slice_index > max_idx:
            self.current_slice_index = max_idx
            self.slider_slice.setValue(max_idx)
            
    def update_camera_orientation(self):
        """Set camera orthogonal to the slice and fit view."""
        self.plotter.enable_parallel_projection()
        self.plotter.enable_image_style()

        # If we have current slice bounds and scale, use the robust helper
        if hasattr(self, 'current_slice_bounds') and self.current_slice_bounds is not None:
             scale = [1.0, 1.0, 1.0]
             if self.plotter.scale is not None:
                 scale = self.plotter.scale

             # Re-calculate center from bounds?
             # Slice center might not be stored directly unless we calculated it in `update_slice`.
             # `update_slice` calculates slice_center.
             # Ideally update_camera_orientation is called AFTER update_slice logic or relies on stored state.
             # But usually on_view_type_changed calls update_slice immediately after.
             # So let's rely on update_slice to set the camera.
             pass

        # Set initial view orientation (before slice is fully loaded)
        # Don't call reset_camera() here - let update_camera_to_slice() handle the complete camera setup
        if self.current_axis == 'Inline':
            self.plotter.view_yz()
        elif self.current_axis == 'Crossline':
            self.plotter.view_xz()
        elif self.current_axis == 'Z-slice':
            self.plotter.view_xy()

    def end_pick(self, pos):
        """Override View2D.end_pick to prevent resetting to default View XY."""
        # Remove the selector observer
        if hasattr(self.plotter.iren, 'interactor'): # Safety check
            self.plotter.iren.interactor.RemoveObservers("LeftButtonPressEvent")
        
        self.plotter.untrack_click_position(side="right")
        self.plotter.untrack_click_position(side="left")

        # Specific to ViewInterpretation: Restore our specific view orientation
        # instead of generic enable_image_style() which enforces view_xy()
        self.update_camera_orientation()
        
        # Closing settings
        self.plotter.reset_key_events()
        self.selected_uids = self.parent.selected_uids
        self.enable_actions()

    def _populate_seismic_cache(self):
        """Pre-populate the seismic cache (dimensions, bounds) for horizon scanning.
        
        This should be called before scan_and_index_existing_horizons() to ensure
        the cached bounds and dimensions are available for classifying horizons.
        """
        if not self.current_seismic_uid:
            return
            
        # Check if cache is already valid for this seismic
        if (hasattr(self, '_cached_seismic') and 
            hasattr(self, '_cached_seismic_uid') and 
            self._cached_seismic_uid == self.current_seismic_uid):
            return  # Cache is already valid
        
        try:
            seismic_vtk = self.parent.image_coll.get_uid_vtk_obj(self.current_seismic_uid)
            if not seismic_vtk:
                self.print_terminal("Could not get seismic VTK object for cache")
                return
            self._cached_seismic = pv.wrap(seismic_vtk)
            self._cached_seismic_uid = self.current_seismic_uid
            self._cached_dims = self._cached_seismic.dimensions
            self._cached_bounds = self._cached_seismic.bounds
            self.print_terminal(f"Pre-cached seismic dims: {self._cached_dims}, bounds: {self._cached_bounds}")
            
            # Also cache scalar range for consistent colormap
            if 'intensity' in self._cached_seismic.array_names:
                self._cached_scalar_range = self._cached_seismic.get_data_range('intensity')
            else:
                self._cached_scalar_range = None
        except Exception as e:
            self.print_terminal(f"Error pre-populating seismic cache: {e}")

    def update_slice(self):
        if not self.current_seismic_uid:
            self.print_terminal("No seismic UID selected")
            return
        
        # Disable rendering during updates to prevent flickering
        # We'll render once at the very end
        self.plotter.render_window.SetDesiredUpdateRate(0.01)
        
        # Cache the seismic wrapper to avoid repeated wrapping
        if not hasattr(self, '_cached_seismic') or not hasattr(self, '_cached_seismic_uid') or self._cached_seismic_uid != self.current_seismic_uid:
            self.print_terminal(f"Caching seismic data for {self.current_seismic_uid}")
            seismic_vtk = self.parent.image_coll.get_uid_vtk_obj(self.current_seismic_uid)
            if not seismic_vtk:
                self.print_terminal("Could not get seismic VTK object")
                return
            self._cached_seismic = pv.wrap(seismic_vtk)
            self._cached_seismic_uid = self.current_seismic_uid
            self._cached_dims = self._cached_seismic.dimensions
            self._cached_bounds = self._cached_seismic.bounds
            self.print_terminal(f"Seismic dims: {self._cached_dims}, bounds: {self._cached_bounds}")
            # Calculate scalar range from the FULL volume for consistent colormap across all slices
            # Use get_data_range for the full extent (like mesh slicer does in view_3d)
            if 'intensity' in self._cached_seismic.array_names:
                self._cached_scalar_range = self._cached_seismic.get_data_range('intensity')
                self.print_terminal(f"Scalar range (full volume): {self._cached_scalar_range}")
            else:
                self._cached_scalar_range = None
        
        # Always use the cached scalar range from the full volume to ensure consistent colormap
        # This prevents per-slice rescaling which causes intensity changes when scrolling
        if not hasattr(self, '_cached_scalar_range'):
            self._cached_scalar_range = None
        self.scalar_range = self._cached_scalar_range
        
        seismic = self._cached_seismic
        dims = self._cached_dims
        bounds = self._cached_bounds
        
        # Hide full volume if displayed
        try:
            if self.current_seismic_uid in self.plotter.renderer.actors:
                self.plotter.remove_actor(self.current_seismic_uid)
        except:
            pass
        
        slice_actor_name = "seismic_slice_actor"
            
        try:
            # Helper to get coordinate from index
            def get_coord(axis_idx, idx):
                min_val = bounds[axis_idx*2]
                max_val = bounds[axis_idx*2+1]
                n_points = dims[axis_idx]
                if n_points <= 1: return min_val
                return min_val + idx * (max_val - min_val) / (n_points - 1)

            # Use extract_subset then convert to surface for proper rendering
            subset = None
            if self.current_axis == 'Inline':
                i = self.current_slice_index
                subset = seismic.extract_subset([i, i, 0, dims[1]-1, 0, dims[2]-1])
                # Calculate exact slice position from index using original volume grid
                self.current_slice_position = bounds[0] + i * (bounds[1] - bounds[0]) / max(dims[0] - 1, 1)
            elif self.current_axis == 'Crossline':
                j = self.current_slice_index
                subset = seismic.extract_subset([0, dims[0]-1, j, j, 0, dims[2]-1])
                # Calculate exact slice position from index using original volume grid
                self.current_slice_position = bounds[2] + j * (bounds[3] - bounds[2]) / max(dims[1] - 1, 1)
            elif self.current_axis == 'Z-slice':
                k = self.current_slice_index
                subset = seismic.extract_subset([0, dims[0]-1, 0, dims[1]-1, k, k])
                # Calculate exact slice position from index using original volume grid
                self.current_slice_position = bounds[4] + k * (bounds[5] - bounds[4]) / max(dims[2] - 1, 1)
            
            if subset is None or subset.n_points == 0:
                self.print_terminal("Subset is empty!")
                return
            
            # Convert StructuredGrid to surface for proper 2D rendering
            subset = subset.extract_surface()

            # Align slice to its true plane for rotated/skewed grids
            # (avoids forcing Inline/Crossline to X/Y-constant planes)
            affine = self._get_seismic_axis_vectors()
            if affine is not None:
                plane_info = self._get_slice_plane_from_affine(
                    slice_idx=self.current_slice_index,
                    affine=affine,
                    axis=self.current_axis,
                )
                if plane_info is not None:
                    plane_center, plane_normal, _row_vec, _col_vec, _dims = plane_info
                    self.current_slice_plane_center = plane_center
                    self.current_slice_plane_normal = plane_normal
                    try:
                        pts = subset.points.astype(np.float64, copy=False)
                        subset.points = self._project_points_to_plane(pts, plane_center, plane_normal)
                    except Exception:
                        pass
            
            self.print_terminal(f"Slice position for {self.current_axis} index {self.current_slice_index}: {self.current_slice_position}")
            
            scalars = 'intensity' if 'intensity' in subset.array_names else (subset.array_names[0] if subset.array_names else None)
            
            # Get colormap and scalar range
            cmap = self.get_seismic_colormap()
            scalar_range = self.scalar_range if hasattr(self, 'scalar_range') else None
            
            # Check if actor exists - update in place for smooth transition
            actor_exists = slice_actor_name in self.plotter.renderer.actors
            
            if actor_exists and self.slice_actor is not None:
                # Update existing actor's mesh data in-place (smooth, no flicker)
                self.slice_actor.mapper.SetInputData(subset)
                self.slice_actor.mapper.SetScalarRange(scalar_range if scalar_range else subset.get_data_range())
                self.slice_actor.mapper.Update()
                self.slice_actor.SetPickable(False)
            else:
                # First time: add new slice actor
                self.slice_actor = self.plotter.add_mesh(
                    subset, 
                    name=slice_actor_name,
                    scalars=scalars,
                    clim=scalar_range,
                    cmap=cmap, 
                    show_scalar_bar=False, 
                    pickable=False,
                    lighting=False,
                    reset_camera=False
                )
            
            self.current_slice_bounds = subset.bounds
            slice_center = subset.center
            
            scale = [1.0, 1.0, 1.0]
            if self.plotter.scale is not None:
                scale = self.plotter.scale
            
            # Apply scale to center for camera positioning
            scaled_center = [
                slice_center[0] * scale[0],
                slice_center[1] * scale[1],
                slice_center[2] * scale[2]
            ]
            
            # Update camera to fit the slice
            # Only reset camera on first load, axis change, or if explicitly requested (e.g. on slice move)
            # The user requested that moving the slicer resets the camera to respect VE and fit the slice.
            # So we effectively update it every time the slice bounds/position changes significantly or if we want to enforce the lock.
            
            # For now, we update it if not initialized OR if we want to force "Fit to View" behavior on slice change
            # However, forceful reset on every scroll might be annoying if user zoomed in.
            # User said: "when we are moving the slicer ... the camera doesnt respect the vertical exageration ... like it must repsect it"
            # And "camera is still not properly position to the whole slice"
            # This implies we SHOULD match the slice bounds.
            
            # Let's do it on every update for now to ensure "locking" behavior as requested ("lock the camera view to the slice").
            self.update_camera_to_slice(scaled_center, bounds, scale)
            
            # Update grid annotations on every slice change to show current slice number
            self.update_grid_annotations()
            
            # Update visibility of interpretation lines for the current slice
            self.update_interpretation_line_visibility()
            
            # Update visibility of multipart horizons (efficient single-entity horizons)
            self.update_all_multipart_horizons_visibility()
            
            # Update visibility of multipart faults
            self.update_all_multipart_faults_visibility()


        except Exception as e:
            self.print_terminal(f"Error updating slice: {e}")
        
        # Restore normal update rate and render once at the end
        # This prevents flickering by batching all visual updates
        self.plotter.render_window.SetDesiredUpdateRate(30)
        self.plotter.render()

    def update_grid_annotations(self):
        """Update grid rulers, title, and direction labels based on toggle states."""
        try:
            # 1. Update Grid (Rulers)
            if self.slice_actor:
                # Check toggle
                if hasattr(self, 'chk_grid') and self.chk_grid.isChecked():
                    # Determine labels based on axis
                    xtitle, ytitle, ztitle = "", "", ""
                    if self.current_axis == 'Inline':
                         xtitle = "Crossline"
                         ytitle = "Depth/Time"
                    elif self.current_axis == 'Crossline':
                         xtitle = "Inline"
                         ytitle = "Depth/Time"
                    elif self.current_axis == 'Z-slice':
                         xtitle = "Inline"
                         ytitle = "Crossline"

                    # Auto-scale large coordinates to keep labels short (e.g. 6.08e8 -> 6.08)
                    bounds = self.slice_actor.bounds
                    scaled_ranges = list(bounds)
                    
                    def get_scale_and_title(min_v, max_v, title):
                        mean_v = (min_v + max_v) / 2.0
                        if abs(mean_v) > 0:
                            power = math_floor(math_log10(abs(mean_v)))
                            # Only scale if >= 10000 or <= 0.0001
                            if abs(power) >= 4:
                                scale = 10**power
                                return scale, f"{title} (x10^{power})"
                        return 1.0, title

                    x_scale, x_title_scaled = get_scale_and_title(bounds[0], bounds[1], xtitle)
                    y_scale, y_title_scaled = get_scale_and_title(bounds[2], bounds[3], ytitle)
                    z_scale, z_title_scaled = get_scale_and_title(bounds[4], bounds[5], ztitle)

                    scaled_ranges[0] /= x_scale
                    scaled_ranges[1] /= x_scale
                    scaled_ranges[2] /= y_scale
                    scaled_ranges[3] /= y_scale
                    scaled_ranges[4] /= z_scale
                    scaled_ranges[5] /= z_scale

                    self.plotter.show_grid(
                        mesh=self.slice_actor,
                        grid=False,
                        location='outer',
                        ticks='both',
                        show_xaxis=True,
                        show_yaxis=True,
                        show_zaxis=True,
                        xlabel=x_title_scaled,
                        ylabel=y_title_scaled,
                        zlabel=z_title_scaled,
                        font_size=8,
                        color='white',
                        bold=False,
                        n_xlabels=5,
                        n_ylabels=5,
                        fmt='%.3g',
                        axes_ranges=scaled_ranges
                    )
                else:
                    self.plotter.remove_bounds_axes() # Hides grid

            # 2. Update Title (Top Center)
            # Remove existing title first
            if hasattr(self, '_title_actor') and self._title_actor:
                self.plotter.remove_actor(self._title_actor)
                self._title_actor = None
            
            if hasattr(self, 'chk_title') and self.chk_title.isChecked():
                title_text = f"{self.current_axis}: {self.current_slice_index}"
                self._title_actor = self.plotter.add_text(
                    title_text, 
                    position='upper_edge', 
                    font_size=14, 
                    color='white',
                    shadow=True
                )
            
            # 3. Direction Labels (N/S/E/W)
            # Clear old labels
            if hasattr(self, '_direction_actors'):
                for actor in self._direction_actors:
                    self.plotter.remove_actor(actor)
            self._direction_actors = []
            
            if hasattr(self, 'chk_dirs') and self.chk_dirs.isChecked():
                # Logic for labels
                left_label, right_label = "", ""
                if self.current_axis == 'Inline':
                    left_label = "S"
                    right_label = "N"
                elif self.current_axis == 'Crossline':
                    left_label = "W"
                    right_label = "E"
                 
                if left_label and right_label:
                    act_l = self.plotter.add_text(left_label, position='upper_left', font_size=16, color='yellow')
                    act_r = self.plotter.add_text(right_label, position='upper_right', font_size=16, color='yellow')
                    self._direction_actors.extend([act_l, act_r])

        except Exception as e:
             self.print_terminal(f"Error updating annotations: {e}")


    def update_camera_to_slice(self, center, bounds, scale):
        """
        Enforce a 2D-like view locked to the current axis, fitted to the slice bounds,
        respecting Vertical Exaggeration.
        """
        # Lock rotation by using Image style (Left=Pan, Right=Zoom)
        self.plotter.enable_image_style()
        self.plotter.enable_parallel_projection()

        # Get camera reference - we'll set orientation manually without calling view methods
        # to avoid the automatic reset_camera() that view_xy/xz/yz trigger
        camera = self.plotter.camera

        # Calculate fitting dimensions with Scale (VE) applied
        # bounds is [xmin, xmax, ymin, ymax, zmin, zmax] (unscaled)
        # scale is [sx, sy, sz]

        # Determine width/height of the slice in WORLD (scaled) units
        width = 0.0
        height = 0.0

        if self.current_axis == 'Inline':
            # YZ plane - camera looks along +X axis (from negative X towards positive X)
            width = abs(bounds[3] - bounds[2]) * scale[1]
            height = abs(bounds[5] - bounds[4]) * scale[2]

            # Position camera on NEGATIVE X side looking towards POSITIVE X (front view)
            camera.position = (center[0] - max(width, height) * 2, center[1], center[2])
            camera.focal_point = center
            camera.view_up = (0, 0, 1)
            
        elif self.current_axis == 'Crossline':
            # XZ plane - camera looks along +Y axis (from negative Y towards positive Y)
            width = abs(bounds[1] - bounds[0]) * scale[0]
            height = abs(bounds[5] - bounds[4]) * scale[2]
            
            # Position camera on NEGATIVE Y side looking towards POSITIVE Y (front view)
            camera.position = (center[0], center[1] - max(width, height) * 2, center[2])
            camera.focal_point = center
            camera.view_up = (0, 0, 1)
            
        elif self.current_axis == 'Z-slice':
            # XY plane
            width = abs(bounds[1] - bounds[0]) * scale[0]
            height = abs(bounds[3] - bounds[2]) * scale[1]
            
            # Position: Look down Z axis
            camera.position = (center[0], center[1], center[2] + max(width, height) * 2)
            camera.focal_point = center
            camera.view_up = (0, 1, 0)
            
        # Refine Parallel Scale to FIT WHOLE SLICE
        # parallel_scale is half the viewport height in world units.
        # We need to consider the viewport aspect ratio.
        
        try:
            # window_size is (width, height)
            win_w, win_h = self.plotter.window_size
            if win_h > 0:
                view_aspect = win_w / win_h
            else:
                view_aspect = 1.0
        except:
            view_aspect = 1.0
            
        # Slice aspect ratio
        slice_aspect = width / height if height > 0 else 1.0
        
        # If slice is "wider" than the view (relative to aspect), we fit to WIDTH
        if slice_aspect > view_aspect:
            # Fit width: 
            # The view width must be at least 'width'.
            # view_width = width
            # view_height = view_width / view_aspect
            # parallel_scale = view_height / 2
            desired_height = width / view_aspect
            padding = 1.05 # 5% padding
            camera.parallel_scale = (desired_height / 2) * padding
        else:
            # Fit height:
            # The view height must be at least 'height'
            padding = 1.05
            camera.parallel_scale = (height / 2) * padding
            
        self.plotter.reset_camera_clipping_range()
        self._camera_initialized = True
                    

    
    def get_seismic_colormap(self):
        """Get the colormap for 'intensity' property from the legend manager, or default to gray."""
        try:
            if hasattr(self.parent, 'prop_legend_df') and self.parent.prop_legend_df is not None:
                # Look for 'intensity' property colormap
                row = self.parent.prop_legend_df[self.parent.prop_legend_df['property_name'] == 'intensity']
                if not row.empty:
                    return row['colormap'].iloc[0]
        except:
            pass
        return 'gray'  # Default

    def _get_geol_legend_color(self, uid, default=(1.0, 1.0, 1.0)):
        """Return normalized RGB color for a geological entity from the legend table."""
        try:
            legend = self.parent.geol_coll.get_uid_legend(uid=uid)
            return (
                legend["color_R"] / 255.0,
                legend["color_G"] / 255.0,
                legend["color_B"] / 255.0,
            )
        except Exception:
            return default

    def _sanitize_legend_value(self, value, fallback="undef"):
        """Normalize legend metadata values so they are always usable strings."""
        if value is None:
            return fallback
        try:
            text = str(value).strip()
        except Exception:
            return fallback
        if text == "" or text.lower() in {"nan", "none", "null"}:
            return fallback
        return text

    def _sanitize_legend_choices(self, values, fallback="undef"):
        """Return unique, clean combo choices for legend-related dialogs."""
        out = []
        for value in values:
            clean = self._sanitize_legend_value(value, fallback="")
            if clean and clean not in out:
                out.append(clean)
        if not out:
            out = [fallback]
        return out

    def _get_geol_legend_style(self, uid):
        """Return standard style values (color, line width, opacity) from geology legend."""
        try:
            legend = self.parent.geol_coll.get_uid_legend(uid=uid)
            return {
                "color": (
                    legend["color_R"] / 255.0,
                    legend["color_G"] / 255.0,
                    legend["color_B"] / 255.0,
                ),
                "line_width": float(legend["line_thick"]),
                "opacity": float(legend["opacity"]) / 100.0,
            }
        except Exception:
            return {
                "color": (1.0, 1.0, 1.0),
                "line_width": 5.0,
                "opacity": 1.0,
            }

    def _set_entity_parent_to_current_seismic(self, entity_dict):
        """Attach the active seismic uid as parent metadata for generated interpretation entities."""
        if entity_dict is None:
            return
        entity_dict["parent_uid"] = str(self.current_seismic_uid) if self.current_seismic_uid else ""

    def _get_entity_parent_seismic_uid(self, uid):
        """Resolve the seismic parent uid stored on an interpretation entity."""
        try:
            parent_uid = self.parent.geol_coll.get_uid_x_section(uid)
            if isinstance(parent_uid, str) and parent_uid.strip():
                return parent_uid.strip()
        except Exception:
            pass
        return self.current_seismic_uid

    def _is_fault_interpretation_entity(self, uid):
        """Best-effort classification for propagated interpretation entities."""
        for getter_name in ("get_uid_role", "get_uid_feature"):
            try:
                value = getattr(self.parent.geol_coll, getter_name)(uid)
            except Exception:
                value = None
            if isinstance(value, str) and "fault" in value.strip().lower():
                return True
        return False

    def _register_multipart_interpretation_entity(
        self, uid, axis, slice_indices, slice_to_cell_index
    ):
        """Register a multipart interpretation entity in the correct slice-aware registry."""
        if not hasattr(self, "multipart_horizons"):
            self.multipart_horizons = {}
        if not hasattr(self, "multipart_faults"):
            self.multipart_faults = {}

        metadata = {
            'seismic_uid': self._get_entity_parent_seismic_uid(uid),
            'axis': axis,
            'slice_indices': list(slice_indices),
            'slice_to_cell_index': dict(slice_to_cell_index),
            'seed_slice': slice_indices[0] if slice_indices else 0,
        }

        if self._is_fault_interpretation_entity(uid):
            self.multipart_faults[uid] = metadata
            self.multipart_horizons.pop(uid, None)
            return "fault"

        self.multipart_horizons[uid] = metadata
        self.multipart_faults.pop(uid, None)
        return "horizon"

    def _store_single_slice_interpretation_metadata(self, uid=None, slice_info=None):
        """Persist exact slice metadata on a single-slice interpretation line."""
        if not uid or not slice_info:
            return
        try:
            vtk_obj = self.parent.geol_coll.get_uid_vtk_obj(uid)
            if vtk_obj is None:
                return

            field_data = vtk_obj.GetFieldData()
            if field_data is None:
                return

            axis_arr = vtkStringArray()
            axis_arr.SetName("single_slice_axis")
            axis_arr.SetNumberOfValues(1)
            axis_arr.SetValue(0, str(slice_info.get("axis", self.current_axis)))
            if field_data.HasArray("single_slice_axis"):
                field_data.RemoveArray("single_slice_axis")
            field_data.AddArray(axis_arr)

            slice_arr = vtkIntArray()
            slice_arr.SetName("single_slice_index")
            slice_arr.SetNumberOfComponents(1)
            slice_arr.InsertNextValue(int(slice_info.get("slice_index", self.current_slice_index)))
            if field_data.HasArray("single_slice_index"):
                field_data.RemoveArray("single_slice_index")
            field_data.AddArray(slice_arr)
            vtk_obj.Modified()
        except Exception:
            pass

    def _extract_single_slice_interpretation_metadata(self, uid=None, vtk_obj=None):
        """Read explicit slice metadata stored on a single-slice interpretation line."""
        if vtk_obj is None and uid is not None:
            try:
                vtk_obj = self.parent.geol_coll.get_uid_vtk_obj(uid)
            except Exception:
                vtk_obj = None
        if vtk_obj is None:
            return None

        try:
            field_data = vtk_obj.GetFieldData()
            if field_data is None:
                return None
            if not (field_data.HasArray("single_slice_axis") and field_data.HasArray("single_slice_index")):
                return None

            axis_array = field_data.GetAbstractArray("single_slice_axis")
            slice_array = field_data.GetArray("single_slice_index")
            if axis_array is None or slice_array is None or slice_array.GetNumberOfTuples() <= 0:
                return None

            axis = axis_array.GetValue(0)
            slice_index = int(slice_array.GetValue(0))
            return {
                "seismic_uid": self._get_entity_parent_seismic_uid(uid),
                "axis": axis,
                "slice_index": slice_index,
            }
        except Exception:
            return None

    def _refresh_properties_legend(self):
        """Refresh the Properties manager table safely."""
        try:
            self.parent.prop_legend.update_widget(self.parent)
        except Exception:
            pass

    def _format_slice_range_property_name(self, slice_indices):
        """Build a human-readable property label from slice indices."""
        try:
            clean = sorted({int(i) for i in (slice_indices or [])})
        except Exception:
            clean = []
        if not clean:
            return "slice_index"
        return f"slices_{clean[0]}-{clean[-1]}"

    def _extract_slice_indices_from_vtk(self, vtk_obj):
        """Collect unique slice indices from cell/point `slice_index` arrays."""
        if vtk_obj is None:
            return []
        out = []
        try:
            cell_data = vtk_obj.GetCellData()
            if cell_data and cell_data.HasArray("slice_index"):
                arr = cell_data.GetArray("slice_index")
                for i in range(arr.GetNumberOfTuples()):
                    v = int(arr.GetValue(i))
                    if v >= 0:
                        out.append(v)
            elif vtk_obj.GetPointData() and vtk_obj.GetPointData().HasArray("slice_index"):
                arr = vtk_obj.GetPointData().GetArray("slice_index")
                for i in range(arr.GetNumberOfTuples()):
                    v = int(arr.GetValue(i))
                    if v >= 0:
                        out.append(v)
        except Exception:
            return []
        return sorted(set(out))

    def _ensure_slice_range_point_array(self, vtk_obj, prop_name):
        """Create/update a point-data alias array with the range property name."""
        if vtk_obj is None or not prop_name or prop_name == "slice_index":
            return
        try:
            point_data = vtk_obj.GetPointData()
            if point_data is None:
                return
            source = point_data.GetArray("slice_index")
            if source is None:
                return
            alias = vtkIntArray()
            alias.SetName(prop_name)
            alias.SetNumberOfComponents(1)
            for i in range(source.GetNumberOfTuples()):
                alias.InsertNextValue(int(source.GetValue(i)))
            if point_data.HasArray(prop_name):
                point_data.RemoveArray(prop_name)
            point_data.AddArray(alias)
        except Exception:
            pass

    def _ensure_slice_index_property_metadata(self, entity_dict=None, uid=None, vtk_obj=None, slice_indices=None):
        """
        Ensure `slice_index` appears in properties metadata when the geometry carries
        a point/cell `slice_index` array.
        """
        if not slice_indices:
            slice_indices = self._extract_slice_indices_from_vtk(vtk_obj)
        prop_name = self._format_slice_range_property_name(slice_indices)
        if prop_name == "slice_index" and not slice_indices:
            return False
        self._ensure_slice_range_point_array(vtk_obj, prop_name)

        if entity_dict is not None:
            prop_names = list(entity_dict.get("properties_names") or [])
            prop_comps = list(entity_dict.get("properties_components") or [])
            while len(prop_comps) < len(prop_names):
                prop_comps.append(1)
            keep_names = []
            keep_comps = []
            for i, name in enumerate(prop_names):
                if name == "slice_index" or (isinstance(name, str) and name.startswith("slices_")):
                    continue
                keep_names.append(name)
                keep_comps.append(prop_comps[i] if i < len(prop_comps) else 1)
            prop_names = keep_names
            prop_comps = keep_comps
            if prop_name not in prop_names:
                prop_names.append(prop_name)
                prop_comps.append(1)
                entity_dict["properties_names"] = prop_names
                entity_dict["properties_components"] = prop_comps
                return True
            return False

        if uid is not None:
            try:
                prop_names = list(self.parent.geol_coll.get_uid_properties_names(uid) or [])
                prop_comps = list(self.parent.geol_coll.get_uid_properties_components(uid) or [])
            except Exception:
                return False
            while len(prop_comps) < len(prop_names):
                prop_comps.append(1)
            keep_names = []
            keep_comps = []
            for i, name in enumerate(prop_names):
                if name == "slice_index" or (isinstance(name, str) and name.startswith("slices_")):
                    continue
                keep_names.append(name)
                keep_comps.append(prop_comps[i] if i < len(prop_comps) else 1)
            prop_names = keep_names
            prop_comps = keep_comps
            if prop_name in prop_names:
                return False
            prop_names.append(prop_name)
            prop_comps.append(1)
            self.parent.geol_coll.set_uid_properties_names(uid=uid, properties_names=prop_names)
            self.parent.geol_coll.set_uid_properties_components(uid=uid, properties_components=prop_comps)
            try:
                self.parent.signals.data_keys_added.emit([uid], self.parent.geol_coll)
            except Exception:
                pass
            self._refresh_properties_legend()
            return True

        return False

    def _get_visible_line_actor_for_uid(self, uid=None):
        """Return the currently visible actor used to display a line uid in this view."""
        if not uid:
            return None

        actors = getattr(self.plotter.renderer, "actors", {})
        for actor_name in (
            f"multipart_slice_{uid}",
            f"multipart_fault_slice_{uid}",
            uid,
            f"geol_coll_{uid}",
            f"geo_{uid}",
        ):
            actor = actors.get(actor_name)
            if actor is not None:
                try:
                    if actor.GetVisibility():
                        return actor
                except Exception:
                    return actor
        return None

    def _begin_slice_line_edit_pick_mode(self):
        """Temporarily make the seismic slice the only pickable actor during line editing."""
        self._edit_pickable_state = {}
        for name, actor in self.plotter.renderer.actors.items():
            try:
                self._edit_pickable_state[name] = actor.GetPickable()
                actor.SetPickable(name == "seismic_slice_actor")
            except Exception:
                pass

        try:
            if self.slice_actor is not None:
                self.slice_actor.SetPickable(True)
        except Exception:
            pass

    def _get_plotter_scale_factors(self):
        """Return the active plotter scale as XYZ factors."""
        try:
            scale = self.plotter.scale
            if scale is not None and len(scale) >= 3:
                sx = float(scale[0]) if scale[0] not in (None, 0) else 1.0
                sy = float(scale[1]) if scale[1] not in (None, 0) else 1.0
                sz = float(scale[2]) if scale[2] not in (None, 0) else 1.0
                return sx, sy, sz
        except Exception:
            pass
        return 1.0, 1.0, 1.0

    def _build_editor_input_polydata(self, data=None):
        """Build a temporary polyline in display-space coordinates for the editor widget."""
        if data is None:
            return None

        editor_line = PolyLine()
        try:
            editor_line.DeepCopy(data)
        except Exception:
            return data

        try:
            pts = np.asarray(editor_line.points, dtype=float).copy()
        except Exception:
            return editor_line

        sx, sy, sz = self._get_plotter_scale_factors()
        pts[:, 0] *= sx
        pts[:, 1] *= sy
        pts[:, 2] *= sz
        editor_line.points = pts
        editor_line.Modified()
        return editor_line

    def _end_slice_line_edit_pick_mode(self):
        """Restore actor pickability after line editing."""
        saved_state = getattr(self, "_edit_pickable_state", None)
        if saved_state:
            for name, pickable in saved_state.items():
                try:
                    if name in self.plotter.renderer.actors:
                        self.plotter.renderer.actors[name].SetPickable(pickable)
                except Exception:
                    pass
        if hasattr(self, "_edit_pickable_state"):
            try:
                del self._edit_pickable_state
            except Exception:
                pass

    def _prepare_numeric_array_builders(
        self, source_data=None, skip_names=None, skip_prefixes=None
    ):
        """Create writable numeric arrays matching the source VTK data arrays."""
        if source_data is None:
            return []

        skip_names = set(skip_names or [])
        skip_prefixes = tuple(skip_prefixes or ())
        builders = []
        for array_idx in range(source_data.GetNumberOfArrays()):
            source_array = source_data.GetArray(array_idx)
            if source_array is None:
                continue
            array_name = source_array.GetName() or ""
            if array_name in skip_names:
                continue
            if array_name and any(array_name.startswith(prefix) for prefix in skip_prefixes):
                continue

            target_array = source_array.NewInstance()
            target_array.SetName(array_name)
            target_array.SetNumberOfComponents(source_array.GetNumberOfComponents())
            builders.append((source_array, target_array))
        return builders

    def _append_numeric_tuple(self, builders=None, source_idx=None, default_idx=None):
        """Append one tuple to each target numeric array."""
        for source_array, target_array in builders or []:
            tuple_idx = None
            if source_idx is not None and 0 <= source_idx < source_array.GetNumberOfTuples():
                tuple_idx = source_idx
            elif default_idx is not None and 0 <= default_idx < source_array.GetNumberOfTuples():
                tuple_idx = default_idx

            if tuple_idx is None:
                target_array.InsertNextTuple(
                    tuple(0.0 for _ in range(source_array.GetNumberOfComponents()))
                )
            else:
                target_array.InsertNextTuple(source_array.GetTuple(tuple_idx))

    def _get_axis_spacing(self, axis=None):
        """Return the cached spacing for the requested interpretation axis."""
        axis = axis or self.current_axis
        dims = getattr(self, "_cached_dims", None)
        bounds = getattr(self, "_cached_bounds", None)
        if dims is None or bounds is None:
            return None

        axis_to_idx = {"Inline": 0, "Crossline": 1, "Z-slice": 2}
        axis_idx = axis_to_idx.get(axis)
        if axis_idx is None:
            return None

        n_points = max(int(dims[axis_idx]) - 1, 1)
        return float(bounds[axis_idx * 2 + 1] - bounds[axis_idx * 2]) / float(n_points)

    def _world_points_to_slice_uv(self, points=None, slice_idx=None, axis=None, affine=None):
        """Convert world-space points on one slice plane to continuous in-plane slice coordinates."""
        if points is None:
            return None

        pts = np.asarray(points, dtype=float)
        if pts.ndim != 2 or pts.shape[1] != 3 or pts.shape[0] < 2:
            return None

        axis = axis or self.current_axis
        if affine is None:
            affine = self._get_seismic_axis_vectors()

        if affine is not None:
            origin, a0, a1, a2, _dims = affine
            if axis == "Inline":
                base = origin + int(slice_idx) * a0
                basis = np.column_stack([a1, a2])
            elif axis == "Crossline":
                base = origin + int(slice_idx) * a1
                basis = np.column_stack([a0, a2])
            else:
                base = origin + int(slice_idx) * a2
                basis = np.column_stack([a0, a1])
            try:
                uv, *_ = np.linalg.lstsq(basis, (pts - base).T, rcond=None)
                return np.asarray(uv.T, dtype=float)
            except Exception:
                return None

        bounds = getattr(self, "_cached_bounds", None)
        dims = getattr(self, "_cached_dims", None)
        if bounds is None or dims is None:
            return None

        spacing = [
            float(bounds[1] - bounds[0]) / max(int(dims[0]) - 1, 1),
            float(bounds[3] - bounds[2]) / max(int(dims[1]) - 1, 1),
            float(bounds[5] - bounds[4]) / max(int(dims[2]) - 1, 1),
        ]
        if axis == "Inline":
            return np.column_stack(
                [
                    (pts[:, 1] - bounds[2]) / spacing[1] if spacing[1] else 0.0,
                    (pts[:, 2] - bounds[4]) / spacing[2] if spacing[2] else 0.0,
                ]
            )
        if axis == "Crossline":
            return np.column_stack(
                [
                    (pts[:, 0] - bounds[0]) / spacing[0] if spacing[0] else 0.0,
                    (pts[:, 2] - bounds[4]) / spacing[2] if spacing[2] else 0.0,
                ]
            )
        return np.column_stack(
            [
                (pts[:, 0] - bounds[0]) / spacing[0] if spacing[0] else 0.0,
                (pts[:, 1] - bounds[2]) / spacing[1] if spacing[1] else 0.0,
            ]
        )

    def _slice_uv_to_world_points(self, slice_uv=None, slice_idx=None, axis=None, affine=None):
        """Convert continuous in-plane slice coordinates back to world-space points."""
        if slice_uv is None:
            return None

        uv = np.asarray(slice_uv, dtype=float)
        if uv.ndim != 2 or uv.shape[1] != 2 or uv.shape[0] < 2:
            return None

        axis = axis or self.current_axis
        if affine is None:
            affine = self._get_seismic_axis_vectors()

        if affine is not None:
            origin, a0, a1, a2, _dims = affine
            if axis == "Inline":
                base = origin + int(slice_idx) * a0
                basis_row = a1
                basis_col = a2
            elif axis == "Crossline":
                base = origin + int(slice_idx) * a1
                basis_row = a0
                basis_col = a2
            else:
                base = origin + int(slice_idx) * a2
                basis_row = a0
                basis_col = a1
            pts = (
                base[None, :]
                + uv[:, 0:1] * basis_row[None, :]
                + uv[:, 1:2] * basis_col[None, :]
            )
            return np.asarray(pts, dtype=float)

        bounds = getattr(self, "_cached_bounds", None)
        dims = getattr(self, "_cached_dims", None)
        if bounds is None or dims is None:
            return None

        spacing = [
            float(bounds[1] - bounds[0]) / max(int(dims[0]) - 1, 1),
            float(bounds[3] - bounds[2]) / max(int(dims[1]) - 1, 1),
            float(bounds[5] - bounds[4]) / max(int(dims[2]) - 1, 1),
        ]
        axis_spacing = self._get_axis_spacing(axis=axis)
        if axis_spacing is None:
            return None

        target_coord = {
            "Inline": float(bounds[0]) + int(slice_idx) * axis_spacing,
            "Crossline": float(bounds[2]) + int(slice_idx) * axis_spacing,
            "Z-slice": float(bounds[4]) + int(slice_idx) * axis_spacing,
        }[axis]

        pts = np.zeros((uv.shape[0], 3), dtype=float)
        if axis == "Inline":
            pts[:, 0] = target_coord
            pts[:, 1] = bounds[2] + uv[:, 0] * spacing[1]
            pts[:, 2] = bounds[4] + uv[:, 1] * spacing[2]
        elif axis == "Crossline":
            pts[:, 0] = bounds[0] + uv[:, 0] * spacing[0]
            pts[:, 1] = target_coord
            pts[:, 2] = bounds[4] + uv[:, 1] * spacing[2]
        else:
            pts[:, 0] = bounds[0] + uv[:, 0] * spacing[0]
            pts[:, 1] = bounds[2] + uv[:, 1] * spacing[1]
            pts[:, 2] = target_coord
        return pts

    def _build_multipart_vtk_with_replaced_slices(
        self, vtk_obj=None, edited_points_by_slice=None
    ):
        """Return a multipart PolyLine where one or more slices are replaced with edited geometry."""
        if vtk_obj is None or not edited_points_by_slice:
            return None, [], {}

        cell_data = vtk_obj.GetCellData()
        if cell_data is None or not cell_data.HasArray("slice_index"):
            return None, [], {}

        from vtk import vtkCellArray, vtkIntArray, vtkPoints

        point_data = vtk_obj.GetPointData()
        field_data = vtk_obj.GetFieldData()
        cell_slice_array = cell_data.GetArray("slice_index")
        point_slice_array = (
            point_data.GetArray("slice_index")
            if point_data is not None and point_data.HasArray("slice_index")
            else None
        )

        clean_replacements = {}
        for raw_slice_idx, raw_points in dict(edited_points_by_slice).items():
            try:
                target_slice_idx = int(raw_slice_idx)
            except Exception:
                continue
            points = np.asarray(raw_points, dtype=float)
            if points.ndim != 2 or points.shape[0] < 2 or points.shape[1] != 3:
                continue
            clean_replacements[target_slice_idx] = points

        if not clean_replacements:
            return None, [], {}

        reference_by_slice = {}
        for old_cell_id in range(vtk_obj.GetNumberOfCells()):
            old_slice_idx = int(cell_slice_array.GetValue(old_cell_id))
            if old_slice_idx not in clean_replacements or old_slice_idx in reference_by_slice:
                continue
            cell = vtk_obj.GetCell(old_cell_id)
            point_id = None
            if cell is not None and cell.GetNumberOfPoints() > 0:
                point_id = cell.GetPointId(0)
            reference_by_slice[old_slice_idx] = {
                "cell_id": old_cell_id,
                "point_id": point_id,
            }

        if any(slice_idx not in reference_by_slice for slice_idx in clean_replacements):
            return None, [], {}

        point_builders = self._prepare_numeric_array_builders(
            source_data=point_data,
            skip_names={"slice_index"},
            skip_prefixes=("slices_",),
        )
        cell_builders = self._prepare_numeric_array_builders(
            source_data=cell_data,
            skip_names={"slice_index"},
            skip_prefixes=("slices_",),
        )

        new_points = vtkPoints()
        new_lines = vtkCellArray()
        point_slice_values = []
        cell_slice_values = []
        inserted_slices = set()

        for old_cell_id in range(vtk_obj.GetNumberOfCells()):
            old_slice_idx = int(cell_slice_array.GetValue(old_cell_id))
            if old_slice_idx in clean_replacements:
                if old_slice_idx in inserted_slices:
                    continue

                edited_points = clean_replacements[old_slice_idx]
                reference_ids = reference_by_slice.get(old_slice_idx, {})
                reference_cell_id = reference_ids.get("cell_id")
                reference_point_id = reference_ids.get("point_id")
                start_idx = new_points.GetNumberOfPoints()
                for point in edited_points:
                    new_points.InsertNextPoint(float(point[0]), float(point[1]), float(point[2]))
                    point_slice_values.append(old_slice_idx)
                    self._append_numeric_tuple(
                        builders=point_builders,
                        source_idx=None,
                        default_idx=reference_point_id,
                    )

                new_lines.InsertNextCell(int(edited_points.shape[0]))
                for point_id in range(start_idx, start_idx + int(edited_points.shape[0])):
                    new_lines.InsertCellPoint(point_id)

                cell_slice_values.append(old_slice_idx)
                self._append_numeric_tuple(
                    builders=cell_builders,
                    source_idx=None,
                    default_idx=reference_cell_id,
                )
                inserted_slices.add(old_slice_idx)
                continue

            cell = vtk_obj.GetCell(old_cell_id)
            if cell is None:
                continue

            n_pts = cell.GetNumberOfPoints()
            if n_pts < 2:
                continue

            start_idx = new_points.GetNumberOfPoints()
            for point_idx in range(n_pts):
                old_point_id = cell.GetPointId(point_idx)
                point = vtk_obj.GetPoint(old_point_id)
                new_points.InsertNextPoint(float(point[0]), float(point[1]), float(point[2]))
                if point_slice_array is not None:
                    point_slice_values.append(int(point_slice_array.GetValue(old_point_id)))
                else:
                    point_slice_values.append(old_slice_idx)
                self._append_numeric_tuple(
                    builders=point_builders,
                    source_idx=old_point_id,
                    default_idx=None,
                )

            new_lines.InsertNextCell(n_pts)
            for point_id in range(start_idx, start_idx + n_pts):
                new_lines.InsertCellPoint(point_id)

            cell_slice_values.append(old_slice_idx)
            self._append_numeric_tuple(
                builders=cell_builders,
                source_idx=old_cell_id,
                default_idx=None,
            )

        if (
            inserted_slices != set(clean_replacements.keys())
            or new_points.GetNumberOfPoints() == 0
            or new_lines.GetNumberOfCells() == 0
        ):
            return None, [], {}

        rebuilt_line = PolyLine()
        rebuilt_line.SetPoints(new_points)
        rebuilt_line.SetLines(new_lines)

        for _source_array, target_array in point_builders:
            rebuilt_line.GetPointData().AddArray(target_array)
        for _source_array, target_array in cell_builders:
            rebuilt_line.GetCellData().AddArray(target_array)
        self._copy_field_data_arrays(
            source_data=field_data,
            target_data=rebuilt_line.GetFieldData(),
        )

        point_slice_out = vtkIntArray()
        point_slice_out.SetName("slice_index")
        point_slice_out.SetNumberOfComponents(1)
        for value in point_slice_values:
            point_slice_out.InsertNextValue(int(value))
        rebuilt_line.GetPointData().AddArray(point_slice_out)

        cell_slice_out = vtkIntArray()
        cell_slice_out.SetName("slice_index")
        cell_slice_out.SetNumberOfComponents(1)
        for value in cell_slice_values:
            cell_slice_out.InsertNextValue(int(value))
        rebuilt_line.GetCellData().AddArray(cell_slice_out)

        slice_indices = sorted({int(value) for value in cell_slice_values if int(value) >= 0})
        slice_to_cell_index = {}
        for new_cell_idx, value in enumerate(cell_slice_values):
            value = int(value)
            if value not in slice_to_cell_index:
                slice_to_cell_index[value] = new_cell_idx

        self._ensure_slice_index_property_metadata(
            vtk_obj=rebuilt_line,
            slice_indices=slice_indices,
        )
        rebuilt_line.Modified()
        return rebuilt_line, slice_indices, slice_to_cell_index

    def _build_multipart_vtk_with_replaced_slice(
        self, vtk_obj=None, slice_idx=None, edited_points=None
    ):
        """Return a multipart PolyLine where one slice is replaced with edited geometry."""
        return self._build_multipart_vtk_with_replaced_slices(
            vtk_obj=vtk_obj,
            edited_points_by_slice={slice_idx: edited_points},
        )

    def _prompt_multipart_edit_propagation_slices(self, selection=None, current_slice_idx=None):
        """Ask whether the current edit should be copied to additional slices and return matching targets."""
        if selection is None:
            return []

        available_slices = sorted({int(idx) for idx in selection.get("available_slices", [])})
        if not available_slices:
            return []

        apply_to_range = options_dialog(
            title="Edit line",
            message=(
                "Do you want to apply this edited line to other slices of the same multipart "
                "entity?"
            ),
            yes_role="Yes",
            no_role="No",
        )
        if apply_to_range != 0:
            return []

        current_slice_idx = int(current_slice_idx)
        range_in = multiple_input_dialog(
            title=f"Apply Edit To Slice Range ({available_slices[0]}-{available_slices[-1]})",
            input_dict={
                "slice_from": ["Apply from slice:", current_slice_idx],
                "slice_to": ["Apply to slice:", current_slice_idx],
            },
        )
        if range_in is None:
            return []

        slice_from = int(range_in["slice_from"])
        slice_to = int(range_in["slice_to"])
        if slice_from > slice_to:
            slice_from, slice_to = slice_to, slice_from

        return [
            slice_idx
            for slice_idx in available_slices
            if slice_from <= slice_idx <= slice_to
        ]

    def _finalize_standard_line_edit(self, uid=None, editor=None):
        """Apply a standard line edit result to a single geometry uid."""
        try:
            self.plotter.untrack_click_position(side="right")
        except Exception:
            pass
        self._end_slice_line_edit_pick_mode()

        try:
            traced_pld = (
                editor.GetContourRepresentation().GetContourRepresentationAsPolyData()
            )
        except Exception:
            traced_pld = None

        try:
            if editor is not None:
                editor.EnabledOff()
        except Exception:
            pass

        if traced_pld is None or traced_pld.GetNumberOfPoints() < 2:
            self.clear_selection()
            freeze_gui_off(self)
            return

        points = np.array(traced_pld.GetPoints().GetData(), dtype=float)
        snapped_points = self.snap_points_to_slice(points, points_are_display_coords=True)

        vtk_obj = PolyLine()
        vtk_obj.points = snapped_points
        vtk_obj.auto_cells()

        self.parent.geol_coll.replace_vtk(uid=uid, vtk_object=vtk_obj)

        if uid in getattr(self, "interpretation_lines", {}):
            self._store_single_slice_interpretation_metadata(
                uid=uid,
                slice_info=self.interpretation_lines[uid],
            )
            self.set_actor_visibility(uid, True)

        self.plotter.render()
        self.clear_selection()
        freeze_gui_off(self)

    def _finalize_multipart_line_edit(self, selection=None, editor=None):
        """Rewrite the active slice of a multipart propagated line after editing."""
        try:
            self.plotter.untrack_click_position(side="right")
        except Exception:
            pass
        self._end_slice_line_edit_pick_mode()

        try:
            traced_pld = (
                editor.GetContourRepresentation().GetContourRepresentationAsPolyData()
            )
        except Exception:
            traced_pld = None

        try:
            if editor is not None:
                editor.EnabledOff()
        except Exception:
            pass

        if traced_pld is None or traced_pld.GetNumberOfPoints() < 2 or selection is None:
            self.clear_selection()
            freeze_gui_off(self)
            return

        uid = selection["uid"]
        entity_kind = selection["entity_kind"]
        entity_info = selection["entity_info"]
        slice_idx = int(self.current_slice_index)

        points = np.array(traced_pld.GetPoints().GetData(), dtype=float)
        snapped_points = self.snap_points_to_slice(points, points_are_display_coords=True)
        current_vtk = self.parent.geol_coll.get_uid_vtk_obj(uid)
        replacement_points_by_slice = {slice_idx: snapped_points}

        target_slices = self._prompt_multipart_edit_propagation_slices(
            selection=selection,
            current_slice_idx=slice_idx,
        )
        target_slices = sorted({int(idx) for idx in target_slices})
        if target_slices:
            affine = self._get_seismic_axis_vectors()
            template_uv = self._world_points_to_slice_uv(
                points=snapped_points,
                slice_idx=slice_idx,
                axis=entity_info.get("axis", self.current_axis),
                affine=affine,
            )
            if template_uv is None:
                message_dialog(
                    title="Edit line",
                    message=(
                        "The edited line was saved on the current slice, but it could not be "
                        "projected to the requested slice range."
                    ),
                )
            else:
                for target_slice_idx in target_slices:
                    if target_slice_idx == slice_idx:
                        continue
                    target_points = self._slice_uv_to_world_points(
                        slice_uv=template_uv,
                        slice_idx=target_slice_idx,
                        axis=entity_info.get("axis", self.current_axis),
                        affine=affine,
                    )
                    if target_points is None:
                        continue
                    replacement_points_by_slice[int(target_slice_idx)] = target_points

        new_vtk, slice_indices, _slice_to_cell_index = self._build_multipart_vtk_with_replaced_slices(
            vtk_obj=current_vtk,
            edited_points_by_slice=replacement_points_by_slice,
        )
        if new_vtk is None:
            message_dialog(
                title="Edit line",
                message="Could not rewrite the edited slice back into the multipart line.",
            )
            self.clear_selection()
            freeze_gui_off(self)
            return

        self._remove_filtered_actor(f"multipart_slice_{uid}")
        self._remove_filtered_actor(f"multipart_fault_slice_{uid}")
        self._remove_raw_actor_for_uid(uid)
        self.parent.geol_coll.replace_vtk(uid=uid, vtk_object=new_vtk)
        self.scan_and_index_single_horizon(uid)

        seed_slice = entity_info.get("seed_slice")
        if uid in getattr(self, "multipart_horizons", {}) and seed_slice in slice_indices:
            self.multipart_horizons[uid]["seed_slice"] = int(seed_slice)
        if uid in getattr(self, "multipart_faults", {}) and seed_slice in slice_indices:
            self.multipart_faults[uid]["seed_slice"] = int(seed_slice)

        self._mark_slice_visibility_dirty()
        if entity_kind == "horizon":
            self.update_multipart_horizon_visibility(uid)
        else:
            self.update_multipart_fault_visibility(uid)
        self.plotter.render()

        self.print_terminal(
            f"Edited multipart {entity_kind} {uid[:8]}... on slice {slice_idx}: "
            f"{len(points)} control points updated."
        )
        if len(replacement_points_by_slice) > 1:
            propagated_slices = sorted(replacement_points_by_slice.keys())
            self.print_terminal(
                f"Applied the same edit to slices {propagated_slices[0]}-{propagated_slices[-1]} "
                f"({len(propagated_slices)} slices total)."
            )
        self.clear_selection()
        freeze_gui_off(self)

    @freeze_gui_on
    def edit_selected_line(self):
        """Edit a visible interpretation line or the current slice of a multipart line."""
        selected_uids = [
            uid
            for uid in list(getattr(self.parent, "selected_uids", []) or [])
            if uid in set(self.parent.geol_coll.get_uids)
        ]
        if not selected_uids:
            self.print_terminal(" -- No input data selected -- ")
            freeze_gui_off(self)
            return

        sel_uid = selected_uids[0]
        selection = self._resolve_multipart_entity_for_edit(
            uid=sel_uid,
            action_title="Edit line",
            show_messages=False,
        )

        if selection is not None:
            entity_info = selection["entity_info"]
            if entity_info.get("seismic_uid") != self.current_seismic_uid or entity_info.get("axis") != self.current_axis:
                message_dialog(
                    title="Edit line",
                    message="Show the propagated line on its matching seismic and axis before editing it.",
                )
                freeze_gui_off(self)
                return
            if self.current_slice_index not in selection["available_slices"]:
                message_dialog(
                    title="Edit line",
                    message="Move to a slice where the selected propagated line is visible before editing it.",
                )
                freeze_gui_off(self)
                return

            actor = self._get_visible_line_actor_for_uid(sel_uid)
            if actor is None:
                message_dialog(
                    title="Edit line",
                    message="The selected propagated line is not currently visible in the interpretation view.",
                )
                freeze_gui_off(self)
                return

            data = actor.GetMapper().GetInput()
            editor_data = self._build_editor_input_polydata(data=data)
            self._begin_slice_line_edit_pick_mode()
            editor = Editor(self)
            editor.EnabledOn()
            editor.initialize(editor_data, "edit")
            self.plotter.track_click_position(
                side="right",
                callback=lambda event: self._finalize_multipart_line_edit(
                    selection=selection,
                    editor=editor,
                ),
            )
            return

        try:
            topology = self.parent.geol_coll.get_uid_topology(sel_uid)
        except Exception:
            topology = None
        if topology != "PolyLine":
            self.print_terminal(" -- Selected data is not a line -- ")
            freeze_gui_off(self)
            return

        actor = self._get_visible_line_actor_for_uid(sel_uid)
        if actor is None:
            self.print_terminal(" -- Selected line is not visible in the current interpretation slice -- ")
            freeze_gui_off(self)
            return

        data = actor.GetMapper().GetInput()
        editor_data = self._build_editor_input_polydata(data=data)
        self._begin_slice_line_edit_pick_mode()
        editor = Editor(self)
        editor.EnabledOn()
        editor.initialize(editor_data, "edit")
        self.plotter.track_click_position(
            side="right",
            callback=lambda event: self._finalize_standard_line_edit(
                uid=sel_uid,
                editor=editor,
            ),
        )

    def _build_propagated_entity_name(self, seed_uid, slice_indices, fallback_name):
        """
        Build a propagated entity name from the seed interpretation name.

        The suffix uses the actual propagated slice interval, formatted as
        ``(start-end)`` so repeated tracking keeps the correct positioning.
        """
        base_name = fallback_name
        try:
            seed_name = self.parent.geol_coll.get_uid_name(seed_uid)
            if isinstance(seed_name, str) and seed_name.strip():
                base_name = seed_name.strip()
        except Exception:
            pass

        try:
            clean = sorted({int(idx) for idx in (slice_indices or [])})
        except Exception:
            clean = []

        if isinstance(base_name, str):
            base_name = re_sub(r"\s*\(\d+\s*-\s*\d+\)\s*$", "", base_name).strip()

        if not clean:
            return base_name
        return f"{base_name} ({clean[0]}-{clean[-1]})"

    def _build_multipart_entity_dict_from_source(
        self, source_uid=None, vtk_obj=None, slice_indices=None, fallback_name="multipart"
    ):
        """Clone multipart entity metadata from an existing geology uid."""
        if not source_uid or vtk_obj is None:
            return None

        entity_dict = deepcopy(self.parent.geol_coll.entity_dict)
        entity_dict["name"] = self._build_propagated_entity_name(
            seed_uid=source_uid,
            slice_indices=slice_indices,
            fallback_name=fallback_name,
        )
        entity_dict["topology"] = "PolyLine"
        entity_dict["vtk_obj"] = vtk_obj

        for key, getter_name, default in (
            ("role", "get_uid_role", "undef"),
            ("feature", "get_uid_feature", fallback_name),
            ("scenario", "get_uid_scenario", "undef"),
            ("parent_uid", "get_uid_x_section", ""),
        ):
            try:
                entity_dict[key] = getattr(self.parent.geol_coll, getter_name)(source_uid)
            except Exception:
                entity_dict[key] = default

        try:
            entity_dict["properties_names"] = list(
                self.parent.geol_coll.get_uid_properties_names(source_uid) or []
            )
        except Exception:
            entity_dict["properties_names"] = []

        try:
            entity_dict["properties_components"] = list(
                self.parent.geol_coll.get_uid_properties_components(source_uid) or []
            )
        except Exception:
            entity_dict["properties_components"] = []

        self._ensure_slice_index_property_metadata(
            entity_dict=entity_dict,
            vtk_obj=vtk_obj,
            slice_indices=slice_indices,
        )
        return entity_dict

    def _copy_selected_numeric_arrays(
        self, source_data, target_data, selected_ids, skip_names=None, skip_prefixes=None
    ):
        """Copy numeric data arrays for a subset of tuples."""
        if source_data is None or target_data is None:
            return
        skip_names = set(skip_names or [])
        skip_prefixes = tuple(skip_prefixes or ())
        for array_idx in range(source_data.GetNumberOfArrays()):
            source_array = source_data.GetArray(array_idx)
            if source_array is None:
                continue
            array_name = source_array.GetName() or ""
            if array_name in skip_names:
                continue
            if array_name and any(array_name.startswith(prefix) for prefix in skip_prefixes):
                continue
            copied_array = source_array.NewInstance()
            copied_array.SetName(array_name)
            copied_array.SetNumberOfComponents(source_array.GetNumberOfComponents())
            copied_array.SetNumberOfTuples(len(selected_ids))
            for new_idx, old_idx in enumerate(selected_ids):
                copied_array.SetTuple(new_idx, source_array.GetTuple(old_idx))
            target_data.AddArray(copied_array)

    def _copy_field_data_arrays(self, source_data, target_data):
        """Copy field-data arrays as-is."""
        if source_data is None or target_data is None:
            return
        for array_idx in range(source_data.GetNumberOfArrays()):
            source_array = source_data.GetAbstractArray(array_idx)
            if source_array is None:
                continue
            copied_array = source_array.NewInstance()
            copied_array.DeepCopy(source_array)
            target_data.AddArray(copied_array)

    def _build_multipart_subset_vtk(self, vtk_obj=None, kept_cell_ids=None):
        """Create a new multipart PolyLine keeping only the requested cells."""
        if vtk_obj is None or not kept_cell_ids:
            return None, [], {}

        source_cell_data = vtk_obj.GetCellData()
        cell_slice_array = (
            source_cell_data.GetArray("slice_index")
            if source_cell_data is not None and source_cell_data.HasArray("slice_index")
            else None
        )

        new_points = vtkPoints()
        new_lines = vtkCellArray()
        point_map = {}
        kept_point_ids = []
        point_slice_values = []
        kept_slice_values = []

        for old_cell_id in kept_cell_ids:
            cell = vtk_obj.GetCell(old_cell_id)
            if cell is None:
                continue
            n_pts = cell.GetNumberOfPoints()
            if n_pts <= 0:
                continue

            slice_idx = (
                int(cell_slice_array.GetValue(old_cell_id))
                if cell_slice_array is not None
                else -1
            )
            new_line_point_ids = []
            for point_idx in range(n_pts):
                old_point_id = cell.GetPointId(point_idx)
                if old_point_id not in point_map:
                    new_point_id = new_points.InsertNextPoint(vtk_obj.GetPoint(old_point_id))
                    point_map[old_point_id] = new_point_id
                    kept_point_ids.append(old_point_id)
                    point_slice_values.append(slice_idx)
                new_line_point_ids.append(point_map[old_point_id])

            new_lines.InsertNextCell(len(new_line_point_ids))
            for new_point_id in new_line_point_ids:
                new_lines.InsertCellPoint(new_point_id)
            kept_slice_values.append(slice_idx)

        if new_points.GetNumberOfPoints() == 0 or new_lines.GetNumberOfCells() == 0:
            return None, [], {}

        subset_line = PolyLine()
        subset_line.SetPoints(new_points)
        subset_line.SetLines(new_lines)

        self._copy_selected_numeric_arrays(
            source_data=vtk_obj.GetPointData(),
            target_data=subset_line.GetPointData(),
            selected_ids=kept_point_ids,
            skip_names={"slice_index"},
            skip_prefixes=("slices_",),
        )
        self._copy_selected_numeric_arrays(
            source_data=vtk_obj.GetCellData(),
            target_data=subset_line.GetCellData(),
            selected_ids=kept_cell_ids,
            skip_names={"slice_index"},
            skip_prefixes=("slices_",),
        )
        self._copy_field_data_arrays(
            source_data=vtk_obj.GetFieldData(),
            target_data=subset_line.GetFieldData(),
        )

        point_slice_out = vtkIntArray()
        point_slice_out.SetName("slice_index")
        point_slice_out.SetNumberOfComponents(1)
        for slice_idx in point_slice_values:
            point_slice_out.InsertNextValue(int(slice_idx))
        subset_line.GetPointData().AddArray(point_slice_out)

        cell_slice_out = vtkIntArray()
        cell_slice_out.SetName("slice_index")
        cell_slice_out.SetNumberOfComponents(1)
        for slice_idx in kept_slice_values:
            cell_slice_out.InsertNextValue(int(slice_idx))
        subset_line.GetCellData().AddArray(cell_slice_out)

        remaining_slices = sorted({int(idx) for idx in kept_slice_values if int(idx) >= 0})
        slice_to_cell_index = {}
        for new_cell_idx, slice_idx in enumerate(kept_slice_values):
            slice_idx = int(slice_idx)
            if slice_idx not in slice_to_cell_index:
                slice_to_cell_index[slice_idx] = new_cell_idx

        self._ensure_slice_index_property_metadata(
            vtk_obj=subset_line, slice_indices=remaining_slices
        )
        subset_line.Modified()
        return subset_line, remaining_slices, slice_to_cell_index

    def _extract_multipart_branch_segments(
        self, vtk_obj=None, axis=None, entity_kind="horizon"
    ):
        """Collect per-cell geometry descriptors used to separate disconnected multipart branches."""
        if vtk_obj is None or vtk_obj.GetNumberOfCells() == 0:
            return {}

        cell_data = vtk_obj.GetCellData()
        if cell_data is None or not cell_data.HasArray("slice_index"):
            return {}

        slice_array = cell_data.GetArray("slice_index")
        _, in_plane_axes = self._get_slice_plane_axes(axis=axis)
        primary_axis = self._get_multipart_sampling_primary_axis(
            axis=axis, entity_kind=entity_kind
        )
        if primary_axis in in_plane_axes:
            primary_axis_2d = in_plane_axes.index(primary_axis)
        else:
            primary_axis_2d = 0

        segments_by_slice = {}
        for cell_idx in range(vtk_obj.GetNumberOfCells()):
            cell = vtk_obj.GetCell(cell_idx)
            if cell is None:
                continue

            n_pts = cell.GetNumberOfPoints()
            if n_pts < 2:
                continue

            points = np.array(
                [vtk_obj.GetPoint(cell.GetPointId(i)) for i in range(n_pts)], dtype=float
            )
            centroid_3d = points.mean(axis=0)
            centroid_2d = centroid_3d[list(in_plane_axes)]
            order_value = float(centroid_3d[primary_axis])
            segment = {
                "cell_id": int(cell_idx),
                "slice_idx": int(slice_array.GetValue(cell_idx)),
                "points": points,
                "centroid_2d": centroid_2d,
                "order_value": order_value,
                "primary_value": float(centroid_2d[primary_axis_2d]),
                "point_count": int(n_pts),
            }
            segments_by_slice.setdefault(segment["slice_idx"], []).append(segment)

        for slice_idx in list(segments_by_slice.keys()):
            segments_by_slice[slice_idx].sort(
                key=lambda segment: (segment["order_value"], segment["cell_id"])
            )
        return segments_by_slice

    def _estimate_multipart_branch_match_distance(self, segments_by_slice=None):
        """Estimate a stable matching distance for tracking disconnected slice branches."""
        if not segments_by_slice:
            return 0.0

        same_slice_separations = []
        for slice_segments in segments_by_slice.values():
            if len(slice_segments) < 2:
                continue
            centers = [segment["centroid_2d"] for segment in slice_segments]
            for idx in range(len(centers)):
                nearest = None
                for jdx in range(len(centers)):
                    if idx == jdx:
                        continue
                    dist = float(np.linalg.norm(centers[idx] - centers[jdx]))
                    if nearest is None or dist < nearest:
                        nearest = dist
                if nearest is not None and nearest > 0.0:
                    same_slice_separations.append(nearest)

        if same_slice_separations:
            return max(1.0e-6, float(np.median(same_slice_separations)) * 0.6)

        ordered_slices = sorted(segments_by_slice.keys())
        adjacent_motion = []
        for prev_slice, next_slice in zip(ordered_slices[:-1], ordered_slices[1:]):
            prev_segments = segments_by_slice.get(prev_slice, [])
            next_segments = segments_by_slice.get(next_slice, [])
            if not prev_segments or not next_segments:
                continue
            for segment in next_segments:
                nearest = min(
                    float(
                        np.linalg.norm(
                            segment["centroid_2d"] - prev_segment["centroid_2d"]
                        )
                    )
                    for prev_segment in prev_segments
                )
                if nearest > 0.0:
                    adjacent_motion.append(nearest)

        if adjacent_motion:
            return max(1.0e-6, float(np.median(adjacent_motion)) * 2.0)
        return 0.0

    def _build_multipart_branch_name(
        self,
        seed_uid=None,
        slice_indices=None,
        branch_index=1,
        branch_count=1,
        fallback_name="multipart",
    ):
        """Build a stable name for one separated branch of a multipart interpretation entity."""
        base_name = self._build_propagated_entity_name(
            seed_uid=seed_uid,
            slice_indices=[],
            fallback_name=fallback_name,
        )
        if branch_count > 1:
            base_name = re_sub(r"\s+part\s+\d+\s*$", "", base_name, flags=re_IGNORECASE)
            base_name = f"{base_name} part {int(branch_index)}"

        clean = sorted({int(idx) for idx in (slice_indices or [])})
        if not clean:
            return base_name
        return f"{base_name} ({clean[0]}-{clean[-1]})"

    def _detect_disconnected_multipart_branches(
        self,
        vtk_obj=None,
        axis=None,
        entity_kind="horizon",
        max_slice_gap=2,
        match_distance=0.0,
    ):
        """Group same-slice disconnected cells into continuous multipart branches across slices."""
        segments_by_slice = self._extract_multipart_branch_segments(
            vtk_obj=vtk_obj,
            axis=axis,
            entity_kind=entity_kind,
        )
        if not segments_by_slice:
            return [], {}

        max_slice_gap = max(0, int(max_slice_gap))
        auto_match_distance = self._estimate_multipart_branch_match_distance(
            segments_by_slice=segments_by_slice
        )
        if match_distance is None or float(match_distance) <= 0.0:
            match_distance = auto_match_distance
        else:
            match_distance = float(match_distance)

        branches = []
        next_branch_id = 0
        ordered_slices = sorted(segments_by_slice.keys())

        for slice_idx in ordered_slices:
            current_segments = list(segments_by_slice.get(slice_idx, []))
            if not current_segments:
                continue

            eligible_branch_ids = [
                branch["branch_id"]
                for branch in branches
                if slice_idx - branch["last_slice_idx"] <= max_slice_gap + 1
            ]
            branch_map = {branch["branch_id"]: branch for branch in branches}
            matched_segment_ids = set()
            matched_branch_ids = set()

            if eligible_branch_ids and current_segments:
                branch_rows = [branch_map[branch_id] for branch_id in eligible_branch_ids]
                cost_matrix = np.full(
                    (len(branch_rows), len(current_segments)),
                    fill_value=1.0e9,
                    dtype=float,
                )
                raw_center_deltas = {}

                for row_idx, branch in enumerate(branch_rows):
                    for col_idx, segment in enumerate(current_segments):
                        center_delta = float(
                            np.linalg.norm(
                                segment["centroid_2d"] - branch["last_centroid_2d"]
                            )
                        )
                        order_delta = abs(
                            float(segment["order_value"]) - float(branch["last_order_value"])
                        )
                        slice_gap = max(0, int(slice_idx - branch["last_slice_idx"] - 1))
                        gap_penalty = slice_gap * max(match_distance, 1.0)
                        raw_center_deltas[(row_idx, col_idx)] = center_delta
                        cost_matrix[row_idx, col_idx] = center_delta + 0.35 * order_delta + gap_penalty

                row_ids, col_ids = linear_sum_assignment(cost_matrix)
                for row_idx, col_idx in zip(row_ids, col_ids):
                    center_delta = raw_center_deltas[(row_idx, col_idx)]
                    allow_match = (
                        match_distance <= 0.0 or center_delta <= float(match_distance)
                    )
                    if not allow_match:
                        continue

                    branch = branch_rows[row_idx]
                    segment = current_segments[col_idx]
                    branch["segments"].append(segment)
                    branch["last_slice_idx"] = int(slice_idx)
                    branch["last_centroid_2d"] = np.asarray(
                        segment["centroid_2d"], dtype=float
                    )
                    branch["last_order_value"] = float(segment["order_value"])
                    matched_segment_ids.add(segment["cell_id"])
                    matched_branch_ids.add(branch["branch_id"])

            for segment in current_segments:
                if segment["cell_id"] in matched_segment_ids:
                    continue
                branches.append(
                    {
                        "branch_id": next_branch_id,
                        "segments": [segment],
                        "last_slice_idx": int(slice_idx),
                        "last_centroid_2d": np.asarray(segment["centroid_2d"], dtype=float),
                        "last_order_value": float(segment["order_value"]),
                    }
                )
                next_branch_id += 1

        branch_payloads = []
        for branch in branches:
            cell_ids = [segment["cell_id"] for segment in branch["segments"]]
            if not cell_ids:
                continue

            slice_indices = sorted(
                {int(segment["slice_idx"]) for segment in branch["segments"]}
            )
            centroid_stack = np.vstack(
                [np.asarray(segment["centroid_2d"], dtype=float) for segment in branch["segments"]]
            )
            branch_payloads.append(
                {
                    "branch_id": int(branch["branch_id"]),
                    "cell_ids": cell_ids,
                    "slice_indices": slice_indices,
                    "cell_count": len(cell_ids),
                    "mean_order_value": float(
                        np.mean(
                            [
                                float(segment["order_value"])
                                for segment in branch["segments"]
                            ]
                        )
                    ),
                    "mean_centroid_2d": centroid_stack.mean(axis=0),
                }
            )

        branch_payloads.sort(
            key=lambda payload: (
                -payload["cell_count"],
                payload["slice_indices"][0] if payload["slice_indices"] else 10**9,
                payload["mean_order_value"],
            )
        )
        for branch_index, payload in enumerate(branch_payloads, start=1):
            payload["branch_index"] = branch_index

        return branch_payloads, {
            "auto_match_distance": float(auto_match_distance),
            "used_match_distance": float(match_distance),
            "slice_count": len(ordered_slices),
            "max_parts_per_slice": max(
                len(slice_segments) for slice_segments in segments_by_slice.values()
            ),
            "multi_part_slice_count": int(
                sum(1 for slice_segments in segments_by_slice.values() if len(slice_segments) > 1)
            ),
            "branch_count": len(branch_payloads),
        }

    def _get_slice_plane_axes(self, axis=None):
        """Return the normal and in-plane coordinate indices for a slice axis."""
        axis = axis or self.current_axis
        if axis == "Inline":
            return 0, (1, 2)
        if axis == "Crossline":
            return 1, (0, 2)
        return 2, (0, 1)

    def _resolve_polyline_axis_for_simplify(self, uid=None, vtk_obj=None):
        """Resolve the slice axis used to simplify interpretation polylines."""
        if uid in getattr(self, "multipart_horizons", {}):
            axis = self.multipart_horizons[uid].get("axis")
            if axis:
                return axis
        if uid in getattr(self, "multipart_faults", {}):
            axis = self.multipart_faults[uid].get("axis")
            if axis:
                return axis

        slice_info = self._extract_single_slice_interpretation_metadata(
            uid=uid, vtk_obj=vtk_obj
        )
        if slice_info and slice_info.get("axis"):
            return slice_info["axis"]

        try:
            field_data = vtk_obj.GetFieldData() if vtk_obj is not None else None
            if field_data is not None:
                for array_name in ("slice_axis", "single_slice_axis"):
                    if not field_data.HasArray(array_name):
                        continue
                    axis_array = field_data.GetAbstractArray(array_name)
                    if axis_array and axis_array.GetNumberOfValues() > 0:
                        axis = axis_array.GetValue(0)
                        if axis:
                            return axis
        except Exception:
            pass

        if vtk_obj is not None:
            try:
                bounds = vtk_obj.GetBounds()
                x_range = abs(bounds[1] - bounds[0])
                y_range = abs(bounds[3] - bounds[2])
                z_range = abs(bounds[5] - bounds[4])
                range_by_axis = {
                    "Inline": x_range,
                    "Crossline": y_range,
                    "Z-slice": z_range,
                }
                return min(range_by_axis, key=range_by_axis.get)
            except Exception:
                pass

        return self.current_axis

    def _simplify_polyline_cell_points(self, points=None, tolerance=0.1, axis=None):
        """Simplify one polyline cell in the correct slice plane."""
        clean_points, _source_s, keep_mask = self._prepare_polyline_sampling(points)
        if clean_points is None or keep_mask is None:
            return None

        normal_axis, in_plane_axes = self._get_slice_plane_axes(axis=axis)
        in_plane_points = clean_points[:, list(in_plane_axes)]
        if in_plane_points.shape[0] < 2:
            return None

        simplified_uv = in_plane_points
        if tolerance > 0.0 and in_plane_points.shape[0] > 2:
            shp_line_in = shp_linestring(in_plane_points)
            shp_line_out = shp_line_in.simplify(
                float(tolerance), preserve_topology=False
            )
            if shp_line_out is None or shp_line_out.is_empty:
                simplified_uv = np.vstack((in_plane_points[0], in_plane_points[-1]))
            elif hasattr(shp_line_out, "coords"):
                simplified_uv = np.asarray(shp_line_out.coords, dtype=float)
            elif hasattr(shp_line_out, "geoms"):
                candidate_coords = [
                    np.asarray(geom.coords, dtype=float)
                    for geom in shp_line_out.geoms
                    if hasattr(geom, "coords") and len(geom.coords) >= 2
                ]
                if candidate_coords:
                    simplified_uv = max(candidate_coords, key=len)

        if simplified_uv.ndim != 2 or simplified_uv.shape[0] < 2:
            simplified_uv = np.vstack((in_plane_points[0], in_plane_points[-1]))

        if simplified_uv.shape[0] > 1:
            keep_out = np.ones(simplified_uv.shape[0], dtype=bool)
            keep_out[1:] = (
                np.linalg.norm(np.diff(simplified_uv, axis=0), axis=1) > 1.0e-9
            )
            simplified_uv = simplified_uv[keep_out]
        if simplified_uv.shape[0] < 2:
            simplified_uv = np.vstack((in_plane_points[0], in_plane_points[-1]))

        source_indices = []
        search_start = 0
        for out_uv in simplified_uv:
            candidate_points = in_plane_points[search_start:]
            if candidate_points.size == 0:
                source_idx = in_plane_points.shape[0] - 1
            else:
                distances = np.linalg.norm(candidate_points - out_uv, axis=1)
                source_idx = search_start + int(np.argmin(distances))
            source_indices.append(source_idx)
            search_start = min(source_idx, in_plane_points.shape[0] - 1)

        if len(source_indices) < 2:
            source_indices = [0, in_plane_points.shape[0] - 1]
            simplified_uv = np.vstack((in_plane_points[0], in_plane_points[-1]))

        simplified_points = np.zeros((simplified_uv.shape[0], 3), dtype=float)
        simplified_points[:, in_plane_axes[0]] = simplified_uv[:, 0]
        simplified_points[:, in_plane_axes[1]] = simplified_uv[:, 1]
        simplified_points[:, normal_axis] = float(
            np.median(clean_points[:, normal_axis])
        )

        return {
            "points": simplified_points,
            "keep_mask": keep_mask,
            "source_indices": source_indices,
        }

    def _build_simplified_polyline_vtk(self, vtk_obj=None, tolerance=0.1, axis=None):
        """Simplify all cells of a PolyLine while preserving interpretation metadata."""
        if vtk_obj is None or vtk_obj.GetNumberOfCells() == 0:
            return None, [], {}, {}

        from vtk import vtkCellArray, vtkIntArray, vtkPoints

        source_point_data = vtk_obj.GetPointData()
        source_cell_data = vtk_obj.GetCellData()
        source_field_data = vtk_obj.GetFieldData()

        point_slice_array = (
            source_point_data.GetArray("slice_index")
            if source_point_data is not None and source_point_data.HasArray("slice_index")
            else None
        )
        cell_slice_array = (
            source_cell_data.GetArray("slice_index")
            if source_cell_data is not None and source_cell_data.HasArray("slice_index")
            else None
        )

        new_points = vtkPoints()
        new_lines = vtkCellArray()
        selected_point_ids = []
        selected_cell_ids = []
        point_slice_values = []
        cell_slice_values = []
        old_total_points = 0

        for cell_idx in range(vtk_obj.GetNumberOfCells()):
            cell = vtk_obj.GetCell(cell_idx)
            if cell is None:
                continue

            n_pts = cell.GetNumberOfPoints()
            if n_pts < 2:
                continue

            point_ids = [cell.GetPointId(i) for i in range(n_pts)]
            raw_points = np.array(
                [vtk_obj.GetPoint(point_id) for point_id in point_ids], dtype=float
            )
            old_total_points += int(n_pts)

            simplified = self._simplify_polyline_cell_points(
                points=raw_points,
                tolerance=tolerance,
                axis=axis,
            )
            if simplified is None:
                continue

            clean_point_ids = np.asarray(point_ids, dtype=int)[simplified["keep_mask"]]
            simplified_points = simplified["points"]
            source_indices = simplified["source_indices"]
            if simplified_points.shape[0] < 2 or clean_point_ids.size < 2:
                continue

            start_idx = new_points.GetNumberOfPoints()
            for local_idx, point in enumerate(simplified_points):
                new_points.InsertNextPoint(float(point[0]), float(point[1]), float(point[2]))
                source_point_id = int(clean_point_ids[source_indices[local_idx]])
                selected_point_ids.append(source_point_id)

                if point_slice_array is not None:
                    point_slice_values.append(int(point_slice_array.GetValue(source_point_id)))
                elif cell_slice_array is not None:
                    point_slice_values.append(int(cell_slice_array.GetValue(cell_idx)))

            new_lines.InsertNextCell(simplified_points.shape[0])
            for point_id in range(start_idx, start_idx + simplified_points.shape[0]):
                new_lines.InsertCellPoint(point_id)

            selected_cell_ids.append(cell_idx)
            if cell_slice_array is not None:
                cell_slice_values.append(int(cell_slice_array.GetValue(cell_idx)))

        if new_points.GetNumberOfPoints() == 0 or new_lines.GetNumberOfCells() == 0:
            return None, [], {}, {}

        simplified_line = PolyLine()
        simplified_line.SetPoints(new_points)
        simplified_line.SetLines(new_lines)

        self._copy_selected_numeric_arrays(
            source_data=source_point_data,
            target_data=simplified_line.GetPointData(),
            selected_ids=selected_point_ids,
            skip_names={"slice_index"},
            skip_prefixes=("slices_",),
        )
        self._copy_selected_numeric_arrays(
            source_data=source_cell_data,
            target_data=simplified_line.GetCellData(),
            selected_ids=selected_cell_ids,
            skip_names={"slice_index"},
            skip_prefixes=("slices_",),
        )
        self._copy_field_data_arrays(
            source_data=source_field_data,
            target_data=simplified_line.GetFieldData(),
        )

        if point_slice_values:
            point_slice_out = vtkIntArray()
            point_slice_out.SetName("slice_index")
            point_slice_out.SetNumberOfComponents(1)
            for slice_idx in point_slice_values:
                point_slice_out.InsertNextValue(int(slice_idx))
            simplified_line.GetPointData().AddArray(point_slice_out)

        if cell_slice_values:
            cell_slice_out = vtkIntArray()
            cell_slice_out.SetName("slice_index")
            cell_slice_out.SetNumberOfComponents(1)
            for slice_idx in cell_slice_values:
                cell_slice_out.InsertNextValue(int(slice_idx))
            simplified_line.GetCellData().AddArray(cell_slice_out)

        slice_indices = sorted(
            {
                int(slice_idx)
                for slice_idx in (cell_slice_values or point_slice_values)
                if int(slice_idx) >= 0
            }
        )
        slice_to_cell_index = {}
        for new_cell_idx, slice_idx in enumerate(cell_slice_values):
            slice_idx = int(slice_idx)
            if slice_idx not in slice_to_cell_index:
                slice_to_cell_index[slice_idx] = new_cell_idx

        if slice_indices:
            self._ensure_slice_index_property_metadata(
                vtk_obj=simplified_line, slice_indices=slice_indices
            )
        simplified_line.Modified()

        stats = {
            "old_total_points": int(old_total_points),
            "new_total_points": int(new_points.GetNumberOfPoints()),
            "cell_count": int(new_lines.GetNumberOfCells()),
        }
        return simplified_line, slice_indices, slice_to_cell_index, stats

    def _prepare_polyline_sampling(self, points):
        """Remove duplicate vertices and build cumulative arclength coordinates."""
        clean_points = np.asarray(points, dtype=float)
        if clean_points.ndim != 2 or clean_points.shape[0] < 2:
            return None, None, None

        keep_mask = np.ones(clean_points.shape[0], dtype=bool)
        if clean_points.shape[0] > 1:
            seg_lengths = np.linalg.norm(np.diff(clean_points, axis=0), axis=1)
            keep_mask[1:] = seg_lengths > 1.0e-9

        clean_points = clean_points[keep_mask]
        if clean_points.shape[0] < 2:
            return None, None, keep_mask

        seg_lengths = np.linalg.norm(np.diff(clean_points, axis=0), axis=1)
        cum_length = np.concatenate(([0.0], np.cumsum(seg_lengths)))
        if cum_length[-1] <= 0:
            return None, None, keep_mask
        return clean_points, cum_length, keep_mask

    def _sample_polyline_values(self, values, source_s, target_s):
        """Interpolate point coordinates or point-data tuples along arclength."""
        values = np.asarray(values, dtype=float)
        squeeze = values.ndim == 1
        if squeeze:
            values = values[:, None]

        sampled = np.empty((len(target_s), values.shape[1]), dtype=float)
        for comp_idx in range(values.shape[1]):
            sampled[:, comp_idx] = np.interp(target_s, source_s, values[:, comp_idx])

        if squeeze:
            return sampled[:, 0]
        return sampled

    def _project_regularized_stack_to_slice_planes(
        self, point_stack=None, cells=None, axis=None, reference_stack=None
    ):
        """Project each regularized slice row back to its source slice plane."""
        if point_stack is None:
            return None

        stack = np.asarray(point_stack, dtype=float).copy()
        if stack.ndim != 3 or stack.shape[0] == 0:
            return stack

        axis = axis or self.current_axis
        affine = self._get_seismic_axis_vectors()
        normal_axis, _in_plane_axes = self._get_slice_plane_axes(axis=axis)

        for row_idx in range(stack.shape[0]):
            slice_idx = None
            if cells is not None and row_idx < len(cells):
                try:
                    slice_idx = int(cells[row_idx]["slice_idx"])
                except Exception:
                    slice_idx = None

            if affine is not None and slice_idx is not None:
                plane_info = self._get_slice_plane_from_affine(
                    slice_idx=slice_idx,
                    affine=affine,
                    axis=axis,
                )
                if plane_info is not None:
                    center, normal, _row_vec, _col_vec, _dims = plane_info
                    try:
                        stack[row_idx, :, :] = self._project_points_to_plane(
                            stack[row_idx, :, :], center, normal
                        )
                        continue
                    except Exception:
                        pass

            if reference_stack is not None and row_idx < len(reference_stack):
                try:
                    target_coord = float(
                        np.mean(np.asarray(reference_stack[row_idx], dtype=float)[:, normal_axis])
                    )
                    stack[row_idx, :, normal_axis] = target_coord
                except Exception:
                    pass

        return stack

    def _apply_gridded_regularization(
        self,
        point_stack=None,
        cells=None,
        axis=None,
        smooth_sigma=1.0,
        preserve_slice_indices=None,
    ):
        """
        Enforce a smoother tensor-like lattice by regularizing the cross-slice columns
        after row-wise slice resampling, then projecting every row back to its slice plane.
        """
        if point_stack is None:
            return None

        base_stack = np.asarray(point_stack, dtype=float)
        if base_stack.ndim != 3 or base_stack.shape[0] < 2 or base_stack.shape[1] < 2:
            return base_stack

        axis = axis or self.current_axis
        keep_original = {int(slice_idx) for slice_idx in (preserve_slice_indices or [])}
        normal_axis, in_plane_axes = self._get_slice_plane_axes(axis=axis)
        grid_sigma = max(float(smooth_sigma), 0.75)

        gridded_stack = np.asarray(base_stack, dtype=float).copy()
        row_count, col_count, _coord_count = gridded_stack.shape

        # Regularize the "perpendicular" column curves so adjacent slices share
        # more consistent correspondences before any surface interpolation.
        for col_idx in range(col_count):
            column_curve = gridded_stack[:, col_idx, :]
            clean_points, source_s, _keep_mask = self._prepare_polyline_sampling(column_curve)
            if clean_points is None or source_s is None:
                continue

            target_s = np.linspace(0.0, source_s[-1], row_count)
            column_uniform = self._sample_polyline_values(
                clean_points, source_s, target_s
            )
            if grid_sigma > 0.0 and row_count > 2:
                for coord_idx in in_plane_axes:
                    column_uniform[:, coord_idx] = ndimage.gaussian_filter1d(
                        column_uniform[:, coord_idx],
                        sigma=grid_sigma,
                        axis=0,
                        mode="nearest",
                    )
            if row_count >= 2:
                column_uniform[0, :] = column_curve[0, :]
                column_uniform[-1, :] = column_curve[-1, :]
            gridded_stack[:, col_idx, :] = column_uniform

        # Add a light along-line smoothing pass so the first/last column boundaries
        # and intermediate rows form cleaner bands for downstream Delaunay meshing.
        row_sigma = min(max(grid_sigma * 0.35, 0.0), 1.0)
        if row_sigma > 0.0 and col_count > 2:
            for row_idx in range(row_count):
                row_curve = gridded_stack[row_idx, :, :].copy()
                for coord_idx in in_plane_axes:
                    gridded_stack[row_idx, :, coord_idx] = ndimage.gaussian_filter1d(
                        row_curve[:, coord_idx],
                        sigma=row_sigma,
                        axis=0,
                        mode="nearest",
                    )
                gridded_stack[row_idx, 0, :] = row_curve[0, :]
                gridded_stack[row_idx, -1, :] = row_curve[-1, :]

        gridded_stack[:, :, normal_axis] = base_stack[:, :, normal_axis]
        gridded_stack = self._project_regularized_stack_to_slice_planes(
            point_stack=gridded_stack,
            cells=cells,
            axis=axis,
            reference_stack=base_stack,
        )

        # Re-impose uniform row sampling after the column pass so each slice remains
        # evenly sampled and directly usable as a clean multipart line set.
        for row_idx in range(row_count):
            slice_idx = None
            if cells is not None and row_idx < len(cells):
                slice_idx = int(cells[row_idx]["slice_idx"])
            if slice_idx in keep_original:
                gridded_stack[row_idx, :, :] = base_stack[row_idx, :, :]
                continue

            clean_points, source_s, _keep_mask = self._prepare_polyline_sampling(
                gridded_stack[row_idx, :, :]
            )
            if clean_points is None or source_s is None:
                gridded_stack[row_idx, :, :] = base_stack[row_idx, :, :]
                continue

            target_s = np.linspace(0.0, source_s[-1], col_count)
            row_uniform = self._sample_polyline_values(clean_points, source_s, target_s)
            gridded_stack[row_idx, :, :] = row_uniform

        gridded_stack[:, :, normal_axis] = base_stack[:, :, normal_axis]
        gridded_stack = self._project_regularized_stack_to_slice_planes(
            point_stack=gridded_stack,
            cells=cells,
            axis=axis,
            reference_stack=base_stack,
        )

        for row_idx in range(row_count):
            slice_idx = None
            if cells is not None and row_idx < len(cells):
                slice_idx = int(cells[row_idx]["slice_idx"])
            if slice_idx in keep_original:
                gridded_stack[row_idx, :, :] = base_stack[row_idx, :, :]

        return gridded_stack

    def _build_grid_polyline_from_stack(self, point_stack=None):
        """Build a true grid PolyLine containing both row and column polylines."""
        if point_stack is None:
            return None

        stack = np.asarray(point_stack, dtype=float)
        if stack.ndim != 3 or stack.shape[0] < 2 or stack.shape[1] < 2:
            return None

        from vtk import vtkCellArray, vtkPoints

        row_count, col_count, _coord_count = stack.shape
        vtk_points = vtkPoints()
        for row_idx in range(row_count):
            for col_idx in range(col_count):
                point = stack[row_idx, col_idx]
                vtk_points.InsertNextPoint(
                    float(point[0]), float(point[1]), float(point[2])
                )

        vtk_lines = vtkCellArray()

        # Row polylines: the regularized parallel slice traces.
        for row_idx in range(row_count):
            vtk_lines.InsertNextCell(col_count)
            for col_idx in range(col_count):
                vtk_lines.InsertCellPoint(row_idx * col_count + col_idx)

        # Column polylines: perpendicular connectors completing the grid.
        for col_idx in range(col_count):
            vtk_lines.InsertNextCell(row_count)
            for row_idx in range(row_count):
                vtk_lines.InsertCellPoint(row_idx * col_count + col_idx)

        grid_line = PolyLine()
        grid_line.SetPoints(vtk_points)
        grid_line.SetLines(vtk_lines)
        grid_line.Modified()
        return grid_line

    def _build_grid_entity_dict_from_source(
        self, source_uid=None, vtk_obj=None, slice_indices=None, fallback_name="multipart"
    ):
        """Clone source metadata for a non-slice-filtered gridded PolyLine entity."""
        if not source_uid or vtk_obj is None:
            return None

        entity_dict = deepcopy(self.parent.geol_coll.entity_dict)
        base_name = self._build_propagated_entity_name(
            seed_uid=source_uid,
            slice_indices=[],
            fallback_name=fallback_name,
        )
        try:
            import re

            base_name = re.sub(
                r"\s+regularized\s*$", "", str(base_name).strip(), flags=re.IGNORECASE
            )
            base_name = re.sub(
                r"\s+gridded\s*$", "", str(base_name).strip(), flags=re.IGNORECASE
            )
        except Exception:
            pass

        if slice_indices:
            entity_dict["name"] = (
                f"{base_name} gridded ({int(slice_indices[0])}-{int(slice_indices[-1])})"
            )
        else:
            entity_dict["name"] = f"{base_name} gridded"

        entity_dict["topology"] = "PolyLine"
        entity_dict["vtk_obj"] = vtk_obj

        for key, getter_name, default in (
            ("role", "get_uid_role", "undef"),
            ("feature", "get_uid_feature", fallback_name),
            ("scenario", "get_uid_scenario", "undef"),
            ("parent_uid", "get_uid_x_section", ""),
        ):
            try:
                entity_dict[key] = getattr(self.parent.geol_coll, getter_name)(source_uid)
            except Exception:
                entity_dict[key] = default

        entity_dict["properties_names"] = []
        entity_dict["properties_components"] = []
        return entity_dict

    def _get_multipart_sampling_primary_axis(self, axis=None, entity_kind="horizon"):
        """Return the preferred in-plane ordering axis for multipart regularization."""
        axis = axis or self.current_axis
        if entity_kind == "fault":
            return 2
        if axis == "Inline":
            return 1
        return 0

    def _collapse_slice_regularization_groups(
        self, slice_segments=None, axis=None, entity_kind="horizon"
    ):
        """Collapse one or more same-slice polyline parts into a single ordered trace."""
        if not slice_segments:
            return None

        primary_axis = self._get_multipart_sampling_primary_axis(
            axis=axis, entity_kind=entity_kind
        )
        _, in_plane_axes = self._get_slice_plane_axes(axis=axis)
        secondary_axes = [coord_idx for coord_idx in in_plane_axes if coord_idx != primary_axis]
        if not secondary_axes:
            secondary_axes = [coord_idx for coord_idx in range(3) if coord_idx != primary_axis]
        secondary_axis = secondary_axes[0]

        merged_points = []
        for segment in slice_segments:
            pts = np.asarray(segment["points"], dtype=float)
            if pts.ndim == 2 and pts.shape[0] >= 2:
                merged_points.append(pts)
        if not merged_points:
            return None

        merged_points = np.vstack(merged_points)
        if merged_points.shape[0] < 2:
            return None

        order = np.argsort(merged_points[:, primary_axis], kind="mergesort")
        sorted_points = merged_points[order]
        primary_values = sorted_points[:, primary_axis]
        secondary_values = sorted_points[:, secondary_axis]

        diffs = np.diff(primary_values)
        positive_diffs = np.abs(diffs[np.abs(diffs) > 1.0e-9])
        merge_tolerance = float(np.median(positive_diffs) * 0.35) if positive_diffs.size else 0.0
        merge_tolerance = max(merge_tolerance, 1.0e-6)

        grouped_points = []
        start_idx = 0
        for point_idx in range(1, len(sorted_points) + 1):
            at_end = point_idx == len(sorted_points)
            if not at_end:
                same_group = abs(primary_values[point_idx] - primary_values[point_idx - 1]) <= merge_tolerance
            else:
                same_group = False
            if same_group:
                continue
            group = sorted_points[start_idx:point_idx]
            grouped_points.append(group.mean(axis=0))
            start_idx = point_idx

        grouped_points = np.asarray(grouped_points, dtype=float)
        clean_points, source_s, _ = self._prepare_polyline_sampling(grouped_points)
        if clean_points is None:
            return None

        return {
            "slice_idx": int(slice_segments[0]["slice_idx"]),
            "points": clean_points,
            "source_s": source_s,
            "length": float(source_s[-1]),
            "point_count": int(clean_points.shape[0]),
            "source_cell_ids": [segment["cell_id"] for segment in slice_segments],
            "parts_merged": len(slice_segments),
        }

    def _extract_multipart_regularization_cells(
        self, vtk_obj=None, axis=None, entity_kind="horizon"
    ):
        """Collect one cleaned trace per slice for multipart regularization."""
        if vtk_obj is None or vtk_obj.GetNumberOfCells() == 0:
            return []

        cell_data = vtk_obj.GetCellData()
        if cell_data is None or not cell_data.HasArray("slice_index"):
            return []

        slice_array = cell_data.GetArray("slice_index")

        _, in_plane_axes = self._get_slice_plane_axes(axis=axis)
        ordered_cell_ids = sorted(
            range(vtk_obj.GetNumberOfCells()),
            key=lambda cell_idx: (int(slice_array.GetValue(cell_idx)), cell_idx),
        )

        extracted_segments = []
        previous_points = None
        for cell_idx in ordered_cell_ids:
            cell = vtk_obj.GetCell(cell_idx)
            if cell is None:
                continue
            n_pts = cell.GetNumberOfPoints()
            if n_pts < 2:
                continue

            point_ids = [cell.GetPointId(i) for i in range(n_pts)]
            raw_points = np.array(
                [vtk_obj.GetPoint(point_id) for point_id in point_ids], dtype=float
            )

            if previous_points is not None:
                prev_2d = previous_points[:, in_plane_axes]
                curr_2d = raw_points[:, in_plane_axes]
                forward_cost = np.linalg.norm(curr_2d[0] - prev_2d[0]) + np.linalg.norm(
                    curr_2d[-1] - prev_2d[-1]
                )
                reverse_cost = np.linalg.norm(curr_2d[-1] - prev_2d[0]) + np.linalg.norm(
                    curr_2d[0] - prev_2d[-1]
                )
                if reverse_cost + 1.0e-9 < forward_cost:
                    raw_points = raw_points[::-1]
                    point_ids = point_ids[::-1]

            clean_points, source_s, keep_mask = self._prepare_polyline_sampling(raw_points)
            if clean_points is None:
                continue

            extracted_segments.append(
                {
                    "cell_id": cell_idx,
                    "slice_idx": int(slice_array.GetValue(cell_idx)),
                    "points": clean_points,
                    "source_s": source_s,
                    "length": float(source_s[-1]),
                    "point_count": int(clean_points.shape[0]),
                }
            )
            previous_points = clean_points

        if not extracted_segments:
            return []

        collapsed_cells = []
        current_slice_idx = None
        current_group = []
        for segment in extracted_segments:
            if current_slice_idx is None or segment["slice_idx"] == current_slice_idx:
                current_group.append(segment)
                current_slice_idx = segment["slice_idx"]
                continue

            collapsed = self._collapse_slice_regularization_groups(
                slice_segments=current_group,
                axis=axis,
                entity_kind=entity_kind,
            )
            if collapsed is not None:
                collapsed_cells.append(collapsed)
            current_group = [segment]
            current_slice_idx = segment["slice_idx"]

        if current_group:
            collapsed = self._collapse_slice_regularization_groups(
                slice_segments=current_group,
                axis=axis,
                entity_kind=entity_kind,
            )
            if collapsed is not None:
                collapsed_cells.append(collapsed)

        return collapsed_cells

    def _estimate_multipart_regularization_defaults(
        self, vtk_obj=None, axis=None, entity_kind="horizon"
    ):
        """Suggest a stable point count and smoothing defaults for multipart resampling."""
        cells = self._extract_multipart_regularization_cells(
            vtk_obj=vtk_obj, axis=axis, entity_kind=entity_kind
        )
        if not cells:
            return {
                "slice_count": 0,
                "suggested_point_count": 0,
                "median_length": 0.0,
                "median_spacing": 0.0,
                "merged_part_count": 0,
            }

        lengths = [cell["length"] for cell in cells if cell["length"] > 0]
        avg_spacings = [
            cell["length"] / max(cell["point_count"] - 1, 1)
            for cell in cells
            if cell["length"] > 0 and cell["point_count"] > 1
        ]
        point_counts = [cell["point_count"] for cell in cells]

        median_length = float(np.median(lengths)) if lengths else 0.0
        median_spacing = float(np.median(avg_spacings)) if avg_spacings else 0.0
        if median_length > 0 and median_spacing > 0:
            suggested_point_count = int(np.ceil(median_length / median_spacing)) + 1
        else:
            suggested_point_count = int(np.median(point_counts)) if point_counts else 2
        suggested_point_count = max(2, min(800, suggested_point_count))

        return {
            "slice_count": len(cells),
            "suggested_point_count": suggested_point_count,
            "median_length": median_length,
            "median_spacing": median_spacing,
            "merged_part_count": int(
                sum(max(0, cell.get("parts_merged", 1) - 1) for cell in cells)
            ),
        }

    def _build_regularized_multipart_vtk(
        self,
        vtk_obj=None,
        axis=None,
        entity_kind="horizon",
        target_point_count=None,
        smooth_sigma=1.0,
        preserve_slice_indices=None,
        gridded_resampling=False,
    ):
        """Rebuild multipart geometry with uniform per-slice sampling."""
        cells = self._extract_multipart_regularization_cells(
            vtk_obj=vtk_obj, axis=axis, entity_kind=entity_kind
        )
        if not cells:
            return None, [], {}, {}

        if target_point_count is None:
            defaults = self._estimate_multipart_regularization_defaults(
                vtk_obj=vtk_obj, axis=axis, entity_kind=entity_kind
            )
            target_point_count = defaults.get("suggested_point_count", 2)
        target_point_count = max(2, min(int(target_point_count), 8000))

        resampled_stack = []
        for cell in cells:
            target_s = np.linspace(0.0, cell["length"], target_point_count)
            sampled_points = self._sample_polyline_values(
                cell["points"], cell["source_s"], target_s
            )
            resampled_stack.append(sampled_points)

        resampled_stack = np.stack(resampled_stack, axis=0)
        smoothed_stack = resampled_stack.copy()

        normal_axis, in_plane_axes = self._get_slice_plane_axes(axis=axis)
        smooth_sigma = float(smooth_sigma)
        if smooth_sigma > 0.0 and len(cells) > 2:
            for coord_idx in in_plane_axes:
                smoothed_stack[:, :, coord_idx] = ndimage.gaussian_filter1d(
                    resampled_stack[:, :, coord_idx],
                    sigma=smooth_sigma,
                    axis=0,
                    mode="nearest",
                )

        smoothed_stack[:, :, normal_axis] = resampled_stack[:, :, normal_axis]
        smoothed_stack[0, :, :] = resampled_stack[0, :, :]
        smoothed_stack[-1, :, :] = resampled_stack[-1, :, :]

        keep_original = {int(slice_idx) for slice_idx in (preserve_slice_indices or [])}
        if keep_original:
            for row_idx, cell in enumerate(cells):
                if cell["slice_idx"] in keep_original:
                    smoothed_stack[row_idx, :, :] = resampled_stack[row_idx, :, :]

        if gridded_resampling:
            smoothed_stack = self._apply_gridded_regularization(
                point_stack=smoothed_stack,
                cells=cells,
                axis=axis,
                smooth_sigma=smooth_sigma,
                preserve_slice_indices=preserve_slice_indices,
            )

        from vtk import vtkCellArray, vtkIntArray, vtkPoints

        new_points = vtkPoints()
        new_lines = vtkCellArray()
        point_slice_values = []
        cell_slice_values = []

        for row_idx, cell in enumerate(cells):
            start_idx = new_points.GetNumberOfPoints()
            sampled_points = smoothed_stack[row_idx]
            for point_idx, point in enumerate(sampled_points):
                new_points.InsertNextPoint(float(point[0]), float(point[1]), float(point[2]))
                point_slice_values.append(cell["slice_idx"])

            new_lines.InsertNextCell(target_point_count)
            for point_id in range(start_idx, start_idx + target_point_count):
                new_lines.InsertCellPoint(point_id)
            cell_slice_values.append(cell["slice_idx"])

        if new_points.GetNumberOfPoints() == 0 or new_lines.GetNumberOfCells() == 0:
            return None, [], {}, {}

        regularized_line = PolyLine()
        regularized_line.SetPoints(new_points)
        regularized_line.SetLines(new_lines)

        self._copy_selected_numeric_arrays(
            source_data=vtk_obj.GetCellData(),
            target_data=regularized_line.GetCellData(),
            selected_ids=[cell["source_cell_ids"][0] for cell in cells],
            skip_names={"slice_index"},
            skip_prefixes=("slices_",),
        )
        self._copy_field_data_arrays(
            source_data=vtk_obj.GetFieldData(),
            target_data=regularized_line.GetFieldData(),
        )

        point_slice_array = vtkIntArray()
        point_slice_array.SetName("slice_index")
        point_slice_array.SetNumberOfComponents(1)
        for slice_idx in point_slice_values:
            point_slice_array.InsertNextValue(int(slice_idx))
        regularized_line.GetPointData().AddArray(point_slice_array)

        cell_slice_array = vtkIntArray()
        cell_slice_array.SetName("slice_index")
        cell_slice_array.SetNumberOfComponents(1)
        for slice_idx in cell_slice_values:
            cell_slice_array.InsertNextValue(int(slice_idx))
        regularized_line.GetCellData().AddArray(cell_slice_array)

        regularized_slices = [cell["slice_idx"] for cell in cells]
        slice_to_cell_index = {
            int(slice_idx): cell_idx for cell_idx, slice_idx in enumerate(regularized_slices)
        }
        self._ensure_slice_index_property_metadata(
            vtk_obj=regularized_line, slice_indices=regularized_slices
        )
        regularized_line.Modified()

        old_point_counts = [cell["point_count"] for cell in cells]
        old_spacings = [
            cell["length"] / max(cell["point_count"] - 1, 1)
            for cell in cells
            if cell["point_count"] > 1 and cell["length"] > 0
        ]
        stats = {
            "slice_count": len(cells),
            "old_total_points": int(sum(old_point_counts)),
            "new_total_points": int(len(cells) * target_point_count),
            "old_median_points": float(np.median(old_point_counts)) if old_point_counts else 0.0,
            "old_median_spacing": float(np.median(old_spacings)) if old_spacings else 0.0,
            "new_points_per_slice": int(target_point_count),
            "smooth_sigma": smooth_sigma,
            "gridded_resampling": bool(gridded_resampling),
            "merged_part_count": int(
                sum(max(0, cell.get("parts_merged", 1) - 1) for cell in cells)
            ),
        }
        grid_vtk = None
        if gridded_resampling:
            grid_vtk = self._build_grid_polyline_from_stack(point_stack=smoothed_stack)
        return regularized_line, regularized_slices, slice_to_cell_index, stats, grid_vtk

    def _get_selected_multipart_entities_for_edit(self, action_title="Edit Multipart Slices"):
        """Resolve all selected propagated multipart horizons/faults and validate their slice metadata."""
        geol_uids = set(self.parent.geol_coll.get_uids)
        selected_uids = [
            uid
            for uid in list(getattr(self.parent, "selected_uids", []) or [])
            if uid in geol_uids
        ]
        if not selected_uids:
            message_dialog(
                title=action_title,
                message="Select at least one propagated horizon or fault in the geology tree.",
            )
            return []

        selections = []
        skipped_uids = []
        for uid in selected_uids:
            selection = self._resolve_multipart_entity_for_edit(
                uid=uid,
                action_title=action_title,
                show_messages=False,
            )
            if selection is None:
                skipped_uids.append(uid)
                continue
            selections.append(selection)

        if not selections:
            message_dialog(
                title=action_title,
                message="None of the selected entities is a propagated multipart horizon or fault.",
            )
            return []

        if skipped_uids:
            skipped_labels = []
            for uid in skipped_uids[:5]:
                try:
                    skipped_labels.append(self.parent.geol_coll.get_uid_name(uid))
                except Exception:
                    skipped_labels.append(f"{uid[:8]}...")
            more_count = max(0, len(skipped_uids) - len(skipped_labels))
            more_suffix = f" and {more_count} more" if more_count else ""
            self.print_terminal(
                "Skipped selected geology entities that are not editable multipart horizons/faults: "
                f"{', '.join(skipped_labels)}{more_suffix}."
            )

        return selections

    def _describe_multipart_entity_for_dialog(self, selection=None):
        """Build a compact label for dialog titles when editing multipart entities."""
        if selection is None:
            return "multipart entity"

        uid = selection.get("uid")
        entity_kind = selection.get("entity_kind", "multipart")
        try:
            entity_name = str(self.parent.geol_coll.get_uid_name(uid)).strip()
        except Exception:
            entity_name = ""

        if entity_name:
            return f"{entity_kind}: {entity_name}"
        return f"{entity_kind}: {uid[:8]}..." if uid else entity_kind

    def _regularize_single_multipart_entity(
        self, selection=None, action_title="Regularize Multipart Sampling"
    ):
        """Regularize one propagated multipart horizon/fault and report whether the flow completed."""
        if selection is None:
            return "failed"

        uid = selection["uid"]
        entity_kind = selection["entity_kind"]
        entity_info = selection["entity_info"]
        vtk_obj = selection["vtk_obj"]
        available_slices = selection["available_slices"]
        axis = entity_info.get("axis", self.current_axis)
        entity_label = self._describe_multipart_entity_for_dialog(selection=selection)
        dialog_title = f"{action_title} - {entity_label}"

        defaults = self._estimate_multipart_regularization_defaults(
            vtk_obj=vtk_obj, axis=axis, entity_kind=entity_kind
        )
        if defaults["slice_count"] == 0:
            message_dialog(
                title=dialog_title,
                message="The selected multipart entity does not contain valid line geometry.",
            )
            return "failed"

        settings = multiple_input_dialog(
            title=f"{dialog_title} ({available_slices[0]}-{available_slices[-1]})",
            input_dict={
                "points_per_slice": [
                    "Points per slice:",
                    defaults["suggested_point_count"],
                ],
                "smooth_sigma": [
                    "Cross-slice smoothing sigma:",
                    1.0 if defaults["slice_count"] > 2 else 0.0,
                ],
                "preserve_seed_slice": [
                    "Keep the seed slice unchanged:",
                    ["Yes", "No"],
                    "Yes",
                ],
                "gridded_resampling": [
                    "Gridded resampling for Delaunay-ready sampling:",
                    ["No", "Yes"],
                    "No",
                ],
            },
        )
        if settings is None:
            return "cancelled"

        try:
            points_per_slice = max(2, int(settings["points_per_slice"]))
            smooth_sigma = max(0.0, float(settings["smooth_sigma"]))
            preserve_seed_slice = str(settings["preserve_seed_slice"]).strip().lower() != "no"
            gridded_resampling = (
                str(settings.get("gridded_resampling", "No")).strip().lower() == "yes"
            )
        except Exception:
            message_dialog(
                title=dialog_title,
                message="Invalid resampling parameters.",
            )
            return "failed"

        preserve_slice_indices = []
        seed_slice = entity_info.get("seed_slice")
        if preserve_seed_slice and seed_slice in available_slices:
            preserve_slice_indices.append(int(seed_slice))

        new_vtk, new_slices, slice_to_cell_index, stats, grid_vtk = self._build_regularized_multipart_vtk(
            vtk_obj=vtk_obj,
            axis=axis,
            entity_kind=entity_kind,
            target_point_count=points_per_slice,
            smooth_sigma=smooth_sigma,
            preserve_slice_indices=preserve_slice_indices,
            gridded_resampling=gridded_resampling,
        )
        if new_vtk is None or not new_slices:
            message_dialog(
                title=dialog_title,
                message="Could not rebuild the selected multipart geometry.",
            )
            return "failed"

        grid_uid = None
        fallback_name = "fault" if entity_kind == "fault" else "multipart"
        if gridded_resampling and grid_vtk is not None:
            grid_entity_dict = self._build_grid_entity_dict_from_source(
                source_uid=uid,
                vtk_obj=grid_vtk,
                slice_indices=new_slices,
                fallback_name=fallback_name,
            )
            if grid_entity_dict is None:
                message_dialog(
                    title=dialog_title,
                    message="Could not build the gridded companion entity.",
                )
                return "failed"

        write_mode = options_dialog(
            title=dialog_title,
            message=(
                f"Do you want to overwrite the original multipart {entity_kind}, "
                f"or keep it and add a new regularized entity?"
            ),
            yes_role="Overwrite",
            no_role="New",
            reject_role="Cancel",
        )
        if write_mode not in (0, 1):
            return "cancelled"

        if write_mode == 1:
            import re

            new_entity_dict = self._build_multipart_entity_dict_from_source(
                source_uid=uid,
                vtk_obj=new_vtk,
                slice_indices=new_slices,
                fallback_name=fallback_name,
            )
            if new_entity_dict is None:
                message_dialog(
                    title=dialog_title,
                    message="Could not build the new regularized multipart entity.",
                )
                return "failed"

            base_name = self._build_propagated_entity_name(
                seed_uid=uid,
                slice_indices=[],
                fallback_name=fallback_name,
            )
            base_name = re_sub(
                r"\s+regularized\s*$", "", base_name, flags=re_IGNORECASE
            )
            if new_slices:
                new_entity_dict["name"] = (
                    f"{base_name} regularized ({new_slices[0]}-{new_slices[-1]})"
                )
            else:
                new_entity_dict["name"] = f"{base_name} regularized"

            new_uid = self.parent.geol_coll.add_entity_from_dict(new_entity_dict)
            self._register_multipart_interpretation_entity(
                uid=new_uid,
                axis=axis,
                slice_indices=new_slices,
                slice_to_cell_index=slice_to_cell_index,
            )
            if new_uid in getattr(self, "multipart_horizons", {}):
                self.multipart_horizons[new_uid]["seed_slice"] = entity_info.get(
                    "seed_slice", new_slices[0]
                )
                self.update_multipart_horizon_visibility(uid)
                self.update_multipart_horizon_visibility(new_uid)
            if new_uid in getattr(self, "multipart_faults", {}):
                self.multipart_faults[new_uid]["seed_slice"] = entity_info.get(
                    "seed_slice", new_slices[0]
                )
                self.update_multipart_fault_visibility(uid)
                self.update_multipart_fault_visibility(new_uid)

            if gridded_resampling and grid_vtk is not None:
                grid_uid = self.parent.geol_coll.add_entity_from_dict(grid_entity_dict)
                try:
                    self.set_actor_visibility(grid_uid, False)
                except Exception:
                    pass

            self._mark_slice_visibility_dirty()
            self.plotter.render()
            self.print_terminal(
                f"Created regularized multipart {entity_kind} {new_uid[:8]}... from {uid[:8]}... "
                f"across {stats['slice_count']} slices: "
                f"{int(round(stats['old_median_points']))} -> {stats['new_points_per_slice']} "
                f"points/slice, merged {stats['merged_part_count']} duplicate slice parts, "
                f"median spacing {stats['old_median_spacing']:.3f}, "
                f"smoothing sigma {stats['smooth_sigma']:.2f}, "
                f"gridded resampling {'on' if stats.get('gridded_resampling') else 'off'}"
                f"{f', grid entity {grid_uid[:8]}...' if grid_uid else ''}."
            )
            return "done"

        self._remove_filtered_actor(f"multipart_slice_{uid}")
        self._remove_filtered_actor(f"multipart_fault_slice_{uid}")
        self._remove_raw_actor_for_uid(uid)
        self._register_multipart_interpretation_entity(
            uid=uid,
            axis=axis,
            slice_indices=new_slices,
            slice_to_cell_index=slice_to_cell_index,
        )
        if uid in getattr(self, "multipart_horizons", {}):
            self.multipart_horizons[uid]["seed_slice"] = entity_info.get(
                "seed_slice", new_slices[0]
            )
        if uid in getattr(self, "multipart_faults", {}):
            self.multipart_faults[uid]["seed_slice"] = entity_info.get(
                "seed_slice", new_slices[0]
            )

        self.parent.geol_coll.replace_vtk(uid=uid, vtk_object=new_vtk)
        self._mark_slice_visibility_dirty()
        if uid in getattr(self, "multipart_horizons", {}):
            self.update_multipart_horizon_visibility(uid)
        if uid in getattr(self, "multipart_faults", {}):
            self.update_multipart_fault_visibility(uid)

        if gridded_resampling and grid_vtk is not None:
            grid_uid = self.parent.geol_coll.add_entity_from_dict(grid_entity_dict)
            try:
                self.set_actor_visibility(grid_uid, False)
            except Exception:
                pass
        self.plotter.render()

        self.print_terminal(
            f"Regularized multipart {entity_kind} {uid[:8]}... across {stats['slice_count']} slices: "
            f"{int(round(stats['old_median_points']))} -> {stats['new_points_per_slice']} "
            f"points/slice, merged {stats['merged_part_count']} duplicate slice parts, "
            f"median spacing {stats['old_median_spacing']:.3f}, "
            f"smoothing sigma {stats['smooth_sigma']:.2f}, "
            f"gridded resampling {'on' if stats.get('gridded_resampling') else 'off'}"
            f"{f', grid entity {grid_uid[:8]}...' if grid_uid else ''}."
        )
        return "done"

    def regularize_multipart_sampling(self):
        """Uniformly resample selected propagated multipart horizons/faults for downstream modelling."""
        selections = self._get_selected_multipart_entities_for_edit(
            action_title="Regularize Multipart Sampling"
        )
        if not selections:
            return

        processed_count = 0
        total_count = len(selections)
        for index, selection in enumerate(selections, start=1):
            action_title = "Regularize Multipart Sampling"
            if total_count > 1:
                action_title = f"Regularize Multipart Sampling ({index}/{total_count})"

            status = self._regularize_single_multipart_entity(
                selection=selection,
                action_title=action_title,
            )
            if status == "cancelled":
                if total_count > 1 and index < total_count:
                    self.print_terminal(
                        f"Stopped multipart regularization after {processed_count} of "
                        f"{total_count} selected entities."
                    )
                return
            if status == "done":
                processed_count += 1

    def simplify_selected_lines(self):
        """Simplify selected interpretation polylines, including multipart entities."""
        self.print_terminal(
            "Simplify line. Define tolerance value: small values preserve more vertices."
        )

        selected_uids = list(getattr(self.parent, "selected_uids", []) or [])
        if not selected_uids:
            self.print_terminal(" -- No input data selected -- ")
            return

        tolerance_p = input_one_value_dialog(
            parent=self,
            title="Simplify - Tolerance",
            label="Insert tolerance parameter",
            default_value="0.1",
        )
        if tolerance_p is None:
            return
        if tolerance_p <= 0:
            tolerance_p = 0.1

        processed_uids = []
        for uid in selected_uids:
            if uid not in set(self.parent.geol_coll.get_uids):
                continue

            try:
                topology = self.parent.geol_coll.get_uid_topology(uid)
            except Exception:
                topology = None
            if topology != "PolyLine":
                self.print_terminal(f" -- Selected data is not a line: {uid} -- ")
                continue

            try:
                vtk_obj = self.parent.geol_coll.get_uid_vtk_obj(uid)
            except Exception:
                vtk_obj = None
            if vtk_obj is None or vtk_obj.GetNumberOfCells() == 0:
                self.print_terminal(f" -- Object not valid for {uid} -- ")
                continue

            self.scan_and_index_single_horizon(uid)
            axis = self._resolve_polyline_axis_for_simplify(uid=uid, vtk_obj=vtk_obj)
            new_vtk, slice_indices, slice_to_cell_index, stats = (
                self._build_simplified_polyline_vtk(
                    vtk_obj=vtk_obj,
                    tolerance=tolerance_p,
                    axis=axis,
                )
            )
            if new_vtk is None or new_vtk.GetNumberOfCells() == 0:
                self.print_terminal(f" -- Simplification failed for {uid} -- ")
                continue

            self._remove_filtered_actor(f"multipart_slice_{uid}")
            self._remove_filtered_actor(f"multipart_fault_slice_{uid}")
            self.parent.geol_coll.replace_vtk(uid=uid, vtk_object=new_vtk)

            if slice_indices:
                self._register_multipart_interpretation_entity(
                    uid=uid,
                    axis=axis,
                    slice_indices=slice_indices,
                    slice_to_cell_index=slice_to_cell_index,
                )
            elif uid in getattr(self, "interpretation_lines", {}):
                self.register_interpretation_line(uid, self.interpretation_lines[uid])

            processed_uids.append(uid)
            if uid in getattr(self, "multipart_horizons", {}):
                entity_kind = "multipart horizon"
            elif uid in getattr(self, "multipart_faults", {}):
                entity_kind = "multipart fault"
            else:
                entity_kind = "line"
            self.print_terminal(
                f"Simplified {entity_kind} {uid[:8]}... on {axis}: "
                f"{stats['old_total_points']} -> {stats['new_total_points']} points "
                f"across {stats['cell_count']} cell(s)."
            )

        if not processed_uids:
            return

        self._mark_slice_visibility_dirty()
        self.update_interpretation_line_visibility()
        self.update_all_multipart_horizons_visibility()
        self.update_all_multipart_faults_visibility()
        self.plotter.render()
        self.clear_selection()

    def _resolve_multipart_entity_for_edit(
        self, uid=None, action_title="Edit Multipart Slices", show_messages=True
    ):
        """Resolve one propagated multipart entity and validate its slice metadata."""
        if uid not in set(self.parent.geol_coll.get_uids):
            if show_messages:
                message_dialog(
                    title=action_title,
                    message="The selected entity is not present in the geology tree.",
                )
            return None

        self.scan_and_index_single_horizon(uid)

        entity_kind = None
        entity_info = None
        if uid in getattr(self, "multipart_horizons", {}):
            entity_kind = "horizon"
            entity_info = self.multipart_horizons[uid]
        elif uid in getattr(self, "multipart_faults", {}):
            entity_kind = "fault"
            entity_info = self.multipart_faults[uid]

        if entity_info is None:
            if show_messages:
                message_dialog(
                    title=action_title,
                    message="The selected entity is not a propagated multipart horizon or fault.",
                )
            return None

        vtk_obj = self.parent.geol_coll.get_uid_vtk_obj(uid)
        if vtk_obj is None or vtk_obj.GetNumberOfCells() == 0:
            if show_messages:
                message_dialog(
                    title=action_title,
                    message="The selected entity has no geometry to edit.",
                )
            return None

        cell_data = vtk_obj.GetCellData()
        if cell_data is None or not cell_data.HasArray("slice_index"):
            if show_messages:
                message_dialog(
                    title=action_title,
                    message="The selected multipart entity has no slice_index cell data.",
                )
            return None

        available_slices = sorted(
            {int(idx) for idx in entity_info.get("slice_indices", [])}
            or set(self._extract_slice_indices_from_vtk(vtk_obj))
        )
        if not available_slices:
            if show_messages:
                message_dialog(
                    title=action_title,
                    message="No slice indices were found on the selected entity.",
                )
            return None

        return {
            "uid": uid,
            "entity_kind": entity_kind,
            "entity_info": entity_info,
            "vtk_obj": vtk_obj,
            "cell_data": cell_data,
            "slice_array": cell_data.GetArray("slice_index"),
            "available_slices": available_slices,
        }

    def _get_selected_multipart_entity_for_edit(self, action_title="Edit Multipart Slices"):
        """Resolve the selected propagated multipart entity and validate its slice metadata."""
        selected_uids = [
            uid
            for uid in list(getattr(self.parent, "selected_uids", []) or [])
            if uid in set(self.parent.geol_coll.get_uids)
        ]
        if len(selected_uids) != 1:
            message_dialog(
                title=action_title,
                message="Select exactly one propagated horizon or fault in the geology tree.",
            )
            return None

        return self._resolve_multipart_entity_for_edit(
            uid=selected_uids[0],
            action_title=action_title,
            show_messages=True,
        )

    def delete_multipart_slices(self):
        """Delete a slice interval from the selected propagated multipart horizon/fault."""
        selection = self._get_selected_multipart_entity_for_edit(
            action_title="Delete Multipart Slices"
        )
        if selection is None:
            return

        uid = selection["uid"]
        entity_kind = selection["entity_kind"]
        entity_info = selection["entity_info"]
        vtk_obj = selection["vtk_obj"]
        cell_data = selection["cell_data"]
        available_slices = selection["available_slices"]

        range_in = multiple_input_dialog(
            title=f"Delete Multipart Slices ({available_slices[0]}-{available_slices[-1]})",
            input_dict={
                "slice_from": ["Delete from slice:", available_slices[0]],
                "slice_to": ["Delete to slice:", available_slices[-1]],
            },
        )
        if range_in is None:
            return

        slice_from = int(range_in["slice_from"])
        slice_to = int(range_in["slice_to"])
        if slice_from > slice_to:
            slice_from, slice_to = slice_to, slice_from

        slices_to_delete = {
            slice_idx
            for slice_idx in available_slices
            if slice_from <= slice_idx <= slice_to
        }
        if not slices_to_delete:
            message_dialog(
                title="Delete Multipart Slices",
                message="The requested interval does not match any slices in the selected entity.",
            )
            return

        slice_array = cell_data.GetArray("slice_index")
        kept_cell_ids = [
            cell_idx
            for cell_idx in range(vtk_obj.GetNumberOfCells())
            if int(slice_array.GetValue(cell_idx)) not in slices_to_delete
        ]

        if not kept_cell_ids:
            self.parent.geol_coll.remove_entity(uid=uid)
            self.print_terminal(
                f"Deleted multipart {entity_kind} {uid[:8]}... because all slices were removed."
            )
            return

        new_vtk, remaining_slices, slice_to_cell_index = self._build_multipart_subset_vtk(
            vtk_obj=vtk_obj,
            kept_cell_ids=kept_cell_ids,
        )
        if new_vtk is None or new_vtk.GetNumberOfCells() == 0:
            self.parent.geol_coll.remove_entity(uid=uid)
            self.print_terminal(
                f"Deleted multipart {entity_kind} {uid[:8]}... because no valid slices remained."
            )
            return

        axis = entity_info.get("axis", self.current_axis)
        self._remove_filtered_actor(f"multipart_slice_{uid}")
        self._remove_filtered_actor(f"multipart_fault_slice_{uid}")
        self._remove_raw_actor_for_uid(uid)
        self._register_multipart_interpretation_entity(
            uid=uid,
            axis=axis,
            slice_indices=remaining_slices,
            slice_to_cell_index=slice_to_cell_index,
        )
        self.parent.geol_coll.replace_vtk(uid=uid, vtk_object=new_vtk)
        self._mark_slice_visibility_dirty()
        if uid in getattr(self, "multipart_horizons", {}):
            self.update_multipart_horizon_visibility(uid)
        if uid in getattr(self, "multipart_faults", {}):
            self.update_multipart_fault_visibility(uid)
        self.plotter.render()
        self.print_terminal(
            f"Deleted slices {slice_from}-{slice_to} from multipart {entity_kind} {uid[:8]}.... "
            f"Remaining slices: {remaining_slices[0]}-{remaining_slices[-1]}"
        )

    def split_multipart_slices(self):
        """Split a slice interval from the selected multipart horizon/fault into a new entity."""
        selection = self._get_selected_multipart_entity_for_edit(
            action_title="Split Multipart Slices"
        )
        if selection is None:
            return

        uid = selection["uid"]
        entity_kind = selection["entity_kind"]
        entity_info = selection["entity_info"]
        vtk_obj = selection["vtk_obj"]
        slice_array = selection["slice_array"]
        available_slices = selection["available_slices"]

        range_in = multiple_input_dialog(
            title=f"Split Multipart Slices ({available_slices[0]}-{available_slices[-1]})",
            input_dict={
                "slice_from": ["Split out from slice:", available_slices[0]],
                "slice_to": ["Split out to slice:", available_slices[-1]],
            },
        )
        if range_in is None:
            return

        slice_from = int(range_in["slice_from"])
        slice_to = int(range_in["slice_to"])
        if slice_from > slice_to:
            slice_from, slice_to = slice_to, slice_from

        slices_to_extract = {
            slice_idx
            for slice_idx in available_slices
            if slice_from <= slice_idx <= slice_to
        }
        if not slices_to_extract:
            message_dialog(
                title="Split Multipart Slices",
                message="The requested interval does not match any slices in the selected entity.",
            )
            return
        if len(slices_to_extract) == len(available_slices):
            message_dialog(
                title="Split Multipart Slices",
                message="The requested interval covers the whole multipart entity. Leave at least one slice in the original entity.",
            )
            return

        extracted_cell_ids = []
        remaining_cell_ids = []
        for cell_idx in range(vtk_obj.GetNumberOfCells()):
            slice_idx = int(slice_array.GetValue(cell_idx))
            if slice_idx in slices_to_extract:
                extracted_cell_ids.append(cell_idx)
            else:
                remaining_cell_ids.append(cell_idx)

        if not extracted_cell_ids or not remaining_cell_ids:
            message_dialog(
                title="Split Multipart Slices",
                message="The split must produce both an extracted part and a remaining part.",
            )
            return

        extracted_vtk, extracted_slices, extracted_map = self._build_multipart_subset_vtk(
            vtk_obj=vtk_obj,
            kept_cell_ids=extracted_cell_ids,
        )
        remaining_vtk, remaining_slices, remaining_map = self._build_multipart_subset_vtk(
            vtk_obj=vtk_obj,
            kept_cell_ids=remaining_cell_ids,
        )
        if (
            extracted_vtk is None
            or remaining_vtk is None
            or not extracted_slices
            or not remaining_slices
        ):
            message_dialog(
                title="Split Multipart Slices",
                message="The multipart entity could not be split with the requested interval.",
            )
            return

        axis = entity_info.get("axis", self.current_axis)
        original_name = self._build_propagated_entity_name(
            seed_uid=uid,
            slice_indices=remaining_slices,
            fallback_name="multipart",
        )
        new_entity_dict = self._build_multipart_entity_dict_from_source(
            source_uid=uid,
            vtk_obj=extracted_vtk,
            slice_indices=extracted_slices,
            fallback_name="multipart",
        )
        if new_entity_dict is None:
            message_dialog(
                title="Split Multipart Slices",
                message="Could not build the new multipart entity.",
            )
            return

        self._remove_filtered_actor(f"multipart_slice_{uid}")
        self._remove_filtered_actor(f"multipart_fault_slice_{uid}")
        self._remove_raw_actor_for_uid(uid)

        self._register_multipart_interpretation_entity(
            uid=uid,
            axis=axis,
            slice_indices=remaining_slices,
            slice_to_cell_index=remaining_map,
        )
        self.parent.geol_coll.replace_vtk(uid=uid, vtk_object=remaining_vtk)
        self.parent.geol_coll.set_uid_name(uid=uid, name=original_name)
        try:
            self.parent.geol_coll.modelReset.emit()
        except Exception:
            pass

        new_uid = self.parent.geol_coll.add_entity_from_dict(new_entity_dict)
        self._register_multipart_interpretation_entity(
            uid=new_uid,
            axis=axis,
            slice_indices=extracted_slices,
            slice_to_cell_index=extracted_map,
        )

        try:
            self.parent.signals.metadata_modified.emit([uid], self.parent.geol_coll)
        except Exception:
            pass

        self._mark_slice_visibility_dirty()
        if uid in getattr(self, "multipart_horizons", {}):
            self.update_multipart_horizon_visibility(uid)
            self.update_multipart_horizon_visibility(new_uid)
        if uid in getattr(self, "multipart_faults", {}):
            self.update_multipart_fault_visibility(uid)
            self.update_multipart_fault_visibility(new_uid)
        self.plotter.render()
        self.print_terminal(
            f"Split multipart {entity_kind} {uid[:8]}... into "
            f"{remaining_slices[0]}-{remaining_slices[-1]} and "
            f"{extracted_slices[0]}-{extracted_slices[-1]}."
        )

    def separate_disconnected_multipart_parts(self):
        """Separate one multipart horizon/fault into multiple branch entities when same-slice parts are disconnected."""
        selection = self._get_selected_multipart_entity_for_edit(
            action_title="Separate Disconnected Multipart Parts"
        )
        if selection is None:
            return

        uid = selection["uid"]
        entity_kind = selection["entity_kind"]
        entity_info = selection["entity_info"]
        vtk_obj = selection["vtk_obj"]
        axis = entity_info.get("axis", self.current_axis)

        segments_by_slice = self._extract_multipart_branch_segments(
            vtk_obj=vtk_obj,
            axis=axis,
            entity_kind=entity_kind,
        )
        if not segments_by_slice:
            message_dialog(
                title="Separate Disconnected Multipart Parts",
                message="The selected multipart entity has no valid slice segments to analyze.",
            )
            return

        multi_part_slices = [
            slice_idx
            for slice_idx, slice_segments in segments_by_slice.items()
            if len(slice_segments) > 1
        ]
        if not multi_part_slices:
            message_dialog(
                title="Separate Disconnected Multipart Parts",
                message="No slice in the selected multipart entity contains multiple disconnected parts.",
            )
            return

        auto_match_distance = self._estimate_multipart_branch_match_distance(
            segments_by_slice=segments_by_slice
        )
        settings = multiple_input_dialog(
            title="Separate Disconnected Multipart Parts",
            input_dict={
                "max_gap_slices": [
                    "Allow the same part to disappear for up to N slices:",
                    2,
                ],
                "match_distance": [
                    "Match distance in slice plane (0 = auto):",
                    float(auto_match_distance),
                ],
            },
        )
        if settings is None:
            return

        try:
            max_gap_slices = max(0, int(settings["max_gap_slices"]))
            match_distance = float(settings["match_distance"])
        except Exception:
            message_dialog(
                title="Separate Disconnected Multipart Parts",
                message="Invalid separation settings.",
            )
            return

        branches, stats = self._detect_disconnected_multipart_branches(
            vtk_obj=vtk_obj,
            axis=axis,
            entity_kind=entity_kind,
            max_slice_gap=max_gap_slices,
            match_distance=match_distance,
        )
        if len(branches) <= 1:
            message_dialog(
                title="Separate Disconnected Multipart Parts",
                message="The selected multipart entity could not be separated into multiple continuous parts with the current settings.",
            )
            return

        seed_slice = entity_info.get("seed_slice")
        branches.sort(
            key=lambda payload: (
                0 if seed_slice in payload.get("slice_indices", []) else 1,
                -payload.get("cell_count", 0),
                payload.get("branch_index", 10**9),
            )
        )
        for branch_index, payload in enumerate(branches, start=1):
            payload["branch_index"] = branch_index

        split_payloads = []
        for payload in branches:
            branch_vtk, branch_slices, branch_map = self._build_multipart_subset_vtk(
                vtk_obj=vtk_obj,
                kept_cell_ids=payload["cell_ids"],
            )
            if branch_vtk is None or not branch_slices:
                continue
            payload["vtk_obj"] = branch_vtk
            payload["slice_indices"] = branch_slices
            payload["slice_to_cell_index"] = branch_map
            split_payloads.append(payload)

        if len(split_payloads) <= 1:
            message_dialog(
                title="Separate Disconnected Multipart Parts",
                message="The selected multipart entity could not be rewritten into multiple valid branch entities.",
            )
            return

        branch_count = len(split_payloads)
        fallback_name = "fault" if entity_kind == "fault" else "multipart"

        self._remove_filtered_actor(f"multipart_slice_{uid}")
        self._remove_filtered_actor(f"multipart_fault_slice_{uid}")
        self._remove_raw_actor_for_uid(uid)

        primary_payload = split_payloads[0]
        primary_name = self._build_multipart_branch_name(
            seed_uid=uid,
            slice_indices=primary_payload["slice_indices"],
            branch_index=1,
            branch_count=branch_count,
            fallback_name=fallback_name,
        )
        self._register_multipart_interpretation_entity(
            uid=uid,
            axis=axis,
            slice_indices=primary_payload["slice_indices"],
            slice_to_cell_index=primary_payload["slice_to_cell_index"],
        )
        if uid in getattr(self, "multipart_horizons", {}):
            self.multipart_horizons[uid]["seed_slice"] = (
                int(seed_slice)
                if seed_slice in primary_payload["slice_indices"]
                else primary_payload["slice_indices"][0]
            )
        if uid in getattr(self, "multipart_faults", {}):
            self.multipart_faults[uid]["seed_slice"] = (
                int(seed_slice)
                if seed_slice in primary_payload["slice_indices"]
                else primary_payload["slice_indices"][0]
            )
        self.parent.geol_coll.replace_vtk(uid=uid, vtk_object=primary_payload["vtk_obj"])
        self.parent.geol_coll.set_uid_name(uid=uid, name=primary_name)

        new_uids = []
        for payload in split_payloads[1:]:
            new_entity_dict = self._build_multipart_entity_dict_from_source(
                source_uid=uid,
                vtk_obj=payload["vtk_obj"],
                slice_indices=payload["slice_indices"],
                fallback_name=fallback_name,
            )
            if new_entity_dict is None:
                continue

            new_entity_dict["name"] = self._build_multipart_branch_name(
                seed_uid=uid,
                slice_indices=payload["slice_indices"],
                branch_index=payload["branch_index"],
                branch_count=branch_count,
                fallback_name=fallback_name,
            )
            new_uid = self.parent.geol_coll.add_entity_from_dict(new_entity_dict)
            self._register_multipart_interpretation_entity(
                uid=new_uid,
                axis=axis,
                slice_indices=payload["slice_indices"],
                slice_to_cell_index=payload["slice_to_cell_index"],
            )
            if new_uid in getattr(self, "multipart_horizons", {}):
                self.multipart_horizons[new_uid]["seed_slice"] = payload["slice_indices"][0]
            if new_uid in getattr(self, "multipart_faults", {}):
                self.multipart_faults[new_uid]["seed_slice"] = payload["slice_indices"][0]
            new_uids.append(new_uid)

        try:
            self.parent.geol_coll.modelReset.emit()
        except Exception:
            pass

        try:
            self.parent.signals.metadata_modified.emit([uid], self.parent.geol_coll)
        except Exception:
            pass

        self._mark_slice_visibility_dirty()
        if entity_kind == "horizon":
            self.update_multipart_horizon_visibility(uid)
            for new_uid in new_uids:
                self.update_multipart_horizon_visibility(new_uid)
        else:
            self.update_multipart_fault_visibility(uid)
            for new_uid in new_uids:
                self.update_multipart_fault_visibility(new_uid)
        self.plotter.render()

        self.print_terminal(
            f"Separated multipart {entity_kind} {uid[:8]}... into {len(new_uids) + 1} parts "
            f"(max parts/slice: {stats['max_parts_per_slice']}, "
            f"match distance: {stats['used_match_distance']:.3f})."
        )

    def update_slice_colormap(self):
        """Update the slice colormap when legend changes - called by prop_legend_cmap_modified signal."""
        if self.slice_actor is not None:
            cmap = self.get_seismic_colormap()
            # Force full redraw with new colormap
            self._camera_initialized = True  # Keep camera position
            # Note: Do NOT reset scalar_range here - we want to keep using the full volume range
            # for consistent colormap across all slices. The _cached_scalar_range will be used.
            old_slice_actor = self.slice_actor
            self.slice_actor = None  # Force full update
            self.update_slice()

    def draw_interpretation_line(self):
        """Draw a line on the current seismic slice. The line will be snapped to the slice plane."""
        def end_digitize(event, input_dict):
            # Signal called to end the digitization of a trace. It returns a new polydata
            self.plotter.untrack_click_position()
            traced_pld = (
                tracer.GetContourRepresentation().GetContourRepresentationAsPolyData()
            )
            if traced_pld.GetNumberOfPoints() > 0:
                # Copy the traced polydata to our vtk object first (like standard draw_line)
                input_dict["vtk_obj"].ShallowCopy(traced_pld)
                
                # Debug: Print original points before snapping
                points = np.array(input_dict["vtk_obj"].GetPoints().GetData())
                self.print_terminal(f"Original traced points (first 3): {points[:min(3, len(points))]}")
                self.print_terminal(f"Current axis: {self.current_axis}, slice position: {self.current_slice_position}")
                
                # Now snap the points to the current slice plane
                snapped_points = self.snap_points_to_slice(points)
                self.print_terminal(f"Snapped points (first 3): {snapped_points[:min(3, len(snapped_points))]}")
                
                input_dict["vtk_obj"].points = snapped_points
                
                # Store the slice info for this line (capture current values from outer scope)
                slice_info = {
                    'seismic_uid': self.current_seismic_uid,
                    'axis': self.current_axis,
                    'slice_index': self.current_slice_index
                }
                
                # Add to geological collection - this emits signals that other views listen to
                new_uid = self.parent.geol_coll.add_entity_from_dict(input_dict)
                self.print_terminal(f"Created interpretation line with {len(snapped_points)} points, uid: {new_uid}")
                
                # Track this interpretation line with its slice info
                # Track this interpretation line with its slice info
                self.register_interpretation_line(new_uid, slice_info)
                self.print_terminal(f"Registered interpretation line {new_uid} for {slice_info['axis']} slice {slice_info['slice_index']}")
            
            # Restore pickability state of all actors
            if hasattr(self, '_saved_pickable_state'):
                for name, pickable in self._saved_pickable_state.items():
                    try:
                        if name in self.plotter.renderer.actors:
                            self.plotter.renderer.actors[name].SetPickable(pickable)
                    except:
                        pass
                delattr(self, '_saved_pickable_state')
                    
            tracer.EnabledOff()
            self.enable_actions()

        self.disable_actions()
        
        if not self.current_seismic_uid:
            self.print_terminal("Please select a seismic volume first!")
            self.enable_actions()
            return
        
        # Create deepcopy of the geological entity dictionary.
        line_dict = deepcopy(self.parent.geol_coll.entity_dict)
        feature_choices = self._sanitize_legend_choices(
            self.parent.geol_coll.legend_df["feature"].tolist(), fallback="undef"
        )
        scenario_choices = self._sanitize_legend_choices(
            self.parent.geol_coll.legend_df["scenario"].tolist(), fallback="undef"
        )
        # One dictionary is set as input for a general widget of multiple-value-input
        line_dict_in = {
            "name": ["PolyLine name: ", "interp_line"],
            "role": [
                "Role: ",
                self.parent.geol_coll.valid_roles,
            ],
            "feature": [
                "Feature: ",
                feature_choices,
            ],
            "scenario": [
                "Scenario: ",
                scenario_choices,
            ],
        }
        line_dict_updt = multiple_input_dialog(
            title="Digitize Interpretation Line", input_dict=line_dict_in
        )
        # Check if the output of the widget is empty or not. If the Cancel button was clicked, the tool quits
        if line_dict_updt is None:
            self.enable_actions()
            return
        # Getting the values that have been typed by the user through the widget
        for key in line_dict_updt:
            line_dict[key] = line_dict_updt[key]
        line_dict["role"] = self._sanitize_legend_value(line_dict.get("role"), "undef")
        line_dict["feature"] = self._sanitize_legend_value(line_dict.get("feature"), "undef")
        line_dict["scenario"] = self._sanitize_legend_value(line_dict.get("scenario"), "undef")
        
        line_dict["topology"] = "PolyLine"
        line_dict["x_section"] = ""
        line_dict["vtk_obj"] = PolyLine()
        self._set_entity_parent_to_current_seismic(line_dict)
        
        # Store pickability state of all actors, then make only the slice pickable
        self._saved_pickable_state = {}
        for name, actor in self.plotter.renderer.actors.items():
            try:
                self._saved_pickable_state[name] = actor.GetPickable()
                if name != "seismic_slice_actor":
                    actor.SetPickable(False)
            except:
                pass
        
        # Ensure the slice actor is pickable
        if self.slice_actor:
            try:
                self.slice_actor.SetPickable(True)
                self.print_terminal("Slice actor is now the only pickable object for tracing")
            except Exception as e:
                self.print_terminal(f"Could not set slice pickable: {e}")
        
        tracer = Tracer(self)
        tracer.EnabledOn()
        self.plotter.track_click_position(
            side="right", callback=lambda event: end_digitize(event, line_dict)
        )
    
    def add_picking_plane(self):
        """Add a transparent plane at the current slice position for picking during line drawing."""
        # Remove any existing picking plane first
        if 'picking_plane' in self.plotter.renderer.actors:
            self.plotter.remove_actor('picking_plane')
            self.print_terminal("Removed old picking plane")
        
        if not hasattr(self, 'current_slice_bounds') or self.current_slice_bounds is None:
            self.print_terminal("No slice bounds available for picking plane")
            return
            
        bounds = self.current_slice_bounds
        
        self.print_terminal(f"DEBUG: Creating picking plane at slice position {self.current_slice_position} for {self.current_axis} index {self.current_slice_index}")
        self.print_terminal(f"DEBUG: Bounds: {bounds}")
        
        # Get vertical exaggeration to position plane in display space
        v_exag = 1.0
        try:
            scale = self.plotter.scale
            if scale is not None and len(scale) >= 3:
                v_exag = scale[2]
                if v_exag == 0:
                    v_exag = 1.0
        except:
            pass
        
        # Create a plane mesh for picking.
        # It must be in DISPLAY coordinates (with VE applied) because the tracer picks in rendered space.
        plane = None
        affine = self._get_seismic_axis_vectors()
        if affine is not None:
            plane_info = self._get_slice_plane_from_affine(
                slice_idx=self.current_slice_index,
                affine=affine,
                axis=self.current_axis,
            )
            if plane_info is not None:
                plane_center, plane_normal, row_vec, col_vec, dims = plane_info
                disp_center, disp_normal, i_size, j_size = self._get_display_plane_from_affine(
                    plane_center, plane_normal, row_vec, col_vec, dims, v_exag
                )
                plane = pv.Plane(
                    center=disp_center,
                    direction=disp_normal,
                    i_size=i_size,
                    j_size=j_size,
                    i_resolution=1,
                    j_resolution=1
                )
                self.print_terminal(
                    f"DEBUG: Affine picking plane center: {disp_center}, normal: {disp_normal}"
                )

        if plane is None:
            # Fallback to axis-aligned planes
            if self.current_axis == 'Inline':
                # YZ plane at current X position
                plane_center = (self.current_slice_position, (bounds[2]+bounds[3])/2, (bounds[4]+bounds[5])/2 * v_exag)
                plane = pv.Plane(
                    center=plane_center,
                    direction=(1, 0, 0),  # Normal along X
                    i_size=bounds[3] - bounds[2],  # Y extent
                    j_size=abs(bounds[5] - bounds[4]) * v_exag,  # Z extent with VE
                    i_resolution=1,
                    j_resolution=1
                )
                self.print_terminal(f"DEBUG: Inline picking plane center: {plane_center}")
            elif self.current_axis == 'Crossline':
                # XZ plane at current Y position
                plane_center = ((bounds[0]+bounds[1])/2, self.current_slice_position, (bounds[4]+bounds[5])/2 * v_exag)
                plane = pv.Plane(
                    center=plane_center,
                    direction=(0, 1, 0),  # Normal along Y
                    i_size=bounds[1] - bounds[0],  # X extent
                    j_size=abs(bounds[5] - bounds[4]) * v_exag,  # Z extent with VE
                    i_resolution=1,
                    j_resolution=1
                )
                self.print_terminal(f"DEBUG: Crossline picking plane center: {plane_center}")
            elif self.current_axis == 'Z-slice':
                # XY plane at current Z position (scaled)
                plane_center = ((bounds[0]+bounds[1])/2, (bounds[2]+bounds[3])/2, self.current_slice_position * v_exag)
                plane = pv.Plane(
                    center=plane_center,
                    direction=(0, 0, 1),  # Normal along Z
                    i_size=bounds[1] - bounds[0],  # X extent
                    j_size=bounds[3] - bounds[2],  # Y extent
                    i_resolution=1,
                    j_resolution=1
                )
                self.print_terminal(f"DEBUG: Z-slice picking plane center: {plane_center}")
        
        # Add the plane with very low opacity so it's invisible but pickable
        self.plotter.add_mesh(
            plane,
            name='picking_plane',
            color='white',
            opacity=0.01,  # Nearly invisible
            pickable=True,
            reset_camera=False
        )
        self.print_terminal(f"Added picking plane at {self.current_axis} position {self.current_slice_position} (VE={v_exag})")
        
        # Debug: print plane bounds to verify it's at the right position
        self.print_terminal(f"Picking plane bounds: {plane.bounds}")

    def snap_points_to_slice(self, points, points_are_display_coords=True):
        """Snap points to the current slice plane based on the current axis and slice position.
        Points from the tracer are typically in display coordinates (with VE applied), so
        convert them back to real world coordinates before storing when requested."""
        snapped = points.copy()
        
        # Get the current vertical exaggeration from the plotter scale
        v_exag = 1.0
        try:
            scale = self.plotter.scale
            if scale is not None and len(scale) >= 3:
                v_exag = scale[2]  # Z scale is vertical exaggeration
                if v_exag == 0:
                    v_exag = 1.0
        except:
            pass
        
        self.print_terminal(f"Snapping with v_exag={v_exag}, axis={self.current_axis}, slice_pos={self.current_slice_position}")
        
        # Only Z coordinates need to be unscaled when the picked points come from
        # display-space interactions such as traced contours on the rendered slice.
        if points_are_display_coords and v_exag != 1.0:
            snapped[:, 2] = snapped[:, 2] / v_exag
            self.print_terminal(f"Unscaled Z by factor {v_exag}")
        
        # Snap to the true slice plane if available (rotated/skewed grids)
        plane_center = getattr(self, "current_slice_plane_center", None)
        plane_normal = getattr(self, "current_slice_plane_normal", None)
        if plane_center is not None and plane_normal is not None:
            try:
                snapped = self._project_points_to_plane(snapped, plane_center, plane_normal)
            except Exception:
                pass
        else:
            # Fallback to axis-aligned snapping
            if self.current_axis == 'Inline':
                # For inline view (YZ plane), X must be constant
                snapped[:, 0] = self.current_slice_position
                self.print_terminal(f"Snapped X to {self.current_slice_position}")
            elif self.current_axis == 'Crossline':
                # For crossline view (XZ plane), Y must be constant
                snapped[:, 1] = self.current_slice_position
                self.print_terminal(f"Snapped Y to {self.current_slice_position}")
            elif self.current_axis == 'Z-slice':
                # For Z-slice view (XY plane), Z must be constant
                snapped[:, 2] = self.current_slice_position
                self.print_terminal(f"Snapped Z to {self.current_slice_position}")
        
        self.print_terminal(f"Final snapped points range: X=[{snapped[:, 0].min():.2f}, {snapped[:, 0].max():.2f}], Y=[{snapped[:, 1].min():.2f}, {snapped[:, 1].max():.2f}], Z=[{snapped[:, 2].min():.2f}, {snapped[:, 2].max():.2f}]")
        
        return snapped

    def update_interpretation_line_visibility(self):
        """Update visibility of interpretation lines based on current slice.
        
        OPTIMIZED: Uses spatial hash map (interpretation_lines_by_slice) for O(1) lookup
        instead of iterating through all lines.
        """
        # Ensure we have a valid state
        if not self.current_seismic_uid:
            return

        cache_key = (self.current_seismic_uid, self.current_axis, self.current_slice_index)
        
        # Avoid redundant updates if nothing changed
        if hasattr(self, '_last_visibility_key') and self._last_visibility_key == cache_key:
            # Check if any new lines were added that invalidated the clean state
            if not getattr(self, '_visibility_dirty', False):
                return
        
        self._last_visibility_key = cache_key
        self._visibility_dirty = False
        
        try:
            # 1. Get the set of UIDs that SHOULD be visible on this slice
            target_uids = set(self.interpretation_lines_by_slice.get(cache_key, set()))
            target_uids = {
                uid for uid in target_uids if self._is_uid_enabled_in_tree(uid)
            }
            
            # 2. Track currently visible lines to minimize VTK calls
            if not hasattr(self, 'vis_lines_on_display'):
                self.vis_lines_on_display = set()
            
            # If we don't track what's currently visible properly, we might just assume 
            # we need to hide everything that is NOT in target_uids but IS in interpretation_lines
            # However, iterating self.interpretation_lines is O(N).
            # Better approach:
            # - Hide everything in self.vis_lines_on_display that is NOT in target_uids
            # - Show everything in target_uids that is NOT in self.vis_lines_on_display
            
            to_hide = self.vis_lines_on_display - target_uids
            to_show = target_uids - self.vis_lines_on_display
            
            # Batch apply changes
            
            # HIDE
            for uid in to_hide:
                self.set_actor_visibility(uid, False)
                
            # SHOW
            for uid in to_show:
                self.set_actor_visibility(uid, True)
            
            # Update state
            self.vis_lines_on_display = target_uids.copy()
                        
        except Exception as e:
            self.print_terminal(f"Error updating interpretation line visibility: {e}")
            self.print_terminal(traceback_format_exc())

    def set_actor_visibility(self, uid, visible):
        """Helper to safely set actor visibility with caching."""
        if not hasattr(self, '_actor_cache'):
            self._actor_cache = {}
            
        actor = self._actor_cache.get(uid)
        
        if actor is None:
            # Try direct UID lookup first (most common)
            if uid in self.plotter.renderer.actors:
                actor = self.plotter.renderer.actors[uid]
            else:
                # Try prefixed names
                for prefix in ['geol_coll_', 'geo_']:
                    actor_name = f"{prefix}{uid}"
                    if actor_name in self.plotter.renderer.actors:
                        actor = self.plotter.renderer.actors[actor_name]
                        break
            
            if actor:
                self._actor_cache[uid] = actor
        
        if actor:
            actor.SetVisibility(visible)

    def register_interpretation_line(self, uid, slice_info):
        """Register a line in both the main dict and the spatial index."""
        self.interpretation_lines[uid] = slice_info
        self._store_single_slice_interpretation_metadata(uid=uid, slice_info=slice_info)
        
        key = (slice_info['seismic_uid'], slice_info['axis'], slice_info['slice_index'])
        if key not in self.interpretation_lines_by_slice:
            self.interpretation_lines_by_slice[key] = set()
        self.interpretation_lines_by_slice[key].add(uid)
        
        # Enforce visibility immediately to ensure sync with new actors
        # This fixes the issue where newly propagated lines (shown by default in on_entities_added)
        # stay visible because the optimized visibility update loop doesn't know about them yet.
        
        # Skip visual update if propagating (batch mode)
        if hasattr(self, '_is_propagating') and self._is_propagating:
            return

        matches_current = (
            slice_info['seismic_uid'] == self.current_seismic_uid and
            slice_info['axis'] == self.current_axis and
            slice_info['slice_index'] == self.current_slice_index and
            self._is_uid_enabled_in_tree(uid)
        )
        
        self.set_actor_visibility(uid, matches_current)
        
        # Keep the visibility tracking set in sync
        if hasattr(self, 'vis_lines_on_display'):
            if matches_current:
                self.vis_lines_on_display.add(uid)
            elif uid in self.vis_lines_on_display:
                self.vis_lines_on_display.remove(uid)
        
        # Mark visibility as dirty just in case
        self._visibility_dirty = True
        
    def unregister_interpretation_line(self, uid):
        """Remove a line from tracking."""
        if uid in self.interpretation_lines:
            slice_info = self.interpretation_lines[uid]
            key = (slice_info['seismic_uid'], slice_info['axis'], slice_info['slice_index'])
            
            if key in self.interpretation_lines_by_slice:
                if uid in self.interpretation_lines_by_slice[key]:
                    self.interpretation_lines_by_slice[key].remove(uid)
                    # Clean up empty sets to save memory
                    if not self.interpretation_lines_by_slice[key]:
                        del self.interpretation_lines_by_slice[key]
            
            del self.interpretation_lines[uid]
            self._visibility_dirty = True

    def update_multipart_horizon_visibility(self, uid=None):
        """
        Update visibility of multipart horizon lines by extracting only the cells
        that match the current slice and creating a filtered actor.
        
        Args:
            uid: Specific horizon UID to update, or None to update all multipart horizons
        """
        if not hasattr(self, 'multipart_horizons'):
            return
        
        if not self.multipart_horizons:
            return
        
        uids_to_update = [uid] if uid else list(self.multipart_horizons.keys())
        
        for horizon_uid in uids_to_update:
            if horizon_uid not in self.multipart_horizons:
                continue
                
            horizon_info = self.multipart_horizons[horizon_uid]
            actor_name = f"multipart_slice_{horizon_uid}"
            
            # ALWAYS remove the old filtered actor first to prevent accumulation
            # Try multiple methods to ensure it's removed
            try:
                self._remove_filtered_actor(actor_name)
            except Exception:
                pass
            # Multipart horizons must never leak their full actor into the slice view.
            self._remove_raw_actor_for_uid(horizon_uid)

            if not self._is_uid_enabled_in_tree(horizon_uid):
                self.set_actor_visibility(horizon_uid, False)
                continue
            
            # Check if this horizon matches current view context
            if (horizon_info['seismic_uid'] != self.current_seismic_uid or 
                horizon_info['axis'] != self.current_axis):
                # Hide completely if not matching seismic/axis
                self.set_actor_visibility(horizon_uid, False)
                continue
            
            # Check if current slice is in this horizon's range
            if self.current_slice_index not in horizon_info['slice_indices']:
                # Hide if current slice is not in this horizon
                self.set_actor_visibility(horizon_uid, False)
                continue
            
            # Get the VTK object
            try:
                vtk_obj = self.parent.geol_coll.get_uid_vtk_obj(horizon_uid)
                if vtk_obj is None:
                    continue
            except Exception:
                continue
            
            # Extract only cells matching current slice using direct cell iteration
            try:
                # Check if slice_index array exists
                if not vtk_obj.GetCellData().HasArray("slice_index"):
                    self.print_terminal(f"  Warning: No slice_index array in {horizon_uid}")
                    # No slice data - show the full horizon for this slice
                    self.set_actor_visibility(horizon_uid, True)
                    continue
                
                slice_array = vtk_obj.GetCellData().GetArray("slice_index")
                n_cells = vtk_obj.GetNumberOfCells()
                
                # Find cells that match the current slice index
                matching_cell_ids = []
                for i in range(n_cells):
                    cell_slice_idx = int(slice_array.GetValue(i))
                    if cell_slice_idx == self.current_slice_index:
                        matching_cell_ids.append(i)
                
                if len(matching_cell_ids) == 0:
                    self.set_actor_visibility(horizon_uid, False)
                    continue

                filtered_polydata, _, _ = self._build_multipart_subset_vtk(
                    vtk_obj=vtk_obj,
                    kept_cell_ids=matching_cell_ids,
                )
                if filtered_polydata is None:
                    self.set_actor_visibility(horizon_uid, False)
                    continue

                n_filtered_cells = filtered_polydata.GetNumberOfCells()
                n_filtered_points = filtered_polydata.GetNumberOfPoints()
                
                if n_filtered_cells > 0 and n_filtered_points > 0:
                    # Use standard geological legend style (same behavior as other views).
                    style = self._get_geol_legend_style(horizon_uid)
                    
                    # Add new filtered actor
                    self.plotter.add_mesh(
                        pv.wrap(filtered_polydata),
                        name=actor_name,
                        color=style["color"],
                        line_width=style["line_width"],
                        opacity=style["opacity"],
                        render_lines_as_tubes=True,
                        pickable=True,
                        reset_camera=False
                    )
                    
                    # Hide the full multipart actor (we're showing the filtered version)
                    self.set_actor_visibility(horizon_uid, False)
                else:
                    # No cells match - just hide (actor already removed above)
                    self.set_actor_visibility(horizon_uid, False)
                    
            except Exception as e:
                self.print_terminal(f"Error filtering multipart horizon {horizon_uid}: {e}")
                self.print_terminal(traceback_format_exc())
                # Fall back to showing full horizon
                self.set_actor_visibility(horizon_uid, True)

    def update_all_multipart_horizons_visibility(self):
        """Update visibility for all multipart horizons based on current slice."""
        if not hasattr(self, 'multipart_horizons'):
            return
        
        for uid in list(self.multipart_horizons.keys()):
            self.update_multipart_horizon_visibility(uid)

    def update_multipart_fault_visibility(self, uid=None):
        """
        Update visibility of multipart fault lines by extracting only the cells
        that match the current slice and creating a filtered actor.
        
        Args:
            uid: Specific fault UID to update, or None to update all multipart faults
        """
        
        if not hasattr(self, 'multipart_faults'):
            return
        
        if not self.multipart_faults:
            return
        
        uids_to_update = [uid] if uid else list(self.multipart_faults.keys())
        
        for fault_uid in uids_to_update:
            if fault_uid not in self.multipart_faults:
                continue
            
            fault_info = self.multipart_faults[fault_uid]
            actor_name = f"multipart_fault_slice_{fault_uid}"
            
            # ALWAYS remove the old filtered actor first to prevent accumulation
            # Try multiple methods to ensure it's removed
            try:
                self._remove_filtered_actor(actor_name)
            except Exception:
                pass

            if not self._is_uid_enabled_in_tree(fault_uid):
                self.set_actor_visibility(fault_uid, False)
                continue
            
            # Check if this fault matches current view context
            if (fault_info['seismic_uid'] != self.current_seismic_uid or
                fault_info['axis'] != self.current_axis):
                # Hide completely if not matching seismic/axis
                self.set_actor_visibility(fault_uid, False)
                continue
            
            # Check if current slice is in this fault's range
            if 'slice_indices' in fault_info and self.current_slice_index not in fault_info['slice_indices']:
                self.set_actor_visibility(fault_uid, False)
                continue
            
            # Get the original VTK object
            try:
                vtk_obj = self.parent.geol_coll.get_uid_vtk_obj(fault_uid)
                if vtk_obj is None:
                    continue
            except:
                continue
            
            # Check if slice_index array exists
            if not vtk_obj.GetCellData().HasArray("slice_index"):
                # No slice data, show entire fault
                self.set_actor_visibility(fault_uid, True)
                continue
            
            # Hide the original full actor
            self.set_actor_visibility(fault_uid, False)
            
            # Extract cells matching current slice using direct iteration
            slice_array = vtk_obj.GetCellData().GetArray("slice_index")
            n_cells = vtk_obj.GetNumberOfCells()
            
            # Find cells that match the current slice index
            matching_cell_ids = []
            for i in range(n_cells):
                cell_slice_idx = int(slice_array.GetValue(i))
                if cell_slice_idx == self.current_slice_index:
                    matching_cell_ids.append(i)
            
            if len(matching_cell_ids) == 0:
                continue
            
            # Extract the matching cells manually
            new_points = vtkPoints()
            new_lines = vtkCellArray()
            point_map = {}  # old_id -> new_id
            
            for cell_id in matching_cell_ids:
                cell = vtk_obj.GetCell(cell_id)
                n_pts = cell.GetNumberOfPoints()
                
                new_line_pts = []
                for j in range(n_pts):
                    old_pt_id = cell.GetPointId(j)
                    
                    if old_pt_id not in point_map:
                        pt = vtk_obj.GetPoint(old_pt_id)
                        new_pt_id = new_points.InsertNextPoint(pt)
                        point_map[old_pt_id] = new_pt_id
                    
                    new_line_pts.append(point_map[old_pt_id])
                
                # Add the line cell
                new_lines.InsertNextCell(len(new_line_pts))
                for pt_id in new_line_pts:
                    new_lines.InsertCellPoint(pt_id)
            
            # Create filtered polydata
            filtered_polydata = vtkPolyData()
            filtered_polydata.SetPoints(new_points)
            filtered_polydata.SetLines(new_lines)
            
            n_filtered_cells = filtered_polydata.GetNumberOfCells()
            n_filtered_points = filtered_polydata.GetNumberOfPoints()
            
            if n_filtered_cells > 0 and n_filtered_points > 0:
                # Use standard geological legend style (same behavior as other views).
                style = self._get_geol_legend_style(fault_uid)
                
                # Add filtered actor
                self.plotter.add_mesh(
                    pv.wrap(filtered_polydata),
                    name=actor_name,
                    color=style["color"],
                    line_width=style["line_width"],
                    opacity=style["opacity"],
                    render_lines_as_tubes=True,
                    pickable=True,
                    reset_camera=False
                )

    def update_all_multipart_faults_visibility(self):
        """Update visibility for all multipart faults based on current slice."""
        if not hasattr(self, 'multipart_faults'):
            return
        
        for uid in list(self.multipart_faults.keys()):
            self.update_multipart_fault_visibility(uid)
    
    def scan_and_index_existing_horizons(self):
        """
        Scan all PolyLines in the project. If they align spatially with the current seismic volume,
        index them so they are only shown on the correct slice.
        O(N) operation runs once per volume load.
        """
        if getattr(self, '_lines_indexed', False):
            return

        self.print_terminal("Scanning existing horizons to index for efficient slicing...")
        
        count = 0
        try:
            # Get all geological entities
            all_uids = self.parent.geol_coll.get_uids
            
            # We will batch-hide everything first to ensure clean state? 
            # Or just let update_interpretation_line_visibility handle it.
            # Only process PolyLines
            
            for uid in all_uids:
                if uid in self.interpretation_lines:
                    continue
                
                # Check topology
                if self.parent.geol_coll.get_uid_topology(uid) != 'PolyLine':
                    continue
                
                self.scan_and_index_single_horizon(uid)
                count += 1
                
        except Exception as e:
            self.print_terminal(f"Error scanning horizons: {e}")
            self.print_terminal(traceback_format_exc())
            
        self._lines_indexed = True
        self.print_terminal(f"Indexing complete. Processed {count} potential horizons.")
        
        # Update visibility for both regular interpretation lines and multipart horizons/faults
        self.update_interpretation_line_visibility()
        self.update_all_multipart_horizons_visibility()
        self.update_all_multipart_faults_visibility()
    
    def scan_and_index_single_horizon(self, uid):
        """Check if a single horizon fits the current seismic grid and index it."""
        try:
            vtk_obj = self.parent.geol_coll.get_uid_vtk_obj(uid)
            if not vtk_obj or vtk_obj.GetNumberOfPoints() == 0:
                return

            explicit_slice_info = self._extract_single_slice_interpretation_metadata(
                uid=uid, vtk_obj=vtk_obj
            )
            if explicit_slice_info is not None:
                self.register_interpretation_line(uid, explicit_slice_info)
                self.set_actor_visibility(uid, False)
                return

            # First check if this is a multipart horizon (has slice_index cell data)
            # This is more efficient than checking geometry, and handles propagated horizons
            cell_data = vtk_obj.GetCellData()
            if cell_data and cell_data.HasArray("slice_index"):
                self._ensure_slice_index_property_metadata(uid=uid, vtk_obj=vtk_obj)
                # This is a multipart horizon! Reconstruct its metadata
                slice_array = cell_data.GetArray("slice_index")
                n_cells = vtk_obj.GetNumberOfCells()
                
                # Extract unique slice indices and build mapping
                slice_indices = []
                slice_to_cell_index = {}
                for i in range(n_cells):
                    slice_idx = int(slice_array.GetValue(i))
                    if slice_idx not in slice_to_cell_index:
                        slice_indices.append(slice_idx)
                        slice_to_cell_index[slice_idx] = i
                
                # First, try to get the axis from stored field data (preferred method)
                axis = None
                field_data = vtk_obj.GetFieldData()
                if field_data and field_data.HasArray("slice_axis"):
                    axis_array = field_data.GetAbstractArray("slice_axis")
                    if axis_array and axis_array.GetNumberOfValues() > 0:
                        axis = axis_array.GetValue(0)
                        self.print_terminal(f"  Recovered axis from field data: {axis}")
                
                # Fall back to geometry detection if no stored axis
                if axis is None:
                    # Determine axis by checking the geometry of the first cell's points
                    # Get first cell points to detect which plane it lies in
                    first_cell = vtk_obj.GetCell(0)
                    n_pts = first_cell.GetNumberOfPoints()
                    if n_pts > 0:
                        # Sample more points for better accuracy
                        pts = [first_cell.GetPoints().GetPoint(i) for i in range(min(n_pts, 50))]
                        xs = [p[0] for p in pts]
                        ys = [p[1] for p in pts]
                        zs = [p[2] for p in pts]
                        
                        x_range = max(xs) - min(xs)
                        y_range = max(ys) - min(ys)
                        z_range = max(zs) - min(zs)
                        
                        # Determine which axis has minimal variation (that's the slice axis)
                        # Use a more robust comparison: check which dimension has the smallest range
                        # relative to the total span, or is essentially zero
                        ranges = [('Inline', x_range), ('Crossline', y_range), ('Z-slice', z_range)]
                        
                        # Sort by range to find the smallest
                        ranges.sort(key=lambda r: r[1])
                        smallest_axis, smallest_range = ranges[0]
                        second_axis, second_range = ranges[1]
                        
                        # The axis with smallest range is the slice axis, but only if it's
                        # significantly smaller than the others (at least 10x smaller, or near zero)
                        total_range = x_range + y_range + z_range
                        if total_range > 0:
                            if smallest_range < 0.01 * total_range or smallest_range < second_range * 0.1:
                                axis = smallest_axis
                            else:
                                # Default to current axis if detection is ambiguous
                                axis = self.current_axis
                        else:
                            axis = self.current_axis
                        
                        self.print_terminal(f"  Detected axis from geometry: {axis} (ranges: X={x_range:.2f}, Y={y_range:.2f}, Z={z_range:.2f})")
                
                # If axis is still None (no field data and geometry detection failed), default to current axis
                if axis is None:
                    axis = self.current_axis
                    self.print_terminal(f"  Using current axis as fallback: {axis}")
                    
                entity_kind = self._register_multipart_interpretation_entity(
                    uid=uid,
                    axis=axis,
                    slice_indices=slice_indices,
                    slice_to_cell_index=slice_to_cell_index,
                )
                
                self.print_terminal(
                    f"Registered multipart {entity_kind} {uid}: {len(slice_indices)} slices on {axis}"
                )
                # IMPORTANT: Hide the full horizon actor - we will only show filtered slices
                self.set_actor_visibility(uid, False)
                # Also try to remove it from renderer completely to prevent it showing
                try:
                    if uid in self.plotter.renderer.actors:
                        self.plotter.remove_actor(uid)
                except:
                    pass
                return
            
            # Not a multipart horizon - check if it's a single-slice interpretation line
            bounds = vtk_obj.GetBounds() # (xmin, xmax, ymin, ymax, zmin, zmax)
            
            # Get metadata about current seismic
            # We need the real internal spatial reference (origin/spacing) 
            # which we cache in get_slice_as_2d_array logic or need to access again.
            
            if not hasattr(self, '_cached_bounds') or not self._cached_bounds:
                return

            seismic_bounds = self._cached_bounds
            seismic_dims = self._cached_dims

            # Try to recover multipart slice metadata from geometry when slice_index arrays
            # are missing (e.g. after generic merge/split operations).
            if self._try_register_multipart_from_geometry(
                uid=uid,
                vtk_obj=vtk_obj,
                seismic_bounds=seismic_bounds,
                seismic_dims=seismic_dims,
            ):
                self._ensure_slice_index_property_metadata(uid=uid, vtk_obj=vtk_obj)
                return
            
            # Calculate spacing on the fly (assuming regular grid)
            dx = (seismic_bounds[1] - seismic_bounds[0]) / max(seismic_dims[0] - 1, 1)
            dy = (seismic_bounds[3] - seismic_bounds[2]) / max(seismic_dims[1] - 1, 1)
            dz = (seismic_bounds[5] - seismic_bounds[4]) / max(seismic_dims[2] - 1, 1)

            # Spacing-aware tolerance for "flatness" to handle operations introducing
            # small numerical offsets along the nominal slice axis.
            tol_x = max(abs(dx) * 0.35, 1e-3)
            tol_y = max(abs(dy) * 0.35, 1e-3)
            tol_z = max(abs(dz) * 0.35, 1e-3)
            x_range = abs(bounds[1] - bounds[0])
            y_range = abs(bounds[3] - bounds[2])
            z_range = abs(bounds[5] - bounds[4])
            min_span_guard = 1e-9

            # Check for Inline (YZ plane, X is constant)
            if x_range < tol_x and x_range < 0.1 * max(y_range, z_range, min_span_guard):
                # Calculate which slice index this corresponds to
                # x = bounds[0] (or center)
                x_pos = (bounds[0] + bounds[1]) / 2.0
                
                # Inverse mapping: index = (pos - origin) / spacing
                # Should match world_to_slice_coords logic
                if dx > 0:
                    idx_float = (x_pos - seismic_bounds[0]) / dx
                    idx = int(round(idx_float))
                    
                    # Verify it's actually close to an integer index
                    if abs(idx_float - idx) < 0.1:
                        if 0 <= idx < seismic_dims[0]:
                            self.register_interpretation_line(uid, {
                                'seismic_uid': self.current_seismic_uid,
                                'axis': 'Inline',
                                'slice_index': idx
                            })
                            # Initially hide it (visibility update will show it if it matches current)
                            self.set_actor_visibility(uid, False)
                            return

            # Check for Crossline (XZ plane, Y is constant)
            if y_range < tol_y and y_range < 0.1 * max(x_range, z_range, min_span_guard):
                y_pos = (bounds[2] + bounds[3]) / 2.0
                if dy > 0:
                    idx_float = (y_pos - seismic_bounds[2]) / dy
                    idx = int(round(idx_float))
                    if abs(idx_float - idx) < 0.1:
                        if 0 <= idx < seismic_dims[1]:
                            self.register_interpretation_line(uid, {
                                'seismic_uid': self.current_seismic_uid,
                                'axis': 'Crossline',
                                'slice_index': idx
                            })
                            self.set_actor_visibility(uid, False)
                            return

            # Check for Z-slice (XY plane, Z is constant)
            if z_range < tol_z and z_range < 0.1 * max(x_range, y_range, min_span_guard):
                z_pos = (bounds[4] + bounds[5]) / 2.0
                if dz > 0:
                    idx_float = (z_pos - seismic_bounds[4]) / dz
                    idx = int(round(idx_float))
                    if abs(idx_float - idx) < 0.1:
                         if 0 <= idx < seismic_dims[2]:
                            self.register_interpretation_line(uid, {
                                'seismic_uid': self.current_seismic_uid,
                                'axis': 'Z-slice',
                                'slice_index': idx
                            })
                            self.set_actor_visibility(uid, False)
                            return

        except Exception as e:
            # self.print_terminal(f"Debug: failed to scan {uid}: {e}")
            pass

    def _try_register_multipart_from_geometry(self, uid, vtk_obj, seismic_bounds, seismic_dims):
        """
        Infer per-cell slice indices from geometry for polylines missing slice_index arrays.
        This is used to preserve slice-aware visibility after generic merge/split operations.
        """
        try:
            n_cells = vtk_obj.GetNumberOfCells()
            if n_cells < 2:
                return False

            dx = (seismic_bounds[1] - seismic_bounds[0]) / max(seismic_dims[0] - 1, 1)
            dy = (seismic_bounds[3] - seismic_bounds[2]) / max(seismic_dims[1] - 1, 1)
            dz = (seismic_bounds[5] - seismic_bounds[4]) / max(seismic_dims[2] - 1, 1)
            axis_specs = [
                ("Inline", 0, seismic_bounds[0], dx, seismic_dims[0]),
                ("Crossline", 1, seismic_bounds[2], dy, seismic_dims[1]),
                ("Z-slice", 2, seismic_bounds[4], dz, seismic_dims[2]),
            ]

            best = None
            for axis_name, coord_idx, origin, spacing, dim_n in axis_specs:
                if abs(spacing) <= 0:
                    continue

                per_cell = {}
                spreads = []
                frac_err = []
                for cell_id in range(n_cells):
                    cell = vtk_obj.GetCell(cell_id)
                    pts = cell.GetPoints() if cell is not None else None
                    if pts is None:
                        continue
                    n_pts = pts.GetNumberOfPoints()
                    if n_pts < 2:
                        continue

                    coords = [pts.GetPoint(i)[coord_idx] for i in range(n_pts)]
                    c_min = min(coords)
                    c_max = max(coords)
                    c_avg = (c_min + c_max) * 0.5
                    idx_float = (c_avg - origin) / spacing
                    idx_round = int(round(idx_float))
                    if idx_round < 0 or idx_round >= dim_n:
                        continue

                    per_cell[cell_id] = idx_round
                    spreads.append(abs(c_max - c_min) / max(abs(spacing), 1e-12))
                    frac_err.append(abs(idx_float - idx_round))

                if not per_cell:
                    continue

                unique_slices = sorted(set(per_cell.values()))
                if len(unique_slices) < 2:
                    continue

                med_spread = float(np.median(spreads)) if spreads else 1e9
                med_err = float(np.median(frac_err)) if frac_err else 1e9

                # Keep only strong slice-grid fits.
                if med_spread > 0.45 or med_err > 0.45:
                    continue

                score = med_spread + med_err
                candidate = (axis_name, per_cell, unique_slices, score)
                if best is None:
                    best = candidate
                else:
                    _, _, best_slices, best_score = best
                    if (len(unique_slices), -score) > (len(best_slices), -best_score):
                        best = candidate

            if best is None:
                return False

            axis_name, per_cell, unique_slices, _ = best


            # Build cell-level slice_index array.
            cell_slice_arr = vtkIntArray()
            cell_slice_arr.SetName("slice_index")
            cell_slice_arr.SetNumberOfComponents(1)
            for cell_id in range(n_cells):
                cell_slice_arr.InsertNextValue(int(per_cell.get(cell_id, -1)))
            cell_data = vtk_obj.GetCellData()
            if cell_data and cell_data.HasArray("slice_index"):
                cell_data.RemoveArray("slice_index")
            vtk_obj.GetCellData().AddArray(cell_slice_arr)

            # Build point-level slice_index array (best effort from first owning cell).
            n_points = vtk_obj.GetNumberOfPoints()
            point_slice = [-1] * n_points
            for cell_id, sidx in per_cell.items():
                cell = vtk_obj.GetCell(cell_id)
                if cell is None:
                    continue
                for j in range(cell.GetNumberOfPoints()):
                    pid = cell.GetPointId(j)
                    if 0 <= pid < n_points and point_slice[pid] < 0:
                        point_slice[pid] = int(sidx)
            point_slice_arr = vtkIntArray()
            point_slice_arr.SetName("slice_index")
            point_slice_arr.SetNumberOfComponents(1)
            for sidx in point_slice:
                point_slice_arr.InsertNextValue(int(sidx))
            point_data = vtk_obj.GetPointData()
            if point_data and point_data.HasArray("slice_index"):
                point_data.RemoveArray("slice_index")
            vtk_obj.GetPointData().AddArray(point_slice_arr)

            # Store axis in field data.
            axis_arr = vtkStringArray()
            axis_arr.SetName("slice_axis")
            axis_arr.SetNumberOfValues(1)
            axis_arr.SetValue(0, axis_name)
            field_data = vtk_obj.GetFieldData()
            if field_data and field_data.HasArray("slice_axis"):
                field_data.RemoveArray("slice_axis")
            vtk_obj.GetFieldData().AddArray(axis_arr)
            vtk_obj.Modified()

            self._register_multipart_interpretation_entity(
                uid=uid,
                axis=axis_name,
                slice_indices=unique_slices,
                slice_to_cell_index={sidx: cid for cid, sidx in per_cell.items()},
            )

            self.print_terminal(
                f"Recovered multipart slice metadata for {uid[:8]}... ({axis_name}, {len(unique_slices)} slices)"
            )
            self.set_actor_visibility(uid, False)
            return True
        except Exception:
            return False
    
    def _invalidate_actor_cache(self, uid=None):
        """Invalidate actor cache when entities are added/removed."""
        if not hasattr(self, '_actor_cache'):
            return
        if uid is None:
            self._actor_cache.clear()
        elif uid in self._actor_cache:
            del self._actor_cache[uid]

    def _remove_raw_actor_for_uid(self, uid):
        """Remove any raw full-geometry actor for a slice-filtered entity."""
        for actor_name in (uid, f"geol_coll_{uid}", f"geo_{uid}"):
            try:
                if actor_name in self.plotter.renderer.actors:
                    self.plotter.remove_actor(actor_name)
            except Exception:
                pass
        self._invalidate_actor_cache(uid)

    def _suppress_full_multipart_actors(self):
        """Ensure propagated multipart entities are never shown as full actors."""
        for uid in list(getattr(self, "multipart_horizons", {}).keys()):
            self._remove_raw_actor_for_uid(uid)
        for uid in list(getattr(self, "multipart_faults", {}).keys()):
            self._remove_raw_actor_for_uid(uid)
        # Also invalidate the visibility key to force update
        if hasattr(self, '_last_visibility_key'):
            del self._last_visibility_key

    def _remove_filtered_actor(self, actor_name):
        """Remove a slice-filtered actor if it exists in the renderer."""
        if not actor_name:
            return
        try:
            self.plotter.remove_actor(actor_name)
        except Exception:
            pass
        try:
            actors = getattr(self.plotter.renderer, "actors", {})
            if actor_name in actors:
                actor = actors[actor_name]
                self.plotter.renderer.RemoveActor(actor)
                del actors[actor_name]
        except Exception:
            pass

    def _is_uid_enabled_in_tree(self, uid=None):
        """Return the current checkbox-driven visibility state for a uid."""
        actor_row = self._actors_df_row_safe(uid=uid)
        if actor_row.empty:
            return True
        try:
            return bool(actor_row["show"].to_list()[0])
        except Exception:
            return True

    def _is_slice_filtered_uid(self, uid=None):
        """Return True for interpretation entities controlled by slice-aware visibility."""
        if not uid:
            return False
        if uid in getattr(self, "interpretation_lines", {}):
            return True
        if uid in getattr(self, "multipart_horizons", {}):
            return True
        if uid in getattr(self, "multipart_faults", {}):
            return True

        actor_row = self._actors_df_row_safe(uid=uid)
        if actor_row.empty:
            return False
        try:
            if actor_row["collection"].to_list()[0] != "geol_coll":
                return False
        except Exception:
            return False

        try:
            vtk_obj = self.parent.geol_coll.get_uid_vtk_obj(uid)
        except Exception:
            return False
        if vtk_obj is None:
            return False

        try:
            cell_data = vtk_obj.GetCellData()
            if cell_data and cell_data.HasArray("slice_index"):
                return True
        except Exception:
            pass

        return self._extract_single_slice_interpretation_metadata(
            uid=uid, vtk_obj=vtk_obj
        ) is not None

    def _mark_slice_visibility_dirty(self):
        """Force the next slice-aware visibility refresh to recompute state."""
        self._visibility_dirty = True
        if hasattr(self, "_last_visibility_key"):
            try:
                del self._last_visibility_key
            except Exception:
                pass

    def toggle_visibility(
        self, collection_name=None, turn_on_uids=None, turn_off_uids=None
    ):
        """
        Keep tree checkbox visibility in sync with slice-aware interpretation actors.
        """
        turn_on_uids = list(turn_on_uids or [])
        turn_off_uids = list(turn_off_uids or [])
        slice_filtered_uids = set()

        for uid in turn_on_uids:
            actor_row = self._actors_df_row_safe(uid=uid)
            if actor_row.empty:
                continue
            self.actors_df.loc[self.actors_df["uid"] == uid, "show"] = True
            if self._is_slice_filtered_uid(uid):
                slice_filtered_uids.add(uid)
                self.scan_and_index_single_horizon(uid)
                self.set_actor_visibility(uid, False)
                continue
            self.set_actor_visible(uid=uid, visible=True)

        for uid in turn_off_uids:
            actor_row = self._actors_df_row_safe(uid=uid)
            if actor_row.empty:
                continue
            self.actors_df.loc[self.actors_df["uid"] == uid, "show"] = False
            if self._is_slice_filtered_uid(uid):
                slice_filtered_uids.add(uid)
                self.set_actor_visibility(uid, False)
                self._remove_filtered_actor(f"multipart_slice_{uid}")
                self._remove_filtered_actor(f"multipart_fault_slice_{uid}")
                if hasattr(self, "vis_lines_on_display"):
                    self.vis_lines_on_display.discard(uid)
                continue
            self.set_actor_visible(uid=uid, visible=False)

        if not slice_filtered_uids:
            return

        self._mark_slice_visibility_dirty()
        self.update_interpretation_line_visibility()
        for uid in slice_filtered_uids:
            if uid in getattr(self, "multipart_horizons", {}):
                self.update_multipart_horizon_visibility(uid)
            if uid in getattr(self, "multipart_faults", {}):
                self.update_multipart_fault_visibility(uid)
        self.plotter.render()

    # ==================== Semi-Auto Tracking Methods ====================
    
    def compute_edge_cost_map(self, slice_data):
        """
        Compute edge detection cost map using Sobel filter.
        High edge strength = low cost (path prefers to follow horizons).
        
        Args:
            slice_data: 2D numpy array of seismic amplitudes
            
        Returns:
            cost_map: 2D numpy array where low values indicate strong edges (horizons)
        """
        # Normalize data to 0-1 range
        data_min = np.nanmin(slice_data)
        data_max = np.nanmax(slice_data)
        if data_max - data_min > 0:
            normalized = (slice_data - data_min) / (data_max - data_min)
        else:
            normalized = slice_data.copy()
        
        # Apply Sobel filter for edge detection
        # We use the vertical gradient (changes in amplitude along Z/time axis)
        # For seismic, horizons are typically horizontal features
        sobel_x = ndimage.sobel(normalized, axis=0)  # Horizontal edges
        sobel_y = ndimage.sobel(normalized, axis=1)  # Vertical edges
        
        # Combine gradients - magnitude of gradient
        edge_magnitude = np.sqrt(sobel_x**2 + sobel_y**2)
        
        # Normalize edge magnitude
        edge_max = np.nanmax(edge_magnitude)
        if edge_max > 0:
            edge_magnitude = edge_magnitude / edge_max
        
        # Invert: high edge strength = low cost
        # Add small epsilon to avoid zero costs
        cost_map = 1.0 - edge_magnitude + 0.01
        
        return cost_map

    def compute_fault_edge_cost_map(self, slice_data):
        """
        Compute a fault-oriented cost map.

        Faults appear as near-vertical discontinuities on Inline/Crossline sections.
        We therefore favor strong *vertical edges* (horizontal gradient).

        Returns:
            cost_map: 2D numpy array where low values indicate likely fault pixels
        """
        data_min = np.nanmin(slice_data)
        data_max = np.nanmax(slice_data)
        if data_max - data_min > 0:
            normalized = (slice_data - data_min) / (data_max - data_min)
        else:
            normalized = slice_data.copy()

        # Horizontal Sobel (axis=1) detects vertical edges
        sobel_horizontal = ndimage.sobel(normalized, axis=1)
        edge_strength = np.abs(sobel_horizontal)

        edge_max = np.nanmax(edge_strength)
        if edge_max > 0:
            edge_strength = edge_strength / edge_max

        # Invert: strong vertical edge => low cost
        return 1.0 - edge_strength + 0.01
    
    def add_existing_lines_to_cost_map(self, cost_map, axis_info, spacing, v_exag):
        """
        Add high-cost zones around existing interpretation lines on the current slice.
        This prevents new paths from jumping to or crossing existing horizons.
        
        Args:
            cost_map: 2D numpy array of costs (will be modified in place)
            axis_info: dict with bounds and axis info
            spacing: (dx, dy, dz) spacing
            v_exag: vertical exaggeration
            
        Returns:
            modified cost_map with existing lines marked as high cost
        """
        if not hasattr(self, 'interpretation_lines') or not self.interpretation_lines:
            return cost_map
        
        # Get existing lines on the current slice using spatial index (O(1))
        existing_line_uids = []
        cache_key = (self.current_seismic_uid, self.current_axis, self.current_slice_index)
        if cache_key in self.interpretation_lines_by_slice:
            existing_line_uids = list(self.interpretation_lines_by_slice[cache_key])
        
        if not existing_line_uids:
            self.print_terminal("No existing lines on current slice to avoid")
            return cost_map
        
        self.print_terminal(f"Found {len(existing_line_uids)} existing lines to avoid")
        
        # High cost value for forbidden zones
        FORBIDDEN_COST = 100.0
        # Radius around existing lines to mark as forbidden (in pixels)
        FORBIDDEN_RADIUS = 5
        
        for uid in existing_line_uids:
            try:
                # Get the VTK object for this line
                vtk_obj = self.parent.geol_coll.get_uid_vtk_obj(uid)
                if vtk_obj is None:
                    continue
                
                # Get points from the line
                points = np.array(vtk_obj.GetPoints().GetData())
                if len(points) == 0:
                    continue
                
                # Convert each point to slice coordinates and mark forbidden zone
                for point in points:
                    # Points are stored in REAL coordinates, need to convert to slice indices
                    # But we need to handle the coordinate system correctly
                    world_point = (point[0], point[1], point[2] * v_exag)  # Apply VE for display coords
                    slice_coord = self.world_to_slice_coords(world_point, axis_info, spacing, v_exag)
                    
                    row, col = int(slice_coord[0]), int(slice_coord[1])
                    
                    # Mark a zone around this point as high cost
                    for dr in range(-FORBIDDEN_RADIUS, FORBIDDEN_RADIUS + 1):
                        for dc in range(-FORBIDDEN_RADIUS, FORBIDDEN_RADIUS + 1):
                            r, c = row + dr, col + dc
                            if 0 <= r < cost_map.shape[0] and 0 <= c < cost_map.shape[1]:
                                # Use distance-based cost: closer = higher cost
                                dist = np.sqrt(dr**2 + dc**2)
                                if dist <= FORBIDDEN_RADIUS:
                                    # Exponential falloff from center
                                    penalty = FORBIDDEN_COST * (1 - dist / (FORBIDDEN_RADIUS + 1))
                                    cost_map[r, c] = max(cost_map[r, c], penalty)
                
                self.print_terminal(f"Marked forbidden zone for line {uid[:8]}...")
                
            except Exception as e:
                self.print_terminal(f"Error processing existing line {uid}: {e}")
                continue
        
        return cost_map
    
    def astar_pathfind(self, cost_map, start, end, corridor_width=None):
        """
        A* pathfinding algorithm to find optimal path between two points.
        CRITICAL: For seismic horizons, we constrain the VERTICAL (col/Z) axis
        to interpolate between start and end Z values, preventing jumps to other reflectors.
        
        Args:
            cost_map: 2D numpy array of costs (lower = preferred)
            start: (row, col) starting point - row is horizontal, col is vertical (Z/time)
            end: (row, col) ending point
            corridor_width: Maximum allowed vertical deviation from the interpolated Z value
            
        Returns:
            path: List of (row, col) points from start to end, or None if no path found
        """
        rows, cols = cost_map.shape
        
        # Validate start and end points
        start = (int(np.clip(start[0], 0, rows-1)), int(np.clip(start[1], 0, cols-1)))
        end = (int(np.clip(end[0], 0, rows-1)), int(np.clip(end[1], 0, cols-1)))
        
        # Heuristic: Euclidean distance
        def heuristic(a, b):
            return np.sqrt((a[0] - b[0])**2 + (a[1] - b[1])**2)
        
        # CRITICAL: For seismic horizons, constrain VERTICAL (col) position
        # The expected col (Z/time) at any row should interpolate between start and end
        def get_expected_col(row):
            """Get the expected column (Z) value at a given row by linear interpolation."""
            if start[0] == end[0]:
                return start[1]  # Same row, use start col
            # Linear interpolation of col based on row position
            t = (row - start[0]) / (end[0] - start[0])
            return start[1] + t * (end[1] - start[1])
        
        def is_in_vertical_corridor(point):
            """Check if point's col (Z) is within corridor of expected value."""
            if corridor_width is None:
                return True
            row, col = point
            expected_col = get_expected_col(row)
            deviation = abs(col - expected_col)
            return deviation <= corridor_width
        
        # 8-connected neighbors (including diagonals for smoother paths)
        neighbors = [(-1, 0), (1, 0), (0, -1), (0, 1),
                     (-1, -1), (-1, 1), (1, -1), (1, 1)]
        
        # Priority queue: (f_score, counter, node)
        counter = 0
        open_set = [(0, counter, start)]
        came_from = {}
        
        g_score = {start: 0}
        f_score = {start: heuristic(start, end)}
        
        visited = set()
        
        while open_set:
            current = heapq.heappop(open_set)[2]
            
            if current == end:
                # Reconstruct path
                path = [current]
                while current in came_from:
                    current = came_from[current]
                    path.append(current)
                path.reverse()
                return path
            
            if current in visited:
                continue
            visited.add(current)
            
            for dr, dc in neighbors:
                neighbor = (current[0] + dr, current[1] + dc)
                
                # Check bounds
                if not (0 <= neighbor[0] < rows and 0 <= neighbor[1] < cols):
                    continue
                
                if neighbor in visited:
                    continue
                
                # CRITICAL: Check vertical corridor constraint
                if not is_in_vertical_corridor(neighbor):
                    continue
                
                # Cost to move to neighbor
                move_cost = np.sqrt(2) if (dr != 0 and dc != 0) else 1.0
                
                # VERY STRONG penalty for vertical deviation from expected path
                if corridor_width is not None and corridor_width > 0:
                    expected_col = get_expected_col(neighbor[0])
                    vertical_deviation = abs(neighbor[1] - expected_col)
                    # Cubic penalty - strongly discourages vertical deviation
                    deviation_penalty = (vertical_deviation / max(corridor_width, 1)) ** 3 * 50.0
                else:
                    deviation_penalty = 0
                
                tentative_g = g_score[current] + cost_map[neighbor[0], neighbor[1]] * move_cost + deviation_penalty
                
                if neighbor not in g_score or tentative_g < g_score[neighbor]:
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    f_score[neighbor] = tentative_g + heuristic(neighbor, end)
                    counter += 1
                    heapq.heappush(open_set, (f_score[neighbor], counter, neighbor))
        
        # No path found
        return None

    def astar_pathfind_fault(self, cost_map, start, end, corridor_width=None):
        """
        A* pathfinding algorithm specialized for faults.

        CRITICAL: For faults, we constrain the HORIZONTAL (row/X) axis as a function
        of depth/time (col/Z), preventing the path from drifting to unrelated edges.
        """
        rows, cols = cost_map.shape

        start = (int(np.clip(start[0], 0, rows - 1)), int(np.clip(start[1], 0, cols - 1)))
        end = (int(np.clip(end[0], 0, rows - 1)), int(np.clip(end[1], 0, cols - 1)))

        def heuristic(a, b):
            return np.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)

        def get_expected_row(col):
            """Get the expected row (X) value at a given col (Z) by linear interpolation."""
            if start[1] == end[1]:
                return start[0]
            t = (col - start[1]) / (end[1] - start[1])
            return start[0] + t * (end[0] - start[0])

        def is_in_horizontal_corridor(point):
            if corridor_width is None:
                return True
            row, col = point
            expected_row = get_expected_row(col)
            return abs(row - expected_row) <= corridor_width

        neighbors = [
            (-1, 0), (1, 0), (0, -1), (0, 1),
            (-1, -1), (-1, 1), (1, -1), (1, 1),
        ]

        counter = 0
        open_set = [(0, counter, start)]
        came_from = {}

        g_score = {start: 0}
        f_score = {start: heuristic(start, end)}

        visited = set()

        while open_set:
            current = heapq.heappop(open_set)[2]

            if current == end:
                path = [current]
                while current in came_from:
                    current = came_from[current]
                    path.append(current)
                path.reverse()
                return path

            if current in visited:
                continue
            visited.add(current)

            for dr, dc in neighbors:
                neighbor = (current[0] + dr, current[1] + dc)
                if not (0 <= neighbor[0] < rows and 0 <= neighbor[1] < cols):
                    continue
                if neighbor in visited:
                    continue
                if not is_in_horizontal_corridor(neighbor):
                    continue

                move_cost = np.sqrt(2) if (dr != 0 and dc != 0) else 1.0

                if corridor_width is not None and corridor_width > 0:
                    expected_row = get_expected_row(neighbor[1])
                    horizontal_deviation = abs(neighbor[0] - expected_row)
                    deviation_penalty = (horizontal_deviation / max(corridor_width, 1)) ** 3 * 50.0
                else:
                    deviation_penalty = 0.0

                tentative_g = (
                    g_score[current]
                    + cost_map[neighbor[0], neighbor[1]] * move_cost
                    + deviation_penalty
                )

                if neighbor not in g_score or tentative_g < g_score[neighbor]:
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    f_score[neighbor] = tentative_g + heuristic(neighbor, end)
                    counter += 1
                    heapq.heappush(open_set, (f_score[neighbor], counter, neighbor))

        return None

    def _start_semi_auto_tracking(self, mode: str):
        """
        Start semi-auto tracking interaction (waypoints + A*).

        Args:
            mode: 'horizon' or 'fault'
        """
        self.disable_actions()

        if not self.current_seismic_uid:
            self.print_terminal("Please select a seismic volume first!")
            self.enable_actions()
            return

        slice_data, origin, spacing, axis_info = self.get_slice_as_2d_array()
        if slice_data is None:
            self.print_terminal("Could not extract slice data for auto-tracking!")
            self.enable_actions()
            return

        self._autotrack_mode = mode

        if mode == "fault":
            title = "Semi-Auto Fault Tracking"
            default_name = "auto_fault"
            self.print_terminal(f"Slice data shape: {slice_data.shape}")
            self.print_terminal("Computing fault (vertical edge) cost map...")
            cost_map = self.compute_fault_edge_cost_map(slice_data)
        else:
            title = "Semi-Auto Horizon Tracking"
            default_name = "auto_horizon"
            self.print_terminal(f"Slice data shape: {slice_data.shape}")
            self.print_terminal("Computing edge detection cost map...")
            cost_map = self.compute_edge_cost_map(slice_data)

        self.print_terminal(f"Cost map range: {cost_map.min():.3f} to {cost_map.max():.3f}")

        v_exag = 1.0
        try:
            if self.plotter.scale is not None and len(self.plotter.scale) >= 3:
                v_exag = self.plotter.scale[2]
                if v_exag == 0:
                    v_exag = 1.0
        except Exception:
            pass
        self.print_terminal(f"Vertical exaggeration: {v_exag}")

        # Avoid crossing existing lines (still useful for faults to avoid snapping to horizons)
        cost_map = self.add_existing_lines_to_cost_map(cost_map, axis_info, spacing, v_exag)
        self.print_terminal(f"Cost map range after forbidden zones: {cost_map.min():.3f} to {cost_map.max():.3f}")

        # Make only the seismic slice pickable
        self._saved_pickable_states = {}
        for name, actor in self.plotter.renderer.actors.items():
            try:
                self._saved_pickable_states[name] = actor.GetPickable()
                actor.SetPickable(name == "seismic_slice_actor")
                if name == "seismic_slice_actor":
                    self.print_terminal(f"Made {name} PICKABLE")
            except Exception:
                pass

        # Store for callbacks
        self._autotrack_cost_map = cost_map
        self._autotrack_axis_info = axis_info
        self._autotrack_spacing = spacing
        self._autotrack_origin = origin
        self._autotrack_v_exag = v_exag
        self._autotrack_points = []
        self._autotrack_markers = []
        self._autotrack_preview_actors = []

        line_dict = deepcopy(self.parent.geol_coll.entity_dict)
        feature_choices = self._sanitize_legend_choices(
            self.parent.geol_coll.legend_df["feature"].tolist(), fallback="undef"
        )
        scenario_choices = self._sanitize_legend_choices(
            self.parent.geol_coll.legend_df["scenario"].tolist(), fallback="undef"
        )
        line_dict_in = {
            "name": ["PolyLine name: ", default_name],
            "role": [
                "Role: ",
                self.parent.geol_coll.valid_roles,
            ],
            "feature": [
                "Feature: ",
                feature_choices,
            ],
            "scenario": [
                "Scenario: ",
                scenario_choices,
            ],
        }
        line_dict_updt = multiple_input_dialog(title=title, input_dict=line_dict_in)

        if line_dict_updt is None:
            self.enable_actions()
            return

        for key in line_dict_updt:
            line_dict[key] = line_dict_updt[key]
        role_fallback = "fault" if mode == "fault" else "top"
        feature_fallback = "auto_fault" if mode == "fault" else "auto_horizon"
        line_dict["role"] = self._sanitize_legend_value(line_dict.get("role"), role_fallback)
        line_dict["feature"] = self._sanitize_legend_value(line_dict.get("feature"), feature_fallback)
        line_dict["scenario"] = self._sanitize_legend_value(line_dict.get("scenario"), "undef")

        line_dict["topology"] = "PolyLine"
        line_dict["x_section"] = ""
        line_dict["vtk_obj"] = PolyLine()
        self._set_entity_parent_to_current_seismic(line_dict)

        self._autotrack_line_dict = line_dict

        self.print_terminal(f"=== {title} ===")
        if mode == "fault":
            self.print_terminal("LEFT-CLICK: Add waypoint on the fault (near-vertical edge)")
        else:
            self.print_terminal("LEFT-CLICK: Add waypoint on the horizon")
        self.print_terminal("RIGHT-CLICK: Finish and create the tracked line")
        self.print_terminal("Add at least 2 waypoints, then right-click to finish.")

        # Calculate marker size based on slice bounds (more reliable than spacing)
        bounds = axis_info['bounds']
        extent_x = abs(bounds[1] - bounds[0])
        extent_y = abs(bounds[3] - bounds[2])
        extent_z = abs(bounds[5] - bounds[4]) * v_exag  # Account for VE in display
        max_extent = max(extent_x, extent_y, extent_z)
        self._autotrack_marker_size = max_extent * 0.01  # 1% of max extent
        self.print_terminal(f"Marker size: {self._autotrack_marker_size}")

        # Waypoint picking
        max_jump_samples = 50 if mode == "fault" else 20

        def on_point_picked(picked_point):
            if picked_point is None:
                return

            self.print_terminal(f"DEBUG: Raw picked point: {picked_point}")

            point = list(picked_point)

            # Snap picked point to the true slice plane (supports rotated/skewed grids)
            try:
                plane_center = getattr(self, "current_slice_plane_center", None)
                plane_normal = getattr(self, "current_slice_plane_normal", None)
                if plane_center is not None and plane_normal is not None:
                    z_real = float(point[2]) / v_exag if v_exag != 0 else float(point[2])
                    p_real = np.array([float(point[0]), float(point[1]), z_real], dtype=float)
                    p_proj = self._project_points_to_plane(p_real[None, :], plane_center, plane_normal)[0]
                    point[0] = float(p_proj[0])
                    point[1] = float(p_proj[1])
                    point[2] = float(p_proj[2] * v_exag)
                else:
                    # Fallback to axis-aligned snapping
                    if self.current_axis == 'Inline':
                        point[0] = self.current_slice_position
                    elif self.current_axis == 'Crossline':
                        point[1] = self.current_slice_position
                    elif self.current_axis == 'Z-slice':
                        point[2] = self.current_slice_position
            except Exception:
                if self.current_axis == 'Inline':
                    point[0] = self.current_slice_position
                elif self.current_axis == 'Crossline':
                    point[1] = self.current_slice_position
                elif self.current_axis == 'Z-slice':
                    point[2] = self.current_slice_position

            self.print_terminal(f"DEBUG: Snapped to slice position: {point}")

            test_slice_coord = self.world_to_slice_coords(point, axis_info, spacing, v_exag)
            self.print_terminal(
                f"DEBUG: Slice coords = row:{test_slice_coord[0]}, col(Z):{test_slice_coord[1]}"
            )

            if len(self._autotrack_points) > 0:
                prev_point = self._autotrack_points[-1]
                prev_slice_coord = self.world_to_slice_coords(prev_point, axis_info, spacing, v_exag)

                if mode == "fault":
                    jump = abs(test_slice_coord[0] - prev_slice_coord[0])
                    if jump > max_jump_samples:
                        self.print_terminal(
                            f"WARNING: Row(X) jumped {jump} samples (max allowed: {max_jump_samples})"
                        )
                        self.print_terminal(
                            f"  Previous row: {prev_slice_coord[0]}, Current row: {test_slice_coord[0]}"
                        )
                else:
                    jump = abs(test_slice_coord[1] - prev_slice_coord[1])
                    if jump > max_jump_samples:
                        self.print_terminal(
                            f"WARNING: Z jumped {jump} samples (max allowed: {max_jump_samples})"
                        )
                        self.print_terminal(
                            f"  Previous col(Z): {prev_slice_coord[1]}, Current col(Z): {test_slice_coord[1]}"
                        )
                        self.print_terminal(
                            "  This may indicate picking is not hitting the slice - try clicking directly on the seismic image"
                        )

            # Store display point
            self._autotrack_points.append(tuple(point))

            # Draw a preview segment between consecutive waypoints for visual guidance
            if len(self._autotrack_points) >= 2:
                self._show_path_preview(
                    self._autotrack_points[-2],
                    self._autotrack_points[-1],
                )

            marker_name = f'autotrack_marker_{len(self._autotrack_points)}'
            marker_point = list(point)
            small_offset = self._autotrack_marker_size * 0.5

            if self.current_axis == 'Inline':
                marker_point[0] -= small_offset
            elif self.current_axis == 'Crossline':
                marker_point[1] -= small_offset
            elif self.current_axis == 'Z-slice':
                marker_point[2] += small_offset

            waypoint_num = len(self._autotrack_points)
            self.plotter.add_point_labels(
                [marker_point],
                [f"  {waypoint_num}"],
                name=marker_name,
                show_points=False,
                text_color='red',
                font_size=14,
                bold=True,
                shape=None,
                always_visible=True,
                pickable=False,
                reset_camera=False
            )
            self._autotrack_markers.append(marker_name)

            self.print_terminal(f"Waypoint {waypoint_num} added at {point}")
            self.plotter.update()
            self.plotter.render()

        def on_finish(_point):
            if len(self._autotrack_points) < 2:
                self.print_terminal("Need at least 2 waypoints! Add more points or press ESC to cancel.")
                return

            self.print_terminal(f"Finishing with {len(self._autotrack_points)} waypoints...")
            self.plotter.untrack_click_position(side="left")
            self.plotter.untrack_click_position(side="right")
            self._run_autotrack_pathfinding_multi()

        self.plotter.track_click_position(side="left", callback=on_point_picked)
        self.plotter.track_click_position(side="right", callback=on_finish)
    
    def get_slice_as_2d_array(self):
        """
        Extract the current seismic slice as a 2D numpy array.
        
        Returns:
            data_2d: 2D numpy array of seismic values
            origin: (x, y, z) origin of the slice in world coordinates
            spacing: (dx, dy, dz) spacing of the slice
            axis_info: dict with axis mapping info for coordinate conversion
        """
        if not hasattr(self, '_cached_seismic') or self._cached_seismic is None:
            return None, None, None, None
        
        seismic = self._cached_seismic
        dims = self._cached_dims
        bounds = self._cached_bounds
        
        # Get the intensity/amplitude data
        if 'intensity' in seismic.array_names:
            data = seismic['intensity']
        elif seismic.array_names:
            data = seismic[seismic.array_names[0]]
        else:
            return None, None, None, None
        
        # Reshape to 3D grid
        data_3d = data.reshape(dims, order='F')  # Fortran order for VTK
        
        # Calculate spacing
        spacing = [
            (bounds[1] - bounds[0]) / max(dims[0] - 1, 1),
            (bounds[3] - bounds[2]) / max(dims[1] - 1, 1),
            (bounds[5] - bounds[4]) / max(dims[2] - 1, 1)
        ]
        affine = self._get_seismic_axis_vectors()
        #affine = self._get_seismic_axis_vectors()
        #affine = self._get_seismic_axis_vectors()
        #affine = self._get_seismic_axis_vectors()
        
        # Extract the 2D slice based on current axis
        axis_info = {
            'axis': self.current_axis,
            'slice_index': self.current_slice_index,
            'bounds': bounds,
            'dims': dims,
            'spacing': spacing,
            'affine': self._get_seismic_axis_vectors()
        }
        
        if self.current_axis == 'Inline':
            # YZ plane at X index
            idx = min(self.current_slice_index, dims[0] - 1)
            data_2d = data_3d[idx, :, :]  # Shape: (ny, nz)
            origin = (bounds[0] + idx * spacing[0], bounds[2], bounds[4])
            axis_info['plane'] = 'YZ'
            axis_info['row_axis'] = 'Y'  # rows in 2D array correspond to Y
            axis_info['col_axis'] = 'Z'  # cols in 2D array correspond to Z
            
        elif self.current_axis == 'Crossline':
            # XZ plane at Y index
            idx = min(self.current_slice_index, dims[1] - 1)
            data_2d = data_3d[:, idx, :]  # Shape: (nx, nz)
            origin = (bounds[0], bounds[2] + idx * spacing[1], bounds[4])
            axis_info['plane'] = 'XZ'
            axis_info['row_axis'] = 'X'
            axis_info['col_axis'] = 'Z'
            
        elif self.current_axis == 'Z-slice':
            # XY plane at Z index
            idx = min(self.current_slice_index, dims[2] - 1)
            data_2d = data_3d[:, :, idx]  # Shape: (nx, ny)
            origin = (bounds[0], bounds[2], bounds[4] + idx * spacing[2])
            axis_info['plane'] = 'XY'
            axis_info['row_axis'] = 'X'
            axis_info['col_axis'] = 'Y'
        
        return data_2d, origin, spacing, axis_info
    
    def world_to_slice_coords(self, world_point, axis_info, spacing, v_exag=1.0):
        """Convert world coordinates to slice 2D array indices.
        
        Args:
            world_point: (x, y, z) in DISPLAY coordinates (with VE applied to Z)
            axis_info: dict with bounds and axis info
            spacing: (dx, dy, dz) spacing in REAL coordinates
            v_exag: vertical exaggeration factor applied to display
        """
        bounds = axis_info['bounds']
        affine = axis_info.get('affine')
        
        # The picked point Z is in display coords (scaled by VE)
        # Convert Z back to real coordinates for slice indexing
        real_z = world_point[2] / v_exag if v_exag != 0 else world_point[2]
        
        if affine is not None:
            real_pt = (float(world_point[0]), float(world_point[1]), float(real_z))
            rc = self._world_to_slice_rc(
                real_pt,
                slice_idx=int(axis_info.get('slice_index', self.current_slice_index)),
                affine=affine,
                axis=self.current_axis,
            )
            if rc is not None:
                return rc

        if self.current_axis == 'Inline':
            # YZ plane - world (x, y, z) -> slice (row=y, col=z)
            row = int((world_point[1] - bounds[2]) / spacing[1]) if spacing[1] > 0 else 0
            col = int((real_z - bounds[4]) / spacing[2]) if spacing[2] > 0 else 0
        elif self.current_axis == 'Crossline':
            # XZ plane - world (x, y, z) -> slice (row=x, col=z)
            row = int((world_point[0] - bounds[0]) / spacing[0]) if spacing[0] > 0 else 0
            col = int((real_z - bounds[4]) / spacing[2]) if spacing[2] > 0 else 0
        elif self.current_axis == 'Z-slice':
            # XY plane - world (x, y, z) -> slice (row=x, col=y)
            row = int((world_point[0] - bounds[0]) / spacing[0]) if spacing[0] > 0 else 0
            col = int((world_point[1] - bounds[2]) / spacing[1]) if spacing[1] > 0 else 0
        
        return (row, col)
    
    def slice_coords_to_world(self, slice_point, axis_info, spacing, origin):
        """Convert slice 2D array indices to world coordinates."""
        bounds = axis_info['bounds']
        affine = axis_info.get('affine')
        row, col = slice_point

        if affine is not None:
            wp = self._slice_rc_to_world(
                slice_idx=int(axis_info.get('slice_index', self.current_slice_index)),
                row=int(row),
                col=int(col),
                affine=affine,
                axis=self.current_axis,
            )
            if wp is not None:
                return wp
        
        if self.current_axis == 'Inline':
            # YZ plane - slice (row=y_idx, col=z_idx) -> world (x, y, z)
            x = self.current_slice_position
            y = bounds[2] + row * spacing[1]
            z = bounds[4] + col * spacing[2]
        elif self.current_axis == 'Crossline':
            # XZ plane
            x = bounds[0] + row * spacing[0]
            y = self.current_slice_position
            z = bounds[4] + col * spacing[2]
        elif self.current_axis == 'Z-slice':
            # XY plane
            x = bounds[0] + row * spacing[0]
            y = bounds[2] + col * spacing[1]
            z = self.current_slice_position
        
        return (x, y, z)

    def _get_seismic_axis_vectors(self):
        """Return affine axis vectors derived from the current seismic StructuredGrid."""
        try:
            if getattr(self, "_cached_affine_uid", None) == self.current_seismic_uid:
                return getattr(self, "_cached_affine", None)

            seismic_vtk = self.parent.image_coll.get_uid_vtk_obj(self.current_seismic_uid)
            if seismic_vtk is None:
                return None
            dims = seismic_vtk.GetDimensions()
            nx, ny, nz = int(dims[0]), int(dims[1]), int(dims[2])
            origin = np.array(seismic_vtk.GetPoint(0), dtype=float)
            a0 = (
                np.array(seismic_vtk.GetPoint(1), dtype=float) - origin
                if nx > 1
                else np.array([1.0, 0.0, 0.0], dtype=float)
            )
            a1 = (
                np.array(seismic_vtk.GetPoint(nx), dtype=float) - origin
                if ny > 1
                else np.array([0.0, 1.0, 0.0], dtype=float)
            )
            a2 = (
                np.array(seismic_vtk.GetPoint(nx * ny), dtype=float) - origin
                if nz > 1
                else np.array([0.0, 0.0, 1.0], dtype=float)
            )
            affine = (origin, a0, a1, a2, (nx, ny, nz))
            self._cached_affine = affine
            self._cached_affine_uid = self.current_seismic_uid
            return affine
        except Exception:
            return None

    def _get_slice_plane_from_affine(self, slice_idx, affine=None, axis=None):
        """Return slice plane center/normal and in-plane vectors for rotated/skewed grids."""
        axis = axis or self.current_axis
        if affine is None:
            affine = self._get_seismic_axis_vectors()
        if affine is None:
            return None

        origin, a0, a1, a2, dims = affine
        nx, ny, nz = dims
        i = int(slice_idx)

        if axis == "Inline":
            base = origin + i * a0
            row_vec = a1
            col_vec = a2
            center = base + (ny - 1) * 0.5 * row_vec + (nz - 1) * 0.5 * col_vec
        elif axis == "Crossline":
            base = origin + i * a1
            row_vec = a0
            col_vec = a2
            center = base + (nx - 1) * 0.5 * row_vec + (nz - 1) * 0.5 * col_vec
        else:  # Z-slice
            base = origin + i * a2
            row_vec = a0
            col_vec = a1
            center = base + (nx - 1) * 0.5 * row_vec + (ny - 1) * 0.5 * col_vec

        normal = np.cross(row_vec, col_vec)
        n_norm = float(np.linalg.norm(normal))
        if n_norm > 0:
            normal = normal / n_norm
        return (center, normal, row_vec, col_vec, dims)

    def _get_display_plane_from_affine(self, center, normal, row_vec, col_vec, dims, v_exag):
        """Convert a real-space slice plane to display-space parameters (VE applied)."""
        center_disp = (float(center[0]), float(center[1]), float(center[2]) * v_exag)
        normal_disp = np.array([normal[0], normal[1], normal[2] / v_exag], dtype=float)
        n_norm = float(np.linalg.norm(normal_disp))
        if n_norm > 0:
            normal_disp = normal_disp / n_norm

        row_disp = np.array([row_vec[0], row_vec[1], row_vec[2] * v_exag], dtype=float)
        col_disp = np.array([col_vec[0], col_vec[1], col_vec[2] * v_exag], dtype=float)

        row_len = float(np.linalg.norm(row_disp))
        col_len = float(np.linalg.norm(col_disp))
        nx, ny, nz = dims

        if self.current_axis == "Inline":
            i_size = max(row_len * max(ny - 1, 1), 1.0)
            j_size = max(col_len * max(nz - 1, 1), 1.0)
        elif self.current_axis == "Crossline":
            i_size = max(row_len * max(nx - 1, 1), 1.0)
            j_size = max(col_len * max(nz - 1, 1), 1.0)
        else:  # Z-slice
            i_size = max(row_len * max(nx - 1, 1), 1.0)
            j_size = max(col_len * max(ny - 1, 1), 1.0)

        return center_disp, normal_disp.tolist(), i_size, j_size

    def _project_points_to_plane(self, points, center, normal):
        """Project points onto a plane defined by center and normal (real coords)."""
        pts = np.asarray(points, dtype=np.float64)
        c = np.asarray(center, dtype=np.float64)
        n = np.asarray(normal, dtype=np.float64)
        n_norm = float(np.linalg.norm(n))
        if n_norm == 0:
            return pts
        n = n / n_norm
        d = np.dot(pts - c, n)
        return pts - d[:, None] * n[None, :]

    def _slice_rc_to_world(self, slice_idx: int, row: int, col: int, affine=None, axis=None):
        """Convert (slice_idx, row, col) to world coordinates using affine axis vectors."""
        axis = axis or self.current_axis
        if affine is None:
            affine = self._get_seismic_axis_vectors()
        if affine is None:
            return None
        origin, a0, a1, a2, _dims = affine
        i = int(slice_idx)
        r = float(row)
        c = float(col)
        if axis == "Inline":
            p = origin + i * a0 + r * a1 + c * a2
        elif axis == "Crossline":
            p = origin + r * a0 + i * a1 + c * a2
        else:  # "Z-slice"
            p = origin + r * a0 + c * a1 + i * a2
        return (float(p[0]), float(p[1]), float(p[2]))

    def _world_to_slice_rc(self, world_point, slice_idx: int, affine=None, axis=None):
        """Convert world coordinates to (row, col) on a given slice using affine axis vectors."""
        axis = axis or self.current_axis
        if affine is None:
            affine = self._get_seismic_axis_vectors()
        if affine is None:
            return None
        origin, a0, a1, a2, dims = affine
        p = np.array(world_point, dtype=float)
        i = int(slice_idx)

        if axis == "Inline":
            base = origin + i * a0
            A = np.column_stack([a1, a2])
            size_row, size_col = dims[1], dims[2]
        elif axis == "Crossline":
            base = origin + i * a1
            A = np.column_stack([a0, a2])
            size_row, size_col = dims[0], dims[2]
        else:  # "Z-slice"
            base = origin + i * a2
            A = np.column_stack([a0, a1])
            size_row, size_col = dims[0], dims[1]

        b = p - base
        try:
            rc, *_ = np.linalg.lstsq(A, b, rcond=None)
            row = int(np.clip(np.round(rc[0]), 0, max(size_row - 1, 0)))
            col = int(np.clip(np.round(rc[1]), 0, max(size_col - 1, 0)))
            return (row, col)
        except Exception:
            return None
    
    def draw_semi_auto_line(self):
        """
        Semi-automatic horizon tracking using edge detection and A* pathfinding.
        User clicks multiple waypoints along the horizon, then right-clicks to finish.
        The algorithm finds optimal paths between consecutive waypoints.
        """
        self._start_semi_auto_tracking(mode="horizon")

    def draw_semi_auto_fault_line(self):
        """
        Semi-automatic fault picking using vertical-edge cost map and fault-oriented A*.
        User clicks multiple waypoints along the fault, then right-clicks to finish.
        """
        self._start_semi_auto_tracking(mode="fault")
    
    def _show_path_preview(self, point_a, point_b):
        """Show a preview line between two display-space points."""
        try:
            # Click picks are stored in display space (Z already scaled by VE).
            # Mesh actors are rendered with plotter scale, so convert back to real Z
            # to avoid applying vertical exaggeration twice.
            v_exag = float(getattr(self, "_autotrack_v_exag", 1.0) or 1.0)
            p0 = np.array(point_a, dtype=float).copy()
            p1 = np.array(point_b, dtype=float).copy()
            if v_exag != 0.0 and v_exag != 1.0:
                p0[2] = p0[2] / v_exag
                p1[2] = p1[2] / v_exag

            # Create a simple line between the two points for visual feedback
            line = pv.Line(p0, p1)
            preview_name = f'autotrack_preview_{len(self._autotrack_preview_actors)}'
            self.plotter.add_mesh(
                line,
                color='red',
                line_width=6,
                name=preview_name,
                pickable=False,
                reset_camera=False,
                lighting=False,
            )
            self._autotrack_preview_actors.append(preview_name)
            self.plotter.update()
            self.plotter.render()
        except Exception as e:
            self.print_terminal(f"Preview error: {e}")
    
    def _run_autotrack_pathfinding_multi(self):
        """Execute A* pathfinding between all consecutive waypoints."""
        try:
            waypoints = self._autotrack_points
            cost_map = self._autotrack_cost_map
            axis_info = self._autotrack_axis_info
            spacing = self._autotrack_spacing
            origin = self._autotrack_origin
            v_exag = self._autotrack_v_exag
            line_dict = self._autotrack_line_dict
            mode = getattr(self, "_autotrack_mode", "horizon")
            
            self.print_terminal(f"Running pathfinding between {len(waypoints)} waypoints...")
            
            # Corridor is used to prevent jumping to unrelated features.
            # Horizons: constrain col(Z) as a function of row(X).
            # Faults: constrain row(X) as a function of col(Z).
            if mode == "fault":
                MAX_CORRIDOR = 6
                MIN_CORRIDOR = 2
            else:
                MAX_CORRIDOR = 2
                MIN_CORRIDOR = 1
            
            self.print_terminal(f"Using VERY TIGHT corridor: {MIN_CORRIDOR}-{MAX_CORRIDOR} pixels max")
            
            # Collect all path segments
            all_world_points = []
            
            for i in range(len(waypoints) - 1):
                point_a = waypoints[i]  # In display coords
                point_b = waypoints[i + 1]  # In display coords
                
                # Convert display coordinates to slice indices
                start = self.world_to_slice_coords(point_a, axis_info, spacing, v_exag)
                end = self.world_to_slice_coords(point_b, axis_info, spacing, v_exag)
                
                self.print_terminal(f"Segment {i+1}: slice coords {start} -> {end}")
                
                # Clamp to valid range
                start = (
                    int(np.clip(start[0], 0, cost_map.shape[0] - 1)),
                    int(np.clip(start[1], 0, cost_map.shape[1] - 1))
                )
                end = (
                    int(np.clip(end[0], 0, cost_map.shape[0] - 1)),
                    int(np.clip(end[1], 0, cost_map.shape[1] - 1))
                )
                
                if mode == "fault":
                    horizontal_diff = abs(start[0] - end[0])
                    segment_corridor = min(
                        MAX_CORRIDOR,
                        max(MIN_CORRIDOR, horizontal_diff // 3 + MIN_CORRIDOR)
                    )
                    self.print_terminal(
                        f"Segment {i+1}: horizontal diff={horizontal_diff}, corridor={segment_corridor}"
                    )
                    path = self.astar_pathfind_fault(cost_map, start, end, corridor_width=segment_corridor)
                else:
                    vertical_diff = abs(start[1] - end[1])
                    segment_corridor = min(
                        MAX_CORRIDOR,
                        max(MIN_CORRIDOR, vertical_diff // 3 + MIN_CORRIDOR)
                    )
                    self.print_terminal(
                        f"Segment {i+1}: vertical diff={vertical_diff}, corridor={segment_corridor}"
                    )
                    path = self.astar_pathfind(cost_map, start, end, corridor_width=segment_corridor)
                
                if path is None:
                    self.print_terminal(f"No path found for segment {i+1}! Using straight line.")
                    # Fallback: use straight line
                    path = [start, end]
                
                self.print_terminal(f"Segment {i+1}: found {len(path)} points")
                
                # Convert path to world coordinates (REAL coords, not display)
                for j, slice_point in enumerate(path):
                    # Skip first point of subsequent segments to avoid duplicates
                    if i > 0 and j == 0:
                        continue
                    world_point = self.slice_coords_to_world(slice_point, axis_info, spacing, origin)
                    all_world_points.append(world_point)
            
            if len(all_world_points) < 2:
                self.print_terminal("Not enough points for a line!")
                self._cleanup_autotrack()
                self.enable_actions()
                return
            
            self.print_terminal(f"Total path: {len(all_world_points)} points")
            
            # Subsample if too many points
            if len(all_world_points) > 1000:
                step = len(all_world_points) // 1000
                subsampled = all_world_points[::step]
                # Ensure end point is included
                if subsampled[-1] != all_world_points[-1]:
                    subsampled.append(all_world_points[-1])
                all_world_points = subsampled
                self.print_terminal(f"Subsampled to {len(all_world_points)} points")
            
            # Create numpy array of points (in REAL coordinates)
            points_array = np.array(all_world_points, dtype=np.float64)
            
            # Snap to slice:
            # - Inline/Crossline: project to the fitted slice plane (supports rotated surveys)
            # - Z-slice: enforce constant Z
            if self.current_axis in ("Inline", "Crossline"):
                plane_center = getattr(self, "current_slice_plane_center", None)
                plane_normal = getattr(self, "current_slice_plane_normal", None)
                if plane_center is not None and plane_normal is not None:
                    try:
                        points_array = self._project_points_to_plane(points_array, plane_center, plane_normal)
                    except Exception:
                        pass
                else:
                    offset = 1.0
                    if self.current_axis == 'Inline':
                        points_array[:, 0] = self.current_slice_position - offset
                    else:
                        points_array[:, 1] = self.current_slice_position - offset
            elif self.current_axis == 'Z-slice':
                points_array[:, 2] = self.current_slice_position
            
            # Create proper VTK PolyLine
            n_points = len(points_array)
            
            # Create the polydata with points
            polydata = pv.PolyData(points_array)
            
            # Create line connectivity: for a polyline, we need [n, 0, 1, 2, ..., n-1]
            lines = np.hstack([[n_points], np.arange(n_points)])
            polydata.lines = lines
            
            # Copy to our VTK object
            line_dict["vtk_obj"].ShallowCopy(polydata)
            
            # Store slice info
            slice_info = {
                'seismic_uid': self.current_seismic_uid,
                'axis': self.current_axis,
                'slice_index': self.current_slice_index
            }
            
            # Add to geological collection
            new_uid = self.parent.geol_coll.add_entity_from_dict(line_dict)
            self.print_terminal(f"Created auto-tracked horizon with {n_points} points, uid: {new_uid}")
            
            # Track this interpretation line
            # Track this interpretation line
            self.register_interpretation_line(new_uid, slice_info)
            self.print_terminal(f"Registered auto-tracked line {new_uid} for {slice_info['axis']} slice {slice_info['slice_index']}")
            self.print_terminal(f"Registered auto-tracked line {new_uid} for {slice_info['axis']} slice {slice_info['slice_index']}")
            
        except Exception as e:
            self.print_terminal(f"Error in auto-tracking: {e}")
            self.print_terminal(traceback_format_exc())
        
        finally:
            self._cleanup_autotrack()
            self.enable_actions()
    
    def _cleanup_autotrack(self):
        """Clean up temporary auto-tracking state and markers."""
        # Remove visual markers
        if hasattr(self, '_autotrack_markers'):
            for marker_name in self._autotrack_markers:
                try:
                    if marker_name in self.plotter.renderer.actors:
                        self.plotter.remove_actor(marker_name)
                except:
                    pass
            self._autotrack_markers = []
        
        # Remove preview lines
        if hasattr(self, '_autotrack_preview_actors'):
            for preview_name in self._autotrack_preview_actors:
                try:
                    if preview_name in self.plotter.renderer.actors:
                        self.plotter.remove_actor(preview_name)
                except:
                    pass
            self._autotrack_preview_actors = []
        
        # Restore pickable states for all actors
        if hasattr(self, '_saved_pickable_states'):
            for name, was_pickable in self._saved_pickable_states.items():
                try:
                    if name in self.plotter.renderer.actors:
                        self.plotter.renderer.actors[name].SetPickable(was_pickable)
                except:
                    pass
            del self._saved_pickable_states
            self.print_terminal("Restored pickable states for all actors")
        
        # Clear state
        if hasattr(self, '_autotrack_cost_map'):
            del self._autotrack_cost_map
        if hasattr(self, '_autotrack_axis_info'):
            del self._autotrack_axis_info
        if hasattr(self, '_autotrack_spacing'):
            del self._autotrack_spacing
        if hasattr(self, '_autotrack_origin'):
            del self._autotrack_origin
        if hasattr(self, '_autotrack_points'):
            del self._autotrack_points
        if hasattr(self, '_autotrack_line_dict'):
            del self._autotrack_line_dict
        if hasattr(self, '_autotrack_v_exag'):
            del self._autotrack_v_exag
        if hasattr(self, '_autotrack_marker_size'):
            del self._autotrack_marker_size
        
        self.plotter.render()

    # ==================== End Semi-Auto Tracking Methods ====================
    
    # ==================== Auto Propagation Methods ====================
    
    def propagate_horizon(self):
        """
        Propagate a selected horizon through adjacent slices using template matching.
        Uses cross-correlation to find the best matching position on each slice.
        """
        self.disable_actions()
        
        # Check if we have a seismic volume
        if not self.current_seismic_uid:
            self.print_terminal("No seismic volume loaded!")
            self.enable_actions()
            return
        
        # Helper function to check if UID exists in geol_coll
        def uid_exists(uid):
            try:
                return (self.parent.geol_coll.df["uid"] == uid).any()
            except:
                return False
        
        # Clean up interpretation_lines - remove any UIDs that no longer exist in geol_coll
        uids_to_remove = []
        for uid in list(self.interpretation_lines.keys()):
            if not uid_exists(uid):
                uids_to_remove.append(uid)
        
        if uids_to_remove:
            for uid in uids_to_remove:
                self.unregister_interpretation_line(uid)
                self.print_terminal(f"Removed deleted horizon {uid[:8]}... from tracking list")
        
        # Get list of semi-auto tracked horizons ONLY (from interpretation_lines)
        # This excludes manually drawn lines and other entities
        all_lines = []
        for uid, slice_info in self.interpretation_lines.items():
            if slice_info['seismic_uid'] == self.current_seismic_uid and slice_info['axis'] == self.current_axis:
                # Verify the entity still exists and get its name
                if uid_exists(uid):
                    try:
                        name = self.parent.geol_coll.get_uid_name(uid)
                        slice_idx = slice_info['slice_index']
                        all_lines.append((uid, name, slice_idx))
                    except:
                        pass
        
        if not all_lines:
            self.print_terminal("No semi-auto tracked horizons found!")
            self.print_terminal("First use 'Semi-Auto Track Horizon' to create a seed horizon on this axis.")
            self.enable_actions()
            return
        
        # Sort by slice index, then by name
        all_lines.sort(key=lambda x: (x[2], x[1]))
        
        # Create selection dialog

        
        dialog = QDialog(self)
        dialog.setWindowTitle("Propagate Horizon")
        dialog.setMinimumWidth(500)
        layout = QVBoxLayout(dialog)
        layout.setSpacing(8)
        
        # === TOP ROW: Horizon selection ===
        horizon_layout = QHBoxLayout()
        horizon_layout.addWidget(QLabel("Seed horizon:"))
        combo_horizon = QComboBox()
        for uid, name, slice_idx in all_lines:
            display_text = f"{name} [Slice {slice_idx}]" if slice_idx >= 0 else f"{name} [Current]"
            combo_horizon.addItem(display_text, uid)
        combo_horizon.setMinimumWidth(250)
        horizon_layout.addWidget(combo_horizon, 1)
        layout.addLayout(horizon_layout)

        tooltip_hint = QLabel(
            "Hover an attribute or parameter to see what it does and what Low or High values mean."
        )
        tooltip_hint.setStyleSheet("color: gray;")
        tooltip_hint.setWordWrap(True)
        layout.addWidget(tooltip_hint)
        
        # === TWO COLUMN LAYOUT ===
        columns_layout = QHBoxLayout()
        
        # --- LEFT COLUMN ---
        left_widget = QVBoxLayout()
        
        # Direction (compact)
        dir_group = QGroupBox("Direction")
        dir_layout = QVBoxLayout(dir_group)
        dir_layout.setSpacing(2)
        direction_group = QButtonGroup(dialog)
        radio_forward = QRadioButton("Forward")
        radio_backward = QRadioButton("Backward")
        radio_both = QRadioButton("Both")
        radio_forward.setChecked(True)
        direction_group.addButton(radio_forward, 0)
        direction_group.addButton(radio_backward, 1)
        direction_group.addButton(radio_both, 2)
        dir_layout.addWidget(radio_forward)
        dir_layout.addWidget(radio_backward)
        dir_layout.addWidget(radio_both)
        left_widget.addWidget(dir_group)
        
        # Tracking Attributes (compact checkboxes)
        attr_group = QGroupBox("Attributes")
        attr_layout = QVBoxLayout(attr_group)
        attr_layout.setSpacing(2)
        check_amplitude = QCheckBox("Amplitude")
        check_amplitude.setChecked(True)
        check_edge = QCheckBox("Edge")
        check_edge.setChecked(True)
        check_phase = QCheckBox("Phase")
        check_similarity = QCheckBox("Similarity")
        check_dip = QCheckBox("Dip")
        self._apply_control_tooltip(
            check_amplitude,
            "Track the reflector by envelope/reflection strength. Best for bright, continuous horizons.",
        )
        self._apply_control_tooltip(
            check_edge,
            "Track the reflector boundary by gradient strength. Useful when the event is clearer as an edge than as a peak or trough.",
        )
        self._apply_control_tooltip(
            check_phase,
            "Track phase continuity. Useful where amplitude is weak but the reflector keeps a stable phase character.",
        )
        self._apply_control_tooltip(
            check_similarity,
            "Favor lateral coherence from trace to trace. Helps reject noisy or isolated picks.",
        )
        self._apply_control_tooltip(
            check_dip,
            "Favor dip continuity from slice to slice. Useful for smooth structure; less useful where dip changes abruptly.",
        )
        attr_layout.addWidget(check_amplitude)
        attr_layout.addWidget(check_edge)
        attr_layout.addWidget(check_phase)
        attr_layout.addWidget(check_similarity)
        attr_layout.addWidget(check_dip)
        left_widget.addWidget(attr_group)
        
        left_widget.addStretch()
        columns_layout.addLayout(left_widget)
        
        # --- RIGHT COLUMN ---
        right_widget = QVBoxLayout()
        
        # Parameters (using form layout for compactness)
        params_group = QGroupBox("Parameters")
        params_form = QFormLayout(params_group)
        params_form.setSpacing(4)
        
        spin_slices = QSpinBox()
        spin_slices.setRange(1, 500)
        spin_slices.setValue(50)
        self._apply_control_tooltip(
            spin_slices,
            "How many slices to propagate away from the seed.",
            low_text="Shorter propagation. Faster and safer when you only trust the seed locally.",
            high_text="Longer propagation. Covers more of the volume, but drift can accumulate farther from the seed.",
        )
        params_form.addRow(
            self._make_control_label(
                "Slices:",
                "How many slices to propagate away from the seed.",
                low_text="Shorter propagation. Faster and safer when you only trust the seed locally.",
                high_text="Longer propagation. Covers more of the volume, but drift can accumulate farther from the seed.",
            ),
            spin_slices,
        )
        
        spin_search = QSpinBox()
        spin_search.setRange(5, 50)
        spin_search.setValue(15)
        self._apply_control_tooltip(
            spin_search,
            "Vertical search range around the previous depth pick on each new slice.",
            low_text="Stays close to the previous pick. Better for stable reflectors, but may miss real jumps, drag, or throw.",
            high_text="Allows larger depth changes. Better for complex structure, but easier to jump to the wrong reflector.",
        )
        params_form.addRow(
            self._make_control_label(
                "Search window:",
                "Vertical search range around the previous depth pick on each new slice.",
                low_text="Stays close to the previous pick. Better for stable reflectors, but may miss real jumps, drag, or throw.",
                high_text="Allows larger depth changes. Better for complex structure, but easier to jump to the wrong reflector.",
            ),
            spin_search,
        )
        
        spin_smooth = QDoubleSpinBox()
        spin_smooth.setRange(0.0, 10.0)
        spin_smooth.setValue(2.0)
        spin_smooth.setSingleStep(0.5)
        self._apply_control_tooltip(
            spin_smooth,
            "How strongly the propagated horizon is smoothed along the picked line.",
            low_text="Preserves local bends and fault-related shape changes, but can look noisy.",
            high_text="Produces a cleaner line, but can flatten subtle structure or over-smooth real geometry.",
        )
        params_form.addRow(
            self._make_control_label(
                "Smoothing:",
                "How strongly the propagated horizon is smoothed along the picked line.",
                low_text="Preserves local bends and fault-related shape changes, but can look noisy.",
                high_text="Produces a cleaner line, but can flatten subtle structure or over-smooth real geometry.",
            ),
            spin_smooth,
        )
        
        spin_max_jump = QSpinBox()
        spin_max_jump.setRange(1, 20)
        spin_max_jump.setValue(3)
        self._apply_control_tooltip(
            spin_max_jump,
            "Maximum allowed sample-to-sample change after smoothing.",
            low_text="Keeps the horizon very stable and continuous, but may not follow steep or sharply bent events.",
            high_text="Allows sharper curvature and local offsets, but can admit zig-zagging or unstable picks.",
        )
        params_form.addRow(
            self._make_control_label(
                "Max jump:",
                "Maximum allowed sample-to-sample change after smoothing.",
                low_text="Keeps the horizon very stable and continuous, but may not follow steep or sharply bent events.",
                high_text="Allows sharper curvature and local offsets, but can admit zig-zagging or unstable picks.",
            ),
            spin_max_jump,
        )
        
        right_widget.addWidget(params_group)

        fault_group = QGroupBox("Fault Attachment")
        fault_form = QFormLayout(fault_group)
        fault_form.setSpacing(4)

        spin_fault_snap_weight = QDoubleSpinBox()
        spin_fault_snap_weight.setRange(0.0, 10.0)
        spin_fault_snap_weight.setValue(2.0)
        spin_fault_snap_weight.setSingleStep(0.1)
        self._apply_control_tooltip(
            spin_fault_snap_weight,
            "How strongly a real horizon/fault crossing is pulled toward the mapped fault position.",
            low_text="Weak attachment. Safer if fault picks are uncertain, but contacts may detach across slices.",
            high_text="Strong attachment. Better for preserving true crossings, but can over-pull the horizon onto a wrong fault trace.",
        )
        fault_form.addRow(
            self._make_control_label(
                "Snap weight:",
                "How strongly a real horizon/fault crossing is pulled toward the mapped fault position.",
                low_text="Weak attachment. Safer if fault picks are uncertain, but contacts may detach across slices.",
                high_text="Strong attachment. Better for preserving true crossings, but can over-pull the horizon onto a wrong fault trace.",
            ),
            spin_fault_snap_weight,
        )

        spin_fault_attach_depth_tol = QSpinBox()
        spin_fault_attach_depth_tol.setRange(0, 20)
        spin_fault_attach_depth_tol.setValue(2)
        self._apply_control_tooltip(
            spin_fault_attach_depth_tol,
            "Allowed depth mismatch when following the same crossing onto the next slice.",
            low_text="Strict depth matching. Prevents false attachments, but may lose real crossings when throw changes quickly.",
            high_text="Flexible depth matching. Better for variable throw, but can attach to the wrong depth level.",
        )
        fault_form.addRow(
            self._make_control_label(
                "Depth tol:",
                "Allowed depth mismatch when following the same crossing onto the next slice.",
                low_text="Strict depth matching. Prevents false attachments, but may lose real crossings when throw changes quickly.",
                high_text="Flexible depth matching. Better for variable throw, but can attach to the wrong depth level.",
            ),
            spin_fault_attach_depth_tol,
        )

        spin_fault_attach_row_tol = QSpinBox()
        spin_fault_attach_row_tol.setRange(0, 30)
        spin_fault_attach_row_tol.setValue(8)
        self._apply_control_tooltip(
            spin_fault_attach_row_tol,
            "How far laterally the current horizon may sit from the predicted crossing before attachment is rejected.",
            low_text="Strict lateral consistency. Good for clean data, but may miss real crossings in noisy areas.",
            high_text="Permissive lateral consistency. Better for noisy data, but easier to force a wrong crossing.",
        )
        fault_form.addRow(
            self._make_control_label(
                "Row tol:",
                "How far laterally the current horizon may sit from the predicted crossing before attachment is rejected.",
                low_text="Strict lateral consistency. Good for clean data, but may miss real crossings in noisy areas.",
                high_text="Permissive lateral consistency. Better for noisy data, but easier to force a wrong crossing.",
            ),
            spin_fault_attach_row_tol,
        )

        spin_fault_attach_col_tol = QSpinBox()
        spin_fault_attach_col_tol.setRange(0, 20)
        spin_fault_attach_col_tol.setValue(4)
        self._apply_control_tooltip(
            spin_fault_attach_col_tol,
            "How far vertically the current horizon may sit from the predicted crossing before attachment is rejected.",
            low_text="Strict vertical consistency. Safer for clean horizons, but can miss real crossings with local depth variation.",
            high_text="More vertical flexibility. Better for drag or rollover near faults, but can lock onto the wrong event.",
        )
        fault_form.addRow(
            self._make_control_label(
                "Col tol:",
                "How far vertically the current horizon may sit from the predicted crossing before attachment is rejected.",
                low_text="Strict vertical consistency. Safer for clean horizons, but can miss real crossings with local depth variation.",
                high_text="More vertical flexibility. Better for drag or rollover near faults, but can lock onto the wrong event.",
            ),
            spin_fault_attach_col_tol,
        )

        spin_fault_attach_blend = QSpinBox()
        spin_fault_attach_blend.setRange(0, 10)
        spin_fault_attach_blend.setValue(3)
        self._apply_control_tooltip(
            spin_fault_attach_blend,
            "How many neighboring samples are softly blended into the attached crossing point.",
            low_text="Very localized attachment. Preserves sharp offsets, but may leave a visible kink.",
            high_text="Broader blending. Produces a smoother contact, but may smear the throw over too wide an area.",
        )
        fault_form.addRow(
            self._make_control_label(
                "Blend rows:",
                "How many neighboring samples are softly blended into the attached crossing point.",
                low_text="Very localized attachment. Preserves sharp offsets, but may leave a visible kink.",
                high_text="Broader blending. Produces a smoother contact, but may smear the throw over too wide an area.",
            ),
            spin_fault_attach_blend,
        )

        right_widget.addWidget(fault_group)
        
        # Advanced Weights (collapsible, compact grid)
        weights_group = QGroupBox("Advanced Weights")
        weights_group.setCheckable(True)
        weights_group.setChecked(False)
        weights_grid = QGridLayout(weights_group)
        weights_grid.setSpacing(4)
        
        spin_smooth_weight = QDoubleSpinBox()
        spin_smooth_weight.setRange(0.0, 1.0)
        spin_smooth_weight.setValue(0.3)
        spin_smooth_weight.setSingleStep(0.1)
        self._apply_control_tooltip(
            spin_smooth_weight,
            "How strongly the tracker prefers continuity with the previous slice.",
            low_text="Attributes dominate. More flexible, but easier to drift.",
            high_text="Continuity dominates. More stable, but less able to follow real structural changes.",
        )
        weights_grid.addWidget(
            self._make_control_label(
                "Smooth:",
                "How strongly the tracker prefers continuity with the previous slice.",
                low_text="Attributes dominate. More flexible, but easier to drift.",
                high_text="Continuity dominates. More stable, but less able to follow real structural changes.",
            ),
            0,
            0,
        )
        weights_grid.addWidget(spin_smooth_weight, 0, 1)
        
        spin_amp_weight = QDoubleSpinBox()
        spin_amp_weight.setRange(0.0, 1.0)
        spin_amp_weight.setValue(0.3)
        spin_amp_weight.setSingleStep(0.1)
        self._apply_control_tooltip(
            spin_amp_weight,
            "How much reflection strength influences the pick.",
            low_text="Amplitude has little effect. Useful if amplitudes are unreliable.",
            high_text="Strong reflectors dominate. Good for bright horizons, risky if nearby events are brighter.",
        )
        weights_grid.addWidget(
            self._make_control_label(
                "Amp:",
                "How much reflection strength influences the pick.",
                low_text="Amplitude has little effect. Useful if amplitudes are unreliable.",
                high_text="Strong reflectors dominate. Good for bright horizons, risky if nearby events are brighter.",
            ),
            0,
            2,
        )
        weights_grid.addWidget(spin_amp_weight, 0, 3)
        
        spin_edge_weight = QDoubleSpinBox()
        spin_edge_weight.setRange(0.0, 1.0)
        spin_edge_weight.setValue(0.2)
        spin_edge_weight.setSingleStep(0.1)
        self._apply_control_tooltip(
            spin_edge_weight,
            "How much reflector boundary sharpness influences the pick.",
            low_text="Edge sharpness has little effect.",
            high_text="Sharp boundaries dominate. Good for crisp events, risky in noisy data or near faults.",
        )
        weights_grid.addWidget(
            self._make_control_label(
                "Edge:",
                "How much reflector boundary sharpness influences the pick.",
                low_text="Edge sharpness has little effect.",
                high_text="Sharp boundaries dominate. Good for crisp events, risky in noisy data or near faults.",
            ),
            1,
            0,
        )
        weights_grid.addWidget(spin_edge_weight, 1, 1)
        
        spin_phase_weight = QDoubleSpinBox()
        spin_phase_weight.setRange(0.0, 1.0)
        spin_phase_weight.setValue(0.2)
        spin_phase_weight.setSingleStep(0.1)
        self._apply_control_tooltip(
            spin_phase_weight,
            "How much phase continuity influences the pick.",
            low_text="Phase has little effect.",
            high_text="Phase continuity dominates. Useful for subtle events, but can mislead if phase is unstable.",
        )
        weights_grid.addWidget(
            self._make_control_label(
                "Phase:",
                "How much phase continuity influences the pick.",
                low_text="Phase has little effect.",
                high_text="Phase continuity dominates. Useful for subtle events, but can mislead if phase is unstable.",
            ),
            1,
            2,
        )
        weights_grid.addWidget(spin_phase_weight, 1, 3)
        
        spin_sim_weight = QDoubleSpinBox()
        spin_sim_weight.setRange(0.0, 1.0)
        spin_sim_weight.setValue(0.15)
        spin_sim_weight.setSingleStep(0.05)
        self._apply_control_tooltip(
            spin_sim_weight,
            "How much lateral coherence influences the pick.",
            low_text="Similarity has little effect.",
            high_text="Coherence dominates. Good for continuous horizons, but may suppress real local changes.",
        )
        weights_grid.addWidget(
            self._make_control_label(
                "Sim:",
                "How much lateral coherence influences the pick.",
                low_text="Similarity has little effect.",
                high_text="Coherence dominates. Good for continuous horizons, but may suppress real local changes.",
            ),
            2,
            0,
        )
        weights_grid.addWidget(spin_sim_weight, 2, 1)
        
        spin_dip_weight = QDoubleSpinBox()
        spin_dip_weight.setRange(0.0, 1.0)
        spin_dip_weight.setValue(0.15)
        spin_dip_weight.setSingleStep(0.05)
        self._apply_control_tooltip(
            spin_dip_weight,
            "How much dip continuity from the previous slice influences the pick.",
            low_text="Dip has little effect. Better where dip changes quickly.",
            high_text="Dip continuity dominates. Better for smooth structure, but can resist real local dip changes.",
        )
        weights_grid.addWidget(
            self._make_control_label(
                "Dip:",
                "How much dip continuity from the previous slice influences the pick.",
                low_text="Dip has little effect. Better where dip changes quickly.",
                high_text="Dip continuity dominates. Better for smooth structure, but can resist real local dip changes.",
            ),
            2,
            2,
        )
        weights_grid.addWidget(spin_dip_weight, 2, 3)
        
        right_widget.addWidget(weights_group)
        right_widget.addStretch()
        columns_layout.addLayout(right_widget)
        
        layout.addLayout(columns_layout)
        
        # === BUTTONS ===
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_ok = QPushButton("Propagate")
        btn_cancel = QPushButton("Cancel")
        btn_ok.clicked.connect(dialog.accept)
        btn_cancel.clicked.connect(dialog.reject)
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)
        
        if dialog.exec() != QDialog.Accepted:
            self.enable_actions()
            return
        
        # Get parameters
        selected_idx = combo_horizon.currentIndex()
        seed_uid = combo_horizon.currentData()
        seed_name = all_lines[selected_idx][1]
        seed_slice_idx = all_lines[selected_idx][2]
        
        # If slice index unknown, use current slice
        if seed_slice_idx < 0:
            seed_slice_idx = self.current_slice_index
            self.print_terminal(f"Using current slice {seed_slice_idx} as seed position")
        
        direction = direction_group.checkedId()  # 0=forward, 1=backward, 2=both
        num_slices = spin_slices.value()
        
        # Build list of selected attributes
        selected_attributes = []
        if check_amplitude.isChecked():
            selected_attributes.append('amplitude')
        if check_edge.isChecked():
            selected_attributes.append('edge')
        if check_phase.isChecked():
            selected_attributes.append('phase')
        if check_similarity.isChecked():
            selected_attributes.append('similarity')
        if check_dip.isChecked():
            selected_attributes.append('dip')
        
        # Default to amplitude+edge if nothing selected
        if not selected_attributes:
            selected_attributes = ['amplitude', 'edge']
        
        # Get tracking parameters
        search_window = spin_search.value()
        smooth_sigma = spin_smooth.value()
        max_jump = spin_max_jump.value()
        fault_snap_weight = spin_fault_snap_weight.value()
        fault_attach_depth_tolerance = spin_fault_attach_depth_tol.value()
        fault_attach_apply_row_tolerance = spin_fault_attach_row_tol.value()
        fault_attach_apply_col_tolerance = spin_fault_attach_col_tol.value()
        fault_attach_blend_rows = spin_fault_attach_blend.value()
        
        # Get weights (use defaults if not expanded)
        if weights_group.isChecked():
            smoothness_weight = spin_smooth_weight.value()
            amplitude_weight = spin_amp_weight.value()
            edge_weight = spin_edge_weight.value()
            phase_weight = spin_phase_weight.value()
            similarity_weight = spin_sim_weight.value()
            dip_weight = spin_dip_weight.value()
        else:
            smoothness_weight = 0.3
            amplitude_weight = 0.3
            edge_weight = 0.2
            phase_weight = 0.2
            similarity_weight = 0.15
            dip_weight = 0.15
        
        self.print_terminal(f"=== Propagating Horizon ===")
        self.print_terminal(f"Seed horizon: {seed_name} (slice {seed_slice_idx})")
        self.print_terminal(f"Direction: {['Forward', 'Backward', 'Both'][direction]}")
        self.print_terminal(f"Attributes: {', '.join(selected_attributes)}")
        self.print_terminal(f"Search: ±{search_window}, Smooth: {smooth_sigma}, MaxJump: {max_jump}")
        
        self.print_terminal(
            "Fault attach: "
            f"snap={fault_snap_weight}, depth_tol={fault_attach_depth_tolerance}, "
            f"row_tol={fault_attach_apply_row_tolerance}, col_tol={fault_attach_apply_col_tolerance}, "
            f"blend={fault_attach_blend_rows}"
        )
        
        # Run propagation
        try:
            self._run_horizon_propagation(
                seed_uid=seed_uid,
                direction=direction,
                num_slices=num_slices,
                attributes=selected_attributes,
                search_window=search_window,
                smooth_sigma=smooth_sigma,
                max_jump=max_jump,
                smoothness_weight=smoothness_weight,
                amplitude_weight=amplitude_weight,
                edge_weight=edge_weight,
                phase_weight=phase_weight,
                similarity_weight=similarity_weight,
                dip_weight=dip_weight,
                fault_snap_weight=fault_snap_weight,
                fault_attach_depth_tolerance=fault_attach_depth_tolerance,
                fault_attach_apply_row_tolerance=fault_attach_apply_row_tolerance,
                fault_attach_apply_col_tolerance=fault_attach_apply_col_tolerance,
                fault_attach_blend_rows=fault_attach_blend_rows,
                seed_slice_index=seed_slice_idx
            )
        except Exception as e:
            self.print_terminal(f"Error during propagation: {e}")
            self.print_terminal(traceback_format_exc())
        
        self.enable_actions()
    
    def _run_horizon_propagation(
        self,
        seed_uid,
        direction,
        num_slices,
        attributes=None,
        search_window=15,
        smooth_sigma=2.0,
        max_jump=3,
        smoothness_weight=0.3,
        amplitude_weight=0.3,
        edge_weight=0.2,
        phase_weight=0.2,
        similarity_weight=0.15,
        dip_weight=0.15,
        fault_snap_weight=2.0,
        fault_attach_depth_tolerance=2,
        fault_attach_apply_row_tolerance=8,
        fault_attach_apply_col_tolerance=4,
        fault_attach_blend_rows=3,
        seed_slice_index=None
    ):
        """
        Execute the horizon propagation using attribute-guided tracking.
        Creates a SINGLE multipart PolyLine entity containing all propagated segments.
        
        Args:
            seed_uid: UID of the seed horizon line
            direction: 0=forward, 1=backward, 2=both
            num_slices: Number of slices to propagate
            attributes: List of attributes to use ['amplitude', 'edge', 'phase', 'similarity', 'dip']
            search_window: Search window size (samples)
            smooth_sigma: Gaussian smoothing sigma (0=no smoothing)
            max_jump: Maximum allowed jump between slices (samples)
            smoothness_weight: Weight for smooth path preference (0-1)
            amplitude_weight: Weight for amplitude tracking (0-1)
            edge_weight: Weight for edge strength (0-1)
            phase_weight: Weight for phase continuity (0-1)
            similarity_weight: Weight for trace similarity (0-1)
            dip_weight: Weight for dip consistency (0-1)
            fault_snap_weight: Strength of fault snapping when a real crossing is detected
            fault_attach_depth_tolerance: Max allowed vertical shift when following a crossing
            fault_attach_apply_row_tolerance: Max lateral mismatch before forcing attachment
            fault_attach_apply_col_tolerance: Max vertical mismatch before forcing attachment
            fault_attach_blend_rows: Neighbor rows softly blended into the attached point
            seed_slice_index: Index of the seed slice
        """
        if attributes is None:
            attributes = ['amplitude', 'edge']

        
        # Get the seismic data
        if not hasattr(self, '_cached_seismic') or self._cached_seismic is None:
            self.print_terminal("No cached seismic data!")
            return
        
        seismic = self._cached_seismic
        dims = self._cached_dims
        bounds = self._cached_bounds
        
        # Get the 3D data array
        if 'intensity' in seismic.array_names:
            data = seismic['intensity']
        elif seismic.array_names:
            data = seismic[seismic.array_names[0]]
        else:
            self.print_terminal("No data arrays in seismic!")
            return
        
        data_3d = data.reshape(dims, order='F').astype(np.float32)
        
        # Calculate spacing
        spacing = [
            (bounds[1] - bounds[0]) / max(dims[0] - 1, 1),
            (bounds[3] - bounds[2]) / max(dims[1] - 1, 1),
            (bounds[5] - bounds[4]) / max(dims[2] - 1, 1)
        ]
        
        # Get the seed horizon points using the proper method
        seed_vtk = None
        try:
            # Use the collection's get_uid_vtk_obj method which handles the uid column properly
            seed_vtk = self.parent.geol_coll.get_uid_vtk_obj(seed_uid)
        except Exception as e:
            self.print_terminal(f"Could not get seed horizon vtk object: {e}")
        
        if seed_vtk is None:
            self.print_terminal(f"Could not get seed horizon! UID: {seed_uid}")
            return
        
        seed_points = np.array(seed_vtk.GetPoints().GetData())
        if len(seed_points) == 0:
            self.print_terminal("Seed horizon has no points!")
            return
        
        self.print_terminal(f"Seed horizon has {len(seed_points)} points")
        
        # Get the seed slice index - use provided value or fall back to current slice
        if seed_slice_index is not None:
            current_idx = seed_slice_index
        else:
            current_idx = self.current_slice_index
        
        self.print_terminal(f"Starting propagation from slice {current_idx}")
        
        # Determine slice limits based on axis
        if self.current_axis == 'Inline':
            max_slice = dims[0] - 1
        elif self.current_axis == 'Crossline':
            max_slice = dims[1] - 1
        else:
            max_slice = dims[2] - 1
        
        # Determine which slices to propagate to
        slices_to_track = []
        if direction == 0:  # Forward
            slices_to_track = list(range(current_idx + 1, min(current_idx + num_slices + 1, max_slice + 1)))
        elif direction == 1:  # Backward
            slices_to_track = list(range(current_idx - 1, max(current_idx - num_slices - 1, -1), -1))
        else:  # Both
            forward = list(range(current_idx + 1, min(current_idx + num_slices + 1, max_slice + 1)))
            backward = list(range(current_idx - 1, max(current_idx - num_slices - 1, -1), -1))
            slices_to_track = backward[::-1] + forward  # Process in order
        
        self.print_terminal(f"Will propagate to {len(slices_to_track)} slices")
        
        if len(slices_to_track) == 0:
            self.print_terminal("No slices to propagate to!")
            return
        affine = self._get_seismic_axis_vectors()
        # Convert seed points to slice coordinates (row, col)
        seed_indices = []
        for pt in seed_points:
            rc = None
            if affine is not None:
                rc = self._world_to_slice_rc(pt, slice_idx=current_idx, affine=affine, axis=self.current_axis)
            if rc is None:
                if self.current_axis == 'Inline':
                    row = int((pt[1] - bounds[2]) / spacing[1]) if spacing[1] > 0 else 0
                    col = int((pt[2] - bounds[4]) / spacing[2]) if spacing[2] > 0 else 0
                elif self.current_axis == 'Crossline':
                    row = int((pt[0] - bounds[0]) / spacing[0]) if spacing[0] > 0 else 0
                    col = int((pt[2] - bounds[4]) / spacing[2]) if spacing[2] > 0 else 0
                else:  # Z-slice
                    row = int((pt[0] - bounds[0]) / spacing[0]) if spacing[0] > 0 else 0
                    col = int((pt[1] - bounds[2]) / spacing[1]) if spacing[1] > 0 else 0
                rc = (row, col)
            seed_indices.append(rc)
        
        # Subsample if too many points (for speed)
        if len(seed_indices) > 200:
            step = len(seed_indices) // 200
            seed_indices = seed_indices[::step]
            self.print_terminal(f"Subsampled seed to {len(seed_indices)} points")
        
        # Progress callback
        def progress_callback(msg, pct=None):
            self.print_terminal(f"Tracking: {msg}")
        
        # Run attribute-guided tracking
        self._is_propagating = True
        try:
            # Collect fault traces (if any) to make horizon propagation fault-aware.
            # This helps preserve horizon throw and prevents the horizon from snapping onto faults.
            fault_traces_by_slice = None
            try:
                wanted_slices = set([current_idx] + list(slices_to_track))
                fault_traces_by_slice = {}

                if hasattr(self, 'multipart_faults') and self.multipart_faults:
                    for fault_uid, info in list(self.multipart_faults.items()):
                        if (info.get('seismic_uid') != self.current_seismic_uid or
                            info.get('axis') != self.current_axis):
                            continue

                        fault_vtk = self.parent.geol_coll.get_uid_vtk_obj(fault_uid)
                        if fault_vtk is None or fault_vtk.GetNumberOfCells() == 0:
                            continue

                        cell_data = fault_vtk.GetCellData()
                        if cell_data is None or not cell_data.HasArray("slice_index"):
                            continue

                        slice_arr = cell_data.GetArray("slice_index")
                        n_cells = fault_vtk.GetNumberOfCells()

                        for cell_idx in range(n_cells):
                            sidx = int(slice_arr.GetValue(cell_idx))
                            if sidx not in wanted_slices:
                                continue

                            cell = fault_vtk.GetCell(cell_idx)
                            pts = cell.GetPoints()
                            if pts is None:
                                continue

                            n_pts = pts.GetNumberOfPoints()
                            if n_pts < 2:
                                continue

                            trace = []
                            for j in range(n_pts):
                                x, y, z = pts.GetPoint(j)
                                rc = None
                                if affine is not None:
                                    rc = self._world_to_slice_rc(
                                        (x, y, z),
                                        slice_idx=sidx,
                                        affine=affine,
                                        axis=self.current_axis,
                                    )
                                if rc is None:
                                    if self.current_axis == 'Inline':
                                        row = int((y - bounds[2]) / spacing[1]) if spacing[1] > 0 else 0
                                        col = int((z - bounds[4]) / spacing[2]) if spacing[2] > 0 else 0
                                    elif self.current_axis == 'Crossline':
                                        row = int((x - bounds[0]) / spacing[0]) if spacing[0] > 0 else 0
                                        col = int((z - bounds[4]) / spacing[2]) if spacing[2] > 0 else 0
                                    else:  # Z-slice
                                        row = int((x - bounds[0]) / spacing[0]) if spacing[0] > 0 else 0
                                        col = int((y - bounds[2]) / spacing[1]) if spacing[1] > 0 else 0
                                    rc = (row, col)
                                trace.append(rc)

                            if len(trace) >= 2:
                                fault_traces_by_slice.setdefault(sidx, []).append(trace)

                if not fault_traces_by_slice:
                    fault_traces_by_slice = None
            except Exception:
                fault_traces_by_slice = None

            success, horizons, result_msg = propagate_horizon(
                data_3d=data_3d,
                seed_positions=seed_indices,
                seed_slice_idx=current_idx,
                axis=self.current_axis,
                slices_to_track=slices_to_track,
                attributes=attributes,
                search_window=search_window,
                smooth_sigma=smooth_sigma,
                max_jump=max_jump,
                smoothness_weight=smoothness_weight,
                amplitude_weight=amplitude_weight,
                edge_weight=edge_weight,
                phase_weight=phase_weight,
                similarity_weight=similarity_weight,
                dip_weight=dip_weight,
                fault_snap_weight=fault_snap_weight,
                fault_attach_depth_tolerance=fault_attach_depth_tolerance,
                fault_attach_apply_row_tolerance=fault_attach_apply_row_tolerance,
                fault_attach_apply_col_tolerance=fault_attach_apply_col_tolerance,
                fault_attach_blend_rows=fault_attach_blend_rows,
                progress_callback=progress_callback,
                fault_traces_by_slice=fault_traces_by_slice
            )
            
            if not success:
                self.print_terminal(f"Tracking failed: {result_msg}")
                return
            
            self.print_terminal(f"Tracking complete: {len(horizons)} slices")
            
            if len(horizons) == 0:
                self.print_terminal("No horizons were tracked!")
                return
            
            # Build multipart polyline from tracking results
            all_points = []
            all_lines = []
            point_slice_indices = []
            cell_slice_indices = []
            slice_to_point_range = {}
            current_point_offset = 0
            
            sorted_slices = sorted(horizons.keys())
            
            for slice_idx in sorted_slices:
                positions = horizons[slice_idx]
                if len(positions) < 2:
                    continue
                
                # Convert slice coordinates to world coordinates
                world_points = []
                for row, col in positions:
                    wp = None
                    if affine is not None:
                        wp = self._slice_rc_to_world(
                            slice_idx=slice_idx,
                            row=row,
                            col=col,
                            affine=affine,
                            axis=self.current_axis,
                        )
                    if wp is None:
                        if self.current_axis == 'Inline':
                            x = bounds[0] + slice_idx * (bounds[1] - bounds[0]) / max(dims[0] - 1, 1)
                            y = bounds[2] + row * spacing[1]
                            z = bounds[4] + col * spacing[2]
                        elif self.current_axis == 'Crossline':
                            x = bounds[0] + row * spacing[0]
                            y = bounds[2] + slice_idx * (bounds[3] - bounds[2]) / max(dims[1] - 1, 1)
                            z = bounds[4] + col * spacing[2]
                        else:  # Z-slice
                            x = bounds[0] + row * spacing[0]
                            y = bounds[2] + col * spacing[1]
                            z = bounds[4] + slice_idx * (bounds[5] - bounds[4]) / max(dims[2] - 1, 1)
                        wp = (x, y, z)
                    world_points.append(wp)
                
                # Sort points along horizon
                world_points.sort(key=lambda p: p[0] if self.current_axis != 'Inline' else p[1])
                
                n_pts = len(world_points)
                start_idx = current_point_offset
                
                all_points.extend(world_points)
                point_slice_indices.extend([slice_idx] * n_pts)
                
                # VTK line connectivity
                all_lines.append(n_pts)
                all_lines.extend(list(range(start_idx, start_idx + n_pts)))
                cell_slice_indices.append(slice_idx)
                
                slice_to_point_range[slice_idx] = (start_idx, start_idx + n_pts - 1)
                current_point_offset += n_pts
            
            # Create VTK multipart polyline
            if len(all_points) >= 2 and len(cell_slice_indices) > 0:
                self.print_terminal(f"Creating multipart horizon with {len(cell_slice_indices)} parts, {len(all_points)} total points...")
                
                # Create VTK points
                vtk_points = vtkPoints()
                for pt in all_points:
                    vtk_points.InsertNextPoint(pt[0], pt[1], pt[2])
                
                # Create VTK lines (cell array)
                vtk_lines = vtkCellArray()
                i = 0
                while i < len(all_lines):
                    n_pts = all_lines[i]
                    vtk_lines.InsertNextCell(n_pts)
                    for j in range(n_pts):
                        vtk_lines.InsertCellPoint(all_lines[i + 1 + j])
                    i += n_pts + 1
                
                # Create the PolyLine entity
                multipart_line = PolyLine()
                multipart_line.SetPoints(vtk_points)
                multipart_line.SetLines(vtk_lines)
                
                # Add point data array for slice indices (allows filtering by slice)
                point_slice_array = vtkIntArray()
                point_slice_array.SetName("slice_index")
                point_slice_array.SetNumberOfComponents(1)
                for idx in point_slice_indices:
                    point_slice_array.InsertNextValue(idx)
                multipart_line.GetPointData().AddArray(point_slice_array)
                
                # Add cell data array for slice indices (allows filtering by slice)
                cell_slice_array = vtkIntArray()
                cell_slice_array.SetName("slice_index")
                cell_slice_array.SetNumberOfComponents(1)
                for idx in cell_slice_indices:
                    cell_slice_array.InsertNextValue(idx)
                multipart_line.GetCellData().AddArray(cell_slice_array)
                
                # Store the slice axis as field data so it can be recovered on project reload
                axis_array = vtkStringArray()
                axis_array.SetName("slice_axis")
                axis_array.SetNumberOfValues(1)
                axis_array.SetValue(0, self.current_axis)
                multipart_line.GetFieldData().AddArray(axis_array)
                
                # Create entity dictionary
                line_dict = deepcopy(self.parent.geol_coll.entity_dict)
                line_dict["name"] = self._build_propagated_entity_name(
                    seed_uid=seed_uid,
                    slice_indices=cell_slice_indices,
                    fallback_name="auto_horizon",
                )
                line_dict["topology"] = "PolyLine"
                line_dict["x_section"] = ""
                line_dict["vtk_obj"] = multipart_line
                self._set_entity_parent_to_current_seismic(line_dict)
                self._ensure_slice_index_property_metadata(
                    entity_dict=line_dict,
                    vtk_obj=multipart_line,
                    slice_indices=cell_slice_indices,
                )
                # Keep propagated horizon metadata aligned with the seed interpretation.
                line_dict["role"] = self._sanitize_legend_value(
                    self.parent.geol_coll.get_uid_role(seed_uid), "top"
                )
                line_dict["feature"] = self._sanitize_legend_value(
                    self.parent.geol_coll.get_uid_feature(seed_uid), "auto_horizon"
                )
                line_dict["scenario"] = self._sanitize_legend_value(
                    self.parent.geol_coll.get_uid_scenario(seed_uid), "undef"
                )
                
                # Add to collection
                new_uid = self.parent.geol_coll.add_entity_from_dict(line_dict)
                self._refresh_properties_legend()
                
                # Store multipart horizon metadata for visibility management
                if not hasattr(self, 'multipart_horizons'):
                    self.multipart_horizons = {}
                
                self.multipart_horizons[new_uid] = {
                    'seismic_uid': self.current_seismic_uid,
                    'axis': self.current_axis,
                    'slice_indices': list(slice_to_point_range.keys()),
                    'slice_to_cell_index': {slice_idx: i for i, slice_idx in enumerate(cell_slice_indices)},
                    'seed_slice': current_idx
                }
                
                self.print_terminal(f"=== Propagation Complete ===")
                self.print_terminal(f"Created multipart horizon: {line_dict['name']}")
                self.print_terminal(f"Contains {len(cell_slice_indices)} line segments across slices")
                self.print_terminal(f"Slice range: {min(cell_slice_indices)} to {max(cell_slice_indices)}")
                
                # Add actor to scene and update visibility
                self.show_actor_with_property(uid=new_uid, coll_name='geol_coll', visible=True)
                
                # CRITICAL: Set thick line width for multipart horizons for better visibility
                try:
                    if new_uid in self.plotter.renderer.actors:
                        actor = self.plotter.renderer.actors[new_uid]
                        if actor and hasattr(actor, 'GetProperty'):
                            actor.GetProperty().SetLineWidth(8)  # Very thick for propagated horizons
                            self.print_terminal(f"Set line width to 8 for multipart horizon {new_uid}")
                except Exception as e:
                    self.print_terminal(f"Could not set line width: {e}")
                
                self._mark_slice_visibility_dirty()
                self.update_interpretation_line_visibility()
                self.update_multipart_horizon_visibility(new_uid)
            else:
                self.print_terminal("No valid line segments were created during propagation!")

        except Exception as e:
            self.print_terminal(f"Error in propagation: {e}")
            self.print_terminal(traceback_format_exc())
        
        finally:
            self._is_propagating = False
            self.plotter.render()

    # ==================== End Auto Propagation Methods ====================

    # ==================== Fault Tracking Methods ====================
    
    def propagate_fault(self):
        """Open dialog to propagate a fault line across multiple slices."""
        self.disable_actions()
        
        # Get existing lines that could be fault seeds
        if not hasattr(self, 'interpretation_lines') or not self.interpretation_lines:
            QMessageBox.warning(self, "No Fault Seed Lines", 
                "Please draw a VERTICAL fault line first:\n\n"
                "1. Use 'Draw Interpretation Line' from the menu\n"
                "2. Draw a line following the fault (should be roughly vertical)\n"
                "3. Then use 'Propagate Fault' to extend it across slices.")
            self.enable_actions()
            return
        
        # Filter for lines on the current seismic (potential fault seeds)
        all_lines = []
        for uid, info in self.interpretation_lines.items():
            if info.get('seismic_uid') == self.current_seismic_uid:
                name = f"Line_{uid[:8]}"
                try:
                    mask = self.parent.geol_coll.df['uid'] == uid
                    if mask.any():
                        name = self.parent.geol_coll.df.loc[mask, 'name'].values[0]
                except:
                    pass
                slice_idx = info.get('slice_index', -1)
                all_lines.append((uid, name, slice_idx))
        
        if not all_lines:
            QMessageBox.warning(self, "No Lines", 
                "No seed lines found for the current seismic volume.\n\n"
                "Draw a vertical line on a fault using 'Draw Interpretation Line'.")
            self.enable_actions()
            return
        
        # Show compact dialog
 
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Propagate Fault")
        dialog.setMinimumWidth(450)
        layout = QVBoxLayout(dialog)
        layout.setSpacing(8)
        
        # Info label
        info = QLabel("Select a line drawn on a fault. The line should be roughly VERTICAL.")
        info.setStyleSheet("color: gray; font-style: italic;")
        info.setWordWrap(True)
        layout.addWidget(info)

        tooltip_hint = QLabel(
            "Hover an attribute or parameter to see what it does and what Low or High values mean."
        )
        tooltip_hint.setStyleSheet("color: gray;")
        tooltip_hint.setWordWrap(True)
        layout.addWidget(tooltip_hint)
        
        # Seed selection
        seed_layout = QHBoxLayout()
        seed_layout.addWidget(QLabel("Seed fault line:"))
        combo_seed = QComboBox()
        for uid, name, slice_idx in all_lines:
            display_text = f"{name} [Slice {slice_idx}]" if slice_idx >= 0 else f"{name} [Current]"
            combo_seed.addItem(display_text, uid)
        combo_seed.setMinimumWidth(200)
        seed_layout.addWidget(combo_seed, 1)
        layout.addLayout(seed_layout)
        
        # Two columns
        columns = QHBoxLayout()
        
        # Left: Direction + Attributes
        left = QVBoxLayout()
        
        dir_group = QGroupBox("Direction")
        dir_layout = QVBoxLayout(dir_group)
        dir_layout.setSpacing(2)
        direction_group = QButtonGroup(dialog)
        radio_forward = QRadioButton("Forward")
        radio_backward = QRadioButton("Backward")
        radio_both = QRadioButton("Both")
        radio_forward.setChecked(True)
        direction_group.addButton(radio_forward, 0)
        direction_group.addButton(radio_backward, 1)
        direction_group.addButton(radio_both, 2)
        dir_layout.addWidget(radio_forward)
        dir_layout.addWidget(radio_backward)
        dir_layout.addWidget(radio_both)
        left.addWidget(dir_group)
        
        attr_group = QGroupBox("Attributes")
        attr_layout = QVBoxLayout(attr_group)
        attr_layout.setSpacing(2)
        check_vert_edge = QCheckBox("Vertical Edge")
        check_vert_edge.setChecked(True)
        check_discont = QCheckBox("Discontinuity")
        check_discont.setChecked(True)
        check_variance = QCheckBox("Variance")
        check_likelihood = QCheckBox("Likelihood")
        self._apply_control_tooltip(
            check_vert_edge,
            "Track the fault using strong vertical-edge response. This is usually the primary fault indicator.",
        )
        self._apply_control_tooltip(
            check_discont,
            "Track where reflector continuity breaks across the fault. Useful when the fault appears as a clear discontinuity.",
        )
        self._apply_control_tooltip(
            check_variance,
            "Track locally chaotic or high-variance zones around the fault damage zone.",
        )
        self._apply_control_tooltip(
            check_likelihood,
            "Track a combined fault-likelihood attribute built from edge, discontinuity, and variance.",
        )
        attr_layout.addWidget(check_vert_edge)
        attr_layout.addWidget(check_discont)
        attr_layout.addWidget(check_variance)
        attr_layout.addWidget(check_likelihood)
        left.addWidget(attr_group)
        left.addStretch()
        columns.addLayout(left)
        
        # Right: Parameters
        right = QVBoxLayout()
        
        params_group = QGroupBox("Parameters")
        params_form = QFormLayout(params_group)
        params_form.setSpacing(4)
        
        spin_slices = QSpinBox()
        spin_slices.setRange(1, 500)
        spin_slices.setValue(50)
        self._apply_control_tooltip(
            spin_slices,
            "How many slices to propagate the fault away from the seed.",
            low_text="Shorter propagation. Faster and safer when you only trust the fault locally.",
            high_text="Longer propagation. Covers more of the volume, but drift can accumulate farther from the seed.",
        )
        params_form.addRow(
            self._make_control_label(
                "Slices:",
                "How many slices to propagate the fault away from the seed.",
                low_text="Shorter propagation. Faster and safer when you only trust the fault locally.",
                high_text="Longer propagation. Covers more of the volume, but drift can accumulate farther from the seed.",
            ),
            spin_slices,
        )
        
        spin_search = QSpinBox()
        spin_search.setRange(3, 30)
        spin_search.setValue(10)
        self._apply_control_tooltip(
            spin_search,
            "Horizontal search range around the previous fault position for each depth sample.",
            low_text="Keeps the fault close to the previous slice. Good for stable faults, but may miss real lateral shifts.",
            high_text="Allows stronger lateral movement. Better for dipping or rapidly shifting faults, but easier to jump to noise.",
        )
        params_form.addRow(
            self._make_control_label(
                "Search window:",
                "Horizontal search range around the previous fault position for each depth sample.",
                low_text="Keeps the fault close to the previous slice. Good for stable faults, but may miss real lateral shifts.",
                high_text="Allows stronger lateral movement. Better for dipping or rapidly shifting faults, but easier to jump to noise.",
            ),
            spin_search,
        )
        
        spin_smooth = QDoubleSpinBox()
        spin_smooth.setRange(0.0, 5.0)
        spin_smooth.setValue(1.5)
        spin_smooth.setSingleStep(0.5)
        self._apply_control_tooltip(
            spin_smooth,
            "How strongly the propagated fault trace is smoothed along depth.",
            low_text="Preserves local bends and irregularities, but can look noisy.",
            high_text="Produces a cleaner trace, but can wash out real local dip changes or segmentation.",
        )
        params_form.addRow(
            self._make_control_label(
                "Smoothing:",
                "How strongly the propagated fault trace is smoothed along depth.",
                low_text="Preserves local bends and irregularities, but can look noisy.",
                high_text="Produces a cleaner trace, but can wash out real local dip changes or segmentation.",
            ),
            spin_smooth,
        )
        
        spin_max_jump = QSpinBox()
        spin_max_jump.setRange(1, 10)
        spin_max_jump.setValue(2)
        self._apply_control_tooltip(
            spin_max_jump,
            "Controls how abruptly the fault trace is allowed to change between neighboring depth samples.",
            low_text="Keeps the trace coherent and stable, but may underfit sharp bends.",
            high_text="Allows stronger local shape changes, but can increase zig-zagging and false excursions.",
        )
        params_form.addRow(
            self._make_control_label(
                "Max jump:",
                "Controls how abruptly the fault trace is allowed to change between neighboring depth samples.",
                low_text="Keeps the trace coherent and stable, but may underfit sharp bends.",
                high_text="Allows stronger local shape changes, but can increase zig-zagging and false excursions.",
            ),
            spin_max_jump,
        )
        
        right.addWidget(params_group)
        right.addStretch()
        columns.addLayout(right)
        
        layout.addLayout(columns)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_ok = QPushButton("Propagate Fault")
        btn_cancel = QPushButton("Cancel")
        btn_ok.clicked.connect(dialog.accept)
        btn_cancel.clicked.connect(dialog.reject)
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)
        
        if dialog.exec() != QDialog.Accepted:
            self.enable_actions()
            return
        
        # Get parameters
        selected_idx = combo_seed.currentIndex()
        seed_uid = combo_seed.currentData()
        seed_name = all_lines[selected_idx][1]
        seed_slice_idx = all_lines[selected_idx][2]
        
        if seed_slice_idx < 0:
            seed_slice_idx = self.current_slice_index
        
        direction = direction_group.checkedId()
        num_slices = spin_slices.value()
        
        # Build attributes list
        selected_attributes = []
        if check_vert_edge.isChecked():
            selected_attributes.append('vertical_edge')
        if check_discont.isChecked():
            selected_attributes.append('discontinuity')
        if check_variance.isChecked():
            selected_attributes.append('variance')
        if check_likelihood.isChecked():
            selected_attributes.append('likelihood')
        
        if not selected_attributes:
            selected_attributes = ['vertical_edge', 'discontinuity']
        
        search_window = spin_search.value()
        smooth_sigma = spin_smooth.value()
        max_jump = spin_max_jump.value()
        
        self.print_terminal(f"=== Propagating Fault ===")
        self.print_terminal(f"Seed: {seed_name} (slice {seed_slice_idx})")
        self.print_terminal(f"Attributes: {', '.join(selected_attributes)}")
        
        try:
            self._run_fault_propagation(
                seed_uid=seed_uid,
                direction=direction,
                num_slices=num_slices,
                attributes=selected_attributes,
                search_window=search_window,
                smooth_sigma=smooth_sigma,
                max_jump=max_jump,
                seed_slice_index=seed_slice_idx
            )
        except Exception as e:
            self.print_terminal(f"Error during fault propagation: {e}")
            self.print_terminal(traceback_format_exc())
        
        self.enable_actions()

    def _run_fault_propagation(
        self,
        seed_uid,
        direction,
        num_slices,
        attributes=None,
        search_window=10,
        smooth_sigma=1.5,
        max_jump=2,
        seed_slice_index=None
    ):
        """Execute fault propagation using attribute-guided tracking."""
        if attributes is None:
            attributes = ['vertical_edge', 'discontinuity']
        

        
        # Get seed line geometry using correct method
        seed_line = self.parent.geol_coll.get_uid_vtk_obj(seed_uid)
        if seed_line is None:
            self.print_terminal("Could not find seed fault line")
            return
        
        # Get seismic volume data from cache
        if not hasattr(self, '_cached_seismic') or self._cached_seismic is None:
            self.print_terminal("No cached seismic data!")
            return
        
        seismic = self._cached_seismic
        dims = self._cached_dims
        bounds = self._cached_bounds
        
        # Get the 3D data array
        if 'intensity' in seismic.array_names:
            data = seismic['intensity']
        elif seismic.array_names:
            data = seismic[seismic.array_names[0]]
        else:
            self.print_terminal("No data arrays in seismic!")
            return
        
        data_3d = data.reshape(dims, order='F').astype(np.float32)
        
        # Calculate spacing
        spacing = [
            (bounds[1] - bounds[0]) / max(dims[0] - 1, 1),
            (bounds[3] - bounds[2]) / max(dims[1] - 1, 1),
            (bounds[5] - bounds[4]) / max(dims[2] - 1, 1)
        ]
        
        # Get seed points from VTK object
        seed_points_world = np.array(seed_line.GetPoints().GetData())
        if len(seed_points_world) == 0:
            self.print_terminal("Seed fault line has no points!")
            return
        
        self.print_terminal(f"Seed fault line has {len(seed_points_world)} points")
        
        current_idx = seed_slice_index if seed_slice_index is not None else self.current_slice_index

        affine = self._get_seismic_axis_vectors()
        # Convert seed points to slice coordinates (row, col)
        # Same logic as horizon propagation
        seed_indices = []
        for pt in seed_points_world:
            rc = None
            if affine is not None:
                rc = self._world_to_slice_rc(pt, slice_idx=current_idx, affine=affine, axis=self.current_axis)
            if rc is None:
                if self.current_axis == 'Inline':
                    row = int((pt[1] - bounds[2]) / spacing[1]) if spacing[1] > 0 else 0
                    col = int((pt[2] - bounds[4]) / spacing[2]) if spacing[2] > 0 else 0
                elif self.current_axis == 'Crossline':
                    row = int((pt[0] - bounds[0]) / spacing[0]) if spacing[0] > 0 else 0
                    col = int((pt[2] - bounds[4]) / spacing[2]) if spacing[2] > 0 else 0
                else:  # Z-slice
                    row = int((pt[0] - bounds[0]) / spacing[0]) if spacing[0] > 0 else 0
                    col = int((pt[1] - bounds[2]) / spacing[1]) if spacing[1] > 0 else 0
                rc = (row, col)
            seed_indices.append(rc)
        
        if not seed_indices:
            self.print_terminal("Could not convert seed points to slice coordinates")
            return
        
        self.print_terminal(f"Converted to {len(seed_indices)} slice coordinates")
        
        # Build slice list
        if self.current_axis == 'Inline':
            max_slices = data_3d.shape[0]
        elif self.current_axis == 'Crossline':
            max_slices = data_3d.shape[1]
        else:
            max_slices = data_3d.shape[2]
        
        slices_to_track = []
        if direction == 0:  # Forward
            slices_to_track = list(range(current_idx + 1, min(current_idx + num_slices + 1, max_slices)))
        elif direction == 1:  # Backward
            slices_to_track = list(range(current_idx - 1, max(current_idx - num_slices - 1, -1), -1))
        else:  # Both
            forward = list(range(current_idx + 1, min(current_idx + num_slices + 1, max_slices)))
            backward = list(range(current_idx - 1, max(current_idx - num_slices - 1, -1), -1))
            slices_to_track = backward[::-1] + forward
        
        def progress_callback(msg, pct):
            self.print_terminal(f"  {msg}" + (f" ({pct}%)" if pct is not None else ""))
        
        self._is_propagating = True
        try:
            success, faults, result_msg = propagate_fault(
                data_3d=data_3d,
                seed_points=seed_indices,
                seed_slice_idx=current_idx,
                axis=self.current_axis,
                slices_to_track=slices_to_track,
                attributes=attributes,
                search_window=search_window,
                smooth_sigma=smooth_sigma,
                max_jump=max_jump,
                progress_callback=progress_callback
            )
            
            if not success:
                self.print_terminal(f"Fault tracking failed: {result_msg}")
                return
            
            self.print_terminal(f"Fault tracking complete: {len(faults)} slices")
            
            # Build multipart polyline for fault
            if faults:
                all_points = []
                all_lines = []
                point_slice_indices = []
                cell_slice_indices = []
                slice_to_point_range = {}
                current_point_offset = 0
                
                sorted_slices = sorted(faults.keys())
                
                for slice_idx in sorted_slices:
                    positions = faults[slice_idx]
                    if len(positions) < 2:
                        continue
                    
                    # Convert slice coordinates to world coordinates (same as horizon)
                    world_points = []
                    for row, col in positions:
                        wp = None
                        if affine is not None:
                            wp = self._slice_rc_to_world(
                                slice_idx=slice_idx,
                                row=row,
                                col=col,
                                affine=affine,
                                axis=self.current_axis,
                            )
                        if wp is None:
                            if self.current_axis == 'Inline':
                                x = bounds[0] + slice_idx * (bounds[1] - bounds[0]) / max(dims[0] - 1, 1)
                                y = bounds[2] + row * spacing[1]
                                z = bounds[4] + col * spacing[2]
                            elif self.current_axis == 'Crossline':
                                x = bounds[0] + row * spacing[0]
                                y = bounds[2] + slice_idx * (bounds[3] - bounds[2]) / max(dims[1] - 1, 1)
                                z = bounds[4] + col * spacing[2]
                            else:  # Z-slice
                                x = bounds[0] + row * spacing[0]
                                y = bounds[2] + col * spacing[1]
                                z = bounds[4] + slice_idx * (bounds[5] - bounds[4]) / max(dims[2] - 1, 1)
                            wp = (x, y, z)
                        world_points.append(wp)
                    
                    # For faults, sort by Z (vertical) instead of horizontal
                    world_points.sort(key=lambda p: p[2])
                    
                    n_pts = len(world_points)
                    start_idx = current_point_offset
                    
                    all_points.extend(world_points)
                    point_slice_indices.extend([slice_idx] * n_pts)
                    
                    all_lines.append(n_pts)
                    all_lines.extend(list(range(start_idx, start_idx + n_pts)))
                    cell_slice_indices.append(slice_idx)
                    
                    slice_to_point_range[slice_idx] = (start_idx, start_idx + n_pts - 1)
                    current_point_offset += n_pts
                
                # Create VTK multipart polyline
                if len(all_points) >= 2 and len(cell_slice_indices) > 0:
                    self.print_terminal(f"Creating multipart fault with {len(cell_slice_indices)} parts, {len(all_points)} total points...")
                    
                    # Create VTK points
                    vtk_points = vtkPoints()
                    for pt in all_points:
                        vtk_points.InsertNextPoint(pt[0], pt[1], pt[2])
                    
                    # Create VTK lines (cell array)
                    vtk_lines = vtkCellArray()
                    i = 0
                    while i < len(all_lines):
                        n_pts_in_line = all_lines[i]
                        id_list = vtkIdList()
                        for j in range(n_pts_in_line):
                            id_list.InsertNextId(all_lines[i + 1 + j])
                        vtk_lines.InsertNextCell(id_list)
                        i += n_pts_in_line + 1
                    
                    multipart_fault = PolyLine()
                    multipart_fault.SetPoints(vtk_points)
                    multipart_fault.SetLines(vtk_lines)
                    
                    # Add slice index arrays
                    point_array = vtkIntArray()
                    point_array.SetName("slice_index")
                    for idx in point_slice_indices:
                        point_array.InsertNextValue(idx)
                    multipart_fault.GetPointData().AddArray(point_array)
                    
                    cell_array = vtkIntArray()
                    cell_array.SetName("slice_index")
                    for idx in cell_slice_indices:
                        cell_array.InsertNextValue(idx)
                    multipart_fault.GetCellData().AddArray(cell_array)
                    
                    # Store the slice axis as field data so it can be recovered on project reload
                    axis_array = vtkStringArray()
                    axis_array.SetName("slice_axis")
                    axis_array.SetNumberOfValues(1)
                    axis_array.SetValue(0, self.current_axis)
                    multipart_fault.GetFieldData().AddArray(axis_array)
                    
                    # Create entity
                    fault_dict = deepcopy(self.parent.geol_coll.entity_dict)
                    fault_dict["name"] = self._build_propagated_entity_name(
                        seed_uid=seed_uid,
                        slice_indices=cell_slice_indices,
                        fallback_name="auto_fault",
                    )
                    fault_dict["topology"] = "PolyLine"
                    fault_dict["x_section"] = ""
                    fault_dict["vtk_obj"] = multipart_fault
                    self._set_entity_parent_to_current_seismic(fault_dict)
                    self._ensure_slice_index_property_metadata(
                        entity_dict=fault_dict,
                        vtk_obj=multipart_fault,
                        slice_indices=cell_slice_indices,
                    )
                    # Keep propagated fault metadata aligned with the seed interpretation.
                    fault_dict["role"] = self._sanitize_legend_value(
                        self.parent.geol_coll.get_uid_role(seed_uid), "fault"
                    )
                    fault_dict["feature"] = self._sanitize_legend_value(
                        self.parent.geol_coll.get_uid_feature(seed_uid), "auto_fault"
                    )
                    fault_dict["scenario"] = self._sanitize_legend_value(
                        self.parent.geol_coll.get_uid_scenario(seed_uid), "undef"
                    )
                    
                    new_uid = self.parent.geol_coll.add_entity_from_dict(fault_dict)
                    self._refresh_properties_legend()
                    
                    # Store metadata
                    if not hasattr(self, 'multipart_faults'):
                        self.multipart_faults = {}
                    
                    self.multipart_faults[new_uid] = {
                        'seismic_uid': self.current_seismic_uid,
                        'axis': self.current_axis,
                        'slice_indices': list(slice_to_point_range.keys()),
                        'slice_to_cell_index': {slice_idx: i for i, slice_idx in enumerate(cell_slice_indices)},
                        'seed_slice': current_idx
                    }
                    
                    self.print_terminal(f"=== Fault Propagation Complete ===")
                    self.print_terminal(f"Created multipart fault: {fault_dict['name']}")
                    self.print_terminal(f"Contains {len(cell_slice_indices)} segments across slices")
                    self.print_terminal(f"Total points: {len(all_points)}")
                    
                    # Initially hide the raw actor - we'll show filtered version
                    self.set_actor_visibility(new_uid, False)
                    
                    # Update visibility to show only current slice segment
                    self.update_multipart_fault_visibility(new_uid)
                    
                    # Note: Line width is set in update_multipart_fault_visibility
                    pass
                else:
                    self.print_terminal("No valid fault segments created!")
        
        except Exception as e:
            self.print_terminal(f"Error in fault propagation: {e}")
            self.print_terminal(traceback_format_exc())
        
        finally:
            self._is_propagating = False
            self.plotter.render()

    # ==================== End Fault Tracking Methods ====================

    def initialize_menu_tools(self):
        super().initialize_menu_tools()

        # Interpretation view does not use the generic 2D "Modify" workflow.
        # Keep only the local multipart-edit tools in the Modify menu.
        try:
            if hasattr(self, "menuModify") and self.menuModify is not None:
                self.menuModify.clear()
                self.menuModify.setEnabled(True)
                self.menuModify.menuAction().setVisible(True)
        except Exception:
            pass

        # Remove inherited Create actions that are not relevant to interpretation workflow.
        try:
            remove_create_texts = {
                "Draw line",
                "Copy parallel",
                "Copy kink",
                "Copy similar",
                "Section from strike",
                "Boundary from 2 points",
                "Boundary from 3 points",
                "Boundary from OBB",
            }
            for action in list(self.menuCreate.actions()):
                if action.text() in remove_create_texts:
                    self.menuCreate.removeAction(action)
        except Exception:
            pass

        # Add interpretation-specific draw line action
        self.drawInterpLineButton = QAction("Draw Interpretation Line", self)
        self.drawInterpLineButton.triggered.connect(self.draw_interpretation_line)
        self.menuCreate.addAction(self.drawInterpLineButton)
        
        # Add semi-auto tracking action
        self.semiAutoTrackButton = QAction("Semi-Auto Track Horizon", self)
        self.semiAutoTrackButton.triggered.connect(self.draw_semi_auto_line)
        self.menuCreate.addAction(self.semiAutoTrackButton)

        # Add semi-auto fault tracking action
        self.semiAutoTrackFaultButton = QAction("Semi-Auto Track Fault", self)
        self.semiAutoTrackFaultButton.triggered.connect(self.draw_semi_auto_fault_line)
        self.menuCreate.addAction(self.semiAutoTrackFaultButton)
        
        # Add propagate horizon action
        self.propagateHorizonButton = QAction("Propagate Horizon (Auto-Track 3D)", self)
        self.propagateHorizonButton.triggered.connect(self.propagate_horizon)
        self.menuCreate.addAction(self.propagateHorizonButton)
        
        # Add propagate fault action
        self.propagateFaultButton = QAction("Propagate Fault (Auto-Track 3D)", self)
        self.propagateFaultButton.triggered.connect(self.propagate_fault)
        self.menuCreate.addAction(self.propagateFaultButton)

        self.regularizeMultipartSamplingButton = QAction(
            "Regularize Multipart Sampling...", self
        )
        self.regularizeMultipartSamplingButton.triggered.connect(
            self.regularize_multipart_sampling
        )
        self.editLineButton = QAction("Edit line", self)
        self.editLineButton.triggered.connect(self.edit_selected_line)
        self.menuModify.addAction(self.editLineButton)
        self.simplifyLineButton = QAction("Simplify line", self)
        self.simplifyLineButton.triggered.connect(self.simplify_selected_lines)
        self.menuModify.addAction(self.simplifyLineButton)

        self.menuModify.addAction(self.regularizeMultipartSamplingButton)

        self.splitMultipartSlicesButton = QAction("Split Multipart Slices...", self)
        self.splitMultipartSlicesButton.triggered.connect(self.split_multipart_slices)
        self.menuModify.addAction(self.splitMultipartSlicesButton)

        self.separateDisconnectedMultipartButton = QAction(
            "Separate Disconnected Multipart Parts...", self
        )
        self.separateDisconnectedMultipartButton.triggered.connect(
            self.separate_disconnected_multipart_parts
        )
        self.menuModify.addAction(self.separateDisconnectedMultipartButton)

        self.deleteMultipartSlicesButton = QAction("Delete Multipart Slices...", self)
        self.deleteMultipartSlicesButton.triggered.connect(self.delete_multipart_slices)
        self.menuModify.addAction(self.deleteMultipartSlicesButton)

        # Connect our custom handler for additional processing (volume list refresh)
        try:
            self.parent.signals.entities_added.connect(self.on_entities_added)
        except Exception as e:
            self.print_terminal(f"Warning: Could not connect entities_added signal: {e}")
        
        # Connect to entity removal signal to clean up interpretation_lines
        try:
            self.parent.signals.entities_removed.connect(self.on_entities_removed)
        except Exception as e:
            self.print_terminal(f"Warning: Could not connect entities_removed signal: {e}")
        
        # Connect to colormap change signal to update slice colormap
        try:
            self.parent.signals.prop_legend_cmap_modified.connect(self.on_colormap_changed)
        except Exception as e:
            self.print_terminal(f"Warning: Could not connect prop_legend_cmap_modified signal: {e}")

        # Keep custom multipart filtered actors synced with standard geology legend edits.
        try:
            self.parent.signals.legend_color_modified.connect(
                self.on_geology_legend_style_changed
            )
            self.parent.signals.legend_thick_modified.connect(
                self.on_geology_legend_style_changed
            )
            self.parent.signals.legend_opacity_modified.connect(
                self.on_geology_legend_style_changed
            )
        except Exception as e:
            self.print_terminal(f"Warning: Could not connect geology legend style signals: {e}")
    
    def on_entities_removed(self, uids):
        """
        Called when entities are removed from any collection.

        IMPORTANT: Treat these UIDs as deleted from the scene and aggressively purge
        all interpretation-view tracking state (single-slice lines + multipart horizons/faults).
        This keeps ViewInterpretation in sync when the user deletes entities in BaseView.
        """
        if not uids:
            return

        # Normalize input to an iterable of strings
        try:
            uid_list = list(uids)
        except Exception:
            uid_list = [uids]

        for uid in uid_list:
            if not uid:
                continue

            # 1) Clean up single-slice interpretation tracking (semi-auto horizons/fault seeds)
            if hasattr(self, 'interpretation_lines') and uid in self.interpretation_lines:
                try:
                    self.unregister_interpretation_line(uid)
                except Exception:
                    pass

                # Keep visibility set consistent
                if hasattr(self, 'vis_lines_on_display') and uid in self.vis_lines_on_display:
                    try:
                        self.vis_lines_on_display.remove(uid)
                    except Exception:
                        pass

                self._invalidate_actor_cache(uid)
                self.print_terminal(f"Removed {uid[:8]}... from interpretation lines tracking")

            # 2) Clean up multipart horizon tracking + filtered actor
            if hasattr(self, 'multipart_horizons') and uid in self.multipart_horizons:
                try:
                    del self.multipart_horizons[uid]
                except Exception:
                    pass

                actor_name = f"multipart_slice_{uid}"
                if hasattr(self, 'plotter') and actor_name in self.plotter.renderer.actors:
                    try:
                        self.plotter.remove_actor(actor_name)
                    except Exception:
                        pass

                self._invalidate_actor_cache(uid)
                self.print_terminal(f"Removed multipart horizon {uid[:8]}... from tracking")

            # 3) Clean up multipart fault tracking + filtered actor
            if hasattr(self, 'multipart_faults') and uid in self.multipart_faults:
                try:
                    del self.multipart_faults[uid]
                except Exception:
                    pass

                actor_name = f"multipart_fault_slice_{uid}"
                if hasattr(self, 'plotter') and actor_name in self.plotter.renderer.actors:
                    try:
                        self.plotter.remove_actor(actor_name)
                    except Exception:
                        pass

                self._invalidate_actor_cache(uid)
                self.print_terminal(f"Removed multipart fault {uid[:8]}... from tracking")

        # Force a visibility refresh after removals (even if slice key didn't change)
        self._visibility_dirty = True
        if hasattr(self, '_last_visibility_key'):
            try:
                del self._last_visibility_key
            except Exception:
                pass
        try:
            self.update_interpretation_line_visibility()
            self.update_all_multipart_horizons_visibility()
            self.update_all_multipart_faults_visibility()
        except Exception:
            pass
    
    def on_colormap_changed(self, property_name):
        """Called when colormap is changed in the legend manager."""
        if property_name == 'intensity':
            self.update_slice_colormap()

    def on_geology_legend_style_changed(self, updated_uids, collection):
        """Refresh multipart filtered actors when geology legend style changes."""
        try:
            if collection is not self.parent.geol_coll:
                return
        except Exception:
            return

        try:
            changed = set(updated_uids or [])
        except Exception:
            changed = set()

        horizon_uids = set(getattr(self, "multipart_horizons", {}).keys())
        fault_uids = set(getattr(self, "multipart_faults", {}).keys())
        needs_refresh = bool(changed & (horizon_uids | fault_uids))

        if not needs_refresh:
            return

        self.update_all_multipart_horizons_visibility()
        self.update_all_multipart_faults_visibility()
        self.plotter.render()

    def _refresh_multipart_entities_for_uids(self, updated_uids=None, collection=None):
        """Rebuild filtered multipart actors after generic collection updates."""
        try:
            if collection is not self.parent.geol_coll:
                return
        except Exception:
            return

        try:
            changed = set(updated_uids or [])
        except Exception:
            changed = set()

        if not changed:
            return

        horizon_uids = changed & set(getattr(self, "multipart_horizons", {}).keys())
        fault_uids = changed & set(getattr(self, "multipart_faults", {}).keys())
        if not horizon_uids and not fault_uids:
            return

        for uid in horizon_uids:
            self.update_multipart_horizon_visibility(uid)
        for uid in fault_uids:
            self.update_multipart_fault_visibility(uid)

        self.plotter.render()

    def _actors_df_row_safe(self, uid=None):
        """Return the actor dataframe row for a uid, if present in this view."""
        try:
            return self.actors_df.loc[self.actors_df["uid"] == uid]
        except Exception:
            return self.actors_df.iloc[0:0]

    def _qt_object_is_alive(self, obj):
        """Return True when a Qt wrapper still owns a live C++ object."""
        if obj is None:
            return False
        try:

            return bool(shiboken_is_valid(obj))
        except Exception:
            try:
                obj.metaObject()
                return True
            except RuntimeError:
                return False
            except Exception:
                return True

    def _update_tree_properties_for_existing_uids(self, tree=None, uids=None):
        """Refresh property combos only for tree items that are already present."""
        if not self._qt_object_is_alive(tree):
            return

        try:
            uid_list = list(uids or [])
        except Exception:
            uid_list = []

        if not uid_list:
            return

        try:
            if not self._qt_object_is_alive(tree):
                return
            tree.blockSignals(True)
            all_items = tree.findItems("", Qt.MatchContains | Qt.MatchRecursive)
            items_by_uid = {}
            for item in all_items:
                try:
                    item_uid = tree.get_item_uid(item)
                except Exception:
                    item_uid = None
                if item_uid:
                    items_by_uid[str(item_uid)] = item

            for uid in uid_list:
                item = items_by_uid.get(str(uid))
                if item is None:
                    continue
                try:
                    row = tree.collection.df.loc[
                        tree.collection.df[tree.uid_label] == uid
                    ].iloc[0]
                except Exception:
                    continue
                try:
                    tree.removeItemWidget(item, tree.columnCount() - 1)
                except Exception:
                    pass
                try:
                    tree.setItemWidget(
                        item,
                        tree.columnCount() - 1,
                        tree.create_property_combo(row=row),
                    )
                except Exception:
                    continue
        finally:
            try:
                if self._qt_object_is_alive(tree):
                    tree.blockSignals(False)
            except Exception:
                pass

    def change_actor_color(self, updated_uids=None, collection=None):
        """Update actor color without assuming every uid has a raw actor."""
        actors = getattr(self.plotter.renderer, "actors", {})
        for uid in updated_uids or []:
            if uid not in self.uids_in_view or uid not in actors:
                continue
            color_R = collection.get_uid_legend(uid=uid)["color_R"]
            color_G = collection.get_uid_legend(uid=uid)["color_G"]
            color_B = collection.get_uid_legend(uid=uid)["color_B"]
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            actors[uid].GetProperty().SetColor(color_RGB)

    def change_actor_opacity(self, updated_uids=None, collection=None):
        """Update actor opacity without assuming every uid has a raw actor."""
        actors = getattr(self.plotter.renderer, "actors", {})
        for uid in updated_uids or []:
            if uid not in self.uids_in_view or uid not in actors:
                continue
            opacity = collection.get_uid_legend(uid=uid)["opacity"] / 100
            actors[uid].GetProperty().SetOpacity(opacity)

    def change_actor_line_thick(self, updated_uids=None, collection=None):
        """Update actor line width without assuming every uid has a raw actor."""
        actors = getattr(self.plotter.renderer, "actors", {})
        for uid in updated_uids or []:
            if uid not in self.uids_in_view or uid not in actors:
                continue
            line_thick = collection.get_uid_legend(uid=uid)["line_thick"]
            actors[uid].GetProperty().SetLineWidth(line_thick)

    def change_actor_point_size(self, updated_uids=None, collection=None):
        """Update actor point size without assuming every uid has a raw actor."""
        actors = getattr(self.plotter.renderer, "actors", {})
        for uid in updated_uids or []:
            if uid not in self.uids_in_view or uid not in actors:
                continue
            point_size = collection.get_uid_legend(uid=uid)["point_size"]
            actors[uid].GetProperty().SetPointSize(point_size)

    def entities_metadata_modified_update_views(self, collection=None, updated_uids=None):
        """Keep multipart interpretation actors slice-filtered after metadata edits."""
        super().entities_metadata_modified_update_views(
            collection=collection, updated_uids=updated_uids
        )
        self._refresh_multipart_entities_for_uids(
            updated_uids=updated_uids, collection=collection
        )

    def entities_data_keys_added_update_views(self, updated_uids=None, collection=None):
        """Refresh multipart filtered actors after property schema changes."""
        updated_uids = collection.filter_uids(query=self.view_filter, uids=updated_uids)
        tree = self.tree_from_coll(coll=collection)
        for uid in updated_uids:
            actor_row = self._actors_df_row_safe(uid)
            if actor_row.empty:
                continue
            shown_property = actor_row["show_property"].to_list()[0]
            if shown_property is None:
                continue
            if shown_property in collection.get_uid_properties_names(uid):
                continue
            show = actor_row["show"].to_list()[0]
            self.show_actor_with_property(
                uid=uid,
                coll_name=collection.collection_name,
                show_property=None,
                visible=show,
            )
            self.actors_df.loc[self.actors_df["uid"] == uid, ["show_property"]] = None
        self._update_tree_properties_for_existing_uids(tree=tree, uids=updated_uids)
        self._refresh_multipart_entities_for_uids(
            updated_uids=updated_uids, collection=collection
        )

    def entities_data_keys_removed_update_views(self, updated_uids=None, collection=None):
        """Refresh multipart filtered actors after property removals."""
        self.entities_data_keys_added_update_views(
            updated_uids=updated_uids, collection=collection
        )

    def entities_data_val_modified_update_views(self, updated_uids=None, collection=None):
        """Refresh multipart filtered actors after property value edits."""
        updated_uids = collection.filter_uids(query=self.view_filter, uids=updated_uids)
        for uid in updated_uids:
            actor_row = self._actors_df_row_safe(uid)
            if actor_row.empty:
                continue
            shown_property = actor_row["show_property"].to_list()[0]
            if shown_property is None:
                continue
            if shown_property in collection.get_uid_properties_names(uid):
                continue
            show = actor_row["show"].to_list()[0]
            self.show_actor_with_property(
                uid=uid,
                coll_name=collection.collection_name,
                show_property=None,
                visible=show,
            )
            self.actors_df.loc[self.actors_df["uid"] == uid, ["show_property"]] = None
        self._refresh_multipart_entities_for_uids(
            updated_uids=updated_uids, collection=collection
        )

    def show_qt_canvas(self):
        """Show the Qt Window and refresh the volume list."""
        super().show_qt_canvas()
        # Clear any full seismic volume actors that might have been inherited
        self.clear_seismic_volumes()
        # Refresh volume list to detect any seismics (combo_volume now exists)
        # This will call update_slice() at line 271 which creates and displays the slice
        self.refresh_volume_list()
        # Ensure plotter updates immediately
        if self.plotter:
            self.plotter.render()
    
    def _force_initial_display(self):
        """Force initial slice display after window is fully shown."""
        if self.current_seismic_uid:
            self.print_terminal("Forcing initial slice display...")
            self._camera_initialized = False  # Force camera reset
            self.update_slice_limits()
            self.update_camera_orientation()  # Sets correct view (YZ for Inline, etc.)
            self.update_slice()
    
    def clear_seismic_volumes(self):
        """Remove any full seismic volume actors from the plotter."""
        try:
            # Get all seismic UIDs from image_coll
            if hasattr(self.parent, 'image_coll') and self.parent.image_coll is not None:
                for uid in self.parent.image_coll.get_uids:
                    try:
                        topology = self.parent.image_coll.get_uid_topology(uid)
                        if topology == 'Seismics':
                            # Try to remove this actor if it exists
                            if uid in self.plotter.renderer.actors:
                                self.plotter.remove_actor(uid)
                                self.print_terminal(f"Cleared full seismic volume: {uid}")
                    except:
                        pass
        except Exception as e:
            self.print_terminal(f"Error clearing seismic volumes: {e}")

    def vert_exag(self):
        """Override parent's vertical exaggeration method to update slice view after scale change."""
        # Get current scale value as default
        current_scale = 1.0
        if self.plotter.scale is not None and len(self.plotter.scale) >= 3:
            current_scale = self.plotter.scale[2]
        
        exag_value = input_one_value_dialog(
            parent=self,
            title="Vertical exaggeration options",
            label="Set vertical exaggeration",
            default_value=current_scale,
        )
        
        if exag_value is not None:
            self.plotter.set_scale(zscale=exag_value)
            # Update the slice display and camera to respect new vertical exaggeration
            if self.current_seismic_uid:
                self.update_slice()
                self.plotter.render()
