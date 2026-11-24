"""Headless check: Properties > Calculate Lineations (point sets from Plunge/Trend, lines from their
segments), Calculate Plunge/Trend and Invert lineations, with the polarity convention (unit vectors,
positive plunge downwards, -90 <= plunge <= 90)."""
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
import pzero.orientation_analysis as oa  # noqa: E402
from pzero.project_window import ProjectWindow  # noqa: E402
from pzero.entities_factory import PolyLine, VertexSet  # noqa: E402

failed = False


def check(label, cond):
    global failed
    print(("PASS " if cond else "FAIL ") + label)
    failed |= not cond


def unit(v):
    v = np.asarray(v, dtype=float)
    return v / np.linalg.norm(v)


def polyline(points, cells):
    line = PolyLine()
    poly = pv.PolyData(np.asarray(points, dtype=float))
    poly.lines = np.hstack([[len(c)] + list(c) for c in cells])
    line.ShallowCopy(poly)
    return line


# ---- line_lineations: average of the segments at each node, first to last node
open_line = polyline([[0, 0, 0], [1, 0, 0], [1, 1, 0]], [[0, 1, 2]])
lin = oa.line_lineations(open_line)
check("open line: ends follow their segment, the middle node averages both",
      np.allclose(lin[0], [1, 0, 0]) and np.allclose(lin[2], [0, 1, 0])
      and np.allclose(lin[1], unit([1, 1, 0])))
square_by_index = polyline([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], [[0, 1, 2, 3, 0]])
lin = oa.line_lineations(square_by_index)
check("closed loop (last node = first node): the first node averages two segments",
      np.allclose(lin[0], unit([1, -1, 0])) and np.allclose(lin[2], unit([-1, 1, 0])))
square_by_position = polyline([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 0]], [[0, 1, 2, 3, 4]])
lin = oa.line_lineations(square_by_position)
check("closed loop (first and last nodes at the same position): both average two segments",
      np.allclose(lin[0], unit([1, -1, 0])) and np.allclose(lin[4], unit([1, -1, 0])))
check("unit vectors", np.allclose(np.linalg.norm(lin, axis=1), 1.0))
pl, tr = oa.lineations2plunge_trends([[0, 0.5 ** 0.5, -(0.5 ** 0.5)], [0.5 ** 0.5, 0, 0.5 ** 0.5]])
check("lineations2plunge_trends: down = positive plunge, up = negative, trend toward the vector",
      np.allclose(pl, [45, -45]) and np.allclose(tr, [0, 90]))

# ---- plunge / trend <-> lineation vectors, back and forth (x east, y north, z up)
cases = {  # vector: (plunge, trend)
    (0, 1, 0): (0, 0), (1, 0, 0): (0, 90), (0, -1, 0): (0, 180), (-1, 0, 0): (0, 270),
    (0, 0, -1): (90, None), (0, 0, 1): (-90, None),
    (0, 0.5 ** 0.5, -(0.5 ** 0.5)): (45, 0), (-(0.5 ** 0.5), 0, 0.5 ** 0.5): (-45, 270),
}
ok_forward, ok_back = True, True
for vector, (plunge, trend) in cases.items():
    p_calc, t_calc = oa.lineations2plunge_trends([vector])
    ok_forward &= abs(p_calc[0] - plunge) < 1e-9 and (trend is None or abs(t_calc[0] - trend) < 1e-9)
    back = np.asarray(oa.plunge_trends2lineations(plunges=float(plunge), trends=float(trend or 0))).reshape(-1)
    ok_back &= np.allclose(back, vector, atol=1e-12)
check("lineation -> plunge/trend: [0,1,0] 0/0, [1,0,0] 0/90, [0,-1,0] 0/180, [-1,0,0] 0/270, down 90, up -90",
      ok_forward)
check("plunge/trend -> lineation gives the same vectors back", ok_back)
rng = np.random.default_rng(3)
random_vectors = rng.normal(size=(500, 3))
random_vectors /= np.linalg.norm(random_vectors, axis=1)[:, None]
p_r, t_r = oa.lineations2plunge_trends(random_vectors)
check("random vectors: plunge in [-90, 90], trend in [0, 360), exact round trip",
      p_r.min() >= -90 and p_r.max() <= 90 and t_r.min() >= 0 and t_r.max() < 360
      and np.allclose(np.asarray(oa.plunge_trends2lineations(plunges=p_r, trends=t_r)), random_vectors))

# ---- the tools
pw = ProjectWindow()
terminal = []
pw.print_terminal = lambda string=None: terminal.append(str(string))


def add(coll, topology, obj, name, props, comps):
    d = deepcopy(coll.entity_dict)
    d.update(name=name, uid=str(uuid4()), topology=topology, vtk_obj=obj,
             properties_names=props, properties_components=comps)
    if "role" in d and coll.valid_roles:
        d["role"] = coll.valid_roles[0]
    return coll.add_entity_from_dict(entity_dict=d)


def point_set(props):
    pts = pv.PolyData(np.random.default_rng(0).random((len(next(iter(props.values()))), 3)))
    for name, values in props.items():
        pts[name] = np.asarray(values, dtype=float)
    obj = VertexSet()
    obj.ShallowCopy(pts)
    return obj


ps = add(pw.geol_coll, "VertexSet", point_set({"Plunge": [30, -20], "Trend": [0, 90]}), "ps",
         ["Plunge", "Trend"], [1, 1])
ps_old = add(pw.fluid_coll, "VertexSet", point_set({"plunge": [10.0], "azimuth": [180.0]}), "ps_old",
             ["plunge", "azimuth"], [1, 1])
