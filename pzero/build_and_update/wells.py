from PyQt5.QtWidgets import QTreeWidgetItem, QComboBox
from PyQt5.QtCore import Qt

from pandas import unique as pd_unique

# Methods used to build and update the WELLS table


def create_well_tree(self):
    """Create topology tree with checkboxes and properties"""
    self.WellsTreeWidget.clear()
    self.WellsTreeWidget.setColumnCount(3)
    self.WellsTreeWidget.setHeaderLabels(["Loc ID > Component", "uid", "property"])
    self.WellsTreeWidget.hideColumn(1)  # hide the uid column
    self.WellsTreeWidget.setItemsExpandable(True)

    # get unique well-head locations
    locids = pd_unique(self.parent.well_coll.df.query(self.view_filter)["Loc ID"])

    for locid in locids:
        uid = self.parent.well_coll.df.loc[
            (self.parent.well_coll.df["Loc ID"] == locid), "uid"
        ].values[0]
        tlevel_1 = QTreeWidgetItem(
            self.WellsTreeWidget, [locid]
        )  # self.GeologyTreeWidget as parent -> top level
        tlevel_1.setFlags(
            tlevel_1.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
        )

        property_combo = QComboBox()
        property_combo.uid = uid
        property_combo.name = "Annotations"
        property_combo.addItem("none")
        property_combo.addItem("name")
        self.WellsTreeWidget.setItemWidget(tlevel_1, 2, property_combo)
        property_combo.currentIndexChanged.connect(lambda: self.toggle_property())

        # ======================================= TRACE =======================================

        tlevel_2_trace = QTreeWidgetItem(
            tlevel_1, ["Trace", uid]
        )  # tlevel_1 as parent -> middle level
        tlevel_2_trace.setFlags(
            tlevel_2_trace.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
        )

        property_combo = QComboBox()
        property_combo.uid = uid
        property_combo.name = "Trace"
        property_combo.addItem("none")
        property_combo.addItem("X")
        property_combo.addItem("Y")
        property_combo.addItem("Z")
        for prop in self.parent.well_coll.get_uid_properties_names(uid):
            if prop == "LITHOLOGY":
                pass
            elif prop == "GEOLOGY":
                pass
            else:
                property_combo.addItem(prop)

        self.WellsTreeWidget.setItemWidget(tlevel_2_trace, 2, property_combo)
        property_combo.currentIndexChanged.connect(lambda: self.toggle_property())
        tlevel_2_trace.setFlags(tlevel_2_trace.flags() | Qt.ItemIsUserCheckable)
        if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
            tlevel_2_trace.setCheckState(0, Qt.Checked)
        elif not self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
            tlevel_2_trace.setCheckState(0, Qt.Unchecked)

    # ======================================= MARKER =======================================

    # tlevel_2_mark = QTreeWidgetItem(tlevel_1, ['Markers', uid])  # tlevel_1 as parent -> middle level
    # tlevel_2_mark.setFlags(tlevel_2_mark.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable)

    # property_combo = QComboBox()
    # property_combo.uid = uid
    # property_combo.name = 'Marker'
    # property_combo.addItem("none")
    # for prop in self.parent.well_coll.get_uid_marker_names(uid):
    #     property_combo.addItem(prop)

    # self.WellsTreeWidget.setItemWidget(tlevel_2_mark, 2, property_combo)
    # property_combo.currentIndexChanged.connect(lambda: self.toggle_property())
    # tlevel_2_mark.setFlags(tlevel_2_mark.flags() | Qt.ItemIsUserCheckable)
    # if self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
    #     tlevel_2_mark.setCheckState(0, Qt.Checked)
    # elif not self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
    #     tlevel_2_mark.setCheckState(0, Qt.Unchecked)

    # ======================================= ANNOTATIONS =======================================

    # tlevel_2_mark = QTreeWidgetItem(tlevel_1, ['Annotations', uid])  # tlevel_1 as parent -> middle level
    # tlevel_2_mark.setFlags(tlevel_2_mark.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable)

    # property_combo = QComboBox()
    # property_combo.uid = uid
    # property_combo.name = 'Annotations'
    # property_combo.addItem("none")
    # for annotation_uid in self.parent.backgrounds_coll.get_buid_uid(uid):
    #     name = self.parent.backgrounds_coll.get_uid_name(annotation_uid)
    #     property_combo.addItem(name)

    # self.WellsTreeWidget.setItemWidget(tlevel_2_mark, 2, property_combo)
    # property_combo.currentIndexChanged.connect(lambda: self.toggle_property())
    # tlevel_2_mark.setFlags(tlevel_2_mark.flags() | Qt.ItemIsUserCheckable)
    # if self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
    #     tlevel_2_mark.setCheckState(0, Qt.Checked)
    # elif not self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
    #     tlevel_2_mark.setCheckState(0, Qt.Unchecked)

    """Send messages. Note that with tristate several signals are emitted in a sequence, one for each
    changed item, but upper levels do not broadcast uid's so they are filtered in the toggle method."""
    self.WellsTreeWidget.itemChanged.connect(self.toggle_well_visibility)
    self.WellsTreeWidget.expandAll()


