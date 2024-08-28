from PyQt5.QtWidgets import QTreeWidgetItem, QComboBox
from pandas import unique as pd_unique
from PyQt5.QtCore import Qt


# Methods used to build and update the FLUID and FLUID TOPOLOGY trees __________________???

def create_fluids_tree(self):
    """Create fluids tree with checkboxes and properties"""
    self.FluidsTreeWidget.clear()
    self.FluidsTreeWidget.setColumnCount(3)
    self.FluidsTreeWidget.setHeaderLabels(
        ["Role > Feature > Scenario > Name", "uid", "property"]
    )
    self.FluidsTreeWidget.hideColumn(1)  # hide the uid column
    self.FluidsTreeWidget.setItemsExpandable(True)
    roles = pd_unique(self.parent.fluids_coll.df.query(self.view_filter)["role"])
    for role in roles:
        flevel_1 = QTreeWidgetItem(
            self.FluidsTreeWidget, [role]
        )  # self.FluidsTreeWidget as parent -> top level
        flevel_1.setFlags(
            flevel_1.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
        )
        features = pd_unique(
            self.parent.fluids_coll.df.query(self.view_filter).loc[
                self.parent.fluids_coll.df.query(self.view_filter)["role"] == role,
                "feature",
            ]
        )
        for feature in features:
            flevel_2 = QTreeWidgetItem(
                flevel_1, [feature]
            )  # flevel_1 as parent -> 1st middle level
            flevel_2.setFlags(
                flevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
            )
            fluid_scenario = pd_unique(
                self.parent.fluids_coll.df.query(self.view_filter).loc[
                    (self.parent.fluids_coll.df.query(self.view_filter)["role"] == role)
                    & (self.parent.fluids_coll.df.query(self.view_filter)["feature"] == feature),
                    "scenario",
                ]
            )
            for scenario in fluid_scenario:
                flevel_3 = QTreeWidgetItem(
                    flevel_2, [scenario]
                )  # flevel_2 as parent -> 2nd middle level
                flevel_3.setFlags(
                    flevel_3.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
                )
                uids = self.parent.fluids_coll.df.query(self.view_filter).loc[
                    (self.parent.fluids_coll.df.query(self.view_filter)["role"] == role)
                    & (self.parent.fluids_coll.df.query(self.view_filter)["feature"] == feature)
                    & (self.parent.fluids_coll.df.query(self.view_filter)["scenario"] == scenario),
                    "uid",
                ].to_list()
                for uid in uids:
                    property_combo = QComboBox()
                    property_combo.uid = uid
                    property_combo.addItem("none")
                    property_combo.addItem("X")
                    property_combo.addItem("Y")
                    property_combo.addItem("Z")
                    for prop in self.parent.fluids_coll.get_uid_properties_names(
                            uid
                    ):
                        property_combo.addItem(prop)
                    name = self.parent.fluids_coll.df.loc[
                        (self.parent.fluids_coll.df["uid"] == uid), "name"
                    ].values[0]
                    flevel_4 = QTreeWidgetItem(
                        flevel_3, [name, uid]
                    )  # flevel_3 as parent -> lower level
                    self.FluidsTreeWidget.setItemWidget(flevel_4, 2, property_combo)
                    property_combo.currentIndexChanged.connect(
                        lambda: self.toggle_property()
                    )
                    flevel_4.setFlags(flevel_4.flags() | Qt.ItemIsUserCheckable)
                    if self.actors_df.loc[
                        self.actors_df["uid"] == uid, "show"
                    ].values[0]:
                        flevel_4.setCheckState(0, Qt.Checked)
                    elif not self.actors_df.loc[
                        self.actors_df["uid"] == uid, "show"
                    ].values[0]:
                        flevel_4.setCheckState(0, Qt.Unchecked)
    """Send messages. Note that with tristate several signals are emitted in a sequence, one for each
    changed item, but upper levels do not broadcast uid's so they are filtered in the toggle method."""
    self.FluidsTreeWidget.itemChanged.connect(
        self.toggle_fluids_visibility 
    )
    self.FluidsTreeWidget.expandAll()


