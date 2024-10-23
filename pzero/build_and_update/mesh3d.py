from PySide6.QtWidgets import QTableWidgetItem, QComboBox
from PySide6.QtCore import Qt

"""Methods used to build and update the MESH3D table in views."""


def create_mesh3d_list(self):
    """Create mesh3D list with checkboxes."""
    self.Mesh3DTableWidget.clear()
    self.Mesh3DTableWidget.setColumnCount(3)
    self.Mesh3DTableWidget.setRowCount(0)
    self.Mesh3DTableWidget.setHorizontalHeaderLabels(["Name", "uid"])
    self.Mesh3DTableWidget.hideColumn(1)  # hide the uid column
    uids = self.parent.mesh3d_coll.df.query(self.view_filter)["uid"].to_list()
    row = 0
    for uid in uids:
        name = self.parent.mesh3d_coll.df.loc[
            self.parent.mesh3d_coll.df["uid"] == uid, "name"
        ].values[0]
        name_item = QTableWidgetItem(name)
        name_item.setFlags(name_item.flags() | Qt.ItemIsUserCheckable)
        name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
        uid_item = QTableWidgetItem(uid)
        property_combo = QComboBox()
        property_combo.uid = uid
        property_combo.addItem("none")
        property_combo.texture_uid_list = ["none", "X", "Y", "Z"]
        property_combo.addItem("X")
        property_combo.addItem("Y")
        property_combo.addItem("Z")
        for prop in self.parent.mesh3d_coll.get_uid_properties_names(uid):
            property_combo.addItem(prop)
        self.Mesh3DTableWidget.insertRow(row)
        self.Mesh3DTableWidget.setItem(row, 0, name_item)
        self.Mesh3DTableWidget.setItem(row, 1, uid_item)
        self.Mesh3DTableWidget.setCellWidget(row, 2, property_combo)
        property_combo.currentIndexChanged.connect(lambda *, sender=property_combo: toggle_property_mesh3d(self, sender=sender))
        if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
            name_item.setCheckState(Qt.Checked)
        elif not self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
            name_item.setCheckState(Qt.Unchecked)
        row += 1
    """Send message with argument = the cell being checked/unchecked."""
    self.Mesh3DTableWidget.itemChanged.connect(self.toggle_mesh3d_visibility)


def update_mesh3d_list_added(self, new_list=None, sec_uid=None):
    """Update Mesh3D list without creating a new model"""
    row = self.Mesh3DTableWidget.rowCount()
    uid_list = list(new_list["uid"])
    if sec_uid:
        for i, uid in enumerate(new_list["uid"]):
            if (
                    sec_uid
                    != self.parent.mesh3d_coll.df.loc[
                self.parent.mesh3d_coll.df["uid"] == uid, "x_section"
            ].values[0]
            ):
                del uid_list[i]
    for uid in uid_list:
        name = self.parent.mesh3d_coll.df.loc[
            self.parent.mesh3d_coll.df["uid"] == uid, "name"
        ].values[0]
        name_item = QTableWidgetItem(name)
        name_item.setFlags(name_item.flags() | Qt.ItemIsUserCheckable)
        name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
        uid_item = QTableWidgetItem(uid)
        property_combo = QComboBox()
        property_combo.uid = uid
        property_combo.addItem("none")
        property_combo.texture_uid_list = ["none", "X", "Y", "Z"]
        property_combo.addItem("X")
        property_combo.addItem("Y")
        property_combo.addItem("Z")
        for prop in self.parent.mesh3d_coll.get_uid_properties_names(uid):
            property_combo.addItem(prop)
        self.Mesh3DTableWidget.insertRow(row)
        self.Mesh3DTableWidget.setItem(row, 0, name_item)
        self.Mesh3DTableWidget.setItem(row, 1, uid_item)
        self.Mesh3DTableWidget.setCellWidget(row, 2, property_combo)
        property_combo.currentIndexChanged.connect(lambda *, sender=property_combo: toggle_property_mesh3d(self, sender=sender))
        if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
            name_item.setCheckState(Qt.Checked)
        elif not self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
            name_item.setCheckState(Qt.Unchecked)
        row += 1
    """Send message with argument = the cell being checked/unchecked."""
    self.Mesh3DTableWidget.itemChanged.connect(self.toggle_mesh3d_visibility)


def update_mesh3d_list_removed(self, removed_list=None):
    """Update Mesh3D list without creating a new model"""
    for uid in removed_list:
        for row in range(self.Mesh3DTableWidget.rowCount()):
            """Iterate through each row of the QTableWidget to find the row with the corresponding entity"""
            if self.Mesh3DTableWidget.item(row, 1).text() == uid:
                """Row found: delete row"""
                self.Mesh3DTableWidget.removeRow(row)
                row -= 1
                break
    """Send message with argument = the cell being checked/unchecked."""
    self.Mesh3DTableWidget.itemChanged.connect(self.toggle_dom_visibility)


def toggle_mesh3d_visibility(self, cell):
    """Called by self.Mesh3DTableWidget.itemChanged.connect(self.toggle_mesh3d_visibility)."""
    check_state = self.Mesh3DTableWidget.item(
        cell.row(), 0
    ).checkState()  # this is the check state of cell "name"
    uid = self.Mesh3DTableWidget.item(
        cell.row(), 1
    ).text()  # this is the text of cell "uid"
    if check_state == Qt.Checked:
        if not self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
            self.actors_df.loc[self.actors_df["uid"] == uid, "show"] = True
            self.set_actor_visible(uid=uid, visible=True)
    elif check_state == Qt.Unchecked:
        if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
            self.actors_df.loc[self.actors_df["uid"] == uid, "show"] = False
            self.set_actor_visible(uid=uid, visible=False)


def toggle_property_mesh3d(self, sender=None):
    """Method to toggle the texture shown by a Mesh3D that is already present in the view."""
    # Collect values from combo box.
    # combo = self.sender()
    show_property = sender.currentText()
    uid = sender.uid
    show = self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]
    collection = self.actors_df.loc[self.actors_df["uid"] == uid, "collection"].values[0]
    # This replaces the previous copy of the actor with the same uid, and updates the actors dataframe.
    # See issue #33 for a discussion on actors replacement by the PyVista add_mesh and add_volume methods.
    this_actor = self.show_actor_with_property(uid=uid,
                                               collection=collection,
                                               show_property=show_property,
                                               visible=show)
    self.actors_df.loc[self.actors_df["uid"] == uid, ["show_property"]] = show_property
