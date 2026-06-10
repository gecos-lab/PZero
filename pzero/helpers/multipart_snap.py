"""Pure geometry helpers for snapping multipart interpretation line slices."""

import numpy as np
from shapely.geometry import LineString as shp_linestring
from shapely.geometry import Point as shp_point
from shapely.ops import split as shp_split


def dedupe_consecutive_uv(coords=None, tolerance=1.0e-8):
    """Remove consecutive duplicate 2D slice coordinates."""
    if coords is None:
        return None
    uv = np.asarray(coords, dtype=float)
    if uv.ndim != 2 or uv.shape[1] != 2:
        return None
    if uv.shape[0] <= 1:
        return uv
    distances = np.linalg.norm(np.diff(uv, axis=0), axis=1)
    keep = np.concatenate([[True], distances > float(tolerance)])
    cleaned = uv[keep]
    return cleaned if cleaned.shape[0] >= 2 else uv[: min(uv.shape[0], 2)]


def uv_coords_changed(coords_a=None, coords_b=None, tolerance=1.0e-8):
    """Return True when two 2D line coordinate arrays differ."""
    if coords_a is None or coords_b is None:
        return True
    a = np.asarray(coords_a, dtype=float)
    b = np.asarray(coords_b, dtype=float)
    if a.shape != b.shape:
        return True
    if a.size == 0 and b.size == 0:
        return False
    return bool(np.linalg.norm(a - b) > float(tolerance))


def extract_intersection_uv_points(geometry=None):
    """Extract representative 2D points from a Shapely intersection geometry."""
    if geometry is None or geometry.is_empty:
        return []
    gtype = geometry.geom_type
    if gtype == "Point":
        return [np.asarray(geometry.coords[0], dtype=float)]
    if gtype == "MultiPoint":
        return [np.asarray(point.coords[0], dtype=float) for point in geometry.geoms]
    if gtype in ("LineString", "LinearRing"):
        coords = list(geometry.coords)
        return [
            np.asarray(coords[0], dtype=float),
            np.asarray(coords[-1], dtype=float),
        ]
    if gtype == "MultiLineString":
        points = []
        for line in geometry.geoms:
            coords = list(line.coords)
            if coords:
                points.append(np.asarray(coords[0], dtype=float))
                points.append(np.asarray(coords[-1], dtype=float))
        return points
    if hasattr(geometry, "geoms"):
        points = []
        for geom in geometry.geoms:
            points.extend(extract_intersection_uv_points(geometry=geom))
        return points
    return []


def insert_uv_point_on_line(line_uv=None, point=None, tolerance=1.0e-8):
    """Insert a 2D point as a vertex if it lies on a line segment."""
    uv = np.asarray(line_uv, dtype=float)
    point = np.asarray(point, dtype=float).reshape(2)
    for vertex in uv:
        if np.linalg.norm(vertex - point) <= float(tolerance):
            return uv

    point_geom = shp_point(float(point[0]), float(point[1]))
    for idx in range(len(uv) - 1):
        segment = shp_linestring([uv[idx], uv[idx + 1]])
        if segment.distance(point_geom) <= float(tolerance):
            return np.concatenate(
                (uv[: idx + 1], point.reshape(1, 2), uv[idx + 1 :]),
                axis=0,
            )
    return uv


def trim_uv_terminal_branch(line_uv=None, point=None, max_distance=0.0, tolerance=1.0e-8):
    """Trim a short overshooting terminal branch back to an intersection point."""
    uv = np.asarray(line_uv, dtype=float)
    point = np.asarray(point, dtype=float).reshape(2)
    if uv.shape[0] < 2:
        return uv, False

    out = insert_uv_point_on_line(uv, point, tolerance=tolerance)
    out = dedupe_consecutive_uv(out, tolerance=tolerance)
    if out is None or out.shape[0] < 2:
        return uv, False

    start_dist = float(np.linalg.norm(point - out[0]))
    end_dist = float(np.linalg.norm(point - out[-1]))
    if (
        start_dist > float(max_distance) + float(tolerance)
        and end_dist > float(max_distance) + float(tolerance)
    ):
        return out, uv_coords_changed(uv, out, tolerance=tolerance)

    distances = np.linalg.norm(out - point, axis=1)
    point_idx = int(distances.argmin())
    if distances[point_idx] > float(tolerance):
        return out, uv_coords_changed(uv, out, tolerance=tolerance)

    if start_dist <= end_dist:
        if point_idx == 0:
            return out, uv_coords_changed(uv, out, tolerance=tolerance)
        trimmed = out[point_idx:, :]
    else:
        if point_idx >= out.shape[0] - 1:
            return out, uv_coords_changed(uv, out, tolerance=tolerance)
        trimmed = out[: point_idx + 1, :]

    trimmed = dedupe_consecutive_uv(trimmed, tolerance=tolerance)
    if trimmed is None or trimmed.shape[0] < 2:
        return out, uv_coords_changed(uv, out, tolerance=tolerance)
    return trimmed, True


