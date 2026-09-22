"""Header-layout discovery from textual declarations and trace geometry."""

import re
import numpy as np


def decode_text(raw):
    candidates = [raw.decode(codec, errors="replace") for codec in ("ascii", "cp500")]
    text = max(candidates, key=lambda value: sum(c.isalnum() or c == " " for c in value))
    return "\n".join(text[i:i + 80].strip() for i in range(0, len(text), 80))


def header_declarations(text):
    """Extract byte starts and widths without interpreting processing-history numbers."""
    patterns = {
        "inline": r"(?:IN[ _-]?LINE(?:_NO)?|ILINE_NO|LINE NUMBER|LINE)",
        "crossline": r"(?:CROSS[ _-]?LINE|X[ _-]?LINE(?:_NO)?|CDP NUMBER|CDP|TRACE NUMBER)",
        "x": r"(?:CDP[ _-]?X(?:-COORD)?|SOURCE X|X COORDINATE|X LOCATION|UTM-X|BINX \(CDPX\))",
        "y": r"(?:CDP[ _-]?Y(?:-COORD)?|SOURCE Y|Y COORDINATE|Y LOCATION|UTM-Y|BINY \(CDPY\))",
    }
    found = {}
    for line in text.upper().splitlines():
        if "BINARY" in line:
            continue
        for key, label in patterns.items():
            # Forward and reverse forms, e.g. INLINE: 189-192 and
            # BYTES 187-188 CROSSLINE NUMBER (3D).
            forms = [
                rf"\b{label}\b(?: NUMBER)?\s*(?::|=)?\s*(?:TRACE\s*)?(?:BYTES?\s*)?(\d{{1,3}})\s*[-–]\s*(\d{{1,3}})",
                rf"\b{label}\b(?: NUMBER)?\s*[:=]\s*(?:BYTES?\s*)?(\d{{1,3}})(?=\s|$)",
                rf"BYTES?\s*(\d{{1,3}})\s*[-–]\s*(\d{{1,3}})\s+{label}\b",
            ]
            for pattern in forms:
                match = re.search(pattern, line)
                if match:
                    start = int(match[1])
                    width = int(match[2]) - start + 1 if match.lastindex == 2 else 4
                    if width in (2, 4) and 1 <= start <= 241 - width:
                        found[key] = (start, width)
                    break
        for key, field in (("inline", "ILINE_NO"), ("crossline", "XLINE_NO")):
            match = re.search(rf"{field},([24])I,,(\d+)", line)
            if match:
                found[key] = (int(match[2]), int(match[1]))
    return found


def header_column(headers, start, width, endian):
    dtype = (">" if endian == "big" else "<") + f"i{width}"
    return np.ascontiguousarray(headers[:, start - 1:start - 1 + width]).view(dtype).ravel()


