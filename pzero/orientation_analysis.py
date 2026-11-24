"""orientation_analysis.py
PZero© Andrea Bistacchi"""

from numpy import cos as np_cos
from numpy import sin as np_sin
from numpy import deg2rad as np_deg2rad
from numpy import greater as np_greater
from numpy import less_equal as np_less_equal
from numpy import array as np_array
from numpy import asarray as np_asarray
from numpy import arange as np_arange
from numpy import cross as np_cross
from numpy import squeeze as np_squeeze
from numpy import sum as np_sum
from numpy import dot as np_dot
from numpy import argsort as np_argsort
from numpy import column_stack as np_column_stack
from numpy import vstack as np_vstack
from numpy import concatenate as np_concatenate
from numpy import isin as np_isin
from numpy import sqrt as np_sqrt
from numpy import exp as np_exp
from numpy import atleast_1d as np_atleast_1d
from numpy import argmin as np_argmin
from numpy import where as np_where
from numpy import all as np_all
from numpy import arctan2 as np_arctan2
from numpy import arcsin as np_arcsin
from numpy import clip as np_clip
from numpy import pi as np_pi
from numpy import abs as np_abs
from numpy import any as np_any
from numpy.linalg import norm as np_linalg_norm
from numpy.linalg import eigh as np_linalg_eigh
from numpy.linalg import det as np_linalg_det
from numpy.random import default_rng as np_random_default_rng
from numpy import ndarray as np_ndarray
from numpy import number as np_number

from scipy.spatial.distance import cdist
from scipy.cluster.vq import kmeans2

from pzero.helpers.helper_dialogs import multiple_input_dialog, options_dialog

from .helpers.helper_functions import uses_selection
from .helpers.helper_functions import freeze_gui_onoff, freeze_gui_on, freeze_gui_off

# -----IN THE FUTURE add functions for orientation analysis.-----


def strikes2dip_directions(strikes=None):
    """Convert Strike to Dip-Direction according to right-hand rule,
    all in degrees. Accepts single values, lists or Numpy arrays and
    returns the same types."""
    if isinstance(strikes, np_ndarray):
        strikes_array = strikes
        directions_array = (strikes_array + 90) * np_less_equal(strikes_array, 270) + (
            strikes_array - 270
        ) * np_greater(strikes_array, 270)
        directions = directions_array
        return directions
    elif isinstance(strikes, list):
        strikes_array = np_asarray(strikes)
        directions_array = (strikes_array + 90) * np_less_equal(strikes_array, 270) + (
            strikes_array - 270
        ) * np_greater(strikes_array, 270)
        directions = list(directions_array)
        return directions
    elif isinstance(strikes, (float, int)):
        if strikes <= 270:
            directions = strikes + 90
        else:
            directions = strikes - 270
        return directions
    else:
        print("Strike type not recognized")


# ---- Orientation property names (see "Orientation conventions" in pzero/README.md) ----
# Planes / surfaces: Normals (unit vectors, downwards for normal polarity, upwards for overturned)
# and Dip / Direction. Lines / lineations: Lineations (unit vectors, downwards for normal polarity,
# upwards for overturned) and Plunge / Trend.
NORMALS = "Normals"
DIP = "Dip"
DIRECTION = "Direction"
LINEATIONS = "Lineations"
PLUNGE = "Plunge"
TREND = "Trend"
ORIENTATION_PROPERTY_NAMES = (NORMALS, DIP, DIRECTION, LINEATIONS, PLUNGE, TREND)

# Older names, compared ignoring case, spaces, underscores and other separators.
_ORIENTATION_ALIASES = {
    "normals": NORMALS,
    "normal": NORMALS,
    "lineations": LINEATIONS,
    "lineation": LINEATIONS,
    "dip": DIP,
    "dipdirection": DIRECTION,
    "dipdir": DIRECTION,
    "direction": DIRECTION,
    "dipazimuth": DIRECTION,
    "dipaz": DIRECTION,
    "plunge": PLUNGE,
    "trend": TREND,
    "plungeazimuth": TREND,
    "plungeaz": TREND,
    "plungedirection": TREND,
    "plungedir": TREND,
}


def _orientation_key(name):
    from re import sub as re_sub

    return re_sub(r"[^a-z0-9]", "", str(name).lower())


def orientation_name_map(names=None):
    """Renames {old name: canonical name} for the orientation properties among names (e.g.
    "dip direction" -> "Direction", "plunge" -> "Plunge"). A plain "azimuth" is the Direction of a
    plane if there is a dip, or the Trend of a line if there is a plunge (unchanged if both or
    neither). Names whose canonical name is already present are not renamed."""
    names = [str(name) for name in (names or [])]
    keys = {_orientation_key(name) for name in names}
    has_dip, has_plunge = "dip" in keys, "plunge" in keys
    taken = set(names)
    mapping = {}
    for name in names:
        key = _orientation_key(name)
        new = _ORIENTATION_ALIASES.get(key)
        if key == "azimuth":
            new = DIRECTION if has_dip and not has_plunge else (TREND if has_plunge and not has_dip else None)
        if new and new != name and new not in taken:
            mapping[name] = new
            taken.add(new)
    return mapping


def find_orientation_property(names=None, canonical=None):
    """The name under which the orientation property canonical (e.g. DIRECTION) is stored among
    names: the canonical name, or an older name (e.g. "dip direction") of an entity not converted
    yet. None if absent."""
    names = [str(name) for name in (names or [])]
    if canonical in names:
        return canonical
    for old, new in orientation_name_map(names).items():
        if new == canonical:
            return old
    return None


def rename_orientation_arrays(vtk_obj=None):
    """Rename the orientation arrays of a VTK object (point, cell and field data) to the canonical
    names. Returns {old: new} of the point data (the entity properties)."""
    point_mapping = {}
    for data, is_point_data in (
        (vtk_obj.GetPointData(), True),
        (vtk_obj.GetCellData(), False),
        (vtk_obj.GetFieldData(), False),
    ):
        if data is None:
            continue
        array_names = [data.GetArrayName(i) for i in range(data.GetNumberOfArrays())]
        mapping = orientation_name_map([name for name in array_names if name])
        for old, new in mapping.items():
            data.GetAbstractArray(old).SetName(new)
        if is_point_data:
            point_mapping = mapping
    if point_mapping or vtk_obj is not None:
        vtk_obj.Modified()
    return point_mapping


