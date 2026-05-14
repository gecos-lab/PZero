"""Utilities that expose PZero collections to the embedded PyMeshIt GUI."""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
from vtkmodules.util.numpy_support import vtk_to_numpy


@dataclass(frozen=True)
class PZeroEntityRecord:
    """Descriptor for a single entity that can be sent from PZero to PyMeshIt."""

    collection_key: str
    collection_label: str
    uid: str
    name: str
    topology: str
    point_count: int
    role: str = ""
    feature: str = ""
    scenario: str = ""
    face_id: Optional[int] = None  # For boundary faces: 0=bottom, 1=top, 2=front, 3=back, 4=left, 5=right


class PZeroPymeshitBridge:
    """Expose PZero collections to the PyMeshIt workflow GUI."""

    _POINT_IMPORT_TOPOLOGIES = frozenset({"TriSurf", "PolyLine", "XsPolyLine"})
    _POLYLINE_TOPOLOGIES = frozenset({"PolyLine", "XsPolyLine"})
    SORT_OPTIONS: Dict[str, str] = {
        "collection_name": "Collection, Name",
        "role": "Role",
        "topology": "Type",
        "name": "Name",
        "feature": "Feature",
        "scenario": "Scenario",
        "points": "Point Count",
    }

    _COLLECTION_LABELS: Dict[str, str] = {
        "geol_coll": "Geology",
        "mesh3d_coll": "3D Meshes",
        "dom_coll": "DOM / Point Clouds",
        "image_coll": "Images",
        "boundary_coll": "Boundaries",
        "well_coll": "Wells",
        "fluid_coll": "Fluids",
        "backgrnd_coll": "Backgrounds",
    }

    def __init__(self, project_window) -> None:
        self._project = project_window

    @classmethod
    def supports_point_import_option(cls, topology: str) -> bool:
        """Return True when PyMeshIt can import this topology as XYZ points."""
        return str(topology or "") in cls._POINT_IMPORT_TOPOLOGIES

    @classmethod
    def is_polyline_topology(cls, topology: str) -> bool:
        """Return True when the topology should behave as a 1D polyline in PyMeshIt."""
        return str(topology or "") in cls._POLYLINE_TOPOLOGIES

    @classmethod
    def default_dataset_type(cls, topology: str, load_as_points: bool = False) -> str:
        """Map a PZero topology to the internal PyMeshIt dataset type."""
        topology = str(topology or "")
        if topology == "TriSurf" and load_as_points:
            return "SURFACE"
        if cls.is_polyline_topology(topology):
            return "SURFACE" if load_as_points else "WELL"
        return topology or "PZERO"

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #
    def list_entities(
        self,
        sort_by: str = "collection_name",
        reverse: bool = False,
    ) -> List[PZeroEntityRecord]:
        """Return a flat catalog of entities that own VTK geometries."""
        records: List[PZeroEntityRecord] = []

        for attr_name, label in self._COLLECTION_LABELS.items():
            collection = getattr(self._project, attr_name, None)
            if collection is None or not hasattr(collection, "df"):
                continue
            if collection.df.empty:
                continue
            if "uid" not in collection.df.columns:
                continue

            topology_column = "topology" if "topology" in collection.df.columns else None
            role_column = "role" if "role" in collection.df.columns else None
            feature_column = "feature" if "feature" in collection.df.columns else None
            scenario_column = "scenario" if "scenario" in collection.df.columns else None
            name_column = "name" if "name" in collection.df.columns else None

            for _, row in collection.df.iterrows():
                uid = row.get("uid")
                if not uid:
                    continue
                vtk_obj = collection.get_uid_vtk_obj(uid)
                point_count = _count_points(vtk_obj)
                if point_count == 0:
                    continue
                
                # Special handling for boundary collection: export 6 faces separately
                if attr_name == "boundary_coll" and _is_boundary_cube(vtk_obj):
                    face_names = ["Bottom", "Top", "Front", "Back", "Left", "Right"]
                    base_name = str(row.get(name_column, uid)) if name_column else str(uid)
                    for face_id, face_name in enumerate(face_names):
                        record = PZeroEntityRecord(
                            collection_key=attr_name,
                            collection_label=label,
                            uid=uid,
                            name=f"{base_name} - {face_name}",
                            topology="BORDER",  # Mark as BORDER for PyMeshIt
                            role=_collection_value_as_text(row.get(role_column, "")) if role_column else "",
                            feature=_collection_value_as_text(row.get(feature_column, "")) if feature_column else "",
                            scenario=_collection_value_as_text(row.get(scenario_column, "")) if scenario_column else "",
                            point_count=4,  # Each face has 4 points
                            face_id=face_id,
                        )
                        records.append(record)
                else:
                    record = PZeroEntityRecord(
                        collection_key=attr_name,
                        collection_label=label,
                        uid=uid,
                        name=str(row.get(name_column, uid)) if name_column else str(uid),
                        topology=str(row.get(topology_column, "")) if topology_column else "",
                        role=_collection_value_as_text(row.get(role_column, "")) if role_column else "",
                        feature=_collection_value_as_text(row.get(feature_column, "")) if feature_column else "",
                        scenario=_collection_value_as_text(row.get(scenario_column, "")) if scenario_column else "",
                        point_count=point_count,
                    )
                    records.append(record)

        return self.sort_entity_records(records, sort_by=sort_by, reverse=reverse)

    @classmethod
    def sort_entity_records(
        cls,
        records: List[PZeroEntityRecord],
        sort_by: str = "collection_name",
        reverse: bool = False,
    ) -> List[PZeroEntityRecord]:
        """Return records sorted by one of the import-table sort keys."""
        sort_by = str(sort_by or "collection_name")

        def text(value) -> str:
            return str(value or "").casefold()

        key_builders = {
            "collection_name": lambda rec: (
                text(rec.collection_label),
                text(rec.name),
                text(rec.topology),
                text(rec.role),
            ),
            "role": lambda rec: (
                text(rec.role),
                text(rec.topology),
                text(rec.collection_label),
                text(rec.name),
            ),
            "topology": lambda rec: (
                text(rec.topology),
                text(rec.role),
                text(rec.collection_label),
                text(rec.name),
            ),
            "type": lambda rec: (
                text(rec.topology),
                text(rec.role),
                text(rec.collection_label),
                text(rec.name),
            ),
            "name": lambda rec: (
                text(rec.name),
                text(rec.collection_label),
                text(rec.topology),
            ),
            "feature": lambda rec: (
                text(rec.feature),
                text(rec.role),
                text(rec.collection_label),
                text(rec.name),
            ),
            "scenario": lambda rec: (
                text(rec.scenario),
                text(rec.role),
                text(rec.collection_label),
                text(rec.name),
            ),
            "points": lambda rec: (
                int(rec.point_count or 0),
                text(rec.collection_label),
                text(rec.name),
            ),
        }
        key_func = key_builders.get(sort_by, key_builders["collection_name"])
        return sorted(records, key=key_func, reverse=reverse)

    def load_points(
        self, collection_key: str, uid: str, face_id: Optional[int] = None,
        extension_factor: float = 0.2
    ) -> Optional[np.ndarray]:
        """
        Return the XYZ coordinates for the requested entity, or None.
        
        Parameters
        ----------
        collection_key : str
            Key identifying the collection (e.g., 'boundary_coll')
        uid : str
            Unique identifier of the entity
        face_id : Optional[int]
            For boundary cubes: 0=bottom, 1=top, 2=front, 3=back, 4=left, 5=right
        extension_factor : float
            Factor by which to extend boundary faces (default 0.2 = 20% extension)
            Only applies to boundary faces. Increase this if intersections are incomplete.
        
        Returns
        -------
        Optional[np.ndarray]
            Array of shape (N, 3) containing point coordinates, or None if not found
        """
        collection = getattr(self._project, collection_key, None)
        if collection is None:
            return None
        if not hasattr(collection, "get_uid_vtk_obj"):
            return None
        vtk_obj = collection.get_uid_vtk_obj(uid)
        
        # Extract specific face for boundary cubes
        if face_id is not None and collection_key == "boundary_coll":
            return _extract_boundary_face(vtk_obj, face_id, extension_factor)
        
        return _vtk_dataset_to_points(vtk_obj)

    def load_triangles(
        self, collection_key: str, uid: str
    ) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        """
        Extract triangles and vertices from a TriSurf entity.
        
        Parameters
        ----------
        collection_key : str
            Key identifying the collection (e.g., 'geol_coll')
        uid : str
            Unique identifier of the TriSurf entity
        
        Returns
        -------
        Optional[Tuple[np.ndarray, np.ndarray]]
            Tuple of (vertices, triangles) arrays, or None if not a TriSurf or extraction fails.
            vertices: (N, 3) array of point coordinates
            triangles: (M, 3) array of triangle indices into vertices
        """
        collection = getattr(self._project, collection_key, None)
        if collection is None:
            return None
        if not hasattr(collection, "get_uid_vtk_obj"):
            return None
        
        vtk_obj = collection.get_uid_vtk_obj(uid)
        if vtk_obj is None:
            return None
        
        # Check if it's a TriSurf
        from pzero.entities_factory import TriSurf
        if not isinstance(vtk_obj, TriSurf):
            return None
        
        # Extract vertices
        vertices = _vtk_dataset_to_points(vtk_obj)
        if vertices is None or len(vertices) == 0:
            return None
        
        # Extract triangles using TriSurf's cells property
        try:
            cells = vtk_obj.cells  # Returns (N, 3) array of triangle indices
            if cells is None or len(cells) == 0:
                return None
            triangles = np.asarray(cells, dtype=np.int32)
        except Exception:
            return None
        
        return vertices, triangles

    def load_trisurf_components(
        self, collection_key: str, uid: str
    ) -> List[Tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]]:
        """
        Extract disconnected triangle components from a TriSurf entity.

        GOCAD border files can contain several TFACE parts that PZero stores as
        one geology TriSurf. PyMeshIt needs those independent border faces as
        separate surfaces, so split by triangle connectivity and provide each
        component's vertices, triangles, and ordered boundary loop.
        """
        collection = getattr(self._project, collection_key, None)
        vtk_obj = None
        if collection is not None and hasattr(collection, "get_uid_vtk_obj"):
            vtk_obj = collection.get_uid_vtk_obj(uid)

        tri_data = self.load_triangles(collection_key, uid)
        if tri_data is None:
            return []

        vertices, triangles = tri_data
        tface_ids = _get_cell_data_array(vtk_obj, "GOCAD_TFACE")
        if tface_ids is not None and len(tface_ids) == len(triangles):
            components = _split_triangles_by_cell_labels(vertices, triangles, tface_ids)
            if len(components) > 1:
                return components

        tube_side_components = _split_tube_surface_by_direction_changes(vertices, triangles)
        if len(tube_side_components) > 1:
            return tube_side_components

        return _split_triangles_by_connected_components(vertices, triangles)

    def load_boundary_edges(
        self, collection_key: str, uid: str
    ) -> Optional[np.ndarray]:
        """
        Extract the actual boundary edges from a TriSurf entity.
        
        This extracts the true boundary polylines preserving their exact shape,
        including concave features. Unlike a convex hull, this captures the
        actual outline of the surface.
        
        Parameters
        ----------
        collection_key : str
            Key identifying the collection (e.g., 'geol_coll')
        uid : str
            Unique identifier of the TriSurf entity
        
        Returns
        -------
        Optional[np.ndarray]
            Array of shape (N, 3) containing ordered boundary edge points,
            or None if extraction fails
        """
        collection = getattr(self._project, collection_key, None)
        if collection is None:
            return None
        if not hasattr(collection, "get_uid_vtk_obj"):
            return None
        
        vtk_obj = collection.get_uid_vtk_obj(uid)
        if vtk_obj is None:
            return None
        
        # Check if it's a TriSurf
        from pzero.entities_factory import TriSurf
        if not isinstance(vtk_obj, TriSurf):
            return None
        
        # Extract boundary using TriSurf's get_clean_boundary method
        try:
            boundary_polydata = vtk_obj.get_clean_boundary()
            if boundary_polydata is None:
                return None
            
            # Extract ordered boundary points from the VTK polylines
            boundary_points = _extract_ordered_boundary_points(boundary_polydata)
            if boundary_points is None or len(boundary_points) == 0:
                return None
            
            return boundary_points
        except Exception:
            return None


