"""boundary_collection.py
PZero© Andrea Bistacchi"""

from copy import deepcopy

from uuid import uuid4 as uuid_uuid4

from vtkmodules.vtkCommonDataModel import vtkDataObject
from vtk import vtkPoints

from numpy import array as np_array
from numpy import ndarray as np_ndarray
from numpy import float32 as np_float32
from numpy import arctan2 as np_arctan2
from numpy import cos as np_cos
from numpy import sin as np_sin
from numpy import linalg as np_linalg
from numpy import concatenate as np_concatenate
from numpy import mean as np_mean
from numpy import min as np_min
from numpy import max as np_max
from numpy import dot as np_dot
from numpy import full as np_full
from numpy import tile as np_tile

from scipy.spatial import ConvexHull

from pandas import DataFrame as pd_DataFrame
from pandas import concat as pd_concat

from pyvista import Line as pv_Line
from pyvista import lines_from_points as pv_lines_from_points

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QGridLayout, QLabel, QLineEdit, QCheckBox,
                               QPushButton, QVBoxLayout, QSlider, QSpinBox,
                               QGroupBox, QComboBox, QApplication)

from pzero.entities_factory import PolyLine, TriSurf
from pzero.helpers.helper_dialogs import general_input_dialog, message_dialog
from .AbstractCollection import BaseCollection


def compute_obb_boundary(parent):
    """Compute true minimum area oriented bounding box from all data using convex hull and rotating axes."""
    
    # Collect all points from all collections
    all_points = []
    
    # helper to get points from collection
    def get_points(coll):
        pts = []
        try:
            for uid in coll.get_uids:
                vtk_obj = coll.get_uid_vtk_obj(uid)
                if hasattr(vtk_obj, 'points') and isinstance(vtk_obj.points, np_ndarray):
                    pts.append(vtk_obj.points)
        except:
            pass
        return pts

    all_points.extend(get_points(parent.geol_coll))
    all_points.extend(get_points(parent.fluid_coll))
    all_points.extend(get_points(parent.backgrnd_coll))
    all_points.extend(get_points(parent.well_coll))
    all_points.extend(get_points(parent.dom_coll))
    
    if not all_points:
        return None, None, None
        
    # Concatenate all points
    combined_points = np_concatenate(all_points, axis=0)
    
    # Use only X,Y coordinates for 2D OBB (map view)
    xy_points = combined_points[:, :2]
    
    # Compute Convex Hull
    try:
        hull = ConvexHull(xy_points)
        hull_points = xy_points[hull.vertices]
    except:
        # Fallback to AABB if hull fails (e.g. collinear points)
        min_x, min_y = np_min(xy_points, axis=0)
        max_x, max_y = np_max(xy_points, axis=0)
        corners = np_array([[min_x, min_y], [max_x, min_y], [max_x, max_y], [min_x, max_y]])
        return corners, np_max(combined_points[:, 2]), np_min(combined_points[:, 2])

    # Minimum Area Bounding Box (MABB) algorithm
    min_area = float('inf')
    best_corners = None
    best_angle = 0.0
    best_translation = np_array([0.0, 0.0])
    
    for i in range(len(hull_points)):
        # Edge between hull_points[i] and hull_points[(i+1)%len(hull_points)]
        p1 = hull_points[i]
        p2 = hull_points[(i+1) % len(hull_points)]
        edge = p2 - p1
        
        # Angle of the edge
        angle = np_arctan2(edge[1], edge[0])
        
        # Rotation matrix to align edge with X-axis
        rotation = np_array([
            [np_cos(angle), np_sin(angle)],
            [-np_sin(angle), np_cos(angle)]
        ])
        
        # Rotate points
        rotated_points = np_dot(xy_points, rotation.T)
        
        # Axis-aligned bounding box in rotated space
        min_r = np_min(rotated_points, axis=0)
        max_r = np_max(rotated_points, axis=0)
        
        # Add 10% margin
        range_r = max_r - min_r
        margin = range_r * 0.1
        min_r_ext = min_r - margin
        max_r_ext = max_r + margin
        
        area = (max_r_ext[0] - min_r_ext[0]) * (max_r_ext[1] - min_r_ext[1])
        
        if area < min_area:
            min_area = area
            best_angle = angle
            # Translation vector is the min corner in rotated (local) space
            best_translation = min_r_ext
            # Corners in rotated space
            corners_r = np_array([
                [min_r_ext[0], min_r_ext[1]],
                [max_r_ext[0], min_r_ext[1]],
                [max_r_ext[0], max_r_ext[1]],
                [min_r_ext[0], max_r_ext[1]]
            ])
            # Rotate back to original space
            best_corners = np_dot(corners_r, rotation)
            # Store the LOCAL-space translation (min corner in rotated space)
            # This is needed because transformation is: rotate first, then translate
            best_local_translation = min_r_ext.copy()
    
    # Return the local-space translation (min_r_ext) - NOT the real-world corner
    # The transformation order is: rotate -> translate (forward), translate -> inverse rotate (inverse)
            
    # Get Z extent from all points
    z_min = np_min(combined_points[:, 2])
    z_max = np_max(combined_points[:, 2])
    z_margin = (z_max - z_min) * 0.1
    z_bottom = z_min - z_margin
    z_top = z_max + z_margin
    
    return best_corners, z_top, z_bottom, best_angle, best_local_translation

