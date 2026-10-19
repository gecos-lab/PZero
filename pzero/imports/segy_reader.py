"""SEG-Y storage inspection, header discovery and explicit physical coordinates.

Fixed-length 3D grids support bounded navigation repair and masked missing bins.
Unsupported layouts fail explicitly; amplitude traces are never fabricated.
"""

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import struct

import numpy as np
from .segy_headers import decode_text, detect_mapping, survey_hints


SAMPLE_FORMATS = {
    1: (4, "IBM float32"),
    2: (4, "int32"),
    3: (2, "int16"),
    5: (4, "IEEE float32"),
    6: (8, "IEEE float64"), 7: (3, "int24"), 8: (1, "int8"),
    9: (8, "int64"), 10: (4, "uint32"), 11: (2, "uint16"),
    12: (8, "uint64"), 15: (3, "uint24"), 16: (1, "uint8"),
}
DEFAULT_HEADERS = {"inline": 189, "crossline": 193, "x": 181, "y": 185}
METADATA_KEY = "pzero_seismic_metadata"


@dataclass(frozen=True)
class SegyImportOptions:
    name: str = ""
    domain: str = "twt"
    xy_units: str = "header"
    vertical_units: str = "ms"
    negate_z: bool = True
    # Time defaults to recording delay and binary sample interval. Depth must
    # have explicit sampling: SEG-Y's time fields cannot establish depth units.
    sample_origin: float | None = None
    sample_step: float | None = None
    vertical_datum: str = "Unspecified"
    file_crs: str = ""
    target_crs: str = ""
    endian: str = "auto"
    headers: dict | None = None
    header_widths: dict | None = None
    depth_model: str = "none"
    velocity_m_s: float | None = None
    time_depth_table: list = field(default_factory=list)
    depth_datum_m: float = 0.0
    model_time_datum_s: float = 0.0

    def to_dict(self):
        return asdict(self)


