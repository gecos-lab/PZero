"""segy_standardizer.py by Waqas Hussain
PZero© Andrea Bistacchi

Utility functions for standardizing SEG-Y files for PZero compatibility.

This module handles both standard and non-standard SEG-Y files by:
1. Using coordinate values (X/Y) to determine the actual grid structure
2. Converting IBM Float to IEEE Float
3. Writing proper inline/crossline and CDP coordinates to standard locations
4. Ensuring segyio compatibility for PZero import
"""

import os
import struct


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


def ibm_to_ieee(ibm_bytes):
    """
    Convert IBM 370 floating point to IEEE 754 floating point.
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
    This is necessary because sampling can miss unique values.
    
    Returns dict with coordinate source detection and grid info.
    """
    print_fn("Scanning all traces for coordinate analysis...")
    
    file_size = os.path.getsize(input_file)
    
    # Track all unique values for each coordinate type
    src_x_values = set()
    src_y_values = set()
    cdp_x_values = set()
    cdp_y_values = set()
    inline_values = set()
    xline_values = set()
    field_record_values = set()
    cdp_number_values = set()
    
    # Also track coordinate pairs for grid detection
    trace_coords = []  # List of (trace_idx, x_key, y_key)
    
    with open(input_file, "rb") as f:
        for i in range(total_traces):
            pos = 3600 + i * trace_size
            if pos >= file_size:
                break
            
            f.seek(pos)
            header = f.read(240)
            
            if len(header) != 240:
                break
            
            # Read all coordinate fields
            scalar = struct.unpack('>h', header[70:72])[0]
            
            def apply_scalar(val, s):
                if s < 0:
                    return val / abs(s)
                elif s > 0:
                    return val * s
                return float(val)
            
            # Source X/Y
            src_x = struct.unpack('>l', header[72:76])[0]
            src_y = struct.unpack('>l', header[76:80])[0]
            src_x_scaled = apply_scalar(src_x, scalar)
            src_y_scaled = apply_scalar(src_y, scalar)
            src_x_values.add(src_x)
            src_y_values.add(src_y)
            
            # CDP X/Y (standard)
            cdp_x = struct.unpack('>l', header[180:184])[0]
            cdp_y = struct.unpack('>l', header[184:188])[0]
            cdp_x_values.add(cdp_x)
            cdp_y_values.add(cdp_y)
            
            # Inline/Crossline (standard)
            inline = struct.unpack('>l', header[188:192])[0]
            xline = struct.unpack('>l', header[192:196])[0]
            inline_values.add(inline)
            xline_values.add(xline)
            
            # Field Record and CDP Number (potential inline/crossline)
            field_rec = struct.unpack('>l', header[8:12])[0]
            cdp_num = struct.unpack('>l', header[20:24])[0]
            field_record_values.add(field_rec)
            cdp_number_values.add(cdp_num)
            
            # Store trace info - use the best available coordinates
            # Priority: Source X/Y (if valid) > CDP X/Y > Inline/Crossline
            if src_x != 0 or src_y != 0:
                trace_coords.append((i, src_x, src_y, pos))
            elif cdp_x != 0 or cdp_y != 0:
                trace_coords.append((i, cdp_x, cdp_y, pos))
            else:
                # Use field record / cdp number as pseudo-coordinates
                trace_coords.append((i, cdp_num, field_rec, pos))
            
            if (i + 1) % 50000 == 0:
                print_fn(f"  Scanned {i + 1}/{total_traces} traces...")
    
    print_fn(f"  Scan complete: {len(trace_coords)} traces")
    
    # Analyze what we found
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
    
    # Determine best coordinate source for grid detection
    # Priority: Source X/Y > CDP X/Y > Field Record/CDP Number
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
        # Fallback to field record / cdp number
        results['x_source'] = 'cdp_number'
        results['y_source'] = 'field_record'
        results['n_x'] = results['cdp_number']['count']
        results['n_y'] = results['field_record']['count']
        print_fn(f"  Using Field Record/CDP Number: {results['n_x']} x {results['n_y']}")
    
    return results


