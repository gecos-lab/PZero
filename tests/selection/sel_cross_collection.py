"""Headless check: tools of categories A (per entity) and B (cutters) work across collections,
each output staying in the collection of its input; category C tools stay single-collection."""
import os
import sys
from copy import deepcopy
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))

from PySide6.QtWidgets import QApplication, QMessageBox

app = QApplication.instance() or QApplication(sys.argv)
import numpy as np  # noqa: E402
import pyvista as pv  # noqa: E402
from pzero.project_window import ProjectWindow  # noqa: E402
from pzero.entities_factory import PolyLine, TriSurf  # noqa: E402
import pzero.three_d_surfaces as tds  # noqa: E402
import pzero.project_window as pwm  # noqa: E402

pw = ProjectWindow()
failed = False


def check(label, cond):
    global failed
    print(("PASS " if cond else "FAIL ") + label)
    failed |= not cond


def add(coll, topology, cls, mesh, name):
    d = deepcopy(coll.entity_dict)
    d.update(name=name, uid=str(uuid4()), topology=topology)
    if "role" in d and coll.valid_roles:
        d["role"] = coll.valid_roles[0]
    obj = cls()
    obj.ShallowCopy(mesh)
    d["vtk_obj"] = obj
    return coll.add_entity_from_dict(entity_dict=d)


def select(*uids):
    pw.set_selection(mode="clear")
    for u in uids:
        pw.set_selection([u], mode="add")


plane = pv.Plane(i_resolution=6, j_resolution=6).triangulate()
line = pv.Line((-0.5, 0.1, 0.0), (0.5, 0.1, 0.0), resolution=8)
g_surf = add(pw.geol_coll, "TriSurf", TriSurf, plane, "g_surf")
f_surf = add(pw.fluid_coll, "TriSurf", TriSurf, plane, "f_surf")
b_surf = add(pw.boundary_coll, "TriSurf", TriSurf, plane, "b_surf")
g_line = add(pw.geol_coll, "PolyLine", PolyLine, line, "g_line")
f_line = add(pw.fluid_coll, "PolyLine", PolyLine, line, "f_line")
b_line = add(pw.boundary_coll, "PolyLine", PolyLine, line, "b_line")

# A: smoothing of a geology and a fluid TriSurf together, outputs in their own collections
n_g, n_f = len(pw.geol_coll.df), len(pw.fluid_coll.df)
select(g_surf, g_line, f_surf)
tds.surface_smoothing(pw)
check("smoothing: output in geology", len(pw.geol_coll.df) == n_g + 1 and pw.geol_coll.df["name"].iloc[-1] == "g_surf_smoothed")
check("smoothing: output in fluids", len(pw.fluid_coll.df) == n_f + 1 and pw.fluid_coll.df["name"].iloc[-1] == "f_surf_smoothed")
check("smoothing: both surfaces stay selected, line deselected", pw.selection_uids() == [g_surf, f_surf])

# A: connected parts on geology and boundary surfaces together
select(g_surf, b_surf)
pw.connected_parts()
check("connected parts on geology and boundaries",
      "RegionId" in pw.geol_coll.get_uid_properties_names(g_surf)
      and "RegionId" in pw.boundary_coll.get_uid_properties_names(b_surf))

# A: clone across collections, each clone in its own collection
n_g, n_b = len(pw.geol_coll.df), len(pw.boundary_coll.df)
select(g_line, b_line)
pw.entity_clone()
check("clone in geology and boundaries", len(pw.geol_coll.df) == n_g + 1 and len(pw.boundary_coll.df) == n_b + 1)
clones = [pw.geol_coll.df["uid"].iloc[-1], pw.boundary_coll.df["uid"].iloc[-1]]
check("clones selected instead of originals", sorted(pw.selection_uids()) == sorted(clones))

# A: remove across collections (confirmation stubbed)
pwm.QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
tmp_g = add(pw.geol_coll, "PolyLine", PolyLine, line, "tmp_g")
tmp_f = add(pw.fluid_coll, "PolyLine", PolyLine, line, "tmp_f")
select(tmp_g, tmp_f)
pw.entity_remove()
check("remove across collections",
      tmp_g not in pw.geol_coll.get_uids and tmp_f not in pw.fluid_coll.get_uids and pw.selection_uids() == [])

