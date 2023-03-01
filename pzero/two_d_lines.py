from copy import deepcopy

import numpy as np
from numpy import asarray as np_asarray
from numpy import vstack as np_vstack
from numpy import column_stack as np_column_stack
from numpy import array as np_array
from numpy import zeros as np_zeros
from numpy import shape as np_shape
from numpy import sqrt as np_sqrt
from numpy import flip as np_flip
from numpy import arange as np_arange

from vtk import vtkTransform, vtkTransformPolyDataFilter

from .geological_collection import GeologicalCollection
from .helper_dialogs import multiple_input_dialog, input_one_value_dialog, message_dialog, tic, toc
from .helper_widgets import Editor, Tracer
from .windows_factory import ViewMap, ViewXsection, NavigationToolbar, NewViewMap, NewViewXsection
from .entities_factory import PolyLine, XsPolyLine
from shapely import affinity
from shapely.geometry import LineString, Point, MultiLineString
from shapely.ops import split, snap
from PyQt5.QtWidgets import QAction
from time import sleep

"""Implementation of functions specific to this view (e.g. particular editing or visualization functions)"""


def draw_line(self):
    def end_digitize(event, input_dict):
        # Signal called to end the digitization of a trace. It returns a new polydata
        self.plotter.untrack_click_position()
        traced_pld = tracer.GetContourRepresentation().GetContourRepresentationAsPolyData()
        input_dict['vtk_obj'].ShallowCopy(traced_pld)
        self.parent.geol_coll.add_entity_from_dict(input_dict)
        tracer.EnabledOff()
        self.enable_actions()

    self.disable_actions()
    """Create deepcopy of the geological entity dictionary."""
    line_dict = deepcopy(self.parent.geol_coll.geological_entity_dict)
    """One dictionary is set as input for a general widget of multiple-value-input"""
    line_dict_in = {'name': ['PolyLine name: ', 'new_pline'],
                    'geological_type': ['Geological type: ', GeologicalCollection.valid_geological_types],
                    'geological_feature': ['Geological feature: ',
                                           self.parent.geol_legend_df['geological_feature'].tolist()],
                    'scenario': ['Scenario: ', list(set(self.parent.geol_legend_df['scenario'].tolist()))]}
    line_dict_updt = multiple_input_dialog(title='Digitize new PolyLine', input_dict=line_dict_in)
    """Check if the output of the widget is empty or not. If the Cancel button was clicked, the tool quits"""
    if line_dict_updt is None:
        self.enable_actions()
        return
    """Getting the values that have been typed by the user through the widget"""
    for key in line_dict_updt:
        line_dict[key] = line_dict_updt[key]
    if isinstance(self, NewViewMap):
        line_dict['topological_type'] = 'PolyLine'
        line_dict['x_section'] = None
        line_dict['vtk_obj'] = PolyLine()
    elif isinstance(self, NewViewXsection):
        line_dict['topological_type'] = 'XsPolyLine'
        line_dict['x_section'] = self.this_x_section_uid
        line_dict['vtk_obj'] = XsPolyLine(x_section_uid=self.this_x_section_uid, parent=self.parent)
    tracer = Tracer(self)
    tracer.EnabledOn()
    self.plotter.track_click_position(side='right', callback=lambda event: end_digitize(event, line_dict))


def edit_line(self):

    def end_edit(event, uid):
        self.plotter.untrack_click_position(side='right')
        traced_pld = editor.GetContourRepresentation().GetContourRepresentationAsPolyData()
        if isinstance(self, NewViewMap):
            vtk_obj = PolyLine()
        elif isinstance(self, NewViewXsection):
            vtk_obj = XsPolyLine(x_section_uid=self.this_x_section_uid, parent=self.parent)
        vtk_obj.ShallowCopy(traced_pld)
        self.parent.geol_coll.replace_vtk(uid=uid, vtk_object=vtk_obj, const_color=True)
        editor.EnabledOff()
        self.clear_selection()
        self.enable_actions()

    self.disable_actions()
    sel_uid = self.selected_uids[0]
    actor = self.plotter.renderer.actors[sel_uid]
    data = actor.mapper.dataset
    # self.tracer.SetInputData(data)
    editor = Editor(self)
    editor.EnabledOn()
    editor.initialize(data,'edit')
    self.plotter.track_click_position(side='right', callback=lambda event: end_edit(event, sel_uid))
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
        self.parent.geol_coll.get_uid_vtk_obj(current_uid).sort_nodes()  # this could be probably done per-part__________________________
        """Deselect input line."""
        self.parent.geology_geom_modified_signal.emit([current_uid])  # emit uid as list to force redraw()
        # """Un-Freeze QT interface"""
        # for action in self.findChildren(QAction):
        #     action.setEnabled(True)
    self.clear_selection()


def move_line(self, points=None):
    """Move the whole line by rigid-body translation."""
    print("Move Line. Move the whole line by rigid-body translation.")

    vector_by_mouse_dU = points[1, 0] - points[0, 0]
    if isinstance(self, NewViewMap):
        vector_by_mouse_dV = points[1, 1] - points[0, 1]
    elif isinstance(self, NewViewXsection):
        vector_by_mouse_dV = points[1, 2] - points[0, 2]

    for current_uid in self.selected_uids:
        if (self.parent.geol_coll.get_uid_topological_type(current_uid) != "PolyLine") and (
                self.parent.geol_coll.get_uid_topological_type(current_uid) != "XsPolyLine"):
            print(" -- Selected data is not a line -- ")
            return

        """Editing loop."""
        """For some reason in the following the [:] is needed."""
        if isinstance(self, (ViewMap, NewViewMap)):
            x = self.parent.geol_coll.get_uid_vtk_obj(current_uid).points_X[:] + vector_by_mouse_dU
            y = self.parent.geol_coll.get_uid_vtk_obj(current_uid).points_Y[:] + vector_by_mouse_dV
            z = self.parent.geol_coll.get_uid_vtk_obj(current_uid).points_Z[:]

        elif isinstance(self, (ViewXsection, NewViewXsection)):
            vector_by_mouse_dX, vector_by_mouse_dY = self.parent.xsect_coll.get_deltaXY_from_deltaW(
                section_uid=self.this_x_section_uid, deltaW=vector_by_mouse_dU)
            x = self.parent.geol_coll.get_uid_vtk_obj(current_uid).points_X[:] + vector_by_mouse_dX
            y = self.parent.geol_coll.get_uid_vtk_obj(current_uid).points_Y[:] + vector_by_mouse_dY
            z = self.parent.geol_coll.get_uid_vtk_obj(current_uid).points_Z[:]+ vector_by_mouse_dV

        points = np.stack((x, y, z), axis=1)
        self.parent.geol_coll.get_uid_vtk_obj(current_uid).points = points
        left_right(current_uid)
        """Deselect input line."""
        self.parent.geology_geom_modified_signal.emit([current_uid])  # emit uid as list to force redraw()
        """Un-Freeze QT interface"""
    self.clear_selection()

    self.enable_actions()