def estimate_grid_dimensions(total_traces, hint_x=None, hint_y=None):
    """
    Estimate grid dimensions for a given number of traces.
    """
    import math
    
    if hint_x is not None and hint_y is not None and hint_x > 1 and hint_y > 1:
        # If hints exactly match, use them
        if hint_x * hint_y == total_traces:
            return hint_x, hint_y
        
        # Search for close matches
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
    
    # Single hint
    if hint_x is not None and hint_x > 1 and total_traces % hint_x == 0:
        return hint_x, total_traces // hint_x
    if hint_y is not None and hint_y > 1 and total_traces % hint_y == 0:
        return total_traces // hint_y, hint_y
    
    # Fallback: find factors close to square root
    sqrt_traces = int(math.sqrt(total_traces))
    
    for n in range(sqrt_traces, 0, -1):
        if total_traces % n == 0:
            m = total_traces // n
            return n, m
    
    return 1, total_traces


def build_coordinate_grid(trace_coords, n_inlines, n_xlines, total_traces, print_fn=print):
    """
    Build a mapping from grid position (inline, crossline) to trace file position.
    
    This sorts traces by their X/Y coordinates to determine their grid position.
    """
    print_fn("Building coordinate grid mapping...")
    
    if not trace_coords:
        print_fn("  No coordinate data - using sequential order")
        return {i: 3600 + i * 6244 for i in range(total_traces)}  # Fallback
    
    # Get unique X and Y values
    x_values = sorted(set(t[1] for t in trace_coords))
    y_values = sorted(set(t[2] for t in trace_coords))
    
    print_fn(f"  X values: {len(x_values)} unique (range {min(x_values)} to {max(x_values)})")
    print_fn(f"  Y values: {len(y_values)} unique (range {min(y_values)} to {max(y_values)})")
    
    # Create lookup from coordinate to grid index
    x_to_idx = {x: i for i, x in enumerate(x_values)}
    y_to_idx = {y: i for i, y in enumerate(y_values)}
    
    # Map each trace to its grid position
    # Grid position = inline_idx * n_xlines + xline_idx
    # We treat X as crossline (varies faster) and Y as inline
    grid_map = {}  # grid_position -> trace_file_position
    
    for trace_idx, x, y, file_pos in trace_coords:
        if x in x_to_idx and y in y_to_idx:
            xline_idx = x_to_idx[x]  # X varies within each inline
            inline_idx = y_to_idx[y]  # Y is the inline
            grid_pos = inline_idx * n_xlines + xline_idx
            grid_map[grid_pos] = file_pos
    
    print_fn(f"  Mapped {len(grid_map)} traces to grid positions")
    
    # Check coverage
    expected = n_inlines * n_xlines
    if len(grid_map) < expected:
        print_fn(f"  Warning: Only {len(grid_map)}/{expected} grid positions have traces")
    
    return grid_map


