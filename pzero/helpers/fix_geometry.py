"""fix_geometry.py
Interactive `Fix Geometry` tool for TriSurf entities.

Provides a dialog that lets the user clean, decimate, smooth, flatten,
refine (subdivide), fill holes, and clip a triangulated surface, with
live 3D preview inside the current PZero 3D view.

The goal is to produce a TriSurf whose geometry is numerically well
conditioned for downstream re-meshing in PyMeshIT (i.e. no duplicated
points, no degenerate / near-degenerate triangles, no tiny holes, low
curvature relative to the target edge length).

PZero  (c)  Andrea Bistacchi
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
import pyvista as pv
from vtkmodules.vtkFiltersCore import vtkDelaunay3D
from vtkmodules.vtkFiltersGeometry import vtkDataSetSurfaceFilter
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..entities_factory import TriSurf
from .helper_functions import best_fitting_plane

# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------

#: Collections that are scanned for TriSurf entities.
TRISURF_COLLECTIONS: Tuple[str, ...] = (
    "geol_coll",
    "boundary_coll",
    "fluid_coll",
    "backgrnd_coll",
)

#: Name of the preview actor registered in the plotter.
PREVIEW_ACTOR_NAME: str = "fix_geometry_preview"

#: Debounce delay in milliseconds between a parameter change and a preview rebuild.
PREVIEW_DEBOUNCE_MS: int = 120

#: Opacity of the original surface while the dialog is open (translucent
#: wireframe for visual comparison with the preview).
ORIGINAL_GHOST_OPACITY: float = 0.20

#: Default preview color (yellow = "draft geometry").
PREVIEW_COLOR: Tuple[float, float, float] = (1.0, 0.85, 0.15)

#: Default preview edge color.
PREVIEW_EDGE_COLOR: Tuple[float, float, float] = (0.15, 0.15, 0.15)


# -----------------------------------------------------------------------------
# Geometry helpers
# -----------------------------------------------------------------------------


def _bbox_diagonal(poly: pv.PolyData) -> float:
    """Return the diagonal length of the axis-aligned bounding box.

    Falls back to 1.0 for empty / invalid meshes so that downstream
    tolerances never become zero.
    """
    if poly is None or poly.n_points == 0:
        return 1.0
    xmin, xmax, ymin, ymax, zmin, zmax = poly.bounds
    diag = float(
        np.sqrt((xmax - xmin) ** 2 + (ymax - ymin) ** 2 + (zmax - zmin) ** 2)
    )
    return diag if diag > 0.0 else 1.0


def _unit_vector(vec: np.ndarray) -> Optional[np.ndarray]:
    """Return `vec` normalized, or `None` if its norm is too small."""
    arr = np.asarray(vec, dtype=float)
    norm = float(np.linalg.norm(arr))
    if norm <= 1e-12:
        return None
    return arr / norm


def _to_pyvista_triangles(vtk_trisurf) -> pv.PolyData:
    """Wrap a TriSurf as a pure-triangle PyVista PolyData.

    Shallow copy is enough because all filters below return new objects.
    """
    poly = pv.wrap(vtk_trisurf)
    if not isinstance(poly, pv.PolyData):
        poly = pv.PolyData(poly)
    return poly.triangulate()


def _convex_hull_polydata(points: np.ndarray) -> Optional[pv.PolyData]:
    """Compute the 3D convex hull of `points` as a triangulated PolyData.

    Returns `None` if the hull cannot be built (collinear / coplanar
    clouds or not enough points).
    """
    if points is None or points.shape[0] < 4:
        return None
    try:
        poly_pts = pv.PolyData(np.asarray(points, dtype=float))
        del3d = vtkDelaunay3D()
        del3d.SetInputData(poly_pts)
        del3d.Update()
        surf = vtkDataSetSurfaceFilter()
        surf.SetInputConnection(del3d.GetOutputPort())
        surf.Update()
        hull = pv.wrap(surf.GetOutput())
        if not isinstance(hull, pv.PolyData):
            hull = pv.PolyData(hull)
        hull = hull.triangulate()
        if hull.n_cells == 0:
            return None
        return hull
    except Exception:
        return None


def _blend_toward_convex_hull(
    points: np.ndarray, blend: float
) -> np.ndarray:
    """Move points toward their closest projection on the convex hull.

    This is the operation to "remove concave features" from a surface:
    vertices already on the convex hull stay put (they are the extremal
    ones), while vertices in concave pockets are pulled outward onto the
    hull surface.

    Parameters
    ----------
    points:
        Array of shape (n, 3).
    blend:
        Blend factor in [0, 1]. 0 returns `points` unchanged, 1 projects
        every vertex onto the hull, intermediate values partially
        "convexify" the geometry.
    """
    if blend <= 0.0 or points.shape[0] < 4:
        return points
    blend = float(min(max(blend, 0.0), 1.0))
    hull = _convex_hull_polydata(points)
    if hull is None:
        return points
    try:
        _, closest = hull.find_closest_cell(
            np.asarray(points, dtype=float), return_closest_point=True
        )
    except TypeError:
        return points
    except Exception:
        return points
    closest = np.asarray(closest)
    if closest.shape != points.shape:
        return points
    return points + blend * (closest - points)


def _project_to_plane(points: np.ndarray, blend: float) -> np.ndarray:
    """Blend `points` toward their best-fit plane.

    Parameters
    ----------
    points:
        Array of shape (n, 3).
    blend:
        Blend factor in [0, 1]. 0 returns `points` unchanged,
        1 returns the fully planar projection.
    """
    if blend <= 0.0 or points.shape[0] < 3:
        return points
    blend = float(min(max(blend, 0.0), 1.0))
    center, normal = best_fitting_plane(points)
    normal = normal / (np.linalg.norm(normal) + 1e-12)
    offsets = np.dot(points - center, normal)
    projected = points - np.outer(offsets, normal)
    return points + blend * (projected - points)


def _fallback_in_plane_axis(
    normal: np.ndarray, preferred: Tuple[float, float, float]
) -> np.ndarray:
    """Return a stable in-plane axis as close as possible to `preferred`."""
    refs = [np.asarray(preferred, dtype=float)]
    refs.extend(
        [
            np.array([1.0, 0.0, 0.0]),
            np.array([0.0, 1.0, 0.0]),
            np.array([0.0, 0.0, 1.0]),
        ]
    )
    for ref in refs:
        tangent = ref - np.dot(ref, normal) * normal
        axis = _unit_vector(tangent)
        if axis is not None:
            return axis
    return np.array([1.0, 0.0, 0.0], dtype=float)


def _surface_local_frame(
    points: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Build a stable local `(u, v, n)` frame for a near-planar TriSurf.

    `u` follows the dominant in-plane geometric axis, while its sign and
    `v`'s sign are oriented as consistently as possible with world-space
    references so that `left/right/up/down` feel stable across previews.
    """
    center, normal = best_fitting_plane(points)
    normal = _unit_vector(normal)
    if normal is None:
        normal = np.array([0.0, 0.0, 1.0], dtype=float)

    centered = np.asarray(points, dtype=float) - center
    planar = centered - np.outer(np.dot(centered, normal), normal)

    u_axis = None
    try:
        _, _, vh = np.linalg.svd(planar, full_matrices=False)
        if vh.size:
            candidate = vh[0]
            candidate = candidate - np.dot(candidate, normal) * normal
            u_axis = _unit_vector(candidate)
    except Exception:
        u_axis = None
    if u_axis is None:
        u_axis = _fallback_in_plane_axis(normal, (1.0, 0.0, 0.0))

    u_ref = _fallback_in_plane_axis(normal, (1.0, 0.0, 0.0))
    if float(np.dot(u_axis, u_ref)) < 0.0:
        u_axis = -u_axis

    v_axis = _unit_vector(np.cross(normal, u_axis))
    if v_axis is None:
        v_axis = _fallback_in_plane_axis(normal, (0.0, 0.0, 1.0))

    v_ref = _fallback_in_plane_axis(normal, (0.0, 0.0, 1.0))
    if float(np.dot(v_axis, v_ref)) < 0.0:
        v_axis = -v_axis

    local_points = np.column_stack(
        [
            np.dot(centered, u_axis),
            np.dot(centered, v_axis),
            np.dot(centered, normal),
        ]
    )
    return center, u_axis, v_axis, normal, local_points


