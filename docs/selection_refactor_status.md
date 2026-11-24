# Global selection refactor — status and handoff

Branch: `global_selection` (from `Release_2.0`). Last update: 2026-11-17.

This file lets work continue from any workstation or Claude Code session: read it first, together with
the "Selection and tools" section of `pzero/README.md` (selection model and the table of which entities
each tool accepts — keep that table in sync when a tool spec changes).

## Goal

Three systems managed selection (project window tables, each view, the tree inside each view). They
are now synced through a single project-level store, keeping their functionality.

## Design in short

- Store: `ProjectWindow._selection`, ordered dict `{uid: collection_name}` in click order. Every change
  goes through `ProjectWindow.set_selection(uids, mode, collection, source)` (modes: replace, add,
  remove, toggle, clear); "replace" keeps the position of uids already selected.
- Signals: `selection_modified(added, removed, collections, source)` and the legacy
  `selection_changed(collection)`.
- Readers: `collection.selected_uids` (delegates to the store, returns a copy),
  `ProjectWindow.selected_uids` (collection of the tab in front), `view.selected_uids` (read-only,
  project selection restricted to the entities shown in the view).
- Tables (`connect_table_selection`, `_sync_table_selection`) and trees
  (`CustomTreeWidget.on_tree_selection_changed`, `set_selection_from_collection`) send changes to the
  store and mirror it. Trees send add/remove deltas; selecting a group selects all its entities.
- VTK views (`ViewVTK`): highlight of changed uids only, flushed once per event loop iteration with
  one render. Yellow outer border for surfaces/DEMs/DOMs/images, yellow edges for closed surfaces,
  yellow thicker lines/points, box for point clouds and volumes. `show_actor_with_property` and
  `change_actor_*` are wrapped automatically in every subclass (`__init_subclass__`) so the highlight
  survives actor re-creation and legend changes.
- Freeze: `disable_actions` / `enable_actions` (used by the freeze decorators) also freeze user
  selection in tables and trees (`ProjectWindow.set_selection_frozen`).
- Tools: `@uses_selection(valid=..., topologies=..., require_properties=..., min_selected=...,
  max_selected=...)` (`helpers/helper_functions.py`) calls
  `ProjectWindow.restrict_selection_for_tool` before a tool runs: one collection per run, only usable
  entities, last N in click order, others deselected; if not enough, the tool does not run.
  Tools read `active_collection(self)` and write outputs in the same collection
  (`derived_entity_dict`, `entity_metadata_input_dict`, `uid_metadata`).

## Deferred view and legend updates

Entity signals (added, removed, geometry, properties, metadata, legend styles) are queued by each view
(`BaseView._queue_entity_update`), merged per kind and collection, and processed once per event loop
iteration (`_run_deferred`): pending legend rebuilds first (`ProjectWindow.request_legend_update` /
`flush_legend_updates`; `Legend` and `PropertiesCMaps.update_widget` only request a rebuild), then the
updates in a fixed order (removed, added, geometry, properties, metadata, legend styles), then the
selection highlight, with VTK rendering suppressed during the pass and one render at the end.
Commands that read the content of a view (`@uses_selection` with a view, line tools, Ctrl+A) call
`view.flush_pending_updates()` first. `ViewVTK.get_actor_by_uid` caches actors (PyVista 0.45 looks
actors up with a linear scan). `append_uid_property` emits data_keys_added (was metadata_modified).
Benchmark: `python tests/selection/bench_bulk_updates.py 300` (300 TriSurfs, 2 views: add 10 s,
dip/direction 14 s, remove 7 s; more than 15 minutes in total before).

## Phases

| Phase | Content | Status |
|---|---|---|
| 1 | Store, signals, collection delegation | Done, GUI-tested, commit 5a68684 |
| 2 | Project tables adapter, tab brought to front | Done, GUI-tested, commit 761b61f |
| 3 | View trees adapter, group selection, rebuilds keep selection | Done, GUI-tested, commit 761b61f |
| 4 | VTK views highlight and picking + follow-ups below | Done, GUI-tested (commits from 5075b6f) |
| 5 | Stereoplot: drawing, contours, statistics on shown entities, selection highlight, shortcuts, Select menu | Done, GUI-tested (commits be142d7 to ea149cc) |
| 6 | Remove dead code: `BaseViewSignals.newSelection`, commented `on_selection_changed` slots in `view_map.py` / `view_xsection.py`, commented `selected_uids_all`, the empty stereoplot `on_selection_changed` slot. `AbstractCollection._selected_uids` is kept: it is the fallback of collections not attached to a project window | Done |

