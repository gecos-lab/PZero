"""three_d_surfaces.py
PZero© Andrea Bistacchi"""

from copy import deepcopy

from uuid import uuid4

from PySide6.QtWidgets import QDockWidget

from pyvista import PolyData as pv_PolyData

from numpy import abs as np_abs
from numpy import array as np_array
from numpy import around as np_around
from numpy import cbrt as np_cbrt
from numpy import cos as np_cos
from numpy import flip as np_flip
from numpy import float32 as np_float32
from numpy import float64 as np_float64
from numpy import ndarray as np_ndarray
from numpy import pi as np_pi
from numpy import sin as np_sin
from numpy import sqrt as np_sqrt
from numpy import zeros as np_zeros

from pandas import DataFrame as pd_DataFrame
from pandas import concat as pd_concat

from scipy.interpolate import griddata as sp_griddata

from vtk import (
    vtkAppendPolyData,
    vtkDelaunay2D,
    vtkSurfaceReconstructionFilter,
    vtkPoints,
    vtkPolyData,
    vtkContourFilter,
    vtkSmoothPolyDataFilter,
    vtkLinearExtrusionFilter,
    vtkTransform,
    vtkTransformPolyDataFilter,
    vtkDecimatePro,
    vtkQuadricDecimation,
    vtkLinearSubdivisionFilter,
    vtkButterflySubdivisionFilter,
    vtkLoopSubdivisionFilter,
    vtkStripper,
    vtkCleanPolyData,
    vtkTriangleFilter,
    vtkImageData,
    vtkCutter,
    vtkPointInterpolator2D,
    vtkVoronoiKernel,
    vtkThresholdPoints,
    vtkDataObject,
    vtkPolyDataConnectivityFilter,
    vtkClipPolyData,
)
from vtkmodules.util import numpy_support
from vtkmodules.vtkCommonDataModel import vtkBoundingBox

from LoopStructural import GeologicalModel

from pzero.helpers.helper_dialogs import (
    multiple_input_dialog,
    input_one_value_dialog,
    input_text_dialog,
    input_combo_dialog,
    input_checkbox_dialog,
    options_dialog,
    tic,
    toc,
    progress_dialog,
    general_input_dialog,
)
from .entities_factory import (
    TriSurf,
    XsPolyLine,
    PolyLine,
    VertexSet,
    Voxet,
    XsVoxet,
    XsVertexSet,
    Attitude,
)
from .helpers.helper_functions import freeze_gui_onoff, freeze_gui_on, freeze_gui_off


def _build_extrusion_output_dict(self, input_uid, title, default_suffix):
    """Create the output entity dictionary shared by extrusion tools."""
    surf_dict = deepcopy(self.geol_coll.entity_dict)
    input_dict = {
        "name": [
            "TriSurf name: ",
            self.geol_coll.get_uid_name(input_uid) + default_suffix,
        ],
        "role": [
            "Role: ",
            self.geol_coll.valid_roles,
        ],
        "feature": [
            "Feature: ",
            self.geol_coll.get_uid_feature(input_uid),
        ],
        "scenario": ["Scenario: ", self.geol_coll.get_uid_scenario(input_uid)],
    }
    surf_dict_updt = multiple_input_dialog(title=title, input_dict=input_dict)
    if surf_dict_updt is None:
        return None
    for key in surf_dict_updt:
        surf_dict[key] = surf_dict_updt[key]
    surf_dict["topology"] = "TriSurf"
    surf_dict["vtk_obj"] = TriSurf()
    return surf_dict


def _ask_linear_extrusion_parameters(self, title):
    """Ask for extrusion direction and vertical limits."""
    trend = input_one_value_dialog(title=title, label="Trend Value", default_value=90.0)
    if trend is None:
        trend = 90.0
    plunge = input_one_value_dialog(
        title=title, label="Plunge Value", default_value=30.0
    )
    if plunge is None:
        plunge = 30.0
    extrusion_par = {"bottom": ["Lower limit:", -1000], "top": ["Higher limit", 1000]}
    vertical_extrusion = multiple_input_dialog(
        title="Vertical Extrusion", input_dict=extrusion_par
    )
    if vertical_extrusion is None:
        self.print_terminal(
            "Wrong extrusion parameters, please check the top and bottom values"
        )
        return None
    if vertical_extrusion["top"] <= vertical_extrusion["bottom"]:
        self.print_terminal(" -- Higher limit must be greater than lower limit -- ")
        return None
    return trend, plunge, vertical_extrusion


def _get_linear_extrusion_vector(trend, plunge):
    """Return extrusion direction cosines from trend/plunge."""
    x_vector = -(np_cos((trend - 90) * np_pi / 180) * np_cos(plunge * np_pi / 180))
    y_vector = np_sin((trend - 90) * np_pi / 180) * np_cos(plunge * np_pi / 180)
    z_vector = np_sin(plunge * np_pi / 180)
    return x_vector, y_vector, z_vector


def _build_sampled_extrusion_surface(
    source_line, extrusion_vector, bottom_limit, top_limit, sample_lines
):
    """Create a triangulated extrusion with intermediate profiles."""
    ordered_line = source_line.deep_copy()
    ordered_line.sort_nodes()
    if ordered_line.points_number < 2:
        return None

    source_points = np_array(ordered_line.points)
    points_per_row = source_points.shape[0]
    row_count = int(sample_lines) + 2
    if row_count < 2:
        row_count = 2

    extrusion_vector = np_array(extrusion_vector)
    scale_step = (top_limit - bottom_limit) / (row_count - 1)

    output_surface = TriSurf()
    for row_id in range(row_count):
        row_offset = bottom_limit + row_id * scale_step
        translated_row = source_points + row_offset * extrusion_vector
        for point in translated_row:
            output_surface.append_point(point)

    for row_id in range(row_count - 1):
        row_start = row_id * points_per_row
        next_row_start = (row_id + 1) * points_per_row
        for point_id in range(points_per_row - 1):
            point_00 = row_start + point_id
            point_01 = row_start + point_id + 1
            point_10 = next_row_start + point_id
            point_11 = next_row_start + point_id + 1
            output_surface.append_cell(
                cell_array=np_array([point_00, point_10, point_01])
            )
            output_surface.append_cell(
                cell_array=np_array([point_01, point_10, point_11])
            )

    output_surface.BuildLinks()
    output_surface.Modified()
    return output_surface


def get_boundary_obb_transform(boundary_coll, boundary_uid):
    """
    Get OBB transformation parameters from a boundary if available.
    
    Returns a dict with:
        - 'has_obb': bool - whether the boundary has OBB transformation data
        - 'angle': float - rotation angle in radians (around Z axis)
        - 'translation': ndarray - translation vector [tx, ty] in local (rotated) space
        - 'center': ndarray - center of the oriented bounding box [cx, cy]
        
    The transformation to align OBB with axes is:
        1. Translate to center: p' = p - center
        2. Rotate by -angle: p'' = R(-angle) @ p'
        
    The inverse transformation (from axis-aligned back to OBB) is:
        1. Rotate by angle: p' = R(angle) @ p''
        2. Translate from center: p = p' + center
    """
    from numpy import mean as np_mean
    from numpy import arctan2 as np_arctan2
    from numpy import linalg as np_linalg
    from numpy import array as np_array
    from numpy import cos as np_cos
    from numpy import sin as np_sin
    
    vtk_obj = boundary_coll.get_uid_vtk_obj(boundary_uid)
    
    # Check if boundary has OBB properties
    property_names = boundary_coll.get_uid_properties_names(boundary_uid)
    
    if "obb_angle" not in property_names:
        return {"has_obb": False}
    
    # Get OBB angle from point data (it's the same for all points)
    obb_angle = vtk_obj.get_point_data("obb_angle")[0]
    
    # Get OBB translation if available
    obb_translation = None
    if "obb_translation" in property_names:
        obb_translation = vtk_obj.get_point_data("obb_translation")[0]
    
    # Calculate center from boundary points (XY only)
    points = vtk_obj.points
    center_xy = np_array([np_mean(points[:, 0]), np_mean(points[:, 1])])
    
    return {
        "has_obb": True,
        "angle": float(obb_angle),
        "translation": obb_translation,
        "center": center_xy
    }


def transform_points_to_aligned(points_df, obb_info):
    """
    Transform points from OBB-oriented space to axis-aligned space.
    
    The OBB algorithm stores the angle such that:
    - The rotation matrix R = [[cos(angle), sin(angle)], [-sin(angle), cos(angle)]]
      transforms points from world space to aligned (local) space.
    - This is the same as rotating by -angle using standard convention.
    
    Args:
        points_df: DataFrame with X, Y, Z columns (and optionally nx, ny, nz for normals)
        obb_info: dict from get_boundary_obb_transform
        
    Returns:
        DataFrame with transformed coordinates
    """
    from numpy import cos as np_cos
    from numpy import sin as np_sin
    from numpy import array as np_array
    
    if not obb_info["has_obb"]:
        return points_df
    
    angle = obb_info["angle"]
    center = obb_info["center"]
    
    # The OBB uses rotation matrix: [[cos(angle), sin(angle)], [-sin(angle), cos(angle)]]
    # This rotates from world to local (aligned) space
    c, s = np_cos(angle), np_sin(angle)
    R_to_local = np_array([[c, s], [-s, c]])
    
    # Transform XY coordinates: first center, then rotate to local
    xy = points_df[["X", "Y"]].values
    xy_centered = xy - center
    xy_rotated = (R_to_local @ xy_centered.T).T
    
    # Update dataframe
    transformed_df = points_df.copy()
    transformed_df["X"] = xy_rotated[:, 0]
    transformed_df["Y"] = xy_rotated[:, 1]
    # Z remains unchanged
    
    # Transform normals if present (only rotation, no translation)
    if "nx" in points_df.columns and "ny" in points_df.columns:
        nxy = points_df[["nx", "ny"]].values
        nxy_rotated = (R_to_local @ nxy.T).T
        transformed_df["nx"] = nxy_rotated[:, 0]
        transformed_df["ny"] = nxy_rotated[:, 1]
        # nz remains unchanged
    
    return transformed_df


def transform_vtk_to_obb(vtk_obj, obb_info, voxet_world_origin=None):
    """
    Transform a VTK object from axis-aligned (local) space back to OBB-oriented (world) space.
    
    The vtkContourFilter outputs surfaces using: origin + index * spacing
    but does NOT apply the direction matrix rotation. So the surface is at the
    correct translated position but not rotated.
    
    We need to rotate around the voxet's world origin point.
    
    Args:
        vtk_obj: VTK PolyData object (TriSurf, etc.)
        obb_info: dict from get_boundary_obb_transform
        voxet_world_origin: The origin of the voxet in world space (for rotation pivot)
        
    Returns:
        Transformed VTK object (modified in place)
    """
    from numpy import cos as np_cos
    from numpy import sin as np_sin
    from numpy import array as np_array
    from numpy import mean as np_mean
    
    if not obb_info["has_obb"]:
        return vtk_obj
    
    angle = obb_info["angle"]
    center = obb_info["center"]
    
    # Rotation matrix from local to world
    c, s = np_cos(angle), np_sin(angle)
    R_to_world = np_array([[c, -s], [s, c]])
    
    # Get points from VTK object
    points = vtk_obj.points
    if points is None or len(points) == 0:
        return vtk_obj
    
    xy = points[:, :2]
    
    # If voxet_world_origin is provided, use it as rotation pivot
    # Otherwise use the center from obb_info
    if voxet_world_origin is not None:
        pivot = np_array([voxet_world_origin[0], voxet_world_origin[1]])
    else:
        pivot = center
    
    # Rotate around the pivot point:
    # 1. Translate to pivot
    # 2. Rotate
    # 3. Translate back
    xy_centered = xy - pivot
    xy_rotated = (R_to_world @ xy_centered.T).T
    xy_final = xy_rotated + pivot
    
    # Update points in VTK object
    points[:, 0] = xy_final[:, 0]
    points[:, 1] = xy_final[:, 1]
    # Z remains unchanged
    
    vtk_obj.points = points
    
    return vtk_obj


def transform_voxet_to_obb(voxet, obb_info, original_origin, original_spacing, original_dimensions):
    """
    Transform a Voxet from axis-aligned space back to OBB-oriented space.
    This is more complex as voxets are structured grids.
    
    For voxets, we need to transform the origin and keep track of orientation.
    Note: VTK ImageData doesn't support arbitrary orientation, so for now
    we store the transformation and apply it when extracting surfaces.
    
    Args:
        voxet: Voxet object
        obb_info: dict from get_boundary_obb_transform
        original_origin: original origin before OBB alignment
        original_spacing: spacing values
        original_dimensions: dimension values
        
    Returns:
        Transformed Voxet with OBB metadata
    """
    from numpy import cos as np_cos
    from numpy import sin as np_sin
    from numpy import array as np_array
    from numpy import full as np_full
    from numpy import tile as np_tile
    
    if not obb_info["has_obb"]:
        return voxet
    
    angle = obb_info["angle"]
    center = obb_info["center"]
    
    # Store OBB transformation info as field data on the voxet
    n_points = voxet.points_number
    
    # Add obb_angle as point data
    voxet.set_point_data(
        data_key="obb_angle",
        attribute_matrix=np_full(n_points, angle, dtype=np_float32)
    )
    
    # Add obb_center as point data  
    voxet.set_point_data(
        data_key="obb_center",
        attribute_matrix=np_tile(center, (n_points, 1)).astype(np_float32)
    )
    
    return voxet


