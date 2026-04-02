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
    input_combo_dialog,
    multiple_input_dialog,
    input_one_value_dialog,
    message_dialog,
)
from .helpers.helper_widgets import Editor, Tracer, Tracer3D
from .helpers.helper_functions import freeze_gui_onoff, freeze_gui_on, freeze_gui_off
from .entities_factory import PolyLine, XsPolyLine

from .views.view_map import ViewMap; from .views.view_xsection import ViewXsection


def _choose_draw_line_collection(self):
    collection_map = {
        "Geology": self.parent.geol_coll,
        "Fluid contacts": self.parent.fluid_coll,
        "Background data": self.parent.backgrnd_coll,
    }
    selected_collection = input_combo_dialog(
        parent=self,
        title="Line destination",
        label="Choose destination collection",
        choice_list=list(collection_map.keys()),
    )
    if selected_collection is None:
        return None
    return collection_map[selected_collection]


@freeze_gui_on
def draw_line(self):
    def end_digitize(event, input_dict):
        # Signal called to end the digitization of a trace. It returns a new polydata
        self.plotter.untrack_click_position()
        traced_pld = (
            tracer.GetContourRepresentation().GetContourRepresentationAsPolyData()
        )
        if traced_pld.GetNumberOfPoints() > 0:
            input_dict["vtk_obj"].ShallowCopy(traced_pld)
            source_coll.add_entity_from_dict(input_dict)
        tracer.EnabledOff()
        # self.enable_actions()
        freeze_gui_off(self)

    # self.disable_actions()
    source_coll = _choose_draw_line_collection(self)
    if source_coll is None:
        freeze_gui_off(self)
        return

    # Create deepcopy of the selected collection entity dictionary.
    line_dict = deepcopy(source_coll.entity_dict)
    feature_list = source_coll.legend_df["feature"].tolist()
    if not feature_list:
        feature_list = [line_dict["feature"]]
    scenario_list = list(set(source_coll.legend_df["scenario"].tolist()))
    if not scenario_list:
        scenario_list = [line_dict["scenario"]]
    # One dictionary is set as input for a general widget of multiple-value-input"""
    line_dict_in = {
        "name": ["PolyLine name: ", "new_pline"],
        "role": [
            "Role: ",
            source_coll.valid_roles,
        ],
        "feature": [
            "Feature: ",
            feature_list,
        ],
        "scenario": [
            "Scenario: ",
            scenario_list,
        ],
    }
    line_dict_updt = multiple_input_dialog(
        title="Digitize new PolyLine", input_dict=line_dict_in
    )
    # Check if the output of the widget is empty or not. If the Cancel button was clicked, the tool quits
    if line_dict_updt is None:
        # self.enable_actions()
        freeze_gui_off(self)
        return
    # Getting the values that have been typed by the user through the widget
    for key in line_dict_updt:
        line_dict[key] = line_dict_updt[key]
    if isinstance(self, ViewMap):
        line_dict["topology"] = "PolyLine"
        line_dict["parent_uid"] = ""
        line_dict["vtk_obj"] = PolyLine()
    elif isinstance(self, ViewXsection):
        line_dict["topology"] = "XsPolyLine"
        line_dict["parent_uid"] = self.this_x_section_uid
        line_dict["vtk_obj"] = XsPolyLine(
            x_section_uid=self.this_x_section_uid, parent=self.parent
        )
    # elif isinstance(self, View3D):
    #     line_dict["topology"] = "PolyLine"
    #     line_dict["parent_uid"] = ""
    #     line_dict["vtk_obj"] = PolyLine()
    tracer = Tracer(self)
    tracer.EnabledOn()
    self.plotter.track_click_position(
        side="right", callback=lambda event: end_digitize(event, line_dict)
    )


@freeze_gui_on
def draw_line_3d(self):
    """Draw a line in 3D using point clicking. Only works on surfaces.
    
    Usage:
    - Left-click on surfaces to add points
    - Right-click to finish drawing
    - Clicking in void space will not add points
    """
    import numpy as np
    from vtkmodules.vtkRenderingCore import vtkCellPicker

    def _get_vertical_exaggeration():
        """Return current Z scale used in the 3D view (fallback to 1.0)."""
        v_exag = 1.0
        try:
            if hasattr(self, "v_exaggeration") and self.v_exaggeration not in [None, 0]:
                v_exag = float(self.v_exaggeration)
            elif (
                hasattr(self, "plotter")
                and getattr(self.plotter, "scale", None) is not None
                and len(self.plotter.scale) >= 3
                and self.plotter.scale[2] not in [None, 0]
            ):
                v_exag = float(self.plotter.scale[2])
        except Exception:
            v_exag = 1.0
        return v_exag if np.isfinite(v_exag) and v_exag != 0 else 1.0
    
    def on_left_click(obj, event):
        """Handle left-click to add point only if clicking on a surface.
        
        Args:
            obj: The VTK interactor object
            event: The VTK event object containing click information
        """
        if not tracer_3d.is_active:
            return
        
        # Get the event position from the interactor
        pos = obj.GetEventPosition()
        
        # Create a cell picker to check if we hit a surface
        picker = vtkCellPicker()
        picker.SetTolerance(0.01)
        
        # Try to pick an actor at the click position
        style = obj.GetInteractorStyle()
        style.SetDefaultRenderer(self.plotter.renderer)
        picker_output = picker.Pick(pos[0], pos[1], 0, style.GetDefaultRenderer())
        
        # Check if we hit a surface (actor)
        if picker_output and picker.GetActor():
            # Get the intersection point on the surface
            picked_position = picker.GetPickPosition()
            
            try:
                # Convert to list if needed
                if isinstance(picked_position, (tuple, list, np.ndarray)):
                    point = list(picked_position) if not isinstance(picked_position, list) else picked_position
                    if len(point) == 3:
                        # Picker returns coordinates in rendered/scaled space.
                        # Convert Z back to model space so the saved line respects vertical exaggeration.
                        v_exag = _get_vertical_exaggeration()
                        if v_exag != 1.0:
                            point[2] = point[2] / v_exag
                        tracer_3d.add_point(point)
                        self.print_terminal(f"✓ Point {len(tracer_3d.points)} added at ({point[0]:.2f}, {point[1]:.2f}, {point[2]:.2f})")
                    else:
                        self.print_terminal(f"ERROR: Point has {len(point)} coordinates, expected 3")
                else:
                    self.print_terminal(f"ERROR: picked_position is not a valid type: {type(picked_position)}")
            except Exception as e:
                self.print_terminal(f"ERROR adding point: {e}")
        else:
            # No surface was hit - inform user
            self.print_terminal("No surface detected at click position. Click on a surface to add points.")
    
    # Store observer tags for cleanup
    observer_tags = {}
    
    def on_right_click(obj, event):
        """Handle right-click to finish drawing."""
        if not tracer_3d.is_active:
            freeze_gui_off(self)
            return
        
        # Remove event observers using stored tags
        if "left" in observer_tags:
            self.plotter.iren.interactor.RemoveObserver(observer_tags["left"])
        if "right" in observer_tags:
            self.plotter.iren.interactor.RemoveObserver(observer_tags["right"])
        
        # Check if we have enough points
        if len(tracer_3d.points) < 2:
            self.print_terminal("Need at least 2 points to create a line")
            tracer_3d.disable()
            # self.enable_actions()
            freeze_gui_off(self)
            return
        
        # Get the polydata from the tracer
        traced_pld = tracer_3d.get_polydata()
        
        if traced_pld and traced_pld.GetNumberOfPoints() > 0:
            line_dict["vtk_obj"].ShallowCopy(traced_pld)
            source_coll.add_entity_from_dict(line_dict)
            self.print_terminal(f"✓ Created line with {len(tracer_3d.points)} points")
        
        # Clean up
        tracer_3d.disable()
        # self.enable_actions()
        freeze_gui_off(self)
    
    # self.disable_actions()

    source_coll = _choose_draw_line_collection(self)
    if source_coll is None:
        freeze_gui_off(self)
        return

    # Create deepcopy of the selected collection entity dictionary
    line_dict = deepcopy(source_coll.entity_dict)
    feature_list = source_coll.legend_df["feature"].tolist()
    if not feature_list:
        feature_list = [line_dict["feature"]]
    scenario_list = list(set(source_coll.legend_df["scenario"].tolist()))
    if not scenario_list:
        scenario_list = [line_dict["scenario"]]

    # One dictionary is set as input for a general widget of multiple-value-input
    line_dict_in = {
        "name": ["PolyLine name: ", "new_pline"],
        "role": [
            "Role: ",
            source_coll.valid_roles,
        ],
        "feature": [
            "Feature: ",
            feature_list,
        ],
        "scenario": [
            "Scenario: ",
            scenario_list,
        ],
    }
    
    line_dict_updt = multiple_input_dialog(
        title="Digitize new 3D PolyLine", input_dict=line_dict_in
    )
    
    # Check if the output of the widget is empty or not
    if line_dict_updt is None:
        # self.enable_actions()
        freeze_gui_off(self)
        return
    
    # Getting the values that have been typed by the user through the widget
    for key in line_dict_updt:
        line_dict[key] = line_dict_updt[key]
    
    line_dict["topology"] = "PolyLine"
    line_dict["vtk_obj"] = PolyLine()
    
    # Create and enable the 3D tracer
    tracer_3d = Tracer3D(self)
    tracer_3d.enable()
    
    # Set up click handlers using VTK event observers for surface picking
    observer_tags["left"] = self.plotter.iren.interactor.AddObserver("LeftButtonPressEvent", on_left_click)
    observer_tags["right"] = self.plotter.iren.interactor.AddObserver("RightButtonPressEvent", on_right_click)
    
    self.print_terminal("3D Line Drawing: Left-click on surfaces to add points, Right-click to finish")

