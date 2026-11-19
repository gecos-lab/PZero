"""Headless check: converted tools work on any collection (output in the same collection)."""
import os
import sys
from copy import deepcopy
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))

from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)
import numpy as np  # noqa: E402
import pyvista as pv  # noqa: E402
from pzero.project_window import ProjectWindow  # noqa: E402
from pzero.entities_factory import TriSurf, PolyLine, VertexSet  # noqa: E402
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
    if "role" in d:
        d["role"] = coll.valid_roles[0] if coll.valid_roles else d["role"]
    obj = cls()
    obj.ShallowCopy(mesh)
    d["vtk_obj"] = obj
    return coll.add_entity_from_dict(entity_dict=d)


def select(*uids):
    pw.set_selection(mode="clear")
    for u in uids:
        pw.set_selection([u], mode="add")


plane = pv.Plane(i_resolution=6, j_resolution=6).triangulate()
f_surf = add(pw.fluid_coll, "TriSurf", TriSurf, plane, "fluid_surf")
b_surf = add(pw.boundary_coll, "TriSurf", TriSurf, plane, "bound_surf")
g_line = add(pw.geol_coll, "PolyLine", PolyLine, pv.Line((0, 0, 0), (1, 0, 0), resolution=3), "geol_line")
pts = pv.PolyData(np.random.default_rng(0).random((30, 3)) * [1, 1, 0.01])
f_pts = add(pw.fluid_coll, "VertexSet", VertexSet, pts, "fluid_pts")

# surface smoothing on a fluid TriSurf, with a geology line also selected
n_fluid = len(pw.fluid_coll.df)
select(g_line, f_surf)
tds.surface_smoothing(pw)
check("smoothing ran on fluid TriSurf, output in fluids", len(pw.fluid_coll.df) == n_fluid + 1)
check("smoothed name derived", pw.fluid_coll.df["name"].iloc[-1] == "fluid_surf_smoothed")
check("geology line deselected", pw.selection_uids() == [f_surf])
check("fluids tab in front", pw.shown_table == "tabFluids")

# smoothing on a boundary TriSurf (no role/feature in the schema)
n_b = len(pw.boundary_coll.df)
select(b_surf)
tds.surface_smoothing(pw)
check("smoothing ran on boundary TriSurf", len(pw.boundary_coll.df) == n_b + 1)

# Delaunay 2D on fluid points (dialogs stubbed)
tds.multiple_input_dialog = lambda title=None, input_dict=None: {k: (v[2] if len(v) > 2 else (v[1][0] if isinstance(v[1], list) else v[1])) for k, v in input_dict.items()}
tds.input_one_value_dialog = lambda **kw: 0
n_fluid = len(pw.fluid_coll.df)
select(f_pts)
tds.interpolation_delaunay_2d(pw)
check("delaunay on fluid points, output in fluids", len(pw.fluid_coll.df) == n_fluid + 1 and pw.fluid_coll.df["topology"].iloc[-1] == "TriSurf")

# connected parts on a boundary surface
select(b_surf)
pw.connected_parts()
check("connected parts on boundary", "RegionId" in pw.boundary_coll.get_uid_properties_names(b_surf))

# merge needs at least 2 entities: a TriSurf alone is not enough -> tool does not run, selection kept
select(f_surf)
pw.entities_merge()
check("merge refuses a single entity", pw.selection_uids() == [f_surf])

# merge of two fluid lines (dialogs stubbed)
l1 = add(pw.fluid_coll, "PolyLine", PolyLine, pv.Line((0, 0, 0), (1, 0, 0), resolution=2), "fl1")
l2 = add(pw.fluid_coll, "PolyLine", PolyLine, pv.Line((0, 1, 0), (1, 1, 0), resolution=2), "fl2")
pwm.multiple_input_dialog = lambda title=None, input_dict=None: {k: v[1][0] for k, v in input_dict.items()}
pwm.options_dialog = lambda **kw: 0
n_fluid = len(pw.fluid_coll.df)
select(l1, f_surf, l2)
pw.entities_merge()
check("merge of fluid lines, output in fluids", len(pw.fluid_coll.df) == n_fluid + 1)
merged_uid = pw.fluid_coll.df["uid"].iloc[-1]
check("merged line is PolyLine and selected", pw.fluid_coll.get_uid_topology(merged_uid) == "PolyLine" and pw.selection_uids() == [merged_uid])

# merge of two TriSurfs (any PolyData topology)
s2 = add(pw.fluid_coll, "TriSurf", TriSurf, plane, "fluid_surf_2")
n_fluid = len(pw.fluid_coll.df)
select(f_surf, s2)
pw.entities_merge()
check("merge of two TriSurfs", len(pw.fluid_coll.df) == n_fluid + 1 and pw.fluid_coll.df["topology"].iloc[-1] == "TriSurf")


# smoothing / subdivision / retopo preview window on a fluid TriSurf (not only geology)
from PySide6.QtWidgets import QMainWindow  # noqa: E402
from pzero.helpers.helper_dialogs import PreviewWidget  # noqa: E402

select(f_surf)
preview = PreviewWidget.__new__(PreviewWidget)
QMainWindow.__init__(preview)
preview.setupUi(preview)
preview.parent = pw
preview.title1, preview.title2 = "a", "b"
preview.initialize_interactor()
check("preview window loads a fluid TriSurf", preview.mesh is pw.fluid_coll.get_uid_vtk_obj(f_surf))
preview.preview_plotter.close()


# smoothing parameters exposed in the dialog: the preview passes the dialog values positionally
import numpy as np  # noqa: E402
from PySide6.QtWidgets import QLineEdit, QCheckBox  # noqa: E402
from pzero.helpers.helper_dialogs import multiple_input_dialog as real_dialog  # noqa: E402

rng = np.random.default_rng(0)
noisy = pv.Plane(i_resolution=30, j_resolution=30).triangulate()
noisy.points[:, 2] += rng.normal(0, 0.02, noisy.n_points)
n_uid = add(pw.fluid_coll, "TriSurf", TriSurf, noisy, "noisy")
captured = {}
pwm.multiple_input_dialog = lambda **kw: captured.setdefault("w", real_dialog(**kw))
pwm.PreviewWidget = lambda **kw: captured.setdefault("kw", kw)
select(n_uid)
pw.smooth_dialog()
params = []
for child in captured["w"].children():
    if child.objectName():
        params.append(child.text() if isinstance(child, QLineEdit) else child.isChecked() if isinstance(child, QCheckBox) else None)
check("smoothing dialog fields in parameter order", params == ["20", "0.5", "0.0", True, False])
smoothed = captured["kw"]["function"](pw, 1, *params)
z_in = np.std(noisy.points[:, 2])
z_out = np.std(pv.wrap(smoothed).points[:, 2])
check("smoothing with dialog defaults reduces noise clearly (>40%)", z_out < 0.6 * z_in)

print("RESULT:", "FAILED" if failed else "ALL PASSED")
