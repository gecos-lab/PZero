"""Headless check: tools deselect entities they cannot use (restrict_selection_for_tool / @uses_selection)."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))

from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)
import pandas as pd  # noqa: E402
from pzero.project_window import ProjectWindow  # noqa: E402
from pzero.helpers.helper_functions import uses_selection  # noqa: E402

pw = ProjectWindow()
for coll_name, rows in (
    ("geol_coll", [("s1", "TriSurf"), ("s2", "TriSurf"), ("l1", "PolyLine"), ("p1", "VertexSet")]),
    ("dom_coll", [("pc1", "PCDom"), ("dem1", "DEM")]),
    ("mesh3d_coll", [("v1", "Voxet")]),
):
    coll = getattr(pw, coll_name)
    coll.table_model.beginResetModel()
    coll.df = pd.DataFrame({"uid": [r[0] for r in rows], "name": [r[0] for r in rows], "topology": [r[1] for r in rows]})
    coll.table_model.endResetModel()

failed = False


def check(label, cond):
    global failed
    print(("PASS " if cond else "FAIL ") + label)
    failed |= not cond


ran = []


@uses_selection(valid={"geol_coll": ["TriSurf"]})
def trisurf_tool(self):
    ran.append(list(self.selected_uids))


@uses_selection(valid={"dom_coll": ["PCDom"]}, max_selected=1)
def pc_tool(self):
    ran.append(list(self.selected_uids))


@uses_selection(valid=None)
def any_tool(self):
    ran.append(list(self.selected_uids))


def select(*uids):
    pw.set_selection(mode="clear")
    for u in uids:
        pw.set_selection([u], mode="add")


# TriSurf-only tool with surfaces, a line, a point cloud and a voxet selected
select("s1", "l1", "pc1", "s2", "v1")
trisurf_tool(pw)
check("trisurf tool runs on surfaces only", ran[-1] == ["s1", "s2"])
check("non-surfaces deselected", pw.selection_uids() == ["s1", "s2"])
check("geology tab in front", pw.shown_table == "tabGeology")

# point-cloud single-entity tool: last selected PCDom, DOM tab brought to front
pw.dom_coll.table_model.beginResetModel()
pw.dom_coll.df = pd.concat([pw.dom_coll.df, pd.DataFrame({"uid": ["pc2"], "name": ["pc2"], "topology": ["PCDom"]})], ignore_index=True)
pw.dom_coll.table_model.endResetModel()
select("pc1", "s1", "pc2", "dem1")
pc_tool(pw)
check("pc tool takes last selected point cloud", ran[-1] == ["pc2"])
check("only that point cloud stays selected", pw.selection_uids() == ["pc2"])
check("DOM tab in front", pw.shown_table == "tabDOMs")

# not enough usable entities: tool does not run, selection unchanged
n = len(ran)
select("l1", "dem1")
trisurf_tool(pw)
check("tool not run without usable entities", len(ran) == n)
check("selection unchanged when tool cannot run", pw.selection_uids() == ["l1", "dem1"])

# generic tool: works on one collection (the shown tab's), deselects others
select("s1", "pc1", "l1")
pw.tabWidgetTopLeft.setCurrentWidget(pw.tabGeology)
any_tool(pw)
check("generic tool keeps shown tab collection", ran[-1] == ["s1", "l1"])
check("other collections deselected", pw.selection_uids() == ["s1", "l1"])

# shown tab without usable entities: falls back to the collection of the last usable one
select("s1", "pc1")
pw.tabWidgetTopLeft.setCurrentWidget(pw.tabMeshes)
any_tool(pw)
check("falls back to last selected collection", ran[-1] == ["pc1"] and pw.shown_table == "tabDOMs")

# real decorated project tool spec is attached (smoke): entity_remove keeps one collection
select("s1", "pc1")
pw.tabWidgetTopLeft.setCurrentWidget(pw.tabGeology)
check("restrict helper returns chosen", pw.restrict_selection_for_tool(valid=None) == ["s1"])

print("RESULT:", "FAILED" if failed else "ALL PASSED")
