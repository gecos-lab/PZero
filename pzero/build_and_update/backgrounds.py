from PySide6.QtWidgets import QTreeWidgetItem, QComboBox
from PySide6.QtCore import Qt

from pandas import unique as pd_unique

"""Methods used to build and update the BACKGROUNDS and BACKGROUNDS TOPOLOGY trees."""


def create_backgrounds_tree(self):
    """Create Backgrounds tree with checkboxes and properties"""
    self.BackgroundsTreeWidget.clear()
    self.BackgroundsTreeWidget.setColumnCount(3)
    self.BackgroundsTreeWidget.setHeaderLabels(
        ["Role > Feature > Name", "uid", "property"]
    )
    # hide the uid column
    self.BackgroundsTreeWidget.hideColumn(1)
    self.BackgroundsTreeWidget.setItemsExpandable(True)
    roles = pd_unique(self.parent.backgrnd_coll.df.query(self.view_filter)["role"])
    for role in roles:
        flevel_1 = QTreeWidgetItem(
            self.BackgroundsTreeWidget, [role]
        )  # self.BackgroundsTreeWidget as parent -> top level
        flevel_1.setFlags(
            flevel_1.flags() | Qt.ItemIsUserTristate | Qt.ItemIsUserCheckable
        )
        features = pd_unique(
            self.parent.backgrnd_coll.df.query(self.view_filter).loc[
                self.parent.backgrnd_coll.df.query(self.view_filter)["role"] == role,
                "feature",
            ]
        )
        for feature in features:
            flevel_2 = QTreeWidgetItem(
                flevel_1, [feature]
            )  # flevel_1 as parent -> 1st middle level
            flevel_2.setFlags(
                flevel_2.flags() | Qt.ItemIsUserTristate | Qt.ItemIsUserCheckable
            )
            uids = (
                self.parent.backgrnd_coll.df.query(self.view_filter)
                .loc[
                    (
                        self.parent.backgrnd_coll.df.query(self.view_filter)["role"]
                        == role
                    )
                    & (
                        self.parent.backgrnd_coll.df.query(self.view_filter)["feature"]
                        == feature
                    ),
                    "uid",
                ]
                .to_list()
            )
            for uid in uids:
                property_combo = QComboBox()
                property_combo.uid = uid
                property_combo.name = "Annotations"
                property_combo.addItem("none")
                property_combo.addItem("name")
                for prop in self.parent.backgrnd_coll.get_uid_properties_names(uid):
                    property_combo.addItem(prop)
                name = self.parent.backgrnd_coll.df.loc[
                    (self.parent.backgrnd_coll.df["uid"] == uid), "name"
                ].values[0]
                flevel_3 = QTreeWidgetItem(
                    flevel_2, [name, uid]
                )  # flevel_3 as parent -> lower level
                self.BackgroundsTreeWidget.setItemWidget(flevel_3, 2, property_combo)
                property_combo.currentIndexChanged.connect(
                    lambda *, sender=property_combo: self.toggle_property(sender=sender)
                )
                flevel_3.setFlags(flevel_3.flags() | Qt.ItemIsUserCheckable)
                if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                    flevel_3.setCheckState(0, Qt.Checked)
                elif not self.actors_df.loc[
                    self.actors_df["uid"] == uid, "show"
                ].values[0]:
                    flevel_3.setCheckState(0, Qt.Unchecked)
    """Send messages. Note that with tristate several signals are emitted in a sequence, one for each
    changed item, but upper levels do not broadcast uid's so they are filtered in the toggle method."""
    self.BackgroundsTreeWidget.itemChanged.connect(self.toggle_backgrounds_visibility)
    # Squeeze column width to fit content
    for col in range(self.BackgroundsTreeWidget.columnCount()):
        self.BackgroundsTreeWidget.resizeColumnToContents(col)
    self.BackgroundsTreeWidget.expandAll()


