from PyQt5.QtWidgets import QTableWidgetItem, QComboBox
from PyQt5.QtCore import Qt

# Methods used to build and update the DOM table


def create_dom_list(self, sec_uid=None):
    """Create cross-sections list with checkboxes."""
    self.DOMsTableWidget.clear()
    self.DOMsTableWidget.setColumnCount(3)
    self.DOMsTableWidget.setRowCount(0)
    self.DOMsTableWidget.setHorizontalHeaderLabels(["Name", "uid", "Show property"])
    self.DOMsTableWidget.hideColumn(1)  # hide the uid column
    row = 0
    uids = self.parent.dom_coll.df.query(self.view_filter)["uid"].to_list()
    for uid in uids:
        name = self.parent.dom_coll.df.loc[
            self.parent.dom_coll.df["uid"] == uid, "name"
        ].values[0]
        name_item = QTableWidgetItem(name)
        name_item.setFlags(name_item.flags() | Qt.ItemIsUserCheckable)
        name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
        uid_item = QTableWidgetItem(uid)
        property_texture_combo = QComboBox()
        property_texture_combo.uid = uid
        property_texture_combo.addItem("none")
        property_texture_combo.texture_uid_list = ["none", "X", "Y", "Z"]
        property_texture_combo.addItem("X")
        property_texture_combo.addItem("Y")
        property_texture_combo.addItem("Z")
        # property_texture_combo.addItem("RGB")

        """[Gabriele] To add support to multi components properties (e.g. RGB) we can add a component check (if components > 1). If this statement is True we can iterate over the n components and set the new n properties using the template prop[n_component]. These properties do not point to actual data (the "RGB[0]" property is not present) but to a slice of the original property (RGB[:,0])."""

        for prop, components in zip(
                self.parent.dom_coll.get_uid_properties_names(uid),
                self.parent.dom_coll.get_uid_properties_components(uid),
        ):
            if (
                    prop
                    not in self.parent.dom_coll.df.loc[
                self.parent.dom_coll.df["uid"] == uid, "texture_uids"
            ].values[0]
            ):
                property_texture_combo.addItem(prop)
                property_texture_combo.texture_uid_list.append(prop)

                if components > 1:
                    for component in range(components):
                        property_texture_combo.addItem(f"{prop}[{component}]")
                        property_texture_combo.texture_uid_list.append(
                            f"{prop}[{component}]"
                        )

        for texture_uid in self.parent.dom_coll.df.loc[
            self.parent.dom_coll.df["uid"] == uid, "texture_uids"
        ].values[0]:
            texture_name = self.parent.image_coll.df.loc[
                self.parent.image_coll.df["uid"] == texture_uid, "name"
            ].values[0]
            property_texture_combo.addItem(texture_name)
            property_texture_combo.texture_uid_list.append(texture_uid)

        self.DOMsTableWidget.insertRow(row)
        self.DOMsTableWidget.setItem(row, 0, name_item)
        self.DOMsTableWidget.setItem(row, 1, uid_item)
        self.DOMsTableWidget.setCellWidget(row, 2, property_texture_combo)
        property_texture_combo.currentIndexChanged.connect(
            lambda: self.toggle_property_texture()
        )
        if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
            name_item.setCheckState(Qt.Checked)
        elif not self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
            name_item.setCheckState(Qt.Unchecked)
        row += 1
    """Send message with argument = the cell being checked/unchecked."""
    self.DOMsTableWidget.itemChanged.connect(self.toggle_dom_visibility)


