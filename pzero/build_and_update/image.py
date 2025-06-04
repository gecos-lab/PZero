from PySide6.QtWidgets import QTableWidgetItem, QComboBox, QHeaderView
from PySide6.QtCore import Qt

"""Methods used to build and update the IMAGE table."""


def create_image_list(self, sec_uid=None):
    """Create image list with checkboxes."""
    self.ImagesTableWidget.clear()
    self.ImagesTableWidget.setColumnCount(3)
    self.ImagesTableWidget.setRowCount(0)
    self.ImagesTableWidget.setHorizontalHeaderLabels(["Name", "uid"])
    self.ImagesTableWidget.hideColumn(1)  # hide the uid column
    uids = self.parent.image_coll.df.query(self.view_filter)["uid"].to_list()
    row = 0
    for uid in uids:
        name = self.parent.image_coll.df.loc[
            self.parent.image_coll.df["uid"] == uid, "name"
        ].values[0]
        name_item = QTableWidgetItem(name)
        name_item.setFlags(name_item.flags() | Qt.ItemIsUserCheckable)
        name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
        uid_item = QTableWidgetItem(uid)
        property_combo = QComboBox()
        property_combo.uid = uid
        property_combo.addItem("none")
        property_combo.texture_uid_list = ["none"]
        # property_combo.texture_uid_list = ["none", "X", "Y", "Z"]
        # property_combo.addItem("X")
        # property_combo.addItem("Y")
        # property_combo.addItem("Z")
        for prop in self.parent.image_coll.get_uid_properties_names(uid):
            property_combo.addItem(prop)
        self.ImagesTableWidget.insertRow(row)
        self.ImagesTableWidget.setItem(row, 0, name_item)
        self.ImagesTableWidget.setItem(row, 1, uid_item)
        self.ImagesTableWidget.setCellWidget(row, 2, property_combo)
        property_combo.currentIndexChanged.connect(
            lambda *, sender=property_combo: toggle_property_image(self, sender=sender)
        )
        if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
            name_item.setCheckState(Qt.Checked)
        elif not self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
            name_item.setCheckState(Qt.Unchecked)
        row += 1
    """Send message with argument = the cell being checked/unchecked."""
    self.ImagesTableWidget.itemChanged.connect(self.toggle_image_visibility)
    # Squeeze column width to fit content
    self.ImagesTableWidget.horizontalHeader().ResizeMode(QHeaderView.ResizeToContents)


def update_image_list_added(self, new_list=None, sec_uid=None):
    """Update Image list without creating a new model"""
    row = self.ImagesTableWidget.rowCount()
    if sec_uid:
        uids = self.parent.image_coll.df.loc[
            (self.parent.image_coll.df["x_section"] == sec_uid), "uid"
        ].to_list()
    else:
        uids = self.parent.image_coll.df["uid"].to_list()
    for uid in uids:
        name = self.parent.image_coll.df.loc[
            self.parent.image_coll.df["uid"] == uid, "name"
        ].values[0]
        name_item = QTableWidgetItem(name)
        name_item.setFlags(name_item.flags() | Qt.ItemIsUserCheckable)
        name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
        uid_item = QTableWidgetItem(uid)
        property_combo = QComboBox()
        property_combo.uid = uid
        property_combo.addItem("none")
        property_combo.texture_uid_list = ["none"]
        # property_combo.texture_uid_list = ["none", "X", "Y", "Z"]
        # property_combo.addItem("X")
        # property_combo.addItem("Y")
        # property_combo.addItem("Z")
        for prop in self.parent.image_coll.get_uid_properties_names(uid):
            property_combo.addItem(prop)
        self.ImagesTableWidget.insertRow(row)
        self.ImagesTableWidget.setItem(row, 0, name_item)
        self.ImagesTableWidget.setItem(row, 1, uid_item)
        self.ImagesTableWidget.setCellWidget(row, 2, property_combo)
        property_combo.currentIndexChanged.connect(
            lambda *, sender=property_combo: toggle_property_image(self, sender=sender)
        )
        if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
            name_item.setCheckState(Qt.Checked)
        elif not self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
            name_item.setCheckState(Qt.Unchecked)
        row += 1
    """Send message with argument = the cell being checked/unchecked."""
    self.ImagesTableWidget.itemChanged.connect(self.toggle_image_visibility)
    # Squeeze column width to fit content
    self.ImagesTableWidget.horizontalHeader().ResizeMode(QHeaderView.ResizeToContents)


def update_image_list_removed(self, removed_list=None):
    """Update Image list without creating a new model"""
    for uid in removed_list:
        for row in range(self.ImagesTableWidget.rowCount()):
            """Iterate through each row of the QTableWidget to find the row with the corresponding entity"""
            if self.ImagesTableWidget.item(row, 1).text() == uid:
                """Row found: delete row"""
                self.ImagesTableWidget.removeRow(row)
                row -= 1
                break
    """Send message with argument = the cell being checked/unchecked."""
    self.ImagesTableWidget.itemChanged.connect(self.toggle_dom_visibility)


def toggle_image_visibility(self, cell):
    """Called by self.ImagesTableWidget.itemChanged.connect(self.toggle_image_visibility)."""
    # this is the check state of cell "name"
    check_state = self.ImagesTableWidget.item(cell.row(), 0).checkState()
    # this is the text of cell "uid"
    uid = self.ImagesTableWidget.item(cell.row(), 1).text()
    if check_state == Qt.Checked:
        if not self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
            self.actors_df.loc[self.actors_df["uid"] == uid, "show"] = True
            self.set_actor_visible(uid=uid, visible=True)
    elif check_state == Qt.Unchecked:
        if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
            self.actors_df.loc[self.actors_df["uid"] == uid, "show"] = False
            self.set_actor_visible(uid=uid, visible=False)


def toggle_property_image(self, sender=None):
    """Method to toggle the property shown by an image that is already present in the view."""
    # Collect values from combo box.
    # combo = self.sender()
    show_property = sender.currentText()
    uid = sender.uid
    show = self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]
    collection = self.actors_df.loc[self.actors_df["uid"] == uid, "collection"].values[
        0
    ]
    # This replaces the previous copy of the actor with the same uid, and updates the actors dataframe.
    # See issue #33 for a discussion on actors replacement by the PyVista add_mesh and add_volume methods.
    this_actor = self.show_actor_with_property(
        uid=uid, collection=collection, show_property=show_property, visible=show
    )
    self.actors_df.loc[self.actors_df["uid"] == uid, ["show_property"]] = show_property
