"""image_collection.py
PZero© Andrea Bistacchi"""

import numpy as np
from pandas import set_option as pd_set_option
from pandas import DataFrame as pd_DataFrame
import uuid
from copy import deepcopy
from PyQt5.QtCore import QAbstractTableModel, Qt, QVariant
from .entities_factory import MapImage, XsImage, Seismics, Image3D

"""Options to print Pandas dataframes in console for testing."""
pd_desired_width = 800
pd_max_columns = 20
pd_show_precision = 4
pd_max_colwidth = 80
pd_set_option('display.width', pd_desired_width)
np.set_printoptions(linewidth=pd_desired_width)
pd_set_option('display.max_columns', pd_max_columns)
pd_set_option('display.precision', pd_show_precision)
pd_set_option('display.max_colwidth', pd_max_colwidth)


class ImageCollection(QAbstractTableModel):
    """
    Initialize ImageCollection table.
    Column headers are taken from ImageCollection.image_entity_dict.keys()
    parent is supposed to be the project_window

    image_entity_dict is a dictionary of entity attributes used throughout the project.
    Always use deepcopy(ImageCollection.image_entity_dict) to copy this dictionary without altering the original.
    """
    image_entity_dict = {'uid': "",
                         'name': "undef",
                         'image_type': "undef",
                         'properties_names': [],
                         'properties_components': [],
                         'properties_types': [],
                         'x_section': "",  # this is the uid of the cross section for "XsVertexSet", "XsPolyLine", and "XsImage", empty for all others
                         'vtk_obj': None}

    image_entity_type_dict = {'uid': str,
                              'name': str,
                              'image_type': str,
                              'properties_names': list,
                              'properties_components': list,
                              'properties_types': list,
                              'x_section': str,
                              'vtk_obj': object}

    """List of valid data types."""
    valid_image_types = ["MapImage", "XsImage", "Seismics", "Image3D"]  # "TSDomImage"???

    """Initialize ImageCollection table. Column headers are taken from
    ImageCollection.image_entity_dict.keys(), and parent is supposed to be the project_window."""
    """IN THE FUTURE the edit dialog should be able to edit metadata of multiple entities (and selecting "None" will not change them)."""

    def __init__(self, parent=None, *args, **kwargs):
        super(ImageCollection, self).__init__(*args, **kwargs)
        """Import reference to parent, otherwise it is difficult to reference them in SetData() that has a standard list of inputs."""
        self.parent = parent

        """Initialize Pandas dataframe."""
        self.df = pd_DataFrame(columns=list(self.image_entity_dict.keys()))

        """Here we use .columns.get_indexer to get indexes of the columns that we would like to be editable in the QTableView"""
        self.editable_columns = self.df.columns.get_indexer(["name"])

    """Custom methods used to add or remove entities, query the dataframe, etc."""

    def add_entity_from_dict(self, entity_dict=None):
        """Add entity to collection from dictionary.
        Create a new uid if it is not included in the dictionary."""
        """NOTE THAT HERE WE ASSUME THE ATTRIBUTES HAVE BEEN CAREFULLY DEFINED, OTHERWISE A CHECK AS IN REPLACE_VTK WOULD BE NECESSARY"""
        if not entity_dict['uid']:
            entity_dict['uid'] = str(uuid.uuid4())
        """"Append new row to dataframe. Note that the 'append()' method for Pandas dataframes DOES NOT
        work in place, hence a NEW dataframe is created every time and then substituted to the old one."""
        self.df = self.df.append(entity_dict, ignore_index=True)
        """Reset data model"""
        self.modelReset.emit()
        """Update properties colormaps if needed"""
        for i in range(len(entity_dict['properties_names'])):
            if entity_dict['properties_components'][i] == 1:
                property_name = entity_dict['properties_names'][i]
                if self.parent.prop_legend_df.loc[self.parent.prop_legend_df['property_name'] == property_name].empty:
                    self.parent.prop_legend_df = self.parent.prop_legend_df.append({'property_name': property_name, 'colormap': 'gray'}, ignore_index=True)
                    self.parent.prop_legend.update_widget(self.parent)
        """Then emit signal to update the views."""
        self.parent.image_added_signal.emit([entity_dict['uid']])  # a list of uids is emitted, even if the entity is just one
        return entity_dict['uid']

    def remove_entity(self, uid=None):
        """Remove entity from collection. Remove row from dataframe and reset data model."""
        """First remove textures, if defined."""
        for dom_uid in self.parent.dom_coll.get_uids():
            if uid in self.parent.dom_coll.get_uid_texture_uids(dom_uid):
                self.parent.dom_coll.remove_map_texture_from_dom(dom_uid=dom_uid, map_image_uid=uid)
        """Then remove image"""
        self.df.drop(self.df[self.df['uid'] == uid].index, inplace=True)
        self.modelReset.emit()  # is this really necessary?
        self.parent.prop_legend.update_widget(self.parent)
        """When done, send a signal over to the views."""
        self.parent.image_removed_signal.emit([uid])  # a list of uids is emitted, even if the entity is just one
        return uid

    def replace_vtk(self, uid=None, vtk_object=None):
        if isinstance(vtk_object, type(self.df.loc[self.df['uid'] == uid, 'vtk_obj'].values[0])):
            new_dict = deepcopy(self.df.loc[self.df['uid'] == uid, self.df.columns != 'vtk_obj'].to_dict('records')[0])
            new_dict['vtk_obj'] = vtk_object
            """Check properties attributes"""
            if isinstance(self, MapImage):  # "TSDomImage"???
                new_dict['image_type'] = "MapImage"
            elif isinstance(self,XsImage):
                new_dict['image_type'] = "XsImage"
            elif isinstance(self, Seismics):
                new_dict['image_type'] = "Seismics"
            elif isinstance(self, Image3D):
                new_dict['image_type'] = "Image3D"
            else:
                print("ERROR - class not recognized.")
            new_dict['properties_names'] = vtk_object.properties_names
            new_dict['properties_components'] = vtk_object.properties_components
            new_dict['properties_types'] = vtk_object.properties_types
            """Remove and add"""
            self.remove_entity(uid)
            self.add_entity_from_dict(entity_dict=new_dict)
            self.modelReset.emit()  # is this really necessary?
            self.parent.prop_legend.update_widget(self.parent)
        else:
            print("ERROR - replace_vtk with vtk of a different type.")

    def get_number_of_entities(self):
        """Get number of entities stored in Pandas dataframe."""
        return self.df.shape[0]

    def get_uids(self):
        """Get list of uids."""
        return self.df['uid'].to_list()

    def get_legend(self):
        """Get legend."""
        legend_dict = self.parent.others_legend_df.loc[self.parent.others_legend_df['other_type'] == 'Image'].to_dict('records')
        return legend_dict[0]

    def get_image_type_uids(self, image_type=None):
        """Get list of uids of a given image_type."""
        return self.df.loc[self.df['image_type'] == image_type, 'uid'].to_list()

    def get_uid_name(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df['uid'] == uid, 'name'].values[0]

    def set_uid_name(self, uid=None, name=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df['uid'] == uid, 'name'] = name

    def get_uid_image_type(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df['uid'] == uid, 'image_type'].values[0]

    def set_uid_image_type(self, uid=None, image_type=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df['uid'] == uid, 'image_type'] = image_type

    def get_uid_properties_names(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid.. This is a LIST even if we extract it with values[0]!"""
        return self.df.loc[self.df['uid'] == uid, 'properties_names'].values[0]

    def set_uid_properties_names(self, uid=None, properties_names=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df['uid'] == uid, 'properties_names'] = properties_names

    def get_uid_properties_components(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid.. This is a LIST even if we extract it with values[0]!"""
        return self.df.loc[self.df['uid'] == uid, 'properties_components'].values[0]

    def set_uid_properties_components(self, uid=None, properties_components=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df['uid'] == uid, 'properties_components'] = properties_components

    def get_uid_properties_types(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid. This is a LIST even if we extract it with values[0]!"""
        return self.get_uid_vtk_obj(uid).properties_types

    def set_uid_properties_types(self, uid=None, properties_types=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df['uid'] == uid, 'properties_types'] = properties_types

    def get_uid_x_section(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df['uid'] == uid, 'x_section'].values[0]

    def set_uid_x_section(self, uid=None, x_section=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df['uid'] == uid, 'x_section'] = x_section

    def get_uid_vtk_obj(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df['uid'] == uid, 'vtk_obj'].values[0]

    def set_uid_vtk_obj(self, uid=None, vtk_obj=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df['uid'] == uid, 'vtk_obj'] = vtk_obj

    """Standard QT methods slightly adapted to the data source."""

    def data(self, index, role):
        """Data is updated on the fly:
        .row() index points to an entity in the vtkCollection
        .column() index points to an element in the list created on the fly
        based on the column headers stored in the dictionary."""
        if role == Qt.DisplayRole:
            value = self.df.iloc[index.row(), index.column()]
            return str(value)

    def headerData(self, section, orientation, role):
        """Set header from pandas dataframe. "section" is a standard Qt variable."""
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                return str(self.df.columns[section])
            if orientation == Qt.Vertical:
                return str(self.df.index[section])

    def rowCount(self, index):
        """Set row count from pandas dataframe"""
        return self.df.shape[0]

    def columnCount(self, index):
        """Set column count from pandas dataframe"""
        return self.df.shape[1]

    def flags(self, index):
        """Set editable columns."""
        if index.column() in self.editable_columns:
            return Qt.ItemFlags(QAbstractTableModel.flags(self, index) | Qt.ItemIsEditable)
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def setData(self, index, value, role=Qt.EditRole):
        """This is the method allowing to edit the table and the underlying dataframe.
        "self.parent is" is used to point to parent, because the standard Qt setData
        method does not allow for extra variables to be passed into this method."""
        if index.isValid():
            self.df.iloc[index.row(), index.column()] = value
            if self.data(index, Qt.DisplayRole) == value:
                self.dataChanged.emit(index, index)
                uid = self.df.iloc[index.row(), 0]
                self.parent.image_metadata_modified_signal.emit([uid])  # a list of uids is emitted, even if the entity is just one
                return True
        return QVariant()
