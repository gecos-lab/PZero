from PyQt5.QtCore import QAbstractTableModel, Qt, QVariant
from abc import abstractmethod, ABC

from pandas import DataFrame
import numpy.typing as npt
from numpy import ndarray
import numpy as np
from vtkmodules.vtkCommonDataModel import vtkDataObject


class Meta(type(ABC), type(QAbstractTableModel)):
    required_attributes = []

    def __call__(self, *args, **kwargs):
        obj = super(Meta, self).__call__(*args, **kwargs)
        for attr_name in obj.required_attributes:
            if not getattr(obj, attr_name):
                raise ValueError('required attribute (%s) not set' % attr_name)
        return obj


class BaseCollection(QAbstractTableModel, ABC, metaclass=Meta):
    required_attributes = ['parent', 'entity_dict', 'entity_type_dict', 'valid_topological_types',
                           'editable_columns_names', 'collection_name']

    def __init__(self, *args, **kwargs):
        super(BaseCollection, self).__init__(*args, **kwargs)
        """Import reference to parent, otherwise it is difficult to reference them in SetData() 
        that has a standard list of inputs."""

        self._parent = None
        self._entity_dict: dict = dict()
        self._entity_type_dict: dict = dict()
        self._valid_types: list = list()
        self._valid_topological_types: list = list()
        self._df: DataFrame = DataFrame()
        self._editable_columns_names: list = list()
        self._collection_name: str = ''
    # =========================== Abstract (obligatory) methods ================================

    @abstractmethod
    def add_entity_from_dict(self, entity_dict: DataFrame = None, color: ndarray = None):
        """Add entity to collection from dictionary."""

        pass

    @abstractmethod
    def remove_entity(self, uid: str = None) -> str:
        """Remove entity from collection."""

        pass

    @abstractmethod
    def clone_entity(self, uid: str = None) -> str:
        """Clone an entity. Take care since this sends signals immediately (?)."""

        pass

    @abstractmethod
    def replace_vtk(self, uid: str = None, vtk_object: vtkDataObject = None, const_color: bool = True):
        """
        Replace the vtk object of a given uid with another vtkobject. Const_color is a flag, if True the color is
        maintained while if False it is generated again
        """

        pass

    @abstractmethod
    def attr_modified_update_legend_table(self):
        """Update legend table, adding or removing items, based on metadata table.
        This is called when editing the geological dataframe with setData(). Slightly different versions
        are found in add_entity_from_dict and remove_entity methods."""

        pass

    @abstractmethod
    def get_uid_legend(self, uid: str = None) -> dict:
        """Get legend as dictionary from uid."""

        pass

    @abstractmethod
    def set_uid_legend(self,
                       uid: str = None,
                       color_R: float = None,
                       color_G: float = None,
                       color_B: float = None,
                       line_thick: float = None,
                       point_size: float = None,
                       opacity: float = None,
                       ):
        """Set legend properties from uid. Take care since this resets the legend for all similar objects."""

        pass

    @abstractmethod
    def metadata_modified_signal(self, updated_list: list = None):
        """
        Method used to emit the metadata modified signal for the given collection
        """

        pass

    @abstractmethod
    def data_keys_removed_signal(self, updated_list: list = None):
        """
        Method used to emit the data keys removed signal modified signal for the given collection
        """

        pass

    # @staticmethod
    # @abstractmethod
    # def import_data(path: str):
    #     pass
    # =================================== Common properties ================================================

    @property
    def parent(self):
        """
        Get or set the parent of the Collection
        """
        return self._parent

    @parent.setter
    def parent(self, parent):
        self._parent = parent

    @property
    def entity_dict(self) -> dict:
        """
        Get or set the entity dict of the Collection
        """
        return self._entity_dict

    @entity_dict.setter
    def entity_dict(self, entity_dict: dict):
        self._entity_dict = entity_dict

    @property
    def entity_type_dict(self) -> dict:
        """
        Get or set the entity type dict of the Collection
        """

        return self._entity_type_dict

    @entity_type_dict.setter
    def entity_type_dict(self, entity_type_dict: dict):
        self._entity_type_dict = entity_type_dict

    @property
    def valid_types(self) -> list:
        """
        Get or set the valid types list of the Collection
        """

        return self._valid_types

    @valid_types.setter
    def valid_types(self, valid_types: list):
        self._valid_types = valid_types

    @property
    def valid_topological_types(self) -> list:
        """
        Get or set the valid topological list of the Collection
        """

        return self._valid_topological_types

    @valid_topological_types.setter
    def valid_topological_types(self, valid_topological_types: list):
        self._valid_topological_types = valid_topological_types

    @property
    def editable_columns_names(self):
        """
        Get or set the editable columns names of the Collection
        """

        return self._editable_columns_names

    @editable_columns_names.setter
    def editable_columns_names(self, editable_columns_names: list):
        self._editable_columns_names = editable_columns_names

    @property
    def df(self) -> DataFrame:
        """
        Get or set the dataframe of the Collection
        """

        return self._df

    @df.setter
    def df(self, df: DataFrame):
        self._df = df

    @property
    def collection_name(self) -> str:
        """
        Get or set the collection name
        """

        return self._collection_name

    @collection_name.setter
    def collection_name(self, name: str):

        self._collection_name = name

    @property
    def coll_type_name(self) -> str:
        """
        Helper property to get the full collection type column name for the given collection
        """

        return f'{self.collection_name}_type'

    @property
    def coll_feature_name(self) -> str:
        """
        Helper property to get the full collection feature column name for the given collection
        """

        return f'{self.collection_name}_feature'

    @property
    def entity_dict_keys(self) -> list:
        """
        Get the entity dict keys as a list
        """

        return list(self.entity_dict.keys())

    @property
    def editable_columns(self) -> npt.NDArray[np.intp]:
        """Here we use .columns.get_indexer to get indexes of the columns
        that we would like to be editable in the QTableView"""

        return self.df.columns.get_indexer(self.editable_columns_names)

    @property
    def get_number_of_entities(self) -> int:
        """Get number of entities stored in Pandas dataframe."""

        return self.df.shape[0]

    @property
    def get_uids(self) -> list:
        """Get list of uids."""

        return self.df["uid"].to_list()

    @property
    def get_names(self) -> list:
        """Get list of names."""

        return self.df["name"].to_list()

    # =================================== Common methods ================================================

    def initialize_df(self):
        """Initialize Pandas dataframe."""
        self.df = DataFrame(columns=self.entity_dict_keys)

    def get_topological_type_uids(self, topological_type: str = None) -> list:
        """Get list of uids of a given topological_type."""

        # Use the query method

        return self.df.loc[
            self.df["topological_type"] == topological_type, "uid"
        ].to_list()

    def get_uid_name(self, uid: str = None) -> str:
        """Get value(s) stored in dataframe (as pointer) from uid."""

        # Use the query method

        return self.df.loc[self.df["uid"] == uid, "name"].values[0]

    def set_uid_name(self, uid: str = None, name: str = None):
        """Set value(s) stored in dataframe (as pointer) from uid."""

        self.df.loc[self.df["uid"] == uid, "name"] = name

    def get_name_uid(self, name=None) -> list:
        """
        Get a list of uids corresponding to a given name.
        """
        return self.df.loc[self.df["name"] == name, "uid"].to_list()

    def get_uid_topological_type(self, uid: str = None) -> str:
        """Get value topological type from uid."""

        return self.df.loc[self.df["uid"] == uid, "topological_type"].values[0]

    def set_uid_topological_type(self, uid: str = None, topological_type: str = None):
        """Set topological type from uid."""
        self.df.loc[self.df["uid"] == uid, "topological_type"] = topological_type

    def get_uid_scenario(self, uid: str = None) -> str:
        """Get scenario from uid."""
        return self.df.loc[self.df["uid"] == uid, "scenario"].values[0]

    def set_uid_scenario(self, uid: str = None, scenario: str = None):
        """Set scenario from uid."""
        self.df.loc[self.df["uid"] == uid, "scenario"] = scenario

    def get_uid_properties_names(self, uid: str = None) -> list:
        """Get properties value names from uid. This is a LIST even if we extract it with values[0]!"""
        return self.df.loc[self.df["uid"] == uid, "properties_names"].values[0]

    def set_uid_properties_names(self, uid: str = None, properties_names: list = None):
        """Set properties value names from uid. This is a LIST and "at" must be used!"""
        row = self.df[self.df["uid"] == uid].index.values[0]
        self.df.at[row, "properties_names"] = properties_names

    def get_uid_properties_components(self, uid: str = None) -> list:
        """Get properties components from uid. This is a LIST even if we extract it with values[0]!"""
        return self.df.loc[self.df["uid"] == uid, "properties_components"].values[0]

    def set_uid_properties_components(self, uid: str = None, properties_components: list = None):
        """Set properties componentes from uid. This is a LIST and "at" must be used!"""
        row = self.df[self.df["uid"] == uid].index.values[0]
        self.df.at[row, "properties_components"] = properties_components

    def get_uid_x_section(self, uid: str = None) -> str:
        """Get xsection uid from uid."""
        return self.df.loc[self.df["uid"] == uid, "x_section"].values[0]

    def set_uid_x_section(self, uid: str = None, x_section: str = None):
        """Set xsection uid from uid."""
        self.df.loc[self.df["uid"] == uid, "x_section"] = x_section

    def get_xuid_uid(self, xuid: str = None) -> list:
        """Get the uids of the geological objects for the corresponding xsec uid"""
        return self.df.loc[self.df["x_section"] == xuid, "uid"].to_list()

    def get_uid_vtk_obj(self, uid: str = None) -> vtkDataObject:
        """Get vtk object from uid."""
        return self.df.loc[self.df["uid"] == uid, "vtk_obj"].values[0]

    def set_uid_vtk_obj(self, uid: str = None, vtk_obj: vtkDataObject = None):
        """Set vtk object from uid."""
        self.df.loc[self.df["uid"] == uid, "vtk_obj"] = vtk_obj

    def append_uid_property(self, uid: str = None, property_name: str = None, property_components: str = None):
        """Add property name and components to an uid and create empty property on vtk object.
        For some reason here list.append(new_element) does not work"""
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
        self.metadata_modified_signal([uid])

    def remove_uid_property(self, uid: str = None, property_name: str = None):
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
        self.data_keys_removed_signal([uid])

    def get_uid_property_shape(self, uid: str = None, property_name: str = None) -> tuple:
        """Returns the shape of the property data array."""
        return self.get_uid_vtk_obj(uid).get_point_data_shape(property_name)

    def get_uid_property(self, uid: str = None, property_name: str = None) -> ndarray:
        """Returns an array with property data."""
        return self.get_uid_vtk_obj(uid).get_point_data(property_name)

    def get_legend(self):
        legend_dict = self.parent.others_legend_df.loc[
            self.parent.others_legend_df["other_type"] == "DOM"
        ].to_dict("records")
        return legend_dict[0]

    # =================== Common QT methods slightly adapted to the data source ====================================

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
                self.geology_attr_modified_update_legend_table()
                self.parent.metadata_modified_signal.emit(
                    [uid]
                )  # a list of uids is emitted, even if the entity is just one
                return True
        return QVariant()