def boundary_from_obb(self):
    """Create a new Boundary from OBB (Oriented Bounding Box) analysis of all data"""
    boundary_dict = deepcopy(self.parent.boundary_coll.entity_dict)
    
    # Freeze QT interface
    self.disable_actions()
    
    # Compute initial OBB values
    obb_result = compute_obb_boundary(self.parent)
    
    if obb_result[0] is None:
        message_dialog(title="OBB Boundary Error", message="No data found to compute OBB boundary.")
        self.enable_actions()
        return
    
    # Extract OBB results
    corners_xy, top, bottom, obb_angle, obb_translation = obb_result
    
    # Create enhanced dialog with OBB compute button and size controls
    # Store original OBB dimensions for scaling
    original_corners = corners_xy.copy()
    
    # Calculate original dimensions for scaling reference
    obb_width = np_max(corners_xy[:, 0]) - np_min(corners_xy[:, 0])
    obb_height = np_max(corners_xy[:, 1]) - np_min(corners_xy[:, 1])
    
    # Create custom dialog widget
    dialog = QWidget()
    dialog.setWindowTitle("New Boundary from OBB - Interactive Sizing")
    dialog.resize(500, 400)
    dialog.setWindowModality(Qt.ApplicationModal)
    
    layout = QVBoxLayout(dialog)
    
    # Add warning label
    warning_label = QLabel("Build new Boundary using OBB (Oriented Bounding Box) analysis of all data.\nMinimum volume oriented boundary box will be created based on covariance matrix.\nUse sliders to adjust size.")
    layout.addWidget(warning_label)
    
    # Create form layout for basic inputs
    basic_group = QGroupBox("Basic Settings")
    basic_layout = QGridLayout(basic_group)
    
    # Boundary selection dropdown
    boundary_combo = QComboBox()
    boundary_combo.addItem("Create New Boundary", "new")
    
    # Add existing boundaries to dropdown
    existing_boundaries = self.parent.boundary_coll.get_names
    for boundary_name in existing_boundaries:
        boundary_uid = None
        for uid in self.parent.boundary_coll.get_uids:
            if self.parent.boundary_coll.get_uid_name(uid) == boundary_name:
                boundary_uid = uid
                break
        if boundary_uid:
            boundary_combo.addItem(f"Update: {boundary_name}", boundary_uid)
    
    # Input fields
    name_edit = QLineEdit("obb_boundary")
    top_edit = QLineEdit(f"{top:.2f}")
    bottom_edit = QLineEdit(f"{bottom:.2f}")
    volume_checkbox = QCheckBox()
    volume_checkbox.setChecked(True)
    
    # Function to handle boundary selection change
    def on_boundary_selection_changed():
        selected_data = boundary_combo.currentData()
        if selected_data == "new":
            # New boundary mode
            name_edit.setEnabled(True)
            name_edit.setText("obb_boundary")
            top_edit.setText(f"{top:.2f}")
            bottom_edit.setText(f"{bottom:.2f}")
            volume_checkbox.setChecked(True)
        else:
            # Update existing boundary mode
            existing_uid = selected_data
            existing_name = self.parent.boundary_coll.get_uid_name(existing_uid)
            name_edit.setEnabled(False)
            name_edit.setText(existing_name)
            
            # Get existing boundary properties
            existing_vtk = self.parent.boundary_coll.get_uid_vtk_obj(existing_uid)
            if hasattr(existing_vtk, 'points') and existing_vtk.points is not None:
                if len(existing_vtk.points) > 0:
                    existing_z_values = existing_vtk.points[:, 2]
                    if len(existing_z_values) > 0:
                        z_min = np_min(existing_z_values)
                        z_max = np_max(existing_z_values)
                        if z_min != z_max:
                            top_edit.setText(f"{z_max:.2f}")
                            bottom_edit.setText(f"{z_min:.2f}")
                            volume_checkbox.setChecked(True)
                        else:
                            # It's a 2D boundary
                            volume_checkbox.setChecked(False)
    
    boundary_combo.currentTextChanged.connect(on_boundary_selection_changed)
    
    # Add to basic form
    basic_layout.addWidget(QLabel("Boundary:"), 0, 0)
    basic_layout.addWidget(boundary_combo, 0, 1)
    basic_layout.addWidget(QLabel("Boundary name:"), 1, 0)
    basic_layout.addWidget(name_edit, 1, 1)
    basic_layout.addWidget(QLabel("Top Z:"), 2, 0)
    basic_layout.addWidget(top_edit, 2, 1)
    basic_layout.addWidget(QLabel("Bottom Z:"), 3, 0)
    basic_layout.addWidget(bottom_edit, 3, 1)
    basic_layout.addWidget(QLabel("Create volume:"), 4, 0)
    basic_layout.addWidget(volume_checkbox, 4, 1)
    
    layout.addWidget(basic_group)
    
    # Create size control group
    size_group = QGroupBox("Size Controls")
    size_layout = QGridLayout(size_group)
    
    # Width control (along first principal component)
    width_label = QLabel("Width Scale:")
    width_slider = QSlider(Qt.Horizontal)
    width_slider.setMinimum(10)  # 10% of original
    width_slider.setMaximum(500)  # 500% of original
    width_slider.setValue(100)  # 100% = original size
    width_spinbox = QSpinBox()
    width_spinbox.setMinimum(10)
    width_spinbox.setMaximum(500)
    width_spinbox.setValue(100)
    width_spinbox.setSuffix("%")
    
    # Height control (along second principal component)
    height_label = QLabel("Height Scale:")
    height_slider = QSlider(Qt.Horizontal)
    height_slider.setMinimum(10)  # 10% of original
    height_slider.setMaximum(500)  # 500% of original
    height_slider.setValue(100)  # 100% = original size
    height_spinbox = QSpinBox()
    height_spinbox.setMinimum(10)
    height_spinbox.setMaximum(500)
    height_spinbox.setValue(100)
    height_spinbox.setSuffix("%")
    
    # Connect sliders and spinboxes
    width_slider.valueChanged.connect(width_spinbox.setValue)
    width_spinbox.valueChanged.connect(width_slider.setValue)
    height_slider.valueChanged.connect(height_spinbox.setValue)
    height_spinbox.valueChanged.connect(height_slider.setValue)
    
    # Add to size layout
    size_layout.addWidget(width_label, 0, 0)
    size_layout.addWidget(width_slider, 0, 1)
    size_layout.addWidget(width_spinbox, 0, 2)
    size_layout.addWidget(height_label, 1, 0)
    size_layout.addWidget(height_slider, 1, 1)
    size_layout.addWidget(height_spinbox, 1, 2)
    
    layout.addWidget(size_group)
    
    # Function to update corners based on slider values
    def update_corners_from_sliders():
        nonlocal corners_xy
        # Get scale factors from sliders (convert percentage to decimal)
        width_scale = width_slider.value() / 100.0
        height_scale = height_slider.value() / 100.0
        
        # Calculate center of original corners
        center_x = np_mean(original_corners[:, 0])
        center_y = np_mean(original_corners[:, 1])
        
        # To scale correctly, we need to transform to local coordinates (un-rotated)
        # Calculate rotation angle using similar logic to get_boundary_orientation_info
        # We know it's a rectangle because it comes from PCA/OBB
        p0 = original_corners[0]
        p1 = original_corners[1]
        p3 = original_corners[3]
        
        edge1 = p1 - p0
        edge2 = p3 - p0
        
        # Find the primary edge (longest one) for consistent orientation
        edge1_len = np_linalg.norm(edge1)
        edge2_len = np_linalg.norm(edge2)
        
        if edge1_len >= edge2_len:
            primary_edge = edge1
        else:
            primary_edge = edge2
        
        # Calculate rotation angle
        rotation_angle = np_arctan2(primary_edge[1], primary_edge[0])
        
        # Rotation matrices
        c, s = np_cos(-rotation_angle), np_sin(-rotation_angle)
        R_inv = np_array(((c, -s), (s, c))) # Rotate to align with axes
        
        c, s = np_cos(rotation_angle), np_sin(rotation_angle)
        R = np_array(((c, -s), (s, c))) # Rotate back
        
        # Center points
        centered_points = original_corners - np_array([center_x, center_y])
        
        # Rotate to local frame
        local_points = np_dot(centered_points, R_inv.T)
        
        # Apply scaling in local aligned frame
        scaled_local = local_points.copy()
        scaled_local[:, 0] *= width_scale
        scaled_local[:, 1] *= height_scale
        
        # Rotate back to global frame
        scaled_centered = np_dot(scaled_local, R.T)
        
        # Add center back
        scaled_corners = scaled_centered + np_array([center_x, center_y])
        
        corners_xy = scaled_corners
        return scaled_corners
    
    # Button layout
    button_layout = QGridLayout()
    
    # OBB compute button
    def compute_obb_callback():
        nonlocal corners_xy, top, bottom, original_corners, obb_angle, obb_translation
        new_result = compute_obb_boundary(self.parent)
        if new_result[0] is not None:
            corners_xy, new_top, new_bottom, new_angle, new_translation = new_result
            original_corners = corners_xy.copy()  # Update original reference
            obb_angle = new_angle
            obb_translation = new_translation
            top_edit.setText(f"{new_top:.2f}")
            bottom_edit.setText(f"{new_bottom:.2f}")
            top = new_top
            bottom = new_bottom
            # Reset sliders to 100%
            width_slider.setValue(100)
            height_slider.setValue(100)
    
    obb_button = QPushButton("Compute OBB")
    obb_button.clicked.connect(compute_obb_callback)
    
    ok_button = QPushButton("OK")
    cancel_button = QPushButton("Cancel")
    
    button_layout.addWidget(obb_button, 0, 0)
    button_layout.addWidget(cancel_button, 0, 1)
    button_layout.addWidget(ok_button, 0, 2)
    
    layout.addLayout(button_layout)
    
    # Dialog result handling
    dialog_result = {"accepted": False}
        
    def reject_dialog():
        dialog_result["accepted"] = False
        dialog.close()
    
    def accept_dialog():
        dialog_result["accepted"] = True
        # Update corners one final time before accepting
        update_corners_from_sliders()
        dialog.close()
    
    ok_button.clicked.connect(accept_dialog)
    cancel_button.clicked.connect(reject_dialog)
    
    # Show dialog and wait for result
    dialog.show()
    
    # Process events until dialog is closed
    while dialog.isVisible():
        QApplication.processEvents()
    
    if not dialog_result["accepted"]:
        self.enable_actions()
        return
    
    # Get values from dialog
    selected_data = boundary_combo.currentData()
    boundary_dict_updt = {
        "name": name_edit.text() if name_edit.text() else "obb_boundary",
        "top": float(top_edit.text()) if top_edit.text() else 1000.0,
        "bottom": float(bottom_edit.text()) if bottom_edit.text() else -1000.0,
        "activatevolume": "check" if volume_checkbox.isChecked() else "uncheck",
        "corners": corners_xy  # Store the oriented corners
    }
    
    # Check if top and bottom fields are valid
    if boundary_dict_updt["top"] == boundary_dict_updt["bottom"]:
        boundary_dict_updt["top"] = boundary_dict_updt["top"] + 1.0
    
    if selected_data == "new":
        # Creating new boundary
        # Check if other Boundaries with the same name exist. If so, add suffix to make the name unique.
        while True:
            if boundary_dict_updt["name"] in self.parent.boundary_coll.get_names:
                boundary_dict_updt["name"] = boundary_dict_updt["name"] + "_0"
            else:
                break
        
        boundary_dict["name"] = boundary_dict_updt["name"]
        
        if boundary_dict_updt["activatevolume"] == "check":
            # Build oriented Boundary as volume using OBB corners
            boundary_dict["topology"] = "TriSurf"
            boundary_dict["vtk_obj"] = TriSurf()
            nodes = vtkPoints()
            
            # Get the oriented corners
            corners = boundary_dict_updt["corners"]
            
            # Bottom face (4 corners at bottom Z)
            for i in range(4):
                nodes.InsertPoint(
                    i,
                    corners[i, 0],  # X from OBB
                    corners[i, 1],  # Y from OBB  
                    boundary_dict_updt["bottom"]  # Z bottom
                )
            
            # Top face (4 corners at top Z)
            for i in range(4):
                nodes.InsertPoint(
                    i + 4,
                    corners[i, 0],  # X from OBB
                    corners[i, 1],  # Y from OBB
                    boundary_dict_updt["top"]  # Z top
                )
            
            boundary_dict["vtk_obj"].SetPoints(nodes)
            
            # Create triangular faces for the oriented box
            # Bottom face (2 triangles)
            boundary_dict["vtk_obj"].append_cell(np_array([0, 1, 2]))
            boundary_dict["vtk_obj"].append_cell(np_array([0, 2, 3]))
            
            # Top face (2 triangles)
            boundary_dict["vtk_obj"].append_cell(np_array([4, 6, 5]))
            boundary_dict["vtk_obj"].append_cell(np_array([4, 7, 6]))
            
            # Side faces (8 triangles)
            boundary_dict["vtk_obj"].append_cell(np_array([0, 1, 4]))
            boundary_dict["vtk_obj"].append_cell(np_array([1, 4, 5]))
            boundary_dict["vtk_obj"].append_cell(np_array([1, 2, 5]))
            boundary_dict["vtk_obj"].append_cell(np_array([2, 5, 6]))
            boundary_dict["vtk_obj"].append_cell(np_array([2, 3, 6]))
            boundary_dict["vtk_obj"].append_cell(np_array([3, 6, 7]))
            boundary_dict["vtk_obj"].append_cell(np_array([3, 0, 7]))
            boundary_dict["vtk_obj"].append_cell(np_array([0, 7, 4]))
        else:
            # Build oriented rectangular polyline at Z=0 meters using OBB corners
            boundary_dict["topology"] = "PolyLine"
            boundary_dict["vtk_obj"] = PolyLine()
            corners = boundary_dict_updt["corners"]
            boundary_dict["vtk_obj"].points = [
                (corners[0, 0], corners[0, 1], 0.0),  # corner 0
                (corners[1, 0], corners[1, 1], 0.0),  # corner 1
                (corners[2, 0], corners[2, 1], 0.0),  # corner 2
                (corners[3, 0], corners[3, 1], 0.0),  # corner 3
                (corners[0, 0], corners[0, 1], 0.0),  # back to corner 0 to close
            ]
            boundary_dict["vtk_obj"].auto_cells()
        
        uid = self.parent.boundary_coll.add_entity_from_dict(entity_dict=boundary_dict)
        
        # Store OBB transformation properties on the boundary
        n_points = boundary_dict["vtk_obj"].points_number
        
        # Add obb_angle property
        self.parent.boundary_coll.append_uid_property(
            uid=uid, 
            property_name="obb_angle",
            property_components=1
        )
        self.parent.boundary_coll.get_uid_vtk_obj(uid).set_point_data(
            data_key="obb_angle",
            attribute_matrix=np_full(n_points, obb_angle, dtype=np_float32)
        )
        
        # Add obb_translation property
        self.parent.boundary_coll.append_uid_property(
            uid=uid,
            property_name="obb_translation",
            property_components=2
        )
        self.parent.boundary_coll.get_uid_vtk_obj(uid).set_point_data(
            data_key="obb_translation",
            attribute_matrix=np_tile(obb_translation, (n_points, 1)).astype(np_float32)
        )
    
    else:
        # Updating existing boundary - it was already updated in the preview
        # The boundary is already updated via the preview mechanism
        pass
    
    # Un-Freeze QT interface
    self.enable_actions()