def rotate_line(self):
    """Rotate the whole line by rigid-body rotation using Shapely."""
    print("Rotate Line. Rotate the whole line by rigid-body rotation. Please insert angle of anticlockwise rotation.")
    """Terminate running event loops"""
    """Check if a line is selected"""
    if not self.selected_uids:
        print(" -- No input data selected -- ")
        return
    """Freeze QT interface"""
    self.disable_actions()

    angle = input_one_value_dialog(parent=self, title="Rotate Line",
                                   label="Insert rotation angle in degrees, anticlockwise", default_value=10)
    for current_uid in self.selected_uids:
        if (self.parent.geol_coll.get_uid_topological_type(current_uid) != "PolyLine") and (
                self.parent.geol_coll.get_uid_topological_type(current_uid) != "XsPolyLine"):
            print(" -- Selected data is not a line -- ")
            return

        if angle is None:
            """Un-Freeze QT interface"""
            self.enable_actions()
            return
        if isinstance(self, (ViewMap, NewViewMap)):
            inU = self.parent.geol_coll.get_uid_vtk_obj(current_uid).points_X
            inV = self.parent.geol_coll.get_uid_vtk_obj(current_uid).points_Y
        elif isinstance(self, (ViewXsection, NewViewXsection)):
            inU = self.parent.geol_coll.get_uid_vtk_obj(current_uid).points_W
            inV = self.parent.geol_coll.get_uid_vtk_obj(current_uid).points_Z
        """Stack coordinates in two-columns matrix"""
        inUV = np_column_stack((inU, inV))
        """Run the Shapely function."""
        shp_line_in = LineString(inUV)
        shp_line_out = affinity.rotate(shp_line_in, angle, origin='centroid', use_radians=False)  # Use Shapely to rotate
        outUV = np_array(shp_line_out)
        """Un-stack output coordinates and write them to the empty dictionary."""
        outU = outUV[:, 0]
        outV = outUV[:, 1]
        if isinstance(self, (ViewMap, NewViewMap)):
            x = outU
            y = outV
            z = self.parent.geol_coll.get_uid_vtk_obj(current_uid).points_Z

        elif isinstance(self, (ViewXsection, NewViewXsection)):
            outX, outY = self.parent.xsect_coll.get_XY_from_W(section_uid=self.this_x_section_uid, W=outU)
            x = outX
            y = outY
            z = outV

        points = np.stack((x, y, z), axis=1)
        self.parent.geol_coll.get_uid_vtk_obj(current_uid).points = points
        left_right(current_uid)
        self.parent.geology_geom_modified_signal.emit([current_uid])  # emit uid as list to force redraw()
    """Deselect input line."""
    self.clear_selection()
    """Un-Freeze QT interface"""
    self.enable_actions()


def extend_line(self):
    def end_edit(event, uid):
        self.plotter.untrack_click_position(side='right')
        self.plotter.untrack_click_position(side='left')
        self.plotter.clear_events_for_key('k')

        traced_pld = extender.GetContourRepresentation().GetContourRepresentationAsPolyData()
        if isinstance(self, NewViewMap):
            vtk_obj = PolyLine()
        elif isinstance(self, NewViewXsection):
            vtk_obj = XsPolyLine(x_section_uid=self.this_x_section_uid, parent=self.parent)
        vtk_obj.ShallowCopy(traced_pld)

        self.parent.geol_coll.replace_vtk(uid=uid, vtk_object=vtk_obj, const_color=True)
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
    if (self.parent.geol_coll.get_uid_topological_type(self.selected_uids[0]) != "PolyLine") and (
            self.parent.geol_coll.get_uid_topological_type(self.selected_uids[0]) != "XsPolyLine"):
        print(" -- Selected data is not a line -- ")
        return
    """Freeze QT interface"""
    self.disable_actions()
    """If more than one line is selected, keep the first"""
    sel_uid = self.selected_uids[0]
    current_line = self.actors_df.loc[self.actors_df['uid'] == sel_uid, 'actor'].values[0].GetMapper().GetInput()

    extender = Editor(self)
    extender.EnabledOn()
    extender.initialize(current_line, 'extend')

    self.plotter.track_click_position(side='right', callback=lambda event: end_edit(event, sel_uid))

def split_line_line(self):
    """Split line (paper) with another line (scissors). First, select the paper-line then the scissors-line"""
    print("Split line with line. Line to be split has been selected, please select an intersecting line.")
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
    if (self.parent.geol_coll.get_uid_topological_type(current_uid_scissors) != "PolyLine") and (
            self.parent.geol_coll.get_uid_topological_type(current_uid_scissors) != "XsPolyLine"):
        print(" -- Selected scissor is not a line -- ")
        return

    for current_uid_paper in self.selected_uids[:-1]:
        if (self.parent.geol_coll.get_uid_topological_type(current_uid_paper) != "PolyLine") and (
                self.parent.geol_coll.get_uid_topological_type(current_uid_paper) != "XsPolyLine"):
            print(" -- Selected paper is not a line -- ")
            return


        """Create deepcopies of the selected entities. Split U- and V-coordinates."""
        if isinstance(self, (ViewMap,NewViewMap)):
            inU_paper = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid_paper).points[:, 0])
            inV_paper = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid_paper).points[:, 1])
            inU_scissors = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid_scissors).points[:, 0])
            inV_scissors = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid_scissors).points[:, 1])
        elif isinstance(self, (ViewXsection,NewViewXsection)):
            inU_paper = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid_paper).points_W)
            inV_paper = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid_paper).points_Z)
            inU_scissors = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid_scissors).points_W)
            inV_scissors = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid_scissors).points_Z)
        """Stack coordinates in two-columns matrix"""
        inUV_paper = np_column_stack((inU_paper, inV_paper))
        inUV_scissors = np_column_stack((inU_scissors, inV_scissors))
        """Run the Shapely function."""
        shp_line_in_paper = LineString(inUV_paper)
        shp_line_in_scissors = LineString(inUV_scissors)
        """Check if the two lineal geometries have shared path with dimension 1 (= they share a line-type object)"""
        if shp_line_in_paper.crosses(shp_line_in_scissors) == True:
            """Run the split shapely function."""
            lines = split(shp_line_in_paper,
                          shp_line_in_scissors)  # lines must include all line parts not affected by splitting and two parts for the split line__________
        else:  # handles the case when the LineString share a linear path and, for the moment, exists the tool
            """Un-Freeze QT interface"""
            self.enable_actions()
            return
        replace = 1  # replace = 1 for the first line to operate replace_vtk
        uids = [current_uid_scissors]
        for line in lines:
            """Create empty dictionary for the output lines."""
            new_line = deepcopy(self.parent.geol_coll.geological_entity_dict)
            new_line['name'] = \
                self.parent.geol_coll.df.loc[self.parent.geol_coll.df['uid'] == current_uid_paper, 'name'].values[
                    0] + '_split'
            new_line['topological_type'] = \
                self.parent.geol_coll.df.loc[
                    self.parent.geol_coll.df['uid'] == current_uid_paper, 'topological_type'].values[0]
            new_line['geological_type'] = \
                self.parent.geol_coll.df.loc[
                    self.parent.geol_coll.df['uid'] == current_uid_paper, 'geological_type'].values[0]
            new_line['geological_feature'] = \
                self.parent.geol_coll.df.loc[
                    self.parent.geol_coll.df['uid'] == current_uid_paper, 'geological_feature'].values[
                    0]
            new_line['scenario'] = \
                self.parent.geol_coll.df.loc[self.parent.geol_coll.df['uid'] == current_uid_paper, 'scenario'].values[0]
            if isinstance(self, (ViewMap,NewViewMap)):
                new_line['x_section'] = None
                new_line['vtk_obj'] = PolyLine()
            elif isinstance(self, (ViewXsection, NewViewXsection)):
                new_line['x_section'] = self.this_x_section_uid
                new_line['vtk_obj'] = XsPolyLine(self.this_x_section_uid, parent=self.parent)
            outUV = deepcopy(np_array(line))
            """Un-stack output coordinates and write them to the empty dictionary."""
            outU = outUV[:, 0]
            outV = outUV[:, 1]
            """Convert local coordinates to XYZ ones."""
            if isinstance(self, (ViewMap, NewViewMap)):
                outX = outU
                outY = outV
                outZ = np_zeros(np_shape(outX))
            elif isinstance(self, (ViewXsection, NewViewXsection)):
                outX, outY = self.parent.xsect_coll.get_XY_from_W(section_uid=self.this_x_section_uid, W=outU)
                outZ = outV
            """Create new vtk objects"""
            new_points = np_column_stack((outX, outY, outZ))
            new_line['vtk_obj'].points = new_points
            new_line['vtk_obj'].auto_cells()
            if new_line['vtk_obj'].points_number > 0:
                """Replace VTK object"""
                if replace == 1:
                    self.parent.geol_coll.replace_vtk(uid=current_uid_paper, vtk_object=new_line['vtk_obj'])
                    self.parent.geology_geom_modified_signal.emit([current_uid_paper])  # emit uid as list to force redraw()
                    replace = 0
                    uids.append(current_uid_paper)
                else:
                    """Create entity from the dictionary"""
                    uid = self.parent.geol_coll.add_entity_from_dict(new_line)
                    uids.append(uid)
                del new_line['vtk_obj']
            else:
                print("Empty object")
        """Deselect input line and force redraw"""

        self.parent.geology_geom_modified_signal.emit(uids)  # emit uid as list to force redraw()
    self.clear_selection()
    """Un-Freeze QT interface"""
    self.enable_actions()


