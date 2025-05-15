# CHANGELOG


## v0.1.1 (2025-05-15)

### Bug Fixes

- **Actions**: Add deploy job
  ([`7b32e4f`](https://github.com/gecos-lab/PZero/commit/7b32e4fc88374df227532f3856465444d7f58ed6))


## v0.1.0 (2025-05-15)

### Bug Fixes

- **shp2vtk**: Handle 2D LineString geometries to prevent IndexError
  ([`1c7d98b`](https://github.com/gecos-lab/PZero/commit/1c7d98b8c9b883424b8edd76783ef8c5ba9f1040))

fix(shp2vtk): Handle 2D LineString geometries to prevent IndexError

**Issue:** An `IndexError: tuple index out of range` was raised when importing shapefiles containing
  2D `LineString` geometries. This error occurred because the code attempted to access the second
  dimension of the `outXYZ` array (`np_shape(outXYZ)[1]`) without ensuring that the array actually
  had two dimensions.

**Cause:** The `shp2vtk` function processed geometries by converting their coordinates into NumPy
  arrays. For 2D `LineString` geometries, the resulting `outXYZ` array had a shape of `(n, 2)`,
  where `n` is the number of points. When the code attempted to access `np_shape(outXYZ)[1]`, it
  expected a third dimension (Z-coordinate), which did not exist, leading to the `IndexError`.

**Solution:** Implemented a check to determine if a `LineString` geometry is 2D. If it is, a
  Z-coordinate with a value of zero is appended to each point, effectively converting the geometry
  to 3D. This ensures that `outXYZ` always has three dimensions, preventing the `IndexError`.

**Code Changes:** ```python if gdf.geom_type[row] == "LineString": outXYZ =
  np_array(list(gdf.loc[row].geometry.coords), dtype=float) if np_shape(outXYZ)[1] == 2: outZ =
  np_zeros((np_shape(outXYZ)[0], 1)) outXYZ = np_column_stack((outXYZ, outZ))
  curr_obj_dict["vtk_obj"].points = outXYZ curr_obj_dict["vtk_obj"].auto_cells()

For Fiona error, in the filepath, I upgraded geopandas to 0.14.4 and the problem was solved.

### Features

- **deployment**: Add requirements.in
  ([`015542d`](https://github.com/gecos-lab/PZero/commit/015542d217c68e91114d473358ec461e8cd56082))

- **workflows**: Adding new workflows
  ([`8de467d`](https://github.com/gecos-lab/PZero/commit/8de467d998f9c3f70815f8a1744543d2b1ca1408))

- **workflows**: Adding new workflows
  ([`d3237b3`](https://github.com/gecos-lab/PZero/commit/d3237b364432cf5dfb2776c9986cbbd5cbd1eb9a))
