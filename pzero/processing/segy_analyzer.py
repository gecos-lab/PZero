"""segy_analyzer.py - Standalone SEG-Y File Analyzer
PZero© Andrea Bistacchi

A diagnostic tool to analyze SEG-Y files and understand their structure.
Helps identify why files may be non-standard and how to fix them.

Usage: python segy_analyzer.py [optional_segy_file]
"""

import sys
import os
import struct
from pathlib import Path

# Try to import PySide6, fall back to message if not available
try:
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QTextEdit, QLabel, QFileDialog, QTabWidget,
        QTableWidget, QTableWidgetItem, QHeaderView, QSplitter,
        QGroupBox, QScrollArea, QFrame
    )
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont, QColor
    HAS_GUI = True
except ImportError:
    HAS_GUI = False
    print("PySide6 not available. Running in console mode.")


# ============================================================================
# SEG-Y Analysis Functions
# ============================================================================

def read_textual_header(filepath):
    """Read and decode the 3200-byte textual header."""
    with open(filepath, 'rb') as f:
        raw = f.read(3200)
    
    # Try EBCDIC first, then ASCII
    try:
        text = raw.decode('cp500')  # EBCDIC
        encoding = "EBCDIC"
    except:
        try:
            text = raw.decode('ascii', errors='replace')
            encoding = "ASCII"
        except:
            text = str(raw)
            encoding = "Unknown"
    
    # Format into 40 lines of 80 characters
    lines = [text[i:i+80] for i in range(0, 3200, 80)]
    return '\n'.join(lines), encoding


def read_binary_header(filepath):
    """Read and parse the 400-byte binary header."""
    with open(filepath, 'rb') as f:
        f.seek(3200)
        raw = f.read(400)
    
    # Key binary header fields (SEG-Y Rev 1/2)
    fields = {
        'Job ID': (0, 4, '>l'),
        'Line Number': (4, 8, '>l'),
        'Reel Number': (8, 12, '>l'),
        'Traces per Ensemble': (12, 14, '>H'),
        'Aux Traces per Ensemble': (14, 16, '>H'),
        'Sample Interval (μs)': (16, 18, '>H'),
        'Original Sample Interval': (18, 20, '>H'),
        'Samples per Trace': (20, 22, '>H'),
        'Original Samples per Trace': (22, 24, '>H'),
        'Data Format Code': (24, 26, '>H'),
        'Ensemble Fold': (26, 28, '>H'),
        'Trace Sorting Code': (28, 30, '>H'),
        'Vertical Sum Code': (30, 32, '>H'),
        'Measurement System': (54, 56, '>H'),
        'SEG-Y Revision': (300, 302, '>H'),
        'Fixed Trace Length Flag': (302, 304, '>H'),
        'Extended Headers Count': (304, 306, '>H'),
    }
    
    result = {}
    for name, (start, end, fmt) in fields.items():
        try:
            value = struct.unpack(fmt, raw[start:end])[0]
            result[name] = value
        except:
            result[name] = "Error"
    
    # Interpret data format code
    format_codes = {
        1: "IBM Float (4 bytes)",
        2: "32-bit Integer",
        3: "16-bit Integer",
        4: "32-bit Fixed Point with Gain",
        5: "IEEE Float (4 bytes)",
        6: "IEEE Double (8 bytes)",
        7: "24-bit Integer",
        8: "8-bit Integer",
    }
    result['Data Format Description'] = format_codes.get(
        result.get('Data Format Code', 0), "Unknown"
    )
    
    # Interpret trace sorting
    sorting_codes = {
        0: "Unknown",
        1: "As recorded",
        2: "CDP ensemble",
        3: "Single fold continuous profile",
        4: "Horizontally stacked",
        5: "Common source point",
        6: "Common receiver point",
        7: "Common offset point",
        8: "Common mid-point",
        9: "Common conversion point",
    }
    result['Trace Sorting Description'] = sorting_codes.get(
        result.get('Trace Sorting Code', 0), "Unknown"
    )
    
    return result, raw


