"""project_window.py
PZero© Andrea Bistacchi"""

import os
from copy import deepcopy
from datetime import datetime
from shutil import copy2

from PyQt5.QtWidgets import QMainWindow, QMessageBox, QProgressDialog
from PyQt5.QtCore import Qt, pyqtSignal, QSortFilterProxyModel
import vtk
import pandas as pd
from .project_window_ui import Ui_ProjectWindow
from .entities_factory import Plane, VertexSet, PolyLine, TriSurf, XsVertexSet, XsPolyLine, DEM, MapImage, Voxet, Seismics, XsVoxet, TetraSolid, PCDom, TSDom
from .geological_collection import GeologicalCollection
from .xsection_collection import XSectionCollection
from .dom_collection import DomCollection
from .image_collection import ImageCollection
from .mesh3d_collection import Mesh3DCollection
from .boundary_collection import BoundaryCollection
from .legend_manager import Legend
from .properties_manager import PropertiesCMaps
from .gocad2vtk import gocad2vtk, vtk2gocad, gocad2vtk_section, gocad2vtk_boundary
from .pyvista2vtk import pyvista2vtk
from .vedo2vtk import vedo2vtk
from .shp2vtk import shp2vtk
from .dem2vtk import dem2vtk
from .dxf2vtk import vtk2dxf
from .segy2vtk import segy2vtk
from .windows_factory import View3D
from .windows_factory import ViewMap
from .windows_factory import ViewXsection
from .helper_dialogs import options_dialog, save_file_dialog, open_file_dialog, input_combo_dialog, message_dialog, multiple_input_dialog, input_one_value_dialog, input_text_dialog, progress_dialog
from .image2vtk import geo_image2vtk
from .stl2vtk import vtk2stl, vtk2stl_dilation
from .obj2vtk import vtk2obj
from .ply2vtk import vtk2ply
from .three_d_surfaces import interpolation_delaunay_2d, poisson_interpolation, implicit_model_loop_structural, surface_smoothing, linear_extrusion, decimation_pro_resampling, decimation_quadric_resampling, subdivision_resampling, intersection_xs, project_2_dem, project_2_xs
from .orientation_analysis import set_normals


