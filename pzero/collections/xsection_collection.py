"""xsection_collection.py
PZero© Andrea Bistacchi"""

import uuid

from copy import deepcopy

from numpy import array as np_array
from numpy import ndarray as np_ndarray
from numpy import cos as np_cos
from numpy import deg2rad as np_deg2rad
from numpy import dot as np_dot
from numpy import matmul as np_matmul
from numpy import pi as np_pi
from numpy import repeat as np_repeat
from numpy import sin as np_sin
from numpy import sqrt as np_sqrt
from numpy import sign as np_sign
from numpy.linalg import inv as np_linalg_inv

from pandas import DataFrame as pd_DataFrame
from pandas import read_csv as pd_read_csv
from pandas import unique as pd_unique
from pandas import concat as pd_concat

from vtk import vtkPoints, vtkCellArray, vtkLine

from pzero.entities_factory import Plane, XsPolyLine
from pzero.helpers.helper_dialogs import general_input_dialog, open_file_dialog
from pzero.helpers.helper_functions import auto_sep
from pzero.orientation_analysis import dip_directions2normals, get_dip_dir_vectors

from .AbstractCollection import BaseCollection


# =================================== Methods used to create cross sections ===========================================


def section_from_azimuth(self, vector):
    """Create cross section from one point and azimuth."""
    section_dict = deepcopy(self.parent.xsect_coll.entity_dict)
    self.plotter.untrack_click_position(side="left")

    # points = np.array([vector.p1, vector.p2])

    section_dict_in = {
        "warning": [
            "XSection from azimuth",
            "Build new XSection from a user-drawn line.\nOnce drawn, values can be modified from keyboard\nor by drawing another vector.",
            "QLabel",
        ],
        "name": ["Insert Xsection name", "new_section", "QLineEdit"],
        "base_x": ["Insert origin X coord", vector.p1[0], "QLineEdit"],
        "base_y": ["Insert origin Y coord", vector.p1[1], "QLineEdit"],
        "end_x": ["Insert end X coord", vector.p2[0], "QLineEdit"],
        "end_y": ["Insert end Y coord", vector.p2[1], "QLineEdit"],
        "azimuth": ["Insert azimuth", vector.azimuth, "QLineEdit"],
        "dip": ["Insert dip", 90.0, "QLineEdit"],
        "length": ["Insert length", vector.length, "QLineEdit"],
        "width": ["Insert width", 0.0, "QLineEdit"],
        "bottom": ["Insert bottom", 0.0, "QLineEdit"],
        "multiple": [
            "Multiple XSections",
            "Draw a set of parallel XSections",
            "QCheckBox",
        ],
        "spacing": ["Spacing", 1000.0, "QLineEdit"],
        "num_xs": ["Number of XSections", 5, "QLineEdit"],
        "along": ["Repeat parallel to:", ["Normal", "Azimuth"], "QComboBox"],
    }
    section_dict_updt = general_input_dialog(
        title="New XSection from points", input_dict=section_dict_in
    )
    if section_dict_updt is None:
        # Check for a valid input dictionary.
        # If None un-freeze the Qt interface and return.
        self.enable_actions()
        return
    while True:
        # Add "_0" to section name to ensure uniqueness.
        if section_dict_updt["name"] in self.parent.xsect_coll.get_names:
            section_dict_updt["name"] = section_dict_updt["name"] + "_0"
        else:
            break
    for key in section_dict_updt:
        # Update section dictionary entries.
        section_dict[key] = section_dict_updt[key]
    # Use other dialog dictionary entries as parameters for multiple sections.
    multiple = section_dict["multiple"]
    num_xs = section_dict["num_xs"]
    along = section_dict["along"]
    section_dict.pop("multiple", None)
    section_dict.pop("num_xs", None)
    # Define other (redundant) section parameters.
    section_dict["base_z"] = section_dict["bottom"]
    # section_dict["top"] = section_dict.get("bottom") + section_dict.get("width")
    section_dict["end_z"] = section_dict["top"]
    # Calculate normals.
    normals = dip_directions2normals(
        dips=section_dict["dip"], directions=(section_dict["azimuth"] + 90) % 360
    )
    section_dict["normal_x"] = normals[0]
    section_dict["normal_y"] = normals[1]
    section_dict["normal_z"] = normals[2]
    # ADD CROSS-SECTION TO COLLECTION.
    uid = self.parent.xsect_coll.add_entity_from_dict(entity_dict=section_dict)
    # The following seems not necessary
    # if section_dict is None:
    #     """Un-Freeze QT interface"""
    #     self.enable_actions()
    # if multiple == "uncheck":
    #     """Un-Freeze QT interface"""
    #     self.enable_actions()
    # The following adds more parallel seriated cross-sections.
    if multiple == "check":
        name_original_xs = section_dict["name"]
        spacing = section_dict["spacing"]
        for xsect in range(num_xs - 1):
            section_dict["name"] = name_original_xs + "_" + str(xsect)
            while True:
                if section_dict["name"] in self.parent.xsect_coll.get_names:
                    section_dict["name"] = section_dict["name"] + "_0"
                else:
                    break
            tx = self.parent.xsect_coll.get_uid_normal_x(uid) * spacing
            ty = self.parent.xsect_coll.get_uid_normal_y(uid) * spacing
            if along == "Normal":
                tz = self.parent.xsect_coll.get_uid_normal_z(uid) * spacing
            else:
                tz = 0
            trans_mat = np_array(
                [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [tx, ty, tz, 1]]
            )
            frame = self.parent.xsect_coll.get_uid_vtk_obj(uid)
            homo_points = frame.get_homo_points()
            new_points = np_matmul(homo_points, trans_mat)[:, :-1]
            section_dict["base_x"] = new_points[0, 0]
            section_dict["base_y"] = new_points[0, 1]
            section_dict["base_z"] = new_points[0, 2]
            section_dict["end_x"] = new_points[3, 0]
            section_dict["end_y"] = new_points[3, 1]
            section_dict["end_z"] = new_points[3, 2]
            section_dict["bottom"] = new_points[0, 2]
            section_dict["top"] = new_points[3, 2]
            section_dict["uid"] = None
            uid = self.parent.xsect_coll.add_entity_from_dict(entity_dict=section_dict)
    # At the end un-freeze the Qt interface before returning.
    self.enable_actions()


