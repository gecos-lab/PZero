"""Canonical SEG-Y geometry headers and IEEE sample-format conversion.

Coordinates and line numbers are retained. Unsupported storage fails before the
output is replaced; callers can safely retain an existing destination file.
"""

import os
from pathlib import Path
import struct
import tempfile

import numpy as np

from pzero.imports.segy_reader import DEFAULT_HEADERS, file_identity, inspect_segy, iter_trace_samples


def read_binary_header(file):
    """Read the conventional big-endian interval, count and format fields."""
    file.seek(3200)
    header = file.read(400)
    if len(header) != 400:
        raise ValueError("Truncated SEG-Y binary header")
    return tuple(struct.unpack(">H", header[offset:offset + 2])[0] for offset in (16, 20, 24))


def analyze_segy_parameters(input_file):
    survey = inspect_segy(input_file)
    return {
        "num_samples": survey["num_samples"],
        "sample_interval": survey["sample_interval_us"],
        "format_code": survey["format_code"],
        "trace_size": survey["trace_size"], "trace_header_size": 240,
        "sample_size": survey["sample_size"], "trace_offset": survey["trace_offset"],
        "endian": survey["endian"],
    }


def ibm_to_ieee_vectorized(ibm_data):
    """
    Convert IBM 370 floating point to IEEE 754 - vectorized numpy version.
    Much faster than sample-by-sample conversion.
    
    Args:
        ibm_data: numpy array of uint32 (big-endian IBM floats as integers)
    
    Returns:
        numpy array of float32 (IEEE floats)
    """
    # Handle zeros
    result = np.zeros(len(ibm_data), dtype=np.float32)
    nonzero_mask = ibm_data != 0
    
    if not np.any(nonzero_mask):
        return result
    
    ibm_nonzero = ibm_data[nonzero_mask].astype(np.int64)
    
    # Extract IBM components
    sign = (ibm_nonzero >> 31) & 1
    exponent = (ibm_nonzero >> 24) & 0x7F
    mantissa = ibm_nonzero & 0x00FFFFFF
    
    # Handle zero mantissa
    mantissa_nonzero = mantissa != 0
    
    # IBM exponent is base-16, excess-64
    # Value = (-1)^sign * 16^(exp-64) * (mantissa / 2^24)
    # Value = (-1)^sign * mantissa * 2^(4*(exp-64) - 24)
    exp16 = exponent - 64
    
    # Calculate IEEE value
    ieee_values = np.zeros(len(ibm_nonzero), dtype=np.float64)
    valid = mantissa_nonzero
    ieee_values[valid] = mantissa[valid] * np.power(2.0, 4 * exp16[valid] - 24)
    
    # Apply sign
    ieee_values[sign == 1] *= -1
    
    result[nonzero_mask] = ieee_values.astype(np.float32)
    return result


def ibm_to_ieee(ibm_bytes):
    """
    Convert single IBM 370 floating point to IEEE 754 floating point.
    Used for small conversions where vectorization overhead isn't worth it.
    """
    ibm_int = struct.unpack(">I", ibm_bytes)[0]
    
    if ibm_int == 0:
        return 0.0
    
    sign = (ibm_int >> 31) & 1
    exponent = (ibm_int >> 24) & 0x7F
    mantissa = ibm_int & 0x00FFFFFF
    
    if mantissa == 0:
        return 0.0
    
    exp16 = exponent - 64
    ieee_value = mantissa * (2.0 ** (4 * exp16 - 24))
    
    if sign:
        ieee_value = -ieee_value
    
    return ieee_value


