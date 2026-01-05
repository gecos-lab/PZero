# Processing

This folder contains modules for data processing and standardization tasks within the PZero project, including SEG-Y seismic data standardization and coordinate reference system (CRS) utilities.

## File Overview

### `segy_analyzer.py` - SEG-Y Diagnostic Tool

**Standalone GUI tool** for analyzing SEG-Y files and understanding their structure. Helps identify why files may be non-standard and what needs to be fixed for PZero compatibility.

**Run it:**
```bash
python pzero/processing/segy_analyzer.py [optional_segy_file]
```

**Key Features:**
- Reads and displays textual header (EBCDIC/ASCII)
- Parses binary header fields with problematic values highlighted
- Shows trace headers for first N traces
- **Auto-detects non-standard byte locations** for coordinates/inline/crossline
- Analyzes coordinate distribution (CDP, Source, Group, Inline/Crossline)
- Tests segyio compatibility (strict and non-strict modes)
- Generates standardization assessment with specific issues

**GUI Tabs:**
- **Summary**: Complete analysis report with standardization assessment
- **Binary Header**: All binary header fields (red = problematic, green = correct)
- **Trace Headers**: First 20 trace headers in table form
- **Coordinates**: Statistical analysis of standard coordinate locations
- **Byte Location Scan**: Scans ALL potential byte locations to find where data is stored
- **Textual Header**: 3200-byte EBCDIC/ASCII header
- **segyio Test**: Compatibility test results

**Detected Non-Standard Patterns:**

| File Pattern | Inline Location | Crossline Location | Coordinate Location |
|--------------|-----------------|--------------------|--------------------|
| Standard | 189-192 (4-byte) | 193-196 (4-byte) | CDP X/Y at 181-188 |
| Poseidon-style | 191-192 (2-byte) | 187-188 (2-byte) | 201-204, 205-208 |
| Stratton-style | None (Field Record) | None (CDP Number) | Source X/Y at 73-80 |

### `segy_standardizer.py` - SEG-Y Conversion Tool

Utility functions for standardizing non-standard SEG-Y files to ensure PZero/segyio compatibility. **Now auto-detects non-standard byte locations!**

**Main functions:**

- `convert_to_standard_segy(input_file, output_file, print_fn)`: Main entry point with verification
- `standardize_segy_for_pzero(input_file, output_file, print_fn)`: Core conversion logic
- `verify_segy_structure(output_file, print_fn)`: Verifies segyio can read the output

**Key helper functions:**

- `detect_byte_locations(...)`: **Auto-detects where coordinates are stored**
- `build_trace_index(...)`: Builds index for trace reordering
- `ibm_to_ieee(ibm_bytes)`: Converts IBM 370 float to IEEE 754 float
- `estimate_grid_dimensions(total_traces, hint_x, hint_y)`: Calculates optimal grid from trace count

**Conversion Process:**

1. **Analyze input file** - Extract samples, format code, trace count
2. **Detect byte locations** - Scan for inline/crossline/coordinates at standard AND non-standard locations
3. **Build trace index** - Map all traces with their inline/crossline values
4. **Validate grid** - Check if detected grid matches trace count
5. **Fallback to synthetic** - Generate regular grid if detection fails
6. **Convert data** - IBM float → IEEE float
7. **Write standard format** - Output with proper inline/crossline at standard byte locations
8. **Verify output** - Ensure segyio can read the result

**Supported Input Formats:**

| Pattern | What's Detected | What's Generated |
|---------|-----------------|------------------|
| Standard SEG-Y | IL/XL/CDP at standard locations | Preserved (format converted) |
| Missing IL/XL | Coordinates from Source/Group/CDP | Synthetic IL/XL + preserved coords |
| Non-standard bytes | IL/XL at 2-byte or alternate locations | Standard 4-byte IL/XL |
| No coordinates | Nothing usable | Synthetic grid + synthetic coords |

### `CRS.py` - Coordinate Reference System Tools

Utilities for handling coordinate reference systems (CRS) and spatial transformations, based on PROJ.

**Main functions:**

- `CRS_list(self)`: Prints all valid CRS definitions
- `CRS_transform_selected(self)`: Transforms CRS of selected entities
- `CRS_transform_uid_accurate(self, uid, collection, from_CRS, to_CRS)`: Accurate point-by-point transformation
- `CRS_fit_transformation(uid, collection, from_CRS, to_CRS)`: Calculates transformation matrix from bounds
- `CRS_apply_transformation(uid, collection, transformation_matrix)`: Applies VTK linear transformation

## SEG-Y Standard Reference

### Standard Byte Locations (SEG-Y Rev 1/2)

**Binary Header (bytes 3201-3600):**
- 17-18: Sample interval (μs)
- 21-22: Samples per trace
- 25-26: Data format code (1=IBM, 5=IEEE)
- 29-30: Trace sorting code

**Trace Header (bytes 1-240 of each trace):**
- 1-4: Trace sequence in line
- 5-8: Trace sequence in file
- 9-12: Field record number
- 21-24: CDP number
- 71-72: Coordinate scalar
- 73-76: Source X
- 77-80: Source Y
- 81-84: Group X
- 85-88: Group Y
- 115-116: Number of samples
- 117-118: Sample interval
- 181-184: **CDP X** (standard for 3D)
- 185-188: **CDP Y** (standard for 3D)
- 189-192: **Inline 3D** (standard)
- 193-196: **Crossline 3D** (standard)

### What Makes a "Standard" SEG-Y File

1. **Data format code = 5** (IEEE float), not 1 (IBM float)
2. **Valid inline/crossline** at bytes 189-196 with multiple unique values
3. **Valid CDP X/Y** at bytes 181-188 with UTM-scale coordinates
4. **Grid matches trace count**: n_inlines × n_crosslines = total_traces
5. **segyio strict mode passes**: Can be opened without errors
