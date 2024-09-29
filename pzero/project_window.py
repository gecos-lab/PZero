"""project_window.py
PZero© Andrea Bistacchi"""

import os

from copy import deepcopy

from datetime import datetime

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QMainWindow, QMessageBox

from pandas import DataFrame as pd_DataFrame
from pandas import read_csv as pd_read_csv
from pandas import read_json as pd_read_json

from vtk import (
    vtkPolyData,
    vtkAppendPolyData,
    vtkOctreePointLocator,
    vtkXMLPolyDataWriter,
    vtkXMLStructuredGridWriter,
    vtkXMLImageDataWriter,
    vtkXMLStructuredGridReader,
    vtkXMLPolyDataReader,
    vtkXMLImageDataReader,
)

from pzero.collections.background_collection import BackgroundCollection
from pzero.collections.boundary_collection import BoundaryCollection
from pzero.collections.dom_collection import DomCollection
from pzero.collections.fluid_collection import FluidsCollection
from pzero.collections.geological_collection import GeologicalCollection
from pzero.collections.image_collection import ImageCollection
from pzero.collections.mesh3d_collection import Mesh3DCollection
from pzero.collections.well_collection import WellCollection
from pzero.collections.xsection_collection import XSectionCollection
from pzero.helpers.helper_dialogs import (
    options_dialog,
    save_file_dialog,
    open_file_dialog,
    open_files_dialog,
    input_combo_dialog,
    message_dialog,
    multiple_input_dialog,
    input_one_value_dialog,
    progress_dialog,
    import_dialog,
    PreviewWidget,
    input_text_dialog,
)
from pzero.imports.cesium2vtk import vtk2cesium
from pzero.imports.dem2vtk import dem2vtk
from pzero.imports.dxf2vtk import vtk2dxf
from pzero.imports.gltf2vtk import vtk2gltf
from pzero.imports.gocad2vtk import gocad2vtk, gocad2vtk_section, gocad2vtk_boundary
from pzero.imports.image2vtk import geo_image2vtk, xs_image2vtk
from pzero.imports.lxml2vtk import vtk2lxml
from pzero.imports.obj2vtk import vtk2obj
from pzero.imports.pc2vtk import pc2vtk
from pzero.imports.ply2vtk import vtk2ply
from pzero.imports.pyvista2vtk import pyvista2vtk
from pzero.imports.segy2vtk import segy2vtk
from pzero.imports.shp2vtk import shp2vtk
from pzero.imports.stl2vtk import vtk2stl, vtk2stl_dilation
from pzero.imports.vedo2vtk import vedo2vtk
from pzero.imports.well2vtk import well2vtk
from pzero.ui.project_window_ui import Ui_ProjectWindow
from .entities_factory import (
    VertexSet,
    PolyLine,
    TriSurf,
    XsVertexSet,
    XsPolyLine,
    DEM,
    MapImage,
    Voxet,
    Seismics,
    XsVoxet,
    PCDom,
    TSDom,
    Well,
    Attitude,
    XsImage,
)
from .legend_manager import Legend
from .orientation_analysis import set_normals
from .point_clouds import decimate_pc
from .properties_manager import PropertiesCMaps
from .three_d_surfaces import (
    interpolation_delaunay_2d,
    poisson_interpolation,
    implicit_model_loop_structural,
    surface_smoothing,
    linear_extrusion,
    decimation_pro_resampling,
    decimation_quadric_resampling,
    subdivision_resampling,
    intersection_xs,
    project_2_dem,
    project_2_xs,
    split_surf,
    retopo,
)
from .windows_factory import NewViewMap
from .windows_factory import NewViewXsection
from .windows_factory import View3D
from .windows_factory import ViewStereoplot