# ------------------------------------------------------------------------- #
# Helpers
# ------------------------------------------------------------------------- #
def _count_points(vtk_obj) -> int:
    """Count the number of points in a VTK object."""
    if vtk_obj is None or not hasattr(vtk_obj, "GetNumberOfPoints"):
        return 0
    try:
        return int(vtk_obj.GetNumberOfPoints())
    except Exception:
        return 0


def _collection_value_as_text(value) -> str:
    """Normalize optional collection metadata values to clean strings."""
    if value is None:
        return ""
    try:
        if isinstance(value, (float, np.floating)) and np.isnan(value):
            return ""
    except Exception:
        pass
    return str(value)


def _vtk_dataset_to_points(vtk_obj) -> Optional[np.ndarray]:
    """Convert any VTK dataset with points to a (N, 3) numpy array."""
    if vtk_obj is None or not hasattr(vtk_obj, "GetPoints"):
        return None
    vtk_points = vtk_obj.GetPoints()
    if vtk_points is None:
        return None
    vtk_array = vtk_points.GetData()
    if vtk_array is None:
        return None
    try:
        np_points = vtk_to_numpy(vtk_array)
    except Exception:
        return None
    if np_points is None or np_points.size == 0:
        return None
    # Always return a float64 copy to avoid dangling references.
    return np.asarray(np_points, dtype=float).copy()