def create_fluids_topology_tree(self):
    """Create topology tree with checkboxes and properties"""
    self.FluidsTopologyTreeWidget.clear()
    self.FluidsTopologyTreeWidget.setColumnCount(3)
    self.FluidsTopologyTreeWidget.setHeaderLabels(
        ["Role > Scenario > Name", "uid", "property"]
    )
    self.FluidsTopologyTreeWidget.hideColumn(1)  # hide the uid column
    self.FluidsTopologyTreeWidget.setItemsExpandable(True)
    topo_types = pd_unique(self.parent.fluids_coll.df.query(self.view_filter)["topology"])

    for topo_type in topo_types:
        tlevel_1 = QTreeWidgetItem(
            self.FluidsTopologyTreeWidget, [topo_type]
        )  # self.GeologyTreeWidget as parent -> top level
        tlevel_1.setFlags(
            tlevel_1.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
        )
        for scenario in pd_unique(
                self.parent.fluids_coll.df.query(self.view_filter).loc[
                    self.parent.fluids_coll.df.query(self.view_filter)["topology"] == topo_type,
                    "scenario",
                ]
        ):
            tlevel_2 = QTreeWidgetItem(
                tlevel_1, [scenario]
            )  # tlevel_1 as parent -> middle level
            tlevel_2.setFlags(
                tlevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
            )
            uids = self.parent.fluids_coll.df.query(self.view_filter).loc[
                (self.parent.fluids_coll.df.query(self.view_filter)["topology"] == topo_type)
                & (self.parent.fluids_coll.df.query(self.view_filter)["scenario"] == scenario),
                "uid",
            ].to_list()
            for uid in uids:
                property_combo = QComboBox()
                property_combo.uid = uid
                property_combo.addItem("none")
                property_combo.addItem("X")
                property_combo.addItem("Y")
                property_combo.addItem("Z")
                for prop in self.parent.fluids_coll.get_uid_properties_names(uid):
                    property_combo.addItem(prop)
                name = self.parent.fluids_coll.df.loc[
                    self.parent.fluids_coll.df["uid"] == uid, "name"
                ].values[0]
                tlevel_3 = QTreeWidgetItem(
                    tlevel_2, [name, uid]
                )  # tlevel_2 as parent -> lower level
                self.FluidsTopologyTreeWidget.setItemWidget(
                    tlevel_3, 2, property_combo
                )
                property_combo.currentIndexChanged.connect(
                    lambda: self.toggle_property()
                )
                tlevel_3.setFlags(tlevel_3.flags() | Qt.ItemIsUserCheckable)
                if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[
                    0
                ]:
                    tlevel_3.setCheckState(0, Qt.Checked)
                elif not self.actors_df.loc[
                    self.actors_df["uid"] == uid, "show"
                ].values[0]:
                    tlevel_3.setCheckState(0, Qt.Unchecked)
    """Send messages. Note that with tristate several signals are emitted in a sequence, one for each
    changed item, but upper levels do not broadcast uid's so they are filtered in the toggle method."""
    self.FluidsTopologyTreeWidget.itemChanged.connect(
        self.toggle_fluids_visibility 
    )
    self.FluidsTopologyTreeWidget.expandAll()