def _get_editable_line_source_coll(self, selected_uids=None, min_selected=1):
    valid_tables = {
        "tabGeology": "geol_coll",
        "tabFluids": "fluid_coll",
        "tabBackgrounds": "backgrnd_coll",
    }
    if self.parent.shown_table not in valid_tables:
        self.print_terminal(
            " -- Move Line is supported only for geology, fluids, and backgrounds -- "
        )
        return None

    source_coll = getattr(self.parent, valid_tables[self.parent.shown_table])
    if selected_uids is None:
        selected_uids = self.selected_uids

    if not selected_uids:
        self.print_terminal(" -- No input data selected -- ")
        return None
    if len(selected_uids) < min_selected:
        self.print_terminal(
            f" -- Not enough input data selected. Select at least {min_selected} objects -- "
        )
        return None

    for current_uid in selected_uids:
        if (source_coll.get_uid_topology(current_uid) != "PolyLine") and (
            source_coll.get_uid_topology(current_uid) != "XsPolyLine"
        ):
            self.print_terminal(f" -- Selected data {current_uid} is not a line -- ")
            return None
    return source_coll


def start_checked_line_tool(self, tool_func, selected_uids=None, min_selected=1):
    """Validate line selection before starting a line editing tool."""
    if (
        _get_editable_line_source_coll(
            self, selected_uids=selected_uids, min_selected=min_selected
        )
        is None
    ):
        return
    tool_func(self)
    
@freeze_gui_on
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
        # elif isinstance(self, View3D):
        #     vtk_obj = PolyLine()
        vtk_obj.ShallowCopy(traced_pld)
        source_coll.replace_vtk(uid=uid, vtk_object=vtk_obj)
        editor.EnabledOff()
        self.clear_selection()
        freeze_gui_off(self)

    source_coll = _get_editable_line_source_coll(
        self, selected_uids=self.selected_uids[:1]
    )
    if source_coll is None:
        freeze_gui_off(self)
        return
    # self.disable_actions()
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


@freeze_gui_onoff
def sort_line_nodes(self):
    """Sort line nodes."""
    source_coll = _get_editable_line_source_coll(self)
    if source_coll is None:
        return

    self.print_terminal("Sort line nodes according to cell order.")
    # """Terminate running event loops"""
    # self.stop_event_loops()
    # for action in self.findChildren(QAction):
    #     if isinstance(action.parentWidget(), NavigationToolbar) is False:
    #         action.setDisabled(True)
    # If more than one line is selected, keep the first.
    for current_uid in self.selected_uids:
        # For some reason in the following the [:] is needed.
        source_coll.get_uid_vtk_obj(
            current_uid
        ).sort_nodes()  # this could be probably done per-part__________________________
        # Deselect input line.
        self.parent.signals.geom_modified.emit([current_uid], source_coll)
        # for action in self.findChildren(QAction):
        #     action.setEnabled(True)
    # Deselect input line.
    self.clear_selection()





def move_line(self, vector):
    """Move the whole line by rigid-body translation.
    Here transformation to UV is not necessary since the translation vector is already in world space
    """
    # It should block the function before to activate the vector
    if self.selected_uids == []:
        self.print_terminal(" -- No input data selected -- ")
        freeze_gui_off(self)
        return

    self.print_terminal("Move Line. Move the whole line by rigid-body translation.")
    if vector.length == 0:
        self.print_terminal("Zero-length vector")
        freeze_gui_off(self)
        return

    source_coll = _get_editable_line_source_coll(self)
    if source_coll is None:
        freeze_gui_off(self)
        return

    for current_uid in self.selected_uids:

        # Editing loop.
        # -----For some reason in the following the [:] is needed.-----
        x = source_coll.get_uid_vtk_obj(current_uid).points_X[:] + vector.deltas[0]
        y = source_coll.get_uid_vtk_obj(current_uid).points_Y[:] + vector.deltas[1]
        z = source_coll.get_uid_vtk_obj(current_uid).points_Z[:] + vector.deltas[2]

        points = np_stack((x, y, z), axis=1)
        source_coll.get_uid_vtk_obj(current_uid).points = points
        left_right(self, uid=current_uid, source_coll=source_coll)
        # Deselect input line.
        self.parent.signals.geom_modified.emit([current_uid], source_coll)
    # Deselect input line.
    self.clear_selection()
    freeze_gui_off(self)


