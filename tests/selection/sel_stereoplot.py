"""Headless check: the stereoplot draws any entity with Normals or Lineations, in any collection;
upward vectors as hollow markers on the upper hemisphere; large entities as contours only."""
import os
import sys
import warnings
from copy import deepcopy
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))

from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)
import numpy as np  # noqa: E402
import pyvista as pv  # noqa: E402
import mplstereonet  # noqa: E402
from matplotlib.contour import ContourSet  # noqa: E402
from matplotlib.collections import PathCollection  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from pzero.project_window import ProjectWindow  # noqa: E402
from pzero.entities_factory import TriSurf, PolyLine, VertexSet  # noqa: E402
from pzero.views.view_stereoplot import ViewStereoplot, StereoActor  # noqa: E402

pw = ProjectWindow()
failed = False
messages = []
pw.print_terminal = lambda string=None: messages.append(str(string))


def check(label, cond):
    global failed
    print(("PASS " if cond else "FAIL ") + label)
    failed |= not cond


def add(coll, topology, cls, mesh, name, props):
    d = deepcopy(coll.entity_dict)
    d.update(name=name, uid=str(uuid4()), topology=topology)
    if "role" in d:
        d["role"] = coll.valid_roles[0] if coll.valid_roles else d["role"]
    obj = cls()
    obj.ShallowCopy(mesh)
    d["vtk_obj"] = obj
    d["properties_names"] = list(props)
    d["properties_components"] = [3] * len(props)
    return coll.add_entity_from_dict(entity_dict=d)


def unit(v):
    v = np.asarray(v, dtype=float)
    return v / np.linalg.norm(v, axis=-1, keepdims=True)


def scatters(actor):
    return [a for a in actor.artists if isinstance(a, PathCollection)]


r2 = 2 ** -0.5
# geology TriSurf, upright plane dipping 45 toward east: downward normal toward west
surf = pv.Plane(i_resolution=3, j_resolution=3).triangulate()
surf["Normals"] = np.tile([-r2, 0.0, -r2], (surf.n_points, 1))
g_surf = add(pw.geol_coll, "TriSurf", TriSurf, surf, "st_surf", ["Normals"])
# fluid points: 3 upright + 2 overturned (upward normal toward east)
pts = pv.PolyData(np.random.default_rng(0).random((5, 3)))
pts["Normals"] = unit([[-1, 0, -1], [-1, 0.05, -1], [-1, -0.05, -1], [1, 0, 1], [1, 0.05, 1]])
f_pts = add(pw.fluid_coll, "VertexSet", VertexSet, pts, "fluid_pts", ["Normals"])
# boundary line with lineations, one plunging 30 toward N and one upward (negative plunge)
line = pv.Line((0, 0, 0), (1, 0, 0), resolution=1)
c30, s30 = np.cos(np.radians(30)), np.sin(np.radians(30))
line["Lineations"] = np.array([[0, c30, -s30], [0, c30, s30]])
b_line = add(pw.boundary_coll, "PolyLine", PolyLine, line, "bound_line", ["Lineations"])
# large geology point cloud (contours only above the threshold)
big_v = unit(np.random.default_rng(1).normal(size=(600, 3)) * [0.2, 0.2, 1] + [0, 0, -1])
big = pv.PolyData(np.random.default_rng(2).random((600, 3)))
big["Normals"] = big_v
g_big = add(pw.geol_coll, "VertexSet", VertexSet, big, "big_pts", ["Normals"])

with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter("always")
    stereo = ViewStereoplot(parent=pw)
    stereo.contours_only_threshold = 500
    stereo._rebuild_all_entity_actors()
    app.processEvents()
check("no RuntimeWarning (arcsin) while drawing",
      not any(issubclass(w.category, RuntimeWarning) for w in caught))
in_view = set(stereo.actors_df["uid"])
check("entities of geology, fluids and boundaries are in the view",
      {g_surf, f_pts, b_line, g_big} <= in_view)
for uid, label in ((g_surf, "TriSurf"), (f_pts, "fluid points"), (b_line, "boundary line")):
    check(f"{label} drawn as markers", isinstance(stereo.mpl_actors.get(uid), StereoActor)
          and len(scatters(stereo.mpl_actors[uid])) == 1)

# positions and hollow markers
sc = scatters(stereo.mpl_actors[f_pts])[0]
offsets = np.asarray(sc.get_offsets())
lon_w, lat_w = mplstereonet.line(45, 270)
lon_e, lat_e = mplstereonet.line(45, 90)
check("upright pole at plunge 45 toward west", np.allclose(offsets[0], [lon_w[0], lat_w[0]]))
check("overturned pole at its own trend (east), upper hemisphere",
      np.allclose(offsets[3], [lon_e[0], lat_e[0]]))
face = sc.get_facecolors()
edge = sc.get_edgecolors()
check("upright filled, overturned hollow with the same edge color",
      np.all(face[:3, 3] > 0) and np.all(face[3:, 3] == 0) and np.allclose(edge[3:, :3], edge[0, :3]))
