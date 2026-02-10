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

from vtk import vtkAppendPolyData

from pandas import DataFrame as pd_DataFrame

from pzero.collections.background_collection import BackgroundCollection
from pzero.collections.fluid_collection import FluidCollection
from pzero.collections.geological_collection import GeologicalCollection
from pzero.entities_factory import PolyLine, VertexSet, Attitude
from pzero.helpers.helper_dialogs import ShapefileAssignmentDialog, options_dialog
from pzero.orientation_analysis import dip_directions2normals

USER_DEFINED_FEATURE_TOKEN = "__user_defined_feature__"
USER_DEFINED_FEATURE_COLUMN = "__pzero_user_defined_feature__"
FIXED_ROLE_TOKEN = "__fixed_role__"
FIXED_ROLE_COLUMN = "__pzero_fixed_role__"
USER_DEFINED_NAME_TOKEN = "__user_defined_name__"
USER_DEFINED_NAME_COLUMN = "__pzero_user_defined_name__"
USER_DEFINED_SCENARIO_TOKEN = "__user_defined_scenario__"
USER_DEFINED_SCENARIO_COLUMN = "__pzero_user_defined_scenario__"

# Importer for SHP files and other GIS formats, to be improved IN THE FUTURE.
# Known bugs for multi-part polylines.
# Points not handled correctly.


def _get_valid_roles_for_collection(collection):
    """Return the list of valid roles for a given collection type string."""
    if collection == "Geology":
        return GeologicalCollection().valid_roles
    elif collection == "Fluid contacts":
        return FluidCollection().valid_roles
    elif collection == "Background data":
        return BackgroundCollection().valid_roles
    return ["undef"]


def _get_point_group_columns(props_map, column_names):
    """Return the list of shapefile column names used to group Point rows into entities.

    Points are grouped by the combination of (feature, role, scenario) when those
    columns are mapped.  At minimum, feature must be present.

    Returns
    -------
    list[str]
        Column names in gdf that define the grouping, ordered as
        [feature, role, scenario] (only those that are mapped and present).
    """
    group_cols = []
    for prop in ("feature", "role", "scenario"):
        col = props_map.get(prop)
        if col and col in column_names:
            group_cols.append(col)
    return group_cols


def _count_entities(gdf, geom_type, props_map, column_names):
    """Count the number of entities that will be created from the GeoDataFrame.

    For LineString/MultiLineString: 1 entity per row.
    For Point: 1 entity per unique (feature, role, scenario) combination.
    """
    if geom_type in ("LineString", "MultiLineString"):
        return gdf.shape[0]
    elif geom_type == "Point":
        group_cols = _get_point_group_columns(props_map, column_names)
        if group_cols:
            return len(gdf.groupby(group_cols))
    return 0


def _validate_and_fix_roles(gdf, geom_type, props_map, column_names, valid_roles):
    """Validate role values in the GeoDataFrame and replace invalid ones with 'undef'.

    Modifies gdf in-place.  For Point geometries, entities are grouped by
    (feature, role, scenario) so each group has a uniform role.  We count
    the number of *groups* whose role is invalid, replace it with 'undef',
    and then recompute the total (which may change because formerly-distinct
    groups can merge after replacement).

    Returns
    -------
    tuple[int, int]
        (total_entity_count, invalid_role_count)  where total_entity_count
        is computed *after* replacement.
    """
    role_col = props_map.get("role")
    if not role_col or role_col not in column_names:
        total = _count_entities(gdf, geom_type, props_map, column_names)
        return total, 0

    # Identify invalid role rows BEFORE replacement
    invalid_mask = ~gdf[role_col].isin(valid_roles)

    if geom_type in ("LineString", "MultiLineString"):
        invalid_entity_count = int(invalid_mask.sum())
    elif geom_type == "Point":
        group_cols = _get_point_group_columns(props_map, column_names)
        if group_cols:
            # Each group has uniform role (role is a grouping column).
            # Count groups whose role is not in valid_roles.
            group_roles = gdf.groupby(group_cols)[role_col].first()
            invalid_entity_count = int((~group_roles.isin(valid_roles)).sum())
        else:
            invalid_entity_count = 0
    else:
        invalid_entity_count = 0

    # Replace ALL invalid role values in-place
    if invalid_mask.any():
        gdf.loc[invalid_mask, role_col] = "undef"

    # Recompute total AFTER replacement (groups may merge when role → 'undef')
    total = _count_entities(gdf, geom_type, props_map, column_names)

    return total, invalid_entity_count


