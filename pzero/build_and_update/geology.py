from PyQt5.QtWidgets import QTreeWidgetItem, QComboBox
from pandas import unique as pd_unique
from PyQt5.QtCore import Qt

# ================================  build and update trees and tables ================================

# Methods used to build and update the GEOLOGY and TOPOLOGY trees

# It would be nice to find a way to further separate the two trees but it looks like they are very co-dependent


def create_geology_tree(self):
    """Create geology tree with checkboxes and properties"""
    self.GeologyTreeWidget.clear()
    self.GeologyTreeWidget.setColumnCount(3)
    self.GeologyTreeWidget.setHeaderLabels(
        ["Role > Feature > Scenario > Name", "uid", "property"]
    )
    # hide the uid column
    self.GeologyTreeWidget.hideColumn(1)
    self.GeologyTreeWidget.setItemsExpandable(True)
    geo_types = pd_unique(self.parent.geol_coll.df.query(self.view_filter)["role"])
    for role in geo_types:
        # self.GeologyTreeWidget as parent -> top level
        glevel_1 = QTreeWidgetItem(
            self.GeologyTreeWidget, [role]
        )
        glevel_1.setFlags(
            glevel_1.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
        )
        features = pd_unique(
            self.parent.geol_coll.df.query(self.view_filter).loc[
                self.parent.geol_coll.df.query(self.view_filter)["role"] == role,
                "feature",
            ]
        )
        for feature in features:
            # glevel_1 as parent -> 1st middle level
            glevel_2 = QTreeWidgetItem(
                glevel_1, [feature]
            )
            glevel_2.setFlags(
                glevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
            )
            geo_scenario = pd_unique(
                self.parent.geol_coll.df.query(self.view_filter).loc[
                    (self.parent.geol_coll.df.query(self.view_filter)["role"] == role)
                    & (
                            self.parent.geol_coll.df.query(self.view_filter)["feature"]
                            == feature
                    ),
                    "scenario",
                ]
            )
            for scenario in geo_scenario:
                # glevel_2 as parent -> 2nd middle level
                glevel_3 = QTreeWidgetItem(
                    glevel_2, [scenario]
                )
                glevel_3.setFlags(
                    glevel_3.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
                )
                uids = self.parent.geol_coll.df.query(self.view_filter).loc[
                    (self.parent.geol_coll.df.query(self.view_filter)["role"] == role)
                    & (
                            self.parent.geol_coll.df.query(self.view_filter)["feature"]
                            == feature
                    )
                    & (self.parent.geol_coll.df.query(self.view_filter)["scenario"] == scenario),
                    "uid",
                ].to_list()
                for uid in uids:
                    property_combo = QComboBox()
                    property_combo.uid = uid
                    property_combo.addItem("none")
                    property_combo.addItem("X")
                    property_combo.addItem("Y")
                    property_combo.addItem("Z")
                    for prop in self.parent.geol_coll.get_uid_properties_names(uid):
                        property_combo.addItem(prop)
                    name = self.parent.geol_coll.df.loc[
                        (self.parent.geol_coll.df["uid"] == uid), "name"
                    ].values[0]
                    # glevel_3 as parent -> lower level
                    glevel_4 = QTreeWidgetItem(
                        glevel_3, [name, uid]
                    )
                    self.GeologyTreeWidget.setItemWidget(
                        glevel_4, 2, property_combo
                    )
                    property_combo.currentIndexChanged.connect(
                        lambda: self.toggle_property()
                    )
                    glevel_4.setFlags(glevel_4.flags() | Qt.ItemIsUserCheckable)
                    if self.actors_df.loc[
                        self.actors_df["uid"] == uid, "show"
                    ].values[0]:
                        glevel_4.setCheckState(0, Qt.Checked)
                    elif not self.actors_df.loc[
                        self.actors_df["uid"] == uid, "show"
                    ].values[0]:
                        glevel_4.setCheckState(0, Qt.Unchecked)
    # Send messages. Note that with tristate several signals are emitted in a sequence, one for each
    # changed item, but upper levels do not broadcast uid's so they are filtered in the toggle method.
    self.GeologyTreeWidget.itemChanged.connect(self.toggle_geology_visibility )
    self.GeologyTreeWidget.expandAll()