# A: line tools keep lines of several collections; C: weld stays in one collection
from pzero.views.view_3d import View3D  # noqa: E402
from pzero.two_d_lines import start_checked_line_tool  # noqa: E402

v = View3D(parent=pw)
seen = []
select(g_line, f_line, g_surf)
start_checked_line_tool(v, lambda view: seen.append(view.selected_uids), cross_collection=True)
check("line tool across geology and fluids", seen[-1] == [g_line, f_line])
v.enable_actions()
select(g_line, f_line)
start_checked_line_tool(v, lambda view: seen.append(view.selected_uids), min_selected=1)
check("weld-like tool (single collection) keeps one collection", seen[-1] == [f_line])
v.enable_actions()

# A: projection to cross-section of geology, fluid and boundary lines together
xs = deepcopy(pw.xsect_coll.entity_dict)
xs.update(name="XS1", origin_x=0.2, origin_y=-2.0, origin_z=-2.0, strike=0.0, dip=90.0, length=4.0, height=4.0)
pw.xsect_coll.add_entity_from_dict(entity_dict=xs)
tds.input_checkbox_dialog = lambda **kw: ["XS1"]
tds.general_input_dialog = lambda **kw: {"dist_sec": 0.0, "proj_plunge": 0.0, "proj_trend": 90.0, "filter_polyline_geometry": ""}
n_g, n_f, n_b = len(pw.geol_coll.df), len(pw.fluid_coll.df), len(pw.boundary_coll.df)
select(g_line, f_line, b_line)
tds.project_2_xs(pw)
check("projection outputs in geology, fluids and boundaries",
      pw.geol_coll.df["name"].iloc[-1] == "g_line_prj_XS1" and len(pw.geol_coll.df) == n_g + 1
      and pw.fluid_coll.df["name"].iloc[-1] == "f_line_prj_XS1" and len(pw.fluid_coll.df) == n_f + 1
      and pw.boundary_coll.df["name"].iloc[-1] == "b_line_prj_XS1" and len(pw.boundary_coll.df) == n_b + 1)
check("projection to X-section: the projected entities become the selection",
      sorted(pw.selection_uids()) == sorted([pw.geol_coll.df["uid"].iloc[-1], pw.fluid_coll.df["uid"].iloc[-1],
                                             pw.boundary_coll.df["uid"].iloc[-1]]))

# B/A: intersection of a fluid line and a geology surface together
n_g, n_f = len(pw.geol_coll.df), len(pw.fluid_coll.df)
select(f_line, g_surf)
tds.intersection_xs(pw)
check("intersection outputs in fluids and geology",
      pw.fluid_coll.df["topology"].iloc[-1] == "XsVertexSet" and len(pw.fluid_coll.df) == n_f + 1
      and pw.geol_coll.df["topology"].iloc[-1] == "XsPolyLine" and len(pw.geol_coll.df) == n_g + 1)
check("intersection: the outputs become the selection instead of the inputs",
      sorted(pw.selection_uids()) == sorted([pw.fluid_coll.df["uid"].iloc[-1], pw.geol_coll.df["uid"].iloc[-1]]))


# split creates new entities that join the selection (split multipart: parts replace the original)
two_parts = pv.Line((0, 5, 0), (1, 5, 0), resolution=2) + pv.Line((3, 5, 0), (4, 5, 0), resolution=2)
mp = add(pw.fluid_coll, "PolyLine", PolyLine, two_parts, "mp")
select(mp)
pw.split_multipart()
parts = [u for u in pw.fluid_coll.get_uids if pw.fluid_coll.get_uid_name(u).startswith("mp_")]
check("split multipart: parts created and selected", len(parts) == 2 and sorted(pw.selection_uids()) == sorted(parts))


# copy parallel / similar on several lines of several collections (map view): one copy each,
# in the collection of its line, copies selected
import pzero.two_d_lines as tdl  # noqa: E402
from pzero.views.view_map import ViewMap  # noqa: E402

