"""Headless check of phase 4: VTK highlight follows the project selection."""
import os
import sys
from copy import deepcopy
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))

from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)
import pyvista as pv  # noqa: E402
from pzero.project_window import ProjectWindow  # noqa: E402
from pzero.entities_factory import TriSurf, PolyLine  # noqa: E402

pw = ProjectWindow()


def add_entity(topology, cls, pv_mesh, name):
    d = deepcopy(pw.geol_coll.entity_dict)
    d.update(name=name, uid=str(uuid4()), topology=topology, role="fault", feature=name)
    obj = cls()
    obj.ShallowCopy(pv_mesh)
    d["vtk_obj"] = obj
    return pw.geol_coll.add_entity_from_dict(entity_dict=d)


surf_uid = add_entity("TriSurf", TriSurf, pv.Sphere().triangulate(), "surf")
plane_uid = add_entity("TriSurf", TriSurf, pv.Plane(i_resolution=4, j_resolution=4).triangulate(), "plane")
line_uid = add_entity("PolyLine", PolyLine, pv.Line((0, 0, 0), (1, 1, 1), resolution=5), "line")
line2_uid = add_entity("PolyLine", PolyLine, pv.Line((0, 0, 1), (1, 1, 2), resolution=5), "line2")

from pzero.views.view_3d import View3D  # noqa: E402

v1 = View3D(parent=pw)
v2 = View3D(parent=pw)
failed = False


def check(label, cond):
    global failed
    print(("PASS " if cond else "FAIL ") + label)
    failed |= not cond


def flush():
    for _ in range(3):
        app.processEvents()


def prop(view, uid):
    return view.get_actor_by_uid(uid).GetProperty()


check("wrapper installed on View3D", getattr(View3D.show_actor_with_property, "_highlight_aware", False))
orig_lw_line = prop(v1, line_uid).GetLineWidth()
orig_color_line = prop(v1, line_uid).GetColor()
n_actors = len(v1.plotter.renderer.actors)

# select from the store (e.g. a tree) -> both views highlight, no extra actors
pw.geol_coll.selected_uids = [surf_uid, line_uid]
flush()
for name, v in (("v1", v1), ("v2", v2)):
    check(f"{name} surface edges on", prop(v, surf_uid).GetEdgeVisibility() == 1)
    check(f"{name} line yellow", tuple(round(c, 3) for c in prop(v, line_uid).GetColor()) == (1.0, 1.0, 0.0))
check("no extra actors for property highlight", len(v1.plotter.renderer.actors) == n_actors)
check("view selected_uids", sorted(v1.selected_uids) == sorted([surf_uid, line_uid]))

# legend change while selected: applies to base style, highlight kept
pw.geol_coll.selected_uids = [line_uid]
flush()
check("surface unhighlighted", prop(v1, surf_uid).GetEdgeVisibility() == 0)
v1.change_actor_line_thick(updated_uids=[line_uid], collection=pw.geol_coll)
check("line still highlighted after legend change", tuple(round(c, 3) for c in prop(v1, line_uid).GetColor()) == (1.0, 1.0, 0.0))

# deselect -> original style restored
pw.set_selection(mode="clear")
flush()
legend_lw = pw.geol_coll.get_uid_legend(uid=line_uid)["line_thick"]
check("line color restored", prop(v1, line_uid).GetColor() == orig_color_line)
check("line width restored to legend value", prop(v1, line_uid).GetLineWidth() == legend_lw)
check("highlight records empty", not v1._highlighted and not v2._highlighted)

# actor recreation while selected keeps highlight
pw.geol_coll.selected_uids = [surf_uid]
flush()
v1.show_actor_with_property(uid=surf_uid, coll_name="geol_coll", show_property=None, visible=True)
check("recreated actor highlighted", prop(v1, surf_uid).GetEdgeVisibility() == 1)

# view clear_selection -> store and other view
v1.clear_selection()
flush()
check("clear_selection -> store", pw.selection_uids() == [])
check("other view unhighlighted", prop(v2, surf_uid).GetEdgeVisibility() == 0)

