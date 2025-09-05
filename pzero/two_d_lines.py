"""two_d_lines.py
PZero© Andrea Bistacchi"""

from copy import deepcopy

from PySide6.QtGui import QAction

from geopandas import GeoDataFrame as geodataframe

from numpy import stack as np_stack
from numpy import arange as np_arange
from numpy import array as np_array
from numpy import column_stack as np_column_stack
from numpy import flipud as np_flipud
from numpy import round as np_round
from numpy import shape as np_shape
from numpy import zeros as np_zeros
from numpy import concatenate as np_concatenate
from numpy.linalg import norm as np_norm

# from shapely import affinity
from shapely.affinity import scale as shp_scale
from shapely.affinity import rotate as shp_rotate
from shapely.geometry import Point as shp_point
from shapely.geometry import LineString as shp_linestring

# from shapely.geometry import MultiLineString as shp_multilinestring
from shapely.ops import snap as shp_snap
from shapely.ops import split as shp_split

from .helpers.helper_dialogs import (
    multiple_input_dialog,
    input_one_value_dialog,
    message_dialog,
)
from .helpers.helper_widgets import Editor, Tracer
from .helpers.helper_functions import freeze_gui
from .entities_factory import PolyLine, XsPolyLine

from .views.dock_window import ViewMap, ViewXsection


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
    # Create deepcopy of the geological entity dictionary.
    line_dict = deepcopy(self.parent.geol_coll.entity_dict)
    # One dictionary is set as input for a general widget of multiple-value-input"""
    line_dict_in = {
        "name": ["PolyLine name: ", "new_pline"],
        "role": [
            "Role: ",
            self.parent.geol_coll.valid_roles,
        ],
        "feature": [
            "Feature: ",
            self.parent.geol_coll.legend_df["feature"].tolist(),
        ],
        "scenario": [
            "Scenario: ",
            list(set(self.parent.geol_coll.legend_df["scenario"].tolist())),
        ],
    }
    line_dict_updt = multiple_input_dialog(
        title="Digitize new PolyLine", input_dict=line_dict_in
    )
    # Check if the output of the widget is empty or not. If the Cancel button was clicked, the tool quits
    if line_dict_updt is None:
        self.enable_actions()
        return
    # Getting the values that have been typed by the user through the widget
    for key in line_dict_updt:
        line_dict[key] = line_dict_updt[key]
    if isinstance(self, ViewMap):
        line_dict["topology"] = "PolyLine"
        line_dict["x_section"] = ""
        line_dict["vtk_obj"] = PolyLine()
    elif isinstance(self, ViewXsection):
        line_dict["topology"] = "XsPolyLine"
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
        if isinstance(self, ViewMap):
            vtk_obj = PolyLine()
        elif isinstance(self, ViewXsection):
            vtk_obj = XsPolyLine(
                x_section_uid=self.this_x_section_uid, parent=self.parent
            )
        vtk_obj.ShallowCopy(traced_pld)
        self.parent.geol_coll.replace_vtk(uid=uid, vtk_object=vtk_obj)
        editor.EnabledOff()
        self.clear_selection()
        self.enable_actions()

    if not self.selected_uids:
        self.print_terminal(" -- No input data selected -- ")
        return
    self.disable_actions()
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


@freeze_gui
def sort_line_nodes(self):
    """Sort line nodes."""
    self.print_terminal("Sort line nodes according to cell order.")
    # """Terminate running event loops"""
    # self.stop_event_loops()
    # Check if a line is selected
    if not self.selected_uids:
        self.print_terminal(" -- No input data selected -- ")
        return
    # for action in self.findChildren(QAction):
    #     if isinstance(action.parentWidget(), NavigationToolbar) is False:
    #         action.setDisabled(True)
    # If more than one line is selected, keep the first.
    for current_uid in self.selected_uids:
        # For some reason in the following the [:] is needed.
        self.parent.geol_coll.get_uid_vtk_obj(
            current_uid
        ).sort_nodes()  # this could be probably done per-part__________________________
        # Deselect input line.
        self.parent.signals.geom_modified.emit([current_uid], self.parent.geol_coll)
        # for action in self.findChildren(QAction):
        #     action.setEnabled(True)
    # Deselect input line.
    self.clear_selection()


@freeze_gui
def move_line(self, vector):
    """Move the whole line by rigid-body translation.
    Here transformation to UV is not necessary since the translation vector is already in world space
    """
    # It should block the function before to activate the vector
    if not self.selected_uids:
        self.print_terminal(" -- No input data selected -- ")
        return

    self.print_terminal("Move Line. Move the whole line by rigid-body translation.")
    if vector.length == 0:
        self.print_terminal("Zero-length vector")
        return

    for current_uid in self.selected_uids:
        if (self.parent.geol_coll.get_uid_topology(current_uid) != "PolyLine") and (
            self.parent.geol_coll.get_uid_topology(current_uid) != "XsPolyLine"
        ):
            self.print_terminal(" -- Selected data is not a line -- ")
            return

        # Editing loop.
        # -----For some reason in the following the [:] is needed.-----
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

        points = np_stack((x, y, z), axis=1)
        self.parent.geol_coll.get_uid_vtk_obj(current_uid).points = points
        left_right(current_uid)
        # Deselect input line.
        self.parent.signals.geom_modified.emit([current_uid], self.parent.geol_coll)
    # Deselect input line.
    self.clear_selection()


@freeze_gui
def rotate_line(self):
    """Rotate lines by rigid-body rotation using Shapely."""
    self.print_terminal(
        "Rotate Line. Rotate the whole line by rigid-body rotation. Please insert angle of clockwise rotation."
    )
    # Check if at least a line is selected.
    if not self.selected_uids:
        self.print_terminal(" -- No input data selected -- ")
        return
    # Input rotation angle. None exits the function.
    angle = input_one_value_dialog(
        parent=self,
        title="Rotate Line",
        label="Insert rotation angle in degrees, clockwise",
        default_value=10,
    )
    if angle is None:
        self.print_terminal(" -- Angle is None -- ")
        return
    for current_uid in self.selected_uids:
        if (self.parent.geol_coll.get_uid_topology(current_uid) != "PolyLine") and (
            self.parent.geol_coll.get_uid_topology(current_uid) != "XsPolyLine"
        ):
            self.print_terminal(" -- Selected data is not a line -- ")
            return
        if isinstance(self, ViewMap):
            inU = self.parent.geol_coll.get_uid_vtk_obj(current_uid).points_X
            inV = self.parent.geol_coll.get_uid_vtk_obj(current_uid).points_Y
        elif isinstance(self, ViewXsection):
            inU, inV = self.parent.geol_coll.get_uid_vtk_obj(current_uid).world2plane()
        # Stack coordinates in two-columns matrix and convert into Shapely object.
        inUV = np_column_stack((inU, inV))
        shp_line_in = shp_linestring(inUV)
        # Use Shapely to rotate
        shp_line_out = shp_rotate(
            shp_line_in, angle, origin="centroid", use_radians=False
        )
        # Un-stack output coordinates and write them to the empty dictionary.
        outUV = np_array(shp_line_out.coords)
        outU = outUV[:, 0]
        outV = outUV[:, 1]
        if isinstance(self, ViewMap):
            outX = outU
            outY = outV
            outZ = self.parent.geol_coll.get_uid_vtk_obj(current_uid).points_Z
        elif isinstance(self, ViewXsection):
            outX, outY, outZ = self.parent.xsect_coll.plane2world(
                self.this_x_section_uid, outU, outV
            )
        outXYZ = np_column_stack((outX, outY, outZ))
        self.parent.geol_coll.get_uid_vtk_obj(current_uid).points = outXYZ
        left_right(current_uid)
        # emit uid as list to force redraw()
        self.parent.signals.geom_modified.emit([current_uid], self.parent.geol_coll)
    # Deselect input line.
    self.clear_selection()


