from copy import deepcopy

import numpy as np
from PyQt5.QtWidgets import QAction
from geopandas import GeoDataFrame as geodataframe
from numpy import arange as np_arange
from numpy import array as np_array
from numpy import column_stack as np_column_stack
from numpy import flip as np_flip
from numpy import round as np_round
from numpy import shape as np_shape
from numpy import sqrt as np_sqrt
from numpy import zeros as np_zeros
from shapely import affinity
from shapely.affinity import scale
from shapely.geometry import LineString, Point, MultiLineString
from shapely.ops import snap as shp_snap
from shapely.ops import split

from pzero.collections.geological_collection import GeologicalCollection
from pzero.helpers.helper_dialogs import (
    multiple_input_dialog,
    input_one_value_dialog,
    message_dialog,
)
from pzero.helpers.helper_widgets import Editor, Tracer
from .entities_factory import PolyLine, XsPolyLine

# from .windows_factory import ViewMap, ViewXsection, NewViewMap, NewViewXsection
from .windows_factory import NewViewMap, NewViewXsection

"""Implementation of functions specific to this view (e.g. particular editing or visualization functions)"""


def draw_line(self):

    def end_digitize(event, input_dict):
        # Signal called to end the digitization of a trace. It returns a new polydata
        self.plotter.untrack_click_position()
        traced_pld = (
            tracer.GetContourRepresentation().GetContourRepresentationAsPolyData()
        )
        if traced_pld.GetNumberOfPoints() > 0:
            input_dict["vtk_obj"].ShallowCopy(traced_pld)
            self.parent.geol_coll.add_entity_from_dict(input_dict)
        tracer.EnabledOff()
        self.enable_actions()

    self.disable_actions()
    """Create deepcopy of the geological entity dictionary."""
    line_dict = deepcopy(self.parent.geol_coll.entity_dict)
    """One dictionary is set as input for a general widget of multiple-value-input"""
    line_dict_in = {
        "name": ["PolyLine name: ", "new_pline"],
        "geological_type": [
            "Geological type: ",
            self.parent.geol_coll.valid_types,
        ],
        "geological_feature": [
            "Geological feature: ",
            self.parent.geol_legend_df["geological_feature"].tolist(),
        ],
        "scenario": [
            "Scenario: ",
            list(set(self.parent.geol_legend_df["scenario"].tolist())),
        ],
    }
    line_dict_updt = multiple_input_dialog(
        title="Digitize new PolyLine", input_dict=line_dict_in
    )
    """Check if the output of the widget is empty or not. If the Cancel button was clicked, the tool quits"""
    if line_dict_updt is None:
        self.enable_actions()
        return
    """Getting the values that have been typed by the user through the widget"""
    for key in line_dict_updt:
        line_dict[key] = line_dict_updt[key]
    if isinstance(self, NewViewMap):
        line_dict["topological_type"] = "PolyLine"
        line_dict["x_section"] = None
        line_dict["vtk_obj"] = PolyLine()
    elif isinstance(self, NewViewXsection):
        line_dict["topological_type"] = "XsPolyLine"
        line_dict["x_section"] = self.this_x_section_uid
        line_dict["vtk_obj"] = XsPolyLine(
            x_section_uid=self.this_x_section_uid, parent=self.parent
        )
    tracer = Tracer(self)
    tracer.EnabledOn()
    self.plotter.track_click_position(
        side="right", callback=lambda event: end_digitize(event, line_dict)
    )


def edit_line(self):
    def end_edit(event, uid):
        self.plotter.untrack_click_position(side="right")
        traced_pld = (
            editor.GetContourRepresentation().GetContourRepresentationAsPolyData()
        )
        if isinstance(self, NewViewMap):
            vtk_obj = PolyLine()
        elif isinstance(self, NewViewXsection):
            vtk_obj = XsPolyLine(
                x_section_uid=self.this_x_section_uid, parent=self.parent
            )
        vtk_obj.ShallowCopy(traced_pld)
        self.parent.geol_coll.replace_vtk(uid=uid, vtk_object=vtk_obj)
        editor.EnabledOff()
        self.clear_selection()
        self.enable_actions()

    self.disable_actions()
    if not self.selected_uids:
        print(" -- No input data selected -- ")
        return
    sel_uid = self.selected_uids[0]
    actor = self.plotter.renderer.actors[sel_uid]
    data = actor.mapper.dataset
    # self.tracer.SetInputData(data)
    editor = Editor(self)
    editor.EnabledOn()
    editor.initialize(data, "edit")
    self.plotter.track_click_position(
        side="right", callback=lambda event: end_edit(event, sel_uid)
    )
    # self.plotter.track_mouse_position()
    # self.plotter.track_click_position(side='left', callback=left_click, viewport=True)


def sort_line_nodes(self):
    """Sort line nodes."""
    print("Sort line nodes according to cell order.")
    # """Terminate running event loops"""
    # self.stop_event_loops()
    """Check if a line is selected"""
    if not self.selected_uids:
        print(" -- No input data selected -- ")
        return
    # """Freeze QT interface"""
    # for action in self.findChildren(QAction):
    #     if isinstance(action.parentWidget(), NavigationToolbar) is False:
    #         action.setDisabled(True)
    """If more than one line is selected, keep the first."""
    for current_uid in self.selected_uids:
        """For some reason in the following the [:] is needed."""
        self.parent.geol_coll.get_uid_vtk_obj(
            current_uid
        ).sort_nodes()  # this could be probably done per-part__________________________
        """Deselect input line."""
        self.parent.geology_geom_modified_signal.emit(
            [current_uid]
        )  # emit uid as list to force redraw()
        # """Un-Freeze QT interface"""
        # for action in self.findChildren(QAction):
        #     action.setEnabled(True)
    self.clear_selection()


def move_line(self, vector):
    """Move the whole line by rigid-body translation.
    Here transformation to UV is not necessary since the translation vector is already in world space
    """
    print("Move Line. Move the whole line by rigid-body translation.")
    if vector.length == 0:
        print("Zero-length vector")
        self.enable_actions()
        return

    for current_uid in self.selected_uids:
        if (
            self.parent.geol_coll.get_uid_topological_type(current_uid) != "PolyLine"
        ) and (
            self.parent.geol_coll.get_uid_topological_type(current_uid) != "XsPolyLine"
        ):
            print(" -- Selected data is not a line -- ")
            return

        """Editing loop."""
        """For some reason in the following the [:] is needed."""
        x = (
            self.parent.geol_coll.get_uid_vtk_obj(current_uid).points_X[:]
            + vector.deltas[0]
        )
        y = (
            self.parent.geol_coll.get_uid_vtk_obj(current_uid).points_Y[:]
            + vector.deltas[1]
        )
        z = (
            self.parent.geol_coll.get_uid_vtk_obj(current_uid).points_Z[:]
            + vector.deltas[2]
        )

        points = np.stack((x, y, z), axis=1)
        self.parent.geol_coll.get_uid_vtk_obj(current_uid).points = points
        left_right(current_uid)
        """Deselect input line."""
        self.parent.geology_geom_modified_signal.emit(
            [current_uid]
        )  # emit uid as list to force redraw()
        """Un-Freeze QT interface"""
    self.clear_selection()

    self.enable_actions()


def rotate_line(self):
    """Rotate the whole line by rigid-body rotation using Shapely."""
    print(
        "Rotate Line. Rotate the whole line by rigid-body rotation. Please insert angle of anticlockwise rotation."
    )
    """Terminate running event loops"""
    """Check if a line is selected"""
    if not self.selected_uids:
        print(" -- No input data selected -- ")
        return
    """Freeze QT interface"""
    self.disable_actions()

    angle = input_one_value_dialog(
        parent=self,
        title="Rotate Line",
        label="Insert rotation angle in degrees, anticlockwise",
        default_value=10,
    )
    for current_uid in self.selected_uids:
        if (
            self.parent.geol_coll.get_uid_topological_type(current_uid) != "PolyLine"
        ) and (
            self.parent.geol_coll.get_uid_topological_type(current_uid) != "XsPolyLine"
        ):
            print(" -- Selected data is not a line -- ")
            return

        if angle is None:
            """Un-Freeze QT interface"""
            self.enable_actions()
            return
        if isinstance(self, NewViewMap):
            inU = self.parent.geol_coll.get_uid_vtk_obj(current_uid).points_X
            inV = self.parent.geol_coll.get_uid_vtk_obj(current_uid).points_Y
        elif isinstance(self, NewViewXsection):
            inU, inV = self.parent.geol_coll.get_uid_vtk_obj(current_uid).world2plane()
        """Stack coordinates in two-columns matrix"""
        """Run the Shapely function."""
        inUV = np_column_stack((inU, inV))
        shp_line_in = LineString(inUV)
        shp_line_out = affinity.rotate(
            shp_line_in, angle, origin="centroid", use_radians=False
        )  # Use Shapely to rotate
        outUV = np_array(shp_line_out)
        """Un-stack output coordinates and write them to the empty dictionary."""
        outU = outUV[:, 0]
        outV = outUV[:, 1]
        if isinstance(self, NewViewMap):
            outX = outU
            outY = outV
            outZ = self.parent.geol_coll.get_uid_vtk_obj(current_uid).points_Z

        elif isinstance(self, NewViewXsection):
            outX, outY, outZ = self.parent.xsect_coll.plane2world(
                self.this_x_section_uid, outU, outV
            )

        outXYZ = np_column_stack((outX, outY, outZ))
        self.parent.geol_coll.get_uid_vtk_obj(current_uid).points = outXYZ
        left_right(current_uid)
        self.parent.geology_geom_modified_signal.emit(
            [current_uid]
        )  # emit uid as list to force redraw()
    """Deselect input line."""
    self.clear_selection()
    """Un-Freeze QT interface"""
    self.enable_actions()


