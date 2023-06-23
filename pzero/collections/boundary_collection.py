"""boundary_collection.py
PZero© Andrea Bistacchi"""

"""Import as much as possible as from <module> import <class> or <class as ...>"""
from copy import deepcopy
from uuid import uuid4 as uuid_uuid4

from PyQt5.QtCore import QAbstractTableModel, Qt, QVariant
from numpy import array as np_array
from numpy import set_printoptions as np_set_printoptions
from pandas import DataFrame as pd_DataFrame
from pandas import set_option as pd_set_option
from vtk import vtkPoints

from pzero.entities_factory import PolyLine, TriSurf
from pzero.helpers.helper_dialogs import general_input_dialog

"""Options to print Pandas dataframes in console for testing."""
pd_desired_width = 800
pd_max_columns = 20
pd_show_precision = 4
pd_max_colwidth = 80
pd_set_option("display.width", pd_desired_width)
np_set_printoptions(linewidth=pd_desired_width)
pd_set_option("display.max_columns", pd_max_columns)
pd_set_option("display.precision", pd_show_precision)
pd_set_option("display.max_colwidth", pd_max_colwidth)

""""Methods used to create boundaries. TO BE MOVED IN ANOTHER MODULE - WORKS IN MAP VIEW?? ________________________________"""