def extend_line(self):
    def end_edit(event, uid):
        self.plotter.untrack_click_position(side="right")
        self.plotter.untrack_click_position(side="left")
        self.plotter.clear_events_for_key("k")

        traced_pld = (
            extender.GetContourRepresentation().GetContourRepresentationAsPolyData()
        )
        if isinstance(self, ViewMap):
            vtk_obj = PolyLine()
        elif isinstance(self, ViewXsection):
            vtk_obj = XsPolyLine(
                x_section_uid=self.this_x_section_uid, parent=self.parent
            )
        vtk_obj.ShallowCopy(traced_pld)

        self.parent.geol_coll.replace_vtk(uid=uid, vtk_object=vtk_obj)
        extender.EnabledOff()
        self.clear_selection()
        self.enable_actions()

    # Extend selected line.
    self.print_terminal("Extend Line. Press 'k' to change end of line to extend.")
    """Terminate running event loops"""
    # self.stop_event_loops()
    # Check if a line is selected
    if not self.selected_uids:
        self.print_terminal(" -- No input data selected -- ")
        return
    if (
        self.parent.geol_coll.get_uid_topology(self.selected_uids[0]) != "PolyLine"
    ) and (
        self.parent.geol_coll.get_uid_topology(self.selected_uids[0]) != "XsPolyLine"
    ):
        self.print_terminal(" -- Selected data is not a line -- ")
        return
    # Freeze QT interface
    self.disable_actions()
    # If more than one line is selected, keep the first
    sel_uid = self.selected_uids[0]
    current_line = self.get_actor_by_uid(sel_uid).GetMapper().GetInput()

    extender = Editor(self)
    extender.EnabledOn()
    extender.initialize(current_line, "extend")

    self.plotter.track_click_position(
        side="right", callback=lambda event: end_edit(event, sel_uid)
    )


@freeze_gui
def split_line_line(self):
    """Split line (paper) with another line (scissors). First, select the paper-line then the scissors-line"""
    # print("Split line with line. Line to be split has been selected, please select an intersecting line.")   #Reviw needed
    # Terminate running event loops
    # Check if a line is selected
    if not self.selected_uids:
        self.print_terminal(" -- No input data selected -- ")
        return
    elif len(self.selected_uids) <= 1:
        self.print_terminal(
            " -- Not enough input data selected. Select at least 2 objects -- "
        )
        return

    current_uid_scissors = self.selected_uids[-1]
    if (
        self.parent.geol_coll.get_uid_topology(current_uid_scissors) != "PolyLine"
    ) and (
        self.parent.geol_coll.get_uid_topology(current_uid_scissors) != "XsPolyLine"
    ):
        self.print_terminal(" -- Selected scissor is not a line -- ")
        return

    if isinstance(self, ViewMap):
        inU = self.parent.geol_coll.get_uid_vtk_obj(current_uid_scissors).points_X
        inV = self.parent.geol_coll.get_uid_vtk_obj(current_uid_scissors).points_Y
    elif isinstance(self, ViewXsection):
        inU, inV = self.parent.geol_coll.get_uid_vtk_obj(
            current_uid_scissors
        ).world2plane()

    inUV_scissors = np_column_stack((inU, inV))
    shp_line_in_scissors = shp_linestring(inUV_scissors)

    for current_uid_paper in self.selected_uids[:-1]:
        if (
            self.parent.geol_coll.get_uid_topology(current_uid_paper) != "PolyLine"
        ) and (
            self.parent.geol_coll.get_uid_topology(current_uid_paper) != "XsPolyLine"
        ):
            self.print_terminal(" -- Selected paper is not a line -- ")
            return

        if isinstance(self, ViewMap):
            inU = self.parent.geol_coll.get_uid_vtk_obj(current_uid_paper).points_X
            inV = self.parent.geol_coll.get_uid_vtk_obj(current_uid_paper).points_Y
        elif isinstance(self, ViewXsection):
            inU, inV = self.parent.geol_coll.get_uid_vtk_obj(
                current_uid_paper
            ).world2plane()
        inUV_paper = np_column_stack((inU, inV))

        # Create deepcopies of the selected entities. Split U- and V-coordinates.
        # inU_paper = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid_paper).points[:, 0])
        # inV_paper = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid_paper).points[:, 1])
        # inZ_paper = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid_paper).points[:, 2])
        # inU_scissors = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid_scissors).points[:, 0])
        # inV_scissors = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid_scissors).points[:, 1])
        # inZ_scissors = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid_scissors).points[:, 2])

        # Stack coordinates in two-columns matrix
        # inUV_paper = np_column_stack((inU_paper, inV_paper,inZ_paper))
        # Run the Shapely function.
        shp_line_in_paper = shp_linestring(inUV_paper)
        # Check if the two lineal geometries have shared path with dimension 1 (= they share a line-type object)
        if shp_line_in_paper.crosses(shp_line_in_scissors):
            # Run the split shapely function.
            split_lines = shp_split(
                shp_line_in_paper, shp_line_in_scissors
            )  # lines must include all line parts not affected by splitting and two parts for the split line__________
        else:  # handles the case when the shp_linestring share a linear path and, for the moment, exists the tool
            # Deselect input line.
            self.clear_selection()
            return
        replace = 1  # replace = 1 for the first line to operate replace_vtk
        uids = [current_uid_scissors]
        for line in split_lines.geoms:
            # Create empty dictionary for the output lines.
            new_line = deepcopy(self.parent.geol_coll.entity_dict)
            new_line["name"] = (
                self.parent.geol_coll.df.loc[
                    self.parent.geol_coll.df["uid"] == current_uid_paper, "name"
                ].values[0]
                + "_split"
            )
            new_line["topology"] = self.parent.geol_coll.df.loc[
                self.parent.geol_coll.df["uid"] == current_uid_paper, "topology"
            ].values[0]
            new_line["role"] = self.parent.geol_coll.df.loc[
                self.parent.geol_coll.df["uid"] == current_uid_paper, "role"
            ].values[0]
            new_line["feature"] = self.parent.geol_coll.df.loc[
                self.parent.geol_coll.df["uid"] == current_uid_paper,
                "feature",
            ].values[0]
            new_line["scenario"] = self.parent.geol_coll.df.loc[
                self.parent.geol_coll.df["uid"] == current_uid_paper, "scenario"
            ].values[0]
            outU = np_array(line.coords)[:, 0]
            outV = np_array(line.coords)[:, 1]
            if isinstance(self, ViewMap):
                new_line["x_section"] = None
                new_line["vtk_obj"] = PolyLine()
                outX = outU
                outY = outV
                outZ = np_zeros(np_shape(outX))

            elif isinstance(self, ViewXsection):
                new_line["x_section"] = self.this_x_section_uid
                new_line["vtk_obj"] = XsPolyLine(
                    self.this_x_section_uid, parent=self.parent
                )
                outX, outY, outZ = self.parent.xsect_coll.plane2world(
                    self.this_x_section_uid, outU, outV
                )
            # Create new vtk objects
            outXYZ = np_column_stack((outX, outY, outZ))
            new_line["vtk_obj"].points = outXYZ
            new_line["vtk_obj"].auto_cells()
            if new_line["vtk_obj"].points_number > 0:
                # Replace VTK object
                if replace == 1:
                    self.parent.geol_coll.replace_vtk(
                        uid=current_uid_paper, vtk_object=new_line["vtk_obj"]
                    )
                    self.parent.signals.geom_modified.emit(
                        [current_uid_paper], self.parent.geol_coll
                    )
                    replace = 0
                    uids.append(current_uid_paper)
                else:
                    # Create entity from the dictionary
                    uid = self.parent.geol_coll.add_entity_from_dict(new_line)
                    uids.append(uid)
                del new_line["vtk_obj"]
            else:
                self.print_terminal("Empty object")
        # Deselect input line and force redraw

        # self.parent.signals.geom_modified.emit(uids)  # emit uid as list to force redraw()
    # Deselect input line.
    self.clear_selection()