def _apply_side_clip(
    mesh: pv.PolyData, params: Dict[str, object]
) -> pv.PolyData:
    """Clip `mesh` from one local side using a planar trim.

    The clip plane is defined in the surface local frame, so `left`,
    `right`, `up`, and `down` follow the current TriSurf orientation
    instead of the global XYZ axes.
    """
    if mesh is None or mesh.n_points < 3 or mesh.n_cells == 0:
        return mesh

    clip_enabled = bool(params.get("clip_enabled", False))
    if not clip_enabled:
        return mesh

    clip_side = str(params.get("clip_side", "left")).lower()
    clip_mode = str(params.get("clip_mode", "length")).lower()
    clip_length = max(float(params.get("clip_length", 0.0)), 0.0)
    clip_extent = max(float(params.get("clip_extent", 0.0)), 0.0)
    if clip_length <= 0.0 and clip_extent <= 0.0:
        return mesh

    center, u_axis, v_axis, normal, local_points = _surface_local_frame(
        np.asarray(mesh.points)
    )
    u_min, u_max = float(local_points[:, 0].min()), float(local_points[:, 0].max())
    v_min, v_max = float(local_points[:, 1].min()), float(local_points[:, 1].max())
    u_span = u_max - u_min
    v_span = v_max - v_min

    if clip_side in ("left", "right"):
        side_span = u_span
        axis_normal = (1.0, 0.0, 0.0)
    else:
        side_span = v_span
        axis_normal = (0.0, 1.0, 0.0)
    if side_span <= 1e-12:
        return mesh

    if clip_mode == "extent":
        trim = clip_extent * side_span
    else:
        trim = clip_length
    trim = min(max(trim, 0.0), max(side_span - 1e-9, 0.0))
    if trim <= 0.0:
        return mesh

    local_mesh = mesh.copy(deep=True)
    local_mesh.points = local_points

    if clip_side == "left":
        origin = (u_min + trim, 0.0, 0.0)
        invert = False
    elif clip_side == "right":
        origin = (u_max - trim, 0.0, 0.0)
        invert = True
    elif clip_side == "down":
        origin = (0.0, v_min + trim, 0.0)
        invert = False
    else:  # "up"
        origin = (0.0, v_max - trim, 0.0)
        invert = True

    clipped = local_mesh.clip(normal=axis_normal, origin=origin, invert=invert)
    clipped = clipped.clean(
        tolerance=0.0,
        absolute=True,
        lines_to_points=False,
        polys_to_lines=False,
        strips_to_polys=False,
    ).triangulate()
    if clipped.n_points == 0 or clipped.n_cells == 0:
        return clipped

    basis = np.column_stack((u_axis, v_axis, normal))
    clipped.points = np.asarray(clipped.points) @ basis.T + center
    return clipped.clean(
        tolerance=0.0,
        absolute=True,
        lines_to_points=False,
        polys_to_lines=False,
        strips_to_polys=False,
    ).triangulate()