def extend_line(self):
    def end_edit(event, uid):
        self.plotter.untrack_click_position(side="right")
        self.plotter.untrack_click_position(side="left")
        self.plotter.clear_events_for_key("k")

        traced_pld = (
            extender.GetContourRepresentation().GetContourRepresentationAsPolyData()
        )
        if isinstance(self, NewViewMap):
            vtk_obj = PolyLine()
        elif isinstance(self, NewViewXsection):
            vtk_obj = XsPolyLine(
                x_section_uid=self.this_x_section_uid, parent=self.parent
            )
        vtk_obj.ShallowCopy(traced_pld)

        self.parent.geol_coll.replace_vtk(uid=uid, vtk_object=vtk_obj)
        extender.EnabledOff()
        self.clear_selection()
        self.enable_actions()

    """Extend selected line."""
    print("Extend Line. Press k to change end of line to extend.")
    """Terminate running event loops"""
    # self.stop_event_loops()
    """Check if a line is selected"""
    if not self.selected_uids:
        print(" -- No input data selected -- ")
        return
    if (
        self.parent.geol_coll.get_uid_topological_type(self.selected_uids[0])
        != "PolyLine"
    ) and (
        self.parent.geol_coll.get_uid_topological_type(self.selected_uids[0])
        != "XsPolyLine"
    ):
        print(" -- Selected data is not a line -- ")
        return
    """Freeze QT interface"""
    self.disable_actions()
    """If more than one line is selected, keep the first"""
    sel_uid = self.selected_uids[0]
    current_line = (
        self.actors_df.loc[self.actors_df["uid"] == sel_uid, "actor"]
        .values[0]
        .GetMapper()
        .GetInput()
    )

    extender = Editor(self)
    extender.EnabledOn()
    extender.initialize(current_line, "extend")

    self.plotter.track_click_position(
        side="right", callback=lambda event: end_edit(event, sel_uid)
    )


def split_line_line(self):
    """Split line (paper) with another line (scissors). First, select the paper-line then the scissors-line"""
    print(
        "Split line with line. Line to be split has been selected, please select an intersecting line."
    )
    """Terminate running event loops"""
    """Check if a line is selected"""
    if not self.selected_uids:
        print(" -- No input data selected -- ")
        return
    elif len(self.selected_uids) <= 1:
        print(" -- Not enough input data selected. Select at least 2 objects -- ")
        return
    """Freeze QT interface"""
    self.disable_actions()
    current_uid_scissors = self.selected_uids[-1]
    if (
        self.parent.geol_coll.get_uid_topological_type(current_uid_scissors)
        != "PolyLine"
    ) and (
        self.parent.geol_coll.get_uid_topological_type(current_uid_scissors)
        != "XsPolyLine"
    ):
        print(" -- Selected scissor is not a line -- ")
        return

    if isinstance(self, NewViewMap):
        inU = self.parent.geol_coll.get_uid_vtk_obj(current_uid_scissors).points_X
        inV = self.parent.geol_coll.get_uid_vtk_obj(current_uid_scissors).points_Y
    elif isinstance(self, NewViewXsection):
        inU, inV = self.parent.geol_coll.get_uid_vtk_obj(
            current_uid_scissors
        ).world2plane()

    inUV_scissors = np_column_stack((inU, inV))
    shp_line_in_scissors = LineString(inUV_scissors)

    for current_uid_paper in self.selected_uids[:-1]:
        if (
            self.parent.geol_coll.get_uid_topological_type(current_uid_paper)
            != "PolyLine"
        ) and (
            self.parent.geol_coll.get_uid_topological_type(current_uid_paper)
            != "XsPolyLine"
        ):
            print(" -- Selected paper is not a line -- ")
            return

        if isinstance(self, NewViewMap):
            inU = self.parent.geol_coll.get_uid_vtk_obj(current_uid_paper).points_X
            inV = self.parent.geol_coll.get_uid_vtk_obj(current_uid_paper).points_Y
        elif isinstance(self, NewViewXsection):
            inU, inV = self.parent.geol_coll.get_uid_vtk_obj(
                current_uid_paper
            ).world2plane()
        inUV_paper = np_column_stack((inU, inV))

        """Create deepcopies of the selected entities. Split U- and V-coordinates."""
        # inU_paper = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid_paper).points[:, 0])
        # inV_paper = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid_paper).points[:, 1])
        # inZ_paper = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid_paper).points[:, 2])
        # inU_scissors = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid_scissors).points[:, 0])
        # inV_scissors = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid_scissors).points[:, 1])
        # inZ_scissors = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid_scissors).points[:, 2])

        """Stack coordinates in two-columns matrix"""
        # inUV_paper = np_column_stack((inU_paper, inV_paper,inZ_paper))
        """Run the Shapely function."""
        shp_line_in_paper = LineString(inUV_paper)
        """Check if the two lineal geometries have shared path with dimension 1 (= they share a line-type object)"""
        if shp_line_in_paper.crosses(shp_line_in_scissors):
            """Run the split shapely function."""
            lines = split(
                shp_line_in_paper, shp_line_in_scissors
            )  # lines must include all line parts not affected by splitting and two parts for the split line__________
        else:  # handles the case when the LineString share a linear path and, for the moment, exists the tool
            """Un-Freeze QT interface"""
            self.clear_selection()
            self.enable_actions()
            return
        replace = 1  # replace = 1 for the first line to operate replace_vtk
        uids = [current_uid_scissors]
        for line in lines:
            """Create empty dictionary for the output lines."""
            new_line = deepcopy(self.parent.geol_coll.entity_dict)
            new_line["name"] = (
                self.parent.geol_coll.df.loc[
                    self.parent.geol_coll.df["uid"] == current_uid_paper, "name"
                ].values[0]
                + "_split"
            )
            new_line["topological_type"] = self.parent.geol_coll.df.loc[
                self.parent.geol_coll.df["uid"] == current_uid_paper, "topological_type"
            ].values[0]
            new_line["geological_type"] = self.parent.geol_coll.df.loc[
                self.parent.geol_coll.df["uid"] == current_uid_paper, "geological_type"
            ].values[0]
            new_line["geological_feature"] = self.parent.geol_coll.df.loc[
                self.parent.geol_coll.df["uid"] == current_uid_paper,
                "geological_feature",
            ].values[0]
            new_line["scenario"] = self.parent.geol_coll.df.loc[
                self.parent.geol_coll.df["uid"] == current_uid_paper, "scenario"
            ].values[0]
            outU = np_array(line)[:, 0]
            outV = np_array(line)[:, 1]
            if isinstance(self, NewViewMap):
                new_line["x_section"] = None
                new_line["vtk_obj"] = PolyLine()
                outX = outU
                outY = outV
                outZ = np_zeros(np_shape(outX))

            elif isinstance(self, NewViewXsection):
                new_line["x_section"] = self.this_x_section_uid
                new_line["vtk_obj"] = XsPolyLine(
                    self.this_x_section_uid, parent=self.parent
                )
                outX, outY, outZ = self.parent.xsect_coll.plane2world(
                    self.this_x_section_uid, outU, outV
                )
            """Create new vtk objects"""
            outXYZ = np_column_stack((outX, outY, outZ))
            new_line["vtk_obj"].points = outXYZ
            new_line["vtk_obj"].auto_cells()
            if new_line["vtk_obj"].points_number > 0:
                """Replace VTK object"""
                if replace == 1:
                    self.parent.geol_coll.replace_vtk(uid=current_uid_paper, vtk_object=new_line["vtk_obj"])
                    self.parent.geology_geom_modified_signal.emit(
                        [current_uid_paper]
                    )  # emit uid as list to force redraw()
                    replace = 0
                    uids.append(current_uid_paper)
                else:
                    """Create entity from the dictionary"""
                    uid = self.parent.geol_coll.add_entity_from_dict(new_line)
                    uids.append(uid)
                del new_line["vtk_obj"]
            else:
                print("Empty object")
        """Deselect input line and force redraw"""

        # self.parent.geology_geom_modified_signal.emit(uids)  # emit uid as list to force redraw()
    self.clear_selection()
    """Un-Freeze QT interface"""
    self.enable_actions()