def split_line_existing_point(self):
    # Here transformation to UV is not necessary since we select a point in world space
    def end_select(event, uid):
        point_pos = selector.active_pos
        self.plotter.untrack_click_position(side="right")
        # Create empty dictionary for the output line
        new_line_1 = deepcopy(self.parent.geol_coll.entity_dict)
        new_line_2 = deepcopy(self.parent.geol_coll.entity_dict)
        new_line_2["name"] = (
            self.parent.geol_coll.df.loc[
                self.parent.geol_coll.df["uid"] == uid, "name"
            ].values[0]
            + "_split"
        )
        new_line_2["topology"] = self.parent.geol_coll.df.loc[
            self.parent.geol_coll.df["uid"] == uid, "topology"
        ].values[0]
        new_line_2["role"] = self.parent.geol_coll.df.loc[
            self.parent.geol_coll.df["uid"] == uid, "role"
        ].values[0]
        new_line_2["feature"] = self.parent.geol_coll.df.loc[
            self.parent.geol_coll.df["uid"] == uid, "feature"
        ].values[0]
        new_line_2["scenario"] = self.parent.geol_coll.df.loc[
            self.parent.geol_coll.df["uid"] == uid, "scenario"
        ].values[0]
        if isinstance(self, ViewMap):
            inU_line = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(uid).points[:, 0])
            inV_line = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(uid).points[:, 1])
        elif isinstance(self, ViewXsection):
            inU_line = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(uid).points_W)
            inV_line = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(uid).points_Z)
            new_line_2["x_section"] = self.this_x_section_uid
        # Stack coordinates in two-columns matrix"""
        inUV_line = np_column_stack((inU_line, inV_line))
        # Run the Shapely function.
        shp_line_in = shp_linestring(
            deepcopy(self.parent.geol_coll.get_uid_vtk_obj(uid).points)
        )
        # x_vertex_unit = deepcopy(current_line_U_true[vertex_ind])
        # y_vertex_unit = deepcopy(current_line_V_true[vertex_ind])
        shp_point_in = shp_point(point_pos[0], point_pos[1], point_pos[2])
        # Splitting shapely function.
        split_lines = shp_split(shp_line_in, shp_point_in)
        line1_out = shp_linestring(split_lines.geoms[0])
        line2_out = shp_linestring(split_lines.geoms[1])
        # Convert shapely lines to UV objects
        outUV_1 = deepcopy(np_array(line1_out.coords))
        outUV_2 = deepcopy(np_array(line2_out.coords))
        # Un-stack output coordinates and write them to the empty dictionary.
        outU_1 = outUV_1[:, 0]
        outV_1 = outUV_1[:, 1]
        outU_2 = outUV_2[:, 0]
        outV_2 = outUV_2[:, 1]
        if isinstance(self, ViewMap):
            outX_1 = outU_1
            outY_1 = outV_1
            outZ_1 = np_zeros(np_shape(outX_1))
            outX_2 = outU_2
            outY_2 = outV_2
            outZ_2 = np_zeros(np_shape(outX_2))
        elif isinstance(self, ViewXsection):
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
        if isinstance(self, ViewMap):
            new_line_1["vtk_obj"] = PolyLine()
            new_line_2["vtk_obj"] = PolyLine()
        elif isinstance(self, ViewXsection):
            new_line_1["vtk_obj"] = XsPolyLine(
                self.this_x_section_uid, parent=self.parent
            )
            new_line_2["vtk_obj"] = XsPolyLine(
                self.this_x_section_uid, parent=self.parent
            )
        new_line_1["vtk_obj"].points = deepcopy(np_array(line1_out.coords))
        new_line_1["vtk_obj"].auto_cells()
        new_line_2["vtk_obj"].points = deepcopy(np_array(line2_out.coords))
        new_line_2[
            "vtk_obj"
        ].auto_cells()  # lines must include all line parts not affected by splitting and two parts for the split line__________
        # Replace VTK object
        if new_line_1["vtk_obj"].points_number > 0:
            self.parent.geol_coll.replace_vtk(uid=uid, vtk_object=new_line_1["vtk_obj"])
            del new_line_1
        else:
            self.print_terminal("Empty object")
        # Create entity from the dictionary
        if new_line_2["vtk_obj"].points_number > 0:
            self.parent.geol_coll.add_entity_from_dict(new_line_2)
            del new_line_2
        else:
            self.print_terminal("Empty object")
        # Deselect input line.
        self.clear_selection()
        selector.EnabledOff()
        # Un-Freeze QT interface
        self.enable_actions()

    # Split line at selected existing point (vertex)
    self.print_terminal(
        "Split line at existing point. Line to be split has been selected,\nplease select an existing point for splitting."
    )
    # Check if a line is selecte
    if not self.selected_uids:
        self.print_terminal(" -- No input data selected -- ")
        return
    if (
        self.parent.geol_coll.get_uid_topology(self.selected_uids[0]) != "PolyLine"
    ) and (
        self.parent.geol_coll.get_uid_topology(self.selected_uids[0]) != "XsPolyLine"
    ):
        self.print_terminal(" -- Selected data is not a line -- ")
        return
    # Freeze QT interface
    self.disable_actions
    # If more than one line is selected, keep the first
    sel_uid = self.selected_uids[0]
    current_line = self.get_actor_by_uid(sel_uid)
    line = current_line.mapper.dataset
    selector = Editor(self)
    selector.EnabledOn()
    selector.initialize(line, "select")
    self.plotter.track_click_position(
        side="right", callback=lambda event: end_select(event, sel_uid)
    )


def split_line_vector(self, vector): ...


# check merge, snap, and see if a bridge nodes method is needed____________________


