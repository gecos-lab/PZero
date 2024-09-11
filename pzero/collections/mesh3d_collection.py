"""mesh3d_collection.py
PZero© Andrea Bistacchi"""

import uuid
from copy import deepcopy

from PyQt5.QtCore import QAbstractTableModel, Qt, QVariant
from numpy import set_printoptions as np_set_set_printoptions, ndarray
from pandas import DataFrame as pd_DataFrame, DataFrame
from pandas import set_option as pd_set_option
from vtkmodules.vtkCommonDataModel import vtkDataObject

from .AbstractCollection import BaseCollection

"""Options to print Pandas dataframes in console for testing."""
pd_desired_width = 800
pd_max_columns = 20
pd_show_precision = 4
pd_max_colwidth = 80
pd_set_option("display.width", pd_desired_width)
np_set_set_printoptions(linewidth=pd_desired_width)
pd_set_option("display.max_columns", pd_max_columns)
pd_set_option("display.precision", pd_show_precision)
pd_set_option("display.max_colwidth", pd_max_colwidth)


class Mesh3DCollection(BaseCollection):
    """Collection for all mesh entities and their metadata."""
    def __init__(self, parent = None, *args, **kwargs):
        super(Mesh3DCollection, self).__init__(parent, *args, **kwargs)
        # Initialize properties required by the abstract superclass.
        self.entity_dict = {
            "uid": "",
            "name": "undef",
            "topology": "undef",
            "scenario": "undef",
            "properties_names": [],
            "properties_components": [],
            "x_section": "",  # this is the uid of the cross-section for "XsVoxet", empty for all others
            "vtk_obj": None,
        }

        self.entity_type_dict = {
            "uid": str,
            "name": str,
            "topology": str,
            "scenario": str,
            "properties_names": list,
            "properties_components": list,
            "x_section": str,
            "vtk_obj": object,
        }

        self.valid_topologies = ["TetraSolid", "Voxet", "XsVoxet"]

        self.editable_columns_names = ["name", "scenario"]

        self.collection_name = 'mesh3d'

        self.initialize_df()

    # =================================== Obligatory methods ===========================================

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
        # Update properties colormaps if needed.
        for property_name in entity_dict["properties_names"]:
            if self.parent.prop_legend_df.loc[
                self.parent.prop_legend_df["property_name"] == property_name
            ].empty:
                self.parent.prop_legend_df = self.parent.prop_legend_df.append(
                    {"property_name": property_name, "colormap": "rainbow"},
                    ignore_index=True,
                )
                self.parent.prop_legend.update_widget(self.parent)
        # Then emit signal to update the views. A list of uids is emitted, even if the
        # entity is just one, for future compatibility
        self.parent.mesh3d_added_signal.emit([entity_dict["uid"]])
        return entity_dict["uid"]

    def remove_entity(self, uid: str = None) -> str:
        """Remove an entity and its metadata."""
        # Remove row from dataframe and reset data model.
        if uid not in self.get_uids:
            return
        self.df.drop(self.df[self.df["uid"] == uid].index, inplace=True)
        self.modelReset.emit()  # is this really necessary?
        self.parent.prop_legend.update_widget(self.parent)
        # When done, send a signal over to the views. A list of uids is emitted, even if the entity is just one.
        self.parent.mesh3d_removed_signal.emit([uid])
        return uid

    def clone_entity(self, uid: str = None) -> str:
        """Clone an entity."""
        # Not implemented for this collection, but required by the abstract superclass.
        pass

    def replace_vtk(self, uid: str = None, vtk_object: vtkDataObject = None):
        """Replace an entity."""
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
            self.parent.others_legend_df["other_collection"] == "Mesh3D"
            ].to_dict("records")
        return legend_dict[0]

    def set_uid_legend(self, uid: str = None, color_R: float = None, color_G: float = None, color_B: float = None,
                       line_thick: float = None, point_size: float = None, opacity: float = None):
        """Set the legend for a particular uid."""
        # Not implemented for this collection, but required by the abstract superclass.
        pass

    def metadata_modified_signal(self, updated_list: list = None):
        """Signal emitted when metadata change."""
        self.parent.mesh3d_metadata_modified_signal.emit(updated_list)

    def data_keys_modified_signal(self, updated_list: list = None):
        """Signal emitted when point data keys change."""
        self.parent.mesh3d_data_keys_modified_signal.emit(updated_list)

