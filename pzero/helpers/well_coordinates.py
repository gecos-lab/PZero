"""Explicit coordinate declarations for imported well workbooks.

Converted wells may embed JSON in INFO.COORDINATE_METADATA or provide the
well-specific *_coordinate_metadata.json sidecar written by the converter.
Geometry or property names alone do not establish CRS or time datum.
"""

from copy import deepcopy
import json
from pathlib import Path

import numpy as np


def load_well_coordinate_metadata(path, well_name, embedded=None):
    """Read an explicit declaration; untagged workbooks remain untagged."""
    if isinstance(embedded, str) and embedded.strip():
        payload = json.loads(embedded)
    else:
        # Well names are data, never filesystem paths.
        name = str(well_name)
        if name in ("", ".", "..") or "/" in name or "\\" in name:
            raise ValueError("Invalid well name for a coordinate sidecar")
        sidecar = Path(path).parent / (name + "_coordinate_metadata.json")
        if not sidecar.is_file():
            return {}
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Well coordinate metadata must be a JSON object")
    if "seismic_frame" in payload:
        if str(payload.get("well", "")) != str(well_name):
            raise ValueError("Coordinate sidecar belongs to a different well")
        payload = payload["seismic_frame"]
    if not isinstance(payload, dict):
        raise ValueError("Well coordinate frame must be a JSON object")
    metadata = deepcopy(payload)
    required = (
        "vertical_domain",
        "vertical_units",
        "vertical_datum",
        "z_positive",
        "crs",
        "xy_units",
    )
    if any(key not in metadata for key in required):
        raise ValueError("Incomplete well coordinate declaration")
    conversion = metadata.get("well_conversion", {})
    if conversion and str(conversion.get("well", "")) != str(well_name):
        raise ValueError("Coordinate declaration belongs to a different well")
    return metadata


def validate_well_time_coordinates(metadata, points, time_values):
    """Confirm that declared time samples actually describe the supplied Z."""
    domain, units = metadata.get("vertical_domain"), metadata.get("vertical_units")
    if domain not in ("twt", "owt") or units not in ("ms", "s"):
        raise ValueError("Expected a well coordinate declaration in TWT/OWT and ms/s")
    if metadata.get("xy_units") != "m" or not metadata.get("crs"):
        raise ValueError(
            "Time-domain well coordinates require metres and a declared CRS"
        )
    positive = metadata.get("z_positive")
    if positive not in ("up", "down"):
        raise ValueError("Time-domain well coordinates require a declared Z sign")
    points = np.asarray(points, dtype=float)
    times = np.asarray(time_values, dtype=float).reshape(-1)
    if (
        points.ndim != 2
        or points.shape[1] != 3
        or len(times) != len(points)
        or not len(times)
    ):
        raise ValueError(
            "Well time samples must correspond to every trajectory station"
        )
    if not np.isfinite(points).all() or not np.isfinite(times).all():
        raise ValueError("Well coordinates and time samples must be finite")
    expected_z = -times if positive == "up" else times
    if not np.allclose(points[:, 2], expected_z, rtol=0, atol=1e-8):
        raise ValueError("Well Z coordinates disagree with the declared time samples")


def well_time_column(metadata):
    """Return the explicit sample column required for this declaration."""
    domain = {"twt": "TWT", "owt": "OWT"}.get(metadata.get("vertical_domain"))
    units = metadata.get("vertical_units")
    if domain is None or units not in ("ms", "s"):
        raise ValueError("Unsupported well time-coordinate declaration")
    return f"{domain}_{units}"
