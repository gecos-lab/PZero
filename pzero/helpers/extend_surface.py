"""Geometry used by the 3D view's Extend surface tool."""

import numpy as np


def _copy_tuple_arrays(attributes, source_id):
    """Copy an existing point or cell tuple onto a newly appended element."""
    for array_id in range(attributes.GetNumberOfArrays()):
        array = attributes.GetAbstractArray(array_id)
        array.InsertNextTuple(source_id, array)


def _surface_boundary_edges(surface, direction):
    """Return oriented outer edges grouped by the side facing the direction."""
    points = np.asarray(surface.points)
    triangles = np.asarray(surface.cells)
    edges = {}
    for cell_id, triangle in enumerate(triangles):
        for start, end in (
            (triangle[0], triangle[1]),
            (triangle[1], triangle[2]),
            (triangle[2], triangle[0]),
        ):
            key = tuple(sorted((int(start), int(end))))
            if key in edges:
                count, oriented = edges[key]
                edges[key] = (count + 1, oriented)
            else:
                edges[key] = (1, (int(start), int(end), cell_id))

    boundary = [edge for count, edge in edges.values() if count == 1]
    if not boundary:
        return [], []

    unit = direction / np.linalg.norm(direction)
    # Edges parallel to the extension already run along its direction.
    facing = []
    for start, end, cell_id in boundary:
        edge = points[end] - points[start]
        length = np.linalg.norm(edge)
        if length and abs(np.dot(edge, unit)) / length <= 0.5:
            facing.append((start, end, cell_id))
    if not facing:
        facing = boundary

    projections = np.array(
        [np.dot((points[start] + points[end]) / 2, unit) for start, end, _ in facing]
    )
    middle = (projections.min() + projections.max()) / 2
    positive = [edge for edge, value in zip(facing, projections) if value >= middle]
    negative = [edge for edge, value in zip(facing, projections) if value <= middle]
    return positive, negative


def extend_geology_entity(vtk_obj, topology, direction, distance, side):
    """Return a new geological entity with selected ends/boundaries extended.

    ``direction`` is a vector in model units and ``distance`` scales it.
    The source entity is never changed.
    """
    offset = np.asarray(direction, dtype=float) * float(distance)
    if not np.all(np.isfinite(offset)) or np.linalg.norm(offset) == 0:
        return None
    if side not in ("positive", "negative", "both"):
        return None

    if topology == "PolyLine":
        if vtk_obj.GetNumberOfPoints() < 2 or vtk_obj.GetNumberOfLines() < 1:
            return None
        result = vtk_obj.deep_copy()
        result.points = np.asarray(vtk_obj.points, dtype=float).copy()
        for selected, source_id, cell_id, sign in (
            (
                side in ("positive", "both"),
                vtk_obj.GetNumberOfPoints() - 1,
                vtk_obj.GetNumberOfLines() - 1,
                1,
            ),
            (side in ("negative", "both"), 0, 0, -1),
        ):
            if not selected:
                continue
            new_id = result.GetNumberOfPoints()
            result.append_point(np.asarray(vtk_obj.GetPoint(source_id)) + sign * offset)
            _copy_tuple_arrays(result.GetPointData(), source_id)
            if sign > 0:
                result.append_cell(np.array([source_id, new_id]))
            else:
                result.append_cell(np.array([new_id, source_id]))
            _copy_tuple_arrays(result.GetCellData(), cell_id)
        result.Modified()
        return result

    if topology == "TriSurf":
        if vtk_obj.GetNumberOfPoints() < 3 or vtk_obj.GetNumberOfPolys() < 1:
            return None
        positive, negative = _surface_boundary_edges(vtk_obj, offset)
        chosen = []
        if side in ("positive", "both"):
            chosen.append((positive, offset))
        if side in ("negative", "both"):
            chosen.append((negative, -offset))
        if not any(edges for edges, _ in chosen):
            return None

        result = vtk_obj.deep_copy()
        result.points = np.asarray(vtk_obj.points, dtype=float).copy()
        for boundary, shift in chosen:
            new_ids = {}
            for start, end, cell_id in boundary:
                for point_id in (start, end):
                    if point_id not in new_ids:
                        new_ids[point_id] = result.GetNumberOfPoints()
                        result.append_point(
                            np.asarray(vtk_obj.GetPoint(point_id)) + shift
                        )
                        _copy_tuple_arrays(result.GetPointData(), point_id)
                # The boundary edge is reversed in the new triangles to keep
                # their winding consistent with the source surface.
                result.append_cell(np.array([end, start, new_ids[start]]))
                result.append_cell(np.array([end, new_ids[start], new_ids[end]]))
                _copy_tuple_arrays(result.GetCellData(), cell_id)
                _copy_tuple_arrays(result.GetCellData(), cell_id)
        result.Modified()
        return result

    return None