@freeze_gui
def merge_lines(self):
    """Merge two (contiguous or non-contiguous) lines.
    Metadata will be taken from the first selected line."""
    # Check if at least 2 lines are selected.
    self.print_terminal(f"self.selected_uids: {self.selected_uids}")
    if not self.selected_uids:
        self.print_terminal(" -- No input data selected -- ")
        self.enable_actions()
        return
    # Create local copy of selected_uids
    in_uids = self.selected_uids
    if len(in_uids) <= 1:
        self.print_terminal(
            " -- Not enough input data selected. Select at least 2 objects -- "
        )
        self.enable_actions()
        return
    # Check if all input entities are PolyLine or XsPolyLine
    # print(in_uids)
    for uid in in_uids:
        if self.parent.geol_coll.get_uid_topology(uid) == "PolyLine":
            continue
        elif self.parent.geol_coll.get_uid_topology(uid) == "XsPolyLine":
            continue
        else:
            self.print_terminal(" -- Selection must include lines only -- ")
            self.enable_actions()
            return
    # For XsPolyLine, check that they all belong to the same cross-section.
    this_xsection = None
    for uid in in_uids:
        if self.parent.geol_coll.get_uid_topology(uid) == "XsPolyLine":
            if this_xsection is None:
                this_xsection = self.parent.geol_coll.get_uid_x_section(uid)
            elif this_xsection is not None:
                if self.parent.geol_coll.get_uid_x_section(uid) != this_xsection:
                    self.print_terminal(
                        " -- Selection must include lines belonging to the same cross-section only -- "
                    )
                    self.enable_actions()
                    return
    # Create empty dictionary for the output line.
    new_line = deepcopy(self.parent.geol_coll.entity_dict)
    # Populate metadata from first selected line.
    new_line["name"] = self.parent.geol_coll.get_uid_name(in_uids[0])
    new_line["topology"] = self.parent.geol_coll.get_uid_topology(in_uids[0])
    new_line["role"] = self.parent.geol_coll.get_uid_role(in_uids[0])
    new_line["feature"] = self.parent.geol_coll.get_uid_feature(in_uids[0])
    new_line["scenario"] = self.parent.geol_coll.get_uid_scenario(in_uids[0])
    new_line["x_section"] = self.parent.geol_coll.get_uid_x_section(in_uids[0])
    # Mering properties not yet implemented.
    new_line["properties_names"] = []
    new_line["properties_components"] = []
    # Create empty PolyLine() or XsPolyLine().
    if self.parent.geol_coll.get_uid_topology(in_uids[0]) == "XsPolyLine":
        new_line["vtk_obj"] = XsPolyLine()
    else:
        new_line["vtk_obj"] = PolyLine()
    # Add points to new merged line.
    points_0 = self.parent.geol_coll.get_uid_vtk_obj(in_uids[0]).points.copy()
    for uid in in_uids[1::]:
        points_1 = self.parent.geol_coll.get_uid_vtk_obj(uid).points.copy()
        first2first = points_0[1, :] - points_1[1, :]
        first2first_norm = np_norm(first2first)
        first2last = points_0[1, :] - points_1[-1, :]
        first2last_norm = np_norm(first2last)
        last2first = points_0[-1, :] - points_1[1, :]
        last2first_norm = np_norm(last2first)
        last2last = points_0[-1, :] - points_1[-1, :]
        last2last_norm = np_norm(last2last)
        scores = np_array(
            [first2first_norm, first2last_norm, last2first_norm, last2last_norm]
        )
        # Smaller norm first2first_norm -> join first node of points_0 to first point of points_1 -> need to revert points_0
        if scores.argmin() == 0:
            points_0 = np_flipud(points_0)
        # Smaller norm first2last_norm -> join first node of points_0 to last point of points_1 -> need to revert both
        if scores.argmin() == 1:
            points_0 = np_flipud(points_0)
            points_1 = np_flipud(points_1)
        # Smaller norm last2first_norm -> join last node of points_0 to first point of points_1 -> need to revert none
        if scores.argmin() == 2:
            pass
        # Smaller norm last2last_norm -> join last node of points_0 to last point of points_1 -> need to revert points_1
        if scores.argmin() == 3:
            points_1 = np_flipud(points_1)
        points_0 = np_concatenate((points_0, points_1), axis=0)
    new_line["vtk_obj"].points = points_0
    # Automatically create all line cells.
    new_line["vtk_obj"].auto_cells()
    # Deselect input lines.
    self.clear_selection()
    # Remove input lines.
    for uid in in_uids:
        self.parent.geol_coll.remove_entity(uid)
    self.parent.geol_coll.add_entity_from_dict(new_line)


@freeze_gui
def snap_line(self):
    """Snaps vertices of the selected line (the snapping-line) to the nearest vertex of the chosen line (goal-line),
    depending on the Tolerance parameter."""
    # print("Snap line to line. Line to be snapped has been selected, please select second line.")
    # Terminate running event loops
    # Check if a line is selected
    if not self.selected_uids:
        self.print_terminal(" -- No input data selected -- ")
        return
    elif len(self.selected_uids) <= 1:
        self.print_terminal(
            " -- Not enough input data selected. Select at least 2 objects -- "
        )
        return
    current_uid_goal = self.selected_uids[-1]
    if (self.parent.geol_coll.get_uid_topology(current_uid_goal) != "PolyLine") and (
        self.parent.geol_coll.get_uid_topology(current_uid_goal) != "XsPolyLine"
    ):
        self.print_terminal(" -- Selected goal is not a line -- ")
        return
    tolerance = input_one_value_dialog(
        parent=self,
        title="Snap tolerance",
        label="Insert snap tolerance",
        default_value=10,
    )

    for current_uid_snap in self.selected_uids[:-1]:
        # print(current_uid_snap)
        if (
            self.parent.geol_coll.get_uid_topology(current_uid_snap) != "PolyLine"
        ) and (
            self.parent.geol_coll.get_uid_topology(current_uid_snap) != "XsPolyLine"
        ):
            self.print_terminal(" -- Selected snap is not a line -- ")
            return

        # Create empty dictionary for the output line.
        new_line_snap = deepcopy(self.parent.geol_coll.entity_dict)
        new_line_goal = deepcopy(self.parent.geol_coll.entity_dict)

        # Editing loop. Get coordinates of the line to be modified (snap-line).
        if isinstance(self, ViewMap):
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
        elif isinstance(self, ViewXsection):
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
        # Stack coordinates in two-columns matrix
        inUV_snap = np_column_stack((inU_snap, inV_snap))
        inUV_goal = np_column_stack((inU_goal, inV_goal))
        # Run the Shapely function.
        shp_line_in_snap = shp_linestring(inUV_snap)
        shp_line_in_goal = shp_linestring(inUV_goal)

        shp_line_in_goal, extended = int_node(shp_line_in_goal, shp_line_in_snap)
        # plt.plot(np_array(shp_line_in_goal.coords)[:, 0], np_array(shp_line_in_goal.coords)[:, 1], 'r-o')
        # plt.plot(np_array(extended.coords)[:, 0], np_array(extended.coords)[:, 1], 'b-o')
        # plt.show()

        # -----In the snapping tool, the last input value is called Tolerance. Can be modified, do some checks.
        # Little tolerance risks of not snapping distant lines, while too big tolerance snaps to the wrong vertex and
        # not to the nearest one----
        if shp_line_in_snap.is_simple and shp_line_in_goal.is_simple:
            shp_line_out_snap = shp_snap(shp_line_in_snap, shp_line_in_goal, tolerance)
        else:
            self.print_terminal("Polyline is not simple, it self-intersects")
            return
        shp_line_out_diff = shp_line_out_snap.difference(
            shp_line_in_goal
        )  # eliminate the shared path that Snap may create
        outUV_snap = deepcopy(np_array(shp_line_out_diff.coords))
        outUV_goal = deepcopy(np_array(shp_line_in_goal.coords))
        # Un-stack output coordinates and write them to the empty dictionary.
        if outUV_snap.ndim < 2:
            self.print_terminal("Invalid shape")
            continue
        outU_snap = outUV_snap[:, 0]
        outV_snap = outUV_snap[:, 1]
        outU_goal = outUV_goal[:, 0]
        outV_goal = outUV_goal[:, 1]
        # Convert local coordinates to XYZ ones.
        if isinstance(self, ViewMap):
            outX_snap = outU_snap
            outY_snap = outV_snap
            outZ_snap = np_zeros(np_shape(outX_snap))

            outX_goal = outU_goal
            outY_goal = outV_goal
            outZ_goal = np_zeros(np_shape(outX_goal))
        elif isinstance(self, ViewXsection):
            outX_snap, outY_snap, outZ_snap = self.parent.xsect_coll.plane2world(
                self.this_x_section_uid, outU_snap, outV_snap
            )
            outX_goal, outY_goal, outZ_goal = self.parent.xsect_coll.plane2world(
                self.this_x_section_uid, outU_goal, outV_goal
            )

            # outZ = outV
        # Create new vtk objects
        new_points_snap = np_column_stack((outX_snap, outY_snap, outZ_snap))
        new_points_goal = np_column_stack((outX_goal, outY_goal, outZ_goal))

        new_line_snap["vtk_obj"].points = new_points_snap
        new_line_snap["vtk_obj"].auto_cells()
        new_line_goal["vtk_obj"].points = new_points_goal
        new_line_goal["vtk_obj"].auto_cells()
        # Replace VTK object
        if new_line_snap["vtk_obj"].points_number > 0:
            self.parent.geol_coll.replace_vtk(
                uid=current_uid_snap, vtk_object=new_line_snap["vtk_obj"]
            )
            self.parent.geol_coll.replace_vtk(
                uid=current_uid_goal, vtk_object=new_line_goal["vtk_obj"]
            )
            del new_line_snap
            del new_line_goal
        else:
            print("Empty object")
        # Deselect input lines
    self.clear_selection()