def uv_endpoint_extension_candidates(line_uv=None, tolerance=1.0e-12):
    """Return start/end ray candidates for endpoint snapping."""
    uv = np.asarray(line_uv, dtype=float)
    candidates = []
    if uv.shape[0] < 2:
        return candidates

    end_anchor = uv[-1]
    for idx in range(uv.shape[0] - 2, -1, -1):
        vec = end_anchor - uv[idx]
        vec_len = float(np.linalg.norm(vec))
        if vec_len > float(tolerance):
            candidates.append(("append", end_anchor, vec / vec_len))
            break

    start_anchor = uv[0]
    for idx in range(1, uv.shape[0]):
        vec = start_anchor - uv[idx]
        vec_len = float(np.linalg.norm(vec))
        if vec_len > float(tolerance):
            candidates.append(("prepend", start_anchor, vec / vec_len))
            break
    return candidates


def snap_two_uv_lines_to_intersection(
    line_a_uv=None, line_b_uv=None, max_distance=10.0, tolerance=1.0e-8
):
    """
    Snap two same-slice 2D polylines to exact shared intersection vertices.

    Returns updated coordinates for both lines plus per-slice stats.
    """
    line_uv = {
        "a": dedupe_consecutive_uv(line_a_uv, tolerance=tolerance),
        "b": dedupe_consecutive_uv(line_b_uv, tolerance=tolerance),
    }
    if (
        line_uv["a"] is None
        or line_uv["b"] is None
        or line_uv["a"].shape[0] < 2
        or line_uv["b"].shape[0] < 2
    ):
        return line_a_uv, line_b_uv, {
            "changed_a": False,
            "changed_b": False,
            "intersection_count": 0,
            "trim_count": 0,
            "endpoint_snap_count": 0,
        }

    changed = {"a": False, "b": False}
    trim_count = 0
    endpoint_snap_count = 0
    intersection_count = 0

    line_a = shp_linestring(line_uv["a"])
    line_b = shp_linestring(line_uv["b"])
    if line_a.intersects(line_b):
        raw_points = extract_intersection_uv_points(line_a.intersection(line_b))
        intersection_points = []
        for point in raw_points:
            if any(
                np.linalg.norm(point - saved) <= float(tolerance)
                for saved in intersection_points
            ):
                continue
            intersection_points.append(point)

        for point in intersection_points:
            intersection_count += 1
            before_a = line_uv["a"]
            before_b = line_uv["b"]
            out_a = insert_uv_point_on_line(before_a, point, tolerance=tolerance)
            out_a = dedupe_consecutive_uv(out_a, tolerance=tolerance)
            out_b = insert_uv_point_on_line(before_b, point, tolerance=tolerance)
            out_b = dedupe_consecutive_uv(out_b, tolerance=tolerance)
            if uv_coords_changed(before_a, out_a, tolerance=tolerance):
                changed["a"] = True
            if uv_coords_changed(before_b, out_b, tolerance=tolerance):
                changed["b"] = True
            line_uv["a"] = out_a
            line_uv["b"] = out_b

            for key in ("a", "b"):
                before = line_uv[key]
                nearest_endpoint_dist = min(
                    float(np.linalg.norm(point - before[0])),
                    float(np.linalg.norm(point - before[-1])),
                )
                if nearest_endpoint_dist > float(max_distance) + float(tolerance):
                    continue
                trimmed, did_trim = trim_uv_terminal_branch(
                    before,
                    point,
                    max_distance=max_distance,
                    tolerance=tolerance,
                )
                line_uv[key] = trimmed
                if did_trim:
                    changed[key] = True
                    trim_count += 1

    for key, target_key in (("a", "b"), ("b", "a")):
        current_uv = line_uv[key]
        if current_uv is None or current_uv.shape[0] < 2:
            continue
        for mode, anchor, direction in uv_endpoint_extension_candidates(current_uv):
            ray_end = anchor + direction * float(max_distance)
            ray = shp_linestring([anchor, ray_end])
            other_line = shp_linestring(line_uv[target_key])
            candidates = extract_intersection_uv_points(ray.intersection(other_line))

            best_point = None
            best_dist = None
            for candidate in candidates:
                vec = candidate - anchor
                proj = float(vec[0] * direction[0] + vec[1] * direction[1])
                if (
                    proj < -float(tolerance)
                    or proj > float(max_distance) + float(tolerance)
                ):
                    continue
                if best_dist is None or proj < best_dist:
                    best_dist = proj
                    best_point = candidate

            if best_point is None or best_dist is None:
                continue

            active_before = line_uv[key]
            if mode == "append":
                if (
                    best_dist > float(tolerance)
                    and np.linalg.norm(best_point - active_before[-1]) > float(tolerance)
                ):
                    active_after = np.concatenate(
                        (active_before, best_point.reshape(1, 2)), axis=0
                    )
                    line_uv[key] = dedupe_consecutive_uv(
                        active_after, tolerance=tolerance
                    )
                    changed[key] = True
                    endpoint_snap_count += 1
            else:
                if (
                    best_dist > float(tolerance)
                    and np.linalg.norm(best_point - active_before[0]) > float(tolerance)
                ):
                    active_after = np.concatenate(
                        (best_point.reshape(1, 2), active_before), axis=0
                    )
                    line_uv[key] = dedupe_consecutive_uv(
                        active_after, tolerance=tolerance
                    )
                    changed[key] = True
                    endpoint_snap_count += 1

            target_before = line_uv[target_key]
            target_after = insert_uv_point_on_line(
                target_before, best_point, tolerance=tolerance
            )
            target_after = dedupe_consecutive_uv(target_after, tolerance=tolerance)
            if uv_coords_changed(target_before, target_after, tolerance=tolerance):
                line_uv[target_key] = target_after
                changed[target_key] = True

    return line_uv["a"], line_uv["b"], {
        "changed_a": bool(changed["a"]),
        "changed_b": bool(changed["b"]),
        "intersection_count": int(intersection_count),
        "trim_count": int(trim_count),
        "endpoint_snap_count": int(endpoint_snap_count),
    }


