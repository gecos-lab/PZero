"""DIM_collection.py
PZero© Andrea Bistacchi"""

from uuid import uuid4

from numpy import ndarray as np_ndarray

from pandas import DataFrame as pd_DataFrame
from pandas import concat as pd_concat

from .AbstractCollection import BaseCollection


class DIMCollection(BaseCollection):
    """Collection for all mesh entities and their metadata."""

    def __init__(self, parent=None, *args, **kwargs):
        super(DIMCollection, self).__init__(parent, *args, **kwargs)
        # Initialize properties required by the abstract superclass.
        self.entity_dict = {}

        self.entity_dict_types = {}

        self.valid_topologies = []

        self.editable_columns_names = ["name", "scenario"]

        self.collection_name = ""

        self.default_colormap = ""

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
        # New syntax with Pandas >= 2.0.0:
        self.df = pd_concat([self.df, pd_DataFrame([entity_dict])], ignore_index=True)
        # Reset data model.
        self.modelReset.emit()
        # Update properties colormaps if needed. This is generally necessary just for images,
        # but it is worth adding it here for a more general behaviour with no relevant computational cost.
        for i in range(len(entity_dict["properties_names"])):
            if entity_dict["properties_components"][i] == 1:
                property_name = entity_dict["properties_names"][i]
                if self.parent.prop_legend_df.loc[
                    self.parent.prop_legend_df["property_name"] == property_name
                ].empty:
                    # New Pandas >= 2.0.0
                    self.parent.prop_legend_df = pd_concat(
                        [
                            self.parent.prop_legend_df,
                            pd_DataFrame(
                                [
                                    {
                                        "property_name": property_name,
                                        "colormap": self.default_colormap,
                                    }
                                ]
                            ),
                        ],
                        ignore_index=True,
                    )
                    self.parent.prop_legend.update_widget(self.parent)
        # Then emit signal to update the views. A list of uids is emitted, even if the
        # entity is just one, for future compatibility
        self.parent.signals.entities_added.emit([entity_dict["uid"]], self)
        return entity_dict["uid"]

    def remove_entity(self, uid: str = None) -> str:
        """Remove an entity and its metadata."""
        # First remove textures from DOMs, if defined. This is generally necessary just for images,
        # but it is worth adding it here for a more general behaviour with no relevant computational cost.
        for dom_uid in self.parent.dom_coll.get_uids:
            if uid in self.parent.dom_coll.get_uid_textures(dom_uid):
                self.parent.dom_coll.remove_map_texture_from_dom(
                    dom_uid=dom_uid, map_image_uid=uid
                )
        # Remove row from dataframe and reset data model.
        if uid not in self.get_uids:
            return
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
        """Remove unused roles / features from a legend table."""
        # legend_updated is used to record if the table is updated or not.
        legend_updated: bool = False
        return legend_updated

    def get_uid_legend(self, uid: str = None) -> dict:
        """Get legend for a particular uid. Implemented in subclasses."""
        pass

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
