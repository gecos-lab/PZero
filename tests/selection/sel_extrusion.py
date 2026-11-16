"""Headless check: single Extrusion tool in View3D > Create, optional densification."""
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
from pzero.entities_factory import PolyLine  # noqa: E402
import pzero.three_d_surfaces as tds  # noqa: E402

pw = ProjectWindow()
failed = False


def check(label, cond):
    global failed
    print(("PASS " if cond else "FAIL ") + label)
    failed |= not cond


d = deepcopy(pw.fluid_coll.entity_dict)
line = PolyLine()
line.ShallowCopy(pv.Line((0, 0, 0), (100, 0, 0), resolution=10))
d.update(name="fl", uid=str(uuid4()), topology="PolyLine", vtk_obj=line, role=pw.fluid_coll.valid_roles[0])
line_uid = pw.fluid_coll.add_entity_from_dict(entity_dict=d)

from pzero.views.view_3d import View3D  # noqa: E402

v = View3D(parent=pw)
check("Extrusion in View3D Create menu", "Extrusion" in [a.text() for a in v.menuCreate.actions()])
check("no extrusion in project Projection menu", not any("xtrusion" in a.text() for a in pw.menuProjection.actions()))
check("enhanced extrusion removed", not hasattr(tds, "enhanced_linear_extrusion"))

DENSIFY = {"value": False}


def fake_dialog(title=None, input_dict=None):
    out = {}
    for k, val in input_dict.items():
        default = val[1]
        if isinstance(default, list):
            default = val[2] if len(val) > 2 else default[0]
        out[k] = default
    if "densify" in out:
        out["densify"] = DENSIFY["value"]
        out["sample_lines"] = 4
    return out


tds.multiple_input_dialog = fake_dialog

pw.set_selection(mode="clear")
pw.set_selection([line_uid], mode="add")
n = len(pw.fluid_coll.df)
v.actionExtrusion.trigger()
check("simple extrusion -> TriSurf in fluids", len(pw.fluid_coll.df) == n + 1 and pw.fluid_coll.df["topology"].iloc[-1] == "TriSurf")
simple_uid = pw.fluid_coll.df["uid"].iloc[-1]
check("simple extrusion name", pw.fluid_coll.get_uid_name(simple_uid) == "fl_extruded")

DENSIFY["value"] = True
pw.set_selection(mode="clear")
pw.set_selection([line_uid], mode="add")
v.actionExtrusion.trigger()
dense_uid = pw.fluid_coll.df["uid"].iloc[-1]
check("densified extrusion created", len(pw.fluid_coll.df) == n + 2 and pw.fluid_coll.get_uid_name(dense_uid) == "fl_densified_extruded")
check(
    "densified has more points",
    pw.fluid_coll.get_uid_vtk_obj(dense_uid).GetNumberOfPoints() > pw.fluid_coll.get_uid_vtk_obj(simple_uid).GetNumberOfPoints(),
)

print("RESULT:", "FAILED" if failed else "ALL PASSED")