Phase 4 follow-ups included in the same commit:

- Line tools in 2D views keep the selection (edit, sort, move, rotate, extend, split x2, snap,
  resample x2, simplify; weld selects the welded line; copy parallel/kink/similar still clear it);
  single-line tools use the last selected line.
- All selection-based tools decorated with `@uses_selection`; early tools converted from
  `self.geol_coll` to the active collection (any collection, outputs in the same collection).
- Extrusion: simple + densified merged in one tool (`three_d_surfaces.linear_extrusion`, checkbox for
  densification), only in View3D > Create.
- Point clouds: Properties > Calculate Dip/Direction wired to `point_clouds.normals2dd` (any entity
  with Normals); new Interpolation > "Planar facets from PC clusters" (`facets_pc`); both removed from
  View3D > Create. Build Octree restricted to point clouds.
- Intersection with cross-section (`intersection_xs`) by topology on any collection; TetraSolid is a
  placeholder. Projection to DEM / cross-section also accepts boundary lines.

## Decisions taken (do not re-discuss unless asked)

- Click order everywhere; tools deselect entities they cannot use (no silent filtering).
- New entities created by split tools (line by line, at point, surface, multipart) and newly drawn
  lines join the selection; all parts of a split line get the `_split` suffix, the weld output `_weld` (once);
- Ctrl+A / Ctrl+Shift+A (Cmd on macOS): select / deselect all in tables, trees and views; in the
  graphics of a view Ctrl+A selects the shown entities and deselects the hidden ones of that view
  (hiding alone never deselects); weld/snap print why lines of other sections are not used;
  after Entities > Clone the clones replace the originals in the selection, and after copy
  parallel/kink/similar the copies replace the input lines (no line tool clears the selection).
- Clone works on any number and type of entities, cross-sections included; copy parallel/kink/similar
  work on all selected lines, one copy per line: in cross-section views lines of that section only
  (same_parent), in map views any PolyLine/XsPolyLine (no section filter).
- Mixed collections (`cross_collection=True`) for tools that modify/derive each entity independently
  or cut entities with another one (2D line tools except weld, surface modifiers, split line/surface,
  intersection, projection, connected parts, split multipart, properties, dip/direction, remove,
  clone, info, export VTK, CRS): each output stays in its input's collection. One collection for
  tools with a single output from several inputs (weld, merge to multipart, interpolations).
  The README table has a "Collections per run" column.
- Single-entity tools use the last selected entity.
- Picking in a view selects among the entities of that view; selections in other views/collections
  are kept. Hidden entities stay selected (no highlight while hidden).
- Selecting from a view or view tree brings the collection tab to front.
- Views are always shown: do not defer highlight of hidden views; no merged highlight actor for now.
- Orientation convention: downward normals for upright planes, upward for overturned ones. Poles
  and lineations: overturned/upward = negative plunge. Planes: overturned can be dip > 90 or
  negative dip with opposite direction (equivalent, same pole); both accepted on input
  (`dip_directions2normals`), dip > 90 used when computing from normals
  (`normals2dip_directions`, same as `points_map_dip`). The facing direction of a surface cannot
  be known by the software (VTK orients normals consistently, not up/down): Properties > Invert normals
  polarity (`orientation_analysis.invert_polarity`) flips Normals and/or dip/direction of the
  selected entities (TriSurf triangle order too, so Calculate Normals keeps it). Calculate Normals,
  Calculate Dip/Direction and Invert polarity emit data_val_modified: views showing the changed
  values redraw them (the stereoplot always, since pole positions depend on Normals). Fixed in
  `ViewVTK.show_actor_with_property`: 3-component properties (Normals, RGB) on lines/surfaces were
  reset to the legend colour unless a stale legend row with the plain name existed (the property
  legend lists them only per component, e.g. Normals[0]), which made the redraw fail. Views check
  the shown drop-down item with `BaseView.shown_property_available` (default items, properties,
  components such as Normals[2] of "Normals", textures): before, an entity showing a component was
  reset to the legend colour (tree not updated) whenever properties were added or values changed.
  `PolyData.points_map_dip` / `points_map_dip_direction` deliberately unchanged (apparent-dip traces
  in map/cross-section views rely on them).