lsc = scatters(stereo.mpl_actors[b_line])[0]
lon_n, lat_n = mplstereonet.line(30, 0)
check("lineations: triangles, plunge 30 N filled, negative plunge hollow at the same position",
      np.allclose(np.asarray(lsc.get_offsets()), [[lon_n[0], lat_n[0]]] * 2)
      and lsc.get_facecolors()[0, 3] > 0 and lsc.get_facecolors()[1, 3] == 0)

# large entity: contours only, in the legend color
big_actor = stereo.mpl_actors[g_big]
check("entity above threshold drawn as contours only",
      isinstance(big_actor, StereoActor) and not scatters(big_actor)
      and any(isinstance(a, ContourSet) for a in big_actor.artists))
legend = pw.geol_coll.get_uid_legend(uid=g_big)
rgb = [legend["color_R"] / 255, legend["color_G"] / 255, legend["color_B"] / 255]
cs = [a for a in big_actor.artists if isinstance(a, ContourSet)][0]
check("terminal says once that the large entity is drawn as contours",
      sum("big_pts has 600 vectors (> 500)" in m for m in messages) == 1)
check("contours in the entity legend color", np.allclose(np.asarray(cs.get_edgecolor())[:, :3], rgb))

# hide / show
stereo.set_actor_visible(uid=f_pts, visible=False)
check("hidden", stereo.actor_shown(f_pts) is False)
stereo.set_actor_visible(uid=f_pts, visible=True)
check("shown again", stereo.actor_shown(f_pts) is True)
check("no error messages", not any("ERROR" in m for m in messages))

# planes: solid for upright, dashed for overturned
stereo.show_actor_with_property(uid=f_pts, coll_name="fluid_coll", show_property="Planes", visible=True)
lines = [a for a in stereo.mpl_actors[f_pts].artists if isinstance(a, Line2D)]
check("planes: one solid and one dashed line", sorted(l.get_linestyle() for l in lines) == ["-", "--"])

# legend color change redraws with the new color
original_legend = pw.fluid_coll.get_uid_legend
pw.fluid_coll.get_uid_legend = lambda uid=None: {**original_legend(uid=uid), "color_R": 255, "color_G": 0, "color_B": 0}
stereo.actors_df.loc[stereo.actors_df["uid"] == f_pts, "show_property"] = "Poles"
stereo.change_actor_color(updated_uids=[f_pts], collection=pw.fluid_coll)
sc = scatters(stereo.mpl_actors[f_pts])[0]
check("color change applied to filled and hollow markers",
      np.allclose(sc.get_edgecolors()[:, :3], [1, 0, 0]) and np.all(sc.get_facecolors()[3:, 3] == 0))
pw.fluid_coll.get_uid_legend = original_legend

# toggle contours / projection rebuild the figure (they called a missing method before)
stereo.set_actor_visible(uid=g_surf, visible=False)
stereo.actors_df.loc[stereo.actors_df["uid"] == g_surf, "show"] = False
stereo.toggle_contours()
check("toggle contours: one pooled density (lines), entities keep their markers",
      isinstance(stereo.pooled_contour_actor, ContourSet)
      and not stereo.pooled_contour_actor.filled
      and not any(isinstance(a, ContourSet) for a in stereo.mpl_actors[f_pts].artists)
      and scatters(stereo.mpl_actors[f_pts]) and not scatters(stereo.mpl_actors[g_big]))


def pooled_density_max():
    return max(float(np.max(level)) for level in stereo.pooled_contour_actor.levels)


levels_all = stereo.pooled_contour_actor.levels.copy()
stereo.set_actor_visible(uid=g_big, visible=False)
stereo.actors_df.loc[stereo.actors_df["uid"] == g_big, "show"] = False
app.processEvents()
check("hiding an entity updates the pooled density",
      isinstance(stereo.pooled_contour_actor, ContourSet)
      and not np.array_equal(stereo.pooled_contour_actor.levels, levels_all))
stereo.actors_df.loc[stereo.actors_df["uid"] == g_big, "show"] = True
stereo.set_actor_visible(uid=g_big, visible=True)
app.processEvents()
check("showing it again restores the pooled density",
      np.array_equal(stereo.pooled_contour_actor.levels, levels_all))
stereo.toggle_contours()
check("toggle contours again: filled pooled density, background (level 0) not filled",
      stereo.pooled_contour_actor.filled and min(stereo.pooled_contour_actor.levels) > 0)
stereo.toggle_contours()
check("toggle contours a third time: no pooled density, no contour left on the axes except the "
      "contours-only entity", stereo.pooled_contour_actor is None
      and [c for c in stereo.ax.collections if isinstance(c, ContourSet)]
      == [a for a in stereo.mpl_actors[g_big].artists if isinstance(a, ContourSet)])
stereo.toggle_contours()  # lines again for the projection toggle below
stereo.toggle_projection()
check("toggle projection redraws all entities",
      all(isinstance(stereo.mpl_actors.get(u), StereoActor) for u in (g_surf, f_pts, b_line, g_big)))
check("an entity hidden before the rebuild stays hidden and can be shown again",
      stereo.actor_shown(g_surf) is False)
stereo.set_actor_visible(uid=g_surf, visible=True)
check("shown after the rebuild", stereo.actor_shown(g_surf) is True)