def boundary_from_points(self, vector):
    """Create a new Boundary from a vector"""
    boundary_dict = deepcopy(self.parent.boundary_coll.boundary_entity_dict)
    """multiple_input_dialog widget is built to check the default value associated to each feature in
    section_dict_in: this value defines the type (str-int-float) of the output that is passed to section_dict_updt.
    It is therefore necessary in section_dict_in to implement the right type for each variable."""
    """Freeze QT interface"""
    self.disable_actions()
    """Draw the diagonal of the Boundary by drawing a vector with vector_by_mouse. "while True" lets the user 
    draw the vector multiple times if modifications are necessary"""
    self.plotter.untrack_click_position(side="left")

    boundary_dict_in = {
        "warning": [
            "Boundary from points",
            "Build new Boundary from a user-drawn line that represents the horizontal diagonal\nof the Bounding box.\nOnce drawn, values can be modified from keyboard or by drawing another vector.",
            "QLabel",
        ],
        "name": ["Insert Boundary name", "new_boundary", "QLineEdit"],
        "origin_x": ["Insert origin X coord", vector.p1[0], "QLineEdit"],
        "origin_y": ["Insert origin Y coord", vector.p1[1], "QLineEdit"],
        "end_x": ["Insert end-point X coord", vector.p2[0], "QLineEdit"],
        "end_y": ["Insert end-point Y coord", vector.p2[1], "QLineEdit"],
        "top": ["Insert top", 1000.0, "QLineEdit"],
        "bottom": ["Insert bottom", -1000.0, "QLineEdit"],
        "activatevolume": [
            "volumeyn",
            "Do not create volume. Create horizontal parallelogram at Z=0 meters",
            "QCheckBox",
        ],
    }
    boundary_dict_updt = general_input_dialog(
        title="New Boundary from points", input_dict=boundary_dict_in
    )
    if boundary_dict_updt is None:
        self.enable_actions()
        return
    """Check if other Boundaries with the same name exist. If so, add suffix to make the name unique"""
    while True:
        if boundary_dict_updt["name"] in self.parent.boundary_coll.get_names():
            boundary_dict_updt["name"] = boundary_dict_updt["name"] + "_0"
        else:
            break
    """Check if top and bottom fields are empty"""
    if boundary_dict_updt["top"] is None:
        boundary_dict_updt["top"] = 1000.0
    if boundary_dict_updt["bottom"] is None:
        boundary_dict_updt["bottom"] = -1000.0
    if boundary_dict_updt["top"] == boundary_dict_updt["bottom"]:
        boundary_dict_updt["top"] = boundary_dict_updt["top"] + 1.0
    boundary_dict["name"] = boundary_dict_updt["name"]
    if boundary_dict_updt["activatevolume"] == "check":
        """Build rectangular polyline at Z=0 meters"""
        boundary_dict["topological_type"] = "PolyLine"
        boundary_dict["vtk_obj"] = PolyLine()
        boundary_dict["vtk_obj"].points = [
            (boundary_dict_updt["origin_x"], boundary_dict_updt["origin_y"], 0.0),
            (boundary_dict_updt["end_x"], boundary_dict_updt["origin_y"], 0.0),
            (boundary_dict_updt["end_x"], boundary_dict_updt["end_y"], 0.0),
            (boundary_dict_updt["origin_x"], boundary_dict_updt["end_y"], 0.0),
            (boundary_dict_updt["origin_x"], boundary_dict_updt["origin_y"], 0.0),
        ]
        boundary_dict["vtk_obj"].auto_cells()
    else:
        """Build Boundary as volume"""
        boundary_dict["topological_type"] = "TriSurf"
        boundary_dict["vtk_obj"] = TriSurf()
        nodes = vtkPoints()
        nodes.InsertPoint(
            0,
            boundary_dict_updt["origin_x"],
            boundary_dict_updt["origin_y"],
            boundary_dict_updt["bottom"],
        )
        nodes.InsertPoint(
            1,
            boundary_dict_updt["end_x"],
            boundary_dict_updt["origin_y"],
            boundary_dict_updt["bottom"],
        )
        nodes.InsertPoint(
            2,
            boundary_dict_updt["end_x"],
            boundary_dict_updt["end_y"],
            boundary_dict_updt["bottom"],
        )
        nodes.InsertPoint(
            3,
            boundary_dict_updt["origin_x"],
            boundary_dict_updt["end_y"],
            boundary_dict_updt["bottom"],
        )
        nodes.InsertPoint(
            4,
            boundary_dict_updt["origin_x"],
            boundary_dict_updt["origin_y"],
            boundary_dict_updt["top"],
        )
        nodes.InsertPoint(
            5,
            boundary_dict_updt["end_x"],
            boundary_dict_updt["origin_y"],
            boundary_dict_updt["top"],
        )
        nodes.InsertPoint(
            6,
            boundary_dict_updt["end_x"],
            boundary_dict_updt["end_y"],
            boundary_dict_updt["top"],
        )
        nodes.InsertPoint(
            7,
            boundary_dict_updt["origin_x"],
            boundary_dict_updt["end_y"],
            boundary_dict_updt["top"],
        )
        boundary_dict["vtk_obj"].SetPoints(nodes)
        boundary_dict["vtk_obj"].append_cell(np_array([0, 1, 4]))
        boundary_dict["vtk_obj"].append_cell(np_array([1, 4, 5]))
        boundary_dict["vtk_obj"].append_cell(np_array([1, 2, 5]))
        boundary_dict["vtk_obj"].append_cell(np_array([2, 5, 6]))
        boundary_dict["vtk_obj"].append_cell(np_array([2, 3, 6]))
        boundary_dict["vtk_obj"].append_cell(np_array([3, 6, 7]))
        boundary_dict["vtk_obj"].append_cell(np_array([0, 4, 7]))
        boundary_dict["vtk_obj"].append_cell(np_array([0, 3, 7]))
        boundary_dict["vtk_obj"].append_cell(np_array([4, 6, 7]))
        boundary_dict["vtk_obj"].append_cell(np_array([4, 5, 6]))
        boundary_dict["vtk_obj"].append_cell(np_array([0, 1, 3]))
        boundary_dict["vtk_obj"].append_cell(np_array([1, 2, 3]))
    uid = self.parent.boundary_coll.add_entity_from_dict(entity_dict=boundary_dict)
    """Un-Freeze QT interface"""
    self.enable_actions()


