"""view_stereoplot.py
PZero© Andrea Bistacchi"""

# PySide6 imports____
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QSizePolicy, QTreeWidgetItem, QComboBox
from matplotlib.backends.backend_template import FigureCanvas

# numpy import____
from numpy import all as np_all
from numpy import ndarray as np_ndarray

# Pandas imports____
from pandas import DataFrame as pd_DataFrame
from pandas import unique as pd_unique

# mplstereonet import____
import mplstereonet
from matplotlib import style as mplstyle

# from matplotlib.backend_bases import FigureCanvasBase

# the following is customized in subclass NavigationToolbar a few lines below
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT

# Background color for matplotlib plots, it could be made interactive in the future.
# 'fast' is supposed to make plotting large objects faster.
mplstyle.use(["dark_background", "fast"])


class NavigationToolbar(NavigationToolbar2QT):
    """Can customize NavigationToolbar2QT used in matplotlib to display only the buttons we need.
    Note that toolitems is a class variable defined before __init__."""

    toolitems = [
        t
        for t in NavigationToolbar2QT.toolitems
        if t[0] in ("Home", "Pan", "Zoom", "Save")
    ]

    def __init__(self, parent=None, *args, **kwargs):
        super(NavigationToolbar, self).__init__(parent, *args, **kwargs)


# PZero imports____
from .abstract_mpl_view import MPLView

