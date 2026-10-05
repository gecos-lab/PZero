"""Formation definitions and voxel assignment for the LoopStructural workflow."""

import json

import numpy as np
from vtk import vtkStringArray
from vtkmodules.util.numpy_support import numpy_to_vtk, vtk_to_numpy


FORMATION_PROPERTY = "FormationID"
FORMATION_METADATA = "LoopStructuralFormations"
UNASSIGNED_ID = -1


def default_formations(contacts):
    """Suggest intervals between contacts, including both unbounded end units.

    Contacts contain scalar ``value`` and a display ``name``. Contact names
    describe interfaces, so the suggested volume names deliberately describe
    intervals until the user supplies formation names.
    """
    contacts_by_value = {
        float(contact["value"]): contact
        for contact in contacts
        if np.isfinite(float(contact["value"]))
    }
    ordered = sorted(contacts_by_value.items())
    bounds = [-np.inf] + [value for value, _ in ordered] + [np.inf]
    definitions = []
    for index, (lower, upper) in enumerate(zip(bounds[:-1], bounds[1:])):
        if not ordered:
            name = "Formation_1"
        elif index == 0:
            name = f"Below_{ordered[0][1]['name']}"
        elif index == len(ordered):
            name = f"Above_{ordered[-1][1]['name']}"
        else:
            name = f"{ordered[index - 1][1]['name']}_to_{ordered[index][1]['name']}"
        definitions.append(
            {
                "name": name,
                "id": index + 1,
                "min": lower,
                "max": upper,
                "color": "#808080",
            }
        )
    return definitions


def validate_formations(definitions):
    """Return normalized definitions; reject ambiguous or invalid assignments."""
    if not definitions:
        raise ValueError("Define at least one formation.")
    normalized = []
    for definition in definitions:
        name = str(definition["name"]).strip()
        try:
            material_id = int(str(definition["id"]))
            lower, upper = float(definition["min"]), float(definition["max"])
        except (ValueError, TypeError, OverflowError) as error:
            raise ValueError(
                "IDs must be integers and limits must be numbers or +/-inf."
            ) from error
        if not name:
            raise ValueError("Every formation needs a name.")
        if not 1 <= material_id <= np.iinfo(np.int32).max:
            raise ValueError(
                "Formation IDs must be positive 32-bit integers; -1 is unassigned."
            )
        if np.isnan(lower) or np.isnan(upper) or lower >= upper:
            raise ValueError(
                f"{name}: the lower limit must be less than the upper limit."
            )
        color = str(definition.get("color", "#808080"))
        if len(color) != 7 or not color.startswith("#"):
            raise ValueError(f"{name}: enter a colour as #RRGGBB.")
        try:
            int(color[1:], 16)
        except ValueError as error:
            raise ValueError(f"{name}: enter a colour as #RRGGBB.") from error
        normalized.append(
            {
                **definition,
                "name": name,
                "id": material_id,
                "min": lower,
                "max": upper,
                "color": color.lower(),
            }
        )
    if len({item["id"] for item in normalized}) != len(normalized):
        raise ValueError("Each formation must have a different ID.")
    if len({item["name"] for item in normalized}) != len(normalized):
        raise ValueError("Each formation must have a different name.")
    normalized.sort(key=lambda item: item["min"])
    for previous, current in zip(normalized[:-1], normalized[1:]):
        if previous["max"] > current["min"]:
            raise ValueError(
                f"Scalar ranges overlap: {previous['name']} and {current['name']}."
            )
    return normalized


def classify_formations(values, definitions):
    """Assign discrete IDs using lower-inclusive, upper-exclusive intervals.

    Undefined scalar values and gaps remain -1. Contacts belong to the unit
    starting at that value, avoiding unassigned bands at exact contact values.
    """
    values = np.asarray(values)
    ids = np.full(values.shape, UNASSIGNED_ID, dtype=np.int32)
    finite = np.isfinite(values)
    for item in validate_formations(definitions):
        mask = finite & (values >= item["min"]) & (values < item["max"])
        ids[mask] = item["id"]
    return ids


def voxet_sample_points(origin, spacing, dimensions, cell_centres=False):
    """Generate local model coordinates in VTK order (X varies fastest)."""
    dimensions = np.asarray(dimensions, dtype=int)
    counts = dimensions - 1 if cell_centres else dimensions
    offset = 0.5 if cell_centres else 0.0
    axes = [
        origin[axis] + (np.arange(counts[axis]) + offset) * spacing[axis]
        for axis in range(3)
    ]
    z, y, x = np.meshgrid(axes[2], axes[1], axes[0], indexing="ij")
    return np.column_stack((x.ravel(), y.ravel(), z.ravel()))


def read_formation_metadata(voxet):
    """Read definitions persisted in the Voxet's VTK field data."""
    array = voxet.GetFieldData().GetAbstractArray(FORMATION_METADATA)
    if array is None or array.GetNumberOfValues() == 0:
        return None
    return json.loads(array.GetValue(0))