def _apply_fix_pipeline(
    source: pv.PolyData, params: Dict[str, object]
) -> pv.PolyData:
    """Run the configured sequence of filters on `source`.

    The pipeline order matters: clean first to remove duplicates and
    degenerate triangles, then topology-changing steps (fill holes,
    decimation, subdivision), then geometry-only steps (smoothing,
    planar projection), and finally optional side clipping.
    """
    mesh = source.triangulate()

    diag = _bbox_diagonal(mesh)

    # 1. Clean / merge duplicate points.
    clean_tol = float(params.get("clean_tol_rel", 0.0))
    if clean_tol > 0.0:
        mesh = mesh.clean(
            tolerance=clean_tol * diag,
            absolute=True,
            lines_to_points=False,
            polys_to_lines=False,
            strips_to_polys=False,
        )

    # 2. Fill small holes (helps PLCs that must be watertight).
    hole_size_rel = float(params.get("fill_holes_rel", 0.0))
    if hole_size_rel > 0.0 and mesh.n_points > 0:
        mesh = mesh.fill_holes(hole_size_rel * diag)
        mesh = mesh.triangulate()

    # 3. Decimation: reduce triangle count to simplify.
    target_reduction = float(params.get("decimate_target", 0.0))
    if target_reduction > 0.0 and mesh.n_cells > 4:
        algorithm = str(params.get("decimate_algorithm", "decimate_pro"))
        feature_angle = float(params.get("decimate_feature_angle", 45.0))
        preserve_topology = bool(params.get("decimate_preserve_topology", True))
        boundary_vertex_deletion = bool(
            params.get("decimate_boundary_deletion", False)
        )
        if algorithm == "decimate":
            mesh = mesh.decimate(
                target_reduction=target_reduction,
                volume_preservation=True,
            )
        else:
            mesh = mesh.decimate_pro(
                reduction=target_reduction,
                feature_angle=feature_angle,
                preserve_topology=preserve_topology,
                boundary_vertex_deletion=boundary_vertex_deletion,
            )
        mesh = mesh.triangulate()

    # 4. Subdivision: densify for smoother downstream meshing.
    subdivisions = int(params.get("subdivide_levels", 0))
    if subdivisions > 0 and mesh.n_cells > 0:
        subfilter = str(params.get("subdivide_type", "linear"))
        try:
            mesh = mesh.subdivide(subdivisions, subfilter=subfilter)
        except Exception:
            mesh = mesh.subdivide(subdivisions, subfilter="linear")
        mesh = mesh.triangulate()

    # 5. Smoothing: curvature / noise reduction.
    smooth_method = str(params.get("smooth_method", "none"))
    smooth_iters = int(params.get("smooth_iterations", 0))
    if smooth_method != "none" and smooth_iters > 0 and mesh.n_points > 0:
        boundary_smoothing = bool(params.get("smooth_boundary", False))
        feature_smoothing = bool(params.get("smooth_feature", False))
        feature_angle = float(params.get("smooth_feature_angle", 45.0))
        edge_angle = float(params.get("smooth_edge_angle", 15.0))
        if smooth_method == "laplacian":
            relaxation = float(params.get("smooth_relaxation", 0.1))
            mesh = mesh.smooth(
                n_iter=smooth_iters,
                relaxation_factor=relaxation,
                feature_smoothing=feature_smoothing,
                boundary_smoothing=boundary_smoothing,
                feature_angle=feature_angle,
                edge_angle=edge_angle,
            )
        else:
            pass_band = float(params.get("smooth_pass_band", 0.1))
            try:
                mesh = mesh.smooth_taubin(
                    n_iter=smooth_iters,
                    pass_band=pass_band,
                    feature_smoothing=feature_smoothing,
                    boundary_smoothing=boundary_smoothing,
                    feature_angle=feature_angle,
                    edge_angle=edge_angle,
                    normalize_coordinates=True,
                )
            except TypeError:
                mesh = mesh.smooth_taubin(
                    n_iter=smooth_iters,
                    pass_band=pass_band,
                )

    # 6. Remove concave features by blending vertices toward the convex hull.
    convex_blend = float(params.get("convex_blend", 0.0))
    if convex_blend > 0.0 and mesh.n_points >= 4:
        pts = np.asarray(mesh.points)
        new_pts = _blend_toward_convex_hull(pts, convex_blend)
        if new_pts.shape == pts.shape:
            mesh.points = new_pts

    # 7. Planar projection blend (reduce overall curvature).
    planarity = float(params.get("planarity_blend", 0.0))
    if planarity > 0.0 and mesh.n_points >= 3:
        pts = np.asarray(mesh.points)
        new_pts = _project_to_plane(pts, planarity)
        mesh.points = new_pts

    # 8. Trim one side with a local planar clip.
    mesh = _apply_side_clip(mesh, params)

    # Always end with a triangulated, compacted mesh.
    mesh = mesh.clean(
        tolerance=0.0,
        absolute=True,
        lines_to_points=False,
        polys_to_lines=False,
        strips_to_polys=False,
    ).triangulate()
    return mesh


def _pyvista_to_trisurf(source: pv.PolyData) -> TriSurf:
    """Build a fresh TriSurf that owns a deep copy of `source` geometry."""
    out = TriSurf()
    out.DeepCopy(source)
    return out