class ViewStereoplot(MPLView):
    def __init__(self, *args, **kwargs):
        super(ViewStereoplot, self).__init__(*args, **kwargs)
        self.setWindowTitle("Stereoplot View")
        self.tog_contours = -1
        # mplstyle.context('classic')

    def initialize_menu_tools(self):
        """This is the method of the ViewStereoplot() class, used to add menu tools in addition to those inherited from
        superclasses, that are appended here using super().initialize_menu_tools()."""
        # append code from MPLView()
        super().initialize_menu_tools()

        # then add new code specific to MPLView()
        self.actionContours = QAction("View contours", self)
        self.actionContours.triggered.connect(
            lambda: self.toggle_contours(filled=False)
        )
        self.menuView.addAction(self.actionContours)

        self.actionSetPolar = QAction("Set polar grid", self)
        self.actionSetPolar.triggered.connect(lambda: self.change_grid(kind="polar"))
        self.menuView.addAction(self.actionSetPolar)

        self.actionSetEq = QAction("Set equatorial grid", self)
        self.actionSetEq.triggered.connect(lambda: self.change_grid(kind="equatorial"))
        self.menuView.addAction(self.actionSetEq)

        self.actionSetEquiare = QAction("Equiareal (Schmidt)", self)
        self.actionSetEquiare.triggered.connect(
            lambda: self.change_proj(projection="equal_area_stereonet")
        )
        self.menuView.addAction(self.actionSetEquiare)

        self.actionSetEquiang = QAction("Equiangolar (Wulff)", self)
        self.actionSetEquiang.triggered.connect(
            lambda: self.change_proj(projection="equal_angle_stereonet")
        )
        self.menuView.addAction(self.actionSetEquiang)

    def initialize_interactor(self, kind=None, projection="equal_area_stereonet"):
        self.grid_kind = kind
        self.proj_type = projection

        with mplstyle.context("default"):
            # Create Matplotlib canvas, figure and navi_toolbar. this implicitly
            # creates also the canvas to contain the figure.
            self.figure, self.ax = mplstereonet.subplots(projection=self.proj_type)

        self.canvas = FigureCanvas(
            self.figure
        )  # get a reference to the canvas that contains the figure
        # print("dir(self.canvas):\n", dir(self.canvas))
        # https://doc.qt.io/qt-5/qsizepolicy.html
        self.navi_toolbar = NavigationToolbar(
            self.figure.canvas, self
        )  # create a navi_toolbar with the matplotlib.backends.backend_qt5agg method NavigationToolbar

        # Create Qt layout andNone add Matplotlib canvas, figure and navi_toolbar"""
        # canvas_widget = self.figure.canvas
        # canvas_widget.setAutoFillBackground(True)
        self.ViewFrameLayout.addWidget(
            self.canvas
        )  # add Matplotlib canvas (created above) as a widget to the Qt layout
        # print(plot_widget)
        self.ViewFrameLayout.addWidget(
            self.navi_toolbar
        )  # add navigation navi_toolbar (created above) to the layout
        self.ax.grid(kind=self.grid_kind, color="k")

    def create_geology_tree(self):
        """Create geology tree with checkboxes and properties"""
        self.GeologyTreeWidget.clear()
        self.GeologyTreeWidget.setColumnCount(3)
        self.GeologyTreeWidget.setHeaderLabels(
            ["Role > Feature > Scenario > Name", "uid", "property"]
        )
        self.GeologyTreeWidget.hideColumn(1)  # hide the uid column
        self.GeologyTreeWidget.setItemsExpandable(True)

        filtered_geo = self.parent.geol_coll.df.loc[
            (self.parent.geol_coll.df["topology"] == "VertexSet")
            | (self.parent.geol_coll.df["topology"] == "XsVertexSet"),
            "role",
        ]
        roles = pd_unique(filtered_geo)
        print("roles: ", roles)

        for role in roles:
            glevel_1 = QTreeWidgetItem(
                self.GeologyTreeWidget, [role]
            )  # self.GeologyTreeWidget as parent -> top level
            glevel_1.setFlags(
                glevel_1.flags() | Qt.ItemIsUserTristate | Qt.ItemIsUserCheckable
            )
            filtered_features = self.parent.geol_coll.df.loc[
                (self.parent.geol_coll.df["role"] == role)
                & (
                    (self.parent.geol_coll.df["topology"] == "VertexSet")
                    | (self.parent.geol_coll.df["topology"] == "XsVertexSet")
                ),
                "feature",
            ]
            features = pd_unique(filtered_features)
            print("features: ", features)
            for feature in features:
                glevel_2 = QTreeWidgetItem(
                    glevel_1, [feature]
                )  # glevel_1 as parent -> 1st middle level
                glevel_2.setFlags(
                    glevel_2.flags() | Qt.ItemIsUserTristate | Qt.ItemIsUserCheckable
                )
                geo_scenario = pd_unique(
                    self.parent.geol_coll.df.loc[
                        (self.parent.geol_coll.df["role"] == role)
                        & (self.parent.geol_coll.df["feature"] == feature),
                        "scenario",
                    ]
                )
                for scenario in geo_scenario:
                    glevel_3 = QTreeWidgetItem(
                        glevel_2, [scenario]
                    )  # glevel_2 as parent -> 2nd middle level
                    glevel_3.setFlags(
                        glevel_3.flags()
                        | Qt.ItemIsUserTristate
                        | Qt.ItemIsUserCheckable
                    )
                    uids = self.parent.geol_coll.df.loc[
                        (self.parent.geol_coll.df["role"] == role)
                        & (self.parent.geol_coll.df["feature"] == feature)
                        & (self.parent.geol_coll.df["scenario"] == scenario)
                        & (
                            (self.parent.geol_coll.df["topology"] == "VertexSet")
                            | (self.parent.geol_coll.df["topology"] == "XsVertexSet")
                        ),
                        "uid",
                    ].to_list()
                    for uid in uids:
                        property_combo = QComboBox()
                        property_combo.uid = uid
                        property_combo.addItem("Poles")
                        # property_combo.addItem("Planes")
                        name = self.parent.geol_coll.df.loc[
                            (self.parent.geol_coll.df["uid"] == uid), "name"
                        ].values[0]
                        glevel_4 = QTreeWidgetItem(
                            glevel_3, [name, uid]
                        )  # glevel_3 as parent -> lower level
                        self.GeologyTreeWidget.setItemWidget(
                            glevel_4, 2, property_combo
                        )
                        property_combo.currentIndexChanged.connect(
                            lambda *, sender=property_combo: self.toggle_property(
                                sender=sender
                            )
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
        self.GeologyTreeWidget.itemChanged.connect(self.toggle_geology_visibility)
        self.GeologyTreeWidget.expandAll()

    def create_topology_tree(self):
        """Create topology tree with checkboxes and properties"""
        self.GeologyTopologyTreeWidget.clear()
        self.GeologyTopologyTreeWidget.setColumnCount(3)
        self.GeologyTopologyTreeWidget.setHeaderLabels(
            ["Role > Scenario > Name", "uid", "property"]
        )
        self.GeologyTopologyTreeWidget.hideColumn(1)  # hide the uid column
        self.GeologyTopologyTreeWidget.setItemsExpandable(True)

        filtered_topo = self.parent.geol_coll.df.loc[
            (self.parent.geol_coll.df["topology"] == "VertexSet")
            | (self.parent.geol_coll.df["topology"] == "XsVertexSet"),
            "topology",
        ]
        topo_types = pd_unique(filtered_topo)
        for topo_type in topo_types:
            tlevel_1 = QTreeWidgetItem(
                self.GeologyTopologyTreeWidget, [topo_type]
            )  # self.GeologyTreeWidget as parent -> top level
            tlevel_1.setFlags(
                tlevel_1.flags() | Qt.ItemIsUserTristate | Qt.ItemIsUserCheckable
            )
            for scenario in pd_unique(
                self.parent.geol_coll.df.loc[
                    self.parent.geol_coll.df["topology"] == topo_type, "scenario"
                ]
            ):
                tlevel_2 = QTreeWidgetItem(
                    tlevel_1, [scenario]
                )  # tlevel_1 as parent -> middle level
                tlevel_2.setFlags(
                    tlevel_2.flags() | Qt.ItemIsUserTristate | Qt.ItemIsUserCheckable
                )

                uids = self.parent.geol_coll.df.loc[
                    (self.parent.geol_coll.df["topology"] == topo_type)
                    & (self.parent.geol_coll.df["scenario"] == scenario)
                    & (
                        (self.parent.geol_coll.df["topology"] == "VertexSet")
                        | (self.parent.geol_coll.df["topology"] == "XsVertexSet")
                    ),
                    "uid",
                ].to_list()
                for uid in uids:
                    property_combo = QComboBox()
                    property_combo.uid = uid
                    property_combo.addItem("Poles")
                    # property_combo.addItem("Planes")
                    name = self.parent.geol_coll.df.loc[
                        self.parent.geol_coll.df["uid"] == uid, "name"
                    ].values[0]
                    tlevel_3 = QTreeWidgetItem(
                        tlevel_2, [name, uid]
                    )  # tlevel_2 as parent -> lower level
                    self.GeologyTopologyTreeWidget.setItemWidget(
                        tlevel_3, 2, property_combo
                    )
                    property_combo.currentIndexChanged.connect(
                        lambda *, sender=property_combo: self.toggle_property(
                            sender=sender
                        )
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
        # changed item, but upper levels do not broadcast uid's so they are filtered in the toggle method.
        self.GeologyTopologyTreeWidget.itemChanged.connect(
            self.toggle_geology_visibility
        )
        self.GeologyTopologyTreeWidget.expandAll()

    def update_geology_tree_added(self, new_list=None):
        """Update geology tree without creating a new model"""
        uid_list = list(new_list["uid"])
        for uid in uid_list:
            if (
                self.GeologyTreeWidget.findItems(
                    self.parent.geol_coll.get_uid_role(uid),
                    Qt.MatchExactly,
                    0,
                )
                != []
            ):
                # Already exists a TreeItem (1 level) for the geological type
                counter_1 = 0
                for child_1 in range(
                    self.GeologyTreeWidget.findItems(
                        self.parent.geol_coll.get_uid_role(uid),
                        Qt.MatchExactly,
                        0,
                    )[0].childCount()
                ):
                    # for cycle that loops n times as the number of subItems in the specific geological type branch
                    if self.GeologyTreeWidget.findItems(
                        self.parent.geol_coll.get_uid_role(uid),
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
                            self.parent.geol_coll.get_uid_role(uid),
                            Qt.MatchExactly,
                            0,
                        )[0].childCount()
                    ):
                        if self.GeologyTreeWidget.findItems(
                            self.parent.geol_coll.get_uid_role(uid),
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
                                        self.parent.geol_coll.get_uid_role(uid),
                                        Qt.MatchExactly,
                                        0,
                                    )[0]
                                ).childCount()
                            ):
                                # For cycle that loops n times as the number of sub-subItems in the
                                # specific geological type and geological feature branch.
                                if self.GeologyTreeWidget.itemBelow(
                                    self.GeologyTreeWidget.findItems(
                                        self.parent.geol_coll.get_uid_role(uid),
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
                                            self.parent.geol_coll.get_uid_role(uid),
                                            Qt.MatchExactly,
                                            0,
                                        )[0]
                                    ).childCount()
                                ):
                                    if self.GeologyTreeWidget.itemBelow(
                                        self.GeologyTreeWidget.findItems(
                                            self.parent.geol_coll.get_uid_role(uid),
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
                                        # property_combo.addItem("Planes")
                                        property_combo.addItem("Poles")
                                        for (
                                            prop
                                        ) in self.parent.geol_coll.get_uid_properties_names(
                                            uid
                                        ):
                                            property_combo.addItem(prop)
                                        name = self.parent.geol_coll.get_uid_name(uid)
                                        glevel_4 = QTreeWidgetItem(
                                            self.GeologyTreeWidget.findItems(
                                                self.parent.geol_coll.get_uid_role(uid),
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
                                            lambda *, sender=property_combo: self.toggle_property(
                                                sender=sender
                                            )
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
                                        self.parent.geol_coll.get_uid_role(uid),
                                        Qt.MatchExactly,
                                        0,
                                    )[0].child(child_1),
                                    [self.parent.geol_coll.get_uid_scenario(uid)],
                                )
                                glevel_3.setFlags(
                                    glevel_3.flags()
                                    | Qt.ItemIsUserTristate
                                    | Qt.ItemIsUserCheckable
                                )
                                self.GeologyTreeWidget.insertTopLevelItem(0, glevel_3)
                                property_combo = QComboBox()
                                property_combo.uid = uid
                                # property_combo.addItem("Planes")
                                property_combo.addItem("Poles")
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
                                    lambda *, sender=property_combo: self.toggle_property(
                                        sender=sender
                                    )
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
                            self.parent.geol_coll.get_uid_role(uid),
                            Qt.MatchExactly,
                            0,
                        )[0],
                        [self.parent.geol_coll.get_uid_feature(uid)],
                    )
                    glevel_2.setFlags(
                        glevel_2.flags()
                        | Qt.ItemIsUserTristate
                        | Qt.ItemIsUserCheckable
                    )
                    self.GeologyTreeWidget.insertTopLevelItem(0, glevel_2)
                    glevel_3 = QTreeWidgetItem(
                        glevel_2, [self.parent.geol_coll.get_uid_scenario(uid)]
                    )
                    glevel_3.setFlags(
                        glevel_3.flags()
                        | Qt.ItemIsUserTristate
                        | Qt.ItemIsUserCheckable
                    )
                    self.GeologyTreeWidget.insertTopLevelItem(0, glevel_3)
                    property_combo = QComboBox()
                    property_combo.uid = uid
                    # property_combo.addItem("Planes")
                    property_combo.addItem("Poles")
                    for prop in self.parent.geol_coll.get_uid_properties_names(uid):
                        property_combo.addItem(prop)
                    name = self.parent.geol_coll.get_uid_name(uid)
                    glevel_4 = QTreeWidgetItem(glevel_3, [name, uid])
                    self.GeologyTreeWidget.setItemWidget(glevel_4, 2, property_combo)
                    property_combo.currentIndexChanged.connect(
                        lambda *, sender=property_combo: self.toggle_property(
                            sender=sender
                        )
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
                    [self.parent.geol_coll.get_uid_role(uid)],
                )
                glevel_1.setFlags(
                    glevel_1.flags() | Qt.ItemIsUserTristate | Qt.ItemIsUserCheckable
                )
                self.GeologyTreeWidget.insertTopLevelItem(0, glevel_1)
                glevel_2 = QTreeWidgetItem(
                    glevel_1, [self.parent.geol_coll.get_uid_feature(uid)]
                )
                glevel_2.setFlags(
                    glevel_2.flags() | Qt.ItemIsUserTristate | Qt.ItemIsUserCheckable
                )
                self.GeologyTreeWidget.insertTopLevelItem(0, glevel_2)
                glevel_3 = QTreeWidgetItem(
                    glevel_2, [self.parent.geol_coll.get_uid_scenario(uid)]
                )
                glevel_3.setFlags(
                    glevel_3.flags() | Qt.ItemIsUserTristate | Qt.ItemIsUserCheckable
                )
                self.GeologyTreeWidget.insertTopLevelItem(0, glevel_3)
                property_combo = QComboBox()
                property_combo.uid = uid
                # property_combo.addItem("Planes")
                property_combo.addItem("Poles")
                for prop in self.parent.geol_coll.get_uid_properties_names(uid):
                    property_combo.addItem(prop)
                name = self.parent.geol_coll.get_uid_name(uid)
                glevel_4 = QTreeWidgetItem(glevel_3, [name, uid])
                self.GeologyTreeWidget.setItemWidget(glevel_4, 2, property_combo)
                property_combo.currentIndexChanged.connect(
                    lambda *, sender=property_combo: self.toggle_property(sender=sender)
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
        self.GeologyTreeWidget.itemChanged.connect(self.toggle_geology_visibility)
        self.GeologyTreeWidget.expandAll()

    def update_topology_tree_added(self, new_list=None):
        """Update topology tree without creating a new model"""
        uid_list = list(new_list["uid"])
        for uid in uid_list:
            if (
                self.GeologyTopologyTreeWidget.findItems(
                    self.parent.geol_coll.get_uid_topology(uid),
                    Qt.MatchExactly,
                    0,
                )
                != []
            ):
                # Already exists a TreeItem (1 level) for the topological type
                counter_1 = 0
                for child_1 in range(
                    self.GeologyTopologyTreeWidget.findItems(
                        self.parent.geol_coll.get_uid_topology(uid),
                        Qt.MatchExactly,
                        0,
                    )[0].childCount()
                ):
                    # for cycle that loops n times as the number of subItems in the specific topological type branch
                    if self.GeologyTopologyTreeWidget.findItems(
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
                        self.GeologyTopologyTreeWidget.findItems(
                            self.parent.geol_coll.get_uid_topology(uid),
                            Qt.MatchExactly,
                            0,
                        )[0].childCount()
                    ):
                        if self.GeologyTopologyTreeWidget.findItems(
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
                            # property_combo.addItem("Planes")
                            property_combo.addItem("Poles")
                            for prop in self.parent.geol_coll.get_uid_properties_names(
                                uid
                            ):
                                property_combo.addItem(prop)
                            name = self.parent.geol_coll.get_uid_name(uid)
                            tlevel_3 = QTreeWidgetItem(
                                self.GeologyTopologyTreeWidget.findItems(
                                    self.parent.geol_coll.get_uid_topology(uid),
                                    Qt.MatchExactly,
                                    0,
                                )[0].child(child_1),
                                [name, uid],
                            )
                            self.GeologyTopologyTreeWidget.setItemWidget(
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
                            self.GeologyTopologyTreeWidget.insertTopLevelItem(
                                0, tlevel_3
                            )
                            break
                else:
                    # Same topological type, different scenario
                    tlevel_2 = QTreeWidgetItem(
                        self.GeologyTopologyTreeWidget.findItems(
                            self.parent.geol_coll.get_uid_topology(uid),
                            Qt.MatchExactly,
                            0,
                        )[0],
                        [self.parent.geol_coll.get_uid_scenario(uid)],
                    )
                    tlevel_2.setFlags(
                        tlevel_2.flags()
                        | Qt.ItemIsUserTristate
                        | Qt.ItemIsUserCheckable
                    )
                    self.GeologyTopologyTreeWidget.insertTopLevelItem(0, tlevel_2)
                    property_combo = QComboBox()
                    property_combo.uid = uid
                    # property_combo.addItem("Planes")
                    property_combo.addItem("Poles")
                    for prop in self.parent.geol_coll.get_uid_properties_names(uid):
                        property_combo.addItem(prop)
                    name = self.parent.geol_coll.get_uid_name(uid)
                    tlevel_3 = QTreeWidgetItem(tlevel_2, [name, uid])
                    self.GeologyTopologyTreeWidget.setItemWidget(
                        tlevel_3, 2, property_combo
                    )
                    property_combo.currentIndexChanged.connect(
                        lambda *, sender=property_combo: self.toggle_property(
                            sender=sender
                        )
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
                    self.GeologyTopologyTreeWidget.insertTopLevelItem(0, tlevel_3)
                    break
            else:
                # Different topological type and scenario
                tlevel_1 = QTreeWidgetItem(
                    self.GeologyTopologyTreeWidget,
                    [self.parent.geol_coll.get_uid_topology(uid)],
                )
                tlevel_1.setFlags(
                    tlevel_1.flags() | Qt.ItemIsUserTristate | Qt.ItemIsUserCheckable
                )
                self.GeologyTopologyTreeWidget.insertTopLevelItem(0, tlevel_1)
                tlevel_2 = QTreeWidgetItem(
                    tlevel_1, [self.parent.geol_coll.get_uid_scenario(uid)]
                )
                tlevel_2.setFlags(
                    tlevel_2.flags() | Qt.ItemIsUserTristate | Qt.ItemIsUserCheckable
                )
                self.GeologyTopologyTreeWidget.insertTopLevelItem(0, tlevel_2)
                property_combo = QComboBox()
                property_combo.uid = uid
                # property_combo.addItem("Planes")
                property_combo.addItem("Poles")
                for prop in self.parent.geol_coll.get_uid_properties_names(uid):
                    property_combo.addItem(prop)
                name = self.parent.geol_coll.get_uid_name(uid)
                tlevel_3 = QTreeWidgetItem(tlevel_2, [name, uid])
                self.GeologyTopologyTreeWidget.setItemWidget(
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
                self.GeologyTopologyTreeWidget.insertTopLevelItem(0, tlevel_3)
                break
        self.GeologyTopologyTreeWidget.itemChanged.connect(
            self.toggle_geology_visibility
        )
        self.GeologyTopologyTreeWidget.expandAll()

    def set_actor_visible(self, uid=None, visible=None):
        # print(self.actors_df)
        """Set actor uid visible or invisible (visible = True or False)"""
        if isinstance(
            self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[0], Line2D
        ):
            "Case for Line2D"
            self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[
                0
            ].set_visible(visible)
            self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[
                0
            ].figure.canvas.draw()
        elif isinstance(
            self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[0],
            PathCollection,
        ):
            "Case for PathCollection -> ax.scatter"
            pass
        elif isinstance(
            self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[0],
            TriContourSet,
        ):
            "Case for TriContourSet -> ax.tricontourf"
            pass
        elif isinstance(
            self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[0],
            AxesImage,
        ):
            "Case for AxesImage (i.e. images)"
            # Hide other images if (1) they are shown and (2) you are showing another one.
            for hide_uid in self.actors_df.loc[
                (self.actors_df["collection"] == "image_coll")
                & (self.actors_df["show"])
                & (self.actors_df["uid"] != uid),
                "uid",
            ].to_list():
                self.actors_df.loc[self.actors_df["uid"] == hide_uid, "show"] = False
                self.actors_df.loc[self.actors_df["uid"] == hide_uid, "actor"].values[
                    0
                ].set_visible(False)
                row = self.ImagesTableWidget.findItems(hide_uid, Qt.MatchExactly)[
                    0
                ].row()
                self.ImagesTableWidget.item(row, 0).setCheckState(Qt.Unchecked)
            # Then show this one.
            self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[
                0
            ].set_visible(visible)
            self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[
                0
            ].figure.canvas.draw()
        else:
            "Do-nothing option to avoid errors, but it does not set/unset visibility."
            pass

    def remove_actor_in_view(self, uid=None, redraw=False):
        """ "Remove actor from plotter"""
        # Can remove a single entity or a list of entities as actors - here we remove a single entity"

        if not self.actors_df.loc[self.actors_df["uid"] == uid].empty:
            if self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[0]:
                # print(self.actors_df.loc[self.actors_df['uid'] == uid, 'actor'].values)
                # print(self.actors_df.loc[self.actors_df['uid'] == uid, 'actor'].values[0])
                self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[
                    0
                ].remove()
                self.actors_df.drop(
                    self.actors_df[self.actors_df["uid"] == uid].index, inplace=True
                )
            if redraw:
                # IN THE FUTURE check if there is a way to redraw just the actor that has just been removed.
                self.figure.canvas.draw()
                print("redraw all - a more efficient alternative should be found")

    def show_actor_with_property(
        self,
        uid=None,
        collection=None,
        show_property="Poles",
        visible=None,
        filled=None,
    ):
        if show_property is None:
            show_property = "Poles"
        # Show actor with scalar property (default None)
        # https://github.com/pyvista/pyvista/blob/140b15be1d4021b81ded46b1c212c70e86a98ee7/pyvista/plotting/plotting.py#L1045
        # First get the vtk object from its collection.
        show_property_title = show_property
        this_coll = eval("self.parent." + collection)
        if collection == "geol_coll":
            color_R = this_coll.get_uid_legend(uid=uid)["color_R"]
            color_G = this_coll.get_uid_legend(uid=uid)["color_G"]
            color_B = this_coll.get_uid_legend(uid=uid)["color_B"]
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            line_thick = this_coll.get_uid_legend(uid=uid)["line_thick"]
            plot_entity = this_coll.get_uid_vtk_obj(uid)
        else:
            # catch errors
            print("no collection", collection)
            plot_entity = None
        # Then plot.
        if isinstance(plot_entity, (VertexSet, XsVertexSet, Attitude)):
            if isinstance(plot_entity.points, np_ndarray):
                if plot_entity.points_number > 0:
                    # This check is needed to avoid errors when trying to plot an empty
                    # PolyData, just created at the beginning of a digitizing session.
                    # Check if both these conditions are necessary_________________
                    # [Gabriele] Dip az needs to be converted to strike (dz-90) to plot with mplstereonet
                    strike = (plot_entity.points_map_dip_azimuth - 90) % 360
                    dip = plot_entity.points_map_dip

                    if np_all(strike != None):
                        if uid in self.selected_uids:
                            if show_property == "Planes":
                                this_actor = self.ax.plane(
                                    strike, dip, color=color_RGB
                                )[0]
                            else:
                                this_actor = self.ax.pole(strike, dip, color=color_RGB)[
                                    0
                                ]

                            this_actor.set_visible(visible)
                        else:
                            if show_property == "Planes":
                                this_actor = self.ax.plane(
                                    strike, dip, color=color_RGB
                                )[0]
                            else:
                                if filled is not None and visible is True:
                                    if filled:
                                        self.ax.density_contourf(
                                            strike, dip, measurement="poles"
                                        )
                                    else:
                                        self.ax.density_contour(
                                            strike, dip, measurement="poles"
                                        )
                                this_actor = self.ax.pole(strike, dip, color=color_RGB)[
                                    0
                                ]
                            if this_actor:
                                this_actor.set_visible(visible)
                    else:
                        this_actor = None
                else:
                    this_actor = None
            else:
                this_actor = None
        else:
            this_actor = None
        if this_actor:
            this_actor.figure.canvas.draw()
        return this_actor

    # def stop_event_loops(self):
    #     """Terminate running event loops"""
    #     self.figure.canvas.stop_event_loop()

    def change_grid(self, kind):
        self.grid_kind = kind
        self.ViewFrameLayout.removeWidget(self.canvas)
        self.ViewFrameLayout.removeWidget(self.navi_toolbar)
        self.initialize_interactor(kind=kind, projection=self.proj_type)
        uids = self.parent.geol_coll.df.loc[
            self.parent.geol_coll.df["topology"] == "VertexSet", "uid"
        ]

        # [Gabriele]It is not always the case that VertexSets have normal data (are attitude measurements). When
        # importing from shp we should add a dialog to identify VertexSets as Attitude measurements

        # att_uid_list = []
        # for uid in uids:
        #     obj = self.parent.geol_coll.get_uid_vtk_obj(uid)
        #     if isinstance(obj, Attitude):
        #         att_uid_list.append(uid)
        # print(att_uid_list)
        for uid in uids:
            show = self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]
            self.remove_actor_in_view(uid, redraw=False)
            this_actor = self.show_actor_with_property(uid, "geol_coll", visible=show)
            # Old Pandas <= 1.5.3
            # self.actors_df = self.actors_df.append(
            #     {
            #         "uid": uid,
            #         "actor": this_actor,
            #         "show": show,
            #         "collection": "geol_collection",
            #         "show_property": "poles",
            #     },
            #     ignore_index=True,
            # )
            # New Pandas >= 2.0.0
            self.actors_df = pd_concat(
                [
                    self.actors_df,
                    pd_DataFrame(
                        [
                            {
                                "uid": uid,
                                "actor": this_actor,
                                "show": show,
                                "collection": "geol_collection",
                                "show_property": "poles",
                            }
                        ]
                    ),
                ],
                ignore_index=True,
            )
            # For now only geol_collection (I guess this is the only collection for attitude measurements)

    def change_proj(self, projection):
        self.proj_type = projection
        self.ViewFrameLayout.removeWidget(self.canvas)
        self.ViewFrameLayout.removeWidget(self.navi_toolbar)
        self.initialize_interactor(kind=self.grid_kind, projection=self.proj_type)
        uids = self.parent.geol_coll.df.loc[
            self.parent.geol_coll.df["topology"] == "VertexSet", "uid"
        ]
        for uid in uids:
            show = self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]
            self.remove_actor_in_view(uid, redraw=False)
            this_actor = self.show_actor_with_property(uid, "geol_coll", visible=show)
            # Old Pandas <= 1.5.3
            # self.actors_df = self.actors_df.append(
            #     {
            #         "uid": uid,
            #         "actor": this_actor,
            #         "show": show,
            #         "collection": "geol_collection",
            #         "show_property": "poles",
            #     },
            #     ignore_index=True,
            # )
            # New Pandas >= 2.0.0
            self.actors_df = pd_concat(
                [
                    self.actors_df,
                    pd_DataFrame(
                        [
                            {
                                "uid": uid,
                                "actor": this_actor,
                                "show": show,
                                "collection": "geol_collection",
                                "show_property": "poles",
                            }
                        ]
                    ),
                ],
                ignore_index=True,
            )

    def toggle_contours(self, filled=False):
        # This is not the best way, but for now will do.
        """It's a toggle switch that display kamb contours for visible poles in
        the stereoplot."""

        self.ViewFrameLayout.removeWidget(self.canvas)
        self.ViewFrameLayout.removeWidget(self.navi_toolbar)

        self.initialize_interactor(kind=self.grid_kind, projection=self.proj_type)
        uids = self.parent.geol_coll.df.loc[
            (self.parent.geol_coll.df["topology"] == "VertexSet")
            | (self.parent.geol_coll.df["topology"] == "XsVertexSet"),
            "uid",
        ]

        if self.tog_contours == -1:
            filled_opt = filled
            self.tog_contours *= -1
            print("Contours enabled")
        else:
            filled_opt = None
            self.tog_contours *= -1
            print("Contours disabled")

        for uid in uids:
            show = self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]

            self.remove_actor_in_view(uid, redraw=False)

            this_actor = self.show_actor_with_property(
                uid, "geol_coll", visible=show, filled=filled_opt
            )
            # Old Pandas <= 1.5.3
            # self.actors_df = self.actors_df.append(
            #     {
            #         "uid": uid,
            #         "actor": this_actor,
            #         "show": show,
            #         "collection": "geol_collection",
            #         "show_property": "poles",
            #     },
            #     ignore_index=True,
            # )
            # New Pandas >= 2.0.0
            self.actors_df = pd_concat(
                [
                    self.actors_df,
                    pd_DataFrame(
                        [
                            {
                                "uid": uid,
                                "actor": this_actor,
                                "show": show,
                                "collection": "geol_collection",
                                "show_property": "poles",
                            }
                        ]
                    ),
                ],
                ignore_index=True,
            )

    def change_actor_color(self, uid=None, collection=None):
        """Change colour with Matplotlib method."""
        if collection == "geol_coll":
            color_R = self.parent.geol_coll.get_uid_legend(uid=uid)["color_R"]
            color_G = self.parent.geol_coll.get_uid_legend(uid=uid)["color_G"]
            color_B = self.parent.geol_coll.get_uid_legend(uid=uid)["color_B"]
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
        elif collection == "xsect_coll":
            color_R = self.parent.xsect_coll.get_legend()["color_R"]
            color_G = self.parent.xsect_coll.get_legend()["color_G"]
            color_B = self.parent.xsect_coll.get_legend()["color_B"]
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
        else:
            return
        if isinstance(
            self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[0], Line2D
        ):
            "Case for Line2D"
            self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[
                0
            ].set_color(color_RGB)
            self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[
                0
            ].figure.canvas.draw()

    def change_actor_opacity(self, uid=None, collection=None):
        return

    def change_actor_line_thick(self, uid=None, collection=None):
        return

    def change_actor_point_size(self, uid=None, collection=None):
        return