class ProjectWindow(QMainWindow, Ui_ProjectWindow):
    """Create project window and import UI created with Qt Designer by subclassing both"""

    # Signals defined here are meant to be broadcast TO ALL views. This is why we use signals
    # instead of functions that will act within a single view only. They all pass a list of uid's.
    project_close_signal = (
        pyqtSignal()
    )  # this is used to delete open windows when the current project is closed (and a new one is opened)

    geology_added_signal = pyqtSignal(list)
    geology_removed_signal = pyqtSignal(list)
    geology_geom_modified_signal = pyqtSignal(list)  # this includes topology modified
    geology_data_keys_modified_signal = pyqtSignal(list)
    geology_data_val_modified_signal = pyqtSignal(list)
    geology_metadata_modified_signal = pyqtSignal(list)
    geology_legend_color_modified_signal = pyqtSignal(list)
    geology_legend_thick_modified_signal = pyqtSignal(list)
    geology_legend_point_size_modified_signal = pyqtSignal(list)
    geology_legend_opacity_modified_signal = pyqtSignal(list)

    xsect_added_signal = pyqtSignal(list)
    xsect_removed_signal = pyqtSignal(list)
    xsect_geom_modified_signal = pyqtSignal(list)  # this includes topology modified
    xsect_metadata_modified_signal = pyqtSignal(list)
    xsect_legend_color_modified_signal = pyqtSignal(list)
    xsect_legend_thick_modified_signal = pyqtSignal(list)
    xsect_legend_opacity_modified_signal = pyqtSignal(list)

    boundary_added_signal = pyqtSignal(list)
    boundary_removed_signal = pyqtSignal(list)
    boundary_geom_modified_signal = pyqtSignal(list)  # this includes topology modified
    boundary_metadata_modified_signal = pyqtSignal(list)
    boundary_legend_color_modified_signal = pyqtSignal(list)
    boundary_legend_thick_modified_signal = pyqtSignal(list)
    boundary_legend_opacity_modified_signal = pyqtSignal(list)

    mesh3d_added_signal = pyqtSignal(list)
    mesh3d_removed_signal = pyqtSignal(list)
    mesh3d_data_keys_modified_signal = pyqtSignal(list)
    mesh3d_data_val_modified_signal = pyqtSignal(list)
    mesh3d_metadata_modified_signal = pyqtSignal(list)
    mesh3d_legend_color_modified_signal = pyqtSignal(list)
    mesh3d_legend_thick_modified_signal = pyqtSignal(list)
    mesh3d_legend_opacity_modified_signal = pyqtSignal(list)

    dom_added_signal = pyqtSignal(list)
    dom_removed_signal = pyqtSignal(list)
    dom_data_keys_modified_signal = pyqtSignal(list)
    dom_data_val_modified_signal = pyqtSignal(list)
    dom_metadata_modified_signal = pyqtSignal(list)
    dom_legend_color_modified_signal = pyqtSignal(list)
    dom_legend_thick_modified_signal = pyqtSignal(list)
    dom_legend_point_size_modified_signal = pyqtSignal(list)
    dom_legend_opacity_modified_signal = pyqtSignal(list)

    image_added_signal = pyqtSignal(list)
    image_removed_signal = pyqtSignal(list)
    image_metadata_modified_signal = pyqtSignal(list)
    image_legend_opacity_modified_signal = pyqtSignal(list)

    well_added_signal = pyqtSignal(list)
    well_removed_signal = pyqtSignal(list)
    well_data_keys_modified_signal = pyqtSignal(list)
    well_data_val_modified_signal = pyqtSignal(list)
    well_metadata_modified_signal = pyqtSignal(list)
    well_legend_color_modified_signal = pyqtSignal(list)
    well_legend_thick_modified_signal = pyqtSignal(list)
    well_legend_opacity_modified_signal = pyqtSignal(list)

    fluid_added_signal = pyqtSignal(list)
    fluid_removed_signal = pyqtSignal(list)
    fluid_geom_modified_signal = pyqtSignal(list)  # this includes topology modified
    fluid_data_keys_modified_signal = pyqtSignal(list)
    fluid_data_val_modified_signal = pyqtSignal(list)
    fluid_metadata_modified_signal = pyqtSignal(list)
    fluid_legend_color_modified_signal = pyqtSignal(list)
    fluid_legend_thick_modified_signal = pyqtSignal(list)
    fluid_legend_point_size_modified_signal = pyqtSignal(list)
    fluid_legend_opacity_modified_signal = pyqtSignal(list)

    background_added_signal = pyqtSignal(list)
    background_removed_signal = pyqtSignal(list)
    background_geom_modified_signal = pyqtSignal(
        list
    )  # this includes topology modified
    background_data_keys_modified_signal = pyqtSignal(list)
    background_data_val_modified_signal = pyqtSignal(list)
    background_metadata_modified_signal = pyqtSignal(list)
    background_legend_color_modified_signal = pyqtSignal(list)
    background_legend_thick_modified_signal = pyqtSignal(list)
    background_legend_point_size_modified_signal = pyqtSignal(list)
    background_legend_opacity_modified_signal = pyqtSignal(list)

    prop_legend_cmap_modified_signal = pyqtSignal(str)

    line_digitized_signal = pyqtSignal(dict)

    """Add other signals above this line ----------------------------------------"""

    def __init__(self, *args, **kwargs):
        super(ProjectWindow, self).__init__(*args, **kwargs)
        """Import GUI from project_window_ui.py"""
        self.setupUi(self)

        """Connect actionQuit.triggered SIGNAL to self.close SLOT"""
        self.actionQuit.triggered.connect(self.close)

        """Welcome message"""
        self.TextTerminal.appendPlainText(
            "Welcome to PZero!\n3D modelling application by Andrea Bistacchi, started June 3rd 2020."
        )

        """Initialize empty project."""
        self.create_empty()

        # startup_option = options_dialog(title='PZero', message='Do you want to create a new project or open an existing one?', yes_role='Create New Project', no_role='Open Existing Project', reject_role='Close PZero')
        # if startup_option == 0:
        #     self.TextTerminal.appendPlainText("Creating a new empty project.")
        #     self.new_project()
        # elif startup_option == 1:
        #     self.TextTerminal.appendPlainText("Opening an existing project.")
        #     self.open_project()
        # else:
        #     self.close(True)  # this actually crashes the application, but at the moment I do not have another working solution to close it

        """File>Project actions -> slots"""
        self.actionProjectNew.triggered.connect(self.new_project)
        self.actionProjectOpen.triggered.connect(self.open_project)
        self.actionProjectSave.triggered.connect(self.save_project)

        """File>Import actions -> slots"""
        self.actionImportGocad.triggered.connect(self.import_gocad)
        self.actionImportGocadXsection.triggered.connect(self.import_gocad_sections)
        self.actionImportGocadBoundary.triggered.connect(self.import_gocad_boundary)
        self.actionImportPyvista.triggered.connect(lambda: pyvista2vtk(self=self))
        self.actionImportPC.triggered.connect(self.import_PC)
        self.actionImportVedo.triggered.connect(lambda: vedo2vtk(self=self))
        self.actionImportSHP.triggered.connect(self.import_SHP)
        self.actionImportDEM.triggered.connect(self.import_DEM)
        self.actionImportOrthoImage.triggered.connect(self.import_mapimage)
        self.actionImportXsectionImage.triggered.connect(self.import_xsimage)
        self.actionImportWellData.triggered.connect(self.import_welldata)
        self.actionImportSEGY.triggered.connect(self.import_SEGY)

        """File>Export actions -> slots"""
        self.actionExportCAD.triggered.connect(self.export_cad)
        self.actionExportVTK.triggered.connect(self.export_vtk)
        self.actionExportCSV.triggered.connect(self.export_csv)

        """Edit actions -> slots"""
        self.actionEditEntityRemove.triggered.connect(self.entity_remove)
        self.actionConnectedParts.triggered.connect(self.connected_parts)
        self.actionMergeEntities.triggered.connect(self.entities_merge)
        self.actionSplitMultipart.triggered.connect(self.split_multipart)
        self.actionDecimatePointCloud.triggered.connect(self.decimate_pc_dialog)
        """______________________________________ ADD TOOL TO PRINT VTK INFO self.TextTerminal.appendPlainText( -- vtk object as text -- )"""
        self.actionEditTextureAdd.triggered.connect(self.texture_add)
        self.actionEditTextureRemove.triggered.connect(self.texture_remove)
        self.actionAddProperty.triggered.connect(self.property_add)
        self.actionRemoveProperty.triggered.connect(self.property_remove)
        self.actionCalculateNormal.triggered.connect(self.normals_calculate)
        self.actionCalculateLineation.triggered.connect(self.lineations_calculate)

        self.actionBuildOctree.triggered.connect(self.build_octree)

        """Interpolation actions -> slots"""
        self.actionDelaunay2DInterpolation.triggered.connect(
            lambda: interpolation_delaunay_2d(self)
        )
        self.actionPoissonInterpolation.triggered.connect(
            lambda: poisson_interpolation(self)
        )
        self.actionLoopStructuralImplicitModelling.triggered.connect(
            lambda: implicit_model_loop_structural(self)
        )
        self.actionSurfaceSmoothing.triggered.connect(self.smooth_dialog)
        self.actionSubdivisionResampling.triggered.connect(self.subd_res_dialog)
        self.actionDecimationPro.triggered.connect(
            lambda: decimation_pro_resampling(self)
        )
        self.actionDecimationQuadric.triggered.connect(
            lambda: decimation_quadric_resampling(self)
        )
        self.actionExtrusion.triggered.connect(lambda: linear_extrusion(self))
        self.actionProject2DEM.triggered.connect(lambda: project_2_dem(self))
        self.actionIntersectionXSection.triggered.connect(lambda: intersection_xs(self))
        self.actionProject2XSection.triggered.connect(lambda: project_2_xs(self))
        self.actionSplitSurf.triggered.connect(lambda: split_surf(self))
        self.actionRetopologize.triggered.connect(self.retopologize_surface)

        """View actions -> slots"""
        self.actionView3D.triggered.connect(lambda: View3D(parent=self))
        self.actionViewMap.triggered.connect(lambda: NewViewMap(parent=self))
        self.actionViewPlaneXsection.triggered.connect(
            lambda: NewViewXsection(parent=self)
        )
        self.actionViewStereoplot.triggered.connect(lambda: ViewStereoplot(parent=self))

        self.update_actors = True

    def closeEvent(self, event):
        """Re-implement the standard closeEvent method of QWidget and ask (1) to save project, and (2) for confirmation to quit."""
        reply = QMessageBox.question(
            self,
            "Closing Pzero",
            "Save the project?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.save_project()
        reply = QMessageBox.question(
            self,
            "Closing Pzero",
            "Confirm quit?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.project_close_signal.emit()  # this is used to delete open windows when the current project is closed
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
        selected_uids = []
        if self.shown_table == "tabGeology":
            selected_idxs_proxy = self.GeologyTableView.selectionModel().selectedRows(column=0)  # this will always give rows that have selected the column 0 (in this case uid). By changing the column=0 to another index it will give the value in another column
            for idx_proxy in selected_idxs_proxy:
                selected_uids.append(idx_proxy.data())

        elif self.shown_table == "tabXSections":
            selected_idxs_proxy = self.XSectionsTableView.selectionModel().selectedRows(column=0)
            for idx_proxy in selected_idxs_proxy:
                selected_uids.append(idx_proxy.data())

        elif self.shown_table == "tabMeshes3D":
            selected_idxs_proxy = self.Meshes3DTableView.selectionModel().selectedRows(column=0)
            for idx_proxy in selected_idxs_proxy:
                selected_uids.append(idx_proxy.data())

        elif self.shown_table == "tabDOMs":
            selected_idxs_proxy = self.DOMsTableView.selectionModel().selectedRows(column=0)
            for idx_proxy in selected_idxs_proxy:
                selected_uids.append(idx_proxy.data())
        elif self.shown_table == "tabImages":
            selected_idxs_proxy = self.ImagesTableView.selectionModel().selectedRows(column=0)
            for idx_proxy in selected_idxs_proxy:
                selected_uids.append(idx_proxy.data())

        elif self.shown_table == "tabBoundaries":
            selected_idxs_proxy = self.BoundariesTableView.selectionModel().selectedRows(column=0)
            for idx_proxy in selected_idxs_proxy:
                selected_uids.append(idx_proxy.data())

        elif self.shown_table == "tabWells":
            selected_idxs_proxy = self.WellsTableView.selectionModel().selectedRows(column=0)
            for idx_proxy in selected_idxs_proxy:
                selected_uids.append(idx_proxy.data())

        elif self.shown_table == "tabFluids":
            selected_idxs_proxy = self.FluidsTableView.selectionModel().selectedRows(column=0)
            for idx_proxy in selected_idxs_proxy:
                selected_uids.append(idx_proxy.data())

        elif self.shown_table == "tabBackgrounds":
            selected_idxs_proxy = self.BackgroundsTableView.selectionModel().selectedRows(column=0)
            for idx_proxy in selected_idxs_proxy:
                selected_uids.append(idx_proxy.data())
        return selected_uids

    # [Gabriele] This is should be used for cross collection operations (e.g. cut surfaces in the geology table with the DEM).
    # We could use this instead of selected_uids but we should impose validity checks for the different functions
    # @property
    # def selected_uids_all(self):
    #     """Returns a list of all uids selected in every table view."""
    #     tab_list = ["tabDOMs","tabGeology","tabXSections","tabMeshes3D","tabImages","tabBoundaries","tabWells","tabFluids"]
    #     selected_idxs = []
    #     selected_uids_all = []
    #     for tab in tab_list:
    #         if tab == "tabGeology":
    #             selected_idxs_proxy = self.GeologyTableView.selectionModel().selectedRows()
    #             for idx_proxy in selected_idxs_proxy:
    #                 selected_idxs.append(self.proxy_geol_coll.mapToSource(idx_proxy))
    #             for idx in selected_idxs:
    #                 selected_uids_all.append(self.geol_coll.data(index=idx, qt_role=Qt.DisplayRole))
    #         elif tab == "tabXSections":
    #             selected_idxs_proxy = self.XSectionsTableView.selectionModel().selectedRows()
    #             for idx_proxy in selected_idxs_proxy:
    #                 selected_idxs.append(self.proxy_xsect_coll.mapToSource(idx_proxy))
    #             for idx in selected_idxs:
    #                 selected_uids_all.append(self.xsect_coll.data(index=idx, qt_role=Qt.DisplayRole))
    #         elif tab == "tabMeshes3D":
    #             selected_idxs_proxy = self.Meshes3DTableView.selectionModel().selectedRows()
    #             for idx_proxy in selected_idxs_proxy:
    #                 selected_idxs.append(self.proxy_mesh3d_coll.mapToSource(idx_proxy))
    #             for idx in selected_idxs:
    #                 selected_uids_all.append(self.mesh3d_coll.data(index=idx, qt_role=Qt.DisplayRole))
    #         elif tab == "tabDOMs":
    #             selected_idxs_proxy = self.DOMsTableView.selectionModel().selectedRows()
    #             for idx_proxy in selected_idxs_proxy:
    #                 selected_idxs.append(self.proxy_dom_coll.mapToSource(idx_proxy))
    #             for idx in selected_idxs:
    #                 selected_uids_all.append(self.dom_coll.data(index=idx, qt_role=Qt.DisplayRole))
    #         elif tab == "tabImages":
    #             selected_idxs_proxy = self.ImagesTableView.selectionModel().selectedRows()
    #             for idx_proxy in selected_idxs_proxy:
    #                 selected_idxs.append(self.proxy_image_coll.mapToSource(idx_proxy))
    #             for idx in selected_idxs:
    #                 selected_uids_all.append(self.image_coll.data(index=idx, qt_role=Qt.DisplayRole))
    #         elif tab == "tabBoundaries":
    #             selected_idxs_proxy = self.BoundariesTableView.selectionModel().selectedRows()
    #             for idx_proxy in selected_idxs_proxy:
    #                 selected_idxs.append(self.proxy_boundary_coll.mapToSource(idx_proxy))
    #             for idx in selected_idxs:
    #                 selected_uids_all.append(self.boundary_coll.data(index=idx, qt_role=Qt.DisplayRole))
    #         elif tab == "tabWells":
    #             selected_idxs_proxy = self.WellsTableView.selectionModel().selectedRows()
    #             for idx_proxy in selected_idxs_proxy:
    #                 selected_idxs.append(self.proxy_well_coll.mapToSource(idx_proxy))
    #             for idx in selected_idxs:
    #                 selected_uids_all.append(self.well_coll.data(index=idx, qt_role=Qt.DisplayRole))
    #         elif tab == "tabFluids":
    #             selected_idxs_proxy = self.FluidsTableView.selectionModel().selectedRows()
    #             for idx_proxy in selected_idxs_proxy:
    #                 selected_idxs.append(self.proxy_well_coll.mapToSource(idx_proxy))
    #             for idx in selected_idxs:
    #                 selected_uids_all.append(self.fluids_coll.data(index=idx, qt_role=Qt.DisplayRole))
    #         elif tab == "tabBackgrounds":
    #             selected_idxs_proxy = self.BackgroundsTableView.selectionModel().selectedRows()
    #             for idx_proxy in selected_idxs_proxy:
    #                 selected_idxs.append(self.proxy_well_coll.mapToSource(idx_proxy))
    #             for idx in selected_idxs:
    #                 selected_uids_all.append(self.backgrounds_coll.data(index=idx, qt_role=Qt.DisplayRole))
    #     return selected_uids_all

    def entity_remove(self):
        """Remove entities selected in an attribute table. Just rows completely selected are removed."""
        if not self.selected_uids:
            return
        """Confirm removal dialog."""
        if len(self.selected_uids) > 10:
            msg = f"{self.selected_uids[:10]} and {len(self.selected_uids[10:])} more"
        else:
            msg = f"{self.selected_uids}"
        check = QMessageBox.question(
            self,
            "Remove Entities",
            (f"Do you really want to remove entities\n{msg}\nPlease confirm."),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if check == QMessageBox.No:
            return
        """Remove entities."""
        self.update_actors = False
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
                self.boundary_coll.remove_entity(uid=uid)
            elif self.shown_table == "tabWells":
                self.well_coll.remove_entity(uid=uid)
            elif self.shown_table == "tabFluids":
                self.fluids_coll.remove_entity(uid=uid)
            elif self.shown_table == "tabBackgrounds":
                self.backgrounds_coll.remove_entity(uid=uid)
        self.update_actors = True

    def entities_merge(self):
        # ____________________________________________________ CHECK (1) HOW PROPERTIES AND TEXTURES ARE AFFECTED BY MERGING, (2) HOW IT WORKS FOR DOMs
        """Merge entities of the same topology - VertexSet, PolyLine, TriSurf, ..."""
        if not self.selected_uids:
            return
        """Check if a suitable collection is selected."""
        if self.shown_table == "tabGeology":
            collection = self.geol_coll
            """Create deepcopy of the geological entity dictionary."""
            new_dict = deepcopy(collection.entity_dict)
            name_list = []
            topology_list = []
            role_list = []
            feature_list = []
            scenario_list = []
            xsect_list = []
            for uid in self.selected_uids:
                name_list.append(collection.get_uid_name(uid))
                topology_list.append(collection.get_uid_topology(uid))
                role_list.append(collection.get_uid_role(uid))
                feature_list.append(collection.get_uid_feature(uid))
                scenario_list.append(collection.get_uid_scenario(uid))
                xsect_list.append(collection.get_uid_scenario(uid))
            name_list = list(set(name_list))
            topology_list = list(set(topology_list))
            role_list = list(set(role_list))
            feature_list = list(set(feature_list))
            scenario_list = list(set(scenario_list))
            xsect_list = list(set(xsect_list))
            input_dict = {
                "name": ["New name: ", name_list],
                "topology": ["Topology", topology_list],
                "role": ["Role: ", role_list],
                "feature": ["Feature: ", feature_list],
                "scenario": ["Scenario: ", scenario_list],
                "x_section": ["XSection: ", xsect_list],
            }
        elif self.shown_table == "tabDOMs":
            collection = self.dom_coll
            """Create deepcopy of the geological entity dictionary."""
            new_dict = deepcopy(collection.entity_dict)
            name_list = []
            topology_list = []
            xsect_list = []
            for uid in self.selected_uids:
                name_list.append(collection.get_uid_name(uid))
                topology_list.append(collection.get_uid_topology(uid))
                xsect_list.append(collection.get_uid_scenario(uid))
            name_list = list(set(name_list))
            topology_list = list(set(topology_list))
            xsect_list = list(set(xsect_list))
            input_dict = {
                "name": ["New name: ", name_list],
                "topology": ["Topology", topology_list],
                "x_section": ["XSection: ", xsect_list],
            }
        else:
            return
        updt_dict = multiple_input_dialog(
            title="Merge entities to multi-part", input_dict=input_dict
        )
        """Check if the output of the widget is empty or not. If the Cancel button was clicked, the tool quits"""
        if updt_dict is None:
            return
        """Set the values that have been typed by the user through the multiple input widget."""
        for key in updt_dict:
            new_dict[key] = updt_dict[key]
        """Create an empty vtk entity from classes VertexSet, PolyLine, TriSurf, XsVertexSet, XsPolyLine (geology), 
        TSDom, PCDom (DOM)."""
        if new_dict["topology"] == "VertexSet":
            new_dict["vtk_obj"] = VertexSet()
        elif new_dict["topology"] == "PolyLine":
            new_dict["vtk_obj"] = PolyLine()
        elif new_dict["topology"] == "TriSurf":
            new_dict["vtk_obj"] = TriSurf()
        elif new_dict["topology"] == "XsVertexSet":
            new_dict["vtk_obj"] = XsVertexSet()
        elif new_dict["topology"] == "XsPolyLine":
            new_dict["vtk_obj"] = XsPolyLine()
        elif new_dict["topology"] == "TSDom":
            new_dict["vtk_obj"] = TSDom()
        elif new_dict["topology"] == "PCDom":
            new_dict["vtk_obj"] = PCDom()
        else:
            return
        """Ask whether to keep or removed merged entities."""
        remove_merged_option = options_dialog(
            title="Remove merged entities?",
            message="Do you want to keep or remove merged entities?",
            yes_role="Keep",
            no_role="Remove",
            reject_role="Quit merging",
        )
        if not (remove_merged_option == 0 or remove_merged_option == 1):
            return
        """Create a vtkAppendPolyData filter to merge all input vtk objects"""
        vtkappend = vtkAppendPolyData()
        """Loop that collects all selected items to create the merge. Only entities of the same
        topology as chosen in the widget are merged, others are discarded."""
        for uid in self.selected_uids:
            if new_dict["topology"] == collection.get_uid_topology(uid):
                vtkappend.AddInputData(collection.get_uid_vtk_obj(uid))
                if remove_merged_option == 1:
                    collection.remove_entity(uid=uid)
        vtkappend.Update()
        """ShallowCopy is the way to copy the new vtk object into the empty instance created above."""
        new_dict["vtk_obj"].ShallowCopy(vtkappend.GetOutput())
        new_dict["vtk_obj"].Modified()
        """Test if the merged object is not empty."""
        if new_dict["vtk_obj"].points_number == 0:
            return
        """Add new entity from surf_dict. Function add_entity_from_dict creates a new uid"""
        uid_new = collection.add_entity_from_dict(new_dict)

    def texture_add(self):
        """Add texture to selected DEMs. Just rows completely selected are considered."""
        if not self.shown_table == "tabDOMs":
            return
        if not self.selected_uids:
            return
        """Map Image selection dialog."""
        map_image_names = self.image_coll.df.loc[
            self.image_coll.df["topology"] == "MapImage", "name"
        ].to_list()
        map_image_name = input_combo_dialog(
            parent=None,
            title="Add texture to DEM",
            label="Choose Map Image",
            choice_list=map_image_names,
        )
        if not map_image_name:
            return
        map_image_uid = self.image_coll.df.loc[
            self.image_coll.df["name"] == map_image_name, "uid"
        ].values[0]
        if map_image_uid not in self.image_coll.get_uids:
            return
        """Add textures."""
        dom_uids = self.selected_uids
        for dom_uid in dom_uids:
            if isinstance(self.dom_coll.get_uid_vtk_obj(dom_uid), DEM):
                self.dom_coll.add_map_texture_to_dom(
                    dom_uid=dom_uid, map_image_uid=map_image_uid
                )

    def texture_remove(self):
        """Remove texture to selected DEMs. Just rows completely selected are considered."""
        if not self.shown_table == "tabDOMs":
            return
        if not self.selected_uids:
            return
        """Map Image selection dialog."""
        map_image_names = self.image_coll.df.loc[
            self.image_coll.df["topology"] == "MapImage", "name"
        ].to_list()
        map_image_name = input_combo_dialog(
            parent=None,
            title="Remove texture from DEM",
            label="Choose Map Image",
            choice_list=map_image_names,
        )
        if not map_image_name:
            return
        map_image_uid = self.image_coll.df.loc[
            self.image_coll.df["name"] == map_image_name, "uid"
        ].values[0]
        if map_image_uid not in self.image_coll.get_uids:
            return
        """Remove textures."""
        if map_image_uid in self.image_coll.get_uids:
            dom_uids = self.selected_uids
            for dom_uid in dom_uids:
                self.dom_coll.remove_map_texture_from_dom(
                    dom_uid=dom_uid, map_image_uid=map_image_uid
                )

    def property_add(self):
        # ____________________________________________________ ADD IMAGES
        """Add empty property on geological entity"""
        if not self.shown_table in ["tabGeology", "tabMeshes3D", "tabDOMs"]:
            return
        if not self.selected_uids:
            return
        input_dict = {
            "property_name": ["Property name: ", "new_property"],
            "property_components": ["Property components: ", 1],
        }
        if not input_dict:
            return
        updt_dict = multiple_input_dialog(
            title="Add empty property", input_dict=input_dict
        )
        if self.shown_table == "tabGeology":
            for uid in self.selected_uids:
                if not updt_dict["property_name"] in self.geol_coll.get_uid_properties_names(uid):
                    self.geol_coll.append_uid_property(
                        uid=uid,
                        property_name=updt_dict["property_name"],
                        property_components=updt_dict["property_components"],
                    )
        elif self.shown_table == "tabMeshes3D":
            for uid in self.selected_uids:
                if not updt_dict["property_name"] in self.mesh3d_coll.get_uid_properties_names(uid):
                    self.mesh3d_coll.append_uid_property(
                        uid=uid,
                        property_name=updt_dict["property_name"],
                        property_components=updt_dict["property_components"],
                    )
        elif self.shown_table == "tabDOMs":
            for uid in self.selected_uids:
                if not updt_dict["property_name"] in self.dom_coll.get_uid_properties_names(uid):
                    self.dom_coll.append_uid_property(
                        uid=uid,
                        property_name=updt_dict["property_name"],
                        property_components=updt_dict["property_components"],
                    )
        """Finally update properties legend."""
        self.prop_legend.update_widget(self)

    def property_remove(self):
        # ____________________________________________________ ADD IMAGES
        if not self.shown_table in ["tabGeology", "tabMeshes3D", "tabDOMs"]:
            return
        if not self.selected_uids:
            return
        if self.shown_table == "tabGeology":
            property_name_list = self.geol_coll.get_uid_properties_names(
                uid=self.selected_uids[0]
            )
            if len(self.selected_uids) > 1:
                for uid in self.selected_uids[1:]:
                    property_name_list = list(
                        set(property_name_list)
                        & set(self.geol_coll.get_uid_properties_names(uid=uid))
                    )
            if property_name_list == []:
                return
            property_name = input_combo_dialog(
                parent=None,
                title="Remove selected property",
                label="Remove property",
                choice_list=property_name_list,
            )
            for uid in self.selected_uids:
                self.geol_coll.remove_uid_property(uid=uid, property_name=property_name)
        elif self.shown_table == "tabMeshes3D":
            property_name_list = self.mesh3d_coll.get_uid_properties_names(
                uid=self.selected_uids[0]
            )
            if len(self.selected_uids) > 1:
                for uid in self.selected_uids[1:]:
                    property_name_list = list(
                        set(property_name_list)
                        & set(self.mesh3d_coll.get_uid_properties_names(uid=uid))
                    )
            if property_name_list == []:
                return
            property_name = input_combo_dialog(
                parent=None,
                title="Remove selected property",
                label="Remove property",
                choice_list=property_name_list,
            )
            for uid in self.selected_uids:
                self.mesh3d_coll.remove_uid_property(
                    uid=uid, property_name=property_name
                )
        elif self.shown_table == "tabDOMs":
            property_name_list = self.dom_coll.get_uid_properties_names(
                uid=self.selected_uids[0]
            )
            if len(self.selected_uids) > 1:
                for uid in self.selected_uids[1:]:
                    property_name_list = list(
                        set(property_name_list)
                        & set(self.dom_coll.get_uid_properties_names(uid=uid))
                    )
            if property_name_list == []:
                return
            property_name = input_combo_dialog(
                parent=None,
                title="Remove selected property",
                label="Remove property",
                choice_list=property_name_list,
            )
            for uid in self.selected_uids:
                self.dom_coll.remove_uid_property(uid=uid, property_name=property_name)
        """Finally update properties legend."""
        self.prop_legend.update_widget(self)

    def normals_calculate(self):
        # ____________________________________________________ ADD MORE CASES FOR POINT CLOUDS ETC.
        """Calculate Normals on geological entities (add point clouds and DOMS in the future)."""
        if self.shown_table in ["tabGeology", "tabMeshes3D", "tabDOMs"]:
            if self.selected_uids:
                set_normals(self)

    def lineations_calculate(self):
        # ____________________________________________________ IMPLEMENT THIS FOR POINTS WITH PLUNGE/TREND AND FOR POLYLINES
        """Calculate lineations on geological entities."""
        pass

    def build_octree(self):
        if self.selected_uids:
            for uid in self.selected_uids:
                if self.shown_table == "tabGeology":
                    entity = self.geol_coll.get_uid_vtk_obj(uid)
                elif self.shown_table == "tabXSections":
                    entity = self.xsect_coll.get_uid_vtk_obj(uid)
                elif self.shown_table == "tabMeshes3D":
                    entity = self.mesh3d_coll.get_uid_vtk_obj(uid)
                elif self.shown_table == "tabDOMs":
                    entity = self.dom_coll.get_uid_vtk_obj(uid)
                elif self.shown_table == "tabImages":
                    entity = self.image_coll.get_uid_vtk_obj(uid)
                elif self.shown_table == "tabBoundaries":
                    entity = self.boundary_coll.get_uid_vtk_obj(uid)
                elif self.shown_table == "tabWells":
                    entity = self.well_coll.get_uid_vtk_obj(uid)

                octree = vtkOctreePointLocator()
                octree.SetDataSet(entity)
                octree.BuildLocator()
                entity.locator = octree

    def decimate_pc_dialog(self):
        if self.selected_uids:
            fac = (
                input_one_value_dialog(
                    parent=self,
                    title="Decimation factor",
                    label="Set the decimation factor (% of the original)",
                    default_value=100.0,
                )
                / 100
            )
            for uid in self.selected_uids:
                if self.shown_table == "tabDOMs":
                    collection = self.dom_coll
                    entity = collection.get_uid_vtk_obj(uid)

                    vtk_object = decimate_pc(entity, fac)
                    vtk_out_dict = deepcopy(
                        collection.df.loc[collection.df["uid"] == uid]
                        .drop(["uid", "vtk_obj"], axis=1)
                        .to_dict("records")[0]
                    )
                    name = vtk_out_dict["name"]
                    vtk_out_dict["uid"] = None
                    vtk_out_dict["name"] = f"{name}_subsamp_{fac}"
                    vtk_out_dict["vtk_obj"] = vtk_object
                    collection.add_entity_from_dict(entity_dict=vtk_out_dict)
                else:
                    print("Only Point clouds are supported")
                    return
        else:
            print("No entity selected")

    def smooth_dialog(self):
        input_dict = {
            "convergence_value": ["Convergence value:", 1],
            "boundary_smoothing": ["Boundary smoothing", False],
            "edge_smoothing": ["Edge smoothing", False],
        }
        surf_dict_updt = multiple_input_dialog(
            title="Surface smoothing", input_dict=input_dict, return_widget=True
        )

        sel_uids = self.selected_uids
        if len(sel_uids) > 1:
            print("Multiple surfaces selected, only one will be previewed")
        elif len(sel_uids) == 0:
            print("No selected objects")
            return

        for uid in sel_uids:
            mesh = self.geol_coll.get_uid_vtk_obj(uid)

        PreviewWidget(
            parent=self,
            titles=["Original mesh", "Smoothed mesh"],
            mesh=mesh,
            opt_widget=surf_dict_updt,
            function=surface_smoothing,
        )

    def subd_res_dialog(self):
        input_dict = {
            "type": ["Subdivision type:", ["linear", "butterfly", "loop"]],
            "n_subd": ["Number of iterations", 2],
        }
        subd_input = multiple_input_dialog(
            "Subdivision dialog", input_dict, return_widget=True
        )

        sel_uids = self.selected_uids
        if len(sel_uids) > 1:
            print("Multiple surfaces selected, only one will be previewed")
        elif len(sel_uids) == 0:
            print("No selected objects")
            return

        for uid in sel_uids:
            mesh = self.geol_coll.get_uid_vtk_obj(uid)

        PreviewWidget(
            parent=self,
            titles=["Original mesh", "Subdivided mesh"],
            mesh=mesh,
            opt_widget=subd_input,
            function=subdivision_resampling,
        )
        # subdivision_resampling(self,type=subd_input['type'],n_subd=subd_input['n_subd'])

    def retopologize_surface(self):
        input_dict = {
            "dec_int": ["Decimation intensity: ", 0],
            "n_iter": ["Number of iterations: ", 40],
            "rel_fac": ["Relaxation factor: ", 0.1],
        }
        retop_par_widg = multiple_input_dialog(
            title="Retopologize surface", input_dict=input_dict, return_widget=True
        )

        sel_uids = self.selected_uids
        if len(sel_uids) > 1:
            print("Multiple surfaces selected, only one will be previewed")
        elif len(sel_uids) == 0:
            print("No selected objects")
            return

        for uid in sel_uids:
            mesh = self.geol_coll.get_uid_vtk_obj(uid)

        PreviewWidget(
            parent=self,
            titles=["Original mesh", "Retopologized mesh"],
            opt_widget=retop_par_widg,
            function=retopo,
        )

    def connected_parts(self):
        """Calculate connectivity of PolyLine and TriSurf entities."""
        if self.selected_uids:
            if self.shown_table == "tabGeology":
                collection = self.geol_coll
            elif self.shown_table == "tabDOMs":
                collection = self.dom_coll
            elif self.shown_table == "tabBoundaries":
                collection = self.boundary_coll
            else:
                return
            for uid in self.selected_uids:
                if isinstance(collection.get_uid_vtk_obj(uid), (PolyLine, TriSurf)):
                    collection.append_uid_property(
                        uid=uid, property_name="RegionId", property_components=1
                    )
                    collection.get_uid_vtk_obj(uid).connected_calc()
                elif isinstance(collection.get_uid_vtk_obj(uid), PCDom):
                    collection.append_uid_property(
                        uid=uid, property_name="ClusterId", property_components=1
                    )
                    collection.get_uid_vtk_obj(uid).connected_calc()
            self.prop_legend.update_widget(self)

    def split_multipart(self):
        """Split multi-part entities into single-parts."""
        if self.selected_uids:
            if self.shown_table == "tabGeology":
                collection = self.geol_coll
            elif self.shown_table == "tabDOMs":
                collection = self.dom_coll
            elif self.shown_table == "tabBoundaries":
                collection = self.boundary_coll
            else:
                return
            for uid in self.selected_uids:
                if isinstance(collection.get_uid_vtk_obj(uid), (PolyLine, TriSurf)):
                    if "RegionId" not in collection.get_uid_properties_names(uid):
                        collection.append_uid_property(
                            uid=uid, property_name="RegionId", property_components=1
                        )
                    vtk_out_list = collection.get_uid_vtk_obj(uid).split_parts()

                    for i, vtk_object in enumerate(vtk_out_list):
                        vtk_out_dict = deepcopy(
                            collection.df.loc[collection.df["uid"] == uid]
                            .drop(["uid", "vtk_obj"], axis=1)
                            .to_dict("records")[0]
                        )
                        name = vtk_out_dict["name"]
                        vtk_out_dict["uid"] = None
                        vtk_out_dict["name"] = f"{name}_{i}"
                        vtk_out_dict["vtk_obj"] = vtk_object
                        collection.add_entity_from_dict(entity_dict=vtk_out_dict)
                    collection.remove_entity(uid)
                elif isinstance(collection.get_uid_vtk_obj(uid), PCDom):
                    vtk_out_list = collection.get_uid_vtk_obj(uid).split_parts()
                    for i, vtk_object in enumerate(vtk_out_list):
                        vtk_out_dict = deepcopy(
                            collection.df.loc[collection.df["uid"] == uid]
                            .drop(["uid", "vtk_obj"], axis=1)
                            .to_dict("records")[0]
                        )
                        name = vtk_out_dict["name"]
                        vtk_out_dict["uid"] = None
                        vtk_out_dict["name"] = f"{name}_{i}"
                        vtk_out_dict["vtk_obj"] = vtk_object
                        collection.add_entity_from_dict(entity_dict=vtk_out_dict)
                    collection.remove_entity(uid)

            self.prop_legend.update_widget(self)

    """Methods used to save/open/create new projects."""

    def create_empty(self):
        """Create empty containers for a new empty project."""
        self.project_close_signal.emit()  # this is used to delete open windows when the current project is closed (and a new one is opened)

        """Create the geol_coll GeologicalCollection (a Qt QAbstractTableModel with a Pandas dataframe as attribute)
        and connect the model to GeologyTableView (a Qt QTableView created with QTDesigner and provided by
        Ui_ProjectWindow). Setting the model also updates the view."""
        self.geol_coll = GeologicalCollection(parent=self)
        self.GeologyTableView.setModel(self.geol_coll.proxy_table_model)

        """Create the xsect_coll XSectionCollection (a Qt QAbstractTableModel with a Pandas dataframe as attribute)
        and connect the model to XSectionsTableView (a Qt QTableView created with QTDesigner and provided by
        Ui_ProjectWindow). Setting the model also updates the view."""
        self.xsect_coll = XSectionCollection(parent=self)
        self.XSectionsTableView.setModel(self.xsect_coll.proxy_table_model)

        """Create the dom_coll DomCollection (a Qt QAbstractTableModel with a Pandas dataframe as attribute)
        and connect the model to DOMsTableView (a Qt QTableView created with QTDesigner and provided by
        Ui_ProjectWindow). Setting the model also updates the view."""
        self.dom_coll = DomCollection(parent=self)
        self.DOMsTableView.setModel(self.dom_coll.proxy_table_model)

        """Create the image_coll ImageCollection (a Qt QAbstractTableModel with a Pandas dataframe as attribute)
        and connect the model to ImagesTableView (a Qt QTableView created with QTDesigner and provided by
        Ui_ProjectWindow). Setting the model also updates the view."""
        self.image_coll = ImageCollection(parent=self)
        self.ImagesTableView.setModel(self.image_coll.proxy_table_model)

        """Create the mesh3d_coll Mesh3DCollection (a Qt QAbstractTableModel with a Pandas dataframe as attribute)
        and connect the model to Meshes3DTableView (a Qt QTableView created with QTDesigner and provided by
        Ui_ProjectWindow). Setting the model also updates the view."""
        self.mesh3d_coll = Mesh3DCollection(parent=self)
        self.Meshes3DTableView.setModel(self.mesh3d_coll.proxy_table_model)

        """Create the boundary_coll BoundaryCollection (a Qt QAbstractTableModel with a Pandas dataframe as attribute)
        and connect the model to BoundaryTableView (a Qt QTableView created with QTDesigner and provided by
        Ui_ProjectWindow). Setting the model also updates the view."""
        self.boundary_coll = BoundaryCollection(parent=self)
        self.BoundariesTableView.setModel(self.boundary_coll.proxy_table_model)

        """[Gabriele]  Create the weel_coll WellCollection (a Qt QAbstractTableModel with a Pandas dataframe as attribute)
        and connect the model to WellTableView (a Qt QTableView created with QTDesigner and provided by
        Ui_ProjectWindow). Setting the model also updates the view."""
        self.well_coll = WellCollection(parent=self)
        self.WellsTableView.setModel(self.well_coll.proxy_table_model)

        """[Gabriele]  Create the fluids_coll FluidsCollection (a Qt QAbstractTableModel with a Pandas dataframe as attribute)
        and connect the model to FluidTableView (a Qt QTableView created with QTDesigner and provided by
        Ui_ProjectWindow). Setting the model also updates the view."""
        self.fluids_coll = FluidsCollection(parent=self)
        self.FluidsTableView.setModel(self.fluids_coll.proxy_table_model)

        """[Gabriele]  Create the backgrounds_coll BackgroundCollection (a Qt QAbstractTableModel with a Pandas dataframe as attribute)
        and connect the model to FluidTableView (a Qt QTableView created with QTDesigner and provided by
        Ui_ProjectWindow). Setting the model also updates the view."""
        self.backgrounds_coll = BackgroundCollection(parent=self)
        self.BackgroundsTableView.setModel(self.backgrounds_coll.proxy_table_model)

        """Create the geol_coll.legend_df legend table (a Pandas dataframe), create the corresponding QT
        Legend self.legend (a Qt QTreeWidget that is internally connected to its data source),
        and update the widget."""
        self.geol_coll.legend_df = pd_DataFrame(columns=list(Legend.geol_legend_dict.keys()))
        self.well_legend_df = pd_DataFrame(columns=list(Legend.well_legend_dict.keys()))
        self.fluids_coll.legend_df = pd_DataFrame(
            columns=list(Legend.fluids_legend_dict.keys())
        )
        self.backgrounds_coll.legend_df = pd_DataFrame(
            columns=list(Legend.backgrounds_legend_dict.keys())
        )

        self.others_legend_df = pd_DataFrame(deepcopy(Legend.others_legend_dict))
        self.legend = Legend()
        self.legend.update_widget(parent=self)

        """Create the prop_legend_df table (a Pandas dataframe), create the corresponding QT
        PropertiesCMaps table widget self.prop_legend (a Qt QTableWidget that is internally connected to its data source),
        and update the widget."""  # ____________________________________________________________________________________ UPDATE THIS TO ALLOW SORTING BY PROPERTY NAME
        self.prop_legend_df = pd_DataFrame(PropertiesCMaps.prop_cmap_dict)
        self.prop_legend = PropertiesCMaps()
        self.prop_legend.update_widget(parent=self)

    def save_project(self):
        # ________________________________________WRITERS TO BE MOVED TO COLLECTIONS
        """Save project to file and folder"""
        """Get date and time, used to save incremental revisions."""
        now = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        """Select and open output file and folder. Saving always performs a complete backup since the output folder
        is named with the present date and time "rev_<now>"."""
        self.out_file_name = save_file_dialog(
            parent=self, caption="Save project.", filter="PZero (*.p0)"
        )
        if not self.out_file_name:
            return
        out_dir_name = self.out_file_name[:-3] + "_p0/rev_" + now
        self.TextTerminal.appendPlainText(
            (
                "Saving project as VTK files and csv tables with metada and legend.\n"
                + "In file/folder: "
                "" + self.out_file_name + " / " + out_dir_name + "\n"
            )
        )
        """Create the folder if it does not exist already."""
        if not os.path.isdir(self.out_file_name[:-3] + "_p0"):
            os.mkdir(self.out_file_name[:-3] + "_p0")
        os.mkdir(out_dir_name)
        """Save the root file pointing to the folder."""
        fout = open(self.out_file_name, "w")
        fout.write(
            "PZero project file saved in folder with the same name, including VTK files and CSV tables.\n"
        )
        fout.write("Last saved revision:\n")
        fout.write("rev_" + now)
        fout.close()

        """--------------------- SAVE LEGENDS ---------------------"""

        """Save geological legend table to JSON file. Keep old CSV table format here in comments, in case it might be useful in the future."""
        self.geol_coll.legend_df.to_json(
            out_dir_name + "/geol_legend_table.json", orient="index"
        )
        # self.geol_coll.legend_df.to_csv(out_dir_name + '/geol_legend_table.csv', encoding='utf-8', index=False)
        """Save others legend table to JSON file."""
        self.others_legend_df.to_json(
            out_dir_name + "/others_legend_table.json", orient="index"
        )
        # self.others_legend_df.to_csv(out_dir_name + '/others_legend_table.csv', encoding='utf-8', index=False)
        """Save properties legend table to JSON file."""
        self.prop_legend_df.to_json(
            out_dir_name + "/prop_legend_df.json", orient="index"
        )
        # self.prop_legend_df.to_csv(out_dir_name + '/prop_legend_df.csv', encoding='utf-8', index=False)

        self.well_legend_df.to_json(
            out_dir_name + "/well_legend_table.json", orient="index"
        )

        self.fluids_coll.legend_df.to_json(
            out_dir_name + "/fluids_legend_table.json", orient="index"
        )

        self.backgrounds_coll.legend_df.to_json(
            out_dir_name + "/backgrounds_legend_table.json", orient="index"
        )

        """--------------------- SAVE tables ---------------------"""

        """Save x_section table to JSON file."""
        out_cols = list(self.xsect_coll.df.columns)
        out_cols.remove("vtk_plane")
        out_cols.remove("vtk_frame")
        self.xsect_coll.df[out_cols].to_json(
            out_dir_name + "/xsection_table.json", orient="index"
        )
        # self.xsect_coll.df[out_cols].to_csv(out_dir_name + '/xsection_table.csv', encoding='utf-8', index=False)

        """Save geological collection table to JSON file and entities as VTK."""
        out_cols = list(self.geol_coll.df.columns)
        out_cols.remove("vtk_obj")
        self.geol_coll.df[out_cols].to_json(
            out_dir_name + "/geological_table.json", orient="index"
        )
        # self.geol_coll.df[out_cols].to_csv(out_dir_name + '/geological_table.csv', encoding='utf-8', index=False)
        prgs_bar = progress_dialog(
            max_value=self.geol_coll.df.shape[0],
            title_txt="Save geology",
            label_txt="Saving geological objects...",
            cancel_txt=None,
            parent=self,
        )
        for uid in self.geol_coll.df["uid"].to_list():
            pd_writer = vtkXMLPolyDataWriter()
            pd_writer.SetFileName(out_dir_name + "/" + uid + ".vtp")
            pd_writer.SetInputData(self.geol_coll.get_uid_vtk_obj(uid))
            pd_writer.Write()
            prgs_bar.add_one()

        """Save DOM collection table to JSON file and entities as VTK."""
        out_cols = list(self.dom_coll.df.columns)
        out_cols.remove("vtk_obj")
        self.dom_coll.df[out_cols].to_json(
            out_dir_name + "/dom_table.json", orient="index"
        )
        # self.dom_coll.df[out_cols].to_csv(out_dir_name + '/dom_table.csv', encoding='utf-8', index=False)
        prgs_bar = progress_dialog(
            max_value=self.dom_coll.df.shape[0],
            title_txt="Save DOM",
            label_txt="Saving DOM objects...",
            cancel_txt=None,
            parent=self,
        )
        for uid in self.dom_coll.df["uid"].to_list():
            if (
                self.dom_coll.df.loc[self.dom_coll.df["uid"] == uid, "topology"].values[
                    0
                ]
                == "DEM"
            ):
                sg_writer = vtkXMLStructuredGridWriter()
                sg_writer.SetFileName(out_dir_name + "/" + uid + ".vts")
                sg_writer.SetInputData(self.dom_coll.get_uid_vtk_obj(uid))
                sg_writer.Write()
                prgs_bar.add_one()
            elif (
                self.dom_coll.df.loc[self.dom_coll.df["uid"] == uid, "topology"].values[
                    0
                ]
                == "DomXs"
            ):
                pl_writer = vtkXMLPolyDataWriter()
                pl_writer.SetFileName(out_dir_name + "/" + uid + ".vtp")
                pl_writer.SetInputData(self.dom_coll.get_uid_vtk_obj(uid))
                pl_writer.Write()
                prgs_bar.add_one()
            elif (
                self.dom_coll.df.loc[self.dom_coll.df["uid"] == uid, "topology"].values[
                    0
                ]
                == "PCDom"
            ):  # _____________ PROBABLY THE SAME WILL WORK FOR TSDOMs
                """Save PCDOm collection entities as VTK"""
                pd_writer = vtkXMLPolyDataWriter()
                pd_writer.SetFileName(out_dir_name + "/" + uid + ".vtp")
                pd_writer.SetInputData(self.dom_coll.get_uid_vtk_obj(uid))
                pd_writer.Write()
                prgs_bar.add_one()

        """Save image collection table to JSON file and entities as VTK."""
        out_cols = list(self.image_coll.df.columns)
        out_cols.remove("vtk_obj")
        self.image_coll.df[out_cols].to_json(
            out_dir_name + "/image_table.json", orient="index"
        )
        # self.image_coll.df[out_cols].to_csv(out_dir_name + '/image_table.csv', encoding='utf-8', index=False)
        prgs_bar = progress_dialog(
            max_value=self.image_coll.df.shape[0],
            title_txt="Save image",
            label_txt="Saving image objects...",
            cancel_txt=None,
            parent=self,
        )
        for uid in self.image_coll.df["uid"].to_list():
            if self.image_coll.df.loc[
                self.image_coll.df["uid"] == uid, "topology"
            ].values[0] in ["MapImage", "XsImage", "TSDomImage"]:
                im_writer = vtkXMLImageDataWriter()
                im_writer.SetFileName(out_dir_name + "/" + uid + ".vti")
                im_writer.SetInputData(self.image_coll.get_uid_vtk_obj(uid))
                im_writer.Write()
                prgs_bar.add_one()
            elif self.image_coll.df.loc[
                self.image_coll.df["uid"] == uid, "topology"
            ].values[0] in ["Seismics"]:
                sg_writer = vtkXMLStructuredGridWriter()
                sg_writer.SetFileName(out_dir_name + "/" + uid + ".vts")
                sg_writer.SetInputData(self.image_coll.get_uid_vtk_obj(uid))
                sg_writer.Write()

        """Save mesh3d collection table to JSON file and entities as VTK."""
        out_cols = list(self.mesh3d_coll.df.columns)
        out_cols.remove("vtk_obj")
        self.mesh3d_coll.df[out_cols].to_json(
            out_dir_name + "/mesh3d_table.json", orient="index"
        )
        # self.mesh3d_coll.df[out_cols].to_csv(out_dir_name + '/mesh3d_table.csv', encoding='utf-8', index=False)
        prgs_bar = progress_dialog(
            max_value=self.mesh3d_coll.df.shape[0],
            title_txt="Save 3D mesh",
            label_txt="Saving 3D mesh objects...",
            cancel_txt=None,
            parent=self,
        )
        for uid in self.mesh3d_coll.df["uid"].to_list():
            if self.mesh3d_coll.df.loc[
                self.mesh3d_coll.df["uid"] == uid, "topology"
            ].values[0] in ["Voxet", "XsVoxet"]:
                im_writer = vtkXMLImageDataWriter()
                im_writer.SetFileName(out_dir_name + "/" + uid + ".vti")
                im_writer.SetInputData(self.mesh3d_coll.get_uid_vtk_obj(uid))
                im_writer.Write()
            prgs_bar.add_one()

        """Save boundaries collection table to JSON file and entities as VTK."""
        out_cols = list(self.boundary_coll.df.columns)
        out_cols.remove("vtk_obj")
        self.boundary_coll.df[out_cols].to_json(
            out_dir_name + "/boundary_table.json", orient="index"
        )
        # self.boundary_coll.df[out_cols].to_csv(out_dir_name + '/boundary_table.csv', encoding='utf-8', index=False)
        prgs_bar = progress_dialog(
            max_value=self.boundary_coll.df.shape[0],
            title_txt="Save boundary",
            label_txt="Saving boundary objects...",
            cancel_txt=None,
            parent=self,
        )
        for uid in self.boundary_coll.df["uid"].to_list():
            pd_writer = vtkXMLPolyDataWriter()
            pd_writer.SetFileName(out_dir_name + "/" + uid + ".vtp")
            pd_writer.SetInputData(self.boundary_coll.get_uid_vtk_obj(uid))
            pd_writer.Write()
            prgs_bar.add_one()

        """Save wells collection table to JSON file and entities as VTK."""

        out_cols = list(self.well_coll.df.columns)
        out_cols.remove("vtk_obj")
        self.well_coll.df[out_cols].to_json(
            out_dir_name + "/well_table.json", orient="index"
        )
        # self.boundary_coll.df[out_cols].to_csv(out_dir_name + '/boundary_table.csv', encoding='utf-8', index=False)
        prgs_bar = progress_dialog(
            max_value=self.well_coll.df.shape[0],
            title_txt="Save wells",
            label_txt="Saving well objects...",
            cancel_txt=None,
            parent=self,
        )
        for uid in self.well_coll.df["uid"].to_list():
            pd_writer = vtkXMLPolyDataWriter()
            pd_writer.SetFileName(out_dir_name + "/" + uid + ".vtp")
            pd_writer.SetInputData(self.well_coll.get_uid_vtk_obj(uid))
            pd_writer.Write()
            prgs_bar.add_one()

        """Save fluids collection table to JSON file and entities as VTK."""
        out_cols = list(self.fluids_coll.df.columns)
        out_cols.remove("vtk_obj")
        self.fluids_coll.df[out_cols].to_json(
            out_dir_name + "/fluids_table.json", orient="index"
        )
        # self.geol_coll.df[out_cols].to_csv(out_dir_name + '/geological_table.csv', encoding='utf-8', index=False)
        prgs_bar = progress_dialog(
            max_value=self.fluids_coll.df.shape[0],
            title_txt="Save fluids",
            label_txt="Saving fluid objects...",
            cancel_txt=None,
            parent=self,
        )
        for uid in self.fluids_coll.df["uid"].to_list():
            pd_writer = vtkXMLPolyDataWriter()
            pd_writer.SetFileName(out_dir_name + "/" + uid + ".vtp")
            pd_writer.SetInputData(self.fluids_coll.get_uid_vtk_obj(uid))
            pd_writer.Write()
            prgs_bar.add_one()

        """Save Backgrounds collection table to JSON file and entities as VTK."""
        out_cols = list(self.backgrounds_coll.df.columns)
        out_cols.remove("vtk_obj")
        self.backgrounds_coll.df[out_cols].to_json(
            out_dir_name + "/backgrounds_table.json", orient="index"
        )
        # self.geol_coll.df[out_cols].to_csv(out_dir_name + '/geological_table.csv', encoding='utf-8', index=False)
        prgs_bar = progress_dialog(
            max_value=self.backgrounds_coll.df.shape[0],
            title_txt="Save Backgrounds",
            label_txt="Saving Backgrounds objects...",
            cancel_txt=None,
            parent=self,
        )
        for uid in self.backgrounds_coll.df["uid"].to_list():
            pd_writer = vtkXMLPolyDataWriter()
            pd_writer.SetFileName(out_dir_name + "/" + uid + ".vtp")
            pd_writer.SetInputData(self.backgrounds_coll.get_uid_vtk_obj(uid))
            pd_writer.Write()
            prgs_bar.add_one()

    def new_project(self):
        """Creates a new empty project, after having cleared all variables."""
        """Ask confirmation if the project already contains entities in the geological collection."""
        if self.geol_coll.get_number_of_entities > 0:
            confirm_new = QMessageBox.question(
                self,
                "New Project",
                "Clear all entities and variables of the present project?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if confirm_new == QMessageBox.No:
                return
        """Create empty containers."""
        self.create_empty()
        # """Save a new empty project to file"""
        # self.save_project()

    def open_project(self):
        """Opens a project previously saved to disk."""
        # Create empty containers. This clears all previous objects and also allows for missing tables below.
        if self.geol_coll.get_number_of_entities > 0:
            confirm_new = QMessageBox.question(
                self,
                "Open Project",
                "Save all entities and variables of the present project?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if confirm_new == QMessageBox.Yes:
                self.save_project()

        self.create_empty()

        # Select and open project file.
        in_file_name = open_file_dialog(
            parent=self, caption="Open PZero project", filter=("PZero (*.p0)")
        )
        if not in_file_name:
            return
        self.out_file_name = in_file_name

        # Read name of last revision in project file. This opens the last revision.
        # To open a different one, edit the project file.
        # ___________________________________ IN THE FUTURE an option to open a specific revision could be added
        fin = open(in_file_name, "rt")
        rev_name = fin.readlines()[2].strip()
        fin.close()
        in_dir_name = in_file_name[:-3] + "_p0/" + rev_name
        self.TextTerminal.appendPlainText(
            ("Opening project/revision : " + in_file_name + "/" + rev_name + "\n")
        )
        if not os.path.isdir(in_dir_name):
            print(in_dir_name)
            print("error: missing folder")
            return

        #  In the following it is still possible to open old projects with metadata stored
        #  as CSV tables, however JSON is used now because it leads to fewer problems and errors
        #  for numeric and list fields. In fact, reading Pandas dataframes from JSON, dtype
        #  from the class definitions specifies the type of each column.
        # ______ CONSIDER REMOVING THE POSSIBILITY TO OPEN OLD PROJECTS WITH CSV TABLES
        # ______ THAT WILL CAUSE ERRORS IN CASE OF LISTS

        # --------------------- READ LEGENDS ---------------------

        # Read geological legend tables.
        if os.path.isfile((in_dir_name + "/geol_legend_table.csv")) or os.path.isfile(
            (in_dir_name + "/geol_legend_table.json")
        ):
            if os.path.isfile((in_dir_name + "/geol_legend_table.json")):
                new_geol_coll_legend_df = pd_read_json(
                    in_dir_name + "/geol_legend_table.json",
                    orient="index",
                    dtype=Legend.legend_dict_types,
                )
                # in the branch called "Riccardo", a control to set opacity to 100 in
                # case it was null was added here, but it is most problably useless
            else:
                new_geol_coll_legend_df = pd_read_csv(
                    in_dir_name + "/geol_legend_table.csv",
                    encoding="utf-8",
                    dtype=Legend.legend_dict_types,
                    keep_default_na=False,
                )
            if not new_geol_coll_legend_df.empty:
                self.geol_coll.legend_df = new_geol_coll_legend_df

            in_keys = set(self.geol_coll.legend_df.keys())
            def_keys = set(Legend.geol_legend_dict.keys())

            diffs = def_keys.difference(in_keys)

            for diff in diffs:
                self.geol_coll.legend_df[diff] = Legend.geol_legend_dict[diff]
            self.geol_coll.legend_df.sort_values(
                by="time", ascending=True, inplace=True
            )

        # Read well legend tables.
        if os.path.isfile((in_dir_name + "/well_legend_table.csv")) or os.path.isfile(
            (in_dir_name + "/well_legend_table.json")
        ):
            if os.path.isfile((in_dir_name + "/well_legend_table.json")):
                new_well_legend_df = pd_read_json(
                    in_dir_name + "/well_legend_table.json",
                    orient="index",
                    dtype=Legend.legend_dict_types,
                )
            else:
                new_well_legend_df = pd_read_csv(
                    in_dir_name + "/well_legend_table.csv",
                    encoding="utf-8",
                    dtype=Legend.legend_dict_types,
                    keep_default_na=False,
                )
            if not new_well_legend_df.empty:
                self.well_legend_df = new_well_legend_df
            in_keys = set(self.well_legend_df.keys())
            def_keys = set(Legend.well_legend_dict.keys())

            diffs = def_keys.difference(in_keys)

            for diff in diffs:
                self.well_legend_df[diff] = Legend.well_legend_dict[diff]
            self.well_legend_df.sort_values(by="Loc ID", ascending=True, inplace=True)

        # Read fluids legend tables.
        if os.path.isfile((in_dir_name + "/fluids_legend_table.csv")) or os.path.isfile(
            (in_dir_name + "/fluids_legend_table.json")
        ):
            if os.path.isfile((in_dir_name + "/fluids_legend_table.json")):
                new_fluids_legend_df = pd_read_json(
                    in_dir_name + "/fluids_legend_table.json",
                    orient="index",
                    dtype=Legend.legend_dict_types,
                )
            else:
                new_fluids_legend_df = pd_read_csv(
                    in_dir_name + "/fluids_legend_table.csv",
                    encoding="utf-8",
                    dtype=Legend.legend_dict_types,
                    keep_default_na=False,
                )
            if not new_fluids_legend_df.empty:
                self.fluids_coll.legend_df = new_fluids_legend_df
            in_keys = set(self.fluids_coll.legend_df.keys())
            def_keys = set(Legend.fluids_legend_dict.keys())

            diffs = def_keys.difference(in_keys)

            for diff in diffs:
                self.fluids_coll.legend_df[diff] = Legend.fluids_legend_dict[diff]
            self.fluids_coll.legend_df.sort_values(
                by="time", ascending=True, inplace=True
            )

        # Read Backgrounds legend tables.
        if os.path.isfile(
            (in_dir_name + "/backgrounds_legend_table.csv")
        ) or os.path.isfile((in_dir_name + "/backgrounds_legend_table.json")):
            if os.path.isfile((in_dir_name + "/backgrounds_legend_table.json")):
                new_backgrounds_legend_df = pd_read_json(
                    in_dir_name + "/backgrounds_legend_table.json",
                    orient="index",
                    dtype=Legend.legend_dict_types,
                )
            else:
                new_backgrounds_legend_df = pd_read_csv(
                    in_dir_name + "/backgrounds_legend_table.csv",
                    encoding="utf-8",
                    dtype=Legend.legend_dict_types,
                    keep_default_na=False,
                )
            if not new_backgrounds_legend_df.empty:
                self.backgrounds_coll.legend_df = new_backgrounds_legend_df
            in_keys = set(self.backgrounds_coll.legend_df.keys())
            def_keys = set(Legend.backgrounds_legend_dict.keys())

            diffs = def_keys.difference(in_keys)

            for diff in diffs:
                self.backgrounds_coll.legend_df[diff] = Legend.backgrounds_legend_dict[diff]

        # Read other legend tables.
        if os.path.isfile((in_dir_name + "/others_legend_table.csv")) or os.path.isfile(
            (in_dir_name + "/others_legend_table.json")
        ):
            if os.path.isfile((in_dir_name + "/others_legend_table.json")):
                new_others_legend_df = pd_read_json(
                    in_dir_name + "/others_legend_table.json",
                    orient="index",
                    dtype=Legend.legend_dict_types,
                )
            else:
                new_others_legend_df = pd_read_csv(
                    in_dir_name + "/others_legend_table.csv",
                    encoding="utf-8",
                    dtype=Legend.legend_dict_types,
                    keep_default_na=False,
                )
            in_keys = set(self.others_legend_df.keys())
            def_keys = set(Legend.others_legend_dict.keys())

            diffs = def_keys.difference(in_keys)

            for diff in diffs:
                self.others_legend_df[diff] = Legend.others_legend_dict[diff]

        if os.path.isfile((in_dir_name + "/prop_legend_df.csv")) or os.path.isfile(
            (in_dir_name + "/prop_legend_df.json")
        ):
            if os.path.isfile((in_dir_name + "/prop_legend_df.json")):
                new_prop_legend_df = pd_read_json(
                    in_dir_name + "/prop_legend_df.json",
                    orient="index",
                    dtype=PropertiesCMaps.prop_cmap_dict_types,
                )
                if not new_prop_legend_df.empty:
                    self.prop_legend_df = new_prop_legend_df
            else:
                self.prop_legend.update_widget(parent=self)

        # Update all legends.
        self.legend.update_widget(parent=self)

        # --------------------- READ TABLES ---------------------

        # Read x_section table and build cross-sections. Note beginResetModel() and endResetModel().
        if os.path.isfile((in_dir_name + "/xsection_table.csv")) or os.path.isfile(
            (in_dir_name + "/xsection_table.json")
        ):
            self.xsect_coll.table_model.beginResetModel()
            if os.path.isfile((in_dir_name + "/xsection_table.json")):
                new_xsect_coll_df = pd_read_json(
                    in_dir_name + "/xsection_table.json",
                    orient="index",
                    dtype=XSectionCollection.entity_dict_types,
                )
            else:
                new_xsect_coll_df = pd_read_csv(
                    in_dir_name + "/xsection_table.csv",
                    encoding="utf-8",
                    dtype=XSectionCollection.entity_dict_types,
                    keep_default_na=False,
                )
            if not new_xsect_coll_df.empty:
                if not "scenario" in new_xsect_coll_df:
                    new_xsect_coll_df.insert(2, "scenario", "undef")
                if not "dip" in new_xsect_coll_df:
                    new_xsect_coll_df.insert(13, "dip", 90.0)
                if not "width" in new_xsect_coll_df:
                    new_xsect_coll_df.insert(15, "width", new_xsect_coll_df.top - new_xsect_coll_df.bottom)
                self.xsect_coll.df = new_xsect_coll_df
            for uid in self.xsect_coll.df["uid"].tolist():
                self.xsect_coll.set_geometry(uid=uid)
            self.xsect_coll.table_model.endResetModel()

        # Read DOM table and files. Note beginResetModel() and endResetModel().
        if os.path.isfile((in_dir_name + "/dom_table.csv")) or os.path.isfile(
            (in_dir_name + "/dom_table.json")
        ):
            self.dom_coll.table_model.beginResetModel()
            if os.path.isfile((in_dir_name + "/dom_table.json")):
                new_dom_coll_df = pd_read_json(
                    in_dir_name + "/dom_table.json",
                    orient="index",
                    dtype=DomCollection.entity_dict_types,
                )
            else:
                new_dom_coll_df = pd_read_csv(
                    in_dir_name + "/dom_table.csv",
                    encoding="utf-8",
                    dtype=DomCollection.entity_dict_types,
                    keep_default_na=False,
                )
            if not new_dom_coll_df.empty:
                if not "scenario" in new_dom_coll_df:
                    new_dom_coll_df.insert(3, "scenario", "undef")
                self.dom_coll.df = new_dom_coll_df
            if 'topology' in self.dom_coll.df.columns:
                self.dom_coll.df.rename(columns={'topology': 'topology'}, inplace=True)
            prgs_bar = progress_dialog(
                max_value=self.dom_coll.df.shape[0],
                title_txt="Open DOM",
                label_txt="Opening DOM objects...",
                cancel_txt=None,
                parent=self,
            )
            for uid in self.dom_coll.df["uid"].to_list():
                if self.dom_coll.get_uid_topology(uid) == "DEM":
                    if not os.path.isfile((in_dir_name + "/" + uid + ".vts")):
                        print("error: missing VTK file")
                        return
                    vtk_object = DEM()
                    sg_reader = vtkXMLStructuredGridReader()
                    sg_reader.SetFileName(in_dir_name + "/" + uid + ".vts")
                    sg_reader.Update()
                    vtk_object.ShallowCopy(sg_reader.GetOutput())
                    vtk_object.Modified()
                elif self.dom_coll.get_uid_topology(uid) == "DomXs":
                    xsect_uid = self.dom_coll.get_uid_x_section(uid)
                    vtk_object = XsPolyLine(x_section_uid=xsect_uid, parent=self)
                    pl_reader = vtkXMLPolyDataReader()
                    pl_reader.SetFileName(in_dir_name + "/" + uid + ".vtp")
                    pl_reader.Update()
                    vtk_object.ShallowCopy(pl_reader.GetOutput())
                    vtk_object.Modified()
                elif (
                    self.dom_coll.df.loc[
                        self.dom_coll.df["uid"] == uid, "topology"
                    ].values[0]
                    == "TSDom"
                ):
                    """Add code to read TSDOM here__________"""
                    vtk_object = TSDom()
                elif (
                    self.dom_coll.df.loc[
                        self.dom_coll.df["uid"] == uid, "topology"
                    ].values[0]
                    == "PCDom"
                ):
                    """Open saved PCDoms data"""
                    vtk_object = PCDom()
                    pd_reader = vtkXMLPolyDataReader()
                    pd_reader.SetFileName(in_dir_name + "/" + uid + ".vtp")
                    pd_reader.Update()
                    vtk_object.ShallowCopy(pd_reader.GetOutput())
                    vtk_object.Modified()
                self.dom_coll.set_uid_vtk_obj(uid=uid, vtk_obj=vtk_object)
                prgs_bar.add_one()
            self.dom_coll.table_model.endResetModel()

        # Read image collection and files.
        if os.path.isfile((in_dir_name + "/image_table.csv")) or os.path.isfile(
            (in_dir_name + "/image_table.json")
        ):
            self.image_coll.table_model.beginResetModel()
            if os.path.isfile((in_dir_name + "/image_table.json")):
                new_image_coll_df = pd_read_json(
                    in_dir_name + "/image_table.json",
                    orient="index",
                    dtype=ImageCollection.entity_dict_types,
                )
            else:
                new_image_coll_df = pd_read_csv(
                    in_dir_name + "/image_table.csv",
                    encoding="utf-8",
                    dtype=ImageCollection.entity_dict_types,
                    keep_default_na=False,
                )
            if not new_image_coll_df.empty:
                if not "scenario" in new_image_coll_df:
                    new_image_coll_df.insert(3, "scenario", "undef")
                self.image_coll.df = new_image_coll_df
            prgs_bar = progress_dialog(
                max_value=self.image_coll.df.shape[0],
                title_txt="Open image",
                label_txt="Opening image objects...",
                cancel_txt=None,
                parent=self,
            )
            for uid in self.image_coll.df["uid"].to_list():
                if self.image_coll.df.loc[
                    self.image_coll.df["uid"] == uid, "topology"
                ].values[0] in ["MapImage", "TSDomImage"]:
                    if not os.path.isfile((in_dir_name + "/" + uid + ".vti")):
                        print("error: missing image file")
                        return
                    vtk_object = MapImage()
                    im_reader = vtkXMLImageDataReader()
                    im_reader.SetFileName(in_dir_name + "/" + uid + ".vti")
                    im_reader.Update()
                    vtk_object.ShallowCopy(im_reader.GetOutput())
                    vtk_object.Modified()
                elif self.image_coll.df.loc[
                    self.image_coll.df["uid"] == uid, "topology"
                ].values[0] in ["XsImage"]:
                    if not os.path.isfile((in_dir_name + "/" + uid + ".vti")):
                        print("error: missing image file")
                        return
                    vtk_object = XsImage(
                        parent=self,
                        x_section_uid=self.image_coll.df.loc[
                            self.image_coll.df["uid"] == uid, "x_section"
                        ].values[0],
                    )
                    im_reader = vtkXMLImageDataReader()
                    im_reader.SetFileName(in_dir_name + "/" + uid + ".vti")
                    im_reader.Update()
                    vtk_object.ShallowCopy(im_reader.GetOutput())
                    vtk_object.Modified()
                elif self.image_coll.df.loc[
                    self.image_coll.df["uid"] == uid, "topology"
                ].values[0] in ["Seismics"]:
                    if not os.path.isfile((in_dir_name + "/" + uid + ".vts")):
                        print("error: missing VTK file")
                        return
                    vtk_object = Seismics()
                    sg_reader = vtkXMLStructuredGridReader()
                    sg_reader.SetFileName(in_dir_name + "/" + uid + ".vts")
                    sg_reader.Update()
                    vtk_object.ShallowCopy(sg_reader.GetOutput())
                    vtk_object.Modified()
                self.image_coll.set_uid_vtk_obj(uid=uid, vtk_obj=vtk_object)
                prgs_bar.add_one()
            self.image_coll.table_model.endResetModel()

        # Read mesh3d collection and files.
        if os.path.isfile((in_dir_name + "/mesh3d_table.csv")) or os.path.isfile(
            (in_dir_name + "/mesh3d_table.json")
        ):
            self.mesh3d_coll.table_model.beginResetModel()
            if os.path.isfile((in_dir_name + "/mesh3d_table.json")):
                new_mesh3d_coll_df = pd_read_json(
                    in_dir_name + "/mesh3d_table.json",
                    orient="index",
                    dtype=Mesh3DCollection.entity_dict_types,
                )
            else:
                new_mesh3d_coll_df = pd_read_csv(
                    in_dir_name + "/mesh3d_table.csv",
                    encoding="utf-8",
                    dtype=Mesh3DCollection.entity_dict_types,
                    keep_default_na=False,
                )
            if not new_mesh3d_coll_df.empty:
                if not "scenario" in new_mesh3d_coll_df:
                    new_mesh3d_coll_df.insert(3, "scenario", "undef")
                self.mesh3d_coll.df = new_mesh3d_coll_df
            prgs_bar = progress_dialog(
                max_value=self.mesh3d_coll.df.shape[0],
                title_txt="Open 3D mesh",
                label_txt="Opening 3D mesh objects...",
                cancel_txt=None,
                parent=self,
            )
            for uid in self.mesh3d_coll.df["uid"].to_list():
                if self.mesh3d_coll.df.loc[
                    self.mesh3d_coll.df["uid"] == uid, "topology"
                ].values[0] in ["Voxet"]:
                    if not os.path.isfile((in_dir_name + "/" + uid + ".vti")):
                        print("error: missing .mesh3d file")
                        return
                    vtk_object = Voxet()
                    im_reader = vtkXMLImageDataReader()
                    im_reader.SetFileName(in_dir_name + "/" + uid + ".vti")
                    im_reader.Update()
                    vtk_object.ShallowCopy(im_reader.GetOutput())
                    vtk_object.Modified()
                elif self.mesh3d_coll.df.loc[
                    self.mesh3d_coll.df["uid"] == uid, "topology"
                ].values[0] in ["XsVoxet"]:
                    if not os.path.isfile((in_dir_name + "/" + uid + ".vti")):
                        print("error: missing .mesh3d file")
                        return
                    vtk_object = XsVoxet(
                        x_section_uid=self.mesh3d_coll.df.loc[
                            self.mesh3d_coll.df["uid"] == uid, "x_section"
                        ].values[0],
                        parent=self,
                    )
                    im_reader = vtkXMLImageDataReader()
                    im_reader.SetFileName(in_dir_name + "/" + uid + ".vti")
                    im_reader.Update()
                    vtk_object.ShallowCopy(im_reader.GetOutput())
                    vtk_object.Modified()
                self.mesh3d_coll.set_uid_vtk_obj(uid=uid, vtk_obj=vtk_object)
                prgs_bar.add_one()
            self.mesh3d_coll.table_model.endResetModel()

        # Read boundaries collection and files.
        if os.path.isfile((in_dir_name + "/boundary_table.csv")) or os.path.isfile(
            (in_dir_name + "/boundary_table.json")
        ):
            self.boundary_coll.table_model.beginResetModel()
            if os.path.isfile((in_dir_name + "/boundary_table.json")):
                new_boundary_coll_df = pd_read_json(
                    in_dir_name + "/boundary_table.json",
                    orient="index",
                    dtype=BoundaryCollection.entity_dict_types,
                )
            else:
                new_boundary_coll_df = pd_read_csv(
                    in_dir_name + "/boundary_table.csv",
                    encoding="utf-8",
                    dtype=BoundaryCollection.entity_dict_types,
                    keep_default_na=False,
                )
            if not new_boundary_coll_df.empty:
                if not "scenario" in new_boundary_coll_df:
                    new_boundary_coll_df.insert(3, "scenario", "undef")
                self.boundary_coll.df = new_boundary_coll_df
            prgs_bar = progress_dialog(
                max_value=self.boundary_coll.df.shape[0],
                title_txt="Open boundary",
                label_txt="Opening boundary objects...",
                cancel_txt=None,
                parent=self,
            )
            for uid in self.boundary_coll.df["uid"].to_list():
                if not os.path.isfile((in_dir_name + "/" + uid + ".vtp")):
                    print("error: missing VTK file")
                    return
                if self.boundary_coll.get_uid_topology(uid) == "PolyLine":
                    vtk_object = PolyLine()
                elif self.boundary_coll.get_uid_topology(uid) == "TriSurf":
                    vtk_object = TriSurf()
                pd_reader = vtkXMLPolyDataReader()
                pd_reader.SetFileName(in_dir_name + "/" + uid + ".vtp")
                pd_reader.Update()
                vtk_object.ShallowCopy(pd_reader.GetOutput())
                vtk_object.Modified()
                self.boundary_coll.set_uid_vtk_obj(uid=uid, vtk_obj=vtk_object)
                prgs_bar.add_one()
            self.boundary_coll.table_model.endResetModel()

        # Read well table and files.
        if os.path.isfile((in_dir_name + "/well_table.csv")) or os.path.isfile(
            (in_dir_name + "/well_table.json")
        ):
            self.well_coll.table_model.beginResetModel()
            if os.path.isfile((in_dir_name + "/well_table.json")):
                new_well_coll_df = pd_read_json(
                    in_dir_name + "/well_table.json",
                    orient="index",
                    dtype=WellCollection.entity_dict_types,
                )
            else:
                new_well_coll_df = pd_read_csv(
                    in_dir_name + "/well_table.csv",
                    encoding="utf-8",
                    dtype=WellCollection.entity_dict_types,
                    keep_default_na=False,
                )
            if not new_well_coll_df.empty:
                if not "scenario" in new_well_coll_df:
                    new_well_coll_df.insert(2, "scenario", "undef")
                self.well_coll.df = new_well_coll_df
            prgs_bar = progress_dialog(
                max_value=self.well_coll.df.shape[0],
                title_txt="Open wells",
                label_txt="Opening well objects...",
                cancel_txt=None,
                parent=self,
            )
            for uid in self.well_coll.df["uid"].to_list():
                if not os.path.isfile((in_dir_name + "/" + uid + ".vtp")):
                    print("error: missing VTK file")
                    return
                vtk_object = Well()
                pd_reader = vtkXMLPolyDataReader()
                pd_reader.SetFileName(in_dir_name + "/" + uid + ".vtp")
                pd_reader.Update()
                vtk_object.trace = pd_reader.GetOutput()

                self.well_coll.set_uid_vtk_obj(uid=uid, vtk_obj=vtk_object.trace)
                # Don't know if I like it.
                # Maybe it's better to always add to the vtkobject column the
                # Well and not the WellTrace instance and then call well.trace/head where needed
                prgs_bar.add_one()
            self.well_coll.table_model.endResetModel()
        self.prop_legend.update_widget(parent=self)

        # Read geological table and files.
        if os.path.isfile((in_dir_name + "/geological_table.csv")) or os.path.isfile(
            (in_dir_name + "/geological_table.json")
        ):
            self.geol_coll.table_model.beginResetModel()
            if os.path.isfile((in_dir_name + "/geological_table.json")):
                # noinspection PyTypeChecker
                new_geol_coll_df = pd_read_json(
                    in_dir_name + "/geological_table.json",
                    orient="index",
                    dtype=GeologicalCollection.entity_dict_types,
                )
            else:
                new_geol_coll_df = pd_read_csv(
                    in_dir_name + "/geological_table.csv",
                    encoding="utf-8",
                    dtype=GeologicalCollection.entity_dict_types,
                    keep_default_na=False,
                )
            if not new_geol_coll_df.empty:
                self.geol_coll.df = new_geol_coll_df

            prgs_bar = progress_dialog(
                max_value=self.geol_coll.df.shape[0],
                title_txt="Open geology",
                label_txt="Opening geological objects...",
                cancel_txt=None,
                parent=self,
            )
            for uid in self.geol_coll.df["uid"].to_list():
                if not os.path.isfile((in_dir_name + "/" + uid + ".vtp")):
                    print("error: missing VTK file")
                    return
                if self.geol_coll.get_uid_topology(uid) == "VertexSet":
                    if "dip" in self.geol_coll.get_uid_properties_names(uid):
                        vtk_object = Attitude()
                    else:
                        vtk_object = VertexSet()
                elif self.geol_coll.get_uid_topology(uid) == "PolyLine":
                    vtk_object = PolyLine()
                elif self.geol_coll.get_uid_topology(uid) == "TriSurf":
                    vtk_object = TriSurf()
                elif self.geol_coll.get_uid_topology(uid) == "XsVertexSet":
                    vtk_object = XsVertexSet(
                        self.geol_coll.get_uid_x_section(uid), parent=self
                    )
                elif self.geol_coll.get_uid_topology(uid) == "XsPolyLine":
                    vtk_object = XsPolyLine(
                        self.geol_coll.get_uid_x_section(uid), parent=self
                    )
                pd_reader = vtkXMLPolyDataReader()
                pd_reader.SetFileName(in_dir_name + "/" + uid + ".vtp")
                pd_reader.Update()
                vtk_object.ShallowCopy(pd_reader.GetOutput())
                vtk_object.Modified()
                self.geol_coll.set_uid_vtk_obj(uid=uid, vtk_obj=vtk_object)
                prgs_bar.add_one()
            self.geol_coll.table_model.endResetModel()
        # Update legend.
        self.prop_legend.update_widget(parent=self)

        # Read fluids table and files.
        if os.path.isfile((in_dir_name + "/fluids_table.csv")) or os.path.isfile(
            (in_dir_name + "/fluids_table.json")
        ):
            self.fluids_coll.table_model.beginResetModel()
            if os.path.isfile((in_dir_name + "/fluids_table.json")):
                new_fluids_coll_df = pd_read_json(
                    in_dir_name + "/fluids_table.json",
                    orient="index",
                    dtype=FluidsCollection.entity_dict_types,
                )
            else:
                new_fluids_coll_df = pd_read_csv(
                    in_dir_name + "/fluids_table.csv",
                    encoding="utf-8",
                    dtype=FluidsCollection.entity_dict_types,
                    keep_default_na=False,
                )
            if not new_fluids_coll_df.empty:
                self.fluids_coll.df = new_fluids_coll_df
            prgs_bar = progress_dialog(
                max_value=self.fluids_coll.df.shape[0],
                title_txt="Open fluids",
                label_txt="Opening fluid objects...",
                cancel_txt=None,
                parent=self,
            )
            for uid in self.fluids_coll.df["uid"].to_list():
                if not os.path.isfile((in_dir_name + "/" + uid + ".vtp")):
                    print("error: missing VTK file")
                    return
                if self.fluids_coll.get_uid_topology(uid) == "VertexSet":
                    vtk_object = VertexSet()
                elif self.fluids_coll.get_uid_topology(uid) == "PolyLine":
                    vtk_object = PolyLine()
                elif self.fluids_coll.get_uid_topology(uid) == "TriSurf":
                    vtk_object = TriSurf()
                elif self.fluids_coll.get_uid_topology(uid) == "XsVertexSet":
                    vtk_object = XsVertexSet(
                        self.fluids_coll.get_uid_x_section(uid), parent=self
                    )
                elif self.fluids_coll.get_uid_topology(uid) == "XsPolyLine":
                    vtk_object = XsPolyLine(
                        self.fluids_coll.get_uid_x_section(uid), parent=self
                    )
                pd_reader = vtkXMLPolyDataReader()
                pd_reader.SetFileName(in_dir_name + "/" + uid + ".vtp")
                pd_reader.Update()
                vtk_object.ShallowCopy(pd_reader.GetOutput())
                vtk_object.Modified()
                self.fluids_coll.set_uid_vtk_obj(uid=uid, vtk_obj=vtk_object)
                prgs_bar.add_one()
            self.fluids_coll.table_model.endResetModel()
        # Update legend.
        self.prop_legend.update_widget(parent=self)

        # Read Backgrounds table and files."""
        if os.path.isfile((in_dir_name + "/backgrounds_table.csv")) or os.path.isfile(
            (in_dir_name + "/backgrounds_table.json")
        ):
            self.backgrounds_coll.table_model.beginResetModel()
            if os.path.isfile((in_dir_name + "/backgrounds_table.json")):
                new_backgrounds_coll_df = pd_read_json(
                    in_dir_name + "/backgrounds_table.json",
                    orient="index",
                    dtype=FluidsCollection.entity_dict_types,
                )
            else:
                new_backgrounds_coll_df = pd_read_csv(
                    in_dir_name + "/backgrounds_table.csv",
                    encoding="utf-8",
                    dtype=FluidsCollection.entity_dict_types,
                    keep_default_na=False,
                )
            if not new_backgrounds_coll_df.empty:
                if not "scenario" in new_backgrounds_coll_df:
                    new_backgrounds_coll_df.insert(5, "scenario", "undef")
                self.backgrounds_coll.df = new_backgrounds_coll_df
            prgs_bar = progress_dialog(
                max_value=self.backgrounds_coll.df.shape[0],
                title_txt="Open fluids",
                label_txt="Opening fluid objects...",
                cancel_txt=None,
                parent=self,
            )
            for uid in self.backgrounds_coll.df["uid"].to_list():
                if not os.path.isfile((in_dir_name + "/" + uid + ".vtp")):
                    print("error: missing VTK file")
                    return
                if self.backgrounds_coll.get_uid_topology(uid) == "VertexSet":
                    vtk_object = VertexSet()
                elif self.backgrounds_coll.get_uid_topology(uid) == "PolyLine":
                    vtk_object = PolyLine()
                # elif self.backgrounds_coll.get_uid_topology(uid) == 'TriSurf':
                #     vtk_object = TriSurf()
                # elif self.backgrounds_coll.get_uid_topology(uid) == 'XsVertexSet':
                #     vtk_object = XsVertexSet(self.backgrounds_coll.get_uid_x_section(uid), parent=self)
                # elif self.backgrounds_coll.get_uid_topology(uid) == 'XsPolyLine':
                #     vtk_object = XsPolyLine(self.backgrounds_coll.get_uid_x_section(uid), parent=self)
                pd_reader = vtkXMLPolyDataReader()
                pd_reader.SetFileName(in_dir_name + "/" + uid + ".vtp")
                pd_reader.Update()
                vtk_object.ShallowCopy(pd_reader.GetOutput())
                vtk_object.Modified()
                self.backgrounds_coll.set_uid_vtk_obj(uid=uid, vtk_obj=vtk_object)
                prgs_bar.add_one()
            self.backgrounds_coll.table_model.endResetModel()
        # Update legend.
        self.prop_legend.update_widget(parent=self)

    # ---- Methods used to import entities from other file formats. ----

    def import_gocad(self):
        """Import Gocad ASCII file and update geological collection."""
        self.TextTerminal.appendPlainText("Importing Gocad ASCII format")
        self.TextTerminal.appendPlainText(
            "Properties are discarded if they are not 1D, 2D, 3D, 4D, 6D or 9D (due to VTK limitations)"
        )
        """Select and open input file"""
        in_file_name = open_file_dialog(
            parent=self,
            caption="Import entities from Gocad ASCII file",
            filter="Gocad ASCII (*.*)",
        )
        if in_file_name:
            self.TextTerminal.appendPlainText("in_file_name: " + in_file_name)
            gocad2vtk(self=self, in_file_name=in_file_name, uid_from_name=False)
            self.prop_legend.update_widget(parent=self)

    def import_gocad_sections(self):
        """Import cross-section saved as Gocad ASCII file and update geological collection."""
        self.TextTerminal.appendPlainText("Importing Gocad ASCII format")
        self.TextTerminal.appendPlainText(
            "Properties are discarded if they are not 1D, 2D, 3D, 4D, 6D or 9D (due to VTK limitations)"
        )
        # Select input files.
        in_file_names = open_files_dialog(
            parent=self,
            caption="Import entities from Gocad ASCII files",
            filter="Gocad ASCII (*.*)",
        )
        if not in_file_names:
            return
        # Define import options.
        scenario_default = input_text_dialog(
            parent=None, title="Scenario", label="Default scenario", default_text="undef"
        )
        if not scenario_default:
            scenario_default = "undef"
        role_default = input_combo_dialog(
            parent=None,
            title="Role",
            label="Default role",
            choice_list=self.geol_coll.valid_roles,
        )
        if not role_default:
            role_default = "undef"
        feature_from_name = options_dialog(
            title="Feature from name",
            message="Get geological feature from object name if not defined in file",
            yes_role="Yes",
            no_role="No",
            reject_role=None,
        )
        if feature_from_name == 0:
            feature_from_name = True
        else:
            feature_from_name = False
        append_opt = options_dialog(
            title="Append option",
            message=f"Append entities to XSections?\nSection will NOT be re-oriented.",
            yes_role="Cancel",
            no_role="OK",
            reject_role=None)
        # Process files.
        for in_file_name in in_file_names:
            self.TextTerminal.appendPlainText("in_file_name: " + in_file_name)
            # Get x-section name from file.
            x_section_name = os.path.splitext(os.path.basename(in_file_name))[0]
            if x_section_name in self.xsect_coll.df["name"].to_list():
                if append_opt == 0:
                    return
                else:
                    x_section_uid = self.xsect_coll.df.loc[
                        self.xsect_coll.df["name"] == x_section_name, "uid"
                    ].values[0]
            else:
                append_opt = 0
                section_dict = deepcopy(self.xsect_coll.entity_dict)
                section_dict["name"] = x_section_name
                x_section_uid = self.xsect_coll.add_entity_from_dict(entity_dict=section_dict)
            gocad2vtk_section(
                self=self,
                in_file_name=in_file_name,
                uid_from_name=False,
                x_section_uid=x_section_uid,
                scenario_default=scenario_default,
                role_default=role_default,
                feature_from_name=feature_from_name,
                append_opt=append_opt,
            )
            self.prop_legend.update_widget(parent=self)

    def import_gocad_boundary(self):
        """Import Gocad ASCII file and update boundary collection."""
        self.TextTerminal.appendPlainText("Importing Gocad ASCII format as boundary")
        self.TextTerminal.appendPlainText(
            "Properties are discarded - only mesh imported."
        )
        """Select and open input file"""
        in_file_name = open_file_dialog(
            parent=self,
            caption="Import entities from Gocad ASCII file",
            filter="Gocad ASCII (*.*)",
        )
        if in_file_name:
            self.TextTerminal.appendPlainText("in_file_name: " + in_file_name)
            gocad2vtk_boundary(
                self=self,
                in_file_name=in_file_name,
                uid_from_name=False,
            )

    def import_sections(self):
        """Import section traces from different kinds of files."""
        sections_from_file(self)

    def import_PC(self):
        """Import point cloud data. File extension dependent (.txt, .xyz, .las) -> Ui_ImportOptionsWindow ui to preview the data (similar to stereonet)"""

        default_attr_list = [
            "As is",
            "X",
            "Y",
            "Z",
            "Red",
            "Green",
            "Blue",
            "Intensity",
            "Nx",
            "Ny",
            "Nz",
            "User defined",
            "N.a.",
        ]

        ext_filter = "All supported (*.txt *.csv *.xyz *.asc *.ply *.las *.laz);;Text files (*.txt *.csv *.xyz *.asc);;PLY files (*.ply);;LAS/LAZ files (*.las *.laz)"

        add_opt = [["check255Box", "Display RGB values within the 0-255 range"]]

        args = import_dialog(
            self,
            default_attr_list=default_attr_list,
            ext_filter=ext_filter,
            caption="Import point cloud data",
            add_opt=add_opt,
        ).args
        if args:
            in_file_name, col_names, row_range, index_list, delimiter, origin = args
            self.TextTerminal.appendPlainText("in_file_name: " + in_file_name)
            pc2vtk(
                in_file_name=in_file_name,
                col_names=col_names,
                row_range=row_range,
                usecols=index_list,
                delimiter=delimiter,
                self=origin,
                header_row=0,
            )

    def import_SHP(self):
        # __________________________________________________________________ UPDATE IN shp2vtk.py OR DUPLICATE THIS TO IMPORT SHP GEOLOGY OR BOUNDARY
        """Import SHP file and update geological collection."""
        self.TextTerminal.appendPlainText("Importing SHP file")
        list = ["Geology", "Fluid contacts", "Background data"]
        """Select and open input file"""
        in_file_name = open_file_dialog(
            parent=self, caption="Import SHP file", filter="shp (*.shp)"
        )
        coll = input_combo_dialog(
            parent=self, title="Collection", label="Assign collection", choice_list=list
        )
        if in_file_name:
            self.TextTerminal.appendPlainText("in_file_name: " + in_file_name)
            shp2vtk(self=self, in_file_name=in_file_name, collection=coll)

    def import_DEM(self):
        """Import DEM file and update DEM collection."""
        self.TextTerminal.appendPlainText("Importing DEM in supported format (geotiff)")
        list = ["DEMs and DOMs", "Fluid contacts"]

        """Select and open input file"""
        in_file_name = open_file_dialog(
            parent=self, caption="Import DEM from file", filter="Geotiff (*.tif)"
        )
        coll = input_combo_dialog(
            parent=self, title="Collection", label="Assign collection", choice_list=list
        )
        if in_file_name:
            self.TextTerminal.appendPlainText("in_file_name: " + in_file_name)
            dem2vtk(self=self, in_file_name=in_file_name, collection="DEMs and DOMs")

    def import_mapimage(self):
        """Import map image and update image collection."""
        self.TextTerminal.appendPlainText(
            "Importing image from supported format (GDAL)"
        )
        """Select and open input file"""
        in_file_name = open_file_dialog(
            parent=self,
            caption="Import image from file",
            filter="Image (*.tif *.jpg *.png *.bmp)",
        )
        if in_file_name:
            self.TextTerminal.appendPlainText("in_file_name: " + in_file_name)
            geo_image2vtk(self=self, in_file_name=in_file_name)

    def import_xsimage(self):
        """Import XSimage and update image collection."""
        self.TextTerminal.appendPlainText(
            "Importing image from supported format (GDAL)"
        )
        """Select and open input file"""
        in_file_name = open_file_dialog(
            parent=self,
            caption="Import image from file",
            filter="Image (*.tif *.jpg *.png *.bmp)",
        )
        if in_file_name:
            self.TextTerminal.appendPlainText("in_file_name: " + in_file_name)
            """Select the Xsection"""
            if self.xsect_coll.get_uids:
                x_section_name = input_combo_dialog(
                    parent=None,
                    title="Xsection",
                    label="Choose Xsection",
                    choice_list=self.xsect_coll.get_names,
                )
            else:
                message_dialog(title="Xsection", message="No Xsection in project")
                return
            if x_section_name:
                x_section_uid = self.xsect_coll.df.loc[
                    self.xsect_coll.df["name"] == x_section_name, "uid"
                ].values[0]
                xs_image2vtk(
                    self=self, in_file_name=in_file_name, x_section_uid=x_section_uid
                )
                self.prop_legend.update_widget(parent=self)

    def import_welldata(self):
        path = open_file_dialog(
            parent=self, caption="Import well data", filter="XLXS files (*.xlsx)"
        )

        if path:
            well2vtk(self, path=path)
            self.prop_legend.update_widget(parent=self)
        else:
            return

        # loc_attr_list = ['As is','LocationID', 'LocationType', 'Easting', 'Northing', 'GroundLevel', 'FinalDepth', 'Trend', 'Plunge','N.a.']

        # data_attr_list = ['As is','LocationID','DepthTop', 'DepthBase','DepthPoint','GeologyCode','N.a.']

        # ext_filter = "All supported (*.txt *.csv *.xyz *.asc *.las);;Text files (*.txt *.csv *.xyz *.asc);;LAS files (*.las)"

        # locargs = import_dialog(parent=self,default_attr_list=loc_attr_list,ext_filter=ext_filter,caption='Import well location data').args

        # dataargs = import_dialog(parent=self,default_attr_list=data_attr_list,ext_filter=ext_filter,caption='Import well data',multiple=True).args

        # if locargs and dataargs:
        #     in_file_name = [locargs[0],dataargs[0]]
        #     col_names = [locargs[1],dataargs[1]]
        #     index_list = [locargs[3],dataargs[3]]
        #     delimiter = [locargs[4],dataargs[4]]
        #     origin = [locargs[5],dataargs[5]]
        #     # self.TextTerminal.appendPlainText('in_file_name: ' + in_file_name)
        #     well2vtk(in_file_name=in_file_name, col_names=col_names, usecols=index_list, delimiter=delimiter, self=self, header_row=0)

    def import_SEGY(self):
        # ___________________________________________________________ TO BE REVIEWED AND UPDATED IN MODULE segy2vtk
        """Import SEGY file and update Mesh3D collection."""
        self.TextTerminal.appendPlainText("Importing SEGY seismics file.")
        """Select and open input file"""
        in_file_name = open_file_dialog(
            parent=self, caption="Import SEGY from file", filter="SEGY (*.sgy *.segy)"
        )
        if in_file_name:
            self.TextTerminal.appendPlainText("in_file_name: " + in_file_name)
            segy2vtk(self=self, in_file_name=in_file_name)

    """Methods used to export entities to other file formats."""

    def export_cad(self):
        # ________________________________________________________________ IMPLEMENT GOCAD EXPORT
        """Base method to choose a CAD format for exporting geological entities."""
        cad_format = input_combo_dialog(
            parent=self,
            title="CAD format",
            label="Choose CAD format",
            choice_list=[
                "DXF",
                "GOCAD",
                "GLTF",
                "CESIUM",
                "OBJ",
                "PLY",
                "STL",
                "STL with 1m dilation",
                "LandXML",
            ],
        )
        out_dir_name = save_file_dialog(
            parent=self, caption="Export geological entities as CAD meshes."
        )
        if not out_dir_name:
            return
        self.TextTerminal.appendPlainText(
            ("Saving CAD surfaces in folder: " + out_dir_name)
        )
        """Create the folder if it does not exist already."""
        if not os.path.isdir(out_dir_name):
            os.mkdir(out_dir_name)
        if cad_format == "DXF":
            print("is DXF")
            os.mkdir(f"{out_dir_name}/csv")
            os.mkdir(f"{out_dir_name}/dxf")
            vtk2dxf(self=self, out_dir_name=out_dir_name)
        elif cad_format == "GOCAD":
            # vtk2gocad(self=self, out_file_name=(out_dir_name + '/gocad_ascii.gp'))
            pass
        elif cad_format == "GLTF":
            vtk2gltf(self=self, out_dir_name=out_dir_name)
        elif cad_format == "CESIUM":
            vtk2cesium(self=self, out_dir_name=out_dir_name)
        elif cad_format == "OBJ":
            vtk2obj(self=self, out_dir_name=out_dir_name)
        elif cad_format == "PLY":
            vtk2ply(self=self, out_dir_name=out_dir_name)
        elif cad_format == "STL":
            vtk2stl(self=self, out_dir_name=out_dir_name)
        elif cad_format == "STL with 1m dilation":
            vtk2stl_dilation(self=self, out_dir_name=out_dir_name, tol=1)
        elif cad_format == "LandXML":
            vtk2lxml(self=self, out_dir_name=out_dir_name)
        else:
            return
        """Save geological legend table to CSV and JSON files."""
        self.geol_coll.legend_df.to_csv(
            out_dir_name + "/geol_legend_table.csv", encoding="utf-8", index=False
        )
        self.geol_coll.legend_df.to_json(
            out_dir_name + "/geol_legend_table.json", orient="index"
        )
        """Save others legend table to CSV and JSON files."""
        self.others_legend_df.to_csv(
            out_dir_name + "/others_legend_table.csv", encoding="utf-8", index=False
        )
        self.others_legend_df.to_json(
            out_dir_name + "/others_legend_table.json", orient="index"
        )
        """Save x_section table to CSV and JSON files."""
        out_cols = list(self.xsect_coll.df.columns)
        out_cols.remove("vtk_plane")
        out_cols.remove("vtk_frame")
        self.xsect_coll.df[out_cols].to_csv(
            out_dir_name + "/xsection_table.csv", encoding="utf-8", index=False
        )
        self.xsect_coll.df[out_cols].to_json(
            out_dir_name + "/xsection_table.json", orient="index"
        )
        """Save geological collection table to CSV and JSON files."""
        out_cols = list(self.geol_coll.df.columns)
        out_cols.remove("vtk_obj")
        self.geol_coll.df[out_cols].to_csv(
            out_dir_name + "/geological_table.csv", encoding="utf-8", index=False
        )
        self.geol_coll.df[out_cols].to_json(
            out_dir_name + "/geological_table.json", orient="index"
        )
        """Save DOM collection table to CSV and JSON files."""
        out_cols = list(self.dom_coll.df.columns)
        out_cols.remove("vtk_obj")
        self.dom_coll.df[out_cols].to_csv(
            out_dir_name + "/dom_table.csv", encoding="utf-8", index=False
        )
        self.dom_coll.df[out_cols].to_json(
            out_dir_name + "/dom_table.json", orient="index"
        )
        """Save image collection table to CSV and JSON files."""
        out_cols = list(self.image_coll.df.columns)
        out_cols.remove("vtk_obj")
        self.image_coll.df[out_cols].to_csv(
            out_dir_name + "/image_table.csv", encoding="utf-8", index=False
        )
        self.image_coll.df[out_cols].to_json(
            out_dir_name + "/image_table.json", orient="index"
        )
        """Save mesh3d collection table to CSV and JSON files."""
        out_cols = list(self.mesh3d_coll.df.columns)
        out_cols.remove("vtk_obj")
        self.mesh3d_coll.df[out_cols].to_csv(
            out_dir_name + "/mesh3d_table.csv", encoding="utf-8", index=False
        )
        self.mesh3d_coll.df[out_cols].to_json(
            out_dir_name + "/mesh3d_table.json", orient="index"
        )
        """Save boundary collection table to CSV and JSON files."""
        out_cols = list(self.boundary_coll.df.columns)
        out_cols.remove("vtk_obj")
        self.boundary_coll.df[out_cols].to_csv(
            out_dir_name + "/boundary_table.csv", encoding="utf-8", index=False
        )
        self.boundary_coll.df[out_cols].to_json(
            out_dir_name + "/boundary_table.json", orient="index"
        )

        """Save well collection table to CSV and JSON files."""
        out_cols = list(self.well_coll.df.columns)
        out_cols.remove("vtk_obj")
        self.well_coll.df[out_cols].to_json(
            out_dir_name + "/well_table.json", orient="index"
        )
        self.well_coll.df[out_cols].to_csv(
            out_dir_name + "/well_table.csv", encoding="utf-8", index=False
        )
        print("All files saved.")

    def export_vtk(self):
        """[Gabriele] Function used to export selected objects as vtk files"""
        if not self.selected_uids:
            return

        else:
            self.out_dir_name = save_file_dialog(
                parent=self, caption="Select save directory.", directory=True
            )
            # print(self.out_file_name)
            for (
                uid
            ) in (
                self.selected_uids
            ):  # [gabriele] this could be generalized with a helper function
                if self.shown_table == "tabGeology":
                    entity = self.geol_coll.get_uid_vtk_obj(uid)

                    pd_writer = vtkXMLPolyDataWriter()
                    pd_writer.SetFileName(f"{self.out_dir_name}/{uid}.vtp")
                    pd_writer.SetInputData(entity)
                    pd_writer.Write()
                    border = entity.get_clean_boundary()
                    pd_writer = vtkXMLPolyDataWriter()
                    pd_writer.SetFileName(f"{self.out_dir_name}/{uid}_border.vtp")
                    pd_writer.SetInputData(border)
                    pd_writer.Write()
                elif self.shown_table == "tabXSections":
                    entity = self.xsect_coll.get_uid_vtk_obj(uid)

                    pd_writer = vtkXMLPolyDataWriter()
                    pd_writer.SetFileName(f"{self.out_dir_name}/{uid}.vtp")
                    pd_writer.SetInputData(entity)
                    pd_writer.Write()
                elif self.shown_table == "tabMeshes3D":
                    entity = self.mesh3d_coll.get_uid_vtk_obj(uid)

                    pd_writer = vtkXMLPolyDataWriter()
                    pd_writer.SetFileName(f"{self.out_dir_name}/{uid}.vtp")
                    pd_writer.SetInputData(entity)
                    pd_writer.Write()
                elif self.shown_table == "tabDOMs":
                    entity = self.dom_coll.get_uid_vtk_obj(uid)
                    temp = vtkPolyData()
                    temp.ShallowCopy(entity)  # I hate this
                    pd_writer = vtkXMLPolyDataWriter()
                    pd_writer.SetFileName(f"{self.out_dir_name}/{uid}.vtp")
                    pd_writer.SetInputData(temp)
                    pd_writer.Write()
                    del temp
                elif self.shown_table == "tabImages":
                    entity = self.image_coll.get_uid_vtk_obj(uid)

                    pd_writer = vtkXMLPolyDataWriter()
                    pd_writer.SetFileName(f"{self.out_dir_name}/{uid}.vtp")
                    pd_writer.SetInputData(entity)
                    pd_writer.Write()
                elif self.shown_table == "tabBoundaries":
                    entity = self.boundary_coll.get_uid_vtk_obj(uid)

                    pd_writer = vtkXMLPolyDataWriter()
                    pd_writer.SetFileName(f"{self.out_dir_name}/{uid}.vtp")
                    pd_writer.SetInputData(entity)
                    pd_writer.Write()
                elif self.shown_table == "tabWells":
                    entity = self.well_coll.get_uid_vtk_obj(uid)

                    pd_writer = vtkXMLPolyDataWriter()
                    pd_writer.SetFileName(f"{self.out_dir_name}/{uid}.vtp")
                    pd_writer.SetInputData(entity)
                    pd_writer.Write()
                print(f"exported {uid}")

    # Everything here is very bad, but I am short on time
    def export_csv(self):
        if not self.selected_uids:
            return

        else:
            self.out_dir_name = save_file_dialog(
                parent=self, caption="Select save directory.", directory=True
            )
            # print(self.out_file_name)
            for (
                uid
            ) in (
                self.selected_uids
            ):  # [gabriele] this could be generalized with a helper function
                if self.shown_table == "tabGeology":
                    entity = self.geol_coll.get_uid_vtk_obj(uid)

                    df = pd_DataFrame()
                    if isinstance(entity, TriSurf):
                        for key in entity.get_field_data_keys():
                            if key == "Normals" or key == "Centers":
                                data = entity.get_field_data(key).reshape(-1, 3)
                            else:
                                data = entity.get_field_data(key)
                            if data.ndim == 1:
                                df[key] = data
                            else:
                                for i in range(data.ndim + 1):
                                    df[f"{key}_{i}"] = data[:, i]

                    else:
                        for key in entity.point_data_keys:
                            data = entity.get_point_data(key)

                            if key == "Normals":
                                df["dip dir"] = entity.points_map_dip_azimuth
                                df["dip"] = entity.points_map_dip
                            if data.ndim == 1:
                                df[key] = data
                            else:
                                for i in range(data.ndim):
                                    df[f"{key}_{i}"] = data[:, i]

                    df.to_csv(f"{self.out_dir_name}/{uid}.csv")
                else:
                    print("Only geology objects are supported")
