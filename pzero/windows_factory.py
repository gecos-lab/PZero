"""windows_factory.py
PZero© Andrea Bistacchi"""

"""QT imports"""
from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QCloseEvent,QFont

"""PZero imports"""
from .base_view_window_ui import Ui_BaseViewWindow
from .entities_factory import VertexSet, PolyLine, TriSurf, TetraSolid, XsVertexSet, XsPolyLine, DEM, PCDom, MapImage, Voxet, XsVoxet, Plane, Seismics, XsTriSurf, XsImage, PolyData, Wells, WellMarker,Attitude
from .helper_dialogs import input_one_value_dialog, input_text_dialog, input_combo_dialog, message_dialog, options_dialog, multiple_input_dialog, tic, toc,open_file_dialog
from .geological_collection import GeologicalCollection
from .dom_collection import DomCollection
from copy import deepcopy
from uuid import uuid4
from .helper_functions import angle_wrapper,PCA,best_fitting_plane

"""Maths imports"""
from math import degrees, sqrt, atan2
import numpy as np
import pandas as pd

""""VTK imports"""
""""VTK Numpy interface imports"""
# import vtk.numpy_interface.dataset_adapter as dsa
from vtk.util import numpy_support
from vtkmodules.vtkInteractionWidgets import vtkCameraOrientationWidget
from vtk import vtkAppendPolyData,vtkExtractPoints,vtkIdList,vtkStaticPointLocator,vtkThreshold,vtkSphere,vtkDataObject,vtkEuclideanClusterExtraction,vtkRadiusOutlierRemoval,vtkThresholdPoints


"""3D plotting imports"""
from pyvista import global_theme as pv_global_theme
from pyvistaqt import QtInteractor as pvQtInteractor
from pyvista import _vtk
from pyvista import read_texture
from pyvista import Disc as pvDisc
from pyvista import PolyData as pvPolyData
from pyvista import PointSet as pvPointSet
from pyvista.core.filters import _update_alg


"""2D plotting imports"""
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT  # this is customized in subclass NavigationToolbar a few lines below
# DO NOT USE import matplotlib.pyplot as plt  IT CREATES A DUPLICATE WINDOW IN NOTEBOOK
from matplotlib.figure import Figure
from matplotlib.offsetbox import TextArea, AnnotationBbox
from matplotlib.lines import Line2D
from matplotlib.image import AxesImage
from matplotlib.collections import PathCollection
from matplotlib.tri.tricontour import TriContourSet
import matplotlib.style as mplstyle
# from matplotlib.backend_bases import FigureCanvasBase
import mplstereonet

from uuid import UUID

"""Probably not-required imports"""
# import sys
# from time import sleep

mplstyle.use(['dark_background', 'fast'])
"""Background color for matplotlib plots.
Could be made interactive in the future.
'fast' is supposed to make plotting large objects faster"""



