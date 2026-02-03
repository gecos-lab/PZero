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
        # avoid overriding vtk SetParent; store UI parent separately
        self._parent = parent
        self.SetInteractor(self._parent.plotter.iren.interactor)
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
        # hold event translator in Python attribute to avoid VTK attribute conflict
        self._event_translator = self.GetEventTranslator()
        self._event_translator.RemoveTranslation(vtkCommand.RightButtonPressEvent)


class Vector(vtkContourWidget):
    def __init__(self, parent=None, pass_func=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # avoid overriding vtk SetParent; store UI parent separately
        self._parent = parent
        self.SetInteractor(self._parent.plotter.iren.interactor)
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
        # hold event translator in Python attribute to avoid VTK attribute conflict
        self._event_translator = self.GetEventTranslator()
        self._event_translator.RemoveTranslation(vtkCommand.RightButtonPressEvent)
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
            # invoke callback with original parent
            self.run_function(self._parent, vector=self)


class Tracer3D:
    """A 3D line drawing tool that uses point picking for better 3D interaction.
    Click on surfaces to add points, right-click to finish."""
    
    def __init__(self, parent=None):
        self._parent = parent
        self.points = []
        self.line_actor = None
        self.temp_line_actor = None
        self.point_actors = []
        self.is_active = False
        
    def enable(self):
        """Enable the 3D line drawing mode."""
        self.is_active = True
        self.points = []
        self.line_actor = None
        self.temp_line_actor = None
        self.point_actors = []
        
    def disable(self):
        """Disable the 3D line drawing mode and clean up."""
        self.is_active = False
        self._cleanup_visuals()
        
    def _cleanup_visuals(self):
        """Remove all visual elements."""
        if self.line_actor and hasattr(self._parent, 'plotter'):
            try:
                self._parent.plotter.remove_actor(self.line_actor)
            except:
                pass
        if self.temp_line_actor and hasattr(self._parent, 'plotter'):
            try:
                self._parent.plotter.remove_actor(self.temp_line_actor)
            except:
                pass
        for actor in self.point_actors:
            try:
                self._parent.plotter.remove_actor(actor)
            except:
                pass
        self.line_actor = None
        self.temp_line_actor = None
        self.point_actors = []

    def _compute_point_radius(self, point):
        """Compute a screen-consistent radius that scales down when zooming in."""
        import math

        try:
            renderer = self._parent.plotter.renderer
            camera = renderer.GetActiveCamera()
            bounds = renderer.ComputeVisiblePropBounds()
            scene_size = max(
                bounds[1] - bounds[0],
                bounds[3] - bounds[2],
                bounds[5] - bounds[4],
            )
            # Determine viewport height in pixels
            try:
                render_window = renderer.GetRenderWindow()
                _, height_px = render_window.GetSize()
            except Exception:
                _, height_px = renderer.GetSize()
            height_px = max(height_px, 1)

            if camera.GetParallelProjection():
                parallel_scale = camera.GetParallelScale() or (scene_size * 0.5)
                world_per_pixel = (2.0 * parallel_scale) / height_px
            else:
                cam_pos = camera.GetPosition()
                dist = math.sqrt(
                    (cam_pos[0] - point[0]) ** 2
                    + (cam_pos[1] - point[1]) ** 2
                    + (cam_pos[2] - point[2]) ** 2
                )
                view_angle = camera.GetViewAngle()
                world_per_pixel = (
                    2.0 * dist * math.tan(math.radians(view_angle * 0.5))
                ) / height_px

            desired_px = 4.0
            radius = world_per_pixel * desired_px

            if scene_size > 0:
                min_radius = scene_size * 0.001
                max_radius = scene_size * 0.02
                radius = min(max(radius, min_radius), max_radius)

            return radius
        except Exception:
            return None
        
    def add_point(self, point):
        """Add a point to the line being drawn."""
        import pyvista as pv
        import numpy as np
        
        # Convert to tuple if needed
        if isinstance(point, np.ndarray):
            point = tuple(point)
        
        self.points.append(point)
        
        # Calculate appropriate sphere radius based on scene bounds
        sphere_radius = self._compute_point_radius(point)
        if not sphere_radius:
            try:
                bounds = self._parent.plotter.renderer.ComputeVisiblePropBounds()
                scene_size = max(
                    bounds[1] - bounds[0],
                    bounds[3] - bounds[2],
                    bounds[5] - bounds[4],
                )
                sphere_radius = scene_size * 0.01  # 1% of scene size
            except Exception:
                sphere_radius = 10  # Fallback radius
        
        # Add a sphere at the point location for visual feedback
        sphere = pv.Sphere(radius=sphere_radius, center=point, theta_resolution=16, phi_resolution=16)
        actor = self._parent.plotter.add_mesh(
            sphere, color='red', opacity=0.9, pickable=False, lighting=True
        )
        self.point_actors.append(actor)
        
        # Update the line visualization
        if len(self.points) >= 2:
            self._update_line()
        
        self._parent.plotter.render()
        
    def _update_line(self):
        """Update the line visualization."""
        import pyvista as pv
        import numpy as np
        
        # Remove old line actor
        if self.line_actor:
            try:
                self._parent.plotter.remove_actor(self.line_actor)
            except:
                pass
        
        # Create new line from all points
        line = pv.lines_from_points(np.array(self.points))
        self.line_actor = self._parent.plotter.add_mesh(
            line, color='yellow', line_width=5, pickable=False, lighting=False
        )
        
    def update_temp_line(self, current_pos):
        """Show a temporary line from the last point to current mouse position."""
        import pyvista as pv
        import numpy as np
        
        if len(self.points) == 0:
            return
            
        # Remove old temp line
        if self.temp_line_actor:
            try:
                self._parent.plotter.remove_actor(self.temp_line_actor)
            except:
                pass
        
        # Create temp line from last point to current position
        temp_line = pv.lines_from_points(np.array([self.points[-1], current_pos]))
        self.temp_line_actor = self._parent.plotter.add_mesh(
            temp_line, color='gray', line_width=1, opacity=0.5, pickable=False
        )
        self._parent.plotter.render()
        
    def get_polydata(self):
        """Get the final polydata object."""
        import pyvista as pv
        import numpy as np
        
        if len(self.points) < 2:
            return None
        
        # Create polydata from points
        line = pv.lines_from_points(np.array(self.points))
        return line


class Editor(vtkContourWidget):
    def __init__(self, parent=None, pass_func=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # avoid overriding vtk SetParent; store UI parent separately
        self._parent = parent
        self.SetInteractor(self._parent.plotter.iren.interactor)
        # self.GetContourRepresentation().BuildRepresentation()
        # self.GetContourRepresentation().ShowSelectedNodesOn()
        head = pv_wrap(self.GetContourRepresentation().GetActiveCursorShape())
        self.pos_fin = [0, 0]
        self.active_pos = [0, 0, 0]
        self.active_ind = 0
        # hold event translator in Python attribute to avoid VTK attribute conflict
        self._event_translator = self.GetEventTranslator()

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
            self._event_translator.RemoveTranslation(vtkCommand.RightButtonPressEvent)
            self._event_translator.RemoveTranslation(vtkCommand.LeftButtonPressEvent)
            f_node = self.GetContourRepresentation().GetNumberOfNodes() - 1
            self.GetContourRepresentation().GetNthNodeDisplayPosition(
                f_node, self.pos_fin
            )
            self.GetContourRepresentation().ActivateNode(self.pos_fin)
            self.Render()
            # set up callback and key for extending line
            self._parent.plotter.track_click_position(
                side="left", callback=self.extend_line, viewport=True
            )
            self._parent.plotter.add_key_event("k", self.switch_active)
        elif mode == "select":
            self.Initialize(line, 0)
            self.ContinuousDrawOff()
            self.FollowCursorOff()
            self.AllowNodePickingOn()

            self._event_translator.RemoveTranslation(vtkCommand.RightButtonPressEvent)
            self._event_translator.RemoveTranslation(vtkCommand.LeftButtonPressEvent)
            self.Render()
            self._parent.plotter.track_click_position(
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
        # avoid overriding vtk SetParent; store UI parent separately
        self._parent = parent
        self.SetInteractor(self._parent.plotter.iren.interactor)
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
        # hold event translator in Python attribute to avoid VTK attribute conflict
        self._event_translator = self.GetEventTranslator()
        self._event_translator.RemoveTranslation(vtkCommand.RightButtonPressEvent)