def split_line_existing_point(self):
    """Split line at selected existing point (vertex)"""
    print(
        "Split line at existing point. Line to be split has been selected, please select an existing point for splitting.")
    """Terminate running event loops"""
    self.stop_event_loops()
    """Check if a line is selected"""
    if not self.selected_uids:
        print(" -- No input data selected -- ")
        return
    if (self.parent.geol_coll.get_uid_topological_type(self.selected_uids[0]) != "PolyLine") and (
            self.parent.geol_coll.get_uid_topological_type(self.selected_uids[0]) != "XsPolyLine"):
        print(" -- Selected data is not a line -- ")
        return
    """Freeze QT interface"""
    for action in self.findChildren(QAction):
        if isinstance(action.parentWidget(), NavigationToolbar) is False:
            action.setDisabled(True)
    """If more than one line is selected, keep the first"""
    current_uid = self.selected_uids[0]
    current_line = self.actors_df.loc[self.actors_df['uid'] == current_uid, 'actor'].values[0]
    epsilon = 6
    """get_data() returns the coordinates in the original "true" units (e.g. metres)"""
    current_line_U_true, current_line_V_true = current_line.get_data()
    """ax.transData.transform() returns the coordinates in pixels"""
    current_line_UV_px = self.ax.transData.transform(np_vstack([current_line_U_true, current_line_V_true]).T)
    current_line_U_px, current_line_V_px = current_line_UV_px.T
    """Select editable vertex."""
    self.pick_with_mouse()

    if self.pick_with_mouse_button != 1:
        """Un-Freeze QT interface"""
        for action in self.findChildren(QAction):
            action.setEnabled(True)
        return
    vertex_U_px = self.pick_with_mouse_U_pixels
    vertex_V_px = self.pick_with_mouse_V_pixels
    dist_px = np_sqrt(
        (current_line_U_px - vertex_U_px) ** 2 + (current_line_V_px - vertex_V_px) ** 2)  # calculate distance
    vertex_ind = dist_px.argmin()  # find index of closest vertex and select it
    if dist_px[vertex_ind] >= epsilon:  # if distance is larger than epsilon, deselect vertex and exit
        print("Picking too far from any vertex. Retry.")
    else:
        """Select and redraw vertex that cuts the line."""
        cutting_vertex, = self.ax.plot(current_line_U_true[vertex_ind], current_line_V_true[vertex_ind], color='red')
        cutting_vertex.set_marker('D')
        cutting_vertex.figure.canvas.draw()
        """Once vertex has been selected, create two LineString and Point entities to perform the shapely function split()."""
        """Create empty dictionary for the output line"""
        new_line_1 = deepcopy(self.parent.geol_coll.geological_entity_dict)
        new_line_2 = deepcopy(self.parent.geol_coll.geological_entity_dict)
        new_line_2['name'] = \
            self.parent.geol_coll.df.loc[self.parent.geol_coll.df['uid'] == current_uid, 'name'].values[0] + '_split'
        new_line_2['topological_type'] = \
            self.parent.geol_coll.df.loc[self.parent.geol_coll.df['uid'] == current_uid, 'topological_type'].values[0]
        new_line_2['geological_type'] = \
            self.parent.geol_coll.df.loc[self.parent.geol_coll.df['uid'] == current_uid, 'geological_type'].values[0]
        new_line_2['geological_feature'] = \
            self.parent.geol_coll.df.loc[self.parent.geol_coll.df['uid'] == current_uid, 'geological_feature'].values[0]
        new_line_2['scenario'] = \
            self.parent.geol_coll.df.loc[self.parent.geol_coll.df['uid'] == current_uid, 'scenario'].values[0]
        if isinstance(self, ViewMap):
            inU_line = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid).points[:, 0])
            inV_line = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid).points[:, 1])
        elif isinstance(self, ViewXsection):
            inU_line = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid).points_W)
            inV_line = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid).points_Z)
            new_line_2['x_section'] = self.this_x_section_uid
        """Stack coordinates in two-columns matrix"""
        inUV_line = np_column_stack((inU_line, inV_line))
        """Run the Shapely function."""
        shp_line_in = LineString(inUV_line)
        x_vertex_unit = deepcopy(current_line_U_true[vertex_ind])
        y_vertex_unit = deepcopy(current_line_V_true[vertex_ind])
        shp_point_in = Point(x_vertex_unit, y_vertex_unit)
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
        if isinstance(self, ViewMap):
            outX_1 = outU_1
            outY_1 = outV_1
            outZ_1 = np_zeros(np_shape(outX_1))
            outX_2 = outU_2
            outY_2 = outV_2
            outZ_2 = np_zeros(np_shape(outX_2))
        elif isinstance(self, ViewXsection):
            outX_1, outY_1 = self.parent.xsect_coll.get_XY_from_W(section_uid=self.this_x_section_uid, W=outU_1)
            outZ_1 = outV_1
            outX_2, outY_2 = self.parent.xsect_coll.get_XY_from_W(section_uid=self.this_x_section_uid, W=outU_2)
            outZ_2 = outV_2
        new_points_1 = np_column_stack((outX_1, outY_1, outZ_1))
        new_points_2 = np_column_stack((outX_2, outY_2, outZ_2))
        if isinstance(self, ViewMap):
            new_line_1['vtk_obj'] = PolyLine()
            new_line_2['vtk_obj'] = PolyLine()
        elif isinstance(self, ViewXsection):
            new_line_1['vtk_obj'] = XsPolyLine(self.this_x_section_uid, parent=self.parent)
            new_line_2['vtk_obj'] = XsPolyLine(self.this_x_section_uid, parent=self.parent)
        new_line_1['vtk_obj'].points = new_points_1
        new_line_1['vtk_obj'].auto_cells()
        new_line_2['vtk_obj'].points = new_points_2
        new_line_2[
            'vtk_obj'].auto_cells()  # lines must include all line parts not affected by splitting and two parts for the split line__________
        """Replace VTK object"""
        if new_line_1['vtk_obj'].points_number > 0:
            self.parent.geol_coll.replace_vtk(uid=current_uid, vtk_object=new_line_1['vtk_obj'])
            del new_line_1
        else:
            print("Empty object")
        """Create entity from the dictionary"""
        if new_line_2['vtk_obj'].points_number > 0:
            self.parent.geol_coll.add_entity_from_dict(new_line_2)
            del new_line_2
        else:
            print("Empty object")
        """Deselect input line."""
        self.selected_uids = []
        """The following lines are needed to hide and remove the draggable vertex without calling a complete redraw of the canvas."""
        cutting_vertex.set_visible(False)
        cutting_vertex.figure.canvas.draw()
        cutting_vertex.remove()
        self.parent.geology_geom_modified_signal.emit([current_uid])  # emit uid as list to force redraw()
    """Un-Freeze QT interface"""
    for action in self.findChildren(QAction):
        action.setEnabled(True)


