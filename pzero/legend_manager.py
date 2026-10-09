"""legend_manager.py
PZero© Andrea Bistacchi"""

from PySide6.QtWidgets import (
    QTreeWidgetItem,
    QColorDialog,
    QPushButton,
    QSpinBox,
    QDoubleSpinBox,
    QComboBox,
    QHeaderView,
)
from PySide6.QtGui import QColor
from PySide6.QtCore import QObject

from pandas import unique as pd_unique
from math import isnan


legend_level_col = "Level"
legacy_legend_time_col = "time"


class Legend(QObject):
    """Legend for geological and all other entities.
    Dictionaries used to define types of legend columns."""

    geol_legend_dict = {
        "role": "undef",
        "feature": "undef",
        legend_level_col: 0.0,
        "sequence": "strati_0",
        "scenario": "undef",
        "color_R": int(255),
        "color_G": int(255),
        "color_B": int(255),
        "line_thick": int(2),
        "point_size": int(10),
        "opacity": int(100),
    }
    fluids_legend_dict = {
        "role": "undef",
        "feature": "undef",
        legend_level_col: 0.0,
        "sequence": "fluid_0",
        "scenario": "undef",
        "color_R": int(255),
        "color_G": int(255),
        "color_B": int(255),
        "line_thick": int(2),
        "point_size": int(10),
        "opacity": int(100),
    }
    backgrounds_legend_dict = {
        "role": "undef",
        "feature": "undef",
        legend_level_col: 0.0,
        "sequence": "back_0",
        "scenario": "undef",
        "color_R": int(255),
        "color_G": int(255),
        "color_B": int(255),
        "line_thick": int(2),
        "point_size": int(10),
        "opacity": int(100),
    }

    well_legend_dict = {
        "name": "undef",
        "color_R": int(255),
        "color_G": int(255),
        "color_B": int(255),
        "line_thick": int(2),
        "point_size": int(0),
        "opacity": int(100),
    }

    legend_dict_types = {
        "role": str,
        "feature": str,
        legend_level_col: float,
        "sequence": str,
        "scenario": str,
        "color_R": int,
        "color_G": int,
        "color_B": int,
        "line_thick": int,
        "point_size": int,
        "opacity": int,
    }
    legacy_legend_dict_types = {
        **legend_dict_types,
        legacy_legend_time_col: float,
    }

    @staticmethod
    def normalize_legend_dataframe(dataframe):
        """Migrate the legacy legend ``time`` column to ``Level`` in place."""
        if dataframe is None or legacy_legend_time_col not in dataframe.columns:
            return dataframe
        if legend_level_col not in dataframe.columns:
            dataframe.rename(
                columns={legacy_legend_time_col: legend_level_col}, inplace=True
            )
            return dataframe

        missing_level = dataframe[legend_level_col].isna()
        dataframe.loc[missing_level, legend_level_col] = dataframe.loc[
            missing_level, legacy_legend_time_col
        ]
        dataframe.drop(columns=legacy_legend_time_col, inplace=True)
        return dataframe

    others_legend_dict = {
        "other_collection": ["Boundary", "DOM", "Image", "Mesh3D", "Wells", "XSection"],
        "uid": ["", "", "", "", "", ""],
        "color_R": [255, 255, 255, 255, 255, 255],
        "color_G": [255, 255, 255, 255, 255, 255],
        "color_B": [255, 255, 255, 255, 255, 255],
        "line_thick": [2, 2, 2, 1, 2, 2],
        "point_size": [0, 2, 0, 0, 0, 0],
        "opacity": [100, 100, 100, 100, 100, 100],
    }

    def __init__(self, parent=None, *args, **kwargs):
        QObject.__init__(self, parent)

    def update_widget(self, parent=None):
        """Update the legend widget based on the legend table.
        The pattern to extract a cell value from a Pandas dataframe is: dataframe.loc[boolean_index_rows, boolean_index_columns].values[cell_id]
        The boolean indexes used by loc can be:
        - the name of a column (e.g. "color")
        - a boolean indexing series (i.e. a sequence of True and False values) obtained by one or more conditions applied on the dataframe
        - a numeric index or a range of indexes as used by iloc (i.e. 3 or 3:5)
        The method values[] applied at the end returns the cell value(s) at specified cell(s), otherwise a dataframe would be returned
        The function pd_unique() used above returns a list of unique values from a set of cells.
        TO ADD MORE PROPERTIES TO THE LEGEND, SIMPLY ADD MORE COLUMNS TO THE legend AND NEW WIDGETS HERE POINTING TO THE NEW COLUMNS
        Note that at and iat can be used to access a single value in a cell directly (so values[] is not required), but do not work with conditional indexing.
        """
        parent.LegendTreeWidget.clear()
        parent.LegendTreeWidget.setColumnCount(10)
        parent.LegendTreeWidget.setHeaderLabels(
            [
                "Role > Feature > Scenario",
                "R",
                "G",
                "B",
                "Color",
                "Line thickness",
                "Point size",
                "Opacity",
                "Level",
                "Sequence",
                "Show edges",
                "Show nodes",
            ]
        )
        parent.LegendTreeWidget.setItemsExpandable(True)

        for other_collection in pd_unique(parent.others_legend_df["other_collection"]):
            color_R = parent.others_legend_df.loc[
                parent.others_legend_df["other_collection"] == other_collection,
                "color_R",
            ].values[0]
            color_G = parent.others_legend_df.loc[
                parent.others_legend_df["other_collection"] == other_collection,
                "color_G",
            ].values[0]
            color_B = parent.others_legend_df.loc[
                parent.others_legend_df["other_collection"] == other_collection,
                "color_B",
            ].values[0]
            line_thick = parent.others_legend_df.loc[
                parent.others_legend_df["other_collection"] == other_collection,
                "line_thick",
            ].values[0]
            point_size = parent.others_legend_df.loc[
                parent.others_legend_df["other_collection"] == other_collection,
                "point_size",
            ].values[0]
            opacity = parent.others_legend_df.loc[
                parent.others_legend_df["other_collection"] == other_collection,
                "opacity",
            ].values[0]

            "other_color_dialog_btn > QPushButton used to select color"
            other_color_dialog_btn = QPushButton()
            other_color_dialog_btn.other_collection = other_collection  # this is to pass these values to the update function below
            other_color_dialog_btn.setStyleSheet(
                "background-color:rgb({},{},{})".format(color_R, color_G, color_B)
            )
            "other_line_thick_spn > QSpinBox used to select line thickness"
            other_line_thick_spn = QSpinBox()
            other_line_thick_spn.other_collection = other_collection  # this is to pass these values to the update function below
            other_line_thick_spn.setValue(line_thick)
            "other_point_size_spn > QSpinBox used to select point size"
            other_point_size_spn = QSpinBox()
            other_point_size_spn.other_collection = other_collection  # this is to pass these values to the update function below
            other_point_size_spn.setValue(point_size)
            "other_opacity_spn > QSpinBox used to select opacity"
            other_opacity_spn = QSpinBox()
            other_opacity_spn.setMaximum(100)
            other_opacity_spn.other_collection = other_collection  # this is to pass these values to the update function below
            other_opacity_spn.setValue(opacity)
            "IN THE FUTURE add QComboBox() here to show/hide mesh edges___________"
            "IN THE FUTURE add QComboBox() here to show/hide points___________"
            "Create items"
            llevel_1 = QTreeWidgetItem(
                parent.LegendTreeWidget,
                [other_collection, str(color_R), str(color_G), str(color_B)],
            )  # self.GeologyTreeWidget as parent -> top level
            if other_collection == "Mesh3D":
                for uid, name in parent.mesh3d_coll.df[["uid", "name"]].itertuples(
                    index=False, name=None
                ):
                    legend = parent.mesh3d_coll.get_uid_legend(uid)
                    mesh_item = QTreeWidgetItem(
                        llevel_1,
                        [
                            str(name),
                            str(legend["color_R"]),
                            str(legend["color_G"]),
                            str(legend["color_B"]),
                        ],
                    )
                    color_button = QPushButton()
                    color_button.setStyleSheet(
                        "background-color:rgb({},{},{})".format(
                            legend["color_R"], legend["color_G"], legend["color_B"]
                        )
                    )
                    parent.LegendTreeWidget.setItemWidget(mesh_item, 4, color_button)
                    color_button.clicked.connect(
                        lambda *, mesh_uid=uid, item=mesh_item, button=color_button: self.change_mesh_color(
                            parent=parent, uid=mesh_uid, item=item, button=button
                        )
                    )
                    thick_spin = QSpinBox()
                    thick_spin.setValue(legend["line_thick"])
                    parent.LegendTreeWidget.setItemWidget(mesh_item, 5, thick_spin)
                    thick_spin.valueChanged.connect(
                        lambda value, mesh_uid=uid: self.change_mesh_style(
                            parent, mesh_uid, "line_thick", value
                        )
                    )
                    opacity_spin = QSpinBox()
                    opacity_spin.setMaximum(100)
                    opacity_spin.setValue(legend["opacity"])
                    parent.LegendTreeWidget.setItemWidget(mesh_item, 7, opacity_spin)
                    opacity_spin.valueChanged.connect(
                        lambda value, mesh_uid=uid: self.change_mesh_style(
                            parent, mesh_uid, "opacity", value
                        )
                    )
                continue
            parent.LegendTreeWidget.setItemWidget(llevel_1, 4, other_color_dialog_btn)
            parent.LegendTreeWidget.setItemWidget(llevel_1, 5, other_line_thick_spn)
            if other_collection == "DOM":
                parent.LegendTreeWidget.setItemWidget(llevel_1, 6, other_point_size_spn)
                other_point_size_spn.valueChanged.connect(
                    lambda *, sender=other_point_size_spn: self.change_other_feature_point_size(
                        sender=sender, parent=parent
                    )
                )
            parent.LegendTreeWidget.setItemWidget(llevel_1, 7, other_opacity_spn)
            "Set signals for the widgets below"
            other_color_dialog_btn.clicked.connect(
                lambda *, sender=other_color_dialog_btn: self.change_other_feature_color(
                    sender=sender, parent=parent
                )
            )
            other_line_thick_spn.valueChanged.connect(
                lambda *, sender=other_line_thick_spn: self.change_other_feature_line_thick(
                    sender=sender, parent=parent
                )
            )
            other_opacity_spn.valueChanged.connect(
                lambda *, sender=other_opacity_spn: self.change_other_feature_opacity(
                    sender=sender, parent=parent
                )
            )

        for role in pd_unique(parent.geol_coll.legend_df["role"]):
            llevel_1 = QTreeWidgetItem(
                parent.LegendTreeWidget, [role]
            )  # self.GeologyTreeWidget as parent -> top level
            for feature in pd_unique(
                parent.geol_coll.legend_df.loc[
                    parent.geol_coll.legend_df["role"] == role,
                    "feature",
                ]
            ):
                llevel_2 = QTreeWidgetItem(
                    llevel_1, [feature]
                )  # llevel_1 as parent -> 2nd level
                for scenario in pd_unique(
                    parent.geol_coll.legend_df.loc[
                        (parent.geol_coll.legend_df["role"] == role)
                        & (parent.geol_coll.legend_df["feature"] == feature),
                        "scenario",
                    ]
                ):
                    color_R = parent.geol_coll.legend_df.loc[
                        (parent.geol_coll.legend_df["role"] == role)
                        & (parent.geol_coll.legend_df["feature"] == feature)
                        & (parent.geol_coll.legend_df["scenario"] == scenario),
                        "color_R",
                    ].values[0]
                    color_G = parent.geol_coll.legend_df.loc[
                        (parent.geol_coll.legend_df["role"] == role)
                        & (parent.geol_coll.legend_df["feature"] == feature)
                        & (parent.geol_coll.legend_df["scenario"] == scenario),
                        "color_G",
                    ].values[0]
                    color_B = parent.geol_coll.legend_df.loc[
                        (parent.geol_coll.legend_df["role"] == role)
                        & (parent.geol_coll.legend_df["feature"] == feature)
                        & (parent.geol_coll.legend_df["scenario"] == scenario),
                        "color_B",
                    ].values[0]
                    line_thick = parent.geol_coll.legend_df.loc[
                        (parent.geol_coll.legend_df["role"] == role)
                        & (parent.geol_coll.legend_df["feature"] == feature)
                        & (parent.geol_coll.legend_df["scenario"] == scenario),
                        "line_thick",
                    ].values[0]
                    point_size = parent.geol_coll.legend_df.loc[
                        (parent.geol_coll.legend_df["role"] == role)
                        & (parent.geol_coll.legend_df["feature"] == feature)
                        & (parent.geol_coll.legend_df["scenario"] == scenario),
                        "point_size",
                    ].values[0]
                    opacity = parent.geol_coll.legend_df.loc[
                        (parent.geol_coll.legend_df["role"] == role)
                        & (parent.geol_coll.legend_df["feature"] == feature)
                        & (parent.geol_coll.legend_df["scenario"] == scenario),
                        "opacity",
                    ].values[0]
                    level_value = parent.geol_coll.legend_df.loc[
                        (parent.geol_coll.legend_df["role"] == role)
                        & (parent.geol_coll.legend_df["feature"] == feature)
                        & (parent.geol_coll.legend_df["scenario"] == scenario),
                        legend_level_col,
                    ].values[0]
                    sequence_value = parent.geol_coll.legend_df.loc[
                        (parent.geol_coll.legend_df["role"] == role)
                        & (parent.geol_coll.legend_df["feature"] == feature)
                        & (parent.geol_coll.legend_df["scenario"] == scenario),
                        "sequence",
                    ].values[0]
                    # if not isinstance(sequence_value, str):
                    #     print("sequence_value: ", sequence_value)
                    #     sequence_value = "strati_0"
                    #     print("sequence_value: ", sequence_value)
                    "geol_color_dialog_btn > QPushButton used to select color"
                    geol_color_dialog_btn = QPushButton()
                    geol_color_dialog_btn.role = role  # this is to pass these values to the update function below
                    geol_color_dialog_btn.feature = feature
                    geol_color_dialog_btn.scenario = scenario
                    geol_color_dialog_btn.setStyleSheet(
                        "background-color:rgb({},{},{})".format(
                            color_R, color_G, color_B
                        )
                    )
                    "geol_line_thick_spn > QSpinBox used to select line thickness"
                    geol_line_thick_spn = QSpinBox()
                    geol_line_thick_spn.role = role  # this is to pass these values to the update function below
                    geol_line_thick_spn.feature = feature
                    geol_line_thick_spn.scenario = scenario
                    geol_line_thick_spn.setValue(line_thick)
                    "geol_point_size_spn > QSpinBox used to select point size"
                    geol_point_size_spn = QSpinBox()
                    geol_point_size_spn.role = role  # this is to pass these values to the update function below
                    geol_point_size_spn.feature = feature
                    geol_point_size_spn.scenario = scenario
                    if isnan(point_size):
                        point_size = 0
                    geol_point_size_spn.setValue(point_size)
                    "geol_line_opacity_spn > QSpinBox used to select opacity"
                    geol_opacity_spn = QSpinBox()
                    geol_opacity_spn.role = role  # this is to pass these values to the update function below
                    geol_opacity_spn.feature = feature
                    geol_opacity_spn.scenario = scenario
                    geol_opacity_spn.setMaximum(100)
                    if isnan(opacity):
                        opacity = 0
                    geol_opacity_spn.setValue(opacity)
                    "geol_level_spn > QDoubleSpinBox used to set the structural level"
                    geol_level_spn = QDoubleSpinBox()
                    geol_level_spn.setMinimum(-999999.0)
                    geol_level_spn.role = role  # this is to pass these values to the update function below
                    geol_level_spn.feature = feature
                    geol_level_spn.scenario = scenario
                    geol_level_spn.setValue(level_value)
                    "geol_sequence_combo > QComboBox used to define geological sequence"
                    geol_sequence_combo = QComboBox()
                    geol_sequence_combo.setEditable(True)
                    geol_sequence_combo.role = role  # this is to pass these values to the update function below
                    geol_sequence_combo.feature = feature
                    geol_sequence_combo.scenario = scenario
                    geol_sequence_combo.addItems(
                        parent.geol_coll.legend_df["sequence"].unique()
                    )
                    geol_sequence_combo.setCurrentText(sequence_value)
                    "IN THE FUTURE add QComboBox() to show/hide mesh edges___________"
                    "IN THE FUTURE add QComboBox() to show/hide points___________"
                    "Create items"
                    llevel_3 = QTreeWidgetItem(
                        llevel_2, [scenario, str(color_R), str(color_G), str(color_B)]
                    )  # llevel_2 as parent -> 3rd level
                    parent.LegendTreeWidget.setItemWidget(
                        llevel_3, 4, geol_color_dialog_btn
                    )
                    parent.LegendTreeWidget.setItemWidget(
                        llevel_3, 5, geol_line_thick_spn
                    )
                    parent.LegendTreeWidget.setItemWidget(
                        llevel_3, 6, geol_point_size_spn
                    )
                    parent.LegendTreeWidget.setItemWidget(llevel_3, 7, geol_opacity_spn)
                    parent.LegendTreeWidget.setItemWidget(llevel_3, 8, geol_level_spn)
                    parent.LegendTreeWidget.setItemWidget(
                        llevel_3, 9, geol_sequence_combo
                    )
                    "Set signals for the widgets below"
                    geol_color_dialog_btn.clicked.connect(
                        lambda *, sender=geol_color_dialog_btn: self.change_geology_feature_color(
                            sender=sender, parent=parent
                        )
                    )
                    geol_line_thick_spn.valueChanged.connect(
                        lambda *, sender=geol_line_thick_spn: self.change_geology_feature_line_thick(
                            sender=sender, parent=parent
                        )
                    )
                    geol_point_size_spn.valueChanged.connect(
                        lambda *, sender=geol_point_size_spn: self.change_geology_feature_point_size(
                            sender=sender, parent=parent
                        )
                    )
                    geol_opacity_spn.valueChanged.connect(
                        lambda *, sender=geol_opacity_spn: self.change_geology_feature_opacity(
                            sender=sender, parent=parent
                        )
                    )
                    geol_level_spn.editingFinished.connect(
                        lambda *, sender=geol_level_spn: self.change_level(
                            sender=sender, parent=parent
                        )
                    )
                    geol_sequence_combo.currentTextChanged.connect(
                        lambda *, sender=geol_sequence_combo: self.change_geological_sequence(
                            sender=sender, parent=parent
                        )
                    )

        for role in pd_unique(parent.fluid_coll.legend_df["role"]):
            llevel_1 = QTreeWidgetItem(
                parent.LegendTreeWidget, [role]
            )  # self.GeologyTreeWidget as parent -> top level
            for feature in pd_unique(
                parent.fluid_coll.legend_df.loc[
                    parent.fluid_coll.legend_df["role"] == role, "feature"
                ]
            ):
                llevel_2 = QTreeWidgetItem(
                    llevel_1, [feature]
                )  # llevel_1 as parent -> 2nd level
                for scenario in pd_unique(
                    parent.fluid_coll.legend_df.loc[
                        (parent.fluid_coll.legend_df["role"] == role)
                        & (parent.fluid_coll.legend_df["feature"] == feature),
                        "scenario",
                    ]
                ):
                    color_R = parent.fluid_coll.legend_df.loc[
                        (parent.fluid_coll.legend_df["role"] == role)
                        & (parent.fluid_coll.legend_df["feature"] == feature)
                        & (parent.fluid_coll.legend_df["scenario"] == scenario),
                        "color_R",
                    ].values[0]
                    color_G = parent.fluid_coll.legend_df.loc[
                        (parent.fluid_coll.legend_df["role"] == role)
                        & (parent.fluid_coll.legend_df["feature"] == feature)
                        & (parent.fluid_coll.legend_df["scenario"] == scenario),
                        "color_G",
                    ].values[0]
                    color_B = parent.fluid_coll.legend_df.loc[
                        (parent.fluid_coll.legend_df["role"] == role)
                        & (parent.fluid_coll.legend_df["feature"] == feature)
                        & (parent.fluid_coll.legend_df["scenario"] == scenario),
                        "color_B",
                    ].values[0]
                    line_thick = parent.fluid_coll.legend_df.loc[
                        (parent.fluid_coll.legend_df["role"] == role)
                        & (parent.fluid_coll.legend_df["feature"] == feature)
                        & (parent.fluid_coll.legend_df["scenario"] == scenario),
                        "line_thick",
                    ].values[0]
                    point_size = parent.fluid_coll.legend_df.loc[
                        (parent.fluid_coll.legend_df["role"] == role)
                        & (parent.fluid_coll.legend_df["feature"] == feature)
                        & (parent.fluid_coll.legend_df["scenario"] == scenario),
                        "point_size",
                    ].values[0]
                    opacity = parent.fluid_coll.legend_df.loc[
                        (parent.fluid_coll.legend_df["role"] == role)
                        & (parent.fluid_coll.legend_df["feature"] == feature)
                        & (parent.fluid_coll.legend_df["scenario"] == scenario),
                        "opacity",
                    ].values[0]
                    level_value = parent.fluid_coll.legend_df.loc[
                        (parent.fluid_coll.legend_df["role"] == role)
                        & (parent.fluid_coll.legend_df["feature"] == feature)
                        & (parent.fluid_coll.legend_df["scenario"] == scenario),
                        legend_level_col,
                    ].values[0]
                    # fluid_sequence_value = parent.fluid_coll.legend_df.loc[(parent.fluid_coll.legend_df['role'] == role) & (parent.fluid_coll.legend_df['feature'] == feature) & (parent.fluid_coll.legend_df['scenario'] == scenario), "sequence"].values[0]
                    # if not isinstance(sequence_value, str):
                    #     print("sequence_value: ", sequence_value)
                    #     sequence_value = "strati_0"
                    #     print("sequence_value: ", sequence_value)
                    "geol_color_dialog_btn > QPushButton used to select color"
                    fluid_color_dialog_btn = QPushButton()
                    fluid_color_dialog_btn.role = role  # this is to pass these values to the update function below
                    fluid_color_dialog_btn.feature = feature
                    fluid_color_dialog_btn.scenario = scenario
                    fluid_color_dialog_btn.setStyleSheet(
                        "background-color:rgb({},{},{})".format(
                            color_R, color_G, color_B
                        )
                    )
                    "fluid_line_thick_spn > QSpinBox used to select line thickness"
                    fluid_line_thick_spn = QSpinBox()
                    fluid_line_thick_spn.role = role  # this is to pass these values to the update function below
                    fluid_line_thick_spn.feature = feature
                    fluid_line_thick_spn.scenario = scenario
                    fluid_line_thick_spn.setValue(line_thick)
                    "fluid_point_size_spn > QSpinBox used to select point size"
                    fluid_point_size_spn = QSpinBox()
                    fluid_point_size_spn.role = role  # this is to pass these values to the update function below
                    fluid_point_size_spn.feature = feature
                    fluid_point_size_spn.scenario = scenario
                    fluid_point_size_spn.setValue(point_size)
                    "fluid_opacity_spn > QSpinBox used to select line thickness"
                    fluid_opacity_spn = QSpinBox()
                    fluid_opacity_spn.role = role  # this is to pass these values to the update function below
                    fluid_opacity_spn.feature = feature
                    fluid_opacity_spn.scenario = scenario
                    fluid_opacity_spn.setMaximum(100)
                    fluid_opacity_spn.setValue(opacity)
                    "fluid_level_spn > QDoubleSpinBox used to set the structural level"
                    fluid_level_spn = QDoubleSpinBox()
                    fluid_level_spn.setMinimum(-999999.0)
                    fluid_level_spn.role = role  # this is to pass these values to the update function below
                    fluid_level_spn.feature = feature
                    fluid_level_spn.scenario = scenario
                    fluid_level_spn.setValue(level_value)
                    "geol_sequence_combo > QComboBox used to define geological sequence"
                    # geol_sequence_combo = QComboBox()
                    # geol_sequence_combo.setEditable(True)
                    # geol_sequence_combo.role = role  # this is to pass these values to the update function below
                    # geol_sequence_combo.feature = feature
                    # geol_sequence_combo.scenario = scenario
                    # geol_sequence_combo.addItems(parent.geol_coll.legend_df['sequence'].unique())
                    # geol_sequence_combo.setCurrentText(sequence_value)
                    "IN THE FUTURE add QComboBox() to show/hide mesh edges___________"
                    "IN THE FUTURE add QComboBox() to show/hide points___________"
                    "Create items"
                    llevel_3 = QTreeWidgetItem(
                        llevel_2, [scenario, str(color_R), str(color_G), str(color_B)]
                    )  # llevel_2 as parent -> 3rd level
                    parent.LegendTreeWidget.setItemWidget(
                        llevel_3, 4, fluid_color_dialog_btn
                    )
                    parent.LegendTreeWidget.setItemWidget(
                        llevel_3, 5, fluid_line_thick_spn
                    )
                    parent.LegendTreeWidget.setItemWidget(
                        llevel_3, 6, fluid_point_size_spn
                    )
                    parent.LegendTreeWidget.setItemWidget(
                        llevel_3, 7, fluid_opacity_spn
                    )
                    parent.LegendTreeWidget.setItemWidget(llevel_3, 8, fluid_level_spn)
                    # parent.LegendTreeWidget.setItemWidget(llevel_3, 7, geol_sequence_combo)
                    "Set signals for the widgets below"
                    fluid_color_dialog_btn.clicked.connect(
                        lambda *, sender=fluid_color_dialog_btn: self.change_fluid_feature_color(
                            sender=sender, parent=parent
                        )
                    )
                    fluid_line_thick_spn.valueChanged.connect(
                        lambda *, sender=fluid_line_thick_spn: self.change_fluid_feature_line_thick(
                            sender=sender, parent=parent
                        )
                    )
                    fluid_point_size_spn.valueChanged.connect(
                        lambda *, sender=fluid_point_size_spn: self.change_fluid_feature_point_size(
                            sender=sender, parent=parent
                        )
                    )
                    fluid_opacity_spn.valueChanged.connect(
                        lambda *, sender=fluid_opacity_spn: self.change_fluid_feature_opacity(
                            sender=sender, parent=parent
                        )
                    )
                    fluid_level_spn.editingFinished.connect(
                        lambda *, sender=fluid_level_spn: self.change_fluid_level(
                            sender=sender, parent=parent
                        )
                    )
                    # fluid_sequence_combo.currentTextChanged.connect(lambda: self.change_fluid_sequence(parent=parent))

        for role in pd_unique(parent.backgrnd_coll.legend_df["role"]):
            llevel_1 = QTreeWidgetItem(
                parent.LegendTreeWidget, [role]
            )  # self.GeologyTreeWidget as parent -> top level
            for feature in pd_unique(
                parent.backgrnd_coll.legend_df.loc[
                    parent.backgrnd_coll.legend_df["role"] == role,
                    "feature",
                ]
            ):
                llevel_2 = QTreeWidgetItem(
                    llevel_1, [feature]
                )  # llevel_1 as parent -> 2nd level
                color_R = parent.backgrnd_coll.legend_df.loc[
                    (parent.backgrnd_coll.legend_df["role"] == role)
                    & (parent.backgrnd_coll.legend_df["feature"] == feature),
                    "color_R",
                ].values[0]
                color_G = parent.backgrnd_coll.legend_df.loc[
                    (parent.backgrnd_coll.legend_df["role"] == role)
                    & (parent.backgrnd_coll.legend_df["feature"] == feature),
                    "color_G",
                ].values[0]
                color_B = parent.backgrnd_coll.legend_df.loc[
                    (parent.backgrnd_coll.legend_df["role"] == role)
                    & (parent.backgrnd_coll.legend_df["feature"] == feature),
                    "color_B",
                ].values[0]
                line_thick = parent.backgrnd_coll.legend_df.loc[
                    (parent.backgrnd_coll.legend_df["role"] == role)
                    & (parent.backgrnd_coll.legend_df["feature"] == feature),
                    "line_thick",
                ].values[0]
                point_size = parent.backgrnd_coll.legend_df.loc[
                    (parent.backgrnd_coll.legend_df["role"] == role)
                    & (parent.backgrnd_coll.legend_df["feature"] == feature),
                    "point_size",
                ].values[0]
                opacity = parent.backgrnd_coll.legend_df.loc[
                    (parent.backgrnd_coll.legend_df["role"] == role)
                    & (parent.backgrnd_coll.legend_df["feature"] == feature),
                    "opacity",
                ].values[0]
                "geol_color_dialog_btn > QPushButton used to select color"
                backgrounds_color_dialog_btn = QPushButton()
                backgrounds_color_dialog_btn.role = (
                    role  # this is to pass these values to the update function below
                )
                backgrounds_color_dialog_btn.feature = feature
                backgrounds_color_dialog_btn.setStyleSheet(
                    "background-color:rgb({},{},{})".format(color_R, color_G, color_B)
                )
                "background_line_thick_spn > QSpinBox used to select line thickness"
                background_line_thick_spn = QSpinBox()
                background_line_thick_spn.role = (
                    role  # this is to pass these values to the update function below
                )
                background_line_thick_spn.feature = feature
                background_line_thick_spn.setValue(line_thick)

                "background_point_size_spn > QSpinBox used to select line thickness"
                background_point_size_spn = QSpinBox()
                background_point_size_spn.role = (
                    role  # this is to pass these values to the update function below
                )
                background_point_size_spn.feature = feature
                background_point_size_spn.setValue(point_size)
                "background_opacity_spn > QSpinBox used to select line thickness"
                background_opacity_spn = QSpinBox()
                background_opacity_spn.role = (
                    role  # this is to pass these values to the update function below
                )
                background_opacity_spn.feature = feature
                background_opacity_spn.setMaximum(100)
                background_opacity_spn.setValue(opacity)
                "Create items"
                # llevel_3 = QTreeWidgetItem(llevel_2, [scenario, str(color_R), str(color_G), str(color_B)])  # llevel_2 as parent -> 3rd level
                parent.LegendTreeWidget.setItemWidget(
                    llevel_2, 4, backgrounds_color_dialog_btn
                )
                parent.LegendTreeWidget.setItemWidget(
                    llevel_2, 5, background_line_thick_spn
                )
                parent.LegendTreeWidget.setItemWidget(
                    llevel_2, 6, background_point_size_spn
                )
                parent.LegendTreeWidget.setItemWidget(
                    llevel_2, 7, background_opacity_spn
                )
                "Set signals for the widgets below"
                backgrounds_color_dialog_btn.clicked.connect(
                    lambda *, sender=backgrounds_color_dialog_btn: self.change_background_feature_color(
                        sender=sender, parent=parent
                    )
                )
                background_line_thick_spn.valueChanged.connect(
                    lambda *, sender=background_line_thick_spn: self.change_background_feature_line_thick(
                        sender=sender, parent=parent
                    )
                )
                background_point_size_spn.valueChanged.connect(
                    lambda *, sender=background_point_size_spn: self.change_background_feature_point_size(
                        sender=sender, parent=parent
                    )
                )
                background_opacity_spn.valueChanged.connect(
                    lambda *, sender=background_opacity_spn: self.change_background_opacity(
                        sender=sender, parent=parent
                    )
                )
        # Squeeze column width to fit content
        for col in range(parent.LegendTreeWidget.columnCount()):
            parent.LegendTreeWidget.resizeColumnToContents(col)
        # Expand all tree items
        parent.LegendTreeWidget.expandAll()

    def change_mesh_color(self, parent, uid, item, button):
        legend = parent.mesh3d_coll.get_uid_legend(uid)
        color = QColorDialog.getColor(
            initial=QColor(
                legend["color_R"], legend["color_G"], legend["color_B"]
            ),
            title="Select color",
        )
        if not color.isValid():
            return
        values = (color.red(), color.green(), color.blue())
        parent.mesh3d_coll.set_uid_legend(
            uid=uid, color_R=values[0], color_G=values[1], color_B=values[2]
        )
        for column, value in enumerate(values, start=1):
            item.setText(column, str(value))
        button.setStyleSheet("background-color:rgb({},{},{})".format(*values))
        parent.signals.legend_color_modified.emit([uid], parent.mesh3d_coll)

    def change_mesh_style(self, parent, uid, property_name, value):
        parent.mesh3d_coll.set_uid_legend(uid=uid, **{property_name: value})
        signal = (
            parent.signals.legend_thick_modified
            if property_name == "line_thick"
            else parent.signals.legend_opacity_modified
        )
        signal.emit([uid], parent.mesh3d_coll)

    def change_geology_feature_color(self, sender=None, parent=None):
        # role = self.sender().role
        # feature = self.sender().feature
        # scenario = self.sender().scenario
        role = sender.role
        feature = sender.feature
        scenario = sender.scenario
        # Here we use the same query as above to GET the color from the legend
        old_color_R = parent.geol_coll.legend_df.loc[
            (parent.geol_coll.legend_df["role"] == role)
            & (parent.geol_coll.legend_df["feature"] == feature)
            & (parent.geol_coll.legend_df["scenario"] == scenario),
            "color_R",
        ].values[0]
        old_color_G = parent.geol_coll.legend_df.loc[
            (parent.geol_coll.legend_df["role"] == role)
            & (parent.geol_coll.legend_df["feature"] == feature)
            & (parent.geol_coll.legend_df["scenario"] == scenario),
            "color_G",
        ].values[0]
        old_color_B = parent.geol_coll.legend_df.loc[
            (parent.geol_coll.legend_df["role"] == role)
            & (parent.geol_coll.legend_df["feature"] == feature)
            & (parent.geol_coll.legend_df["scenario"] == scenario),
            "color_B",
        ].values[0]
        color_in = QColor(
            old_color_R, old_color_G, old_color_B
        )  # https://doc.qt.io/qtforpython/PySide2/QtGui/QColor.html#PySide2.QtGui.QColor
        color_out = QColorDialog.getColor(
            initial=color_in, title="Select color"
        )  # https://doc.qt.io/qtforpython/PySide2/QtWidgets/QColorDialog.html#PySide2.QtWidgets.PySide2.QtWidgets.QColorDialog.getColor
        if not color_out.isValid():
            color_out = color_in
        new_color_R = color_out.red()
        new_color_G = color_out.green()
        new_color_B = color_out.blue()
        # Here the query is reversed and modified, dropping the values() method, to allow SETTING the color in the legend.
        parent.geol_coll.legend_df.loc[
            (parent.geol_coll.legend_df["role"] == role)
            & (parent.geol_coll.legend_df["feature"] == feature)
            & (parent.geol_coll.legend_df["scenario"] == scenario),
            "color_R",
        ] = new_color_R
        parent.geol_coll.legend_df.loc[
            (parent.geol_coll.legend_df["role"] == role)
            & (parent.geol_coll.legend_df["feature"] == feature)
            & (parent.geol_coll.legend_df["scenario"] == scenario),
            "color_G",
        ] = new_color_G
        parent.geol_coll.legend_df.loc[
            (parent.geol_coll.legend_df["role"] == role)
            & (parent.geol_coll.legend_df["feature"] == feature)
            & (parent.geol_coll.legend_df["scenario"] == scenario),
            "color_B",
        ] = new_color_B
        # Update sender color.
        # self.sender().setStyleSheet(
        #     "background-color:rgb({},{},{})".format(
        #         new_color_R, new_color_G, new_color_B
        #     )
        # )
        sender.setStyleSheet(
            "background-color:rgb({},{},{})".format(
                new_color_R, new_color_G, new_color_B
            )
        )
        # Signal to update actors in windows. This is emitted only for the modified uid under the 'color' key.
        updated_list = parent.geol_coll.df.loc[
            (parent.geol_coll.df["role"] == role)
            & (parent.geol_coll.df["feature"] == feature)
            & (parent.geol_coll.df["scenario"] == scenario),
            "uid",
        ].to_list()
        parent.signals.legend_color_modified.emit(updated_list, parent.geol_coll)
        # self.change_well_feature_color(parent,feature) #Update the wells

    def change_geology_feature_line_thick(self, sender=None, parent=None):
        # role = self.sender().role
        # feature = self.sender().feature
        # scenario = self.sender().scenario
        # line_thick = self.sender().value()
        role = sender.role
        feature = sender.feature
        scenario = sender.scenario
        line_thick = sender.value()
        "Here the query is reversed and modified, dropping the values() method, to allow SETTING the line thickness in the legend"
        parent.geol_coll.legend_df.loc[
            (parent.geol_coll.legend_df["role"] == role)
            & (parent.geol_coll.legend_df["feature"] == feature)
            & (parent.geol_coll.legend_df["scenario"] == scenario),
            "line_thick",
        ] = line_thick
        # Signal to update actors in windows. This is emitted only for the modified uid under the 'line_thick' key.
        updated_list = parent.geol_coll.df.loc[
            (parent.geol_coll.df["role"] == role)
            & (parent.geol_coll.df["feature"] == feature)
            & (parent.geol_coll.df["scenario"] == scenario),
            "uid",
        ].to_list()
        parent.signals.legend_thick_modified.emit(updated_list, parent.geol_coll)

    def change_geology_feature_point_size(self, sender=None, parent=None):
        # role = self.sender().role
        # feature = self.sender().feature
        # scenario = self.sender().scenario
        # point_size = self.sender().value()
        role = sender.role
        feature = sender.feature
        scenario = sender.scenario
        point_size = sender.value()
        # Here the query is reversed and modified, dropping the values() method, to allow SETTING the line thickness in the legend
        parent.geol_coll.legend_df.loc[
            (parent.geol_coll.legend_df["role"] == role)
            & (parent.geol_coll.legend_df["feature"] == feature)
            & (parent.geol_coll.legend_df["scenario"] == scenario),
            "point_size",
        ] = point_size
        # Signal to update actors in windows. This is emitted only for the modified uid under the 'line_thick' key.
        updated_list = parent.geol_coll.df.loc[
            (parent.geol_coll.df["role"] == role)
            & (parent.geol_coll.df["feature"] == feature)
            & (parent.geol_coll.df["scenario"] == scenario),
            "uid",
        ].to_list()
        parent.signals.legend_point_size_modified.emit(updated_list, parent.geol_coll)

    def change_geology_feature_opacity(self, sender=None, parent=None):
        # role = self.sender().role
        # feature = self.sender().feature
        # scenario = self.sender().scenario
        # opacity = self.sender().value()
        role = sender.role
        feature = sender.feature
        scenario = sender.scenario
        opacity = sender.value()
        # Here the query is reversed and modified, dropping the values() method, to allow SETTING the line thickness in the legend
        parent.geol_coll.legend_df.loc[
            (parent.geol_coll.legend_df["role"] == role)
            & (parent.geol_coll.legend_df["feature"] == feature)
            & (parent.geol_coll.legend_df["scenario"] == scenario),
            "opacity",
        ] = opacity
        # Signal to update actors in windows. This is emitted only for the modified uid under the 'opacity' key.
        updated_list = parent.geol_coll.df.loc[
            (parent.geol_coll.df["role"] == role)
            & (parent.geol_coll.df["feature"] == feature)
            & (parent.geol_coll.df["scenario"] == scenario),
            "uid",
        ].to_list()
        parent.signals.legend_opacity_modified.emit(updated_list, parent.geol_coll)

    def change_level(self, sender=None, parent=None):
        role = sender.role
        feature = sender.feature
        scenario = sender.scenario
        level = sender.value()
        parent.geol_coll.legend_df.loc[
            (parent.geol_coll.legend_df["role"] == role)
            & (parent.geol_coll.legend_df["feature"] == feature)
            & (parent.geol_coll.legend_df["scenario"] == scenario),
            legend_level_col,
        ] = level
        parent.geol_coll.legend_df.sort_values(
            by=legend_level_col, ascending=True, inplace=True
        )
        if hasattr(parent, "sync_structural_topology_tables_from_legend"):
            parent.sync_structural_topology_tables_from_legend()

    def change_geological_sequence(self, sender=None, parent=None):
        # role = self.sender().role
        # feature = self.sender().feature
        # scenario = self.sender().scenario
        # geol_seqn = self.sender().currentText()
        role = sender.role
        feature = sender.feature
        scenario = sender.scenario
        geol_seqn = sender.currentText()
        parent.geol_coll.legend_df.loc[
            (parent.geol_coll.legend_df["role"] == role)
            & (parent.geol_coll.legend_df["feature"] == feature)
            & (parent.geol_coll.legend_df["scenario"] == scenario),
            "sequence",
        ] = geol_seqn
        # THE FOLLOWING MUST BE CHANGED IN A FOR LOOP OVER ALL ITEMS IN COLUMN 7
        # parent.LegendTreeWidget.setItemWidget(llevel_3, 7, geol_sequence_combo)
        # UPDATING THE VALUES AS IN
        # geol_sequence_combo.addItems(parent.geol_coll.legend_df['sequence'].unique())

    def change_other_feature_color(self, sender=None, parent=None):
        # other_collection = self.sender().other_collection
        other_collection = sender.other_collection
        # Here we use the same query as above to GET the color from the legend
        old_color_R = parent.others_legend_df.loc[
            (parent.others_legend_df["other_collection"] == other_collection), "color_R"
        ].values[0]
        old_color_G = parent.others_legend_df.loc[
            (parent.others_legend_df["other_collection"] == other_collection), "color_G"
        ].values[0]
        old_color_B = parent.others_legend_df.loc[
            (parent.others_legend_df["other_collection"] == other_collection), "color_B"
        ].values[0]
        color_in = QColor(
            old_color_R, old_color_G, old_color_B
        )  # https://doc.qt.io/qtforpython/PySide2/QtGui/QColor.html#PySide2.QtGui.QColor
        color_out = QColorDialog.getColor(
            initial=color_in, title="Select color"
        )  # https://doc.qt.io/qtforpython/PySide2/QtWidgets/QColorDialog.html#PySide2.QtWidgets.PySide2.QtWidgets.QColorDialog.getColor
        if not color_out.isValid():
            color_out = color_in
        new_color_R = color_out.red()
        new_color_G = color_out.green()
        new_color_B = color_out.blue()
        # Here the query is reversed and modified, dropping the values() method, to allow SETTING the color in the legend.
        parent.others_legend_df.loc[
            (parent.others_legend_df["other_collection"] == other_collection), "color_R"
        ] = new_color_R
        parent.others_legend_df.loc[
            (parent.others_legend_df["other_collection"] == other_collection), "color_G"
        ] = new_color_G
        parent.others_legend_df.loc[
            (parent.others_legend_df["other_collection"] == other_collection), "color_B"
        ] = new_color_B
        # Update sender color.
        # self.sender().setStyleSheet(
        #     "background-color:rgb({},{},{})".format(
        #         new_color_R, new_color_G, new_color_B
        #     )
        # )
        sender.setStyleSheet(
            "background-color:rgb({},{},{})".format(
                new_color_R, new_color_G, new_color_B
            )
        )
        # Signals to update actors in windows. This is emitted only for the modified uid under the 'color' key.
        if other_collection == "XSection":
            parent.signals.legend_color_modified.emit(
                parent.xsect_coll.df["uid"].tolist(),
                parent.xsect_coll,
            )

        elif other_collection == "DOM":
            parent.signals.legend_color_modified.emit(
                parent.dom_coll.df["uid"].tolist(),
                parent.dom_coll,
            )

        elif other_collection == "Mesh3D":
            parent.signals.legend_color_modified.emit(
                parent.mesh3d_coll.df["uid"].tolist(),
                parent.mesh3d_coll,
            )

        elif other_collection == "Boundary":
            parent.signals.legend_color_modified.emit(
                parent.boundary_coll.df["uid"].tolist(), parent.boundary_coll
            )
        elif other_collection == "Wells":
            parent.signals.legend_color_modified.emit(
                parent.well_coll.df["uid"].tolist(),
                parent.well_coll,
            )

    def change_other_feature_line_thick(self, sender=None, parent=None):
        # other_collection = self.sender().other_collection
        # line_thick = self.sender().value()
        other_collection = sender.other_collection
        line_thick = sender.value()
        # Here the query is reversed and modified, dropping the values() method, to allow SETTING the line thickness in the legend
        parent.others_legend_df.loc[
            (parent.others_legend_df["other_collection"] == other_collection),
            "line_thick",
        ] = line_thick
        # Signals to update actors in windows. This is emitted only for the modified uid under the 'color' key.
        if other_collection == "XSection":
            parent.signals.legend_thick_modified.emit(
                parent.xsect_coll.df["uid"].tolist(),
                parent.xsect_coll,
            )
        elif other_collection == "DOM":
            parent.signals.legend_thick_modified.emit(
                parent.dom_coll.df["uid"].tolist(),
                parent.dom_coll,
            )
        elif other_collection == "Mesh3D":
            parent.signals.legend_thick_modified.emit(
                parent.dom_coll.df["uid"].tolist(),
                parent.mesh3d_coll,
            )
        elif other_collection == "Boundary":
            parent.signals.legend_thick_modified.emit(
                parent.boundary_coll.df["uid"].tolist(), parent.boundary_coll
            )
        elif other_collection == "Wells":
            parent.signals.legend_thick_modified.emit(
                parent.well_coll.df["uid"].tolist(),
                parent.well_coll,
            )

    def change_other_feature_point_size(self, sender=None, parent=None):
        # other_collection = self.sender().other_collection
        # point_size = self.sender().value()
        other_collection = sender.other_collection
        point_size = sender.value()
        # Here the query is reversed and modified, dropping the values() method, to allow SETTING the line thickness in the legend
        parent.others_legend_df.loc[
            (parent.others_legend_df["other_collection"] == other_collection),
            "point_size",
        ] = point_size
        # Signals to update actors in windows. This is emitted only for the modified uid under the 'color' key.
        # if other_collection == "XSection":
        #     parent.xsect_legend_point_size_modified_signal.emit(parent.xsect_coll.df['uid'].tolist())
        if other_collection == "DOM":
            parent.signals.legend_point_size_modified.emit(
                parent.dom_coll.df["uid"].tolist(),
                parent.dom_coll,
            )
        # elif other_collection == "Mesh3D":
        #     parent.mesh3d_legend_point_size_modified_signal.emit(parent.dom_coll.df['uid'].tolist())
        # elif other_collection == "Boundary":
        #     parent.boundary_legend_point_size_modified_signal.emit(parent.boundary_coll.df['uid'].tolist())

    def change_other_feature_opacity(self, sender=None, parent=None):
        # other_collection = self.sender().other_collection
        # opacity = self.sender().value()
        other_collection = sender.other_collection
        opacity = sender.value()
        # Here the query is reversed and modified, dropping the values() method, to allow SETTING the line thickness in the legend
        parent.others_legend_df.loc[
            (parent.others_legend_df["other_collection"] == other_collection), "opacity"
        ] = opacity
        # Signals to update actors in windows. This is emitted only for the modified uid under the 'color' key.
        if other_collection == "XSection":
            parent.signals.legend_opacity_modified.emit(
                parent.xsect_coll.df["uid"].tolist(),
                parent.xsect_coll,
            )
        elif other_collection == "DOM":
            parent.signals.legend_opacity_modified.emit(
                parent.dom_coll.df["uid"].tolist(),
                parent.dom_coll,
            )
        elif other_collection == "Mesh3D":
            parent.signals.legend_opacity_modified.emit(
                parent.mesh3d_coll.df["uid"].tolist(),
                parent.mesh3d_coll,
            )
        elif other_collection == "Boundary":
            parent.signals.legend_opacity_modified.emit(
                parent.boundary_coll.df["uid"].tolist(),
                parent.boundary_coll,
            )
        elif other_collection == "Image":
            parent.signals.legend_opacity_modified.emit(
                parent.image_coll.df["uid"].tolist(),
                parent.image_coll,
            )
        elif other_collection == "Wells":
            parent.signals.legend_opacity_modified.emit(
                parent.well_coll.df["uid"].tolist(),
                parent.well_coll,
            )

    def change_fluid_feature_color(self, sender=None, parent=None):
        # role = self.sender().role
        # feature = self.sender().feature
        # scenario = self.sender().scenario
        role = sender.role
        feature = sender.feature
        scenario = sender.scenario
        # Here we use the same query as above to GET the color from the legend
        old_color_R = parent.fluid_coll.legend_df.loc[
            (parent.fluid_coll.legend_df["role"] == role)
            & (parent.fluid_coll.legend_df["feature"] == feature)
            & (parent.fluid_coll.legend_df["scenario"] == scenario),
            "color_R",
        ].values[0]
        old_color_G = parent.fluid_coll.legend_df.loc[
            (parent.fluid_coll.legend_df["role"] == role)
            & (parent.fluid_coll.legend_df["feature"] == feature)
            & (parent.fluid_coll.legend_df["scenario"] == scenario),
            "color_G",
        ].values[0]
        old_color_B = parent.fluid_coll.legend_df.loc[
            (parent.fluid_coll.legend_df["role"] == role)
            & (parent.fluid_coll.legend_df["feature"] == feature)
            & (parent.fluid_coll.legend_df["scenario"] == scenario),
            "color_B",
        ].values[0]
        color_in = QColor(
            old_color_R, old_color_G, old_color_B
        )  # https://doc.qt.io/qtforpython/PySide2/QtGui/QColor.html#PySide2.QtGui.QColor
        color_out = QColorDialog.getColor(
            initial=color_in, title="Select color"
        )  # https://doc.qt.io/qtforpython/PySide2/QtWidgets/QColorDialog.html#PySide2.QtWidgets.PySide2.QtWidgets.QColorDialog.getColor
        if not color_out.isValid():
            color_out = color_in
        new_color_R = color_out.red()
        new_color_G = color_out.green()
        new_color_B = color_out.blue()
        # Here the query is reversed and modified, dropping the values() method, to allow SETTING the color in the legend.
        parent.fluid_coll.legend_df.loc[
            (parent.fluid_coll.legend_df["role"] == role)
            & (parent.fluid_coll.legend_df["feature"] == feature)
            & (parent.fluid_coll.legend_df["scenario"] == scenario),
            "color_R",
        ] = new_color_R
        parent.fluid_coll.legend_df.loc[
            (parent.fluid_coll.legend_df["role"] == role)
            & (parent.fluid_coll.legend_df["feature"] == feature)
            & (parent.fluid_coll.legend_df["scenario"] == scenario),
            "color_G",
        ] = new_color_G
        parent.fluid_coll.legend_df.loc[
            (parent.fluid_coll.legend_df["role"] == role)
            & (parent.fluid_coll.legend_df["feature"] == feature)
            & (parent.fluid_coll.legend_df["scenario"] == scenario),
            "color_B",
        ] = new_color_B
        # Update sender color.
        # self.sender().setStyleSheet(
        sender.setStyleSheet(
            "background-color:rgb({},{},{})".format(
                new_color_R, new_color_G, new_color_B
            )
        )
        # Signal to update actors in windows. This is emitted only for the modified uid under the 'color' key.
        updated_list = parent.fluid_coll.df.loc[
            (parent.fluid_coll.df["role"] == role)
            & (parent.fluid_coll.df["feature"] == feature)
            & (parent.fluid_coll.df["scenario"] == scenario),
            "uid",
        ].to_list()
        parent.signals.legend_color_modified.emit(updated_list, parent.fluid_coll)
        # self.change_fluid_feature_color(parent) #Update the fluids

    def change_fluid_feature_line_thick(self, sender=None, parent=None):
        # role = self.sender().role
        # feature = self.sender().feature
        # scenario = self.sender().scenario
        # line_thick = self.sender().value()
        role = sender.role
        feature = sender.feature
        scenario = sender.scenario
        line_thick = sender.value()
        # Here the query is reversed and modified, dropping the values() method, to allow SETTING the line thickness in the legend
        parent.fluid_coll.legend_df.loc[
            (parent.fluid_coll.legend_df["role"] == role)
            & (parent.fluid_coll.legend_df["feature"] == feature)
            & (parent.fluid_coll.legend_df["scenario"] == scenario),
            "line_thick",
        ] = line_thick
        # Signal to update actors in windows. This is emitted only for the modified uid under the 'line_thick' key.
        updated_list = parent.fluid_coll.df.loc[
            (parent.fluid_coll.df["role"] == role)
            & (parent.fluid_coll.df["feature"] == feature)
            & (parent.fluid_coll.df["scenario"] == scenario),
            "uid",
        ].to_list()
        parent.signals.legend_thick_modified.emit(updated_list, parent.fluid_coll)

    def change_fluid_feature_point_size(self, sender=None, parent=None):
        # role = self.sender().role
        # feature = self.sender().feature
        # scenario = self.sender().scenario
        # point_size = self.sender().value()
        role = sender.role
        feature = sender.feature
        scenario = sender.scenario
        point_size = sender.value()
        # Here the query is reversed and modified, dropping the values() method, to allow SETTING the line thickness in the legend
        parent.fluid_coll.legend_df.loc[
            (parent.fluid_coll.legend_df["role"] == role)
            & (parent.fluid_coll.legend_df["feature"] == feature)
            & (parent.fluid_coll.legend_df["scenario"] == scenario),
            "point_size",
        ] = point_size
        # Signal to update actors in windows. This is emitted only for the modified uid under the 'line_thick' key.
        updated_list = parent.fluid_coll.df.loc[
            (parent.fluid_coll.df["role"] == role)
            & (parent.fluid_coll.df["feature"] == feature)
            & (parent.fluid_coll.df["scenario"] == scenario),
            "uid",
        ].to_list()
        parent.signals.legend_point_size_modified.emit(updated_list, parent.fluid_coll)

    def change_fluid_feature_opacity(self, sender=None, parent=None):
        # role = self.sender().role
        # feature = self.sender().feature
        # scenario = self.sender().scenario
        # opacity = self.sender().value()
        role = sender.role
        feature = sender.feature
        scenario = sender.scenario
        opacity = sender.value()
        # Here the query is reversed and modified, dropping the values() method, to allow SETTING the line thickness in the legend
        parent.fluid_coll.legend_df.loc[
            (parent.fluid_coll.legend_df["role"] == role)
            & (parent.fluid_coll.legend_df["feature"] == feature)
            & (parent.fluid_coll.legend_df["scenario"] == scenario),
            "opacity",
        ] = opacity
        # Signal to update actors in windows. This is emitted only for the modified uid under the 'line_thick' key.
        updated_list = parent.fluid_coll.df.loc[
            (parent.fluid_coll.df["role"] == role)
            & (parent.fluid_coll.df["feature"] == feature)
            & (parent.fluid_coll.df["scenario"] == scenario),
            "uid",
        ].to_list()
        parent.signals.legend_opacity_modified.emit(updated_list, parent.fluid_coll)

    def change_fluid_level(self, sender=None, parent=None):
        role = sender.role
        feature = sender.feature
        scenario = sender.scenario
        level = sender.value()
        parent.fluid_coll.legend_df.loc[
            (parent.fluid_coll.legend_df["role"] == role)
            & (parent.fluid_coll.legend_df["feature"] == feature)
            & (parent.fluid_coll.legend_df["scenario"] == scenario),
            legend_level_col,
        ] = level
        parent.fluid_coll.legend_df.sort_values(
            by=legend_level_col, ascending=True, inplace=True
        )

    def change_background_feature_color(self, sender=None, parent=None):
        # role = self.sender().role
        # feature = self.sender().feature
        role = sender.role
        feature = sender.feature
        # Here we use the same query as above to GET the color from the legend
        old_color_R = parent.backgrnd_coll.legend_df.loc[
            (parent.backgrnd_coll.legend_df["role"] == role)
            & (parent.backgrnd_coll.legend_df["feature"] == feature),
            "color_R",
        ].values[0]
        old_color_G = parent.backgrnd_coll.legend_df.loc[
            (parent.backgrnd_coll.legend_df["role"] == role)
            & (parent.backgrnd_coll.legend_df["feature"] == feature),
            "color_G",
        ].values[0]
        old_color_B = parent.backgrnd_coll.legend_df.loc[
            (parent.backgrnd_coll.legend_df["role"] == role)
            & (parent.backgrnd_coll.legend_df["feature"] == feature),
            "color_B",
        ].values[0]
        color_in = QColor(
            old_color_R, old_color_G, old_color_B
        )  # https://doc.qt.io/qtforpython/PySide2/QtGui/QColor.html#PySide2.QtGui.QColor
        color_out = QColorDialog.getColor(
            initial=color_in, title="Select color"
        )  # https://doc.qt.io/qtforpython/PySide2/QtWidgets/QColorDialog.html#PySide2.QtWidgets.PySide2.QtWidgets.QColorDialog.getColor
        if not color_out.isValid():
            color_out = color_in
        new_color_R = color_out.red()
        new_color_G = color_out.green()
        new_color_B = color_out.blue()
        # Here the query is reversed and modified, dropping the values() method, to allow SETTING the color in the legend.
        parent.backgrnd_coll.legend_df.loc[
            (parent.backgrnd_coll.legend_df["role"] == role)
            & (parent.backgrnd_coll.legend_df["feature"] == feature),
            "color_R",
        ] = new_color_R
        parent.backgrnd_coll.legend_df.loc[
            (parent.backgrnd_coll.legend_df["role"] == role)
            & (parent.backgrnd_coll.legend_df["feature"] == feature),
            "color_G",
        ] = new_color_G
        parent.backgrnd_coll.legend_df.loc[
            (parent.backgrnd_coll.legend_df["role"] == role)
            & (parent.backgrnd_coll.legend_df["feature"] == feature),
            "color_B",
        ] = new_color_B
        # Update sender color.
        # self.sender().setStyleSheet(
        #     "background-color:rgb({},{},{})".format(
        #         new_color_R, new_color_G, new_color_B
        #     )
        # )
        sender.setStyleSheet(
            "background-color:rgb({},{},{})".format(
                new_color_R, new_color_G, new_color_B
            )
        )
        # Signal to update actors in windows. This is emitted only for the modified uid under the 'color' key.
        updated_list = parent.backgrnd_coll.df.loc[
            (parent.backgrnd_coll.df["role"] == role)
            & (parent.backgrnd_coll.df["feature"] == feature),
            "uid",
        ].to_list()
        parent.signals.legend_color_modified.emit(updated_list, parent.backgrnd_coll)

    def change_background_feature_line_thick(self, sender=None, parent=None):
        # role = self.sender().role
        # feature = self.sender().feature
        # line_thick = self.sender().value()
        role = sender.role
        feature = sender.feature
        line_thick = sender.value()
        # Here the query is reversed and modified, dropping the values() method, to allow SETTING the line thickness in the legend
        parent.backgrnd_coll.legend_df.loc[
            (parent.backgrnd_coll.legend_df["role"] == role)
            & (parent.backgrnd_coll.legend_df["feature"] == feature),
            "line_thick",
        ] = line_thick
        # Signal to update actors in windows. This is emitted only for the modified uid under the 'line_thick' key.
        updated_list = parent.backgrnd_coll.df.loc[
            (parent.backgrnd_coll.df["role"] == role)
            & (parent.backgrnd_coll.df["feature"] == feature),
            "uid",
        ].to_list()
        parent.signals.legend_thick_modified.emit(updated_list, parent.backgrnd_coll)

    def change_background_feature_point_size(self, sender=None, parent=None):
        # role = self.sender().role
        # feature = self.sender().feature
        # point_size = self.sender().value()
        role = sender.role
        feature = sender.feature
        point_size = sender.value()
        # Here the query is reversed and modified, dropping the values() method, to allow SETTING the line thickness in the legend
        parent.backgrnd_coll.legend_df.loc[
            (parent.backgrnd_coll.legend_df["role"] == role)
            & (parent.backgrnd_coll.legend_df["feature"] == feature),
            "point_size",
        ] = point_size
        # Signal to update actors in windows. This is emitted only for the modified uid under the 'line_thick' key.
        updated_list = parent.backgrnd_coll.df.loc[
            (parent.backgrnd_coll.df["role"] == role)
            & (parent.backgrnd_coll.df["feature"] == feature),
            "uid",
        ].to_list()
        parent.signals.legend_point_size_modified.emit(
            updated_list, parent.backgrnd_coll
        )

    def change_background_opacity(self, sender=None, parent=None):
        # role = self.sender().role
        # feature = self.sender().feature
        # opacity = self.sender().value()
        role = sender.role
        feature = sender.feature
        opacity = sender.value()
        # Here the query is reversed and modified, dropping the values() method, to allow SETTING the opacity in the legend
        parent.backgrnd_coll.legend_df.loc[
            (parent.backgrnd_coll.legend_df["role"] == role)
            & (parent.backgrnd_coll.legend_df["feature"] == feature),
            "opacity",
        ] = opacity
        # Signal to update actors in windows. This is emitted only for the modified uid under the 'line_thick' key.
        updated_list = parent.backgrnd_coll.df.loc[
            (parent.backgrnd_coll.df["role"] == role)
            & (parent.backgrnd_coll.df["feature"] == feature),
            "uid",
        ].to_list()
        parent.signals.legend_opacity_modified.emit(updated_list, parent.backgrnd_coll)

    # def change_geological_sequence(self, parent=None):
    #     role = self.sender().role
    #     feature = self.sender().feature
    #     scenario = self.sender().scenario
    #     geol_seqn = self.sender().currentText()
    #     parent.geol_coll.legend_df.loc[(parent.geol_coll.legend_df['role'] == role) & (parent.geol_coll.legend_df['feature'] == feature) & (parent.geol_coll.legend_df['scenario'] == scenario), "sequence"] = geol_seqn
    #     """THE FOLLOWING MUST BE CHANGED IN A FOR LOOP OVER ALL ITEMS IN COLUMN 7
    #     parent.LegendTreeWidget.setItemWidget(llevel_3, 7, geol_sequence_combo)
    #     UPDATING THE VALUES AS IN
    #     geol_sequence_combo.addItems(parent.geol_coll.legend_df['sequence'].unique())"""
