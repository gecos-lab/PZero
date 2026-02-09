"""xsection_collection.py
PZero© Andrea Bistacchi"""

import uuid

from copy import deepcopy

from numpy import array as np_array
from numpy import ndarray as np_ndarray
from numpy import cos as np_cos
from numpy import deg2rad as np_deg2rad
from numpy import dot as np_dot
from numpy import cross as np_cross
from numpy import matmul as np_matmul
from numpy import pi as np_pi
from numpy import repeat as np_repeat
from numpy import sin as np_sin
from numpy import rad2deg as np_rad2deg
from numpy import arctan2 as np_arctan2
from numpy import arcsin as np_arcsin
from numpy import sqrt as np_sqrt
from numpy import sign as np_sign
from numpy import float32 as np_float32
from numpy import float64 as np_float64
from numpy.linalg import inv as np_linalg_inv
from numpy import round as np_round

from pandas import DataFrame as pd_DataFrame
from pandas import read_csv as pd_read_csv
from pandas import unique as pd_unique
from pandas import concat as pd_concat

from vtk import vtkPoints, vtkCellArray, vtkLine
from vtkmodules.numpy_interface.dataset_adapter import WrapDataObject
from vtkmodules.vtkFiltersCore import vtkAppendPolyData

from pzero.entities_factory import Plane, XsPolyLine
from pzero.helpers.helper_dialogs import general_input_dialog, open_file_dialog
from pzero.helpers.helper_functions import auto_sep, best_fitting_plane, freeze_gui_onoff
from pzero.orientation_analysis import dip_directions2normals, get_dip_dir_vectors

from .AbstractCollection import BaseCollection


# =================================== Methods used to create cross sections ===========================================


@freeze_gui_onoff
def section_from_strike(self, vector):
    """Create a cross-section from one point and strike."""
    self.plotter.untrack_click_position(side="left")

    section_dict_in = {
        "warning": [
            "XSection from strike",
            "Build new (parallel) XSection(s) from a user-drawn line.\nUse Number = 1 for a single XSection.\nFor Number > 1, parallel XSections are distributed along the normal pole vector according to spacing.\nOnce drawn, values can be modified from keyboard\nor by drawing another vector.",
            "QLabel",
        ],
        "name": ["Insert Xsection name", "new_section", "QLineEdit"],
        "origin_x": ["Insert origin X coord", np_round(vector.p1[0]), "QLineEdit"],
        "origin_y": ["Insert origin Y coord", np_round(vector.p1[1]), "QLineEdit"],
        "origin_z": ["Insert origin Z coord", np_round(vector.p1[2]), "QLineEdit"],
        "strike": ["Insert strike", np_round(vector.azimuth), "QLineEdit"],
        "dip": ["Insert dip", 90.0, "QLineEdit"],
        "length": ["Insert length", np_round(vector.length), "QLineEdit"],
        "height": ["Insert height", np_round(vector.length/200)*100, "QLineEdit"],
        "num_xs": ["Number of XSections", 1, "QLineEdit"],
        "spacing": ["Spacing of XSections (+o-)", np_round(vector.length/200)*100, "QLineEdit"],
    }
    section_dict_updt = general_input_dialog(
        title="New XSection from points", input_dict=section_dict_in
    )
    if section_dict_updt is None:
        # Check for a valid input dictionary.
        return

    section_dict = deepcopy(self.parent.xsect_coll.entity_dict)
    for key in section_dict.keys():
        if key in section_dict_updt.keys():
            section_dict[key] = section_dict_updt[key]

    normal_x = (
        np_sin(np_deg2rad(section_dict_updt["strike"] - 90))
        * section_dict_updt["spacing"]
    )
    normal_y = (
        np_cos(np_deg2rad(section_dict_updt["strike"] - 90))
        * section_dict_updt["spacing"]
    )
    normal_z = (
        -np_sin(np_deg2rad(90 - section_dict_updt["dip"]))
        * section_dict_updt["spacing"]
    )

    origin_x = section_dict["origin_x"]
    origin_y = section_dict["origin_y"]
    origin_z = section_dict["origin_z"]

    for i in range(section_dict_updt["num_xs"]):
        if section_dict_updt["num_xs"] > 1:
            name = section_dict_updt["name"] + "_" + str(i)
        else:
            name = section_dict_updt["name"]
        while True:
            if name in self.parent.xsect_coll.get_names:
                name = name + "_(1)"
            else:
                break
        section_dict["name"] = name
        section_dict["uid"] = None

        section_dict["origin_x"] = origin_x + normal_x * i
        section_dict["origin_y"] = origin_y + normal_y * i
        section_dict["origin_z"] = origin_z + normal_z * i

        self.parent.xsect_coll.add_entity_from_dict(entity_dict=section_dict)


