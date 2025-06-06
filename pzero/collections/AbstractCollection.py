"""AbstractCollection.py
PZero© Andrea Bistacchi"""

# from PySide6.QtCore import QAbstractTableModel, Qt, QVariant, QSortFilterProxyModel, QObject, pyqtSignal
from PySide6.QtCore import QAbstractTableModel, Qt, QSortFilterProxyModel, QObject
from PySide6.QtCore import Signal as pyqtSignal

from abc import abstractmethod, ABC

from pandas import DataFrame as pd_DataFrame

import numpy.typing as npt
from numpy import ndarray as np_ndarray
from numpy import intp as np_intp

from vtkmodules.vtkCommonDataModel import vtkDataObject


class CollectionSignals(QObject):
    """
    This class is necessary since non-Qt classes cannot emit Qt signals. Therefore, we create a generic
    CollectionSignals() Qt object, that will include all signals used by collections. These will be used according
    to the following pattern:

    self.signals = CollectionSignals()

    self.signals.specific_signal.emit(some_message)

    etc.

    Basically in this way, instead of using inheritance, we add all signals with a qick move by composition.
    """

    entities_added = pyqtSignal(list)
    entities_removed = pyqtSignal(list)
    geom_modified = pyqtSignal(list)  # this includes topology modified
    data_keys_modified = pyqtSignal(
        list
    )  # remove after splittting keys added/removed ==========
    data_keys_added = pyqtSignal(list)
    data_keys_removed = pyqtSignal(list)
    data_val_modified = pyqtSignal(list)
    metadata_modified = pyqtSignal(list)
    legend_color_modified = pyqtSignal(list)
    legend_thick_modified = pyqtSignal(list)
    legend_point_size_modified = pyqtSignal(list)
    legend_opacity_modified = pyqtSignal(list)
    itemsSelected = pyqtSignal(
        str
    )  # selection changed on the collection in the signal argument