@freeze_gui_onoff
def rotate_line(self):
    """Rotate lines by rigid-body rotation using Shapely."""
    source_coll = _get_editable_line_source_coll(self)
    if source_coll is None:
        return

    self.print_terminal(
        "Rotate Line. Rotate the whole line by rigid-body rotation. Please insert angle of anticlockwise rotation."
    )
    # Input rotation angle. None exits the function.
    angle = input_one_value_dialog(
        parent=self,
        title="Rotate Line",
        label="Insert rotation angle in degrees, anticlockwise",
        default_value=10,
    )
    if angle is None:
        self.print_terminal(" -- Angle is None -- ")
        return
    for current_uid in self.selected_uids:
        if isinstance(self, ViewMap):
            inU = source_coll.get_uid_vtk_obj(current_uid).points_X
            inV = source_coll.get_uid_vtk_obj(current_uid).points_Y
        elif isinstance(self, ViewXsection):
            in_vtk_obj = source_coll.get_uid_vtk_obj(current_uid)
            inU, inV = self.parent.xsect_coll.world2plane(
                section_uid=self.this_x_section_uid,
                X=in_vtk_obj.points_X,
                Y=in_vtk_obj.points_Y,
                Z=in_vtk_obj.points_Z,
            )
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
            outZ = source_coll.get_uid_vtk_obj(current_uid).points_Z
        elif isinstance(self, ViewXsection):
            outX, outY, outZ = self.parent.xsect_coll.plane2world(
                self.this_x_section_uid, outU, outV
            )
        outXYZ = np_column_stack((outX, outY, outZ))
        source_coll.get_uid_vtk_obj(current_uid).points = outXYZ
        left_right(self, uid=current_uid, source_coll=source_coll)
        # emit uid as list to force redraw()
        self.parent.signals.geom_modified.emit([current_uid], source_coll)
    # Deselect input line.
    self.clear_selection()


@freeze_gui_on
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
        # elif isinstance(self, View3D):
        #         vtk_obj = PolyLine()
        vtk_obj.ShallowCopy(traced_pld)

        source_coll.replace_vtk(uid=uid, vtk_object=vtk_obj)
        extender.EnabledOff()
        self.clear_selection()
        freeze_gui_off(self)

    # Extend selected line.
    self.print_terminal("Extend Line. Press 'k' to change end of line to extend.")
    """Terminate running event loops"""
    # self.stop_event_loops()
    # Check if a line is selected
    if not self.selected_uids:
        self.print_terminal(" -- No input data selected -- ")
        freeze_gui_off(self)
        return
    source_coll = _get_editable_line_source_coll(
        self, selected_uids=self.selected_uids[:1]
    )
    if source_coll is None:
        freeze_gui_off(self)
        return
    # If more than one line is selected, keep the first
    sel_uid = self.selected_uids[0]
    current_line = self.get_actor_by_uid(sel_uid).GetMapper().GetInput()

    extender = Editor(self)
    extender.EnabledOn()
    extender.initialize(current_line, "extend")

    self.plotter.track_click_position(
        side="right", callback=lambda event: end_edit(event, sel_uid)
    )


@freeze_gui_onoff
def split_line_line(self):
    """Split line (paper) with another line (scissors). First, select the paper-line then the scissors-line"""
    # print("Split line with line. Line to be split has been selected, please select an intersecting line.")   #Reviw needed
    # Terminate running event loops
    source_coll = _get_editable_line_source_coll(self, min_selected=2)
    if source_coll is None:
        return

    current_uid_scissors = self.selected_uids[-1]
    if isinstance(self, ViewMap):
        inU = source_coll.get_uid_vtk_obj(current_uid_scissors).points_X
        inV = source_coll.get_uid_vtk_obj(current_uid_scissors).points_Y
    elif isinstance(self, ViewXsection):
        in_vtk_obj = source_coll.get_uid_vtk_obj(current_uid_scissors)
        inU, inV = self.parent.xsect_coll.world2plane(
            section_uid=self.this_x_section_uid,
            X=in_vtk_obj.points_X,
            Y=in_vtk_obj.points_Y,
            Z=in_vtk_obj.points_Z,
        )

    inUV_scissors = np_column_stack((inU, inV))
    shp_line_in_scissors = shp_linestring(inUV_scissors)

    for current_uid_paper in self.selected_uids[:-1]:
        if isinstance(self, ViewMap):
            inU = source_coll.get_uid_vtk_obj(current_uid_paper).points_X
            inV = source_coll.get_uid_vtk_obj(current_uid_paper).points_Y
        elif isinstance(self, ViewXsection):
            in_vtk_obj = source_coll.get_uid_vtk_obj(current_uid_paper)
            inU, inV = self.parent.xsect_coll.world2plane(
                section_uid=self.this_x_section_uid,
                X=in_vtk_obj.points_X,
                Y=in_vtk_obj.points_Y,
                Z=in_vtk_obj.points_Z,
            )
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
        # Run split. If lines do not strictly cross, extend splitter to catch touch/T intersections.
        paper_to_split = shp_line_in_paper
        splitter = shp_line_in_scissors
        if not shp_line_in_paper.crosses(shp_line_in_scissors):
            paper_to_split, splitter = int_node(shp_line_in_paper, shp_line_in_scissors)
        if not paper_to_split.intersects(splitter):
            self.print_terminal(
                f" -- Paper line {current_uid_paper} does not intersect scissor line {current_uid_scissors} -- "
            )
            self.clear_selection()
            return
        split_lines = shp_split(paper_to_split, splitter)
        if len(split_lines.geoms) < 2:
            self.print_terminal(
                f" -- Scissor line {current_uid_scissors} does not split paper line {current_uid_paper} -- "
            )
            self.clear_selection()
            return
        replace = 1  # replace = 1 for the first line to operate replace_vtk
        uids = [current_uid_scissors]
        for line in split_lines.geoms:
            # Create empty dictionary for the output lines.
            new_line = deepcopy(source_coll.entity_dict)
            new_line["name"] = (
                source_coll.df.loc[source_coll.df["uid"] == current_uid_paper, "name"].values[0]
                + "_split"
            )
            new_line["topology"] = source_coll.df.loc[
                source_coll.df["uid"] == current_uid_paper, "topology"
            ].values[0]
            new_line["role"] = source_coll.df.loc[
                source_coll.df["uid"] == current_uid_paper, "role"
            ].values[0]
            new_line["feature"] = source_coll.df.loc[
                source_coll.df["uid"] == current_uid_paper, "feature"
            ].values[0]
            new_line["scenario"] = source_coll.df.loc[
                source_coll.df["uid"] == current_uid_paper, "scenario"
            ].values[0]
            outU = np_array(line.coords)[:, 0]
            outV = np_array(line.coords)[:, 1]
            if isinstance(self, ViewMap):
                new_line["parent_uid"] = None
                new_line["vtk_obj"] = PolyLine()
                outX = outU
                outY = outV
                outZ = np_zeros(np_shape(outX))

            elif isinstance(self, ViewXsection):
                new_line["parent_uid"] = self.this_x_section_uid
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
                    source_coll.replace_vtk(uid=current_uid_paper, vtk_object=new_line["vtk_obj"])
                    self.parent.signals.geom_modified.emit([current_uid_paper], source_coll)
                    replace = 0
                    uids.append(current_uid_paper)
                else:
                    # Create entity from the dictionary
                    uid = source_coll.add_entity_from_dict(new_line)
                    uids.append(uid)
                del new_line["vtk_obj"]
            else:
                self.print_terminal(f" -- Split generated an empty object for {current_uid_paper} -- ")
        # Deselect input line and force redraw

        # self.parent.signals.geom_modified.emit(uids)  # emit uid as list to force redraw()
    # Deselect input line.
    self.clear_selection()



