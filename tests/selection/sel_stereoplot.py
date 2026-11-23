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
check("no arcsin warning from analysis overlays",
      not any("arcsin" in str(w.message) for w in caught))

check("biaxial k-medoids note printed when the k-medoids boxes are checked",
      any("k-medoids on Normals is biaxial" in m for m in messages))

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

print("RESULT:", "FAILED" if failed else "ALL PASSED")