class BaseCollection(ABC):
    """Abstract class used as a base for all collections, implemented with ABC in order to
    set a mandatory standard for all subclasses with the @abstractmethod decorator."""

    def __init__(self, parent=None, *args, **kwargs):
        super(BaseCollection, self).__init__(*args, **kwargs)
        # Import reference to parent = the project, otherwise it is difficult
        # to reference it in SetData() that has a standard list of inputs.
        # Then initialise some standard lists and dictionaries and the
        # Qt table model as a property (hence using composition).
        # All these properties are defined as private protected properties, and
        # then exposed with public @property and @__.setter decorators
        # because .... _____________EXPLAIN WHY HERE!

        self._parent = parent
        self._collection_name: str = ""

        self._signals = CollectionSignals()

        self._entity_dict: dict = dict()
        self._entity_dict_types: dict = dict()

        self._valid_roles: list = list()
        self._valid_topologies: list = list()

        self._df: pd_DataFrame = pd_DataFrame()
        self._editable_columns_names: list = list()
        self._selected_uids: list = list()  # list of selected uids

        self._table_model = BaseTableModel(self.parent, self)

    # =========================== Abstract (obligatory) methods ================================

    @abstractmethod
    def add_entity_from_dict(
        self, entity_dict: pd_DataFrame = None, color: np_ndarray = None
    ):
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
    def replace_vtk(self, uid: str = None, vtk_object: vtkDataObject = None):
        """Replace the vtk object of a given uid with another vtkobject."""
        # ============ CAN BE UNIFIED AS COMMON METHOD OF THE ABSTRACT COLLECTION WHEN SIGNALS WILL BE UNIFIED ==========
        # ============ NOT CLEAR HOW TO DEAL WITH COLLECTIONS OF IMMUTABLE VTKs (images, DOMs, meshes, etc.) ==========
        pass

    @abstractmethod
    def attr_modified_update_legend_table(self):
        """Update legend table, adding or removing items, based on metadata table.
        This is called when editing the geological dataframe with setData(). Slightly different versions
        are found in add_entity_from_dict and remove_entity methods."""
        pass

    @abstractmethod
    def remove_unused_from_legend(self):
        """Remove unused types / features from a legend table."""
        legend_updated: bool = False
        return legend_updated

    @abstractmethod
    def get_uid_legend(self, uid: str = None) -> dict:
        """Get legend as dictionary from uid."""
        pass

    @abstractmethod
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
        """Set legend properties from uid. Take care since this resets the legend for all similar objects."""
        pass

    # =================================== Common properties ================================================

    @property
    def parent(self):
        """Get the parent of the Collection."""
        return self._parent

    @property
    def collection_name(self) -> str:
        """Get the collection name."""
        return self._collection_name

    @collection_name.setter
    def collection_name(self, collection_name) -> str:
        """Get the collection name."""
        self._collection_name = collection_name

    @property
    def signals(self):
        return self._signals

    @property
    def entity_dict(self) -> dict:
        """Get the entity dict of the Collection."""
        return self._entity_dict

    @entity_dict.setter
    def entity_dict(self, entity_dict: dict):
        """Set the entity dict of the Collection."""
        self._entity_dict = entity_dict

    @property
    def entity_dict_types(self) -> dict:
        """Get the entity type dict of the Collection."""
        return self._entity_dict_types

    @entity_dict_types.setter
    def entity_dict_types(self, entity_dict_types: dict):
        """Set the entity type dict of the Collection."""
        self._entity_dict_types = entity_dict_types

    @property
    def valid_roles(self) -> list:
        """Get the valid types list of the Collection."""
        return self._valid_roles

    @valid_roles.setter
    def valid_roles(self, valid_roles: list):
        """Set the valid types list of the Collection."""
        self._valid_roles = valid_roles

    @property
    def valid_topologies(self) -> list:
        """Get the valid topological list of the Collection."""
        return self._valid_topologies

    @valid_topologies.setter
    def valid_topologies(self, valid_topologies: list):
        """Set the valid topological list of the Collection."""
        self._valid_topologies = valid_topologies

    @property
    def editable_columns_names(self):
        """Get the editable columns names of the Collection."""
        return self._editable_columns_names

    @editable_columns_names.setter
    def editable_columns_names(self, editable_columns_names: list):
        """Set the editable columns names of the Collection."""
        self._editable_columns_names = editable_columns_names

    @property
    def df(self) -> pd_DataFrame:
        """Get the dataframe of the Collection."""
        return self._df

    @df.setter
    def df(self, df: pd_DataFrame):
        """Set the dataframe of the Collection."""
        self._df = df

    @property
    def selected_uids(self):
        return self._selected_uids

    @selected_uids.setter
    def selected_uids(self, selected_uids: list):
        self._selected_uids = selected_uids

    @property
    def entity_dict_keys(self) -> list:
        """Get the entity dict keys as a list."""
        return list(self.entity_dict.keys())

    @property
    def editable_columns(self) -> npt.NDArray[np_intp]:
        """Here we use .columns.get_indexer to get indexes of the columns
        that we would like to be editable in the QTableView."""
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

    @property
    def table_model(self):
        """Get the table model."""
        return self._table_model

    @property
    def proxy_table_model(self) -> QSortFilterProxyModel:
        """Get the proxy table model, used i.e. when sorting rows in the table view."""
        proxy_coll = QSortFilterProxyModel(self.parent)
        proxy_coll.setSourceModel(self.table_model)
        return proxy_coll

    @property
    def modelReset(self):
        """Helper property used to avoid changing the code in the different collections 20 times."""
        return self.table_model.modelReset

    # =================================== Common methods ================================================

    def print_terminal(self, string=None):
        return self.parent.print_terminal(string=string)

    def initialize_df(self):
        """Initialize Pandas dataframe. Must be called in the subclass constructor."""
        self.df = pd_DataFrame(columns=self.entity_dict_keys)

    def get_uid_name(self, uid: str = None) -> str:
        """Get value(s) stored in dataframe (as pointer) from uid."""
        # Use the query method in the future?
        return self.df.loc[self.df["uid"] == uid, "name"].values[0]

    def set_uid_name(self, uid: str = None, name: str = None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df["uid"] == uid, "name"] = name

    def get_name_uid(self, name=None) -> list:
        """Get a list of uids corresponding to a given name."""
        # Use the query method in the future?
        return self.df.loc[self.df["name"] == name, "uid"].to_list()

    def get_topology_uids(self, topology: str = None) -> list:
        """Get list of uids of a given topology."""
        # Use the query method in the future?
        return self.df.loc[self.df["topology"] == topology, "uid"].to_list()

    def get_uid_topology(self, uid: str = None) -> str:
        """Get value topological type from uid."""
        # Use the query method in the future?
        return self.df.loc[self.df["uid"] == uid, "topology"].values[0]

    def set_uid_topology(self, uid: str = None, topology: str = None):
        """Set topological type from uid."""
        self.df.loc[self.df["uid"] == uid, "topology"] = topology

    def get_uid_scenario(self, uid: str = None) -> str:
        """Get scenario from uid."""
        # Use the query method in the future?
        return self.df.loc[self.df["uid"] == uid, "scenario"].values[0]

    def set_uid_scenario(self, uid: str = None, scenario: str = None):
        """Set scenario from uid."""
        self.df.loc[self.df["uid"] == uid, "scenario"] = scenario

    def get_uid_properties_names(self, uid: str = None) -> list:
        """Get properties value names from uid. This is a LIST even if we extract it with values[0]."""
        # Use the query method in the future?
        return self.df.loc[self.df["uid"] == uid, "properties_names"].values[0]

    def set_uid_properties_names(self, uid: str = None, properties_names: list = None):
        """Set properties value names from uid. This is a LIST and "at" must be used!"""
        row = self.df[self.df["uid"] == uid].index.values[0]
        self.df.at[row, "properties_names"] = properties_names

    def get_uid_properties_components(self, uid: str = None) -> list:
        """Get properties components from uid. This is a LIST even if we extract it with values[0]."""
        # Use the query method in the future?
        return self.df.loc[self.df["uid"] == uid, "properties_components"].values[0]

    def set_uid_properties_components(
        self, uid: str = None, properties_components: list = None
    ):
        """Set properties componentes from uid. This is a LIST and "at" must be used!"""
        row = self.df[self.df["uid"] == uid].index.values[0]
        self.df.at[row, "properties_components"] = properties_components

    def get_uid_x_section(self, uid: str = None) -> str:
        """Get xsection uid from uid."""
        # Use the query method in the future?
        return self.df.loc[self.df["uid"] == uid, "x_section"].values[0]

    def set_uid_x_section(self, uid: str = None, x_section: str = None):
        """Set xsection uid from uid."""
        self.df.loc[self.df["uid"] == uid, "x_section"] = x_section

    def get_xuid_uid(self, xuid: str = None) -> list:
        """Get the uids of the geological objects for the corresponding xsec uid"""
        # Use the query method in the future?
        return self.df.loc[self.df["x_section"] == xuid, "uid"].to_list()

    def get_uid_vtk_obj(self, uid: str = None) -> vtkDataObject:
        """Get vtk object from uid."""
        # Use the query method in the future?
        return self.df.loc[self.df["uid"] == uid, "vtk_obj"].values[0]

    def set_uid_vtk_obj(self, uid: str = None, vtk_obj: vtkDataObject = None):
        """Set vtk object from uid."""
        self.df.loc[self.df["uid"] == uid, "vtk_obj"] = vtk_obj

    def append_uid_property(
        self,
        uid: str = None,
        property_name: str = None,
        property_components: str = None,
    ):
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
        # IN THE FUTURE add cell data.
        self.signals.metadata_modified.emit([uid])

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
        # IN THE FUTURE add cell data.
        self.signals.data_keys_modified([uid])

    def get_uid_property_shape(
        self, uid: str = None, property_name: str = None
    ) -> tuple:
        """Returns the shape of the property data array."""
        return self.get_uid_vtk_obj(uid).get_point_data_shape(property_name)

    def get_uid_property(
        self, uid: str = None, property_name: str = None
    ) -> np_ndarray:
        """Returns an array with property data."""
        return self.get_uid_vtk_obj(uid).get_point_data(property_name)

    def get_legend(self):
        """Returns the currently active legend dictionary."""
        legend_dict = self.parent.others_legend_df.loc[
            self.parent.others_legend_df["other_collection"] == "DOM"
        ].to_dict("records")
        return legend_dict[0]

    def filter_uids(self, query: str = None, uids: list = None):
        return list(
            set(self.df.query(query)["uid"].tolist())
            - (set(self.df.query(query)["uid"].tolist()) - set(uids))
        )

    # =================== Common QT methods slightly adapted to the data source ====================================