def _get_cell_data_array(vtk_obj, array_name: str) -> Optional[np.ndarray]:
    """Return a named VTK cell-data array as numpy, when available."""
    if vtk_obj is None or not hasattr(vtk_obj, "GetCellData"):
        return None
    try:
        vtk_array = vtk_obj.GetCellData().GetArray(array_name)
    except Exception:
        return None
    if vtk_array is None:
        return None
    try:
        return np.asarray(vtk_to_numpy(vtk_array)).copy()
    except Exception:
        return None


def _split_triangles_by_cell_labels(
    vertices: np.ndarray,
    triangles: np.ndarray,
    labels: np.ndarray,
) -> List[Tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]]:
    """Split triangles into components using a per-cell label such as GOCAD_TFACE."""
    vertices = np.asarray(vertices, dtype=float)
    triangles = np.asarray(triangles, dtype=np.int32)
    labels = np.asarray(labels)
    components: List[Tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]] = []

    for label in sorted(np.unique(labels)):
        tri_indices = np.where(labels == label)[0]
        if len(tri_indices) == 0:
            continue
        component_global_triangles = triangles[tri_indices]
        used_point_ids = np.unique(component_global_triangles.ravel())
        point_id_map = {int(old_id): new_id for new_id, old_id in enumerate(used_point_ids)}
        local_triangles = np.array(
            [[point_id_map[int(point_id)] for point_id in tri] for tri in component_global_triangles],
            dtype=np.int32,
        )
        local_vertices = vertices[used_point_ids].copy()
        boundary_points = _component_boundary_loop(local_vertices, local_triangles)
        components.append((local_vertices, local_triangles, boundary_points))

    components.sort(key=lambda item: len(item[1]), reverse=True)
    return components