def update_geology_tree_added(self, uid_list=None):
    """Update geology tree without creating a new model"""
    for uid in uid_list:
        if (
                self.GeologyTreeWidget.findItems(
                    self.parent.geol_coll.get_uid_type(uid),
                    Qt.MatchExactly,
                    0,
                )
                != []
        ):
            # Already exists a TreeItem (1 level) for the geological type
            counter_1 = 0
            for child_1 in range(
                    self.GeologyTreeWidget.findItems(
                        self.parent.geol_coll.get_uid_type(uid),
                        Qt.MatchExactly,
                        0,
                    )[0].childCount()
            ):
                # for cycle that loops n times as the number of subItems in the specific geological type branch
                if self.GeologyTreeWidget.findItems(
                        self.parent.geol_coll.get_uid_type(uid),
                        Qt.MatchExactly,
                        0,
                )[0].child(child_1).text(
                    0
                ) == self.parent.geol_coll.get_uid_feature(
                    uid
                ):
                    counter_1 += 1
            if counter_1 != 0:
                for child_1 in range(
                        self.GeologyTreeWidget.findItems(
                            self.parent.geol_coll.get_uid_type(uid),
                            Qt.MatchExactly,
                            0,
                        )[0].childCount()
                ):
                    if self.GeologyTreeWidget.findItems(
                            self.parent.geol_coll.get_uid_type(uid),
                            Qt.MatchExactly,
                            0,
                    )[0].child(child_1).text(
                        0
                    ) == self.parent.geol_coll.get_uid_feature(
                        uid
                    ):
                        # Already exists a TreeItem (2 level) for the geological feature
                        counter_2 = 0
                        for child_2 in range(
                                self.GeologyTreeWidget.itemBelow(
                                    self.GeologyTreeWidget.findItems(
                                        self.parent.geol_coll.get_uid_type(
                                            uid
                                        ),
                                        Qt.MatchExactly,
                                        0,
                                    )[0]
                                ).childCount()
                        ):
                            # for cycle that loops n times as the number of sub-subItems in the specific geological
                            # type and geological feature branch
                            if self.GeologyTreeWidget.itemBelow(
                                    self.GeologyTreeWidget.findItems(
                                        self.parent.geol_coll.get_uid_type(
                                            uid
                                        ),
                                        Qt.MatchExactly,
                                        0,
                                    )[0]
                            ).child(child_2).text(
                                0
                            ) == self.parent.geol_coll.get_uid_scenario(
                                uid
                            ):
                                counter_2 += 1
                        if counter_2 != 0:
                            for child_2 in range(
                                    self.GeologyTreeWidget.itemBelow(
                                        self.GeologyTreeWidget.findItems(
                                            self.parent.geol_coll.get_uid_type(
                                                uid
                                            ),
                                            Qt.MatchExactly,
                                            0,
                                        )[0]
                                    ).childCount()
                            ):
                                if self.GeologyTreeWidget.itemBelow(
                                        self.GeologyTreeWidget.findItems(
                                            self.parent.geol_coll.get_uid_type(
                                                uid
                                            ),
                                            Qt.MatchExactly,
                                            0,
                                        )[0]
                                ).child(child_2).text(
                                    0
                                ) == self.parent.geol_coll.get_uid_scenario(
                                    uid
                                ):
                                    # Same geological type, geological feature and scenario
                                    property_combo = QComboBox()
                                    property_combo.uid = uid
                                    property_combo.addItem("none")
                                    property_combo.addItem("X")
                                    property_combo.addItem("Y")
                                    property_combo.addItem("Z")
                                    for (
                                            prop
                                    ) in self.parent.geol_coll.get_uid_properties_names(
                                        uid
                                    ):
                                        property_combo.addItem(prop)
                                    name = self.parent.geol_coll.get_uid_name(uid)
                                    glevel_4 = QTreeWidgetItem(
                                        self.GeologyTreeWidget.findItems(
                                            self.parent.geol_coll.get_uid_type(
                                                uid
                                            ),
                                            Qt.MatchExactly,
                                            0,
                                        )[0]
                                        .child(child_1)
                                        .child(child_2),
                                        [name, uid],
                                    )
                                    self.GeologyTreeWidget.setItemWidget(
                                        glevel_4, 2, property_combo
                                    )
                                    property_combo.currentIndexChanged.connect(
                                        lambda: self.toggle_property()
                                    )
                                    glevel_4.setFlags(
                                        glevel_4.flags() | Qt.ItemIsUserCheckable
                                    )
                                    if self.actors_df.loc[
                                        self.actors_df["uid"] == uid, "show"
                                    ].values[0]:
                                        glevel_4.setCheckState(0, Qt.Checked)
                                    elif not self.actors_df.loc[
                                        self.actors_df["uid"] == uid, "show"
                                    ].values[0]:
                                        glevel_4.setCheckState(0, Qt.Unchecked)
                                    self.GeologyTreeWidget.insertTopLevelItem(
                                        0, glevel_4
                                    )
                                    break
                        else:
                            # Same geological type and geological feature, different scenario
                            glevel_3 = QTreeWidgetItem(
                                self.GeologyTreeWidget.findItems(
                                    self.parent.geol_coll.get_uid_type(
                                        uid
                                    ),
                                    Qt.MatchExactly,
                                    0,
                                )[0].child(child_1),
                                [self.parent.geol_coll.get_uid_scenario(uid)],
                            )
                            glevel_3.setFlags(
                                glevel_3.flags()
                                | Qt.ItemIsTristate
                                | Qt.ItemIsUserCheckable
                            )
                            self.GeologyTreeWidget.insertTopLevelItem(0, glevel_3)
                            property_combo = QComboBox()
                            property_combo.uid = uid
                            property_combo.addItem("none")
                            property_combo.addItem("X")
                            property_combo.addItem("Y")
                            property_combo.addItem("Z")
                            for (
                                    prop
                            ) in self.parent.geol_coll.get_uid_properties_names(
                                uid
                            ):
                                property_combo.addItem(prop)
                            name = self.parent.geol_coll.get_uid_name(uid)
                            glevel_4 = QTreeWidgetItem(glevel_3, [name, uid])
                            self.GeologyTreeWidget.setItemWidget(
                                glevel_4, 2, property_combo
                            )
                            property_combo.currentIndexChanged.connect(
                                lambda: self.toggle_property()
                            )
                            glevel_4.setFlags(
                                glevel_4.flags() | Qt.ItemIsUserCheckable
                            )
                            if self.actors_df.loc[
                                self.actors_df["uid"] == uid, "show"
                            ].values[0]:
                                glevel_4.setCheckState(0, Qt.Checked)
                            elif not self.actors_df.loc[
                                self.actors_df["uid"] == uid, "show"
                            ].values[0]:
                                glevel_4.setCheckState(0, Qt.Unchecked)
                            self.GeologyTreeWidget.insertTopLevelItem(0, glevel_4)
                            break
            else:
                # Same geological type, different geological feature and scenario
                glevel_2 = QTreeWidgetItem(
                    self.GeologyTreeWidget.findItems(
                        self.parent.geol_coll.get_uid_type(uid),
                        Qt.MatchExactly,
                        0,
                    )[0],
                    [self.parent.geol_coll.get_uid_feature(uid)],
                )
                glevel_2.setFlags(
                    glevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
                )
                self.GeologyTreeWidget.insertTopLevelItem(0, glevel_2)
                glevel_3 = QTreeWidgetItem(
                    glevel_2, [self.parent.geol_coll.get_uid_scenario(uid)]
                )
                glevel_3.setFlags(
                    glevel_3.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
                )
                self.GeologyTreeWidget.insertTopLevelItem(0, glevel_3)
                property_combo = QComboBox()
                property_combo.uid = uid
                property_combo.addItem("none")
                property_combo.addItem("X")
                property_combo.addItem("Y")
                property_combo.addItem("Z")
                for prop in self.parent.geol_coll.get_uid_properties_names(uid):
                    property_combo.addItem(prop)
                name = self.parent.geol_coll.get_uid_name(uid)
                glevel_4 = QTreeWidgetItem(glevel_3, [name, uid])
                self.GeologyTreeWidget.setItemWidget(glevel_4, 2, property_combo)
                property_combo.currentIndexChanged.connect(
                    lambda: self.toggle_property()
                )
                glevel_4.setFlags(glevel_4.flags() | Qt.ItemIsUserCheckable)
                if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[
                    0
                ]:
                    glevel_4.setCheckState(0, Qt.Checked)
                elif not self.actors_df.loc[
                    self.actors_df["uid"] == uid, "show"
                ].values[0]:
                    glevel_4.setCheckState(0, Qt.Unchecked)
                self.GeologyTreeWidget.insertTopLevelItem(0, glevel_4)
                break
        else:
            # Different geological type, geological feature and scenario
            glevel_1 = QTreeWidgetItem(
                self.GeologyTreeWidget,
                [self.parent.geol_coll.get_uid_type(uid)],
            )
            glevel_1.setFlags(
                glevel_1.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
            )
            self.GeologyTreeWidget.insertTopLevelItem(0, glevel_1)
            glevel_2 = QTreeWidgetItem(
                glevel_1, [self.parent.geol_coll.get_uid_feature(uid)]
            )
            glevel_2.setFlags(
                glevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
            )
            self.GeologyTreeWidget.insertTopLevelItem(0, glevel_2)
            glevel_3 = QTreeWidgetItem(
                glevel_2, [self.parent.geol_coll.get_uid_scenario(uid)]
            )
            glevel_3.setFlags(
                glevel_3.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
            )
            self.GeologyTreeWidget.insertTopLevelItem(0, glevel_3)
            property_combo = QComboBox()
            property_combo.uid = uid
            property_combo.addItem("none")
            property_combo.addItem("X")
            property_combo.addItem("Y")
            property_combo.addItem("Z")
            for prop in self.parent.geol_coll.get_uid_properties_names(uid):
                property_combo.addItem(prop)
            name = self.parent.geol_coll.get_uid_name(uid)
            glevel_4 = QTreeWidgetItem(glevel_3, [name, uid])
            self.GeologyTreeWidget.setItemWidget(glevel_4, 2, property_combo)
            property_combo.currentIndexChanged.connect(
                lambda: self.toggle_property()
            )
            glevel_4.setFlags(glevel_4.flags() | Qt.ItemIsUserCheckable)
            if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                glevel_4.setCheckState(0, Qt.Checked)
            elif not self.actors_df.loc[
                self.actors_df["uid"] == uid, "show"
            ].values[0]:
                glevel_4.setCheckState(0, Qt.Unchecked)
            self.GeologyTreeWidget.insertTopLevelItem(0, glevel_4)
            break
    self.GeologyTreeWidget.itemChanged.connect(self.toggle_geology_visibility )
    self.GeologyTreeWidget.expandAll()


