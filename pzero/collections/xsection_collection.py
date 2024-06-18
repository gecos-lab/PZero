"""xsection_collection.py
PZero© Andrea Bistacchi"""
import uuid

# import numpy_interface.dataset_adapter as dsa
# import numpy_interface.algorithms as algs
from copy import deepcopy

import pandas as pd
from PyQt5.QtCore import QAbstractTableModel, Qt, QVariant
from numpy import array as np_array
from numpy import cos as np_cos
from numpy import deg2rad as np_deg2rad
from numpy import dot as np_dot
from numpy import matmul as np_matmul
from numpy import pi as np_pi
from numpy import repeat as np_repeat
from numpy import set_printoptions as np_set_printoptions
from numpy import sin as np_sin
from numpy.linalg import inv as np_linalg_inv
from vtk import vtkPoints, vtkCellArray, vtkLine

# from PyQt5.QtGui import QStandardItem, QImage
from pzero.entities_factory import Plane, XsPolyLine
from pzero.helpers.helper_dialogs import general_input_dialog, open_file_dialog
from pzero.helpers.helper_functions import auto_sep
from pzero.orientation_analysis import dip_directions2normals, get_dip_dir_vectors

"""Options to print Pandas dataframes in console"""
pd_desired_width = 800
pd_max_columns = 20
pd_show_precision = 4
pd_max_colwidth = 80
pd.set_option("display.width", pd_desired_width)
np_set_printoptions(linewidth=pd_desired_width)
pd.set_option("display.max_columns", pd_max_columns)
pd.set_option("display.precision", pd_show_precision)
pd.set_option("display.max_colwidth", pd_max_colwidth)

""""Methods used to create cross sections."""