def file_identity(path):
    stat = Path(path).stat()
    return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def inspect_segy(path, endian="auto", headers=None, header_widths=None):
    """Inspect revision 0/1/2 fixed-length traces and discover vendor mappings."""
    path = Path(path)
    identity = file_identity(path)
    repairs = []
    with path.open("rb") as stream:
        prefix = stream.read(3728)
    if len(prefix) < 3600:
        raise ValueError("Truncated SEG-Y: text and binary headers are required.")
    tape_offset = 0
    if not any(struct.unpack(order + "H", prefix[3224:3226])[0] in SAMPLE_FORMATS for order in (">", "<")):
        if len(prefix) >= 3728 and any(struct.unpack(order + "H", prefix[3352:3354])[0] in SAMPLE_FORMATS for order in (">", "<")):
            tape_offset = 128
            repairs.append("Removed 128-byte tape label for standard output.")
    binary = prefix[tape_offset + 3200:tape_offset + 3600]
    if endian == "auto":
        candidates = [order for order, marker in (("big", ">"), ("little", "<"))
                      if struct.unpack(marker + "H", binary[24:26])[0] in SAMPLE_FORMATS]
        if len(candidates) != 1:
            code = struct.unpack(">H", binary[24:26])[0]
            raise ValueError(f"Unsupported or ambiguous SEG-Y sample format {code}. Supported codes: {sorted(SAMPLE_FORMATS)}.")
        endian = candidates[0]
    if endian not in ("big", "little"):
        raise ValueError("Byte order must be auto, big or little.")
    marker = ">" if endian == "big" else "<"
    def number(position, kind):
        return struct.unpack_from(marker + kind, binary, position)[0]
    format_code = number(24, "H")
    if format_code not in SAMPLE_FORMATS:
        raise ValueError(f"Unsupported SEG-Y sample format {format_code}; fixed-point-with-gain code 4 requires a dedicated decoder.")
    revision = number(300, "H")
    if revision in (1, 2):
        repairs.append(f"Corrected legacy revision word {revision}.")
    elif revision not in (0, 256, 512, 513):
        raise ValueError(f"Unsupported SEG-Y revision word {revision}.")
    rev2 = revision in (512, 513)
    ns, interval = number(20, "H"), float(number(16, "H"))
    if rev2:
        ns = number(68, "I") or ns
        interval = number(72, "d") or interval
        if number(306, "I"):
            raise ValueError("SEG-Y trace-header extensions are not yet supported.")
    extended = number(304, "h") if revision else 0
    offset = tape_offset + 3600
    text_blocks = [prefix[tape_offset:tape_offset + 3200]]
    with path.open("rb") as stream:
        stream.seek(offset)
        if extended < 0:
            while stream.tell() + 3200 <= identity["size"]:
                block = stream.read(3200)
                text_blocks.append(block)
                if "ENDTEXT" in decode_text(block).upper().replace(" ", ""):
                    break
            else:
                raise ValueError("Extended textual headers have no EndText terminator.")
            offset = stream.tell()
            repairs.append("Resolved variable-count extended textual headers.")
        else:
            for _ in range(extended):
                block = stream.read(3200)
                if len(block) != 3200:
                    raise ValueError("Truncated extended textual header.")
                text_blocks.append(block)
            offset += extended * 3200
        if rev2 and number(320, "Q"):
            offset = number(320, "Q")
        stream.seek(offset)
        first_header = stream.read(240)
    if len(first_header) < 240:
        raise ValueError("Truncated SEG-Y: no complete trace header.")
    trace_ns = struct.unpack_from(marker + "H", first_header, 114)[0]
    trace_dt = struct.unpack_from(marker + "H", first_header, 116)[0]
    if ns < 2 and trace_ns >= 2:
        ns = trace_ns
        repairs.append("Recovered sample count from trace headers.")
    if interval <= 0 and trace_dt > 0:
        interval = float(trace_dt)
        repairs.append("Recovered sample interval from trace headers.")
    if ns < 2 or not np.isfinite(interval):
        raise ValueError("No valid sample count/interval in SEG-Y headers.")
    sample_size, format_name = SAMPLE_FORMATS[format_code]
    trace_size = 240 + ns * sample_size
    payload = identity["size"] - offset
    if rev2:
        trailers = number(328, "i")
        if trailers >= 0:
            payload -= trailers * 3200
        elif number(312, "Q"):
            payload = number(312, "Q") * trace_size
        else:
            raise ValueError("Unknown-count SEG-Y trailers need a declared trace count.")
    if payload > 0 and payload % trace_size and trace_ns >= 2 and trace_ns != ns:
        candidate_size = 240 + trace_ns * sample_size
        if payload % candidate_size == 0:
            ns, trace_size = trace_ns, candidate_size
            repairs.append("Recovered inconsistent binary sample count from trace headers.")
    if payload <= 0 or payload % trace_size:
        raise ValueError("Truncated or variable-length SEG-Y traces: file size does not match the declared sampling.")
    count = payload // trace_size
    text = "\n".join(decode_text(block) for block in text_blocks)
    dtype = np.dtype({"names": ["header"], "formats": [("u1", (240,))], "offsets": [0], "itemsize": trace_size})
    records = np.memmap(path, mode="r", dtype=dtype, offset=offset, shape=(count,))
    try:
        raw = records["header"]
        if headers is None:
            mapping, widths, evidence = detect_mapping(raw, text, endian)
        else:
            mapping = dict(DEFAULT_HEADERS, **headers)
            widths = dict.fromkeys(DEFAULT_HEADERS, 4)
            widths.update(header_widths or {})
            evidence = "manual header mapping"
        if set(mapping) != set(DEFAULT_HEADERS) or set(widths) != set(DEFAULT_HEADERS):
            raise ValueError("Header mappings must specify inline, crossline, X and Y.")
        spans = []
        for key, value in mapping.items():
            width = widths[key]
            if width not in (2, 4) or not isinstance(value, int) or not 1 <= value <= 241 - width:
                raise ValueError("Header fields must be 2 or 4 bytes within the 240-byte trace header.")
            spans.append(set(range(value, value + width)))
        if any(a & b for i, a in enumerate(spans) for b in spans[i + 1:]):
            raise ValueError("Inline, crossline, X and Y header fields must not overlap.")
        fields = {key: (value - 1, f"i{widths[key]}") for key, value in mapping.items()}
        fields.update({"scalar": (70, "i2"), "coordinate_units": (88, "i2"),
                       "delay": (108, "i2"), "ns": (114, "u2"), "dt": (116, "u2"), "time_scalar": (214, "i2")})
        values = {key: np.ascontiguousarray(raw[:, pos:pos + np.dtype(marker + typ).itemsize]).view(marker + typ).ravel().copy()
                  for key, (pos, typ) in fields.items()}
    finally:
        records._mmap.close()
    if np.any((values["ns"] != 0) & (values["ns"] != ns)) and ns <= 65535:
        raise ValueError("Variable trace sample counts are not supported.")
    if np.any((values["dt"] != 0) & (values["dt"] != interval)) and interval <= 65535:
        intervals = np.unique(values["dt"][values["dt"] != 0])
        if len(intervals) != 1:
            raise ValueError("Variable trace sample intervals are not supported.")
        interval = float(intervals[0])
        repairs.append("Recovered inconsistent binary interval from uniform trace headers.")
    time_scale = coordinate_scale(values["time_scalar"]) if revision else 1.0
    delays = values["delay"].astype(float) * time_scale
    hints = survey_hints(text, interval, float(delays[0]))
    if not np.allclose(delays, delays[0], rtol=0, atol=1e-9) and hints.get("domain") != "depth":
        raise ValueError("Trace recording delays differ; a common sampling axis is required.")
    return {"path": str(path.resolve()), "identity": identity, "endian": endian,
            "format_code": format_code, "format_name": format_name, "sample_size": sample_size,
            "trace_size": trace_size, "trace_offset": offset, "trace_count": count,
            "num_samples": ns, "sample_interval_us": interval, "delay_ms": float(delays[0]),
            "measurement_system": number(54, "H"), "headers": mapping, "header_widths": widths,
            "revision": revision, "text_header": text, "text_blocks": text_blocks,
            "binary_header": binary, "hints": hints, "detection_evidence": evidence, "repairs": repairs,
            "requires_standardization": bool(repairs or mapping != DEFAULT_HEADERS or any(w != 4 for w in widths.values())
                                              or format_code != 5 or revision != 256 or endian != "big"), **values}


