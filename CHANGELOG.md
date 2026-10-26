# CHANGELOG


## v1.5.0 (2026-10-21)

### Chores

- Test workflow
  ([`71e3765`](https://github.com/gecos-lab/PZero/commit/71e37657ed871adf5015e80c258489c6e34bafce))

### Features

- **stereo & points**: Stereoplots & pointclouds completed
  ([`238998d`](https://github.com/gecos-lab/PZero/commit/238998d43411a58494d5e50acbd778cf122cb71a))

- **stereo-points**: Stereoplots and pointclouds completed
  ([`03429d5`](https://github.com/gecos-lab/PZero/commit/03429d56b2f0e952e8674e5a5c50ee5d9a2f94c4))

- **stereo-points**: Stereoplots and pointclouds completed, CICD fixed
  ([`c4b2bfd`](https://github.com/gecos-lab/PZero/commit/c4b2bfd037bc0749fcd1e3a7837cfbcb88b86cf5))

- **stereo-points**: Stereoplots and pointclouds completed, CICD fixed
  ([`dba028c`](https://github.com/gecos-lab/PZero/commit/dba028c619c93d615aa378374d7da966fbcd03dc))

- **stereo-points**: Stereoplots and pointclouds completed, CICD fixed
  ([`6d05794`](https://github.com/gecos-lab/PZero/commit/6d057941933c8194aa0163341fdf41bc028a65ca))


## v1.4.2 (2026-07-28)

### Bug Fixes

- **cicd**: Repair workflow
  ([`05f51aa`](https://github.com/gecos-lab/PZero/commit/05f51aab0cd8a7d73b7221f7f845ce4ffc8f155c))

### Documentation

- Update readme
  ([`13819ef`](https://github.com/gecos-lab/PZero/commit/13819ef62851ddcdca4e74157ac4ea5e5264f8d7))


## v1.4.1 (2026-07-27)

### Bug Fixes

- **ci/cd**: Empty commit to test CI/CD
  ([`4297c2f`](https://github.com/gecos-lab/PZero/commit/4297c2f960c6cb79269a3a76edf810fd5f2de162))

- **ci/cd**: Empty commit to test CI/CD
  ([`6b7dc55`](https://github.com/gecos-lab/PZero/commit/6b7dc55f3c0f4278a7c32244e119d1f394f4bbd4))

- **ci/cd**: Empty commit to test CI/CD
  ([`f1d4309`](https://github.com/gecos-lab/PZero/commit/f1d43099d864a692352b16566c59680fe8dd23a8))


## v1.4.0 (2026-07-27)


## v1.3.6 (2026-05-11)

### Bug Fixes

- **DEM NaN**: Dem import NaN's detection
  ([`f75033d`](https://github.com/gecos-lab/PZero/commit/f75033d6c544f477e6111638334f8dae7e1de467))


## v1.3.5 (2026-02-25)

### Bug Fixes

- **ci/cd**: Add tag-ignore to prevent duplicating release
  ([`3007840`](https://github.com/gecos-lab/PZero/commit/3007840d4384ddd4f16dcd65f119e129b94bbf93))

- **cicd**: Tags-ignore commented
  ([`c364606`](https://github.com/gecos-lab/PZero/commit/c364606def3b0fa042ceace4b02ee04a25e3a2cb))

- **crs**: Add test_epsg to project file
  ([`0c73400`](https://github.com/gecos-lab/PZero/commit/0c7340068c79699009c2694680c5fab053d22e5d))


## v1.3.4 (2026-02-25)

### Bug Fixes

- **draw_line**: Unfreeze GUI if aborted with cancel in dialog
  ([`89183dd`](https://github.com/gecos-lab/PZero/commit/89183ddb7bb9eedb222940a808f812152a56999c))


## v1.3.3 (2026-02-25)

### Bug Fixes

- **role**: Role combo box added
  ([`83a823e`](https://github.com/gecos-lab/PZero/commit/83a823ef35316ef80121e491ece95e80f5f44df9))


## v1.3.2 (2026-02-20)

### Bug Fixes

- **venv**: Update pyinstaller version to 6.15.0 and add setuptools<81.0.0
  ([`4263077`](https://github.com/gecos-lab/PZero/commit/4263077a5d115be5596b75373eadf7e2de388d11))


## v1.3.1 (2026-02-20)

### Bug Fixes

- **venv**: Update pyinstaller version to 6.15.0 and add setuptools
  ([`bdada12`](https://github.com/gecos-lab/PZero/commit/bdada1220adfc6938b76e5b25de5bae7e9c11267))


## v1.3.0 (2026-02-05)

### Bug Fixes

- **pointcloud**: Improve coordinate column detection in pc2vtk import
  ([`3897918`](https://github.com/gecos-lab/PZero/commit/38979187e7c813d029f62dc62b1494fac060c20d))

Enhanced the pc2vtk import process to automatically detect and normalize coordinate columns (X, Y,
  Z) using common aliases. Added user feedback for detected and missing coordinate columns,
  improving robustness and usability when importing point cloud data. Also refactored DIMCollection
  to update property legends only when necessary.

Co-Authored-By: Riccardo Monti <150252648+r-monti14@users.noreply.github.com>

- **RemoveEntity**: Remove actors when entities are deleted
  ([`8136b41`](https://github.com/gecos-lab/PZero/commit/8136b41947be82714dbaab248ece58bc38adadd3))

Adds logic to remove silhouette actors from the plotter's renderer when corresponding entities are
  removed. Also ensures removed UIDs are cleared from selected_uids. This improves view consistency
  after entity deletion.

- **RemoveEntity**: Remove actors when entities are deleted
  ([`a795c4d`](https://github.com/gecos-lab/PZero/commit/a795c4df5421580cd4490c4d69117c5f826ebd6e))

Adds logic to remove silhouette actors from the plotter's renderer when corresponding entities are
  removed. Also ensures removed UIDs are cleared from selected_uids. This improves view consistency
  after entity deletion.

- **viewtree**: Added mesh slicer to the right click on view tree
  ([`9c4163e`](https://github.com/gecos-lab/PZero/commit/9c4163e31aba5cb41bb72b088779c3ee9e5e7603))

Added a mesh-slicer entry to the tree view context menu that appears for mesh and image entities,
  ensuring the targeted item becomes the dialog selection. Exposed the mesh slicer’s entity combos
  and initializer so that external callers can programmatically select the correct entity when
  opening or reusing the dialog.

- **viewtree**: Added mesh slicer to the right click on view tree
  ([`b763f44`](https://github.com/gecos-lab/PZero/commit/b763f44aeaa877d00c36e10bb3ea91d86652e819))

Added a mesh-slicer entry to the tree view context menu that appears for mesh and image entities,
  ensuring the targeted item becomes the dialog selection. Exposed the mesh slicer’s entity combos
  and initializer so that external callers can programmatically select the correct entity when
  opening or reusing the dialog.

- **well2vtk**: Add borehole view mode selection for wells
  ([`e317512`](https://github.com/gecos-lab/PZero/commit/e31751235599a30b2aebf90af6820db3f05b3692))

Introduces a context menu in the tree view to select borehole visualization mode (trace or cylinder)
  for wells. Updates 3D view logic to refresh well property actors when the visualization method
  changes and improves entity factory handling for cylinder mode. This enhances user control over
  well rendering in the UI.

- **well2vtk**: Add borehole view mode selection for wells
  ([`0fe9323`](https://github.com/gecos-lab/PZero/commit/0fe932319788e8e6b92838ae028f00f10f74c4a5))

Introduces a context menu in the tree view to select borehole visualization mode (trace or cylinder)
  for wells. Updates 3D view logic to refresh well property actors when the visualization method
  changes and improves entity factory handling for cylinder mode. This enhances user control over
  well rendering in the UI.

- **wellcollection**: Refactor well collection
  ([`ed48703`](https://github.com/gecos-lab/PZero/commit/ed4870300b1138c1e1a596a0e2ef84217c7d655c))

Updated WellCollection to use 'Loc ID' as the key column for well legends instead of 'name'. Removed
  geology marker creation from well2vtk on temporary basis, ensuring wells are only added to
  WellCollection. Added helper for retrieving Loc ID by uid and clarified entity attributes for
  WellCollection.

- **wellcollection**: Refactor well collection
  ([`258b3e6`](https://github.com/gecos-lab/PZero/commit/258b3e636715df84286f60fdd668e0411bc5c2f9))

Updated WellCollection to use 'Loc ID' as the key column for well legends instead of 'name'. Removed
  geology marker creation from well2vtk on temporary basis, ensuring wells are only added to
  WellCollection. Added helper for retrieving Loc ID by uid and clarified entity attributes for
  WellCollection.

### Features

- Add interactive PCA-based boundary creation with size controls and preview
  ([`e30aeca`](https://github.com/gecos-lab/PZero/commit/e30aeca32bacf59ebc6700d08e04d4b4bd972b94))

- Add compute_pca_boundary() function for automatic boundary calculation using PCA - Implement
  boundary_from_pca() with enhanced interactive dialog - Add dropdown selection for creating new or
  updating existing boundaries - Include width/height sliders (10%-500%) for precise size control -
  Implement real-time preview system with "Update Preview" button - Support orientation-preserving
  scaling relative to PCA-computed center - Enable seamless 2D/3D boundary conversion during updates
  - Add automatic cleanup of temporary preview boundaries - Integrate PCA boundary option in Map
  View Create menu

Co-Authored-By: Riccardo Monti <150252648+r-monti14@users.noreply.github.com>

- Add oriented boundary support with coordinate transformation for Loop Structural
  ([`0e1b47d`](https://github.com/gecos-lab/PZero/commit/0e1b47d9101766c06f51da9b59fe4d672849bc46))

- Add compute_obb_boundary() function with interactive dialog and real-time preview - Implement
  coordinate transformation system for oriented boundaries in Loop Structural - Add boundary
  orientation detection using covariance analysis - Transform geological data to/from local
  coordinates for proper orientation handling - Update implicit_model_loop_structural() to respect
  boundary orientation - Add adaptive grid resolution and interpolation method selection for sparse
  data - Integrate "Boundary from OBB" option in MapView Create menu - Maintain backward
  compatibility with existing axis-aligned boundaries

Fixes issue where Loop Structural ignored oriented boundary geometry and created axis-aligned
  meshes. Iso-surfaces and voxets now properly align with oriented boundary coordinate systems,
  enabling accurate structural geology modeling.

Files modified: - pzero/collections/boundary_collection.py - pzero/three_d_surfaces.py -
  pzero/windows_factory.py

- **Take a screenshot**: Add advanced screenshot export dialog for VTK views
  ([`cd0b591`](https://github.com/gecos-lab/PZero/commit/cd0b59124623dbcf02a3f7de897422c4be453dff))

Introduces ScreenshotExportDialog for exporting high-quality screenshots with customizable
  resolution, format, colormap, and view settings. Integrates the dialog into ViewVTK, replacing the
  previous basic export_screen implementation and providing a more flexible export workflow.


## v1.2.6 (2025-09-30)

### Bug Fixes

- **pyinstaller**: Set pyinstaller=6.15.0 for Windows only
  ([`01c78fb`](https://github.com/gecos-lab/PZero/commit/01c78fbc1c153f8c27f67b383d835720acc516b4))


## v1.2.5 (2025-09-30)

### Bug Fixes

- **pyinstaller**: Set pyinstaller=6.15.0 to try and solve antivirus false positive
  ([`59cf13c`](https://github.com/gecos-lab/PZero/commit/59cf13cc875f0c24d25e76fe6d9633d0858eda24))


## v1.2.4 (2025-09-30)

### Bug Fixes

- **pyinstaller**: Added --hidden-import=pyogrio._geometry
  ([`44e2044`](https://github.com/gecos-lab/PZero/commit/44e204418aad08c4bbe3382396312efd6401561f))


## v1.2.3 (2025-09-30)

### Bug Fixes

- **pyinstaller**: Added --hidden-import=fiona.schema --hidden-import=fiona._shim
  ([`166fb17`](https://github.com/gecos-lab/PZero/commit/166fb17692f56283e699f8795bd14e4a4578eb78))


## v1.2.2 (2025-09-29)

### Bug Fixes

- **pyinstaller**: Added --hidden-import=geopandas
  ([`3aa9702`](https://github.com/gecos-lab/PZero/commit/3aa97028b61de10cbd326d9b4f22c3b68ee7d031))


## v1.2.1 (2025-09-26)

### Bug Fixes

- **Ubuntu**: Release name renamed from -Linux to -Ubuntu
  ([`9a6a6d9`](https://github.com/gecos-lab/PZero/commit/9a6a6d9f133d4d2a184d695e7dbd6b56260dde9e))


## v1.2.0 (2025-09-12)

### Bug Fixes

- **meshslicer**: Ensure Mesh Slicer dialog is singleton in View3D
  ([`bbca0c8`](https://github.com/gecos-lab/PZero/commit/bbca0c8f03823cb2f033bbb4a26cdc97040edaf4))

Adds logic to track and reuse a single instance of the Mesh Slicer dialog in the View3D class,
  preventing multiple dialogs from being opened simultaneously. The dialog reference is reset when
  the dialog is closed or destroyed, ensuring correct behavior for subsequent openings.

- **meshslicer**: Prevent slice planes from disappearing at mesh bounds
  ([`c947f22`](https://github.com/gecos-lab/PZero/commit/c947f22570796ed33472e6cc35b2f03d61fa7690))

Introduces a small epsilon to clamp slice positions slightly inside mesh bounds, preventing slice
  planes from disappearing when positioned at exact boundaries. Adjusts clamping logic and slice
  creation to ensure visibility, and updates widget bounds handling for vertical exaggeration.

### Features

- **MeshSlicer**: All the changes from mesh slicer has been forwarded and properly synced into the
  new refactored main
  ([`e7775cc`](https://github.com/gecos-lab/PZero/commit/e7775cc99e950d6fc409224dd2cf37526c8379a0))

Introduces a unified mesh slicer dialog in View3D supporting both single and multi-slice modes,
  direct manipulation, and property colormap synchronization. Slices now update their visuals when
  the main actor's property changes, and grid slices can be manipulated interactively. The
  implementation includes robust UI controls, synchronization with property changes, and improved
  slice actor management.


## v1.1.28 (2025-09-10)

### Bug Fixes

- **prop combo**: Temporary fix for normals
  ([`c8a19e0`](https://github.com/gecos-lab/PZero/commit/c8a19e05758526ddb2268cd2758a3a38304e733b))


## v1.1.27 (2025-09-09)

### Bug Fixes

- **prop combo**: Solved bug in tree combobox when removing a property
  ([`1f6c505`](https://github.com/gecos-lab/PZero/commit/1f6c5054a8a9cc1bfde9eb71f74021fbdc28bde5))


## v1.1.26 (2025-09-08)


## v1.1.25 (2025-09-07)

### Bug Fixes

- **zoom home**: Zoom to home view removed in 2D views
  ([`0884a3f`](https://github.com/gecos-lab/PZero/commit/0884a3f37474fb723bb1a511bb256fabe4e1c642))


## v1.1.24 (2025-09-07)

### Bug Fixes

- **2D selection**: On_selection_changed commented in map and xsection
  ([`931d1b7`](https://github.com/gecos-lab/PZero/commit/931d1b74690fcd4dfd6aaefb389b1b34fc05e266))


## v1.1.23 (2025-09-07)

### Bug Fixes

- **icon**: Windows icon added
  ([`1cdd7d6`](https://github.com/gecos-lab/PZero/commit/1cdd7d68379685ad3e03b468af7cf450439859a5))

- **tabMeshes**: Tabmeshes3d to tabMeshes
  ([`0bf8e48`](https://github.com/gecos-lab/PZero/commit/0bf8e4873a006aa82ecf166795dea9cbc9b4a9d7))


## v1.1.22 (2025-09-05)

### Bug Fixes

- **open project**: Texture null to empty list
  ([`78d22c8`](https://github.com/gecos-lab/PZero/commit/78d22c8b79cb6d5b129d478a9ef8fa2e52ebb30b))


## v1.1.21 (2025-09-03)

### Bug Fixes

- **print**: Removed some print
  ([`eccd957`](https://github.com/gecos-lab/PZero/commit/eccd95771ad2660f77fc10aaa70dc843e5c54e27))


## v1.1.20 (2025-09-02)

### Bug Fixes

- **print**: Removed some print
  ([`84ecdf9`](https://github.com/gecos-lab/PZero/commit/84ecdf9e3620ef384cd2752d1d2b2af11c9874dc))


## v1.1.19 (2025-09-01)

### Bug Fixes

- **splash**: New splash screen
  ([`ba647cf`](https://github.com/gecos-lab/PZero/commit/ba647cf6610a8ac10d6e5b9d30ebd0d9b29a1505))


## v1.1.18 (2025-09-01)

### Bug Fixes

- **terminal**: Many print's removed or sent to PZero terminal
  ([`4751dbf`](https://github.com/gecos-lab/PZero/commit/4751dbff32eb9aa2e0f295fdf2e604c0745c65de))


## v1.1.17 (2025-08-28)

### Bug Fixes

- **open project**: Rename texture column
  ([`b028221`](https://github.com/gecos-lab/PZero/commit/b028221fa1d0ed65001c5df3f68f7baa8ad4e89b))


## v1.1.16 (2025-08-28)

### Bug Fixes

- **open project**: Checks old projects dataframe columns and options when opening
  ([`ed95e8e`](https://github.com/gecos-lab/PZero/commit/ed95e8e03208756f3dec58d3c89cf54c68633b34))


## v1.1.15 (2025-08-22)

### Bug Fixes

- **XYZV in 2D**: Solved also for V
  ([`a7aeb3c`](https://github.com/gecos-lab/PZero/commit/a7aeb3cfb5c0a8302061e937129895884defe774))


## v1.1.14 (2025-08-22)

### Bug Fixes

- **XYZV in 2D**: Solved also for V
  ([`c39ece1`](https://github.com/gecos-lab/PZero/commit/c39ece1fff11ccd8026ed49d844ace9c1463f4a7))


## v1.1.13 (2025-08-22)

### Bug Fixes

- **XYZV in 2D**: Solved foe XYZ - V still problems
  ([`d3fe77f`](https://github.com/gecos-lab/PZero/commit/d3fe77f05e708d59f9c563f1a9d2e6a29c5c85cc))


## v1.1.12 (2025-07-14)

### Bug Fixes

- **splash screen**: Updated splash screen with --add-data
  ([`0d32cd5`](https://github.com/gecos-lab/PZero/commit/0d32cd556c4f947cd55fa2e161263f8d270735bb))


## v1.1.11 (2025-07-14)

### Bug Fixes

- **splash screen**: Updated splash screen with --add-data
  ([`9966817`](https://github.com/gecos-lab/PZero/commit/99668171211171ec298e265e5f8df7ed894be16f))


## v1.1.10 (2025-07-14)

### Bug Fixes

- **splash screen**: Updated splash screen with --add-data
  ([`68922c4`](https://github.com/gecos-lab/PZero/commit/68922c4191ff4e53812a4097c5ebe91be447a4ab))


## v1.1.9 (2025-07-14)

### Bug Fixes

- **splash screen**: Updated splash screen with --add-data
  ([`9cb34b9`](https://github.com/gecos-lab/PZero/commit/9cb34b9d0b65a575ddda56e6e3e8dda27f6e4884))


## v1.1.8 (2025-07-14)

### Bug Fixes

- **splash screen**: Updated splash screen with --add-data
  ([`355ffd8`](https://github.com/gecos-lab/PZero/commit/355ffd84da64f7124f596056cf9259c0b8cd073a))


## v1.1.7 (2025-07-14)

### Bug Fixes

- **splash screen**: Updated splash screen with --add-data
  ([`73aa8c1`](https://github.com/gecos-lab/PZero/commit/73aa8c174c2ae82abfdada03c5248a987c2b9032))


## v1.1.6 (2025-07-14)

### Bug Fixes

- **splash screen**: Updated splash screen with --add-data
  ([`fc85206`](https://github.com/gecos-lab/PZero/commit/fc85206376282e2b72918a7421944825e49a87c9))


## v1.1.5 (2025-07-14)

### Bug Fixes

- **splash screen**: Updated splash screen with --add-data
  ([`dd8fa29`](https://github.com/gecos-lab/PZero/commit/dd8fa29a2c70ebde777675d5487f054ff8591afd))


## v1.1.4 (2025-07-14)

### Bug Fixes

- **splash screen**: Updated splash screen with --add-data
  ([`a2f23bd`](https://github.com/gecos-lab/PZero/commit/a2f23bd9fa7301e9faf551004f38035e06f14fdb))


## v1.1.3 (2025-07-14)

### Bug Fixes

- **splash screen**: Updated splash screen with --add-data
  ([`4de3730`](https://github.com/gecos-lab/PZero/commit/4de3730c86e87e612daab29cffb84c76f8646226))


## v1.1.2 (2025-07-11)

### Bug Fixes

- **splash screen**: New splash screen in exe
  ([`b8e67e5`](https://github.com/gecos-lab/PZero/commit/b8e67e567c9a7ece6604f49b20bb37931cf31511))


## v1.1.1 (2025-07-11)

### Bug Fixes

- **splash screen**: New splash screen in exe
  ([`44840c3`](https://github.com/gecos-lab/PZero/commit/44840c3e3a724eab365b57cc1a7a79a62c94687e))

- **splash screen**: New splash screen in exe
  ([`8e2cb88`](https://github.com/gecos-lab/PZero/commit/8e2cb88e1b23d97446ac3ccb3f2d8da22cb76de2))


## v1.1.0 (2025-07-11)


## v0.1.24 (2025-06-18)


## v0.1.23 (2025-05-22)

### Bug Fixes

- **ReadMe**: Readme updated to point to exe etc
  ([`3ba1e18`](https://github.com/gecos-lab/PZero/commit/3ba1e188ebe4b52928bb32d024af0aedd9c4c902))


## v0.1.22 (2025-05-22)

### Bug Fixes

- **Actions**: Reverting back to previous
  ([`08a02d7`](https://github.com/gecos-lab/PZero/commit/08a02d7268426a881f96c72118fb8933d3510606))


## v0.1.21 (2025-05-22)

### Bug Fixes

- **Actions**: Ubuntu-20.04 added, file names fixed
  ([`10b63f0`](https://github.com/gecos-lab/PZero/commit/10b63f01f2e71fff23a01ead3cf2fab96a0b2723))


## v0.1.20 (2025-05-21)

### Bug Fixes

- **Actions**: Try fixing Upload executable and macos #7
  ([`353fc03`](https://github.com/gecos-lab/PZero/commit/353fc0399216fafb4b4364acb7828d207e3124b0))


## v0.1.19 (2025-05-21)

### Bug Fixes

- **Actions**: Try fixing Upload executable and macos #6
  ([`28ef8c5`](https://github.com/gecos-lab/PZero/commit/28ef8c5981755bb7872bdb908985d15d6e1ad360))


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
