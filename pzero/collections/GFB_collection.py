"""GFB_collection.py
PZero© Andrea Bistacchi"""

from uuid import uuid4

from copy import deepcopy

from numpy import ndarray as np_ndarray
from numpy import set_printoptions as np_set_printoptions
from numpy import round as np_round
from numpy import random as np_random

from pandas import DataFrame as pd_DataFrame
from pandas import set_option as pd_set_option
from pandas import unique as pd_unique
from pandas import concat as pd_concat

from vtkmodules.vtkCommonDataModel import vtkDataObject

from .AbstractCollection import BaseCollection


class GFBCollection(BaseCollection):
    """Intermediate abstract class used as a base for geological, fluid and background collections."""

    def __init__(self, parent=None, *args, **kwargs):
        super(GFBCollection, self).__init__(parent, *args, **kwargs)
        # Initialize properties required by the abstract superclass.
        self.entity_dict = {
            "uid": "",
            "name": "undef",
            "scenario": "undef",
            "x_section": "",  # this is the uid of the cross section for "XsVertexSet", "XsPolyLine", and "XsImage", empty for all others
            "topology": "undef",
            "vtk_obj": None,
            "role": "undef",
            "feature": "undef",
            "properties_names": [],
            "properties_components": [],
        }

        self.entity_dict_types = {
            "uid": str,
            "name": str,
            "scenario": str,
            "x_section": str,  # this is the uid of the cross section for "XsVertexSet", "XsPolyLine", and "XsImage", empty for all others
            "topology": str,
            "vtk_obj": object,
            "role": str,
            "feature": str,
            "properties_names": list,
            "properties_components": list,
        }

        self.valid_roles = []

        self.valid_topologies = [
            "VertexSet",
            "PolyLine",
            "TriSurf",
            "XsVertexSet",
            "XsPolyLine",
        ]

        self.editable_columns_names = ["name", "scenario", "role", "feature"]

        self.collection_name = ""

        self.default_sequence = ""

        self.initialize_df()

    # =================================== Obligatory methods ===========================================

    def add_entity_from_dict(
        self, entity_dict: pd_DataFrame = None, color: np_ndarray = None
    ):
        """Add an entity from a dictionary shaped as self.entity_dict."""
        # Create a new uid if it is not included in the dictionary.
        if not entity_dict["uid"]:
            entity_dict["uid"] = str(uuid4())
        # Append new row to dataframe. Note that the 'append()' method for Pandas dataframes DOES NOT
        # work in place, hence a NEW dataframe is created every time and then substituted to the old one.
        # Old and less efficient syntax used up to Pandas 1.5.3:
        # self.df = self.df.append(entity_dict, ignore_index=True)
        # New syntax with Pandas >= 2.0.0:
        self.df = pd_concat([self.df, pd_DataFrame([entity_dict])], ignore_index=True)
        # Reset data model.
        self.modelReset.emit()
        # Then add new role / feature / scenario to the legend if needed.
        # Note that for performance reasons this is done explicitly here, when adding an entity to the
        # collection, and not with a signal telling the legend to be updated by scanning the whole collection.
        role = entity_dict["role"]
        feature = entity_dict["feature"]
        scenario = entity_dict["scenario"]
        if self.legend_df.loc[
            (self.legend_df["role"] == role)
            & (self.legend_df["feature"] == feature)
            & (self.legend_df["scenario"] == scenario)
        ].empty:
            if color:
                R, G, B = color
            else:
                R, G, B = np_round(np_random.random(3) * 255)
            # Use default generic values for legend.
            # Old Pandas <= 1.5.3
            # self.legend_df = self.legend_df.append(
            #     {
            #         "role": role,
            #         "feature": feature,
            #         "time": 0.0,
            #         "sequence": self.default_sequence,
            #         "scenario": scenario,
            #         "color_R": R,
            #         "color_G": G,
            #         "color_B": B,
            #         "line_thick": 5.0,
            #         "point_size": 10.0,
            #         "opacity": 100,
            #     },
            #     ignore_index=True,
            # )
            # New Pandas >= 2.0.0
            self.legend_df = pd_concat(
                [
                    self.legend_df,
                    pd_DataFrame(
                        [
                            {
                                "role": role,
                                "feature": feature,
                                "time": 0.0,
                                "sequence": self.default_sequence,
                                "scenario": scenario,
                                "color_R": R,
                                "color_G": G,
                                "color_B": B,
                                "line_thick": 5.0,
                                "point_size": 10.0,
                                "opacity": 100,
                            }
                        ]
                    ),
                ],
                ignore_index=True,
            )
            self.parent.legend.update_widget(self.parent)
            self.parent.prop_legend.update_widget(self.parent)
        # Then emit signal to update the views. A list of uids is emitted, even if the
        # entity is just one, for future compatibility
        self.signals.entity_added.emit([entity_dict["uid"]])
        return entity_dict["uid"]

    def remove_entity(self, uid: str = None) -> str:
        """Remove an entity and its metadata."""
        # Remove row from dataframe and reset data model.
        if uid not in self.get_uids:
            return
        self.df.drop(self.df[self.df["uid"] == uid].index, inplace=True)
        self.modelReset.emit()  # is this really necessary?
        # Then remove role / feature / scenario from legend if needed.
        # legend_updated is used to record if the table is updated or not.
        # Note that for performance reasons this is done explicitly here, when adding an entity to the
        # collection, and not with a signal telling the legend to be updated by scanning the whole collection.
        legend_updated = self.remove_unused_from_legend()
        # When done, if the table was updated update the widget, and in any case send the signal over to the views.
        if legend_updated:
            self.parent.legend.update_widget(self.parent)
            self.parent.prop_legend.update_widget(self.parent)
        # A list of uids is emitted, even if the entity is just one
        self.signals.entities_removed.emit([uid])
        return uid

    def clone_entity(self, uid: str = None) -> str:
        """Clone an entity."""
        # Take care since add_entity_from_dict sends signals immediately.
        # First check whether the uid to be cloned exists.
        self.print_terminal("debug")
        if uid not in self.get_uids:
            return
        # Ten deep-copy the base disctionary, copy parameters and the VTK object, and create new entity.
        # ====== CAN BE UNIFIED AS COMMON METHOD OF THE ABSTRACT COLLECTION IF "GEOLOGICAL" METHODS WILL BE UNIFIED ====
        entity_dict = deepcopy(self.entity_dict)
        entity_dict["name"] = self.get_uid_name(uid)
        entity_dict["topology"] = self.get_uid_topology(uid)
        entity_dict["role"] = self.get_uid_role(uid)
        entity_dict["feature"] = self.get_uid_feature(uid)
        entity_dict["scenario"] = self.get_uid_scenario(uid)
        entity_dict["properties_names"] = self.get_uid_properties_names(uid)
        entity_dict["properties_components"] = self.get_uid_properties_components(uid)
        entity_dict["x_section"] = self.get_uid_x_section(uid)
        entity_dict["vtk_obj"] = self.get_uid_vtk_obj(uid).deep_copy()
        out_uid = self.add_entity_from_dict(entity_dict=entity_dict)
        return out_uid

    def replace_vtk(self, uid: str = None, vtk_object: vtkDataObject = None):
        """Replace the vtk object of a given uid with another vtkobject."""
        # ============ CAN BE UNIFIED AS COMMON METHOD OF THE ABSTRACT COLLECTION WHEN SIGNALS WILL BE UNIFIED ==========
        if isinstance(
            vtk_object, type(self.df.loc[self.df["uid"] == uid, "vtk_obj"].values[0])
        ):
            # Replace old properties names and components with new ones
            keys = vtk_object.point_data_keys
            self.df.loc[self.df["uid"] == uid, "properties_names"].values[0] = []
            self.df.loc[self.df["uid"] == uid, "properties_components"].values[0] = []
            for key in keys:
                components = vtk_object.get_point_data_shape(key)[1]
                current_names = pd_DataFrame(
                    self.df.loc[self.df["uid"] == uid, "properties_names"].values[0]
                )
                current_names = pd_concat(
                    [current_names, pd_DataFrame([key])], ignore_index=True
                )
                self.df.loc[self.df["uid"] == uid, "properties_names"].values[0] = (
                    current_names[0].tolist()
                )
                current_components = pd_DataFrame(
                    self.df.loc[self.df["uid"] == uid, "properties_components"].values[
                        0
                    ]
                )
                current_components = pd_concat(
                    [current_components, pd_DataFrame([components])], ignore_index=True
                )
                self.df.loc[self.df["uid"] == uid, "properties_components"].values[
                    0
                ] = current_components[0].tolist()
            self.df.loc[self.df["uid"] == uid, "vtk_obj"] = vtk_object
            self.parent.prop_legend.update_widget(self.parent)
            self.signals.data_keys_modified.emit([uid])
            self.signals.geom_modified.emit([uid])
        else:
            self.parent.print_terminal("ERROR - replace_vtk with vtk of a different type not allowed.")

    def attr_modified_update_legend_table(self):
        """Update legend table when attributes are changed."""
        # First remove unused role / feature.
        # legend_updated is used to record if the table is updated or not.
        legend_updated = self.remove_unused_from_legend()
        # Then add new role / feature.
        for uid in self.df["uid"].to_list():
            role = self.df.loc[self.df["uid"] == uid, "role"].values[0]
            feature = self.df.loc[self.df["uid"] == uid, "feature"].values[0]
            scenario = self.df.loc[self.df["uid"] == uid, "scenario"].values[0]
            if self.legend_df.loc[
                (self.legend_df["role"] == role)
                & (self.legend_df["feature"] == feature)
                & (self.legend_df["scenario"] == scenario)
            ].empty:
                # Old Pandas <= 1.5.3
                # self.legend_df = self.legend_df.append(
                #     {
                #         "role": role,
                #         "feature": feature,
                #         "time": 0.0,
                #         "sequence": self.default_sequence,
                #         "scenario": scenario,
                #         "color_R": round(np_random.random() * 255),
                #         "color_G": round(np_random.random() * 255),
                #         "color_B": round(np_random.random() * 255),
                #         "line_thick": 2.0,
                #     },
                #     ignore_index=True,
                # )
                # New Pandas >= 2.0.0
                self.legend_df = pd_concat(
                    [
                        self.legend_df,
                        pd_DataFrame(
                            [
                                {
                                    "role": role,
                                    "feature": feature,
                                    "time": 0.0,
                                    "sequence": self.default_sequence,
                                    "scenario": scenario,
                                    "color_R": round(np_random.random() * 255),
                                    "color_G": round(np_random.random() * 255),
                                    "color_B": round(np_random.random() * 255),
                                    "line_thick": 2.0,
                                }
                            ]
                        ),
                    ],
                    ignore_index=True,
                )
                legend_updated = legend_updated or True
        # When done, if the table was updated, update the widget. No signal is sent here to the views.
        if legend_updated:
            self.parent.legend.update_widget(self.parent)

    def remove_unused_from_legend(self):
        """Remove unused roles / features from a legend table."""
        # legend_updated is used to record if the table is updated or not.
        legend_updated = False
        roles_in_legend = pd_unique(self.legend_df["role"])
        features_in_legend = pd_unique(self.legend_df["feature"])
        scenarios_in_legend = pd_unique(self.legend_df["scenario"])
        for role in roles_in_legend:
            if self.df.loc[self.df["role"] == role].empty:
                # Get index of row to be removed, then remove it in place with .drop().
                idx_remove = self.legend_df[self.legend_df["role"] == role].index
                self.legend_df.drop(idx_remove, inplace=True)
                legend_updated = legend_updated or True
            for feature in features_in_legend:
                if self.df.loc[
                    (self.df["role"] == role) & (self.df["feature"] == feature)
                ].empty:
                    # Get index of row to be removed, then remove it in place with .drop().
                    idx_remove = self.legend_df[
                        (self.legend_df["role"] == role)
                        & (self.legend_df["feature"] == feature)
                    ].index
                    self.legend_df.drop(idx_remove, inplace=True)
                    legend_updated = legend_updated or True
                for scenario in scenarios_in_legend:
                    if self.df.loc[
                        (self.df["role"] == role)
                        & (self.df["feature"] == feature)
                        & (self.df["scenario"] == scenario)
                    ].empty:
                        # Get index of row to be removed, then remove it in place with .drop().
                        idx_remove = self.legend_df[
                            (self.legend_df["role"] == role)
                            & (self.legend_df["feature"] == feature)
                            & (self.legend_df["scenario"] == scenario)
                        ].index
                        self.legend_df.drop(idx_remove, inplace=True)
                        legend_updated = legend_updated or True
        for feature in features_in_legend:
            if self.df.loc[self.df["feature"] == feature].empty:
                # Get index of row to be removed, then remove it in place with .drop().
                idx_remove = self.legend_df[self.legend_df["feature"] == feature].index
                self.legend_df.drop(idx_remove, inplace=True)
                legend_updated = legend_updated or True
            for scenario in scenarios_in_legend:
                if self.df.loc[
                    (self.df["feature"] == feature) & (self.df["scenario"] == scenario)
                ].empty:
                    # Get index of row to be removed, then remove it in place with .drop().
                    idx_remove = self.legend_df[
                        (self.legend_df["feature"] == feature)
                        & (self.legend_df["scenario"] == scenario)
                    ].index
                    self.legend_df.drop(idx_remove, inplace=True)
                    legend_updated = legend_updated or True
        for scenario in scenarios_in_legend:
            if self.df.loc[self.df["scenario"] == scenario].empty:
                # Get index of row to be removed, then remove it in place with .drop().
                idx_remove = self.legend_df[
                    self.legend_df["scenario"] == scenario
                ].index
                self.legend_df.drop(idx_remove, inplace=True)
                legend_updated = legend_updated or True
        return legend_updated

    def get_uid_legend(self, uid: str = None) -> dict:
        """Get legend for a particular uid."""
        role = self.df.loc[self.df["uid"] == uid, "role"].values[0]
        feature = self.df.loc[self.df["uid"] == uid, "feature"].values[0]
        scenario = self.df.loc[self.df["uid"] == uid, "scenario"].values[0]
        legend_dict = self.legend_df.loc[
            (self.legend_df["role"] == role)
            & (self.legend_df["feature"] == feature)
            & (self.legend_df["scenario"] == scenario)
        ].to_dict("records")
        return legend_dict[
            0
        ]  # the '[0]' is needed since .to_dict('records') returns a list of dictionaries (with just one element in this case)

    def set_uid_legend(
        self,
        uid: str = None,
        color_R: float = None,
        color_G: float = None,
        color_B: float = None,
        line_thick: float = None,
        point_size: float = None,
        opacity: float = None,
    ):
        """Set the legend for a particular uid."""
        # ==== AT THE MOEMENT THIS IS USED JUST WHEN IMPORTING GOCAD ASCII FILES WITH A RECORDED LEGEND. ==========
        # ==== IN THE FUTURE SEE IF IT IS POSSIBLE TO USE THIS IN add_entity_from_dict ============================
        legend_dict = self.get_uid_legend(uid)
        if isinstance(color_R, float):
            if 0.0 <= color_R <= 255.0:
                self.legend_df.loc[
                    (self.legend_df["role"] == legend_dict["role"])
                    & (self.legend_df["feature"] == legend_dict["feature"])
                    & (self.legend_df["scenario"] == legend_dict["scenario"]),
                    "color_R",
                ] = color_R
        if isinstance(color_G, float):
            if 0.0 <= color_G <= 255.0:
                self.legend_df.loc[
                    (self.legend_df["role"] == legend_dict["role"])
                    & (self.legend_df["feature"] == legend_dict["feature"])
                    & (self.legend_df["scenario"] == legend_dict["scenario"]),
                    "color_G",
                ] = color_G
        if isinstance(color_B, float):
            if 0.0 <= color_B <= 255.0:
                self.legend_df.loc[
                    (self.legend_df["role"] == legend_dict["role"])
                    & (self.legend_df["feature"] == legend_dict["feature"])
                    & (self.legend_df["scenario"] == legend_dict["scenario"]),
                    "color_B",
                ] = color_B
        if isinstance(line_thick, float):
            if line_thick >= 0.0:
                self.legend_df.loc[
                    (self.legend_df["role"] == legend_dict["role"])
                    & (self.legend_df["feature"] == legend_dict["feature"])
                    & (self.legend_df["scenario"] == legend_dict["scenario"]),
                    "line_thick",
                ] = line_thick
        if isinstance(point_size, float):
            if point_size >= 0.0:
                self.legend_df.loc[
                    (self.legend_df["role"] == legend_dict["role"])
                    & (self.legend_df["feature"] == legend_dict["feature"])
                    & (self.legend_df["scenario"] == legend_dict["scenario"]),
                    "point_size",
                ] = point_size
        if isinstance(opacity, float):
            if 0.0 <= opacity <= 100.0:
                self.legend_df.loc[
                    (self.legend_df["role"] == legend_dict["role"])
                    & (self.legend_df["feature"] == legend_dict["feature"])
                    & (self.legend_df["scenario"] == legend_dict["scenario"]),
                    "opacity",
                ] = opacity

    def get_role_uids(self, role: str = None) -> list:
        """Get list of uids with a given role in a given collection."""
        # ====== in the future use the query method? ========================================
        return self.df.loc[self.df["role"] == role, "uid"].to_list()

    def get_uid_role(self, uid: str = None):
        """Get role of a given uid."""
        return self.df.loc[self.df["uid"] == uid, "role"].values[0]

    def set_uid_role(self, uid=None, role=None):
        """Set role of a given uid."""
        self.df.loc[self.df["uid"] == uid, "role"] = role

    def get_feature_uids(self, coll_feature: str = None) -> list:
        """Get list of uids of a given collection feature."""
        # ====== in the future use the query method? ========================================
        return self.df.loc[self.df["feature"] == coll_feature, "uid"].to_list()

    def get_uid_feature(self, uid: str = None):
        """Get collection type from uid."""
        return self.df.loc[self.df["uid"] == uid, "feature"].values[0]

    def set_uid_feature(self, uid=None, feature=None):
        """Set collection type from uid."""
        self.df.loc[self.df["uid"] == uid, "feature"] = feature