def get_aligned_bounds_from_obb(boundary_coll, boundary_uid, obb_info):
    """
    Get axis-aligned bounding box after transforming OBB boundary to local space.
    
    Uses the same rotation convention as transform_points_to_aligned:
    R_to_local = [[cos(angle), sin(angle)], [-sin(angle), cos(angle)]]
    
    Returns:
        tuple: (origin_x, origin_y, origin_z, max_x, max_y, max_z)
    """
    from numpy import min as np_min
    from numpy import max as np_max
    from numpy import cos as np_cos
    from numpy import sin as np_sin
    from numpy import array as np_array
    
    vtk_obj = boundary_coll.get_uid_vtk_obj(boundary_uid)
    points = vtk_obj.points
    
    if not obb_info["has_obb"]:
        # Return standard axis-aligned bounds
        bounds = vtk_obj.GetBounds()
        return bounds[0], bounds[2], bounds[4], bounds[1], bounds[3], bounds[5]
    
    angle = obb_info["angle"]
    center = obb_info["center"]
    
    # Use the same rotation matrix as in OBB computation: R_to_local
    c, s = np_cos(angle), np_sin(angle)
    R_to_local = np_array([[c, s], [-s, c]])
    
    # Transform XY coordinates to local (aligned) space
    xy = points[:, :2]
    xy_centered = xy - center
    xy_rotated = (R_to_local @ xy_centered.T).T
    
    # Get bounds in aligned space
    origin_x = np_min(xy_rotated[:, 0])
    origin_y = np_min(xy_rotated[:, 1])
    origin_z = np_min(points[:, 2])
    max_x = np_max(xy_rotated[:, 0])
    max_y = np_max(xy_rotated[:, 1])
    max_z = np_max(points[:, 2])
    
    return origin_x, origin_y, origin_z, max_x, max_y, max_z
    
    return origin_x, origin_y, origin_z, max_x, max_y, max_z


@freeze_gui_onoff
def interpolation_delaunay_2d(self):
    """The vtkDelaunay2D object takes vtkPointSet (or any of its subclasses) as input and
    generates a vtkPolyData on output - typically a triangle mesh if Alpha value is not defined.
    Select the whole line of two or more vtkPointSet entities and start the algorithm.
    """
    self.print_terminal("Delaunay2D: interpolation of Points, Lines and Surfaces")
    if self.shown_table != "tabGeology":
        self.print_terminal(" -- Only geological objects can be interpolated -- ")
        return
    # Check if some vtkPolyData is selected
    if not self.selected_uids:
        self.print_terminal(" -- No input data selected -- ")
        return
    else:
        # Deep copy list of selected uids needed otherwise problems
        # can arise if the main geology table is deselected while the dataframe is being built
        input_uids = deepcopy(self.selected_uids)
    for uid in input_uids:
        if (
            isinstance(self.geol_coll.get_uid_vtk_obj(uid), PolyLine)
            or isinstance(self.geol_coll.get_uid_vtk_obj(uid), XsPolyLine)
            or isinstance(self.geol_coll.get_uid_vtk_obj(uid), VertexSet)
            or isinstance(self.geol_coll.get_uid_vtk_obj(uid), XsVertexSet)
            or isinstance(self.geol_coll.get_uid_vtk_obj(uid), TriSurf)
        ):
            pass
        else:
            self.print_terminal(" -- Error input type -- ")
            return
    # Create deepcopy of the geological entity dictionary.
    surf_dict = deepcopy(self.geol_coll.entity_dict)
    input_dict = {
        "name": [
            "TriSurf name: ",
            self.geol_coll.get_uid_name(input_uids[0]) + "_delaunay2d",
        ],
        "role": [
            "Role: ",
            self.geol_coll.valid_roles,
            self.geol_coll.get_uid_role(input_uids[0]),
        ],
        "feature": [
            "Feature: ",
            self.geol_coll.get_uid_feature(input_uids[0]),
        ],
        "scenario": ["Scenario: ", self.geol_coll.get_uid_scenario(input_uids[0])],
    }
    surf_dict_updt = multiple_input_dialog(
        title="New Delaunay 2D interpolation", input_dict=input_dict
    )
    # Check if the output of the widget is empty or not. If the Cancel button was clicked, the tool quits
    if surf_dict_updt is None:
        return
    # Ask for the Tolerance and Alpha values. Tolerance controls discarding of closely spaced points.
    # Alpha controls the 'size' of output primitivies - a 0 Alpha Value outputs a triangle mesh.
    tolerance_value = input_one_value_dialog(
        title="Delaunay2D Parameters",
        label="Tolerance Value. Discard points " "closer than the specified value",
        default_value=0,
    )
    if tolerance_value is None:
        tolerance_value = 0
    alpha_value = input_one_value_dialog(
        title="Delaunay2D Parameters",
        label="Alpha Value. Discard triangles not contained "
        "in a sphere of radius set "
        "by the specified value ",
        default_value=0,
    )
    if alpha_value is None:
        alpha_value = 0
    # Getting the values that have been typed by the user through the multiple input widget
    for key in surf_dict_updt:
        surf_dict[key] = surf_dict_updt[key]
    surf_dict["topology"] = "TriSurf"
    surf_dict["vtk_obj"] = TriSurf()
    # Create a vtkAppendPolyData filter to merge all input vtk objects. Else, it does not seem possible to
    # input multiple objects into vtkDelaunay2D
    vtkappend = vtkAppendPolyData()
    for uid in input_uids:
        vtkappend.AddInputData(self.geol_coll.get_uid_vtk_obj(uid))
    vtkappend.Update()

    bounding_box = vtkBoundingBox()
    bounding_box.ComputeBounds(vtkappend.GetOutput().GetPoints())
    diagonal = bounding_box.GetDiagonalLength()
    tolerance_value_bounding = tolerance_value / diagonal
    # Create a new instance of the interpolation class
    delaunay_2d = vtkDelaunay2D()
    delaunay_2d.SetInputDataObject(vtkappend.GetOutput())
    delaunay_2d.SetProjectionPlaneMode(1)
    trans = delaunay_2d.ComputeBestFittingPlane(vtkappend.GetOutput())
    delaunay_2d.SetTransform(trans)
    delaunay_2d.SetTolerance(tolerance_value_bounding)
    delaunay_2d.SetAlpha(alpha_value)

    delaunay_2d.Update()  # executes the interpolation
    # ShallowCopy is the way to copy the new interpolated surface into the TriSurf instance created at the beginning
    surf_dict["vtk_obj"].ShallowCopy(delaunay_2d.GetOutput())
    surf_dict["vtk_obj"].Modified()
    # Add new entity from surf_dict. Function add_entity_from_dict creates a new uid
    if surf_dict["vtk_obj"].points_number > 0:
        self.geol_coll.add_entity_from_dict(surf_dict)
    else:
        self.print_terminal(" -- empty object -- ")


@freeze_gui_onoff
def poisson_interpolation(self):
    """vtkSurfaceReconstructionFilter can be used to reconstruct surfaces from point clouds. Input is a vtkDataSet
    defining points assumed to lie on the surface of a 3D object."""
    self.print_terminal(
        "Interpolation from point cloud: build surface from interpolation"
    )
    if self.shown_table != "tabGeology":
        self.print_terminal(" -- Only geological objects can be interpolated -- ")
        return
    # Check if some vtkPolyData is selected
    if not self.selected_uids:
        self.print_terminal("No input data selected.")
        return
    else:
        # Deep copy list of selected uids needed otherwise problems can arise if the main geology table is deseselcted while the dataframe is being built
        input_uids = deepcopy(self.selected_uids)
    for uid in input_uids:
        if (
            isinstance(self.geol_coll.get_uid_vtk_obj(uid), PolyLine)
            or isinstance(self.geol_coll.get_uid_vtk_obj(uid), XsPolyLine)
            or isinstance(self.geol_coll.get_uid_vtk_obj(uid), VertexSet)
            or isinstance(self.geol_coll.get_uid_vtk_obj(uid), XsVertexSet)
            or isinstance(self.geol_coll.get_uid_vtk_obj(uid), TriSurf)
        ):
            pass
        else:
            self.print_terminal(" -- Error input type -- ")
            return
    # Create deepcopy of the geological entity dictionary.
    surf_dict = deepcopy(self.geol_coll.entity_dict)
    input_dict = {
        "name": [
            "TriSurf name: ",
            self.geol_coll.get_uid_name(input_uids[0]) + "_cloud",
        ],
        "role": [
            "Role: ",
            self.parent.geol_coll.valid_roles,
        ],
        "feature": [
            "Feature: ",
            self.geol_coll.get_uid_feature(input_uids[0]),
        ],
        "scenario": ["Scenario: ", self.geol_coll.get_uid_scenario(input_uids[0])],
    }
    surf_dict_updt = multiple_input_dialog(
        title="Surface interpolation from point cloud", input_dict=input_dict
    )
    # Check if the output of the widget is empty or not. If the Cancel button was clicked, the tool quits
    if surf_dict_updt is None:
        return
    # Getting the values that have been typed by the user through the multiple input widget
    for key in surf_dict_updt:
        surf_dict[key] = surf_dict_updt[key]
    surf_dict["topology"] = "TriSurf"
    surf_dict["vtk_obj"] = TriSurf()
    # Create a new instance of the interpolation class
    surf_from_points = vtkSurfaceReconstructionFilter()
    sample_spacing = input_one_value_dialog(
        title="Surface interpolation from point cloud",
        label="Sample Spacing",
        default_value=-1.0,
    )
    if sample_spacing is None:
        pass
    else:
        surf_from_points.SetSampleSpacing(sample_spacing)
    neighborhood_size = input_one_value_dialog(
        title="Surface interpolation from point cloud",
        label="Neighborhood Size",
        default_value=20,
    )
    if neighborhood_size is None:
        pass
    else:
        surf_from_points.SetNeighborhoodSize(int(neighborhood_size))
    # Create a vtkAppendPolyData filter to merge all input vtk objects.
    vtkappend = vtkAppendPolyData()
    for uid in input_uids:
        if (
            self.geol_coll.get_uid_topology(input_uids[0]) == "XsPolyLine"
            or self.geol_coll.get_uid_topology(input_uids[0]) == "PolyLine"
            or self.geol_coll.get_uid_topology(input_uids[0]) == "TriSurf"
        ):
            # Extract points from vtkpolydata
            point_coord = self.geol_coll.get_uid_vtk_obj(uid).points
            points = vtkPoints()
            x = 0
            for row in point_coord:
                points.InsertPoint(
                    x, point_coord[x, 0], point_coord[x, 1], point_coord[x, 2]
                )
                x += 1
            polydata = vtkPolyData()
            polydata.SetPoints(points)
            vtkappend.AddInputData(polydata)
        elif self.geol_coll.get_uid_topology(input_uids[0]) == "VertexSet":
            vtkappend.AddInputData(self.geol_coll.get_uid_vtk_obj(uid))
    vtkappend.Update()
    # The created vtkPolyData is used as the input for vtkSurfaceReconstructionFilter
    surf_from_points.SetInputDataObject(vtkappend.GetOutput())
    surf_from_points.Update()  # executes the interpolation. Output is vtkImageData
    # Contour the grid at zero to extract the surface
    contour_surface = vtkContourFilter()
    contour_surface.SetInputData(surf_from_points.GetOutput())
    contour_surface.SetValue(0, 0.0)
    contour_surface.Update()
    # ShallowCopy is the way to copy the new interpolated surface into the TriSurf instance created at the beginning
    surf_dict["vtk_obj"].ShallowCopy(contour_surface.GetOutput())
    surf_dict["vtk_obj"].Modified()
    # Add new entity from surf_dict. Function add_entity_from_dict creates a new uid
    if surf_dict["vtk_obj"].points_number > 0:
        self.geol_coll.add_entity_from_dict(surf_dict)
    else:
        self.print_terminal(" -- empty object -- ")


