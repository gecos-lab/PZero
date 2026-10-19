"""Index/physical-coordinate conversion for rectilinear survey axes."""
import numpy as np


def axis_coordinate(values, index, inverse=False):
    """Piecewise linear conversion, including linear continuation outside bounds."""
    if values is None:
        return np.asarray(index, dtype=float)
    values = np.asarray(values, dtype=float)
    if len(values) < 2:
        return np.asarray(index, dtype=float)
    indices = np.arange(len(values), dtype=float)
    xp, fp = (values, indices) if inverse else (indices, values)
    x = np.asarray(index, dtype=float)
    result = np.interp(x, xp, fp)
    result = np.where(x < xp[0], fp[0] + (x - xp[0]) * (fp[1] - fp[0]) / (xp[1] - xp[0]), result)
    return np.where(x > xp[-1], fp[-1] + (x - xp[-1]) * (fp[-1] - fp[-2]) / (xp[-1] - xp[-2]), result)


def slice_camera_frame(center, row_span, col_span, scale, aspect, north_up=False):
    """Fit a parallel camera to a survey slice after applying actor scale.

    Spans are the complete physical edge vectors, not the volume's world-axis
    bounds. Increasing row coordinates run right; increasing column coordinates
    run up. Plan views can instead face down with north up. Orthogonalizing the
    camera preserves skew in the survey geometry.
    """
    scale = np.asarray(scale, dtype=float)
    center = np.asarray(center, dtype=float) * scale
    row = np.asarray(row_span, dtype=float) * scale
    col = np.asarray(col_span, dtype=float) * scale
    normal = np.cross(row, col)
    norm = np.linalg.norm(normal)
    if not np.isfinite(norm) or norm <= 0 or not np.isfinite(aspect) or aspect <= 0:
        raise ValueError("Cannot fit a camera to a degenerate seismic slice.")
    normal /= norm
    if north_up:
        if normal[2] < 0:
            normal = -normal
        up = np.array([0., 1., 0.]) - normal[1] * normal
        up /= np.linalg.norm(up)
    else:
        up = col / np.linalg.norm(col)
    right = np.cross(up, normal)
    width = abs(np.dot(row, right)) + abs(np.dot(col, right))
    height = abs(np.dot(row, up)) + abs(np.dot(col, up))
    return {
        "position": center + normal * max(width, height) * 2,
        "focal_point": center,
        "view_up": up,
        "right": right,
        "parallel_scale": max(height, width / aspect) * 0.5 * 1.05,
    }
