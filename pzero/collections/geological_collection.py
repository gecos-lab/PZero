"""geological_collection.py
PZero© Andrea Bistacchi"""

import uuid
from copy import deepcopy

from PyQt5.QtCore import QAbstractTableModel, Qt, QVariant
from numpy import random as np_random, ndarray
from numpy import round as np_round
from numpy import set_printoptions as np_set_set_printoptions
from pandas import DataFrame as pd_DataFrame, DataFrame
from pandas import set_option as pd_set_option
from pandas import unique as pd_unique
from vtkmodules.vtkCommonDataModel import vtkDataObject

from .AbstractCollection import BaseCollection

"""Options to print Pandas dataframes in console when testing."""
pd_desired_width = 800
pd_max_columns = 20
pd_show_precision = 4
pd_max_colwidth = 80
pd_set_option("display.width", pd_desired_width)
np_set_set_printoptions(linewidth=pd_desired_width)
pd_set_option("display.max_columns", pd_max_columns)
pd_set_option("display.precision", pd_show_precision)
pd_set_option("display.max_colwidth", pd_max_colwidth)


class GeologicalCollection(BaseCollection):
    """Collection for all geological entities and their metadata."""
    def __init__(self, parent=None, *args, **kwargs):
        super(GeologicalCollection, self).__init__(parent, *args, **kwargs)

        # Initialize properties required by the abstract superclass.
        self.entity_dict = {
            "uid": "",
            "name": "undef",
            "topological_type": "undef",
            "geological_type": "undef",
            "geological_feature": "undef",
            "scenario": "undef",
            "properties_names": [],
            "properties_components": [],
            "x_section": "",  # this is the uid of the cross section for "XsVertexSet", "XsPolyLine", and "XsImage", empty for all others
            "vtk_obj": None,
        }

        self.entity_type_dict = {
            "uid": str,
            "name": str,
            "topological_type": str,
            "geological_type": str,
            "geological_feature": str,
            "scenario": str,
            "properties_names": list,
            "properties_components": list,
            "x_section": str,
            "vtk_obj": object,
        }

        self.valid_types = [
            "undef",
            "fault",
            "tectonic",
            "intrusive",
            "unconformity",
            "top",
            "bedding",
            "foliation",
            "lineation",
            "axial_surface",
            "fold_axis",
        ]

        self.valid_topological_types = [
            "VertexSet",
            "PolyLine",
            "TriSurf",
            "XsVertexSet",
            "XsPolyLine",
        ]

        self.editable_columns_names = ["name", "geological_type", "geological_feature", "scenario"]

        self.collection_name = 'geological'

        self.initialize_df()

    # =================================== Obligatory methods ===========================================

    def add_entity_from_dict(self, entity_dict: DataFrame = None, color: ndarray = None):
        """Add a entity from a dictionary shaped as self.entity_dict."""
        # Create a new uid if it is not included in the dictionary.
        if not entity_dict["uid"]:
            entity_dict["uid"] = str(uuid.uuid4())
        # Append new row to dataframe. Note that the 'append()' method for Pandas dataframes DOES NOT
        # work in place, hence a NEW dataframe is created every time and then substituted to the old one.
        self.df = self.df.append(entity_dict, ignore_index=True)
        # Reset data model.
        self.modelReset.emit()
        # Then add new type / feature / scenario to the legend if needed.
        # Note that for performance reasons this is done explicitly here, when adding an entity to the
        # collection, and not with a signal telling the legend to be updated by scanning the whole collection.
        geo_type = entity_dict["geological_type"]
        feature = entity_dict["geological_feature"]
        scenario = entity_dict["scenario"]
        if self.parent.geol_legend_df.loc[
            (self.parent.geol_legend_df["geological_type"] == geo_type)
            & (self.parent.geol_legend_df["geological_feature"] == feature)
            & (self.parent.geol_legend_df["scenario"] == scenario)
        ].empty:
            if color:
                R, G, B = color
            else:
                R, G, B = np_round(np_random.random(3) * 255)
            # Use default generic values for legend.
            self.parent.geol_legend_df = self.parent.geol_legend_df.append(
                {
                    "geological_type": geo_type,
                    "geological_feature": feature,
                    "scenario": scenario,
                    "color_R": R,
                    "color_G": G,
                    "color_B": B,
                    "line_thick": 5.0,                    "point_size": 10.0,
                    "opacity": 100,
                    "geological_time": 0.0,
                    "geological_sequence": "strati_0",
                },
                ignore_index=True,
            )
            self.parent.legend.update_widget(self.parent)
            self.parent.prop_legend.update_widget(self.parent)
        # Then emit signal to update the views. A list of uids is emitted, even if the
        # entity is just one, for future compatibility
        self.parent.geology_added_signal.emit(
            [entity_dict["uid"]]
        )
        return entity_dict["uid"]

    def remove_entity(self, uid: str = None) -> str:
        """Remove an entity and its metadata."""
        # Remove row from dataframe and reset data model.
        if uid not in self.get_uids:
            return
        self.df.drop(self.parent.geol_coll.df[self.parent.geol_coll.df["uid"] == uid].index, inplace=True)
        self.modelReset.emit()  # is this really necessary?
        # Then remove type / feature / scenario from legend if needed.
        # legend_updated is used to record if the table is updated or not.
        # Note that for performance reasons this is done explicitly here, when adding an entity to the
        # collection, and not with a signal telling the legend to be updated by scanning the whole collection.
        legend_updated = self.remove_unused_from_legend()
        """When done, if the table was updated update the widget, and in any case send the signal over to the views."""
        if legend_updated:
            self.parent.legend.update_widget(self.parent)
            self.parent.prop_legend.update_widget(self.parent)
        # A list of uids is emitted, even if the entity is just one
        self.parent.geology_removed_signal.emit([uid])
        return uid

    def clone_entity(self, uid: str = None) -> str:
        """Clone an entity."""
        # Take care since add_entity_from_dict sends signals immediately.
        # First check whether the uid to be cloned exists.
        if uid not in self.get_uids:
            return
        # Ten deep-copy the base disctionary, copy parameters and the VTK object, and create new entity.
        # ====== CAN BE UNIFIED AS COMMON METHOD OF THE ABSTRACT COLLECTION IF "GEOLOGICAL" METHODS WILL BE UNIFIED ====
        entity_dict = deepcopy(self.entity_dict)
        entity_dict["name"] = self.get_uid_name(uid)
        entity_dict["topological_type"] = self.get_uid_topological_type(uid)
        entity_dict["geological_type"] = self.get_uid_geological_type(uid)
        entity_dict["geological_feature"] = self.get_uid_geological_feature(uid)
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
        if isinstance(vtk_object, type(self.df.loc[self.df["uid"] == uid, "vtk_obj"].values[0])):
            # Replace old properties names and components with new ones
            keys = vtk_object.point_data_keys
            self.df.loc[self.df["uid"] == uid, "properties_names"].values[0] = []
            self.df.loc[self.df["uid"] == uid, "properties_components"].values[0] = []
            for key in keys:
                components = vtk_object.get_point_data_shape(key)[1]
                self.df.loc[self.df["uid"] == uid, "properties_names"].append(key)
                self.df.loc[self.df["uid"] == uid, "properties_components"].append(components)
            self.df.loc[self.df["uid"] == uid, "vtk_obj"] = vtk_object
            self.parent.prop_legend.update_widget(self.parent)
            self.parent.geology_data_keys_modified_signal.emit([uid])
            self.parent.geology_geom_modified_signal.emit([uid])
        else:
            print("ERROR - replace_vtk with vtk of a different type not allowed.")

    def attr_modified_update_legend_table(self):
        """Update legend table when attributes are changed."""
        # First remove unused geo_type / feature.
        # legend_updated is used to record if the table is updated or not.
        legend_updated = self.remove_unused_from_legend()
        # Then add new geo_type / feature.
        for uid in self.parent.geol_coll.df["uid"].to_list():
            geo_type = self.parent.geol_coll.df.loc[
                self.parent.geol_coll.df["uid"] == uid, "geological_type"
            ].values[0]
            feature = self.parent.geol_coll.df.loc[
                self.parent.geol_coll.df["uid"] == uid, "geological_feature"
            ].values[0]
            scenario = self.parent.geol_coll.df.loc[
                self.parent.geol_coll.df["uid"] == uid, "scenario"
            ].values[0]
            if self.parent.geol_legend_df.loc[
                (self.parent.geol_legend_df["geological_type"] == geo_type)
                & (self.parent.geol_legend_df["geological_feature"] == feature)
                & (self.parent.geol_legend_df["scenario"] == scenario)
            ].empty:
                self.parent.geol_legend_df = self.parent.geol_legend_df.append(
                    {
                        "geological_type": geo_type,
                        "geological_feature": feature,
                        "scenario": scenario,
                        "color_R": round(np_random.random() * 255),
                        "color_G": round(np_random.random() * 255),
                        "color_B": round(np_random.random() * 255),
                        "line_thick": 2.0,
                        "geological_time": 0.0,
                        "geological_sequence": "strati_0",
                    },
                    ignore_index=True,
                )
                legend_updated = True
        # When done, if the table was updated, update the widget. No signal is sent here to the views.
        if legend_updated:
            self.parent.legend.update_widget(self.parent)

    def remove_unused_from_legend(self):
        """Remove unused types / features from a legend table."""
        # legend_updated is used to record if the table is updated or not.
        legend_updated = False
        geo_types_in_legend = pd_unique(self.parent.geol_legend_df["geological_type"])
        features_in_legend = pd_unique(self.parent.geol_legend_df["geological_feature"])
        scenarios_in_legend = pd_unique(self.parent.geol_legend_df["scenario"])
        for geo_type in geo_types_in_legend:
            if self.parent.geol_coll.df.loc[
                self.parent.geol_coll.df["geological_type"] == geo_type
            ].empty:
                # Get index of row to be removed, then remove it in place with .drop().
                idx_remove = self.parent.geol_legend_df[
                    self.parent.geol_legend_df["geological_type"] == geo_type
                    ].index
                self.parent.geol_legend_df.drop(idx_remove, inplace=True)
                legend_updated = legend_updated or True
            for feature in features_in_legend:
                if self.parent.geol_coll.df.loc[
                    (self.parent.geol_coll.df["geological_type"] == geo_type)
                    & (self.parent.geol_coll.df["geological_feature"] == feature)
                ].empty:
                    # Get index of row to be removed, then remove it in place with .drop().
                    idx_remove = self.parent.geol_legend_df[
                        (self.parent.geol_legend_df["geological_type"] == geo_type)
                        & (self.parent.geol_legend_df["geological_feature"] == feature)
                        ].index
                    self.parent.geol_legend_df.drop(idx_remove, inplace=True)
                    legend_updated = legend_updated or True
                for scenario in scenarios_in_legend:
                    if self.parent.geol_coll.df.loc[
                        (self.parent.geol_coll.df["geological_type"] == geo_type)
                        & (self.parent.geol_coll.df["geological_feature"] == feature)
                        & (self.parent.geol_coll.df["scenario"] == scenario)
                    ].empty:
                        # Get index of row to be removed, then remove it in place with .drop().
                        idx_remove = self.parent.geol_legend_df[
                            (self.parent.geol_legend_df["geological_type"] == geo_type)
                            & (
                                    self.parent.geol_legend_df["geological_feature"]
                                    == feature
                            )
                            & (self.parent.geol_legend_df["scenario"] == scenario)
                            ].index
                        self.parent.geol_legend_df.drop(idx_remove, inplace=True)
                        legend_updated = legend_updated or True
        for feature in features_in_legend:
            if self.parent.geol_coll.df.loc[
                self.parent.geol_coll.df["geological_feature"] == feature
            ].empty:
                # Get index of row to be removed, then remove it in place with .drop().
                idx_remove = self.parent.geol_legend_df[
                    self.parent.geol_legend_df["geological_feature"] == feature
                    ].index
                self.parent.geol_legend_df.drop(idx_remove, inplace=True)
                legend_updated = legend_updated or True
            for scenario in scenarios_in_legend:
                if self.parent.geol_coll.df.loc[
                    (self.parent.geol_coll.df["geological_feature"] == feature)
                    & (self.parent.geol_coll.df["scenario"] == scenario)
                ].empty:
                    # Get index of row to be removed, then remove it in place with .drop().
                    idx_remove = self.parent.geol_legend_df[
                        (self.parent.geol_legend_df["geological_feature"] == feature)
                        & (self.parent.geol_legend_df["scenario"] == scenario)
                        ].index
                    self.parent.geol_legend_df.drop(idx_remove, inplace=True)
                    legend_updated = legend_updated or True
        for scenario in scenarios_in_legend:
            if self.parent.geol_coll.df.loc[
                self.parent.geol_coll.df["scenario"] == scenario
            ].empty:
                # Get index of row to be removed, then remove it in place with .drop().
                idx_remove = self.parent.geol_legend_df[
                    self.parent.geol_legend_df["scenario"] == scenario
                    ].index
                self.parent.geol_legend_df.drop(idx_remove, inplace=True)
                legend_updated = legend_updated or True
        return legend_updated

    def get_uid_legend(self, uid: str = None) -> dict:
        """Get legend for a particular uid."""
        geo_type = self.df.loc[self.df["uid"] == uid, "geological_type"].values[0]
        feature = self.df.loc[self.df["uid"] == uid, "geological_feature"].values[0]
        scenario = self.df.loc[self.df["uid"] == uid, "scenario"].values[0]
        legend_dict = self.parent.geol_legend_df.loc[
            (self.parent.geol_legend_df["geological_type"] == geo_type)
            & (self.parent.geol_legend_df["geological_feature"] == feature)
            & (self.parent.geol_legend_df["scenario"] == scenario)
            ].to_dict("records")
        return legend_dict[0]  # the '[0]' is needed since .to_dict('records') returns a list of dictionaries (with just one element in this case)

    def set_uid_legend(self, uid: str = None, color_R: float = None, color_G: float = None, color_B: float = None,
                       line_thick: float = None, point_size: float = None, opacity: float = None):
        """Set the legend for a particular uid."""
        # ==== AT THE MOEMENT THIS IS USED JUST WHEN IMPORTING GOCAD ASCII FILES WITH A RECORDED LEGEND. ==========
        # ==== IN THE FUTURE SEE IF IT IS POSSIBLE TO USE THIS IN add_entity_from_dict ============================
        legend_dict = self.get_uid_legend(uid)
        if isinstance(color_R, float):
            if 0.0 <= color_R <= 255.0:
                self.parent.geol_legend_df.loc[
                    (self.parent.geol_legend_df["geological_type"] == legend_dict["geological_type"])
                    & (self.parent.geol_legend_df["geological_feature"] == legend_dict["geological_feature"])
                    & (self.parent.geol_legend_df["scenario"] == legend_dict["scenario"]),
                    "color_R",
                ] = color_R
        if isinstance(color_G, float):
            if 0.0 <= color_G <= 255.0:
                self.parent.geol_legend_df.loc[
                    (self.parent.geol_legend_df["geological_type"] == legend_dict["geological_type"])
                    & (self.parent.geol_legend_df["geological_feature"] == legend_dict["geological_feature"])
                    & (self.parent.geol_legend_df["scenario"] == legend_dict["scenario"]),
                    "color_G",
                ] = color_G
        if isinstance(color_B, float):
            if 0.0 <= color_B <= 255.0:
                self.parent.geol_legend_df.loc[
                    (self.parent.geol_legend_df["geological_type"] == legend_dict["geological_type"])
                    & (self.parent.geol_legend_df["geological_feature"] == legend_dict["geological_feature"])
                    & (self.parent.geol_legend_df["scenario"] == legend_dict["scenario"]),
                    "color_B",
                ] = color_B
        if isinstance(line_thick, float):
            if line_thick >= 0.0:
                self.parent.geol_legend_df.loc[
                    (self.parent.geol_legend_df["geological_type"] == legend_dict["geological_type"])
                    & (self.parent.geol_legend_df["geological_feature"] == legend_dict["geological_feature"])
                    & (self.parent.geol_legend_df["scenario"] == legend_dict["scenario"]),
                    "line_thick",
                ] = line_thick
        if isinstance(point_size, float):
            if point_size >= 0.0:
                self.parent.geol_legend_df.loc[
                    (self.parent.geol_legend_df["geological_type"] == legend_dict["geological_type"])
                    & (self.parent.geol_legend_df["geological_feature"] == legend_dict["geological_feature"])
                    & (self.parent.geol_legend_df["scenario"] == legend_dict["scenario"]),
                    "point_size",
                ] = point_size
        if isinstance(opacity, float):
            if 0.0 <= opacity <= 100.0:
                self.parent.geol_legend_df.loc[
                    (self.parent.geol_legend_df["geological_type"] == legend_dict["geological_type"])
                    & (self.parent.geol_legend_df["geological_feature"] == legend_dict["geological_feature"])
                    & (self.parent.geol_legend_df["scenario"] == legend_dict["scenario"]),
                    "opacity",
                ] = opacity

    def metadata_modified_signal(self, updated_list: list = None):
        self.parent.geology_metadata_modified_signal.emit(updated_list)

    def data_keys_modified_signal(self, updated_list: list = None):
        self.parent.geology_data_keys_modified_signal.emit(updated_list)

    # =================================== Additional methods ===========================================
    # ====== CAN BE UNIFIED AS COMMON METHOD OF THE ABSTRACT COLLECTION IF "GEOLOGICAL" METHODS WILL BE UNIFIED ====

    def get_type_uids(self, coll_type: str = None) -> list:
        """Get list of uids of a given collection type."""
        # ====== in the future use the query method? ========================================
        return self.df.loc[self.df[self.coll_type_name] == coll_type, "uid"].to_list()

    def get_uid_geological_type(self, uid: str = None):
        """Get collection type from uid."""
        return self.df.loc[self.df["uid"] == uid, self.coll_type_name].values[0]

    def set_uid_geological_type(self, uid=None, geological_type=None):
        """Set collection type from uid."""
        self.df.loc[self.df["uid"] == uid, self.coll_type_name] = geological_type

    def get_feature_uids(self, coll_feature: str = None) -> list:
        """Get list of uids of a given collection feature."""
        # ====== in the future use the query method? ========================================
        return self.df.loc[self.df[self.coll_feature_name] == coll_feature, "uid"].to_list()

    def get_uid_geological_feature(self, uid: str = None):
        """Get collection type from uid."""
        return self.df.loc[self.df["uid"] == uid, self.coll_feature_name].values[0]

    def set_uid_geological_feature(self, uid=None, geological_feature=None):
        """Set collection type from uid."""
        self.df.loc[self.df["uid"] == uid, self.coll_feature_name] = geological_feature