@freeze_gui_onoff
def split_line_existing_point(self):
    # Split line at picked point in 2D work coordinates (map XY or xsection UV).
    def end_select(event, uid):
        point_pos = selector.active_pos
        self.plotter.untrack_click_position(side="right")
        # Create empty dictionary for the output lines
        new_line_1 = deepcopy(source_coll.entity_dict)
        new_line_2 = deepcopy(source_coll.entity_dict)
        new_line_2["name"] = (
            source_coll.df.loc[source_coll.df["uid"] == uid, "name"].values[0]
            + "_split"
        )
        new_line_2["topology"] = source_coll.df.loc[
            source_coll.df["uid"] == uid, "topology"
        ].values[0]
        new_line_2["role"] = source_coll.df.loc[
            source_coll.df["uid"] == uid, "role"
        ].values[0]
        new_line_2["feature"] = source_coll.df.loc[
            source_coll.df["uid"] == uid, "feature"
        ].values[0]
        new_line_2["scenario"] = source_coll.df.loc[
            source_coll.df["uid"] == uid, "scenario"
        ].values[0]

        vtk_obj = source_coll.get_uid_vtk_obj(uid)

        if isinstance(self, ViewMap):
            inU_line = deepcopy(vtk_obj.points_X)
            inV_line = deepcopy(vtk_obj.points_Y)
            point_u = point_pos[0]
            point_v = point_pos[1]
        elif isinstance(self, ViewXsection):
            inU_line, inV_line = self.parent.xsect_coll.world2plane(
                section_uid=self.this_x_section_uid,
                X=vtk_obj.points_X,
                Y=vtk_obj.points_Y,
                Z=vtk_obj.points_Z,
            )
            point_u, point_v = self.parent.xsect_coll.world2plane(
                section_uid=self.this_x_section_uid,
                X=[point_pos[0]],
                Y=[point_pos[1]],
                Z=[point_pos[2]],
            )
            point_u = float(point_u[0])
            point_v = float(point_v[0])
            new_line_2["parent_uid"] = self.this_x_section_uid

        inUV_line = np_column_stack((inU_line, inV_line))
        if inUV_line.shape[0] < 3:
            self.print_terminal(" -- Line has too few points to split -- ")
            return

        # Split at nearest existing vertex (excluding first/last point).
        distances = np_norm(inUV_line - np_array([point_u, point_v]), axis=1)
        vertex_ind = int(distances.argmin())
        if vertex_ind <= 0 or vertex_ind >= inUV_line.shape[0] - 1:
            self.print_terminal(" -- Split point does not divide the line -- ")
            return

        outUV_1 = deepcopy(inUV_line[: vertex_ind + 1, :])
        outUV_2 = deepcopy(inUV_line[vertex_ind:, :])
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
            outX_1, outY_1, outZ_1 = self.parent.xsect_coll.plane2world(
                self.this_x_section_uid, outU_1, outV_1
            )
            outX_2, outY_2, outZ_2 = self.parent.xsect_coll.plane2world(
                self.this_x_section_uid, outU_2, outV_2
            )
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
        new_line_1["vtk_obj"].points = new_points_1
        new_line_1["vtk_obj"].auto_cells()
        new_line_2["vtk_obj"].points = new_points_2
        new_line_2["vtk_obj"].auto_cells()
        # Replace VTK object
        if new_line_1["vtk_obj"].points_number > 0:
            source_coll.replace_vtk(uid=uid, vtk_object=new_line_1["vtk_obj"])
            del new_line_1
        else:
            self.print_terminal("Empty object")
        # Create entity from the dictionary
        if new_line_2["vtk_obj"].points_number > 0:
            source_coll.add_entity_from_dict(new_line_2)
            del new_line_2
        else:
            self.print_terminal("Empty object")
        # Deselect input line.
        self.clear_selection()
        selector.EnabledOff()

    # Split line at selected existing point (vertex)
    self.print_terminal(
        "Split line at existing point. Line to be split has been selected,\nplease select an existing point for splitting."
    )
    source_coll = _get_editable_line_source_coll(
        self, selected_uids=self.selected_uids[:1]
    )
    if source_coll is None:
        return
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

def split_line_vector(self, vector):
    freeze_gui_off(self)
    pass


# check merge, snap, and see if a bridge nodes method is needed____________________


@freeze_gui_onoff
def merge_lines(self):
    """Merge two (contiguous or non-contiguous) lines.
    Metadata will be taken from the first selected line."""
    source_coll = _get_editable_line_source_coll(self, min_selected=2)
    if source_coll is None:
        return

    self.print_terminal(f"self.selected_uids: {self.selected_uids}")
    # Create local copy of selected_uids
    in_uids = self.selected_uids
    # For XsPolyLine, check that they all belong to the same cross-section.
    this_xsection = None
    for uid in in_uids:
        if source_coll.get_uid_topology(uid) == "XsPolyLine":
            if this_xsection is None:
                this_xsection = source_coll.get_uid_x_section(uid)
            elif this_xsection is not None:
                if source_coll.get_uid_x_section(uid) != this_xsection:
                    self.print_terminal(
                        " -- Selection must include lines belonging to the same cross-section only -- "
                    )
                    # self.enable_actions()
                    return
    # Create empty dictionary for the output line.
    new_line = deepcopy(source_coll.entity_dict)
    # Populate metadata from first selected line.
    source_uid = in_uids[0]
    new_line["name"] = source_coll.get_uid_name(source_uid)
    new_line["topology"] = source_coll.get_uid_topology(source_uid)
    new_line["role"] = source_coll.get_uid_role(source_uid)
    new_line["feature"] = source_coll.get_uid_feature(source_uid)
    new_line["scenario"] = source_coll.get_uid_scenario(source_uid)
    new_line["parent_uid"] = source_coll.get_uid_x_section(source_uid)
    new_line["properties_names"] = deepcopy(
        source_coll.get_uid_properties_names(source_uid)
    )
    new_line["properties_components"] = deepcopy(
        source_coll.get_uid_properties_components(source_uid)
    )
    # Create empty PolyLine() or XsPolyLine().
    if source_coll.get_uid_topology(source_uid) == "XsPolyLine":
        new_line["vtk_obj"] = XsPolyLine()
    else:
        new_line["vtk_obj"] = PolyLine()
    # Add points to new merged line.
    points_0 = source_coll.get_uid_vtk_obj(in_uids[0]).points.copy()
    for uid in in_uids[1::]:
        points_1 = source_coll.get_uid_vtk_obj(uid).points.copy()
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
        # Add merged line first. Remove source lines only if add succeeds.
    out_uid = source_coll.add_entity_from_dict(new_line)
    if not out_uid:
        self.print_terminal(" -- Failed to add merged line. Input lines not removed -- ")
        self.enable_actions()
        return
    # Deselect input lines, then remove old entities.
    self.clear_selection()
    for uid in in_uids:
        if uid == out_uid:
            continue
        source_coll.remove_entity(uid)
def _ordered_unique_uids(uids):
    ordered = []
    for uid in uids:
        if uid not in ordered:
            ordered.append(uid)
    return ordered


def _extract_intersection_points(geometry):
    if geometry.is_empty:
        return []
    gtype = geometry.geom_type
    if gtype == "Point":
        return [np_array(geometry.coords[0], dtype=float)]
    if gtype == "MultiPoint":
        return [np_array(point.coords[0], dtype=float) for point in geometry.geoms]
    if gtype in ("LineString", "LinearRing"):
        coords = list(geometry.coords)
        return [np_array(coords[0], dtype=float), np_array(coords[-1], dtype=float)]
    if gtype == "MultiLineString":
        points = []
        for line in geometry.geoms:
            coords = list(line.coords)
            points.append(np_array(coords[0], dtype=float))
            points.append(np_array(coords[-1], dtype=float))
        return points
    if hasattr(geometry, "geoms"):
        points = []
        for geom in geometry.geoms:
            points.extend(_extract_intersection_points(geom))
        return points
    return []