def update_well_tree_added(self, new_list=None):
    #############################################################
    # IS IT NECESSARY TO CONSIDER CROSS SEVTION HERE?
    #############################################################
    """Update well tree without creating a new model"""
    for uid in new_list["uid"]:
        if (
                self.WellsTreeWidget.findItems(
                    self.parent.well_coll.get_uid_well_locid(uid), Qt.MatchExactly, 0
                )
                != []
        ):
            """Already exists a TreeItem (1 level) for the geological type"""
            counter_1 = 0
            for child_1 in range(
                    self.WellsTreeWidget.findItems(
                        self.parent.well_coll.get_uid_well_locid(uid),
                        Qt.MatchExactly,
                        0,
                    )[0].childCount()
            ):
                glevel_2 = QTreeWidgetItem(
                    self.WellsTreeWidget.findItems(
                        self.parent.well_coll.get_uid_well_locid(uid),
                        Qt.MatchExactly,
                        0,
                    )[0]
                )
                glevel_2.setFlags(
                    glevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
                )
                self.WellsTreeWidget.insertTopLevelItem(0, glevel_2)

                property_combo = QComboBox()
                property_combo.uid = uid
                property_combo.name = "Trace"
                property_combo.addItem("none")
                property_combo.addItem("X")
                property_combo.addItem("Y")
                property_combo.addItem("Z")
                for prop in self.parent.well_coll.get_uid_properties_names(uid):
                    if prop == "LITHOLOGY":
                        pass
                    elif prop == "GEOLOGY":
                        pass
                    else:
                        property_combo.addItem(prop)

                self.WellsTreeWidget.setItemWidget(glevel_2, 2, property_combo)
                property_combo.currentIndexChanged.connect(
                    lambda: self.toggle_property()
                )
                glevel_2.setFlags(glevel_2.flags() | Qt.ItemIsUserCheckable)
                if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[
                    0
                ]:
                    glevel_2.setCheckState(0, Qt.Checked)
                elif not self.actors_df.loc[
                    self.actors_df["uid"] == uid, "show"
                ].values[0]:
                    glevel_2.setCheckState(0, Qt.Unchecked)
                self.WellsTreeWidget.insertTopLevelItem(0, glevel_2)
                break
        else:
            """Different geological type, geological feature and scenario"""
            tlevel_1 = QTreeWidgetItem(
                self.WellsTreeWidget,
                [self.parent.well_coll.get_uid_well_locid(uid)],
            )  # self.GeologyTreeWidget as parent -> top level
            tlevel_1.setFlags(
                tlevel_1.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
            )

            property_combo = QComboBox()
            property_combo.uid = uid
            property_combo.name = "Annotations"
            property_combo.addItem("none")
            property_combo.addItem("name")
            self.WellsTreeWidget.setItemWidget(tlevel_1, 2, property_combo)
            property_combo.currentIndexChanged.connect(
                lambda: self.toggle_property()
            )

            # ======================================= TRACE =======================================

            tlevel_2_trace = QTreeWidgetItem(
                tlevel_1, ["Trace", uid]
            )  # tlevel_1 as parent -> middle level
            tlevel_2_trace.setFlags(
                tlevel_2_trace.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
            )

            property_combo = QComboBox()
            property_combo.uid = uid
            property_combo.name = "Trace"
            property_combo.addItem("none")
            property_combo.addItem("X")
            property_combo.addItem("Y")
            property_combo.addItem("Z")
            for prop in self.parent.well_coll.get_uid_properties_names(uid):
                if prop == "LITHOLOGY":
                    pass
                elif prop == "GEOLOGY":
                    pass
                else:
                    property_combo.addItem(prop)

            self.WellsTreeWidget.setItemWidget(tlevel_2_trace, 2, property_combo)
            property_combo.currentIndexChanged.connect(
                lambda: self.toggle_property()
            )
            tlevel_2_trace.setFlags(tlevel_2_trace.flags() | Qt.ItemIsUserCheckable)
            if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                tlevel_2_trace.setCheckState(0, Qt.Checked)
            elif not self.actors_df.loc[
                self.actors_df["uid"] == uid, "show"
            ].values[0]:
                tlevel_2_trace.setCheckState(0, Qt.Unchecked)
            break

    self.WellsTreeWidget.itemChanged.connect(self.toggle_well_visibility)
    self.WellsTreeWidget.expandAll()


