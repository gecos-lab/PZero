"""xyz2vtk.py
PZero generic XYZ importer."""

from copy import deepcopy
from os import path as os_path
from uuid import uuid4

from numpy import array as np_array
from numpy import zeros as np_zeros
from pandas import read_csv as pd_read_csv
from pandas import to_numeric as pd_to_numeric
from pyvista import read as pv_read

from pzero.entities_factory import VertexSet
from pzero.imports.pc2vtk import _normalise_coordinate_columns


TEXT_EXTENSIONS = {".txt", ".csv", ".xyz", ".asc", ".dat"}
VTK_EXTENSIONS = {".vtu", ".vtk", ".vtp"}
VALID_PROPERTY_COMPONENTS = {1, 2, 3, 4, 6, 9}


def _coerce_points_to_3d(points_matrix):
    """Return an n x 3 float array."""
    points_array = np_array(points_matrix, dtype=float)
    if points_array.ndim == 1:
        points_array = points_array.reshape(1, -1)
    if points_array.shape[1] == 2:
        out = np_zeros((points_array.shape[0], 3))
        out[:, :2] = points_array
        return out
    return points_array[:, :3]


def _extract_numeric_properties(input_df, excluded_columns=None):
    """Keep numeric properties only."""
    excluded_columns = set(excluded_columns or [])
    properties = {}
    for column_name in input_df.columns:
        if column_name in excluded_columns:
            continue
        numeric_values = pd_to_numeric(input_df[column_name], errors="coerce")
        if numeric_values.notna().all():
            properties[column_name] = numeric_values.to_numpy()
    return properties


def _extract_from_headered_text(file_path):
    """Try reading a text file assuming the first valid row is a header."""
    input_df = pd_read_csv(
        file_path,
        sep=r"[,\s;]+",
        engine="python",
        comment="#",
    )
    if input_df.empty:
        raise ValueError("no tabular data found")

    missing_axes, _ = _normalise_coordinate_columns(input_df)
    if "Z" in missing_axes and "X" in input_df.columns and "Y" in input_df.columns:
        input_df["Z"] = 0.0
        missing_axes.remove("Z")
    if missing_axes:
        raise ValueError("coordinate columns not found in header")

    for axis in ("X", "Y", "Z"):
        input_df[axis] = pd_to_numeric(input_df[axis], errors="raise")

    points = _coerce_points_to_3d(input_df[["X", "Y", "Z"]].to_numpy())
    properties = _extract_numeric_properties(input_df, excluded_columns={"X", "Y", "Z"})
    return points, properties


def _extract_from_plain_text(file_path):
    """Fallback parser for files made of raw XYZ values."""
    points = []
    with open(file_path, "r") as in_file:
        for line in in_file:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            cleaned = stripped.replace("\t", " ").replace(",", " ").replace(";", " ")
            parts = [part for part in cleaned.split() if part]
            if len(parts) < 2:
                continue
            try:
                x_val = float(parts[0])
                y_val = float(parts[1])
                z_val = float(parts[2]) if len(parts) >= 3 else 0.0
            except ValueError:
                continue
            points.append([x_val, y_val, z_val])

    if not points:
        raise ValueError("no valid XYZ rows found")
    return _coerce_points_to_3d(points), {}


def _read_text_xyz(file_path):
    """Read text-based XYZ files with a header-aware pass and a raw fallback."""
    try:
        return _extract_from_headered_text(file_path)
    except Exception:
        return _extract_from_plain_text(file_path)


def _vtk_array_components(values):
    """Return the VTK-compatible component count for a property array."""
    shape = getattr(values, "shape", ())
    if len(shape) > 2:
        return None
    if len(shape) <= 1:
        return 1
    return shape[1]


