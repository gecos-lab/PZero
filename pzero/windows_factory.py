"""windows_factory.py
PZero© Andrea Bistacchi"""

"""QT imports"""
from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QCloseEvent

"""PZero imports"""
from .base_view_window_ui import Ui_BaseViewWindow
from .entities_factory import VertexSet, PolyLine, TriSurf, TetraSolid, XsVertexSet, XsPolyLine, DEM, PCDom, MapImage, Voxet, XsVoxet, Plane, Seismics, XsTriSurf
from .helper_dialogs import input_one_value_dialog, input_text_dialog, input_combo_dialog, message_dialog, options_dialog, multiple_input_dialog, tic, toc,open_file_dialog
# from .geological_collection import GeologicalCollection
# from copy import deepcopy

"""Maths imports"""
import math
import numpy as np
import pandas as pd

""""VTK imports"""
# import vtk
""""VTK Numpy interface imports"""
# import vtk.numpy_interface.dataset_adapter as dsa
from vtk.util import numpy_support

"""3D plotting imports"""
import pyvista as pv
from pyvistaqt import QtInteractor as pvQtInteractor

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

"""Probably not-required imports"""
# import sys
# from time import sleep


"""Background color for matplotlib plots.
Could be made interactive in the future.
'fast' is supposed to make plotting large objects faster"""
mplstyle.use(['dark_background', 'fast'])


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
        self.actors_df = pd.DataFrame(columns=['uid', 'actor', 'show', 'collection', 'show_prop'])

        """Create list of selected uid's."""
        self.selected_uids = []

        """Initialize menus and tools, canvas, add actors and show it. These methods must be defined in subclasses."""
        self.initialize_menu_tools()
        self.initialize_interactor()
        self.add_all_entities()
        self.show_qt_canvas()

        """Build and show geology and topology trees, and cross-section, DOM, image, lists"""
        self.create_geology_tree()
        self.create_topology_tree()
        self.create_xsections_tree()
        self.create_boundary_list()
        self.create_mesh3d_list()
        self.create_dom_list()
        self.create_image_list()

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

        self.parent.prop_legend_cmap_modified_signal.connect(lambda this_property: self.prop_legend_cmap_modified_update_views(this_property=this_property))

    def show_qt_canvas(self):
        """Show the Qt Window"""
        self.show()

    """Methods used to build and update the geology and topology trees."""

    def create_geology_tree(self):
        """Create geology tree with checkboxes and properties"""
        self.GeologyTreeWidget.clear()
        self.GeologyTreeWidget.setColumnCount(3)
        self.GeologyTreeWidget.setHeaderLabels(['Type > Feature > Scenario > Name', 'uid', 'property'])
        self.GeologyTreeWidget.hideColumn(1)  # hide the uid column
        self.GeologyTreeWidget.setItemsExpandable(True)
        for geo_type in pd.unique(self.parent.geol_coll.df['geological_type']):
            glevel_1 = QTreeWidgetItem(self.GeologyTreeWidget, [geo_type])  # self.GeologyTreeWidget as parent -> top level
            glevel_1.setFlags(glevel_1.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable)
            for feature in pd.unique(self.parent.geol_coll.df.loc[self.parent.geol_coll.df['geological_type'] == geo_type, 'geological_feature']):
                glevel_2 = QTreeWidgetItem(glevel_1, [feature])  # glevel_1 as parent -> 1st middle level
                glevel_2.setFlags(glevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable)
                for scenario in pd.unique(self.parent.geol_coll.df.loc[(self.parent.geol_coll.df['geological_type'] == geo_type) & (self.parent.geol_coll.df['geological_feature'] == feature), 'scenario']):
                    glevel_3 = QTreeWidgetItem(glevel_2, [scenario])  # glevel_2 as parent -> 2nd middle level
                    glevel_3.setFlags(glevel_3.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable)
                    for uid in self.parent.geol_coll.df.loc[(self.parent.geol_coll.df['geological_type'] == geo_type) & (self.parent.geol_coll.df['geological_feature'] == feature) & (self.parent.geol_coll.df['scenario'] == scenario), 'uid'].to_list():
                        property_combo = QComboBox()
                        property_combo.uid = uid
                        property_combo.addItem("none")
                        property_combo.addItem("X")
                        property_combo.addItem("Y")
                        property_combo.addItem("Z")
                        for prop in self.parent.geol_coll.get_uid_properties_names(uid):
                            property_combo.addItem(prop)
                        name = self.parent.geol_coll.df.loc[self.parent.geol_coll.df['uid'] == uid, 'name'].values[0]
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
        for topo_type in pd.unique(self.parent.geol_coll.df['topological_type']):
            tlevel_1 = QTreeWidgetItem(self.TopologyTreeWidget, [topo_type])  # self.GeologyTreeWidget as parent -> top level
            tlevel_1.setFlags(tlevel_1.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable)
            for scenario in pd.unique(self.parent.geol_coll.df.loc[self.parent.geol_coll.df['topological_type'] == topo_type, 'scenario']):
                tlevel_2 = QTreeWidgetItem(tlevel_1, [scenario])  # tlevel_1 as parent -> middle level
                tlevel_2.setFlags(tlevel_2.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable)
                for uid in self.parent.geol_coll.df.loc[(self.parent.geol_coll.df['topological_type'] == topo_type) & (self.parent.geol_coll.df['scenario'] == scenario), 'uid'].to_list():
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

    def update_geology_tree_added(self, new_list=None):
        """Update geology tree without creating a new model"""
        for uid in new_list['uid']:
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

    def update_topology_tree_added(self, new_list=None):
        """Update topology tree without creating a new model"""
        for uid in new_list['uid']:
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
        self.actors_df = self.actors_df.append({'uid': uid, 'actor': this_actor, 'show': show, 'collection': collection, 'show_prop': show_property}, ignore_index=True)  # self.set_actor_visible(uid=uid, visible=show)

    """Methods used to build and update the cross-section table."""

    def create_xsections_tree(self):
        """Create XSection tree with checkboxes and properties"""
        self.XSectionTreeWidget.clear()
        self.XSectionTreeWidget.setColumnCount(2)
        self.XSectionTreeWidget.setHeaderLabels(['Name', 'uid'])
        self.XSectionTreeWidget.hideColumn(1)  # hide the uid column
        self.XSectionTreeWidget.setItemsExpandable(True)
        name_xslevel1 = ["All XSections"]
        xslevel_1 = QTreeWidgetItem(self.XSectionTreeWidget, name_xslevel1)  # self.XSectionTreeWidget as parent -> top level
        xslevel_1.setFlags(xslevel_1.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable)
        for uid in self.parent.xsect_coll.df['uid']:
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

    def update_xsections_tree_added(self, new_list=None):
        """Update XSection tree without creating a new model"""
        for uid in new_list['uid']:
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

    def create_boundary_list(self):
        """Create boundaries list with checkboxes."""
        self.BoundariesTableWidget.clear()
        self.BoundariesTableWidget.setColumnCount(2)
        self.BoundariesTableWidget.setRowCount(0)
        self.BoundariesTableWidget.setHorizontalHeaderLabels(['Name', 'uid'])
        self.BoundariesTableWidget.hideColumn(1)  # hide the uid column
        row = 0
        for uid in self.parent.boundary_coll.df['uid'].to_list():
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

    def create_mesh3d_list(self):
        """Create mesh3D list with checkboxes."""
        self.Mesh3DTableWidget.clear()
        self.Mesh3DTableWidget.setColumnCount(3)
        self.Mesh3DTableWidget.setRowCount(0)
        self.Mesh3DTableWidget.setHorizontalHeaderLabels(['Name', 'uid'])
        self.Mesh3DTableWidget.hideColumn(1)  # hide the uid column
        row = 0
        for uid in self.parent.mesh3d_coll.df['uid'].to_list():
            name = self.parent.mesh3d_coll.df.loc[self.parent.mesh3d_coll.df['uid'] == uid, 'name'].values[0]
            mesh3d_type = self.parent.mesh3d_coll.df.loc[self.parent.mesh3d_coll.df['uid'] == uid, 'mesh3d_type'].values[0]
            name_item = QTableWidgetItem(name)
            name_item.setFlags(name_item.flags() | Qt.ItemIsUserCheckable)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            uid_item = QTableWidgetItem(uid)
            property_combo = QComboBox()
            property_combo.uid = uid
            property_combo.addItem("none")
            property_combo.texture_uid_list = ["none", "X", "Y", "Z"]
            if mesh3d_type != "Voxet" and mesh3d_type != "XsVoxet":
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
        for uid in new_list['uid']:
            name = self.parent.mesh3d_coll.df.loc[self.parent.mesh3d_coll.df['uid'] == uid, 'name'].values[0]
            mesh3d_type = self.parent.mesh3d_coll.df.loc[self.parent.mesh3d_coll.df['uid'] == uid, 'mesh3d_type'].values[0]
            name_item = QTableWidgetItem(name)
            name_item.setFlags(name_item.flags() | Qt.ItemIsUserCheckable)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            uid_item = QTableWidgetItem(uid)
            property_combo = QComboBox()
            property_combo.uid = uid
            property_combo.addItem("none")
            property_combo.texture_uid_list = ["none", "X", "Y", "Z"]
            if mesh3d_type != "Voxet" and mesh3d_type != "XsVoxet":
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

    def create_dom_list(self):
        """Create cross-sections list with checkboxes."""
        self.DOMsTableWidget.clear()
        self.DOMsTableWidget.setColumnCount(3)
        self.DOMsTableWidget.setRowCount(0)
        self.DOMsTableWidget.setHorizontalHeaderLabels(['Name', 'uid','Colors'])
        self.DOMsTableWidget.hideColumn(1)  # hide the uid column
        row = 0
        for uid in self.parent.dom_coll.df['uid'].to_list():
            name = self.parent.dom_coll.df.loc[self.parent.dom_coll.df['uid'] == uid, 'name'].values[0]
            name_item = QTableWidgetItem(name)
            name_item.setFlags(name_item.flags() | Qt.ItemIsUserCheckable)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            uid_item = QTableWidgetItem(uid)
            property_texture_combo = QComboBox()
            property_texture_combo.uid = uid
            property_texture_combo.addItem("none")
            property_texture_combo.texture_uid_list = ["none", "X", "Y", "Z","RGB"]
            property_texture_combo.addItem("X")
            property_texture_combo.addItem("Y")
            property_texture_combo.addItem("Z")
            property_texture_combo.addItem("RGB")
            for prop in self.parent.dom_coll.get_uid_properties_names(uid):
                if prop not in self.parent.dom_coll.df.loc[self.parent.dom_coll.df['uid'] == uid, "texture_uids"].values[0]:
                    property_texture_combo.addItem(prop)
                    property_texture_combo.texture_uid_list.append(prop)
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

    def update_dom_list_added(self, new_list=None):
        """Update DOM list without creating a new model"""
        row = self.DOMsTableWidget.rowCount()
        for uid in new_list['uid']:
            name = self.parent.dom_coll.df.loc[self.parent.dom_coll.df['uid'] == uid, 'name'].values[0]
            name_item = QTableWidgetItem(name)
            name_item.setFlags(name_item.flags() | Qt.ItemIsUserCheckable)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            uid_item = QTableWidgetItem(uid)
            property_texture_combo = QComboBox()
            property_texture_combo.uid = uid
            property_texture_combo.addItem("none")
            property_texture_combo.texture_uid_list = ["none", "X", "Y", "Z","RGB"]
            property_texture_combo.addItem("X")
            property_texture_combo.addItem("Y")
            property_texture_combo.addItem("Z")
            property_texture_combo.addItem("RGB")
            for prop in self.parent.dom_coll.get_uid_properties_names(uid):
                if prop not in self.parent.dom_coll.df.loc[self.parent.dom_coll.df['uid'] == uid, "texture_uids"].values[0]:
                    property_texture_combo.addItem(prop)
                    property_texture_combo.texture_uid_list.append(prop)
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
        #print(uid)
        if check_state == Qt.Checked:
            if not self.actors_df.loc[self.actors_df['uid'] == uid, 'show'].values[0]:
                self.actors_df.loc[self.actors_df['uid'] == uid, 'show'] = True
                #print(self.actors_df['actor'])
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
        try:
            self.plotter.remove_scalar_bar()
        except IndexError:
            pass

        self.remove_actor_in_view(uid=uid)

        # self.plotter.remove_scalar_bar()

        this_actor = self.show_actor_with_property(uid=uid, collection=collection, show_property=property_texture_uid, visible=show)
        self.actors_df = self.actors_df.append({'uid': uid, 'actor': this_actor, 'show': show, 'collection': collection, 'show_prop': property_texture_uid}, ignore_index=True)  # self.set_actor_visible(uid=uid, visible=show)

    """Methods used to build and update the image table."""

    def create_image_list(self):
        """Create image list with checkboxes."""
        self.ImagesTableWidget.clear()
        self.ImagesTableWidget.setColumnCount(2)
        self.ImagesTableWidget.setRowCount(0)
        self.ImagesTableWidget.setHorizontalHeaderLabels(['Name', 'uid'])
        self.ImagesTableWidget.hideColumn(1)  # hide the uid column
        row = 0
        for uid in self.parent.image_coll.df['uid'].to_list():
            name = self.parent.image_coll.df.loc[self.parent.image_coll.df['uid'] == uid, 'name'].values[0]
            name_item = QTableWidgetItem(name)
            name_item.setFlags(name_item.flags() | Qt.ItemIsUserCheckable)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            uid_item = QTableWidgetItem(uid)
            self.ImagesTableWidget.insertRow(row)
            self.ImagesTableWidget.setItem(row, 0, name_item)
            self.ImagesTableWidget.setItem(row, 1, uid_item)
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
            self.ImagesTableWidget.insertRow(row)
            self.ImagesTableWidget.setItem(row, 0, name_item)
            self.ImagesTableWidget.setItem(row, 1, uid_item)
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

    """Methods used to add, remove, and update actors from the geological collection."""

    def geology_added_update_views(self, updated_list=None):
        """This is called when an entity is added to the geological collection.
        Disconnect signals to geology and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.GeologyTreeWidget.itemChanged.disconnect()
        self.TopologyTreeWidget.itemChanged.disconnect()
        """Create pandas dataframe as list of "new" actors"""
        self.actors_df_new = pd.DataFrame(columns=['uid', 'actor', 'show', 'collection', 'show_prop'])
        for uid in updated_list:
            this_actor = self.show_actor_with_property(uid=uid, collection='geol_coll', show_property=None, visible=True)
            self.actors_df = self.actors_df.append({'uid': uid, 'actor': this_actor, 'show': True, 'collection': 'geol_coll', 'show_prop': None}, ignore_index=True)
            self.actors_df_new = self.actors_df_new.append({'uid': uid, 'actor': this_actor, 'show': True, 'collection': 'geol_coll', 'show_prop': None}, ignore_index=True)
            self.update_geology_tree_added(self.actors_df_new)
            self.update_topology_tree_added(self.actors_df_new)
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
        """This is called when the color in the geological legend is modified.
        Disconnect signals to geology and topology tree, if they are set, to avoid a nasty loop
        that disrupts the trees, then they are reconnected when the trees are rebuilt"""
        self.GeologyTreeWidget.itemChanged.disconnect()
        self.TopologyTreeWidget.itemChanged.disconnect()
        for uid in updated_list:
            """Case for color changed"""
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
        self.actors_df_new = pd.DataFrame(columns=['uid', 'actor', 'show', 'collection', 'show_prop'])
        for uid in updated_list:
            this_actor = self.show_actor_with_property(uid=uid, collection='xsect_coll', show_property=None, visible=True)
            self.actors_df = self.actors_df.append({'uid': uid, 'actor': this_actor, 'show': True, 'collection': 'xsect_coll', 'show_prop': None}, ignore_index=True)
            self.actors_df_new = self.actors_df_new.append({'uid': uid, 'actor': this_actor, 'show': True, 'collection': 'xsect_coll', 'show_prop': None}, ignore_index=True)
            self.update_xsections_tree_added(self.actors_df_new)
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
        self.actors_df_new = pd.DataFrame(columns=['uid', 'actor', 'show', 'collection', 'show_prop'])
        for uid in updated_list:
            this_actor = self.show_actor_with_property(uid=uid, collection='boundary_coll', show_property=None, visible=False)
            self.actors_df = self.actors_df.append({'uid': uid, 'actor': this_actor, 'show': False, 'collection': 'boundary_coll', 'show_prop': None}, ignore_index=True)
            self.actors_df_new = self.actors_df_new.append({'uid': uid, 'actor': this_actor, 'show': False, 'collection': 'boundary_coll', 'show_prop': None}, ignore_index=True)
            self.update_boundary_list_added(self.actors_df_new)
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
        self.actors_df_new = pd.DataFrame(columns=['uid', 'actor', 'show', 'collection', 'show_prop'])
        for uid in updated_list:
            this_actor = self.show_actor_with_property(uid=uid, collection='mesh3d_coll', show_property=None, visible=False)
            self.actors_df = self.actors_df.append({'uid': uid, 'actor': this_actor, 'show': False, 'collection': 'mesh3d_coll', 'show_prop': None}, ignore_index=True)
            self.actors_df_new = self.actors_df_new.append({'uid': uid, 'actor': this_actor, 'show': False, 'collection': 'mesh3d_coll', 'show_prop': None}, ignore_index=True)
            self.update_mesh3d_list_added(self.actors_df_new)
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
        self.actors_df_new = pd.DataFrame(columns=['uid', 'actor', 'show', 'collection', 'show_prop'])
        for uid in updated_list:
            this_actor = self.show_actor_with_property(uid=uid, collection='dom_coll', show_property=None, visible=False)
            self.actors_df = self.actors_df.append({'uid': uid, 'actor': this_actor, 'show': False, 'collection': 'dom_coll', 'show_prop': None}, ignore_index=True)
            self.actors_df_new = self.actors_df_new.append({'uid': uid, 'actor': this_actor, 'show': False, 'collection': 'dom_coll', 'show_prop': None}, ignore_index=True)
            self.update_dom_list_added(self.actors_df_new)
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
        self.actors_df_new = pd.DataFrame(columns=['uid', 'actor', 'show', 'collection', 'show_prop'])
        for uid in updated_list:
            this_actor = self.show_actor_with_property(uid=uid, collection='image_coll', show_property=None, visible=False)
            self.actors_df = self.actors_df.append({'uid': uid, 'actor': this_actor, 'show': False, 'collection': 'image_coll', 'show_prop': None}, ignore_index=True)
            self.actors_df_new = self.actors_df_new.append({'uid': uid, 'actor': this_actor, 'show': False, 'collection': 'image_coll', 'show_prop': None}, ignore_index=True)
            self.update_image_list_added(self.actors_df_new)
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
            this_actor = self.show_actor_with_property(uid=uid, collection='xsect_coll', show_property=None, visible=True)
            self.actors_df = self.actors_df.append({'uid': uid, 'actor': this_actor, 'show': True, 'collection': 'xsect_coll', 'show_prop': None}, ignore_index=True)
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
        """List of selected_uids is cleared"""
        self.selected_uids = []

class View3D(BaseView):
    """Create 3D view and import UI created with Qt Designer by subclassing base view"""
    """parent is the QT object that is launching this one, hence the ProjectWindow() instance in this case"""

# [Gabriele] Set the default 3D view as x +ve. Maybe there is a better place to put this variable

    default_view = [(554532.4159059974, 5063817.5, 0.0),
 (548273.0, 5063817.5, 0.0),
 (0.0, 0.0, 1.0)]

    def __init__(self, *args, **kwargs):
        super(View3D, self).__init__(*args, **kwargs)

        """Rename Base View, Menu and Tool"""
        self.setWindowTitle("3D View")

    """Re-implementations of functions that appear in all views - see placeholders in BaseView()"""

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
        self.menuBaseView.setTitle("Project")
        self.actionBase_Tool.setText("Project")

        # [Gabriele] Options menu

        self.menuOptions = QMenu("Options",self)
        self.menuWindow.addMenu(self.menuOptions)

        self.useCube = QAction("Orientation cube", self)
        box_args = {'color_box': True,
                    'opacity':1}
        self.useCube.triggered.connect(lambda: self.plotter.add_axes(box=True,box_args=box_args))
        self.menuOptions.addAction(self.useCube)

        self.useAxis = QAction("Orientation axis", self)
        self.useAxis.triggered.connect(lambda: self.plotter.add_axes(box=False))
        self.menuOptions.addAction(self.useAxis)

        # [Gabriele] Default views menu

        self.menuView = QMenu("Views",self)
        self.menuWindow.addMenu(self.menuView)

        # [Gabriele] Save current view
        self.setView = QAction("Set view", self)
        self.setView.triggered.connect(lambda: self.view_manager("save"))
        self.menuView.addAction(self.setView)

        self.setView = QAction("Set view to active", self) # [Gabriele] If two objects are active it centers the view on the barycenter.
        self.setView.triggered.connect(lambda: self.plotter.reset_camera())
        self.menuView.addAction(self.setView)

        self.menuView.addSeparator()

        # [Gabriele] x,y,z +ve and -ve options
        self.xposView = QAction("x +ve", self)
        self.xposView.triggered.connect(lambda: self.plotter.view_yz())
        self.menuView.addAction(self.xposView)


        self.xnegView = QAction("x -ve", self)
        self.xnegView.triggered.connect(lambda: self.plotter.view_yz(True))
        self.menuView.addAction(self.xnegView)

        self.yposView = QAction("y +ve", self)
        self.yposView.triggered.connect(lambda: self.plotter.view_xz(True))
        self.menuView.addAction(self.yposView)

        self.ynegView = QAction("y -ve", self)
        self.ynegView.triggered.connect(lambda: self.plotter.view_xz())
        self.menuView.addAction(self.ynegView)

        self.zposView = QAction("z +ve", self)
        self.zposView.triggered.connect(lambda: self.plotter.view_xy())
        self.menuView.addAction(self.zposView)

        self.znegView = QAction("z -ve", self)
        self.znegView.triggered.connect(lambda: self.plotter.view_xy(True))
        self.menuView.addAction(self.znegView)

        self.menuView.addSeparator()

        # [Gabriele] Return to saved view
        self.resetView = QAction("Reset view", self)
        self.resetView.triggered.connect(lambda: self.view_manager("reset"))
        self.menuView.addAction(self.resetView)

    def view_manager(self,mode):
        if mode == "save":
                self.default_view = self.plotter.camera_position
        elif mode == "reset":
                self.plotter.camera_position = self.default_view
        #
        # self.setView = QAction(BaseViewWindow)
        # self.setView.setObjectName("setview")
        # self.menuViews.addAction("setview")



    def initialize_interactor(self):
        """Add the pyvista interactor object to self.ViewFrameLayout ->
        the layout of an empty frame generated with Qt Designer"""
        self.plotter = pvQtInteractor(self.ViewFrame)
        self.plotter.set_background('black')  # background color - could be made interactive in the future
        self.ViewFrameLayout.addWidget(self.plotter.interactor)
        self.plotter.show_axes_all()

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
        """Note: no legend for image."""
        """Update color for actor uid"""
        color_RGB = [color_R / 255, color_G / 255, color_B / 255]
        self.actors_df.loc[self.actors_df['uid'] == uid, 'actor'].values[0].GetProperty().SetColor(color_RGB)

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
            """Note: no legend for image."""
        if isinstance(self.parent.dom_coll.get_uid_vtk_obj(uid), PCDom):
            # [Gabriele] If PCDom we need to set point size not line thickness
            self.actors_df.loc[self.actors_df['uid'] == uid, 'actor'].values[0].GetProperty().SetPointSize(line_thick)
        else:
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
            #print(plot_entity)
        elif collection == 'image_coll':
            """Note: no legend for image."""
            color_RGB = [255, 255, 255]
            line_thick = 5.0
            plot_entity = self.parent.image_coll.get_uid_vtk_obj(uid)
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
        elif isinstance(plot_entity, (VertexSet, XsVertexSet)):
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
                                               plot_texture_option=False, plot_rgb_option=plot_rgb_option, visible=visible,
                                               style='points', point_size=line_thick*10.0, points_as_spheres=True)
            else:
                this_actor = None
        elif isinstance(plot_entity, DEM):
            """Show texture specified in show_property"""
            if show_property in self.parent.dom_coll.df.loc[self.parent.dom_coll.df['uid'] == uid, "texture_uids"].values[0]:
                active_image = self.parent.image_coll.df.loc[self.parent.image_coll.df['uid'] == show_property, "vtk_obj"].values[0]
                active_image_texture = active_image.texture
                active_image_bands_n = active_image.bands_n
                if active_image_bands_n == 3:
                    plot_rgb_option = True
                elif active_image_bands_n == 1:
                    plot_rgb_option = False
                this_actor = self.plot_mesh_3D(uid=uid, plot_entity=plot_entity, color_RGB=None, show_property=None, show_scalar_bar=None,
                                               color_bar_range=None, show_property_title=None, line_thick=None,
                                               plot_texture_option=active_image_texture, plot_rgb_option=plot_rgb_option, visible=visible)
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
                elif show_property == 'RGB': #[Gabriele] For now this can do
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
            file = self.parent.dom_coll.df.loc[self.parent.dom_coll.df['uid'] == uid, "name"].values[0]
            if isinstance(plot_entity.points, np.ndarray):
                """This  check is needed to avoid errors when trying to plot an empty
                PolyData, just created at the beginning of a digitizing session."""


                # [Gabriele] Basic properties
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

                    if plot_entity.get_point_data('Red').size > 1:
                        R = plot_entity.get_point_data('Red')
                        G = plot_entity.get_point_data('Green')
                        B = plot_entity.get_point_data('Blue')
                        if '.laz' in file or '.las' in file:
                            ''' [Gabriele] Las and laz files save color data in uint16 format. To conver to RGB we can divide by 255. Since show property only works with 0-1 values we divide again by 255.'''
                            R = (R/255**2)
                            G = (G/255**2)
                            B = (B/255**2)
                        elif type(R[0]) is int:
                            # [Gabriele] If is an integer divide by 255 to have it in the 0-1 range
                            R = (R/255)
                            G = (G/255)
                            B = (B/255)
                        show_property = np.array([R,G,B]).T # [Gabriele] Set color data as a 3xn matrix (w/o .T is a nx3 matrix)
                        plot_rgb_option = True # [Gabriele] Use RGB

                    else:
                        print('No RGB values present')
                        show_property = None

                else:
                    show_scalar_bar = True
                    if '.laz' in file or '.las' in file:
                        show_property = plot_entity.get_point_data(show_property)/255**2
                    else:
                        show_property = plot_entity.get_point_data(show_property)



            this_actor = self.plot_PC_3D(uid=uid,plot_entity=plot_entity,color_RGB=color_RGB, show_property=show_property, show_scalar_bar=show_scalar_bar, color_bar_range=None, show_property_title=show_property_title, plot_rgb_option=plot_rgb_option,visible=visible,point_size=line_thick)

        elif isinstance(plot_entity, MapImage):
            """Texture options according to type."""
            if plot_entity.bands_n == 3:
                plot_rgb_option = True
            elif plot_entity.bands_n == 1:
                plot_rgb_option = False
            this_actor = self.plot_mesh_3D(uid=uid, plot_entity=plot_entity.frame, color_RGB=None, show_property=None, show_scalar_bar=None,
                                           color_bar_range=None, show_property_title=None, line_thick=None,
                                           plot_texture_option=plot_entity.texture, plot_rgb_option=plot_rgb_option, visible=visible)
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
                this_actor = self.plot_mesh_3D(uid=uid, plot_entity=plot_entity, color_RGB=color_RGB, show_property=show_property, show_scalar_bar=show_scalar_bar,
                                               color_bar_range=None, show_property_title=show_property_title, line_thick=line_thick,
                                               plot_texture_option=False, plot_rgb_option=plot_rgb_option, visible=visible)
            else:
                this_actor = None
        else:
            print("[Windows factory]: actor with no class")
            this_actor = None
        return this_actor

    def plot_mesh_3D(self, uid=None, plot_entity=None, color_RGB=None, show_property=None, show_scalar_bar=None,
                     color_bar_range=None, show_property_title=None, line_thick=None,
                     plot_texture_option=None, plot_rgb_option=None, visible=None,
                     style='surface', point_size=5.0, points_as_spheres=False):
        if not self.actors_df.empty:
            """This stores the camera position before redrawing the actor.
            Added to avoid a bug that sometimes sends the scene to a very distant place.
            Could be used as a basis to implement saved views widgets, synced 3D views, etc.
            The is is needed to avoid sending the camera to the origin that is the
            default position before any mesh is plotted."""
            camera_position = self.plotter.camera_position
        if show_property is not None:
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
                                           render_lines_as_tubes=False,
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
                                           pickable=True,  # bool
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

    def plot_PC_3D(self, uid=None, plot_entity=None,visible=None,color_RGB=None, show_property=None, show_scalar_bar=None, color_bar_range=None, show_property_title=None, plot_rgb_option=None, point_size=5.0, points_as_spheres=True):
        '''[Gabriele]  Plot the point cloud'''

        if not self.actors_df.empty:
            """This stores the camera position before redrawing the actor.
            Added to avoid a bug that sometimes sends the scene to a very distant place.
            Could be used as a basis to implement saved views widgets, synced 3D views, etc.
            The is is needed to avoid sending the camera to the origin that is the
            default position before any mesh is plotted."""
            camera_position = self.plotter.camera_position

        # [Gabriele] if rgb options is true -> there is no need of cmap
        if show_property is not None and plot_rgb_option == None:
            show_property_cmap = self.parent.prop_legend_df.loc[self.parent.prop_legend_df['property_name'] == show_property_title, "colormap"].values[0]
        else:
            show_property_cmap = None
        this_actor= self.plotter.add_points(plot_entity,name=uid,
                                            point_size=point_size,
                                            render_points_as_spheres=points_as_spheres,
                                            color=color_RGB,
                                            scalars=show_property,
                                            n_colors=256,
                                            clim=color_bar_range,
                                            flip_scalars=False,
                                            interpolate_before_map=True,
                                            cmap=show_property_cmap,
                                            scalar_bar_args={'title': show_property_title, 'title_font_size': 20, 'label_font_size': 16, 'shadow': True, 'interactive': True,'fmt':"%.1f"},
                                            rgb=plot_rgb_option,
                                            show_scalar_bar=show_scalar_bar)



        if not visible:
            this_actor.SetVisibility(False)
        if not self.actors_df.empty:
            """See above."""
            self.plotter.camera_position = camera_position
        return this_actor



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
                    self.temp_vbm_length = math.sqrt(self.temp_vbm_dU ** 2 + self.temp_vbm_dV ** 2)
                    self.temp_vbm_azimuth = math.degrees(math.atan2(self.temp_vbm_dU, self.temp_vbm_dV))
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
        from .xsection_collection import section_from_azimuth, section_from_points
        from .boundary_collection import boundary_from_points

        self.sectionFromAzimuthButton = QAction('Section from Azimuth', self)  # create action
        self.sectionFromAzimuthButton.triggered.connect(lambda: section_from_azimuth(self))  # connect action to function with additional argument parent
        self.menuBaseView.addAction(self.sectionFromAzimuthButton)  # add action to menu
        self.toolBarBase.addAction(self.sectionFromAzimuthButton)  # add action to toolbar

        self.sectionFromPointsButton = QAction('Section from 2 points', self)  # create action
        self.sectionFromPointsButton.triggered.connect(lambda: section_from_points(self))  # connect action to function with additional argument parent
        self.menuBaseView.addAction(self.sectionFromPointsButton)  # add action to menu
        self.toolBarBase.addAction(self.sectionFromPointsButton)  # add action to toolbar

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
            plot_entity = self.parent.image_coll.get_uid_vtk_obj(uid)
        """Then plot."""
        if isinstance(plot_entity, (VertexSet, PolyLine, XsVertexSet, XsPolyLine)):
            if isinstance(plot_entity.points, np.ndarray):
                if plot_entity.points_number > 0:
                    """This  check is needed to avoid errors when trying to plot an empty
                    PolyData, just created at the beginning of a digitizing session.
                    Check if both these conditions are necessary_________________"""
                    X = plot_entity.points_X
                    Y = plot_entity.points_Y
                    if isinstance(plot_entity, VertexSet):
                        if uid in self.selected_uids:
                            if show_property == "Normals":
                                U = np.sin(plot_entity.points_map_dip_azimuth * np.pi / 180)
                                V = np.cos(plot_entity.points_map_dip_azimuth * np.pi / 180)
                                # in quiver scale=40 means arrow is 1/40 of figure width, (shaft) width is scaled to figure width, head length and width are scaled to shaft
                                this_actor = self.ax.quiver(X, Y, U, V, pivot='mid', scale=40, width=0.005, headlength=3, headaxislength=3, facecolor=color_RGB, edgecolor='white', linewidth=1)
                            else:
                                this_actor, = self.ax.plot(X, Y, color=color_RGB, linestyle='', marker='o', markersize=12, markeredgecolor='white', label=uid, picker=True)
                            this_actor.set_visible(visible)
                        else:
                            if show_property == "Normals":
                                U = np.sin(plot_entity.points_map_dip_azimuth * np.pi / 180)
                                V = np.cos(plot_entity.points_map_dip_azimuth * np.pi / 180)
                                # in quiver scale=40 means arrow is 1/40 of figure width, (shaft) width is scaled to figure width, head length and width are scaled to shaft
                                this_actor = self.ax.quiver(X, Y, U, V, pivot='mid', scale=40, width=0.005, headlength=3, headaxislength=3, facecolor=color_RGB, edgecolor='white', linewidth=1)
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
                    if plot_entity.bands_n == 3:
                        """RGB for 3-bands images"""
                        this_actor = self.ax.imshow(plot_entity.image_data, origin='upper', extent=xy_bounds, zorder=0)
                    elif plot_entity.bands_n == 1:
                        """Greyscale for single band images"""
                        this_actor = self.ax.imshow(plot_entity.image_data, origin='upper', extent=xy_bounds, zorder=0, cmap='Greys_r')
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
        this_actor.figure.canvas.draw()
        return this_actor

    """Implementation of functions specific to this view (e.g. particular editing or visualization functions)"""


class ViewXsection(View2D):
    """Create map view and import UI created with Qt Designer by subclassing base view"""
    """parent is the QT object that is launching this one, hence the ProjectWindow() instance in this case"""

    def __init__(self, parent=None, *args, **kwargs):
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

    """Implementation of functions specific to 2D views"""

    def initialize_menu_tools(self):
        """Inheritance of common tools"""
        super().initialize_menu_tools()
        """Tools specific to Xsection view"""
        """NONE AT THE MOMENT"""

    def show_actor_with_property(self, uid=None, collection=None, show_property=None, visible=None):
        """Show actor with scalar property (default None)
        https://github.com/pyvista/pyvista/blob/140b15be1d4021b81ded46b1c212c70e86a98ee7/pyvista/plotting/plotting.py#L1045"""
        if collection == 'geol_coll':
            if ((self.parent.geol_coll.get_uid_topological_type(uid) == "XsVertexSet" or
                self.parent.geol_coll.get_uid_topological_type(uid) == "XsPolyLine") and
                self.parent.geol_coll.get_uid_x_section(uid) == self.this_x_section_uid):
                color_R = self.parent.geol_coll.get_uid_legend(uid=uid)['color_R']
                color_G = self.parent.geol_coll.get_uid_legend(uid=uid)['color_G']
                color_B = self.parent.geol_coll.get_uid_legend(uid=uid)['color_B']
                color_RGB = [color_R / 255, color_G / 255, color_B / 255]
                line_thick = self.parent.geol_coll.get_uid_legend(uid=uid)['line_thick']
                plot_entity = self.parent.geol_coll.get_uid_vtk_obj(uid)
            else:
                # print(uid, " Entities belonging to other x_sections and to XsVertexSet or XsPolyLine classes cannot be plot in this x_section.")
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
                # print(uid, " Other x_sections cannot be plot in this x_section.")
                plot_entity = None
        elif collection == 'boundary_coll':
            if (self.parent.boundary_coll.get_uid_topological_type(uid) == "XsPolyLine" and
                self.parent.boundary_coll.get_uid_x_section(uid) == self.this_x_section_uid):
                    color_R = self.parent.boundary_coll.get_legend()['color_R']
                    color_G = self.parent.boundary_coll.get_legend()['color_G']
                    color_B = self.parent.boundary_coll.get_legend()['color_B']
                    color_RGB = [color_R / 255, color_G / 255, color_B / 255]
                    line_thick = self.parent.boundary_coll.get_legend()['line_thick']
                    plot_entity = self.parent.boundary_coll.get_uid_vtk_obj(uid)
            else:
                # print(uid, " Entities belonging to other x_sections and XsVoxet class cannot be plot in this x_section.")
                plot_entity = None
        elif collection == 'mesh3d_coll':
            if (self.parent.mesh3d_coll.get_uid_mesh3d_type(uid) == "XsVoxet" and
                self.parent.mesh3d_coll.get_uid_x_section(uid) == self.this_x_section_uid):
                    color_R = self.parent.mesh3d_coll.get_legend()['color_R']
                    color_G = self.parent.mesh3d_coll.get_legend()['color_G']
                    color_B = self.parent.mesh3d_coll.get_legend()['color_B']
                    color_RGB = [color_R / 255, color_G / 255, color_B / 255]
                    line_thick = self.parent.mesh3d_coll.get_legend()['line_thick']
                    plot_entity = self.parent.mesh3d_coll.get_uid_vtk_obj(uid)
            else:
                # print(uid, " Entities belonging to other x_sections and XsVoxet class cannot be plot in this x_section.")
                plot_entity = None
        elif collection == 'dom_coll':
            if (self.parent.dom_coll.get_uid_dom_type(uid) == "DomXs" and
                self.parent.dom_coll.get_uid_x_section(uid) == self.this_x_section_uid):
                    color_R = self.parent.dom_coll.get_legend()['color_R']
                    color_G = self.parent.dom_coll.get_legend()['color_G']
                    color_B = self.parent.dom_coll.get_legend()['color_B']
                    color_RGB = [color_R / 255, color_G / 255, color_B / 255]
                    line_thick = self.parent.dom_coll.get_legend()['line_thick']
                    plot_entity = self.parent.dom_coll.get_uid_vtk_obj(uid)
            else:
                # print(uid, " Entities belonging to other x_sections and DomXs class cannot be plot in this x_section.")
                plot_entity = None
        elif collection == 'image_coll':
            """To be updated in future for Xsection images______________________"""
            # print(uid, " Images still not supported in x_section.")
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
            else:
                if isinstance(plot_entity.points, np.ndarray):
                    if plot_entity.points_number > 0:
                        """This  check is needed to avoid errors when trying to plot an empty
                        PolyData, just created at the beginning of a digitizing session.
                        Check if both these conditions are necessary_________________"""
                        W = plot_entity.points_W
                        Z = plot_entity.points_Z
                        if isinstance(plot_entity, XsVertexSet):
                            if uid in self.selected_uids:
                                if show_property == "Normals":
                                    U = np.cos(plot_entity.points_xs_app_dip * np.pi / 180)
                                    V = np.sin(plot_entity.points_xs_app_dip * np.pi / 180)
                                    # in quiver scale=40 means arrow is 1/40 of figure width, (shaft) width is scaled to figure width, head length and width are scaled to shaft
                                    this_actor = self.ax.quiver(W, Z, U, V, pivot='mid', scale=50, width=0.002, headwidth=1, headlength=0.01, headaxislength=0.01, facecolor=color_RGB, edgecolor='white', linewidth=1)
                                else:
                                    this_actor, = self.ax.plot(W, Z, color=color_RGB, linestyle='', marker='o', markersize=12, markeredgecolor='white', label=uid, picker=True)
                                this_actor.set_visible(visible)
                            else:
                                if show_property == "Normals":
                                    U = np.cos(plot_entity.points_xs_app_dip * np.pi / 180)
                                    V = -np.sin(plot_entity.points_xs_app_dip * np.pi / 180)
                                    # in quiver scale=40 means arrow is 1/40 of figure width, (shaft) width is scaled to figure width, head length and width are scaled to shaft
                                    this_actor = self.ax.quiver(W, Z, U, V, pivot='mid', scale=50, width=0.002, headwidth=1, headlength=0.01, headaxislength=0.01, facecolor=color_RGB, edgecolor='white', linewidth=1)
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

    """Implementation of functions specific to this view (e.g. particular editing or visualization functions)"""
    """NONE AT THE MOMENT"""