# check merge, snap, and see if a bridge nodes method is needed____________________

def merge_lines(self):
    """Merge two (contiguous or non-contiguous) lines."""  # lines must include all line parts not affected by splitting and two parts for the split line__________
    print("Merge two lines. First line has been selected, please select second line for merging.")
    """Terminate running event loops"""
    """Check if a line is selected"""
    if not self.selected_uids:
        print(" -- No input data selected -- ")
        return
    elif len(self.selected_uids) <= 1:
        print(" -- Not enough input data selected. Select at least 2 objects -- ")
        return
    if (self.parent.geol_coll.get_uid_topological_type(self.selected_uids[0]) != "PolyLine") and (
            self.parent.geol_coll.get_uid_topological_type(self.selected_uids[0]) != "XsPolyLine"):
        print(" -- Selected data is not a line -- ")
        return
    """Freeze QT interface"""
    self.disable_actions()

    current_uid_one = self.selected_uids[0]
    current_uid_two = self.selected_uids[1]
    """Create empty dictionary for the output line."""
    new_line = deepcopy(self.parent.geol_coll.geological_entity_dict)
    if isinstance(self, (ViewMap,NewViewMap)):
        new_line['vtk_obj'] = PolyLine()
        new_line['x_section'] = None
        inU_one = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid_one).points[:, 0])
        inV_one = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid_one).points[:, 1])
        inU_two = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid_two).points[:, 0])
        inV_two = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid_two).points[:, 1])
    elif isinstance(self, (ViewXsection,NewViewXsection)):
        new_line['vtk_obj'] = XsPolyLine(self.this_x_section_uid, parent=self.parent)
        new_line['x_section'] = self.this_x_section_uid
        inU_one = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid_one).points_W)
        inV_one = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid_one).points_Z)
        inU_two = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid_two).points_W)
        inV_two = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid_two).points_Z)
    """Calculate distances"""
    dist_start_start = np_sqrt((inU_one[0] - inU_two[0]) ** 2 + (inV_one[0] - inV_two[0]) ** 2)
    dist_end_end = np_sqrt((inU_one[-1] - inU_two[-1]) ** 2 + (inV_one[-1] - inV_two[-1]) ** 2)
    dist_start_end = np_sqrt((inU_one[0] - inU_two[-1]) ** 2 + (inV_one[0] - inV_two[-1]) ** 2)
    dist_end_start = np_sqrt((inU_one[-1] - inU_two[0]) ** 2 + (inV_one[-1] - inV_two[0]) ** 2)
    if min(dist_start_start, dist_end_end, dist_start_end, dist_end_start) == dist_start_start:  # flip line 1
        inU_one = np_flip(inU_one, 0)
        inV_one = np_flip(inV_one, 0)
    elif min(dist_start_start, dist_end_end, dist_start_end, dist_end_start) == dist_end_end:  # flip line 2
        inU_two = np_flip(inU_two, 0)
        inV_two = np_flip(inV_two, 0)
    elif min(dist_start_start, dist_end_end, dist_start_end,
             dist_end_start) == dist_start_end:  # flip both line 1 and line 2
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
    if isinstance(self, (ViewMap,NewViewMap)):
        outX = outU
        outY = outV
        outZ = np_zeros(np_shape(outX))
    elif isinstance(self, (ViewXsection,NewViewXsection)):
        outX, outY = self.parent.xsect_coll.get_XY_from_W(section_uid=self.this_x_section_uid, W=outU)
        outZ = outV
    new_points = np_column_stack((outX, outY, outZ))
    new_line['vtk_obj'].points = new_points
    new_line['vtk_obj'].auto_cells()
    """Replace VTK object"""
    if new_line['vtk_obj'].points_number > 0:
        self.parent.geol_coll.replace_vtk(uid=current_uid_one, vtk_object=new_line['vtk_obj'])
        del new_line
    else:
        print("Empty object")
    """Deselect input line."""
    self.clear_selection()
    self.parent.geol_coll.remove_entity(current_uid_two)
    self.parent.geology_geom_modified_signal.emit([current_uid_one])  # emit uid as list to force redraw()
    """Un-Freeze QT interface"""
    self.enable_actions()