- Intersection: PolyLine/XsPolyLine → XsVertexSet, TriSurf → XsPolyLine, DEM/TSDom → DomXs,
  Voxet → XsVoxet; boundary lines give no output (Boundaries cannot store points); TetraSolid
  placeholder (future output TriSurf or XsTriSurf). Merge to multipart (Entities menu, not Weld
  lines): any PolyData topology (points, lines, surfaces, PCDom, TSDom), one topology per merge.
- Projection > Project to DEM/surface (`project_2_dem`, 2026-11-23): onto any DEM, DOM
  surface (TSDom) or TriSurf of any collection (`_projection_surfaces`), by intersecting the vertical
  through each point with the surface (`_VerticalProjector`, vtkModifiedBSPTree: all crossings;
  the one nearest to the point's elevation on folds); points outside keep their elevation (message);
  no surface -> message, no dialog. Outputs `<name>_prj_<surface>`; the outputs of Project to
  DEM/surface, Project to X-section and X-section Intersection become the selection
  (`_selects_new_entities`). Views keep the 3:1 split on resize until the user moves the divider
  (a view opened as a later tab got about 1:1). Draw line also in Boundaries (name and scenario only). Cross-section
  views show "Xsection <name>" in their tab.
- Orientation property names (2026-11-23, see "Orientation conventions" in pzero/README.md):
  Normals, Dip, Direction (planes); Lineations, Plunge, Trend (lines). Older names (dip direction,
  dip_dir, azimuth, plunge, trend, ...) are renamed when a project is opened
  (`normalize_orientation_names`: metadata, VTK point/cell/field arrays, property legend);
  importers (xyz, shapefile: Dip, Direction, Strike = right-hand rule, Plunge, Trend, Nx/Ny/Nz,
  Lx/Ly/Lz) and tools write the canonical names; xyz-imported normals keep their sign.
  Test: `tests/selection/sel_orientation_names.py`.
- Meshes and images open showing their active property (or the first one), and the tree drop-down
  shows it (`BaseView.initial_show_property`). Before, Voxets were drawn without a colour, so
  PyVista coloured them by their active property while the drop-down said "none"; with "none"
  Voxets now use the legend colour. Images: a whole RGB(A) property is shown as is (the Images
  tree lists whole multi-component properties), one band (a component such as RGB[0], or a
  single-component property) is painted with the colormap and range of the properties legend
  (`ViewVTK.image_property_texture`). X, Y, Z are offered only for entities that store point
  coordinates (not Voxet, XsVoxet, MapImage, XsImage). Test: `tests/selection/sel_initial_property.py`.
- Lineation tools (2026-11-24): Properties > Calculate Lineations (`set_lineations`: point sets
  from Plunge/Trend, lines from their segments, inversion proposed if mostly upwards), Calculate
  Plunge/Trend (`lineations2pt`, was not connected), Invert lineations (`invert_lineations`, also
  reverses the node order of lines). Test: `tests/selection/sel_lineations.py`.
- Stereoplot Analysis menu (2026-11-24): Contour settings (exponential Kamb, linear Kamb, Kamb,
  Schmidt; sigma) and Axial (bidirectional) / Polar (unidirectional) data, used by contours and
  statistics for both normals and lineations (before: normals axial, lineations polar for
  statistics, everything axial for contours). `kamb_density_grid(method=..., axial=...)`.
  Analysis menu order: data type | Contour settings | Fisher | Bingham | K-medoids (k, seed
  picking, centres, colours, Save cluster ID as property, Show statistics: terminal only), with
  titled sections Fisher, Bingham, K-medoids.
  View > Contour display settings: base colour (single-hue colormap) of lines and fills (filled
  contours keep their lines) and the contours-only threshold. Switching axial/polar redraws only
  the entities drawn as contours and computes the pooled contours once (3.8 s -> 1.3 s with a
  100k-vector entity).
- Merge to multipart, weld and snap: inputs and outputs belong to one cross-section; only entities
  with the parent_uid of the last selected one are used (`same_parent=True`), others deselected.

## Stereoplot (phase 5)

- Any entity of any collection with Normals and/or Lineations is drawn from its vectors
  (`ViewStereoplot.show_actor_with_property`): Normals as circles (poles), Lineations as triangles.
  Downward vectors filled on the lower hemisphere; upward vectors (overturned poles, negative
  plunge) hollow, same color and size, on the upper hemisphere at their own trend. "Planes" draws
  great circles, dashed for overturned planes. The artists of an entity are grouped in a
  `StereoActor`; colour/opacity changes redraw the entity.
- Entities with more than `contours_only_threshold` vectors (default 20000, View > Contours-only
  threshold) are drawn as density lines in their legend colour instead of markers (hidden with
  Toggle poles). Toggle contours (lines / filled / off) draws one density of all the shown entities
  together, updated when entities are shown, hidden, added or removed; filled contours start
  above 0 (background not filled).
- Kamb kernel capped at 1000 points (`kamb_density_grid(max_kernel_n=1000)`): with more points
  the kernel gets narrower than the grid and the contours are noise; above 1000 the density is
  the expected one of a 1000-point random sample (identical to mplstereonet up to 1000); vectors
  are then merged in ~1 degree bins (error < 1% of the maximum). Benchmark (markers vs contours,
  build / redraw): 100k 1.3-3.5 s / 1.3-3.3 s vs 1.6 s / 0.06 s; 1M 17-34 s / 25-31 s vs 4.7 s /
  0.06 s. Markers cost every redraw (hide/show, selection, toggles), contours only once.
- k-medoids (`kmedoids_clusters`): no N x N matrices (320 GB for 100k axial normals, which made
  the statistics swap); medoids of clusters above 4000 vectors are approximated as in
  CLARA (`_cluster_medoid`), iterations stop when the total distance stops decreasing.
  100k normals: k=1..8 in 0.05-0.8 s; results on small datasets unchanged. k-medoids on Normals
  stays biaxial (data doubled with antipodes, user decision 2026-11-23). Since 2026-11-24: 2k
  clusters of the doubled data, each merged with its opposite copy, so k clusters for any k
  (with k clusters of the doubled data even k gave k/2); paired k-medoids++ initialisation. The k spin box works in detached menus (`KSpinBoxAction`). Benchmark: markers 0.35 s per
  100k points per redraw; mplstereonet Kamb contours 10 s for 20k points, so contours use
  `orientation_analysis.kamb_density_grid` (same result, k-d tree, 0.34 s for 100k, 2.7 s for 1M).
- Statistics (Fisher, Bingham, k-medoids) are computed on the shown entities, as the pooled
  contours, not on the selection; there is no Recompute / auto recomputation command. Showing,
  hiding, adding or removing entities recomputes them and redraws the overlays whose checkbox is
  checked (quietly: results are printed only when a box is checked); the checkboxes are never
  changed automatically. Statistics are computed only when needed (a checked overlay, seed
  picking, Save clusters, Export statistics, k change).
- Lasso (selection), seed picking (shown entities) and cluster saving work on any collection and
  use the same positions as the drawing. Fixed: Toggle projection/contours crashed (`_deactivate_rectangle`
  did not exist); entities hidden at a rebuild could not be shown again.
- View > Toggle poles (markers of Normals and Lineations, e.g. to see contours) and Toggle great
  circles (planes of all Normals). Analysis overlays: axial results (Bingham axes, normals) folded
  to the lower hemisphere, directional ones (lineations) hollow when upward; no arcsin warnings.
- View filters (`BaseView.sync_view_filter`, used by the properties and metadata handlers of all
  views): entities that start/stop matching the filter of a view after a change enter/leave it,
  e.g. Calculate Normals adds an entity to the stereoplot, a parent_uid change moves it in/out of a
  cross-section view (no tool changes parent_uid of an existing entity at the moment). Fixed Calculate Normals on point
  sets (`vset_set_normals` shadowed its argument).
- Stereoplot Select menu: "By polygon" (one-shot region selection, no checkbox) and
  "Clear Selection" (as in the other views). Ctrl+A / Ctrl+Shift+A work on the stereoplot
  canvas (it had no focus policy, so the view shortcuts never received the keys).
  Move to another collection brings the destination table tab to front.
- Stereoplot selection highlight (`selection_modified_update_actors`,
  `_update_selection_highlight`): yellow rings on the poles of the selected entities shown in
  the view, whatever selected them (Ctrl+A, polygon, tables, other views); hidden entities and
  hidden poles are not highlighted; at most 2000 rings per entity. The polygon tool no longer
  draws its own highlight. The mplstereonet warning "invalid value encountered in arcsin" (cursor
  far outside the stereonet circle) is filtered in view_stereoplot.py (library untouched).
- Test: `tests/selection/sel_stereoplot.py`.

## Open items

All phases done and GUI-tested (checklist below). Left for separate work:

- Tools specific to the interpretation and cross-section views (`view_interpretation.py`,
  `view_xsection.py`) still keep their own record of picked entities.
- Exports refactor (deferred by the user).
- Point-cloud tools: GUI checks of section 6 (Planar facets from PC clusters, Build Octree), deferred by the user.
- Not covered by headless tests: DEM/TSDom/Voxet intersection branches, project-to-DEM of boundary
  lines, mouse picking, visual look of the highlight.

## Headless tests

Root tests (`pytest tests/test_point_clouds.py tests/test_entities_factory.py`): the
normals2dd / facets_pc tests use `_FakeProject` (the tools run on the project window since the
refactor); before, four normals2dd tests passed without testing anything (dip was pre-set).

`tests/selection/` — run `pytest tests/selection` (about 1 minute) or a single script, e.g.
`.venv\Scripts\python.exe tests\selection\sel_trees.py`. Each script prints PASS/FAIL per check.

## GUI test checklist (phase 4 commit)

Watch the PZero terminal and the console for tracebacks.

1. — PASSED 2026-11-17. Highlight (3D + map view open): open/closed surface, property-coloured line, points, well, DEM,
   textured DOM, point cloud, image, cross-section; Ctrl-A in a large table then deselect
   (responsiveness); change shown property / legend colour and thickness / hide-show while selected;
   vertical exaggeration; a new view shows the existing selection.
2. Picking: click, Shift-click, click on an already selected entity (tab to front), Clear selection
   button (only entities of that view; there is no `c` shortcut). — PASSED 2026-11-17
3. — PASSED 2026-11-17. Freeze: during Edit/Move line, table and tree selection (also right-click) cannot change; picking
   still works; everything unfreezes after the tool.
4. Line tools in a cross-section: line + surface + line selected → Edit line keeps only the last
   line; Sort/Resample keep all lines in click order; selection kept after the listed tools; weld
   selects the result; copy tools clear; weld and snap with lines of two sections (or section + map
   lines) use only the lines of the last clicked line's section.
5. Tools on other collections: smoothing/decimation/subdivision/retopo on Fluids and Boundaries
   TriSurfs (output in the same collection, no role/feature in Boundaries); Delaunay/Poisson on fluid
   points; merge to multipart of two lines and of two surfaces (result selected), lines + surface
   (surface deselected), a single entity refused, entities of two sections (only the last one's
   section merged); connected parts / split multipart on a
   boundary TriSurf; property add/remove on a mesh or image; a selection with nothing usable prints
   what is needed and does not run.
6. Moved tools: View3D > Create > Extrusion with and without densification (not in project window
   or 2D views); Properties > Calculate Dip/Direction on a point cloud and a TriSurf with Normals
   (overturned → dip > 90; wrong polarity → Properties > Invert normals); Interpolation > Planar
   facets from PC clusters; Build Octree only on
   point clouds.
7. Intersection/projection: boundary TriSurf → XsPolyLine; boundary line → message, no output;
   DEM and TSDom → DomXs; Voxet in Meshes and in Images → XsVoxet; TetraSolid → "not implemented";
   XsPolyLine of section A cut by section B → XsVertexSet; boundary line projected to DEM and to a
   cross-section; attitude import with negative dip or dip > 90 → overturned plane.
8. Regression sweep: open/new project, close views; delete a selected entity; move an entity to
   another collection (stays selected); stereoplot lasso.
9. Stereoplot: TriSurf / point cloud / fluid or boundary entity with Normals shown; overturned
   surface → hollow poles on the opposite side; lineations as triangles (upward hollow); a large
   point cloud → contours in its colour (change View > Contours-only threshold); Toggle poles / great
   circles; Calculate Normals on a point set adds it to the view; Planes, colour by
   property, legend colour/opacity, hide/show; Toggle contours / projection / grid; lasso;
   statistics follow hide/show with the checked boxes unchanged; save clusters.