class NavigationToolbar(NavigationToolbar2QT):
    """Can customize NavigationToolbar2QT to display only the buttons we need.
    Note that toolitems is a class variable defined before __init__."""

    toolitems = [t for t in NavigationToolbar2QT.toolitems if t[0] in ('Home', 'Pan', 'Zoom', 'Save')]
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
        # MEMORY, BUT CREATES PROBLEMS WITH SIGNALS THAT ARE STILL ACTIVE
        # SEE DISCUSSIONS ON QPointer AND WA_DeleteOnClose ON THE INTERNET
        # self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.parent = parent

        """Connect actionQuit.triggered SIGNAL to self.close SLOT"""
        self.actionClose.triggered.connect(self.close)

        """Create empty Pandas dataframe with actor's with columns:
        uid = actor's uid -> the same as the original object's uid
        actor = the actor
        show = a boolean to show (True) or hide (false) the actor
        collection = the original collection of the actor, e.g. geol_coll, xsect_coll, etc."""
        self.actors_df = pd.DataFrame(columns=['uid', 'actor', 'show', 'collection'])

        """Create list of selected uid's."""
        self.selected_uids = []

        """Initialize menus and tools, canvas, add actors and show it. These methods must be defined in subclasses."""
        self.initialize_menu_tools()
        self.initialize_interactor()
        self.add_all_entities()
        self.show_qt_canvas()

        if not isinstance(self, ViewXsection):
            """Build and show geology and topology trees, and cross-section, DOM, image, lists.
            Reimplemented for ViewXsection with entities limited to those belonging to the Xsection."""
            self.create_geology_tree()
            self.create_topology_tree()
            self.create_xsections_tree()
            self.create_boundary_list()
            self.create_mesh3d_list()
            self.create_dom_list()
            self.create_image_list()
            self.create_well_tree()

        """Build and show other widgets, icons, tools - TO BE DONE_________________________________"""

        """Connect signals to update functions. Use lambda functions where we need to pass additional
        arguments such as parent in addition to the signal itself - the updated_list."""

        self.parent.geology_added_signal.connect(lambda updated_list: self.geology_added_update_views(updated_list=updated_list))
        self.parent.geology_removed_signal.connect(lambda updated_list: self.geology_removed_update_views(updated_list=updated_list))
        self.parent.geology_geom_modified_signal.connect(lambda updated_list: self.geology_geom_modified_update_views(updated_list=updated_list))
        self.parent.geology_data_keys_removed_signal.connect(lambda updated_list: self.geology_data_keys_modified_update_views(updated_list=updated_list))
        self.parent.geology_data_val_modified_signal.connect(lambda updated_list: self.geology_data_val_modified_update_views(updated_list=updated_list))
        self.parent.geology_metadata_modified_signal.connect(lambda updated_list: self.geology_metadata_modified_update_views(updated_list=updated_list))
        self.parent.geology_legend_color_modified_signal.connect(lambda updated_list: self.geology_legend_color_modified_update_views(updated_list=updated_list))
        self.parent.geology_legend_thick_modified_signal.connect(lambda updated_list: self.geology_legend_thick_modified_update_views(updated_list=updated_list))

        self.parent.xsect_added_signal.connect(lambda updated_list: self.xsect_added_update_views(updated_list=updated_list))
        self.parent.xsect_removed_signal.connect(lambda updated_list: self.xsect_removed_update_views(updated_list=updated_list))
        self.parent.xsect_geom_modified_signal.connect(lambda updated_list: self.xsect_geom_modified_update_views(updated_list=updated_list))
        self.parent.xsect_metadata_modified_signal.connect(lambda updated_list: self.xsect_metadata_modified_update_views(updated_list=updated_list))
        self.parent.xsect_legend_color_modified_signal.connect(lambda updated_list: self.xsect_legend_color_modified_update_views(updated_list=updated_list))
        self.parent.xsect_legend_thick_modified_signal.connect(lambda updated_list: self.xsect_legend_thick_modified_update_views(updated_list=updated_list))

        self.parent.boundary_added_signal.connect(lambda updated_list: self.boundary_added_update_views(updated_list=updated_list))
        self.parent.boundary_removed_signal.connect(lambda updated_list: self.boundary_removed_update_views(updated_list=updated_list))
        self.parent.boundary_geom_modified_signal.connect(lambda updated_list: self.boundary_geom_modified_update_views(updated_list=updated_list))
        self.parent.boundary_metadata_modified_signal.connect(lambda updated_list: self.boundary_metadata_modified_update_views(updated_list=updated_list))
        self.parent.boundary_legend_color_modified_signal.connect(lambda updated_list: self.boundary_legend_color_modified_update_views(updated_list=updated_list))
        self.parent.boundary_legend_thick_modified_signal.connect(lambda updated_list: self.boundary_legend_thick_modified_update_views(updated_list=updated_list))

        self.parent.mesh3d_added_signal.connect(lambda updated_list: self.mesh3d_added_update_views(updated_list=updated_list))
        self.parent.mesh3d_removed_signal.connect(lambda updated_list: self.mesh3d_removed_update_views(updated_list=updated_list))
        self.parent.mesh3d_data_keys_removed_signal.connect(lambda updated_list: self.mesh3d_data_keys_modified_update_views(updated_list=updated_list))
        self.parent.mesh3d_data_val_modified_signal.connect(lambda updated_list: self.mesh3d_data_val_modified_update_views(updated_list=updated_list))
        self.parent.mesh3d_metadata_modified_signal.connect(lambda updated_list: self.mesh3d_metadata_modified_update_views(updated_list=updated_list))
        self.parent.mesh3d_legend_color_modified_signal.connect(lambda updated_list: self.mesh3d_legend_color_modified_update_views(updated_list=updated_list))
        self.parent.mesh3d_legend_thick_modified_signal.connect(lambda updated_list: self.mesh3d_legend_thick_modified_update_views(updated_list=updated_list))

        self.parent.dom_added_signal.connect(lambda updated_list: self.dom_added_update_views(updated_list=updated_list))
        self.parent.dom_removed_signal.connect(lambda updated_list: self.dom_removed_update_views(updated_list=updated_list))
        self.parent.dom_data_keys_removed_signal.connect(lambda updated_list: self.dom_data_keys_modified_update_views(updated_list=updated_list))
        self.parent.dom_data_val_modified_signal.connect(lambda updated_list: self.dom_data_val_modified_update_views(updated_list=updated_list))
        self.parent.dom_metadata_modified_signal.connect(lambda updated_list: self.dom_metadata_modified_update_views(updated_list=updated_list))
        self.parent.dom_legend_color_modified_signal.connect(lambda updated_list: self.dom_legend_color_modified_update_views(updated_list=updated_list))
        self.parent.dom_legend_thick_modified_signal.connect(lambda updated_list: self.dom_legend_thick_modified_update_views(updated_list=updated_list))

        self.parent.image_added_signal.connect(lambda updated_list: self.image_added_update_views(updated_list=updated_list))
        self.parent.image_removed_signal.connect(lambda updated_list: self.image_removed_update_views(updated_list=updated_list))
        self.parent.image_metadata_modified_signal.connect(lambda updated_list: self.image_metadata_modified_update_views(updated_list=updated_list))

        self.parent.well_added_signal.connect(lambda updated_list: self.well_added_update_views(updated_list=updated_list))
        self.parent.well_removed_signal.connect(lambda updated_list: self.well_removed_update_views(updated_list=updated_list))
        self.parent.well_data_keys_removed_signal.connect(lambda updated_list: self.well_data_keys_modified_update_views(updated_list=updated_list))
        self.parent.well_data_val_modified_signal.connect(lambda updated_list: self.well_data_val_modified_update_views(updated_list=updated_list))
        self.parent.well_metadata_modified_signal.connect(lambda updated_list: self.well_metadata_modified_update_views(updated_list=updated_list))
        self.parent.well_legend_color_modified_signal.connect(lambda updated_list: self.well_legend_color_modified_update_views(updated_list=updated_list))
        self.parent.well_legend_thick_modified_signal.connect(lambda updated_list: self.well_legend_thick_modified_update_views(updated_list=updated_list))

        self.parent.prop_legend_cmap_modified_signal.connect(lambda this_property: self.prop_legend_cmap_modified_update_views(this_property=this_property))

    def show_qt_canvas(self):
        """Show the Qt Window"""
        self.show()
        if isinstance(self, View3D):
            """Turn on the orientation widget AFTER the canvas is shown."""
            self.cam_orient_widget.On()

    """Methods used to build and update the geology and topology trees."""

    def create_geology_tree(self, sec_uid=None):
        """Create geology tree with checkboxes and properties"""
        self.GeologyTreeWidget.clear()
        self.GeologyTreeWidget.setColumnCount(3)
        self.GeologyTreeWidget.setHeaderLabels(['Type > Feature > Scenario > Name', 'uid', 'property'])
        self.GeologyTreeWidget.hideColumn(1)  # hide the uid column
        self.GeologyTreeWidget.setItemsExpandable(True)
        if sec_uid:
            geo_types = pd.unique(self.parent.geol_coll.df.loc[(self.parent.geol_coll.df['x_section'] == sec_uid), 'geological_type'])
        else:
            geo_types = pd.unique(self.parent.geol_coll.df['geological_type'])
        for geo_type in geo_types:
            glevel_1 = QTreeWidgetItem(self.GeologyTreeWidget, [geo_type])  # self.GeologyTreeWidget as parent -> top level
            glevel_1.setFlags(glevel_1.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable)
            if sec_uid:
                geo_features = pd.unique(self.parent.geol_coll.df.loc[(self.parent.geol_coll.df['geological_type'] == geo_type) & (self.parent.geol_coll.df['x_section'] == sec_uid), 'geological_feature'])
            else:
                geo_features = pd.unique(self.parent.geol_coll.df.loc[self.parent.geol_coll.df['geological_type'] == geo_type, 'geological_feature'])
            for feature in geo_features:
                glevel_2 = QTreeWidgetItem(glevel_1, [feature])  # glevel_1 as parent -> 1st middle level
                glevel_2.setFlags(glevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable)
                if sec_uid:
                    geo_scenario = pd.unique(self.parent.geol_coll.df.loc[(self.parent.geol_coll.df['geological_type'] == geo_type) & (self.parent.geol_coll.df['geological_feature'] == feature) & (self.parent.geol_coll.df['x_section'] == sec_uid), 'scenario'])
                else:
                    geo_scenario = pd.unique(self.parent.geol_coll.df.loc[(self.parent.geol_coll.df['geological_type'] == geo_type) & (self.parent.geol_coll.df['geological_feature'] == feature),'scenario'])
                for scenario in geo_scenario:
                    glevel_3 = QTreeWidgetItem(glevel_2, [scenario])  # glevel_2 as parent -> 2nd middle level
                    glevel_3.setFlags(glevel_3.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable)
                    if sec_uid:
                        uids = self.parent.geol_coll.df.loc[(self.parent.geol_coll.df['geological_type'] == geo_type) & (self.parent.geol_coll.df['geological_feature'] == feature) & (self.parent.geol_coll.df['scenario'] == scenario) & (self.parent.geol_coll.df['x_section'] == sec_uid), 'uid'].to_list()
                    else:
                        uids= self.parent.geol_coll.df.loc[(self.parent.geol_coll.df['geological_type'] == geo_type) & (self.parent.geol_coll.df['geological_feature'] == feature) & (self.parent.geol_coll.df['scenario'] == scenario), 'uid'].to_list()
                    for uid in uids:
                        property_combo = QComboBox()
                        property_combo.uid = uid
                        property_combo.addItem("none")
                        property_combo.addItem("X")
                        property_combo.addItem("Y")
                        property_combo.addItem("Z")
                        for prop in self.parent.geol_coll.get_uid_properties_names(uid):
                            property_combo.addItem(prop)
                        name = self.parent.geol_coll.df.loc[(self.parent.geol_coll.df['uid'] == uid), 'name'].values[0]
                        glevel_4 = QTreeWidgetItem(glevel_3, [name, uid])  # glevel_3 as parent -> lower level
                        self.GeologyTreeWidget.setItemWidget(glevel_4, 2, property_combo)
                        property_combo.currentIndexChanged.connect(lambda: self.toggle_property())
                        glevel_4.setFlags(glevel_4.flags() | Qt.ItemIsUserCheckable)
                        if self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                            glevel_4.setCheckState(0, Qt.Checked)
                        elif not self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                            glevel_4.setCheckState(0, Qt.Unchecked)
        """Send messages. Note that with tristate several signals are emitted in a sequence, one for each
        changed item, but upper levels do not broadcast uid's so they are filtered in the toggle method."""
        self.GeologyTreeWidget.itemChanged.connect(self.toggle_geology_topology_visibility)
        self.GeologyTreeWidget.expandAll()

    def create_topology_tree(self,sec_uid=None):
        """Create topology tree with checkboxes and properties"""
        self.TopologyTreeWidget.clear()
        self.TopologyTreeWidget.setColumnCount(3)
        self.TopologyTreeWidget.setHeaderLabels(['Type > Scenario > Name', 'uid', 'property'])
        self.TopologyTreeWidget.hideColumn(1)  # hide the uid column
        self.TopologyTreeWidget.setItemsExpandable(True)

        if sec_uid:
            filtered_topo = self.parent.geol_coll.df.loc[(self.parent.geol_coll.df['x_section'] == sec_uid), 'topological_type']
            topo_types = pd.unique(filtered_topo)
        else:
            topo_types = pd.unique(self.parent.geol_coll.df['topological_type'])

        for topo_type in topo_types:
            tlevel_1 = QTreeWidgetItem(self.TopologyTreeWidget, [topo_type])  # self.GeologyTreeWidget as parent -> top level
            tlevel_1.setFlags(tlevel_1.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable)
            for scenario in pd.unique(self.parent.geol_coll.df.loc[self.parent.geol_coll.df['topological_type'] == topo_type, 'scenario']):
                tlevel_2 = QTreeWidgetItem(tlevel_1, [scenario])  # tlevel_1 as parent -> middle level
                tlevel_2.setFlags(tlevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable)
                if sec_uid:
                    uids = self.parent.geol_coll.df.loc[(self.parent.geol_coll.df['topological_type'] == topo_type) & (self.parent.geol_coll.df['scenario'] == scenario) & (self.parent.geol_coll.df['x_section'] == sec_uid), 'uid'].to_list()
                else:
                    uids = self.parent.geol_coll.df.loc[(self.parent.geol_coll.df['topological_type'] == topo_type) & (self.parent.geol_coll.df['scenario'] == scenario), 'uid'].to_list()
                for uid in uids:
                    property_combo = QComboBox()
                    property_combo.uid = uid
                    property_combo.addItem("none")
                    property_combo.addItem("X")
                    property_combo.addItem("Y")
                    property_combo.addItem("Z")
                    for prop in self.parent.geol_coll.get_uid_properties_names(uid):
                        property_combo.addItem(prop)
                    name = self.parent.geol_coll.df.loc[self.parent.geol_coll.df['uid'] == uid, 'name'].values[0]
                    tlevel_3 = QTreeWidgetItem(tlevel_2, [name, uid])  # tlevel_2 as parent -> lower level
                    self.TopologyTreeWidget.setItemWidget(tlevel_3, 2, property_combo)
                    property_combo.currentIndexChanged.connect(lambda: self.toggle_property())
                    tlevel_3.setFlags(tlevel_3.flags() | Qt.ItemIsUserCheckable)
                    if self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                        tlevel_3.setCheckState(0, Qt.Checked)
                    elif not self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                        tlevel_3.setCheckState(0, Qt.Unchecked)
        """Send messages. Note that with tristate several signals are emitted in a sequence, one for each
        changed item, but upper levels do not broadcast uid's so they are filtered in the toggle method."""
        self.TopologyTreeWidget.itemChanged.connect(self.toggle_geology_topology_visibility)
        self.TopologyTreeWidget.expandAll()

    def update_geology_tree_added(self, new_list=None,sec_uid=None):
        """Update geology tree without creating a new model"""
        uid_list = list(new_list['uid'])
        if sec_uid:
            for i,uid in enumerate(new_list['uid']):
                if sec_uid != self.parent.geol_coll.df.loc[self.parent.geol_coll.df['uid'] == uid, 'x_section'].values[0]:
                    del uid_list[i]
        for uid in uid_list:
            if self.GeologyTreeWidget.findItems(self.parent.geol_coll.get_uid_geological_type(uid), Qt.MatchExactly, 0) != []:
                """Already exists a TreeItem (1 level) for the geological type"""
                counter_1 = 0
                for child_1 in range(self.GeologyTreeWidget.findItems(self.parent.geol_coll.get_uid_geological_type(uid), Qt.MatchExactly, 0)[0].childCount()):
                    """for cycle that loops n times as the number of subItems in the specific geological type branch"""
                    if self.GeologyTreeWidget.findItems(self.parent.geol_coll.get_uid_geological_type(uid), Qt.MatchExactly, 0)[0].child(child_1).text(0) == self.parent.geol_coll.get_uid_geological_feature(uid):
                        counter_1 += 1
                if counter_1 != 0:
                    for child_1 in range(self.GeologyTreeWidget.findItems(self.parent.geol_coll.get_uid_geological_type(uid), Qt.MatchExactly, 0)[0].childCount()):
                        if self.GeologyTreeWidget.findItems(self.parent.geol_coll.get_uid_geological_type(uid), Qt.MatchExactly, 0)[0].child(child_1).text(0) == self.parent.geol_coll.get_uid_geological_feature(uid):
                            """Already exists a TreeItem (2 level) for the geological feature"""
                            counter_2 = 0
                            for child_2 in range(self.GeologyTreeWidget.itemBelow(self.GeologyTreeWidget.findItems(self.parent.geol_coll.get_uid_geological_type(uid), Qt.MatchExactly, 0)[0]).childCount()):
                                """for cycle that loops n times as the number of sub-subItems in the specific geological type and geological feature branch"""
                                if self.GeologyTreeWidget.itemBelow(self.GeologyTreeWidget.findItems(self.parent.geol_coll.get_uid_geological_type(uid), Qt.MatchExactly, 0)[0]).child(child_2).text(0) == self.parent.geol_coll.get_uid_scenario(uid):
                                    counter_2 += 1
                            if counter_2 != 0:
                                for child_2 in range(self.GeologyTreeWidget.itemBelow(self.GeologyTreeWidget.findItems(self.parent.geol_coll.get_uid_geological_type(uid),Qt.MatchExactly, 0)[0]).childCount()):
                                    if self.GeologyTreeWidget.itemBelow(self.GeologyTreeWidget.findItems(self.parent.geol_coll.get_uid_geological_type(uid), Qt.MatchExactly, 0)[0]).child(child_2).text(0) == self.parent.geol_coll.get_uid_scenario(uid):
                                        """Same geological type, geological feature and scenario"""
                                        property_combo = QComboBox()
                                        property_combo.uid = uid
                                        property_combo.addItem("none")
                                        property_combo.addItem("X")
                                        property_combo.addItem("Y")
                                        property_combo.addItem("Z")
                                        for prop in self.parent.geol_coll.get_uid_properties_names(uid):
                                            property_combo.addItem(prop)
                                        name = self.parent.geol_coll.get_uid_name(uid)
                                        glevel_4 = QTreeWidgetItem(self.GeologyTreeWidget.findItems(self.parent.geol_coll.get_uid_geological_type(uid), Qt.MatchExactly, 0)[0].child(child_1).child(child_2), [name, uid])
                                        self.GeologyTreeWidget.setItemWidget(glevel_4, 2, property_combo)
                                        property_combo.currentIndexChanged.connect(lambda: self.toggle_property())
                                        glevel_4.setFlags(glevel_4.flags() | Qt.ItemIsUserCheckable)
                                        if self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                                            glevel_4.setCheckState(0, Qt.Checked)
                                        elif not self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                                            glevel_4.setCheckState(0, Qt.Unchecked)
                                        self.GeologyTreeWidget.insertTopLevelItem(0, glevel_4)
                                        break
                            else:
                                """Same geological type and geological feature, different scenario"""
                                glevel_3 = QTreeWidgetItem(self.GeologyTreeWidget.findItems(self.parent.geol_coll.get_uid_geological_type(uid), Qt.MatchExactly, 0)[0].child(child_1), [self.parent.geol_coll.get_uid_scenario(uid)])
                                glevel_3.setFlags(glevel_3.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable)
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
                                property_combo.currentIndexChanged.connect(lambda: self.toggle_property())
                                glevel_4.setFlags(glevel_4.flags() | Qt.ItemIsUserCheckable)
                                if self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                                    glevel_4.setCheckState(0, Qt.Checked)
                                elif not self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                                    glevel_4.setCheckState(0, Qt.Unchecked)
                                self.GeologyTreeWidget.insertTopLevelItem(0, glevel_4)
                                break
                else:
                    """Same geological type, different geological feature and scenario"""
                    glevel_2 = QTreeWidgetItem(self.GeologyTreeWidget.findItems(self.parent.geol_coll.get_uid_geological_type(uid), Qt.MatchExactly, 0)[0], [self.parent.geol_coll.get_uid_geological_feature(uid)])
                    glevel_2.setFlags(glevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable)
                    self.GeologyTreeWidget.insertTopLevelItem(0, glevel_2)
                    glevel_3 = QTreeWidgetItem(glevel_2, [self.parent.geol_coll.get_uid_scenario(uid)])
                    glevel_3.setFlags(glevel_3.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable)
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
                    property_combo.currentIndexChanged.connect(lambda: self.toggle_property())
                    glevel_4.setFlags(glevel_4.flags() | Qt.ItemIsUserCheckable)
                    if self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                        glevel_4.setCheckState(0, Qt.Checked)
                    elif not self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                        glevel_4.setCheckState(0, Qt.Unchecked)
                    self.GeologyTreeWidget.insertTopLevelItem(0, glevel_4)
                    break
            else:
                """Different geological type, geological feature and scenario"""
                glevel_1 = QTreeWidgetItem(self.GeologyTreeWidget, [self.parent.geol_coll.get_uid_geological_type(uid)])
                glevel_1.setFlags(glevel_1.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable)
                self.GeologyTreeWidget.insertTopLevelItem(0, glevel_1)
                glevel_2 = QTreeWidgetItem(glevel_1, [self.parent.geol_coll.get_uid_geological_feature(uid)])
                glevel_2.setFlags(glevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable)
                self.GeologyTreeWidget.insertTopLevelItem(0, glevel_2)
                glevel_3 = QTreeWidgetItem(glevel_2, [self.parent.geol_coll.get_uid_scenario(uid)])
                glevel_3.setFlags(glevel_3.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable)
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
                property_combo.currentIndexChanged.connect(lambda: self.toggle_property())
                glevel_4.setFlags(glevel_4.flags() | Qt.ItemIsUserCheckable)
                if self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                    glevel_4.setCheckState(0, Qt.Checked)
                elif not self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                    glevel_4.setCheckState(0, Qt.Unchecked)
                self.GeologyTreeWidget.insertTopLevelItem(0, glevel_4)
                break
        self.GeologyTreeWidget.itemChanged.connect(self.toggle_geology_topology_visibility)
        self.GeologyTreeWidget.expandAll()

    def update_geology_tree_removed(self, removed_list=None): # second attempt
        """When geological entity is removed, update Geology Tree without building a new model"""
        success = 0
        for uid in removed_list:
            for top_geo_type in range(self.GeologyTreeWidget.topLevelItemCount()):
                """Iterate through every Geological Type top level"""
                for child_geo_feat in range(self.GeologyTreeWidget.topLevelItem(top_geo_type).childCount()):
                    """Iterate through every Geological Feature child"""
                    for child_scenario in range(self.GeologyTreeWidget.topLevelItem(top_geo_type).child(child_geo_feat).childCount()):
                        """Iterate through every Scenario child"""
                        for child_entity in range(self.GeologyTreeWidget.topLevelItem(top_geo_type).child(child_geo_feat).child(child_scenario).childCount()):
                            """Iterate through every Entity child"""
                            if self.GeologyTreeWidget.topLevelItem(top_geo_type).child(child_geo_feat).child(child_scenario).child(child_entity).text(1) == uid:
                                """Complete check: entity found has the uid of the entity we need to remove. Delete child, then ensure no Child or Top Level remain empty"""
                                success = 1
                                self.GeologyTreeWidget.topLevelItem(top_geo_type).child(child_geo_feat).child(child_scenario).removeChild(self.GeologyTreeWidget.topLevelItem(top_geo_type).child(child_geo_feat).child(child_scenario).child(child_entity))
                                if self.GeologyTreeWidget.topLevelItem(top_geo_type).child(child_geo_feat).child(child_scenario).childCount() == 0:
                                    self.GeologyTreeWidget.topLevelItem(top_geo_type).child(child_geo_feat).removeChild(self.GeologyTreeWidget.topLevelItem(top_geo_type).child(child_geo_feat).child(child_scenario))
                                    if self.GeologyTreeWidget.topLevelItem(top_geo_type).child(child_geo_feat).childCount() == 0:
                                        self.GeologyTreeWidget.topLevelItem(top_geo_type).removeChild(self.GeologyTreeWidget.topLevelItem(top_geo_type).child(child_geo_feat))
                                        if self.GeologyTreeWidget.topLevelItem(top_geo_type).childCount() == 0:
                                            self.GeologyTreeWidget.takeTopLevelItem(top_geo_type)
                                break
                        if success == 1:
                            break
                    if success == 1:
                        break
                if success == 1:
                    break

    def update_topology_tree_added(self, new_list=None,sec_uid=None):
        """Update topology tree without creating a new model"""
        uid_list = list(new_list['uid'])
        if sec_uid:
            for i,uid in enumerate(new_list['uid']):
                if sec_uid != self.parent.geol_coll.df.loc[self.parent.geol_coll.df['uid'] == uid, 'x_section'].values[0]:
                    del uid_list[i]
        for uid in uid_list:
            if self.TopologyTreeWidget.findItems(self.parent.geol_coll.get_uid_topological_type(uid), Qt.MatchExactly, 0) != []:
                """Already exists a TreeItem (1 level) for the topological type"""
                counter_1 = 0
                for child_1 in range(self.TopologyTreeWidget.findItems(self.parent.geol_coll.get_uid_topological_type(uid), Qt.MatchExactly, 0)[0].childCount()):
                    """for cycle that loops n times as the number of subItems in the specific topological type branch"""
                    if self.TopologyTreeWidget.findItems(self.parent.geol_coll.get_uid_topological_type(uid), Qt.MatchExactly, 0)[0].child(child_1).text(0) == self.parent.geol_coll.get_uid_scenario(uid):
                        counter_1 += 1
                if counter_1 != 0:
                    for child_1 in range(self.TopologyTreeWidget.findItems(self.parent.geol_coll.get_uid_topological_type(uid), Qt.MatchExactly, 0)[0].childCount()):
                        if self.TopologyTreeWidget.findItems(self.parent.geol_coll.get_uid_topological_type(uid), Qt.MatchExactly, 0)[0].child(child_1).text(0) == self.parent.geol_coll.get_uid_scenario(uid):
                            """Same topological type and scenario"""
                            property_combo = QComboBox()
                            property_combo.uid = uid
                            property_combo.addItem("none")
                            property_combo.addItem("X")
                            property_combo.addItem("Y")
                            property_combo.addItem("Z")
                            for prop in self.parent.geol_coll.get_uid_properties_names(uid):
                                property_combo.addItem(prop)
                            name = self.parent.geol_coll.get_uid_name(uid)
                            tlevel_3 = QTreeWidgetItem(self.TopologyTreeWidget.findItems(self.parent.geol_coll.get_uid_topological_type(uid), Qt.MatchExactly, 0)[0].child(child_1), [name, uid])
                            self.TopologyTreeWidget.setItemWidget(tlevel_3, 2, property_combo)
                            property_combo.currentIndexChanged.connect(lambda: self.toggle_property())
                            tlevel_3.setFlags(tlevel_3.flags() | Qt.ItemIsUserCheckable)
                            if self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                                tlevel_3.setCheckState(0, Qt.Checked)
                            elif not self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                                tlevel_3.setCheckState(0, Qt.Unchecked)
                            self.TopologyTreeWidget.insertTopLevelItem(0, tlevel_3)
                            break
                else:
                    """Same topological type, different scenario"""
                    tlevel_2 = QTreeWidgetItem(self.TopologyTreeWidget.findItems(self.parent.geol_coll.get_uid_topological_type(uid), Qt.MatchExactly, 0)[0], [self.parent.geol_coll.get_uid_scenario(uid)])
                    tlevel_2.setFlags(tlevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable)
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
                    property_combo.currentIndexChanged.connect(lambda: self.toggle_property())
                    tlevel_3.setFlags(tlevel_3.flags() | Qt.ItemIsUserCheckable)
                    if self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                        tlevel_3.setCheckState(0, Qt.Checked)
                    elif not self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                        tlevel_3.setCheckState(0, Qt.Unchecked)
                    self.TopologyTreeWidget.insertTopLevelItem(0, tlevel_3)
                    break
            else:
                """Different topological type and scenario"""
                tlevel_1 = QTreeWidgetItem(self.TopologyTreeWidget, [self.parent.geol_coll.get_uid_topological_type(uid)])
                tlevel_1.setFlags(tlevel_1.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable)
                self.TopologyTreeWidget.insertTopLevelItem(0, tlevel_1)
                tlevel_2 = QTreeWidgetItem(tlevel_1, [self.parent.geol_coll.get_uid_scenario(uid)])
                tlevel_2.setFlags(tlevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable)
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
                property_combo.currentIndexChanged.connect(lambda: self.toggle_property())
                tlevel_3.setFlags(tlevel_3.flags() | Qt.ItemIsUserCheckable)
                if self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                    tlevel_3.setCheckState(0, Qt.Checked)
                elif not self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                    tlevel_3.setCheckState(0, Qt.Unchecked)
                self.TopologyTreeWidget.insertTopLevelItem(0, tlevel_3)
                break
        self.TopologyTreeWidget.itemChanged.connect(self.toggle_geology_topology_visibility)
        self.TopologyTreeWidget.expandAll()

    def update_topology_tree_removed(self, removed_list=None):
        """When geological entity is removed, update Topology Tree without building a new model"""
        success = 0
        for uid in removed_list:
            for top_topo_type in range(self.TopologyTreeWidget.topLevelItemCount()):
                """Iterate through every Topological Type top level"""
                for child_scenario in range(self.TopologyTreeWidget.topLevelItem(top_topo_type).childCount()):
                    """Iterate through every Scenario child"""
                    for child_entity in range(self.TopologyTreeWidget.topLevelItem(top_topo_type).child(child_scenario).childCount()):
                        """Iterate through every Entity child"""
                        if self.TopologyTreeWidget.topLevelItem(top_topo_type).child(child_scenario).child(child_entity).text(1) == uid:
                            """Complete check: entity found has the uid of the entity we need to remove. Delete child, then ensure no Child or Top Level remain empty"""
                            success = 1
                            self.TopologyTreeWidget.topLevelItem(top_topo_type).child(child_scenario).removeChild(self.TopologyTreeWidget.topLevelItem(top_topo_type).child(child_scenario).child(child_entity))
                            if self.TopologyTreeWidget.topLevelItem(top_topo_type).child(child_scenario).childCount() == 0:
                                self.TopologyTreeWidget.topLevelItem(top_topo_type).removeChild(self.TopologyTreeWidget.topLevelItem(top_topo_type).child(child_scenario))
                                if self.TopologyTreeWidget.topLevelItem(top_topo_type).childCount() == 0:
                                    self.TopologyTreeWidget.takeTopLevelItem(top_topo_type)
                            break
                    if success == 1:
                        break
                if success == 1:
                    break

    def update_geology_checkboxes(self, uid=None, uid_checkState=None):
        """Update checkboxes in geology tree, called when state changed in topology tree."""
        item = self.GeologyTreeWidget.findItems(uid, Qt.MatchFixedString | Qt.MatchRecursive, 1)[0]
        if uid_checkState == Qt.Checked:
            item.setCheckState(0, Qt.Checked)
        elif uid_checkState == Qt.Unchecked:
            item.setCheckState(0, Qt.Unchecked)

    def update_topology_checkboxes(self, uid=None, uid_checkState=None):
        """Update checkboxes in topology tree, called when state changed in geology tree."""
        item = self.TopologyTreeWidget.findItems(uid, Qt.MatchFixedString | Qt.MatchRecursive, 1)[0]
        if uid_checkState == Qt.Checked:
            item.setCheckState(0, Qt.Checked)
        elif uid_checkState == Qt.Unchecked:
            item.setCheckState(0, Qt.Unchecked)

    def toggle_geology_topology_visibility(self, item, column):
        """Called by self.GeologyTreeWidget.itemChanged.connect(self.toggle_geology_topology_visibility) and self.TopologyTreeWidget.itemChanged.connect(self.toggle_geology_topology_visibility)"""
        name = item.text(0)  # not used
        uid = item.text(1)
        uid_checkState = item.checkState(0)
        if uid:  # needed to skip messages from upper levels of tree that do not broadcast uid's
            if uid_checkState == Qt.Checked:
                if not self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                    self.actors_df.loc[self.actors_df['uid'] == uid, 'show'] = True
                    self.set_actor_visible(uid=uid, visible=True)
            elif uid_checkState == Qt.Unchecked:
                if self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                    self.actors_df.loc[self.actors_df['uid'] == uid, 'show'] = False
                    self.set_actor_visible(uid=uid, visible=False)
            """Before updating checkboxes, disconnect signals to geology and topology tree, if they are set,
            to avoid a nasty loop that disrupts the trees, then reconnect them (it is also possible that
            they are automatically reconnected whe the trees are rebuilt."""
            self.GeologyTreeWidget.itemChanged.disconnect()
            self.TopologyTreeWidget.itemChanged.disconnect()
            self.update_geology_checkboxes(uid=uid, uid_checkState=uid_checkState)
            self.update_topology_checkboxes(uid=uid, uid_checkState=uid_checkState)
            self.GeologyTreeWidget.itemChanged.connect(self.toggle_geology_topology_visibility)
            self.TopologyTreeWidget.itemChanged.connect(self.toggle_geology_topology_visibility)

    def toggle_property(self):
        """Generic method to toggle the property shown by an actor that is already present in the view."""
        combo = self.sender()
        show_property = combo.currentText()
        uid = combo.uid
        show = self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]
        collection = self.actors_df.loc[self.actors_df['uid'] == uid, 'collection'].values[0]
        """This removes the previous copy of the actor with the same uid, then calls the viewer-specific function that shows an actor with a property.
        IN THE FUTURE see if it is possible and more efficient to keep the actor and just change the property shown."""
        self.remove_actor_in_view(uid=uid)
        this_actor = self.show_actor_with_property(uid=uid, collection=collection, show_property=show_property, visible=show)
        self.actors_df = self.actors_df.append({'uid': uid, 'actor': this_actor, 'show': show, 'collection': collection, 'show_prop': show_property}, ignore_index=True) # self.set_actor_visible(uid=uid, visible=show)

    """Methods used to build and update the cross-section table."""

    def create_xsections_tree(self, sec_uid=None):
        """Create XSection tree with checkboxes and properties"""
        self.XSectionTreeWidget.clear()
        self.XSectionTreeWidget.setColumnCount(2)
        self.XSectionTreeWidget.setHeaderLabels(['Name', 'uid'])
        self.XSectionTreeWidget.hideColumn(1)  # hide the uid column
        self.XSectionTreeWidget.setItemsExpandable(True)
        name_xslevel1 = ["All XSections"]
        xslevel_1 = QTreeWidgetItem(self.XSectionTreeWidget, name_xslevel1)  # self.XSectionTreeWidget as parent -> top level
        xslevel_1.setFlags(xslevel_1.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable)
        if sec_uid:
            uids = self.parent.xsect_coll.df.loc[self.parent.xsect_coll.df['uid'] == sec_uid, 'uid'].to_list()
        else:
            uids = self.parent.xsect_coll.df['uid'].to_list()
        for uid in uids:
            name = self.parent.xsect_coll.df.loc[self.parent.xsect_coll.df['uid'] == uid, 'name'].values[0]
            xslevel_2 = QTreeWidgetItem(xslevel_1, [name, uid])  # xslevel_2 as parent -> lower level
            xslevel_2.setFlags(xslevel_2.flags() | Qt.ItemIsUserCheckable)
            if self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                xslevel_2.setCheckState(0, Qt.Checked)
            elif not self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                xslevel_2.setCheckState(0, Qt.Unchecked)
        """Send messages. Note that with tristate several signals are emitted in a sequence, one for each
        changed item, but upper levels do not broadcast uid's so they are filtered in the toggle method."""
        self.XSectionTreeWidget.itemChanged.connect(self.toggle_xsection_visibility)
        self.XSectionTreeWidget.expandAll()

    def update_xsections_tree_added(self, new_list=None,sec_uid=None):
        """Update XSection tree without creating a new model"""
        uid_list = list(new_list['uid'])
        if sec_uid:
            for i,uid in enumerate(new_list['uid']):
                if sec_uid != uid:
                    del uid_list[i]
        for uid in uid_list:
            name = self.parent.xsect_coll.get_uid_name(uid)
            xslevel_2 = QTreeWidgetItem(self.XSectionTreeWidget.findItems("All XSections", Qt.MatchExactly, 0)[0], [name, uid])
            xslevel_2.setFlags(xslevel_2.flags() | Qt.ItemIsUserCheckable)
            if self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                xslevel_2.setCheckState(0, Qt.Checked)
            elif not self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                xslevel_2.setCheckState(0, Qt.Unchecked)
        self.XSectionTreeWidget.itemChanged.connect(self.toggle_xsection_visibility)
        self.XSectionTreeWidget.expandAll()

    def update_xsections_tree_removed(self, removed_list=None):
        """Update XSection tree without creating a new model"""
        success = 0
        for uid in removed_list:
            for top_box in range(self.XSectionTreeWidget.topLevelItemCount()):
                """Iterate through every Collection top level"""
                for child_xsect in range(self.XSectionTreeWidget.topLevelItem(top_box).childCount()):
                    """Iterate through every XSection"""
                    if self.XSectionTreeWidget.topLevelItem(top_box).child(child_xsect).text(1) == uid:
                        """Complete check: entity found has the uid of the entity we need to remove. Delete child"""
                        success = 1
                        self.XSectionTreeWidget.topLevelItem(top_box).removeChild(self.XSectionTreeWidget.topLevelItem(top_box).child(child_xsect))
                        break
                if success == 1:
                    break

    def update_xsection_checkboxes(self, uid=None, uid_checkState=None):
        """Update checkboxes in XSection tree, called when state changed in xsection tree."""
        item = self.XSectionTreeWidget.findItems(uid, Qt.MatchFixedString | Qt.MatchRecursive, 1)[0]
        if uid_checkState == Qt.Checked:
            item.setCheckState(0, Qt.Checked)
        elif uid_checkState == Qt.Unchecked:
            item.setCheckState(0, Qt.Unchecked)

    def toggle_xsection_visibility(self, item, column):
        """Called by self.XSectionTreeWidget.itemChanged.connect(self.toggle_xsection_visibility)."""
        name = item.text(0)  # not used
        uid = item.text(1)
        uid_checkState = item.checkState(0)
        if uid:  # needed to skip messages from upper levels of tree that do not broadcast uid's
            if uid_checkState == Qt.Checked:
                if not self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                    self.actors_df.loc[self.actors_df['uid'] == uid, 'show'] = True
                    self.set_actor_visible(uid=uid, visible=True)
            elif uid_checkState == Qt.Unchecked:
                if self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                    self.actors_df.loc[self.actors_df['uid'] == uid, 'show'] = False
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
        self.BoundariesTableWidget.setHorizontalHeaderLabels(['Name', 'uid'])
        self.BoundariesTableWidget.hideColumn(1)  # hide the uid column
        if sec_uid:
            uids = self.parent.boundary_coll.df.loc[(self.parent.boundary_coll.df['x_section'] == sec_uid), 'uid'].to_list()
        else:
            uids = self.parent.boundary_coll.df['uid'].to_list()
        row = 0
        for uid in uids:
            name = self.parent.boundary_coll.df.loc[self.parent.boundary_coll.df['uid'] == uid, 'name'].values[0]
            name_item = QTableWidgetItem(name)
            name_item.setFlags(name_item.flags() | Qt.ItemIsUserCheckable)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            uid_item = QTableWidgetItem(uid)
            self.BoundariesTableWidget.insertRow(row)
            self.BoundariesTableWidget.setItem(row, 0, name_item)
            self.BoundariesTableWidget.setItem(row, 1, uid_item)
            if self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                name_item.setCheckState(Qt.Checked)
            elif not self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                name_item.setCheckState(Qt.Unchecked)
            row += 1
        """Send message with argument = the cell being checked/unchecked."""
        self.BoundariesTableWidget.itemChanged.connect(self.toggle_boundary_visibility)

    def update_boundary_list_added(self, new_list=None):
        """Update boundaries list without creating a new model"""
        row = self.BoundariesTableWidget.rowCount()
        for uid in new_list['uid']:
            name = self.parent.boundary_coll.df.loc[self.parent.boundary_coll.df['uid'] == uid, 'name'].values[0]
            name_item = QTableWidgetItem(name)
            name_item.setFlags(name_item.flags() | Qt.ItemIsUserCheckable)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            uid_item = QTableWidgetItem(uid)
            self.BoundariesTableWidget.insertRow(row)
            self.BoundariesTableWidget.setItem(row, 0, name_item)
            self.BoundariesTableWidget.setItem(row, 1, uid_item)
            if self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                name_item.setCheckState(Qt.Checked)
            elif not self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
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
        check_state = self.BoundariesTableWidget.item(cell.row(), 0).checkState()  # this is the check state of cell "name"
        uid = self.BoundariesTableWidget.item(cell.row(), 1).text()  # this is the text of cell "uid"
        if check_state == Qt.Checked:
            if not self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                self.actors_df.loc[self.actors_df['uid'] == uid, 'show'] = True
                self.set_actor_visible(uid=uid, visible=True)
        elif check_state == Qt.Unchecked:
            if self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                self.actors_df.loc[self.actors_df['uid'] == uid, 'show'] = False
                self.set_actor_visible(uid=uid, visible=False)

    """Methods used to build and update the Mesh3D table."""

    def create_mesh3d_list(self,sec_uid=None):
        """Create mesh3D list with checkboxes."""
        self.Mesh3DTableWidget.clear()
        self.Mesh3DTableWidget.setColumnCount(3)
        self.Mesh3DTableWidget.setRowCount(0)
        self.Mesh3DTableWidget.setHorizontalHeaderLabels(['Name', 'uid'])
        self.Mesh3DTableWidget.hideColumn(1)  # hide the uid column
        if sec_uid:
            uids = self.parent.mesh3d_coll.df.loc[(self.parent.mesh3d_coll.df['x_section']==sec_uid),'uid'].to_list()
        else:
            uids = self.parent.mesh3d_coll.df['uid'].to_list()
        row = 0
        for uid in uids:
            name = self.parent.mesh3d_coll.df.loc[self.parent.mesh3d_coll.df['uid'] == uid, 'name'].values[0]
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
            property_combo.currentIndexChanged.connect(lambda: self.toggle_property_mesh3d())
            if self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                name_item.setCheckState(Qt.Checked)
            elif not self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                name_item.setCheckState(Qt.Unchecked)
            row += 1
        """Send message with argument = the cell being checked/unchecked."""
        self.Mesh3DTableWidget.itemChanged.connect(self.toggle_mesh3d_visibility)

    def update_mesh3d_list_added(self, new_list=None):
        """Update Mesh3D list without creating a new model"""
        row = self.Mesh3DTableWidget.rowCount()
        uid_list = list(new_list['uid'])
        if sec_uid:
            for i,uid in enumerate(new_list['uid']):
                if sec_uid != self.parent.mesh3d_coll.df.loc[self.parent.mesh3d_coll.df['uid'] == uid, 'x_section'].values[0]:
                    del uid_list[i]
        for uid in uid_list:
            name = self.parent.mesh3d_coll.df.loc[self.parent.mesh3d_coll.df['uid'] == uid, 'name'].values[0]
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
            property_combo.currentIndexChanged.connect(lambda: self.toggle_property_mesh3d())
            if self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                name_item.setCheckState(Qt.Checked)
            elif not self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
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
        check_state = self.Mesh3DTableWidget.item(cell.row(), 0).checkState()  # this is the check state of cell "name"
        uid = self.Mesh3DTableWidget.item(cell.row(), 1).text()  # this is the text of cell "uid"
        if check_state == Qt.Checked:
            if not self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                self.actors_df.loc[self.actors_df['uid'] == uid, 'show'] = True
                self.set_actor_visible(uid=uid, visible=True)
        elif check_state == Qt.Unchecked:
            if self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                self.actors_df.loc[self.actors_df['uid'] == uid, 'show'] = False
                self.set_actor_visible(uid=uid, visible=False)

    def toggle_property_mesh3d(self):
        """Method to toggle the texture shown by a Mesh3D that is already present in the view."""
        """Collect values from combo box."""
        combo = self.sender()
        show_property = combo.currentText()
        uid = combo.uid
        show = self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]
        collection = self.actors_df.loc[self.actors_df['uid'] == uid, 'collection'].values[0]
        """This removes the previous copy of the actor with the same uid, then calls the viewer-specific function that shows an actor with a property.
        IN THE FUTURE see if it is possible and more efficient to keep the actor and just change the property shown."""
        self.remove_actor_in_view(uid=uid)
        this_actor = self.show_actor_with_property(uid=uid, collection=collection, show_property=show_property, visible=show)
        self.actors_df = self.actors_df.append({'uid': uid, 'actor': this_actor, 'show': show, 'collection': collection, 'show_prop': show_property}, ignore_index=True)  # self.set_actor_visible(uid=uid, visible=show)

    """Methods used to build and update the DOM table."""

    def create_dom_list(self,sec_uid=None):
        """Create cross-sections list with checkboxes."""
        self.DOMsTableWidget.clear()
        self.DOMsTableWidget.setColumnCount(3)
        self.DOMsTableWidget.setRowCount(0)
        self.DOMsTableWidget.setHorizontalHeaderLabels(['Name', 'uid','Show property'])
        self.DOMsTableWidget.hideColumn(1)  # hide the uid column
        row = 0
        if sec_uid:
            uids = self.parent.dom_coll.df.loc[(self.parent.dom_coll.df['x_section']==sec_uid),'uid'].to_list()
        else:
            uids = self.parent.dom_coll.df['uid'].to_list()
        for uid in uids:
            # print(self.parent.dom_coll.df.loc[self.parent.dom_coll.df['uid'] == uid, 'name'])
            name = self.parent.dom_coll.df.loc[self.parent.dom_coll.df['uid'] == uid, 'name'].values[0]
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

            '''[Gabriele] To add support to multi components properties (e.g. RGB) we can add a component check (if components > 1). If this statement is True we can iterate over the n components and set the new n properties using the template prop[n_component]. These properties do not point to actual data (the "RGB[0]" property is not present) but to a slice of the original property (RGB[:,0]).'''

            for prop, components in zip(self.parent.dom_coll.get_uid_properties_names(uid),self.parent.dom_coll.get_uid_properties_components(uid)):

                if prop not in self.parent.dom_coll.df.loc[self.parent.dom_coll.df['uid'] == uid, "texture_uids"].values[0]:
                    property_texture_combo.addItem(prop)
                    property_texture_combo.texture_uid_list.append(prop)

                    if components > 1:
                        for component in range(components):
                            property_texture_combo.addItem(f'{prop}[{component}]')
                            property_texture_combo.texture_uid_list.append(f'{prop}[{component}]')

            for texture_uid in self.parent.dom_coll.df.loc[self.parent.dom_coll.df['uid'] == uid, 'texture_uids'].values[0]:
                texture_name = self.parent.image_coll.df.loc[self.parent.image_coll.df['uid'] == texture_uid, 'name'].values[0]
                property_texture_combo.addItem(texture_name)
                property_texture_combo.texture_uid_list.append(texture_uid)

            self.DOMsTableWidget.insertRow(row)
            self.DOMsTableWidget.setItem(row, 0, name_item)
            self.DOMsTableWidget.setItem(row, 1, uid_item)
            self.DOMsTableWidget.setCellWidget(row, 2, property_texture_combo)
            property_texture_combo.currentIndexChanged.connect(lambda: self.toggle_property_texture())
            if self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                name_item.setCheckState(Qt.Checked)
            elif not self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                name_item.setCheckState(Qt.Unchecked)
            row += 1
        """Send message with argument = the cell being checked/unchecked."""
        self.DOMsTableWidget.itemChanged.connect(self.toggle_dom_visibility)

    def update_dom_list_added(self, new_list=None, sec_uid=None):
        """Update DOM list without creating a new model"""
        # print('update_dom_list_added')
        row = self.DOMsTableWidget.rowCount()
        uid_list = list(new_list['uid'])
        if sec_uid:
            for i,uid in enumerate(new_list['uid']):
                if sec_uid != self.parent.dom_coll.df.loc[self.parent.dom_coll.df['uid'] == uid, 'x_section'].values[0]:
                    del uid_list[i]
        for uid in uid_list:
            name = self.parent.dom_coll.df.loc[self.parent.dom_coll.df['uid'] == uid, 'name'].values[0]
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

            '''[Gabriele] See function above for explanation'''

            for prop, components in zip(self.parent.dom_coll.get_uid_properties_names(uid),self.parent.dom_coll.get_uid_properties_components(uid)):
                if prop not in self.parent.dom_coll.df.loc[self.parent.dom_coll.df['uid'] == uid, "texture_uids"].values[0]:
                    property_texture_combo.addItem(prop)
                    property_texture_combo.texture_uid_list.append(prop)
                    # print(prop)
                    if components > 1:
                        for n_component in range(components):
                            property_texture_combo.addItem(f'{prop}[{n_component}]')
                            property_texture_combo.texture_uid_list.append(f'{prop}[{n_component}]')
            for texture_uid in self.parent.dom_coll.df.loc[self.parent.dom_coll.df['uid'] == uid, 'texture_uids'].values[0]:
                texture_name = self.parent.image_coll.df.loc[self.parent.image_coll.df['uid'] == texture_uid, 'name'].values[0]
                property_texture_combo.addItem(texture_name)
                property_texture_combo.texture_uid_list.append(texture_uid)
            self.DOMsTableWidget.insertRow(row)
            self.DOMsTableWidget.setItem(row, 0, name_item)
            self.DOMsTableWidget.setItem(row, 1, uid_item)
            self.DOMsTableWidget.setCellWidget(row, 2, property_texture_combo)
            property_texture_combo.currentIndexChanged.connect(lambda: self.toggle_property_texture())
            if self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                name_item.setCheckState(Qt.Checked)
            elif not self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
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
        check_state = self.DOMsTableWidget.item(cell.row(), 0).checkState()  # this is the check state of cell "name"

        uid = self.DOMsTableWidget.item(cell.row(), 1).text()  # this is the text of cell "uid"
        # print(uid)
        if check_state == Qt.Checked:
            if not self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                self.actors_df.loc[self.actors_df['uid'] == uid, 'show'] = True
                self.set_actor_visible(uid=uid, visible=True)


        elif check_state == Qt.Unchecked:
            if self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                self.actors_df.loc[self.actors_df['uid'] == uid, 'show'] = False
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
        if property_texture_uid in self.parent.dom_coll.df.loc[self.parent.dom_coll.df['uid'] == uid, "texture_uids"].values[0]:
            self.parent.dom_coll.set_active_texture_on_dom(dom_uid=uid, map_image_uid=property_texture_uid)
        """Show DOM with current texture"""
        show = self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]
        collection = self.actors_df.loc[self.actors_df['uid'] == uid, 'collection'].values[0]
        """This removes the previous copy of the actor with the same uid, then calls the viewer-specific function that shows an actor with a property.
        IN THE FUTURE see if it is possible and more efficient to keep the actor and just change the property shown."""

        # [Gabriele] Remove the previous scalar bar if present
        if hasattr(self, 'plotter'):
            try:
                self.plotter.remove_scalar_bar()
            except IndexError:
                pass
        self.remove_actor_in_view(uid=uid)
        this_actor = self.show_actor_with_property(uid=uid, collection=collection, show_property=property_texture_uid, visible=show)
        self.actors_df = self.actors_df.append({'uid': uid, 'actor': this_actor, 'show': show, 'collection': collection, 'show_prop': property_texture_uid}, ignore_index=True)  # self.set_actor_visible(uid=uid, visible=show)

    """Methods used to build and update the image table."""

    def create_image_list(self, sec_uid=None):
        """Create image list with checkboxes."""
        self.ImagesTableWidget.clear()
        self.ImagesTableWidget.setColumnCount(3)
        self.ImagesTableWidget.setRowCount(0)
        self.ImagesTableWidget.setHorizontalHeaderLabels(['Name', 'uid'])
        self.ImagesTableWidget.hideColumn(1)  # hide the uid column
        if sec_uid:
            uids = self.parent.image_coll.df.loc[(self.parent.image_coll.df['x_section'] == sec_uid), 'uid'].to_list()
        else:
            uids = self.parent.image_coll.df['uid'].to_list()
        row = 0
        for uid in uids:
            name = self.parent.image_coll.df.loc[self.parent.image_coll.df['uid'] == uid, 'name'].values[0]
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
            property_combo.currentIndexChanged.connect(lambda: self.toggle_property_image())  #___________
            if self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                name_item.setCheckState(Qt.Checked)
            elif not self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                name_item.setCheckState(Qt.Unchecked)
            row += 1
        """Send message with argument = the cell being checked/unchecked."""
        self.ImagesTableWidget.itemChanged.connect(self.toggle_image_visibility)

    def update_image_list_added(self, new_list=None):
        """Update Image list without creating a new model"""
        row = self.ImagesTableWidget.rowCount()
        for uid in new_list['uid']:
            name = self.parent.image_coll.df.loc[self.parent.image_coll.df['uid'] == uid, 'name'].values[0]
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
            property_combo.currentIndexChanged.connect(lambda: self.toggle_property_image())  #___________
            if self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                name_item.setCheckState(Qt.Checked)
            elif not self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
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
        check_state = self.ImagesTableWidget.item(cell.row(), 0).checkState()  # this is the check state of cell "name"
        uid = self.ImagesTableWidget.item(cell.row(), 1).text()  # this is the text of cell "uid"
        if check_state == Qt.Checked:
            if not self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                self.actors_df.loc[self.actors_df['uid'] == uid, 'show'] = True
                self.set_actor_visible(uid=uid, visible=True)
        elif check_state == Qt.Unchecked:
            if self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                self.actors_df.loc[self.actors_df['uid'] == uid, 'show'] = False
                self.set_actor_visible(uid=uid, visible=False)

    def toggle_property_image(self):
        """Method to toggle the property shown by an image that is already present in the view."""
        """Collect values from combo box."""
        combo = self.sender()
        show_property = combo.currentText()
        uid = combo.uid
        show = self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]
        collection = self.actors_df.loc[self.actors_df['uid'] == uid, 'collection'].values[0]
        """This removes the previous copy of the actor with the same uid, then calls the viewer-specific function that shows an actor with a property.
        IN THE FUTURE see if it is possible and more efficient to keep the actor and just change the property shown."""
        self.remove_actor_in_view(uid=uid)
        this_actor = self.show_actor_with_property(uid=uid, collection=collection, show_property=show_property, visible=show)
        self.actors_df = self.actors_df.append({'uid': uid, 'actor': this_actor, 'show': show, 'collection': collection, 'show_prop': show_property}, ignore_index=True)  # self.set_actor_visible(uid=uid, visible=show)

    def create_well_tree(self):
        """Create topology tree with checkboxes and properties"""
        self.WellsTreeWidget.clear()
        self.WellsTreeWidget.setColumnCount(3)
        self.WellsTreeWidget.setHeaderLabels(['Loc ID > Unit name', 'uid', 'property'])
        self.WellsTreeWidget.hideColumn(1)  # hide the uid column
        self.WellsTreeWidget.setItemsExpandable(True)


        locids = pd.unique(self.parent.well_coll.df['Loc ID'])

        for locid in locids:
            tlevel_1 = QTreeWidgetItem(self.WellsTreeWidget, [locid])  # self.GeologyTreeWidget as parent -> top level
            tlevel_1.setFlags(tlevel_1.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable)
            for geological_feature in pd.unique(self.parent.well_coll.df.loc[self.parent.well_coll.df['Loc ID'] == locid, 'geological_feature']):
                uid = self.parent.well_coll.df.loc[(self.parent.well_coll.df['Loc ID'] == locid)&(self.parent.well_coll.df['geological_feature'] == geological_feature), 'uid'].values[0]
                tlevel_2 = QTreeWidgetItem(tlevel_1, [geological_feature, uid])  # tlevel_1 as parent -> middle level
                tlevel_2.setFlags(tlevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable)

                property_combo = QComboBox()
                property_combo.uid = uid
                property_combo.addItem("none")
                property_combo.addItem("X")
                property_combo.addItem("Y")
                property_combo.addItem("Z")
                for prop in self.parent.well_coll.get_uid_properties_names(uid):
                    property_combo.addItem(prop)

                self.WellsTreeWidget.setItemWidget(tlevel_2, 2, property_combo)
                property_combo.currentIndexChanged.connect(lambda: self.toggle_property())
                tlevel_2.setFlags(tlevel_2.flags() | Qt.ItemIsUserCheckable)
                if self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                    tlevel_2.setCheckState(0, Qt.Checked)
                elif not self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                    tlevel_2.setCheckState(0, Qt.Unchecked)
        """Send messages. Note that with tristate several signals are emitted in a sequence, one for each
        changed item, but upper levels do not broadcast uid's so they are filtered in the toggle method."""
        self.WellsTreeWidget.itemChanged.connect(self.toggle_well_visibility)
        self.WellsTreeWidget.expandAll()


    def update_well_tree_added(self, new_list=None):
        """Update geology tree without creating a new model"""
        for uid in new_list['uid']:
            if self.WellsTreeWidget.findItems(self.parent.well_coll.get_uid_well_locid(uid), Qt.MatchExactly, 0) != []:
                """Already exists a TreeItem (1 level) for the geological type"""
                counter_1 = 0
                for child_1 in range(self.WellsTreeWidget.findItems(self.parent.well_coll.get_uid_well_locid(uid), Qt.MatchExactly, 0)[0].childCount()):
                    glevel_2 = QTreeWidgetItem(self.WellsTreeWidget.findItems(self.parent.well_coll.get_uid_well_locid(uid), Qt.MatchExactly, 0)[0], [self.parent.well_coll.get_uid_geological_feature(uid),uid])
                    glevel_2.setFlags(glevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable)
                    self.WellsTreeWidget.insertTopLevelItem(0, glevel_2)

                    property_combo = QComboBox()
                    property_combo.uid = uid
                    property_combo.addItem("none")
                    property_combo.addItem("X")
                    property_combo.addItem("Y")
                    property_combo.addItem("Z")
                    for prop in self.parent.well_coll.get_uid_properties_names(uid):
                        property_combo.addItem(prop)

                    self.WellsTreeWidget.setItemWidget(glevel_2, 2, property_combo)
                    property_combo.currentIndexChanged.connect(lambda: self.toggle_property())
                    glevel_2.setFlags(glevel_2.flags() | Qt.ItemIsUserCheckable)
                    if self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                        glevel_2.setCheckState(0, Qt.Checked)
                    elif not self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                        glevel_2.setCheckState(0, Qt.Unchecked)
                    self.WellsTreeWidget.insertTopLevelItem(0, glevel_2)
                    break
            else:
                """Different geological type, geological feature and scenario"""
                glevel_1 = QTreeWidgetItem(self.WellsTreeWidget, [self.parent.well_coll.get_uid_well_locid(uid)])
                glevel_1.setFlags(glevel_1.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable)
                self.WellsTreeWidget.insertTopLevelItem(0, glevel_1)

                property_combo = QComboBox()
                property_combo.uid = uid
                property_combo.addItem("none")
                property_combo.addItem("X")
                property_combo.addItem("Y")
                property_combo.addItem("Z")
                for prop in self.parent.well_coll.get_uid_properties_names(uid):
                    property_combo.addItem(prop)

                name = self.parent.well_coll.get_uid_geological_feature(uid)
                glevel_2 = QTreeWidgetItem(glevel_1, [name, uid])
                self.WellsTreeWidget.setItemWidget(glevel_2, 2, property_combo)
                property_combo.currentIndexChanged.connect(lambda: self.toggle_property())
                glevel_2.setFlags(glevel_2.flags() | Qt.ItemIsUserCheckable)
                if self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                    glevel_2.setCheckState(0, Qt.Checked)
                elif not self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                    glevel_2.setCheckState(0, Qt.Unchecked)
                self.WellsTreeWidget.insertTopLevelItem(0, glevel_2)
                break

        self.WellsTreeWidget.itemChanged.connect(self.toggle_well_visibility)
        self.WellsTreeWidget.expandAll()



    def update_well_tree_removed(self, removed_list=None):
        """When geological entity is removed, update Geology Tree without building a new model"""
        success = 0
        for uid in removed_list:
            for well_locid in range(self.WellsTreeWidget.topLevelItemCount()):
                """Iterate through every Geological Type top level"""
                for child_geo_feat in range(self.WellsTreeWidget.topLevelItem(well_locid).childCount()):
                    """Iterate through every Geological Feature child"""
                    if self.WellsTreeWidget.topLevelItem(well_locid).child(child_geo_feat).text(1) == uid:
                        """Complete check: entity found has the uid of the entity we need to remove. Delete child, then ensure no Child or Top Level remain empty"""
                        success = 1
                        self.WellsTreeWidget.topLevelItem(well_locid).child(child_geo_feat).removeChild(self.WellsTreeWidget.topLevelItem(well_locid).child(child_geo_feat))

                        if self.WellsTreeWidget.topLevelItem(well_locid).childCount() == 0:
                            self.WellsTreeWidget.takeTopLevelItem(well_locid)
                        break
                if success == 1:
                    break

    def update_well_checkboxes(self, uid=None, uid_checkState=None):
        """Update checkboxes in geology tree, called when state changed in topology tree."""
        item = self.WellsTreeWidget.findItems(uid, Qt.MatchFixedString | Qt.MatchRecursive, 1)[0]
        if uid_checkState == Qt.Checked:
            item.setCheckState(0, Qt.Checked)
        elif uid_checkState == Qt.Unchecked:
            item.setCheckState(0, Qt.Unchecked)

    def toggle_well_visibility(self, item, column):
        """Called by self.WellsTreeWidget.itemChanged.connect(self.toggle_boundary_visibility)."""
        name = item.text(0)  # not used
        uid = item.text(1)
        uid_checkState = item.checkState(0)
        if uid:  # needed to skip messages from upper levels of tree that do not broadcast uid's
            if uid_checkState == Qt.Checked:
                if not self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                    self.actors_df.loc[self.actors_df['uid'] == uid, 'show'] = True
                    self.set_actor_visible(uid=uid, visible=True)
            elif uid_checkState == Qt.Unchecked:
                if self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                    self.actors_df.loc[self.actors_df['uid'] == uid, 'show'] = False
                    self.set_actor_visible(uid=uid, visible=False)

            self.WellsTreeWidget.itemChanged.disconnect()
            self.update_well_checkboxes(uid=uid, uid_checkState=uid_checkState)
            self.WellsTreeWidget.itemChanged.connect(self.toggle_well_visibility)


    def well_added_update_views(self, updated_list=None):
        """This is called when an entity is added to the geological collection.
        Disconnect signals to geology and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.WellsTreeWidget.itemChanged.disconnect()
        """Create pandas dataframe as list of "new" actors"""
        actors_df_new = pd.DataFrame(columns=['uid', 'actor', 'show', 'collection', 'show_prop'])
        for uid in updated_list:
            this_actor = self.show_actor_with_property(uid=uid, collection='well_coll', show_property=None, visible=True)
            self.actors_df = self.actors_df.append({'uid': uid, 'actor': this_actor, 'show': True, 'collection': 'well_coll', 'show_prop': None}, ignore_index=True)
            actors_df_new = actors_df_new.append({'uid': uid, 'actor': this_actor, 'show': True, 'collection': 'well_coll', 'show_prop': None}, ignore_index=True)
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
            if not self.actors_df.loc[self.actors_df['uid'] == uid, 'show_prop'].to_list() == []:
                if not self.actors_df.loc[self.actors_df['uid'] == uid, 'show_prop'].values[0] in self.parent.geol_coll.get_uid_properties_names(uid):
                    show = self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].to_list()[0]
                    self.remove_actor_in_view(uid=uid)
                    this_actor = self.show_actor_with_property(uid=uid, collection='geol_coll', show_property=None, visible=show)
                    self.actors_df = self.actors_df.append({'uid': uid, 'actor': this_actor, 'show': show, 'collection': 'well_coll', 'show_prop': None}, ignore_index=True)  # self.actors_df.loc[self.actors_df["uid"] == uid, 'actor'] = this_actor
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
            self.change_actor_color(uid=uid, collection='well_coll')
            self.change_actor_line_thick(uid=uid, collection='well_coll')
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
            self.change_actor_color(uid=uid, collection='well_coll')
        """Re-connect signals."""
        self.WellsTreeWidget.itemChanged.connect(self.toggle_well_visibility)

    def well_legend_thick_modified_update_views(self, updated_list=None):
        """This is called when the line thickness in the geological legend is modified.
        Disconnect signals to geology and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.WellsTreeWidget.itemChanged.disconnect()
        for uid in updated_list:
            """Case for line_thick changed"""
            self.change_actor_line_thick(uid=uid, collection='well_coll')
        """Re-connect signals."""
        self.WellsTreeWidget.itemChanged.connect(self.toggle_well_visibility)
    """Methods used to add, remove, and update actors from the geological collection."""

    def geology_added_update_views(self, updated_list=None):
        """This is called when an entity is added to the geological collection.
        Disconnect signals to geology and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.GeologyTreeWidget.itemChanged.disconnect()
        self.TopologyTreeWidget.itemChanged.disconnect()
        """Create pandas dataframe as list of "new" actors"""
        actors_df_new = pd.DataFrame(columns=['uid', 'actor', 'show', 'collection', 'show_prop'])
        for uid in updated_list:
            this_actor = self.show_actor_with_property(uid=uid, collection='geol_coll', show_property=None, visible=True)
            self.actors_df = self.actors_df.append({'uid': uid, 'actor': this_actor, 'show': True, 'collection': 'geol_coll', 'show_prop': None}, ignore_index=True)
            actors_df_new = actors_df_new.append({'uid': uid, 'actor': this_actor, 'show': True, 'collection': 'geol_coll', 'show_prop': None}, ignore_index=True)
            self.update_geology_tree_added(actors_df_new)
            self.update_topology_tree_added(actors_df_new)
        """Re-connect signals."""
        self.GeologyTreeWidget.itemChanged.connect(self.toggle_geology_topology_visibility)
        self.TopologyTreeWidget.itemChanged.connect(self.toggle_geology_topology_visibility)

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
        self.GeologyTreeWidget.itemChanged.connect(self.toggle_geology_topology_visibility)
        self.TopologyTreeWidget.itemChanged.connect(self.toggle_geology_topology_visibility)

    def geology_geom_modified_update_views(self, updated_list=None):
        """This is called when an entity geometry or topology is modified (i.e. the vtk object is modified).
        Disconnect signals to geology and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.GeologyTreeWidget.itemChanged.disconnect()
        self.TopologyTreeWidget.itemChanged.disconnect()
        for uid in updated_list:
            """This calls the viewer-specific function that shows an actor with property = None.
            IN THE FUTURE update required to keep the current property shown.____________"""
            self.remove_actor_in_view(uid=uid)
            this_actor = self.show_actor_with_property(uid=uid, collection='geol_coll', show_property=None, visible=True)
            self.actors_df = self.actors_df.append({'uid': uid, 'actor': this_actor, 'show': True, 'collection': 'geol_coll', 'show_prop': None}, ignore_index=True)  # self.actors_df.loc[self.actors_df["uid"] == uid, 'actor'] = this_actor
        """Re-connect signals."""
        self.GeologyTreeWidget.itemChanged.connect(self.toggle_geology_topology_visibility)
        self.TopologyTreeWidget.itemChanged.connect(self.toggle_geology_topology_visibility)

    def geology_data_keys_modified_update_views(self, updated_list=None):
        """This is called when entity point or cell data are modified.
        Disconnect signals to geology and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.GeologyTreeWidget.itemChanged.disconnect()
        self.TopologyTreeWidget.itemChanged.disconnect()
        for uid in updated_list:
            if not self.actors_df.loc[self.actors_df['uid'] == uid, 'show_prop'].to_list() == []:
                if not self.actors_df.loc[self.actors_df['uid'] == uid, 'show_prop'].values[0] in self.parent.geol_coll.get_uid_properties_names(uid):
                    show = self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].to_list()[0]
                    self.remove_actor_in_view(uid=uid)
                    this_actor = self.show_actor_with_property(uid=uid, collection='geol_coll', show_property=None, visible=show)
                    self.actors_df = self.actors_df.append({'uid': uid, 'actor': this_actor, 'show': show, 'collection': 'geol_coll', 'show_prop': None}, ignore_index=True)  # self.actors_df.loc[self.actors_df["uid"] == uid, 'actor'] = this_actor
                    self.create_geology_tree()
                    self.create_topology_tree()
        """Re-connect signals."""
        self.GeologyTreeWidget.itemChanged.connect(self.toggle_geology_topology_visibility)
        self.TopologyTreeWidget.itemChanged.connect(self.toggle_geology_topology_visibility)

    def geology_data_val_modified_update_views(self, updated_list=None):
        """This is called when entity point or cell data are modified.
        Disconnect signals to geology and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.GeologyTreeWidget.itemChanged.disconnect()
        self.TopologyTreeWidget.itemChanged.disconnect()
        """IN THE FUTURE - generally just update the properties list - more complicate if we modify or delete the property that is shown_____________________"""
        """Re-connect signals."""
        self.GeologyTreeWidget.itemChanged.connect(self.toggle_geology_topology_visibility)
        self.TopologyTreeWidget.itemChanged.connect(self.toggle_geology_topology_visibility)

    def geology_metadata_modified_update_views(self, updated_list=None):
        """This is called when entity metadata are modified, and the legend is automatically updated.
        Disconnect signals to geology and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.GeologyTreeWidget.itemChanged.disconnect()
        self.TopologyTreeWidget.itemChanged.disconnect()
        for uid in updated_list:
            """Case for entities modified"""
            self.change_actor_color(uid=uid, collection='geol_coll')
            self.change_actor_line_thick(uid=uid, collection='geol_coll')
            self.create_geology_tree()
            self.create_topology_tree()
        """Re-connect signals."""
        self.GeologyTreeWidget.itemChanged.connect(self.toggle_geology_topology_visibility)
        self.TopologyTreeWidget.itemChanged.connect(self.toggle_geology_topology_visibility)

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
                self.change_actor_color(uid=self.parent.geol_coll.get_uid_x_section(uid), collection='well_coll')
            self.change_actor_color(uid=uid, collection='geol_coll')

        """Re-connect signals."""
        self.GeologyTreeWidget.itemChanged.connect(self.toggle_geology_topology_visibility)
        self.TopologyTreeWidget.itemChanged.connect(self.toggle_geology_topology_visibility)

    def geology_legend_thick_modified_update_views(self, updated_list=None):
        """This is called when the line thickness in the geological legend is modified.
        Disconnect signals to geology and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.GeologyTreeWidget.itemChanged.disconnect()
        self.TopologyTreeWidget.itemChanged.disconnect()
        for uid in updated_list:
            """Case for line_thick changed"""
            self.change_actor_line_thick(uid=uid, collection='geol_coll')
        """Re-connect signals."""
        self.GeologyTreeWidget.itemChanged.connect(self.toggle_geology_topology_visibility)
        self.TopologyTreeWidget.itemChanged.connect(self.toggle_geology_topology_visibility)

    """Methods used to add, remove, and update actors from the cross section collection."""

    def xsect_added_update_views(self, updated_list=None):
        """This is called when a cross-section is added to the xsect collection.
        Disconnect signals to xsect list, if they are set, then they are
        reconnected when the list is rebuilt"""
        self.XSectionTreeWidget.itemChanged.disconnect()
        actors_df_new = pd.DataFrame(columns=['uid', 'actor', 'show', 'collection', 'show_prop'])
        for uid in updated_list:
            this_actor = self.show_actor_with_property(uid=uid, collection='xsect_coll', show_property=None, visible=True)
            self.actors_df = self.actors_df.append({'uid': uid, 'actor': this_actor, 'show': True, 'collection': 'xsect_coll', 'show_prop': None}, ignore_index=True)
            actors_df_new = actors_df_new.append({'uid': uid, 'actor': this_actor, 'show': True, 'collection': 'xsect_coll', 'show_prop': None}, ignore_index=True)
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
            IN THE FUTURE update required to keep the current property shown.____________"""
            self.remove_actor_in_view(uid=uid)
            this_actor = self.show_actor_with_property(uid=uid, collection='xsect_coll', show_property=None, visible=True)
            self.actors_df.loc[self.actors_df["uid"] == uid, 'actor'].values[0] = this_actor
        """Re-connect signals."""
        self.XSectionTreeWidget.itemChanged.connect(self.toggle_xsection_visibility)

    def xsect_metadata_modified_update_views(self, updated_list=None):
        """This is called when the cross-section metadata are modified.
        Disconnect signals to xsect list, if they are set, then they are
        reconnected when the list is rebuilt"""
        self.XSectionTreeWidget.itemChanged.disconnect()
        for uid in updated_list:
            """Case for entities modified"""
            self.change_actor_color(uid=uid, collection='xsect_coll')
            self.change_actor_line_thick(uid=uid, collection='xsect_coll')
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
            self.change_actor_color(uid=uid, collection='xsect_coll')
        """Re-connect signals."""
        self.XSectionTreeWidget.itemChanged.connect(self.toggle_xsection_visibility)

    def xsect_legend_thick_modified_update_views(self, updated_list=None):
        """This is called when the line thickness in the cross-section legend is modified.
        Disconnect signals to xsect list, if they are set, then they are
        reconnected when the list is rebuilt"""
        self.XSectionTreeWidget.itemChanged.disconnect()
        for uid in updated_list:
            """Case for line_thick changed"""
            self.change_actor_line_thick(uid=uid, collection='xsect_coll')
        """Re-connect signals."""
        self.XSectionTreeWidget.itemChanged.connect(self.toggle_xsection_visibility)

    """Methods used to add, remove, and update actors from the Boundary collection."""

    def boundary_added_update_views(self, updated_list=None):
        """This is called when a boundary is added to the boundary collection.
        Disconnect signals to boundary list, if they are set, then they are
        reconnected when the list is rebuilt"""
        self.BoundariesTableWidget.itemChanged.disconnect()
        actors_df_new = pd.DataFrame(columns=['uid', 'actor', 'show', 'collection', 'show_prop'])
        for uid in updated_list:
            this_actor = self.show_actor_with_property(uid=uid, collection='boundary_coll', show_property=None, visible=False)
            self.actors_df = self.actors_df.append({'uid': uid, 'actor': this_actor, 'show': False, 'collection': 'boundary_coll', 'show_prop': None}, ignore_index=True)
            actors_df_new = actors_df_new.append({'uid': uid, 'actor': this_actor, 'show': False, 'collection': 'boundary_coll', 'show_prop': None}, ignore_index=True)
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
            this_actor = self.show_actor_with_property(uid=uid, collection='boundary_coll', show_property=None, visible=True)
            self.actors_df = self.actors_df.append({'uid': uid, 'actor': this_actor, 'show': True, 'collection': 'boundary_coll', 'show_prop': None}, ignore_index=True)  # self.actors_df.loc[self.actors_df["uid"] == uid, 'actor'] = this_actor
        """Re-connect signals."""
        self.BoundariesTableWidget.itemChanged.connect(self.toggle_boundary_visibility)

    def boundary_metadata_modified_update_views(self, updated_list=None):
        """This is called when the boundary metadata are modified.
        Disconnect signals to boundary list, if they are set, then they are
        reconnected when the list is rebuilt"""
        self.BoundariesTableWidget.itemChanged.disconnect()
        for uid in updated_list:
            """Case for entities modified"""
            self.change_actor_color(uid=uid, collection='boundary_coll')
            self.change_actor_line_thick(uid=uid, collection='boundary_coll')
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
            self.change_actor_color(uid=uid, collection='boundary_coll')
        """Re-connect signals."""
        self.BoundariesTableWidget.itemChanged.connect(self.toggle_boundary_visibility)

    def boundary_legend_thick_modified_update_views(self, updated_list=None):
        """This is called when the line thickness in the boundary legend is modified.
        Disconnect signals to boundary list, if they are set, then they are
        reconnected when the list is rebuilt"""
        self.BoundariesTableWidget.itemChanged.disconnect()
        for uid in updated_list:
            """Case for line_thick changed"""
            self.change_actor_line_thick(uid=uid, collection='boundary_coll')
        """Re-connect signals."""
        self.BoundariesTableWidget.itemChanged.connect(self.toggle_boundary_visibility)

    """Methods used to add, remove, and update actors from the Mesh3D collection."""

    def mesh3d_added_update_views(self, updated_list=None):
        """This is called when a mesh3d is added to the mesh3d collection.
        Disconnect signals to mesh3d list, if they are set, then they are
        reconnected when the list is rebuilt"""
        self.Mesh3DTableWidget.itemChanged.disconnect()
        actors_df_new = pd.DataFrame(columns=['uid', 'actor', 'show', 'collection', 'show_prop'])
        for uid in updated_list:
            this_actor = self.show_actor_with_property(uid=uid, collection='mesh3d_coll', show_property=None, visible=False)
            self.actors_df = self.actors_df.append({'uid': uid, 'actor': this_actor, 'show': False, 'collection': 'mesh3d_coll', 'show_prop': None}, ignore_index=True)
            actors_df_new = actors_df_new.append({'uid': uid, 'actor': this_actor, 'show': False, 'collection': 'mesh3d_coll', 'show_prop': None}, ignore_index=True)
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
            if not self.actors_df.loc[self.actors_df['uid'] == uid, 'show_prop'].to_list() == []:
                if not self.actors_df.loc[self.actors_df['uid'] == uid, 'show_prop'].values[0] in self.parent.mesh3d_coll.get_uid_properties_names(uid):
                    show = self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].to_list()[0]
                    self.remove_actor_in_view(uid=uid)
                    this_actor = self.show_actor_with_property(uid=uid, collection='mesh3d_coll', show_property=None, visible=show)
                    self.actors_df = self.actors_df.append({'uid': uid, 'actor': this_actor, 'show': show, 'collection': 'mesh3d_coll', 'show_prop': None}, ignore_index=True)  # self.actors_df.loc[self.actors_df["uid"] == uid, 'actor'] = this_actor
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
            self.change_actor_color(uid=uid, collection='mesh3d_coll')
            self.change_actor_line_thick(uid=uid, collection='mesh3d_coll')
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
            self.change_actor_color(uid=uid, collection='mesh3d_coll')
        """Re-connect signals."""
        self.Mesh3DTableWidget.itemChanged.connect(self.toggle_mesh3d_visibility)

    def mesh3d_legend_thick_modified_update_views(self, updated_list=None):
        """This is called when the line thickness in the cross-section legend is modified.
        Disconnect signals to mesh3d list, if they are set, then they are
        reconnected when the list is rebuilt"""
        self.Mesh3DTableWidget.itemChanged.disconnect()
        for uid in updated_list:
            """Case for line_thick changed"""
            self.change_actor_line_thick(uid=uid, collection='mesh3d_coll')
        """Re-connect signals."""
        self.Mesh3DTableWidget.itemChanged.connect(self.toggle_mesh3d_visibility)

    """Methods used to add, remove, and update actors from the DOM collection."""

    def dom_added_update_views(self, updated_list=None):
        """This is called when a DOM is added to the xsect collection.
        Disconnect signals to dom list, if they are set, then they are
        reconnected when the list is rebuilt"""
        self.DOMsTableWidget.itemChanged.disconnect()
        actors_df_new = pd.DataFrame(columns=['uid', 'actor', 'show', 'collection', 'show_prop'])
        for uid in updated_list:
            this_actor = self.show_actor_with_property(uid=uid, collection='dom_coll', show_property=None, visible=False)
            self.actors_df = self.actors_df.append({'uid': uid, 'actor': this_actor, 'show': False, 'collection': 'dom_coll', 'show_prop': None}, ignore_index=True)
            actors_df_new = actors_df_new.append({'uid': uid, 'actor': this_actor, 'show': False, 'collection': 'dom_coll', 'show_prop': None}, ignore_index=True)
            self.update_dom_list_added(actors_df_new)
        """Re-connect signals."""
        self.DOMsTableWidget.itemChanged.connect(self.toggle_dom_visibility)

    def dom_removed_update_views(self, updated_list=None):
        """This is called when a DOM is removed from the dom collection.
        Disconnect signals to dom list, if they are set, then they are
        reconnected when the list is rebuilt"""
        self.DOMsTableWidget.itemChanged.disconnect()
        for uid in updated_list:
            self.remove_actor_in_view(uid=uid)
            self.update_dom_list_removed(removed_list=updated_list)
        """Re-connect signals."""
        self.DOMsTableWidget.itemChanged.connect(self.toggle_dom_visibility)

    def dom_data_keys_modified_update_views(self, updated_list=None):
        """This is called when entity point or cell data are modified.
        Disconnect signals to geology and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.DOMsTableWidget.itemChanged.disconnect()
        for uid in updated_list:
            if not self.actors_df.loc[self.actors_df['uid'] == uid, 'show_prop'].to_list() == []:
                if not self.actors_df.loc[self.actors_df['uid'] == uid, 'show_prop'].values[0] in self.parent.dom_coll.get_uid_properties_names(uid):
                    show = self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].to_list()[0]
                    self.remove_actor_in_view(uid=uid)
                    this_actor = self.show_actor_with_property(uid=uid, collection='dom_coll', show_property=None, visible=show)
                    self.actors_df = self.actors_df.append({'uid': uid, 'actor': this_actor, 'show': show, 'collection': 'dom_coll', 'show_prop': None}, ignore_index=True)  # self.actors_df.loc[self.actors_df["uid"] == uid, 'actor'] = this_actor
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
            self.change_actor_color(uid=uid, collection='dom_coll')
            self.change_actor_line_thick(uid=uid, collection='dom_coll')
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
            self.change_actor_color(uid=uid, collection='dom_coll')
        """Re-connect signals."""
        self.DOMsTableWidget.itemChanged.connect(self.toggle_dom_visibility)

    def dom_legend_thick_modified_update_views(self, updated_list=None):
        """This is called when the line thickness in the cross-section legend is modified.
        Disconnect signals to xsect list, if they are set, then they are
        reconnected when the list is rebuilt"""
        self.DOMsTableWidget.itemChanged.disconnect()
        for uid in updated_list:
            """Case for line_thick changed"""
            self.change_actor_line_thick(uid=uid, collection='dom_coll')
        """Re-connect signals."""
        self.DOMsTableWidget.itemChanged.connect(self.toggle_dom_visibility)

    """Methods used to add, remove, and update actors from the image collection."""

    def image_added_update_views(self, updated_list=None):
        """This is called when an image is added to the image collection.
        Disconnect signals to image list, if they are set, then they are
        reconnected when the list is rebuilt"""   """________________________________________________________________________"""
        self.ImagesTableWidget.itemChanged.disconnect()
        actors_df_new = pd.DataFrame(columns=['uid', 'actor', 'show', 'collection', 'show_prop'])
        for uid in updated_list:
            this_actor = self.show_actor_with_property(uid=uid, collection='image_coll', show_property=None, visible=False)
            self.actors_df = self.actors_df.append({'uid': uid, 'actor': this_actor, 'show': False, 'collection': 'image_coll', 'show_prop': None}, ignore_index=True)
            actors_df_new = actors_df_new.append({'uid': uid, 'actor': this_actor, 'show': False, 'collection': 'image_coll', 'show_prop': None}, ignore_index=True)
            self.update_image_list_added(actors_df_new)
        """Re-connect signals."""
        self.ImagesTableWidget.itemChanged.connect(self.toggle_image_visibility)

    def image_removed_update_views(self, updated_list=None):
        """This is called when an image is removed from the image collection.
        Disconnect signals to image list, if they are set, then they are
        reconnected when the list is rebuilt"""   """________________________________________________________________________"""
        self.ImagesTableWidget.itemChanged.disconnect()
        for uid in updated_list:
            self.remove_actor_in_view(uid=uid)
            self.update_image_list_removed(removed_list=updated_list)
        """Re-connect signals."""
        self.ImagesTableWidget.itemChanged.connect(self.toggle_image_visibility)

    def image_metadata_modified_update_views(self, updated_list=None):
        """This is called when the image metadata are modified.
        Disconnect signals to image list, if they are set, then they are
        reconnected when the list is rebuilt"""   """________________________________________________________________________"""
        self.ImagesTableWidget.itemChanged.disconnect()
        for uid in updated_list:
            """Case for entities modified"""
            self.create_image_list()
        """Re-connect signals."""
        self.ImagesTableWidget.itemChanged.connect(self.toggle_image_visibility)

    """General methods shared by all views."""

    def add_all_entities(self):
        """Add all entities in project collections. This must be reimplemented for cross-sections in order
        to show entities belonging to the section only. All objects are visible by default -> show = True"""
        for uid in self.parent.geol_coll.df['uid'].tolist():
            this_actor = self.show_actor_with_property(uid=uid, collection='geol_coll', show_property=None, visible=True)
            self.actors_df = self.actors_df.append({'uid': uid, 'actor': this_actor, 'show': True, 'collection': 'geol_coll', 'show_prop': None}, ignore_index=True)
        for uid in self.parent.xsect_coll.df['uid'].tolist():
            this_actor = self.show_actor_with_property(uid=uid, collection='xsect_coll', show_property=None, visible=False)
            self.actors_df = self.actors_df.append({'uid': uid, 'actor': this_actor, 'show': False, 'collection': 'xsect_coll', 'show_prop': None}, ignore_index=True)
        for uid in self.parent.boundary_coll.df['uid'].tolist():
            this_actor = self.show_actor_with_property(uid=uid, collection='boundary_coll', show_property=None, visible=False)
            self.actors_df = self.actors_df.append({'uid': uid, 'actor': this_actor, 'show': False, 'collection': 'boundary_coll', 'show_prop': None}, ignore_index=True)
        for uid in self.parent.mesh3d_coll.df['uid'].tolist():
            this_actor = self.show_actor_with_property(uid=uid, collection='mesh3d_coll', show_property=None, visible=False)
            self.actors_df = self.actors_df.append({'uid': uid, 'actor': this_actor, 'show': False, 'collection': 'mesh3d_coll', 'show_prop': None}, ignore_index=True)
        for uid in self.parent.dom_coll.df['uid'].tolist():
            this_actor = self.show_actor_with_property(uid=uid, collection='dom_coll', show_property=None, visible=False)
            self.actors_df = self.actors_df.append({'uid': uid, 'actor': this_actor, 'show': False, 'collection': 'dom_coll', 'show_prop': None}, ignore_index=True)
        for uid in self.parent.image_coll.df['uid'].tolist():
            this_actor = self.show_actor_with_property(uid=uid, collection='image_coll', show_property=None, visible=False)
            self.actors_df = self.actors_df.append({'uid': uid, 'actor': this_actor, 'show': False, 'collection': 'image_coll', 'show_prop': None}, ignore_index=True)
        for uid in self.parent.well_coll.df['uid'].tolist():
            this_actor = self.show_actor_with_property(uid=uid, collection='well_coll', show_property=None, visible=False)
            self.actors_df = self.actors_df.append({'uid': uid, 'actor': this_actor, 'show': False, 'collection': 'well_coll', 'show_prop': None}, ignore_index=True)

    def prop_legend_cmap_modified_update_views(self, this_property=None):
        """Redraw all actors that are currently shown with a property whose colormap has been changed."""
        for uid in self.actors_df['uid'].to_list():
            if self.actors_df.loc[self.actors_df['uid'] == uid, 'show_prop'].to_list()[0] == this_property:
                show = self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].to_list()[0]
                collection = self.actors_df.loc[self.actors_df['uid'] == uid, 'collection'].to_list()[0]
                """This removes the previous copy of the actor with the same uid, then calls the viewer-specific function that shows an actor with a property.
                IN THE FUTURE see if it is possible and more efficient to keep the actor and just change the property shown."""
                self.remove_actor_in_view(uid=uid)
                this_actor = self.show_actor_with_property(uid=uid, collection=collection, show_property=this_property, visible=show)
                self.actors_df = self.actors_df.append({'uid': uid, 'actor': this_actor, 'show': show, 'collection': collection, 'show_prop': this_property}, ignore_index=True)

    """All following functions must be re-implemented in derived classes - they appear here just as placeholders"""

    def closeEvent(self, event):
        """Override the closeEvent method of QWidget, close the plotter and ask for confirmation.
        This can be reimplemented for some particular kind of view, such as the 3D view."""
        reply = QMessageBox.question(self, 'Closing window', 'Close this window?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            event.accept()  # SEE ABOVE ON THE CLOSED WINDOW REFERENCE PROBLEM___________________________  # self.close()  # self = None
        else:
            event.ignore()

    def initialize_menu_tools(self):
        """placeholder to be superseded by specific method in subclass"""
        pass

    def initialize_interactor(self):
        """placeholder to be superseded by specific method in subclass"""
        pass

    def change_actor_color(self, uid=None, collection=None):
        """placeholder to be superseded by specific method in subclass"""
        pass

    def change_actor_line_thick(self, uid=None, collection=None):
        """placeholder to be superseded by specific method in subclass"""
        pass

    def set_actor_visible(self, uid=None, visible=None):
        """placeholder to be superseded by specific method in subclass"""
        pass

    def show_actor_with_property(self, uid=None, collection=None, show_property=None, visible=None):
        """placeholder to be superseded by specific method in subclass"""
        pass

    def entity_remove_selected(self):
        """Remove entities selected in View"""

        if not self.selected_uids:
            return
        """Confirm removal dialog."""
        check = QMessageBox.question(self, "Remove Entities", ("Do you really want to remove entities\n" + str(self.selected_uids) + "\nPlease confirm."), QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if check == QMessageBox.No:
            return
        """Remove entities."""
        for uid in self.selected_uids:
            if self.actors_df.loc[self.actors_df['uid'] == uid, 'collection'].values[0] == 'geol_coll':
                self.parent.geol_coll.remove_entity(uid=uid)
            elif self.actors_df.loc[self.actors_df['uid'] == uid, 'collection'].values[0] == 'xsect_coll':
                self.parent.xsect_coll.remove_entity(uid=uid)
            elif self.actors_df.loc[self.actors_df['uid'] == uid, 'collection'].values[0] == 'boundary_coll':
                self.parent.boundary_coll.remove_entity(uid=uid)
            elif self.actors_df.loc[self.actors_df['uid'] == uid, 'collection'].values[0] == 'mesh3d_coll':
                self.parent.mesh3d_coll.remove_entity(uid=uid)
            elif self.actors_df.loc[self.actors_df['uid'] == uid, 'collection'].values[0] == 'dom_coll':
                self.parent.dom_coll.remove_entity(uid=uid)
            elif self.actors_df.loc[self.actors_df['uid'] == uid, 'collection'].values[0] == 'image_coll':
                self.parent.image_coll.remove_entity(uid=uid)
            elif self.actors_df.loc[self.actors_df['uid'] == uid, 'collection'].values[0] == 'well_coll':
                self.parent.well_coll.remove_entity(uid=uid)
        """List of selected_uids is cleared"""
        self.selected_uids = []


class View3D(BaseView):
    """Create 3D view and import UI created with Qt Designer by subclassing base view"""
    """parent is the QT object that is launching this one, hence the ProjectWindow() instance in this case"""

    # [Gabriele] Set the default 3D view as x +ve. Maybe there is a better place to put this variable
    # _____________________________________________________________________________________________________________SOLVE THIS
    default_view = [(554532.4159059974, 5063817.5, 0.0),
                    (548273.0, 5063817.5, 0.0),
                    (0.0, 0.0, 1.0)]

    def __init__(self, *args, **kwargs):
        super(View3D, self).__init__(*args, **kwargs)

        self.act_list = []

        """Rename Base View, Menu and Tool"""
        self.setWindowTitle("3D View")
        self.tog_att = -1 #Attitude picker disabled

    """Re-implementations of functions that appear in all views - see placeholders in BaseView()"""
    def show_qt_canvas(self):
        """Show the Qt Window"""
        self.show()
        self.cam_orient_widget.On() # [Gabriele] The orientation widget needs to be turned on AFTER the canvas is shown
        self.plotter.enable_mesh_picking(callback=lambda mesh: self.pkd_mesh(mesh),show_message=False)
    def closeEvent(self, event):
        """Override the standard closeEvent method since self.plotter.close() is needed to cleanly close the vtk plotter."""
        reply = QMessageBox.question(self, 'Closing window', 'Close this window?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.plotter.close()  # needed to cleanly close the vtk plotter
            event.accept()
        else:
            event.ignore()

    def initialize_menu_tools(self):
        """Customize menus and tools for this view"""
        self.menuBaseView.setTitle("Edit")
        self.actionBase_Tool.setText("Edit")

        """Manage home view"""
        self.saveHomeView = QAction("Save home view", self)
        self.saveHomeView.triggered.connect(self.save_home_view)
        self.menuWindow.addAction(self.saveHomeView)

        self.zoomHomeView = QAction("Zoom to home view", self)
        self.zoomHomeView.triggered.connect(self.zoom_home_view)
        self.menuWindow.addAction(self.zoomHomeView)

        self.zoomActive = QAction("Zoom to active", self)
        self.zoomActive.triggered.connect(self.zoom_active)
        self.menuWindow.addAction(self.zoomActive)

        # self.showOct = QAction("Show octree structure", self)
        # self.showOct.triggered.connect(self.show_octree)
        # self.menuWindow.addAction(self.showOct)

        self.menuEdit = QMenu('Edit point cloud',self)
        # self.actionCalculateNormalsPC = QAction('Calculate normals for point clouds',self)
        self.actionNormals2dd = QAction('Convert normals to Dip/Direction',self)
        self.actionNormals2dd.triggered.connect(lambda: self.normals2dd())
        self.actionFilterMenu = QMenu('Filters',self)
        self.actionFilterThresh = QAction('Threshold filter',self)
        self.actionFilterThresh.triggered.connect(lambda: self.thresh_filt())
        self.actionFilterRadial = QAction('Radial filter',self)
        self.actionFilterRadial.triggered.connect(lambda: self.radial_filt())
        self.actionFilterStat = QAction('Statistical outlier filter',self)
        self.actionFilterStat.triggered.connect(lambda: self.stat_filt())


        self.actionFilterMenu.addAction(self.actionFilterThresh)
        # self.actionFilterMenu.addAction(self.actionFilterRadial)
        # self.actionFilterMenu.addAction(self.actionFilterStat)
        self.menuEdit.addAction(self.actionNormals2dd)
        self.menuEdit.addMenu(self.actionFilterMenu)
        self.menuTools.addMenu(self.menuEdit)

        self.menuPicker = QMenu('Pickers',self)

        self.actionPickAttitude = QAction('Toggle measure attitude on a mesh',self)
        self.actionPickAttitude.triggered.connect(lambda: self.act_att())
        self.menuPicker.addAction(self.actionPickAttitude)
        self.actionPickSegm = QAction('Automatic segmentation',self)
        self.actionPickSegm.triggered.connect(lambda: self.act_seg())
        self.menuPicker.addAction(self.actionPickSegm)

        self.actionPickMesh = QAction('Toggle mesh picking',self)
        self.actionPickMesh.triggered.connect(lambda: self.act_pmesh())
        self.menuPicker.addAction(self.actionPickMesh)
        self.menuTools.addMenu(self.menuPicker)

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
        self.plotter.set_background('black')  # background color - could be made interactive in the future
        self.ViewFrameLayout.addWidget(self.plotter.interactor)
        # self.plotter.show_axes_all()
        """Set orientation widget (turned on after the qt canvas is shown)"""
        self.cam_orient_widget = vtkCameraOrientationWidget()
        self.cam_orient_widget.SetParentRenderer(self.plotter.renderer)
        """Set default orientation horizontal because vertical colorbars interfere with the widget."""
        pv_global_theme.colorbar_orientation = 'horizontal'

    #     # [Gabriele] Add picking functionality (this should be put in a menu to enable or disable)
    #
    def act_att(self):

        if self.tog_att == -1:
            input_dict = {'name': ['Set name: ', 'Set_0'], 'geological_type': ['Geological type: ', GeologicalCollection.valid_geological_types]}

            set_opt = multiple_input_dialog(title="Create measure set", input_dict=input_dict)
            self.plotter.enable_point_picking(callback=lambda mesh,pid: self.pkd_point(mesh,pid,set_opt),show_message=False,color='yellow',use_mesh=True)
            self.tog_att *= -1
            print('Picking enabled')
        else:
            # picker = self.plotter.picker
            # #print(picker)
            # picker.RemoveObservers(_vtk.vtkCommand.EndPickEvent)
            self.plotter.disable_picking()
            self.plotter.enable_mesh_picking(callback=lambda mesh: self.pkd_mesh(mesh),show_message=False)
            self.tog_att *= -1
            print('Picking disabled')

    def act_pmesh(self):
        '''[Gabriele] Not the best solution but for now it works'''
        if self.tog_att == -1:
            self.plotter.enable_mesh_picking(callback=lambda mesh: self.pkd_mesh(mesh),show_message=False)
            print('Mesh picking enabled')
        else:
            # picker = self.plotter.picker
            #print(picker)
            # picker.RemoveObservers(_vtk.vtkCommand.EndPickEvent)
            self.plotter.disable_picking()
            self.plotter.enable_mesh_picking(callback=lambda mesh: self.pkd_mesh(mesh),show_message=False)
            self.tog_att *= -1
            print('Picking disabled')

    def pkd_point(self,mesh,pid,set_opt):

        # print(mesh.array_names)

        uid = [i for i in mesh.array_names if 'tag_' in i][0][4:]

        obj = self.parent.dom_coll.get_uid_vtk_obj(uid)
        # locator = vtkStaticPointLocator()
        # locator.SetDataSet(obj)
        # locator.BuildLocator()
        # id_list = vtkIdList()
        # print(center)
        #
        # locator.FindClosestNPoints(30,center,id_list)
        # print(obj.GetPoints().GetPoints(id_list).GetData())
        #
        sph_r = 0.2 #radius of the selection sphere
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
        # print(numpy_support.vtk_to_numpy(extr.GetOutput().GetPointData().GetArray('Normals')))
        points = numpy_support.vtk_to_numpy(extr.GetOutput().GetPoints().GetData())
        plane_c,plane_n = best_fitting_plane(points)


        if plane_n[2]>0: #If Z is positive flip the normals
            plane_n *=-1
        #sel_p = PolyData(points)

        # range = sel_p.points[:,0].max() - sel_p.points[:,0].min()
        # surf = sel_p.reconstruct_surface()
        # norm_mean = np.mean(surf.point_normals,axis=0)
        # std = np.std(surf.cell_normals,axis=0)
        # print(std)
        # if norm_mean[2]<0:
        #     norm_mean *= -1


        # temp_point = PolyData(plane_c)
        # #temp_point['Normals'] = [plane_n]
        # # temp_plane = pvPlane(center=plane_c,direction = plane_n, i_size=dim,j_size=dim,i_resolution=1,j_resolution=1)
        #
        # nx,ny,nz = plane_n
        # dip = np.arccos(nz)
        # dir = angle_wrapper(np.arctan2(nx, ny)-np.deg2rad(90))
        # temp_point['dip'] = [np.rad2deg(dip)]
        # temp_point['dir'] = [np.rad2deg(dir)]



        # print(att_point)

        if set_opt['name'] in self.parent.geol_coll.df['name'].values:
            uid = self.parent.geol_coll.get_name_uid(set_opt['name'])
            old_vtk_obj = self.parent.geol_coll.get_uid_vtk_obj(uid)

            old_vtk_obj.append_point(point_vector=plane_c)
            old_plane_n = old_vtk_obj.get_point_data('Normals')
            old_plane_n = np.append(old_plane_n,plane_n).reshape(-1,3)
            old_vtk_obj.set_point_data('Normals',old_plane_n)
            old_vtk_obj.auto_cells()
            self.parent.geol_coll.replace_vtk(uid,old_vtk_obj,const_color=True)


        else:
            att_point = Attitude()

            att_point.append_point(point_vector=plane_c)
            att_point.auto_cells()

            att_point.init_point_data(data_key='Normals',dimension=3)

            att_point.set_point_data(data_key='Normals',attribute_matrix=plane_n)


            properties_name = att_point.point_data_keys
            properties_components = [att_point.get_point_data_shape(i)[1] for i in properties_name]

            curr_obj_dict = deepcopy(GeologicalCollection.geological_entity_dict)
            curr_obj_dict['uid'] = str(uuid4())
            curr_obj_dict['name'] = set_opt['name']
            curr_obj_dict['geological_type'] = set_opt['geological_type']
            curr_obj_dict['topological_type'] = "VertexSet"
            curr_obj_dict['geological_feature'] = set_opt['name']
            curr_obj_dict['properties_names'] = properties_name
            curr_obj_dict['properties_components'] = properties_components
            curr_obj_dict['vtk_obj'] = att_point
            """Add to entity collection."""
            self.parent.geol_coll.add_entity_from_dict(entity_dict=curr_obj_dict)

            del extr
            del sphere


        #self.plotter.add_mesh(temp_plane,color='r',pickable =False)
        # print(plane)

        # pts = mesh.extract_points(sel_points['SelectedPoints'].view(bool), adjacent_cells=False)
        # pts_act = plt.add_mesh(sel_p,color='r',pickable =False)
        # act_list.append(pts_act)
        # self.act_list.append(actor)

    def pkd_mesh(self,mesh):


        ''' Very basic function to pick a mesh and select the corresponding item
            in the legend. The item is selected by comparing the selected mesh center and boundary with all of the centers and boundaries of the available object.
            THIS IS NOT OPTIMAL FOR LARGE PROJECTS. It could be usefull to calculate
            the parameters at startup (when loading the objects) or when creating new
            objects and save them in a specific file/list.

            Another solution could be to define a new empty attribute called tag_uid that
            is set when a new entity is created. The tag can be extracted when an entity is selected and searched for in the entity list. This way there is no need to compare the centers and boudaries.
            '''
        uid = [i for i in mesh.array_names if 'tag_' in i][0][4:]

        idx = self.actors_df.loc[self.actors_df['uid'] == uid].index[0]
        self.parent.GeologyTableView.selectRow(idx)
        return

    def change_actor_color(self, uid=None, collection=None):
        if collection == 'geol_coll':
            color_R = self.parent.geol_coll.get_uid_legend(uid=uid)['color_R']
            color_G = self.parent.geol_coll.get_uid_legend(uid=uid)['color_G']
            color_B = self.parent.geol_coll.get_uid_legend(uid=uid)['color_B']
        elif collection == 'xsect_coll':
            color_R = self.parent.xsect_coll.get_legend()['color_R']
            color_G = self.parent.xsect_coll.get_legend()['color_G']
            color_B = self.parent.xsect_coll.get_legend()['color_B']
        elif collection == 'boundary_coll':
            color_R = self.parent.boundary_coll.get_legend()['color_R']
            color_G = self.parent.boundary_coll.get_legend()['color_G']
            color_B = self.parent.boundary_coll.get_legend()['color_B']
        elif collection == 'mesh3d_coll':
            color_R = self.parent.mesh3d_coll.get_legend()['color_R']
            color_G = self.parent.mesh3d_coll.get_legend()['color_G']
            color_B = self.parent.mesh3d_coll.get_legend()['color_B']
        elif collection == 'dom_coll':
            color_R = self.parent.dom_coll.get_legend()['color_R']
            color_G = self.parent.dom_coll.get_legend()['color_G']
            color_B = self.parent.dom_coll.get_legend()['color_B']
        elif collection == 'well_coll':
            color_R = self.parent.well_coll.get_uid_legend(uid=uid)['color_R']
            color_G = self.parent.well_coll.get_uid_legend(uid=uid)['color_G']
            color_B = self.parent.well_coll.get_uid_legend(uid=uid)['color_B']
        """Note: no legend for image."""
        """Update color for actor uid"""
        color_RGB = [color_R / 255, color_G / 255, color_B / 255]
        self.actors_df.loc[self.actors_df['uid'] == uid, 'actor'].values[0].GetProperty().SetColor(color_RGB)

    def change_actor_line_thick(self, uid=None, collection=None):
        """Update line thickness for actor uid"""
        if collection == 'geol_coll':
            line_thick = self.parent.geol_coll.get_uid_legend(uid=uid)['line_thick']
            if isinstance(self.parent.geol_coll.get_uid_vtk_obj(uid),VertexSet):
                self.actors_df.loc[self.actors_df['uid'] == uid, 'actor'].values[0].GetProperty().SetPointSize(line_thick)

        elif collection == 'xsect_coll':
            line_thick = self.parent.xsect_coll.get_legend()['line_thick']
        elif collection == 'boundary_coll':
            line_thick = self.parent.boundary_coll.get_legend()['line_thick']
        elif collection == 'mesh3d_coll':
            line_thick = self.parent.mesh3d_coll.get_legend()['line_thick']
        elif collection == 'dom_coll':
            line_thick = self.parent.dom_coll.get_legend()['line_thick']
            """Note: no legend for image."""
            if isinstance(self.parent.dom_coll.get_uid_vtk_obj(uid), PCDom):
                """Use line_thick to set point size here."""
                self.actors_df.loc[self.actors_df['uid'] == uid, 'actor'].values[0].GetProperty().SetPointSize(line_thick)
            else:
                self.actors_df.loc[self.actors_df['uid'] == uid, 'actor'].values[0].GetProperty().SetLineWidth(line_thick)
        elif collection == 'well_coll':
            line_thick = self.parent.well_coll.get_uid_legend(uid=uid)['line_thick']
            self.actors_df.loc[self.actors_df['uid'] == uid, 'actor'].values[0].GetProperty().SetLineWidth(line_thick)

    def set_actor_visible(self, uid=None, visible=None):
        """Set actor uid visible or invisible (visible = True or False)"""
        this_actor = self.actors_df.loc[self.actors_df['uid'] == uid, 'actor'].values[0]
        this_actor.SetVisibility(visible)

    def remove_actor_in_view(self, uid=None, redraw=False):
        """"Remove actor from plotter"""
        """plotter.remove_actor can remove a single entity or a list of entities as actors -> here we remove a single entity"""
        if not self.actors_df.loc[self.actors_df['uid'] == uid].empty:
            this_actor = self.actors_df.loc[self.actors_df['uid'] == uid, 'actor'].values[0]
            success = self.plotter.remove_actor(this_actor)
            self.actors_df.drop(self.actors_df[self.actors_df['uid'] == uid].index, inplace=True)

    def show_actor_with_property(self, uid=None, collection=None, show_property=None, visible=None):
        """Show actor with scalar property (default None)
        https://github.com/pyvista/pyvista/blob/140b15be1d4021b81ded46b1c212c70e86a98ee7/pyvista/plotting/plotting.py#L1045"""
        """First get the vtk object from its collection."""
        show_property_title = show_property
        show_scalar_bar = True
        if collection == 'geol_coll':
            color_R = self.parent.geol_coll.get_uid_legend(uid=uid)['color_R']
            color_G = self.parent.geol_coll.get_uid_legend(uid=uid)['color_G']
            color_B = self.parent.geol_coll.get_uid_legend(uid=uid)['color_B']
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            line_thick = self.parent.geol_coll.get_uid_legend(uid=uid)['line_thick']
            plot_entity = self.parent.geol_coll.get_uid_vtk_obj(uid)
        elif collection == 'xsect_coll':
            color_R = self.parent.xsect_coll.get_legend()['color_R']
            color_G = self.parent.xsect_coll.get_legend()['color_G']
            color_B = self.parent.xsect_coll.get_legend()['color_B']
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            line_thick = self.parent.xsect_coll.get_legend()['line_thick']
            plot_entity = self.parent.xsect_coll.get_uid_vtk_frame(uid)
        elif collection == 'boundary_coll':
            color_R = self.parent.boundary_coll.get_legend()['color_R']
            color_G = self.parent.boundary_coll.get_legend()['color_G']
            color_B = self.parent.boundary_coll.get_legend()['color_B']
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            line_thick = self.parent.boundary_coll.get_legend()['line_thick']
            plot_entity = self.parent.boundary_coll.get_uid_vtk_obj(uid)
        elif collection == 'mesh3d_coll':
            color_R = self.parent.mesh3d_coll.get_legend()['color_R']
            color_G = self.parent.mesh3d_coll.get_legend()['color_G']
            color_B = self.parent.mesh3d_coll.get_legend()['color_B']
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            line_thick = self.parent.mesh3d_coll.get_legend()['line_thick']
            plot_entity = self.parent.mesh3d_coll.get_uid_vtk_obj(uid)
        elif collection == 'dom_coll':
            color_R = self.parent.dom_coll.get_legend()['color_R']
            color_G = self.parent.dom_coll.get_legend()['color_G']
            color_B = self.parent.dom_coll.get_legend()['color_B']
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            line_thick = self.parent.dom_coll.get_legend()['line_thick']
            plot_entity = self.parent.dom_coll.get_uid_vtk_obj(uid)
        elif collection == 'image_coll':
            """Note: no legend for image."""
            color_RGB = [255, 255, 255]
            line_thick = 5.0
            plot_entity = self.parent.image_coll.get_uid_vtk_obj(uid)
        elif collection == 'well_coll':
            color_R = self.parent.well_coll.get_uid_legend(uid=uid)['color_R']
            color_G = self.parent.well_coll.get_uid_legend(uid=uid)['color_G']
            color_B = self.parent.well_coll.get_uid_legend(uid=uid)['color_B']
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            line_thick = self.parent.well_coll.get_uid_legend(uid=uid)['line_thick']
            plot_entity = self.parent.well_coll.get_uid_vtk_obj(uid)
        else:
            print("no collection")
            this_actor = None
        """Then plot the vtk object with proper options."""
        if isinstance(plot_entity, (PolyLine, TriSurf, XsPolyLine)):
            plot_rgb_option = None
            if isinstance(plot_entity.points, np.ndarray):
                """This  check is needed to avoid errors when trying to plot an empty
                PolyData, just created at the beginning of a digitizing session."""
                if show_property is None:
                    show_scalar_bar = False
                    pass
                elif show_property == 'none':
                    show_scalar_bar = False
                    show_property = None
                elif show_property == 'X':
                    show_property = plot_entity.points_X
                elif show_property == 'Y':
                    show_property = plot_entity.points_Y
                elif show_property == 'Z':
                    show_property = plot_entity.points_Z
                else:
                    if plot_entity.get_point_data_shape(show_property)[-1] == 3:
                        plot_rgb_option = True
                this_actor = self.plot_mesh_3D(uid=uid, plot_entity=plot_entity, color_RGB=color_RGB, show_property=show_property, show_scalar_bar=show_scalar_bar,
                                               color_bar_range=None, show_property_title=show_property_title, line_thick=line_thick,
                                               plot_texture_option=False, plot_rgb_option=plot_rgb_option, visible=visible)
            else:
                this_actor = None
        elif isinstance(plot_entity, (VertexSet, XsVertexSet,WellMarker,Attitude)):
            if isinstance(plot_entity, Attitude):
                pickable=False
            else:
                pickable=True
            style = 'points'
            plot_rgb_option = None
            texture=False
            if isinstance(plot_entity.points, np.ndarray):
                """This  check is needed to avoid errors when trying to plot an empty
                PolyData, just created at the beginning of a digitizing session."""
                if show_property is None:
                    show_scalar_bar = False
                    pass
                elif show_property == 'none':
                    show_scalar_bar = False
                    show_property = None
                elif show_property == 'X':
                    show_property = plot_entity.points_X
                elif show_property == 'Y':
                    show_property = plot_entity.points_Y
                elif show_property == 'Z':
                    show_property = plot_entity.points_Z
                elif show_property == 'Normals':
                    # r = self.parent.geol_coll.get_uid_legend(uid=uid)['line_thick']
                    texture = read_texture('pzero/icons/dip.png')
                    disk = pvDisc(outer = 10,inner=0,c_res=30)
                    disk.texture_map_to_plane(inplace=True)
                    show_scalar_bar = False
                    show_property = None

                    show_property_title = 'none'
                    style = 'surface'
                    pv_downcast = pvPolyData()
                    pv_downcast.ShallowCopy(plot_entity)
                    pv_downcast.Modified()

                    # print(pv_downcast['Normals'])
                    plot_entity = pv_downcast.glyph(orient='Normals',geom=disk)
                    # print('Normals not available for now in 3D view')



                else:
                    if plot_entity.get_point_data_shape(show_property)[-1] == 3:
                        plot_rgb_option = True
                this_actor = self.plot_mesh_3D(uid=uid, plot_entity=plot_entity, color_RGB=color_RGB, show_property=show_property, show_scalar_bar=show_scalar_bar,
                                               color_bar_range=None, show_property_title=show_property_title, line_thick=line_thick,
                                               plot_texture_option=texture, plot_rgb_option=plot_rgb_option, visible=visible,
                                               style=style, point_size=line_thick*10.0, points_as_spheres=True, pickable=pickable)
            else:
                this_actor = None
        elif isinstance(plot_entity, DEM):
            """Show texture specified in show_property"""
            if show_property in self.parent.dom_coll.df.loc[self.parent.dom_coll.df['uid'] == uid, "texture_uids"].values[0]:
                active_image = self.parent.image_coll.get_uid_vtk_obj(show_property)
                active_image_texture = active_image.texture
                # active_image_properties_components = active_image.properties_components[0]  # IF USED THIS MUST BE FIXED FOR TEXTURES WITH MORE THAN 3 COMPONENTS
                this_actor = self.plot_mesh_3D(uid=uid, plot_entity=plot_entity, color_RGB=None, show_property=None, show_scalar_bar=None,
                                               color_bar_range=None, show_property_title=None, line_thick=None,
                                               plot_texture_option=active_image_texture, plot_rgb_option=False, visible=visible)
            else:
                plot_rgb_option = None
                if show_property is None:
                    show_scalar_bar = False
                    pass
                elif show_property == 'none':
                    show_scalar_bar = False
                    show_property = None
                elif show_property == 'X':
                    show_property = plot_entity.points_X
                elif show_property == 'Y':
                    show_property = plot_entity.points_Y
                elif show_property == 'Z':
                    show_property = plot_entity.points_Z
                elif show_property == 'RGB':
                    show_scalar_bar = False
                    show_property = None
                else:
                    if plot_entity.get_point_data_shape(show_property)[-1] == 3:
                        plot_rgb_option = True
                this_actor = self.plot_mesh_3D(uid=uid, plot_entity=plot_entity, color_RGB=color_RGB, show_property=show_property, show_scalar_bar=show_scalar_bar,
                                               color_bar_range=None, show_property_title=show_property_title, line_thick=line_thick,
                                               plot_texture_option=False, plot_rgb_option=plot_rgb_option, visible=visible)
        elif isinstance(plot_entity, PCDom):
            plot_rgb_option = None
            # new_plot = pvPointSet()
            # new_plot.ShallowCopy(plot_entity)#this is temporary
            file = self.parent.dom_coll.df.loc[self.parent.dom_coll.df['uid'] == uid, "name"].values[0]
            if isinstance(plot_entity.points, np.ndarray):
                """This check is needed to avoid errors when trying to plot an empty
                PolyData, just created at the beginning of a digitizing session."""
                if show_property is None:
                    show_scalar_bar = False
                    show_property_value = None
                    pass
                elif show_property == 'none':
                    show_scalar_bar = False
                    show_property_value = None
                elif show_property == 'X':
                    show_property_value = plot_entity.points_X
                elif show_property == 'Y':
                    show_property_value = plot_entity.points_Y
                elif show_property == 'Z':
                    show_property_value = plot_entity.points_Z
                elif show_property[-1] == ']':
                    '''[Gabriele] we can identify multicomponents properties such as RGB[0] or Normals[0] by taking the last character of the property name ("]").'''
                    show_scalar_bar = True
                    # [Gabriele] Get the start and end index of the [n_component]
                    pos1 = show_property.index('[')
                    pos2 = show_property.index(']')
                    # [Gabriele] Get the original property (e.g. RGB[0] -> RGB)
                    original_prop = show_property[:pos1]
                    # [Gabriele] Get the column index (the n_component value)
                    index = int(show_property[pos1+1:pos2])
                    show_property_value = plot_entity.get_point_data(original_prop)[:, index]
                else:
                    n_comp = self.parent.dom_coll.get_uid_properties_components(uid)[self.parent.dom_coll.get_uid_properties_names(uid).index(show_property)]
                    '''[Gabriele] Get the n of components for the given property. If it's > 1 then do stuff depending on the type of property (e.g. show_rgb_option -> True if the property is RGB)'''
                    if n_comp > 1:
                        show_property_value= plot_entity.get_point_data(show_property)
                        show_scalar_bar = False
                        # if show_property == 'RGB':
                        plot_rgb_option = True
                    else:
                        show_scalar_bar = True
                        show_property_value = plot_entity.get_point_data(show_property)
            this_actor = self.plot_PC_3D(uid=uid,plot_entity=plot_entity,color_RGB=color_RGB, show_property=show_property_value, show_scalar_bar=show_scalar_bar, color_bar_range=None, show_property_title=show_property_title, plot_rgb_option=plot_rgb_option,visible=visible,point_size=line_thick)

        elif isinstance(plot_entity, (MapImage, XsImage)):
            """Do not plot directly image - it is much slower.
            Texture options according to type."""
            if show_property is None or show_property == 'none':
                plot_texture_option = None
            else:
                plot_texture_option = plot_entity.texture
            this_actor = self.plot_mesh_3D(uid=uid, plot_entity=plot_entity.frame, color_RGB=None, show_property=None, show_scalar_bar=None,
                                           color_bar_range=None, show_property_title=None, line_thick=line_thick,
                                           plot_texture_option=plot_texture_option, plot_rgb_option=False, visible=visible)
        elif isinstance(plot_entity, Seismics):
            plot_rgb_option = None
            if isinstance(plot_entity.points, np.ndarray):
                """This  check is needed to avoid errors when trying to plot an empty
                PolyData, just created at the beginning of a digitizing session."""
                if show_property is None:
                    show_scalar_bar = False
                    pass
                elif show_property == 'none':
                    show_scalar_bar = False
                    show_property = None
                elif show_property == 'X':
                    show_property = plot_entity.points_X
                elif show_property == 'Y':
                    show_property = plot_entity.points_Y
                elif show_property == 'Z':
                    show_property = plot_entity.points_Z
                else:
                    if plot_entity.get_point_data_shape(show_property)[-1] == 3:
                        plot_rgb_option = True
                this_actor = self.plot_mesh_3D(uid=uid, plot_entity=plot_entity, color_RGB=color_RGB, show_property=show_property, show_scalar_bar=show_scalar_bar,
                                               color_bar_range=None, show_property_title=show_property_title, line_thick=line_thick,
                                               plot_texture_option=False, plot_rgb_option=plot_rgb_option, visible=visible)
            else:
                this_actor = None
        elif isinstance(plot_entity, Voxet):
            plot_rgb_option = None
            if plot_entity.cells_number > 0:
                """This  check is needed to avoid errors when trying to plot an empty Voxet."""
                if show_property is None:
                    show_scalar_bar = False
                elif show_property == 'none':
                    show_property = None
                    show_scalar_bar = False
                else:
                    if plot_entity.get_point_data_shape(show_property)[-1] == 3:
                        plot_rgb_option = True
                this_actor = self.plot_mesh_3D(uid=uid, plot_entity=plot_entity, color_RGB=None, show_property=show_property, show_scalar_bar=show_scalar_bar,
                                               color_bar_range=None, show_property_title=show_property_title, line_thick=line_thick,
                                               plot_texture_option=False, plot_rgb_option=plot_rgb_option, visible=visible)
            else:
                this_actor = None
        elif isinstance(plot_entity, Wells):
            plot_rgb_option = None
            if show_property is None:
                show_scalar_bar = False
                pass
            elif show_property == 'none':
                show_scalar_bar = False
                show_property = None
            elif show_property == 'X':
                show_property = plot_entity.points_X
            elif show_property == 'Y':
                show_property = plot_entity.points_Y
            elif show_property == 'Z':
                show_property = plot_entity.points_Z
            else:
                if plot_entity.get_point_data_shape(show_property)[-1] == 3:
                    plot_rgb_option = True
            this_actor = self.plot_mesh_3D(uid=uid, plot_entity=plot_entity, color_RGB=color_RGB, show_property=show_property, show_scalar_bar=show_scalar_bar,
                                           color_bar_range=None, show_property_title=show_property_title, line_thick=line_thick,
                                           plot_texture_option=False, plot_rgb_option=plot_rgb_option, visible=visible,
                                           render_lines_as_tubes=True)
        else:
            print("[Windows factory]: actor with no class")
            this_actor = None
        return this_actor

    def plot_mesh_3D(self, uid=None, plot_entity=None, color_RGB=None, show_property=None, show_scalar_bar=None,
                     color_bar_range=None, show_property_title=None, line_thick=None,
                     plot_texture_option=None, plot_rgb_option=None, visible=None,
                     style='surface', point_size=5.0, points_as_spheres=False,render_lines_as_tubes=False,pickable = True):
        if not self.actors_df.empty:
            """This stores the camera position before redrawing the actor.
            Added to avoid a bug that sometimes sends the scene to a very distant place.
            Could be used as a basis to implement saved views widgets, synced 3D views, etc.
            The is is needed to avoid sending the camera to the origin that is the
            default position before any mesh is plotted."""
            camera_position = self.plotter.camera_position
        if show_property_title is not None and show_property_title != 'none':
            show_property_cmap = self.parent.prop_legend_df.loc[self.parent.prop_legend_df['property_name'] == show_property_title, "colormap"].values[0]
        else:
            show_property_cmap = None
        this_actor = self.plotter.add_mesh(plot_entity,
                                           color=color_RGB,  # string, RGB list, or hex string, overridden if scalars are specified
                                           style=style,  # 'surface' (default), 'wireframe', or 'points'
                                           scalars=show_property,  # str pointing to vtk property or numpy.ndarray
                                           clim=color_bar_range,  # color bar range for scalars, e.g. [-1, 2]
                                           show_edges=None,  # bool
                                           edge_color=None,  # default black
                                           point_size=point_size,  # was 5.0
                                           line_width=line_thick,
                                           opacity=1.0,  # ___________________ single value > uniform opacity. A string can be specified to map the scalars range to opacity.
                                           flip_scalars=False,  # flip direction of cmap
                                           lighting=None,  # bool to enable view-direction lighting
                                           n_colors=256,  # number of colors to use when displaying scalars
                                           interpolate_before_map=True,  # bool for smoother scalars display (default True)
                                           cmap=show_property_cmap,  # ____________________________ name of the Matplotlib colormap, includes 'colorcet' and 'cmocean', and custom colormaps like ['green', 'red', 'blue']
                                           label=None,  # string label for legend with pyvista.BasePlotter.add_legend
                                           reset_camera=None,
                                           scalar_bar_args={'title': show_property_title, 'title_font_size': 10, 'label_font_size': 8, 'shadow': True, 'interactive': True},  # keyword arguments for scalar bar, see pyvista.BasePlotter.add_scalar_bar
                                           show_scalar_bar=show_scalar_bar,  # bool (default True)
                                           multi_colors=False,  # for MultiBlock datasets
                                           name=uid,  # actor name
                                           texture=plot_texture_option,  # ________________________________ vtk.vtkTexture or np.ndarray or boolean, will work if input mesh has texture coordinates. True > first available texture. String > texture with that name already associated to mesh.
                                           render_points_as_spheres=points_as_spheres,
                                           render_lines_as_tubes=render_lines_as_tubes,
                                           smooth_shading=False,
                                           ambient=0.0,
                                           diffuse=1.0,
                                           specular=0.0,
                                           specular_power=100.0,
                                           nan_color=None,  # color to use for all NaN values
                                           nan_opacity=1.0,  # opacity to use for all NaN values
                                           culling=None,  # 'front', 'back', 'false' (default) > does not render faces that are culled
                                           rgb=plot_rgb_option,  # True > plot array values as RGB(A) colors
                                           categories=False,  # True > number of unique values in the scalar used as 'n_colors' argument
                                           use_transparency=False,  # _______________________ invert the opacity mapping as transparency mapping
                                           below_color=None,  # solid color for values below the scalars range in 'clim'
                                           above_color=None,  # solid color for values above the scalars range in 'clim'
                                           annotations=None,  # dictionary of annotations for scale bar witor 'points'h keys = float values and values = string annotations
                                           pickable=pickable,  # bool
                                           preference="point",
                                           log_scale=False)
        if not visible:
            this_actor.SetVisibility(False)
        if not self.actors_df.empty:
            """See above."""
            self.plotter.camera_position = camera_position
        return this_actor

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

    def plot_PC_3D(self, uid=None, plot_entity=None,visible=None, color_RGB=None, show_property=None, show_scalar_bar=None, color_bar_range=None, show_property_title=None, plot_rgb_option=None, point_size=1.0, points_as_spheres=True):
        """[Gabriele]  Plot the point cloud"""
        if not self.actors_df.empty:
            """This stores the camera position before redrawing the actor.
            Added to avoid a bug that sometimes sends the scene to a very distant place.
            Could be used as a basis to implement saved views widgets, synced 3D views, etc.
            The is is needed to avoid sending the camera to the origin that is the
            default position before any mesh is plotted."""
            camera_position = self.plotter.camera_position
        if show_property is not None and plot_rgb_option is None:
            show_property_cmap = self.parent.prop_legend_df.loc[self.parent.prop_legend_df['property_name'] == show_property_title, "colormap"].values[0]
        else:
            show_property_cmap = None
        this_actor= self.plotter.add_points(plot_entity,
                                            name=uid,
                                            style='points',
                                            point_size=point_size,
                                            render_points_as_spheres=points_as_spheres,
                                            color=color_RGB,
                                            scalars=show_property,
                                            n_colors=256,
                                            clim=color_bar_range,
                                            flip_scalars=False,
                                            interpolate_before_map=True,
                                            cmap=show_property_cmap,
                                            scalar_bar_args={'title': show_property_title, 'title_font_size': 20, 'label_font_size': 16, 'shadow': True, 'interactive': True,'vertical':False},
                                            rgb=plot_rgb_option,
                                            show_scalar_bar=show_scalar_bar)
        # self.n_points = plot_entity.GetNumberOfPoints()
        if not visible:
            this_actor.SetVisibility(False)
        if not self.actors_df.empty:
            """See above."""
            self.plotter.camera_position = camera_position
        return this_actor



    def show_octree(self):
        vis_uids =  self.actors_df.loc[self.actors_df['show'] == True,'uid']
        for uid in vis_uids:
            vtk_obj = self.parent.dom_coll.get_uid_vtk_obj(uid)
            oct = PolyData() #[Gabriele] possible recursion problem
            # print(vtk_obj.locator)
            vtk_obj.locator.GenerateRepresentation(3,oct)

            self.plotter.add_mesh(oct,style='wireframe',color='red')




    '''[Gabriele] PC Filters ----------------------------------------------------'''

    def radial_filt(self):
        print('Radial filtering')

    def stat_filt(self):
        print('Statistical outlier filtering')

    def thresh_filt(self):
        uid =  self.actors_df.loc[self.actors_df['show'] == True,'uid'].values[0]
        vtk_obj = self.parent.dom_coll.get_uid_vtk_obj(uid)
        if isinstance(vtk_obj,PCDom):

            input_dict = {'prop_name': ['Select property name: ', vtk_obj.properties_names], 'l_t': ['Lower threshold: ', 0], 'u_t': ['Upper threshold: ', 10]}
            dialog = multiple_input_dialog(title='Threshold filter', input_dict=input_dict)

            thresh = vtkThreshold()
            thresh.SetInputData(vtk_obj)
            thresh.SetInputArrayToProcess(0,0,0,vtkDataObject.FIELD_ASSOCIATION_POINTS,dialog['prop_name'])
            thresh.SetLowerThreshold(float(dialog['l_t']))
            thresh.SetUpperThreshold(float(dialog['u_t']))
            thresh.Update()
            out = PCDom()
            out.ShallowCopy(thresh.GetOutput())
            out.generate_cells()
            # out.plot()
            # self.parent.dom_coll.replace_vtk(uid[0],out)
            entity_dict = deepcopy(self.parent.dom_coll.dom_entity_dict)
            # print(entity_dict)
            entity_dict['name'] = self.parent.dom_coll.get_uid_name(uid) + '_thresh_'+str(dialog['l_t'])+'_'+str(dialog['u_t'])
            entity_dict['vtk_obj'] = out
            entity_dict['dom_type'] = 'PCDom'
            entity_dict['properties_names'] = self.parent.dom_coll.get_uid_properties_names(uid)
            entity_dict['dom_type'] = 'PCDom'
            entity_dict['properties_components'] = self.parent.dom_coll.get_uid_properties_components(uid)
            entity_dict['vtk_obj'] = out
            self.parent.dom_coll.add_entity_from_dict(entity_dict)
            del out
            del thresh

        else:
            print('Entity not point cloud or multiple entities visible')


    def surf_den_filt(self):
        print('Surface density filtering')
    def rough_filt(self):
        print('Roughness filtering')
    def curv_filt(self):
        print('Curvature filtering')
    def manual_filt(self):
        print('Manual filtering')

    def act_seg(self):
        uid =  self.actors_df.loc[self.actors_df['show'] == True,'uid'].values[0]
        vtk_obj = self.parent.dom_coll.get_uid_vtk_obj(uid)
        if isinstance(vtk_obj,PCDom):
            input_dict = {'name': ['Name result: ','segmented_'],'dd1': ['Dip direction lower threshold: ', 0], 'dd2': ['Dip direction upper threshold: ', 10],'d1': ['Dip lower threshold: ', 0], 'd2': ['Dip upper threshold: ', 10], 'rad': ['Search radius: ',0.0],'nn':['Minimum number of neighbors: ',15]}
            dialog = multiple_input_dialog(title='Segmentation filter', input_dict=input_dict)

            # print(dialog)

            vtk_obj.GetPointData().SetActiveScalars('dip direction')
            connectivity_filter_dd = vtkEuclideanClusterExtraction()
            connectivity_filter_dd.SetInputData(vtk_obj)
            connectivity_filter_dd.SetRadius(dialog['rad'])
            connectivity_filter_dd.SetExtractionModeToAllClusters()
            connectivity_filter_dd.ScalarConnectivityOn()
            connectivity_filter_dd.SetScalarRange(dialog['dd1'],dialog['dd2'])
            _update_alg(connectivity_filter_dd,True,'Segmenting on dip directions')
            f1 = connectivity_filter_dd.GetOutput()
            # print(f1)
            f1.GetPointData().SetActiveScalars('dip')
            # print(f1.GetNumberOfPoints())
            #
            connectivity_filter_dip = vtkEuclideanClusterExtraction()
            connectivity_filter_dip.SetInputData(f1)
            connectivity_filter_dip.SetRadius(dialog['rad'])
            connectivity_filter_dip.SetExtractionModeToAllClusters()
            connectivity_filter_dip.ColorClustersOn()
            connectivity_filter_dip.ScalarConnectivityOn()
            connectivity_filter_dip.SetScalarRange(dialog['d1'],dialog['d2'])

            _update_alg(connectivity_filter_dip,True,'Segmenting dips')

            n_clusters = connectivity_filter_dip.GetNumberOfExtractedClusters()

            # print(n_clusters)

            r = vtkRadiusOutlierRemoval()
            r.SetInputData(connectivity_filter_dip.GetOutput())
            r.SetRadius(dialog['rad'])
            r.SetNumberOfNeighbors(dialog['nn'])
            r.GenerateOutliersOff()

            _update_alg(r,True,'Cleaning pc')
            pc_clean = r.GetOutput()
            pc_clean.GetPointData().SetActiveScalars('ClusterId')
            appender = vtkAppendPolyData()
            appender_pc = vtkAppendPolyData()


            for i in range(n_clusters):

                thresh = vtkThresholdPoints()

                thresh.SetInputData(pc_clean)
                thresh.ThresholdBetween(i,i)

                thresh.Update()

                points = numpy_support.vtk_to_numpy(thresh.GetOutput().GetPoints().GetData())
                # print(points)
                if thresh.GetOutput().GetNumberOfPoints() > dialog['nn']:
                    # print(thresh.GetOutput())
                    c,n = best_fitting_plane(points)
                    # n = np.mean(numpy_support.vtk_to_numpy(thresh.GetOutput().GetPointData().GetArray('Normals')),axis=0)
                    # c = np.mean(points,axis=0)
                    if n[0] >= 0:
                        n *= -1
                    # plane = pv.Plane(center = c, direction= n)
                    att_point = Attitude()
                    att_point.append_point(point_vector=c)
                    att_point.auto_cells()
                    att_point.set_point_data(data_key='Normals',attribute_matrix=n)
                    appender.AddInputData(att_point)
                    appender_pc.AddInputData(thresh.GetOutput())
            appender.Update()
            appender_pc.Update()
            points = Attitude()
            points.ShallowCopy(appender.GetOutput())
            properties_name = points.point_data_keys
            properties_components = [points.get_point_data_shape(i)[1] for i in properties_name]



            curr_obj_dict = deepcopy(GeologicalCollection.geological_entity_dict)
            curr_obj_dict['uid'] = str(uuid4())
            curr_obj_dict['name'] = dialog['name']
            curr_obj_dict['geological_type'] = 'undef'
            curr_obj_dict['topological_type'] = "VertexSet"
            curr_obj_dict['geological_feature'] = dialog['name']
            curr_obj_dict['properties_names'] = properties_name
            curr_obj_dict['properties_components'] = properties_components
            curr_obj_dict['vtk_obj'] = points
            """Add to entity collection."""
            self.parent.geol_coll.add_entity_from_dict(entity_dict=curr_obj_dict)

            seg_pc = PCDom()
            seg_pc.ShallowCopy(appender_pc.GetOutput())
            seg_pc.generate_cells()
            properties_name = seg_pc.point_data_keys
            properties_components = [seg_pc.get_point_data_shape(i)[1] for i in properties_name]

            curr_obj_dict = deepcopy(DomCollection.dom_entity_dict)
            curr_obj_dict['uid'] = str(uuid4())
            curr_obj_dict['name'] = f'pc_{dialog["name"]}'
            curr_obj_dict['dom_type'] = "PCDom"
            curr_obj_dict['properties_names'] = properties_name
            curr_obj_dict['properties_components'] = properties_components
            curr_obj_dict['vtk_obj'] = seg_pc
            """Add to entity collection."""
            self.parent.dom_coll.add_entity_from_dict(entity_dict=curr_obj_dict)

            del f1
            del pc_clean
            del seg_pc
            del points
            del properties_name
            del properties_components

        else:
            print('Entity not point cloud or multiple entities visible')

    '''[Gabriele] PC Edit ----------------------------------------------------'''

    def normals2dd(self):
        vis_uids =  self.actors_df.loc[self.actors_df['show'] == True,'uid']
        for uid in vis_uids:
            vtk_obj = self.parent.dom_coll.get_uid_vtk_obj(uid)
            prop_keys = vtk_obj.point_data_keys
            if 'Normals' not in prop_keys:
                print('Normal data not present. Import or create normal data to proceed')
            else:
                # normals = vtk_obj.get_point_data('Normals')
                # nx,ny,nz = normals[:,0],normals[:,1],normals[:,2]
                # dip = np.arccos(np.abs(nz))
                # dir = np.arctan2(nx, ny)-np.deg2rad(90))
                dip = vtk_obj.points_map_dip
                dip_az = vtk_obj.points_map_dip_azimuth

                # print(np.rad2deg(dir))
                vtk_obj.init_point_data('dip',1)
                vtk_obj.init_point_data('dip direction',1)

                vtk_obj.set_point_data('dip',dip)
                vtk_obj.set_point_data('dip direction',np.abs(dip_az))

                self.parent.dom_coll.replace_vtk(uid,vtk_obj)
            # print(normals)
            # normals_neg = np.where(normals[:,2]<0)
            # normals[normals_neg] *= -1
            # for i,normal in enumerate(normals):
            #     center = vtk_obj.points[i]
            #     arrow = pvArrow(center,direction = normal,tip_radius=0.05,shaft_radius=0.025,scale=0.2)
            #     self.plotter.add_mesh(arrow,color='yellow')



            # print(normals)

class View2D(BaseView):
    """Create 2D view and import UI created with Qt Designer by subclassing base view"""
    """parent is the QT object that is launching this one, hence the ProjectWindow() instance in this case"""

    def __init__(self, *args, **kwargs):
        super(View2D, self).__init__(*args, **kwargs)

    """Re-implementations of functions that appear in all views - see placeholders in BaseView()"""

    def initialize_menu_tools(self):
        """Imports for this view."""
        from .two_d_lines import draw_line, edit_line, sort_line_nodes, move_line, rotate_line, extend_line, split_line_line, split_line_existing_point, merge_lines, snap_line, resample_line_distance, resample_line_number_points, simplify_line, copy_parallel, copy_kink, copy_similar, measure_distance
        """Customize menus and tools for this view"""
        self.menuBaseView.setTitle("Edit")
        self.actionBase_Tool.setText("Edit")

        self.removeEntityButton = QAction('Remove Entity', self)  # create action
        self.removeEntityButton.triggered.connect(self.entity_remove_selected)  # connect action to function
        self.menuBaseView.addAction(self.removeEntityButton)  # add action to menu
        self.toolBarBase.addAction(self.removeEntityButton)  # add action to toolbar

        self.drawLineButton = QAction('Draw line', self)  # create action
        self.drawLineButton.triggered.connect(lambda: draw_line(self))  # connect action to function with additional argument parent
        self.menuBaseView.addAction(self.drawLineButton)  # add action to menu
        self.toolBarBase.addAction(self.drawLineButton)  # add action to toolbar

        self.selectLineButton = QAction('Select line', self)  # create action
        self.selectLineButton.triggered.connect(self.select_actor_with_mouse)  # connect action to function
        self.menuBaseView.addAction(self.selectLineButton)  # add action to menu
        self.toolBarBase.addAction(self.selectLineButton)  # add action to toolbar

        self.clearSelectionButton = QAction('Clear Selection', self)  # create action
        self.clearSelectionButton.triggered.connect(self.clear_selection)  # connect action to function
        self.menuBaseView.addAction(self.clearSelectionButton)  # add action to menu
        self.toolBarBase.addAction(self.clearSelectionButton)  # add action to toolbar

        self.editLineButton = QAction('Edit line', self)  # create action
        self.editLineButton.triggered.connect(lambda: edit_line(self))  # connect action to function
        self.menuBaseView.addAction(self.editLineButton)  # add action to menu
        self.toolBarBase.addAction(self.editLineButton)  # add action to toolbar

        self.sortLineButton = QAction('Sort line nodes', self)  # create action
        self.sortLineButton.triggered.connect(lambda: sort_line_nodes(self))  # connect action to function
        self.menuBaseView.addAction(self.sortLineButton)  # add action to menu
        self.toolBarBase.addAction(self.sortLineButton)  # add action to toolbar

        self.moveLineButton = QAction('Move line', self)  # create action
        self.moveLineButton.triggered.connect(lambda: move_line(self))  # connect action to function
        self.menuBaseView.addAction(self.moveLineButton)  # add action to menu
        self.toolBarBase.addAction(self.moveLineButton)  # add action to toolbar

        self.rotateLineButton = QAction('Rotate line', self)  # create action
        self.rotateLineButton.triggered.connect(lambda: rotate_line(self))  # connect action to function
        self.menuBaseView.addAction(self.rotateLineButton)  # add action to menu
        self.toolBarBase.addAction(self.rotateLineButton)  # add action to toolbar

        self.extendButton = QAction('Extend line', self)  # create action
        self.extendButton.triggered.connect(lambda: extend_line(self))  # connect action to function
        self.menuBaseView.addAction(self.extendButton)  # add action to menu
        self.toolBarBase.addAction(self.extendButton)  # add action to toolbar

        self.splitLineByLineButton = QAction('Split line-line', self)  # create action
        self.splitLineByLineButton.triggered.connect(lambda: split_line_line(self))  # connect action to function
        self.menuBaseView.addAction(self.splitLineByLineButton)  # add action to menu
        self.toolBarBase.addAction(self.splitLineByLineButton)  # add action to toolbar

        self.splitLineByPointButton = QAction('Split line-point', self)  # create action
        self.splitLineByPointButton.triggered.connect(lambda: split_line_existing_point(self))  # connect action to function
        self.menuBaseView.addAction(self.splitLineByPointButton)  # add action to menu
        self.toolBarBase.addAction(self.splitLineByPointButton)  # add action to toolbar

        self.mergeLineButton = QAction('Merge lines', self)  # create action
        self.mergeLineButton.triggered.connect(lambda: merge_lines(self))  # connect action to function
        self.menuBaseView.addAction(self.mergeLineButton)  # add action to menu
        self.toolBarBase.addAction(self.mergeLineButton)  # add action to toolbar

        self.snapLineButton = QAction('Snap line', self)  # create action
        self.snapLineButton.triggered.connect(lambda: snap_line(self))  # connect action to function
        self.menuBaseView.addAction(self.snapLineButton)  # add action to menu
        self.toolBarBase.addAction(self.snapLineButton)  # add action to toolbar

        self.resampleDistanceButton = QAction('Resample distance', self)  # create action
        self.resampleDistanceButton.triggered.connect(lambda: resample_line_distance(self))  # connect action to function
        self.menuBaseView.addAction(self.resampleDistanceButton)  # add action to menu
        self.toolBarBase.addAction(self.resampleDistanceButton)  # add action to toolbar

        self.resampleNumberButton = QAction('Resample number', self)  # create action
        self.resampleNumberButton.triggered.connect(lambda: resample_line_number_points(self))  # connect action to function
        self.menuBaseView.addAction(self.resampleNumberButton)  # add action to menu
        self.toolBarBase.addAction(self.resampleNumberButton)  # add action to toolbar

        self.simplifyButton = QAction('Simplify line', self)  # create action
        self.simplifyButton.triggered.connect(lambda: simplify_line(self))  # connect action to function
        self.menuBaseView.addAction(self.simplifyButton)  # add action to menu
        self.toolBarBase.addAction(self.simplifyButton)  # add action to toolbar

        self.copyParallelButton = QAction('Copy parallel', self)  # create action
        self.copyParallelButton.triggered.connect(lambda: copy_parallel(self))  # connect action to function
        self.menuBaseView.addAction(self.copyParallelButton)  # add action to menu
        self.toolBarBase.addAction(self.copyParallelButton)  # add action to toolbar

        self.copyKinkButton = QAction('Copy kink', self)  # create action
        self.copyKinkButton.triggered.connect(lambda: copy_kink(self))  # connect action to function
        self.menuBaseView.addAction(self.copyKinkButton)  # add action to menu
        self.toolBarBase.addAction(self.copyKinkButton)  # add action to toolbar

        self.copySimilarButton = QAction('Copy similar', self)  # create action
        self.copySimilarButton.triggered.connect(lambda: copy_similar(self))  # connect action to function
        self.menuBaseView.addAction(self.copySimilarButton)  # add action to menu
        self.toolBarBase.addAction(self.copySimilarButton)  # add action to toolbar

        self.measureDistanceButton = QAction('Measure', self)  # create action
        self.measureDistanceButton.triggered.connect(lambda: measure_distance(self))  # connect action to function
        self.menuBaseView.addAction(self.measureDistanceButton)  # add action to menu
        self.toolBarBase.addAction(self.measureDistanceButton)  # add action to toolbar

    def initialize_interactor(self):
        """Initialize parameters for mouse interaction functions."""
        self.pick_with_mouse_U_data = 0
        self.pick_with_mouse_V_data = 0
        self.pick_with_mouse_U_pixels = 0
        self.pick_with_mouse_V_pixels = 0
        self.pick_with_mouse_button = None
        self.vector_by_mouse_dU = 0
        self.vector_by_mouse_dV = 0
        self.vector_by_mouse_length = 0
        self.vector_by_mouse_azimuth = 0
        """Initialize some other variable"""
        # self.current_line = None
        self.vertex_ind = None
        self.press = None
        self.dU = 0.0
        self.dV = 0.0
        self.Us = []
        self.Vs = []
        """Create Matplotlib canvas, figure and navi_toolbar"""
        self.figure = Figure()  # create a Matplotlib figure; this implicitly creates also the canvas to contain the figure
        self.canvas = FigureCanvas(self.figure)  # get a reference to the canvas that contains the figure
        # print("dir(self.canvas):\n", dir(self.canvas))
        """https://doc.qt.io/qt-5/qsizepolicy.html"""
        self.navi_toolbar = NavigationToolbar(self.canvas, self)  # create a navi_toolbar with the matplotlib.backends.backend_qt5agg method NavigationToolbar
        """Create Qt layout and add Matplotlib canvas, figure and navi_toolbar"""
        self.ViewFrameLayout.addWidget(self.canvas)  # add Matplotlib canvas (created above) as a widget to the Qt layout
        self.ViewFrameLayout.addWidget(self.navi_toolbar)  # add navigation navi_toolbar (created above) to the layout
        """Get reference to figure axes (Matplotlib)"""
        self.ax = self.figure.gca()  # create reference to plt figure axes gca() = "get current axes"
        """Set properties of figure and axes (Matplotlib)
        IN THE FUTURE SOLVE PROBLEMS WITH AXES NOT FILLING THE WHOLE CANVAS________"""
        figure_size = self.figure.get_size_inches() * self.figure.dpi
        self.base_font_size = int(figure_size[1] / 36)
        # self.ax.set(xlim=(0.0, 3000.0), ylim=(0.0, 1000.0))  # set W limit
        # self.ax.autoscale(enable=True, axis='both', tight=True)  # check autoscale ________________________________________________________________________________________
        self.ax.set_aspect(1.0)  # set axis aspect ratio such as height is 1 times the width. aspect=1 is the same as aspect=’equal’. vertical exaggeration is 1
        self.ax.grid(color='gray', linestyle=':', linewidth=0.5)  # turn on the grid
        self.figure.tight_layout(pad=1)  # tight layout
        # self.figure.set_tight_layout(True)
        # self.ax.use_sticky_edges = False  # https://matplotlib.org/stable/gallery/subplots_axes_and_figures/axes_margins.html
        # self.figure.set_constrained_layout(True)
        """Create container for text messages at the base of the canvas."""
        """SEND THIS TO STATUS BAR IN THE FUTURE?_____________"""
        self.text_msg = self.ax.add_artist(TextArea("some text", textprops=dict(fontsize=int(self.base_font_size), color="crimson")))
        self.text_msg.set_offset((int(self.base_font_size * .4), int(self.base_font_size * .4)))
        self.text_msg.set_text("message box")

    def change_actor_color(self, uid=None, collection=None):
        """Update color for actor uid"""
        if collection == 'geol_coll':
            color_R = self.parent.geol_coll.get_uid_legend(uid=uid)['color_R']
            color_G = self.parent.geol_coll.get_uid_legend(uid=uid)['color_G']
            color_B = self.parent.geol_coll.get_uid_legend(uid=uid)['color_B']
        elif collection == 'xsect_coll':
            color_R = self.parent.xsect_coll.get_legend()['color_R']
            color_G = self.parent.xsect_coll.get_legend()['color_G']
            color_B = self.parent.xsect_coll.get_legend()['color_B']
        elif collection == 'boundary_coll':
            color_R = self.parent.boundary_coll.get_legend()['color_R']
            color_G = self.parent.boundary_coll.get_legend()['color_G']
            color_B = self.parent.boundary_coll.get_legend()['color_B']
        elif collection == 'mesh3d_coll':
            color_R = self.parent.mesh3d_coll.get_legend()['color_R']
            color_G = self.parent.mesh3d_coll.get_legend()['color_G']
            color_B = self.parent.mesh3d_coll.get_legend()['color_B']
        elif collection == 'dom_coll':
            color_R = self.parent.dom_coll.get_legend()['color_R']
            color_G = self.parent.dom_coll.get_legend()['color_G']
            color_B = self.parent.dom_coll.get_legend()['color_B']
        """Note: no legend for image."""
        color_RGB = [color_R / 255, color_G / 255, color_B / 255]
        if isinstance(self.actors_df.loc[self.actors_df['uid'] == uid, 'actor'].values[0], Line2D):
            "Case for Line2D"
            self.actors_df.loc[self.actors_df['uid'] == uid, 'actor'].values[0].set_color(color_RGB)
            self.actors_df.loc[self.actors_df['uid'] == uid, 'actor'].values[0].figure.canvas.draw()
        elif isinstance(self.actors_df.loc[self.actors_df['uid'] == uid, 'actor'].values[0], PathCollection):
            "Case for PathCollection -> ax.scatter"
            pass
        elif isinstance(self.actors_df.loc[self.actors_df['uid'] == uid, 'actor'].values[0], TriContourSet):
            "Case for TriContourSet -> ax.tricontourf"
            pass
        else:
            "Do-nothing option to avoid errors, but it does not update color."
            pass

    def change_actor_line_thick(self, uid=None, collection=None):
        """Update line thickness for actor uid"""
        if collection == 'geol_coll':
            line_thick = self.parent.geol_coll.get_uid_legend(uid=uid)['line_thick']
        elif collection == 'xsect_coll':
            line_thick = self.parent.xsect_coll.get_legend()['line_thick']
        elif collection == 'boundary_coll':
            line_thick = self.parent.boundary_coll.get_legend()['line_thick']
        elif collection == 'mesh3d_coll':
            line_thick = self.parent.mesh3d_coll.get_legend()['line_thick']
        elif collection == 'dom_coll':
            line_thick = self.parent.dom_coll.get_legend()['line_thick']
        else:
            return
        """Note: no legend for image."""
        if isinstance(self.actors_df.loc[self.actors_df['uid'] == uid, 'actor'].values[0], Line2D):
            "Case for Line2D"
            self.actors_df.loc[self.actors_df['uid'] == uid, 'actor'].values[0].set_linewidth(line_thick)
            self.actors_df.loc[self.actors_df['uid'] == uid, 'actor'].values[0].figure.canvas.draw()
        elif isinstance(self.actors_df.loc[self.actors_df['uid'] == uid, 'actor'].values[0], PathCollection):
            "Case for PathCollection -> ax.scatter"
            pass
        elif isinstance(self.actors_df.loc[self.actors_df['uid'] == uid, 'actor'].values[0], TriContourSet):
            "Case for TriContourSet -> ax.tricontourf"
            pass
        else:
            "Do-nothing option to avoid errors, but it does not update color."
            pass

    def set_actor_visible(self, uid=None, visible=None):
        """Set actor uid visible or invisible (visible = True or False)"""
        if isinstance(self.actors_df.loc[self.actors_df['uid'] == uid, 'actor'].values[0], Line2D):
            "Case for Line2D"
            self.actors_df.loc[self.actors_df['uid'] == uid, 'actor'].values[0].set_visible(visible)
            self.actors_df.loc[self.actors_df['uid'] == uid, 'actor'].values[0].figure.canvas.draw()
        elif isinstance(self.actors_df.loc[self.actors_df['uid'] == uid, 'actor'].values[0], PathCollection):
            "Case for PathCollection -> ax.scatter"
            pass
        elif isinstance(self.actors_df.loc[self.actors_df['uid'] == uid, 'actor'].values[0], TriContourSet):
            "Case for TriContourSet -> ax.tricontourf"
            pass
        elif isinstance(self.actors_df.loc[self.actors_df['uid'] == uid, 'actor'].values[0], AxesImage):
            "Case for AxesImage (i.e. images)"
            """Hide other images if (1) they are shown and (2) you are showing another one."""
            for hide_uid in self.actors_df.loc[(self.actors_df['collection'] == 'image_coll') & (self.actors_df['show']) & (self.actors_df['uid'] != uid), 'uid'].to_list():
                self.actors_df.loc[self.actors_df['uid'] == hide_uid, 'show'] = False
                self.actors_df.loc[self.actors_df['uid'] == hide_uid, 'actor'].values[0].set_visible(False)
                row = self.ImagesTableWidget.findItems(hide_uid, Qt.MatchExactly)[0].row()
                self.ImagesTableWidget.item(row, 0).setCheckState(Qt.Unchecked)
            """Then show this one."""
            self.actors_df.loc[self.actors_df['uid'] == uid, 'actor'].values[0].set_visible(visible)
            self.actors_df.loc[self.actors_df['uid'] == uid, 'actor'].values[0].figure.canvas.draw()
        else:
            "Do-nothing option to avoid errors, but it does not set/unset visibility."
            pass

    def remove_actor_in_view(self, uid=None, redraw=False):
        """"Remove actor from plotter"""
        """Can remove a single entity or a list of entities as actors - here we remove a single entity"""
        if not self.actors_df.loc[self.actors_df['uid'] == uid].empty:
            if self.actors_df.loc[self.actors_df['uid'] == uid, 'actor'].values[0]:
                self.actors_df.loc[self.actors_df['uid'] == uid, 'actor'].values[0].remove()
                self.actors_df.drop(self.actors_df[self.actors_df['uid'] == uid].index, inplace=True)
            if redraw:
                """IN THE FUTURE check if there is a way to redraw just the actor that has just been removed."""
                self.figure.canvas.draw()
                print("redraw all - a more efficient alternative should be found")

    def show_actor_with_property(self, uid=None, collection=None, show_property=None, visible=None):
        """placeholder to be superseded by specific method in subclass"""
        pass

    """Graphic inputs and interactions."""

    def stop_event_loops(self):
        """Terminate running event loops"""
        self.figure.canvas.stop_event_loop()

    def select_actor_with_mouse(self):
        """Select a line with mouse click."""
        self.stop_event_loops()
        self.clear_selection()

        def select_actor_pick(event):
            while self.selected_uids == []:
                if event.artist:
                    if self.actors_df.loc[self.actors_df['actor'] == event.artist, 'collection'].values[0] == 'geol_coll':
                        """IN THE FUTURE check why the condition above rises an error, but then the code runs flawlessly."""
                        uid = self.actors_df.loc[self.actors_df['actor'] == event.artist, 'uid'].values[0]
                        if self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0] == True:
                            self.selected_uids = [uid]
                            self.parent.geology_geom_modified_signal.emit([uid])  # emit uid as list to force redraw
                        elif self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0] == False:
                            return
                    else:
                        return
            event.canvas.mpl_disconnect(self.cid_select)
            self.figure.canvas.stop_event_loop()

        self.canvas.setFocusPolicy(Qt.ClickFocus)
        self.canvas.setFocus()
        self.cid_select = self.canvas.mpl_connect('pick_event', select_actor_pick)  # connects to callback function. cid is just an integer id
        self.figure.canvas.start_event_loop(timeout=-1)

    def pick_with_mouse(self):
        """Pick one point and read coordinates and mouse button. Pick with_mouse abbreviated to PWM in inner functions."""
        """I have added a lot of try/except to handle scattered errors that are probably related to some interaction
        between mouse callbacks and events (particularly event.button) in pick_with_mouse and vector_by_mouse"""
        """_______I would like to make all other temporary variables private to this function and its sub-functions but I still don't know how_______"""
        self.pick_with_mouse_U_data = 0
        self.pick_with_mouse_V_data = 0
        self.pick_with_mouse_U_pixels = 0
        self.pick_with_mouse_V_pixels = 0
        self.pick_with_mouse_button = None
        self.pick_with_mouse_key = None

        def pwm_press_callback(event):
            """This is activated when a mouse button is pressed within the axes."""
            if event.inaxes is None:  # Escape if button is pressed outside axes
                return
            try:
                self.pick_with_mouse_U_data = event.xdata
                self.pick_with_mouse_V_data = event.ydata
                self.pick_with_mouse_U_pixels = event.x
                self.pick_with_mouse_V_pixels = event.y
                self.pick_with_mouse_button = event.button
                event.canvas.mpl_disconnect(self.cid_pwm_1)
                event.canvas.mpl_disconnect(self.cid_pwm_2)
                event.canvas.mpl_disconnect(self.cid_pwm_3)
                event.canvas.mpl_disconnect(self.cid_pwm_4)
                self.text_msg.set_text("x: {0:.2f} y: {1:.2f} x: {2:d} y: {3:d} btn: {4:d}".format(self.pick_with_mouse_U_data, self.pick_with_mouse_V_data, self.pick_with_mouse_U_pixels, self.pick_with_mouse_V_pixels, self.pick_with_mouse_button))
                self.figure.canvas.stop_event_loop()
            except:
                return

        def pwm_motion_callback(event):
            """For some reason, having press, motion and release callbacks also here, and closing them at the end, reduces
            the errors in vector_by_mouse. Probably there is some garbage collection going on between these callbacks,
            but it is difficult to solve."""
            pass

        def pwm_release_callback(event):
            """See pwm_motion_callback."""
            pass

        def pwm_key_callback(event):
            """This is activated when a keyboard button is pressed."""
            try:
                self.pick_with_mouse_key = event.key
                event.canvas.mpl_disconnect(self.cid_pwm_1)
                event.canvas.mpl_disconnect(self.cid_pwm_2)
                event.canvas.mpl_disconnect(self.cid_pwm_3)
                event.canvas.mpl_disconnect(self.cid_pwm_4)
                self.figure.canvas.stop_event_loop()
            except:
                return

        self.canvas.setFocusPolicy(Qt.ClickFocus)
        self.canvas.setFocus()
        self.cid_pwm_1 = self.canvas.mpl_connect('button_press_event', pwm_press_callback)
        self.cid_pwm_2 = self.canvas.mpl_connect('motion_notify_event', pwm_motion_callback)
        self.cid_pwm_3 = self.canvas.mpl_connect('button_release_event', pwm_release_callback)
        self.cid_pwm_4 = self.canvas.mpl_connect('key_release_event', pwm_key_callback)
        self.figure.canvas.start_event_loop(timeout=-1)

    def vector_by_mouse(self, verbose=False):
        """Get a vector by left-click and drag. Any other click does nothing. Vector_by_mouse abbreviated to VBM in inner functions."""
        """self.temp_vbm_line is a temporary Line2D, added to self.ax and removed when completing this function."""
        """I have added a lot of try/except to handle scattered errors that are probably related to some interaction
        between mouse callbacks and events (particularly event.button) in pick_with_mouse and vector_by_mouse"""
        """_______I would like to make all other temporary variables private to this function and its sub-functions but I still don't know how_______"""
        self.vector_by_mouse_dU = 0
        self.vector_by_mouse_dV = 0
        self.vector_by_mouse_length = 0
        self.vector_by_mouse_azimuth = 0
        self.temp_vbm_line, = self.ax.plot([], [], color='red')
        self.temp_vbm_line.set_linewidth(3)
        self.temp_vbm_line.set_marker('o')

        def vbm_press_callback(event):
            """This is activated when left mouse button is pressed within the axes."""
            if event.inaxes is None:  # Escape if button is pressed outside axes
                return
            if event.button != 1:  # Escape if button different from left is pressed
                try:
                    event.canvas.mpl_disconnect(self.cid_vbm_1)
                    event.canvas.mpl_disconnect(self.cid_vbm_2)
                    event.canvas.mpl_disconnect(self.cid_vbm_3)
                    event.button = None
                    self.figure.canvas.stop_event_loop()
                    return
                except:
                    return
            if event.button == 1:  # Get start point at left-click
                try:
                    self.temp_vbm_U0 = event.xdata
                    self.temp_vbm_V0 = event.ydata
                    self.vbm_U0 = event.xdata # save initial X data
                    self.vbm_V0 = event.ydata # save initial Y data
                except:
                    return

        def vbm_motion_callback(event):
            """This is activated during mouse movement on axes, if left button is pressed and a vertex index is selected."""
            if event.inaxes is None:  # Escape if button pressed outside axes
                return
            if event.button != 1:  # Escape if button pressed is not left (= 1)
                return
            if event.button == 1:  # Do this only if left button is pressed (= 1)
                try:
                    self.vbm_Uf = event.xdata # save final X data
                    self.vbm_Vf = event.ydata # save final Y data
                    self.temp_vbm_dU = event.xdata - self.temp_vbm_U0
                    self.temp_vbm_dV = event.ydata - self.temp_vbm_V0
                    self.temp_vbm_length = sqrt(self.temp_vbm_dU ** 2 + self.temp_vbm_dV ** 2)
                    self.temp_vbm_azimuth = degrees(atan2(self.temp_vbm_dU, self.temp_vbm_dV))
                    self.temp_vbm_line.set_data([self.temp_vbm_U0, event.xdata], [self.temp_vbm_V0, event.ydata])
                    self.temp_vbm_line.figure.canvas.draw()  # ________________WE NEED SOMETHING HERE TO SHOW THESE VALUES IN REAL TIME____________________________________________  # self.text_msg.set_text("dU: {0:.2f} dV: {1:.2f} length: {2:d} azimuth: {3:d}".format(self.temp_vbm_dU,  #                                                                                     self.temp_vbm_dV,  #                                                                                     self.temp_vbm_length,  #                                                                                     self.temp_vbm_azimuth))
                except:
                    return

        def vbm_release_callback(event):
            """This clears temporary variables and returns the vector as:
            self.vector_by_mouse_dU
            self.vector_by_mouse_dV
            self.vector_by_mouse_length
            self.vector_by_mouse_azimuth"""
            if event.inaxes is None:  # Escape if button pressed outside axes
                return
            if event.button != 1:  # Escape if button pressed is not left (= 1)
                return
            if event.button == 1:  # Do this only if left button is pressed (= 1)
                try:
                    event.canvas.mpl_disconnect(self.cid_vbm_1)
                    event.canvas.mpl_disconnect(self.cid_vbm_2)
                    event.canvas.mpl_disconnect(self.cid_vbm_3)
                    event.button = None
                    self.vector_by_mouse_dU = self.temp_vbm_dU
                    self.vector_by_mouse_dV = self.temp_vbm_dV
                    self.vector_by_mouse_length = self.temp_vbm_length
                    self.vector_by_mouse_azimuth = self.temp_vbm_azimuth
                    if self.vector_by_mouse_azimuth < 0:  # convert azimuth to 0-360 degrees range
                        self.vector_by_mouse_azimuth = self.vector_by_mouse_azimuth + 360
                    self.temp_vbm_dU = None
                    self.temp_vbm_dV = None
                    self.temp_vbm_U0 = None
                    self.temp_vbm_V0 = None
                    self.temp_vbm_line.remove()
                    self.figure.canvas.draw()  ## ___________________________ here we must find a way to remove the temp vector without redrawing the whole canvas
                    self.text_msg.set_text("dU: {0:.2f} dV: {1:.2f} length: {2:.2f} azimuth: {3:.2f}".format(self.vector_by_mouse_dU, self.vector_by_mouse_dV, self.vector_by_mouse_length, self.vector_by_mouse_azimuth))
                    self.figure.canvas.stop_event_loop()
                except:
                    return

        self.cid_vbm_1 = self.canvas.mpl_connect('button_press_event', vbm_press_callback)
        self.cid_vbm_2 = self.canvas.mpl_connect('motion_notify_event', vbm_motion_callback)
        self.cid_vbm_3 = self.canvas.mpl_connect('button_release_event', vbm_release_callback)
        self.figure.canvas.start_event_loop(timeout=-1)

    def clear_selection(self):
        """Clear all possible selected elements in view. Resets selection."""
        if not self.selected_uids == []:
            deselected_uids = self.selected_uids
            self.selected_uids = []
            self.parent.geology_geom_modified_signal.emit(deselected_uids)  # emit uid as list to force redraw

    """"_______________________________________________________________________________"""


class ViewMap(View2D):
    """Create map view and import UI created with Qt Designer by subclassing base view"""
    """parent is the QT object that is launching this one, hence the ProjectWindow() instance in this case"""

    def __init__(self, *args, **kwargs):
        super(ViewMap, self).__init__(*args, **kwargs)

        """Rename Base View, Menu and Tool"""
        self.setWindowTitle("Map View")
        self.ax.set_title("Map", fontsize=self.base_font_size)  # set title _____________________________________________________UPDATE
        self.ax.set_xlabel("X [m]", fontsize=int(self.base_font_size * .8))  # set label for W coordinate
        self.ax.set_ylabel("Y [m]", fontsize=int(self.base_font_size * .8))  # set label for Z coordinate

    """Re-implementations of functions that appear in all views - see placeholders in BaseView()"""
    """NONE AT THE MOMENT"""

    """Implementation of functions specific to 2D views"""

    def initialize_menu_tools(self):
        """Inheritance of common tools"""
        super().initialize_menu_tools()
        """Tools specific to map view"""
        from .xsection_collection import section_from_azimuth, section_from_points, sections_from_file
        from .boundary_collection import boundary_from_points

        self.sectionFromAzimuthButton = QAction('Section from Azimuth', self)  # create action
        self.sectionFromAzimuthButton.triggered.connect(lambda: section_from_azimuth(self))  # connect action to function with additional argument parent
        self.menuBaseView.addAction(self.sectionFromAzimuthButton)  # add action to menu
        self.toolBarBase.addAction(self.sectionFromAzimuthButton)  # add action to toolbar

        self.sectionFromPointsButton = QAction('Section from 2 points', self)  # create action
        self.sectionFromPointsButton.triggered.connect(lambda: section_from_points(self))  # connect action to function with additional argument parent
        self.menuBaseView.addAction(self.sectionFromPointsButton)  # add action to menu
        self.toolBarBase.addAction(self.sectionFromPointsButton)  # add action to toolbar

        self.sectionFromFileButton = QAction('Sections from file', self)
        self.sectionFromFileButton.triggered.connect(lambda: sections_from_file(self))

        self.menuBaseView.addAction(self.sectionFromFileButton)  # add action to menu
        self.toolBarBase.addAction(self.sectionFromFileButton)  # add action to toolbar

        self.boundaryFromPointsButton = QAction('Boundary from 2 points', self)  # create action
        self.boundaryFromPointsButton.triggered.connect(lambda: boundary_from_points(self))  # connect action to function with additional argument parent
        self.menuBaseView.addAction(self.boundaryFromPointsButton)  # add action to menu
        self.toolBarBase.addAction(self.boundaryFromPointsButton)  # add action to toolbar

    def show_actor_with_property(self, uid=None, collection=None, show_property=None, visible=None):
        """Show actor with scalar property (default None)
        https://github.com/pyvista/pyvista/blob/140b15be1d4021b81ded46b1c212c70e86a98ee7/pyvista/plotting/plotting.py#L1045"""
        """First get entity from collection."""
        if collection == 'geol_coll':
            color_R = self.parent.geol_coll.get_uid_legend(uid=uid)['color_R']
            color_G = self.parent.geol_coll.get_uid_legend(uid=uid)['color_G']
            color_B = self.parent.geol_coll.get_uid_legend(uid=uid)['color_B']
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            line_thick = self.parent.geol_coll.get_uid_legend(uid=uid)['line_thick']
            plot_entity = self.parent.geol_coll.get_uid_vtk_obj(uid)
        elif collection == 'xsect_coll':
            color_R = self.parent.xsect_coll.get_legend()['color_R']
            color_G = self.parent.xsect_coll.get_legend()['color_G']
            color_B = self.parent.xsect_coll.get_legend()['color_B']
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            line_thick = self.parent.xsect_coll.get_legend()['line_thick']
            plot_entity = self.parent.xsect_coll.get_uid_vtk_frame(uid)
        elif collection == 'boundary_coll':
            color_R = self.parent.boundary_coll.get_legend()['color_R']
            color_G = self.parent.boundary_coll.get_legend()['color_G']
            color_B = self.parent.boundary_coll.get_legend()['color_B']
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            line_thick = self.parent.boundary_coll.get_legend()['line_thick']
            plot_entity = self.parent.boundary_coll.get_uid_vtk_obj(uid)
        elif collection == 'mesh3d_coll':
            color_R = self.parent.mesh3d_coll.get_legend()['color_R']
            color_G = self.parent.mesh3d_coll.get_legend()['color_G']
            color_B = self.parent.mesh3d_coll.get_legend()['color_B']
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            line_thick = self.parent.mesh3d_coll.get_legend()['line_thick']
            plot_entity = self.parent.mesh3d_coll.get_uid_vtk_obj(uid)
        elif collection == 'dom_coll':
            color_R = self.parent.dom_coll.get_legend()['color_R']
            color_G = self.parent.dom_coll.get_legend()['color_G']
            color_B = self.parent.dom_coll.get_legend()['color_B']
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            line_thick = self.parent.dom_coll.get_legend()['line_thick']
            plot_entity = self.parent.dom_coll.get_uid_vtk_obj(uid)
        elif collection == 'image_coll':
            color_R = self.parent.image_coll.get_legend()['color_R']
            color_G = self.parent.image_coll.get_legend()['color_G']
            color_B = self.parent.image_coll.get_legend()['color_B']
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            line_thick = self.parent.image_coll.get_legend()['line_thick']
            plot_entity = self.parent.image_coll.get_uid_vtk_obj(uid)
        """Then plot."""
        if isinstance(plot_entity, (VertexSet, PolyLine, XsVertexSet, XsPolyLine, Attitude)):
            if isinstance(plot_entity.points, np.ndarray):
                if plot_entity.points_number > 0:
                    """This  check is needed to avoid errors when trying to plot an empty
                    PolyData, just created at the beginning of a digitizing session.
                    Check if both these conditions are necessary_________________"""
                    X = plot_entity.points_X
                    Y = plot_entity.points_Y
                    if isinstance(plot_entity, (VertexSet,Attitude)):
                        if uid in self.selected_uids:
                            if show_property == "Normals":
                                U = np.sin((plot_entity.points_map_dip_azimuth+90) * np.pi / 180)
                                V = np.cos((plot_entity.points_map_dip_azimuth+90) * np.pi / 180)
                                # in quiver scale=40 means arrow is 1/40 of figure width, (shaft) width is scaled to figure width, head length and width are scaled to shaft
                                this_actor = self.ax.quiver(X, Y, U, V, pivot='mid', scale=40, width=0.005, headlength=3, headaxislength=3, facecolor=color_RGB, edgecolor='white', linewidth=1)
                            else:
                                this_actor, = self.ax.plot(X, Y, color=color_RGB, linestyle='', marker='o', markersize=12, markeredgecolor='white', label=uid, picker=True)
                            this_actor.set_visible(visible)
                        else:
                            if show_property == "Normals":
                                U = np.sin((plot_entity.points_map_dip_azimuth+90) * np.pi / 180)
                                V = np.cos((plot_entity.points_map_dip_azimuth+90) * np.pi / 180)
                                # in quiver scale=40 means arrow is 1/40 of figure width, (shaft) width is scaled to figure width, head length and width are scaled to shaft
                                this_actor = self.ax.quiver(X, Y, U, V, pivot='mid', scale=40, width=0.005, headlength=3, headaxislength=3, facecolor=color_RGB, edgecolor='white', linewidth=1)
                                for i,x in enumerate(X):
                                    y = Y[i]
                                    dip = int(plot_entity.points_map_dip[i])
                                    self.ax.annotate(f'{dip}',xy=(x,y))
                            else:
                                this_actor, = self.ax.plot(X, Y, color=color_RGB, linestyle='', marker='o', markersize=8, markeredgecolor='white', label=uid, picker=True)
                            this_actor.set_visible(visible)
                    elif isinstance(plot_entity, PolyLine):
                        if uid in self.selected_uids:
                            this_actor, = self.ax.plot(X, Y, color=color_RGB, linewidth=line_thick * 2, marker='o', label=uid, picker=True)
                            this_actor.set_visible(visible)
                        else:
                            this_actor, = self.ax.plot(X, Y, color=color_RGB, linewidth=line_thick, label=uid, picker=True)
                            this_actor.set_visible(visible)
                else:
                    this_actor = None
            else:
                this_actor = None
        elif isinstance(plot_entity, TriSurf):
            if isinstance(plot_entity.points, np.ndarray):
                if plot_entity.points_number > 0:
                    """This  check is needed to avoid errors when trying to plot an empty
                    PolyData, just created at the beginning of a digitizing session.
                    Check if both these conditions are necessary_________________"""
                    if collection == 'geol_coll':
                        surf_boundary = plot_entity.get_clean_boundary()
                        for cell in range(surf_boundary.GetNumberOfCells()):
                            border_points = numpy_support.vtk_to_numpy(surf_boundary.GetCell(cell).GetPoints().GetData())
                        X = border_points[:, 0]
                        Y = border_points[:, 1]
                    elif collection == 'boundary_coll':
                        bounds = plot_entity.bounds
                        X = [bounds[0], bounds[1], bounds[1], bounds[0], bounds[0]]
                        Y = [bounds[2], bounds[2], bounds[3], bounds[3], bounds[2]]
                    this_actor, = self.ax.plot(X, Y, color=color_RGB, linewidth=line_thick, label=uid, picker=True)
                    this_actor.set_visible(visible)
                else:
                    this_actor = None
            else:
                this_actor = None
        elif isinstance(plot_entity, DEM):
            if isinstance(plot_entity.points, np.ndarray):
                if plot_entity.points_number > 0:
                    """This  check is needed to avoid errors when trying to plot an empty
                    PolyData, just created at the beginning of a digitizing session.
                    Check if both these conditions are necessary_________________"""
                    bounds = plot_entity.bounds
                    X = [bounds[0], bounds[1], bounds[1], bounds[0], bounds[0]]
                    Y = [bounds[2], bounds[2], bounds[3], bounds[3], bounds[2]]
                    this_actor, = self.ax.plot(X, Y, color=color_RGB, linewidth=line_thick, label=uid, picker=True)
                    this_actor.set_visible(visible)
                else:
                    this_actor = None
            else:
                this_actor = None
        elif isinstance(plot_entity, MapImage):
            if plot_entity.bounds:
                if (plot_entity.bounds[0] != plot_entity.bounds[1]) and (plot_entity.bounds[2] != plot_entity.bounds[3]):
                    """This check is needed to avoid plotting empty or non-georeferenced images.
                    Check if both these conditions are necessary_________________"""
                    xy_bounds = plot_entity.bounds[0:4]
                    if show_property not in [None, 'none']:
                        if plot_entity.get_property_components(show_property) == 3:
                            """RGB for 3-component properties"""
                            this_actor = self.ax.imshow(plot_entity.image_data(show_property), origin='upper', extent=xy_bounds, zorder=0)
                        elif plot_entity.get_property_components(show_property) == 1:
                            """Greyscale for single property images"""
                            show_property_title = show_property
                            show_property_cmap = self.parent.prop_legend_df.loc[self.parent.prop_legend_df['property_name'] == show_property_title, "colormap"].values[0]
                            this_actor = self.ax.imshow(plot_entity.image_data(show_property), origin='upper', extent=xy_bounds, zorder=0, cmap=show_property_cmap)
                    else:
                        X = [xy_bounds[0], xy_bounds[1], xy_bounds[1], xy_bounds[0], xy_bounds[0]]
                        Y = [xy_bounds[2], xy_bounds[2], xy_bounds[3], xy_bounds[3], xy_bounds[2]]
                        this_actor, = self.ax.plot(X, Y, color=color_RGB, linewidth=line_thick, label=uid, picker=True)
                    this_actor.set_visible(visible)
                else:
                    this_actor = None
            else:
                this_actor = None
        elif isinstance(plot_entity, Seismics):
            if isinstance(plot_entity.points, np.ndarray):
                if plot_entity.points_number > 0:
                    """This  check is needed to avoid errors when trying to plot an empty
                    object, just created at the beginning of a digitizing session.
                    Check if both these conditions are necessary_________________"""
                    bounds = plot_entity.bounds
                    X = [bounds[0], bounds[1], bounds[1], bounds[0], bounds[0]]
                    Y = [bounds[2], bounds[2], bounds[3], bounds[3], bounds[2]]
                    this_actor, = self.ax.plot(X, Y, color=color_RGB, linewidth=line_thick, label=uid, picker=True)
                    this_actor.set_visible(visible)
                else:
                    this_actor = None
            else:
                this_actor = None
        elif isinstance(plot_entity, Voxet):
            if plot_entity.bounds:
                if (plot_entity.bounds[0] != plot_entity.bounds[1]) and (plot_entity.bounds[2] != plot_entity.bounds[3]):
                    """This check is needed to avoid plotting empty or non-georeferenced voxets.
                    Check if both these conditions are necessary_________________"""
                    bounds = plot_entity.bounds
                    X = [bounds[0], bounds[1], bounds[1], bounds[0], bounds[0]]
                    Y = [bounds[2], bounds[2], bounds[3], bounds[3], bounds[2]]
                    this_actor, = self.ax.plot(X, Y, color=color_RGB, linewidth=line_thick, label=uid, picker=True)
                    this_actor.set_visible(visible)
                else:
                    this_actor = None
            else:
                this_actor = None
        if this_actor:
            this_actor.figure.canvas.draw()
            return this_actor

    """Implementation of functions specific to this view (e.g. particular editing or visualization functions)"""


class ViewXsection(View2D):
    """Create map view and import UI created with Qt Designer by subclassing base view"""
    """parent is the QT object that is launching this one, hence the ProjectWindow() instance in this case"""

    '''[Gabriele]  [TODO] xsection update only objects that are projected on the section.'''

    def __init__(self, parent=None,*args, **kwargs):
        """Set the Xsection"""

        if parent.xsect_coll.get_names():
            self.this_x_section_name = input_combo_dialog(parent=None, title="Xsection", label="Choose Xsection", choice_list=parent.xsect_coll.get_names())
        else:
            message_dialog(title="Xsection", message="No Xsection in project")
            return
        if self.this_x_section_name:
            self.this_x_section_uid = parent.xsect_coll.df.loc[parent.xsect_coll.df['name'] == self.this_x_section_name, 'uid'].values[0]
        else:
            return

        """super here after having set the x_section_uid and _name"""
        super(ViewXsection, self).__init__(parent, *args, **kwargs)

        """Rename Base View, Menu and Tool"""
        self.setWindowTitle("Xsection View")
        self.ax.set_title(("Xsection: " + self.this_x_section_name), fontsize=self.base_font_size)  # set title
        self.ax.set_xlabel("W [m]", fontsize=int(self.base_font_size * .8))  # set label for W coordinate
        self.ax.set_ylabel("Z [m]", fontsize=int(self.base_font_size * .8))  # set label for Z coordinate

        """Re-implementations of functions that appear in all views - see placeholders in BaseView()"""
        """NONE AT THE MOMENT"""
        self.create_geology_tree(sec_uid=self.this_x_section_uid)
        self.create_topology_tree(sec_uid=self.this_x_section_uid)
        self.create_xsections_tree(sec_uid=self.this_x_section_uid)
        self.create_boundary_list(sec_uid=self.this_x_section_uid)
        self.create_mesh3d_list(sec_uid=self.this_x_section_uid)
        self.create_dom_list(sec_uid=self.this_x_section_uid)
        self.create_image_list(sec_uid=self.this_x_section_uid)




    """Implementation of functions specific to 2D views"""

    def initialize_menu_tools(self):
        """Inheritance of common tools"""
        super().initialize_menu_tools()
        """Tools specific to Xsection view"""
        """NONE AT THE MOMENT"""
        self.secNavigator = QAction("Section navigator", self)
        self.secNavigator.triggered.connect(self.navigator)
        self.menuWindow.addAction(self.secNavigator)

    def show_actor_with_property(self, uid=None, collection=None, show_property=None, visible=None):
        """Show actor with scalar property (default None)
        https://github.com/pyvista/pyvista/blob/140b15be1d4021b81ded46b1c212c70e86a98ee7/pyvista/plotting/plotting.py#L1045"""
        if collection == 'geol_coll':
            if (self.parent.geol_coll.get_uid_topological_type(uid) == "XsVertexSet" or self.parent.geol_coll.get_uid_topological_type(uid) == "XsPolyLine") and self.parent.geol_coll.get_uid_x_section(uid) == self.this_x_section_uid:
                color_R = self.parent.geol_coll.get_uid_legend(uid=uid)['color_R']
                color_G = self.parent.geol_coll.get_uid_legend(uid=uid)['color_G']
                color_B = self.parent.geol_coll.get_uid_legend(uid=uid)['color_B']
                color_RGB = [color_R / 255, color_G / 255, color_B / 255]
                line_thick = self.parent.geol_coll.get_uid_legend(uid=uid)['line_thick']
                plot_entity = self.parent.geol_coll.get_uid_vtk_obj(uid)
            else:
                plot_entity = None
        elif collection == 'xsect_coll':
            """To be updated in future for Xsection intersections_______________"""
            if uid == self.this_x_section_uid:
                color_R = self.parent.xsect_coll.get_legend()['color_R']
                color_G = self.parent.xsect_coll.get_legend()['color_G']
                color_B = self.parent.xsect_coll.get_legend()['color_B']
                color_RGB = [color_R / 255, color_G / 255, color_B / 255]
                line_thick = self.parent.xsect_coll.get_legend()['line_thick']
                plot_entity = self.parent.xsect_coll.get_uid_vtk_frame(uid)
            else:
                plot_entity = None
        elif collection == 'boundary_coll':
            if self.parent.boundary_coll.get_uid_topological_type(uid) == "XsPolyLine" and self.parent.boundary_coll.get_uid_x_section(uid) == self.this_x_section_uid:
                    color_R = self.parent.boundary_coll.get_legend()['color_R']
                    color_G = self.parent.boundary_coll.get_legend()['color_G']
                    color_B = self.parent.boundary_coll.get_legend()['color_B']
                    color_RGB = [color_R / 255, color_G / 255, color_B / 255]
                    line_thick = self.parent.boundary_coll.get_legend()['line_thick']
                    plot_entity = self.parent.boundary_coll.get_uid_vtk_obj(uid)
            else:
                plot_entity = None
        elif collection == 'mesh3d_coll':
            if self.parent.mesh3d_coll.get_uid_mesh3d_type(uid) == "XsVoxet" and self.parent.mesh3d_coll.get_uid_x_section(uid) == self.this_x_section_uid:
                    color_R = self.parent.mesh3d_coll.get_legend()['color_R']
                    color_G = self.parent.mesh3d_coll.get_legend()['color_G']
                    color_B = self.parent.mesh3d_coll.get_legend()['color_B']
                    color_RGB = [color_R / 255, color_G / 255, color_B / 255]
                    line_thick = self.parent.mesh3d_coll.get_legend()['line_thick']
                    plot_entity = self.parent.mesh3d_coll.get_uid_vtk_obj(uid)
            else:
                plot_entity = None
        elif collection == 'dom_coll':
            if self.parent.dom_coll.get_uid_dom_type(uid) == "DomXs" and self.parent.dom_coll.get_uid_x_section(uid) == self.this_x_section_uid:
                    color_R = self.parent.dom_coll.get_legend()['color_R']
                    color_G = self.parent.dom_coll.get_legend()['color_G']
                    color_B = self.parent.dom_coll.get_legend()['color_B']
                    color_RGB = [color_R / 255, color_G / 255, color_B / 255]
                    line_thick = self.parent.dom_coll.get_legend()['line_thick']
                    plot_entity = self.parent.dom_coll.get_uid_vtk_obj(uid)
            else:
                plot_entity = None
        elif collection == 'image_coll':
            if self.parent.image_coll.get_uid_image_type(uid) == "XsImage" and self.parent.image_coll.get_uid_x_section(uid) == self.this_x_section_uid:
                    color_R = self.parent.image_coll.get_legend()['color_R']
                    color_G = self.parent.image_coll.get_legend()['color_G']
                    color_B = self.parent.image_coll.get_legend()['color_B']
                    color_RGB = [color_R / 255, color_G / 255, color_B / 255]
                    line_thick = self.parent.image_coll.get_legend()['line_thick']
                    plot_entity = self.parent.image_coll.get_uid_vtk_obj(uid)
            else:
                plot_entity = None
        if plot_entity:
            if isinstance(plot_entity, XsVoxet):
                if plot_entity.bounds:
                    if (plot_entity.bounds[0] != plot_entity.bounds[1]) and (plot_entity.bounds[2] != plot_entity.bounds[3]):
                        wz_bounds = plot_entity.xs_bounds
                        if show_property not in [None, 'none']:
                            show_property_title = show_property
                            show_property_cmap = self.parent.prop_legend_df.loc[self.parent.prop_legend_df['property_name'] == show_property_title, "colormap"].values[0]
                            left, right = self.ax.get_xlim()  # needed since sometimes plotting an image resizes the plot to the image area only
                            bottom, top = self.ax.get_ylim()
                            this_actor = self.ax.imshow(plot_entity.image_data(show_property), origin='upper', extent=wz_bounds, zorder=0, cmap=show_property_cmap)
                            self.ax.set_xlim(left=left, right=right)
                            self.ax.set_ylim(bottom=bottom, top=top)
                            this_actor.set_visible(visible)
                        else:
                            W = [wz_bounds[0], wz_bounds[1], wz_bounds[1], wz_bounds[0], wz_bounds[0]]
                            Z = [wz_bounds[2], wz_bounds[2], wz_bounds[3], wz_bounds[3], wz_bounds[2]]
                            this_actor, = self.ax.plot(W, Z, color=color_RGB, linewidth=line_thick, label=uid, picker=True)
                            this_actor.set_visible(visible)
                    else:
                        this_actor = None
                else:
                    this_actor = None
            elif isinstance(plot_entity, XsImage):
                if plot_entity.bounds:
                    print('plot_entity.bounds: ', plot_entity.bounds)
                    if (plot_entity.bounds[0] != plot_entity.bounds[1]) and (plot_entity.bounds[2] != plot_entity.bounds[3]):
                        wz_bounds = plot_entity.xs_bounds
                        print('wz_bounds: ', wz_bounds)
                        if show_property not in [None, 'none']:
                            print('show_property: ', show_property)
                            left, right = self.ax.get_xlim()  # needed since sometimes plotting an image resizes the plot to the image area only
                            bottom, top = self.ax.get_ylim()
                            if plot_entity.get_property_components(show_property) == 3:
                                """RGB for 3-component properties"""
                                this_actor = self.ax.imshow(plot_entity.image_data(show_property), origin='upper', extent=wz_bounds, zorder=0)
                            elif plot_entity.get_property_components(show_property) == 1:
                                """Greyscale for single property images"""
                                show_property_title = show_property
                                show_property_cmap = self.parent.prop_legend_df.loc[self.parent.prop_legend_df['property_name'] == show_property_title, "colormap"].values[0]
                                this_actor = self.ax.imshow(plot_entity.image_data(show_property), origin='upper', extent=wz_bounds, zorder=0, cmap=show_property_cmap)
                            self.ax.set_xlim(left=left, right=right)
                            self.ax.set_ylim(bottom=bottom, top=top)
                            this_actor.set_visible(visible)
                        else:
                            print('show_property: ', show_property)
                            W = [wz_bounds[0], wz_bounds[1], wz_bounds[1], wz_bounds[0], wz_bounds[0]]
                            Z = [wz_bounds[2], wz_bounds[2], wz_bounds[3], wz_bounds[3], wz_bounds[2]]
                            this_actor, = self.ax.plot(W, Z, color=color_RGB, linewidth=line_thick, label=uid, picker=True)
                            this_actor.set_visible(visible)
                    else:
                        this_actor = None
                else:
                    this_actor = None
            else:
                if isinstance(plot_entity.points, np.ndarray):
                    if plot_entity.points_number > 0:
                        """These  checks are needed to avoid errors when trying to plot an empty
                        PolyData, just created at the beginning of a digitizing session.
                        Check if both these conditions are necessary_________________"""
                        W = plot_entity.points_W
                        Z = plot_entity.points_Z
                        if isinstance(plot_entity, XsVertexSet):
                            if uid in self.selected_uids:
                                if show_property == "Normals":
                                    U = np.cos(plot_entity.points_xs_app_dip * np.pi / 180)
                                    V = np.sin(plot_entity.points_xs_app_dip * np.pi / 180)
                                    """In quiver scale=40 means arrow is 1/40 of figure width, (shaft) width is scaled to figure width, head length and width are scaled to shaft."""
                                    this_actor = self.ax.quiver(W, Z, U, V, pivot='mid', scale=50, width=0.002, headwidth=1, headlength=0.01, headaxislength=0.01, facecolor=color_RGB, edgecolor='white', linewidth=1)

                                else:
                                    this_actor, = self.ax.plot(W, Z, color=color_RGB, linestyle='', marker='o', markersize=12, markeredgecolor='white', label=uid, picker=True)
                                this_actor.set_visible(visible)
                            else:
                                if show_property == "Normals":
                                    U = np.cos(plot_entity.points_xs_app_dip * np.pi / 180)
                                    V = -np.sin(plot_entity.points_xs_app_dip * np.pi / 180)
                                    """In quiver scale=40 means arrow is 1/40 of figure width, (shaft) width is scaled to figure width, head length and width are scaled to shaft."""
                                    this_actor = self.ax.quiver(W,Z,U,V,pivot='mid', scale=50, width=0.002, headwidth=1, headlength=0.01, headaxislength=0.01, facecolor=color_RGB, edgecolor='white', linewidth=1)
                                else:
                                    this_actor, = self.ax.plot(W, Z, color=color_RGB, linestyle='', marker='o', markersize=8, markeredgecolor='white', label=uid, picker=True)
                                this_actor.set_visible(visible)
                        elif isinstance(plot_entity, XsPolyLine):
                            if uid in self.selected_uids:
                                this_actor, = self.ax.plot(W, Z, color=color_RGB, linewidth=line_thick * 2, marker='o', label=uid, picker=True)
                                this_actor.set_visible(visible)
                            else:
                                this_actor, = self.ax.plot(W, Z, color=color_RGB, linewidth=line_thick, label=uid, picker=True)
                                this_actor.set_visible(visible)
                    else:
                        print(uid, " Entity has zero points.")
                        this_actor = None
                else:
                    print(uid, " Entity is None.")
                    this_actor = None
            this_actor.figure.canvas.draw()
        else:
            this_actor = None
        return this_actor

    '''[Gabriele] Update the views depending on the sec_uid. We need to redefine the functions to use the sec_uid parameter for the update_dom_list_added func. We just need the x_added_x functions because the x_removed_x works on an already build/modified tree'''

    def geology_added_update_views(self, updated_list=None):
        """This is called when an entity is added to the geological collection.
        Disconnect signals to geology and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.GeologyTreeWidget.itemChanged.disconnect()
        self.TopologyTreeWidget.itemChanged.disconnect()
        """Create pandas dataframe as list of "new" actors"""
        actors_df_new = pd.DataFrame(columns=['uid', 'actor', 'show', 'collection', 'show_prop'])
        for uid in updated_list:
            this_actor = self.show_actor_with_property(uid=uid, collection='geol_coll', show_property=None, visible=True)
            self.actors_df = self.actors_df.append({'uid': uid, 'actor': this_actor, 'show': True, 'collection': 'geol_coll', 'show_prop': None}, ignore_index=True)
            actors_df_new = actors_df_new.append({'uid': uid, 'actor': this_actor, 'show': True, 'collection': 'geol_coll', 'show_prop': None}, ignore_index=True)
            self.update_geology_tree_added(actors_df_new, sec_uid=self.this_x_section_uid)
            self.update_topology_tree_added(actors_df_new, sec_uid=self.this_x_section_uid)
        """Re-connect signals."""
        self.GeologyTreeWidget.itemChanged.connect(self.toggle_geology_topology_visibility)
        self.TopologyTreeWidget.itemChanged.connect(self.toggle_geology_topology_visibility)

    def mesh3d_added_update_views(self, updated_list=None):
        """This is called when a mesh3d is added to the mesh3d collection.
        Disconnect signals to mesh3d list, if they are set, then they are
        reconnected when the list is rebuilt"""
        self.Mesh3DTableWidget.itemChanged.disconnect()
        actors_df_new = pd.DataFrame(columns=['uid', 'actor', 'show', 'collection', 'show_prop'])
        for uid in updated_list:
            this_actor = self.show_actor_with_property(uid=uid, collection='mesh3d_coll', show_property=None, visible=False)
            self.actors_df = self.actors_df.append({'uid': uid, 'actor': this_actor, 'show': False, 'collection': 'mesh3d_coll', 'show_prop': None}, ignore_index=True)
            actors_df_new = actors_df_new.append({'uid': uid, 'actor': this_actor, 'show': False, 'collection': 'mesh3d_coll', 'show_prop': None}, ignore_index=True)
            self.update_mesh3d_list_added(actors_df_new, sec_uid=self.this_x_section_uid)
        """Re-connect signals."""
        self.Mesh3DTableWidget.itemChanged.connect(self.toggle_mesh3d_visibility)

    def dom_added_update_views(self, updated_list=None):
        """This is called when a DOM is added to the xsect collection.
        Disconnect signals to dom list, if they are set, then they are
        reconnected when the list is rebuilt"""
        self.DOMsTableWidget.itemChanged.disconnect()
        actors_df_new = pd.DataFrame(columns=['uid', 'actor', 'show', 'collection', 'show_prop'])
        for uid in updated_list:
            this_actor = self.show_actor_with_property(uid=uid, collection='dom_coll', show_property=None, visible=False)
            self.actors_df = self.actors_df.append({'uid': uid, 'actor': this_actor, 'show': False, 'collection': 'dom_coll', 'show_prop': None}, ignore_index=True)
            actors_df_new = actors_df_new.append({'uid': uid, 'actor': this_actor, 'show': False, 'collection': 'dom_coll', 'show_prop': None}, ignore_index=True)
            self.update_dom_list_added(actors_df_new, sec_uid=self.this_x_section_uid)
        """Re-connect signals."""
        self.DOMsTableWidget.itemChanged.connect(self.toggle_dom_visibility)

    def xsect_added_update_views(self, updated_list=None):
        """This is called when a cross-section is added to the xsect collection.
        Disconnect signals to xsect list, if they are set, then they are
        reconnected when the list is rebuilt"""
        self.XSectionTreeWidget.itemChanged.disconnect()
        actors_df_new = pd.DataFrame(columns=['uid', 'actor', 'show', 'collection', 'show_prop'])
        for uid in updated_list:
            this_actor = self.show_actor_with_property(uid=uid, collection='xsect_coll', show_property=None, visible=True)
            self.actors_df = self.actors_df.append({'uid': uid, 'actor': this_actor, 'show': True, 'collection': 'xsect_coll', 'show_prop': None}, ignore_index=True)
            actors_df_new = actors_df_new.append({'uid': uid, 'actor': this_actor, 'show': True, 'collection': 'xsect_coll', 'show_prop': None}, ignore_index=True)
            self.update_xsections_tree_added(actors_df_new, sec_uid=self.this_x_section_uid)
        """Re-connect signals."""
        self.XSectionTreeWidget.itemChanged.connect(self.toggle_xsection_visibility)

    """Implementation of functions specific to this view (e.g. particular editing or visualization functions)"""

    """NONE AT THE MOMENT"""
    def navigator(self):
        sec_list = self.parent.xsect_coll.get_names()
        idx = sec_list.index(self.this_x_section_name)
        NavigatorWidget(self,sec_list,idx)


class ViewStereoplot(BaseView):
    def __init__(self, *args, **kwargs):
        super(ViewStereoplot, self).__init__(*args, **kwargs)
        self.setWindowTitle("Stereoplot View")
        self.tog_contours = -1
        # mplstyle.context('classic')
    def initialize_menu_tools(self):

        self.actionContours = QAction('View contours',self)
        self.actionContours.triggered.connect(lambda: self.toggle_contours(filled=False))
        self.menuTools.addAction(self.actionContours)


        self.menuPlot = QMenu('Plot options',self)


        self.menuGrids = QMenu('Grid overlays',self)
        self.actionSetPolar = QAction('Set polar grid',self)
        self.actionSetPolar.triggered.connect(lambda: self.change_grid(kind='polar'))
        self.actionSetEq = QAction('Set equatorial grid',self)
        self.actionSetEq.triggered.connect(lambda: self.change_grid(kind='equatorial'))
        self.menuGrids.addAction(self.actionSetPolar)
        self.menuGrids.addAction(self.actionSetEq)
        self.menuPlot.addMenu(self.menuGrids)

        self.menuProj = QMenu('Stereoplot projection',self)
        self.actionSetEquiare = QAction('Equiareal (Schmidt)',self)
        self.actionSetEquiare.triggered.connect(lambda: self.change_proj(projection='equal_area_stereonet'))
        self.actionSetEquiang = QAction('Equiangolar (Wulff)',self)
        self.actionSetEquiang.triggered.connect(lambda: self.change_proj(projection='equal_angle_stereonet'))
        self.menuProj.addAction(self.actionSetEquiare)
        self.menuProj.addAction(self.actionSetEquiang)
        self.menuPlot.addMenu(self.menuProj)
        self.menubar.insertMenu(self.menuHelp.menuAction(),self.menuPlot)






    def initialize_interactor(self,kind=None,projection='equal_area_stereonet'):
        self.grid_kind = kind
        self.proj_type = projection

        with mplstyle.context(('default')):
            """Create Matplotlib canvas, figure and navi_toolbar"""
            self.figure,self.ax = mplstereonet.subplots(projection=self.proj_type)  # create a Matplotlib figure; this implicitly creates also the canvas to contain the figure

        self.canvas = FigureCanvas(self.figure)  # get a reference to the canvas that contains the figure
        # print("dir(self.canvas):\n", dir(self.canvas))
        """https://doc.qt.io/qt-5/qsizepolicy.html"""
        self.navi_toolbar = NavigationToolbar(self.figure.canvas, self)  # create a navi_toolbar with the matplotlib.backends.backend_qt5agg method NavigationToolbar

        """Create Qt layout andNone add Matplotlib canvas, figure and navi_toolbar"""
        # canvas_widget = self.figure.canvas
        # canvas_widget.setAutoFillBackground(True)
        self.ViewFrameLayout.addWidget(self.canvas)  # add Matplotlib canvas (created above) as a widget to the Qt layout
        # print(plot_widget)
        self.ViewFrameLayout.addWidget(self.navi_toolbar)  # add navigation navi_toolbar (created above) to the layout
        self.ax.grid(kind=self.grid_kind,color='k')

    def create_geology_tree(self):
        """Create geology tree with checkboxes and properties"""
        self.GeologyTreeWidget.clear()
        self.GeologyTreeWidget.setColumnCount(3)
        self.GeologyTreeWidget.setHeaderLabels(['Type > Feature > Scenario > Name', 'uid', 'property'])
        self.GeologyTreeWidget.hideColumn(1)  # hide the uid column
        self.GeologyTreeWidget.setItemsExpandable(True)

        filtered_geo = self.parent.geol_coll.df.loc[(self.parent.geol_coll.df['topological_type'] == 'VertexSet'), 'geological_type']
        geo_types = pd.unique(filtered_geo)

        for geo_type in geo_types:
            glevel_1 = QTreeWidgetItem(self.GeologyTreeWidget, [geo_type])  # self.GeologyTreeWidget as parent -> top level
            glevel_1.setFlags(glevel_1.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable)


            filtered_geo_feat = self.parent.geol_coll.df.loc[(self.parent.geol_coll.df['geological_type'] == geo_type) & (self.parent.geol_coll.df['topological_type'] == 'VertexSet'), 'geological_feature']
            geo_features = pd.unique(filtered_geo_feat)


            for feature in geo_features:
                glevel_2 = QTreeWidgetItem(glevel_1, [feature])  # glevel_1 as parent -> 1st middle level
                glevel_2.setFlags(glevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable)

                geo_scenario = pd.unique(self.parent.geol_coll.df.loc[(self.parent.geol_coll.df['geological_type'] == geo_type) & (self.parent.geol_coll.df['geological_feature'] == feature),'scenario'])

                for scenario in geo_scenario:
                    glevel_3 = QTreeWidgetItem(glevel_2, [scenario])  # glevel_2 as parent -> 2nd middle level
                    glevel_3.setFlags(glevel_3.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable)


                    uids = self.parent.geol_coll.df.loc[(self.parent.geol_coll.df['geological_type'] == geo_type) & (self.parent.geol_coll.df['geological_feature'] == feature) & (self.parent.geol_coll.df['scenario'] == scenario) & (self.parent.geol_coll.df['topological_type'] == 'VertexSet'), 'uid'].to_list()

                    for uid in uids:
                        property_combo = QComboBox()
                        property_combo.uid = uid
                        property_combo.addItem("Poles")
                        # property_combo.addItem("Planes")

                        name = self.parent.geol_coll.df.loc[(self.parent.geol_coll.df['uid'] == uid), 'name'].values[0]
                        glevel_4 = QTreeWidgetItem(glevel_3, [name, uid])  # glevel_3 as parent -> lower level
                        self.GeologyTreeWidget.setItemWidget(glevel_4, 2, property_combo)
                        property_combo.currentIndexChanged.connect(lambda: self.toggle_property())
                        glevel_4.setFlags(glevel_4.flags() | Qt.ItemIsUserCheckable)
                        if self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                            glevel_4.setCheckState(0, Qt.Checked)
                        elif not self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                            glevel_4.setCheckState(0, Qt.Unchecked)
        """Send messages. Note that with tristate several signals are emitted in a sequence, one for each
        changed item, but upper levels do not broadcast uid's so they are filtered in the toggle method."""
        self.GeologyTreeWidget.itemChanged.connect(self.toggle_geology_topology_visibility)
        self.GeologyTreeWidget.expandAll()

    def create_topology_tree(self):
        """Create topology tree with checkboxes and properties"""
        self.TopologyTreeWidget.clear()
        self.TopologyTreeWidget.setColumnCount(3)
        self.TopologyTreeWidget.setHeaderLabels(['Type > Scenario > Name', 'uid', 'property'])
        self.TopologyTreeWidget.hideColumn(1)  # hide the uid column
        self.TopologyTreeWidget.setItemsExpandable(True)

        filtered_topo = self.parent.geol_coll.df.loc[(self.parent.geol_coll.df['topological_type'] == 'VertexSet'), 'topological_type']
        topo_types = pd.unique(filtered_topo)

        for topo_type in topo_types:
            tlevel_1 = QTreeWidgetItem(self.TopologyTreeWidget, [topo_type])  # self.GeologyTreeWidget as parent -> top level
            tlevel_1.setFlags(tlevel_1.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable)
            for scenario in pd.unique(self.parent.geol_coll.df.loc[self.parent.geol_coll.df['topological_type'] == topo_type, 'scenario']):
                tlevel_2 = QTreeWidgetItem(tlevel_1, [scenario])  # tlevel_1 as parent -> middle level
                tlevel_2.setFlags(tlevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable)

                uids = self.parent.geol_coll.df.loc[(self.parent.geol_coll.df['topological_type'] == topo_type) & (self.parent.geol_coll.df['scenario'] == scenario) & (self.parent.geol_coll.df['topological_type'] == 'VertexSet'), 'uid'].to_list()

                for uid in uids:
                    property_combo = QComboBox()
                    property_combo.uid = uid
                    property_combo.addItem("Poles")
                    # property_combo.addItem("Planes")
                    name = self.parent.geol_coll.df.loc[self.parent.geol_coll.df['uid'] == uid, 'name'].values[0]
                    tlevel_3 = QTreeWidgetItem(tlevel_2, [name, uid])  # tlevel_2 as parent -> lower level
                    self.TopologyTreeWidget.setItemWidget(tlevel_3, 2, property_combo)
                    property_combo.currentIndexChanged.connect(lambda: self.toggle_property())
                    tlevel_3.setFlags(tlevel_3.flags() | Qt.ItemIsUserCheckable)
                    if self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                        tlevel_3.setCheckState(0, Qt.Checked)
                    elif not self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                        tlevel_3.setCheckState(0, Qt.Unchecked)
        """Send messages. Note that with tristate several signals are emitted in a sequence, one for each
        changed item, but upper levels do not broadcast uid's so they are filtered in the toggle method."""
        self.TopologyTreeWidget.itemChanged.connect(self.toggle_geology_topology_visibility)
        self.TopologyTreeWidget.expandAll()

    def update_geology_tree_added(self, new_list=None):
        """Update geology tree without creating a new model"""
        uid_list = list(new_list['uid'])
        for uid in uid_list:
            if self.GeologyTreeWidget.findItems(self.parent.geol_coll.get_uid_geological_type(uid), Qt.MatchExactly, 0) != []:
                """Already exists a TreeItem (1 level) for the geological type"""
                counter_1 = 0
                for child_1 in range(self.GeologyTreeWidget.findItems(self.parent.geol_coll.get_uid_geological_type(uid), Qt.MatchExactly, 0)[0].childCount()):
                    """for cycle that loops n times as the number of subItems in the specific geological type branch"""
                    if self.GeologyTreeWidget.findItems(self.parent.geol_coll.get_uid_geological_type(uid), Qt.MatchExactly, 0)[0].child(child_1).text(0) == self.parent.geol_coll.get_uid_geological_feature(uid):
                        counter_1 += 1
                if counter_1 != 0:
                    for child_1 in range(self.GeologyTreeWidget.findItems(self.parent.geol_coll.get_uid_geological_type(uid), Qt.MatchExactly, 0)[0].childCount()):
                        if self.GeologyTreeWidget.findItems(self.parent.geol_coll.get_uid_geological_type(uid), Qt.MatchExactly, 0)[0].child(child_1).text(0) == self.parent.geol_coll.get_uid_geological_feature(uid):
                            """Already exists a TreeItem (2 level) for the geological feature"""
                            counter_2 = 0
                            for child_2 in range(self.GeologyTreeWidget.itemBelow(self.GeologyTreeWidget.findItems(self.parent.geol_coll.get_uid_geological_type(uid), Qt.MatchExactly, 0)[0]).childCount()):
                                """for cycle that loops n times as the number of sub-subItems in the specific geological type and geological feature branch"""
                                if self.GeologyTreeWidget.itemBelow(self.GeologyTreeWidget.findItems(self.parent.geol_coll.get_uid_geological_type(uid), Qt.MatchExactly, 0)[0]).child(child_2).text(0) == self.parent.geol_coll.get_uid_scenario(uid):
                                    counter_2 += 1
                            if counter_2 != 0:
                                for child_2 in range(self.GeologyTreeWidget.itemBelow(self.GeologyTreeWidget.findItems(self.parent.geol_coll.get_uid_geological_type(uid),Qt.MatchExactly, 0)[0]).childCount()):
                                    if self.GeologyTreeWidget.itemBelow(self.GeologyTreeWidget.findItems(self.parent.geol_coll.get_uid_geological_type(uid), Qt.MatchExactly, 0)[0]).child(child_2).text(0) == self.parent.geol_coll.get_uid_scenario(uid):
                                        """Same geological type, geological feature and scenario"""
                                        property_combo = QComboBox()
                                        property_combo.uid = uid
                                        # property_combo.addItem("Planes")
                                        property_combo.addItem("Poles")
                                        for prop in self.parent.geol_coll.get_uid_properties_names(uid):
                                            property_combo.addItem(prop)
                                        name = self.parent.geol_coll.get_uid_name(uid)
                                        glevel_4 = QTreeWidgetItem(self.GeologyTreeWidget.findItems(self.parent.geol_coll.get_uid_geological_type(uid), Qt.MatchExactly, 0)[0].child(child_1).child(child_2), [name, uid])
                                        self.GeologyTreeWidget.setItemWidget(glevel_4, 2, property_combo)
                                        property_combo.currentIndexChanged.connect(lambda: self.toggle_property())
                                        glevel_4.setFlags(glevel_4.flags() | Qt.ItemIsUserCheckable)
                                        if self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                                            glevel_4.setCheckState(0, Qt.Checked)
                                        elif not self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                                            glevel_4.setCheckState(0, Qt.Unchecked)
                                        self.GeologyTreeWidget.insertTopLevelItem(0, glevel_4)
                                        break
                            else:
                                """Same geological type and geological feature, different scenario"""
                                glevel_3 = QTreeWidgetItem(self.GeologyTreeWidget.findItems(self.parent.geol_coll.get_uid_geological_type(uid), Qt.MatchExactly, 0)[0].child(child_1), [self.parent.geol_coll.get_uid_scenario(uid)])
                                glevel_3.setFlags(glevel_3.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable)
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
                                property_combo.currentIndexChanged.connect(lambda: self.toggle_property())
                                glevel_4.setFlags(glevel_4.flags() | Qt.ItemIsUserCheckable)
                                if self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                                    glevel_4.setCheckState(0, Qt.Checked)
                                elif not self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                                    glevel_4.setCheckState(0, Qt.Unchecked)
                                self.GeologyTreeWidget.insertTopLevelItem(0, glevel_4)
                                break
                else:
                    """Same geological type, different geological feature and scenario"""
                    glevel_2 = QTreeWidgetItem(self.GeologyTreeWidget.findItems(self.parent.geol_coll.get_uid_geological_type(uid), Qt.MatchExactly, 0)[0], [self.parent.geol_coll.get_uid_geological_feature(uid)])
                    glevel_2.setFlags(glevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable)
                    self.GeologyTreeWidget.insertTopLevelItem(0, glevel_2)
                    glevel_3 = QTreeWidgetItem(glevel_2, [self.parent.geol_coll.get_uid_scenario(uid)])
                    glevel_3.setFlags(glevel_3.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable)
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
                    property_combo.currentIndexChanged.connect(lambda: self.toggle_property())
                    glevel_4.setFlags(glevel_4.flags() | Qt.ItemIsUserCheckable)
                    if self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                        glevel_4.setCheckState(0, Qt.Checked)
                    elif not self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                        glevel_4.setCheckState(0, Qt.Unchecked)
                    self.GeologyTreeWidget.insertTopLevelItem(0, glevel_4)
                    break
            else:
                """Different geological type, geological feature and scenario"""
                glevel_1 = QTreeWidgetItem(self.GeologyTreeWidget, [self.parent.geol_coll.get_uid_geological_type(uid)])
                glevel_1.setFlags(glevel_1.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable)
                self.GeologyTreeWidget.insertTopLevelItem(0, glevel_1)
                glevel_2 = QTreeWidgetItem(glevel_1, [self.parent.geol_coll.get_uid_geological_feature(uid)])
                glevel_2.setFlags(glevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable)
                self.GeologyTreeWidget.insertTopLevelItem(0, glevel_2)
                glevel_3 = QTreeWidgetItem(glevel_2, [self.parent.geol_coll.get_uid_scenario(uid)])
                glevel_3.setFlags(glevel_3.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable)
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
                property_combo.currentIndexChanged.connect(lambda: self.toggle_property())
                glevel_4.setFlags(glevel_4.flags() | Qt.ItemIsUserCheckable)
                if self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                    glevel_4.setCheckState(0, Qt.Checked)
                elif not self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                    glevel_4.setCheckState(0, Qt.Unchecked)
                self.GeologyTreeWidget.insertTopLevelItem(0, glevel_4)
                break
        self.GeologyTreeWidget.itemChanged.connect(self.toggle_geology_topology_visibility)
        self.GeologyTreeWidget.expandAll()

    def update_topology_tree_added(self, new_list=None):
        """Update topology tree without creating a new model"""
        uid_list = list(new_list['uid'])
        for uid in uid_list:
            if self.TopologyTreeWidget.findItems(self.parent.geol_coll.get_uid_topological_type(uid), Qt.MatchExactly, 0) != []:
                """Already exists a TreeItem (1 level) for the topological type"""
                counter_1 = 0
                for child_1 in range(self.TopologyTreeWidget.findItems(self.parent.geol_coll.get_uid_topological_type(uid), Qt.MatchExactly, 0)[0].childCount()):
                    """for cycle that loops n times as the number of subItems in the specific topological type branch"""
                    if self.TopologyTreeWidget.findItems(self.parent.geol_coll.get_uid_topological_type(uid), Qt.MatchExactly, 0)[0].child(child_1).text(0) == self.parent.geol_coll.get_uid_scenario(uid):
                        counter_1 += 1
                if counter_1 != 0:
                    for child_1 in range(self.TopologyTreeWidget.findItems(self.parent.geol_coll.get_uid_topological_type(uid), Qt.MatchExactly, 0)[0].childCount()):
                        if self.TopologyTreeWidget.findItems(self.parent.geol_coll.get_uid_topological_type(uid), Qt.MatchExactly, 0)[0].child(child_1).text(0) == self.parent.geol_coll.get_uid_scenario(uid):
                            """Same topological type and scenario"""
                            property_combo = QComboBox()
                            property_combo.uid = uid
                            # property_combo.addItem("Planes")
                            property_combo.addItem("Poles")
                            for prop in self.parent.geol_coll.get_uid_properties_names(uid):
                                property_combo.addItem(prop)
                            name = self.parent.geol_coll.get_uid_name(uid)
                            tlevel_3 = QTreeWidgetItem(self.TopologyTreeWidget.findItems(self.parent.geol_coll.get_uid_topological_type(uid), Qt.MatchExactly, 0)[0].child(child_1), [name, uid])
                            self.TopologyTreeWidget.setItemWidget(tlevel_3, 2, property_combo)
                            property_combo.currentIndexChanged.connect(lambda: self.toggle_property())
                            tlevel_3.setFlags(tlevel_3.flags() | Qt.ItemIsUserCheckable)
                            if self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                                tlevel_3.setCheckState(0, Qt.Checked)
                            elif not self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                                tlevel_3.setCheckState(0, Qt.Unchecked)
                            self.TopologyTreeWidget.insertTopLevelItem(0, tlevel_3)
                            break
                else:
                    """Same topological type, different scenario"""
                    tlevel_2 = QTreeWidgetItem(self.TopologyTreeWidget.findItems(self.parent.geol_coll.get_uid_topological_type(uid), Qt.MatchExactly, 0)[0], [self.parent.geol_coll.get_uid_scenario(uid)])
                    tlevel_2.setFlags(tlevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable)
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
                    property_combo.currentIndexChanged.connect(lambda: self.toggle_property())
                    tlevel_3.setFlags(tlevel_3.flags() | Qt.ItemIsUserCheckable)
                    if self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                        tlevel_3.setCheckState(0, Qt.Checked)
                    elif not self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                        tlevel_3.setCheckState(0, Qt.Unchecked)
                    self.TopologyTreeWidget.insertTopLevelItem(0, tlevel_3)
                    break
            else:
                """Different topological type and scenario"""
                tlevel_1 = QTreeWidgetItem(self.TopologyTreeWidget, [self.parent.geol_coll.get_uid_topological_type(uid)])
                tlevel_1.setFlags(tlevel_1.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable)
                self.TopologyTreeWidget.insertTopLevelItem(0, tlevel_1)
                tlevel_2 = QTreeWidgetItem(tlevel_1, [self.parent.geol_coll.get_uid_scenario(uid)])
                tlevel_2.setFlags(tlevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable)
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
                property_combo.currentIndexChanged.connect(lambda: self.toggle_property())
                tlevel_3.setFlags(tlevel_3.flags() | Qt.ItemIsUserCheckable)
                if self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                    tlevel_3.setCheckState(0, Qt.Checked)
                elif not self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                    tlevel_3.setCheckState(0, Qt.Unchecked)
                self.TopologyTreeWidget.insertTopLevelItem(0, tlevel_3)
                break
        self.TopologyTreeWidget.itemChanged.connect(self.toggle_geology_topology_visibility)
        self.TopologyTreeWidget.expandAll()

    def set_actor_visible(self, uid=None, visible=None):
        # print(self.actors_df)
        """Set actor uid visible or invisible (visible = True or False)"""
        if isinstance(self.actors_df.loc[self.actors_df['uid'] == uid, 'actor'].values[0], Line2D):
            "Case for Line2D"
            self.actors_df.loc[self.actors_df['uid'] == uid, 'actor'].values[0].set_visible(visible)
            self.actors_df.loc[self.actors_df['uid'] == uid, 'actor'].values[0].figure.canvas.draw()
        elif isinstance(self.actors_df.loc[self.actors_df['uid'] == uid, 'actor'].values[0], PathCollection):
            "Case for PathCollection -> ax.scatter"
            pass
        elif isinstance(self.actors_df.loc[self.actors_df['uid'] == uid, 'actor'].values[0], TriContourSet):
            "Case for TriContourSet -> ax.tricontourf"
            pass
        elif isinstance(self.actors_df.loc[self.actors_df['uid'] == uid, 'actor'].values[0], AxesImage):
            "Case for AxesImage (i.e. images)"
            """Hide other images if (1) they are shown and (2) you are showing another one."""
            for hide_uid in self.actors_df.loc[(self.actors_df['collection'] == 'image_coll') & (self.actors_df['show']) & (self.actors_df['uid'] != uid), 'uid'].to_list():
                self.actors_df.loc[self.actors_df['uid'] == hide_uid, 'show'] = False
                self.actors_df.loc[self.actors_df['uid'] == hide_uid, 'actor'].values[0].set_visible(False)
                row = self.ImagesTableWidget.findItems(hide_uid, Qt.MatchExactly)[0].row()
                self.ImagesTableWidget.item(row, 0).setCheckState(Qt.Unchecked)
            """Then show this one."""
            self.actors_df.loc[self.actors_df['uid'] == uid, 'actor'].values[0].set_visible(visible)
            self.actors_df.loc[self.actors_df['uid'] == uid, 'actor'].values[0].figure.canvas.draw()
        else:
            "Do-nothing option to avoid errors, but it does not set/unset visibility."
            pass

    def remove_actor_in_view(self, uid=None, redraw=False):
        """"Remove actor from plotter"""
        """Can remove a single entity or a list of entities as actors - here we remove a single entity"""

        if not self.actors_df.loc[self.actors_df['uid'] == uid].empty:
            if self.actors_df.loc[self.actors_df['uid'] == uid, 'actor'].values[0]:
                # print(self.actors_df.loc[self.actors_df['uid'] == uid, 'actor'].values)
                # print(self.actors_df.loc[self.actors_df['uid'] == uid, 'actor'].values[0])
                self.actors_df.loc[self.actors_df['uid'] == uid, 'actor'].values[0].remove()
                self.actors_df.drop(self.actors_df[self.actors_df['uid'] == uid].index, inplace=True)
            if redraw:
                """IN THE FUTURE check if there is a way to redraw just the actor that has just been removed."""
                self.figure.canvas.draw()
                print("redraw all - a more efficient alternative should be found")

    def show_actor_with_property(self, uid=None, collection=None, show_property='Poles', visible=None,filled=None):
        if show_property is None:
            show_property='Poles'
        """Show actor with scalar property (default None)
        https://github.com/pyvista/pyvista/blob/140b15be1d4021b81ded46b1c212c70e86a98ee7/pyvista/plotting/plotting.py#L1045"""
        """First get entity from collection."""
        if collection == 'geol_coll':
            color_R = self.parent.geol_coll.get_uid_legend(uid=uid)['color_R']
            color_G = self.parent.geol_coll.get_uid_legend(uid=uid)['color_G']
            color_B = self.parent.geol_coll.get_uid_legend(uid=uid)['color_B']
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            line_thick = self.parent.geol_coll.get_uid_legend(uid=uid)['line_thick']
            plot_entity = self.parent.geol_coll.get_uid_vtk_obj(uid)
        elif collection == 'xsect_coll':
            color_R = self.parent.xsect_coll.get_legend()['color_R']
            color_G = self.parent.xsect_coll.get_legend()['color_G']
            color_B = self.parent.xsect_coll.get_legend()['color_B']
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            line_thick = self.parent.xsect_coll.get_legend()['line_thick']
            plot_entity = self.parent.xsect_coll.get_uid_vtk_frame(uid)
        else:
            plot_entity = None
        """Then plot."""
        if isinstance(plot_entity, (VertexSet, Attitude)):
            if isinstance(plot_entity.points, np.ndarray):
                if plot_entity.points_number > 0:
                    """This check is needed to avoid errors when trying to plot an empty
                    PolyData, just created at the beginning of a digitizing session.
                    Check if both these conditions are necessary_________________"""

                    self.dip_az = plot_entity.points_map_dip_azimuth
                    self.dip = plot_entity.points_map_dip


                    # [Gabriele] Dip az needs to be converted to strike (dz-90) to plot with mplstereonet
                    if uid in self.selected_uids:
                        if show_property == "Planes":
                            this_actor = self.ax.plane(self.dip_az-90,self.dip,color=color_RGB)[0]
                        else:
                            this_actor = self.ax.pole(self.dip_az-90, self.dip, color=color_RGB)[0]

                        this_actor.set_visible(visible)
                    else:
                        if show_property == "Planes":
                            this_actor = self.ax.plane(self.dip_az-90,self.dip,color=color_RGB)[0]
                        else:
                            if filled is not None and visible is True:

                                if filled:
                                    self.ax.density_contourf(self.dip_az-90, self.dip,measurement='poles')
                                else:
                                    self.ax.density_contour(self.dip_az-90, self.dip,measurement='poles')
                            this_actor = self.ax.pole(self.dip_az-90, self.dip, color=color_RGB)[0]
                        if this_actor:
                            this_actor.set_visible(visible)
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


    def change_grid(self,kind):
        self.grid_kind = kind
        self.ViewFrameLayout.removeWidget(self.canvas)
        self.ViewFrameLayout.removeWidget(self.navi_toolbar)
        self.initialize_interactor(kind=kind,projection=self.proj_type)
        uids = self.parent.geol_coll.df.loc[self.parent.geol_coll.df['topological_type']=='VertexSet','uid']


        # print(uids)
        '''[Gabriele]It is not always the case that VertexSets have normal data (are attitude measurements). When importing from shp we should add a dialog to identify VertexSets as Attitude measurements
        '''

        # att_uid_list = []
        # for uid in uids:
        #     obj = self.parent.geol_coll.get_uid_vtk_obj(uid)
        #     if isinstance(obj, Attitude):
        #         att_uid_list.append(uid)
        # print(att_uid_list)
        for uid in uids:
            show = self.actors_df.loc[self.actors_df['uid']==uid,'show'].values[0]
            self.remove_actor_in_view(uid,redraw=False)
            this_actor = self.show_actor_with_property(uid,'geol_coll',visible=show)
            self.actors_df = self.actors_df.append({'uid': uid, 'actor': this_actor, 'show': show, 'collection': 'geol_collection', 'show_prop': 'poles'}, ignore_index=True)
            #For now only geol_collection (I guess this is the only collection for attitude measurements)

    def change_proj(self,projection):
        self.proj_type = projection
        self.ViewFrameLayout.removeWidget(self.canvas)
        self.ViewFrameLayout.removeWidget(self.navi_toolbar)
        self.initialize_interactor(kind=self.grid_kind,projection=self.proj_type)
        uids = self.parent.geol_coll.df.loc[self.parent.geol_coll.df['topological_type']=='VertexSet','uid']
        for uid in uids:
            show = self.actors_df.loc[self.actors_df['uid']==uid,'show'].values[0]
            self.remove_actor_in_view(uid,redraw=False)
            this_actor=self.show_actor_with_property(uid,'geol_coll',visible=show)
            self.actors_df = self.actors_df.append({'uid': uid, 'actor': this_actor, 'show': show, 'collection': 'geol_collection', 'show_prop': 'poles'}, ignore_index=True)

    def toggle_contours(self,filled=False):

        '''[Gabriele] This is not the best way, but for now will do.
        It's a toggle switch that display kamb contours for visible poles in
        the stereoplot.'''

        self.ViewFrameLayout.removeWidget(self.canvas)
        self.ViewFrameLayout.removeWidget(self.navi_toolbar)

        self.initialize_interactor(kind=self.grid_kind,projection=self.proj_type)
        uids = self.parent.geol_coll.df.loc[self.parent.geol_coll.df['topological_type']=='VertexSet','uid']

        if self.tog_contours == -1:
            filled_opt = filled
            self.tog_contours *= -1
            print('Contours enabled')
        else:
            filled_opt = None
            self.tog_contours *= -1
            print('Contours disabled')

        for uid in uids:
            show = self.actors_df.loc[self.actors_df['uid']==uid,'show'].values[0]

            self.remove_actor_in_view(uid,redraw=False)

            this_actor=self.show_actor_with_property(uid,'geol_coll',visible=show,filled=filled_opt)
            self.actors_df = self.actors_df.append({'uid': uid, 'actor': this_actor, 'show': show, 'collection': 'geol_collection', 'show_prop': 'poles'}, ignore_index=True)