@freeze_gui_onoff
def implicit_model_loop_structural(self):
    """Function to call LoopStructural's implicit modelling algorithms.
    Input Data is organized as the following columns:
    X - x component of the cartesian coordinates
    Y - y component of the cartesian coordinates
    Z - z component of the cartesian coordinates
    feature_name - unique name of the geological feature being modelled - this is not the feature generally defined in geological_collection.py, but the sequence defined in legend_manager.py
    val - value observations of the scalar field - this is the time defined in legend_manager.py
    interface - unique identifier for an interface containing similar scalar field values
    nx - x component of the gradient norm
    ny - y component of the gradient norm
    nz - z component of the gradient norm
    gx - x component of a gradient constraint
    gy - y component of a gradient constraint
    gz - z component of a gradient constraint
    tx - x component of a gradient tangent constraint
    ty - y component of a gradient tangent constraint
    tz - z component of a gradient tangent constraint
    coord - coordinate of the structural frame data point is used for ???
    """
    self.print_terminal(
        "LoopStructural implicit geomodeller\ngithub.com/Loop3D/LoopStructural"
    )
    if self.shown_table != "tabGeology":
        self.print_terminal(" -- Only geological objects can be interpolated -- ")
        return
    # Check if some vtkPolyData is selected
    if not self.selected_uids:
        self.print_terminal("No input data selected.")
        return
    else:
        # Deep copy list of selected uids needed otherwise problems can arise if the main geology table is deseselcted while the dataframe is being built
        input_uids = deepcopy(self.selected_uids)
    "Dictionary used to define the fields of the Loop input data Pandas dataframe."
    loop_input_dict = {
        "X": None,
        "Y": None,
        "Z": None,
        "feature_name": None,
        "val": None,
        "interface": None,
        "nx": None,
        "ny": None,
        "nz": None,
        "gx": None,
        "gy": None,
        "gz": None,
        "tx": None,
        "ty": None,
        "tz": None,
        "coord": None,
    }
    # Create empty dataframe to collect all input data.
    self.print_terminal("-> creating input dataframe...")
    tic(parent=self)
    all_input_data_df = pd_DataFrame(columns=list(loop_input_dict.keys()))
    # For every selected item extract interesting data: XYZ, feature_name, val, etc.
    prgs_bar = progress_dialog(
        max_value=len(input_uids),
        title_txt="Input dataframe",
        label_txt="Adding geological objects to input dataframe...",
        cancel_txt=None,
        parent=self,
    )
    for uid in input_uids:
        # Create empty dataframe to collect input data for this object.
        entity_input_data_df = pd_DataFrame(columns=list(loop_input_dict.keys()))
        # XYZ data for every selected entity.
        # Adding all columns at once is about 10% faster than adding them separately, but still slow.
        entity_input_data_df[["X", "Y", "Z"]] = self.geol_coll.get_uid_vtk_obj(
            uid
        ).points
        if "Normals" in self.geol_coll.get_uid_properties_names(uid):
            entity_input_data_df[["nx", "ny", "nz"]] = self.geol_coll.get_uid_property(
                uid=uid, property_name="Normals"
            )
        # feature_name value
        featname_single = self.geol_coll.legend_df.loc[
            (self.geol_coll.legend_df["role"] == self.geol_coll.get_uid_role(uid))
            & (
                self.geol_coll.legend_df["feature"]
                == self.geol_coll.get_uid_feature(uid)
            )
            & (
                self.geol_coll.legend_df["scenario"]
                == self.geol_coll.get_uid_scenario(uid)
            ),
            "sequence",
        ].values[0]
        entity_input_data_df["feature_name"] = featname_single
        # val value
        val_single = self.geol_coll.legend_df.loc[
            (self.geol_coll.legend_df["role"] == self.geol_coll.get_uid_role(uid))
            & (
                self.geol_coll.legend_df["feature"]
                == self.geol_coll.get_uid_feature(uid)
            )
            & (
                self.geol_coll.legend_df["scenario"]
                == self.geol_coll.get_uid_scenario(uid)
            ),
            "time",
        ].values[0]
        if val_single == -999999.0:
            val_single = float("nan")
        entity_input_data_df["val"] = val_single
        # nx, ny and nz: TO BE IMPLEMENTED
        # gx, gy and gz: TO BE IMPLEMENTED
        # Append dataframe for this input entity to the general input dataframe.
        # Old Pandas <= 1.5.3
        # all_input_data_df = all_input_data_df.append(
        #     entity_input_data_df, ignore_index=True
        # )
        # New Pandas >= 2.0.0
        all_input_data_df = pd_concat(
            [all_input_data_df, entity_input_data_df], ignore_index=True
        )
        prgs_bar.add_one()
    toc(parent=self)
    prgs_bar.close()
    # Drop columns with no valid value (i.e. all NaNs).
    self.print_terminal("-> drop empty columns...")
    tic(parent=self)
    all_input_data_df.dropna(axis=1, how="all", inplace=True)
    toc(parent=self)
    self.print_terminal(f"all_input_data_df:\n{all_input_data_df}")
    # Ask for bounding box for the model
    input_dict = {
        "boundary": ["Boundary: ", self.boundary_coll.get_names],
        "method": ["Interpolation method: ", ["PLI", "FDI", "surfe"]],
    }
    options_dict = multiple_input_dialog(
        title="Implicit Modelling - LoopStructural algorithms", input_dict=input_dict
    )
    if options_dict is None:
        options_dict["boundary"] = self.boundary_coll.get_names[0]
        options_dict["method"] = "PLI"
    boundary_uid = self.boundary_coll.df.loc[
        self.boundary_coll.df["name"] == options_dict["boundary"], "uid"
    ].values[0]
    
    # Automatically check if boundary has OBB transformation
    obb_info = get_boundary_obb_transform(self.boundary_coll, boundary_uid)
    use_obb_alignment = obb_info["has_obb"]
    
    if use_obb_alignment:
        self.print_terminal(f"-> OBB boundary detected. Rotation angle: {np_around(obb_info['angle'] * 180 / np_pi, 2)} degrees")
        self.print_terminal("-> Transforming data to axis-aligned coordinate system...")
        # Get aligned bounds from OBB boundary
        origin_x, origin_y, origin_z_temp, maximum_x, maximum_y, maximum_z_temp = get_aligned_bounds_from_obb(
            self.boundary_coll, boundary_uid, obb_info
        )
        # Transform input data to aligned coordinates
        all_input_data_df = transform_points_to_aligned(all_input_data_df, obb_info)
        self.print_terminal(f"-> Data transformed. New aligned bounds: X[{origin_x:.2f}, {maximum_x:.2f}], Y[{origin_y:.2f}, {maximum_y:.2f}]")
    else:
        origin_x = self.boundary_coll.get_uid_vtk_obj(boundary_uid).GetBounds()[0]
        origin_y = self.boundary_coll.get_uid_vtk_obj(boundary_uid).GetBounds()[2]
        maximum_x = self.boundary_coll.get_uid_vtk_obj(boundary_uid).GetBounds()[1]
        maximum_y = self.boundary_coll.get_uid_vtk_obj(boundary_uid).GetBounds()[3]
    if (
        self.boundary_coll.get_uid_vtk_obj(boundary_uid).GetBounds()[4]
        == self.boundary_coll.get_uid_vtk_obj(boundary_uid).GetBounds()[5]
    ):
        # Boundary with no vertical dimension has been chosen. A dialog that asks for max and min Z is needed
        vertical_extension_in = {
            "message": [
                "Model vertical extension",
                "Define MAX and MIN vertical extension of the 3D implicit model.",
                "QLabel",
            ],
            "top": ["Insert top", 1000.0, "QLineEdit"],
            "bottom": ["Insert bottom", -1000.0, "QLineEdit"],
        }
        vertical_extension_updt = general_input_dialog(
            title="Implicit Modelling - LoopStructural algorithms",
            input_dict=vertical_extension_in,
        )
        if vertical_extension_updt["top"] is None:
            vertical_extension_updt["top"] = 1000.0
        if vertical_extension_updt["bottom"] is None:
            vertical_extension_updt["bottom"] = -1000.0
        if vertical_extension_updt["bottom"] > vertical_extension_updt["top"]:
            # Manages the case where mistakenly bottom > top
            origin_z = vertical_extension_updt["top"]
            maximum_z = vertical_extension_updt["bottom"]
        elif vertical_extension_updt["bottom"] == vertical_extension_updt["top"]:
            origin_z = vertical_extension_updt["bottom"] - 25.0  # arbitrary value
            maximum_z = vertical_extension_updt["bottom"] + 25.0  # arbitrary value
        else:
            origin_z = vertical_extension_updt["bottom"]
            maximum_z = vertical_extension_updt["top"]
    else:
        # Collect information on the vertical extension of the model from the Boundary vtk obj
        origin_z = self.boundary_coll.get_uid_vtk_obj(boundary_uid).GetBounds()[4]
        maximum_z = self.boundary_coll.get_uid_vtk_obj(boundary_uid).GetBounds()[5]
    edge_x = maximum_x - origin_x
    edge_y = maximum_y - origin_y
    edge_z = maximum_z - origin_z
    # Define origin and maximum extension of modelling domain
    origin = [origin_x, origin_y, origin_z]
    maximum = [maximum_x, maximum_y, maximum_z]
    self.print_terminal(f"origin: {origin}")
    self.print_terminal(f"origin: {maximum}")
    # Check if Input Data and Bounding Box overlaps. If so, gives warning and exists the tool.
    if (
        (all_input_data_df["X"].min() > maximum_x)
        or (all_input_data_df["X"].max() < origin_x)
        or (all_input_data_df["Y"].min() > maximum_y)
        or (all_input_data_df["Y"].max() < origin_y)
        or (all_input_data_df["Z"].min() > maximum_z)
        or (all_input_data_df["Z"].max() < origin_z)
    ):
        self.print_terminal("Exit tool: Bounding Box does not intersect input data")
        return
    default_spacing = np_cbrt(
        edge_x * edge_y * edge_z / (50 * 50 * 25)
    )  # default dimension in Loop is 50 x 50 x 25
    target_spacing = input_one_value_dialog(
        title="Implicit Modelling - LoopStructural algorithms",
        label="Grid target spacing in model units\n (yields a 62500 cells model)",
        default_value=default_spacing,
    )
    if target_spacing is None or target_spacing <= 0:
        target_spacing = default_spacing
    dimension_x = int(np_around(edge_x / target_spacing))
    if dimension_x == 0:
        dimension_x = 1
    dimension_y = int(np_around(edge_y / target_spacing))
    if dimension_y == 0:
        dimension_y = 1
    dimension_z = int(np_around(edge_z / target_spacing))
    if dimension_z == 0:
        dimension_z = 1
    dimensions = [dimension_x, dimension_y, dimension_z]
    spacing_x = edge_x / dimension_x
    spacing_y = edge_y / dimension_y
    spacing_z = edge_z / dimension_z
    spacing = [spacing_x, spacing_y, spacing_z]
    self.print_terminal(f"dimensions: {dimensions}")
    self.print_terminal(f"spacing: {spacing}")
    # Create model as instance of Loop GeologicalModel with limits given by origin and maximum.
    # Keep rescale=True (default) for performance and precision.
    # THIS SHOULD BE CHANGED IN FUTURE TO BETTER DEAL WITH IRREGULARLY DISTRIBUTED INPUT DATA.
    # * ``interpolatortype`` - we can either use a PiecewiseLinearInterpolator ``PLI``, a FiniteDifferenceInterpolator ``FDI`` or a radial basis interpolator ``surfe``
    # * ``nelements - int`` is the how many elements are used to discretize the resulting solution
    # * ``buffer - float`` buffer percentage around the model area
    # * ``solver`` - the algorithm to solve the least squares problem e.g. ``lu`` for lower upper decomposition, ``cg`` for conjugate gradient, ``pyamg`` for an algorithmic multigrid solver
    # * ``damp - bool`` - whether to add a small number to the diagonal of the interpolation matrix for discrete interpolators - this can help speed up the solver and makes the solution more stable for some interpolators
    self.print_terminal("-> create model...")
    tic(parent=self)
    model = GeologicalModel(origin, maximum)
    toc(parent=self)
    # Link the input data dataframe to the model.
    self.print_terminal("-> set_model_data...")
    tic(parent=self)
    model.set_model_data(all_input_data_df)
    toc(parent=self)
    # Add a foliation to the model
    self.print_terminal("-> create_and_add_foliation...")
    tic(parent=self)
    # interpolator_type can be 'PLI', 'FDI' or 'surfe'
    model.create_and_add_foliation(
        "strati_0",
        interpolator_type=options_dict["method"],
        nelements=(dimensions[0] * dimensions[1] * dimensions[2]),
    )
    # In version 1.1+ the implicit function representing a geological feature does not have to be solved to generate the model object.
    # The scalar field is solved on demand when the geological features are evaluated. This means that parts of the geological model
    # can be modified and only the older (features lower in the feature list) are updated.
    # All features in the model can be updated with model.update(verbose=True).
    # model.update(verbose=True)  # This will solve the implicit function for all features in the model and provide a progress bar -- causes crash
    # A GeologicalFeature can be extracted from the model either by name...
    # my_feature = model[feature_name_value]  # useful?
    # A regular grid inside the model bounding box can be retrieved in the following way:
    # - nsteps defines how many points in x, y and z
    # - shuffle defines whether the points should be ordered by axis x, y, z (False?) or random (True?).
    # - rescale defines whether the returned points should be in model coordinates or real world coordinates.
    # Set calculation grid resolution. Default resolution is set as to obtain a model close to 10000 cells.
    # FOR THE FUTURE: anisotropic resolution?
    # rescale is True by default
    regular_grid = model.regular_grid(nsteps=dimensions, shuffle=False, rescale=False)
    toc(parent=self)
    # Evaluate scalar field.#
    self.print_terminal("-> evaluate_feature_value...")
    tic(parent=self)
    scalar_field = model.evaluate_feature_value("strati_0", regular_grid, scale=False)
    scalar_field = scalar_field.reshape((dimension_x, dimension_y, dimension_z))
    # OLD ----------------
    # VTK image data is ordered (z,y,x) in memory, while the Loop Structural output
    # Numpy array is ordered as regular_grid, so (x,y,-z). See explanations on VTK here:
    # https://discourse.vtk.org/t/numpy-tensor-to-vtkimagedata/5154/3
    # https://discourse.vtk.org/t/the-direction-of-vtkimagedata-make-something-wrong/4997
    # scalar_field = scalar_field[:, :, ::-1]
    # scalar_field = np_flip(scalar_field, 2)
    # OLD ----------------
    # NEW ----------------
    # It looks like that the Numpy output from LoopStructural now is
    # ordered as (x,y,z), so inverting the 'z' is no more required.
    # NEW ----------------
    scalar_field = scalar_field.transpose(2, 1, 0)
    scalar_field = scalar_field.ravel()  # flatten returns a copy
    # Evaluate scalar field gradient.
    # print("-> evaluate_feature_gradient...")
    # scalar_field_gradient = model.evaluate_feature_gradient("strati_0", regular_grid, scale=False)
    toc(parent=self)
    # Create deepcopy of the Mesh3D entity dictionary.
    self.print_terminal("-> create Voxet...")
    tic(parent=self)
    voxet_dict = deepcopy(self.mesh3d_coll.entity_dict)
    # Get output Voxet name.
    model_name = input_text_dialog(
        title="Implicit Modelling - LoopStructural algorithms",
        label="Name of the output Voxet",
        default_text="Loop_model",
    )
    if model_name is None:
        model_name = "Loop_model"
    # print(model_name)
    voxet_dict["name"] = model_name
    voxet_dict["topology"] = "Voxet"
    voxet_dict["properties_names"] = ["strati_0"]
    voxet_dict["properties_components"] = [1]
    # Create new instance of Voxet() class
    voxet_dict["vtk_obj"] = Voxet()
    
    # Calculate origin in aligned space (cell centers)
    aligned_origin = [
        origin_x + spacing_x / 2,
        origin_y + spacing_y / 2,
        origin_z + spacing_z / 2,
    ]
    
    # If OBB alignment was used, transform Voxet back to world space
    if use_obb_alignment:
        from numpy import array as np_array
        from vtk import vtkMatrix3x3
        
        angle = obb_info["angle"]
        center = obb_info["center"]
        
        # Create the inverse rotation matrix (from local to world)
        # R_to_world = [[cos(angle), -sin(angle), 0], [sin(angle), cos(angle), 0], [0, 0, 1]]
        c, s = np_cos(angle), np_sin(angle)
        
        # Transform the origin from aligned space to world space
        origin_xy = np_array([aligned_origin[0], aligned_origin[1]])
        R_to_world_2d = np_array([[c, -s], [s, c]])
        origin_world_xy = (R_to_world_2d @ origin_xy) + center
        
        world_origin = [
            origin_world_xy[0],
            origin_world_xy[1],
            aligned_origin[2]  # Z unchanged
        ]
        
        # Set the direction matrix for the Voxet (3x3 rotation matrix)
        direction_matrix = vtkMatrix3x3()
        direction_matrix.SetElement(0, 0, c)
        direction_matrix.SetElement(0, 1, -s)
        direction_matrix.SetElement(0, 2, 0)
        direction_matrix.SetElement(1, 0, s)
        direction_matrix.SetElement(1, 1, c)
        direction_matrix.SetElement(1, 2, 0)
        direction_matrix.SetElement(2, 0, 0)
        direction_matrix.SetElement(2, 1, 0)
        direction_matrix.SetElement(2, 2, 1)
        
        voxet_dict["vtk_obj"].origin = world_origin
        voxet_dict["vtk_obj"].direction_matrix = direction_matrix
        # Store world_origin for surface transformation later
        voxet_world_origin = world_origin
        self.print_terminal(f"-> Voxet transformed to OBB orientation")
    else:
        voxet_dict["vtk_obj"].origin = aligned_origin
        voxet_world_origin = None
    
    voxet_dict["vtk_obj"].dimensions = dimensions
    voxet_dict["vtk_obj"].spacing = spacing
    # print(voxet_dict)
    toc(parent=self)
    # Pass calculated values of the LoopStructural model to the Voxet, as scalar fields
    self.print_terminal("-> populate Voxet...")
    tic(parent=self)
    voxet_dict["vtk_obj"].set_point_data(
        data_key="strati_0", attribute_matrix=scalar_field
    )
    # Create new entity in mesh3d_coll from the populated voxet dictionary
    if voxet_dict["vtk_obj"].points_number > 0:
        self.mesh3d_coll.add_entity_from_dict(voxet_dict)
    else:
        self.print_terminal(" -- empty object -- ")
        return
    voxet_dict["vtk_obj"].Modified()
    toc(parent=self)
    # Extract isosurfaces with vtkFlyingEdges3D. Documentation in:
    # https://vtk.org/doc/nightly/html/classvtkFlyingEdges3D.html
    # https://python.hotexamples.com/examples/vtk/-/vtkFlyingEdges3D/python-vtkflyingedges3d-function-examples.html
    self.print_terminal("-> extract isosurfaces...")
    tic(parent=self)
    for value in all_input_data_df["val"].dropna().unique():
        value = float(value)
        voxet_dict["vtk_obj"].GetPointData().SetActiveScalars("strati_0")
        self.print_terminal(f"-> extract iso-surface at value = {value}")
        # Get metadata of first geological feature of this time
        role = self.geol_coll.legend_df.loc[
            self.geol_coll.legend_df["time"] == value, "role"
        ].values[0]
        feature = self.geol_coll.legend_df.loc[
            self.geol_coll.legend_df["time"] == value, "feature"
        ].values[0]
        scenario = self.geol_coll.legend_df.loc[
            self.geol_coll.legend_df["time"] == value, "scenario"
        ].values[0]
        # Iso-surface algorithm
        iso_surface = vtkContourFilter()
        # iso_surface = vtkFlyingEdges3D()
        # iso_surface = vtkMarchingCubes()
        iso_surface.SetInputData(voxet_dict["vtk_obj"])
        iso_surface.ComputeScalarsOn()
        iso_surface.ComputeGradientsOn()
        iso_surface.SetArrayComponent(0)
        iso_surface.GenerateTrianglesOn()
        iso_surface.UseScalarTreeOn()
        iso_surface.SetValue(0, value)
        iso_surface.Update()
        # Create new TriSurf and populate with iso-surface
        surf_dict = deepcopy(self.geol_coll.entity_dict)
        surf_dict["name"] = feature + "_from_" + model_name
        surf_dict["topology"] = "TriSurf"
        surf_dict["role"] = role
        surf_dict["feature"] = feature
        surf_dict["scenario"] = scenario
        surf_dict["vtk_obj"] = TriSurf()
        surf_dict["vtk_obj"].ShallowCopy(iso_surface.GetOutput())
        
        # vtkContourFilter does NOT apply the direction matrix to its output,
        # so we need to manually transform the isosurface from aligned space to OBB world space
        if use_obb_alignment:
            surf_dict["vtk_obj"] = transform_vtk_to_obb(surf_dict["vtk_obj"], obb_info, voxet_world_origin)
            self.print_terminal(f"-> iso-surface transformed to OBB coordinate system")
        
        surf_dict["vtk_obj"].Modified()
        if isinstance(surf_dict["vtk_obj"].points, np_ndarray):
            if len(surf_dict["vtk_obj"].points) > 0:
                # Add entity to geological collection only if it is not empty
                self.geol_coll.add_entity_from_dict(surf_dict)
                self.print_terminal(
                    f"-> iso-surface at value = {value} has been created"
                )
            else:
                self.print_terminal(" -- empty object -- ")
    toc(parent=self)
    self.print_terminal("Loop interpolation completed.")


