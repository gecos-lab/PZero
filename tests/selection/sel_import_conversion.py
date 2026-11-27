"""Headless check: importers convert property names to the PZero conventions after one confirmation
per import: orientation names (e.g. "Dip (degrees)", "dip_direction", "plunge") to Dip, Direction,
Plunge, Trend; normals components and lowercase normals to the 3-component Normals (sign kept);
R, G, B to RGB for point clouds. Point clouds, GOCAD and VTK files."""
import os
import sys
import tempfile
import types

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))

from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)
import numpy as np  # noqa: E402
import pyvista as pv  # noqa: E402
import pzero.orientation_analysis as oa  # noqa: E402
import pzero.imports.pyvista2vtk as pv2  # noqa: E402
from pzero.project_window import ProjectWindow  # noqa: E402
from pzero.imports.gocad2vtk import gocad2vtk  # noqa: E402
from pzero.imports.pc2vtk import pc2vtk  # noqa: E402

failed = False


def check(label, cond):
    global failed
    print(("PASS " if cond else "FAIL ") + label)
    failed |= not cond


# ---- plans
plan = oa.describe_property_plan(oa.plan_imported_properties(
    ["Nx", "Ny", "Nz", "Dip (degrees)", "Dip direction (degrees)", "Intensity"]))
check("plan: normals components merged, names with units converted",
      plan == ["Nx, Ny, Nz -> Normals (3 components)", "Dip (degrees) -> Dip", "Dip direction (degrees) -> Direction"])
check("plan: colour channels merged only when asked (point clouds)",
      "R, G, B -> RGB (3 components)" in oa.describe_property_plan(oa.plan_imported_properties(["R", "G", "B"], rgb=True))
      and not oa.plan_imported_properties(["R", "G", "B"]))
check("plan: plunge / azimuth -> Plunge / Trend; normals -> Normals; nothing if already canonical",
      oa.describe_property_plan(oa.plan_imported_properties(["plunge", "azimuth"])) == ["plunge -> Plunge", "azimuth -> Trend"]
      and oa.describe_property_plan(oa.plan_imported_properties(["normals"])) == ["normals -> Normals"]
      and oa.plan_imported_properties(["Normals", "Dip", "Direction", "value"]) == [])

pw = ProjectWindow()
terminal = []
pw.print_terminal = lambda string=None: terminal.append(str(string))
asked = []
answer = {"value": 0}  # 0 = Convert, 1 = Keep
oa.options_dialog = lambda **kw: asked.append(kw["message"]) or answer["value"]
tmp = tempfile.mkdtemp(prefix="pzero_import_")

# ---- GOCAD: two objects in one file, one question
gocad_file = os.path.join(tmp, "attitudes.vs")
with open(gocad_file, "w") as f:
    for name in ("set_a", "set_b"):
        f.write(f"GOCAD VSet 1\nHEADER {{\nname:{name}\n}}\nPROPERTIES dip dip_direction\nESIZES 1 1\n"
                "PVRTX 1 0 0 0 30 90\nPVRTX 2 1 0 0 135 270\nEND\n")
import pzero.imports.gocad2vtk as g2v  # noqa: E402

# the importer's own dialogs: default scenario and role, feature from name (no), legend reset (no)
g2v.input_text_dialog = lambda **kw: "undef"
g2v.input_combo_dialog = lambda **kw: kw["choice_list"][0]
g2v.options_dialog = lambda **kw: 1
oa.start_property_import(pw)
gocad2vtk(self=pw, in_file_name=gocad_file, uid_from_name=False)
gocad_uids = pw.geol_coll.df["uid"].tolist()
check("GOCAD: both objects imported", len(gocad_uids) == 2)
check("GOCAD: dip, dip_direction -> Dip, Direction (metadata and arrays)",
      all(pw.geol_coll.get_uid_properties_names(u) == ["Dip", "Direction"]
          and {"Dip", "Direction"} <= set(pw.geol_coll.get_uid_vtk_obj(u).point_data_keys) for u in gocad_uids))
check("GOCAD: asked once for the two objects of the import", len(asked) == 1 and "attitudes.vs" in asked[0])

# ---- VTK file: lowercase normals, plunge / trend with units; answered "Keep"
asked.clear()
answer["value"] = 1
mesh = pv.Plane(i_resolution=2, j_resolution=2).triangulate()
mesh.point_data["normals"] = np.tile([0.0, 0.0, 1.0], (mesh.n_points, 1))  # upward: kept as given
mesh.point_data["Plunge (deg)"] = np.zeros(mesh.n_points)
vtk_file = os.path.join(tmp, "surface.vtp")
mesh.save(vtk_file)
pv2.QFileDialog = types.SimpleNamespace(getOpenFileName=lambda *a, **k: (vtk_file, ""))
pv2.pyvista2vtk(pw)
kept_uid = pw.geol_coll.df["uid"].iloc[-1]
check("VTK: conversion refused -> original names kept",
      len(asked) == 1 and {"normals", "Plunge (deg)"} <= set(pw.geol_coll.get_uid_properties_names(kept_uid)))
asked.clear()
answer["value"] = 0
pv2.pyvista2vtk(pw)
conv_uid = pw.geol_coll.df["uid"].iloc[-1]
conv = pw.geol_coll.get_uid_vtk_obj(conv_uid)
check("VTK: normals -> Normals, Plunge (deg) -> Plunge; normals keep their sign",
      {"Normals", "Plunge"} <= set(pw.geol_coll.get_uid_properties_names(conv_uid))
      and np.allclose(conv.get_point_data("Normals")[:, 2], 1.0))
check("menu label: Import VTK/PLY/OBJ/STL", pw.actionImportPyVista.text() == "Import VTK/PLY/OBJ/STL")

# ---- point cloud: R G B, nx ny nz (one upward), Dip (degrees)
asked.clear()
pc_file = os.path.join(tmp, "cloud.csv")
with open(pc_file, "w") as f:
    f.write("x,y,z,R,G,B,nx,ny,nz,Dip (degrees)\n")
    f.write("0,0,0,255,0,0,0,0,-1,10\n1,0,0,0,255,0,0,0,1,170\n0,1,0,0,0,255,0.6,0,-0.8,37\n")
origin = types.SimpleNamespace(parent=pw)
oa.start_property_import(pw)
pc2vtk(in_file_name=pc_file, col_names=["X", "Y", "Z", "R", "G", "B", "nx", "ny", "nz", "Dip (degrees)"],
       row_range=range(1, 4), header_row=0, usecols=list(range(10)), delimiter=",", self=origin)
pc_uid = pw.dom_coll.df["uid"].iloc[-1]
pc = pw.dom_coll.get_uid_vtk_obj(pc_uid)
names = pw.dom_coll.get_uid_properties_names(pc_uid)
check("point cloud: R, G, B -> RGB; nx, ny, nz -> Normals; Dip (degrees) -> Dip",
      {"RGB", "Normals", "Dip"} <= set(names) and not {"R", "nx", "Dip (degrees)"} & set(names))
check("point cloud: RGB values and normals kept as given (upward normal not flipped)",
      np.array_equal(pc.get_point_data("RGB")[0], [255, 0, 0]) and pc.get_point_data("Normals")[1, 2] > 0)
check("point cloud: asked once", len(asked) == 1)

__import__("shutil").rmtree(tmp, ignore_errors=True)
print("RESULT:", "FAILED" if failed else "ALL PASSED")