def create_backgrounds_topology_tree(self):
    """Create topology tree with checkboxes and properties"""
    self.BackgroundsTopologyTreeWidget.clear()
    self.BackgroundsTopologyTreeWidget.setColumnCount(3)
    self.BackgroundsTreeWidget.setHeaderLabels(
        ["Role > Feature > Name", "uid", "property"]
    )
    self.BackgroundsTopologyTreeWidget.hideColumn(1)  # hide the uid column
    self.BackgroundsTopologyTreeWidget.setItemsExpandable(True)
    topo_types = pd_unique(
        self.parent.backgrnd_coll.df.query(self.view_filter)["topology"]
    )
    for topo_type in topo_types:
        tlevel_1 = QTreeWidgetItem(
            self.BackgroundsTopologyTreeWidget, [topo_type]
        )  # self.GeologyTreeWidget as parent -> top level
        tlevel_1.setFlags(
            tlevel_1.flags() | Qt.ItemIsUserTristate | Qt.ItemIsUserCheckable
        )

        for role in pd_unique(
            self.parent.backgrnd_coll.df.query(self.view_filter).loc[
                self.parent.backgrnd_coll.df.query(self.view_filter)["topology"]
                == topo_type,
                "role",
            ]
        ):
            tlevel_2 = QTreeWidgetItem(
                tlevel_1, [role]
            )  # tlevel_1 as parent -> middle level
            tlevel_2.setFlags(
                tlevel_2.flags() | Qt.ItemIsUserTristate | Qt.ItemIsUserCheckable
            )
            uids = (
                self.parent.backgrnd_coll.df.query(self.view_filter)
                .loc[
                    (
                        self.parent.backgrnd_coll.df.query(self.view_filter)["topology"]
                        == topo_type
                    )
                    & (
                        self.parent.backgrnd_coll.df.query(self.view_filter)["role"]
                        == role
                    ),
                    "uid",
                ]
                .to_list()
            )
            for uid in uids:
                property_combo = QComboBox()
                property_combo.uid = uid
                property_combo.name = "Annotations"
                property_combo.addItem("none")
                property_combo.addItem("name")
                for prop in self.parent.backgrnd_coll.get_uid_properties_names(uid):
                    property_combo.addItem(prop)
                name = self.parent.backgrnd_coll.df.loc[
                    self.parent.backgrnd_coll.df["uid"] == uid, "name"
                ].values[0]
                tlevel_3 = QTreeWidgetItem(
                    tlevel_2, [name, uid]
                )  # tlevel_2 as parent -> lower level
                self.BackgroundsTopologyTreeWidget.setItemWidget(
                    tlevel_3, 2, property_combo
                )
                property_combo.currentIndexChanged.connect(
                    lambda *, sender=property_combo: self.toggle_property(sender=sender)
                )
                tlevel_3.setFlags(tlevel_3.flags() | Qt.ItemIsUserCheckable)
                if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                    tlevel_3.setCheckState(0, Qt.Checked)
                elif not self.actors_df.loc[
                    self.actors_df["uid"] == uid, "show"
                ].values[0]:
                    tlevel_3.setCheckState(0, Qt.Unchecked)
    """Send messages. Note that with tristate several signals are emitted in a sequence, one for each
    changed item, but upper levels do not broadcast uid's so they are filtered in the toggle method."""
    self.BackgroundsTopologyTreeWidget.itemChanged.connect(
        self.toggle_backgrounds_visibility
    )
    # Squeeze column width to fit content
    for col in range(self.BackgroundsTopologyTreeWidget.columnCount()):
        self.BackgroundsTopologyTreeWidget.resizeColumnToContents(col)
    self.BackgroundsTopologyTreeWidget.expandAll()