def update_geology_tree_removed(self, removed_list=None):
    """When geological entity is removed, update Geology Tree without building a new model"""
    success = 0
    for uid in removed_list:
        for top_geo_type in range(self.GeologyTreeWidget.topLevelItemCount()):
            # Iterate through every Geological Role top level
            for child_geo_feat in range(
                    self.GeologyTreeWidget.topLevelItem(top_geo_type).childCount()
            ):
                # Iterate through every Geological Feature child
                for child_scenario in range(
                        self.GeologyTreeWidget.topLevelItem(top_geo_type)
                                .child(child_geo_feat)
                                .childCount()
                ):
                    # Iterate through every Scenario child
                    for child_entity in range(
                            self.GeologyTreeWidget.topLevelItem(top_geo_type)
                                    .child(child_geo_feat)
                                    .child(child_scenario)
                                    .childCount()
                    ):
                        # Iterate through every Entity child
                        if (
                                self.GeologyTreeWidget.topLevelItem(top_geo_type)
                                        .child(child_geo_feat)
                                        .child(child_scenario)
                                        .child(child_entity)
                                        .text(1)
                                == uid
                        ):
                            # Complete check: entity found has the uid of the entity we need to remove. Delete
                            # child, then ensure no Child or Top Level remain empty
                            success = 1
                            self.GeologyTreeWidget.topLevelItem(top_geo_type).child(
                                child_geo_feat
                            ).child(child_scenario).removeChild(
                                self.GeologyTreeWidget.topLevelItem(top_geo_type)
                                .child(child_geo_feat)
                                .child(child_scenario)
                                .child(child_entity)
                            )
                            if (
                                    self.GeologyTreeWidget.topLevelItem(top_geo_type)
                                            .child(child_geo_feat)
                                            .child(child_scenario)
                                            .childCount()
                                    == 0
                            ):
                                self.GeologyTreeWidget.topLevelItem(
                                    top_geo_type
                                ).child(child_geo_feat).removeChild(
                                    self.GeologyTreeWidget.topLevelItem(
                                        top_geo_type
                                    )
                                    .child(child_geo_feat)
                                    .child(child_scenario)
                                )
                                if (
                                        self.GeologyTreeWidget.topLevelItem(
                                            top_geo_type
                                        )
                                                .child(child_geo_feat)
                                                .childCount()
                                        == 0
                                ):
                                    self.GeologyTreeWidget.topLevelItem(
                                        top_geo_type
                                    ).removeChild(
                                        self.GeologyTreeWidget.topLevelItem(
                                            top_geo_type
                                        ).child(child_geo_feat)
                                    )
                                    if (
                                            self.GeologyTreeWidget.topLevelItem(
                                                top_geo_type
                                            ).childCount()
                                            == 0
                                    ):
                                        self.GeologyTreeWidget.takeTopLevelItem(
                                            top_geo_type
                                        )
                            break
                    if success == 1:
                        break
                if success == 1:
                    break
            if success == 1:
                break