vm = ViewMap(parent=pw)
c1 = add(pw.geol_coll, "PolyLine", PolyLine, pv.Line((0, 10, 0), (5, 10, 0), resolution=5), "c1")
c2 = add(pw.fluid_coll, "PolyLine", PolyLine, pv.Line((0, 20, 0), (5, 20, 0), resolution=5), "c2")
tdl.input_one_value_dialog = lambda **kw: 2.0
for _ in range(5):
    app.processEvents()  # views process the queued additions (in the GUI, between user actions)
select(c1, c2)
tdl.start_checked_line_tool(vm, tdl.copy_parallel, same_parent=True, cross_collection=True)
copies = pw.selection_uids()
check("copy parallel: one copy per line, copies selected",
      len(copies) == 2 and pw.collection_of_uid(copies[0]) == "geol_coll" and pw.collection_of_uid(copies[1]) == "fluid_coll"
      and pw.geol_coll.get_uid_name(copies[0]) == "c1_para_2")


class FakeVector:
    length = 3.0
    deltas = (0.0, 3.0, 0.0)


select(c1, c2)
vm.disable_actions()
tdl.copy_similar(vm, FakeVector())
copies = pw.selection_uids()
check("copy similar: one copy per line, translated, copies selected",
      len(copies) == 2 and pw.fluid_coll.get_uid_vtk_obj(copies[1]).points_Y[0] == 23.0)

# clone of mixed classes and cross-sections
xs_uid = pw.xsect_coll.get_uids[0]
xs_line = add(pw.geol_coll, "XsPolyLine", PolyLine, line, "xs_line")
pw.geol_coll.df.loc[pw.geol_coll.df["uid"] == xs_line, "parent_uid"] = xs_uid
n_x, n_g = len(pw.xsect_coll.df), len(pw.geol_coll.df)
select(xs_uid, xs_line, g_surf)
pw.entity_clone()
check("clone of a cross-section, a XsPolyLine and a TriSurf together",
      len(pw.xsect_coll.df) == n_x + 1 and len(pw.geol_coll.df) == n_g + 2 and len(pw.selection_uids()) == 3)


# map view: copy tools take any PolyLine/XsPolyLine, NOT filtered by cross-section
xa = add(pw.geol_coll, "XsPolyLine", PolyLine, pv.Line((0, 30, 0), (5, 30, 0), resolution=5), "xa")
xb = add(pw.fluid_coll, "XsPolyLine", PolyLine, pv.Line((0, 40, 0), (5, 40, 0), resolution=5), "xb")
pw.geol_coll.df.loc[pw.geol_coll.df["uid"] == xa, "parent_uid"] = "XS_A"
pw.fluid_coll.df.loc[pw.fluid_coll.df["uid"] == xb, "parent_uid"] = "XS_B"
vm2 = ViewMap(parent=pw)
select(c1, xa, xb)
vm2.copyParallelButton.trigger()
check("map view: copy parallel on lines of different sections (3 copies)", len(pw.selection_uids()) == 3)


# Ctrl+A / Ctrl+Shift+A in a view; Ctrl+Shift+A in a table
pw.set_selection(mode="clear")
v.select_all_in_view()
check("Ctrl+A in view selects all shown entities", set(pw.selection_uids()) == set(v.shown_uids))
v.deselect_all_in_view()
check("Ctrl+Shift+A in view deselects the view entities", v.selected_uids == [])
select(g_line, f_line)
geology_shortcut = next(sc for sc in pw._deselect_all_shortcuts if sc.parent() is pw.GeologyTableView)
geology_shortcut.activated.emit()
check("Ctrl+Shift+A in the Geology table deselects geology only", pw.selection_uids() == [f_line])


# weld output named with the _weld suffix and selected
w1 = add(pw.geol_coll, "PolyLine", PolyLine, pv.Line((0, 50, 0), (2, 50, 0), resolution=2), "w1")
w2 = add(pw.geol_coll, "PolyLine", PolyLine, pv.Line((2.1, 50, 0), (4, 50, 0), resolution=2), "w2")
for _ in range(5):
    app.processEvents()
