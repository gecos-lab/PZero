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

## Phases

| Phase | Content | Status |
|---|---|---|
| 1 | Store, signals, collection delegation | Done, GUI-tested, commit 46ff7a4 |
| 2 | Project tables adapter, tab brought to front | Done, GUI-tested, commit f75c790 |
| 3 | View trees adapter, group selection, rebuilds keep selection | Done, GUI-tested, commit f75c790 |
| 4 | VTK views highlight and picking + follow-ups below | Done, **GUI test pending** (commit after f75c790) |
| 5 | Matplotlib views: stereoplot highlight (signed dips → upper hemisphere), 2D/interpretation views | To do |
| 6 | Remove dead code: `BaseViewSignals.newSelection`, commented `on_selection_changed` slots in `view_map.py` / `view_xsection.py`, commented `selected_uids_all`, `AbstractCollection._selected_uids` | To do |

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
- Single-entity tools use the last selected entity.
- Picking in a view selects among the entities of that view; selections in other views/collections
  are kept. Hidden entities stay selected (no highlight while hidden).
- Selecting from a view or view tree brings the collection tab to front.
- Views are always shown: do not defer highlight of hidden views; no merged highlight actor for now.
- Orientation convention: downward normals for upright planes; -90 < dip < 90, negative for
  overturned surfaces (upper hemisphere), standard dip direction in both cases
  (`orientation_analysis.normals2dip_directions`, `dip_directions2normals`).
  `PolyData.points_map_dip` / `points_map_dip_direction` deliberately unchanged (apparent-dip traces
  in map/cross-section views rely on them).
- Intersection: PolyLine/XsPolyLine → XsVertexSet, TriSurf → XsPolyLine, DEM/TSDom → DomXs,
  Voxet → XsVoxet; boundary lines give no output (Boundaries cannot store points); TetraSolid
  placeholder (future output TriSurf or XsTriSurf). Merge to multipart: lines only.

## Open items

- GUI test of the phase 4 commit (checklist below).
- Phase 5 and 6.
- Tools specific to the interpretation and cross-section views (`view_interpretation.py`,
  `view_xsection.py`) and the stereoplot still use their own selection logic (phase 5).
- Pre-existing: meshes open with a scalar property applied but not selected in the tree drop-down
  (not investigated).
- Not covered by headless tests: DEM/TSDom/Voxet intersection branches, project-to-DEM of boundary
  lines, mouse picking, visual look of the highlight.

## Headless tests

`tests/selection/` — run `pytest tests/selection` (about 1 minute) or a single script, e.g.
`.venv\Scripts\python.exe tests\selection\sel_trees.py`. Each script prints PASS/FAIL per check.

## GUI test checklist (phase 4 commit)

Watch the PZero terminal and the console for tracebacks.

1. Highlight (3D + map view open): open/closed surface, property-coloured line, points, well, DEM,
   textured DOM, point cloud, image, cross-section; Ctrl-A in a large table then deselect
   (responsiveness); change shown property / legend colour and thickness / hide-show while selected;
   vertical exaggeration; a new view shows the existing selection.
2. Picking: click, Shift-click, click on an already selected entity (tab to front), clear selection
   button / `c` (only entities of that view).
3. Freeze: during Edit/Move line, table and tree selection (also right-click) cannot change; picking
   still works; everything unfreezes after the tool.
4. Line tools in a cross-section: line + surface + line selected → Edit line keeps only the last
   line; Sort/Resample keep all lines in click order; selection kept after the listed tools; weld
   selects the result; copy tools clear.
5. Tools on other collections: smoothing/decimation/subdivision/retopo on Fluids and Boundaries
   TriSurfs (output in the same collection, no role/feature in Boundaries); Delaunay/Poisson on fluid
   points; merge of fluid lines (a surface alone is refused); connected parts / split multipart on a
   boundary TriSurf; property add/remove on a mesh or image; a selection with nothing usable prints
   what is needed and does not run.
6. Moved tools: View3D > Create > Extrusion with and without densification (not in project window
   or 2D views); Properties > Calculate Dip/Direction on a point cloud and a TriSurf with Normals
   (overturned → negative dip); Interpolation > Planar facets from PC clusters; Build Octree only on
   point clouds.
7. Intersection/projection: boundary TriSurf → XsPolyLine; boundary line → message, no output;
   DEM and TSDom → DomXs; Voxet in Meshes and in Images → XsVoxet; TetraSolid → "not implemented";
   XsPolyLine of section A cut by section B → XsVertexSet; boundary line projected to DEM and to a
   cross-section; attitude import with negative dip → overturned plane.
8. Regression sweep: open/new project, close views; delete a selected entity; move an entity to
   another collection (stays selected); stereoplot lasso and auto-recompute.