def update_geology_checkboxes(self, uid=None, uid_checkState=None):
    """Update checkboxes in geology tree, called when state changed in topology tree."""
    item = self.GeologyTreeWidget.findItems(
        uid, Qt.MatchFixedString | Qt.MatchRecursive, 1
    )[0]
    if uid_checkState == Qt.Checked:
        item.setCheckState(0, Qt.Checked)
    elif uid_checkState == Qt.Unchecked:
        item.setCheckState(0, Qt.Unchecked)


def create_topology_tree(self):
    """Create topology tree with checkboxes and properties"""
    self.TopologyTreeWidget.clear()
    self.TopologyTreeWidget.setColumnCount(3)
    self.TopologyTreeWidget.setHeaderLabels(
        ["Role > Scenario > Name", "uid", "property"]
    )
    # hide the uid column
    self.TopologyTreeWidget.hideColumn(1)
    self.TopologyTreeWidget.setItemsExpandable(True)
    topo_types = pd_unique(self.parent.geol_coll.df.query(self.view_filter)["topology"])

    for topo_type in topo_types:
        # self.GeologyTreeWidget as parent -> top level
        tlevel_1 = QTreeWidgetItem(
            self.TopologyTreeWidget, [topo_type]
        )
        tlevel_1.setFlags(
            tlevel_1.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
        )
        for scenario in pd_unique(
                self.parent.geol_coll.df.query(self.view_filter).loc[
                    self.parent.geol_coll.df.query(self.view_filter)["topology"] == topo_type,
                    "scenario",
                ]
        ):
            # tlevel_1 as parent -> middle level
            tlevel_2 = QTreeWidgetItem(
                tlevel_1, [scenario]
            )
            tlevel_2.setFlags(
                tlevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
            )
            uids = self.parent.geol_coll.df.query(self.view_filter).loc[
                (self.parent.geol_coll.df.query(self.view_filter)["topology"] == topo_type)
                & (self.parent.geol_coll.df.query(self.view_filter)["scenario"] == scenario),
                "uid",
            ].to_list()
            for uid in uids:
                property_combo = QComboBox()
                property_combo.uid = uid
                property_combo.addItem("none")
                property_combo.addItem("X")
                property_combo.addItem("Y")
                property_combo.addItem("Z")
                for prop in self.parent.geol_coll.get_uid_properties_names(uid):
                    property_combo.addItem(prop)
                name = self.parent.geol_coll.df.loc[
                    self.parent.geol_coll.df["uid"] == uid, "name"
                ].values[0]
                # tlevel_2 as parent -> lower level
                tlevel_3 = QTreeWidgetItem(
                    tlevel_2, [name, uid]
                )
                self.TopologyTreeWidget.setItemWidget(tlevel_3, 2, property_combo)
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
    # Send messages. Note that with tristate several signals are emitted in a sequence, one for each
    # changed item, but upper levels do not broadcast uid's so they are filtered in the toggle method
    self.TopologyTreeWidget.itemChanged.connect(
        self.toggle_geology_visibility 
    )
    self.TopologyTreeWidget.expandAll()