def update_backgrounds_tree_added(self, new_list=None, sec_uid=None):
    """Update background tree without creating a new model"""

    uid_list = list(new_list["uid"])
    if sec_uid:
        for i, uid in enumerate(new_list["uid"]):
            if (
                sec_uid
                != self.parent.backgrnd_coll.df.loc[
                    self.parent.backgrnd_coll.df["uid"] == uid, "x_section"
                ].values[0]
            ):
                del uid_list[i]
    for uid in uid_list:
        if (
            self.BackgroundsTreeWidget.findItems(
                self.parent.backgrnd_coll.get_uid_role(uid),
                Qt.MatchExactly,
                0,
            )
            != []
        ):
            """Already exists a TreeItem (1 level) for the background type"""
            counter_1 = 0
            for child_1 in range(
                self.BackgroundsTreeWidget.findItems(
                    self.parent.backgrnd_coll.get_uid_role(uid),
                    Qt.MatchExactly,
                    0,
                )[0].childCount()
            ):
                """for cycle that loops n times as the number of subItems in the specific background type branch"""
                if self.BackgroundsTreeWidget.findItems(
                    self.parent.backgrnd_coll.get_uid_role(uid),
                    Qt.MatchExactly,
                    0,
                )[0].child(child_1).text(
                    0
                ) == self.parent.backgrnd_coll.get_uid_feature(
                    uid
                ):
                    counter_1 += 1
            if counter_1 != 0:
                for child_1 in range(
                    self.BackgroundsTreeWidget.findItems(
                        self.parent.backgrnd_coll.get_uid_role(uid),
                        Qt.MatchExactly,
                        0,
                    )[0].childCount()
                ):
                    if self.BackgroundsTreeWidget.findItems(
                        self.parent.backgrnd_coll.get_uid_role(uid),
                        Qt.MatchExactly,
                        0,
                    )[0].child(child_1).text(
                        0
                    ) == self.parent.backgrnd_coll.get_uid_feature(
                        uid
                    ):
                        """Already exists a TreeItem (2 level) for the background feature"""

                        """Same background type and background feature"""
                        property_combo = QComboBox()
                        property_combo.uid = uid
                        property_combo.name = "Annotations"
                        property_combo.addItem("none")
                        property_combo.addItem("name")
                        for prop in self.parent.backgrnd_coll.get_uid_properties_names(
                            uid
                        ):
                            property_combo.addItem(prop)
                        name = self.parent.backgrnd_coll.get_uid_name(uid)
                        flevel_3 = QTreeWidgetItem(
                            self.BackgroundsTreeWidget.findItems(
                                self.parent.backgrnd_coll.get_uid_role(uid),
                                Qt.MatchExactly,
                                0,
                            )[0].child(child_1),
                            [name, uid],
                        )
                        self.BackgroundsTreeWidget.setItemWidget(
                            flevel_3, 2, property_combo
                        )
                        property_combo.currentIndexChanged.connect(
                            lambda *, sender=property_combo: self.toggle_property(
                                sender=sender
                            )
                        )
                        flevel_3.setFlags(flevel_3.flags() | Qt.ItemIsUserCheckable)
                        if self.actors_df.loc[
                            self.actors_df["uid"] == uid, "show"
                        ].values[0]:
                            flevel_3.setCheckState(0, Qt.Checked)
                        elif not self.actors_df.loc[
                            self.actors_df["uid"] == uid, "show"
                        ].values[0]:
                            flevel_3.setCheckState(0, Qt.Unchecked)
                        self.BackgroundsTreeWidget.insertTopLevelItem(0, flevel_3)
                        break
            else:
                """Same background type, different background feature"""
                flevel_2 = QTreeWidgetItem(
                    self.BackgroundsTreeWidget.findItems(
                        self.parent.backgrnd_coll.get_uid_role(uid),
                        Qt.MatchExactly,
                        0,
                    )[0],
                    [self.parent.backgrnd_coll.get_uid_feature(uid)],
                )
                flevel_2.setFlags(
                    flevel_2.flags() | Qt.ItemIsUserTristate | Qt.ItemIsUserCheckable
                )
                self.BackgroundsTreeWidget.insertTopLevelItem(0, flevel_2)
                property_combo = QComboBox()
                property_combo.uid = uid
                property_combo.name = "Annotations"
                property_combo.addItem("none")
                property_combo.addItem("name")
                for prop in self.parent.backgrnd_coll.get_uid_properties_names(uid):
                    property_combo.addItem(prop)
                name = self.parent.backgrnd_coll.get_uid_name(uid)

                flevel_3 = QTreeWidgetItem(flevel_2, [name, uid])
                self.BackgroundsTreeWidget.setItemWidget(flevel_3, 2, property_combo)
                property_combo.currentIndexChanged.connect(
                    lambda *, sender=property_combo: self.toggle_property(sender=sender)
                )
                flevel_3.setFlags(flevel_3.flags() | Qt.ItemIsUserCheckable)
                if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                    flevel_3.setCheckState(0, Qt.Checked)
                elif not self.actors_df.loc[
                    self.actors_df["uid"] == uid, "show"
                ].values[0]:
                    flevel_3.setCheckState(0, Qt.Unchecked)
                self.BackgroundsTreeWidget.insertTopLevelItem(0, flevel_3)
                break
        else:
            """Different background type and background feature"""
            flevel_1 = QTreeWidgetItem(
                self.BackgroundsTreeWidget,
                [self.parent.backgrnd_coll.get_uid_role(uid)],
            )
            flevel_1.setFlags(
                flevel_1.flags() | Qt.ItemIsUserTristate | Qt.ItemIsUserCheckable
            )
            self.BackgroundsTreeWidget.insertTopLevelItem(0, flevel_1)
            flevel_2 = QTreeWidgetItem(
                flevel_1,
                [self.parent.backgrnd_coll.get_uid_feature(uid)],
            )
            flevel_2.setFlags(
                flevel_2.flags() | Qt.ItemIsUserTristate | Qt.ItemIsUserCheckable
            )
            self.BackgroundsTreeWidget.insertTopLevelItem(0, flevel_2)
            property_combo = QComboBox()
            property_combo.uid = uid
            property_combo.name = "Annotations"
            property_combo.addItem("none")
            property_combo.addItem("name")
            for prop in self.parent.backgrnd_coll.get_uid_properties_names(uid):
                property_combo.addItem(prop)
            name = self.parent.backgrnd_coll.get_uid_name(uid)
            flevel_3 = QTreeWidgetItem(flevel_2, [name, uid])
            self.BackgroundsTreeWidget.setItemWidget(flevel_3, 2, property_combo)
            property_combo.currentIndexChanged.connect(
                lambda *, sender=property_combo: self.toggle_property(sender=sender)
            )
            flevel_3.setFlags(flevel_3.flags() | Qt.ItemIsUserCheckable)
            if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                flevel_3.setCheckState(0, Qt.Checked)
            elif not self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                flevel_3.setCheckState(0, Qt.Unchecked)
            self.BackgroundsTreeWidget.insertTopLevelItem(0, flevel_3)
            break
    self.BackgroundsTreeWidget.itemChanged.connect(self.toggle_backgrounds_visibility)
    # Squeeze column width to fit content
    for col in range(self.BackgroundsTreeWidget.columnCount()):
        self.BackgroundsTreeWidget.resizeColumnToContents(col)
    self.BackgroundsTreeWidget.expandAll()


