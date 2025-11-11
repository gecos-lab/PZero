"""pc2vtk.py by Gabriele Benedetti
PZero© Andrea Bistacchi"""

from os import path as os_path

from uuid import uuid4

from laspy import read as lp_read
from numpy import array as np_array
from numpy import c_ as np_c_
from numpy import column_stack as np_column_stack
from numpy import shape as np_shape
from numpy import uint8 as np_uint8
from numpy import where as np_where
from pandas import DataFrame as pd_DataFrame
from pandas import read_csv as pd_read_csv
from pandas import to_numeric as pd_to_numeric
from re import sub as re_sub

from vtk import vtkPoints
from vtkmodules.util.numpy_support import numpy_to_vtk
from pzero.collections.dom_collection import DomCollection
from pzero.entities_factory import PCDom


COORDINATE_ALIASES = {
    "X": (
        "easting",
        "east",
        "longitude",
        "lon",
        "utm_e",
        "utme",
        "coordx",
        "xcoord",
        "xcoordinate",
    ),
    "Y": (
        "northing",
        "north",
        "latitude",
        "lat",
        "utm_n",
        "utmn",
        "coordy",
        "ycoord",
        "ycoordinate",
    ),
    "Z": (
        "elevation",
        "height",
        "altitude",
        "depth",
        "coordz",
        "zcoord",
        "zcoordinate",
    ),
}


def _sanitize_column_name(column_name: str) -> str:
    """Sanitize a column name by stripping non-alphanumeric characters."""
    return re_sub(r"[^a-z0-9]", "", column_name.lower())


def _match_coordinate_column(available_columns, axis: str) -> str | None:
    """
    Try to find a column corresponding to the requested axis.

    It matches exact aliases after stripping non-alphanumeric characters.
    """
    search_terms = (axis,) + COORDINATE_ALIASES.get(axis, tuple())
    sanitized_columns = {
        col_name: _sanitize_column_name(col_name) for col_name in available_columns
    }
    for term in search_terms:
        sanitized_term = _sanitize_column_name(term)
        for column_name, sanitized_column in sanitized_columns.items():
            if sanitized_column == sanitized_term:
                return column_name
    return None


def _normalise_coordinate_columns(input_df: pd_DataFrame) -> tuple[list[str], dict]:
    """Rename coordinate columns to the canonical X, Y, Z labels when possible."""
    rename_map = {}
    remaining_columns = list(input_df.columns)

    for axis in ("X", "Y", "Z"):
        if axis in input_df.columns:
            if axis in remaining_columns:
                remaining_columns.remove(axis)
            continue
        matched_column = _match_coordinate_column(remaining_columns, axis)
        if matched_column:
            rename_map[matched_column] = axis
            remaining_columns.remove(matched_column)

    if rename_map:
        input_df.rename(columns=rename_map, inplace=True)

    missing_axes = [axis for axis in ("X", "Y", "Z") if axis not in input_df.columns]
    return missing_axes, rename_map