def split_line_existing_point(self):
    # Here transformation to UV is not necessary since we select a point in world space
    def end_select(event, uid):
        point_pos = selector.active_pos
        self.plotter.untrack_click_position(side="right")
        """Create empty dictionary for the output line"""
        new_line_1 = deepcopy(self.parent.geol_coll.entity_dict)
        new_line_2 = deepcopy(self.parent.geol_coll.entity_dict)
        new_line_2["name"] = (
            self.parent.geol_coll.df.loc[
                self.parent.geol_coll.df["uid"] == uid, "name"
            ].values[0]
            + "_split"
        )
        new_line_2["topological_type"] = self.parent.geol_coll.df.loc[
            self.parent.geol_coll.df["uid"] == uid, "topological_type"
        ].values[0]
        new_line_2["geological_type"] = self.parent.geol_coll.df.loc[
            self.parent.geol_coll.df["uid"] == uid, "geological_type"
        ].values[0]
        new_line_2["geological_feature"] = self.parent.geol_coll.df.loc[
            self.parent.geol_coll.df["uid"] == uid, "geological_feature"
        ].values[0]
        new_line_2["scenario"] = self.parent.geol_coll.df.loc[
            self.parent.geol_coll.df["uid"] == uid, "scenario"
        ].values[0]
        if isinstance(self, NewViewMap):
            inU_line = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(uid).points[:, 0])
            inV_line = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(uid).points[:, 1])
        elif isinstance(self, NewViewXsection):
            inU_line = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(uid).points_W)
            inV_line = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(uid).points_Z)
            new_line_2["x_section"] = self.this_x_section_uid
        """Stack coordinates in two-columns matrix"""
        inUV_line = np_column_stack((inU_line, inV_line))
        """Run the Shapely function."""
        shp_line_in = LineString(
            deepcopy(self.parent.geol_coll.get_uid_vtk_obj(uid).points)
        )
        # x_vertex_unit = deepcopy(current_line_U_true[vertex_ind])
        # y_vertex_unit = deepcopy(current_line_V_true[vertex_ind])
        shp_point_in = Point(point_pos[0], point_pos[1], point_pos[2])
        """Splitting shapely function."""
        line1, line2 = split(shp_line_in, shp_point_in)
        line1_out = LineString(line1)
        line2_out = LineString(line2)
        """Convert shapely lines to UV objects"""
        outUV_1 = deepcopy(np_array(line1_out))
        outUV_2 = deepcopy(np_array(line2_out))
        """Un-stack output coordinates and write them to the empty dictionary."""
        outU_1 = outUV_1[:, 0]
        outV_1 = outUV_1[:, 1]
        outU_2 = outUV_2[:, 0]
        outV_2 = outUV_2[:, 1]
        if isinstance(self, NewViewMap):
            outX_1 = outU_1
            outY_1 = outV_1
            outZ_1 = np_zeros(np_shape(outX_1))
            outX_2 = outU_2
            outY_2 = outV_2
            outZ_2 = np_zeros(np_shape(outX_2))
        elif isinstance(self, NewViewXsection):
            outX_1, outY_1 = self.parent.xsect_coll.get_XY_from_W(
                section_uid=self.this_x_section_uid, W=outU_1
            )
            outZ_1 = outV_1
            outX_2, outY_2 = self.parent.xsect_coll.get_XY_from_W(
                section_uid=self.this_x_section_uid, W=outU_2
            )
            outZ_2 = outV_2
        new_points_1 = np_column_stack((outX_1, outY_1, outZ_1))
        new_points_2 = np_column_stack((outX_2, outY_2, outZ_2))
        if isinstance(self, NewViewMap):
            new_line_1["vtk_obj"] = PolyLine()
            new_line_2["vtk_obj"] = PolyLine()
        elif isinstance(self, NewViewXsection):
            new_line_1["vtk_obj"] = XsPolyLine(
                self.this_x_section_uid, parent=self.parent
            )
            new_line_2["vtk_obj"] = XsPolyLine(
                self.this_x_section_uid, parent=self.parent
            )
        new_line_1["vtk_obj"].points = deepcopy(np_array(line1_out))
        new_line_1["vtk_obj"].auto_cells()
        new_line_2["vtk_obj"].points = deepcopy(np_array(line2_out))
        new_line_2[
            "vtk_obj"
        ].auto_cells()  # lines must include all line parts not affected by splitting and two parts for the split line__________
        """Replace VTK object"""
        if new_line_1["vtk_obj"].points_number > 0:
            self.parent.geol_coll.replace_vtk(uid=uid, vtk_object=new_line_1["vtk_obj"])
            del new_line_1
        else:
            print("Empty object")
        """Create entity from the dictionary"""
        if new_line_2["vtk_obj"].points_number > 0:
            self.parent.geol_coll.add_entity_from_dict(new_line_2)
            del new_line_2
        else:
            print("Empty object")
        """Deselect input line."""
        self.clear_selection()
        selector.EnabledOff()
        """Un-Freeze QT interface"""
        self.enable_actions()

    """Split line at selected existing point (vertex)"""
    print(
        "Split line at existing point. Line to be split has been selected, "
        "please select an existing point for splitting."
    )
    """Check if a line is selected"""
    if not self.selected_uids:
        print(" -- No input data selected -- ")
        return
    if (
        self.parent.geol_coll.get_uid_topological_type(self.selected_uids[0])
        != "PolyLine"
    ) and (
        self.parent.geol_coll.get_uid_topological_type(self.selected_uids[0])
        != "XsPolyLine"
    ):
        print(" -- Selected data is not a line -- ")
        return
    """Freeze QT interface"""
    self.disable_actions
    """If more than one line is selected, keep the first"""
    sel_uid = self.selected_uids[0]
    current_line = self.actors_df.loc[self.actors_df["uid"] == sel_uid, "actor"].values[
        0
    ]
    line = current_line.mapper.dataset
    selector = Editor(self)
    selector.EnabledOn()
    selector.initialize(line, "select")
    self.plotter.track_click_position(
        side="right", callback=lambda event: end_select(event, sel_uid)
    )


def split_line_vector(self, vector):
    ...


# check merge, snap, and see if a bridge nodes method is needed____________________


