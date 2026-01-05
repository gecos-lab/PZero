"""segy_standardizer.py by Waqas Hussain
PZero© Andrea Bistacchi

Utility functions for standardizing SEG-Y files for PZero compatibility.

This module handles both standard and non-standard SEG-Y files by:
1. Using coordinate values (X/Y) to determine the actual grid structure
2. Converting IBM Float to IEEE Float (vectorized for speed)
3. Writing proper inline/crossline and CDP coordinates to standard locations
4. Ensuring segyio compatibility for PZero import
"""

import os
import struct
import numpy as np


def read_binary_header(file):
    """Read basic binary header values"""
    file.seek(3200)
    binary_header = file.read(400)

    sample_interval = struct.unpack(">H", binary_header[16:18])[0]
    num_samples = struct.unpack(">H", binary_header[20:22])[0]
    data_format = struct.unpack(">H", binary_header[24:26])[0]

    return sample_interval, num_samples, data_format


def analyze_segy_parameters(input_file):
    """Extract standard parameters from SEGY file analysis"""
    with open(input_file, "rb") as file:
        file.seek(3200)
        binary_header = file.read(400)

        sample_interval = struct.unpack(">H", binary_header[16:18])[0]
        num_samples = struct.unpack(">H", binary_header[20:22])[0]
        format_code = struct.unpack(">H", binary_header[24:26])[0]

        trace_header_size = 240
        sample_size = 4
        trace_data_size = num_samples * sample_size
        trace_size = trace_header_size + trace_data_size

        return {
            "num_samples": num_samples,
            "sample_interval": sample_interval,
            "format_code": format_code,
            "trace_size": trace_size,
            "trace_header_size": trace_header_size,
            "sample_size": sample_size,
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


def scan_all_traces_for_coordinates(input_file, trace_size, total_traces, print_fn=print):
    """
    Scan ALL traces to get accurate unique coordinate counts.
    Optimized with buffered reading.
    """
    print_fn("Scanning all traces for coordinate analysis...")
    
    file_size = os.path.getsize(input_file)
    
    # Track all unique values
    src_x_values = set()
    src_y_values = set()
    cdp_x_values = set()
    cdp_y_values = set()
    inline_values = set()
    xline_values = set()
    field_record_values = set()
    cdp_number_values = set()
    
    # Store trace coordinates
    trace_coords = []
    
    # Read in larger chunks for speed
    CHUNK_SIZE = 10000  # Read 10000 trace headers at a time
    header_size = 240
    
    with open(input_file, "rb") as f:
        for chunk_start in range(0, total_traces, CHUNK_SIZE):
            chunk_end = min(chunk_start + CHUNK_SIZE, total_traces)
            chunk_count = chunk_end - chunk_start
            
            # Read all headers in this chunk
            headers_data = bytearray()
            for i in range(chunk_start, chunk_end):
                pos = 3600 + i * trace_size
                if pos >= file_size:
                    break
                f.seek(pos)
                headers_data.extend(f.read(header_size))
            
            # Parse headers
            for local_idx in range(chunk_count):
                global_idx = chunk_start + local_idx
                offset = local_idx * header_size
                
                if offset + header_size > len(headers_data):
                    break
                
                header = headers_data[offset:offset + header_size]
                
                # Read coordinates
                scalar = struct.unpack('>h', header[70:72])[0]
                
                src_x = struct.unpack('>l', header[72:76])[0]
                src_y = struct.unpack('>l', header[76:80])[0]
                src_x_values.add(src_x)
                src_y_values.add(src_y)
                
                cdp_x = struct.unpack('>l', header[180:184])[0]
                cdp_y = struct.unpack('>l', header[184:188])[0]
                cdp_x_values.add(cdp_x)
                cdp_y_values.add(cdp_y)
                
                inline = struct.unpack('>l', header[188:192])[0]
                xline = struct.unpack('>l', header[192:196])[0]
                inline_values.add(inline)
                xline_values.add(xline)
                
                field_rec = struct.unpack('>l', header[8:12])[0]
                cdp_num = struct.unpack('>l', header[20:24])[0]
                field_record_values.add(field_rec)
                cdp_number_values.add(cdp_num)
                
                # Store trace info
                file_pos = 3600 + global_idx * trace_size
                if src_x != 0 or src_y != 0:
                    trace_coords.append((global_idx, src_x, src_y, file_pos))
                elif cdp_x != 0 or cdp_y != 0:
                    trace_coords.append((global_idx, cdp_x, cdp_y, file_pos))
                else:
                    trace_coords.append((global_idx, cdp_num, field_rec, file_pos))
            
            if chunk_end % 100000 == 0 or chunk_end == total_traces:
                print_fn(f"  Scanned {chunk_end}/{total_traces} traces...")
    
    print_fn(f"  Scan complete: {len(trace_coords)} traces")
    
    # Build results
    results = {
        'src_x': {'count': len(src_x_values), 'all_zero': src_x_values == {0}},
        'src_y': {'count': len(src_y_values), 'all_zero': src_y_values == {0}},
        'cdp_x': {'count': len(cdp_x_values), 'all_zero': cdp_x_values == {0}},
        'cdp_y': {'count': len(cdp_y_values), 'all_zero': cdp_y_values == {0}},
        'inline': {'count': len(inline_values), 'all_zero': inline_values == {0}},
        'xline': {'count': len(xline_values), 'all_zero': xline_values == {0}},
        'field_record': {'count': len(field_record_values), 'all_zero': field_record_values == {0}},
        'cdp_number': {'count': len(cdp_number_values), 'all_zero': cdp_number_values == {0}},
        'trace_coords': trace_coords,
    }
    
    # Determine best coordinate source
    if not results['src_x']['all_zero'] and not results['src_y']['all_zero']:
        results['x_source'] = 'src_x'
        results['y_source'] = 'src_y'
        results['n_x'] = results['src_x']['count']
        results['n_y'] = results['src_y']['count']
        print_fn(f"  Using Source X/Y: {results['n_x']} x {results['n_y']}")
    elif not results['cdp_x']['all_zero'] and not results['cdp_y']['all_zero']:
        results['x_source'] = 'cdp_x'
        results['y_source'] = 'cdp_y'
        results['n_x'] = results['cdp_x']['count']
        results['n_y'] = results['cdp_y']['count']
        print_fn(f"  Using CDP X/Y: {results['n_x']} x {results['n_y']}")
    elif not results['inline']['all_zero'] and not results['xline']['all_zero']:
        results['x_source'] = 'inline'
        results['y_source'] = 'xline'
        results['n_x'] = results['inline']['count']
        results['n_y'] = results['xline']['count']
        print_fn(f"  Using Inline/Crossline: {results['n_x']} x {results['n_y']}")
    else:
        results['x_source'] = 'cdp_number'
        results['y_source'] = 'field_record'
        results['n_x'] = results['cdp_number']['count']
        results['n_y'] = results['field_record']['count']
        print_fn(f"  Using Field Record/CDP Number: {results['n_x']} x {results['n_y']}")
    
    return results


def estimate_grid_dimensions(total_traces, hint_x=None, hint_y=None):
    """Estimate grid dimensions for a given number of traces."""
    import math
    
    if hint_x is not None and hint_y is not None and hint_x > 1 and hint_y > 1:
        if hint_x * hint_y == total_traces:
            return hint_x, hint_y
        
        best_match = None
        best_distance = float('inf')
        
        search_range_x = max(20, hint_x // 5)
        search_range_y = max(20, hint_y // 5)
        
        for dx in range(-search_range_x, search_range_x + 1):
            test_x = hint_x + dx
            if test_x <= 0:
                continue
            if total_traces % test_x == 0:
                test_y = total_traces // test_x
                distance = abs(test_x - hint_x) + abs(test_y - hint_y)
                if distance < best_distance:
                    best_distance = distance
                    best_match = (test_x, test_y)
        
        if best_match is not None:
            return best_match
    
    if hint_x is not None and hint_x > 1 and total_traces % hint_x == 0:
        return hint_x, total_traces // hint_x
    if hint_y is not None and hint_y > 1 and total_traces % hint_y == 0:
        return total_traces // hint_y, hint_y
    
    sqrt_traces = int(math.sqrt(total_traces))
    
    for n in range(sqrt_traces, 0, -1):
        if total_traces % n == 0:
            m = total_traces // n
            return n, m
    
    return 1, total_traces


def build_coordinate_grid(trace_coords, n_inlines, n_xlines, total_traces, print_fn=print):
    """Build a mapping from grid position to trace file position."""
    print_fn("Building coordinate grid mapping...")
    
    if not trace_coords:
        print_fn("  No coordinate data - using sequential order")
        return None  # Signal to use sequential
    
    # Get unique X and Y values
    x_values = sorted(set(t[1] for t in trace_coords))
    y_values = sorted(set(t[2] for t in trace_coords))
    
    print_fn(f"  X values: {len(x_values)} unique")
    print_fn(f"  Y values: {len(y_values)} unique")
    
    # Create lookup
    x_to_idx = {x: i for i, x in enumerate(x_values)}
    y_to_idx = {y: i for i, y in enumerate(y_values)}
    
    # Build grid map
    grid_map = {}
    for trace_idx, x, y, file_pos in trace_coords:
        if x in x_to_idx and y in y_to_idx:
            xline_idx = x_to_idx[x]
            inline_idx = y_to_idx[y]
            grid_pos = inline_idx * n_xlines + xline_idx
            grid_map[grid_pos] = file_pos
    
    print_fn(f"  Mapped {len(grid_map)} traces to grid positions")
    
    return grid_map


def standardize_segy_for_pzero(input_file, output_file, print_fn=print):
    """Standardize SEGY file for PZero compatibility.
    
    Optimized version with:
    - Chunked header reading
    - Vectorized IBM to IEEE conversion
    - Batch trace processing
    """
    params = analyze_segy_parameters(input_file)
    num_samples = params["num_samples"]
    trace_size = params["trace_size"]
    sample_interval = params["sample_interval"]
    format_code = params["format_code"]

    print_fn(f"Input file parameters:")
    print_fn(f"  Samples per trace: {num_samples}")
    print_fn(f"  Trace size: {trace_size} bytes")
    print_fn(f"  Sample interval: {sample_interval} μs")
    print_fn(f"  Format code: {format_code} ({'IBM Float' if format_code == 1 else 'IEEE Float' if format_code == 5 else 'Other'})")

    file_size = os.path.getsize(input_file)
    total_traces = (file_size - 3600) // trace_size
    print_fn(f"  Total traces: {total_traces}")
    print_fn("")

    # Scan traces
    coord_info = scan_all_traces_for_coordinates(input_file, trace_size, total_traces, print_fn)
    print_fn("")
    
    # Grid dimensions
    hint_x = coord_info.get('n_x', 1)
    hint_y = coord_info.get('n_y', 1)
    
    if hint_x * hint_y == total_traces:
        n_xlines = hint_x
        n_inlines = hint_y
        print_fn(f"Grid from coordinates: {n_inlines} inlines x {n_xlines} crosslines")
    else:
        print_fn(f"Coordinate grid {hint_x}x{hint_y}={hint_x*hint_y} doesn't match {total_traces} traces")
        n_xlines, n_inlines = estimate_grid_dimensions(total_traces, hint_x, hint_y)
        print_fn(f"Adjusted grid: {n_inlines} inlines x {n_xlines} crosslines")
    
    # Build grid mapping
    grid_map = build_coordinate_grid(
        coord_info['trace_coords'], 
        n_inlines, 
        n_xlines, 
        total_traces, 
        print_fn
    )
    print_fn("")
    
    traces_to_process = min(n_inlines * n_xlines, total_traces)
    print_fn(f"Output: {n_inlines} inlines x {n_xlines} crosslines = {traces_to_process} traces")
    print_fn(f"Using vectorized conversion for speed...")
    print_fn("")

    # Pre-compute output trace header template
    header_template = bytearray(240)
    header_template[114:116] = struct.pack(">H", num_samples)
    header_template[116:118] = struct.pack(">H", sample_interval)
    header_template[70:72] = struct.pack(">h", 1)  # Scalar = 1
    
    spacing = 1000
    data_size = num_samples * 4
    
    # Batch size for processing
    BATCH_SIZE = 1000  # Process 1000 traces at a time
    
    with open(input_file, "rb") as infile, open(output_file, "wb") as outfile:
        # Write headers
        textual_header = infile.read(3200)
        binary_header = bytearray(infile.read(400))

        binary_header[12:14] = struct.pack(">H", min(n_xlines, 32767))
        binary_header[14:16] = struct.pack(">H", 0)
        binary_header[16:18] = struct.pack(">H", sample_interval)
        binary_header[20:22] = struct.pack(">H", num_samples)
        binary_header[24:26] = struct.pack(">H", 5)
        binary_header[26:28] = struct.pack(">H", 1)
        binary_header[28:30] = struct.pack(">H", 4)
        binary_header[300:302] = struct.pack(">H", 2)
        binary_header[302:304] = struct.pack(">H", 1)
        binary_header[304:306] = struct.pack(">H", 0)

        outfile.write(textual_header)
        outfile.write(binary_header)

        trace_count = 0
        last_progress = 0
        
        # Process traces in batches
        for batch_start in range(0, traces_to_process, BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, traces_to_process)
            
            # Collect source positions for this batch
            batch_data = []
            for grid_pos in range(batch_start, batch_end):
                inline_idx = grid_pos // n_xlines
                xline_idx = grid_pos % n_xlines
                
                if grid_map and grid_pos in grid_map:
                    source_pos = grid_map[grid_pos]
                else:
                    source_pos = 3600 + grid_pos * trace_size
                
                batch_data.append((inline_idx, xline_idx, source_pos))
            
            # Read and process batch
            for inline_idx, xline_idx, source_pos in batch_data:
                if source_pos >= file_size:
                    continue
                
                infile.seek(source_pos)
                raw_trace = infile.read(240 + data_size)
                
                if len(raw_trace) < 240:
                    continue
                
                # Build output trace header
                trace_header = bytearray(header_template)
                
                inline_num = inline_idx + 1
                xline_num = xline_idx + 1
                
                trace_header[188:192] = struct.pack(">l", inline_num)
                trace_header[192:196] = struct.pack(">l", xline_num)
                trace_header[180:184] = struct.pack(">l", xline_num * spacing)
                trace_header[184:188] = struct.pack(">l", inline_num * spacing)
                trace_header[0:4] = struct.pack(">l", xline_num)
                trace_header[4:8] = struct.pack(">l", trace_count + 1)
                
                outfile.write(trace_header)
                
                # Convert trace data
                trace_data = raw_trace[240:240 + data_size]
                if len(trace_data) < data_size:
                    trace_data = trace_data.ljust(data_size, b'\x00')
                
                if format_code == 1:  # IBM Float - vectorized conversion
                    # Convert bytes to uint32 array
                    ibm_ints = np.frombuffer(trace_data, dtype='>u4')
                    ieee_floats = ibm_to_ieee_vectorized(ibm_ints)
                    outfile.write(ieee_floats.astype('>f4').tobytes())
                elif format_code == 5:  # Already IEEE
                    outfile.write(trace_data)
                else:
                    # Other formats - zero fill
                    outfile.write(b'\x00' * data_size)
                
                trace_count += 1
            
            # Progress update
            progress = (batch_end * 100) // traces_to_process
            if progress >= last_progress + 5:  # Update every 5%
                print_fn(f"Progress: {progress}% ({trace_count}/{traces_to_process} traces)")
                last_progress = progress

        print_fn(f"\n{'='*60}")
        print_fn(f"Standardization completed!")
        print_fn(f"{'='*60}")
        print_fn(f"  Traces written: {trace_count}")
        print_fn(f"  Grid: {n_inlines} inlines x {n_xlines} crosslines")
        print_fn(f"  Samples per trace: {num_samples}")
        print_fn(f"  Sample interval: {sample_interval} μs")
        print_fn(f"  Data format: IEEE Float (code 5)")
        return True


def verify_segy_structure(output_file, print_fn=print):
    """Verify that the converted SEG-Y file can be read by segyio."""
    try:
        import segyio
        
        with segyio.open(output_file, "r", strict=False) as f:
            n_traces = f.tracecount
            samples = f.samples
            
            print_fn(f"\nVerification - file opened successfully:")
            print_fn(f"  Traces: {n_traces}")
            print_fn(f"  Samples: {len(samples) if samples is not None else 'N/A'}")
            
            try:
                ilines = f.ilines
                xlines = f.xlines
            except:
                ilines = None
                xlines = None
            
            if ilines is not None and hasattr(ilines, '__len__') and len(ilines) > 0:
                print_fn(f"  Inlines: {len(ilines)} ({min(ilines)} to {max(ilines)})")
            else:
                print_fn(f"  Inlines: NOT DETECTED")
                
            if xlines is not None and hasattr(xlines, '__len__') and len(xlines) > 0:
                print_fn(f"  Crosslines: {len(xlines)} ({min(xlines)} to {max(xlines)})")
            else:
                print_fn(f"  Crosslines: NOT DETECTED")
            
            print_fn("  Sample traces:")
            for i in [0, 1, min(10, n_traces-1)]:
                if i < n_traces:
                    il = f.attributes(segyio.TraceField.INLINE_3D)[i]
                    xl = f.attributes(segyio.TraceField.CROSSLINE_3D)[i]
                    cdpx = f.attributes(segyio.TraceField.CDP_X)[i]
                    cdpy = f.attributes(segyio.TraceField.CDP_Y)[i]
                    print_fn(f"    Trace {i}: IL={il}, XL={xl}, CDP_X={cdpx}, CDP_Y={cdpy}")
            
            if ilines is None or not hasattr(ilines, '__len__') or len(ilines) == 0:
                raise ValueError("segyio could not detect inline structure")
            if xlines is None or not hasattr(xlines, '__len__') or len(xlines) == 0:
                raise ValueError("segyio could not detect crossline structure")
            
            print_fn("\n✓ Verification passed!")
            return True
            
    except ImportError:
        print_fn("Warning: segyio not available for verification")
        return True
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"segyio verification failed: {str(e)}")


def convert_to_standard_segy(input_file, output_file, print_fn=print):
    """Main conversion function with verification"""
    try:
        success = standardize_segy_for_pzero(input_file, output_file, print_fn=print_fn)
        
        if success:
            print_fn("\nVerifying converted file...")
            verify_segy_structure(output_file, print_fn=print_fn)
            
        return success
    except Exception as e:
        raise Exception(f"Error during conversion: {str(e)}")
