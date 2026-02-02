"""shp2vtk.py
PZero© Andrea Bistacchi"""

from copy import deepcopy

from geopandas import read_file as gpd_read_file

from numpy import array as np_array
from numpy import asarray as np_asarray
from numpy import atleast_1d as np_atleast_1d
from numpy import column_stack as np_column_stack
from numpy import shape as np_shape
from numpy import zeros as np_zeros

from pandas import Series as pd_series

from vtk import vtkAppendPolyData

from pandas import DataFrame as pd_DataFrame

from pzero.collections.background_collection import BackgroundCollection
from pzero.collections.fluid_collection import FluidCollection
from pzero.collections.geological_collection import GeologicalCollection
from pzero.entities_factory import PolyLine, VertexSet, Attitude
from pzero.helpers.helper_dialogs import ShapefileAssignmentDialog
from pzero.orientation_analysis import dip_directions2normals

# Importer for SHP files and other GIS formats, to be improved IN THE FUTURE.
# Known bugs for multi-part polylines.
# Points not handled correctly.


def shp2vtk(self=None, in_file_name=None, collection=None):
    """Import and add a points and polylines from shape files as VertexSet and PolyLine entities.
    <self> is the calling ProjectWindow() instance."""
    # try:
    # Read shape file into a GeoPandas dataframe. Each row is an
    # entity with geometry stored in the geometry column in shapely format.
    gdf = gpd_read_file(in_file_name)
    # print("geometry type: ", gdf.geom_type[0])
    # print("CRS:\n", gdf.crs)
    # if False in gdf.is_valid[:]:
    #     print("Not valid geometries found - aborting.")
    #     return
    # if True in gdf.is_empty[:]:
    #     print("Empty geometries found - aborting.")
    #     return

    # Determine topology type from geometry
    geom_type = gdf.geom_type[0]
    if geom_type in ["LineString", "MultiLineString"]:
        topology_type = "PolyLine"
    elif geom_type == "Point":
        topology_type = "Point"
    else:
        self.print_terminal(
            f"Only Point and Line geometries can be imported. Found: {geom_type} - aborting."
        )
        return

    # Create DataFrame with attributes (excluding geometry) for the dialog
    attrs_df = pd_DataFrame(gdf.drop(columns="geometry"))

    # include_label only for Background data (original code handled label only there)
    include_label = collection == "Background data"

    # Open dialog to assign shapefile attributes to PZero properties
    dialog = ShapefileAssignmentDialog(
        parent=self,
        shapefile_df=attrs_df,
        topology_type=topology_type,
        include_label=include_label,
    )
    attribute_mapping = dialog.exec()

    # If user cancelled, abort import
    if attribute_mapping is None:
        self.print_terminal("Import cancelled by user.")
        return

    # Split mapping into properties vs orientation-related fields
    # Build maps without mutating original
    props_allowed = {"name", "role", "feature"}
    if include_label:
        props_allowed.add("label")
    # Add scenario for Geology and Fluid collections
    if collection in ["Geology", "Fluid contacts"]:
        props_allowed.add("scenario")
    props_map = {k: v for k, v in attribute_mapping.items() if k in props_allowed}
    if collection in ["Geology", "Fluid contacts"]:
        props_allowed.add("scenario")
    props_map = {k: v for k, v in attribute_mapping.items() if k in props_allowed}
    # Include dip, dip_dir, and dir (dir will be converted to dip_dir with +90° rotation)
    orient_map = {
        k: v for k, v in attribute_mapping.items() if k in {"dip", "dip_dir", "dir"}
    }

    column_names = list(gdf.columns)

    # Use props_map (entity properties) and orient_map (orientation fields) for subsequent processing
    # No additional filtering needed here; include_label already controls presence of 'label'

    if collection == "Geology":
        if (gdf.geom_type[0] == "LineString") or (
            gdf.geom_type[0] == "MultiLineString"
        ):
            for row in range(gdf.shape[0]):
                curr_obj_dict = deepcopy(GeologicalCollection().entity_dict)
                # Use props_map to assign properties
                for pzero_prop, shp_col in props_map.items():
                    if shp_col in column_names:
                        curr_obj_dict[pzero_prop] = gdf.loc[row, shp_col]
                curr_obj_dict["topology"] = "PolyLine"
                curr_obj_dict["vtk_obj"] = PolyLine()
                if gdf.geom_type[row] == "LineString":
                    outXYZ = np_array(list(gdf.loc[row].geometry.coords), dtype=float)
                    if np_shape(outXYZ)[1] == 2:
                        outZ = np_zeros((np_shape(outXYZ)[0], 1))
                        outXYZ = np_column_stack((outXYZ, outZ))
                    curr_obj_dict["vtk_obj"].points = outXYZ
                    curr_obj_dict["vtk_obj"].auto_cells()
                elif gdf.geom_type[row] == "MultiLineString":
                    # to be solved with https://shapely.readthedocs.io/en/stable/migration.html ???
                    outXYZ_list = np_array(gdf.loc[row].geometry)
                    vtkappend = vtkAppendPolyData()
                    for outXYZ in outXYZ_list:
                        temp_vtk = PolyLine()
                        # print("outXYZ:\n", outXYZ)
                        # print("np_shape(outXYZ):\n", np_shape(outXYZ))
                        if np_shape(outXYZ)[1] == 2:
                            outZ = np_zeros((np_shape(outXYZ)[0], 1))
                            # print("outZ:\n", outZ)
                            outXYZ = np_column_stack((outXYZ, outZ))
                        # print("outXYZ:\n", outXYZ)
                        temp_vtk.points = outXYZ
                        temp_vtk.auto_cells()
                        vtkappend.AddInputData(temp_vtk)
                    vtkappend.Update()
                    curr_obj_dict["vtk_obj"].ShallowCopy(vtkappend.GetOutput())
                # Create entity from the dictionary and run left_right.
                if curr_obj_dict["vtk_obj"].points_number > 0:
                    output_uid = self.geol_coll.add_entity_from_dict(curr_obj_dict)
                else:
                    print("Empty object")
                # else:
                # except:
                #     print("Invalid object")
                del curr_obj_dict
        elif gdf.geom_type[0] == "Point":
            feature_col = props_map.get("feature")
            if feature_col and feature_col in column_names:
                gdf_index = gdf.set_index(feature_col)
                feat_list = set(gdf_index.index)
                for i in feat_list:
                    curr_obj_dict = deepcopy(GeologicalCollection().entity_dict)
                    # Check if we have dip data (Attitude)
                    dip_col = orient_map.get("dip")
                    if dip_col and dip_col in gdf.columns:
                        vtk_obj = Attitude()
                    else:
                        vtk_obj = VertexSet()
                    # Assign entity properties
                    for pzero_prop, shp_col in props_map.items():
                        if shp_col in column_names:
                            if pzero_prop == "feature":
                                curr_obj_dict["feature"] = i
                            else:
                                curr_obj_dict[pzero_prop] = pd_series(
                                    gdf_index.loc[i, shp_col]
                                )[0]
                    curr_obj_dict["topology"] = "VertexSet"
                    curr_obj_dict["vtk_obj"] = vtk_obj
                    # Add a coordinate column in the gdf_index dataframe
                    gdf_index["coords"] = gdf_index.geometry.apply(
                        lambda x: np_array(x.coords[0])
                    )
                    outXYZ = np_array([p for p in gdf_index.loc[i, "coords"]])
                    if outXYZ.ndim == 1:
                        outXYZ = outXYZ.reshape(-1, np_shape(outXYZ)[0])
                    if np_shape(outXYZ)[1] == 2:
                        outZ = np_zeros((np_shape(outXYZ)[0], 1))
                        # print("outZ:\n", outZ)
                        outXYZ = np_column_stack((outXYZ, outZ))
                    # print(np_shape(outXYZ))
                    curr_obj_dict["vtk_obj"].points = outXYZ

                    # Handle dip data using mapping
                    dip_col = orient_map.get("dip")
                    if dip_col and dip_col in column_names:
                        # Use pd_series constructor and ensure always array with atleast_1d
                        dip_values = np_atleast_1d(
                            pd_series(gdf_index.loc[i, dip_col]).values
                        )
                        curr_obj_dict["vtk_obj"].set_point_data("dip", dip_values)

                    # Handle dip_dir or dir (dir needs conversion: dir + 90° = dip_dir)
                    has_angle_data = False
                    dir_col = orient_map.get("dir")
                    if dir_col and dir_col in column_names:
                        # Convert dir to dip_dir by adding 90 degrees (as in original)
                        dir_values = pd_series(gdf_index.loc[i, dir_col])
                        direction = (dir_values + 90) % 360
                        curr_obj_dict["vtk_obj"].set_point_data(
                            "dip_dir", np_atleast_1d(direction.values)
                        )
                        has_angle_data = True
                    else:
                        # Try dip_dir directly
                        dip_dir_col = orient_map.get("dip_dir")
                        if dip_dir_col and dip_dir_col in column_names:
                            dip_dir_values = np_atleast_1d(
                                pd_series(gdf_index.loc[i, dip_dir_col]).values
                            )
                            curr_obj_dict["vtk_obj"].set_point_data(
                                "dip_dir", dip_dir_values
                            )
                            has_angle_data = True

                    # Calculate normals if we have both dip and angle data
                    if dip_col and dip_col in column_names and has_angle_data:
                        normals = dip_directions2normals(
                            curr_obj_dict["vtk_obj"].get_point_data("dip"),
                            curr_obj_dict["vtk_obj"].get_point_data("dip_dir"),
                        )
                        curr_obj_dict["vtk_obj"].set_point_data("Normals", normals)
                    # if curr_obj_dict["vtk_obj"].points_number > 1:
                    #     curr_obj_dict["vtk_obj"].auto_cells()
                    #     # print(curr_obj_dict["vtk_obj"].point_data_keys)
                    #     properties_names = curr_obj_dict["vtk_obj"].point_data_keys
                    #     properties_components = [
                    #         curr_obj_dict["vtk_obj"].get_point_data_shape(key)[1]
                    #         for key in properties_names
                    #     ]
                    #     curr_obj_dict["properties_names"] = properties_names
                    #     curr_obj_dict["properties_components"] = properties_components
                    #     self.geol_coll.add_entity_from_dict(curr_obj_dict)
                    #     del curr_obj_dict
                    # elif curr_obj_dict["vtk_obj"].points_number > 0:
                    #     curr_obj_dict["vtk_obj"].auto_cells()
                    #     # print(curr_obj_dict["vtk_obj"].point_data_keys)
                    #     properties_names = curr_obj_dict["vtk_obj"].point_data_keys
                    #     properties_components = [
                    #         curr_obj_dict["vtk_obj"].get_point_data_shape(key)[1]
                    #         for key in properties_names
                    #     ]
                    #     curr_obj_dict["properties_names"] = properties_names
                    #     curr_obj_dict["properties_components"] = properties_components
                    #     self.geol_coll.add_entity_from_dict(curr_obj_dict)
                    #     del curr_obj_dict
                    curr_obj_dict["vtk_obj"].auto_cells()
                    # print(curr_obj_dict["vtk_obj"].point_data_keys)
                    properties_names = curr_obj_dict["vtk_obj"].point_data_keys
                    properties_components = [
                        curr_obj_dict["vtk_obj"].get_point_data_shape(key)[1]
                        for key in properties_names
                    ]
                    curr_obj_dict["properties_names"] = properties_names
                    curr_obj_dict["properties_components"] = properties_components
                    self.geol_coll.add_entity_from_dict(curr_obj_dict)
                    del curr_obj_dict
            else:
                self.print_terminal(
                    "Incomplete data. Feature property is required but not found in mapping."
                )
    elif collection == "Fluid contacts":
        print(gdf.geom_type[0])
        if (gdf.geom_type[0] == "LineString") or (
            gdf.geom_type[0] == "MultiLineString"
        ):
            for row in range(gdf.shape[0]):
                curr_obj_dict = deepcopy(FluidCollection().entity_dict)
                for pzero_prop, shp_col in props_map.items():
                    if shp_col in column_names:
                        curr_obj_dict[pzero_prop] = gdf.loc[row, shp_col]
                curr_obj_dict["topology"] = "PolyLine"
                curr_obj_dict["vtk_obj"] = PolyLine()

                if gdf.geom_type[row] == "LineString":
                    outXYZ = np_array(list(gdf.loc[row].geometry.coords), dtype=float)
                    if np_shape(outXYZ)[1] == 2:
                        outZ = np_zeros((np_shape(outXYZ)[0], 1))
                        # print("outZ:\n", outZ)
                        outXYZ = np_column_stack((outXYZ, outZ))
                    # print("outXYZ:\n", outXYZ)
                    curr_obj_dict["vtk_obj"].points = outXYZ
                    curr_obj_dict["vtk_obj"].auto_cells()
                elif gdf.geom_type[row] == "MultiLineString":
                    outXYZ_list = np_array(gdf.loc[row].geometry)
                    vtkappend = vtkAppendPolyData()
                    for outXYZ in outXYZ_list:
                        temp_vtk = PolyLine()
                        if np_shape(outXYZ)[1] == 2:
                            outZ = np_zeros((np_shape(outXYZ)[0], 1))
                            # print("outZ:\n", outZ)
                            outXYZ = np_column_stack((outXYZ, outZ))
                        # print("outXYZ:\n", outXYZ)
                        temp_vtk.points = outXYZ
                        temp_vtk.auto_cells()
                        vtkappend.AddInputData(temp_vtk)
                    vtkappend.Update()
                    curr_obj_dict["vtk_obj"].ShallowCopy(vtkappend.GetOutput())
                # Create entity from the dictionary and run left_right.
                if curr_obj_dict["vtk_obj"].points_number > 0:
                    output_uid = self.fluid_coll.add_entity_from_dict(curr_obj_dict)
                else:
                    print("Empty object")
                # else:
                # except:
                #     print("Invalid object")
                del curr_obj_dict
        elif gdf.geom_type[0] == "Point":
            feature_col = props_map.get("feature")
            if feature_col and feature_col in column_names:
                gdf_index = gdf.set_index(feature_col)
                feat_list = set(gdf_index.index)
                for i in feat_list:
                    curr_obj_dict = deepcopy(FluidCollection().entity_dict)
                    dip_col = orient_map.get("dip")
                    vtk_obj = (
                        Attitude()
                        if (dip_col and dip_col in gdf.columns)
                        else VertexSet()
                    )
                    for pzero_prop, shp_col in props_map.items():
                        if shp_col in column_names:
                            if pzero_prop == "feature":
                                curr_obj_dict["feature"] = i
                            else:
                                curr_obj_dict[pzero_prop] = pd_series(
                                    gdf_index.loc[i, shp_col]
                                )[0]
                    curr_obj_dict["topology"] = "VertexSet"
                    curr_obj_dict["vtk_obj"] = vtk_obj
                    # Add a coordinate column in the gdf_index dataframe
                    gdf_index["coords"] = gdf_index.geometry.apply(
                        lambda x: np_array(x.coords[0])
                    )
                    outXYZ = np_array([p for p in gdf_index.loc[i, "coords"]])
                    if outXYZ.ndim == 1:
                        outXYZ = outXYZ.reshape(-1, np_shape(outXYZ)[0])
                    if np_shape(outXYZ)[1] == 2:
                        outZ = np_zeros((np_shape(outXYZ)[0], 1))
                        # print("outZ:\n", outZ)
                        outXYZ = np_column_stack((outXYZ, outZ))
                    # print(np_shape(outXYZ))
                    curr_obj_dict["vtk_obj"].points = outXYZ

                    # Handle orientation data for Attitude objects (copied from Geology)
                    if isinstance(vtk_obj, Attitude):
                        # Handle dip data
                        dip_col = orient_map.get("dip")
                        if dip_col and dip_col in column_names:
                            dip_values = np_atleast_1d(
                                pd_series(gdf_index.loc[i, dip_col]).values
                            )
                            curr_obj_dict["vtk_obj"].set_point_data("dip", dip_values)

                        # Handle dip_dir or dir (dir needs conversion: dir + 90° = dip_dir)
                        has_angle_data = False
                        dir_col = orient_map.get("dir")
                        if dir_col and dir_col in column_names:
                            # Convert dir to dip_dir by adding 90 degrees
                            dir_values = pd_series(gdf_index.loc[i, dir_col])
                            direction = (dir_values + 90) % 360
                            curr_obj_dict["vtk_obj"].set_point_data(
                                "dip_dir", np_atleast_1d(direction.values)
                            )
                            has_angle_data = True
                        else:
                            # Try dip_dir directly
                            dip_dir_col = orient_map.get("dip_dir")
                            if dip_dir_col and dip_dir_col in column_names:
                                dip_dir_values = np_atleast_1d(
                                    pd_series(gdf_index.loc[i, dip_dir_col]).values
                                )
                                curr_obj_dict["vtk_obj"].set_point_data(
                                    "dip_dir", dip_dir_values
                                )
                                has_angle_data = True

                        # Calculate normals if we have both dip and angle data
                        if dip_col and dip_col in column_names and has_angle_data:
                            normals = dip_directions2normals(
                                curr_obj_dict["vtk_obj"].get_point_data("dip"),
                                curr_obj_dict["vtk_obj"].get_point_data("dip_dir"),
                            )
                            curr_obj_dict["vtk_obj"].set_point_data("Normals", normals)

                    if curr_obj_dict["vtk_obj"].points_number > 1:
                        curr_obj_dict["vtk_obj"].auto_cells()
                        # print(curr_obj_dict["vtk_obj"].point_data_keys)
                        properties_names = curr_obj_dict["vtk_obj"].point_data_keys
                        properties_components = [
                            curr_obj_dict["vtk_obj"].get_point_data_shape(key)[1]
                            for key in properties_names
                        ]
                        curr_obj_dict["properties_names"] = properties_names
                        curr_obj_dict["properties_components"] = properties_components
                        self.fluid_coll.add_entity_from_dict(curr_obj_dict)
                        del curr_obj_dict
                    elif curr_obj_dict["vtk_obj"].points_number > 0:
                        curr_obj_dict["vtk_obj"].auto_cells()
                        # print(curr_obj_dict["vtk_obj"].point_data_keys)
                        properties_names = curr_obj_dict["vtk_obj"].point_data_keys
                        properties_components = [
                            curr_obj_dict["vtk_obj"].get_point_data_shape(key)[1]
                            for key in properties_names
                        ]
                        curr_obj_dict["properties_names"] = properties_names
                        curr_obj_dict["properties_components"] = properties_components
                        self.fluid_coll.add_entity_from_dict(curr_obj_dict)
                        del curr_obj_dict
            else:
                self.print_terminal(
                    "Incomplete data. Feature property is required but not found in mapping."
                )
    elif collection == "Background data":
        if (gdf.geom_type[0] == "LineString") or (
            gdf.geom_type[0] == "MultiLineString"
        ):
            for row in range(gdf.shape[0]):
                curr_obj_dict = deepcopy(BackgroundCollection().entity_dict)
                for pzero_prop, shp_col in props_map.items():
                    if shp_col in column_names:
                        curr_obj_dict[pzero_prop] = gdf.loc[row, shp_col]
                curr_obj_dict["topology"] = "PolyLine"
                curr_obj_dict["vtk_obj"] = PolyLine()
                if gdf.geom_type[row] == "LineString":
                    outXYZ = np_array(list(gdf.loc[row].geometry.coords), dtype=float)
                    # print("outXYZ:\n", outXYZ)
                    if np_shape(outXYZ)[1] == 2:
                        outZ = np_zeros((np_shape(outXYZ)[0], 1))
                        # print("outZ:\n", outZ)
                        outXYZ = np_column_stack((outXYZ, outZ))
                    # print("outXYZ:\n", outXYZ)
                    curr_obj_dict["vtk_obj"].points = outXYZ
                    curr_obj_dict["vtk_obj"].auto_cells()
                    # Handle label field if present in mapping
                    label_col = props_map.get("label")
                    if label_col and label_col in column_names:
                        curr_obj_dict["vtk_obj"].set_field_data(
                            name="name", data=gdf[label_col].values
                        )
                elif gdf.geom_type[row] == "MultiLineString":
                    outXYZ_list = np_array(gdf.loc[row].geometry)
                    vtkappend = vtkAppendPolyData()
                    for outXYZ in outXYZ_list:
                        temp_vtk = PolyLine()
                        # print("outXYZ:\n", outXYZ)
                        # print("np_shape(outXYZ):\n", np_shape(outXYZ))
                        if np_shape(outXYZ)[1] == 2:
                            outZ = np_zeros((np_shape(outXYZ)[0], 1))
                            # print("outZ:\n", outZ)
                            outXYZ = np_column_stack((outXYZ, outZ))
                        # print("outXYZ:\n", outXYZ)
                        temp_vtk.points = outXYZ
                        temp_vtk.auto_cells()
                        vtkappend.AddInputData(temp_vtk)
                    vtkappend.Update()
                    # Handle label field if present in mapping
                    label_col = props_map.get("label")
                    if label_col and label_col in column_names:
                        out_vtk = PolyLine()
                        out_vtk.ShallowCopy(vtkappend.GetOutput())
                        out_vtk.set_field_data(name="name", data=gdf[label_col].values)
                        curr_obj_dict["vtk_obj"].ShallowCopy(out_vtk)
                    else:
                        curr_obj_dict["vtk_obj"].ShallowCopy(vtkappend.GetOutput())

                if curr_obj_dict["vtk_obj"].points_number > 0:
                    self.backgrnd_coll.add_entity_from_dict(curr_obj_dict)
                else:
                    self.print_terminal("Empty object")
                del curr_obj_dict
            # Points
        elif gdf.geom_type[0] == "Point":
            feature_col = props_map.get("feature")
            if feature_col and feature_col in column_names:
                gdf_index = gdf.set_index(feature_col)
                feat_list = set(gdf_index.index)
                for i in feat_list:
                    curr_obj_dict = deepcopy(BackgroundCollection().entity_dict)
                    vtk_obj = VertexSet()
                    for pzero_prop, shp_col in props_map.items():
                        if shp_col in column_names:
                            if pzero_prop == "feature":
                                curr_obj_dict["feature"] = i
                            else:
                                curr_obj_dict[pzero_prop] = pd_series(
                                    gdf_index.loc[i, shp_col]
                                )[0]
                    curr_obj_dict["topology"] = "VertexSet"
                    curr_obj_dict["vtk_obj"] = vtk_obj
                    # Add a coordinate column in the gdf_index dataframe
                    gdf_index["coords"] = gdf_index.geometry.apply(
                        lambda x: np_array(x.coords[0])
                    )
                    outXYZ = np_array([p for p in gdf_index.loc[i, "coords"]])
                    if outXYZ.ndim == 1:
                        outXYZ = outXYZ.reshape(-1, np_shape(outXYZ)[0])
                    if np_shape(outXYZ)[1] == 2:
                        outZ = np_zeros((np_shape(outXYZ)[0], 1))
                        # print("outZ:\n", outZ)
                        outXYZ = np_column_stack((outXYZ, outZ))
                    curr_obj_dict["vtk_obj"].points = outXYZ
                    curr_obj_dict["vtk_obj"].auto_cells()
                    # Handle label field if present in mapping
                    label_col = props_map.get("label")
                    if label_col and label_col in column_names:
                        curr_obj_dict["vtk_obj"].set_field_data(
                            name="name", data=np_asarray(gdf_index.loc[i, label_col])
                        )
                    else:
                        curr_obj_dict["vtk_obj"].set_field_data(name="name")

                    if curr_obj_dict["vtk_obj"].points_number > 0:
                        self.backgrnd_coll.add_entity_from_dict(curr_obj_dict)
                    del curr_obj_dict
            else:
                self.print_terminal(
                    "Incomplete data. Feature property is required but not found in mapping."
                )