@freeze_gui_onoff
def surface_smoothing(
    self, mode=0, convergence_value=1, boundary_smoothing=False, edge_smoothing=False
):
    """Smoothing tools adjust the positions of points to reduce the noise content in the surface."""
    self.print_terminal("Surface Smoothing: reduce the noise of the surface")
    if self.shown_table != "tabGeology":
        self.print_terminal(" -- Only geological objects can be modified -- ")
        return
    # Check if some vtkPolyData is selected
    if not self.selected_uids:
        self.print_terminal("No input data selected.")
        return
    else:
        # Deep copy list of selected uids needed otherwise problems can arise if the main geology table is deseselcted while the dataframe is being built
        input_uids = deepcopy(self.selected_uids)
    for uid in input_uids:
        if isinstance(self.geol_coll.get_uid_vtk_obj(uid), TriSurf):
            smoother = vtkSmoothPolyDataFilter()
            smoother.SetInputData(self.geol_coll.get_uid_vtk_obj(uid))
            if convergence_value is None:
                convergence_value = 1
            smoother.SetConvergence(float(convergence_value))
            smoother.SetBoundarySmoothing(boundary_smoothing)
            smoother.SetFeatureEdgeSmoothing(edge_smoothing)
            smoother.Update()
            if mode:
                return smoother.GetOutput()
            else:
                # Create deepcopy of the geological entity dictionary.
                surf_dict = deepcopy(self.geol_coll.entity_dict)
                surf_dict["name"] = self.geol_coll.get_uid_name(uid) + "_smoothed"
                surf_dict["feature"] = self.geol_coll.get_uid_feature(uid)
                surf_dict["scenario"] = self.geol_coll.get_uid_scenario(uid)
                surf_dict["role"] = self.geol_coll.get_uid_role(uid)
                surf_dict["topology"] = "TriSurf"
                surf_dict["vtk_obj"] = TriSurf()
                surf_dict["vtk_obj"].ShallowCopy(smoother.GetOutput())
                surf_dict["vtk_obj"].Modified()

                if surf_dict["vtk_obj"].points_number > 0:
                    self.geol_coll.add_entity_from_dict(surf_dict)
                else:
                    self.print_terminal(" -- empty object -- ")

        else:
            self.print_terminal(" -- Error input type: only TriSurf type -- ")
            return
    # Create deepcopy of the geological entity dictionary.
    # surf_dict = deepcopy(self.geol_coll.entity_dict)
    # input_dict = {'name': ['TriSurf name: ', self.geol_coll.get_uid_name(input_uids[0]) + '_smooth'], 'role': ['Role: ', self.parent.geol_coll.valid_roles], 'feature': ['Feature: ', self.geol_coll.get_uid_feature(input_uids[0])], 'scenario': ['Scenario: ', self.geol_coll.get_uid_scenario(input_uids[0])]}
    # surf_dict_updt = multiple_input_dialog(title='Surface smoothing', input_dict=input_dict)
    # Check if the output of the widget is empty or not. If the Cancel button was clicked, the tool quits
    # if surf_dict_updt is None:
    #     return
    # Getting the values that have been typed by the user through the multiple input widget
    # for key in surf_dict_updt:
    #     surf_dict[key] = surf_dict_updt[key]
    # surf_dict['topology'] = 'TriSurf'
    # surf_dict['vtk_obj'] = TriSurf()
    # Create a new instance of the interpolation class
    # smoother = vtkSmoothPolyDataFilter()
    # smoother.SetInputData(self.geol_coll.get_uid_vtk_obj(input_uids[0]))
    # Ask for the Convergence value (smaller numbers result in more smoothing iterations).
    # convergence_value = input_one_value_dialog(title='Surface smoothing parameters', label='Convergence Value (small values result in more smoothing)', default_value=1)
    # if convergence_value is None:
    #     convergence_value = 1
    # smoother.SetConvergence(convergence_value)
    # Ask for BoundarySmoothing (smoothing of vertices on the boundary of the mesh) and FeatureEdgeSmoothing
    # (smoothing along sharp interior edges).
    # boundary_smoothing = input_text_dialog(title='Surface smoothing parameters', label='Boundary Smoothing (ON/OFF)', default_text='OFF')
    # if boundary_smoothing is None:
    #     pass
    # elif boundary_smoothing == 'ON' or boundary_smoothing == 'on':
    #     smoother.SetBoundarySmoothing(True)
    # elif boundary_smoothing == 'OFF' or boundary_smoothing == 'off':
    #     smoother.SetBoundarySmoothing(False)
    # edge_smooth_switch = input_text_dialog(title='Surface smoothing parameters', label='Feature Edge Smoothing (ON/OFF)', default_text='OFF')
    # if edge_smooth_switch is None:
    #     pass
    # elif edge_smooth_switch == 'ON' or edge_smooth_switch == 'on':
    #     smoother.SetBoundarySmoothing(True)
    # elif edge_smooth_switch == 'OFF' or edge_smooth_switch == 'off':
    #     smoother.SetFeatureEdgeSmoothing(False)
    # smoother.Update()
    # ShallowCopy is the way to copy the new interpolated surface into the TriSurf instance created at the beginning
    # surf_dict['vtk_obj'].ShallowCopy(smoother.GetOutput())
    # surf_dict['vtk_obj'].Modified()
    # Add new entity from surf_dict. Function add_entity_from_dict creates a new uid
    # if surf_dict['vtk_obj'].points_number > 0:
    #     self.geol_coll.add_entity_from_dict(surf_dict)
    # else:
    #     print(" -- empty object -- ")


@freeze_gui_onoff
def linear_extrusion(self):
    """vtkLinearExtrusionFilter sweeps the generating primitives along a straight line path. This tool is here
    used to create fault surfaces from faults traces."""
    self.print_terminal(
        "Linear extrusion: create surface by projecting target linear object along a straight line path"
    )
    if self.shown_table != "tabGeology":
        self.print_terminal(" -- Only geological objects can be projected -- ")
        return
    # Check if some vtkPolyData is selected
    if not self.selected_uids:
        self.print_terminal("No input data selected.")
        return
    else:
        # Deep copy list of selected uids needed otherwise problems can arise if the main geology table is deselected while the dataframe is being built
        input_uids = deepcopy(self.selected_uids)
    for uid in input_uids:
        if isinstance(self.geol_coll.get_uid_vtk_obj(uid), PolyLine) or isinstance(
            self.geol_coll.get_uid_vtk_obj(uid), XsPolyLine
        ):
            pass
        else:
            self.print_terminal(
                " -- Error input type: only PolyLine and XsPolyLine type -- "
            )
            return
    surf_dict = _build_extrusion_output_dict(
        self=self,
        input_uid=input_uids[0],
        title="Linear Extrusion",
        default_suffix="_extruded",
    )
    if surf_dict is None:
        return
    extrusion_parameters = _ask_linear_extrusion_parameters(
        self=self, title="Linear Extrusion"
    )
    if extrusion_parameters is None:
        return
    trend, plunge, vertical_extrusion = extrusion_parameters
    total_extrusion = vertical_extrusion["top"] - vertical_extrusion["bottom"]
    linear_extrusion = vtkLinearExtrusionFilter()
    linear_extrusion.CappingOn()  # yes or no?
    linear_extrusion.SetExtrusionTypeToVectorExtrusion()
    x_vector, y_vector, z_vector = _get_linear_extrusion_vector(trend, plunge)
    linear_extrusion.SetVector(
        x_vector, y_vector, z_vector
    )  # double,double,double format
    linear_extrusion.SetScaleFactor(total_extrusion)  # double format
    linear_extrusion.SetInputData(self.geol_coll.get_uid_vtk_obj(input_uids[0]))
    linear_extrusion.Update()

    #  The output of vtkLinearExtrusionFilter() are triangle strips we convert them to triangles with vtkTriangleFilter
    triangle_filt = vtkTriangleFilter()
    triangle_filt.SetInputConnection(linear_extrusion.GetOutputPort())
    triangle_filt.Update()

    #  translate the plane using the xyz vector with intensity = negative extrusion value.
    translate = vtkTransform()
    translate.Translate(
        x_vector * vertical_extrusion["bottom"],
        y_vector * vertical_extrusion["bottom"],
        z_vector * vertical_extrusion["bottom"],
    )

    transform_filter = vtkTransformPolyDataFilter()
    transform_filter.SetTransform(translate)
    transform_filter.SetInputConnection(triangle_filt.GetOutputPort())
    transform_filter.Update()

    out_polydata = transform_filter.GetOutput()
    # ShallowCopy is the way to copy the new interpolated surface into the TriSurf instance created at the beginning
    surf_dict["vtk_obj"].ShallowCopy(out_polydata)
    surf_dict["vtk_obj"].Modified()
    # Add new entity from surf_dict. Function add_entity_from_dict creates a new uid
    if surf_dict["vtk_obj"].points_number > 0:
        self.geol_coll.add_entity_from_dict(surf_dict)
    else:
        self.print_terminal(" -- empty object -- ")


