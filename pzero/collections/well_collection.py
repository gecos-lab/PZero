"""well_collection.py
PZero© Andrea Bistacchi"""

import uuid
from copy import deepcopy

from PyQt5.QtCore import QAbstractTableModel, Qt, QVariant
from numpy import random as np_random, ndarray
from numpy import round as np_round
from pandas import DataFrame as pd_DataFrame, DataFrame
from pandas import unique as pd_unique
from vtkmodules.vtkCommonDataModel import vtkDataObject

from .AbstractCollection import BaseCollection


class WellCollection(BaseCollection):
    """Collection for all wells and their metadata."""
    def __init__(self, parent=None, *args, **kwargs):
        super(WellCollection, self).__init__(parent, *args, **kwargs)
        # Initialize properties required by the abstract superclass.
        self.entity_dict = {
            "uid": "",
            "Loc ID": "undef",
            "scenario": "undef",
            "properties_names": [],
            "properties_components": [],
            "properties_types": [],
            "markers": [],
            "x_section": [], # this is the uid of the cross section for "XsVertexSet", "XsPolyLine", and "XsImage", empty for all others
            "vtk_obj": None,
        }

        self.entity_type_dict = {
            "uid": str,
            "Loc ID": str,
            "scenario": str,
            "properties_names": list,
            "properties_components": list,
            "properties_types": list,
            "markers": list,
            "x_section": str,
            "vtk_obj": object,
        }

        self.valid_topologies = [
            "VertexSet",
            "PolyLine",
            "XsVertexSet",
            "XsPolyLine",
        ]

        self.editable_columns_names = ["name", "scenario"]

        self.collection_name = 'wells'

        self.initialize_df()

    def add_entity_from_dict(self, entity_dict: DataFrame = None, color: ndarray = None):
        """Add an entity from a dictionary shaped as self.entity_dict."""
        # Create a new uid if it is not included in the dictionary.
        if not entity_dict["uid"]:
            entity_dict["uid"] = str(uuid.uuid4())
        # Append new row to dataframe. Note that the 'append()' method for Pandas dataframes DOES NOT
        # work in place, hence a NEW dataframe is created every time and then substituted to the old one.
        self.df = self.df.append(entity_dict, ignore_index=True)
        # Reset data model.
        self.modelReset.emit()
        self.parent.prop_legend.update_widget(self.parent)
        # Then update the legend if needed.
        # Note that for performance reasons this is done explicitly here, when adding an entity to the
        # collection, and not with a signal telling the legend to be updated by scanning the whole collection.
        locid = entity_dict["Loc ID"]
        if self.parent.well_legend_df.loc[
            self.parent.well_legend_df["Loc ID"] == locid
        ].empty:
            R, G, B = np_round(np_random.random(3) * 255)
            self.parent.well_legend_df = self.parent.well_legend_df.append(
                {
                    "Loc ID": locid,
                    "color_R": R,
                    "color_G": G,
                    "color_B": B,
                    "line_thick": 2.0,
                    "opacity": 100,
                },
                ignore_index=True,
            )
            self.parent.legend.update_widget(self.parent)
            self.parent.prop_legend.update_widget(self.parent)
        # Then emit signal to update the views. A list of uids is emitted, even if the entity is just one.
        self.parent.well_added_signal.emit([entity_dict["uid"]])
        return entity_dict["uid"]

    def remove_entity(self, uid: str = None) -> str:
        """Remove an entity and its metadata."""
        # Remove row from dataframe and reset data model.
        self.df.drop(self.df[self.df["uid"] == uid].index, inplace=True)
        self.modelReset.emit()  # is this really necessary?
        self.parent.prop_legend.update_widget(self.parent)
        # When done, send a signal over to the views. A list of uids is emitted, even if the entity is just one.
        self.parent.well_removed_signal.emit([uid])
        return uid

    def clone_entity(self, uid: str = None) -> str:
        """Clone an entity."""
        # Not implemented for this collection, but required by the abstract superclass.
        pass

    def replace_vtk(self, uid: str = None, vtk_object: vtkDataObject = None):
        """Replace the vtk object of a given uid with another vtkobject."""
        # ============ CAN BE UNIFIED AS COMMON METHOD OF THE ABSTRACT COLLECTION WHEN SIGNALS WILL BE UNIFIED ==========
        # Not implemented for this collection, but required by the abstract superclass.
        pass

    def attr_modified_update_legend_table(self):
        """Update legend table when attributes are changed."""
        # First remove unused locid / feature.
        legend_updated = self.remove_unused_from_legend()
        # Then add new locid / feature.
        for uid in self.parent.well_coll.df["uid"].to_list():
            locid = self.parent.well_coll.df.loc[
                self.parent.well_coll.df["uid"] == uid, "Loc ID"
            ].values[0]
            feature = self.parent.well_coll.df.loc[
                self.parent.well_coll.df["uid"] == uid, "geological_feature"
            ].values[0]
            if self.parent.well_legend_df.loc[
                (self.parent.well_legend_df["Loc ID"] == locid)
                & (self.parent.well_legend_df["geological_feature"] == feature)
            ].empty:
                self.parent.well_legend_df = self.parent.well_legend_df.append(
                    {
                        "Loc ID": locid,
                        "geological_feature": feature,
                        "color_R": round(np_random.random() * 255),
                        "color_G": round(np_random.random() * 255),
                        "color_B": round(np_random.random() * 255),
                        "line_thick": 2.0,
                    },
                    ignore_index=True,
                )
                legend_updated = legend_updated or True
        # When done, if the table was updated update the widget. No signal is sent here to the views.
        if legend_updated:
            self.parent.legend.update_widget(self.parent)

    def remove_unused_from_legend(self):
        """Remove unused types / features from a legend table."""
        legend_updated = False
        locid_in_legend = pd_unique(self.parent.well_legend_df["Loc ID"])
        features_in_legend = pd_unique(self.parent.well_legend_df["geological_feature"])
        for loc_id in locid_in_legend:
            if self.parent.well_coll.df.loc[
                self.parent.well_coll.df["Loc ID"] == loc_id
            ].empty:
                # Get index of row to be removed, then remove it in place with .drop().
                idx_remove = self.parent.well_legend_df[
                    self.parent.well_legend_df["Loc ID"] == loc_id
                    ].index
                self.parent.well_legend_df.drop(idx_remove, inplace=True)
                legend_updated = legend_updated or True
            for feature in features_in_legend:
                if self.parent.well_coll.df.loc[
                    (self.parent.well_coll.df["Loc ID"] == loc_id)
                    & (self.parent.well_coll.df["geological_feature"] == feature)
                ].empty:
                    # Get index of row to be removed, then remove it in place with .drop().
                    idx_remove = self.parent.well_legend_df[
                        (self.parent.well_legend_df["Loc ID"] == loc_id)
                        & (self.parent.well_legend_df["geological_feature"] == feature)
                        ].index
                    self.parent.well_legend_df.drop(idx_remove, inplace=True)
                    legend_updated = legend_updated or True
        for feature in features_in_legend:
            if self.parent.well_coll.df.loc[
                self.parent.well_coll.df["geological_feature"] == feature
            ].empty:
                # Get index of row to be removed, then remove it in place with .drop().
                idx_remove = self.parent.well_legend_df[
                    self.parent.well_legend_df["geological_feature"] == feature
                    ].index
                self.parent.well_legend_df.drop(idx_remove, inplace=True)
                legend_updated = legend_updated or True
        return legend_updated

    def get_uid_legend(self, uid: str = None) -> dict:
        """Get legend for a particular uid."""
        locid = self.df.loc[self.df["uid"] == uid, "Loc ID"].values[0]
        legend_dict = self.parent.well_legend_df.loc[
            self.parent.well_legend_df["Loc ID"] == locid
            ].to_dict("records")
        return legend_dict[0]

    def set_uid_legend(self, uid: str = None, color_R: float = None, color_G: float = None, color_B: float = None,
                       line_thick: float = None, point_size: float = None, opacity: float = None):
        """Set the legend for a particular uid."""
        # Not implemented for this collection, but required by the abstract superclass.
        pass

    def metadata_modified_signal(self, updated_list: list = None):
        """Signal emitted when metadata change."""
        self.parent.well_metadata_modified_signal.emit(updated_list)

    def data_keys_modified_signal(self, updated_list: list = None):
        """Signal emitted when point data keys change."""
        self.parent.well_data_keys_modified_signal.emit(updated_list)

    # =================================== Additional methods ===========================================

    def get_well_locid_uids(self, locid=None):
        """Get list of uids of a given locid."""
        return self.df.loc[self.df["Loc ID"] == locid, "uid"].to_list()

    def get_uid_well_locid(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df["uid"] == uid, "Loc ID"].values[0]

    def set_uid_well_locid(self, uid=None, locid=None):
        """Set value(s) stored in dataframe (as pointer) from uid.."""
        self.df.loc[self.df["uid"] == uid, "Loc ID"] = locid
