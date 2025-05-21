# CHANGELOG


## v0.1.18 (2025-05-21)

### Bug Fixes

- **Actions**: Try fixing Upload executable and macos #5
  ([`1805b77`](https://github.com/gecos-lab/PZero/commit/1805b77d1605ca614d6c086ec5726a7c26e548b5))


## v0.1.17 (2025-05-21)

### Bug Fixes

- **Actions**: Try fixing Upload executable and macos #4
  ([`38de032`](https://github.com/gecos-lab/PZero/commit/38de032dbfef62ff62772409d003c11c51c0031c))


## v0.1.16 (2025-05-21)

### Bug Fixes

- **Actions**: Try fixing Upload executable and macos #3
  ([`c31ca74`](https://github.com/gecos-lab/PZero/commit/c31ca749b5fef847080595f65215912754f7a369))


## v0.1.15 (2025-05-21)

### Bug Fixes

- **Actions**: Try fixing Upload executable and macos #2
  ([`575567e`](https://github.com/gecos-lab/PZero/commit/575567ec5bb669feeac57c2f0187dc75e043e07d))


## v0.1.14 (2025-05-21)

### Bug Fixes

- **Actions**: Try fixing Upload executable and macos
  ([`06676aa`](https://github.com/gecos-lab/PZero/commit/06676aa1387167a0f53c33bf9fb76ad1cfe0eee0))


## v0.1.13 (2025-05-21)

### Bug Fixes

- **Actions**: Try fixing Upload executable
  ([`eb8f0cf`](https://github.com/gecos-lab/PZero/commit/eb8f0cf6a313d22671fb17420e245975ecf39077))


## v0.1.12 (2025-05-21)

### Bug Fixes

- **Actions**: Use --windowed and not --target-arch universal2
  ([`a645a28`](https://github.com/gecos-lab/PZero/commit/a645a288301dc76e8169c7e84efaf51ba4290c48))


## v0.1.11 (2025-05-21)

### Bug Fixes

- **Actions**: Fix zip file upload
  ([`18e0ae8`](https://github.com/gecos-lab/PZero/commit/18e0ae88bdabeb9e4676b1ec507ae57f7a9bc6e7))


## v0.1.10 (2025-05-21)


## v0.1.9 (2025-05-21)

### Bug Fixes

- **Actions**: --onedir, zip files
  ([`b9f1ddc`](https://github.com/gecos-lab/PZero/commit/b9f1ddcb99cdbd873a977d992542e252c24d2d61))

- **Actions**: Fix zip file
  ([`fce1c14`](https://github.com/gecos-lab/PZero/commit/fce1c14ba2592372c55eb9987df3af7f1b3664ad))


## v0.1.8 (2025-05-15)

### Bug Fixes

- **Actions**: One file dist folder path
  ([`b875c7a`](https://github.com/gecos-lab/PZero/commit/b875c7af29a6feca91ee5a31cd6593c6c68ba298))


## v0.1.7 (2025-05-15)

### Bug Fixes

- **Actions**: One file option
  ([`8693278`](https://github.com/gecos-lab/PZero/commit/8693278331c84e0913164ea9fe72ecdf6e89c9eb))


## v0.1.6 (2025-05-15)

### Bug Fixes

- **Actions**: Change pzero name using os
  ([`2d57d72`](https://github.com/gecos-lab/PZero/commit/2d57d72be32eab30d880ae3524e082a805bd2232))


## v0.1.5 (2025-05-15)

### Bug Fixes

- **Actions**: Upload only pzero files
  ([`6fef293`](https://github.com/gecos-lab/PZero/commit/6fef293d0fb85702f140f3618057e6c547f7bd55))


## v0.1.4 (2025-05-15)

### Bug Fixes

- **Actions**: Add token auth
  ([`51a4ba7`](https://github.com/gecos-lab/PZero/commit/51a4ba710cd93306bab346890cbaa8b8b9062a83))


## v0.1.3 (2025-05-15)

### Bug Fixes

- **Actions**: Try to upload executable
  ([`cbfd176`](https://github.com/gecos-lab/PZero/commit/cbfd17684457dba7a55c926213f4b7f310cf270e))


## v0.1.2 (2025-05-15)


## v0.1.1 (2025-05-15)

### Bug Fixes

- **Actions**: Add deploy job
  ([`7b32e4f`](https://github.com/gecos-lab/PZero/commit/7b32e4fc88374df227532f3856465444d7f58ed6))

- **Actions**: Fix python version to 3.12
  ([`1d4b2cf`](https://github.com/gecos-lab/PZero/commit/1d4b2cf22de5fdfb851e99b9cb59de604dbe180d))


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