def merge_lines(self):
    """Merge two (contiguous or non-contiguous) lines."""  # lines must include all line parts not affected by splitting and two parts for the split line__________
    print(
        "Merge two lines. First line has been selected, please select second line for merging."
    )
    """Terminate running event loops"""
    """Check if a line is selected"""
    if not self.selected_uids:
        print(" -- No input data selected -- ")
        return
    elif len(self.selected_uids) <= 1:
        print(" -- Not enough input data selected. Select at least 2 objects -- ")
        return
    if (
        self.parent.geol_coll.get_uid_topological_type(self.selected_uids[0])
        != "PolyLine"
    ) and (
        self.parent.geol_coll.get_uid_topological_type(self.selected_uids[0])
        != "XsPolyLine"
    ):
        print(" -- Selected data is not a line -- ")
        return
    """Freeze QT interface"""
    self.disable_actions()

    current_uid_one = self.selected_uids[0]
    current_uid_two = self.selected_uids[1]
    """Create empty dictionary for the output line."""
    new_line = deepcopy(self.parent.geol_coll.entity_dict)
    if isinstance(self, NewViewMap):
        # if isinstance(self, (ViewMap, NewViewMap)):
        new_line["vtk_obj"] = PolyLine()
        new_line["x_section"] = None
        inU_one = deepcopy(
            self.parent.geol_coll.get_uid_vtk_obj(current_uid_one).points[:, 0]
        )
        inV_one = deepcopy(
            self.parent.geol_coll.get_uid_vtk_obj(current_uid_one).points[:, 1]
        )
        inU_two = deepcopy(
            self.parent.geol_coll.get_uid_vtk_obj(current_uid_two).points[:, 0]
        )
        inV_two = deepcopy(
            self.parent.geol_coll.get_uid_vtk_obj(current_uid_two).points[:, 1]
        )
    # elif isinstance(self, (ViewXsection, NewViewXsection)):
    elif isinstance(self, NewViewXsection):
        new_line["vtk_obj"] = XsPolyLine(self.this_x_section_uid, parent=self.parent)
        new_line["x_section"] = self.this_x_section_uid
        inU_one, inV_one = self.parent.geol_coll.get_uid_vtk_obj(
            current_uid_one
        ).world2plane()
        inU_two, inV_two = self.parent.geol_coll.get_uid_vtk_obj(
            current_uid_two
        ).world2plane()
    """Calculate distances"""
    dist_start_start = np_sqrt(
        (inU_one[0] - inU_two[0]) ** 2 + (inV_one[0] - inV_two[0]) ** 2
    )
    dist_end_end = np_sqrt(
        (inU_one[-1] - inU_two[-1]) ** 2 + (inV_one[-1] - inV_two[-1]) ** 2
    )
    dist_start_end = np_sqrt(
        (inU_one[0] - inU_two[-1]) ** 2 + (inV_one[0] - inV_two[-1]) ** 2
    )
    dist_end_start = np_sqrt(
        (inU_one[-1] - inU_two[0]) ** 2 + (inV_one[-1] - inV_two[0]) ** 2
    )
    if (
        min(dist_start_start, dist_end_end, dist_start_end, dist_end_start)
        == dist_start_start
    ):  # flip line 1
        inU_one = np_flip(inU_one, 0)
        inV_one = np_flip(inV_one, 0)
    elif (
        min(dist_start_start, dist_end_end, dist_start_end, dist_end_start)
        == dist_end_end
    ):  # flip line 2
        inU_two = np_flip(inU_two, 0)
        inV_two = np_flip(inV_two, 0)
    elif (
        min(dist_start_start, dist_end_end, dist_start_end, dist_end_start)
        == dist_start_end
    ):  # flip both line 1 and line 2
        inU_one = np_flip(inU_one, 0)
        inV_one = np_flip(inV_one, 0)
        inU_two = np_flip(inU_two, 0)
        inV_two = np_flip(inV_two, 0)
    inUV_one = np_column_stack((inU_one, inV_one))
    inUV_two = np_column_stack((inU_two, inV_two))
    """Run the Shapely function."""
    shp_line_in_one = LineString(inUV_one)
    shp_line_in_two = LineString(inUV_two)
    """Remove the path that lines may share"""
    shp_line_out_diff = shp_line_in_one.difference(shp_line_in_two)
    """Extract coordinates of the two lines to create a new LineString"""
    if shp_line_out_diff.is_simple and shp_line_in_two.is_simple:
        inlines = MultiLineString([shp_line_out_diff, shp_line_in_two])
        outcoords = [list(i.coords) for i in inlines]
        shp_line_out = LineString([i for sublist in outcoords for i in sublist])
        outUV = deepcopy(np_array(shp_line_out))
    else:
        print("Polyline is not simple, it self-intersects")
        """Un-Freeze QT interface"""
        self.disable_actions()
        return
    """Un-stack output coordinates and write them to the empty dictionary."""
    outU = outUV[:, 0]
    outV = outUV[:, 1]
    if isinstance(self, NewViewMap):
        # if isinstance(self, (ViewMap, NewViewMap)):
        outX = outU
        outY = outV
        outZ = np_zeros(np_shape(outX))
    # elif isinstance(self, (ViewXsection, NewViewXsection)):
    elif isinstance(self, NewViewXsection):
        outX, outY, outZ = self.parent.xsect_coll.plane2world(
            self.this_x_section_uid, outU, outV
        )

    outXYZ = np_column_stack((outX, outY, outZ))

    new_line["vtk_obj"].points = outXYZ
    new_line["vtk_obj"].auto_cells()
    """Replace VTK object"""
    if new_line["vtk_obj"].points_number > 0:
        self.parent.geol_coll.replace_vtk(uid=current_uid_one, vtk_object=new_line["vtk_obj"])
        del new_line
    else:
        print("Empty object")
    """Deselect input line."""
    self.clear_selection()
    self.parent.update_actors = False
    self.parent.geol_coll.remove_entity(current_uid_two)
    # self.parent.geology_geom_modified_signal.emit([current_uid_one])  # emit uid as list to force redraw()
    """Un-Freeze QT interface"""
    self.enable_actions()


def snap_line(self):
    """Snaps vertices of the selected line (the snapping-line) to the nearest vertex of the chosen line (goal-line),
    depending on the Tolerance parameter."""
    print(
        "Snap line to line. Line to be snapped has been selected, please select second line."
    )
    """Terminate running event loops"""
    """Check if a line is selected"""
    if not self.selected_uids:
        print(" -- No input data selected -- ")
        return
    elif len(self.selected_uids) <= 1:
        print(" -- Not enough input data selected. Select at least 2 objects -- ")
        return
    """Freeze QT interface"""
    self.disable_actions()
    current_uid_goal = self.selected_uids[-1]
    if (
        self.parent.geol_coll.get_uid_topological_type(current_uid_goal) != "PolyLine"
    ) and (
        self.parent.geol_coll.get_uid_topological_type(current_uid_goal) != "XsPolyLine"
    ):
        print(" -- Selected goal is not a line -- ")
        return
    tolerance = input_one_value_dialog(
        parent=self,
        title="Snap tolerance",
        label="Insert snap tolerance",
        default_value=10,
    )

    for current_uid_snap in self.selected_uids[:-1]:
        print(current_uid_snap)
        if (
            self.parent.geol_coll.get_uid_topological_type(current_uid_snap)
            != "PolyLine"
        ) and (
            self.parent.geol_coll.get_uid_topological_type(current_uid_snap)
            != "XsPolyLine"
        ):
            print(" -- Selected snap is not a line -- ")
            return

        """Create empty dictionary for the output line."""
        new_line_snap = deepcopy(self.parent.geol_coll.entity_dict)
        new_line_goal = deepcopy(self.parent.geol_coll.entity_dict)

        """Editing loop. Get coordinates of the line to be modified (snap-line)."""
        if isinstance(self, NewViewMap):
            new_line_snap["vtk_obj"] = PolyLine()
            new_line_snap["x_section"] = None
            new_line_goal["vtk_obj"] = PolyLine()
            new_line_goal["x_section"] = None
            inU_snap = deepcopy(
                self.parent.geol_coll.get_uid_vtk_obj(current_uid_snap).points_X
            )
            inV_snap = deepcopy(
                self.parent.geol_coll.get_uid_vtk_obj(current_uid_snap).points_Y
            )
            inU_goal = deepcopy(
                self.parent.geol_coll.get_uid_vtk_obj(current_uid_goal).points_X
            )
            inV_goal = deepcopy(
                self.parent.geol_coll.get_uid_vtk_obj(current_uid_goal).points_Y
            )
        elif isinstance(self, NewViewXsection):
            new_line_snap["vtk_obj"] = XsPolyLine(
                self.this_x_section_uid, parent=self.parent
            )
            new_line_snap["x_section"] = self.this_x_section_uid
            new_line_goal["vtk_obj"] = XsPolyLine(
                self.this_x_section_uid, parent=self.parent
            )
            new_line_goal["x_section"] = self.this_x_section_uid
            inU_snap, inV_snap = self.parent.geol_coll.get_uid_vtk_obj(
                current_uid_snap
            ).world2plane()
            inU_goal, inV_goal = self.parent.geol_coll.get_uid_vtk_obj(
                current_uid_goal
            ).world2plane()
        """Stack coordinates in two-columns matrix"""
        inUV_snap = np_column_stack((inU_snap, inV_snap))
        inUV_goal = np_column_stack((inU_goal, inV_goal))
        """Run the Shapely function."""
        shp_line_in_snap = LineString(inUV_snap)
        shp_line_in_goal = LineString(inUV_goal)

        shp_line_in_goal, extended = int_node(shp_line_in_goal, shp_line_in_snap)
        # plt.plot(np_array(shp_line_in_goal)[:, 0], np_array(shp_line_in_goal)[:, 1], 'r-o')
        # plt.plot(np_array(extended)[:, 0], np_array(extended)[:, 1], 'b-o')
        # plt.show()

        """In the snapping tool, the last input value is called Tolerance. Can be modified, do some checks.
        Little tolerance risks of not snapping distant lines, while too big tolerance snaps to the wrong vertex and
        not to the nearest one"""
        if shp_line_in_snap.is_simple and shp_line_in_goal.is_simple:
            shp_line_out_snap = shp_snap(shp_line_in_snap, shp_line_in_goal, tolerance)
        else:
            print("Polyline is not simple, it self-intersects")
            """Un-Freeze QT interface"""
            self.enable_actions()
            return
        shp_line_out_diff = shp_line_out_snap.difference(
            shp_line_in_goal
        )  # eliminate the shared path that Snap may create
        outUV_snap = deepcopy(np_array(shp_line_out_diff))
        outUV_goal = deepcopy(np_array(shp_line_in_goal))
        """Un-stack output coordinates and write them to the empty dictionary."""
        if outUV_snap.ndim < 2:
            print("Invalid shape")
            continue
        outU_snap = outUV_snap[:, 0]
        outV_snap = outUV_snap[:, 1]
        outU_goal = outUV_goal[:, 0]
        outV_goal = outUV_goal[:, 1]
        """Convert local coordinates to XYZ ones."""
        if isinstance(self, NewViewMap):
            outX_snap = outU_snap
            outY_snap = outV_snap
            outZ_snap = np_zeros(np_shape(outX_snap))

            outX_goal = outU_goal
            outY_goal = outV_goal
            outZ_goal = np_zeros(np_shape(outX_goal))
        elif isinstance(self, NewViewXsection):
            outX_snap, outY_snap, outZ_snap = self.parent.xsect_coll.plane2world(
                self.this_x_section_uid, outU_snap, outV_snap
            )
            outX_goal, outY_goal, outZ_goal = self.parent.xsect_coll.plane2world(
                self.this_x_section_uid, outU_goal, outV_goal
            )

            # outZ = outV
        """Create new vtk objects"""
        new_points_snap = np_column_stack((outX_snap, outY_snap, outZ_snap))
        new_points_goal = np_column_stack((outX_goal, outY_goal, outZ_goal))

        new_line_snap["vtk_obj"].points = new_points_snap
        new_line_snap["vtk_obj"].auto_cells()
        new_line_goal["vtk_obj"].points = new_points_goal
        new_line_goal["vtk_obj"].auto_cells()
        """Replace VTK object"""
        if new_line_snap["vtk_obj"].points_number > 0:
            self.parent.geol_coll.replace_vtk(uid=current_uid_snap,vtk_object=new_line_snap["vtk_obj"])
            self.parent.geol_coll.replace_vtk(uid=current_uid_goal,vtk_object=new_line_goal["vtk_obj"])
            del new_line_snap
            del new_line_goal
        else:
            print("Empty object")
        """Un-Freeze QT interface"""
    self.clear_selection()
    self.enable_actions()


