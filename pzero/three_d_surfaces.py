"""three_d_surfaces.py
PZero© Andrea Bistacchi"""

from copy import deepcopy

from uuid import uuid4

from PySide6.QtWidgets import QDockWidget

from pyvista import PolyData as pv_PolyData

from numpy import abs as np_abs
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
from numpy import array as np_array
from numpy import sum as np_sum

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
    vtkOBBTree,
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


def transform_vtk_from_aligned_to_world(vtk_obj, obb_info):
    """
    Transform a VTK object from boundary-aligned model coordinates back to world space.

    Unlike `transform_vtk_to_obb`, this is for geometry sampled directly in the
    aligned model space where the boundary centre is the XY origin.
    """
    from numpy import cos as np_cos
    from numpy import sin as np_sin
    from numpy import array as np_array

    if not obb_info["has_obb"]:
        return vtk_obj

    points = vtk_obj.points
    if points is None or len(points) == 0:
        return vtk_obj

    angle = obb_info["angle"]
    center = obb_info["center"]
    c, s = np_cos(angle), np_sin(angle)
    R_to_world = np_array([[c, -s], [s, c]])

    xy_world = (R_to_world @ points[:, :2].T).T + center
    points[:, 0] = xy_world[:, 0]
    points[:, 1] = xy_world[:, 1]
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


def _compute_fault_geometric_features(points):
    """
    Compute geometric features of fault data using PCA (Principal Component Analysis).
    
    Analyzes the point cloud to determine the fault's center, principal axes,
    and their lengths. Used for LoopStructural fault interpolation parameters.
    
    Args:
        points: numpy array of shape (n, 3) with X, Y, Z coordinates
    
    Returns:
        center: numpy array [x, y, z] of the fault center
        axes: numpy array of shape (3, 3) with principal axes as rows
              (major, intermediate, minor axes - sorted by length descending)
        lengths: numpy array [major_len, intermediate_len, minor_len]
    """
    from numpy import array as np_array
    from numpy import mean as np_mean
    from numpy import cov as np_cov
    from numpy import linalg as np_linalg
    from numpy import argsort as np_argsort
    from numpy import ptp as np_ptp
    from numpy import identity as np_identity
    from numpy import cross as np_cross
    from numpy import dot as np_dot

    if points is None or len(points) == 0:
        return np_array([0, 0, 0]), np_identity(3), np_array([0, 0, 0])
    
    points = np_array(points)
    center = np_mean(points, axis=0)
    
    if len(points) <= 1:
        return center, np_identity(3), np_zeros(3)
    
    centered_points = points - center
    
    if len(points) == 2:
        # Special handling for 2 points (a line)
        vec = centered_points[1] - centered_points[0]
        length1 = np_linalg.norm(vec)
        axis1 = vec / length1 if length1 > 1e-6 else np_array([1, 0, 0])
        
        # Create two orthogonal axes
        temp_axis = np_array([0, 0, 1]) if abs(np_dot(axis1, np_array([0, 0, 1]))) < 0.9 else np_array([0, 1, 0])
        axis2 = np_cross(axis1, temp_axis)
        axis2_norm = np_linalg.norm(axis2)
        if axis2_norm > 1e-6:
            axis2 = axis2 / axis2_norm
        
        axis3 = np_cross(axis1, axis2)
        axis3_norm = np_linalg.norm(axis3)
        if axis3_norm > 1e-6:
            axis3 = axis3 / axis3_norm
        
        return center, np_array([axis1, axis2, axis3]), np_array([length1, 0, 0])
    
    # Calculate covariance matrix
    cov_matrix = np_cov(centered_points.T)
    eigenvalues, eigenvectors_cols = np_linalg.eigh(cov_matrix)
    
    # Sort by eigenvalues in descending order
    sort_idx = np_argsort(eigenvalues)[::-1]
    axes = eigenvectors_cols[:, sort_idx].T  # Transpose to get axes as rows
    
    # Compute lengths based on point cloud extents along these axes
    projected_coords = centered_points @ axes.T
    lengths = np_ptp(projected_coords, axis=0)
    
    # Ensure axes are normalized
    for i in range(3):
        norm = np_linalg.norm(axes[i])
        if norm > 1e-6:
            axes[i] = axes[i] / norm
        else:
            default_axes = np_identity(3)
            axes[i] = default_axes[i]
    
    # Sort axes by length (descending)
    sort_idx = np_argsort(lengths)[::-1]
    axes = axes[sort_idx]
    lengths = lengths[sort_idx]
    
    # Ensure right-handed coordinate system
    if np_dot(np_cross(axes[0], axes[1]), axes[2]) < 0:
        axes[2] = -axes[2]
    
    return center, axes, lengths


def _normalise_fault_obb_lengths(
    lengths,
    zero_tol=1e-6,
    minor_ratio=0.1,
    collapse_ratio=1e-3,
):
    """
    Prevent numerically flat fault OBBs from carrying a zero minor length.

    LoopStructural needs a non-zero fault thickness. When the OBB collapses
    the minor axis for a very planar point set, reuse the fault's own in-plane
    scale and assign a default thickness as a fraction of the major length.
    """
    from numpy import array as np_array

    lengths = np_array(lengths, dtype=float).copy()
    if lengths.size < 3:
        return lengths

    reference_length = 0.0
    if lengths[0] > zero_tol:
        reference_length = float(lengths[0])
    elif lengths[1] > zero_tol:
        reference_length = float(lengths[1])

    collapsed_minor_limit = max(zero_tol, reference_length * collapse_ratio)
    if lengths[2] <= collapsed_minor_limit and reference_length > zero_tol:
        lengths[2] = max(reference_length * minor_ratio, 1e-3)

    return lengths


def _compute_fault_geometric_features_obb(points):
    """
    Compute fault geometric features using vtkOBBTree minimum-volume OBB.

    Returns:
        center: numpy array [x, y, z] of OBB center
        axes: numpy array of shape (3, 3) with unit vectors as rows
              (major, intermediate, minor)
        lengths: numpy array [major_len, intermediate_len, minor_len]
    """
    from numpy import array as np_array
    from numpy import identity as np_identity
    from numpy import linalg as np_linalg
    from numpy import argsort as np_argsort
    from numpy import cross as np_cross
    from numpy import dot as np_dot

    if points is None or len(points) == 0:
        return np_array([0, 0, 0]), np_identity(3), np_array([0, 0, 0])

    points = np_array(points)
    if len(points) <= 2:
        # Degenerate geometries are handled more robustly by PCA fallback.
        return _compute_fault_geometric_features(points)

    vtk_points = vtkPoints()
    for point in points:
        vtk_points.InsertNextPoint(float(point[0]), float(point[1]), float(point[2]))

    corner = [0.0, 0.0, 0.0]
    max_axis_vec = [0.0, 0.0, 0.0]
    mid_axis_vec = [0.0, 0.0, 0.0]
    min_axis_vec = [0.0, 0.0, 0.0]
    sizes = [0.0, 0.0, 0.0]

    try:
        vtkOBBTree.ComputeOBB(
            vtk_points, corner, max_axis_vec, mid_axis_vec, min_axis_vec, sizes
        )
    except Exception:
        return _compute_fault_geometric_features(points)

    axis_vectors = np_array([max_axis_vec, mid_axis_vec, min_axis_vec], dtype=float)
    lengths = np_array([np_linalg.norm(vec) for vec in axis_vectors], dtype=float)

    axes = np_identity(3)
    for i in range(3):
        if lengths[i] > 1e-9:
            axes[i] = axis_vectors[i] / lengths[i]

    # Sort to guarantee major/intermediate/minor ordering.
    sort_idx = np_argsort(lengths)[::-1]
    axes = axes[sort_idx]
    lengths = lengths[sort_idx]

    center = np_array(corner, dtype=float) + 0.5 * (
        axis_vectors[0] + axis_vectors[1] + axis_vectors[2]
    )

    lengths = _normalise_fault_obb_lengths(lengths)

    # Keep a right-handed frame.
    if np_dot(np_cross(axes[0], axes[1]), axes[2]) < 0:
        axes[2] = -axes[2]

    return center, axes, lengths


def _compute_fault_box_in_axes(points, axes):
    """
    Compute box centre and lengths for points in a supplied orthonormal basis.

    This keeps the extents consistent after the in-plane fault basis is rotated
    to the strike/dip convention used for LoopStructural fault parameters.
    """
    from numpy import array as np_array
    from numpy import identity as np_identity
    from numpy import cross as np_cross
    from numpy import dot as np_dot
    from numpy import linalg as np_linalg

    if points is None or len(points) == 0:
        return np_array([0.0, 0.0, 0.0]), np_identity(3), np_array([0.0, 0.0, 0.0])

    points = np_array(points, dtype=float)
    axes = np_array(axes, dtype=float)
    if axes.shape != (3, 3):
        axes = np_identity(3)

    normed_axes = np_identity(3)
    for i in range(3):
        axis_norm = np_linalg.norm(axes[i])
        if axis_norm > 1e-9:
            normed_axes[i] = axes[i] / axis_norm

    if np_dot(np_cross(normed_axes[0], normed_axes[1]), normed_axes[2]) < 0.0:
        normed_axes[2] = -normed_axes[2]

    projected_coords = points @ normed_axes.T
    min_coords = projected_coords.min(axis=0)
    max_coords = projected_coords.max(axis=0)
    lengths = _normalise_fault_obb_lengths(max_coords - min_coords)
    center_local = 0.5 * (min_coords + max_coords)
    center = center_local @ normed_axes

    return center, normed_axes, lengths


def _project_vector_to_plane(vector, normal, fallback=None):
    """Project a vector onto a plane and normalize the result."""
    from numpy import array as np_array
    from numpy import dot as np_dot
    from numpy import linalg as np_linalg

    vector = np_array(vector, dtype=float)
    normal = np_array(normal, dtype=float)
    projected = vector - np_dot(vector, normal) * normal
    projected_norm = np_linalg.norm(projected)
    if projected_norm > 1e-9:
        return projected / projected_norm
    if fallback is not None:
        fallback_vec = np_array(fallback, dtype=float)
        fallback_projected = fallback_vec - np_dot(fallback_vec, normal) * normal
        fallback_norm = np_linalg.norm(fallback_projected)
        if fallback_norm > 1e-9:
            return fallback_projected / fallback_norm
    return None


def _principal_direction_from_points(points, fallback=None):
    """Return the dominant PCA direction for a 3D point cloud."""
    from numpy import array as np_array
    from numpy import argsort as np_argsort
    from numpy import cov as np_cov
    from numpy import linalg as np_linalg
    from numpy import mean as np_mean

    points = np_array(points, dtype=float)
    if points.ndim != 2 or points.shape[1] < 3 or points.shape[0] < 2:
        points = np_array([])
    if points.size == 0:
        if fallback is None:
            return None
        fallback = np_array(fallback, dtype=float)
        fallback_norm = np_linalg.norm(fallback)
        return fallback / fallback_norm if fallback_norm > 1e-9 else None

    if points.shape[0] == 2:
        direction = points[1] - points[0]
    else:
        centered = points - np_mean(points, axis=0)
        cov_matrix = np_cov(centered.T)
        eigenvalues, eigenvectors_cols = np_linalg.eigh(cov_matrix)
        direction = eigenvectors_cols[:, np_argsort(eigenvalues)[::-1][0]]

    direction_norm = np_linalg.norm(direction)
    if direction_norm > 1e-9:
        return direction / direction_norm
    if fallback is None:
        return None
    fallback = np_array(fallback, dtype=float)
    fallback_norm = np_linalg.norm(fallback)
    return fallback / fallback_norm if fallback_norm > 1e-9 else None


def _infer_fault_normal(points, explicit_normal=None, trace_points=None, fallback_axes=None):
    """
    Infer a stable fault normal from explicit normals first, then 3D geometry.

    `PolyLine` trace points are only used as a last-resort vertical-fault
    assumption when the merged geometry is effectively line-like.
    """
    from numpy import array as np_array
    from numpy import argsort as np_argsort
    from numpy import cov as np_cov
    from numpy import cross as np_cross
    from numpy import dot as np_dot
    from numpy import linalg as np_linalg
    from numpy import mean as np_mean

    def _normed(vec, fallback=None):
        if vec is None:
            vec = np_array([])
        vec = np_array(vec, dtype=float)
        vec_norm = np_linalg.norm(vec)
        if vec_norm > 1e-9:
            return vec / vec_norm
        if fallback is not None:
            fallback_vec = np_array(fallback, dtype=float)
            fallback_norm = np_linalg.norm(fallback_vec)
            if fallback_norm > 1e-9:
                return fallback_vec / fallback_norm
        return np_array([0.0, 0.0, 1.0], dtype=float)

    fallback_normal = None
    if fallback_axes is not None:
        fallback_axes = np_array(fallback_axes, dtype=float)
        if fallback_axes.shape == (3, 3):
            fallback_normal = _normed(fallback_axes[2], fallback=[0.0, 0.0, 1.0])

    if explicit_normal is not None:
        normal = _normed(explicit_normal, fallback=fallback_normal)
        if fallback_normal is not None and np_dot(normal, fallback_normal) < 0.0:
            normal = -normal
        return {
            "normal": normal,
            "source": "input_normals",
            "line_ratio": float("nan"),
            "plane_ratio": float("nan"),
            "line_like": False,
        }

    points = np_array(points, dtype=float)
    if points.ndim == 2 and points.shape[0] >= 3 and points.shape[1] >= 3:
        centered = points - np_mean(points, axis=0)
        cov_matrix = np_cov(centered.T)
        eigenvalues, eigenvectors_cols = np_linalg.eigh(cov_matrix)
        sort_idx = np_argsort(eigenvalues)[::-1]
        eigenvalues = np_array(eigenvalues[sort_idx], dtype=float)
        axes = eigenvectors_cols[:, sort_idx].T
        if np_dot(np_cross(axes[0], axes[1]), axes[2]) < 0.0:
            axes[2] = -axes[2]

        line_ratio = (
            float(eigenvalues[1] / eigenvalues[0]) if eigenvalues[0] > 1e-12 else 0.0
        )
        plane_ratio = (
            float(eigenvalues[2] / eigenvalues[1]) if eigenvalues[1] > 1e-12 else float("inf")
        )
        line_like = line_ratio < 0.02
        if not line_like:
            normal = _normed(axes[2], fallback=fallback_normal)
            if fallback_normal is not None and np_dot(normal, fallback_normal) < 0.0:
                normal = -normal
            return {
                "normal": normal,
                "source": "best_fit_plane",
                "line_ratio": line_ratio,
                "plane_ratio": plane_ratio,
                "line_like": False,
            }

    trace_direction = _principal_direction_from_points(trace_points)
    if trace_direction is not None:
        vertical_normal = np_cross(trace_direction, np_array([0.0, 0.0, 1.0], dtype=float))
        vertical_normal = _normed(vertical_normal, fallback=fallback_normal)
        if fallback_normal is not None and np_dot(vertical_normal, fallback_normal) < 0.0:
            vertical_normal = -vertical_normal
        return {
            "normal": vertical_normal,
            "source": "trace_vertical_assumption",
            "line_ratio": float("nan"),
            "plane_ratio": float("nan"),
            "line_like": True,
        }

    normal = _normed(fallback_normal, fallback=[0.0, 0.0, 1.0])
    return {
        "normal": normal,
        "source": "obb_minor_axis_fallback",
        "line_ratio": float("nan"),
        "plane_ratio": float("nan"),
        "line_like": True,
    }