def _insert_point_on_line_coords(line_coords, point, eps=1e-8):
    for vertex in line_coords:
        if np_norm(vertex - point) <= eps:
            return line_coords
    point_geom = shp_point(float(point[0]), float(point[1]))
    for i in range(len(line_coords) - 1):
        segment = shp_linestring([line_coords[i], line_coords[i + 1]])
        if segment.distance(point_geom) <= eps:
            return np_concatenate(
                (line_coords[: i + 1], point.reshape(1, 2), line_coords[i + 1 :]),
                axis=0,
            )
    return line_coords


def _dedupe_consecutive_coords(line_coords, eps=1e-8):
    if len(line_coords) <= 1:
        return line_coords
    out_coords = [line_coords[0]]
    for vertex in line_coords[1:]:
        if np_norm(vertex - out_coords[-1]) > eps:
            out_coords.append(vertex)
    return np_array(out_coords, dtype=float)


def _coords_changed(coords_a, coords_b, eps=1e-8):
    if coords_a.shape != coords_b.shape:
        return True
    if coords_a.size == 0 and coords_b.size == 0:
        return False
    return np_norm(coords_a - coords_b) > eps


def _trim_terminal_branch(line_coords, point, tolerance, eps=1e-8):
    if len(line_coords) < 2:
        return line_coords, False

    out_coords = _insert_point_on_line_coords(line_coords, point, eps=eps)
    out_coords = _dedupe_consecutive_coords(out_coords, eps=eps)
    if len(out_coords) < 2:
        return line_coords, False

    start_dist = np_norm(point - out_coords[0])
    end_dist = np_norm(point - out_coords[-1])
    if (start_dist > tolerance + eps) and (end_dist > tolerance + eps):
        return out_coords, _coords_changed(line_coords, out_coords, eps=eps)

    distances = np_norm(out_coords - point, axis=1)
    point_idx = int(distances.argmin())
    if distances[point_idx] > eps:
        return out_coords, _coords_changed(line_coords, out_coords, eps=eps)

    if start_dist <= end_dist:
        if point_idx == 0:
            return out_coords, _coords_changed(line_coords, out_coords, eps=eps)
        trimmed = out_coords[point_idx:, :]
    else:
        if point_idx >= len(out_coords) - 1:
            return out_coords, _coords_changed(line_coords, out_coords, eps=eps)
        trimmed = out_coords[: point_idx + 1, :]
    
    trimmed = _dedupe_consecutive_coords(trimmed, eps=eps)
    if len(trimmed) < 2:
        return out_coords, _coords_changed(line_coords, out_coords, eps=eps)

    return trimmed, True


def _endpoint_extension_candidates(line_coords, eps=1e-12):
    candidates = []
    end_anchor = line_coords[-1]
    for i in range(len(line_coords) - 2, -1, -1):
        vec = end_anchor - line_coords[i]
        vec_len = np_norm(vec)
        if vec_len > eps:
            candidates.append(("append", end_anchor, vec / vec_len))
            break
    start_anchor = line_coords[0]
    for i in range(1, len(line_coords)):
        vec = start_anchor - line_coords[i]
        vec_len = np_norm(vec)
        if vec_len > eps:
            candidates.append(("prepend", start_anchor, vec / vec_len))
            break
    return candidates

@freeze_gui_onoff
def snap_line(self):
    """Snap selected lines by trimming short terminal branches and extending close endpoints."""
    source_coll = _get_editable_line_source_coll(self, min_selected=2)
    if source_coll is None:
        return

    ordered_selected_uids = _ordered_unique_uids(self.selected_uids)

    tolerance = input_one_value_dialog(
        parent=self,
        title="Snap max extension distance",
        label="Insert max extension distance",
        default_value=10,
    )
    if tolerance is None:
        self.print_terminal(" -- Snap cancelled by user -- ")
        return
    if isinstance(tolerance, str) or tolerance <= 0:
        self.print_terminal(" -- Max extension distance must be > 0 -- ")
        return

    eps = 1e-8
    max_dist = float(tolerance)
    line_uv = {}

    if isinstance(self, ViewMap):
        for uid in ordered_selected_uids:
            vtk_obj = source_coll.get_uid_vtk_obj(uid)
            in_u = np_array(vtk_obj.points_X).reshape(-1)
            in_v = np_array(vtk_obj.points_Y).reshape(-1)
            in_uv = _dedupe_consecutive_coords(np_column_stack((in_u, in_v)), eps=eps)
            if len(in_uv) < 2:
                self.print_terminal(" -- Lines must have at least 2 vertices -- ")
                return
            line_uv[uid] = in_uv
    elif isinstance(self, ViewXsection):
        for uid in ordered_selected_uids:
            vtk_obj = source_coll.get_uid_vtk_obj(uid)
            in_u, in_v = self.parent.xsect_coll.world2plane(
                section_uid=self.this_x_section_uid,
                X=vtk_obj.points_X,
                Y=vtk_obj.points_Y,
                Z=vtk_obj.points_Z,
            )
            in_uv = _dedupe_consecutive_coords(np_column_stack((in_u, in_v)), eps=eps)
            if len(in_uv) < 2:
                self.print_terminal(" -- Lines must have at least 2 vertices -- ")
                return
            line_uv[uid] = in_uv
    else:
        self.print_terminal(" -- Snap to intersection is available only in 2D views -- ")
        return

    changed_uids = set()
    trimmed_uids = set()
    endpoint_snap_count = 0

    # Step 1: detect intersections and trim short terminal branches.
    for idx_a, uid_a in enumerate(ordered_selected_uids):
        for uid_b in ordered_selected_uids[idx_a + 1 :]:
            if len(line_uv[uid_a]) < 2 or len(line_uv[uid_b]) < 2:
                continue
            line_a = shp_linestring(line_uv[uid_a])
            line_b = shp_linestring(line_uv[uid_b])
            if not line_a.intersects(line_b):
                continue

            raw_points = _extract_intersection_points(line_a.intersection(line_b))
            intersection_points = []
            for point in raw_points:
                if any(np_norm(point - saved) <= eps for saved in intersection_points):
                    continue
                intersection_points.append(point)

            for point in intersection_points:
                before_a = line_uv[uid_a]
                before_b = line_uv[uid_b]
                nearest_dist_a = min(
                    np_norm(point - before_a[0]), np_norm(point - before_a[-1])
                )
                nearest_dist_b = min(
                    np_norm(point - before_b[0]), np_norm(point - before_b[-1])
                )
                if (nearest_dist_a > max_dist + eps) and (nearest_dist_b > max_dist + eps):
                    continue

                out_a = _insert_point_on_line_coords(before_a, point, eps=eps)
                out_a = _dedupe_consecutive_coords(out_a, eps=eps)
                out_b = _insert_point_on_line_coords(before_b, point, eps=eps)
                out_b = _dedupe_consecutive_coords(out_b, eps=eps)
                if _coords_changed(before_a, out_a, eps=eps):
                    changed_uids.add(uid_a)
                if _coords_changed(before_b, out_b, eps=eps):
                    changed_uids.add(uid_b)
                line_uv[uid_a] = out_a
                line_uv[uid_b] = out_b

                if nearest_dist_a <= max_dist + eps:
                    trimmed_a, did_trim_a = _trim_terminal_branch(
                        line_uv[uid_a], point, max_dist, eps=eps
                    )
                    line_uv[uid_a] = trimmed_a
                    if did_trim_a:
                        changed_uids.add(uid_a)
                        trimmed_uids.add(uid_a)

                if nearest_dist_b <= max_dist + eps:
                    trimmed_b, did_trim_b = _trim_terminal_branch(
                        line_uv[uid_b], point, max_dist, eps=eps
                    )
                    line_uv[uid_b] = trimmed_b
                    if did_trim_b:
                        changed_uids.add(uid_b)
                        trimmed_uids.add(uid_b)

    # Step 2: extend every endpoint to the closest reachable line and add node on target.
    for uid in ordered_selected_uids:
        current_uv = line_uv[uid]
        if len(current_uv) < 2:
            continue
        endpoint_candidates = _endpoint_extension_candidates(current_uv)
        for mode, anchor, direction in endpoint_candidates:
            ray_end = anchor + direction * max_dist
            ray = shp_linestring([anchor, ray_end])
            best_target_uid = None
            best_hit_point = None
            best_hit_dist = None
            zero_target_uid = None
            zero_hit_point = None

            for other_uid in ordered_selected_uids:
                if other_uid == uid or len(line_uv[other_uid]) < 2:
                    continue
                other_line = shp_linestring(line_uv[other_uid])
                intersections = _extract_intersection_points(
                    ray.intersection(other_line)
                )
                for candidate in intersections:
                    vec = candidate - anchor
                    proj = float(vec[0] * direction[0] + vec[1] * direction[1])
                    if proj < -eps or proj > max_dist + eps:
                        continue
                    if abs(proj) <= eps:
                        if zero_hit_point is None:
                            zero_hit_point = candidate
                            zero_target_uid = other_uid
                        continue
                    if (best_hit_dist is None) or (proj < best_hit_dist):
                        best_hit_dist = proj
                        best_hit_point = candidate
                        best_target_uid = other_uid

            if zero_hit_point is not None:
                hit_point = zero_hit_point
                hit_dist = 0.0
                target_uid = zero_target_uid
            else:
                hit_point = best_hit_point
                hit_dist = best_hit_dist
                target_uid = best_target_uid

            if hit_point is None or target_uid is None:
                continue

            active_before = line_uv[uid]
            if mode == "append":
                if hit_dist > eps and np_norm(hit_point - active_before[-1]) > eps:
                    active_after = np_concatenate(
                        (active_before, hit_point.reshape(1, 2)), axis=0
                    )
                    line_uv[uid] = _dedupe_consecutive_coords(active_after, eps=eps)
                    changed_uids.add(uid)
                    endpoint_snap_count += 1
            else:
                if hit_dist > eps and np_norm(hit_point - active_before[0]) > eps:
                    active_after = np_concatenate(
                        (hit_point.reshape(1, 2), active_before), axis=0
                    )
                    line_uv[uid] = _dedupe_consecutive_coords(active_after, eps=eps)
                    changed_uids.add(uid)
                    endpoint_snap_count += 1

            target_before = line_uv[target_uid]
            target_after = _insert_point_on_line_coords(target_before, hit_point, eps=eps)
            target_after = _dedupe_consecutive_coords(target_after, eps=eps)
            if _coords_changed(target_before, target_after, eps=eps):
                line_uv[target_uid] = target_after
                changed_uids.add(target_uid)

    if not changed_uids:
        self.print_terminal(
            "Snap to intersection completed: no short branches or endpoint snaps found within distance."
        )
        self.clear_selection()
        return

    for uid in ordered_selected_uids:
        if uid not in changed_uids:
            continue
        out_uv = _dedupe_consecutive_coords(line_uv[uid], eps=eps)
        if len(out_uv) < 2:
            continue
        if isinstance(self, ViewMap):
            out_x = out_uv[:, 0]
            out_y = out_uv[:, 1]
            out_z = np_zeros(np_shape(out_x))
            out_vtk = PolyLine()
        else:
            out_x, out_y, out_z = self.parent.xsect_coll.plane2world(
                self.this_x_section_uid, out_uv[:, 0], out_uv[:, 1]
            )
            out_vtk = XsPolyLine(self.this_x_section_uid, parent=self.parent)
        out_vtk.points = np_column_stack((out_x, out_y, out_z))
        out_vtk.auto_cells()
        if out_vtk.points_number >= 2:
            source_coll.replace_vtk(uid=uid, vtk_object=out_vtk)

    self.print_terminal(
        "Snap to intersection completed: updated "
        + str(len(changed_uids))
        + " line(s), trimmed "
        + str(len(trimmed_uids))
        + " line(s), endpoint snaps "
        + str(endpoint_snap_count)
        + "."
    )
    self.clear_selection()


