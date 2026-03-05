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

    # Keep a right-handed frame.
    if np_dot(np_cross(axes[0], axes[1]), axes[2]) < 0:
        axes[2] = -axes[2]

    return center, axes, lengths


def _orient_fault_axes_for_rake(axes, center_normal=None):
    """
    Orient fault axes so rake conventions are stable:
    - intermediate axis points to the "upper" direction on the fault plane
    - normal axis is aligned with center_normal when available
    - deterministic fallback for vertical/degenerate cases
    """
    from numpy import array as np_array
    from numpy import dot as np_dot
    from numpy import cross as np_cross
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
    normal = _normed(axes[2], fallback=[0.0, 0.0, 1.0])

    north = np_array([0.0, 1.0, 0.0], dtype=float)

    if center_normal is not None:
        cn = _normed(np_array(center_normal, dtype=float), fallback=[0.0, 0.0, 1.0])
        if np_dot(normal, cn) < 0.0:
            normal = -normal
    elif abs(normal[2]) <= 1e-6:
        # Rare vertical-fault fallback requested by user: point normal to north.
        if np_dot(normal, north) < 0.0:
            normal = -normal

    up = np_array([0.0, 0.0, 1.0], dtype=float)

    # Up direction projected on fault plane: gives deterministic up-dip direction.
    up_proj = up - np_dot(up, normal) * normal
    if np_linalg.norm(up_proj) <= 1e-9:
        # Rare fallback: if projection is degenerate, use north projected on plane.
        up_proj = north - np_dot(north, normal) * normal

    if np_linalg.norm(up_proj) > 1e-9:
        intermediate = _normed(up_proj, fallback=[0.0, 1.0, 0.0])
        major_candidate = np_cross(intermediate, normal)
        major = _normed(major_candidate, fallback=major)
    else:
        # Last-resort orthonormalization from current major.
        major = major - np_dot(major, normal) * normal
        major = _normed(major, fallback=[1.0, 0.0, 0.0])
        intermediate = _normed(np_cross(normal, major), fallback=[0.0, 1.0, 0.0])

    # Keep right-handed frame.
    if np_dot(np_cross(major, intermediate), normal) < 0.0:
        major = -major

    return np_array([major, intermediate, normal], dtype=float)


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


