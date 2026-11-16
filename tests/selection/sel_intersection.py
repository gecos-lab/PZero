"""Headless check: intersection with cross-section on any collection (PolyLine, TriSurf, DEM, TSDom, Voxet)."""
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
from pzero.entities_factory import PolyLine, TriSurf, VertexSet  # noqa: E402
import pzero.three_d_surfaces as tds  # noqa: E402

pw = ProjectWindow()
failed = False
messages = []
pw.print_terminal = lambda string=None: messages.append(str(string))


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


# vertical N-S cross-section through x = 0.2
xs = deepcopy(pw.xsect_coll.entity_dict)
xs.update(name="XS1", origin_x=0.2, origin_y=-2.0, origin_z=-2.0, strike=0.0, dip=90.0, length=4.0, height=4.0)
xs_uid = pw.xsect_coll.add_entity_from_dict(entity_dict=xs)

plane = pv.Plane(i_resolution=8, j_resolution=8).triangulate()  # horizontal, x and y in [-0.5, 0.5]
line = pv.Line((-0.5, 0.1, 0.0), (0.5, 0.1, 0.0), resolution=8)
b_surf = add(pw.boundary_coll, "TriSurf", TriSurf, plane, "bsurf")
b_line = add(pw.boundary_coll, "PolyLine", PolyLine, line, "bline")
f_line = add(pw.fluid_coll, "PolyLine", PolyLine, line, "fline")
f_pts = add(pw.fluid_coll, "VertexSet", VertexSet, pv.PolyData([[0.2, 0, 0]]), "fpts")

tds.input_checkbox_dialog = lambda **kw: ["XS1"]


def select(*uids):
    pw.set_selection(mode="clear")
    for u in uids:
        pw.set_selection([u], mode="add")


n_b = len(pw.boundary_coll.df)
select(b_surf, b_line)
tds.intersection_xs(pw)
new_b = pw.boundary_coll.df.iloc[n_b:]
check("boundary TriSurf -> XsPolyLine in boundaries", list(new_b["topology"]) == ["XsPolyLine"])
check("output named with section", list(new_b["name"]) == ["bsurf_int_XS1"])
check("boundary line skipped with message", any("cannot be stored in Boundaries" in m for m in messages))

n_f = len(pw.fluid_coll.df)
select(f_line, f_pts)
tds.intersection_xs(pw)
new_f = pw.fluid_coll.df.iloc[n_f:]
check("fluid PolyLine -> XsVertexSet in fluids", list(new_f["topology"]) == ["XsVertexSet"])
check("points not accepted (deselected)", not pw.is_selected(f_pts))


# projection of a boundary line to the cross-section -> XsPolyLine in boundaries
tds.general_input_dialog = lambda **kw: {"dist_sec": 0.0, "proj_plunge": 0.0, "proj_trend": 90.0, "filter_polyline_geometry": ""}
n_b = len(pw.boundary_coll.df)
select(b_line)
tds.project_2_xs(pw)
new_b = pw.boundary_coll.df.iloc[n_b:]
check("boundary line projected to XS -> XsPolyLine in boundaries", list(new_b["topology"]) == ["XsPolyLine"] and list(new_b["name"]) == ["bline_prj_XS1"])

# TetraSolid placeholder: accepted, message, no output
from pzero.entities_factory import TetraSolid
tet = pv.ImageData(dimensions=(3, 3, 3)).cast_to_unstructured_grid().triangulate()
t_uid = add(pw.mesh3d_coll, "TetraSolid", TetraSolid, tet, "tet")
n_m = len(pw.mesh3d_coll.df)
messages.clear()
select(t_uid)
tds.intersection_xs(pw)
check("TetraSolid placeholder message, no output", any("TetraSolid meshes is not implemented yet" in m for m in messages) and len(pw.mesh3d_coll.df) == n_m)

print("RESULT:", "FAILED" if failed else "ALL PASSED")