@freeze_gui_onoff
def resample_lines_distance(self):
    """Resample selected line with constant specified spacing."""
    source_coll = _get_editable_line_source_coll(self)
    if source_coll is None:
        return
    # Input distance for evenly spacing resampling.
    # Add a message to not use it with Draw Line 3D method
    self.print_terminal(
        "Resample Line with Distance. \nWARNING: do not use with Draw Line 3D method. \n"
        "Only XsPolylines maintain the Z value. For Polylines on the DEM it is necessary to reproject them. \n"
        "Please, notice that if snapping actions have been applied to the selected line(s), \n"
        "watertight connections with other lines may be lost after resampling."
    )
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
        # Create empty dictionary for the output line.
        new_line = deepcopy(source_coll.entity_dict)
        # Define topology and parent_uid. Get coordinates of input line.
        if isinstance(self, ViewMap):
            new_line["topology"] = "PolyLine"
            new_line["parent_uid"] = None
            inU = deepcopy(source_coll.get_uid_vtk_obj(current_uid).points[:, 0])
            inV = deepcopy(source_coll.get_uid_vtk_obj(current_uid).points[:, 1])
        elif isinstance(self, ViewXsection):
            new_line["topology"] = "XsPolyLine"
            new_line["parent_uid"] = self.this_x_section_uid
            in_vtk_obj = source_coll.get_uid_vtk_obj(current_uid)
            inU, inV = self.parent.xsect_coll.world2plane(
                section_uid=self.this_x_section_uid,
                X=in_vtk_obj.points_X,
                Y=in_vtk_obj.points_Y,
                Z=in_vtk_obj.points_Z,
            )
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
            source_coll.replace_vtk(uid=current_uid, vtk_object=new_line["vtk_obj"])
            del new_line
        else:
            self.print_terminal(" -- Empty object -- ")
        # Deselect input line and emit uid as list to force redraw.
        self.clear_selection()
        self.parent.signals.geom_modified.emit([current_uid], source_coll)
        self.print_terminal(
            f"Line {current_uid} resampled with distance = {distance_delta}"
        )


@freeze_gui_onoff
def resample_lines_number_points(self):
    # this must be done per-part___________________________________________________
    """Resample selected line with constant spacing defined by a specified number of nodes."""
    source_coll = _get_editable_line_source_coll(self)
    if source_coll is None:
        return
    # Input the number of points for evenly spacing resampling.
    self.print_terminal(
        "Resample Line with Distance. \nWARNING: do not use with Draw Line 3D method. \n"
        "Only XsPolylines maintain the Z value. For Polylines on the DEM it is necessary to reproject them. \n"
        "Please, notice that if snapping actions have been applied to the selected line(s), \n"
        "watertight connections with other lines may be lost after resampling."
    )
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
        # Create empty dictionary for the output line.
        new_line = deepcopy(source_coll.entity_dict)
        # Define topology and parent_uid. Get coordinates of input line.
        if isinstance(self, ViewMap):
            new_line["topology"] = "PolyLine"
            new_line["parent_uid"] = None
            inU = deepcopy(source_coll.get_uid_vtk_obj(current_uid).points[:, 0])
            inV = deepcopy(source_coll.get_uid_vtk_obj(current_uid).points[:, 1])
        elif isinstance(self, ViewXsection):
            new_line["topology"] = "XsPolyLine"
            new_line["parent_uid"] = self.this_x_section_uid
            in_vtk_obj = source_coll.get_uid_vtk_obj(current_uid)
            inU, inV = self.parent.xsect_coll.world2plane(
                section_uid=self.this_x_section_uid,
                X=in_vtk_obj.points_X,
                Y=in_vtk_obj.points_Y,
                Z=in_vtk_obj.points_Z,
            )
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
            source_coll.replace_vtk(uid=current_uid, vtk_object=new_line["vtk_obj"])
            del new_line
        else:
            self.print_terminal(" -- Empty object -- ")
        # Deselect input line and emit uid as list to force redraw.
        self.clear_selection()
        self.parent.signals.geom_modified.emit([current_uid], source_coll)
        self.print_terminal(
            f"Line {current_uid} resampled with number of points = {number_of_points}"
        )


