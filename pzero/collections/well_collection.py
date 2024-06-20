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

    def __init__(self, parent=None, *args, **kwargs):
        super(WellCollection, self).__init__(*args, **kwargs)

        self.parent = parent

        self.entity_dict = {
            "uid": "",
            "Loc ID": "undef",
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
            "properties_names": list,
            "properties_components": list,
            "properties_types": list,
            "markers": list,
            "x_section": str,
            "vtk_obj": object,
        }

        self.valid_topological_types = [
            "VertexSet",
            "PolyLine",
            "XsVertexSet",
            "XsPolyLine",
        ]

        self.editable_columns_names = ["name"]

        self.collection_name = 'wells'

        self.initialize_df()

    def add_entity_from_dict(self, entity_dict: DataFrame = None, color: ndarray = None):
        if not entity_dict["uid"]:
            entity_dict["uid"] = str(uuid.uuid4())
        """"Append new row to dataframe. Note that the 'append()' method for Pandas dataframes DOES NOT
        work in place, hence a NEW dataframe is created every time and then substituted to the old one."""
        self.df = self.df.append(entity_dict, ignore_index=True)
        """Reset data model"""
        self.modelReset.emit()
        self.parent.prop_legend.update_widget(self.parent)
        """Then emit signal to update the views."""
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
        """Then emit signal to update the views."""
        self.parent.well_added_signal.emit(
            [entity_dict["uid"]]
        )  # a list of uids is emitted, even if the entity is just one
        return entity_dict["uid"]

    def remove_entity(self, uid: str = None) -> str:
        self.df.drop(self.df[self.df["uid"] == uid].index, inplace=True)
        self.modelReset.emit()  # is this really necessary?
        self.parent.prop_legend.update_widget(self.parent)
        """When done, send a signal over to the views."""
        self.parent.well_removed_signal.emit(
            [uid]
        )  # a list of uids is emitted, even if the entity is just one
        return uid

    def clone_entity(self, uid: str = None) -> str:
        pass

    def replace_vtk(self, uid: str = None, vtk_object: vtkDataObject = None, const_color: bool = True):
        if isinstance(
                vtk_object, type(self.df.loc[self.df["uid"] == uid, "vtk_obj"].values[0])
        ):
            new_dict = deepcopy(
                self.df.loc[
                    self.df["uid"] == uid, self.df.columns != "vtk_obj"
                ].to_dict("records")[0]
            )
            new_dict["vtk_obj"] = vtk_object
            self.remove_entity(uid)
            self.add_entity_from_dict(entity_dict=new_dict)
        else:
            print("ERROR - replace_vtk with vtk of a different type.")

    def attr_modified_update_legend_table(self):
        table_updated = False
        """First remove unused locid / feature"""
        locid_in_legend = pd_unique(self.parent.well_legend_df["Loc ID"])
        features_in_legend = pd_unique(self.parent.well_legend_df["geological_feature"])
        for loc_id in locid_in_legend:
            if self.parent.well_coll.df.loc[
                self.parent.well_coll.df["Loc ID"] == loc_id
            ].empty:
                """Get index of row to be removed, then remove it in place with .drop()."""
                idx_remove = self.parent.well_legend_df[
                    self.parent.well_legend_df["Loc ID"] == loc_id
                    ].index
                self.parent.well_legend_df.drop(idx_remove, inplace=True)
                table_updated = table_updated or True
            for feature in features_in_legend:
                if self.parent.well_coll.df.loc[
                    (self.parent.well_coll.df["Loc ID"] == loc_id)
                    & (self.parent.well_coll.df["geological_feature"] == feature)
                ].empty:
                    """Get index of row to be removed, then remove it in place with .drop()."""
                    idx_remove = self.parent.well_legend_df[
                        (self.parent.well_legend_df["Loc ID"] == loc_id)
                        & (self.parent.well_legend_df["geological_feature"] == feature)
                        ].index
                    self.parent.well_legend_df.drop(idx_remove, inplace=True)
                    table_updated = table_updated or True

        for feature in features_in_legend:
            if self.parent.well_coll.df.loc[
                self.parent.well_coll.df["geological_feature"] == feature
            ].empty:
                """Get index of row to be removed, then remove it in place with .drop()."""
                idx_remove = self.parent.well_legend_df[
                    self.parent.well_legend_df["geological_feature"] == feature
                    ].index
                self.parent.well_legend_df.drop(idx_remove, inplace=True)
                table_updated = table_updated or True

        """Then add new locid / feature"""
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
                table_updated = table_updated or True
        """When done, if the table was updated update the widget. No signal is sent here to the views."""
        if table_updated:
            self.parent.legend.update_widget(self.parent)

    def get_uid_legend(self, uid: str = None) -> dict:
        locid = self.df.loc[self.df["uid"] == uid, "Loc ID"].values[0]

        legend_dict = self.parent.well_legend_df.loc[
            self.parent.well_legend_df["Loc ID"] == locid
            ].to_dict("records")

        return legend_dict[0]

    def set_uid_legend(self, uid: str = None, color_R: float = None, color_G: float = None, color_B: float = None,
                       line_thick: float = None, point_size: float = None, opacity: float = None):
        pass

    def metadata_modified_signal(self, updated_list: list = None):
        self.parent.well_metadata_modified_signal.emit(updated_list)

    def data_keys_removed_signal(self, updated_list: list = None):
        self.parent.well_data_keys_removed_signal.emit(updated_list)

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


