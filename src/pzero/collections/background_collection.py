"""backgrounds_collection.py
PZero© Andrea Bistacchi"""

import numpy as np
import pandas as pd
import uuid
from copy import deepcopy
from PyQt5.QtCore import Qt, QVariant

from pzero.collections.collection_base import CollectionBase

"""Options to print Pandas dataframes in console when testing."""
pd_desired_width = 800
pd_max_columns = 20
pd_show_precision = 4
pd_max_colwidth = 80
pd.set_option('display.width', pd_desired_width)
np.set_printoptions(linewidth=pd_desired_width)
pd.set_option('display.max_columns', pd_max_columns)
pd.set_option('display.precision', pd_show_precision)
pd.set_option('display.max_colwidth', pd_max_colwidth)


class BackgroundCollection(CollectionBase):
    """
    Initialize BackgroundCollection table.
    Column headers are taken from BackgroundCollection.background_entity_dict.keys()
    parent is supposed to be the project_window
    """

    """background_entity_dict is a dictionary of entity metadata used throughout the project.
    Keys define both the background and topological meaning of entities and values are default values that
    implicitly define types. Always use deepcopy(BackgroundCollection.background_entity_dict) to
    copy this dictionary without altering the original."""

    @property
    def entity_dict(self):
            return {'uid': "",
                              'name': "undef",
                              'topological_type': "undef",
                              'background_type': "undef",
                              'background_feature': "undef",
                              'properties_names': [],
                              'properties_components': [],
                              'x_section': "",
                              # this is the uid of the cross section for "XsVertexSet", "XsPolyLine", and "XsImage", empty for all others
                              'borehole': "",
                              'vtk_obj': None}

    @property
    def type_dict(self):
        return {'uid': str,
                                   'name': str,
                                   'topological_type': str,
                                   'background_type': str,
                                   'background_feature': str,
                                   'properties_names': list,
                                   'properties_components': list,
                                   'x_section': str,
                                   # this is the uid of the cross section for "XsVertexSet", "XsPolyLine", and "XsImage", empty for all others
                                   'borehole': str,
                                   'vtk_obj': object}


    @property
    def valid_type(self):
        """List of valid background types."""
        return ["undef",
                "Annotations",
                "Cultural"]

    @property
    def valid_topological_type(self):
        """List of valid data types."""
        return ["VertexSet", "PolyLine", "TriSurf", "XsVertexSet", "XsPolyLine"]
    
    
    @property
    def editable_columns(self):
        return self._df.columns.get_indexer(["name", "type", "feature"])
    

    """Initialize BackgroundCollection table. Column headers are taken from
    BackgroundCollection.background_entity_dict.keys(), and parent is supposed to be the project_window."""
    """IN THE FUTURE the edit dialog should be able to edit metadata of multiple entities (and selecting "None" will not change them)."""


    def add_entity_from_dict(self, entity_dict=None, color=None):
        """Add entity to collection from dictionary."""
        """Create a new uid if it is not included in the dictionary."""
        if not entity_dict['uid']:
            entity_dict['uid'] = str(uuid.uuid4())
        """"Append new row to dataframe. Note that the 'append()' method for Pandas dataframes DOES NOT
        work in place, hence a NEW dataframe is created every time and then substituted to the old one."""
        self._df = self._df.append(entity_dict, ignore_index=True)
        """Reset data model"""
        self.modelReset.emit()
        """Then add new background_type / feature to the legend if needed."""
        background_type = entity_dict['background_type']
        feature = entity_dict['background_feature']
        if self.main_window.backgrounds_legend_df.loc[(self.main_window.backgrounds_legend_df['background_type'] == background_type)
                                                 & (self.main_window.backgrounds_legend_df['background_feature'] == feature)].empty:
            if color:
                print(color)
                R, G, B = color
            else:
                R, G, B = np.round(np.random.random(3) * 255)
            self.main_window.backgrounds_legend_df = self.main_window.backgrounds_legend_df.append({'background_type': background_type,
                                                                                         'background_feature': feature,
                                                                                         'color_R': R,
                                                                                         'color_G': G,
                                                                                         'color_B': B,
                                                                                         'line_thick': 2.0,
                                                                                         'point_size': 10.0,
                                                                                         'opacity': 100},
                                                                                        ignore_index=True)
            self.main_window.legend.update_widget(self.main_window)
            self.main_window.prop_legend.update_widget(self.main_window)
        """Then emit signal to update the views."""
        self.main_window.background_added_signal.emit(
            [entity_dict['uid']])  # a list of uids is emitted, even if the entity is just one, for future compatibility
        return entity_dict['uid']

    def remove_entity(self, uid=None):
        """Remove entity from collection."""
        """Remove row from dataframe and reset data model."""
        if not uid in self.get_uids():
            return
        self._df.drop(self.main_window.backgrounds_coll._df[self.main_window.backgrounds_coll._df['uid'] == uid].index, inplace=True)
        self.modelReset.emit()  # is this really necessary?
        """Then remove background_type / feature from legend if needed."""
        """table_updated is used to record if the table is updated or not"""
        table_updated = False
        backgrounds_types_in_legend = pd.unique(self.main_window.backgrounds_legend_df['background_type'])
        features_in_legend = pd.unique(self.main_window.backgrounds_legend_df['background_feature'])
        for background_type in backgrounds_types_in_legend:
            if self.main_window.backgrounds_coll._df.loc[self.main_window.backgrounds_coll._df['background_type'] == background_type].empty:
                """Get index of row to be removed, then remove it in place with .drop()."""
                idx_remove = self.main_window.backgrounds_legend_df[
                    self.main_window.backgrounds_legend_df['background_type'] == background_type].index
                self.main_window.backgrounds_legend_df.drop(idx_remove, inplace=True)
                table_updated = table_updated or True
            for feature in features_in_legend:
                if self.main_window.backgrounds_coll._df.loc[
                    (self.main_window.backgrounds_coll._df['background_type'] == background_type) & (
                            self.main_window.backgrounds_coll._df['background_feature'] == feature)].empty:
                    """Get index of row to be removed, then remove it in place with .drop()."""
                    idx_remove = self.main_window.backgrounds_legend_df[
                        (self.main_window.backgrounds_legend_df['background_type'] == background_type) & (
                                self.main_window.backgrounds_legend_df['background_feature'] == feature)].index
                    self.main_window.backgrounds_legend_df.drop(idx_remove, inplace=True)
                    table_updated = table_updated or True
        for feature in features_in_legend:
            if self.main_window.backgrounds_coll._df.loc[self.main_window.backgrounds_coll._df['background_feature'] == feature].empty:
                """Get index of row to be removed, then remove it in place with .drop()."""
                idx_remove = self.main_window.backgrounds_legend_df[
                    self.main_window.backgrounds_legend_df['background_feature'] == feature].index
                self.main_window.backgrounds_legend_df.drop(idx_remove, inplace=True)
                table_updated = table_updated or True
        """When done, if the table was updated update the widget, and in any case send the signal over to the views."""
        if table_updated:
            self.main_window.legend.update_widget(self.main_window)
            self.main_window.prop_legend.update_widget(self.main_window)
        self.main_window.background_removed_signal.emit([uid])  # a list of uids is emitted, even if the entity is just one
        return uid

    def clone_entity(self, uid=None):
        """Clone an entity. Take care since this sends signals immediately."""
        if not uid in self.get_uids():
            return
        entity_dict = deepcopy(self.background_entity_dict)
        entity_dict['name'] = self.get_uid_name(uid)
        entity_dict['topological_type'] = self.get_uid_topological_type(uid)
        entity_dict['background_type'] = self.get_uid_background_type(uid)
        entity_dict['background_feature'] = self.get_uid_background_feature(uid)
        entity_dict['properties_names'] = self.get_uid_properties_names(uid)
        entity_dict['properties_components'] = self.get_uid_properties_components(uid)
        entity_dict['x_section'] = self.get_uid_x_section(uid)
        entity_dict['borehole'] = self.get_uid_borehole(uid)
        entity_dict['vtk_obj'] = self.get_uid_vtk_obj(uid).deep_copy()
        out_uid = self.add_entity_from_dict(self, entity_dict=entity_dict)
        return out_uid

    def replace_vtk(self, uid=None, vtk_object=None, const_color=False):
        if isinstance(vtk_object, type(self._df.loc[self._df['uid'] == uid, 'vtk_obj'].values[0])):
            new_dict = deepcopy(self._df.loc[self._df['uid'] == uid, self._df.columns != 'vtk_obj'].to_dict('records')[0])
            new_dict['vtk_obj'] = vtk_object
            if const_color:
                R = self.get_uid_legend(uid=uid)['color_R']
                G = self.get_uid_legend(uid=uid)['color_G']
                B = self.get_uid_legend(uid=uid)['color_B']
                color = [R, G, B]
            else:
                color = None
            self.remove_entity(uid)
            self.add_entity_from_dict(entity_dict=new_dict, color=color)
        else:
            print("ERROR - replace_vtk with vtk of a different type.")

    def backgrounds_attr_modified_update_legend_table(self):
        """Update legend table, adding or removing items, based on metadata table.
        This is called when editing the background dataframe with setData(). Slightly different versions
        are found in add_ and remove_entity methods."""
        """table_updated is used to record if the table is updated or not"""
        table_updated = False
        """First remove unused background_type / feature"""
        backgrounds_types_in_legend = pd.unique(self.main_window.backgrounds_legend_df['background_type'])
        features_in_legend = pd.unique(self.main_window.backgrounds_legend_df['background_feature'])
        for background_type in backgrounds_types_in_legend:
            if self.main_window.backgrounds_coll._df.loc[self.main_window.backgrounds_coll._df['background_type'] == background_type].empty:
                """Get index of row to be removed, then remove it in place with .drop()."""
                idx_remove = self.main_window.backgrounds_legend_df[
                    self.main_window.backgrounds_legend_df['background_type'] == background_type].index
                self.main_window.backgrounds_legend_df.drop(idx_remove, inplace=True)
                table_updated = table_updated or True
            for feature in features_in_legend:
                if self.main_window.backgrounds_coll._df.loc[
                    (self.main_window.backgrounds_coll._df['background_type'] == background_type) & (
                            self.main_window.backgrounds_coll._df['background_feature'] == feature)].empty:
                    """Get index of row to be removed, then remove it in place with .drop()."""
                    idx_remove = self.main_window.backgrounds_legend_df[
                        (self.main_window.backgrounds_legend_df['background_type'] == background_type) & (
                                self.main_window.backgrounds_legend_df['background_feature'] == feature)].index
                    self.main_window.backgrounds_legend_df.drop(idx_remove, inplace=True)
                    table_updated = table_updated or True
        for feature in features_in_legend:
            if self.main_window.backgrounds_coll._df.loc[self.main_window.backgrounds_coll._df['background_feature'] == feature].empty:
                """Get index of row to be removed, then remove it in place with .drop()."""
                idx_remove = self.main_window.backgrounds_legend_df[
                    self.main_window.backgrounds_legend_df['background_feature'] == feature].index
                self.main_window.backgrounds_legend_df.drop(idx_remove, inplace=True)
                table_updated = table_updated or True
        """Then add new background_type / feature"""
        for uid in self.main_window.backgrounds_coll._df['uid'].to_list():
            background_type = \
                self.main_window.backgrounds_coll._df.loc[self.main_window.backgrounds_coll._df['uid'] == uid, "type"].values[0]
            feature = \
                self.main_window.backgrounds_coll._df.loc[self.main_window.backgrounds_coll._df['uid'] == uid, "feature"].values[0]
            if self.main_window.backgrounds_legend_df.loc[
                (self.main_window.backgrounds_legend_df['background_type'] == background_type) & (
                        self.main_window.backgrounds_legend_df['background_feature'] == feature)].empty:
                self.main_window.backgrounds_legend_df = self.main_window.backgrounds_legend_df.append(
                    {'background_type': background_type,
                     'background_feature': feature,
                     'color_R': round(np.random.random() * 255),
                     'color_G': round(np.random.random() * 255),
                     'color_B': round(np.random.random() * 255),
                     'line_thick': 2.0},
                    ignore_index=True)
                table_updated = table_updated or True
        """When done, if the table was updated update the widget. No signal is sent here to the views."""
        if table_updated:
            self.main_window.legend.update_widget(self.main_window)

    def get_uid_legend(self, uid=None):
        """Get legend as dictionary from uid."""
        background_type = self._df.loc[self._df['uid'] == uid, 'background_type'].values[0]
        feature = self._df.loc[self._df['uid'] == uid, 'background_feature'].values[0]
        legend_dict = self.main_window.backgrounds_legend_df.loc[
            (self.main_window.backgrounds_legend_df['background_type'] == background_type) & (
                    self.main_window.backgrounds_legend_df['background_feature'] == feature)].to_dict('records')
        return legend_dict[
            0]  # the '[0]' is needed since .to_dict('records') returns a list of dictionaries (with just one element
        # in this case)

    def get_backgrounds_type_uids(self, type=None):
        """Get list of uids of a given type."""
        return self._df.loc[self._df['background_type'] == type, 'uid'].to_list()

    def get_name_uid(self, name=None):
        return self._df.loc[self._df['name'] == name, 'uid'].values[0]

    def get_uid_topological_type(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self._df.loc[self._df['uid'] == uid, 'topological_type'].values[0]

    def set_uid_topological_type(self, uid=None, topological_type=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self._df.loc[self._df['uid'] == uid, 'topological_type'] = topological_type

    def get_uid_background_type(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self._df.loc[self._df['uid'] == uid, 'background_type'].values[0]

    def set_uid_background_type(self, uid=None, type=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self._df.loc[self._df['uid'] == uid, 'background_type'] = type

    def get_uid_background_feature(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self._df.loc[self._df['uid'] == uid, 'background_feature'].values[0]

    def set_uid_background_feature(self, uid=None, feature=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self._df.loc[self._df['uid'] == uid, 'background_feature'] = feature

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

    def get_xuid_uid(self, xuid=None):
        '''[Gabriele] Get the uids of the background objects for the corresponding xsec uid (parent)'''
        return self._df.loc[self._df['x_section'] == xuid, 'uid']

    def get_buid_uid(self, buid=None):
        '''[Gabriele] Get the uids of the background objects for the corresponding bore uid (parent)'''

        return self._df.loc[self._df['borehole'] == buid, 'uid']

    def get_uid_borehole(self, uid=None):

        return self._df.loc[self._df['uid'] == uid, 'borehole'].values[0]

    def set_uid_borehole(self, uid=None, borehole=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self._df.loc[self._df['uid'] == uid, 'x_section'] = borehole

    def get_uid_vtk_obj(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self._df.loc[self._df['uid'] == uid, 'vtk_obj'].values[0]

    def set_uid_vtk_obj(self, uid=None, vtk_obj=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self._df.loc[self._df['uid'] == uid, 'vtk_obj'] = vtk_obj

    def append_uid_property(self, uid=None, property_name=None, property_components=None):
        """Add property name and components to an uid and create empty property on vtk object.
        For some reason here list.append(new_element) does not work"""
        old_properties_names = self.get_uid_properties_names(uid=uid)
        old_properties_components = self.get_uid_properties_components(uid=uid)
        new_properties_names = old_properties_names + [property_name]
        new_properties_components = old_properties_components + [property_components]
        self.set_uid_properties_names(uid=uid, properties_names=new_properties_names)
        self.set_uid_properties_components(uid=uid, properties_components=new_properties_components)
        self.get_uid_vtk_obj(uid=uid).init_point_data(data_key=property_name, dimension=property_components)
        """IN THE FUTURE add cell data"""
        self.main_window.background_metadata_modified_signal.emit([uid])

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
        self.main_window.background_data_keys_removed_signal.emit([uid])

    def get_uid_property_shape(self, uid=None, property_name=None):
        """Returns an array with property data."""
        return self.get_uid_vtk_obj(uid).get_point_data_shape(property_name)

    def get_uid_property(self, uid=None, property_name=None):
        """Returns an array with property data."""
        return self.get_uid_vtk_obj(uid).get_point_data(property_name)

    """Standard QT methods slightly adapted to the data source."""

    def setData(self, index, value, role=Qt.EditRole):
        """This is the method allowing to edit the table and the underlying dataframe.
        "self.main_window is" is used to point to parent, because the standard Qt setData
        method does not allow for extra variables to be passed into this method."""
        if index.isValid():
            self._df.iloc[index.row(), index.column()] = value
            if self.data(index, Qt.DisplayRole) == value:
                self.dataChanged.emit(index, index)
                uid = self._df.iloc[index.row(), 0]
                self.backgrounds_attr_modified_update_legend_table()
                self.main_window.background_metadata_modified_signal.emit(
                    [uid])  # a list of uids is emitted, even if the entity is just one
                return True
        return QVariant()