def normalize_orientation_names(project=None):
    """Failsafe for projects saved with older orientation names (dip direction, dip_dir, azimuth,
    plunge, trend, ...): rename them to the canonical names (Dip, Direction, Plunge, Trend, ...) in
    the entity metadata (properties_names), in the VTK arrays and in the property legend. Called
    when a project is opened. Returns {(old, new): number of entities} and prints a summary."""
    collections = [
        getattr(project, name, None)
        for name in ("geol_coll", "fluid_coll", "backgrnd_coll", "boundary_coll", "dom_coll", "mesh3d_coll")
    ]
    renamed = {}
    for collection in collections:
        if collection is None or "properties_names" not in collection.df.columns:
            continue
        for idx in collection.df.index:
            uid = collection.df.at[idx, "uid"]
            vtk_obj = collection.get_uid_vtk_obj(uid)
            if vtk_obj is not None:
                rename_orientation_arrays(vtk_obj)
            names = list(collection.df.at[idx, "properties_names"] or [])
            mapping = orientation_name_map(names)
            if not mapping:
                continue
            collection.df.at[idx, "properties_names"] = [mapping.get(name, name) for name in names]
            for old, new in mapping.items():
                renamed[(old, new)] = renamed.get((old, new), 0) + 1
    legend = getattr(project, "prop_legend_df", None)
    if legend is not None and "property_name" in legend.columns and not legend.empty:
        legend_names = legend["property_name"].astype(str).tolist()
        bases = [name.split("[")[0] for name in legend_names]
        base_mapping = orientation_name_map(list(dict.fromkeys(bases)))
        drop = []
        for idx, name, base in zip(legend.index, legend_names, bases):
            if base in base_mapping:
                new_name = base_mapping[base] + name[len(base):]
                if new_name in legend_names:
                    drop.append(idx)
                else:
                    legend.at[idx, "property_name"] = new_name
        if drop:
            legend.drop(index=drop, inplace=True)
            legend.reset_index(drop=True, inplace=True)
    if renamed and hasattr(project, "print_terminal"):
        summary = ", ".join(f"{old} -> {new} ({count})" for (old, new), count in renamed.items())
        project.print_terminal(f"Orientation property names updated to the current convention: {summary}")
    return renamed


def plunge_trends2lineations(plunges=None, trends=None):
    """Convert Plunge/Trend measurements in degrees (single or list)
    to lineation unit vectors pointing downwards if Plunge > 0.
    Accepts single values, lists or Numpy arrays and
    returns Numpy arrays."""
    if isinstance(plunges, (float, int, list, np_number)) and isinstance(
        trends, (float, int, list, np_number)
    ):
        plunges_array = np_asarray(plunges)
        trends_array = np_asarray(trends)
    elif isinstance(plunges, np_ndarray) and isinstance(trends, np_ndarray):
        plunges_array = plunges
        trends_array = trends
    else:
        print("Plunge/Trend type not recognized.")
    plunges_array = np_deg2rad(plunges_array)
    trends_array = np_deg2rad(trends_array)
    lineations = np_asarray(
        [
            np_sin(trends_array) * np_cos(plunges_array),
            np_cos(trends_array) * np_cos(plunges_array),
            -np_sin(plunges_array),
        ]
    )
    return lineations.T


def dip_directions2normals(dips=None, directions=None, return_dip_dir_vec=False):
    """Convert Dip/Direction measurements in degrees (single or list) to normal unit vectors.
    0 <= Dip <= 90 gives downward normals (upright planes). Overturned planes (upward normals) are
    accepted in both equivalent conventions: 90 < Dip <= 180 with the same Direction, or
    -90 < Dip < 0 with the opposite Direction (Dip, Direction) == (Dip + 180, Direction + 180).
    normals2dip_directions returns the > 90 convention.
    Accepts single values, lists or Numpy arrays and
    returns Numpy arrays. We use np_squeeze to avoid having multi-dimensional arrays"""
    if isinstance(dips, (float, int, list)) and isinstance(
        directions, (float, int, list)
    ):
        dips_array = np_squeeze(np_asarray(dips))
        directions_array = np_squeeze(np_asarray(directions))
    elif isinstance(dips, np_ndarray) and isinstance(directions, np_ndarray):
        dips_array = np_squeeze(dips)
        directions_array = np_squeeze(directions)
    else:
        print("Dip/Direction type not recognized.")
    dips_array = np_squeeze(np_asarray(dips_array, dtype=float))
    directions_array = np_squeeze(np_asarray(directions_array, dtype=float))
    # Negative dips (overturned planes) -> equivalent > 90 convention.
    negative = dips_array < 0
    dips_array = dips_array + 180 * negative
    directions_array = directions_array + 180 * negative
    # The normal is the line with trend Direction + 180 and plunge 90 - Dip: it points downwards
    # for Dip < 90 and upwards (negative plunge) for Dip > 90.
    plunges_array = 90 - dips_array
    trends_array = (directions_array + 180) % 360
    normals = plunge_trends2lineations(plunges=plunges_array, trends=trends_array)

    return normals


def vset_set_normals(VertexSet=None, dip_name=None, dir_name=None):
    """Set the Normals point property of a VertexSet / XsVertexSet (the argument, an instance)
    from its dip and direction point properties."""
    dips_array = VertexSet.get_point_data(dip_name)
    dirs_array = VertexSet.get_point_data(dir_name)
    normals = dip_directions2normals(dips=dips_array, directions=dirs_array)
    VertexSet.init_point_data(data_key="Normals", dimension=3)
    VertexSet.set_point_data(data_key="Normals", attribute_matrix=normals)


@uses_selection(topologies=["VertexSet", "XsVertexSet", "TriSurf", "XsPolyLine", "PCDom"], cross_collection=True)
@freeze_gui_onoff
def set_normals(self):
    """
    Set the Normals point property on the selected entities, of any collection, each in its own:
    - VertexSet / XsVertexSet: from their dip and direction properties (names asked once, among the
      properties shared by all the selected point sets);
    - TriSurf, XsPolyLine and PCDom (point clouds): calculated from the geometry.
    Other entities (e.g. DEMs) cannot have normals calculated and are deselected by @uses_selection.
    """
    from .entities_factory import VertexSet, XsVertexSet
    from .helpers.helper_functions import entity_collection, tool_uids

    uids = tool_uids(self)
    if not uids:
        self.print_terminal("No input data selected.")
        return

    def add_normals_property(collection, uid):
        if "Normals" not in collection.get_uid_properties_names(uid):
            collection.append_uid_property(
                uid=uid, property_name="Normals", property_components=3
            )

    point_set_uids = [
        uid
        for uid in uids
        if isinstance(entity_collection(self, uid).get_uid_vtk_obj(uid), (VertexSet, XsVertexSet))
    ]
    geometry_uids = [uid for uid in uids if uid not in set(point_set_uids)]

    # Point sets: normals from dip / direction properties.
    if point_set_uids:
        property_name_list = list(
            entity_collection(self, point_set_uids[0]).get_uid_properties_names(point_set_uids[0])
        )
        for uid in point_set_uids[1:]:
            names = entity_collection(self, uid).get_uid_properties_names(uid)
            property_name_list = [name for name in property_name_list if name in names]
        if not property_name_list:
            self.print_terminal(
                " -- Normals of point sets: no dip/direction properties shared by all of them -- "
            )
        else:
            updt_dict = multiple_input_dialog(
                title="Select Dip/Direction property names",
                input_dict={
                    "dip_name": ["Dip property: ", property_name_list],
                    "dir_name": ["Direction property: ", property_name_list],
                },
            )
            if updt_dict is not None:
                for uid in point_set_uids:
                    collection = entity_collection(self, uid)
                    add_normals_property(collection, uid)
                    vset_set_normals(
                        VertexSet=collection.get_uid_vtk_obj(uid),
                        dip_name=updt_dict["dip_name"],
                        dir_name=updt_dict["dir_name"],
                    )
                    self.print_terminal(f"Normals set on {collection.get_uid_name(uid)}")

    # TriSurf, XsPolyLine, point clouds: normals from geometry.
    for uid in geometry_uids:
        collection = entity_collection(self, uid)
        add_normals_property(collection, uid)
        collection.get_uid_vtk_obj(uid).vtk_set_normals()
        self.print_terminal(f"Normals set on {collection.get_uid_name(uid)}")

    _emit_values_modified(self, uids)
    self.prop_legend.update_widget(self)
    self.print_terminal("All Normals set.")