def iter_trace_samples(survey, order=None, batch_size=512):
    """Decode supported encodings directly, including formats older segyio lacks."""
    code = survey["format_code"]
    marker = ">" if survey["endian"] == "big" else "<"
    ns = survey["num_samples"]
    kinds = {1: "u4", 2: "i4", 3: "i2", 5: "f4", 6: "f8", 8: "i1",
             9: "i8", 10: "u4", 11: "u2", 12: "u8", 16: "u1"}
    field_type = ("u1", (ns, 3)) if code in (7, 15) else (marker + kinds[code], (ns,))
    dtype = np.dtype({"names": ["samples"], "formats": [field_type], "offsets": [240], "itemsize": survey["trace_size"]})
    data = np.memmap(survey["path"], mode="r", dtype=dtype, offset=survey["trace_offset"], shape=(survey["trace_count"],))
    order = np.arange(survey["trace_count"]) if order is None else np.asarray(order)
    try:
        for start in range(0, len(order), batch_size):
            indices = order[start:start + batch_size]
            block = np.array(data["samples"][indices])
            if code == 1:
                from pzero.processing.segy_standardizer import ibm_to_ieee_vectorized
                block = ibm_to_ieee_vectorized(block.ravel()).reshape(len(indices), ns)
            elif code in (7, 15):
                octets = block.astype(np.int32)
                if marker == "<":
                    octets = octets[:, :, ::-1]
                block = (octets[:, :, 0] << 16) | (octets[:, :, 1] << 8) | octets[:, :, 2]
                if code == 7:
                    block = np.where(block & 0x800000, block - 0x1000000, block)
            yield indices, block.astype(np.float64 if code in (6, 9, 12) else np.float32)
    finally:
        data._mmap.close()


def coordinate_scale(scalars):
    scalars = np.asarray(scalars, dtype=float)
    result = np.ones_like(scalars)
    result[scalars > 0] = scalars[scalars > 0]
    result[scalars < 0] = 1.0 / np.abs(scalars[scalars < 0])
    return result