def update_fluids_tree_added(self, new_list=None, sec_uid=None):
    """Update fluid tree without creating a new model"""
    uid_list = list(new_list["uid"])
    if sec_uid:
        for i, uid in enumerate(new_list["uid"]):
            if (
                    sec_uid
                    != self.parent.fluids_coll.df.loc[
                self.parent.fluids_coll.df["uid"] == uid, "x_section"
            ].values[0]
            ):
                del uid_list[i]
    for uid in uid_list:
        if (
                self.FluidsTreeWidget.findItems(
                    self.parent.fluids_coll.get_uid_type(uid), Qt.MatchExactly, 0
                )
                != []
        ):
            """Already exists a TreeItem (1 level) for the fluid type"""
            counter_1 = 0
            for child_1 in range(
                    self.FluidsTreeWidget.findItems(
                        self.parent.fluids_coll.get_uid_type(uid),
                        Qt.MatchExactly,
                        0,
                    )[0].childCount()
            ):
                """for cycle that loops n times as the number of subItems in the specific fluid type branch"""
                if self.FluidsTreeWidget.findItems(
                        self.parent.fluids_coll.get_uid_type(uid),
                        Qt.MatchExactly,
                        0,
                )[0].child(child_1).text(
                    0
                ) == self.parent.fluids_coll.get_uid_feature(
                    uid
                ):
                    counter_1 += 1
            if counter_1 != 0:
                for child_1 in range(
                        self.FluidsTreeWidget.findItems(
                            self.parent.fluids_coll.get_uid_type(uid),
                            Qt.MatchExactly,
                            0,
                        )[0].childCount()
                ):
                    if self.FluidsTreeWidget.findItems(
                            self.parent.fluids_coll.get_uid_type(uid),
                            Qt.MatchExactly,
                            0,
                    )[0].child(child_1).text(
                        0
                    ) == self.parent.fluids_coll.get_uid_feature(
                        uid
                    ):
                        """Already exists a TreeItem (2 level) for the fluid feature"""
                        counter_2 = 0
                        for child_2 in range(
                                self.FluidsTreeWidget.itemBelow(
                                    self.FluidsTreeWidget.findItems(
                                        self.parent.fluids_coll.get_uid_type(uid),
                                        Qt.MatchExactly,
                                        0,
                                    )[0]
                                ).childCount()
                        ):
                            """for cycle that loops n times as the number of sub-subItems in the specific fluid type and fluid feature branch"""
                            if self.FluidsTreeWidget.itemBelow(
                                    self.FluidsTreeWidget.findItems(
                                        self.parent.fluids_coll.get_uid_type(uid),
                                        Qt.MatchExactly,
                                        0,
                                    )[0]
                            ).child(child_2).text(
                                0
                            ) == self.parent.fluids_coll.get_uid_scenario(
                                uid
                            ):
                                counter_2 += 1
                        if counter_2 != 0:
                            for child_2 in range(
                                    self.FluidsTreeWidget.itemBelow(
                                        self.FluidsTreeWidget.findItems(
                                            self.parent.fluids_coll.get_uid_type(
                                                uid
                                            ),
                                            Qt.MatchExactly,
                                            0,
                                        )[0]
                                    ).childCount()
                            ):
                                if self.FluidsTreeWidget.itemBelow(
                                        self.FluidsTreeWidget.findItems(
                                            self.parent.fluids_coll.get_uid_type(
                                                uid
                                            ),
                                            Qt.MatchExactly,
                                            0,
                                        )[0]
                                ).child(child_2).text(
                                    0
                                ) == self.parent.fluids_coll.get_uid_scenario(
                                    uid
                                ):
                                    """Same fluid type, fluid feature and scenario"""
                                    property_combo = QComboBox()
                                    property_combo.uid = uid
                                    property_combo.addItem("none")
                                    property_combo.addItem("X")
                                    property_combo.addItem("Y")
                                    property_combo.addItem("Z")
                                    for (
                                            prop
                                    ) in self.parent.fluids_coll.get_uid_properties_names(
                                        uid
                                    ):
                                        property_combo.addItem(prop)
                                    name = self.parent.fluids_coll.get_uid_name(uid)
                                    flevel_4 = QTreeWidgetItem(
                                        self.FluidsTreeWidget.findItems(
                                            self.parent.fluids_coll.get_uid_type(
                                                uid
                                            ),
                                            Qt.MatchExactly,
                                            0,
                                        )[0]
                                        .child(child_1)
                                        .child(child_2),
                                        [name, uid],
                                    )
                                    self.FluidsTreeWidget.setItemWidget(
                                        flevel_4, 2, property_combo
                                    )
                                    property_combo.currentIndexChanged.connect(
                                        lambda: self.toggle_property()
                                    )
                                    flevel_4.setFlags(
                                        flevel_4.flags() | Qt.ItemIsUserCheckable
                                    )
                                    if self.actors_df.loc[
                                        self.actors_df["uid"] == uid, "show"
                                    ].values[0]:
                                        flevel_4.setCheckState(0, Qt.Checked)
                                    elif not self.actors_df.loc[
                                        self.actors_df["uid"] == uid, "show"
                                    ].values[0]:
                                        flevel_4.setCheckState(0, Qt.Unchecked)
                                    self.FluidsTreeWidget.insertTopLevelItem(
                                        0, flevel_4
                                    )
                                    break
                        else:
                            """Same fluid type and fluid feature, different scenario"""
                            flevel_3 = QTreeWidgetItem(
                                self.FluidsTreeWidget.findItems(
                                    self.parent.fluids_coll.get_uid_type(uid),
                                    Qt.MatchExactly,
                                    0,
                                )[0].child(child_1),
                                [self.parent.fluids_coll.get_uid_scenario(uid)],
                            )
                            flevel_3.setFlags(
                                flevel_3.flags()
                                | Qt.ItemIsTristate
                                | Qt.ItemIsUserCheckable
                            )
                            self.FluidsTreeWidget.insertTopLevelItem(0, flevel_3)
                            property_combo = QComboBox()
                            property_combo.uid = uid
                            property_combo.addItem("none")
                            property_combo.addItem("X")
                            property_combo.addItem("Y")
                            property_combo.addItem("Z")
                            for (
                                    prop
                            ) in self.parent.fluids_coll.get_uid_properties_names(
                                uid
                            ):
                                property_combo.addItem(prop)
                            name = self.parent.fluids_coll.get_uid_name(uid)
                            flevel_4 = QTreeWidgetItem(flevel_3, [name, uid])
                            self.FluidsTreeWidget.setItemWidget(
                                flevel_4, 2, property_combo
                            )
                            property_combo.currentIndexChanged.connect(
                                lambda: self.toggle_property()
                            )
                            flevel_4.setFlags(
                                flevel_4.flags() | Qt.ItemIsUserCheckable
                            )
                            if self.actors_df.loc[
                                self.actors_df["uid"] == uid, "show"
                            ].values[0]:
                                flevel_4.setCheckState(0, Qt.Checked)
                            elif not self.actors_df.loc[
                                self.actors_df["uid"] == uid, "show"
                            ].values[0]:
                                flevel_4.setCheckState(0, Qt.Unchecked)
                            self.FluidsTreeWidget.insertTopLevelItem(0, flevel_4)
                            break
            else:
                """Same fluid type, different fluid feature and scenario"""
                flevel_2 = QTreeWidgetItem(
                    self.FluidsTreeWidget.findItems(
                        self.parent.fluids_coll.get_uid_type(uid),
                        Qt.MatchExactly,
                        0,
                    )[0],
                    [self.parent.fluids_coll.get_uid_feature(uid)],
                )
                flevel_2.setFlags(
                    flevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
                )
                self.FluidsTreeWidget.insertTopLevelItem(0, flevel_2)
                flevel_3 = QTreeWidgetItem(
                    flevel_2, [self.parent.fluids_coll.get_uid_scenario(uid)]
                )
                flevel_3.setFlags(
                    flevel_3.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
                )
                self.FluidsTreeWidget.insertTopLevelItem(0, flevel_3)
                property_combo = QComboBox()
                property_combo.uid = uid
                property_combo.addItem("none")
                property_combo.addItem("X")
                property_combo.addItem("Y")
                property_combo.addItem("Z")
                for prop in self.parent.fluids_coll.get_uid_properties_names(uid):
                    property_combo.addItem(prop)
                name = self.parent.fluids_coll.get_uid_name(uid)
                flevel_4 = QTreeWidgetItem(flevel_3, [name, uid])
                self.FluidsTreeWidget.setItemWidget(flevel_4, 2, property_combo)
                property_combo.currentIndexChanged.connect(
                    lambda: self.toggle_property()
                )
                flevel_4.setFlags(flevel_4.flags() | Qt.ItemIsUserCheckable)
                if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[
                    0
                ]:
                    flevel_4.setCheckState(0, Qt.Checked)
                elif not self.actors_df.loc[
                    self.actors_df["uid"] == uid, "show"
                ].values[0]:
                    flevel_4.setCheckState(0, Qt.Unchecked)
                self.FluidsTreeWidget.insertTopLevelItem(0, flevel_4)
                break
        else:
            """Different fluid type, fluid feature and scenario"""
            flevel_1 = QTreeWidgetItem(
                self.FluidsTreeWidget,
                [self.parent.fluids_coll.get_uid_type(uid)],
            )
            flevel_1.setFlags(
                flevel_1.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
            )
            self.FluidsTreeWidget.insertTopLevelItem(0, flevel_1)
            flevel_2 = QTreeWidgetItem(
                flevel_1, [self.parent.fluids_coll.get_uid_feature(uid)]
            )
            flevel_2.setFlags(
                flevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
            )
            self.FluidsTreeWidget.insertTopLevelItem(0, flevel_2)
            flevel_3 = QTreeWidgetItem(
                flevel_2, [self.parent.fluids_coll.get_uid_scenario(uid)]
            )
            flevel_3.setFlags(
                flevel_3.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
            )
            self.FluidsTreeWidget.insertTopLevelItem(0, flevel_3)
            property_combo = QComboBox()
            property_combo.uid = uid
            property_combo.addItem("none")
            property_combo.addItem("X")
            property_combo.addItem("Y")
            property_combo.addItem("Z")
            for prop in self.parent.fluids_coll.get_uid_properties_names(uid):
                property_combo.addItem(prop)
            name = self.parent.fluids_coll.get_uid_name(uid)
            flevel_4 = QTreeWidgetItem(flevel_3, [name, uid])
            self.FluidsTreeWidget.setItemWidget(flevel_4, 2, property_combo)
            property_combo.currentIndexChanged.connect(
                lambda: self.toggle_property()
            )
            flevel_4.setFlags(flevel_4.flags() | Qt.ItemIsUserCheckable)
            if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                flevel_4.setCheckState(0, Qt.Checked)
            elif not self.actors_df.loc[
                self.actors_df["uid"] == uid, "show"
            ].values[0]:
                flevel_4.setCheckState(0, Qt.Unchecked)
            self.FluidsTreeWidget.insertTopLevelItem(0, flevel_4)
            break
    self.FluidsTreeWidget.itemChanged.connect(
        self.toggle_fluids_visibility 
    )
    self.FluidsTreeWidget.expandAll()


