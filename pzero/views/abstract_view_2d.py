"""abstract_view_2d.py
PZero© Andrea Bistacchi"""

# PySide6 imports____
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QMainWindow,
    QMenu,
    QAbstractItemView,
    QDockWidget,
    QSizePolicy,
    QMessageBox,
)

# PZero imports____
from .abstract_view_vtk import ViewVTK
from ..helpers.helper_widgets import Vector


class View2D(ViewVTK):
    """Create 2D view using vtk/pyvista. This should be more efficient than matplotlib"""

    def __init__(self, *args, **kwargs):
        super(View2D, self).__init__(*args, **kwargs)

        self.line_dict = None
        self.plotter.enable_image_style()
        self.plotter.enable_parallel_projection()

    # Re-implementations of functions that appear in all views - see placeholders in BaseView()

    def end_pick(self, pos):
        """Function used to disable actor picking. Due to some slight difference,
        must be reimplemented in subclasses."""
        # Remove the selector observer
        self.plotter.iren.interactor.RemoveObservers(
            "LeftButtonPressEvent"
        )
        # Remove the right click observer
        self.plotter.untrack_click_position(
            side="right"
        )
        # Remove the left click observer
        self.plotter.untrack_click_position(
            side="left"
        )
        # self.plotter.track_click_position(
        #    lambda pos: self.plotter.camera.SetFocalPoint(pos), side="left", double=True
        # )
        # Specific to View3D() implementation.
        self.plotter.enable_image_style()
        # Closing settings
        self.plotter.reset_key_events()
        self.selected_uids = self.parent.selected_uids
        self.enable_actions()

    def initialize_menu_tools(self):
        from ..two_d_lines import (
            draw_line,
            edit_line,
            sort_line_nodes,
            move_line,
            rotate_line,
            extend_line,
            split_line_line,
            split_line_existing_point,
            merge_lines,
            snap_line,
            resample_lines_distance,
            resample_lines_number_points,
            simplify_line,
            copy_parallel,
            copy_kink,
            copy_similar,
            measure_distance,
            clean_intersection,
        )

        # Imports for this view.
        # Customize menus and tools for this view
        super().initialize_menu_tools()
        # self.menuBaseView.setTitle("Edit")
        # self.actionBase_Tool.setText("Edit")

        # ------------------------------------
        # CONSIDER MOVING SOME OF THE FOLLOWING METHODS TO VTKView(), IN ORDER TO HAVE THEM ALSO IN 3D VIEWS
        # ------------------------------------

        self.drawLineButton = QAction("Draw line", self)
        self.drawLineButton.triggered.connect(lambda: draw_line(self))
        self.menuCreate.addAction(self.drawLineButton)

        self.editLineButton = QAction("Edit line", self)
        self.editLineButton.triggered.connect(lambda: edit_line(self))
        self.menuModify.addAction(self.editLineButton)

        self.sortLineButton = QAction("Sort line nodes", self)
        self.sortLineButton.triggered.connect(lambda: sort_line_nodes(self))
        self.menuModify.addAction(self.sortLineButton)

        self.moveLineButton = QAction("Move line", self)
        self.moveLineButton.triggered.connect(lambda: self.vector_by_mouse(move_line))
        self.menuModify.addAction(self.moveLineButton)

        self.rotateLineButton = QAction("Rotate line", self)
        self.rotateLineButton.triggered.connect(lambda: rotate_line(self))
        self.menuModify.addAction(self.rotateLineButton)

        self.extendButton = QAction("Extend line", self)
        self.extendButton.triggered.connect(lambda: extend_line(self))
        self.menuModify.addAction(self.extendButton)

        self.splitLineByLineButton = QAction("Split line-line", self)
        self.splitLineByLineButton.triggered.connect(lambda: split_line_line(self))
        self.menuModify.addAction(self.splitLineByLineButton)

        self.splitLineByPointButton = QAction("Split line-point", self)
        self.splitLineByPointButton.triggered.connect(
            lambda: split_line_existing_point(self)
        )
        self.menuModify.addAction(self.splitLineByPointButton)

        self.mergeLineButton = QAction("Merge lines", self)
        self.mergeLineButton.triggered.connect(lambda: merge_lines(self))
        self.menuModify.addAction(self.mergeLineButton)

        self.snapLineButton = QAction("Snap line", self)
        self.snapLineButton.triggered.connect(lambda: snap_line(self))
        self.menuModify.addAction(self.snapLineButton)

        self.resampleDistanceButton = QAction("Resample distance", self)
        self.resampleDistanceButton.triggered.connect(
            lambda: resample_lines_distance(self)
        )
        self.menuModify.addAction(self.resampleDistanceButton)

        self.resampleNumberButton = QAction("Resample number", self)
        self.resampleNumberButton.triggered.connect(
            lambda: resample_lines_number_points(self)
        )
        self.menuModify.addAction(self.resampleNumberButton)

        self.simplifyButton = QAction("Simplify line", self)
        self.simplifyButton.triggered.connect(lambda: simplify_line(self))
        self.menuModify.addAction(self.simplifyButton)

        self.copyParallelButton = QAction("Copy parallel", self)
        self.copyParallelButton.triggered.connect(lambda: copy_parallel(self))
        self.menuCreate.addAction(self.copyParallelButton)

        self.copyKinkButton = QAction("Copy kink", self)
        self.copyKinkButton.triggered.connect(lambda: copy_kink(self))
        self.menuCreate.addAction(self.copyKinkButton)

        self.copySimilarButton = QAction("Copy similar", self)
        self.copySimilarButton.triggered.connect(
            lambda: self.vector_by_mouse(copy_similar)
        )
        self.menuCreate.addAction(self.copySimilarButton)

        self.measureDistanceButton = QAction("Measure", self)
        self.measureDistanceButton.triggered.connect(
            lambda: self.vector_by_mouse(measure_distance)
        )
        self.menuView.addAction(self.measureDistanceButton)

        self.cleanSectionButton = QAction("Clean intersections", self)
        self.cleanSectionButton.triggered.connect(lambda: clean_intersection(self))
        self.menuModify.addAction(self.cleanSectionButton)

    def vector_by_mouse(self, func):
        # if not self.selected_uids:
        #     print(" -- No input data selected -- ")
        #     return
        self.disable_actions()
        vector = Vector(parent=self, pass_func=func)
        vector.EnabledOn()
