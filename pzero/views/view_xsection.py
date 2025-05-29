"""view_xsection.py
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

# numpy import____
from numpy import array as np_array

# PyVista imports____
from pyvista import Arrow as pv_Arrow

# PZero imports____
from .abstract_view_2d import View2D
from ..helpers.helper_dialogs import input_combo_dialog, message_dialog


class ViewXsection(View2D):
    def __init__(self, parent=None, *args, **kwargs):
        # Choose section name with dialog.
        if parent.xsect_coll.get_names:
            self.this_x_section_name = input_combo_dialog(
                parent=None,
                title="Xsection",
                label="Choose Xsection",
                choice_list=parent.xsect_coll.get_names,
            )
        else:
            message_dialog(title="Xsection", message="No Xsection in project")
            return
        # Select section uid from name.
        if self.this_x_section_name:
            self.this_x_section_uid = parent.xsect_coll.df.loc[
                parent.xsect_coll.df["name"] == self.this_x_section_name, "uid"
            ].values[0]
        else:
            return
        # Set filter for entities belonging to this cross section.
        self.view_filter = f'x_section == "{self.this_x_section_uid}"'

        # Super here after having set the x_section_uid and _name
        super(ViewXsection, self).__init__(parent, *args, **kwargs)

        # Rename Base View, Menu and Tool
        self.setWindowTitle(f"Xsection View: {self.this_x_section_name}")

        # Store center and direction in internal variables of this view
        section_plane = parent.xsect_coll.get_uid_vtk_plane(self.this_x_section_uid)
        self.center = np_array(section_plane.GetOrigin())
        self.direction = np_array(section_plane.GetNormal())
        # Apply to plotter
        self.plotter.camera.focal_point = self.center
        self.plotter.camera.position = self.center + self.direction
        self.plotter.reset_camera()

    # Update the views depending on the sec_uid. We need to redefine the functions to use
    # the sec_uid parameter for the update_dom_list_added func. We just need the x_added_x
    # functions because the x_removed_x works on an already built/modified tree.

    def initialize_menu_tools(self):
        """This is the intermediate method of the VTKView() abstract class, used to add menu tools used by all VTK windows.
        The code appearing here is appended in subclasses using super().initialize_menu_tools() in their first line.
        """
        # append code from BaseView()
        super().initialize_menu_tools()

        self.horizMirrorButton = QAction("Mirror horizontal axes", self)
        self.horizMirrorButton.triggered.connect(self.horizontal_mirror)
        self.menuView.addAction(self.horizMirrorButton)

    def set_orientation_widget(self):
        self.plotter.add_orientation_widget(
            pv_Arrow(direction=(0.0, 1.0, 0.0), scale=0.3),
            interactive=None,
            color="gold",
        )

    def horizontal_mirror(self):
        """Mirror horizontal axes."""
        self.print_terminal("Mirroring horizontal axes.")
        # Mirror internal variable used to store direction
        self.direction = -self.direction
        # Apply to plotter
        self.plotter.camera.focal_point = self.center
        self.plotter.camera.position = self.center + self.direction
        self.plotter.reset_camera()

