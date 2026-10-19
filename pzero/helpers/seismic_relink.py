"""Migrate legacy interpretation coordinates when their seismic parent is relinked.

The legacy coordinate frame is reconstructed from source headers, never inferred
from interpretation bounds. All copies are prepared before the collection changes.
"""
from copy import deepcopy
from pathlib import Path
import numpy as np
from vtk import vtkPoints, vtkStringArray
from vtkmodules.util.numpy_support import numpy_to_vtk, vtk_to_numpy

from pzero.imports.segy_reader import (
    DEFAULT_HEADERS, SegyImportOptions, file_identity, get_seismic_metadata,
    inspect_segy, prepare_geometry, set_seismic_metadata,
)


def _string(obj, name):
    value = obj.GetFieldData().GetAbstractArray(name)
    return value.GetValue(0) if value is not None and value.GetNumberOfValues() else None


def _set_string(obj, name, value):
    array = vtkStringArray()
    array.SetName(name)
    array.InsertNextValue(value)
    obj.GetFieldData().RemoveArray(name)
    obj.GetFieldData().AddArray(array)


def _physical_recipe(metadata):
    recipe = dict(metadata.get("import_options", {}))
    for key in ("name", "endian", "headers", "header_widths"):
        recipe.pop(key, None)
    return recipe


def _is_legacy_time_reference(obj):
    """Recognize the explicit coordinate recipe of historical reference horizons.

    These imported references stored physical TWT * -125, unlike the old
    seismic grid's sample-index linspace. Do not evaluate arbitrary field text.
    """
    return obj is not None and (
        _string(obj, "coordinate_frame") == "PZero segy2vtk raw SEG-Y headers"
        and _string(obj, "xy_transform") == "x_raw = x * 100; y_raw = y * 100"
        and _string(obj, "z_transform") == "z = -125 * source_twt_ms"
    )