def snap_line(self):
    """Snaps vertices of the selected line (the snapping-line) to the nearest vertex of the chosen line (goal-line),
    depending on the Tolerance parameter."""
    print("Snap line to line. Line to be snapped has been selected, please select second line.")
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
    if (self.parent.geol_coll.get_uid_topological_type(current_uid_goal) != "PolyLine") and (
            self.parent.geol_coll.get_uid_topological_type(current_uid_goal) != "XsPolyLine"):
        print(" -- Selected goal is not a line -- ")
        return
    tolerance = input_one_value_dialog(parent=self, title="Snap tolerance",
                                   label="Insert snap tolerance", default_value=10)
    for current_uid_snap in self.selected_uids[:-1]:
        if (self.parent.geol_coll.get_uid_topological_type(current_uid_snap) != "PolyLine") and (
                self.parent.geol_coll.get_uid_topological_type(current_uid_snap) != "XsPolyLine"):
            print(" -- Selected snap is not a line -- ")
            return

        """Create empty dictionary for the output line."""
        new_line = deepcopy(self.parent.geol_coll.geological_entity_dict)
        """Editing loop. Get coordinates of the line to be modified (snap-line)."""
        if isinstance(self, (ViewMap, NewViewMap)):
            new_line['vtk_obj'] = PolyLine()
            new_line['x_section'] = None
            inU_snap = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid_snap).points[:, 0])
            inV_snap = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid_snap).points[:, 1])
            inU_goal = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid_goal).points[:, 0])
            inV_goal = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid_goal).points[:, 1])
        elif isinstance(self, (ViewXsection,NewViewXsection)):
            new_line['vtk_obj'] = XsPolyLine(self.this_x_section_uid, parent=self.parent)
            new_line['x_section'] = self.this_x_section_uid
            inU_snap = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid_snap).points_W)
            inV_snap = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid_snap).points_Z)
            inU_goal = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid_goal).points_W)
            inV_goal = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid_goal).points_Z)
        """Stack coordinates in two-columns matrix"""
        inUV_snap = np_column_stack((inU_snap, inV_snap))
        inUV_goal = np_column_stack((inU_goal, inV_goal))
        """Run the Shapely function."""
        shp_line_in_snap = LineString(inUV_snap)
        shp_line_in_goal = LineString(inUV_goal)
        """In the snapping tool, the last input value is called Tolerance. Can be modified, do some checks.
        Little tolerance risks of not snapping distant lines, while too big tolerance snaps to the wrong vertex and
        not to the nearest one"""
        if shp_line_in_snap.is_simple and shp_line_in_goal.is_simple:
            shp_line_out_snap = snap(shp_line_in_snap, shp_line_in_goal, tolerance)
        else:
            print("Polyline is not simple, it self-intersects")
            """Un-Freeze QT interface"""
            self.enable_actions()
            return
        shp_line_out_diff = shp_line_out_snap.difference(shp_line_in_goal)  # eliminate the shared path that Snap may create
        outUV = deepcopy(np_array(shp_line_out_diff))
        """Un-stack output coordinates and write them to the empty dictionary."""
        if outUV.ndim < 2:
            print(outUV)
            print('Invalid shape')
            self.clear_selection()
            self.enable_actions()
            return
        outU = outUV[:, 0]
        outV = outUV[:, 1]
        """Convert local coordinates to XYZ ones."""
        if isinstance(self, (ViewMap,NewViewMap)):
            outX = outU
            outY = outV
            outZ = np_zeros(np_shape(outX))
        elif isinstance(self, (ViewXsection,NewViewXsection)):
            outX, outY = self.parent.xsect_coll.get_XY_from_W(section_uid=self.this_x_section_uid, W=outU)
            outZ = outV
        """Create new vtk objects"""
        new_points = np_column_stack((outX, outY, outZ))
        new_line['vtk_obj'].points = new_points
        new_line['vtk_obj'].auto_cells()
        """Replace VTK object"""
        if new_line['vtk_obj'].points_number > 0:
            self.parent.geol_coll.replace_vtk(uid=current_uid_snap, vtk_object=new_line['vtk_obj'])
            del new_line
        else:
            print("Empty object")
        """Deselect input line and force redraw"""
        self.parent.geology_geom_modified_signal.emit(
            [current_uid_snap, current_uid_goal])  # emit uid as list to force redraw()
        """Un-Freeze QT interface"""
    self.clear_selection()
    self.enable_actions()


def resample_line_distance(self):  # this must be done per-part_______________________________________________________
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
    distance_delta = input_one_value_dialog(parent=self, title="Spacing distance for Line Resampling",
                                            label="Insert spacing distance", default_value="Distance")
    for current_uid in self.selected_uids:
        if (self.parent.geol_coll.get_uid_topological_type(current_uid) != "PolyLine") and (
                self.parent.geol_coll.get_uid_topological_type(current_uid) != "XsPolyLine"):
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
        new_line = deepcopy(self.parent.geol_coll.geological_entity_dict)
        if isinstance(self, (ViewMap,NewViewMap)):
            new_line['topological_type'] = 'PolyLine'
            new_line['x_section'] = None
            inU = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid).points[:, 0])
            inV = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid).points[:, 1])
        elif isinstance(self, (ViewXsection,NewViewXsection)):
            new_line['topological_type'] = 'XsPolyLine'
            new_line['x_section'] = self.this_x_section_uid
            inU = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid).points_W)
            inV = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid).points_Z)
        """Stack coordinates in two-columns matrix"""
        inUV = np_column_stack((inU, inV))
        """Run the Shapely function."""
        shp_line_in = LineString(inUV)
        if distance_delta >= shp_line_in.length:
            while distance_delta >= shp_line_in.length:
                distance_delta = distance_delta / 2
        distances = np_arange(0, shp_line_in.length, distance_delta)
        points = [shp_line_in.interpolate(distance) for distance in distances] + [shp_line_in.boundary[1]]
        shp_line_out = LineString(points)
        outUV = deepcopy(np_array(shp_line_out))
        """Un-stack output coordinates and write them to the empty dictionary."""
        outU = outUV[:, 0]
        outV = outUV[:, 1]
        if isinstance(self, (ViewMap,NewViewMap)):
            outX = outU
            outY = outV
            outZ = np_zeros(np_shape(outX))
            new_line['vtk_obj'] = PolyLine()
        elif isinstance(self, (ViewXsection,NewViewXsection)):
            outX, outY = self.parent.xsect_coll.get_XY_from_W(section_uid=self.this_x_section_uid, W=outU)
            outZ = outV
            new_line['vtk_obj'] = XsPolyLine(self.this_x_section_uid, parent=self.parent)
        new_points = np_column_stack((outX, outY, outZ))
        new_line['vtk_obj'].points = new_points
        new_line['vtk_obj'].auto_cells()
        """Replace VTK object"""
        if new_line['vtk_obj'].points_number > 0:
            self.parent.geol_coll.replace_vtk(uid=current_uid, vtk_object=new_line['vtk_obj'])
            del new_line
        else:
            print("Empty object")
        """Deselect input line."""
        self.parent.geology_geom_modified_signal.emit([current_uid])  # emit uid as list to force redraw()
        """Un-Freeze QT interface"""
    self.clear_selection()
    self.enable_actions()