@freeze_gui_onoff
def simplify_line(self):
    """Return a simplified representation of the line. Permits the user to choose a value for the Tolerance parameter."""
    source_coll = _get_editable_line_source_coll(self)
    if source_coll is None:
        return

    self.print_terminal(
        "Simplify line. Define tolerance value: "
        "small values result in more vertices and great similarity with the input line."
    )

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
            vtk_obj = source_coll.get_uid_vtk_obj(current_uid)
            if vtk_obj is None or vtk_obj.points_number <= 0:
                self.print_terminal(f" --  Object not valid for {current_uid} -- ")
                continue

            # Editing loop. Create empty dictionary for the output line
            new_line = deepcopy(source_coll.entity_dict)

            # Get coordinates of input line.
            if isinstance(self, ViewMap):
                new_line["topology"] = "PolyLine"
                inU = vtk_obj.points_X
                inV = vtk_obj.points_Y
                new_line["vtk_obj"] = PolyLine()
            elif isinstance(self, ViewXsection):
                new_line["topology"] = "XsPolyLine"
                new_line["parent_uid"] = self.this_x_section_uid
                inU, inV = self.parent.xsect_coll.world2plane(
                    section_uid=self.this_x_section_uid,
                    X=vtk_obj.points_X,
                    Y=vtk_obj.points_Y,
                    Z=vtk_obj.points_Z,
                )
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
                source_coll.replace_vtk(uid=current_uid, vtk_object=new_line["vtk_obj"])
                self.parent.signals.geom_modified.emit([current_uid], source_coll)
            else:
                self.print_terminal(
                    f"Empty geometry after parallel offset {current_uid}"
                )

    except Exception as e:
        self.print_terminal(f"Error: {str(e)}")

    # Deselect input line.
    self.clear_selection()


@freeze_gui_onoff
def copy_parallel(self):
    # this must be done per-part_______________________________________________________
    """Parallel folding. Create a line copied and translated from a template line using Shapely.
    Since lines are oriented left-to-right and bottom-to-top, and here we copy a line to the left,
    a positive distance creates a line shifted upwards and to the left."""
    self.print_terminal("Copy Parallel. Create a line copied and translated.")
    # Terminate running event loops

    source_coll = _get_editable_line_source_coll(
        self, selected_uids=self.selected_uids[:1]
    )
    if source_coll is None:
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
        # # Un-Freeze QT interface
        # self.enable_actions()
        return

    in_line_name = source_coll.df.loc[source_coll.df["uid"] == input_uid, "name"].values[0]
    out_line_name = in_line_name + "_para_" + "%d" % distance

    # Create empty dictionary for the output line and set name and role.
    # -----IN THE FUTURE see if other metadata should be automatically set.
    line_dict = deepcopy(source_coll.entity_dict)
    line_dict["name"] = out_line_name
    line_dict["role"] = source_coll.df.loc[source_coll.df["uid"] == input_uid, "role"].values[0]
    line_dict["feature"] = source_coll.get_uid_feature(self.selected_uids[0])
    line_dict["scenario"] = source_coll.get_uid_scenario(self.selected_uids[0])
    if isinstance(self, ViewMap):
        # if isinstance(self, (ViewMap, ViewMap)):
        inU = source_coll.get_uid_vtk_obj(input_uid).points_X
        inV = source_coll.get_uid_vtk_obj(input_uid).points_Y

        line_dict["vtk_obj"] = PolyLine()
        line_dict["topology"] = "PolyLine"
    # elif isinstance(self, (ViewXsection, ViewXsection)):
    elif isinstance(self, ViewXsection):
        in_vtk_obj = source_coll.get_uid_vtk_obj(input_uid)
        inU, inV = self.parent.xsect_coll.world2plane(
            section_uid=self.this_x_section_uid,
            X=in_vtk_obj.points_X,
            Y=in_vtk_obj.points_Y,
            Z=in_vtk_obj.points_Z,
        )
        line_dict["vtk_obj"] = XsPolyLine(self.this_x_section_uid, parent=self.parent)
        line_dict["topology"] = "XsPolyLine"
        line_dict["parent_uid"] = self.this_x_section_uid

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
        if shp_line_out.is_empty:
            self.print_terminal("Empty geometry after parallel offset")
            return
        if shp_line_out.geom_type == "LineString":
            out_line = shp_line_out
        elif hasattr(shp_line_out, "geoms"):
            line_parts = [
                geom
                for geom in shp_line_out.geoms
                if geom.geom_type == "LineString" and len(geom.coords) >= 2
            ]
            if not line_parts:
                self.print_terminal("Invalid offset geometry")
                return
            out_line = max(line_parts, key=lambda geom: geom.length)
        else:
            self.print_terminal("Unsupported offset geometry")
            return

        outUV = np_array(out_line.coords)
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
        output_uid = source_coll.add_entity_from_dict(line_dict)
        left_right(self, uid=output_uid, source_coll=source_coll)
    else:
        self.print_terminal("Empty object")


@freeze_gui_onoff
def copy_kink(self):
    """Kink folding. Create a line copied and translated from a template line using Shapely.
    Since lines are oriented left-to-right and bottom-to-top, and here we copy a line to the left,
    a positive distance creates a line shifted upwards and to the left."""
    self.print_terminal("Copy Kink. Create a line copied and translated.")

    source_coll = _get_editable_line_source_coll(
        self, selected_uids=self.selected_uids[:1]
    )
    if source_coll is None:
        return

    # If more than one line is selected, keep the first.
    input_uid = self.selected_uids[0]

    vtk_obj = source_coll.get_uid_vtk_obj(input_uid)
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

    in_line_name = source_coll.df.loc[source_coll.df["uid"] == input_uid, "name"].values[0]
    out_line_name = in_line_name + "_kink_" + "%d" % distance

    # Create empty dictionary for the output line and set name and role.
    line_dict = deepcopy(source_coll.entity_dict)
    line_dict["name"] = out_line_name
    line_dict["role"] = source_coll.df.loc[source_coll.df["uid"] == input_uid, "role"].values[0]
    line_dict["feature"] = source_coll.get_uid_feature(self.selected_uids[0])
    line_dict["scenario"] = source_coll.get_uid_scenario(self.selected_uids[0])

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
            line_dict["parent_uid"] = self.this_x_section_uid
            inU, inV = self.parent.xsect_coll.world2plane(
                section_uid=self.this_x_section_uid,
                X=vtk_obj.points_X,
                Y=vtk_obj.points_Y,
                Z=vtk_obj.points_Z,
            )

        # Stack coordinates in two-columns matrix
        inUV = np_column_stack((inU, inV))

        # Deselect input line.
        self.clear_selection()
        self.parent.signals.geom_modified.emit([input_uid], source_coll)

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
        if shp_line_out.geom_type == "LineString":
            out_line = shp_line_out
        elif hasattr(shp_line_out, "geoms"):
            line_parts = [
                geom
                for geom in shp_line_out.geoms
                if geom.geom_type == "LineString" and len(geom.coords) >= 2
            ]
            if not line_parts:
                self.print_terminal("Invalid offset geometry")
                return
            out_line = max(line_parts, key=lambda geom: geom.length)
        else:
            self.print_terminal("Unsupported offset geometry")
            return
        
        outUV = np_array(out_line.coords)
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
            output_uid = source_coll.add_entity_from_dict(line_dict)
            left_right(self, uid=output_uid, source_coll=source_coll)
        else:
            self.print_terminal("Empty object")

    except Exception as e:
        self.print_terminal(f"Error: {str(e)}")