def resample_line_distance(
    self,
):  # this must be done per-part_______________________________________________________
    """Resample selected line with constant spacing. Distance of spacing is required"""
    print("Resample line. Define constant spacing for resampling.")
    """Terminate running event loops"""
    """Check if a line is selected"""
    if not self.selected_uids:
        print(" -- No input data selected -- ")
        return
    """Freeze QT interface"""
    self.disable_actions()
    """Ask for distance for evenly spacing resampling"""
    distance_delta = input_one_value_dialog(
        parent=self,
        title="Spacing distance for Line Resampling",
        label="Insert spacing distance",
        default_value="Distance",
    )
    for current_uid in self.selected_uids:
        if (
            self.parent.geol_coll.get_uid_topological_type(current_uid) != "PolyLine"
        ) and (
            self.parent.geol_coll.get_uid_topological_type(current_uid) != "XsPolyLine"
        ):
            print(" -- Selected data is not a line -- ")
            return

        if distance_delta is None or isinstance(distance_delta, str):
            """Un-Freeze QT interface"""
            for action in self.findChildren(QAction):
                action.setEnabled(True)
            return
        else:
            distance_delta = int(distance_delta)
        if distance_delta <= 0:
            distance_delta = 20
        """Create empty dictionary for the output line"""
        new_line = deepcopy(self.parent.geol_coll.entity_dict)
        if isinstance(self, NewViewMap):
            new_line["topological_type"] = "PolyLine"
            new_line["x_section"] = None
            inU = deepcopy(
                self.parent.geol_coll.get_uid_vtk_obj(current_uid).points[:, 0]
            )
            inV = deepcopy(
                self.parent.geol_coll.get_uid_vtk_obj(current_uid).points[:, 1]
            )
        elif isinstance(self, NewViewXsection):
            new_line["topological_type"] = "XsPolyLine"
            new_line["x_section"] = self.this_x_section_uid
            inU, inV = self.parent.geol_coll.get_uid_vtk_obj(current_uid).world2plane()
        """Stack coordinates in two-columns matrix"""
        inUV = np_column_stack((inU, inV))
        """Run the Shapely function."""
        shp_line_in = LineString(inUV)
        if distance_delta >= shp_line_in.length:
            while distance_delta >= shp_line_in.length:
                distance_delta = distance_delta / 2
        distances = np_arange(0, shp_line_in.length, distance_delta)
        points = [shp_line_in.interpolate(distance) for distance in distances] + [
            shp_line_in.boundary[1]
        ]
        shp_line_out = LineString(points)
        outUV = deepcopy(np_array(shp_line_out))
        """Un-stack output coordinates and write them to the empty dictionary."""
        outU = outUV[:, 0]
        outV = outUV[:, 1]
        if isinstance(self, NewViewMap):
            # if isinstance(self, (ViewMap, NewViewMap)):
            outX = outU
            outY = outV
            outZ = np_zeros(np_shape(outX))
            new_line["vtk_obj"] = PolyLine()
        # elif isinstance(self, (ViewXsection, NewViewXsection)):
        elif isinstance(self, NewViewXsection):
            outX, outY, outZ = self.parent.xsect_coll.plane2world(
                self.this_x_section_uid, outU, outV
            )
            new_line["vtk_obj"] = XsPolyLine(
                self.this_x_section_uid, parent=self.parent
            )
        outXYZ = np_column_stack((outX, outY, outZ))
        new_line["vtk_obj"].points = outXYZ
        new_line["vtk_obj"].auto_cells()
        """Replace VTK object"""
        if new_line["vtk_obj"].points_number > 0:
            self.parent.geol_coll.replace_vtk(uid=current_uid, vtk_object=new_line["vtk_obj"])
            del new_line
        else:
            print("Empty object")
        """Deselect input line."""
        self.parent.geology_geom_modified_signal.emit(
            [current_uid]
        )  # emit uid as list to force redraw()
        """Un-Freeze QT interface"""
    self.clear_selection()
    self.enable_actions()


def resample_line_number_points(
    self,
):  # this must be done per-part___________________________________________________
    """Resample selected line with constant spacing. Number of points to divide the line in is required"""
    print("Resample line. Define number of vertices to create on the line.")
    """Terminate running event loops"""
    """Check if a line is selected"""
    if not self.selected_uids:
        print(" -- No input data selected -- ")
        return
    """Freeze QT interface"""
    self.disable_actions()
    """Ask for the number of points for evenly spacing resampling"""
    number_of_points = input_one_value_dialog(
        parent=self,
        title="Number of points for Line Resampling",
        label="Insert number of points",
        default_value="Number",
    )
    for current_uid in self.selected_uids:
        if (
            self.parent.geol_coll.get_uid_topological_type(current_uid) != "PolyLine"
        ) and (
            self.parent.geol_coll.get_uid_topological_type(current_uid) != "XsPolyLine"
        ):
            print(" -- Selected data is not a line -- ")
            return

        if number_of_points is None or isinstance(number_of_points, str):
            """Un-Freeze QT interface"""
            self.enable_actions()
            return
        else:
            number_of_points = int(number_of_points)
        if number_of_points <= 1:
            number_of_points = 20
        """Editing loop"""
        """Create empty dictionary for the output line"""
        new_line = deepcopy(self.parent.geol_coll.entity_dict)
        """Define topological_type and x_section. Get coordinates of input line"""
        if isinstance(self, NewViewMap):
            # if isinstance(self, (ViewMap, NewViewMap)):
            new_line["topological_type"] = "PolyLine"
            new_line["x_section"] = None
            inU = deepcopy(
                self.parent.geol_coll.get_uid_vtk_obj(current_uid).points[:, 0]
            )
            inV = deepcopy(
                self.parent.geol_coll.get_uid_vtk_obj(current_uid).points[:, 1]
            )
        # elif isinstance(self, (ViewXsection, NewViewXsection)):
        elif isinstance(self, NewViewXsection):
            new_line["topological_type"] = "XsPolyLine"
            new_line["x_section"] = self.this_x_section_uid

            inU, inV = self.parent.geol_coll.get_uid_vtk_obj(current_uid).world2plane()
        """Stack coordinates in two-columns matrix"""
        inUV = np_column_stack((inU, inV))
        """Run the Shapely function."""
        shp_line_in = LineString(inUV)
        distances = (
            shp_line_in.length * i / (number_of_points - 1)
            for i in range(number_of_points)
        )
        points = [shp_line_in.interpolate(distance) for distance in distances]
        shp_line_out = LineString(points)
        outUV = deepcopy(np_array(shp_line_out))
        """Un-stack output coordinates and write them to the empty dictionary."""
        outU = outUV[:, 0]
        outV = outUV[:, 1]
        if isinstance(self, NewViewMap):
            # if isinstance(self, (ViewMap, NewViewMap)):
            outX = outU
            outY = outV
            outZ = np_zeros(np_shape(outX))
            new_line["vtk_obj"] = PolyLine()
        # elif isinstance(self, (ViewXsection, NewViewXsection)):
        elif isinstance(self, NewViewXsection):
            outX, outY, outZ = self.parent.xsect_coll.plane2world(
                self.this_x_section_uid, outU, outV
            )
            new_line["vtk_obj"] = XsPolyLine(
                self.this_x_section_uid, parent=self.parent
            )
        outXYZ = np_column_stack((outX, outY, outZ))
        new_line["vtk_obj"].points = outXYZ
        new_line["vtk_obj"].auto_cells()
        """Replace VTK object"""
        if new_line["vtk_obj"].points_number > 0:
            self.parent.geol_coll.replace_vtk(uid=current_uid, vtk_object=new_line["vtk_obj"])
            del new_line
        else:
            print("Empty object")

        self.parent.geology_geom_modified_signal.emit(
            [current_uid]
        )  # emit uid as list to force redraw()
    """Deselect input line."""
    self.clear_selection()
    """Un-Freeze QT interface"""
    self.enable_actions()