def _emit_values_modified(self, uids):
    """Emit data_val_modified for uids, grouped by collection, so that the views showing these
    properties (e.g. the stereoplot showing Normals) redraw them. self is the ProjectWindow."""
    from .helpers.helper_functions import entity_collection

    by_collection = {}
    for uid in uids:
        collection = entity_collection(self, uid)
        if collection is not None:
            by_collection.setdefault(collection.collection_name, (collection, []))[1].append(uid)
    for collection, collection_uids in by_collection.values():
        self.signals.data_val_modified.emit(collection_uids, collection)


def invert_dip_directions(dips=None, directions=None):
    """Dip/Direction of the same planes with the opposite polarity (normal n -> -n): an upright
    plane becomes overturned and vice versa. Negative (overturned) dips are first converted to the
    equivalent > 90 convention, so the result is always 0 <= Dip <= 180. Returns two Numpy arrays."""
    dips = np_asarray(dips, dtype=float).copy()
    directions = np_asarray(directions, dtype=float).copy()
    negative = dips < 0
    dips[negative] += 180
    directions[negative] += 180
    return 180 - dips, (directions + 180) % 360


@uses_selection(cross_collection=True)
@freeze_gui_onoff
def invert_polarity(self):
    """
    Properties > Invert polarity: invert the facing direction of the selected entities (any class
    and collection), e.g. a surface whose normals point downwards on the overturned limb and upwards
    on the upright one. Normals are inverted (n -> -n) if present; dip / dip direction point
    properties are converted to the opposite polarity if present (dip -> 180 - dip, direction ->
    direction + 180); both, consistently, if both are present. For TriSurfs the order of the
    triangle vertices is also reversed, so that Calculate Normals keeps the new polarity.
    Entities with neither Normals nor Dip and Direction are deselected.
    """
    from vtkmodules.vtkFiltersCore import vtkReverseSense
    from .entities_factory import TriSurf
    from .helpers.helper_functions import entity_collection, tool_uids

    unusable = []
    inverted = []
    for uid in tool_uids(self):
        collection = entity_collection(self, uid)
        vtk_obj = collection.get_uid_vtk_obj(uid) if collection is not None else None
        keys = list(vtk_obj.point_data_keys) if vtk_obj is not None else []
        has_normals = NORMALS in keys
        dip_name = find_orientation_property(keys, DIP)
        direction_name = find_orientation_property(keys, DIRECTION)
        has_dip = dip_name is not None and direction_name is not None
        if not (has_normals or has_dip):
            unusable.append(uid)
            continue
        done = []
        if has_normals:
            # Flip the existing arrays in place: same data type and same role (active point /
            # cell normals), so that the views show them exactly as before.
            from vtkmodules.util.numpy_support import vtk_to_numpy

            for data in (vtk_obj.GetPointData(), vtk_obj.GetCellData()):
                array = data.GetArray("Normals")
                if array is not None:
                    values = vtk_to_numpy(array)  # a view on the VTK array
                    values *= -1
                    array.Modified()
            done.append("Normals")
            if isinstance(vtk_obj, TriSurf) and vtk_obj.GetNumberOfPolys() > 0:
                # Reverse the triangle vertex order (point normals and data are untouched), so
                # that vtkPolyDataNormals (Calculate Normals) gives the new polarity.
                reverse = vtkReverseSense()
                reverse.SetInputData(vtk_obj)
                reverse.ReverseCellsOn()
                reverse.ReverseNormalsOff()
                reverse.Update()
                vtk_obj.SetPolys(reverse.GetOutput().GetPolys())
                done.append("triangle order")
        if has_dip:
            dips, directions = invert_dip_directions(
                vtk_obj.get_point_data(dip_name), vtk_obj.get_point_data(direction_name)
            )
            vtk_obj.set_point_data(data_key=dip_name, attribute_matrix=dips)
            vtk_obj.set_point_data(data_key=direction_name, attribute_matrix=directions)
            done.append("Dip / Direction")
        vtk_obj.Modified()
        inverted.append(uid)
        self.print_terminal(
            f"Polarity inverted on {collection.get_uid_name(uid)}: {', '.join(done)}"
        )
    if unusable:
        self.print_terminal(
            f" -- Invert normals: {len(unusable)} entities without Normals or Dip and "
            f"Direction deselected -- "
        )
        self.set_selection(uids=unusable, mode="remove", source=self)
    if inverted:
        _emit_values_modified(self, inverted)
        self.prop_legend.update_widget(self)


def lineations2plunge_trends(lineations=None):
    """Convert lineation vectors (N x 3, or a single 3-vector) to Plunge/Trend in degrees, inverse of
    plunge_trends2lineations: -90 <= Plunge <= 90, positive for vectors pointing downwards and
    negative for upward (overturned) ones; 0 <= Trend < 360 toward the horizontal component of the
    vector. Returns two Numpy arrays (plunges, trends)."""
    from numpy import degrees as np_degrees

    vectors = np_asarray(lineations, dtype=float).reshape(-1, 3)
    plunges = np_degrees(np_arcsin(np_clip(-vectors[:, 2], -1.0, 1.0)))
    trends = np_degrees(np_arctan2(vectors[:, 0], vectors[:, 1])) % 360
    return plunges, trends


def line_lineations(polyline=None):
    """Lineations of a polyline: at each node, the unit vector of the average of the unit vectors of
    the segments meeting at that node, oriented from the first to the last node of each line. The
    end nodes of open lines have one segment; on closed loops (last node = first node, by index or
    by position) the first and last nodes have two; nodes shared by several lines average all their
    segments. Nodes without segments (or where segments cancel out) get NaN.
    Returns an N x 3 Numpy array."""
    from numpy import allclose as np_allclose
    from numpy import full as np_full
    from numpy import nan as np_nan
    from numpy import zeros as np_zeros
    from numpy.linalg import norm as np_norm
    from vtkmodules.vtkCommonCore import vtkIdList

    points = np_asarray(polyline.points, dtype=float).reshape(-1, 3)
    sums = np_zeros(points.shape, dtype=float)
    lines = polyline.GetLines()
    ids = vtkIdList()
    lines.InitTraversal()
    while lines.GetNextCell(ids):
        cell = [ids.GetId(i) for i in range(ids.GetNumberOfIds())]
        if len(cell) < 2:
            continue
        units = []
        for a, b in zip(cell[:-1], cell[1:]):
            segment = points[b] - points[a]
            length = np_norm(segment)
            unit = segment / length if length > 0 else None
            units.append(unit)
            if unit is not None:
                sums[a] += unit
                sums[b] += unit
        closed_by_position = cell[0] != cell[-1] and np_allclose(points[cell[0]], points[cell[-1]])
        if closed_by_position and units[0] is not None and units[-1] is not None:
            # closed loop with distinct first and last nodes at the same position
            sums[cell[0]] += units[-1]
            sums[cell[-1]] += units[0]
    norms = np_norm(sums, axis=1)
    lineations = np_full(points.shape, np_nan)
    valid = norms > 1e-12
    lineations[valid] = sums[valid] / norms[valid][:, None]
    return lineations


