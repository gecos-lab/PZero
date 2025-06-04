"""abstract_base_view.py
PZero© Andrea Bistacchi"""

from PySide6.QtCore import QRect, QObject

# PySide6 imports____
from PySide6.QtWidgets import QMainWindow
from PySide6.QtGui import QAction
from PySide6.QtCore import Signal as pyqtSignal

# PZero imports____
from .view_tree import CustomTreeWidget
from ..ui.base_view_window_ui import Ui_BaseViewWindow
from ..add_remove_update_actors.background import *
from ..add_remove_update_actors.boundary import *
from ..add_remove_update_actors.dom import *
from ..add_remove_update_actors.fluid import *
from ..add_remove_update_actors.geology import *
from ..add_remove_update_actors.image import *
from ..add_remove_update_actors.mesh3d import *
from ..add_remove_update_actors.wells import *
from ..add_remove_update_actors.xsection import *


class BaseViewSignals(QObject):
    """
    This class is necessary since non-Qt classes cannot emit Qt signals. Therefore, we create a generic
    BaseViewSignals() Qt object that will include all signals used by collections. These will be used according
    to the following pattern:

    self.signals = BaseViewSignals()
    self.signals.specific_signal.emit(some_message)

    Basically, in this way, instead of using inheritance, we add all signals with a quick move by composition.
    """

    # signal broadcast on checkbox toggled, with the collection and lists of uids to be turned on or off as arguments
    checkboxToggled = pyqtSignal(str, list, list)
    # signal broadcast on property combobox changed, with the collection, uid and property as arguments
    propertyToggled = pyqtSignal(str, str, str)
    # signal for selection change, emits a list of UIDs
    newSelection = pyqtSignal(list)