def _print_import_summary(caller, imported_count, total_entities, invalid_role_count):
    """Print a terminal summary message after shapefile import."""
    msg = f"Shapefile import complete: {imported_count}/{total_entities} entities imported"
    if invalid_role_count > 0:
        msg += f" ({invalid_role_count} had invalid roles set to 'undef')"
    caller.print_terminal(msg + ".")


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

    # Get valid_roles for all collections
    valid_roles = None
    if collection == "Geology":
        valid_roles = GeologicalCollection().valid_roles
    elif collection == "Fluid contacts":
        valid_roles = FluidCollection().valid_roles
    elif collection == "Background data":
        valid_roles = BackgroundCollection().valid_roles

    # Open dialog to assign shapefile attributes to PZero properties
    dialog = ShapefileAssignmentDialog(
        parent=self,
        shapefile_df=attrs_df,
        topology_type=topology_type,
        include_label=include_label,
        valid_roles=valid_roles,
    )
    attribute_mapping = dialog.exec()

    # If user cancelled, abort import
    if attribute_mapping is None:
        self.print_terminal("Import cancelled by user.")
        return

    # Support an explicit user-defined feature value for all imported objects.
    if attribute_mapping.get("feature") == USER_DEFINED_FEATURE_TOKEN:
        user_feature_value = str(
            attribute_mapping.get("feature_user_value", "undef")
        ).strip()
        if not user_feature_value:
            user_feature_value = "undef"
        feature_col_name = USER_DEFINED_FEATURE_COLUMN
        while feature_col_name in gdf.columns:
            feature_col_name = f"_{feature_col_name}"
        gdf[feature_col_name] = user_feature_value
        attribute_mapping["feature"] = feature_col_name

    # Support a fixed role value for all imported objects.
    if attribute_mapping.get("role") == FIXED_ROLE_TOKEN:
        fixed_role_value = str(attribute_mapping.get("role_fixed_value", "undef")).strip()
        if not fixed_role_value:
            fixed_role_value = "undef"
        role_col_name = FIXED_ROLE_COLUMN
        while role_col_name in gdf.columns:
            role_col_name = f"_{role_col_name}"
        gdf[role_col_name] = fixed_role_value
        attribute_mapping["role"] = role_col_name

    # Support a user-defined name value for all imported objects.
    if attribute_mapping.get("name") == USER_DEFINED_NAME_TOKEN:
        user_name_value = str(attribute_mapping.get("name_user_value", "")).strip()
        if not user_name_value:
            user_name_value = "undef"
        name_col_name = USER_DEFINED_NAME_COLUMN
        while name_col_name in gdf.columns:
            name_col_name = f"_{name_col_name}"
        gdf[name_col_name] = user_name_value
        attribute_mapping["name"] = name_col_name

    # Support a user-defined scenario value for all imported objects.
    if attribute_mapping.get("scenario") == USER_DEFINED_SCENARIO_TOKEN:
        user_scenario_value = str(attribute_mapping.get("scenario_user_value", "")).strip()
        if not user_scenario_value:
            user_scenario_value = "undef"
        scenario_col_name = USER_DEFINED_SCENARIO_COLUMN
        while scenario_col_name in gdf.columns:
            scenario_col_name = f"_{scenario_col_name}"
        gdf[scenario_col_name] = user_scenario_value
        attribute_mapping["scenario"] = scenario_col_name

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

    # --- Role Validation ---
    valid_roles = _get_valid_roles_for_collection(collection)
    total_entities, invalid_role_count = _validate_and_fix_roles(
        gdf, geom_type, props_map, column_names, valid_roles
    )

    if invalid_role_count > 0:
        user_choice = options_dialog(
            title="Invalid roles found",
            message=(
                f"{invalid_role_count} entities out of {total_entities} "
                f"have been assigned role 'undef' (invalid role for {collection}).\n"
                f"Continue with import or Cancel?"
            ),
            yes_role="Continue",
            no_role="Cancel",
        )
        if user_choice != 0:
            self.print_terminal(
                f"Import cancelled: {invalid_role_count}/{total_entities} entities "
                f"had invalid roles."
            )
            return

    if collection == "Geology":
        if (gdf.geom_type[0] == "LineString") or (
            gdf.geom_type[0] == "MultiLineString"
        ):
            imported_count = 0
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
                    imported_count += 1
                else:
                    print("Empty object")
                # else:
                # except:
                #     print("Invalid object")
                del curr_obj_dict
            _print_import_summary(self, imported_count, total_entities, invalid_role_count)
        elif gdf.geom_type[0] == "Point":
            feature_col = props_map.get("feature")
            group_cols = _get_point_group_columns(props_map, column_names)
            if feature_col and feature_col in column_names and group_cols:
                imported_count = 0
                for _group_key, group_df in gdf.groupby(group_cols):
                    curr_obj_dict = deepcopy(GeologicalCollection().entity_dict)
                    # Check if we have dip data (Attitude)
                    dip_col = orient_map.get("dip")
                    if dip_col and dip_col in gdf.columns:
                        vtk_obj = Attitude()
                    else:
                        vtk_obj = VertexSet()
                    # Assign entity properties from the first row of the group
                    for pzero_prop, shp_col in props_map.items():
                        if shp_col in column_names:
                            curr_obj_dict[pzero_prop] = group_df.iloc[0][shp_col]
                    curr_obj_dict["topology"] = "VertexSet"
                    curr_obj_dict["vtk_obj"] = vtk_obj
                    # Extract coordinates from all points in the group
                    outXYZ = np_array(
                        [np_array(geom.coords[0]) for geom in group_df.geometry]
                    )
                    if outXYZ.ndim == 1:
                        outXYZ = outXYZ.reshape(-1, np_shape(outXYZ)[0])
                    if np_shape(outXYZ)[1] == 2:
                        outZ = np_zeros((np_shape(outXYZ)[0], 1))
                        outXYZ = np_column_stack((outXYZ, outZ))
                    curr_obj_dict["vtk_obj"].points = outXYZ

                    # Handle dip data using mapping
                    dip_col = orient_map.get("dip")
                    if dip_col and dip_col in column_names:
                        dip_values = np_atleast_1d(group_df[dip_col].values)
                        curr_obj_dict["vtk_obj"].set_point_data("dip", dip_values)

                    # Handle dip_dir or dir (dir needs conversion: dir + 90° = dip_dir)
                    has_angle_data = False
                    dir_col = orient_map.get("dir")
                    if dir_col and dir_col in column_names:
                        # Convert dir to dip_dir by adding 90 degrees (as in original)
                        direction = (group_df[dir_col].values + 90) % 360
                        curr_obj_dict["vtk_obj"].set_point_data(
                            "dip_dir", np_atleast_1d(direction)
                        )
                        has_angle_data = True
                    else:
                        # Try dip_dir directly
                        dip_dir_col = orient_map.get("dip_dir")
                        if dip_dir_col and dip_dir_col in column_names:
                            dip_dir_values = np_atleast_1d(group_df[dip_dir_col].values)
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
                    curr_obj_dict["vtk_obj"].auto_cells()
                    properties_names = curr_obj_dict["vtk_obj"].point_data_keys
                    properties_components = [
                        curr_obj_dict["vtk_obj"].get_point_data_shape(key)[1]
                        for key in properties_names
                    ]
                    curr_obj_dict["properties_names"] = properties_names
                    curr_obj_dict["properties_components"] = properties_components
                    self.geol_coll.add_entity_from_dict(curr_obj_dict)
                    imported_count += 1
                    del curr_obj_dict
                _print_import_summary(self, imported_count, total_entities, invalid_role_count)
            else:
                self.print_terminal(
                    "Incomplete data. Feature property is required but not found in mapping."
                )
    elif collection == "Fluid contacts":
        print(gdf.geom_type[0])
        if (gdf.geom_type[0] == "LineString") or (
            gdf.geom_type[0] == "MultiLineString"
        ):
            imported_count = 0
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
                    imported_count += 1
                else:
                    print("Empty object")
                # else:
                # except:
                #     print("Invalid object")
                del curr_obj_dict
            _print_import_summary(self, imported_count, total_entities, invalid_role_count)
        elif gdf.geom_type[0] == "Point":
            feature_col = props_map.get("feature")
            group_cols = _get_point_group_columns(props_map, column_names)
            if feature_col and feature_col in column_names and group_cols:
                imported_count = 0
                for _group_key, group_df in gdf.groupby(group_cols):
                    curr_obj_dict = deepcopy(FluidCollection().entity_dict)
                    dip_col = orient_map.get("dip")
                    vtk_obj = (
                        Attitude()
                        if (dip_col and dip_col in gdf.columns)
                        else VertexSet()
                    )
                    # Assign entity properties from the first row of the group
                    for pzero_prop, shp_col in props_map.items():
                        if shp_col in column_names:
                            curr_obj_dict[pzero_prop] = group_df.iloc[0][shp_col]
                    curr_obj_dict["topology"] = "VertexSet"
                    curr_obj_dict["vtk_obj"] = vtk_obj
                    # Extract coordinates from all points in the group
                    outXYZ = np_array(
                        [np_array(geom.coords[0]) for geom in group_df.geometry]
                    )
                    if outXYZ.ndim == 1:
                        outXYZ = outXYZ.reshape(-1, np_shape(outXYZ)[0])
                    if np_shape(outXYZ)[1] == 2:
                        outZ = np_zeros((np_shape(outXYZ)[0], 1))
                        outXYZ = np_column_stack((outXYZ, outZ))
                    curr_obj_dict["vtk_obj"].points = outXYZ

                    # Handle orientation data for Attitude objects
                    if isinstance(vtk_obj, Attitude):
                        # Handle dip data
                        dip_col = orient_map.get("dip")
                        if dip_col and dip_col in column_names:
                            dip_values = np_atleast_1d(group_df[dip_col].values)
                            curr_obj_dict["vtk_obj"].set_point_data("dip", dip_values)

                        # Handle dip_dir or dir (dir needs conversion: dir + 90° = dip_dir)
                        has_angle_data = False
                        dir_col = orient_map.get("dir")
                        if dir_col and dir_col in column_names:
                            # Convert dir to dip_dir by adding 90 degrees
                            direction = (group_df[dir_col].values + 90) % 360
                            curr_obj_dict["vtk_obj"].set_point_data(
                                "dip_dir", np_atleast_1d(direction)
                            )
                            has_angle_data = True
                        else:
                            # Try dip_dir directly
                            dip_dir_col = orient_map.get("dip_dir")
                            if dip_dir_col and dip_dir_col in column_names:
                                dip_dir_values = np_atleast_1d(
                                    group_df[dip_dir_col].values
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

                    curr_obj_dict["vtk_obj"].auto_cells()
                    properties_names = curr_obj_dict["vtk_obj"].point_data_keys
                    properties_components = [
                        curr_obj_dict["vtk_obj"].get_point_data_shape(key)[1]
                        for key in properties_names
                    ]
                    curr_obj_dict["properties_names"] = properties_names
                    curr_obj_dict["properties_components"] = properties_components
                    self.fluid_coll.add_entity_from_dict(curr_obj_dict)
                    imported_count += 1
                    del curr_obj_dict
                _print_import_summary(self, imported_count, total_entities, invalid_role_count)
            else:
                self.print_terminal(
                    "Incomplete data. Feature property is required but not found in mapping."
                )
    elif collection == "Background data":
        if (gdf.geom_type[0] == "LineString") or (
            gdf.geom_type[0] == "MultiLineString"
        ):
            imported_count = 0
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
                    imported_count += 1
                else:
                    self.print_terminal("Empty object")
                del curr_obj_dict
            _print_import_summary(self, imported_count, total_entities, invalid_role_count)
            # Points
        elif gdf.geom_type[0] == "Point":
            feature_col = props_map.get("feature")
            group_cols = _get_point_group_columns(props_map, column_names)
            if feature_col and feature_col in column_names and group_cols:
                imported_count = 0
                for _group_key, group_df in gdf.groupby(group_cols):
                    curr_obj_dict = deepcopy(BackgroundCollection().entity_dict)
                    vtk_obj = VertexSet()
                    # Assign entity properties from the first row of the group
                    for pzero_prop, shp_col in props_map.items():
                        if shp_col in column_names:
                            curr_obj_dict[pzero_prop] = group_df.iloc[0][shp_col]
                    curr_obj_dict["topology"] = "VertexSet"
                    curr_obj_dict["vtk_obj"] = vtk_obj
                    # Extract coordinates from all points in the group
                    outXYZ = np_array(
                        [np_array(geom.coords[0]) for geom in group_df.geometry]
                    )
                    if outXYZ.ndim == 1:
                        outXYZ = outXYZ.reshape(-1, np_shape(outXYZ)[0])
                    if np_shape(outXYZ)[1] == 2:
                        outZ = np_zeros((np_shape(outXYZ)[0], 1))
                        outXYZ = np_column_stack((outXYZ, outZ))
                    curr_obj_dict["vtk_obj"].points = outXYZ
                    curr_obj_dict["vtk_obj"].auto_cells()
                    # Handle label field if present in mapping
                    label_col = props_map.get("label")
                    if label_col and label_col in column_names:
                        curr_obj_dict["vtk_obj"].set_field_data(
                            name="name", data=np_asarray(group_df[label_col].values)
                        )
                    else:
                        curr_obj_dict["vtk_obj"].set_field_data(name="name")

                    if curr_obj_dict["vtk_obj"].points_number > 0:
                        self.backgrnd_coll.add_entity_from_dict(curr_obj_dict)
                        imported_count += 1
                    del curr_obj_dict
                _print_import_summary(self, imported_count, total_entities, invalid_role_count)
            else:
                self.print_terminal(
                    "Incomplete data. Feature property is required but not found in mapping."
                )