def copy_similar(self, vector):
    # this must be done per-part_______________________________________________________
    """Similar folding. Create a line copied and translated from a template line.
    Does not need U,V coordinates since the translation vector is already in world coords
    """
    self.print_terminal("Copy Similar. Create a line copied and translated.")
    # Terminate running event loops
    # self.stop_event_loops()
    source_coll = _get_editable_line_source_coll(
        self, selected_uids=self.selected_uids[:1]
    )
    if source_coll is None:
        freeze_gui_off(self)
        return
    # If more than one line is selected, keep the first.
    # We can switch to multiple entities in the future ------------------------------------------------
    input_uid = self.selected_uids[0]
    # ----IN THE FUTURE add a test to check that the selected feature is a geological feature
    # Create empty dictionary for the output line and set name and role.
    # IN THE FUTURE see if other metadata should be automatically set.
    line_dict = deepcopy(source_coll.entity_dict)
    line_dict["role"] = source_coll.df.loc[source_coll.df["uid"] == input_uid, "role"].values[0]
    line_dict["feature"] = source_coll.get_uid_feature(self.selected_uids[0])
    line_dict["scenario"] = source_coll.get_uid_scenario(self.selected_uids[0])
    if isinstance(self, ViewMap):
        line_dict["vtk_obj"] = PolyLine()
        line_dict["topology"] = "PolyLine"
    elif isinstance(self, ViewXsection):
        line_dict["vtk_obj"] = XsPolyLine(self.this_x_section_uid, parent=self.parent)
        line_dict["topology"] = "XsPolyLine"
        line_dict["parent_uid"] = self.this_x_section_uid
    # Get coordinates of input line.
    inX = source_coll.get_uid_vtk_obj(input_uid).points_X
    inY = source_coll.get_uid_vtk_obj(input_uid).points_Y
    inZ = source_coll.get_uid_vtk_obj(input_uid).points_Z
    # Get similar folding vector.
    if vector.length == 0:
        self.print_terminal("Zero-length vector")
        freeze_gui_off(self)
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
    in_line_name = source_coll.df.loc[source_coll.df["uid"] == input_uid, "name"].values[0]
    distance = vector.length
    out_line_name = f"{in_line_name}_simi_{round(distance, 2)}"

    line_dict["name"] = out_line_name
    # Create entity from the dictionary and run left_right.
    output_uid = source_coll.add_entity_from_dict(line_dict)
    left_right(self, uid=output_uid, source_coll=source_coll)
    # Deselect input line.
    if line_dict["vtk_obj"].points_number > 0:
        self.clear_selection()
        # self.parent.geol_coll.signals.geom_modified.emit([input_uid])  # emit uid as list to force redraw()
    else:
        self.print_terminal("Empty object")
    freeze_gui_off(self)


def measure_distance(self, vector):
    """Tool to measure distance between two points. Draw a vector_by_mouse and obtain length and azimuth"""
    self.print_terminal(
        "Measure Distance between two points by drawing a vector by mouse"
    )

    def end_measure(event=None):
        """Cleanup function to properly end the measurement tool"""
        # self.enable_actions()
        if hasattr(self, "plotter"):
            self.plotter.untrack_click_position(side="right")

    # self.disable_actions()

    if vector.length == 0:
        self.print_terminal("Zero-length vector")
        end_measure()
        return

    message = (
        "Distance (m): "
        + str(round(vector.length, 2))
        + "\n\n"
        + "Strike: "
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
    # Finally, unfreeze the GUI.
    freeze_gui_off(self)


def flip_line(self, uid=None, source_coll=None):
    """Flip points array top to bottom in order to reverse the line order."""
    # self.parent.geol_coll.get_uid_vtk_obj(uid).points = np_flip(self.parent.geol_coll.get_uid_vtk_obj(uid).points, 0)
    if source_coll is None:
        source_coll = self.parent.geol_coll
    source_coll.get_uid_vtk_obj(uid).points = np_flipud(source_coll.get_uid_vtk_obj(uid).points)


def left_right(self, uid=None, source_coll=None):
    """Ensures lines are oriented left-to-right and bottom-to-top in map or cross-section"""
    if source_coll is None:
        source_coll = self.parent.geol_coll
    if isinstance(self, ViewMap):
        # if isinstance(self, ViewMap):
        U_line = source_coll.get_uid_vtk_obj(uid).points_X
        V_line = source_coll.get_uid_vtk_obj(uid).points_Y
    # elif isinstance(self, ViewXsection):
    elif isinstance(self, ViewXsection):
        vtk_obj = source_coll.get_uid_vtk_obj(uid)
        U_line, V_line = self.parent.xsect_coll.world2plane(
            section_uid=self.this_x_section_uid,
            X=vtk_obj.points_X,
            Y=vtk_obj.points_Y,
            Z=vtk_obj.points_Z,
        )
    # elif isinstance(self, View3D):
    #     # For 3D view, left-right orientation is not meaningful, so return early
    #     return
    else:
        return
    if len(U_line) < 2:
        return
    if U_line[0] > U_line[-1]:  # reverse if right-to-left
        flip_line(self, uid=uid, source_coll=source_coll)
    elif (
        U_line[0] == U_line[-1] and V_line[0] > V_line[-1]
    ):  # reverse if vertical up-to-down
        flip_line(self, uid=uid, source_coll=source_coll)


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
                line2, xfact=fac, yfact=fac, origin=line2.coords[0]
            )
            scaled_segment2 = shp_scale(
                scaled_segment1,
                xfact=fac,
                yfact=fac,
                origin=scaled_segment1.coords[-1],
            )
            extended_line = shp_linestring(scaled_segment2)
        elif len(line2.coords) == 3:
            first_seg = shp_linestring(line2.coords[:2])
            last_seg = shp_linestring(line2.coords[-2:])
            scaled_first_segment = shp_scale(
                first_seg, xfact=fac, yfact=fac, origin=first_seg.coords[-1]
            )
            scaled_last_segment = shp_scale(
                last_seg, xfact=fac, yfact=fac, origin=last_seg.coords[0]
            )
            extended_line = shp_linestring(
                [*scaled_first_segment.coords, *scaled_last_segment.coords]
            )
        else:
            first_seg = shp_linestring(line2.coords[:2])
            last_seg = shp_linestring(line2.coords[-2:])

            scaled_first_segment = shp_scale(
                first_seg, xfact=fac, yfact=fac, origin=first_seg.coords[-1]
            )
            scaled_last_segment = shp_scale(
                last_seg, xfact=fac, yfact=fac, origin=last_seg.coords[0]
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
