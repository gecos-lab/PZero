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

def standardize_segy_for_pzero(input_file, output_file):
    """Standardize SEGY file specifically for PZero compatibility"""
    try:
        with open(input_file, 'rb') as infile:
            # Validate structure and get parameters
            num_samples, data_format, expected_traces, trace_size = validate_segy_structure(infile)
            
            # Calculate grid dimensions
            grid_size = int(np.sqrt(expected_traces))
            while grid_size * grid_size > expected_traces:
                grid_size -= 1
            actual_traces = grid_size * grid_size
            
            # Read headers
            infile.seek(0)
            textual_header = infile.read(3200)
            binary_header = bytearray(infile.read(400))
            
            # Create standardized file
            with open(output_file, 'wb') as outfile:
                # Update and write headers
                binary_header = update_to_rev2(binary_header, actual_traces, num_samples)
                outfile.write(textual_header)
                outfile.write(binary_header)
                
                # Process traces
                trace_count = 0
                for inline in range(grid_size):
                    for xline in range(grid_size):
                        if trace_count >= actual_traces:
                            break
                            
                        # Read trace header
                        trace_header = bytearray(infile.read(240))
                        
                        # Update trace header
                        trace_header[114:116] = struct.pack('>H', num_samples)
                        trace_header[116:118] = struct.pack('>H', 2000)
                        trace_header[188:190] = struct.pack('>H', inline + 1)
                        trace_header[192:194] = struct.pack('>H', xline + 1)
                        trace_header[180:184] = struct.pack('>l', inline * 100)
                        trace_header[184:188] = struct.pack('>l', xline * 100)
                        
                        outfile.write(trace_header)
                        
                        # Read and convert trace data
                        data = infile.read(num_samples * 4)
                        if len(data) < num_samples * 4:
                            data = data.ljust(num_samples * 4, b'\x00')
                        
                        # Convert samples to IEEE float
                        for i in range(0, len(data), 4):
                            sample_bytes = data[i:i+4].ljust(4, b'\x00')
                            try:
                                if data_format == 1:  # IBM Float
                                    sample = struct.unpack('>f', sample_bytes)[0]
                                elif data_format == 2:  # 32-bit Integer
                                    sample = float(struct.unpack('>l', sample_bytes)[0])
                                elif data_format == 3:  # 16-bit Integer
                                    sample = float(struct.unpack('>h', sample_bytes[:2])[0])
                                elif data_format == 5:  # IEEE Float
                                    sample = struct.unpack('>f', sample_bytes)[0]
                                elif data_format == 8:  # 8-bit Integer
                                    sample = float(struct.unpack('b', sample_bytes[:1])[0])
                                else:
                                    sample = 0.0
                            except struct.error:
                                sample = 0.0
                                
                            outfile.write(struct.pack('>f', sample))
                        
                        trace_count += 1
                        
                        if trace_count % 1000 == 0:
                            print(f"Processed {trace_count}/{actual_traces} traces")
                
                print(f"\nStandardization completed:")
                print(f"- Total traces: {trace_count}")
                print(f"- Grid size: {grid_size}x{grid_size}")
                print(f"- Samples per trace: {num_samples}")
                return True
                
    except Exception as e:
        print(f"Standardization error: {str(e)}")
        return False

def convert_to_standard_segy(input_file, output_file):
    """Main conversion function"""
    try:
        return standardize_segy_for_pzero(input_file, output_file)
    except Exception as e:
        raise Exception(f"Error during conversion: {str(e)}") 