def standardize_segy_for_pzero(input_file, output_file, print_fn=print):
    """Standardize SEGY file specifically for PZero compatibility.
    
    This function:
    1. Scans ALL traces to get accurate coordinate counts
    2. Uses coordinates to determine actual grid structure
    3. Reorders traces into proper crossline-major order
    4. Converts IBM Float to IEEE Float
    5. Writes standard inline/crossline/CDP locations
    """
    # Get parameters
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

    # Scan all traces for coordinate analysis
    coord_info = scan_all_traces_for_coordinates(input_file, trace_size, total_traces, print_fn)
    print_fn("")
    
    # Determine grid dimensions
    hint_x = coord_info.get('n_x', 1)
    hint_y = coord_info.get('n_y', 1)
    
    # Check if coordinate-based grid matches trace count
    if hint_x * hint_y == total_traces:
        n_xlines = hint_x  # X direction = crosslines
        n_inlines = hint_y  # Y direction = inlines
        print_fn(f"Grid from coordinates: {n_inlines} inlines x {n_xlines} crosslines = {n_inlines * n_xlines}")
    else:
        # Grid doesn't match - find closest factors
        print_fn(f"Coordinate grid {hint_x}x{hint_y}={hint_x*hint_y} doesn't match {total_traces} traces")
        n_xlines, n_inlines = estimate_grid_dimensions(total_traces, hint_x, hint_y)
        print_fn(f"Adjusted grid: {n_inlines} inlines x {n_xlines} crosslines = {n_inlines * n_xlines}")
    
    # Build coordinate-to-grid mapping
    grid_map = build_coordinate_grid(
        coord_info['trace_coords'], 
        n_inlines, 
        n_xlines, 
        total_traces, 
        print_fn
    )
    print_fn("")
    
    # Calculate traces to process
    grid_traces = n_inlines * n_xlines
    traces_to_process = min(grid_traces, total_traces)
    
    print_fn(f"Output: {n_inlines} inlines x {n_xlines} crosslines = {traces_to_process} traces")
    print_fn("")

    with open(input_file, "rb") as infile, open(output_file, "wb") as outfile:
        # Read and update headers
        textual_header = infile.read(3200)
        binary_header = bytearray(infile.read(400))

        # Update binary header
        binary_header[12:14] = struct.pack(">H", min(n_xlines, 32767))
        binary_header[14:16] = struct.pack(">H", 0)
        binary_header[16:18] = struct.pack(">H", sample_interval)
        binary_header[20:22] = struct.pack(">H", num_samples)
        binary_header[24:26] = struct.pack(">H", 5)  # IEEE float
        binary_header[26:28] = struct.pack(">H", 1)
        binary_header[28:30] = struct.pack(">H", 4)  # Horizontally stacked
        binary_header[300:302] = struct.pack(">H", 2)  # Rev 2
        binary_header[302:304] = struct.pack(">H", 1)
        binary_header[304:306] = struct.pack(">H", 0)

        outfile.write(textual_header)
        outfile.write(binary_header)

        # Coordinate spacing for synthetic CDP coordinates
        spacing = 1000
        
        # Process traces in grid order (crossline-major)
        trace_count = 0
        data_size = num_samples * 4
        
        for inline_idx in range(n_inlines):
            for xline_idx in range(n_xlines):
                grid_pos = inline_idx * n_xlines + xline_idx
                
                # Get source trace position
                if grid_pos in grid_map:
                    source_pos = grid_map[grid_pos]
                else:
                    # Fallback: use sequential trace
                    source_pos = 3600 + trace_count * trace_size
                
                if source_pos >= file_size:
                    continue
                
                # Read source trace
                infile.seek(source_pos)
                trace_header = bytearray(infile.read(240))
                
                if len(trace_header) != 240:
                    continue

                # Calculate output inline/crossline numbers (1-based)
                inline_num = inline_idx + 1
                xline_num = xline_idx + 1

                # Write to standard locations
                trace_header[188:192] = struct.pack(">l", inline_num)  # Inline
                trace_header[192:196] = struct.pack(">l", xline_num)   # Crossline

                # Generate CDP coordinates
                cdp_x = xline_num * spacing
                cdp_y = inline_num * spacing
                trace_header[180:184] = struct.pack(">l", int(cdp_x))
                trace_header[184:188] = struct.pack(">l", int(cdp_y))
                
                # Coordinate scalar = 1
                trace_header[70:72] = struct.pack(">h", 1)
                
                # Sample info
                trace_header[114:116] = struct.pack(">H", num_samples)
                trace_header[116:118] = struct.pack(">H", sample_interval)
                
                # Trace sequence
                trace_header[0:4] = struct.pack(">l", xline_num)
                trace_header[4:8] = struct.pack(">l", trace_count + 1)

                outfile.write(trace_header)

                # Read and convert trace data
                data = infile.read(data_size)
                if len(data) < data_size:
                    data = data.ljust(data_size, b"\x00")
                elif len(data) > data_size:
                    data = data[:data_size]

                # Convert samples
                for i in range(0, len(data), 4):
                    sample_bytes = data[i:i + 4].ljust(4, b"\x00")
                    try:
                        if format_code == 1:  # IBM Float
                            sample = ibm_to_ieee(sample_bytes)
                        elif format_code == 5:  # IEEE Float
                            sample = struct.unpack(">f", sample_bytes)[0]
                        else:
                            sample = 0.0
                    except:
                        sample = 0.0
                    outfile.write(struct.pack(">f", sample))

                trace_count += 1

            # Progress update per inline
            if (inline_idx + 1) % 50 == 0:
                print_fn(f"Processed inline {inline_idx + 1}/{n_inlines} ({trace_count} traces)")

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
    """
    Verify that the converted SEG-Y file can be read by segyio.
    """
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
            except Exception as e:
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
            
            # Sample trace headers
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
