"""helper_widgets.py
PZero© Andrea Bistacchi"""

from math import degrees, atan2, sqrt, asin

from numpy import array as np_array
from numpy import flip as np_flip

from pyvista import lines_from_points as pv_line_from_points
from pyvista import wrap as pv_wrap

from vtkmodules.vtkCommonCore import vtkCommand
from vtkmodules.vtkInteractionWidgets import (
    vtkContourWidget,
    vtkLinearContourLineInterpolator,
)


class Tracer(vtkContourWidget):
    def __init__(self, parent=None, pass_func=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.parent = parent
        self.SetInteractor(self.parent.plotter.iren.interactor)
        head = pv_wrap(self.GetContourRepresentation().GetActiveCursorShape())
        self.GetContourRepresentation().SetCursorShape(head)
        self.GetContourRepresentation().SetLineInterpolator(
            vtkLinearContourLineInterpolator()
        )
        self.GetContourRepresentation().GetLinesProperty().SetLineWidth(3)
        self.GetContourRepresentation().GetProperty().SetColor((255, 255, 255))
        self.GetContourRepresentation().GetActiveProperty().SetColor((255, 0, 0))

        self.ContinuousDrawOff()
        self.FollowCursorOn()
        self.event_translator = self.GetEventTranslator()
        self.event_translator.RemoveTranslation(vtkCommand.RightButtonPressEvent)


class Vector(vtkContourWidget):
    def __init__(self, parent=None, pass_func=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.parent = parent
        self.SetInteractor(self.parent.plotter.iren.interactor)
        self.GetContourRepresentation().SetLineInterpolator(
            vtkLinearContourLineInterpolator()
        )
        head = pv_wrap(self.GetContourRepresentation().GetActiveCursorShape()).scale(
            0.5, 0.5, 0.5
        )
        self.GetContourRepresentation().SetCursorShape(head)
        self.GetContourRepresentation().SetLineInterpolator(
            vtkLinearContourLineInterpolator()
        )
        self.GetContourRepresentation().GetProperty().SetColor((255, 0, 0))
        self.GetContourRepresentation().GetProperty().SetPointSize(0)
        self.GetContourRepresentation().GetActiveProperty().SetColor((255, 0, 0))
        self.GetContourRepresentation().GetLinesProperty().SetLineWidth(5)
        self.GetContourRepresentation().GetLinesProperty().SetColor((255, 0, 0))
        self.ContinuousDrawOff()
        self.FollowCursorOn()
        self.AddObserver(vtkCommand.InteractionEvent, self.check_length)
        self.event_translator = self.GetEventTranslator()
        self.event_translator.RemoveTranslation(vtkCommand.RightButtonPressEvent)
        self.run_function = pass_func
        self.length = 0
        self.deltas = 0
        self.azimuth = 0
        self.dip = 0
        self.p1 = [0, 0, 0]
        self.p2 = [0, 0, 0]
        self.line = None

    def check_length(self, event1, event2):
        n_nodes = self.GetContourRepresentation().GetNumberOfNodes()
        if n_nodes == 3:
            pld = self.GetContourRepresentation().GetContourRepresentationAsPolyData()
            self.GetContourRepresentation().GetNthNodeWorldPosition(0, self.p1)
            self.GetContourRepresentation().GetNthNodeWorldPosition(1, self.p2)
            self.deltas = np_array(self.p2) - np_array(self.p1)
            self.length = sqrt(
                self.deltas[0] ** 2 + self.deltas[1] ** 2 + self.deltas[2] ** 2
            )
            self.azimuth = degrees(atan2(self.deltas[0], self.deltas[1])) % 360
            self.line = pv_line_from_points(np_array([self.p1, self.p2]))
            # self.points = np_array(pld.GetPoints().GetData())[:2, :]
            self.dip = degrees(asin(abs(self.deltas[2] / self.length))) % 90

            # print(self.length)
            self.EnabledOff()
            self.run_function(self.parent, vector=self)


class Editor(vtkContourWidget):
    def __init__(self, parent=None, pass_func=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.parent = parent
        self.SetInteractor(self.parent.plotter.iren.interactor)
        # self.GetContourRepresentation().BuildRepresentation()
        # self.GetContourRepresentation().ShowSelectedNodesOn()
        head = pv_wrap(self.GetContourRepresentation().GetActiveCursorShape())
        self.pos_fin = [0, 0]
        self.active_pos = [0, 0, 0]
        self.active_ind = 0
        self.event_translator = self.GetEventTranslator()

        self.GetContourRepresentation().SetCursorShape(head)
        self.GetContourRepresentation().SetLineInterpolator(
            vtkLinearContourLineInterpolator()
        )
        self.GetContourRepresentation().GetLinesProperty().SetLineWidth(3)
        self.GetContourRepresentation().GetProperty().SetColor((255, 255, 255))
        self.GetContourRepresentation().GetActiveProperty().SetColor((255, 0, 0))
        self.ContinuousDrawOff()

    def initialize(self, line, mode):
        if mode == "edit":
            if mode == "edit":
                self.Initialize(line)
                self.FollowCursorOn()
                self.event_translator = self.GetEventTranslator()
                self.event_translator.RemoveTranslation(
                    vtkCommand.RightButtonPressEvent
                )

        elif mode == "extend":
            self.Initialize(line, 0)
            self.ContinuousDrawOff()
            self.FollowCursorOff()
            self.AllowNodePickingOn()

            self.event_translator.RemoveTranslation(vtkCommand.RightButtonPressEvent)
            self.event_translator.RemoveTranslation(vtkCommand.LeftButtonPressEvent)
            f_node = self.GetContourRepresentation().GetNumberOfNodes() - 1
            self.GetContourRepresentation().GetNthNodeDisplayPosition(
                f_node, self.pos_fin
            )
            self.GetContourRepresentation().ActivateNode(self.pos_fin)
            self.Render()
            self.parent.plotter.track_click_position(
                side="left", callback=self.extend_line, viewport=True
            )
            self.parent.plotter.add_key_event("k", self.switch_active)
        elif mode == "select":
            self.Initialize(line, 0)
            self.ContinuousDrawOff()
            self.FollowCursorOff()
            self.AllowNodePickingOn()

            self.event_translator.RemoveTranslation(vtkCommand.RightButtonPressEvent)
            self.event_translator.RemoveTranslation(vtkCommand.LeftButtonPressEvent)
            self.Render()
            self.parent.plotter.track_click_position(
                side="left", callback=self.select_point, viewport=True
            )

    def extend_line(self, event=None):
        f_node = self.GetContourRepresentation().GetNumberOfNodes()
        self.GetContourRepresentation().AddNodeAtDisplayPosition(event)
        self.GetContourRepresentation().GetNthNodeDisplayPosition(f_node, self.pos_fin)
        self.GetContourRepresentation().ActivateNode(self.pos_fin)
        self.Render()

    def select_point(self, event=None):
        self.GetContourRepresentation().ActivateNode(event)
        self.GetContourRepresentation().GetActiveNodeWorldPosition(self.active_pos)
        self.Render()

    def switch_active(self):
        line = pv_wrap(
            self.GetContourRepresentation().GetContourRepresentationAsPolyData()
        )
        points = line.points
        p_flip = np_flip(points, axis=0)
        # line = pv.lines_from_points(p_flip)
        self.GetContourRepresentation().ClearAllNodes()
        for point in p_flip:
            self.GetContourRepresentation().AddNodeAtWorldPosition(point)
        self.Render()


class Scissors(vtkContourWidget):
    def __init__(self, parent=None, pass_func=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.parent = parent
        self.SetInteractor(self.parent.plotter.iren.interactor)
        head = pv_wrap(self.GetContourRepresentation().GetActiveCursorShape())
        self.GetContourRepresentation().SetCursorShape(head)
        self.GetContourRepresentation().SetLineInterpolator(
            vtkLinearContourLineInterpolator()
        )
        self.GetContourRepresentation().GetLinesProperty().SetLineWidth(3)
        self.GetContourRepresentation().GetProperty().SetColor((255, 255, 255))
        self.GetContourRepresentation().GetActiveProperty().SetColor((255, 0, 0))

        self.ContinuousDrawOff()
        self.FollowCursorOn()
        self.event_translator = self.GetEventTranslator()
        self.event_translator.RemoveTranslation(vtkCommand.RightButtonPressEvent)