def section_from_azimuth(self, vector):
    section_dict = deepcopy(self.parent.xsect_coll.section_dict)

    self.plotter.untrack_click_position(side="left")

    # points = np.array([vector.p1, vector.p2])

    section_dict_in = {
        "warning": [
            "XSection from azimuth",
            "Build new XSection from a user-drawn line.\nOnce drawn, values can be "
            "modified from keyboard\nor by drawing another vector.",
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
        "activate": [
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
        self.enable_actions()
        return

    while True:
        if section_dict_updt["name"] in self.parent.xsect_coll.get_names():
            section_dict_updt["name"] = section_dict_updt["name"] + "_0"
        else:
            break

    for key in section_dict_updt:
        section_dict[key] = section_dict_updt[key]

    activate = section_dict["activate"]
    num_xs = section_dict["num_xs"]
    along = section_dict["along"]

    section_dict.pop("activate", None)
    section_dict.pop("num_xs", None)

    section_dict["base_z"] = section_dict["bottom"]
    section_dict["end_z"] = section_dict["top"]
    normals = dip_directions2normals(
        dips=section_dict["dip"], directions=(section_dict["azimuth"] + 90) % 360
    )
    section_dict["normal_x"] = normals[0]
    section_dict["normal_y"] = normals[1]
    section_dict["normal_z"] = normals[2]
    uid = self.parent.xsect_coll.add_entity_from_dict(entity_dict=section_dict)

    if section_dict is None:
        """Un-Freeze QT interface"""
        self.enable_actions()
    if activate == "uncheck":
        """Un-Freeze QT interface"""
        self.enable_actions()
    else:
        name_original_xs = section_dict["name"]
        spacing = section_dict["spacing"]
        for xsect in range(num_xs - 1):
            section_dict["name"] = name_original_xs + "_" + str(xsect)
            while True:
                if section_dict["name"] in self.parent.xsect_coll.get_names():
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

            frame = self.parent.xsect_coll.get_uid_vtk_frame(uid)
            homo_points = frame.get_homo_points()
            new_points = np_matmul(homo_points, trans_mat)[:, :-1]
            section_dict["base_x"] = new_points[0, 0]
            section_dict["base_y"] = new_points[0, 1]

            section_dict["end_x"] = new_points[3, 0]
            section_dict["end_y"] = new_points[3, 1]
            section_dict["bottom"] = new_points[0, 2]
            section_dict["uid"] = None

            uid = self.parent.xsect_coll.add_entity_from_dict(entity_dict=section_dict)

        self.enable_actions()


def sections_from_file(self):
    from os.path import splitext

    """[Gabriele]  Read GOCAD ASCII (.pl) or ASCII files (.dat) to extract the data necessary to create a section (or 
    multiple sections). The necessary keys are defined in the section_dict_updt dict.

    For GOCAD ASCII the file is parsed for every line searching for key words that define the line containing the data.

    For normal ASCII files exported from MOVE the data is registered as a csv and so the pd.read_csv function can be 
    used. The separator is automatically extracted using csv.Sniffer() (auto_sep helper function).

    For both importing methods the user must define the top and bottom values of the section.
    """
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

    name, extension = splitext(
        files[0]
    )  # [Gabriele] This could be implemented automatically in open_file_dialog
    # return file and extension list

    section_dict_in = {
        "warning": [
            "XSection from file",
            "Build new XSection from a GOCAD ASCII or simple ASCII "
            "file.\nChoose the top and bottom limit of the sections to "
            "continue",
            "QLabel",
        ],
        "top": ["Insert top", 0.0, "QLineEdit"],
        "bottom": ["Insert bottom", 0.0, "QLineEdit"],
    }

    # [Gabriele] Check the file type
    for file in files:
        if extension == ".pl":
            top_bottom = general_input_dialog(
                title="XSection from files", input_dict=section_dict_in
            )
            with open(file, "r") as IN:
                for line in IN:
                    if "name:" in line:
                        line_data = line.strip().split(":")
                        section_dict_updt["name"] = line_data[1]
                    elif "VRTX 1" in line:
                        line_data = line.strip().split()
                        section_dict_updt["base_x"] = float(line_data[2])
                        section_dict_updt["base_y"] = float(line_data[3])
                    elif "VRTX 2" in line:
                        line_data = line.strip().split()
                        section_dict_updt["end_x"] = float(line_data[2])
                        section_dict_updt["end_y"] = float(line_data[3])
                    elif line.strip() == "END":
                        # [Gabriele] When the END of the entry is reached create a section
                        section_dict_updt["top"] = top_bottom["top"]
                        section_dict_updt["bottom"] = top_bottom["bottom"]
                        section_from_points(
                            self, drawn=False, section_dict_updt=section_dict_updt
                        )
        elif extension == ".dat":
            top_bottom = general_input_dialog(
                title="XSection from files", input_dict=section_dict_in
            )
            sep = auto_sep(file)
            pd_df = pd.read_csv(file, sep=sep)
            unique_traces = pd.unique(pd_df["Name"])
            for trace in unique_traces:
                section_dict_updt["name"] = trace
                section_dict_updt["base_x"] = pd_df.loc[
                    (pd_df["Name"] == trace) & (pd_df["Vertex Index"] == 1)
                ]["x"].values
                section_dict_updt["base_y"] = pd_df.loc[
                    (pd_df["Name"] == trace) & (pd_df["Vertex Index"] == 1)
                ]["y"].values
                section_dict_updt["base_z"] = pd_df.loc[
                    (pd_df["Name"] == trace) & (pd_df["Vertex Index"] == 1)
                ]["y"].values
                section_dict_updt["end_x"] = pd_df.loc[
                    (pd_df["Name"] == trace) & (pd_df["Vertex Index"] == 2)
                ]["x"].values
                section_dict_updt["end_y"] = pd_df.loc[
                    (pd_df["Name"] == trace) & (pd_df["Vertex Index"] == 2)
                ]["y"].values
                section_dict_updt["top"] = top_bottom["top"]
                section_dict_updt["bottom"] = top_bottom["bottom"]
                section_from_points(
                    self, drawn=False, section_dict_updt=section_dict_updt
                )
        elif extension == ".csv":
            sep = auto_sep(file)
            pd_df = pd.read_csv(file, sep=sep)
            for index, sec in pd_df.iterrows():
                section_dict_updt["name"] = sec["name"]
                section_dict_updt["base_x"] = sec["base_x"]
                section_dict_updt["base_y"] = sec["base_y"]
                section_dict_updt["end_x"] = sec["end_x"]
                section_dict_updt["end_y"] = sec["end_y"]
                section_dict_updt["top"] = sec["top"]
                section_dict_updt["bottom"] = sec["bottom"]
                section_from_points(
                    self, drawn=False, section_dict_updt=section_dict_updt
                )


def section_from_entities(self):
    """
    Create cross section from selected PolyLine and VertexSet, and convert these entities to XsPolyLine and XsVertexSet.
    """
    print("TEST section_from_entities")
    # Get input objects.
    if self.shown_table != "tabGeology":
        print(" -- Only geological objects can be used at the moment -- ")
        return
    # Check if some vtkPolyData is selected.
    if not self.selected_uids:
        print("No input data selected.")
        return
    else:
        # Deep copy list of selected uids needed otherwise problems can arise if the main geology table is
        # deseselcted while the dataframe is being built.
        input_uids = deepcopy(self.selected_uids)
    # Select points and polylines only.
    input_uids_clean = deepcopy(input_uids)
    for uid in input_uids:
        if self.geol_coll.get_uid_topological_type(uid) not in [
            "VertexSet",
            "PolyLine",
            "XsVertexSet",
            "XsPolyLine",
        ]:
            input_uids_clean.remove(uid)
    input_uids = deepcopy(input_uids_clean)
    del input_uids_clean
    if not input_uids:
        print("No valid input data selected.")
        return

    # Create a vtkAppendPolyData filter to merge all input vtk objects.
    vtkappend = vtk.vtkAppendPolyData()
    for uid in input_uids:
        vtkappend.AddInputData(self.geol_coll.get_uid_vtk_obj(uid))
    vtkappend.Update()

    # Fit new cross section plane.
    new_xs_plane = Plane()
    new_xs_plane.ComputeBestFittingPlane(vtkappend.GetOutput())

    #########################################################





    """Define projection parameters (float64 needed for "t" afterwards)"""
    xs_names = self.xsect_coll.get_names()
    input_dict = {
        "xs_name": ["XSection: ", xs_names],
        "proj_plunge": ["Projection axis plunge: ", 0.0],
        "proj_trend": ["Projection axis trend: ", 0.0],
        "dist_sec": ["Maximum distance from section: ", 0.0],
    }
    options_dict = multiple_input_dialog(
        title="Projection to XSection", input_dict=input_dict
    )
    if options_dict is None:
        return
    xs_name = options_dict["xs_name"]
    xs_dist = options_dict["dist_sec"]
    xs_uid = self.xsect_coll.df.loc[
        self.xsect_coll.df["name"] == xs_name, "uid"
    ].values[0]
    proj_plunge = np_float64(options_dict["proj_plunge"])
    proj_trend = np_float64(options_dict["proj_trend"])
    """Constrain to 0-180."""
    if proj_trend > 180.0:
        proj_trend -= 180.0
        proj_plunge = -proj_plunge
    """Check for projection trend parallel to cross section."""
    if (
            abs(self.xsect_coll.get_uid_azimuth(xs_uid) - proj_trend) < 10.0
            or abs(self.xsect_coll.get_uid_azimuth(xs_uid) - 180.0 - proj_trend) < 10.0
    ):
        print("Plunge too close to being parallel to XSection (angle < 10°)")
        return
    """Get cross section start and end points (float64 needed for "t" afterwards)."""
    xa = np_float64(self.xsect_coll.get_uid_base_x(xs_uid))
    ya = np_float64(self.xsect_coll.get_uid_base_y(xs_uid))
    xb = np_float64(self.xsect_coll.get_uid_end_x(xs_uid))
    yb = np_float64(self.xsect_coll.get_uid_end_y(xs_uid))

    """Calculate projection direction cosines (float64 needed for "t" afterwards)."""
    alpha = np_float64(
        np_sin(proj_trend * np_pi / 180.0) * np_cos(proj_plunge * np_pi / 180.0)
    )
    beta = np_float64(
        np_cos(proj_trend * np_pi / 180.0) * np_cos(proj_plunge * np_pi / 180.0)
    )
    gamma = np_float64(-np_sin(proj_plunge * np_pi / 180.0))
    """Project each entity."""
    for uid in input_uids:
        """Clone entity."""
        entity_dict = deepcopy(self.geol_coll.geological_entity_dict)
        entity_dict["name"] = self.geol_coll.get_uid_name(uid) + "_prj_" + xs_name
        entity_dict["geological_type"] = self.geol_coll.get_uid_geological_type(uid)
        entity_dict["geological_feature"] = self.geol_coll.get_uid_geological_feature(
            uid
        )
        entity_dict["scenario"] = self.geol_coll.get_uid_scenario(uid)
        entity_dict["properties_names"] = self.geol_coll.get_uid_properties_names(uid)
        entity_dict[
            "properties_components"
        ] = self.geol_coll.get_uid_properties_components(uid)
        entity_dict["x_section"] = xs_uid
        if self.geol_coll.get_uid_topological_type(uid) == "VertexSet":
            entity_dict["topological_type"] = "XsVertexSet"
            out_vtk = XsVertexSet(x_section_uid=xs_uid, parent=self)
            out_vtk.DeepCopy(self.geol_coll.get_uid_vtk_obj(uid))
        elif (
                self.geol_coll.get_uid_topological_type(uid) == "PolyLine"
                or self.geol_coll.get_uid_topological_type(uid) == "XsPolyLine"
        ):
            entity_dict["topological_type"] = "XsPolyLine"
            out_vtk = XsPolyLine(x_section_uid=xs_uid, parent=self)
            out_vtk.DeepCopy(self.geol_coll.get_uid_vtk_obj(uid))
        else:
            entity_dict["topological_type"] = self.geol_coll.get_uid_topological_type(
                uid
            )
            out_vtk = self.geol_coll.get_uid_vtk_obj(uid).deep_copy()
        """Perform projection on clone (the last two steps could be merged).
         np_float64 is needed to calculate "t" with a good precision
         when X and Y are in UTM coordinates with very large values,
         then the result is cast to float32 that is the VTK standard."""
        xo = out_vtk.points_X.astype(np_float64)
        yo = out_vtk.points_Y.astype(np_float64)
        zo = out_vtk.points_Z.astype(np_float64)
        t = (-xo * (yb - ya) - yo * (xa - xb) - ya * xb + yb * xa) / (
                alpha * (yb - ya) + beta * (xa - xb)
        )

        out_vtk.points_X[:] = (xo + alpha * t).astype(np_float32)
        out_vtk.points_Y[:] = (yo + beta * t).astype(np_float32)
        out_vtk.points_Z[:] = (zo + gamma * t).astype(np_float32)

        out_vtk.set_point_data("distance", np_abs(t))

        if entity_dict["topological_type"] == "XsVertexSet":
            # print(out_vtk.get_point_data('distance'))
            if xs_dist <= 0:
                entity_dict["vtk_obj"] = out_vtk
                self.geol_coll.add_entity_from_dict(entity_dict=entity_dict)
            else:
                thresh = vtk.vtkThresholdPoints()
                thresh.SetInputData(out_vtk)
                thresh.ThresholdByLower(xs_dist)
                thresh.SetInputArrayToProcess(
                    0, 0, 0, vtk.vtkDataObject().FIELD_ASSOCIATION_POINTS, "distance"
                )
                thresh.Update()

                thresholded = thresh.GetOutput()

                if thresholded.GetNumberOfPoints() > 0:
                    out_vtk.DeepCopy(thresholded)
                    entity_dict["vtk_obj"] = out_vtk
                    out_uid = self.geol_coll.add_entity_from_dict(
                        entity_dict=entity_dict
                    )
                else:
                    print(
                        f'No measure found for group {entity_dict["name"]}, try to extend the maximum distance'
                    )

        elif entity_dict["topological_type"] == "XsPolyLine":
            """Output, checking for multipart for polylines."""
            connectivity = vtk.vtkPolyDataConnectivityFilter()
            connectivity.SetInputData(out_vtk)
            connectivity.SetExtractionModeToAllRegions()
            connectivity.Update()
            n_regions = connectivity.GetNumberOfExtractedRegions()
            connectivity.SetExtractionModeToSpecifiedRegions()
            connectivity.Update()
            # entity_dict['vtk_obj'] = XsPolyLine()
            for region in range(n_regions):
                connectivity.InitializeSpecifiedRegionList()
                connectivity.AddSpecifiedRegion(region)
                connectivity.Update()
                """connectivity_clean, used to remove orphan points left behind by connectivity"""
                connectivity_clean = vtk.vtkCleanPolyData()
                connectivity_clean.SetInputConnection(connectivity.GetOutputPort())
                connectivity_clean.Update()
                """Check if polyline really exists then create entity"""
                if xs_dist <= 0:
                    out_vtk = connectivity_clean.GetOutput()
                else:
                    thresh = vtk.vtkThresholdPoints()
                    thresh.SetInputConnection(connectivity_clean.GetOutputPort())
                    thresh.ThresholdByLower(xs_dist)
                    thresh.SetInputArrayToProcess(
                        0,
                        0,
                        0,
                        vtk.vtkDataObject().FIELD_ASSOCIATION_POINTS,
                        "distance",
                    )
                    thresh.Update()

                    out_vtk = thresh.GetOutput()
                if out_vtk.GetNumberOfPoints() > 0:
                    # vtkAppendPolyData...
                    entity_dict["vtk_obj"] = XsPolyLine(
                        x_section_uid=xs_uid, parent=self
                    )
                    entity_dict["vtk_obj"].DeepCopy(connectivity_clean.GetOutput())
                    for data_key in entity_dict["vtk_obj"].point_data_keys:
                        if not data_key in entity_dict["properties_names"]:
                            entity_dict["vtk_obj"].remove_point_data(data_key)
                    out_uid = self.geol_coll.add_entity_from_dict(
                        entity_dict=entity_dict
                    )
                else:
                    print(" -- empty object -- ")

        ##################################################################################################################


class XSectionCollection(QAbstractTableModel):
    """
    Initialize XSectionCollection table.
    Column headers are taken from XSectionCollection.section_dict.keys()
    parent is supposed to be the project_window
    """

    """IN THE FUTURE we can use a trace PolyLine, with just a segment connecting base to end points?"""

    """section_dict is a dictionary of attributes used to define Xsections.
    Always use deepcopy(GeologicalCollection.geological_entity_dict) to copy
    this dictioary without altering the original."""
    section_dict = {
        "uid": "",
        "name": "undef",
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
        "vtk_frame": None,
    }  # None to avoid errors with deepcopy

    section_type_dict = {
        "uid": str,
        "name": str,
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

    """The edit dialog will be able to edit attributes of multiple entities (and selecting "None" will not change 
    them)______"""

    def __init__(self, parent=None, *args, **kwargs):
        super(XSectionCollection, self).__init__(*args, **kwargs)
        """Import reference to parent, otherwise it is difficult to reference them in SetData() that has a standard 
        list of inputs."""
        self.parent = parent

        """Initialize Pandas dataframe."""
        self.df = pd.DataFrame(columns=list(self.section_dict.keys()))

        """Here we use .columns.get_indexer to get indexes of the columns that we would like to be editable in the 
        QTableView"""
        """IN THE FUTURE think about editing top, bottom (just modify frame). To modify end-point and base-point we 
        need to ensure that they lie in the cross section, then just modify frame since W coords of objects are 
        always calculated on-the-fly."""
        self.editable_columns = self.df.columns.get_indexer(["name"])

    """Custom methods used to add or remove entities, query the dataframe, etc."""

    def add_entity_from_dict(self, entity_dict=None):
        """Add entity to collection from dictionary."""
        """Create a new uid if it is not included in the dictionary."""
        if not entity_dict["uid"]:
            entity_dict["uid"] = str(uuid.uuid4())
        """Append new row to dataframe. Note that the 'append()' method for Pandas dataframes DOES NOT
        work in place, hence a NEW dataframe is created every time and then substituted to the old one."""
        self.df = self.df.append(entity_dict, ignore_index=True)
        self.set_geometry(uid=entity_dict["uid"])
        """Reset data model"""
        self.modelReset.emit()
        self.parent.xsect_added_signal.emit(
            [entity_dict["uid"]]
        )  # a list of uids is emitted, even if the entity is just one
        return entity_dict["uid"]

    def remove_entity(self, uid=None):
        """Remove entity from collection."""
        """Remove row from dataframe and reset data model."""
        """NOTE THAT AT THE MOMENT REMOVING A SECTION DOES NOT REMOVE THE ASSOCIATED OBJECTS."""
        if not uid in self.get_uids():
            return
        self.df.drop(self.df[self.df["uid"] == uid].index, inplace=True)
        self.modelReset.emit()  # is this really necessary?
        self.parent.xsect_removed_signal.emit(
            [uid]
        )  # a list of uids is emitted, even if the entity is just one
        return uid

    def get_number_of_entities(self):
        """Get number of entities stored in Pandas dataframe."""
        return self.df.shape[0]

    def get_uids(self):
        """Get list of uids."""
        return self.df["uid"].to_list()

    def get_names(self):
        """Get list of names."""
        return self.df["name"].to_list()

    def get_legend(self):
        legend_dict = self.parent.others_legend_df.loc[
            self.parent.others_legend_df["other_type"] == "XSection"
        ].to_dict("records")
        return legend_dict[0]

    def get_uid_name(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df["uid"] == uid, "name"].values[0]

    def set_uid_name(self, uid=None, name=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df["uid"] == uid, "name"] = name

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

    def get_uid_vtk_frame(self, uid=None):
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
        """Gets X, Y coordinates from W coordinate (distance along the Xsection horizontal axis)"""
        azimuth = self.df.loc[self.df["uid"] == section_uid, "azimuth"].values[0]
        base_x = self.df.loc[self.df["uid"] == section_uid, "base_x"].values[0]
        base_y = self.df.loc[self.df["uid"] == section_uid, "base_y"].values[0]
        X = W * np_sin(azimuth * np_pi / 180) + base_x
        Y = W * np_cos(azimuth * np_pi / 180) + base_y
        return X, Y

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
        uid = self.df.iloc[index.row(), 0]
        if index.isValid():
            self.df.iloc[index.row(), index.column()] = value
            if self.data(index, Qt.DisplayRole) == value:
                """The following check is needed to avoid duplicate names that are not allowed for cross sections."""
                if self.df["name"].duplicated().sum() > 0:
                    self.df.iloc[index.row(), index.column()] = value + "_" + uid
                self.dataChanged.emit(index, index)
                self.parent.xsect_metadata_modified_signal.emit(
                    [uid]
                )  # a list of uids is emitted, even if the entity is just one
                return True
            return QVariant()
