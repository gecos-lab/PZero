"""dxf2vtk.py
PZero Andrea Bistacchi
"""

from copy import deepcopy

import ezdxf

from ezdxf import new as ezdxf_new
from ezdxf.acis import api as acis

from numpy import array as np_array
from numpy import asarray as np_asarray

from pandas import DataFrame as pd_DataFrame

from vtkmodules.util import numpy_support

from pzero.collections.background_collection import BackgroundCollection
from pzero.collections.fluid_collection import FluidCollection
from pzero.collections.geological_collection import GeologicalCollection
from pzero.entities_factory import PolyLine, TriSurf, VertexSet
from pzero.helpers.helper_dialogs import (
    ShapefileAssignmentDialog,
    input_combo_dialog,
    options_dialog,
)

VECTOR_COLLECTIONS = ["Geology", "Fluid contacts", "Background data"]
USER_DEFINED_FEATURE_TOKEN = "__user_defined_feature__"
USER_DEFINED_FEATURE_COLUMN = "__pzero_user_defined_feature__"
FIXED_ROLE_TOKEN = "__fixed_role__"
FIXED_ROLE_COLUMN = "__pzero_fixed_role__"
USER_DEFINED_NAME_TOKEN = "__user_defined_name__"
USER_DEFINED_NAME_COLUMN = "__pzero_user_defined_name__"
USER_DEFINED_SCENARIO_TOKEN = "__user_defined_scenario__"
USER_DEFINED_SCENARIO_COLUMN = "__pzero_user_defined_scenario__"
SOLID_TYPES = {"3DSOLID", "BODY"}
SURFACE_TYPES = {
    "3DFACE",
    "SOLID",
    "TRACE",
    "MESH",
    "REGION",
    "SURFACE",
    "EXTRUDEDSURFACE",
    "LOFTEDSURFACE",
    "REVOLVEDSURFACE",
    "SWEPTSURFACE",
}
CURVE_TYPES = {"ARC", "CIRCLE", "ELLIPSE", "SPLINE"}


def _get_valid_roles_for_collection(collection):
    if collection == "Geology":
        return GeologicalCollection().valid_roles
    if collection == "Fluid contacts":
        return FluidCollection().valid_roles
    if collection == "Background data":
        return BackgroundCollection().valid_roles
    return ["undef"]


def _get_target_collection(self, collection):
    if collection == "Geology":
        return self.geol_coll, GeologicalCollection().entity_dict
    if collection == "Fluid contacts":
        return self.fluid_coll, FluidCollection().entity_dict
    if collection == "Background data":
        return self.backgrnd_coll, BackgroundCollection().entity_dict
    return None, None


def _unique_column_name(df, base_name):
    column_name = base_name
    while column_name in df.columns:
        column_name = f"_{column_name}"
    return column_name


def _normalize_point(point, default_z=0.0):
    if hasattr(point, "x"):
        return [float(point.x), float(point.y), float(getattr(point, "z", default_z))]

    coords = list(point)
    if len(coords) == 2:
        coords.append(default_z)
    return [float(coords[0]), float(coords[1]), float(coords[2])]


def _point_entity_location_wcs(entity):
    try:
        return entity.ocs().to_wcs(entity.dxf.location)
    except Exception:
        return entity.dxf.location


def _clean_face_vertices(vertices):
    cleaned = []
    for vertex in vertices:
        xyz = _normalize_point(vertex)
        if not cleaned or xyz != cleaned[-1]:
            cleaned.append(xyz)
    if len(cleaned) > 1 and cleaned[0] == cleaned[-1]:
        cleaned.pop()
    return cleaned


def _build_vertex_set(points):
    if not points:
        return None
    vtk_obj = VertexSet()
    vtk_obj.points = np_array([_normalize_point(point) for point in points], dtype=float)
    vtk_obj.auto_cells()
    return vtk_obj if vtk_obj.points_number > 0 else None


def _build_polyline(points, closed=False):
    out_points = [_normalize_point(point) for point in points]
    if closed and len(out_points) > 1 and out_points[0] != out_points[-1]:
        out_points.append(out_points[0])
    if len(out_points) < 2:
        return None
    vtk_obj = PolyLine()
    vtk_obj.points = np_array(out_points, dtype=float)
    vtk_obj.auto_cells()
    return vtk_obj if vtk_obj.points_number > 1 else None