def sections_from_file(self):
    """Create cross section from file."""
    # Read GOCAD ASCII (.pl) or ASCII files (.dat) to extract the data necessary to create a section (or
    # multiple sections). The necessary keys are defined in the section_dict_updt dict.
    # For GOCAD ASCII the file is parsed for every line searching for key words that define the line containing the data.
    # For normal ASCII files exported from MOVE the data is registered as a csv and so the pd_read_csv function can be
    # used. The separator is automatically extracted using csv.Sniffer() (auto_sep helper function).
    # For both importing methods the user must define the top and bottom values of the section.

    # section_from_points IS MISSING! BUT IT IS NOT NECESSARY. SIMILAR FUNCTIONALITY
    # IS ALREADY PRESENT IN section_from_azimuth
    # USE THAT OR EXTRACT "FROM POINTS" IN A SEPARATE FUNCTION
    # OR CREATE A METHOD TO FILL MISSING PARAMETERS IN THE COLLECTION??

    from os.path import splitext

    section_dict = deepcopy(self.parent.xsect_coll.entity_dict)
    section_dict_updt = {
        "name": "",
        "base_x": 0,
        "base_y": 0,
        "end_x": 0,
        "end_y": 0,
        "dip": 90.0,
        "top": 0,
        "bottom": 0,
    }
    files = open_file_dialog(
        parent=self,
        caption="Import section traces",
        filter="GOCAD ASCII (*.*);;ASCII (*.dat);;CSV (*.csv)",
        multiple=True,
    )
    # return file and extension list
    # This could be implemented automatically in open_file_dialog
    name, extension = splitext(files[0])
    section_dict_in = {
        "warning": [
            "XSection from file",
            "Build new XSection from a GOCAD ASCII or simple ASCII file.\nChoose the top and bottom limit of the sections to continue",
            "QLabel",
        ],
        "top": ["Insert top", 0.0, "QLineEdit"],
        "bottom": ["Insert bottom", 0.0, "QLineEdit"],
    }
    for file in files:
        # Check the file type and import accordingly
        # If no valid type is found, do nothing.
        if extension == ".pl":
            top_bottom = general_input_dialog(
                title="XSection from files", input_dict=section_dict_in
            )
            with open(file, "r") as IN:
                for line in IN:
                    if "name:" in line:
                        line_data = line.strip().split(":")
                        section_dict["name"] = line_data[1]
                    elif "VRTX 1" in line:
                        line_data = line.strip().split()
                        section_dict["base_x"] = float(line_data[2])
                        section_dict["base_y"] = float(line_data[3])
                    elif "VRTX 2" in line:
                        line_data = line.strip().split()
                        section_dict["end_x"] = float(line_data[2])
                        section_dict["end_y"] = float(line_data[3])
                    elif line.strip() == "END":
                        # When the END line is reached create a section
                        section_dict["base_z"] = top_bottom["bottom"]
                        section_dict["bottom"] = top_bottom["bottom"]
                        section_dict["end_z"] = top_bottom["top"]
                        section_dict["top"] = top_bottom["top"]
                        # UPDATE OTHER PARAMETERS BEFORE CREATING SECTION _______________________________________
                        uid = self.parent.xsect_coll.add_entity_from_dict(
                            entity_dict=section_dict
                        )

        elif extension == ".dat":
            top_bottom = general_input_dialog(
                title="XSection from files", input_dict=section_dict_in
            )
            sep = auto_sep(file)
            pd_df = pd_read_csv(file, sep=sep)
            unique_traces = pd_unique(pd_df["Name"])
            for trace in unique_traces:
                section_dict["name"] = trace
                section_dict["base_x"] = pd_df.loc[
                    (pd_df["Name"] == trace) & (pd_df["Vertex Index"] == 1)
                ]["x"].values
                section_dict["base_y"] = pd_df.loc[
                    (pd_df["Name"] == trace) & (pd_df["Vertex Index"] == 1)
                ]["y"].values
                section_dict["base_z"] = pd_df.loc[
                    (pd_df["Name"] == trace) & (pd_df["Vertex Index"] == 1)
                ]["y"].values
                section_dict["end_x"] = pd_df.loc[
                    (pd_df["Name"] == trace) & (pd_df["Vertex Index"] == 2)
                ]["x"].values
                section_dict["end_y"] = pd_df.loc[
                    (pd_df["Name"] == trace) & (pd_df["Vertex Index"] == 2)
                ]["y"].values
                section_dict["base_z"] = top_bottom["bottom"]
                section_dict["bottom"] = top_bottom["bottom"]
                section_dict["end_z"] = top_bottom["top"]
                section_dict["top"] = top_bottom["top"]
                # UPDATE OTHER PARAMETERS BEFORE CREATING SECTION _______________________________________
                uid = self.parent.xsect_coll.add_entity_from_dict(
                    entity_dict=section_dict
                )

        elif extension == ".csv":
            sep = auto_sep(file)
            pd_df = pd_read_csv(file, sep=sep)
            for index, sec in pd_df.iterrows():
                section_dict["name"] = sec["name"]
                section_dict["base_x"] = sec["base_x"]
                section_dict["base_y"] = sec["base_y"]
                section_dict["end_x"] = sec["end_x"]
                section_dict["end_y"] = sec["end_y"]
                section_dict["base_z"] = top_bottom["bottom"]
                section_dict["bottom"] = top_bottom["bottom"]
                section_dict["end_z"] = top_bottom["top"]
                section_dict["top"] = top_bottom["top"]
                # UPDATE OTHER PARAMETERS BEFORE CREATING SECTION _______________________________________
                uid = self.parent.xsect_coll.add_entity_from_dict(
                    entity_dict=section_dict
                )


