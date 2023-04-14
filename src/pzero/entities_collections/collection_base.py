from abc import abstractmethod

import pandas as pd
from PyQt5.QtCore import QAbstractTableModel, Qt, QObject
import logging as log
import deprecated

class CollectionBase(QAbstractTableModel):

    def __init__(self, parent=None):
        super(CollectionBase, self).__init__(parent=parent)


        """Initialize Pandas dataframe."""
        self._df = pd.DataFrame(columns=list(self.entity_dict.keys()))


    @property
    @deprecated.deprecated("Accessing main window from a collection is discouraged" )
    def main_window(self):
        log.debug("Accessing main window from a collection. this beahvior is scheduled to be removed.")
        return self.parent().parent()

    @property
    @abstractmethod
    def entity_dict(self):
        raise NotImplementedError("BoundaryCollection.entity_dict() is not implemented yet.")

    @property
    @abstractmethod
    def type_dict(self):
        raise NotImplementedError("BoundaryCollection.type_dict() is not implemented yet.")

    @property
    @abstractmethod
    def valid_topological_type(self):
        raise NotImplementedError("BoundaryCollection.valid_topological_type() is not implemented yet.")

    @property
    @abstractmethod
    def valid_types(self):
        raise NotImplementedError("BoundaryCollection.valid_types() is not implemented yet.")

    @property
    @abstractmethod
    def editable_columns(self):
        raise NotImplementedError("BoundaryCollection.editable_columns() is not implemented yet.")


    # # @property
    # # def parent(self) :
    # #     return super(CollectionBase).parent()
    #
    # @parent.setter
    # def parent(self, parent) :
    #     QObject.setParent(self, parent)

    def data(self, index, role):
        """Data is updated on the fly:
        .row() index points to an entity in the vtkCollection
        .column() index points to an element in the list created on the fly
        based on the column headers stored in the dictionary."""
        if role == Qt.DisplayRole:
            value = self._df.iloc[index.row(), index.column()]
            return str(value)

    def headerData(self, section, orientation, role):
        """Set header from pandas dataframe. "section" is a standard Qt variable."""
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                return str(self._df.columns[section])
            if orientation == Qt.Vertical:
                return str(self._df.index[section])

    def rowCount(self, index):
        """Set row count from pandas dataframe"""
        return self._df.shape[0]

    def columnCount(self, index):
        """Set column count from pandas dataframe"""
        return self._df.shape[1]

    def flags(self, index):
        """Set editable columns."""
        if index.column() in self.editable_columns:
            return Qt.ItemFlags(QAbstractTableModel.flags(self, index) | Qt.ItemIsEditable)
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def get_number_of_entities(self):
        """Get number of entities stored in Pandas dataframe."""
        return self._df.shape[0]

    def get_uids(self):
        """Get list of uids."""
        return self._df['uid'].to_list()

    def remove_entity(self, uid=None):
        raise NotImplementedError

    def has_uid(self, uid=None):
        """Check if uid is in collection."""
        return uid in self._df['uid'].to_list()

    def get_topological_type_uids(self, topological_type=None):
        """Get list of uids of a given topological_type."""
        return self._df.loc[self._df['topological_type'] == topological_type, 'uid'].to_list()

    def get_uid_name(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self._df.loc[self._df['uid'] == uid, 'name'].values[0]

    def set_uid_name(self, uid=None, name=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self._df.loc[self._df['uid'] == uid, 'name'] = name

    def get_names(self):
        """Get list of names."""
        return self._df['name'].to_list()

    def set_uid_vtk_obj(self, uid=None, vtk_obj=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self._df.loc[self._df['uid'] == uid, 'vtk_obj'] = vtk_obj

    def get_uid_vtk_obj(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self._df.loc[self._df['uid'] == uid, 'vtk_obj'].values[0]

    def set_uid_topological_type(self, uid=None, topological_type=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self._df.loc[self._df['uid'] == uid, 'topological_type'] = topological_type

    def get_uid_topological_type(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self._df.loc[self._df['uid'] == uid, 'topological_type'].values[0]

    def get_name_uid(self, name=None):
        return self._df.loc[self._df['name'] == name, 'uid'].values[0]

    def drop_df_entry_by_uid(self, uid=None):
        """Drop an entry in the dataframe by uid."""
        if not uid in self.get_uids():
            log.warning("uid not found in collection")
            return

        self._df.drop(self._df[self._df['uid'] == uid].index, inplace=True)
        self.modelReset.emit()