def _split_triangles_by_connected_components(
    vertices: np.ndarray,
    triangles: np.ndarray,
) -> List[Tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]]:
    """Split triangles into connected components using shared triangle vertices."""
    vertices = np.asarray(vertices, dtype=float)
    triangles = np.asarray(triangles, dtype=np.int32)
    if vertices.ndim != 2 or vertices.shape[0] == 0:
        return []
    if triangles.ndim != 2 or triangles.shape[0] == 0 or triangles.shape[1] < 3:
        return []

    triangles = triangles[:, :3]
    point_to_triangles: Dict[int, List[int]] = {}
    for tri_idx, tri in enumerate(triangles):
        for point_id in tri:
            point_to_triangles.setdefault(int(point_id), []).append(tri_idx)

    visited = np.zeros(len(triangles), dtype=bool)
    components: List[Tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]] = []

    for seed_idx in range(len(triangles)):
        if visited[seed_idx]:
            continue

        stack = [seed_idx]
        visited[seed_idx] = True
        component_tri_indices = []

        while stack:
            tri_idx = stack.pop()
            component_tri_indices.append(tri_idx)
            for point_id in triangles[tri_idx]:
                for neighbour_idx in point_to_triangles.get(int(point_id), []):
                    if not visited[neighbour_idx]:
                        visited[neighbour_idx] = True
                        stack.append(neighbour_idx)

        component_global_triangles = triangles[component_tri_indices]
        used_point_ids = np.unique(component_global_triangles.ravel())
        point_id_map = {int(old_id): new_id for new_id, old_id in enumerate(used_point_ids)}
        local_triangles = np.array(
            [[point_id_map[int(point_id)] for point_id in tri] for tri in component_global_triangles],
            dtype=np.int32,
        )
        local_vertices = vertices[used_point_ids].copy()
        boundary_points = _component_boundary_loop(local_vertices, local_triangles)
        components.append((local_vertices, local_triangles, boundary_points))

    components.sort(key=lambda item: len(item[1]), reverse=True)
    return components