@freeze_gui_onoff
def enhanced_linear_extrusion(self):
    """Create a sampled extrusion surface with intermediate profiles."""
    self.print_terminal(
        "Enhanced extrusion: create a surface from one polyline with internal sampled extrusion lines"
    )
    if self.shown_table != "tabGeology":
        self.print_terminal(" -- Only geological objects can be projected -- ")
        return
    if not self.selected_uids:
        self.print_terminal("No input data selected.")
        return

    input_uids = deepcopy(self.selected_uids)
    if len(input_uids) != 1:
        self.print_terminal(" -- Select a single PolyLine or XsPolyLine -- ")
        return

    input_obj = self.geol_coll.get_uid_vtk_obj(input_uids[0])
    if not isinstance(input_obj, (PolyLine, XsPolyLine)):
        self.print_terminal(" -- Error input type: only PolyLine and XsPolyLine type -- ")
        return

    surf_dict = _build_extrusion_output_dict(
        self=self,
        input_uid=input_uids[0],
        title="Enhanced Extrusion",
        default_suffix="_enhanced_extruded",
    )
    if surf_dict is None:
        return

    extrusion_parameters = _ask_linear_extrusion_parameters(
        self=self, title="Enhanced Extrusion"
    )
    if extrusion_parameters is None:
        return
    trend, plunge, vertical_extrusion = extrusion_parameters

    sample_lines = input_one_value_dialog(
        title="Enhanced Extrusion",
        label="Internal sample lines",
        default_value=10,
    )
    if sample_lines is None:
        sample_lines = 10
    sample_lines = max(1, int(round(sample_lines)))

    extrusion_vector = _get_linear_extrusion_vector(trend, plunge)
    output_surface = _build_sampled_extrusion_surface(
        source_line=input_obj,
        extrusion_vector=extrusion_vector,
        bottom_limit=vertical_extrusion["bottom"],
        top_limit=vertical_extrusion["top"],
        sample_lines=sample_lines,
    )
    if output_surface is None or output_surface.points_number == 0:
        self.print_terminal(" -- empty object -- ")
        return

    surf_dict["vtk_obj"].ShallowCopy(output_surface)
    surf_dict["vtk_obj"].Modified()
    self.geol_coll.add_entity_from_dict(surf_dict)


@freeze_gui_onoff
def decimation_pro_resampling(self):
    """Decimation reduces the number of triangles in a triangle mesh while maintaining a faithful approximation to
    the original mesh."""
    self.print_terminal(
        "Decimation Pro: resample target surface and reduce number of triangles of the mesh"
    )
    if self.shown_table != "tabGeology":
        self.print_terminal(" -- Only geological objects can be resampled -- ")
        return
    # Check if some vtkPolyData is selected
    if not self.selected_uids:
        self.print_terminal("No input data selected.")
        return
    else:
        # Deep copy list of selected uids needed otherwise problems can arise if the main geology table is deseselcted while the dataframe is being built
        input_uids = deepcopy(self.selected_uids)
    for uid in input_uids:
        if isinstance(self.geol_coll.get_uid_vtk_obj(uid), TriSurf):
            pass
        else:
            self.print_terminal(" -- Error input type: only TriSurf type -- ")
            return
    # Create deepcopy of the geological entity dictionary.
    surf_dict = deepcopy(self.geol_coll.entity_dict)
    surf_dict["name"] = self.geol_coll.get_uid_name(input_uids[0]) + "_decimated"
    surf_dict["feature"] = self.geol_coll.get_uid_feature(input_uids[0])
    surf_dict["scenario"] = self.geol_coll.get_uid_scenario(input_uids[0])
    surf_dict["role"] = self.geol_coll.get_uid_role(input_uids[0])
    surf_dict["topology"] = "TriSurf"
    surf_dict["vtk_obj"] = TriSurf()
    # Create a new instance of the decimation class
    deci = vtkDecimatePro()
    deci.SetInputData(self.geol_coll.get_uid_vtk_obj(input_uids[0]))
    # Target Reduction value. Specify the desired reduction in the total number of polygons (e.g., when
    # Reduction is set to 0.9, this filter will try to reduce the data set to 10% of its original size).
    tar_reduct = input_one_value_dialog(
        title="Decimation Resampling parameters",
        label="Target Reduction Value",
        default_value=0.5,
    )
    if tar_reduct is None:
        tar_reduct = 0.5
    deci.SetTargetReduction(tar_reduct)
    # Preserve Topology switch. Turn on/off whether to preserve the topology of the original mesh.
    preserve_topology = input_text_dialog(
        title="Decimation Resampling parameters",
        label="Preserve Topology (ON/OFF)",
        default_text="ON",
    )
    if preserve_topology is None:
        pass
    elif preserve_topology == "ON" or preserve_topology == "on":
        deci.PreserveTopologyOn()
    elif preserve_topology == "OFF" or preserve_topology == "off":
        deci.PreserveTopologyOff()
    # Boundary Vertex Deletion switch. Turn on/off the deletion of vertices on the boundary of a mesh.
    bound_vert_del = input_text_dialog(
        title="Decimation Resampling parameters",
        label="Boundary Vertex Deletion (ON/OFF)",
        default_text="OFF",
    )
    if bound_vert_del is None:
        pass
    elif bound_vert_del == "ON" or bound_vert_del == "on":
        deci.BoundaryVertexDeletionOn()
    elif bound_vert_del == "OFF" or bound_vert_del == "off":
        deci.BoundaryVertexDeletionOff()
    # Splitting switch. Turn on/off the splitting of the mesh at corners, along edges, at non-manifold points, or
    # anywhere else a split is required.
    splitting = input_text_dialog(
        title="Decimation Resampling parameters",
        label="Splitting (ON to preserve original topology/OFF)",
        default_text="ON",
    )
    if splitting is None:
        pass
    elif splitting == "ON" or splitting == "on":
        deci.SplittingOn()
    elif splitting == "OFF" or splitting == "off":
        deci.SplittingOff()
    deci.Update()
    # ShallowCopy is the way to copy the new interpolated surface into the TriSurf instance created at the beginning
    surf_dict["vtk_obj"].ShallowCopy(deci.GetOutput())
    surf_dict["vtk_obj"].Modified()
    # Add new entity from surf_dict. Function add_entity_from_dict creates a new uid
    if surf_dict["vtk_obj"].points_number > 0:
        self.geol_coll.add_entity_from_dict(surf_dict)
    else:
        self.print_terminal(" -- empty object -- ")


@freeze_gui_onoff
def decimation_quadric_resampling(self):
    """Decimation reduces the number of triangles in a triangle mesh while maintaining a faithful approximation to
    the original mesh."""
    self.print_terminal(
        "Decimation Quadric: resample target surface and reduce number of triangles of the mesh"
    )
    if self.shown_table != "tabGeology":
        self.print_terminal(" -- Only geological objects can be resampled -- ")
        return
    # Check if some vtkPolyData is selected
    if not self.selected_uids:
        self.print_terminal("No input data selected.")
        return
    else:
        # Deep copy list of selected uids needed otherwise problems can arise if the main geology table is deseselcted while the dataframe is being built
        input_uids = deepcopy(self.selected_uids)
    for uid in input_uids:
        if isinstance(self.geol_coll.get_uid_vtk_obj(uid), TriSurf):
            pass
        else:
            self.print_terminal(" -- Error input type: only TriSurf type -- ")
            return
    # Create deepcopy of the geological entity dictionary.
    surf_dict = deepcopy(self.geol_coll.entity_dict)
    surf_dict["name"] = self.geol_coll.get_uid_name(input_uids[0]) + "_decimated"
    surf_dict["feature"] = self.geol_coll.get_uid_feature(input_uids[0])
    surf_dict["scenario"] = self.geol_coll.get_uid_scenario(input_uids[0])
    surf_dict["role"] = self.geol_coll.get_uid_role(input_uids[0])
    surf_dict["topology"] = "TriSurf"
    surf_dict["vtk_obj"] = TriSurf()
    # Create a new instance of the decimation class
    deci = vtkQuadricDecimation()
    deci.SetInputData(self.geol_coll.get_uid_vtk_obj(input_uids[0]))
    # Target Reduction value. Specify the desired reduction in the total number of polygons (e.g., when
    # Target Reduction is set to 0.9, this filter will try to reduce the data set to 10% of its original size).
    tar_reduct = input_one_value_dialog(
        title="Decimation Resampling parameters",
        label="Target Reduction Value",
        default_value=0.5,
    )
    if tar_reduct is None:
        tar_reduct = "0.5"
    deci.SetTargetReduction(tar_reduct)
    deci.Update()
    # ShallowCopy is the way to copy the new interpolated surface into the TriSurf instance created at the beginning
    surf_dict["vtk_obj"].ShallowCopy(deci.GetOutput())
    surf_dict["vtk_obj"].Modified()
    # Add new entity from surf_dict. Function add_entity_from_dict creates a new uid
    if surf_dict["vtk_obj"].points_number > 0:
        self.geol_coll.add_entity_from_dict(surf_dict)
    else:
        self.print_terminal(" -- empty object -- ")


@freeze_gui_onoff
def subdivision_resampling(self, mode=0, type="linear", n_subd=2):
    """Different types of subdivisions. Subdivides a triangular, polygonal surface; four new triangles are created for each triangle of the polygonal surface.:

    1. vtkLinearSubdivisionFilter (shape preserving)
    2. vtkButterflySubdivisionFilter  (not shape preserving)
    3. vtkLoopSubdivisionFilter (not shape preserving)"""
    self.print_terminal(
        "Subdivision resampling: resample target surface and increase number of triangles of the mesh"
    )
    if self.shown_table != "tabGeology":
        self.print_terminal(" -- Only geological objects can be resampled -- ")
        return
    # Check if some vtkPolyData is selected
    if not self.selected_uids:
        self.print_terminal("No input data selected.")
        return
    else:
        # Deep copy list of selected uids needed otherwise problems can arise if the main geology table is
        # deseselcted while the dataframe is being built
        input_uids = deepcopy(self.selected_uids)
    for uid in input_uids:
        if isinstance(self.geol_coll.get_uid_vtk_obj(uid), TriSurf):
            if type == "linear":
                subdiv_filter = vtkLinearSubdivisionFilter()
            elif type == "butterfly":
                subdiv_filter = vtkButterflySubdivisionFilter()
            elif type == "loop":
                subdiv_filter = vtkLoopSubdivisionFilter()
            # Create a new instance of the decimation class

            subdiv_filter.SetInputData(self.geol_coll.get_uid_vtk_obj(uid))
            subdiv_filter.SetNumberOfSubdivisions(int(n_subd))
            subdiv_filter.Update()
            # ShallowCopy is the way to copy the new interpolated surface into the
            #    TriSurf instance created at the beginning

            if mode:
                return subdiv_filter.GetOutput()
            else:
                # Add new entity from surf_dict. Function add_entity_from_dict creates a new uid
                # Create deepcopy of the geological entity dictionary.
                surf_dict = deepcopy(self.geol_coll.entity_dict)
                surf_dict["name"] = self.geol_coll.get_uid_name(uid) + "_subdivided"
                surf_dict["feature"] = self.geol_coll.get_uid_feature(uid)
                surf_dict["scenario"] = self.geol_coll.get_uid_scenario(uid)
                surf_dict["role"] = self.geol_coll.get_uid_role(uid)
                surf_dict["topology"] = "TriSurf"
                surf_dict["vtk_obj"] = TriSurf()
                surf_dict["vtk_obj"].ShallowCopy(subdiv_filter.GetOutput())
                surf_dict["vtk_obj"].Modified()

                if surf_dict["vtk_obj"].points_number > 0:
                    self.geol_coll.add_entity_from_dict(surf_dict)
                else:
                    self.print_terminal(" -- empty object -- ")
        else:
            self.print_terminal(" -- Error input type: only TriSurf type -- ")
            return


