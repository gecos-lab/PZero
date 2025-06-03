from PySide6.QtWidgets import QTreeWidgetItem, QComboBox
from PySide6.QtCore import Qt

from pandas import unique as pd_unique

"""Methods used to build and update the GEOLOGY and TOPOLOGY trees."""


def create_geology_tree(self):
    """Create geology tree with checkboxes and properties"""
    # Send messages. Note that with tristate several signals are emitted in a sequence, one for each
    # changed item, but upper levels do not broadcast uid's so they are filtered in the toggle method.
    self.GeologyTreeWidget.itemChanged.connect(self.toggle_geology_visibility)


def update_geology_tree_added(self, uid_list=None):
    """Update geology tree without creating a new model"""
    self.GeologyTreeWidget.itemChanged.connect(self.toggle_geology_visibility)


def update_geology_tree_removed(self, removed_list=None):
    """When geological entity is removed, update Geology Tree without building a new model"""


def toggle_geology_visibility(self, item):
    """Called by self.GeologyTreeWidget.itemChanged.connect(self.toggle_geology_visibility ) and
    self.GeologyTopologyTreeWidget.itemChanged.connect(self.toggle_geology_visibility )
    """
    # name = item.text(0)  # not used
    uid = item.text(1)
    uid_checkState = item.checkState(0)
    # needed to skip messages from upper levels of tree that do not broadcast uid's
    if uid:
        if uid_checkState == Qt.Checked:
            if not self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                self.actors_df.loc[self.actors_df["uid"] == uid, "show"] = True
                self.set_actor_visible(uid=uid, visible=True)
        elif uid_checkState == Qt.Unchecked:
            if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                self.actors_df.loc[self.actors_df["uid"] == uid, "show"] = False
                self.set_actor_visible(uid=uid, visible=False)
        # Before updating checkboxes, disconnect signals to geology and topology tree, if they are set,
        # to avoid a nasty loop that disrupts the trees, then reconnect them (it is also possible that
        # they are automatically reconnected whe the trees are rebuilt.
        self.GeologyTreeWidget.itemChanged.disconnect()
        self.GeologyTopologyTreeWidget.itemChanged.disconnect()
        update_geology_checkboxes(self, uid=uid, uid_checkState=uid_checkState)
        update_topology_checkboxes(self, uid=uid, uid_checkState=uid_checkState)
        self.GeologyTreeWidget.itemChanged.connect(self.toggle_geology_visibility)
        self.GeologyTopologyTreeWidget.itemChanged.connect(
            self.toggle_geology_visibility
        )
