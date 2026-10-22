# Imports

This folder contains modules for importing, exporting, and converting various data formats (such as well data, mesh data, images, triangulated surfaces, GIS shapefiles, seismic SEG-Y volumes, PyVista-supported formats, PLY surfaces, point clouds, OBJ surfaces, LandXML surfaces, glTF/GLB models, GOCAD ASCII files, DXF files, DEM rasters, Cesium 3D Tiles, and abstract base classes) into VTK objects and internal representations for the PZero project.

## File Overview

### Project coordinate systems

Use **File > CRS > Assign project CRS** to declare a projected EPSG system in
metres. This assigns metadata; existing coordinates stay unchanged. The status
bar shows the current CRS. Projects save it in the `.p0` file and in each revision's
`pzero_crs.json`; older projects open with an unspecified CRS.

SHP, DEM and map-image imports can reproject into the project CRS after confirmation.
GOCAD, XYZ, PyVista, LAS/point-cloud and well imports check for a matching CRS and
stop on a mismatch. Files without metadata ask for a source CRS; an unspecified
local system is allowed only when the project also has no declared CRS. Elevation
and depth must already be in metres. Horizontal reprojection preserves Z; seismic
time retains its separate domain and units. SEG-Y uses the project's CRS as its
output CRS through the existing seismic import dialog.

CAD, VTK and CSV exports include `pzero_crs.json` and an EPSG-named text file.
Cesium also receives the actual CRS through its native writer. Keep these sidecars
with exported geometry. Imports recognize per-file `.crs.json` and `.prj` files,
then the export folder's `pzero_crs.json`. Whole-project reprojection is not included.

## Format handlers

- `well2vtk.py`  
  Converts well data from Excel and other formats into VTK objects and PZero entities.  
  **Main function:**  
  - `well2vtk(self, path=None)`

- `mesh2vtk.py`  
  Imports mesh data (e.g., from GOCAD or other sources) and converts them into VTK mesh objects.

- `image2vtk.py`  
  Imports image data and converts them into VTK image objects.

- `stl2vtk.py`  
  Exports triangulated surfaces (TSurfs) to STL files, with optional boundary dilation.  
  **Main functions:**  
  - `vtk2stl(self, out_dir_name)`  
  - `vtk2stl_dilation(self, out_dir_name, tol=1.0)`

- `shp2vtk.py`  
  Imports points and polylines from ESRI Shapefiles (SHP) and other GIS formats.  
  **Main function:**  
  - `shp2vtk(self, in_file_name, collection)`

- `segy2vtk.py`  
  Imports seismic SEG-Y volumes and converts them into VTK structured grids.  
  **Main functions:**  
  - `segy2vtk(self, in_file_name)`  
  - `read_segy_file(in_file_name)`

- `pyvista2vtk.py`  
  Imports various file formats supported by PyVista and adds them as VTK polydata entities.  
  **Main function:**  
  - `pyvista2vtk(self)`

- `ply2vtk.py`  
  Exports all triangulated surfaces (TSurfs) to PLY files with color information.  
  **Main function:**  
  - `vtk2ply(self, out_dir_name)`

- `pc2vtk.py`  
  Imports point cloud data from PLY, LAS/LAZ, or CSV files and converts them into VTK point cloud objects.  
  **Main function:**  
  - `pc2vtk(in_file_name, col_names, row_range, header_row, usecols, delimiter, self=None)`

- `obj2vtk.py`  
  Exports all triangulated surfaces (TSurfs) to OBJ files.  
  **Main function:**  
  - `vtk2obj(self, out_dir_name)`

- `lxml2vtk.py`  
  Exports triangulated surfaces (TSurfs) to LandXML files and provides a placeholder for LandXML import.  
  **Main functions:**  
  - `vtk2lxml(self, out_dir_name=None)`  
  - `lxml2vtk(self, input_path=None)`

- `gltf2vtk.py`  
  Exports all triangulated surfaces (TSurfs) to a GLTF binary file (.glb) using VTK’s GLTF writer.  
  **Main function:**  
  - `vtk2gltf(self, out_dir_name=None)`

- `gocad2vtk.py`  
  Imports and exports GOCAD ASCII files (VSet, PLine, TSurf) as VTK entities for geology, cross-sections, and boundaries.  
  **Main functions:**  
  - `gocad2vtk(self, in_file_name, uid_from_name=None)`  
  - `gocad2vtk_section(self, in_file_name, ...)`  
  - `gocad2vtk_boundary(self, in_file_name, uid_from_name=None)`  
  - `vtk2gocad(self, out_file_name)`

- `dxf2vtk.py`  
  Exports all triangulated surfaces, boundaries, and wells to DXF files as 3DFACE objects and 3D polylines, including CSV exports of coordinates.  
  **Main function:**  
  - `vtk2dxf(self, out_dir_name=None)`

- `dem2vtk.py`  
  Imports Digital Elevation Model (DEM) raster files (e.g., GeoTIFF) and adds them as VTK structured grids to the project.  
  **Main function:**  
  - `dem2vtk(self, in_file_name, collection)`

- `cesium2vtk.py`  
  Exports all triangulated surfaces to a Cesium 3D Tiles collection (GLTF binary surfaces, .glb) using VTK’s Cesium3DTilesWriter.  
  **Main function:**  
  - `vtk2cesium(self, out_dir_name=None)`

- `AbstractImporter.py`  
  In theory should provide abstract base classes for import/export operations, ensuring a consistent interface for all importers and exporters, but this is not yet implemented.  
  **Main class:**  
  - `BaseIO`: Abstract base class with `import_from_file()` and `output_to_file()` methods to be implemented by subclasses.