@freeze_gui_onoff
def intersection_xs(self):
    """vtkCutter is a filter to cut through data using any subclass of vtkImplicitFunction.
    HOW TO USE: select one or more Geological objects, DOMs or 3D Meshes (Source data), then function asks for XSection
    (input data) for the filter."""
    self.print_terminal(
        "Intersection with XSection: intersect Geological entities, 3D Meshes and DEM & DOMs."
    )
    # Check if some vtkPolyData is selected
    if not self.selected_uids:
        self.print_terminal("No input data selected.")
        return
    else:
        # Deep copy list of selected uids needed otherwise problems can arise if the
        # main geology table is deseselcted while the dataframe is being built
        input_uids = deepcopy(self.selected_uids)

    # Input selection dialog"
    xsect_names = input_checkbox_dialog(
        title="Intersection XSection",
        label="Choose XSections to intersect",
        choice_list=self.xsect_coll.get_names,
    )
    if xsect_names is None:
        return
    # xsect_uids = []
    for sec_name in xsect_names:  # this is redundant
        xsect_uid = self.xsect_coll.df.loc[
            self.xsect_coll.df["name"] == sec_name, "uid"
        ].values[0]
        postfix = f"_int_{sec_name}"
        if self.shown_table == "tabGeology":
            for uid in input_uids:
                if self.geol_coll.get_uid_topology(uid) in [
                    "PolyLine",
                    "XsPolyLine",
                ]:
                    # Intersection for PolyLine and XsPolyLine.
                    if self.geol_coll.get_uid_x_section(uid) != xsect_uid:
                        # cutter
                        cutter = vtkCutter()
                        cutter.SetCutFunction(
                            self.xsect_coll.get_uid_vtk_plane(xsect_uid)
                        )
                        cutter.SetInputData(self.geol_coll.get_uid_vtk_obj(uid))
                        cutter.Update()
                        if cutter.GetOutput().GetNumberOfPoints() > 0:
                            # Create new dict for the new XsVertexSet

                            obj_dict = deepcopy(self.geol_coll.entity_dict)
                            obj_dict["parent_uid"] = xsect_uid
                            obj_dict["topology"] = "XsVertexSet"
                            obj_dict["vtk_obj"] = XsVertexSet(
                                x_section_uid=xsect_uid, parent=self
                            )
                            obj_dict["name"] = (
                                f"{self.geol_coll.get_uid_name(uid)}{postfix}"
                            )
                            obj_dict["role"] = self.geol_coll.get_uid_role(uid)
                            obj_dict["feature"] = self.geol_coll.get_uid_feature(uid)
                            obj_dict["scenario"] = self.geol_coll.get_uid_scenario(uid)
                            obj_dict["properties_names"] = (
                                self.geol_coll.get_uid_properties_names(uid)
                            )
                            obj_dict["properties_components"] = (
                                self.geol_coll.get_uid_properties_components(uid)
                            )
                            obj_dict["vtk_obj"].DeepCopy(cutter.GetOutput())
                            for data_key in obj_dict["vtk_obj"].point_data_keys:
                                if not data_key in obj_dict["properties_names"]:
                                    obj_dict["vtk_obj"].remove_point_data(data_key)
                            self.geol_coll.add_entity_from_dict(obj_dict)
                        else:
                            self.print_terminal(" -- empty object from cutter -- ")
                    else:
                        self.print_terminal(
                            " -- no intersection of XsPolyLine with its own XSection -- "
                        )
                elif self.geol_coll.get_uid_topology(uid) == "TriSurf":
                    # cutter
                    cutter = vtkCutter()
                    cutter.SetCutFunction(self.xsect_coll.get_uid_vtk_plane(xsect_uid))
                    cutter.SetInputData(self.geol_coll.get_uid_vtk_obj(uid))
                    cutter.Update()
                    # cutter_clean
                    cutter_clean = vtkCleanPolyData()
                    cutter_clean.ConvertLinesToPointsOff()
                    cutter_clean.ConvertPolysToLinesOff()
                    cutter_clean.ConvertStripsToPolysOff()
                    cutter_clean.SetTolerance(0.0)
                    cutter_clean.SetInputConnection(cutter.GetOutputPort())
                    cutter_clean.Update()
                    # cutter_clean_strips
                    cutter_clean_strips = vtkStripper()
                    cutter_clean_strips.JoinContiguousSegmentsOn()
                    cutter_clean_strips.SetInputConnection(cutter_clean.GetOutputPort())
                    cutter_clean_strips.Update()
                    # cutter_clean_strips_clean, needed to sort the nodes and cells in the right order
                    cutter_clean_strips_clean = vtkCleanPolyData()
                    cutter_clean_strips_clean.ConvertLinesToPointsOff()
                    cutter_clean_strips_clean.ConvertPolysToLinesOff()
                    cutter_clean_strips_clean.ConvertStripsToPolysOff()
                    cutter_clean_strips_clean.SetTolerance(0.0)
                    cutter_clean_strips_clean.SetInputConnection(
                        cutter_clean_strips.GetOutputPort()
                    )
                    cutter_clean_strips_clean.Update()
                    # cutter_clean_strips_clean_triangle, used to convert polyline cells back to lines
                    cutter_clean_strips_clean_triangle = vtkTriangleFilter()
                    cutter_clean_strips_clean_triangle.SetInputConnection(
                        cutter_clean_strips_clean.GetOutputPort()
                    )
                    cutter_clean_strips_clean_triangle.Update()
                    # connectivity, split multiple part polylines, first using .SetExtractionModeToAllRegions()
                    # to get the number of parts/regions, then switching to .SetExtractionModeToSpecifiedRegions()
                    # to extract the parts/regions sequentially
                    if (
                        cutter_clean_strips_clean_triangle.GetOutput().GetNumberOfPoints()
                        > 0
                    ):
                        connectivity = vtkPolyDataConnectivityFilter()
                        connectivity.SetInputConnection(
                            cutter_clean_strips_clean_triangle.GetOutputPort()
                        )
                        connectivity.SetExtractionModeToAllRegions()
                        connectivity.Update()
                        n_regions = connectivity.GetNumberOfExtractedRegions()
                        connectivity.SetExtractionModeToSpecifiedRegions()
                        connectivity.Update()
                        for region in range(n_regions):
                            connectivity.InitializeSpecifiedRegionList()
                            connectivity.AddSpecifiedRegion(region)
                            connectivity.Update()
                            # connectivity_clean, used to remove orphan points left behind by connectivity
                            connectivity_clean = vtkCleanPolyData()
                            connectivity_clean.SetInputConnection(
                                connectivity.GetOutputPort()
                            )
                            connectivity_clean.Update()
                            # Check if polyline really exists then create entity
                            if connectivity_clean.GetOutput().GetNumberOfPoints() > 0:
                                # Create new dict for the new XsPolyLine
                                obj_dict = deepcopy(self.geol_coll.entity_dict)
                                obj_dict["parent_uid"] = xsect_uid
                                obj_dict["topology"] = "XsPolyLine"
                                obj_dict["vtk_obj"] = XsPolyLine(
                                    x_section_uid=xsect_uid, parent=self
                                )
                                obj_dict["name"] = (
                                    f"{self.geol_coll.get_uid_name(uid)}{postfix}"
                                )
                                obj_dict["role"] = self.geol_coll.get_uid_role(uid)
                                obj_dict["feature"] = self.geol_coll.get_uid_feature(
                                    uid
                                )
                                obj_dict["scenario"] = self.geol_coll.get_uid_scenario(
                                    uid
                                )
                                obj_dict["properties_names"] = (
                                    self.geol_coll.get_uid_properties_names(uid)
                                )
                                obj_dict["properties_components"] = (
                                    self.geol_coll.get_uid_properties_components(uid)
                                )
                                obj_dict["vtk_obj"].DeepCopy(
                                    connectivity_clean.GetOutput()
                                )
                                for data_key in obj_dict["vtk_obj"].point_data_keys:
                                    if not data_key in obj_dict["properties_names"]:
                                        obj_dict["vtk_obj"].remove_point_data(data_key)
                                self.geol_coll.add_entity_from_dict(obj_dict)
                            else:
                                self.print_terminal(
                                    " -- empty object from connectivity_clean-- "
                                )
                    else:
                        self.print_terminal(
                            " -- empty object from cutter_clean_strips_clean_triangle -- "
                        )
        elif self.shown_table == "tabMeshes":
            for uid in input_uids:
                if self.mesh3d_coll.get_uid_mesh3d_type(uid) == "Voxet":
                    # Get cutter - a polydata slice cut across the voxet.
                    cutter = vtkCutter()
                    cutter.SetCutFunction(self.xsect_coll.get_uid_vtk_plane(xsect_uid))
                    cutter.SetInputData(self.mesh3d_coll.get_uid_vtk_obj(uid))
                    cutter.Update()
                    if cutter.GetOutput().GetNumberOfPoints() > 0:
                        cutter.GetOutput().GetPointData().SetActiveScalars(
                            self.mesh3d_coll.get_uid_properties_names(uid)[0]
                        )
                        cutter_bounds = np_float64(cutter.GetOutput().GetBounds())
                        dim_Z = self.mesh3d_coll.get_uid_vtk_obj(uid).W_n
                        spacing_Z = self.mesh3d_coll.get_uid_vtk_obj(uid).W_step
                        if spacing_Z < 0:
                            spacing_Z *= -1
                        cutter_n_points = cutter.GetOutput().GetNumberOfPoints()
                        dim_W = int(cutter_n_points / dim_Z)
                        spacing_W = np_sqrt(
                            (cutter_bounds[1] - cutter_bounds[0]) ** 2
                            + (cutter_bounds[3] - cutter_bounds[2]) ** 2
                        ) / (dim_W - 1)
                        strike = self.xsect_coll.get_uid_strike(xsect_uid)
                        # The direction matrix is a 3x3 transformation matrix supporting scaling and rotation.
                        # (double  	e00,
                        # double  	e01,
                        # double  	e02,
                        # double  	e10,
                        # double  	e11,
                        # double  	e12,
                        # double  	e20,
                        # double  	e21,
                        # double  	e22)
                        if strike <= 90:
                            origin = [
                                cutter_bounds[0],
                                cutter_bounds[2],
                                cutter_bounds[4],
                            ]
                            direction_matrix = [
                                np_sin(strike * np_pi / 180),
                                0,
                                -(np_cos(strike * np_pi / 180)),
                                np_cos(strike * np_pi / 180),
                                0,
                                np_sin(strike * np_pi / 180),
                                0,
                                1,
                                0,
                            ]
                        elif strike <= 180:
                            origin = [
                                cutter_bounds[1],
                                cutter_bounds[2],
                                cutter_bounds[4],
                            ]
                            direction_matrix = [
                                -(np_sin(strike * np_pi / 180)),
                                0,
                                -(np_cos(strike * np_pi / 180)),
                                -(np_cos(strike * np_pi / 180)),
                                0,
                                np_sin(strike * np_pi / 180),
                                0,
                                1,
                                0,
                            ]
                        elif strike <= 270:
                            origin = [
                                cutter_bounds[0],
                                cutter_bounds[2],
                                cutter_bounds[4],
                            ]
                            direction_matrix = [
                                -(np_sin(strike * np_pi / 180)),
                                0,
                                -(np_cos(strike * np_pi / 180)),
                                -(np_cos(strike * np_pi / 180)),
                                0,
                                np_sin(strike * np_pi / 180),
                                0,
                                1,
                                0,
                            ]
                        else:
                            origin = [
                                cutter_bounds[1],
                                cutter_bounds[2],
                                cutter_bounds[4],
                            ]
                            direction_matrix = [
                                np_sin(strike * np_pi / 180),
                                0,
                                -(np_cos(strike * np_pi / 180)),
                                np_cos(strike * np_pi / 180),
                                0,
                                np_sin(strike * np_pi / 180),
                                0,
                                1,
                                0,
                            ]
                        # Create vtkImageData with the geometry to fit data from cutter
                        probe_image = vtkImageData()
                        probe_image.SetOrigin(origin)
                        probe_image.SetSpacing([spacing_W, spacing_Z, 0.0])
                        probe_image.SetDimensions([dim_W, dim_Z, 1])
                        probe_image.SetDirectionMatrix(direction_matrix)
                        probe_n_points = probe_image.GetNumberOfPoints()
                        # scipy.interpolate.griddata: get point coordinates from cutter.GetOutput() + strati_0 values +
                        # calculate point coordinates for probe_image, the final regular grid. Then, execute griddata
                        XYZ_cutter = numpy_support.vtk_to_numpy(
                            cutter.GetOutput().GetPoints().GetData()
                        )
                        values = numpy_support.vtk_to_numpy(
                            cutter.GetOutput().GetPointData().GetArray(0)
                        ).reshape((dim_Z * dim_W,))
                        XYZ_probe = np_zeros((probe_n_points, 3))
                        for point in range(probe_n_points):
                            XYZ_probe[point, :] = probe_image.GetPoint(point)
                        regular_values = sp_griddata(
                            points=XYZ_cutter,
                            values=values,
                            xi=XYZ_probe,
                            method="nearest",
                        )
                        # regular_values = sp_griddata(points=XYZ_cutter, values=values, xi=XYZ_probe, method='linear')
                        # regular_values = sp_griddata(points=XYZ_cutter, values=values, xi=XYZ_probe, method='linear', rescale=True)
                        # Pass values from griddata interpolation to probe_image
                        probe_image.GetPointData().AddArray(
                            numpy_support.numpy_to_vtk(regular_values)
                        )
                        probe_image.GetPointData().GetArray(0).SetName(
                            self.mesh3d_coll.get_uid_properties_names(uid)[0]
                        )
                        # Create new dict for the new XsVoxet
                        obj_dict = deepcopy(self.mesh3d_coll.entity_dict)
                        obj_dict["name"] = (
                            f"{self.mesh3d_coll.get_uid_name(uid)}{postfix}"
                        )
                        obj_dict["topology"] = "XsVoxet"
                        obj_dict["properties_names"] = (
                            self.mesh3d_coll.get_uid_properties_names(uid)
                        )
                        obj_dict["properties_components"] = (
                            self.mesh3d_coll.get_uid_properties_components(uid)
                        )
                        obj_dict["parent_uid"] = xsect_uid
                        obj_dict["vtk_obj"] = XsVoxet(
                            x_section_uid=xsect_uid, parent=self
                        )
                        obj_dict["vtk_obj"].ShallowCopy(probe_image)
                        if obj_dict["vtk_obj"].points_number > 0:
                            self.mesh3d_coll.add_entity_from_dict(obj_dict)
                        else:
                            self.print_terminal(" -- empty object -- ")
                    else:
                        self.print_terminal(" -- empty object -- ")
        elif self.shown_table == "tabDOMs":
            for uid in input_uids:
                if self.dom_coll.get_uid_topology(uid) == "DEM":
                    # cutter
                    cutter = vtkCutter()
                    cutter.SetCutFunction(self.xsect_coll.get_uid_vtk_plane(xsect_uid))
                    cutter.SetInputData(self.dom_coll.get_uid_vtk_obj(uid))
                    cutter.Update()
                    # Create new dict for the new DomXs
                    obj_dict = deepcopy(self.dom_coll.entity_dict)
                    obj_dict["name"] = f"{self.dom_coll.get_uid_name(uid)}{postfix}"
                    obj_dict["topology"] = "DomXs"
                    obj_dict["properties_names"] = (
                        self.dom_coll.get_uid_properties_names(uid)
                    )
                    obj_dict["properties_components"] = (
                        self.dom_coll.get_uid_properties_components(uid)
                    )
                    obj_dict["parent_uid"] = xsect_uid
                    obj_dict["vtk_obj"] = XsPolyLine(
                        x_section_uid=xsect_uid, parent=self
                    )
                    obj_dict["vtk_obj"].DeepCopy(cutter.GetOutput())
                    self.print_terminal(f"obj_dict['vtk_obj']:\n{obj_dict['vtk_obj']}")
                    if obj_dict["vtk_obj"].points_number > 0:
                        for data_key in obj_dict["vtk_obj"].point_data_keys:
                            if not data_key in obj_dict["properties_names"]:
                                obj_dict["vtk_obj"].remove_point_data(data_key)
                        self.dom_coll.add_entity_from_dict(obj_dict)
                    else:
                        self.print_terminal(" -- empty object -- ")
        else:
            self.print_terminal(
                " -- Only Geological objects, 3D Meshes and DEM & DOMs can be intersected with XSection -- "
            )


