"""view_interpretation.py
PZero© Andrea Bistacchi"""

# PySide6 imports
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QComboBox, QSlider, QSpinBox, QVBoxLayout
)
from PySide6.QtCore import Qt

# VTK/PyVista imports
import pyvista as pv
import numpy as np
from copy import deepcopy

# PZero imports
from .view_map import ViewMap
from ..entities_factory import Seismics, PolyLine
from ..helpers.helper_dialogs import multiple_input_dialog
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
        
        # Setup specific UI controls
        self.setup_controls()
        
        # Override default view to something neutral initially
        self.plotter.view_xy()
        
        # Use trackball style instead of image style to allow proper 3D views
        # Image style forces XY view which breaks Inline/Crossline views
        # self.plotter.enable_trackball_style()
        
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
        
    def setup_controls(self):
        """Add controls for slicing to the layout"""
        # We need to find where to add these controls. 
        # Typically ViewVTK has a main layout. We can add a toolbar-like widget at the top.
        
        control_widget = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        control_widget.setLayout(layout)
        
        # Seismic Volume Selector
        layout.addWidget(QLabel("Volume:"))
        self.combo_volume = QComboBox()
        self.combo_volume.currentIndexChanged.connect(self.on_volume_changed)
        layout.addWidget(self.combo_volume)
        
        # Slice Type Selector
        layout.addWidget(QLabel("View:"))
        self.combo_view = QComboBox()
        self.combo_view.addItems(["Inline", "Crossline", "Z-slice"])
        self.combo_view.currentTextChanged.connect(self.on_view_type_changed)
        layout.addWidget(self.combo_view)
        
        # Slice Index Slider
        layout.addWidget(QLabel("Slice:"))
        self.slider_slice = QSlider(Qt.Horizontal)
        self.slider_slice.valueChanged.connect(self.on_slider_changed)
        layout.addWidget(self.slider_slice)
        
        # Slice Index SpinBox
        self.spin_slice = QSpinBox()
        self.spin_slice.valueChanged.connect(self.on_spin_changed)
        layout.addWidget(self.spin_slice)
        
        # Refresh button to manually refresh volume list
        from PySide6.QtWidgets import QPushButton
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh_volume_list)
        layout.addWidget(self.refresh_button)
        
        # Add to main layout
        # Assuming self.layout() exists from parent QMainWindow or similar, 
        # but ViewVTK setup might be different. 
        # ViewVTK inherits QMainWindow. centralWidget is likely the QVTKRenderWindowInteractor or a container.
        # Let's check if we can insert it into a toolbar or add a dock widget.
        # For simplicity, let's create a DockWidget for controls or add to a layout if central widget is a container.
        # In ViewVTK, self.frame is the central widget often.
        
        # Using a QDockWidget for controls to ensure it doesn't interfere with the render window
        from PySide6.QtWidgets import QDockWidget
        self.controls_dock = QDockWidget("Interpretation Controls", self)
        self.controls_dock.setWidget(control_widget)
        self.controls_dock.setAllowedAreas(Qt.TopDockWidgetArea | Qt.BottomDockWidgetArea)
        self.addDockWidget(Qt.TopDockWidgetArea, self.controls_dock)
        
    def on_entities_added(self, uids, collection):
        """Called when new entities are added to any collection"""
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
            self._camera_initialized = False  # Reset camera on volume change
            self.scalar_range = None  # Reset scalar range
            # Clear cached seismic data
            if hasattr(self, '_cached_seismic'):
                del self._cached_seismic
            self.update_slice_limits()
            self.update_camera_orientation()
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
        
        # Fallback / Initial set (before slice is fully loaded)
        if self.current_axis == 'Inline': 
            self.plotter.view_yz()
        elif self.current_axis == 'Crossline':
            self.plotter.view_xz() 
        elif self.current_axis == 'Z-slice':
            self.plotter.view_xy()
            
        self.plotter.reset_camera()

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
            # Calculate percentile-based scalar range for better contrast
            if 'intensity' in self._cached_seismic.array_names:
                data = self._cached_seismic['intensity']
                self.scalar_range = (np.percentile(data, 1), np.percentile(data, 99))
                self.print_terminal(f"Scalar range (percentile): {self.scalar_range}")
        
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

        except Exception as e:
            self.print_terminal(f"Error updating slice: {e}")
            import traceback
            self.print_terminal(traceback.format_exc())
        
        self.plotter.render()

    def update_camera_to_slice(self, center, bounds, scale):
        """
        Enforce a 2D-like view locked to the current axis, fitted to the slice bounds, 
        respecting Vertical Exaggeration.
        """
        # Lock rotation by using Image style (Left=Pan, Right=Zoom)
        # We must call specific view setup AFTER this because it might reset to XY
        self.plotter.enable_image_style()
        self.plotter.enable_parallel_projection()
        
        camera = self.plotter.camera
        
        # Calculate fitting dimensions with Scale (VE) applied
        # bounds is [xmin, xmax, ymin, ymax, zmin, zmax] (unscaled)
        # scale is [sx, sy, sz]
        
        # Determine width/height of the slice in WORLD (scaled) units
        width = 0.0
        height = 0.0
        
        if self.current_axis == 'Inline':
            # YZ plane
            width = abs(bounds[3] - bounds[2]) * scale[1]
            height = abs(bounds[5] - bounds[4]) * scale[2]
            
            # Position: Look down X axis
            camera.position = (center[0] + max(width, height) * 2, center[1], center[2])
            camera.focal_point = center
            camera.view_up = (0, 0, 1)
            
        elif self.current_axis == 'Crossline':
            # XZ plane
            width = abs(bounds[1] - bounds[0]) * scale[0]
            height = abs(bounds[5] - bounds[4]) * scale[2]
            
            # Position: Look down Y axis
            camera.position = (center[0], center[1] + max(width, height) * 2, center[2])
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
            self.scalar_range = None  # Reset scalar range
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
                
                # Now snap the points to the current slice plane
                points = np.array(input_dict["vtk_obj"].GetPoints().GetData())
                snapped_points = self.snap_points_to_slice(points)
                input_dict["vtk_obj"].points = snapped_points
                
                # Add to geological collection - this emits signals that other views listen to
                new_uid = self.parent.geol_coll.add_entity_from_dict(input_dict)
                self.print_terminal(f"Created interpretation line with {len(snapped_points)} points, uid: {new_uid}")
            
            # Remove the temporary picking plane
            if 'picking_plane' in self.plotter.renderer.actors:
                self.plotter.remove_actor('picking_plane')
                    
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
        
        # Create a transparent picking plane at the current slice position
        # This ensures the tracer draws directly on the slice plane
        self.add_picking_plane()
        
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
        
        # Create a plane mesh at the slice position
        if self.current_axis == 'Inline':
            # YZ plane at current X position
            plane = pv.Plane(
                center=(self.current_slice_position, (bounds[2]+bounds[3])/2, (bounds[4]+bounds[5])/2),
                direction=(1, 0, 0),
                i_size=bounds[3] - bounds[2],  # Y extent
                j_size=abs(bounds[5] - bounds[4]),  # Z extent
                i_resolution=1,
                j_resolution=1
            )
        elif self.current_axis == 'Crossline':
            # XZ plane at current Y position  
            plane = pv.Plane(
                center=((bounds[0]+bounds[1])/2, self.current_slice_position, (bounds[4]+bounds[5])/2),
                direction=(0, 1, 0),
                i_size=bounds[1] - bounds[0],  # X extent
                j_size=abs(bounds[5] - bounds[4]),  # Z extent
                i_resolution=1,
                j_resolution=1
            )
        elif self.current_axis == 'Z-slice':
            # XY plane at current Z position
            plane = pv.Plane(
                center=((bounds[0]+bounds[1])/2, (bounds[2]+bounds[3])/2, self.current_slice_position),
                direction=(0, 0, 1),
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

    def snap_points_to_slice(self, points):
        """Snap points to the current slice plane based on the current axis and slice position.
        Also accounts for vertical exaggeration - the drawn points are in exaggerated coordinates,
        so we need to unscale Z before storing."""
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
        
        # If vertical exaggeration is applied, the Z coordinates of drawn points are scaled
        # We need to unscale them to get real coordinates
        if v_exag != 1.0:
            snapped[:, 2] = snapped[:, 2] / v_exag
        
        # Now snap to the current slice position (in real coordinates)
        if self.current_axis == 'Inline':
            # For inline view (YZ plane), set X to the slice position
            snapped[:, 0] = self.current_slice_position
        elif self.current_axis == 'Crossline':
            # For crossline view (XZ plane), set Y to the slice position
            snapped[:, 1] = self.current_slice_position
        elif self.current_axis == 'Z-slice':
            # For Z-slice view (XY plane), set Z to the slice position
            snapped[:, 2] = self.current_slice_position
            
        return snapped

    def initialize_menu_tools(self):
        super().initialize_menu_tools()
        # Add interpretation-specific draw line action
        self.drawInterpLineButton = QAction("Draw Interpretation Line", self)
        self.drawInterpLineButton.triggered.connect(self.draw_interpretation_line)
        self.menuCreate.insertAction(self.menuCreate.actions()[0], self.drawInterpLineButton)
        
        # Connect our custom handler for additional processing (volume list refresh)
        try:
            self.parent.signals.entities_added.connect(self.on_entities_added)
        except Exception as e:
            self.print_terminal(f"Warning: Could not connect entities_added signal: {e}")
        
        # Connect to colormap change signal to update slice colormap
        try:
            self.parent.signals.prop_legend_cmap_modified.connect(self.on_colormap_changed)
        except Exception as e:
            self.print_terminal(f"Warning: Could not connect prop_legend_cmap_modified signal: {e}")
    
    def on_colormap_changed(self, property_name):
        """Called when colormap is changed in the legend manager."""
        if property_name == 'intensity':
            self.update_slice_colormap()

    def show_qt_canvas(self):
        """Show the Qt Window and refresh the volume list."""
        super().show_qt_canvas()
        # Clear any full seismic volume actors that might have been added
        self.clear_seismic_volumes()
        # Refresh volume list to detect any seismics (combo_volume now exists)
        self.refresh_volume_list()
    
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
