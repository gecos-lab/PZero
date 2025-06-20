"""windows_factory.py
PZero© Andrea Bistacchi"""

# General Python imports____
from copy import deepcopy
from uuid import uuid4

# from math import degrees, sqrt, atan2
# import sys
# from time import sleep
# from uuid import UUID (there is already above 'from uuid import uuid4')

# PySide6 imports____
from PySide6.QtWidgets import (
    QMainWindow,
    QMenu,
    QAbstractItemView,
    QDockWidget,
    QSizePolicy,
    QMessageBox,
)
from PySide6.QtGui import QAction
from PySide6.QtCore import Qt
from PySide6.QtCore import Signal as pyqtSignal

# Numpy imports____
from numpy import append as np_append
from numpy import ndarray as np_ndarray

# from numpy import sin as np_sin
# from numpy import cos as np_cos
# from numpy import pi as np_pi
from numpy import array as np_array
from numpy import all as np_all

# from numpy import cross as np_cross

# Pandas imports____
from pandas import DataFrame as pd_DataFrame
from pandas import unique as pd_unique

# VTK imports incl. VTK-Numpy interface____
from vtkmodules.vtkRenderingCore import vtkPropPicker, vtkCellPicker

# import vtk.numpy_interface.dataset_adapter as dsa
from vtkmodules.util import numpy_support
from vtkmodules.vtkInteractionWidgets import vtkCameraOrientationWidget
from vtk import vtkExtractPoints, vtkSphere, vtkAppendPolyData

# PyVista imports____
from pyvista import global_theme as pv_global_theme
from pyvistaqt import QtInteractor as pvQtInteractor
from pyvista import Box as pv_Box
from pyvista import Line as pv_Line
from pyvista import Disc as pv_Disc
from pyvista import PointSet as pvPointSet
from pyvista import Plotter as pv_plot
from pyvista import Arrow as pv_Arrow

# Matplotlib imports____
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

# the following is customized in subclass NavigationToolbar a few lines below
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT

# DO NOT USE import matplotlib.pyplot as plt  IT CREATES A DUPLICATE WINDOW IN NOTEBOOK
# from matplotlib.figure import Figure
# from matplotlib.offsetbox import TextArea
from matplotlib.lines import Line2D
from matplotlib.image import AxesImage
from matplotlib.collections import PathCollection
from matplotlib.tri import TriContourSet
import matplotlib.style as mplstyle

# from matplotlib.backend_bases import FigureCanvasBase

# mplstereonet import____
import mplstereonet

# PZero imports____
from pzero.ui.base_view_window_ui import Ui_BaseViewWindow
from pzero.collections.geological_collection import GeologicalCollection
from pzero.helpers.helper_dialogs import (
    input_one_value_dialog,
    input_combo_dialog,
    message_dialog,
    multiple_input_dialog,
    progress_dialog,
    save_file_dialog,
)
from pzero.helpers.helper_functions import best_fitting_plane, gen_frame
from pzero.helpers.helper_widgets import Vector
from .entities_factory import (
    VertexSet,
    PolyLine,
    TriSurf,
    XsVertexSet,
    XsPolyLine,
    DEM,
    PCDom,
    MapImage,
    Voxet,
    XsVoxet,
    Seismics,
    XsImage,
    PolyData,
    Well,
    WellMarker,
    WellTrace,
    Attitude,
)
from .orientation_analysis import get_dip_dir_vectors
from .build_and_update.backgrounds import *
from .build_and_update.boundary import *
from .build_and_update.dom import *
from .build_and_update.fluids import *
from .build_and_update.geology import *
from .build_and_update.image import *
from .build_and_update.mesh3d import *
from .build_and_update.wells import *
from .build_and_update.xsections import *
from .add_remove_update_actors.background import *
from .add_remove_update_actors.boundary import *
from .add_remove_update_actors.dom import *
from .add_remove_update_actors.fluid import *
from .add_remove_update_actors.geology import *
from .add_remove_update_actors.image import *
from .add_remove_update_actors.mesh3d import *
from .add_remove_update_actors.wells import *
from .add_remove_update_actors.xsection import *

# Background color for matplotlib plots.
# Could be made interactive in the future.
# 'fast' is supposed to make plotting large objects faster.
mplstyle.use(["dark_background", "fast"])


class NavigationToolbar(NavigationToolbar2QT):
    """Can customize NavigationToolbar2QT to display only the buttons we need.
    Note that toolitems is a class variable defined before __init__."""

    toolitems = [
        t
        for t in NavigationToolbar2QT.toolitems
        if t[0] in ("Home", "Pan", "Zoom", "Save")
    ]

    def __init__(self, parent=None, *args, **kwargs):
        super(NavigationToolbar, self).__init__(parent, *args, **kwargs)


class DockWindow(QDockWidget):
    """Creates a QDockWidget and then fills it with a single QWidget that includes all objects of a dockable graphical window.
    Each window needs its specific dock widget in order to be dockable, movable anc closable independently.
    In the following code, copied from Qt Designer (Form > View Python code - layout saved as project_window_with_dock_widget.ui),
    the dock widget is locked to the right dock area, floatable, movable and closable, hence it will only appear in the
    right dock area or undocked on the desktop."""

    def __init__(self, parent=None, window_type=None, *args, **kwargs):
        super(DockWindow, self).__init__(parent, *args, **kwargs)
        n_docks = len(parent.findChildren(QDockWidget))
        # Setup property and connect signal to delete dock widget (not only hide) when the project is closed.
        parent.project_close_signal.connect(self.deleteLater)
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
        # Create the graphical window as a QWidget to be included into the QDockWidget as its content
        if window_type == "View3D":
            self.canvas = View3D(parent=parent)
        elif window_type == "ViewMap":
            self.canvas = ViewMap(parent=parent)
        elif window_type == "ViewXsection":
            self.canvas = ViewXsection(parent=parent)
        elif window_type == "ViewStereoplot":
            self.canvas = ViewStereoplot(parent=parent)
        else:
            # Exit doing nothing in case the window type is not recognized.
            print("window type not recognized")
            return
        # Add the content widget to the dock widget and add the dock widget to the main project window.
        # After this has been set, calling self.canvas returns the same object as calling self.widget().
        self.setWidget(self.canvas)
        # Add dock widget to main window (= parent).
        parent.addDockWidget(Qt.RightDockWidgetArea, self)
        # Make all dock widgets tabbed if more than one is open.
        if n_docks > 1:
            parent.tabifyDockWidget(parent.findChildren(QDockWidget)[0], self)
        else:
            if window_type == "View3D":
                print(
                    "Warning: we have to add some code here to solve the orientation widget problem."
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
        if isinstance(self.canvas, VTKView):
            self.canvas.plotter.close()


class BaseView(QMainWindow, Ui_BaseViewWindow):
    """Create base view - abstract class providing common methods for all views. This includes all side tree and list
    views, but not the main plotting canvas, that must be managed by subclasses.
    parent is the QT object that is launching this one, hence the ProjectWindow() instance.
    """

    def __init__(self, parent=None, *args, **kwargs):
        super(BaseView, self).__init__(parent, *args, **kwargs)
        self.setupUi(self)
        # _____________________________________________________________________________
        # THE FOLLOWING ACTUALLY DELETES ANY REFERENCE TO CLOSED WINDOWS, HENCE FREEING
        # MEMORY, BUT COULD CREATE PROBLEMS WITH SIGNALS THAT ARE STILL ACTIVE
        # SEE DISCUSSIONS ON QPointer AND WA_DeleteOnClose ON THE INTERNET
        # _____________________________________________________________________________
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.parent = parent

        self.actors_df = pd_DataFrame(
            columns=["uid", "actor", "show", "collection", "show_property"]
        )

        # Create empty list of selected uid's
        # _____________________________________________
        # SEE IF IT IA A GOOD IDEA TO USE INSTEAD A NEW "selected" COLUMN IN self.actors_df
        # _____________________________________________

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

        self.toggle_backgrounds_visibility = lambda item: toggle_backgrounds_visibility(
            self, item
        )

        self.toggle_boundary_visibility = lambda item: toggle_boundary_visibility(
            self, item
        )

        self.toggle_dom_visibility = lambda cell: toggle_dom_visibility(self, cell)

        self.toggle_fluids_visibility = lambda item: toggle_fluids_visibility(
            self, item
        )

        self.toggle_geology_visibility = lambda item: toggle_geology_visibility(
            self, item
        )

        self.toggle_image_visibility = lambda cell: toggle_image_visibility(self, cell)

        self.toggle_mesh3d_visibility = lambda cell: toggle_mesh3d_visibility(
            self, cell
        )

        self.toggle_well_visibility = lambda item: toggle_well_visibility(self, item)

        self.toggle_xsection_visibility = lambda item: toggle_xsection_visibility(
            self, item
        )

        create_geology_tree(self)
        create_topology_tree(self)
        create_xsections_tree(self)
        create_boundary_list(self)
        create_mesh3d_list(self)
        create_dom_list(self)
        create_image_list(self)
        create_well_tree(self)
        create_fluids_tree(self)
        create_fluids_topology_tree(self)
        create_backgrounds_tree(self)
        create_backgrounds_topology_tree(self)

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

    # ================================  general methods ================================

    # General methods shared by all views

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
        """Add all entities in project collections.
        All objects are visible by default -> show = True
        This must be reimplemented for cross-sections in order
        to show entities belonging to the section only."""
        for uid in self.parent.geol_coll.df.query(self.view_filter)["uid"].tolist():
            this_actor = self.show_actor_with_property(
                uid=uid, collection="geol_coll", show_property=None, visible=True
            )
            # Old Pandas <= 1.5.3
            # self.actors_df = self.actors_df.append(
            #     {
            #         "uid": uid,
            #         "actor": this_actor,
            #         "show": True,
            #         "collection": "geol_coll",
            #         "show_property": None,
            #     },
            #     ignore_index=True,
            # )
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
                                "collection": "geol_coll",
                                "show_property": None,
                            }
                        ]
                    ),
                ],
                ignore_index=True,
            )
        try:
            for uid in self.parent.xsect_coll.df.query(self.view_filter)[
                "uid"
            ].tolist():
                this_actor = self.show_actor_with_property(
                    uid=uid, collection="xsect_coll", show_property=None, visible=False
                )
                # Old Pandas <= 1.5.3
                # self.actors_df = self.actors_df.append(
                #     {
                #         "uid": uid,
                #         "actor": this_actor,
                #         "show": False,
                #         "collection": "xsect_coll",
                #         "show_property": None,
                #     },
                #     ignore_index=True,
                # )
                # New Pandas >= 2.0.0
                self.actors_df = pd_concat(
                    [
                        self.actors_df,
                        pd_DataFrame(
                            [
                                {
                                    "uid": uid,
                                    "actor": this_actor,
                                    "show": False,
                                    "collection": "xsect_coll",
                                    "show_property": None,
                                }
                            ]
                        ),
                    ],
                    ignore_index=True,
                )
        except:
            # This plots the X section frame in cases where a X section is plotting itself in a NewXsView()
            this_actor = self.show_actor_with_property(
                uid=self.this_x_section_uid,
                collection="xsect_coll",
                show_property=None,
                visible=False,
            )
            # Old Pandas <= 1.5.3
            # self.actors_df = self.actors_df.append(
            #     {
            #         "uid": self.this_x_section_uid,
            #         "actor": this_actor,
            #         "show": False,
            #         "collection": "xsect_coll",
            #         "show_property": None,
            #     },
            #     ignore_index=True,
            # )
            # New Pandas >= 2.0.0
            self.actors_df = pd_concat(
                [
                    self.actors_df,
                    pd_DataFrame(
                        [
                            {
                                "uid": self.this_x_section_uid,
                                "actor": this_actor,
                                "show": False,
                                "collection": "xsect_coll",
                                "show_property": None,
                            }
                        ]
                    ),
                ],
                ignore_index=True,
            )
        for uid in self.parent.boundary_coll.df.query(self.view_filter)["uid"].tolist():
            this_actor = self.show_actor_with_property(
                uid=uid, collection="boundary_coll", show_property=None, visible=False
            )
            # Old Pandas <= 1.5.3
            # self.actors_df = self.actors_df.append(
            #     {
            #         "uid": uid,
            #         "actor": this_actor,
            #         "show": False,
            #         "collection": "boundary_coll",
            #         "show_property": None,
            #     },
            #     ignore_index=True,
            # )
            # New Pandas >= 2.0.0
            self.actors_df = pd_concat(
                [
                    self.actors_df,
                    pd_DataFrame(
                        [
                            {
                                "uid": uid,
                                "actor": this_actor,
                                "show": False,
                                "collection": "boundary_coll",
                                "show_property": None,
                            }
                        ]
                    ),
                ],
                ignore_index=True,
            )
        for uid in self.parent.mesh3d_coll.df.query(self.view_filter)["uid"].tolist():
            this_actor = self.show_actor_with_property(
                uid=uid, collection="mesh3d_coll", show_property=None, visible=False
            )
            # Old Pandas <= 1.5.3
            # self.actors_df = self.actors_df.append(
            #     {
            #         "uid": uid,
            #         "actor": this_actor,
            #         "show": False,
            #         "collection": "mesh3d_coll",
            #         "show_property": None,
            #     },
            #     ignore_index=True,
            # )
            # New Pandas >= 2.0.0
            self.actors_df = pd_concat(
                [
                    self.actors_df,
                    pd_DataFrame(
                        [
                            {
                                "uid": uid,
                                "actor": this_actor,
                                "show": False,
                                "collection": "mesh3d_coll",
                                "show_property": None,
                            }
                        ]
                    ),
                ],
                ignore_index=True,
            )
        for uid in self.parent.dom_coll.df.query(self.view_filter)["uid"].tolist():
            this_actor = self.show_actor_with_property(
                uid=uid, collection="dom_coll", show_property=None, visible=False
            )
            # Old Pandas <= 1.5.3
            # self.actors_df = self.actors_df.append(
            #     {
            #         "uid": uid,
            #         "actor": this_actor,
            #         "show": False,
            #         "collection": "dom_coll",
            #         "show_property": None,
            #     },
            #     ignore_index=True,
            # )
            # New Pandas >= 2.0.0
            self.actors_df = pd_concat(
                [
                    self.actors_df,
                    pd_DataFrame(
                        [
                            {
                                "uid": uid,
                                "actor": this_actor,
                                "show": False,
                                "collection": "dom_coll",
                                "show_property": None,
                            }
                        ]
                    ),
                ],
                ignore_index=True,
            )
        for uid in self.parent.image_coll.df.query(self.view_filter)["uid"].tolist():
            this_actor = self.show_actor_with_property(
                uid=uid, collection="image_coll", show_property=None, visible=False
            )
            # Old Pandas <= 1.5.3
            # self.actors_df = self.actors_df.append(
            #     {
            #         "uid": uid,
            #         "actor": this_actor,
            #         "show": False,
            #         "collection": "image_coll",
            #         "show_property": None,
            #     },
            #     ignore_index=True,
            # )
            # New Pandas >= 2.0.0
            self.actors_df = pd_concat(
                [
                    self.actors_df,
                    pd_DataFrame(
                        [
                            {
                                "uid": uid,
                                "actor": this_actor,
                                "show": False,
                                "collection": "image_coll",
                                "show_property": None,
                            }
                        ]
                    ),
                ],
                ignore_index=True,
            )
        for uid in self.parent.well_coll.df.query(self.view_filter)["uid"].tolist():
            this_actor = self.show_actor_with_property(
                uid=uid, collection="well_coll", show_property=None, visible=False
            )
            # Old Pandas <= 1.5.3
            # self.actors_df = self.actors_df.append(
            #     {
            #         "uid": uid,
            #         "actor": this_actor,
            #         "show": False,
            #         "collection": "well_coll",
            #         "show_property": None,
            #     },
            #     ignore_index=True,
            # )
            # New Pandas >= 2.0.0
            self.actors_df = pd_concat(
                [
                    self.actors_df,
                    pd_DataFrame(
                        [
                            {
                                "uid": uid,
                                "actor": this_actor,
                                "show": False,
                                "collection": "well_coll",
                                "show_property": None,
                            }
                        ]
                    ),
                ],
                ignore_index=True,
            )
        for uid in self.parent.fluid_coll.df.query(self.view_filter)["uid"].tolist():
            this_actor = self.show_actor_with_property(
                uid=uid, collection="fluid_coll", show_property=None, visible=False
            )
            # Old Pandas <= 1.5.3
            # self.actors_df = self.actors_df.append(
            #     {
            #         "uid": uid,
            #         "actor": this_actor,
            #         "show": False,
            #         "collection": "fluid_coll",
            #         "show_property": None,
            #     },
            #     ignore_index=True,
            # )
            # New Pandas >= 2.0.0
            self.actors_df = pd_concat(
                [
                    self.actors_df,
                    pd_DataFrame(
                        [
                            {
                                "uid": uid,
                                "actor": this_actor,
                                "show": False,
                                "collection": "fluid_coll",
                                "show_property": None,
                            }
                        ]
                    ),
                ],
                ignore_index=True,
            )
        for uid in self.parent.backgrnd_coll.df.query(self.view_filter)["uid"].tolist():
            this_actor = self.show_actor_with_property(
                uid=uid,
                collection="backgrnd_coll",
                show_property=None,
                visible=False,
            )
            # Old Pandas <= 1.5.3
            # self.actors_df = self.actors_df.append(
            #     {
            #         "uid": uid,
            #         "actor": this_actor,
            #         "show": False,
            #         "collection": "backgrnd_coll",
            #         "show_property": None,
            #     },
            #     ignore_index=True,
            # )
            # New Pandas >= 2.0.0
            self.actors_df = pd_concat(
                [
                    self.actors_df,
                    pd_DataFrame(
                        [
                            {
                                "uid": uid,
                                "actor": this_actor,
                                "show": False,
                                "collection": "backgrnd_coll",
                                "show_property": None,
                            }
                        ]
                    ),
                ],
                ignore_index=True,
            )

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

    def initialize_menu_tools(self):
        """This is the base method of the abstract BaseView() class, used to add menu tools used by all windows.
        The code appearing here is appended in subclasses using super().initialize_menu_tools() in their first line.
        """

    def initialize_interactor(self):
        """Dummy method to initialize the plotting canvas. Must be implemented in subclasses."""
        return

    def show_qt_canvas(self):
        """Dummy method to show the plotting canvas. Must be implemented in subclasses."""
        return

    def closeEvent(self, event):
        """Override the standard closeEvent method by (i) disconnecting all signals and,
        (ii) closing the plotter for vtk windows."""
        self.enable_actions()
        self.disconnect_all_signals()
        if isinstance(self, VTKView):
            self.plotter.close()  # needed to cleanly close the vtk plotter
        event.accept()

    def disable_actions(self):
        """Freeze all actions while doing something."""
        # self.parent.findChildren(QAction) returns a list of all actions in the application.
        for action in self.parent.findChildren(QAction):
            try:
                # try - except added to catch an inexplicable bug with an action with text=""
                if isinstance(action.parent(), NavigationToolbar) is False:
                    action.setDisabled(True)
            except:
                pass

    def enable_actions(self):
        """Un-freeze all actions after having done something."""
        # self.parent.findChildren(QAction) returns a list of all actions in the application.
        for action in self.parent.findChildren(QAction):
            action.setEnabled(True)
            # try:
            #     # try - except added for symmetry with disable_actions (bug with an action with text="")
            #     action.setEnabled(True)
            #     print("enable: ", action)
            # except:
            #     pass

    def print_terminal(self, string=None):
        """Show string in terminal."""
        try:
            self.parent.TextTerminal.appendPlainText(string)
        except:
            self.parent.TextTerminal.appendPlainText("error printing in terminal")