def update_topology_tree_added(self, uid_list=None):
    """Update topology tree without creating a new model"""
    for uid in uid_list:
        if (
                self.TopologyTreeWidget.findItems(
                    self.parent.geol_coll.get_uid_topology(uid),
                    Qt.MatchExactly,
                    0,
                )
                != []
        ):
            # Already exists a TreeItem (1 level) for the topological type
            counter_1 = 0
            for child_1 in range(
                    self.TopologyTreeWidget.findItems(
                        self.parent.geol_coll.get_uid_topology(uid),
                        Qt.MatchExactly,
                        0,
                    )[0].childCount()
            ):
                # for cycle that loops n times as the number of subItems in the specific topological type branch
                if self.TopologyTreeWidget.findItems(
                        self.parent.geol_coll.get_uid_topology(uid),
                        Qt.MatchExactly,
                        0,
                )[0].child(child_1).text(
                    0
                ) == self.parent.geol_coll.get_uid_scenario(
                    uid
                ):
                    counter_1 += 1
            if counter_1 != 0:
                for child_1 in range(
                        self.TopologyTreeWidget.findItems(
                            self.parent.geol_coll.get_uid_topology(uid),
                            Qt.MatchExactly,
                            0,
                        )[0].childCount()
                ):
                    if self.TopologyTreeWidget.findItems(
                            self.parent.geol_coll.get_uid_topology(uid),
                            Qt.MatchExactly,
                            0,
                    )[0].child(child_1).text(
                        0
                    ) == self.parent.geol_coll.get_uid_scenario(
                        uid
                    ):
                        # Same topological type and scenario
                        property_combo = QComboBox()
                        property_combo.uid = uid
                        property_combo.addItem("none")
                        property_combo.addItem("X")
                        property_combo.addItem("Y")
                        property_combo.addItem("Z")
                        for prop in self.parent.geol_coll.get_uid_properties_names(
                                uid
                        ):
                            property_combo.addItem(prop)
                        name = self.parent.geol_coll.get_uid_name(uid)
                        tlevel_3 = QTreeWidgetItem(
                            self.TopologyTreeWidget.findItems(
                                self.parent.geol_coll.get_uid_topology(uid),
                                Qt.MatchExactly,
                                0,
                            )[0].child(child_1),
                            [name, uid],
                        )
                        self.TopologyTreeWidget.setItemWidget(
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
                # Same topological type, different scenario
                tlevel_2 = QTreeWidgetItem(
                    self.TopologyTreeWidget.findItems(
                        self.parent.geol_coll.get_uid_topology(uid),
                        Qt.MatchExactly,
                        0,
                    )[0],
                    [self.parent.geol_coll.get_uid_scenario(uid)],
                )
                tlevel_2.setFlags(
                    tlevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
                )
                self.TopologyTreeWidget.insertTopLevelItem(0, tlevel_2)
                property_combo = QComboBox()
                property_combo.uid = uid
                property_combo.addItem("none")
                property_combo.addItem("X")
                property_combo.addItem("Y")
                property_combo.addItem("Z")
                for prop in self.parent.geol_coll.get_uid_properties_names(uid):
                    property_combo.addItem(prop)
                name = self.parent.geol_coll.get_uid_name(uid)
                tlevel_3 = QTreeWidgetItem(tlevel_2, [name, uid])
                self.TopologyTreeWidget.setItemWidget(tlevel_3, 2, property_combo)
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
                self.TopologyTreeWidget.insertTopLevelItem(0, tlevel_3)
                break
        else:
            # Different topological type and scenario
            tlevel_1 = QTreeWidgetItem(
                self.TopologyTreeWidget,
                [self.parent.geol_coll.get_uid_topology(uid)],
            )
            tlevel_1.setFlags(
                tlevel_1.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
            )
            self.TopologyTreeWidget.insertTopLevelItem(0, tlevel_1)
            tlevel_2 = QTreeWidgetItem(
                tlevel_1, [self.parent.geol_coll.get_uid_scenario(uid)]
            )
            tlevel_2.setFlags(
                tlevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
            )
            self.TopologyTreeWidget.insertTopLevelItem(0, tlevel_2)
            property_combo = QComboBox()
            property_combo.uid = uid
            property_combo.addItem("none")
            property_combo.addItem("X")
            property_combo.addItem("Y")
            property_combo.addItem("Z")
            for prop in self.parent.geol_coll.get_uid_properties_names(uid):
                property_combo.addItem(prop)
            name = self.parent.geol_coll.get_uid_name(uid)
            tlevel_3 = QTreeWidgetItem(tlevel_2, [name, uid])
            self.TopologyTreeWidget.setItemWidget(tlevel_3, 2, property_combo)
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
            self.TopologyTreeWidget.insertTopLevelItem(0, tlevel_3)
            break
    self.TopologyTreeWidget.itemChanged.connect(
        self.toggle_geology_visibility 
    )
    self.TopologyTreeWidget.expandAll()


def update_topology_tree_removed(self, removed_list=None):
    """When geological entity is removed, update Topology Tree without building a new model"""
    success = 0
    for uid in removed_list:
        for top_topo_type in range(self.TopologyTreeWidget.topLevelItemCount()):
            # Iterate through every Topological Role top level
            for child_scenario in range(
                    self.TopologyTreeWidget.topLevelItem(top_topo_type).childCount()
            ):
                # Iterate through every Scenario child
                for child_entity in range(
                        self.TopologyTreeWidget.topLevelItem(top_topo_type)
                                .child(child_scenario)
                                .childCount()
                ):
                    # Iterate through every Entity child
                    if (
                            self.TopologyTreeWidget.topLevelItem(top_topo_type)
                                    .child(child_scenario)
                                    .child(child_entity)
                                    .text(1)
                            == uid
                    ):
                        # Complete check: entity found has the uid of the entity we need to remove. Delete child,
                        # then ensure no Child or Top Level remain empty
                        success = 1
                        self.TopologyTreeWidget.topLevelItem(top_topo_type).child(
                            child_scenario
                        ).removeChild(
                            self.TopologyTreeWidget.topLevelItem(top_topo_type)
                            .child(child_scenario)
                            .child(child_entity)
                        )
                        if (
                                self.TopologyTreeWidget.topLevelItem(top_topo_type)
                                        .child(child_scenario)
                                        .childCount()
                                == 0
                        ):
                            self.TopologyTreeWidget.topLevelItem(
                                top_topo_type
                            ).removeChild(
                                self.TopologyTreeWidget.topLevelItem(
                                    top_topo_type
                                ).child(child_scenario)
                            )
                            if (
                                    self.TopologyTreeWidget.topLevelItem(
                                        top_topo_type
                                    ).childCount()
                                    == 0
                            ):
                                self.TopologyTreeWidget.takeTopLevelItem(
                                    top_topo_type
                                )
                        break
                if success == 1:
                    break
            if success == 1:
                break


def update_topology_checkboxes(self, uid=None, uid_checkState=None):
    """Update checkboxes in topology tree, called when state changed in geology tree."""
    item = self.TopologyTreeWidget.findItems(
        uid, Qt.MatchFixedString | Qt.MatchRecursive, 1
    )[0]
    if uid_checkState == Qt.Checked:
        item.setCheckState(0, Qt.Checked)
    elif uid_checkState == Qt.Unchecked:
        item.setCheckState(0, Qt.Unchecked)


def toggle_geology_visibility (self, item):
    """Called by self.GeologyTreeWidget.itemChanged.connect(self.toggle_geology_visibility ) and
    self.TopologyTreeWidget.itemChanged.connect(self.toggle_geology_visibility )"""
    # name = item.text(0)  # not used

    uid = item.text(1)
    uid_checkState = item.checkState(0)
    # needed to skip messages from upper levels of tree that do not broadcast uid's
    if (
            uid
    ):
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
        # Before updating checkboxes, disconnect signals to geology and topology tree, if they are set,
        # to avoid a nasty loop that disrupts the trees, then reconnect them (it is also possible that
        # they are automatically reconnected whe the trees are rebuilt
        self.GeologyTreeWidget.itemChanged.disconnect()
        self.TopologyTreeWidget.itemChanged.disconnect()
        update_geology_checkboxes(self, uid=uid, uid_checkState=uid_checkState)
        update_topology_checkboxes(self, uid=uid, uid_checkState=uid_checkState)
        self.GeologyTreeWidget.itemChanged.connect(
            self.toggle_geology_visibility 
        )
        self.TopologyTreeWidget.itemChanged.connect(
            self.toggle_geology_visibility 
        )