def boundary_from_points(self, vector):
    """Create a new Boundary from a vector with two end points"""
    boundary_dict = deepcopy(self.parent.boundary_coll.entity_dict)
    # Freeze QT interface.
    self.disable_actions()
    # Draw the diagonal of the Boundary by drawing a vector with vector_by_mouse. "while True" lets the user
    # draw the vector multiple times if modifications are necessary.
    self.plotter.untrack_click_position(side="left")
    # Multiple_input_dialog widget is built to check the default value associated to each feature in
    # section_dict_in: this value defines the type (str-int-float) of the output that is passed to section_dict_updt.
    # It is therefore necessary in section_dict_in to implement the right type for each variable."""
    boundary_dict_in = {
        "warning": [
            "Boundary from points",
            "Build new Boundary from a user-drawn line that represents the horizontal diagonal\nof the Bounding box.\nOnce drawn, values can be modified from keyboard or by drawing another vector.",
            "QLabel",
        ],
        "name": ["Insert Boundary name", "new_boundary", "QLineEdit"],
        "origin_x": ["Insert origin X coord", vector.p1[0], "QLineEdit"],
        "origin_y": ["Insert origin Y coord", vector.p1[1], "QLineEdit"],
        "end_x": ["Insert end-point X coord", vector.p2[0], "QLineEdit"],
        "end_y": ["Insert end-point Y coord", vector.p2[1], "QLineEdit"],
        "top": ["Insert top", 1000.0, "QLineEdit"],
        "bottom": ["Insert bottom", -1000.0, "QLineEdit"],
        "activatevolume": [
            "volumeyn",
            "Do not create volume. Create horizontal parallelogram at Z=0 meters",
            "QCheckBox",
        ],
    }
    boundary_dict_updt = general_input_dialog(
        title="New Boundary from points", input_dict=boundary_dict_in
    )
    if boundary_dict_updt is None:
        self.enable_actions()
        return
    # Check if other Boundaries with the same name exist. If so, add suffix to make the name unique.
    while True:
        if boundary_dict_updt["name"] in self.parent.boundary_coll.get_names:
            boundary_dict_updt["name"] = boundary_dict_updt["name"] + "_0"
        else:
            break
    # Check if top and bottom fields are empty.
    if boundary_dict_updt["top"] is None:
        boundary_dict_updt["top"] = 1000.0
    if boundary_dict_updt["bottom"] is None:
        boundary_dict_updt["bottom"] = -1000.0
    if boundary_dict_updt["top"] == boundary_dict_updt["bottom"]:
        boundary_dict_updt["top"] = boundary_dict_updt["top"] + 1.0
    boundary_dict["name"] = boundary_dict_updt["name"]
    if boundary_dict_updt["activatevolume"] == "check":
        # Build rectangular polyline at Z=0 meters.
        boundary_dict["topology"] = "PolyLine"
        boundary_dict["vtk_obj"] = PolyLine()
        boundary_dict["vtk_obj"].points = [
            (boundary_dict_updt["origin_x"], boundary_dict_updt["origin_y"], 0.0),
            (boundary_dict_updt["end_x"], boundary_dict_updt["origin_y"], 0.0),
            (boundary_dict_updt["end_x"], boundary_dict_updt["end_y"], 0.0),
            (boundary_dict_updt["origin_x"], boundary_dict_updt["end_y"], 0.0),
            (boundary_dict_updt["origin_x"], boundary_dict_updt["origin_y"], 0.0),
        ]
        boundary_dict["vtk_obj"].auto_cells()
    else:
        # Build Boundary as volume.
        boundary_dict["topology"] = "TriSurf"
        boundary_dict["vtk_obj"] = TriSurf()
        nodes = vtkPoints()
        nodes.InsertPoint(
            0,
            boundary_dict_updt["origin_x"],
            boundary_dict_updt["origin_y"],
            boundary_dict_updt["bottom"],
        )
        nodes.InsertPoint(
            1,
            boundary_dict_updt["end_x"],
            boundary_dict_updt["origin_y"],
            boundary_dict_updt["bottom"],
        )
        nodes.InsertPoint(
            2,
            boundary_dict_updt["end_x"],
            boundary_dict_updt["end_y"],
            boundary_dict_updt["bottom"],
        )
        nodes.InsertPoint(
            3,
            boundary_dict_updt["origin_x"],
            boundary_dict_updt["end_y"],
            boundary_dict_updt["bottom"],
        )
        nodes.InsertPoint(
            4,
            boundary_dict_updt["origin_x"],
            boundary_dict_updt["origin_y"],
            boundary_dict_updt["top"],
        )
        nodes.InsertPoint(
            5,
            boundary_dict_updt["end_x"],
            boundary_dict_updt["origin_y"],
            boundary_dict_updt["top"],
        )
        nodes.InsertPoint(
            6,
            boundary_dict_updt["end_x"],
            boundary_dict_updt["end_y"],
            boundary_dict_updt["top"],
        )
        nodes.InsertPoint(
            7,
            boundary_dict_updt["origin_x"],
            boundary_dict_updt["end_y"],
            boundary_dict_updt["top"],
        )
        boundary_dict["vtk_obj"].SetPoints(nodes)
        boundary_dict["vtk_obj"].append_cell(np_array([0, 1, 4]))
        boundary_dict["vtk_obj"].append_cell(np_array([1, 4, 5]))
        boundary_dict["vtk_obj"].append_cell(np_array([1, 2, 5]))
        boundary_dict["vtk_obj"].append_cell(np_array([2, 5, 6]))
        boundary_dict["vtk_obj"].append_cell(np_array([2, 3, 6]))
        boundary_dict["vtk_obj"].append_cell(np_array([3, 6, 7]))
        boundary_dict["vtk_obj"].append_cell(np_array([0, 4, 7]))
        boundary_dict["vtk_obj"].append_cell(np_array([0, 3, 7]))
        boundary_dict["vtk_obj"].append_cell(np_array([4, 6, 7]))
        boundary_dict["vtk_obj"].append_cell(np_array([4, 5, 6]))
        boundary_dict["vtk_obj"].append_cell(np_array([0, 1, 3]))
        boundary_dict["vtk_obj"].append_cell(np_array([1, 2, 3]))
    uid = self.parent.boundary_coll.add_entity_from_dict(entity_dict=boundary_dict)
    # try:
    #     for view in self.parent.view_dict.values():
    #         if hasattr(view, "add_all_entities"):
    #             view.add_all_entities()
    # except Exception:
    #     pass
    # Un-Freeze QT interface
    self.enable_actions()