class VTKView(BaseView):
    """Abstract class used as a base for all classes using the VTK/PyVista plotting canvas."""

    def __init__(self, *args, **kwargs):
        super(VTKView, self).__init__(*args, **kwargs)

    def change_actor_color(self, uid=None, collection=None):
        """Update color for actor uid"""
        if uid in self.actors_df.uid:
            # _______________________________________________________________________
            # THIS COULD BE SIMPLIFIED IF A SUPER-CLASS TO COLLECTIONS IS IMPLEMENTED
            # _______________________________________________________________________
            if collection == "geol_coll":
                color_R = self.parent.geol_coll.get_uid_legend(uid=uid)["color_R"]
                color_G = self.parent.geol_coll.get_uid_legend(uid=uid)["color_G"]
                color_B = self.parent.geol_coll.get_uid_legend(uid=uid)["color_B"]
            elif collection == "xsect_coll":
                color_R = self.parent.xsect_coll.get_legend()["color_R"]
                color_G = self.parent.xsect_coll.get_legend()["color_G"]
                color_B = self.parent.xsect_coll.get_legend()["color_B"]
            elif collection == "boundary_coll":
                color_R = self.parent.boundary_coll.get_legend()["color_R"]
                color_G = self.parent.boundary_coll.get_legend()["color_G"]
                color_B = self.parent.boundary_coll.get_legend()["color_B"]
            elif collection == "mesh3d_coll":
                color_R = self.parent.mesh3d_coll.get_legend()["color_R"]
                color_G = self.parent.mesh3d_coll.get_legend()["color_G"]
                color_B = self.parent.mesh3d_coll.get_legend()["color_B"]
            elif collection == "dom_coll":
                color_R = self.parent.dom_coll.get_legend()["color_R"]
                color_G = self.parent.dom_coll.get_legend()["color_G"]
                color_B = self.parent.dom_coll.get_legend()["color_B"]
            elif collection == "well_coll":
                color_R = self.parent.well_coll.get_uid_legend(uid=uid)["color_R"]
                color_G = self.parent.well_coll.get_uid_legend(uid=uid)["color_G"]
                color_B = self.parent.well_coll.get_uid_legend(uid=uid)["color_B"]
            elif collection == "fluid_coll":
                color_R = self.parent.fluid_coll.get_uid_legend(uid=uid)["color_R"]
                color_G = self.parent.fluid_coll.get_uid_legend(uid=uid)["color_G"]
                color_B = self.parent.fluid_coll.get_uid_legend(uid=uid)["color_B"]
            elif collection == "backgrnd_coll":
                color_R = self.parent.backgrnd_coll.get_uid_legend(uid=uid)["color_R"]
                color_G = self.parent.backgrnd_coll.get_uid_legend(uid=uid)["color_G"]
                color_B = self.parent.backgrnd_coll.get_uid_legend(uid=uid)["color_B"]
            # No color for image
            # Now update color for actor uid
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[
                0
            ].GetProperty().SetColor(color_RGB)
        else:
            return

    def change_actor_opacity(self, uid=None, collection=None):
        """Update opacity for actor uid"""
        if uid in self.actors_df.uid:
            # _______________________________________________________________________
            # THIS COULD BE SIMPLIFIED IF A SUPER-CLASS TO COLLECTIONS IS IMPLEMENTED
            # _______________________________________________________________________
            if collection == "geol_coll":
                opacity = self.parent.geol_coll.get_uid_legend(uid=uid)["opacity"] / 100
            elif collection == "xsect_coll":
                opacity = self.parent.xsect_coll.get_legend()["opacity"] / 100
            elif collection == "boundary_coll":
                opacity = self.parent.boundary_coll.get_legend()["opacity"] / 100
            elif collection == "mesh3d_coll":
                opacity = self.parent.mesh3d_coll.get_legend()["opacity"] / 100
            elif collection == "dom_coll":
                opacity = self.parent.dom_coll.get_legend()["opacity"] / 100
            elif collection == "well_coll":
                opacity = self.parent.well_coll.get_uid_legend(uid=uid)["opacity"] / 100
            elif collection == "fluid_coll":
                opacity = (
                    self.parent.fluid_coll.get_uid_legend(uid=uid)["opacity"] / 100
                )
            elif collection == "backgrnd_coll":
                opacity = (
                    self.parent.backgrnd_coll.get_uid_legend(uid=uid)["opacity"] / 100
                )
            elif collection == "image_coll":
                opacity = self.parent.image_coll.get_legend()["opacity"] / 100
            # Now update color for actor uid
            self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[
                0
            ].GetProperty().SetOpacity(opacity)
        else:
            return

    def change_actor_line_thick(self, uid=None, collection=None):
        """Update line thickness for actor uid"""
        if uid in self.actors_df.uid:
            # _______________________________________________________________________
            # THIS COULD BE SIMPLIFIED IF A SUPER-CLASS TO COLLECTIONS IS IMPLEMENTED
            # _______________________________________________________________________
            if collection == "geol_coll":
                line_thick = self.parent.geol_coll.get_uid_legend(uid=uid)["line_thick"]
            elif collection == "xsect_coll":
                line_thick = self.parent.xsect_coll.get_legend()["line_thick"]
            elif collection == "boundary_coll":
                line_thick = self.parent.boundary_coll.get_legend()["line_thick"]
            elif collection == "mesh3d_coll":
                line_thick = self.parent.mesh3d_coll.get_legend()["line_thick"]
            elif collection == "dom_coll":
                line_thick = self.parent.dom_coll.get_legend()["line_thick"]
            elif collection == "well_coll":
                line_thick = self.parent.well_coll.get_uid_legend(uid=uid)["line_thick"]
            elif collection == "fluid_coll":
                line_thick = self.parent.fluid_coll.get_uid_legend(uid=uid)[
                    "line_thick"
                ]
            elif collection == "backgrnd_coll":
                line_thick = self.parent.backgrnd_coll.get_uid_legend(uid=uid)[
                    "line_thick"
                ]
            # No thickness for image
            # Now update thickness for actor uid
            self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[
                0
            ].GetProperty().SetLineWidth(line_thick)
        else:
            return

    def change_actor_point_size(self, uid=None, collection=None):
        """Update point size for actor uid"""
        if uid in self.actors_df.uid:
            # _______________________________________________________________________
            # THIS COULD BE SIMPLIFIED IF A SUPER-CLASS TO COLLECTIONS IS IMPLEMENTED
            # _______________________________________________________________________
            if collection == "geol_coll":
                point_size = self.parent.geol_coll.get_uid_legend(uid=uid)["point_size"]
            elif collection == "xsect_coll":
                point_size = self.parent.xsect_coll.get_legend()["point_size"]
            elif collection == "boundary_coll":
                point_size = self.parent.boundary_coll.get_legend()["point_size"]
            elif collection == "mesh3d_coll":
                point_size = self.parent.mesh3d_coll.get_legend()["point_size"]
            elif collection == "dom_coll":
                point_size = self.parent.dom_coll.get_legend()["point_size"]
                """Note: no legend for image."""
            elif collection == "well_coll":
                point_size = self.parent.well_coll.get_uid_legend(uid=uid)["point_size"]
            elif collection == "fluid_coll":
                point_size = self.parent.fluid_coll.get_uid_legend(uid=uid)[
                    "point_size"
                ]
            elif collection == "backgrnd_coll":
                point_size = self.parent.backgrnd_coll.get_uid_legend(uid=uid)[
                    "point_size"
                ]
            # No thickness for image
            # Now update point size for actor uid
            self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[
                0
            ].GetProperty().SetPointSize(point_size)
        else:
            return

    def set_actor_visible(self, uid=None, visible=None, name=None):
        """Set actor uid visible or invisible (visible = True or False)"""
        this_actor = self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[0]
        collection = self.actors_df.loc[
            self.actors_df["uid"] == uid, "collection"
        ].values[0]
        actors = self.plotter.renderer.actors
        if collection == "well_coll":
            # case for WELLS
            if name == "Trace":
                # case for WELL TRACE
                if f"{uid}_prop" in actors.keys():
                    prop_actor = actors[f"{uid}_prop"]
                    prop_actor.SetVisibility(visible)
                if f"{uid}_geo" in actors:
                    geo_actor = actors[f"{uid}_geo"]
                    geo_actor.SetVisibility(visible)
                # self.plotter.remove_actor(f'{uid}_prop')
                # self.plotter.remove_actor(f'{uid}_geo')
                this_actor.SetVisibility(visible)
            elif name == "Markers":
                # case for WELL markers
                if f"{uid}_marker-labels" in actors.keys():
                    marker_actor_labels = actors[f"{uid}_marker-labels"]
                    marker_actor_points = actors[f"{uid}_marker-points"]
                    marker_actor_labels.SetVisibility(visible)
                    marker_actor_points.SetVisibility(visible)
        elif collection == "backgrnd_coll":
            # case for BACKGROUNDS
            if f"{uid}_name-labels" in actors.keys():
                marker_actor_labels = actors[f"{uid}_name-labels"]
                marker_actor_labels.SetVisibility(visible)
            this_actor.SetVisibility(visible)
        else:
            # case for ALL OTHER COLLECTIONS
            this_actor.SetVisibility(visible)

    def remove_actor_in_view(self, uid=None, redraw=False):
        """ "Remove actor from plotter"""
        # plotter.remove_actor can remove a single entity or a list of entities as actors ->
        # here we remove a single entity
        if not self.actors_df.loc[self.actors_df["uid"] == uid].empty:
            this_actor = self.actors_df.loc[
                self.actors_df["uid"] == uid, "actor"
            ].values[0]
            success = self.plotter.remove_actor(this_actor)
            self.actors_df.drop(
                self.actors_df[self.actors_df["uid"] == uid].index, inplace=True
            )

    def show_actor_with_property(
        self, uid=None, collection=None, show_property=None, visible=None
    ):
        """
        Show actor with scalar property (default None). See details in:
        https://github.com/pyvista/pyvista/blob/140b15be1d4021b81ded46b1c212c70e86a98ee7/pyvista/plotting/plotting.py#L1045
        """
        # First get the vtk object from its collection.
        show_property_title = show_property
        this_coll = eval("self.parent." + collection)
        if collection in ["geol_coll", "fluid_coll", "backgrnd_coll", "well_coll"]:
            color_R = this_coll.get_uid_legend(uid=uid)["color_R"]
            color_G = this_coll.get_uid_legend(uid=uid)["color_G"]
            color_B = this_coll.get_uid_legend(uid=uid)["color_B"]
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            line_thick = this_coll.get_uid_legend(uid=uid)["line_thick"]
            point_size = this_coll.get_uid_legend(uid=uid)["point_size"]
            opacity = this_coll.get_uid_legend(uid=uid)["opacity"] / 100
            plot_entity = this_coll.get_uid_vtk_obj(uid)
        elif collection in [
            "xsect_coll",
            "boundary_coll",
            "mesh3d_coll",
            "dom_coll",
            "image_coll",
        ]:
            color_R = this_coll.get_legend()["color_R"]
            color_G = this_coll.get_legend()["color_G"]
            color_B = this_coll.get_legend()["color_B"]
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            line_thick = this_coll.get_legend()["line_thick"]
            point_size = this_coll.get_legend()["point_size"]
            opacity = this_coll.get_legend()["opacity"] / 100
            plot_entity = this_coll.get_uid_vtk_obj(uid)
        else:
            # catch errors
            print("no collection", collection)
            this_actor = None
        # Then plot the vtk object with proper options.
        if isinstance(plot_entity, (PolyLine, TriSurf, XsPolyLine)) and not isinstance(
            plot_entity, WellTrace
        ):
            plot_rgb_option = None
            if isinstance(plot_entity.points, np_ndarray):
                # This  check is needed to avoid errors when trying to plot an empty
                # PolyData, just created at the beginning of a digitizing session.
                if show_property == "none" or show_property is None:
                    show_property = None
                elif show_property == "X":
                    show_property = plot_entity.points_X
                elif show_property == "Y":
                    show_property = plot_entity.points_Y
                elif show_property == "Z":
                    show_property = plot_entity.points_Z
                else:
                    if plot_entity.get_point_data_shape(show_property)[-1] == 3:
                        plot_rgb_option = True
                this_actor = self.plot_mesh(
                    uid=uid,
                    plot_entity=plot_entity,
                    color_RGB=color_RGB,
                    show_property=show_property,
                    color_bar_range=None,
                    show_property_title=show_property_title,
                    line_thick=line_thick,
                    plot_texture_option=False,
                    plot_rgb_option=plot_rgb_option,
                    visible=visible,
                    point_size=point_size,
                    opacity=opacity,
                )
            else:
                this_actor = None
        elif isinstance(plot_entity, (VertexSet, XsVertexSet, WellMarker, Attitude)):
            if isinstance(plot_entity, Attitude):
                pickable = False
            else:
                pickable = True
            style = "points"
            plot_rgb_option = None
            smooth_shading = False
            if isinstance(plot_entity.points, np_ndarray):
                # This  check is needed to avoid errors when trying to plot an empty
                # PolyData, just created at the beginning of a digitizing session.
                if show_property == "none" or show_property is None:
                    show_property = None
                elif show_property == "X":
                    show_property = plot_entity.points_X
                elif show_property == "Y":
                    show_property = plot_entity.points_Y
                elif show_property == "Z":
                    show_property = plot_entity.points_Z
                elif show_property == "Normals":
                    show_property_title = None
                    show_property = None
                    style = "surface"
                    appender = vtkAppendPolyData()
                    r = point_size
                    points = plot_entity.points
                    normals = plot_entity.get_point_data("Normals")
                    dip_vectors, dir_vectors = get_dip_dir_vectors(normals=normals)
                    line1 = pv_Line(pointa=(0, 0, 0), pointb=(r, 0, 0))
                    line2 = pv_Line(pointa=(-r, 0, 0), pointb=(r, 0, 0))

                    for point, normal in zip(points, normals):
                        # base = pv_Plane(center=point, direction=normal,i_size=r,j_size=r)
                        base = pv_Disc(
                            center=point, normal=normal, inner=0, outer=r, c_res=30
                        )
                        appender.AddInputData(base)

                    dip_glyph = plot_entity.glyph(geometry=line1, prop=dip_vectors)
                    dir_glyph = plot_entity.glyph(geometry=line2, prop=dir_vectors)

                    appender.AddInputData(dip_glyph)
                    appender.AddInputData(dir_glyph)
                    appender.Update()
                    plot_entity = appender.GetOutput()

                elif show_property == "name":
                    point = plot_entity.points
                    name_value = plot_entity.get_field_data("name")
                    self.plotter.add_point_labels(
                        point,
                        name_value,
                        always_visible=True,
                        show_points=False,
                        font_size=15,
                        shape_opacity=0.5,
                        name=f"{uid}_name",
                    )
                    show_property = None
                    show_property_title = None

                else:
                    if plot_entity.get_point_data_shape(show_property)[-1] == 3:
                        plot_rgb_option = True
                this_actor = self.plot_mesh(
                    uid=uid,
                    plot_entity=plot_entity,
                    color_RGB=color_RGB,
                    show_property=show_property,
                    color_bar_range=None,
                    show_property_title=show_property_title,
                    line_thick=line_thick,
                    plot_texture_option=False,
                    plot_rgb_option=plot_rgb_option,
                    visible=visible,
                    style=style,
                    point_size=point_size,
                    points_as_spheres=True,
                    pickable=pickable,
                    opacity=opacity,
                )
            else:
                this_actor = None
        elif isinstance(plot_entity, DEM):
            # Show texture specified in show_property
            if (
                show_property
                in self.parent.dom_coll.df.loc[
                    self.parent.dom_coll.df["uid"] == uid, "texture_uids"
                ].values[0]
            ):
                active_image = self.parent.image_coll.get_uid_vtk_obj(show_property)
                active_image_texture = active_image.texture
                # active_image_properties_components = active_image.properties_components[0]  # IF USED THIS MUST BE FIXED FOR TEXTURES WITH MORE THAN 3 COMPONENTS
                this_actor = self.plot_mesh(
                    uid=uid,
                    plot_entity=plot_entity,
                    color_RGB=None,
                    show_property=None,
                    color_bar_range=None,
                    show_property_title=None,
                    line_thick=None,
                    plot_texture_option=active_image_texture,
                    plot_rgb_option=False,
                    visible=visible,
                )
            else:
                plot_rgb_option = None
                if show_property == "none" or show_property is None:
                    show_property = None
                elif show_property == "X":
                    show_property = plot_entity.points_X
                elif show_property == "Y":
                    show_property = plot_entity.points_Y
                elif show_property == "Z":
                    show_property = plot_entity.points_Z
                elif show_property == "RGB":
                    show_property = None
                else:
                    if plot_entity.get_point_data_shape(show_property)[-1] == 3:
                        plot_rgb_option = True
                this_actor = self.plot_mesh(
                    uid=uid,
                    plot_entity=plot_entity,
                    color_RGB=color_RGB,
                    show_property=show_property,
                    color_bar_range=None,
                    show_property_title=show_property_title,
                    line_thick=line_thick,
                    plot_texture_option=False,
                    plot_rgb_option=plot_rgb_option,
                    visible=visible,
                )
        elif isinstance(plot_entity, PCDom):
            plot_rgb_option = None
            new_plot = pvPointSet()
            new_plot.ShallowCopy(plot_entity)  # this is temporary
            file = self.parent.dom_coll.df.loc[
                self.parent.dom_coll.df["uid"] == uid, "name"
            ].values[0]
            if isinstance(plot_entity.points, np_ndarray):
                # This check is needed to avoid errors when trying to plot an empty
                # PolyData, just created at the beginning of a digitizing session.
                if show_property == "none" or show_property is None:
                    show_property_value = None
                elif show_property == "X":
                    show_property_value = plot_entity.points_X
                elif show_property == "Y":
                    show_property_value = plot_entity.points_Y
                elif show_property == "Z":
                    show_property_value = plot_entity.points_Z
                elif show_property[-1] == "]":
                    # We can identify multicomponents properties such as RGB[0] or Normals[0] by
                    # taking the last character of the property name ("]").
                    # Get the start and end index of the [n_component]
                    pos1 = show_property.index("[")
                    pos2 = show_property.index("]")
                    # Get the original property (e.g. RGB[0] -> RGB)
                    original_prop = show_property[:pos1]
                    # Get the column index (the n_component value)
                    index = int(show_property[pos1 + 1 : pos2])
                    show_property_value = plot_entity.get_point_data(original_prop)[
                        :, index
                    ]
                else:
                    n_comp = self.parent.dom_coll.get_uid_properties_components(uid)[
                        self.parent.dom_coll.get_uid_properties_names(uid).index(
                            show_property
                        )
                    ]
                    # Get the n of components for the given property. If it's > 1 then do stuff depending
                    # on the type of property (e.g. show_rgb_option -> True if the property is RGB).
                    if n_comp > 1:
                        show_property_value = plot_entity.get_point_data(show_property)
                        plot_rgb_option = True
                    else:
                        show_property_value = plot_entity.get_point_data(show_property)
            this_actor = self.plot_PC_3D(
                uid=uid,
                plot_entity=new_plot,
                color_RGB=color_RGB,
                show_property=show_property_value,
                color_bar_range=None,
                show_property_title=show_property_title,
                plot_rgb_option=plot_rgb_option,
                visible=visible,
                point_size=line_thick,
                opacity=opacity,
            )

        elif isinstance(plot_entity, (MapImage, XsImage)):
            # Do not plot directly image - it is much slower.
            # Texture options according to type.
            if show_property == "none" or show_property is None:
                plot_texture_option = None
            else:
                plot_texture_option = plot_entity.texture
            this_actor = self.plot_mesh(
                uid=uid,
                plot_entity=plot_entity.frame,
                color_RGB=None,
                show_property=None,
                color_bar_range=None,
                show_property_title=None,
                line_thick=line_thick,
                plot_texture_option=plot_texture_option,
                plot_rgb_option=False,
                visible=visible,
                opacity=opacity,
            )
        elif isinstance(plot_entity, Seismics):
            plot_rgb_option = None
            if isinstance(plot_entity.points, np_ndarray):
                # This  check is needed to avoid errors when trying to plot an empty
                # PolyData, just created at the beginning of a digitizing session.
                if show_property == "none" or show_property is None:
                    show_property = None
                elif show_property == "X":
                    show_property = plot_entity.points_X
                elif show_property == "Y":
                    show_property = plot_entity.points_Y
                elif show_property == "Z":
                    show_property = plot_entity.points_Z
                else:
                    if plot_entity.get_point_data_shape(show_property)[-1] == 3:
                        plot_rgb_option = True
                this_actor = self.plot_mesh(
                    uid=uid,
                    plot_entity=plot_entity,
                    color_RGB=color_RGB,
                    show_property=show_property,
                    color_bar_range=None,
                    show_property_title=show_property_title,
                    line_thick=line_thick,
                    plot_texture_option=False,
                    plot_rgb_option=plot_rgb_option,
                    visible=visible,
                    opacity=opacity,
                )
            else:
                this_actor = None
        elif isinstance(plot_entity, Voxet):
            plot_rgb_option = None
            if plot_entity.cells_number > 0:
                # This  check is needed to avoid errors when trying to plot an empty Voxet.
                # Here we treat X, Y, Z as None, in order to avoid a crash related to the fact that Voxets
                # do not have XYZ coordinates stored explicitly. This can be improved in the future.
                if any(
                    [
                        show_property == "none",
                        show_property is None,
                        show_property == "X",
                        show_property == "Y",
                        show_property == "Z",
                    ]
                ):
                    show_property = None
                else:
                    if plot_entity.get_point_data_shape(show_property)[-1] == 3:
                        plot_rgb_option = True
                this_actor = self.plot_mesh(
                    uid=uid,
                    plot_entity=plot_entity,
                    color_RGB=None,
                    show_property=show_property,
                    color_bar_range=None,
                    show_property_title=show_property_title,
                    line_thick=line_thick,
                    plot_texture_option=False,
                    plot_rgb_option=plot_rgb_option,
                    visible=visible,
                    opacity=opacity,
                )
            else:
                this_actor = None
        elif isinstance(plot_entity, WellTrace):
            plot_rgb_option = None
            if show_property == "none" or show_property is None:
                show_property = None
                self.plotter.remove_actor(f"{uid}_prop")
            elif show_property == "X":
                show_property = plot_entity.points_X
            elif show_property == "Y":
                show_property = plot_entity.points_Y
            elif show_property == "Z":
                show_property = plot_entity.points_Z
            elif show_property == "MD":
                show_property = plot_entity.get_point_data(data_key="MD")
            else:
                prop = plot_entity.plot_along_trace(
                    show_property, method=self.trace_method, camera=self.plotter.camera
                )
                self.plotter.add_actor(prop, name=f"{uid}_prop")
                show_property = None
                show_property_title = None
            this_actor = self.plot_mesh(
                uid=uid,
                plot_entity=plot_entity,
                color_RGB=color_RGB,
                show_property=show_property,
                color_bar_range=None,
                show_property_title=show_property_title,
                line_thick=line_thick,
                plot_texture_option=False,
                plot_rgb_option=plot_rgb_option,
                visible=visible,
                render_lines_as_tubes=False,
                opacity=opacity,
            )
        else:
            # catch errors
            print("[Windows factory]: actor with no class")
            this_actor = None
        return this_actor

    def show_markers(self, uid=None, show_property=None):
        plot_entity = self.parent.well_coll.get_uid_vtk_obj(uid)
        marker_data = self.parent.well_coll.get_uid_marker_names(uid)
        if show_property == "none" or show_property is None:
            show_property = None
            self.plotter.remove_actor(f"{uid}_marker-labels")
            self.plotter.remove_actor(f"{uid}_marker-points")
        elif show_property in marker_data:
            points_pos, points_labels = plot_entity.plot_markers(show_property)
            # print(points_pos,points_labels)
            this_actor = self.plotter.add_point_labels(
                points_pos,
                points_labels,
                always_visible=True,
                show_points=True,
                render_points_as_spheres=True,
                point_size=15,
                font_size=30,
                shape_opacity=0.5,
                name=f"{uid}_marker",
            )
            show_property = None
            show_property_title = None

    def show_labels(self, uid=None, collection=None, show_property=None):
        if collection == "geol_coll":
            plot_entity = self.parent.geol_coll.get_uid_vtk_obj(uid)
            point = plot_entity.GetCenter()
            name_value = self.parent.geol_coll.get_uid_name(uid)
        elif collection == "xsect_coll":
            plot_entity = self.parent.xsect_coll.get_uid_vtk_obj(uid)
            point = plot_entity.GetCenter()
            name_value = self.parent.xsect_coll.get_uid_name(uid)
        elif collection == "boundary_coll":
            plot_entity = self.parent.boundary_coll.get_uid_vtk_obj(uid)
            point = plot_entity.GetCenter()
            name_value = self.parent.boundary_coll.get_uid_name(uid)
        elif collection == "mesh3d_coll":
            plot_entity = self.parent.mesh3d_coll.get_uid_vtk_obj(uid)
            point = plot_entity.GetCenter()
            name_value = self.parent.mesh3d_coll.get_uid_name(uid)
        elif collection == "dom_coll":
            plot_entity = self.parent.dom_coll.get_uid_vtk_obj(uid)
            point = plot_entity.GetCenter()
            name_value = self.parent.dom_coll.get_uid_name(uid)
        elif collection == "image_coll":
            plot_entity = self.parent.image_coll.get_uid_vtk_obj(uid)
            point = plot_entity.GetCenter()
            name_value = self.parent.image_coll.get_uid_name(uid)
        elif collection == "well_coll":
            plot_entity = self.parent.well_coll.get_uid_vtk_obj(uid)
            point = plot_entity.points[0].reshape(-1, 3)
            name_value = [self.parent.well_coll.get_uid_well_locid(uid)]
        elif collection == "fluid_coll":
            plot_entity = self.parent.fluid_coll.get_uid_vtk_obj(uid)
            point = plot_entity.GetCenter()
            name_value = self.parent.fluid_coll.get_uid_name(uid)
        elif collection == "backgrnd_coll":
            plot_entity = self.parent.backgrnd_coll.get_uid_vtk_obj(uid)
            if self.parent.backgrnd_coll.get_uid_topology(uid) == "PolyLine":
                point = plot_entity.GetCenter()
            else:
                point = plot_entity.points
            name = plot_entity.get_field_data_keys()[0]
            name_value = plot_entity.get_field_data(name)
        if show_property == "none" or show_property is None:
            show_property = None
            self.plotter.remove_actor(f"{uid}_name-labels")
        else:
            self.plotter.add_point_labels(
                point,
                name_value,
                always_visible=True,
                show_points=False,
                font_size=15,
                shape_opacity=0.5,
                name=f"{uid}_name",
            )

    def save_home_view(self):
        self.default_view = self.plotter.camera_position

    def zoom_home_view(self):
        self.plotter.camera_position = self.default_view

    def zoom_active(self):
        self.plotter.reset_camera()

    def initialize_menu_tools(self):
        """This is the intermediate method of the VTKView() abstract class, used to add menu tools used by all VTK windows.
        The code appearing here is appended in subclasses using super().initialize_menu_tools() in their first line.
        """
        # append code from BaseView()
        super().initialize_menu_tools()

        # then add new code specific to VTKView()
        self.saveHomeView = QAction("Save home view", self)
        self.saveHomeView.triggered.connect(self.save_home_view)
        self.menuView.addAction(self.saveHomeView)  # add action to menu

        self.zoomHomeView = QAction("Zoom to home", self)
        self.zoomHomeView.triggered.connect(self.zoom_home_view)
        self.menuView.addAction(self.zoomHomeView)

        self.zoomActive = QAction("Zoom to active", self)
        self.zoomActive.triggered.connect(self.zoom_active)
        self.menuView.addAction(self.zoomActive)

        self.selectLineButton = QAction("Select entity", self)
        self.selectLineButton.triggered.connect(self.select_actor_with_mouse)
        self.menuSelect.addAction(self.selectLineButton)

        self.clearSelectionButton = QAction("Clear Selection", self)
        self.clearSelectionButton.triggered.connect(self.clear_selection)
        self.menuSelect.addAction(self.clearSelectionButton)

        self.removeEntityButton = QAction("Remove Entity", self)
        self.removeEntityButton.triggered.connect(self.remove_entity)
        self.menuModify.addAction(self.removeEntityButton)

        self.vertExagButton = QAction("Vertical exaggeration", self)
        self.vertExagButton.triggered.connect(self.vert_exag)
        self.menuView.addAction(self.vertExagButton)

        self.actionExportScreen = QAction("Take screenshot", self)
        self.actionExportScreen.triggered.connect(self.export_screen)
        self.menuView.addAction(self.actionExportScreen)

    def export_screen(self):
        out_file_name = save_file_dialog(
            parent=self,
            caption="Export 3D view as HTML.",
            filter="png (*.png);; jpeg (*.jpg)",
        )
        self.plotter.screenshot(
            out_file_name, transparent_background=True, window_size=(1920, 1080)
        )

    def initialize_interactor(self):
        """Add the pyvista interactor object to self.ViewFrameLayout ->
        the layout of an empty frame generated with Qt Designer"""
        # print(self.ViewFrame)
        self.plotter = pvQtInteractor(self.ViewFrame)
        # background color - could be made interactive in the future
        self.plotter.set_background("black")
        self.ViewFrameLayout.addWidget(self.plotter.interactor)
        # self.plotter.show_axes_all()

        # Set orientation widget
        # In an old version it was turned on after the qt canvas was shown, but this does not seem necessary
        if isinstance(self, View3D):
            self.plotter.add_camera_orientation_widget()
            # self.cam_orient_widget = vtkCameraOrientationWidget()
            # self.cam_orient_widget.SetParentRenderer(self.plotter.renderer)
            # self.cam_orient_widget.On()
        elif isinstance(self, ViewXsection):
            self.plotter.add_orientation_widget(
                pv_Arrow(direction=(0.0, 1.0, 0.0), scale=0.3),
                interactive=None,
                color="gold",
            )
        elif isinstance(self, ViewMap):
            self.plotter.add_north_arrow_widget(interactive=None, color="gold")

        # Set default orientation horizontal because vertical colorbars interfere with the camera widget.
        pv_global_theme.colorbar_orientation = "horizontal"

        # Manage home view
        self.default_view = self.plotter.camera_position
        # self.plotter.track_click_position(
        #    lambda pos: self.plotter.camera.SetFocalPoint(pos), side="left", double=True
        # )

    def show_qt_canvas(self):
        """Show the Qt Window"""
        self.show()
        if isinstance(self, View3D):
            # ________________________
            # CHECK THIS ZOOM SETTING
            # ________________________
            self.init_zoom = self.plotter.camera.distance

            # self.picker = self.plotter.enable_mesh_picking(callback= self.pkd_mesh,show_message=False)

    def plot_mesh(
        self,
        uid=None,
        plot_entity=None,
        color_RGB=None,
        show_property=None,
        color_bar_range=None,
        show_property_title=None,
        line_thick=None,
        plot_texture_option=None,
        plot_rgb_option=None,
        visible=None,
        style="surface",
        point_size=None,
        points_as_spheres=False,
        render_lines_as_tubes=False,
        pickable=True,
        opacity=1.0,
        smooth_shading=False,
    ):
        """Plot mesh in PyVista interactive plotter."""
        if not self.actors_df.empty:
            # This stores the camera position before redrawing the actor. Added to avoid a bug that sometimes sends
            # the scene to a very distant place or to the origin that is the default position before any mesh is plotted.
            camera_position = self.plotter.camera_position
        if show_property_title is not None and show_property_title != "none":
            show_property_cmap = self.parent.prop_legend_df.loc[
                self.parent.prop_legend_df["property_name"] == show_property_title,
                "colormap",
            ].values[0]
        else:
            show_property_cmap = None
        this_actor = self.plotter.add_mesh(
            plot_entity,
            color=color_RGB,  # string, RGB list, or hex string, overridden if scalars are specified
            style=style,  # 'surface' (default), 'wireframe', or 'points'
            scalars=show_property,  # str pointing to vtk property or numpy.ndarray
            clim=color_bar_range,  # color bar range for scalars, e.g. [-1, 2]
            show_edges=None,  # bool
            edge_color=None,  # default black
            point_size=point_size,  # was 5.0
            line_width=line_thick,
            opacity=opacity,  # single value > uniform opacity, but string can be specified to map the scalars range to opacity.
            flip_scalars=False,  # flip direction of cmap
            lighting=None,  # bool to enable view-direction lighting
            n_colors=256,  # number of colors to use when displaying scalars
            interpolate_before_map=True,  # bool for smoother scalars display (default True)
            cmap=show_property_cmap,  # name of the Matplotlib colormap, includes 'colorcet' and 'cmocean', and custom colormaps like ['green', 'red', 'blue']
            label=None,  # string label for legend with pyvista.BasePlotter.add_legend
            reset_camera=None,
            scalar_bar_args=None,  # keyword arguments for scalar bar, see pyvista.BasePlotter.add_scalar_bar
            show_scalar_bar=False,  # bool (default True)
            multi_colors=False,  # for MultiBlock datasets
            name=uid,  # actor name
            texture=plot_texture_option,  # vtk.vtkTexture or np_ndarray or boolean, will work if input mesh has texture coordinates. True > first available texture. String > texture with that name already associated to mesh.
            render_points_as_spheres=points_as_spheres,
            render_lines_as_tubes=render_lines_as_tubes,
            smooth_shading=smooth_shading,
            ambient=0.0,
            diffuse=1.0,
            specular=0.0,
            specular_power=100.0,
            nan_color=None,  # color to use for all nan values
            nan_opacity=1.0,  # opacity to use for all nan values
            culling=None,  # 'front', 'back', 'false' (default) > does not render faces that are culled
            rgb=plot_rgb_option,  # True > plot array values as RGB(A) colors
            categories=False,  # True > number of unique values in the scalar used as 'n_colors' argument
            use_transparency=False,  # invert the opacity mapping as transparency mapping
            below_color=None,  # solid color for values below the scalars range in 'clim'
            above_color=None,  # solid color for values above the scalars range in 'clim'
            annotations=None,  # dictionary of annotations for scale bar witor 'points'h keys = float values and values = string annotations
            pickable=pickable,  # bool
            preference="point",
            log_scale=False,
        )
        if not visible:
            this_actor.SetVisibility(False)
        if not self.actors_df.empty:
            # See above.
            self.plotter.camera_position = camera_position
        return this_actor

    def actor_in_table(self, sel_uid=None):
        """Method used to highlight in the main project table view a list of selected actors."""
        if sel_uid:
            # To select the mesh in the entity list we compare the actors of the actors_df dataframe
            # with the picker.GetActor() result
            collection = self.actors_df.loc[
                self.actors_df["uid"] == sel_uid[0], "collection"
            ].values[0]
            if collection == "geol_coll":
                table = self.parent.GeologyTableView
                df = self.parent.geol_coll.df
                # set the correct tab to avoid problems
                self.parent.tabWidgetTopLeft.setCurrentIndex(0)
            elif collection == "dom_coll":
                table = self.parent.DOMsTableView
                df = self.parent.dom_coll.df
                # set the correct tab to avoid problems
                self.parent.tabWidgetTopLeft.setCurrentIndex(4)
            else:
                print(
                    "Selection not supported for entities that do not belong to geological or DOM collection."
                )
                return
            table.clearSelection()
            if len(sel_uid) > 1:
                table.setSelectionMode(QAbstractItemView.MultiSelection)

            # In general this approach is not the best.
            # In the actors_df the index of the df is indipendent from the index of the table views.
            # We could have 6 entities 5 of which are in the geology tab and 1 in the image tab.
            # When selecting the image the actors_df index could be anything from 0 to 5 (depends on the add_all_entities order)
            # but in the table view is 0 thus returning nothing.
            # To resolve this we could:
            #   1. Create a actor_df for each collection
            #   2. Have a general actors_df with a table_index value (that needs to be updated when adding or removing objects)
            #   3. Have a selected_entities_df indipendent from the tables or views that collects the selected actors (both in the table or in the view)

            # For now selection will work only for geology objects

            for uid in sel_uid:
                uid_list = [
                    table.model().index(row, 0).data() for row in range(len(df.index))
                ]
                idx = uid_list.index(uid)
                # coll = self.actors_df.loc[self.actors_df['uid'] == uid, 'collection'].values[0]

                # if coll == 'geol_coll':
                table.selectRow(idx)

                # elif coll == 'image_coll':
                #     self.parent.ImagesTableView.selectRow(idx)
                # return
        else:
            self.parent.GeologyTableView.clearSelection()
            self.parent.DOMsTableView.clearSelection()
            self.selected_uids = []

    def select_actor_with_mouse(self):
        """Function used to initiate actor selection"""
        self.disable_actions()
        self.plotter.iren.interactor.AddObserver(
            "LeftButtonPressEvent", self.select_actor
        )
        # self.plotter.iren.interactor.AddObserver('KeyPressEvent',self.clear_selected)
        self.plotter.track_click_position(self.end_pick)
        self.plotter.add_key_event("c", self.clear_selection)

    def end_pick(self, pos):
        """Function used to disable actor picking"""

        self.plotter.iren.interactor.RemoveObservers(
            "LeftButtonPressEvent"
        )  # Remove the selector observer
        self.plotter.untrack_click_position(
            side="right"
        )  # Remove the right click observer
        self.plotter.untrack_click_position(
            side="left"
        )  # Remove the left click observer
        # self.plotter.track_click_position(
        #    lambda pos: self.plotter.camera.SetFocalPoint(pos), side="left", double=True
        # )
        if isinstance(self, View3D):
            self.plotter.enable_trackball_style()
        elif isinstance(self, View2D):
            self.plotter.enable_image_style()

        self.plotter.reset_key_events()
        self.selected_uids = self.parent.selected_uids
        self.enable_actions()

    def clear_selection(self):
        for av_actor in self.plotter.renderer.actors.copy():
            self.plotter.remove_bounding_box()
            if "_silh" in av_actor:
                self.plotter.remove_actor(av_actor)

        if not self.selected_uids == []:
            deselected_uids = self.selected_uids
            self.selected_uids = []
        self.actor_in_table()

    def select_actor(self, obj, event):
        """Select actor with VTK picking."""
        # initialize selction sets
        name_list = set()
        actors = set(self.plotter.renderer.actors)

        # initialize render interaction
        style = obj.GetInteractorStyle()
        style.SetDefaultRenderer(self.plotter.renderer)
        pos = obj.GetEventPosition()
        shift = obj.GetShiftKey()

        # create picker
        # Note that https://discourse.vtk.org/t/get-picked-vtk-actor/3474 says vtkPropPicker() is problematic
        # picker = vtkPropPicker()
        # picker_output = picker.PickProp(pos[0], pos[1], style.GetDefaultRenderer())
        # on the other hand vtkCellPicker() allows setting the tolerance for picking
        picker = vtkCellPicker()
        picker.SetTolerance(0.01)
        picker_output = picker.Pick(pos[0], pos[1], 0, style.GetDefaultRenderer())
        actor = picker.GetActor()

        # show messages in terminal
        self.print_terminal(f"Picker tolerance: {picker.GetTolerance()}")
        self.print_terminal(f"Picker output: {picker_output}")
        # self.print_terminal(f"Picker actor: {actor}")

        # proceed if an actor is selected
        if not self.actors_df.loc[self.actors_df["actor"] == actor, "uid"].empty:
            # if picker_output:
            # Get uid of picked actor
            sel_uid = self.actors_df.loc[
                self.actors_df["actor"] == actor, "uid"
            ].values[0]
            self.print_terminal(f"Picked uid: {sel_uid}")

            # Add uid of picked actor to selected_uids list, with SHIFT-SELECT option
            if shift:
                self.selected_uids.append(sel_uid)
            else:
                self.selected_uids = [sel_uid]
            self.print_terminal(f"Selected uids: {self.selected_uids}")

            # Show selected actors in yellow
            for sel_uid in self.selected_uids:
                sel_actor = self.actors_df.loc[
                    self.actors_df["uid"] == sel_uid, "actor"
                ].values[0]
                collection = self.actors_df.loc[
                    self.actors_df["uid"] == sel_uid, "collection"
                ].values[0]
                mesh = sel_actor.GetMapper().GetInput()
                name = f"{sel_uid}_silh"
                name_list.add(name)
                if collection == "dom_coll":
                    bounds = sel_actor.GetBounds()
                    mesh = pv_Box(bounds)

                self.plotter.add_mesh(
                    mesh,
                    pickable=False,
                    name=name,
                    color="Yellow",
                    style="wireframe",
                    line_width=5,
                )

                for av_actor in actors.difference(name_list):
                    if "_silh" in av_actor:
                        self.plotter.remove_actor(av_actor)

            self.actor_in_table(self.selected_uids)

        else:
            return None

    def remove_entity(self):
        """This method first removes the yellow silhouette that highlights selected actors (actually an actor itself),
        then call the general method to remove entities from the project, which in turn fires a signal to update all
        plot windows removing all actors."""
        for sel_uid in self.selected_uids:
            self.plotter.remove_actor(f"{sel_uid}_silh")
        self.parent.entity_remove()

    def vert_exag(self):
        exag_value = input_one_value_dialog(
            parent=self,
            title="Vertical exaggeration options",
            label="Set vertical exaggeration",
            default_value=1.0,
        )

        self.plotter.set_scale(zscale=exag_value)