# hide selected entity: stays selected
pw.geol_coll.selected_uids = [surf_uid]
flush()
v1.set_actor_visible(uid=surf_uid, visible=False)
check("hidden entity stays selected", pw.is_selected(surf_uid))

# a new view shows the existing selection
v3 = View3D(parent=pw)
flush()
check("new view highlights existing selection", prop(v3, surf_uid).GetEdgeVisibility() == 1)


# open surface -> yellow border line (outline actor), not edges
pw.set_selection(mode="clear")
pw.geol_coll.selected_uids = [plane_uid]
flush()
silh = v1.plotter.renderer.actors.get(f"{plane_uid}_silh")
check("open surface gets border outline", silh is not None and silh.GetMapper().GetInput().GetNumberOfLines() == 16)
check("open surface edges untouched", prop(v1, plane_uid).GetEdgeVisibility() == 0)
pw.set_selection(mode="clear")
flush()
check("border outline removed on deselect", f"{plane_uid}_silh" not in v1.plotter.renderer.actors)

# line tool with a line and a surface selected: surface ignored, selection unchanged
from pzero.two_d_lines import start_checked_line_tool
pw.tabWidgetTopLeft.setCurrentWidget(pw.tabGeology)
pw.geol_coll.selected_uids = [plane_uid, line_uid]
seen = []
start_checked_line_tool(v1, lambda view: seen.append(view.selected_uids), max_selected=1)
check("line tool sees only the line", seen == [[line_uid]])
check("non-line entity deselected", pw.selection_uids() == [line_uid])
pw.set_selection(mode="clear")
pw.geol_coll.selected_uids = [line2_uid, plane_uid, line_uid]
seen = []
start_checked_line_tool(v1, lambda view: seen.append(view.selected_uids), max_selected=1)
check("single-line tool takes the last selected line", seen == [[line_uid]])
check("only the last line stays selected", pw.selection_uids() == [line_uid])
pw.set_selection(mode="clear")
pw.geol_coll.selected_uids = [line2_uid, plane_uid, line_uid]
seen = []
start_checked_line_tool(v1, lambda view: seen.append(view.selected_uids))
check("multi-line tool keeps all lines in click order", seen == [[line2_uid, line_uid]])
check("multi-line tool deselects non-lines", pw.selection_uids() == [line2_uid, line_uid])
pw.geol_coll.selected_uids = [plane_uid, line_uid]

# freeze: user selection in tables/trees blocked while a tool runs
from PySide6.QtCore import QItemSelectionModel as QISM
from PySide6.QtWidgets import QAbstractItemView
v1.disable_actions()
check("table frozen", pw.GeologyTableView.selectionMode() == QAbstractItemView.NoSelection)
check("tree frozen", v1.GeologyTreeWidget.selectionMode() == QAbstractItemView.NoSelection)
pw.GeologyTableView.selectionModel().select(pw.GeologyTableView.model().index(0, 0), QISM.ClearAndSelect | QISM.Rows)
check("table change undone while frozen", sorted(pw.selection_uids()) == sorted([plane_uid, line_uid]))
pw.set_selection([line_uid], mode="remove", source=v1)
check("tools can still change selection", pw.selection_uids() == [plane_uid])
v1.enable_actions()
check("table unfrozen", pw.GeologyTableView.selectionMode() != QAbstractItemView.NoSelection)
check("tree unfrozen", v1.GeologyTreeWidget.selectionMode() == QAbstractItemView.ExtendedSelection)

# removing the entity prunes and cleans up
pw.geol_coll.remove_entities([surf_uid])
flush()
check("removed entity pruned", not pw.is_selected(surf_uid) and surf_uid not in v1._highlighted)

# Normals shown as RGB in a 3D view: still shown after Calculate Normals / Dip/Direction
# (3-component properties are in the property legend only per component, e.g. Normals[0])
import io  # noqa: E402
import contextlib  # noqa: E402
import pzero.orientation_analysis as oa  # noqa: E402
from pzero.point_clouds import normals2dd  # noqa: E402

nsurf_uid = add_entity("TriSurf", TriSurf, pv.Sphere().triangulate(), "nsurf")
flush()
terminal = []
pw.print_terminal = lambda string=None: terminal.append(str(string))
pw.set_selection([nsurf_uid], mode="replace")
oa.set_normals(pw)
flush()