def _mesh_quality_stats(mesh: pv.PolyData) -> Dict[str, float]:
    """Compute a few quality indicators useful for the mesh engineer.

    Returns edge-length statistics and the minimum triangle area.
    """
    stats = {
        "n_points": float(mesh.n_points),
        "n_cells": float(mesh.n_cells),
        "edge_min": 0.0,
        "edge_mean": 0.0,
        "edge_max": 0.0,
        "area_min": 0.0,
    }
    if mesh.n_cells == 0:
        return stats
    try:
        qual = mesh.compute_cell_sizes(
            length=False, area=True, volume=False
        )
        areas = np.asarray(qual.cell_data["Area"])
        stats["area_min"] = float(np.min(areas)) if areas.size else 0.0
    except Exception:
        pass
    try:
        edges = mesh.extract_all_edges()
        pts = np.asarray(edges.points)
        lines = edges.lines.reshape(-1, 3)[:, 1:3]
        if lines.size:
            e_lengths = np.linalg.norm(pts[lines[:, 0]] - pts[lines[:, 1]], axis=1)
            stats["edge_min"] = float(e_lengths.min())
            stats["edge_mean"] = float(e_lengths.mean())
            stats["edge_max"] = float(e_lengths.max())
    except Exception:
        pass
    return stats


# -----------------------------------------------------------------------------
# Dialog
# -----------------------------------------------------------------------------


