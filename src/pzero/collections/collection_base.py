from abc import abstractmethod
from pathlib import Path

import pandas as pd
from PyQt5.QtCore import QAbstractTableModel, Qt, QObject
import logging as log
import deprecated

from pandas import read_json
from pandas import read_csv


class CollectionBase(QAbstractTableModel):

    def __init__(self, parent=None):
        super(CollectionBase, self).__init__(parent=parent)
        """Initialize Pandas dataframe."""
        self._df = pd.DataFrame(columns=list(self.entity_dict.keys()))

    @property
    @deprecated.deprecated("Accessing main window from a collection is discouraged")
    def main_window(self):
        log.debug("Accessing main window from a collection. this beahvior is scheduled to be removed.")
        return self.parent().parent()

    @property
    def entity_dict(self):
        raise NotImplementedError("BoundaryCollection.entity_dict() is not implemented yet.")

    @property
    def type_dict(self):
        raise NotImplementedError("BoundaryCollection.type_dict() is not implemented yet.")

    @property
    def valid_topological_type(self):
        raise NotImplementedError("BoundaryCollection.valid_topological_type() is not implemented yet.")

    @property
    def valid_types(self):
        raise NotImplementedError("BoundaryCollection.valid_types() is not implemented yet.")

    @property
    @abstractmethod
    def editable_columns(self):
        raise NotImplementedError("BoundaryCollection.editable_columns() is not implemented yet.")

    @property
    @abstractmethod
    def default_save_table_filename(self):
        raise NotImplementedError("default filename not implemented in subclass.")

    def post_json_read(self):
        pass

    def post_csv_read(self):
        pass

    def read(self, project_root, filename=None):
        log.debug(f"Reading {self.__class__.__name__} from {project_root} with filename {filename}")
        if not filename:
            filename = self.default_save_table_filename

        expected_filename = Path(project_root).joinpath(f"{filename}_table")

        if expected_filename.with_suffix(".json").exists():
            type = "JSON"
            filename = expected_filename.with_suffix(".json")


        elif expected_filename.with_suffix(
                ".csv").exists():  # here we should use a serialization factory. So that in the future we can target additional formats (binary, e.g. feather, pickle etc).
            type = "CSV"
            filename = expected_filename.with_suffix(".csv")

        else:
            log.warning(f"Could not find {expected_filename} in {project_root}. Table not loaded.")
            return dict(type=None, filename=None)

        if type == "JSON":
            got = read_json(filename, orient='index', dtype=self.entity_dict)
            if not got.empty:
                self._df = got
                self.post_json_read()

        elif type == "CSV":
            got = read_csv(filename, encoding='utf-8', dtype=self.type_dict, keep_default_na=False)
            if not got.empty:
                self._df = got
                self.post_csv_read()

        return dict(type=type, filename=filename)

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