class BaseView(QMainWindow, Ui_BaseViewWindow):
    """
    Create base view - abstract class providing common methods for all views. This includes all side tree and list
    views, but not the main plotting canvas, that must be managed by subclasses.
    parent is the QT object that is launching this one, hence the ProjectWindow() instance.
    """

    def __init__(self, parent=None, *args, **kwargs):
        super(BaseView, self).__init__(parent, *args, **kwargs)
        self.setupUi(self)
        # Qt.WA_DeleteOnClose DELETES ANY REFERENCE TO CLOSED WINDOWS, HENCE FREEING
        # MEMORY, BUT COULD CREATE PROBLEMS WITH SIGNALS THAT ARE STILL ACTIVE
        # SEE DISCUSSIONS ON QPointer AND WA_DeleteOnClose ON THE INTERNET
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.parent = parent
        self.signals = BaseViewSignals()
        self.print_terminal = self.parent.print_terminal
        self.tree_collection_dict = {
            "GeologyTreeWidget": "geol_coll",
            "FluidsTreeWidget": "fluid_coll",
            "BackgroundsTreeWidget": "backgrnd_coll",
            "DOMsTreeWidget": "dom_coll",
            "ImagesTreeWidget": "image_coll",
            "Mesh3DTreeWidget": "mesh3d_coll",
            "BoundariesTreeWidget": "boundary_coll",
            "XSectionTreeWidget": "xsect_coll",
            "WellsTreeWidget": "well_coll",
        }
        self.actors_df = pd_DataFrame(
            {
                "uid": str,
                "actor": str,
                "show": bool,
                "collection": str,
                "show_property": str,
            },
            index=[],
        )
        # __________________________________________________________________________________________
        # THIS MUST BE REMOVED - USE self.collection.selected_uids  ================================
        # __________________________________________________________________________________________
        self.selected_uids = []
        # Set view_filter attribute to a string indicating that all entities must be selected (i.e. no filtering).
        # Somebody says 'ilevel_0 in ilevel_0' is more robust than 'index == index', but it seems OK.
        if not hasattr(self, "view_filter"):
            self.view_filter = "index == index"
            self.this_x_section_uid = []
        # Initialize menus and tools, canvas, add actors and show it. These methods must be defined in subclasses.
        self.initialize_menu_tools()
        self.initialize_interactor()
        self.add_all_entities()
        # self.show_qt_canvas()  # comment this to avoid flashing window when opening a new view
        # self.toggle_backgrounds_visibility = lambda item: toggle_backgrounds_visibility(self, item)
        # self.toggle_boundary_visibility = lambda item: toggle_boundary_visibility(self, item)
        # self.toggle_dom_visibility = lambda cell: toggle_dom_visibility(self, cell)
        # self.toggle_fluids_visibility = lambda item: toggle_fluids_visibility(self, item)
        # self.toggle_geology_visibility = lambda item: toggle_geology_visibility(self, item)
        # self.toggle_image_visibility = lambda cell: toggle_image_visibility(self, cell)
        # self.toggle_mesh3d_visibility = lambda cell: toggle_mesh3d_visibility(self, cell)
        # self.toggle_well_visibility = lambda item: toggle_well_visibility(self, item)
        # self.toggle_xsection_visibility = lambda item: toggle_xsection_visibility(self, item)

        self.create_trees()

        self.connect_signals()

        # create_geology_tree(self)
        # create_topology_tree(self)
        # create_xsections_tree(self)
        # create_boundary_list(self)
        # create_mesh3d_list(self)
        # create_dom_list(self)
        # create_image_list(self)
        # create_well_tree(self)
        # create_fluids_tree(self)
        # create_fluids_topology_tree(self)
        # create_backgrounds_tree(self)
        # create_backgrounds_topology_tree(self)

        # Build and show other widgets, icons, tools, etc.
        # ----

        # Connect signals to update functions. Use lambda functions where we need to pass additional
        # arguments such as parent in addition to the signal itself, e.g. the updated_list
        # Note that it could be possible to connect the (lambda) functions directly, without naming them, as in:
        # self.parent.geol_coll.signals.added.connect(lambda updated_list: self.geology_added_update_views(
        #             updated_list=updated_list
        #         ))
        # but in this way it will be impossible to disconnect them selectively when closing this window, so we use:
        # self.upd_list_geo_add = lambda updated_list: self.geology_added_update_views(
        #             updated_list=updated_list
        #         )
        # self.parent.geol_coll.signals.added.connect(self.upd_list_geo_add)
        # self.parent.geol_coll.signals.added.disconnect(self.upd_list_geo_add)

        # Define GEOLOGY lamda functions and signals

        self.upd_list_geo_add = lambda updated_list: geology_added_update_views(
            self, updated_list=updated_list
        )
        self.upd_list_geo_rm = lambda updated_list: geology_removed_update_views(
            self, updated_list=updated_list
        )
        self.upd_list_geo_mod = lambda updated_list: geology_geom_modified_update_views(
            self, updated_list=updated_list
        )
        self.upd_list_geo_datakeys_mod = (
            lambda updated_list: geology_data_keys_modified_update_views(
                self, updated_list=updated_list
            )
        )
        self.upd_list_geo_dataval_mod = (
            lambda updated_list: geology_data_val_modified_update_views(
                self, updated_list=updated_list
            )
        )
        self.upd_list_geo_metadata_mod = (
            lambda updated_list: geology_metadata_modified_update_views(
                self, updated_list=updated_list
            )
        )
        # self.upd_list_geo_leg_col_mod = lambda updated_list: self.geology_legend_color_modified_update_views(
        #     updated_list=updated_list
        # )
        self.upd_list_geo_leg_col_mod = (
            lambda updated_list: geology_legend_modified_update_views(
                self, updated_list=updated_list
            )
        )
        # self.upd_list_geo_leg_thick_mod = lambda updated_list: self.geology_legend_thick_modified_update_views(
        #     updated_list=updated_list
        # )
        self.upd_list_geo_leg_thick_mod = (
            lambda updated_list: geology_legend_modified_update_views(
                self, updated_list=updated_list
            )
        )
        # self.upd_list_geo_leg_point_mod = lambda updated_list: self.geology_legend_point_size_modified_update_views(
        #     updated_list=updated_list
        # )
        self.upd_list_geo_leg_point_mod = (
            lambda updated_list: geology_legend_modified_update_views(
                self, updated_list=updated_list
            )
        )
        # self.upd_list_geo_leg_op_mod = lambda updated_list: self.geology_legend_opacity_modified_update_views(
        #     updated_list=updated_list
        # )
        self.upd_list_geo_leg_op_mod = (
            lambda updated_list: geology_legend_modified_update_views(
                self, updated_list=updated_list
            )
        )

        # Connect GEOLOGY lamda functions and signals

        self.parent.geol_coll.signals.added.connect(
            self.upd_list_geo_add
        )  # this is emitted from the collection
        self.parent.geol_coll.signals.removed.connect(
            self.upd_list_geo_rm
        )  # this is emitted from the collection
        self.parent.geol_coll.signals.data_keys_modified.connect(
            self.upd_list_geo_datakeys_mod
        )  # this is emitted from collection
        self.parent.geol_coll.signals.metadata_modified.connect(
            self.upd_list_geo_metadata_mod
        )  # this is emitted from collection and three_d_surfaces
        self.parent.geol_coll.signals.geom_modified.connect(
            self.upd_list_geo_mod
        )  # this is emitted from two_d_lines and three_d_surfaces
        self.parent.geol_coll.signals.data_keys_modified.connect(
            self.upd_list_geo_dataval_mod
        )  # this is emitted from nowhere (?)
        self.parent.geol_coll.signals.legend_color_modified.connect(
            self.upd_list_geo_leg_col_mod
        )  # this is emitted from legend manager
        self.parent.geol_coll.signals.legend_thick_modified.connect(
            self.upd_list_geo_leg_thick_mod
        )  # this is emitted from legend manager
        self.parent.geol_coll.signals.legend_point_size_modified.connect(
            self.upd_list_geo_leg_point_mod
        )  # this is emitted from legend manager
        self.parent.geol_coll.signals.legend_opacity_modified.connect(
            self.upd_list_geo_leg_op_mod
        )  # this is emitted from legend manager

        # Define X SECTION lamda functions and signals

        self.upd_list_x_add = lambda updated_list: xsect_added_update_views(
            self, updated_list=updated_list
        )
        self.upd_list_x_rm = lambda updated_list: xsect_removed_update_views(
            self, updated_list=updated_list
        )
        self.upd_list_x_mod = lambda updated_list: xsect_geom_modified_update_views(
            self, updated_list=updated_list
        )
        self.upd_list_x_metadata_mod = (
            lambda updated_list: xsect_metadata_modified_update_views(
                self, updated_list=updated_list
            )
        )
        self.upd_list_x_leg_col_mod = (
            lambda updated_list: xsect_legend_color_modified_update_views(
                self, updated_list=updated_list
            )
        )
        self.upd_list_x_leg_thick_mod = (
            lambda updated_list: xsect_legend_thick_modified_update_views(
                self, updated_list=updated_list
            )
        )
        self.upd_list_x_leg_op_mod = (
            lambda updated_list: xsect_legend_opacity_modified_update_views(
                self, updated_list=updated_list
            )
        )

        # Connect X SECTION lamda functions and signals

        self.parent.xsect_coll.signals.added.connect(
            self.upd_list_x_add
        )  # this is emitted from the collection
        self.parent.xsect_coll.signals.removed.connect(
            self.upd_list_x_rm
        )  # this is emitted from the collection
        self.parent.xsect_coll.signals.metadata_modified.connect(
            self.upd_list_x_metadata_mod
        )  # this is emitted from the collection

        self.parent.xsect_coll.signals.geom_modified.connect(
            self.upd_list_x_mod
        )  # this is emitted from nowhere (?)

        self.parent.xsect_coll.signals.legend_color_modified.connect(
            self.upd_list_x_leg_col_mod
        )  # this is emitted from the legend manager
        self.parent.xsect_coll.signals.legend_thick_modified.connect(
            self.upd_list_x_leg_thick_mod
        )  # this is emitted from the legend manager
        self.parent.xsect_coll.signals.legend_opacity_modified.connect(
            self.upd_list_x_leg_op_mod
        )  # this is emitted from the legend manager

        # Define BOUNDARY lamda functions and signals

        self.upd_list_bound_add = lambda updated_list: boundary_added_update_views(
            self, updated_list=updated_list
        )
        self.upd_list_bound_rm = lambda updated_list: boundary_removed_update_views(
            self, updated_list=updated_list
        )
        self.upd_list_bound_geo_mod = (
            lambda updated_list: boundary_geom_modified_update_views(
                self, updated_list=updated_list
            )
        )
        self.upd_list_bound_metadata_mod = (
            lambda updated_list: boundary_metadata_modified_update_views(
                self, updated_list=updated_list
            )
        )
        self.upd_list_bound_leg_col_mod = (
            lambda updated_list: boundary_legend_color_modified_update_views(
                self, updated_list=updated_list
            )
        )
        self.upd_list_bound_leg_thick_mod = (
            lambda updated_list: boundary_legend_thick_modified_update_views(
                self, updated_list=updated_list
            )
        )
        self.upd_list_bound_leg_op_mod = (
            lambda updated_list: boundary_legend_opacity_modified_update_views(
                self, updated_list=updated_list
            )
        )

        # Connect BOUNDARY lamda functions and signals

        self.parent.boundary_coll.signals.added.connect(
            self.upd_list_bound_add
        )  # this is emitted from the collection
        self.parent.boundary_coll.signals.removed.connect(
            self.upd_list_bound_rm
        )  # this is emitted from the collection
        self.parent.boundary_coll.signals.metadata_modified.connect(
            self.upd_list_bound_metadata_mod
        )  # this is emitted from the collection

        self.parent.boundary_coll.signals.geom_modified.connect(
            self.upd_list_bound_geo_mod
        )  # this is emitted from nowhere(?)

        self.parent.boundary_coll.signals.legend_color_modified.connect(
            self.upd_list_bound_leg_col_mod
        )  # this is emitted from the legend manager
        self.parent.boundary_coll.signals.legend_thick_modified.connect(
            self.upd_list_bound_leg_thick_mod
        )  # this is emitted from the legend manager
        self.parent.boundary_coll.signals.legend_opacity_modified.connect(
            self.upd_list_bound_leg_op_mod
        )  # this is emitted from the legend manager

        # Define MESH 3D lamda functions and signals

        self.upd_list_mesh3d_add = lambda updated_list: mesh3d_added_update_views(
            self, updated_list=updated_list
        )
        self.upd_list_mesh3d_rm = lambda updated_list: mesh3d_removed_update_views(
            self, updated_list=updated_list
        )
        self.upd_list_mesh3d_data_keys_mod = (
            lambda updated_list: mesh3d_data_keys_modified_update_views(
                self, updated_list=updated_list
            )
        )
        self.upd_list_mesh3d_data_val_mod = (
            lambda updated_list: mesh3d_data_val_modified_update_views(
                self, updated_list=updated_list
            )
        )
        self.upd_list_mesh3d_metadata_mod = (
            lambda updated_list: mesh3d_metadata_modified_update_views(
                self, updated_list=updated_list
            )
        )
        self.upd_list_mesh3d_leg_col_mod = (
            lambda updated_list: mesh3d_legend_color_modified_update_views(
                self, updated_list=updated_list
            )
        )
        self.upd_list_mesh3d_leg_thick_mod = (
            lambda updated_list: mesh3d_legend_thick_modified_update_views(
                self, updated_list=updated_list
            )
        )
        self.upd_list_mesh3d_leg_op_mod = (
            lambda updated_list: mesh3d_legend_opacity_modified_update_views(
                self, updated_list=updated_list
            )
        )

        # Connect MESH 3D lamda functions and signals

        self.parent.mesh3d_coll.signals.added.connect(
            self.upd_list_mesh3d_add
        )  # this is emitted from the collection
        self.parent.mesh3d_coll.signals.removed.connect(
            self.upd_list_mesh3d_rm
        )  # this is emitted from the collection
        self.parent.mesh3d_coll.signals.data_keys_modified.connect(
            self.upd_list_mesh3d_data_keys_mod
        )  # this is emitted from the collection
        self.parent.mesh3d_coll.signals.metadata_modified.connect(
            self.upd_list_mesh3d_metadata_mod
        )  # this is emitted from the collection

        self.parent.mesh3d_coll.signals.data_val_modified.connect(
            self.upd_list_mesh3d_data_val_mod
        )  # this is emitted from nowhere (?)

        self.parent.mesh3d_coll.signals.legend_color_modified.connect(
            self.upd_list_mesh3d_leg_col_mod
        )  # this is emitted from the legend manager
        self.parent.mesh3d_coll.signals.legend_thick_modified.connect(
            self.upd_list_mesh3d_leg_thick_mod
        )  # this is emitted from the legend manager
        self.parent.mesh3d_coll.signals.legend_opacity_modified.connect(
            self.upd_list_mesh3d_leg_op_mod
        )  # this is emitted from the legend manager

        # Define DOM lamda functions and signals

        self.upd_list_dom_add = lambda updated_list: dom_added_update_views(
            self, updated_list=updated_list
        )
        self.upd_list_dom_rm = lambda updated_list: dom_removed_update_views(
            self, updated_list=updated_list
        )
        self.upd_list_dom_data_keys_mod = (
            lambda updated_list: dom_data_keys_modified_update_views(
                self, updated_list=updated_list
            )
        )
        self.upd_list_dom_data_val_mod = (
            lambda updated_list: dom_data_val_modified_update_views(
                self, updated_list=updated_list
            )
        )
        self.upd_list_dom_metadata_mod = (
            lambda updated_list: dom_metadata_modified_update_views(
                self, updated_list=updated_list
            )
        )
        self.upd_list_dom_leg_col_mod = (
            lambda updated_list: dom_legend_color_modified_update_views(
                self, updated_list=updated_list
            )
        )
        self.upd_list_dom_leg_thick_mod = (
            lambda updated_list: dom_legend_thick_modified_update_views(
                self, updated_list=updated_list
            )
        )
        self.upd_list_dom_leg_point_mod = (
            lambda updated_list: dom_legend_point_size_modified_update_views(
                self, updated_list=updated_list
            )
        )
        self.upd_list_dom_leg_op_mod = (
            lambda updated_list: dom_legend_opacity_modified_update_views(
                self, updated_list=updated_list
            )
        )

        # Collect DOM lamda functions and signals

        self.parent.dom_coll.signals.added.connect(
            self.upd_list_dom_add
        )  # this is emitted from the collection
        self.parent.dom_coll.signals.removed.connect(
            self.upd_list_dom_rm
        )  # this is emitted from the collection
        self.parent.dom_coll.signals.data_keys_modified.connect(
            self.upd_list_dom_data_keys_mod
        )  # this is emitted from the collection
        self.parent.dom_coll.signals.metadata_modified.connect(
            self.upd_list_dom_metadata_mod
        )  # this is emitted from the collection

        self.parent.dom_coll.signals.data_val_modified.connect(
            self.upd_list_dom_data_val_mod
        )  # this is emitted from nowhere(?)

        self.parent.dom_coll.signals.legend_color_modified.connect(
            self.upd_list_dom_leg_col_mod
        )  # this is emitted from the legend manager
        self.parent.dom_coll.signals.legend_thick_modified.connect(
            self.upd_list_dom_leg_thick_mod
        )  # this is emitted from the legend manager
        self.parent.dom_coll.signals.legend_point_size_modified.connect(
            self.upd_list_dom_leg_point_mod
        )  # this is emitted from the legend manager
        self.parent.dom_coll.signals.legend_opacity_modified.connect(
            self.upd_list_dom_leg_op_mod
        )  # this is emitted from the legend manager

        # Define IMAGE lamda functions and signals

        self.upd_list_img_add = lambda updated_list: image_added_update_views(
            self, updated_list=updated_list
        )
        self.upd_list_img_rm = lambda updated_list: image_removed_update_views(
            self, updated_list=updated_list
        )
        self.upd_list_metadata_mod = (
            lambda updated_list: image_metadata_modified_update_views(
                self, updated_list=updated_list
            )
        )
        self.upd_list_img_leg_op_mod = (
            lambda updated_list: image_legend_opacity_modified_update_views(
                self, updated_list=updated_list
            )
        )

        # Connect IMAGE lamda functions and signals

        self.parent.image_coll.signals.added.connect(
            self.upd_list_img_add
        )  # this is emitted from the collection
        self.parent.image_coll.signals.removed.connect(
            self.upd_list_img_rm
        )  # this is emitted from the collection
        self.parent.image_coll.signals.metadata_modified.connect(
            self.upd_list_metadata_mod
        )  # this is emitted from the collection

        self.parent.image_coll.signals.legend_opacity_modified.connect(
            self.upd_list_img_leg_op_mod
        )  # this is emitted from the legend manager

        # Define WELL lamda functions and signals

        self.upd_list_well_add = lambda updated_list: well_added_update_views(
            self, updated_list=updated_list
        )
        self.upd_list_well_rm = lambda updated_list: well_removed_update_views(
            self, updated_list=updated_list
        )
        self.upd_list_well_data_keys_mod = (
            lambda updated_list: well_data_keys_modified_update_views(
                self, updated_list=updated_list
            )
        )
        self.upd_list_well_data_val_mod = (
            lambda updated_list: well_data_val_modified_update_views(
                self, updated_list=updated_list
            )
        )
        self.upd_list_well_metadata_mod = (
            lambda updated_list: well_metadata_modified_update_views(
                self, updated_list=updated_list
            )
        )
        self.upd_list_well_leg_col_mod = (
            lambda updated_list: well_legend_color_modified_update_views(
                self, updated_list=updated_list
            )
        )
        self.upd_list_well_leg_thick_mod = (
            lambda updated_list: well_legend_thick_modified_update_views(
                self, updated_list=updated_list
            )
        )
        self.upd_list_well_leg_op_mod = (
            lambda updated_list: well_legend_opacity_modified_update_views(
                self, updated_list=updated_list
            )
        )

        # Connect WELL lamda functions and signals

        self.parent.well_coll.signals.added.connect(
            self.upd_list_well_add
        )  # this is emitted from the collection
        self.parent.well_coll.signals.removed.connect(
            self.upd_list_well_rm
        )  # this is emitted from the collection
        self.parent.well_coll.signals.data_keys_modified.connect(
            self.upd_list_well_data_keys_mod
        )  # this is emitted from the collection
        self.parent.well_coll.signals.metadata_modified.connect(
            self.upd_list_well_metadata_mod
        )  # this is emitted from the collection

        self.parent.well_coll.signals.data_val_modified.connect(
            self.upd_list_well_data_val_mod
        )  # this is emitted from nowhere(?)

        self.parent.well_coll.signals.legend_color_modified.connect(
            self.upd_list_well_leg_col_mod
        )  # this is emitted from the legend manager
        self.parent.well_coll.signals.legend_thick_modified.connect(
            self.upd_list_well_leg_thick_mod
        )  # this is emitted from the legend manager
        self.parent.well_coll.signals.legend_opacity_modified.connect(
            self.upd_list_well_leg_op_mod
        )  # this is emitted from the legend manager

        # Define FLUID lamda functions and signals

        self.upd_list_fluid_add = lambda updated_list: fluid_added_update_views(
            self, updated_list=updated_list
        )
        self.upd_list_fluid_rm = lambda updated_list: fluid_removed_update_views(
            self, updated_list=updated_list
        )
        self.upd_list_fluid_geo_mod = (
            lambda updated_list: fluid_geom_modified_update_views(
                self, updated_list=updated_list
            )
        )
        self.upd_list_fluid_data_keys_mod = (
            lambda updated_list: fluid_data_keys_modified_update_views(
                self, updated_list=updated_list
            )
        )
        self.upd_list_fluid_data_val_mod = (
            lambda updated_list: fluid_data_val_modified_update_views(
                self, updated_list=updated_list
            )
        )
        self.upd_list_fluid_metadata_mod = (
            lambda updated_list: fluid_metadata_modified_update_views(
                self, updated_list=updated_list
            )
        )
        self.upd_list_fluid_leg_col_mod = (
            lambda updated_list: fluid_legend_color_modified_update_views(
                self, updated_list=updated_list
            )
        )
        self.upd_list_fluid_leg_thick_mod = (
            lambda updated_list: fluid_legend_thick_modified_update_views(
                self, updated_list=updated_list
            )
        )
        self.upd_list_fluid_leg_point_mod = (
            lambda updated_list: fluid_legend_point_size_modified_update_views(
                self, updated_list=updated_list
            )
        )
        self.upd_list_fluid_leg_op_mod = (
            lambda updated_list: fluid_legend_opacity_modified_update_views(
                self, updated_list=updated_list
            )
        )

        # Connect FLUID lamda functions and signals

        self.parent.fluid_coll.signals.added.connect(
            self.upd_list_fluid_add
        )  # this is emitted from the collection
        self.parent.fluid_coll.signals.removed.connect(
            self.upd_list_fluid_rm
        )  # this is emitted from the collection
        self.parent.fluid_coll.signals.data_keys_modified.connect(
            self.upd_list_fluid_data_keys_mod
        )  # this is emitted from the collection
        self.parent.fluid_coll.signals.metadata_modified.connect(
            self.upd_list_fluid_metadata_mod
        )  # this is emitted from the collection

        self.parent.fluid_coll.signals.geom_modified.connect(
            self.upd_list_fluid_geo_mod
        )  # this is emitted from nowhere(?)

        self.parent.fluid_coll.signals.data_val_modified.connect(
            self.upd_list_fluid_data_val_mod
        )  # this is emitted from nowhere(?)

        self.parent.fluid_coll.signals.legend_color_modified.connect(
            self.upd_list_fluid_leg_col_mod
        )  # this is emitted from the legend manager
        self.parent.fluid_coll.signals.legend_thick_modified.connect(
            self.upd_list_fluid_leg_thick_mod
        )  # this is emitted from the legend manager
        self.parent.fluid_coll.signals.legend_point_size_modified.connect(
            self.upd_list_fluid_leg_point_mod
        )  # this is emitted from the legend manager
        self.parent.fluid_coll.signals.legend_opacity_modified.connect(
            self.upd_list_fluid_leg_op_mod
        )  # this is emitted from the legend manager

        # Define BACKGROUND lamda functions and signals

        self.upd_list_background_add = (
            lambda updated_list: background_added_update_views(
                self, updated_list=updated_list
            )
        )
        self.upd_list_background_rm = (
            lambda updated_list: background_removed_update_views(
                self, updated_list=updated_list
            )
        )
        self.upd_list_background_geo_mod = (
            lambda updated_list: background_geom_modified_update_views(
                self, updated_list=updated_list
            )
        )
        self.upd_list_background_data_keys = (
            lambda updated_list: background_data_keys_modified_update_views(
                self, updated_list=updated_list
            )
        )
        self.upd_list_background_data_val = (
            lambda updated_list: background_data_val_modified_update_views(
                self, updated_list=updated_list
            )
        )
        self.upd_list_background_metadata = (
            lambda updated_list: background_metadata_modified_update_views(
                self, updated_list=updated_list
            )
        )
        self.upd_list_background_leg_col = (
            lambda updated_list: background_legend_color_modified_update_views(
                self, updated_list=updated_list
            )
        )
        self.upd_list_background_leg_thick = (
            lambda updated_list: background_legend_thick_modified_update_views(
                self, updated_list=updated_list
            )
        )
        self.upd_list_background_leg_point = (
            lambda updated_list: background_legend_point_size_modified_update_views(
                self, updated_list=updated_list
            )
        )
        self.upd_list_background_leg_op = (
            lambda updated_list: background_legend_opacity_modified_update_views(
                self, updated_list=updated_list
            )
        )

        # Connect BACKGROUND lamda functions and signals

        self.parent.backgrnd_coll.signals.added.connect(
            self.upd_list_background_add
        )  # this is emitted from the collection
        self.parent.backgrnd_coll.signals.removed.connect(
            self.upd_list_background_rm
        )  # this is emitted from the collection
        self.parent.backgrnd_coll.signals.data_keys_modified.connect(
            self.upd_list_background_data_keys
        )  # this is emitted from the collection
        self.parent.backgrnd_coll.signals.metadata_modified.connect(
            self.upd_list_background_metadata
        )  # this is emitted from the collection

        self.parent.backgrnd_coll.signals.geom_modified.connect(
            self.upd_list_background_geo_mod
        )  # this is emitted from nowhere(?)
        self.parent.backgrnd_coll.signals.data_val_modified.connect(
            self.upd_list_background_data_val
        )  # this is emitted from nowhere(?)

        self.parent.backgrnd_coll.signals.legend_color_modified.connect(
            self.upd_list_background_leg_col
        )  # this is emitted from the legend manager
        self.parent.backgrnd_coll.signals.legend_thick_modified.connect(
            self.upd_list_background_leg_thick
        )  # this is emitted from the legend manager
        self.parent.backgrnd_coll.signals.legend_point_size_modified.connect(
            self.upd_list_background_leg_point
        )  # this is emitted from the legend manager
        self.parent.backgrnd_coll.signals.legend_opacity_modified.connect(
            self.upd_list_background_leg_op
        )  # this is emitted from the legend manager

        # Define and connect PROPERTY LEGEND lamda functions and signals

        self.prop_legend_lambda = (
            lambda this_property: self.prop_legend_cmap_modified_update_views(
                this_property=this_property
            )
        )

        self.parent.prop_legend_cmap_modified_signal.connect(self.prop_legend_lambda)

    # ================================  General methods shared by all views ===========================================

    def connect_signals(self):
        self.signals.checkboxToggled.connect(
            lambda collection_name, turn_on_uids, turn_off_uids: self.toggle_visibility(
                collection_name, turn_on_uids, turn_off_uids
            )
        )

    def disconnect_all_signals(self):
        """Used to disconnect all windows signals correctly, when a window is closed.
        If this method is removed PZero will crash when closing a window.
        If new signals are added, they must be listed also here.
        It would be nicer to keep a list of signals and then disconnect all signals in
        the list, but we have not found a way to do this at the moment."""

        # Disconnect GEOLOGY signals

        self.parent.geol_coll.signals.added.disconnect(self.upd_list_geo_add)
        self.parent.geol_coll.signals.removed.disconnect(self.upd_list_geo_rm)
        self.parent.geol_coll.signals.geom_modified.disconnect(self.upd_list_geo_mod)
        self.parent.geol_coll.signals.data_keys_modified.disconnect(
            self.upd_list_geo_datakeys_mod
        )
        self.parent.geol_coll.signals.data_keys_modified.disconnect(
            self.upd_list_geo_dataval_mod
        )
        self.parent.geol_coll.signals.metadata_modified.disconnect(
            self.upd_list_geo_metadata_mod
        )
        self.parent.geol_coll.signals.legend_color_modified.disconnect(
            self.upd_list_geo_leg_col_mod
        )
        self.parent.geol_coll.signals.legend_thick_modified.disconnect(
            self.upd_list_geo_leg_thick_mod
        )
        self.parent.geol_coll.signals.legend_point_size_modified.disconnect(
            self.upd_list_geo_leg_point_mod
        )
        self.parent.geol_coll.signals.legend_opacity_modified.disconnect(
            self.upd_list_geo_leg_op_mod
        )

        # Disconnect X-SECTION signals

        self.parent.xsect_coll.signals.added.disconnect(self.upd_list_x_add)
        self.parent.xsect_coll.signals.removed.disconnect(self.upd_list_x_rm)
        self.parent.xsect_coll.signals.geom_modified.disconnect(self.upd_list_x_mod)
        self.parent.xsect_coll.signals.metadata_modified.disconnect(
            self.upd_list_x_metadata_mod
        )
        self.parent.xsect_coll.signals.legend_color_modified.disconnect(
            self.upd_list_x_leg_col_mod
        )
        self.parent.xsect_coll.signals.legend_thick_modified.disconnect(
            self.upd_list_x_leg_thick_mod
        )
        self.parent.xsect_coll.signals.legend_opacity_modified.disconnect(
            self.upd_list_x_leg_op_mod
        )

        # Disconnect BOUNDARY signals

        self.parent.boundary_coll.signals.added.disconnect(self.upd_list_bound_add)
        self.parent.boundary_coll.signals.removed.disconnect(self.upd_list_bound_rm)
        self.parent.boundary_coll.signals.geom_modified.disconnect(
            self.upd_list_bound_geo_mod
        )
        self.parent.boundary_coll.signals.metadata_modified.disconnect(
            self.upd_list_bound_metadata_mod
        )
        self.parent.boundary_coll.signals.legend_color_modified.disconnect(
            self.upd_list_bound_leg_col_mod
        )
        self.parent.boundary_coll.signals.legend_thick_modified.disconnect(
            self.upd_list_bound_leg_thick_mod
        )
        self.parent.boundary_coll.signals.legend_opacity_modified.disconnect(
            self.upd_list_bound_leg_op_mod
        )

        # Disconnect MESH3D signals

        self.parent.mesh3d_coll.signals.added.disconnect(self.upd_list_mesh3d_add)
        self.parent.mesh3d_coll.signals.removed.disconnect(self.upd_list_mesh3d_rm)
        self.parent.mesh3d_coll.signals.data_keys_modified.disconnect(
            self.upd_list_mesh3d_data_keys_mod
        )
        self.parent.mesh3d_coll.signals.data_val_modified.disconnect(
            self.upd_list_mesh3d_data_val_mod
        )
        self.parent.mesh3d_coll.signals.metadata_modified.disconnect(
            self.upd_list_mesh3d_metadata_mod
        )
        self.parent.mesh3d_coll.signals.legend_color_modified.disconnect(
            self.upd_list_mesh3d_leg_col_mod
        )
        self.parent.mesh3d_coll.signals.legend_thick_modified.disconnect(
            self.upd_list_mesh3d_leg_thick_mod
        )
        self.parent.mesh3d_coll.signals.legend_opacity_modified.disconnect(
            self.upd_list_mesh3d_leg_op_mod
        )

        # Disconnect DOM signals

        self.parent.dom_coll.signals.added.disconnect(self.upd_list_dom_add)
        self.parent.dom_coll.signals.removed.disconnect(self.upd_list_dom_rm)
        self.parent.dom_coll.signals.data_keys_modified.disconnect(
            self.upd_list_dom_data_keys_mod
        )
        self.parent.dom_coll.signals.data_val_modified.disconnect(
            self.upd_list_dom_data_val_mod
        )
        self.parent.dom_coll.signals.metadata_modified.disconnect(
            self.upd_list_dom_metadata_mod
        )
        self.parent.dom_coll.signals.legend_color_modified.disconnect(
            self.upd_list_dom_leg_col_mod
        )
        self.parent.dom_coll.signals.legend_thick_modified.disconnect(
            self.upd_list_dom_leg_thick_mod
        )
        self.parent.dom_coll.signals.legend_point_size_modified.disconnect(
            self.upd_list_dom_leg_point_mod
        )
        self.parent.dom_coll.signals.legend_opacity_modified.disconnect(
            self.upd_list_dom_leg_op_mod
        )

        # Disconnect IMAGE signals

        self.parent.image_coll.signals.added.disconnect(self.upd_list_img_add)
        self.parent.image_coll.signals.removed.disconnect(self.upd_list_img_rm)
        self.parent.image_coll.signals.metadata_modified.disconnect(
            self.upd_list_metadata_mod
        )
        self.parent.image_coll.signals.legend_opacity_modified.disconnect(
            self.upd_list_img_leg_op_mod
        )

        # Disconnect WELL signals

        self.parent.well_coll.signals.added.disconnect(self.upd_list_well_add)
        self.parent.well_coll.signals.removed.disconnect(self.upd_list_well_rm)
        self.parent.well_coll.signals.data_keys_modified.disconnect(
            self.upd_list_well_data_keys_mod
        )
        self.parent.well_coll.signals.data_val_modified.disconnect(
            self.upd_list_well_data_val_mod
        )
        self.parent.well_coll.signals.metadata_modified.disconnect(
            self.upd_list_well_metadata_mod
        )
        self.parent.well_coll.signals.legend_color_modified.disconnect(
            self.upd_list_well_leg_col_mod
        )
        self.parent.well_coll.signals.legend_thick_modified.disconnect(
            self.upd_list_well_leg_thick_mod
        )
        self.parent.well_coll.signals.legend_opacity_modified.disconnect(
            self.upd_list_well_leg_op_mod
        )

        # Disconnect FLUID signals

        self.parent.fluid_coll.signals.added.disconnect(self.upd_list_fluid_add)
        self.parent.fluid_coll.signals.removed.disconnect(self.upd_list_fluid_rm)
        self.parent.fluid_coll.signals.geom_modified.disconnect(
            self.upd_list_fluid_geo_mod
        )
        self.parent.fluid_coll.signals.data_keys_modified.disconnect(
            self.upd_list_fluid_data_keys_mod
        )
        self.parent.fluid_coll.signals.data_val_modified.disconnect(
            self.upd_list_fluid_data_val_mod
        )
        self.parent.fluid_coll.signals.metadata_modified.disconnect(
            self.upd_list_fluid_metadata_mod
        )
        self.parent.fluid_coll.signals.legend_color_modified.disconnect(
            self.upd_list_fluid_leg_col_mod
        )
        self.parent.fluid_coll.signals.legend_thick_modified.disconnect(
            self.upd_list_fluid_leg_thick_mod
        )
        self.parent.fluid_coll.signals.legend_point_size_modified.disconnect(
            self.upd_list_fluid_leg_point_mod
        )
        self.parent.fluid_coll.signals.legend_opacity_modified.disconnect(
            self.upd_list_fluid_leg_op_mod
        )

        # Disconnect BACKGROUND signals

        self.parent.backgrnd_coll.signals.added.disconnect(self.upd_list_background_add)
        self.parent.backgrnd_coll.signals.removed.disconnect(
            self.upd_list_background_rm
        )
        self.parent.backgrnd_coll.signals.geom_modified.disconnect(
            self.upd_list_background_geo_mod
        )
        self.parent.backgrnd_coll.signals.data_keys_modified.disconnect(
            self.upd_list_background_data_keys
        )
        self.parent.backgrnd_coll.signals.data_val_modified.disconnect(
            self.upd_list_background_data_val
        )
        self.parent.backgrnd_coll.signals.metadata_modified.disconnect(
            self.upd_list_background_metadata
        )
        self.parent.backgrnd_coll.signals.legend_color_modified.disconnect(
            self.upd_list_background_leg_col
        )
        self.parent.backgrnd_coll.signals.legend_thick_modified.disconnect(
            self.upd_list_background_leg_thick
        )
        self.parent.backgrnd_coll.signals.legend_point_size_modified.disconnect(
            self.upd_list_background_leg_point
        )
        self.parent.backgrnd_coll.signals.legend_opacity_modified.disconnect(
            self.upd_list_background_leg_op
        )

        # Disconnect PROPERTY LEGEND signals

        self.parent.prop_legend_cmap_modified_signal.disconnect(self.prop_legend_lambda)

    def disable_actions(self):
        """Freeze all actions while doing something."""
        # self.parent.findChildren(QAction) returns a list of all actions in the application.
        for action in self.parent.findChildren(QAction):
            # try - except added to catch an inexplicable bug with an action with text=""
            try:
                action.setDisabled(True)
            except:
                pass

    def enable_actions(self):
        """Un-freeze all actions after having done something."""
        # self.parent.findChildren(QAction) returns a list of all actions in the application.
        for action in self.parent.findChildren(QAction):
            action.setEnabled(True)

    def create_trees(self):
        for tree_name, coll_name in self.tree_collection_dict.items():
            show_name = tree_name.removesuffix("Widget")
            page_name = show_name + "Page"
            layout_name = show_name + "Layout"
            collection = eval(f"self.parent.{coll_name}")
            tree_labels = ["role", "topology", "feature", "scenario"]
            if not "role" in eval(f"self.parent.{coll_name}.entity_dict.keys()"):
                tree_labels.remove("role")
            if not "topology" in eval(f"self.parent.{coll_name}.entity_dict.keys()"):
                tree_labels.remove("topology")
            if not "feature" in eval(f"self.parent.{coll_name}.entity_dict.keys()"):
                tree_labels.remove("feature")
            if "properties_names" in eval(
                f"self.parent.{coll_name}.entity_dict.keys()"
            ):
                prop_label = "properties_names"
            else:
                prop_label = None
            default_labels = ["none", "X", "Y", "Z"]
            setattr(
                self,
                f"{tree_name}",
                CustomTreeWidget(
                    parent=eval(f"self.{page_name}"),
                    view=self,
                    collection=collection,
                    tree_labels=tree_labels,
                    name_label="name",
                    uid_label="uid",
                    prop_label=prop_label,
                    default_labels=default_labels,
                ),
            )
            eval(f"self.{tree_name}").setObjectName(tree_name)
            eval(f"self.{layout_name}").addWidget(eval(f"self.{tree_name}"))

    def toggle_visibility(
        self, collection_name=None, turn_on_uids=None, turn_off_uids=None
    ):
        # self.print_terminal("Toggling visibility - on uids: " + str(turn_on_uids) + " - off uids: " + str(turn_off_uids))
        # if turn_on_uids:
        for uid in turn_on_uids:
            # if (self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0] == False):
            # self.print_terminal("on: " + str(self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]))
            self.set_actor_visible(uid=uid, visible=True)
        # if turn_off_uids:
        for uid in turn_off_uids:
            # if (self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0] == True):
            # self.print_terminal("off: " + str(self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]))
            self.set_actor_visible(uid=uid, visible=False)

    def toggle_property(self, sender=None):
        """Generic method to toggle the property shown by an actor that is already present in the view."""
        show_property = sender.currentText()
        uid = sender.uid
        try:
            name = sender.name
        except AttributeError:
            name = None
        show = self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]
        collection = self.actors_df.loc[
            self.actors_df["uid"] == uid, "collection"
        ].values[0]
        # Replace the previous copy of the actor with the same uid, and update the actors dataframe, only if a
        # property that has been removed is shown at the moment. See issue #33 for a discussion on actors
        # replacement by the PyVista add_mesh and add_volume methods.
        if name == "Marker":
            # case for Marker
            self.show_markers(uid=uid, show_property=show_property)
        elif name == "Annotations":
            # case for Annotations
            self.show_labels(
                uid=uid, show_property=show_property, collection=collection
            )
        else:
            # case for all other properties
            this_actor = self.show_actor_with_property(
                uid=uid,
                collection=collection,
                show_property=show_property,
                visible=show,
            )
        # Replace the shown property in the actors dataframe
        self.actors_df.loc[self.actors_df["uid"] == uid, "show_property"] = (
            show_property
        )

    def add_all_entities(self):
        """
        Add all entities in project collections.
        All objects are visible by default -> show = True.
        """
        for collection_name in self.tree_collection_dict.values():
            try:
                for uid in (
                    eval(f"self.parent.{collection_name}")
                    .df.query(self.view_filter)["uid"]
                    .tolist()
                ):
                    this_actor = self.show_actor_with_property(
                        uid=uid,
                        collection=collection_name,
                        show_property=None,
                        visible=True,
                    )
                    # New Pandas >= 2.0.0
                    self.actors_df = pd_concat(
                        [
                            self.actors_df,
                            pd_DataFrame(
                                [
                                    {
                                        "uid": uid,
                                        "actor": this_actor,
                                        "show": True,
                                        "collection": collection_name,
                                        "show_property": None,
                                    }
                                ]
                            ),
                        ],
                        ignore_index=True,
                    )
            except:
                pass
        # try:
        #     for uid in self.parent.xsect_coll.df.query(self.view_filter)[
        #         "uid"
        #     ].tolist():
        #         this_actor = self.show_actor_with_property(
        #             uid=uid, collection="xsect_coll", show_property=None, visible=False
        #         )
        #         # New Pandas >= 2.0.0
        #         self.actors_df = pd_concat(
        #             [
        #                 self.actors_df,
        #                 pd_DataFrame(
        #                     [
        #                         {
        #                             "uid": uid,
        #                             "actor": this_actor,
        #                             "show": False,
        #                             "collection": "xsect_coll",
        #                             "show_property": None,
        #                         }
        #                     ]
        #                 ),
        #             ],
        #             ignore_index=True,
        #         )
        # except:
        #     pass
        # try:
        #     for uid in self.parent.boundary_coll.df.query(self.view_filter)[
        #         "uid"
        #     ].tolist():
        #         this_actor = self.show_actor_with_property(
        #             uid=uid,
        #             collection="boundary_coll",
        #             show_property=None,
        #             visible=False,
        #         )
        #         # New Pandas >= 2.0.0
        #         self.actors_df = pd_concat(
        #             [
        #                 self.actors_df,
        #                 pd_DataFrame(
        #                     [
        #                         {
        #                             "uid": uid,
        #                             "actor": this_actor,
        #                             "show": False,
        #                             "collection": "boundary_coll",
        #                             "show_property": None,
        #                         }
        #                     ]
        #                 ),
        #             ],
        #             ignore_index=True,
        #         )
        # except:
        #     pass
        # for uid in self.parent.mesh3d_coll.df.query(self.view_filter)["uid"].tolist():
        #     this_actor = self.show_actor_with_property(
        #         uid=uid, collection="mesh3d_coll", show_property=None, visible=False
        #     )
        #     # New Pandas >= 2.0.0
        #     self.actors_df = pd_concat(
        #         [
        #             self.actors_df,
        #             pd_DataFrame(
        #                 [
        #                     {
        #                         "uid": uid,
        #                         "actor": this_actor,
        #                         "show": False,
        #                         "collection": "mesh3d_coll",
        #                         "show_property": None,
        #                     }
        #                 ]
        #             ),
        #         ],
        #         ignore_index=True,
        #     )
        # for uid in self.parent.dom_coll.df.query(self.view_filter)["uid"].tolist():
        #     this_actor = self.show_actor_with_property(
        #         uid=uid, collection="dom_coll", show_property=None, visible=False
        #     )
        #     # New Pandas >= 2.0.0
        #     self.actors_df = pd_concat(
        #         [
        #             self.actors_df,
        #             pd_DataFrame(
        #                 [
        #                     {
        #                         "uid": uid,
        #                         "actor": this_actor,
        #                         "show": False,
        #                         "collection": "dom_coll",
        #                         "show_property": None,
        #                     }
        #                 ]
        #             ),
        #         ],
        #         ignore_index=True,
        #     )
        # for uid in self.parent.image_coll.df.query(self.view_filter)["uid"].tolist():
        #     this_actor = self.show_actor_with_property(
        #         uid=uid, collection="image_coll", show_property=None, visible=False
        #     )
        #     # New Pandas >= 2.0.0
        #     self.actors_df = pd_concat(
        #         [
        #             self.actors_df,
        #             pd_DataFrame(
        #                 [
        #                     {
        #                         "uid": uid,
        #                         "actor": this_actor,
        #                         "show": False,
        #                         "collection": "image_coll",
        #                         "show_property": None,
        #                     }
        #                 ]
        #             ),
        #         ],
        #         ignore_index=True,
        #     )
        # for uid in self.parent.well_coll.df.query(self.view_filter)["uid"].tolist():
        #     this_actor = self.show_actor_with_property(
        #         uid=uid, collection="well_coll", show_property=None, visible=False
        #     )
        #     # New Pandas >= 2.0.0
        #     self.actors_df = pd_concat(
        #         [
        #             self.actors_df,
        #             pd_DataFrame(
        #                 [
        #                     {
        #                         "uid": uid,
        #                         "actor": this_actor,
        #                         "show": False,
        #                         "collection": "well_coll",
        #                         "show_property": None,
        #                     }
        #                 ]
        #             ),
        #         ],
        #         ignore_index=True,
        #     )
        # for uid in self.parent.fluid_coll.df.query(self.view_filter)["uid"].tolist():
        #     this_actor = self.show_actor_with_property(
        #         uid=uid, collection="fluid_coll", show_property=None, visible=False
        #     )
        #     # New Pandas >= 2.0.0
        #     self.actors_df = pd_concat(
        #         [
        #             self.actors_df,
        #             pd_DataFrame(
        #                 [
        #                     {
        #                         "uid": uid,
        #                         "actor": this_actor,
        #                         "show": False,
        #                         "collection": "fluid_coll",
        #                         "show_property": None,
        #                     }
        #                 ]
        #             ),
        #         ],
        #         ignore_index=True,
        #     )
        # for uid in self.parent.backgrnd_coll.df.query(self.view_filter)["uid"].tolist():
        #     this_actor = self.show_actor_with_property(
        #         uid=uid,
        #         collection="backgrnd_coll",
        #         show_property=None,
        #         visible=False,
        #     )
        #     # New Pandas >= 2.0.0
        #     self.actors_df = pd_concat(
        #         [
        #             self.actors_df,
        #             pd_DataFrame(
        #                 [
        #                     {
        #                         "uid": uid,
        #                         "actor": this_actor,
        #                         "show": False,
        #                         "collection": "backgrnd_coll",
        #                         "show_property": None,
        #                     }
        #                 ]
        #             ),
        #         ],
        #         ignore_index=True,
        #     )

    def prop_legend_cmap_modified_update_views(self, this_property=None):
        """Redraw all actors that are currently shown with a property whose colormap has been changed."""
        for uid in self.actors_df["uid"].to_list():
            if (
                self.actors_df.loc[
                    self.actors_df["uid"] == uid, "show_property"
                ].to_list()[0]
                == this_property
            ):
                show = self.actors_df.loc[
                    self.actors_df["uid"] == uid, "show"
                ].to_list()[0]
                collection = self.actors_df.loc[
                    self.actors_df["uid"] == uid, "collection"
                ].to_list()[0]
                # This replaces the previous copy of the actor with the same uid, and updates the actors dataframe.
                # See issue #33 for a discussion on actors replacement by the PyVista add_mesh and add_volume methods.
                this_actor = self.show_actor_with_property(
                    uid=uid,
                    collection=collection,
                    show_property=this_property,
                    visible=show,
                )
                self.actors_df.loc[self.actors_df["uid"] == uid, ["show_property"]] = (
                    this_property
                )

    # ================================  General methods shared by all views - built incrementally =====================

    def initialize_menu_tools(self):
        """This is the base method of the abstract BaseView() class, used to add menu tools used by all windows.
        The code appearing here is appended in subclasses using super().initialize_menu_tools() in their first line.
        Do not use "pass" that would be appended to child classes.
        """

    def closeEvent(self, event):
        """Override the standard closeEvent method by (i) disconnecting all signals."""
        self.enable_actions()
        self.disconnect_all_signals()
        event.accept()

    # ================================  Placeholders for required methods, implemented in child classes ===============

    def change_actor_color(self, uid=None, collection=None):
        """Dummy method to update color for actor uid. Must be implemented in subclasses."""
        return

    def change_actor_opacity(self, uid=None, collection=None):
        """Dummy method to update opacity for actor uid. Must be implemented in subclasses."""
        return

    def change_actor_line_thick(self, uid=None, collection=None):
        """Dummy method to update line thickness for actor uid. Must be implemented in subclasses."""
        return

    def change_actor_point_size(self, uid=None, collection=None):
        """Dummy method to update point size for actor uid. Must be implemented in subclasses."""
        return self.add_all_entities()

    def set_actor_visible(self, uid=None, visible=None, name=None):
        """Dummy method to Set actor uid visible or invisible (visible = True or False).
        Must be implemented in subclasses."""
        return

    def remove_actor_in_view(self, uid=None, redraw=False):
        """Dummy method to remove actor with uid. Must be implemented in subclasses."""
        return

    def show_actor_with_property(
        self, uid=None, collection=None, show_property=None, visible=None
    ):
        """Dummy method to show actor with uid and property. Must be implemented in subclasses."""
        return

    def show_markers(self, uid=None, show_property=None):
        """Dummy method to show markers for uid and property. Must be implemented in subclasses."""
        return

    def show_labels(self, uid=None, collection=None, show_property=None):
        """Dummy method to show labels for uid and property. Must be implemented in subclasses."""
        return

    def initialize_interactor(self):
        """Dummy method to initialize the plotting canvas. Must be implemented in subclasses."""
        return

    def show_qt_canvas(self):
        """Dummy method to show the plotting canvas. Must be implemented in subclasses."""
        return