class FixGeometryDialog(QDialog):
    """Interactive dialog that fixes the geometry of a selected TriSurf.

    Usage
    -----
    ``FixGeometryDialog(view).exec()``

    The dialog reads the list of TriSurf entities from the project
    collections, renders a live preview in ``view.plotter`` and, on
    `Apply`, replaces the underlying vtk object via
    ``collection.replace_vtk`` (which in turn updates all open views).
    """

    def __init__(self, view, parent=None):
        super().__init__(parent or view)
        self.view = view
        self.project = view.parent

        self.setWindowTitle("Fix Geometry")
        self.setModal(False)
        self.resize(460, 720)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(PREVIEW_DEBOUNCE_MS)
        self._debounce.timeout.connect(self._rebuild_preview)

        self._candidates: List[Tuple[str, str, str]] = []
        self._current_uid: Optional[str] = None
        self._current_coll: Optional[str] = None
        self._original_opacity: Optional[float] = None
        self._original_visibility: Optional[bool] = None
        self._last_result: Optional[pv.PolyData] = None

        self._build_ui()
        self._populate_candidates()

        if self._candidates:
            self._on_entity_changed(0)

    # ------------------------------------------------------------------ UI ---

    def _build_ui(self) -> None:
        """Assemble all widgets grouped by semantic section."""
        root = QVBoxLayout(self)

        # Entity selector.
        entity_group = QGroupBox("Target TriSurf")
        entity_form = QFormLayout(entity_group)
        self.entity_combo = QComboBox()
        self.entity_combo.currentIndexChanged.connect(self._on_entity_changed)
        entity_form.addRow("Entity:", self.entity_combo)
        root.addWidget(entity_group)

        # Scroll area for parameters so the dialog stays usable on small screens.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        scroll.setWidget(content)
        params_layout = QVBoxLayout(content)

        params_layout.addWidget(self._build_clean_group())
        params_layout.addWidget(self._build_decimate_group())
        params_layout.addWidget(self._build_subdivide_group())
        params_layout.addWidget(self._build_smooth_group())
        params_layout.addWidget(self._build_convex_group())
        params_layout.addWidget(self._build_planar_group())
        params_layout.addWidget(self._build_clip_group())
        params_layout.addStretch(1)

        root.addWidget(scroll, 1)

        # Stats readout.
        self.stats_label = QLabel("-")
        self.stats_label.setWordWrap(True)
        self.stats_label.setStyleSheet("color: #555; font-family: monospace;")
        root.addWidget(self.stats_label)

        # Preview toggle and helper buttons.
        preview_row = QHBoxLayout()
        self.preview_check = QCheckBox("Live preview")
        self.preview_check.setChecked(True)
        self.preview_check.toggled.connect(self._on_preview_toggled)
        preview_row.addWidget(self.preview_check)
        self.clear_preview_button = QPushButton("Clear preview")
        self.clear_preview_button.setToolTip(
            "Remove the preview actor from the 3D view and restore\n"
            "the original surface to its normal opacity."
        )
        self.clear_preview_button.clicked.connect(self._clear_preview)
        preview_row.addWidget(self.clear_preview_button)
        self.reset_button = QPushButton("Reset parameters")
        self.reset_button.clicked.connect(self._reset_parameters)
        preview_row.addWidget(self.reset_button)
        preview_row.addStretch(1)
        root.addLayout(preview_row)

        # OK / Apply / Cancel.
        buttons = QDialogButtonBox(
            QDialogButtonBox.Apply | QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.button(QDialogButtonBox.Apply).clicked.connect(self._on_apply)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self._on_cancel)
        root.addWidget(buttons)

    def _build_clean_group(self) -> QGroupBox:
        group = QGroupBox("1. Clean and repair")
        form = QFormLayout(group)

        self.clean_tol_spin = QDoubleSpinBox()
        self.clean_tol_spin.setDecimals(5)
        self.clean_tol_spin.setRange(0.0, 0.1)
        self.clean_tol_spin.setSingleStep(0.0005)
        self.clean_tol_spin.setValue(0.0)
        self.clean_tol_spin.setToolTip(
            "Merge duplicate / near-duplicate points.\n"
            "Expressed as a fraction of the bounding-box diagonal.\n"
            "Keep at 0 for an identity initial preview."
        )
        self.clean_tol_spin.valueChanged.connect(self._schedule_preview)
        form.addRow("Merge tolerance (rel):", self.clean_tol_spin)

        self.fill_holes_spin = QDoubleSpinBox()
        self.fill_holes_spin.setDecimals(3)
        self.fill_holes_spin.setRange(0.0, 2.0)
        self.fill_holes_spin.setSingleStep(0.01)
        self.fill_holes_spin.setValue(0.0)
        self.fill_holes_spin.setToolTip(
            "Maximum hole size (relative to bbox diagonal).\n"
            "0 disables hole filling."
        )
        self.fill_holes_spin.valueChanged.connect(self._schedule_preview)
        form.addRow("Fill holes up to (rel):", self.fill_holes_spin)

        return group

    def _build_decimate_group(self) -> QGroupBox:
        group = QGroupBox("2. Decimate (reduce triangle count)")
        form = QFormLayout(group)

        self.decimate_spin = QDoubleSpinBox()
        self.decimate_spin.setDecimals(3)
        self.decimate_spin.setRange(0.0, 0.99)
        self.decimate_spin.setSingleStep(0.05)
        self.decimate_spin.setValue(0.0)
        self.decimate_spin.setToolTip(
            "Fraction of triangles to remove.\n"
            "0.0 keeps the mesh unchanged; 0.5 halves the count."
        )
        self.decimate_spin.valueChanged.connect(self._schedule_preview)
        form.addRow("Target reduction:", self.decimate_spin)

        self.decimate_algo = QComboBox()
        self.decimate_algo.addItems(["decimate_pro", "decimate"])
        self.decimate_algo.setToolTip(
            "decimate_pro: feature / topology preserving (recommended for "
            "geological surfaces).\ndecimate: quadric-based, volume preserving."
        )
        self.decimate_algo.currentIndexChanged.connect(self._schedule_preview)
        form.addRow("Algorithm:", self.decimate_algo)

        self.decimate_feature_angle = QDoubleSpinBox()
        self.decimate_feature_angle.setRange(1.0, 180.0)
        self.decimate_feature_angle.setValue(45.0)
        self.decimate_feature_angle.setSuffix(" deg")
        self.decimate_feature_angle.valueChanged.connect(self._schedule_preview)
        form.addRow("Feature angle:", self.decimate_feature_angle)

        self.decimate_preserve = QCheckBox("Preserve topology")
        self.decimate_preserve.setChecked(True)
        self.decimate_preserve.toggled.connect(self._schedule_preview)
        form.addRow(self.decimate_preserve)

        self.decimate_boundary_deletion = QCheckBox("Allow boundary vertex deletion")
        self.decimate_boundary_deletion.setChecked(False)
        self.decimate_boundary_deletion.setToolTip(
            "Keep disabled to preserve the surface border\n"
            "so intersections with other surfaces remain clean."
        )
        self.decimate_boundary_deletion.toggled.connect(self._schedule_preview)
        form.addRow(self.decimate_boundary_deletion)

        return group

    def _build_subdivide_group(self) -> QGroupBox:
        group = QGroupBox("3. Subdivide (refine triangle count)")
        form = QFormLayout(group)

        self.subdivide_levels = QSpinBox()
        self.subdivide_levels.setRange(0, 3)
        self.subdivide_levels.setValue(0)
        self.subdivide_levels.setToolTip(
            "Each subdivision level multiplies the triangle count by 4.\n"
            "0 disables subdivision."
        )
        self.subdivide_levels.valueChanged.connect(self._schedule_preview)
        form.addRow("Levels:", self.subdivide_levels)

        self.subdivide_type = QComboBox()
        self.subdivide_type.addItems(["linear", "loop", "butterfly"])
        self.subdivide_type.setToolTip(
            "linear: straight interpolation (keeps shape).\n"
            "loop / butterfly: smooth interpolation (reduces curvature)."
        )
        self.subdivide_type.currentIndexChanged.connect(self._schedule_preview)
        form.addRow("Type:", self.subdivide_type)

        return group

    def _build_smooth_group(self) -> QGroupBox:
        group = QGroupBox("4. Smooth (reduce curvature / noise)")
        form = QFormLayout(group)

        self.smooth_method = QComboBox()
        self.smooth_method.addItems(["none", "laplacian", "taubin"])
        self.smooth_method.setCurrentText("none")
        self.smooth_method.setToolTip(
            "laplacian: fast, shrinks surfaces.\n"
            "taubin: volume preserving (recommended)."
        )
        self.smooth_method.currentIndexChanged.connect(self._schedule_preview)
        form.addRow("Method:", self.smooth_method)

        self.smooth_iterations = QSpinBox()
        self.smooth_iterations.setRange(0, 500)
        self.smooth_iterations.setValue(20)
        self.smooth_iterations.valueChanged.connect(self._schedule_preview)
        form.addRow("Iterations:", self.smooth_iterations)

        self.smooth_relaxation = QDoubleSpinBox()
        self.smooth_relaxation.setDecimals(3)
        self.smooth_relaxation.setRange(0.0, 1.0)
        self.smooth_relaxation.setSingleStep(0.01)
        self.smooth_relaxation.setValue(0.10)
        self.smooth_relaxation.setToolTip("Laplacian relaxation factor.")
        self.smooth_relaxation.valueChanged.connect(self._schedule_preview)
        form.addRow("Relaxation (laplacian):", self.smooth_relaxation)

        self.smooth_pass_band = QDoubleSpinBox()
        self.smooth_pass_band.setDecimals(3)
        self.smooth_pass_band.setRange(0.001, 2.0)
        self.smooth_pass_band.setSingleStep(0.01)
        self.smooth_pass_band.setValue(0.10)
        self.smooth_pass_band.setToolTip(
            "Taubin pass band: smaller values = stronger smoothing."
        )
        self.smooth_pass_band.valueChanged.connect(self._schedule_preview)
        form.addRow("Pass band (taubin):", self.smooth_pass_band)

        self.smooth_boundary = QCheckBox("Smooth boundary")
        self.smooth_boundary.setChecked(False)
        self.smooth_boundary.setToolTip(
            "Keep disabled to preserve the surface border for intersections."
        )
        self.smooth_boundary.toggled.connect(self._schedule_preview)
        form.addRow(self.smooth_boundary)

        self.smooth_feature = QCheckBox("Smooth feature edges")
        self.smooth_feature.setChecked(False)
        self.smooth_feature.toggled.connect(self._schedule_preview)
        form.addRow(self.smooth_feature)

        self.smooth_feature_angle = QDoubleSpinBox()
        self.smooth_feature_angle.setRange(1.0, 180.0)
        self.smooth_feature_angle.setValue(45.0)
        self.smooth_feature_angle.setSuffix(" deg")
        self.smooth_feature_angle.valueChanged.connect(self._schedule_preview)
        form.addRow("Feature angle:", self.smooth_feature_angle)

        return group

    def _build_convex_group(self) -> QGroupBox:
        group = QGroupBox("5. Remove concave features (convex blend)")
        form = QFormLayout(group)

        self.convex_blend_spin = QDoubleSpinBox()
        self.convex_blend_spin.setDecimals(3)
        self.convex_blend_spin.setRange(0.0, 1.0)
        self.convex_blend_spin.setSingleStep(0.05)
        self.convex_blend_spin.setValue(0.0)
        self.convex_blend_spin.setToolTip(
            "Blend each vertex toward its projection on the surface's\n"
            "convex hull. 0 = keep original concavities.\n"
            "1 = fully convexify (every vertex lies on the hull).\n"
            "Useful to remove dimples and self-folding features that\n"
            "break down-stream intersection and tetrahedralization."
        )
        self.convex_blend_spin.valueChanged.connect(self._schedule_preview)
        form.addRow("Convex blend:", self.convex_blend_spin)

        return group

    def _build_planar_group(self) -> QGroupBox:
        group = QGroupBox("6. Flatten toward best-fit plane")
        form = QFormLayout(group)

        self.planarity_spin = QDoubleSpinBox()
        self.planarity_spin.setDecimals(3)
        self.planarity_spin.setRange(0.0, 1.0)
        self.planarity_spin.setSingleStep(0.05)
        self.planarity_spin.setValue(0.0)
        self.planarity_spin.setToolTip(
            "0 = keep original curvature.\n"
            "1 = project every vertex onto the best-fit plane.\n"
            "Intermediate values blend between the two."
        )
        self.planarity_spin.valueChanged.connect(self._schedule_preview)
        form.addRow("Planarity blend:", self.planarity_spin)

        return group

    def _build_clip_group(self) -> QGroupBox:
        group = QGroupBox("7. Side clip trim")
        form = QFormLayout(group)

        self.clip_enable = QCheckBox("Enable side clipping")
        self.clip_enable.setChecked(False)
        self.clip_enable.setToolTip(
            "Trim the selected TriSurf with a planar clip aligned to the\n"
            "surface local frame. The new border is cleaned and retriangulated."
        )
        self.clip_enable.toggled.connect(self._schedule_preview)
        form.addRow(self.clip_enable)

        self.clip_side_combo = QComboBox()
        self.clip_side_combo.addItems(["left", "right", "down", "up"])
        self.clip_side_combo.setToolTip(
            "Choose which local side of the TriSurf is trimmed.\n"
            "The local frame is inferred from the surface geometry."
        )
        self.clip_side_combo.currentIndexChanged.connect(self._schedule_preview)
        form.addRow("Side:", self.clip_side_combo)

        self.clip_mode_combo = QComboBox()
        self.clip_mode_combo.addItems(["length", "extent"])
        self.clip_mode_combo.setToolTip(
            "length: clip inward by an absolute distance.\n"
            "extent: clip inward by a fraction of the side span."
        )
        self.clip_mode_combo.currentIndexChanged.connect(self._schedule_preview)
        form.addRow("Measure:", self.clip_mode_combo)

        self.clip_length_spin = QDoubleSpinBox()
        self.clip_length_spin.setDecimals(4)
        self.clip_length_spin.setRange(0.0, 1.0e9)
        self.clip_length_spin.setSingleStep(1.0)
        self.clip_length_spin.setValue(0.0)
        self.clip_length_spin.setToolTip(
            "Absolute inward trim distance in project units.\n"
            "Used when Measure = length."
        )
        self.clip_length_spin.valueChanged.connect(self._schedule_preview)
        form.addRow("Length:", self.clip_length_spin)

        self.clip_extent_spin = QDoubleSpinBox()
        self.clip_extent_spin.setDecimals(3)
        self.clip_extent_spin.setRange(0.0, 1.0)
        self.clip_extent_spin.setSingleStep(0.05)
        self.clip_extent_spin.setValue(0.0)
        self.clip_extent_spin.setToolTip(
            "Relative inward trim amount in [0, 1].\n"
            "Used when Measure = extent."
        )
        self.clip_extent_spin.valueChanged.connect(self._schedule_preview)
        form.addRow("Extent (rel):", self.clip_extent_spin)

        return group

    # ------------------------------------------------------------ data model ---

    def _populate_candidates(self) -> None:
        """Scan project collections for TriSurf entities."""
        self._candidates.clear()
        self.entity_combo.blockSignals(True)
        self.entity_combo.clear()
        for coll_name in TRISURF_COLLECTIONS:
            collection = getattr(self.project, coll_name, None)
            if collection is None or not hasattr(collection, "df"):
                continue
            try:
                uids = collection.get_topology_uids("TriSurf")
            except Exception:
                uids = []
            for uid in uids:
                try:
                    name = collection.get_uid_name(uid)
                except Exception:
                    name = uid
                label = f"{coll_name}: {name}"
                self._candidates.append((uid, coll_name, name))
                self.entity_combo.addItem(label, userData=uid)
        self.entity_combo.blockSignals(False)

        # Prefer the currently selected uid if it is a TriSurf.
        selected = getattr(self.view, "selected_uids", None) or []
        for uid in selected:
            idx = self._candidate_index(uid)
            if idx is not None:
                self.entity_combo.setCurrentIndex(idx)
                break

        if not self._candidates:
            self.stats_label.setText(
                "No TriSurf entities found in the project. "
                "Create or import a triangulated surface first."
            )

    def _candidate_index(self, uid: str) -> Optional[int]:
        for i, (cand_uid, _, _) in enumerate(self._candidates):
            if cand_uid == uid:
                return i
        return None

    def _current_collection(self):
        if self._current_coll is None:
            return None
        return getattr(self.project, self._current_coll, None)

    def _current_original(self) -> Optional[TriSurf]:
        collection = self._current_collection()
        if collection is None or self._current_uid is None:
            return None
        try:
            return collection.get_uid_vtk_obj(self._current_uid)
        except Exception:
            return None

    # ---------------------------------------------------------- parameters ---

    def _collect_params(self) -> Dict[str, object]:
        """Gather widget values into the dict consumed by `_apply_fix_pipeline`."""
        return {
            "clean_tol_rel": self.clean_tol_spin.value(),
            "fill_holes_rel": self.fill_holes_spin.value(),
            "decimate_target": self.decimate_spin.value(),
            "decimate_algorithm": self.decimate_algo.currentText(),
            "decimate_feature_angle": self.decimate_feature_angle.value(),
            "decimate_preserve_topology": self.decimate_preserve.isChecked(),
            "decimate_boundary_deletion": self.decimate_boundary_deletion.isChecked(),
            "subdivide_levels": self.subdivide_levels.value(),
            "subdivide_type": self.subdivide_type.currentText(),
            "smooth_method": self.smooth_method.currentText(),
            "smooth_iterations": self.smooth_iterations.value(),
            "smooth_relaxation": self.smooth_relaxation.value(),
            "smooth_pass_band": self.smooth_pass_band.value(),
            "smooth_boundary": self.smooth_boundary.isChecked(),
            "smooth_feature": self.smooth_feature.isChecked(),
            "smooth_feature_angle": self.smooth_feature_angle.value(),
            "smooth_edge_angle": 15.0,
            "convex_blend": self.convex_blend_spin.value(),
            "planarity_blend": self.planarity_spin.value(),
            "clip_enabled": self.clip_enable.isChecked(),
            "clip_side": self.clip_side_combo.currentText(),
            "clip_mode": self.clip_mode_combo.currentText(),
            "clip_length": self.clip_length_spin.value(),
            "clip_extent": self.clip_extent_spin.value(),
        }

    def _reset_parameters(self) -> None:
        self.clean_tol_spin.setValue(0.0)
        self.fill_holes_spin.setValue(0.0)
        self.decimate_spin.setValue(0.0)
        self.decimate_algo.setCurrentIndex(0)
        self.decimate_feature_angle.setValue(45.0)
        self.decimate_preserve.setChecked(True)
        self.decimate_boundary_deletion.setChecked(False)
        self.subdivide_levels.setValue(0)
        self.subdivide_type.setCurrentText("linear")
        self.smooth_method.setCurrentText("none")
        self.smooth_iterations.setValue(20)
        self.smooth_relaxation.setValue(0.10)
        self.smooth_pass_band.setValue(0.10)
        self.smooth_boundary.setChecked(False)
        self.smooth_feature.setChecked(False)
        self.smooth_feature_angle.setValue(45.0)
        self.convex_blend_spin.setValue(0.0)
        self.planarity_spin.setValue(0.0)
        self.clip_enable.setChecked(False)
        self.clip_side_combo.setCurrentText("left")
        self.clip_mode_combo.setCurrentText("length")
        self.clip_length_spin.setValue(0.0)
        self.clip_extent_spin.setValue(0.0)
        self._schedule_preview()

    # ------------------------------------------------------------- preview ---

    def _on_entity_changed(self, index: int) -> None:
        """Target entity changed: restore the previous one and hook the new one."""
        self._restore_original_actor()
        self._remove_preview_actor()

        if index < 0 or index >= len(self._candidates):
            self._current_uid = None
            self._current_coll = None
            return

        uid, coll, _ = self._candidates[index]
        self._current_uid = uid
        self._current_coll = coll
        self._ghost_original_actor()
        self._schedule_preview()

    def _on_preview_toggled(self, checked: bool) -> None:
        if checked:
            self._ghost_original_actor()
            self._schedule_preview()
        else:
            self._remove_preview_actor()
            self._restore_original_actor()

    def _schedule_preview(self) -> None:
        if not self.preview_check.isChecked():
            return
        self._debounce.start()

    def _rebuild_preview(self) -> None:
        """Actually run the pipeline and update the preview actor."""
        original = self._current_original()
        if original is None:
            return
        try:
            source = _to_pyvista_triangles(original)
            result = _apply_fix_pipeline(source, self._collect_params())
        except Exception as exc:  # keep the dialog responsive on filter failure
            self.stats_label.setText(f"Preview error: {exc}")
            return

        self._last_result = result
        self._update_preview_actor(result)
        self._update_stats(source, result)

    def _update_preview_actor(self, mesh: pv.PolyData) -> None:
        if mesh is None or mesh.n_points == 0:
            self._remove_preview_actor()
            return
        plotter = getattr(self.view, "plotter", None)
        if plotter is None:
            return

        # Save the camera so that adding / replacing the preview actor
        # does not reset the user's viewpoint (PyVista can change it
        # implicitly on the very first `add_mesh`, which is what caused
        # the "flip to opposite direction" flash on dialog open).
        saved_camera = None
        try:
            saved_camera = list(plotter.camera_position)
        except Exception:
            saved_camera = None

        try:
            plotter.remove_actor(PREVIEW_ACTOR_NAME)
        except Exception:
            pass
        try:
            plotter.add_mesh(
                mesh,
                name=PREVIEW_ACTOR_NAME,
                color=PREVIEW_COLOR,
                edge_color=PREVIEW_EDGE_COLOR,
                show_edges=True,
                opacity=1.0,
                lighting=True,
                smooth_shading=False,
                pickable=False,
                reset_camera=False,
                render=False,
            )
        except Exception:
            pass
        if saved_camera is not None:
            try:
                plotter.camera_position = saved_camera
            except Exception:
                pass
        try:
            plotter.render()
        except Exception:
            pass

    def _remove_preview_actor(self) -> None:
        plotter = getattr(self.view, "plotter", None)
        if plotter is None:
            return
        saved_camera = None
        try:
            saved_camera = list(plotter.camera_position)
        except Exception:
            saved_camera = None
        try:
            plotter.remove_actor(PREVIEW_ACTOR_NAME)
        except Exception:
            pass
        if saved_camera is not None:
            try:
                plotter.camera_position = saved_camera
            except Exception:
                pass
        try:
            plotter.render()
        except Exception:
            pass

    def _clear_preview(self) -> None:
        """Remove the preview actor and restore the original surface.

        The user can still tweak parameters after this: changing any
        value will rebuild the preview on the next debounce tick (as
        long as `Live preview` is enabled).
        """
        self._remove_preview_actor()
        self._restore_original_actor()
        self._last_result = None
        if self.preview_check.isChecked():
            self._ghost_original_actor()

    def _ghost_original_actor(self) -> None:
        """Make the original actor translucent so the preview is visible."""
        actor = self._original_actor()
        if actor is None:
            return
        try:
            prop = actor.GetProperty()
            if self._original_opacity is None:
                self._original_opacity = prop.GetOpacity()
            if self._original_visibility is None:
                self._original_visibility = bool(actor.GetVisibility())
            actor.SetVisibility(True)
            prop.SetOpacity(ORIGINAL_GHOST_OPACITY)
        except Exception:
            pass

    def _restore_original_actor(self) -> None:
        actor = self._original_actor()
        if actor is None:
            return
        try:
            if self._original_opacity is not None:
                actor.GetProperty().SetOpacity(self._original_opacity)
            if self._original_visibility is not None:
                actor.SetVisibility(self._original_visibility)
        except Exception:
            pass
        finally:
            self._original_opacity = None
            self._original_visibility = None

    def _original_actor(self):
        if self._current_uid is None:
            return None
        getter = getattr(self.view, "get_actor_by_uid", None)
        if not callable(getter):
            return None
        try:
            return getter(self._current_uid)
        except Exception:
            return None

    def _update_stats(
        self, source: pv.PolyData, result: pv.PolyData
    ) -> None:
        src = _mesh_quality_stats(source)
        dst = _mesh_quality_stats(result)
        txt = (
            f"Points  : {int(src['n_points']):>7} -> {int(dst['n_points']):>7}\n"
            f"Cells   : {int(src['n_cells']):>7} -> {int(dst['n_cells']):>7}\n"
            f"Edge min: {src['edge_min']:>10.4g} -> {dst['edge_min']:>10.4g}\n"
            f"Edge avg: {src['edge_mean']:>10.4g} -> {dst['edge_mean']:>10.4g}\n"
            f"Edge max: {src['edge_max']:>10.4g} -> {dst['edge_max']:>10.4g}\n"
            f"Area min: {src['area_min']:>10.4g} -> {dst['area_min']:>10.4g}"
        )
        self.stats_label.setText(txt)

    # --------------------------------------------------------- apply / close ---

    def _on_apply(self) -> None:
        """Commit the current preview as the new vtk object of the entity."""
        if self._current_uid is None or self._current_coll is None:
            return
        if self._last_result is None:
            self._rebuild_preview()
            if self._last_result is None:
                return
        if self._last_result.n_points == 0 or self._last_result.n_cells == 0:
            QMessageBox.warning(
                self,
                "Fix Geometry",
                "The resulting surface is empty. Adjust the parameters first.",
            )
            return

        collection = self._current_collection()
        if collection is None:
            return

        new_trisurf = _pyvista_to_trisurf(self._last_result)
        try:
            collection.replace_vtk(uid=self._current_uid, vtk_object=new_trisurf)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Fix Geometry",
                f"Could not replace the vtk object:\n{exc}",
            )
            return

        # After apply, the original actor is rebuilt by the project signal;
        # reset our cached state so that closing does not override the new one.
        self._original_opacity = None
        self._original_visibility = None
        self._remove_preview_actor()
        # Re-ghost with the freshly rebuilt actor for continued tweaking.
        self._ghost_original_actor()
        self._schedule_preview()

    def _on_accept(self) -> None:
        self._on_apply()
        self.accept()

    def _on_cancel(self) -> None:
        self.reject()

    # ------------------------------------------------------------ closing ---

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt signature
        self._remove_preview_actor()
        self._restore_original_actor()
        super().closeEvent(event)

    def reject(self) -> None:  # noqa: D401 - Qt slot
        self._remove_preview_actor()
        self._restore_original_actor()
        super().reject()


# -----------------------------------------------------------------------------
# Entry point
# -----------------------------------------------------------------------------


def open_fix_geometry_dialog(view) -> None:
    """Open the Fix Geometry dialog attached to `view`.

    Shows a warning message box instead of opening the dialog when the
    project does not contain any TriSurf entity.
    """
    dialog = FixGeometryDialog(view)
    if not dialog._candidates:
        QMessageBox.information(
            view,
            "Fix Geometry",
            "No TriSurf entity is available in the project.",
        )
        dialog.deleteLater()
        return
    dialog.show()
