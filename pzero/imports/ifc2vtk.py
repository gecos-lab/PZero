"""ifc2vtk.py
PZero© Andrea Bistacchi

Minimal IFC export helpers for selected PZero objects.
"""

from __future__ import annotations

from os import path as os_path

from numpy import asarray as np_asarray

from pzero.entities_factory import TetraSolid, TriSurf


def _ensure_ifc_extension(out_file_name: str) -> str:
    """Append the IFC extension if the user omitted it in the save dialog."""
    if out_file_name.lower().endswith(".ifc"):
        return out_file_name
    return out_file_name + ".ifc"


def _trisurf_payload(vtk_obj: TriSurf) -> tuple[list[list[float]], list[list[int]]]:
    """Convert a TriSurf into IFC-compatible vertices and triangle indices."""
    vertices = np_asarray(vtk_obj.points, dtype=float)
    faces = np_asarray(vtk_obj.cells, dtype=int)
    return vertices.tolist(), (faces + 1).tolist()


def _mesh_payload(vtk_obj) -> tuple[list[list[float]], list[list[int]]]:
    """
    Convert a supported mesh entity into a triangulated outer surface suitable for IFC export.

    Mesh3D objects are exported as closed tessellations by extracting the visible boundary surface.
    """
    import pyvista as pv

    surface = pv.wrap(vtk_obj).extract_surface().triangulate()
    vertices = np_asarray(surface.points, dtype=float)
    if vertices.size == 0 or surface.n_cells == 0:
        return [], []

    faces = np_asarray(surface.faces, dtype=int).reshape(-1, 4)[:, 1:4]
    return vertices.tolist(), (faces + 1).tolist()


def _collect_export_items(self=None) -> list[dict]:
    """Collect supported selected objects from the active table for IFC export."""
    items = []
    collection_key = self.selected_collection

    if collection_key == "geol_coll":
        collection = self.geol_coll
        for uid in self.selected_uids:
            vtk_obj = collection.get_uid_vtk_obj(uid)
            if not isinstance(vtk_obj, TriSurf):
                self.print_terminal(
                    f"IFC export skipped geology uid {uid}: only TriSurf is supported in the first spike."
                )
                continue

            vertices, faces = _trisurf_payload(vtk_obj)
            if not vertices or not faces:
                self.print_terminal(
                    f"IFC export skipped geology uid {uid}: empty or invalid TriSurf."
                )
                continue

            items.append(
                {
                    "uid": uid,
                    "name": collection.get_uid_name(uid) or uid,
                    "closed": False,
                    "vertices": vertices,
                    "faces": faces,
                }
            )

    elif collection_key == "mesh3d_coll":
        collection = self.mesh3d_coll
        for uid in self.selected_uids:
            vtk_obj = collection.get_uid_vtk_obj(uid)
            if not isinstance(vtk_obj, TetraSolid):
                self.print_terminal(
                    f"IFC export skipped mesh uid {uid}: only TetraSolid is supported in the first spike."
                )
                continue

            vertices, faces = _mesh_payload(vtk_obj)
            if not vertices or not faces:
                self.print_terminal(
                    f"IFC export skipped mesh uid {uid}: unable to extract a valid outer surface."
                )
                continue

            items.append(
                {
                    "uid": uid,
                    "name": collection.get_uid_name(uid) or uid,
                    "closed": True,
                    "vertices": vertices,
                    "faces": faces,
                }
            )
    else:
        self.print_terminal(
            "IFC export is currently available only from the Geology and Meshes tables."
        )

    return items


def vtk2ifc(self=None, out_file_name: str | None = None) -> bool:
    """
    Export selected geological TriSurf or mesh entities to a minimal IFC4X3 file.

    Geological TriSurfs are exported as open tessellations (Closed = FALSE).
    Mesh collection items are exported as closed tessellations (Closed = TRUE) when
    a valid outer triangulated surface can be extracted.
    """
    if not self.selected_uids:
        self.print_terminal("IFC export requires at least one selected object.")
        return False

    if not out_file_name:
        self.print_terminal("IFC export aborted: no output path selected.")
        return False

    try:
        import ifcopenshell
        import ifcopenshell.api.context
        import ifcopenshell.api.geometry
        import ifcopenshell.api.root
        import ifcopenshell.api.unit
    except ImportError:
        self.print_terminal(
            "IFC export requires IfcOpenShell. Install it first and restart PZero."
        )
        return False

    export_items = _collect_export_items(self=self)
    if not export_items:
        self.print_terminal("IFC export aborted: no supported selected objects found.")
        return False

    out_file_name = _ensure_ifc_extension(out_file_name)

    model = ifcopenshell.file(schema="IFC4X3_ADD2")
    ifcopenshell.api.root.create_entity(
        model,
        ifc_class="IfcProject",
        name="PZero IFC Export",
    )

    # Use explicit metre-based defaults so PZero coordinates pass through unchanged.
    length = ifcopenshell.api.unit.add_si_unit(model, unit_type="LENGTHUNIT")
    area = ifcopenshell.api.unit.add_si_unit(model, unit_type="AREAUNIT")
    volume = ifcopenshell.api.unit.add_si_unit(model, unit_type="VOLUMEUNIT")
    ifcopenshell.api.unit.assign_unit(model, units=[length, area, volume])

    model_context = ifcopenshell.api.context.add_context(model, context_type="Model")
    body_context = ifcopenshell.api.context.add_context(
        model,
        context_type="Model",
        context_identifier="Body",
        target_view="MODEL_VIEW",
        parent=model_context,
    )

    for item in export_items:
        element = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcBuildingElementProxy",
            name=item["name"],
        )
        ifcopenshell.api.geometry.edit_object_placement(model, product=element)

        point_list = model.create_entity(
            "IfcCartesianPointList3D",
            CoordList=item["vertices"],
        )
        face_set = model.create_entity(
            "IfcTriangulatedFaceSet",
            Coordinates=point_list,
            CoordIndex=item["faces"],
            Closed=item["closed"],
        )
        representation = model.create_entity(
            "IfcShapeRepresentation",
            ContextOfItems=body_context,
            RepresentationIdentifier="Body",
            RepresentationType="Tessellation",
            Items=[face_set],
        )
        ifcopenshell.api.geometry.assign_representation(
            model,
            product=element,
            representation=representation,
        )

    model.write(out_file_name)
    self.print_terminal(
        f"IFC4X3 export completed: {len(export_items)} object(s) written to {os_path.basename(out_file_name)}"
    )
    return True