def resample_line_number_points(self):  # this must be done per-part___________________________________________________
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
    number_of_points = input_one_value_dialog(parent=self, title="Number of points for Line Resampling",
                                              label="Insert number of points", default_value="Number")
    for current_uid in self.selected_uids:
        if (self.parent.geol_coll.get_uid_topological_type(current_uid) != "PolyLine") and (
                self.parent.geol_coll.get_uid_topological_type(current_uid) != "XsPolyLine"):
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
        new_line = deepcopy(self.parent.geol_coll.geological_entity_dict)
        """Define topological_type and x_section. Get coordinates of input line"""
        if isinstance(self, (ViewMap,NewViewMap)):
            new_line['topological_type'] = 'PolyLine'
            new_line['x_section'] = None
            inU = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid).points[:, 0])
            inV = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid).points[:, 1])
        elif isinstance(self, (ViewXsection,NewViewXsection)):
            new_line['topological_type'] = 'XsPolyLine'
            new_line['x_section'] = self.this_x_section_uid
            inU = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid).points_W)
            inV = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid).points_Z)
        """Stack coordinates in two-columns matrix"""
        inUV = np_column_stack((inU, inV))
        """Run the Shapely function."""
        shp_line_in = LineString(inUV)
        distances = (shp_line_in.length * i / (number_of_points - 1) for i in range(number_of_points))
        points = [shp_line_in.interpolate(distance) for distance in distances]
        shp_line_out = LineString(points)
        outUV = deepcopy(np_array(shp_line_out))
        """Un-stack output coordinates and write them to the empty dictionary."""
        outU = outUV[:, 0]
        outV = outUV[:, 1]
        if isinstance(self, (ViewMap,NewViewMap)):
            outX = outU
            outY = outV
            outZ = np_zeros(np_shape(outX))
            new_line['vtk_obj'] = PolyLine()
        elif isinstance(self, (ViewXsection,NewViewXsection)):
            outX, outY = self.parent.xsect_coll.get_XY_from_W(section_uid=self.this_x_section_uid, W=outU)
            outZ = outV
            new_line['vtk_obj'] = XsPolyLine(self.this_x_section_uid, parent=self.parent)
        new_points = np_column_stack((outX, outY, outZ))
        new_line['vtk_obj'].points = new_points
        new_line['vtk_obj'].auto_cells()
        """Replace VTK object"""
        if new_line['vtk_obj'].points_number > 0:
            self.parent.geol_coll.replace_vtk(uid=current_uid, vtk_object=new_line['vtk_obj'])
            del new_line
        else:
            print("Empty object")

        self.parent.geology_geom_modified_signal.emit([current_uid])  # emit uid as list to force redraw()
    """Deselect input line."""
    self.clear_selection()
    """Un-Freeze QT interface"""
    self.enable_actions()


def simplify_line(self):  # this must be done per-part_______________________________________________________
    """Return a simplified representation of the line. Permits the user to choose a value for the Tolerance parameter."""
    print("Simplify line. Define tolerance value: "
          "small values result in more vertices and great similarity with the input line.")
    """Terminate running event loops"""

    """Check if a line is selected"""
    if not self.selected_uids:
        print(" -- No input data selected -- ")
        return
    """Freeze QT interface"""
    self.disable_actions()
    """Ask for the tolerance parameter"""
    tolerance_p = input_one_value_dialog(parent=self, title="Simplify - Tolerance", label="Insert tolerance parameter",
                                         default_value="0.1")
    for current_uid in self.selected_uids:
        if (self.parent.geol_coll.get_uid_topological_type(current_uid) != "PolyLine") and (
                self.parent.geol_coll.get_uid_topological_type(current_uid) != "XsPolyLine"):
            print(" -- Selected data is not a line -- ")
            return

        if tolerance_p is None:
            """Un-Freeze QT interface"""
            self.enable_actions()
            return
        if tolerance_p <= 0:
            tolerance_p = 0.1
        """Editing loop. Create empty dictionary for the output line"""
        new_line = deepcopy(self.parent.geol_coll.geological_entity_dict)
        """Get coordinates of input line."""
        if isinstance(self, (ViewMap,NewViewMap)):
            new_line['topological_type'] = 'PolyLine'
            new_line['x_section'] = None
            inU = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid).points[:, 0])
            inV = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid).points[:, 1])
        elif isinstance(self, (ViewXsection,NewViewXsection)):
            new_line['topological_type'] = 'XsPolyLine'
            new_line['x_section'] = self.this_x_section_uid
            inU = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid).points_W)
            inV = deepcopy(self.parent.geol_coll.get_uid_vtk_obj(current_uid).points_Z)
        """Stack coordinates in two-columns matrix"""
        inUV = np_column_stack((inU, inV))
        """Run the Shapely function."""
        shp_line_in = LineString(inUV)
        shp_line_out = shp_line_in.simplify(tolerance_p, preserve_topology=False)
        outUV = deepcopy(np_array(shp_line_out))
        """Un-stack output coordinates and write them to the empty dictionary."""
        outU = outUV[:, 0]
        outV = outUV[:, 1]
        if isinstance(self, (ViewMap,NewViewMap)):
            outX = outU
            outY = outV
            outZ = np_zeros(np_shape(outX))
            new_line['vtk_obj'] = PolyLine()
        elif isinstance(self, (ViewXsection,NewViewXsection)):
            outX, outY = self.parent.xsect_coll.get_XY_from_W(section_uid=self.this_x_section_uid, W=outU)
            outZ = outV
            new_line['vtk_obj'] = XsPolyLine(self.this_x_section_uid, parent=self.parent)
        """Create new vtk"""
        new_points = np_column_stack((outX, outY, outZ))
        new_line['vtk_obj'].points = new_points
        new_line['vtk_obj'].auto_cells()
        """Replace VTK object"""
        if new_line['vtk_obj'].points_number > 0:
            self.parent.geol_coll.replace_vtk(uid=current_uid, vtk_object=new_line['vtk_obj'])
            del new_line
        else:
            print("Empty object")

        self.parent.geology_geom_modified_signal.emit([current_uid])  # emit uid as list to force redraw()
    """Deselect input line."""
    self.clear_selection()
    """Un-Freeze QT interface"""
    self.enable_actions()