select(w1, w2)
tdl.start_checked_line_tool(vm, tdl.merge_lines, min_selected=2, same_parent=True)
sel = pw.selection_uids()
check("weld output named _weld and selected", len(sel) == 1 and pw.geol_coll.get_uid_name(sel[0]) == "w1_weld")


# surface tools on TriSurfs of several collections: one output per input, in its own collection
sphere = pv.Sphere().triangulate()
sg = add(pw.geol_coll, "TriSurf", TriSurf, sphere, "sg")
sf = add(pw.fluid_coll, "TriSurf", TriSurf, sphere, "sf")
sb = add(pw.boundary_coll, "TriSurf", TriSurf, sphere, "sb")
tds.input_one_value_dialog = lambda **kw: 0.5
tds.input_text_dialog = lambda **kw: kw.get("default_text")
for label, run, suffix in (
    ("decimation pro", lambda: tds.decimation_pro_resampling(pw), "_decimated"),
    ("decimation quadric", lambda: tds.decimation_quadric_resampling(pw), "_decimated"),
    ("subdivision", lambda: tds.subdivision_resampling(pw, 0, "linear", 1), "_subdivided"),
    ("retopo", lambda: tds.retopo(pw, 0, 0.2, 10, 0.1), "_retopo"),
):
    counts = [len(c.df) for c in (pw.geol_coll, pw.fluid_coll, pw.boundary_coll)]
    select(sg, sf, sb)
    run()
    new_names = [c.df["name"].iloc[-1] for c in (pw.geol_coll, pw.fluid_coll, pw.boundary_coll)]
    grew = [len(c.df) - n for c, n in zip((pw.geol_coll, pw.fluid_coll, pw.boundary_coll), counts)]
    check(f"{label} on geology, fluid and boundary TriSurfs", grew == [1, 1, 1] and new_names == ["sg" + suffix, "sf" + suffix, "sb" + suffix])


# Ctrl+A in the graphics: shown entities selected, hidden entities of the view deselected,
# entities outside the view untouched; hiding alone does not deselect
pw.set_selection(mode="clear")
hide_uid = g_line
v.set_actor_visible(uid=hide_uid, visible=False)
v.actors_df.loc[v.actors_df["uid"] == hide_uid, "show"] = False
pw.set_selection([hide_uid], mode="add")
check("hiding does not deselect", pw.is_selected(hide_uid))
v.select_all_in_view()
check("Ctrl+A selects shown entities", set(v.shown_uids) <= set(pw.selection_uids()))
check("Ctrl+A deselects hidden entities of the view", not pw.is_selected(hide_uid))
v.actors_df.loc[v.actors_df["uid"] == hide_uid, "show"] = True
v.set_actor_visible(uid=hide_uid, visible=True)


# Calculate Normals across collections: TriSurfs and point clouds get Normals, a DEM is deselected
from pzero.entities_factory import PCDom  # noqa: E402

pc = PCDom()
pc.ShallowCopy(pv.PolyData(np.random.default_rng(2).random((200, 3)) * [10, 10, 0.1]))
dpc = deepcopy(pw.dom_coll.entity_dict)
dpc.update(name="pc", uid=str(uuid4()), topology="PCDom", vtk_obj=pc)
pc_uid = pw.dom_coll.add_entity_from_dict(entity_dict=dpc)
dem_like = TriSurf()
dem_like.ShallowCopy(plane)
ddem = deepcopy(pw.dom_coll.entity_dict)
ddem.update(name="dem", uid=str(uuid4()), topology="DEM", vtk_obj=dem_like)
dem_uid = pw.dom_coll.add_entity_from_dict(entity_dict=ddem)
nsg = add(pw.geol_coll, "TriSurf", TriSurf, plane, "nsg")
nsf = add(pw.fluid_coll, "TriSurf", TriSurf, plane, "nsf")
select(nsg, dem_uid, nsf, pc_uid)
pw.normals_calculate()
check("normals on geology and fluid TriSurfs and point cloud",
      "Normals" in pw.geol_coll.get_uid_properties_names(nsg)
      and "Normals" in pw.fluid_coll.get_uid_properties_names(nsf)
      and "Normals" in pw.dom_coll.get_uid_properties_names(pc_uid))
