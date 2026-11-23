"""Headless check: orientation property names follow the convention (Normals, Dip, Direction;
Lineations, Plunge, Trend). Projects saved with older names are converted when opened; importers
and tools write the canonical names."""
import os
import sys
import tempfile
from copy import deepcopy
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))

from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pyvista as pv  # noqa: E402
import pzero.project_window as pwm  # noqa: E402
from pzero.project_window import ProjectWindow  # noqa: E402
from pzero.entities_factory import Attitude, TriSurf, VertexSet  # noqa: E402
from pzero.orientation_analysis import (  # noqa: E402
    find_orientation_property,
    orientation_name_map,
    plunge_trends2lineations,
)
from pzero.imports.xyz2vtk import _build_tabular_vtk_object  # noqa: E402

failed = False


def check(label, cond):
    global failed
    print(("PASS " if cond else "FAIL ") + label)
    failed |= not cond


# ---- alias rules
check("dip direction, dip_dir, dipdir, Dip Direction -> Direction",
      all(orientation_name_map(["dip", name]).get(name) == "Direction"
          for name in ("dip direction", "dip_dir", "dipdir", "Dip Direction", "dip azimuth")))
check("dip, DIP -> Dip; plunge -> Plunge; trend, plunge azimuth -> Trend",
      orientation_name_map(["DIP", "direction"]) == {"DIP": "Dip", "direction": "Direction"}
      and orientation_name_map(["plunge", "plunge azimuth"]) == {"plunge": "Plunge", "plunge azimuth": "Trend"})
check("azimuth is Direction with a dip, Trend with a plunge, unchanged otherwise",
      orientation_name_map(["dip", "azimuth"])["azimuth"] == "Direction"
      and orientation_name_map(["plunge", "azimuth"])["azimuth"] == "Trend"
      and "azimuth" not in orientation_name_map(["azimuth"]))
check("an older name is not renamed if the canonical name exists too",
      orientation_name_map(["dip", "Dip"]) == {})
check("find_orientation_property finds the canonical or the older name",
      find_orientation_property(["Dip", "x"], "Dip") == "Dip"
      and find_orientation_property(["dip", "dip_dir"], "Direction") == "dip_dir"
      and find_orientation_property(["x"], "Dip") is None)

# ---- a project saved with older names is converted when opened
pw = ProjectWindow()
terminal = []
pw.print_terminal = lambda string=None: terminal.append(str(string))


def add(coll, topology, cls, mesh, name, props, comps):
    d = deepcopy(coll.entity_dict)
    d.update(name=name, uid=str(uuid4()), topology=topology, properties_names=props, properties_components=comps)
    if "role" in d and coll.valid_roles:
        d["role"] = coll.valid_roles[0]
    obj = cls()
    obj.ShallowCopy(mesh)
    d["vtk_obj"] = obj
    return coll.add_entity_from_dict(entity_dict=d)


att = pv.PolyData(np.random.default_rng(0).random((3, 3)))
att["dip"] = np.array([30.0, 45.0, 135.0])
att["dip direction"] = np.array([90.0, 180.0, 270.0])
att["Normals"] = np.array([[-0.5, 0.0, -0.866], [0.0, 0.707, -0.707], [0.707, 0.0, 0.707]])
g_att = add(pw.geol_coll, "VertexSet", Attitude, att, "old_planes",
            ["dip", "dip direction", "Normals"], [1, 1, 3])
lin = pv.PolyData(np.random.default_rng(1).random((2, 3)))
lin["plunge"] = np.array([30.0, 10.0])
lin["azimuth"] = np.array([0.0, 90.0])
f_lin = add(pw.fluid_coll, "VertexSet", VertexSet, lin, "old_lines", ["plunge", "azimuth"], [1, 1])
facets = TriSurf()
facets.ShallowCopy(pv.Plane().triangulate())
facets.set_field_data("dip direction", np.array([90.0]))
facets.set_field_data("dip", np.array([30.0]))
g_facets = add(pw.geol_coll, "TriSurf", TriSurf, facets, "old_facets", [], [])
pw.prop_legend._update_widget_now(pw)
check("legend has the older names before saving",
      {"dip", "dip direction", "plunge", "azimuth"} <= set(pw.prop_legend_df["property_name"]))