def read_trace_headers(filepath, num_traces=10, trace_size=None):
    """Read trace headers for the first N traces."""
    file_size = os.path.getsize(filepath)
    
    with open(filepath, 'rb') as f:
        # Get samples per trace from binary header
        f.seek(3200 + 20)
        samples = struct.unpack('>H', f.read(2))[0]
        
        f.seek(3200 + 24)
        format_code = struct.unpack('>H', f.read(2))[0]
        
        # Calculate trace size
        sample_size = 4  # Default for float/int32
        if format_code == 3:
            sample_size = 2
        elif format_code == 8:
            sample_size = 1
        elif format_code == 6:
            sample_size = 8
            
        if trace_size is None:
            trace_size = 240 + samples * sample_size
        
        total_traces = (file_size - 3600) // trace_size
        
        traces = []
        for i in range(min(num_traces, total_traces)):
            pos = 3600 + i * trace_size
            f.seek(pos)
            header = f.read(240)
            
            if len(header) != 240:
                break
            
            trace_info = parse_trace_header(header, i)
            traces.append(trace_info)
    
    return traces, total_traces, trace_size, samples


def parse_trace_header(header, trace_num):
    """Parse a single trace header - standard locations."""
    fields = {
        'Trace #': trace_num,
        'Trace Seq in Line (1-4)': struct.unpack('>l', header[0:4])[0],
        'Trace Seq in File (5-8)': struct.unpack('>l', header[4:8])[0],
        'Field Record (9-12)': struct.unpack('>l', header[8:12])[0],
        'Trace in Record (13-16)': struct.unpack('>l', header[12:16])[0],
        'Source Point (17-20)': struct.unpack('>l', header[16:20])[0],
        'CDP (21-24)': struct.unpack('>l', header[20:24])[0],
        'Trace in CDP (25-28)': struct.unpack('>l', header[24:28])[0],
        'Trace ID (29-30)': struct.unpack('>H', header[28:30])[0],
        'Coord Scalar (71-72)': struct.unpack('>h', header[70:72])[0],
        'Source X (73-76)': struct.unpack('>l', header[72:76])[0],
        'Source Y (77-80)': struct.unpack('>l', header[76:80])[0],
        'Group X (81-84)': struct.unpack('>l', header[80:84])[0],
        'Group Y (85-88)': struct.unpack('>l', header[84:88])[0],
        'Coord Units (89-90)': struct.unpack('>H', header[88:90])[0],
        'Samples (115-116)': struct.unpack('>H', header[114:116])[0],
        'Sample Interval (117-118)': struct.unpack('>H', header[116:118])[0],
        'CDP X (181-184)': struct.unpack('>l', header[180:184])[0],
        'CDP Y (185-188)': struct.unpack('>l', header[184:188])[0],
        'Inline 3D (189-192)': struct.unpack('>l', header[188:192])[0],
        'Crossline 3D (193-196)': struct.unpack('>l', header[192:196])[0],
    }
    return fields