def _split_tube_surface_by_direction_changes(
    vertices: np.ndarray,
    triangles: np.ndarray,
) -> List[Tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]]:
    """
    Split a closed lateral border tube into direction-aware side faces.

    SKUA/GOCAD borders often store top and bottom as separate TriSurfs and the
    lateral border as one connected TUBE surface. That tube has repeated XY
    columns through Z, so connected-component splitting cannot separate it. We
    trace the XY column loop and split at the major footprint direction changes.
    """
    vertices = np.asarray(vertices, dtype=float)
    triangles = np.asarray(triangles, dtype=np.int32)
    if vertices.ndim != 2 or vertices.shape[0] < 8:
        return []
    if triangles.ndim != 2 or triangles.shape[0] < 4 or triangles.shape[1] < 3:
        return []

    unique_xy, vertex_column_ids, xy_counts = _tube_unique_xy_columns(vertices)
    if len(unique_xy) < 4:
        return []

    # Tube side surfaces have vertical columns: many Z values for every XY.
    # Regular geological surfaces normally have each XY only once.
    repeated_column_ratio = float(len(vertices)) / float(len(unique_xy))
    if repeated_column_ratio < 3.0 or int(np.median(xy_counts)) < 3:
        return []

    ring = _trace_xy_column_ring(vertex_column_ids, unique_xy, triangles)
    if len(ring) < 4:
        return []

    corner_positions = _major_direction_break_positions(unique_xy[ring], target_count=4)
    if len(corner_positions) < 3:
        return []

    components: List[Tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]] = []
    min_triangles = max(4, int(0.005 * len(triangles)))
    for segment_columns in _ring_segments_from_break_positions(ring, corner_positions):
        segment_column_set = set(segment_columns)
        tri_indices = []
        for tri_idx, tri in enumerate(triangles[:, :3]):
            tri_columns = {int(vertex_column_ids[int(point_id)]) for point_id in tri}
            if tri_columns.issubset(segment_column_set):
                tri_indices.append(tri_idx)

        if len(tri_indices) < min_triangles:
            return []

        component_global_triangles = triangles[np.asarray(tri_indices, dtype=np.int32), :3]
        used_point_ids = np.unique(component_global_triangles.ravel())
        point_id_map = {int(old_id): new_id for new_id, old_id in enumerate(used_point_ids)}
        local_triangles = np.array(
            [[point_id_map[int(point_id)] for point_id in tri] for tri in component_global_triangles],
            dtype=np.int32,
        )
        local_vertices = vertices[used_point_ids].copy()
        boundary_points = _component_boundary_loop(local_vertices, local_triangles)
        components.append((local_vertices, local_triangles, boundary_points))

    return components