# Toggle poles / great circles
stereo.toggle_poles()
app.processEvents()
check("toggle poles: no markers and no entity contours, only the pooled density",
      all(stereo.mpl_actors.get(u) is None for u in (g_surf, f_pts, b_line, g_big))
      and [c for c in stereo.ax.collections if isinstance(c, ContourSet)] == [stereo.pooled_contour_actor])
stereo.toggle_poles()
check("toggle poles again: markers back", scatters(stereo.mpl_actors[f_pts]))
stereo.toggle_great_circles()
check("toggle great circles: circles plus poles",
      any(isinstance(a, Line2D) for a in stereo.mpl_actors[f_pts].artists)
      and scatters(stereo.mpl_actors[f_pts]))
stereo.toggle_great_circles()
check("toggle great circles again: no circles",
      not any(isinstance(a, Line2D) for a in stereo.mpl_actors[f_pts].artists))

# statistics on the shown entities (any collection), not on the selection
def set_shown(uid, shown):
    stereo.actors_df.loc[stereo.actors_df["uid"] == uid, "show"] = shown
    stereo.set_actor_visible(uid=uid, visible=shown)


menu_texts = [a.text() for a in stereo.menuAnalysis.actions()]
check("no Recompute / auto recomputation commands",
      not any("ecompute" in t or "recomputation" in t for t in menu_texts))
for uid in (g_surf, g_big):
    set_shown(uid, False)
app.processEvents()
pw.set_selection(mode="clear")
normals_df, lineations_df = stereo.get_normals_and_lineations_for_analysis()
check("analysis reads the shown entities (fluid normals, boundary lineations), nothing selected",
      set(normals_df["uid"]) == {f_pts} and len(normals_df) == 5 and len(lineations_df) == 2)
stereo.kmedoids_k = 2
stereo.save_clusters_as_property("clusters")
check("clusters saved on the fluid entity",
      "clusters" in pw.fluid_coll.get_uid_properties_names(f_pts)
      and len(pw.fluid_coll.get_uid_vtk_obj(f_pts).get_point_data("clusters")) == 5)

# contours of many points are smooth (kernel of at most 1000 points) and match mplstereonet for few
from pzero.orientation_analysis import kamb_density_grid  # noqa: E402
from mplstereonet.contouring import density_grid  # noqa: E402

few = unit(np.random.default_rng(5).normal(size=(500, 3)))
pl, tr = mplstereonet.vector2plunge_bearing(*few.T)
lo, la = mplstereonet.line(pl, tr)
check("Kamb density equals mplstereonet up to 1000 points",
      np.allclose(kamb_density_grid(lo, la)[2], density_grid(pl, tr, measurement="lines")[2]))
many = unit(np.random.default_rng(6).normal(size=(100000, 3)) * [0.3, 0.3, 1] + [0, 0, -1])
pl, tr = mplstereonet.vector2plunge_bearing(*many.T)
lo, la = mplstereonet.line(pl, tr)
dens = kamb_density_grid(lo, la)[2]
# smooth: neighbouring grid nodes differ little compared with the maximum
check("Kamb density of 100k points is smooth",
      np.max(np.abs(np.diff(dens, axis=0))) < 0.15 * dens.max())

# Bingham / Fisher / k-medoids overlays with upward vectors: no arcsin warning
keys = ("bingham_major_pole", "bingham_intermediate_pole", "bingham_minor_pole",
        "bingham_minor_gc", "fisher_mean_pole", "kmedoids_centers", "kmedoids_color")
with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter("always")
    for key in keys:
        stereo.analysis_action_for_key[key].trigger()  # check the box, as the user
check("checked overlays drawn", all(stereo.analysis_actors.get(k) for k in keys))


def zorders(actor):
    items = actor if isinstance(actor, list) else [actor]
    out = []
    for item in items:
        out += [a.get_zorder() for a in item.artists] if isinstance(item, StereoActor) else [item.get_zorder()]
    return out


pole_z = min(z for k in ("fisher_mean_pole", "bingham_major_pole", "bingham_intermediate_pole",
                         "bingham_minor_pole", "kmedoids_centers") for z in zorders(stereo.analysis_actors[k]))
circle_z = max(zorders(stereo.analysis_actors["bingham_minor_gc"]))
cluster_colors_z = max(zorders(stereo.analysis_actors["kmedoids_color"]))
data_z = max(a.get_zorder() for actor in stereo.mpl_actors.values() if actor is not None for a in actor.artists)
check("drawing order: data < cluster colours < selection rings < great circle < mean and cluster-centre poles",
      data_z < cluster_colors_z < stereo.Z_HIGHLIGHT < circle_z < pole_z)
check("no arcsin warning from analysis overlays",
      not any("arcsin" in str(w.message) for w in caught))

check("k-medoids with k=2: exactly 2 cluster centres (opposite copies merged)",
      len(stereo.analysis_results["normals"]["kmedoids"]["centroids"]) == stereo.kmedoids_k == 2)

# k spin box: one per place the menu is shown (e.g. a detached copy), all in sync
from PySide6.QtWidgets import QMenu  # noqa: E402