def _reverse_line_order(polyline=None):
    """Reverse the node order of every line cell of a polyline (point data untouched)."""
    from vtkmodules.vtkCommonCore import vtkIdList
    from vtkmodules.vtkCommonDataModel import vtkCellArray

    reversed_lines = vtkCellArray()
    ids = vtkIdList()
    lines = polyline.GetLines()
    lines.InitTraversal()
    while lines.GetNextCell(ids):
        cell = [ids.GetId(i) for i in range(ids.GetNumberOfIds())]
        reversed_lines.InsertNextCell(len(cell), cell[::-1])
    polyline.SetLines(reversed_lines)


def _invert_lineations_of(vtk_obj=None):
    """Invert the sense of the lineations of an entity: Lineations n -> -n, Plunge -> -Plunge,
    Trend -> Trend + 180 (the same line, opposite sense), and the node order of lines (so that
    Calculate Lineations keeps the new sense). Returns the list of what was changed."""
    from vtkmodules.util.numpy_support import vtk_to_numpy
    from .entities_factory import PolyLine

    done = []
    keys = list(vtk_obj.point_data_keys)
    for data in (vtk_obj.GetPointData(), vtk_obj.GetCellData()):
        array = data.GetArray(LINEATIONS) if data is not None else None
        if array is not None:
            values = vtk_to_numpy(array)  # a view on the VTK array
            values *= -1
            array.Modified()
    if LINEATIONS in keys:
        done.append(LINEATIONS)
    plunge_name = find_orientation_property(keys, PLUNGE)
    trend_name = find_orientation_property(keys, TREND)
    if plunge_name and trend_name:
        plunges = np_asarray(vtk_obj.get_point_data(plunge_name), dtype=float)
        trends = np_asarray(vtk_obj.get_point_data(trend_name), dtype=float)
        vtk_obj.set_point_data(data_key=plunge_name, attribute_matrix=-plunges)
        vtk_obj.set_point_data(data_key=trend_name, attribute_matrix=(trends + 180.0) % 360)
        done.append("Plunge / Trend")
    if isinstance(vtk_obj, PolyLine) and vtk_obj.GetNumberOfLines() > 0:
        _reverse_line_order(vtk_obj)
        done.append("node order")
    vtk_obj.Modified()
    return done


def _set_point_property(collection, uid, vtk_obj, name, values):
    """Store values as the point property name of uid (added to the metadata if new)."""
    if name not in collection.get_uid_properties_names(uid):
        collection.append_uid_property(
            uid=uid, property_name=name, property_components=1 if values.ndim == 1 else values.shape[1]
        )
    vtk_obj.set_point_data(data_key=name, attribute_matrix=values)


@uses_selection(topologies=["VertexSet", "XsVertexSet", "PolyLine", "XsPolyLine"], cross_collection=True)
@freeze_gui_onoff
def set_lineations(self):
    """
    Properties > Calculate Lineations on the selected entities, of any collection, each in its own:
    - point sets (VertexSet, XsVertexSet): Lineations from their Plunge / Trend properties (found
      under the canonical or older names; otherwise their names are asked, among the properties
      shared by those point sets);
    - lines (PolyLine, XsPolyLine): at each node, the average of the segments meeting there,
      oriented from the first to the last node (line_lineations). Lines with lineations mostly
      pointing upwards (overturned by the convention) can then be inverted.
    Lineations are unit vectors, downwards for positive plunge (see "Orientation conventions" in
    pzero/README.md). Other entities are deselected by @uses_selection.
    """
    from .entities_factory import PolyLine
    from .helpers.helper_functions import entity_collection, tool_uids

    uids = tool_uids(self)
    if not uids:
        self.print_terminal("No input data selected.")
        return
    line_uids = [uid for uid in uids if isinstance(entity_collection(self, uid).get_uid_vtk_obj(uid), PolyLine)]
    point_set_uids = [uid for uid in uids if uid not in set(line_uids)]
    done_uids = []

    # Point sets: from Plunge / Trend.
    names_by_uid = {}
    missing = []
    for uid in point_set_uids:
        names = entity_collection(self, uid).get_uid_properties_names(uid)
        plunge_name = find_orientation_property(names, PLUNGE)
        trend_name = find_orientation_property(names, TREND)
        if plunge_name and trend_name:
            names_by_uid[uid] = (plunge_name, trend_name)
        else:
            missing.append(uid)
    if missing:
        shared = list(entity_collection(self, missing[0]).get_uid_properties_names(missing[0]))
        for uid in missing[1:]:
            names = entity_collection(self, uid).get_uid_properties_names(uid)
            shared = [name for name in shared if name in names]
        if not shared:
            self.print_terminal(
                " -- Lineations of point sets: no Plunge / Trend properties shared by all of them -- "
            )
        else:
            answer = multiple_input_dialog(
                title="Select Plunge/Trend property names",
                input_dict={
                    "plunge_name": ["Plunge property: ", shared],
                    "trend_name": ["Trend property: ", shared],
                },
            )
            if answer is not None:
                for uid in missing:
                    names_by_uid[uid] = (answer["plunge_name"], answer["trend_name"])
    for uid, (plunge_name, trend_name) in names_by_uid.items():
        collection = entity_collection(self, uid)
        vtk_obj = collection.get_uid_vtk_obj(uid)
        lineations = np_asarray(
            plunge_trends2lineations(
                plunges=np_asarray(vtk_obj.get_point_data(plunge_name), dtype=float).reshape(-1),
                trends=np_asarray(vtk_obj.get_point_data(trend_name), dtype=float).reshape(-1),
            ),
            dtype=float,
        ).reshape(-1, 3)
        _set_point_property(collection, uid, vtk_obj, LINEATIONS, lineations)
        done_uids.append(uid)
        self.print_terminal(f"Lineations set on {collection.get_uid_name(uid)} (from {plunge_name} / {trend_name})")

    # Lines: from the segments, first to last node.
    upward_uids = []
    for uid in line_uids:
        collection = entity_collection(self, uid)
        vtk_obj = collection.get_uid_vtk_obj(uid)
        lineations = line_lineations(vtk_obj)
        valid = lineations[:, 2] == lineations[:, 2]  # not NaN
        if not valid.any():
            self.print_terminal(f" -- {collection.get_uid_name(uid)}: no segments, no lineations -- ")
            continue
        _set_point_property(collection, uid, vtk_obj, LINEATIONS, lineations)
        done_uids.append(uid)
        if (lineations[valid, 2] > 0).mean() > 0.5:
            upward_uids.append(uid)
        self.print_terminal(f"Lineations set on {collection.get_uid_name(uid)} (first to last node)")
    if upward_uids:
        names = ", ".join(entity_collection(self, uid).get_uid_name(uid) for uid in upward_uids)
        choice = options_dialog(
            title="Calculate Lineations",
            message=(
                f"The lineations of {len(upward_uids)} line(s) mostly point upwards "
                f"(negative plunge, overturned by the convention):\n{names}\n\n"
                "Invert them (and the node order of the lines)?"
            ),
            yes_role="Invert",
            no_role="Keep",
            reject_role=None,
        )
        if choice == 0:
            for uid in upward_uids:
                _invert_lineations_of(entity_collection(self, uid).get_uid_vtk_obj(uid))
            self.print_terminal(f"Lineations inverted on: {names}")
    if done_uids:
        _emit_values_modified(self, done_uids)
        self.prop_legend.update_widget(self)
    self.print_terminal("All Lineations set.")


