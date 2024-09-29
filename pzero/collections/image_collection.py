"""image_collection.py
PZero© Andrea Bistacchi"""

from uuid import uuid4

from numpy import set_printoptions as np_set_printoptions
from numpy import ndarray as np_ndarray

from pandas import DataFrame as pd_DataFrame
from pandas import set_option as pd_set_option

from vtkmodules.vtkCommonDataModel import vtkDataObject

from .AbstractCollection import BaseCollection

# Options to print Pandas dataframes in console for testing.
pd_desired_width = 800
pd_max_columns = 20
pd_show_precision = 4
pd_max_colwidth = 80
pd_set_option("display.width", pd_desired_width)
np_set_printoptions(linewidth=pd_desired_width)
pd_set_option("display.max_columns", pd_max_columns)
pd_set_option("display.precision", pd_show_precision)
pd_set_option("display.max_colwidth", pd_max_colwidth)


class ImageCollection(BaseCollection):
    """Collection for all image entities and their metadata."""
    def __init__(self, parent=None, *args, **kwargs):
        super(ImageCollection, self).__init__(parent, *args, **kwargs)
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
            "vtk_obj": object,
        }

        self.valid_topologies = [
            "MapImage",
            "XsImage",
            "Seismics",
            "Image3D",
        ]

        self.editable_columns_names = ["name", "scenario"]

        self.collection_name = 'image'

        self.initialize_df()

    def add_entity_from_dict(self, entity_dict: pd_DataFrame = None, color: np_ndarray = None):
        """Add a entity from a dictionary shaped as self.entity_dict."""
        # NOTE THAT HERE WE ASSUME THE ATTRIBUTES HAVE BEEN CAREFULLY DEFINED, OTHERWISE A CHECK
        # AS IN REPLACE_VTK WOULD BE NECESSARY.
        if not entity_dict["uid"]:
            entity_dict["uid"] = str(uuid4())
        # Append new row to dataframe. Note that the 'append()' method for Pandas dataframes DOES NOT
        # work in place, hence a NEW dataframe is created every time and then substituted to the old one.
        self.df = self.df.append(entity_dict, ignore_index=True)
        # Reset data model.
        self.modelReset.emit()
        # Update properties colormaps if needed.
        for i in range(len(entity_dict["properties_names"])):
            if entity_dict["properties_components"][i] == 1:
                property_name = entity_dict["properties_names"][i]
                if self.parent.prop_legend_df.loc[
                    self.parent.prop_legend_df["property_name"] == property_name
                ].empty:
                    self.parent.prop_legend_df = self.parent.prop_legend_df.append(
                        {"property_name": property_name, "colormap": "gray"},
                        ignore_index=True,
                    )
                    self.parent.prop_legend.update_widget(self.parent)
        # Then emit signal to update the views. A list of uids is emitted, even if the entity is just one
        self.parent.image_coll.signals.added.emit(
            [entity_dict["uid"]]
        )
        return entity_dict["uid"]

    def remove_entity(self, uid: str = None) -> str:
        """Remove an entity and its metadata."""
        # First remove textures, if defined.
        for dom_uid in self.parent.dom_coll.get_uids:
            if uid in self.parent.dom_coll.get_uid_texture_uids(dom_uid):
                self.parent.dom_coll.remove_map_texture_from_dom(
                    dom_uid=dom_uid, map_image_uid=uid
                )
        # Then remove image.
        self.df.drop(self.df[self.df["uid"] == uid].index, inplace=True)
        self.modelReset.emit()  # is this really necessary?
        self.parent.prop_legend.update_widget(self.parent)
        # When done, send a signal over to the views. A list of uids is emitted, even if the entity is just one.
        self.parent.image_coll.signals.removed.emit(
            [uid]
        )
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
        # legend_updated is used to record if the table is updated or not.
        legend_updated: bool = False
        return legend_updated

    def get_uid_legend(self, uid: str = None) -> dict:
        """Get legend for a particular uid."""
        legend_dict = self.parent.others_legend_df.loc[self.parent.others_legend_df["other_collection"] == "Image"].to_dict("records")
        return legend_dict[0]

    def set_uid_legend(self, uid: str = None, color_R: float = None, color_G: float = None, color_B: float = None,
                       line_thick: float = None, point_size: float = None, opacity: float = None):
        """Set the legend for a particular uid."""
        # Not implemented for this collection, but required by the abstract superclass.
        pass

    # def metadata_modified_signal(self, updated_list: list = None):
    #     """Signal emitted when metadata change."""
    #     self.parent.image_coll.signals.metadata_modified.emit(updated_list)

    # def data_keys_modified_signal(self, updated_list: list = None):
    #     """Signal emitted when point data keys change."""
    #     # Not implemented for this collection, but required by the abstract superclass.
    #     pass