def _build_trisurf(face_vertices_list):
    points = []
    point_ids = {}
    cells = []

    for face_vertices in face_vertices_list:
        clean_face = _clean_face_vertices(face_vertices)
        if len(clean_face) < 3:
            continue

        face_ids = []
        for point in clean_face:
            key = tuple(point)
            if key not in point_ids:
                point_ids[key] = len(points)
                points.append(point)
            face_ids.append(point_ids[key])

        for idx in range(1, len(face_ids) - 1):
            cells.append([face_ids[0], face_ids[idx], face_ids[idx + 1]])

    if not cells:
        return None

    vtk_obj = TriSurf()
    vtk_obj.points = np_array(points, dtype=float)
    for cell in cells:
        vtk_obj.append_cell(np_array(cell, dtype=int))
    return vtk_obj


def _get_acis_bodies(entity):
    try:
        return acis.load_dxf(entity)
    except Exception:
        return []


def _flatten_curve(entity):
    try:
        points = list(entity.flattening(0.1))
    except Exception:
        return None
    return _build_polyline(points, closed=entity.dxftype() == "CIRCLE")


def _build_polyline_from_entity(entity):
    entity_type = entity.dxftype()

    if entity_type == "LINE":
        return _build_polyline([entity.dxf.start, entity.dxf.end])

    if entity_type == "LWPOLYLINE":
        points = list(entity.vertices_in_wcs())
        return _build_polyline(points, closed=entity.closed)

    if entity_type == "POLYLINE":
        return _build_polyline(list(entity.points()), closed=entity.is_closed)

    if entity_type in CURVE_TYPES:
        return _flatten_curve(entity)

    return None


def _face_vertices_from_entity(entity):
    entity_type = entity.dxftype()

    if entity_type in {"3DFACE", "TRACE", "SOLID"}:
        vertices = [entity.dxf.vtx0, entity.dxf.vtx1, entity.dxf.vtx2]
        if hasattr(entity.dxf, "vtx3"):
            vertices.append(entity.dxf.vtx3)
        return [_clean_face_vertices(vertices)]

    if entity_type == "MESH":
        vertices = [_normalize_point(vertex) for vertex in entity.vertices]
        return [[vertices[int(index)] for index in face] for face in entity.faces]

    if entity_type == "POLYLINE" and entity.get_mode() == "AcDbPolyFaceMesh":
        return [
            [vertex.dxf.location for vertex in face]
            for face in entity.faces()
        ]

    if entity_type == "POLYLINE" and entity.get_mode() == "AcDbPolygonMesh":
        faces = []
        for virtual_entity in entity.virtual_entities():
            if virtual_entity.dxftype() == "3DFACE":
                faces.extend(_face_vertices_from_entity(virtual_entity))
        return faces

    if entity_type in SOLID_TYPES | (SURFACE_TYPES - {"3DFACE", "SOLID", "TRACE", "MESH"}):
        faces = []
        for body in _get_acis_bodies(entity):
            try:
                meshes = acis.mesh_from_body(body)
            except Exception:
                continue
            for mesh in meshes:
                vertices = [_normalize_point(vertex) for vertex in mesh.vertices]
                for face in mesh.faces:
                    faces.append([vertices[int(index)] for index in face])
        return faces

    return []


def _make_record(entity, topology, vtk_obj):
    layer = getattr(entity.dxf, "layer", "0")
    handle = getattr(entity.dxf, "handle", "")
    entity_type = entity.dxftype()
    parts = [str(layer), entity_type.lower()]
    if handle:
        parts.append(str(handle))

    return {
        "name": "_".join(parts),
        "layer": str(layer),
        "entity_type": entity_type,
        "handle": str(handle),
        "topology": topology,
        "vtk_obj": vtk_obj,
    }