def standardize_segy_for_pzero(input_file, output_file, print_fn=print, survey=None):
    """Write IEEE samples and canonical geometry fields without changing navigation.

    Original byte order and unrelated trace fields are retained. When remapping,
    the original textual header is retained as an extended textual header.
    Output is validated before atomically replacing the destination.
    """
    source_path, destination = Path(input_file).resolve(), Path(output_file).resolve()
    if source_path == destination or (destination.exists() and os.path.samefile(source_path, destination)):
        raise ValueError("Input and output SEG-Y paths must differ.")
    survey = inspect_segy(source_path) if survey is None else survey
    if survey["path"] != str(source_path) or survey["identity"] != file_identity(source_path):
        raise ValueError("The source SEG-Y changed after inspection.")
    marker = ">" if survey["endian"] == "big" else "<"
    remap = survey["headers"] != DEFAULT_HEADERS or any(w != 4 for w in survey["header_widths"].values())
    texts = list(survey["text_blocks"])
    if remap:
        lines = ["C 1 PZERO STANDARDIZED COPY - ORIGINAL TEXT FOLLOWS IN EXTENDED HEADER",
                 "C 2 INLINE: 189-192  CROSSLINE: 193-196",
                 "C 3 CDP_X: 181-184  CDP_Y: 185-188",
                 "C 4 ORIGINAL COORDINATES, SCALARS, LINE NUMBERS AND SAMPLING RETAINED"]
        texts.insert(0, "".join(line.ljust(80) for line in lines).ljust(3200).encode("ascii"))
    binary = bytearray(survey["binary_header"])
    wide = survey["format_code"] in (6, 9, 12)
    output_format = 6 if wide else 5
    ns, interval = survey["num_samples"], survey["sample_interval_us"]
    rev2 = wide or ns > 65535 or interval > 65535 or interval != int(interval)
    struct.pack_into(marker + "H", binary, 24, output_format)
    struct.pack_into(marker + "H", binary, 300, 512 if rev2 else 256)
    struct.pack_into(marker + "H", binary, 302, 1)
    struct.pack_into(marker + "h", binary, 304, len(texts) - 1)
    struct.pack_into(marker + "H", binary, 20, ns if ns <= 65535 else 0)
    struct.pack_into(marker + "H", binary, 16, int(interval) if interval <= 65535 else 0)
    if rev2:
        struct.pack_into(marker + "I", binary, 68, ns)
        struct.pack_into(marker + "d", binary, 72, interval)
        struct.pack_into(marker + "I", binary, 96, 0x01020304)
    # Remove storage offsets/trailers from the original; this copy is contiguous.
    binary[306:332] = bytes(26)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, suffix=".sgy", delete=False) as target:
            temporary = Path(target.name)
            target.write(texts[0]); target.write(binary)
            for block in texts[1:]:
                target.write(block)
            with source_path.open("rb") as raw:
                for indices, samples in iter_trace_samples(survey):
                    if not np.all(np.isfinite(samples)):
                        raise ValueError("Non-finite amplitudes during conversion.")
                    for index, values in zip(indices, samples):
                        raw.seek(survey["trace_offset"] + int(index) * survey["trace_size"])
                        header = bytearray(raw.read(240))
                        if len(header) != 240:
                            raise ValueError("Truncated trace header during conversion.")
                        if survey["revision"] == 0:
                            # This field was undefined in revision 0. Do not let
                            # unrelated vendor bytes acquire time-scalar meaning.
                            struct.pack_into(marker + "h", header, 214, 0)
                        if remap:
                            for key, start in DEFAULT_HEADERS.items():
                                struct.pack_into(marker + "i", header, start - 1, int(survey[key][index]))
                        target.write(header)
                        target.write(values.astype(marker + ("f8" if wide else "f4")).tobytes())
        verify_segy_structure(temporary, print_fn=print_fn)
        if file_identity(source_path) != survey["identity"]:
            raise ValueError("The source SEG-Y changed during conversion.")
        os.replace(temporary, destination)
        temporary = None
        print_fn(f"Standardized {survey['trace_count']} traces; navigation and sampling preserved.")
        return True
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def verify_segy_structure(output_file, print_fn=print):
    survey = inspect_segy(output_file, headers=DEFAULT_HEADERS)
    for _, samples in iter_trace_samples(survey, order=[0, survey["trace_count"] - 1]):
        if not np.all(np.isfinite(samples)):
            raise ValueError("Non-finite amplitudes in standardized output.")
    print_fn("Verified SEG-Y headers, trace sizes and sample decoding.")
    return True


def convert_to_standard_segy(input_file, output_file, print_fn=print):
    return standardize_segy_for_pzero(input_file, output_file, print_fn=print_fn)