@uses_selection(valid=None, require_properties=["Lineations"], cross_collection=True)
@freeze_gui_onoff
def lineations2pt(self):
    """Properties > Calculate Plunge/Trend: Plunge and Trend point properties from the Lineations of
    the selected entities, of any collection (lineations2plunge_trends: -90 <= Plunge <= 90,
    negative for upward lineations)."""
    from .helpers.helper_functions import entity_collection, tool_uids

    done_uids = []
    for uid in tool_uids(self):
        collection = entity_collection(self, uid)
        vtk_obj = collection.get_uid_vtk_obj(uid)
        if LINEATIONS not in vtk_obj.point_data_keys:
            self.print_terminal(f" -- {collection.get_uid_name(uid)}: no Lineations, skipped -- ")
            continue
        plunges, trends = lineations2plunge_trends(vtk_obj.get_point_data(LINEATIONS))
        names = collection.get_uid_properties_names(uid)
        for canonical, values in ((PLUNGE, plunges), (TREND, trends)):
            _set_point_property(
                collection, uid, vtk_obj, find_orientation_property(names, canonical) or canonical, values
            )
        done_uids.append(uid)
        self.print_terminal(f"Plunge/trend set on {collection.get_uid_name(uid)}")
    if done_uids:
        _emit_values_modified(self, done_uids)
        self.prop_legend.update_widget(self)
    self.print_terminal("All plunge/trends set.")


@uses_selection(cross_collection=True)
@freeze_gui_onoff
def invert_lineations(self):
    """Properties > Invert lineations: invert the sense of the lineations of the selected entities (any
    class and collection): Lineations n -> -n, Plunge -> -Plunge and Trend -> Trend + 180 (the same
    line, opposite sense), consistently if both are present; for lines also the node order, so that
    Calculate Lineations keeps the new sense. Entities with neither Lineations nor Plunge and Trend
    are deselected."""
    from .helpers.helper_functions import entity_collection, tool_uids

    unusable = []
    inverted = []
    for uid in tool_uids(self):
        collection = entity_collection(self, uid)
        vtk_obj = collection.get_uid_vtk_obj(uid) if collection is not None else None
        keys = list(vtk_obj.point_data_keys) if vtk_obj is not None else []
        has_plunge_trend = find_orientation_property(keys, PLUNGE) and find_orientation_property(keys, TREND)
        if LINEATIONS not in keys and not has_plunge_trend:
            unusable.append(uid)
            continue
        done = _invert_lineations_of(vtk_obj)
        inverted.append(uid)
        self.print_terminal(f"Lineations inverted on {collection.get_uid_name(uid)}: {', '.join(done)}")
    if unusable:
        self.print_terminal(
            f" -- Invert lineations: {len(unusable)} entities without Lineations or Plunge and "
            f"Trend deselected -- "
        )
        self.set_selection(uids=unusable, mode="remove", source=self)
    if inverted:
        _emit_values_modified(self, inverted)
        self.prop_legend.update_widget(self)


def normals2dip_directions(normals=None):
    """Convert normal vectors (N x 3, or a single 3-vector) to Dip/Direction in degrees, inverse of
    dip_directions2normals. Normals pointing downwards (upright planes) give 0 <= Dip <= 90;
    normals pointing upwards (overturned planes) give 90 < Dip <= 180 (the > 90 convention, the
    same as PolyData.points_map_dip / points_map_dip_direction). Direction is opposite to the
    horizontal component of the normal. Returns two Numpy arrays (dips, directions)."""
    normals = np_asarray(normals, dtype=float).reshape(-1, 3)
    directions = (np_arctan2(normals[:, 0], normals[:, 1]) * 180 / np_pi - 180) % 360
    dips = 90 - np_arcsin(np_clip(-normals[:, 2], -1.0, 1.0)) * 180 / np_pi
    return dips, directions


def get_dip_dir_vectors(normals=None, az=False):
    if normals.ndim == 1:
        normals = np_array([normals])
    # normals[np_where(normals[:, 2] > 0)] *= -1
    dir_vectors = normals.copy()
    dir_vectors[:, 2] = 0
    dir_vectors[:, 0], dir_vectors[:, 1] = (
        normals[:, 1],
        -normals[:, 0],
    )  # direction is the az vector rotated clockwise by 90° around the Z axis
    dip_vectors = np_cross(normals, dir_vectors)
    if az:
        az_vectors = dip_vectors.copy()
        az_vectors[:, 2] = 0
        return az_vectors, dir_vectors
    else:
        return dip_vectors, dir_vectors


def fisherparams(samplecart, is_axial=False):
    """
    Calculate fisher parameters.

    Parameters
    ----------
    samplecart : ndarray, shape (N, 3)
        Sample of unit vectors on the sphere
    is_axial : bool, optional
        If True, vectors are resolved to the lower hemisphere before
        computing. Use for plane normals (axial data). Default False
        (polar/lineation data).

    Returns
    -------
    dict
        "mean_direction" : ndarray, shape (1, 3)
            Mean direction (unit vector), resolved to lower hemisphere.
        "kappa" : float
            Fisher concentration parameter.
    """
    samplecart = np_asarray(samplecart, dtype=float)

    if samplecart.ndim != 2 or samplecart.shape[1] != 3:
        raise ValueError("samplecart must have shape (N, 3)")

    if is_axial:
        samplecart = resolve_lower_hemisphere(samplecart)

    n = samplecart.shape[0]

    # Resultant vector
    Rvec = np_sum(samplecart, axis=0)
    R = np_linalg_norm(Rvec)

    if R == 0:
        raise ValueError("Resultant length is zero; mean direction undefined")

    # Mean direction
    muhat = Rvec / R

    # Mean resultant length
    Rbar = R / n

    # Fisher concentration estimate (sphstat formula)
    if Rbar < 0.9:
        kappahat = (3 * Rbar - Rbar**3) / (1 - Rbar**2)
    else:
        kappahat = 1.0 / (Rbar**3 - 4 * Rbar**2 + 3 * Rbar)

    axeshat = muhat.reshape(1, 3)

    # Enforce lower hemisphere on returned mean direction
    if axeshat[0, 2] > 0:
        axeshat = -axeshat

    return {"mean_direction": axeshat, "kappa": kappahat}


# def kentparams(samplecart, is_axial=False):
#     """
#     Calculate kents parameters.

#     Parameters
#     ----------
#     samplecart : ndarray, shape (N, 3)
#         Sample of unit vectors
#     is_axial : bool, optional
#         If True, vectors are resolved to the lower hemisphere before
#         computing. Use for plane normals (axial data). Default False
#         (polar/lineation data).

#     Returns
#     -------
#     dict
#         "axes": ndarray, shape (3, 3)
#             Orthonormal axes:
#             axes[0] = mean direction (mu), resolved to lower hemisphere.
#             axes[1] = major axis (gamma1)
#             axes[2] = minor axis (gamma2)
#         "kappa" : float
#             Kent concentration parameter
#         "beta" : float
#             Kent ovalness parameter
#     """
#     samplecart = np_asarray(samplecart, dtype=float)

#     if samplecart.ndim != 2 or samplecart.shape[1] != 3:
#         raise ValueError("samplecart must have shape (N, 3)")

#     if is_axial:
#         samplecart = resolve_lower_hemisphere(samplecart)

#     n = samplecart.shape[0]

