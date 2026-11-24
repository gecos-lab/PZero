"""Headless check: meshes and images open in the views showing their active property, and the tree
drop-down shows it (before, Voxets were coloured by their active property while the drop-down said
"none"). Image textures follow the property chosen in the drop-down."""
import os
import sys
from copy import deepcopy
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))

from PySide6.QtWidgets import QApplication, QComboBox

app = QApplication.instance() or QApplication(sys.argv)
import numpy as np  # noqa: E402
import pyvista as pv  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from pzero.project_window import ProjectWindow  # noqa: E402
from pzero.entities_factory import MapImage, PolyLine, TetraSolid, Voxet  # noqa: E402
from pzero.views.view_3d import View3D  # noqa: E402

failed = False


def check(label, cond):
    global failed
    print(("PASS " if cond else "FAIL ") + label)
    failed |= not cond


pw = ProjectWindow()
pw.print_terminal = lambda string=None: None


def add(coll, topology, obj, name, props, comps):
    d = deepcopy(coll.entity_dict)
    d.update(name=name, uid=str(uuid4()), topology=topology, vtk_obj=obj,
             properties_names=props, properties_components=comps)
    if "role" in d and coll.valid_roles:
        d["role"] = coll.valid_roles[0]
    return coll.add_entity_from_dict(entity_dict=d)


def make_voxet(name="vox"):
    grid = pv.ImageData(dimensions=(6, 6, 6))
    grid.point_data["porosity"] = np.zeros(grid.n_points)
    grid.point_data["density"] = np.arange(grid.n_points, dtype=float)
    grid.set_active_scalars("density")  # active: the second property
    vox = Voxet()
    vox.ShallowCopy(grid)
    return add(pw.mesh3d_coll, "Voxet", vox, name, ["porosity", "density"], [1, 1])


def make_tetra():
    grid = pv.ImageData(dimensions=(3, 3, 3)).cast_to_unstructured_grid().triangulate()
    tet = TetraSolid()
    tet.ShallowCopy(grid)
    tet.GetPointData().AddArray(pv.convert_array(np.arange(tet.GetNumberOfPoints(), dtype=float), name="temp"))
    tet.GetPointData().SetActiveScalars("temp")
    return add(pw.mesh3d_coll, "TetraSolid", tet, "tet", ["temp"], [1])


def make_image():
    img = MapImage()
    img.SetDimensions(4, 3, 1)
    img.SetSpacing(1.0, 1.0, 1.0)
    rgb = pv.convert_array(np.random.default_rng(0).integers(0, 255, (12, 3)).astype(np.uint8), name="RGB")
    band = pv.convert_array(np.arange(12, dtype=float), name="band")
    img.GetPointData().AddArray(rgb)
    img.GetPointData().AddArray(band)
    img.GetPointData().SetActiveScalars("RGB")
    return add(pw.image_coll, "MapImage", img, "img", ["RGB", "band"], [3, 1])


vox_uid, tet_uid, img_uid = make_voxet(), make_tetra(), make_image()
line_obj = PolyLine()
line_obj.ShallowCopy(pv.Line((0, 0, 0), (1, 1, 1)))
line_uid = add(pw.geol_coll, "PolyLine", line_obj, "line", [], [])
v = View3D(parent=pw)
for _ in range(3):
    app.processEvents()


def shown(uid):
    return v.actors_df.loc[v.actors_df["uid"] == uid, "show_property"].values[0]


def combo_text(collection, uid):
    tree = v.tree_from_coll(coll=collection)
    for item in tree.findItems("", Qt.MatchContains | Qt.MatchRecursive):
        if tree.get_item_uid(item) == uid:
            for column in range(tree.columnCount()):
                widget = tree.itemWidget(item, column)
                if isinstance(widget, QComboBox):
                    return widget.currentText()
    return None


def colours_by(uid):
    mapper = v.get_actor_by_uid(uid).GetMapper()
    return mapper.GetArrayName() if mapper.GetScalarVisibility() else None


check("Voxet opens showing its active property, drop-down in sync",
      shown(vox_uid) == "density" and combo_text(pw.mesh3d_coll, vox_uid) == "density" and colours_by(vox_uid) == "density")
check("TetraSolid opens showing its active property, drop-down in sync",
      shown(tet_uid) == "temp" and combo_text(pw.mesh3d_coll, tet_uid) == "temp" and colours_by(tet_uid) == "temp")
check("image opens showing its active property (whole RGB listed in the drop-down)",
      shown(img_uid) == "RGB" and combo_text(pw.image_coll, img_uid) == "RGB"
      and v.get_actor_by_uid(img_uid).texture is not None)