def simplify_line(
    self,
):  # this must be done per-part_______________________________________________________
    """Return a simplified representation of the line. Permits the user to choose a value for the Tolerance parameter."""
    print(
        "Simplify line. Define tolerance value: "
        "small values result in more vertices and great similarity with the input line."
    )
    """Terminate running event loops"""

    """Check if a line is selected"""
    if not self.selected_uids:
        print(" -- No input data selected -- ")
        return
    """Freeze QT interface"""
    self.disable_actions()
    """Ask for the tolerance parameter"""
    tolerance_p = input_one_value_dialog(
        parent=self,
        title="Simplify - Tolerance",
        label="Insert tolerance parameter",
        default_value="0.1",
    )
    for current_uid in self.selected_uids:
        if (
            self.parent.geol_coll.get_uid_topological_type(current_uid) != "PolyLine"
        ) and (
            self.parent.geol_coll.get_uid_topological_type(current_uid) != "XsPolyLine"
        ):
            print(" -- Selected data is not a line -- ")
            return

        if tolerance_p is None:
            """Un-Freeze QT interface"""
            self.enable_actions()
            return
        if tolerance_p <= 0:
            tolerance_p = 0.1
        """Editing loop. Create empty dictionary for the output line"""
        new_line = deepcopy(self.parent.geol_coll.entity_dict)
        """Get coordinates of input line."""
        if isinstance(self, NewViewMap):
            # if isinstance(self, (ViewMap, NewViewMap)):
            new_line["topological_type"] = "PolyLine"
            new_line["x_section"] = None
            inU = deepcopy(
                self.parent.geol_coll.get_uid_vtk_obj(current_uid).points[:, 0]
            )
            inV = deepcopy(
                self.parent.geol_coll.get_uid_vtk_obj(current_uid).points[:, 1]
            )
        # elif isinstance(self, (ViewXsection, NewViewXsection)):
        elif isinstance(self, NewViewXsection):
            new_line["topological_type"] = "XsPolyLine"
            new_line["x_section"] = self.this_x_section_uid
            inU, inV = deepcopy(
                self.parent.geol_coll.get_uid_vtk_obj(current_uid).world2plane()
            )
        """Stack coordinates in two-columns matrix"""
        inUV = np_column_stack((inU, inV))
        """Run the Shapely function."""
        shp_line_in = LineString(inUV)
        shp_line_out = shp_line_in.simplify(tolerance_p, preserve_topology=False)
        outUV = deepcopy(np_array(shp_line_out))
        """Un-stack output coordinates and write them to the empty dictionary."""
        outU = outUV[:, 0]
        outV = outUV[:, 1]
        if isinstance(self, NewViewMap):
            # if isinstance(self, (ViewMap, NewViewMap)):
            outX = outU
            outY = outV
            outZ = np_zeros(np_shape(outX))
            new_line["vtk_obj"] = PolyLine()
        # elif isinstance(self, (ViewXsection, NewViewXsection)):
        elif isinstance(self, NewViewXsection):
            outX, outY, outZ = self.parent.xsect_coll.plane2world(
                self.this_x_section_uid, outU, outV
            )
            new_line["vtk_obj"] = XsPolyLine(
                self.this_x_section_uid, parent=self.parent
            )
        """Create new vtk"""
        new_points = np_column_stack((outX, outY, outZ))
        new_line["vtk_obj"].points = new_points
        new_line["vtk_obj"].auto_cells()
        """Replace VTK object"""
        if new_line["vtk_obj"].points_number > 0:
            self.parent.geol_coll.replace_vtk(uid=current_uid, vtk_object=new_line["vtk_obj"])
            del new_line
        else:
            print("Empty object")

        self.parent.geology_geom_modified_signal.emit(
            [current_uid]
        )  # emit uid as list to force redraw()
    """Deselect input line."""
    self.clear_selection()
    """Un-Freeze QT interface"""
    self.enable_actions()


def copy_parallel(
    self,
):  # this must be done per-part_______________________________________________________
    """Parallel folding. Create a line copied and translated from a template line using Shapely.
    Since lines are oriented left-to-right and bottom-to-top, and here we copy a line to the left,
    a positive distance creates a line shifted upwards and to the left."""
    print("Copy Parallel. Create a line copied and translated.")
    """Terminate running event loops"""

    """Check if a line is selected"""
    if not self.selected_uids:
        print(" -- No input data selected -- ")
        return
    if (
        self.parent.geol_coll.get_uid_topological_type(self.selected_uids[0])
        != "PolyLine"
    ) and (
        self.parent.geol_coll.get_uid_topological_type(self.selected_uids[0])
        != "XsPolyLine"
    ):
        print(" -- Selected data is not a line -- ")
        return
    """Freeze QT interface"""
    self.disable_actions()
    """If more than one line is selected, keep the first."""
    input_uid = self.selected_uids[0]
    """IN THE FUTURE add a test to check that the selected feature is a geological feature"""
    """Editing loop."""
    distance = input_one_value_dialog(
        parent=self,
        title="Line from template",
        label="Insert distance",
        default_value=100,
    )
    if distance is None:
        """Un-Freeze QT interface"""
        self.enable_actions()
        return

    in_line_name = self.parent.geol_coll.df.loc[
        self.parent.geol_coll.df["uid"] == input_uid, "name"
    ].values[0]
    out_line_name = in_line_name + "_para_" + "%d" % distance

    """Create empty dictionary for the output line and set name and geological_type.
    IN THE FUTURE see if other metadata should be automatically set."""
    line_dict = deepcopy(self.parent.geol_coll.entity_dict)
    line_dict["name"] = out_line_name
    line_dict["geological_type"] = self.parent.geol_coll.df.loc[
        self.parent.geol_coll.df["uid"] == input_uid, "geological_type"
    ].values[0]
    line_dict["geological_feature"] = self.parent.geol_coll.get_uid_geological_feature(
        self.selected_uids[0]
    )
    line_dict["scenario"] = self.parent.geol_coll.get_uid_scenario(
        self.selected_uids[0]
    )
    if isinstance(self, NewViewMap):
        # if isinstance(self, (ViewMap, NewViewMap)):
        inU = self.parent.geol_coll.get_uid_vtk_obj(input_uid).points_X
        inV = self.parent.geol_coll.get_uid_vtk_obj(input_uid).points_Y

        line_dict["vtk_obj"] = PolyLine()
        line_dict["topological_type"] = "PolyLine"
    # elif isinstance(self, (ViewXsection, NewViewXsection)):
    elif isinstance(self, NewViewXsection):
        inU, inV = self.parent.geol_coll.get_uid_vtk_obj(input_uid).world2plane()
        line_dict["vtk_obj"] = XsPolyLine(self.this_x_section_uid, parent=self.parent)
        line_dict["topological_type"] = "XsPolyLine"
        line_dict["x_section"] = self.this_x_section_uid

    inUV = np_column_stack((inU, inV))
    """Deselect input line."""
    self.clear_selection()
    # self.parent.geology_geom_modified_signal.emit([input_uid])  # emit uid as list to force redraw()
    """Run the Shapely function."""
    shp_line_in = LineString(inUV)
    # print(shp_line_in)
    # print("shp_line_in.parallel_offset")
    if shp_line_in.is_simple:
        shp_line_out = shp_line_in.parallel_offset(
            distance, "left", resolution=16, join_style=1
        )  # parallel folds are obtained with join_style=1

        outUV = np_array(shp_line_out)
        """Un-stack output coordinates and write them to the empty dictionary."""
        outU = outUV[:, 0]
        outV = outUV[:, 1]
    else:
        print("Polyline is not simple, it self-intersects")
        """Un-Freeze QT interface"""
        for action in self.findChildren(QAction):
            action.setEnabled(True)
        return
    if isinstance(self, NewViewMap):
        # if isinstance(self, (ViewMap, NewViewMap)):
        outX = outU
        outY = outV
        outZ = np_zeros(np_shape(outX))
    # elif isinstance(self, (ViewXsection, NewViewXsection)):
    elif isinstance(self, NewViewXsection):
        outX, outY, outZ = self.parent.xsect_coll.plane2world(
            self.this_x_section_uid, outU, outV
        )
    """Stack coordinates in two-columns matrix and write to vtk object."""
    print("outXYZ = np_column_stack((outX, outY, outZ))")
    outXYZ = np_column_stack((outX, outY, outZ))

    line_dict["vtk_obj"].points = outXYZ
    line_dict["vtk_obj"].auto_cells()
    """Create entity from the dictionary and run left_right."""
    if line_dict["vtk_obj"].points_number > 0:
        output_uid = self.parent.geol_coll.add_entity_from_dict(line_dict)
        left_right(output_uid)
    else:
        print("Empty object")
    """Un-Freeze QT interface"""
    self.enable_actions()