@freeze_gui
def resample_lines_distance(self):
    """Resample selected line with constant specified spacing."""
    # Check if at least a line is selected.
    if not self.selected_uids:
        self.print_terminal(" -- No input data selected -- ")
        return
    # Input distance for evenly spacing resampling.
    distance_delta = input_one_value_dialog(
        parent=self,
        title="Spacing distance for Line Resampling",
        label="Insert spacing distance",
        default_value="Distance",
    )
    if any(
        [distance_delta is None, isinstance(distance_delta, str), distance_delta <= 0]
    ):
        self.print_terminal(" -- Distance is None -- ")
        return
    # distance_delta = int(distance_delta)
    for current_uid in self.selected_uids:
        if (self.parent.geol_coll.get_uid_topology(current_uid) != "PolyLine") and (
            self.parent.geol_coll.get_uid_topology(current_uid) != "XsPolyLine"
        ):
            self.print_terminal(" -- Selected data is not a line -- ")
            return
        # Create empty dictionary for the output line.
        new_line = deepcopy(self.parent.geol_coll.entity_dict)
        # Define topology and x_section. Get coordinates of input line.
        if isinstance(self, ViewMap):
            new_line["topology"] = "PolyLine"
            new_line["x_section"] = None
            inU = deepcopy(
                self.parent.geol_coll.get_uid_vtk_obj(current_uid).points[:, 0]
            )
            inV = deepcopy(
                self.parent.geol_coll.get_uid_vtk_obj(current_uid).points[:, 1]
            )
        elif isinstance(self, ViewXsection):
            new_line["topology"] = "XsPolyLine"
            new_line["x_section"] = self.this_x_section_uid
            inU, inV = self.parent.geol_coll.get_uid_vtk_obj(current_uid).world2plane()
        # Stack coordinates in two-columns matrix.
        inUV = np_column_stack((inU, inV))
        # Run the Shapely function.
        shp_line_in = shp_linestring(inUV)
        if distance_delta >= shp_line_in.length:
            while distance_delta >= shp_line_in.length:
                distance_delta = distance_delta / 2
        distances = np_arange(0, shp_line_in.length, distance_delta)
        points = [
            tuple(shp_line_in.interpolate(distance).coords[0]) for distance in distances
        ]
        points.append(tuple(shp_line_in.coords[-1]))
        shp_line_out = shp_linestring(points)
        outUV = deepcopy(np_array(shp_line_out.coords))
        # Un-stack output coordinates and write them to the empty dictionary.
        outU = outUV[:, 0]
        outV = outUV[:, 1]
        if isinstance(self, ViewMap):
            outX = outU
            outY = outV
            outZ = np_zeros(np_shape(outX))
            new_line["vtk_obj"] = PolyLine()
        elif isinstance(self, ViewXsection):
            outX, outY, outZ = self.parent.xsect_coll.plane2world(
                self.this_x_section_uid, outU, outV
            )
            new_line["vtk_obj"] = XsPolyLine(
                self.this_x_section_uid, parent=self.parent
            )
        outXYZ = np_column_stack((outX, outY, outZ))
        new_line["vtk_obj"].points = outXYZ
        new_line["vtk_obj"].auto_cells()
        # Replace VTK object.
        if new_line["vtk_obj"].points_number > 0:
            self.parent.geol_coll.replace_vtk(
                uid=current_uid, vtk_object=new_line["vtk_obj"]
            )
            del new_line
        else:
            self.print_terminal(" -- Empty object -- ")
        # Deselect input line and emit uid as list to force redraw.
        self.clear_selection()
        self.parent.signals.geom_modified.emit([current_uid], self.parent.geol_coll)
        self.print_terminal(
            f"Line {current_uid} resampled with distance = {distance_delta}"
        )


@freeze_gui
def resample_lines_number_points(
    self,
):  # this must be done per-part___________________________________________________
    """Resample selected line with constant spacing defined by a specified number of nodes."""
    # Check if at least a line is selected.
    if not self.selected_uids:
        self.print_terminal(" -- No input data selected -- ")
        return
    # Input the number of points for evenly spacing resampling.
    number_of_points = input_one_value_dialog(
        parent=self,
        title="Number of points for Line Resampling",
        label="Insert number of points",
        default_value="Number",
    )
    if any(
        [
            number_of_points is None,
            isinstance(number_of_points, str),
            number_of_points <= 1,
        ]
    ):
        self.print_terminal(" -- Number of nodes is None -- ")
        return
    else:
        number_of_points = int(number_of_points)
    for current_uid in self.selected_uids:
        if (self.parent.geol_coll.get_uid_topology(current_uid) != "PolyLine") and (
            self.parent.geol_coll.get_uid_topology(current_uid) != "XsPolyLine"
        ):
            self.print_terminal(" -- Selected data is not a line -- ")
            return
        # Create empty dictionary for the output line.
        new_line = deepcopy(self.parent.geol_coll.entity_dict)
        # Define topology and x_section. Get coordinates of input line.
        if isinstance(self, ViewMap):
            new_line["topology"] = "PolyLine"
            new_line["x_section"] = None
            inU = deepcopy(
                self.parent.geol_coll.get_uid_vtk_obj(current_uid).points[:, 0]
            )
            inV = deepcopy(
                self.parent.geol_coll.get_uid_vtk_obj(current_uid).points[:, 1]
            )
        elif isinstance(self, ViewXsection):
            new_line["topology"] = "XsPolyLine"
            new_line["x_section"] = self.this_x_section_uid
            inU, inV = self.parent.geol_coll.get_uid_vtk_obj(current_uid).world2plane()
        # Stack coordinates in two-columns matrix.
        inUV = np_column_stack((inU, inV))
        # Run the Shapely function.
        shp_line_in = shp_linestring(inUV)
        distances = (
            shp_line_in.length * i / (number_of_points - 1)
            for i in range(number_of_points)
        )
        points = [
            tuple(shp_line_in.interpolate(distance).coords[0]) for distance in distances
        ]
        points.append(tuple(shp_line_in.coords[-1]))
        shp_line_out = shp_linestring(points)
        outUV = deepcopy(np_array(shp_line_out.coords))
        # Un-stack output coordinates and write them to the empty dictionary.
        outU = outUV[:, 0]
        outV = outUV[:, 1]
        if isinstance(self, ViewMap):
            outX = outU
            outY = outV
            outZ = np_zeros(np_shape(outX))
            new_line["vtk_obj"] = PolyLine()
        elif isinstance(self, ViewXsection):
            outX, outY, outZ = self.parent.xsect_coll.plane2world(
                self.this_x_section_uid, outU, outV
            )
            new_line["vtk_obj"] = XsPolyLine(
                self.this_x_section_uid, parent=self.parent
            )
        outXYZ = np_column_stack((outX, outY, outZ))
        new_line["vtk_obj"].points = outXYZ
        new_line["vtk_obj"].auto_cells()
        # Replace VTK object.
        if new_line["vtk_obj"].points_number > 0:
            self.parent.geol_coll.replace_vtk(
                uid=current_uid, vtk_object=new_line["vtk_obj"]
            )
            del new_line
        else:
            self.print_terminal(" -- Empty object -- ")
        # Deselect input line and emit uid as list to force redraw.
        self.clear_selection()
        self.parent.geol_coll.signals.geom_modified.emit(
            [current_uid], self.parent.geol_coll
        )
        self.print_terminal(
            f"Line {current_uid} resampled with number of points = {number_of_points}"
        )