def _collect_records_from_entity(entity, records, skipped):
    entity_type = entity.dxftype()

    if entity_type == "POINT":
        vtk_obj = _build_vertex_set([_point_entity_location_wcs(entity)])
        if vtk_obj is not None:
            records.append(_make_record(entity, "VertexSet", vtk_obj))
        return

    if entity_type in {"LINE", "LWPOLYLINE"} | CURVE_TYPES:
        vtk_obj = _build_polyline_from_entity(entity)
        if vtk_obj is not None:
            records.append(_make_record(entity, "PolyLine", vtk_obj))
        return

    if entity_type == "POLYLINE":
        mode = entity.get_mode()
        if mode in {"AcDb2dPolyline", "AcDb3dPolyline"}:
            vtk_obj = _build_polyline_from_entity(entity)
            if vtk_obj is not None:
                records.append(_make_record(entity, "PolyLine", vtk_obj))
            return

        if mode in {"AcDbPolyFaceMesh", "AcDbPolygonMesh"}:
            vtk_obj = _build_trisurf(_face_vertices_from_entity(entity))
            if vtk_obj is not None:
                records.append(_make_record(entity, "TriSurf", vtk_obj))
            return

    if entity_type in SURFACE_TYPES:
        vtk_obj = _build_trisurf(_face_vertices_from_entity(entity))
        if vtk_obj is not None:
            records.append(_make_record(entity, "TriSurf", vtk_obj))
            return

    if entity_type in SOLID_TYPES:
        vtk_obj = _build_trisurf(_face_vertices_from_entity(entity))
        if vtk_obj is not None:
            records.append(_make_record(entity, "TriSurf", vtk_obj))
            return

    if hasattr(entity, "virtual_entities"):
        try:
            virtual_entities = list(entity.virtual_entities())
        except Exception:
            virtual_entities = []
        if virtual_entities:
            for virtual_entity in virtual_entities:
                _collect_records_from_entity(virtual_entity, records, skipped)
            return

    skipped[entity_type] = skipped.get(entity_type, 0) + 1


def _apply_manual_mapping(attrs_df, attribute_mapping):
    attrs_df = attrs_df.copy()
    attribute_mapping = dict(attribute_mapping)

    if attribute_mapping.get("feature") == USER_DEFINED_FEATURE_TOKEN:
        column_name = _unique_column_name(attrs_df, USER_DEFINED_FEATURE_COLUMN)
        attrs_df[column_name] = str(
            attribute_mapping.get("feature_user_value", "undef")
        ).strip() or "undef"
        attribute_mapping["feature"] = column_name

    if attribute_mapping.get("role") == FIXED_ROLE_TOKEN:
        column_name = _unique_column_name(attrs_df, FIXED_ROLE_COLUMN)
        attrs_df[column_name] = str(
            attribute_mapping.get("role_fixed_value", "undef")
        ).strip() or "undef"
        attribute_mapping["role"] = column_name

    if attribute_mapping.get("name") == USER_DEFINED_NAME_TOKEN:
        column_name = _unique_column_name(attrs_df, USER_DEFINED_NAME_COLUMN)
        attrs_df[column_name] = str(
            attribute_mapping.get("name_user_value", "undef")
        ).strip() or "undef"
        attribute_mapping["name"] = column_name

    if attribute_mapping.get("scenario") == USER_DEFINED_SCENARIO_TOKEN:
        column_name = _unique_column_name(attrs_df, USER_DEFINED_SCENARIO_COLUMN)
        attrs_df[column_name] = str(
            attribute_mapping.get("scenario_user_value", "undef")
        ).strip() or "undef"
        attribute_mapping["scenario"] = column_name

    return attrs_df, attribute_mapping


def _validate_roles(self, attrs_df, props_map, collection):
    role_column = props_map.get("role")
    if not role_column or role_column not in attrs_df.columns:
        return True

    valid_roles = _get_valid_roles_for_collection(collection)
    invalid_mask = ~attrs_df[role_column].isin(valid_roles)
    invalid_count = int(invalid_mask.sum())
    if invalid_count == 0:
        return True

    attrs_df.loc[invalid_mask, role_column] = "undef"
    choice = options_dialog(
        title="Invalid roles found",
        message=(
            f"{invalid_count} entities have been assigned role 'undef' "
            f"(invalid role for {collection}).\nContinue with import or Cancel?"
        ),
        yes_role="Continue",
        no_role="Cancel",
    )
    return choice == 0