#     # Scatter matrix
#     S = np_dot(samplecart.T, samplecart) / n

#     # Eigen-decomposition (symmetric matrix)
#     evals, evecs = np_linalg_eigh(S)

#     # Sort eigenvalues descending
#     idx = np_argsort(evals)[::-1]
#     evals = evals[idx]
#     evecs = evecs[:, idx]

#     # Axes: mean direction, major, minor
#     mu = evecs[:, 0]
#     gamma1 = evecs[:, 1]
#     gamma2 = evecs[:, 2]

#     # Enforce lower hemisphere on mean direction — eigh returns eigenvectors
#     # with arbitrary sign, so mu and -mu are equally valid mathematically.
#     # For consistent plotting, we resolve to the lower hemisphere here.
#     if mu[2] > 0:
#         mu = -mu
#         # Flip gamma1 too to keep the right-handed system consistent
#         gamma1 = -gamma1

#     # Enforce right-handed coordinate system
#     if np_linalg_det(np_column_stack((mu, gamma1, gamma2))) < 0:
#         gamma2 = -gamma2

#     axes = np_vstack((mu, gamma1, gamma2))

#     # Kent parameters (moment estimates)
#     kappahat = n * (evals[0] - evals[2])
#     betahat = n * (evals[1] - evals[2]) / 2.0

#     return {"axes": axes, "kappa": kappahat, "beta": betahat}


def bingham(samplecart, is_axial=False):
    """
    Calculate Bingham parameters.

    Parameters
    ----------
    samplecart : ndarray, shape (N, 3)
        Sample of unit vectors
    is_axial : bool, optional
        If True, vectors are resolved to the lower hemisphere before
        computing. Use for plane normals (axial data). Default False
        (polar/lineation data). Note: Bingham's orientation tensor is
        already sign-invariant, so is_axial has no effect on kappa/eigenvalues
        — it only affects the sign of returned eigenvectors.

    Returns
    -------
    dict
        "eigenvalues": ndarray, shape (3,)
            Eigenvalues
        "axes": ndarray, shape (3, 3)
            Orthonormal axes:
            axes[0] = major axis (mu), resolved to lower hemisphere.
            axes[1] = intermediate axis (gamma1)
            axes[2] = minor axis (gamma2)
    """
    samplecart = np_asarray(samplecart, dtype=float)

    if samplecart.ndim != 2 or samplecart.shape[1] != 3:
        raise ValueError("samplecart must have shape (N, 3)")

    if is_axial:
        samplecart = resolve_lower_hemisphere(samplecart)

    n = samplecart.shape[0]

    # Scatter matrix
    T = np_dot(samplecart.T, samplecart) / n

    # Bingham distribution parameters
    eigenvalues, eigenvectors = np_linalg_eigh(T)
    idx = np_argsort(eigenvalues)[::-1]
    eigenvalues = eigenvalues[idx]
    eigenvectors = eigenvectors[:, idx]

    # Axes: major, intermediate, minor
    mu = eigenvectors[:, 0]
    gamma1 = eigenvectors[:, 1]
    gamma2 = eigenvectors[:, 2]

    # Enforce lower hemisphere on major axis — same reasoning as kentparams:
    # eigh sign is arbitrary, resolve for consistent plotting.
    if mu[2] > 0:
        mu = -mu
        gamma1 = -gamma1

    # Enforce right-handed coordinate system
    if np_linalg_det(np_column_stack((mu, gamma1, gamma2))) < 0:
        gamma2 = -gamma2

    axes = np_vstack((mu, gamma1, gamma2))

    return {"eigenvalues": eigenvalues, "axes": axes}


def kmeans_clusters(samplecart, k, seeds=None, is_axial=False):
    """
    Calculate k-means clusters.

    Parameters
    ----------
    samplecart : ndarray, shape (N, 3)
        Sample of unit vectors
    k : int
        Number of clusters to form
    seeds : ndarray, shape (k, 3), optional
        Initial centroids for k-means. If provided, used directly as starting
        points (minit='matrix'). If None, k-means++ initialization is used.
    is_axial : bool, optional
        If True, the data is treated as axial (e.g. plane normals). Vectors
        are first resolved to the lower hemisphere, then doubled by appending
        their antipodes before clustering. This prevents clusters that straddle
        the stereonet equator from being split into two phantom clusters.
        Only the labels for the original N vectors are returned.
        Default is False (polar/lineation data).

    Returns
    -------
    dict
        "centroids" : ndarray, shape (k, 3)
            Cluster centroids. Not guaranteed to be unit vectors — must be
            re-normalized before plotting as poles.
        "labels" : ndarray, shape (N,)
            Cluster index (0 to k-1) assigned to each input vector, in the
            same order as samplecart.
    """
    samplecart = np_asarray(samplecart, dtype=float)

    if samplecart.ndim != 2 or samplecart.shape[1] != 3:
        raise ValueError("samplecart must have shape (N, 3)")

    n = samplecart.shape[0]

    if k < 1:
        raise ValueError("k must be at least 1")

    if is_axial:
        samplecart_resolved = resolve_lower_hemisphere(samplecart)
        samplecart_input = double_axial(samplecart_resolved)
    else:
        samplecart_input = samplecart

    n_input = samplecart_input.shape[0]

    if k > n_input:
        raise ValueError(
            f"k ({k}) cannot be greater than the number of data points ({n_input})"
        )

    if seeds is not None:
        seeds = np_asarray(seeds, dtype=float)
        if seeds.shape != (k, 3):
            raise ValueError(f"seeds must have shape ({k}, 3), got {seeds.shape}")
        if is_axial:
            seeds_input = resolve_lower_hemisphere(seeds)
        else:
            seeds_input = seeds
        centroids, labels_input = kmeans2(samplecart_input, seeds_input, minit="matrix")
    else:
        centroids, labels_input = kmeans2(samplecart_input, k, minit="++")

    # For axial data, keep only labels for the original N vectors
    labels = labels_input[:n]

    return {"centroids": centroids, "labels": labels}


def _cluster_medoid(points, max_exact=4000, n_candidates=500, n_reference=4000):
    """Index (in points) of the medoid of a cluster: the point with the smallest sum of distances
    to the others. Exact up to max_exact points; for larger clusters (an exact search needs a
    points x points matrix, e.g. 320 GB for 200k vectors) the candidates are the n_candidates
    points closest to the cluster mean direction, and the sums are computed on a random sample of
    n_reference points (as in CLARA), drawn with a fixed seed so that the PAM iterations converge."""
    from numpy import argpartition as np_argpartition

    m = points.shape[0]
    if m <= max_exact:
        return int(np_argmin(cdist(points, points).sum(axis=1)))
    mean = points.mean(axis=0)
    candidates = np_argpartition(-(points @ mean), n_candidates)[:n_candidates]
    reference = points[np_random_default_rng(0).choice(m, n_reference, replace=False)]
    sums = cdist(points[candidates], reference).sum(axis=1)
    return int(candidates[np_argmin(sums)])


