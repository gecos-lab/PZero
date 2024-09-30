"""boundary_collection.py
PZero© Andrea Bistacchi"""

from vtkmodules.vtkCommonDataModel import vtkDataObject

from copy import deepcopy
from uuid import uuid4 as uuid_uuid4

from numpy import array as np_array
from numpy import ndarray as np_ndarray
from numpy import set_printoptions as np_set_printoptions

from pandas import DataFrame as pd_DataFrame
from pandas import set_option as pd_set_option

from vtk import vtkPoints

from pzero.entities_factory import PolyLine, TriSurf
from pzero.helpers.helper_dialogs import general_input_dialog
from .AbstractCollection import BaseCollection

# Options to print Pandas dataframes in console for testing.
pd_desired_width = 800
pd_max_columns = 20
pd_show_precision = 4
pd_max_colwidth = 80
pd_set_option("display.width", pd_desired_width)
np_set_printoptions(linewidth=pd_desired_width)
pd_set_option("display.max_columns", pd_max_columns)
pd_set_option("display.precision", pd_show_precision)
pd_set_option("display.max_colwidth", pd_max_colwidth)

def boundary_from_points(self, vector):
    """Create a new Boundary from a vector"""
    boundary_dict = deepcopy(self.parent.boundary_coll.entity_dict)
    # Freeze QT interface.
    self.disable_actions()
    # Draw the diagonal of the Boundary by drawing a vector with vector_by_mouse. "while True" lets the user
    # draw the vector multiple times if modifications are necessary.
    self.plotter.untrack_click_position(side="left")
    # Multiple_input_dialog widget is built to check the default value associated to each feature in
    # section_dict_in: this value defines the type (str-int-float) of the output that is passed to section_dict_updt.
    # It is therefore necessary in section_dict_in to implement the right type for each variable."""
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
    # Check if other Boundaries with the same name exist. If so, add suffix to make the name unique.
    while True:
        if boundary_dict_updt["name"] in self.parent.boundary_coll.get_names:
            boundary_dict_updt["name"] = boundary_dict_updt["name"] + "_0"
        else:
            break
    # Check if top and bottom fields are empty.
    if boundary_dict_updt["top"] is None:
        boundary_dict_updt["top"] = 1000.0
    if boundary_dict_updt["bottom"] is None:
        boundary_dict_updt["bottom"] = -1000.0
    if boundary_dict_updt["top"] == boundary_dict_updt["bottom"]:
        boundary_dict_updt["top"] = boundary_dict_updt["top"] + 1.0
    boundary_dict["name"] = boundary_dict_updt["name"]
    if boundary_dict_updt["activatevolume"] == "check":
        # Build rectangular polyline at Z=0 meters.
        boundary_dict["topology"] = "PolyLine"
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
        # Build Boundary as volume.
        boundary_dict["topology"] = "TriSurf"
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
    # Un-Freeze QT interface
    self.enable_actions()


class BoundaryCollection(BaseCollection):
    """Collection for all boundaries and their metadata."""
    def __init__(self, parent=None, *args, **kwargs):
        super(BoundaryCollection, self).__init__(parent, *args, **kwargs)
        # Initialize properties required by the abstract superclass.
        self.entity_dict = {
            "uid": "",
            "name": "undef",
            "topology": "undef",
            "scenario": "undef",
            "x_section": "", # this is the uid of the cross section for "XsVertexSet", "XsPolyLine", and "XsImage", empty for all others
            "vtk_obj": None,
        }

        self.entity_dict_types = {
            "uid": str,
            "name": str,
            "topology": str,
            "scenario": str,
            "x_section": str,
            "vtk_obj": object,
        }

        self.valid_topologies = ["PolyLine", "TriSurf", "XsPolyLine"]

        self.editable_columns_names = ["name", "scenario"]

        self.collection_name = 'boundary'

        self.initialize_df()

    # =================================== Obligatory methods ===========================================

    def add_entity_from_dict(self, entity_dict: pd_DataFrame = None, color: np_ndarray = None):
        """Add an entity from a dictionary shaped as self.entity_dict."""
        # Create a new uid if it is not included in the dictionary.
        if not entity_dict["uid"]:
            entity_dict["uid"] = str(uuid_uuid4())
        # Append new row to dataframe. Note that the 'append()' method for Pandas dataframes DOES NOT
        # work in place, hence a NEW dataframe is created every time and then substituted to the old one.
        self.df = self.df.append(entity_dict, ignore_index=True)
        # Reset data model.
        self.modelReset.emit()
        # Then emit signal to update the views. A list of uids is emitted, even if the entity is just one.
        self.signals.added.emit([entity_dict["uid"]])
        return entity_dict["uid"]

    def remove_entity(self, uid: str = None) -> str:
        """Remove an entity and its metadata."""
        # Remove row from dataframe and reset data model.
        self.df.drop(self.df[self.df["uid"] == uid].index, inplace=True)
        self.modelReset.emit()  # is this really necessary?
        # When done, send a signal over to the views. A list of uids is emitted, even if the entity is just one.
        self.signals.removed.emit([uid])
        return uid

    def clone_entity(self, uid: str = None) -> str:
        """Clone an entity."""
        # Not implemented for this collection, but required by the abstract superclass.
        pass

    def replace_vtk(self, uid: str = None, vtk_object: vtkDataObject = None):
        """Replace the vtk object of a given uid with another vtkobject."""
        # ============ CAN BE UNIFIED AS COMMON METHOD OF THE ABSTRACT COLLECTION WHEN SIGNALS WILL BE UNIFIED ==========
        if isinstance(vtk_object, type(self.df.loc[self.df["uid"] == uid, "vtk_obj"].values[0])):
            self.df.loc[self.df["uid"] == uid, "vtk_obj"] = vtk_object
            self.signals.geom_modified.emit([uid])
        else:
            print("ERROR - replace_vtk with vtk of a different type not allowed.")

    def attr_modified_update_legend_table(self):
        """Update legend table when attributes are changed."""
        # Not implemented for this collection, but required by the abstract superclass.
        pass

    def remove_unused_from_legend(self):
        """Remove unused roles / features from a legend table."""
        legend_updated: bool = False
        return legend_updated

    def get_uid_legend(self, uid: str = None) -> dict:
        """Get legend for a particular uid."""
        # Not implemented for this collection, but required by the abstract superclass.
        pass

    def set_uid_legend(self, uid: str = None, color_R: float = None, color_G: float = None, color_B: float = None,
                       line_thick: float = None, point_size: float = None, opacity: float = None):
        """Set the legend for a particular uid."""
        # Not implemented for this collection, but required by the abstract superclass.
        pass

    # def metadata_modified_signal(self, updated_list: list = None):
    #     """Signal emitted when metadata change."""
    #     self.parent.boundary_coll.signals.metadata_modified.emit(updated_list)

    # def data_keys_modified_signal(self, updated_list: list = None):
    #     """Signal emitted when point data keys change."""
    #     # Not implemented for this collection, but required by the abstract superclass.
    #     pass
