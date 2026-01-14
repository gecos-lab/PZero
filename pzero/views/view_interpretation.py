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
        if self.current_seismic_uid:
             self.scan_and_index_existing_horizons()
        
    def show_actor_with_property(self, uid=None, coll_name=None, show_property=None, visible=None):
        """Override to prevent showing full seismic volumes - we only show slices."""
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
        # For all other entities, use normal display
        super().show_actor_with_property(uid=uid, coll_name=coll_name, show_property=show_property, visible=visible)

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
        self.chk_grid.stateChanged.connect(lambda: self.update_grid_annotations())
        bot_layout.addWidget(self.chk_grid)

        # Title Toggle
        self.chk_title = QCheckBox("Title")
        self.chk_title.setChecked(True)
        self.chk_title.stateChanged.connect(lambda: self.update_grid_annotations())
        bot_layout.addWidget(self.chk_title)
        
        # Directions Toggle
        self.chk_dirs = QCheckBox("NS/EW")
        self.chk_dirs.setChecked(True)
        self.chk_dirs.stateChanged.connect(lambda: self.update_grid_annotations())
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
                    else:
                        # NEW: Try to classify it immediately if we have a volume loaded
                        # This handles undo/redo or external adds
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
                                return

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
            
            self._camera_initialized = False  # Reset camera on volume change
            self.scalar_range = None  # Reset scalar range
            # Clear cached seismic data and scalar range when volume changes
            if hasattr(self, '_cached_seismic'):
                del self._cached_seismic
            if hasattr(self, '_cached_scalar_range'):
                del self._cached_scalar_range
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

    def update_slice(self):
        if not self.current_seismic_uid:
            self.print_terminal("No seismic UID selected")
            return
        
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
                self.current_slice_position = get_coord(0, i)
                subset = seismic.extract_subset([i, i, 0, dims[1]-1, 0, dims[2]-1])
            elif self.current_axis == 'Crossline':
                j = self.current_slice_index
                self.current_slice_position = get_coord(1, j)
                subset = seismic.extract_subset([0, dims[0]-1, j, j, 0, dims[2]-1])
            elif self.current_axis == 'Z-slice':
                k = self.current_slice_index
                self.current_slice_position = get_coord(2, k)
                subset = seismic.extract_subset([0, dims[0]-1, 0, dims[1]-1, k, k])
            
            if subset is None or subset.n_points == 0:
                self.print_terminal("Subset is empty!")
                return
            
            # Convert StructuredGrid to surface for proper 2D rendering
            subset = subset.extract_surface()
            
            scalars = 'intensity' if 'intensity' in subset.array_names else (subset.array_names[0] if subset.array_names else None)
            
            # Get colormap and scalar range
            cmap = self.get_seismic_colormap()
            scalar_range = self.scalar_range if hasattr(self, 'scalar_range') else None
            
            # Remove old slice actor
            if slice_actor_name in self.plotter.renderer.actors:
                self.plotter.remove_actor(slice_actor_name)
            
            # Add new slice
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
            self.update_grid_annotations()
            
            # Update visibility of interpretation lines for the current slice
            self.update_interpretation_line_visibility()
            
            # Update visibility of multipart horizons (efficient single-entity horizons)
            self.update_all_multipart_horizons_visibility()


        except Exception as e:
            self.print_terminal(f"Error updating slice: {e}")
            import traceback
            self.print_terminal(traceback.format_exc())
        
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
                    
            self.plotter.render()

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
        # One dictionary is set as input for a general widget of multiple-value-input
        line_dict_in = {
            "name": ["PolyLine name: ", "interp_line"],
            "role": [
                "Role: ",
                self.parent.geol_coll.valid_roles,
            ],
            "feature": [
                "Feature: ",
                self.parent.geol_coll.legend_df["feature"].tolist(),
            ],
            "scenario": [
                "Scenario: ",
                list(set(self.parent.geol_coll.legend_df["scenario"].tolist())),
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
        if not hasattr(self, 'current_slice_bounds') or self.current_slice_bounds is None:
            self.print_terminal("No slice bounds available for picking plane")
            return
            
        bounds = self.current_slice_bounds
        
        # Create a plane mesh at the slice position using explicit i and j directions
        # to ensure proper orientation matching the camera view
        if self.current_axis == 'Inline':
            # YZ plane at current X position
            # i direction along Y, j direction along Z
            plane = pv.Plane(
                center=(self.current_slice_position, (bounds[2]+bounds[3])/2, (bounds[4]+bounds[5])/2),
                direction=(1, 0, 0),  # Normal along X
                i_size=bounds[3] - bounds[2],  # Y extent
                j_size=abs(bounds[5] - bounds[4]),  # Z extent
                i_resolution=1,
                j_resolution=1
            )
        elif self.current_axis == 'Crossline':
            # XZ plane at current Y position  
            # i direction along X, j direction along Z
            plane = pv.Plane(
                center=((bounds[0]+bounds[1])/2, self.current_slice_position, (bounds[4]+bounds[5])/2),
                direction=(0, 1, 0),  # Normal along Y
                i_size=bounds[1] - bounds[0],  # X extent
                j_size=abs(bounds[5] - bounds[4]),  # Z extent
                i_resolution=1,
                j_resolution=1
            )
        elif self.current_axis == 'Z-slice':
            # XY plane at current Z position
            # i direction along X, j direction along Y
            plane = pv.Plane(
                center=((bounds[0]+bounds[1])/2, (bounds[2]+bounds[3])/2, self.current_slice_position),
                direction=(0, 0, 1),  # Normal along Z
                i_size=bounds[1] - bounds[0],  # X extent
                j_size=bounds[3] - bounds[2],  # Y extent
                i_resolution=1,
                j_resolution=1
            )
        
        # Add the plane with very low opacity so it's invisible but pickable
        self.plotter.add_mesh(
            plane,
            name='picking_plane',
            color='white',
            opacity=0.01,  # Nearly invisible
            pickable=True,
            reset_camera=False
        )
        self.print_terminal(f"Added picking plane at {self.current_axis} position {self.current_slice_position}")
        
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
        
        # Tiny offset towards the camera to avoid z-fighting with the slice
        offset = 1.0  # Just 1 unit offset in real coordinates
        
        # Now snap to the current slice position (in real coordinates)
        if self.current_axis == 'Inline':
            # For inline view (YZ plane), set X to the slice position
            snapped[:, 0] = self.current_slice_position - offset
        elif self.current_axis == 'Crossline':
            # For crossline view (XZ plane), set Y to the slice position
            snapped[:, 1] = self.current_slice_position - offset
        elif self.current_axis == 'Z-slice':
            # For Z-slice view (XY plane), set Z to the slice position
            snapped[:, 2] = self.current_slice_position + offset
            
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
        
        This uses VTK's threshold filter to show only cells with matching slice_index.
        
        Args:
            uid: Specific horizon UID to update, or None to update all multipart horizons
        """
        from vtk import vtkThreshold, vtkGeometryFilter
        
        if not hasattr(self, 'multipart_horizons'):
            return
        
        uids_to_update = [uid] if uid else list(self.multipart_horizons.keys())
        
        for horizon_uid in uids_to_update:
            if horizon_uid not in self.multipart_horizons:
                continue
                
            horizon_info = self.multipart_horizons[horizon_uid]
            actor_name = f"multipart_slice_{horizon_uid}"
            
            # Check if this horizon matches current view context
            if (horizon_info['seismic_uid'] != self.current_seismic_uid or 
                horizon_info['axis'] != self.current_axis):
                # Hide completely if not matching seismic/axis
                self.set_actor_visibility(horizon_uid, False)
                # Also remove the filtered actor
                if actor_name in self.plotter.renderer.actors:
                    self.plotter.remove_actor(actor_name)
                continue
            
            # Check if current slice is in this horizon's range
            if self.current_slice_index not in horizon_info['slice_indices']:
                # Hide if current slice is not in this horizon
                self.set_actor_visibility(horizon_uid, False)
                # Also remove the filtered actor - THIS IS THE KEY FIX
                if actor_name in self.plotter.renderer.actors:
                    self.plotter.remove_actor(actor_name)
                continue
            
            # Get the VTK object
            try:
                vtk_obj = self.parent.geol_coll.get_uid_vtk_obj(horizon_uid)
                if vtk_obj is None:
                    continue
            except:
                continue
            
            # Extract only cells matching current slice using VTK threshold
            try:
                # Set active scalars to slice_index for thresholding
                vtk_obj.GetCellData().SetActiveScalars("slice_index")
                
                # Threshold to extract only cells with current slice index
                threshold = vtkThreshold()
                threshold.SetInputData(vtk_obj)
                threshold.SetInputArrayToProcess(0, 0, 0, 1, "slice_index")  # 1 = cell data
                threshold.SetLowerThreshold(self.current_slice_index)
                threshold.SetUpperThreshold(self.current_slice_index)
                threshold.Update()
                
                # Convert to polydata for rendering
                geometry = vtkGeometryFilter()
                geometry.SetInputConnection(threshold.GetOutputPort())
                geometry.Update()
                
                filtered_polydata = geometry.GetOutput()
                
                if filtered_polydata.GetNumberOfCells() > 0:
                    # Update or create the actor for this filtered view
                    actor_name = f"multipart_slice_{horizon_uid}"
                    
                    # Get color from collection
                    try:
                        mask = self.parent.geol_coll.df['uid'] == horizon_uid
                        if mask.any():
                            row = self.parent.geol_coll.df.loc[mask].iloc[0]
                            color = (row['color_R']/255, row['color_G']/255, row['color_B']/255)
                        else:
                            color = (1.0, 1.0, 0.0)  # Default yellow
                    except:
                        color = (1.0, 1.0, 0.0)
                    
                    # Remove old filtered actor if exists
                    if actor_name in self.plotter.renderer.actors:
                        self.plotter.remove_actor(actor_name)
                    
                    # Add new filtered actor
                    self.plotter.add_mesh(
                        pv.wrap(filtered_polydata),
                        name=actor_name,
                        color=color,
                        line_width=2,
                        render_lines_as_tubes=False,
                        pickable=False,
                        reset_camera=False
                    )
                    
                    # Hide the full multipart actor (we're showing the filtered version)
                    self.set_actor_visibility(horizon_uid, False)
                else:
                    # No cells match - hide everything
                    actor_name = f"multipart_slice_{horizon_uid}"
                    if actor_name in self.plotter.renderer.actors:
                        self.plotter.remove_actor(actor_name)
                    self.set_actor_visibility(horizon_uid, False)
                    
            except Exception as e:
                self.print_terminal(f"Error filtering multipart horizon {horizon_uid}: {e}")
                # Fall back to showing full horizon
                self.set_actor_visibility(horizon_uid, True)

    def update_all_multipart_horizons_visibility(self):
        """Update visibility for all multipart horizons based on current slice."""
        if not hasattr(self, 'multipart_horizons'):
            return
        
        for uid in list(self.multipart_horizons.keys()):
            self.update_multipart_horizon_visibility(uid)

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
        self.update_interpretation_line_visibility()

    def scan_and_index_single_horizon(self, uid):
        """Check if a single horizon fits the current seismic grid and index it."""
        try:
            vtk_obj = self.parent.geol_coll.get_uid_vtk_obj(uid)
            if not vtk_obj or vtk_obj.GetNumberOfPoints() == 0:
                return

            bounds = vtk_obj.GetBounds() # (xmin, xmax, ymin, ymax, zmin, zmax)
            
            # Get metadata about current seismic
            # We need the real internal spatial reference (origin/spacing) 
            # which we cache in get_slice_as_2d_array logic or need to access again.
            
            if not hasattr(self, '_cached_bounds') or not self._cached_bounds:
                return

            seismic_bounds = self._cached_bounds
            seismic_dims = self._cached_dims
            
            # Simple tolerance for "flatness"
            TOLERANCE = 0.01 
            
            # Calculate spacing on the fly (assuming regular grid)
            dx = (seismic_bounds[1] - seismic_bounds[0]) / max(seismic_dims[0] - 1, 1)
            dy = (seismic_bounds[3] - seismic_bounds[2]) / max(seismic_dims[1] - 1, 1)
            dz = (seismic_bounds[5] - seismic_bounds[4]) / max(seismic_dims[2] - 1, 1)

            # Check for Inline (YZ plane, X is constant)
            if abs(bounds[1] - bounds[0]) < TOLERANCE:
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
            if abs(bounds[3] - bounds[2]) < TOLERANCE:
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
            if abs(bounds[5] - bounds[4]) < TOLERANCE:
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
        
        # Extract the 2D slice based on current axis
        axis_info = {
            'axis': self.current_axis,
            'slice_index': self.current_slice_index,
            'bounds': bounds,
            'dims': dims,
            'spacing': spacing
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
        
        # The picked point Z is in display coords (scaled by VE)
        # Convert Z back to real coordinates for slice indexing
        real_z = world_point[2] / v_exag if v_exag != 0 else world_point[2]
        
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
        row, col = slice_point
        
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
    
    def draw_semi_auto_line(self):
        """
        Semi-automatic horizon tracking using edge detection and A* pathfinding.
        User clicks multiple waypoints along the horizon, then right-clicks to finish.
        The algorithm finds optimal paths between consecutive waypoints.
        """
        self.disable_actions()
        
        if not self.current_seismic_uid:
            self.print_terminal("Please select a seismic volume first!")
            self.enable_actions()
            return
        
        # Get slice data for edge detection
        slice_data, origin, spacing, axis_info = self.get_slice_as_2d_array()
        if slice_data is None:
            self.print_terminal("Could not extract slice data for auto-tracking!")
            self.enable_actions()
            return
        
        self.print_terminal(f"Slice data shape: {slice_data.shape}")
        
        # Compute edge cost map
        self.print_terminal("Computing edge detection cost map...")
        cost_map = self.compute_edge_cost_map(slice_data)
        self.print_terminal(f"Cost map range: {cost_map.min():.3f} to {cost_map.max():.3f}")
        
        # Get vertical exaggeration
        v_exag = 1.0
        try:
            if self.plotter.scale is not None and len(self.plotter.scale) >= 3:
                v_exag = self.plotter.scale[2]
                if v_exag == 0:
                    v_exag = 1.0
        except:
            pass
        self.print_terminal(f"Vertical exaggeration: {v_exag}")
        
        # Add forbidden zones around existing interpretation lines
        # This prevents the new path from jumping to or crossing existing horizons
        cost_map = self.add_existing_lines_to_cost_map(cost_map, axis_info, spacing, v_exag)
        self.print_terminal(f"Cost map range after forbidden zones: {cost_map.min():.3f} to {cost_map.max():.3f}")
        
        # CRITICAL: Make only the seismic slice pickable
        # This prevents picking from jumping to existing interpretation lines
        self._saved_pickable_states = {}
        for name, actor in self.plotter.renderer.actors.items():
            try:
                self._saved_pickable_states[name] = actor.GetPickable()
                # Make everything non-pickable except the seismic slice
                if name == "seismic_slice_actor":
                    actor.SetPickable(True)
                    self.print_terminal(f"Made {name} PICKABLE")
                else:
                    actor.SetPickable(False)
            except:
                pass
        
        # Store for use in callbacks
        self._autotrack_cost_map = cost_map
        self._autotrack_axis_info = axis_info
        self._autotrack_spacing = spacing
        self._autotrack_origin = origin
        self._autotrack_v_exag = v_exag
        self._autotrack_points = []  # Will hold multiple waypoints
        self._autotrack_markers = []  # Visual markers for clicked points
        self._autotrack_preview_actors = []  # Preview line segments
        
        # Create entity dictionary for the new line
        line_dict = deepcopy(self.parent.geol_coll.entity_dict)
        line_dict_in = {
            "name": ["PolyLine name: ", "auto_horizon"],
            "role": [
                "Role: ",
                self.parent.geol_coll.valid_roles,
            ],
            "feature": [
                "Feature: ",
                self.parent.geol_coll.legend_df["feature"].tolist(),
            ],
            "scenario": [
                "Scenario: ",
                list(set(self.parent.geol_coll.legend_df["scenario"].tolist())),
            ],
        }
        line_dict_updt = multiple_input_dialog(
            title="Semi-Auto Horizon Tracking", input_dict=line_dict_in
        )
        
        if line_dict_updt is None:
            self.enable_actions()
            return
        
        for key in line_dict_updt:
            line_dict[key] = line_dict_updt[key]
        
        line_dict["topology"] = "PolyLine"
        line_dict["x_section"] = ""
        line_dict["vtk_obj"] = PolyLine()
        
        self._autotrack_line_dict = line_dict
        
        self.print_terminal("=== Semi-Auto Horizon Tracking ===")
        self.print_terminal("LEFT-CLICK: Add waypoint on the horizon")
        self.print_terminal("RIGHT-CLICK: Finish and create the tracked line")
        self.print_terminal("Add at least 2 waypoints, then right-click to finish.")
        
        # Calculate marker size based on slice bounds (more reliable than spacing)
        bounds = axis_info['bounds']
        extent_x = abs(bounds[1] - bounds[0])
        extent_y = abs(bounds[3] - bounds[2])
        extent_z = abs(bounds[5] - bounds[4]) * v_exag  # Account for VE in display
        max_extent = max(extent_x, extent_y, extent_z)
        marker_size = max_extent * 0.01  # 1% of max extent
        self._autotrack_marker_size = marker_size
        self.print_terminal(f"Marker size: {marker_size}")
        
        # Enable point picking - use pick_click_position which returns the exact clicked 3D world point
        def on_point_picked(picked_point):
            if picked_point is None:
                return
            
            # DEBUG: Print raw picked point
            self.print_terminal(f"DEBUG: Raw picked point: {picked_point}")
            
            point = list(picked_point)
            
            # Convert to slice coordinates to see where we're picking
            test_slice_coord = self.world_to_slice_coords(point, axis_info, spacing, v_exag)
            self.print_terminal(f"DEBUG: Slice coords = row:{test_slice_coord[0]}, col(Z):{test_slice_coord[1]}")
            
            # CRITICAL FIX: Validate Z value to prevent jumping to other reflectors
            # If we have previous waypoints, check if Z jumped too much
            MAX_Z_JUMP = 20  # Maximum allowed jump in slice column (Z) units between consecutive waypoints
            
            if len(self._autotrack_points) > 0:
                # Get previous waypoint's Z in slice coordinates
                prev_point = self._autotrack_points[-1]
                prev_slice_coord = self.world_to_slice_coords(prev_point, axis_info, spacing, v_exag)
                
                z_jump = abs(test_slice_coord[1] - prev_slice_coord[1])
                
                # Safety check - if picking still jumps too much, warn user
                # With pickable fix, this should rarely happen
                if z_jump > MAX_Z_JUMP:
                    self.print_terminal(f"WARNING: Z jumped {z_jump} samples (max allowed: {MAX_Z_JUMP})")
                    self.print_terminal(f"  Previous col(Z): {prev_slice_coord[1]}, Current col(Z): {test_slice_coord[1]}")
                    self.print_terminal(f"  This may indicate picking is not hitting the slice - try clicking directly on the seismic image")
                    # Still accept the point but warn - user can right-click to finish with good points
            
            # Store the point in DISPLAY coordinates
            self._autotrack_points.append(tuple(point))
            
            # Add visual marker using 2D billboard approach
            marker_name = f'autotrack_marker_{len(self._autotrack_points)}'
            
            # Create marker at the picked point with a SMALL offset towards camera
            # to avoid z-fighting with the seismic slice
            marker_point = list(point)
            small_offset = self._autotrack_marker_size * 0.5  # Very small offset relative to marker size
            
            if self.current_axis == 'Inline':
                marker_point[0] -= small_offset
            elif self.current_axis == 'Crossline':
                marker_point[1] -= small_offset
            elif self.current_axis == 'Z-slice':
                marker_point[2] += small_offset
            
            # Use add_point_labels for guaranteed visibility (2D overlay)
            # User requested to remove yellow blobs and lines, keep only red text
            waypoint_num = len(self._autotrack_points)
            self.plotter.add_point_labels(
                [marker_point],
                [f"  {waypoint_num}"],
                name=marker_name,
                show_points=False,    # Do not render points/markers at all
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
            
            # Preview line drawing removed as per user request (was causing VE alignment issues)
            # if len(self._autotrack_points) >= 2:
            #     self._show_path_preview(
            #         self._autotrack_points[-2],
            #         self._autotrack_points[-1]
            #     )
            
            # Force immediate render update
            self.plotter.update()
            self.plotter.render()
        
        def on_finish(point):
            # Right-click finishes the tracking
            if len(self._autotrack_points) < 2:
                self.print_terminal("Need at least 2 waypoints! Add more points or press ESC to cancel.")
                return
            
            self.print_terminal(f"Finishing with {len(self._autotrack_points)} waypoints...")
            self.plotter.untrack_click_position(side="left")
            self.plotter.untrack_click_position(side="right")
            
            # Run pathfinding between all consecutive waypoints
            self._run_autotrack_pathfinding_multi()
        
        # Track left clicks for point selection, right click to finish
        # Use track_click_position which picks the surface point at cursor location
        self.plotter.track_click_position(side="left", callback=on_point_picked)
        self.plotter.track_click_position(side="right", callback=on_finish)
    
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
            
            self.print_terminal(f"Running pathfinding between {len(waypoints)} waypoints...")
            
            # VERY TIGHT corridor width - critical to prevent jumping between horizons
            # A seismic reflector is only a few samples thick, so we use a very tight corridor
            # Maximum corridor of 5 pixels prevents jumping to other horizons
            MAX_CORRIDOR = 2   # Maximum corridor width in pixels/samples - VERY TIGHT
            MIN_CORRIDOR = 1   # Minimum corridor width
            
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
                
                # Use VERY tight corridor - only allow minimal deviation from direct path
                # The corridor is strictly capped to prevent jumping to other horizons
                vertical_diff = abs(start[1] - end[1])
                # Very strict: corridor is based on vertical diff but capped tightly
                segment_corridor = min(MAX_CORRIDOR, max(MIN_CORRIDOR, vertical_diff // 3 + MIN_CORRIDOR))
                
                self.print_terminal(f"Segment {i+1}: vertical diff={vertical_diff}, corridor={segment_corridor}")
                
                # Run A* pathfinding with TIGHT corridor constraint
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
            
            # Apply slice snapping (small offset to avoid z-fighting)
            # But do NOT unscale Z again - these are already in real coords
            offset = 1.0
            if self.current_axis == 'Inline':
                points_array[:, 0] = self.current_slice_position - offset
            elif self.current_axis == 'Crossline':
                points_array[:, 1] = self.current_slice_position - offset
            elif self.current_axis == 'Z-slice':
                points_array[:, 2] = self.current_slice_position + offset
            
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
            
            # Generate a distinct random color for this horizon
            import random
            horizon_color = [random.randint(50, 255), random.randint(50, 255), random.randint(50, 255)]
            # Ensure it's not too dark or too similar to white
            while sum(horizon_color) < 300 or sum(horizon_color) > 650:
                horizon_color = [random.randint(50, 255), random.randint(50, 255), random.randint(50, 255)]
            
            self.print_terminal(f"Generated random color: RGB{tuple(horizon_color)}")
            
            # Add to geological collection
            new_uid = self.parent.geol_coll.add_entity_from_dict(line_dict)
            self.print_terminal(f"Created auto-tracked horizon with {n_points} points, uid: {new_uid}")
            
            # Set the color for the line using proper UID lookup (uid is a column, not the index)
            try:
                mask = self.parent.geol_coll.df['uid'] == new_uid
                if mask.any():
                    self.parent.geol_coll.df.loc[mask, 'color_R'] = horizon_color[0]
                    self.parent.geol_coll.df.loc[mask, 'color_G'] = horizon_color[1]
                    self.parent.geol_coll.df.loc[mask, 'color_B'] = horizon_color[2]
                    self.print_terminal(f"Set color in df for {new_uid}")
            except Exception as color_err:
                self.print_terminal(f"Could not set color in df: {color_err}")
            
            # Also try to update the actor color directly if it exists
            try:
                actor_name = f"geol_coll_{new_uid}"
                if actor_name in self.plotter.renderer.actors:
                    actor = self.plotter.renderer.actors[actor_name]
                    actor.GetProperty().SetColor(horizon_color[0]/255.0, horizon_color[1]/255.0, horizon_color[2]/255.0)
                    self.print_terminal(f"Set actor color for {actor_name}")
                else:
                    # Try without prefix
                    if new_uid in self.plotter.renderer.actors:
                        actor = self.plotter.renderer.actors[new_uid]
                        actor.GetProperty().SetColor(horizon_color[0]/255.0, horizon_color[1]/255.0, horizon_color[2]/255.0)
                        self.print_terminal(f"Set actor color for {new_uid}")
            except Exception as actor_err:
                self.print_terminal(f"Could not set actor color: {actor_err}")
            
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
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QComboBox, QSpinBox, QLabel, QPushButton, QHBoxLayout, QRadioButton, QButtonGroup, QGroupBox
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Propagate Horizon")
        dialog.setMinimumWidth(400)
        layout = QVBoxLayout(dialog)
        
        # Horizon selection with clear information
        horizon_group = QGroupBox("Select Seed Horizon")
        horizon_layout = QVBoxLayout(horizon_group)
        
        horizon_layout.addWidget(QLabel("Choose the horizon to propagate:"))
        combo_horizon = QComboBox()
        for uid, name, slice_idx in all_lines:
            if slice_idx >= 0:
                display_text = f"{name}  [Slice {slice_idx}]"
            else:
                display_text = f"{name}  [Slice unknown]"
            combo_horizon.addItem(display_text, uid)
        combo_horizon.setMinimumWidth(350)
        horizon_layout.addWidget(combo_horizon)
        
        # Show info about selected horizon
        info_label = QLabel("")
        info_label.setStyleSheet("color: gray; font-style: italic;")
        horizon_layout.addWidget(info_label)
        
        def update_info():
            idx = combo_horizon.currentIndex()
            if idx >= 0:
                uid, name, slice_idx = all_lines[idx]
                if slice_idx >= 0:
                    info_label.setText(f"Will start propagation from slice {slice_idx}")
                else:
                    info_label.setText(f"Slice position unknown - will use current slice ({self.current_slice_index})")
        
        combo_horizon.currentIndexChanged.connect(update_info)
        update_info()
        
        layout.addWidget(horizon_group)
        
        # Direction selection
        direction_group_box = QGroupBox("Propagation Direction")
        direction_layout = QVBoxLayout(direction_group_box)
        direction_group = QButtonGroup(dialog)
        radio_forward = QRadioButton("Forward (increasing slice index)")
        radio_backward = QRadioButton("Backward (decreasing slice index)")
        radio_both = QRadioButton("Both directions")
        radio_forward.setChecked(True)
        direction_group.addButton(radio_forward, 0)
        direction_group.addButton(radio_backward, 1)
        direction_group.addButton(radio_both, 2)
        direction_layout.addWidget(radio_forward)
        direction_layout.addWidget(radio_backward)
        direction_layout.addWidget(radio_both)
        layout.addWidget(direction_group_box)
        
        # Number of slices
        slices_group = QGroupBox("Propagation Range")
        slices_layout = QVBoxLayout(slices_group)
        slices_layout.addWidget(QLabel("Number of slices to propagate:"))
        spin_slices = QSpinBox()
        spin_slices.setRange(1, 500)
        spin_slices.setValue(50)
        slices_layout.addWidget(spin_slices)
        layout.addWidget(slices_group)
        
        # Template parameters
        params_group = QGroupBox("Tracking Parameters")
        params_layout = QVBoxLayout(params_group)
        
        params_layout.addWidget(QLabel("Template half-height (samples):"))
        spin_template = QSpinBox()
        spin_template.setRange(3, 30)
        spin_template.setValue(7)
        spin_template.setToolTip("Vertical size of amplitude template for matching")
        params_layout.addWidget(spin_template)
        
        params_layout.addWidget(QLabel("Search window (samples):"))
        spin_search = QSpinBox()
        spin_search.setRange(5, 50)
        spin_search.setValue(15)
        spin_search.setToolTip("Vertical search range on each new slice")
        params_layout.addWidget(spin_search)
        
        # Smoothing parameter - helps focus on prominent reflectors
        params_layout.addWidget(QLabel("Smoothing sigma (0=none):"))
        spin_smooth = QSpinBox()
        spin_smooth.setRange(0, 10)
        spin_smooth.setValue(2)
        spin_smooth.setToolTip("Gaussian smoothing to suppress small edges and focus on prominent reflectors")
        params_layout.addWidget(spin_smooth)
        layout.addWidget(params_group)
        
        # Buttons
        btn_layout = QHBoxLayout()
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
        template_half = spin_template.value()
        search_window = spin_search.value()
        smooth_sigma = spin_smooth.value()
        
        self.print_terminal(f"=== Propagating Horizon ===")
        self.print_terminal(f"Seed horizon: {seed_name} (slice {seed_slice_idx})")
        self.print_terminal(f"Direction: {['Forward', 'Backward', 'Both'][direction]}")
        self.print_terminal(f"Slices: {num_slices}, Template: ±{template_half}, Search: ±{search_window}, Smooth: {smooth_sigma}")
        
        # Run propagation with the seed slice index
        try:
            self._run_horizon_propagation(
                seed_uid=seed_uid,
                direction=direction,
                num_slices=num_slices,
                template_half=template_half,
                search_window=search_window,
                smooth_sigma=smooth_sigma,
                seed_slice_index=seed_slice_idx
            )
        except Exception as e:
            self.print_terminal(f"Error during propagation: {e}")
            import traceback
            self.print_terminal(traceback.format_exc())
        
        self.enable_actions()
    
    def _run_horizon_propagation(self, seed_uid, direction, num_slices, template_half, search_window, smooth_sigma=2, seed_slice_index=None):
        """
        Execute the horizon propagation using template matching.
        Creates a SINGLE multipart PolyLine entity containing all propagated segments.
        This is much more efficient than creating separate entities for each slice.
        
        Args:
            seed_uid: UID of the seed horizon line
            direction: 0=forward, 1=backward, 2=both
            num_slices: Number of slices to propagate
            template_half: Half-height of the template window (samples)
            search_window: Search window size (samples)
            smooth_sigma: Gaussian smoothing sigma (0=no smoothing)
        """
        from scipy import signal
        from scipy.ndimage import gaussian_filter1d
        from vtk import vtkPoints, vtkCellArray, vtkFloatArray, vtkIntArray
        import random
        
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
        
        # Apply Gaussian smoothing along the vertical (Z) axis to suppress small edges
        # This helps focus on prominent/continuous reflectors
        if smooth_sigma > 0:
            self.print_terminal(f"Applying Gaussian smoothing (sigma={smooth_sigma}) to enhance prominent reflectors...")
            # Smooth along the Z axis (axis 2 for all slice types)
            data_3d = gaussian_filter1d(data_3d, sigma=smooth_sigma, axis=2)
        
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
        
        # Convert seed points to slice coordinates
        # Seed points are in world coordinates, need to convert to indices
        seed_indices = []
        for pt in seed_points:
            if self.current_axis == 'Inline':
                row = int((pt[1] - bounds[2]) / spacing[1]) if spacing[1] > 0 else 0
                col = int((pt[2] - bounds[4]) / spacing[2]) if spacing[2] > 0 else 0
            elif self.current_axis == 'Crossline':
                row = int((pt[0] - bounds[0]) / spacing[0]) if spacing[0] > 0 else 0
                col = int((pt[2] - bounds[4]) / spacing[2]) if spacing[2] > 0 else 0
            else:  # Z-slice
                row = int((pt[0] - bounds[0]) / spacing[0]) if spacing[0] > 0 else 0
                col = int((pt[1] - bounds[2]) / spacing[1]) if spacing[1] > 0 else 0
            seed_indices.append((row, col))
        
        # Subsample if too many points (for speed)
        if len(seed_indices) > 200:
            step = len(seed_indices) // 200
            seed_indices = seed_indices[::step]
            self.print_terminal(f"Subsampled seed to {len(seed_indices)} points")
        
        # Get seed slice data and extract templates
        if self.current_axis == 'Inline':
            seed_slice = data_3d[current_idx, :, :]
        elif self.current_axis == 'Crossline':
            seed_slice = data_3d[:, current_idx, :]
        else:
            seed_slice = data_3d[:, :, current_idx]
        
        # Extract templates from seed horizon
        templates = []
        template_positions = []
        n_rows, n_cols = seed_slice.shape
        
        for row, col in seed_indices:
            # Ensure within bounds
            row = int(np.clip(row, 0, n_rows - 1))
            col = int(np.clip(col, template_half, n_cols - template_half - 1))
            
            # Extract vertical template
            template = seed_slice[row, col - template_half:col + template_half + 1].copy()
            if len(template) == 2 * template_half + 1:
                templates.append(template)
                template_positions.append((row, col))
        
        self.print_terminal(f"Extracted {len(templates)} templates")
        
        if len(templates) == 0:
            self.print_terminal("Could not extract any templates!")
            return
        
        # Generate a random color for this propagated horizon set
        horizon_color = [random.randint(50, 255), random.randint(50, 255), random.randint(50, 255)]
        while sum(horizon_color) < 300 or sum(horizon_color) > 650:
            horizon_color = [random.randint(50, 255), random.randint(50, 255), random.randint(50, 255)]
        
        # Track current positions (will be updated slice by slice)
        current_positions = list(template_positions)
        
        # ============ MULTIPART LINE STORAGE ============
        # Instead of creating one entity per slice, we collect all parts into a single multipart PolyLine
        all_points = []  # List of all points across all slices
        all_lines = []   # Line connectivity array for VTK
        point_slice_indices = []  # Slice index for each point (for filtering)
        cell_slice_indices = []   # Slice index for each cell/line segment (for filtering)
        slice_to_point_range = {}  # Maps slice_index -> (start_point_idx, end_point_idx)
        current_point_offset = 0
        successful_slices = 0
        
        self.print_terminal(f"Will propagate to {len(slices_to_track)} slices: {slices_to_track[:5]}...")
        
        self._is_propagating = True  # Enable batch mode
        try:
            for slice_loop_idx, slice_idx in enumerate(slices_to_track):
                try:
                    # Get slice data
                    if self.current_axis == 'Inline':
                        new_slice = data_3d[slice_idx, :, :]
                    elif self.current_axis == 'Crossline':
                        new_slice = data_3d[:, slice_idx, :]
                    else:
                        new_slice = data_3d[:, :, slice_idx]
                    
                    # Match each template on the new slice
                    new_positions = []
                    
                    for i, (template, (row, expected_col)) in enumerate(zip(templates, current_positions)):
                        # Define search range
                        search_start = max(template_half, expected_col - search_window)
                        search_end = min(n_cols - template_half - 1, expected_col + search_window)
                        
                        if search_start >= search_end:
                            new_positions.append((row, expected_col))
                            continue
                        
                        # Extract search region
                        search_region = new_slice[row, search_start - template_half:search_end + template_half + 1]
                        
                        if len(search_region) < len(template):
                             new_positions.append((row, expected_col))
                             continue
                        
                        # Cross-correlation
                        try:
                            correlation = signal.correlate(search_region, template, mode='valid')
                            best_offset = np.argmax(correlation)
                            best_col = search_start + best_offset
                            new_positions.append((row, best_col))
                        except:
                            new_positions.append((row, expected_col))
                    
                    # ============ SMOOTHING ============
                    rows_arr = np.array([p[0] for p in new_positions])
                    cols_arr = np.array([p[1] for p in new_positions], dtype=np.float64)
                    
                    from scipy.ndimage import median_filter
                    cols_smoothed = median_filter(cols_arr, size=5)
                    cols_smoothed = gaussian_filter1d(cols_smoothed, sigma=3)
                    
                    max_jump = 2
                    for i in range(1, len(cols_smoothed)):
                        diff = cols_smoothed[i] - cols_smoothed[i-1]
                        if abs(diff) > max_jump:
                            cols_smoothed[i] = cols_smoothed[i-1] + np.sign(diff) * max_jump
                    
                    new_positions = [(int(rows_arr[i]), int(round(cols_smoothed[i]))) for i in range(len(rows_arr))]
                    
                    # Convert to world coordinates
                    world_points = []
                    for row, col in new_positions:
                        if self.current_axis == 'Inline':
                            x = bounds[0] + slice_idx * spacing[0]
                            y = bounds[2] + row * spacing[1]
                            z = bounds[4] + col * spacing[2]
                        elif self.current_axis == 'Crossline':
                            x = bounds[0] + row * spacing[0]
                            y = bounds[2] + slice_idx * spacing[1]
                            z = bounds[4] + col * spacing[2]
                        else:
                            x = bounds[0] + row * spacing[0]
                            y = bounds[2] + col * spacing[1]
                            z = bounds[4] + slice_idx * spacing[2]
                        world_points.append((x, y, z))
                    
                    world_points.sort(key=lambda p: p[0] if self.current_axis != 'Inline' else p[1])
                    
                    # Check points
                    if len(world_points) < 2:
                        self.print_terminal(f"  WARNING: Slice {slice_idx} produced insufficient points: {len(world_points)}")
                        current_positions = new_positions
                        continue
                    
                    # ============ ADD TO MULTIPART STRUCTURE ============
                    n_pts_this_slice = len(world_points)
                    start_pt_idx = current_point_offset
                    
                    # Add points
                    all_points.extend(world_points)
                    
                    # Add slice index for each point (for point data array)
                    point_slice_indices.extend([slice_idx] * n_pts_this_slice)
                    
                    # Build line connectivity for this slice's polyline
                    # VTK format: [n_pts, pt0, pt1, pt2, ..., ptn-1]
                    line_indices = list(range(start_pt_idx, start_pt_idx + n_pts_this_slice))
                    all_lines.append(n_pts_this_slice)
                    all_lines.extend(line_indices)
                    
                    # Add slice index for this cell/line (for cell data array)
                    cell_slice_indices.append(slice_idx)
                    
                    # Track point range for this slice
                    slice_to_point_range[slice_idx] = (start_pt_idx, start_pt_idx + n_pts_this_slice - 1)
                    
                    current_point_offset += n_pts_this_slice
                    successful_slices += 1
                    
                    # Update current positions
                    current_positions = new_positions
                    
                    # Progress log
                    if (slice_loop_idx + 1) % 10 == 0:
                        self.print_terminal(f"  Processed slice {slice_idx}. Total parts: {successful_slices}")
                        
                except Exception as inner_e:
                    self.print_terminal(f"ERROR processing slice {slice_idx}: {inner_e}")
                    import traceback
                    self.print_terminal(traceback.format_exc())
                    if not new_positions:
                        new_positions = current_positions
                    current_positions = new_positions

            # ============ CREATE SINGLE MULTIPART POLYLINE ENTITY ============
            if successful_slices > 0 and len(all_points) >= 2:
                self.print_terminal(f"Creating multipart horizon with {successful_slices} parts, {len(all_points)} total points...")
                
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
                
                # Create entity dictionary
                line_dict = deepcopy(self.parent.geol_coll.entity_dict)
                line_dict["name"] = f"horizon_{current_idx}_multipart"
                line_dict["topology"] = "PolyLine"
                line_dict["x_section"] = ""
                line_dict["vtk_obj"] = multipart_line
                
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
                
                # Set color
                try:
                    mask = self.parent.geol_coll.df['uid'] == new_uid
                    if mask.any():
                        self.parent.geol_coll.df.loc[mask, 'color_R'] = horizon_color[0]
                        self.parent.geol_coll.df.loc[mask, 'color_G'] = horizon_color[1]
                        self.parent.geol_coll.df.loc[mask, 'color_B'] = horizon_color[2]
                except:
                    pass
                
                self.print_terminal(f"=== Propagation Complete ===")
                self.print_terminal(f"Created multipart horizon: {line_dict['name']}")
                self.print_terminal(f"Contains {successful_slices} line segments across slices")
                self.print_terminal(f"Slice range: {min(cell_slice_indices)} to {max(cell_slice_indices)}")
                self.print_terminal(f"Color: RGB{tuple(horizon_color)}")
                
                # Add actor to scene and update visibility
                self.show_actor_with_property(uid=new_uid, coll_name='geol_coll', visible=True)
                self.update_multipart_horizon_visibility(new_uid)
            else:
                self.print_terminal("No valid line segments were created during propagation!")

        finally:
            self._is_propagating = False  # Disable batch mode
            self.plotter.render()
    
    # ==================== End Auto Propagation Methods ====================

    def initialize_menu_tools(self):
        super().initialize_menu_tools()
        # Add interpretation-specific draw line action
        self.drawInterpLineButton = QAction("Draw Interpretation Line", self)
        self.drawInterpLineButton.triggered.connect(self.draw_interpretation_line)
        self.menuCreate.insertAction(self.menuCreate.actions()[0], self.drawInterpLineButton)
        
        # Add semi-auto tracking action
        self.semiAutoTrackButton = QAction("Semi-Auto Track Horizon", self)
        self.semiAutoTrackButton.triggered.connect(self.draw_semi_auto_line)
        self.menuCreate.insertAction(self.menuCreate.actions()[1], self.semiAutoTrackButton)
        
        # Add propagate horizon action
        self.propagateHorizonButton = QAction("Propagate Horizon (Auto-Track 3D)", self)
        self.propagateHorizonButton.triggered.connect(self.propagate_horizon)
        self.menuCreate.insertAction(self.menuCreate.actions()[2], self.propagateHorizonButton)
        
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
    
    def on_entities_removed(self, uids):
        """Called when entities are removed from any collection. Clean up interpretation_lines and multipart_horizons."""
        if not hasattr(self, 'interpretation_lines'):
            self.interpretation_lines = {}
        
        for uid in uids:
            # Clean up single-line interpretation tracking
            if uid in self.interpretation_lines:
                # Check if the entity is actually removed from geol_coll
                try:
                    exists = (self.parent.geol_coll.df["uid"] == uid).any()
                    if not exists:
                        self.unregister_interpretation_line(uid)
                        # Invalidate actor cache for this uid
                        self._invalidate_actor_cache(uid)
                        self.print_terminal(f"Removed {uid[:8]}... from interpretation lines tracking")
                except:
                    # If we can't check, assume it's removed
                    self.unregister_interpretation_line(uid)
                    self._invalidate_actor_cache(uid)
                    self.print_terminal(f"Removed {uid[:8]}... from interpretation lines tracking")
            
            # Clean up multipart horizon tracking
            if hasattr(self, 'multipart_horizons') and uid in self.multipart_horizons:
                try:
                    exists = (self.parent.geol_coll.df["uid"] == uid).any()
                    if not exists:
                        del self.multipart_horizons[uid]
                        # Remove any filtered slice actors
                        actor_name = f"multipart_slice_{uid}"
                        if actor_name in self.plotter.renderer.actors:
                            self.plotter.remove_actor(actor_name)
                        self._invalidate_actor_cache(uid)
                        self.print_terminal(f"Removed multipart horizon {uid[:8]}... from tracking")
                except:
                    del self.multipart_horizons[uid]
                    actor_name = f"multipart_slice_{uid}"
                    if actor_name in self.plotter.renderer.actors:
                        self.plotter.remove_actor(actor_name)
                    self._invalidate_actor_cache(uid)
                    self.print_terminal(f"Removed multipart horizon {uid[:8]}... from tracking")
    
    def on_colormap_changed(self, property_name):
        """Called when colormap is changed in the legend manager."""
        if property_name == 'intensity':
            self.update_slice_colormap()

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