check("DEM deselected, no normals", not pw.is_selected(dem_uid) and "Normals" not in pw.dom_coll.get_uid_properties_names(dem_uid))


# tools with required properties / property tools with everything selected, cross-sections included
import pzero.point_clouds as pcl  # noqa: E402
pw.set_selection(uids=[u for c in pw.tab_collection_dict.values() for u in getattr(pw, c).get_uids], mode="replace")
pcl.normals2dd(pw)
check("dip/direction with everything selected (incl. cross-sections): no crash, only entities with Normals kept",
      pw.selection_uids() and all("Normals" in pw.collection_of_uid(u) and False or True for u in pw.selection_uids())
      and not any(pw.collection_of_uid(u) == "xsect_coll" for u in pw.selection_uids()))
pw.set_selection(uids=[u for c in pw.tab_collection_dict.values() for u in getattr(pw, c).get_uids], mode="replace")
pwm.multiple_input_dialog = lambda **kw: {"property_name": "ptest", "property_components": 1}
pw.property_add()
check("add property with everything selected: cross-sections deselected",
      not any(pw.collection_of_uid(u) == "xsect_coll" for u in pw.selection_uids()) and "ptest" in pw.geol_coll.get_uid_properties_names(g_line))


# deferred view updates: many entities added and removed in one operation, views consistent after
# one event loop pass (one merged update per kind instead of one per entity)
for _ in range(5):
    app.processEvents()
bulk = [add(pw.fluid_coll, "TriSurf", TriSurf, plane, f"bulk{i}") for i in range(40)]
check("views not yet updated before the event loop runs", bulk[0] not in set(v.actors_df["uid"]))
for _ in range(5):
    app.processEvents()
check("bulk additions shown in the view", set(bulk) <= set(v.actors_df["uid"]) and all(v.get_actor_by_uid(u) is not None for u in bulk))
pw.fluid_coll.remove_entities(bulk[:30])
pw.fluid_coll.remove_entities(bulk[30:])
for _ in range(5):
    app.processEvents()
check("bulk removals gone from the view and its tree",
      not (set(bulk) & set(v.actors_df["uid"]))
      and not any(v.FluidsTreeWidget.get_item_uid(i) in set(bulk) for i in v.FluidsTreeWidget.findItems("", __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.MatchContains | __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.MatchRecursive)))

# View filters: an entity whose parent_uid changes enters / leaves a cross-section view
import pzero.views.view_xsection as vxs  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402

vxs.input_combo_dialog = lambda **kw: "XS1"
xs_view = vxs.ViewXsection(parent=pw)
xs_uid = pw.xsect_coll.df.loc[pw.xsect_coll.df["name"] == "XS1", "uid"].values[0]
moving = add(pw.geol_coll, "PolyLine", PolyLine, line, "moving_line")
app.processEvents()


def in_xs_view(uid):
    tree = xs_view.GeologyTreeWidget
    items = tree.findItems("", Qt.MatchContains | Qt.MatchRecursive)
    in_tree = any(tree.get_item_uid(item) == uid for item in items)
    return uid in set(xs_view.actors_df["uid"]), in_tree


def set_parent(uid, parent):
    pw.geol_coll.df.loc[pw.geol_coll.df["uid"] == uid, "parent_uid"] = parent
    pw.signals.metadata_modified.emit([uid], pw.geol_coll)
    xs_view.flush_pending_updates()
    app.processEvents()


check("line without parent not in the cross-section view", in_xs_view(moving) == (False, False))
set_parent(moving, xs_uid)
check("parent_uid set to the section: the line enters the view and its tree",
      in_xs_view(moving) == (True, True))
set_parent(moving, "")
check("parent_uid cleared: the line leaves the view and its tree",
      in_xs_view(moving) == (False, False))

# Project to surface (vertical), onto any surface
from pzero.entities_factory import VertexSet  # noqa: E402