def extend_uv_line_for_splitter(line_uv=None, factor=100.0, tolerance=1.0e-12):
    """Extend the terminal segments of a 2D polyline for robust T/touch splitting."""
    uv = dedupe_consecutive_uv(line_uv, tolerance=tolerance)
    if uv is None or uv.shape[0] < 2:
        return uv

    out = uv.astype(float, copy=True)

    first_vec = out[0] - out[1]
    first_len = float(np.linalg.norm(first_vec))
    if first_len > float(tolerance):
        out[0] = out[0] + (first_vec / first_len) * first_len * (float(factor) - 1.0)

    last_vec = out[-1] - out[-2]
    last_len = float(np.linalg.norm(last_vec))
    if last_len > float(tolerance):
        out[-1] = out[-1] + (last_vec / last_len) * last_len * (float(factor) - 1.0)

    return out


def split_uv_line_by_line(
    paper_uv=None,
    scissors_uv=None,
    extension_factor=100.0,
    tolerance=1.0e-8,
):
    """
    Split one 2D polyline by another 2D polyline.

    Returns a list of split coordinate arrays. An empty list means no valid split
    occurred. The splitter is extended when the two lines only touch or form a T.
    """
    paper = dedupe_consecutive_uv(paper_uv, tolerance=tolerance)
    scissors = dedupe_consecutive_uv(scissors_uv, tolerance=tolerance)
    if (
        paper is None
        or scissors is None
        or paper.shape[0] < 2
        or scissors.shape[0] < 2
    ):
        return []

    paper_line = shp_linestring(paper)
    scissors_line = shp_linestring(scissors)
    splitter = scissors_line

    if not paper_line.crosses(scissors_line):
        extended_scissors = extend_uv_line_for_splitter(
            scissors, factor=extension_factor, tolerance=tolerance
        )
        if extended_scissors is not None and extended_scissors.shape[0] >= 2:
            splitter = shp_linestring(extended_scissors)

    if not paper_line.intersects(splitter):
        return []

    try:
        split_lines = shp_split(paper_line, splitter)
    except Exception:
        return []

    if len(split_lines.geoms) < 2:
        return []

    pieces = []
    for geom in split_lines.geoms:
        if geom.is_empty or not hasattr(geom, "coords"):
            continue
        coords = dedupe_consecutive_uv(
            np.asarray(geom.coords, dtype=float),
            tolerance=tolerance,
        )
        if coords is not None and coords.shape[0] >= 2:
            pieces.append(coords)

    return pieces if len(pieces) >= 2 else []