def update_backgrounds_tree_removed(
    self, removed_list=None
):  # second attchild_background_featempt
    """When background entity is removed, update Geology Tree without building a new model"""
    success = 0
    for uid in removed_list:
        for top_role in range(self.BackgroundsTreeWidget.topLevelItemCount()):
            """Iterate through every background Role top level"""

            for child_feature in range(
                self.BackgroundsTreeWidget.topLevelItem(top_role).childCount()
            ):
                """Iterate through every background Feature child"""

                for child_entity in range(
                    self.BackgroundsTreeWidget.topLevelItem(top_role)
                    .child(child_feature)
                    .childCount()
                ):
                    """Iterate through every Entity child"""

                    if (
                        self.BackgroundsTreeWidget.topLevelItem(top_role)
                        .child(child_feature)
                        .child(child_entity)
                        .text(1)
                        == uid
                    ):
                        """Complete check: entity found has the uid of the entity we need to remove. Delete child, then ensure no Child or Top Level remain empty"""
                        success = 1
                        self.BackgroundsTreeWidget.topLevelItem(top_role).child(
                            child_feature
                        ).removeChild(
                            self.BackgroundsTreeWidget.topLevelItem(top_role)
                            .child(child_feature)
                            .child(child_entity)
                        )
                        if (
                            self.BackgroundsTreeWidget.topLevelItem(top_role)
                            .child(child_feature)
                            .childCount()
                            == 0
                        ):
                            self.BackgroundsTreeWidget.topLevelItem(top_role).child(
                                child_feature
                            ).removeChild(
                                self.BackgroundsTreeWidget.topLevelItem(top_role).child(
                                    child_feature
                                )
                            )
                            if (
                                self.BackgroundsTreeWidget.topLevelItem(
                                    top_role
                                ).childCount()
                                == 0
                            ):
                                self.BackgroundsTreeWidget.takeTopLevelItem(top_role)
                        break
                if success == 1:
                    break
            if success == 1:
                break
        if success == 1:
            break