def copy_kink(
    self,
):  # this must be done per-part_______________________________________________________
    """Kink folding. Create a line copied and translated from a template line using Shapely.
    Since lines are oriented left-to-right and bottom-to-top, and here we copy a line to the left,
    a positive distance creates a line shifted upwards and to the left."""
    print("Copy Kink. Create a line copied and translated.")
    """Terminate running event loops"""
    """Check if a line is selected"""
    if not self.selected_uids:
        print(" -- No input data selected -- ")
        return
    if (
        self.parent.geol_coll.get_uid_topological_type(self.selected_uids[0])
        != "PolyLine"
    ) and (
        self.parent.geol_coll.get_uid_topological_type(self.selected_uids[0])
        != "XsPolyLine"
    ):
        print(" -- Selected data is not a line -- ")
        return
    """Freeze QT interface"""
    self.disable_actions()
    """If more than one line is selected, keep the first."""
    input_uid = self.selected_uids[0]
    """IN THE FUTURE add a test to check that the selected feature is a geological feature"""
    """Editing loop."""
    distance = input_one_value_dialog(
        parent=self,
        title="Line from template",
        label="Insert distance",
        default_value=100,
    )
    if distance is None:
        """Un-Freeze QT interface"""
        self.enable_actions()
        return

    in_line_name = self.parent.geol_coll.df.loc[
        self.parent.geol_coll.df["uid"] == input_uid, "name"
    ].values[0]
    out_line_name = in_line_name + "_kink_" + "%d" % distance

    """Create empty dictionary for the output line and set name and geological_type.
    IN THE FUTURE see if other metadata should be automatically set."""
    line_dict = deepcopy(self.parent.geol_coll.entity_dict)
    line_dict["name"] = out_line_name
    line_dict["geological_type"] = self.parent.geol_coll.df.loc[
        self.parent.geol_coll.df["uid"] == input_uid, "geological_type"
    ].values[0]
    line_dict["geological_feature"] = self.parent.geol_coll.get_uid_geological_feature(
        self.selected_uids[0]
    )
    line_dict["scenario"] = self.parent.geol_coll.get_uid_scenario(
        self.selected_uids[0]
    )
    if isinstance(self, NewViewMap):
        # if isinstance(self, (ViewMap, NewViewMap)):
        line_dict["vtk_obj"] = PolyLine()
        line_dict["topological_type"] = "PolyLine"
        inU = self.parent.geol_coll.get_uid_vtk_obj(input_uid).points_X
        inV = self.parent.geol_coll.get_uid_vtk_obj(input_uid).points_Y
    # elif isinstance(self, (ViewXsection, NewViewXsection)):
    elif isinstance(self, NewViewXsection):
        line_dict["vtk_obj"] = XsPolyLine(self.this_x_section_uid, parent=self.parent)
        line_dict["topological_type"] = "XsPolyLine"
        line_dict["x_section"] = self.this_x_section_uid
        inU, inV = self.parent.geol_coll.get_uid_vtk_obj(input_uid).world2plane()

    """Stack coordinates in two-columns matrix"""
    inUV = np_column_stack((inU, inV))
    """Deselect input line."""
    self.clear_selection()
    self.parent.geology_geom_modified_signal.emit(
        [input_uid]
    )  # emit uid as list to force redraw()
    """Run the Shapely function."""
    shp_line_in = LineString(inUV)
    if shp_line_in.is_simple:
        shp_line_out = shp_line_in.parallel_offset(
            distance, "left", resolution=16, join_style=2, mitre_limit=10.0
        )  # kink folds are obtained with join_style=2, mitre_limit=10.0
        outUV = np_array(shp_line_out)
        """Un-stack output coordinates and write them to the empty dictionary."""
        outU = outUV[:, 0]
        outV = outUV[:, 1]
    else:
        print("Polyline is not simple, it self-intersects")
        """Un-Freeze QT interface"""
        self.enable_actions()
        return
    if isinstance(self, NewViewMap):
        # if isinstance(self, (ViewMap, NewViewMap)):
        outX = outU
        outY = outV
        outZ = np_zeros(np_shape(outX))
    # elif isinstance(self, (ViewXsection, NewViewXsection)):
    elif isinstance(self, NewViewXsection):
        outX, outY, outZ = self.parent.xsect_coll.plane2world(
            self.this_x_section_uid, outU, outV
        )
    """Stack coordinates in two-columns matrix and write to vtk object."""
    outXYZ = np_column_stack((outX, outY, outZ))
    line_dict["vtk_obj"].points = outXYZ
    line_dict["vtk_obj"].auto_cells()
    """Create entity from the dictionary and run left_right."""
    if line_dict["vtk_obj"].points_number > 0:
        output_uid = self.parent.geol_coll.add_entity_from_dict(line_dict)
        left_right(output_uid)
    else:
        print("Empty object")
    """Un-Freeze QT interface"""
    self.enable_actions()