def copy_parallel(self):  # this must be done per-part_______________________________________________________
    """Parallel folding. Create a line copied and translated from a template line using Shapely.
    Since lines are oriented left-to-right and bottom-to-top, and here we copy a line to the left,
    a positive distance creates a line shifted upwards and to the left."""
    print("Copy Parallel. Create a line copied and translated.")
    """Terminate running event loops"""

    """Check if a line is selected"""
    if not self.selected_uids:
        print(" -- No input data selected -- ")
        return
    if (self.parent.geol_coll.get_uid_topological_type(self.selected_uids[0]) != "PolyLine") and (
            self.parent.geol_coll.get_uid_topological_type(self.selected_uids[0]) != "XsPolyLine"):
        print(" -- Selected data is not a line -- ")
        return
    """Freeze QT interface"""
    self.disable_actions()
    """If more than one line is selected, keep the first."""
    input_uid = self.selected_uids[0]
    """IN THE FUTURE add a test to check that the selected feature is a geological feature"""
    """Editing loop."""
    distance = input_one_value_dialog(parent=self, title="Line from template", label="Insert distance",
                                      default_value=100)
    if distance is None:
        """Un-Freeze QT interface"""
        self.enable_actions()
        return

    in_line_name = self.parent.geol_coll.df.loc[self.parent.geol_coll.df['uid'] == input_uid, 'name'].values[0]
    out_line_name = in_line_name + '_para_' + '%d' % distance

    """Create empty dictionary for the output line and set name and geological_type.
    IN THE FUTURE see if other metadata should be automatically set."""
    line_dict = deepcopy(self.parent.geol_coll.geological_entity_dict)
    line_dict['name'] = out_line_name
    line_dict['geological_type'] = \
        self.parent.geol_coll.df.loc[self.parent.geol_coll.df['uid'] == input_uid, 'geological_type'].values[0]
    line_dict['geological_feature'] = self.parent.geol_coll.get_uid_geological_feature(self.selected_uids[0])
    line_dict['scenario'] = self.parent.geol_coll.get_uid_scenario(self.selected_uids[0])
    if isinstance(self, (ViewMap,NewViewMap)):
        line_dict['vtk_obj'] = PolyLine()
        line_dict['topological_type'] = 'PolyLine'
    elif isinstance(self, (ViewXsection,NewViewXsection)):
        line_dict['vtk_obj'] = XsPolyLine(self.this_x_section_uid, parent=self.parent)
        line_dict['topological_type'] = 'XsPolyLine'
        line_dict['x_section'] = self.this_x_section_uid
    """Get coordinates of input line."""
    if isinstance(self, (ViewMap,NewViewMap)):
        inU = self.parent.geol_coll.get_uid_vtk_obj(input_uid).points_X
        inV = self.parent.geol_coll.get_uid_vtk_obj(input_uid).points_Y
    elif isinstance(self, (ViewXsection,NewViewXsection)):
        inU = self.parent.geol_coll.get_uid_vtk_obj(input_uid).points_W
        inV = self.parent.geol_coll.get_uid_vtk_obj(input_uid).points_Z
    """Stack coordinates in two-columns matrix"""
    print("np_column_stack((inU, inV))")
    inUV = np_column_stack((inU, inV))
    """Deselect input line."""
    self.clear_selection()
    self.parent.geology_geom_modified_signal.emit([input_uid])  # emit uid as list to force redraw()
    """Run the Shapely function."""
    shp_line_in = LineString(inUV)
    print("shp_line_in.parallel_offset")
    if shp_line_in.is_simple:

        shp_line_out = shp_line_in.parallel_offset(distance, 'left', resolution=16,
                                                   join_style=1)  # parallel folds are obtained with join_style=1

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
    if isinstance(self, (ViewMap,NewViewMap)):
        outX = outU
        outY = outV
        outZ = np_zeros(np_shape(outX))
    elif isinstance(self, (ViewXsection,NewViewXsection)):
        outX, outY = self.parent.xsect_coll.get_XY_from_W(section_uid=self.this_x_section_uid, W=outU)
        outZ = outV
    """Stack coordinates in two-columns matrix and write to vtk object."""
    print("outXYZ = np_column_stack((outX, outY, outZ))")

    outXYZ = np_column_stack((outX, outY, outZ))

    line_dict['vtk_obj'].points = outXYZ
    line_dict['vtk_obj'].auto_cells()
    """Create entity from the dictionary and run left_right."""
    if line_dict['vtk_obj'].points_number > 0:
        output_uid = self.parent.geol_coll.add_entity_from_dict(line_dict)
        left_right(output_uid)
    else:
        print("Empty object")
    """Un-Freeze QT interface"""
    self.enable_actions()


def copy_kink(self):  # this must be done per-part_______________________________________________________
    """Kink folding. Create a line copied and translated from a template line using Shapely.
    Since lines are oriented left-to-right and bottom-to-top, and here we copy a line to the left,
    a positive distance creates a line shifted upwards and to the left."""
    print("Copy Kink. Create a line copied and translated.")
    """Terminate running event loops"""
    """Check if a line is selected"""
    if not self.selected_uids:
        print(" -- No input data selected -- ")
        return
    if (self.parent.geol_coll.get_uid_topological_type(self.selected_uids[0]) != "PolyLine") and (
            self.parent.geol_coll.get_uid_topological_type(self.selected_uids[0]) != "XsPolyLine"):
        print(" -- Selected data is not a line -- ")
        return
    """Freeze QT interface"""
    self.disable_actions()
    """If more than one line is selected, keep the first."""
    input_uid = self.selected_uids[0]
    """IN THE FUTURE add a test to check that the selected feature is a geological feature"""
    """Editing loop."""
    distance = input_one_value_dialog(parent=self, title="Line from template", label="Insert distance",
                                      default_value=100)
    if distance is None:
        """Un-Freeze QT interface"""
        self.enable_actions()
        return

    in_line_name = self.parent.geol_coll.df.loc[self.parent.geol_coll.df['uid'] == input_uid, 'name'].values[0]
    out_line_name = in_line_name + '_kink_' + '%d' % distance

    """Create empty dictionary for the output line and set name and geological_type.
    IN THE FUTURE see if other metadata should be automatically set."""
    line_dict = deepcopy(self.parent.geol_coll.geological_entity_dict)
    line_dict['name'] = out_line_name
    line_dict['geological_type'] = \
        self.parent.geol_coll.df.loc[self.parent.geol_coll.df['uid'] == input_uid, 'geological_type'].values[0]
    line_dict['geological_feature'] = self.parent.geol_coll.get_uid_geological_feature(self.selected_uids[0])
    line_dict['scenario'] = self.parent.geol_coll.get_uid_scenario(self.selected_uids[0])
    if isinstance(self, (ViewMap,NewViewMap)):
        line_dict['vtk_obj'] = PolyLine()
        line_dict['topological_type'] = 'PolyLine'
    elif isinstance(self, (ViewXsection,NewViewXsection)):
        line_dict['vtk_obj'] = XsPolyLine(self.this_x_section_uid, parent=self.parent)
        line_dict['topological_type'] = 'XsPolyLine'
        line_dict['x_section'] = self.this_x_section_uid
    """Get coordinates of input line."""
    if isinstance(self, (ViewMap,NewViewMap)):
        inU = self.parent.geol_coll.get_uid_vtk_obj(input_uid).points_X
        inV = self.parent.geol_coll.get_uid_vtk_obj(input_uid).points_Y
    elif isinstance(self, (ViewXsection,NewViewXsection)):
        inU = self.parent.geol_coll.get_uid_vtk_obj(input_uid).points_W
        inV = self.parent.geol_coll.get_uid_vtk_obj(input_uid).points_Z
    """Stack coordinates in two-columns matrix"""
    inUV = np_column_stack((inU, inV))
    """Deselect input line."""
    self.clear_selection()
    self.parent.geology_geom_modified_signal.emit([input_uid])  # emit uid as list to force redraw()
    """Run the Shapely function."""
    shp_line_in = LineString(inUV)
    if shp_line_in.is_simple:
        shp_line_out = shp_line_in.parallel_offset(distance, 'left', resolution=16, join_style=2,
                                                   mitre_limit=10.0)  # kink folds are obtained with join_style=2, mitre_limit=10.0
        outUV = np_array(shp_line_out)
        """Un-stack output coordinates and write them to the empty dictionary."""
        outU = outUV[:, 0]
        outV = outUV[:, 1]
    else:
        print("Polyline is not simple, it self-intersects")
        """Un-Freeze QT interface"""
        self.enable_actions()
        return
    if isinstance(self, (ViewMap,NewViewMap)):
        outX = outU
        outY = outV
        outZ = np_zeros(np_shape(outX))
    elif isinstance(self, (ViewXsection,NewViewXsection)):
        outX, outY = self.parent.xsect_coll.get_XY_from_W(section_uid=self.this_x_section_uid, W=outU)
        outZ = outV
    """Stack coordinates in two-columns matrix and write to vtk object."""
    outXYZ = np_column_stack((outX, outY, outZ))
    line_dict['vtk_obj'].points = outXYZ
    line_dict['vtk_obj'].auto_cells()
    """Create entity from the dictionary and run left_right."""
    if line_dict['vtk_obj'].points_number > 0:
        output_uid = self.parent.geol_coll.add_entity_from_dict(line_dict)
        left_right(output_uid)
    else:
        print("Empty object")
    """Un-Freeze QT interface"""
    self.enable_actions()