def kmedoids_clusters(samplecart, k, seeds=None, is_axial=False):
    """
    Calculate k-medoids clusters using the PAM algorithm.
    Unlike k-means, medoids are actual data points rather than arithmetic
    means, making them more appropriate for directional/spherical data where
    the mean of unit vectors is not itself a unit vector.

    Parameters
    ----------
    samplecart : ndarray, shape (N, 3)
        Sample of unit vectors
    k : int
        Number of clusters to form
    seeds : ndarray, shape (k, 3), optional
        Initial medoid vectors. Each seed is matched to its nearest actual
        data point, which becomes the initial medoid. If None, k random
        data points are chosen as initial medoids.
    is_axial : bool, optional
        If True, the data is treated as axial (plane normals) and doubled
        before clustering to prevent border-straddling splits. Only the
        labels for the original N vectors are returned. Default False.

    Returns
    -------
    dict
        "centroids" : ndarray, shape (k, 3)
            Medoid vectors — actual data points from samplecart, guaranteed
            to be unit vectors. Named "centroids" for interface compatibility
            with kmeans_clusters.
        "labels" : ndarray, shape (N,)
            Cluster index (0 to k-1) assigned to each input vector.
    """
    samplecart = np_asarray(samplecart, dtype=float)

    ### Clause guard part ###
    if samplecart.ndim != 2 or samplecart.shape[1] != 3:
        raise ValueError("samplecart must have shape (N, 3)")

    n = samplecart.shape[0]

    if k < 1:
        raise ValueError("k must be at least 1")

    if is_axial:
        samplecart_resolved = resolve_lower_hemisphere(samplecart)
        samplecart_input = double_axial(samplecart_resolved)
    else:
        samplecart_input = samplecart

    n_input = samplecart_input.shape[0]

    if k > n:
        raise ValueError(
            f"k ({k}) cannot be greater than the number of data points ({n})"
        )
    # Axial data are doubled (each vector and its opposite), so every cluster has an opposite copy:
    # 2k clusters are searched, starting from opposite pairs of medoids, and each cluster is merged
    # with its opposite copy at the end, giving k clusters (with k clusters of the doubled data,
    # a cluster and its own copy would often be two of them, i.e. only k/2 distinct clusters).
    k_input = 2 * k if is_axial else k

    # Initialize medoid indices
    if seeds is not None:
        seeds = np_asarray(seeds, dtype=float)
        if seeds.shape[0] != k:
            raise ValueError(f"seeds must have shape (k, 3), got {seeds.shape}")
        if is_axial:
            seeds = np_vstack([seeds, -seeds])
        # Match each seed to its nearest actual data point
        D_seeds = cdist(
            seeds, samplecart_input
        )  # If seed picking, initialize the medoid with the closest point
        medoid_indices = np_argmin(D_seeds, axis=1)  # for each seed
    else:
        # If no seed picking: k-medoids++ (Arthur and Vassilvitskii 2007), the first medoid at random,
        # the next ones far from those already chosen (probability proportional to the squared
        # distance), fixed seed. For axial data the medoids are chosen in opposite pairs.
        from numpy import minimum as np_minimum

        rng = np_random_default_rng(42)
        chosen = [int(rng.integers(n))]
        candidates = samplecart_input[:n]

        def _pair(indices):
            return list(indices) + [i + n for i in indices] if is_axial else list(indices)

        nearest = cdist(candidates, samplecart_input[_pair(chosen)]).min(axis=1)
        while len(chosen) < k:
            weights = nearest**2
            total = weights.sum()
            if total > 0:
                new = int(rng.choice(n, p=weights / total))
            else:
                new = int(rng.choice([i for i in range(n) if i not in chosen]))
            chosen.append(new)
            nearest = np_minimum(
                nearest, cdist(candidates, samplecart_input[_pair([new])]).min(axis=1)
            )
        medoid_indices = np_array(_pair(chosen))

    # PAM update loop
    ### The actual loop that is the method ###
    best_cost = None
    best_medoid_indices = medoid_indices.copy()
    for _ in range(300):  # 300 should be enough to converge
        D = cdist(
            samplecart_input, samplecart_input[medoid_indices]
        )  # Distance between all poles and the current medoids
        labels_input = np_argmin(D, axis=1)  # Find the nearest medoid for each point
        # Stop when the total distance to the medoids does not decrease any more (approximated
        # medoids of large clusters can otherwise alternate between equivalent solutions).
        cost = D[np_arange(n_input), labels_input].sum()
        if best_cost is not None and cost >= best_cost * (1.0 - 1e-12):
            break
        best_cost = cost
        best_medoid_indices = medoid_indices.copy()

        new_medoid_indices = medoid_indices.copy()
        for j in range(k_input):  # For each cluster j
            cluster_mask = labels_input == j  # Test if there are poles in that cluster
            if not cluster_mask.any():
                continue
            cluster_indices = np_where(cluster_mask)[
                0
            ]  # Take all the points assigned to that cluster
            # The point with the smallest total distance to the others of the cluster becomes
            # the new medoid (approximated for large clusters, see _cluster_medoid).
            best = cluster_indices[
                _cluster_medoid(samplecart_input[cluster_indices])
            ]
            new_medoid_indices[j] = best  # Make this point the new medoid

        if np_all(
            new_medoid_indices == medoid_indices
        ):  # If the medoid didn't changed, it converge, break the loop
            break
        medoid_indices = new_medoid_indices
    medoid_indices = best_medoid_indices

    # Final assignment
    D = cdist(samplecart_input, samplecart_input[medoid_indices])
    labels_input = np_argmin(D, axis=1)
    if is_axial:
        # Merge each cluster with its opposite copy: the cluster that contains the opposite of
        # its medoid (index + n in the doubled data). Each pair keeps the smaller cluster id.
        from numpy import minimum as np_minimum
        from numpy import unique as np_unique

        partner = labels_input[(medoid_indices + n) % n_input]
        pair_id = np_minimum(np_arange(k_input), partner)
        pair_labels = pair_id[labels_input[:n]]  # labels of the original N vectors only
        kept_clusters, labels = np_unique(pair_labels, return_inverse=True)
        # centre of each pair: its medoid, as the original (lower hemisphere) vector
        medoids = samplecart_input[medoid_indices[kept_clusters] % n]
    else:
        labels = labels_input
        medoids = samplecart_input[medoid_indices]

    return {"centroids": medoids, "labels": labels}


# Density contouring methods (as in mplstereonet), with the labels shown in the stereoplot.
DENSITY_METHODS = {
    "exponential_kamb": "Exponential Kamb (Vollmer 1995)",
    "linear_kamb": "Linear Kamb (Vollmer 1995)",
    "kamb": "Kamb (1959)",
    "schmidt": "Schmidt (1% area)",
}