class WellCollection(QAbstractTableModel):
    """
    Initialize WellCollection table.
    Column headers are taken from WellCollection.well_entity_dict.keys()
    parent is supposed to be the project_window
    """

    """well_entity_dict is a dictionary of entity metadata used throughout the project.
    Keys define both the well and topological meaning of entities and values are default values that
    implicitly define types. Always use deepcopy(WellCollection.well_entity_dict) to
    copy this dictionary without altering the original."""
    well_entity_dict = {
        "uid": "",
        "Loc ID": "undef",
        "properties_names": [],
        "properties_components": [],
        "properties_types": [],
        "markers": [],
        "x_section": [], # this is the uid of the cross section for "XsVertexSet", "XsPolyLine", and "XsImage", empty for all others
        "vtk_obj": None,
    }

    well_entity_type_dict = {
        "uid": str,
        "Loc ID": str,
        "properties_names": list,
        "properties_components": list,
        "properties_types": list,
        "markers": list,
        "x_section": str,
        "vtk_obj": object,
    }

    """Initialize WellCollection table. Column headers are taken from
    WellCollection.well_entity_dict.keys(), and parent is supposed to be the project_window."""
    """IN THE FUTURE the edit dialog should be able to edit metadata of multiple entities (and selecting "None" will not change them)."""

    def __init__(self, parent=None, *args, **kwargs):
        super(WellCollection, self).__init__(*args, **kwargs)
        """Import reference to parent, otherwise it is difficult to reference them in SetData() that has a standard list of inputs."""
        self.parent = parent
        """Initialize Pandas dataframe."""
        self.df = pd_DataFrame(columns=list(self.well_entity_dict.keys()))
        """Here we use .columns.get_indexer to get indexes of the columns that we would like to be editable in the QTableView"""
        self.editable_columns = self.df.columns.get_indexer(["name"])

    """Custom methods used to add or remove entities, query the dataframe, etc."""

    def add_entity_from_dict(self, entity_dict=None, color=None):
        """Add entity to collection from dictionary.
        Create a new uid if it is not included in the dictionary."""
        if not entity_dict["uid"]:
            entity_dict["uid"] = str(uuid.uuid4())
        """"Append new row to dataframe. Note that the 'append()' method for Pandas dataframes DOES NOT
        work in place, hence a NEW dataframe is created every time and then substituted to the old one."""
        self.df = self.df.append(entity_dict, ignore_index=True)
        """Reset data model"""
        self.modelReset.emit()
        self.parent.prop_legend.update_widget(self.parent)
        """Then emit signal to update the views."""
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
        """Then emit signal to update the views."""
        self.parent.well_added_signal.emit(
            [entity_dict["uid"]]
        )  # a list of uids is emitted, even if the entity is just one
        return entity_dict["uid"]

    def remove_entity(self, uid=None):
        """Remove entity from collection. Remove row from dataframe and reset data model."""
        self.df.drop(self.df[self.df["uid"] == uid].index, inplace=True)
        self.modelReset.emit()  # is this really necessary?
        self.parent.prop_legend.update_widget(self.parent)
        """When done, send a signal over to the views."""
        self.parent.well_removed_signal.emit(
            [uid]
        )  # a list of uids is emitted, even if the entity is just one
        return uid

    def replace_vtk(self, uid=None, vtk_object=None):
        if isinstance(
            vtk_object, type(self.df.loc[self.df["uid"] == uid, "vtk_obj"].values[0])
        ):
            new_dict = deepcopy(
                self.df.loc[
                    self.df["uid"] == uid, self.df.columns != "vtk_obj"
                ].to_dict("records")[0]
            )
            new_dict["vtk_obj"] = vtk_object
            self.remove_entity(uid)
            self.add_entity_from_dict(entity_dict=new_dict)
        else:
            print("ERROR - replace_vtk with vtk of a different type.")

    def well_attr_modified_update_legend_table(self):
        table_updated = False
        """First remove unused locid / feature"""
        locid_in_legend = pd_unique(self.parent.well_legend_df["Loc ID"])
        features_in_legend = pd_unique(self.parent.well_legend_df["geological_feature"])
        for loc_id in locid_in_legend:
            if self.parent.well_coll.df.loc[
                self.parent.well_coll.df["Loc ID"] == loc_id
            ].empty:
                """Get index of row to be removed, then remove it in place with .drop()."""
                idx_remove = self.parent.well_legend_df[
                    self.parent.well_legend_df["Loc ID"] == loc_id
                ].index
                self.parent.well_legend_df.drop(idx_remove, inplace=True)
                table_updated = table_updated or True
            for feature in features_in_legend:
                if self.parent.well_coll.df.loc[
                    (self.parent.well_coll.df["Loc ID"] == loc_id)
                    & (self.parent.well_coll.df["geological_feature"] == feature)
                ].empty:
                    """Get index of row to be removed, then remove it in place with .drop()."""
                    idx_remove = self.parent.well_legend_df[
                        (self.parent.well_legend_df["Loc ID"] == loc_id)
                        & (self.parent.well_legend_df["geological_feature"] == feature)
                    ].index
                    self.parent.well_legend_df.drop(idx_remove, inplace=True)
                    table_updated = table_updated or True

        for feature in features_in_legend:
            if self.parent.well_coll.df.loc[
                self.parent.well_coll.df["geological_feature"] == feature
            ].empty:
                """Get index of row to be removed, then remove it in place with .drop()."""
                idx_remove = self.parent.well_legend_df[
                    self.parent.well_legend_df["geological_feature"] == feature
                ].index
                self.parent.well_legend_df.drop(idx_remove, inplace=True)
                table_updated = table_updated or True

        """Then add new locid / feature"""
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
                table_updated = table_updated or True
        """When done, if the table was updated update the widget. No signal is sent here to the views."""
        if table_updated:
            self.parent.legend.update_widget(self.parent)

    def get_number_of_entities(self):
        """Get number of entities stored in Pandas dataframe."""
        return self.df.shape[0]

    def get_uid_legend(self, uid=None):
        """Get legend as dictionary from uid."""
        locid = self.df.loc[self.df["uid"] == uid, "Loc ID"].values[0]

        legend_dict = self.parent.well_legend_df.loc[
            self.parent.well_legend_df["Loc ID"] == locid
        ].to_dict("records")
        # print(legend_dict[0])
        return legend_dict[
            0
        ]  # the '[0]' is needed since .to_dict('records') returns a list of dictionaries (with just one element in this case)

    def get_uids(self):
        """Get list of uids."""
        return self.df["uid"].to_list()

    def get_well_locid_uids(self, locid=None):
        """Get list of uids of a given locid."""
        return self.df.loc[self.df["Loc ID"] == locid, "uid"].to_list()

    def get_uid_name(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df["uid"] == uid, "Loc ID"].values[0]

    def set_uid_name(self, uid=None, name=None):
        """Set value(s) stored in dataframe (as pointer) from uid.."""
        self.df.loc[self.df["uid"] == uid, "name"] = name

    def get_uid_well_locid(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df["uid"] == uid, "Loc ID"].values[0]

    def set_uid_well_locid(self, uid=None, locid=None):
        """Set value(s) stored in dataframe (as pointer) from uid.."""
        self.df.loc[self.df["uid"] == uid, "Loc ID"] = locid

    def get_uid_geological_feature(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df["uid"] == uid, "geological_feature"].values[0]

    def set_uid_geological_feature(self, uid=None, geological_feature=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df["uid"] == uid, "geological_feature"] = geological_feature

    def get_uid_properties_names(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid. This is a LIST even if we extract it with values[0]!"""
        return self.df.loc[self.df["uid"] == uid, "properties_names"].values[0]

    def set_uid_properties_names(self, uid=None, properties_names=None):
        """Set value(s) stored in dataframe (as pointer) from uid. This is a LIST and "at" must be used!"""
        row = self.df[self.df["uid"] == uid].index.values[0]
        self.df.at[row, "properties_names"] = properties_names

    def get_uid_properties_components(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid. This is a LIST even if we extract it with values[0]!"""
        return self.df.loc[self.df["uid"] == uid, "properties_components"].values[0]

    def set_uid_properties_components(self, uid=None, properties_components=None):
        """Set value(s) stored in dataframe (as pointer) from uid. This is a LIST and "at" must be used!"""
        row = self.df[self.df["uid"] == uid].index.values[0]
        self.df.at[row, "properties_components"] = properties_components

    def get_uid_marker_names(self, uid=None):
        return self.df.loc[self.df["uid"] == uid, "markers"].values[0]

    def get_uid_vtk_obj(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df["uid"] == uid, "vtk_obj"].values[0]

    def set_uid_vtk_obj(self, uid=None, vtk_obj=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df["uid"] == uid, "vtk_obj"] = vtk_obj

    def append_uid_property(
        self, uid=None, property_name=None, property_components=None
    ):
        """Add property name and components to an uid and create empty property on vtk object.
        For some reason here list.append(new_eleemnt) does not work"""
        old_properties_names = self.get_uid_properties_names(uid=uid)
        old_properties_components = self.get_uid_properties_components(uid=uid)
        new_properties_names = old_properties_names + [property_name]
        new_properties_components = old_properties_components + [property_components]
        self.set_uid_properties_names(uid=uid, properties_names=new_properties_names)
        self.set_uid_properties_components(
            uid=uid, properties_components=new_properties_components
        )
        self.get_uid_vtk_obj(uid=uid).init_point_data(
            data_key=property_name, dimension=property_components
        )
        """IN THE FUTURE add cell data"""
        # self.parent.prop_legend.update_widget(self.parent)
        self.parent.well_metadata_modified_signal.emit([uid])

    def remove_uid_property(self, uid=None, property_name=None):
        """Remove property name and components from an uid and remove property on vtk object.
        Note that pop() works in place (its output is the removed element)."""
        idx = self.get_uid_properties_names(uid=uid).index(property_name)
        properties_names = self.get_uid_properties_names(uid=uid)
        properties_components = self.get_uid_properties_components(uid=uid)
        properties_names.pop(idx)
        properties_components.pop(idx)
        self.set_uid_properties_names(uid=uid, properties_names=properties_names)
        self.set_uid_properties_components(
            uid=uid, properties_components=properties_components
        )
        self.get_uid_vtk_obj(uid=uid).remove_point_data(data_key=property_name)
        """IN THE FUTURE add cell data"""
        # self.parent.prop_legend.update_widget(self.parent)
        self.parent.well_data_keys_removed_signal.emit([uid])

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
            return Qt.ItemFlags(
                QAbstractTableModel.flags(self, index) | Qt.ItemIsEditable
            )
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
                self.well_attr_modified_update_legend_table()
                self.parent.well_metadata_modified_signal.emit(
                    [uid]
                )  # a list of uids is emitted, even if the entity is just one
                return True
        return QVariant()