class XSectionCollection(BaseCollection):
    """Cross-section collection."""

    def __init__(self, parent=None, *args, **kwargs):
        super(XSectionCollection, self).__init__(parent, *args, **kwargs)

        # Initialize properties required by the abstract superclass.
        self.entity_dict = {
            "uid": "",
            "name": "undef",
            "scenario": "undef",
            "base_x": 0.0,
            "base_y": 0.0,
            "base_z": 0.0,
            "end_x": 0.0,
            "end_y": 0.0,
            "end_z": 0.0,
            "normal_x": 0.0,
            "normal_y": 0.0,
            "normal_z": 0.0,
            "azimuth": 0.0,
            "dip": 90.0,
            "length": 0.0,
            "width": 0.0,
            "top": 0.0,
            "bottom": 0.0,
            "vtk_plane": None,  # None to avoid errors with deepcopy
            "vtk_frame": None,  # None to avoid errors with deepcopy
        }
        self.entity_dict_types = {
            "uid": str,
            "name": str,
            "scenario": "undef",
            "base_x": float,
            "base_y": float,
            "base_z": float,
            "end_x": float,
            "end_y": float,
            "end_z": float,
            "normal_x": float,
            "normal_y": float,
            "normal_z": float,
            "azimuth": float,
            "dip": float,
            "length": float,
            "width": float,
            "top": float,
            "bottom": float,
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
        """Add new cross-section from a suitable dictionary shaped like self.entity_dict."""
        # Create a new uid if it is not included in the dictionary.
        if not entity_dict["uid"]:
            entity_dict["uid"] = str(uuid.uuid4())
        # Append new row to dataframe. Note that the 'append()' method for Pandas dataframes DOES NOT
        # work in place, hence a NEW dataframe is created every time and then substituted to the old one.
        # Old and less efficient syntax used up to Pandas 1.5.3:
        # self.df = self.df.append(entity_dict, ignore_index=True)
        # New syntax with Pandas >= 2.0.0:
        self.df = pd_concat([self.df, pd_DataFrame([entity_dict])], ignore_index=True)
        self.set_geometry(uid=entity_dict["uid"])
        # Reset data model
        self.modelReset.emit()
        # Emit a list of uids, even if the entity is just one
        self.parent.signals.entities_added.emit([entity_dict["uid"]], self)
        return entity_dict["uid"]

    def remove_entity(self, uid: str = None) -> str:
        """Remove row from dataframe and reset data model. NOTE THAT AT THE MOMENT
        REMOVING A SECTION DOES NOT REMOVE THE ASSOCIATED OBJECTS."""
        if uid not in self.get_uids:
            return
        self.df.drop(self.df[self.df["uid"] == uid].index, inplace=True)
        self.modelReset.emit()  # is this really necessary?
        # Emit a list of uids, even if the entity is just one
        self.parent.signals.entities_removed.emit([uid], self)
        return uid

    def clone_entity(self, uid: str = None) -> str:
        """Not implemented for XSectionCollection, but required by the abstract superclass."""
        pass

    def attr_modified_update_legend_table(self):
        """Not implemented for XSectionCollection, but required by the abstract superclass."""
        pass

    def remove_unused_from_legend(self):
        """Remove unused types / features from a legend table."""
        legend_updated: bool = False
        return legend_updated

    def get_uid_legend(self, uid: str = None) -> dict:
        """Supposed to get legend for a particular uid, in this case gets legend for XSection that are all the same."""
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
        """Not implemented for XSectionCollection, but required by the abstract superclass."""
        pass

    # =================================== Additional methods ===========================================

    def get_uid_base_x(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df["uid"] == uid, "base_x"].values[0]

    def set_uid_base_x(self, uid=None, base_x=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df["uid"] == uid, "base_x"] = base_x

    def get_uid_base_y(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df["uid"] == uid, "base_y"].values[0]

    def set_uid_base_y(self, uid=None, base_y=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df["uid"] == uid, "base_y"] = base_y

    def get_uid_base_z(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df["uid"] == uid, "base_z"].values[0]

    def set_uid_base_z(self, uid=None, base_z=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df["uid"] == uid, "base_z"] = base_z

    def get_uid_end_x(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df["uid"] == uid, "end_x"].values[0]

    def set_uid_end_x(self, uid=None, end_x=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df["uid"] == uid, "end_x"] = end_x

    def get_uid_end_y(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df["uid"] == uid, "end_y"].values[0]

    def set_uid_end_y(self, uid=None, end_y=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df["uid"] == uid, "end_y"] = end_y

    def get_uid_end_z(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df["uid"] == uid, "end_z"].values[0]

    def set_uid_end_z(self, uid=None, end_z=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df["uid"] == uid, "end_z"] = end_z

    def get_uid_normal_x(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df["uid"] == uid, "normal_x"].values[0]

    def set_uid_normal_x(self, uid=None, normal_x=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df["uid"] == uid, "normal_x"] = normal_x

    def get_uid_normal_y(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df["uid"] == uid, "normal_y"].values[0]

    def set_uid_normal_y(self, uid=None, normal_y=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df["uid"] == uid, "normal_y"] = normal_y

    def get_uid_normal_z(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df["uid"] == uid, "normal_z"].values[0]

    def set_uid_normal_z(self, uid=None, normal_z=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df["uid"] == uid, "normal_z"] = normal_z

    def get_uid_azimuth(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df["uid"] == uid, "azimuth"].values[0]

    def set_uid_azimuth(self, uid=None, azimuth=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df["uid"] == uid, "azimuth"] = azimuth

    def get_uid_length(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df["uid"] == uid, "length"].values[0]

    def set_uid_length(self, uid=None, length=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df["uid"] == uid, "length"] = length

    def get_uid_width(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df["uid"] == uid, "width"].values[0]

    def set_uid_width(self, uid=None, width=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df["uid"] == uid, "width"] = width

    def get_uid_top(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df["uid"] == uid, "top"].values[0]

    def set_uid_top(self, uid=None, top=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df["uid"] == uid, "top"] = top

    def get_uid_bottom(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df["uid"] == uid, "bottom"].values[0]

    def set_uid_bottom(self, uid=None, bottom=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df["uid"] == uid, "bottom"] = bottom

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

    def set_parameters_in_table(
        self,
        uid=None,
        name=None,
        base_point=None,
        end_point=None,
        normal=None,
        azimuth=None,
        length=None,
        top=None,
        bottom=None,
    ):
        """Write parameters in Xsections Pandas dataframe"""
        self.df.loc[self.df["uid"] == uid, "name"] = name
        self.df.loc[self.df["uid"] == uid, "base_x"] = base_point[0]
        self.df.loc[self.df["uid"] == uid, "base_y"] = base_point[1]
        self.df.loc[self.df["uid"] == uid, "base_z"] = base_point[2]
        self.df.loc[self.df["uid"] == uid, "end_x"] = end_point[0]
        self.df.loc[self.df["uid"] == uid, "end_y"] = end_point[1]
        self.df.loc[self.df["uid"] == uid, "end_z"] = end_point[2]
        self.df.loc[self.df["uid"] == uid, "normal_x"] = normal[0]
        self.df.loc[self.df["uid"] == uid, "normal_y"] = normal[1]
        self.df.loc[self.df["uid"] == uid, "normal_z"] = normal[2]
        self.df.loc[self.df["uid"] == uid, "azimuth"] = azimuth
        self.df.loc[self.df["uid"] == uid, "length"] = length
        self.df.loc[self.df["uid"] == uid, "top"] = top
        self.df.loc[self.df["uid"] == uid, "bottom"] = bottom

    def set_from_table(self, uid=None):
        """Get parameters from x_section table and set them on x_section"""
        self.set_geometry(uid=uid)

    def get_XY_from_W(self, section_uid=None, W=None):
        """Gets X, Y coordinates from W coordinate (distance along the Xsection horizontal axis).
        Should work for a single W value or for an array, in which case should return X, Y as arrays.
        """
        azimuth = self.df.loc[self.df["uid"] == section_uid, "azimuth"].values[0]
        base_x = self.df.loc[self.df["uid"] == section_uid, "base_x"].values[0]
        base_y = self.df.loc[self.df["uid"] == section_uid, "base_y"].values[0]
        X = W * np_sin(azimuth * np_pi / 180) + base_x
        Y = W * np_cos(azimuth * np_pi / 180) + base_y
        return X, Y

    def get_W_from_XY(self, section_uid=None, X=None, Y=None):
        """Gets W coordinate (distance along the Xsection horizontal axis) from X, Y coordinates.
        Should work for a single W value or for an array, in which case should return X, Y as arrays.
        """
        base_x = self.df.loc[self.df["uid"] == section_uid, "base_x"].values[0]
        base_y = self.df.loc[self.df["uid"] == section_uid, "base_y"].values[0]
        end_x = self.df.loc[self.df["uid"] == section_uid, "end_x"].values[0]
        end_y = self.df.loc[self.df["uid"] == section_uid, "end_y"].values[0]
        sense = np_sign(
            (X - base_x) * (end_x - base_x) + (Y - base_y) * (end_y - base_y)
        )
        W = np_sqrt((X - base_x) ** 2 + (Y - base_y) ** 2) * sense
        return W

    def get_deltaXY_from_deltaW(self, section_uid=None, deltaW=None):
        """Gets X, Y coordinates from W coordinate (distance along the Xsection horizontal axis)"""
        azimuth = self.df.loc[self.df["uid"] == section_uid, "azimuth"].values[0]
        deltaX = deltaW * np_sin(azimuth * np_pi / 180)
        deltaY = deltaW * np_cos(azimuth * np_pi / 180)
        return deltaX, deltaY

    def plane2world(self, section_uid=None, u=None, v=None, as_arr=False):
        n_points = len(u)
        plane = self.get_uid_vtk_plane(section_uid)

        normal = np_array(plane.GetNormal())
        origin = np_array(plane.GetOrigin())
        d = np_repeat(np_dot(normal, origin), n_points)

        dip_vec, dir_vec = get_dip_dir_vectors(np_array([normal]))
        A = np_array([dir_vec[0], dip_vec[0], normal])
        B = np_array(
            [u, -v, d]
        )  # this should be [-u +v -d] (because we calculated -v) but it is opposite because of the right hand rule
        X = np_linalg_inv(A).dot(B).T

        if as_arr:
            return X
        else:
            return X[:, 0], X[:, 1], X[:, 2]

    def set_geometry(self, uid=None):
        """ "Given all parameters, sets the vtkPlane origin and normal properties, and builds the frame used for
        visualization"""

        base_point = [
            self.df.loc[self.df["uid"] == uid, "base_x"].values[0],
            self.df.loc[self.df["uid"] == uid, "base_y"].values[0],
            self.df.loc[self.df["uid"] == uid, "base_z"].values[0],
        ]
        end_point = [
            self.df.loc[self.df["uid"] == uid, "end_x"].values[0],
            self.df.loc[self.df["uid"] == uid, "end_y"].values[0],
            self.df.loc[self.df["uid"] == uid, "end_z"].values[0],
        ]
        normal = [
            self.df.loc[self.df["uid"] == uid, "normal_x"].values[0],
            self.df.loc[self.df["uid"] == uid, "normal_y"].values[0],
            self.df.loc[self.df["uid"] == uid, "normal_z"].values[0],
        ]

        dip = np_deg2rad(self.df.loc[self.df["uid"] == uid, "dip"].values[0])
        azimuth = np_deg2rad(
            (self.df.loc[self.df["uid"] == uid, "azimuth"].values[0] + 180) % 360
        )

        width = self.df.loc[self.df["uid"] == uid, "width"].values[0]
        bottom = self.df.loc[self.df["uid"] == uid, "bottom"].values[0]

        vtk_frame = XsPolyLine(x_section_uid=uid, parent=self.parent)

        frame_points = vtkPoints()
        frame_cells = vtkCellArray()
        frame_points.InsertPoint(0, base_point[0], base_point[1], bottom)
        frame_points.InsertPoint(
            1,
            base_point[0] + width * np_cos(dip) * np_cos(-azimuth),
            base_point[1] + width * np_cos(dip) * np_sin(-azimuth),
            bottom + width * np_sin(dip),
        )
        frame_points.InsertPoint(
            2,
            end_point[0] + width * np_cos(dip) * np_cos(-azimuth),
            end_point[1] + width * np_cos(dip) * np_sin(-azimuth),
            bottom + width * np_sin(dip),
        )
        frame_points.InsertPoint(3, end_point[0], end_point[1], bottom)
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
        vtk_plane.SetOrigin(base_point)
        vtk_plane.SetNormal(normal)
        self.df.loc[self.df["uid"] == uid, "vtk_plane"] = vtk_plane
        self.df.loc[self.df["uid"] == uid, "vtk_frame"] = vtk_frame

    def set_length(self, uid=None):
        self.df.loc[self.df["uid"] == uid, "length"] = np_sqrt(
            (
                self.df.loc[self.df["uid"] == uid, "base_x"]
                - self.df.loc[self.df["uid"] == uid, "end_x"]
            )
            ** 2
            + (
                self.df.loc[self.df["uid"] == uid, "base_y"]
                - self.df.loc[self.df["uid"] == uid, "end_y"]
            )
            ** 2
        )

    def set_width(self, uid=None):
        self.df.loc[self.df["uid"] == uid, "width"] = (
            self.df.loc[self.df["uid"] == uid, "top"]
            - self.df.loc[self.df["uid"] == uid, "bottom"]
        )

    def get_all_xsect_entities(self, xuid=None):
        """Get all entities belonging to the uid cross-section, in a dictionary sorted by collection."""
        all_entities = {}
        for coll_name in self.parent.tab_collection_dict.values():
            coll = eval(f"self.parent.{coll_name}")
            if coll_name != "xsect_coll":
                all_entities[coll_name] = coll.get_xuid_uid(xuid=xuid)
        return all_entities

    # def fix_top_values_on_load(self):
    #     """Fix saved values: if top == 0.0 and top < bottom, set top = bottom + width and sync end_z."""
    #     if self.df.empty:
    #         return []
    #
    #     # Check where top is zero (old versions) and lower than bottom
    #     needs_top_fix = (self.df["top"] == 0.0) & (self.df["top"] < self.df["bottom"])
    #     if not needs_top_fix.any():
    #         return []
    #
    #     # Compute and assign new top and end_z values
    #     new_top = self.df.loc[needs_top_fix, "bottom"] + self.df.loc[needs_top_fix, "width"]
    #     self.df.loc[needs_top_fix, "top"] = new_top
    #     self.df.loc[needs_top_fix, "end_z"] = new_top
    #
    #     changed_uids = self.df.loc[needs_top_fix, "uid"].tolist()
    #
    #     try:
    #         if changed_uids:
    #             self.modelReset.emit()
    #     except Exception:
    #         pass
    #
    #     return changed_uids
    #
    #
    #
