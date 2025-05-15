from PySide6.QtWidgets import QTreeWidgetItem
from PySide6.QtCore import Qt

"""Methods used to build and update the X-SECTION table."""


def create_xsections_tree(self):
    """Create XSection tree with checkboxes and properties"""
    self.XSectionTreeWidget.clear()
    self.XSectionTreeWidget.setColumnCount(2)
    self.XSectionTreeWidget.setHeaderLabels(["Name", "uid"])
    self.XSectionTreeWidget.hideColumn(1)  # hide the uid column
    self.XSectionTreeWidget.setItemsExpandable(True)
    name_xslevel1 = ["All XSections"]
    # self.XSectionTreeWidget as parent -> top level
    xslevel_1 = QTreeWidgetItem(self.XSectionTreeWidget, name_xslevel1)
    xslevel_1.setFlags(
        xslevel_1.flags() | Qt.ItemIsUserTristate | Qt.ItemIsUserCheckable
    )
    # The following manages the exception when a X sections wants to show itself.
    try:
        uids = self.parent.xsect_coll.df.query(self.view_filter)["uid"].to_list()
    except:
        uids = [self.this_x_section_uid]
    for uid in uids:
        # Do not use query here, it's not necessary and will rise errors.
        name = self.parent.xsect_coll.df.loc[
            self.parent.xsect_coll.df["uid"] == uid, "name"
        ].values[0]
        # xslevel_2 as parent -> lower level
        xslevel_2 = QTreeWidgetItem(xslevel_1, [name, uid])
        xslevel_2.setFlags(xslevel_2.flags() | Qt.ItemIsUserCheckable)
        if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
            xslevel_2.setCheckState(0, Qt.Checked)
        elif not self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
            xslevel_2.setCheckState(0, Qt.Unchecked)
    # Send messages. Note that with tristate several signals are emitted in a sequence, one for each
    # changed item, but upper levels do not broadcast uid's so they are filtered in the toggle method
    self.XSectionTreeWidget.itemChanged.connect(self.toggle_xsection_visibility)
    # Squeeze column width to fit content
    for col in range(self.XSectionTreeWidget.columnCount()):
        self.XSectionTreeWidget.resizeColumnToContents(col)
    self.XSectionTreeWidget.expandAll()


def update_xsections_tree_added(self, new_list=None, sec_uid=None):
    """Update XSection tree without creating a new model"""
    uid_list = list(new_list["uid"])
    if sec_uid:
        for i, uid in enumerate(new_list["uid"]):
            if sec_uid != uid:
                del uid_list[i]
    for uid in uid_list:
        name = self.parent.xsect_coll.get_uid_name(uid)
        xslevel_2 = QTreeWidgetItem(
            self.XSectionTreeWidget.findItems("All XSections", Qt.MatchExactly, 0)[0],
            [name, uid],
        )
        xslevel_2.setFlags(xslevel_2.flags() | Qt.ItemIsUserCheckable)
        if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
            xslevel_2.setCheckState(0, Qt.Checked)
        elif not self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
            xslevel_2.setCheckState(0, Qt.Unchecked)
    self.XSectionTreeWidget.itemChanged.connect(self.toggle_xsection_visibility)
    # Squeeze column width to fit content
    for col in range(self.XSectionTreeWidget.columnCount()):
        self.XSectionTreeWidget.resizeColumnToContents(col)
    self.XSectionTreeWidget.expandAll()


def update_xsections_tree_removed(self, removed_list=None):
    """Update XSection tree without creating a new model"""
    success = 0
    for uid in removed_list:
        for top_box in range(self.XSectionTreeWidget.topLevelItemCount()):
            """Iterate through every Collection top level"""
            for child_xsect in range(
                self.XSectionTreeWidget.topLevelItem(top_box).childCount()
            ):
                """Iterate through every XSection"""
                if (
                    self.XSectionTreeWidget.topLevelItem(top_box)
                    .child(child_xsect)
                    .text(1)
                    == uid
                ):
                    """Complete check: entity found has the uid of the entity we need to remove. Delete child"""
                    success = 1
                    self.XSectionTreeWidget.topLevelItem(top_box).removeChild(
                        self.XSectionTreeWidget.topLevelItem(top_box).child(child_xsect)
                    )
                    break
            if success == 1:
                break


def update_xsection_checkboxes(self, uid=None, uid_checkState=None):
    """Update checkboxes in XSection tree, called when state changed in xsection tree."""
    item = self.XSectionTreeWidget.findItems(
        uid, Qt.MatchFixedString | Qt.MatchRecursive, 1
    )[0]
    if uid_checkState == Qt.Checked:
        item.setCheckState(0, Qt.Checked)
    elif uid_checkState == Qt.Unchecked:
        item.setCheckState(0, Qt.Unchecked)


def toggle_xsection_visibility(self, item):
    """Called by self.XSectionTreeWidget.itemChanged.connect(self.toggle_xsection_visibility)."""
    name = item.text(0)  # not used
    uid = item.text(1)
    uid_checkState = item.checkState(0)
    if (
        uid
    ):  # needed to skip messages from upper levels of tree that do not broadcast uid's
        if uid_checkState == Qt.Checked:
            if not self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                self.actors_df.loc[self.actors_df["uid"] == uid, "show"] = True
                self.set_actor_visible(uid=uid, visible=True)
        elif uid_checkState == Qt.Unchecked:
            if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                self.actors_df.loc[self.actors_df["uid"] == uid, "show"] = False
                self.set_actor_visible(uid=uid, visible=False)
        """Before updating checkboxes, disconnect signals to xsection tree, if they are set,
        to avoid a nasty loop that disrupts the trees, then reconnect them (it is also possible that
        they are automatically reconnected whe the trees are rebuilt."""
        self.XSectionTreeWidget.itemChanged.disconnect()
        update_xsection_checkboxes(self, uid=uid, uid_checkState=uid_checkState)
        self.XSectionTreeWidget.itemChanged.connect(self.toggle_xsection_visibility)