@freeze_gui_onoff
def project_2_dem(self):
    """vtkProjectedTerrainPath projects an input polyline onto a terrain image.
    HOW TO USE: at the moment, as vtkProjectedTerrainPath takes vtkImageData as input, we need to import
    DEM file also as MapImage (--> as vtkImageData) and to use this entity as source data for the
    projection"""
    # self.print_terminal("Vertical Projection: project target lines onto a terrain image")
    if self.shown_table != "tabGeology":
        self.print_terminal(" -- Only geological objects can be interpolated -- ")
        return
    # Check if some vtkPolyData is selected
    if not self.selected_uids:
        self.print_terminal("No input data selected.")
        return
    else:
        input_uids = deepcopy(self.selected_uids)
    # for uid in input_uids:
    #     if isinstance(self.geol_coll.get_uid_vtk_obj(uid), PolyLine):
    #         pass
    #     else:
    #         print(" -- Error input type: only PolyLine type -- ")
    #         return
    # Ask if the tool replaces the input entities, or if they shall be preserved
    replace_on_off = options_dialog(
        title="Project to Surface",
        message="Replace Original Entities?",
        yes_role="Yes",
        no_role="No",
        reject_role=None,
    )
    if replace_on_off is None:
        return
    # Ask for the DOM (/DEM), source of the projection
    dom_list_uids = self.dom_coll.get_uids
    dom_list_names = []
    for uid in dom_list_uids:
        dom_list_names.append(self.dom_coll.get_uid_name(uid))
    dom_name = input_combo_dialog(
        title="Project to Surface",
        label="Input surface for projection",
        choice_list=dom_list_names,
    )
    if dom_name is None:
        return
    dom_uid = self.dom_coll.df.loc[self.dom_coll.df["name"] == dom_name, "uid"].values[
        0
    ]
    #     print("dom_uid ", dom_uid)
    #     Convert DEM (vtkStructuredGrid) in vtkImageData to perform the projection with vtkProjectedTerrainPath
    #     dem_to_image = vtkDEMReader()
    #     dem_to_image.SetInputData(self.dom_coll.get_uid_vtk_obj(dom_uid))
    #     dem_to_image.Update()
    #     print("dem_to_image ", dem_to_image)
    #     print("dem_to_image.GetOutput() ", dem_to_image.GetOutput())
    #     Ask for the MapImage, source of the projection
    #     image_list_uids = self.image_coll.get_uids()
    #     image_list_names = []
    #     for uid in image_list_uids:
    #         image_list_names.append(self.image_coll.get_uid_name(uid))
    #     img_name = input_combo_dialog(title='Project to Surface', label='Input surface for projection', choice_list=image_list_names)
    #     if img_name is None:
    #         return
    #     img_uid = self.image_coll.df.loc[self.image_coll.df['name'] == img_name, 'uid'].values[0]
    # ----- some check is needed here. Check if the chosen image is a 2D map with elevation values -----
    prgs_bar = progress_dialog(
        max_value=len(input_uids),
        title_txt="Input dataframe",
        label_txt="Projecting data to DEM...",
        cancel_txt=None,
        parent=self,
    )
    # Track UIDs to update at the end
    updated_uids = []

    for uid in input_uids:
        # Determine which entity to project
        if replace_on_off == 1:  # No - first create a copy, then project only the copy
            # Create a copy of the original entity (not projected)
            obj_dict = deepcopy(self.geol_coll.entity_dict)
            obj_dict["uid"] = None  # Will generate new uid
            obj_dict["name"] = f"{self.geol_coll.get_uid_name(uid)}_proj_DEM"
            obj_dict["feature"] = self.geol_coll.get_uid_feature(uid)
            obj_dict["scenario"] = self.geol_coll.get_uid_scenario(uid)
            obj_dict["role"] = self.geol_coll.get_uid_role(uid)
            obj_dict["topology"] = self.geol_coll.get_uid_topology(uid)
            obj_dict["properties_names"] = self.geol_coll.get_uid_properties_names(uid)
            obj_dict["properties_components"] = (
                self.geol_coll.get_uid_properties_components(uid)
            )

            # Create VTK object and copy geometry from original
            if isinstance(self.geol_coll.get_uid_vtk_obj(uid), PolyLine):
                obj_dict["vtk_obj"] = PolyLine()
            elif isinstance(self.geol_coll.get_uid_vtk_obj(uid), Attitude):
                obj_dict["vtk_obj"] = Attitude()
            elif isinstance(self.geol_coll.get_uid_vtk_obj(uid), VertexSet):
                obj_dict["vtk_obj"] = VertexSet()

            obj_dict["vtk_obj"].DeepCopy(self.geol_coll.get_uid_vtk_obj(uid))

            # Add the copy to collection
            if obj_dict["vtk_obj"].points_number > 0:
                new_uid = self.geol_coll.add_entity_from_dict(obj_dict)
                uid_to_project = new_uid
            else:
                self.print_terminal(" -- empty object -- ")
                prgs_bar.add_one()
                continue
        else:  # Yes - project original entity directly
            uid_to_project = uid

        # Now project the target entity (either original or the new copy)
        projection = vtkPointInterpolator2D()
        projection.SetInputData(self.geol_coll.get_uid_vtk_obj(uid_to_project))
        projection.SetSourceData(self.dom_coll.get_uid_vtk_obj(dom_uid))
        projection.SetKernel(vtkVoronoiKernel())
        projection.SetNullPointsStrategyToClosestPoint()
        projection.SetZArrayName("elevation")
        projection.Update()

        # Create temporary object to hold projected geometry
        projected_obj = None
        if isinstance(self.geol_coll.get_uid_vtk_obj(uid_to_project), PolyLine):
            projected_obj = PolyLine()
        elif isinstance(self.geol_coll.get_uid_vtk_obj(uid_to_project), Attitude):
            projected_obj = Attitude()
        elif isinstance(self.geol_coll.get_uid_vtk_obj(uid_to_project), VertexSet):
            projected_obj = VertexSet()

        if projected_obj is None:
            self.print_terminal(f" -- Unknown object type for uid {uid_to_project} -- ")
            prgs_bar.add_one()
            continue

        # Apply projection - use DeepCopy to ensure complete copy of geometry
        projected_obj.DeepCopy(projection.GetOutput())
        # Update Z coordinates with elevation data - recreate points array to ensure VTK recognizes the change
        elevation = projected_obj.get_point_data("elevation")
        new_points = projected_obj.points.copy()
        new_points[:, 2] = elevation
        projected_obj.points = new_points
        # Force update of internal VTK structures
        projected_obj.Modified()

        if projected_obj.points_number == 0:
            self.print_terminal(" -- empty object after projection -- ")
            prgs_bar.add_one()
            continue

        # Update the entity with projected geometry
        # Note: replace_vtk already emits geom_modified signal
        self.geol_coll.replace_vtk(uid=uid_to_project, vtk_object=projected_obj)

        # Update entity name
        if replace_on_off == 1:  # No - set name for new entity
            self.geol_coll.set_uid_name(
                uid=uid_to_project, name=f"{self.geol_coll.get_uid_name(uid)}_proj_DEM"
            )
        else:  # Yes - set name for original entity
            self.geol_coll.set_uid_name(
                uid=uid_to_project, name=f"{self.geol_coll.get_uid_name(uid)}_proj_DEM"
            )

        updated_uids.append(uid_to_project)
        prgs_bar.add_one()

    prgs_bar.close()

    # Emit metadata_modified signal for name changes (geom_modified already emitted by replace_vtk)
    if updated_uids:
        self.signals.metadata_modified.emit(updated_uids, self.geol_coll)

    # Force render in all views to ensure visual update
    from pzero.views.dock_window import DockWindow
    dock_windows = self.findChildren(DockWindow)
    for dock in dock_windows:
        if hasattr(dock, "canvas") and hasattr(dock.canvas, "plotter"):
            try:
                dock.canvas.plotter.render()
            except Exception:
                pass  # Ignore if render fails

    # Clear selection in all views after projection
    for dock in dock_windows:
        if hasattr(dock, "canvas") and hasattr(dock.canvas, "clear_selection"):
            dock.canvas.clear_selection()