def boundary_from_three_points(self, vector):
    """Create a new Boundary from three points (orthogonal edges)"""
    boundary_dict = deepcopy(self.parent.boundary_coll.entity_dict)
    # Freeze QT interface.
    self.disable_actions()
    self.plotter.untrack_click_position(side="left")

    p1 = np_array(vector.p1, dtype=float)
    p2 = np_array(vector.p2, dtype=float)
    delta_xy = p2[:2] - p1[:2]
    length = np_linalg.norm(delta_xy)
    if length == 0:
        self.print_terminal(" -- Boundary from 3 points: first two points are coincident -- ")
        self.enable_actions()
        return

    # Show the first line segment (p1 -> p2) while placing the third point
    first_line = pv_Line((p1[0], p1[1], p1[2]), (p2[0], p2[1], p2[2]))
    first_actor_name = f"boundary_first_line_{uuid_uuid4()}"
    self.plotter.add_mesh(
        first_line,
        color="red",
        line_width=5,
        name=first_actor_name,
        pickable=False,
    )

    # Initialize rectangle outline (degenerate until third point moves)
    rect_points = np_array(
        [
            [p1[0], p1[1], p1[2]],
            [p2[0], p2[1], p2[2]],
            [p2[0], p2[1], p2[2]],
            [p1[0], p1[1], p1[2]],
            [p1[0], p1[1], p1[2]],
        ],
        dtype=float,
    )
    rect_line = pv_lines_from_points(rect_points, close=False)
    rect_actor_name = f"boundary_rect_preview_{uuid_uuid4()}"
    self.plotter.add_mesh(
        rect_line,
        color="red",
        line_width=5,
        name=rect_actor_name,
        pickable=False,
    )

    # Build orthogonal live guide line through p2
    perp_unit = np_array([-delta_xy[1], delta_xy[0]]) / length
    guide_line = pv_Line((p2[0], p2[1], p2[2]), (p2[0], p2[1], p2[2]))
    guide_actor_name = f"boundary_ortho_guide_{uuid_uuid4()}"
    self.plotter.add_mesh(
        guide_line,
        color="red",
        line_width=5,
        name=guide_actor_name,
        pickable=False,
    )

    self.print_terminal(" -- Click third point on the orthogonal guide line -- ")

    interactor = self.plotter.iren.interactor

    def update_live_line(obj=None, event=None):
        try:
            x, y = interactor.GetEventPosition()
            renderer = self.plotter.renderer
            renderer.SetDisplayPoint(x, y, 0)
            renderer.DisplayToWorld()
            world = np_array(renderer.GetWorldPoint(), dtype=float)
            if world[3] != 0:
                world = world / world[3]
            p_raw = np_array([world[0], world[1], p2[2]], dtype=float)
        except Exception:
            return
        t = (p_raw[0] - p2[0]) * perp_unit[0] + (p_raw[1] - p2[1]) * perp_unit[1]
        p_proj = np_array(
            [p2[0] + perp_unit[0] * t, p2[1] + perp_unit[1] * t, p2[2]]
        )
        p4 = np_array([p1[0] + (p_proj[0] - p2[0]), p1[1] + (p_proj[1] - p2[1]), p1[2]])
        guide_line.points = np_array(
            [[p2[0], p2[1], p2[2]], [p_proj[0], p_proj[1], p_proj[2]]]
        )
        guide_line.Modified()
        rect_line.points = np_array(
            [
                [p1[0], p1[1], p1[2]],
                [p2[0], p2[1], p2[2]],
                [p_proj[0], p_proj[1], p_proj[2]],
                [p4[0], p4[1], p4[2]],
                [p1[0], p1[1], p1[2]],
            ],
            dtype=float,
        )
        rect_line.Modified()
        try:
            self.plotter.render()
        except Exception:
            pass

    mouse_move_id = interactor.AddObserver("MouseMoveEvent", update_live_line)

    def end_third_point(event):
        self.plotter.untrack_click_position(side="left")
        try:
            interactor.RemoveObserver(mouse_move_id)
        except Exception:
            pass
        try:
            self.plotter.remove_actor(first_actor_name)
        except Exception:
            pass
        try:
            self.plotter.remove_actor(rect_actor_name)
        except Exception:
            pass
        try:
            self.plotter.remove_actor(guide_actor_name)
        except Exception:
            pass

        if event is None:
            self.enable_actions()
            return

        p3_raw = np_array(event, dtype=float)
        # Project third point onto orthogonal line through p2 (map XY)
        t = (p3_raw[0] - p2[0]) * perp_unit[0] + (p3_raw[1] - p2[1]) * perp_unit[1]
        p3 = np_array([p2[0] + perp_unit[0] * t, p2[1] + perp_unit[1] * t, p2[2]])

        boundary_dict_in = {
            "warning": [
                "Boundary from 3 points",
                "Build new Boundary from a user-drawn line and a third point constrained to\n"
                "an orthogonal guide line. Two orthogonal edges define the boundary box.\n"
                "Once picked, values can be modified from keyboard.",
                "QLabel",
            ],
            "name": ["Insert Boundary name", "new_boundary", "QLineEdit"],
            "p1_x": ["Insert point 1 X coord", p1[0], "QLineEdit"],
            "p1_y": ["Insert point 1 Y coord", p1[1], "QLineEdit"],
            "p2_x": ["Insert point 2 X coord", p2[0], "QLineEdit"],
            "p2_y": ["Insert point 2 Y coord", p2[1], "QLineEdit"],
            "p3_x": ["Insert point 3 X coord", p3[0], "QLineEdit"],
            "p3_y": ["Insert point 3 Y coord", p3[1], "QLineEdit"],
            "top": ["Insert top", 1000.0, "QLineEdit"],
            "bottom": ["Insert bottom", -1000.0, "QLineEdit"],
            "activatevolume": [
                "volumeyn",
                "Do not create volume. Create horizontal parallelogram at Z=0 meters",
                "QCheckBox",
            ],
        }

        boundary_dict_updt = general_input_dialog(
            title="New Boundary from 3 points", input_dict=boundary_dict_in
        )
        if boundary_dict_updt is None:
            self.enable_actions()
            return

        # Check if other Boundaries with the same name exist. If so, add suffix to make the name unique.
        while True:
            if boundary_dict_updt["name"] in self.parent.boundary_coll.get_names:
                boundary_dict_updt["name"] = boundary_dict_updt["name"] + "_0"
            else:
                break

        # Check if top and bottom fields are empty.
        if boundary_dict_updt["top"] is None:
            boundary_dict_updt["top"] = 1000.0
        if boundary_dict_updt["bottom"] is None:
            boundary_dict_updt["bottom"] = -1000.0
        if boundary_dict_updt["top"] == boundary_dict_updt["bottom"]:
            boundary_dict_updt["top"] = boundary_dict_updt["top"] + 1.0

        # Enforce orthogonality after possible manual edits
        p1_xy = np_array([boundary_dict_updt["p1_x"], boundary_dict_updt["p1_y"]], dtype=float)
        p2_xy = np_array([boundary_dict_updt["p2_x"], boundary_dict_updt["p2_y"]], dtype=float)
        p3_xy = np_array([boundary_dict_updt["p3_x"], boundary_dict_updt["p3_y"]], dtype=float)
        delta_xy_local = p2_xy - p1_xy
        length_local = np_linalg.norm(delta_xy_local)
        if length_local == 0:
            self.print_terminal(" -- Boundary from 3 points: point 1 and point 2 are coincident -- ")
            self.enable_actions()
            return
        perp_unit_local = np_array([-delta_xy_local[1], delta_xy_local[0]]) / length_local
        t_local = (p3_xy[0] - p2_xy[0]) * perp_unit_local[0] + (p3_xy[1] - p2_xy[1]) * perp_unit_local[1]
        p3_xy = p2_xy + perp_unit_local * t_local
        p4_xy = p1_xy + (p3_xy - p2_xy)
        # Store OBB-like orientation (angle in radians) so LoopStructural can align the model.
        # Convention must match compute_obb_boundary / get_boundary_obb_transform.
        obb_angle = float(np_arctan2(delta_xy_local[1], delta_xy_local[0]))

        boundary_dict["name"] = boundary_dict_updt["name"]

        if boundary_dict_updt["activatevolume"] == "check":
            # Build rectangular polyline at Z=0 meters (orthogonal, oriented).
            boundary_dict["topology"] = "PolyLine"
            boundary_dict["vtk_obj"] = PolyLine()
            boundary_dict["vtk_obj"].points = [
                (p1_xy[0], p1_xy[1], 0.0),
                (p2_xy[0], p2_xy[1], 0.0),
                (p3_xy[0], p3_xy[1], 0.0),
                (p4_xy[0], p4_xy[1], 0.0),
                (p1_xy[0], p1_xy[1], 0.0),
            ]
            boundary_dict["vtk_obj"].auto_cells()
        else:
            # Build Boundary as volume.
            boundary_dict["topology"] = "TriSurf"
            boundary_dict["vtk_obj"] = TriSurf()
            nodes = vtkPoints()
            # Bottom face
            nodes.InsertPoint(0, p1_xy[0], p1_xy[1], boundary_dict_updt["bottom"])
            nodes.InsertPoint(1, p2_xy[0], p2_xy[1], boundary_dict_updt["bottom"])
            nodes.InsertPoint(2, p3_xy[0], p3_xy[1], boundary_dict_updt["bottom"])
            nodes.InsertPoint(3, p4_xy[0], p4_xy[1], boundary_dict_updt["bottom"])
            # Top face
            nodes.InsertPoint(4, p1_xy[0], p1_xy[1], boundary_dict_updt["top"])
            nodes.InsertPoint(5, p2_xy[0], p2_xy[1], boundary_dict_updt["top"])
            nodes.InsertPoint(6, p3_xy[0], p3_xy[1], boundary_dict_updt["top"])
            nodes.InsertPoint(7, p4_xy[0], p4_xy[1], boundary_dict_updt["top"])
            boundary_dict["vtk_obj"].SetPoints(nodes)
            # Faces
            boundary_dict["vtk_obj"].append_cell(np_array([0, 1, 2]))
            boundary_dict["vtk_obj"].append_cell(np_array([0, 2, 3]))
            boundary_dict["vtk_obj"].append_cell(np_array([4, 6, 5]))
            boundary_dict["vtk_obj"].append_cell(np_array([4, 7, 6]))
            boundary_dict["vtk_obj"].append_cell(np_array([0, 1, 4]))
            boundary_dict["vtk_obj"].append_cell(np_array([1, 4, 5]))
            boundary_dict["vtk_obj"].append_cell(np_array([1, 2, 5]))
            boundary_dict["vtk_obj"].append_cell(np_array([2, 5, 6]))
            boundary_dict["vtk_obj"].append_cell(np_array([2, 3, 6]))
            boundary_dict["vtk_obj"].append_cell(np_array([3, 6, 7]))
            boundary_dict["vtk_obj"].append_cell(np_array([3, 0, 7]))
            boundary_dict["vtk_obj"].append_cell(np_array([0, 7, 4]))

        uid = self.parent.boundary_coll.add_entity_from_dict(entity_dict=boundary_dict)
        # Add OBB angle metadata (same pattern used by boundary_from_obb) so oriented boundaries
        # are correctly handled by LoopStructural alignment logic.
        try:
            n_points = boundary_dict["vtk_obj"].points_number
            self.parent.boundary_coll.append_uid_property(
                uid=uid, property_name="obb_angle", property_components=1
            )
            self.parent.boundary_coll.get_uid_vtk_obj(uid).set_point_data(
                data_key="obb_angle",
                attribute_matrix=np_full(n_points, obb_angle, dtype=np_float32),
            )
        except Exception:
            # If anything goes wrong, continue without OBB metadata (boundary still exists).
            pass
        try:
            for view in self.parent.view_dict.values():
                if hasattr(view, "add_all_entities"):
                    view.add_all_entities()
        except Exception:
            pass
        # Un-Freeze QT interface
        self.enable_actions()

    self.plotter.track_click_position(side="left", callback=end_third_point)