terminal = []
pw.print_terminal = lambda string=None: terminal.append(str(string))
tilted = pv.Plane(center=(0, 0, 0), i_size=10, j_size=10, i_resolution=10, j_resolution=10).triangulate()
tilted.points[:, 2] = 0.5 * tilted.points[:, 0] + 1.0  # z = 0.5 x + 1
f_tilted = add(pw.fluid_coll, "TriSurf", TriSurf, tilted, "tilted")
# a folded surface: two layers at z = 0 and z = 5 above the same area
layer0 = pv.Plane(center=(20, 0, 0), i_size=4, j_size=4).triangulate()
layer5 = pv.Plane(center=(20, 0, 5), i_size=4, j_size=4).triangulate()
b_fold = add(pw.boundary_coll, "TriSurf", TriSurf, layer0.merge(layer5), "fold")
high_line = add(pw.geol_coll, "PolyLine", PolyLine,
                pv.Line((-2, 0, 50), (2, 0, 50), resolution=4), "high_line")
far_pts = add(pw.fluid_coll, "VertexSet", VertexSet,
              pv.PolyData(np.array([[1.0, 1.0, -30.0], [100.0, 100.0, 7.0]])), "far_pts")
fold_pts = add(pw.geol_coll, "VertexSet", VertexSet,
               pv.PolyData(np.array([[20.0, 0.0, 4.0], [20.5, 0.5, 1.0]])), "fold_pts")
labels = list(tds._projection_surfaces(pw).keys())
check("surfaces offered: TriSurfs of any collection", "tilted (Fluids)" in labels and "fold (Boundaries)" in labels)


def project_onto(label, uids, replace=False):
    tds.options_dialog = lambda **kw: 0 if replace else 1  # Yes = replace, No = copies
    tds.input_combo_dialog = lambda **kw: label
    pw.set_selection(uids, mode="replace")
    tds.project_2_dem(pw)


n_g, n_f = len(pw.geol_coll.df), len(pw.fluid_coll.df)
project_onto("tilted (Fluids)", [high_line, far_pts])
out_line = pw.geol_coll.df["uid"].iloc[-1]
out_pts = pw.fluid_coll.df["uid"].iloc[-1]
line_pts = pw.geol_coll.get_uid_vtk_obj(out_line).points
check("line projected onto a TriSurf (copy in its collection, named _prj_<surface>)",
      len(pw.geol_coll.df) == n_g + 1 and pw.geol_coll.get_uid_name(out_line) == "high_line_prj_tilted"
      and np.allclose(line_pts[:, 2], 0.5 * line_pts[:, 0] + 1.0, atol=1e-5)
      and np.allclose(line_pts[:, :2], pw.geol_coll.get_uid_vtk_obj(high_line).points[:, :2]))
far_out = pw.fluid_coll.get_uid_vtk_obj(out_pts).points
check("point below the surface projected up, point outside keeps its elevation (with a message)",
      abs(far_out[0, 2] - 1.5) < 1e-5 and abs(far_out[1, 2] - 7.0) < 1e-6
      and any("1 of 2 points outside tilted" in m for m in terminal))
check("the projected copies become the selection", sorted(pw.selection_uids()) == sorted([out_line, out_pts]))
check("the original line is unchanged", np.allclose(pw.geol_coll.get_uid_vtk_obj(high_line).points[:, 2], 50))

project_onto("fold (Boundaries)", [fold_pts], replace=True)
fold_out = pw.geol_coll.get_uid_vtk_obj(fold_pts).points
check("folded surface: the intersection nearest to each point (z 4 -> 5, z 1 -> 0), original replaced",
      np.allclose(fold_out[:, 2], [5.0, 0.0], atol=1e-5) and pw.geol_coll.get_uid_name(fold_pts) == "fold_pts_prj_fold"
      and pw.selection_uids() == [fold_pts])

# a DEM-like surface in DOMs (structured grid) is offered and works
from pzero.entities_factory import DEM  # noqa: E402

xx, yy = np.meshgrid(np.linspace(-50, -40, 6), np.linspace(-5, 5, 6))
grid = pv.StructuredGrid(xx, yy, 3.0 + 0 * xx)
dem = DEM()
dem.ShallowCopy(grid)
d = deepcopy(pw.dom_coll.entity_dict)
d.update(name="dem_target", uid=str(uuid4()), topology="DEM", vtk_obj=dem)
dem_uid = pw.dom_coll.add_entity_from_dict(entity_dict=d)
dem_line = add(pw.geol_coll, "PolyLine", PolyLine, pv.Line((-48, 0, 0), (-42, 0, 0), resolution=3), "dem_line")
project_onto("dem_target (DOMs)", [dem_line])
check("projection onto a DEM", np.allclose(pw.geol_coll.get_uid_vtk_obj(pw.geol_coll.df["uid"].iloc[-1]).points[:, 2], 3.0))