def update_backgrounds_topology_tree_added(self, new_list=None, sec_uid=None):
    """Update topology tree without creating a new model"""
    uid_list = list(new_list["uid"])
    if sec_uid:
        for i, uid in enumerate(new_list["uid"]):
            if (
                sec_uid
                != self.parent.backgrnd_coll.df.loc[
                    self.parent.backgrnd_coll.df["uid"] == uid, "x_section"
                ].values[0]
            ):
                del uid_list[i]
    for uid in uid_list:
        if (
            self.BackgroundsTopologyTreeWidget.findItems(
                self.parent.backgrnd_coll.get_uid_topology(uid),
                Qt.MatchExactly,
                0,
            )
            != []
        ):
            """Already exists a TreeItem (1 level) for the topological type"""
            counter_1 = 0
            for child_1 in range(
                self.BackgroundsTopologyTreeWidget.findItems(
                    self.parent.backgrnd_coll.get_uid_topology(uid),
                    Qt.MatchExactly,
                    0,
                )[0].childCount()
            ):
                """for cycle that loops n times as the number of subItems in the specific topological type branch"""
                if self.BackgroundsTopologyTreeWidget.findItems(
                    self.parent.backgrnd_coll.get_uid_topology(uid),
                    Qt.MatchExactly,
                    0,
                )[0].child(child_1).text(
                    0
                ) == self.parent.backgrnd_coll.get_uid_feature(
                    uid
                ):
                    counter_1 += 1
            if counter_1 != 0:
                for child_1 in range(
                    self.BackgroundsTopologyTreeWidget.findItems(
                        self.parent.backgrnd_coll.get_uid_topology(uid),
                        Qt.MatchExactly,
                        0,
                    )[0].childCount()
                ):
                    if self.BackgroundsTopologyTreeWidget.findItems(
                        self.parent.backgrnd_coll.get_uid_topology(uid),
                        Qt.MatchExactly,
                        0,
                    )[0].child(child_1).text(
                        0
                    ) == self.parent.backgrnd_coll.get_uid_feature(
                        uid
                    ):
                        """Same topological type and feature"""
                        property_combo = QComboBox()
                        property_combo.uid = uid
                        property_combo.name = "Annotations"
                        property_combo.addItem("none")
                        property_combo.addItem("name")
                        for prop in self.parent.backgrnd_coll.get_uid_properties_names(
                            uid
                        ):
                            property_combo.addItem(prop)
                        name = self.parent.backgrnd_coll.get_uid_name(uid)
                        tlevel_3 = QTreeWidgetItem(
                            self.BackgroundsTopologyTreeWidget.findItems(
                                self.parent.backgrnd_coll.get_uid_topology(uid),
                                Qt.MatchExactly,
                                0,
                            )[0].child(child_1),
                            [name, uid],
                        )
                        self.BackgroundsTopologyTreeWidget.setItemWidget(
                            tlevel_3, 2, property_combo
                        )
                        property_combo.currentIndexChanged.connect(
                            lambda *, sender=property_combo: self.toggle_property(
                                sender=sender
                            )
                        )
                        tlevel_3.setFlags(tlevel_3.flags() | Qt.ItemIsUserCheckable)
                        if self.actors_df.loc[
                            self.actors_df["uid"] == uid, "show"
                        ].values[0]:
                            tlevel_3.setCheckState(0, Qt.Checked)
                        elif not self.actors_df.loc[
                            self.actors_df["uid"] == uid, "show"
                        ].values[0]:
                            tlevel_3.setCheckState(0, Qt.Unchecked)
                        self.BackgroundsTopologyTreeWidget.insertTopLevelItem(
                            0, tlevel_3
                        )
                        break
            else:
                """Same topological type, different feature"""
                tlevel_2 = QTreeWidgetItem(
                    self.BackgroundsTopologyTreeWidget.findItems(
                        self.parent.backgrnd_coll.get_uid_topology(uid),
                        Qt.MatchExactly,
                        0,
                    )[0],
                    [self.parent.backgrnd_coll.get_uid_feature(uid)],
                )
                tlevel_2.setFlags(
                    tlevel_2.flags() | Qt.ItemIsUserTristate | Qt.ItemIsUserCheckable
                )
                self.BackgroundsTopologyTreeWidget.insertTopLevelItem(0, tlevel_2)
                property_combo = QComboBox()
                property_combo.uid = uid
                property_combo.name = "Annotations"
                property_combo.addItem("none")
                property_combo.addItem("name")
                for prop in self.parent.backgrnd_coll.get_uid_properties_names(uid):
                    property_combo.addItem(prop)
                name = self.parent.backgrnd_coll.get_uid_name(uid)
                tlevel_3 = QTreeWidgetItem(tlevel_2, [name, uid])
                self.BackgroundsTopologyTreeWidget.setItemWidget(
                    tlevel_3, 2, property_combo
                )
                property_combo.currentIndexChanged.connect(
                    lambda *, sender=property_combo: self.toggle_property(sender=sender)
                )
                tlevel_3.setFlags(tlevel_3.flags() | Qt.ItemIsUserCheckable)
                if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                    tlevel_3.setCheckState(0, Qt.Checked)
                elif not self.actors_df.loc[
                    self.actors_df["uid"] == uid, "show"
                ].values[0]:
                    tlevel_3.setCheckState(0, Qt.Unchecked)
                self.BackgroundsTopologyTreeWidget.insertTopLevelItem(0, tlevel_3)
                break
        else:
            """Different topological type and feature"""
            tlevel_1 = QTreeWidgetItem(
                self.BackgroundsTopologyTreeWidget,
                [self.parent.backgrnd_coll.get_uid_topology(uid)],
            )
            tlevel_1.setFlags(
                tlevel_1.flags() | Qt.ItemIsUserTristate | Qt.ItemIsUserCheckable
            )
            self.BackgroundsTopologyTreeWidget.insertTopLevelItem(0, tlevel_1)
            tlevel_2 = QTreeWidgetItem(
                tlevel_1,
                [self.parent.backgrnd_coll.get_uid_feature(uid)],
            )
            tlevel_2.setFlags(
                tlevel_2.flags() | Qt.ItemIsUserTristate | Qt.ItemIsUserCheckable
            )
            self.BackgroundsTopologyTreeWidget.insertTopLevelItem(0, tlevel_2)
            property_combo = QComboBox()
            property_combo.uid = uid
            property_combo.name = "Annotations"
            property_combo.addItem("none")
            property_combo.addItem("name")
            for prop in self.parent.backgrnd_coll.get_uid_properties_names(uid):
                property_combo.addItem(prop)
            name = self.parent.backgrnd_coll.get_uid_name(uid)
            tlevel_3 = QTreeWidgetItem(tlevel_2, [name, uid])
            self.BackgroundsTopologyTreeWidget.setItemWidget(
                tlevel_3, 2, property_combo
            )
            property_combo.currentIndexChanged.connect(
                lambda *, sender=property_combo: self.toggle_property(sender=sender)
            )
            tlevel_3.setFlags(tlevel_3.flags() | Qt.ItemIsUserCheckable)
            if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                tlevel_3.setCheckState(0, Qt.Checked)
            elif not self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                tlevel_3.setCheckState(0, Qt.Unchecked)
            self.BackgroundsTopologyTreeWidget.insertTopLevelItem(0, tlevel_3)
            break
    self.BackgroundsTopologyTreeWidget.itemChanged.connect(
        self.toggle_geology_visibility
    )
    # Squeeze column width to fit content
    for col in range(self.BackgroundsTopologyTreeWidget.columnCount()):
        self.BackgroundsTopologyTreeWidget.resizeColumnToContents(col)
    self.BackgroundsTopologyTreeWidget.expandAll()