def update_fluids_tree_removed(self, removed_list=None):  # second attchild_fluid_featempt
    """When fluid entity is removed, update Geology Tree without building a new model"""
    success = 0
    for uid in removed_list:
        for top_fluid_type in range(self.FluidsTreeWidget.topLevelItemCount()):
            """Iterate through every fluid Role top level"""
            for child_fluid_feat in range(
                    self.FluidsTreeWidget.topLevelItem(top_fluid_type).childCount()
            ):
                """Iterate through every fluid Feature child"""
                for child_scenario in range(
                        self.FluidsTreeWidget.topLevelItem(top_fluid_type)
                                .child(child_fluid_feat)
                                .childCount()
                ):
                    """Iterate through every Scenario child"""
                    for child_entity in range(
                            self.FluidsTreeWidget.topLevelItem(top_fluid_type)
                                    .child(child_fluid_feat)
                                    .child(child_scenario)
                                    .childCount()
                    ):
                        """Iterate through every Entity child"""
                        if (
                                self.FluidsTreeWidget.topLevelItem(top_fluid_type)
                                        .child(child_fluid_feat)
                                        .child(child_scenario)
                                        .child(child_entity)
                                        .text(1)
                                == uid
                        ):
                            """Complete check: entity found has the uid of the entity we need to remove. Delete child, then ensure no Child or Top Level remain empty"""
                            success = 1
                            self.FluidsTreeWidget.topLevelItem(
                                top_fluid_type
                            ).child(child_fluid_feat).child(
                                child_scenario
                            ).removeChild(
                                self.FluidsTreeWidget.topLevelItem(top_fluid_type)
                                .child(child_fluid_feat)
                                .child(child_scenario)
                                .child(child_entity)
                            )
                            if (
                                    self.FluidsTreeWidget.topLevelItem(top_fluid_type)
                                            .child(child_fluid_feat)
                                            .child(child_scenario)
                                            .childCount()
                                    == 0
                            ):
                                self.FluidsTreeWidget.topLevelItem(
                                    top_fluid_type
                                ).child(child_fluid_feat).removeChild(
                                    self.FluidsTreeWidget.topLevelItem(
                                        top_fluid_type
                                    )
                                    .child(child_fluid_feat)
                                    .child(child_scenario)
                                )
                                if (
                                        self.FluidsTreeWidget.topLevelItem(
                                            top_fluid_type
                                        )
                                                .child(child_fluid_feat)
                                                .childCount()
                                        == 0
                                ):
                                    self.FluidsTreeWidget.topLevelItem(
                                        top_fluid_type
                                    ).removeChild(
                                        self.FluidsTreeWidget.topLevelItem(
                                            top_fluid_type
                                        ).child(child_fluid_feat)
                                    )
                                    if (
                                            self.FluidsTreeWidget.topLevelItem(
                                                top_fluid_type
                                            ).childCount()
                                            == 0
                                    ):
                                        self.FluidsTreeWidget.takeTopLevelItem(
                                            top_fluid_type
                                        )
                            break
                    if success == 1:
                        break
                if success == 1:
                    break
            if success == 1:
                break