class MPLView(BaseView):
    """Abstract class used as a base for all classes using the Matplotlib plotting canvas."""

    def __init__(self, *args, **kwargs):
        super(MPLView, self).__init__(*args, **kwargs)


class View3D(VTKView):
    """Create 3D view and import UI created with Qt Designer by subclassing base view.
    Parent is the QT object that is launching this one, hence the ProjectWindow() instance in this case.
    """

    def __init__(self, *args, **kwargs):
        super(View3D, self).__init__(*args, **kwargs)

        self.plotter.enable_trackball_style()
        self.plotter.disable_parallel_projection()
        """Rename Base View, Menu and Tool"""
        self.setWindowTitle("3D View")
        self.tog_att = -1  # Attitude picker disabled
        self.trace_method = (
            "trace"  # visualization method for boreholes properties (trace or cylinder)
        )
        self.toggle_bore_geo = -1
        self.toggle_bore_litho = -1

        self.trigger_event = "LeftButtonPressEvent"

    def initialize_menu_tools(self):
        """Customize menus and tools for this view"""
        from .point_clouds import (
            cut_pc,
            segment_pc,
            facets_pc,
            auto_pick,
            thresh_filt,
            normals2dd,
            calibration_pc,
        )

        super().initialize_menu_tools()

        self.menuBoreTraceVis = QMenu("Borehole visualization methods", self)

        self.actionBoreTrace = QAction("Trace", self)
        self.actionBoreTrace.triggered.connect(lambda: self.change_bore_vis("trace"))

        self.actionBoreCylinder = QAction("Cylinder", self)
        self.actionBoreCylinder.triggered.connect(
            lambda: self.change_bore_vis("cylinder")
        )

        self.actionToggleGeology = QAction("Toggle geology", self)
        self.actionToggleGeology.triggered.connect(lambda: self.change_bore_vis("geo"))

        self.actionToggleLithology = QAction("Toggle lithology", self)
        self.actionToggleLithology.triggered.connect(
            lambda: self.change_bore_vis("litho")
        )

        self.menuBoreTraceVis.addAction(self.actionBoreTrace)
        self.menuBoreTraceVis.addAction(self.actionBoreCylinder)
        self.menuBoreTraceVis.addAction(self.actionToggleLithology)
        self.menuBoreTraceVis.addAction(self.actionToggleGeology)

        self.menuView.addMenu(self.menuBoreTraceVis)

        # self.actionThresholdf.triggered.connect(lambda: thresh_filt(self))
        # self.actionSurface_densityf.triggered.connect(lambda: self.surf_den_filt())
        # self.actionRoughnessf.triggered.connect(lambda: self.rough_filt())
        # self.actionCurvaturef.triggered.connect(lambda: self.curv_filt())
        # self.actionNormalsf.triggered.connect(lambda: self.norm_filt())
        # self.actionManualBoth.triggered.connect(lambda: cut_pc(self))
        # self.actionManualInner.triggered.connect(lambda: cut_pc(self, "inner"))
        # self.actionManualOuter.triggered.connect(lambda: cut_pc(self, "outer"))
        #
        # self.actionCalibration.triggered.connect(lambda: calibration_pc(self))
        # self.actionManual_picking.triggered.connect(lambda: self.act_att())
        # self.actionSegment.triggered.connect(lambda: segment_pc(self))
        # self.actionPick.triggered.connect(lambda: auto_pick(self))
        # self.actionFacets.triggered.connect(lambda: facets_pc(self))
        #
        # # self.actionCalculate_normals.triggered.connect(lambda: self.normalGeometry())
        # self.actionNormals_to_DDR.triggered.connect(lambda: normals2dd(self))

        # self.showOct = QAction("Show octree structure", self)
        # self.showOct.triggered.connect(self.show_octree)
        # self.menuBaseView.addAction(self.showOct)
        # self.toolBarBase.addAction(self.showOct)

        self.actionExportGltf = QAction("Export as GLTF", self)
        self.actionExportGltf.triggered.connect(self.export_gltf)
        self.menuView.addAction(self.actionExportGltf)

        self.actionExportHtml = QAction("Export as HTML", self)
        self.actionExportHtml.triggered.connect(self.export_html)
        self.menuView.addAction(self.actionExportHtml)

        self.actionExportObj = QAction("Export as OBJ", self)
        self.actionExportObj.triggered.connect(self.export_obj)
        self.menuView.addAction(self.actionExportObj)

        self.actionExportVtkjs = QAction("Export as VTKjs", self)
        self.actionExportVtkjs.triggered.connect(self.export_vtkjs)
        self.menuView.addAction(self.actionExportVtkjs)

        # self.menuOrbit = QMenu("Orbit around", self)
        # self.actionOrbitEntity = QAction("Entity", self)
        # self.actionOrbitEntity.triggered.connect(lambda: self.orbit_entity())
        # self.menuOrbit.addAction(self.actionOrbitEntity)
        # self.menuWindow.addMenu(self.menuOrbit)

    def export_html(self):
        out_file_name = save_file_dialog(
            parent=self, caption="Export 3D view as HTML.", filter="html (*.html)"
        )
        self.plotter.export_html(out_file_name)

    def export_vtkjs(self):
        out_file_name = save_file_dialog(
            parent=self, caption="Export 3D view as VTKjs.", filter="vtkjs (*.vtkjs)"
        ).removesuffix(".vtkjs")
        self.plotter.export_vtkjs(out_file_name)

    def export_obj(self):
        out_file_name = save_file_dialog(
            parent=self, caption="Export 3D view as OBJ.", filter="obj (*.obj)"
        ).removesuffix(".obj")
        self.plotter.export_obj(out_file_name)

    def export_gltf(self):
        out_file_name = save_file_dialog(
            parent=self, caption="Export 3D view as GLTF.", filter="gltf (*.gltf)"
        )
        self.plotter.export_gltf(out_file_name)

    def act_att(self):
        """Used to activate pkd_point, which returns data from picking on point clouds."""
        if self.tog_att == -1:
            input_dict = {
                "name": ["Set name: ", "Set_0"],
                "role": [
                    "Role: ",
                    self.parent.geol_coll.valid_roles,
                ],
            }
            set_opt = multiple_input_dialog(
                title="Create measure set", input_dict=input_dict
            )
            self.plotter.enable_point_picking(
                callback=lambda mesh, pid: self.pkd_point(mesh, pid, set_opt),
                show_message=False,
                color="yellow",
                use_mesh=True,
            )
            self.tog_att *= -1
            print("Picking enabled")
        else:
            self.plotter.disable_picking()
            self.tog_att *= -1
            print("Picking disabled")

    def pkd_point(self, mesh, pid, set_opt):
        """Used by  pkd_point, which returns data from picking on point clouds."""
        obj = mesh

        sph_r = 0.2  # radius of the selection sphere
        center = mesh.points[pid]

        sphere = vtkSphere()
        sphere.SetCenter(center)
        sphere.SetRadius(sph_r)

        extr = vtkExtractPoints()

        extr.SetImplicitFunction(sphere)
        extr.SetInputData(obj)
        extr.ExtractInsideOn()
        extr.Update()
        # [Gabriele] We could try to do this with vtkPCANormalEstimation
        points = numpy_support.vtk_to_numpy(extr.GetOutput().GetPoints().GetData())
        plane_c, plane_n = best_fitting_plane(points)

        if plane_n[2] > 0:  # If Z is positive flip the normals
            plane_n *= -1

        if set_opt["name"] in self.parent.geol_coll.df["name"].values:
            uid = self.parent.geol_coll.get_name_uid(set_opt["name"])
            old_vtk_obj = self.parent.geol_coll.get_uid_vtk_obj(uid)

            old_vtk_obj.append_point(point_vector=plane_c)
            old_plane_n = old_vtk_obj.get_point_data("Normals")
            old_plane_n = np_append(old_plane_n, plane_n).reshape(-1, 3)
            old_vtk_obj.set_point_data("Normals", old_plane_n)
            old_vtk_obj.auto_cells()
            self.parent.geol_coll.replace_vtk(uid, old_vtk_obj)
        else:
            att_point = Attitude()

            att_point.append_point(point_vector=plane_c)
            att_point.auto_cells()

            att_point.init_point_data(data_key="Normals", dimension=3)

            att_point.set_point_data(data_key="Normals", attribute_matrix=plane_n)

            properties_name = att_point.point_data_keys
            properties_components = [
                att_point.get_point_data_shape(i)[1] for i in properties_name
            ]

            curr_obj_dict = deepcopy(GeologicalCollection.entity_dict)
            curr_obj_dict["uid"] = str(uuid4())
            curr_obj_dict["name"] = set_opt["name"]
            curr_obj_dict["role"] = set_opt["role"]
            curr_obj_dict["topology"] = "VertexSet"
            curr_obj_dict["feature"] = set_opt["name"]
            curr_obj_dict["properties_names"] = properties_name
            curr_obj_dict["properties_components"] = properties_components
            curr_obj_dict["vtk_obj"] = att_point
            # Add to entity collection.
            self.parent.geol_coll.add_entity_from_dict(entity_dict=curr_obj_dict)

            del extr
            del sphere

    def plot_volume_3D(self, uid=None, plot_entity=None):
        if not self.actors_df.empty:
            """This stores the camera position before redrawing the actor.
            Added to avoid a bug that sometimes sends the scene to a very distant place.
            Could be used as a basis to implement saved views widgets, synced 3D views, etc.
            The is is needed to avoid sending the camera to the origin that is the
            default position before any mesh is plotted."""
            camera_position = self.plotter.camera_position
        this_actor = self.plotter.add_volume(plot_entity, name=uid)
        if not self.actors_df.empty:
            # See above.
            self.plotter.camera_position = camera_position
        return this_actor

    # Implementation of functions specific to this view (e.g. particular editing or visualization functions)
    # NONE AT THE MOMENT

    def plot_PC_3D(
        self,
        uid=None,
        plot_entity=None,
        visible=None,
        color_RGB=None,
        show_property=None,
        color_bar_range=None,
        show_property_title=None,
        plot_rgb_option=None,
        point_size=1.0,
        points_as_spheres=True,
        opacity=1.0,
    ):
        # Plot the point cloud
        if not self.actors_df.empty:
            """This stores the camera position before redrawing the actor.
            Added to avoid a bug that sometimes sends the scene to a very distant place.
            Could be used as a basis to implement saved views widgets, synced 3D views, etc.
            The is is needed to avoid sending the camera to the origin that is the
            default position before any mesh is plotted."""
            camera_position = self.plotter.camera_position
        if show_property is not None and plot_rgb_option is None:
            show_property_cmap = self.parent.prop_legend_df.loc[
                self.parent.prop_legend_df["property_name"] == show_property_title,
                "colormap",
            ].values[0]
        else:
            show_property_cmap = None
        this_actor = self.plotter.add_points(
            plot_entity,
            name=uid,
            style="points",
            point_size=point_size,
            render_points_as_spheres=points_as_spheres,
            color=color_RGB,
            scalars=show_property,
            n_colors=256,
            clim=color_bar_range,
            flip_scalars=False,
            interpolate_before_map=True,
            cmap=show_property_cmap,
            scalar_bar_args=None,
            rgb=plot_rgb_option,
            show_scalar_bar=False,
            opacity=opacity,
        )
        # self.n_points = plot_entity.GetNumberOfPoints()
        if not visible:
            this_actor.SetVisibility(False)
        if not self.actors_df.empty:
            # See above.
            self.plotter.camera_position = camera_position
        return this_actor

    def show_octree(self):
        vis_uids = self.actors_df.loc[self.actors_df["show"] == True, "uid"]
        for uid in vis_uids:
            vtk_obj = self.parent.dom_coll.get_uid_vtk_obj(uid)
            octree = PolyData()  # [Gabriele] possible recursion problem
            # print(vtk_obj.locator)
            vtk_obj.locator.GenerateRepresentation(3, octree)

            self.plotter.add_mesh(octree, style="wireframe", color="red")

    def change_bore_vis(self, method):
        actors = set(self.plotter.renderer.actors.copy())
        wells = set(self.parent.well_coll.get_uids)

        well_actors = actors.intersection(wells)
        if method == "trace":
            self.trace_method = method
        elif method == "cylinder":
            self.trace_method = method
        elif method == "geo":
            for uid in well_actors:
                if "_geo" in uid:
                    pass
                else:
                    plot_entity = self.parent.well_coll.get_uid_vtk_obj(uid)
                    if self.toggle_bore_geo == 1:
                        self.plotter.remove_actor(f"{uid}_geo")
                    elif self.toggle_bore_geo == -1:
                        self.plotter.remove_actor(f"{uid}_litho")
                        geo = plot_entity.plot_tube("GEOLOGY")
                        if geo != None:
                            self.plotter.add_mesh(geo, name=f"{uid}_geo", rgb=True)

            self.toggle_bore_geo *= -1
        elif method == "litho":
            for uid in well_actors:
                if "_litho" in uid:
                    pass
                else:
                    plot_entity = self.parent.well_coll.get_uid_vtk_obj(uid)
                    if self.toggle_bore_litho == 1:
                        self.plotter.remove_actor(f"{uid}_litho")
                    elif self.toggle_bore_litho == -1:
                        self.plotter.remove_actor(f"{uid}_geo")
                        litho = plot_entity.plot_tube("LITHOLOGY")
                        if litho != None:
                            self.plotter.add_mesh(litho, name=f"{uid}_litho", rgb=True)

            self.toggle_bore_litho *= -1

    # Orbit object ----------------------------------------------------

    def orbit_entity(self):
        uid_list = list(self.actors_df["uid"].values)

        in_dict = {
            "uid": ["Actor uid", uid_list],
            "up_x": ["Orbital plane (Nx)", 0.0],
            "up_y": ["Orbital plane (Ny)", 0.0],
            "up_z": ["Orbital plane (Nz)", 1.0],
            "fac": ["Zoom factor", 1.0],
            "ele": ["Elevation above surface", 0],
            "fps": ["Fps", 60],
            "length": ["Movie length [sec]:", 60],
            "name": ["gif name", "test"],
        }

        opt_dict = multiple_input_dialog(
            title="Orbiting options", input_dict=in_dict, return_widget=False
        )

        uid = opt_dict["uid"]
        entity = self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[0]

        focus = entity.GetCenter()
        view_up = [
            float(opt_dict["up_x"]),
            float(opt_dict["up_y"]),
            float(opt_dict["up_z"]),
        ]
        factor = float(opt_dict["fac"])

        # time = int(opt_dict['length']/60)

        # print(factor)

        off_screen_plot = pv_plot(off_screen=True)
        # off_screen_plot.set_background('Green')

        visible_actors = self.actors_df.loc[
            self.actors_df["show"] == True, "actor"
        ].values
        for actor in visible_actors:
            off_screen_plot.add_actor(actor)

        # off_screen_plot.show(auto_close=False)
        n_points = int(opt_dict["fps"] * opt_dict["length"])
        path = off_screen_plot.generate_orbital_path(
            n_points=n_points,
            factor=factor,
            viewup=view_up,
            shift=float(opt_dict["ele"]),
        )

        # off_screen_plot.store_image = True
        # off_screen_plot.open_gif(f'{opt_dict["name"]}.gif')

        points = path.points
        off_screen_plot.set_focus(focus)
        off_screen_plot.set_viewup(view_up)
        images = []
        prgs = progress_dialog(
            max_value=n_points,
            title_txt="Writing gif",
            label_txt="Saving frames",
            parent=self,
        )
        # print('Creating gif')
        for point in range(n_points):
            # print(f'{point}/{n_points}',end='\r')
            off_screen_plot.set_position(points[point])

            # off_screen_plot.write_frame()
            img = off_screen_plot.screenshot(transparent_background=True)
            images.append(gen_frame(img))
            prgs.add_one()
        duration = 1000 / opt_dict["fps"]
        images[0].save(
            f'{opt_dict["name"]}.gif',
            save_all=True,
            append_images=images,
            loop=0,
            duration=duration,
            disposal=2,
        )
        # off_screen_plot.orbit_on_path(path=path,focus=focus, write_frames=True,progress_bar=True,threaded=False)
        # off_screen_plot.close()