class BoundaryCollection(BaseCollection):
    """Collection for all boundaries and their metadata."""

    def __init__(self, parent=None, *args, **kwargs):
        super(BoundaryCollection, self).__init__(parent, *args, **kwargs)
        # Initialize properties required by the abstract superclass.
        self.entity_dict = {
            "uid": "",
            "name": "undef",
            "scenario": "undef",
            "parent_uid": "",  # this is the uid of the cross section for "XsVertexSet", "XsPolyLine", and "XsImage", empty for all others
            "topology": "undef",
            "vtk_obj": None,
            "properties_names": [],  # at the moment this is used to store OBB rotation -> use a dynamic property instead
            "properties_components": [],
        }

        self.entity_dict_types = {
            "uid": str,
            "name": str,
            "scenario": str,
            "parent_uid": str,
            "topology": str,
            "vtk_obj": object,
            "properties_names": list,
            "properties_components": list,
        }

        self.valid_topologies = ["PolyLine", "TriSurf", "XsPolyLine"]

        self.editable_columns_names = ["name", "scenario"]

        self.collection_name = "boundary_coll"

        self.initialize_df()

    # =================================== Obligatory methods ===========================================

    def add_entity_from_dict(
        self, entity_dict: pd_DataFrame = None, color: np_ndarray = None
    ):
        """Add an entity from a dictionary shaped as self.entity_dict."""
        # Create a new uid if it is not included in the dictionary.
        if not entity_dict["uid"]:
            entity_dict["uid"] = str(uuid_uuid4())
        # Append new row to dataframe. Note that the 'append()' method for Pandas dataframes DOES NOT
        # work in place, hence a NEW dataframe is created every time and then substituted to the old one.
        # New syntax with Pandas >= 2.0.0:
        self.df = pd_concat([self.df, pd_DataFrame([entity_dict])], ignore_index=True)
        # Reset data model.
        self.modelReset.emit()
        # Then emit signal to update the views. A list of uids is emitted, even if the entity is just one.
        self.parent.signals.entities_added.emit([entity_dict["uid"]], self)
        return entity_dict["uid"]

    def remove_entity(self, uid: str = None) -> str:
        """Remove an entity and its metadata."""
        # Remove row from dataframe and reset data model.
        self.df.drop(self.df[self.df["uid"] == uid].index, inplace=True)
        self.modelReset.emit()  # is this really necessary?
        # When done, send a signal over to the views. A list of uids is emitted, even if the entity is just one.
        self.parent.signals.entities_removed.emit([uid], self)
        return uid

    def clone_entity(self, uid: str = None) -> str:
        """Clone an entity."""
        # Not implemented for this collection, but required by the abstract superclass.
        pass

    def attr_modified_update_legend_table(self):
        """Update legend table when attributes are changed."""
        # Not implemented for this collection, but required by the abstract superclass.
        pass

    def remove_unused_from_legend(self):
        """Remove unused roles / features from a legend table."""
        legend_updated: bool = False
        return legend_updated

    def get_uid_legend(self, uid: str = None) -> dict:
        """Supposed to get legend for a particular uid, in this case gets legend for boundaries that are all the same."""
        legend_dict = self.parent.others_legend_df.loc[
            self.parent.others_legend_df["other_collection"] == "Boundary"
        ].to_dict("records")
        return legend_dict[0]

    def set_uid_legend(
        self,
        uid: str = None,
        color_R: float = None,
        color_G: float = None,
        color_B: float = None,
        line_thick: float = None,
        point_size: float = None,
        opacity: float = None,
    ):
        """Set the legend for a particular uid."""
        # Not implemented for this collection, but required by the abstract superclass.
        pass
