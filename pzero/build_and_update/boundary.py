from PySide6.QtWidgets import QTableWidgetItem, QHeaderView
from PySide6.QtCore import Qt

"""Methods used to build and update the BOUNDARY table."""


def create_boundary_list(self):
    """Create boundaries list with checkboxes."""
    self.BoundariesTableWidget.clear()
    self.BoundariesTableWidget.setColumnCount(2)
    self.BoundariesTableWidget.setRowCount(0)
    self.BoundariesTableWidget.setHorizontalHeaderLabels(["Name", "uid"])
    self.BoundariesTableWidget.hideColumn(1)  # hide the uid column
    try:
        uids = self.parent.boundary_coll.df.query(self.view_filter)["uid"].to_list()
    except:
        uids = []
    row = 0
    for uid in uids:
        name = self.parent.boundary_coll.df.loc[
            self.parent.boundary_coll.df["uid"] == uid, "name"
        ].values[0]
        name_item = QTableWidgetItem(name)
        name_item.setFlags(name_item.flags() | Qt.ItemIsUserCheckable)
        name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
        uid_item = QTableWidgetItem(uid)
        self.BoundariesTableWidget.insertRow(row)
        self.BoundariesTableWidget.setItem(row, 0, name_item)
        self.BoundariesTableWidget.setItem(row, 1, uid_item)
        if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
            name_item.setCheckState(Qt.Checked)
        elif not self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
            name_item.setCheckState(Qt.Unchecked)
        row += 1
    """Send message with argument = the cell being checked/unchecked."""
    self.BoundariesTableWidget.itemChanged.connect(self.toggle_boundary_visibility)
    # Squeeze column width to fit content
    self.BoundariesTableWidget.horizontalHeader().ResizeMode(
        QHeaderView.ResizeToContents
    )


def update_boundary_list_added(self, new_list=None, sec_uid=None):
    """Update boundaries list without creating a new model"""
    row = self.BoundariesTableWidget.rowCount()
    if sec_uid:
        uids = self.parent.boundary_coll.df.loc[
            (self.parent.boundary_coll.df["x_section"] == sec_uid), "uid"
        ].to_list()
    else:
        uids = self.parent.boundary_coll.df["uid"].to_list()
    for uid in uids:
        name = self.parent.boundary_coll.df.loc[
            self.parent.boundary_coll.df["uid"] == uid, "name"
        ].values[0]
        name_item = QTableWidgetItem(name)
        name_item.setFlags(name_item.flags() | Qt.ItemIsUserCheckable)
        name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
        uid_item = QTableWidgetItem(uid)
        self.BoundariesTableWidget.insertRow(row)
        self.BoundariesTableWidget.setItem(row, 0, name_item)
        self.BoundariesTableWidget.setItem(row, 1, uid_item)
        if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
            name_item.setCheckState(Qt.Checked)
        elif not self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
            name_item.setCheckState(Qt.Unchecked)
        row += 1
    """Send message with argument = the cell being checked/unchecked."""
    self.BoundariesTableWidget.itemChanged.connect(self.toggle_boundary_visibility)
    # Squeeze column width to fit content
    self.BoundariesTableWidget.horizontalHeader().ResizeMode(
        QHeaderView.ResizeToContents
    )


def update_boundary_list_removed(self, removed_list=None):
    """Update boundary list without creating a new model"""
    for uid in removed_list:
        for row in range(self.BoundariesTableWidget.rowCount()):
            """Iterate through each row of the QTableWidget to find the row with the corresponding entity"""
            if self.BoundariesTableWidget.item(row, 1).text() == uid:
                """Row found: delete row"""
                self.BoundariesTableWidget.removeRow(row)
                row -= 1
                break
    """Send message with argument = the cell being checked/unchecked."""
    self.BoundariesTableWidget.itemChanged.connect(self.toggle_boundary_visibility)


def toggle_boundary_visibility(self, cell):
    """Called by self.BoundariesTableWidget.itemChanged.connect(self.toggle_boundary_visibility)."""
    check_state = self.BoundariesTableWidget.item(
        cell.row(), 0
    ).checkState()  # this is the check state of cell "name"
    uid = self.BoundariesTableWidget.item(
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
