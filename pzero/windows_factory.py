"""windows_factory.py
PZero© Andrea Bistacchi"""
from vtkmodules.vtkRenderingCore import vtkPropPicker

"""QT imports"""
from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt

"""PZero imports"""
from pzero.ui.base_view_window_ui import Ui_BaseViewWindow
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
from pzero.helpers.helper_dialogs import (
    input_one_value_dialog,
    input_combo_dialog,
    message_dialog,
    multiple_input_dialog,
    progress_dialog,
    save_file_dialog,
    NavigatorWidget,
)
from pzero.collections.geological_collection import GeologicalCollection
from .orientation_analysis import get_dip_dir_vectors
from pzero.helpers.helper_functions import best_fitting_plane, gen_frame
from pzero.helpers.helper_widgets import Vector

"""Maths imports"""
from math import degrees, sqrt, atan2
from numpy import append as np_append
from numpy import ndarray as np_ndarray
from numpy import sin as np_sin
from numpy import cos as np_cos
from numpy import pi as np_pi
from numpy import array as np_array
from numpy import all as np_all
from numpy import cross as np_cross

from pandas import DataFrame as pd_DataFrame
from pandas import unique as pd_unique

from copy import deepcopy
from uuid import uuid4

""""VTK imports"""
""""VTK Numpy interface imports"""
# import vtk.numpy_interface.dataset_adapter as dsa
from vtkmodules.util import numpy_support
from vtkmodules.vtkInteractionWidgets import vtkCameraOrientationWidget
from vtk import vtkExtractPoints, vtkSphere, vtkAppendPolyData

"""3D plotting imports"""
from pyvista import global_theme as pv_global_theme
from pyvistaqt import QtInteractor as pvQtInteractor
from pyvista import Box as pv_Box
from pyvista import Line as pv_Line
from pyvista import Disc as pv_Disc

from pyvista import PointSet as pvPointSet
from pyvista import Plotter as pv_plot

"""2D plotting imports"""
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import (
    NavigationToolbar2QT,
)  # this is customized in subclass NavigationToolbar a few lines below

# DO NOT USE import matplotlib.pyplot as plt  IT CREATES A DUPLICATE WINDOW IN NOTEBOOK
from matplotlib.figure import Figure
from matplotlib.offsetbox import TextArea
from matplotlib.lines import Line2D
from matplotlib.image import AxesImage
from matplotlib.collections import PathCollection
from matplotlib.tri.tricontour import TriContourSet
import matplotlib.style as mplstyle

# from matplotlib.backend_bases import FigureCanvasBase
import mplstereonet

"""Probably not-required imports"""
# import sys
# from time import sleep
# from uuid import UUID (there is already above 'from uuid import uuid4')


mplstyle.use(["dark_background", "fast"])
"""Background color for matplotlib plots.
Could be made interactive in the future.
'fast' is supposed to make plotting large objects faster"""


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


class BaseView(QMainWindow, Ui_BaseViewWindow):
    """Create base view - abstract class providing common methods for all views"""

    """parent is the QT object that is launching this one, hence the ProjectWindow() instance in this case"""

    def __init__(self, parent=None, *args, **kwargs):
        super(BaseView, self).__init__(parent, *args, **kwargs)
        self.setupUi(self)
        # _____________________________________________________________________________
        # THE FOLLOWING ACTUALLY DELETES ANY REFERENCE TO CLOSED WINDOWS, HENCE FREEING
        # MEMORY, BUT COULD CREATE PROBLEMS WITH SIGNALS THAT ARE STILL ACTIVE
        # SEE DISCUSSIONS ON QPointer AND WA_DeleteOnClose ON THE INTERNET
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.parent = parent
        """Connect actionQuit.triggered SIGNAL to self.close SLOT"""
        self.actionClose.triggered.connect(self.close)

        """Connect signal to delete window when the project is closed (and a new one is opened)."""
        self.parent.project_close_signal.connect(self.close)

        """Create empty Pandas dataframe with actor's with columns:
        uid = actor's uid -> the same as the original object's uid
        actor = the actor
        show = a boolean to show (True) or hide (false) the actor
        collection = the original collection of the actor, e.g. geol_coll, xsect_coll, etc."""
        self.actors_df = pd_DataFrame(columns=["uid", "actor", "show", "collection"])

        """Create list of selected uid's."""
        self.selected_uids = []

        """Initialize menus and tools, canvas, add actors and show it. These methods must be defined in subclasses."""
        self.initialize_menu_tools()
        self.initialize_interactor()
        self.add_all_entities()
        self.show_qt_canvas()

        if not isinstance(self, NewViewXsection):
            """Build and show geology and topology trees, and cross-section, DOM, image, lists.
            Reimplemented for NewViewXsection with entities limited to those belonging to the Xsection.
            """
            self.create_geology_tree()
            self.create_topology_tree()
            self.create_xsections_tree()
            self.create_boundary_list()
            self.create_mesh3d_list()
            self.create_dom_list()
            self.create_image_list()
            self.create_well_tree()
            self.create_fluids_tree()
            self.create_fluids_topology_tree()
            self.create_backgrounds_tree()
            self.create_backgrounds_topology_tree()

        """Build and show other widgets, icons, tools - TO BE DONE_________________________________"""

        """Connect signals to update functions. Use lambda functions where we need to pass additional
        arguments such as parent in addition to the signal itself - the updated_list."""

        # Geology lamda functions and signals
        self.upd_list_geo_add = lambda updated_list: self.geology_added_update_views(
            updated_list=updated_list
        )
        self.upd_list_geo_rm = lambda updated_list: self.geology_removed_update_views(
            updated_list=updated_list
        )
        self.upd_list_geo_mod = (
            lambda updated_list: self.geology_geom_modified_update_views(
                updated_list=updated_list
            )
        )
        self.upd_list_geo_datakeys_mod = (
            lambda updated_list: self.geology_data_keys_modified_update_views(
                updated_list=updated_list
            )
        )
        self.upd_list_geo_dataval_mod = (
            lambda updated_list: self.geology_data_val_modified_update_views(
                updated_list=updated_list
            )
        )
        self.upd_list_geo_metadata_mod = (
            lambda updated_list: self.geology_metadata_modified_update_views(
                updated_list=updated_list
            )
        )
        self.upd_list_geo_leg_col_mod = (
            lambda updated_list: self.geology_legend_color_modified_update_views(
                updated_list=updated_list
            )
        )
        self.upd_list_geo_leg_thick_mod = (
            lambda updated_list: self.geology_legend_thick_modified_update_views(
                updated_list=updated_list
            )
        )
        self.upd_list_geo_leg_point_mod = (
            lambda updated_list: self.geology_legend_point_size_modified_update_views(
                updated_list=updated_list
            )
        )
        self.upd_list_geo_leg_op_mod = (
            lambda updated_list: self.geology_legend_opacity_modified_update_views(
                updated_list=updated_list
            )
        )

        self.parent.geology_added_signal.connect(self.upd_list_geo_add)
        self.parent.geology_removed_signal.connect(self.upd_list_geo_rm)
        self.parent.geology_geom_modified_signal.connect(self.upd_list_geo_mod)
        self.parent.geology_data_keys_removed_signal.connect(
            self.upd_list_geo_datakeys_mod
        )
        self.parent.geology_data_val_modified_signal.connect(
            self.upd_list_geo_dataval_mod
        )
        self.parent.geology_metadata_modified_signal.connect(
            self.upd_list_geo_metadata_mod
        )
        self.parent.geology_legend_color_modified_signal.connect(
            self.upd_list_geo_leg_col_mod
        )
        self.parent.geology_legend_thick_modified_signal.connect(
            self.upd_list_geo_leg_thick_mod
        )
        self.parent.geology_legend_point_size_modified_signal.connect(
            self.upd_list_geo_leg_point_mod
        )
        self.parent.geology_legend_opacity_modified_signal.connect(
            self.upd_list_geo_leg_op_mod
        )

        # X Section lamda functions and signals
        self.upd_list_x_add = lambda updated_list: self.xsect_added_update_views(
            updated_list=updated_list
        )
        self.upd_list_x_rm = lambda updated_list: self.xsect_removed_update_views(
            updated_list=updated_list
        )
        self.upd_list_x_mod = (
            lambda updated_list: self.xsect_geom_modified_update_views(
                updated_list=updated_list
            )
        )
        self.upd_list_x_metadata_mod = (
            lambda updated_list: self.xsect_metadata_modified_update_views(
                updated_list=updated_list
            )
        )
        self.upd_list_x_leg_col_mod = (
            lambda updated_list: self.xsect_legend_color_modified_update_views(
                updated_list=updated_list
            )
        )
        self.upd_list_x_leg_thick_mod = (
            lambda updated_list: self.xsect_legend_thick_modified_update_views(
                updated_list=updated_list
            )
        )
        self.upd_list_x_leg_op_mod = (
            lambda updated_list: self.xsect_legend_opacity_modified_update_views(
                updated_list=updated_list
            )
        )

        self.parent.xsect_added_signal.connect(self.upd_list_x_add)
        self.parent.xsect_removed_signal.connect(self.upd_list_x_rm)
        self.parent.xsect_geom_modified_signal.connect(self.upd_list_x_mod)
        self.parent.xsect_metadata_modified_signal.connect(self.upd_list_x_metadata_mod)
        self.parent.xsect_legend_color_modified_signal.connect(
            self.upd_list_x_leg_col_mod
        )
        self.parent.xsect_legend_thick_modified_signal.connect(
            self.upd_list_x_leg_thick_mod
        )
        self.parent.xsect_legend_opacity_modified_signal.connect(
            self.upd_list_x_leg_op_mod
        )

        # Boundary lamda functions and signals
        self.upd_list_bound_add = lambda updated_list: self.boundary_added_update_views(
            updated_list=updated_list
        )
        self.upd_list_bound_rm = (
            lambda updated_list: self.boundary_removed_update_views(
                updated_list=updated_list
            )
        )
        self.upd_list_bound_geo_mod = (
            lambda updated_list: self.boundary_geom_modified_update_views(
                updated_list=updated_list
            )
        )
        self.upd_list_bound_metadata_mod = (
            lambda updated_list: self.boundary_metadata_modified_update_views(
                updated_list=updated_list
            )
        )
        self.upd_list_bound_leg_col_mod = (
            lambda updated_list: self.boundary_legend_color_modified_update_views(
                updated_list=updated_list
            )
        )
        self.upd_list_bound_leg_thick_mod = (
            lambda updated_list: self.boundary_legend_thick_modified_update_views(
                updated_list=updated_list
            )
        )
        self.upd_list_bound_leg_op_mod = (
            lambda updated_list: self.boundary_legend_opacity_modified_update_views(
                updated_list=updated_list
            )
        )

        self.parent.boundary_added_signal.connect(self.upd_list_bound_add)
        self.parent.boundary_removed_signal.connect(self.upd_list_bound_rm)
        self.parent.boundary_geom_modified_signal.connect(self.upd_list_bound_geo_mod)
        self.parent.boundary_metadata_modified_signal.connect(
            self.upd_list_bound_metadata_mod
        )
        self.parent.boundary_legend_color_modified_signal.connect(
            self.upd_list_bound_leg_col_mod
        )
        self.parent.boundary_legend_thick_modified_signal.connect(
            self.upd_list_bound_leg_thick_mod
        )
        self.parent.boundary_legend_opacity_modified_signal.connect(
            self.upd_list_bound_leg_op_mod
        )

        # Mesh 3D lamda functions and signals
        self.upd_list_mesh3d_add = lambda updated_list: self.mesh3d_added_update_views(
            updated_list=updated_list
        )
        self.upd_list_mesh3d_rm = lambda updated_list: self.mesh3d_removed_update_views(
            updated_list=updated_list
        )
        self.upd_list_mesh3d_data_keys_mod = (
            lambda updated_list: self.mesh3d_data_keys_modified_update_views(
                updated_list=updated_list
            )
        )
        self.upd_list_mesh3d_data_val_mod = (
            lambda updated_list: self.mesh3d_data_val_modified_update_views(
                updated_list=updated_list
            )
        )
        self.upd_list_mesh3d_metadata_mod = (
            lambda updated_list: self.mesh3d_metadata_modified_update_views(
                updated_list=updated_list
            )
        )
        self.upd_list_mesh3d_leg_col_mod = (
            lambda updated_list: self.mesh3d_legend_color_modified_update_views(
                updated_list=updated_list
            )
        )
        self.upd_list_mesh3d_leg_thick_mod = (
            lambda updated_list: self.mesh3d_legend_thick_modified_update_views(
                updated_list=updated_list
            )
        )
        self.upd_list_mesh3d_leg_op_mod = (
            lambda updated_list: self.mesh3d_legend_opacity_modified_update_views(
                updated_list=updated_list
            )
        )

        self.parent.mesh3d_added_signal.connect(self.upd_list_mesh3d_add)
        self.parent.mesh3d_removed_signal.connect(self.upd_list_mesh3d_rm)
        self.parent.mesh3d_data_keys_removed_signal.connect(
            self.upd_list_mesh3d_data_keys_mod
        )
        self.parent.mesh3d_data_val_modified_signal.connect(
            self.upd_list_mesh3d_data_val_mod
        )
        self.parent.mesh3d_metadata_modified_signal.connect(
            self.upd_list_mesh3d_metadata_mod
        )
        self.parent.mesh3d_legend_color_modified_signal.connect(
            self.upd_list_mesh3d_leg_col_mod
        )
        self.parent.mesh3d_legend_thick_modified_signal.connect(
            self.upd_list_mesh3d_leg_thick_mod
        )
        self.parent.mesh3d_legend_opacity_modified_signal.connect(
            self.upd_list_mesh3d_leg_op_mod
        )

        # Dom lamda functions and signals
        self.upd_list_dom_add = lambda updated_list: self.dom_added_update_views(
            updated_list=updated_list
        )
        self.upd_list_dom_rm = lambda updated_list: self.dom_removed_update_views(
            updated_list=updated_list
        )
        self.upd_list_dom_data_keys_mod = (
            lambda updated_list: self.dom_data_keys_modified_update_views(
                updated_list=updated_list
            )
        )
        self.upd_list_dom_data_val_mod = (
            lambda updated_list: self.dom_data_val_modified_update_views(
                updated_list=updated_list
            )
        )
        self.upd_list_dom_metadata_mod = (
            lambda updated_list: self.dom_metadata_modified_update_views(
                updated_list=updated_list
            )
        )
        self.upd_list_dom_leg_col_mod = (
            lambda updated_list: self.dom_legend_color_modified_update_views(
                updated_list=updated_list
            )
        )
        self.upd_list_dom_leg_thick_mod = (
            lambda updated_list: self.dom_legend_thick_modified_update_views(
                updated_list=updated_list
            )
        )
        self.upd_list_dom_leg_point_mod = (
            lambda updated_list: self.dom_legend_point_size_modified_update_views(
                updated_list=updated_list
            )
        )
        self.upd_list_dom_leg_op_mod = (
            lambda updated_list: self.dom_legend_opacity_modified_update_views(
                updated_list=updated_list
            )
        )

        self.parent.dom_added_signal.connect(self.upd_list_dom_add)
        self.parent.dom_removed_signal.connect(self.upd_list_dom_rm)
        self.parent.dom_data_keys_removed_signal.connect(
            self.upd_list_dom_data_keys_mod
        )
        self.parent.dom_data_val_modified_signal.connect(self.upd_list_dom_data_val_mod)
        self.parent.dom_metadata_modified_signal.connect(self.upd_list_dom_metadata_mod)
        self.parent.dom_legend_color_modified_signal.connect(
            self.upd_list_dom_leg_col_mod
        )
        self.parent.dom_legend_thick_modified_signal.connect(
            self.upd_list_dom_leg_thick_mod
        )
        self.parent.dom_legend_point_size_modified_signal.connect(
            self.upd_list_dom_leg_point_mod
        )
        self.parent.dom_legend_opacity_modified_signal.connect(
            self.upd_list_dom_leg_op_mod
        )

        # Image lamda functions and signals
        self.upd_list_img_add = lambda updated_list: self.image_added_update_views(
            updated_list=updated_list
        )
        self.upd_list_img_rm = lambda updated_list: self.image_removed_update_views(
            updated_list=updated_list
        )
        self.upd_list_metadata_mod = (
            lambda updated_list: self.image_metadata_modified_update_views(
                updated_list=updated_list
            )
        )
        self.upd_list_img_leg_op_mod = (
            lambda updated_list: self.image_legend_opacity_modified_update_views(
                updated_list=updated_list
            )
        )

        self.parent.image_added_signal.connect(self.upd_list_img_add)
        self.parent.image_removed_signal.connect(self.upd_list_img_rm)
        self.parent.image_metadata_modified_signal.connect(self.upd_list_metadata_mod)
        self.parent.image_legend_opacity_modified_signal.connect(
            self.upd_list_img_leg_op_mod
        )

        # Well lamda functions and signals
        self.upd_list_well_add = lambda updated_list: self.well_added_update_views(
            updated_list=updated_list
        )
        self.upd_list_well_rm = lambda updated_list: self.well_removed_update_views(
            updated_list=updated_list
        )
        self.upd_list_well_data_keys_mod = (
            lambda updated_list: self.well_data_keys_modified_update_views(
                updated_list=updated_list
            )
        )
        self.upd_list_well_data_val_mod = (
            lambda updated_list: self.well_data_val_modified_update_views(
                updated_list=updated_list
            )
        )
        self.upd_list_well_metadata_mod = (
            lambda updated_list: self.well_metadata_modified_update_views(
                updated_list=updated_list
            )
        )
        self.upd_list_well_leg_col_mod = (
            lambda updated_list: self.well_legend_color_modified_update_views(
                updated_list=updated_list
            )
        )
        self.upd_list_well_leg_thick_mod = (
            lambda updated_list: self.well_legend_thick_modified_update_views(
                updated_list=updated_list
            )
        )
        self.upd_list_well_leg_op_mod = (
            lambda updated_list: self.well_legend_opacity_modified_update_views(
                updated_list=updated_list
            )
        )

        self.parent.well_added_signal.connect(self.upd_list_well_add)
        self.parent.well_removed_signal.connect(self.upd_list_well_rm)
        self.parent.well_data_keys_removed_signal.connect(
            self.upd_list_well_data_keys_mod
        )
        self.parent.well_data_val_modified_signal.connect(
            self.upd_list_well_data_val_mod
        )
        self.parent.well_metadata_modified_signal.connect(
            self.upd_list_well_metadata_mod
        )
        self.parent.well_legend_color_modified_signal.connect(
            self.upd_list_well_leg_col_mod
        )
        self.parent.well_legend_thick_modified_signal.connect(
            self.upd_list_well_leg_thick_mod
        )
        self.parent.well_legend_opacity_modified_signal.connect(
            self.upd_list_well_leg_op_mod
        )

        # Fluid lamda functions and signals
        self.upd_list_fluid_add = lambda updated_list: self.fluid_added_update_views(
            updated_list=updated_list
        )
        self.upd_list_fluid_rm = lambda updated_list: self.fluid_removed_update_views(
            updated_list=updated_list
        )
        self.upd_list_fluid_geo_mod = (
            lambda updated_list: self.fluid_geom_modified_update_views(
                updated_list=updated_list
            )
        )
        self.upd_list_fluid_data_keys_mod = (
            lambda updated_list: self.fluid_data_keys_modified_update_views(
                updated_list=updated_list
            )
        )
        self.upd_list_fluid_data_val_mod = (
            lambda updated_list: self.fluid_data_val_modified_update_views(
                updated_list=updated_list
            )
        )
        self.upd_list_fluid_metadata_mod = (
            lambda updated_list: self.fluid_metadata_modified_update_views(
                updated_list=updated_list
            )
        )
        self.upd_list_fluid_leg_col_mod = (
            lambda updated_list: self.fluid_legend_color_modified_update_views(
                updated_list=updated_list
            )
        )
        self.upd_list_fluid_leg_thick_mod = (
            lambda updated_list: self.fluid_legend_thick_modified_update_views(
                updated_list=updated_list
            )
        )
        self.upd_list_fluid_leg_point_mod = (
            lambda updated_list: self.fluid_legend_point_size_modified_update_views(
                updated_list=updated_list
            )
        )
        self.upd_list_fluid_leg_op_mod = (
            lambda updated_list: self.fluid_legend_opacity_modified_update_views(
                updated_list=updated_list
            )
        )

        self.parent.fluid_added_signal.connect(self.upd_list_fluid_add)
        self.parent.fluid_removed_signal.connect(self.upd_list_fluid_rm)
        self.parent.fluid_geom_modified_signal.connect(self.upd_list_fluid_geo_mod)
        self.parent.fluid_data_keys_removed_signal.connect(
            self.upd_list_fluid_data_keys_mod
        )
        self.parent.fluid_data_val_modified_signal.connect(
            self.upd_list_fluid_data_val_mod
        )
        self.parent.fluid_metadata_modified_signal.connect(
            self.upd_list_fluid_metadata_mod
        )
        self.parent.fluid_legend_color_modified_signal.connect(
            self.upd_list_fluid_leg_col_mod
        )
        self.parent.fluid_legend_thick_modified_signal.connect(
            self.upd_list_fluid_leg_thick_mod
        )
        self.parent.fluid_legend_point_size_modified_signal.connect(
            self.upd_list_fluid_leg_point_mod
        )
        self.parent.fluid_legend_opacity_modified_signal.connect(
            self.upd_list_fluid_leg_op_mod
        )

        # Background lamda functions and signals
        self.upd_list_background_add = (
            lambda updated_list: self.background_added_update_views(
                updated_list=updated_list
            )
        )
        self.upd_list_background_rm = (
            lambda updated_list: self.background_removed_update_views(
                updated_list=updated_list
            )
        )
        self.upd_list_background_geo_mod = (
            lambda updated_list: self.background_geom_modified_update_views(
                updated_list=updated_list
            )
        )
        self.upd_list_background_data_keys = (
            lambda updated_list: self.background_data_keys_modified_update_views(
                updated_list=updated_list
            )
        )
        self.upd_list_background_data_val = (
            lambda updated_list: self.background_data_val_modified_update_views(
                updated_list=updated_list
            )
        )
        self.upd_list_background_metadata = (
            lambda updated_list: self.background_metadata_modified_update_views(
                updated_list=updated_list
            )
        )
        self.upd_list_background_leg_col = (
            lambda updated_list: self.background_legend_color_modified_update_views(
                updated_list=updated_list
            )
        )
        self.upd_list_background_leg_thick = (
            lambda updated_list: self.background_legend_thick_modified_update_views(
                updated_list=updated_list
            )
        )
        self.upd_list_background_leg_point = lambda updated_list: self.background_legend_point_size_modified_update_views(
            updated_list=updated_list
        )
        self.upd_list_background_leg_op = (
            lambda updated_list: self.background_legend_opacity_modified_update_views(
                updated_list=updated_list
            )
        )

        self.parent.background_added_signal.connect(self.upd_list_background_add)
        self.parent.background_removed_signal.connect(self.upd_list_background_rm)
        self.parent.background_geom_modified_signal.connect(
            self.upd_list_background_geo_mod
        )
        self.parent.background_data_keys_removed_signal.connect(
            self.upd_list_background_data_keys
        )
        self.parent.background_data_val_modified_signal.connect(
            self.upd_list_background_data_val
        )
        self.parent.background_metadata_modified_signal.connect(
            self.upd_list_background_metadata
        )
        self.parent.background_legend_color_modified_signal.connect(
            self.upd_list_background_leg_col
        )
        self.parent.background_legend_thick_modified_signal.connect(
            self.upd_list_background_leg_thick
        )
        self.parent.background_legend_point_size_modified_signal.connect(
            self.upd_list_background_leg_point
        )
        self.parent.background_legend_opacity_modified_signal.connect(
            self.upd_list_background_leg_op
        )

        # Prop Legend lamda functions and signals
        self.prop_legend_lambda = (
            lambda this_property: self.prop_legend_cmap_modified_update_views(
                this_property=this_property
            )
        )
        self.parent.prop_legend_cmap_modified_signal.connect(self.prop_legend_lambda)

    def show_qt_canvas(self):
        """Show the Qt Window"""
        self.show()
        if isinstance(self, View3D):
            """Turn on the orientation widget AFTER the canvas is shown."""
            self.cam_orient_widget.On()

    # ================================  build and update ================================

    """Methods used to build and update the geology and topology trees."""

    # Help to disconnect all windows signals correctly, if this method is removed it will crash in this case
    def disconnect_all_lambda_signals(self):
        # Disconnect geology signals
        self.parent.geology_added_signal.disconnect(self.upd_list_geo_add)
        self.parent.geology_removed_signal.disconnect(self.upd_list_geo_rm)
        self.parent.geology_geom_modified_signal.disconnect(self.upd_list_geo_mod)
        self.parent.geology_data_keys_removed_signal.disconnect(
            self.upd_list_geo_datakeys_mod
        )
        self.parent.geology_data_val_modified_signal.disconnect(
            self.upd_list_geo_dataval_mod
        )
        self.parent.geology_metadata_modified_signal.disconnect(
            self.upd_list_geo_metadata_mod
        )
        self.parent.geology_legend_color_modified_signal.disconnect(
            self.upd_list_geo_leg_col_mod
        )
        self.parent.geology_legend_thick_modified_signal.disconnect(
            self.upd_list_geo_leg_thick_mod
        )
        self.parent.geology_legend_point_size_modified_signal.disconnect(
            self.upd_list_geo_leg_point_mod
        )
        self.parent.geology_legend_opacity_modified_signal.disconnect(
            self.upd_list_geo_leg_op_mod
        )

        # Disconnect XSect signals
        self.parent.xsect_added_signal.disconnect(self.upd_list_x_add)
        self.parent.xsect_removed_signal.disconnect(self.upd_list_x_rm)
        self.parent.xsect_geom_modified_signal.disconnect(self.upd_list_x_mod)
        self.parent.xsect_metadata_modified_signal.disconnect(
            self.upd_list_x_metadata_mod
        )
        self.parent.xsect_legend_color_modified_signal.disconnect(
            self.upd_list_x_leg_col_mod
        )
        self.parent.xsect_legend_thick_modified_signal.disconnect(
            self.upd_list_x_leg_thick_mod
        )
        self.parent.xsect_legend_opacity_modified_signal.disconnect(
            self.upd_list_x_leg_op_mod
        )

        # Disconnect Boundary signals
        self.parent.boundary_added_signal.disconnect(self.upd_list_bound_add)
        self.parent.boundary_removed_signal.disconnect(self.upd_list_bound_rm)
        self.parent.boundary_geom_modified_signal.disconnect(
            self.upd_list_bound_geo_mod
        )
        self.parent.boundary_metadata_modified_signal.disconnect(
            self.upd_list_bound_metadata_mod
        )
        self.parent.boundary_legend_color_modified_signal.disconnect(
            self.upd_list_bound_leg_col_mod
        )
        self.parent.boundary_legend_thick_modified_signal.disconnect(
            self.upd_list_bound_leg_thick_mod
        )
        self.parent.boundary_legend_opacity_modified_signal.disconnect(
            self.upd_list_bound_leg_op_mod
        )

        # Disconnect Mesh3D signals
        self.parent.mesh3d_added_signal.disconnect(self.upd_list_mesh3d_add)
        self.parent.mesh3d_removed_signal.disconnect(self.upd_list_mesh3d_rm)
        self.parent.mesh3d_data_keys_removed_signal.disconnect(
            self.upd_list_mesh3d_data_keys_mod
        )
        self.parent.mesh3d_data_val_modified_signal.disconnect(
            self.upd_list_mesh3d_data_val_mod
        )
        self.parent.mesh3d_metadata_modified_signal.disconnect(
            self.upd_list_mesh3d_metadata_mod
        )
        self.parent.mesh3d_legend_color_modified_signal.disconnect(
            self.upd_list_mesh3d_leg_col_mod
        )
        self.parent.mesh3d_legend_thick_modified_signal.disconnect(
            self.upd_list_mesh3d_leg_thick_mod
        )
        self.parent.mesh3d_legend_opacity_modified_signal.disconnect(
            self.upd_list_mesh3d_leg_op_mod
        )

        # Disconnect Dom signals
        self.parent.dom_added_signal.disconnect(self.upd_list_dom_add)
        self.parent.dom_removed_signal.disconnect(self.upd_list_dom_rm)
        self.parent.dom_data_keys_removed_signal.disconnect(
            self.upd_list_dom_data_keys_mod
        )
        self.parent.dom_data_val_modified_signal.disconnect(
            self.upd_list_dom_data_val_mod
        )
        self.parent.dom_metadata_modified_signal.disconnect(
            self.upd_list_dom_metadata_mod
        )
        self.parent.dom_legend_color_modified_signal.disconnect(
            self.upd_list_dom_leg_col_mod
        )
        self.parent.dom_legend_thick_modified_signal.disconnect(
            self.upd_list_dom_leg_thick_mod
        )
        self.parent.dom_legend_point_size_modified_signal.disconnect(
            self.upd_list_dom_leg_point_mod
        )
        self.parent.dom_legend_opacity_modified_signal.disconnect(
            self.upd_list_dom_leg_op_mod
        )

        # Disconnect Image signals
        self.parent.image_added_signal.disconnect(self.upd_list_img_add)
        self.parent.image_removed_signal.disconnect(self.upd_list_img_rm)
        self.parent.image_metadata_modified_signal.disconnect(
            self.upd_list_metadata_mod
        )
        self.parent.image_legend_opacity_modified_signal.disconnect(
            self.upd_list_img_leg_op_mod
        )

        # Disconnect Well signals
        self.parent.well_added_signal.disconnect(self.upd_list_well_add)
        self.parent.well_removed_signal.disconnect(self.upd_list_well_rm)
        self.parent.well_data_keys_removed_signal.disconnect(
            self.upd_list_well_data_keys_mod
        )
        self.parent.well_data_val_modified_signal.disconnect(
            self.upd_list_well_data_val_mod
        )
        self.parent.well_metadata_modified_signal.disconnect(
            self.upd_list_well_metadata_mod
        )
        self.parent.well_legend_color_modified_signal.disconnect(
            self.upd_list_well_leg_col_mod
        )
        self.parent.well_legend_thick_modified_signal.disconnect(
            self.upd_list_well_leg_thick_mod
        )
        self.parent.well_legend_opacity_modified_signal.disconnect(
            self.upd_list_well_leg_op_mod
        )

        # Disconnect Fluid signals
        self.parent.fluid_added_signal.disconnect(self.upd_list_fluid_add)
        self.parent.fluid_removed_signal.disconnect(self.upd_list_fluid_rm)
        self.parent.fluid_geom_modified_signal.disconnect(self.upd_list_fluid_geo_mod)
        self.parent.fluid_data_keys_removed_signal.disconnect(
            self.upd_list_fluid_data_keys_mod
        )
        self.parent.fluid_data_val_modified_signal.disconnect(
            self.upd_list_fluid_data_val_mod
        )
        self.parent.fluid_metadata_modified_signal.disconnect(
            self.upd_list_fluid_metadata_mod
        )
        self.parent.fluid_legend_color_modified_signal.disconnect(
            self.upd_list_fluid_leg_col_mod
        )
        self.parent.fluid_legend_thick_modified_signal.disconnect(
            self.upd_list_fluid_leg_thick_mod
        )
        self.parent.fluid_legend_point_size_modified_signal.disconnect(
            self.upd_list_fluid_leg_point_mod
        )
        self.parent.fluid_legend_opacity_modified_signal.disconnect(
            self.upd_list_fluid_leg_op_mod
        )

        # Disconnect Background signals
        self.parent.background_added_signal.disconnect(self.upd_list_background_add)
        self.parent.background_removed_signal.disconnect(self.upd_list_background_rm)
        self.parent.background_geom_modified_signal.disconnect(
            self.upd_list_background_geo_mod
        )
        self.parent.background_data_keys_removed_signal.disconnect(
            self.upd_list_background_data_keys
        )
        self.parent.background_data_val_modified_signal.disconnect(
            self.upd_list_background_data_val
        )
        self.parent.background_metadata_modified_signal.disconnect(
            self.upd_list_background_metadata
        )
        self.parent.background_legend_color_modified_signal.disconnect(
            self.upd_list_background_leg_col
        )
        self.parent.background_legend_thick_modified_signal.disconnect(
            self.upd_list_background_leg_thick
        )
        self.parent.background_legend_point_size_modified_signal.disconnect(
            self.upd_list_background_leg_point
        )
        self.parent.background_legend_opacity_modified_signal.disconnect(
            self.upd_list_background_leg_op
        )

        # Disconnect Prop Legend signals
        self.parent.prop_legend_cmap_modified_signal.disconnect(self.prop_legend_lambda)

    def create_geology_tree(self, sec_uid=None):
        """Create geology tree with checkboxes and properties"""
        self.GeologyTreeWidget.clear()
        self.GeologyTreeWidget.setColumnCount(3)
        self.GeologyTreeWidget.setHeaderLabels(
            ["Type > Feature > Scenario > Name", "uid", "property"]
        )
        self.GeologyTreeWidget.hideColumn(1)  # hide the uid column
        self.GeologyTreeWidget.setItemsExpandable(True)
        if sec_uid:
            geo_types = pd_unique(
                self.parent.geol_coll.df.loc[
                    (self.parent.geol_coll.df["x_section"] == sec_uid),
                    "geological_type",
                ]
            )
        else:
            geo_types = pd_unique(self.parent.geol_coll.df["geological_type"])
        for geo_type in geo_types:
            glevel_1 = QTreeWidgetItem(
                self.GeologyTreeWidget, [geo_type]
            )  # self.GeologyTreeWidget as parent -> top level
            glevel_1.setFlags(
                glevel_1.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
            )
            if sec_uid:
                geo_features = pd_unique(
                    self.parent.geol_coll.df.loc[
                        (self.parent.geol_coll.df["geological_type"] == geo_type)
                        & (self.parent.geol_coll.df["x_section"] == sec_uid),
                        "geological_feature",
                    ]
                )
            else:
                geo_features = pd_unique(
                    self.parent.geol_coll.df.loc[
                        self.parent.geol_coll.df["geological_type"] == geo_type,
                        "geological_feature",
                    ]
                )
            for feature in geo_features:
                glevel_2 = QTreeWidgetItem(
                    glevel_1, [feature]
                )  # glevel_1 as parent -> 1st middle level
                glevel_2.setFlags(
                    glevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
                )
                if sec_uid:
                    geo_scenario = pd_unique(
                        self.parent.geol_coll.df.loc[
                            (self.parent.geol_coll.df["geological_type"] == geo_type)
                            & (
                                self.parent.geol_coll.df["geological_feature"]
                                == feature
                            )
                            & (self.parent.geol_coll.df["x_section"] == sec_uid),
                            "scenario",
                        ]
                    )
                else:
                    geo_scenario = pd_unique(
                        self.parent.geol_coll.df.loc[
                            (self.parent.geol_coll.df["geological_type"] == geo_type)
                            & (
                                self.parent.geol_coll.df["geological_feature"]
                                == feature
                            ),
                            "scenario",
                        ]
                    )
                for scenario in geo_scenario:
                    glevel_3 = QTreeWidgetItem(
                        glevel_2, [scenario]
                    )  # glevel_2 as parent -> 2nd middle level
                    glevel_3.setFlags(
                        glevel_3.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
                    )
                    if sec_uid:
                        uids = self.parent.geol_coll.df.loc[
                            (self.parent.geol_coll.df["geological_type"] == geo_type)
                            & (
                                self.parent.geol_coll.df["geological_feature"]
                                == feature
                            )
                            & (self.parent.geol_coll.df["scenario"] == scenario)
                            & (self.parent.geol_coll.df["x_section"] == sec_uid),
                            "uid",
                        ].to_list()
                    else:
                        uids = self.parent.geol_coll.df.loc[
                            (self.parent.geol_coll.df["geological_type"] == geo_type)
                            & (
                                self.parent.geol_coll.df["geological_feature"]
                                == feature
                            )
                            & (self.parent.geol_coll.df["scenario"] == scenario),
                            "uid",
                        ].to_list()
                    for uid in uids:
                        property_combo = QComboBox()
                        property_combo.uid = uid
                        property_combo.addItem("none")
                        property_combo.addItem("X")
                        property_combo.addItem("Y")
                        property_combo.addItem("Z")
                        for prop in self.parent.geol_coll.get_uid_properties_names(uid):
                            property_combo.addItem(prop)
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
                            lambda: self.toggle_property()
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
        """Send messages. Note that with tristate several signals are emitted in a sequence, one for each
        changed item, but upper levels do not broadcast uid's so they are filtered in the toggle method."""
        self.GeologyTreeWidget.itemChanged.connect(
            self.toggle_geology_topology_visibility
        )
        self.GeologyTreeWidget.expandAll()

    def create_topology_tree(self, sec_uid=None):
        """Create topology tree with checkboxes and properties"""
        self.TopologyTreeWidget.clear()
        self.TopologyTreeWidget.setColumnCount(3)
        self.TopologyTreeWidget.setHeaderLabels(
            ["Type > Scenario > Name", "uid", "property"]
        )
        self.TopologyTreeWidget.hideColumn(1)  # hide the uid column
        self.TopologyTreeWidget.setItemsExpandable(True)

        if sec_uid:
            filtered_topo = self.parent.geol_coll.df.loc[
                (self.parent.geol_coll.df["x_section"] == sec_uid), "topological_type"
            ]
            topo_types = pd_unique(filtered_topo)
        else:
            topo_types = pd_unique(self.parent.geol_coll.df["topological_type"])

        for topo_type in topo_types:
            tlevel_1 = QTreeWidgetItem(
                self.TopologyTreeWidget, [topo_type]
            )  # self.GeologyTreeWidget as parent -> top level
            tlevel_1.setFlags(
                tlevel_1.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
            )
            for scenario in pd_unique(
                self.parent.geol_coll.df.loc[
                    self.parent.geol_coll.df["topological_type"] == topo_type,
                    "scenario",
                ]
            ):
                tlevel_2 = QTreeWidgetItem(
                    tlevel_1, [scenario]
                )  # tlevel_1 as parent -> middle level
                tlevel_2.setFlags(
                    tlevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
                )
                if sec_uid:
                    uids = self.parent.geol_coll.df.loc[
                        (self.parent.geol_coll.df["topological_type"] == topo_type)
                        & (self.parent.geol_coll.df["scenario"] == scenario)
                        & (self.parent.geol_coll.df["x_section"] == sec_uid),
                        "uid",
                    ].to_list()
                else:
                    uids = self.parent.geol_coll.df.loc[
                        (self.parent.geol_coll.df["topological_type"] == topo_type)
                        & (self.parent.geol_coll.df["scenario"] == scenario),
                        "uid",
                    ].to_list()
                for uid in uids:
                    property_combo = QComboBox()
                    property_combo.uid = uid
                    property_combo.addItem("none")
                    property_combo.addItem("X")
                    property_combo.addItem("Y")
                    property_combo.addItem("Z")
                    for prop in self.parent.geol_coll.get_uid_properties_names(uid):
                        property_combo.addItem(prop)
                    name = self.parent.geol_coll.df.loc[
                        self.parent.geol_coll.df["uid"] == uid, "name"
                    ].values[0]
                    tlevel_3 = QTreeWidgetItem(
                        tlevel_2, [name, uid]
                    )  # tlevel_2 as parent -> lower level
                    self.TopologyTreeWidget.setItemWidget(tlevel_3, 2, property_combo)
                    property_combo.currentIndexChanged.connect(
                        lambda: self.toggle_property()
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
        """Send messages. Note that with tristate several signals are emitted in a sequence, one for each
        changed item, but upper levels do not broadcast uid's so they are filtered in the toggle method."""
        self.TopologyTreeWidget.itemChanged.connect(
            self.toggle_geology_topology_visibility
        )
        self.TopologyTreeWidget.expandAll()

    def update_geology_tree_added(self, new_list=None, sec_uid=None):
        """Update geology tree without creating a new model"""
        uid_list = list(new_list["uid"])
        if sec_uid:
            for i, uid in enumerate(new_list["uid"]):
                if (
                    sec_uid
                    != self.parent.geol_coll.df.loc[
                        self.parent.geol_coll.df["uid"] == uid, "x_section"
                    ].values[0]
                ):
                    del uid_list[i]
        for uid in uid_list:
            if (
                self.GeologyTreeWidget.findItems(
                    self.parent.geol_coll.get_uid_geological_type(uid),
                    Qt.MatchExactly,
                    0,
                )
                != []
            ):
                """Already exists a TreeItem (1 level) for the geological type"""
                counter_1 = 0
                for child_1 in range(
                    self.GeologyTreeWidget.findItems(
                        self.parent.geol_coll.get_uid_geological_type(uid),
                        Qt.MatchExactly,
                        0,
                    )[0].childCount()
                ):
                    """for cycle that loops n times as the number of subItems in the specific geological type branch"""
                    if self.GeologyTreeWidget.findItems(
                        self.parent.geol_coll.get_uid_geological_type(uid),
                        Qt.MatchExactly,
                        0,
                    )[0].child(child_1).text(
                        0
                    ) == self.parent.geol_coll.get_uid_geological_feature(
                        uid
                    ):
                        counter_1 += 1
                if counter_1 != 0:
                    for child_1 in range(
                        self.GeologyTreeWidget.findItems(
                            self.parent.geol_coll.get_uid_geological_type(uid),
                            Qt.MatchExactly,
                            0,
                        )[0].childCount()
                    ):
                        if self.GeologyTreeWidget.findItems(
                            self.parent.geol_coll.get_uid_geological_type(uid),
                            Qt.MatchExactly,
                            0,
                        )[0].child(child_1).text(
                            0
                        ) == self.parent.geol_coll.get_uid_geological_feature(
                            uid
                        ):
                            """Already exists a TreeItem (2 level) for the geological feature"""
                            counter_2 = 0
                            for child_2 in range(
                                self.GeologyTreeWidget.itemBelow(
                                    self.GeologyTreeWidget.findItems(
                                        self.parent.geol_coll.get_uid_geological_type(
                                            uid
                                        ),
                                        Qt.MatchExactly,
                                        0,
                                    )[0]
                                ).childCount()
                            ):
                                """for cycle that loops n times as the number of sub-subItems in the specific geological type and geological feature branch"""
                                if self.GeologyTreeWidget.itemBelow(
                                    self.GeologyTreeWidget.findItems(
                                        self.parent.geol_coll.get_uid_geological_type(
                                            uid
                                        ),
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
                                            self.parent.geol_coll.get_uid_geological_type(
                                                uid
                                            ),
                                            Qt.MatchExactly,
                                            0,
                                        )[0]
                                    ).childCount()
                                ):
                                    if self.GeologyTreeWidget.itemBelow(
                                        self.GeologyTreeWidget.findItems(
                                            self.parent.geol_coll.get_uid_geological_type(
                                                uid
                                            ),
                                            Qt.MatchExactly,
                                            0,
                                        )[0]
                                    ).child(child_2).text(
                                        0
                                    ) == self.parent.geol_coll.get_uid_scenario(
                                        uid
                                    ):
                                        """Same geological type, geological feature and scenario"""
                                        property_combo = QComboBox()
                                        property_combo.uid = uid
                                        property_combo.addItem("none")
                                        property_combo.addItem("X")
                                        property_combo.addItem("Y")
                                        property_combo.addItem("Z")
                                        for (
                                            prop
                                        ) in self.parent.geol_coll.get_uid_properties_names(
                                            uid
                                        ):
                                            property_combo.addItem(prop)
                                        name = self.parent.geol_coll.get_uid_name(uid)
                                        glevel_4 = QTreeWidgetItem(
                                            self.GeologyTreeWidget.findItems(
                                                self.parent.geol_coll.get_uid_geological_type(
                                                    uid
                                                ),
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
                                            lambda: self.toggle_property()
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
                                """Same geological type and geological feature, different scenario"""
                                glevel_3 = QTreeWidgetItem(
                                    self.GeologyTreeWidget.findItems(
                                        self.parent.geol_coll.get_uid_geological_type(
                                            uid
                                        ),
                                        Qt.MatchExactly,
                                        0,
                                    )[0].child(child_1),
                                    [self.parent.geol_coll.get_uid_scenario(uid)],
                                )
                                glevel_3.setFlags(
                                    glevel_3.flags()
                                    | Qt.ItemIsTristate
                                    | Qt.ItemIsUserCheckable
                                )
                                self.GeologyTreeWidget.insertTopLevelItem(0, glevel_3)
                                property_combo = QComboBox()
                                property_combo.uid = uid
                                property_combo.addItem("none")
                                property_combo.addItem("X")
                                property_combo.addItem("Y")
                                property_combo.addItem("Z")
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
                                    lambda: self.toggle_property()
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
                    """Same geological type, different geological feature and scenario"""
                    glevel_2 = QTreeWidgetItem(
                        self.GeologyTreeWidget.findItems(
                            self.parent.geol_coll.get_uid_geological_type(uid),
                            Qt.MatchExactly,
                            0,
                        )[0],
                        [self.parent.geol_coll.get_uid_geological_feature(uid)],
                    )
                    glevel_2.setFlags(
                        glevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
                    )
                    self.GeologyTreeWidget.insertTopLevelItem(0, glevel_2)
                    glevel_3 = QTreeWidgetItem(
                        glevel_2, [self.parent.geol_coll.get_uid_scenario(uid)]
                    )
                    glevel_3.setFlags(
                        glevel_3.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
                    )
                    self.GeologyTreeWidget.insertTopLevelItem(0, glevel_3)
                    property_combo = QComboBox()
                    property_combo.uid = uid
                    property_combo.addItem("none")
                    property_combo.addItem("X")
                    property_combo.addItem("Y")
                    property_combo.addItem("Z")
                    for prop in self.parent.geol_coll.get_uid_properties_names(uid):
                        property_combo.addItem(prop)
                    name = self.parent.geol_coll.get_uid_name(uid)
                    glevel_4 = QTreeWidgetItem(glevel_3, [name, uid])
                    self.GeologyTreeWidget.setItemWidget(glevel_4, 2, property_combo)
                    property_combo.currentIndexChanged.connect(
                        lambda: self.toggle_property()
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
                """Different geological type, geological feature and scenario"""
                glevel_1 = QTreeWidgetItem(
                    self.GeologyTreeWidget,
                    [self.parent.geol_coll.get_uid_geological_type(uid)],
                )
                glevel_1.setFlags(
                    glevel_1.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
                )
                self.GeologyTreeWidget.insertTopLevelItem(0, glevel_1)
                glevel_2 = QTreeWidgetItem(
                    glevel_1, [self.parent.geol_coll.get_uid_geological_feature(uid)]
                )
                glevel_2.setFlags(
                    glevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
                )
                self.GeologyTreeWidget.insertTopLevelItem(0, glevel_2)
                glevel_3 = QTreeWidgetItem(
                    glevel_2, [self.parent.geol_coll.get_uid_scenario(uid)]
                )
                glevel_3.setFlags(
                    glevel_3.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
                )
                self.GeologyTreeWidget.insertTopLevelItem(0, glevel_3)
                property_combo = QComboBox()
                property_combo.uid = uid
                property_combo.addItem("none")
                property_combo.addItem("X")
                property_combo.addItem("Y")
                property_combo.addItem("Z")
                for prop in self.parent.geol_coll.get_uid_properties_names(uid):
                    property_combo.addItem(prop)
                name = self.parent.geol_coll.get_uid_name(uid)
                glevel_4 = QTreeWidgetItem(glevel_3, [name, uid])
                self.GeologyTreeWidget.setItemWidget(glevel_4, 2, property_combo)
                property_combo.currentIndexChanged.connect(
                    lambda: self.toggle_property()
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
        self.GeologyTreeWidget.itemChanged.connect(
            self.toggle_geology_topology_visibility
        )
        self.GeologyTreeWidget.expandAll()

    def update_geology_tree_removed(self, removed_list=None):  # second attempt
        """When geological entity is removed, update Geology Tree without building a new model"""
        success = 0
        for uid in removed_list:
            for top_geo_type in range(self.GeologyTreeWidget.topLevelItemCount()):
                """Iterate through every Geological Type top level"""
                for child_geo_feat in range(
                    self.GeologyTreeWidget.topLevelItem(top_geo_type).childCount()
                ):
                    """Iterate through every Geological Feature child"""
                    for child_scenario in range(
                        self.GeologyTreeWidget.topLevelItem(top_geo_type)
                        .child(child_geo_feat)
                        .childCount()
                    ):
                        """Iterate through every Scenario child"""
                        for child_entity in range(
                            self.GeologyTreeWidget.topLevelItem(top_geo_type)
                            .child(child_geo_feat)
                            .child(child_scenario)
                            .childCount()
                        ):
                            """Iterate through every Entity child"""
                            if (
                                self.GeologyTreeWidget.topLevelItem(top_geo_type)
                                .child(child_geo_feat)
                                .child(child_scenario)
                                .child(child_entity)
                                .text(1)
                                == uid
                            ):
                                """Complete check: entity found has the uid of the entity we need to remove. Delete child, then ensure no Child or Top Level remain empty"""
                                success = 1
                                self.GeologyTreeWidget.topLevelItem(top_geo_type).child(
                                    child_geo_feat
                                ).child(child_scenario).removeChild(
                                    self.GeologyTreeWidget.topLevelItem(top_geo_type)
                                    .child(child_geo_feat)
                                    .child(child_scenario)
                                    .child(child_entity)
                                )
                                if (
                                    self.GeologyTreeWidget.topLevelItem(top_geo_type)
                                    .child(child_geo_feat)
                                    .child(child_scenario)
                                    .childCount()
                                    == 0
                                ):
                                    self.GeologyTreeWidget.topLevelItem(
                                        top_geo_type
                                    ).child(child_geo_feat).removeChild(
                                        self.GeologyTreeWidget.topLevelItem(
                                            top_geo_type
                                        )
                                        .child(child_geo_feat)
                                        .child(child_scenario)
                                    )
                                    if (
                                        self.GeologyTreeWidget.topLevelItem(
                                            top_geo_type
                                        )
                                        .child(child_geo_feat)
                                        .childCount()
                                        == 0
                                    ):
                                        self.GeologyTreeWidget.topLevelItem(
                                            top_geo_type
                                        ).removeChild(
                                            self.GeologyTreeWidget.topLevelItem(
                                                top_geo_type
                                            ).child(child_geo_feat)
                                        )
                                        if (
                                            self.GeologyTreeWidget.topLevelItem(
                                                top_geo_type
                                            ).childCount()
                                            == 0
                                        ):
                                            self.GeologyTreeWidget.takeTopLevelItem(
                                                top_geo_type
                                            )
                                break
                        if success == 1:
                            break
                    if success == 1:
                        break
                if success == 1:
                    break

    def update_topology_tree_added(self, new_list=None, sec_uid=None):
        """Update topology tree without creating a new model"""
        uid_list = list(new_list["uid"])
        if sec_uid:
            for i, uid in enumerate(new_list["uid"]):
                if (
                    sec_uid
                    != self.parent.geol_coll.df.loc[
                        self.parent.geol_coll.df["uid"] == uid, "x_section"
                    ].values[0]
                ):
                    del uid_list[i]
        for uid in uid_list:
            if (
                self.TopologyTreeWidget.findItems(
                    self.parent.geol_coll.get_uid_topological_type(uid),
                    Qt.MatchExactly,
                    0,
                )
                != []
            ):
                """Already exists a TreeItem (1 level) for the topological type"""
                counter_1 = 0
                for child_1 in range(
                    self.TopologyTreeWidget.findItems(
                        self.parent.geol_coll.get_uid_topological_type(uid),
                        Qt.MatchExactly,
                        0,
                    )[0].childCount()
                ):
                    """for cycle that loops n times as the number of subItems in the specific topological type branch"""
                    if self.TopologyTreeWidget.findItems(
                        self.parent.geol_coll.get_uid_topological_type(uid),
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
                        self.TopologyTreeWidget.findItems(
                            self.parent.geol_coll.get_uid_topological_type(uid),
                            Qt.MatchExactly,
                            0,
                        )[0].childCount()
                    ):
                        if self.TopologyTreeWidget.findItems(
                            self.parent.geol_coll.get_uid_topological_type(uid),
                            Qt.MatchExactly,
                            0,
                        )[0].child(child_1).text(
                            0
                        ) == self.parent.geol_coll.get_uid_scenario(
                            uid
                        ):
                            """Same topological type and scenario"""
                            property_combo = QComboBox()
                            property_combo.uid = uid
                            property_combo.addItem("none")
                            property_combo.addItem("X")
                            property_combo.addItem("Y")
                            property_combo.addItem("Z")
                            for prop in self.parent.geol_coll.get_uid_properties_names(
                                uid
                            ):
                                property_combo.addItem(prop)
                            name = self.parent.geol_coll.get_uid_name(uid)
                            tlevel_3 = QTreeWidgetItem(
                                self.TopologyTreeWidget.findItems(
                                    self.parent.geol_coll.get_uid_topological_type(uid),
                                    Qt.MatchExactly,
                                    0,
                                )[0].child(child_1),
                                [name, uid],
                            )
                            self.TopologyTreeWidget.setItemWidget(
                                tlevel_3, 2, property_combo
                            )
                            property_combo.currentIndexChanged.connect(
                                lambda: self.toggle_property()
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
                            self.TopologyTreeWidget.insertTopLevelItem(0, tlevel_3)
                            break
                else:
                    """Same topological type, different scenario"""
                    tlevel_2 = QTreeWidgetItem(
                        self.TopologyTreeWidget.findItems(
                            self.parent.geol_coll.get_uid_topological_type(uid),
                            Qt.MatchExactly,
                            0,
                        )[0],
                        [self.parent.geol_coll.get_uid_scenario(uid)],
                    )
                    tlevel_2.setFlags(
                        tlevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
                    )
                    self.TopologyTreeWidget.insertTopLevelItem(0, tlevel_2)
                    property_combo = QComboBox()
                    property_combo.uid = uid
                    property_combo.addItem("none")
                    property_combo.addItem("X")
                    property_combo.addItem("Y")
                    property_combo.addItem("Z")
                    for prop in self.parent.geol_coll.get_uid_properties_names(uid):
                        property_combo.addItem(prop)
                    name = self.parent.geol_coll.get_uid_name(uid)
                    tlevel_3 = QTreeWidgetItem(tlevel_2, [name, uid])
                    self.TopologyTreeWidget.setItemWidget(tlevel_3, 2, property_combo)
                    property_combo.currentIndexChanged.connect(
                        lambda: self.toggle_property()
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
                    self.TopologyTreeWidget.insertTopLevelItem(0, tlevel_3)
                    break
            else:
                """Different topological type and scenario"""
                tlevel_1 = QTreeWidgetItem(
                    self.TopologyTreeWidget,
                    [self.parent.geol_coll.get_uid_topological_type(uid)],
                )
                tlevel_1.setFlags(
                    tlevel_1.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
                )
                self.TopologyTreeWidget.insertTopLevelItem(0, tlevel_1)
                tlevel_2 = QTreeWidgetItem(
                    tlevel_1, [self.parent.geol_coll.get_uid_scenario(uid)]
                )
                tlevel_2.setFlags(
                    tlevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
                )
                self.TopologyTreeWidget.insertTopLevelItem(0, tlevel_2)
                property_combo = QComboBox()
                property_combo.uid = uid
                property_combo.addItem("none")
                property_combo.addItem("X")
                property_combo.addItem("Y")
                property_combo.addItem("Z")
                for prop in self.parent.geol_coll.get_uid_properties_names(uid):
                    property_combo.addItem(prop)
                name = self.parent.geol_coll.get_uid_name(uid)
                tlevel_3 = QTreeWidgetItem(tlevel_2, [name, uid])
                self.TopologyTreeWidget.setItemWidget(tlevel_3, 2, property_combo)
                property_combo.currentIndexChanged.connect(
                    lambda: self.toggle_property()
                )
                tlevel_3.setFlags(tlevel_3.flags() | Qt.ItemIsUserCheckable)
                if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                    tlevel_3.setCheckState(0, Qt.Checked)
                elif not self.actors_df.loc[
                    self.actors_df["uid"] == uid, "show"
                ].values[0]:
                    tlevel_3.setCheckState(0, Qt.Unchecked)
                self.TopologyTreeWidget.insertTopLevelItem(0, tlevel_3)
                break
        self.TopologyTreeWidget.itemChanged.connect(
            self.toggle_geology_topology_visibility
        )
        self.TopologyTreeWidget.expandAll()

    def update_topology_tree_removed(self, removed_list=None):
        """When geological entity is removed, update Topology Tree without building a new model"""
        success = 0
        for uid in removed_list:
            for top_topo_type in range(self.TopologyTreeWidget.topLevelItemCount()):
                """Iterate through every Topological Type top level"""
                for child_scenario in range(
                    self.TopologyTreeWidget.topLevelItem(top_topo_type).childCount()
                ):
                    """Iterate through every Scenario child"""
                    for child_entity in range(
                        self.TopologyTreeWidget.topLevelItem(top_topo_type)
                        .child(child_scenario)
                        .childCount()
                    ):
                        """Iterate through every Entity child"""
                        if (
                            self.TopologyTreeWidget.topLevelItem(top_topo_type)
                            .child(child_scenario)
                            .child(child_entity)
                            .text(1)
                            == uid
                        ):
                            """Complete check: entity found has the uid of the entity we need to remove. Delete child, then ensure no Child or Top Level remain empty"""
                            success = 1
                            self.TopologyTreeWidget.topLevelItem(top_topo_type).child(
                                child_scenario
                            ).removeChild(
                                self.TopologyTreeWidget.topLevelItem(top_topo_type)
                                .child(child_scenario)
                                .child(child_entity)
                            )
                            if (
                                self.TopologyTreeWidget.topLevelItem(top_topo_type)
                                .child(child_scenario)
                                .childCount()
                                == 0
                            ):
                                self.TopologyTreeWidget.topLevelItem(
                                    top_topo_type
                                ).removeChild(
                                    self.TopologyTreeWidget.topLevelItem(
                                        top_topo_type
                                    ).child(child_scenario)
                                )
                                if (
                                    self.TopologyTreeWidget.topLevelItem(
                                        top_topo_type
                                    ).childCount()
                                    == 0
                                ):
                                    self.TopologyTreeWidget.takeTopLevelItem(
                                        top_topo_type
                                    )
                            break
                    if success == 1:
                        break
                if success == 1:
                    break

    def update_geology_checkboxes(self, uid=None, uid_checkState=None):
        """Update checkboxes in geology tree, called when state changed in topology tree."""
        item = self.GeologyTreeWidget.findItems(
            uid, Qt.MatchFixedString | Qt.MatchRecursive, 1
        )[0]
        if uid_checkState == Qt.Checked:
            item.setCheckState(0, Qt.Checked)
        elif uid_checkState == Qt.Unchecked:
            item.setCheckState(0, Qt.Unchecked)

    def update_topology_checkboxes(self, uid=None, uid_checkState=None):
        """Update checkboxes in topology tree, called when state changed in geology tree."""
        item = self.TopologyTreeWidget.findItems(
            uid, Qt.MatchFixedString | Qt.MatchRecursive, 1
        )[0]
        if uid_checkState == Qt.Checked:
            item.setCheckState(0, Qt.Checked)
        elif uid_checkState == Qt.Unchecked:
            item.setCheckState(0, Qt.Unchecked)

    def toggle_geology_topology_visibility(self, item, column):
        """Called by self.GeologyTreeWidget.itemChanged.connect(self.toggle_geology_topology_visibility) and self.TopologyTreeWidget.itemChanged.connect(self.toggle_geology_topology_visibility)"""
        name = item.text(0)  # not used
        uid = item.text(1)
        uid_checkState = item.checkState(0)
        if (
            uid
        ):  # needed to skip messages from upper levels of tree that do not broadcast uid's
            if uid_checkState == Qt.Checked:
                if not self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[
                    0
                ]:
                    self.actors_df.loc[self.actors_df["uid"] == uid, "show"] = True
                    self.set_actor_visible(uid=uid, visible=True)
            elif uid_checkState == Qt.Unchecked:
                if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                    self.actors_df.loc[self.actors_df["uid"] == uid, "show"] = False
                    self.set_actor_visible(uid=uid, visible=False)
            """Before updating checkboxes, disconnect signals to geology and topology tree, if they are set,
            to avoid a nasty loop that disrupts the trees, then reconnect them (it is also possible that
            they are automatically reconnected whe the trees are rebuilt."""
            self.GeologyTreeWidget.itemChanged.disconnect()
            self.TopologyTreeWidget.itemChanged.disconnect()
            self.update_geology_checkboxes(uid=uid, uid_checkState=uid_checkState)
            self.update_topology_checkboxes(uid=uid, uid_checkState=uid_checkState)
            self.GeologyTreeWidget.itemChanged.connect(
                self.toggle_geology_topology_visibility
            )
            self.TopologyTreeWidget.itemChanged.connect(
                self.toggle_geology_topology_visibility
            )

    """Methods used to build and update the cross-section table."""

    def create_xsections_tree(self, sec_uid=None):
        """Create XSection tree with checkboxes and properties"""
        self.XSectionTreeWidget.clear()
        self.XSectionTreeWidget.setColumnCount(2)
        self.XSectionTreeWidget.setHeaderLabels(["Name", "uid"])
        self.XSectionTreeWidget.hideColumn(1)  # hide the uid column
        self.XSectionTreeWidget.setItemsExpandable(True)
        name_xslevel1 = ["All XSections"]
        xslevel_1 = QTreeWidgetItem(
            self.XSectionTreeWidget, name_xslevel1
        )  # self.XSectionTreeWidget as parent -> top level
        xslevel_1.setFlags(
            xslevel_1.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
        )
        if sec_uid:
            uids = self.parent.xsect_coll.df.loc[
                self.parent.xsect_coll.df["uid"] == sec_uid, "uid"
            ].to_list()
        else:
            uids = self.parent.xsect_coll.df["uid"].to_list()
        for uid in uids:
            name = self.parent.xsect_coll.df.loc[
                self.parent.xsect_coll.df["uid"] == uid, "name"
            ].values[0]
            xslevel_2 = QTreeWidgetItem(
                xslevel_1, [name, uid]
            )  # xslevel_2 as parent -> lower level
            xslevel_2.setFlags(xslevel_2.flags() | Qt.ItemIsUserCheckable)
            if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                xslevel_2.setCheckState(0, Qt.Checked)
            elif not self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                xslevel_2.setCheckState(0, Qt.Unchecked)
        """Send messages. Note that with tristate several signals are emitted in a sequence, one for each
        changed item, but upper levels do not broadcast uid's so they are filtered in the toggle method."""
        self.XSectionTreeWidget.itemChanged.connect(self.toggle_xsection_visibility)
        self.XSectionTreeWidget.expandAll()

    def update_xsections_tree_added(self, new_list=None, sec_uid=None):
        """Update XSection tree without creating a new model"""
        uid_list = list(new_list["uid"])
        if sec_uid:
            for i, uid in enumerate(new_list["uid"]):
                if sec_uid != uid:
                    del uid_list[i]
        for uid in uid_list:
            name = self.parent.xsect_coll.get_uid_name(uid)
            xslevel_2 = QTreeWidgetItem(
                self.XSectionTreeWidget.findItems("All XSections", Qt.MatchExactly, 0)[
                    0
                ],
                [name, uid],
            )
            xslevel_2.setFlags(xslevel_2.flags() | Qt.ItemIsUserCheckable)
            if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                xslevel_2.setCheckState(0, Qt.Checked)
            elif not self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                xslevel_2.setCheckState(0, Qt.Unchecked)
        self.XSectionTreeWidget.itemChanged.connect(self.toggle_xsection_visibility)
        self.XSectionTreeWidget.expandAll()

    def update_xsections_tree_removed(self, removed_list=None):
        """Update XSection tree without creating a new model"""
        success = 0
        for uid in removed_list:
            for top_box in range(self.XSectionTreeWidget.topLevelItemCount()):
                """Iterate through every Collection top level"""
                for child_xsect in range(
                    self.XSectionTreeWidget.topLevelItem(top_box).childCount()
                ):
                    """Iterate through every XSection"""
                    if (
                        self.XSectionTreeWidget.topLevelItem(top_box)
                        .child(child_xsect)
                        .text(1)
                        == uid
                    ):
                        """Complete check: entity found has the uid of the entity we need to remove. Delete child"""
                        success = 1
                        self.XSectionTreeWidget.topLevelItem(top_box).removeChild(
                            self.XSectionTreeWidget.topLevelItem(top_box).child(
                                child_xsect
                            )
                        )
                        break
                if success == 1:
                    break

    def update_xsection_checkboxes(self, uid=None, uid_checkState=None):
        """Update checkboxes in XSection tree, called when state changed in xsection tree."""
        item = self.XSectionTreeWidget.findItems(
            uid, Qt.MatchFixedString | Qt.MatchRecursive, 1
        )[0]
        if uid_checkState == Qt.Checked:
            item.setCheckState(0, Qt.Checked)
        elif uid_checkState == Qt.Unchecked:
            item.setCheckState(0, Qt.Unchecked)

    def toggle_xsection_visibility(self, item, column):
        """Called by self.XSectionTreeWidget.itemChanged.connect(self.toggle_xsection_visibility)."""
        name = item.text(0)  # not used
        uid = item.text(1)
        uid_checkState = item.checkState(0)
        if (
            uid
        ):  # needed to skip messages from upper levels of tree that do not broadcast uid's
            if uid_checkState == Qt.Checked:
                if not self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[
                    0
                ]:
                    self.actors_df.loc[self.actors_df["uid"] == uid, "show"] = True
                    self.set_actor_visible(uid=uid, visible=True)
            elif uid_checkState == Qt.Unchecked:
                if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                    self.actors_df.loc[self.actors_df["uid"] == uid, "show"] = False
                    self.set_actor_visible(uid=uid, visible=False)
            """Before updating checkboxes, disconnect signals to xsection tree, if they are set,
            to avoid a nasty loop that disrupts the trees, then reconnect them (it is also possible that
            they are automatically reconnected whe the trees are rebuilt."""
            self.XSectionTreeWidget.itemChanged.disconnect()
            self.update_xsection_checkboxes(uid=uid, uid_checkState=uid_checkState)
            self.XSectionTreeWidget.itemChanged.connect(self.toggle_xsection_visibility)

    """Methods used to build and update the Boundary table."""

    def create_boundary_list(self, sec_uid=None):
        """Create boundaries list with checkboxes."""
        self.BoundariesTableWidget.clear()
        self.BoundariesTableWidget.setColumnCount(2)
        self.BoundariesTableWidget.setRowCount(0)
        self.BoundariesTableWidget.setHorizontalHeaderLabels(["Name", "uid"])
        self.BoundariesTableWidget.hideColumn(1)  # hide the uid column
        if sec_uid:
            uids = self.parent.boundary_coll.df.loc[
                (self.parent.boundary_coll.df["x_section"] == sec_uid), "uid"
            ].to_list()
        else:
            uids = self.parent.boundary_coll.df["uid"].to_list()
        row = 0
        for uid in uids:
            name = self.parent.boundary_coll.df.loc[
                self.parent.boundary_coll.df["uid"] == uid, "name"
            ].values[0]
            name_item = QTableWidgetItem(name)
            name_item.setFlags(name_item.flags() | Qt.ItemIsUserCheckable)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            uid_item = QTableWidgetItem(uid)
            self.BoundariesTableWidget.insertRow(row)
            self.BoundariesTableWidget.setItem(row, 0, name_item)
            self.BoundariesTableWidget.setItem(row, 1, uid_item)
            if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                name_item.setCheckState(Qt.Checked)
            elif not self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                name_item.setCheckState(Qt.Unchecked)
            row += 1
        """Send message with argument = the cell being checked/unchecked."""
        self.BoundariesTableWidget.itemChanged.connect(self.toggle_boundary_visibility)

    def update_boundary_list_added(self, new_list=None, sec_uid=None):
        """Update boundaries list without creating a new model"""
        row = self.BoundariesTableWidget.rowCount()
        if sec_uid:
            uids = self.parent.boundary_coll.df.loc[
                (self.parent.boundary_coll.df["x_section"] == sec_uid), "uid"
            ].to_list()
        else:
            uids = self.parent.boundary_coll.df["uid"].to_list()
        for uid in uids:
            name = self.parent.boundary_coll.df.loc[
                self.parent.boundary_coll.df["uid"] == uid, "name"
            ].values[0]
            name_item = QTableWidgetItem(name)
            name_item.setFlags(name_item.flags() | Qt.ItemIsUserCheckable)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            uid_item = QTableWidgetItem(uid)
            self.BoundariesTableWidget.insertRow(row)
            self.BoundariesTableWidget.setItem(row, 0, name_item)
            self.BoundariesTableWidget.setItem(row, 1, uid_item)
            if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                name_item.setCheckState(Qt.Checked)
            elif not self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                name_item.setCheckState(Qt.Unchecked)
            row += 1
        """Send message with argument = the cell being checked/unchecked."""
        self.BoundariesTableWidget.itemChanged.connect(self.toggle_boundary_visibility)

    def update_boundary_list_removed(self, removed_list=None):
        """Update boundary list without creating a new model"""
        for uid in removed_list:
            for row in range(self.BoundariesTableWidget.rowCount()):
                """Iterate through each row of the QTableWidget to find the row with the corresponding entity"""
                if self.BoundariesTableWidget.item(row, 1).text() == uid:
                    """Row found: delete row"""
                    self.BoundariesTableWidget.removeRow(row)
                    row -= 1
                    break
        """Send message with argument = the cell being checked/unchecked."""
        self.BoundariesTableWidget.itemChanged.connect(self.toggle_boundary_visibility)

    def toggle_boundary_visibility(self, cell):
        """Called by self.BoundariesTableWidget.itemChanged.connect(self.toggle_boundary_visibility)."""
        check_state = self.BoundariesTableWidget.item(
            cell.row(), 0
        ).checkState()  # this is the check state of cell "name"
        uid = self.BoundariesTableWidget.item(
            cell.row(), 1
        ).text()  # this is the text of cell "uid"
        if check_state == Qt.Checked:
            if not self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                self.actors_df.loc[self.actors_df["uid"] == uid, "show"] = True
                self.set_actor_visible(uid=uid, visible=True)
        elif check_state == Qt.Unchecked:
            if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                self.actors_df.loc[self.actors_df["uid"] == uid, "show"] = False
                self.set_actor_visible(uid=uid, visible=False)

    """Methods used to build and update the Mesh3D table."""

    def create_mesh3d_list(self, sec_uid=None):
        """Create mesh3D list with checkboxes."""
        self.Mesh3DTableWidget.clear()
        self.Mesh3DTableWidget.setColumnCount(3)
        self.Mesh3DTableWidget.setRowCount(0)
        self.Mesh3DTableWidget.setHorizontalHeaderLabels(["Name", "uid"])
        self.Mesh3DTableWidget.hideColumn(1)  # hide the uid column
        if sec_uid:
            uids = self.parent.mesh3d_coll.df.loc[
                (self.parent.mesh3d_coll.df["x_section"] == sec_uid), "uid"
            ].to_list()
        else:
            uids = self.parent.mesh3d_coll.df["uid"].to_list()
        row = 0
        for uid in uids:
            name = self.parent.mesh3d_coll.df.loc[
                self.parent.mesh3d_coll.df["uid"] == uid, "name"
            ].values[0]
            name_item = QTableWidgetItem(name)
            name_item.setFlags(name_item.flags() | Qt.ItemIsUserCheckable)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            uid_item = QTableWidgetItem(uid)
            property_combo = QComboBox()
            property_combo.uid = uid
            property_combo.addItem("none")
            property_combo.texture_uid_list = ["none", "X", "Y", "Z"]
            property_combo.addItem("X")
            property_combo.addItem("Y")
            property_combo.addItem("Z")
            for prop in self.parent.mesh3d_coll.get_uid_properties_names(uid):
                property_combo.addItem(prop)
            self.Mesh3DTableWidget.insertRow(row)
            self.Mesh3DTableWidget.setItem(row, 0, name_item)
            self.Mesh3DTableWidget.setItem(row, 1, uid_item)
            self.Mesh3DTableWidget.setCellWidget(row, 2, property_combo)
            property_combo.currentIndexChanged.connect(
                lambda: self.toggle_property_mesh3d()
            )
            if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                name_item.setCheckState(Qt.Checked)
            elif not self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                name_item.setCheckState(Qt.Unchecked)
            row += 1
        """Send message with argument = the cell being checked/unchecked."""
        self.Mesh3DTableWidget.itemChanged.connect(self.toggle_mesh3d_visibility)

    def update_mesh3d_list_added(self, new_list=None, sec_uid=None):
        """Update Mesh3D list without creating a new model"""
        row = self.Mesh3DTableWidget.rowCount()
        uid_list = list(new_list["uid"])
        if sec_uid:
            for i, uid in enumerate(new_list["uid"]):
                if (
                    sec_uid
                    != self.parent.mesh3d_coll.df.loc[
                        self.parent.mesh3d_coll.df["uid"] == uid, "x_section"
                    ].values[0]
                ):
                    del uid_list[i]
        for uid in uid_list:
            name = self.parent.mesh3d_coll.df.loc[
                self.parent.mesh3d_coll.df["uid"] == uid, "name"
            ].values[0]
            name_item = QTableWidgetItem(name)
            name_item.setFlags(name_item.flags() | Qt.ItemIsUserCheckable)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            uid_item = QTableWidgetItem(uid)
            property_combo = QComboBox()
            property_combo.uid = uid
            property_combo.addItem("none")
            property_combo.texture_uid_list = ["none", "X", "Y", "Z"]
            property_combo.addItem("X")
            property_combo.addItem("Y")
            property_combo.addItem("Z")
            for prop in self.parent.mesh3d_coll.get_uid_properties_names(uid):
                property_combo.addItem(prop)
            self.Mesh3DTableWidget.insertRow(row)
            self.Mesh3DTableWidget.setItem(row, 0, name_item)
            self.Mesh3DTableWidget.setItem(row, 1, uid_item)
            self.Mesh3DTableWidget.setCellWidget(row, 2, property_combo)
            property_combo.currentIndexChanged.connect(
                lambda: self.toggle_property_mesh3d()
            )
            if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                name_item.setCheckState(Qt.Checked)
            elif not self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                name_item.setCheckState(Qt.Unchecked)
            row += 1
        """Send message with argument = the cell being checked/unchecked."""
        self.Mesh3DTableWidget.itemChanged.connect(self.toggle_mesh3d_visibility)

    def update_mesh3d_list_removed(self, removed_list=None):
        """Update Mesh3D list without creating a new model"""
        for uid in removed_list:
            for row in range(self.Mesh3DTableWidget.rowCount()):
                """Iterate through each row of the QTableWidget to find the row with the corresponding entity"""
                if self.Mesh3DTableWidget.item(row, 1).text() == uid:
                    """Row found: delete row"""
                    self.Mesh3DTableWidget.removeRow(row)
                    row -= 1
                    break
        """Send message with argument = the cell being checked/unchecked."""
        self.Mesh3DTableWidget.itemChanged.connect(self.toggle_dom_visibility)

    def toggle_mesh3d_visibility(self, cell):
        """Called by self.Mesh3DTableWidget.itemChanged.connect(self.toggle_mesh3d_visibility)."""
        check_state = self.Mesh3DTableWidget.item(
            cell.row(), 0
        ).checkState()  # this is the check state of cell "name"
        uid = self.Mesh3DTableWidget.item(
            cell.row(), 1
        ).text()  # this is the text of cell "uid"
        if check_state == Qt.Checked:
            if not self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                self.actors_df.loc[self.actors_df["uid"] == uid, "show"] = True
                self.set_actor_visible(uid=uid, visible=True)
        elif check_state == Qt.Unchecked:
            if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                self.actors_df.loc[self.actors_df["uid"] == uid, "show"] = False
                self.set_actor_visible(uid=uid, visible=False)

    def toggle_property_mesh3d(self):
        """Method to toggle the texture shown by a Mesh3D that is already present in the view."""
        """Collect values from combo box."""
        combo = self.sender()
        show_property = combo.currentText()
        uid = combo.uid
        show = self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]
        collection = self.actors_df.loc[
            self.actors_df["uid"] == uid, "collection"
        ].values[0]
        """This removes the previous copy of the actor with the same uid, then calls the viewer-specific function that shows an actor with a property.
        IN THE FUTURE see if it is possible and more efficient to keep the actor and just change the property shown."""
        self.remove_actor_in_view(uid=uid)
        this_actor = self.show_actor_with_property(
            uid=uid, collection=collection, show_property=show_property, visible=show
        )
        self.actors_df = self.actors_df.append(
            {
                "uid": uid,
                "actor": this_actor,
                "show": show,
                "collection": collection,
                "show_prop": show_property,
            },
            ignore_index=True,
        )  # self.set_actor_visible(uid=uid, visible=show)

    """Methods used to build and update the DOM table."""

    def create_dom_list(self, sec_uid=None):
        """Create cross-sections list with checkboxes."""
        self.DOMsTableWidget.clear()
        self.DOMsTableWidget.setColumnCount(3)
        self.DOMsTableWidget.setRowCount(0)
        self.DOMsTableWidget.setHorizontalHeaderLabels(["Name", "uid", "Show property"])
        self.DOMsTableWidget.hideColumn(1)  # hide the uid column
        row = 0
        if sec_uid:
            uids = self.parent.dom_coll.df.loc[
                (self.parent.dom_coll.df["x_section"] == sec_uid), "uid"
            ].to_list()
        else:
            uids = self.parent.dom_coll.df["uid"].to_list()
        for uid in uids:
            # print(self.parent.dom_coll.df.loc[self.parent.dom_coll.df['uid'] == uid, 'name'])
            name = self.parent.dom_coll.df.loc[
                self.parent.dom_coll.df["uid"] == uid, "name"
            ].values[0]
            name_item = QTableWidgetItem(name)
            name_item.setFlags(name_item.flags() | Qt.ItemIsUserCheckable)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            uid_item = QTableWidgetItem(uid)
            property_texture_combo = QComboBox()
            property_texture_combo.uid = uid
            property_texture_combo.addItem("none")
            property_texture_combo.texture_uid_list = ["none", "X", "Y", "Z"]
            property_texture_combo.addItem("X")
            property_texture_combo.addItem("Y")
            property_texture_combo.addItem("Z")
            # property_texture_combo.addItem("RGB")

            """[Gabriele] To add support to multi components properties (e.g. RGB) we can add a component check (if components > 1). If this statement is True we can iterate over the n components and set the new n properties using the template prop[n_component]. These properties do not point to actual data (the "RGB[0]" property is not present) but to a slice of the original property (RGB[:,0])."""

            for prop, components in zip(
                self.parent.dom_coll.get_uid_properties_names(uid),
                self.parent.dom_coll.get_uid_properties_components(uid),
            ):
                if (
                    prop
                    not in self.parent.dom_coll.df.loc[
                        self.parent.dom_coll.df["uid"] == uid, "texture_uids"
                    ].values[0]
                ):
                    property_texture_combo.addItem(prop)
                    property_texture_combo.texture_uid_list.append(prop)

                    if components > 1:
                        for component in range(components):
                            property_texture_combo.addItem(f"{prop}[{component}]")
                            property_texture_combo.texture_uid_list.append(
                                f"{prop}[{component}]"
                            )

            for texture_uid in self.parent.dom_coll.df.loc[
                self.parent.dom_coll.df["uid"] == uid, "texture_uids"
            ].values[0]:
                texture_name = self.parent.image_coll.df.loc[
                    self.parent.image_coll.df["uid"] == texture_uid, "name"
                ].values[0]
                property_texture_combo.addItem(texture_name)
                property_texture_combo.texture_uid_list.append(texture_uid)

            self.DOMsTableWidget.insertRow(row)
            self.DOMsTableWidget.setItem(row, 0, name_item)
            self.DOMsTableWidget.setItem(row, 1, uid_item)
            self.DOMsTableWidget.setCellWidget(row, 2, property_texture_combo)
            property_texture_combo.currentIndexChanged.connect(
                lambda: self.toggle_property_texture()
            )
            if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                name_item.setCheckState(Qt.Checked)
            elif not self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                name_item.setCheckState(Qt.Unchecked)
            row += 1
        """Send message with argument = the cell being checked/unchecked."""
        self.DOMsTableWidget.itemChanged.connect(self.toggle_dom_visibility)

    def update_dom_list_added(self, new_list=None, sec_uid=None):
        """Update DOM list without creating a new model"""
        # print('update_dom_list_added')
        row = self.DOMsTableWidget.rowCount()
        uid_list = list(new_list["uid"])
        if sec_uid:
            for i, uid in enumerate(new_list["uid"]):
                if (
                    sec_uid
                    != self.parent.dom_coll.df.loc[
                        self.parent.dom_coll.df["uid"] == uid, "x_section"
                    ].values[0]
                ):
                    del uid_list[i]
        for uid in uid_list:
            name = self.parent.dom_coll.df.loc[
                self.parent.dom_coll.df["uid"] == uid, "name"
            ].values[0]
            name_item = QTableWidgetItem(name)
            name_item.setFlags(name_item.flags() | Qt.ItemIsUserCheckable)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            uid_item = QTableWidgetItem(uid)
            property_texture_combo = QComboBox()
            property_texture_combo.uid = uid
            property_texture_combo.addItem("none")
            property_texture_combo.texture_uid_list = ["none", "X", "Y", "Z"]
            property_texture_combo.addItem("X")
            property_texture_combo.addItem("Y")
            property_texture_combo.addItem("Z")
            # property_texture_combo.addItem("RGB")

            """[Gabriele] See function above for explanation"""

            for prop, components in zip(
                self.parent.dom_coll.get_uid_properties_names(uid),
                self.parent.dom_coll.get_uid_properties_components(uid),
            ):
                if (
                    prop
                    not in self.parent.dom_coll.df.loc[
                        self.parent.dom_coll.df["uid"] == uid, "texture_uids"
                    ].values[0]
                ):
                    property_texture_combo.addItem(prop)
                    property_texture_combo.texture_uid_list.append(prop)
                    # print(prop)
                    if components > 1:
                        for n_component in range(components):
                            property_texture_combo.addItem(f"{prop}[{n_component}]")
                            property_texture_combo.texture_uid_list.append(
                                f"{prop}[{n_component}]"
                            )
            for texture_uid in self.parent.dom_coll.df.loc[
                self.parent.dom_coll.df["uid"] == uid, "texture_uids"
            ].values[0]:
                texture_name = self.parent.image_coll.df.loc[
                    self.parent.image_coll.df["uid"] == texture_uid, "name"
                ].values[0]
                property_texture_combo.addItem(texture_name)
                property_texture_combo.texture_uid_list.append(texture_uid)
            self.DOMsTableWidget.insertRow(row)
            self.DOMsTableWidget.setItem(row, 0, name_item)
            self.DOMsTableWidget.setItem(row, 1, uid_item)
            self.DOMsTableWidget.setCellWidget(row, 2, property_texture_combo)
            property_texture_combo.currentIndexChanged.connect(
                lambda: self.toggle_property_texture()
            )
            if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                name_item.setCheckState(Qt.Checked)
            elif not self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                name_item.setCheckState(Qt.Unchecked)
            row += 1
        """Send message with argument = the cell being checked/unchecked."""
        self.DOMsTableWidget.itemChanged.connect(self.toggle_dom_visibility)

    def update_dom_list_removed(self, removed_list=None):
        """Update DOM list without creating a new model"""
        for uid in removed_list:
            for row in range(self.DOMsTableWidget.rowCount()):
                """Iterate through each row of the QTableWidget to find the row with the corresponding entity"""
                if self.DOMsTableWidget.item(row, 1).text() == uid:
                    """Row found: delete row"""
                    self.DOMsTableWidget.removeRow(row)
                    row -= 1
                    break
        """Send message with argument = the cell being checked/unchecked."""
        self.DOMsTableWidget.itemChanged.connect(self.toggle_dom_visibility)

    def toggle_dom_visibility(self, cell):
        """Called by self.DOMsTableWidget.itemChanged.connect(self.toggle_dom_visibility)."""
        check_state = self.DOMsTableWidget.item(
            cell.row(), 0
        ).checkState()  # this is the check state of cell "name"

        if self.DOMsTableWidget.item(cell.row(), 1):
            uid = self.DOMsTableWidget.item(
                cell.row(), 1
            ).text()  # this is the text of cell "uid"
        else:
            return
        if check_state == Qt.Checked:
            if not self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                self.actors_df.loc[self.actors_df["uid"] == uid, "show"] = True
                self.set_actor_visible(uid=uid, visible=True)

        elif check_state == Qt.Unchecked:
            if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                self.actors_df.loc[self.actors_df["uid"] == uid, "show"] = False
                self.set_actor_visible(uid=uid, visible=False)

    def toggle_property_texture(self):
        """Method to toggle the texture shown by a DEM that is already present in the view."""
        """Collect values from combo box."""

        combo = self.sender()
        uid = combo.uid
        property_texture_id = combo.currentIndex()  # 0 means "none"
        property_texture_list = combo.texture_uid_list
        property_texture_uid = property_texture_list[property_texture_id]
        """Set the active texture coordinates."""
        if (
            property_texture_uid
            in self.parent.dom_coll.df.loc[
                self.parent.dom_coll.df["uid"] == uid, "texture_uids"
            ].values[0]
        ):
            self.parent.dom_coll.set_active_texture_on_dom(
                dom_uid=uid, map_image_uid=property_texture_uid
            )
        """Show DOM with current texture"""
        show = self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]
        collection = self.actors_df.loc[
            self.actors_df["uid"] == uid, "collection"
        ].values[0]
        """This removes the previous copy of the actor with the same uid, then calls the viewer-specific function that shows an actor with a property.
        IN THE FUTURE see if it is possible and more efficient to keep the actor and just change the property shown."""

        # [Gabriele] Remove the previous scalar bar if present
        if hasattr(self, "plotter"):
            try:
                self.plotter.remove_scalar_bar()
            except IndexError:
                pass
        self.remove_actor_in_view(uid=uid)
        this_actor = self.show_actor_with_property(
            uid=uid,
            collection=collection,
            show_property=property_texture_uid,
            visible=show,
        )
        self.actors_df = self.actors_df.append(
            {
                "uid": uid,
                "actor": this_actor,
                "show": show,
                "collection": collection,
                "show_prop": property_texture_uid,
            },
            ignore_index=True,
        )  # self.set_actor_visible(uid=uid, visible=show)

    """Methods used to build and update the image table."""

    def create_image_list(self, sec_uid=None):
        """Create image list with checkboxes."""
        self.ImagesTableWidget.clear()
        self.ImagesTableWidget.setColumnCount(3)
        self.ImagesTableWidget.setRowCount(0)
        self.ImagesTableWidget.setHorizontalHeaderLabels(["Name", "uid"])
        self.ImagesTableWidget.hideColumn(1)  # hide the uid column
        if sec_uid:
            uids = self.parent.image_coll.df.loc[
                (self.parent.image_coll.df["x_section"] == sec_uid), "uid"
            ].to_list()
        else:
            uids = self.parent.image_coll.df["uid"].to_list()
        row = 0
        for uid in uids:
            name = self.parent.image_coll.df.loc[
                self.parent.image_coll.df["uid"] == uid, "name"
            ].values[0]
            name_item = QTableWidgetItem(name)
            name_item.setFlags(name_item.flags() | Qt.ItemIsUserCheckable)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            uid_item = QTableWidgetItem(uid)
            property_combo = QComboBox()
            property_combo.uid = uid
            property_combo.addItem("none")
            property_combo.texture_uid_list = ["none"]
            # property_combo.texture_uid_list = ["none", "X", "Y", "Z"]
            # property_combo.addItem("X")
            # property_combo.addItem("Y")
            # property_combo.addItem("Z")
            for prop in self.parent.image_coll.get_uid_properties_names(uid):
                property_combo.addItem(prop)
            self.ImagesTableWidget.insertRow(row)
            self.ImagesTableWidget.setItem(row, 0, name_item)
            self.ImagesTableWidget.setItem(row, 1, uid_item)
            self.ImagesTableWidget.setCellWidget(row, 2, property_combo)
            property_combo.currentIndexChanged.connect(
                lambda: self.toggle_property_image()
            )  # ___________
            if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                name_item.setCheckState(Qt.Checked)
            elif not self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                name_item.setCheckState(Qt.Unchecked)
            row += 1
        """Send message with argument = the cell being checked/unchecked."""
        self.ImagesTableWidget.itemChanged.connect(self.toggle_image_visibility)

    def update_image_list_added(self, new_list=None, sec_uid=None):
        """Update Image list without creating a new model"""
        row = self.ImagesTableWidget.rowCount()
        if sec_uid:
            uids = self.parent.image_coll.df.loc[
                (self.parent.image_coll.df["x_section"] == sec_uid), "uid"
            ].to_list()
        else:
            uids = self.parent.image_coll.df["uid"].to_list()
        for uid in uids:
            name = self.parent.image_coll.df.loc[
                self.parent.image_coll.df["uid"] == uid, "name"
            ].values[0]
            name_item = QTableWidgetItem(name)
            name_item.setFlags(name_item.flags() | Qt.ItemIsUserCheckable)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            uid_item = QTableWidgetItem(uid)
            property_combo = QComboBox()
            property_combo.uid = uid
            property_combo.addItem("none")
            property_combo.texture_uid_list = ["none"]
            # property_combo.texture_uid_list = ["none", "X", "Y", "Z"]
            # property_combo.addItem("X")
            # property_combo.addItem("Y")
            # property_combo.addItem("Z")
            for prop in self.parent.image_coll.get_uid_properties_names(uid):
                property_combo.addItem(prop)
            self.ImagesTableWidget.insertRow(row)
            self.ImagesTableWidget.setItem(row, 0, name_item)
            self.ImagesTableWidget.setItem(row, 1, uid_item)
            self.ImagesTableWidget.setCellWidget(row, 2, property_combo)
            property_combo.currentIndexChanged.connect(
                lambda: self.toggle_property_image()
            )  # ___________
            if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                name_item.setCheckState(Qt.Checked)
            elif not self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                name_item.setCheckState(Qt.Unchecked)
            row += 1
        """Send message with argument = the cell being checked/unchecked."""
        self.ImagesTableWidget.itemChanged.connect(self.toggle_image_visibility)

    def update_image_list_removed(self, removed_list=None):
        """Update Image list without creating a new model"""
        for uid in removed_list:
            for row in range(self.ImagesTableWidget.rowCount()):
                """Iterate through each row of the QTableWidget to find the row with the corresponding entity"""
                if self.ImagesTableWidget.item(row, 1).text() == uid:
                    """Row found: delete row"""
                    self.ImagesTableWidget.removeRow(row)
                    row -= 1
                    break
        """Send message with argument = the cell being checked/unchecked."""
        self.ImagesTableWidget.itemChanged.connect(self.toggle_dom_visibility)

    def toggle_image_visibility(self, cell):
        """Called by self.ImagesTableWidget.itemChanged.connect(self.toggle_image_visibility)."""
        check_state = self.ImagesTableWidget.item(
            cell.row(), 0
        ).checkState()  # this is the check state of cell "name"
        uid = self.ImagesTableWidget.item(
            cell.row(), 1
        ).text()  # this is the text of cell "uid"
        if check_state == Qt.Checked:
            if not self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                self.actors_df.loc[self.actors_df["uid"] == uid, "show"] = True
                self.set_actor_visible(uid=uid, visible=True)
        elif check_state == Qt.Unchecked:
            if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                self.actors_df.loc[self.actors_df["uid"] == uid, "show"] = False
                self.set_actor_visible(uid=uid, visible=False)

    def toggle_property_image(self):
        """Method to toggle the property shown by an image that is already present in the view."""
        """Collect values from combo box."""
        combo = self.sender()
        show_property = combo.currentText()
        uid = combo.uid
        show = self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]
        collection = self.actors_df.loc[
            self.actors_df["uid"] == uid, "collection"
        ].values[0]
        """This removes the previous copy of the actor with the same uid, then calls the viewer-specific function that shows an actor with a property.
        IN THE FUTURE see if it is possible and more efficient to keep the actor and just change the property shown."""
        self.remove_actor_in_view(uid=uid)
        this_actor = self.show_actor_with_property(
            uid=uid, collection=collection, show_property=show_property, visible=show
        )
        self.actors_df = self.actors_df.append(
            {
                "uid": uid,
                "actor": this_actor,
                "show": show,
                "collection": collection,
                "show_prop": show_property,
            },
            ignore_index=True,
        )  # self.set_actor_visible(uid=uid, visible=show)

    """Methods used to build and update the Wells table."""

    def create_well_tree(self):
        """Create topology tree with checkboxes and properties"""
        self.WellsTreeWidget.clear()
        self.WellsTreeWidget.setColumnCount(3)
        self.WellsTreeWidget.setHeaderLabels(["Loc ID > Component", "uid", "property"])
        self.WellsTreeWidget.hideColumn(1)  # hide the uid column
        self.WellsTreeWidget.setItemsExpandable(True)

        locids = pd_unique(self.parent.well_coll.df["Loc ID"])

        for locid in locids:
            uid = self.parent.well_coll.df.loc[
                (self.parent.well_coll.df["Loc ID"] == locid), "uid"
            ].values[0]
            tlevel_1 = QTreeWidgetItem(
                self.WellsTreeWidget, [locid]
            )  # self.GeologyTreeWidget as parent -> top level
            tlevel_1.setFlags(
                tlevel_1.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
            )

            property_combo = QComboBox()
            property_combo.uid = uid
            property_combo.name = "Annotations"
            property_combo.addItem("none")
            property_combo.addItem("name")
            self.WellsTreeWidget.setItemWidget(tlevel_1, 2, property_combo)
            property_combo.currentIndexChanged.connect(lambda: self.toggle_property())

            # ======================================= TRACE =======================================

            tlevel_2_trace = QTreeWidgetItem(
                tlevel_1, ["Trace", uid]
            )  # tlevel_1 as parent -> middle level
            tlevel_2_trace.setFlags(
                tlevel_2_trace.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
            )

            property_combo = QComboBox()
            property_combo.uid = uid
            property_combo.name = "Trace"
            property_combo.addItem("none")
            property_combo.addItem("X")
            property_combo.addItem("Y")
            property_combo.addItem("Z")
            for prop in self.parent.well_coll.get_uid_properties_names(uid):
                if prop == "LITHOLOGY":
                    pass
                elif prop == "GEOLOGY":
                    pass
                else:
                    property_combo.addItem(prop)

            self.WellsTreeWidget.setItemWidget(tlevel_2_trace, 2, property_combo)
            property_combo.currentIndexChanged.connect(lambda: self.toggle_property())
            tlevel_2_trace.setFlags(tlevel_2_trace.flags() | Qt.ItemIsUserCheckable)
            if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                tlevel_2_trace.setCheckState(0, Qt.Checked)
            elif not self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                tlevel_2_trace.setCheckState(0, Qt.Unchecked)

        # ======================================= MARKER =======================================

        # tlevel_2_mark = QTreeWidgetItem(tlevel_1, ['Markers', uid])  # tlevel_1 as parent -> middle level
        # tlevel_2_mark.setFlags(tlevel_2_mark.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable)

        # property_combo = QComboBox()
        # property_combo.uid = uid
        # property_combo.name = 'Marker'
        # property_combo.addItem("none")
        # for prop in self.parent.well_coll.get_uid_marker_names(uid):
        #     property_combo.addItem(prop)

        # self.WellsTreeWidget.setItemWidget(tlevel_2_mark, 2, property_combo)
        # property_combo.currentIndexChanged.connect(lambda: self.toggle_property())
        # tlevel_2_mark.setFlags(tlevel_2_mark.flags() | Qt.ItemIsUserCheckable)
        # if self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
        #     tlevel_2_mark.setCheckState(0, Qt.Checked)
        # elif not self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
        #     tlevel_2_mark.setCheckState(0, Qt.Unchecked)

        # ======================================= ANNOTATIONS =======================================

        # tlevel_2_mark = QTreeWidgetItem(tlevel_1, ['Annotations', uid])  # tlevel_1 as parent -> middle level
        # tlevel_2_mark.setFlags(tlevel_2_mark.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable)

        # property_combo = QComboBox()
        # property_combo.uid = uid
        # property_combo.name = 'Annotations'
        # property_combo.addItem("none")
        # for annotation_uid in self.parent.backgrounds_coll.get_buid_uid(uid):
        #     name = self.parent.backgrounds_coll.get_uid_name(annotation_uid)
        #     property_combo.addItem(name)

        # self.WellsTreeWidget.setItemWidget(tlevel_2_mark, 2, property_combo)
        # property_combo.currentIndexChanged.connect(lambda: self.toggle_property())
        # tlevel_2_mark.setFlags(tlevel_2_mark.flags() | Qt.ItemIsUserCheckable)
        # if self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
        #     tlevel_2_mark.setCheckState(0, Qt.Checked)
        # elif not self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
        #     tlevel_2_mark.setCheckState(0, Qt.Unchecked)

        """Send messages. Note that with tristate several signals are emitted in a sequence, one for each
        changed item, but upper levels do not broadcast uid's so they are filtered in the toggle method."""
        self.WellsTreeWidget.itemChanged.connect(self.toggle_well_visibility)
        self.WellsTreeWidget.expandAll()

    def update_well_tree_added(self, new_list=None):
        """Update well tree without creating a new model"""
        for uid in new_list["uid"]:
            if (
                self.WellsTreeWidget.findItems(
                    self.parent.well_coll.get_uid_well_locid(uid), Qt.MatchExactly, 0
                )
                != []
            ):
                """Already exists a TreeItem (1 level) for the geological type"""
                counter_1 = 0
                for child_1 in range(
                    self.WellsTreeWidget.findItems(
                        self.parent.well_coll.get_uid_well_locid(uid),
                        Qt.MatchExactly,
                        0,
                    )[0].childCount()
                ):
                    glevel_2 = QTreeWidgetItem(
                        self.WellsTreeWidget.findItems(
                            self.parent.well_coll.get_uid_well_locid(uid),
                            Qt.MatchExactly,
                            0,
                        )[0]
                    )
                    glevel_2.setFlags(
                        glevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
                    )
                    self.WellsTreeWidget.insertTopLevelItem(0, glevel_2)

                    property_combo = QComboBox()
                    property_combo.uid = uid
                    property_combo.name = "Trace"
                    property_combo.addItem("none")
                    property_combo.addItem("X")
                    property_combo.addItem("Y")
                    property_combo.addItem("Z")
                    for prop in self.parent.well_coll.get_uid_properties_names(uid):
                        if prop == "LITHOLOGY":
                            pass
                        elif prop == "GEOLOGY":
                            pass
                        else:
                            property_combo.addItem(prop)

                    self.WellsTreeWidget.setItemWidget(glevel_2, 2, property_combo)
                    property_combo.currentIndexChanged.connect(
                        lambda: self.toggle_property()
                    )
                    glevel_2.setFlags(glevel_2.flags() | Qt.ItemIsUserCheckable)
                    if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[
                        0
                    ]:
                        glevel_2.setCheckState(0, Qt.Checked)
                    elif not self.actors_df.loc[
                        self.actors_df["uid"] == uid, "show"
                    ].values[0]:
                        glevel_2.setCheckState(0, Qt.Unchecked)
                    self.WellsTreeWidget.insertTopLevelItem(0, glevel_2)
                    break
            else:
                """Different geological type, geological feature and scenario"""
                tlevel_1 = QTreeWidgetItem(
                    self.WellsTreeWidget,
                    [self.parent.well_coll.get_uid_well_locid(uid)],
                )  # self.GeologyTreeWidget as parent -> top level
                tlevel_1.setFlags(
                    tlevel_1.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
                )

                property_combo = QComboBox()
                property_combo.uid = uid
                property_combo.name = "Annotations"
                property_combo.addItem("none")
                property_combo.addItem("name")
                self.WellsTreeWidget.setItemWidget(tlevel_1, 2, property_combo)
                property_combo.currentIndexChanged.connect(
                    lambda: self.toggle_property()
                )

                # ======================================= TRACE =======================================

                tlevel_2_trace = QTreeWidgetItem(
                    tlevel_1, ["Trace", uid]
                )  # tlevel_1 as parent -> middle level
                tlevel_2_trace.setFlags(
                    tlevel_2_trace.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
                )

                property_combo = QComboBox()
                property_combo.uid = uid
                property_combo.name = "Trace"
                property_combo.addItem("none")
                property_combo.addItem("X")
                property_combo.addItem("Y")
                property_combo.addItem("Z")
                for prop in self.parent.well_coll.get_uid_properties_names(uid):
                    if prop == "LITHOLOGY":
                        pass
                    elif prop == "GEOLOGY":
                        pass
                    else:
                        property_combo.addItem(prop)

                self.WellsTreeWidget.setItemWidget(tlevel_2_trace, 2, property_combo)
                property_combo.currentIndexChanged.connect(
                    lambda: self.toggle_property()
                )
                tlevel_2_trace.setFlags(tlevel_2_trace.flags() | Qt.ItemIsUserCheckable)
                if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                    tlevel_2_trace.setCheckState(0, Qt.Checked)
                elif not self.actors_df.loc[
                    self.actors_df["uid"] == uid, "show"
                ].values[0]:
                    tlevel_2_trace.setCheckState(0, Qt.Unchecked)
                break

        self.WellsTreeWidget.itemChanged.connect(self.toggle_well_visibility)
        self.WellsTreeWidget.expandAll()

    def update_well_tree_removed(self, removed_list=None):
        """When geological entity is removed, update Geology Tree without building a new model"""
        success = 0
        for uid in removed_list:
            for well_locid in range(self.WellsTreeWidget.topLevelItemCount()):
                """Iterate through every Geological Type top level"""
                for child_geo_feat in range(
                    self.WellsTreeWidget.topLevelItem(well_locid).childCount()
                ):
                    """Iterate through every Geological Feature child"""
                    if (
                        self.WellsTreeWidget.topLevelItem(well_locid)
                        .child(child_geo_feat)
                        .text(1)
                        == uid
                    ):
                        """Complete check: entity found has the uid of the entity we need to remove. Delete child, then ensure no Child or Top Level remain empty"""
                        success = 1
                        self.WellsTreeWidget.topLevelItem(well_locid).child(
                            child_geo_feat
                        ).removeChild(
                            self.WellsTreeWidget.topLevelItem(well_locid).child(
                                child_geo_feat
                            )
                        )

                        if (
                            self.WellsTreeWidget.topLevelItem(well_locid).childCount()
                            == 0
                        ):
                            self.WellsTreeWidget.takeTopLevelItem(well_locid)
                        break
                if success == 1:
                    break

    def toggle_well_visibility(self, item, column):
        """Called by self.WellsTreeWidget.itemChanged.connect(self.toggle_boundary_visibility)."""

        name = item.text(0)  # not used
        uid = item.text(1)
        uid_checkState = item.checkState(0)
        if (
            uid
        ):  # needed to skip messages from upper levels of tree that do not broadcast uid's
            if uid_checkState == Qt.Checked:
                if not self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[
                    0
                ]:
                    if name == "Trace":
                        self.actors_df.loc[self.actors_df["uid"] == uid, "show"] = True
                self.set_actor_visible(uid=uid, visible=True, name=name)
            elif uid_checkState == Qt.Unchecked:
                if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                    if name == "Trace":
                        self.actors_df.loc[self.actors_df["uid"] == uid, "show"] = False
                self.set_actor_visible(uid=uid, visible=False, name=name)

            self.WellsTreeWidget.itemChanged.disconnect()
            self.WellsTreeWidget.itemChanged.connect(self.toggle_well_visibility)

    """Methods used to build and update the fluid and fluid topology trees."""

    def create_fluids_tree(self, sec_uid=None):
        """Create fluids tree with checkboxes and properties"""
        self.FluidsTreeWidget.clear()
        self.FluidsTreeWidget.setColumnCount(3)
        self.FluidsTreeWidget.setHeaderLabels(
            ["Type > Feature > Scenario > Name", "uid", "property"]
        )
        self.FluidsTreeWidget.hideColumn(1)  # hide the uid column
        self.FluidsTreeWidget.setItemsExpandable(True)
        if sec_uid:
            fluid_types = pd_unique(
                self.parent.fluids_coll.df.loc[
                    (self.parent.fluids_coll.df["x_section"] == sec_uid), "fluid_type"
                ]
            )
        else:
            fluid_types = pd_unique(self.parent.fluids_coll.df["fluid_type"])
        for fluid_type in fluid_types:
            flevel_1 = QTreeWidgetItem(
                self.FluidsTreeWidget, [fluid_type]
            )  # self.FluidsTreeWidget as parent -> top level
            flevel_1.setFlags(
                flevel_1.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
            )
            if sec_uid:
                fluid_features = pd_unique(
                    self.parent.fluids_coll.df.loc[
                        (self.parent.fluids_coll.df["fluid_type"] == fluid_type)
                        & (self.parent.fluids_coll.df["x_section"] == sec_uid),
                        "fluid_feature",
                    ]
                )
            else:
                fluid_features = pd_unique(
                    self.parent.fluids_coll.df.loc[
                        self.parent.fluids_coll.df["fluid_type"] == fluid_type,
                        "fluid_feature",
                    ]
                )
            for feature in fluid_features:
                flevel_2 = QTreeWidgetItem(
                    flevel_1, [feature]
                )  # flevel_1 as parent -> 1st middle level
                flevel_2.setFlags(
                    flevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
                )
                if sec_uid:
                    fluid_scenario = pd_unique(
                        self.parent.fluids_coll.df.loc[
                            (self.parent.fluids_coll.df["fluid_type"] == fluid_type)
                            & (self.parent.fluids_coll.df["fluid_feature"] == feature)
                            & (self.parent.fluids_coll.df["x_section"] == sec_uid),
                            "scenario",
                        ]
                    )
                else:
                    fluid_scenario = pd_unique(
                        self.parent.fluids_coll.df.loc[
                            (self.parent.fluids_coll.df["fluid_type"] == fluid_type)
                            & (self.parent.fluids_coll.df["fluid_feature"] == feature),
                            "scenario",
                        ]
                    )
                for scenario in fluid_scenario:
                    flevel_3 = QTreeWidgetItem(
                        flevel_2, [scenario]
                    )  # flevel_2 as parent -> 2nd middle level
                    flevel_3.setFlags(
                        flevel_3.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
                    )
                    if sec_uid:
                        uids = self.parent.fluids_coll.df.loc[
                            (self.parent.fluids_coll.df["fluid_type"] == fluid_type)
                            & (self.parent.fluids_coll.df["fluid_feature"] == feature)
                            & (self.parent.fluids_coll.df["scenario"] == scenario)
                            & (self.parent.fluids_coll.df["x_section"] == sec_uid),
                            "uid",
                        ].to_list()
                    else:
                        uids = self.parent.fluids_coll.df.loc[
                            (self.parent.fluids_coll.df["fluid_type"] == fluid_type)
                            & (self.parent.fluids_coll.df["fluid_feature"] == feature)
                            & (self.parent.fluids_coll.df["scenario"] == scenario),
                            "uid",
                        ].to_list()
                    for uid in uids:
                        property_combo = QComboBox()
                        property_combo.uid = uid
                        property_combo.addItem("none")
                        property_combo.addItem("X")
                        property_combo.addItem("Y")
                        property_combo.addItem("Z")
                        for prop in self.parent.fluids_coll.get_uid_properties_names(
                            uid
                        ):
                            property_combo.addItem(prop)
                        name = self.parent.fluids_coll.df.loc[
                            (self.parent.fluids_coll.df["uid"] == uid), "name"
                        ].values[0]
                        flevel_4 = QTreeWidgetItem(
                            flevel_3, [name, uid]
                        )  # flevel_3 as parent -> lower level
                        self.FluidsTreeWidget.setItemWidget(flevel_4, 2, property_combo)
                        property_combo.currentIndexChanged.connect(
                            lambda: self.toggle_property()
                        )
                        flevel_4.setFlags(flevel_4.flags() | Qt.ItemIsUserCheckable)
                        if self.actors_df.loc[
                            self.actors_df["uid"] == uid, "show"
                        ].values[0]:
                            flevel_4.setCheckState(0, Qt.Checked)
                        elif not self.actors_df.loc[
                            self.actors_df["uid"] == uid, "show"
                        ].values[0]:
                            flevel_4.setCheckState(0, Qt.Unchecked)
        """Send messages. Note that with tristate several signals are emitted in a sequence, one for each
        changed item, but upper levels do not broadcast uid's so they are filtered in the toggle method."""
        self.FluidsTreeWidget.itemChanged.connect(
            self.toggle_fluids_topology_visibility
        )
        self.FluidsTreeWidget.expandAll()

    def create_fluids_topology_tree(self, sec_uid=None):
        """Create topology tree with checkboxes and properties"""
        self.FluidsTopologyTreeWidget.clear()
        self.FluidsTopologyTreeWidget.setColumnCount(3)
        self.FluidsTopologyTreeWidget.setHeaderLabels(
            ["Type > Scenario > Name", "uid", "property"]
        )
        self.FluidsTopologyTreeWidget.hideColumn(1)  # hide the uid column
        self.FluidsTopologyTreeWidget.setItemsExpandable(True)

        if sec_uid:
            filtered_topo = self.parent.fluids_coll.df.loc[
                (self.parent.fluids_coll.df["x_section"] == sec_uid), "topological_type"
            ]
            topo_types = pd_unique(filtered_topo)
        else:
            topo_types = pd_unique(self.parent.fluids_coll.df["topological_type"])

        for topo_type in topo_types:
            tlevel_1 = QTreeWidgetItem(
                self.FluidsTopologyTreeWidget, [topo_type]
            )  # self.GeologyTreeWidget as parent -> top level
            tlevel_1.setFlags(
                tlevel_1.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
            )
            for scenario in pd_unique(
                self.parent.fluids_coll.df.loc[
                    self.parent.fluids_coll.df["topological_type"] == topo_type,
                    "scenario",
                ]
            ):
                tlevel_2 = QTreeWidgetItem(
                    tlevel_1, [scenario]
                )  # tlevel_1 as parent -> middle level
                tlevel_2.setFlags(
                    tlevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
                )
                if sec_uid:
                    uids = self.parent.fluids_coll.df.loc[
                        (self.parent.fluids_coll.df["topological_type"] == topo_type)
                        & (self.parent.fluids_coll.df["scenario"] == scenario)
                        & (self.parent.fluids_coll.df["x_section"] == sec_uid),
                        "uid",
                    ].to_list()
                else:
                    uids = self.parent.fluids_coll.df.loc[
                        (self.parent.fluids_coll.df["topological_type"] == topo_type)
                        & (self.parent.fluids_coll.df["scenario"] == scenario),
                        "uid",
                    ].to_list()
                for uid in uids:
                    property_combo = QComboBox()
                    property_combo.uid = uid
                    property_combo.addItem("none")
                    property_combo.addItem("X")
                    property_combo.addItem("Y")
                    property_combo.addItem("Z")
                    for prop in self.parent.fluids_coll.get_uid_properties_names(uid):
                        property_combo.addItem(prop)
                    name = self.parent.fluids_coll.df.loc[
                        self.parent.fluids_coll.df["uid"] == uid, "name"
                    ].values[0]
                    tlevel_3 = QTreeWidgetItem(
                        tlevel_2, [name, uid]
                    )  # tlevel_2 as parent -> lower level
                    self.FluidsTopologyTreeWidget.setItemWidget(
                        tlevel_3, 2, property_combo
                    )
                    property_combo.currentIndexChanged.connect(
                        lambda: self.toggle_property()
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
        """Send messages. Note that with tristate several signals are emitted in a sequence, one for each
        changed item, but upper levels do not broadcast uid's so they are filtered in the toggle method."""
        self.FluidsTopologyTreeWidget.itemChanged.connect(
            self.toggle_fluids_topology_visibility
        )
        self.FluidsTopologyTreeWidget.expandAll()

    def update_fluids_tree_added(self, new_list=None, sec_uid=None):
        """Update fluid tree without creating a new model"""
        uid_list = list(new_list["uid"])
        if sec_uid:
            for i, uid in enumerate(new_list["uid"]):
                if (
                    sec_uid
                    != self.parent.fluids_coll.df.loc[
                        self.parent.fluids_coll.df["uid"] == uid, "x_section"
                    ].values[0]
                ):
                    del uid_list[i]
        for uid in uid_list:
            if (
                self.FluidsTreeWidget.findItems(
                    self.parent.fluids_coll.get_uid_fluid_type(uid), Qt.MatchExactly, 0
                )
                != []
            ):
                """Already exists a TreeItem (1 level) for the fluid type"""
                counter_1 = 0
                for child_1 in range(
                    self.FluidsTreeWidget.findItems(
                        self.parent.fluids_coll.get_uid_fluid_type(uid),
                        Qt.MatchExactly,
                        0,
                    )[0].childCount()
                ):
                    """for cycle that loops n times as the number of subItems in the specific fluid type branch"""
                    if self.FluidsTreeWidget.findItems(
                        self.parent.fluids_coll.get_uid_fluid_type(uid),
                        Qt.MatchExactly,
                        0,
                    )[0].child(child_1).text(
                        0
                    ) == self.parent.fluids_coll.get_uid_fluid_feature(
                        uid
                    ):
                        counter_1 += 1
                if counter_1 != 0:
                    for child_1 in range(
                        self.FluidsTreeWidget.findItems(
                            self.parent.fluids_coll.get_uid_fluid_type(uid),
                            Qt.MatchExactly,
                            0,
                        )[0].childCount()
                    ):
                        if self.FluidsTreeWidget.findItems(
                            self.parent.fluids_coll.get_uid_fluid_type(uid),
                            Qt.MatchExactly,
                            0,
                        )[0].child(child_1).text(
                            0
                        ) == self.parent.fluids_coll.get_uid_fluid_feature(
                            uid
                        ):
                            """Already exists a TreeItem (2 level) for the fluid feature"""
                            counter_2 = 0
                            for child_2 in range(
                                self.FluidsTreeWidget.itemBelow(
                                    self.FluidsTreeWidget.findItems(
                                        self.parent.fluids_coll.get_uid_fluid_type(uid),
                                        Qt.MatchExactly,
                                        0,
                                    )[0]
                                ).childCount()
                            ):
                                """for cycle that loops n times as the number of sub-subItems in the specific fluid type and fluid feature branch"""
                                if self.FluidsTreeWidget.itemBelow(
                                    self.FluidsTreeWidget.findItems(
                                        self.parent.fluids_coll.get_uid_fluid_type(uid),
                                        Qt.MatchExactly,
                                        0,
                                    )[0]
                                ).child(child_2).text(
                                    0
                                ) == self.parent.fluids_coll.get_uid_scenario(
                                    uid
                                ):
                                    counter_2 += 1
                            if counter_2 != 0:
                                for child_2 in range(
                                    self.FluidsTreeWidget.itemBelow(
                                        self.FluidsTreeWidget.findItems(
                                            self.parent.fluids_coll.get_uid_fluid_type(
                                                uid
                                            ),
                                            Qt.MatchExactly,
                                            0,
                                        )[0]
                                    ).childCount()
                                ):
                                    if self.FluidsTreeWidget.itemBelow(
                                        self.FluidsTreeWidget.findItems(
                                            self.parent.fluids_coll.get_uid_fluid_type(
                                                uid
                                            ),
                                            Qt.MatchExactly,
                                            0,
                                        )[0]
                                    ).child(child_2).text(
                                        0
                                    ) == self.parent.fluids_coll.get_uid_scenario(
                                        uid
                                    ):
                                        """Same fluid type, fluid feature and scenario"""
                                        property_combo = QComboBox()
                                        property_combo.uid = uid
                                        property_combo.addItem("none")
                                        property_combo.addItem("X")
                                        property_combo.addItem("Y")
                                        property_combo.addItem("Z")
                                        for (
                                            prop
                                        ) in self.parent.fluids_coll.get_uid_properties_names(
                                            uid
                                        ):
                                            property_combo.addItem(prop)
                                        name = self.parent.fluids_coll.get_uid_name(uid)
                                        flevel_4 = QTreeWidgetItem(
                                            self.FluidsTreeWidget.findItems(
                                                self.parent.fluids_coll.get_uid_fluid_type(
                                                    uid
                                                ),
                                                Qt.MatchExactly,
                                                0,
                                            )[0]
                                            .child(child_1)
                                            .child(child_2),
                                            [name, uid],
                                        )
                                        self.FluidsTreeWidget.setItemWidget(
                                            flevel_4, 2, property_combo
                                        )
                                        property_combo.currentIndexChanged.connect(
                                            lambda: self.toggle_property()
                                        )
                                        flevel_4.setFlags(
                                            flevel_4.flags() | Qt.ItemIsUserCheckable
                                        )
                                        if self.actors_df.loc[
                                            self.actors_df["uid"] == uid, "show"
                                        ].values[0]:
                                            flevel_4.setCheckState(0, Qt.Checked)
                                        elif not self.actors_df.loc[
                                            self.actors_df["uid"] == uid, "show"
                                        ].values[0]:
                                            flevel_4.setCheckState(0, Qt.Unchecked)
                                        self.FluidsTreeWidget.insertTopLevelItem(
                                            0, flevel_4
                                        )
                                        break
                            else:
                                """Same fluid type and fluid feature, different scenario"""
                                flevel_3 = QTreeWidgetItem(
                                    self.FluidsTreeWidget.findItems(
                                        self.parent.fluids_coll.get_uid_fluid_type(uid),
                                        Qt.MatchExactly,
                                        0,
                                    )[0].child(child_1),
                                    [self.parent.fluids_coll.get_uid_scenario(uid)],
                                )
                                flevel_3.setFlags(
                                    flevel_3.flags()
                                    | Qt.ItemIsTristate
                                    | Qt.ItemIsUserCheckable
                                )
                                self.FluidsTreeWidget.insertTopLevelItem(0, flevel_3)
                                property_combo = QComboBox()
                                property_combo.uid = uid
                                property_combo.addItem("none")
                                property_combo.addItem("X")
                                property_combo.addItem("Y")
                                property_combo.addItem("Z")
                                for (
                                    prop
                                ) in self.parent.fluids_coll.get_uid_properties_names(
                                    uid
                                ):
                                    property_combo.addItem(prop)
                                name = self.parent.fluids_coll.get_uid_name(uid)
                                flevel_4 = QTreeWidgetItem(flevel_3, [name, uid])
                                self.FluidsTreeWidget.setItemWidget(
                                    flevel_4, 2, property_combo
                                )
                                property_combo.currentIndexChanged.connect(
                                    lambda: self.toggle_property()
                                )
                                flevel_4.setFlags(
                                    flevel_4.flags() | Qt.ItemIsUserCheckable
                                )
                                if self.actors_df.loc[
                                    self.actors_df["uid"] == uid, "show"
                                ].values[0]:
                                    flevel_4.setCheckState(0, Qt.Checked)
                                elif not self.actors_df.loc[
                                    self.actors_df["uid"] == uid, "show"
                                ].values[0]:
                                    flevel_4.setCheckState(0, Qt.Unchecked)
                                self.FluidsTreeWidget.insertTopLevelItem(0, flevel_4)
                                break
                else:
                    """Same fluid type, different fluid feature and scenario"""
                    flevel_2 = QTreeWidgetItem(
                        self.FluidsTreeWidget.findItems(
                            self.parent.fluids_coll.get_uid_fluid_type(uid),
                            Qt.MatchExactly,
                            0,
                        )[0],
                        [self.parent.fluids_coll.get_uid_fluid_feature(uid)],
                    )
                    flevel_2.setFlags(
                        flevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
                    )
                    self.FluidsTreeWidget.insertTopLevelItem(0, flevel_2)
                    flevel_3 = QTreeWidgetItem(
                        flevel_2, [self.parent.fluids_coll.get_uid_scenario(uid)]
                    )
                    flevel_3.setFlags(
                        flevel_3.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
                    )
                    self.FluidsTreeWidget.insertTopLevelItem(0, flevel_3)
                    property_combo = QComboBox()
                    property_combo.uid = uid
                    property_combo.addItem("none")
                    property_combo.addItem("X")
                    property_combo.addItem("Y")
                    property_combo.addItem("Z")
                    for prop in self.parent.fluids_coll.get_uid_properties_names(uid):
                        property_combo.addItem(prop)
                    name = self.parent.fluids_coll.get_uid_name(uid)
                    flevel_4 = QTreeWidgetItem(flevel_3, [name, uid])
                    self.FluidsTreeWidget.setItemWidget(flevel_4, 2, property_combo)
                    property_combo.currentIndexChanged.connect(
                        lambda: self.toggle_property()
                    )
                    flevel_4.setFlags(flevel_4.flags() | Qt.ItemIsUserCheckable)
                    if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[
                        0
                    ]:
                        flevel_4.setCheckState(0, Qt.Checked)
                    elif not self.actors_df.loc[
                        self.actors_df["uid"] == uid, "show"
                    ].values[0]:
                        flevel_4.setCheckState(0, Qt.Unchecked)
                    self.FluidsTreeWidget.insertTopLevelItem(0, flevel_4)
                    break
            else:
                """Different fluid type, fluid feature and scenario"""
                flevel_1 = QTreeWidgetItem(
                    self.FluidsTreeWidget,
                    [self.parent.fluids_coll.get_uid_fluid_type(uid)],
                )
                flevel_1.setFlags(
                    flevel_1.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
                )
                self.FluidsTreeWidget.insertTopLevelItem(0, flevel_1)
                flevel_2 = QTreeWidgetItem(
                    flevel_1, [self.parent.fluids_coll.get_uid_fluid_feature(uid)]
                )
                flevel_2.setFlags(
                    flevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
                )
                self.FluidsTreeWidget.insertTopLevelItem(0, flevel_2)
                flevel_3 = QTreeWidgetItem(
                    flevel_2, [self.parent.fluids_coll.get_uid_scenario(uid)]
                )
                flevel_3.setFlags(
                    flevel_3.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
                )
                self.FluidsTreeWidget.insertTopLevelItem(0, flevel_3)
                property_combo = QComboBox()
                property_combo.uid = uid
                property_combo.addItem("none")
                property_combo.addItem("X")
                property_combo.addItem("Y")
                property_combo.addItem("Z")
                for prop in self.parent.fluids_coll.get_uid_properties_names(uid):
                    property_combo.addItem(prop)
                name = self.parent.fluids_coll.get_uid_name(uid)
                flevel_4 = QTreeWidgetItem(flevel_3, [name, uid])
                self.FluidsTreeWidget.setItemWidget(flevel_4, 2, property_combo)
                property_combo.currentIndexChanged.connect(
                    lambda: self.toggle_property()
                )
                flevel_4.setFlags(flevel_4.flags() | Qt.ItemIsUserCheckable)
                if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                    flevel_4.setCheckState(0, Qt.Checked)
                elif not self.actors_df.loc[
                    self.actors_df["uid"] == uid, "show"
                ].values[0]:
                    flevel_4.setCheckState(0, Qt.Unchecked)
                self.FluidsTreeWidget.insertTopLevelItem(0, flevel_4)
                break
        self.FluidsTreeWidget.itemChanged.connect(
            self.toggle_fluids_topology_visibility
        )
        self.FluidsTreeWidget.expandAll()

    def update_fluids_tree_removed(self, removed_list=None):  # second attchild_fluid_featempt
        """When fluid entity is removed, update Geology Tree without building a new model"""
        success = 0
        for uid in removed_list:
            for top_fluid_type in range(self.FluidsTreeWidget.topLevelItemCount()):
                """Iterate through every fluid Type top level"""
                for child_fluid_feat in range(
                    self.FluidsTreeWidget.topLevelItem(top_fluid_type).childCount()
                ):
                    """Iterate through every fluid Feature child"""
                    for child_scenario in range(
                        self.FluidsTreeWidget.topLevelItem(top_fluid_type)
                        .child(child_fluid_feat)
                        .childCount()
                    ):
                        """Iterate through every Scenario child"""
                        for child_entity in range(
                            self.FluidsTreeWidget.topLevelItem(top_fluid_type)
                            .child(child_fluid_feat)
                            .child(child_scenario)
                            .childCount()
                        ):
                            """Iterate through every Entity child"""
                            if (
                                self.FluidsTreeWidget.topLevelItem(top_fluid_type)
                                .child(child_fluid_feat)
                                .child(child_scenario)
                                .child(child_entity)
                                .text(1)
                                == uid
                            ):
                                """Complete check: entity found has the uid of the entity we need to remove. Delete child, then ensure no Child or Top Level remain empty"""
                                success = 1
                                self.FluidsTreeWidget.topLevelItem(
                                    top_fluid_type
                                ).child(child_fluid_feat).child(
                                    child_scenario
                                ).removeChild(
                                    self.FluidsTreeWidget.topLevelItem(top_fluid_type)
                                    .child(child_fluid_feat)
                                    .child(child_scenario)
                                    .child(child_entity)
                                )
                                if (
                                    self.FluidsTreeWidget.topLevelItem(top_fluid_type)
                                    .child(child_fluid_feat)
                                    .child(child_scenario)
                                    .childCount()
                                    == 0
                                ):
                                    self.FluidsTreeWidget.topLevelItem(
                                        top_fluid_type
                                    ).child(child_fluid_feat).removeChild(
                                        self.FluidsTreeWidget.topLevelItem(
                                            top_fluid_type
                                        )
                                        .child(child_fluid_feat)
                                        .child(child_scenario)
                                    )
                                    if (
                                        self.FluidsTreeWidget.topLevelItem(
                                            top_fluid_type
                                        )
                                        .child(child_fluid_feat)
                                        .childCount()
                                        == 0
                                    ):
                                        self.FluidsTreeWidget.topLevelItem(
                                            top_fluid_type
                                        ).removeChild(
                                            self.FluidsTreeWidget.topLevelItem(
                                                top_fluid_type
                                            ).child(child_fluid_feat)
                                        )
                                        if (
                                            self.FluidsTreeWidget.topLevelItem(
                                                top_fluid_type
                                            ).childCount()
                                            == 0
                                        ):
                                            self.FluidsTreeWidget.takeTopLevelItem(
                                                top_fluid_type
                                            )
                                break
                        if success == 1:
                            break
                    if success == 1:
                        break
                if success == 1:
                    break

    def update_fluids_topology_tree_added(self, new_list=None, sec_uid=None):
        """Update topology tree without creating a new model"""
        uid_list = list(new_list["uid"])
        if sec_uid:
            for i, uid in enumerate(new_list["uid"]):
                if (
                    sec_uid
                    != self.parent.geol_coll.df.loc[
                        self.parent.geol_coll.df["uid"] == uid, "x_section"
                    ].values[0]
                ):
                    del uid_list[i]
        for uid in uid_list:
            if (
                self.FluidsTopologyTreeWidget.findItems(
                    self.parent.fluids_coll.get_uid_topological_type(uid),
                    Qt.MatchExactly,
                    0,
                )
                != []
            ):
                """Already exists a TreeItem (1 level) for the topological type"""
                counter_1 = 0
                for child_1 in range(
                    self.FluidsTopologyTreeWidget.findItems(
                        self.parent.fluids_coll.get_uid_topological_type(uid),
                        Qt.MatchExactly,
                        0,
                    )[0].childCount()
                ):
                    """for cycle that loops n times as the number of subItems in the specific topological type branch"""
                    if self.FluidsTopologyTreeWidget.findItems(
                        self.parent.fluids_coll.get_uid_topological_type(uid),
                        Qt.MatchExactly,
                        0,
                    )[0].child(child_1).text(
                        0
                    ) == self.parent.fluids_coll.get_uid_scenario(
                        uid
                    ):
                        counter_1 += 1
                if counter_1 != 0:
                    for child_1 in range(
                        self.FluidsTopologyTreeWidget.findItems(
                            self.parent.fluids_coll.get_uid_topological_type(uid),
                            Qt.MatchExactly,
                            0,
                        )[0].childCount()
                    ):
                        if self.FluidsTopologyTreeWidget.findItems(
                            self.parent.fluids_coll.get_uid_topological_type(uid),
                            Qt.MatchExactly,
                            0,
                        )[0].child(child_1).text(
                            0
                        ) == self.parent.fluids_coll.get_uid_scenario(
                            uid
                        ):
                            """Same topological type and scenario"""
                            property_combo = QComboBox()
                            property_combo.uid = uid
                            property_combo.addItem("none")
                            property_combo.addItem("X")
                            property_combo.addItem("Y")
                            property_combo.addItem("Z")
                            for (
                                prop
                            ) in self.parent.fluids_coll.get_uid_properties_names(uid):
                                property_combo.addItem(prop)
                            name = self.parent.fluids_coll.get_uid_name(uid)
                            tlevel_3 = QTreeWidgetItem(
                                self.FluidsTopologyTreeWidget.findItems(
                                    self.parent.fluids_coll.get_uid_topological_type(
                                        uid
                                    ),
                                    Qt.MatchExactly,
                                    0,
                                )[0].child(child_1),
                                [name, uid],
                            )
                            self.FluidsTopologyTreeWidget.setItemWidget(
                                tlevel_3, 2, property_combo
                            )
                            property_combo.currentIndexChanged.connect(
                                lambda: self.toggle_property()
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
                            self.TopologyTreeWidget.insertTopLevelItem(0, tlevel_3)
                            break
                else:
                    """Same topological type, different scenario"""
                    tlevel_2 = QTreeWidgetItem(
                        self.FluidsTopologyTreeWidget.findItems(
                            self.parent.fluids_coll.get_uid_topological_type(uid),
                            Qt.MatchExactly,
                            0,
                        )[0],
                        [self.parent.fluids_coll.get_uid_scenario(uid)],
                    )
                    tlevel_2.setFlags(
                        tlevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
                    )
                    self.FluidsTopologyTreeWidget.insertTopLevelItem(0, tlevel_2)
                    property_combo = QComboBox()
                    property_combo.uid = uid
                    property_combo.addItem("none")
                    property_combo.addItem("X")
                    property_combo.addItem("Y")
                    property_combo.addItem("Z")
                    for prop in self.parent.fluids_coll.get_uid_properties_names(uid):
                        property_combo.addItem(prop)
                    name = self.parent.fluids_coll.get_uid_name(uid)
                    tlevel_3 = QTreeWidgetItem(tlevel_2, [name, uid])
                    self.FluidsTopologyTreeWidget.setItemWidget(
                        tlevel_3, 2, property_combo
                    )
                    property_combo.currentIndexChanged.connect(
                        lambda: self.toggle_property()
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
                    self.FluidsTopologyTreeWidget.insertTopLevelItem(0, tlevel_3)
                    break
            else:
                """Different topological type and scenario"""
                tlevel_1 = QTreeWidgetItem(
                    self.FluidsTopologyTreeWidget,
                    [self.parent.fluids_coll.get_uid_topological_type(uid)],
                )
                tlevel_1.setFlags(
                    tlevel_1.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
                )
                self.FluidsTopologyTreeWidget.insertTopLevelItem(0, tlevel_1)
                tlevel_2 = QTreeWidgetItem(
                    tlevel_1, [self.parent.fluids_coll.get_uid_scenario(uid)]
                )
                tlevel_2.setFlags(
                    tlevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
                )
                self.FluidsTopologyTreeWidget.insertTopLevelItem(0, tlevel_2)
                property_combo = QComboBox()
                property_combo.uid = uid
                property_combo.addItem("none")
                property_combo.addItem("X")
                property_combo.addItem("Y")
                property_combo.addItem("Z")
                for prop in self.parent.fluids_coll.get_uid_properties_names(uid):
                    property_combo.addItem(prop)
                name = self.parent.fluids_coll.get_uid_name(uid)
                tlevel_3 = QTreeWidgetItem(tlevel_2, [name, uid])
                self.FluidsTopologyTreeWidget.setItemWidget(tlevel_3, 2, property_combo)
                property_combo.currentIndexChanged.connect(
                    lambda: self.toggle_property()
                )
                tlevel_3.setFlags(tlevel_3.flags() | Qt.ItemIsUserCheckable)
                if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                    tlevel_3.setCheckState(0, Qt.Checked)
                elif not self.actors_df.loc[
                    self.actors_df["uid"] == uid, "show"
                ].values[0]:
                    tlevel_3.setCheckState(0, Qt.Unchecked)
                self.FluidsTopologyTreeWidget.insertTopLevelItem(0, tlevel_3)
                break
        self.FluidsTopologyTreeWidget.itemChanged.connect(
            self.toggle_fluids_topology_visibility
        )
        self.FluidsTopologyTreeWidget.expandAll()

    def update_fluids_topology_tree_removed(self, removed_list=None):
        """When fluid entity is removed, update Topology Tree without building a new model"""
        success = 0
        for uid in removed_list:
            for top_topo_type in range(
                self.FluidsTopologyTreeWidget.topLevelItemCount()
            ):
                """Iterate through every Topological Type top level"""
                for child_scenario in range(
                    self.FluidsTopologyTreeWidget.topLevelItem(
                        top_topo_type
                    ).childCount()
                ):
                    """Iterate through every Scenario child"""
                    for child_entity in range(
                        self.FluidsTopologyTreeWidget.topLevelItem(top_topo_type)
                        .child(child_scenario)
                        .childCount()
                    ):
                        """Iterate through every Entity child"""
                        if (
                            self.FluidsTopologyTreeWidget.topLevelItem(top_topo_type)
                            .child(child_scenario)
                            .child(child_entity)
                            .text(1)
                            == uid
                        ):
                            """Complete check: entity found has the uid of the entity we need to remove. Delete child, then ensure no Child or Top Level remain empty"""
                            success = 1
                            self.FluidsTopologyTreeWidget.topLevelItem(
                                top_topo_type
                            ).child(child_scenario).removeChild(
                                self.FluidsTopologyTreeWidget.topLevelItem(
                                    top_topo_type
                                )
                                .child(child_scenario)
                                .child(child_entity)
                            )
                            if (
                                self.FluidsTopologyTreeWidget.topLevelItem(
                                    top_topo_type
                                )
                                .child(child_scenario)
                                .childCount()
                                == 0
                            ):
                                self.FluidsTopologyTreeWidget.topLevelItem(
                                    top_topo_type
                                ).removeChild(
                                    self.FluidsTopologyTreeWidget.topLevelItem(
                                        top_topo_type
                                    ).child(child_scenario)
                                )
                                if (
                                    self.FluidsTopologyTreeWidget.topLevelItem(
                                        top_topo_type
                                    ).childCount()
                                    == 0
                                ):
                                    self.FluidsTopologyTreeWidget.takeTopLevelItem(
                                        top_topo_type
                                    )
                            break
                    if success == 1:
                        break
                if success == 1:
                    break

    def update_fluids_checkboxes(self, uid=None, uid_checkState=None):
        """Update checkboxes in fluid tree, called when state changed in topology tree."""
        item = self.FluidsTreeWidget.findItems(
            uid, Qt.MatchFixedString | Qt.MatchRecursive, 1
        )[0]
        if uid_checkState == Qt.Checked:
            item.setCheckState(0, Qt.Checked)
        elif uid_checkState == Qt.Unchecked:
            item.setCheckState(0, Qt.Unchecked)

    def update_fluids_topology_checkboxes(self, uid=None, uid_checkState=None):
        """Update checkboxes in topology tree, called when state changed in geology tree."""
        item = self.FluidsTopologyTreeWidget.findItems(
            uid, Qt.MatchFixedString | Qt.MatchRecursive, 1
        )[0]
        if uid_checkState == Qt.Checked:
            item.setCheckState(0, Qt.Checked)
        elif uid_checkState == Qt.Unchecked:
            item.setCheckState(0, Qt.Unchecked)

    def toggle_fluids_topology_visibility(self, item, column):
        """Called by self.FluidsTreeWidget.itemChanged.connect(self.toggle_fluids_topology_visibility) and self.FluidsTopologyTreeWidget.itemChanged.connect(self.toggle_fluids_topology_visibility)"""
        name = item.text(0)  # not used
        uid = item.text(1)
        uid_checkState = item.checkState(0)
        if (
            uid
        ):  # needed to skip messages from upper levels of tree that do not broadcast uid's
            if uid_checkState == Qt.Checked:
                if not self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[
                    0
                ]:
                    self.actors_df.loc[self.actors_df["uid"] == uid, "show"] = True
                    self.set_actor_visible(uid=uid, visible=True)
            elif uid_checkState == Qt.Unchecked:
                if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                    self.actors_df.loc[self.actors_df["uid"] == uid, "show"] = False
                    self.set_actor_visible(uid=uid, visible=False)
            """Before updating checkboxes, disconnect signals to fluid and topology tree, if they are set,
            to avoid a nasty loop that disrupts the trees, then reconnect them (it is also possible that
            they are automatically reconnected whe the trees are rebuilt."""
            self.FluidsTreeWidget.itemChanged.disconnect()
            self.FluidsTopologyTreeWidget.itemChanged.disconnect()
            self.update_fluids_checkboxes(uid=uid, uid_checkState=uid_checkState)
            self.update_fluids_topology_checkboxes(
                uid=uid, uid_checkState=uid_checkState
            )
            self.FluidsTreeWidget.itemChanged.connect(
                self.toggle_fluids_topology_visibility
            )
            self.FluidsTopologyTreeWidget.itemChanged.connect(
                self.toggle_fluids_topology_visibility
            )

    """Methods used to build and update the backgrounds_misti tree."""

    def create_backgrounds_tree(self, sec_uid=None):
        """Create Backgrounds tree with checkboxes and properties"""
        self.BackgroundsTreeWidget.clear()
        self.BackgroundsTreeWidget.setColumnCount(3)
        self.BackgroundsTreeWidget.setHeaderLabels(
            ["Type > Feature > Name", "uid", "property"]
        )
        self.BackgroundsTreeWidget.hideColumn(1)  # hide the uid column
        self.BackgroundsTreeWidget.setItemsExpandable(True)
        if sec_uid:
            background_types = pd_unique(
                self.parent.backgrounds_coll.df.loc[
                    (self.parent.backgrounds_coll.df["x_section"] == sec_uid),
                    "background_type",
                ]
            )
        else:
            background_types = pd_unique(
                self.parent.backgrounds_coll.df["background_type"]
            )
        for background_type in background_types:
            flevel_1 = QTreeWidgetItem(
                self.BackgroundsTreeWidget, [background_type]
            )  # self.BackgroundsTreeWidget as parent -> top level
            flevel_1.setFlags(
                flevel_1.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
            )
            if sec_uid:
                background_features = pd_unique(
                    self.parent.backgrounds_coll.df.loc[
                        (
                            self.parent.backgrounds_coll.df["background_type"]
                            == background_type
                        )
                        & (self.parent.backgrounds_coll.df["x_section"] == sec_uid),
                        "background_feature",
                    ]
                )
            else:
                background_features = pd_unique(
                    self.parent.backgrounds_coll.df.loc[
                        self.parent.backgrounds_coll.df["background_type"]
                        == background_type,
                        "background_feature",
                    ]
                )
            for feature in background_features:
                flevel_2 = QTreeWidgetItem(
                    flevel_1, [feature]
                )  # flevel_1 as parent -> 1st middle level
                flevel_2.setFlags(
                    flevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
                )
                if sec_uid:
                    uids = self.parent.backgrounds_coll.df.loc[
                        (
                            self.parent.backgrounds_coll.df["background_type"]
                            == background_type
                        )
                        & (
                            self.parent.backgrounds_coll.df["background_feature"]
                            == feature
                        )
                        & (self.parent.backgrounds_coll.df["x_section"] == sec_uid),
                        "uid",
                    ].to_list()
                else:
                    uids = self.parent.backgrounds_coll.df.loc[
                        (
                            self.parent.backgrounds_coll.df["background_type"]
                            == background_type
                        )
                        & (
                            self.parent.backgrounds_coll.df["background_feature"]
                            == feature
                        ),
                        "uid",
                    ].to_list()
                for uid in uids:
                    property_combo = QComboBox()
                    property_combo.uid = uid
                    property_combo.name = "Annotations"
                    property_combo.addItem("none")
                    property_combo.addItem("name")
                    for prop in self.parent.backgrounds_coll.get_uid_properties_names(
                        uid
                    ):
                        property_combo.addItem(prop)
                    name = self.parent.backgrounds_coll.df.loc[
                        (self.parent.backgrounds_coll.df["uid"] == uid), "name"
                    ].values[0]
                    flevel_3 = QTreeWidgetItem(
                        flevel_2, [name, uid]
                    )  # flevel_3 as parent -> lower level
                    self.BackgroundsTreeWidget.setItemWidget(
                        flevel_3, 2, property_combo
                    )
                    property_combo.currentIndexChanged.connect(
                        lambda: self.toggle_property()
                    )
                    flevel_3.setFlags(flevel_3.flags() | Qt.ItemIsUserCheckable)
                    if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[
                        0
                    ]:
                        flevel_3.setCheckState(0, Qt.Checked)
                    elif not self.actors_df.loc[
                        self.actors_df["uid"] == uid, "show"
                    ].values[0]:
                        flevel_3.setCheckState(0, Qt.Unchecked)
        """Send messages. Note that with tristate several signals are emitted in a sequence, one for each
        changed item, but upper levels do not broadcast uid's so they are filtered in the toggle method."""
        self.BackgroundsTreeWidget.itemChanged.connect(
            self.toggle_backgrounds_topology_visibility
        )
        self.BackgroundsTreeWidget.expandAll()

    def create_backgrounds_topology_tree(self, sec_uid=None):
        """Create topology tree with checkboxes and properties"""
        self.BackgroundsTopologyTreeWidget.clear()
        self.BackgroundsTopologyTreeWidget.setColumnCount(3)
        self.BackgroundsTreeWidget.setHeaderLabels(
            ["Type > Feature > Name", "uid", "property"]
        )
        self.BackgroundsTopologyTreeWidget.hideColumn(1)  # hide the uid column
        self.BackgroundsTopologyTreeWidget.setItemsExpandable(True)
        if sec_uid:
            filtered_topo = self.parent.backgrounds_coll.df.loc[
                (self.parent.backgrounds_coll.df["x_section"] == sec_uid),
                "topological_type",
            ]
            topo_types = pd_unique(filtered_topo)
        else:
            topo_types = pd_unique(self.parent.backgrounds_coll.df["topological_type"])
        for topo_type in topo_types:
            tlevel_1 = QTreeWidgetItem(
                self.BackgroundsTopologyTreeWidget, [topo_type]
            )  # self.GeologyTreeWidget as parent -> top level
            tlevel_1.setFlags(
                tlevel_1.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
            )

            for background_type in pd_unique(
                self.parent.backgrounds_coll.df.loc[
                    self.parent.backgrounds_coll.df["topological_type"] == topo_type,
                    "background_type",
                ]
            ):
                tlevel_2 = QTreeWidgetItem(
                    tlevel_1, [background_type]
                )  # tlevel_1 as parent -> middle level
                tlevel_2.setFlags(
                    tlevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
                )
                if sec_uid:
                    uids = self.parent.backgrounds_coll.df.loc[
                        (
                            self.parent.backgrounds_coll.df["topological_type"]
                            == topo_type
                        )
                        & (
                            self.parent.backgrounds_coll.df["background_type"]
                            == background_type
                        )
                        & (self.parent.backgrounds_coll.df["x_section"] == sec_uid),
                        "uid",
                    ].to_list()
                else:
                    uids = self.parent.backgrounds_coll.df.loc[
                        (
                            self.parent.backgrounds_coll.df["topological_type"]
                            == topo_type
                        )
                        & (
                            self.parent.backgrounds_coll.df["background_type"]
                            == background_type
                        ),
                        "uid",
                    ].to_list()
                for uid in uids:
                    property_combo = QComboBox()
                    property_combo.uid = uid
                    property_combo.name = "Annotations"
                    property_combo.addItem("none")
                    property_combo.addItem("name")
                    for prop in self.parent.backgrounds_coll.get_uid_properties_names(
                        uid
                    ):
                        property_combo.addItem(prop)
                    name = self.parent.backgrounds_coll.df.loc[
                        self.parent.backgrounds_coll.df["uid"] == uid, "name"
                    ].values[0]
                    tlevel_3 = QTreeWidgetItem(
                        tlevel_2, [name, uid]
                    )  # tlevel_2 as parent -> lower level
                    self.BackgroundsTopologyTreeWidget.setItemWidget(
                        tlevel_3, 2, property_combo
                    )
                    property_combo.currentIndexChanged.connect(
                        lambda: self.toggle_property()
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
        """Send messages. Note that with tristate several signals are emitted in a sequence, one for each
        changed item, but upper levels do not broadcast uid's so they are filtered in the toggle method."""
        self.BackgroundsTopologyTreeWidget.itemChanged.connect(
            self.toggle_backgrounds_topology_visibility
        )
        self.BackgroundsTopologyTreeWidget.expandAll()

    def update_backgrounds_tree_added(self, new_list=None, sec_uid=None):
        """Update background tree without creating a new model"""

        uid_list = list(new_list["uid"])
        if sec_uid:
            for i, uid in enumerate(new_list["uid"]):
                if (
                    sec_uid
                    != self.parent.backgrounds_coll.df.loc[
                        self.parent.backgrounds_coll.df["uid"] == uid, "x_section"
                    ].values[0]
                ):
                    del uid_list[i]
        for uid in uid_list:
            if (
                self.BackgroundsTreeWidget.findItems(
                    self.parent.backgrounds_coll.get_uid_background_type(uid),
                    Qt.MatchExactly,
                    0,
                )
                != []
            ):
                """Already exists a TreeItem (1 level) for the background type"""
                counter_1 = 0
                for child_1 in range(
                    self.BackgroundsTreeWidget.findItems(
                        self.parent.backgrounds_coll.get_uid_background_type(uid),
                        Qt.MatchExactly,
                        0,
                    )[0].childCount()
                ):
                    """for cycle that loops n times as the number of subItems in the specific background type branch"""
                    if self.BackgroundsTreeWidget.findItems(
                        self.parent.backgrounds_coll.get_uid_background_type(uid),
                        Qt.MatchExactly,
                        0,
                    )[0].child(child_1).text(
                        0
                    ) == self.parent.backgrounds_coll.get_uid_background_feature(
                        uid
                    ):
                        counter_1 += 1
                if counter_1 != 0:
                    for child_1 in range(
                        self.BackgroundsTreeWidget.findItems(
                            self.parent.backgrounds_coll.get_uid_background_type(uid),
                            Qt.MatchExactly,
                            0,
                        )[0].childCount()
                    ):
                        if self.BackgroundsTreeWidget.findItems(
                            self.parent.backgrounds_coll.get_uid_background_type(uid),
                            Qt.MatchExactly,
                            0,
                        )[0].child(child_1).text(
                            0
                        ) == self.parent.backgrounds_coll.get_uid_background_feature(
                            uid
                        ):
                            """Already exists a TreeItem (2 level) for the background feature"""

                            """Same background type and background feature"""
                            property_combo = QComboBox()
                            property_combo.uid = uid
                            property_combo.name = "Annotations"
                            property_combo.addItem("none")
                            property_combo.addItem("name")
                            for (
                                prop
                            ) in self.parent.backgrounds_coll.get_uid_properties_names(
                                uid
                            ):
                                property_combo.addItem(prop)
                            name = self.parent.backgrounds_coll.get_uid_name(uid)
                            flevel_3 = QTreeWidgetItem(
                                self.BackgroundsTreeWidget.findItems(
                                    self.parent.backgrounds_coll.get_uid_background_type(
                                        uid
                                    ),
                                    Qt.MatchExactly,
                                    0,
                                )[0].child(child_1),
                                [name, uid],
                            )
                            self.BackgroundsTreeWidget.setItemWidget(
                                flevel_3, 2, property_combo
                            )
                            property_combo.currentIndexChanged.connect(
                                lambda: self.toggle_property()
                            )
                            flevel_3.setFlags(flevel_3.flags() | Qt.ItemIsUserCheckable)
                            if self.actors_df.loc[
                                self.actors_df["uid"] == uid, "show"
                            ].values[0]:
                                flevel_3.setCheckState(0, Qt.Checked)
                            elif not self.actors_df.loc[
                                self.actors_df["uid"] == uid, "show"
                            ].values[0]:
                                flevel_3.setCheckState(0, Qt.Unchecked)
                            self.BackgroundsTreeWidget.insertTopLevelItem(0, flevel_3)
                            break
                else:
                    """Same background type, different background feature"""
                    flevel_2 = QTreeWidgetItem(
                        self.BackgroundsTreeWidget.findItems(
                            self.parent.backgrounds_coll.get_uid_background_type(uid),
                            Qt.MatchExactly,
                            0,
                        )[0],
                        [self.parent.backgrounds_coll.get_uid_background_feature(uid)],
                    )
                    flevel_2.setFlags(
                        flevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
                    )
                    self.BackgroundsTreeWidget.insertTopLevelItem(0, flevel_2)
                    property_combo = QComboBox()
                    property_combo.uid = uid
                    property_combo.name = "Annotations"
                    property_combo.addItem("none")
                    property_combo.addItem("name")
                    for prop in self.parent.backgrounds_coll.get_uid_properties_names(
                        uid
                    ):
                        property_combo.addItem(prop)
                    name = self.parent.backgrounds_coll.get_uid_name(uid)

                    flevel_3 = QTreeWidgetItem(flevel_2, [name, uid])
                    self.BackgroundsTreeWidget.setItemWidget(
                        flevel_3, 2, property_combo
                    )
                    property_combo.currentIndexChanged.connect(
                        lambda: self.toggle_property()
                    )
                    flevel_3.setFlags(flevel_3.flags() | Qt.ItemIsUserCheckable)
                    if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[
                        0
                    ]:
                        flevel_3.setCheckState(0, Qt.Checked)
                    elif not self.actors_df.loc[
                        self.actors_df["uid"] == uid, "show"
                    ].values[0]:
                        flevel_3.setCheckState(0, Qt.Unchecked)
                    self.BackgroundsTreeWidget.insertTopLevelItem(0, flevel_3)
                    break
            else:
                """Different background type and background feature"""
                flevel_1 = QTreeWidgetItem(
                    self.BackgroundsTreeWidget,
                    [self.parent.backgrounds_coll.get_uid_background_type(uid)],
                )
                flevel_1.setFlags(
                    flevel_1.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
                )
                self.BackgroundsTreeWidget.insertTopLevelItem(0, flevel_1)
                flevel_2 = QTreeWidgetItem(
                    flevel_1,
                    [self.parent.backgrounds_coll.get_uid_background_feature(uid)],
                )
                flevel_2.setFlags(
                    flevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
                )
                self.BackgroundsTreeWidget.insertTopLevelItem(0, flevel_2)
                property_combo = QComboBox()
                property_combo.uid = uid
                property_combo.name = "Annotations"
                property_combo.addItem("none")
                property_combo.addItem("name")
                for prop in self.parent.backgrounds_coll.get_uid_properties_names(uid):
                    property_combo.addItem(prop)
                name = self.parent.backgrounds_coll.get_uid_name(uid)
                flevel_3 = QTreeWidgetItem(flevel_2, [name, uid])
                self.BackgroundsTreeWidget.setItemWidget(flevel_3, 2, property_combo)
                property_combo.currentIndexChanged.connect(
                    lambda: self.toggle_property()
                )
                flevel_3.setFlags(flevel_3.flags() | Qt.ItemIsUserCheckable)
                if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                    flevel_3.setCheckState(0, Qt.Checked)
                elif not self.actors_df.loc[
                    self.actors_df["uid"] == uid, "show"
                ].values[0]:
                    flevel_3.setCheckState(0, Qt.Unchecked)
                self.BackgroundsTreeWidget.insertTopLevelItem(0, flevel_3)
                break
        self.BackgroundsTreeWidget.itemChanged.connect(
            self.toggle_backgrounds_topology_visibility
        )
        self.BackgroundsTreeWidget.expandAll()

    def update_backgrounds_tree_removed(self, removed_list=None):  # second attchild_background_featempt
        """When background entity is removed, update Geology Tree without building a new model"""
        success = 0
        for uid in removed_list:
            for top_background_type in range(
                self.BackgroundsTreeWidget.topLevelItemCount()
            ):
                """Iterate through every background Type top level"""

                for child_background_feat in range(
                    self.BackgroundsTreeWidget.topLevelItem(
                        top_background_type
                    ).childCount()
                ):
                    """Iterate through every background Feature child"""

                    for child_entity in range(
                        self.BackgroundsTreeWidget.topLevelItem(top_background_type)
                        .child(child_background_feat)
                        .childCount()
                    ):
                        """Iterate through every Entity child"""

                        if (
                            self.BackgroundsTreeWidget.topLevelItem(top_background_type)
                            .child(child_background_feat)
                            .child(child_entity)
                            .text(1)
                            == uid
                        ):
                            """Complete check: entity found has the uid of the entity we need to remove. Delete child, then ensure no Child or Top Level remain empty"""
                            success = 1
                            self.BackgroundsTreeWidget.topLevelItem(
                                top_background_type
                            ).child(child_background_feat).removeChild(
                                self.BackgroundsTreeWidget.topLevelItem(
                                    top_background_type
                                )
                                .child(child_background_feat)
                                .child(child_entity)
                            )
                            if (
                                self.BackgroundsTreeWidget.topLevelItem(
                                    top_background_type
                                )
                                .child(child_background_feat)
                                .childCount()
                                == 0
                            ):
                                self.BackgroundsTreeWidget.topLevelItem(
                                    top_background_type
                                ).child(child_background_feat).removeChild(
                                    self.BackgroundsTreeWidget.topLevelItem(
                                        top_background_type
                                    ).child(child_background_feat)
                                )
                                if (
                                    self.BackgroundsTreeWidget.topLevelItem(
                                        top_background_type
                                    ).childCount()
                                    == 0
                                ):
                                    self.BackgroundsTreeWidget.takeTopLevelItem(
                                        top_background_type
                                    )
                            break
                    if success == 1:
                        break
                if success == 1:
                    break
            if success == 1:
                break

    def update_backgrounds_topology_tree_added(self, new_list=None, sec_uid=None):
        """Update topology tree without creating a new model"""
        uid_list = list(new_list["uid"])
        if sec_uid:
            for i, uid in enumerate(new_list["uid"]):
                if (
                    sec_uid
                    != self.parent.backgrounds_coll.df.loc[
                        self.parent.backgrounds_coll.df["uid"] == uid, "x_section"
                    ].values[0]
                ):
                    del uid_list[i]
        for uid in uid_list:
            if (
                self.BackgroundsTopologyTreeWidget.findItems(
                    self.parent.backgrounds_coll.get_uid_topological_type(uid),
                    Qt.MatchExactly,
                    0,
                )
                != []
            ):
                """Already exists a TreeItem (1 level) for the topological type"""
                counter_1 = 0
                for child_1 in range(
                    self.BackgroundsTopologyTreeWidget.findItems(
                        self.parent.backgrounds_coll.get_uid_topological_type(uid),
                        Qt.MatchExactly,
                        0,
                    )[0].childCount()
                ):
                    """for cycle that loops n times as the number of subItems in the specific topological type branch"""
                    if self.BackgroundsTopologyTreeWidget.findItems(
                        self.parent.backgrounds_coll.get_uid_topological_type(uid),
                        Qt.MatchExactly,
                        0,
                    )[0].child(child_1).text(
                        0
                    ) == self.parent.backgrounds_coll.get_uid_background_feature(
                        uid
                    ):
                        counter_1 += 1
                if counter_1 != 0:
                    for child_1 in range(
                        self.BackgroundsTopologyTreeWidget.findItems(
                            self.parent.backgrounds_coll.get_uid_topological_type(uid),
                            Qt.MatchExactly,
                            0,
                        )[0].childCount()
                    ):
                        if self.BackgroundsTopologyTreeWidget.findItems(
                            self.parent.backgrounds_coll.get_uid_topological_type(uid),
                            Qt.MatchExactly,
                            0,
                        )[0].child(child_1).text(
                            0
                        ) == self.parent.backgrounds_coll.get_uid_background_feature(
                            uid
                        ):
                            """Same topological type and feature"""
                            property_combo = QComboBox()
                            property_combo.uid = uid
                            property_combo.name = "Annotations"
                            property_combo.addItem("none")
                            property_combo.addItem("name")
                            for (
                                prop
                            ) in self.parent.backgrounds_coll.get_uid_properties_names(
                                uid
                            ):
                                property_combo.addItem(prop)
                            name = self.parent.backgrounds_coll.get_uid_name(uid)
                            tlevel_3 = QTreeWidgetItem(
                                self.BackgroundsTopologyTreeWidget.findItems(
                                    self.parent.backgrounds_coll.get_uid_topological_type(
                                        uid
                                    ),
                                    Qt.MatchExactly,
                                    0,
                                )[0].child(child_1),
                                [name, uid],
                            )
                            self.BackgroundsTopologyTreeWidget.setItemWidget(
                                tlevel_3, 2, property_combo
                            )
                            property_combo.currentIndexChanged.connect(
                                lambda: self.toggle_property()
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
                            self.BackgroundsTopologyTreeWidget.insertTopLevelItem(
                                0, tlevel_3
                            )
                            break
                else:
                    """Same topological type, different feature"""
                    tlevel_2 = QTreeWidgetItem(
                        self.BackgroundsTopologyTreeWidget.findItems(
                            self.parent.backgrounds_coll.get_uid_topological_type(uid),
                            Qt.MatchExactly,
                            0,
                        )[0],
                        [self.parent.backgrounds_coll.get_uid_background_feature(uid)],
                    )
                    tlevel_2.setFlags(
                        tlevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
                    )
                    self.BackgroundsTopologyTreeWidget.insertTopLevelItem(0, tlevel_2)
                    property_combo = QComboBox()
                    property_combo.uid = uid
                    property_combo.name = "Annotations"
                    property_combo.addItem("none")
                    property_combo.addItem("name")
                    for prop in self.parent.backgrounds_coll.get_uid_properties_names(
                        uid
                    ):
                        property_combo.addItem(prop)
                    name = self.parent.backgrounds_coll.get_uid_name(uid)
                    tlevel_3 = QTreeWidgetItem(tlevel_2, [name, uid])
                    self.BackgroundsTopologyTreeWidget.setItemWidget(
                        tlevel_3, 2, property_combo
                    )
                    property_combo.currentIndexChanged.connect(
                        lambda: self.toggle_property()
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
                    self.BackgroundsTopologyTreeWidget.insertTopLevelItem(0, tlevel_3)
                    break
            else:
                """Different topological type and feature"""
                tlevel_1 = QTreeWidgetItem(
                    self.BackgroundsTopologyTreeWidget,
                    [self.parent.backgrounds_coll.get_uid_topological_type(uid)],
                )
                tlevel_1.setFlags(
                    tlevel_1.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
                )
                self.BackgroundsTopologyTreeWidget.insertTopLevelItem(0, tlevel_1)
                tlevel_2 = QTreeWidgetItem(
                    tlevel_1,
                    [self.parent.backgrounds_coll.get_uid_background_feature(uid)],
                )
                tlevel_2.setFlags(
                    tlevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
                )
                self.BackgroundsTopologyTreeWidget.insertTopLevelItem(0, tlevel_2)
                property_combo = QComboBox()
                property_combo.uid = uid
                property_combo.name = "Annotations"
                property_combo.addItem("none")
                property_combo.addItem("name")
                for prop in self.parent.backgrounds_coll.get_uid_properties_names(uid):
                    property_combo.addItem(prop)
                name = self.parent.backgrounds_coll.get_uid_name(uid)
                tlevel_3 = QTreeWidgetItem(tlevel_2, [name, uid])
                self.BackgroundsTopologyTreeWidget.setItemWidget(
                    tlevel_3, 2, property_combo
                )
                property_combo.currentIndexChanged.connect(
                    lambda: self.toggle_property()
                )
                tlevel_3.setFlags(tlevel_3.flags() | Qt.ItemIsUserCheckable)
                if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                    tlevel_3.setCheckState(0, Qt.Checked)
                elif not self.actors_df.loc[
                    self.actors_df["uid"] == uid, "show"
                ].values[0]:
                    tlevel_3.setCheckState(0, Qt.Unchecked)
                self.BackgroundsTopologyTreeWidget.insertTopLevelItem(0, tlevel_3)
                break
        self.BackgroundsTopologyTreeWidget.itemChanged.connect(
            self.toggle_geology_topology_visibility
        )
        self.BackgroundsTopologyTreeWidget.expandAll()

    def update_backgrounds_topology_tree_removed(self, removed_list=None):
        """When background entity is removed, update Topology Tree without building a new model"""
        success = 0
        for uid in removed_list:
            for top_topo_type in range(
                self.BackgroundsTopologyTreeWidget.topLevelItemCount()
            ):
                """Iterate through every Topological Type top level"""
                for child_scenario in range(
                    self.BackgroundsTopologyTreeWidget.topLevelItem(
                        top_topo_type
                    ).childCount()
                ):
                    """Iterate through every Scenario child"""
                    for child_entity in range(
                        self.BackgroundsTopologyTreeWidget.topLevelItem(top_topo_type)
                        .child(child_scenario)
                        .childCount()
                    ):
                        """Iterate through every Entity child"""
                        if (
                            self.BackgroundsTopologyTreeWidget.topLevelItem(
                                top_topo_type
                            )
                            .child(child_scenario)
                            .child(child_entity)
                            .text(1)
                            == uid
                        ):
                            """Complete check: entity found has the uid of the entity we need to remove. Delete child, then ensure no Child or Top Level remain empty"""
                            success = 1
                            self.BackgroundsTopologyTreeWidget.topLevelItem(
                                top_topo_type
                            ).child(child_scenario).removeChild(
                                self.BackgroundsTopologyTreeWidget.topLevelItem(
                                    top_topo_type
                                )
                                .child(child_scenario)
                                .child(child_entity)
                            )
                            if (
                                self.BackgroundsTopologyTreeWidget.topLevelItem(
                                    top_topo_type
                                )
                                .child(child_scenario)
                                .childCount()
                                == 0
                            ):
                                self.BackgroundsTopologyTreeWidget.topLevelItem(
                                    top_topo_type
                                ).removeChild(
                                    self.BackgroundsTopologyTreeWidget.topLevelItem(
                                        top_topo_type
                                    ).child(child_scenario)
                                )
                                if (
                                    self.BackgroundsTopologyTreeWidget.topLevelItem(
                                        top_topo_type
                                    ).childCount()
                                    == 0
                                ):
                                    self.BackgroundsTopologyTreeWidget.takeTopLevelItem(
                                        top_topo_type
                                    )
                            break
                    if success == 1:
                        break
                if success == 1:
                    break

    def update_backgrounds_checkboxes(self, uid=None, uid_checkState=None):
        """Update checkboxes in background tree, called when state changed in topology tree."""
        item = self.BackgroundsTreeWidget.findItems(
            uid, Qt.MatchFixedString | Qt.MatchRecursive, 1
        )[0]
        if uid_checkState == Qt.Checked:
            item.setCheckState(0, Qt.Checked)
        elif uid_checkState == Qt.Unchecked:
            item.setCheckState(0, Qt.Unchecked)

    def update_backgrounds_topology_checkboxes(self, uid=None, uid_checkState=None):
        """Update checkboxes in topology tree, called when state changed in geology tree."""
        item = self.BackgroundsTopologyTreeWidget.findItems(
            uid, Qt.MatchFixedString | Qt.MatchRecursive, 1
        )[0]
        if uid_checkState == Qt.Checked:
            item.setCheckState(0, Qt.Checked)
        elif uid_checkState == Qt.Unchecked:
            item.setCheckState(0, Qt.Unchecked)

    def toggle_backgrounds_topology_visibility(self, item, column):
        """Called by self.BackgroundsTreeWidget.itemChanged.connect(self.toggle_backgrounds_topology_visibility) and self.BackgroundsTopologyTreeWidget.itemChanged.connect(self.toggle_backgrounds_topology_visibility)"""
        name = item.text(0)  # not used
        uid = item.text(1)
        uid_checkState = item.checkState(0)
        if (
            uid
        ):  # needed to skip messages from upper levels of tree that do not broadcast uid's
            if uid_checkState == Qt.Checked:
                if not self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[
                    0
                ]:
                    self.actors_df.loc[self.actors_df["uid"] == uid, "show"] = True
                    self.set_actor_visible(uid=uid, visible=True, name=name)
            elif uid_checkState == Qt.Unchecked:
                if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                    self.actors_df.loc[self.actors_df["uid"] == uid, "show"] = False
                    self.set_actor_visible(uid=uid, visible=False, name=name)
            """Before updating checkboxes, disconnect signals to background and topology tree, if they are set,
            to avoid a nasty loop that disrupts the trees, then reconnect them (it is also possible that
            they are automatically reconnected whe the trees are rebuilt."""
            self.BackgroundsTreeWidget.itemChanged.disconnect()
            self.BackgroundsTopologyTreeWidget.itemChanged.disconnect()
            self.update_backgrounds_checkboxes(uid=uid, uid_checkState=uid_checkState)
            self.update_backgrounds_topology_checkboxes(
                uid=uid, uid_checkState=uid_checkState
            )
            self.BackgroundsTreeWidget.itemChanged.connect(
                self.toggle_backgrounds_topology_visibility
            )
            self.BackgroundsTopologyTreeWidget.itemChanged.connect(
                self.toggle_backgrounds_topology_visibility
            )

    # ================================  add, remove, and update actors ================================

    """Methods used to add, remove, and update actors from the geological collection."""

    def geology_added_update_views(self, updated_list=None):
        """This is called when an entity is added to the geological collection.
        Disconnect signals to geology and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.GeologyTreeWidget.itemChanged.disconnect()
        self.TopologyTreeWidget.itemChanged.disconnect()
        """Create pandas dataframe as list of "new" actors"""
        actors_df_new = pd_DataFrame(
            columns=["uid", "actor", "show", "collection", "show_prop"]
        )
        for uid in updated_list:
            this_actor = self.show_actor_with_property(
                uid=uid, collection="geol_coll", show_property=None, visible=True
            )
            self.actors_df = self.actors_df.append(
                {
                    "uid": uid,
                    "actor": this_actor,
                    "show": True,
                    "collection": "geol_coll",
                    "show_prop": None,
                },
                ignore_index=True,
            )
            actors_df_new = actors_df_new.append(
                {
                    "uid": uid,
                    "actor": this_actor,
                    "show": True,
                    "collection": "geol_coll",
                    "show_prop": None,
                },
                ignore_index=True,
            )
            self.update_geology_tree_added(actors_df_new)
            self.update_topology_tree_added(actors_df_new)
        """Re-connect signals."""
        self.GeologyTreeWidget.itemChanged.connect(
            self.toggle_geology_topology_visibility
        )
        self.TopologyTreeWidget.itemChanged.connect(
            self.toggle_geology_topology_visibility
        )

    def geology_removed_update_views(self, updated_list=None):
        """This is called when an entity is removed from the geological collection.
        Disconnect signals to geology and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.GeologyTreeWidget.itemChanged.disconnect()
        self.TopologyTreeWidget.itemChanged.disconnect()
        for uid in updated_list:
            self.remove_actor_in_view(uid=uid, redraw=True)
        self.update_geology_tree_removed(removed_list=updated_list)
        self.update_topology_tree_removed(removed_list=updated_list)
        """Re-connect signals."""
        self.GeologyTreeWidget.itemChanged.connect(
            self.toggle_geology_topology_visibility
        )
        self.TopologyTreeWidget.itemChanged.connect(
            self.toggle_geology_topology_visibility
        )

    def geology_geom_modified_update_views(self, updated_list=None):
        """This is called when an entity geometry or topology is modified (i.e. the vtk object is modified).
        Disconnect signals to geology and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.GeologyTreeWidget.itemChanged.disconnect()
        self.TopologyTreeWidget.itemChanged.disconnect()
        for uid in updated_list:
            """This calls the viewer-specific function that shows an actor with property = None.
            IN THE FUTURE update required to keep the current property shown.____________
            """
            self.remove_actor_in_view(uid=uid)
            this_actor = self.show_actor_with_property(
                uid=uid, collection="geol_coll", show_property=None, visible=True
            )
            self.actors_df = self.actors_df.append(
                {
                    "uid": uid,
                    "actor": this_actor,
                    "show": True,
                    "collection": "geol_coll",
                    "show_prop": None,
                },
                ignore_index=True,
            )  # self.actors_df.loc[self.actors_df["uid"] == uid, 'actor'] = this_actor
        """Re-connect signals."""
        self.GeologyTreeWidget.itemChanged.connect(
            self.toggle_geology_topology_visibility
        )
        self.TopologyTreeWidget.itemChanged.connect(
            self.toggle_geology_topology_visibility
        )

    def geology_data_keys_modified_update_views(self, updated_list=None):
        """This is called when entity point or cell data are modified.
        Disconnect signals to geology and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.GeologyTreeWidget.itemChanged.disconnect()
        self.TopologyTreeWidget.itemChanged.disconnect()
        for uid in updated_list:
            if (
                not self.actors_df.loc[
                    self.actors_df["uid"] == uid, "show_prop"
                ].to_list()
                == []
            ):
                if not self.actors_df.loc[
                    self.actors_df["uid"] == uid, "show_prop"
                ].values[0] in self.parent.geol_coll.get_uid_properties_names(uid):
                    show = self.actors_df.loc[
                        self.actors_df["uid"] == uid, "show"
                    ].to_list()[0]
                    self.remove_actor_in_view(uid=uid)
                    this_actor = self.show_actor_with_property(
                        uid=uid,
                        collection="geol_coll",
                        show_property=None,
                        visible=show,
                    )
                    self.actors_df = self.actors_df.append(
                        {
                            "uid": uid,
                            "actor": this_actor,
                            "show": show,
                            "collection": "geol_coll",
                            "show_prop": None,
                        },
                        ignore_index=True,
                    )  # self.actors_df.loc[self.actors_df["uid"] == uid, 'actor'] = this_actor
                    self.create_geology_tree()
                    self.create_topology_tree()
        """Re-connect signals."""
        self.GeologyTreeWidget.itemChanged.connect(
            self.toggle_geology_topology_visibility
        )
        self.TopologyTreeWidget.itemChanged.connect(
            self.toggle_geology_topology_visibility
        )

    def geology_data_val_modified_update_views(self, updated_list=None):
        """This is called when entity point or cell data are modified.
        Disconnect signals to geology and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.GeologyTreeWidget.itemChanged.disconnect()
        self.TopologyTreeWidget.itemChanged.disconnect()
        """IN THE FUTURE - generally just update the properties list - more complicate if we modify or delete the property that is shown_____________________"""
        """Re-connect signals."""
        self.GeologyTreeWidget.itemChanged.connect(
            self.toggle_geology_topology_visibility
        )
        self.TopologyTreeWidget.itemChanged.connect(
            self.toggle_geology_topology_visibility
        )

    def geology_metadata_modified_update_views(self, updated_list=None):
        """This is called when entity metadata are modified, and the legend is automatically updated.
        Disconnect signals to geology and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.GeologyTreeWidget.itemChanged.disconnect()
        self.TopologyTreeWidget.itemChanged.disconnect()
        for uid in updated_list:
            """Case for entities modified"""
            self.change_actor_color(uid=uid, collection="geol_coll")
            self.change_actor_line_thick(uid=uid, collection="geol_coll")
            self.create_geology_tree()
            self.create_topology_tree()
        """Re-connect signals."""
        self.GeologyTreeWidget.itemChanged.connect(
            self.toggle_geology_topology_visibility
        )
        self.TopologyTreeWidget.itemChanged.connect(
            self.toggle_geology_topology_visibility
        )

    def geology_legend_color_modified_update_views(self, updated_list=None):
        # print(updated_list)
        """This is called when the color in the geological legend is modified.
        Disconnect signals to geology and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.GeologyTreeWidget.itemChanged.disconnect()
        self.TopologyTreeWidget.itemChanged.disconnect()
        for uid in updated_list:
            """Case for color changed"""
            wells_list = self.parent.well_coll.get_uids()
            if self.parent.geol_coll.get_uid_x_section(uid) in wells_list:
                self.change_actor_color(
                    uid=self.parent.geol_coll.get_uid_x_section(uid),
                    collection="well_coll",
                )
            self.change_actor_color(uid=uid, collection="geol_coll")

        """Re-connect signals."""
        self.GeologyTreeWidget.itemChanged.connect(
            self.toggle_geology_topology_visibility
        )
        self.TopologyTreeWidget.itemChanged.connect(
            self.toggle_geology_topology_visibility
        )

    def geology_legend_thick_modified_update_views(self, updated_list=None):
        """This is called when the line thickness in the geological legend is modified.
        Disconnect signals to geology and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.GeologyTreeWidget.itemChanged.disconnect()
        self.TopologyTreeWidget.itemChanged.disconnect()
        for uid in updated_list:
            """Case for line_thick changed"""
            self.change_actor_line_thick(uid=uid, collection="geol_coll")
        """Re-connect signals."""
        self.GeologyTreeWidget.itemChanged.connect(
            self.toggle_geology_topology_visibility
        )
        self.TopologyTreeWidget.itemChanged.connect(
            self.toggle_geology_topology_visibility
        )

    def geology_legend_point_size_modified_update_views(self, updated_list=None):
        """This is called when the point size in the geological legend is modified.
        Disconnect signals to geology and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.GeologyTreeWidget.itemChanged.disconnect()
        self.TopologyTreeWidget.itemChanged.disconnect()
        for uid in updated_list:
            """Case for line_thick changed"""
            self.change_actor_point_size(uid=uid, collection="geol_coll")
        """Re-connect signals."""
        self.GeologyTreeWidget.itemChanged.connect(
            self.toggle_geology_topology_visibility
        )
        self.TopologyTreeWidget.itemChanged.connect(
            self.toggle_geology_topology_visibility
        )

    def geology_legend_opacity_modified_update_views(self, updated_list=None):
        """This is called when the line thickness in the geological legend is modified.
        Disconnect signals to geology and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.GeologyTreeWidget.itemChanged.disconnect()
        self.TopologyTreeWidget.itemChanged.disconnect()
        for uid in updated_list:
            """Case for line_thick changed"""
            self.change_actor_opacity(uid=uid, collection="geol_coll")
        """Re-connect signals."""
        self.GeologyTreeWidget.itemChanged.connect(
            self.toggle_geology_topology_visibility
        )
        self.TopologyTreeWidget.itemChanged.connect(
            self.toggle_geology_topology_visibility
        )

    """Methods used to add, remove, and update actors from the cross section collection."""

    def xsect_added_update_views(self, updated_list=None):
        """This is called when a cross-section is added to the xsect collection.
        Disconnect signals to xsect list, if they are set, then they are
        reconnected when the list is rebuilt"""
        self.XSectionTreeWidget.itemChanged.disconnect()
        actors_df_new = pd_DataFrame(
            columns=["uid", "actor", "show", "collection", "show_prop"]
        )
        for uid in updated_list:
            this_actor = self.show_actor_with_property(
                uid=uid, collection="xsect_coll", show_property=None, visible=True
            )
            self.actors_df = self.actors_df.append(
                {
                    "uid": uid,
                    "actor": this_actor,
                    "show": True,
                    "collection": "xsect_coll",
                    "show_prop": None,
                },
                ignore_index=True,
            )
            actors_df_new = actors_df_new.append(
                {
                    "uid": uid,
                    "actor": this_actor,
                    "show": True,
                    "collection": "xsect_coll",
                    "show_prop": None,
                },
                ignore_index=True,
            )
            self.update_xsections_tree_added(actors_df_new)
        """Re-connect signals."""
        self.XSectionTreeWidget.itemChanged.connect(self.toggle_xsection_visibility)

    def xsect_removed_update_views(self, updated_list=None):
        """This is called when a cross-section is removed from the xsect collection.
        Disconnect signals to xsect list, if they are set, then they are
        reconnected when the list is rebuilt"""
        self.XSectionTreeWidget.itemChanged.disconnect()
        for uid in updated_list:
            self.remove_actor_in_view(uid=uid)
            self.update_xsections_tree_removed(removed_list=updated_list)
        """Re-connect signals."""
        self.XSectionTreeWidget.itemChanged.connect(self.toggle_xsection_visibility)

    def xsect_geom_modified_update_views(self, updated_list=None):
        """This is called when an cross-section geometry is modified (i.e. the frame is modified).
        Disconnect signals to xsect list, if they are set, then they are
        reconnected when the list is rebuilt"""
        self.XSectionTreeWidget.itemChanged.disconnect()
        for uid in updated_list:
            """This calls the viewer-specific function that shows an actor with property = None.
            IN THE FUTURE update required to keep the current property shown.____________
            """
            self.remove_actor_in_view(uid=uid)
            this_actor = self.show_actor_with_property(
                uid=uid, collection="xsect_coll", show_property=None, visible=True
            )
            self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[
                0
            ] = this_actor
        """Re-connect signals."""
        self.XSectionTreeWidget.itemChanged.connect(self.toggle_xsection_visibility)

    def xsect_metadata_modified_update_views(self, updated_list=None):
        """This is called when the cross-section metadata are modified.
        Disconnect signals to xsect list, if they are set, then they are
        reconnected when the list is rebuilt"""
        self.XSectionTreeWidget.itemChanged.disconnect()
        for uid in updated_list:
            """Case for entities modified"""
            self.change_actor_color(uid=uid, collection="xsect_coll")
            self.change_actor_line_thick(uid=uid, collection="xsect_coll")
            self.create_xsections_tree()
        """Re-connect signals."""
        self.XSectionTreeWidget.itemChanged.connect(self.toggle_xsection_visibility)

    def xsect_legend_color_modified_update_views(self, updated_list=None):
        """This is called when the color in the cross-section legend is modified.
        Disconnect signals to xsect list, if they are set, then they are
        reconnected when the list is rebuilt"""
        self.XSectionTreeWidget.itemChanged.disconnect()
        for uid in updated_list:
            """Case for color changed"""
            self.change_actor_color(uid=uid, collection="xsect_coll")
        """Re-connect signals."""
        self.XSectionTreeWidget.itemChanged.connect(self.toggle_xsection_visibility)

    def xsect_legend_thick_modified_update_views(self, updated_list=None):
        """This is called when the line thickness in the cross-section legend is modified.
        Disconnect signals to xsect list, if they are set, then they are
        reconnected when the list is rebuilt"""
        self.XSectionTreeWidget.itemChanged.disconnect()
        for uid in updated_list:
            """Case for line_thick changed"""
            self.change_actor_line_thick(uid=uid, collection="xsect_coll")
        """Re-connect signals."""
        self.XSectionTreeWidget.itemChanged.connect(self.toggle_xsection_visibility)

    def xsect_legend_opacity_modified_update_views(self, updated_list=None):
        """This is called when the opacity in the image legend is modified.
        Disconnect signals to image tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.XSectionTreeWidget.itemChanged.disconnect()
        for uid in updated_list:
            """Case for color changed"""
            self.change_actor_opacity(uid=uid, collection="xsect_coll")
        """Re-connect signals."""
        self.XSectionTreeWidget.itemChanged.connect(self.toggle_xsect_visibility)

    """Methods used to add, remove, and update actors from the Boundary collection."""

    def boundary_added_update_views(self, updated_list=None):
        """This is called when a boundary is added to the boundary collection.
        Disconnect signals to boundary list, if they are set, then they are
        reconnected when the list is rebuilt"""
        self.BoundariesTableWidget.itemChanged.disconnect()
        actors_df_new = pd_DataFrame(
            columns=["uid", "actor", "show", "collection", "show_prop"]
        )
        for uid in updated_list:
            this_actor = self.show_actor_with_property(
                uid=uid, collection="boundary_coll", show_property=None, visible=False
            )
            self.actors_df = self.actors_df.append(
                {
                    "uid": uid,
                    "actor": this_actor,
                    "show": False,
                    "collection": "boundary_coll",
                    "show_prop": None,
                },
                ignore_index=True,
            )
            actors_df_new = actors_df_new.append(
                {
                    "uid": uid,
                    "actor": this_actor,
                    "show": False,
                    "collection": "boundary_coll",
                    "show_prop": None,
                },
                ignore_index=True,
            )
            self.update_boundary_list_added(actors_df_new)
        """Re-connect signals."""
        self.BoundariesTableWidget.itemChanged.connect(self.toggle_boundary_visibility)

    def boundary_removed_update_views(self, updated_list=None):
        """This is called when a boundary is removed from the boundary collection.
        Disconnect signals to boundary list, if they are set, then they are
        reconnected when the list is rebuilt"""
        self.BoundariesTableWidget.itemChanged.disconnect()
        for uid in updated_list:
            self.remove_actor_in_view(uid=uid)
            self.update_boundary_list_removed(removed_list=updated_list)
        """Re-connect signals."""
        self.BoundariesTableWidget.itemChanged.connect(self.toggle_boundary_visibility)

    def boundary_geom_modified_update_views(self, updated_list=None):
        """This is called when an entity geometry or topology is modified (i.e. the vtk object is modified).
        Disconnect signals to boundary list, if they are set, then they are
        reconnected when the list is rebuilt"""
        self.BoundariesTableWidget.itemChanged.disconnect()
        for uid in updated_list:
            """This calls the viewer-specific function that shows an actor with property = None."""
            self.remove_actor_in_view(uid=uid)
            this_actor = self.show_actor_with_property(
                uid=uid, collection="boundary_coll", show_property=None, visible=True
            )
            self.actors_df = self.actors_df.append(
                {
                    "uid": uid,
                    "actor": this_actor,
                    "show": True,
                    "collection": "boundary_coll",
                    "show_prop": None,
                },
                ignore_index=True,
            )  # self.actors_df.loc[self.actors_df["uid"] == uid, 'actor'] = this_actor
        """Re-connect signals."""
        self.BoundariesTableWidget.itemChanged.connect(self.toggle_boundary_visibility)

    def boundary_metadata_modified_update_views(self, updated_list=None):
        """This is called when the boundary metadata are modified.
        Disconnect signals to boundary list, if they are set, then they are
        reconnected when the list is rebuilt"""
        self.BoundariesTableWidget.itemChanged.disconnect()
        for uid in updated_list:
            """Case for entities modified"""
            self.change_actor_color(uid=uid, collection="boundary_coll")
            self.change_actor_line_thick(uid=uid, collection="boundary_coll")
            self.create_boundary_list()
        """Re-connect signals."""
        self.BoundariesTableWidget.itemChanged.connect(self.toggle_boundary_visibility)

    def boundary_legend_color_modified_update_views(self, updated_list=None):
        """This is called when the color in the boundary legend is modified.
        Disconnect signals to boundary list, if they are set, then they are
        reconnected when the list is rebuilt"""
        self.BoundariesTableWidget.itemChanged.disconnect()
        for uid in updated_list:
            """Case for color changed"""
            self.change_actor_color(uid=uid, collection="boundary_coll")
        """Re-connect signals."""
        self.BoundariesTableWidget.itemChanged.connect(self.toggle_boundary_visibility)

    def boundary_legend_thick_modified_update_views(self, updated_list=None):
        """This is called when the line thickness in the boundary legend is modified.
        Disconnect signals to boundary list, if they are set, then they are
        reconnected when the list is rebuilt"""
        self.BoundariesTableWidget.itemChanged.disconnect()
        for uid in updated_list:
            """Case for line_thick changed"""
            self.change_actor_line_thick(uid=uid, collection="boundary_coll")
        """Re-connect signals."""
        self.BoundariesTableWidget.itemChanged.connect(self.toggle_boundary_visibility)

    def boundary_legend_opacity_modified_update_views(self, updated_list=None):
        """This is called when the opacity in the image legend is modified.
        Disconnect signals to image tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.BoundariesTableWidget.itemChanged.disconnect()
        for uid in updated_list:
            """Case for color changed"""
            self.change_actor_opacity(uid=uid, collection="boundary_coll")
        """Re-connect signals."""
        self.BoundariesTableWidget.itemChanged.connect(self.toggle_boundary_visibility)

    """Methods used to add, remove, and update actors from the Mesh3D collection."""

    def mesh3d_added_update_views(self, updated_list=None):
        """This is called when a mesh3d is added to the mesh3d collection.
        Disconnect signals to mesh3d list, if they are set, then they are
        reconnected when the list is rebuilt"""
        self.Mesh3DTableWidget.itemChanged.disconnect()
        actors_df_new = pd_DataFrame(
            columns=["uid", "actor", "show", "collection", "show_prop"]
        )
        for uid in updated_list:
            this_actor = self.show_actor_with_property(
                uid=uid, collection="mesh3d_coll", show_property=None, visible=False
            )
            self.actors_df = self.actors_df.append(
                {
                    "uid": uid,
                    "actor": this_actor,
                    "show": False,
                    "collection": "mesh3d_coll",
                    "show_prop": None,
                },
                ignore_index=True,
            )
            actors_df_new = actors_df_new.append(
                {
                    "uid": uid,
                    "actor": this_actor,
                    "show": False,
                    "collection": "mesh3d_coll",
                    "show_prop": None,
                },
                ignore_index=True,
            )
            self.update_mesh3d_list_added(actors_df_new)
        """Re-connect signals."""
        self.Mesh3DTableWidget.itemChanged.connect(self.toggle_mesh3d_visibility)

    def mesh3d_removed_update_views(self, updated_list=None):
        """This is called when a mesh3d is removed from the mesh3d collection.
        Disconnect signals to mesh3d list, if they are set, then they are
        reconnected when the list is rebuilt"""
        self.Mesh3DTableWidget.itemChanged.disconnect()
        for uid in updated_list:
            self.remove_actor_in_view(uid=uid)
            self.update_mesh3d_list_removed(removed_list=updated_list)
        """Re-connect signals."""
        self.Mesh3DTableWidget.itemChanged.connect(self.toggle_mesh3d_visibility)

    def mesh3d_data_keys_modified_update_views(self, updated_list=None):
        """This is called when entity point or cell data are modified.
        Disconnect signals to geology and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.Mesh3DTableWidget.itemChanged.disconnect()
        for uid in updated_list:
            if (
                not self.actors_df.loc[
                    self.actors_df["uid"] == uid, "show_prop"
                ].to_list()
                == []
            ):
                if not self.actors_df.loc[
                    self.actors_df["uid"] == uid, "show_prop"
                ].values[0] in self.parent.mesh3d_coll.get_uid_properties_names(uid):
                    show = self.actors_df.loc[
                        self.actors_df["uid"] == uid, "show"
                    ].to_list()[0]
                    self.remove_actor_in_view(uid=uid)
                    this_actor = self.show_actor_with_property(
                        uid=uid,
                        collection="mesh3d_coll",
                        show_property=None,
                        visible=show,
                    )
                    self.actors_df = self.actors_df.append(
                        {
                            "uid": uid,
                            "actor": this_actor,
                            "show": show,
                            "collection": "mesh3d_coll",
                            "show_prop": None,
                        },
                        ignore_index=True,
                    )  # self.actors_df.loc[self.actors_df["uid"] == uid, 'actor'] = this_actor
                    self.create_mesh3d_list()
        """Re-connect signals."""
        self.Mesh3DTableWidget.itemChanged.connect(self.toggle_dom_visibility)

    def mesh3d_data_val_modified_update_views(self, updated_list=None):
        """This is called when entity point or cell data are modified.
        Disconnect signals to geology and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.Mesh3DTableWidget.itemChanged.disconnect()
        """IN THE FUTURE - generally just update the properties list - more complicate if we modify or delete the property that is shown_____________________"""
        """Re-connect signals."""
        self.Mesh3DTableWidget.itemChanged.connect(self.toggle_dom_visibility)

    def mesh3d_metadata_modified_update_views(self, updated_list=None):
        """This is called when the mesh3d metadata are modified.
        Disconnect signals to mesh3d list, if they are set, then they are
        reconnected when the list is rebuilt"""
        self.Mesh3DTableWidget.itemChanged.disconnect()
        for uid in updated_list:
            """Case for entities modified"""
            self.change_actor_color(uid=uid, collection="mesh3d_coll")
            self.change_actor_line_thick(uid=uid, collection="mesh3d_coll")
            self.create_mesh3d_list()
        """Re-connect signals."""
        self.Mesh3DTableWidget.itemChanged.connect(self.toggle_mesh3d_visibility)

    def mesh3d_legend_color_modified_update_views(self, updated_list=None):
        """This is called when the color in the cross-section legend is modified.
        Disconnect signals to mesh3d list, if they are set, then they are
        reconnected when the list is rebuilt"""
        self.Mesh3DTableWidget.itemChanged.disconnect()
        for uid in updated_list:
            """Case for color changed"""
            self.change_actor_color(uid=uid, collection="mesh3d_coll")
        """Re-connect signals."""
        self.Mesh3DTableWidget.itemChanged.connect(self.toggle_mesh3d_visibility)

    def mesh3d_legend_thick_modified_update_views(self, updated_list=None):
        """This is called when the line thickness in the cross-section legend is modified.
        Disconnect signals to mesh3d list, if they are set, then they are
        reconnected when the list is rebuilt"""
        self.Mesh3DTableWidget.itemChanged.disconnect()
        for uid in updated_list:
            """Case for line_thick changed"""
            self.change_actor_line_thick(uid=uid, collection="mesh3d_coll")
        """Re-connect signals."""
        self.Mesh3DTableWidget.itemChanged.connect(self.toggle_mesh3d_visibility)

    def mesh3d_legend_opacity_modified_update_views(self, updated_list=None):
        """This is called when the opacity in the image legend is modified.
        Disconnect signals to image tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.Mesh3DTableWidget.itemChanged.disconnect()
        for uid in updated_list:
            """Case for color changed"""
            self.change_actor_opacity(uid=uid, collection="mesh3d_coll")
        """Re-connect signals."""
        self.Mesh3DTableWidget.itemChanged.connect(self.toggle_mesh3d_visibility)

    """Methods used to add, remove, and update actors from the DOM collection."""

    def dom_added_update_views(self, updated_list=None):
        """This is called when a DOM is added to the xsect collection.
        Disconnect signals to dom list, if they are set, then they are
        reconnected when the list is rebuilt"""
        self.DOMsTableWidget.itemChanged.disconnect()
        actors_df_new = pd_DataFrame(
            columns=["uid", "actor", "show", "collection", "show_prop"]
        )
        for uid in updated_list:
            this_actor = self.show_actor_with_property(
                uid=uid, collection="dom_coll", show_property=None, visible=False
            )
            self.actors_df = self.actors_df.append(
                {
                    "uid": uid,
                    "actor": this_actor,
                    "show": False,
                    "collection": "dom_coll",
                    "show_prop": None,
                },
                ignore_index=True,
            )
            actors_df_new = actors_df_new.append(
                {
                    "uid": uid,
                    "actor": this_actor,
                    "show": False,
                    "collection": "dom_coll",
                    "show_prop": None,
                },
                ignore_index=True,
            )
            self.update_dom_list_added(actors_df_new)
        """Re-connect signals."""
        self.DOMsTableWidget.itemChanged.connect(self.toggle_dom_visibility)

    def dom_removed_update_views(self, updated_list=None):
        """This is called when a DOM is removed from the dom collection.
        Disconnect signals to dom list, if they are set, then they are
        reconnected when the list is rebuilt"""
        self.DOMsTableWidget.itemChanged.disconnect()
        for uid in updated_list:
            self.remove_actor_in_view(uid=uid, redraw=True)
            self.update_dom_list_removed(removed_list=updated_list)
        """Re-connect signals."""
        self.DOMsTableWidget.itemChanged.connect(self.toggle_dom_visibility)

    def dom_data_keys_modified_update_views(self, updated_list=None):
        """This is called when entity point or cell data are modified.
        Disconnect signals to DOM tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.DOMsTableWidget.itemChanged.disconnect()
        for uid in updated_list:
            if (
                not self.actors_df.loc[
                    self.actors_df["uid"] == uid, "show_prop"
                ].to_list()
                == []
            ):
                if not self.actors_df.loc[
                    self.actors_df["uid"] == uid, "show_prop"
                ].values[0] in self.parent.dom_coll.get_uid_properties_names(uid):
                    show = self.actors_df.loc[
                        self.actors_df["uid"] == uid, "show"
                    ].to_list()[0]
                    self.remove_actor_in_view(uid=uid)
                    this_actor = self.show_actor_with_property(
                        uid=uid, collection="dom_coll", show_property=None, visible=show
                    )
                    self.actors_df = self.actors_df.append(
                        {
                            "uid": uid,
                            "actor": this_actor,
                            "show": show,
                            "collection": "dom_coll",
                            "show_prop": None,
                        },
                        ignore_index=True,
                    )  # self.actors_df.loc[self.actors_df["uid"] == uid, 'actor'] = this_actor
                    self.create_dom_list()
        """Re-connect signals."""
        self.DOMsTableWidget.itemChanged.connect(self.toggle_dom_visibility)

    def dom_data_val_modified_update_views(self, updated_list=None):
        """This is called when entity point or cell data are modified.
        Disconnect signals to geology and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.DOMsTableWidget.itemChanged.disconnect()
        """IN THE FUTURE - generally just update the properties list - more complicate if we modify or delete the property that is shown_____________________"""
        """Re-connect signals."""
        self.DOMsTableWidget.itemChanged.connect(self.toggle_dom_visibility)

    def dom_metadata_modified_update_views(self, updated_list=None):
        """This is called when the DOM metadata are modified.
        Disconnect signals to dom list, if they are set, then they are
        reconnected when the list is rebuilt"""
        self.DOMsTableWidget.itemChanged.disconnect()
        for uid in updated_list:
            """Case for entities modified"""
            self.change_actor_color(uid=uid, collection="dom_coll")
            self.change_actor_line_thick(uid=uid, collection="dom_coll")
            self.create_dom_list()
        """Re-connect signals."""
        self.DOMsTableWidget.itemChanged.connect(self.toggle_dom_visibility)

    def dom_legend_color_modified_update_views(self, updated_list=None):
        """This is called when the color in the cross-section legend is modified.
        Disconnect signals to xsect list, if they are set, then they are
        reconnected when the list is rebuilt"""
        self.DOMsTableWidget.itemChanged.disconnect()
        for uid in updated_list:
            """Case for color changed"""
            self.change_actor_color(uid=uid, collection="dom_coll")
        """Re-connect signals."""
        self.DOMsTableWidget.itemChanged.connect(self.toggle_dom_visibility)

    def dom_legend_thick_modified_update_views(self, updated_list=None):
        """This is called when the line thickness in the cross-section legend is modified.
        Disconnect signals to xsect list, if they are set, then they are
        reconnected when the list is rebuilt"""
        self.DOMsTableWidget.itemChanged.disconnect()
        for uid in updated_list:
            """Case for line_thick changed"""
            self.change_actor_line_thick(uid=uid, collection="dom_coll")
        """Re-connect signals."""
        self.DOMsTableWidget.itemChanged.connect(self.toggle_dom_visibility)

    def dom_legend_point_size_modified_update_views(self, updated_list=None):
        """This is called when the line thickness in the cross-section legend is modified.
        Disconnect signals to xsect list, if they are set, then they are
        reconnected when the list is rebuilt"""
        self.DOMsTableWidget.itemChanged.disconnect()
        for uid in updated_list:
            """Case for line_thick changed"""
            self.change_actor_point_size(uid=uid, collection="dom_coll")
        """Re-connect signals."""
        self.DOMsTableWidget.itemChanged.connect(self.toggle_dom_visibility)

    def dom_legend_opacity_modified_update_views(self, updated_list=None):
        """This is called when the opacity in the image legend is modified.
        Disconnect signals to image tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.DOMsTableWidget.itemChanged.disconnect()
        for uid in updated_list:
            """Case for color changed"""
            if isinstance(self, View3D):
                self.change_actor_opacity(uid=uid, collection="dom_coll")
        """Re-connect signals."""
        self.DOMsTableWidget.itemChanged.connect(self.toggle_dom_visibility)

    """Methods used to add, remove, and update actors from the image collection."""

    def image_added_update_views(self, updated_list=None):
        """This is called when an image is added to the image collection.
        Disconnect signals to image list, if they are set, then they are
        reconnected when the list is rebuilt""" """________________________________________________________________________"""
        self.ImagesTableWidget.itemChanged.disconnect()
        actors_df_new = pd_DataFrame(
            columns=["uid", "actor", "show", "collection", "show_prop"]
        )
        for uid in updated_list:
            this_actor = self.show_actor_with_property(
                uid=uid, collection="image_coll", show_property=None, visible=False
            )
            self.actors_df = self.actors_df.append(
                {
                    "uid": uid,
                    "actor": this_actor,
                    "show": False,
                    "collection": "image_coll",
                    "show_prop": None,
                },
                ignore_index=True,
            )
            actors_df_new = actors_df_new.append(
                {
                    "uid": uid,
                    "actor": this_actor,
                    "show": False,
                    "collection": "image_coll",
                    "show_prop": None,
                },
                ignore_index=True,
            )
            self.update_image_list_added(actors_df_new)
        """Re-connect signals."""
        self.ImagesTableWidget.itemChanged.connect(self.toggle_image_visibility)

    def image_removed_update_views(self, updated_list=None):
        """This is called when an image is removed from the image collection.
        Disconnect signals to image list, if they are set, then they are
        reconnected when the list is rebuilt""" """________________________________________________________________________"""
        self.ImagesTableWidget.itemChanged.disconnect()
        for uid in updated_list:
            self.remove_actor_in_view(uid=uid)
            self.update_image_list_removed(removed_list=updated_list)
        """Re-connect signals."""
        self.ImagesTableWidget.itemChanged.connect(self.toggle_image_visibility)

    def image_metadata_modified_update_views(self, updated_list=None):
        """This is called when the image metadata are modified.
        Disconnect signals to image list, if they are set, then they are
        reconnected when the list is rebuilt""" """________________________________________________________________________"""
        self.ImagesTableWidget.itemChanged.disconnect()
        for uid in updated_list:
            """Case for entities modified"""
            self.create_image_list()
        """Re-connect signals."""
        self.ImagesTableWidget.itemChanged.connect(self.toggle_image_visibility)

    def image_legend_opacity_modified_update_views(self, updated_list=None):
        """This is called when the opacity in the image legend is modified.
        Disconnect signals to image tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.ImagesTableWidget.itemChanged.disconnect()
        for uid in updated_list:
            """Case for color changed"""
            self.change_actor_opacity(uid=uid, collection="image_coll")
        """Re-connect signals."""
        self.ImagesTableWidget.itemChanged.connect(self.toggle_image_visibility)

    """Methods used to add, remove, and update actors from the wells collection."""

    def well_added_update_views(self, updated_list=None):
        """This is called when an entity is added to the well collection.
        Disconnect signals to well tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.WellsTreeWidget.itemChanged.disconnect()
        """Create pandas dataframe as list of "new" actors"""
        actors_df_new = pd_DataFrame(
            columns=["uid", "actor", "show", "collection", "show_prop"]
        )
        for uid in updated_list:
            this_actor = self.show_actor_with_property(
                uid=uid, collection="well_coll", show_property=None, visible=True
            )
            self.actors_df = self.actors_df.append(
                {
                    "uid": uid,
                    "actor": this_actor,
                    "show": True,
                    "collection": "well_coll",
                    "show_prop": None,
                },
                ignore_index=True,
            )
            actors_df_new = actors_df_new.append(
                {
                    "uid": uid,
                    "actor": this_actor,
                    "show": True,
                    "collection": "well_coll",
                    "show_prop": None,
                },
                ignore_index=True,
            )
            self.update_well_tree_added(actors_df_new)
        """Re-connect signals."""
        self.WellsTreeWidget.itemChanged.connect(self.toggle_well_visibility)

    def well_removed_update_views(self, updated_list=None):
        """This is called when an entity is removed from the geological collection.
        Disconnect signals to geology and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.WellsTreeWidget.itemChanged.disconnect()
        for uid in updated_list:
            self.remove_actor_in_view(uid=uid, redraw=True)
        self.update_well_tree_removed(removed_list=updated_list)
        """Re-connect signals."""
        self.WellsTreeWidget.itemChanged.connect(self.toggle_well_visibility)

    def well_data_keys_modified_update_views(self, updated_list=None):
        """This is called when entity point or cell data are modified.
        Disconnect signals to geology and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.WellsTreeWidget.itemChanged.disconnect()
        for uid in updated_list:
            if (
                not self.actors_df.loc[
                    self.actors_df["uid"] == uid, "show_prop"
                ].to_list()
                == []
            ):
                if not self.actors_df.loc[
                    self.actors_df["uid"] == uid, "show_prop"
                ].values[0] in self.parent.geol_coll.get_uid_properties_names(uid):
                    show = self.actors_df.loc[
                        self.actors_df["uid"] == uid, "show"
                    ].to_list()[0]
                    self.remove_actor_in_view(uid=uid)
                    this_actor = self.show_actor_with_property(
                        uid=uid,
                        collection="geol_coll",
                        show_property=None,
                        visible=show,
                    )
                    self.actors_df = self.actors_df.append(
                        {
                            "uid": uid,
                            "actor": this_actor,
                            "show": show,
                            "collection": "well_coll",
                            "show_prop": None,
                        },
                        ignore_index=True,
                    )  # self.actors_df.loc[self.actors_df["uid"] == uid, 'actor'] = this_actor
                    self.create_well_tree()
        """Re-connect signals."""
        self.WellsTreeWidget.itemChanged.connect(self.toggle_well_visibility)

    def well_data_val_modified_update_views(self, updated_list=None):
        ...

    def well_metadata_modified_update_views(self, updated_list=None):
        """This is called when entity metadata are modified, and the legend is automatically updated.
        Disconnect signals to geology and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.WellsTreeWidget.itemChanged.disconnect()
        for uid in updated_list:
            """Case for entities modified"""
            self.change_actor_color(uid=uid, collection="well_coll")
            self.change_actor_line_thick(uid=uid, collection="well_coll")
            self.create_well_tree()
        """Re-connect signals."""
        self.WellsTreeWidget.itemChanged.connect(self.toggle_well_visibility)

    def well_legend_color_modified_update_views(self, updated_list=None):
        """This is called when the color in the geological legend is modified.
        Disconnect signals to geology and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.WellsTreeWidget.itemChanged.disconnect()
        for uid in updated_list:
            """Case for color changed"""
            self.change_actor_color(uid=uid, collection="well_coll")
        """Re-connect signals."""
        self.WellsTreeWidget.itemChanged.connect(self.toggle_well_visibility)

    def well_legend_thick_modified_update_views(self, updated_list=None):
        """This is called when the line thickness in the geological legend is modified.
        Disconnect signals to geology and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.WellsTreeWidget.itemChanged.disconnect()
        for uid in updated_list:
            """Case for line_thick changed"""
            self.change_actor_line_thick(uid=uid, collection="well_coll")
        """Re-connect signals."""
        self.WellsTreeWidget.itemChanged.connect(self.toggle_well_visibility)

    def well_legend_opacity_modified_update_views(self, updated_list=None):
        """This is called when the opacity in the well legend is modified.
        Disconnect signals to geology and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.WellsTreeWidget.itemChanged.disconnect()
        for uid in updated_list:
            """Case for line_thick changed"""
            self.change_actor_opacity(uid=uid, collection="well_coll")
        """Re-connect signals."""
        self.WellsTreeWidget.itemChanged.connect(self.toggle_well_visibility)

    """Methods used to add, remove, and update actors from the fluid collection."""

    def fluid_added_update_views(self, updated_list=None):
        """This is called when an entity is added to the fluid collection.
        Disconnect signals to fluid and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.FluidsTreeWidget.itemChanged.disconnect()
        self.FluidsTopologyTreeWidget.itemChanged.disconnect()
        """Create pandas dataframe as list of "new" actors"""
        actors_df_new = pd_DataFrame(
            columns=["uid", "actor", "show", "collection", "show_prop"]
        )
        for uid in updated_list:
            this_actor = self.show_actor_with_property(
                uid=uid, collection="fluids_coll", show_property=None, visible=True
            )
            self.actors_df = self.actors_df.append(
                {
                    "uid": uid,
                    "actor": this_actor,
                    "show": True,
                    "collection": "fluids_coll",
                    "show_prop": None,
                },
                ignore_index=True,
            )
            actors_df_new = actors_df_new.append(
                {
                    "uid": uid,
                    "actor": this_actor,
                    "show": True,
                    "collection": "fluids_coll",
                    "show_prop": None,
                },
                ignore_index=True,
            )
            self.update_fluids_tree_added(actors_df_new)
            self.update_fluids_topology_tree_added(actors_df_new)
        """Re-connect signals."""
        self.FluidsTreeWidget.itemChanged.connect(
            self.toggle_fluids_topology_visibility
        )
        self.FluidsTopologyTreeWidget.itemChanged.connect(
            self.toggle_fluids_topology_visibility
        )

    def fluid_removed_update_views(self, updated_list=None):
        """This is called when an entity is removed from the fluid collection.
        Disconnect signals to fluid and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.FluidsTreeWidget.itemChanged.disconnect()
        self.FluidsTopologyTreeWidget.itemChanged.disconnect()
        for uid in updated_list:
            self.remove_actor_in_view(uid=uid, redraw=True)
        self.update_fluids_tree_removed(removed_list=updated_list)
        self.update_fluids_topology_tree_removed(removed_list=updated_list)
        """Re-connect signals."""
        self.FluidsTreeWidget.itemChanged.connect(
            self.toggle_fluids_topology_visibility
        )
        self.FluidsTopologyTreeWidget.itemChanged.connect(
            self.toggle_fluids_topology_visibility
        )

    def fluid_geom_modified_update_views(self, updated_list=None):
        """This is called when an entity geometry or topology is modified (i.e. the vtk object is modified).
        Disconnect signals to fluid and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.FluidsTreeWidget.itemChanged.disconnect()
        self.FluidsTopologyTreeWidget.itemChanged.disconnect()
        for uid in updated_list:
            """This calls the viewer-specific function that shows an actor with property = None.
            IN THE FUTURE update required to keep the current property shown.____________
            """
            self.remove_actor_in_view(uid=uid)
            this_actor = self.show_actor_with_property(
                uid=uid, collection="fluids_coll", show_property=None, visible=True
            )
            self.actors_df = self.actors_df.append(
                {
                    "uid": uid,
                    "actor": this_actor,
                    "show": True,
                    "collection": "fluids_coll",
                    "show_prop": None,
                },
                ignore_index=True,
            )  # self.actors_df.loc[self.actors_df["uid"] == uid, 'actor'] = this_actor
        """Re-connect signals."""
        self.FluidsTreeWidget.itemChanged.connect(
            self.toggle_fluids_topology_visibility
        )
        self.FluidsTopologyTreeWidget.itemChanged.connect(
            self.toggle_fluids_topology_visibility
        )

    def fluid_data_keys_modified_update_views(self, updated_list=None):
        """This is called when entity point or cell data are modified.
        Disconnect signals to fluid and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.FluidsTreeWidget.itemChanged.disconnect()
        self.FluidsTopologyTreeWidget.itemChanged.disconnect()
        for uid in updated_list:
            if (
                not self.actors_df.loc[
                    self.actors_df["uid"] == uid, "show_prop"
                ].to_list()
                == []
            ):
                if not self.actors_df.loc[
                    self.actors_df["uid"] == uid, "show_prop"
                ].values[0] in self.parent.fluids_coll.get_uid_properties_names(uid):
                    show = self.actors_df.loc[
                        self.actors_df["uid"] == uid, "show"
                    ].to_list()[0]
                    self.remove_actor_in_view(uid=uid)
                    this_actor = self.show_actor_with_property(
                        uid=uid,
                        collection="fluids_coll",
                        show_property=None,
                        visible=show,
                    )
                    self.actors_df = self.actors_df.append(
                        {
                            "uid": uid,
                            "actor": this_actor,
                            "show": show,
                            "collection": "fluids_coll",
                            "show_prop": None,
                        },
                        ignore_index=True,
                    )  # self.actors_df.loc[self.actors_df["uid"] == uid, 'actor'] = this_actor
                    self.create_fluid_tree()
                    self.create_fluids_topology_tree()
        """Re-connect signals."""
        self.FluidsTreeWidget.itemChanged.connect(
            self.toggle_fluids_topology_visibility
        )
        self.FluidsTopologyTreeWidget.itemChanged.connect(
            self.toggle_fluids_topology_visibility
        )

    def fluid_data_val_modified_update_views(self, updated_list=None):
        """This is called when entity point or cell data are modified.
        Disconnect signals to fluid and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.FluidsTreeWidget.itemChanged.disconnect()
        self.FluidsTopologyTreeWidget.itemChanged.disconnect()
        """IN THE FUTURE - generally just update the properties list - more complicate if we modify or delete the property that is shown_____________________"""
        """Re-connect signals."""
        self.FluidsTreeWidget.itemChanged.connect(
            self.toggle_fluids_topology_visibility
        )
        self.FluidsTopologyTreeWidget.itemChanged.connect(
            self.toggle_fluids_topology_visibility
        )

    def fluid_metadata_modified_update_views(self, updated_list=None):
        """This is called when entity metadata are modified, and the legend is automatically updated.
        Disconnect signals to fluid and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.FluidsTreeWidget.itemChanged.disconnect()
        self.FluidsTopologyTreeWidget.itemChanged.disconnect()
        for uid in updated_list:
            """Case for entities modified"""
            self.change_actor_color(uid=uid, collection="fluids_coll")
            self.change_actor_line_thick(uid=uid, collection="fluids_coll")
            self.create_fluid_tree()
            self.create_fluids_topology_tree()
        """Re-connect signals."""
        self.FluidsTreeWidget.itemChanged.connect(
            self.toggle_fluids_topology_visibility
        )
        self.FluidsTopologyTreeWidget.itemChanged.connect(
            self.toggle_fluids_topology_visibility
        )

    def fluid_legend_color_modified_update_views(self, updated_list=None):
        # print(updated_list)
        """This is called when the color in the fluid legend is modified.
        Disconnect signals to fluid and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.FluidsTreeWidget.itemChanged.disconnect()
        self.FluidsTopologyTreeWidget.itemChanged.disconnect()
        for uid in updated_list:
            """Case for color changed"""
            wells_list = self.parent.well_coll.get_uids()
            if self.parent.fluids_coll.get_uid_x_section(uid) in wells_list:
                self.change_actor_color(
                    uid=self.parent.fluids_coll.get_uid_x_section(uid),
                    collection="well_coll",
                )
            self.change_actor_color(uid=uid, collection="fluids_coll")

        """Re-connect signals."""
        self.FluidsTreeWidget.itemChanged.connect(
            self.toggle_fluids_topology_visibility
        )
        self.FluidsTopologyTreeWidget.itemChanged.connect(
            self.toggle_fluids_topology_visibility
        )

    def fluid_legend_thick_modified_update_views(self, updated_list=None):
        """This is called when the line thickness in the fluid legend is modified.
        Disconnect signals to fluid and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.FluidsTreeWidget.itemChanged.disconnect()
        self.FluidsTopologyTreeWidget.itemChanged.disconnect()
        for uid in updated_list:
            """Case for line_thick changed"""
            self.change_actor_line_thick(uid=uid, collection="fluids_coll")
        """Re-connect signals."""
        self.FluidsTreeWidget.itemChanged.connect(
            self.toggle_fluids_topology_visibility
        )
        self.FluidsTopologyTreeWidget.itemChanged.connect(
            self.toggle_fluids_topology_visibility
        )

    def fluid_legend_point_size_modified_update_views(self, updated_list=None):
        """This is called when the line thickness in the fluid legend is modified.
        Disconnect signals to fluid and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.FluidsTreeWidget.itemChanged.disconnect()
        self.FluidsTopologyTreeWidget.itemChanged.disconnect()
        for uid in updated_list:
            """Case for line_thick changed"""
            self.change_actor_line_point_size(uid=uid, collection="fluids_coll")
        """Re-connect signals."""
        self.FluidsTreeWidget.itemChanged.connect(
            self.toggle_fluids_topology_visibility
        )
        self.FluidsTopologyTreeWidget.itemChanged.connect(
            self.toggle_fluids_topology_visibility
        )

    def fluid_legend_opacity_modified_update_views(self, updated_list=None):
        """This is called when the opacity in the fluid legend is modified.
        Disconnect signals to fluid and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.FluidsTreeWidget.itemChanged.disconnect()
        self.FluidsTopologyTreeWidget.itemChanged.disconnect()
        for uid in updated_list:
            """Case for line_thick changed"""
            self.change_actor_opacity(uid=uid, collection="fluids_coll")
        """Re-connect signals."""
        self.FluidsTreeWidget.itemChanged.connect(
            self.toggle_fluids_topology_visibility
        )
        self.FluidsTopologyTreeWidget.itemChanged.connect(
            self.toggle_fluids_topology_visibility
        )

    """Methods used to add, remove, and update actors from the backgrounds_misti collection."""

    def background_added_update_views(self, updated_list=None):
        """This is called when an entity is added to the fluid collection.
        Disconnect signals to fluid and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.BackgroundsTreeWidget.itemChanged.disconnect()
        self.BackgroundsTopologyTreeWidget.itemChanged.disconnect()
        """Create pandas dataframe as list of "new" actors"""
        actors_df_new = pd_DataFrame(
            columns=["uid", "actor", "show", "collection", "show_prop"]
        )
        for uid in updated_list:
            this_actor = self.show_actor_with_property(
                uid=uid, collection="backgrounds_coll", show_property=None, visible=True
            )
            self.actors_df = self.actors_df.append(
                {
                    "uid": uid,
                    "actor": this_actor,
                    "show": True,
                    "collection": "backgrounds_coll",
                    "show_prop": None,
                },
                ignore_index=True,
            )
            actors_df_new = actors_df_new.append(
                {
                    "uid": uid,
                    "actor": this_actor,
                    "show": True,
                    "collection": "backgrounds_coll",
                    "show_prop": None,
                },
                ignore_index=True,
            )
            self.update_backgrounds_tree_added(actors_df_new)
            self.update_backgrounds_topology_tree_added(actors_df_new)
        """Re-connect signals."""
        self.BackgroundsTreeWidget.itemChanged.connect(
            self.toggle_backgrounds_topology_visibility
        )
        self.BackgroundsTopologyTreeWidget.itemChanged.connect(
            self.toggle_backgrounds_topology_visibility
        )

    def background_removed_update_views(self, updated_list=None):
        """This is called when an entity is removed from the fluid collection.
        Disconnect signals to fluid and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.BackgroundsTreeWidget.itemChanged.disconnect()
        self.BackgroundsTopologyTreeWidget.itemChanged.disconnect()
        for uid in updated_list:
            self.remove_actor_in_view(uid=uid, redraw=True)
        self.update_backgrounds_tree_removed(removed_list=updated_list)
        self.update_backgrounds_topology_tree_removed(removed_list=updated_list)
        """Re-connect signals."""
        self.BackgroundsTreeWidget.itemChanged.connect(
            self.toggle_backgrounds_topology_visibility
        )
        self.BackgroundsTopologyTreeWidget.itemChanged.connect(
            self.toggle_backgrounds_topology_visibility
        )

    def background_geom_modified_update_views(self, updated_list=None):
        """This is called when an entity geometry or topology is modified (i.e. the vtk object is modified).
        Disconnect signals to fluid and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.BackgroundsTreeWidget.itemChanged.disconnect()
        self.BackgroundsTopologyTreeWidget.itemChanged.disconnect()
        for uid in updated_list:
            """This calls the viewer-specific function that shows an actor with property = None.
            IN THE FUTURE update required to keep the current property shown.____________
            """
            self.remove_actor_in_view(uid=uid)
            this_actor = self.show_actor_with_property(
                uid=uid, collection="backgrounds_coll", show_property=None, visible=True
            )
            self.actors_df = self.actors_df.append(
                {
                    "uid": uid,
                    "actor": this_actor,
                    "show": True,
                    "collection": "backgrounds_coll",
                    "show_prop": None,
                },
                ignore_index=True,
            )  # self.actors_df.loc[self.actors_df["uid"] == uid, 'actor'] = this_actor
        """Re-connect signals."""
        self.BackgroundsTreeWidget.itemChanged.connect(
            self.toggle_backgrounds_topology_visibility
        )
        self.BackgroundsTopologyTreeWidget.itemChanged.connect(
            self.toggle_backgrounds_topology_visibility
        )

    def background_data_keys_modified_update_views(self, updated_list=None):
        """This is called when entity point or cell data are modified.
        Disconnect signals to fluid and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.BackgroundsTreeWidget.itemChanged.disconnect()
        self.BackgroundsTopologyTreeWidget.itemChanged.disconnect()
        for uid in updated_list:
            if (
                not self.actors_df.loc[
                    self.actors_df["uid"] == uid, "show_prop"
                ].to_list()
                == []
            ):
                if not self.actors_df.loc[
                    self.actors_df["uid"] == uid, "show_prop"
                ].values[0] in self.parent.backgrounds_coll.get_uid_properties_names(
                    uid
                ):
                    show = self.actors_df.loc[
                        self.actors_df["uid"] == uid, "show"
                    ].to_list()[0]
                    self.remove_actor_in_view(uid=uid)
                    this_actor = self.show_actor_with_property(
                        uid=uid,
                        collection="backgrounds_coll",
                        show_property=None,
                        visible=show,
                    )
                    self.actors_df = self.actors_df.append(
                        {
                            "uid": uid,
                            "actor": this_actor,
                            "show": show,
                            "collection": "backgrounds_coll",
                            "show_prop": None,
                        },
                        ignore_index=True,
                    )  # self.actors_df.loc[self.actors_df["uid"] == uid, 'actor'] = this_actor
                    self.create_fluid_tree()
                    self.create_fluids_topology_tree()
        """Re-connect signals."""
        self.BackgroundsTreeWidget.itemChanged.connect(
            self.toggle_backgrounds_topology_visibility
        )
        self.BackgroundsTopologyTreeWidget.itemChanged.connect(
            self.toggle_backgrounds_topology_visibility
        )

    def background_data_val_modified_update_views(self, updated_list=None):
        """This is called when entity point or cell data are modified.
        Disconnect signals to fluid and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.BackgroundsTreeWidget.itemChanged.disconnect()
        self.BackgroundsTopologyTreeWidget.itemChanged.disconnect()
        """IN THE FUTURE - generally just update the properties list - more complicate if we modify or delete the property that is shown_____________________"""
        """Re-connect signals."""
        self.BackgroundsTreeWidget.itemChanged.connect(
            self.toggle_backgrounds_topology_visibility
        )
        self.BackgroundsTopologyTreeWidget.itemChanged.connect(
            self.toggle_backgrounds_topology_visibility
        )

    def background_metadata_modified_update_views(self, updated_list=None):
        """This is called when entity metadata are modified, and the legend is automatically updated.
        Disconnect signals to fluid and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.BackgroundsTreeWidget.itemChanged.disconnect()
        self.BackgroundsTopologyTreeWidget.itemChanged.disconnect()
        for uid in updated_list:
            """Case for entities modified"""
            self.change_actor_color(uid=uid, collection="backgrounds_coll")
            self.change_actor_line_thick(uid=uid, collection="backgrounds_coll")
            self.create_fluid_tree()
            self.create_fluids_topology_tree()
        """Re-connect signals."""
        self.BackgroundsTreeWidget.itemChanged.connect(
            self.toggle_backgrounds_topology_visibility
        )
        self.BackgroundsTopologyTreeWidget.itemChanged.connect(
            self.toggle_backgrounds_topology_visibility
        )

    def background_legend_color_modified_update_views(self, updated_list=None):
        # print(updated_list)
        """This is called when the color in the fluid legend is modified.
        Disconnect signals to fluid and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.BackgroundsTreeWidget.itemChanged.disconnect()
        self.BackgroundsTopologyTreeWidget.itemChanged.disconnect()
        for uid in updated_list:
            """Case for color changed"""
            wells_list = self.parent.well_coll.get_uids()
            if self.parent.backgrounds_coll.get_uid_x_section(uid) in wells_list:
                self.change_actor_color(
                    uid=self.parent.backgrounds_coll.get_uid_x_section(uid),
                    collection="well_coll",
                )
            self.change_actor_color(uid=uid, collection="backgrounds_coll")

        """Re-connect signals."""
        self.BackgroundsTreeWidget.itemChanged.connect(
            self.toggle_backgrounds_topology_visibility
        )
        self.BackgroundsTopologyTreeWidget.itemChanged.connect(
            self.toggle_backgrounds_topology_visibility
        )

    def background_legend_thick_modified_update_views(self, updated_list=None):
        """This is called when the line thickness in the fluid legend is modified.
        Disconnect signals to fluid and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.BackgroundsTreeWidget.itemChanged.disconnect()
        self.BackgroundsTopologyTreeWidget.itemChanged.disconnect()
        for uid in updated_list:
            """Case for line_thick changed"""
            self.change_actor_line_thick(uid=uid, collection="backgrounds_coll")
        """Re-connect signals."""
        self.BackgroundsTreeWidget.itemChanged.connect(
            self.toggle_backgrounds_topology_visibility
        )
        self.BackgroundsTopologyTreeWidget.itemChanged.connect(
            self.toggle_backgrounds_topology_visibility
        )

    def background_legend_point_size_modified_update_views(self, updated_list=None):
        """This is called when the line thickness in the fluid legend is modified.
        Disconnect signals to fluid and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.BackgroundsTreeWidget.itemChanged.disconnect()
        self.BackgroundsTopologyTreeWidget.itemChanged.disconnect()
        for uid in updated_list:
            """Case for line_thick changed"""
            self.change_actor_point_size(uid=uid, collection="backgrounds_coll")
        """Re-connect signals."""
        self.BackgroundsTreeWidget.itemChanged.connect(
            self.toggle_backgrounds_topology_visibility
        )
        self.BackgroundsTopologyTreeWidget.itemChanged.connect(
            self.toggle_backgrounds_topology_visibility
        )

    def background_legend_opacity_modified_update_views(self, updated_list=None):
        """This is called when the line thickness in the fluid legend is modified.
        Disconnect signals to fluid and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.BackgroundsTreeWidget.itemChanged.disconnect()
        self.BackgroundsTopologyTreeWidget.itemChanged.disconnect()
        for uid in updated_list:
            """Case for line_thick changed"""
            self.change_actor_opacity(uid=uid, collection="backgrounds_coll")
        """Re-connect signals."""
        self.BackgroundsTreeWidget.itemChanged.connect(
            self.toggle_backgrounds_topology_visibility
        )
        self.BackgroundsTopologyTreeWidget.itemChanged.connect(
            self.toggle_backgrounds_topology_visibility
        )

    """General methods shared by all views."""

    def toggle_property(self):
        """Generic method to toggle the property shown by an actor that is already present in the view."""
        combo = self.sender()
        show_property = combo.currentText()
        uid = combo.uid
        try:
            name = combo.name
        except AttributeError:
            name = None
        show = self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]
        collection = self.actors_df.loc[
            self.actors_df["uid"] == uid, "collection"
        ].values[0]
        """This removes the previous copy of the actor with the same uid, then calls the viewer-specific function that shows an actor with a property.
        IN THE FUTURE see if it is possible and more efficient to keep the actor and just change the property shown."""
        if name == "Marker":
            self.show_markers(uid=uid, show_property=show_property)
        elif name == "Annotations":
            self.show_labels(
                uid=uid, show_property=show_property, collection=collection
            )
        else:
            self.remove_actor_in_view(uid=uid)

            this_actor = self.show_actor_with_property(
                uid=uid,
                collection=collection,
                show_property=show_property,
                visible=show,
            )
            self.actors_df = self.actors_df.append(
                {
                    "uid": uid,
                    "actor": this_actor,
                    "show": show,
                    "collection": collection,
                    "show_prop": show_property,
                },
                ignore_index=True,
            )  # self.set_actor_visible(uid=uid, visible=show)

    def add_all_entities(self):
        """Add all entities in project collections. This must be reimplemented for cross-sections in order
        to show entities belonging to the section only. All objects are visible by default -> show = True
        """

        for index, uid in enumerate(self.parent.geol_coll.df["uid"].tolist()):
            this_actor = self.show_actor_with_property(
                uid=uid, collection="geol_coll", show_property=None, visible=True
            )
            self.actors_df = self.actors_df.append(
                {
                    "uid": uid,
                    "actor": this_actor,
                    "show": True,
                    "collection": "geol_coll",
                    "show_prop": None,
                },
                ignore_index=True,
            )

        for uid in self.parent.xsect_coll.df["uid"].tolist():
            this_actor = self.show_actor_with_property(
                uid=uid, collection="xsect_coll", show_property=None, visible=False
            )
            self.actors_df = self.actors_df.append(
                {
                    "uid": uid,
                    "actor": this_actor,
                    "show": False,
                    "collection": "xsect_coll",
                    "show_prop": None,
                },
                ignore_index=True,
            )

        for uid in self.parent.boundary_coll.df["uid"].tolist():
            this_actor = self.show_actor_with_property(
                uid=uid, collection="boundary_coll", show_property=None, visible=False
            )
            self.actors_df = self.actors_df.append(
                {
                    "uid": uid,
                    "actor": this_actor,
                    "show": False,
                    "collection": "boundary_coll",
                    "show_prop": None,
                },
                ignore_index=True,
            )

        for uid in self.parent.mesh3d_coll.df["uid"].tolist():
            this_actor = self.show_actor_with_property(
                uid=uid, collection="mesh3d_coll", show_property=None, visible=False
            )
            self.actors_df = self.actors_df.append(
                {
                    "uid": uid,
                    "actor": this_actor,
                    "show": False,
                    "collection": "mesh3d_coll",
                    "show_prop": None,
                },
                ignore_index=True,
            )

        for uid in self.parent.dom_coll.df["uid"].tolist():
            this_actor = self.show_actor_with_property(
                uid=uid, collection="dom_coll", show_property=None, visible=False
            )
            self.actors_df = self.actors_df.append(
                {
                    "uid": uid,
                    "actor": this_actor,
                    "show": False,
                    "collection": "dom_coll",
                    "show_prop": None,
                },
                ignore_index=True,
            )

        for uid in self.parent.image_coll.df["uid"].tolist():
            this_actor = self.show_actor_with_property(
                uid=uid, collection="image_coll", show_property=None, visible=False
            )
            self.actors_df = self.actors_df.append(
                {
                    "uid": uid,
                    "actor": this_actor,
                    "show": False,
                    "collection": "image_coll",
                    "show_prop": None,
                },
                ignore_index=True,
            )

        for uid in self.parent.well_coll.df["uid"].tolist():
            this_actor = self.show_actor_with_property(
                uid=uid, collection="well_coll", show_property=None, visible=False
            )
            self.actors_df = self.actors_df.append(
                {
                    "uid": uid,
                    "actor": this_actor,
                    "show": False,
                    "collection": "well_coll",
                    "show_prop": None,
                },
                ignore_index=True,
            )

        for uid in self.parent.fluids_coll.df["uid"].tolist():
            this_actor = self.show_actor_with_property(
                uid=uid, collection="fluids_coll", show_property=None, visible=False
            )
            self.actors_df = self.actors_df.append(
                {
                    "uid": uid,
                    "actor": this_actor,
                    "show": False,
                    "collection": "fluids_coll",
                    "show_prop": None,
                },
                ignore_index=True,
            )
        for uid in self.parent.backgrounds_coll.df["uid"].tolist():
            this_actor = self.show_actor_with_property(
                uid=uid,
                collection="backgrounds_coll",
                show_property=None,
                visible=False,
            )
            self.actors_df = self.actors_df.append(
                {
                    "uid": uid,
                    "actor": this_actor,
                    "show": False,
                    "collection": "backgrounds_coll",
                    "show_prop": None,
                },
                ignore_index=True,
            )

    def prop_legend_cmap_modified_update_views(self, this_property=None):
        """Redraw all actors that are currently shown with a property whose colormap has been changed."""
        for uid in self.actors_df["uid"].to_list():
            if (
                self.actors_df.loc[self.actors_df["uid"] == uid, "show_prop"].to_list()[
                    0
                ]
                == this_property
            ):
                show = self.actors_df.loc[
                    self.actors_df["uid"] == uid, "show"
                ].to_list()[0]
                collection = self.actors_df.loc[
                    self.actors_df["uid"] == uid, "collection"
                ].to_list()[0]
                """This removes the previous copy of the actor with the same uid, then calls the viewer-specific function that shows an actor with a property.
                IN THE FUTURE see if it is possible and more efficient to keep the actor and just change the property shown."""
                self.remove_actor_in_view(uid=uid)
                this_actor = self.show_actor_with_property(
                    uid=uid,
                    collection=collection,
                    show_property=this_property,
                    visible=show,
                )
                self.actors_df = self.actors_df.append(
                    {
                        "uid": uid,
                        "actor": this_actor,
                        "show": show,
                        "collection": collection,
                        "show_prop": this_property,
                    },
                    ignore_index=True,
                )

    def change_actor_color(self, uid=None, collection=None):
        """Update color for actor uid"""
        if uid in self.actors_df.uid:
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
            elif collection == "fluids_coll":
                color_R = self.parent.fluids_coll.get_uid_legend(uid=uid)["color_R"]
                color_G = self.parent.fluids_coll.get_uid_legend(uid=uid)["color_G"]
                color_B = self.parent.fluids_coll.get_uid_legend(uid=uid)["color_B"]
            elif collection == "backgrounds_coll":
                color_R = self.parent.backgrounds_coll.get_uid_legend(uid=uid)["color_R"]
                color_G = self.parent.backgrounds_coll.get_uid_legend(uid=uid)["color_G"]
                color_B = self.parent.backgrounds_coll.get_uid_legend(uid=uid)["color_B"]
            """Note: no legend for image."""
            """Update color for actor uid"""
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[
                0
            ].GetProperty().SetColor(color_RGB)
        else:
            return

    def change_actor_opacity(self, uid=None, collection=None):
        """Update opacity for actor uid"""
        if uid in self.actors_df.uid:
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
            elif collection == "fluids_coll":
                opacity = self.parent.fluids_coll.get_uid_legend(uid=uid)["opacity"] / 100
            elif collection == "backgrounds_coll":
                opacity = (
                    self.parent.backgrounds_coll.get_uid_legend(uid=uid)["opacity"] / 100
                )
            elif collection == "image_coll":
                opacity = self.parent.image_coll.get_legend()["opacity"] / 100
            """Note: no legend for image."""
            """Update color for actor uid"""
            self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[
                0
            ].GetProperty().SetOpacity(opacity)
        else:
            return

    def change_actor_line_thick(self, uid=None, collection=None):
        """Update line thickness for actor uid"""
        if uid in self.actors_df.uid:
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
                """Note: no legend for image."""
            elif collection == "well_coll":
                line_thick = self.parent.well_coll.get_uid_legend(uid=uid)["line_thick"]
            elif collection == "fluids_coll":
                line_thick = self.parent.fluids_coll.get_uid_legend(uid=uid)["line_thick"]
            elif collection == "backgrounds_coll":
                line_thick = self.parent.backgrounds_coll.get_uid_legend(uid=uid)[
                    "line_thick"
                ]
            self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[
                0
            ].GetProperty().SetLineWidth(line_thick)
        else:
            return

    def change_actor_point_size(self, uid=None, collection=None):
        """Update point size for actor uid"""
        if uid in self.actors_df.uid:
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
            elif collection == "fluids_coll":
                point_size = self.parent.fluids_coll.get_uid_legend(uid=uid)["point_size"]
            elif collection == "backgrounds_coll":
                point_size = self.parent.backgrounds_coll.get_uid_legend(uid=uid)[
                    "point_size"
                ]
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
            if name == "Trace":
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
                if f"{uid}_marker-labels" in actors.keys():
                    marker_actor_labels = actors[f"{uid}_marker-labels"]
                    marker_actor_points = actors[f"{uid}_marker-points"]
                    marker_actor_labels.SetVisibility(visible)
                    marker_actor_points.SetVisibility(visible)

        elif collection == "backgrounds_coll":
            if f"{uid}_name-labels" in actors.keys():
                marker_actor_labels = actors[f"{uid}_name-labels"]
                marker_actor_labels.SetVisibility(visible)
            this_actor.SetVisibility(visible)

        else:
            this_actor.SetVisibility(visible)

    def remove_actor_in_view(self, uid=None, redraw=False):
        update = self.parent.update_actors
        print("update: ", update)
        """"Remove actor from plotter"""
        """plotter.remove_actor can remove a single entity or a list of entities as actors -> 
        here we remove a single entity"""
        if not self.actors_df.loc[self.actors_df["uid"] == uid].empty:
            this_actor = self.actors_df.loc[
                self.actors_df["uid"] == uid, "actor"
            ].values[0]
            if not update:
                success = self.plotter.remove_actor(this_actor)
            self.actors_df.drop(
                self.actors_df[self.actors_df["uid"] == uid].index, inplace=True
            )

    def show_actor_with_property(self, uid=None, collection=None, show_property=None, visible=None):
        """Show actor with scalar property (default None)
        https://github.com/pyvista/pyvista/blob/140b15be1d4021b81ded46b1c212c70e86a98ee7/pyvista/plotting/plotting.py#L1045
        """
        """First get the vtk object from its collection."""
        show_property_title = show_property
        show_scalar_bar = True
        if collection == "geol_coll":
            color_R = self.parent.geol_coll.get_uid_legend(uid=uid)["color_R"]
            color_G = self.parent.geol_coll.get_uid_legend(uid=uid)["color_G"]
            color_B = self.parent.geol_coll.get_uid_legend(uid=uid)["color_B"]
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            line_thick = self.parent.geol_coll.get_uid_legend(uid=uid)["line_thick"]
            point_size = self.parent.geol_coll.get_uid_legend(uid=uid)["point_size"]
            opacity = self.parent.geol_coll.get_uid_legend(uid=uid)["opacity"] / 100

            plot_entity = self.parent.geol_coll.get_uid_vtk_obj(uid)
        elif collection == "xsect_coll":
            color_R = self.parent.xsect_coll.get_legend()["color_R"]
            color_G = self.parent.xsect_coll.get_legend()["color_G"]
            color_B = self.parent.xsect_coll.get_legend()["color_B"]
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            line_thick = self.parent.xsect_coll.get_legend()["line_thick"]
            opacity = self.parent.xsect_coll.get_legend()["opacity"] / 100

            plot_entity = self.parent.xsect_coll.get_uid_vtk_frame(uid)
        elif collection == "boundary_coll":
            color_R = self.parent.boundary_coll.get_legend()["color_R"]
            color_G = self.parent.boundary_coll.get_legend()["color_G"]
            color_B = self.parent.boundary_coll.get_legend()["color_B"]
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            line_thick = self.parent.boundary_coll.get_legend()["line_thick"]
            opacity = self.parent.boundary_coll.get_legend()["opacity"] / 100

            plot_entity = self.parent.boundary_coll.get_uid_vtk_obj(uid)
        elif collection == "mesh3d_coll":
            color_R = self.parent.mesh3d_coll.get_legend()["color_R"]
            color_G = self.parent.mesh3d_coll.get_legend()["color_G"]
            color_B = self.parent.mesh3d_coll.get_legend()["color_B"]
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            line_thick = self.parent.mesh3d_coll.get_legend()["line_thick"]
            opacity = self.parent.mesh3d_coll.get_legend()["opacity"] / 100

            plot_entity = self.parent.mesh3d_coll.get_uid_vtk_obj(uid)
        elif collection == "dom_coll":
            color_R = self.parent.dom_coll.get_legend()["color_R"]
            color_G = self.parent.dom_coll.get_legend()["color_G"]
            color_B = self.parent.dom_coll.get_legend()["color_B"]
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            line_thick = self.parent.dom_coll.get_legend()["line_thick"]
            opacity = self.parent.dom_coll.get_legend()["opacity"] / 100

            plot_entity = self.parent.dom_coll.get_uid_vtk_obj(uid)
        elif collection == "image_coll":
            """Note: no legend for image."""
            color_RGB = [255, 255, 255]
            line_thick = 5.0
            opacity = self.parent.image_coll.get_legend()["opacity"] / 100

            plot_entity = self.parent.image_coll.get_uid_vtk_obj(uid)
        elif collection == "well_coll":
            color_R = self.parent.well_coll.get_uid_legend(uid=uid)["color_R"]
            color_G = self.parent.well_coll.get_uid_legend(uid=uid)["color_G"]
            color_B = self.parent.well_coll.get_uid_legend(uid=uid)["color_B"]
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            line_thick = self.parent.well_coll.get_uid_legend(uid=uid)["line_thick"]
            opacity = self.parent.well_coll.get_uid_legend(uid=uid)["opacity"] / 100

            plot_entity = self.parent.well_coll.get_uid_vtk_obj(uid)
        elif collection == "fluids_coll":
            color_R = self.parent.fluids_coll.get_uid_legend(uid=uid)["color_R"]
            color_G = self.parent.fluids_coll.get_uid_legend(uid=uid)["color_G"]
            color_B = self.parent.fluids_coll.get_uid_legend(uid=uid)["color_B"]
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            line_thick = self.parent.fluids_coll.get_uid_legend(uid=uid)["line_thick"]
            point_size = self.parent.fluids_coll.get_uid_legend(uid=uid)["point_size"]
            opacity = self.parent.fluids_coll.get_uid_legend(uid=uid)["opacity"] / 100

            plot_entity = self.parent.fluids_coll.get_uid_vtk_obj(uid)
        elif collection == "backgrounds_coll":
            color_R = self.parent.backgrounds_coll.get_uid_legend(uid=uid)["color_R"]
            color_G = self.parent.backgrounds_coll.get_uid_legend(uid=uid)["color_G"]
            color_B = self.parent.backgrounds_coll.get_uid_legend(uid=uid)["color_B"]
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            line_thick = self.parent.backgrounds_coll.get_uid_legend(uid=uid)[
                "line_thick"
            ]
            point_size = self.parent.backgrounds_coll.get_uid_legend(uid=uid)[
                "point_size"
            ]
            opacity = (
                self.parent.backgrounds_coll.get_uid_legend(uid=uid)["opacity"] / 100
            )

            plot_entity = self.parent.backgrounds_coll.get_uid_vtk_obj(uid)
        else:
            print("no collection")
            print(collection)
            this_actor = None
        """Then plot the vtk object with proper options."""
        if isinstance(plot_entity, (PolyLine, TriSurf, XsPolyLine)) and not isinstance(
            plot_entity, WellTrace
        ):
            plot_rgb_option = None
            if isinstance(plot_entity.points, np_ndarray):
                """This  check is needed to avoid errors when trying to plot an empty
                PolyData, just created at the beginning of a digitizing session."""
                if show_property is None:
                    show_scalar_bar = False
                    pass
                elif show_property == "none":
                    show_scalar_bar = False
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
                    show_scalar_bar=show_scalar_bar,
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
                """This  check is needed to avoid errors when trying to plot an empty
                PolyData, just created at the beginning of a digitizing session."""
                if show_property is None:
                    show_scalar_bar = False
                    pass
                elif show_property == "none":
                    show_scalar_bar = False
                    show_property = None
                elif show_property == "X":
                    show_property = plot_entity.points_X
                elif show_property == "Y":
                    show_property = plot_entity.points_Y
                elif show_property == "Z":
                    show_property = plot_entity.points_Z
                elif show_property == "Normals":
                    show_scalar_bar = False
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
                    show_scalar_bar=show_scalar_bar,
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
            """Show texture specified in show_property"""
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
                    show_scalar_bar=None,
                    color_bar_range=None,
                    show_property_title=None,
                    line_thick=None,
                    plot_texture_option=active_image_texture,
                    plot_rgb_option=False,
                    visible=visible,
                )
            else:
                plot_rgb_option = None
                if show_property is None:
                    show_scalar_bar = False
                    pass
                elif show_property == "none":
                    show_scalar_bar = False
                    show_property = None
                elif show_property == "X":
                    show_property = plot_entity.points_X
                elif show_property == "Y":
                    show_property = plot_entity.points_Y
                elif show_property == "Z":
                    show_property = plot_entity.points_Z
                elif show_property == "RGB":
                    show_scalar_bar = False
                    show_property = None
                else:
                    if plot_entity.get_point_data_shape(show_property)[-1] == 3:
                        plot_rgb_option = True
                this_actor = self.plot_mesh(
                    uid=uid,
                    plot_entity=plot_entity,
                    color_RGB=color_RGB,
                    show_property=show_property,
                    show_scalar_bar=show_scalar_bar,
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
                """This check is needed to avoid errors when trying to plot an empty
                PolyData, just created at the beginning of a digitizing session."""
                if show_property is None:
                    show_scalar_bar = False
                    show_property_value = None
                    pass
                elif show_property == "none":
                    show_scalar_bar = False
                    show_property_value = None
                elif show_property == "X":
                    show_property_value = plot_entity.points_X
                elif show_property == "Y":
                    show_property_value = plot_entity.points_Y
                elif show_property == "Z":
                    show_property_value = plot_entity.points_Z
                elif show_property[-1] == "]":
                    """[Gabriele] we can identify multicomponents properties such as RGB[0] or Normals[0] by taking the last character of the property name ("]")."""
                    show_scalar_bar = True
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
                    """[Gabriele] Get the n of components for the given property. If it's > 1 then do stuff depending on the type of property (e.g. show_rgb_option -> True if the property is RGB)"""
                    if n_comp > 1:
                        show_property_value = plot_entity.get_point_data(show_property)
                        show_scalar_bar = False
                        # if show_property == 'RGB':
                        plot_rgb_option = True
                    else:
                        show_scalar_bar = True
                        show_property_value = plot_entity.get_point_data(show_property)
            this_actor = self.plot_PC_3D(
                uid=uid,
                plot_entity=new_plot,
                color_RGB=color_RGB,
                show_property=show_property_value,
                show_scalar_bar=show_scalar_bar,
                color_bar_range=None,
                show_property_title=show_property_title,
                plot_rgb_option=plot_rgb_option,
                visible=visible,
                point_size=line_thick,
                opacity=opacity,
            )

        elif isinstance(plot_entity, (MapImage, XsImage)):
            """Do not plot directly image - it is much slower.
            Texture options according to type."""
            if show_property is None or show_property == "none":
                plot_texture_option = None
            else:
                plot_texture_option = plot_entity.texture
            this_actor = self.plot_mesh(
                uid=uid,
                plot_entity=plot_entity.frame,
                color_RGB=None,
                show_property=None,
                show_scalar_bar=None,
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
                """This  check is needed to avoid errors when trying to plot an empty
                PolyData, just created at the beginning of a digitizing session."""
                if show_property is None:
                    show_scalar_bar = False
                    pass
                elif show_property == "none":
                    show_scalar_bar = False
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
                    show_scalar_bar=show_scalar_bar,
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
                """This  check is needed to avoid errors when trying to plot an empty Voxet."""
                if show_property is None:
                    show_scalar_bar = False
                elif show_property == "none":
                    show_property = None
                    show_scalar_bar = False
                else:
                    if plot_entity.get_point_data_shape(show_property)[-1] == 3:
                        plot_rgb_option = True
                this_actor = self.plot_mesh(
                    uid=uid,
                    plot_entity=plot_entity,
                    color_RGB=None,
                    show_property=show_property,
                    show_scalar_bar=show_scalar_bar,
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
            if show_property is None:
                show_scalar_bar = False
                pass
            elif show_property == "none":
                show_scalar_bar = False
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
                show_scalar_bar=show_scalar_bar,
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

    def show_markers(self, uid=None, show_property=None):
        plot_entity = self.parent.well_coll.get_uid_vtk_obj(uid)
        marker_data = self.parent.well_coll.get_uid_marker_names(uid)

        if show_property is None:
            show_scalar_bar = False
            pass
        elif show_property == "none":
            show_scalar_bar = False
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
            plot_entity = self.parent.xsect_coll.get_uid_vtk_frame(uid)
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
        elif collection == "fluids_coll":
            plot_entity = self.parent.fluids_coll.get_uid_vtk_obj(uid)
            point = plot_entity.GetCenter()
            name_value = self.parent.fluids_coll.get_uid_name(uid)
        elif collection == "backgrounds_coll":
            plot_entity = self.parent.backgrounds_coll.get_uid_vtk_obj(uid)
            if self.parent.backgrounds_coll.get_uid_topological_type(uid) == "PolyLine":
                point = plot_entity.GetCenter()
            else:
                point = plot_entity.points
            name = plot_entity.get_field_data_keys()[0]
            name_value = plot_entity.get_field_data(name)

        if show_property is None:
            show_scalar_bar = False
            pass
        elif show_property == "none":
            show_scalar_bar = False
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

    def initialize_interactor(self):
        """Add the pyvista interactor object to self.ViewFrameLayout ->
        the layout of an empty frame generated with Qt Designer"""
        # print(self.ViewFrame)
        self.plotter = pvQtInteractor(self.ViewFrame)
        self.plotter.set_background(
            "black"
        )  # background color - could be made interactive in the future
        self.ViewFrameLayout.addWidget(self.plotter.interactor)
        # self.plotter.show_axes_all()
        """Set orientation widget (turned on after the qt canvas is shown)"""
        self.cam_orient_widget = vtkCameraOrientationWidget()
        self.cam_orient_widget.SetParentRenderer(self.plotter.renderer)
        """Set default orientation horizontal because vertical colorbars interfere with the camera widget."""
        pv_global_theme.colorbar_orientation = "horizontal"

        """Manage home view"""
        self.default_view = self.plotter.camera_position

        # self.plotter.track_click_position(
        #    lambda pos: self.plotter.camera.SetFocalPoint(pos), side="left", double=True
        # )

    def initialize_menu_tools(self):
        self.saveHomeView = QAction("Save home view", self)  # create action
        self.saveHomeView.triggered.connect(
            self.save_home_view
        )  # connect action to function
        self.menuBaseView.addAction(self.saveHomeView)  # add action to menu
        self.toolBarBase.addAction(self.saveHomeView)  # add action to toolbar

        self.zoomHomeView = QAction("Zoom to home", self)
        self.zoomHomeView.triggered.connect(self.zoom_home_view)
        self.menuBaseView.addAction(self.zoomHomeView)
        self.toolBarBase.addAction(self.zoomHomeView)

        self.zoomActive = QAction("Zoom to active", self)
        self.zoomActive.triggered.connect(self.zoom_active)
        self.menuBaseView.addAction(self.zoomActive)
        self.toolBarBase.addAction(self.zoomActive)

        self.selectLineButton = QAction("Select entity", self)  # create action
        self.selectLineButton.triggered.connect(
            self.select_actor_with_mouse
        )  # connect action to function
        self.menuBaseView.addAction(self.selectLineButton)  # add action to menu
        self.toolBarBase.addAction(self.selectLineButton)  # add action to toolbar

        self.removeEntityButton = QAction("Remove Entity", self)  # create action
        self.removeEntityButton.triggered.connect(
            self.remove_entity
        )  # connect action to function
        self.menuBaseView.addAction(self.removeEntityButton)  # add action to menu
        self.toolBarBase.addAction(self.removeEntityButton)  # add action to toolbar

        self.clearSelectionButton = QAction("Clear Selection", self)  # create action
        self.clearSelectionButton.triggered.connect(
            self.clear_selection
        )  # connect action to function
        self.menuBaseView.addAction(self.clearSelectionButton)  # add action to menu
        self.toolBarBase.addAction(self.clearSelectionButton)  # add action to toolbar

        self.vertExagButton = QAction("Vertical exaggeration", self)
        self.vertExagButton.triggered.connect(
            self.vert_exag
        )  # connect action to function
        self.menuWindow.addAction(self.vertExagButton)  # add action to menu

    def show_qt_canvas(self):
        """Show the Qt Window"""
        self.show()
        if isinstance(self, View3D):
            self.init_zoom = self.plotter.camera.distance
            self.cam_orient_widget.On()  # [Gabriele] The orientation widget needs to be turned on AFTER the canvas is shown
        # self.picker = self.plotter.enable_mesh_picking(callback= self.pkd_mesh,show_message=False)

    def closeEvent(self, event):
        """Override the standard closeEvent method since self.plotter.close() is needed to cleanly close the vtk
        plotter."""
        reply = QMessageBox.question(
            self,
            "Closing window",
            "Close this window?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            # disconnect_all_signals(self.signals)
            self.disconnect_all_lambda_signals()

            # self.upd_list_geo_rm
            if not isinstance(self, ViewStereoplot):
                self.plotter.close()  # needed to cleanly close the vtk plotter
            event.accept()
        else:
            event.ignore()

    def plot_mesh(
        self,
        uid=None,
        plot_entity=None,
        color_RGB=None,
        show_property=None,
        show_scalar_bar=None,
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
        if not self.actors_df.empty:
            """This stores the camera position before redrawing the actor.
            Added to avoid a bug that sometimes sends the scene to a very distant place.
            Could be used as a basis to implement saved views widgets, synced 3D views, etc.
            The is is needed to avoid sending the camera to the origin that is the
            default position before any mesh is plotted."""
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
            color=color_RGB,
            # string, RGB list, or hex string, overridden if scalars are specified
            style=style,  # 'surface' (default), 'wireframe', or 'points'
            scalars=show_property,  # str pointing to vtk property or numpy.ndarray
            clim=color_bar_range,  # color bar range for scalars, e.g. [-1, 2]
            show_edges=None,  # bool
            edge_color=None,  # default black
            point_size=point_size,  # was 5.0
            line_width=line_thick,
            opacity=opacity,
            # ___________________ single value > uniform opacity. A string can be specified to map the scalars range to opacity.
            flip_scalars=False,  # flip direction of cmap
            lighting=None,  # bool to enable view-direction lighting
            n_colors=256,  # number of colors to use when displaying scalars
            interpolate_before_map=True,
            # bool for smoother scalars display (default True)
            cmap=show_property_cmap,
            # ____________________________ name of the Matplotlib colormap, includes 'colorcet' and 'cmocean', and custom colormaps like ['green', 'red', 'blue']
            label=None,  # string label for legend with pyvista.BasePlotter.add_legend
            reset_camera=None,
            scalar_bar_args={
                "title": show_property_title,
                "title_font_size": 10,
                "label_font_size": 8,
                "shadow": True,
                "interactive": True,
            },
            # keyword arguments for scalar bar, see pyvista.BasePlotter.add_scalar_bar
            show_scalar_bar=show_scalar_bar,  # bool (default True)
            multi_colors=False,  # for MultiBlock datasets
            name=uid,  # actor name
            texture=plot_texture_option,
            # ________________________________ vtk.vtkTexture or np_ndarray or boolean, will work if input mesh has texture coordinates. True > first available texture. String > texture with that name already associated to mesh.
            render_points_as_spheres=points_as_spheres,
            render_lines_as_tubes=render_lines_as_tubes,
            smooth_shading=smooth_shading,
            ambient=0.0,
            diffuse=1.0,
            specular=0.0,
            specular_power=100.0,
            nan_color=None,  # color to use for all NaN values
            nan_opacity=1.0,  # opacity to use for all NaN values
            culling=None,
            # 'front', 'back', 'false' (default) > does not render faces that are culled
            rgb=plot_rgb_option,  # True > plot array values as RGB(A) colors
            categories=False,
            # True > number of unique values in the scalar used as 'n_colors' argument
            use_transparency=False,
            # _______________________ invert the opacity mapping as transparency mapping
            below_color=None,  # solid color for values below the scalars range in 'clim'
            above_color=None,  # solid color for values above the scalars range in 'clim'
            annotations=None,
            # dictionary of annotations for scale bar witor 'points'h keys = float values and values = string annotations
            pickable=pickable,  # bool
            preference="point",
            log_scale=False,
        )
        if not visible:
            this_actor.SetVisibility(False)
        if not self.actors_df.empty:
            """See above."""
            self.plotter.camera_position = camera_position
        return this_actor

    def disable_actions(self):
        for action in self.findChildren(QAction):
            if isinstance(action.parentWidget(), NavigationToolbar) is False:
                action.setDisabled(True)

    def enable_actions(self):
        for action in self.findChildren(QAction):
            action.setEnabled(True)

    def remove_entity(self):
        for sel_uid in self.selected_uids:
            self.plotter.remove_actor(f"{sel_uid}_silh")
        self.parent.entity_remove()

    """ Picking general functions """

    def actor_in_table(self, sel_uid=None):
        """Function used to highlight in the table view a list of selected actors"""
        if sel_uid:
            """[Gabriele] To select the mesh in the entity list we compare the actors of the actors_df dataframe
            with the picker.GetActor() result"""
            collection = self.actors_df.loc[
                self.actors_df["uid"] == sel_uid[0], "collection"
            ].values[0]

            if collection == "geol_coll":
                table = self.parent.GeologyTableView
                df = self.parent.geol_coll.df
                self.parent.tabCentral.setCurrentIndex(
                    0
                )  # set the correct tab to avoid problems
            elif collection == "dom_coll":
                table = self.parent.DOMsTableView
                df = self.parent.dom_coll.df
                self.parent.tabCentral.setCurrentIndex(4)
            else:
                print("Selection not supported")
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
        elif isinstance(self, NewView2D):
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
        style = obj.GetInteractorStyle()
        style.SetDefaultRenderer(self.plotter.renderer)
        pos = obj.GetEventPosition()
        shift = obj.GetShiftKey()
        name_list = set()
        # end_pos = style.GetEndPosition()

        picker = vtkPropPicker()
        picker.PickProp(pos[0], pos[1], style.GetDefaultRenderer())

        actors = set(self.plotter.renderer.actors)

        actor = picker.GetActor()

        if not self.actors_df.loc[self.actors_df["actor"] == actor, "uid"].empty:
            sel_uid = self.actors_df.loc[
                self.actors_df["actor"] == actor, "uid"
            ].values[0]
            if shift:
                self.selected_uids.append(sel_uid)
            else:
                self.selected_uids = [sel_uid]

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

    def vert_exag(self):
        exag_value = input_one_value_dialog(
            parent=self,
            title="Vertical exaggeration options",
            label="Set vertical exaggeration",
            default_value=1.0,
        )

        self.plotter.set_scale(zscale=exag_value)


class View3D(BaseView):
    """Create 3D view and import UI created with Qt Designer by subclassing base view"""

    """parent is the QT object that is launching this one, hence the ProjectWindow() instance in this case"""

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

    """Re-implementations of functions that appear in all views - see placeholders in BaseView()"""

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
        self.menuBaseView.setTitle("Edit")
        self.actionBase_Tool.setText("Edit")

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

        self.menuBaseView.addMenu(self.menuBoreTraceVis)

        self.actionThresholdf.triggered.connect(lambda: thresh_filt(self))
        self.actionSurface_densityf.triggered.connect(lambda: self.surf_den_filt())
        self.actionRoughnessf.triggered.connect(lambda: self.rough_filt())
        self.actionCurvaturef.triggered.connect(lambda: self.curv_filt())
        self.actionNormalsf.triggered.connect(lambda: self.norm_filt())
        self.actionManualBoth.triggered.connect(lambda: cut_pc(self))
        self.actionManualInner.triggered.connect(lambda: cut_pc(self, "inner"))
        self.actionManualOuter.triggered.connect(lambda: cut_pc(self, "outer"))

        self.actionCalibration.triggered.connect(lambda: calibration_pc(self))
        self.actionManual_picking.triggered.connect(lambda: self.act_att())
        self.actionSegment.triggered.connect(lambda: segment_pc(self))
        self.actionPick.triggered.connect(lambda: auto_pick(self))
        self.actionFacets.triggered.connect(lambda: facets_pc(self))

        # self.actionCalculate_normals.triggered.connect(lambda: self.normalGeometry())
        self.actionNormals_to_DDR.triggered.connect(lambda: normals2dd(self))

        # self.showOct = QAction("Show octree structure", self)
        # self.showOct.triggered.connect(self.show_octree)
        # self.menuBaseView.addAction(self.showOct)
        # self.toolBarBase.addAction(self.showOct)

        self.menuOrbit = QMenu("Orbit around", self)

        self.actionOrbitEntity = QAction("Entity", self)
        self.actionOrbitEntity.triggered.connect(lambda: self.orbit_entity())
        self.menuOrbit.addAction(self.actionOrbitEntity)

        self.menuWindow.addMenu(self.menuOrbit)

        """______________THIS MUST BE MOVED TO MAIN WINDOW AND NAME MUST BE MORE SPECIFIC_________________"""
        self.actionExportScreen = QAction("Take screenshot", self)
        self.actionExportScreen.triggered.connect(self.export_screen)
        self.menuBaseView.addAction(self.actionExportScreen)
        self.toolBarBase.addAction(self.actionExportScreen)

        self.actionExportGltf = QAction("Export as GLTF", self)
        self.actionExportGltf.triggered.connect(self.export_gltf)
        self.menuBaseView.addAction(self.actionExportGltf)
        self.toolBarBase.addAction(self.actionExportGltf)

        self.actionExportHtml = QAction("Export as HTML", self)
        self.actionExportHtml.triggered.connect(self.export_html)
        self.menuBaseView.addAction(self.actionExportHtml)
        self.toolBarBase.addAction(self.actionExportHtml)

        self.actionExportObj = QAction("Export as OBJ", self)
        self.actionExportObj.triggered.connect(self.export_obj)
        self.menuBaseView.addAction(self.actionExportObj)
        self.toolBarBase.addAction(self.actionExportObj)

        self.actionExportVtkjs = QAction("Export as VTKjs", self)
        self.actionExportVtkjs.triggered.connect(self.export_vtkjs)
        self.menuBaseView.addAction(self.actionExportVtkjs)
        self.toolBarBase.addAction(self.actionExportVtkjs)

    def export_screen(self):
        out_file_name = save_file_dialog(
            parent=self,
            caption="Export 3D view as HTML.",
            filter="png (*.png);; jpeg (*.jpg)",
        )
        self.plotter.screenshot(
            out_file_name, transparent_background=True, window_size=(1920, 1080)
        )

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
        if self.tog_att == -1:
            input_dict = {
                "name": ["Set name: ", "Set_0"],
                "geological_type": [
                    "Geological type: ",
                    GeologicalCollection.valid_geological_types,
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
            self.parent.geol_coll.replace_vtk(uid, old_vtk_obj, const_color=True)
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

            curr_obj_dict = deepcopy(GeologicalCollection.geological_entity_dict)
            curr_obj_dict["uid"] = str(uuid4())
            curr_obj_dict["name"] = set_opt["name"]
            curr_obj_dict["geological_type"] = set_opt["geological_type"]
            curr_obj_dict["topological_type"] = "VertexSet"
            curr_obj_dict["geological_feature"] = set_opt["name"]
            curr_obj_dict["properties_names"] = properties_name
            curr_obj_dict["properties_components"] = properties_components
            curr_obj_dict["vtk_obj"] = att_point
            """Add to entity collection."""
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
            """See above."""
            self.plotter.camera_position = camera_position
        return this_actor

    """Implementation of functions specific to this view (e.g. particular editing or visualization functions)"""
    """NONE AT THE MOMENT"""

    def plot_PC_3D(
        self,
        uid=None,
        plot_entity=None,
        visible=None,
        color_RGB=None,
        show_property=None,
        show_scalar_bar=None,
        color_bar_range=None,
        show_property_title=None,
        plot_rgb_option=None,
        point_size=1.0,
        points_as_spheres=True,
        opacity=1.0,
    ):
        """[Gabriele]  Plot the point cloud"""
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
            scalar_bar_args={
                "title": show_property_title,
                "title_font_size": 20,
                "label_font_size": 16,
                "shadow": True,
                "interactive": True,
                "vertical": False,
            },
            rgb=plot_rgb_option,
            show_scalar_bar=show_scalar_bar,
            opacity=opacity,
        )
        # self.n_points = plot_entity.GetNumberOfPoints()
        if not visible:
            this_actor.SetVisibility(False)
        if not self.actors_df.empty:
            """See above."""
            self.plotter.camera_position = camera_position
        return this_actor

    def show_octree(self):
        vis_uids = self.actors_df.loc[self.actors_df["show"] == True, "uid"]
        for uid in vis_uids:
            vtk_obj = self.parent.dom_coll.get_uid_vtk_obj(uid)
            oct = PolyData()  # [Gabriele] possible recursion problem
            # print(vtk_obj.locator)
            vtk_obj.locator.GenerateRepresentation(3, oct)

            self.plotter.add_mesh(oct, style="wireframe", color="red")

    def change_bore_vis(self, method):
        actors = set(self.plotter.renderer.actors.copy())
        wells = set(self.parent.well_coll.get_uids())

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

    """[Gabriele] Orbit object ----------------------------------------------------"""

    def orbit_entity(self):
        uid_list = list(self.actors_df["uid"].values)

        dict = {
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
            title="Orbiting options", input_dict=dict, return_widget=False
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


class ViewStereoplot(BaseView):
    def __init__(self, *args, **kwargs):
        super(ViewStereoplot, self).__init__(*args, **kwargs)
        self.setWindowTitle("Stereoplot View")
        self.tog_contours = -1
        # mplstyle.context('classic')

    def initialize_menu_tools(self):
        self.actionContours = QAction("View contours", self)
        self.actionContours.triggered.connect(
            lambda: self.toggle_contours(filled=False)
        )
        self.menuTools.addAction(self.actionContours)

        self.menuPlot = QMenu("Plot options", self)

        self.menuGrids = QMenu("Grid overlays", self)
        self.actionSetPolar = QAction("Set polar grid", self)
        self.actionSetPolar.triggered.connect(lambda: self.change_grid(kind="polar"))
        self.actionSetEq = QAction("Set equatorial grid", self)
        self.actionSetEq.triggered.connect(lambda: self.change_grid(kind="equatorial"))
        self.menuGrids.addAction(self.actionSetPolar)
        self.menuGrids.addAction(self.actionSetEq)
        self.menuPlot.addMenu(self.menuGrids)

        self.menuProj = QMenu("Stereoplot projection", self)
        self.actionSetEquiare = QAction("Equiareal (Schmidt)", self)
        self.actionSetEquiare.triggered.connect(
            lambda: self.change_proj(projection="equal_area_stereonet")
        )
        self.actionSetEquiang = QAction("Equiangolar (Wulff)", self)
        self.actionSetEquiang.triggered.connect(
            lambda: self.change_proj(projection="equal_angle_stereonet")
        )
        self.menuProj.addAction(self.actionSetEquiare)
        self.menuProj.addAction(self.actionSetEquiang)
        self.menuPlot.addMenu(self.menuProj)

        self.menubar.insertMenu(self.menuHelp.menuAction(), self.menuPlot)

    def initialize_interactor(self, kind=None, projection="equal_area_stereonet"):
        self.grid_kind = kind
        self.proj_type = projection

        with mplstyle.context("default"):
            """Create Matplotlib canvas, figure and navi_toolbar. this implicitly creates also the canvas to contain the figure"""
            self.figure, self.ax = mplstereonet.subplots(
                projection=self.proj_type
            )

        self.canvas = FigureCanvas(
            self.figure
        )  # get a reference to the canvas that contains the figure
        # print("dir(self.canvas):\n", dir(self.canvas))
        """https://doc.qt.io/qt-5/qsizepolicy.html"""
        self.navi_toolbar = NavigationToolbar(
            self.figure.canvas, self
        )  # create a navi_toolbar with the matplotlib.backends.backend_qt5agg method NavigationToolbar

        """Create Qt layout andNone add Matplotlib canvas, figure and navi_toolbar"""
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
            ["Type > Feature > Scenario > Name", "uid", "property"]
        )
        self.GeologyTreeWidget.hideColumn(1)  # hide the uid column
        self.GeologyTreeWidget.setItemsExpandable(True)

        filtered_geo = self.parent.geol_coll.df.loc[
            (self.parent.geol_coll.df["topological_type"] == "VertexSet")
            | (self.parent.geol_coll.df["topological_type"] == "XsVertexSet"),
            "geological_type"
        ]
        geo_types = pd_unique(filtered_geo)
        print("geo_types: ", geo_types)

        for geo_type in geo_types:
            glevel_1 = QTreeWidgetItem(
                self.GeologyTreeWidget, [geo_type]
            )  # self.GeologyTreeWidget as parent -> top level
            glevel_1.setFlags(
                glevel_1.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
            )
            filtered_geo_feat = self.parent.geol_coll.df.loc[
                (self.parent.geol_coll.df["geological_type"] == geo_type)
                & (
                    (self.parent.geol_coll.df["topological_type"] == "VertexSet")
                    | (self.parent.geol_coll.df["topological_type"] == "XsVertexSet")
                ),
                "geological_feature"
            ]
            geo_features = pd_unique(filtered_geo_feat)
            print("geo_features: ", geo_features)
            for feature in geo_features:
                glevel_2 = QTreeWidgetItem(
                    glevel_1, [feature]
                )  # glevel_1 as parent -> 1st middle level
                glevel_2.setFlags(
                    glevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
                )
                geo_scenario = pd_unique(
                    self.parent.geol_coll.df.loc[
                        (self.parent.geol_coll.df["geological_type"] == geo_type)
                        & (self.parent.geol_coll.df["geological_feature"] == feature),
                        "scenario"
                    ]
                )
                for scenario in geo_scenario:
                    glevel_3 = QTreeWidgetItem(
                        glevel_2, [scenario]
                    )  # glevel_2 as parent -> 2nd middle level
                    glevel_3.setFlags(
                        glevel_3.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
                    )
                    uids = self.parent.geol_coll.df.loc[
                        (self.parent.geol_coll.df["geological_type"] == geo_type)
                        & (self.parent.geol_coll.df["geological_feature"] == feature)
                        & (self.parent.geol_coll.df["scenario"] == scenario)
                        & (
                            (self.parent.geol_coll.df["topological_type"] == "VertexSet")
                        |(self.parent.geol_coll.df["topological_type"] == "XsVertexSet")
                        ),
                        "uid"
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
                            lambda: self.toggle_property()
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
        """Send messages. Note that with tristate several signals are emitted in a sequence, one for each
        changed item, but upper levels do not broadcast uid's so they are filtered in the toggle method."""
        self.GeologyTreeWidget.itemChanged.connect(
            self.toggle_geology_topology_visibility
        )
        self.GeologyTreeWidget.expandAll()

    def create_topology_tree(self):
        """Create topology tree with checkboxes and properties"""
        self.TopologyTreeWidget.clear()
        self.TopologyTreeWidget.setColumnCount(3)
        self.TopologyTreeWidget.setHeaderLabels(
            ["Type > Scenario > Name", "uid", "property"]
        )
        self.TopologyTreeWidget.hideColumn(1)  # hide the uid column
        self.TopologyTreeWidget.setItemsExpandable(True)

        filtered_topo = self.parent.geol_coll.df.loc[
            (self.parent.geol_coll.df["topological_type"] == "VertexSet")
            | (self.parent.geol_coll.df["topological_type"] == "XsVertexSet"),
            "topological_type"
        ]
        topo_types = pd_unique(filtered_topo)
        for topo_type in topo_types:
            tlevel_1 = QTreeWidgetItem(
                self.TopologyTreeWidget, [topo_type]
            )  # self.GeologyTreeWidget as parent -> top level
            tlevel_1.setFlags(
                tlevel_1.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
            )
            for scenario in pd_unique(
                self.parent.geol_coll.df.loc[
                    self.parent.geol_coll.df["topological_type"] == topo_type,
                    "scenario"
                ]
            ):
                tlevel_2 = QTreeWidgetItem(
                    tlevel_1, [scenario]
                )  # tlevel_1 as parent -> middle level
                tlevel_2.setFlags(
                    tlevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
                )

                uids = self.parent.geol_coll.df.loc[
                    (self.parent.geol_coll.df["topological_type"] == topo_type)
                    & (self.parent.geol_coll.df["scenario"] == scenario)
                    & (
                        (self.parent.geol_coll.df["topological_type"] == "VertexSet")
                        | (
                            self.parent.geol_coll.df["topological_type"]
                            == "XsVertexSet"
                        )
                    ),
                    "uid"
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
                    self.TopologyTreeWidget.setItemWidget(tlevel_3, 2, property_combo)
                    property_combo.currentIndexChanged.connect(
                        lambda: self.toggle_property()
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
        """Send messages. Note that with tristate several signals are emitted in a sequence, one for each
        changed item, but upper levels do not broadcast uid's so they are filtered in the toggle method."""
        self.TopologyTreeWidget.itemChanged.connect(
            self.toggle_geology_topology_visibility
        )
        self.TopologyTreeWidget.expandAll()

    def update_geology_tree_added(self, new_list=None):
        """Update geology tree without creating a new model"""
        uid_list = list(new_list["uid"])
        for uid in uid_list:
            if (
                self.GeologyTreeWidget.findItems(
                    self.parent.geol_coll.get_uid_geological_type(uid),
                    Qt.MatchExactly,
                    0,
                )
                != []
            ):
                """Already exists a TreeItem (1 level) for the geological type"""
                counter_1 = 0
                for child_1 in range(
                    self.GeologyTreeWidget.findItems(
                        self.parent.geol_coll.get_uid_geological_type(uid),
                        Qt.MatchExactly,
                        0,
                    )[0].childCount()
                ):
                    """for cycle that loops n times as the number of subItems in the specific geological type branch"""
                    if self.GeologyTreeWidget.findItems(
                        self.parent.geol_coll.get_uid_geological_type(uid),
                        Qt.MatchExactly,
                        0,
                    )[0].child(child_1).text(
                        0
                    ) == self.parent.geol_coll.get_uid_geological_feature(
                        uid
                    ):
                        counter_1 += 1
                if counter_1 != 0:
                    for child_1 in range(
                        self.GeologyTreeWidget.findItems(
                            self.parent.geol_coll.get_uid_geological_type(uid),
                            Qt.MatchExactly,
                            0,
                        )[0].childCount()
                    ):
                        if self.GeologyTreeWidget.findItems(
                            self.parent.geol_coll.get_uid_geological_type(uid),
                            Qt.MatchExactly,
                            0,
                        )[0].child(child_1).text(
                            0
                        ) == self.parent.geol_coll.get_uid_geological_feature(
                            uid
                        ):
                            """Already exists a TreeItem (2 level) for the geological feature"""
                            counter_2 = 0
                            for child_2 in range(
                                self.GeologyTreeWidget.itemBelow(
                                    self.GeologyTreeWidget.findItems(
                                        self.parent.geol_coll.get_uid_geological_type(
                                            uid
                                        ),
                                        Qt.MatchExactly,
                                        0,
                                    )[0]
                                ).childCount()
                            ):
                                """for cycle that loops n times as the number of sub-subItems in the specific geological type and geological feature branch"""
                                if self.GeologyTreeWidget.itemBelow(
                                    self.GeologyTreeWidget.findItems(
                                        self.parent.geol_coll.get_uid_geological_type(
                                            uid
                                        ),
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
                                            self.parent.geol_coll.get_uid_geological_type(
                                                uid
                                            ),
                                            Qt.MatchExactly,
                                            0,
                                        )[0]
                                    ).childCount()
                                ):
                                    if self.GeologyTreeWidget.itemBelow(
                                        self.GeologyTreeWidget.findItems(
                                            self.parent.geol_coll.get_uid_geological_type(
                                                uid
                                            ),
                                            Qt.MatchExactly,
                                            0,
                                        )[0]
                                    ).child(child_2).text(
                                        0
                                    ) == self.parent.geol_coll.get_uid_scenario(
                                        uid
                                    ):
                                        """Same geological type, geological feature and scenario"""
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
                                                self.parent.geol_coll.get_uid_geological_type(
                                                    uid
                                                ),
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
                                            lambda: self.toggle_property()
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
                                """Same geological type and geological feature, different scenario"""
                                glevel_3 = QTreeWidgetItem(
                                    self.GeologyTreeWidget.findItems(
                                        self.parent.geol_coll.get_uid_geological_type(
                                            uid
                                        ),
                                        Qt.MatchExactly,
                                        0,
                                    )[0].child(child_1),
                                    [self.parent.geol_coll.get_uid_scenario(uid)],
                                )
                                glevel_3.setFlags(
                                    glevel_3.flags()
                                    | Qt.ItemIsTristate
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
                                    lambda: self.toggle_property()
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
                    """Same geological type, different geological feature and scenario"""
                    glevel_2 = QTreeWidgetItem(
                        self.GeologyTreeWidget.findItems(
                            self.parent.geol_coll.get_uid_geological_type(uid),
                            Qt.MatchExactly,
                            0,
                        )[0],
                        [self.parent.geol_coll.get_uid_geological_feature(uid)],
                    )
                    glevel_2.setFlags(
                        glevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
                    )
                    self.GeologyTreeWidget.insertTopLevelItem(0, glevel_2)
                    glevel_3 = QTreeWidgetItem(
                        glevel_2, [self.parent.geol_coll.get_uid_scenario(uid)]
                    )
                    glevel_3.setFlags(
                        glevel_3.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
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
                        lambda: self.toggle_property()
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
                """Different geological type, geological feature and scenario"""
                glevel_1 = QTreeWidgetItem(
                    self.GeologyTreeWidget,
                    [self.parent.geol_coll.get_uid_geological_type(uid)],
                )
                glevel_1.setFlags(
                    glevel_1.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
                )
                self.GeologyTreeWidget.insertTopLevelItem(0, glevel_1)
                glevel_2 = QTreeWidgetItem(
                    glevel_1, [self.parent.geol_coll.get_uid_geological_feature(uid)]
                )
                glevel_2.setFlags(
                    glevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
                )
                self.GeologyTreeWidget.insertTopLevelItem(0, glevel_2)
                glevel_3 = QTreeWidgetItem(
                    glevel_2, [self.parent.geol_coll.get_uid_scenario(uid)]
                )
                glevel_3.setFlags(
                    glevel_3.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
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
                    lambda: self.toggle_property()
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
        self.GeologyTreeWidget.itemChanged.connect(
            self.toggle_geology_topology_visibility
        )
        self.GeologyTreeWidget.expandAll()

    def update_topology_tree_added(self, new_list=None):
        """Update topology tree without creating a new model"""
        uid_list = list(new_list["uid"])
        for uid in uid_list:
            if (
                self.TopologyTreeWidget.findItems(
                    self.parent.geol_coll.get_uid_topological_type(uid),
                    Qt.MatchExactly,
                    0,
                )
                != []
            ):
                """Already exists a TreeItem (1 level) for the topological type"""
                counter_1 = 0
                for child_1 in range(
                    self.TopologyTreeWidget.findItems(
                        self.parent.geol_coll.get_uid_topological_type(uid),
                        Qt.MatchExactly,
                        0,
                    )[0].childCount()
                ):
                    """for cycle that loops n times as the number of subItems in the specific topological type branch"""
                    if self.TopologyTreeWidget.findItems(
                        self.parent.geol_coll.get_uid_topological_type(uid),
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
                        self.TopologyTreeWidget.findItems(
                            self.parent.geol_coll.get_uid_topological_type(uid),
                            Qt.MatchExactly,
                            0,
                        )[0].childCount()
                    ):
                        if self.TopologyTreeWidget.findItems(
                            self.parent.geol_coll.get_uid_topological_type(uid),
                            Qt.MatchExactly,
                            0,
                        )[0].child(child_1).text(
                            0
                        ) == self.parent.geol_coll.get_uid_scenario(
                            uid
                        ):
                            """Same topological type and scenario"""
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
                                self.TopologyTreeWidget.findItems(
                                    self.parent.geol_coll.get_uid_topological_type(uid),
                                    Qt.MatchExactly,
                                    0,
                                )[0].child(child_1),
                                [name, uid],
                            )
                            self.TopologyTreeWidget.setItemWidget(
                                tlevel_3, 2, property_combo
                            )
                            property_combo.currentIndexChanged.connect(
                                lambda: self.toggle_property()
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
                            self.TopologyTreeWidget.insertTopLevelItem(0, tlevel_3)
                            break
                else:
                    """Same topological type, different scenario"""
                    tlevel_2 = QTreeWidgetItem(
                        self.TopologyTreeWidget.findItems(
                            self.parent.geol_coll.get_uid_topological_type(uid),
                            Qt.MatchExactly,
                            0,
                        )[0],
                        [self.parent.geol_coll.get_uid_scenario(uid)],
                    )
                    tlevel_2.setFlags(
                        tlevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
                    )
                    self.TopologyTreeWidget.insertTopLevelItem(0, tlevel_2)
                    property_combo = QComboBox()
                    property_combo.uid = uid
                    # property_combo.addItem("Planes")
                    property_combo.addItem("Poles")
                    for prop in self.parent.geol_coll.get_uid_properties_names(uid):
                        property_combo.addItem(prop)
                    name = self.parent.geol_coll.get_uid_name(uid)
                    tlevel_3 = QTreeWidgetItem(tlevel_2, [name, uid])
                    self.TopologyTreeWidget.setItemWidget(tlevel_3, 2, property_combo)
                    property_combo.currentIndexChanged.connect(
                        lambda: self.toggle_property()
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
                    self.TopologyTreeWidget.insertTopLevelItem(0, tlevel_3)
                    break
            else:
                """Different topological type and scenario"""
                tlevel_1 = QTreeWidgetItem(
                    self.TopologyTreeWidget,
                    [self.parent.geol_coll.get_uid_topological_type(uid)],
                )
                tlevel_1.setFlags(
                    tlevel_1.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
                )
                self.TopologyTreeWidget.insertTopLevelItem(0, tlevel_1)
                tlevel_2 = QTreeWidgetItem(
                    tlevel_1, [self.parent.geol_coll.get_uid_scenario(uid)]
                )
                tlevel_2.setFlags(
                    tlevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable
                )
                self.TopologyTreeWidget.insertTopLevelItem(0, tlevel_2)
                property_combo = QComboBox()
                property_combo.uid = uid
                # property_combo.addItem("Planes")
                property_combo.addItem("Poles")
                for prop in self.parent.geol_coll.get_uid_properties_names(uid):
                    property_combo.addItem(prop)
                name = self.parent.geol_coll.get_uid_name(uid)
                tlevel_3 = QTreeWidgetItem(tlevel_2, [name, uid])
                self.TopologyTreeWidget.setItemWidget(tlevel_3, 2, property_combo)
                property_combo.currentIndexChanged.connect(
                    lambda: self.toggle_property()
                )
                tlevel_3.setFlags(tlevel_3.flags() | Qt.ItemIsUserCheckable)
                if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                    tlevel_3.setCheckState(0, Qt.Checked)
                elif not self.actors_df.loc[
                    self.actors_df["uid"] == uid, "show"
                ].values[0]:
                    tlevel_3.setCheckState(0, Qt.Unchecked)
                self.TopologyTreeWidget.insertTopLevelItem(0, tlevel_3)
                break
        self.TopologyTreeWidget.itemChanged.connect(
            self.toggle_geology_topology_visibility
        )
        self.TopologyTreeWidget.expandAll()

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
            """Hide other images if (1) they are shown and (2) you are showing another one."""
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
            """Then show this one."""
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
        """Can remove a single entity or a list of entities as actors - here we remove a single entity"""

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
                """IN THE FUTURE check if there is a way to redraw just the actor that has just been removed."""
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
        """Show actor with scalar property (default None)
        https://github.com/pyvista/pyvista/blob/140b15be1d4021b81ded46b1c212c70e86a98ee7/pyvista/plotting/plotting.py#L1045"""
        """First get entity from collection."""
        if collection == "geol_coll":
            color_R = self.parent.geol_coll.get_uid_legend(uid=uid)["color_R"]
            color_G = self.parent.geol_coll.get_uid_legend(uid=uid)["color_G"]
            color_B = self.parent.geol_coll.get_uid_legend(uid=uid)["color_B"]
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            line_thick = self.parent.geol_coll.get_uid_legend(uid=uid)["line_thick"]
            plot_entity = self.parent.geol_coll.get_uid_vtk_obj(uid)
        elif collection == "xsect_coll":
            color_R = self.parent.xsect_coll.get_legend()["color_R"]
            color_G = self.parent.xsect_coll.get_legend()["color_G"]
            color_B = self.parent.xsect_coll.get_legend()["color_B"]
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            line_thick = self.parent.xsect_coll.get_legend()["line_thick"]
            plot_entity = self.parent.xsect_coll.get_uid_vtk_frame(uid)
        else:
            plot_entity = None
        """Then plot."""
        if isinstance(plot_entity, (VertexSet, XsVertexSet, Attitude)):
            if isinstance(plot_entity.points, np_ndarray):
                if plot_entity.points_number > 0:
                    """This check is needed to avoid errors when trying to plot an empty
                    PolyData, just created at the beginning of a digitizing session.
                    Check if both these conditions are necessary_________________"""
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

    def stop_event_loops(self):
        """Terminate running event loops"""
        self.figure.canvas.stop_event_loop()

    def change_grid(self, kind):
        self.grid_kind = kind
        self.ViewFrameLayout.removeWidget(self.canvas)
        self.ViewFrameLayout.removeWidget(self.navi_toolbar)
        self.initialize_interactor(kind=kind, projection=self.proj_type)
        uids = self.parent.geol_coll.df.loc[
            self.parent.geol_coll.df["topological_type"] == "VertexSet", "uid"
        ]

        # print(uids)
        """[Gabriele]It is not always the case that VertexSets have normal data (are attitude measurements). When importing from shp we should add a dialog to identify VertexSets as Attitude measurements
        """

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
            self.actors_df = self.actors_df.append(
                {
                    "uid": uid,
                    "actor": this_actor,
                    "show": show,
                    "collection": "geol_collection",
                    "show_prop": "poles",
                },
                ignore_index=True,
            )
            # For now only geol_collection (I guess this is the only collection for attitude measurements)

    def change_proj(self, projection):
        self.proj_type = projection
        self.ViewFrameLayout.removeWidget(self.canvas)
        self.ViewFrameLayout.removeWidget(self.navi_toolbar)
        self.initialize_interactor(kind=self.grid_kind, projection=self.proj_type)
        uids = self.parent.geol_coll.df.loc[
            self.parent.geol_coll.df["topological_type"] == "VertexSet", "uid"
        ]
        for uid in uids:
            show = self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]
            self.remove_actor_in_view(uid, redraw=False)
            this_actor = self.show_actor_with_property(uid, "geol_coll", visible=show)
            self.actors_df = self.actors_df.append(
                {
                    "uid": uid,
                    "actor": this_actor,
                    "show": show,
                    "collection": "geol_collection",
                    "show_prop": "poles",
                },
                ignore_index=True,
            )

    def toggle_contours(self, filled=False):
        """[Gabriele] This is not the best way, but for now will do.
        It's a toggle switch that display kamb contours for visible poles in
        the stereoplot."""

        self.ViewFrameLayout.removeWidget(self.canvas)
        self.ViewFrameLayout.removeWidget(self.navi_toolbar)

        self.initialize_interactor(kind=self.grid_kind, projection=self.proj_type)
        uids = self.parent.geol_coll.df.loc[
            (self.parent.geol_coll.df["topological_type"] == "VertexSet")
            | (self.parent.geol_coll.df["topological_type"] == "XsVertexSet"),
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
            self.actors_df = self.actors_df.append(
                {
                    "uid": uid,
                    "actor": this_actor,
                    "show": show,
                    "collection": "geol_collection",
                    "show_prop": "poles",
                },
                ignore_index=True,
            )

    def change_actor_color(self, uid=None, collection=None):
        "Change colour with Matplotlib method."
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


class NewView2D(BaseView):
    """Create 2D view using vtk/pyvista. This should be more efficient than matplotlib"""

    def __init__(self, *args, **kwargs):
        super(NewView2D, self).__init__(*args, **kwargs)

        self.line_dict = None
        self.plotter.enable_image_style()
        self.plotter.enable_parallel_projection()

    """Re-implementations of functions that appear in all views - see placeholders in BaseView()"""

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
            resample_line_distance,
            resample_line_number_points,
            simplify_line,
            copy_parallel,
            copy_kink,
            copy_similar,
            measure_distance,
            clean_intersection,
        )

        """Imports for this view."""
        """Customize menus and tools for this view"""
        super().initialize_menu_tools()
        self.menuBaseView.setTitle("Edit")
        self.actionBase_Tool.setText("Edit")

        self.drawLineButton = QAction("Draw line", self)  # create action
        self.drawLineButton.triggered.connect(
            lambda: draw_line(self)
        )  # connect action to function with additional argument parent
        self.menuBaseView.addAction(self.drawLineButton)  # add action to menu
        self.toolBarBase.addAction(self.drawLineButton)  # add action to toolbar

        self.editLineButton = QAction("Edit line", self)  # create action
        self.editLineButton.triggered.connect(
            lambda: edit_line(self)
        )  # connect action to function
        self.menuBaseView.addAction(self.editLineButton)  # add action to menu
        self.toolBarBase.addAction(self.editLineButton)  # add action to toolbar

        self.sortLineButton = QAction("Sort line nodes", self)  # create action
        self.sortLineButton.triggered.connect(
            lambda: sort_line_nodes(self)
        )  # connect action to function
        self.menuBaseView.addAction(self.sortLineButton)  # add action to menu
        self.toolBarBase.addAction(self.sortLineButton)  # add action to toolbar

        self.moveLineButton = QAction("Move line", self)  # create action
        self.moveLineButton.triggered.connect(
            lambda: self.vector_by_mouse(move_line)
        )  # connect action to function
        self.menuBaseView.addAction(self.moveLineButton)  # add action to menu
        self.toolBarBase.addAction(self.moveLineButton)  # add action to toolbar

        self.rotateLineButton = QAction("Rotate line", self)  # create action
        self.rotateLineButton.triggered.connect(
            lambda: rotate_line(self)
        )  # connect action to function
        self.menuBaseView.addAction(self.rotateLineButton)  # add action to menu
        self.toolBarBase.addAction(self.rotateLineButton)  # add action to toolbar

        self.extendButton = QAction("Extend line", self)  # create action
        self.extendButton.triggered.connect(
            lambda: extend_line(self)
        )  # connect action to function
        self.menuBaseView.addAction(self.extendButton)  # add action to menu
        self.toolBarBase.addAction(self.extendButton)  # add action to toolbar

        self.splitLineByLineButton = QAction("Split line-line", self)  # create action
        self.splitLineByLineButton.triggered.connect(
            lambda: split_line_line(self)
        )  # connect action to function
        self.menuBaseView.addAction(self.splitLineByLineButton)  # add action to menu
        self.toolBarBase.addAction(self.splitLineByLineButton)  # add action to toolbar

        self.splitLineByPointButton = QAction("Split line-point", self)  # create action
        self.splitLineByPointButton.triggered.connect(
            lambda: split_line_existing_point(self)
        )  # connect action to function
        self.menuBaseView.addAction(self.splitLineByPointButton)  # add action to menu
        self.toolBarBase.addAction(self.splitLineByPointButton)  # add action to toolbar

        self.mergeLineButton = QAction("Merge lines", self)  # create action
        self.mergeLineButton.triggered.connect(
            lambda: merge_lines(self)
        )  # connect action to function
        self.menuBaseView.addAction(self.mergeLineButton)  # add action to menu
        self.toolBarBase.addAction(self.mergeLineButton)  # add action to toolbar

        self.snapLineButton = QAction("Snap line", self)  # create action
        self.snapLineButton.triggered.connect(
            lambda: snap_line(self)
        )  # connect action to function
        self.menuBaseView.addAction(self.snapLineButton)  # add action to menu
        self.toolBarBase.addAction(self.snapLineButton)  # add action to toolbar

        self.resampleDistanceButton = QAction(
            "Resample distance", self
        )  # create action
        self.resampleDistanceButton.triggered.connect(
            lambda: resample_line_distance(self)
        )  # connect action to function
        self.menuBaseView.addAction(self.resampleDistanceButton)  # add action to menu
        self.toolBarBase.addAction(self.resampleDistanceButton)  # add action to toolbar

        self.resampleNumberButton = QAction("Resample number", self)  # create action
        self.resampleNumberButton.triggered.connect(
            lambda: resample_line_number_points(self)
        )  # connect action to function
        self.menuBaseView.addAction(self.resampleNumberButton)  # add action to menu
        self.toolBarBase.addAction(self.resampleNumberButton)  # add action to toolbar

        self.simplifyButton = QAction("Simplify line", self)  # create action
        self.simplifyButton.triggered.connect(
            lambda: simplify_line(self)
        )  # connect action to function
        self.menuBaseView.addAction(self.simplifyButton)  # add action to menu
        self.toolBarBase.addAction(self.simplifyButton)  # add action to toolbar

        self.copyParallelButton = QAction("Copy parallel", self)  # create action
        self.copyParallelButton.triggered.connect(
            lambda: copy_parallel(self)
        )  # connect action to function
        self.menuBaseView.addAction(self.copyParallelButton)  # add action to menu
        self.toolBarBase.addAction(self.copyParallelButton)  # add action to toolbar

        self.copyKinkButton = QAction("Copy kink", self)  # create action
        self.copyKinkButton.triggered.connect(
            lambda: copy_kink(self)
        )  # connect action to function
        self.menuBaseView.addAction(self.copyKinkButton)  # add action to menu
        self.toolBarBase.addAction(self.copyKinkButton)  # add action to toolbar

        self.copySimilarButton = QAction("Copy similar", self)  # create action
        self.copySimilarButton.triggered.connect(
            lambda: self.vector_by_mouse(copy_similar)
        )  # connect action to function
        self.menuBaseView.addAction(self.copySimilarButton)  # add action to menu
        self.toolBarBase.addAction(self.copySimilarButton)  # add action to toolbar

        self.measureDistanceButton = QAction("Measure", self)  # cline_thickreate action
        self.measureDistanceButton.triggered.connect(
            lambda: self.vector_by_mouse(measure_distance)
        )  # connect action to function
        self.menuBaseView.addAction(self.measureDistanceButton)  # add action to menu
        self.toolBarBase.addAction(self.measureDistanceButton)  # add action to toolbar

        self.cleanSectionButton = QAction("Clean intersections", self)
        self.cleanSectionButton.triggered.connect(
            lambda: clean_intersection(self)
        )  # connect action to function
        self.menuBaseView.addAction(self.cleanSectionButton)  # add action to menu
        self.toolBarBase.addAction(self.cleanSectionButton)  # add action to toolbar

    def vector_by_mouse(self, func):
        # if not self.selected_uids:
        #     print(" -- No input data selected -- ")
        #     return
        self.disable_actions()
        vector = Vector(parent=self, pass_func=func)
        vector.EnabledOn()


class NewViewMap(NewView2D):
    def __init__(self, *args, **kwargs):
        super(NewViewMap, self).__init__(*args, **kwargs)
        self.setWindowTitle("Map View")
        self.plotter.view_xy()

    def initialize_menu_tools(self):
        from pzero.collections.xsection_collection import (
            section_from_azimuth,
            sections_from_file,
        )
        from pzero.collections.boundary_collection import boundary_from_points

        super().initialize_menu_tools()
        self.sectionFromAzimuthButton = QAction(
            "Section from azimuth", self
        )  # create action
        self.sectionFromAzimuthButton.triggered.connect(
            lambda: self.vector_by_mouse(section_from_azimuth)
        )  # connect action to function)  # connect action to function with additional argument parent
        self.menuBaseView.addAction(self.sectionFromAzimuthButton)  # add action to menu
        self.toolBarBase.addAction(
            self.sectionFromAzimuthButton
        )  # add action to toolbar

        self.sectionFromFileButton = QAction("Sections from file", self)
        self.sectionFromFileButton.triggered.connect(lambda: sections_from_file(self))

        self.menuBaseView.addAction(self.sectionFromFileButton)  # add action to menu
        self.toolBarBase.addAction(self.sectionFromFileButton)  # add action to toolbar

        self.boundaryFromPointsButton = QAction(
            "Boundary from 2 points", self
        )  # create action
        self.boundaryFromPointsButton.triggered.connect(
            lambda: self.vector_by_mouse(boundary_from_points)
        )  # connect action to function with additional argument parent
        self.menuBaseView.addAction(self.boundaryFromPointsButton)  # add action to menu
        self.toolBarBase.addAction(
            self.boundaryFromPointsButton
        )  # add action to toolbar

    def show_actor_with_property(
        self, uid=None, collection=None, show_property=None, visible=None
    ):
        """Show actor with scalar property (default None)
        https://github.com/pyvista/pyvista/blob/140b15be1d4021b81ded46b1c212c70e86a98ee7/pyvista/plotting/plotting.py#L1045
        """
        """First get the vtk object from its collection."""
        show_property_title = show_property
        show_scalar_bar = True
        if collection == "geol_coll":
            color_R = self.parent.geol_coll.get_uid_legend(uid=uid)["color_R"]
            color_G = self.parent.geol_coll.get_uid_legend(uid=uid)["color_G"]
            color_B = self.parent.geol_coll.get_uid_legend(uid=uid)["color_B"]
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            line_thick = self.parent.geol_coll.get_uid_legend(uid=uid)["line_thick"]
            point_size = self.parent.geol_coll.get_uid_legend(uid=uid)["point_size"]
            opacity = self.parent.geol_coll.get_uid_legend(uid=uid)["opacity"] / 100

            plot_entity = self.parent.geol_coll.get_uid_vtk_obj(uid)
        elif collection == "xsect_coll":
            color_R = self.parent.xsect_coll.get_legend()["color_R"]
            color_G = self.parent.xsect_coll.get_legend()["color_G"]
            color_B = self.parent.xsect_coll.get_legend()["color_B"]
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            line_thick = self.parent.xsect_coll.get_legend()["line_thick"]
            opacity = self.parent.xsect_coll.get_legend()["opacity"] / 100

            plot_entity = self.parent.xsect_coll.get_uid_vtk_frame(uid)
        elif collection == "boundary_coll":
            color_R = self.parent.boundary_coll.get_legend()["color_R"]
            color_G = self.parent.boundary_coll.get_legend()["color_G"]
            color_B = self.parent.boundary_coll.get_legend()["color_B"]
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            line_thick = self.parent.boundary_coll.get_legend()["line_thick"]
            opacity = self.parent.boundary_coll.get_legend()["opacity"] / 100

            plot_entity = self.parent.boundary_coll.get_uid_vtk_obj(uid)
        elif collection == "mesh3d_coll":
            color_R = self.parent.mesh3d_coll.get_legend()["color_R"]
            color_G = self.parent.mesh3d_coll.get_legend()["color_G"]
            color_B = self.parent.mesh3d_coll.get_legend()["color_B"]
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            line_thick = self.parent.mesh3d_coll.get_legend()["line_thick"]
            opacity = self.parent.mesh3d_coll.get_legend()["opacity"] / 100

            plot_entity = self.parent.mesh3d_coll.get_uid_vtk_obj(uid)
        elif collection == "dom_coll":
            color_R = self.parent.dom_coll.get_legend()["color_R"]
            color_G = self.parent.dom_coll.get_legend()["color_G"]
            color_B = self.parent.dom_coll.get_legend()["color_B"]
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            line_thick = self.parent.dom_coll.get_legend()["line_thick"]
            opacity = self.parent.dom_coll.get_legend()["opacity"] / 100

            plot_entity = self.parent.dom_coll.get_uid_vtk_obj(uid)
        elif collection == "image_coll":
            """Note: no legend for image."""
            color_RGB = [255, 255, 255]
            line_thick = 5.0
            opacity = self.parent.image_coll.get_legend()["opacity"] / 100

            plot_entity = self.parent.image_coll.get_uid_vtk_obj(uid)
        elif collection == "well_coll":
            color_R = self.parent.well_coll.get_uid_legend(uid=uid)["color_R"]
            color_G = self.parent.well_coll.get_uid_legend(uid=uid)["color_G"]
            color_B = self.parent.well_coll.get_uid_legend(uid=uid)["color_B"]
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            line_thick = self.parent.well_coll.get_uid_legend(uid=uid)["line_thick"]
            opacity = self.parent.well_coll.get_uid_legend(uid=uid)["opacity"] / 100

            plot_entity = self.parent.well_coll.get_uid_vtk_obj(uid)
        elif collection == "fluids_coll":
            color_R = self.parent.fluids_coll.get_uid_legend(uid=uid)["color_R"]
            color_G = self.parent.fluids_coll.get_uid_legend(uid=uid)["color_G"]
            color_B = self.parent.fluids_coll.get_uid_legend(uid=uid)["color_B"]
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            line_thick = self.parent.fluids_coll.get_uid_legend(uid=uid)["line_thick"]
            point_size = self.parent.fluids_coll.get_uid_legend(uid=uid)["point_size"]
            opacity = self.parent.fluids_coll.get_uid_legend(uid=uid)["opacity"] / 100

            plot_entity = self.parent.fluids_coll.get_uid_vtk_obj(uid)
        elif collection == "backgrounds_coll":
            color_R = self.parent.backgrounds_coll.get_uid_legend(uid=uid)["color_R"]
            color_G = self.parent.backgrounds_coll.get_uid_legend(uid=uid)["color_G"]
            color_B = self.parent.backgrounds_coll.get_uid_legend(uid=uid)["color_B"]
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            line_thick = self.parent.backgrounds_coll.get_uid_legend(uid=uid)[
                "line_thick"
            ]
            point_size = self.parent.backgrounds_coll.get_uid_legend(uid=uid)[
                "point_size"
            ]
            opacity = (
                self.parent.backgrounds_coll.get_uid_legend(uid=uid)["opacity"] / 100
            )

            plot_entity = self.parent.backgrounds_coll.get_uid_vtk_obj(uid)
        else:
            print("no collection")
            print(collection)
            this_actor = None
        """Then plot the vtk object with proper options."""
        if isinstance(plot_entity, (PolyLine, TriSurf, XsPolyLine)) and not isinstance(
            plot_entity, WellTrace
        ):
            plot_rgb_option = None
            if isinstance(plot_entity.points, np_ndarray):
                """This  check is needed to avoid errors when trying to plot an empty
                PolyData, just created at the beginning of a digitizing session."""
                if show_property is None:
                    show_scalar_bar = False
                    pass
                elif show_property == "none":
                    show_scalar_bar = False
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
                    show_scalar_bar=show_scalar_bar,
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
                """This  check is needed to avoid errors when trying to plot an empty
                PolyData, just created at the beginning of a digitizing session."""
                if show_property is None:
                    show_scalar_bar = False
                    pass
                elif show_property == "none":
                    show_scalar_bar = False
                    show_property = None
                elif show_property == "X":
                    show_property = plot_entity.points_X
                elif show_property == "Y":
                    show_property = plot_entity.points_Y
                elif show_property == "Z":
                    show_property = plot_entity.points_Z
                elif show_property == "Normals":
                    show_scalar_bar = False
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
                    show_scalar_bar=show_scalar_bar,
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
            """Show texture specified in show_property"""
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
                    show_scalar_bar=None,
                    color_bar_range=None,
                    show_property_title=None,
                    line_thick=None,
                    plot_texture_option=active_image_texture,
                    plot_rgb_option=False,
                    visible=visible,
                )
            else:
                plot_rgb_option = None
                if show_property is None:
                    show_scalar_bar = False
                    pass
                elif show_property == "none":
                    show_scalar_bar = False
                    show_property = None
                elif show_property == "X":
                    show_property = plot_entity.points_X
                elif show_property == "Y":
                    show_property = plot_entity.points_Y
                elif show_property == "Z":
                    show_property = plot_entity.points_Z
                elif show_property == "RGB":
                    show_scalar_bar = False
                    show_property = None
                else:
                    if plot_entity.get_point_data_shape(show_property)[-1] == 3:
                        plot_rgb_option = True
                this_actor = self.plot_mesh(
                    uid=uid,
                    plot_entity=plot_entity,
                    color_RGB=color_RGB,
                    show_property=show_property,
                    show_scalar_bar=show_scalar_bar,
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
                """This check is needed to avoid errors when trying to plot an empty
                PolyData, just created at the beginning of a digitizing session."""
                if show_property is None:
                    show_scalar_bar = False
                    show_property_value = None
                    pass
                elif show_property == "none":
                    show_scalar_bar = False
                    show_property_value = None
                elif show_property == "X":
                    show_property_value = plot_entity.points_X
                elif show_property == "Y":
                    show_property_value = plot_entity.points_Y
                elif show_property == "Z":
                    show_property_value = plot_entity.points_Z
                elif show_property[-1] == "]":
                    """[Gabriele] we can identify multicomponents properties such as RGB[0] or Normals[0] by taking the last character of the property name ("]")."""
                    show_scalar_bar = True
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
                    """[Gabriele] Get the n of components for the given property. If it's > 1 then do stuff depending on the type of property (e.g. show_rgb_option -> True if the property is RGB)"""
                    if n_comp > 1:
                        show_property_value = plot_entity.get_point_data(show_property)
                        show_scalar_bar = False
                        # if show_property == 'RGB':
                        plot_rgb_option = True
                    else:
                        show_scalar_bar = True
                        show_property_value = plot_entity.get_point_data(show_property)
            this_actor = self.plot_PC_3D(
                uid=uid,
                plot_entity=new_plot,
                color_RGB=color_RGB,
                show_property=show_property_value,
                show_scalar_bar=show_scalar_bar,
                color_bar_range=None,
                show_property_title=show_property_title,
                plot_rgb_option=plot_rgb_option,
                visible=visible,
                point_size=line_thick,
                opacity=opacity,
            )

        elif isinstance(plot_entity, (MapImage, XsImage)):
            """Do not plot directly image - it is much slower.
            Texture options according to type."""
            if show_property is None or show_property == "none":
                plot_texture_option = None
            else:
                plot_texture_option = plot_entity.texture
            this_actor = self.plot_mesh(
                uid=uid,
                plot_entity=plot_entity.frame,
                color_RGB=None,
                show_property=None,
                show_scalar_bar=None,
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
                """This  check is needed to avoid errors when trying to plot an empty
                PolyData, just created at the beginning of a digitizing session."""
                if show_property is None:
                    show_scalar_bar = False
                    pass
                elif show_property == "none":
                    show_scalar_bar = False
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
                    show_scalar_bar=show_scalar_bar,
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
                """This  check is needed to avoid errors when trying to plot an empty Voxet."""
                if show_property is None:
                    show_scalar_bar = False
                elif show_property == "none":
                    show_property = None
                    show_scalar_bar = False
                else:
                    if plot_entity.get_point_data_shape(show_property)[-1] == 3:
                        plot_rgb_option = True
                this_actor = self.plot_mesh(
                    uid=uid,
                    plot_entity=plot_entity,
                    color_RGB=None,
                    show_property=show_property,
                    show_scalar_bar=show_scalar_bar,
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
            if show_property is None:
                show_scalar_bar = False
                pass
            elif show_property == "none":
                show_scalar_bar = False
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
                show_scalar_bar=show_scalar_bar,
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


class NewViewXsection(NewView2D):
    def __init__(self, parent=None, *args, **kwargs):
        if parent.xsect_coll.get_names():
            self.this_x_section_name = input_combo_dialog(
                parent=None,
                title="Xsection",
                label="Choose Xsection",
                choice_list=parent.xsect_coll.get_names(),
            )
        else:
            message_dialog(title="Xsection", message="No Xsection in project")
            return
        if self.this_x_section_name:
            self.this_x_section_uid = parent.xsect_coll.df.loc[
                parent.xsect_coll.df["name"] == self.this_x_section_name, "uid"
            ].values[0]
        else:
            return

        """super here after having set the x_section_uid and _name"""
        super(NewViewXsection, self).__init__(parent, *args, **kwargs)

        """Rename Base View, Menu and Tool"""
        self.setWindowTitle("Xsection View")

        self.create_geology_tree(sec_uid=self.this_x_section_uid)
        self.create_topology_tree(sec_uid=self.this_x_section_uid)
        self.create_xsections_tree(sec_uid=self.this_x_section_uid)
        self.create_boundary_list(sec_uid=self.this_x_section_uid)
        self.create_mesh3d_list(sec_uid=self.this_x_section_uid)
        self.create_dom_list(sec_uid=self.this_x_section_uid)
        self.create_image_list(sec_uid=self.this_x_section_uid)

        # We should add something to programmatically set the visibility of entities via UID
        # Don't know if it is already implemented or not
        self.set_actor_visible(uid=self.this_x_section_uid, visible=True)
        self.update_xsection_checkboxes(
            uid=self.this_x_section_uid, uid_checkState=Qt.Checked
        )

        section_plane = parent.xsect_coll.get_uid_vtk_plane(self.this_x_section_uid)
        center = np_array(section_plane.GetOrigin())
        direction = -np_array(section_plane.GetNormal())

        self.plotter.camera.focal_point = center
        self.plotter.camera.position = center + direction
        self.plotter.reset_camera()

    def add_all_entities(self):
        """Add all entities in project collections. All objects are visible by default -> show = True"""
        sec_uid = self.this_x_section_uid
        for uid in self.parent.geol_coll.df["uid"].tolist():
            if self.parent.geol_coll.get_uid_x_section(uid) == sec_uid:
                this_actor = self.show_actor_with_property(
                    uid=uid, collection="geol_coll", show_property=None, visible=True
                )
                self.actors_df = self.actors_df.append(
                    {
                        "uid": uid,
                        "actor": this_actor,
                        "show": True,
                        "collection": "geol_coll",
                        "show_prop": None,
                    },
                    ignore_index=True,
                )

        for uid in self.parent.xsect_coll.df["uid"].tolist():
            if uid == sec_uid:
                this_actor = self.show_actor_with_property(
                    uid=uid, collection="xsect_coll", show_property=None, visible=False
                )
                self.actors_df = self.actors_df.append(
                    {
                        "uid": uid,
                        "actor": this_actor,
                        "show": False,
                        "collection": "xsect_coll",
                        "show_prop": None,
                    },
                    ignore_index=True,
                )

        for uid in self.parent.boundary_coll.df["uid"].tolist():
            if self.parent.boundary_coll.get_uid_x_section(uid) == sec_uid:
                this_actor = self.show_actor_with_property(
                    uid=uid,
                    collection="boundary_coll",
                    show_property=None,
                    visible=False,
                )
                self.actors_df = self.actors_df.append(
                    {
                        "uid": uid,
                        "actor": this_actor,
                        "show": False,
                        "collection": "boundary_coll",
                        "show_prop": None,
                    },
                    ignore_index=True,
                )
        for uid in self.parent.mesh3d_coll.df["uid"].tolist():
            if self.parent.mesh3d_coll.get_uid_x_section(uid) == sec_uid:
                this_actor = self.show_actor_with_property(
                    uid=uid, collection="mesh3d_coll", show_property=None, visible=False
                )
                self.actors_df = self.actors_df.append(
                    {
                        "uid": uid,
                        "actor": this_actor,
                        "show": False,
                        "collection": "mesh3d_coll",
                        "show_prop": None,
                    },
                    ignore_index=True,
                )
        for uid in self.parent.dom_coll.df["uid"].tolist():
            if self.parent.dom_coll.get_uid_x_section(uid) == sec_uid:
                this_actor = self.show_actor_with_property(
                    uid=uid, collection="dom_coll", show_property=None, visible=False
                )
                self.actors_df = self.actors_df.append(
                    {
                        "uid": uid,
                        "actor": this_actor,
                        "show": False,
                        "collection": "dom_coll",
                        "show_prop": None,
                    },
                    ignore_index=True,
                )
        for uid in self.parent.image_coll.df["uid"].tolist():
            if self.parent.image_coll.get_uid_x_section(uid) == sec_uid:
                this_actor = self.show_actor_with_property(
                    uid=uid, collection="image_coll", show_property=None, visible=False
                )
                self.actors_df = self.actors_df.append(
                    {
                        "uid": uid,
                        "actor": this_actor,
                        "show": False,
                        "collection": "image_coll",
                        "show_prop": None,
                    },
                    ignore_index=True,
                )
        for uid in self.parent.well_coll.df["uid"].tolist():
            this_actor = self.show_actor_with_property(
                uid=uid, collection="well_coll", show_property=None, visible=False
            )
            self.actors_df = self.actors_df.append(
                {
                    "uid": uid,
                    "actor": this_actor,
                    "show": False,
                    "collection": "well_coll",
                    "show_prop": None,
                },
                ignore_index=True,
            )
        for uid in self.parent.fluids_coll.df["uid"].tolist():
            if self.parent.fluids_coll.get_uid_x_section(uid) == sec_uid:
                this_actor = self.show_actor_with_property(
                    uid=uid, collection="fluids_coll", show_property=None, visible=False
                )
                self.actors_df = self.actors_df.append(
                    {
                        "uid": uid,
                        "actor": this_actor,
                        "show": False,
                        "collection": "fluids_coll",
                        "show_prop": None,
                    },
                    ignore_index=True,
                )
        for uid in self.parent.backgrounds_coll.df["uid"].tolist():
            if self.parent.backgrounds_coll.get_uid_x_section(uid) == sec_uid:
                this_actor = self.show_actor_with_property(
                    uid=uid,
                    collection="backgrounds_coll",
                    show_property=None,
                    visible=False,
                )
                self.actors_df = self.actors_df.append(
                    {
                        "uid": uid,
                        "actor": this_actor,
                        "show": False,
                        "collection": "backgrounds_coll",
                        "show_prop": None,
                    },
                    ignore_index=True,
                )

    def change_actor_color(self, uid=None, collection=None):
        """Update color for actor uid"""
        sec_uid = self.this_x_section_uid
        attr = getattr(self.parent, collection)
        # if attr.get_uid_x_section(uid=uid) == sec_uid:
        #     color_R = attr.get_uid_legend(uid=uid)['color_R']
        #     color_G = attr.get_uid_legend(uid=uid)['color_G']
        #     color_B = attr.get_uid_legend(uid=uid)['color_B']

        # if attr.get_uid_x_section(uid=uid) == sec_uid:
        if uid in self.actors_df.uid:
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
            elif collection == "fluids_coll":
                color_R = self.parent.fluids_coll.get_uid_legend(uid=uid)["color_R"]
                color_G = self.parent.fluids_coll.get_uid_legend(uid=uid)["color_G"]
                color_B = self.parent.fluids_coll.get_uid_legend(uid=uid)["color_B"]
            elif collection == "backgrounds_coll":
                color_R = self.parent.backgrounds_coll.get_uid_legend(uid=uid)[
                    "color_R"
                ]
                color_G = self.parent.backgrounds_coll.get_uid_legend(uid=uid)[
                    "color_G"
                ]
                color_B = self.parent.backgrounds_coll.get_uid_legend(uid=uid)[
                    "color_B"
                ]
            """Note: no legend for image."""
            """Update color for actor uid"""
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[
                0
            ].GetProperty().SetColor(color_RGB)

    def change_actor_line_thick(self, uid=None, collection=None):
        """Update line thickness for actor uid"""

        sec_uid = self.this_x_section_uid
        attr = getattr(self.parent, collection)
        if attr.get_uid_x_section(uid) == sec_uid:

            if collection == "geol_coll":
                line_thick = self.parent.geol_coll.get_uid_legend(uid=uid)["line_thick"]
                if isinstance(
                    self.parent.geol_coll.get_uid_vtk_obj(uid), VertexSet
                ) or isinstance(
                    self.parent.geol_coll.get_uid_vtk_obj(uid), XsVertexSet
                ):
                    self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[
                        0
                    ].GetProperty().SetPointSize(line_thick)
                else:
                    self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[
                        0
                    ].GetProperty().SetLineWidth(line_thick)

            elif collection == "xsect_coll":
                line_thick = self.parent.xsect_coll.get_legend()["line_thick"]
            elif collection == "boundary_coll":
                line_thick = self.parent.boundary_coll.get_legend()["line_thick"]
            elif collection == "mesh3d_coll":
                line_thick = self.parent.mesh3d_coll.get_legend()["line_thick"]
            elif collection == "dom_coll":
                line_thick = self.parent.dom_coll.get_legend()["line_thick"]
                """Note: no legend for image."""
                if isinstance(self.parent.dom_coll.get_uid_vtk_obj(uid), PCDom):
                    """Use line_thick to set point size here."""
                    self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[
                        0
                    ].GetProperty().SetPointSize(line_thick)
                else:
                    self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[
                        0
                    ].GetProperty().SetLineWidth(line_thick)
            elif collection == "well_coll":
                line_thick = self.parent.well_coll.get_uid_legend(uid=uid)["line_thick"]
                self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[
                    0
                ].GetProperty().SetLineWidth(line_thick)
            elif collection == "fluids_coll":
                line_thick = self.parent.fluids_coll.get_uid_legend(uid=uid)[
                    "line_thick"
                ]

                if isinstance(self.parent.fluids_coll.get_uid_vtk_obj(uid), VertexSet):
                    self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[
                        0
                    ].GetProperty().SetPointSize(line_thick)
                else:
                    self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[
                        0
                    ].GetProperty().SetLineWidth(line_thick)

            elif collection == "backgrounds_coll":
                line_thick = self.parent.backgrounds_coll.get_uid_legend(uid=uid)[
                    "line_thick"
                ]

                if isinstance(
                    self.parent.backgrounds_coll.get_uid_vtk_obj(uid), VertexSet
                ):
                    self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[
                        0
                    ].GetProperty().SetPointSize(line_thick)
                else:
                    self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[
                        0
                    ].GetProperty().SetLineWidth(line_thick)

    def show_actor_with_property(
        self, uid=None, collection=None, show_property=None, visible=None
    ):
        """Show actor with scalar property (default None)
        https://github.com/pyvista/pyvista/blob/140b15be1d4021b81ded46b1c212c70e86a98ee7/pyvista/plotting/plotting.py#L1045
        """
        """First get the vtk object from its collection."""
        show_property_title = show_property
        show_scalar_bar = True
        sec_uid = self.this_x_section_uid
        if (
            collection == "geol_coll"
            and self.parent.geol_coll.get_uid_x_section(uid) == sec_uid
        ):
            color_R = self.parent.geol_coll.get_uid_legend(uid=uid)["color_R"]
            color_G = self.parent.geol_coll.get_uid_legend(uid=uid)["color_G"]
            color_B = self.parent.geol_coll.get_uid_legend(uid=uid)["color_B"]
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            line_thick = self.parent.geol_coll.get_uid_legend(uid=uid)["line_thick"]
            point_size = self.parent.geol_coll.get_uid_legend(uid=uid)["point_size"]
            opacity = self.parent.geol_coll.get_uid_legend(uid=uid)["opacity"] / 100

            plot_entity = self.parent.geol_coll.get_uid_vtk_obj(uid)
        elif collection == "xsect_coll" and uid == sec_uid:
            color_R = self.parent.xsect_coll.get_legend()["color_R"]
            color_G = self.parent.xsect_coll.get_legend()["color_G"]
            color_B = self.parent.xsect_coll.get_legend()["color_B"]
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            line_thick = self.parent.xsect_coll.get_legend()["line_thick"]
            opacity = self.parent.xsect_coll.get_legend()["opacity"] / 100

            plot_entity = self.parent.xsect_coll.get_uid_vtk_frame(uid)
        elif (
            collection == "boundary_coll"
            and self.parent.boundary_coll.get_uid_x_section(uid) == sec_uid
        ):
            color_R = self.parent.boundary_coll.get_legend()["color_R"]
            color_G = self.parent.boundary_coll.get_legend()["color_G"]
            color_B = self.parent.boundary_coll.get_legend()["color_B"]
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            line_thick = self.parent.boundary_coll.get_legend()["line_thick"]
            opacity = self.parent.boundary_coll.get_legend()["opacity"] / 100

            plot_entity = self.parent.boundary_coll.get_uid_vtk_obj(uid)
        elif (
            collection == "mesh3d_coll"
            and self.parent.mesh3d_coll.get_uid_x_section(uid) == sec_uid
        ):
            color_R = self.parent.mesh3d_coll.get_legend()["color_R"]
            color_G = self.parent.mesh3d_coll.get_legend()["color_G"]
            color_B = self.parent.mesh3d_coll.get_legend()["color_B"]
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            line_thick = self.parent.mesh3d_coll.get_legend()["line_thick"]
            opacity = self.parent.mesh3d_coll.get_legend()["opacity"] / 100

            plot_entity = self.parent.mesh3d_coll.get_uid_vtk_obj(uid)
        elif (
            collection == "dom_coll"
            and self.parent.dom_coll.get_uid_x_section(uid) == sec_uid
        ):
            color_R = self.parent.dom_coll.get_legend()["color_R"]
            color_G = self.parent.dom_coll.get_legend()["color_G"]
            color_B = self.parent.dom_coll.get_legend()["color_B"]
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            line_thick = self.parent.dom_coll.get_legend()["line_thick"]
            opacity = self.parent.dom_coll.get_legend()["opacity"] / 100

            plot_entity = self.parent.dom_coll.get_uid_vtk_obj(uid)

        elif (
            collection == "image_coll"
            and self.parent.image_coll.get_uid_x_section(uid) == sec_uid
        ):
            """Note: no legend for image."""
            color_RGB = [255, 255, 255]
            line_thick = 5.0
            opacity = self.parent.image_coll.get_legend()["opacity"] / 100

            plot_entity = self.parent.image_coll.get_uid_vtk_obj(uid)
        elif (
            collection == "well_coll"
            and self.parent.well_coll.get_uid_x_section(uid) == sec_uid
        ):
            color_R = self.parent.well_coll.get_uid_legend(uid=uid)["color_R"]
            color_G = self.parent.well_coll.get_uid_legend(uid=uid)["color_G"]
            color_B = self.parent.well_coll.get_uid_legend(uid=uid)["color_B"]
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            line_thick = self.parent.well_coll.get_uid_legend(uid=uid)["line_thick"]
            opacity = self.parent.well_coll.get_uid_legend(uid=uid)["opacity"] / 100

            plot_entity = self.parent.well_coll.get_uid_vtk_obj(uid)
        elif (
            collection == "fluids_coll"
            and self.parent.fluids_coll.get_uid_x_section(uid) == sec_uid
        ):
            color_R = self.parent.fluids_coll.get_uid_legend(uid=uid)["color_R"]
            color_G = self.parent.fluids_coll.get_uid_legend(uid=uid)["color_G"]
            color_B = self.parent.fluids_coll.get_uid_legend(uid=uid)["color_B"]
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            line_thick = self.parent.fluids_coll.get_uid_legend(uid=uid)["line_thick"]
            point_size = self.parent.fluids_coll.get_uid_legend(uid=uid)["point_size"]
            opacity = self.parent.fluids_coll.get_uid_legend(uid=uid)["opacity"] / 100

            plot_entity = self.parent.fluids_coll.get_uid_vtk_obj(uid)
        elif (
            collection == "backgrounds_coll"
            and self.parent.backgrounds_coll.get_uid_x_section(uid) == sec_uid
        ):
            color_R = self.parent.backgrounds_coll.get_uid_legend(uid=uid)["color_R"]
            color_G = self.parent.backgrounds_coll.get_uid_legend(uid=uid)["color_G"]
            color_B = self.parent.backgrounds_coll.get_uid_legend(uid=uid)["color_B"]
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            line_thick = self.parent.backgrounds_coll.get_uid_legend(uid=uid)[
                "line_thick"
            ]
            point_size = self.parent.backgrounds_coll.get_uid_legend(uid=uid)[
                "point_size"
            ]
            opacity = (
                self.parent.backgrounds_coll.get_uid_legend(uid=uid)["opacity"] / 100
            )

            plot_entity = self.parent.backgrounds_coll.get_uid_vtk_obj(uid)
        else:
            print("no collection")
            print(collection)
            return
        """Then plot the vtk object with proper options."""
        if isinstance(plot_entity, (PolyLine, TriSurf, XsPolyLine)) and not isinstance(
            plot_entity, WellTrace
        ):
            plot_rgb_option = None
            if isinstance(plot_entity.points, np_ndarray):
                """This  check is needed to avoid errors when trying to plot an empty
                PolyData, just created at the beginning of a digitizing session."""
                if show_property is None:
                    show_scalar_bar = False
                    pass
                elif show_property == "none":
                    show_scalar_bar = False
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
                    show_scalar_bar=show_scalar_bar,
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
                """This  check is needed to avoid errors when trying to plot an empty
                PolyData, just created at the beginning of a digitizing session."""
                if show_property is None:
                    show_scalar_bar = False
                    pass
                elif show_property == "none":
                    show_scalar_bar = False
                    show_property = None
                elif show_property == "X":
                    show_property = plot_entity.points_X
                elif show_property == "Y":
                    show_property = plot_entity.points_Y
                elif show_property == "Z":
                    show_property = plot_entity.points_Z
                elif show_property == "Normals":
                    show_scalar_bar = False
                    show_property_title = None
                    show_property = None
                    style = "surface"
                    appender = vtkAppendPolyData()
                    r = self.parent.geol_coll.get_uid_legend(uid=uid)["point_size"] * 4
                    normals = plot_entity.get_point_data("Normals")
                    dip_vectors, _ = get_dip_dir_vectors(normals=normals)

                    plane_n = -np_array(
                        self.parent.xsect_coll.get_uid_vtk_plane(
                            self.this_x_section_uid
                        ).GetNormal()
                    )
                    vector2 = np_cross(plane_n, dip_vectors)
                    line1 = pv_Line(pointa=(0, 0, 0), pointb=(r, 0, 0))
                    line2 = pv_Line(pointa=(0, 0, 0), pointb=(r * 0.25, 0, 0))

                    dip_glyph = plot_entity.glyph(geometry=line1, prop=dip_vectors)
                    n_glyph = plot_entity.glyph(geometry=line2, prop=vector2)

                    appender.AddInputData(dip_glyph)
                    appender.AddInputData(n_glyph)
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
                    show_scalar_bar=show_scalar_bar,
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
            """Show texture specified in show_property"""
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
                    show_scalar_bar=None,
                    color_bar_range=None,
                    show_property_title=None,
                    line_thick=None,
                    plot_texture_option=active_image_texture,
                    plot_rgb_option=False,
                    visible=visible,
                )
            else:
                plot_rgb_option = None
                if show_property is None:
                    show_scalar_bar = False
                    pass
                elif show_property == "none":
                    show_scalar_bar = False
                    show_property = None
                elif show_property == "X":
                    show_property = plot_entity.points_X
                elif show_property == "Y":
                    show_property = plot_entity.points_Y
                elif show_property == "Z":
                    show_property = plot_entity.points_Z
                elif show_property == "RGB":
                    show_scalar_bar = False
                    show_property = None
                else:
                    if plot_entity.get_point_data_shape(show_property)[-1] == 3:
                        plot_rgb_option = True
                this_actor = self.plot_mesh(
                    uid=uid,
                    plot_entity=plot_entity,
                    color_RGB=color_RGB,
                    show_property=show_property,
                    show_scalar_bar=show_scalar_bar,
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
                """This check is needed to avoid errors when trying to plot an empty
                PolyData, just created at the beginning of a digitizing session."""
                if show_property is None:
                    show_scalar_bar = False
                    show_property_value = None
                    pass
                elif show_property == "none":
                    show_scalar_bar = False
                    show_property_value = None
                elif show_property == "X":
                    show_property_value = plot_entity.points_X
                elif show_property == "Y":
                    show_property_value = plot_entity.points_Y
                elif show_property == "Z":
                    show_property_value = plot_entity.points_Z
                elif show_property[-1] == "]":
                    """[Gabriele] we can identify multicomponents properties such as RGB[0] or Normals[0] by taking the last character of the property name ("]")."""
                    show_scalar_bar = True
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
                    """[Gabriele] Get the n of components for the given property. If it's > 1 then do stuff depending on the type of property (e.g. show_rgb_option -> True if the property is RGB)"""
                    if n_comp > 1:
                        show_property_value = plot_entity.get_point_data(show_property)
                        show_scalar_bar = False
                        # if show_property == 'RGB':
                        plot_rgb_option = True
                    else:
                        show_scalar_bar = True
                        show_property_value = plot_entity.get_point_data(show_property)
            this_actor = self.plot_PC_3D(
                uid=uid,
                plot_entity=new_plot,
                color_RGB=color_RGB,
                show_property=show_property_value,
                show_scalar_bar=show_scalar_bar,
                color_bar_range=None,
                show_property_title=show_property_title,
                plot_rgb_option=plot_rgb_option,
                visible=visible,
                point_size=point_size,
                opacity=opacity,
            )

        elif isinstance(plot_entity, (MapImage, XsImage)):
            """Do not plot directly image - it is much slower.
            Texture options according to type."""
            if show_property is None or show_property == "none":
                plot_texture_option = None
            else:
                plot_texture_option = plot_entity.texture
            this_actor = self.plot_mesh(
                uid=uid,
                plot_entity=plot_entity.frame,
                color_RGB=None,
                show_property=None,
                show_scalar_bar=None,
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
                """This  check is needed to avoid errors when trying to plot an empty
                PolyData, just created at the beginning of a digitizing session."""
                if show_property is None:
                    show_scalar_bar = False
                    pass
                elif show_property == "none":
                    show_scalar_bar = False
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
                    show_scalar_bar=show_scalar_bar,
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
                """This  check is needed to avoid errors when trying to plot an empty Voxet."""
                if show_property is None:
                    show_scalar_bar = False
                elif show_property == "none":
                    show_property = None
                    show_scalar_bar = False
                else:
                    if plot_entity.get_point_data_shape(show_property)[-1] == 3:
                        plot_rgb_option = True
                this_actor = self.plot_mesh(
                    uid=uid,
                    plot_entity=plot_entity,
                    color_RGB=None,
                    show_property=show_property,
                    show_scalar_bar=show_scalar_bar,
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
            if show_property is None:
                show_scalar_bar = False
                pass
            elif show_property == "none":
                show_scalar_bar = False
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
                show_scalar_bar=show_scalar_bar,
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

    """[Gabriele] Update the views depending on the sec_uid. We need to redefine the functions to use the sec_uid parameter for the update_dom_list_added func. We just need the x_added_x functions because the x_removed_x works on an already build/modified tree"""

    def geology_added_update_views(self, updated_list=None):
        """This is called when an entity is added to the geological collection.
        Disconnect signals to geology and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.GeologyTreeWidget.itemChanged.disconnect()
        self.TopologyTreeWidget.itemChanged.disconnect()
        """Create pandas dataframe as list of "new" actors"""
        actors_df_new = pd_DataFrame(
            columns=["uid", "actor", "show", "collection", "show_prop"]
        )
        for uid in updated_list:
            this_actor = self.show_actor_with_property(
                uid=uid, collection="geol_coll", show_property=None, visible=True
            )
            self.actors_df = self.actors_df.append(
                {
                    "uid": uid,
                    "actor": this_actor,
                    "show": True,
                    "collection": "geol_coll",
                    "show_prop": None,
                },
                ignore_index=True,
            )
            actors_df_new = actors_df_new.append(
                {
                    "uid": uid,
                    "actor": this_actor,
                    "show": True,
                    "collection": "geol_coll",
                    "show_prop": None,
                },
                ignore_index=True,
            )
            self.update_geology_tree_added(
                actors_df_new, sec_uid=self.this_x_section_uid
            )
            self.update_topology_tree_added(
                actors_df_new, sec_uid=self.this_x_section_uid
            )
        """Re-connect signals."""
        self.GeologyTreeWidget.itemChanged.connect(
            self.toggle_geology_topology_visibility
        )
        self.TopologyTreeWidget.itemChanged.connect(
            self.toggle_geology_topology_visibility
        )

    def mesh3d_added_update_views(self, updated_list=None):
        """This is called when a mesh3d is added to the mesh3d collection.
        Disconnect signals to mesh3d list, if they are set, then they are
        reconnected when the list is rebuilt"""
        self.Mesh3DTableWidget.itemChanged.disconnect()
        actors_df_new = pd_DataFrame(
            columns=["uid", "actor", "show", "collection", "show_prop"]
        )
        for uid in updated_list:
            this_actor = self.show_actor_with_property(
                uid=uid, collection="mesh3d_coll", show_property=None, visible=False
            )
            self.actors_df = self.actors_df.append(
                {
                    "uid": uid,
                    "actor": this_actor,
                    "show": False,
                    "collection": "mesh3d_coll",
                    "show_prop": None,
                },
                ignore_index=True,
            )
            actors_df_new = actors_df_new.append(
                {
                    "uid": uid,
                    "actor": this_actor,
                    "show": False,
                    "collection": "mesh3d_coll",
                    "show_prop": None,
                },
                ignore_index=True,
            )
            self.update_mesh3d_list_added(
                actors_df_new, sec_uid=self.this_x_section_uid
            )
        self.Mesh3DTableWidget.itemChanged.connect(self.toggle_mesh3d_visibility)

    def dom_added_update_views(self, updated_list=None):
        """This is called when a DOM is added to the xsect collection.
        Disconnect signals to dom list, if they are set, then they are
        reconnected when the list is rebuilt"""
        self.DOMsTableWidget.itemChanged.disconnect()
        actors_df_new = pd_DataFrame(
            columns=["uid", "actor", "show", "collection", "show_prop"]
        )
        for uid in updated_list:
            this_actor = self.show_actor_with_property(
                uid=uid, collection="dom_coll", show_property=None, visible=False
            )
            self.actors_df = self.actors_df.append(
                {
                    "uid": uid,
                    "actor": this_actor,
                    "show": False,
                    "collection": "dom_coll",
                    "show_prop": None,
                },
                ignore_index=True,
            )
            actors_df_new = actors_df_new.append(
                {
                    "uid": uid,
                    "actor": this_actor,
                    "show": False,
                    "collection": "dom_coll",
                    "show_prop": None,
                },
                ignore_index=True,
            )
            self.update_dom_list_added(actors_df_new, sec_uid=self.this_x_section_uid)
        """Re-connect signals."""
        self.DOMsTableWidget.itemChanged.connect(self.toggle_dom_visibility)

    def xsect_added_update_views(self, updated_list=None):
        """This is called when a cross-section is added to the xsect collection.
        Disconnect signals to xsect list, if they are set, then they are
        reconnected when the list is rebuilt"""
        self.XSectionTreeWidget.itemChanged.disconnect()
        actors_df_new = pd_DataFrame(
            columns=["uid", "actor", "show", "collection", "show_prop"]
        )
        for uid in updated_list:
            this_actor = self.show_actor_with_property(
                uid=uid, collection="xsect_coll", show_property=None, visible=True
            )
            self.actors_df = self.actors_df.append(
                {
                    "uid": uid,
                    "actor": this_actor,
                    "show": True,
                    "collection": "xsect_coll",
                    "show_prop": None,
                },
                ignore_index=True,
            )
            actors_df_new = actors_df_new.append(
                {
                    "uid": uid,
                    "actor": this_actor,
                    "show": True,
                    "collection": "xsect_coll",
                    "show_prop": None,
                },
                ignore_index=True,
            )
            self.update_xsections_tree_added(
                actors_df_new, sec_uid=self.this_x_section_uid
            )
        """Re-connect signals."""
        self.XSectionTreeWidget.itemChanged.connect(self.toggle_xsection_visibility)
