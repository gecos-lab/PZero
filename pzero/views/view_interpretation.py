"""view_interpretation.py
PZero© Andrea Bistacchi"""

# PySide6 imports
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QComboBox, QSlider, QSpinBox, QVBoxLayout, QCheckBox
)
from PySide6.QtCore import Qt, QTimer

# VTK/PyVista imports
import pyvista as pv
import numpy as np
from copy import deepcopy
import heapq
from scipy import ndimage

# PZero imports
from .view_map import ViewMap
from ..entities_factory import Seismics, PolyLine
from ..helpers.helper_dialogs import multiple_input_dialog, input_one_value_dialog
from ..helpers.helper_widgets import Tracer

class ViewInterpretation(ViewMap):
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
        from PySide6.QtWidgets import QDockWidget
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
            import traceback
            self.print_terminal(traceback.format_exc())
                    
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
            else:
                # First time: add new slice actor
                self.slice_actor = self.plotter.add_mesh(
                    subset, 
                    name=slice_actor_name,
                    scalars=scalars,
                    clim=scalar_range,
                    cmap=cmap, 
                    show_scalar_bar=False, 
                    pickable=True, 
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
            import traceback
            self.print_terminal(traceback.format_exc())
        
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
                            import math
                            power = math.floor(math.log10(abs(mean_v)))
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

    def snap_points_to_slice(self, points):
        """Snap points to the current slice plane based on the current axis and slice position.
        Points from the tracer are in display coordinates (with VE applied), so we need to
        convert them back to real world coordinates before storing."""
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
        
        # Only Z coordinates need to be unscaled (X and Y don't have exaggeration)
        # The tracer picks in display space which has vertical exaggeration applied to Z
        if v_exag != 1.0:
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
            target_uids = self.interpretation_lines_by_slice.get(cache_key, set())
            
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
            import traceback
            self.print_terminal(traceback.format_exc())

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
            slice_info['slice_index'] == self.current_slice_index
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
                self.plotter.remove_actor(actor_name)
            except:
                pass
            
            # Also try to remove from renderer.actors dict directly
            try:
                if actor_name in self.plotter.renderer.actors:
                    actor = self.plotter.renderer.actors[actor_name]
                    self.plotter.renderer.RemoveActor(actor)
                    del self.plotter.renderer.actors[actor_name]
            except:
                pass
            
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
            except Exception as e:
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
                
                # Extract the matching cells manually
                from vtk import vtkPoints, vtkCellArray, vtkPolyData
                
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
                import traceback
                self.print_terminal(traceback.format_exc())
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
        from vtk import vtkPoints, vtkCellArray, vtkPolyData
        
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
                self.plotter.remove_actor(actor_name)
            except:
                pass
            
            # Also try to remove from renderer.actors dict directly
            try:
                if actor_name in self.plotter.renderer.actors:
                    actor = self.plotter.renderer.actors[actor_name]
                    self.plotter.renderer.RemoveActor(actor)
                    del self.plotter.renderer.actors[actor_name]
            except:
                pass
            
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
            import traceback
            self.print_terminal(traceback.format_exc())
            
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

            # First check if this is a multipart horizon (has slice_index cell data)
            # This is more efficient than checking geometry, and handles propagated horizons
            cell_data = vtk_obj.GetCellData()
            if cell_data and cell_data.HasArray("slice_index"):
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
                    
                # Register as multipart horizon
                if not hasattr(self, 'multipart_horizons'):
                    self.multipart_horizons = {}
                
                self.multipart_horizons[uid] = {
                    'seismic_uid': self.current_seismic_uid,
                    'axis': axis,
                    'slice_indices': slice_indices,
                    'slice_to_cell_index': slice_to_cell_index,
                    'seed_slice': slice_indices[0] if slice_indices else 0
                }
                
                self.print_terminal(f"Registered multipart horizon {uid}: {len(slice_indices)} slices on {axis}")
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

            from vtk import vtkIntArray, vtkStringArray

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

            if not hasattr(self, 'multipart_horizons'):
                self.multipart_horizons = {}
            self.multipart_horizons[uid] = {
                'seismic_uid': self.current_seismic_uid,
                'axis': axis_name,
                'slice_indices': unique_slices,
                'slice_to_cell_index': {sidx: cid for cid, sidx in per_cell.items()},
                'seed_slice': unique_slices[0],
            }

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
        # Also invalidate the visibility key to force update
        if hasattr(self, '_last_visibility_key'):
            del self._last_visibility_key

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
        """Show a preview line between two points (just a straight line for visual feedback)."""
        try:
            # Create a simple line between the two points for visual feedback
            line = pv.Line(point_a, point_b)
            preview_name = f'autotrack_preview_{len(self._autotrack_preview_actors)}'
            self.plotter.add_mesh(
                line,
                color='cyan',
                line_width=4,
                name=preview_name,
                pickable=False,
                reset_camera=False,
                lighting=False
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
            import traceback
            self.print_terminal(traceback.format_exc())
        
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
        from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QComboBox, QSpinBox, 
                                         QDoubleSpinBox, QLabel, QPushButton, QRadioButton, 
                                         QButtonGroup, QGroupBox, QCheckBox, QGridLayout, QFormLayout)
        
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
        params_form.addRow("Slices:", spin_slices)
        
        spin_search = QSpinBox()
        spin_search.setRange(5, 50)
        spin_search.setValue(15)
        params_form.addRow("Search window:", spin_search)
        
        spin_smooth = QDoubleSpinBox()
        spin_smooth.setRange(0.0, 10.0)
        spin_smooth.setValue(2.0)
        spin_smooth.setSingleStep(0.5)
        params_form.addRow("Smoothing:", spin_smooth)
        
        spin_max_jump = QSpinBox()
        spin_max_jump.setRange(1, 20)
        spin_max_jump.setValue(3)
        params_form.addRow("Max jump:", spin_max_jump)
        
        right_widget.addWidget(params_group)
        
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
        weights_grid.addWidget(QLabel("Smooth:"), 0, 0)
        weights_grid.addWidget(spin_smooth_weight, 0, 1)
        
        spin_amp_weight = QDoubleSpinBox()
        spin_amp_weight.setRange(0.0, 1.0)
        spin_amp_weight.setValue(0.3)
        spin_amp_weight.setSingleStep(0.1)
        weights_grid.addWidget(QLabel("Amp:"), 0, 2)
        weights_grid.addWidget(spin_amp_weight, 0, 3)
        
        spin_edge_weight = QDoubleSpinBox()
        spin_edge_weight.setRange(0.0, 1.0)
        spin_edge_weight.setValue(0.2)
        spin_edge_weight.setSingleStep(0.1)
        weights_grid.addWidget(QLabel("Edge:"), 1, 0)
        weights_grid.addWidget(spin_edge_weight, 1, 1)
        
        spin_phase_weight = QDoubleSpinBox()
        spin_phase_weight.setRange(0.0, 1.0)
        spin_phase_weight.setValue(0.2)
        spin_phase_weight.setSingleStep(0.1)
        weights_grid.addWidget(QLabel("Phase:"), 1, 2)
        weights_grid.addWidget(spin_phase_weight, 1, 3)
        
        spin_sim_weight = QDoubleSpinBox()
        spin_sim_weight.setRange(0.0, 1.0)
        spin_sim_weight.setValue(0.15)
        spin_sim_weight.setSingleStep(0.05)
        weights_grid.addWidget(QLabel("Sim:"), 2, 0)
        weights_grid.addWidget(spin_sim_weight, 2, 1)
        
        spin_dip_weight = QDoubleSpinBox()
        spin_dip_weight.setRange(0.0, 1.0)
        spin_dip_weight.setValue(0.15)
        spin_dip_weight.setSingleStep(0.05)
        weights_grid.addWidget(QLabel("Dip:"), 2, 2)
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
                seed_slice_index=seed_slice_idx
            )
        except Exception as e:
            self.print_terminal(f"Error during propagation: {e}")
            import traceback
            self.print_terminal(traceback.format_exc())
        
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
            seed_slice_index: Index of the seed slice
        """
        if attributes is None:
            attributes = ['amplitude', 'edge']
        from vtk import vtkPoints, vtkCellArray, vtkIntArray
        from ..helpers.autotracker import propagate_horizon
        
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
                from vtk import vtkStringArray
                axis_array = vtkStringArray()
                axis_array.SetName("slice_axis")
                axis_array.SetNumberOfValues(1)
                axis_array.SetValue(0, self.current_axis)
                multipart_line.GetFieldData().AddArray(axis_array)
                
                # Create entity dictionary
                line_dict = deepcopy(self.parent.geol_coll.entity_dict)
                line_dict["name"] = f"horizon_{current_idx}_multipart"
                line_dict["topology"] = "PolyLine"
                line_dict["x_section"] = ""
                line_dict["vtk_obj"] = multipart_line
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
                
                self.update_multipart_horizon_visibility(new_uid)
            else:
                self.print_terminal("No valid line segments were created during propagation!")

        except Exception as e:
            self.print_terminal(f"Error in propagation: {e}")
            import traceback
            self.print_terminal(traceback.format_exc())
        
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
            from PySide6.QtWidgets import QMessageBox
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
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "No Lines", 
                "No seed lines found for the current seismic volume.\n\n"
                "Draw a vertical line on a fault using 'Draw Interpretation Line'.")
            self.enable_actions()
            return
        
        # Show compact dialog
        from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QComboBox, QSpinBox, 
                                         QDoubleSpinBox, QLabel, QPushButton, QRadioButton, 
                                         QButtonGroup, QGroupBox, QCheckBox, QFormLayout)
        
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
        params_form.addRow("Slices:", spin_slices)
        
        spin_search = QSpinBox()
        spin_search.setRange(3, 30)
        spin_search.setValue(10)
        params_form.addRow("Search window:", spin_search)
        
        spin_smooth = QDoubleSpinBox()
        spin_smooth.setRange(0.0, 5.0)
        spin_smooth.setValue(1.5)
        spin_smooth.setSingleStep(0.5)
        params_form.addRow("Smoothing:", spin_smooth)
        
        spin_max_jump = QSpinBox()
        spin_max_jump.setRange(1, 10)
        spin_max_jump.setValue(2)
        params_form.addRow("Max jump:", spin_max_jump)
        
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
            import traceback
            self.print_terminal(traceback.format_exc())
        
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
        
        from ..helpers.autotracker import propagate_fault
        from vtk import vtkPoints, vtkCellArray, vtkIdList, vtkIntArray
        from ..entities_factory import PolyLine
        from copy import deepcopy
        import numpy as np
        
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
                    from vtk import vtkStringArray
                    axis_array = vtkStringArray()
                    axis_array.SetName("slice_axis")
                    axis_array.SetNumberOfValues(1)
                    axis_array.SetValue(0, self.current_axis)
                    multipart_fault.GetFieldData().AddArray(axis_array)
                    
                    # Create entity
                    fault_dict = deepcopy(self.parent.geol_coll.entity_dict)
                    fault_dict["name"] = f"fault_{current_idx}_multipart"
                    fault_dict["topology"] = "PolyLine"
                    fault_dict["x_section"] = ""
                    fault_dict["vtk_obj"] = multipart_fault
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
            import traceback
            self.print_terminal(traceback.format_exc())
        
        finally:
            self._is_propagating = False
            self.plotter.render()

    # ==================== End Fault Tracking Methods ====================

    def initialize_menu_tools(self):
        super().initialize_menu_tools()

        # Interpretation view does not use the generic 2D "Modify" workflow.
        # Hide the menu and remove inherited actions to avoid inconsistent behavior.
        try:
            if hasattr(self, "menuModify") and self.menuModify is not None:
                self.menuModify.clear()
                self.menuModify.setEnabled(False)
                self.menuModify.menuAction().setVisible(False)
                try:
                    self.menuBar().removeAction(self.menuModify.menuAction())
                except Exception:
                    pass
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