@freeze_gui_onoff
def project_2_xs(self):
    """Projection of a copy of point and polyline geological entities to a planar cross section, along an axis specified with plunge/trend."""
    # self.print_terminal("Projection to cross section")
    # Get input objects - points and polylines at the moment.
    if self.shown_table != "tabGeology":
        self.print_terminal(" -- Only geological objects can be projected -- ")
        return
    # Check if some vtkPolyData is selected
    if not self.selected_uids:
        self.print_terminal("No input data selected.")
        return
    else:
        # Deep copy list of selected uids needed otherwise problems can arise if the main geology table is deseselcted while the dataframe is being built
        input_uids = deepcopy(self.selected_uids)
    # Select points and polylines only.
    input_uids_clean = deepcopy(input_uids)
    for uid in input_uids:
        if self.geol_coll.get_uid_topology(uid) not in [
            "VertexSet",
            "PolyLine",
            "XsVertexSet",
            "XsPolyLine",
        ]:
            input_uids_clean.remove(uid)
    input_uids = deepcopy(input_uids_clean)
    del input_uids_clean
    if not input_uids:
        print("No valid input data selected.")
        return
    # Define projection parameters (float64 needed for "t" afterwards)
    xs_names = self.xsect_coll.get_names
    default_xs_uid = self.xsect_coll.df.loc[
        self.xsect_coll.df["name"] == xs_names[0], "uid"
    ].values[0]
    default_strike = np_float64(self.xsect_coll.get_uid_strike(default_xs_uid))
    default_dip = np_float64(self.xsect_coll.get_uid_dip(default_xs_uid))
    default_proj_trend = round((default_strike + 90.0) % 360.0, 2)
    default_proj_plunge = round(90.0 - default_dip, 2)
    input_dict = {
        "xs_name": ["XSection: ", xs_names],
        "proj_plunge": ["Projection axis plunge: ", default_proj_plunge],
        "proj_trend": ["Projection axis trend: ", default_proj_trend],
        "dist_sec": ["Maximum distance from section: ", 0.0],
    }
    options_dict = multiple_input_dialog(
        title="Projection to XSection", input_dict=input_dict
    )
    if options_dict is None:
        return
    xs_name = options_dict["xs_name"]
    xs_dist = options_dict["dist_sec"]
    xs_uid = self.xsect_coll.df.loc[
        self.xsect_coll.df["name"] == xs_name, "uid"
    ].values[0]
    proj_plunge = np_float64(options_dict["proj_plunge"])
    proj_trend = np_float64(options_dict["proj_trend"])
    # Check for projection trend parallel to cross section.
    if (
        abs((proj_trend - self.xsect_coll.get_uid_strike(xs_uid) + 180.0) % 360.0 - 180.0)
        < 10.0
        or abs(
            (
                proj_trend
                - ((self.xsect_coll.get_uid_strike(xs_uid) + 180.0) % 360.0)
                + 180.0
            )
            % 360.0
            - 180.0
        )
        < 10.0
    ):
        self.print_terminal(
            "Plunge too close to being parallel to XSection (angle < 10°)"
        )
        return
    # # Get cross section start and end points (float64 needed for "t" afterwards).
    # xa = np_float64(self.xsect_coll.get_uid_origin_x(xs_uid))
    # ya = np_float64(self.xsect_coll.get_uid_origin_y(xs_uid))
    # xb = np_float64(self.xsect_coll.get_uid_end_x(xs_uid))
    # yb = np_float64(self.xsect_coll.get_uid_end_y(xs_uid))
    # Get cross section origin and normals (float64 needed for "t" afterwards).
    ox = np_float64(self.xsect_coll.get_uid_origin_x(xs_uid))
    oy = np_float64(self.xsect_coll.get_uid_origin_y(xs_uid))
    oz = np_float64(self.xsect_coll.get_uid_origin_z(xs_uid))
    nx = np_float64(self.xsect_coll.get_uid_normal_x(xs_uid))
    ny = np_float64(self.xsect_coll.get_uid_normal_y(xs_uid))
    nz = np_float64(self.xsect_coll.get_uid_normal_z(xs_uid))

    # Calculate projection direction cosines (float64 needed for "t" afterwards).
    alpha = np_float64(
        np_sin(proj_trend * np_pi / 180.0) * np_cos(proj_plunge * np_pi / 180.0)
    )
    beta = np_float64(
        np_cos(proj_trend * np_pi / 180.0) * np_cos(proj_plunge * np_pi / 180.0)
    )
    gamma = np_float64(-np_sin(proj_plunge * np_pi / 180.0))
    # Project each entity.
    for uid in input_uids:
        # Clone entity.
        entity_dict = deepcopy(self.geol_coll.entity_dict)
        entity_dict["name"] = self.geol_coll.get_uid_name(uid) + "_prj_" + xs_name
        entity_dict["role"] = self.geol_coll.get_uid_role(uid)
        entity_dict["feature"] = self.geol_coll.get_uid_feature(uid)
        entity_dict["scenario"] = self.geol_coll.get_uid_scenario(uid)
        entity_dict["properties_names"] = self.geol_coll.get_uid_properties_names(uid)
        entity_dict["properties_components"] = (
            self.geol_coll.get_uid_properties_components(uid)
        )
        entity_dict["parent_uid"] = xs_uid
        if self.geol_coll.get_uid_topology(uid) == "VertexSet":
            entity_dict["topology"] = "XsVertexSet"
            out_vtk = XsVertexSet(x_section_uid=xs_uid, parent=self)
            out_vtk.DeepCopy(self.geol_coll.get_uid_vtk_obj(uid))
        elif (
            self.geol_coll.get_uid_topology(uid) == "PolyLine"
            or self.geol_coll.get_uid_topology(uid) == "XsPolyLine"
        ):
            entity_dict["topology"] = "XsPolyLine"
            out_vtk = XsPolyLine(x_section_uid=xs_uid, parent=self)
            out_vtk.DeepCopy(self.geol_coll.get_uid_vtk_obj(uid))
        else:
            entity_dict["topology"] = self.geol_coll.get_uid_topology(uid)
            out_vtk = self.geol_coll.get_uid_vtk_obj(uid).deep_copy()
        # Perform projection on clone (the last two steps could be merged).
        # np_float64 is needed to calculate "t" with a good precision
        # when X and Y are in UTM coordinates with very large values,
        # then the result is cast to float32 that is the VTK standard.
        xo = out_vtk.points_X.astype(np_float64)
        yo = out_vtk.points_Y.astype(np_float64)
        zo = out_vtk.points_Z.astype(np_float64)
        # t = (-xo * (yb - ya) - yo * (xa - xb) - ya * xb + yb * xa) / (
        #     alpha * (yb - ya) + beta * (xa - xb)
        # )
        t = (nx * (ox - xo) + ny * (oy - yo) + nz * (oz - zo)) / (nx * alpha + ny * beta + nz * gamma)

        out_vtk.points_X[:] = (xo + alpha * t).astype(np_float32)
        out_vtk.points_Y[:] = (yo + beta * t).astype(np_float32)
        out_vtk.points_Z[:] = (zo + gamma * t).astype(np_float32)

        out_vtk.set_point_data("distance", np_abs(t))

        if entity_dict["topology"] == "XsVertexSet":
            # print(out_vtk.get_point_data('distance'))
            if xs_dist <= 0:
                entity_dict["vtk_obj"] = out_vtk
                self.geol_coll.add_entity_from_dict(entity_dict=entity_dict)
            else:
                thresh = vtkThresholdPoints()
                thresh.SetInputData(out_vtk)
                thresh.ThresholdByLower(xs_dist)
                thresh.SetInputArrayToProcess(
                    0, 0, 0, vtkDataObject().FIELD_ASSOCIATION_POINTS, "distance"
                )
                thresh.Update()

                thresholded = thresh.GetOutput()

                if thresholded.GetNumberOfPoints() > 0:
                    out_vtk.DeepCopy(thresholded)
                    entity_dict["vtk_obj"] = out_vtk
                    out_uid = self.geol_coll.add_entity_from_dict(
                        entity_dict=entity_dict
                    )
                else:
                    self.print_terminal(
                        f'No measure found for group {entity_dict["name"]}, try to extend the maximum distance'
                    )

        elif entity_dict["topology"] == "XsPolyLine":
            # Output, checking for multipart for polylines.
            connectivity = vtkPolyDataConnectivityFilter()
            connectivity.SetInputData(out_vtk)
            connectivity.SetExtractionModeToAllRegions()
            connectivity.Update()
            n_regions = connectivity.GetNumberOfExtractedRegions()
            connectivity.SetExtractionModeToSpecifiedRegions()
            connectivity.Update()
            # entity_dict['vtk_obj'] = XsPolyLine()
            for region in range(n_regions):
                connectivity.InitializeSpecifiedRegionList()
                connectivity.AddSpecifiedRegion(region)
                connectivity.Update()
                # connectivity_clean, used to remove orphan points left behind by connectivity
                connectivity_clean = vtkCleanPolyData()
                connectivity_clean.SetInputConnection(connectivity.GetOutputPort())
                connectivity_clean.Update()
                # Check if polyline really exists then create entity
                if xs_dist <= 0:
                    out_vtk = connectivity_clean.GetOutput()
                else:
                    thresh = vtkThresholdPoints()
                    thresh.SetInputConnection(connectivity_clean.GetOutputPort())
                    thresh.ThresholdByLower(xs_dist)
                    thresh.SetInputArrayToProcess(
                        0,
                        0,
                        0,
                        vtkDataObject().FIELD_ASSOCIATION_POINTS,
                        "distance",
                    )
                    thresh.Update()

                    out_vtk = thresh.GetOutput()
                if out_vtk.GetNumberOfPoints() > 0:
                    # vtkAppendPolyData...
                    entity_dict["vtk_obj"] = XsPolyLine(
                        x_section_uid=xs_uid, parent=self
                    )
                    entity_dict["vtk_obj"].DeepCopy(connectivity_clean.GetOutput())
                    for data_key in entity_dict["vtk_obj"].point_data_keys:
                        if not data_key in entity_dict["properties_names"]:
                            entity_dict["vtk_obj"].remove_point_data(data_key)
                    out_uid = self.geol_coll.add_entity_from_dict(
                        entity_dict=entity_dict
                    )
                else:
                    self.print_terminal(" -- empty object -- ")


@freeze_gui_onoff
def split_surf(self):
    """Split two surfaces. This should be integrated with intersection_xs in one function since is the same thing"""
    if self.shown_table != "tabGeology":
        self.print_terminal(" -- Only surface objects can be intersected -- ")
        return
    if not self.selected_uids:
        self.print_terminal("No input data selected.")
        return
    else:
        # Deep copy list of selected uids needed otherwise problems can arise if the main geology table
        # is deseselcted while the dataframe is being built
        # print(self.selected_uids_all())
        # 0. Define the reference surface and target surfaces
        # if input_uids[0] not in self.geol_coll.get_uids():
        #     ref_surf = self.dom_coll.get_uid_vtk_obj(input_uids[0])
        #     pld = pv_PolyData(ref_surf.points)
        #     pld.delaunay_2d(inplace=True)
        # else:
        scissor_surf = self.geol_coll.get_uid_vtk_obj(self.selected_uids[-1])

        for paper_uid in self.selected_uids[:-1]:  # for every target surface
            paper_surf = self.geol_coll.get_uid_vtk_obj(paper_uid)

            # cutter = vtkIntersectionPolyDataFilter()
            # cutter.SetInputDataObject(0, paper_surf)
            # cutter.SetInputDataObject(1, scissor_surf)

            temp_surf = pv_PolyData()
            temp_surf.ShallowCopy(paper_surf)
            line_intersection = PolyLine()
            intersection, intersect, _ = temp_surf.intersection(
                scissor_surf, split_first=True, split_second=False
            )
            line_intersection.ShallowCopy(intersection)
            paper_intersection = TriSurf()
            paper_intersection.ShallowCopy(intersect)
            # print(temp_surf.array_names)
            implicit_dist = temp_surf.compute_implicit_distance(scissor_surf)
            implicit_dist.set_active_scalars("implicit_distance")
            intersect = vtkClipPolyData()
            intersect.SetInputData(implicit_dist)
            intersect.GenerateClippedOutputOn()

            intersect.Update()

            appender = vtkAppendPolyData()

            # The parts are always 2 even if the surf is crossed more than once
            # (the implicit distance is calculated orthogonal to the ref. surface).
            # For multiple intersections the splitting will result in a multipart
            # object that can be further split using split_parts(). We can then
            # append each single part in a multipart object and assign
            # the RegionId property using connected_calc().
            parts = [intersect.GetOutput(), intersect.GetClippedOutput()]

            for part in parts:
                temp = TriSurf()
                temp.ShallowCopy(part)
                subparts = temp.split_parts()
                for subpart in subparts:
                    appender.AddInputData(subpart)

            appender.Update()

            final_obj = TriSurf()
            final_obj.DeepCopy(appender.GetOutput())

            obj_dict = deepcopy(self.geol_coll.entity_dict)

            obj_dict["uid"] = str(uuid4())

            obj_dict["topology"] = self.geol_coll.get_uid_topology(paper_uid)

            obj_dict["vtk_obj"] = final_obj

            obj_dict["name"] = self.geol_coll.get_uid_name(paper_uid) + "_split"

            obj_dict["role"] = self.geol_coll.get_uid_role(paper_uid)

            obj_dict["feature"] = self.geol_coll.get_uid_feature(paper_uid)

            obj_dict["scenario"] = self.geol_coll.get_uid_scenario(paper_uid)

            self.geol_coll.add_entity_from_dict(obj_dict)

            # Calculate connectivity for the splitted surface

            self.geol_coll.append_uid_property(
                uid=obj_dict["uid"], property_name="RegionId", property_components=1
            )

            self.geol_coll.get_uid_vtk_obj(obj_dict["uid"]).connected_calc()

            # Add line intersection
            obj_dict = deepcopy(self.geol_coll.entity_dict)

            obj_dict["uid"] = str(uuid4())

            obj_dict["topology"] = "PolyLine"

            obj_dict["vtk_obj"] = line_intersection

            obj_dict["name"] = self.geol_coll.get_uid_name(paper_uid) + "_line_int"

            obj_dict["role"] = self.geol_coll.get_uid_role(paper_uid)

            obj_dict["feature"] = self.geol_coll.get_uid_feature(paper_uid)

            obj_dict["scenario"] = self.geol_coll.get_uid_scenario(paper_uid)

            self.geol_coll.add_entity_from_dict(obj_dict)
            self.geol_coll.append_uid_property(
                uid=obj_dict["uid"], property_name="RegionId", property_components=1
            )
            self.geol_coll.get_uid_vtk_obj(obj_dict["uid"]).connected_calc()

            self.prop_legend.update_widget(self)

            del temp_surf
            del intersection

        # 1. Calculate the implicit distance of the target surface[1,2,3,4,..] from the reference surface[0]


@freeze_gui_onoff
def retopo(self, mode=0, dec_int=0.2, n_iter=40, rel_fac=0.1):
    """Function used to retopologize a given surface. This is useful in the case of
    semplifying irregular triangulated meshes for CAD exporting or aesthetic reasons.
    The function is a combonation of two filters:

    - vtkQuadraticDecimation
    - vtkSmoothPolyDataFilter

    For now the parameters (eg. SetTargetReduction, RelaxationFactor etc etc) are fixed but
    in the future it would be nicer to have an adaptive method (maybe using vtkMeshQuality?)
    """
    if self.shown_table != "tabGeology":
        self.print_terminal(" -- Only geological objects can be retopologized -- ")
        return
    if not self.selected_uids:
        self.print_terminal("No input data selected.")
        return
    else:
        # Deep copy list of selected uids needed otherwise problems can arise if the main geology table is deseselcted while the dataframe is being built
        input_uids = deepcopy(self.selected_uids)

        for uid in input_uids:
            if isinstance(self.geol_coll.get_uid_vtk_obj(uid), TriSurf):
                mesh = self.geol_coll.get_uid_vtk_obj(uid)
                dec = vtkQuadricDecimation()
                dec.SetInputData(mesh)
                # tr.SetSourceData(bord)
                dec.SetTargetReduction(float(dec_int))
                dec.VolumePreservationOn()
                dec.Update()

                smooth = vtkSmoothPolyDataFilter()
                smooth.SetInputConnection(dec.GetOutputPort())

                # smooth.SetInputData(surf)
                smooth.SetNumberOfIterations(int(n_iter))
                smooth.SetRelaxationFactor(float(rel_fac))
                smooth.BoundarySmoothingOn()
                smooth.FeatureEdgeSmoothingOn()
                smooth.Update()

                clean = vtkCleanPolyData()
                clean.SetInputConnection(smooth.GetOutputPort())
                clean.Update()

                if mode:
                    return clean.GetOutput()
                else:
                    # Create deepcopy of the geological entity dictionary.
                    surf_dict = deepcopy(self.geol_coll.entity_dict)
                    surf_dict["name"] = self.geol_coll.get_uid_name(uid) + "_retopo"
                    surf_dict["feature"] = self.geol_coll.get_uid_feature(uid)
                    surf_dict["scenario"] = self.geol_coll.get_uid_scenario(uid)
                    surf_dict["role"] = self.geol_coll.get_uid_role(uid)
                    surf_dict["topology"] = "TriSurf"
                    surf_dict["vtk_obj"] = TriSurf()
                    surf_dict["vtk_obj"].ShallowCopy(clean.GetOutput())
                    surf_dict["vtk_obj"].Modified()

                    if surf_dict["vtk_obj"].points_number > 0:
                        self.geol_coll.add_entity_from_dict(surf_dict)
                    else:
                        self.print_terminal(" -- empty object -- ")
            else:
                self.print_terminal(" -- Error input type: only TriSurf type -- ")
                return