def copy_similar(self):  # this must be done per-part_______________________________________________________
    """Similar folding. Create a line copied and translated from a template line."""
    print("Copy Similar. Create a line copied and translated.")
    """Terminate running event loops"""
    self.stop_event_loops()
    """Check if a line is selected"""
    if not self.selected_uids:
        print(" -- No input data selected -- ")
        return
    if (self.parent.geol_coll.get_uid_topological_type(self.selected_uids[0]) != "PolyLine") and (
            self.parent.geol_coll.get_uid_topological_type(self.selected_uids[0]) != "XsPolyLine"):
        print(" -- Selected data is not a line -- ")
        return
    """Freeze QT interface"""
    for action in self.findChildren(QAction):
        if isinstance(action.parentWidget(), NavigationToolbar) is False:
            action.setDisabled(True)
    """If more than one line is selected, keep the first."""
    input_uid = self.selected_uids[0]
    """IN THE FUTURE add a test to check that the selected feature is a geological feature"""
    """Create empty dictionary for the output line and set name and geological_type.
    IN THE FUTURE see if other metadata should be automatically set."""
    line_dict = deepcopy(self.parent.geol_coll.geological_entity_dict)
    line_dict['geological_type'] = \
        self.parent.geol_coll.df.loc[self.parent.geol_coll.df['uid'] == input_uid, 'geological_type'].values[0]
    line_dict['geological_feature'] = self.parent.geol_coll.get_uid_geological_feature(self.selected_uids[0])
    line_dict['scenario'] = self.parent.geol_coll.get_uid_scenario(self.selected_uids[0])
    if isinstance(self, ViewMap):
        line_dict['vtk_obj'] = PolyLine()
        line_dict['topological_type'] = 'PolyLine'
    elif isinstance(self, ViewXsection):
        line_dict['vtk_obj'] = XsPolyLine(self.this_x_section_uid, parent=self.parent)
        line_dict['topological_type'] = 'XsPolyLine'
        line_dict['x_section'] = self.this_x_section_uid
    """Get coordinates of input line."""
    inX = self.parent.geol_coll.get_uid_vtk_obj(input_uid).points_X
    inY = self.parent.geol_coll.get_uid_vtk_obj(input_uid).points_Y
    inZ = self.parent.geol_coll.get_uid_vtk_obj(input_uid).points_Z
    """Get similar folding vector."""
    self.vector_by_mouse(verbose=True)
    if not self.vbm_U0:
        """Deselect input line."""
        self.selected_uids = []
        self.parent.geology_geom_modified_signal.emit([input_uid])  # emit uid as list to force redraw()
        print("Zero-length vector")
        """Un-Freeze QT interface"""
        for action in self.findChildren(QAction):
            action.setEnabled(True)
        return
    """Create output line."""
    if isinstance(self, ViewMap):
        outX = inX + vector_by_mouse_dU
        outY = inY + vector_by_mouse_dV
        outZ = np_zeros(np_shape(outX))
    elif isinstance(self, ViewXsection):
        vector_by_mouse_dX, vector_by_mouse_dY = self.parent.xsect_coll.get_deltaXY_from_deltaW(
            section_uid=self.this_x_section_uid, deltaW=vector_by_mouse_dU)
        outX = inX + vector_by_mouse_dX
        outY = inY + vector_by_mouse_dY
        outZ = inZ + vector_by_mouse_dV
    """Stack coordinates in two-columns matrix and write to vtk object."""
    outXYZ = np_column_stack((outX, outY, outZ))
    line_dict['vtk_obj'].points = outXYZ
    line_dict['vtk_obj'].auto_cells()
    """Set output line name."""
    in_line_name = self.parent.geol_coll.df.loc[self.parent.geol_coll.df['uid'] == input_uid, 'name'].values[0]
    distance = self.vector_by_mouse_length
    out_line_name = in_line_name + '_simi_' + '%d' % distance

    line_dict['name'] = out_line_name
    """Create entity from the dictionary and run left_right."""
    output_uid = self.parent.geol_coll.add_entity_from_dict(line_dict)
    left_right(output_uid)
    """Deselect input line."""
    if line_dict['vtk_obj'].points_number > 0:
        self.selected_uids = []
        self.parent.geology_geom_modified_signal.emit([input_uid])  # emit uid as list to force redraw()
    else:
        print("Empty object")
    """Un-Freeze QT interface"""
    for action in self.findChildren(QAction):
        action.setEnabled(True)


def measure_distance(self):
    """Tool to measure distance between two points. Draw a vector_by_mouse and obtain length and azimuth"""
    print("Measure Distance between two points by drawing a vector by mouse")
    """Terminate running event loops"""
    self.stop_event_loops()
    """Freeze QT interface"""
    for action in self.findChildren(QAction):
        if isinstance(action.parentWidget(), NavigationToolbar) is False:
            action.setDisabled(True)
    self.vector_by_mouse(verbose=True)
    if not self.vbm_U0:
        print("Zero-length vector")
        self.vector_by_mouse_azimuth = 0
        self.vector_by_mouse_length = 0
    message = "Distance (m): " + str(round(self.vector_by_mouse_length, 2)) + "\n\n" + "Azimuth: " + str(
        round(self.vector_by_mouse_azimuth, 2))
    out = message_dialog(title="Measure Distance", message=message)
    """Un-Freeze QT interface"""
    for action in self.findChildren(QAction):
        action.setEnabled(True)


"""Helper and shared functions"""


def flip_line(self, uid=None):
    """Ensures lines are oriented left-to-right and bottom-to-top"""
    # self.parent.geol_coll.get_uid_vtk_obj(uid).points = np_flip(self.parent.geol_coll.get_uid_vtk_obj(uid).points, 0)
    self.parent.geol_coll.get_uid_vtk_obj(uid).points = np_flip(self.parent.geol_coll.get_uid_vtk_obj(uid).points, 0)


def left_right(self, uid=None):
    """Ensures lines are oriented left-to-right and bottom-to-top in map or cross-section"""
    if isinstance(self, ViewMap):
        U_line = self.parent.geol_coll.get_uid_vtk_obj(uid).points_X
        V_line = self.parent.geol_coll.get_uid_vtk_obj(uid).points_Y
    elif isinstance(self, ViewXsection):
        U_line = self.parent.geol_coll.get_uid_vtk_obj(uid).points_W
        V_line = self.parent.geol_coll.get_uid_vtk_obj(uid).points_Z
    else:
        return
    if U_line[0] > U_line[-1]:  # reverse if right-to-left
        flip_line(uid=uid)
    elif U_line[0] == U_line[-1] and V_line[0] > V_line[-1]:  # reverse if vertical up-to-down
        flip_line(uid=uid)
