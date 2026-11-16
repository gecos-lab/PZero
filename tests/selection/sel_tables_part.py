# Phase 2 checks: table adapter. Executed inside test_selection_store.py (pw, check, pd exist).
from PySide6.QtCore import QItemSelectionModel as _QISM, Qt as _Qt

# After create_empty there are new collections and new connections: fill them via modelReset.
for _coll_name, _uids in (("geol_coll", ["g1", "g2", "g3", "g4"]), ("dom_coll", ["d1", "d2"])):
    _coll = getattr(pw, _coll_name)
    _coll.table_model.beginResetModel()
    _coll.df = pd.concat([_coll.df, pd.DataFrame({"uid": _uids, "name": _uids})], ignore_index=True)
    _coll.table_model.endResetModel()

_tv = pw.GeologyTableView
pw.tabWidgetTopLeft.setCurrentWidget(pw.tabGeology)


def _table_uids(tv):
    return sorted(pw.get_selected_uids_from_table(table_view=tv))


# outbound: select rows in the table -> store
_tv.selectionModel().select(
    _tv.model().index(1, 0), _QISM.ClearAndSelect | _QISM.Rows
)
check("table -> store", pw.geol_coll.selected_uids == ["g2"])
check("ProjectWindow.selected_uids follows store", pw.selected_uids == ["g2"])

# inbound: store -> table (e.g. from a tree)
pw.geol_coll.selected_uids = ["g1", "g3", "g4"]
check("store -> table", _table_uids(_tv) == ["g1", "g3", "g4"])
check("no echo back into store", pw.geol_coll.selected_uids == ["g1", "g3", "g4"])

# other collection untouched by geology table sync
pw.set_selection(["d2"], mode="add")
check("dom table synced", _table_uids(pw.DOMsTableView) == ["d2"])
check("geology table unchanged", _table_uids(_tv) == ["g1", "g3", "g4"])

# selected_uids is scoped to the shown tab (the add above brought DOMs to front)
pw.tabWidgetTopLeft.setCurrentWidget(pw.tabGeology)
check("shown tab scoping (geology)", sorted(pw.selected_uids) == ["g1", "g3", "g4"])
pw.tabWidgetTopLeft.setCurrentWidget(pw.tabDOMs)
check("shown tab scoping (doms)", pw.selected_uids == ["d2"])
pw.tabWidgetTopLeft.setCurrentWidget(pw.tabGeology)

# sorted proxy: rows mapped through the proxy
_tv.model().sort(0, _Qt.DescendingOrder)
pw.geol_coll.selected_uids = ["g1"]
check("sorted proxy mapping", _table_uids(_tv) == ["g1"])

# model reset (entities added) restores table selection from store
pw.geol_coll.table_model.beginResetModel()
pw.geol_coll.df = pd.concat([pw.geol_coll.df, pd.DataFrame({"uid": ["g5"], "name": ["g5"]})], ignore_index=True)
pw.geol_coll.table_model.endResetModel()
check("selection restored after model reset", _table_uids(_tv) == ["g1"])

# table clear -> store clear for that collection only
_tv.clearSelection()
check("table clear -> store", pw.geol_coll.selected_uids == [] and pw.dom_coll.selected_uids == ["d2"])

# prune -> table
pw.geol_coll.selected_uids = ["g2", "g3"]
pw.signals.entities_removed.emit(["g3"], pw.geol_coll)
check("prune -> table", _table_uids(_tv) == ["g2"])

# tab follows selections made outside the tables (trees/views/collection API)
pw.tabWidgetTopLeft.setCurrentWidget(pw.tabGeology)
pw.dom_coll.selected_uids = ["d1"]  # e.g. from a DOM tree in a view
check("tab brought to front on view/tree selection", pw.shown_table == "tabDOMs")
check("selected_uids matches new tab", pw.selected_uids == ["d1"])
pw.dom_coll.selected_uids = []  # deselection does not switch
pw.tabWidgetTopLeft.setCurrentWidget(pw.tabGeology)
pw.signals.entities_removed.emit(["g2"], pw.geol_coll)
check("prune does not switch tab", pw.shown_table == "tabGeology")
pw.tabWidgetTopLeft.setCurrentWidget(pw.tabGeology)
pw.DOMsTableView.selectionModel().select(pw.DOMsTableView.model().index(1, 0), _QISM.ClearAndSelect | _QISM.Rows)
check("table selection does not switch tab", pw.shown_table == "tabGeology")

# click order preserved by table selections (replace keeps existing positions)
pw.tabWidgetTopLeft.setCurrentWidget(pw.tabGeology)
pw.set_selection(mode="clear")
_m = _tv.model()
def _row_of(uid):
    return next(r for r in range(_m.rowCount()) if _m.index(r, 0).data() == uid)
_tv.selectionModel().select(_m.index(_row_of("g4"), 0), _QISM.ClearAndSelect | _QISM.Rows)
_tv.selectionModel().select(_m.index(_row_of("g1"), 0), _QISM.Select | _QISM.Rows)
_tv.selectionModel().select(_m.index(_row_of("g5"), 0), _QISM.Select | _QISM.Rows)
check("table keeps click order", pw.geol_coll.selected_uids == ["g4", "g1", "g5"])