def update_backgrounds_topology_tree_removed(self, removed_list=None):
    """When background entity is removed, update Topology Tree without building a new model"""
    success = 0
    for uid in removed_list:
        for top_topo_type in range(
            self.BackgroundsTopologyTreeWidget.topLevelItemCount()
        ):
            """Iterate through every Topological Role top level"""
            for child_scenario in range(
                self.BackgroundsTopologyTreeWidget.topLevelItem(
                    top_topo_type
                ).childCount()
            ):
                """Iterate through every Scenario child"""
                for child_entity in range(
                    self.BackgroundsTopologyTreeWidget.topLevelItem(top_topo_type)
                    .child(child_scenario)
                    .childCount()
                ):
                    """Iterate through every Entity child"""
                    if (
                        self.BackgroundsTopologyTreeWidget.topLevelItem(top_topo_type)
                        .child(child_scenario)
                        .child(child_entity)
                        .text(1)
                        == uid
                    ):
                        """Complete check: entity found has the uid of the entity we need to remove. Delete child, then ensure no Child or Top Level remain empty"""
                        success = 1
                        self.BackgroundsTopologyTreeWidget.topLevelItem(
                            top_topo_type
                        ).child(child_scenario).removeChild(
                            self.BackgroundsTopologyTreeWidget.topLevelItem(
                                top_topo_type
                            )
                            .child(child_scenario)
                            .child(child_entity)
                        )
                        if (
                            self.BackgroundsTopologyTreeWidget.topLevelItem(
                                top_topo_type
                            )
                            .child(child_scenario)
                            .childCount()
                            == 0
                        ):
                            self.BackgroundsTopologyTreeWidget.topLevelItem(
                                top_topo_type
                            ).removeChild(
                                self.BackgroundsTopologyTreeWidget.topLevelItem(
                                    top_topo_type
                                ).child(child_scenario)
                            )
                            if (
                                self.BackgroundsTopologyTreeWidget.topLevelItem(
                                    top_topo_type
                                ).childCount()
                                == 0
                            ):
                                self.BackgroundsTopologyTreeWidget.takeTopLevelItem(
                                    top_topo_type
                                )
                        break
                if success == 1:
                    break
            if success == 1:
                break