class LegacySeismicTransform:
    """Header-only reconstruction of the original raw-XY and /8 Z frame."""

    def __init__(self, target):
        self.metadata = get_seismic_metadata(target)
        path = self.metadata.get("source_file", "")
        if not path or not Path(path).is_file():
            raise ValueError("Legacy coordinate migration needs the original SEG-Y. Reimport it from its current location first.")
        if file_identity(path) != self.metadata.get("source_identity"):
            raise ValueError("The source SEG-Y changed since import. Reimport it before migrating interpretations.")
        options = SegyImportOptions(**self.metadata["import_options"])
        survey = inspect_segy(path, options.endian, options.headers, options.header_widths)
        original = inspect_segy(path, headers=DEFAULT_HEADERS)
        geometry = prepare_geometry(survey, options)
        self.options = options
        self.input_origin = geometry["sample_origin"]
        self.input_step = geometry["sample_step"]
        ni, nx, ns = geometry["dimensions"]
        dims = [0, 0, 0]
        target.GetDimensions(dims)
        if tuple(dims) != (ni, nx, ns):
            raise ValueError("The imported seismic dimensions changed; migration requires the reviewed import geometry.")
        if geometry["missing_bins"]:
            raise ValueError("Legacy migration requires the same complete source survey used by the old importer.")
        old_x = int(np.count_nonzero(original["inline"] == original["inline"][0]))
        old_y = int(np.count_nonzero(original["crossline"] == original["crossline"][0]))
        if old_x * old_y != survey["trace_count"] or min(old_x, old_y) < 2:
            raise ValueError("Source headers cannot reproduce the old importer grid. Use the original, unmodified source SEG-Y.")
        grid_ids = geometry["grid_ids"]
        indices = (grid_ids % ni, grid_ids // ni)
        parameters = geometry["axis_parameters"]
        design = np.column_stack((np.ones(len(grid_ids)), parameters[0][indices[0]], parameters[1][indices[1]]))
        raw_xy = np.column_stack((original["x"], original["y"])).astype(float)
        fit, _, rank, _ = np.linalg.lstsq(design, raw_xy, rcond=None)
        if rank != 3 or abs(np.linalg.det(fit[1:])) < 1e-9:
            raise ValueError("Legacy source navigation cannot be reconstructed.")
        residual = np.linalg.norm(design @ fit - raw_xy, axis=1)
        if residual.max() > max(2, .04 * np.linalg.norm(fit[1:], axis=1).min()):
            raise ValueError("Source navigation is inconsistent with the legacy importer coordinate frame.")
        self.source_origin, self.source_basis = fit[0], fit[1:]
        self.parameter_limits = np.array([parameters[0][-1], parameters[1][-1]])
        # Read the actual target frame and verify it has not been edited since import.
        target_xy = np.array([target.GetPoint(k)[:2] for k in (0, 1, ni, ni * nx - 1)])
        if not np.allclose(target_xy, geometry["xy"][[0, 1, ni, ni * nx - 1]], atol=.01, rtol=0):
            raise ValueError("Target navigation has been edited since import. Reimport before legacy migration.")
        self.target_origin = target_xy[0]
        self.target_basis = np.array([target_xy[1] - target_xy[0], target_xy[2] - target_xy[0]])
        self.source_z = np.linspace(-ns * original["sample_interval_us"] / 8.0, 0, ns)
        target_z = np.array([target.GetPoint(k * ni * nx)[2] for k in range(ns)])
        if not np.allclose(target_z, geometry["z"], atol=1e-8, rtol=1e-10):
            raise ValueError("Target sampling has been edited since import. Reimport before legacy migration.")
        by_source_sample = np.empty(ns)
        by_source_sample[geometry["sample_order"]] = target_z
        self.target_z = by_source_sample[::-1]
        self.axis_maps = {}
        # File-order legacy X/Y indices can be transposed or reversed relative
        # to canonical inline/crossline indices. Preserve the actual trace link.
        used = set()
        for old_axis, old_name in enumerate(("Inline", "Crossline")):
            for new_axis, new_name in enumerate(("Inline", "Crossline")):
                values = indices[new_axis].reshape(old_y, old_x)
                mapping = values[0, :] if old_axis == 0 else values[:, 0]
                expected = np.broadcast_to(mapping[None, :] if old_axis == 0 else mapping[:, None], values.shape)
                if len(np.unique(mapping)) > 1 and np.array_equal(values, expected):
                    self.axis_maps[old_name] = (new_name, mapping.copy())
                    used.add(new_name)
                    break
        if len(used) != 2:
            raise ValueError("Source trace order cannot reproduce legacy slice axes.")
        inverse_samples = np.argsort(geometry["sample_order"])
        self.axis_maps["Z-slice"] = ("Z-slice", inverse_samples[::-1])

    def points(self, points, allow_extensions=False):
        points = np.asarray(points, dtype=float)
        if not len(points):
            return points.copy()
        if not np.all(np.isfinite(points)):
            raise ValueError("Interpretation contains non-finite coordinates.")
        parameters = np.linalg.solve(self.source_basis.T, (points[:, :2] - self.source_origin).T).T
        # Permit modest interpretation extensions but reject unrelated surveys
        # and already-scaled objects with no reliable provenance.
        margin = np.maximum(2, .1 * self.parameter_limits)
        if np.any(parameters < -margin) or np.any(parameters > self.parameter_limits + margin):
            raise ValueError("Interpretation XY does not match this SEG-Y's legacy frame. No coordinates or links were changed.")
        tolerance = max(.01, np.ptp(self.source_z) * 1e-5)
        outside = (points[:, 2] < self.source_z[0] - tolerance) | (points[:, 2] > self.source_z[-1] + tolerance)
        if outside.any() and not allow_extensions:
            raise ValueError("Interpretation Z is outside the legacy sample range. Verify the source seismic before linking.")
        result = np.empty_like(points)
        result[:, :2] = self.target_origin + parameters @ self.target_basis
        if self.options.depth_model == "table":
            # Evaluate the supplied model at each point's actual sample time,
            # including knots between recorded samples and model extensions.
            sample_index = -points[:, 2] / -self.source_z[0] * (len(self.source_z) - 1)
            times = (self.input_origin + sample_index * self.input_step) * (.001 if self.options.vertical_units == "ms" else 1)
            times -= self.options.model_time_datum_s
            table = np.asarray(self.options.time_depth_table, dtype=float)
            if times.min() < table[0, 0] - 1e-12 or times.max() > table[-1, 0] + 1e-12:
                raise ValueError("The time-depth table does not cover the extended model surfaces or interpretation lines. Extend the model's valid coverage or import in time.")
            result[:, 2] = self.options.depth_datum_m - np.interp(times, table[:, 0], table[:, 1])
        else:
            # Native time/depth and constant velocity are affine. Preserve all
            # extensions, including those within the validation tolerance.
            slope = (self.target_z[-1] - self.target_z[0]) / (self.source_z[-1] - self.source_z[0])
            result[:, 2] = self.target_z[0] + (points[:, 2] - self.source_z[0]) * slope
        return result

    def reference_points(self, points):
        """Map explicitly recorded TWT reference coordinates through the import."""
        if self.options.domain != "twt" or self.options.vertical_units not in ("ms", "s"):
            raise ValueError("Legacy TWT reference horizons require a TWT source import (which may then be converted to depth).")
        legacy = np.asarray(points, dtype=float).copy()
        time_ms = -legacy[:, 2] / 125.0
        source_time = time_ms if self.options.vertical_units == "ms" else time_ms / 1000.0
        sample_index = (source_time - self.input_origin) / self.input_step
        legacy[:, 2] = sample_index * self.source_z[0] / (len(self.source_z) - 1)
        return self.points(legacy, allow_extensions=True)

    def remap_slices(self, obj):
        if obj.GetNumberOfPolys():
            # Triangles span slices. Historical surface builders/filtering may
            # have left inconsistent line slice tags; retain them for audit but
            # never classify the mesh as a multipart interpretation line.
            fields = obj.GetFieldData()
            for name in ("slice_axis", "single_slice_axis", "single_slice_index"):
                value = fields.GetAbstractArray(name)
                if value is not None:
                    backup = value.NewInstance()
                    backup.DeepCopy(value)
                    backup.SetName("pzero_legacy_" + name)
                    fields.AddArray(backup)
                    fields.RemoveArray(name)
            return
        for axis_key, single in (("slice_axis", False), ("single_slice_axis", True)):
            old_axis = _string(obj, axis_key)
            if old_axis is None:
                continue
            if old_axis not in self.axis_maps:
                raise ValueError(f"Unknown legacy slice axis: {old_axis}")
            new_axis, mapping = self.axis_maps[old_axis]
            containers = [obj.GetFieldData()] if single else [obj.GetPointData(), obj.GetCellData()]
            for container in containers:
                for index in range(container.GetNumberOfArrays()):
                    array = container.GetArray(index)
                    if array is None:
                        continue
                    name = array.GetName() or ""
                    if name != ("single_slice_index" if single else "slice_index") and not (not single and name.startswith("slices_")):
                        continue
                    backup = array.NewInstance()
                    backup.DeepCopy(array)
                    kind = "field" if single else "point" if container is obj.GetPointData() else "cell"
                    backup.SetName(f"pzero_legacy_{kind}_{name}")
                    obj.GetFieldData().AddArray(backup)
                    values = vtk_to_numpy(array)
                    ids = np.rint(values).astype(int)
                    if not np.allclose(values, ids) or np.any(ids < 0) or np.any(ids >= len(mapping)):
                        raise ValueError("Stored slice indices are outside the legacy source grid.")
                    values[:] = mapping[ids]
                    array.Modified()
            _set_string(obj, axis_key, new_axis)


def prepare_relinked_interpretations(objects, target, old_uid, new_uid, derived_sources=None):
    """Return independent migrated copies; failure leaves every original intact."""
    derived_sources = derived_sources or {}
    target_metadata = get_seismic_metadata(target)
    if target_metadata.get("schema_version", 0) < 1:
        return {}  # Same legacy link-only behaviour when the target is legacy.
    transform = None
    replacements = {}
    for uid, original in objects.items():
        if original is None or not hasattr(original, "GetPoints") or original.GetPoints() is None:
            raise ValueError(f"Interpretation {uid} has no point geometry to align.")
        metadata = get_seismic_metadata(original)
        if metadata.get("schema_version", 0) >= 1:
            if (metadata.get("source_identity") != target_metadata.get("source_identity")
                    or _physical_recipe(metadata) != _physical_recipe(target_metadata)):
                raise ValueError("This interpretation already has physical coordinates from different import settings. Use a matching seismic import.")
            continue  # Already migrated: changing the UID must not apply scaling again.
        if transform is None:
            transform = LegacySeismicTransform(target)
        copy = original.NewInstance()
        copy.DeepCopy(original)
        old_points = vtk_to_numpy(original.GetPoints().GetData())
        is_reference = _is_legacy_time_reference(original)
        if _string(original, "coordinate_frame") and not is_reference:
            raise ValueError(f"Interpretation {uid} declares an unsupported coordinate recipe; its coordinates were not changed.")
        # The selected parent/derived association and source XY checks establish
        # the frame. Modelled lines can extend beyond recorded samples just as
        # surfaces do; preserve them using the same validated vertical mapping.
        new_points = (transform.reference_points(old_points) if is_reference
                      else transform.points(old_points, allow_extensions=True))
        backup = numpy_to_vtk(np.asarray(old_points, dtype=np.float64), deep=True)
        backup.SetName("pzero_legacy_original_points")
        copy.GetFieldData().AddArray(backup)
        points = vtkPoints()
        points.SetData(numpy_to_vtk(new_points, deep=True))
        copy.SetPoints(points)
        angle_array = original.GetPointData().GetArray("obb_angle")
        if angle_array is not None:
            # OBB properties are spatial coordinates too; retaining the old
            # translation would displace later explicit-modelling operations.
            angle = float(vtk_to_numpy(angle_array).ravel()[0])
            direction = np.array([np.cos(angle), np.sin(angle)])
            jacobian = np.linalg.solve(transform.source_basis, transform.target_basis)
            direction = direction @ jacobian
            angle = float(np.arctan2(direction[1], direction[0]))
            rotation = np.array([[np.cos(angle), np.sin(angle)], [-np.sin(angle), np.cos(angle)]])
            translation = (new_points[:, :2] @ rotation.T).min(axis=0)
            for name, values in (("obb_angle", np.full(len(new_points), angle)),
                                 ("obb_translation", np.tile(translation, (len(new_points), 1)))):
                array = original.GetPointData().GetArray(name)
                if array is not None:
                    backup = array.NewInstance()
                    backup.DeepCopy(array)
                    backup.SetName("pzero_legacy_" + name)
                    copy.GetFieldData().AddArray(backup)
                    value = numpy_to_vtk(values, deep=True)
                    value.SetName(name)
                    copy.GetPointData().AddArray(value)
        old_axes = {name: _string(original, name) for name in ("slice_axis", "single_slice_axis")}
        transform.remap_slices(copy)
        if copy.GetNumberOfPolys() and (copy.GetPointData().GetNormals() is not None or copy.GetCellData().GetNormals() is not None):
            from vtk import vtkPolyDataNormals
            point_normals = copy.GetPointData().GetNormals()
            cell_normals = copy.GetCellData().GetNormals()
            point_name = point_normals.GetName() if point_normals is not None else None
            cell_name = cell_normals.GetName() if cell_normals is not None else None
            if point_name:
                copy.GetPointData().RemoveArray(point_name)
            if cell_name:
                copy.GetCellData().RemoveArray(cell_name)
            normals = vtkPolyDataNormals()
            normals.SetInputData(copy)
            normals.SplittingOff()
            normals.ConsistencyOff()
            normals.ComputePointNormalsOn()
            normals.ComputeCellNormalsOn()
            normals.Update()
            if point_name:
                values = normals.GetOutput().GetPointData().GetNormals()
                values.SetName(point_name)
                copy.GetPointData().SetNormals(values)
            if cell_name:
                values = normals.GetOutput().GetCellData().GetNormals()
                values.SetName(cell_name)
                copy.GetCellData().SetNormals(values)
        migrated = deepcopy(target_metadata)
        migrated["interpretation_relink"] = {
            "version": 1, "old_parent_uid": old_uid, "new_parent_uid": new_uid,
            "source_frame": "legacy_raw_xy_twt_times125" if is_reference else "legacy_raw_xy_div8_z", "original_slice_axes": old_axes,
            "original_seismic_metadata": metadata,
        }
        if uid in derived_sources:
            migrated["derived_from_uids"] = derived_sources[uid]
            migrated["interpretation_relink"]["recovered_parent_from"] = (
                "explicit legacy reference recipe and single interpretation group" if is_reference else
                "generated model boundary and single interpretation group" if angle_array is not None
                else "matching generated surface name and source coordinate frame")
        if is_reference:
            # Archive the old recipe so other consumers cannot mistake it for
            # the current physical-coordinate frame on save/reload.
            for name in ("coordinate_frame", "xy_transform", "z_transform"):
                _set_string(copy, "pzero_legacy_" + name, _string(original, name))
                copy.GetFieldData().RemoveArray(name)
        set_seismic_metadata(copy, migrated)
        copy.Modified()
        replacements[uid] = copy
    return replacements


def find_derived_surface_links(records, old_uid):
    """Recover missing parents only for uniquely associated generated surfaces.

    Historical surface builders retained a generated name but discarded the
    seismic parent. Names alone only nominate candidates; coordinate validation
    still takes place for the whole group before applying any changes.
    """
    by_name = {}
    for row in records:
        if row.get("topology") == "PolyLine" and row.get("parent_uid"):
            by_name.setdefault(row.get("name", ""), []).append(row)
    result = {}
    for row in records:
        if row.get("parent_uid") or row.get("topology") != "TriSurf":
            continue
        name = row.get("name", "")
        for suffix in ("_structured_surface", "_delaunay2d"):
            if not name.endswith(suffix):
                continue
            sources = by_name.get(name[:-len(suffix)], [])
            if sources and {r.get("parent_uid") for r in sources} == {old_uid}:
                result[row["uid"]] = [r["uid"] for r in sources]
            break
    return result


def inherit_surface_seismic_parent(collection, source_uids, surface_dict):
    """Keep explicit parent/provenance on newly generated interpretation surfaces."""
    parents = {collection.get_uid_x_section(uid) for uid in source_uids}
    if len(parents) != 1 or not next(iter(parents)):
        return
    parent = next(iter(parents))
    surface_dict["parent_uid"] = parent
    source_metadata = get_seismic_metadata(collection.get_uid_vtk_obj(source_uids[0]))
    if source_metadata:
        metadata = deepcopy(source_metadata)
        metadata["derived_from_uids"] = list(source_uids)
        set_seismic_metadata(surface_dict["vtk_obj"], metadata)


def find_legacy_reference_links(records, old_uid):
    """Nominate explicitly tagged references in a single-parent legacy model.

    Geometry and slice indices are still validated against the chosen SEG-Y
    before any object or parent is changed. Untagged/unrelated objects stay out.
    """
    parents = {r.get("parent_uid") for r in records if r.get("parent_uid")}
    if parents != {old_uid}:
        return {}
    sources = sorted(r["uid"] for r in records if r.get("parent_uid") == old_uid)
    return {r["uid"]: sources for r in records
            if not r.get("parent_uid") and r.get("topology") == "PolyLine"
            and _is_legacy_time_reference(r.get("vtk_obj"))}


def find_legacy_model_boundaries(geology_records, boundary_records, old_uid):
    """Associate a generated model box only when its entire geology has one source."""
    linked = {r["uid"] for r in geology_records if r.get("parent_uid") == old_uid}
    recovered = set(find_derived_surface_links(geology_records, old_uid))
    recovered.update(find_legacy_reference_links(geology_records, old_uid))
    whole_model = bool(linked) and all(r["uid"] in linked | recovered for r in geology_records)
    result = {}
    for row in boundary_records:
        if row.get("parent_uid") == old_uid or (
            whole_model and not row.get("parent_uid")
            and "obb_angle" in (row.get("properties_names") or [])
        ):
            result[row["uid"]] = sorted(linked)
    return result
