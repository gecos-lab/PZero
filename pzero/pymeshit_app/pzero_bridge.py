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

    def load_points(self, collection_key: str, uid: str) -> Optional[np.ndarray]:
        """Return the XYZ coordinates for the requested entity, or None."""
        collection = getattr(self._project, collection_key, None)
        if collection is None:
            return None
        if not hasattr(collection, "get_uid_vtk_obj"):
            return None
        vtk_obj = collection.get_uid_vtk_obj(uid)
        return _vtk_dataset_to_points(vtk_obj)


# ------------------------------------------------------------------------- #
# Helpers
# ------------------------------------------------------------------------- #
def _count_points(vtk_obj) -> int:
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