def copy_similar(
    self, vector
):  # this must be done per-part_______________________________________________________
    """Similar folding. Create a line copied and translated from a template line.
    Does not need U,V coordinates since the translation vector is already in world coords
    """
    print("Copy Similar. Create a line copied and translated.")
    """Terminate running event loops"""
    # self.stop_event_loops()
    """Check if a line is selected"""
    if not self.selected_uids:
        print(" -- No input data selected -- ")
        return
    if (
        self.parent.geol_coll.get_uid_topological_type(self.selected_uids[0])
        != "PolyLine"
    ) and (
        self.parent.geol_coll.get_uid_topological_type(self.selected_uids[0])
        != "XsPolyLine"
    ):
        print(" -- Selected data is not a line -- ")
        return
    """Freeze QT interface"""
    self.disable_actions()
    """If more than one line is selected, keep the first."""
    input_uid = self.selected_uids[0]
    """IN THE FUTURE add a test to check that the selected feature is a geological feature"""
    """Create empty dictionary for the output line and set name and geological_type.
    IN THE FUTURE see if other metadata should be automatically set."""
    line_dict = deepcopy(self.parent.geol_coll.entity_dict)
    line_dict["geological_type"] = self.parent.geol_coll.df.loc[
        self.parent.geol_coll.df["uid"] == input_uid, "geological_type"
    ].values[0]
    line_dict["geological_feature"] = self.parent.geol_coll.get_uid_geological_feature(
        self.selected_uids[0]
    )
    line_dict["scenario"] = self.parent.geol_coll.get_uid_scenario(
        self.selected_uids[0]
    )
    if isinstance(self, NewViewMap):
        line_dict["vtk_obj"] = PolyLine()
        line_dict["topological_type"] = "PolyLine"
    elif isinstance(self, NewViewXsection):
        line_dict["vtk_obj"] = XsPolyLine(self.this_x_section_uid, parent=self.parent)
        line_dict["topological_type"] = "XsPolyLine"
        line_dict["x_section"] = self.this_x_section_uid
    """Get coordinates of input line."""
    inX = self.parent.geol_coll.get_uid_vtk_obj(input_uid).points_X
    inY = self.parent.geol_coll.get_uid_vtk_obj(input_uid).points_Y
    inZ = self.parent.geol_coll.get_uid_vtk_obj(input_uid).points_Z
    """Get similar folding vector."""
    if vector.length == 0:
        print("Zero-length vector")
        self.enable_actions()
        return

    """Create output line."""
    outX = inX + vector.deltas[0]
    outY = inY + vector.deltas[1]
    outZ = inZ + vector.deltas[2]
    """Stack coordinates in two-columns matrix and write to vtk object."""
    outXYZ = np_column_stack((outX, outY, outZ))
    line_dict["vtk_obj"].points = outXYZ
    line_dict["vtk_obj"].auto_cells()
    """Set output line name."""
    in_line_name = self.parent.geol_coll.df.loc[
        self.parent.geol_coll.df["uid"] == input_uid, "name"
    ].values[0]
    distance = vector.length
    out_line_name = f"{in_line_name}_simi_{round(distance, 2)}"

    line_dict["name"] = out_line_name
    """Create entity from the dictionary and run left_right."""
    output_uid = self.parent.geol_coll.add_entity_from_dict(line_dict)
    left_right(output_uid)
    """Deselect input line."""
    if line_dict["vtk_obj"].points_number > 0:
        self.clear_selection()
        # self.parent.geology_geom_modified_signal.emit([input_uid])  # emit uid as list to force redraw()
    else:
        print("Empty object")
    """Un-Freeze QT interface"""
    self.enable_actions()


def measure_distance(self, vector):
    """Tool to measure distance between two points. Draw a vector_by_mouse and obtain length and azimuth"""
    print("Measure Distance between two points by drawing a vector by mouse")
    """Terminate running event loops"""
    """Freeze QT interface"""
    self.disable_actions()
    # points = vector.points
    if vector.length == 0:
        print("Zero-length vector")
        self.enable_actions()
        return

    message = (
        "Distance (m): "
        + str(round(vector.length, 2))
        + "\n\n"
        + "Azimuth: "
        + str(round(vector.azimuth, 2))
        + "\n\n"
        + "Dip: "
        + str(round(vector.dip, 2))
        + "\n\n"
        + "Point1: "
        + str(np_round(vector.p1, 2))
        + "\n\n"
        + "Point2: "
        + str(np_round(vector.p2, 2))
    )
    out = message_dialog(title="Measure Distance", message=message)
    """Un-Freeze QT interface"""
    for action in self.findChildren(QAction):
        action.setEnabled(True)


"""Helper and shared functions"""


def flip_line(self, uid=None):
    """Ensures lines are oriented left-to-right and bottom-to-top"""
    # self.parent.geol_coll.get_uid_vtk_obj(uid).points = np_flip(self.parent.geol_coll.get_uid_vtk_obj(uid).points, 0)
    self.parent.geol_coll.get_uid_vtk_obj(uid).points = np_flip(
        self.parent.geol_coll.get_uid_vtk_obj(uid).points, 0
    )


def left_right(self, uid=None):
    """Ensures lines are oriented left-to-right and bottom-to-top in map or cross-section"""
    if isinstance(self, NewViewMap):
        # if isinstance(self, ViewMap):
        U_line = self.parent.geol_coll.get_uid_vtk_obj(uid).points_X
        V_line = self.parent.geol_coll.get_uid_vtk_obj(uid).points_Y
    # elif isinstance(self, ViewXsection):
    elif isinstance(self, NewViewXsection):
        U_line, V_line = self.parent.geol_coll.get_uid_vtk_obj(uid).world2plane()
    else:
        return
    if U_line[0] > U_line[-1]:  # reverse if right-to-left
        flip_line(uid=uid)
    elif (
        U_line[0] == U_line[-1] and V_line[0] > V_line[-1]
    ):  # reverse if vertical up-to-down
        flip_line(uid=uid)


def int_node(line1, line2):
    """
    Function used to add the intersection node to a line crossed or touched by a second line.
    This function works by extending of a given factor the start and end segment the line2 and then use shapely to:

    1. Split line1 with line2
    2. Join the two split geometries

    We do this to identify and add the intersection node to line1:

    O----------O --split--> O-----O O-----O --join--> O-----O-----O

    The extension is used in case the joint is a Y or T and the positioning of the node is not pixel perfect. Depending
    on the number of segment composing line2 we extend in different ways:

    1. Only one segment extend the whole thing using the start and end vertex
    2. Two segments extend the two segments using the end of the first and the start of the second.
    3. Three or more segments extend the first and last segment using the end of the first and the start of the last.
    """

    fac = 100
    if line1.crosses(line2):
        split_lines1 = split(line1, line2)
        outcoords1 = [list(i.coords) for i in split_lines1]

        new_line = LineString([i for sublist in outcoords1 for i in sublist])
        extended_line = line2

    else:
        if len(line2.coords) == 2:
            scaled_segment1 = scale(
                line2, xfact=fac, yfact=fac, origin=line2.boundary[0]
            )
            scaled_segment2 = scale(
                scaled_segment1,
                xfact=fac,
                yfact=fac,
                origin=scaled_segment1.boundary[1],
            )
            extended_line = LineString(scaled_segment2)
        elif len(line2.coords) == 3:
            first_seg = LineString(line2.coords[:2])
            last_seg = LineString(line2.coords[-2:])
            scaled_first_segment = scale(
                first_seg, xfact=fac, yfact=fac, origin=first_seg.boundary[1]
            )
            scaled_last_segment = scale(
                last_seg, xfact=fac, yfact=fac, origin=last_seg.boundary[0]
            )
            extended_line = LineString(
                [*scaled_first_segment.coords, *scaled_last_segment.coords]
            )
        else:
            first_seg = LineString(line2.coords[:2])
            last_seg = LineString(line2.coords[-2:])

            scaled_first_segment = scale(
                first_seg, xfact=fac, yfact=fac, origin=first_seg.boundary[1]
            )
            scaled_last_segment = scale(
                last_seg, xfact=fac, yfact=fac, origin=last_seg.boundary[0]
            )
            extended_line = LineString(
                [
                    *scaled_first_segment.coords,
                    *line2.coords[2:-2],
                    *scaled_last_segment.coords,
                ]
            )

        split_lines = split(line1, extended_line)

        outcoords = [list(i.coords) for i in split_lines]
        new_line = LineString([i for sublist in outcoords for i in sublist])

    return new_line, extended_line


def clean_intersection(self):
    """
    Clean intersections for a given line. The "search radius" is a buffer applied to the selected line to snap lines
    at a given distance from the selected line
    """
    data = []
    if isinstance(self, NewViewMap):
        for i, line in self.parent.geol_coll.df.loc[
            self.parent.geol_coll.df["topological_type"] == "PolyLine"
        ].iterrows():
            vtkgeom = line["vtk_obj"]
            uid = line["uid"]
            geom = LineString(vtkgeom.points[:, :2])
            data.append({"uid": uid, "geometry": geom})
    elif isinstance(self, NewViewXsection):
        for i, line in self.parent.geol_coll.df.loc[
            self.parent.geol_coll.df["topological_type"] == "XsPolyLine"
        ].iterrows():
            vtkgeom = line["vtk_obj"]
            uid = line["uid"]
            inU, inV = vtkgeom.world2plane()
            inUV = np_column_stack((inU, inV))
            geom = LineString(inUV)
            data.append({"uid": uid, "geometry": geom})
    search = input_one_value_dialog(
        parent=self,
        title="Search radius",
        label="Insert search radius",
        default_value=0.05,
    )
    df = geodataframe(data=data)
    df_buffer = df.buffer(search)

    sel_uid = self.selected_uids[0]

    line1 = df.loc[df["uid"] == sel_uid, "geometry"].values[0]
    idx_line1 = df.index[df["uid"] == sel_uid]

    df_buffer.drop(index=idx_line1, inplace=True)

    idx_list = df_buffer.index[
        df_buffer.intersects(line1) == True
    ]  # Subset the intersecting lines
    uids = df.iloc[idx_list]["uid"].to_list()

    uids.append(sel_uid)

    self.selected_uids = uids
    snap_line(self)
