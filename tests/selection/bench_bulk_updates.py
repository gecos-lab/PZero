"""Timing of bulk operations with views open (not a pass/fail test; run directly):
adding, updating properties of, and removing many entities while a 3D view and a map view are open.

    python tests/selection/bench_bulk_updates.py [N]
"""
import os
import sys
import time
from copy import deepcopy
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)
import numpy as np  # noqa: E402
import pyvista as pv  # noqa: E402
from pzero.project_window import ProjectWindow  # noqa: E402
from pzero.entities_factory import TriSurf  # noqa: E402
from pzero.views.view_3d import View3D  # noqa: E402
from pzero.views.view_map import ViewMap  # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 300
pw = ProjectWindow()
views = [View3D(parent=pw), ViewMap(parent=pw)]


def settle():
    for _ in range(5):
        app.processEvents()


def timed(label, fn):
    t0 = time.perf_counter()
    fn()
    settle()
    print(f"{label:<45} {time.perf_counter() - t0:7.2f} s")


plane = pv.Plane(i_resolution=4, j_resolution=4).triangulate()
plane["Normals"] = np.tile([0.0, 0.0, -1.0], (plane.n_points, 1))
uids = []


def add_all():
    for i in range(N):
        d = deepcopy(pw.geol_coll.entity_dict)
        obj = TriSurf()
        obj.ShallowCopy(plane)
        d.update(name=f"s{i}", uid=str(uuid4()), topology="TriSurf", vtk_obj=obj,
                 properties_names=["Normals"], properties_components=[3])
        uids.append(pw.geol_coll.add_entity_from_dict(entity_dict=d))


def dip_direction_all():
    import pzero.point_clouds as pcl
    pw.set_selection(uids=uids, mode="replace")
    pcl.normals2dd(pw)


def remove_all():
    pw.geol_coll.remove_entities(list(uids))


print(f"N = {N} TriSurfs, 2 views open")
timed(f"add {N} entities", add_all)
timed(f"calculate dip/direction on {N} entities", dip_direction_all)
timed(f"remove {N} entities", remove_all)