def _import_vector_records(self, records, topology, collection):
    attrs_df = pd_DataFrame(
        [
            {
                "name": record["name"],
                "layer": record["layer"],
                "entity_type": record["entity_type"],
                "handle": record["handle"],
            }
            for record in records
        ]
    )

    dialog = ShapefileAssignmentDialog(
        parent=self,
        shapefile_df=attrs_df,
        topology_type="Point" if topology == "VertexSet" else "PolyLine",
        include_label=collection == "Background data",
        valid_roles=_get_valid_roles_for_collection(collection),
    )
    attribute_mapping = dialog.exec()
    if attribute_mapping is None:
        self.print_terminal(f"{topology} import cancelled by user.")
        return 0

    attrs_df, attribute_mapping = _apply_manual_mapping(attrs_df, attribute_mapping)

    props_allowed = {"name", "role", "feature"}
    if collection in {"Geology", "Fluid contacts"}:
        props_allowed.add("scenario")
    if collection == "Background data":
        props_allowed.add("label")
    props_map = {
        key: value for key, value in attribute_mapping.items() if key in props_allowed
    }

    if not _validate_roles(self, attrs_df, props_map, collection):
        self.print_terminal(f"{topology} import cancelled because of invalid roles.")
        return 0

    out_coll, entity_template = _get_target_collection(self, collection)
    imported_count = 0

    for idx, record in enumerate(records):
        curr_obj_dict = deepcopy(entity_template)
        for key, column in props_map.items():
            if column in attrs_df.columns and key in curr_obj_dict:
                curr_obj_dict[key] = attrs_df.loc[idx, column]
        curr_obj_dict["topology"] = topology
        curr_obj_dict["vtk_obj"] = record["vtk_obj"]

        if collection == "Background data":
            label_column = props_map.get("label")
            if label_column and hasattr(curr_obj_dict["vtk_obj"], "set_field_data"):
                curr_obj_dict["vtk_obj"].set_field_data(
                    name="name", data=np_asarray([attrs_df.loc[idx, label_column]])
                )

        out_coll.add_entity_from_dict(curr_obj_dict)
        imported_count += 1

    self.print_terminal(
        f"Imported {imported_count} DXF {topology} entities into {collection}."
    )
    return imported_count


def dxf2vtk(self=None, in_file_name=None):
    """Import a DXF file as VertexSet, PolyLine, and TriSurf entities."""
    if not in_file_name:
        return

    ezdxf.options.load_proxy_graphics = True
    doc = ezdxf.readfile(in_file_name)

    records = []
    skipped = {}
    for entity in doc.modelspace():
        _collect_records_from_entity(entity, records, skipped)

    if not records:
        self.print_terminal("No supported DXF entities found.")
        return

    imported_count = 0
    for topology in ("VertexSet", "PolyLine", "TriSurf"):
        topology_records = [
            record for record in records if record["topology"] == topology
        ]
        if not topology_records:
            continue

        collection = input_combo_dialog(
            parent=self,
            title="Collection",
            label=f"Assign {topology} entities",
            choice_list=VECTOR_COLLECTIONS,
        )
        if not collection:
            self.print_terminal(f"Skipped DXF {topology} entities.")
            continue

        imported_count += _import_vector_records(
            self=self,
            records=topology_records,
            topology=topology,
            collection=collection,
        )

    self.print_terminal(
        f"DXF import complete: {imported_count}/{len(records)} entities imported."
    )

    if skipped:
        skipped_msg = ", ".join(
            f"{entity_type} ({count})" for entity_type, count in sorted(skipped.items())
        )
        self.print_terminal(f"Unsupported DXF entities skipped: {skipped_msg}")