def kamb_density_grid(
    lons,
    lats,
    sigma=3.0,
    gridsize=100,
    cutoff=30.0,
    max_kernel_n=1000,
    bin_size=0.02,
    method="exponential_kamb",
    axial=True,
):
    """Density of orientation data on a stereonet grid, with the methods of mplstereonet:
    "exponential_kamb" (default) and "linear_kamb" (Vollmer 1995) and "kamb" (Kamb 1959), in
    standard deviations; "schmidt" (count in 1% of the sphere area), in percent.
    lons, lats are stereonet coordinates (e.g. from mplstereonet.line or pole).
    axial=True (axial / bidirectional data): each vector is counted with its opposite (|cos|), as in
    mplstereonet; up to max_kernel_n points the result is the same as mplstereonet.density_grid.
    axial=False (polar / unidirectional data): each vector is counted only as itself.
    The Kamb kernels narrow as the number of points n grows (the exponential one is about 0.5 degrees
    wide for 100k points), below the grid spacing (1.8 degrees for gridsize 100), which gives noisy
    contours: for n > max_kernel_n the kernel and the normalization of max_kernel_n points are used
    and the counts are scaled by max_kernel_n / n, i.e. the expected density of a random sample of
    max_kernel_n points; vectors are then merged in bins of about 1 degree (error < 1% of the
    maximum; the exponential kernel is then cut at exp(-10)). Only counter-point pairs inside the
    kernel (exponential: larger than exp(-cutoff)) are
    evaluated (k-d tree), so the cost grows about linearly with the number of points.
    Returns (lon_grid, lat_grid, density), each gridsize x gridsize."""
    from numpy import add as np_add
    from numpy import concatenate as np_concatenate
    from numpy import finfo as np_finfo
    from numpy import maximum as np_maximum
    from numpy import mgrid as np_mgrid
    from numpy import ones as np_ones
    from numpy import unique as np_unique
    from numpy import zeros as np_zeros
    from scipy.spatial import cKDTree
    from mplstereonet import stereonet_math

    if method not in DENSITY_METHODS:
        raise ValueError(f"Unknown density method: {method}")
    bound = np_pi / 2.0
    lon, lat = np_mgrid[-bound : bound : gridsize * 1j, -bound : bound : gridsize * 1j]
    counters = np_vstack(stereonet_math.sph2cart(lon.ravel(), lat.ravel())).T
    points = np_vstack(
        stereonet_math.sph2cart(np_atleast_1d(lons).ravel(), np_atleast_1d(lats).ravel())
    ).T
    n = float(points.shape[0])
    totals = np_zeros(counters.shape[0], dtype=float)
    if n > 0:
        # Kernel parameters (as mplstereonet), with the number of points capped for the Kamb kernels.
        n_kernel = min(n, float(max_kernel_n)) if (max_kernel_n and method != "schmidt") else n
        if method == "exponential_kamb":
            f = 2.0 * (1.0 + n_kernel / sigma**2)
            units = np_sqrt(n_kernel * (f / 2.0 - 1.0) / f**2)
            min_cos = 1.0 - cutoff / f  # exp(f (cos - 1)) < exp(-cutoff) below this
        elif method in ("linear_kamb", "kamb"):
            kamb_radius = 1.0 - sigma**2 / (n_kernel + sigma**2)
            f = 2.0 / (1.0 - kamb_radius)
            units = np_sqrt(n_kernel * kamb_radius * (1.0 - kamb_radius))
            min_cos = kamb_radius
        else:  # schmidt
            min_cos = 1.0 - 0.01
        weights = np_ones(points.shape[0])
        if max_kernel_n and n > max_kernel_n:
            # merge nearly identical vectors (bins of about 1 degree) and count them
            from numpy import round as np_round

            points, counts = np_unique(np_round(points / bin_size) * bin_size, axis=0, return_counts=True)
            points = points / np_linalg_norm(points, axis=1)[:, None]
            weights = counts.astype(float)
            if method == "exponential_kamb":
                # neglect kernel values below exp(-10) of the peak (error ~0.002% of the maximum)
                min_cos = 1.0 - min(cutoff, 10.0) / f
        # chord**2 = 2 (1 - cos)
        radius = np_sqrt(min(4.0, max(0.0, 2.0 * (1.0 - min_cos)))) + 1e-12
        counters_tree = cKDTree(counters)
        rows, cols, cosines = [], [], []
        for these_points in ((points, -points) if axial else (points,)):
            pairs = counters_tree.sparse_distance_matrix(
                cKDTree(these_points), radius, output_type="ndarray"
            )
            rows.append(pairs["i"])
            cols.append(pairs["j"])
            cosines.append(1.0 - pairs["v"] ** 2 / 2.0)
        rows, cols, cosines = np_concatenate(rows), np_concatenate(cols), np_concatenate(cosines)
        if axial and rows.size and min_cos <= 0:
            # |cos|: a counter-point pair found for the vector and for its opposite counts once,
            # with the larger cosine (as mplstereonet). Only possible with kernels wider than 90
            # degrees (very few points): otherwise the two cannot both be near the same counter.
            keys = rows.astype("int64") * points.shape[0] + cols
            order = (-cosines).argsort(kind="stable")
            _, first = np_unique(keys[order], return_index=True)
            keep = order[first]
            rows, cols, cosines = rows[keep], cols[keep], cosines[keep]
        if method == "exponential_kamb":
            kernel = np_exp(f * (np_maximum(cosines, -1.0) - 1.0))
        elif method == "linear_kamb":
            kernel = np_maximum(f * (cosines - kamb_radius), 0.0) * (cosines >= kamb_radius)
        else:  # kamb, schmidt: counts inside the radius
            kernel = (cosines >= min_cos).astype(float)
        np_add.at(totals, rows, kernel * weights[cols])
        if method == "schmidt":
            totals = totals / (n * 0.01)  # percent of the points in 1% of the area
        else:
            totals *= n_kernel / n
            totals = (totals - 0.5) / units
            totals[totals < 0] = 0
    if method in ("exponential_kamb", "linear_kamb"):
        # Never draw a 0 contour for smoothed densities (as mplstereonet).
        totals[totals == 0] = np_finfo(float).tiny
    counter_lon, counter_lat = stereonet_math.cart2sph(*counters.T)
    shape = lon.shape
    return counter_lon.reshape(shape), counter_lat.reshape(shape), totals.reshape(shape)


def resolve_lower_hemisphere(vectors):
    """
    Ensure all unit vectors in the input array point into the lower hemisphere
    (Z <= 0), by flipping any vector with Z > 0. This is the standard
    preprocessing step for axial data (plane normals) before running statistics
    that assume directional data — it eliminates cancellation in resultant-vector
    sums and ensures consistent orientation across the dataset.

    Parameters
    ----------
    vectors : ndarray, shape (N, 3)
        Sample of unit vectors. Modified in-place is avoided by working on
        a copy — the input array is not altered.

    Returns
    -------
    ndarray, shape (N, 3)
        Same vectors, with any upward-pointing vectors flipped to point downward.
    """
    vectors = np_asarray(vectors, dtype=float)
    if vectors.ndim != 2 or vectors.shape[1] != 3:
        raise ValueError("vectors must have shape (N, 3)")
    resolved = vectors.copy()
    upward = resolved[:, 2] > 0
    resolved[upward] *= -1
    return resolved


def double_axial(vectors):
    """
    Double an axial dataset by appending the antipode of every vector.
    For a dataset of N unit vectors, returns a (2N, 3) array whose second
    half is the element-wise negation of the first half.

    This is used before running k-means on axial data (plane normals):
    by including both poles of every plane, clusters that straddle the
    equator of the stereonet are unified rather than split. After clustering,
    only the labels for the first N rows (the original vectors) are kept —
    the second N rows are discarded.

    Parameters
    ----------
    vectors : ndarray, shape (N, 3)
        Sample of unit vectors, already resolved to the lower hemisphere
        via resolve_lower_hemisphere before being passed here.

    Returns
    -------
    ndarray, shape (2N, 3)
        Original vectors stacked on top of their antipodes.
    """
    vectors = np_asarray(vectors, dtype=float)
    if vectors.ndim != 2 or vectors.shape[1] != 3:
        raise ValueError("vectors must have shape (N, 3)")
    return np_vstack([vectors, -vectors])