check("geology entities still open with none", shown(line_uid) is None)

# Voxet with "none": the constant legend colour, not a property
v.toggle_property(collection_name="mesh3d_coll", uid=vox_uid, prop_text="none")
legend = pw.mesh3d_coll.get_legend()
legend_rgb = [legend["color_R"] / 255, legend["color_G"] / 255, legend["color_B"] / 255]
vox_actor = v.get_actor_by_uid(vox_uid)
check("Voxet with none: legend colour, no property",
      not vox_actor.GetMapper().GetScalarVisibility()
      and np.allclose(vox_actor.GetProperty().GetColor(), legend_rgb, atol=1e-3))

# image bands: one band painted with the colormap and range of the properties legend
from vtkmodules.util.numpy_support import vtk_to_numpy  # noqa: E402
from matplotlib import colormaps  # noqa: E402

pw.prop_legend._update_widget_now(pw)
img = pw.image_coll.get_uid_vtk_obj(img_uid)


def texture_rgb(uid):
    texture = v.get_actor_by_uid(uid).texture
    if texture is None:
        return None
    image = texture.to_image()
    return np.asarray(image.active_scalars)[:, :3]


def expected_band_rgb(item, values):
    cmap_name, clim = v._resolve_scalar_range_and_cmap(property_name=item)
    if clim is None:
        clim = (values.min(), values.max())
    normalized = np.clip((values - clim[0]) / ((clim[1] - clim[0]) or 1.0), 0, 1)
    return (colormaps[cmap_name or "rainbow"](normalized)[:, :3] * 255).astype(np.uint8)


rgb_values = vtk_to_numpy(img.GetPointData().GetArray("RGB")).reshape(-1, 3)
check("the properties legend has a row for each band (e.g. RGB[0])", "RGB[0]" in set(pw.prop_legend_df["property_name"]))
v.toggle_property(collection_name="image_coll", uid=img_uid, prop_text="RGB[0]")
check("image RGB[0]: the first band only, through the colormap of the properties legend",
      np.array_equal(texture_rgb(img_uid), expected_band_rgb("RGB[0]", rgb_values[:, 0].astype(float))))
pw.prop_legend_df.loc[pw.prop_legend_df["property_name"] == "RGB[0]", "colormap"] = "viridis"
v.toggle_property(collection_name="image_coll", uid=img_uid, prop_text="RGB[0]")
check("... and follows the colormap chosen in the legend",
      np.array_equal(texture_rgb(img_uid), expected_band_rgb("RGB[0]", rgb_values[:, 0].astype(float))))
band_values = vtk_to_numpy(img.GetPointData().GetArray("band")).astype(float)
v.toggle_property(collection_name="image_coll", uid=img_uid, prop_text="band")
check("single-band property painted with its colormap",
      np.array_equal(texture_rgb(img_uid), expected_band_rgb("band", band_values)))
v.toggle_property(collection_name="image_coll", uid=img_uid, prop_text="RGB")
check("whole RGB: the image colours", np.array_equal(texture_rgb(img_uid), rgb_values))
v.toggle_property(collection_name="image_coll", uid=img_uid, prop_text="none")
check("image with none shows no texture", v.get_actor_by_uid(img_uid).texture is None)


# X, Y, Z only for entities with point coordinates
def combo_items(collection, uid):
    tree = v.tree_from_coll(coll=collection)
    for item in tree.findItems("", Qt.MatchContains | Qt.MatchRecursive):
        if tree.get_item_uid(item) == uid:
            for column in range(tree.columnCount()):
                widget = tree.itemWidget(item, column)
                if isinstance(widget, QComboBox):
                    return [widget.itemText(i) for i in range(widget.count())]
    return []


check("Voxet and image drop-downs without X, Y, Z",
      not {"X", "Y", "Z"} & set(combo_items(pw.mesh3d_coll, vox_uid))
      and not {"X", "Y", "Z"} & set(combo_items(pw.image_coll, img_uid)))
check("TetraSolid and line drop-downs keep X, Y, Z",
      {"X", "Y", "Z"} <= set(combo_items(pw.mesh3d_coll, tet_uid))
      and {"X", "Y", "Z"} <= set(combo_items(pw.geol_coll, line_uid)))

# an entity added while the view is open opens the same way
vox2 = make_voxet("vox2")
v.flush_pending_updates()
for _ in range(3):
    app.processEvents()
check("Voxet added to an open view shows its active property, drop-down in sync",
      shown(vox2) == "density" and combo_text(pw.mesh3d_coll, vox2) == "density")

print("RESULT:", "FAILED" if failed else "ALL PASSED")