def update_backgrounds_checkboxes(self, uid=None, uid_checkState=None):
    """Update checkboxes in background tree, called when state changed in topology tree."""
    item = self.BackgroundsTreeWidget.findItems(
        uid, Qt.MatchFixedString | Qt.MatchRecursive, 1
    )[0]
    if uid_checkState == Qt.Checked:
        item.setCheckState(0, Qt.Checked)
    elif uid_checkState == Qt.Unchecked:
        item.setCheckState(0, Qt.Unchecked)


def update_backgrounds_topology_checkboxes(self, uid=None, uid_checkState=None):
    """Update checkboxes in topology tree, called when state changed in geology tree."""
    item = self.BackgroundsTopologyTreeWidget.findItems(
        uid, Qt.MatchFixedString | Qt.MatchRecursive, 1
    )[0]
    if uid_checkState == Qt.Checked:
        item.setCheckState(0, Qt.Checked)
    elif uid_checkState == Qt.Unchecked:
        item.setCheckState(0, Qt.Unchecked)


def toggle_backgrounds_visibility(self, item):
    """Called by self.BackgroundsTreeWidget.itemChanged.connect(self.toggle_backgrounds_visibility) and self.BackgroundsTopologyTreeWidget.itemChanged.connect(self.toggle_backgrounds_visibility)"""

    name = item.text(0)  # not used
    uid = item.text(1)
    uid_checkState = item.checkState(0)
    if (
        uid
    ):  # needed to skip messages from upper levels of tree that do not broadcast uid's
        if uid_checkState == Qt.Checked:
            if not self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                self.actors_df.loc[self.actors_df["uid"] == uid, "show"] = True
                self.set_actor_visible(uid=uid, visible=True, name=name)
        elif uid_checkState == Qt.Unchecked:
            if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                self.actors_df.loc[self.actors_df["uid"] == uid, "show"] = False
                self.set_actor_visible(uid=uid, visible=False, name=name)
        """Before updating checkboxes, disconnect signals to background and topology tree, if they are set,
        to avoid a nasty loop that disrupts the trees, then reconnect them (it is also possible that
        they are automatically reconnected whe the trees are rebuilt."""
        self.BackgroundsTreeWidget.itemChanged.disconnect()
        self.BackgroundsTopologyTreeWidget.itemChanged.disconnect()
        self.update_backgrounds_checkboxes(uid=uid, uid_checkState=uid_checkState)
        self.update_backgrounds_topology_checkboxes(
            uid=uid, uid_checkState=uid_checkState
        )
        self.BackgroundsTreeWidget.itemChanged.connect(
            self.toggle_backgrounds_visibility
        )
        self.BackgroundsTopologyTreeWidget.itemChanged.connect(
            self.toggle_backgrounds_visibility
        )