other_menu = QMenu()
other_menu.addAction(stereo.kmedoids_k_widget_action)
other_menu.popup(stereo.mapToGlobal(stereo.rect().center()))
stereo.menuAnalysis.popup(stereo.mapToGlobal(stereo.rect().center()))
app.processEvents()
boxes = stereo.kmedoids_k_widget_action.createdWidgets()
boxes[0].setValue(3)
app.processEvents()
check("k spin box in two menus, both show the new k",
      len(boxes) >= 2 and stereo.kmedoids_k == 3 and all(b.value() == 3 for b in boxes))
other_menu.close()
stereo.menuAnalysis.close()
boxes[0].setValue(2)  # back to k = 2 (only 2 lineations stay shown below)
app.processEvents()

# showing / hiding entities recomputes the statistics and redraws the checked overlays
set_shown(f_pts, False)
app.processEvents()
check("hiding an entity: statistics without it, overlays still drawn, boxes still checked",
      f_pts not in set(stereo.last_normals_df["uid"])
      and stereo.analysis_actors.get("kmedoids_color")
      and all(stereo.analysis_action_for_key[k].isChecked() for k in keys))
for uid in (b_line,):
    set_shown(uid, False)
app.processEvents()
check("nothing shown: no overlays, boxes still checked",
      not any(stereo.analysis_actors.get(k) for k in keys)
      and all(stereo.analysis_action_for_key[k].isChecked() for k in keys))
messages.clear()
for uid in (f_pts, b_line):
    set_shown(uid, True)
app.processEvents()
check("shown again: overlays back, results not printed again (automatic refresh)",
      all(stereo.analysis_actors.get(k) for k in ("bingham_major_pole", "kmedoids_color"))
      and not any("Bingham major pole" in m for m in messages))
stereo.analysis_action_for_key["bingham_major_pole"].trigger()  # uncheck
check("unchecking a box hides its overlay only",
      stereo.analysis_actors.get("bingham_major_pole") is None
      and stereo.analysis_actors.get("kmedoids_color"))
set_shown(f_pts, False)
app.processEvents()
check("an unchecked overlay is not redrawn when entities change",
      stereo.analysis_actors.get("bingham_major_pole") is None)
set_shown(f_pts, True)
for uid in (g_surf, g_big):
    set_shown(uid, True)
app.processEvents()

# Calculate Normals on a point set with dip / direction: it enters the stereoplot (was IndexError)
import pzero.orientation_analysis as oa  # noqa: E402
att = pv.PolyData(np.random.default_rng(3).random((4, 3)))
att["dip"] = np.array([30.0, 45.0, 135.0, -45.0])
att["dir"] = np.array([90.0, 90.0, 270.0, 90.0])
d = deepcopy(pw.geol_coll.entity_dict)
d.update(name="att", uid=str(uuid4()), topology="VertexSet", properties_names=["dip", "dir"],
         properties_components=[1, 1])
obj = VertexSet()
obj.ShallowCopy(att)
d["vtk_obj"] = obj
g_att = pw.geol_coll.add_entity_from_dict(entity_dict=d)
app.processEvents()
check("point set without Normals not in the stereoplot", g_att not in set(stereo.actors_df["uid"]))
original_dialog = oa.multiple_input_dialog
oa.multiple_input_dialog = lambda **kwargs: {"dip_name": "dip", "dir_name": "dir"}
pw.set_selection([g_att], mode="replace")
messages.clear()
oa.set_normals(pw)
oa.multiple_input_dialog = original_dialog
stereo.flush_pending_updates()
app.processEvents()
check("Calculate Normals on a point set works", "All Normals set." in messages
      and not any("Traceback" in m or "ERROR" in m for m in messages))
check("the point set enters the stereoplot and is drawn", g_att in set(stereo.actors_df["uid"])
      and isinstance(stereo.mpl_actors.get(g_att), StereoActor))
att_face = scatters(stereo.mpl_actors[g_att])[0].get_facecolors()[:, 3]
check("dip 135/270 and -45/90 drawn hollow, 30 and 45 filled",
      list(att_face > 0) == [True, True, False, False])
pw.geol_coll.remove_uid_property(uid=g_att, property_name="Normals")
stereo.flush_pending_updates()
app.processEvents()
check("removing Normals removes it from the stereoplot", g_att not in set(stereo.actors_df["uid"]))

# k-medoids on many vectors: no N x N matrices, fast
import time  # noqa: E402

t0 = time.perf_counter()
res = oa.kmedoids_clusters(many, 5, is_axial=True)
check("k-medoids, 100k axial vectors, k=5 in a few seconds",
      time.perf_counter() - t0 < 10 and len(res["labels"]) == len(many))

# Properties > Invert polarity
from pzero.orientation_analysis import normals2dip_directions  # noqa: E402
import pzero.point_clouds as pcs  # noqa: E402

check("Invert polarity in the Properties menu",
      pw.actionInvertPolarity in pw.menuProperties.actions())

# TriSurf with Normals and dip / dip direction: a plane dipping 30 toward east, but with upward
# normals (wrong polarity, as an upright limb that looks overturned)
tilted = pv.Plane(direction=(np.sin(np.radians(30)), 0, np.cos(np.radians(30))),
                  i_resolution=4, j_resolution=4).triangulate()
