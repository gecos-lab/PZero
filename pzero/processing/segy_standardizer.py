"""segy_standardizer.py
Utility functions for standardizing SEG-Y files for PZero compatibility"""

import os
import struct
import numpy as np

def read_binary_header(file):
    """Read basic binary header values"""
    file.seek(3200)
    binary_header = file.read(400)

    # Get key values from binary header
    sample_interval = struct.unpack('>H', binary_header[16:18])[0]
    num_samples = struct.unpack('>H', binary_header[20:22])[0]
    data_format = struct.unpack('>H', binary_header[24:26])[0]

    return sample_interval, num_samples, data_format

def analyze_segy_parameters(input_file):
    """Extract standard parameters from SEGY file analysis"""
    with open(input_file, 'rb') as file:
        # Read headers
        file.seek(3200)  # Skip textual header
        binary_header = file.read(400)
        
        # Get basic parameters from binary header
        sample_interval = struct.unpack('>H', binary_header[16:18])[0]
        num_samples = struct.unpack('>H', binary_header[20:22])[0]
        format_code = struct.unpack('>H', binary_header[24:26])[0]
        
        # Calculate trace size
        trace_header_size = 240  # Standard SEG-Y trace header size
        sample_size = 4  # We'll convert everything to 4-byte IEEE float
        trace_data_size = num_samples * sample_size
        trace_size = trace_header_size + trace_data_size
        
        return {
            'num_samples': num_samples,
            'sample_interval': sample_interval,
            'format_code': format_code,
            'trace_size': trace_size,
            'trace_header_size': trace_header_size,
            'sample_size': sample_size
        }

def validate_segy_structure(file):
    """Validate SEGY file structure and return key parameters"""
    file_size = os.path.getsize(file.name)
    if file_size < 3600:  # Basic size check
        raise ValueError("Invalid SEGY file: too small")

    # Read headers
    file.seek(0)
    textual_header = file.read(3200)
    binary_header = file.read(400)

    # Get format details
    sample_interval, num_samples, data_format = read_binary_header(file)
    if num_samples <= 0:
        raise ValueError("Invalid number of samples")

    # Calculate trace size
    trace_size = 240 + (num_samples * 4)  # header + data
    expected_traces = (file_size - 3600) // trace_size

    return num_samples, data_format, expected_traces, trace_size

def update_to_rev2(binary_header, trace_count, samples_per_trace):
    """Update binary header to SEG-Y Rev 2 standard"""
    header = bytearray(binary_header)
    
    # Set revision number to 2
    header[300:302] = struct.pack('>H', 2)
    
    # Update mandatory Rev 2 fields
    header[16:18] = struct.pack('>H', 2000)  # Sample interval (2ms)
    header[20:22] = struct.pack('>H', samples_per_trace)  # Samples per trace
    header[24:26] = struct.pack('>H', 5)  # IEEE float format
    
    # Set measurement system to meters
    header[24:25] = struct.pack('B', 1)
    
    # Set fixed length trace flag
    header[302:304] = struct.pack('>H', 1)
    
    # Set extended header count
    header[304:306] = struct.pack('>H', 0)
    
    return header

