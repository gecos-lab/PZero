"""view_xsection.py
PZero© Andrea Bistacchi"""

# PySide6 imports____
from PySide6.QtGui import QAction

# numpy import____
from numpy import array as np_array

# PyVista imports____
from pyvista import Arrow as pv_Arrow

# PZero imports____
from .abstract_view_2d import View2D
from vtkmodules.vtkFiltersCore import vtkAppendPolyData
from pyvista import Line as pv_Line
from .view_map import ViewMap
from ..orientation_analysis import get_dip_dir_vectors
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
        # Note that this filter does not return the cross section itself. If we want its frame to be shown we must
        # find a different solution to add it to the plotter.
        self.view_filter = (
            f'x_section.str.contains("{self.this_x_section_uid}", na=False)'
        )

        # Super here after having set the x_section_uid and _name
        super(ViewXsection, self).__init__(parent, *args, **kwargs)
        self.parent.signals.selection_changed.connect(self.on_selection_changed)

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

    # ================================  General methods shared by all views - built incrementally =====================

    def initialize_menu_tools(self):
        """This method collects menus and actions in superclasses and then adds custom ones, specific to this view."""
        # append code from superclass
        super().initialize_menu_tools()

        # then add new code specific to this class
        self.horizMirrorButton = QAction("Mirror horizontal axes", self)
        self.horizMirrorButton.triggered.connect(self.horizontal_mirror)
        self.menuView.addAction(self.horizMirrorButton)

    # --- AGGIUNTA: funzione di slot per sincronizzazione selezione ---
    def on_selection_changed(self, collection):
        print("DEBUG SLOT: selection_changed ricevuto per collection:", collection)
        self.selected_uids = collection.selected_uids.copy()
        self.actor_in_table(self.selected_uids)

    # ================================  Methods required by ViewVTK(), (re-)implemented here ==========================

    def set_orientation_widget(self):
        self.plotter.add_orientation_widget(
            pv_Arrow(direction=(0.0, 1.0, 0.0), scale=0.3),
            interactive=None,
            color="gold",
        )

    # ================================  Methods specific to Xsection views ============================================

    def horizontal_mirror(self):
        """Mirror horizontal axes."""
        self.print_terminal("Mirroring horizontal axes.")
        # Mirror internal variable used to store direction
        self.direction = -self.direction
        # Apply to plotter
        self.plotter.camera.focal_point = self.center
        self.plotter.camera.position = self.center + self.direction
        self.plotter.reset_camera()
    
