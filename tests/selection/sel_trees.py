"""Headless check of phase 3: trees mirror the project selection store."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QItemSelectionModel as QISM, Qt

app = QApplication.instance() or QApplication(sys.argv)
from pzero.project_window import ProjectWindow  # noqa: E402
from pzero.views.view_tree import CustomTreeWidget  # noqa: E402
from pzero.views.abstract_base_view import BaseView  # noqa: E402
import pandas as pd  # noqa: E402

pw = ProjectWindow()
rows = []
for uid, role, feature in (
    ("g1", "fault", "F1"), ("g2", "fault", "F1"), ("g3", "fault", "F2"),
    ("g4", "top", "H1"), ("g5", "top", "H1"),
):
    rows.append({"uid": uid, "name": f"n{uid}", "role": role, "feature": feature})
coll = pw.geol_coll
coll.table_model.beginResetModel()
coll.df = pd.DataFrame(rows)
coll.table_model.endResetModel()


class FakeView:
    """Minimal stand-in for a BaseView: parent, actors_df, trees, selection dispatcher."""

    collection_tree_dict = {"geol_coll": "GeologyTreeWidget"}
    selection_modified_update_trees = BaseView.selection_modified_update_trees

    def __init__(self, uids):
        self.parent = pw
        self.actors_df = pd.DataFrame({"uid": uids, "show": True, "show_property": "none", "collection": "geol_coll"})
        self.GeologyTreeWidget = CustomTreeWidget(
            view=self, collection=coll, tree_labels=["role", "feature"],
            name_label="name", uid_label="uid", default_labels=["none"],
        )
        self.lmb = lambda a, r, c, s: self.selection_modified_update_trees(collections=c, source=s)
        pw.signals.selection_modified.connect(self.lmb)


view_a = FakeView(["g1", "g2", "g3", "g4", "g5"])
view_b = FakeView(["g1", "g2", "g3"])  # e.g. a cross-section showing a subset
ta, tb = view_a.GeologyTreeWidget, view_b.GeologyTreeWidget

failed = False


def check(label, cond):
    global failed
    print(("PASS " if cond else "FAIL ") + label)
    failed |= not cond


def item(tree, text):
    return next(i for i in tree.findItems(text, Qt.MatchExactly | Qt.MatchRecursive, 1 if text.startswith("n") else 0))


def sel_uids(tree):
    return sorted(u for u in (tree.get_item_uid(i) for i in tree.selectedItems()) if u)


def click(tree, it, ctrl=False):
    """Emulate a user click: set current, then select (ClearAndSelect or Toggle)."""
    idx = tree.indexFromItem(it, 0)
    flag = (QISM.Toggle if ctrl else QISM.ClearAndSelect) | QISM.Rows
    tree.selectionModel().setCurrentIndex(idx, QISM.NoUpdate)
    tree.selectionModel().select(idx, flag)


# 1. click a leaf in tree A -> store, tree B, table
click(ta, item(ta, "ng1"))
check("leaf click -> store", coll.selected_uids == ["g1"])
check("tree B mirrors", sel_uids(tb) == ["g1"])
check("table mirrors", sorted(pw.get_selected_uids_from_table(pw.GeologyTableView)) == ["g1"])

# 2. click group F1 -> selects g1, g2; group shown selected
click(ta, item(ta, "F1"))
check("group click selects entities", sorted(coll.selected_uids) == ["g1", "g2"])
check("group item shown selected in A", item(ta, "F1").isSelected())
check("group item shown selected in B", item(tb, "F1").isSelected())

# 3. ctrl-click group "fault" (adds g3)
click(ta, item(ta, "fault"), ctrl=True)
check("ctrl-click parent group adds all", sorted(coll.selected_uids) == ["g1", "g2", "g3"])

# 4. ctrl-click group "fault" again -> deselect all its entities
click(ta, item(ta, "fault"), ctrl=True)
check("ctrl-click selected group deselects all", coll.selected_uids == [])

# 5. select group F1, then plain-click its leaf g1 -> only g1
click(ta, item(ta, "F1"))
click(ta, item(ta, "ng1"))
check("plain click leaf inside selected group", coll.selected_uids == ["g1"])
check("group no longer shown selected", not item(ta, "F1").isSelected())

# 6. ctrl-click leaf inside fully selected group -> group unselected, other leaf stays
click(ta, item(ta, "F1"))
click(ta, item(ta, "ng2"), ctrl=True)
check("ctrl-deselect leaf in group", coll.selected_uids == ["g1"])
check("group unselected after partial", not item(ta, "F1").isSelected())

# 7. subset tree B: plain click in B keeps selection of entities not in B
coll.selected_uids = ["g4", "g5"]
check("store -> both trees", sel_uids(ta) == ["g4", "g5"] and sel_uids(tb) == [])
click(tb, item(tb, "ng1"))
check("click in subset tree keeps unseen entities", sorted(coll.selected_uids) == ["g1", "g4", "g5"])
check("tree A follows B", sel_uids(ta) == ["g1", "g4", "g5"])

# 8. tree rebuild (header buttons) keeps selection
ta.populate_tree()
check("populate_tree restores selection", sel_uids(ta) == ["g1", "g4", "g5"])
check("store untouched by rebuild", sorted(coll.selected_uids) == ["g1", "g4", "g5"])

# 9. removing items from a tree does not change the store
tb.remove_items_from_tree(["g1"])
check("tree item removal leaves store", sorted(coll.selected_uids) == ["g1", "g4", "g5"])

# 10. table selection -> trees
pw.GeologyTableView.selectionModel().select(pw.GeologyTableView.model().index(2, 0), QISM.ClearAndSelect | QISM.Rows)
check("table -> tree A", sel_uids(ta) == ["g3"])

# 11. tab switching from tree, including clicking an already-selected item
pw.tabWidgetTopLeft.setCurrentWidget(pw.tabDOMs)
click(ta, item(ta, "ng4"))
check("tree selection brings tab to front", pw.shown_table == "tabGeology")
pw.tabWidgetTopLeft.setCurrentWidget(pw.tabDOMs)
ta.itemClicked.emit(item(ta, "ng4"), 1)
check("click on selected item brings tab to front", pw.shown_table == "tabGeology")

# 12. restore_selection (stereoplot lasso) goes through the store
tb.restore_selection(["g2"])
check("restore_selection -> store and other tree", coll.selected_uids == ["g2"] and sel_uids(ta) == ["g2"])

print("RESULT:", "FAILED" if failed else "ALL PASSED")
