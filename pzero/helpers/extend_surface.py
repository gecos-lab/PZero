"""Geometry used by the 3D view's Extend surface tool."""

import numpy as np
from scipy.sparse import coo_matrix, diags, eye
from scipy.sparse.linalg import spsolve
from vtkmodules.util.numpy_support import numpy_to_vtkIdTypeArray, vtk_to_numpy
from vtkmodules.vtkCommonCore import vtkIdList
from vtkmodules.vtkCommonDataModel import vtkCellArray
from vtkmodules.vtkFiltersCore import vtkPolyDataNormals


def _copy_tuple_arrays(attributes, source_ids):
    """Append source tuples in bulk, including numeric and string arrays."""
    ids = vtkIdList()
    for source_id in source_ids:
        ids.InsertNextId(int(source_id))
    for array_id in range(attributes.GetNumberOfArrays()):
        array = attributes.GetAbstractArray(array_id)
        array.InsertTuplesStartingAt(array.GetNumberOfTuples(), ids, array)


def _surface_boundary_edges(surface, direction, return_shifts=False):
    """Find real open edges, ignoring seams between coincident mesh vertices."""
    points = np.asarray(surface.points, dtype=float)
    triangles = vtk_to_numpy(surface.GetPolys().GetConnectivityArray()).reshape(-1, 3)
    _, representatives, inverse = np.unique(
        points, axis=0, return_index=True, return_inverse=True
    )
    triangles = representatives[inverse[triangles]]
    edges = triangles[:, [0, 1, 1, 2, 2, 0]].reshape(-1, 2)
    keys = np.sort(edges, axis=1)
    order = np.lexsort(keys.T)
    keys = keys[order]
    # A boundary edge occurs once, so both sorted neighbors must differ.
    unique = np.r_[True, np.any(keys[1:] != keys[:-1], axis=1), True]
    first = np.sort(order[unique[:-1] & unique[1:]])
    boundary = np.column_stack((edges[first], first // 3))
    normals = np.cross(
        points[triangles[:, 1]] - points[triangles[:, 0]],
        points[triangles[:, 2]] - points[triangles[:, 0]],
    )
    vectors = points[boundary[:, 1]] - points[boundary[:, 0]]
    outward = np.cross(vectors, normals[boundary[:, 2]])
    lengths = np.linalg.norm(outward, axis=1)
    valid = lengths > 0
    boundary, outward, lengths = boundary[valid], outward[valid], lengths[valid]
    scores = (outward @ (direction / np.linalg.norm(direction))) / lengths
    if return_shifts:
        shifts = _surface_tangent_shifts(points, triangles, boundary, direction)
        # Select sides using the actual slope-following motion at both endpoints.
        scores = np.einsum(
            "ij,ij->i", outward, shifts[boundary[:, :2]].mean(axis=1)
        ) / (lengths * np.linalg.norm(direction))
        positive, negative = boundary[scores > 1e-8], boundary[scores < -1e-8]
        return positive, negative, shifts, normals
    return boundary[scores > 1e-8], boundary[scores < -1e-8]


def _surface_tangent_shifts(points, triangles, boundary, offset):
    """Fit connected two-ring patches and smooth their planes along the boundary."""
    shifts = np.zeros_like(points)
    if not len(boundary):
        return shifts
    ids = np.unique(boundary[:, :2])
    edges = triangles[:, [0, 1, 1, 2, 2, 0]].reshape(-1, 2)
    graph = coo_matrix(
        (np.ones(len(edges)), (edges[:, 0], edges[:, 1])),
        shape=(len(points), len(points)),
    ).tocsr()
    graph = graph + graph.T
    graph.data[:] = 1
    graph += eye(len(points), format="csr")
    neighbors = graph[ids] @ graph
    rows = np.repeat(np.arange(len(ids)), np.diff(neighbors.indptr))
    samples = points[neighbors.indices] - points[ids[rows]]
    centers = np.zeros((len(ids), 3))
    np.add.at(centers, rows, samples)
    samples -= (centers / np.diff(neighbors.indptr)[:, None])[rows]
    covariance = np.zeros((len(ids), 3, 3))
    np.add.at(covariance, rows, samples[:, :, None] * samples[:, None, :])
    normals = np.linalg.eigh(covariance)[1][:, :, 0]

    # Arc-length weights keep very short boundary edges from introducing spikes.
    ends = np.searchsorted(ids, boundary[:, :2])
    lengths = np.linalg.norm(points[boundary[:, 1]] - points[boundary[:, 0]], axis=1)
    weights = coo_matrix(
        (1 / lengths, (ends[:, 0], ends[:, 1])), shape=(len(ids), len(ids))
    ).tocsr()
    weights += weights.T
    mass = np.bincount(ends.ravel(), weights=np.repeat(lengths / 2, 2))
    laplacian = diags(np.asarray(weights.sum(axis=1)).ravel()) - weights
    planes = (normals[:, :, None] * normals[:, None, :]).reshape(-1, 9)
    planes = spsolve(
        diags(mass) + (2 * np.median(lengths)) ** 2 * laplacian,
        mass[:, None] * planes,
    ).reshape(-1, 3, 3)
    normals = np.linalg.eigh(planes)[1][:, :, -1]
    shifts[ids] = offset - normals * (normals @ offset)[:, None]
    return shifts


def _safe_boundary_shifts(points, boundary, shifts, normals):
    """Keep tangent growth outward and cap strips before their winding reverses."""
    ids, first, inverse = np.unique(
        boundary[:, :2], return_index=True, return_inverse=True
    )
    order = first.argsort()
    ids = ids[order]
    ends = order.argsort()[inverse].reshape(-1, 2)
    shifts = shifts[ids].copy()
    edge = points[boundary[:, 1]] - points[boundary[:, 0]]
    normals = normals[boundary[:, 2]]
    normals = normals / np.linalg.norm(normals, axis=1)[:, None]
    outward = np.cross(edge, normals)
    outward /= np.linalg.norm(outward, axis=1)[:, None]
    # Correct small disagreements between the fitted plane and boundary triangles.
    margin = np.linalg.norm(shifts, axis=1).max() * 1e-6
    for _ in range(8):
        scores = np.einsum("ij,ikj->ik", outward, shifts[ends])
        correction = np.maximum(margin - scores, 0)[:, :, None] * outward[:, None, :]
        np.add.at(shifts, ends.ravel(), correction.reshape(-1, 3))
    first, second = shifts[ends[:, 0]], shifts[ends[:, 1]]
    twist = np.einsum("ij,ij->i", np.cross(first, second), normals)
    area = np.column_stack(
        (
            np.einsum("ij,ij->i", np.cross(-edge, second), normals),
            np.einsum("ij,ij->i", np.cross(-edge, first), normals),
        )
    )
    caps = np.ones_like(area)
    folding = twist < 0
    caps[folding] = np.minimum(1, 0.95 * area[folding] / -twist[folding, None])
    factors = np.ones(len(ids))
    np.minimum.at(factors, ends.ravel(), caps.ravel())
    # Spread reductions to neighboring points without exceeding any safe cap.
    for _ in range(3):
        total, count = np.zeros(len(ids)), np.zeros(len(ids))
        np.add.at(total, ends.ravel(), factors[ends[:, ::-1]].ravel())
        np.add.at(count, ends.ravel(), 1)
        factors = np.minimum(factors, (total + factors) / (count + 1))
    return ids, ends, shifts * factors[:, None]


def extend_geology_entity(vtk_obj, topology, direction, distance, side):
    """Return a new geological entity with selected ends/boundaries extended.

    ``direction`` guides surface growth along fitted local tangent planes;
    ``distance`` scales it. PolyLine endpoints use the entered vector directly.
    The source entity is never changed.
    """
    offset = np.asarray(direction, dtype=float) * float(distance)
    if not np.all(np.isfinite(offset)) or np.linalg.norm(offset) == 0:
        return None
    if side not in ("positive", "negative", "both"):
        return None

    points = np.asarray(vtk_obj.points, dtype=float)
    if topology == "PolyLine":
        if vtk_obj.GetNumberOfPoints() < 2 or vtk_obj.GetNumberOfLines() < 1:
            return None
        selected = np.array([side != "negative", side != "positive"])
        point_ids = np.array([len(points) - 1, 0])[selected]
        cell_ids = np.array([vtk_obj.GetNumberOfLines() - 1, 0])[selected]
        new_points = points[point_ids] + np.array([offset, -offset])[selected]
        new_ids = np.arange(len(point_ids)) + len(points)
        cells = np.column_stack((point_ids, new_ids))
        cells[point_ids == 0] = cells[point_ids == 0, ::-1]
        source_cells = vtk_obj.GetLines()
    elif topology == "TriSurf":
        if vtk_obj.GetNumberOfPoints() < 3 or vtk_obj.GetNumberOfPolys() < 1:
            return None
        positive, negative, shifts, normals = _surface_boundary_edges(
            vtk_obj, offset, return_shifts=True
        )
        point_ids, cell_ids, new_points, cells = [], [], [], []
        for boundary, sign, selected in (
            (positive, 1, side != "negative"),
            (negative, -1, side != "positive"),
        ):
            if not selected or not len(boundary):
                continue
            ids, ends, growth = _safe_boundary_shifts(
                points, boundary, sign * shifts, normals
            )
            lengths = np.linalg.norm(
                points[boundary[:, 1]] - points[boundary[:, 0]], axis=1
            )
            span = np.linalg.norm(growth, axis=1).max()
            steps = int(np.clip(np.ceil(span / np.median(lengths)), 1, 16))
            previous = boundary[:, :2]
            for step in range(1, steps + 1):
                new_ids = ends + len(points) + sum(len(part) for part in point_ids)
                start, end = previous.T
                # Reverse the shared edge to preserve the source winding.
                strip = np.empty((len(boundary), 2, 3), dtype=np.int64)
                strip[:, 0] = np.column_stack((end, start, new_ids[:, 0]))
                strip[:, 1] = np.column_stack((end, new_ids[:, 0], new_ids[:, 1]))
                cells.append(strip.reshape(-1, 3))
                point_ids.append(ids)
                cell_ids.append(np.repeat(boundary[:, 2], 2))
                new_points.append(points[ids] + growth * (step / steps))
                previous = new_ids
        if not cells:
            return None
        point_ids, cell_ids = np.concatenate(point_ids), np.concatenate(cell_ids)
        new_points, cells = np.vstack(new_points), np.vstack(cells)
        source_cells = vtk_obj.GetPolys()
    else:
        return None

    result = vtk_obj.deep_copy()
    result.points = np.vstack((points, new_points))
    connectivity = vtk_to_numpy(source_cells.GetConnectivityArray()).reshape(
        -1, cells.shape[1]
    )
    extended_cells = vtkCellArray()
    extended_cells.SetData(
        cells.shape[1],
        numpy_to_vtkIdTypeArray(
            np.vstack((connectivity, cells), dtype=np.int64).ravel(), deep=True
        ),
    )
    if topology == "TriSurf":
        result.SetPolys(extended_cells)
    else:
        result.SetLines(extended_cells)
    _copy_tuple_arrays(result.GetPointData(), point_ids)
    _copy_tuple_arrays(result.GetCellData(), cell_ids)
    if topology == "TriSurf":
        # Normals are derived geometry, so recompute instead of copying stale ones.
        normal_filter = vtkPolyDataNormals()
        normal_filter.SetInputData(result)
        normal_filter.SplittingOff()
        normal_filter.ConsistencyOff()
        normal_filter.ComputeCellNormalsOn()
        normal_filter.Update()
        result.GetPointData().SetNormals(
            normal_filter.GetOutput().GetPointData().GetNormals()
        )
        result.GetCellData().SetNormals(
            normal_filter.GetOutput().GetCellData().GetNormals()
        )
    result.Modified()
    return result