def scan_all_trace_header_locations(filepath, sample_size=1000):
    """
    Scan ALL possible trace header byte locations to detect where coordinates
    are actually stored. This helps identify non-standard files.
    
    Standard SEG-Y locations:
    - CDP X/Y: bytes 181-184, 185-188 (4-byte)
    - Inline 3D: bytes 189-192 (4-byte)
    - Crossline 3D: bytes 193-196 (4-byte)
    
    Non-standard files may store at:
    - Source X/Y: bytes 73-76, 77-80
    - Group X/Y: bytes 81-84, 85-88
    - Poseidon-style: Inline at 191-192 (2-byte), Crossline at 187-188 (2-byte)
    - Poseidon-style: CDP X at 201-204, CDP Y at 205-208
    """
    file_size = os.path.getsize(filepath)
    
    # All potential coordinate locations (byte offset, size, name)
    locations_4byte = [
        (0, 'Trace Seq Line (1-4)'),
        (4, 'Trace Seq File (5-8)'),
        (8, 'Field Record (9-12)'),
        (12, 'Trace in Record (13-16)'),
        (16, 'Source Point (17-20)'),
        (20, 'CDP Number (21-24)'),
        (24, 'Trace in CDP (25-28)'),
        (72, 'Source X (73-76)'),
        (76, 'Source Y (77-80)'),
        (80, 'Group X (81-84)'),
        (84, 'Group Y (85-88)'),
        (180, 'CDP X (181-184) STANDARD'),
        (184, 'CDP Y (185-188) STANDARD'),
        (188, 'Inline 3D (189-192) STANDARD'),
        (192, 'Crossline 3D (193-196) STANDARD'),
        (200, 'Non-std CDP X (201-204)'),
        (204, 'Non-std CDP Y (205-208)'),
    ]
    
    locations_2byte = [
        (186, 'Non-std XL 2-byte (187-188)'),
        (190, 'Non-std IL 2-byte (191-192)'),
    ]
    
    with open(filepath, 'rb') as f:
        f.seek(3200 + 20)
        samples = struct.unpack('>H', f.read(2))[0]
        trace_size = 240 + samples * 4
        total_traces = (file_size - 3600) // trace_size
        
        step = max(1, total_traces // sample_size)
        
        # Collect values from each location
        all_values = {loc[1]: [] for loc in locations_4byte + locations_2byte}
        scalars = []
        
        for i in range(0, total_traces, step):
            pos = 3600 + i * trace_size
            f.seek(pos)
            header = f.read(240)
            
            if len(header) != 240:
                break
            
            scalar = struct.unpack('>h', header[70:72])[0]
            scalars.append(scalar)
            
            # Read 4-byte locations
            for offset, name in locations_4byte:
                val = struct.unpack('>l', header[offset:offset+4])[0]
                all_values[name].append(val)
            
            # Read 2-byte locations
            for offset, name in locations_2byte:
                val = struct.unpack('>H', header[offset:offset+2])[0]
                all_values[name].append(val)
    
    # Analyze each location
    analysis = {}
    for name, values in all_values.items():
        if values:
            unique = set(values)
            non_zero = [v for v in values if v != 0]
            analysis[name] = {
                'min': min(values),
                'max': max(values),
                'unique_count': len(unique),
                'all_zero': all(v == 0 for v in values),
                'all_same': len(unique) == 1,
                'non_zero_count': len(non_zero),
                'has_data': len(unique) > 1 and not all(v == 0 for v in values),
                'sample_values': values[:5]
            }
    
    # Also analyze scalars
    scalar_unique = set(scalars)
    analysis['Coord Scalar (71-72)'] = {
        'min': min(scalars) if scalars else 0,
        'max': max(scalars) if scalars else 0,
        'unique_count': len(scalar_unique),
        'all_zero': all(s == 0 for s in scalars),
        'all_same': len(scalar_unique) == 1,
        'sample_values': scalars[:5]
    }
    
    return analysis, total_traces


def detect_coordinate_source(filepath, sample_size=1000):
    """
    Detect where coordinates are actually stored in this file.
    Returns a dict with detected sources for inline, crossline, X, and Y.
    """
    analysis, total_traces = scan_all_trace_header_locations(filepath, sample_size)
    
    detected = {
        'inline_source': None,
        'crossline_source': None,
        'x_source': None,
        'y_source': None,
        'coord_scalar': None,
        'is_standard': True,
        'issues': []
    }
    
    # Get scalar
    scalar_info = analysis.get('Coord Scalar (71-72)', {})
    detected['coord_scalar'] = scalar_info.get('sample_values', [1])[0] if scalar_info.get('sample_values') else 1
    
    # Check standard inline location (bytes 189-192)
    il_standard = analysis.get('Inline 3D (189-192) STANDARD', {})
    il_nonstandard = analysis.get('Non-std IL 2-byte (191-192)', {})
    
    if il_standard.get('has_data') and il_standard.get('unique_count', 0) > 1:
        detected['inline_source'] = 'Inline 3D (189-192) STANDARD'
    elif il_nonstandard.get('has_data') and il_nonstandard.get('unique_count', 0) > 1:
        detected['inline_source'] = 'Non-std IL 2-byte (191-192)'
        detected['is_standard'] = False
        detected['issues'].append('Inline stored at non-standard 2-byte location (191-192)')
    else:
        # Check if Field Record could be inline
        fr = analysis.get('Field Record (9-12)', {})
        if fr.get('has_data') and fr.get('unique_count', 0) > 1:
            detected['inline_source'] = 'Field Record (9-12)'
            detected['is_standard'] = False
            detected['issues'].append('Inline may be in Field Record (9-12)')
    
    # Check standard crossline location (bytes 193-196)
    xl_standard = analysis.get('Crossline 3D (193-196) STANDARD', {})
    xl_nonstandard = analysis.get('Non-std XL 2-byte (187-188)', {})
    
    if xl_standard.get('has_data') and xl_standard.get('unique_count', 0) > 1:
        detected['crossline_source'] = 'Crossline 3D (193-196) STANDARD'
    elif xl_nonstandard.get('has_data') and xl_nonstandard.get('unique_count', 0) > 1:
        detected['crossline_source'] = 'Non-std XL 2-byte (187-188)'
        detected['is_standard'] = False
        detected['issues'].append('Crossline stored at non-standard 2-byte location (187-188)')
    else:
        # Check if CDP Number could be crossline
        cdp = analysis.get('CDP Number (21-24)', {})
        if cdp.get('has_data') and cdp.get('unique_count', 0) > 1:
            detected['crossline_source'] = 'CDP Number (21-24)'
            detected['is_standard'] = False
            detected['issues'].append('Crossline may be in CDP Number (21-24)')
    
    # Check X coordinate source
    x_candidates = [
        ('CDP X (181-184) STANDARD', True),
        ('Non-std CDP X (201-204)', False),
        ('Source X (73-76)', False),
        ('Group X (81-84)', False),
    ]
    
    for name, is_std in x_candidates:
        info = analysis.get(name, {})
        if info.get('has_data') and info.get('unique_count', 0) > 1:
            detected['x_source'] = name
            if not is_std:
                detected['is_standard'] = False
                detected['issues'].append(f'X coordinate stored at non-standard location: {name}')
            break
    
    # Check Y coordinate source
    y_candidates = [
        ('CDP Y (185-188) STANDARD', True),
        ('Non-std CDP Y (205-208)', False),
        ('Source Y (77-80)', False),
        ('Group Y (85-88)', False),
    ]
    
    for name, is_std in y_candidates:
        info = analysis.get(name, {})
        if info.get('has_data') and info.get('unique_count', 0) > 1:
            detected['y_source'] = name
            if not is_std:
                detected['is_standard'] = False
                detected['issues'].append(f'Y coordinate stored at non-standard location: {name}')
            break
    
    # Add overall issues
    if not detected['inline_source']:
        detected['issues'].append('No valid inline data found')
    if not detected['crossline_source']:
        detected['issues'].append('No valid crossline data found')
    if not detected['x_source']:
        detected['issues'].append('No valid X coordinate data found')
    if not detected['y_source']:
        detected['issues'].append('No valid Y coordinate data found')
    
    return detected, analysis


def analyze_coordinates(filepath, sample_size=1000):
    """Analyze coordinate distribution across traces (standard locations only)."""
    file_size = os.path.getsize(filepath)
    
    with open(filepath, 'rb') as f:
        f.seek(3200 + 20)
        samples = struct.unpack('>H', f.read(2))[0]
        trace_size = 240 + samples * 4
        total_traces = (file_size - 3600) // trace_size
        
        # Sample traces evenly
        step = max(1, total_traces // sample_size)
        
        coords = {
            'cdp_x': [], 'cdp_y': [],
            'src_x': [], 'src_y': [],
            'grp_x': [], 'grp_y': [],
            'inline': [], 'crossline': [],
            'scalars': []
        }
        
        for i in range(0, total_traces, step):
            pos = 3600 + i * trace_size
            f.seek(pos)
            header = f.read(240)
            
            if len(header) != 240:
                break
            
            scalar = struct.unpack('>h', header[70:72])[0]
            coords['scalars'].append(scalar)
            
            # Apply scalar
            def apply_scalar(val, s):
                if s < 0:
                    return val / abs(s)
                elif s > 0:
                    return val * s
                return float(val)
            
            coords['cdp_x'].append(apply_scalar(struct.unpack('>l', header[180:184])[0], scalar))
            coords['cdp_y'].append(apply_scalar(struct.unpack('>l', header[184:188])[0], scalar))
            coords['src_x'].append(apply_scalar(struct.unpack('>l', header[72:76])[0], scalar))
            coords['src_y'].append(apply_scalar(struct.unpack('>l', header[76:80])[0], scalar))
            coords['grp_x'].append(apply_scalar(struct.unpack('>l', header[80:84])[0], scalar))
            coords['grp_y'].append(apply_scalar(struct.unpack('>l', header[84:88])[0], scalar))
            coords['inline'].append(struct.unpack('>l', header[188:192])[0])
            coords['crossline'].append(struct.unpack('>l', header[192:196])[0])
    
    # Analyze each coordinate type
    analysis = {}
    for name, values in coords.items():
        if values:
            unique = set(values)
            analysis[name] = {
                'min': min(values),
                'max': max(values),
                'unique_count': len(unique),
                'all_zero': all(v == 0 for v in values),
                'all_same': len(unique) == 1,
                'sample_values': values[:5]
            }
    
    return analysis, total_traces


def test_segyio_compatibility(filepath):
    """Test if segyio can read the file."""
    results = {
        'can_import': False,
        'can_open': False,
        'strict_mode': False,
        'ilines': None,
        'xlines': None,
        'samples': None,
        'error': None
    }
    
    try:
        import segyio
        results['can_import'] = True
        
        # Try strict mode first
        try:
            with segyio.open(filepath, 'r', strict=True) as f:
                results['strict_mode'] = True
                results['can_open'] = True
                results['ilines'] = list(f.ilines) if f.ilines is not None else None
                results['xlines'] = list(f.xlines) if f.xlines is not None else None
                results['samples'] = len(f.samples) if f.samples is not None else None
        except Exception as e:
            results['strict_error'] = str(e)
        
        # Try non-strict mode
        if not results['strict_mode']:
            try:
                with segyio.open(filepath, 'r', strict=False) as f:
                    results['can_open'] = True
                    results['ilines'] = list(f.ilines) if f.ilines is not None else None
                    results['xlines'] = list(f.xlines) if f.xlines is not None else None
                    results['samples'] = len(f.samples) if f.samples is not None else None
            except Exception as e:
                results['error'] = str(e)
    
    except ImportError:
        results['error'] = "segyio not installed"
    
    return results


def generate_summary(filepath):
    """Generate a complete summary report."""
    report = []
    report.append("=" * 80)
    report.append(f"SEG-Y FILE ANALYSIS: {os.path.basename(filepath)}")
    report.append("=" * 80)
    report.append(f"File size: {os.path.getsize(filepath):,} bytes")
    report.append("")
    
    # Binary header
    bin_header, _ = read_binary_header(filepath)
    report.append("-" * 40)
    report.append("BINARY HEADER")
    report.append("-" * 40)
    for key, value in bin_header.items():
        report.append(f"  {key}: {value}")
    report.append("")
    
    # Trace info
    traces, total, trace_size, samples = read_trace_headers(filepath, 5)
    report.append("-" * 40)
    report.append("TRACE INFORMATION")
    report.append("-" * 40)
    report.append(f"  Total traces: {total:,}")
    report.append(f"  Trace size: {trace_size} bytes")
    report.append(f"  Samples per trace: {samples}")
    report.append("")
    
    # Coordinate analysis (standard locations)
    coord_analysis, _ = analyze_coordinates(filepath, 1000)
    report.append("-" * 40)
    report.append("COORDINATE ANALYSIS (Standard Locations)")
    report.append("-" * 40)
    
    for coord_type in ['cdp_x', 'cdp_y', 'src_x', 'src_y', 'inline', 'crossline']:
        if coord_type in coord_analysis:
            info = coord_analysis[coord_type]
            status = "✓" if not info['all_zero'] and info['unique_count'] > 1 else "✗"
            report.append(f"  {coord_type.upper():12} {status} unique:{info['unique_count']:6}  "
                         f"range: {info['min']:.1f} to {info['max']:.1f}")
    report.append("")
    
    # Non-standard location detection
    detected, all_locations = detect_coordinate_source(filepath, 1000)
    report.append("-" * 40)
    report.append("DETECTED COORDINATE SOURCES")
    report.append("-" * 40)
    report.append(f"  Inline source: {detected['inline_source'] or 'NOT FOUND'}")
    report.append(f"  Crossline source: {detected['crossline_source'] or 'NOT FOUND'}")
    report.append(f"  X coordinate source: {detected['x_source'] or 'NOT FOUND'}")
    report.append(f"  Y coordinate source: {detected['y_source'] or 'NOT FOUND'}")
    report.append(f"  Coordinate scalar: {detected['coord_scalar']}")
    report.append(f"  Is standard format: {detected['is_standard']}")
    if detected['issues']:
        report.append("  Issues detected:")
        for issue in detected['issues']:
            report.append(f"    • {issue}")
    report.append("")
    
    # segyio compatibility
    segyio_results = test_segyio_compatibility(filepath)
    report.append("-" * 40)
    report.append("SEGYIO COMPATIBILITY")
    report.append("-" * 40)
    report.append(f"  Can import segyio: {segyio_results['can_import']}")
    report.append(f"  Opens in strict mode: {segyio_results['strict_mode']}")
    report.append(f"  Opens in non-strict mode: {segyio_results['can_open']}")
    if segyio_results['ilines']:
        report.append(f"  Inlines detected: {len(segyio_results['ilines'])} "
                     f"({min(segyio_results['ilines'])} to {max(segyio_results['ilines'])})")
    else:
        report.append(f"  Inlines detected: NONE")
    if segyio_results['xlines']:
        report.append(f"  Crosslines detected: {len(segyio_results['xlines'])} "
                     f"({min(segyio_results['xlines'])} to {max(segyio_results['xlines'])})")
    else:
        report.append(f"  Crosslines detected: NONE")
    if segyio_results.get('strict_error'):
        report.append(f"  Strict mode error: {segyio_results['strict_error']}")
    if segyio_results.get('error'):
        report.append(f"  Error: {segyio_results['error']}")
    report.append("")
    
    # Standardization assessment
    report.append("-" * 40)
    report.append("STANDARDIZATION ASSESSMENT")
    report.append("-" * 40)
    
    issues = []
    if bin_header.get('Data Format Code') == 1:
        issues.append("• Data format is IBM Float - needs conversion to IEEE")
    if not segyio_results['strict_mode']:
        issues.append("• File doesn't pass segyio strict mode")
    if not segyio_results['ilines']:
        issues.append("• Inline numbers not properly detected by segyio")
    if not segyio_results['xlines']:
        issues.append("• Crossline numbers not properly detected by segyio")
    
    cdp_x_info = coord_analysis.get('cdp_x', {})
    cdp_y_info = coord_analysis.get('cdp_y', {})
    if cdp_x_info.get('all_zero') or cdp_y_info.get('all_zero'):
        issues.append("• CDP coordinates are missing or all zeros (standard location)")
    
    inline_info = coord_analysis.get('inline', {})
    xline_info = coord_analysis.get('crossline', {})
    if inline_info.get('all_zero') or inline_info.get('all_same'):
        issues.append("• Inline 3D values are missing or constant (standard location)")
    if xline_info.get('all_zero') or xline_info.get('all_same'):
        issues.append("• Crossline 3D values are missing or constant (standard location)")
    
    if not detected['is_standard']:
        issues.append("• File uses non-standard byte locations for coordinates")
    
    if issues:
        report.append("  Issues found:")
        for issue in issues:
            report.append(f"    {issue}")
        report.append("")
        report.append("  This file likely needs standardization for PZero.")
    else:
        report.append("  ✓ File appears to be standard and should work with PZero.")
    
    report.append("")
    report.append("=" * 80)
    
    return '\n'.join(report)


def generate_byte_location_report(filepath):
    """Generate detailed report of all scanned byte locations."""
    analysis, total_traces = scan_all_trace_header_locations(filepath, 2000)
    
    report = []
    report.append("=" * 80)
    report.append("DETAILED BYTE LOCATION SCAN")
    report.append(f"Sampled from {total_traces:,} traces")
    report.append("=" * 80)
    report.append("")
    
    # Group by data presence
    with_data = []
    without_data = []
    
    for name, info in sorted(analysis.items()):
        if info.get('has_data', False):
            with_data.append((name, info))
        else:
            without_data.append((name, info))
    
    report.append("-" * 40)
    report.append("LOCATIONS WITH VALID DATA:")
    report.append("-" * 40)
    for name, info in with_data:
        report.append(f"\n{name}:")
        report.append(f"  Unique values: {info['unique_count']}")
        report.append(f"  Range: {info['min']} to {info['max']}")
        report.append(f"  Sample: {info['sample_values'][:5]}")
    
    report.append("")
    report.append("-" * 40)
    report.append("LOCATIONS WITHOUT DATA (zero/constant):")
    report.append("-" * 40)
    for name, info in without_data:
        val = info['sample_values'][0] if info['sample_values'] else 0
        report.append(f"  {name}: {val} (constant)")
    
    return '\n'.join(report)


# ============================================================================
# GUI Application
# ============================================================================

if HAS_GUI:
    class SEGYAnalyzerWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("SEG-Y File Analyzer - PZero Diagnostic Tool")
            self.setMinimumSize(1100, 800)
            self.filepath = None
            self.setup_ui()
        
        def setup_ui(self):
            central = QWidget()
            self.setCentralWidget(central)
            layout = QVBoxLayout(central)
            
            # File selection
            file_layout = QHBoxLayout()
            self.file_label = QLabel("No file selected")
            self.file_label.setStyleSheet("padding: 5px; background: #2a2a2a; border-radius: 3px;")
            btn_open = QPushButton("Open SEG-Y File")
            btn_open.clicked.connect(self.open_file)
            btn_analyze = QPushButton("Analyze")
            btn_analyze.clicked.connect(self.analyze)
            file_layout.addWidget(self.file_label, 1)
            file_layout.addWidget(btn_open)
            file_layout.addWidget(btn_analyze)
            layout.addLayout(file_layout)
            
            # Tab widget for different views
            self.tabs = QTabWidget()
            layout.addWidget(self.tabs)
            
            # Summary tab
            self.summary_text = QTextEdit()
            self.summary_text.setReadOnly(True)
            self.summary_text.setFont(QFont("Consolas", 10))
            self.tabs.addTab(self.summary_text, "Summary")
            
            # Binary header tab
            self.binary_table = QTableWidget()
            self.binary_table.setColumnCount(2)
            self.binary_table.setHorizontalHeaderLabels(["Field", "Value"])
            self.binary_table.horizontalHeader().setStretchLastSection(True)
            self.tabs.addTab(self.binary_table, "Binary Header")
            
            # Trace headers tab
            self.trace_table = QTableWidget()
            self.tabs.addTab(self.trace_table, "Trace Headers")
            
            # Coordinates tab
            self.coord_text = QTextEdit()
            self.coord_text.setReadOnly(True)
            self.coord_text.setFont(QFont("Consolas", 10))
            self.tabs.addTab(self.coord_text, "Coordinates")
            
            # NEW: Byte Location Scan tab
            self.byte_scan_text = QTextEdit()
            self.byte_scan_text.setReadOnly(True)
            self.byte_scan_text.setFont(QFont("Consolas", 10))
            self.tabs.addTab(self.byte_scan_text, "Byte Location Scan")
            
            # Textual header tab
            self.textual_text = QTextEdit()
            self.textual_text.setReadOnly(True)
            self.textual_text.setFont(QFont("Consolas", 9))
            self.tabs.addTab(self.textual_text, "Textual Header")
            
            # segyio compatibility tab
            self.segyio_text = QTextEdit()
            self.segyio_text.setReadOnly(True)
            self.segyio_text.setFont(QFont("Consolas", 10))
            self.tabs.addTab(self.segyio_text, "segyio Test")
            
            # Status bar
            self.statusBar().showMessage("Ready - Open a SEG-Y file to analyze")
        
        def open_file(self):
            filepath, _ = QFileDialog.getOpenFileName(
                self, "Open SEG-Y File", "",
                "SEG-Y Files (*.sgy *.segy *.SGY *.SEGY);;All Files (*)"
            )
            if filepath:
                self.filepath = filepath
                self.file_label.setText(filepath)
                self.statusBar().showMessage(f"Loaded: {os.path.basename(filepath)}")
                self.analyze()
        
        def analyze(self):
            if not self.filepath:
                self.statusBar().showMessage("Please open a file first")
                return
            
            self.statusBar().showMessage("Analyzing...")
            QApplication.processEvents()
            
            try:
                # Summary
                summary = generate_summary(self.filepath)
                self.summary_text.setPlainText(summary)
                
                # Binary header
                bin_header, _ = read_binary_header(self.filepath)
                self.binary_table.setRowCount(len(bin_header))
                for i, (key, value) in enumerate(bin_header.items()):
                    self.binary_table.setItem(i, 0, QTableWidgetItem(key))
                    item = QTableWidgetItem(str(value))
                    # Highlight important values
                    if key == 'Data Format Code' and value == 1:
                        item.setBackground(QColor(180, 100, 100))
                    elif key == 'Data Format Code' and value == 5:
                        item.setBackground(QColor(100, 180, 100))
                    elif key == 'Samples per Trace' and value == 0:
                        item.setBackground(QColor(180, 100, 100))
                    self.binary_table.setItem(i, 1, item)
                self.binary_table.resizeColumnsToContents()
                
                # Trace headers
                traces, total, trace_size, samples = read_trace_headers(self.filepath, 20)
                if traces:
                    cols = list(traces[0].keys())
                    self.trace_table.setColumnCount(len(cols))
                    self.trace_table.setHorizontalHeaderLabels(cols)
                    self.trace_table.setRowCount(len(traces))
                    for i, trace in enumerate(traces):
                        for j, col in enumerate(cols):
                            item = QTableWidgetItem(str(trace[col]))
                            # Highlight non-zero inline/crossline
                            if 'Inline' in col and trace[col] != 0:
                                item.setBackground(QColor(100, 180, 100))
                            elif 'Crossline' in col and trace[col] != 0:
                                item.setBackground(QColor(100, 180, 100))
                            self.trace_table.setItem(i, j, item)
                    self.trace_table.resizeColumnsToContents()
                
                # Coordinates
                coord_analysis, total_traces = analyze_coordinates(self.filepath)
                coord_report = [f"Coordinate Analysis (sampled from {total_traces:,} traces)\n"]
                coord_report.append("-" * 60)
                for coord_type, info in coord_analysis.items():
                    coord_report.append(f"\n{coord_type.upper()}:")
                    coord_report.append(f"  Unique values: {info['unique_count']}")
                    coord_report.append(f"  Range: {info['min']:.2f} to {info['max']:.2f}")
                    coord_report.append(f"  All zero: {info['all_zero']}")
                    coord_report.append(f"  All same: {info['all_same']}")
                    coord_report.append(f"  First 5: {info['sample_values']}")
                self.coord_text.setPlainText('\n'.join(coord_report))
                
                # Byte location scan (NEW)
                byte_report = generate_byte_location_report(self.filepath)
                self.byte_scan_text.setPlainText(byte_report)
                
                # Textual header
                text, encoding = read_textual_header(self.filepath)
                self.textual_text.setPlainText(f"Encoding: {encoding}\n\n{text}")
                
                # segyio test
                segyio_results = test_segyio_compatibility(self.filepath)
                segyio_report = ["segyio Compatibility Test\n", "-" * 40]
                for key, value in segyio_results.items():
                    if key in ['ilines', 'xlines'] and value:
                        segyio_report.append(f"{key}: {len(value)} values ({min(value)} to {max(value)})")
                    else:
                        segyio_report.append(f"{key}: {value}")
                self.segyio_text.setPlainText('\n'.join(segyio_report))
                
                self.statusBar().showMessage("Analysis complete")
                
            except Exception as e:
                import traceback
                self.statusBar().showMessage(f"Error: {str(e)}")
                self.summary_text.setPlainText(f"Error analyzing file:\n\n{str(e)}\n\n{traceback.format_exc()}")


def run_gui(filepath=None):
    """Run the GUI application."""
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    # Dark theme
    palette = app.palette()
    palette.setColor(palette.ColorRole.Window, QColor(53, 53, 53))
    palette.setColor(palette.ColorRole.WindowText, QColor(255, 255, 255))
    palette.setColor(palette.ColorRole.Base, QColor(35, 35, 35))
    palette.setColor(palette.ColorRole.AlternateBase, QColor(53, 53, 53))
    palette.setColor(palette.ColorRole.ToolTipBase, QColor(255, 255, 255))
    palette.setColor(palette.ColorRole.ToolTipText, QColor(255, 255, 255))
    palette.setColor(palette.ColorRole.Text, QColor(255, 255, 255))
    palette.setColor(palette.ColorRole.Button, QColor(53, 53, 53))
    palette.setColor(palette.ColorRole.ButtonText, QColor(255, 255, 255))
    palette.setColor(palette.ColorRole.BrightText, QColor(255, 0, 0))
    palette.setColor(palette.ColorRole.Link, QColor(42, 130, 218))
    palette.setColor(palette.ColorRole.Highlight, QColor(42, 130, 218))
    palette.setColor(palette.ColorRole.HighlightedText, QColor(0, 0, 0))
    app.setPalette(palette)
    
    window = SEGYAnalyzerWindow()
    window.show()
    
    if filepath and os.path.exists(filepath):
        window.filepath = filepath
        window.file_label.setText(filepath)
        window.analyze()
    
    sys.exit(app.exec())


def run_console(filepath):
    """Run in console mode without GUI."""
    if not filepath or not os.path.exists(filepath):
        print("Usage: python segy_analyzer.py <segy_file>")
        return
    
    print(generate_summary(filepath))
    print("\n")
    print(generate_byte_location_report(filepath))


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    filepath = sys.argv[1] if len(sys.argv) > 1 else None
    
    if HAS_GUI:
        run_gui(filepath)
    else:
        run_console(filepath)