@freeze_gui
def simplify_line(self):
    """Return a simplified representation of the line. Permits the user to choose a value for the Tolerance parameter."""
    self.print_terminal(
        "Simplify line. Define tolerance value: "
        "small values result in more vertices and great similarity with the input line."
    )

    # Check if a line is selected
    if not self.selected_uids:
        self.print_terminal(" -- No input data selected -- ")
        return

    # Ask for the tolerance parameter
    tolerance_p = input_one_value_dialog(
        parent=self,
        title="Simplify - Tolerance",
        label="Insert tolerance parameter",
        default_value="0.1",
    )

    if tolerance_p is None:
        return
    if tolerance_p <= 0:
        tolerance_p = 0.1

    try:
        for current_uid in self.selected_uids:
            if (self.parent.geol_coll.get_uid_topology(current_uid) != "PolyLine") and (
                self.parent.geol_coll.get_uid_topology(current_uid) != "XsPolyLine"
            ):
                self.print_terminal(" -- Selected data is not a line -- ")
                continue

            
            vtk_obj = self.parent.geol_coll.get_uid_vtk_obj(current_uid)
            if vtk_obj is None or vtk_obj.points_number <= 0:
                self.print_terminal(f" --  Object not valid for {current_uid} -- ")
                continue

            # Editing loop. Create empty dictionary for the output line
            new_line = deepcopy(self.parent.geol_coll.entity_dict)

            # Get coordinates of input line.
            if isinstance(self, ViewMap):
                new_line["topology"] = "PolyLine"
                inU = vtk_obj.points_X
                inV = vtk_obj.points_Y
                new_line["vtk_obj"] = PolyLine()
            elif isinstance(self, ViewXsection):
                new_line["topology"] = "XsPolyLine"
                new_line["x_section"] = self.this_x_section_uid
                inU, inV = vtk_obj.world2plane()
                new_line["vtk_obj"] = XsPolyLine(
                    self.this_x_section_uid, parent=self.parent
                )

            # Stack coordinates in two-columns matrix
            inUV = np_column_stack((inU, inV))

            # Run the Shapely function.
            shp_line_in = shp_linestring(inUV)

            shp_line_out = shp_line_in.simplify(tolerance_p, preserve_topology=False)

            if shp_line_out.is_empty:
                self.print_terminal(f"Empty geometry {current_uid}")
                continue

            if len(shp_line_out.coords) == 0:
                self.print_terminal(f"No points in line {current_uid}")
                continue

            outUV = np_array(shp_line_out.coords)

            # Un-stack output coordinates and write them to the empty dictionary.
            outU = outUV[:, 0]
            outV = outUV[:, 1]

            if isinstance(self, ViewMap):
                outX = outU
                outY = outV
                outZ = np_zeros(np_shape(outX))
            elif isinstance(self, ViewXsection):
                outX, outY, outZ = self.parent.xsect_coll.plane2world(
                    self.this_x_section_uid, outU, outV
                )

            # Create new vtk
            new_points = np_column_stack((outX, outY, outZ))
            new_line["vtk_obj"].points = new_points
            new_line["vtk_obj"].auto_cells()

            # Replace VTK object
            if new_line["vtk_obj"].points_number > 0:
                self.parent.geol_coll.remove_entity(current_uid)
                self.parent.geol_coll.add_entity_from_dict(new_line)
                self.parent.signals.geom_modified.emit(
                    [current_uid], self.parent.geol_coll
                )
            else:
                self.print_terminal(
                    f"Empty geometry after parallel offset {current_uid}"
                )

    except Exception as e:
        self.print_terminal(f"Error: {str(e)}")

    # Deselect input line.
    self.clear_selection()