def normals_shown(view):
    mapper = view.get_actor_by_uid(nsurf_uid).GetMapper()
    row = view.actors_df.loc[view.actors_df["uid"] == nsurf_uid]
    return (row["show_property"].values[0] == "Normals" and mapper.GetScalarVisibility()
            and mapper.GetArrayName() == "Normals")


stderr = io.StringIO()
with contextlib.redirect_stderr(stderr):
    v1.toggle_property(collection_name="geol_coll", uid=nsurf_uid, prop_text="Normals")
    flush()
    shown_first = normals_shown(v1)
    pw.set_selection([nsurf_uid], mode="replace")
    oa.set_normals(pw)
    v1.flush_pending_updates()
    flush()
    shown_after_normals = normals_shown(v1)
    normals2dd(pw)
    v1.flush_pending_updates()
    flush()
    shown_after_dip = normals_shown(v1)
    pw.set_selection([nsurf_uid], mode="replace")
    oa.invert_polarity(pw)
    v1.flush_pending_updates()
    flush()
    shown_after_invert = normals_shown(v1)
check("Normals shown as RGB colors (no legend row 'Normals')", shown_first)
check("still shown after Calculate Normals", shown_after_normals)
check("still shown after Calculate Dip/Direction", shown_after_dip)
check("still shown after Invert polarity", shown_after_invert)
check("no traceback while redrawing", "Traceback" not in stderr.getvalue())
check("Calculate Dip/Direction reports in the terminal",
      any("Dip/direction set on nsurf" in m for m in terminal) and "All dip/directions set." in terminal)

import numpy as np  # noqa: E402

# several TriSurfs showing a component (Normals[2]): Invert normals, then Calculate Dip/Direction
# (which adds properties) keep it shown, in the actor and in the tree
comp_uids = [add_entity("TriSurf", TriSurf, pv.Sphere(center=(3 * i, 0, 0)).triangulate(), f"comp{i}")
             for i in range(3)]
flush()
pw.set_selection(comp_uids, mode="replace")
oa.set_normals(pw)
v1.flush_pending_updates()
flush()
for u in comp_uids:
    v1.toggle_property(collection_name="geol_coll", uid=u, prop_text="Normals[2]")
flush()


def component_shown(u):
    actor = v1.get_actor_by_uid(u)
    row = v1.actors_df.loc[v1.actors_df["uid"] == u]
    return row["show_property"].values[0] == "Normals[2]" and bool(actor.GetMapper().GetScalarVisibility())


def mapped_z(u):
    # the scalar values the actor shows (the z component of the normals)
    mapper = v1.get_actor_by_uid(u).GetMapper()
    data = mapper.GetInput().GetPointData()
    arr = data.GetArray(mapper.GetArrayName()) if mapper.GetArrayName() else data.GetScalars()
    return float(np.mean([arr.GetTuple1(i) for i in range(arr.GetNumberOfTuples())]))


check("Normals[2] shown on three TriSurfs", all(component_shown(u) for u in comp_uids))
z_before = [mapped_z(u) for u in comp_uids]
stderr = io.StringIO()
with contextlib.redirect_stderr(stderr):
    pw.set_selection(comp_uids, mode="replace")
    oa.invert_polarity(pw)
    v1.flush_pending_updates()
    flush()
check("after Invert normals Normals[2] still shown on all of them", all(component_shown(u) for u in comp_uids))
check("... with the inverted values", all(abs(mapped_z(u) + zb) < 1e-6 for u, zb in zip(comp_uids, z_before)))
with contextlib.redirect_stderr(stderr):
    pw.set_selection(comp_uids, mode="replace")
    normals2dd(pw)  # adds dip and dip direction: data_keys_added
    v1.flush_pending_updates()
    flush()
check("after Calculate Dip/Direction (new properties) Normals[2] still shown",
      all(component_shown(u) for u in comp_uids))
check("no traceback", "Traceback" not in stderr.getvalue())

print("RESULT:", "FAILED" if failed else "ALL PASSED")