# def sections_from_file(self):
#     """Create cross section from file."""
#     # Read GOCAD ASCII (.pl) or ASCII files (.dat) to extract the data necessary to create a section (or
#     # multiple sections). The necessary keys are defined in the section_dict_updt dict.
#     # For GOCAD ASCII the file is parsed for every line searching for key words that define the line containing the data.
#     # For normal ASCII files exported from MOVE the data is registered as a csv and so the pd_read_csv function can be
#     # used. The separator is automatically extracted using csv.Sniffer() (auto_sep helper function).
#     # For both importing methods the user must define the top and bottom values of the section.
#
#     # section_from_points IS MISSING! BUT IT IS NOT NECESSARY. SIMILAR FUNCTIONALITY
#     # IS ALREADY PRESENT IN section_from_strike
#     # USE THAT OR EXTRACT "FROM POINTS" IN A SEPARATE FUNCTION
#     # OR CREATE A METHOD TO FILL MISSING PARAMETERS IN THE COLLECTION??
#
#     from os.path import splitext
#
#     section_dict = deepcopy(self.parent.xsect_coll.entity_dict)
#     section_dict_updt = {
#         "name": "",
#         "origin_x": 0,
#         "origin_y": 0,
#         # "end_x": 0,
#         # "end_y": 0,
#         "dip": 90.0,
#         "top": 0,
#         "bottom": 0,
#     }
#     files = open_file_dialog(
#         parent=self,
#         caption="Import section traces",
#         filter="GOCAD ASCII (*.*);;ASCII (*.dat);;CSV (*.csv)",
#         multiple=True,
#     )
#     # return file and extension list
#     # This could be implemented automatically in open_file_dialog
#     name, extension = splitext(files[0])
#     section_dict_in = {
#         "warning": [
#             "XSection from file",
#             "Build new XSection from a GOCAD ASCII or simple ASCII file.\nChoose the top and bottom limit of the sections to continue",
#             "QLabel",
#         ],
#         "top": ["Insert top", 0.0, "QLineEdit"],
#         "bottom": ["Insert bottom", 0.0, "QLineEdit"],
#     }
#     for file in files:
#         # Check the file type and import accordingly
#         # If no valid type is found, do nothing.
#         if extension == ".pl":
#             top_bottom = general_input_dialog(
#                 title="XSection from files", input_dict=section_dict_in
#             )
#             with open(file, "r") as IN:
#                 for line in IN:
#                     if "name:" in line:
#                         line_data = line.strip().split(":")
#                         section_dict["name"] = line_data[1]
#                     elif "VRTX 1" in line:
#                         line_data = line.strip().split()
#                         section_dict["origin_x"] = float(line_data[2])
#                         section_dict["origin_y"] = float(line_data[3])
#                     elif "VRTX 2" in line:
#                         line_data = line.strip().split()
#                         section_dict["end_x"] = float(line_data[2])
#                         section_dict["end_y"] = float(line_data[3])
#                     elif line.strip() == "END":
#                         # When the END line is reached create a section
#                         section_dict["origin_z"] = top_bottom["bottom"]
#                         section_dict["bottom"] = top_bottom["bottom"]
#                         section_dict["end_z"] = top_bottom["top"]
#                         section_dict["top"] = top_bottom["top"]
#                         # UPDATE OTHER PARAMETERS BEFORE CREATING SECTION _______________________________________
#                         uid = self.parent.xsect_coll.add_entity_from_dict(
#                             entity_dict=section_dict
#                         )
#
#         elif extension == ".dat":
#             top_bottom = general_input_dialog(
#                 title="XSection from files", input_dict=section_dict_in
#             )
#             sep = auto_sep(file)
#             pd_df = pd_read_csv(file, sep=sep)
#             unique_traces = pd_unique(pd_df["Name"])
#             for trace in unique_traces:
#                 section_dict["name"] = trace
#                 section_dict["origin_x"] = pd_df.loc[
#                     (pd_df["Name"] == trace) & (pd_df["Vertex Index"] == 1)
#                 ]["x"].values
#                 section_dict["origin_y"] = pd_df.loc[
#                     (pd_df["Name"] == trace) & (pd_df["Vertex Index"] == 1)
#                 ]["y"].values
#                 section_dict["origin_z"] = pd_df.loc[
#                     (pd_df["Name"] == trace) & (pd_df["Vertex Index"] == 1)
#                 ]["y"].values
#                 section_dict["end_x"] = pd_df.loc[
#                     (pd_df["Name"] == trace) & (pd_df["Vertex Index"] == 2)
#                 ]["x"].values
#                 section_dict["end_y"] = pd_df.loc[
#                     (pd_df["Name"] == trace) & (pd_df["Vertex Index"] == 2)
#                 ]["y"].values
#                 section_dict["origin_z"] = top_bottom["bottom"]
#                 section_dict["bottom"] = top_bottom["bottom"]
#                 section_dict["end_z"] = top_bottom["top"]
#                 section_dict["top"] = top_bottom["top"]
#                 # UPDATE OTHER PARAMETERS BEFORE CREATING SECTION _______________________________________
#                 uid = self.parent.xsect_coll.add_entity_from_dict(
#                     entity_dict=section_dict
#                 )
#
#         elif extension == ".csv":
#             sep = auto_sep(file)
#             pd_df = pd_read_csv(file, sep=sep)
#             for index, sec in pd_df.iterrows():
#                 section_dict["name"] = sec["name"]
#                 section_dict["origin_x"] = sec["origin_x"]
#                 section_dict["origin_y"] = sec["origin_y"]
#                 section_dict["end_x"] = sec["end_x"]
#                 section_dict["end_y"] = sec["end_y"]
#                 section_dict["origin_z"] = top_bottom["bottom"]
#                 section_dict["bottom"] = top_bottom["bottom"]
#                 section_dict["end_z"] = top_bottom["top"]
#                 section_dict["top"] = top_bottom["top"]
#                 # UPDATE OTHER PARAMETERS BEFORE CREATING SECTION _______________________________________
#                 uid = self.parent.xsect_coll.add_entity_from_dict(
#                     entity_dict=section_dict
#                 )
#