def _tube_unique_xy_columns(vertices: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return unique XY columns and the per-vertex column ids."""
    xy = np.round(np.asarray(vertices, dtype=float)[:, :2], decimals=6)
    unique_xy, vertex_column_ids, xy_counts = np.unique(
        xy,
        axis=0,
        return_inverse=True,
        return_counts=True,
    )
    return unique_xy, vertex_column_ids, xy_counts


def _trace_xy_column_ring(
    vertex_column_ids: np.ndarray,
    unique_xy: np.ndarray,
    triangles: np.ndarray,
) -> List[int]:
    """Trace the closed XY column loop of a tube side surface."""
    adjacency: Dict[int, set] = {}
    for tri in triangles[:, :3]:
        tri_columns = sorted({int(vertex_column_ids[int(point_id)]) for point_id in tri})
        if len(tri_columns) != 2:
            continue
        a, b = tri_columns
        adjacency.setdefault(a, set()).add(b)
        adjacency.setdefault(b, set()).add(a)

    if len(adjacency) < 4:
        return []
    if any(len(neighbours) != 2 for neighbours in adjacency.values()):
        return []

    start = min(adjacency, key=lambda idx: (unique_xy[idx, 0], unique_xy[idx, 1]))
    start_neighbours = sorted(
        adjacency[start],
        key=lambda idx: np.arctan2(
            unique_xy[idx, 1] - unique_xy[start, 1],
            unique_xy[idx, 0] - unique_xy[start, 0],
        ),
    )
    if not start_neighbours:
        return []

    ring = [start, start_neighbours[0]]
    previous = start
    current = start_neighbours[0]
    while True:
        next_candidates = [idx for idx in adjacency[current] if idx != previous]
        if not next_candidates:
            return []
        next_idx = next_candidates[0]
        if next_idx == start:
            break
        ring.append(next_idx)
        previous, current = current, next_idx
        if len(ring) > len(adjacency):
            return []

    return ring if len(ring) == len(adjacency) else []


def _major_direction_break_positions(
    loop_xy: np.ndarray,
    target_count: int = 4,
) -> List[int]:
    """Find major footprint direction breaks from a closed XY loop."""
    loop_xy = np.asarray(loop_xy, dtype=float)
    if loop_xy.ndim != 2 or len(loop_xy) < target_count:
        return []

    bbox_diag = float(np.linalg.norm(loop_xy.max(axis=0) - loop_xy.min(axis=0)))
    if bbox_diag <= 0.0:
        return []

    best_indices = None
    best_delta = None
    for fraction in (0.10, 0.09, 0.08, 0.07, 0.06, 0.05, 0.04, 0.03, 0.02, 0.015, 0.01, 0.005):
        indices = _rdp_closed_loop_indices(loop_xy, bbox_diag * fraction)
        if len(indices) < target_count:
            continue
        if len(indices) == target_count:
            return sorted(indices)
        delta = abs(len(indices) - target_count)
        if best_indices is None or delta < best_delta:
            best_indices = indices
            best_delta = delta

    if best_indices is None:
        return _largest_turn_positions(loop_xy, target_count)

    return sorted(_select_polygon_corners_by_area(loop_xy, best_indices, target_count))


def _rdp_closed_loop_indices(points: np.ndarray, epsilon: float) -> List[int]:
    """Simplify a closed 2D loop and return vertex positions in the original loop."""
    closed = np.vstack([points, points[0]])
    indices = _rdp_open_polyline_indices(closed, epsilon)
    last_index = len(closed) - 1
    unique_indices = []
    for idx in indices:
        idx = int(idx)
        if idx == last_index:
            idx = 0
        if idx not in unique_indices:
            unique_indices.append(idx)
    return unique_indices


def _rdp_open_polyline_indices(points: np.ndarray, epsilon: float, offset: int = 0) -> List[int]:
    """Ramer-Douglas-Peucker simplification returning source indices."""
    if len(points) <= 2:
        return [offset, offset + len(points) - 1]

    start = points[0]
    end = points[-1]
    distances = np.array(
        [_point_to_segment_distance(point, start, end) for point in points[1:-1]],
        dtype=float,
    )
    if len(distances) == 0:
        return [offset, offset + len(points) - 1]

    max_local_idx = int(np.argmax(distances)) + 1
    if distances[max_local_idx - 1] <= epsilon:
        return [offset, offset + len(points) - 1]

    left = _rdp_open_polyline_indices(points[: max_local_idx + 1], epsilon, offset)
    right = _rdp_open_polyline_indices(points[max_local_idx:], epsilon, offset + max_local_idx)
    return left[:-1] + right


def _point_to_segment_distance(point: np.ndarray, start: np.ndarray, end: np.ndarray) -> float:
    segment = end - start
    denom = float(np.dot(segment, segment))
    if denom <= 0.0:
        return float(np.linalg.norm(point - start))
    t = float(np.clip(np.dot(point - start, segment) / denom, 0.0, 1.0))
    closest = start + t * segment
    return float(np.linalg.norm(point - closest))


def _select_polygon_corners_by_area(
    loop_xy: np.ndarray,
    candidate_indices: List[int],
    target_count: int,
) -> List[int]:
    """Choose a target number of simplified-loop vertices that preserve area."""
    candidate_indices = sorted({int(idx) for idx in candidate_indices})
    if len(candidate_indices) <= target_count:
        return candidate_indices
    if len(candidate_indices) > 24:
        local_positions = _largest_turn_positions(loop_xy[candidate_indices], target_count)
        return [candidate_indices[pos] for pos in local_positions]

    best_combo = None
    best_area = -1.0
    for combo in itertools.combinations(candidate_indices, target_count):
        polygon = loop_xy[list(combo)]
        area = _polygon_area_2d(polygon)
        if area > best_area:
            best_combo = combo
            best_area = area
    return list(best_combo) if best_combo is not None else candidate_indices[:target_count]


def _polygon_area_2d(points: np.ndarray) -> float:
    if len(points) < 3:
        return 0.0
    x = points[:, 0]
    y = points[:, 1]
    return float(abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) * 0.5)


def _largest_turn_positions(loop_xy: np.ndarray, target_count: int) -> List[int]:
    """Fallback corner picker based on local turning angle."""
    turns = []
    for idx in range(len(loop_xy)):
        prev_pt = loop_xy[(idx - 1) % len(loop_xy)]
        curr_pt = loop_xy[idx]
        next_pt = loop_xy[(idx + 1) % len(loop_xy)]
        v1 = curr_pt - prev_pt
        v2 = next_pt - curr_pt
        len1 = np.linalg.norm(v1)
        len2 = np.linalg.norm(v2)
        if len1 <= 0.0 or len2 <= 0.0:
            angle = 0.0
        else:
            angle = float(np.degrees(np.arccos(np.clip(np.dot(v1 / len1, v2 / len2), -1.0, 1.0))))
        turns.append((angle, idx))

    selected = []
    min_separation = max(1, len(loop_xy) // max(1, target_count * 4))
    for _angle, idx in sorted(turns, reverse=True):
        if all(min((idx - prev) % len(loop_xy), (prev - idx) % len(loop_xy)) >= min_separation for prev in selected):
            selected.append(idx)
        if len(selected) == target_count:
            break
    return sorted(selected)


def _ring_segments_from_break_positions(
    ring: List[int],
    break_positions: List[int],
) -> List[List[int]]:
    """Return inclusive column segments between consecutive break positions."""
    n_ring = len(ring)
    breaks = sorted({int(pos) % n_ring for pos in break_positions})
    segments = []
    for idx, start_pos in enumerate(breaks):
        end_pos = breaks[(idx + 1) % len(breaks)]
        if start_pos < end_pos:
            segments.append(ring[start_pos : end_pos + 1])
        else:
            segments.append(ring[start_pos:] + ring[: end_pos + 1])
    return segments


def _component_boundary_loop(
    vertices: np.ndarray,
    triangles: np.ndarray,
) -> Optional[np.ndarray]:
    """Return the dominant ordered boundary loop for a triangle component."""
    edge_counts: Dict[Tuple[int, int], int] = {}
    for tri in triangles:
        tri_ids = [int(tri[0]), int(tri[1]), int(tri[2])]
        for a, b in ((tri_ids[0], tri_ids[1]), (tri_ids[1], tri_ids[2]), (tri_ids[2], tri_ids[0])):
            edge = (a, b) if a < b else (b, a)
            edge_counts[edge] = edge_counts.get(edge, 0) + 1

    boundary_edges = [edge for edge, count in edge_counts.items() if count == 1]
    if not boundary_edges:
        return None

    adjacency: Dict[int, List[int]] = {}
    for a, b in boundary_edges:
        adjacency.setdefault(a, []).append(b)
        adjacency.setdefault(b, []).append(a)

    chains = []
    unused_edges = {edge for edge in boundary_edges}

    def remove_edge(a: int, b: int) -> None:
        edge = (a, b) if a < b else (b, a)
        unused_edges.discard(edge)

    while unused_edges:
        start_a, start_b = next(iter(unused_edges))
        chain = [start_a, start_b]
        remove_edge(start_a, start_b)

        while True:
            current = chain[-1]
            previous = chain[-2] if len(chain) > 1 else None
            next_candidates = []
            for candidate in adjacency.get(current, []):
                edge = (current, candidate) if current < candidate else (candidate, current)
                if edge in unused_edges and candidate != previous:
                    next_candidates.append(candidate)
            if not next_candidates:
                break
            next_point = next_candidates[0]
            chain.append(next_point)
            remove_edge(current, next_point)
            if next_point == chain[0]:
                break

        chains.append(chain)

    if not chains:
        return None

    chains.sort(key=len, reverse=True)
    dominant_chain = chains[0]
    if len(dominant_chain) < 3:
        return None

    boundary = vertices[np.asarray(dominant_chain, dtype=np.int32), :3]
    if not np.allclose(boundary[0], boundary[-1], atol=1e-10):
        boundary = np.vstack([boundary, boundary[0]])
    return np.asarray(boundary, dtype=float)


def _extract_ordered_boundary_points(boundary_polydata) -> Optional[np.ndarray]:
    """
    Extract ordered boundary points from VTK polydata containing polylines.
    
    This preserves the exact boundary shape, including concave features,
    by following the connectivity of the polylines.
    
    Parameters
    ----------
    boundary_polydata : vtkPolyData
        VTK polydata containing boundary polylines (from get_clean_boundary)
    
    Returns
    -------
    Optional[np.ndarray]
        Array of shape (N, 3) containing ordered boundary points,
        or None if extraction fails
    """
    if boundary_polydata is None:
        return None
    
    # Get all points from the polydata
    all_points = _vtk_dataset_to_points(boundary_polydata)
    if all_points is None or len(all_points) == 0:
        return None
    
    # Get the number of cells (polylines)
    num_cells = boundary_polydata.GetNumberOfCells()
    if num_cells == 0:
        return all_points  # Fallback to all points if no cells
    
    # Extract ordered points from all polyline cells
    ordered_points_list = []
    
    for cell_idx in range(num_cells):
        cell = boundary_polydata.GetCell(cell_idx)
        if cell is None:
            continue
        
        num_points_in_cell = cell.GetNumberOfPoints()
        if num_points_in_cell < 2:
            continue
        
        # Get point IDs in order from this cell
        cell_points = []
        for pt_idx in range(num_points_in_cell):
            point_id = cell.GetPointId(pt_idx)
            if point_id >= 0 and point_id < len(all_points):
                cell_points.append(all_points[point_id])
        
        if len(cell_points) >= 2:
            ordered_points_list.append(np.array(cell_points))
    
    if not ordered_points_list:
        return all_points  # Fallback to all points if no valid cells

    # A workflow boundary must be a single ordered loop. If VTK exposes
    # multiple polylines, use the dominant ring instead of concatenating
    # unrelated loops into one invalid path.
    ordered_points_list.sort(key=lambda x: len(x), reverse=True)
    primary_ring = ordered_points_list[0]

    result_points = []
    for pt in primary_ring:
        if len(result_points) == 0 or not np.allclose(result_points[-1], pt, atol=1e-10):
            result_points.append(pt)

    if len(result_points) < 3:
        return all_points

    result = np.array(result_points, dtype=float)
    if not np.allclose(result[0], result[-1], atol=1e-10):
        result = np.vstack([result, result[0]])
    return result


def _is_boundary_cube(vtk_obj) -> bool:
    """
    Check if a VTK object is a boundary cube (has exactly 8 points).
    
    A PZero boundary cube is defined by 8 corner vertices forming a box.
    """
    return _count_points(vtk_obj) == 8


def _extract_boundary_face(vtk_obj, face_id: int, extension_factor: float = 0.2) -> Optional[np.ndarray]:
    """
    Extract one face from a PZero boundary cube and extend it outward.
    
    The cube has 8 vertices arranged as:
    - Bottom layer (z=bottom): points 0, 1, 2, 3
    - Top layer (z=top): points 4, 5, 6, 7
    
    Point arrangement:
      3 ---- 2      7 ---- 6
      |      |      |      |
      |      |      |      |
      0 ---- 1      4 ---- 5
      (bottom)      (top)
    
    Parameters
    ----------
    vtk_obj : VTK object
        The boundary cube VTK object
    face_id : int
        Face identifier:
        - 0: Bottom face (points 0, 1, 2, 3)
        - 1: Top face (points 4, 5, 6, 7)
        - 2: Front face, min Y (points 0, 1, 5, 4)
        - 3: Back face, max Y (points 3, 2, 6, 7)
        - 4: Left face, min X (points 0, 3, 7, 4)
        - 5: Right face, max X (points 1, 2, 6, 5)
    extension_factor : float
        Factor by which to extend the face beyond its original bounds (default 0.2 = 20%)
    
    Returns
    -------
    Optional[np.ndarray]
        Array of shape (4, 3) containing the 4 corner points of the extended face,
        or None if extraction fails
    """
    all_points = _vtk_dataset_to_points(vtk_obj)
    if all_points is None or len(all_points) != 8:
        return None
    
    # Define face vertex indices
    face_indices = {
        0: [0, 1, 2, 3],  # Bottom
        1: [4, 5, 6, 7],  # Top
        2: [0, 1, 5, 4],  # Front (min Y)
        3: [3, 2, 6, 7],  # Back (max Y)
        4: [0, 3, 7, 4],  # Left (min X)
        5: [1, 2, 6, 5],  # Right (max X)
    }
    
    if face_id not in face_indices:
        return None
    
    indices = face_indices[face_id]
    face_points = all_points[indices].copy()
    
    # Extend the face outward to ensure proper intersection with internal geometry
    extended_face = _extend_boundary_face(face_points, face_id, extension_factor)
    
    return extended_face


def _extend_boundary_face(face_points: np.ndarray, face_id: int, extension_factor: float) -> np.ndarray:
    """
    Extend a boundary face outward from its center.
    
    This ensures that border faces properly cross-cut internal geometry (like faults)
    during intersection calculations.
    
    Parameters
    ----------
    face_points : np.ndarray
        Array of shape (4, 3) containing the 4 corner points of the face
    face_id : int
        Face identifier (0-5)
    extension_factor : float
        Factor by which to extend the face (0.2 = 20% extension on each side)
    
    Returns
    -------
    np.ndarray
        Extended face points (4, 3)
    """
    # Calculate face center
    center = np.mean(face_points, axis=0)
    
    # Extend each point away from center
    extended_points = np.zeros_like(face_points)
    for i in range(4):
        direction = face_points[i] - center
        extended_points[i] = face_points[i] + direction * extension_factor
    
    return extended_points

