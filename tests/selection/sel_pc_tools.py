"""Headless check: point-cloud dip/direction and facets tools run from the project window."""
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
from pzero.entities_factory import PCDom, TriSurf  # noqa: E402

pw = ProjectWindow()
failed = False


def check(label, cond):
    global failed
    print(("PASS " if cond else "FAIL ") + label)
    failed |= not cond


rng = np.random.default_rng(1)
# two planar clusters
a = np.c_[rng.random((200, 2)), np.zeros(200)]
b = np.c_[rng.random((200, 2)) + 3, np.ones(200) * 2 + rng.random(200) * 0.01]
pts = np.vstack([a, b])
cloud = pv.PolyData(pts)
cloud["Normals"] = np.tile([0.0, 0.0, 1.0], (len(pts), 1))
cloud["ClusterId"] = np.r_[np.zeros(200), np.ones(200)]

d = deepcopy(pw.dom_coll.entity_dict)
obj = PCDom()
obj.ShallowCopy(cloud)
d.update(name="pc", uid=str(uuid4()), topology="PCDom", vtk_obj=obj,
         properties_names=["Normals", "ClusterId"], properties_components=[3, 1])
pc_uid = pw.dom_coll.add_entity_from_dict(entity_dict=d)

surf = TriSurf()
surf.ShallowCopy(pv.Plane().triangulate())
g = deepcopy(pw.geol_coll.entity_dict)
g.update(name="s", uid=str(uuid4()), topology="TriSurf", vtk_obj=surf)
s_uid = pw.geol_coll.add_entity_from_dict(entity_dict=g)

labels = [a.text() for a in pw.menuInterpolation.actions()]
check("facets action in Interpolation menu", "Planar facets from PC clusters" in labels)
check("Calculate Dip/Direction connected", pw.actionCalculate_Dip_Direction.receivers("2triggered(bool)") > 0)

pw.set_selection(mode="clear")
pw.set_selection([s_uid], mode="add")
pw.set_selection([pc_uid], mode="add")
pw.actionCalculate_Dip_Direction.trigger()
names = pw.dom_coll.get_uid_properties_names(pc_uid)
check("dip and dip direction added to point cloud", "Dip" in names and "Direction" in names)
check("surface deselected by dip tool", pw.selection_uids() == [pc_uid])

n_geol = len(pw.geol_coll.df)
pw.actionFacetsFromPointCloud.trigger()
check("facets created in geology", len(pw.geol_coll.df) == n_geol + 1 and pw.geol_coll.df["topology"].iloc[-1] == "TriSurf")
check("point cloud stays selected", pw.selection_uids() == [pc_uid])

pw.set_selection(mode="clear")
pw.set_selection([s_uid], mode="add")
pw.build_octree()
check("octree refuses non point clouds", not hasattr(surf, "locator") or surf.locator is None)
pw.set_selection([pc_uid], mode="add")
pw.build_octree()
check("octree built on point cloud", getattr(pw.dom_coll.get_uid_vtk_obj(pc_uid), "locator", None) is not None)


# Calculate Dip/Direction on a geology TriSurf with Normals (any collection)
ns = pv.Plane(direction=(-1, 0, -1)).triangulate().compute_normals(cell_normals=False)
surf2 = TriSurf()
surf2.ShallowCopy(ns)
g2 = deepcopy(pw.geol_coll.entity_dict)
g2.update(name="s_normals", uid=str(uuid4()), topology="TriSurf", vtk_obj=surf2,
          properties_names=["Normals"], properties_components=[3])
s2_uid = pw.geol_coll.add_entity_from_dict(entity_dict=g2)
pw.set_selection(mode="clear")
pw.set_selection([s_uid], mode="add")
pw.set_selection([s2_uid], mode="add")
pw.actionCalculate_Dip_Direction.trigger()
names2 = pw.geol_coll.get_uid_properties_names(s2_uid)
check("dip/direction on geology TriSurf with Normals", "Dip" in names2 and "Direction" in names2)
dip_vals = pw.geol_coll.get_uid_vtk_obj(s2_uid).get_point_data("Dip")
check("dip 45 and direction 90 for a plane with downward normal", abs(float(np.mean(dip_vals)) - 45.0) < 1e-4 and abs(float(np.mean(pw.geol_coll.get_uid_vtk_obj(s2_uid).get_point_data("Direction"))) - 90.0) < 1e-4)
check("surface without Normals deselected", pw.selection_uids() == [s2_uid])


# overturned surface (upward normals): dip > 90 convention
ns3 = pv.Plane(direction=(1, 0, 1)).triangulate().compute_normals(cell_normals=False)
surf3 = TriSurf()
surf3.ShallowCopy(ns3)
g3 = deepcopy(pw.geol_coll.entity_dict)
g3.update(name="s_overturned", uid=str(uuid4()), topology="TriSurf", vtk_obj=surf3,
          properties_names=["Normals"], properties_components=[3])
s3_uid = pw.geol_coll.add_entity_from_dict(entity_dict=g3)
pw.set_selection(mode="clear")
pw.set_selection([s3_uid], mode="add")
pw.actionCalculate_Dip_Direction.trigger()
o = pw.geol_coll.get_uid_vtk_obj(s3_uid)
check("overturned: dip 135 and direction 270",
      abs(float(np.mean(o.get_point_data("Dip"))) - 135.0) < 1e-4
      and abs(float(np.mean(o.get_point_data("Direction"))) - 270.0) < 1e-4)

# both overturned conventions give the same upward normal, and the round trip is exact
from pzero.orientation_analysis import dip_directions2normals, normals2dip_directions
n_pos = np.asarray(dip_directions2normals(dips=[135.0, 30.0], directions=[270.0, 90.0]))
n_neg = np.asarray(dip_directions2normals(dips=[-45.0, 30.0], directions=[90.0, 90.0]))
check("dip 135 / 270 == dip -45 / 90 (upward normal toward east)",
      np.allclose(n_pos, n_neg) and np.allclose(n_pos[0], [2 ** -0.5, 0, 2 ** -0.5]))
check("upright dip 30 toward east has a downward normal toward west",
      n_pos[1][2] < 0 and n_pos[1][0] < 0)
d_rt, dd_rt = normals2dip_directions(n_pos)
check("round trip normals -> dip/direction", np.allclose(d_rt, [135, 30]) and np.allclose(dd_rt, [270, 90]))

print("RESULT:", "FAILED" if failed else "ALL PASSED")