class View2D(VTKView):
    """Create 2D view using vtk/pyvista. This should be more efficient than matplotlib"""

    def __init__(self, *args, **kwargs):
        super(View2D, self).__init__(*args, **kwargs)

        self.line_dict = None
        self.plotter.enable_image_style()
        self.plotter.enable_parallel_projection()

    # Re-implementations of functions that appear in all views - see placeholders in BaseView()

    def initialize_menu_tools(self):
        from .two_d_lines import (
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


class ViewMap(View2D):
    def __init__(self, *args, **kwargs):
        super(ViewMap, self).__init__(*args, **kwargs)
        self.setWindowTitle("Map View")
        self.plotter.view_xy()

    def initialize_menu_tools(self):
        from pzero.collections.xsection_collection import section_from_azimuth
        from pzero.collections.boundary_collection import boundary_from_points

        # Imports for this view.
        # Customize menus and tools for this view
        super().initialize_menu_tools()
        self.sectionFromAzimuthButton = QAction("Section from azimuth", self)
        self.sectionFromAzimuthButton.triggered.connect(
            lambda: self.vector_by_mouse(section_from_azimuth)
        )
        self.menuCreate.addAction(self.sectionFromAzimuthButton)

        self.boundaryFromPointsButton = QAction("Boundary from 2 points", self)
        self.boundaryFromPointsButton.triggered.connect(
            lambda: self.vector_by_mouse(boundary_from_points)
        )
        self.menuCreate.addAction(self.boundaryFromPointsButton)

    def show_actor_with_property(
        self, uid=None, collection=None, show_property=None, visible=None
    ):
        """Show actor with scalar property (default None)
        https://github.com/pyvista/pyvista/blob/140b15be1d4021b81ded46b1c212c70e86a98ee7/pyvista/plotting/plotting.py#L1045
        """
        # First get the vtk object from its collection.
        show_property_title = show_property
        this_coll = eval("self.parent." + collection)
        if collection in ["geol_coll", "fluid_coll", "backgrnd_coll", "well_coll"]:
            color_R = this_coll.get_uid_legend(uid=uid)["color_R"]
            color_G = this_coll.get_uid_legend(uid=uid)["color_G"]
            color_B = this_coll.get_uid_legend(uid=uid)["color_B"]
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            line_thick = this_coll.get_uid_legend(uid=uid)["line_thick"]
            point_size = this_coll.get_uid_legend(uid=uid)["point_size"]
            opacity = this_coll.get_uid_legend(uid=uid)["opacity"] / 100
            plot_entity = this_coll.get_uid_vtk_obj(uid)
        elif collection in [
            "xsect_coll",
            "boundary_coll",
            "mesh3d_coll",
            "dom_coll",
            "image_coll",
        ]:
            color_R = this_coll.get_legend()["color_R"]
            color_G = this_coll.get_legend()["color_G"]
            color_B = this_coll.get_legend()["color_B"]
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            line_thick = this_coll.get_legend()["line_thick"]
            point_size = this_coll.get_legend()["point_size"]
            opacity = this_coll.get_legend()["opacity"] / 100
            plot_entity = this_coll.get_uid_vtk_obj(uid)
        else:
            # catch errors
            print("no collection", collection)
            this_actor = None
        # Then plot the vtk object with proper options.
        if isinstance(plot_entity, (PolyLine, TriSurf, XsPolyLine)) and not isinstance(
            plot_entity, WellTrace
        ):
            plot_rgb_option = None
            if isinstance(plot_entity.points, np_ndarray):
                # This  check is needed to avoid errors when trying to plot an empty
                # PolyData, just created at the beginning of a digitizing session.
                if show_property == "none" or show_property is None:
                    show_property = None
                elif show_property == "X":
                    show_property = plot_entity.points_X
                elif show_property == "Y":
                    show_property = plot_entity.points_Y
                elif show_property == "Z":
                    show_property = plot_entity.points_Z
                else:
                    if plot_entity.get_point_data_shape(show_property)[-1] == 3:
                        plot_rgb_option = True
                this_actor = self.plot_mesh(
                    uid=uid,
                    plot_entity=plot_entity,
                    color_RGB=color_RGB,
                    show_property=show_property,
                    color_bar_range=None,
                    show_property_title=show_property_title,
                    line_thick=line_thick,
                    plot_texture_option=False,
                    plot_rgb_option=plot_rgb_option,
                    visible=visible,
                )
            else:
                this_actor = None
        elif isinstance(plot_entity, (VertexSet, XsVertexSet, WellMarker, Attitude)):
            if isinstance(plot_entity, Attitude):
                pickable = False
            else:
                pickable = True
            style = "points"
            plot_rgb_option = None
            texture = False
            smooth_shading = False
            if isinstance(plot_entity.points, np_ndarray):
                # This  check is needed to avoid errors when trying to plot an empty
                # PolyData, just created at the beginning of a digitizing session.
                if show_property == "none" or show_property is None:
                    show_property = None
                elif show_property == "X":
                    show_property = plot_entity.points_X
                elif show_property == "Y":
                    show_property = plot_entity.points_Y
                elif show_property == "Z":
                    show_property = plot_entity.points_Z
                elif show_property == "Normals":
                    show_property_title = None
                    show_property = None
                    style = "surface"
                    smooth_shading = True
                    appender = vtkAppendPolyData()
                    r = self.parent.geol_coll.get_uid_legend(uid=uid)["point_size"] * 4
                    normals = plot_entity.get_point_data("Normals")
                    az_vectors, dir_vectors = get_dip_dir_vectors(
                        normals=normals, az=True
                    )
                    line1 = pv_Line(pointa=(0, 0, 0), pointb=(r, 0, 0))
                    line2 = pv_Line(pointa=(-r, 0, 0), pointb=(r, 0, 0))

                    az_glyph = plot_entity.glyph(geometry=line1, prop=az_vectors)
                    dir_glyph = plot_entity.glyph(geometry=line2, prop=dir_vectors)

                    appender.AddInputData(az_glyph)
                    appender.AddInputData(dir_glyph)
                    appender.Update()
                    plot_entity = appender.GetOutput()

                elif show_property == "name":
                    point = plot_entity.points
                    name_value = plot_entity.get_field_data("name")
                    self.plotter.add_point_labels(
                        point,
                        name_value,
                        always_visible=True,
                        show_points=False,
                        font_size=15,
                        shape_opacity=0.5,
                        name=f"{uid}_name",
                    )
                    show_property = None
                    show_property_title = None

                else:
                    if plot_entity.get_point_data_shape(show_property)[-1] == 3:
                        plot_rgb_option = True
                this_actor = self.plot_mesh(
                    uid=uid,
                    plot_entity=plot_entity,
                    color_RGB=color_RGB,
                    show_property=show_property,
                    color_bar_range=None,
                    show_property_title=show_property_title,
                    line_thick=line_thick,
                    plot_texture_option=texture,
                    plot_rgb_option=plot_rgb_option,
                    visible=visible,
                    style=style,
                    point_size=point_size,
                    points_as_spheres=True,
                    pickable=pickable,
                )
            else:
                this_actor = None
        elif isinstance(plot_entity, DEM):
            # Show texture specified in show_property
            if (
                show_property
                in self.parent.dom_coll.df.loc[
                    self.parent.dom_coll.df["uid"] == uid, "texture_uids"
                ].values[0]
            ):
                active_image = self.parent.image_coll.get_uid_vtk_obj(show_property)
                active_image_texture = active_image.texture
                # active_image_properties_components = active_image.properties_components[0]  # IF USED THIS MUST BE FIXED FOR TEXTURES WITH MORE THAN 3 COMPONENTS
                this_actor = self.plot_mesh(
                    uid=uid,
                    plot_entity=plot_entity,
                    color_RGB=None,
                    show_property=None,
                    color_bar_range=None,
                    show_property_title=None,
                    line_thick=None,
                    plot_texture_option=active_image_texture,
                    plot_rgb_option=False,
                    visible=visible,
                )
            else:
                plot_rgb_option = None
                if show_property == "none" or show_property is None:
                    show_property = None
                elif show_property == "X":
                    show_property = plot_entity.points_X
                elif show_property == "Y":
                    show_property = plot_entity.points_Y
                elif show_property == "Z":
                    show_property = plot_entity.points_Z
                elif show_property == "RGB":
                    show_property = None
                else:
                    if plot_entity.get_point_data_shape(show_property)[-1] == 3:
                        plot_rgb_option = True
                this_actor = self.plot_mesh(
                    uid=uid,
                    plot_entity=plot_entity,
                    color_RGB=color_RGB,
                    show_property=show_property,
                    color_bar_range=None,
                    show_property_title=show_property_title,
                    line_thick=line_thick,
                    plot_texture_option=False,
                    plot_rgb_option=plot_rgb_option,
                    visible=visible,
                )
        elif isinstance(plot_entity, PCDom):
            plot_rgb_option = None
            new_plot = pvPointSet()
            new_plot.ShallowCopy(plot_entity)  # this is temporary
            file = self.parent.dom_coll.df.loc[
                self.parent.dom_coll.df["uid"] == uid, "name"
            ].values[0]
            if isinstance(plot_entity.points, np_ndarray):
                # This check is needed to avoid errors when trying to plot an empty
                # PolyData, just created at the beginning of a digitizing session.
                if show_property == "none" or show_property is None:
                    show_property_value = None
                elif show_property == "X":
                    show_property_value = plot_entity.points_X
                elif show_property == "Y":
                    show_property_value = plot_entity.points_Y
                elif show_property == "Z":
                    show_property_value = plot_entity.points_Z
                elif show_property[-1] == "]":
                    # [Gabriele] we can identify multicomponent properties such as RGB[0] or Normals[0] by
                    # taking the last character of the property name ("]").
                    # [Gabriele] Get the start and end index of the [n_component]
                    pos1 = show_property.index("[")
                    pos2 = show_property.index("]")
                    # [Gabriele] Get the original property (e.g. RGB[0] -> RGB)
                    original_prop = show_property[:pos1]
                    # [Gabriele] Get the column index (the n_component value)
                    index = int(show_property[pos1 + 1 : pos2])
                    show_property_value = plot_entity.get_point_data(original_prop)[
                        :, index
                    ]
                else:
                    n_comp = self.parent.dom_coll.get_uid_properties_components(uid)[
                        self.parent.dom_coll.get_uid_properties_names(uid).index(
                            show_property
                        )
                    ]
                    # Get the n of components for the given property. If it's > 1 then do stuff depending on the type of property (e.g. show_rgb_option -> True if the property is RGB)
                    if n_comp > 1:
                        show_property_value = plot_entity.get_point_data(show_property)
                        plot_rgb_option = True
                    else:
                        show_property_value = plot_entity.get_point_data(show_property)
            this_actor = self.plot_PC_3D(
                uid=uid,
                plot_entity=new_plot,
                color_RGB=color_RGB,
                show_property=show_property_value,
                color_bar_range=None,
                show_property_title=show_property_title,
                plot_rgb_option=plot_rgb_option,
                visible=visible,
                point_size=line_thick,
                opacity=opacity,
            )

        elif isinstance(plot_entity, (MapImage, XsImage)):
            # Do not plot directly image - it is much slower.
            # Texture options according to type.
            if show_property == "none" or show_property is None:
                plot_texture_option = None
            else:
                plot_texture_option = plot_entity.texture
            this_actor = self.plot_mesh(
                uid=uid,
                plot_entity=plot_entity.frame,
                color_RGB=None,
                show_property=None,
                color_bar_range=None,
                show_property_title=None,
                line_thick=line_thick,
                plot_texture_option=plot_texture_option,
                plot_rgb_option=False,
                visible=visible,
                opacity=opacity,
            )
        elif isinstance(plot_entity, Seismics):
            plot_rgb_option = None
            if isinstance(plot_entity.points, np_ndarray):
                # This  check is needed to avoid errors when trying to plot an empty
                # PolyData, just created at the beginning of a digitizing session.
                if show_property == "none" or show_property is None:
                    show_property = None
                elif show_property == "X":
                    show_property = plot_entity.points_X
                elif show_property == "Y":
                    show_property = plot_entity.points_Y
                elif show_property == "Z":
                    show_property = plot_entity.points_Z
                else:
                    if plot_entity.get_point_data_shape(show_property)[-1] == 3:
                        plot_rgb_option = True
                this_actor = self.plot_mesh(
                    uid=uid,
                    plot_entity=plot_entity,
                    color_RGB=color_RGB,
                    show_property=show_property,
                    color_bar_range=None,
                    show_property_title=show_property_title,
                    line_thick=line_thick,
                    plot_texture_option=False,
                    plot_rgb_option=plot_rgb_option,
                    visible=visible,
                    opacity=opacity,
                )
            else:
                this_actor = None
        elif isinstance(plot_entity, Voxet):
            plot_rgb_option = None
            if plot_entity.cells_number > 0:
                # This  check is needed to avoid errors when trying to plot an empty Voxet.
                # Here we treat X, Y, Z as None, in order to avoid a crash related to the fact that Voxets
                # do not have XYZ coordinates stored explicitly. This can be improved in the future.
                if any(
                    [
                        show_property == "none",
                        show_property is None,
                        show_property == "X",
                        show_property == "Y",
                        show_property == "Z",
                    ]
                ):
                    show_property = None
                else:
                    if plot_entity.get_point_data_shape(show_property)[-1] == 3:
                        plot_rgb_option = True
                this_actor = self.plot_mesh(
                    uid=uid,
                    plot_entity=plot_entity,
                    color_RGB=None,
                    show_property=show_property,
                    color_bar_range=None,
                    show_property_title=show_property_title,
                    line_thick=line_thick,
                    plot_texture_option=False,
                    plot_rgb_option=plot_rgb_option,
                    visible=visible,
                    opacity=opacity,
                )
            else:
                this_actor = None
        elif isinstance(plot_entity, WellTrace):
            plot_rgb_option = None
            if show_property == "none" or show_property is None:
                show_property = None
                self.plotter.remove_actor(f"{uid}_prop")
            elif show_property == "X":
                show_property = plot_entity.points_X
            elif show_property == "Y":
                show_property = plot_entity.points_Y
            elif show_property == "Z":
                show_property = plot_entity.points_Z
            elif show_property == "MD":
                show_property = plot_entity.get_point_data(data_key="MD")
            else:
                prop = plot_entity.plot_along_trace(
                    show_property, method=self.trace_method, camera=self.plotter.camera
                )
                self.plotter.add_actor(prop, name=f"{uid}_prop")
                show_property = None
                show_property_title = None
            this_actor = self.plot_mesh(
                uid=uid,
                plot_entity=plot_entity,
                color_RGB=color_RGB,
                show_property=show_property,
                color_bar_range=None,
                show_property_title=show_property_title,
                line_thick=line_thick,
                plot_texture_option=False,
                plot_rgb_option=plot_rgb_option,
                visible=visible,
                render_lines_as_tubes=False,
                opacity=opacity,
            )
        else:
            print("[Windows factory]: actor with no class")
            this_actor = None
        return this_actor


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

    def horizontal_mirror(self):
        """Mirror horizontal axes."""
        self.print_terminal("Mirroring horizontal axes.")
        # Mirror internal variable used to store direction
        self.direction = -self.direction
        # Apply to plotter
        self.plotter.camera.focal_point = self.center
        self.plotter.camera.position = self.center + self.direction
        self.plotter.reset_camera()


class ViewStereoplot(MPLView):
    def __init__(self, *args, **kwargs):
        super(ViewStereoplot, self).__init__(*args, **kwargs)
        self.setWindowTitle("Stereoplot View")
        self.tog_contours = -1
        # mplstyle.context('classic')

    def initialize_menu_tools(self):
        """This is the method of the ViewStereoplot() class, used to add menu tools in addition to those inherited from
        superclasses, that are appended here using super().initialize_menu_tools()."""
        # append code from MPLView()
        super().initialize_menu_tools()

        # then add new code specific to MPLView()
        self.actionContours = QAction("View contours", self)
        self.actionContours.triggered.connect(
            lambda: self.toggle_contours(filled=False)
        )
        self.menuView.addAction(self.actionContours)

        self.actionSetPolar = QAction("Set polar grid", self)
        self.actionSetPolar.triggered.connect(lambda: self.change_grid(kind="polar"))
        self.menuView.addAction(self.actionSetPolar)

        self.actionSetEq = QAction("Set equatorial grid", self)
        self.actionSetEq.triggered.connect(lambda: self.change_grid(kind="equatorial"))
        self.menuView.addAction(self.actionSetEq)

        self.actionSetEquiare = QAction("Equiareal (Schmidt)", self)
        self.actionSetEquiare.triggered.connect(
            lambda: self.change_proj(projection="equal_area_stereonet")
        )
        self.menuView.addAction(self.actionSetEquiare)

        self.actionSetEquiang = QAction("Equiangolar (Wulff)", self)
        self.actionSetEquiang.triggered.connect(
            lambda: self.change_proj(projection="equal_angle_stereonet")
        )
        self.menuView.addAction(self.actionSetEquiang)

    def initialize_interactor(self, kind=None, projection="equal_area_stereonet"):
        self.grid_kind = kind
        self.proj_type = projection

        with mplstyle.context("default"):
            # Create Matplotlib canvas, figure and navi_toolbar. this implicitly
            # creates also the canvas to contain the figure.
            self.figure, self.ax = mplstereonet.subplots(projection=self.proj_type)

        self.canvas = FigureCanvas(
            self.figure
        )  # get a reference to the canvas that contains the figure
        # print("dir(self.canvas):\n", dir(self.canvas))
        # https://doc.qt.io/qt-5/qsizepolicy.html
        self.navi_toolbar = NavigationToolbar(
            self.figure.canvas, self
        )  # create a navi_toolbar with the matplotlib.backends.backend_qt5agg method NavigationToolbar

        # Create Qt layout andNone add Matplotlib canvas, figure and navi_toolbar"""
        # canvas_widget = self.figure.canvas
        # canvas_widget.setAutoFillBackground(True)
        self.ViewFrameLayout.addWidget(
            self.canvas
        )  # add Matplotlib canvas (created above) as a widget to the Qt layout
        # print(plot_widget)
        self.ViewFrameLayout.addWidget(
            self.navi_toolbar
        )  # add navigation navi_toolbar (created above) to the layout
        self.ax.grid(kind=self.grid_kind, color="k")

    def create_geology_tree(self):
        """Create geology tree with checkboxes and properties"""
        self.GeologyTreeWidget.clear()
        self.GeologyTreeWidget.setColumnCount(3)
        self.GeologyTreeWidget.setHeaderLabels(
            ["Role > Feature > Scenario > Name", "uid", "property"]
        )
        self.GeologyTreeWidget.hideColumn(1)  # hide the uid column
        self.GeologyTreeWidget.setItemsExpandable(True)

        filtered_geo = self.parent.geol_coll.df.loc[
            (self.parent.geol_coll.df["topology"] == "VertexSet")
            | (self.parent.geol_coll.df["topology"] == "XsVertexSet"),
            "role",
        ]
        roles = pd_unique(filtered_geo)
        print("roles: ", roles)

        for role in roles:
            glevel_1 = QTreeWidgetItem(
                self.GeologyTreeWidget, [role]
            )  # self.GeologyTreeWidget as parent -> top level
            glevel_1.setFlags(
                glevel_1.flags() | Qt.ItemIsUserTristate | Qt.ItemIsUserCheckable
            )
            filtered_features = self.parent.geol_coll.df.loc[
                (self.parent.geol_coll.df["role"] == role)
                & (
                    (self.parent.geol_coll.df["topology"] == "VertexSet")
                    | (self.parent.geol_coll.df["topology"] == "XsVertexSet")
                ),
                "feature",
            ]
            features = pd_unique(filtered_features)
            print("features: ", features)
            for feature in features:
                glevel_2 = QTreeWidgetItem(
                    glevel_1, [feature]
                )  # glevel_1 as parent -> 1st middle level
                glevel_2.setFlags(
                    glevel_2.flags() | Qt.ItemIsUserTristate | Qt.ItemIsUserCheckable
                )
                geo_scenario = pd_unique(
                    self.parent.geol_coll.df.loc[
                        (self.parent.geol_coll.df["role"] == role)
                        & (self.parent.geol_coll.df["feature"] == feature),
                        "scenario",
                    ]
                )
                for scenario in geo_scenario:
                    glevel_3 = QTreeWidgetItem(
                        glevel_2, [scenario]
                    )  # glevel_2 as parent -> 2nd middle level
                    glevel_3.setFlags(
                        glevel_3.flags()
                        | Qt.ItemIsUserTristate
                        | Qt.ItemIsUserCheckable
                    )
                    uids = self.parent.geol_coll.df.loc[
                        (self.parent.geol_coll.df["role"] == role)
                        & (self.parent.geol_coll.df["feature"] == feature)
                        & (self.parent.geol_coll.df["scenario"] == scenario)
                        & (
                            (self.parent.geol_coll.df["topology"] == "VertexSet")
                            | (self.parent.geol_coll.df["topology"] == "XsVertexSet")
                        ),
                        "uid",
                    ].to_list()
                    for uid in uids:
                        property_combo = QComboBox()
                        property_combo.uid = uid
                        property_combo.addItem("Poles")
                        # property_combo.addItem("Planes")
                        name = self.parent.geol_coll.df.loc[
                            (self.parent.geol_coll.df["uid"] == uid), "name"
                        ].values[0]
                        glevel_4 = QTreeWidgetItem(
                            glevel_3, [name, uid]
                        )  # glevel_3 as parent -> lower level
                        self.GeologyTreeWidget.setItemWidget(
                            glevel_4, 2, property_combo
                        )
                        property_combo.currentIndexChanged.connect(
                            lambda *, sender=property_combo: self.toggle_property(
                                sender=sender
                            )
                        )
                        glevel_4.setFlags(glevel_4.flags() | Qt.ItemIsUserCheckable)
                        if self.actors_df.loc[
                            self.actors_df["uid"] == uid, "show"
                        ].values[0]:
                            glevel_4.setCheckState(0, Qt.Checked)
                        elif not self.actors_df.loc[
                            self.actors_df["uid"] == uid, "show"
                        ].values[0]:
                            glevel_4.setCheckState(0, Qt.Unchecked)
        # Send messages. Note that with tristate several signals are emitted in a sequence, one for each
        # changed item, but upper levels do not broadcast uid's so they are filtered in the toggle method.
        self.GeologyTreeWidget.itemChanged.connect(self.toggle_geology_visibility)
        self.GeologyTreeWidget.expandAll()

    def create_topology_tree(self):
        """Create topology tree with checkboxes and properties"""
        self.GeologyTopologyTreeWidget.clear()
        self.GeologyTopologyTreeWidget.setColumnCount(3)
        self.GeologyTopologyTreeWidget.setHeaderLabels(
            ["Role > Scenario > Name", "uid", "property"]
        )
        self.GeologyTopologyTreeWidget.hideColumn(1)  # hide the uid column
        self.GeologyTopologyTreeWidget.setItemsExpandable(True)

        filtered_topo = self.parent.geol_coll.df.loc[
            (self.parent.geol_coll.df["topology"] == "VertexSet")
            | (self.parent.geol_coll.df["topology"] == "XsVertexSet"),
            "topology",
        ]
        topo_types = pd_unique(filtered_topo)
        for topo_type in topo_types:
            tlevel_1 = QTreeWidgetItem(
                self.GeologyTopologyTreeWidget, [topo_type]
            )  # self.GeologyTreeWidget as parent -> top level
            tlevel_1.setFlags(
                tlevel_1.flags() | Qt.ItemIsUserTristate | Qt.ItemIsUserCheckable
            )
            for scenario in pd_unique(
                self.parent.geol_coll.df.loc[
                    self.parent.geol_coll.df["topology"] == topo_type, "scenario"
                ]
            ):
                tlevel_2 = QTreeWidgetItem(
                    tlevel_1, [scenario]
                )  # tlevel_1 as parent -> middle level
                tlevel_2.setFlags(
                    tlevel_2.flags() | Qt.ItemIsUserTristate | Qt.ItemIsUserCheckable
                )

                uids = self.parent.geol_coll.df.loc[
                    (self.parent.geol_coll.df["topology"] == topo_type)
                    & (self.parent.geol_coll.df["scenario"] == scenario)
                    & (
                        (self.parent.geol_coll.df["topology"] == "VertexSet")
                        | (self.parent.geol_coll.df["topology"] == "XsVertexSet")
                    ),
                    "uid",
                ].to_list()
                for uid in uids:
                    property_combo = QComboBox()
                    property_combo.uid = uid
                    property_combo.addItem("Poles")
                    # property_combo.addItem("Planes")
                    name = self.parent.geol_coll.df.loc[
                        self.parent.geol_coll.df["uid"] == uid, "name"
                    ].values[0]
                    tlevel_3 = QTreeWidgetItem(
                        tlevel_2, [name, uid]
                    )  # tlevel_2 as parent -> lower level
                    self.GeologyTopologyTreeWidget.setItemWidget(
                        tlevel_3, 2, property_combo
                    )
                    property_combo.currentIndexChanged.connect(
                        lambda *, sender=property_combo: self.toggle_property(
                            sender=sender
                        )
                    )
                    tlevel_3.setFlags(tlevel_3.flags() | Qt.ItemIsUserCheckable)
                    if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[
                        0
                    ]:
                        tlevel_3.setCheckState(0, Qt.Checked)
                    elif not self.actors_df.loc[
                        self.actors_df["uid"] == uid, "show"
                    ].values[0]:
                        tlevel_3.setCheckState(0, Qt.Unchecked)
        # Send messages. Note that with tristate several signals are emitted in a sequence, one for each
        # changed item, but upper levels do not broadcast uid's so they are filtered in the toggle method.
        self.GeologyTopologyTreeWidget.itemChanged.connect(
            self.toggle_geology_visibility
        )
        self.GeologyTopologyTreeWidget.expandAll()

    def update_geology_tree_added(self, new_list=None):
        """Update geology tree without creating a new model"""
        uid_list = list(new_list["uid"])
        for uid in uid_list:
            if (
                self.GeologyTreeWidget.findItems(
                    self.parent.geol_coll.get_uid_role(uid),
                    Qt.MatchExactly,
                    0,
                )
                != []
            ):
                # Already exists a TreeItem (1 level) for the geological type
                counter_1 = 0
                for child_1 in range(
                    self.GeologyTreeWidget.findItems(
                        self.parent.geol_coll.get_uid_role(uid),
                        Qt.MatchExactly,
                        0,
                    )[0].childCount()
                ):
                    # for cycle that loops n times as the number of subItems in the specific geological type branch
                    if self.GeologyTreeWidget.findItems(
                        self.parent.geol_coll.get_uid_role(uid),
                        Qt.MatchExactly,
                        0,
                    )[0].child(child_1).text(
                        0
                    ) == self.parent.geol_coll.get_uid_feature(
                        uid
                    ):
                        counter_1 += 1
                if counter_1 != 0:
                    for child_1 in range(
                        self.GeologyTreeWidget.findItems(
                            self.parent.geol_coll.get_uid_role(uid),
                            Qt.MatchExactly,
                            0,
                        )[0].childCount()
                    ):
                        if self.GeologyTreeWidget.findItems(
                            self.parent.geol_coll.get_uid_role(uid),
                            Qt.MatchExactly,
                            0,
                        )[0].child(child_1).text(
                            0
                        ) == self.parent.geol_coll.get_uid_feature(
                            uid
                        ):
                            # Already exists a TreeItem (2 level) for the geological feature
                            counter_2 = 0
                            for child_2 in range(
                                self.GeologyTreeWidget.itemBelow(
                                    self.GeologyTreeWidget.findItems(
                                        self.parent.geol_coll.get_uid_role(uid),
                                        Qt.MatchExactly,
                                        0,
                                    )[0]
                                ).childCount()
                            ):
                                # For cycle that loops n times as the number of sub-subItems in the
                                # specific geological type and geological feature branch.
                                if self.GeologyTreeWidget.itemBelow(
                                    self.GeologyTreeWidget.findItems(
                                        self.parent.geol_coll.get_uid_role(uid),
                                        Qt.MatchExactly,
                                        0,
                                    )[0]
                                ).child(child_2).text(
                                    0
                                ) == self.parent.geol_coll.get_uid_scenario(
                                    uid
                                ):
                                    counter_2 += 1
                            if counter_2 != 0:
                                for child_2 in range(
                                    self.GeologyTreeWidget.itemBelow(
                                        self.GeologyTreeWidget.findItems(
                                            self.parent.geol_coll.get_uid_role(uid),
                                            Qt.MatchExactly,
                                            0,
                                        )[0]
                                    ).childCount()
                                ):
                                    if self.GeologyTreeWidget.itemBelow(
                                        self.GeologyTreeWidget.findItems(
                                            self.parent.geol_coll.get_uid_role(uid),
                                            Qt.MatchExactly,
                                            0,
                                        )[0]
                                    ).child(child_2).text(
                                        0
                                    ) == self.parent.geol_coll.get_uid_scenario(
                                        uid
                                    ):
                                        # Same geological type, geological feature and scenario
                                        property_combo = QComboBox()
                                        property_combo.uid = uid
                                        # property_combo.addItem("Planes")
                                        property_combo.addItem("Poles")
                                        for (
                                            prop
                                        ) in self.parent.geol_coll.get_uid_properties_names(
                                            uid
                                        ):
                                            property_combo.addItem(prop)
                                        name = self.parent.geol_coll.get_uid_name(uid)
                                        glevel_4 = QTreeWidgetItem(
                                            self.GeologyTreeWidget.findItems(
                                                self.parent.geol_coll.get_uid_role(uid),
                                                Qt.MatchExactly,
                                                0,
                                            )[0]
                                            .child(child_1)
                                            .child(child_2),
                                            [name, uid],
                                        )
                                        self.GeologyTreeWidget.setItemWidget(
                                            glevel_4, 2, property_combo
                                        )
                                        property_combo.currentIndexChanged.connect(
                                            lambda *, sender=property_combo: self.toggle_property(
                                                sender=sender
                                            )
                                        )
                                        glevel_4.setFlags(
                                            glevel_4.flags() | Qt.ItemIsUserCheckable
                                        )
                                        if self.actors_df.loc[
                                            self.actors_df["uid"] == uid, "show"
                                        ].values[0]:
                                            glevel_4.setCheckState(0, Qt.Checked)
                                        elif not self.actors_df.loc[
                                            self.actors_df["uid"] == uid, "show"
                                        ].values[0]:
                                            glevel_4.setCheckState(0, Qt.Unchecked)
                                        self.GeologyTreeWidget.insertTopLevelItem(
                                            0, glevel_4
                                        )
                                        break
                            else:
                                # Same geological type and geological feature, different scenario
                                glevel_3 = QTreeWidgetItem(
                                    self.GeologyTreeWidget.findItems(
                                        self.parent.geol_coll.get_uid_role(uid),
                                        Qt.MatchExactly,
                                        0,
                                    )[0].child(child_1),
                                    [self.parent.geol_coll.get_uid_scenario(uid)],
                                )
                                glevel_3.setFlags(
                                    glevel_3.flags()
                                    | Qt.ItemIsUserTristate
                                    | Qt.ItemIsUserCheckable
                                )
                                self.GeologyTreeWidget.insertTopLevelItem(0, glevel_3)
                                property_combo = QComboBox()
                                property_combo.uid = uid
                                # property_combo.addItem("Planes")
                                property_combo.addItem("Poles")
                                for (
                                    prop
                                ) in self.parent.geol_coll.get_uid_properties_names(
                                    uid
                                ):
                                    property_combo.addItem(prop)
                                name = self.parent.geol_coll.get_uid_name(uid)
                                glevel_4 = QTreeWidgetItem(glevel_3, [name, uid])
                                self.GeologyTreeWidget.setItemWidget(
                                    glevel_4, 2, property_combo
                                )
                                property_combo.currentIndexChanged.connect(
                                    lambda *, sender=property_combo: self.toggle_property(
                                        sender=sender
                                    )
                                )
                                glevel_4.setFlags(
                                    glevel_4.flags() | Qt.ItemIsUserCheckable
                                )
                                if self.actors_df.loc[
                                    self.actors_df["uid"] == uid, "show"
                                ].values[0]:
                                    glevel_4.setCheckState(0, Qt.Checked)
                                elif not self.actors_df.loc[
                                    self.actors_df["uid"] == uid, "show"
                                ].values[0]:
                                    glevel_4.setCheckState(0, Qt.Unchecked)
                                self.GeologyTreeWidget.insertTopLevelItem(0, glevel_4)
                                break
                else:
                    # Same geological type, different geological feature and scenario
                    glevel_2 = QTreeWidgetItem(
                        self.GeologyTreeWidget.findItems(
                            self.parent.geol_coll.get_uid_role(uid),
                            Qt.MatchExactly,
                            0,
                        )[0],
                        [self.parent.geol_coll.get_uid_feature(uid)],
                    )
                    glevel_2.setFlags(
                        glevel_2.flags()
                        | Qt.ItemIsUserTristate
                        | Qt.ItemIsUserCheckable
                    )
                    self.GeologyTreeWidget.insertTopLevelItem(0, glevel_2)
                    glevel_3 = QTreeWidgetItem(
                        glevel_2, [self.parent.geol_coll.get_uid_scenario(uid)]
                    )
                    glevel_3.setFlags(
                        glevel_3.flags()
                        | Qt.ItemIsUserTristate
                        | Qt.ItemIsUserCheckable
                    )
                    self.GeologyTreeWidget.insertTopLevelItem(0, glevel_3)
                    property_combo = QComboBox()
                    property_combo.uid = uid
                    # property_combo.addItem("Planes")
                    property_combo.addItem("Poles")
                    for prop in self.parent.geol_coll.get_uid_properties_names(uid):
                        property_combo.addItem(prop)
                    name = self.parent.geol_coll.get_uid_name(uid)
                    glevel_4 = QTreeWidgetItem(glevel_3, [name, uid])
                    self.GeologyTreeWidget.setItemWidget(glevel_4, 2, property_combo)
                    property_combo.currentIndexChanged.connect(
                        lambda *, sender=property_combo: self.toggle_property(
                            sender=sender
                        )
                    )
                    glevel_4.setFlags(glevel_4.flags() | Qt.ItemIsUserCheckable)
                    if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[
                        0
                    ]:
                        glevel_4.setCheckState(0, Qt.Checked)
                    elif not self.actors_df.loc[
                        self.actors_df["uid"] == uid, "show"
                    ].values[0]:
                        glevel_4.setCheckState(0, Qt.Unchecked)
                    self.GeologyTreeWidget.insertTopLevelItem(0, glevel_4)
                    break
            else:
                # Different geological type, geological feature and scenario
                glevel_1 = QTreeWidgetItem(
                    self.GeologyTreeWidget,
                    [self.parent.geol_coll.get_uid_role(uid)],
                )
                glevel_1.setFlags(
                    glevel_1.flags() | Qt.ItemIsUserTristate | Qt.ItemIsUserCheckable
                )
                self.GeologyTreeWidget.insertTopLevelItem(0, glevel_1)
                glevel_2 = QTreeWidgetItem(
                    glevel_1, [self.parent.geol_coll.get_uid_feature(uid)]
                )
                glevel_2.setFlags(
                    glevel_2.flags() | Qt.ItemIsUserTristate | Qt.ItemIsUserCheckable
                )
                self.GeologyTreeWidget.insertTopLevelItem(0, glevel_2)
                glevel_3 = QTreeWidgetItem(
                    glevel_2, [self.parent.geol_coll.get_uid_scenario(uid)]
                )
                glevel_3.setFlags(
                    glevel_3.flags() | Qt.ItemIsUserTristate | Qt.ItemIsUserCheckable
                )
                self.GeologyTreeWidget.insertTopLevelItem(0, glevel_3)
                property_combo = QComboBox()
                property_combo.uid = uid
                # property_combo.addItem("Planes")
                property_combo.addItem("Poles")
                for prop in self.parent.geol_coll.get_uid_properties_names(uid):
                    property_combo.addItem(prop)
                name = self.parent.geol_coll.get_uid_name(uid)
                glevel_4 = QTreeWidgetItem(glevel_3, [name, uid])
                self.GeologyTreeWidget.setItemWidget(glevel_4, 2, property_combo)
                property_combo.currentIndexChanged.connect(
                    lambda *, sender=property_combo: self.toggle_property(sender=sender)
                )
                glevel_4.setFlags(glevel_4.flags() | Qt.ItemIsUserCheckable)
                if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                    glevel_4.setCheckState(0, Qt.Checked)
                elif not self.actors_df.loc[
                    self.actors_df["uid"] == uid, "show"
                ].values[0]:
                    glevel_4.setCheckState(0, Qt.Unchecked)
                self.GeologyTreeWidget.insertTopLevelItem(0, glevel_4)
                break
        self.GeologyTreeWidget.itemChanged.connect(self.toggle_geology_visibility)
        self.GeologyTreeWidget.expandAll()

    def update_topology_tree_added(self, new_list=None):
        """Update topology tree without creating a new model"""
        uid_list = list(new_list["uid"])
        for uid in uid_list:
            if (
                self.GeologyTopologyTreeWidget.findItems(
                    self.parent.geol_coll.get_uid_topology(uid),
                    Qt.MatchExactly,
                    0,
                )
                != []
            ):
                # Already exists a TreeItem (1 level) for the topological type
                counter_1 = 0
                for child_1 in range(
                    self.GeologyTopologyTreeWidget.findItems(
                        self.parent.geol_coll.get_uid_topology(uid),
                        Qt.MatchExactly,
                        0,
                    )[0].childCount()
                ):
                    # for cycle that loops n times as the number of subItems in the specific topological type branch
                    if self.GeologyTopologyTreeWidget.findItems(
                        self.parent.geol_coll.get_uid_topology(uid),
                        Qt.MatchExactly,
                        0,
                    )[0].child(child_1).text(
                        0
                    ) == self.parent.geol_coll.get_uid_scenario(
                        uid
                    ):
                        counter_1 += 1
                if counter_1 != 0:
                    for child_1 in range(
                        self.GeologyTopologyTreeWidget.findItems(
                            self.parent.geol_coll.get_uid_topology(uid),
                            Qt.MatchExactly,
                            0,
                        )[0].childCount()
                    ):
                        if self.GeologyTopologyTreeWidget.findItems(
                            self.parent.geol_coll.get_uid_topology(uid),
                            Qt.MatchExactly,
                            0,
                        )[0].child(child_1).text(
                            0
                        ) == self.parent.geol_coll.get_uid_scenario(
                            uid
                        ):
                            # Same topological type and scenario
                            property_combo = QComboBox()
                            property_combo.uid = uid
                            # property_combo.addItem("Planes")
                            property_combo.addItem("Poles")
                            for prop in self.parent.geol_coll.get_uid_properties_names(
                                uid
                            ):
                                property_combo.addItem(prop)
                            name = self.parent.geol_coll.get_uid_name(uid)
                            tlevel_3 = QTreeWidgetItem(
                                self.GeologyTopologyTreeWidget.findItems(
                                    self.parent.geol_coll.get_uid_topology(uid),
                                    Qt.MatchExactly,
                                    0,
                                )[0].child(child_1),
                                [name, uid],
                            )
                            self.GeologyTopologyTreeWidget.setItemWidget(
                                tlevel_3, 2, property_combo
                            )
                            property_combo.currentIndexChanged.connect(
                                lambda *, sender=property_combo: self.toggle_property(
                                    sender=sender
                                )
                            )
                            tlevel_3.setFlags(tlevel_3.flags() | Qt.ItemIsUserCheckable)
                            if self.actors_df.loc[
                                self.actors_df["uid"] == uid, "show"
                            ].values[0]:
                                tlevel_3.setCheckState(0, Qt.Checked)
                            elif not self.actors_df.loc[
                                self.actors_df["uid"] == uid, "show"
                            ].values[0]:
                                tlevel_3.setCheckState(0, Qt.Unchecked)
                            self.GeologyTopologyTreeWidget.insertTopLevelItem(
                                0, tlevel_3
                            )
                            break
                else:
                    # Same topological type, different scenario
                    tlevel_2 = QTreeWidgetItem(
                        self.GeologyTopologyTreeWidget.findItems(
                            self.parent.geol_coll.get_uid_topology(uid),
                            Qt.MatchExactly,
                            0,
                        )[0],
                        [self.parent.geol_coll.get_uid_scenario(uid)],
                    )
                    tlevel_2.setFlags(
                        tlevel_2.flags()
                        | Qt.ItemIsUserTristate
                        | Qt.ItemIsUserCheckable
                    )
                    self.GeologyTopologyTreeWidget.insertTopLevelItem(0, tlevel_2)
                    property_combo = QComboBox()
                    property_combo.uid = uid
                    # property_combo.addItem("Planes")
                    property_combo.addItem("Poles")
                    for prop in self.parent.geol_coll.get_uid_properties_names(uid):
                        property_combo.addItem(prop)
                    name = self.parent.geol_coll.get_uid_name(uid)
                    tlevel_3 = QTreeWidgetItem(tlevel_2, [name, uid])
                    self.GeologyTopologyTreeWidget.setItemWidget(
                        tlevel_3, 2, property_combo
                    )
                    property_combo.currentIndexChanged.connect(
                        lambda *, sender=property_combo: self.toggle_property(
                            sender=sender
                        )
                    )
                    tlevel_3.setFlags(tlevel_3.flags() | Qt.ItemIsUserCheckable)
                    if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[
                        0
                    ]:
                        tlevel_3.setCheckState(0, Qt.Checked)
                    elif not self.actors_df.loc[
                        self.actors_df["uid"] == uid, "show"
                    ].values[0]:
                        tlevel_3.setCheckState(0, Qt.Unchecked)
                    self.GeologyTopologyTreeWidget.insertTopLevelItem(0, tlevel_3)
                    break
            else:
                # Different topological type and scenario
                tlevel_1 = QTreeWidgetItem(
                    self.GeologyTopologyTreeWidget,
                    [self.parent.geol_coll.get_uid_topology(uid)],
                )
                tlevel_1.setFlags(
                    tlevel_1.flags() | Qt.ItemIsUserTristate | Qt.ItemIsUserCheckable
                )
                self.GeologyTopologyTreeWidget.insertTopLevelItem(0, tlevel_1)
                tlevel_2 = QTreeWidgetItem(
                    tlevel_1, [self.parent.geol_coll.get_uid_scenario(uid)]
                )
                tlevel_2.setFlags(
                    tlevel_2.flags() | Qt.ItemIsUserTristate | Qt.ItemIsUserCheckable
                )
                self.GeologyTopologyTreeWidget.insertTopLevelItem(0, tlevel_2)
                property_combo = QComboBox()
                property_combo.uid = uid
                # property_combo.addItem("Planes")
                property_combo.addItem("Poles")
                for prop in self.parent.geol_coll.get_uid_properties_names(uid):
                    property_combo.addItem(prop)
                name = self.parent.geol_coll.get_uid_name(uid)
                tlevel_3 = QTreeWidgetItem(tlevel_2, [name, uid])
                self.GeologyTopologyTreeWidget.setItemWidget(
                    tlevel_3, 2, property_combo
                )
                property_combo.currentIndexChanged.connect(
                    lambda *, sender=property_combo: self.toggle_property(sender=sender)
                )
                tlevel_3.setFlags(tlevel_3.flags() | Qt.ItemIsUserCheckable)
                if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                    tlevel_3.setCheckState(0, Qt.Checked)
                elif not self.actors_df.loc[
                    self.actors_df["uid"] == uid, "show"
                ].values[0]:
                    tlevel_3.setCheckState(0, Qt.Unchecked)
                self.GeologyTopologyTreeWidget.insertTopLevelItem(0, tlevel_3)
                break
        self.GeologyTopologyTreeWidget.itemChanged.connect(
            self.toggle_geology_visibility
        )
        self.GeologyTopologyTreeWidget.expandAll()

    def set_actor_visible(self, uid=None, visible=None):
        # print(self.actors_df)
        """Set actor uid visible or invisible (visible = True or False)"""
        if isinstance(
            self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[0], Line2D
        ):
            "Case for Line2D"
            self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[
                0
            ].set_visible(visible)
            self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[
                0
            ].figure.canvas.draw()
        elif isinstance(
            self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[0],
            PathCollection,
        ):
            "Case for PathCollection -> ax.scatter"
            pass
        elif isinstance(
            self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[0],
            TriContourSet,
        ):
            "Case for TriContourSet -> ax.tricontourf"
            pass
        elif isinstance(
            self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[0],
            AxesImage,
        ):
            "Case for AxesImage (i.e. images)"
            # Hide other images if (1) they are shown and (2) you are showing another one.
            for hide_uid in self.actors_df.loc[
                (self.actors_df["collection"] == "image_coll")
                & (self.actors_df["show"])
                & (self.actors_df["uid"] != uid),
                "uid",
            ].to_list():
                self.actors_df.loc[self.actors_df["uid"] == hide_uid, "show"] = False
                self.actors_df.loc[self.actors_df["uid"] == hide_uid, "actor"].values[
                    0
                ].set_visible(False)
                row = self.ImagesTableWidget.findItems(hide_uid, Qt.MatchExactly)[
                    0
                ].row()
                self.ImagesTableWidget.item(row, 0).setCheckState(Qt.Unchecked)
            # Then show this one.
            self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[
                0
            ].set_visible(visible)
            self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[
                0
            ].figure.canvas.draw()
        else:
            "Do-nothing option to avoid errors, but it does not set/unset visibility."
            pass

    def remove_actor_in_view(self, uid=None, redraw=False):
        """ "Remove actor from plotter"""
        # Can remove a single entity or a list of entities as actors - here we remove a single entity"

        if not self.actors_df.loc[self.actors_df["uid"] == uid].empty:
            if self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[0]:
                # print(self.actors_df.loc[self.actors_df['uid'] == uid, 'actor'].values)
                # print(self.actors_df.loc[self.actors_df['uid'] == uid, 'actor'].values[0])
                self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[
                    0
                ].remove()
                self.actors_df.drop(
                    self.actors_df[self.actors_df["uid"] == uid].index, inplace=True
                )
            if redraw:
                # IN THE FUTURE check if there is a way to redraw just the actor that has just been removed.
                self.figure.canvas.draw()
                print("redraw all - a more efficient alternative should be found")

    def show_actor_with_property(
        self,
        uid=None,
        collection=None,
        show_property="Poles",
        visible=None,
        filled=None,
    ):
        if show_property is None:
            show_property = "Poles"
        # Show actor with scalar property (default None)
        # https://github.com/pyvista/pyvista/blob/140b15be1d4021b81ded46b1c212c70e86a98ee7/pyvista/plotting/plotting.py#L1045
        # First get the vtk object from its collection.
        show_property_title = show_property
        this_coll = eval("self.parent." + collection)
        if collection == "geol_coll":
            color_R = this_coll.get_uid_legend(uid=uid)["color_R"]
            color_G = this_coll.get_uid_legend(uid=uid)["color_G"]
            color_B = this_coll.get_uid_legend(uid=uid)["color_B"]
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            line_thick = this_coll.get_uid_legend(uid=uid)["line_thick"]
            plot_entity = this_coll.get_uid_vtk_obj(uid)
        else:
            # catch errors
            print("no collection", collection)
            plot_entity = None
        # Then plot.
        if isinstance(plot_entity, (VertexSet, XsVertexSet, Attitude)):
            if isinstance(plot_entity.points, np_ndarray):
                if plot_entity.points_number > 0:
                    # This check is needed to avoid errors when trying to plot an empty
                    # PolyData, just created at the beginning of a digitizing session.
                    # Check if both these conditions are necessary_________________
                    # [Gabriele] Dip az needs to be converted to strike (dz-90) to plot with mplstereonet
                    strike = (plot_entity.points_map_dip_azimuth - 90) % 360
                    dip = plot_entity.points_map_dip

                    if np_all(strike != None):
                        if uid in self.selected_uids:
                            if show_property == "Planes":
                                this_actor = self.ax.plane(
                                    strike, dip, color=color_RGB
                                )[0]
                            else:
                                this_actor = self.ax.pole(strike, dip, color=color_RGB)[
                                    0
                                ]

                            this_actor.set_visible(visible)
                        else:
                            if show_property == "Planes":
                                this_actor = self.ax.plane(
                                    strike, dip, color=color_RGB
                                )[0]
                            else:
                                if filled is not None and visible is True:
                                    if filled:
                                        self.ax.density_contourf(
                                            strike, dip, measurement="poles"
                                        )
                                    else:
                                        self.ax.density_contour(
                                            strike, dip, measurement="poles"
                                        )
                                this_actor = self.ax.pole(strike, dip, color=color_RGB)[
                                    0
                                ]
                            if this_actor:
                                this_actor.set_visible(visible)
                    else:
                        this_actor = None
                else:
                    this_actor = None
            else:
                this_actor = None
        else:
            this_actor = None
        if this_actor:
            this_actor.figure.canvas.draw()
        return this_actor

    # def stop_event_loops(self):
    #     """Terminate running event loops"""
    #     self.figure.canvas.stop_event_loop()

    def change_grid(self, kind):
        self.grid_kind = kind
        self.ViewFrameLayout.removeWidget(self.canvas)
        self.ViewFrameLayout.removeWidget(self.navi_toolbar)
        self.initialize_interactor(kind=kind, projection=self.proj_type)
        uids = self.parent.geol_coll.df.loc[
            self.parent.geol_coll.df["topology"] == "VertexSet", "uid"
        ]

        # [Gabriele]It is not always the case that VertexSets have normal data (are attitude measurements). When
        # importing from shp we should add a dialog to identify VertexSets as Attitude measurements

        # att_uid_list = []
        # for uid in uids:
        #     obj = self.parent.geol_coll.get_uid_vtk_obj(uid)
        #     if isinstance(obj, Attitude):
        #         att_uid_list.append(uid)
        # print(att_uid_list)
        for uid in uids:
            show = self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]
            self.remove_actor_in_view(uid, redraw=False)
            this_actor = self.show_actor_with_property(uid, "geol_coll", visible=show)
            # Old Pandas <= 1.5.3
            # self.actors_df = self.actors_df.append(
            #     {
            #         "uid": uid,
            #         "actor": this_actor,
            #         "show": show,
            #         "collection": "geol_collection",
            #         "show_property": "poles",
            #     },
            #     ignore_index=True,
            # )
            # New Pandas >= 2.0.0
            self.actors_df = pd_concat(
                [
                    self.actors_df,
                    pd_DataFrame(
                        [
                            {
                                "uid": uid,
                                "actor": this_actor,
                                "show": show,
                                "collection": "geol_collection",
                                "show_property": "poles",
                            }
                        ]
                    ),
                ],
                ignore_index=True,
            )
            # For now only geol_collection (I guess this is the only collection for attitude measurements)

    def change_proj(self, projection):
        self.proj_type = projection
        self.ViewFrameLayout.removeWidget(self.canvas)
        self.ViewFrameLayout.removeWidget(self.navi_toolbar)
        self.initialize_interactor(kind=self.grid_kind, projection=self.proj_type)
        uids = self.parent.geol_coll.df.loc[
            self.parent.geol_coll.df["topology"] == "VertexSet", "uid"
        ]
        for uid in uids:
            show = self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]
            self.remove_actor_in_view(uid, redraw=False)
            this_actor = self.show_actor_with_property(uid, "geol_coll", visible=show)
            # Old Pandas <= 1.5.3
            # self.actors_df = self.actors_df.append(
            #     {
            #         "uid": uid,
            #         "actor": this_actor,
            #         "show": show,
            #         "collection": "geol_collection",
            #         "show_property": "poles",
            #     },
            #     ignore_index=True,
            # )
            # New Pandas >= 2.0.0
            self.actors_df = pd_concat(
                [
                    self.actors_df,
                    pd_DataFrame(
                        [
                            {
                                "uid": uid,
                                "actor": this_actor,
                                "show": show,
                                "collection": "geol_collection",
                                "show_property": "poles",
                            }
                        ]
                    ),
                ],
                ignore_index=True,
            )

    def toggle_contours(self, filled=False):
        # This is not the best way, but for now will do.
        """It's a toggle switch that display kamb contours for visible poles in
        the stereoplot."""

        self.ViewFrameLayout.removeWidget(self.canvas)
        self.ViewFrameLayout.removeWidget(self.navi_toolbar)

        self.initialize_interactor(kind=self.grid_kind, projection=self.proj_type)
        uids = self.parent.geol_coll.df.loc[
            (self.parent.geol_coll.df["topology"] == "VertexSet")
            | (self.parent.geol_coll.df["topology"] == "XsVertexSet"),
            "uid",
        ]

        if self.tog_contours == -1:
            filled_opt = filled
            self.tog_contours *= -1
            print("Contours enabled")
        else:
            filled_opt = None
            self.tog_contours *= -1
            print("Contours disabled")

        for uid in uids:
            show = self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]

            self.remove_actor_in_view(uid, redraw=False)

            this_actor = self.show_actor_with_property(
                uid, "geol_coll", visible=show, filled=filled_opt
            )
            # Old Pandas <= 1.5.3
            # self.actors_df = self.actors_df.append(
            #     {
            #         "uid": uid,
            #         "actor": this_actor,
            #         "show": show,
            #         "collection": "geol_collection",
            #         "show_property": "poles",
            #     },
            #     ignore_index=True,
            # )
            # New Pandas >= 2.0.0
            self.actors_df = pd_concat(
                [
                    self.actors_df,
                    pd_DataFrame(
                        [
                            {
                                "uid": uid,
                                "actor": this_actor,
                                "show": show,
                                "collection": "geol_collection",
                                "show_property": "poles",
                            }
                        ]
                    ),
                ],
                ignore_index=True,
            )

    def change_actor_color(self, uid=None, collection=None):
        """Change colour with Matplotlib method."""
        if collection == "geol_coll":
            color_R = self.parent.geol_coll.get_uid_legend(uid=uid)["color_R"]
            color_G = self.parent.geol_coll.get_uid_legend(uid=uid)["color_G"]
            color_B = self.parent.geol_coll.get_uid_legend(uid=uid)["color_B"]
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
        elif collection == "xsect_coll":
            color_R = self.parent.xsect_coll.get_legend()["color_R"]
            color_G = self.parent.xsect_coll.get_legend()["color_G"]
            color_B = self.parent.xsect_coll.get_legend()["color_B"]
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
        else:
            return
        if isinstance(
            self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[0], Line2D
        ):
            "Case for Line2D"
            self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[
                0
            ].set_color(color_RGB)
            self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[
                0
            ].figure.canvas.draw()

    def change_actor_opacity(self, uid=None, collection=None):
        return

    def change_actor_line_thick(self, uid=None, collection=None):
        return

    def change_actor_point_size(self, uid=None, collection=None):
        return