def standardize_segy_for_pzero(input_file, output_file, print_fn=print):
    """Standardize SEGY file specifically for PZero compatibility"""
    # Get parameters from analysis
    params = analyze_segy_parameters(input_file)
    num_samples = params['num_samples']
    trace_size = params['trace_size']
    sample_interval = params['sample_interval']
    format_code = params['format_code']
    
    print_fn(f"Using analyzed parameters:")
    print_fn(f"- Samples per trace: {num_samples}")
    print_fn(f"- Trace size: {trace_size} bytes")
    print_fn(f"- Sample interval: {sample_interval} μs")
    print_fn(f"- Format code: {format_code}")
    
    with open(input_file, 'rb') as infile, open(output_file, 'wb') as outfile:
        # Read headers
        textual_header = infile.read(3200)
        binary_header = bytearray(infile.read(400))
        
        # Calculate grid dimensions for inline/crossline
        file_size = os.path.getsize(input_file)
        total_traces = (file_size - 3600) // trace_size
        grid_size = int(np.sqrt(total_traces))
        
        # Update binary header for PZero compatibility
        binary_header[20:22] = struct.pack('>H', num_samples)  # Samples per trace
        binary_header[24:26] = struct.pack('>H', 5)  # IEEE float
        binary_header[16:18] = struct.pack('>H', sample_interval)  # Keep original sample interval
        binary_header[300:302] = struct.pack('>H', 2)  # SEG-Y Rev 2
        
        # Write headers
        outfile.write(textual_header)
        outfile.write(binary_header)
        
        # Process traces with PZero-specific headers
        pos = 3600
        trace_count = 0
        
        for inline in range(grid_size):
            for xline in range(grid_size):
                if pos >= file_size:
                    break
                    
                infile.seek(pos)
                trace_header = bytearray(infile.read(240))
                
                if len(trace_header) != 240:
                    break
                
                # Update trace header for PZero
                # Inline number (bytes 189-190)
                trace_header[188:190] = struct.pack('>H', inline + 1)
                
                # Crossline number (bytes 193-194)
                trace_header[192:194] = struct.pack('>H', xline + 1)
                
                # CDP X coordinate (bytes 181-184)
                trace_header[180:184] = struct.pack('>l', inline * 100)
                
                # CDP Y coordinate (bytes 185-188)
                trace_header[184:188] = struct.pack('>l', xline * 100)
                
                # Number of samples (bytes 115-116)
                trace_header[114:116] = struct.pack('>H', num_samples)
                
                # Sample interval (bytes 117-118)
                trace_header[116:118] = struct.pack('>H', sample_interval)
                
                outfile.write(trace_header)
                
                # Process trace data
                data_size = num_samples * 4
                data = infile.read(data_size)
                
                if len(data) < data_size:
                    data = data.ljust(data_size, b'\x00')
                elif len(data) > data_size:
                    data = data[:data_size]
                
                # Convert samples based on format code
                samples = []
                for i in range(0, len(data), 4):
                    sample_bytes = data[i:i+4].ljust(4, b'\x00')
                    try:
                        if format_code == 1:  # IBM Float
                            sample = struct.unpack('>f', sample_bytes)[0]
                        elif format_code == 2:  # 32-bit Integer
                            sample = float(struct.unpack('>l', sample_bytes)[0])
                        elif format_code == 3:  # 16-bit Integer
                            sample = float(struct.unpack('>h', sample_bytes[:2])[0])
                        elif format_code == 5:  # IEEE Float
                            sample = struct.unpack('>f', sample_bytes)[0]
                        elif format_code == 8:  # 8-bit Integer
                            sample = float(struct.unpack('b', sample_bytes[:1])[0])
                        else:
                            sample = 0.0
                    except struct.error:
                        sample = 0.0
                        
                    samples.append(sample)
                
                # Write converted samples
                for sample in samples:
                    outfile.write(struct.pack('>f', sample))
                
                trace_count += 1
                pos = infile.tell()
                
                if trace_count % 1000 == 0:
                    print_fn(f"Processed {trace_count}/{total_traces} traces")
        
        # Update final trace count
        print_fn(f"\nStandardization completed:")
        print_fn(f"- Total traces: {trace_count}")
        print_fn(f"- Grid size: {grid_size}x{grid_size}")
        print_fn(f"- Samples per trace: {num_samples}")
        print_fn(f"- Sample interval: {sample_interval} μs")
        return True

def convert_to_standard_segy(input_file, output_file, print_fn=print):
    """Main conversion function"""
    try:
        return standardize_segy_for_pzero(input_file, output_file, print_fn=print_fn)
    except Exception as e:
        raise Exception(f"Error during conversion: {str(e)}") 