class XSectionCollection(BaseCollection):
    """
    Cross-section collection.

    A cross-section is a 2D surface defined by an origin and a right-handed orthonormal basis of three vectors,
    in order the strike vector of the cross-section, the dip vector, and the normal vector. These vectors follow
    the standard right-handed geological convention, therefore dip points down-dip (along the slope for a dipping
    section or vertically downwards for a vertica section), strike points to the left if we look down-dip, and
    normal points downwards in the opposite quadrant with respect to dip.

    Child entities of a cross-section can return their UV coordinates in the cross-section local reference, with
    U measured as the distance to the cross-section origin parallel to the strike vector,
    and V measured parallel to the dip vector. Also W - measured parallel to the normal vector - could be
    returned in theory, but it should be zero for entities belonging to the section.

    Note that due to this convention the origin is in the upper left corner of a section, seen from the front
    with strike pointing to the right and dip pointing downwards, and that U increases to the right and
    V increases downwards. The latter could be a bit confusing but allows using the right-hand convention
    everywhere.

    The data stored in files and required to define a cross-section are the origin point (x, y, z), the strike
    azimuth angle, the dip angle, and the cross-section length and height (along strike and dip as for e.g.
    geological faults). Other parameters are calculated on the fly.

    Other metadata stored in files are the uid (immutable), name (editable), and scenario (editable).

    VTK objects vtk_plane and vtk_frame are created on the fly when the cross-section is added to the collection,
    then stored in the dataframe.

    In older code U was called W, strike was called azimuth, and height was called width.

    Some older files have origin_z = 0.0 and bottom and top = some other value. We provide a small check
    to detect and correct this problem when opening old projects, but it is not always guaranteed.
    """

    def __init__(self, parent=None, *args, **kwargs):
        super(XSectionCollection, self).__init__(parent, *args, **kwargs)

        # Initialize properties required by the abstract superclass.
        self.entity_dict = {
            "uid": "",
            "name": "undef",
            "scenario": "undef",
            "parent_uid": "",
            "vtk_plane": None,  # None to avoid errors with deepcopy
            "vtk_frame": None,  # None to avoid errors with deepcopy
            "origin_x": 0.0,
            "origin_y": 0.0,
            "origin_z": 0.0,
            # "end_x": 0.0,  # to be removed
            # "end_y": 0.0,
            # "end_z": 0.0,
            # "normal_x": 0.0,  # to be removed
            # "normal_y": 0.0,
            # "normal_z": 0.0,
            "strike": 0.0,  # right-handed strike direction, rename as strike
            "dip": 90.0,
            "length": 0.0,
            "height": 0.0,  # rename to height
            # "top": 0.0,  # to be removed
            # "bottom": 0.0,
        }
        self.entity_dict_types = {
            "uid": str,
            "name": str,
            "scenario": "undef",
            "parent_uid": str,
            "origin_x": float,
            "origin_y": float,
            "origin_z": float,
            # "end_x": float,
            # "end_y": float,
            # "end_z": float,
            # "normal_x": float,
            # "normal_y": float,
            # "normal_z": float,
            "strike": float,
            "dip": float,
            "length": float,
            "height": float,
            # "top": float,
            # "bottom": float,
            "vtk_plane": object,
            "vtk_frame": object,
        }
        self.valid_topologies = [""]
        self.editable_columns_names = ["name", "scenario"]
        self.collection_name = "xsect_coll"
        self.initialize_df()

    def add_entity_from_dict(
        self, entity_dict: pd_DataFrame = None, color: np_ndarray = None
    ):
        """Add a new cross-section from a suitable dictionary shaped like self.entity_dict."""
        # Create a new uid if it is not included in the dictionary.
        if not entity_dict["uid"]:
            entity_dict["uid"] = str(uuid.uuid4())
        # the following ensures that also cross-sections have a parent_uid metadata
        # that actually points to the cross-section itself.
        # even if it is a bit redundant, this is useful to make many methods in PZero more general
        entity_dict["parent_uid"] = entity_dict["uid"]
        # Append new row to dataframe with Pandas >= 2.0.0 syntax.
        self.df = pd_concat([self.df, pd_DataFrame([entity_dict])], ignore_index=True)
        self.set_geometry(uid=entity_dict["uid"])
        # Reset data model
        self.modelReset.emit()
        # Emit a list of uids, even if the entity is just one
        self.parent.signals.entities_added.emit([entity_dict["uid"]], self)
        return entity_dict["uid"]

    def remove_entity(self, uid: str = None) -> str:
        """
        Remove row from dataframe and reset data model.
        NOTE THAT AT THE MOMENT REMOVING A SECTION DOES NOT REMOVE THE ASSOCIATED OBJECTS.
        """
        if uid not in self.get_uids:
            return
        self.df.drop(self.df[self.df["uid"] == uid].index, inplace=True)
        self.modelReset.emit()  # is this really necessary?
        # Emit a list of uids, even if the entity is just one
        self.parent.signals.entities_removed.emit([uid], self)
        return uid

    def clone_entity(self, uid: str = None) -> str:
        """Not implemented for XSectionCollection but required by the abstract superclass."""
        pass

    def attr_modified_update_legend_table(self):
        """Not implemented for XSectionCollection but required by the abstract superclass."""
        pass

    def remove_unused_from_legend(self):
        """
        Remove unused types / features from a legend table.
        Not implemented for XSectionCollection but required by the abstract superclass, just returns 'False'.
        """
        legend_updated: bool = False
        return legend_updated

    def get_uid_legend(self, uid: str = None) -> dict:
        """
        Supposed to get legend for a particular uid, in this case gets
        the legend for XSection's, which are all the same.
        """
        legend_dict = self.parent.others_legend_df.loc[
            self.parent.others_legend_df["other_collection"] == "XSection"
        ].to_dict("records")
        return legend_dict[0]

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
        """Not implemented for XSectionCollection but required by the abstract superclass."""
        pass

    # =================================== Additional methods ===========================================

    def get_uid_origin(self, uid=None):
        """Get value(s) stored in the dataframe (as a pointer) from uid."""
        return np_array(
            [
                self.get_uid_origin_x(uid),
                self.get_uid_origin_y(uid),
                self.get_uid_origin_z(uid),
            ]
        )

    def get_uid_origin_x(self, uid=None):
        """Get value(s) stored in the dataframe (as a pointer) from uid."""
        return self.df.loc[self.df["uid"] == uid, "origin_x"].values[0]

    def set_uid_origin_x(self, uid=None, origin_x=None):
        """Set value(s) stored in the dataframe from uid."""
        self.df.loc[self.df["uid"] == uid, "origin_x"] = origin_x

    def get_uid_origin_y(self, uid=None):
        """Get value(s) stored in the dataframe (as a pointer) from uid."""
        return self.df.loc[self.df["uid"] == uid, "origin_y"].values[0]

    def set_uid_origin_y(self, uid=None, origin_y=None):
        """Set value(s) stored in the dataframe from uid."""
        self.df.loc[self.df["uid"] == uid, "origin_y"] = origin_y

    def get_uid_origin_z(self, uid=None):
        """Get value(s) stored in the dataframe (as a pointer) from uid."""
        return self.df.loc[self.df["uid"] == uid, "origin_z"].values[0]

    def set_uid_origin_z(self, uid=None, origin_z=None):
        """Set value(s) stored in the dataframe from uid."""
        self.df.loc[self.df["uid"] == uid, "origin_z"] = origin_z

    # def get_uid_end_x(self, uid=None):
    #     """Get value(s) stored in the dataframe (as a pointer) from uid."""
    #     return self.df.loc[self.df["uid"] == uid, "end_x"].values[0]
    #
    # def set_uid_end_x(self, uid=None, end_x=None):
    #     """Set value(s) stored in dataframe (as pointer) from uid."""
    #     self.df.loc[self.df["uid"] == uid, "end_x"] = end_x
    #
    # def get_uid_end_y(self, uid=None):
    #     """Get value(s) stored in dataframe (as pointer) from uid."""
    #     return self.df.loc[self.df["uid"] == uid, "end_y"].values[0]
    #
    # def set_uid_end_y(self, uid=None, end_y=None):
    #     """Set value(s) stored in dataframe (as pointer) from uid."""
    #     self.df.loc[self.df["uid"] == uid, "end_y"] = end_y
    #
    # def get_uid_end_z(self, uid=None):
    #     """Get value(s) stored in dataframe (as pointer) from uid."""
    #     return self.df.loc[self.df["uid"] == uid, "end_z"].values[0]
    #
    # def set_uid_end_z(self, uid=None, end_z=None):
    #     """Set value(s) stored in dataframe (as pointer) from uid."""
    #     self.df.loc[self.df["uid"] == uid, "end_z"] = end_z

    def get_uid_strike(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df["uid"] == uid, "strike"].values[0]

    def set_uid_strike(self, uid=None, strike=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df["uid"] == uid, "strike"] = strike

    def get_uid_dip(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df["uid"] == uid, "dip"].values[0]

    def set_uid_dip(self, uid=None, dip=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df["uid"] == uid, "dip"] = dip

    def get_uid_length(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df["uid"] == uid, "length"].values[0]

    def set_uid_length(self, uid=None, length=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df["uid"] == uid, "length"] = length

    def get_uid_width(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df["uid"] == uid, "height"].values[0]

    def set_uid_width(self, uid=None, height=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df["uid"] == uid, "height"] = height

    def get_uid_top(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df["uid"] == uid, "origin_z"].values[0]

    # def set_uid_top(
    #     self, uid=None, top=None
    # ):  # ----------------------------------------------------------------------
    #     """Set value(s) stored in dataframe (as pointer) from uid."""
    #     self.df.loc[self.df["uid"] == uid, "top"] = top

    def get_uid_bottom(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        origin_z = self.df.loc[self.df["uid"] == uid, "origin_z"].values[0]
        dip = self.df.loc[self.df["uid"] == uid, "dip"].values[0]
        height = self.df.loc[self.df["uid"] == uid, "height"].values[0]
        return origin_z - height * np_sin(np_deg2rad(dip))

    # def set_uid_bottom(
    #     self, uid=None, bottom=None
    # ):  # ----------------------------------------------------------------------
    #     """Set value(s) stored in dataframe (as pointer) from uid."""
    #     self.df.loc[self.df["uid"] == uid, "bottom"] = bottom

    def get_uid_vtk_plane(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df["uid"] == uid, "vtk_plane"].values[0]

    def set_uid_vtk_plane(self, uid=None, vtk_plane=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df["uid"] == uid, "vtk_plane"] = vtk_plane

    def get_uid_vtk_obj(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df["uid"] == uid, "vtk_frame"].values[0]

    def set_uid_vtk_frame(self, uid=None, vtk_frame=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df["uid"] == uid, "vtk_frame"] = vtk_frame

    """Methods used to set parameters and the geometry of a single cross section."""

    # def set_parameters_in_table(
    #     self,
    #     uid=None,
    #     name=None,
    #     origin=None,
    #     end_point=None,
    #     normal=None,
    #     strike=None,
    #     length=None,
    #     top=None,
    #     bottom=None,
    # ):
    #     """Write parameters in Xsections Pandas dataframe"""
    #     self.df.loc[self.df["uid"] == uid, "name"] = name
    #     self.df.loc[self.df["uid"] == uid, "origin_x"] = origin[0]
    #     self.df.loc[self.df["uid"] == uid, "origin_y"] = origin[1]
    #     self.df.loc[self.df["uid"] == uid, "origin_z"] = origin[2]
    #     # self.df.loc[self.df["uid"] == uid, "end_x"] = end_point[0]
    #     # self.df.loc[self.df["uid"] == uid, "end_y"] = end_point[1]
    #     # self.df.loc[self.df["uid"] == uid, "end_z"] = end_point[2]
    #     # self.df.loc[self.df["uid"] == uid, "normal_x"] = normal[0]
    #     # self.df.loc[self.df["uid"] == uid, "normal_y"] = normal[1]
    #     # self.df.loc[self.df["uid"] == uid, "normal_z"] = normal[2]
    #     self.df.loc[self.df["uid"] == uid, "strike"] = strike
    #     self.df.loc[self.df["uid"] == uid, "length"] = length
    #     # self.df.loc[self.df["uid"] == uid, "top"] = top
    #     # self.df.loc[self.df["uid"] == uid, "bottom"] = bottom

    def set_from_table(self, uid=None):
        """Get parameters from x-section table and set them on x-section"""
        self.set_geometry(uid=uid)

    def get_XY_from_W(self, section_uid=None, W=None):
        """Gets X, Y coordinates from W coordinate (distance along the Xsection horizontal axis).
        Should work for a single W value or for an array, in which case should return X, Y as arrays.
        """
        strike = self.df.loc[self.df["uid"] == section_uid, "strike"].values[0]
        origin_x = self.df.loc[self.df["uid"] == section_uid, "origin_x"].values[0]
        origin_y = self.df.loc[self.df["uid"] == section_uid, "origin_y"].values[0]
        X = W * np_sin(strike * np_pi / 180) + origin_x
        Y = W * np_cos(strike * np_pi / 180) + origin_y
        return X, Y

    def get_W_from_XY(self, section_uid=None, X=None, Y=None):
        """Gets W coordinate (distance along the Xsection horizontal axis) from X, Y coordinates.
        Should work for a single W value or for an array, in which case should return X, Y as arrays.
        """
        origin_x = self.df.loc[self.df["uid"] == section_uid, "origin_x"].values[0]
        origin_y = self.df.loc[self.df["uid"] == section_uid, "origin_y"].values[0]
        # end_x = self.df.loc[self.df["uid"] == section_uid, "end_x"].values[0]
        # end_y = self.df.loc[self.df["uid"] == section_uid, "end_y"].values[0]
        strike = self.df.loc[self.df["uid"] == section_uid, "strike"].values[0]
        length = self.df.loc[self.df["uid"] == section_uid, "length"].values[0]
        # the following is the dot product between the vector from origin to end of the x-section and the vector
        # from origin to X, Y, and it is positive if both point in the same direction, negative otherwise
        sense = np_sign(
            (X - origin_x) * np_sin(strike) * length
            + (Y - origin_y) * np_cos(strike) * length
        )
        W = np_sqrt((X - origin_x) ** 2 + (Y - origin_y) ** 2) * sense
        return W

    def get_deltaXY_from_deltaW(self, section_uid=None, deltaW=None):
        """Gets X, Y coordinates from W coordinate (distance along the Xsection horizontal axis)"""
        strike = self.df.loc[self.df["uid"] == section_uid, "strike"].values[0]
        deltaX = deltaW * np_sin(strike * np_pi / 180)
        deltaY = deltaW * np_cos(strike * np_pi / 180)
        return deltaX, deltaY

    def get_uid_strike_vect(self, section_uid=None):
        strike = self.df.loc[self.df["uid"] == section_uid, "strike"].values[0]
        return np_array([np_sin(np_deg2rad(strike)), np_cos(np_deg2rad(strike)), 0.0])

    def get_uid_dip_vect(self, section_uid=None):
        strike = self.df.loc[self.df["uid"] == section_uid, "strike"].values[0]
        dip = self.df.loc[self.df["uid"] == section_uid, "dip"].values[0]
        return np_array(
            [
                np_sin(np_deg2rad(strike + 90)) * np_cos(np_deg2rad(dip)),
                np_cos(np_deg2rad(strike + 90)) * np_cos(np_deg2rad(dip)),
                -np_sin(np_deg2rad(dip)),
            ]
        )

    def get_uid_normal_vect(self, section_uid=None):
        strike_vct = self.get_uid_strike_vect(section_uid=section_uid)
        dip_vct = self.get_uid_dip_vect(section_uid=section_uid)
        return np_cross(strike_vct, dip_vct)

    def get_uid_normal_x(self, uid=None):
        return self.get_uid_normal_vect(uid)[0]

    def get_uid_normal_y(self, uid=None):
        return self.get_uid_normal_vect(uid)[1]

    def get_uid_normal_z(self, uid=None):
        return self.get_uid_normal_vect(uid)[2]

    def world2plane(self, section_uid=None, X=None, Y=None, Z=None, as_arr=False):
        """Get UV cross-section plane coordinates from XYZ world coordinates."""
        # the following are strike, dip, normal unit vectors and the
        # position vector origin of the cross-section plane in world XYZ coordinates
        strike_vct = np_float64(
            self.get_uid_strike_vect(section_uid=section_uid).reshape(1, 3)
        )
        dip_vct = np_float64(
            self.get_uid_dip_vect(section_uid=section_uid).reshape(1, 3)
        )
        normal_vct = np_float64(
            self.get_uid_normal_vect(section_uid=section_uid).reshape(1, 3)
        )
        origin = self.get_uid_origin(uid=section_uid).reshape(1, 3)
        XYZ = np_array([X, Y, Z]).T
        # the following is the vector from the origin of the cross-section plane
        # to the point XYZ, still in world XYZ coordinates
        origin_2_point = np_float64(XYZ - origin)
        # and here we convert to the UVW coordinates of the cross-section plane with dot products
        # W is just to check and can be commented in the future
        U = np_float32(np_dot(origin_2_point, strike_vct.T))
        V = np_float32(np_dot(origin_2_point, dip_vct.T))
        W = np_float32(np_dot(origin_2_point, normal_vct.T))
        if any(W**2 > 1e-10):
            print(" ---> check W (should be zero): ", W)
        if as_arr:
            return np_array([U, V]).T
        else:
            return U, V

    def plane2world(self, section_uid=None, U=None, V=None, as_arr=False):
        """Get XYZ world coordinates from UV cross-section plane coordinates."""
        # the following are strike, dip, normal unit vectors and the
        # position vector origin of the cross-section plane in world XYZ coordinates
        strike_vct = np_float64(self.get_uid_strike_vect(section_uid=section_uid))
        dip_vct = np_float64(self.get_uid_dip_vect(section_uid=section_uid))
        origin = np_float64(self.get_uid_origin(uid=section_uid))
        # the following is the vector from the origin of the cross-section plane
        # to the point UV, already in world XYZ coordinates
        origin_2_point = strike_vct * U + dip_vct * V
        # then we add the vector from the origin of the cross-section plane to
        # world coordinates origin (0,0,0), and we get the position in world XYZ coordinates
        XYZ = np_float32(origin_2_point + origin)
        X = XYZ[0]
        Y = XYZ[1]
        Z = XYZ[2]
        if as_arr:
            return XYZ
        else:
            return X, Y, Z

    def set_geometry(self, uid=None):
        """Given all parameters, sets the vtkPlane origin and normal properties, and builds the frame used for
        visualization"""

        # origin = [
        #     self.df.loc[self.df["uid"] == uid, "origin_x"].values[0],
        #     self.df.loc[self.df["uid"] == uid, "origin_y"].values[0],
        #     self.df.loc[self.df["uid"] == uid, "origin_z"].values[0],
        # ]
        origin = self.get_uid_origin(uid=uid)
        # end_point = [
        #     self.df.loc[self.df["uid"] == uid, "end_x"].values[0],
        #     self.df.loc[self.df["uid"] == uid, "end_y"].values[0],
        #     self.df.loc[self.df["uid"] == uid, "end_z"].values[0],
        # ]
        # end_point = [
        #     self.df.loc[self.df["uid"] == uid, "origin_x"].values[0] + self.df.loc[self.df["uid"] == uid, "length"].values[0] * np_sin(self.df.loc[self.df["uid"] == uid, "strike"].values[0] * np_pi / 180),
        #     self.df.loc[self.df["uid"] == uid, "origin_y"].values[0] + self.df.loc[self.df["uid"] == uid, "length"].values[0] * np_cos(self.df.loc[self.df["uid"] == uid, "strike"].values[0] * np_pi / 180),
        #     self.df.loc[self.df["uid"] == uid, "origin_z"].values[0],
        # ]
        # normal = [
        #     self.df.loc[self.df["uid"] == uid, "normal_x"].values[0],
        #     self.df.loc[self.df["uid"] == uid, "normal_y"].values[0],
        #     self.df.loc[self.df["uid"] == uid, "normal_z"].values[0],
        # ]
        normal = self.get_uid_normal_vect(section_uid=uid)

        # dip = np_deg2rad(self.df.loc[self.df["uid"] == uid, "dip"].values[0])
        # azi_r = np_deg2rad(self.df.loc[self.df["uid"] == uid, "strike"].values[0])

        height = self.df.loc[self.df["uid"] == uid, "height"].values[0]
        length = self.df.loc[self.df["uid"] == uid, "length"].values[0]
        # bottom = self.df.loc[self.df["uid"] == uid, "bottom"].values[0]

        strike_vct = self.get_uid_strike_vect(section_uid=uid)
        dip_vct = self.get_uid_dip_vect(section_uid=uid)
        normal_vct = self.get_uid_normal_vect(section_uid=uid)

        # frame is a polyline ordered according the right-hand rule, with the thumb pointing as the
        # cross-section normal unit vector, and the first point in the origin, so the second
        # point is given by origin + strike vector * length, etc. as follows

        second_point = origin + strike_vct * length
        third_point = origin + strike_vct * length + dip_vct * height
        fourth_point = origin + dip_vct * height

        vtk_frame = XsPolyLine(x_section_uid=uid, parent=self.parent)

        frame_points = vtkPoints()
        frame_cells = vtkCellArray()
        frame_points.InsertPoint(0, origin[0], origin[1], origin[2])
        frame_points.InsertPoint(1, second_point[0], second_point[1], second_point[2])
        frame_points.InsertPoint(2, third_point[0], third_point[1], third_point[2])
        frame_points.InsertPoint(3, fourth_point[0], fourth_point[1], fourth_point[2])
        line = vtkLine()
        line.GetPointIds().SetId(0, 0)
        line.GetPointIds().SetId(1, 1)
        frame_cells.InsertNextCell(line)
        line.GetPointIds().SetId(0, 1)
        line.GetPointIds().SetId(1, 2)
        frame_cells.InsertNextCell(line)
        line.GetPointIds().SetId(0, 2)
        line.GetPointIds().SetId(1, 3)
        frame_cells.InsertNextCell(line)
        line.GetPointIds().SetId(0, 3)
        line.GetPointIds().SetId(1, 0)
        frame_cells.InsertNextCell(line)
        vtk_frame.SetPoints(frame_points)
        vtk_frame.SetLines(frame_cells)
        vtk_plane = Plane()
        vtk_plane.SetOrigin(origin)
        vtk_plane.SetNormal(normal)
        self.df.loc[self.df["uid"] == uid, "vtk_plane"] = vtk_plane
        self.df.loc[self.df["uid"] == uid, "vtk_frame"] = vtk_frame

    # def set_length(self, uid=None):
    #     self.df.loc[self.df["uid"] == uid, "length"] = np_sqrt(
    #         (
    #             self.df.loc[self.df["uid"] == uid, "origin_x"]
    #             - self.df.loc[self.df["uid"] == uid, "end_x"]
    #         )
    #         ** 2
    #         + (
    #             self.df.loc[self.df["uid"] == uid, "origin_y"]
    #             - self.df.loc[self.df["uid"] == uid, "end_y"]
    #         )
    #         ** 2
    #     )

    # def set_width(
    #     self, uid=None
    # ):  # ----------------------------------------------------------------------
    #     self.df.loc[self.df["uid"] == uid, "height"] = (
    #         self.df.loc[self.df["uid"] == uid, "top"]
    #         - self.df.loc[self.df["uid"] == uid, "bottom"]
    #     )

    def get_all_xsect_entities(self, xuid=None):
        """Get all entities belonging to the uid cross-section, in a dictionary sorted by collection, excluding the cross-section itself."""
        all_entities = {}
        out_entities = {}
        for coll_name in self.parent.tab_collection_dict.values():
            coll = eval(f"self.parent.{coll_name}")
            if coll_name != "xsect_coll":
                all_entities[coll_name] = coll.get_xuid_uid(xuid=xuid)
        for key in all_entities.keys():
            if all_entities[key]:
                out_entities[key] = all_entities[key]
        return out_entities

    def fit_to_entities(self, xuid=None, fit_method=None):
        """
        Fit the xsection geometry to its child entities.
        fit_method could be 'dipping', 'vertical' or 'frame', and in the third case only length, height, and the frame
        are resized, but strike, dip, and origin are kept unchanged.
        """
        if not any(
            [fit_method == "dipping", fit_method == "vertical", fit_method == "frame"]
        ):
            return
        # collect all entities belonging to the cross-section in a dictionary sorted by collection
        all_entities = self.get_all_xsect_entities(xuid=xuid)
        # create a temporary point cloud appending all points belonging to all entities
        # in case this method is found to be too heavy, in the future we can rewrite it using just the
        # maximum and minimum extent of each entity
        vtkappend = vtkAppendPolyData()
        for coll_name in all_entities.keys():
            coll = eval(f"self.parent.{coll_name}")
            for uid in all_entities[coll_name]:
                if coll.get_uid_topology(uid=uid) in [
                    "XsVertexSet",
                    "XsPolyLine",
                    "XsTriSurf",
                    "XsAttitude",
                ]:
                    vtkappend.AddInputData(coll.get_uid_vtk_obj(uid))
                elif coll.get_uid_topology(uid=uid) in ["XsVoxet", "XsImage"]:
                    vtkappend.AddInputData(coll.get_uid_vtk_obj(uid).frame.GetOutput())
        vtkappend.Update()
        append_points = WrapDataObject(vtkappend.GetOutput()).Points
        if append_points.size == 0:
            return
        # get the best fitting plane parameters
        fit_origin, fit_normal = best_fitting_plane(append_points)
        # for all methods, set origin to that returned by the best-fitting plane
        self.set_uid_origin_x(xuid, fit_origin[0])
        self.set_uid_origin_y(xuid, fit_origin[1])
        self.set_uid_origin_z(xuid, fit_origin[2])
        # now fit origin, strike and dip if the 'dipping' option is selected
        if any([fit_method == "dipping", fit_method == "vertical"]):
            if fit_normal[2] > 0:
                # force cross-section plane to dip with geological convention, i.e. normal vector points downwards
                fit_normal = -fit_normal
            if fit_method == "vertical":
                # force fit_normal to be horizontal -> dip = 90 deg
                fit_normal[0] /= np_sqrt(fit_normal[0] ** 2 + fit_normal[1] ** 2)
                fit_normal[1] /= np_sqrt(fit_normal[0] ** 2 + fit_normal[1] ** 2)
                fit_normal[2] = 0
            # calculate strike and dip from fit_normal vector oriented downwards, i.e. as pole to plane
            strike = (
                np_float32(
                    np_rad2deg(
                        np_arctan2(np_float64(fit_normal[0]), np_float64(fit_normal[1]))
                    )
                    + 90
                )
                % 360
            )
            dip = 90 - np_rad2deg(np_arcsin(np_float64(-fit_normal[2])))
            # set strike and dip in XSection
            self.set_uid_strike(xuid, strike)
            self.set_uid_dip(xuid, dip)
        # Reset data model (maybe not necessary but seems a good idea)
        self.modelReset.emit()
        # now for all options we resize the cross-section frame, length, height and origin to fit the child entities
        append_points_U, append_points_V = self.world2plane(
            section_uid=xuid,
            X=append_points[:, 0],
            Y=append_points[:, 1],
            Z=append_points[:, 2],
        )
        max_U = max(append_points_U)
        min_U = min(append_points_U)
        max_V = max(append_points_V)
        min_V = min(append_points_V)
        new_length = max_U - min_U
        new_height = max_V - min_V
        shift_origin = self.plane2world(section_uid=xuid, U=min_U, V=min_V, as_arr=True)
        self.set_uid_length(xuid, new_length)
        self.set_uid_width(xuid, new_height)
        self.set_uid_origin_x(xuid, shift_origin[0])
        self.set_uid_origin_y(xuid, shift_origin[1])
        self.set_uid_origin_z(xuid, shift_origin[2])
        self.set_geometry(uid=xuid)
        # Reset data model
        self.modelReset.emit()
        # Emit a list of uids, even if the entity is just one
        self.parent.signals.geom_modified.emit([xuid], self)

        # optionally here at the end we could ensure all child entities are exactly aligned with the
        # cross-section plane by projecting them along the normal vector - not yet implemented

        return xuid
