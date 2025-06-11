"""boundary_collection.py
PZero© Andrea Bistacchi"""

from vtkmodules.vtkCommonDataModel import vtkDataObject

from copy import deepcopy
from uuid import uuid4 as uuid_uuid4

from numpy import array as np_array
from numpy import ndarray as np_ndarray
from numpy import set_printoptions as np_set_printoptions

from pandas import DataFrame as pd_DataFrame
from pandas import set_option as pd_set_option
from pandas import concat as pd_concat
import numpy as np
from vtk import vtkPoints
# import np_mean
from numpy import mean as np_mean

from pzero.entities_factory import PolyLine, TriSurf
from pzero.helpers.helper_dialogs import general_input_dialog
from .AbstractCollection import BaseCollection

# Options to print Pandas dataframes in console for testing.
pd_desired_width = 800
pd_max_columns = 20
pd_show_precision = 4
pd_max_colwidth = 80
pd_set_option("display.width", pd_desired_width)
np_set_printoptions(linewidth=pd_desired_width)
pd_set_option("display.max_columns", pd_max_columns)
pd_set_option("display.precision", pd_show_precision)
pd_set_option("display.max_colwidth", pd_max_colwidth)

def compute_pca_boundary(parent):
    """Compute boundary box from all data using PCA analysis"""
    from numpy import concatenate as np_concatenate
    from numpy import mean as np_mean
    from numpy import std as np_std
    from numpy import min as np_min
    from numpy import max as np_max
    from sklearn.decomposition import PCA
    
    # Collect all points from all collections
    all_points = []
    
    # Get points from geological collection
    try:
        for uid in parent.geol_coll.get_uids:
            vtk_obj = parent.geol_coll.get_uid_vtk_obj(uid)
            if hasattr(vtk_obj, 'points') and isinstance(vtk_obj.points, np_ndarray):
                all_points.append(vtk_obj.points)
    except:
        pass
    
    # Get points from fluid collection  
    try:
        for uid in parent.fluid_coll.get_uids:
            vtk_obj = parent.fluid_coll.get_uid_vtk_obj(uid)
            if hasattr(vtk_obj, 'points') and isinstance(vtk_obj.points, np_ndarray):
                all_points.append(vtk_obj.points)
    except:
        pass
        
    # Get points from background collection
    try:
        for uid in parent.backgrnd_coll.get_uids:
            vtk_obj = parent.backgrnd_coll.get_uid_vtk_obj(uid)
            if hasattr(vtk_obj, 'points') and isinstance(vtk_obj.points, np_ndarray):
                all_points.append(vtk_obj.points)
    except:
        pass
        
    # Get points from well collection
    try:
        for uid in parent.well_coll.get_uids:
            vtk_obj = parent.well_coll.get_uid_vtk_obj(uid)
            if hasattr(vtk_obj, 'points') and isinstance(vtk_obj.points, np_ndarray):
                all_points.append(vtk_obj.points)
    except:
        pass
        
    # Get points from domain collection
    try:
        for uid in parent.dom_coll.get_uids:
            vtk_obj = parent.dom_coll.get_uid_vtk_obj(uid)
            if hasattr(vtk_obj, 'points') and isinstance(vtk_obj.points, np_ndarray):
                all_points.append(vtk_obj.points)
    except:
        pass
    
    if not all_points:
        return None, None, None, None, None, None
        
    # Concatenate all points
    combined_points = np_concatenate(all_points, axis=0)
    
    # Use only X,Y coordinates for 2D PCA (map view)
    xy_points = combined_points[:, :2]
    
    # Compute PCA
    pca = PCA(n_components=2)
    pca.fit(xy_points)
    
    # Get the mean center
    center = np_mean(xy_points, axis=0)
    
    # Transform points to PCA space
    transformed_points = pca.transform(xy_points)
    
    # Find the extent in PCA space
    min_pca = np_array([np_min(transformed_points[:, 0]), np_min(transformed_points[:, 1])])
    max_pca = np_array([np_max(transformed_points[:, 0]), np_max(transformed_points[:, 1])])
    
    # Add some margin (10% of range)
    range_pca = max_pca - min_pca
    margin = range_pca * 0.1
    min_pca_extended = min_pca - margin
    max_pca_extended = max_pca + margin
    
    # Create corner points in PCA space (oriented rectangle)
    corners_pca = np_array([
        [min_pca_extended[0], min_pca_extended[1]],  # corner 0
        [max_pca_extended[0], min_pca_extended[1]],  # corner 1 
        [max_pca_extended[0], max_pca_extended[1]],  # corner 2
        [min_pca_extended[0], max_pca_extended[1]]   # corner 3
    ])
    
    # Transform corners back to original coordinate space
    corners_xy = pca.inverse_transform(corners_pca)
    
    # Get Z extent from all points
    z_min = np_min(combined_points[:, 2])
    z_max = np_max(combined_points[:, 2])
    z_range = z_max - z_min
    z_margin = z_range * 0.1
    z_bottom = z_min - z_margin
    z_top = z_max + z_margin
    
    # Return all four corners of the oriented rectangle plus Z extent
    return corners_xy, z_top, z_bottom

