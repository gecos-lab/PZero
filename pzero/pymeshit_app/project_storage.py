"""Portable mesh payloads for self-contained PyMeshIt project files."""

import numpy as np
import pyvista as pv


def serialize_tetrahedral_mesh(mesh):
    """Store the generated grid, including material labels, as plain arrays."""
    if mesh is None:
        return None
    if isinstance(mesh, dict):
        mesh = mesh.get("pyvista_grid")
    if mesh is None:
        return None
    grid = pv.wrap(mesh)
    if not isinstance(grid, pv.UnstructuredGrid):
        raise ValueError("The saved tetrahedral mesh must be an unstructured grid")
    return {
        "format": "pymeshit_unstructured_grid_v1",
        "points": np.array(grid.points, copy=True),
        "cells": np.array(grid.cells, copy=True),
        "celltypes": np.array(grid.celltypes, copy=True),
        **{
            name: {
                key: np.array(value, copy=True)
                for key, value in getattr(grid, name).items()
            }
            for name in ("point_data", "cell_data", "field_data")
        },
        "active_scalars_name": grid.active_scalars_name,
        "active_scalars_association": grid.active_scalars_info.association.value,
    }


def restore_tetrahedral_mesh(payload):
    """Rebuild a grid without rerunning TetGen; old mesh-free files stay valid."""
    if payload is None:
        return None
    if isinstance(payload, pv.UnstructuredGrid):
        return payload.copy(deep=True)
    if isinstance(payload, dict) and "pyvista_grid" in payload:
        return restore_tetrahedral_mesh(payload["pyvista_grid"])
    if (
        not isinstance(payload, dict)
        or payload.get("format") != "pymeshit_unstructured_grid_v1"
    ):
        raise ValueError("Unsupported saved tetrahedral mesh format")
    grid = pv.UnstructuredGrid(
        payload["cells"], payload["celltypes"], payload["points"], deep=True
    )
    for name in ("point_data", "cell_data", "field_data"):
        for key, value in payload.get(name, {}).items():
            getattr(grid, name)[key] = np.array(value, copy=True)
    scalar = payload.get("active_scalars_name")
    if scalar:
        preference = (
            "cell" if payload.get("active_scalars_association") == 1 else "point"
        )
        grid.set_active_scalars(scalar, preference=preference)
    return grid