def detect_mapping(headers, text, endian):
    """Rank declared/vendor layouts by repeated line IDs and XY grid consistency.

    A deterministic trace sample spans the entire file. The selected mapping is
    then read and validated on *all* traces by the caller. No trace-count
    factorization or file-name-specific header assignment is used.
    """
    count = len(headers)
    rng = np.random.default_rng(8128)
    ids = np.unique(np.r_[0, count - 1, rng.choice(count, min(count, 8192), replace=False)])
    sample = np.array(headers[ids])
    cache = {}

    def column(field):
        if field not in cache:
            cache[field] = header_column(sample, *field, endian)
        return cache[field]

    declared = header_declarations("\n".join(text.splitlines()[:40]) if "PZERO STANDARDIZED COPY" in text[:160] else text)
    base = {"inline": (189, 4), "crossline": (193, 4), "x": (181, 4), "y": (185, 4)}
    layouts = [(dict(base, **declared), "textual-header declarations", 0)] if declared else []
    layouts.append((base, "standard SEG-Y fields", 1))
    pairs = [(189, 193), (17, 25), (221, 21), (9, 21), (5, 21), (17, 13), (181, 185)]
    coordinate_pairs = [(181, 185), (73, 77), (81, 85), (201, 205)]
    for il, xl in pairs:
        for x, y in coordinate_pairs:
            layouts.append((dict(zip(base, [(il, 4), (xl, 4), (x, 4), (y, 4)])), "recognized header layout", 3))
    layouts.append((dict(zip(base, [(191, 2), (187, 2), (201, 4), (205, 4)])), "two-byte line numbers", 2))

    scalar = column((71, 2)).astype(float)
    scales = np.where(scalar > 0, scalar, 1 / np.maximum(np.abs(scalar), 1))

    def score(layout):
        spans = [set(range(start, start + width)) for start, width in layout.values()]
        if any(a & b for k, a in enumerate(spans) for b in spans[k + 1:]):
            return None
        il, xl, x, y = [column(layout[key]) for key in base]
        if len(np.unique(il)) < 2 or len(np.unique(xl)) < 2:
            return None
        if max(np.abs(il.astype(float)).max(), np.abs(xl.astype(float)).max()) > 10_000_000:
            return None
        xy = np.column_stack((x, y)) * scales[:, None]
        valid = np.any(xy != 0, axis=1) & (np.abs(xy).max(axis=1) < 1e10)
        if valid.sum() < max(4, len(ids) // 2):
            return None
        design = np.column_stack((np.ones(valid.sum()), il[valid] - float(il[valid].min()), xl[valid] - float(xl[valid].min())))
        fit, _, rank, _ = np.linalg.lstsq(design, xy[valid], rcond=None)
        if rank < 3 or abs(np.linalg.det(fit[1:])) < 1e-12:
            return None
        errors = np.linalg.norm(design @ fit - xy[valid], axis=1)
        extent = np.linalg.norm(np.ptp(xy[valid], axis=0))
        residual = float(np.quantile(errors, .99)) / max(extent, 1)
        if residual > .005:
            return None
        # Repeated bin pairs distinguish prestack gathers from a structural cube.
        duplicate_fraction = 1 - len(np.unique(np.column_stack((il, xl)), axis=0)) / len(il)
        return residual + duplicate_fraction

    ranked = []
    for layout, evidence, priority in layouts:
        value = score(layout)
        if value is not None:
            ranked.append((value + priority * .001, layout, evidence))
    if not ranked:
        # Search other aligned four-byte words for undocumented line IDs. Pair
        # candidates must pass the same spatial test as the known layouts.
        candidates = []
        seen = set()
        for start in range(1, 238, 4):
            values = column((start, 4))
            unique, inverse = np.unique(values, return_inverse=True)
            if 2 <= len(unique) < len(ids) * .9 and np.abs(unique.astype(float)).max() < 1_000_000:
                key = inverse.tobytes()
                if key not in seen:
                    seen.add(key)
                    candidates.append((start, 4))
        for il in candidates:
            for xl in candidates:
                if il == xl:
                    continue
                for x, y in coordinate_pairs:
                    layout = dict(zip(base, [il, xl, (x, 4), (y, 4)]))
                    value = score(layout)
                    if value is not None:
                        ranked.append((value + .01, layout, "scanned trace-header words"))
    if not ranked:
        if "inline" in declared and "crossline" in declared:
            pairs = np.column_stack((column(declared["inline"]), column(declared["crossline"])))
            if len(np.unique(pairs, axis=0)) < .95 * len(pairs):
                raise ValueError("Repeated inline/crossline bins indicate prestack gathers. Stacking/migration is required before importing a structural volume; format conversion cannot replace seismic processing.")
        raise ValueError("Could not identify a consistent survey header layout automatically. Select header bytes and widths on the SEG-Y headers tab.")
    ranked.sort(key=lambda item: item[0])
    _, layout, evidence = ranked[0]
    return ({key: value[0] for key, value in layout.items()},
            {key: value[1] for key, value in layout.items()}, evidence)


def survey_hints(text, interval, delay):
    """Read final sampling declarations, not time values in processing history."""
    upper = text.upper()
    result = {"domain": None, "data_kind": "amplitude", "notes": []}
    if re.search(r"(?:VELOCITY (?:FIELD|MODEL)|DEPTH VELOCITY)", upper):
        result["data_kind"] = "interval_velocity" if "INTERVAL" in upper else "velocity"
    depth_steps = re.findall(r"SAMPLE\s+(?:INTERVAL|RATE)\s*[:=]\s*([\d.]+)\s*(M\b|METRES\b|METERS\b|FT\b|FEET\b)", upper)
    first = re.findall(r"FIRST SAMPLE\s*[:=]\s*(-?[\d.]+)", upper)
    last = re.findall(r"LAST SAMPLE\s*[:=]\s*(-?[\d.]+)", upper)
    if depth_steps:
        step, unit = depth_steps[-1]
        result.update(domain="depth", vertical_units="ft" if unit in ("FT", "FEET") else "m",
                      sample_step=float(step), sample_origin=float(first[-1]) if first else None)
        if not first:
            result["notes"].append("Depth interval is declared; first depth is not declared. Review the first sample.")
        result["notes"].append("Depth sampling read from the textual header.")
    elif re.search(r"\b(?:TIME MIN|FINAL TIME|START TIME|SAMPLE RATE \(USEC\))\b", upper):
        result.update(domain="twt", vertical_units="ms")
        result["notes"].append("Time-domain data indicated by the header; review TWT versus OWT.")
    if last:
        result["last_sample"] = float(last[-1])
    if "NZTM" in upper and "NZGD2000" in upper:
        result.update(file_crs="EPSG:2193", xy_units="m")
    else:
        zone = re.search(r"(?:UTM\s+ZONE|ZONE)\s*[:=]?\s*(\d{1,2})\s*([NS])?\b", upper)
        if zone and "UTM" in upper:
            number, hemisphere = int(zone[1]), zone[2]
            if 1 <= number <= 60:
                if re.search(r"WGS\s*[- ]?84", upper) and hemisphere:
                    result.update(file_crs=f"EPSG:{(32700 if hemisphere == 'S' else 32600) + number}", xy_units="m")
                elif re.search(r"ED\s*[- ]?50", upper) and hemisphere != "S":
                    result.update(file_crs=f"EPSG:{23000 + number}", xy_units="m")
    return result