class BoundaryCollection(QAbstractTableModel):
    """
    Initialize BoundaryCollection table.
    Column headers are taken from BoundaryCollection.boundary_entity_dict.keys()
    parent is supposed to be the project_window

    boundary_entity_dict is a dictionary of entity attributes used throughout the project.
    Always use deepcopy(BoundaryCollection.image_entity_dict) to copy this dictionary without altering the original.
    """

    boundary_entity_dict = {
        "uid": "",
        "name": "undef",
        "topological_type": "undef",
        "x_section": "",
        # this is the uid of the cross section for "XsVertexSet", "XsPolyLine", and "XsImage", empty for all others
        "vtk_obj": None,
    }

    boundary_entity_type_dict = {
        "uid": str,
        "name": str,
        "topological_type": str,
        "x_section": str,
        "vtk_obj": object,
    }

    """List of valid data types."""
    valid_topological_type = ["PolyLine", "TriSurf", "XsPolyLine"]

    """Initialize BoundaryCollection table. Column headers are taken from
    BoundaryCollection.boundary_entity_dict.keys(), and parent is supposed to be the project_window."""
    """IN THE FUTURE the edit dialog should be able to edit metadata of multiple entities (and selecting "None" will not change them)."""

    def __init__(self, parent=None, *args, **kwargs):
        super(BoundaryCollection, self).__init__(*args, **kwargs)
        """Import reference to parent, otherwise it is difficult to reference them in SetData() that has a standard list of inputs."""
        self.parent = parent

        """Initialize Pandas dataframe."""
        self.df = pd_DataFrame(columns=list(self.boundary_entity_dict.keys()))

        """Here we use .columns.get_indexer to get indexes of the columns that we would like to be editable in the QTableView"""
        self.editable_columns = self.df.columns.get_indexer(["name"])

    """Custom methods used to add or remove entities, query the dataframe, etc."""

    def add_entity_from_dict(self, entity_dict=None):
        """Add entity to collection from dictionary.
        Create a new uid if it is not included in the dictionary."""
        if not entity_dict["uid"]:
            entity_dict["uid"] = str(uuid_uuid4())
        """"Append new row to dataframe. Note that the 'append()' method for Pandas dataframes DOES NOT
        work in place, hence a NEW dataframe is created every time and then substituted to the old one."""
        self.df = self.df.append(entity_dict, ignore_index=True)
        """Reset data model"""
        self.modelReset.emit()
        """Then emit signal to update the views."""
        self.parent.boundary_added_signal.emit(
            [entity_dict["uid"]]
        )  # a list of uids is emitted, even if the entity is just one
        return entity_dict["uid"]

    def remove_entity(self, uid=None):
        """Remove entity from collection. Remove row from dataframe and reset data model."""
        self.df.drop(self.df[self.df["uid"] == uid].index, inplace=True)
        self.modelReset.emit()  # is this really necessary?
        """When done, send a signal over to the views."""
        self.parent.boundary_removed_signal.emit(
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

    def get_number_of_entities(self):
        """Get number of entities stored in Pandas dataframe."""
        return self.df.shape[0]

    def get_uids(self):
        """Get list of uids."""
        return self.df["uid"].to_list()

    def get_names(self):
        """Get list of names."""
        return self.df["name"].to_list()

    def get_topological_type_uids(self, topological_type=None):
        """Get list of uids of a given topological_type."""
        return self.df.loc[
            self.df["topological_type"] == topological_type, "uid"
        ].to_list()

    def get_legend(self):
        """Get legend."""
        legend_dict = self.parent.others_legend_df.loc[
            self.parent.others_legend_df["other_type"] == "Boundary"
        ].to_dict("records")
        return legend_dict[0]

    def get_uid_name(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df["uid"] == uid, "name"].values[0]

    def set_uid_name(self, uid=None, name=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df["uid"] == uid, "name"] = name

    def get_uid_topological_type(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df["uid"] == uid, "topological_type"].values[0]

    def set_uid_topological_type(self, uid=None, topological_type=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df["uid"] == uid, "topological_type"] = topological_type

    def get_uid_x_section(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df["uid"] == uid, "x_section"].values[0]

    def set_uid_x_section(self, uid=None, x_section=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df["uid"] == uid, "x_section"] = x_section

    def get_uid_vtk_obj(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df["uid"] == uid, "vtk_obj"].values[0]

    def set_uid_vtk_obj(self, uid=None, vtk_obj=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df["uid"] == uid, "vtk_obj"] = vtk_obj

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
                self.parent.boundary_metadata_modified_signal.emit(
                    [uid]
                )  # a list of uids is emitted, even if the entity is just one
                return True
        return QVariant()