def _orient_fault_axes_for_rake(axes, center_normal=None, trace_points=None):
    """
    Build a stable support frame for a fault from the OBB and inferred normal.

    The returned basis is fixed to the input geometry:
    - axis 0: trace-like direction inside the fault plane
    - axis 1: dip-like direction inside the fault plane
    - axis 2: fault normal
    """
    from numpy import array as np_array
    from numpy import cross as np_cross
    from numpy import dot as np_dot
    from numpy import linalg as np_linalg
    from numpy import identity as np_identity

    axes = np_array(axes, dtype=float)
    if axes.shape != (3, 3):
        return np_identity(3)

    def _normed(vec, fallback=None):
        n = np_linalg.norm(vec)
        if n > 1e-9:
            return vec / n
        if fallback is not None:
            f = np_array(fallback, dtype=float)
            nf = np_linalg.norm(f)
            if nf > 1e-9:
                return f / nf
        return np_array([1.0, 0.0, 0.0], dtype=float)

    major = _normed(axes[0], fallback=[1.0, 0.0, 0.0])
    intermediate = _normed(axes[1], fallback=[0.0, 1.0, 0.0])
    normal = _normed(center_normal, fallback=axes[2])

    preferred_trace = _project_vector_to_plane(major, normal, fallback=intermediate)
    trace_from_polyline = _project_vector_to_plane(
        _principal_direction_from_points(trace_points, fallback=preferred_trace),
        normal,
        fallback=preferred_trace,
    )
    trace_axis = trace_from_polyline if trace_from_polyline is not None else preferred_trace
    if trace_axis is None:
        trace_axis = _project_vector_to_plane(intermediate, normal, fallback=[1.0, 0.0, 0.0])
    trace_axis = _normed(trace_axis, fallback=[1.0, 0.0, 0.0])

    if preferred_trace is not None and np_dot(trace_axis, preferred_trace) < 0.0:
        trace_axis = -trace_axis

    dip_axis = _normed(np_cross(normal, trace_axis), fallback=[0.0, 0.0, 1.0])
    up_proj = _project_vector_to_plane([0.0, 0.0, 1.0], normal, fallback=[0.0, 1.0, 0.0])
    if up_proj is not None and np_dot(dip_axis, up_proj) < 0.0:
        trace_axis = -trace_axis
        dip_axis = -dip_axis

    if np_dot(np_cross(trace_axis, dip_axis), normal) < 0.0:
        dip_axis = -dip_axis

    return np_array([trace_axis, dip_axis, normal], dtype=float)


def _compute_fault_slip_vector_from_rake(axes, rake_deg):
    """
    Convert rake angle on fault plane to a 3D unit slip vector.

    Rake is interpreted in the local fault plane basis:
    - 0 deg: along major (strike) axis
    - +90 deg: along intermediate axis
    - -90 deg: opposite intermediate axis
    """
    from numpy import array as np_array
    from numpy import cross as np_cross
    from numpy import dot as np_dot
    from numpy import identity as np_identity
    from numpy import linalg as np_linalg
    from numpy import deg2rad as np_deg2rad
    from numpy import cos as np_cos
    from numpy import sin as np_sin

    axes = np_array(axes, dtype=float)
    if axes.shape != (3, 3):
        axes = np_identity(3)

    def _normed(vec, fallback=None):
        v = np_array(vec, dtype=float)
        n = np_linalg.norm(v)
        if n > 1e-9:
            return v / n
        if fallback is not None:
            f = np_array(fallback, dtype=float)
            nf = np_linalg.norm(f)
            if nf > 1e-9:
                return f / nf
        return np_array([1.0, 0.0, 0.0], dtype=float)

    major = _normed(axes[0], fallback=[1.0, 0.0, 0.0])
    intermediate = _normed(axes[1], fallback=[0.0, 1.0, 0.0])
    normal = _normed(axes[2], fallback=np_cross(major, intermediate))

    # Re-project to the fault plane and re-normalize to guarantee an orthonormal in-plane basis.
    major = _normed(
        major - np_dot(major, normal) * normal,
        fallback=np_cross(intermediate, normal),
    )
    intermediate = _normed(
        intermediate - np_dot(intermediate, normal) * normal,
        fallback=np_cross(normal, major),
    )

    # Keep right-handed local basis.
    if np_dot(np_cross(major, intermediate), normal) < 0.0:
        intermediate = -intermediate

    rake_rad = np_deg2rad(float(rake_deg))
    rake_components = np_array([np_cos(rake_rad), np_sin(rake_rad)], dtype=float)
    slip_vector = rake_components[0] * major + rake_components[1] * intermediate

    # Numerical guard: keep slip vector exactly in-plane and normalized.
    slip_vector = slip_vector - np_dot(slip_vector, normal) * normal
    slip_vector = _normed(slip_vector, fallback=major)

    return slip_vector, major, intermediate, normal, rake_components


def _build_obb_wireframe_polydata(center, axes, lengths):
    """Build a line-only pyvista PolyData representing an oriented 3D box."""
    from numpy import array as np_array

    center = np_array(center, dtype=float)
    axes = np_array(axes, dtype=float)
    half_lengths = 0.5 * np_array(lengths, dtype=float)

    # Local box corners in [-1, 1]^3.
    corner_signs = np_array(
        [
            [-1, -1, -1],
            [1, -1, -1],
            [1, 1, -1],
            [-1, 1, -1],
            [-1, -1, 1],
            [1, -1, 1],
            [1, 1, 1],
            [-1, 1, 1],
        ],
        dtype=float,
    )

    corners = center + (
        corner_signs[:, [0]] * half_lengths[0] * axes[[0]]
        + corner_signs[:, [1]] * half_lengths[1] * axes[[1]]
        + corner_signs[:, [2]] * half_lengths[2] * axes[[2]]
    )

    edge_pairs = [
        (0, 1), (1, 2), (2, 3), (3, 0),
        (4, 5), (5, 6), (6, 7), (7, 4),
        (0, 4), (1, 5), (2, 6), (3, 7),
    ]
    lines = []
    for start_idx, end_idx in edge_pairs:
        lines.extend([2, start_idx, end_idx])

    return pv_PolyData(corners, lines=np_array(lines))


def _extract_fault_surface_local_grid(model, fault_name, center, axes, lengths, target_spacing):
    """
    Extract a fault surface on an oriented local grid tied to the fault OBB.

    Sampling inside the fault support box keeps the exported fault surface
    bounded to the same OBB used for the fault displacement support.
    """
    from pyvista import StructuredGrid as pv_StructuredGrid
    from numpy import array as np_array
    from numpy import linspace as np_linspace
    from numpy import meshgrid as np_meshgrid
    from numpy import maximum as np_maximum
    from numpy import isnan as np_isnan

    center = np_array(center, dtype=float)
    axes = np_array(axes, dtype=float)
    lengths = np_array(lengths, dtype=float)

    if axes.shape != (3, 3):
        return None

    spacing = float(target_spacing) if target_spacing is not None and target_spacing > 0 else 1.0

    fault_feature = model.get_feature_by_name(fault_name)
    surface_feature = fault_feature[0] if hasattr(fault_feature, "__getitem__") else fault_feature

    # Evaluate on an oriented world/aligned grid, but query LoopStructural in
    # model-local coordinates. The model internally subtracts `model.origin`
    # from all data, so sampling directly in absolute coordinates misses the
    # fault entirely.
    expansion_candidates = [
        np_array([1.05, 1.05, 1.50], dtype=float),
        np_array([1.15, 1.15, 2.50], dtype=float),
        np_array([1.30, 1.30, 4.00], dtype=float),
    ]
    min_lengths = np_array([spacing * 2.0, spacing * 2.0, spacing * 4.0], dtype=float)

    for padding in expansion_candidates:
        safe_lengths = np_maximum(lengths * padding, min_lengths)

        nx = max(25, int(np_around(safe_lengths[0] / spacing)) + 1)
        ny = max(17, int(np_around(safe_lengths[1] / spacing)) + 1)
        nz = max(9, int(np_around(safe_lengths[2] / spacing)) + 1)

        u = np_linspace(-0.5 * safe_lengths[0], 0.5 * safe_lengths[0], nx)
        v = np_linspace(-0.5 * safe_lengths[1], 0.5 * safe_lengths[1], ny)
        w = np_linspace(-0.5 * safe_lengths[2], 0.5 * safe_lengths[2], nz)
        uu, vv, ww = np_meshgrid(u, v, w, indexing="ij")

        points_world = (
            center[None, None, None, :]
            + uu[..., None] * axes[0]
            + vv[..., None] * axes[1]
            + ww[..., None] * axes[2]
        )
        grid = pv_StructuredGrid(
            points_world[..., 0], points_world[..., 1], points_world[..., 2]
        )

        eval_points = (
            model.scale(grid.points, inplace=False)
            if hasattr(model, "scale")
            else grid.points
        )
        scalar_field = np_array(
            surface_feature.evaluate_value(eval_points),
            dtype=float,
        )
        valid_values = scalar_field[~np_isnan(scalar_field)]
        if valid_values.size == 0:
            continue
        if valid_values.min() > 0.0 or valid_values.max() < 0.0:
            continue

        grid.point_data["fault_scalar"] = scalar_field
        contour = grid.contour(isosurfaces=[0.0], scalars="fault_scalar")
        if contour is not None and contour.n_points > 0:
            return contour

    return None


def _safe_relative_time(value):
    """Convert legend time values to a usable float, preserving NaN for unknown ages."""
    try:
        time_value = float(value)
    except (TypeError, ValueError):
        return float("nan")
    if time_value == -999999.0:
        return float("nan")
    return time_value


def _sorted_fault_names_by_time(fault_data, older_first=False):
    """Return fault names sorted by legend time with NaN values last."""

    def _key(fault_name):
        time_value = _safe_relative_time(fault_data[fault_name].get("time"))
        is_nan = time_value != time_value
        if older_first:
            order_value = -time_value if not is_nan else 0.0
        else:
            order_value = time_value if not is_nan else 0.0
        return (is_nan, order_value, fault_name)

    return sorted(fault_data.keys(), key=_key)


def _fault_affects_sequence(fault_time, sequence_youngest_time):
    """
    Determine whether a fault should affect a geological sequence.

    Lower legend times are younger. At sequence granularity we use the youngest
    interface in the sequence as the conservative cutoff, so an older fault does
    not cut any younger interface contained in that series.
    """
    fault_time = _safe_relative_time(fault_time)
    sequence_youngest_time = _safe_relative_time(sequence_youngest_time)
    if fault_time != fault_time or sequence_youngest_time != sequence_youngest_time:
        return True
    return fault_time <= sequence_youngest_time


def _make_fault_group_name(feature, scenario, fallback_name="fault"):
    """Create a stable LoopStructural feature name for a merged fault group."""

    def _clean(value):
        text = str(value).strip()
        if not text or text == "undef":
            return ""
        cleaned = "".join(ch if ch.isalnum() else "_" for ch in text)
        while "__" in cleaned:
            cleaned = cleaned.replace("__", "_")
        return cleaned.strip("_")

    feature_token = _clean(feature)
    scenario_token = _clean(scenario)
    fallback_token = _clean(fallback_name) or "fault"
    tokens = ["fault", feature_token or fallback_token]
    if scenario_token:
        tokens.append(scenario_token)
    return "_".join(tokens)


def _compute_fault_loop_geometry(center, axes, lengths, rake_deg):
    """Return LoopStructural's rotating trace/slip/normal basis for a support box."""
    from numpy import array as np_array
    from numpy import cross as np_cross
    from numpy import dot as np_dot
    from numpy import linalg as np_linalg

    center = np_array(center, dtype=float)
    axes = np_array(axes, dtype=float)
    lengths = _normalise_fault_obb_lengths(np_array(lengths, dtype=float))

    (
        slip_vector,
        strike_axis,
        dip_axis,
        fault_normal,
        rake_components,
    ) = _compute_fault_slip_vector_from_rake(axes, rake_deg)

    loop_trace_axis = np_cross(fault_normal, slip_vector)
    loop_trace_norm = np_linalg.norm(loop_trace_axis)
    if loop_trace_norm <= 1e-9:
        loop_trace_axis = strike_axis
    else:
        loop_trace_axis = loop_trace_axis / loop_trace_norm

    loop_axes = np_array([loop_trace_axis, slip_vector, fault_normal], dtype=float)
    if np_dot(np_cross(loop_axes[0], loop_axes[1]), loop_axes[2]) < 0.0:
        loop_axes[0] = -loop_axes[0]

    corners = _build_fault_box_corners(center, axes, lengths)
    _, _, loop_lengths = _compute_fault_box_in_axes(corners, loop_axes)

    return {
        "loop_axes": loop_axes,
        "loop_lengths": _normalise_fault_obb_lengths(loop_lengths),
        "loop_trace_axis": loop_axes[0],
        "slip_vector": slip_vector,
        "strike_axis": strike_axis,
        "dip_axis": dip_axis,
        "fault_normal": fault_normal,
        "rake_components": rake_components,
    }


def _compute_fault_geometry_for_rake(
    points, plane_axes, center_normal, rake_deg, trace_points=None
):
    """
    Build fault geometry while keeping the support box tied to the input OBB.

    The support frame stays fixed to the inferred trace-like / dip-like axes.
    LoopStructural's rotating trace axis is derived separately from rake.
    """
    from numpy import array as np_array
    from numpy import identity as np_identity

    points = np_array(points, dtype=float)
    oriented_plane_axes = _orient_fault_axes_for_rake(
        plane_axes, center_normal=center_normal, trace_points=trace_points
    )

    if points.size == 0:
        center = np_array([0.0, 0.0, 0.0], dtype=float)
        lengths = np_array([0.0, 0.0, 0.0], dtype=float)
        oriented_plane_axes = np_identity(3)
    else:
        center, oriented_plane_axes, lengths = _compute_fault_box_in_axes(
            points, oriented_plane_axes
        )

    loop_geometry = _compute_fault_loop_geometry(center, oriented_plane_axes, lengths, rake_deg)

    return {
        "center": center,
        "axes": oriented_plane_axes,
        "lengths": _normalise_fault_obb_lengths(lengths),
        "plane_axes": oriented_plane_axes,
        "trace_axis": oriented_plane_axes[0],
        "normal": oriented_plane_axes[2],
        "strike_axis": loop_geometry["strike_axis"],
        "dip_axis": loop_geometry["dip_axis"],
        "slip_axis": loop_geometry["slip_vector"],
        "slip_vector": loop_geometry["slip_vector"],
        "rake_components": loop_geometry["rake_components"],
        "loop_axes": loop_geometry["loop_axes"],
        "loop_lengths": loop_geometry["loop_lengths"],
        "loop_trace_axis": loop_geometry["loop_trace_axis"],
    }