inv_surf = TriSurf()
inv_surf.ShallowCopy(tilted)
inv_surf.vtk_set_normals()
d = deepcopy(pw.geol_coll.entity_dict)
d.update(name="inv_surf", uid=str(uuid4()), topology="TriSurf", vtk_obj=inv_surf,
         properties_names=["Normals"], properties_components=[3])
g_inv = pw.geol_coll.add_entity_from_dict(entity_dict=d)
upward_before = float(np.mean(inv_surf.get_point_data("Normals")[:, 2])) > 0
pw.set_selection([g_inv], mode="replace")
pcs.normals2dd(pw)
dip0 = float(np.mean(inv_surf.get_point_data("Dip")))
dd0 = float(np.mean(inv_surf.get_point_data("Direction")))
check("starting surface: upward normals, dip 150 toward 270 (looks overturned)",
      upward_before and abs(dip0 - 150) < 1e-3 and abs(dd0 - 270) < 1e-3)
app.processEvents()
before_offsets = np.asarray(scatters(stereo.mpl_actors[g_inv])[0].get_offsets()).copy()
before_hollow = scatters(stereo.mpl_actors[g_inv])[0].get_facecolors()[:, 3] == 0
pw.set_selection([g_inv, g_line_noprops := add(pw.geol_coll, "PolyLine", PolyLine,
                  pv.Line((0, 0, 0), (1, 0, 0)), "plain_line", [])], mode="replace")
pw.set_selection([g_inv], mode="add")
messages.clear()
oa.invert_polarity(pw)
stereo.flush_pending_updates()
app.processEvents()
n_after = inv_surf.get_point_data("Normals")
check("Normals inverted (now downward)", float(np.mean(n_after[:, 2])) < 0)
check("dip / dip direction inverted consistently: 30 toward 90",
      abs(float(np.mean(inv_surf.get_point_data("Dip"))) - 30) < 1e-3
      and abs(float(np.mean(inv_surf.get_point_data("Direction"))) - 90) < 1e-3)
dips_from_normals, dirs_from_normals = normals2dip_directions(n_after)
check("Normals and dip / dip direction agree after the inversion",
      np.allclose(dips_from_normals, inv_surf.get_point_data("Dip"), atol=1e-3)
      and np.allclose(dirs_from_normals, inv_surf.get_point_data("Direction"), atol=1e-3))
inv_surf.vtk_set_normals()
check("Calculate Normals after the inversion keeps the new polarity (triangle order reversed)",
      float(np.mean(inv_surf.get_point_data("Normals")[:, 2])) < 0)
check("entity without Normals or dip / direction deselected with a message",
      pw.selection_uids() == [g_inv] and any("deselected" in m for m in messages))
after_scatter = scatters(stereo.mpl_actors[g_inv])[0]
check("stereoplot redrawn: poles move to the other side and change from hollow to filled",
      not np.allclose(np.asarray(after_scatter.get_offsets()), before_offsets)
      and before_hollow.all() and (after_scatter.get_facecolors()[:, 3] > 0).all())
# point set with dip / dip direction only, stored under older names (an entity not converted yet):
# Invert normals finds and updates them (both conventions for overturned planes)
att2 = pv.PolyData(np.random.default_rng(7).random((3, 3)))
att2["dip"] = np.array([30.0, -45.0, 135.0])
att2["dip direction"] = np.array([90.0, 90.0, 270.0])
d = deepcopy(pw.geol_coll.entity_dict)
d.update(name="att2", uid=str(uuid4()), topology="VertexSet", properties_names=["dip", "dip direction"],
         properties_components=[1, 1])
o2 = VertexSet()
o2.ShallowCopy(att2)
d["vtk_obj"] = o2
g_att2 = pw.geol_coll.add_entity_from_dict(entity_dict=d)
pw.set_selection([g_att2], mode="replace")
oa.invert_polarity(pw)
check("dip / direction only: 30/90 -> 150/270, -45/90 and 135/270 -> 45/90",
      np.allclose(o2.get_point_data("dip"), [150, 45, 45])
      and np.allclose(o2.get_point_data("dip direction"), [270, 90, 90])
      and "Normals" not in o2.point_data_keys)

# Select menu: "By polygon" (one-shot, no checkbox) and "Clear Selection"; Ctrl+A / Ctrl+Shift+A
from PySide6.QtCore import Qt as _Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

select_texts = [a.text() for a in stereo.menuSelect.actions()]
check("Select menu: By polygon and Clear Selection",
      "By polygon" in select_texts and "Clear Selection" in select_texts
      and not stereo.actionSelectionTool.isCheckable())
stereo.actionSelectionTool.trigger()
check("By polygon activates the region selection", stereo.selection_tool_active)
stereo._deactivate_selection()
check("... and deactivates after use", not stereo.selection_tool_active)

other = pw.geol_coll.add_entity_from_dict(entity_dict={**deepcopy(pw.geol_coll.entity_dict), "uid": str(uuid4()),
                                                       "name": "not_in_stereo", "topology": "PolyLine",
                                                       "vtk_obj": PolyLine()})
app.processEvents()
# a stereoplot in a dock of the shown project window, as opened from the Windows menu
from pzero.views.dock_window import DockWindow  # noqa: E402