def vtk2dxf(self=None, out_dir_name=None):
    """Exports all triangulated surfaces to a collection of DXF 3DFACE objects and border polyline3d."""
    # Create DXF container.
    # Add entities.
    list_uids = []
    list_names = []
    for uid in self.geol_coll.df["uid"]:
        if isinstance(self.geol_coll.get_uid_vtk_obj(uid), TriSurf):
            legend = self.geol_coll.get_uid_legend(uid=uid)
            R = legend["color_R"]
            G = legend["color_G"]
            B = legend["color_B"]
            parts = self.geol_coll.get_uid_vtk_obj(uid).split_parts()
            for i, part in enumerate(parts):
                dxf_out = ezdxf_new()
                dxf_model = dxf_out.modelspace()
                df = pd_DataFrame()
                dfb = pd_DataFrame()
                vtk_entity = part

                layer = f'{self.geol_coll.df.loc[self.geol_coll.df["uid"] == uid, "feature"].values[0]}'
                layer_b = f"{layer}_boundary"

                xyz = numpy_support.vtk_to_numpy(vtk_entity.GetPoints().GetData())

                df["x"] = xyz[:, 0]
                df["y"] = xyz[:, 1]
                df["z"] = xyz[:, 2]

                dxf_out.layers.add(name=layer)
                dxf_out.layers.add(name=layer_b)

                surf_layer = dxf_out.layers.get(layer)
                surf_layer.rgb = (R, G, B)

                boun_layer = dxf_out.layers.get(layer_b)
                boun_layer.rgb = (R, G, B)

                for c in range(vtk_entity.GetNumberOfCells()):
                    face_points = numpy_support.vtk_to_numpy(
                        vtk_entity.GetCell(c).GetPoints().GetData()
                    )
                    if len(face_points) < 3:
                        print(f"problem with cell {c} in {layer}, skipping cell")
                    else:
                        dxf_model.add_3dface(
                            face_points, dxfattribs={"layer": layer, "color": 256}
                        )

                vtk_border = vtk_entity.get_clean_boundary()

                xyz_b = numpy_support.vtk_to_numpy(vtk_border.GetPoints().GetData())
                dfb["x"] = xyz_b[:, 0]
                dfb["y"] = xyz_b[:, 1]
                dfb["z"] = xyz_b[:, 2]

                for cell in range(vtk_border.GetNumberOfCells()):
                    border_points = numpy_support.vtk_to_numpy(
                        vtk_border.GetCell(cell).GetPoints().GetData()
                    )
                    dxf_model.add_polyline3d(
                        border_points, dxfattribs={"layer": layer_b, "color": 256}
                    )
                if len(parts) > 1:
                    out_file_name = f"{uid}_{layer}_part{i}"
                    list_uids.append(uid)
                    list_names.append(f"{layer}_part{i}")
                else:
                    out_file_name = f"{uid}_{layer}"
                    list_uids.append(uid)
                    list_names.append(layer)

                df.to_csv(f"{out_dir_name}/csv/{out_file_name}.csv", index=False)
                dfb.to_csv(
                    f"{out_dir_name}/csv/{out_file_name}_border.csv", index=False
                )

                dxf_out.saveas(f"{out_dir_name}/dxf/{out_file_name}.dxf")

    for uid in self.boundary_coll.df["uid"]:
        if isinstance(self.boundary_coll.get_uid_vtk_obj(uid), TriSurf):
            layer = (
                uid
                + "_"
                + self.boundary_coll.df.loc[
                    self.boundary_coll.df["uid"] == uid, "name"
                ].values[0]
            )
            vtk_entity = self.boundary_coll.get_uid_vtk_obj(uid)
            for i in range(vtk_entity.GetNumberOfCells()):
                face_points = numpy_support.vtk_to_numpy(
                    vtk_entity.GetCell(i).GetPoints().GetData()
                )
                dxf_model.add_3dface(face_points, dxfattribs={"layer": layer})
            print("entity exported\n")
    for uid in self.well_coll.df["uid"]:
        legend = self.well_coll.get_uid_legend(uid=uid)
        vtk_entity = self.well_coll.get_uid_vtk_obj(uid)
        R = legend["color_R"]
        G = legend["color_G"]
        B = legend["color_B"]
        dxf_out = ezdxf_new()
        dxf_model = dxf_out.modelspace()
        df = pd_DataFrame()
        layer = f'{self.well_coll.df.loc[self.well_coll.df["uid"] == uid, "feature"].values[0]}'

        xyz = numpy_support.vtk_to_numpy(vtk_entity.GetPoints().GetData())

        df["x"] = xyz[:, 0]
        df["y"] = xyz[:, 1]
        df["z"] = xyz[:, 2]

        dxf_out.layers.add(name=layer)

        line_layer = dxf_out.layers.get(layer)
        line_layer.rgb = (R, G, B)

        for cell in range(vtk_entity.GetNumberOfCells()):
            line_points = numpy_support.vtk_to_numpy(
                vtk_entity.GetCell(cell).GetPoints().GetData()
            )
            dxf_model.add_polyline3d(
                line_points, dxfattribs={"layer": layer, "color": 256}
            )

        out_file_name = f"{uid}_{layer}"
        list_uids.append(uid)
        list_names.append(layer)

        df.to_csv(f"{out_dir_name}/csv/{out_file_name}.csv", index=False)

        dxf_out.saveas(f"{out_dir_name}/dxf/{out_file_name}.dxf")

    complete_list = pd_DataFrame({"uids": list_uids, "features": list_names})
    complete_list.to_csv(f"{out_dir_name}/exported_object_list.csv", index=False)
