from vtkmodules.vtkCommonCore import vtkCommand
from vtkmodules.vtkInteractionWidgets import vtkContourWidget, vtkLinearContourLineInterpolator, vtkBrokenLineWidget

from numpy import array as np_array
from pyvista import wrap as pv_wrap


class Tracer(vtkContourWidget):
    def __init__(self, parent=None, pass_func=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.parent = parent
        self.SetInteractor(self.parent.plotter.iren.interactor)
        head = pv_wrap(self.GetContourRepresentation().GetActiveCursorShape())
        self.GetContourRepresentation().SetCursorShape(head)
        self.GetContourRepresentation().SetLineInterpolator(vtkLinearContourLineInterpolator())
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
        self.GetContourRepresentation().SetLineInterpolator(vtkLinearContourLineInterpolator())
        head = pv_wrap(self.GetContourRepresentation().GetActiveCursorShape()).scale(0.5, 0.5, 0.5)
        self.GetContourRepresentation().SetCursorShape(head)
        self.GetContourRepresentation().SetLineInterpolator(vtkLinearContourLineInterpolator())
        self.GetContourRepresentation().GetProperty().SetColor((255, 0, 0))
        self.GetContourRepresentation().GetProperty().SetPointSize(0)
        self.GetContourRepresentation().GetActiveProperty().SetColor((255, 0, 0))
        self.GetContourRepresentation().GetLinesProperty().SetLineWidth(5)
        self.GetContourRepresentation().GetLinesProperty().SetColor((255, 0, 0))
        self.ContinuousDrawOff()
        self.FollowCursorOn()
        self.AddObserver(vtkCommand.InteractionEvent, self.check_length)
        self.run_function = pass_func

    def check_length(self, event1, event2):
        n_nodes = self.GetContourRepresentation().GetNumberOfNodes()
        if n_nodes == 3:
            pld = self.GetContourRepresentation().GetContourRepresentationAsPolyData()
            points = np_array(pld.GetPoints().GetData())[:2, :]
            self.EnabledOff()
            self.run_function(self.parent, points)


class Editor(vtkBrokenLineWidget):
    def __init__(self, parent=None, pass_func=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.parent = parent
        self.SetInteractor(self.parent.plotter.iren.interactor)
        # head = pv_wrap(self.GetContourRepresentation().GetActiveCursorShape())
        # self.GetContourRepresentation().SetCursorShape(head)
        # self.GetContourRepresentation().SetLineInterpolator(vtkLinearContourLineInterpolator())
        # self.GetContourRepresentation().GetLinesProperty().SetLineWidth(3)
        # self.GetContourRepresentation().GetProperty().SetColor((255, 255, 255))
        # self.GetContourRepresentation().GetActiveProperty().SetColor((255, 0, 0))
        #
        # self.ContinuousDrawOff()
        # self.FollowCursorOn()
        # self.AllowNodePickingOn()
        # self.event_translator = self.GetEventTranslator()
        # self.event_translator.RemoveTranslation(vtkCommand.RightButtonPressEvent)
        # self.event_translator.RemoveTranslation(vtkCommand.LeftButtonPressEvent)
    #     self.AddObserver(vtkCommand.StartInteractionEvent, self.point_selected)
    #     self.run_function = pass_func
    #
    # def point_selected(self, event1, event2):
    #     pos = self.parent.plotter.mouse_position
    #
    #     event1.GetContourRepresentation().AddNodeAtWorldPosition()


