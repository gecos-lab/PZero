"""Utilities that expose PZero collections to the embedded PyMeshIt GUI."""

from __future__ import annotations

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
    def list_entities(self) -> List[PZeroEntityRecord]:
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

        records.sort(key=lambda rec: (rec.collection_label, rec.name.lower()))
        return records

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