def _compute_scaled_fault_geometry(
    fault_info, rake_deg, scale_factors=None, normal_override=None
):
    """Return support-box geometry and LoopStructural lengths for the requested rake."""
    from numpy import array as np_array

    if scale_factors is None:
        scale_factors = [1.0, 1.0, 1.0]

    geometry = _compute_fault_geometry_for_rake(
        fault_info.get("points", []),
        fault_info.get("obb_axes", fault_info.get("plane_axes", fault_info.get("axes"))),
        normal_override if normal_override is not None else fault_info.get("center_normal"),
        rake_deg,
        trace_points=fault_info.get("trace_points"),
    )
    scales = np_array(scale_factors, dtype=float)
    geometry["scaled_lengths"] = _normalise_fault_obb_lengths(
        geometry["lengths"] * scales
    )
    scaled_loop_geometry = _compute_fault_loop_geometry(
        geometry["center"],
        geometry["axes"],
        geometry["scaled_lengths"],
        rake_deg,
    )
    geometry["scaled_loop_lengths"] = scaled_loop_geometry["loop_lengths"]
    geometry["loop_axes"] = scaled_loop_geometry["loop_axes"]
    geometry["loop_lengths"] = scaled_loop_geometry["loop_lengths"]
    geometry["loop_trace_axis"] = scaled_loop_geometry["loop_trace_axis"]
    geometry["slip_vector"] = scaled_loop_geometry["slip_vector"]
    geometry["slip_axis"] = scaled_loop_geometry["slip_vector"]
    geometry["strike_axis"] = scaled_loop_geometry["strike_axis"]
    geometry["dip_axis"] = scaled_loop_geometry["dip_axis"]
    geometry["normal"] = scaled_loop_geometry["fault_normal"]
    geometry["rake_components"] = scaled_loop_geometry["rake_components"]
    return geometry


def _build_fault_box_corners(center, axes, lengths):
    """Return the eight corners of an oriented fault support box."""
    from numpy import array as np_array

    center = np_array(center, dtype=float)
    axes = np_array(axes, dtype=float)
    half_lengths = 0.5 * np_array(lengths, dtype=float)
    signs = np_array(
        [
            [-1, -1, -1],
            [1, -1, -1],
            [1, 1, -1],
            [-1, 1, -1],
            [-1, -1, 1],
            [1, -1, 1],
            [1, 1, 1],
            [-1, 1, 1],
        ],
        dtype=float,
    )
    return center + (
        signs[:, [0]] * half_lengths[0] * axes[[0]]
        + signs[:, [1]] * half_lengths[1] * axes[[1]]
        + signs[:, [2]] * half_lengths[2] * axes[[2]]
    )


def _point_to_fault_box_distance(point, center, axes, lengths):
    """Distance from a point to an oriented fault support box."""
    from numpy import abs as np_abs
    from numpy import array as np_array
    from numpy import maximum as np_maximum

    point = np_array(point, dtype=float)
    center = np_array(center, dtype=float)
    axes = np_array(axes, dtype=float)
    half_lengths = 0.5 * np_array(lengths, dtype=float)
    local_point = (point - center) @ axes.T
    delta = np_abs(local_point) - half_lengths
    outside = np_maximum(delta, 0.0)
    return float(np_sqrt(np_sum(outside**2)))


def _fault_bounds_overlap(bounds_a, bounds_b, padding=0.0):
    """Check overlap between two axis-aligned bounds tuples."""
    for dim_idx in range(3):
        min_a = bounds_a[0][dim_idx] - padding
        max_a = bounds_a[1][dim_idx] + padding
        min_b = bounds_b[0][dim_idx] - padding
        max_b = bounds_b[1][dim_idx] + padding
        if max_a < min_b or max_b < min_a:
            return False
    return True


def _compute_fault_relation_suggestions(fault_data, default_rake=-90.0):
    """
    Compute heuristic abutting/splay suggestions for manual confirmation.

    Suggestions are intentionally conservative:
    - only younger-to-older relations are considered
    - equal or unknown times are ignored
    - splay is suggested only for close faults with small acute trace angles
    """
    from numpy import clip as np_clip
    from numpy import degrees as np_degrees
    from numpy import arccos as np_arccos
    from numpy import dot as np_dot

    suggestions = {
        fault_name: {
            "has_abutting": False,
            "abutting_fault": None,
            "has_splay": False,
            "splay_fault": None,
        }
        for fault_name in fault_data.keys()
    }
    if len(fault_data) < 2:
        return suggestions

    geometry_cache = {}
    for fault_name, fault_info in fault_data.items():
        geometry = _compute_scaled_fault_geometry(
            fault_info, default_rake, scale_factors=[1.0, 1.0, 1.0]
        )
        corners = _build_fault_box_corners(
            geometry["center"], geometry["axes"], geometry["scaled_lengths"]
        )
        mins = corners.min(axis=0)
        maxs = corners.max(axis=0)
        tips = np_array(
            [
                geometry["center"] - 0.5 * geometry["scaled_lengths"][0] * geometry["axes"][0],
                geometry["center"] + 0.5 * geometry["scaled_lengths"][0] * geometry["axes"][0],
            ],
            dtype=float,
        )
        geometry_cache[fault_name] = {
            "center": geometry["center"],
            "axes": geometry["axes"],
            "lengths": geometry["scaled_lengths"],
            "bounds": (mins, maxs),
            "tips": tips,
            "time": _safe_relative_time(fault_info.get("time")),
        }

    for source_fault in _sorted_fault_names_by_time(fault_data, older_first=False):
        source_info = geometry_cache[source_fault]
        source_time = source_info["time"]
        if source_time != source_time:
            continue

        best_splay = None
        best_abutting = None

        for target_fault in _sorted_fault_names_by_time(fault_data, older_first=True):
            if target_fault == source_fault:
                continue

            target_info = geometry_cache[target_fault]
            target_time = target_info["time"]
            if target_time != target_time or source_time >= target_time:
                continue

            acute_angle = float(
                np_degrees(
                    np_arccos(
                        np_clip(
                            np_abs(np_dot(source_info["axes"][0], target_info["axes"][0])),
                            -1.0,
                            1.0,
                        )
                    )
                )
            )
            max_major = max(
                source_info["lengths"][0], target_info["lengths"][0], 1e-3
            )
            overlap = _fault_bounds_overlap(
                source_info["bounds"], target_info["bounds"], padding=max_major * 0.05
            )
            tip_distance = min(
                _point_to_fault_box_distance(
                    tip,
                    target_info["center"],
                    target_info["axes"],
                    target_info["lengths"],
                )
                for tip in source_info["tips"]
            )
            near_threshold = max(
                max_major * 0.2,
                source_info["lengths"][2] + target_info["lengths"][2],
                1.0,
            )
            if not (overlap or tip_distance <= near_threshold):
                continue

            if acute_angle <= 30.0 and tip_distance <= max_major * 0.35:
                score = tip_distance + 0.1 * acute_angle
                if best_splay is None or score < best_splay[0]:
                    best_splay = (score, target_fault)
            elif acute_angle <= 85.0:
                score = tip_distance + 0.05 * acute_angle
                if overlap:
                    score *= 0.7
                if best_abutting is None or score < best_abutting[0]:
                    best_abutting = (score, target_fault)

        if best_splay is not None:
            suggestions[source_fault]["has_splay"] = True
            suggestions[source_fault]["splay_fault"] = best_splay[1]
        elif best_abutting is not None:
            suggestions[source_fault]["has_abutting"] = True
            suggestions[source_fault]["abutting_fault"] = best_abutting[1]

    return suggestions


class _FaultSupportBoxRegion:
    """Region callable that limits a fault to an oriented support box."""

    def __init__(self, center, axes, lengths, name="fault_support_box"):
        from numpy import linalg as np_linalg

        center = np_array(center, dtype=float)
        axes = np_array(axes, dtype=float)
        lengths = np_array(lengths, dtype=float)
        axis_norms = np_linalg.norm(axes, axis=1)
        axis_norms[axis_norms <= 1e-9] = 1.0

        self.center = center
        self.axes = axes / axis_norms[:, None]
        self.half_lengths = 0.5 * np_array(lengths, dtype=float)
        self.name = name

    def __call__(self, xyz):
        xyz = np_array(xyz, dtype=float)
        if xyz.ndim == 1:
            xyz = xyz.reshape(1, -1)
        local = (xyz - self.center) @ self.axes.T
        tol = 1e-9
        mask = np_abs(local[:, 0]) <= (self.half_lengths[0] + tol)
        mask = mask & (np_abs(local[:, 1]) <= (self.half_lengths[1] + tol))
        mask = mask & (np_abs(local[:, 2]) <= (self.half_lengths[2] + tol))
        return mask


def _make_fault_support_box_region(fault_feature, center=None, axes=None, lengths=None):
    """Build a region mask from an explicit support box or the Loop fault frame."""
    if center is None:
        center = np_array(fault_feature.fault_centre, dtype=float)
    else:
        center = np_array(center, dtype=float)

    if axes is None:
        axes = np_array(
            [
                fault_feature.fault_strike_vector,
                fault_feature.fault_slip_vector,
                fault_feature.fault_normal_vector,
            ],
            dtype=float,
        )
    else:
        axes = np_array(axes, dtype=float)

    if lengths is None:
        lengths = np_array(
            [
                float(fault_feature.fault_major_axis),
                2.0 * float(fault_feature.fault_intermediate_axis),
                2.0 * float(fault_feature.fault_minor_axis),
            ],
            dtype=float,
        )
    else:
        lengths = np_array(lengths, dtype=float)

    return _FaultSupportBoxRegion(
        center=center,
        axes=axes,
        lengths=lengths,
        name=f"{fault_feature.name}_support_box",
    )