@freeze_gui
def copy_parallel(
    self,
):  # this must be done per-part_______________________________________________________
    """Parallel folding. Create a line copied and translated from a template line using Shapely.
    Since lines are oriented left-to-right and bottom-to-top, and here we copy a line to the left,
    a positive distance creates a line shifted upwards and to the left."""
    self.print_terminal("Copy Parallel. Create a line copied and translated.")
    # Terminate running event loops

    # Check if a line is selected"""
    if not self.selected_uids:
        self.print_terminal(" -- No input data selected -- ")
        return
    if (
        self.parent.geol_coll.get_uid_topology(self.selected_uids[0]) != "PolyLine"
    ) and (
        self.parent.geol_coll.get_uid_topology(self.selected_uids[0]) != "XsPolyLine"
    ):
        self.print_terminal(" -- Selected data is not a line -- ")
        return
    # If more than one line is selected, keep the first."""
    input_uid = self.selected_uids[0]
    # -----IN THE FUTURE add a test to check that the selected feature is a geological feature-----
    # Editing loop
    distance = input_one_value_dialog(
        parent=self,
        title="Line from template",
        label="Insert distance",
        default_value=100,
    )
    if distance is None:
        # Un-Freeze QT interface
        self.enable_actions()
        return

    in_line_name = self.parent.geol_coll.df.loc[
        self.parent.geol_coll.df["uid"] == input_uid, "name"
    ].values[0]
    out_line_name = in_line_name + "_para_" + "%d" % distance

    # Create empty dictionary for the output line and set name and role.
    # -----IN THE FUTURE see if other metadata should be automatically set.
    line_dict = deepcopy(self.parent.geol_coll.entity_dict)
    line_dict["name"] = out_line_name
    line_dict["role"] = self.parent.geol_coll.df.loc[
        self.parent.geol_coll.df["uid"] == input_uid, "role"
    ].values[0]
    line_dict["feature"] = self.parent.geol_coll.get_uid_feature(self.selected_uids[0])
    line_dict["scenario"] = self.parent.geol_coll.get_uid_scenario(
        self.selected_uids[0]
    )
    if isinstance(self, ViewMap):
        # if isinstance(self, (ViewMap, ViewMap)):
        inU = self.parent.geol_coll.get_uid_vtk_obj(input_uid).points_X
        inV = self.parent.geol_coll.get_uid_vtk_obj(input_uid).points_Y

        line_dict["vtk_obj"] = PolyLine()
        line_dict["topology"] = "PolyLine"
    # elif isinstance(self, (ViewXsection, ViewXsection)):
    elif isinstance(self, ViewXsection):
        inU, inV = self.parent.geol_coll.get_uid_vtk_obj(input_uid).world2plane()
        line_dict["vtk_obj"] = XsPolyLine(self.this_x_section_uid, parent=self.parent)
        line_dict["topology"] = "XsPolyLine"
        line_dict["x_section"] = self.this_x_section_uid

    inUV = np_column_stack((inU, inV))
    # Deselect input line.
    self.clear_selection()
    # self.parent.geol_coll.signals.geom_modified.emit([input_uid])  # emit uid as list to force redraw()
    # Run the Shapely function.
    shp_line_in = shp_linestring(inUV)
    # print(shp_line_in)
    # print("shp_line_in.parallel_offset")
    if shp_line_in.is_simple:
        shp_line_out = shp_line_in.parallel_offset(
            distance, "left", resolution=16, join_style=1
        )  # parallel folds are obtained with join_style=1

        outUV = np_array(shp_line_out.coords)
        # Un-stack output coordinates and write them to the empty dictionary.
        outU = outUV[:, 0]
        outV = outUV[:, 1]
    else:
        self.print_terminal("Polyline is not simple, it self-intersects")
        for action in self.findChildren(QAction):
            return
    if isinstance(self, ViewMap):
        # if isinstance(self, (ViewMap, ViewMap)):
        outX = outU
        outY = outV
        outZ = np_zeros(np_shape(outX))
    # elif isinstance(self, (ViewXsection, ViewXsection)):
    elif isinstance(self, ViewXsection):
        outX, outY, outZ = self.parent.xsect_coll.plane2world(
            self.this_x_section_uid, outU, outV
        )
    # Stack coordinates in two-columns matrix and write to vtk object.
    self.print_terminal("outXYZ = np_column_stack((outX, outY, outZ))")
    outXYZ = np_column_stack((outX, outY, outZ))

    line_dict["vtk_obj"].points = outXYZ
    line_dict["vtk_obj"].auto_cells()
    # Create entity from the dictionary and run left_right.
    if line_dict["vtk_obj"].points_number > 0:
        output_uid = self.parent.geol_coll.add_entity_from_dict(line_dict)
        left_right(output_uid)
    else:
        self.print_terminal("Empty object")


@freeze_gui
def copy_kink(self):
    """Kink folding. Create a line copied and translated from a template line using Shapely.
    Since lines are oriented left-to-right and bottom-to-top, and here we copy a line to the left,
    a positive distance creates a line shifted upwards and to the left."""
    self.print_terminal("Copy Kink. Create a line copied and translated.")

    # Check if a line is selected
    if not self.selected_uids:
        self.print_terminal(" -- No input data selected -- ")
        return
    if (
        self.parent.geol_coll.get_uid_topology(self.selected_uids[0]) != "PolyLine"
    ) and (
        self.parent.geol_coll.get_uid_topology(self.selected_uids[0]) != "XsPolyLine"
    ):
        self.print_terminal(" -- Selected data is not a line -- ")
        return

    # If more than one line is selected, keep the first.
    input_uid = self.selected_uids[0]

    vtk_obj = self.parent.geol_coll.get_uid_vtk_obj(input_uid)
    if vtk_obj is None or vtk_obj.points_number <= 0:
        self.print_terminal(" -- Oggetto VTK non valido -- ")
        return

    # Editing loop.
    distance = input_one_value_dialog(
        parent=self,
        title="Line from template",
        label="Insert distance",
        default_value=100,
    )
    if distance is None:
        return

    in_line_name = self.parent.geol_coll.df.loc[
        self.parent.geol_coll.df["uid"] == input_uid, "name"
    ].values[0]
    out_line_name = in_line_name + "_kink_" + "%d" % distance

    # Create empty dictionary for the output line and set name and role.
    line_dict = deepcopy(self.parent.geol_coll.entity_dict)
    line_dict["name"] = out_line_name
    line_dict["role"] = self.parent.geol_coll.df.loc[
        self.parent.geol_coll.df["uid"] == input_uid, "role"
    ].values[0]
    line_dict["feature"] = self.parent.geol_coll.get_uid_feature(self.selected_uids[0])
    line_dict["scenario"] = self.parent.geol_coll.get_uid_scenario(
        self.selected_uids[0]
    )

    try:
        if isinstance(self, ViewMap):
            line_dict["vtk_obj"] = PolyLine()
            line_dict["topology"] = "PolyLine"
            inU = vtk_obj.points_X
            inV = vtk_obj.points_Y
        elif isinstance(self, ViewXsection):
            line_dict["vtk_obj"] = XsPolyLine(
                self.this_x_section_uid, parent=self.parent
            )
            line_dict["topology"] = "XsPolyLine"
            line_dict["x_section"] = self.this_x_section_uid
            inU, inV = vtk_obj.world2plane()

        # Stack coordinates in two-columns matrix
        inUV = np_column_stack((inU, inV))

        # Deselect input line.
        self.clear_selection()
        self.parent.signals.geom_modified.emit([input_uid], self.parent.geol_coll)

        # Run the Shapely function.
        shp_line_in = shp_linestring(inUV)
        if not shp_line_in.is_simple:
            self.print_terminal("Polyline is not simple, it self-intersects")
            return

        shp_line_out = shp_line_in.parallel_offset(
            distance, "left", resolution=16, join_style=2, mitre_limit=10.0
        )  # kink folds are obtained with join_style=2, mitre_limit=10.0

        if shp_line_out.is_empty:
            self.print_terminal("Empty geometry after parallel offset")
            return

        outUV = np_array(shp_line_out.coords)
        outU = outUV[:, 0]
        outV = outUV[:, 1]

        if isinstance(self, ViewMap):
            outX = outU
            outY = outV
            outZ = np_zeros(np_shape(outX))
        elif isinstance(self, ViewXsection):
            outX, outY, outZ = self.parent.xsect_coll.plane2world(
                self.this_x_section_uid, outU, outV
            )

        # Stack coordinates in two-columns matrix and write to vtk object.
        outXYZ = np_column_stack((outX, outY, outZ))
        line_dict["vtk_obj"].points = outXYZ
        line_dict["vtk_obj"].auto_cells()

        # Create entity from the dictionary and run left_right.
        if line_dict["vtk_obj"].points_number > 0:
            output_uid = self.parent.geol_coll.add_entity_from_dict(line_dict)
            left_right(output_uid)
        else:
            self.print_terminal("Empty object")

    except Exception as e:
        self.print_terminal(f"Error: {str(e)}")


