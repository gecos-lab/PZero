"""Utilities that expose PZero collections to the embedded PyMeshIt GUI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

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
    face_id: Optional[int] = None  # For boundary faces: 0=bottom, 1=top, 2=front, 3=back, 4=left, 5=right


class PZeroPymeshitBridge:
    """Expose PZero collections to the PyMeshIt workflow GUI."""

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
                        point_count=point_count,
                    )
                    records.append(record)

        records.sort(key=lambda rec: (rec.collection_label, rec.name.lower()))
        return records

    def load_points(
        self, collection_key: str, uid: str, face_id: Optional[int] = None
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
            return _extract_boundary_face(vtk_obj, face_id)
        
        return _vtk_dataset_to_points(vtk_obj)


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


def _is_boundary_cube(vtk_obj) -> bool:
    """
    Check if a VTK object is a boundary cube (has exactly 8 points).
    
    A PZero boundary cube is defined by 8 corner vertices forming a box.
    """
    return _count_points(vtk_obj) == 8


def _extract_boundary_face(vtk_obj, face_id: int) -> Optional[np.ndarray]:
    """
    Extract one face from a PZero boundary cube.
    
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
    
    Returns
    -------
    Optional[np.ndarray]
        Array of shape (4, 3) containing the 4 corner points of the face,
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
    face_points = all_points[indices]
    
    return face_points.copy()