def boundary_from_pca(self):
    """Create a new Boundary from PCA analysis of all data"""
    boundary_dict = deepcopy(self.parent.boundary_coll.entity_dict)
    
    # Freeze QT interface
    self.disable_actions()
    
    # Compute initial PCA values
    pca_result = compute_pca_boundary(self.parent)
    
    if pca_result[0] is None:
        from pzero.helpers.helper_dialogs import message_dialog
        message_dialog(title="PCA Boundary Error", message="No data found to compute PCA boundary.")
        self.enable_actions()
        return
    
    # Extract PCA results
    corners_xy, top, bottom = pca_result
    
    # Create enhanced dialog with PCA compute button and size controls
    from PySide6.QtWidgets import (QWidget, QGridLayout, QLabel, QLineEdit, QCheckBox, 
                                   QPushButton, QVBoxLayout, QSlider, QHBoxLayout, QSpinBox,
                                   QGroupBox)
    from PySide6.QtCore import Qt
    
    # Store original PCA dimensions for scaling
    original_corners = corners_xy.copy()
    from numpy import linalg as np_linalg
    
    # Calculate original dimensions in PCA space for scaling reference
    pca_width = np.max(corners_xy[:, 0]) - np.min(corners_xy[:, 0])
    pca_height = np.max(corners_xy[:, 1]) - np.min(corners_xy[:, 1])
    
    # Create custom dialog widget
    dialog = QWidget()
    dialog.setWindowTitle("New Boundary from PCA - Interactive Sizing")
    dialog.resize(500, 400)
    dialog.setWindowModality(Qt.ApplicationModal)
    
    layout = QVBoxLayout(dialog)
    
    # Add warning label
    warning_label = QLabel("Build new Boundary using PCA analysis of all data.\nOriented boundary box will be created based on principal components.\nUse sliders to adjust size and click 'Update Preview' to see changes.")
    layout.addWidget(warning_label)
    
    # Create form layout for basic inputs
    basic_group = QGroupBox("Basic Settings")
    basic_layout = QGridLayout(basic_group)
    
    # Boundary selection dropdown
    from PySide6.QtWidgets import QComboBox
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
    name_edit = QLineEdit("pca_boundary")
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
            name_edit.setText("pca_boundary")
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
                        z_min = np.min(existing_z_values)
                        z_max = np.max(existing_z_values)
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
        
        # Scale corners relative to center
        scaled_corners = original_corners.copy()
        scaled_corners[:, 0] = center_x + (scaled_corners[:, 0] - center_x) * width_scale
        scaled_corners[:, 1] = center_y + (scaled_corners[:, 1] - center_y) * height_scale
        
        corners_xy = scaled_corners
        return scaled_corners
    
    # Function to update preview in the main view
    def update_preview():
        # Update corners based on current slider values
        updated_corners = update_corners_from_sliders()
        
        selected_data = boundary_combo.currentData()
        current_top = float(top_edit.text()) if top_edit.text() else top
        current_bottom = float(bottom_edit.text()) if bottom_edit.text() else bottom
        
        if selected_data == "new":
            # Create a temporary boundary for preview
            temp_boundary_dict = deepcopy(self.parent.boundary_coll.entity_dict)
            temp_boundary_dict["name"] = "preview_boundary_temp"
            
            if volume_checkbox.isChecked():
                # Create 3D preview
                temp_boundary_dict["topology"] = "TriSurf"
                temp_boundary_dict["vtk_obj"] = TriSurf()
                nodes = vtkPoints()
                
                # Bottom face
                for i in range(4):
                    nodes.InsertPoint(i, updated_corners[i, 0], updated_corners[i, 1], current_bottom)
                # Top face  
                for i in range(4):
                    nodes.InsertPoint(i + 4, updated_corners[i, 0], updated_corners[i, 1], current_top)
                
                temp_boundary_dict["vtk_obj"].SetPoints(nodes)
                # Add faces (simplified for preview)
                temp_boundary_dict["vtk_obj"].append_cell(np_array([0, 1, 2]))
                temp_boundary_dict["vtk_obj"].append_cell(np_array([0, 2, 3]))
                temp_boundary_dict["vtk_obj"].append_cell(np_array([4, 6, 5]))
                temp_boundary_dict["vtk_obj"].append_cell(np_array([4, 7, 6]))
                temp_boundary_dict["vtk_obj"].append_cell(np_array([0, 1, 4]))
                temp_boundary_dict["vtk_obj"].append_cell(np_array([1, 4, 5]))
                temp_boundary_dict["vtk_obj"].append_cell(np_array([1, 2, 5]))
                temp_boundary_dict["vtk_obj"].append_cell(np_array([2, 5, 6]))
                temp_boundary_dict["vtk_obj"].append_cell(np_array([2, 3, 6]))
                temp_boundary_dict["vtk_obj"].append_cell(np_array([3, 6, 7]))
                temp_boundary_dict["vtk_obj"].append_cell(np_array([3, 0, 7]))
                temp_boundary_dict["vtk_obj"].append_cell(np_array([0, 7, 4]))
            else:
                # Create 2D preview
                temp_boundary_dict["topology"] = "PolyLine"
                temp_boundary_dict["vtk_obj"] = PolyLine()
                temp_boundary_dict["vtk_obj"].points = [
                    (updated_corners[0, 0], updated_corners[0, 1], 0.0),
                    (updated_corners[1, 0], updated_corners[1, 1], 0.0),
                    (updated_corners[2, 0], updated_corners[2, 1], 0.0),
                    (updated_corners[3, 0], updated_corners[3, 1], 0.0),
                    (updated_corners[0, 0], updated_corners[0, 1], 0.0),
                ]
                temp_boundary_dict["vtk_obj"].auto_cells()
            
            # Remove any existing preview
            existing_preview_uids = [uid for uid in self.parent.boundary_coll.get_uids if 
                                    self.parent.boundary_coll.get_uid_name(uid) == "preview_boundary_temp"]
            for uid in existing_preview_uids:
                self.parent.boundary_coll.remove_entity(uid)
            
            # Add new preview
            preview_uid = self.parent.boundary_coll.add_entity_from_dict(entity_dict=temp_boundary_dict)
        
        else:
            # Update existing boundary directly
            existing_uid = selected_data
            existing_vtk = self.parent.boundary_coll.get_uid_vtk_obj(existing_uid)
            
            if volume_checkbox.isChecked():
                # Update to 3D boundary
                if not isinstance(existing_vtk, TriSurf):
                    # Convert from 2D to 3D
                    new_vtk = TriSurf()
                else:
                    new_vtk = existing_vtk
                    new_vtk.Reset()  # Clear existing geometry
                
                nodes = vtkPoints()
                # Bottom face
                for i in range(4):
                    nodes.InsertPoint(i, updated_corners[i, 0], updated_corners[i, 1], current_bottom)
                # Top face  
                for i in range(4):
                    nodes.InsertPoint(i + 4, updated_corners[i, 0], updated_corners[i, 1], current_top)
                
                new_vtk.SetPoints(nodes)
                # Add faces
                new_vtk.append_cell(np_array([0, 1, 2]))
                new_vtk.append_cell(np_array([0, 2, 3]))
                new_vtk.append_cell(np_array([4, 6, 5]))
                new_vtk.append_cell(np_array([4, 7, 6]))
                new_vtk.append_cell(np_array([0, 1, 4]))
                new_vtk.append_cell(np_array([1, 4, 5]))
                new_vtk.append_cell(np_array([1, 2, 5]))
                new_vtk.append_cell(np_array([2, 5, 6]))
                new_vtk.append_cell(np_array([2, 3, 6]))
                new_vtk.append_cell(np_array([3, 6, 7]))
                new_vtk.append_cell(np_array([3, 0, 7]))
                new_vtk.append_cell(np_array([0, 7, 4]))
                
                # Update the topology if changed
                if not isinstance(existing_vtk, TriSurf):
                    self.parent.boundary_coll.df.loc[
                        self.parent.boundary_coll.df["uid"] == existing_uid, "topology"
                    ] = "TriSurf"
                
                self.parent.boundary_coll.replace_vtk(existing_uid, new_vtk)
            
            else:
                # Update to 2D boundary
                if not isinstance(existing_vtk, PolyLine):
                    # Convert from 3D to 2D
                    new_vtk = PolyLine()
                else:
                    new_vtk = existing_vtk
                    new_vtk.Reset()  # Clear existing geometry
                
                new_vtk.points = [
                    (updated_corners[0, 0], updated_corners[0, 1], 0.0),
                    (updated_corners[1, 0], updated_corners[1, 1], 0.0),
                    (updated_corners[2, 0], updated_corners[2, 1], 0.0),
                    (updated_corners[3, 0], updated_corners[3, 1], 0.0),
                    (updated_corners[0, 0], updated_corners[0, 1], 0.0),
                ]
                new_vtk.auto_cells()
                
                # Update the topology if changed
                if not isinstance(existing_vtk, PolyLine):
                    self.parent.boundary_coll.df.loc[
                        self.parent.boundary_coll.df["uid"] == existing_uid, "topology"
                    ] = "PolyLine"
                
                self.parent.boundary_coll.replace_vtk(existing_uid, new_vtk)
        
        # Force view update
        try:
            for view in self.parent.view_dict.values():
                if hasattr(view, 'add_all_entities'):
                    view.add_all_entities()
        except:
            pass
    
    # Button layout
    button_layout = QGridLayout()
    
    # PCA compute button
    def compute_pca_callback():
        nonlocal corners_xy, top, bottom, original_corners
        new_result = compute_pca_boundary(self.parent)
        if new_result[0] is not None:
            corners_xy, new_top, new_bottom = new_result
            original_corners = corners_xy.copy()  # Update original reference
            top_edit.setText(f"{new_top:.2f}")
            bottom_edit.setText(f"{new_bottom:.2f}")
            top = new_top
            bottom = new_bottom
            # Reset sliders to 100%
            width_slider.setValue(100)
            height_slider.setValue(100)
    
    pca_button = QPushButton("Compute PCA")
    pca_button.clicked.connect(compute_pca_callback)
    
    update_button = QPushButton("Update Preview")
    update_button.clicked.connect(update_preview)
    
    ok_button = QPushButton("OK")
    cancel_button = QPushButton("Cancel")
    
    button_layout.addWidget(pca_button, 0, 0)
    button_layout.addWidget(update_button, 0, 1)
    button_layout.addWidget(cancel_button, 0, 2)
    button_layout.addWidget(ok_button, 0, 3)
    
    layout.addLayout(button_layout)
    
    # Dialog result handling
    dialog_result = {"accepted": False}
        
    def reject_dialog():
        dialog_result["accepted"] = False
        # Clean up preview when canceling
        existing_preview_uids = [uid for uid in self.parent.boundary_coll.get_uids if 
                                self.parent.boundary_coll.get_uid_name(uid) == "preview_boundary_temp"]
        for uid in existing_preview_uids:
            self.parent.boundary_coll.remove_entity(uid)
        dialog.close()
    
    def accept_dialog():
        dialog_result["accepted"] = True
        # Update corners one final time before accepting
        update_corners_from_sliders()
        # Clean up preview
        existing_preview_uids = [uid for uid in self.parent.boundary_coll.get_uids if 
                                self.parent.boundary_coll.get_uid_name(uid) == "preview_boundary_temp"]
        for uid in existing_preview_uids:
            self.parent.boundary_coll.remove_entity(uid)
        dialog.close()
    
    ok_button.clicked.connect(accept_dialog)
    cancel_button.clicked.connect(reject_dialog)
    
    # Show dialog and wait for result
    dialog.show()
    
    # Process events until dialog is closed
    from PySide6.QtWidgets import QApplication
    while dialog.isVisible():
        QApplication.processEvents()
    
    if not dialog_result["accepted"]:
        self.enable_actions()
        return
    
    # Get values from dialog
    selected_data = boundary_combo.currentData()
    boundary_dict_updt = {
        "name": name_edit.text() if name_edit.text() else "pca_boundary",
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
            # Build oriented Boundary as volume using PCA corners
            boundary_dict["topology"] = "TriSurf"
            boundary_dict["vtk_obj"] = TriSurf()
            nodes = vtkPoints()
            
            # Get the oriented corners
            corners = boundary_dict_updt["corners"]
            
            # Bottom face (4 corners at bottom Z)
            for i in range(4):
                nodes.InsertPoint(
                    i,
                    corners[i, 0],  # X from PCA
                    corners[i, 1],  # Y from PCA  
                    boundary_dict_updt["bottom"]  # Z bottom
                )
            
            # Top face (4 corners at top Z)
            for i in range(4):
                nodes.InsertPoint(
                    i + 4,
                    corners[i, 0],  # X from PCA
                    corners[i, 1],  # Y from PCA
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
            # Build oriented rectangular polyline at Z=0 meters using PCA corners
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
    
    else:
        # Updating existing boundary - it was already updated in the preview
        # The boundary is already updated via the preview mechanism
        pass
    
    # Un-Freeze QT interface
    self.enable_actions()

def boundary_from_points(self, vector):
    """Create a new Boundary from a vector"""
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
    # Un-Freeze QT interface
    self.enable_actions()


class BoundaryCollection(BaseCollection):
    """Collection for all boundaries and their metadata."""
    def __init__(self, parent=None, *args, **kwargs):
        super(BoundaryCollection, self).__init__(parent, *args, **kwargs)
        # Initialize properties required by the abstract superclass.
        self.entity_dict = {
            "uid": "",
            "name": "undef",
            "topology": "undef",
            "scenario": "undef",
            "x_section": "", # this is the uid of the cross section for "XsVertexSet", "XsPolyLine", and "XsImage", empty for all others
            "vtk_obj": None,
        }

        self.entity_dict_types = {
            "uid": str,
            "name": str,
            "topology": str,
            "scenario": str,
            "x_section": str,
            "vtk_obj": object,
        }

        self.valid_topologies = ["PolyLine", "TriSurf", "XsPolyLine"]

        self.editable_columns_names = ["name", "scenario"]

        self.collection_name = 'boundary'

        self.initialize_df()

    # =================================== Obligatory methods ===========================================

    def add_entity_from_dict(self, entity_dict: pd_DataFrame = None, color: np_ndarray = None):
        """Add an entity from a dictionary shaped as self.entity_dict."""
        # Create a new uid if it is not included in the dictionary.
        if not entity_dict["uid"]:
            entity_dict["uid"] = str(uuid_uuid4())
        # Append new row to dataframe. Note that the 'append()' method for Pandas dataframes DOES NOT
        # work in place, hence a NEW dataframe is created every time and then substituted to the old one.
        # Old and less efficient syntax used up to Pandas 1.5.3:
        # self.df = self.df.append(entity_dict, ignore_index=True)
        # New syntax with Pandas >= 2.0.0:
        self.df = pd_concat([self.df, pd_DataFrame([entity_dict])], ignore_index=True)
        # Reset data model.
        self.modelReset.emit()
        # Then emit signal to update the views. A list of uids is emitted, even if the entity is just one.
        self.signals.added.emit([entity_dict["uid"]])
        return entity_dict["uid"]

    def remove_entity(self, uid: str = None) -> str:
        """Remove an entity and its metadata."""
        # Remove row from dataframe and reset data model.
        self.df.drop(self.df[self.df["uid"] == uid].index, inplace=True)
        self.modelReset.emit()  # is this really necessary?
        # When done, send a signal over to the views. A list of uids is emitted, even if the entity is just one.
        self.signals.removed.emit([uid])
        return uid

    def clone_entity(self, uid: str = None) -> str:
        """Clone an entity."""
        # Not implemented for this collection, but required by the abstract superclass.
        pass

    def replace_vtk(self, uid: str = None, vtk_object: vtkDataObject = None):
        """Replace the vtk object of a given uid with another vtkobject."""
        # ============ CAN BE UNIFIED AS COMMON METHOD OF THE ABSTRACT COLLECTION WHEN SIGNALS WILL BE UNIFIED ==========
        if isinstance(vtk_object, type(self.df.loc[self.df["uid"] == uid, "vtk_obj"].values[0])):
            self.df.loc[self.df["uid"] == uid, "vtk_obj"] = vtk_object
            self.signals.geom_modified.emit([uid])
        else:
            print("ERROR - replace_vtk with vtk of a different type not allowed.")

    def attr_modified_update_legend_table(self):
        """Update legend table when attributes are changed."""
        # Not implemented for this collection, but required by the abstract superclass.
        pass

    def remove_unused_from_legend(self):
        """Remove unused roles / features from a legend table."""
        legend_updated: bool = False
        return legend_updated

    def get_uid_legend(self, uid: str = None) -> dict:
        """Get legend for a particular uid."""
        # Not implemented for this collection, but required by the abstract superclass.
        pass

    def set_uid_legend(self, uid: str = None, color_R: float = None, color_G: float = None, color_B: float = None,
                       line_thick: float = None, point_size: float = None, opacity: float = None):
        """Set the legend for a particular uid."""
        # Not implemented for this collection, but required by the abstract superclass.
        pass