@freeze_gui
def copy_similar(
    self, vector
):  # this must be done per-part_______________________________________________________
    """Similar folding. Create a line copied and translated from a template line.
    Does not need U,V coordinates since the translation vector is already in world coords
    """
    self.print_terminal("Copy Similar. Create a line copied and translated.")
    # Terminate running event loops
    # self.stop_event_loops()
    # Check if a line is selected
    if not self.selected_uids:
        self.print_terminal(" -- No input data selected -- ")
        return
    if (
        self.parent.geol_coll.get_uid_topology(self.selected_uids[0]) != "PolyLine"
    ) and (
        self.parent.geol_coll.get_uid_topology(self.selected_uids[0]) != "XsPolyLine"
    ):
        self.print_terminal(" -- Selected data is not a line -- ")
        return
    # If more than one line is selected, keep the first.
    input_uid = self.selected_uids[0]
    # ----IN THE FUTURE add a test to check that the selected feature is a geological feature
    # Create empty dictionary for the output line and set name and role.
    # IN THE FUTURE see if other metadata should be automatically set.
    line_dict = deepcopy(self.parent.geol_coll.entity_dict)
    line_dict["role"] = self.parent.geol_coll.df.loc[
        self.parent.geol_coll.df["uid"] == input_uid, "role"
    ].values[0]
    line_dict["feature"] = self.parent.geol_coll.get_uid_feature(self.selected_uids[0])
    line_dict["scenario"] = self.parent.geol_coll.get_uid_scenario(
        self.selected_uids[0]
    )
    if isinstance(self, ViewMap):
        line_dict["vtk_obj"] = PolyLine()
        line_dict["topology"] = "PolyLine"
    elif isinstance(self, ViewXsection):
        line_dict["vtk_obj"] = XsPolyLine(self.this_x_section_uid, parent=self.parent)
        line_dict["topology"] = "XsPolyLine"
        line_dict["x_section"] = self.this_x_section_uid
    # Get coordinates of input line.
    inX = self.parent.geol_coll.get_uid_vtk_obj(input_uid).points_X
    inY = self.parent.geol_coll.get_uid_vtk_obj(input_uid).points_Y
    inZ = self.parent.geol_coll.get_uid_vtk_obj(input_uid).points_Z
    # Get similar folding vector.
    if vector.length == 0:
        self.print_terminal("Zero-length vector")
        return

    # Create output line.
    outX = inX + vector.deltas[0]
    outY = inY + vector.deltas[1]
    outZ = inZ + vector.deltas[2]
    # Stack coordinates in two-columns matrix and write to vtk object.
    outXYZ = np_column_stack((outX, outY, outZ))
    line_dict["vtk_obj"].points = outXYZ
    line_dict["vtk_obj"].auto_cells()
    # Set output line name.
    in_line_name = self.parent.geol_coll.df.loc[
        self.parent.geol_coll.df["uid"] == input_uid, "name"
    ].values[0]
    distance = vector.length
    out_line_name = f"{in_line_name}_simi_{round(distance, 2)}"

    line_dict["name"] = out_line_name
    # Create entity from the dictionary and run left_right.
    output_uid = self.parent.geol_coll.add_entity_from_dict(line_dict)
    left_right(output_uid)
    # Deselect input line.
    if line_dict["vtk_obj"].points_number > 0:
        self.clear_selection()
        # self.parent.geol_coll.signals.geom_modified.emit([input_uid])  # emit uid as list to force redraw()
    else:
        self.print_terminal("Empty object")


def measure_distance(self, vector):
    """Tool to measure distance between two points. Draw a vector_by_mouse and obtain length and azimuth"""
    self.print_terminal(
        "Measure Distance between two points by drawing a vector by mouse"
    )

    def end_measure(event=None):
        """Cleanup function to properly end the measurement tool"""
        self.enable_actions()
        if hasattr(self, "plotter"):
            self.plotter.untrack_click_position(side="right")

    self.disable_actions()

    if vector.length == 0:
        self.print_terminal("Zero-length vector")
        end_measure()
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

    dialog = message_dialog(title="Measure Distance", message=message)

    if hasattr(dialog, "finished"):
        dialog.finished.connect(end_measure)
    else:
        end_measure()


def flip_line(self, uid=None):
    """Flip points array top to bottom in order to reverse the line order."""
    # self.parent.geol_coll.get_uid_vtk_obj(uid).points = np_flip(self.parent.geol_coll.get_uid_vtk_obj(uid).points, 0)
    self.parent.geol_coll.get_uid_vtk_obj(uid).points = np_flipud(
        self.parent.geol_coll.get_uid_vtk_obj(uid).points
    )


def left_right(self, uid=None):
    """Ensures lines are oriented left-to-right and bottom-to-top in map or cross-section"""
    if isinstance(self, ViewMap):
        # if isinstance(self, ViewMap):
        U_line = self.parent.geol_coll.get_uid_vtk_obj(uid).points_X
        V_line = self.parent.geol_coll.get_uid_vtk_obj(uid).points_Y
    # elif isinstance(self, ViewXsection):
    elif isinstance(self, ViewXsection):
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
        split_lines1 = shp_split(line1, line2)
        outcoords1 = [list(i.coords) for i in split_lines1.geoms]

        new_line = shp_linestring([i for sublist in outcoords1 for i in sublist])
        extended_line = line2

    else:
        if len(line2.coords) == 2:
            scaled_segment1 = shp_scale(
                line2, xfact=fac, yfact=fac, origin=line2.boundary[0]
            )
            scaled_segment2 = shp_scale(
                scaled_segment1,
                xfact=fac,
                yfact=fac,
                origin=scaled_segment1.boundary[1],
            )
            extended_line = shp_linestring(scaled_segment2)
        elif len(line2.coords) == 3:
            first_seg = shp_linestring(line2.coords[:2])
            last_seg = shp_linestring(line2.coords[-2:])
            scaled_first_segment = shp_scale(
                first_seg, xfact=fac, yfact=fac, origin=first_seg.boundary[1]
            )
            scaled_last_segment = shp_scale(
                last_seg, xfact=fac, yfact=fac, origin=last_seg.boundary[0]
            )
            extended_line = shp_linestring(
                [*scaled_first_segment.coords, *scaled_last_segment.coords]
            )
        else:
            first_seg = shp_linestring(line2.coords[:2])
            last_seg = shp_linestring(line2.coords[-2:])

            scaled_first_segment = shp_scale(
                first_seg, xfact=fac, yfact=fac, origin=first_seg.boundary[1]
            )
            scaled_last_segment = shp_scale(
                last_seg, xfact=fac, yfact=fac, origin=last_seg.boundary[0]
            )
            extended_line = shp_linestring(
                [
                    *scaled_first_segment.coords,
                    *line2.coords[2:-2],
                    *scaled_last_segment.coords,
                ]
            )

        split_lines = shp_split(line1, extended_line)

        outcoords = [list(i.coords) for i in split_lines.geoms]
        new_line = shp_linestring([i for sublist in outcoords for i in sublist])

    return new_line, extended_line


def clean_intersection(self):
    """
    Clean intersections for a given line. The "search radius" is a buffer applied to the selected line to snap lines
    at a given distance from the selected line
    """
    data = []
    if isinstance(self, ViewMap):
        for i, line in self.parent.geol_coll.df.loc[
            self.parent.geol_coll.df["topology"] == "PolyLine"
        ].iterrows():
            vtkgeom = line["vtk_obj"]
            uid = line["uid"]
            geom = shp_linestring(vtkgeom.points[:, :2])
            data.append({"uid": uid, "geometry": geom})
    elif isinstance(self, ViewXsection):
        for i, line in self.parent.geol_coll.df.loc[
            self.parent.geol_coll.df["topology"] == "XsPolyLine"
        ].iterrows():
            vtkgeom = line["vtk_obj"]
            uid = line["uid"]
            inU, inV = vtkgeom.world2plane()
            inUV = np_column_stack((inU, inV))
            geom = shp_linestring(inUV)
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
