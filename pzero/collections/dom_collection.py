"""dom_collection.py
PZero© Andrea Bistacchi"""

from uuid import uuid4

from numpy import set_printoptions as np_set_printoptions
from numpy import ndarray as np_ndarray

from pandas import DataFrame as pd_DataFrame
from pandas import set_option as pd_set_option

from vtkmodules.vtkCommonDataModel import vtkDataObject

from .AbstractCollection import BaseCollection

# Options to print Pandas dataframes in console when testing.
pd_desired_width = 800
pd_max_columns = 20
pd_show_precision = 4
pd_max_colwidth = 80
pd_set_option("display.width", pd_desired_width)
np_set_printoptions(linewidth=pd_desired_width)
pd_set_option("display.max_columns", pd_max_columns)
pd_set_option("display.precision", pd_show_precision)
pd_set_option("display.max_colwidth", pd_max_colwidth)


class DomCollection(BaseCollection):
    """Collection for all DOMs and their metadata."""
    def __init__(self, parent=None, *args, **kwargs):
        super(DomCollection, self).__init__(parent, *args, **kwargs)
        # Initialize properties required by the abstract superclass.
        self.entity_dict = {
            "uid": "",
            "name": "undef",
            "topology": "undef",
            "scenario": "undef",
            "properties_names": [],
            "properties_components": [],
            "properties_types": [],
            "x_section": "", # this is the uid of the cross section for "XsVertexSet", "XsPolyLine", and "XsImage", empty for all others
            "texture_uids": [],  # this refers to the uids of image data for which the texture coordinates have been calculated
            "vtk_obj": None,
        }

        self.entity_dict_types = {
            "uid": str,
            "name": str,
            "topology": str,
            "scenario": str,
            "properties_names": list,
            "properties_components": list,
            "properties_types": list,
            "x_section": str,
            "texture_uids": list,
            "vtk_obj": object,
        }

        self.valid_topologies = ["DEM", "TSDom", "PCDom"]

        self.editable_columns_names = ["name", "scenario"]

        self.collection_name = 'dom'

        self.initialize_df()

    # =================================== Obligatory methods ===========================================

    def add_entity_from_dict(self, entity_dict: pd_DataFrame = None, color: np_ndarray = None):
        """Add an entity from a dictionary shaped as self.entity_dict."""
        # Create a new uid if it is not included in the dictionary.
        if not entity_dict["uid"]:
            entity_dict["uid"] = str(uuid4())
        # Append new row to dataframe. Note that the 'append()' method for Pandas dataframes DOES NOT
        # work in place, hence a NEW dataframe is created every time and then substituted to the old one.
        self.df = self.df.append(entity_dict, ignore_index=True)
        # Reset data model.
        self.modelReset.emit()
        self.parent.prop_legend.update_widget(self.parent)
        # Then emit signal to update the views. A list of uids is emitted, even if the entity is just one.
        self.signals.added.emit([entity_dict["uid"]])
        return entity_dict["uid"]

    def remove_entity(self, uid: str = None) -> str:
        """Remove an entity and its metadata."""
        # Remove row from dataframe and reset data model.
        self.df.drop(self.df[self.df["uid"] == uid].index, inplace=True)
        self.modelReset.emit()  # is this really necessary?
        self.parent.prop_legend.update_widget(self.parent)
        # When done, send a signal over to the views. A list of uids is emitted, even if the entity is just one.
        self.signals.removed.emit([uid])
        return uid

    def clone_entity(self, uid: str = None) -> str:
        """Clone an entity."""
        # Not implemented for this collection, but required by the abstract superclass.
        pass

    def replace_vtk(self, uid: str = None, vtk_object: vtkDataObject = None):
        """Replace the vtk object of a given uid with another vtkobject."""
        # Not implemented for this collection, but required by the abstract superclass.
        pass

    def attr_modified_update_legend_table(self):
        """Update legend table when attributes are changed."""
        # Not implemented for this collection, but required by the abstract superclass.
        pass

    def remove_unused_from_legend(self):
        """Remove unused roles / features from a legend table."""
        legend_updated: bool = False
        return legend_updated

    def get_uid_legend(self, uid: str = None) -> dict:
        """Get legend for a particular uid."""
        legend_dict = self.parent.others_legend_df.loc[
            self.parent.others_legend_df["other_collection"] == "DOM"
            ].to_dict("records")
        return legend_dict[0]

    def set_uid_legend(self, uid: str = None, color_R: float = None, color_G: float = None, color_B: float = None,
                       line_thick: float = None, point_size: float = None, opacity: float = None):
        """Set the legend for a particular uid."""
        # Not implemented for this collection, but required by the abstract superclass.
        pass

    # def metadata_modified_signal(self, updated_list: list = None):
    #     """Signal emitted when metadata change."""
    #     self.parent.dom_coll.signals.metadata_modified.emit(updated_list)

    # def data_keys_modified_signal(self, updated_list: list = None):
    #     """Signal emitted when point data keys change."""
    #     self.parent.dom_coll.signals.data_keys_modified.emit(updated_list)

    # =================================== Additional methods ===========================================

    def get_uid_texture_uids(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df["uid"] == uid, "texture_uids"].values[0]

    def set_uid_texture_uids(self, uid=None, texture_uids=None):
        """Set value(s) stored in dataframe (as pointer) from uid.."""
        self.df.loc[self.df["uid"] == uid, "texture_uids"] = texture_uids

    def add_map_texture_to_dom(self, dom_uid=None, map_image_uid=None):
        """Add a map texture to a DOM."""
        row = self.df[self.df["uid"] == dom_uid].index.values[0]
        if map_image_uid not in self.df.at[row, "texture_uids"]:
            self.get_uid_vtk_obj(dom_uid).add_texture(
                map_image=self.parent.image_coll.get_uid_vtk_obj(map_image_uid),
                map_image_uid=map_image_uid,
            )
            self.df.at[row, "texture_uids"].append(map_image_uid)
            self.signals.metadata_modified.emit([dom_uid])

    def remove_map_texture_from_dom(self, dom_uid=None, map_image_uid=None):
        """Remove a map texture from a DOM."""
        row = self.df[self.df["uid"] == dom_uid].index.values[0]
        if map_image_uid in self.df.at[row, "texture_uids"]:
            self.get_uid_vtk_obj(dom_uid).remove_texture(map_image_uid=map_image_uid)
            self.df.at[row, "texture_uids"].remove(map_image_uid)
            self.signals.data_keys_modified.emit([dom_uid])
            # self.signals.metadata_modified.emit([dom_uid])

    def set_active_texture_on_dom(self, dom_uid=None, map_image_uid=None):
        """Set active texture on a DOM."""
        self.get_uid_vtk_obj(dom_uid).set_active_texture(map_image_uid=map_image_uid)
