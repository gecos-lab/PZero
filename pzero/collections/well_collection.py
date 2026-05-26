"""well_collection.py
PZero© Andrea Bistacchi"""

from uuid import uuid4

from numpy import ndarray as np_ndarray

from pandas import DataFrame as pd_DataFrame
from pandas import concat as pd_concat

from .AbstractCollection import BaseCollection


class WellCollection(BaseCollection):
    """Collection for all wells and their metadata."""
    shared_legend_name = "Wells"

    def __init__(self, parent=None, *args, **kwargs):
        super(WellCollection, self).__init__(parent, *args, **kwargs)
        # Initialize properties required by the abstract superclass.
        self.entity_dict = {
            "uid": "",
            "name": "undef",
            "scenario": "undef",
            "parent_uid": [],  # this is the uid of the cross section for "XsVertexSet", "XsPolyLine", and "XsImage", empty for all others
            "topology": "undef",
            "vtk_obj": None,
            "properties_names": [],
            "properties_components": [],
            "properties_types": [],
            "markers": [],
        }

        self.entity_dict_types = {
            "uid": str,
            "name": str,
            "scenario": str,
            "parent_uid": str,
            "topology": str,
            "vtk_obj": object,
            "properties_names": list,
            "properties_components": list,
            "properties_types": list,
            "markers": list,
        }

        self.valid_topologies = [
            "VertexSet",
            "PolyLine",
            "XsVertexSet",
            "XsPolyLine",
        ]

        self.editable_columns_names = ["name", "scenario"]

        self.collection_name = "well_coll"

        self.initialize_df()

    def add_entity_from_dict(
        self, entity_dict: pd_DataFrame = None, color: np_ndarray = None
    ):
        """Add an entity from a dictionary shaped as self.entity_dict."""
        # Create a new uid if it is not included in the dictionary.
        if not entity_dict["uid"]:
            entity_dict["uid"] = str(uuid4())
        # Append new row to dataframe. Note that the 'append()' method for Pandas dataframes DOES NOT
        # work in place, hence a NEW dataframe is created every time and then substituted to the old one.
        # New syntax with Pandas >= 2.0.0:
        self.df = pd_concat([self.df, pd_DataFrame([entity_dict])], ignore_index=True)
        # Reset data model.
        self.modelReset.emit()
        self.parent.prop_legend.update_widget(self.parent)
        # Then emit signal to update the views. A list of uids is emitted, even if the entity is just one.
        self.parent.signals.entities_added.emit([entity_dict["uid"]], self)
        return entity_dict["uid"]

    def remove_entity(self, uid: str = None) -> str:
        """Remove an entity and its metadata."""
        # Remove row from dataframe and reset data model.
        self.df.drop(self.df[self.df["uid"] == uid].index, inplace=True)
        self.modelReset.emit()  # is this really necessary?
        self.parent.prop_legend.update_widget(self.parent)
        # When done, send a signal over to the views. A list of uids is emitted, even if the entity is just one.
        self.parent.signals.entities_removed.emit([uid], self)
        return uid

    def clone_entity(self, uid: str = None) -> str:
        """Clone an entity."""
        # Not implemented for this collection, but required by the abstract superclass.
        pass

    def attr_modified_update_legend_table(self):
        """Update legend table when attributes are changed."""
        # Not implemented for this collection, but required by the abstract superclass.
        pass

    def remove_unused_from_legend(self):
        """Remove unused names from the well legend table."""
        legend_updated = False
        return legend_updated

    def get_uid_legend(self, uid: str = None) -> dict:
        """Get legend for a particular uid."""
        legend_dict = self.parent.others_legend_df.loc[
            self.parent.others_legend_df["other_collection"] == self.shared_legend_name
        ].to_dict("records")
        if not legend_dict:
            return {
                "color_R": 255,
                "color_G": 255,
                "color_B": 255,
                "line_thick": 2.0,
                "point_size": 0.0,
                "opacity": 100,
            }
        return legend_dict[0]

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
        # Not implemented for this collection, but required by the abstract superclass.
        pass

    # =================================== Additional methods ===========================================

    def get_well_name_uids(self, name=None):
        """Get list of uids of a given name."""
        return self.df.loc[self.df["name"] == name, "uid"].to_list()

    def get_uid_well_name(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df["uid"] == uid, "name"].values[0]

    def set_uid_well_name(self, uid=None, name=None):
        """Set value(s) stored in dataframe (as pointer) from uid.."""
        self.df.loc[self.df["uid"] == uid, "name"] = name

    def get_uid_marker_names(self, uid: str = None) -> list:
        """Get list of marker property names for a given well uid."""
        vtk_obj = self.get_uid_vtk_obj(uid)
        if hasattr(vtk_obj, "get_marker_names"):
            return vtk_obj.get_marker_names()
        return []