class BaseTableModel(QAbstractTableModel):
    """BaseTableModel inherits from QAbstractTableModel setting a few methods and
    the data connection to the Pandas dataframe self.collection.df."""

    def __init__(self, parent=None, collection: BaseCollection = None, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        # Initialize just parent (the project) and the collection.

        self.parent = parent
        self._collection = collection

    @property
    def collection(self):
        """This is the instance of a subclass of BaseCollection used as data."""
        return self._collection

    def data(self, index, qt_role):
        """Data is updated on the fly:
        .row() index points to an entity in the collection
        .column() index points to an element in the list created on the fly
        based on the column headers stored in the dictionary."""
        if qt_role == Qt.DisplayRole:
            value = self.collection.df.iloc[index.row(), index.column()]
            return str(value)

    def headerData(self, section, orientation, qt_role):
        """Set header from pandas dataframe. "section" is a standard Qt variable."""
        if qt_role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                return str(self.collection.df.columns[section])
            if orientation == Qt.Vertical:
                return str(self.collection.df.index[section])

    def rowCount(self, index):
        """Set row count from pandas dataframe."""
        return self.collection.df.shape[0]

    def columnCount(self, index):
        """Set column count from pandas dataframe."""
        return self.collection.df.shape[1]

    def flags(self, index):
        """Set editable columns."""
        if index.column() in self.collection.editable_columns:
            return Qt.ItemFlags(
                QAbstractTableModel.flags(self, index) | Qt.ItemIsEditable
            )
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def setData(self, index, value, qt_role=Qt.EditRole):
        """This is the method allowing to edit the table and the underlying dataframe.
        "self.parent" is used to point to parent, because the standard Qt setData
        method does not allow for extra variables to be passed into this method."""
        if index.isValid():
            self.collection.df.iloc[index.row(), index.column()] = value
            if self.data(index, Qt.DisplayRole) == value:
                self.dataChanged.emit(index, index)
                uid = self.collection.df.iloc[index.row(), 0]
                self.collection.attr_modified_update_legend_table()
                # a list of uids is emitted, even if the entity is just one
                self.collection.signals.metadata_modified.emit([uid])
                return True
        # return QVariant()
        return None