def assign_voxet_formations(
    voxet, sequence, definitions, cell_values=None, context=None
):
    """Store formation IDs on nodes and cells, and persist the formation legend.

    A new Loop model passes scalar values evaluated at actual cell centres.
    Reassignment reuses these stored values. Legacy Voxets can be classified
    from the trilinear scalar value at each cell centre instead.
    """
    definitions = validate_formations(definitions)
    scalar_array = voxet.GetPointData().GetArray(sequence)
    if scalar_array is None or scalar_array.GetNumberOfComponents() != 1:
        raise ValueError(f"The Voxet needs a scalar field named {sequence}.")
    point_values = vtk_to_numpy(scalar_array)
    if cell_values is None:
        stored = voxet.GetCellData().GetArray(sequence)
        if stored is not None:
            cell_values = vtk_to_numpy(stored)
        else:
            nx, ny, nz = voxet.GetDimensions()
            if min(nx, ny, nz) < 2:
                raise ValueError(
                    "Formation assignment needs a three-dimensional Voxet."
                )
            values = point_values.reshape(nz, ny, nx)
            cell_values = (
                sum(
                    values[z : z + nz - 1, y : y + ny - 1, x : x + nx - 1]
                    for z in (0, 1)
                    for y in (0, 1)
                    for x in (0, 1)
                )
                / 8.0
            )
            cell_values = cell_values.ravel()
    cell_values = np.asarray(cell_values).ravel()
    if cell_values.size != voxet.GetNumberOfCells():
        raise ValueError("Cell-centre scalar values do not match the Voxet cells.")
    point_ids = classify_formations(point_values, definitions)
    cell_ids = classify_formations(cell_values, definitions)
    for data, name, values in (
        (voxet.GetPointData(), FORMATION_PROPERTY, point_ids),
        (voxet.GetCellData(), FORMATION_PROPERTY, cell_ids),
        (voxet.GetCellData(), sequence, cell_values),
    ):
        array = numpy_to_vtk(np.ascontiguousarray(values), deep=True)
        array.SetName(name)
        data.AddArray(array)
    # Store unbounded limits as strings to keep the JSON standards compliant.
    stored_definitions = [
        {**item, "min": str(item["min"]), "max": str(item["max"])}
        for item in definitions
    ]
    payload = dict(read_formation_metadata(voxet) or {})
    payload.update(context or {})
    payload.update(version=2, sequence=sequence, formations=stored_definitions)
    metadata = vtkStringArray()
    metadata.SetName(FORMATION_METADATA)
    metadata.InsertNextValue(
        json.dumps(
            payload,
            allow_nan=False,
        )
    )
    voxet.GetFieldData().AddArray(metadata)
    voxet.GetPointData().SetActiveScalars(FORMATION_PROPERTY)
    voxet.GetCellData().SetActiveScalars(FORMATION_PROPERTY)
    voxet.Modified()
    return {
        item["id"]: int(np.count_nonzero(cell_ids == item["id"]))
        for item in definitions
    }


def formation_lookup_table(voxet, project=None, cmap=None):
    """Map categorical IDs using Properties colours, or the geological legend."""
    from pyvista import LookupTable, get_cmap_safe
    from pzero.legend_manager import Legend

    metadata = read_formation_metadata(voxet)
    if metadata is None:
        return None
    formations = metadata["formations"]
    lookup = LookupTable(n_values=len(formations) + 1)
    if cmap is None:
        properties = getattr(project, "prop_legend_df", None)
        if properties is not None:
            matching = properties.loc[
                properties["property_name"] == FORMATION_PROPERTY, "colormap"
            ]
            if not matching.empty:
                cmap = matching.iloc[0]
    if cmap is not None:
        # Sample by numeric value so sparse IDs follow the property's colormap.
        # Use all defined IDs to keep colours stable across displayed subsets.
        ids = np.array([item["id"] for item in formations], dtype=float)
        span = np.ptp(ids)
        positions = (ids - ids.min()) / span if span else np.zeros_like(ids)
        colors = get_cmap_safe(cmap)(positions, bytes=True).tolist()
    else:
        legend_colors = [
            Legend.loop_formation_color(project, item) for item in formations
        ]
        colors = [
            [int(color[offset : offset + 2], 16) for offset in (1, 3, 5)] + [255]
            for color in legend_colors
        ]
    lookup.values = np.array(
        [[128, 128, 128, 255]] + colors,
        dtype=np.uint8,
    )
    lookup.annotations = {
        UNASSIGNED_ID: "Unassigned",
        **{item["id"]: item["name"] for item in formations},
    }
    # PyVista's annotations getter reads VTK allocated size, not tuple count.
    lookup.GetAnnotatedValues().Squeeze()
    lookup.GetAnnotations().Squeeze()
    lookup.SetIndexedLookup(True)
    lookup.SetNanColor(0.5, 0.5, 0.5, 1.0)
    return lookup