class ProjectWindow(QMainWindow, Ui_ProjectWindow):
    """Create project window and import UI created with Qt Designer by subclassing both"""

    """Signals defined here are meant to be broadcast TO ALL views. This is why we use signals
    instead of functions that will act within a single view only. They all pass a list of uid's."""
    geology_added_signal = pyqtSignal(list)
    geology_removed_signal = pyqtSignal(list)
    geology_geom_modified_signal = pyqtSignal(list)  # this includes topology modified
    geology_data_keys_removed_signal = pyqtSignal(list)
    geology_data_val_modified_signal = pyqtSignal(list)
    geology_metadata_modified_signal = pyqtSignal(list)
    geology_legend_color_modified_signal = pyqtSignal(list)
    geology_legend_thick_modified_signal = pyqtSignal(list)

    xsect_added_signal = pyqtSignal(list)
    xsect_removed_signal = pyqtSignal(list)
    xsect_geom_modified_signal = pyqtSignal(list)  # this includes topology modified
    xsect_metadata_modified_signal = pyqtSignal(list)
    xsect_legend_color_modified_signal = pyqtSignal(list)
    xsect_legend_thick_modified_signal = pyqtSignal(list)

    boundary_added_signal = pyqtSignal(list)
    boundary_removed_signal = pyqtSignal(list)
    boundary_geom_modified_signal = pyqtSignal(list)  # this includes topology modified
    boundary_metadata_modified_signal = pyqtSignal(list)
    boundary_legend_color_modified_signal = pyqtSignal(list)
    boundary_legend_thick_modified_signal = pyqtSignal(list)

    mesh3d_added_signal = pyqtSignal(list)
    mesh3d_removed_signal = pyqtSignal(list)
    mesh3d_data_keys_removed_signal = pyqtSignal(list)
    mesh3d_data_val_modified_signal = pyqtSignal(list)
    mesh3d_metadata_modified_signal = pyqtSignal(list)
    mesh3d_legend_color_modified_signal = pyqtSignal(list)
    mesh3d_legend_thick_modified_signal = pyqtSignal(list)

    dom_added_signal = pyqtSignal(list)
    dom_removed_signal = pyqtSignal(list)
    dom_data_keys_removed_signal = pyqtSignal(list)
    dom_data_val_modified_signal = pyqtSignal(list)
    dom_metadata_modified_signal = pyqtSignal(list)
    dom_legend_color_modified_signal = pyqtSignal(list)
    dom_legend_thick_modified_signal = pyqtSignal(list)

    image_added_signal = pyqtSignal(list)
    image_removed_signal = pyqtSignal(list)
    image_metadata_modified_signal = pyqtSignal(list)

    prop_legend_cmap_modified_signal = pyqtSignal(str)

    """IN THE FUTURE add signals for other collections here___________________________"""

    def __init__(self, *args, **kwargs):
        super(ProjectWindow, self).__init__(*args, **kwargs)
        self.setupUi(self)

        """Connect actionQuit.triggered SIGNAL to self.close SLOT"""
        self.actionQuit.triggered.connect(self.close)

        """Welcome message"""
        self.TextTerminal.appendPlainText("Welcome to PZero!\n3D modelling application by Andrea Bistacchi, started June 3rd 2020.")

        startup_option = options_dialog(title='PZero', message='Do you want to create a new project or open an old one?', yes_role='New Project', no_role='Old Project', reject_role='Close')
        if startup_option == 0:
            self.TextTerminal.appendPlainText("Creating a new empty project.")
            self.new_project()
        elif startup_option == 1:
            self.TextTerminal.appendPlainText("Opening an old project.")
            self.open_project()
        else:
            self.close(True)  # this actually crashes the application, but at the moment I do not have another working solution to close it

        """File>Project actions -> slots"""
        self.actionProjectNew.triggered.connect(self.new_project)
        self.actionProjectOpen.triggered.connect(self.open_project)
        self.actionProjectSave.triggered.connect(self.save_project)

        """File>Import actions -> slots"""
        self.actionImportGocad.triggered.connect(self.import_gocad)
        self.actionImportGocadXsection.triggered.connect(self.import_gocad_section)
        self.actionImportGocadBoundary.triggered.connect(self.import_gocad_boundary)  #_______________________________________
        self.actionImportPyvista.triggered.connect(lambda: pyvista2vtk(self=self))
        self.actionImportVedo.triggered.connect(lambda: vedo2vtk(self=self))
        self.actionImportSHP.triggered.connect(self.import_SHP)
        self.actionImportDEM.triggered.connect(self.import_DEM)
        self.actionImportOrthoImage.triggered.connect(self.import_image)
        self.actionImportSEGY.triggered.connect(self.import_SEGY)

        """File>Export actions -> slots"""
        self.actionExportCAD.triggered.connect(self.export_cad)

        """Edit actions -> slots"""
        self.actionEditEntityRemove.triggered.connect(self.entity_remove)
        self.actionMergeEntities.triggered.connect(self.entities_merge)
        self.actionEditTextureAdd.triggered.connect(self.texture_add)
        self.actionEditTextureRemove.triggered.connect(self.texture_remove)
        self.actionAddProperty.triggered.connect(self.property_add)
        self.actionRemoveProperty.triggered.connect(self.property_remove)
        self.actionCalculateNormal.triggered.connect(self.normals_calculate)
        self.actionCalculateLineation.triggered.connect(self.lineations_calculate)

        """Interpolation actions -> slots"""
        self.actionDelaunay2DInterpolation.triggered.connect(lambda: interpolation_delaunay_2d(self))
        self.actionPoissonInterpolation.triggered.connect(lambda: poisson_interpolation(self))
        self.actionLoopStructuralImplicitModelling.triggered.connect(lambda: implicit_model_loop_structural(self))
        self.actionSurfaceSmoothing.triggered.connect(lambda: surface_smoothing(self))
        self.actionSubdivisionResampling.triggered.connect(lambda: subdivision_resampling(self))
        self.actionDecimationPro.triggered.connect(lambda: decimation_pro_resampling(self))
        self.actionDecimationQuadric.triggered.connect(lambda: decimation_quadric_resampling(self))
        self.actionExtrusion.triggered.connect(lambda: linear_extrusion(self))
        self.actionProject2DEM.triggered.connect(lambda: project_2_dem(self))
        self.actionIntersectionXSection.triggered.connect(lambda: intersection_xs(self))
        self.actionProject2XSection.triggered.connect(lambda: project_2_xs(self))

        """View actions -> slots"""
        self.actionView3D.triggered.connect(lambda: View3D(parent=self))
        self.actionViewMap.triggered.connect(lambda: ViewMap(parent=self))
        self.actionViewPlaneXsection.triggered.connect(lambda: ViewXsection(parent=self))
        # self.actionViewStereoplot.triggered.connect(lambda: ViewStereoplot(parent=self))

    def closeEvent(self, event):
        """Re-implement the standard closeEvent method of QWidget and ask (1) to save project, and (2) for confirmation to quit."""
        reply = QMessageBox.question(self, 'Closing Pzero', 'Save the project?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.save_project()
        reply = QMessageBox.question(self, 'Closing Pzero', 'Confirm quit?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            event.accept()
        else:
            event.ignore()

    """Methods used to manage the entities shown in tables."""

    @property
    def shown_table(self):
        """Returns which collection table tab is shown (if any)."""
        return self.tabCentral.currentWidget().objectName()

    @property
    def selected_uids(self):
        """Returns a list of uids selected in the table view. Just rows completely selected are returned."""
        if self.shown_table == "tabGeology":
            selected_idxs_proxy = self.GeologyTableView.selectionModel().selectedRows()
            selected_idxs = []
            for idx_proxy in selected_idxs_proxy:
                selected_idxs.append(self.proxy_geol_coll.mapToSource(idx_proxy))
            selected_uids = []
            for idx in selected_idxs:
                selected_uids.append(self.geol_coll.data(index=idx, role=Qt.DisplayRole))
            return selected_uids
        elif self.shown_table == "tabXSections":
            selected_idxs_proxy = self.XSectionsTableView.selectionModel().selectedRows()
            selected_idxs = []
            for idx_proxy in selected_idxs_proxy:
                selected_idxs.append(self.proxy_xsect_coll.mapToSource(idx_proxy))
            selected_uids = []
            for idx in selected_idxs:
                selected_uids.append(self.xsect_coll.data(index=idx, role=Qt.DisplayRole))
            return selected_uids
        elif self.shown_table == "tabMeshes3D":
            selected_idxs_proxy = self.Meshes3DTableView.selectionModel().selectedRows()
            selected_idxs = []
            for idx_proxy in selected_idxs_proxy:
                selected_idxs.append(self.proxy_mesh3d_coll.mapToSource(idx_proxy))
            selected_uids = []
            for idx in selected_idxs:
                selected_uids.append(self.mesh3d_coll.data(index=idx, role=Qt.DisplayRole))
            return selected_uids
        elif self.shown_table == "tabDOMs":
            selected_idxs_proxy = self.DOMsTableView.selectionModel().selectedRows()
            selected_idxs = []
            for idx_proxy in selected_idxs_proxy:
                selected_idxs.append(self.proxy_dom_coll.mapToSource(idx_proxy))
            selected_uids = []
            for idx in selected_idxs:
                selected_uids.append(self.dom_coll.data(index=idx, role=Qt.DisplayRole))
            return selected_uids
        elif self.shown_table == "tabImages":
            selected_idxs_proxy = self.ImagesTableView.selectionModel().selectedRows()
            selected_idxs = []
            for idx_proxy in selected_idxs_proxy:
                selected_idxs.append(self.proxy_image_coll.mapToSource(idx_proxy))
            selected_uids = []
            for idx in selected_idxs:
                selected_uids.append(self.image_coll.data(index=idx, role=Qt.DisplayRole))
            return selected_uids
        elif self.shown_table == "tabBoundaries":  #_________________________________________________
            selected_idxs_proxy = self.BoundariesTableView.selectionModel().selectedRows()  #_________________________________________________
            selected_idxs = []
            for idx_proxy in selected_idxs_proxy:
                selected_idxs.append(self.proxy_boundary_coll.mapToSource(idx_proxy))  #_________________________________________________
            selected_uids = []
            for idx in selected_idxs:
                selected_uids.append(self.boundary_coll.data(index=idx, role=Qt.DisplayRole))  #_________________________________________________
            return selected_uids
        elif self.shown_table == "tabLegend":
            pass
        elif self.shown_table == "tabProperties":
            pass
        elif self.shown_table == "tabTerminal":
            pass

    def entity_remove(self):
        """Remove entities selected in attributes table. Just rows completely selected are removed."""
        if not self.selected_uids:
            return
        """Confirm removal dialog."""
        check = QMessageBox.question(self, "Remove Entities", ("Do you really want to remove entities\n" + str(self.selected_uids) + "\nPlease confirm."), QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if check == QMessageBox.No:
            return
        """Remove entities."""
        for uid in self.selected_uids:
            if self.shown_table == "tabGeology":
                self.geol_coll.remove_entity(uid=uid)
            elif self.shown_table == "tabXSections":
                self.xsect_coll.remove_entity(uid=uid)
            elif self.shown_table == "tabMeshes3D":
                self.mesh3d_coll.remove_entity(uid=uid)
            elif self.shown_table == "tabDOMs":
                self.dom_coll.remove_entity(uid=uid)
            elif self.shown_table == "tabImages":
                self.image_coll.remove_entity(uid=uid)
            elif self.shown_table == "tabBoundaries":
                self.boundary_coll.remove_entity(uid=uid)  #_________________________________________________

    def entities_merge(self):  # ____________________________________________________________________MOVE THIS TO GEOLOGICAL COLL & MAKE ANOTHER FOR BOUNDARY COLL
        """Merge entities of the same type - VertexSet, PolyLine, TriSurf, ..."""
        """Check if some vtkPolyData is selected"""
        if not self.selected_uids:
            return
        """Create deepcopy of the geological entity dictionary."""
        new_dict = deepcopy(self.geol_coll.geological_entity_dict)
        input_dict = {'topological_type': ['Topological type', ['VertexSet', 'PolyLine', 'TriSurf', 'XsVertexSet', 'XsPolyLine']],
                      'name': ['New name: ', self.geol_coll.get_uid_name(self.selected_uids[0])],
                      'geological_feature': ['Geological feature: ', self.geol_coll.get_uid_geological_feature(self.selected_uids[0])],
                      'scenario': ['Scenario: ', self.geol_coll.get_uid_scenario(self.selected_uids[0])],
                      'geological_type': ['Geological type: ', GeologicalCollection.valid_geological_types]}
        updt_dict = multiple_input_dialog(title='Merge entities', input_dict=input_dict)
        """Check if the output of the widget is empty or not. If the Cancel button was clicked, the tool quits"""
        if updt_dict is None:
            return
        """Getting the values that have been typed by the user through the multiple input widget"""
        for key in updt_dict:
            new_dict[key] = updt_dict[key]
        if new_dict['topological_type'] == 'VertexSet':
            new_dict['vtk_obj'] = VertexSet()
        elif new_dict['topological_type'] == 'PolyLine':
            new_dict['vtk_obj'] = PolyLine()
        elif new_dict['topological_type'] == 'TriSurf':
            new_dict['vtk_obj'] = TriSurf()
        elif new_dict['topological_type'] == 'XsVertexSet':
            new_dict['vtk_obj'] = XsVertexSet()
        elif new_dict['topological_type'] == 'XsPolyLine':
            new_dict['vtk_obj'] = XsPolyLine()
        else:
            return
        """Create a vtkAppenPolyData filter to merge all input vtk objects"""
        vtkappend = vtk.vtkAppendPolyData()
        """Loop that collects all selected items to create the merge. Only entities that have the topological_type
        chosen in the widget are merged, others are discarded."""
        count = 0
        for uid in self.selected_uids:
            if new_dict['topological_type'] == self.geol_coll.get_uid_topological_type(self.selected_uids[count]):
                vtkappend.AddInputData(self.geol_coll.get_uid_vtk_obj(uid))
            count += 1
        vtkappend.Update()
        """ShallowCopy is the way to copy the new interpolated surface into the TriSurf instance created at the beginning"""
        new_dict['vtk_obj'].ShallowCopy(vtkappend.GetOutput())
        new_dict['vtk_obj'].Modified()
        """Add new entity from surf_dict. Function add_entity_from_dict creates a new uid"""
        uid_new = self.geol_coll.add_entity_from_dict(new_dict)

    def texture_add(self):
        """Add texture to selected DEMs. Just rows completely selected are considered."""
        if not self.shown_table == "tabDOMs":
            return
        if not self.selected_uids:
            return
        """Map Image selection dialog."""
        map_image_uids = self.image_coll.df.loc[self.image_coll.df['image_type'] == "MapImage", 'uid'].to_list()
        map_image_uid = input_combo_dialog(parent=None, title="Add texture to DEM", label="Choose Map Image", choice_list=map_image_uids)
        """Add textures."""
        dom_uids = self.selected_uids
        if not map_image_uid in self.image_coll.get_uids():
            return
        for dom_uid in dom_uids:
            if isinstance(self.dom_coll.get_uid_vtk_obj(dom_uid), DEM):
                self.dom_coll.add_map_texture_to_dom(dom_uid=dom_uid, map_image_uid=map_image_uid)

    def texture_remove(self):
        """Remove texture to selected DEMs. Just rows completely selected are considered."""
        if not self.shown_table == "tabDOMs":
            return
        if not self.selected_uids:
            return
        map_image_uids = self.image_coll.df.loc[self.image_coll.df['image_type'] == "MapImage", 'uid'].to_list()
        map_image_uid = input_combo_dialog(parent=None, title="Add texture to DEM", label="Choose Map Image", choice_list=map_image_uids)
        """Remove textures."""
        if map_image_uid in self.image_coll.get_uids():
            dom_uids = self.selected_uids
            for dom_uid in dom_uids:
                self.dom_coll.remove_map_texture_from_dom(dom_uid=dom_uid, map_image_uid=map_image_uid)

    def property_add(self):
        """Add empty property on geological entity"""
        if not self.shown_table in ["tabGeology", "tabMeshes3D", "tabDOMs"]:
            return
        if not self.selected_uids:
            return
        input_dict = {'property_name': ['Property name: ', ''], 'property_components': ['Property components: ', 1]}
        updt_dict = multiple_input_dialog(title='Add empty property', input_dict=input_dict)
        if self.shown_table == "tabGeology":
            for uid in self.selected_uids:
                if not updt_dict['property_name'] in self.geol_coll.get_uid_properties_names(uid):
                    self.geol_coll.append_uid_property(uid=uid, property_name=updt_dict['property_name'], property_components=updt_dict['property_components'])
        elif self.shown_table == "tabMeshes3D":
            for uid in self.selected_uids:
                if not updt_dict['property_name'] in self.mesh3d_coll.get_uid_properties_names(uid):
                    self.mesh3d_coll.append_uid_property(uid=uid, property_name=updt_dict['property_name'], property_components=updt_dict['property_components'])
        elif self.shown_table == "tabDOMs":
            for uid in self.selected_uids:
                if not updt_dict['property_name'] in self.dom_coll.get_uid_properties_names(uid):
                    self.dom_coll.append_uid_property(uid=uid, property_name=updt_dict['property_name'], property_components=updt_dict['property_components'])
        """Finally update properties legend."""
        self.prop_legend.update_widget(self)

    def property_remove(self):
        if not self.shown_table in ["tabGeology", "tabMeshes3D", "tabDOMs"]:
            return
        if not self.selected_uids:
            return
        if self.shown_table == "tabGeology":
            property_name_list = self.geol_coll.get_uid_properties_names(uid=self.selected_uids[0])
            if len(self.selected_uids) > 1:
                for uid in self.selected_uids[1:]:
                    property_name_list = list(set(property_name_list) & set(self.geol_coll.get_uid_properties_names(uid=uid)))
            if property_name_list == []:
                return
            property_name = input_combo_dialog(parent=None, title="Remove selected property", label="Remove property", choice_list=property_name_list)
            for uid in self.selected_uids:
                self.geol_coll.remove_uid_property(uid=uid, property_name=property_name)
        elif self.shown_table == "tabMeshes3D":
            property_name_list = self.mesh3d_coll.get_uid_properties_names(uid=self.selected_uids[0])
            if len(self.selected_uids) > 1:
                for uid in self.selected_uids[1:]:
                    property_name_list = list(set(property_name_list) & set(self.mesh3d_coll.get_uid_properties_names(uid=uid)))
            if property_name_list == []:
                return
            property_name = input_combo_dialog(parent=None, title="Remove selected property", label="Remove property", choice_list=property_name_list)
            for uid in self.selected_uids:
                self.mesh3d_coll.remove_uid_property(uid=uid, property_name=property_name)
        elif self.shown_table == "tabDOMs":
            property_name_list = self.dom_coll.get_uid_properties_names(uid=self.selected_uids[0])
            if len(self.selected_uids) > 1:
                for uid in self.selected_uids[1:]:
                    property_name_list = list(set(property_name_list) & set(self.dom_coll.get_uid_properties_names(uid=uid)))
            if property_name_list == []:
                return
            property_name = input_combo_dialog(parent=None, title="Remove selected property", label="Remove property", choice_list=property_name_list)
            for uid in self.selected_uids:
                self.dom_coll.remove_uid_property(uid=uid, property_name=property_name)
        """Finally update properties legend."""
        self.prop_legend.update_widget(self)

    def normals_calculate(self):
        """Calculate Normals on geological entities (add point clouds and DOMS in the future)."""
        if self.shown_table in ["tabGeology", "tabMeshes3D", "tabDOMs"]:
            if self.selected_uids:
                set_normals(self)

    def lineations_calculate(self):
        """Calculate lineations on geological entities."""
        pass

    """Methods used to save/open/create new projects."""

    def create_empty(self):
        """Create empty containers for a new empty project."""

        """Create the geol_coll GeologicalCollection (a Qt QAbstractTableModel with a Pandas dataframe as attribute)
        and connect the model to GeologyTableView (a Qt QTableView created with QTDesigner and provided by
        Ui_ProjectWindow). Setting the model also updates the view."""
        self.geol_coll = GeologicalCollection(parent=self)
        self.proxy_geol_coll = QSortFilterProxyModel(self)
        self.proxy_geol_coll.setSourceModel(self.geol_coll)
        self.GeologyTableView.setModel(self.proxy_geol_coll)

        """Create the xsect_coll XSectionCollection (a Qt QAbstractTableModel with a Pandas dataframe as attribute)
        and connect the model to XSectionsTableView (a Qt QTableView created with QTDesigner and provided by
        Ui_ProjectWindow). Setting the model also updates the view."""
        self.xsect_coll = XSectionCollection(parent=self)
        self.proxy_xsect_coll = QSortFilterProxyModel(self)
        self.proxy_xsect_coll.setSourceModel(self.xsect_coll)
        self.XSectionsTableView.setModel(self.proxy_xsect_coll)

        """Create the dom_coll DomCollection (a Qt QAbstractTableModel with a Pandas dataframe as attribute)
        and connect the model to DOMsTableView (a Qt QTableView created with QTDesigner and provided by
        Ui_ProjectWindow). Setting the model also updates the view."""
        self.dom_coll = DomCollection(parent=self)
        self.proxy_dom_coll = QSortFilterProxyModel(self)
        self.proxy_dom_coll.setSourceModel(self.dom_coll)
        self.DOMsTableView.setModel(self.proxy_dom_coll)

        """Create the image_coll ImageCollection (a Qt QAbstractTableModel with a Pandas dataframe as attribute)
        and connect the model to ImagesTableView (a Qt QTableView created with QTDesigner and provided by
        Ui_ProjectWindow). Setting the model also updates the view."""
        self.image_coll = ImageCollection(parent=self)
        self.proxy_image_coll = QSortFilterProxyModel(self)
        self.proxy_image_coll.setSourceModel(self.image_coll)
        self.ImagesTableView.setModel(self.proxy_image_coll)

        """Create the mesh3d_coll Mesh3DCollection (a Qt QAbstractTableModel with a Pandas dataframe as attribute)
        and connect the model to Meshes3DTableView (a Qt QTableView created with QTDesigner and provided by
        Ui_ProjectWindow). Setting the model also updates the view."""
        self.mesh3d_coll = Mesh3DCollection(parent=self)
        self.proxy_mesh3d_coll = QSortFilterProxyModel(self)
        self.proxy_mesh3d_coll.setSourceModel(self.mesh3d_coll)
        self.Meshes3DTableView.setModel(self.proxy_mesh3d_coll)

        """Create the boundary_coll BoundaryCollection (a Qt QAbstractTableModel with a Pandas dataframe as attribute)
        and connect the model to BoundaryTableView (a Qt QTableView created with QTDesigner and provided by
        Ui_ProjectWindow). Setting the model also updates the view."""
        self.boundary_coll = BoundaryCollection(parent=self)  #_________________________________________________
        self.proxy_boundary_coll = QSortFilterProxyModel(self)
        self.proxy_boundary_coll.setSourceModel(self.boundary_coll)
        self.BoundariesTableView.setModel(self.proxy_boundary_coll)

        """Create the geol_legend_df legend table (a Pandas dataframe), create the corresponding QT
        Legend self.legend (a Qt QTreeWidget that is internally connected to its data source),
        and update the widget."""
        self.geol_legend_df = pd.DataFrame(columns=list(Legend.geol_legend_dict.keys()))
        self.others_legend_df = pd.DataFrame(deepcopy(Legend.others_legend_dict))
        self.legend = Legend()
        self.legend.update_widget(parent=self)

        """Create the prop_legend_df table (a Pandas dataframe), create the corresponding QT
        PropertiesCMaps table widget self.prop_legend (a Qt QTableWidget that is internally connected to its data source),
        and update the widget."""
        self.prop_legend_df = pd.DataFrame(PropertiesCMaps.prop_cmap_dict)
        self.prop_legend = PropertiesCMaps()
        self.prop_legend.update_widget(parent=self)

    def save_project(self):
        """Save project to file and folder"""
        """Date and time, used to save incremental revisions."""
        now = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        """Select and open output file and folder. Saving always performs a complete backup since the output folder
        is named with the present date and time "rev_<now>"."""
        self.out_file_name = save_file_dialog(parent=self, caption="Save project.", filter="PZero (*.p0)")
        if not self.out_file_name:
            return
        out_dir_name = self.out_file_name[:-3] + '_p0/rev_' + now
        self.TextTerminal.appendPlainText(("Saving project as VTK files and csv tables with metada and legend.\n" + "In file/folder: """ + self.out_file_name + " / " + out_dir_name + "\n"))
        """Create the folder if it does not exist already."""
        if not os.path.isdir(self.out_file_name[:-3] + '_p0'):
            os.mkdir(self.out_file_name[:-3] + '_p0')
        os.mkdir(out_dir_name)
        """Save the root file pointing to the folder."""
        fout = open(self.out_file_name, 'w')
        fout.write("PZero project file saved in folder with the same name, including VTK files and CSV tables.\n")
        fout.write("Last saved revision:\n")
        fout.write("rev_" + now)
        fout.close()
        """Save geological legend table to JSON file."""
        # self.geol_legend_df.to_csv(out_dir_name + '/geol_legend_table.csv', encoding='utf-8', index=False)
        self.geol_legend_df.to_json(out_dir_name + '/geol_legend_table.json', orient='index')
        """Save others legend table to JSON file."""
        # self.others_legend_df.to_csv(out_dir_name + '/others_legend_table.csv', encoding='utf-8', index=False)
        self.others_legend_df.to_json(out_dir_name + '/others_legend_table.json', orient='index')
        """Save properties legend table to JSON file."""
        # self.prop_legend_df.to_csv(out_dir_name + '/prop_legend_df.csv', encoding='utf-8', index=False)
        self.prop_legend_df.to_json(out_dir_name + '/prop_legend_df.json', orient='index')
        """Save x_section table to JSON file."""
        out_cols = list(self.xsect_coll.df.columns)
        out_cols.remove('vtk_plane')
        out_cols.remove('vtk_frame')
        # self.xsect_coll.df[out_cols].to_csv(out_dir_name + '/xsection_table.csv', encoding='utf-8', index=False)
        self.xsect_coll.df[out_cols].to_json(out_dir_name + '/xsection_table.json', orient='index')
        """Save geological collection table to JSON file and entities as VTK."""
        out_cols = list(self.geol_coll.df.columns)
        out_cols.remove('vtk_obj')
        # self.geol_coll.df[out_cols].to_csv(out_dir_name + '/geological_table.csv', encoding='utf-8', index=False)
        self.geol_coll.df[out_cols].to_json(out_dir_name + '/geological_table.json', orient='index')
        prgs_bar = progress_dialog(max_value=self.geol_coll.df.shape[0], title_txt="Save geology", label_txt="Saving geological objects...", cancel_txt=None, parent=self)
        for uid in self.geol_coll.df['uid'].to_list():
            pd_writer = vtk.vtkXMLPolyDataWriter()
            pd_writer.SetFileName(out_dir_name + "/" + uid + ".vtp")
            pd_writer.SetInputData(self.geol_coll.get_uid_vtk_obj(uid))
            pd_writer.Write()
            prgs_bar.add_one()
        """Save DOM collection table to JSON file and entities as VTK."""
        out_cols = list(self.dom_coll.df.columns)
        out_cols.remove('vtk_obj')
        # self.dom_coll.df[out_cols].to_csv(out_dir_name + '/dom_table.csv', encoding='utf-8', index=False)
        self.dom_coll.df[out_cols].to_json(out_dir_name + '/dom_table.json', orient='index')
        prgs_bar = progress_dialog(max_value=self.dom_coll.df.shape[0], title_txt="Save DOM", label_txt="Saving DOM objects...", cancel_txt=None, parent=self)
        for uid in self.dom_coll.df['uid'].to_list():
            if self.dom_coll.df.loc[self.dom_coll.df['uid'] == uid, 'dom_type'].values[0] == "DEM":
                sg_writer = vtk.vtkXMLStructuredGridWriter()
                sg_writer.SetFileName(out_dir_name + "/" + uid + ".vts")
                sg_writer.SetInputData(self.dom_coll.get_uid_vtk_obj(uid))
                sg_writer.Write()
                prgs_bar.add_one()
        """Save image collection table to JSON file and entities as VTK."""
        out_cols = list(self.image_coll.df.columns)
        out_cols.remove('vtk_obj')
        # self.image_coll.df[out_cols].to_csv(out_dir_name + '/image_table.csv', encoding='utf-8', index=False)
        self.image_coll.df[out_cols].to_json(out_dir_name + '/image_table.json', orient='index')
        prgs_bar = progress_dialog(max_value=self.image_coll.df.shape[0], title_txt="Save image", label_txt="Saving image objects...", cancel_txt=None, parent=self)
        for uid in self.image_coll.df['uid'].to_list():
            if self.image_coll.df.loc[self.image_coll.df['uid'] == uid, 'image_type'].values[0] in ["MapImage", "XsImage", "TSDomImage"]:
                im_writer = vtk.vtkXMLImageDataWriter()
                im_writer.SetFileName(out_dir_name + "/" + uid + ".vti")
                im_writer.SetInputData(self.image_coll.get_uid_vtk_obj(uid))
                im_writer.Write()
                prgs_bar.add_one()
        """Save mesh3d collection table to JSON file and entities as VTK."""
        out_cols = list(self.mesh3d_coll.df.columns)
        out_cols.remove('vtk_obj')
        # self.mesh3d_coll.df[out_cols].to_csv(out_dir_name + '/mesh3d_table.csv', encoding='utf-8', index=False)
        self.mesh3d_coll.df[out_cols].to_json(out_dir_name + '/mesh3d_table.json', orient='index')
        prgs_bar = progress_dialog(max_value=self.mesh3d_coll.df.shape[0], title_txt="Save 3D mesh", label_txt="Saving 3D mesh objects...", cancel_txt=None, parent=self)
        for uid in self.mesh3d_coll.df['uid'].to_list():
            if self.mesh3d_coll.df.loc[self.mesh3d_coll.df['uid'] == uid, 'mesh3d_type'].values[0] in ["Voxet", "XsVoxet"]:
                im_writer = vtk.vtkXMLImageDataWriter()
                im_writer.SetFileName(out_dir_name + "/" + uid + ".vti")
                im_writer.SetInputData(self.mesh3d_coll.get_uid_vtk_obj(uid))
                im_writer.Write()
            elif self.mesh3d_coll.df.loc[self.mesh3d_coll.df['uid'] == uid, 'mesh3d_type'].values[0] in ["Seismics"]:
                sg_writer = vtk.vtkXMLStructuredGridWriter()
                sg_writer.SetFileName(out_dir_name + "/" + uid + ".vts")
                sg_writer.SetInputData(self.mesh3d_coll.get_uid_vtk_obj(uid))
                sg_writer.Write()
            prgs_bar.add_one()
        """Save boundaries collection table to JSON file and entities as VTK."""  #_________________________________________________
        out_cols = list(self.boundary_coll.df.columns)
        out_cols.remove('vtk_obj')
        # self.boundary_coll.df[out_cols].to_csv(out_dir_name + '/boundary_table.csv', encoding='utf-8', index=False)
        self.boundary_coll.df[out_cols].to_json(out_dir_name + '/boundary_table.json', orient='index')
        prgs_bar = progress_dialog(max_value=self.boundary_coll.df.shape[0], title_txt="Save boundary", label_txt="Saving boundary objects...", cancel_txt=None, parent=self)
        for uid in self.boundary_coll.df['uid'].to_list():
            pd_writer = vtk.vtkXMLPolyDataWriter()
            pd_writer.SetFileName(out_dir_name + "/" + uid + ".vtp")
            pd_writer.SetInputData(self.boundary_coll.get_uid_vtk_obj(uid))
            pd_writer.Write()
            prgs_bar.add_one()

    def new_project(self):
        """Creates a new empty project, after having cleared all variables."""
        """Ask confirmation if the project already contains entities in the geological collection."""
        try:
            if self.geol_coll.get_number_of_entities() > 0:
                confirm_new = QMessageBox.question(self, 'New Project', 'Clear all entities and variables of the present project?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if confirm_new == QMessageBox.No:
                    return
        except:
            pass
        """Create empty containers."""
        self.create_empty()
        """Save a new empty project to file"""
        self.save_project()

    def open_project(self):
        """Opens a project previously saved to disk."""
        """Create empty containers. This also allows for missing tables below."""
        self.create_empty()
        """Select and open project file."""
        in_file_name = open_file_dialog(parent=self, caption="Open PZero project", filter=("PZero (*.p0)"))
        if not in_file_name:
            return
        self.out_file_name = in_file_name
        """Read name of last revision in project file. This opens the last revision. To open a different
        one, edit the project file.
        IN THE FUTURE an option to open a specific revision could be added.________________"""
        fin = open(in_file_name, 'rt')
        rev_name = fin.readlines()[2]
        fin.close()
        in_dir_name = in_file_name[:-3] + '_p0/' + rev_name
        self.TextTerminal.appendPlainText(("Opening project/revision : " + in_file_name + " / " + rev_name + "\n"))
        if not os.path.isdir(in_dir_name):
            print("error: missing folder")
            return
        """In the following it is still possible to open old projects with metadata stored
         as CSV tables, however JSON is used now because it leads to less probelms and errors
         for numeric and list fields. In fact, reading Pandas dataframes from JSON, dtype
         from the class definitions specifies the type of each column."""
        """First read geological and others legend tables."""
        if os.path.isfile((in_dir_name + '/geol_legend_table.csv')) or os.path.isfile((in_dir_name + '/geol_legend_table.json')):
            if os.path.isfile((in_dir_name + '/geol_legend_table.json')):
                new_geol_legend_df = pd.read_json(in_dir_name + '/geol_legend_table.json', orient='index', dtype=Legend.legend_type_dict)
            else:
                new_geol_legend_df = pd.read_csv(in_dir_name + '/geol_legend_table.csv', encoding='utf-8', dtype=Legend.legend_type_dict, keep_default_na=False)
            if not new_geol_legend_df.empty:
                self.geol_legend_df = new_geol_legend_df
            self.geol_legend_df.sort_values(by='geological_time', ascending=True, inplace=True)
        if os.path.isfile((in_dir_name + '/others_legend_table.csv')) or os.path.isfile((in_dir_name + '/others_legend_table.json')):
            if os.path.isfile((in_dir_name + '/others_legend_table.json')):
                new_others_legend_df = pd.read_json(in_dir_name + '/others_legend_table.json', orient='index', dtype=Legend.legend_type_dict)
            else:
                new_others_legend_df = pd.read_csv(in_dir_name + '/others_legend_table.csv', encoding='utf-8', dtype=Legend.legend_type_dict, keep_default_na=False)
            if not new_others_legend_df.empty:
                # self.others_legend_df = new_others_legend_df
                for type in self.others_legend_df['other_type'].values:
                    if type in new_others_legend_df['other_type'].values:
                        self.others_legend_df[self.others_legend_df['other_type'] == type] = new_others_legend_df[new_others_legend_df['other_type'] == type].values
        if os.path.isfile((in_dir_name + '/prop_legend_df.csv')) or os.path.isfile((in_dir_name + '/prop_legend_df.json')):
            if os.path.isfile((in_dir_name + '/prop_legend_df.json')):
                new_prop_legend_df = pd.read_json(in_dir_name + '/prop_legend_df.json', orient='index', dtype=PropertiesCMaps.prop_cmap_type_dict)
                if not new_prop_legend_df.empty:
                    self.prop_legend_df = new_prop_legend_df
            else:
                self.prop_legend.update_widget(parent=self)
        """Update all legends."""
        self.legend.update_widget(parent=self)
        """Read x_section table and build cross-sections. Note beginResetModel() and endResetModel()."""
        if os.path.isfile((in_dir_name + '/xsection_table.csv')) or os.path.isfile((in_dir_name + '/xsection_table.json')):
            self.xsect_coll.beginResetModel()
            if os.path.isfile((in_dir_name + '/xsection_table.json')):
                new_xsect_coll_df = pd.read_json(in_dir_name + '/xsection_table.json', orient='index', dtype=XSectionCollection.section_type_dict)
                if not new_xsect_coll_df.empty:
                    self.xsect_coll.df = new_xsect_coll_df
            else:
                self.xsect_coll.df = pd.read_csv(in_dir_name + '/xsection_table.csv', encoding='utf-8', dtype=XSectionCollection.section_type_dict, keep_default_na=False)
            for uid in self.xsect_coll.df["uid"].tolist():
                self.xsect_coll.set_geometry(uid=uid)
            self.xsect_coll.endResetModel()
        """Read DOM table and files. Note beginResetModel() and endResetModel()."""
        if os.path.isfile((in_dir_name + '/dom_table.csv')) or os.path.isfile((in_dir_name + '/dom_table.json')):
            self.dom_coll.beginResetModel()
            if os.path.isfile((in_dir_name + '/dom_table.json')):
                new_dom_coll_df = pd.read_json(in_dir_name + '/dom_table.json', orient='index', dtype=DomCollection.dom_entity_type_dict)
                if not new_dom_coll_df.empty:
                    self.dom_coll.df = new_dom_coll_df
            else:
                self.dom_coll.df = pd.read_csv(in_dir_name + '/dom_table.csv', encoding='utf-8', dtype=DomCollection.dom_entity_type_dict, keep_default_na=False)
            prgs_bar = progress_dialog(max_value=self.dom_coll.df.shape[0], title_txt="Open DOM", label_txt="Opening DOM objects...", cancel_txt=None, parent=self)
            for uid in self.dom_coll.df['uid'].to_list():
                if self.dom_coll.get_uid_dom_type(uid) == "DEM":
                    if not os.path.isfile((in_dir_name + "/" + uid + ".vts")):
                        print("error: missing VTK file")
                        return
                    vtk_object = DEM()
                    sg_reader = vtk.vtkXMLStructuredGridReader()
                    sg_reader.SetFileName(in_dir_name + "/" + uid + ".vts")
                    sg_reader.Update()
                    vtk_object.ShallowCopy(sg_reader.GetOutput())
                    vtk_object.Modified()
                elif self.dom_coll.df.loc[self.dom_coll.df['uid'] == uid, 'dom_type'].values[0] == 'TSDom':
                    """Add code to read TSDOM here__________"""
                    vtk_object = TSDom()
                elif self.dom_coll.df.loc[self.dom_coll.df['uid'] == uid, 'dom_type'].values[0] == 'PCDom':
                    """Add code to read TSDOM here__________"""
                    vtk_object = PCDom()
                self.dom_coll.set_uid_vtk_obj(uid=uid, vtk_obj=vtk_object)
                prgs_bar.add_one()
            self.dom_coll.endResetModel()
        """Read image collection and files"""
        if os.path.isfile((in_dir_name + '/image_table.csv')) or os.path.isfile((in_dir_name + '/image_table.json')):
            self.image_coll.beginResetModel()
            if os.path.isfile((in_dir_name + '/image_table.json')):
                new_image_coll_df = pd.read_json(in_dir_name + '/image_table.json', orient='index', dtype=ImageCollection.image_entity_type_dict)
                if not new_image_coll_df.empty:
                    self.image_coll.df = new_image_coll_df
            else:
                self.image_coll.df = pd.read_csv(in_dir_name + '/image_table.csv', encoding='utf-8', dtype=ImageCollection.image_entity_type_dict, keep_default_na=False)
            prgs_bar = progress_dialog(max_value=self.image_coll.df.shape[0], title_txt="Open image", label_txt="Opening image objects...", cancel_txt=None, parent=self)
            for uid in self.image_coll.df['uid'].to_list():
                if self.image_coll.df.loc[self.image_coll.df['uid'] == uid, 'image_type'].values[0] in ["MapImage", "XsImage", "TSDomImage"]:
                    if not os.path.isfile((in_dir_name + "/" + uid + ".vti")):
                        print("error: missing image file")
                        return
                    vtk_object = MapImage()
                    im_reader = vtk.vtkXMLImageDataReader()
                    im_reader.SetFileName(in_dir_name + "/" + uid + ".vti")
                    im_reader.Update()
                    vtk_object.ShallowCopy(im_reader.GetOutput())
                    vtk_object.Modified()
                self.image_coll.set_uid_vtk_obj(uid=uid, vtk_obj=vtk_object)
                prgs_bar.add_one()
            self.image_coll.endResetModel()
        """Read mesh3d collection and files"""
        if os.path.isfile((in_dir_name + '/mesh3d_table.csv')) or os.path.isfile((in_dir_name + '/mesh3d_table.json')):
            self.mesh3d_coll.beginResetModel()
            if os.path.isfile((in_dir_name + '/mesh3d_table.json')):
                new_mesh3d_coll_df = pd.read_json(in_dir_name + '/mesh3d_table.json', orient='index', dtype=Mesh3DCollection.mesh3d_entity_type_dict)
                if not new_mesh3d_coll_df.empty:
                    self.mesh3d_coll.df = new_mesh3d_coll_df
            else:
                self.mesh3d_coll.df = pd.read_csv(in_dir_name + '/mesh3d_table.csv', encoding='utf-8', dtype=Mesh3DCollection.mesh3d_entity_type_dict, keep_default_na=False)
            prgs_bar = progress_dialog(max_value=self.mesh3d_coll.df.shape[0], title_txt="Open 3D mesh", label_txt="Opening 3D mesh objects...", cancel_txt=None, parent=self)
            for uid in self.mesh3d_coll.df['uid'].to_list():
                if self.mesh3d_coll.df.loc[self.mesh3d_coll.df['uid'] == uid, 'mesh3d_type'].values[0] in ["Voxet"]:
                    if not os.path.isfile((in_dir_name + "/" + uid + ".vti")):
                        print("error: missing .mesh3d file")
                        return
                    vtk_object = Voxet()
                    im_reader = vtk.vtkXMLImageDataReader()
                    im_reader.SetFileName(in_dir_name + "/" + uid + ".vti")
                    im_reader.Update()
                    vtk_object.ShallowCopy(im_reader.GetOutput())
                    vtk_object.Modified()
                elif self.mesh3d_coll.df.loc[self.mesh3d_coll.df['uid'] == uid, 'mesh3d_type'].values[0] in ["XsVoxet"]:
                    if not os.path.isfile((in_dir_name + "/" + uid + ".vti")):
                        print("error: missing .mesh3d file")
                        return
                    vtk_object = XsVoxet(x_section_uid=self.mesh3d_coll.df.loc[self.mesh3d_coll.df['uid'] == uid, 'x_section'].values[0], parent=self)
                    im_reader = vtk.vtkXMLImageDataReader()
                    im_reader.SetFileName(in_dir_name + "/" + uid + ".vti")
                    im_reader.Update()
                    vtk_object.ShallowCopy(im_reader.GetOutput())
                    vtk_object.Modified()
                elif self.mesh3d_coll.df.loc[self.mesh3d_coll.df['uid'] == uid, 'mesh3d_type'].values[0] in ["Seismics"]:
                    if not os.path.isfile((in_dir_name + "/" + uid + ".vts")):
                        print("error: missing VTK file")
                        return
                    vtk_object = Seismics()
                    sg_reader = vtk.vtkXMLStructuredGridReader()
                    sg_reader.SetFileName(in_dir_name + "/" + uid + ".vts")
                    sg_reader.Update()
                    vtk_object.ShallowCopy(sg_reader.GetOutput())
                    vtk_object.Modified()
                    prgs_bar.add_one()
                self.mesh3d_coll.set_uid_vtk_obj(uid=uid, vtk_obj=vtk_object)
            self.mesh3d_coll.endResetModel()
        """Read boundaries collection and files"""  #_________________________________________________
        if os.path.isfile((in_dir_name + '/boundary_table.csv')) or os.path.isfile((in_dir_name + '/boundary_table.json')):
            self.boundary_coll.beginResetModel()
            if os.path.isfile((in_dir_name + '/boundary_table.json')):
                new_boundary_coll_df = pd.read_json(in_dir_name + '/boundary_table.json', orient='index', dtype=BoundaryCollection.boundary_entity_type_dict)
                if not new_boundary_coll_df.empty:
                    self.boundary_coll.df = new_boundary_coll_df
            else:
                self.boundary_coll.df = pd.read_csv(in_dir_name + '/boundary_table.csv', encoding='utf-8', dtype=BoundaryCollection.boundary_entity_type_dict, keep_default_na=False)
            prgs_bar = progress_dialog(max_value=self.boundary_coll.df.shape[0], title_txt="Open boundary", label_txt="Opening boundary objects...", cancel_txt=None, parent=self)
            for uid in self.boundary_coll.df['uid'].to_list():
                if not os.path.isfile((in_dir_name + "/" + uid + ".vtp")):
                    print("error: missing VTK file")
                    return
                if self.boundary_coll.get_uid_topological_type(uid) == 'PolyLine':
                    vtk_object = PolyLine()
                elif self.boundary_coll.get_uid_topological_type(uid) == 'TriSurf':
                    vtk_object = TriSurf()
                pd_reader = vtk.vtkXMLPolyDataReader()
                pd_reader.SetFileName(in_dir_name + "/" + uid + ".vtp")
                pd_reader.Update()
                vtk_object.ShallowCopy(pd_reader.GetOutput())
                vtk_object.Modified()
                self.boundary_coll.set_uid_vtk_obj(uid=uid, vtk_obj=vtk_object)
                prgs_bar.add_one()
            self.boundary_coll.endResetModel()
        """Read geological table and files. Note beginResetModel() and endResetModel()."""
        if os.path.isfile((in_dir_name + '/geological_table.csv')) or os.path.isfile((in_dir_name + '/geological_table.json')):
            self.geol_coll.beginResetModel()
            if os.path.isfile((in_dir_name + '/geological_table.json')):
                new_geol_coll_df = pd.read_json(in_dir_name + '/geological_table.json', orient='index', dtype=GeologicalCollection.geological_entity_type_dict)
                if not new_geol_coll_df.empty:
                    self.geol_coll.df = new_geol_coll_df
            else:
                self.geol_coll.df = pd.read_csv(in_dir_name + '/geological_table.csv', encoding='utf-8', dtype=GeologicalCollection.geological_entity_type_dict, keep_default_na=False)
            prgs_bar = progress_dialog(max_value=self.geol_coll.df.shape[0], title_txt="Open geology", label_txt="Opening geological objects...", cancel_txt=None, parent=self)
            for uid in self.geol_coll.df['uid'].to_list():
                if not os.path.isfile((in_dir_name + "/" + uid + ".vtp")):
                    print("error: missing VTK file")
                    return
                if self.geol_coll.get_uid_topological_type(uid) == 'VertexSet':
                    vtk_object = VertexSet()
                elif self.geol_coll.get_uid_topological_type(uid) == 'PolyLine':
                    vtk_object = PolyLine()
                elif self.geol_coll.get_uid_topological_type(uid) == 'TriSurf':
                    vtk_object = TriSurf()
                elif self.geol_coll.get_uid_topological_type(uid) == 'XsVertexSet':
                    vtk_object = XsVertexSet(self.geol_coll.get_uid_x_section(uid), parent=self)
                elif self.geol_coll.get_uid_topological_type(uid) == 'XsPolyLine':
                    vtk_object = XsPolyLine(self.geol_coll.get_uid_x_section(uid), parent=self)
                pd_reader = vtk.vtkXMLPolyDataReader()
                pd_reader.SetFileName(in_dir_name + "/" + uid + ".vtp")
                pd_reader.Update()
                vtk_object.ShallowCopy(pd_reader.GetOutput())
                vtk_object.Modified()
                self.geol_coll.set_uid_vtk_obj(uid=uid, vtk_obj=vtk_object)
                prgs_bar.add_one()
            self.geol_coll.endResetModel()
        """Update legend."""
        self.prop_legend.update_widget(parent=self)

    """Methods used to import entities from other file formats."""

    def import_gocad(self):
        """Import Gocad ASCII file and update geological collection."""
        self.TextTerminal.appendPlainText("Importing Gocad ASCII format")
        self.TextTerminal.appendPlainText("Properties are discarded if they are not 1D, 2D, 3D, 4D, 6D or 9D (due to VTK limitations)")
        """Select and open input file"""
        in_file_name = open_file_dialog(parent=self, caption='Import entities from Gocad ASCII file', filter="Gocad ASCII (*.*)")
        if in_file_name:
            self.TextTerminal.appendPlainText('in_file_name: ' + in_file_name)
            gocad2vtk(self=self, in_file_name=in_file_name, uid_from_name=False)
            self.prop_legend.update_widget(parent=self)

    def import_gocad_section(self):
        """Import Gocad ASCII file and update geological collection."""
        self.TextTerminal.appendPlainText("Importing Gocad ASCII format")
        self.TextTerminal.appendPlainText("Properties are discarded if they are not 1D, 2D, 3D, 4D, 6D or 9D (due to VTK limitations)")
        """Select and open input file"""
        in_file_name = open_file_dialog(parent=self, caption='Import entities from Gocad ASCII file', filter="Gocad ASCII (*.*)")
        if in_file_name:
            self.TextTerminal.appendPlainText('in_file_name: ' + in_file_name)
            """Select the Xsection"""
            if self.xsect_coll.get_uids():
                x_section_name = input_combo_dialog(parent=None, title="Xsection", label="Choose Xsection", choice_list=self.xsect_coll.get_names())
            else:
                message_dialog(title="Xsection", message="No Xsection in project")
                return
            if x_section_name:
                x_section_uid = self.xsect_coll.df.loc[self.xsect_coll.df['name'] == x_section_name, 'uid'].values[0]
                gocad2vtk_section(self=self, in_file_name=in_file_name, uid_from_name=False, x_section=x_section_uid)
                self.prop_legend.update_widget(parent=self)

    def import_gocad_boundary(self):  #_________________________________________________
        """Import Gocad ASCII file and update boundary collection."""
        self.TextTerminal.appendPlainText("Importing Gocad ASCII format as boundary")
        self.TextTerminal.appendPlainText("Properties are discarded - only mesh imported.")
        """Select and open input file"""
        in_file_name = open_file_dialog(parent=self, caption='Import entities from Gocad ASCII file', filter="Gocad ASCII (*.*)")
        if in_file_name:
            self.TextTerminal.appendPlainText('in_file_name: ' + in_file_name)
            gocad2vtk_boundary(self=self, in_file_name=in_file_name, uid_from_name=False)

    def import_SHP(self):  # _______________ MAKE IMPORT SHP BOUNDARY
        """Import SHP file and update geological collection."""
        self.TextTerminal.appendPlainText("Importing SHP file")
        """Select and open input file"""
        in_file_name = open_file_dialog(parent=self, caption='Import SHP file', filter="shp (*.shp)")
        if in_file_name:
            self.TextTerminal.appendPlainText('in_file_name: ' + in_file_name)
            shp2vtk(self=self, in_file_name=in_file_name)

    def import_DEM(self):
        """Import DEM file and update DEM collection."""
        self.TextTerminal.appendPlainText("Importing DEM in supported format (geotiff)")
        """Select and open input file"""
        in_file_name = open_file_dialog(parent=self, caption='Import DEM from file', filter="Geotiff (*.tif)")
        if in_file_name:
            self.TextTerminal.appendPlainText('in_file_name: ' + in_file_name)
            dem2vtk(self=self, in_file_name=in_file_name)

    def import_image(self):
        """Import DEM file and update DEM collection."""
        """TO BE REVIEWED______________"""
        self.TextTerminal.appendPlainText("Importing image from supported format (GDAL)")
        """Select and open input file"""
        in_file_name = open_file_dialog(parent=self, caption='Import image from file', filter="Image (*.tif *.jpg *.png *.bmp)")
        if in_file_name:
            self.TextTerminal.appendPlainText('in_file_name: ' + in_file_name)
            geo_image2vtk(self=self, in_file_name=in_file_name)

    def import_SEGY(self):
        """Import SEGY file and update Mesh3D collection."""
        """TO BE REVIEWED______________"""
        self.TextTerminal.appendPlainText("Importing SEGY seismics file.")
        """Select and open input file"""
        in_file_name = open_file_dialog(parent=self, caption='Import SEGY from file', filter="SEGY (*.sgy *.segy)")
        if in_file_name:
            self.TextTerminal.appendPlainText('in_file_name: ' + in_file_name)
            segy2vtk(self=self, in_file_name=in_file_name)

    """Methods used to export entities to other file formats."""

    def export_cad(self):
        """Base method to chose a CAD format for exporting geological entities."""
        cad_format = input_combo_dialog(parent=self, title="CAD format", label="Choose CAD format", choice_list=["STL with 1m dilation", "DXF", "GOCAD", "OBJ", "PLY", "STL"])
        print(cad_format)
        out_dir_name = save_file_dialog(parent=self, caption="Export geological entities as CAD meshes.")
        if not out_dir_name:
            return
        self.TextTerminal.appendPlainText(("Saving CAD surfaces in folder: " + out_dir_name))
        """Create the folder if it does not exist already."""
        if not os.path.isdir(out_dir_name):
            os.mkdir(out_dir_name)
        if cad_format == "DXF":
            print("is DXF")
            vtk2dxf(self=self, out_dir_name=out_dir_name)
        elif cad_format == "STL":
            vtk2stl(self=self, out_dir_name=out_dir_name)
        elif cad_format == "OBJ":
            vtk2obj(self=self, out_dir_name=out_dir_name)
        elif cad_format == "PLY":
            vtk2ply(self=self, out_dir_name=out_dir_name)
        elif cad_format == "GOCAD":
            pass
        elif cad_format == "STL with 1m dilation":
            vtk2stl_dilation(self=self, out_dir_name=out_dir_name, tol=1)
        else:
            return
        """Save geological legend table to CSV and JSON files."""
        self.geol_legend_df.to_csv(out_dir_name + '/geol_legend_table.csv', encoding='utf-8', index=False)
        self.geol_legend_df.to_json(out_dir_name + '/geol_legend_table.json', orient='index')
        """Save others legend table to CSV and JSON files."""
        self.others_legend_df.to_csv(out_dir_name + '/others_legend_table.csv', encoding='utf-8', index=False)
        self.others_legend_df.to_json(out_dir_name + '/others_legend_table.json', orient='index')
        """Save x_section table to CSV and JSON files."""
        out_cols = list(self.xsect_coll.df.columns)
        out_cols.remove('vtk_plane')
        out_cols.remove('vtk_frame')
        self.xsect_coll.df[out_cols].to_csv(out_dir_name + '/xsection_table.csv', encoding='utf-8', index=False)
        self.xsect_coll.df[out_cols].to_json(out_dir_name + '/xsection_table.json', orient='index')
        """Save geological collection table to CSV and JSON files."""
        out_cols = list(self.geol_coll.df.columns)
        out_cols.remove('vtk_obj')
        self.geol_coll.df[out_cols].to_csv(out_dir_name + '/geological_table.csv', encoding='utf-8', index=False)
        self.geol_coll.df[out_cols].to_json(out_dir_name + '/geological_table.json', orient='index')
        """Save DOM collection table to CSV and JSON files."""
        out_cols = list(self.dom_coll.df.columns)
        out_cols.remove('vtk_obj')
        self.dom_coll.df[out_cols].to_csv(out_dir_name + '/dom_table.csv', encoding='utf-8', index=False)
        self.dom_coll.df[out_cols].to_json(out_dir_name + '/dom_table.json', orient='index')
        """Save image collection table to CSV and JSON files."""
        out_cols = list(self.image_coll.df.columns)
        out_cols.remove('vtk_obj')
        self.image_coll.df[out_cols].to_csv(out_dir_name + '/image_table.csv', encoding='utf-8', index=False)
        self.image_coll.df[out_cols].to_json(out_dir_name + '/image_table.json', orient='index')
        """Save mesh3d collection table to CSV and JSON files."""
        out_cols = list(self.mesh3d_coll.df.columns)
        out_cols.remove('vtk_obj')
        self.mesh3d_coll.df[out_cols].to_csv(out_dir_name + '/mesh3d_table.csv', encoding='utf-8', index=False)
        self.mesh3d_coll.df[out_cols].to_json(out_dir_name + '/mesh3d_table.json', orient='index')
        """Save boundary collection table to CSV and JSON files."""
        out_cols = list(self.boundary_coll.df.columns)
        out_cols.remove('vtk_obj')
        self.boundary_coll.df[out_cols].to_csv(out_dir_name + '/boundary_table.csv', encoding='utf-8', index=False)
        self.boundary_coll.df[out_cols].to_json(out_dir_name + '/boundary_table.json', orient='index')
        print("All files saved.")

    def export_gocad(self):
        """Export all TriSurf's as DXF triangulated surfaces."""
        """TO BE REVIEWED______________"""
        out_dir_name = save_file_dialog(parent=self, caption="Export entities as DXF triangulated surfaces.")
        if not out_dir_name:
            return
        self.TextTerminal.appendPlainText(("Saving DXF surfaces in folder: " + out_dir_name))
        """Create the folder if it does not exist already."""
        if not os.path.isdir(out_dir_name):
            os.mkdir(out_dir_name)
        for uid in self.geol_coll.df['uid']:
            vtk2dxf(self=self, uid=uid, out_dir_name=out_dir_name)

        """Select and open input file"""
        self.out_file_name = save_file_dialog(parent=self, caption="Save project.", filter=("PZero (*.p0)"))
        if not self.out_file_name:
            return
        out_dir_name = self.out_file_name[:-3] + '_p0'
        self.TextTerminal.appendPlainText(("Saving project as Gocad Ascii format and csv tables with attributes and legend.\n" + "In file, folder: """ + self.out_file_name + " ,  " + out_dir_name + "\n" + "Properties are discarded if they are not 1D, 2D, 3D, 4D, 6D or 9D (due to VTK limitations)"))
        if not os.path.isdir(out_dir_name):
            """1- create the folder if it does not exist already."""
            os.mkdir(out_dir_name)
        """2- save the root file pointing to the folder."""
        fout = open(self.out_file_name, 'w')
        fout.write("PZero project file saved in folder with the same name, including Gocad Ascii entities and CSV tables")
        fout.close()
        """3- save x_section table to CSV file."""
        self.xsect_coll.df.to_csv(out_dir_name + '/xsection_table.csv', encoding='utf-8', index=False)
        """4- save geological collection table to CSV file."""
        self.geol_coll.df.to_csv(out_dir_name + '/geological_table.csv', encoding='utf-8', index=False)
        """5- save legend table to CSV file."""
        self.geol_legend_df.to_csv(out_dir_name + '/legend_table.csv', encoding='utf-8', index=False)
        """6- save Gocad Ascii file."""
        vtk2gocad(self=self, out_file_name=(out_dir_name + '/gocad_ascii.gp'))

        """Keep a backup copy of all files with date/time suffix. This is a bit strange
        since the backup is created as a copy of the PRESENT state of the project, but it
        is easier and safer. Images and other static objects are just saved in the project
        when imported and stored as backup files if removed from the project."""
        now = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        copy2((out_dir_name + '/xsection_table.csv'), (out_dir_name + '/section_table' + now + '.csv'))
        copy2((out_dir_name + '/geological_table.csv'), (out_dir_name + '/geological_table' + now + '.csv'))
        copy2((out_dir_name + '/legend_table.csv'), (out_dir_name + '/legend_table' + now + '.csv'))
        copy2((out_dir_name + '/gocad_ascii.gp'), (out_dir_name + '/gocad_ascii' + now + '.gp'))