pw.resize(1400, 900)
pw.show()
stereo_dock = DockWindow(parent=pw, window_type="ViewStereoplot")
sv = stereo_dock.canvas
pw.activateWindow()
for _ in range(10):
    app.processEvents()
QTest.mouseClick(sv.canvas, _Qt.LeftButton)  # the canvas takes the focus on click
app.processEvents()
check("clicking the stereoplot canvas gives it the keyboard focus", app.focusWidget() is sv.canvas)
shown_in_view = set(sv.shown_uids)
pw.set_selection([other], mode="replace")
QTest.keyClick(sv.canvas, _Qt.Key_A, _Qt.ControlModifier)
app.processEvents()
check("Ctrl+A on the stereoplot canvas selects the entities shown in the view (others kept)",
      shown_in_view and shown_in_view <= set(pw.selection_uids()) and other in pw.selection_uids())
for _ in range(3):
    app.processEvents()
ringed = {u for u in shown_in_view if sv.mpl_actors.get(u) is not None}
check("... and highlights them with yellow rings",
      sv.selection_highlight_actor is not None and sv.selection_highlight_uids == ringed
      and sv.selection_highlight_actor.get_markeredgecolor() == "yellow")
hidden_one = sorted(ringed)[0]
sv.actors_df.loc[sv.actors_df["uid"] == hidden_one, "show"] = False
sv.set_actor_visible(uid=hidden_one, visible=False)
for _ in range(3):
    app.processEvents()
check("a hidden entity stays selected but is not highlighted",
      hidden_one in pw.selection_uids() and hidden_one not in sv.selection_highlight_uids)
sv.actors_df.loc[sv.actors_df["uid"] == hidden_one, "show"] = True
sv.set_actor_visible(uid=hidden_one, visible=True)
QTest.keyClick(sv.canvas, _Qt.Key_A, _Qt.ControlModifier | _Qt.ShiftModifier)
app.processEvents()
check("Ctrl+Shift+A on the canvas deselects the entities of the view only",
      pw.selection_uids() == [other])
for _ in range(3):
    app.processEvents()
check("... and removes the highlight", sv.selection_highlight_actor is None)
pw.set_selection([f_pts], mode="replace")  # e.g. selected in a table
for _ in range(3):
    app.processEvents()
check("an entity selected elsewhere (table, other view) is highlighted",
      sv.selection_highlight_uids == {f_pts})
pw.set_selection([other], mode="replace")
sv.select_all_in_view()
sv.actionClearSelection.trigger()
check("Clear Selection deselects the entities of the view only", pw.selection_uids() == [other])

# By polygon with real mouse drags, also past the rim of the stereonet (matplotlib gives no
# stereonet coordinates outside the circle: a drag ending there used to select nothing)
from pzero.orientation_analysis import plunge_trends2lineations as _pt2l  # noqa: E402
from PySide6.QtCore import QPoint as _QPoint  # noqa: E402


def add_pole(name, trend, plunge):
    v = np.asarray(_pt2l(plunges=np.array([float(plunge)]), trends=np.array([float(trend)]))).reshape(1, 3)
    m = pv.PolyData(np.zeros((1, 3)))
    m["Normals"] = v
    return add(pw.geol_coll, "VertexSet", VertexSet, m, name, ["Normals"])


rim_e, mid_e, rim_w = add_pole("rim_east", 90, 5), add_pole("mid_east", 90, 45), add_pole("rim_west", 270, 5)
for _ in range(5):
    app.processEvents()
cxp, cyp = sv.ax.transAxes.transform((0.5, 0.5))
rxp = sv.ax.transAxes.transform((1.0, 0.5))[0] - cxp
ratio = sv.canvas.devicePixelRatioF()


def screen(theta_deg, radius):
    t = np.radians(theta_deg)
    x, y = cxp + radius * rxp * np.sin(t), cyp + radius * rxp * np.cos(t)
    return _QPoint(int(round(x / ratio)), int(round(sv.canvas.height() - y / ratio)))


def drag(a, b):
    pw.set_selection(mode="clear")
    sv.actionSelectionTool.trigger()
    for _ in range(3):
        app.processEvents()  # pending redraws (e.g. of the selection highlight) before the drag
    QTest.mousePress(sv.canvas, _Qt.LeftButton, _Qt.NoModifier, a)
    full_draws = []
    original_draw = sv.figure.canvas.draw
    sv.figure.canvas.draw = lambda *args, **kwargs: (full_draws.append(1), original_draw(*args, **kwargs))
    for step in np.linspace(0, 1, 6)[1:]:  # several mouse movements
        QTest.mouseMove(sv.canvas, a + (b - a) * float(step))
        app.processEvents()
    sv.figure.canvas.draw = original_draw
    xy = sv.selection_patch.get_xy() if sv.selection_patch is not None else np.zeros((0, 2))
    # drawn in axes coordinates, inside the stereonet circle, no full redraw while dragging
    patch_ok = (sv.selection_patch is not None and np.isfinite(xy).all()
                and sv.selection_patch.get_transform() == sv.ax.transAxes
                and (np.hypot(xy[:, 0] - 0.5, xy[:, 1] - 0.5) <= 0.5 + 1e-6).all()
                and not full_draws)
    QTest.mouseRelease(sv.canvas, _Qt.LeftButton, _Qt.NoModifier, b)
    app.processEvents()
    sv._deactivate_selection()
    return set(pw.selection_uids()) & {rim_e, mid_e, rim_w}, patch_ok


