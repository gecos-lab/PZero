"""Headless check of the phase-1 project selection store."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))

from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)

from pzero.project_window import ProjectWindow  # noqa: E402

pw = ProjectWindow()

# Fake uids in two collections, by appending minimal rows to the dataframes.
import pandas as pd  # noqa: E402

for coll_name, uids in (("geol_coll", ["g1", "g2", "g3"]), ("dom_coll", ["d1", "d2"])):
    coll = getattr(pw, coll_name)
    coll.df = pd.concat([coll.df, pd.DataFrame({"uid": uids})], ignore_index=True)

events = []
legacy = []
pw.signals.selection_modified.connect(lambda a, r, c, s: events.append((a, r, s)))
pw.signals.selection_changed.connect(lambda c: legacy.append(c.collection_name))


def check(label, cond):
    print(("PASS " if cond else "FAIL ") + label)
    if not cond:
        global failed
        failed = True


failed = False

# collection setter -> store
pw.geol_coll.selected_uids = ["g1", "g2"]
check("collection setter writes store", pw.selection_uids() == ["g1", "g2"])
check("collection getter reads store", pw.geol_coll.selected_uids == ["g1", "g2"])
check("signal emitted once", len(events) == 1 and events[0][0] == ["g1", "g2"])
check("legacy signal for geol_coll", legacy == ["geol_coll"])
check("active collection", pw.active_selection_collection == "geol_coll")

# getter returns a copy
pw.geol_coll.selected_uids.append("g3")
check("getter returns copy", pw.geol_coll.selected_uids == ["g1", "g2"])

# no-op replace emits nothing
n = len(events)
pw.geol_coll.selected_uids = ["g1", "g2"]
check("no-op replace silent", len(events) == n)

# cross-collection add with lookup
pw.set_selection(["d1"], mode="add")
check("cross-collection add", pw.selection_uids() == ["g1", "g2", "d1"])
check("lookup resolved dom_coll", pw.dom_coll.selected_uids == ["d1"])
check("active follows last add", pw.active_selection_collection == "dom_coll")

# replace scoped to one collection keeps others
pw.geol_coll.selected_uids = ["g3"]
check("scoped replace keeps dom", pw.selection_uids() == ["d1", "g3"])

# toggle
pw.set_selection(["g3", "g1"], mode="toggle")
check("toggle", pw.selection_uids() == ["d1", "g1"])

# unknown uid ignored
check("unknown uid ignored", pw.set_selection(["zzz"], mode="add") is False)

# select_all / deselect_uids helpers
pw.geol_coll.select_all()
check("select_all", set(pw.geol_coll.selected_uids) == {"g1", "g2", "g3"})
pw.geol_coll.deselect_uids(["g2"])
check("deselect_uids", set(pw.geol_coll.selected_uids) == {"g1", "g3"})

# pruning on entities_removed
pw.signals.entities_removed.emit(["g1"], pw.geol_coll)
check("prune removed uid", not pw.is_selected("g1"))

# clear scoped then global
pw.set_selection(mode="clear", collection="dom_coll")
check("scoped clear", pw.selection_uids() == ["g3"])
pw.set_selection(mode="clear")
check("global clear", pw.selection_uids() == [] and pw.active_selection_collection is None)

# new project resets
pw.geol_coll.selected_uids = ["g2"]
pw.create_empty()
check("create_empty resets store", pw.selection_uids() == [])

# --- phase 2 tests inserted below ---
exec(open(__file__.replace("sel_store_and_tables", "sel_tables_part")).read())
print("RESULT:", "FAILED" if failed else "ALL PASSED")