def prepare_geometry(survey, options):
    """Validate and normalize coordinates; return VTK-order trace/sample indices.

    Output XY is metres in a declared projected CRS or an explicitly unspecified
    local system. Z is signed time (ms/s) or elevation (m), never implicit depth.
    """
    if options.domain not in ("twt", "owt", "depth"):
        raise ValueError("Select two-way time, one-way time, or depth.")
    if options.domain == "depth" and options.vertical_units not in ("m", "ft"):
        raise ValueError("Depth sampling units must be metres or feet.")
    if options.domain != "depth" and options.vertical_units not in ("ms", "s"):
        raise ValueError("Time sampling units must be milliseconds or seconds.")
    if np.any(~np.isin(survey["coordinate_units"], [0, 1])):
        raise ValueError("Angular SEG-Y coordinates are not supported. Reproject to a linear XY system before import.")
    xy_units = options.xy_units
    if xy_units == "header":
        xy_units = {1: "m", 2: "ft"}.get(survey["measurement_system"], survey.get("hints", {}).get("xy_units"))
    if xy_units not in ("m", "ft"):
        raise ValueError("XY units are unspecified in the file. Select metres or feet.")
    scale = coordinate_scale(survey["scalar"])
    xy = np.column_stack((survey["x"] * scale, survey["y"] * scale)).astype(float)
    xy *= 0.3048 if xy_units == "ft" else 1.0
    if not np.any(xy):
        raise ValueError("All XY coordinates are zero. Select the correct X/Y header bytes.")
    valid_xy = np.any(xy != 0, axis=1) & (np.abs(survey["x"].astype(float)) < 2147483647) & (np.abs(survey["y"].astype(float)) < 2147483647)
    file_crs, target_crs = options.file_crs.strip(), options.target_crs.strip()
    if target_crs and not file_crs:
        raise ValueError("A file CRS is required to transform to an output CRS.")
    output_crs = file_crs
    if file_crs:
        from pyproj import CRS, Transformer

        source = CRS.from_user_input(file_crs)
        target = CRS.from_user_input(target_crs or file_crs)
        if not source.is_projected or not target.is_projected:
            raise ValueError("File and output CRS must be projected coordinate systems.")
        source_factors = np.array([axis.unit_conversion_factor for axis in source.axis_info[:2]])
        target_factors = np.array([axis.unit_conversion_factor for axis in target.axis_info[:2]])
        native = xy / source_factors
        x, y = Transformer.from_crs(source, target, always_xy=True).transform(
            native[:, 0], native[:, 1], errcheck=True
        )
        xy = np.column_stack((x, y)) * target_factors
        output_crs = target.to_string()
    if not np.all(np.isfinite(xy)):
        raise ValueError("Coordinate transformation produced non-finite coordinates.")
    ilines, il_index = np.unique(survey["inline"], return_inverse=True)
    xlines, xl_index = np.unique(survey["crossline"], return_inverse=True)
    ni, nx = len(ilines), len(xlines)
    if ni < 2 or nx < 2:
        raise ValueError("Expected a 3D post-stack survey with at least two inlines and crosslines. Check header mapping.")
    flat = il_index + ni * xl_index
    if len(np.unique(flat)) != len(flat):
        raise ValueError("Duplicate inline/crossline bins found (possibly prestack data). Import a post-stack volume.")
    if ni * nx > max(4 * len(flat), 100):
        raise ValueError("Survey bins are too sparse for a structural volume. Check line headers or process the gathers first.")
    # Fit physical line numbers, not array indices: decimated surveys can have
    # nonuniform line increments. Keep the original navigation for audit.
    il_parameter = (ilines.astype(float) - ilines[0]) / float(ilines[1] - ilines[0])
    xl_parameter = (xlines.astype(float) - xlines[0]) / float(xlines[1] - xlines[0])
    design = np.column_stack((np.ones(len(flat)), il_parameter[il_index], xl_parameter[xl_index]))
    if valid_xy.sum() < max(4, .95 * len(flat)):
        raise ValueError("Too many missing XY coordinates to establish survey geometry.")
    transform, _, rank, _ = np.linalg.lstsq(design[valid_xy], xy[valid_xy], rcond=None)
    vectors = transform[1:]
    lengths = np.linalg.norm(vectors, axis=1)
    if rank < 3 or np.min(lengths) <= 1e-9 or abs(np.linalg.det(vectors)) < 1e-6 * np.prod(lengths):
        raise ValueError("Survey XY coordinates form a collapsed grid. Check coordinate headers.")
    error = np.linalg.norm(design[valid_xy] @ transform - xy[valid_xy], axis=1)
    # Allow header quantization and modest navigation rounding, not arbitrary warps.
    quantization = float(np.max(scale[valid_xy])) * (.3048 if xy_units == "ft" else 1)
    tolerance = max(.01, min(2 * quantization, .05 * np.min(lengths)), .04 * np.min(lengths))
    if float(error.max()) > tolerance:
        raise ValueError(
            f"Survey is not an affine grid (maximum deviation {error.max():.3f} m, "
            f"tolerance {tolerance:.3f} m). Check header mapping or regularize the survey explicitly."
        )
    ii, jj = np.meshgrid(il_parameter, xl_parameter)
    grid_xy = transform[0] + ii.ravel()[:, None] * vectors[0] + jj.ravel()[:, None] * vectors[1]
    origin, step = options.sample_origin, options.sample_step
    if options.domain == "depth":
        hints = survey.get("hints", {})
        if hints.get("domain") == "depth" and hints.get("vertical_units") == options.vertical_units:
            origin = hints.get("sample_origin") if origin is None else origin
            step = hints.get("sample_step") if step is None else step
        if origin is None or step is None:
            raise ValueError("Depth data require an explicit first sample and sample interval; time headers cannot define depth.")
        factor = 0.3048 if options.vertical_units == "ft" else 1.0
        z_units = "m"
    else:
        factor = 1.0
        z_units = options.vertical_units
        time_factor = 1.0 if z_units == "ms" else 0.001
        if origin is None:
            origin = survey["delay_ms"] * time_factor
        if step is None:
            step = survey["sample_interval_us"] / 1000.0 * time_factor
    if not np.isfinite(origin) or not np.isfinite(step) or step <= 0:
        raise ValueError("First sample must be finite and sample interval must be positive.")
    samples = (origin + np.arange(survey["num_samples"]) * step) * factor
    z = -samples if options.negate_z else samples
    output_domain = options.domain
    if options.depth_model != "none":
        if options.domain == "depth":
            raise ValueError("This volume is already in depth; time-to-depth conversion is not applicable.")
        if not options.negate_z:
            raise ValueError("Depth conversion requires input travel times increasing downward.")
        times = samples * (.001 if options.vertical_units == "ms" else 1)
        relative = times - options.model_time_datum_s
        if not np.isfinite(options.depth_datum_m) or not np.isfinite(options.model_time_datum_s):
            raise ValueError("Model reference time and depth datum must be finite.")
        if options.depth_model == "constant":
            velocity = options.velocity_m_s
            if velocity is None or not np.isfinite(velocity) or velocity <= 0:
                raise ValueError("Enter a positive velocity in m/s for depth conversion.")
            depths = relative * velocity / (2 if options.domain == "twt" else 1)
        elif options.depth_model == "table":
            table = np.asarray(options.time_depth_table, dtype=float)
            if table.ndim != 2 or table.shape[1] != 2 or len(table) < 2 or not np.all(np.isfinite(table)):
                raise ValueError("Provide at least two finite time (seconds), depth (metres) table rows.")
            if np.any(np.diff(table[:, 0]) <= 0) or np.any(np.diff(table[:, 1]) <= 0):
                raise ValueError("Time-depth table times and depths must be strictly increasing.")
            if relative.min() < table[0, 0] - 1e-10 or relative.max() > table[-1, 0] + 1e-10:
                raise ValueError("Time-depth table must cover the entire input time range; extrapolation is disabled.")
            depths = np.interp(relative, table[:, 0], table[:, 1])
        else:
            raise ValueError("Unknown time-to-depth model.")
        z = options.depth_datum_m - depths
        z_units, output_domain = "m", "depth"
    sample_order = np.argsort(z)
    trace_order = np.argsort(flat)
    return {
        "xy": grid_xy, "original_xy": xy, "z": z[sample_order], "trace_order": trace_order,
        "grid_ids": flat, "axis_parameters": (il_parameter, xl_parameter),
        "missing_bins": ni * nx - len(flat), "recovered_coordinates": int((~valid_xy).sum()),
        "output_domain": output_domain,
        "sample_order": sample_order, "inlines": ilines, "crosslines": xlines,
        "dimensions": (ni, nx, len(z)), "z_units": z_units,
        "output_crs": output_crs, "xy_units": xy_units,
        "sample_origin": float(origin), "sample_step": float(step),
        "max_grid_residual_m": float(error.max()),
    }