def pc2vtk(
    in_file_name, col_names, row_range, header_row, usecols, delimiter, self=None
):
    self.parent.print_terminal("Reading and importing file")

    basename = os_path.basename(in_file_name)
    _, ext = os_path.splitext(basename)

    point_cloud = PCDom()  #  vtkPointSet object
    points = vtkPoints()

    skip_range = range(1, row_range.start)
    if skip_range:
        skiprows = skip_range.stop - skip_range.start
    else:
        skiprows = header_row + 1

    if row_range:
        nrows = row_range.stop - row_range.start
    else:
        nrows = None

    #  Read in different ways depending on the input file type
    if ext == ".ply":
        with open(in_file_name, "r") as f:
            for i, line in enumerate(f):
                if "end_header" in line:
                    index = i
                    break
        input_df = pd_read_csv(
            in_file_name,
            skiprows=index + 1 + skiprows,
            usecols=usecols,
            delimiter=delimiter,
            names=col_names,
            index_col=False,
            nrows=nrows,
        )

    elif ext == ".las" or ext == ".laz":
        las_data = lp_read(in_file_name)
        dim_names = las_data.point_format.dimension_names
        prop_dict = dict()
        for dim in dim_names:
            if dim == "X" or dim == "Y" or dim == "Z":
                attr = dim.lower()
                prop_dict[attr] = np_c_[las_data[attr]].flatten()
            else:
                prop_dict[dim] = np_c_[las_data[dim]].flatten()
        if row_range:
            input_df = pd_DataFrame.from_dict(prop_dict).iloc[row_range, usecols]
        else:
            input_df = pd_DataFrame.from_dict(prop_dict).iloc[:, usecols]
        input_df.columns = col_names

    else:
        input_df = pd_read_csv(
            in_file_name,
            delimiter=delimiter,
            usecols=usecols,
            skiprows=skiprows,
            nrows=nrows,
            names=col_names,
        )

    self.parent.print_terminal("Checking the data")

    #  Check if in the whole dataset there are NaNs text and such
    val_check = input_df.apply(
        lambda c: pd_to_numeric(c, errors="coerce").notnull().all()
    )

    if not val_check.all():
        self.parent.print_terminal("Invalid values in data set, not importing.")
    else:
        self.parent.print_terminal("Creating PointCloud")

        # Correcting input data by subtracting an equal value approximated to the hundreds (53932.4325 -> 53932.4325 - 53900.0000 = 32.4325). Can be always applied since for numbers < 100 the approximation is always 0.
        print("input_df shape:", input_df.shape)
        if input_df.empty:
            self.parent.print_terminal("Empty dataframe")

        missing_axes, renamed_axes = _normalise_coordinate_columns(input_df)
        if renamed_axes:
            rename_summary = ", ".join(
                f"{source}->{target}" for source, target in renamed_axes.items()
            )
            self.parent.print_terminal(
                f"Detected coordinate columns: {rename_summary}"
            )
        if missing_axes:
            missing_summary = ", ".join(missing_axes)
            self.parent.print_terminal(
                f"Missing coordinate columns ({missing_summary}). "
                "Please assign them in the import dialog."
            )
            return

        offset = input_df[["X", "Y"]].iloc[0].round(-2)

        input_df["X"] -= offset["X"]
        input_df["Y"] -= offset["Y"]

        XYZ = numpy_to_vtk(
            np_column_stack(
                (input_df["X"].values, input_df["Y"].values, input_df["Z"].values)
            )
        )

        #  Create pyvista PolyData using XYZ data
        points.SetData(XYZ)
        point_cloud.SetPoints(points)
        point_cloud.Modified()
        point_cloud.generate_cells()

        # pv_PD = PointSet(XYZ)
        # Set properties (exclude XYZ data) and add properties names and components in the appropriate lists (properties_names and properties_components).
        input_df.drop(["X", "Y", "Z"], axis=1, inplace=True)

        if not input_df.empty:
            if "Red" in input_df.columns:
                point_cloud.init_point_data("RGB", 3)
                # print(properties_df)
                if self.check255Box.isChecked():
                    RGB = np_array(
                        [input_df["Red"], input_df["Green"], input_df["Blue"]]
                    ).T.astype(np_uint8)
                else:
                    RGB = np_array(
                        [input_df["Red"], input_df["Green"], input_df["Blue"]]
                    ).T

                point_cloud.set_point_data("RGB", RGB)

                input_df.drop(["Red", "Green", "Blue"], axis=1, inplace=True)

            if "Nx" in input_df.columns:
                point_cloud.init_point_data("Normals", 3)
                normals = np_array([input_df["Nx"], input_df["Ny"], input_df["Nz"]]).T

                normals_flipped = np_where(normals[:, 2:] > 0, normals * -1, normals)
                point_cloud.set_point_data("Normals", normals_flipped)

                input_df.drop(["Nx", "Ny", "Nz"], axis=1, inplace=True)

            for property in input_df.columns:
                n_components = np_shape(input_df[property].values)
                if len(n_components):
                    n_components = 1
                else:
                    n_components = n_components[1]
                point_cloud.init_point_data(property, n_components)

                point_cloud.set_point_data(property, input_df[property].values)
                # point_cloud.set_point_data(property,properties_value)

        self.parent.print_terminal("Adding PC to project")
        # point_cloud.ShallowCopy(pv_PD)
        point_cloud.Modified()
        properties_names = point_cloud.point_data_keys
        properties_components = [
            point_cloud.get_point_data_shape(i)[1] for i in properties_names
        ]
        properties_types = [
            point_cloud.get_point_data_type(i) for i in properties_names
        ]

        # point_cloud.generate_point_set()

        # # Create dictionary.
        # curr_obj_attributes = deepcopy(DomCollection.entity_dict)
        # curr_obj_attributes["uid"] = str(uuid4())
        # point_cloud.Modified()
        # curr_obj_attributes["name"] = basename
        # curr_obj_attributes["topology"] = "PCDom"
        # curr_obj_attributes["textures"] = []
        # curr_obj_attributes["properties_names"] = properties_names
        # curr_obj_attributes["properties_components"] = properties_components
        # curr_obj_attributes["properties_types"] = properties_types
        # curr_obj_attributes["vtk_obj"] = point_cloud

        curr_obj_attributes = {
            "uid": str(uuid4()),
            "name": os_path.basename(in_file_name),
            "topology": "PCDom",
            "textures": [],
            "properties_names": properties_names,
            "properties_components": properties_components,
            "properties_types": properties_types,
            "vtk_obj": point_cloud,
        }
        # Add to entity collection.
        self.parent.dom_coll.add_entity_from_dict(entity_dict=curr_obj_attributes)
        # Cleaning.
        del input_df
        del point_cloud
        self.parent.print_terminal("Process completed")
