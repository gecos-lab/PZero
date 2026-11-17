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

# B/A: intersection of a fluid line and a geology surface together
n_g, n_f = len(pw.geol_coll.df), len(pw.fluid_coll.df)
select(f_line, g_surf)
tds.intersection_xs(pw)
check("intersection outputs in fluids and geology",
      pw.fluid_coll.df["topology"].iloc[-1] == "XsVertexSet" and len(pw.fluid_coll.df) == n_f + 1
      and pw.geol_coll.df["topology"].iloc[-1] == "XsPolyLine" and len(pw.geol_coll.df) == n_g + 1)

print("RESULT:", "FAILED" if failed else "ALL PASSED")
