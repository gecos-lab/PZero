"""
Bridge for C++ MeshIt triunsuitable behavior in the Python workflow.

Triangle's Python wrapper does not expose the original C callback hook used by
MeshIt (`triunsuitable` with switch `-u`). This module ports the exact
`triunsuitable` criterion from the C++ code and applies it iteratively by
inserting Steiner points at centroids of unsuitable triangles.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

import numpy as np
import triangle as tr

ONETHIRD = 1.0 / 3.0


def _normalize_feature_inputs(
    feature_points: np.ndarray,
    feature_sizes: np.ndarray,
    mesh_size: float,
) -> tuple[np.ndarray, np.ndarray]:
    pts = np.asarray(feature_points, dtype=np.float64)
    if pts.size == 0:
        return np.empty((0, 2), dtype=np.float64), np.empty((0,), dtype=np.float64)
    if pts.ndim == 1:
        pts = pts.reshape(1, -1)
    if pts.shape[1] != 2:
        raise ValueError("feature_points must have shape (N, 2)")

    sizes = np.asarray(feature_sizes, dtype=np.float64).reshape(-1)
    if sizes.size == 0:
        sizes = np.full((pts.shape[0],), float(mesh_size), dtype=np.float64)
    elif sizes.size == 1 and pts.shape[0] > 1:
        sizes = np.full((pts.shape[0],), float(sizes[0]), dtype=np.float64)
    elif sizes.size != pts.shape[0]:
        n = min(pts.shape[0], sizes.shape[0])
        pts = pts[:n]
        sizes = sizes[:n]

    sizes = np.clip(sizes, 1e-12, max(float(mesh_size), 1e-12))
    return pts, sizes


def triunsuitable_mask(
    vertices: np.ndarray,
    triangles: np.ndarray,
    gradient: float,
    mesh_size: float,
    feature_points: Optional[np.ndarray] = None,
    feature_sizes: Optional[np.ndarray] = None,
) -> np.ndarray:
    """
    Vectorized port of MeshIt C++ `triunsuitable(...)` from `core.cpp`.
    """
    verts = np.asarray(vertices, dtype=np.float64)
    tris = np.asarray(triangles, dtype=np.int32)
    if tris.size == 0:
        return np.zeros((0,), dtype=bool)

    tri_pts = verts[tris]  # (T,3,2)

    dxoa = tri_pts[:, 0, 0] - tri_pts[:, 2, 0]
    dyoa = tri_pts[:, 0, 1] - tri_pts[:, 2, 1]
    dxda = tri_pts[:, 1, 0] - tri_pts[:, 2, 0]
    dyda = tri_pts[:, 1, 1] - tri_pts[:, 2, 1]
    dxod = tri_pts[:, 0, 0] - tri_pts[:, 1, 0]
    dyod = tri_pts[:, 0, 1] - tri_pts[:, 1, 1]

    oalen = dxoa * dxoa + dyoa * dyoa
    dalen = dxda * dxda + dyda * dyda
    odlen = dxod * dxod + dyod * dyod
    sq_meanlen = ONETHIRD * (oalen + dalen + odlen)

    sq_meshsize = float(mesh_size) * float(mesh_size)
    unsuitable = sq_meanlen > sq_meshsize

    if feature_points is None or feature_sizes is None:
        return unsuitable

    fpts, fsizes = _normalize_feature_inputs(
        feature_points=feature_points,
        feature_sizes=feature_sizes,
        mesh_size=mesh_size,
    )
    if fpts.size == 0:
        return unsuitable

    sq_grad = float(gradient) * float(gradient)
    if sq_grad <= 0.0:
        return unsuitable

    centroids = tri_pts.mean(axis=1)
    diff = centroids[:, None, :] - fpts[None, :, :]
    sq_dist = np.sum(diff * diff, axis=2)
    sq_ref = fsizes[None, :] * fsizes[None, :]

    # Directly mirrors the C++ inequality checks.
    influence = sq_dist < (sq_grad * (sq_meshsize - sq_ref))
    local_limit = (sq_dist / sq_grad) + sq_ref
    local_unsuitable = np.any(influence & (sq_meanlen[:, None] > local_limit), axis=1)

    return unsuitable | local_unsuitable


def _dedupe_points(points: np.ndarray, tol: float) -> np.ndarray:
    if points.size == 0:
        return points
    if points.shape[0] <= 1:
        return points
    scale = max(float(tol), 1e-12)
    keys = np.round(points / scale).astype(np.int64)
    _, first_idx = np.unique(keys, axis=0, return_index=True)
    return points[np.sort(first_idx)]


def _filter_far_from_existing(
    candidates: np.ndarray,
    existing_vertices: np.ndarray,
    min_spacing: float,
) -> np.ndarray:
    if candidates.size == 0:
        return candidates
    if existing_vertices.size == 0:
        return candidates
    try:
        from scipy.spatial import cKDTree

        tree = cKDTree(existing_vertices)
        dists, _ = tree.query(candidates, k=1)
        return candidates[dists > min_spacing]
    except Exception:
        # Small fallback when scipy/kdtree is unavailable.
        out = []
        min_sq = float(min_spacing) * float(min_spacing)
        for c in candidates:
            diff = existing_vertices - c
            sq = np.sum(diff * diff, axis=1)
            if np.all(sq > min_sq):
                out.append(c)
        if not out:
            return np.empty((0, 2), dtype=np.float64)
        return np.asarray(out, dtype=np.float64)


def triangulate_with_cpp_triunsuitable(
    tri_input: Dict,
    tri_options: str,
    gradient: float,
    mesh_size: float,
    feature_points: np.ndarray,
    feature_sizes: np.ndarray,
    max_iterations: int = 8,
    max_new_points: int = 2500,
    min_point_spacing: Optional[float] = None,
    logger: Optional[logging.Logger] = None,
) -> Dict:
    """
    Run Triangle and emulate C++ `-u` unsuitable refinement iteratively.
    """
    log = logger or logging.getLogger(__name__)

    current_vertices = np.asarray(tri_input.get("vertices"), dtype=np.float64)
    if current_vertices.ndim != 2 or current_vertices.shape[1] != 2:
        raise ValueError("tri_input['vertices'] must be shape (N, 2)")

    segments = tri_input.get("segments")
    holes = tri_input.get("holes")
    if segments is not None:
        segments = np.asarray(segments, dtype=np.int32)
    if holes is not None and len(holes) > 0:
        holes = np.asarray(holes, dtype=np.float64)

    fpts, fsizes = _normalize_feature_inputs(
        feature_points=feature_points,
        feature_sizes=feature_sizes,
        mesh_size=mesh_size,
    )

    if fpts.size == 0:
        return tr.triangulate(tri_input, tri_options)

    if min_point_spacing is None:
        min_sz = float(np.min(fsizes)) if fsizes.size else float(mesh_size)
        min_point_spacing = max(1e-10, min(min_sz, float(mesh_size)) * 0.2)

    total_added = 0
    result = {}

    for it in range(max_iterations + 1):
        run_input = {"vertices": current_vertices}
        if segments is not None and len(segments) > 0:
            run_input["segments"] = segments
        if holes is not None and len(holes) > 0:
            run_input["holes"] = holes

        result = tr.triangulate(run_input, tri_options)
        if "triangles" not in result or len(result["triangles"]) == 0:
            log.warning("triunsuitable bridge produced an empty triangulation; returning last result")
            return result

        verts = np.asarray(result["vertices"], dtype=np.float64)
        tris = np.asarray(result["triangles"], dtype=np.int32)
        bad_mask = triunsuitable_mask(
            vertices=verts,
            triangles=tris,
            gradient=gradient,
            mesh_size=mesh_size,
            feature_points=fpts,
            feature_sizes=fsizes,
        )
        bad_count = int(np.count_nonzero(bad_mask))
        if bad_count == 0:
            if it > 0:
                log.info(
                    "C++ triunsuitable bridge converged in %d iteration(s); added %d Steiner points",
                    it,
                    total_added,
                )
            return result

        if it >= max_iterations:
            log.info(
                "C++ triunsuitable bridge hit max iterations (%d); remaining unsuitable triangles: %d",
                max_iterations,
                bad_count,
            )
            return result

        centroids = verts[tris[bad_mask]].mean(axis=1)
        centroids = _dedupe_points(centroids, tol=min_point_spacing * 0.5)
        centroids = _filter_far_from_existing(
            candidates=centroids,
            existing_vertices=verts,
            min_spacing=float(min_point_spacing),
        )

        if centroids.size == 0:
            log.info(
                "C++ triunsuitable bridge stopped early: no valid Steiner centroids after filtering "
                "(remaining unsuitable triangles: %d)",
                bad_count,
            )
            return result

        remaining = max_new_points - total_added
        if remaining <= 0:
            log.info(
                "C++ triunsuitable bridge reached max new points (%d); stopping",
                max_new_points,
            )
            return result

        if centroids.shape[0] > remaining:
            centroids = centroids[:remaining]

        current_vertices = np.vstack([current_vertices, centroids])
        total_added += int(centroids.shape[0])

    return result