check("By polygon inside the circle", drag(screen(80, 0.8), screen(100, 0.98))[0] == {rim_e})
selected, patch_ok = drag(screen(80, 0.8), screen(100, 1.2))
check("By polygon released past the rim: selects up to the rim, region drawn correctly",
      selected == {rim_e} and patch_ok)
check("By polygon pressed past the rim", drag(screen(80, 1.3), screen(100, 0.8))[0] == {rim_e})
check("By polygon from the centre area to past the rim", drag(screen(80, 0.3), screen(100, 1.35))[0] == {rim_e, mid_e})
check("a press far from the net does not start a region", drag(screen(80, 1.8), screen(100, 0.5))[0] == set())

# Move to another collection: the table tab follows
pw.show_collection_tab("geol_coll")
pw.set_selection([other], mode="replace")
pw.transfer_entities_between_collections(
    source_collection_name="geol_coll", destination_collection_name="fluid_coll",
    selected_uids=[other], move=True,
)
check("after Move to Fluids the Fluids tab is in front and the entity stays selected",
      pw.tabWidgetTopLeft.currentWidget() is pw.tabFluids and pw.selection_uids() == [other])

# ---- Analysis > Contour settings (methods of mplstereonet) and Axial / Polar data
import pzero.views.view_stereoplot as vsp  # noqa: E402
from pzero.orientation_analysis import DENSITY_METHODS  # noqa: E402

analysis_texts = [a.text() for a in stereo.menuAnalysis.actions()]
check("Analysis menu: Contour settings, Axial (bidirectional) / Polar (unidirectional) data",
      {"Contour settings...", "Axial (bidirectional) data", "Polar (unidirectional) data"} <= set(analysis_texts)
      and stereo.data_axial and stereo.actionAxialData.isChecked() and not stereo.actionPolarData.isChecked())

vectors = unit(np.random.default_rng(11).normal(size=(60, 3)) * [0.4, 0.4, 1] + [0.3, 0, -1])
pl, tr = mplstereonet.vector2plunge_bearing(*vectors.T)
lo, la = mplstereonet.line(pl, tr)
same = True
for method in DENSITY_METHODS:
    for sigma in (3.0, 1.0):
        ours = kamb_density_grid(lo, la, method=method, sigma=sigma)[2]
        theirs = density_grid(pl, tr, measurement="lines", method=method, sigma=sigma)[2]
        tiny = np.finfo(float).tiny
        ours, theirs = np.where(ours <= tiny, 0, ours), np.where(theirs <= tiny, 0, theirs)
        same &= np.allclose(ours, theirs, rtol=1e-9, atol=1e-12 * max(theirs.max(), 1))
check("all contour methods (exponential / linear Kamb, Kamb 1959, Schmidt) equal mplstereonet", same)

# near-horizontal lineations toward 315: axial counting also fills the opposite rim (135), polar does not
horizontal = unit(np.random.default_rng(12).normal(size=(40, 3)) * [0.03, 0.03, 0.02] + [-0.7, 0.7, -0.12])
check("test data: all lineations point downwards (plunge > 0)", (horizontal[:, 2] < 0).all())
pl, tr = mplstereonet.vector2plunge_bearing(*horizontal.T)
lo, la = mplstereonet.line(pl, tr)
opposite = mplstereonet.line(2.0, 135.0)


def density_at(lon_grid, lat_grid, density, point):
    index = np.argmin((lon_grid - point[0][0]) ** 2 + (lat_grid - point[1][0]) ** 2)
    return density.ravel()[index]


axial_grid = kamb_density_grid(lo, la, axial=True)
polar_grid = kamb_density_grid(lo, la, axial=False)
check("axial: density also on the opposite rim; polar: none there",
      density_at(*axial_grid, opposite) > 1.0 and density_at(*polar_grid, opposite) < 1e-6)

vsp.multiple_input_dialog = lambda **kw: {"method": "Schmidt (1% area)", "sigma": "3"}
stereo.contours = False
stereo.set_contour_settings()
app.processEvents()
check("Contour settings: Schmidt chosen, pooled contours redrawn with it",
      stereo.density_method == "schmidt" and stereo.pooled_contour_actor is not None)
messages.clear()
vsp.multiple_input_dialog = lambda **kw: {"method": "Exponential Kamb (Vollmer 1995)", "sigma": "-1"}
stereo.set_contour_settings()
check("invalid sigma refused", stereo.density_method == "schmidt" and any("Invalid sigma" in m for m in messages))
vsp.multiple_input_dialog = lambda **kw: {"method": "Exponential Kamb (Vollmer 1995)", "sigma": "1.5"}
stereo.set_contour_settings()
check("Contour settings: exponential Kamb, sigma 1.5", stereo.density_method == "exponential_kamb" and stereo.density_sigma == 1.5)

stereo.actionPolarData.trigger()
stereo.recompute_values()
check("Polar data: statistics keep upward normals (no folding to the lower hemisphere)",
      not stereo.data_axial and stereo.actionPolarData.isChecked()
      and (np.asarray(stereo.last_normals_array, dtype=float)[:, 2] > 0).any())