def read_grid(path, options, survey=None):
    """Import amplitudes and coordinates with the same explicit trace ordering."""
    import pyvista as pv

    if isinstance(options, dict):
        options = SegyImportOptions(**options)
    if not isinstance(options, SegyImportOptions):
        raise ValueError("SEG-Y import options are required; choose the coordinate and vertical domain settings first.")
    if survey is None:
        survey = inspect_segy(path, options.endian, options.headers, options.header_widths)
    if survey["path"] != str(Path(path).resolve()) or survey["identity"] != file_identity(path):
        raise ValueError("The SEG-Y file changed after inspection. Reopen the import dialog.")
    if ((options.headers is not None and survey["headers"] != options.headers)
            or (options.header_widths is not None and survey["header_widths"] != options.header_widths)
            or options.endian not in ("auto", survey["endian"])):
        raise ValueError("Header settings changed after inspection. Preview the survey again.")
    geometry = prepare_geometry(survey, options)
    ns = survey["num_samples"]
    nt = len(geometry["xy"])
    amplitude_type = np.float64 if survey["format_code"] in (6, 9, 12) else np.float32
    amplitudes = np.full((ns, nt), np.nan, dtype=amplitude_type)
    for indices, block in iter_trace_samples(survey):
        if not np.all(np.isfinite(block)):
            raise ValueError("SEG-Y contains non-finite amplitudes; clean or mask these samples before import.")
        amplitudes[:, geometry["grid_ids"][indices]] = block[:, geometry["sample_order"]].T
    if survey["identity"] != file_identity(path):
        raise ValueError("The SEG-Y file changed while reading amplitudes. Import it again.")
    points = np.empty((ns, nt, 3), dtype=np.float64)
    points[:, :, :2] = geometry["xy"]
    points[:, :, 2] = geometry["z"][:, None]
    grid = pv.StructuredGrid()
    grid.points = points.reshape(-1, 3)
    grid.dimensions = geometry["dimensions"]
    grid.point_data["intensity"] = amplitudes.reshape(-1)
    if geometry["missing_bins"]:
        # VTK HIDDENPOINT (2) prevents rendering holes as measured amplitudes.
        grid.point_data["vtkGhostType"] = np.where(np.isnan(amplitudes), 2, 0).astype(np.uint8).ravel()
    grid.set_active_scalars("intensity")
    metadata = {
        "schema_version": 1, "source_file": survey["path"],
        "source_identity": survey["identity"], "import_options": options.to_dict(),
        "vertical_domain": geometry["output_domain"], "vertical_units": geometry["z_units"],
        "vertical_datum": options.vertical_datum, "z_positive": "up",
        "xy_units": "m", "crs": geometry["output_crs"],
        "sample_origin": geometry["sample_origin"], "sample_step": geometry["sample_step"],
        "sample_input_units": options.vertical_units,
        "coordinate_scalar_applied": True, "max_grid_residual_m": geometry["max_grid_residual_m"],
        "missing_bins": geometry["missing_bins"], "recovered_coordinates": geometry["recovered_coordinates"],
        "detected_headers": survey["headers"], "header_widths": survey["header_widths"],
        "detection_evidence": survey["detection_evidence"], "source_hints": survey.get("hints", {}),
        "repairs": survey.get("repairs", []), "depth_model": options.depth_model,
        "geometry_status": "Affine navigation fit; original measured XY retained in field data",
    }
    set_seismic_metadata(grid, metadata)
    grid.field_data["seismic_inline_numbers"] = geometry["inlines"]
    grid.field_data["seismic_crossline_numbers"] = geometry["crosslines"]
    grid.field_data["seismic_sample_indices"] = geometry["sample_order"]
    grid.field_data["seismic_original_xy"] = geometry["original_xy"]
    grid.field_data["seismic_original_grid_ids"] = geometry["grid_ids"]
    for axis, parameters in enumerate((*geometry["axis_parameters"],
            (geometry["z"] - geometry["z"][0]) / (geometry["z"][1] - geometry["z"][0]))):
        grid.field_data[f"seismic_axis_{axis}"] = parameters
    return grid


def set_seismic_metadata(vtk_object, metadata):
    from vtk import vtkStringArray

    array = vtkStringArray()
    array.SetName(METADATA_KEY)
    array.InsertNextValue(json.dumps(metadata, sort_keys=True))
    vtk_object.GetFieldData().RemoveArray(METADATA_KEY)
    vtk_object.GetFieldData().AddArray(array)


def get_seismic_metadata(vtk_object):
    if vtk_object is None:
        return {}
    array = vtk_object.GetFieldData().GetAbstractArray(METADATA_KEY)
    if array is None or not array.GetNumberOfValues():
        return {}
    try:
        return json.loads(array.GetValue(0))
    except (TypeError, ValueError):
        return {}