def update_dom_list_added(self, new_list=None, sec_uid=None):
    """Update DOM list without creating a new model"""
    # print('update_dom_list_added')
    row = self.DOMsTableWidget.rowCount()
    uid_list = list(new_list["uid"])
    if sec_uid:
        for i, uid in enumerate(new_list["uid"]):
            if (
                    sec_uid
                    != self.parent.dom_coll.df.loc[
                self.parent.dom_coll.df["uid"] == uid, "x_section"
            ].values[0]
            ):
                del uid_list[i]
    for uid in uid_list:
        name = self.parent.dom_coll.df.loc[
            self.parent.dom_coll.df["uid"] == uid, "name"
        ].values[0]
        name_item = QTableWidgetItem(name)
        name_item.setFlags(name_item.flags() | Qt.ItemIsUserCheckable)
        name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
        uid_item = QTableWidgetItem(uid)
        property_texture_combo = QComboBox()
        property_texture_combo.uid = uid
        property_texture_combo.addItem("none")
        property_texture_combo.texture_uid_list = ["none", "X", "Y", "Z"]
        property_texture_combo.addItem("X")
        property_texture_combo.addItem("Y")
        property_texture_combo.addItem("Z")
        # property_texture_combo.addItem("RGB")

        """[Gabriele] See function above for explanation"""

        for prop, components in zip(
                self.parent.dom_coll.get_uid_properties_names(uid),
                self.parent.dom_coll.get_uid_properties_components(uid),
        ):
            if (
                    prop
                    not in self.parent.dom_coll.df.loc[
                self.parent.dom_coll.df["uid"] == uid, "texture_uids"
            ].values[0]
            ):
                property_texture_combo.addItem(prop)
                property_texture_combo.texture_uid_list.append(prop)
                # print(prop)
                if components > 1:
                    for n_component in range(components):
                        property_texture_combo.addItem(f"{prop}[{n_component}]")
                        property_texture_combo.texture_uid_list.append(
                            f"{prop}[{n_component}]"
                        )
        for texture_uid in self.parent.dom_coll.df.loc[
            self.parent.dom_coll.df["uid"] == uid, "texture_uids"
        ].values[0]:
            texture_name = self.parent.image_coll.df.loc[
                self.parent.image_coll.df["uid"] == texture_uid, "name"
            ].values[0]
            property_texture_combo.addItem(texture_name)
            property_texture_combo.texture_uid_list.append(texture_uid)
        self.DOMsTableWidget.insertRow(row)
        self.DOMsTableWidget.setItem(row, 0, name_item)
        self.DOMsTableWidget.setItem(row, 1, uid_item)
        self.DOMsTableWidget.setCellWidget(row, 2, property_texture_combo)
        property_texture_combo.currentIndexChanged.connect(
            lambda: self.toggle_property_texture()
        )
        if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
            name_item.setCheckState(Qt.Checked)
        elif not self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
            name_item.setCheckState(Qt.Unchecked)
        row += 1
    """Send message with argument = the cell being checked/unchecked."""
    self.DOMsTableWidget.itemChanged.connect(self.toggle_dom_visibility)


def update_dom_list_removed(self, removed_list=None):
    """Update DOM list without creating a new model"""
    for uid in removed_list:
        for row in range(self.DOMsTableWidget.rowCount()):
            """Iterate through each row of the QTableWidget to find the row with the corresponding entity"""
            if self.DOMsTableWidget.item(row, 1).text() == uid:
                """Row found: delete row"""
                self.DOMsTableWidget.removeRow(row)
                row -= 1
                break
    """Send message with argument = the cell being checked/unchecked."""
    self.DOMsTableWidget.itemChanged.connect(self.toggle_dom_visibility)


def toggle_dom_visibility(self, cell):
    """Called by self.DOMsTableWidget.itemChanged.connect(self.toggle_dom_visibility)."""
    check_state = self.DOMsTableWidget.item(
        cell.row(), 0
    ).checkState()  # this is the check state of cell "name"

    if self.DOMsTableWidget.item(cell.row(), 1):
        uid = self.DOMsTableWidget.item(
            cell.row(), 1
        ).text()  # this is the text of cell "uid"
    else:
        return
    if check_state == Qt.Checked:
        if not self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
            self.actors_df.loc[self.actors_df["uid"] == uid, "show"] = True
            self.set_actor_visible(uid=uid, visible=True)

    elif check_state == Qt.Unchecked:
        if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
            self.actors_df.loc[self.actors_df["uid"] == uid, "show"] = False
            self.set_actor_visible(uid=uid, visible=False)


def toggle_property_texture(self):
    """Method to toggle the texture shown by a DEM that is already present in the view."""
    # Collect values from combo box and actor's dataframe.
    combo = self.sender()
    uid = combo.uid
    show = self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]
    collection = self.actors_df.loc[self.actors_df["uid"] == uid, "collection"].values[0]
    property_texture_id = combo.currentIndex()  # 0 means "none"
    property_texture_list = combo.texture_uid_list
    property_texture_uid = property_texture_list[property_texture_id]
    # Set the active texture coordinates.
    if property_texture_uid in \
            self.parent.dom_coll.df.loc[self.parent.dom_coll.df["uid"] == uid, "texture_uids"].values[0]:
        self.parent.dom_coll.set_active_texture_on_dom(dom_uid=uid, map_image_uid=property_texture_uid)
    # Remove the previous scalar bar if present
    if hasattr(self, "plotter"):
        try:
            self.plotter.remove_scalar_bar()
        except IndexError:
            pass
    # This replaces the previous copy of the actor with the same uid, and updates the actors dataframe.
    # See issue #33 for a discussion on actors replacement by the PyVista add_mesh and add_volume methods.
    this_actor = self.show_actor_with_property(uid=uid, collection=collection, show_property=property_texture_uid,
                                               visible=show)
    self.actors_df.loc[self.actors_df["uid"] == uid, ["show_property"]] = property_texture_uid