ps_custom = add(pw.geol_coll, "VertexSet", point_set({"pl": [60.0], "tr": [270.0]}), "ps_custom",
                ["pl", "tr"], [1, 1])
down_line = add(pw.geol_coll, "PolyLine", polyline([[0, 0, 0], [1, 0, -1], [2, 0, -2]], [[0, 1, 2]]),
                "down_line", [], [])
up_line = add(pw.boundary_coll, "PolyLine", polyline([[0, 0, 0], [1, 0, 1], [2, 0, 2]], [[0, 1, 2]]),
              "up_line", [], [])
up_keep = add(pw.geol_coll, "PolyLine", polyline([[0, 0, 0], [0, 1, 1]], [[0, 1]]), "up_keep", [], [])
asked = {}
oa.multiple_input_dialog = lambda **kw: asked.setdefault("names", kw["input_dict"]) and {"plunge_name": "pl", "trend_name": "tr"}
oa.options_dialog = lambda **kw: asked.setdefault("invert", kw["message"]) and 0  # Invert
pw.set_selection([ps, ps_old, ps_custom, down_line, up_line], mode="replace")
oa.set_lineations(pw)
g = pw.geol_coll.get_uid_vtk_obj
expected = np.asarray(oa.plunge_trends2lineations(plunges=np.array([30.0, -20.0]), trends=np.array([0.0, 90.0])))
check("point set: Lineations from Plunge / Trend (negative plunge upwards)",
      np.allclose(g(ps).get_point_data("Lineations"), expected) and g(ps).get_point_data("Lineations")[1, 2] > 0)
check("point set with older names (plunge, azimuth) found without asking",
      np.allclose(pw.fluid_coll.get_uid_vtk_obj(ps_old).get_point_data("Lineations").reshape(-1),
                  np.asarray(oa.plunge_trends2lineations(plunges=10.0, trends=180.0)).reshape(-1)))
check("point set without Plunge / Trend: names asked once, then used",
      "names" in asked and np.allclose(g(ps_custom).get_point_data("Lineations").reshape(-1),
                                       np.asarray(oa.plunge_trends2lineations(plunges=60.0, trends=270.0)).reshape(-1)))
check("line going down: lineations from first to last node, downwards",
      np.allclose(g(down_line).get_point_data("Lineations"), [unit([1, 0, -1])] * 3))
up_obj = pw.boundary_coll.get_uid_vtk_obj(up_line)
check("line mostly upwards: inversion proposed, accepted -> downwards, node order reversed",
      "up_line" in asked.get("invert", "")
      and np.allclose(up_obj.get_point_data("Lineations"), [unit([-1, 0, -1])] * 3)
      and list(pv.wrap(up_obj).lines) == [3, 2, 1, 0])
check("Lineations added to the properties", "Lineations" in pw.geol_coll.get_uid_properties_names(down_line)
      and "Lineations" in pw.boundary_coll.get_uid_properties_names(up_line))
asked.clear()
oa.options_dialog = lambda **kw: asked.setdefault("invert", kw["message"]) and 1  # Keep
pw.set_selection([up_keep], mode="replace")
oa.set_lineations(pw)
check("line mostly upwards, inversion refused: kept upwards", g(up_keep).get_point_data("Lineations")[0, 2] > 0)
pw.set_selection([up_line], mode="replace")
asked.clear()
oa.set_lineations(pw)
check("recalculating an inverted line keeps the new sense (no question)",
      "invert" not in asked and up_obj.get_point_data("Lineations")[0, 2] < 0)

# ---- Calculate Plunge/Trend from Lineations
pw.set_selection([down_line, ps], mode="replace")
pw.actionCalculate_Plunge_Trend.trigger()
check("Calculate Plunge/Trend (menu) from Lineations",
      np.allclose(g(down_line).get_point_data("Plunge"), 45) and np.allclose(g(down_line).get_point_data("Trend"), 90)
      and np.allclose(g(ps).get_point_data("Plunge"), [30, -20]) and np.allclose(g(ps).get_point_data("Trend"), [0, 90]))

# ---- Invert lineations
check("Invert lineations in the Properties menu", pw.actionInvertLineations in pw.menuProperties.actions())
no_lin = add(pw.geol_coll, "PolyLine", polyline([[0, 0, 0], [1, 0, 0]], [[0, 1]]), "no_lin", [], [])
pw.set_selection([ps, down_line, no_lin], mode="replace")
terminal.clear()
pw.actionInvertLineations.trigger()
check("point set: Lineations, Plunge and Trend inverted consistently",
      np.allclose(g(ps).get_point_data("Lineations"), -expected)
      and np.allclose(g(ps).get_point_data("Plunge"), [-30, 20]) and np.allclose(g(ps).get_point_data("Trend"), [180, 270]))
check("line: lineations inverted and node order reversed",
      np.allclose(g(down_line).get_point_data("Lineations"), [unit([-1, 0, 1])] * 3)
      and list(pv.wrap(g(down_line)).lines) == [3, 2, 1, 0])
check("entity without lineations deselected with a message",
      no_lin not in pw.selection_uids() and any("deselected" in m for m in terminal))
pw.set_selection([down_line], mode="replace")
oa.options_dialog = lambda **kw: 1
oa.set_lineations(pw)
check("recalculating after Invert lineations keeps the inverted sense",
      np.allclose(g(down_line).get_point_data("Lineations"), [unit([-1, 0, 1])] * 3))

print("RESULT:", "FAILED" if failed else "ALL PASSED")
