"""dom.py
PZero© Andrea Bistacchi"""

from numpy import set_printoptions as np_set_print_options
from pandas import set_option as pd_set_option
import uuid
from copy import deepcopy
from PyQt5.QtCore import Qt, QVariant

from pzero.collections.collection_base import CollectionBase

"""Options to print Pandas dataframes in console when testing."""
pd_desired_width = 800
pd_max_columns = 20
pd_show_precision = 4
pd_max_colwidth = 80
pd_set_option('display.width', pd_desired_width)
np_set_print_options(linewidth=pd_desired_width)
pd_set_option('display.max_columns', pd_max_columns)
pd_set_option('display.precision', pd_show_precision)
pd_set_option('display.max_colwidth', pd_max_colwidth)


class DomCollection(CollectionBase):
    """
    Initialize DomCollection table.
    Column headers are taken from DomCollection.dom_entity_dict.keys()
    parent is supposed to be the project_window

    dom_entity_dict is a dictionary of entity attributes used throughout the project.
    Always use deepcopy(DomCollection.dom_entity_dict) to copy this dictionary without altering the original.
    """
    @property
    def entity_dict(self):
        return {'uid': "",
                       'name': "undef",
                       'dom_type': "undef",
                       'texture_uids': [],  # this refers to the uids of image data for which the texture coordinates have been calculated
                       'properties_names': [],
                       'properties_components': [],
                       'properties_types':[],
                       'x_section': "",  # this is the uid of the cross section for "XsVertexSet", "XsPolyLine", and "XsImage", empty for all others
                       'vtk_obj': None}


    @property
    def type_dict(self):
        return {'uid': str,
                            'name': str,
                            'dom_type': str,
                            'texture_uids': list,
                            'properties_names': list,
                            'properties_components': list,
                            'properties_types':list,
                            'x_section': str, # this is the uid of the cross section for "XsVertexSet", "XsPolyLine", and "XsImage", empty for all others
                            'vtk_obj': object}

    """List of valid data types."""

    @property
    def valid_types(self):
        return ["DEM", "TSDom", "PCDom"]

    @property
    def editable_columns(self):
        return self._df.columns.get_indexer(["name"])

    @property
    def default_save_table_filename(self):
        return "dom"

    """Custom methods used to add or remove entities, query the dataframe, etc."""

    def add_entity_from_dict(self, entity_dict=None):
        """Add entity to collection from dictionary.
        Create a new uid if it is not included in the dictionary."""
        if not entity_dict['uid']:
            entity_dict['uid'] = str(uuid.uuid4())
        """"Append new row to dataframe. Note that the 'append()' method for Pandas dataframes DOES NOT
        work in place, hence a NEW dataframe is created every time and then substituted to the old one."""
        self._df = self._df.append(entity_dict, ignore_index=True)
        """Reset data model"""
        self.modelReset.emit()
        self.main_window.prop_legend.update_widget(self.main_window)
        """Then emit signal to update the views."""
        self.main_window.dom_added_signal.emit([entity_dict['uid']])  # a list of uids is emitted, even if the entity is just one
        return entity_dict['uid']

    def remove_entity(self, uid=None):
        """Remove entity from collection. Remove row from dataframe and reset data model."""
        self._df.drop(self._df[self._df['uid'] == uid].index, inplace=True)
        self.modelReset.emit()  # is this really necessary?
        self.main_window.prop_legend.update_widget(self.main_window)
        """When done, send a signal over to the views."""
        self.main_window.dom_removed_signal.emit([uid])  # a list of uids is emitted, even if the entity is just one
        return uid

    def replace_vtk(self, uid=None, vtk_object=None):
        if isinstance(vtk_object, type(self._df.loc[self._df['uid'] == uid, 'vtk_obj'].values[0])):
            new_dict = deepcopy(self._df.loc[self._df['uid'] == uid, self._df.columns != 'vtk_obj'].to_dict('records')[0])
            keys = vtk_object.point_data_keys
            for key in keys:
                if key not in new_dict['properties_names'] and 'tag_' not in key:
                    components = vtk_object.get_point_data_shape(key)[1]
                    new_dict['properties_names'].append(key)
                    new_dict['properties_components'].append(components)

            new_dict['vtk_obj'] = vtk_object
            self.remove_entity(uid)
            self.add_entity_from_dict(entity_dict=new_dict)
        else:
            print("ERROR - replace_vtk with vtk of a different type.")



    def get_dom_type_uids(self, dom_type=None):
        """Get list of uids of a given dom_type."""
        return self._df.loc[self._df['dom_type'] == dom_type, 'uid'].to_list()

    def get_legend(self):
        legend_dict = self.main_window.others_legend_df.loc[self.main_window.others_legend_df['other_type'] == 'DOM'].to_dict('records')
        return legend_dict[0]



    def get_uid_dom_type(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self._df.loc[self._df['uid'] == uid, 'dom_type'].values[0]

    def set_uid_dom_type(self, uid=None, dom_type=None):
        """Set value(s) stored in dataframe (as pointer) from uid.."""
        self._df.loc[self._df['uid'] == uid, 'dom_type'] = dom_type

    def get_uid_texture_uids(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self._df.loc[self._df['uid'] == uid, 'texture_uids'].values[0]

    def set_uid_texture_uids(self, uid=None, texture_uids=None):
        """Set value(s) stored in dataframe (as pointer) from uid.."""
        self._df.loc[self._df['uid'] == uid, 'texture_uids'] = texture_uids

    def get_uid_properties_names(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid. This is a LIST even if we extract it with values[0]!"""
        return self._df.loc[self._df['uid'] == uid, 'properties_names'].values[0]

    def set_uid_properties_names(self, uid=None, properties_names=None):
        """Set value(s) stored in dataframe (as pointer) from uid. This is a LIST and "at" must be used!"""
        row = self._df[self._df['uid'] == uid].index.values[0]
        self._df.at[row, 'properties_names'] = properties_names

    def get_uid_properties_components(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid. This is a LIST even if we extract it with values[0]!"""
        return self._df.loc[self._df['uid'] == uid, 'properties_components'].values[0]

    def set_uid_properties_components(self, uid=None, properties_components=None):
        """Set value(s) stored in dataframe (as pointer) from uid. This is a LIST and "at" must be used!"""
        row = self._df[self._df['uid'] == uid].index.values[0]
        self._df.at[row, 'properties_components'] = properties_components

    def get_uid_x_section(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self._df.loc[self._df['uid'] == uid, 'x_section'].values[0]

    def set_uid_x_section(self, uid=None, x_section=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self._df.loc[self._df['uid'] == uid, 'x_section'] = x_section

    def get_uid_vtk_obj(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self._df.loc[self._df['uid'] == uid, 'vtk_obj'].values[0]

    def set_uid_vtk_obj(self, uid=None, vtk_obj=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self._df.loc[self._df['uid'] == uid, 'vtk_obj'] = vtk_obj

    def append_uid_property(self, uid=None, property_name=None, property_components=None):
        """Add property name and components to an uid and create empty property on vtk object.
        For some reason here list.append(new_eleemnt) does not work"""
        old_properties_names = self.get_uid_properties_names(uid=uid)
        old_properties_components = self.get_uid_properties_components(uid=uid)
        new_properties_names = old_properties_names + [property_name]
        new_properties_components = old_properties_components + [property_components]
        self.set_uid_properties_names(uid=uid, properties_names=new_properties_names)
        self.set_uid_properties_components(uid=uid, properties_components=new_properties_components)
        self.get_uid_vtk_obj(uid=uid).init_point_data(data_key=property_name, dimension=property_components)
        """IN THE FUTURE add cell data"""
        # self.main_window.prop_legend.update_widget(self.main_window)
        self.main_window.dom_metadata_modified_signal.emit([uid])

    def remove_uid_property(self, uid=None, property_name=None):
        """Remove property name and components from an uid and remove property on vtk object.
        Note that pop() works in place (its output is the removed element)."""
        idx = self.get_uid_properties_names(uid=uid).index(property_name)
        properties_names = self.get_uid_properties_names(uid=uid)
        properties_components = self.get_uid_properties_components(uid=uid)
        properties_names.pop(idx)
        properties_components.pop(idx)
        self.set_uid_properties_names(uid=uid, properties_names=properties_names)
        self.set_uid_properties_components(uid=uid, properties_components=properties_components)
        self.get_uid_vtk_obj(uid=uid).remove_point_data(data_key=property_name)
        """IN THE FUTURE add cell data"""
        # self.main_window.prop_legend.update_widget(self.main_window)
        self.main_window.dom_data_keys_removed_signal.emit([uid])

    def add_map_texture_to_dom(self, dom_uid=None, map_image_uid=None):
        row = self._df[self._df['uid'] == dom_uid].index.values[0]
        if map_image_uid not in self._df.at[row, 'texture_uids']:
            self.get_uid_vtk_obj(dom_uid).add_texture(map_image=self.main_window.image_coll.get_uid_vtk_obj(map_image_uid), map_image_uid=map_image_uid)
            self._df.at[row, 'texture_uids'].append(map_image_uid)
            self.main_window.dom_metadata_modified_signal.emit([dom_uid])

    def remove_map_texture_from_dom(self, dom_uid=None, map_image_uid=None):
        row = self._df[self._df['uid'] == dom_uid].index.values[0]
        if map_image_uid in self._df.at[row, 'texture_uids']:
            self.get_uid_vtk_obj(dom_uid).remove_texture(map_image_uid=map_image_uid)
            self._df.at[row, 'texture_uids'].remove(map_image_uid)
            self.main_window.dom_data_keys_removed_signal.emit([dom_uid])
            # self.main_window.dom_metadata_modified_signal.emit([dom_uid])

    def set_active_texture_on_dom(self, dom_uid=None, map_image_uid=None):
        self.get_uid_vtk_obj(dom_uid).set_active_texture(map_image_uid=map_image_uid)




    def setData(self, index, value, role=Qt.EditRole):
        """This is the method allowing to edit the table and the underlying dataframe.
        "self.main_window is" is used to point to parent, because the standard Qt setData
        method does not allow for extra variables to be passed into this method."""
        if index.isValid():
            self._df.iloc[index.row(), index.column()] = value
            if self.data(index, Qt.DisplayRole) == value:
                self.dataChanged.emit(index, index)
                uid = self._df.iloc[index.row(), 0]
                self.main_window.dom_metadata_modified_signal.emit([uid])  # a list of uids is emitted, even if the entity is just one
                return True
        return QVariant()