def update_well_tree_removed(self, removed_list=None):
    """When geological entity is removed, update Geology Tree without building a new model"""
    success = 0
    for uid in removed_list:
        for well_locid in range(self.WellsTreeWidget.topLevelItemCount()):
            """Iterate through every Geological Role top level"""
            for child_feature in range(
                    self.WellsTreeWidget.topLevelItem(well_locid).childCount()
            ):
                """Iterate through every Geological Feature child"""
                if (
                        self.WellsTreeWidget.topLevelItem(well_locid)
                                .child(child_feature)
                                .text(1)
                        == uid
                ):
                    """Complete check: entity found has the uid of the entity we need to remove. Delete child, then ensure no Child or Top Level remain empty"""
                    success = 1
                    self.WellsTreeWidget.topLevelItem(well_locid).child(
                        child_feature
                    ).removeChild(
                        self.WellsTreeWidget.topLevelItem(well_locid).child(
                            child_feature
                        )
                    )

                    if (
                            self.WellsTreeWidget.topLevelItem(well_locid).childCount()
                            == 0
                    ):
                        self.WellsTreeWidget.takeTopLevelItem(well_locid)
                    break
            if success == 1:
                break


def toggle_well_visibility(self, item):
    """Called by self.WellsTreeWidget.itemChanged.connect(self.toggle_boundary_visibility)."""

    name = item.text(0)  # not used
    uid = item.text(1)
    uid_checkState = item.checkState(0)
    if (
            uid
    ):  # needed to skip messages from upper levels of tree that do not broadcast uid's
        if uid_checkState == Qt.Checked:
            if not self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[
                0
            ]:
                if name == "Trace":
                    self.actors_df.loc[self.actors_df["uid"] == uid, "show"] = True
            self.set_actor_visible(uid=uid, visible=True, name=name)
        elif uid_checkState == Qt.Unchecked:
            if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                if name == "Trace":
                    self.actors_df.loc[self.actors_df["uid"] == uid, "show"] = False
            self.set_actor_visible(uid=uid, visible=False, name=name)

        self.WellsTreeWidget.itemChanged.disconnect()
        self.WellsTreeWidget.itemChanged.connect(self.toggle_well_visibility)