tmp = tempfile.mkdtemp(prefix="pzero_names_")
project_file = os.path.join(tmp, "old_names.p0")
pwm.save_file_dialog = lambda **kw: project_file
pw.save_project()
check("project saved", os.path.isfile(project_file))

pw2 = ProjectWindow()
terminal2 = []
pw2.print_terminal = lambda string=None: terminal2.append(str(string))
pwm.open_file_dialog = lambda **kw: project_file
pwm.input_combo_dialog = lambda **kw: kw["choice_list"][0]  # the last saved revision
pwm.options_dialog = lambda **kw: 1  # (pw2 is empty: not asked)
pw2.open_project()

att2 = pw2.geol_coll.get_uid_vtk_obj(g_att)
check("plane properties renamed in the metadata",
      pw2.geol_coll.get_uid_properties_names(g_att) == ["Dip", "Direction", "Normals"])
check("plane properties renamed in the VTK arrays, values kept",
      {"Dip", "Direction", "Normals"} <= set(att2.point_data_keys)
      and "dip" not in att2.point_data_keys
      and np.allclose(att2.get_point_data("Direction"), [90, 180, 270]))
check("point set with Dip opened as Attitude", isinstance(att2, Attitude))
lin2 = pw2.fluid_coll.get_uid_vtk_obj(f_lin)
check("lineation properties renamed (azimuth -> Trend next to a plunge)",
      pw2.fluid_coll.get_uid_properties_names(f_lin) == ["Plunge", "Trend"]
      and {"Plunge", "Trend"} <= set(lin2.point_data_keys))
field_names = list(pw2.geol_coll.get_uid_vtk_obj(g_facets).get_field_data_keys())
check("field data renamed (e.g. facets)", "Direction" in field_names and "Dip" in field_names
      and "dip direction" not in field_names)
pw2.flush_legend_updates()  # the legend rebuild is deferred to the next event loop iteration
legend_names = set(pw2.prop_legend_df["property_name"])
check("property legend rows renamed",
      {"Dip", "Direction", "Plunge", "Trend"} <= legend_names
      and not ({"dip", "dip direction", "plunge", "azimuth"} & legend_names))
check("terminal reports the renaming",
      any("Orientation property names updated" in m and "dip direction -> Direction" in m for m in terminal2))

# ---- xyz import: canonical names; Strike (right-hand rule); lineations; normals keep their sign
df = pd.DataFrame({"X": [0.0, 1.0], "Y": [0.0, 1.0], "Z": [0.0, 0.0], "Dip": [30.0, 135.0], "Direction": [90.0, 270.0]})
obj = _build_tabular_vtk_object(df)
check("xyz import: Dip / Direction / Normals", {"Dip", "Direction", "Normals"} <= set(obj.point_data_keys))
check("xyz import: overturned dip gives an upward normal", obj.get_point_data("Normals")[1, 2] > 0)
df_strike = pd.DataFrame({"X": [0.0], "Y": [0.0], "Z": [0.0], "Dip": [30.0], "Strike": [0.0]})
obj_strike = _build_tabular_vtk_object(df_strike)
check("xyz import: Strike 0 (right-hand rule) -> Direction 90",
      np.allclose(obj_strike.get_point_data("Direction"), 90.0))
df_lin = pd.DataFrame({"X": [0.0, 1.0], "Y": [0.0, 0.0], "Z": [0.0, 0.0], "Plunge": [30.0, -20.0], "Trend": [0.0, 45.0]})
obj_lin = _build_tabular_vtk_object(df_lin)
expected = np.asarray(plunge_trends2lineations(plunges=np.array([30.0, -20.0]), trends=np.array([0.0, 45.0])))
check("xyz import: Plunge / Trend give Lineations (negative plunge upwards)",
      {"Plunge", "Trend", "Lineations"} <= set(obj_lin.point_data_keys)
      and np.allclose(obj_lin.get_point_data("Lineations"), expected)
      and obj_lin.get_point_data("Lineations")[1, 2] > 0)
df_n = pd.DataFrame({"X": [0.0], "Y": [0.0], "Z": [0.0], "Nx": [0.0], "Ny": [0.0], "Nz": [1.0]})
check("xyz import: upward normals keep their sign (overturned)",
      _build_tabular_vtk_object(df_n).get_point_data("Normals").reshape(-1)[2] > 0)

__import__("shutil").rmtree(tmp, ignore_errors=True)

print("RESULT:", "FAILED" if failed else "ALL PASSED")