def _extract_from_vtk(file_path):
    """Read points and supported point properties from a VTK/PyVista-readable file."""
    mesh = pv_read(file_path)
    if not hasattr(mesh, "points") or mesh.points is None or len(mesh.points) == 0:
        raise ValueError("no points found in VTK dataset")

    points = _coerce_points_to_3d(mesh.points)
    properties = {}
    for property_name in mesh.point_data.keys():
        values = np_array(mesh.point_data[property_name])
        if values.size == 0:
            continue
        if values.dtype.kind not in "biuf":
            continue
        components = _vtk_array_components(values)
        if components not in VALID_PROPERTY_COMPONENTS:
            continue
        properties[property_name] = values
    return points, properties


def _build_vertex_set(points, properties=None):
    """Create a VertexSet from points and optional properties."""
    vtk_obj = VertexSet()
    vtk_obj.points = _coerce_points_to_3d(points)
    vtk_obj.auto_cells()

    for property_name, values in (properties or {}).items():
        vtk_obj.set_point_data(data_key=property_name, attribute_matrix=values)

    return vtk_obj


def _resolve_collection(self, collection_name):
    """Map UI label to the destination collection."""
    collection_map = {
        "Geology": self.geol_coll,
        "Fluid contacts": self.fluid_coll,
        "Background data": self.backgrnd_coll,
    }
    return collection_map.get(collection_name)


def _build_entity_dict(collection, vtk_obj, file_path):
    """Build an entity dictionary for the selected collection."""
    basename = os_path.basename(file_path)
    stem = os_path.splitext(basename)[0]
    entity_dict = deepcopy(collection.entity_dict)
    entity_dict["uid"] = str(uuid4())
    entity_dict["name"] = basename
    entity_dict["topology"] = "VertexSet"
    entity_dict["vtk_obj"] = vtk_obj
    entity_dict["properties_names"] = list(vtk_obj.point_data_keys)
    entity_dict["properties_components"] = [
        vtk_obj.get_point_data_shape(property_name)[1]
        for property_name in entity_dict["properties_names"]
    ]
    if "feature" in entity_dict:
        entity_dict["feature"] = stem
    if "role" in entity_dict:
        entity_dict["role"] = "undef"
    return entity_dict


def xyz2vtk(self=None, in_file_names=None, collection_name="Geology"):
    """
    Import multiple generic XYZ-like files as VertexSet entities.

    Supported formats:
    - Text-based: .txt, .csv, .xyz, .asc, .dat
    - VTK-based: .vtu, .vtk, .vtp
    """
    if self is None or not in_file_names:
        return

    collection = _resolve_collection(self, collection_name)
    if collection is None:
        self.print_terminal(f"Unsupported destination collection: {collection_name}")
        return

    imported_count = 0
    failed_files = []

    for in_file_name in in_file_names:
        _, extension = os_path.splitext(in_file_name)
        extension = extension.lower()
        try:
            if extension in TEXT_EXTENSIONS:
                points, properties = _read_text_xyz(in_file_name)
            elif extension in VTK_EXTENSIONS:
                points, properties = _extract_from_vtk(in_file_name)
            else:
                raise ValueError(f"unsupported extension {extension}")

            vtk_obj = _build_vertex_set(points=points, properties=properties)
            entity_dict = _build_entity_dict(
                collection=collection, vtk_obj=vtk_obj, file_path=in_file_name
            )
            collection.add_entity_from_dict(entity_dict=entity_dict)
            imported_count += 1
            self.print_terminal(
                f"Imported XYZ points: {os_path.basename(in_file_name)} ({vtk_obj.points_number} points)"
            )
        except Exception as exc:
            failed_files.append((os_path.basename(in_file_name), str(exc)))
            self.print_terminal(
                f"Failed to import XYZ points from {os_path.basename(in_file_name)}: {exc}"
            )

    if imported_count:
        self.print_terminal(
            f"XYZ import completed: {imported_count} file(s) added to {collection_name}."
        )
    if failed_files:
        failed_summary = "; ".join(
            f"{file_name}: {error_message}" for file_name, error_message in failed_files
        )
        self.print_terminal(f"XYZ import skipped/failed files: {failed_summary}")