def update_fluids_topology_tree_added(self, new_list=None, sec_uid=None):
    """Update topology tree without creating a new model"""
    uid_list = list(new_list["uid"])
    if sec_uid:
        for i, uid in enumerate(new_list["uid"]):
            if (
                    sec_uid
                    != self.parent.geol_coll.df.loc[
                self.parent.geol_coll.df["uid"] == uid, "x_section"
            ].values[0]
            ):
                del uid_list[i]
    for uid in uid_list:
        if (
                self.FluidsTopologyTreeWidget.findItems(
                    self.parent.fluids_coll.get_uid_topology(uid),
                    Qt.MatchExactly,
                    0,
                )
                != []
        ):
            """Already exists a TreeItem (1 level) for the topological type"""
            counter_1 = 0
            for child_1 in range(
                    self.FluidsTopologyTreeWidget.findItems(
                        self.parent.fluids_coll.get_uid_topology(uid),
                        Qt.MatchExactly,
                        0,
                    )[0].childCount()
            ):
                """for cycle that loops n times as the number of subItems in the specific topological type branch"""
                if self.FluidsTopologyTreeWidget.findItems(
                        self.parent.fluids_coll.get_uid_topology(uid),
                        Qt.MatchExactly,
                        0,
                )[0].child(child_1).text(
                    0
                ) == self.parent.fluids_coll.get_uid_scenario(
                    uid
                ):
                    counter_1 += 1
            if counter_1 != 0:
                for child_1 in range(
                        self.FluidsTopologyTreeWidget.findItems(
                            self.parent.fluids_coll.get_uid_topology(uid),
                            Qt.MatchExactly,
                            0,
                        )[0].childCount()
                ):
                    if self.FluidsTopologyTreeWidget.findItems(
                            self.parent.fluids_coll.get_uid_topology(uid),
                            Qt.MatchExactly,
                            0,
                    )[0].child(child_1).text(
                        0
                    ) == self.parent.fluids_coll.get_uid_scenario(
                        uid
                    ):
                        """Same topological type and scenario"""
                        property_combo = QComboBox()
                        property_combo.uid = uid
                        property_combo.addItem("none")
                        property_combo.addItem("X")
                        property_combo.addItem("Y")
                        property_combo.addItem("Z")
                        for (
                                prop
                        ) in self.parent.fluids_coll.get_uid_properties_names(uid):
                            property_combo.addItem(prop)
                        name = self.parent.fluids_coll.get_uid_name(uid)
                        tlevel_3 = QTreeWidgetItem(
                            self.FluidsTopologyTreeWidget.findItems(
                                self.parent.fluids_coll.get_uid_topology(
                                    uid
                                ),
                                Qt.MatchExactly,
                                0,
                            )[0].child(child_1),
                            [name, uid],
                        )
                        self.FluidsTopologyTreeWidget.setItemWidget(
                            tlevel_3, 2, property_combo
                        )
                        property_combo.currentIndexChanged.connect(
                            lambda: self.toggle_property()
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
                        self.TopologyTreeWidget.insertTopLevelItem(0, tlevel_3)
                        break
            else:
                """Same topological type, different scenario"""
                tlevel_2 = QTreeWidgetItem(
                    self.FluidsTopologyTreeWidget.findItems(
                        self.parent.fluids_coll.get_uid_topology(uid),
                        Qt.MatchExactly,
                        0,
                    )[0],
                    [self.parent.fluids_coll.get_uid_scenario(uid)],
                )
                tlevel_2.setFlags(
                    tlevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
                )
                self.FluidsTopologyTreeWidget.insertTopLevelItem(0, tlevel_2)
                property_combo = QComboBox()
                property_combo.uid = uid
                property_combo.addItem("none")
                property_combo.addItem("X")
                property_combo.addItem("Y")
                property_combo.addItem("Z")
                for prop in self.parent.fluids_coll.get_uid_properties_names(uid):
                    property_combo.addItem(prop)
                name = self.parent.fluids_coll.get_uid_name(uid)
                tlevel_3 = QTreeWidgetItem(tlevel_2, [name, uid])
                self.FluidsTopologyTreeWidget.setItemWidget(
                    tlevel_3, 2, property_combo
                )
                property_combo.currentIndexChanged.connect(
                    lambda: self.toggle_property()
                )
                tlevel_3.setFlags(tlevel_3.flags() | Qt.ItemIsUserCheckable)
                if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[
                    0
                ]:
                    tlevel_3.setCheckState(0, Qt.Checked)
                elif not self.actors_df.loc[
                    self.actors_df["uid"] == uid, "show"
                ].values[0]:
                    tlevel_3.setCheckState(0, Qt.Unchecked)
                self.FluidsTopologyTreeWidget.insertTopLevelItem(0, tlevel_3)
                break
        else:
            """Different topological type and scenario"""
            tlevel_1 = QTreeWidgetItem(
                self.FluidsTopologyTreeWidget,
                [self.parent.fluids_coll.get_uid_topology(uid)],
            )
            tlevel_1.setFlags(
                tlevel_1.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
            )
            self.FluidsTopologyTreeWidget.insertTopLevelItem(0, tlevel_1)
            tlevel_2 = QTreeWidgetItem(
                tlevel_1, [self.parent.fluids_coll.get_uid_scenario(uid)]
            )
            tlevel_2.setFlags(
                tlevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
            )
            self.FluidsTopologyTreeWidget.insertTopLevelItem(0, tlevel_2)
            property_combo = QComboBox()
            property_combo.uid = uid
            property_combo.addItem("none")
            property_combo.addItem("X")
            property_combo.addItem("Y")
            property_combo.addItem("Z")
            for prop in self.parent.fluids_coll.get_uid_properties_names(uid):
                property_combo.addItem(prop)
            name = self.parent.fluids_coll.get_uid_name(uid)
            tlevel_3 = QTreeWidgetItem(tlevel_2, [name, uid])
            self.FluidsTopologyTreeWidget.setItemWidget(tlevel_3, 2, property_combo)
            property_combo.currentIndexChanged.connect(
                lambda: self.toggle_property()
            )
            tlevel_3.setFlags(tlevel_3.flags() | Qt.ItemIsUserCheckable)
            if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                tlevel_3.setCheckState(0, Qt.Checked)
            elif not self.actors_df.loc[
                self.actors_df["uid"] == uid, "show"
            ].values[0]:
                tlevel_3.setCheckState(0, Qt.Unchecked)
            self.FluidsTopologyTreeWidget.insertTopLevelItem(0, tlevel_3)
            break
    self.FluidsTopologyTreeWidget.itemChanged.connect(
        self.toggle_fluids_visibility 
    )
    self.FluidsTopologyTreeWidget.expandAll()


def update_fluids_topology_tree_removed(self, removed_list=None):
    """When fluid entity is removed, update Topology Tree without building a new model"""
    success = 0
    for uid in removed_list:
        for top_topo_type in range(
                self.FluidsTopologyTreeWidget.topLevelItemCount()
        ):
            """Iterate through every Topological Role top level"""
            for child_scenario in range(
                    self.FluidsTopologyTreeWidget.topLevelItem(
                        top_topo_type
                    ).childCount()
            ):
                """Iterate through every Scenario child"""
                for child_entity in range(
                        self.FluidsTopologyTreeWidget.topLevelItem(top_topo_type)
                                .child(child_scenario)
                                .childCount()
                ):
                    """Iterate through every Entity child"""
                    if (
                            self.FluidsTopologyTreeWidget.topLevelItem(top_topo_type)
                                    .child(child_scenario)
                                    .child(child_entity)
                                    .text(1)
                            == uid
                    ):
                        """Complete check: entity found has the uid of the entity we need to remove. Delete child, then ensure no Child or Top Level remain empty"""
                        success = 1
                        self.FluidsTopologyTreeWidget.topLevelItem(
                            top_topo_type
                        ).child(child_scenario).removeChild(
                            self.FluidsTopologyTreeWidget.topLevelItem(
                                top_topo_type
                            )
                            .child(child_scenario)
                            .child(child_entity)
                        )
                        if (
                                self.FluidsTopologyTreeWidget.topLevelItem(
                                    top_topo_type
                                )
                                        .child(child_scenario)
                                        .childCount()
                                == 0
                        ):
                            self.FluidsTopologyTreeWidget.topLevelItem(
                                top_topo_type
                            ).removeChild(
                                self.FluidsTopologyTreeWidget.topLevelItem(
                                    top_topo_type
                                ).child(child_scenario)
                            )
                            if (
                                    self.FluidsTopologyTreeWidget.topLevelItem(
                                        top_topo_type
                                    ).childCount()
                                    == 0
                            ):
                                self.FluidsTopologyTreeWidget.takeTopLevelItem(
                                    top_topo_type
                                )
                        break
                if success == 1:
                    break
            if success == 1:
                break


def update_fluids_checkboxes(self, uid=None, uid_checkState=None):
    """Update checkboxes in fluid tree, called when state changed in topology tree."""
    item = self.FluidsTreeWidget.findItems(
        uid, Qt.MatchFixedString | Qt.MatchRecursive, 1
    )[0]
    if uid_checkState == Qt.Checked:
        item.setCheckState(0, Qt.Checked)
    elif uid_checkState == Qt.Unchecked:
        item.setCheckState(0, Qt.Unchecked)


def update_fluids_topology_checkboxes(self, uid=None, uid_checkState=None):
    """Update checkboxes in topology tree, called when state changed in geology tree."""
    item = self.FluidsTopologyTreeWidget.findItems(
        uid, Qt.MatchFixedString | Qt.MatchRecursive, 1
    )[0]
    if uid_checkState == Qt.Checked:
        item.setCheckState(0, Qt.Checked)
    elif uid_checkState == Qt.Unchecked:
        item.setCheckState(0, Qt.Unchecked)


def toggle_fluids_visibility (self, item):
    """Called by self.FluidsTreeWidget.itemChanged.connect(self.toggle_fluids_visibility ) and self.FluidsTopologyTreeWidget.itemChanged.connect(self.toggle_fluids_visibility )"""
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
                self.actors_df.loc[self.actors_df["uid"] == uid, "show"] = True
                self.set_actor_visible(uid=uid, visible=True)
        elif uid_checkState == Qt.Unchecked:
            if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                self.actors_df.loc[self.actors_df["uid"] == uid, "show"] = False
                self.set_actor_visible(uid=uid, visible=False)
        """Before updating checkboxes, disconnect signals to fluid and topology tree, if they are set,
        to avoid a nasty loop that disrupts the trees, then reconnect them (it is also possible that
        they are automatically reconnected whe the trees are rebuilt."""
        self.FluidsTreeWidget.itemChanged.disconnect()
        self.FluidsTopologyTreeWidget.itemChanged.disconnect()
        self.update_fluids_checkboxes(uid=uid, uid_checkState=uid_checkState)
        self.update_fluids_topology_checkboxes(
            uid=uid, uid_checkState=uid_checkState
        )
        self.FluidsTreeWidget.itemChanged.connect(
            self.toggle_fluids_visibility 
        )
        self.FluidsTopologyTreeWidget.itemChanged.connect(
            self.toggle_fluids_visibility 
        )