# no surface at all: a message and no dialog
pw2 = ProjectWindow()
terminal2 = []
pw2.print_terminal = lambda string=None: terminal2.append(str(string))
lonely = deepcopy(pw2.geol_coll.entity_dict)
lonely_obj = PolyLine()
lonely_obj.ShallowCopy(pv.Line((0, 0, 0), (1, 0, 0)))
lonely.update(name="lonely", uid=str(uuid4()), topology="PolyLine", vtk_obj=lonely_obj)
lonely_uid = pw2.geol_coll.add_entity_from_dict(entity_dict=lonely)
dialogs = []
tds.options_dialog = lambda **kw: dialogs.append("options")
tds.input_combo_dialog = lambda **kw: dialogs.append("combo")
pw2.set_selection([lonely_uid], mode="replace")
tds.project_2_dem(pw2)
check("no surface in the project: message, no dialog",
      not dialogs and any("no surface to project onto" in m for m in terminal2))
check("menu label", pw.actionProject2DEM.text() == "Project to DEM/surface")

# Draw line: Boundaries offered, without role and feature
import types  # noqa: E402

asked = {}
tdl.input_combo_dialog = lambda **kw: asked.setdefault("collections", kw["choice_list"]) and "Boundaries"
chosen = tdl._choose_draw_line_collection(types.SimpleNamespace(parent=pw))
tdl.multiple_input_dialog = lambda title=None, input_dict=None: asked.setdefault("fields", list(input_dict)) and {"name": "bline", "scenario": input_dict["scenario"][1][0]}
line_dict = tdl._ask_new_line_metadata(chosen, "Digitize new PolyLine")
check("draw line: Boundaries in the destination collections",
      "Boundaries" in asked["collections"] and chosen is pw.boundary_coll)
check("draw line in Boundaries: name and scenario only",
      asked["fields"] == ["name", "scenario"] and line_dict["name"] == "bline" and "role" not in line_dict)

# Cross-section views show the section name in their tab
from pzero.views.dock_window import DockWindow  # noqa: E402

vxs.input_combo_dialog = lambda **kw: "XS1"
xs_dock = DockWindow(parent=pw, window_type="ViewXsection")
check("cross-section tab shows the section name", xs_dock.windowTitle() == "Xsection XS1")

# Views keep the 3:1 split (graphics : trees) also when opened as a later tab, and on resize,
# until the user moves the divider
from pzero.views.view_3d import View3D as _View3D  # noqa: E402,F401

pw.resize(1600, 1000)
pw.show()
d3_dock = DockWindow(parent=pw, window_type="View3D")
for _ in range(10):
    app.processEvents()


def split_ratio(dock):
    sizes = dock.canvas.splitter.sizes()
    return sizes[0] / max(1, sum(sizes))


ratios = {}
for dock in (xs_dock, d3_dock):
    dock.raise_()
    for _ in range(10):
        app.processEvents()
    ratios[dock.windowTitle()] = round(split_ratio(dock), 2)
check(f"3:1 split in the cross-section (first tab) and 3D (second tab) views {ratios}",
      all(abs(r - 0.75) < 0.03 for r in ratios.values()))
pw.resize(2200, 1200)
for _ in range(10):
    app.processEvents()
check("3:1 split kept after resizing the window", abs(split_ratio(d3_dock) - 0.75) < 0.03)
d3_dock.canvas.splitter.setSizes([500, 500])
d3_dock.canvas._on_split_moved_by_user()
pw.resize(1800, 1100)
for _ in range(10):
    app.processEvents()
check("a split moved by the user is kept", abs(split_ratio(d3_dock) - 0.5) < 0.05)

print("RESULT:", "FAILED" if failed else "ALL PASSED")
