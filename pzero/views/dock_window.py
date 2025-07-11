"""dock_window.py
PZero© Andrea Bistacchi"""

# PySide6 imports____
from PySide6.QtWidgets import QDockWidget
from PySide6.QtCore import Qt

# PZero imports____
from .view_3d import View3D
from .view_map import ViewMap
from .view_xsection import ViewXsection
from .view_stereoplot import ViewStereoplot
from .abstract_view_vtk import ViewVTK


class DockWindow(QDockWidget):
    """Creates a QDockWidget and then fills it with a single QWidget that includes all objects of a dockable graphical window.
    Each window needs its specific dock widget in order to be dockable, movable anc closable independently.
    In the following code, copied from Qt Designer (Form > View Python code - layout saved as project_window_with_dock_widget.ui),
    the dock widget is locked to the right dock area, floatable, movable and closable, hence it will only appear in the
    right dock area or undocked on the desktop."""

    def __init__(self, parent=None, window_type=None, *args, **kwargs):
        super(DockWindow, self).__init__(parent, *args, **kwargs)
        n_docks = len(parent.findChildren(QDockWidget))

        # Connect signal and set attribute to delete dock widget (not only hide it) when the project is closed.
        parent.signals.project_close.connect(self.deleteLater)
        self.setAttribute(Qt.WA_DeleteOnClose, True)

        # Set other dock window graphical properties.
        self.sizePolicy().setHorizontalStretch(2)
        self.setWindowTitle(window_type)
        self.setFeatures(
            QDockWidget.DockWidgetClosable
            | QDockWidget.DockWidgetFloatable
            | QDockWidget.DockWidgetMovable
        )
        self.setAllowedAreas(Qt.RightDockWidgetArea)

        # Create the graphical window as a QWidget to be included in the QDockWidget as its canvas content
        # This list must be updated if new window classes are added.
        if window_type == "View3D":
            self.canvas = View3D(parent=parent)
        elif window_type == "ViewMap":
            self.canvas = ViewMap(parent=parent)
        elif window_type == "ViewXsection":
            self.canvas = ViewXsection(parent=parent)
        elif window_type == "ViewStereoplot":
            self.canvas = ViewStereoplot(parent=parent)
        else:
            # Exit doing nothing in case the window type is not supported/recognized.
            print("window type not recognized")
            return

        # Add the content widget to the dock widget and add the dock widget to the main project window.
        # After this has been set, calling self.canvas returns the same object as calling self.widget().
        self.setWidget(self.canvas)
        parent.addDockWidget(Qt.RightDockWidgetArea, self)

        # Make all dock widgets tabbed if more than one is open.
        if n_docks > 1:
            parent.tabifyDockWidget(parent.findChildren(QDockWidget)[0], self)
        else:
            if window_type == "View3D":
                parent.print_terminal(
                    "Warning: as far as the orientation widget problem is not solved, please resize the window to make it smaller.\n"
                )

    def closeEvent(self, event):
        """Override the standard closeEvent method in two cases:
        1) when a window is floating, "closing" it actually brings it back in
        the docking area;
        2) when really closing/deleting a window, self.plotter.close() is needed
        to cleanly close the vtk plotter and disconnect_all_lambda_signals."""
        # Case to send floating window back to docking area.
        if self.isFloating():
            self.setFloating(False)
            event.ignore()
            return
        # Case to actually close/delete a window, disconnecting all signals
        # of BaseView(), then cleanly close the VTK plotter.
        self.canvas.enable_actions()
        self.canvas.disconnect_all_signals()
        if isinstance(self.canvas, ViewVTK):
            self.canvas.plotter.close()
