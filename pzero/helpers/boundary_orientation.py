"""Read a boundary's horizontal frame from its current geometry."""

import numpy as np
from scipy.spatial import ConvexHull, QhullError
from vtkmodules.util.numpy_support import vtk_to_numpy
from vtkmodules.vtkCommonCore import vtkStringArray


def mark_oriented_boundary(obj):
    """Record the construction kind for relinking, without storing orientation."""
    tag = vtkStringArray()
    tag.SetName("pzero_boundary_kind")
    tag.InsertNextValue("oriented_box")
    obj.GetFieldData().AddArray(tag)


def is_generated_oriented_boundary(obj):
    if obj is None:
        return False
    tag = obj.GetFieldData().GetAbstractArray("pzero_boundary_kind")
    return bool(
        tag is not None
        and tag.GetNumberOfValues()
        and tag.GetValue(0) == "oriented_box"
    )


def boundary_obb_transform(obj):
    """Return the existing OBB frame convention, using float64 throughout.

    World to local: (XY - center) @ R(-angle).T. Z is unchanged.
    The first stored rectangle edge defines X, including for square boxes;
    duplicated closing points and the top/bottom of a volume have no weight.
    Legacy arrays are only a fallback for older non-rectangular geometry.
    This reads geometry without changing points or rebuilding the boundary.
    """
    if obj is None or obj.GetPoints() is None:
        return {"has_obb": False}
    raw = vtk_to_numpy(obj.GetPoints().GetData())
    points = np.asarray(raw, dtype=np.float64)
    if len(points) < 3 or not np.isfinite(points).all():
        return {"has_obb": False}

    xy = points[:, :2]
    _, indices = np.unique(xy, axis=0, return_index=True)
    unique = xy[np.sort(indices)]
    # Center before hull/vector calculations to retain precision at UTM scales.
    anchor = unique[0]
    local = unique - anchor
    angle = None
    center = None
    try:
        hull = ConvexHull(local).vertices
        if len(hull) == 4:
            hull = np.roll(hull, -np.argmin(hull))
            if hull[1] > hull[-1]:
                hull = np.r_[hull[0], hull[:0:-1]]
            corners = local[hull]
            edges = np.roll(corners, -1, axis=0) - corners
            lengths = np.linalg.norm(edges, axis=1)
            # Old projects may contain float32 points. Allow their coordinate
            # rounding, but do not classify degenerate or skew boxes as rectangles.
            eps = np.finfo(raw.dtype).eps if raw.dtype.kind == "f" else 0.0
            tol = max(
                np.linalg.norm(np.ptp(local, axis=0)) * 1e-9,
                np.abs(xy).max() * eps * 2,
                1e-10,
            )
            dots = np.abs(np.sum(edges * np.roll(edges, -1, axis=0), axis=1))
            if np.all(lengths > 2 * tol) and np.all(
                dots <= tol * (lengths + np.roll(lengths, -1))
            ):
                angle = np.arctan2(edges[0, 1], edges[0, 0])
                center = anchor + corners.mean(axis=0)
    except QhullError:
        pass

    if angle is None:
        # Keep historical projects usable without treating arbitrary untagged
        # surfaces as oriented boxes. Valid rectangles always ignore these arrays.
        stored = obj.GetPointData().GetArray("obb_angle")
        if stored is None or not stored.GetNumberOfTuples():
            return {"has_obb": False}
        angle = np.float64(stored.GetComponent(0, 0))
        if not np.isfinite(angle):
            return {"has_obb": False}
        center = anchor + (local.min(axis=0) + local.max(axis=0)) / 2

    c, s = np.cos(angle), np.sin(angle)
    rotation = np.array([[c, s], [-s, c]], dtype=np.float64)
    translation = ((xy - center) @ rotation.T).min(axis=0) + center @ rotation.T
    return {
        "has_obb": True,
        "angle": float(angle),
        "center": center,
        "translation": translation,
    }