def _fault_obb_settings_dialog(
    parent,
    fault_data,
    default_displacement,
    default_rake=-90.0,
    default_nelements=1000,
    default_fault_buffer=0.2,
    relation_suggestions=None,
):
    """
    Interactive per-fault settings dialog with a reduced stable control set.

    The active workflow keeps only the controls that are currently robust:
    displacement, rake, support-box scaling, inferred-normal polarity flip,
    and manually configured abutting relationships.
    """
    from numpy import array as np_array
    from numpy import dot as np_dot
    from pyvista import Arrow as pv_Arrow
    from pyvistaqt import QtInteractor as pvQtInteractor
    from PySide6.QtWidgets import (
        QCheckBox,
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QDoubleSpinBox,
        QFrame,
        QFormLayout,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QVBoxLayout,
        QWidget,
    )
    from PySide6.QtCore import Qt, QPointF
    from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QPolygonF

    if not fault_data:
        return {}

    fault_names = _sorted_fault_names_by_time(fault_data, older_first=True)
    current_fault = {"name": fault_names[0]}
    is_loading = {"active": False}

    defaults_by_fault = {}
    for fault_name in fault_names:
        geometry = _compute_scaled_fault_geometry(
            fault_data[fault_name],
            rake_deg=default_rake,
            scale_factors=[1.0, 1.0, 1.0],
        )
        defaults_by_fault[fault_name] = {
            "displacement": float(default_displacement),
            "rake": float(default_rake),
            "major_scale_pct": 100.0,
            "intermediate_scale_pct": 100.0,
            "minor_scale_pct": 100.0,
            "flip_polarity": False,
            "has_abutting": False,
            "abutting_fault": None,
            "abutting_positive": True,
        }

    dialog = QDialog(parent)
    dialog.setWindowTitle("Fault Parameters and OBB Fit")
    dialog.resize(900, 700)

    root_layout = QVBoxLayout(dialog)
    info_label = QLabel(
        "Configure each fault independently.\n"
        "Scale controls act on the fixed Trace-like / Dip-like / Normal support box inferred from the input geometry.\n"
        "A polarity flip reverses the inferred normal without exposing manual normal editing.\n"
        "Abutting is fully manual and previewed in the current fault local frame.\n"
        "Advanced controls such as manual normals, per-fault mesh tuning, and splay remain disabled for now."
    )
    root_layout.addWidget(info_label)

    selector_layout = QHBoxLayout()
    selector_layout.addWidget(QLabel("Fault:"))
    fault_combo = QComboBox(dialog)
    for fault_name in fault_names:
        entity_name = fault_data[fault_name]["name"]
        fault_combo.addItem(f"{entity_name} ({fault_name})", fault_name)
    selector_layout.addWidget(fault_combo)
    root_layout.addLayout(selector_layout)

    controls_group = QGroupBox("Per-Fault Controls", dialog)
    controls_layout = QGridLayout(controls_group)
    root_layout.addWidget(controls_group)

    parameters_form = QFormLayout()
    displacement_spin = QDoubleSpinBox(dialog)
    displacement_spin.setDecimals(3)
    displacement_spin.setRange(-1e9, 1e9)
    displacement_spin.setValue(default_displacement)
    parameters_form.addRow("Displacement", displacement_spin)

    rake_spin = QDoubleSpinBox(dialog)
    rake_spin.setDecimals(1)
    rake_spin.setRange(-180.0, 180.0)
    rake_spin.setSingleStep(5.0)
    rake_spin.setValue(default_rake)
    parameters_form.addRow("Rake (deg)", rake_spin)

    flip_polarity_check = QCheckBox("Reverse inferred normal", dialog)
    flip_polarity_check.setChecked(False)
    parameters_form.addRow("Flip polarity", flip_polarity_check)

    controls_layout.addLayout(parameters_form, 0, 0)

    obb_form = QFormLayout()
    major_scale_spin = QDoubleSpinBox(dialog)
    major_scale_spin.setDecimals(1)
    major_scale_spin.setRange(5.0, 500.0)
    major_scale_spin.setSingleStep(5.0)
    major_scale_spin.setSuffix(" %")
    major_scale_spin.setValue(100.0)
    obb_form.addRow("Trace (Major) scale", major_scale_spin)

    intermediate_scale_spin = QDoubleSpinBox(dialog)
    intermediate_scale_spin.setDecimals(1)
    intermediate_scale_spin.setRange(5.0, 500.0)
    intermediate_scale_spin.setSingleStep(5.0)
    intermediate_scale_spin.setSuffix(" %")
    intermediate_scale_spin.setValue(100.0)
    obb_form.addRow("Dip-like (Intermediate) scale", intermediate_scale_spin)

    minor_scale_spin = QDoubleSpinBox(dialog)
    minor_scale_spin.setDecimals(1)
    minor_scale_spin.setRange(5.0, 500.0)
    minor_scale_spin.setSingleStep(5.0)
    minor_scale_spin.setSuffix(" %")
    minor_scale_spin.setValue(100.0)
    obb_form.addRow("Normal (Minor) scale", minor_scale_spin)

    raw_lengths_label = QLabel("")
    scaled_lengths_label = QLabel("")
    obb_form.addRow("Raw Trace/Dip/Normal", raw_lengths_label)
    obb_form.addRow("Scaled Trace/Dip/Normal", scaled_lengths_label)
    controls_layout.addLayout(obb_form, 0, 1)

    relations_form = QFormLayout()
    abutting_check = QCheckBox("Present")
    abutting_target_combo = QComboBox(dialog)
    abutting_side_combo = QComboBox(dialog)
    abutting_side_combo.addItem("Positive side", True)
    abutting_side_combo.addItem("Negative side", False)

    relations_form.addRow("Abutting", abutting_check)
    relations_form.addRow("Abutting with", abutting_target_combo)
    relations_form.addRow("Abut side", abutting_side_combo)
    controls_layout.addLayout(relations_form, 0, 2)

    preview_group = QGroupBox("OBB Preview", dialog)
    preview_layout = QHBoxLayout(preview_group)
    root_layout.addWidget(preview_group, stretch=1)

    class FaultObbPreviewWidget(QWidget):
        """2D preview widget (major/intermediate plane) without OpenGL."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self._fault_name = ""
            self._points_uv = None
            self._rect_uv = None
            self._minor_len = 0.0
            self._target_points_uv = None
            self._abut_line_uv = None
            self._abut_fill_uv = None
            self._abut_side_label = ""
            self.setMinimumHeight(260)

        def set_fault_preview(
            self,
            fault_name,
            points_uv,
            rect_uv,
            minor_len,
            target_points_uv=None,
            abut_line_uv=None,
            abut_fill_uv=None,
            abut_side_label="",
        ):
            self._fault_name = fault_name
            self._points_uv = points_uv
            self._rect_uv = rect_uv
            self._minor_len = minor_len
            self._target_points_uv = target_points_uv
            self._abut_line_uv = abut_line_uv
            self._abut_fill_uv = abut_fill_uv
            self._abut_side_label = abut_side_label
            self.update()

        def _map_to_widget(self, uv, bounds, draw_rect):
            min_u, max_u, min_v, max_v = bounds
            span_u = max(max_u - min_u, 1e-9)
            span_v = max(max_v - min_v, 1e-9)

            available_w = max(draw_rect.width() - 10, 1)
            available_h = max(draw_rect.height() - 30, 1)
            scale = min(available_w / span_u, available_h / span_v)

            cx = 0.5 * (min_u + max_u)
            cy = 0.5 * (min_v + max_v)
            px = draw_rect.center().x() + (uv[0] - cx) * scale
            py = draw_rect.center().y() - (uv[1] - cy) * scale
            return QPointF(px, py)

        def paintEvent(self, event):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing, True)

            painter.fillRect(self.rect(), QColor(32, 32, 32))
            draw_rect = self.rect().adjusted(10, 10, -10, -10)

            painter.setPen(QPen(QColor(90, 90, 90), 1))
            painter.drawRect(draw_rect)

            if self._points_uv is None or self._rect_uv is None:
                painter.setPen(QPen(QColor(200, 200, 200), 1))
                painter.drawText(
                    draw_rect,
                    Qt.AlignCenter,
                    "No preview data",
                )
                painter.end()
                return

            points_uv = self._points_uv
            rect_uv = self._rect_uv

            min_u = min(float(points_uv[:, 0].min()), float(rect_uv[:, 0].min()))
            max_u = max(float(points_uv[:, 0].max()), float(rect_uv[:, 0].max()))
            min_v = min(float(points_uv[:, 1].min()), float(rect_uv[:, 1].min()))
            max_v = max(float(points_uv[:, 1].max()), float(rect_uv[:, 1].max()))
            if self._target_points_uv is not None and len(self._target_points_uv) > 0:
                min_u = min(min_u, float(self._target_points_uv[:, 0].min()))
                max_u = max(max_u, float(self._target_points_uv[:, 0].max()))
                min_v = min(min_v, float(self._target_points_uv[:, 1].min()))
                max_v = max(max_v, float(self._target_points_uv[:, 1].max()))
            bounds = (min_u, max_u, min_v, max_v)

            if self._abut_fill_uv is not None and len(self._abut_fill_uv) >= 3:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(QColor(40, 180, 99, 70)))
                fill_points = QPolygonF(
                    [self._map_to_widget(uv, bounds, draw_rect) for uv in self._abut_fill_uv]
                )
                painter.drawPolygon(fill_points)
                painter.setBrush(Qt.NoBrush)

            # Draw OBB rectangle.
            painter.setPen(QPen(QColor(220, 70, 70), 2))
            rect_points = [self._map_to_widget(uv, bounds, draw_rect) for uv in rect_uv]
            for i in range(4):
                p1 = rect_points[i]
                p2 = rect_points[(i + 1) % 4]
                painter.drawLine(p1, p2)

            if self._abut_line_uv is not None and len(self._abut_line_uv) == 2:
                painter.setPen(QPen(QColor(255, 208, 0), 2))
                p1 = self._map_to_widget(self._abut_line_uv[0], bounds, draw_rect)
                p2 = self._map_to_widget(self._abut_line_uv[1], bounds, draw_rect)
                painter.drawLine(p1, p2)

            # Draw fault points.
            painter.setPen(QPen(QColor(230, 230, 230), 1))
            for uv in points_uv:
                p = self._map_to_widget(uv, bounds, draw_rect)
                painter.drawEllipse(p, 2.0, 2.0)

            if self._target_points_uv is not None and len(self._target_points_uv) > 0:
                painter.setPen(QPen(QColor(255, 181, 71), 1))
                for uv in self._target_points_uv:
                    p = self._map_to_widget(uv, bounds, draw_rect)
                    painter.drawLine(
                        QPointF(p.x() - 2.5, p.y() - 2.5),
                        QPointF(p.x() + 2.5, p.y() + 2.5),
                    )
                    painter.drawLine(
                        QPointF(p.x() - 2.5, p.y() + 2.5),
                        QPointF(p.x() + 2.5, p.y() - 2.5),
                    )

            # Center marker.
            center_p = self._map_to_widget((0.0, 0.0), bounds, draw_rect)
            painter.setPen(QPen(QColor(80, 180, 255), 2))
            painter.drawLine(
                QPointF(center_p.x() - 5, center_p.y()),
                QPointF(center_p.x() + 5, center_p.y()),
            )
            painter.drawLine(
                QPointF(center_p.x(), center_p.y() - 5),
                QPointF(center_p.x(), center_p.y() + 5),
            )

            painter.setPen(QPen(QColor(220, 220, 220), 1))
            painter.drawText(
                draw_rect.adjusted(6, 4, -6, -4),
                Qt.AlignTop | Qt.AlignLeft,
                (
                    f"{self._fault_name}\n"
                    f"Plane: trace/dip\n"
                    f"Normal length: {self._minor_len:.2f}\n"
                    f"{self._abut_side_label}"
                ).strip(),
            )
            painter.end()

    preview_widget = FaultObbPreviewWidget(preview_group)
    preview_layout.addWidget(preview_widget, stretch=1)

    preview_3d_frame = QFrame(preview_group)
    preview_3d_frame.setMinimumHeight(260)
    preview_3d_layout = QVBoxLayout(preview_3d_frame)
    preview_3d_layout.setContentsMargins(0, 0, 0, 0)
    preview_plotter = pvQtInteractor(preview_3d_frame)
    preview_plotter.set_background("black")
    preview_3d_layout.addWidget(preview_plotter.interactor)
    preview_layout.addWidget(preview_3d_frame, stretch=1)

    button_box = QDialogButtonBox(
        QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=dialog
    )
    root_layout.addWidget(button_box)

    def on_accept():
        save_current_fault_settings()
        dialog.accept()

    button_box.accepted.connect(on_accept)
    button_box.rejected.connect(dialog.reject)
    dialog.finished.connect(lambda _result: preview_plotter.close())

    def get_fault_geometry(fault_name):
        params = defaults_by_fault[fault_name]
        normal_override = fault_data[fault_name].get("center_normal")
        if normal_override is not None and params.get("flip_polarity", False):
            normal_override = -np_array(normal_override, dtype=float)
        scales = [
            params["major_scale_pct"] / 100.0,
            params["intermediate_scale_pct"] / 100.0,
            params["minor_scale_pct"] / 100.0,
        ]
        return _compute_scaled_fault_geometry(
            fault_data[fault_name],
            rake_deg=float(params["rake"]),
            scale_factors=scales,
            normal_override=normal_override,
        )

    def get_scaled_lengths(fault_name):
        return get_fault_geometry(fault_name)["scaled_lengths"]

    def _clip_polygon_with_half_plane(polygon_uv, normal_uv, threshold, keep_positive):
        if polygon_uv is None or len(polygon_uv) == 0:
            return None
        polygon_uv = [np_array(vertex, dtype=float) for vertex in polygon_uv]
        if abs(float(normal_uv[0])) <= 1e-12 and abs(float(normal_uv[1])) <= 1e-12:
            reference_inside = threshold >= 0.0 if keep_positive else threshold <= 0.0
            return np_array(polygon_uv, dtype=float) if reference_inside else None

        def _signed_value(vertex_uv):
            return float(np_dot(normal_uv, vertex_uv) + threshold)

        def _is_inside(vertex_uv):
            signed_value = _signed_value(vertex_uv)
            return signed_value >= -1e-9 if keep_positive else signed_value <= 1e-9

        clipped = polygon_uv
        output = []
        for idx in range(len(clipped)):
            current = clipped[idx]
            previous = clipped[idx - 1]
            current_inside = _is_inside(current)
            previous_inside = _is_inside(previous)
            current_value = _signed_value(current)
            previous_value = _signed_value(previous)

            if current_inside != previous_inside:
                delta = current - previous
                denom = current_value - previous_value
                if abs(denom) > 1e-12:
                    t = -previous_value / denom
                    intersection = previous + t * delta
                    output.append(intersection)
            if current_inside:
                output.append(current)

        if len(output) < 3:
            return None
        return np_array(output, dtype=float)

    def _fault_plane_intersections_with_rect(rect_uv, normal_uv, threshold):
        intersections = []
        if rect_uv is None or len(rect_uv) < 4:
            return None

        def _signed_value(vertex_uv):
            return float(np_dot(normal_uv, vertex_uv) + threshold)

        for idx in range(len(rect_uv)):
            start = np_array(rect_uv[idx], dtype=float)
            end = np_array(rect_uv[(idx + 1) % len(rect_uv)], dtype=float)
            start_value = _signed_value(start)
            end_value = _signed_value(end)

            if abs(start_value) <= 1e-9:
                intersections.append(start)
            if start_value * end_value < 0.0:
                denom = start_value - end_value
                if abs(denom) > 1e-12:
                    t = start_value / denom
                    intersections.append(start + t * (end - start))
            elif abs(end_value) <= 1e-9:
                intersections.append(end)

        unique_points = []
        for point_uv in intersections:
            if not any(np_dot(point_uv - existing, point_uv - existing) <= 1e-12 for existing in unique_points):
                unique_points.append(point_uv)
        if len(unique_points) < 2:
            return None
        return np_array(unique_points[:2], dtype=float)

    def _get_abutting_preview_overlay(fault_name, source_center, source_axes, rect_uv):
        params = defaults_by_fault[fault_name]
        if not params.get("has_abutting", False):
            return None

        target_fault_name = params.get("abutting_fault")
        if target_fault_name is None or target_fault_name == fault_name:
            return None

        target_points = np_array(fault_data[target_fault_name].get("points", []), dtype=float)
        if target_points.ndim != 2 or target_points.shape[0] == 0:
            target_points_uv = None
        else:
            target_centered = target_points - source_center
            target_points_uv = np_array(
                [target_centered @ source_axes[0], target_centered @ source_axes[1]],
                dtype=float,
            ).T

        target_geometry = get_fault_geometry(target_fault_name)
        target_center = np_array(target_geometry["center"], dtype=float)
        target_normal = np_array(target_geometry["normal"], dtype=float)
        plane_normal_uv = np_array(
            [np_dot(target_normal, source_axes[0]), np_dot(target_normal, source_axes[1])],
            dtype=float,
        )
        plane_threshold = float(np_dot(target_normal, source_center - target_center))
        # Match LoopStructural PositiveRegion/NegativeRegion sign convention.
        region_normal_uv = -plane_normal_uv
        region_threshold = -plane_threshold
        keep_positive = bool(params.get("abutting_positive", True))

        return {
            "target_points_uv": target_points_uv,
            "abut_line_uv": _fault_plane_intersections_with_rect(
                rect_uv, plane_normal_uv, plane_threshold
            ),
            "abut_fill_uv": _clip_polygon_with_half_plane(
                rect_uv, region_normal_uv, region_threshold, keep_positive
            ),
            "abut_side_label": (
                f"Abut side: {'Positive' if keep_positive else 'Negative'}"
            ),
        }

    def update_preview_3d(fault_name):
        preview_plotter.clear()
        preview_plotter.add_text("3D fault preview", position="upper_left", font_size=10)

        source_geometry = get_fault_geometry(fault_name)
        source_points = np_array(fault_data[fault_name].get("points", []), dtype=float)
        source_center = np_array(source_geometry["center"], dtype=float)
        source_axes = np_array(source_geometry["axes"], dtype=float)
        source_lengths = np_array(source_geometry["scaled_lengths"], dtype=float)
        source_normal = np_array(source_geometry["normal"], dtype=float)

        if source_points.ndim == 2 and source_points.shape[0] > 0:
            preview_plotter.add_mesh(
                pv_PolyData(source_points),
                color="white",
                point_size=8,
                render_points_as_spheres=True,
            )

        source_box = _build_obb_wireframe_polydata(
            source_center, source_axes, source_lengths
        )
        preview_plotter.add_mesh(source_box, color="tomato", line_width=2)

        source_arrow_length = max(
            float(source_lengths[2]),
            0.2 * float(max(source_lengths)),
            1.0,
        )
        source_arrow = pv_Arrow(
            start=source_center,
            direction=source_normal,
            scale=source_arrow_length,
        )
        preview_plotter.add_mesh(source_arrow, color="deepskyblue")

        params = defaults_by_fault[fault_name]
        target_fault_name = params.get("abutting_fault")
        if params.get("has_abutting", False) and target_fault_name not in [None, fault_name]:
            target_geometry = get_fault_geometry(target_fault_name)
            target_points = np_array(
                fault_data[target_fault_name].get("points", []), dtype=float
            )
            target_center = np_array(target_geometry["center"], dtype=float)
            target_axes = np_array(target_geometry["axes"], dtype=float)
            target_lengths = np_array(target_geometry["scaled_lengths"], dtype=float)
            target_normal = np_array(target_geometry["normal"], dtype=float)

            if target_points.ndim == 2 and target_points.shape[0] > 0:
                preview_plotter.add_mesh(
                    pv_PolyData(target_points),
                    color="orange",
                    point_size=8,
                    render_points_as_spheres=True,
                )

            target_box = _build_obb_wireframe_polydata(
                target_center, target_axes, target_lengths
            )
            preview_plotter.add_mesh(target_box, color="gold", line_width=2)

            target_arrow_length = max(
                float(target_lengths[2]),
                0.2 * float(max(target_lengths)),
                1.0,
            )
            target_arrow = pv_Arrow(
                start=target_center,
                direction=target_normal,
                scale=target_arrow_length,
            )
            preview_plotter.add_mesh(target_arrow, color="yellow")

        preview_plotter.show_axes()
        preview_plotter.view_isometric()
        preview_plotter.reset_camera()

    def update_relation_controls_enabled():
        has_other_faults = len(fault_names) > 1
        abutting_enabled = has_other_faults and abutting_check.isChecked()
        abutting_target_combo.setEnabled(abutting_enabled)
        abutting_side_combo.setEnabled(
            abutting_enabled and abutting_target_combo.currentData() is not None
        )

    def populate_relation_targets(fault_name, preferred_abutting=None):
        target_faults = [name for name in fault_names if name != fault_name]

        abutting_target_combo.blockSignals(True)
        abutting_target_combo.clear()
        abutting_target_combo.addItem("None", None)
        for target_name in target_faults:
            target_label = f"{fault_data[target_name]['name']} ({target_name})"
            abutting_target_combo.addItem(target_label, target_name)
        idx = 0
        if preferred_abutting is not None:
            found_idx = abutting_target_combo.findData(preferred_abutting)
            if found_idx >= 0:
                idx = found_idx
        abutting_target_combo.setCurrentIndex(idx)
        abutting_target_combo.blockSignals(False)
        update_relation_controls_enabled()

    def save_current_fault_settings():
        fault_name = current_fault["name"]
        defaults_by_fault[fault_name]["displacement"] = float(displacement_spin.value())
        defaults_by_fault[fault_name]["rake"] = float(rake_spin.value())
        defaults_by_fault[fault_name]["major_scale_pct"] = float(major_scale_spin.value())
        defaults_by_fault[fault_name]["intermediate_scale_pct"] = float(
            intermediate_scale_spin.value()
        )
        defaults_by_fault[fault_name]["minor_scale_pct"] = float(minor_scale_spin.value())
        defaults_by_fault[fault_name]["flip_polarity"] = bool(
            flip_polarity_check.isChecked()
        )
        defaults_by_fault[fault_name]["has_abutting"] = bool(abutting_check.isChecked())
        defaults_by_fault[fault_name]["abutting_fault"] = abutting_target_combo.currentData()
        defaults_by_fault[fault_name]["abutting_positive"] = bool(
            abutting_side_combo.currentData()
        )

    def update_lengths_labels(fault_name):
        geometry = get_fault_geometry(fault_name)
        base_lengths = geometry["lengths"]
        scaled_lengths = geometry["scaled_lengths"]
        raw_lengths_label.setText(
            f"{base_lengths[0]:.2f}, {base_lengths[1]:.2f}, {base_lengths[2]:.2f}"
        )
        scaled_lengths_label.setText(
            f"{scaled_lengths[0]:.2f}, {scaled_lengths[1]:.2f}, {scaled_lengths[2]:.2f}"
        )

    def update_preview(fault_name):
        geometry = get_fault_geometry(fault_name)
        fault_points = np_array(fault_data[fault_name]["points"], dtype=float)
        center = np_array(geometry["center"], dtype=float)
        axes = np_array(geometry["axes"], dtype=float)
        scaled_lengths = np_array(geometry["scaled_lengths"], dtype=float)

        if fault_points is None or len(fault_points) == 0:
            preview_widget.set_fault_preview(
                fault_name=fault_name,
                points_uv=np_array([[0.0, 0.0]], dtype=float),
                rect_uv=np_array([[-1, -1], [1, -1], [1, 1], [-1, 1]], dtype=float),
                minor_len=float(scaled_lengths[2]),
            )
            update_preview_3d(fault_name)
            return

        centered_points = fault_points - center
        points_u = centered_points @ axes[0]
        points_v = centered_points @ axes[1]
        points_uv = np_array([points_u, points_v], dtype=float).T

        major_half = 0.5 * float(scaled_lengths[0])
        intermediate_half = 0.5 * float(scaled_lengths[1])
        rect_uv = np_array(
            [
                [-major_half, -intermediate_half],
                [major_half, -intermediate_half],
                [major_half, intermediate_half],
                [-major_half, intermediate_half],
            ],
            dtype=float,
        )
        overlay = _get_abutting_preview_overlay(fault_name, center, axes, rect_uv)

        preview_widget.set_fault_preview(
            fault_name=fault_name,
            points_uv=points_uv,
            rect_uv=rect_uv,
            minor_len=float(scaled_lengths[2]),
            target_points_uv=None if overlay is None else overlay["target_points_uv"],
            abut_line_uv=None if overlay is None else overlay["abut_line_uv"],
            abut_fill_uv=None if overlay is None else overlay["abut_fill_uv"],
            abut_side_label="" if overlay is None else overlay["abut_side_label"],
        )
        update_preview_3d(fault_name)

    def load_fault_settings(fault_name):
        is_loading["active"] = True
        try:
            params = defaults_by_fault[fault_name]
            displacement_spin.setValue(params["displacement"])
            rake_spin.setValue(params["rake"])
            major_scale_spin.setValue(params["major_scale_pct"])
            intermediate_scale_spin.setValue(params["intermediate_scale_pct"])
            minor_scale_spin.setValue(params["minor_scale_pct"])
            flip_polarity_check.setChecked(bool(params.get("flip_polarity", False)))
            abutting_check.setChecked(bool(params.get("has_abutting", False)))
            abutting_side_combo.setCurrentIndex(
                0 if bool(params.get("abutting_positive", True)) else 1
            )
            populate_relation_targets(
                fault_name,
                preferred_abutting=params.get("abutting_fault"),
            )
        finally:
            is_loading["active"] = False
        update_relation_controls_enabled()
        update_lengths_labels(fault_name)
        update_preview(fault_name)

    def on_fault_changed(_):
        save_current_fault_settings()
        selected_fault = fault_combo.currentData()
        current_fault["name"] = selected_fault
        load_fault_settings(selected_fault)

    def on_controls_changed(*_):
        if is_loading["active"]:
            return
        update_relation_controls_enabled()
        save_current_fault_settings()
        selected_fault = current_fault["name"]
        update_lengths_labels(selected_fault)
        update_preview(selected_fault)

    fault_combo.currentIndexChanged.connect(on_fault_changed)
    displacement_spin.valueChanged.connect(on_controls_changed)
    rake_spin.valueChanged.connect(on_controls_changed)
    flip_polarity_check.toggled.connect(on_controls_changed)
    major_scale_spin.valueChanged.connect(on_controls_changed)
    intermediate_scale_spin.valueChanged.connect(on_controls_changed)
    minor_scale_spin.valueChanged.connect(on_controls_changed)
    abutting_check.toggled.connect(on_controls_changed)
    abutting_target_combo.currentIndexChanged.connect(on_controls_changed)
    abutting_side_combo.currentIndexChanged.connect(on_controls_changed)

    load_fault_settings(current_fault["name"])

    result = dialog.exec()
    if result != QDialog.Accepted:
        return None

    save_current_fault_settings()
    per_fault_settings = {}
    for fault_name in fault_names:
        params = defaults_by_fault[fault_name]
        geometry = get_fault_geometry(fault_name)
        per_fault_settings[fault_name] = {
            "displacement": float(params["displacement"]),
            "rake": float(params["rake"]),
            "center": geometry["center"],
            "axes": geometry["axes"],
            "lengths": geometry["scaled_lengths"],
            "flip_polarity": bool(params.get("flip_polarity", False)),
            "has_abutting": bool(params.get("has_abutting", False)),
            "abutting_fault": params.get("abutting_fault"),
            "abutting_positive": bool(params.get("abutting_positive", True)),
        }

    return per_fault_settings


@freeze_gui_onoff
def implicit_model_loop_structural_with_faults(self):
    """LoopStructural implicit modelling with merged faults and age-aware sequences."""
    from numpy import argmin as np_argmin
    from numpy import concatenate as np_concatenate
    from numpy import dot as np_dot
    from numpy import full as np_full
    from numpy import isnan as np_isnan
    from numpy import linalg as np_linalg

    self.print_terminal(
        "LoopStructural implicit geomodeller WITH FAULT SUPPORT\n"
        "github.com/Loop3D/LoopStructural"
    )
    if self.shown_table != "tabGeology":
        self.print_terminal(" -- Only geological objects can be interpolated -- ")
        return
    if not self.selected_uids:
        self.print_terminal("No input data selected.")
        return

    input_uids = deepcopy(self.selected_uids)
    fault_uids = []
    strati_uids = []
    for uid in input_uids:
        if self.geol_coll.get_uid_role(uid) == "fault":
            fault_uids.append(uid)
        else:
            strati_uids.append(uid)

    self.print_terminal(
        f"Found {len(fault_uids)} fault entities and {len(strati_uids)} stratigraphy entities"
    )
    if not fault_uids:
        self.print_terminal(
            "No fault entities found. Use standard implicit_model_loop_structural for surfaces only."
        )
        return
    if not strati_uids:
        self.print_terminal(
            "WARNING: No stratigraphy entities found. Model will only contain faults."
        )

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

    self.print_terminal("-> Creating input dataframes...")
    tic(parent=self)
    all_input_data_df = pd_DataFrame(columns=list(loop_input_dict.keys()))
    fault_groups = {}
    fault_data = {}
    sequence_data = {}

    if fault_uids:
        prgs_bar = progress_dialog(
            max_value=len(fault_uids),
            title_txt="Processing Faults",
            label_txt="Grouping fault entities...",
            cancel_txt=None,
            parent=self,
        )
        for uid in fault_uids:
            feature = self.geol_coll.get_uid_feature(uid)
            scenario = self.geol_coll.get_uid_scenario(uid)
            entity_name = self.geol_coll.get_uid_name(uid)
            vtk_obj = self.geol_coll.get_uid_vtk_obj(uid)
            points_arr = np_array(vtk_obj.points, dtype=float)

            legend_match = self.geol_coll.legend_df.loc[
                (self.geol_coll.legend_df["role"] == "fault")
                & (self.geol_coll.legend_df["feature"] == feature)
                & (self.geol_coll.legend_df["scenario"] == scenario)
            ]
            fault_time = (
                _safe_relative_time(legend_match["time"].values[0])
                if not legend_match.empty
                else float("nan")
            )

            group_key = (feature, scenario)
            group = fault_groups.setdefault(
                group_key,
                {
                    "feature": feature,
                    "scenario": scenario,
                    "entity_names": [],
                    "uids": [],
                    "topologies": [],
                    "point_segments": [],
                    "trace_segments": [],
                    "normal_segments": [],
                    "time": float("nan"),
                },
            )
            group["entity_names"].append(entity_name)
            group["uids"].append(uid)
            group["topologies"].append(self.geol_coll.get_uid_topology(uid))
            group["point_segments"].append(points_arr)
            if self.geol_coll.get_uid_topology(uid) == "PolyLine":
                group["trace_segments"].append(points_arr)

            normals_arr = None
            if "Normals" in self.geol_coll.get_uid_properties_names(uid):
                normals_arr = np_array(
                    self.geol_coll.get_uid_property(uid=uid, property_name="Normals"),
                    dtype=float,
                )
                if (
                    normals_arr.ndim != 2
                    or normals_arr.shape[0] != points_arr.shape[0]
                    or normals_arr.shape[1] < 3
                ):
                    normals_arr = None
                else:
                    normals_arr = normals_arr[:, :3]
            group["normal_segments"].append(normals_arr)

            existing_time = _safe_relative_time(group.get("time"))
            if existing_time != existing_time and fault_time == fault_time:
                group["time"] = fault_time
            elif (
                fault_time == fault_time
                and existing_time == existing_time
                and abs(existing_time - fault_time) > 1e-9
            ):
                self.print_terminal(
                    f"  WARNING: Fault group ({feature}, {scenario}) has inconsistent legend times "
                    f"({existing_time} vs {fault_time}); keeping {existing_time}."
                )
            prgs_bar.add_one()
        prgs_bar.close()

    if fault_groups:
        prgs_bar = progress_dialog(
            max_value=len(fault_groups),
            title_txt="Processing Faults",
            label_txt="Merging grouped faults...",
            cancel_txt=None,
            parent=self,
        )
        for (feature, scenario), group in fault_groups.items():
            valid_segments = [
                np_array(seg, dtype=float)
                for seg in group["point_segments"]
                if seg is not None and len(seg) > 0
            ]
            if not valid_segments:
                prgs_bar.add_one()
                continue

            points_arr = np_concatenate(valid_segments, axis=0)
            trace_segments = [
                np_array(seg, dtype=float)
                for seg in group.get("trace_segments", [])
                if seg is not None and len(seg) > 0
            ]
            trace_points = (
                np_concatenate(trace_segments, axis=0)
                if trace_segments
                else np_array([], dtype=float).reshape(0, 3)
            )
            display_name = str(feature).strip() if str(feature).strip() not in ["", "undef"] else ""
            if not display_name:
                display_name = str(group["entity_names"][0]).strip()
            if len(group["entity_names"]) > 1:
                display_name = f"{display_name} (+{len(group['entity_names']) - 1})"

            fault_feature_name = _make_fault_group_name(
                feature, scenario, fallback_name=display_name
            )
            fault_name_base = fault_feature_name
            suffix_idx = 2
            while fault_feature_name in fault_data:
                fault_feature_name = f"{fault_name_base}_{suffix_idx}"
                suffix_idx += 1

            obb_center, obb_axes, _ = _compute_fault_geometric_features_obb(points_arr)
            merged_normals = np_full((len(points_arr), 3), float("nan"), dtype=float)
            valid_normal_points = []
            valid_normal_vectors = []
            offset = 0
            for point_segment, normal_segment in zip(
                group["point_segments"], group["normal_segments"]
            ):
                seg_len = len(point_segment) if point_segment is not None else 0
                if seg_len == 0:
                    continue
                if normal_segment is not None and len(normal_segment) == seg_len:
                    normals_arr = np_array(normal_segment, dtype=float)[:, :3]
                    finite_mask = ~np_isnan(normals_arr).any(axis=1)
                    if finite_mask.any():
                        segment_normals = merged_normals[offset : offset + seg_len]
                        segment_normals[finite_mask] = normals_arr[finite_mask]
                        valid_normal_points.append(
                            np_array(point_segment, dtype=float)[finite_mask]
                        )
                        valid_normal_vectors.append(normals_arr[finite_mask])
                offset += seg_len

            explicit_center_normal = None
            if valid_normal_vectors:
                normal_points = np_concatenate(valid_normal_points, axis=0)
                normal_vectors = np_concatenate(valid_normal_vectors, axis=0)
                center_idx = int(np_argmin(np_sum((normal_points - obb_center) ** 2, axis=1)))
                candidate_normal = np_array(normal_vectors[center_idx], dtype=float)
                candidate_norm = np_linalg.norm(candidate_normal)
                if candidate_norm > 1e-9:
                    explicit_center_normal = candidate_normal / candidate_norm

            normal_info = _infer_fault_normal(
                points_arr,
                explicit_normal=explicit_center_normal,
                trace_points=trace_points,
                fallback_axes=obb_axes,
            )
            center_normal = np_array(normal_info["normal"], dtype=float)

            plane_axes = _orient_fault_axes_for_rake(
                obb_axes, center_normal=center_normal, trace_points=trace_points
            )
            default_geometry = _compute_scaled_fault_geometry(
                {
                    "points": points_arr,
                    "obb_axes": obb_axes,
                    "plane_axes": plane_axes,
                    "center_normal": center_normal,
                    "trace_points": trace_points,
                },
                rake_deg=-90.0,
                scale_factors=[1.0, 1.0, 1.0],
            )
            fault_normal = np_array(default_geometry["normal"], dtype=float)
            if np_linalg.norm(fault_normal) <= 1e-9:
                fault_normal = np_array([0.0, 0.0, 1.0], dtype=float)
            missing_normals = np_isnan(merged_normals).any(axis=1)
            merged_normals[missing_normals] = fault_normal

            entity_df = pd_DataFrame(columns=list(loop_input_dict.keys()))
            entity_df[["X", "Y", "Z"]] = points_arr
            entity_df["feature_name"] = fault_feature_name
            entity_df["val"] = 0.0
            entity_df["coord"] = 0
            entity_df[["nx", "ny", "nz"]] = merged_normals
            all_input_data_df = pd_concat(
                [all_input_data_df, entity_df], ignore_index=True
            )

            fault_data[fault_feature_name] = {
                "uids": list(group["uids"]),
                "time": group.get("time"),
                "center": default_geometry["center"],
                "axes": default_geometry["axes"],
                "lengths": default_geometry["lengths"],
                "obb_axes": obb_axes,
                "plane_axes": default_geometry["plane_axes"],
                "center_normal": center_normal,
                "normal_source": normal_info["source"],
                "trace_points": trace_points,
                "name": display_name,
                "feature": feature,
                "scenario": scenario,
                "points": points_arr,
                "entity_names": list(group["entity_names"]),
                "topologies": list(group.get("topologies", [])),
            }
            self.print_terminal(
                f"  Fault group '{fault_feature_name}': {len(group['uids'])} entities, "
                f"center={default_geometry['center']}, lengths={default_geometry['lengths']}, "
                f"normal_source={normal_info['source']}"
            )
            prgs_bar.add_one()
        prgs_bar.close()

    if not fault_data:
        toc(parent=self)
        self.print_terminal("No valid fault geometry found in the selected data.")
        return

    if strati_uids:
        prgs_bar = progress_dialog(
            max_value=len(strati_uids),
            title_txt="Processing Stratigraphy",
            label_txt="Grouping geological sequences...",
            cancel_txt=None,
            parent=self,
        )
        sequence_order = 0
        for uid in strati_uids:
            role = self.geol_coll.get_uid_role(uid)
            feature = self.geol_coll.get_uid_feature(uid)
            scenario = self.geol_coll.get_uid_scenario(uid)
            entity_name = self.geol_coll.get_uid_name(uid)

            entity_df = pd_DataFrame(columns=list(loop_input_dict.keys()))
            points_arr = np_array(self.geol_coll.get_uid_vtk_obj(uid).points, dtype=float)
            entity_df[["X", "Y", "Z"]] = points_arr

            if "Normals" in self.geol_coll.get_uid_properties_names(uid):
                normals_arr = np_array(
                    self.geol_coll.get_uid_property(uid=uid, property_name="Normals"),
                    dtype=float,
                )
                if (
                    normals_arr.ndim == 2
                    and normals_arr.shape[0] == points_arr.shape[0]
                    and normals_arr.shape[1] >= 3
                ):
                    entity_df[["nx", "ny", "nz"]] = normals_arr[:, :3]

            legend_match = self.geol_coll.legend_df.loc[
                (self.geol_coll.legend_df["role"] == role)
                & (self.geol_coll.legend_df["feature"] == feature)
                & (self.geol_coll.legend_df["scenario"] == scenario)
            ]
            if legend_match.empty:
                sequence_name = (
                    str(feature).strip()
                    if str(feature).strip() not in ["", "undef"]
                    else entity_name
                )
                time_value = float("nan")
                self.print_terminal(
                    f"  WARNING: Missing legend entry for '{entity_name}'. "
                    f"Using sequence '{sequence_name}' with NaN time."
                )
            else:
                sequence_name = legend_match["sequence"].values[0]
                if not isinstance(sequence_name, str) or not sequence_name.strip():
                    sequence_name = (
                        str(feature).strip()
                        if str(feature).strip() not in ["", "undef"]
                        else entity_name
                    )
                time_value = _safe_relative_time(legend_match["time"].values[0])

            entity_df["feature_name"] = sequence_name
            entity_df["val"] = time_value
            all_input_data_df = pd_concat(
                [all_input_data_df, entity_df], ignore_index=True
            )

            if sequence_name not in sequence_data:
                sequence_data[sequence_name] = {
                    "order": sequence_order,
                    "youngest_time": time_value,
                    "metadata_by_time": {},
                }
                sequence_order += 1

            seq_info = sequence_data[sequence_name]
            youngest_time = _safe_relative_time(seq_info.get("youngest_time"))
            if time_value == time_value and (
                youngest_time != youngest_time or time_value < youngest_time
            ):
                seq_info["youngest_time"] = time_value

            if time_value == time_value:
                existing_meta = seq_info["metadata_by_time"].get(time_value)
                metadata = {
                    "role": role,
                    "feature": feature,
                    "scenario": scenario,
                }
                if existing_meta is None:
                    seq_info["metadata_by_time"][time_value] = metadata
                elif existing_meta != metadata:
                    self.print_terminal(
                        f"  WARNING: Sequence '{sequence_name}' time {time_value} has conflicting metadata; "
                        f"keeping the first entry."
                    )
            prgs_bar.add_one()
        prgs_bar.close()

    toc(parent=self)

    self.print_terminal("-> Drop empty columns...")
    tic(parent=self)
    all_input_data_df.dropna(axis=1, how="all", inplace=True)
    toc(parent=self)

    input_dict = {
        "boundary": ["Boundary: ", self.boundary_coll.get_names],
        "method": ["Interpolation method: ", ["PLI", "FDI", "surfe"]],
    }
    options_dict = multiple_input_dialog(
        title="Implicit Modelling with Faults", input_dict=input_dict
    )
    if options_dict is None:
        options_dict = {
            "boundary": self.boundary_coll.get_names[0],
            "method": "PLI",
        }

    boundary_uid = self.boundary_coll.df.loc[
        self.boundary_coll.df["name"] == options_dict["boundary"], "uid"
    ].values[0]
    bounds = self.boundary_coll.get_uid_vtk_obj(boundary_uid).GetBounds()
    obb_info = get_boundary_obb_transform(self.boundary_coll, boundary_uid)
    use_obb_alignment = obb_info["has_obb"]

    if use_obb_alignment:
        self.print_terminal(
            f"-> OBB boundary detected. Rotation angle: {np_around(obb_info['angle'] * 180 / np_pi, 2)} degrees"
        )
        self.print_terminal("-> Transforming data to axis-aligned coordinate system...")
        (
            origin_x,
            origin_y,
            origin_z_temp,
            maximum_x,
            maximum_y,
            maximum_z_temp,
        ) = get_aligned_bounds_from_obb(self.boundary_coll, boundary_uid, obb_info)
        all_input_data_df = transform_points_to_aligned(all_input_data_df, obb_info)

        angle = obb_info["angle"]
        obb_center = obb_info["center"]
        c, s = np_cos(angle), np_sin(angle)
        R_to_local = np_array([[c, s], [-s, c]])
        for fault_name, fault_info in fault_data.items():
            fault_points = np_array(fault_info.get("points", []), dtype=float)
            if len(fault_points) > 0:
                xy_rotated = (R_to_local @ (fault_points[:, :2] - obb_center).T).T
                points_aligned = fault_points.copy()
                points_aligned[:, 0] = xy_rotated[:, 0]
                points_aligned[:, 1] = xy_rotated[:, 1]
            else:
                points_aligned = fault_points

            trace_points_world = np_array(fault_info.get("trace_points", []), dtype=float)
            if len(trace_points_world) > 0:
                trace_xy_rotated = (
                    R_to_local @ (trace_points_world[:, :2] - obb_center).T
                ).T
                trace_points_aligned = trace_points_world.copy()
                trace_points_aligned[:, 0] = trace_xy_rotated[:, 0]
                trace_points_aligned[:, 1] = trace_xy_rotated[:, 1]
            else:
                trace_points_aligned = trace_points_world

            center_normal_aligned = fault_info.get("center_normal")
            if center_normal_aligned is not None:
                center_normal_aligned = np_array(center_normal_aligned, dtype=float)
                nxy_rotated = (R_to_local @ center_normal_aligned[:2].reshape(2, 1)).ravel()
                center_normal_aligned = np_array(
                    [nxy_rotated[0], nxy_rotated[1], center_normal_aligned[2]],
                    dtype=float,
                )

            _, obb_axes_raw, _ = _compute_fault_geometric_features_obb(points_aligned)
            plane_axes_aligned = _orient_fault_axes_for_rake(
                obb_axes_raw,
                center_normal=center_normal_aligned,
                trace_points=trace_points_aligned,
            )
            default_geometry = _compute_scaled_fault_geometry(
                {
                    "points": points_aligned,
                    "obb_axes": obb_axes_raw,
                    "plane_axes": plane_axes_aligned,
                    "center_normal": center_normal_aligned,
                    "trace_points": trace_points_aligned,
                },
                rake_deg=-90.0,
                scale_factors=[1.0, 1.0, 1.0],
            )
            fault_info["points"] = points_aligned
            fault_info["trace_points"] = trace_points_aligned
            fault_info["obb_axes"] = obb_axes_raw
            fault_info["plane_axes"] = plane_axes_aligned
            fault_info["center"] = default_geometry["center"]
            fault_info["axes"] = default_geometry["axes"]
            fault_info["lengths"] = default_geometry["lengths"]
            fault_info["center_normal"] = center_normal_aligned

        self.print_terminal(
            f"-> Data transformed. New aligned bounds: X[{origin_x:.2f}, {maximum_x:.2f}], "
            f"Y[{origin_y:.2f}, {maximum_y:.2f}]"
        )
    else:
        origin_x, maximum_x = bounds[0], bounds[1]
        origin_y, maximum_y = bounds[2], bounds[3]

    if bounds[4] == bounds[5]:
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
            title="Implicit Modelling with Faults",
            input_dict=vertical_extension_in,
        )
        origin_z = float(
            (vertical_extension_updt or {}).get("bottom", -1000.0)
        )
        maximum_z = float(
            (vertical_extension_updt or {}).get("top", 1000.0)
        )
        if origin_z > maximum_z:
            origin_z, maximum_z = maximum_z, origin_z
        elif origin_z == maximum_z:
            origin_z -= 25.0
            maximum_z += 25.0
    else:
        origin_z, maximum_z = bounds[4], bounds[5]

    edge_x = maximum_x - origin_x
    edge_y = maximum_y - origin_y
    edge_z = maximum_z - origin_z
    origin = [origin_x, origin_y, origin_z]
    maximum = [maximum_x, maximum_y, maximum_z]

    self.print_terminal(f"Model origin: {origin}")
    self.print_terminal(f"Model maximum: {maximum}")

    if (
        all_input_data_df["X"].min() > maximum_x
        or all_input_data_df["X"].max() < origin_x
        or all_input_data_df["Y"].min() > maximum_y
        or all_input_data_df["Y"].max() < origin_y
        or all_input_data_df["Z"].min() > maximum_z
        or all_input_data_df["Z"].max() < origin_z
    ):
        self.print_terminal("ERROR: Bounding Box does not intersect input data")
        return

    default_spacing = np_cbrt(edge_x * edge_y * edge_z / (50 * 50 * 25))
    target_spacing = input_one_value_dialog(
        title="Implicit Modelling with Faults",
        label="Grid target spacing in model units",
        default_value=default_spacing,
    )
    if target_spacing is None or target_spacing <= 0:
        target_spacing = default_spacing

    dimension_x = max(1, int(np_around(edge_x / target_spacing)))
    dimension_y = max(1, int(np_around(edge_y / target_spacing)))
    dimension_z = max(1, int(np_around(edge_z / target_spacing)))
    dimensions = [dimension_x, dimension_y, dimension_z]
    spacing = [edge_x / dimension_x, edge_y / dimension_y, edge_z / dimension_z]

    target_spacing_strati = input_one_value_dialog(
        title="Implicit Modelling with Faults",
        label="Grid target spacing for stratigraphy (leave blank for same)",
        default_value=target_spacing,
    )
    if target_spacing_strati is None or target_spacing_strati <= 0:
        target_spacing_strati = target_spacing

    dimension_strati_x = max(1, int(np_around(edge_x / target_spacing_strati)))
    dimension_strati_y = max(1, int(np_around(edge_y / target_spacing_strati)))
    dimension_strati_z = max(1, int(np_around(edge_z / target_spacing_strati)))
    dimensions_strati = [dimension_strati_x, dimension_strati_y, dimension_strati_z]
    spacing_strati = [
        edge_x / dimension_strati_x,
        edge_y / dimension_strati_y,
        edge_z / dimension_strati_z,
    ]

    self.print_terminal(f"Grid dimensions (faults): {dimensions}")
    self.print_terminal(f"Grid spacing (faults): {spacing}")
    if dimensions_strati != dimensions:
        self.print_terminal(
            f"Grid dimensions (stratigraphy): {dimensions_strati}"
        )
        self.print_terminal(
            f"Grid spacing (stratigraphy): {spacing_strati}"
        )

    model_diagonal = np_sqrt(edge_x**2 + edge_y**2 + edge_z**2)
    default_displacement = model_diagonal * 0.05
    # Keep advanced per-fault controls fixed until the manual workflow is stabilized.
    default_fault_nelements = 1000
    default_fault_buffer = 0.2
    # Keep abutting fully manual to avoid hidden time-based behaviour.
    relation_suggestions = {}
    fault_params_by_name = _fault_obb_settings_dialog(
        parent=self,
        fault_data=fault_data,
        default_displacement=default_displacement,
        default_rake=-90.0,
        default_nelements=default_fault_nelements,
        default_fault_buffer=default_fault_buffer,
        relation_suggestions=relation_suggestions,
    )
    if fault_params_by_name is None:
        self.print_terminal(
            "Fault settings dialog cancelled. Using defaults for all faults."
        )
        fault_params_by_name = {}
        for fault_name, fault_info in fault_data.items():
            geometry = _compute_scaled_fault_geometry(
                fault_info, rake_deg=-90.0, scale_factors=[1.0, 1.0, 1.0]
            )
            fault_params_by_name[fault_name] = {
                "displacement": float(default_displacement),
                "rake": -90.0,
                "center": geometry["center"],
                "axes": geometry["axes"],
                "lengths": geometry["scaled_lengths"],
                "flip_polarity": False,
                "has_abutting": False,
                "abutting_fault": None,
                "abutting_positive": True,
            }
    else:
        self.print_terminal("Per-fault parameters configured:")
        for fault_name in _sorted_fault_names_by_time(fault_data, older_first=True):
            params = fault_params_by_name.get(fault_name, {})
            self.print_terminal(
                f"  {fault_name}: displacement={float(params.get('displacement', 0.0)):.2f}, "
                f"rake={float(params.get('rake', -90.0)):.1f} deg, "
                f"flip_polarity={'ON' if params.get('flip_polarity', False) else 'OFF'}, "
                f"lengths={params.get('lengths')}, "
                f"abutting={params.get('abutting_fault') if params.get('has_abutting') else 'None'}, "
                f"abut_side={'positive' if params.get('abutting_positive', True) else 'negative'}"
            )

    model_name = "Loop_model_faults"
    fault_creation_order = _sorted_fault_names_by_time(fault_data, older_first=True)
    sequence_names = sorted(
        sequence_data.keys(), key=lambda name: sequence_data[name]["order"]
    )
    interpolation_progress = progress_dialog(
        max_value=max(
            1,
            1
            + len(fault_creation_order)
            + 1
            + len(sequence_names)
            + 1
            + max(len(fault_creation_order) + len(sequence_names), 1)
            + 1
            + len(fault_creation_order)
            + len(sequence_names),
        ),
        title_txt="Implicit Modelling with Faults",
        label_txt="Creating LoopStructural model...",
        cancel_txt=None,
        parent=self,
    )

    def _advance_interpolation_progress(label_txt=None):
        if label_txt is not None:
            interpolation_progress.setLabelText(label_txt)
        interpolation_progress.add_one()

    self.print_terminal("-> Creating LoopStructural model...")
    tic(parent=self)
    model = GeologicalModel(origin, maximum)
    model.set_model_data(all_input_data_df)
    toc(parent=self)
    _advance_interpolation_progress("Creating faults...")
    self.print_terminal(
        f"Input dataframe rows: {len(all_input_data_df)}, features: "
        f"{sorted(all_input_data_df['feature_name'].dropna().unique().tolist())}"
    )

    self.print_terminal("-> Creating faults...")
    tic(parent=self)
    created_fault_features = []
    created_fault_features_by_name = {}

    for fault_name in fault_creation_order:
        fault_info = fault_data[fault_name]
        fault_params_single = fault_params_by_name.get(fault_name, {})
        displacement = float(
            fault_params_single.get("displacement", default_displacement)
        )
        fault_rake = float(fault_params_single.get("rake", -90.0))
        fault_rake = ((fault_rake + 180.0) % 360.0) - 180.0
        flip_polarity = bool(fault_params_single.get("flip_polarity", False))
        normal_override = fault_info.get("center_normal")
        if normal_override is not None and flip_polarity:
            normal_override = -np_array(normal_override, dtype=float)

        base_geometry = _compute_scaled_fault_geometry(
            fault_info,
            rake_deg=fault_rake,
            scale_factors=[1.0, 1.0, 1.0],
            normal_override=normal_override,
        )
        center = np_array(
            fault_params_single.get("center", base_geometry["center"]), dtype=float
        )
        axes = np_array(
            fault_params_single.get("axes", base_geometry["axes"]), dtype=float
        )
        lengths = np_array(
            fault_params_single.get("lengths", base_geometry["scaled_lengths"]),
            dtype=float,
        )
        lengths = _normalise_fault_obb_lengths(lengths)
        if len(lengths) < 3:
            lengths = np_array(base_geometry["scaled_lengths"], dtype=float)

        support_trace_len = max(float(lengths[0]), 1e-3)
        support_dip_len = max(float(lengths[1]), 1e-3)
        support_normal_len = max(float(lengths[2]), 1e-3)

        loop_geometry = _compute_fault_loop_geometry(center, axes, lengths, fault_rake)
        loop_axes = np_array(loop_geometry["loop_axes"], dtype=float)
        loop_lengths = np_array(loop_geometry["loop_lengths"], dtype=float)
        slip_vector = np_array(loop_geometry["slip_vector"], dtype=float)
        strike_axis = np_array(loop_geometry["strike_axis"], dtype=float)
        dip_axis = np_array(loop_geometry["dip_axis"], dtype=float)
        fault_normal = np_array(loop_geometry["fault_normal"], dtype=float)
        rake_components = np_array(loop_geometry["rake_components"], dtype=float)

        ls_major_axis = max(float(loop_lengths[0]), 1e-3)
        ls_intermediate_axis = max(0.5 * float(loop_lengths[1]), 1e-3)
        ls_minor_axis = max(0.5 * float(loop_lengths[2]), 1e-3)

        self.print_terminal(f"  Creating fault: {fault_name}")
        self.print_terminal(f"    Fault geometry: center={center}")
        self.print_terminal(
            f"    support lengths: trace={support_trace_len:.2f}, dip={support_dip_len:.2f}, normal={support_normal_len:.2f}"
        )
        self.print_terminal(
            f"    LoopStructural extents: trace={loop_lengths[0]:.2f}, "
            f"slip={loop_lengths[1]:.2f}, normal={loop_lengths[2]:.2f}"
        )
        self.print_terminal("    Support box axes (fixed):")
        self.print_terminal(f"      trace-like: {axes[0]}")
        self.print_terminal(f"      dip-like: {axes[1]}")
        self.print_terminal(f"      normal: {axes[2]}")
        self.print_terminal("    LoopStructural basis (rake-dependent):")
        self.print_terminal(f"      trace: {loop_axes[0]}")
        self.print_terminal(f"      slip: {loop_axes[1]}")
        self.print_terminal(f"      normal: {loop_axes[2]}")
        self.print_terminal(
            f"    rake components (strike, dip): "
            f"[{rake_components[0]:.4f}, {rake_components[1]:.4f}]"
        )
        self.print_terminal(
            f"    fault_slip_vector (3D): {slip_vector.tolist()}"
        )
        self.print_terminal(
            f"    rake={fault_rake}° (0=sinistral, 90=reverse, -90=normal, ±180=dextral)"
        )
        self.print_terminal(
            f"    fault_normal_vector: {fault_normal.tolist()}"
        )
        self.print_terminal(
            f"    flip_polarity={'ON' if flip_polarity else 'OFF'}"
        )
        self.print_terminal(
            "    faultfunction=BaseFault3D (displacement tapered in slip and trace directions)"
        )
        use_points = True
        self.print_terminal(
            f"    Using points={use_points} for fault frame construction"
        )

        fault_params_ls = {
            "nelements": default_fault_nelements,
            "interpolatortype": options_dict["method"],
            "faultfunction": "BaseFault3D",
            "fault_buffer": default_fault_buffer,
            "fault_center": center.tolist(),
            "fault_normal_vector": fault_normal.tolist(),
            "major_axis": ls_major_axis,
            "minor_axis": ls_minor_axis,
            "intermediate_axis": ls_intermediate_axis,
            "fault_slip_vector": slip_vector.tolist(),
            "points": use_points,
        }

        try:
            model.create_and_add_fault(
                fault_name,
                displacement,
                **fault_params_ls,
            )
            fault_feature = model.get_feature_by_name(fault_name)
            if fault_feature is not None:
                support_center_local = (
                    model.scale(center, inplace=False)
                    if hasattr(model, "scale")
                    else np_array(center, dtype=float)
                )
                support_lengths_local = (
                    np_array(lengths, dtype=float) / float(getattr(model, "scale_factor", 1.0))
                )
                support_region = _make_fault_support_box_region(
                    fault_feature,
                    center=support_center_local,
                    axes=axes,
                    lengths=support_lengths_local,
                )
                fault_feature.add_region(support_region)
                created_fault_features.append(fault_feature)
                created_fault_features_by_name[fault_name] = fault_feature
                support_lengths = np_array(
                    [
                        fault_feature.fault_major_axis,
                        2.0 * fault_feature.fault_intermediate_axis,
                        2.0 * fault_feature.fault_minor_axis,
                    ],
                    dtype=float,
                )
                support_lengths = support_lengths * model.scale_factor
                self.print_terminal(
                    "    Fixed support mask lengths "
                    f"(trace/dip/normal = {lengths[0]:.2f}, {lengths[1]:.2f}, {lengths[2]:.2f})"
                )
                self.print_terminal(
                    "    LoopStructural frame lengths "
                    f"(trace/slip/normal = {support_lengths[0]:.2f}, "
                    f"{support_lengths[1]:.2f}, {support_lengths[2]:.2f})"
                )
                self.print_terminal(
                    f"    Fault '{fault_name}' created successfully (type: {fault_feature.type})"
                )
            else:
                self.print_terminal(
                    f"    WARNING: Could not retrieve fault feature '{fault_name}'"
                )
        except Exception as e:
            import traceback

            self.print_terminal(f"    ERROR creating fault '{fault_name}': {e}")
            self.print_terminal(traceback.format_exc())
        _advance_interpolation_progress()

    if created_fault_features_by_name:
        self.print_terminal("-> Applying fault interactions (abutting)...")
        for source_fault_name in fault_creation_order:
            params = fault_params_by_name.get(source_fault_name, {})
            source_fault = created_fault_features_by_name.get(source_fault_name)
            if source_fault is None:
                continue

            if params.get("has_abutting", False):
                target_fault_name = params.get("abutting_fault")
                if target_fault_name is None:
                    self.print_terminal(
                        f"  WARNING: Abutting enabled for '{source_fault_name}' but no target fault selected."
                    )
                elif target_fault_name == source_fault_name:
                    self.print_terminal(
                        f"  WARNING: Fault '{source_fault_name}' cannot abut itself."
                    )
                else:
                    target_fault = created_fault_features_by_name.get(target_fault_name)
                    if target_fault is None:
                        self.print_terminal(
                            f"  WARNING: Abutting target '{target_fault_name}' not found for '{source_fault_name}'."
                        )
                    else:
                        try:
                            abutting_positive = bool(
                                params.get("abutting_positive", True)
                            )
                            source_fault.add_abutting_fault(
                                target_fault, positive=abutting_positive
                            )
                            self.print_terminal(
                                f"  Abutting relation applied: '{source_fault_name}' with '{target_fault_name}' "
                                f"(side={'positive' if abutting_positive else 'negative'})."
                            )
                        except Exception as e:
                            self.print_terminal(
                                f"  ERROR applying abutting '{source_fault_name}' -> '{target_fault_name}': {e}"
                            )

    toc(parent=self)
    _advance_interpolation_progress("Creating foliations...")

    if sequence_names:
        self.print_terminal("-> Creating foliations (affected by faults)...")
        tic(parent=self)
        for sequence_name in sequence_names:
            eligible_fault_names = [
                fault_name
                for fault_name in fault_creation_order
                if _fault_affects_sequence(
                    fault_data[fault_name].get("time"),
                    sequence_data[sequence_name].get("youngest_time"),
                )
            ]
            foliation_faults = [
                created_fault_features_by_name[fault_name]
                for fault_name in eligible_fault_names
                if fault_name in created_fault_features_by_name
            ]
            try:
                self.print_terminal(
                    f"  Sequence '{sequence_name}' affected by faults: "
                    f"{eligible_fault_names if eligible_fault_names else 'None'}"
                )
                model.create_and_add_foliation(
                    sequence_name,
                    interpolatortype=options_dict["method"],
                    nelements=(dimensions[0] * dimensions[1] * dimensions[2]),
                    faults=foliation_faults if foliation_faults else None,
                )
                self.print_terminal(f"  Foliation '{sequence_name}' created")
            except Exception as e:
                import traceback

                self.print_terminal(
                    f"  ERROR creating foliation '{sequence_name}': {e}"
                )
                self.print_terminal(traceback.format_exc())
            _advance_interpolation_progress()
        toc(parent=self)

    self.print_terminal("-> Evaluating model on regular grid(s)...")
    tic(parent=self)
    regular_grid_faults = model.regular_grid(
        nsteps=dimensions, shuffle=False, rescale=False
    )
    if dimensions_strati == dimensions:
        regular_grid_strati = regular_grid_faults
    else:
        regular_grid_strati = model.regular_grid(
            nsteps=dimensions_strati, shuffle=False, rescale=False
        )
    toc(parent=self)
    _advance_interpolation_progress("Evaluating model features...")

    self.print_terminal("-> Creating output Voxet(s)...")
    tic(parent=self)

    voxet_dict = deepcopy(self.mesh3d_coll.entity_dict)
    voxet_dict["name"] = model_name
    voxet_dict["topology"] = "Voxet"
    voxet_dict["properties_names"] = []
    voxet_dict["properties_components"] = []
    voxet_dict["vtk_obj"] = Voxet()

    aligned_origin_strati = [
        origin_x + spacing_strati[0] / 2,
        origin_y + spacing_strati[1] / 2,
        origin_z + spacing_strati[2] / 2,
    ]
    if use_obb_alignment:
        from vtk import vtkMatrix3x3

        angle = obb_info["angle"]
        obb_center = obb_info["center"]
        c, s = np_cos(angle), np_sin(angle)
        origin_xy = np_array([aligned_origin_strati[0], aligned_origin_strati[1]])
        R_to_world_2d = np_array([[c, -s], [s, c]])
        origin_world_xy = (R_to_world_2d @ origin_xy) + obb_center
        world_origin_strati = [
            origin_world_xy[0],
            origin_world_xy[1],
            aligned_origin_strati[2],
        ]

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

        voxet_dict["vtk_obj"].origin = world_origin_strati
        voxet_dict["vtk_obj"].direction_matrix = direction_matrix
        voxet_world_origin = world_origin_strati
        self.print_terminal("-> Voxet transformed to OBB orientation (stratigraphy)")
    else:
        voxet_dict["vtk_obj"].origin = aligned_origin_strati
        voxet_world_origin = None

    voxet_dict["vtk_obj"].dimensions = dimensions_strati
    voxet_dict["vtk_obj"].spacing = spacing_strati

    fault_voxet_dict = None
    if fault_creation_order:
        fault_voxet_dict = deepcopy(self.mesh3d_coll.entity_dict)
        fault_voxet_dict["name"] = f"{model_name}_faults"
        fault_voxet_dict["topology"] = "Voxet"
        fault_voxet_dict["properties_names"] = []
        fault_voxet_dict["properties_components"] = []
        fault_voxet_dict["vtk_obj"] = Voxet()

        aligned_origin_fault = [
            origin_x + spacing[0] / 2,
            origin_y + spacing[1] / 2,
            origin_z + spacing[2] / 2,
        ]
        if use_obb_alignment:
            from vtk import vtkMatrix3x3

            angle = obb_info["angle"]
            obb_center = obb_info["center"]
            c, s = np_cos(angle), np_sin(angle)
            origin_xy = np_array([aligned_origin_fault[0], aligned_origin_fault[1]])
            R_to_world_2d = np_array([[c, -s], [s, c]])
            origin_world_xy = (R_to_world_2d @ origin_xy) + obb_center
            world_origin_fault = [
                origin_world_xy[0],
                origin_world_xy[1],
                aligned_origin_fault[2],
            ]

            direction_matrix_fault = vtkMatrix3x3()
            direction_matrix_fault.SetElement(0, 0, c)
            direction_matrix_fault.SetElement(0, 1, -s)
            direction_matrix_fault.SetElement(0, 2, 0)
            direction_matrix_fault.SetElement(1, 0, s)
            direction_matrix_fault.SetElement(1, 1, c)
            direction_matrix_fault.SetElement(1, 2, 0)
            direction_matrix_fault.SetElement(2, 0, 0)
            direction_matrix_fault.SetElement(2, 1, 0)
            direction_matrix_fault.SetElement(2, 2, 1)

            fault_voxet_dict["vtk_obj"].origin = world_origin_fault
            fault_voxet_dict["vtk_obj"].direction_matrix = direction_matrix_fault
        else:
            fault_voxet_dict["vtk_obj"].origin = aligned_origin_fault

        fault_voxet_dict["vtk_obj"].dimensions = dimensions
        fault_voxet_dict["vtk_obj"].spacing = spacing

    self.print_terminal(f"  Model features: {[f.name for f in model.features]}")
    fault_names = set(fault_data.keys())

    for feature in model.features:
        interpolation_progress.setLabelText(
            f"Evaluating feature: {feature.name}..."
        )
        self.print_terminal(
            f"  Evaluating feature: {feature.name} (type: {feature.type})"
        )
        try:
            if feature.name in fault_names and fault_voxet_dict is not None:
                grid = regular_grid_faults
                dims = dimensions
                target_voxet = fault_voxet_dict
            else:
                grid = regular_grid_strati
                dims = dimensions_strati
                target_voxet = voxet_dict

            scalar_field = model.evaluate_feature_value(
                feature.name, grid, scale=False
            )
            scalar_field = scalar_field.reshape((dims[0], dims[1], dims[2]))
            scalar_field = scalar_field.transpose(2, 1, 0)
            scalar_field = scalar_field.ravel()

            target_voxet["vtk_obj"].set_point_data(
                data_key=feature.name, attribute_matrix=scalar_field
            )
            target_voxet["properties_names"].append(feature.name)
            target_voxet["properties_components"].append(1)
            self.print_terminal(
                f"    Feature '{feature.name}' evaluated successfully"
            )
        except Exception as e:
            import traceback

            self.print_terminal(f"    ERROR evaluating {feature.name}: {e}")
            self.print_terminal(traceback.format_exc())
        _advance_interpolation_progress()

    voxet_dict["name"] = model_name
    if fault_voxet_dict is not None:
        fault_voxet_dict["name"] = f"{model_name}_faults"

    toc(parent=self)
    _advance_interpolation_progress("Extracting fault surfaces...")

    self.print_terminal("-> Extracting fault surfaces...")
    tic(parent=self)
    pending_fault_surfaces = []
    for fault_name in fault_creation_order:
        interpolation_progress.setLabelText(
            f"Extracting fault surface: {fault_name}..."
        )
        fault_info = fault_data[fault_name]
        try:
            fault_params_single = fault_params_by_name.get(fault_name, {})
            fault_center = np_array(
                fault_params_single.get("center", fault_info["center"]), dtype=float
            )
            fault_axes = np_array(
                fault_params_single.get("axes", fault_info["axes"]), dtype=float
            )
            fault_lengths = np_array(
                fault_params_single.get("lengths", fault_info["lengths"]), dtype=float
            )

            contour_surface = _extract_fault_surface_local_grid(
                model=model,
                fault_name=fault_name,
                center=fault_center,
                axes=fault_axes,
                lengths=fault_lengths,
                target_spacing=target_spacing,
            )
            n_points = int(contour_surface.n_points) if contour_surface is not None else 0
            self.print_terminal(
                f"  Fault '{fault_name}' local-grid isosurface: {n_points} points"
            )

            if n_points > 0:
                surf_dict = deepcopy(self.geol_coll.entity_dict)
                surf_dict["name"] = fault_name
                surf_dict["topology"] = "TriSurf"
                surf_dict["role"] = "fault"
                surf_dict["feature"] = fault_info["feature"]
                surf_dict["scenario"] = fault_info["scenario"]
                surf_dict["vtk_obj"] = TriSurf()
                surf_dict["vtk_obj"].ShallowCopy(contour_surface)
                if use_obb_alignment:
                    surf_dict["vtk_obj"] = transform_vtk_from_aligned_to_world(
                        surf_dict["vtk_obj"], obb_info
                    )
                surf_dict["vtk_obj"].Modified()

                if (
                    isinstance(surf_dict["vtk_obj"].points, np_ndarray)
                    and len(surf_dict["vtk_obj"].points) > 0
                ):
                    pending_fault_surfaces.append((fault_name, surf_dict))
                    self.print_terminal(
                        f"    Fault surface '{fault_name}' extracted ({n_points} points)"
                    )
                else:
                    self.print_terminal(
                        f"    WARNING: Fault surface '{fault_name}' is empty after copy"
                    )
            else:
                self.print_terminal(
                    f"    WARNING: Fault surface '{fault_name}' has no points"
                )
        except Exception as e:
            import traceback

            self.print_terminal(
                f"  ERROR extracting fault surface '{fault_name}': {e}"
            )
            self.print_terminal(traceback.format_exc())
        _advance_interpolation_progress()
    toc(parent=self)

    if sequence_names:
        interpolation_progress.setLabelText("Extracting stratigraphy isosurfaces...")
        self.print_terminal("-> Extracting stratigraphy isosurfaces...")
        tic(parent=self)
        pending_stratigraphy_surfaces = []
        for sequence_name in sequence_names:
            interpolation_progress.setLabelText(
                f"Extracting stratigraphy: {sequence_name}..."
            )
            try:
                if sequence_name not in voxet_dict["properties_names"]:
                    self.print_terminal(
                        f"  WARNING: Sequence property '{sequence_name}' not found in voxet properties"
                    )
                    continue

                metadata_by_time = sequence_data[sequence_name]["metadata_by_time"]
                sequence_values = sorted(metadata_by_time.keys(), reverse=True)
                if not sequence_values:
                    self.print_terminal(
                        f"  WARNING: Sequence '{sequence_name}' has no valid interface times to extract."
                    )
                    continue

                voxet_dict["vtk_obj"].GetPointData().SetActiveScalars(sequence_name)
                self.print_terminal(
                    f"  Sequence '{sequence_name}' values to extract: {sequence_values}"
                )
                for value in sequence_values:
                    metadata = metadata_by_time.get(value, {})
                    self.print_terminal(
                        f"  Extracting iso-surface for '{sequence_name}' at value = {float(value)}"
                    )
                    iso_surface = vtkContourFilter()
                    iso_surface.SetInputData(voxet_dict["vtk_obj"])
                    iso_surface.ComputeScalarsOn()
                    iso_surface.ComputeGradientsOn()
                    iso_surface.SetArrayComponent(0)
                    iso_surface.GenerateTrianglesOn()
                    iso_surface.UseScalarTreeOn()
                    iso_surface.SetValue(0, float(value))
                    iso_surface.Update()

                    n_points = iso_surface.GetOutput().GetNumberOfPoints()
                    self.print_terminal(
                        f"    Isosurface at {float(value)}: {n_points} points"
                    )
                    if n_points <= 0:
                        self.print_terminal(
                            f"      WARNING: Isosurface at {float(value)} has no points"
                        )
                        continue

                    surf_dict = deepcopy(self.geol_coll.entity_dict)
                    surf_dict["name"] = metadata.get("feature", sequence_name)
                    surf_dict["topology"] = "TriSurf"
                    surf_dict["role"] = metadata.get("role", "undef")
                    surf_dict["feature"] = metadata.get("feature", sequence_name)
                    surf_dict["scenario"] = metadata.get("scenario", "undef")
                    surf_dict["vtk_obj"] = TriSurf()
                    surf_dict["vtk_obj"].ShallowCopy(iso_surface.GetOutput())
                    if use_obb_alignment:
                        surf_dict["vtk_obj"] = transform_vtk_to_obb(
                            surf_dict["vtk_obj"], obb_info, voxet_world_origin
                        )
                    surf_dict["vtk_obj"].Modified()

                    if (
                        isinstance(surf_dict["vtk_obj"].points, np_ndarray)
                        and len(surf_dict["vtk_obj"].points) > 0
                    ):
                        pending_stratigraphy_surfaces.append(
                            (metadata.get("feature", sequence_name), surf_dict)
                        )
                        self.print_terminal(
                            f"      Iso-surface at value = {float(value)} created ({n_points} points)"
                        )
                    else:
                        self.print_terminal(
                            f"      WARNING: Isosurface at {float(value)} is empty after copy"
                        )
            except Exception as e:
                import traceback

                self.print_terminal(
                    f"  ERROR extracting stratigraphy surfaces for '{sequence_name}': {e}"
                )
                self.print_terminal(traceback.format_exc())
            _advance_interpolation_progress()
        toc(parent=self)
    else:
        pending_stratigraphy_surfaces = []

    voxet_dict["vtk_obj"].Modified()
    interpolation_progress.close()

    model_name_input = input_text_dialog(
        title="Implicit Modelling with Faults",
        label="Name of the output Voxet",
        default_text=model_name,
    )
    if model_name_input:
        model_name = model_name_input

    voxet_dict["name"] = model_name
    if fault_voxet_dict is not None:
        fault_voxet_dict["name"] = f"{model_name}_faults"

    if voxet_dict["vtk_obj"].points_number > 0:
        self.mesh3d_coll.add_entity_from_dict(voxet_dict)
        self.print_terminal(
            f"  Voxet '{model_name}' created with properties: {voxet_dict['properties_names']}"
        )
    if (
        fault_voxet_dict is not None
        and fault_voxet_dict["vtk_obj"].points_number > 0
        and fault_voxet_dict["properties_names"]
    ):
        self.mesh3d_coll.add_entity_from_dict(fault_voxet_dict)
        self.print_terminal(
            f"  Voxet '{fault_voxet_dict['name']}' created with properties: "
            f"{fault_voxet_dict['properties_names']}"
        )

    for fault_name, surf_dict in pending_fault_surfaces:
        surf_dict["name"] = f"{fault_name}_surface_from_{model_name}"
        self.geol_coll.add_entity_from_dict(surf_dict)

    for surface_feature_name, surf_dict in pending_stratigraphy_surfaces:
        surf_dict["name"] = f"{surface_feature_name}_from_{model_name}"
        self.geol_coll.add_entity_from_dict(surf_dict)

    self.print_terminal("Loop interpolation with faults completed.")


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
    # Create deepcopy of the geological entity dictionary.
    surf_dict = deepcopy(self.geol_coll.entity_dict)
    input_dict = {
        "name": [
            "TriSurf name: ",
            self.geol_coll.get_uid_name(input_uids[0]) + "_extruded",
        ],
        "role": [
            "Role: ",
            self.geol_coll.valid_roles,
        ],
        "feature": [
            "Feature: ",
            self.geol_coll.get_uid_feature(input_uids[0]),
        ],
        "scenario": ["Scenario: ", self.geol_coll.get_uid_scenario(input_uids[0])],
    }
    surf_dict_updt = multiple_input_dialog(
        title="Linear Extrusion", input_dict=input_dict
    )
    # Check if the output of the widget is empty or not. If the Cancel button was clicked, the tool quits
    if surf_dict_updt is None:
        return
    # Getting the values that have been typed by the user through the multiple input widget
    for key in surf_dict_updt:
        surf_dict[key] = surf_dict_updt[key]
    surf_dict["topology"] = "TriSurf"
    surf_dict["vtk_obj"] = TriSurf()
    # Check if the output of the widget is empty or not. If the Cancel button was clicked, the tool quits
    if surf_dict_updt is None:
        return
    # Ask for trend/plunge of the vector to use for the linear extrusion
    trend = input_one_value_dialog(
        title="Linear Extrusion", label="Trend Value", default_value=90.0
    )
    if trend is None:
        trend = 90.00
    plunge = input_one_value_dialog(
        title="Linear Extrusion", label="Plunge Value", default_value=30.0
    )
    if plunge is None:
        plunge = 30.0
    # Ask for vertical extrusion: how extruded will the surface be?
    extrusion_par = {"bottom": ["Lower limit:", -1000], "top": ["Higher limit", 1000]}
    vertical_extrusion = multiple_input_dialog(
        title="Vertical Extrusion", input_dict=extrusion_par
    )
    if vertical_extrusion is None:
        self.print_terminal(
            "Wrong extrusion parameters, please check the top and bottom values"
        )
        return

    total_extrusion = vertical_extrusion["top"] + np_abs(vertical_extrusion["bottom"])
    linear_extrusion = vtkLinearExtrusionFilter()
    linear_extrusion.CappingOn()  # yes or no?
    linear_extrusion.SetExtrusionTypeToVectorExtrusion()
    # Direction cosines
    x_vector = -(np_cos((trend - 90) * np_pi / 180) * np_cos(plunge * np_pi / 180))
    y_vector = np_sin((trend - 90) * np_pi / 180) * np_cos(plunge * np_pi / 180)
    z_vector = np_sin(plunge * np_pi / 180)
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