def _fault_obb_settings_dialog(
    parent,
    fault_data,
    default_displacement,
    default_rake=-90.0,
    default_nelements=1000,
    default_fault_buffer=0.5,
):
    """
    Interactive per-fault settings dialog.

    Allows selecting each fault, adjusting OBB dimensions and fault parameters,
    and previewing fault points + OBB fit.
    """
    from numpy import array as np_array
    from PySide6.QtWidgets import (
        QCheckBox,
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QDoubleSpinBox,
        QFormLayout,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QSpinBox,
        QVBoxLayout,
        QWidget,
    )
    from PySide6.QtCore import Qt, QPointF
    from PySide6.QtGui import QColor, QPainter, QPen

    if not fault_data:
        return {}

    fault_names = list(fault_data.keys())
    current_fault = {"name": fault_names[0]}
    is_loading = {"active": False}

    defaults_by_fault = {}
    for fault_name in fault_names:
        defaults_by_fault[fault_name] = {
            "displacement": float(default_displacement),
            "rake": float(default_rake),
            "nelements": int(default_nelements),
            "fault_buffer": float(default_fault_buffer),
            "major_scale_pct": 100.0,
            "intermediate_scale_pct": 100.0,
            "minor_scale_pct": 100.0,
            "has_abutting": False,
            "abutting_fault": None,
            "has_splay": False,
            "splay_fault": None,
        }

    dialog = QDialog(parent)
    dialog.setWindowTitle("Fault Parameters and OBB Fit")
    dialog.resize(900, 700)

    root_layout = QVBoxLayout(dialog)
    info_label = QLabel(
        "Configure each fault independently.\n"
        "Use OBB scale controls to enlarge/shrink the fault box before interpolation.\n"
        "Optional: define abutting/splay relations with other faults."
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

    nelements_spin = QSpinBox(dialog)
    nelements_spin.setRange(10, 5000000)
    nelements_spin.setValue(default_nelements)
    parameters_form.addRow("N elements", nelements_spin)

    fault_buffer_spin = QDoubleSpinBox(dialog)
    fault_buffer_spin.setDecimals(3)
    fault_buffer_spin.setRange(0.0, 100.0)
    fault_buffer_spin.setSingleStep(0.1)
    fault_buffer_spin.setValue(default_fault_buffer)
    parameters_form.addRow("Fault buffer", fault_buffer_spin)

    controls_layout.addLayout(parameters_form, 0, 0)

    obb_form = QFormLayout()
    major_scale_spin = QDoubleSpinBox(dialog)
    major_scale_spin.setDecimals(1)
    major_scale_spin.setRange(5.0, 500.0)
    major_scale_spin.setSingleStep(5.0)
    major_scale_spin.setSuffix(" %")
    major_scale_spin.setValue(100.0)
    obb_form.addRow("Major scale", major_scale_spin)

    intermediate_scale_spin = QDoubleSpinBox(dialog)
    intermediate_scale_spin.setDecimals(1)
    intermediate_scale_spin.setRange(5.0, 500.0)
    intermediate_scale_spin.setSingleStep(5.0)
    intermediate_scale_spin.setSuffix(" %")
    intermediate_scale_spin.setValue(100.0)
    obb_form.addRow("Intermediate scale", intermediate_scale_spin)

    minor_scale_spin = QDoubleSpinBox(dialog)
    minor_scale_spin.setDecimals(1)
    minor_scale_spin.setRange(5.0, 500.0)
    minor_scale_spin.setSingleStep(5.0)
    minor_scale_spin.setSuffix(" %")
    minor_scale_spin.setValue(100.0)
    obb_form.addRow("Minor scale", minor_scale_spin)

    raw_lengths_label = QLabel("")
    scaled_lengths_label = QLabel("")
    obb_form.addRow("Raw OBB lengths", raw_lengths_label)
    obb_form.addRow("Scaled OBB lengths", scaled_lengths_label)
    controls_layout.addLayout(obb_form, 0, 1)

    relations_form = QFormLayout()
    abutting_check = QCheckBox("Present")
    abutting_target_combo = QComboBox(dialog)
    splay_check = QCheckBox("Present")
    splay_target_combo = QComboBox(dialog)

    relations_form.addRow("Abutting", abutting_check)
    relations_form.addRow("Abutting with", abutting_target_combo)
    relations_form.addRow("Splay", splay_check)
    relations_form.addRow("Splay with", splay_target_combo)
    controls_layout.addLayout(relations_form, 0, 2)

    preview_group = QGroupBox("OBB Preview", dialog)
    preview_layout = QVBoxLayout(preview_group)
    root_layout.addWidget(preview_group, stretch=1)

    class FaultObbPreviewWidget(QWidget):
        """2D preview widget (major/intermediate plane) without OpenGL."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self._fault_name = ""
            self._points_uv = None
            self._rect_uv = None
            self._minor_len = 0.0
            self.setMinimumHeight(260)

        def set_fault_preview(self, fault_name, points_uv, rect_uv, minor_len):
            self._fault_name = fault_name
            self._points_uv = points_uv
            self._rect_uv = rect_uv
            self._minor_len = minor_len
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
            bounds = (min_u, max_u, min_v, max_v)

            # Draw OBB rectangle.
            painter.setPen(QPen(QColor(220, 70, 70), 2))
            rect_points = [self._map_to_widget(uv, bounds, draw_rect) for uv in rect_uv]
            for i in range(4):
                p1 = rect_points[i]
                p2 = rect_points[(i + 1) % 4]
                painter.drawLine(p1, p2)

            # Draw fault points.
            painter.setPen(QPen(QColor(230, 230, 230), 1))
            for uv in points_uv:
                p = self._map_to_widget(uv, bounds, draw_rect)
                painter.drawEllipse(p, 2.0, 2.0)

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
                f"{self._fault_name}\nPlane: major/intermediate\nMinor length: {self._minor_len:.2f}",
            )
            painter.end()

    preview_widget = FaultObbPreviewWidget(preview_group)
    preview_layout.addWidget(preview_widget)

    button_box = QDialogButtonBox(
        QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=dialog
    )
    root_layout.addWidget(button_box)
    button_box.accepted.connect(dialog.accept)
    button_box.rejected.connect(dialog.reject)

    def get_scaled_lengths(fault_name):
        base_lengths = np_array(fault_data[fault_name]["lengths"], dtype=float)
        params = defaults_by_fault[fault_name]
        scales = np_array(
            [
                params["major_scale_pct"] / 100.0,
                params["intermediate_scale_pct"] / 100.0,
                params["minor_scale_pct"] / 100.0,
            ],
            dtype=float,
        )
        return base_lengths * scales

    def update_relation_controls_enabled():
        has_other_faults = len(fault_names) > 1
        abutting_target_combo.setEnabled(has_other_faults and abutting_check.isChecked())
        splay_target_combo.setEnabled(has_other_faults and splay_check.isChecked())

    def populate_relation_targets(fault_name, preferred_abutting=None, preferred_splay=None):
        target_faults = [name for name in fault_names if name != fault_name]

        def _populate_combo(combo, preferred_target):
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("None", None)
            for target_name in target_faults:
                target_label = f"{fault_data[target_name]['name']} ({target_name})"
                combo.addItem(target_label, target_name)
            idx = 0
            if preferred_target is not None:
                found_idx = combo.findData(preferred_target)
                if found_idx >= 0:
                    idx = found_idx
            combo.setCurrentIndex(idx)
            combo.blockSignals(False)

        _populate_combo(abutting_target_combo, preferred_abutting)
        _populate_combo(splay_target_combo, preferred_splay)
        update_relation_controls_enabled()

    def save_current_fault_settings():
        fault_name = current_fault["name"]
        defaults_by_fault[fault_name]["displacement"] = float(displacement_spin.value())
        defaults_by_fault[fault_name]["rake"] = float(rake_spin.value())
        defaults_by_fault[fault_name]["nelements"] = int(nelements_spin.value())
        defaults_by_fault[fault_name]["fault_buffer"] = float(fault_buffer_spin.value())
        defaults_by_fault[fault_name]["major_scale_pct"] = float(major_scale_spin.value())
        defaults_by_fault[fault_name]["intermediate_scale_pct"] = float(
            intermediate_scale_spin.value()
        )
        defaults_by_fault[fault_name]["minor_scale_pct"] = float(minor_scale_spin.value())
        defaults_by_fault[fault_name]["has_abutting"] = bool(abutting_check.isChecked())
        defaults_by_fault[fault_name]["abutting_fault"] = abutting_target_combo.currentData()
        defaults_by_fault[fault_name]["has_splay"] = bool(splay_check.isChecked())
        defaults_by_fault[fault_name]["splay_fault"] = splay_target_combo.currentData()

    def update_lengths_labels(fault_name):
        base_lengths = np_array(fault_data[fault_name]["lengths"], dtype=float)
        scaled_lengths = get_scaled_lengths(fault_name)
        raw_lengths_label.setText(
            f"{base_lengths[0]:.2f}, {base_lengths[1]:.2f}, {base_lengths[2]:.2f}"
        )
        scaled_lengths_label.setText(
            f"{scaled_lengths[0]:.2f}, {scaled_lengths[1]:.2f}, {scaled_lengths[2]:.2f}"
        )

    def update_preview(fault_name):
        fault_points = np_array(fault_data[fault_name]["points"], dtype=float)
        center = np_array(fault_data[fault_name]["center"], dtype=float)
        axes = np_array(fault_data[fault_name]["axes"], dtype=float)
        scaled_lengths = get_scaled_lengths(fault_name)

        if fault_points is None or len(fault_points) == 0:
            preview_widget.set_fault_preview(
                fault_name=fault_name,
                points_uv=np_array([[0.0, 0.0]], dtype=float),
                rect_uv=np_array([[-1, -1], [1, -1], [1, 1], [-1, 1]], dtype=float),
                minor_len=float(scaled_lengths[2]),
            )
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

        preview_widget.set_fault_preview(
            fault_name=fault_name,
            points_uv=points_uv,
            rect_uv=rect_uv,
            minor_len=float(scaled_lengths[2]),
        )

    def load_fault_settings(fault_name):
        is_loading["active"] = True
        try:
            params = defaults_by_fault[fault_name]
            displacement_spin.setValue(params["displacement"])
            rake_spin.setValue(params["rake"])
            nelements_spin.setValue(params["nelements"])
            fault_buffer_spin.setValue(params["fault_buffer"])
            major_scale_spin.setValue(params["major_scale_pct"])
            intermediate_scale_spin.setValue(params["intermediate_scale_pct"])
            minor_scale_spin.setValue(params["minor_scale_pct"])
            abutting_check.setChecked(bool(params.get("has_abutting", False)))
            splay_check.setChecked(bool(params.get("has_splay", False)))
            populate_relation_targets(
                fault_name,
                preferred_abutting=params.get("abutting_fault"),
                preferred_splay=params.get("splay_fault"),
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
    nelements_spin.valueChanged.connect(on_controls_changed)
    fault_buffer_spin.valueChanged.connect(on_controls_changed)
    major_scale_spin.valueChanged.connect(on_controls_changed)
    intermediate_scale_spin.valueChanged.connect(on_controls_changed)
    minor_scale_spin.valueChanged.connect(on_controls_changed)
    abutting_check.toggled.connect(on_controls_changed)
    splay_check.toggled.connect(on_controls_changed)
    abutting_target_combo.currentIndexChanged.connect(on_controls_changed)
    splay_target_combo.currentIndexChanged.connect(on_controls_changed)

    load_fault_settings(current_fault["name"])

    result = dialog.exec()
    if result != QDialog.Accepted:
        return None

    save_current_fault_settings()
    per_fault_settings = {}
    for fault_name in fault_names:
        params = defaults_by_fault[fault_name]
        per_fault_settings[fault_name] = {
            "displacement": float(params["displacement"]),
            "rake": float(params["rake"]),
            "nelements": int(params["nelements"]),
            "fault_buffer": float(params["fault_buffer"]),
            "center": fault_data[fault_name]["center"],
            "axes": fault_data[fault_name]["axes"],
            "lengths": get_scaled_lengths(fault_name),
            "has_abutting": bool(params.get("has_abutting", False)),
            "abutting_fault": params.get("abutting_fault"),
            "has_splay": bool(params.get("has_splay", False)),
            "splay_fault": params.get("splay_fault"),
        }

    return per_fault_settings


@freeze_gui_onoff
def implicit_model_loop_structural_with_faults(self):
    """
    Enhanced LoopStructural implicit modelling with fault support.
    
    This function extends the standard implicit modelling to properly handle
    faults by:
    1. Separating fault entities from stratigraphy entities based on role
    2. Computing fault geometry using OBB analysis (PCA fallback)
    3. Creating faults using LoopStructural's create_and_add_fault()
    4. Creating foliations that are properly affected by faults
    
    Input Data Organization (same as implicit_model_loop_structural):
    X, Y, Z - cartesian coordinates
    feature_name - unique name from legend sequence
    val - scalar field value from legend time
    nx, ny, nz - gradient norm components (if available)
    """
    #We need to make the fault boundary to be freely oriented within the main boundary
    self.print_terminal(
        "LoopStructural implicit geomodeller WITH FAULT SUPPORT\n"
        "github.com/Loop3D/LoopStructural"
    )
    if self.shown_table != "tabGeology":
        self.print_terminal(" -- Only geological objects can be interpolated -- ")
        return
    
    # Check if some vtkPolyData is selected
    if not self.selected_uids:
        self.print_terminal("No input data selected.")
        return
    
    input_uids = deepcopy(self.selected_uids)
    
    # Separate fault entities from stratigraphy entities
    fault_uids = []
    strati_uids = []
    for uid in input_uids:
        role = self.geol_coll.get_uid_role(uid)
        if role == "fault":
            fault_uids.append(uid)
        else:
            strati_uids.append(uid)
    
    self.print_terminal(f"Found {len(fault_uids)} fault entities and {len(strati_uids)} stratigraphy entities")
    
    if not fault_uids:
        self.print_terminal("No fault entities found. Use standard implicit_model_loop_structural for surfaces only.")
        return
    
    if not strati_uids:
        self.print_terminal("WARNING: No stratigraphy entities found. Model will only contain faults.")
    
    # Dictionary for Loop input data
    loop_input_dict = {
        "X": None, "Y": None, "Z": None,
        "feature_name": None, "val": None, "interface": None,
        "nx": None, "ny": None, "nz": None,
        "gx": None, "gy": None, "gz": None,
        "tx": None, "ty": None, "tz": None,
        "coord": None,
    }
    
    # Create dataframes to collect input data
    self.print_terminal("-> Creating input dataframes...")
    tic(parent=self)
    
    all_input_data_df = pd_DataFrame(columns=list(loop_input_dict.keys()))
    fault_data = {}  # Store fault-specific data and geometry
    
    # Process fault entities
    prgs_bar = progress_dialog(
        max_value=len(fault_uids),
        title_txt="Processing Faults",
        label_txt="Analyzing fault geometry...",
        cancel_txt=None,
        parent=self,
    )
    
    for uid in fault_uids:
        entity_df = pd_DataFrame(columns=list(loop_input_dict.keys()))
        vtk_obj = self.geol_coll.get_uid_vtk_obj(uid)
        points = vtk_obj.points
        entity_df[["X", "Y", "Z"]] = points
        points_arr = np_array(points, dtype=float)
        
        # Compute fault geometry from OBB (fallback to PCA when needed).
        center, axes, lengths = _compute_fault_geometric_features_obb(points_arr)
        fault_normal_seed = axes[2] if len(axes) > 2 else np_array([0, 0, 1])
        
        has_entity_normals = "Normals" in self.geol_coll.get_uid_properties_names(uid)

        # Check if entity already has normals, otherwise use OBB/PCA-computed normal.
        if has_entity_normals:
            normals_arr = np_array(
                self.geol_coll.get_uid_property(
                    uid=uid, property_name="Normals"
                ),
                dtype=float,
            )
            entity_df[["nx", "ny", "nz"]] = normals_arr
            self.print_terminal(f"    Using existing normals from entity data")
        else:
            normals_arr = np_array(
                [[fault_normal_seed[0], fault_normal_seed[1], fault_normal_seed[2]]] * len(points_arr),
                dtype=float,
            )
            # Temporarily add normal; we will overwrite with oriented normal below.
            entity_df["nx"] = fault_normal_seed[0]
            entity_df["ny"] = fault_normal_seed[1]
            entity_df["nz"] = fault_normal_seed[2]

        # Get center normal from nearest fault point.
        center_normal = None
        if has_entity_normals and len(points_arr) > 0 and len(normals_arr) == len(points_arr):
            from numpy import argmin as np_argmin
            from numpy import linalg as np_linalg
            dist2 = np_sum((points_arr - center) ** 2, axis=1)
            center_idx = int(np_argmin(dist2))
            candidate_normal = np_array(normals_arr[center_idx], dtype=float)
            n_norm = np_linalg.norm(candidate_normal)
            if n_norm > 1e-9:
                center_normal = candidate_normal / n_norm

        # Orient axes so rake sign is consistent with upper/lower fault face.
        axes = _orient_fault_axes_for_rake(axes, center_normal=center_normal)
        fault_normal = axes[2] if len(axes) > 2 else np_array([0, 0, 1])

        if not has_entity_normals:
            # Update with oriented normal when original normals are missing.
            entity_df["nx"] = fault_normal[0]
            entity_df["ny"] = fault_normal[1]
            entity_df["nz"] = fault_normal[2]
            self.print_terminal(
                f"    Adding OBB/PCA oriented fault normal: [{fault_normal[0]:.4f}, {fault_normal[1]:.4f}, {fault_normal[2]:.4f}]"
            )
        else:
            if center_normal is not None:
                self.print_terminal(
                    f"    Center normal used for rake orientation: [{center_normal[0]:.4f}, {center_normal[1]:.4f}, {center_normal[2]:.4f}]"
                )
            else:
                self.print_terminal(
                    "    Center normal unavailable; using deterministic OBB orientation fallback."
                )
        
        # IMPORTANT: Use a UNIQUE fault feature name (not the shared sequence!)
        # Faults need their own unique name to be created separately from stratigraphy
        fault_feature_name_base = self.geol_coll.get_uid_feature(uid)
        # If feature name is too generic, use entity name instead.
        entity_name = self.geol_coll.get_uid_name(uid)
        if not fault_feature_name_base or fault_feature_name_base == "undef":
            fault_feature_name_base = entity_name
        # Prefix with "fault_" and append UID to avoid collisions among same-feature faults.
        fault_feature_name = f"fault_{fault_feature_name_base}_{uid[:8]}"
        
        entity_df["feature_name"] = fault_feature_name
        entity_df["val"] = 0  # Fault surface is at value 0
        
        # Store fault data with the unique fault name
        fault_data[fault_feature_name] = {
            "uid": uid,
            "center": center,
            "axes": axes,
            "lengths": lengths,
            "center_normal": center_normal,
            "name": entity_name,
            "feature": self.geol_coll.get_uid_feature(uid),
            "scenario": self.geol_coll.get_uid_scenario(uid),
            "points": points_arr,
        }
        
        self.print_terminal(f"  Fault '{fault_feature_name}': center={center}, lengths={lengths}")
        
        all_input_data_df = pd_concat([all_input_data_df, entity_df], ignore_index=True)
        prgs_bar.add_one()
    
    prgs_bar.close()
    
    # Process stratigraphy entities
    if strati_uids:
        prgs_bar = progress_dialog(
            max_value=len(strati_uids),
            title_txt="Processing Stratigraphy",
            label_txt="Adding stratigraphy to dataframe...",
            cancel_txt=None,
            parent=self,
        )
        
        # Use a single consistent name for all stratigraphy data
        strati_feature_name = "stratigraphy"
        
        for uid in strati_uids:
            entity_df = pd_DataFrame(columns=list(loop_input_dict.keys()))
            entity_df[["X", "Y", "Z"]] = self.geol_coll.get_uid_vtk_obj(uid).points
            
            if "Normals" in self.geol_coll.get_uid_properties_names(uid):
                entity_df[["nx", "ny", "nz"]] = self.geol_coll.get_uid_property(
                    uid=uid, property_name="Normals"
                )
            
            # Use consistent stratigraphy feature name for all non-fault entities
            entity_df["feature_name"] = strati_feature_name
            
            val_single = self.geol_coll.legend_df.loc[
                (self.geol_coll.legend_df["role"] == self.geol_coll.get_uid_role(uid))
                & (self.geol_coll.legend_df["feature"] == self.geol_coll.get_uid_feature(uid))
                & (self.geol_coll.legend_df["scenario"] == self.geol_coll.get_uid_scenario(uid)),
                "time",
            ].values[0]
            if val_single == -999999.0:
                val_single = float("nan")
            entity_df["val"] = val_single
            
            all_input_data_df = pd_concat([all_input_data_df, entity_df], ignore_index=True)
            prgs_bar.add_one()
        
        prgs_bar.close()
    
    toc(parent=self)
    
    # Drop empty columns
    self.print_terminal("-> Drop empty columns...")
    tic(parent=self)
    all_input_data_df.dropna(axis=1, how="all", inplace=True)
    toc(parent=self)
    
    # Ask for model parameters
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
            "method": "PLI"
        }
    
    # Get bounding box from boundary (with optional OBB alignment as in implicit_model_loop_structural)
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
        origin_x, origin_y, origin_z_temp, maximum_x, maximum_y, maximum_z_temp = get_aligned_bounds_from_obb(
            self.boundary_coll, boundary_uid, obb_info
        )
        all_input_data_df = transform_points_to_aligned(all_input_data_df, obb_info)

        # Keep fault geometry consistent with transformed model coordinates.
        angle = obb_info["angle"]
        obb_center = obb_info["center"]
        c, s = np_cos(angle), np_sin(angle)
        R_to_local = np_array([[c, s], [-s, c]])
        for fault_name, fault_info in fault_data.items():
            fault_points = np_array(fault_info.get("points", []), dtype=float)
            if len(fault_points) > 0:
                xy = fault_points[:, :2]
                xy_centered = xy - obb_center
                xy_rotated = (R_to_local @ xy_centered.T).T
                points_aligned = fault_points.copy()
                points_aligned[:, 0] = xy_rotated[:, 0]
                points_aligned[:, 1] = xy_rotated[:, 1]
            else:
                points_aligned = fault_points

            center_aligned, axes_aligned, lengths_aligned = _compute_fault_geometric_features_obb(
                points_aligned
            )
            center_normal_aligned = fault_info.get("center_normal")
            if center_normal_aligned is not None:
                center_normal_aligned = np_array(center_normal_aligned, dtype=float)
                nxy = center_normal_aligned[:2]
                nxy_rotated = (R_to_local @ nxy.reshape(2, 1)).ravel()
                center_normal_aligned = np_array(
                    [nxy_rotated[0], nxy_rotated[1], center_normal_aligned[2]],
                    dtype=float,
                )

            fault_info["points"] = points_aligned
            fault_info["center"] = center_aligned
            fault_info["axes"] = axes_aligned
            fault_info["lengths"] = lengths_aligned
            fault_info["center_normal"] = center_normal_aligned

        self.print_terminal(
            f"-> Data transformed. New aligned bounds: X[{origin_x:.2f}, {maximum_x:.2f}], Y[{origin_y:.2f}, {maximum_y:.2f}]"
        )
    else:
        origin_x, maximum_x = bounds[0], bounds[1]
        origin_y, maximum_y = bounds[2], bounds[3]
    
    if bounds[4] == bounds[5]:
        # 2D boundary - ask for vertical extension
        vertical_extension_in = {
            "message": ["Model vertical extension", 
                       "Define MAX and MIN vertical extension of the 3D implicit model.",
                       "QLabel"],
            "top": ["Insert top", 1000.0, "QLineEdit"],
            "bottom": ["Insert bottom", -1000.0, "QLineEdit"],
        }
        vertical_extension_updt = general_input_dialog(
            title="Implicit Modelling with Faults",
            input_dict=vertical_extension_in,
        )
        origin_z = float(vertical_extension_updt.get("bottom", -1000.0))
        maximum_z = float(vertical_extension_updt.get("top", 1000.0))
        if origin_z > maximum_z:
            origin_z, maximum_z = maximum_z, origin_z
    else:
        origin_z, maximum_z = bounds[4], bounds[5]
    
    edge_x = maximum_x - origin_x
    edge_y = maximum_y - origin_y
    edge_z = maximum_z - origin_z
    origin = [origin_x, origin_y, origin_z]
    maximum = [maximum_x, maximum_y, maximum_z]
    
    self.print_terminal(f"Model origin: {origin}")
    self.print_terminal(f"Model maximum: {maximum}")
    
    # Check overlap
    if (all_input_data_df["X"].min() > maximum_x or all_input_data_df["X"].max() < origin_x
        or all_input_data_df["Y"].min() > maximum_y or all_input_data_df["Y"].max() < origin_y
        or all_input_data_df["Z"].min() > maximum_z or all_input_data_df["Z"].max() < origin_z):
        self.print_terminal("ERROR: Bounding Box does not intersect input data")
        return
    
    # Ask for grid spacing
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
    
    self.print_terminal(f"Grid dimensions: {dimensions}")
    self.print_terminal(f"Grid spacing: {spacing}")
    
    # Calculate a sensible default displacement based on model size
    model_diagonal = np_sqrt(edge_x**2 + edge_y**2 + edge_z**2)
    default_displacement = model_diagonal * 0.05  # 5% of model diagonal as default
    # Ask per-fault parameters and OBB scaling.
    fault_params_by_name = _fault_obb_settings_dialog(
        parent=self,
        fault_data=fault_data,
        default_displacement=default_displacement,
        default_rake=-90.0,
        default_nelements=1000,
        default_fault_buffer=0.5,
    )
    if fault_params_by_name is None:
        self.print_terminal(
            "Fault settings dialog cancelled. Using defaults for all faults."
        )
        fault_params_by_name = {}
        for fault_name, fault_info in fault_data.items():
            fault_params_by_name[fault_name] = {
                "displacement": float(default_displacement),
                "rake": -90.0,
                "nelements": 1000,
                "fault_buffer": 0.5,
                "center": fault_info["center"],
                "axes": fault_info["axes"],
                "lengths": fault_info["lengths"],
                "has_abutting": False,
                "abutting_fault": None,
                "has_splay": False,
                "splay_fault": None,
            }
    else:
        self.print_terminal("Per-fault parameters configured:")
        for fault_name, params in fault_params_by_name.items():
            self.print_terminal(
                f"  {fault_name}: displacement={params['displacement']:.2f}, "
                f"rake={params['rake']:.1f} deg, nelements={params['nelements']}, "
                f"buffer={params['fault_buffer']:.2f}, "
                f"lengths={params['lengths']}, "
                f"abutting={params.get('abutting_fault') if params.get('has_abutting') else 'None'}, "
                f"splay={params.get('splay_fault') if params.get('has_splay') else 'None'}"
            )    
    # Create LoopStructural model
    self.print_terminal("-> Creating LoopStructural model...")
    tic(parent=self)
    model = GeologicalModel(origin, maximum)
    # Use set_model_data() method - this is the correct way to assign data
    model.set_model_data(all_input_data_df)
    toc(parent=self)
    
    self.print_terminal(f"all_input_data_df:\n{all_input_data_df}")
    
    # Create faults FIRST (they must exist before foliation that references them)
    self.print_terminal("-> Creating faults...")
    tic(parent=self)
    created_fault_features = []
    created_fault_features_by_name = {}
    
    for fault_name, fault_info in fault_data.items():
        self.print_terminal(f"  Creating fault: {fault_name}")

        fault_params_single = fault_params_by_name.get(fault_name, {})
        center = fault_params_single.get("center", fault_info["center"])
        axes = fault_params_single.get("axes", fault_info["axes"])
        axes = _orient_fault_axes_for_rake(
            axes, center_normal=fault_info.get("center_normal")
        )
        lengths = fault_params_single.get("lengths", fault_info["lengths"])
        displacement = float(
            fault_params_single.get("displacement", default_displacement)
        )
        fault_rake = float(fault_params_single.get("rake", -90.0))
        # Constrain rake to [-180, 180] for consistent interpretation.
        fault_rake = ((fault_rake + 180.0) % 360.0) - 180.0
        nelements = int(fault_params_single.get("nelements", 1000))
        fault_buffer = float(fault_params_single.get("fault_buffer", 0.5))
        
        # Fault extents must be driven by each fault OBB, not by model boundary size.
        lengths = np_array(lengths, dtype=float)
        base_obb_lengths = np_array(fault_info.get("lengths", lengths), dtype=float)
        fault_points = np_array(fault_info.get("points", []), dtype=float)

        # Per-fault fallback scale from that fault point cloud only.
        point_diag = 0.0
        if fault_points is not None and len(fault_points) > 1:
            point_span = fault_points.max(axis=0) - fault_points.min(axis=0)
            point_diag = float(np_sqrt(np_sum(point_span**2)))

        major_ref = (
            float(base_obb_lengths[0])
            if len(base_obb_lengths) > 0 and base_obb_lengths[0] > 1e-6
            else point_diag
        )
        intermediate_ref = (
            float(base_obb_lengths[1])
            if len(base_obb_lengths) > 1 and base_obb_lengths[1] > 1e-6
            else point_diag * 0.5
        )
        minor_ref = (
            float(base_obb_lengths[2])
            if len(base_obb_lengths) > 2 and base_obb_lengths[2] > 1e-6
            else point_diag * 0.2
        )

        # Last-resort tiny defaults for degenerate inputs.
        major_ref = max(major_ref, 1e-3)
        intermediate_ref = max(intermediate_ref, 1e-3)
        minor_ref = max(minor_ref, 1e-3)

        major_len = float(lengths[0]) if len(lengths) > 0 and lengths[0] > 1e-6 else major_ref
        intermediate_len = (
            float(lengths[1]) if len(lengths) > 1 and lengths[1] > 1e-6 else intermediate_ref
        )
        minor_len = float(lengths[2]) if len(lengths) > 2 and lengths[2] > 1e-6 else minor_ref

        # Keep a minimum extent tied to each fault's own OBB scale.
        major_len = max(major_len, major_ref * 0.1, 1e-3)
        intermediate_len = max(intermediate_len, intermediate_ref * 0.1, 1e-3)
        minor_len = max(minor_len, minor_ref * 0.1, 1e-3)
        
        self.print_terminal(f"    Fault geometry: center={center}")
        self.print_terminal(f"    major={major_len:.2f}, intermediate={intermediate_len:.2f}, minor={minor_len:.2f}")
        
        # IMPORTANT: Convert numpy array to list for LoopStructural compatibility
        # LoopStructural's parameter comparison fails with numpy arrays
        center_list = center.tolist() if hasattr(center, 'tolist') else list(center)
        
        # Get the fault axes from OBB (fallback PCA for degenerate geometries).
        slip_vector_3d, major_axis, intermediate_axis, fault_normal, rake_components = (
            _compute_fault_slip_vector_from_rake(axes, fault_rake)
        )

        # Convert to lists for LoopStructural
        fault_normal_list = (
            fault_normal.tolist() if hasattr(fault_normal, "tolist") else list(fault_normal)
        )
        slip_vector_list = (
            slip_vector_3d.tolist()
            if hasattr(slip_vector_3d, "tolist")
            else list(slip_vector_3d)
        )

        # Log the basis and rake decomposition used for the slip vector.
        self.print_terminal("    Fault axes (OBB/PCA, oriented for rake):")
        self.print_terminal(f"      major (strike): {major_axis}")
        self.print_terminal(f"      intermediate (dip): {intermediate_axis}")
        self.print_terminal(f"      minor (normal): {fault_normal}")
        self.print_terminal(
            f"      rake components (major, intermediate): [{rake_components[0]:.4f}, {rake_components[1]:.4f}]"
        )
        # Rake conventions:
        # - 0 deg = along major axis (strike-slip)
        # - +90 deg = along intermediate axis (reverse)
        # - -90 deg = opposite intermediate axis (normal)
        # - +/-180 deg = opposite major axis (strike-slip)

        # Build fault parameters using LoopStructural's expected argument names.
        # Rake-driven slip vector is always provided from the local fault basis.
        fault_params_ls = {
            "nelements": nelements,
            "interpolatortype": options_dict["method"],
            "fault_buffer": fault_buffer,
            "fault_center": center_list,
            "fault_normal_vector": fault_normal_list,
            "major_axis": major_len,
            "minor_axis": minor_len,
            "intermediate_axis": intermediate_len,
            "fault_slip_vector": slip_vector_list,
            "points": True,
        }
        self.print_terminal(f"    fault_slip_vector (3D): {slip_vector_list}")
        
        self.print_terminal(f"    rake={fault_rake}° (0=sinistral, 90=reverse, -90=normal, ±180=dextral)")
        self.print_terminal(f"    fault_normal_vector: {fault_normal_list}")
        self.print_terminal(f"    Using points=True for fault frame construction")
        
        try:
            # Create the fault with displacement
            model.create_and_add_fault(
                fault_name,
                displacement,
                **fault_params_ls
            )
            
            # Get the created fault feature
            fault_feature = model.get_feature_by_name(fault_name)
            if fault_feature is not None:
                created_fault_features.append(fault_feature)
                created_fault_features_by_name[fault_name] = fault_feature
                self.print_terminal(f"    Fault '{fault_name}' created successfully (type: {fault_feature.type})")
            else:
                self.print_terminal(f"    WARNING: Could not retrieve fault feature '{fault_name}'")
        except Exception as e:
            self.print_terminal(f"    ERROR creating fault '{fault_name}': {e}")
            import traceback
            self.print_terminal(traceback.format_exc())

    # Apply optional fault-fault interactions after all faults are available.
    if created_fault_features_by_name:
        self.print_terminal("-> Applying fault interactions (abutting/splay)...")
        for source_fault_name, params in fault_params_by_name.items():
            source_fault = created_fault_features_by_name.get(source_fault_name)
            if source_fault is None:
                continue

            # Splay relation
            if params.get("has_splay", False):
                target_fault_name = params.get("splay_fault")
                if target_fault_name is None:
                    self.print_terminal(
                        f"  WARNING: Splay enabled for '{source_fault_name}' but no target fault selected."
                    )
                elif target_fault_name == source_fault_name:
                    self.print_terminal(
                        f"  WARNING: Fault '{source_fault_name}' cannot splay with itself."
                    )
                else:
                    target_fault = created_fault_features_by_name.get(target_fault_name)
                    if target_fault is None:
                        self.print_terminal(
                            f"  WARNING: Splay target '{target_fault_name}' not found for '{source_fault_name}'."
                        )
                    else:
                        try:
                            if hasattr(source_fault, "builder") and hasattr(source_fault.builder, "add_splay"):
                                region = source_fault.builder.add_splay(target_fault)
                                if hasattr(source_fault, "splay"):
                                    source_fault.splay[target_fault.name] = region
                                self.print_terminal(
                                    f"  Splay relation applied: '{source_fault_name}' with '{target_fault_name}'."
                                )
                            else:
                                self.print_terminal(
                                    f"  WARNING: Fault '{source_fault_name}' does not expose builder.add_splay()."
                                )
                        except Exception as e:
                            self.print_terminal(
                                f"  ERROR applying splay '{source_fault_name}' -> '{target_fault_name}': {e}"
                            )

            # Abutting relation
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
                            source_fault.add_abutting_fault(target_fault, positive=None)
                            self.print_terminal(
                                f"  Abutting relation applied: '{source_fault_name}' with '{target_fault_name}'."
                            )
                        except Exception as e:
                            self.print_terminal(
                                f"  ERROR applying abutting '{source_fault_name}' -> '{target_fault_name}': {e}"
                            )
    
    toc(parent=self)
    
    # Create foliations AFTER faults (so they can be affected by faults)
    strati_feature_name = "stratigraphy"  # Must match name used in dataframe
    
    if strati_uids:
        self.print_terminal("-> Creating foliations (affected by faults)...")
        tic(parent=self)
        
        try:
            # Pass the fault features list so foliation is displaced by faults
            foliation_faults = created_fault_features if created_fault_features else None
            self.print_terminal(f"  Faults affecting foliation: {[f.name for f in created_fault_features] if created_fault_features else 'None'}")
            
            model.create_and_add_foliation(
                strati_feature_name,  # Use consistent name
                interpolator_type=options_dict["method"],  # NOTE: underscore
                nelements=(dimensions[0] * dimensions[1] * dimensions[2]),
                faults=foliation_faults,
            )
            self.print_terminal(f"  Foliation '{strati_feature_name}' created (affected by faults)")
        except Exception as e:
            self.print_terminal(f"  ERROR creating foliation: {e}")
            import traceback
            self.print_terminal(traceback.format_exc())
        
        toc(parent=self)
    
    # Evaluate and visualize
    self.print_terminal("-> Evaluating model on regular grid...")
    tic(parent=self)
    regular_grid = model.regular_grid(nsteps=dimensions, shuffle=False, rescale=False)
    toc(parent=self)
    
    # Create output Voxet
    self.print_terminal("-> Creating output Voxet...")
    tic(parent=self)
    model_name = "Loop_model_faults"
    
    voxet_dict = deepcopy(self.mesh3d_coll.entity_dict)
    voxet_dict["name"] = model_name
    voxet_dict["topology"] = "Voxet"
    voxet_dict["properties_names"] = []
    voxet_dict["properties_components"] = []
    voxet_dict["vtk_obj"] = Voxet()

    aligned_origin = [
        origin_x + spacing[0] / 2,
        origin_y + spacing[1] / 2,
        origin_z + spacing[2] / 2,
    ]
    if use_obb_alignment:
        from vtk import vtkMatrix3x3

        angle = obb_info["angle"]
        obb_center = obb_info["center"]
        c, s = np_cos(angle), np_sin(angle)

        origin_xy = np_array([aligned_origin[0], aligned_origin[1]])
        R_to_world_2d = np_array([[c, -s], [s, c]])
        origin_world_xy = (R_to_world_2d @ origin_xy) + obb_center
        world_origin = [origin_world_xy[0], origin_world_xy[1], aligned_origin[2]]

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
        voxet_world_origin = world_origin
        self.print_terminal("-> Voxet transformed to OBB orientation")
    else:
        voxet_dict["vtk_obj"].origin = aligned_origin
        voxet_world_origin = None

    voxet_dict["vtk_obj"].dimensions = dimensions
    voxet_dict["vtk_obj"].spacing = spacing
    
    # Log all model features
    self.print_terminal(f"  Model features: {[f.name for f in model.features]}")
    
    # Evaluate each feature and store in voxet
    for feature in model.features:
        self.print_terminal(f"  Evaluating feature: {feature.name} (type: {feature.type})")
        try:
            scalar_field = model.evaluate_feature_value(feature.name, regular_grid, scale=False)
            scalar_field = scalar_field.reshape((dimension_x, dimension_y, dimension_z))
            scalar_field = scalar_field.transpose(2, 1, 0)
            scalar_field = scalar_field.ravel()
            
            voxet_dict["vtk_obj"].set_point_data(
                data_key=feature.name, attribute_matrix=scalar_field
            )
            voxet_dict["properties_names"].append(feature.name)
            voxet_dict["properties_components"].append(1)
            self.print_terminal(f"    Feature '{feature.name}' evaluated successfully")
        except Exception as e:
            self.print_terminal(f"    ERROR evaluating {feature.name}: {e}")
            import traceback
            self.print_terminal(traceback.format_exc())

    # Ask output name at the end of interpolation/evaluation, before writing outputs.
    model_name_input = input_text_dialog(
        title="Implicit Modelling with Faults",
        label="Name of the output Voxet",
        default_text=model_name,
    )
    if model_name_input:
        model_name = model_name_input
    voxet_dict["name"] = model_name
    
    if voxet_dict["vtk_obj"].points_number > 0:
        self.mesh3d_coll.add_entity_from_dict(voxet_dict)
        self.print_terminal(f"  Voxet '{model_name}' created with properties: {voxet_dict['properties_names']}")
    
    toc(parent=self)
    
    # Extract FAULT isosurfaces (at value 0 for the fault feature)
    self.print_terminal("-> Extracting fault surfaces...")
    tic(parent=self)
    
    for fault_name, fault_info in fault_data.items():
        try:
            # Check if the fault feature exists in the voxet
            if fault_name not in voxet_dict["properties_names"]:
                self.print_terminal(f"  WARNING: Fault '{fault_name}' not found in voxet properties")
                continue
            
            voxet_dict["vtk_obj"].GetPointData().SetActiveScalars(fault_name)
            
            iso_surface = vtkContourFilter()
            iso_surface.SetInputData(voxet_dict["vtk_obj"])
            iso_surface.ComputeScalarsOn()
            iso_surface.ComputeGradientsOn()
            iso_surface.SetArrayComponent(0)
            iso_surface.GenerateTrianglesOn()
            iso_surface.UseScalarTreeOn()
            iso_surface.SetValue(0, 0.0)  # Fault surface is at scalar value 0
            iso_surface.Update()
            
            n_points = iso_surface.GetOutput().GetNumberOfPoints()
            self.print_terminal(f"  Fault '{fault_name}' isosurface: {n_points} points")
            
            if n_points > 0:
                surf_dict = deepcopy(self.geol_coll.entity_dict)
                surf_dict["name"] = f"{fault_name}_surface_from_{model_name}"
                surf_dict["topology"] = "TriSurf"
                surf_dict["role"] = "fault"
                surf_dict["feature"] = fault_info["feature"]
                surf_dict["scenario"] = fault_info["scenario"]
                surf_dict["vtk_obj"] = TriSurf()
                surf_dict["vtk_obj"].ShallowCopy(iso_surface.GetOutput())
                if use_obb_alignment:
                    surf_dict["vtk_obj"] = transform_vtk_to_obb(
                        surf_dict["vtk_obj"], obb_info, voxet_world_origin
                    )
                surf_dict["vtk_obj"].Modified()
                
                if isinstance(surf_dict["vtk_obj"].points, np_ndarray) and len(surf_dict["vtk_obj"].points) > 0:
                    self.geol_coll.add_entity_from_dict(surf_dict)
                    self.print_terminal(f"    Fault surface '{fault_name}' extracted ({n_points} points)")
                else:
                    self.print_terminal(f"    WARNING: Fault surface '{fault_name}' is empty after copy")
            else:
                self.print_terminal(f"    WARNING: Fault surface '{fault_name}' has no points")
        except Exception as e:
            self.print_terminal(f"  ERROR extracting fault surface '{fault_name}': {e}")
            import traceback
            self.print_terminal(traceback.format_exc())
    
    toc(parent=self)
    
    # Extract STRATIGRAPHY isosurfaces
    strati_feature_name = "stratigraphy"  # Must match name used above
    
    if strati_uids:
        self.print_terminal("-> Extracting stratigraphy isosurfaces...")
        tic(parent=self)
        
        try:
            # Check if stratigraphy feature exists
            if strati_feature_name not in voxet_dict["properties_names"]:
                self.print_terminal(f"  WARNING: '{strati_feature_name}' not found in voxet properties")
                self.print_terminal(f"  Available properties: {voxet_dict['properties_names']}")
            else:
                voxet_dict["vtk_obj"].GetPointData().SetActiveScalars(strati_feature_name)
                
                # Get unique stratigraphic values (excluding fault data)
                # Filter by feature_name == strati_feature_name to get only stratigraphy values
                strati_values = all_input_data_df.loc[
                    all_input_data_df["feature_name"] == strati_feature_name, "val"
                ].dropna().unique()
                
                self.print_terminal(f"  Stratigraphic values to extract: {strati_values}")
                
                for value in strati_values:
                    value = float(value)
                    self.print_terminal(f"  Extracting iso-surface at value = {value}")
                    
                    # Get metadata from legend
                    legend_match = self.geol_coll.legend_df[self.geol_coll.legend_df["time"] == value]
                    if legend_match.empty:
                        self.print_terminal(f"    WARNING: No legend entry for time={value}")
                        continue
                    
                    role = legend_match["role"].values[0]
                    feature = legend_match["feature"].values[0]
                    scenario = legend_match["scenario"].values[0]
                    
                    iso_surface = vtkContourFilter()
                    iso_surface.SetInputData(voxet_dict["vtk_obj"])
                    iso_surface.ComputeScalarsOn()
                    iso_surface.ComputeGradientsOn()
                    iso_surface.SetArrayComponent(0)
                    iso_surface.GenerateTrianglesOn()
                    iso_surface.UseScalarTreeOn()
                    iso_surface.SetValue(0, value)
                    iso_surface.Update()
                    
                    n_points = iso_surface.GetOutput().GetNumberOfPoints()
                    self.print_terminal(f"    Isosurface at {value}: {n_points} points")
                    
                    if n_points > 0:
                        surf_dict = deepcopy(self.geol_coll.entity_dict)
                        surf_dict["name"] = f"{feature}_from_{model_name}"
                        surf_dict["topology"] = "TriSurf"
                        surf_dict["role"] = role
                        surf_dict["feature"] = feature
                        surf_dict["scenario"] = scenario
                        surf_dict["vtk_obj"] = TriSurf()
                        surf_dict["vtk_obj"].ShallowCopy(iso_surface.GetOutput())
                        if use_obb_alignment:
                            surf_dict["vtk_obj"] = transform_vtk_to_obb(
                                surf_dict["vtk_obj"], obb_info, voxet_world_origin
                            )
                        surf_dict["vtk_obj"].Modified()
                        
                        if isinstance(surf_dict["vtk_obj"].points, np_ndarray) and len(surf_dict["vtk_obj"].points) > 0:
                            self.geol_coll.add_entity_from_dict(surf_dict)
                            self.print_terminal(f"      Iso-surface at value = {value} created ({n_points} points)")
                        else:
                            self.print_terminal(f"      WARNING: Isosurface at {value} is empty after copy")
                    else:
                        self.print_terminal(f"      WARNING: Isosurface at {value} has no points")
                        
        except Exception as e:
            self.print_terminal(f"  ERROR extracting stratigraphy surfaces: {e}")
            import traceback
            self.print_terminal(traceback.format_exc())
        
        toc(parent=self)
    
    voxet_dict["vtk_obj"].Modified()
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