stereo.actionAxialData.trigger()
stereo.recompute_values()
check("Axial data: normals folded to the lower hemisphere again",
      stereo.data_axial and (np.asarray(stereo.last_normals_array, dtype=float)[:, 2] <= 0).all())
stereo.density_sigma = 3.0
stereo.contours = None

# ---- menus: Analysis order; View > Contour display settings (colour, contours-only threshold)
from PySide6.QtWidgets import QWidgetAction as _QWidgetAction  # noqa: E402


def menu_layout(menu):
    out = []
    for action in menu.actions():
        if action.isSeparator():
            out.append("|" + action.text())
        elif isinstance(action, _QWidgetAction):
            out.append("<k>")
        else:
            out.append(action.text())
    return out


check("Analysis menu order",
      menu_layout(stereo.menuAnalysis) == [
          "Polar (unidirectional) data", "Axial (bidirectional) data", "|",
          "Contour settings...", "|Fisher",
          "Mean direction as pole", "|Bingham",
          "Major axis as pole", "Intermediate axis as pole", "Minor axis as pole", "Great circle ⊥ minor axis", "|K-medoids",
          "<k>", "Seed picking for clustering (Normals objects)", "Seed picking for clustering (Lineations objects)",
          "Cluster centers as poles", "Color Clusters", "Save cluster ID as property", "Show statistics",
      ])
view_texts = [a.text() for a in stereo.menuView.actions()]
check("View menu: Contour display settings (no separate threshold item)",
      "Contour display settings..." in view_texts and "Contours-only threshold..." not in view_texts)

stereo.contours = True
stereo._update_pooled_contours()
check("filled contours keep their contour lines on top",
      stereo.pooled_contour_actor.filled and stereo.pooled_contour_lines is not None
      and not stereo.pooled_contour_lines.filled)
blue_fill = np.asarray(stereo.pooled_contour_actor.get_facecolor())[-1]
vsp.multiple_input_dialog = lambda **kw: {"color": "Red", "threshold": str(stereo.contours_only_threshold)}
stereo.set_contour_display()
red_fill = np.asarray(stereo.pooled_contour_actor.get_facecolor())[-1]
red_line = np.asarray(stereo.pooled_contour_lines.get_edgecolor())[-1]
check("Contour display settings: base colour Red for fills and lines",
      stereo.contour_color == "Red" and blue_fill[2] > blue_fill[0] and red_fill[0] > red_fill[2]
      and red_line[0] > red_line[2])
check("... the contours-only entity is still drawn as contours",
      any(isinstance(a, ContourSet) for a in stereo.mpl_actors[g_big].artists))
vsp.multiple_input_dialog = lambda **kw: {"color": "Red", "threshold": "100000"}
stereo.set_contour_display()
check("contours-only threshold set in Contour display settings: the large entity gets markers",
      stereo.contours_only_threshold == 100000 and scatters(stereo.mpl_actors[g_big]))
vsp.multiple_input_dialog = lambda **kw: {"color": "Blue", "threshold": "500"}
stereo.set_contour_display()
stereo.contours = None
stereo._update_pooled_contours()
check("contours off: fills and lines removed",
      stereo.pooled_contour_actor is None and stereo.pooled_contour_lines is None)

asked_save = []
vsp.multiple_input_dialog = lambda **kw: asked_save.append(kw) or None
messages.clear()
stereo.actionExportStats.trigger()
check("Show statistics prints the summary, no save dialog",
      not asked_save and any("Orientation Statistics Summary" in m for m in messages))

# ---- k-medoids: exactly k clusters for any k (axial data are doubled; opposite copies merged)
from pzero.orientation_analysis import kmedoids_clusters, plunge_trends2lineations  # noqa: E402

rng_k = np.random.default_rng(0)


def k_group(n, trend, plunge):
    v = np.asarray(plunge_trends2lineations(plunges=np.full(n, float(plunge)), trends=np.full(n, float(trend))))
    return unit(v + rng_k.normal(size=(n, 3)) * 0.1)


four_groups = np.vstack([k_group(300, 140, 50), -k_group(200, 40, 20), k_group(250, 260, 70), k_group(150, 330, 10)])
counts_ok = all(len(kmedoids_clusters(four_groups, k, is_axial=True)["centroids"]) == k for k in range(1, 7))
check("axial k-medoids: k centres for k = 1..6 (even k gave k/2 before)", counts_ok)
result4 = kmedoids_clusters(four_groups, 4, is_axial=True)
check("axial k-medoids, k = 4: the four groups recovered (one given as upward vectors)",
      sorted(np.bincount(result4["labels"]).tolist()) == [150, 200, 250, 300]
      and (np.asarray(result4["centroids"])[:, 2] <= 0).all())
result4p = kmedoids_clusters(four_groups, 4, is_axial=False)
check("polar k-medoids, k = 4: four groups, the upward one with an upward centre",
      sorted(np.bincount(result4p["labels"]).tolist()) == [150, 200, 250, 300]
      and (np.asarray(result4p["centroids"])[:, 2] > 0).sum() == 1)

print("RESULT:", "FAILED" if failed else "ALL PASSED")
