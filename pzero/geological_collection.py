"""geological_collection.py
PZero© Andrea Bistacchi"""


from numpy import set_printoptions as np_set_set_printoptions
from numpy import random as np_random
from numpy import round as np_round

from pandas import set_option as pd_set_option
from pandas import DataFrame as pd_DataFrame
from pandas import unique as pd_unique
import uuid
from copy import deepcopy
from PyQt5.QtCore import QAbstractTableModel, Qt, QVariant

"""Options to print Pandas dataframes in console when testing."""
pd_desired_width = 800
pd_max_columns = 20
pd_show_precision = 4
pd_max_colwidth = 80
pd_set_option('display.width', pd_desired_width)
np_set_set_printoptions(linewidth=pd_desired_width)
pd_set_option('display.max_columns', pd_max_columns)
pd_set_option('display.precision', pd_show_precision)
pd_set_option('display.max_colwidth', pd_max_colwidth)


class GeologicalCollection(QAbstractTableModel):
    """
    Initialize GeologicalCollection table.
    Column headers are taken from GeologicalCollection.geological_entity_dict.keys()
    parent is supposed to be the project_window
    """

    """geological_entity_dict is a dictionary of entity metadata used throughout the project.
    Keys define both the geological and topological meaning of entities and values are default values that
    implicitly define types. Always use deepcopy(GeologicalCollection.geological_entity_dict) to
    copy this dictionary without altering the original."""
    geological_entity_dict = {'uid': "",
                              'name': "undef",
                              'topological_type': "undef",
                              'geological_type': "undef",
                              'geological_feature': "undef",
                              'scenario': "undef",
                              'properties_names': [],
                              'properties_components': [],
                              'x_section': "", # this is the uid of the cross section for "XsVertexSet", "XsPolyLine", and "XsImage", empty for all others
                              'vtk_obj': None}

    geological_entity_type_dict = {'uid': str,
                                   'name': str,
                                   'topological_type': str,
                                   'geological_type': str,
                                   'geological_feature': str,
                                   'scenario': str,
                                   'properties_names': list,
                                   'properties_components': list,
                                   'x_section': str,  # this is the uid of the cross section for "XsVertexSet", "XsPolyLine", and "XsImage", empty for all others
                                   'vtk_obj': object}

    """List of valid geological types."""
    valid_geological_types = ["undef",
                              "fault",
                              "intrusive",
                              "unconformity",
                              "top",
                              "bedding",
                              "foliation",
                              "lineation",
                              "axial_surface",
                              "fold_axis"]

    """List of valid data types."""
    valid_topological_type = ["VertexSet", "PolyLine", "TriSurf", "XsVertexSet", "XsPolyLine"]

    """Initialize GeologicalCollection table. Column headers are taken from
    GeologicalCollection.geological_entity_dict.keys(), and parent is supposed to be the project_window."""
    """IN THE FUTURE the edit dialog should be able to edit metadata of multiple entities (and selecting "None" will not change them)."""

    def __init__(self, parent=None, *args, **kwargs):
        super(GeologicalCollection, self).__init__(*args, **kwargs)
        """Import reference to parent, otherwise it is difficult to reference them in SetData() that has a standard list of inputs."""
        self.parent = parent

        """Initialize Pandas dataframe."""
        self.df = pd_DataFrame(columns=list(self.geological_entity_dict.keys()))

        """Here we use .columns.get_indexer to get indexes of the columns that we would like to be editable in the QTableView"""
        self.editable_columns = self.df.columns.get_indexer(["name", "geological_type", "geological_feature", "scenario"])

    """Custom methods used to add or remove entities, query the dataframe, etc."""

    def add_entity_from_dict(self, entity_dict=None,color=None):
        """Add entity to collection from dictionary."""
        """Create a new uid if it is not included in the dictionary."""
        if not entity_dict['uid']:
            entity_dict['uid'] = str(uuid.uuid4())
        """"Append new row to dataframe. Note that the 'append()' method for Pandas dataframes DOES NOT
        work in place, hence a NEW dataframe is created every time and then substituted to the old one."""
        self.df = self.df.append(entity_dict, ignore_index=True)
        """Reset data model"""
        self.modelReset.emit()
        """Then add new geo_type / feature / scenario to the legend if needed."""
        geo_type = entity_dict["geological_type"]
        feature = entity_dict["geological_feature"]
        scenario = entity_dict["scenario"]
        if self.parent.geol_legend_df.loc[(self.parent.geol_legend_df['geological_type'] == geo_type) & (self.parent.geol_legend_df['geological_feature'] == feature) & (self.parent.geol_legend_df['scenario'] == scenario)].empty:
            if color:
                print(color)
                R,G,B = color
            else:
                R,G,B = np_round(np_random.random(3) * 255)
            self.parent.geol_legend_df = self.parent.geol_legend_df.append({'geological_type': geo_type,
                                                                            'geological_feature': feature,
                                                                            'scenario': scenario,
                                                                            'color_R': R,
                                                                            'color_G': G,
                                                                            'color_B': B,
                                                                            'line_thick': 2.0,
                                                                            'opacity': 100,
                                                                            'geological_time': 0.0,
                                                                            'geological_sequence': "strati_0"},
                                                                           ignore_index=True)
            self.parent.legend.update_widget(self.parent)
            self.parent.prop_legend.update_widget(self.parent)
        """Then emit signal to update the views."""
        self.parent.geology_added_signal.emit([entity_dict['uid']])  # a list of uids is emitted, even if the entity is just one, for future compatibility
        return entity_dict['uid']

    def remove_entity(self, uid=None):
        """Remove entity from collection."""
        """Remove row from dataframe and reset data model."""
        if not uid in self.get_uids():
            return
        self.df.drop(self.parent.geol_coll.df[self.parent.geol_coll.df['uid'] == uid].index, inplace=True)
        self.modelReset.emit()  # is this really necessary?
        """Then remove geo_type / feature / scenario from legend if needed."""
        """table_updated is used to record if the table is updated or not"""
        table_updated = False
        geo_types_in_legend = pd_unique(self.parent.geol_legend_df['geological_type'])
        features_in_legend = pd_unique(self.parent.geol_legend_df['geological_feature'])
        scenarios_in_legend = pd_unique(self.parent.geol_legend_df['scenario'])
        for geo_type in geo_types_in_legend:
            if self.parent.geol_coll.df.loc[self.parent.geol_coll.df['geological_type'] == geo_type].empty:
                """Get index of row to be removed, then remove it in place with .drop()."""
                idx_remove = self.parent.geol_legend_df[self.parent.geol_legend_df['geological_type'] == geo_type].index
                self.parent.geol_legend_df.drop(idx_remove, inplace=True)
                table_updated = table_updated or True
            for feature in features_in_legend:
                if self.parent.geol_coll.df.loc[(self.parent.geol_coll.df['geological_type'] == geo_type) & (self.parent.geol_coll.df['geological_feature'] == feature)].empty:
                    """Get index of row to be removed, then remove it in place with .drop()."""
                    idx_remove = self.parent.geol_legend_df[(self.parent.geol_legend_df['geological_type'] == geo_type) & (self.parent.geol_legend_df['geological_feature'] == feature)].index
                    self.parent.geol_legend_df.drop(idx_remove, inplace=True)
                    table_updated = table_updated or True
                for scenario in scenarios_in_legend:
                    if self.parent.geol_coll.df.loc[(self.parent.geol_coll.df['geological_type'] == geo_type) & (self.parent.geol_coll.df['geological_feature'] == feature) & (self.parent.geol_coll.df['scenario'] == scenario)].empty:
                        """Get index of row to be removed, then remove it in place with .drop()."""
                        idx_remove = self.parent.geol_legend_df[(self.parent.geol_legend_df['geological_type'] == geo_type) & (self.parent.geol_legend_df['geological_feature'] == feature) & (self.parent.geol_legend_df['scenario'] == scenario)].index
                        self.parent.geol_legend_df.drop(idx_remove, inplace=True)
                        table_updated = table_updated or True
        for feature in features_in_legend:
            if self.parent.geol_coll.df.loc[self.parent.geol_coll.df['geological_feature'] == feature].empty:
                """Get index of row to be removed, then remove it in place with .drop()."""
                idx_remove = self.parent.geol_legend_df[self.parent.geol_legend_df['geological_feature'] == feature].index
                self.parent.geol_legend_df.drop(idx_remove, inplace=True)
                table_updated = table_updated or True
            for scenario in scenarios_in_legend:
                if self.parent.geol_coll.df.loc[(self.parent.geol_coll.df['geological_feature'] == feature) & (self.parent.geol_coll.df['scenario'] == scenario)].empty:
                    """Get index of row to be removed, then remove it in place with .drop()."""
                    idx_remove = self.parent.geol_legend_df[(self.parent.geol_legend_df['geological_feature'] == feature) & (self.parent.geol_legend_df['scenario'] == scenario)].index
                    self.parent.geol_legend_df.drop(idx_remove, inplace=True)
                    table_updated = table_updated or True
        for scenario in scenarios_in_legend:
            if self.parent.geol_coll.df.loc[self.parent.geol_coll.df['scenario'] == scenario].empty:
                """Get index of row to be removed, then remove it in place with .drop()."""
                idx_remove = self.parent.geol_legend_df[self.parent.geol_legend_df['scenario'] == scenario].index
                self.parent.geol_legend_df.drop(idx_remove, inplace=True)
                table_updated = table_updated or True
        """When done, if the table was updated update the widget, and in any case send the signal over to the views."""
        if table_updated:
            self.parent.legend.update_widget(self.parent)
            self.parent.prop_legend.update_widget(self.parent)
        self.parent.geology_removed_signal.emit([uid])  # a list of uids is emitted, even if the entity is just one
        return uid

    def clone_entity(self, uid=None):
        """Clone an entity. Take care since this sends signals immediately."""
        if not uid in self.get_uids():
            return
        entity_dict = deepcopy(self.geological_entity_dict)
        entity_dict['name'] = self.get_uid_name(uid)
        entity_dict['topological_type'] = self.get_uid_topological_type(uid)
        entity_dict['geological_type'] = self.get_uid_geological_type(uid)
        entity_dict['geological_feature'] = self.get_uid_geological_feature(uid)
        entity_dict['scenario'] = self.get_uid_scenario(uid)
        entity_dict['properties_names'] = self.get_uid_properties_names(uid)
        entity_dict['properties_components'] = self.get_uid_properties_components(uid)
        entity_dict['x_section'] = self.get_uid_x_section(uid)
        entity_dict['vtk_obj'] = self.get_uid_vtk_obj(uid).deep_copy()
        out_uid = self.add_entity_from_dict(self, entity_dict=entity_dict)
        return out_uid

    def replace_vtk(self, uid=None, vtk_object=None, const_color=False):
        if isinstance(vtk_object, type(self.df.loc[self.df['uid'] == uid, 'vtk_obj'].values[0])):
            new_dict = deepcopy(self.df.loc[self.df['uid'] == uid, self.df.columns != 'vtk_obj'].to_dict('records')[0])
            new_dict['vtk_obj'] = vtk_object
            if const_color:
                R = self.get_uid_legend(uid=uid)['color_R']
                G = self.get_uid_legend(uid=uid)['color_G']
                B = self.get_uid_legend(uid=uid)['color_B']
                color = [R,G,B]
            else:
                color=None
            self.remove_entity(uid)
            self.add_entity_from_dict(entity_dict=new_dict, color=color)
        else:
            print("ERROR - replace_vtk with vtk of a different type.")

    def geology_attr_modified_update_legend_table(self):
        """Update legend table, adding or removing items, based on metadata table.
        This is called when editing the geological dataframe with setData(). Slightly different versions
        are found in add_ and remove_entity methods."""
        """table_updated is used to record if the table is updated or not"""
        table_updated = False
        """First remove unused geo_type / feature"""
        geo_types_in_legend = pd_unique(self.parent.geol_legend_df['geological_type'])
        features_in_legend = pd_unique(self.parent.geol_legend_df['geological_feature'])
        scenarios_in_legend = pd_unique(self.parent.geol_legend_df['scenario'])
        for geo_type in geo_types_in_legend:
            if self.parent.geol_coll.df.loc[self.parent.geol_coll.df['geological_type'] == geo_type].empty:
                """Get index of row to be removed, then remove it in place with .drop()."""
                idx_remove = self.parent.geol_legend_df[self.parent.geol_legend_df['geological_type'] == geo_type].index
                self.parent.geol_legend_df.drop(idx_remove, inplace=True)
                table_updated = table_updated or True
            for feature in features_in_legend:
                if self.parent.geol_coll.df.loc[(self.parent.geol_coll.df['geological_type'] == geo_type) & (self.parent.geol_coll.df['geological_feature'] == feature)].empty:
                    """Get index of row to be removed, then remove it in place with .drop()."""
                    idx_remove = self.parent.geol_legend_df[(self.parent.geol_legend_df['geological_type'] == geo_type) & (self.parent.geol_legend_df['geological_feature'] == feature)].index
                    self.parent.geol_legend_df.drop(idx_remove, inplace=True)
                    table_updated = table_updated or True
                for scenario in scenarios_in_legend:
                    if self.parent.geol_coll.df.loc[(self.parent.geol_coll.df['geological_type'] == geo_type) & (self.parent.geol_coll.df['geological_feature'] == feature) & (self.parent.geol_coll.df['scenario'] == scenario)].empty:
                        """Get index of row to be removed, then remove it in place with .drop()."""
                        idx_remove = self.parent.geol_legend_df[(self.parent.geol_legend_df['geological_type'] == geo_type) & (self.parent.geol_legend_df['geological_feature'] == feature) & (self.parent.geol_legend_df['scenario'] == scenario)].index
                        self.parent.geol_legend_df.drop(idx_remove, inplace=True)
                        table_updated = table_updated or True
        for feature in features_in_legend:
            if self.parent.geol_coll.df.loc[self.parent.geol_coll.df['geological_feature'] == feature].empty:
                """Get index of row to be removed, then remove it in place with .drop()."""
                idx_remove = self.parent.geol_legend_df[self.parent.geol_legend_df['geological_feature'] == feature].index
                self.parent.geol_legend_df.drop(idx_remove, inplace=True)
                table_updated = table_updated or True
            for scenario in scenarios_in_legend:
                if self.parent.geol_coll.df.loc[(self.parent.geol_coll.df['geological_feature'] == feature) & (self.parent.geol_coll.df['scenario'] == scenario)].empty:
                    """Get index of row to be removed, then remove it in place with .drop()."""
                    idx_remove = self.parent.geol_legend_df[(self.parent.geol_legend_df['geological_feature'] == feature) & (self.parent.geol_legend_df['scenario'] == scenario)].index
                    self.parent.geol_legend_df.drop(idx_remove, inplace=True)
                    table_updated = table_updated or True
        for scenario in scenarios_in_legend:
            if self.parent.geol_coll.df.loc[self.parent.geol_coll.df['scenario'] == scenario].empty:
                """Get index of row to be removed, then remove it in place with .drop()."""
                idx_remove = self.parent.geol_legend_df[self.parent.geol_legend_df['scenario'] == scenario].index
                self.parent.geol_legend_df.drop(idx_remove, inplace=True)
                table_updated = table_updated or True
        """Then add new geo_type / feature"""
        for uid in self.parent.geol_coll.df['uid'].to_list():
            geo_type = self.parent.geol_coll.df.loc[self.parent.geol_coll.df['uid'] == uid, "geological_type"].values[0]
            feature = self.parent.geol_coll.df.loc[self.parent.geol_coll.df['uid'] == uid, "geological_feature"].values[0]
            scenario = self.parent.geol_coll.df.loc[self.parent.geol_coll.df['uid'] == uid, "scenario"].values[0]
            if self.parent.geol_legend_df.loc[(self.parent.geol_legend_df['geological_type'] == geo_type) & (self.parent.geol_legend_df['geological_feature'] == feature) & (self.parent.geol_legend_df['scenario'] == scenario)].empty:
                self.parent.geol_legend_df = self.parent.geol_legend_df.append({'geological_type': geo_type,
                                                                                'geological_feature': feature,
                                                                                'scenario': scenario,
                                                                                'color_R': round(np_random.random() * 255),
                                                                                'color_G': round(np_random.random() * 255),
                                                                                'color_B': round(np_random.random() * 255),
                                                                                'line_thick': 2.0,
                                                                                'geological_time': 0.0,
                                                                                'geological_sequence': "strati_0"},
                                                                               ignore_index=True)
                table_updated = table_updated or True
        """When done, if the table was updated update the widget. No signal is sent here to the views."""
        if table_updated:
            self.parent.legend.update_widget(self.parent)

    def get_number_of_entities(self):
        """Get number of entities stored in Pandas dataframe."""
        return self.df.shape[0]

    def get_uid_legend(self, uid=None):
        """Get legend as dictionary from uid."""
        geo_type = self.df.loc[self.df['uid'] == uid, 'geological_type'].values[0]
        feature = self.df.loc[self.df['uid'] == uid, 'geological_feature'].values[0]
        scenario = self.df.loc[self.df['uid'] == uid, 'scenario'].values[0]
        legend_dict = self.parent.geol_legend_df.loc[(self.parent.geol_legend_df['geological_type'] == geo_type) & (self.parent.geol_legend_df['geological_feature'] == feature) & (self.parent.geol_legend_df['scenario'] == scenario)].to_dict('records')
        return legend_dict[0]  # the '[0]' is needed since .to_dict('records') returns a list of dictionaries (with just one element in this case)

    def get_uids(self):
        """Get list of uids."""
        return self.df['uid'].to_list()

    def get_topological_type_uids(self, topological_type=None):
        """Get list of uids of a given topological_type."""
        return self.df.loc[self.df['topological_type'] == topological_type, 'uid'].to_list()

    def get_geological_type_uids(self, geological_type=None):
        """Get list of uids of a given geological_type."""
        return self.df.loc[self.df['geological_type'] == geological_type, 'uid'].to_list()

    def get_uid_name(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df['uid'] == uid, 'name'].values[0]

    def set_uid_name(self, uid=None, name=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df['uid'] == uid, 'name'] = name

    def get_name_uid(self,name=None):
        return self.df.loc[self.df['name'] == name, 'uid'].values[0]

    def get_uid_topological_type(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df['uid'] == uid, 'topological_type'].values[0]

    def set_uid_topological_type(self, uid=None, topological_type=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df['uid'] == uid, 'topological_type'] = topological_type

    def get_uid_geological_type(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df['uid'] == uid, 'geological_type'].values[0]

    def set_uid_geological_type(self, uid=None, geological_type=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df['uid'] == uid, 'geological_type'] = geological_type

    def get_uid_geological_feature(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df['uid'] == uid, 'geological_feature'].values[0]

    def set_uid_geological_feature(self, uid=None, geological_feature=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df['uid'] == uid, 'geological_feature'] = geological_feature

    def get_uid_scenario(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df['uid'] == uid, 'scenario'].values[0]

    def set_uid_scenario(self, uid=None, scenario=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df['uid'] == uid, 'scenario'] = scenario

    def get_uid_properties_names(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid. This is a LIST even if we extract it with values[0]!"""
        return self.df.loc[self.df['uid'] == uid, 'properties_names'].values[0]

    def set_uid_properties_names(self, uid=None, properties_names=None):
        """Set value(s) stored in dataframe (as pointer) from uid. This is a LIST and "at" must be used!"""
        row = self.df[self.df['uid'] == uid].index.values[0]
        self.df.at[row, 'properties_names'] = properties_names

    def get_uid_properties_components(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid. This is a LIST even if we extract it with values[0]!"""
        return self.df.loc[self.df['uid'] == uid, 'properties_components'].values[0]

    def set_uid_properties_components(self, uid=None, properties_components=None):
        """Set value(s) stored in dataframe (as pointer) from uid. This is a LIST and "at" must be used!"""
        row = self.df[self.df['uid'] == uid].index.values[0]
        self.df.at[row, 'properties_components'] = properties_components

    def get_uid_x_section(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df['uid'] == uid, 'x_section'].values[0]

    def set_uid_x_section(self, uid=None, x_section=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df['uid'] == uid, 'x_section'] = x_section

    def get_xuid_uid(self,xuid=None):
        '''[Gabriele] Get the uids of the geological objects for the corresponding xsec uid (parent)'''
        return self.df.loc[self.df['x_section']== xuid, 'uid']

    def get_uid_vtk_obj(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df['uid'] == uid, 'vtk_obj'].values[0]

    def set_uid_vtk_obj(self, uid=None, vtk_obj=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df['uid'] == uid, 'vtk_obj'] = vtk_obj

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
        self.parent.geology_metadata_modified_signal.emit([uid])

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
        self.parent.geology_data_keys_removed_signal.emit([uid])

    def get_uid_property_shape(self, uid=None, property_name=None):
        """Returns an array with property data."""
        return self.get_uid_vtk_obj(uid).get_point_data_shape(property_name)

    def get_uid_property(self, uid=None, property_name=None):
        """Returns an array with property data."""
        return self.get_uid_vtk_obj(uid).get_point_data(property_name)

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
                self.geology_attr_modified_update_legend_table()
                self.parent.geology_metadata_modified_signal.emit([uid])  # a list of uids is emitted, even if the entity is just one
                return True
        return QVariant()
