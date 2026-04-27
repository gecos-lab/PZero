"""project_window.py
PZero© Andrea Bistacchi"""

from os import path as os_path
from os import mkdir as os_mkdir

from copy import deepcopy

from datetime import datetime

from numpy import cos as np_cos
from numpy import pi as np_pi
from numpy import sin as np_sin

from PySide6.QtCore import Signal as pyqtSignal
from PySide6.QtCore import QObject, QUrl
from PySide6.QtWidgets import (
    QMainWindow,
    QMessageBox,
    QDialog,
    QLabel,
    QVBoxLayout,
    QComboBox,
    QMenu,
    QWidget,
)
from PySide6.QtGui import QAction, QDesktopServices, QPixmap
from PySide6.QtCore import Qt, QTimer

from pandas import DataFrame as pd_DataFrame
from pandas import read_csv as pd_read_csv
from pandas import read_json as pd_read_json
from pandas import concat as pd_concat

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
from pzero.collections.fluid_collection import FluidCollection
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
from pzero.imports.gocad2vtk import (
    gocad2vtk,
    gocad2vtk_section,
    gocad2vtk_boundary,
    vtk2gocad,
)
from pzero.imports.image2vtk import geo_image2vtk, xs_image2vtk
from pzero.imports.lxml2vtk import vtk2lxml
from pzero.imports.obj2vtk import vtk2obj
from pzero.imports.pc2vtk import pc2vtk
from pzero.imports.ply2vtk import vtk2ply
from pzero.imports.pyvista2vtk import pyvista2vtk
from pzero.imports.segy2vtk import segy2vtk, read_segy_file
from pzero.imports.shp2vtk import shp2vtk
from pzero.imports.stl2vtk import vtk2stl, vtk2stl_dilation
from pzero.imports.table2data import import_tables
from pzero.imports.well2vtk import well2vtk
from pzero.imports.xyz2vtk import xyz2vtk
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
from .helpers.helper_functions import freeze_gui_onoff
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
    enhanced_linear_extrusion,
    decimation_pro_resampling,
    decimation_quadric_resampling,
    subdivision_resampling,
    intersection_xs,
    project_2_dem,
    project_2_xs,
    split_surf,
    retopo,
)

from pzero.views.dock_window import DockWindow
from .processing.CRS import CRS_list, CRS_transform_selected
# import json
from json import dump as json_dump
from json import load as json_load


class ProjectSignals(QObject):
    """
    This class is used to store signals used project-wide that will be used according
    to the following pattern:

    -> within project:
    self.signals = ProjectSignals()

    -> within child objects:
    self.project.signals.specific_signal.emit(some_message)
    self.project.signals.specific_signal.connect(some_message)

    Basically in this way we add all signals by composition.
    """

    # project_close is used to delete open windows when the current project is closed (and a new one is opened).
    project_close = pyqtSignal()  # seems OK

    # prop_legend_cmap_modified is uded by the property legend manager when a color map is changed for some
    # property called "str"
    prop_legend_cmap_modified = pyqtSignal(str)  # seems OK

    # The following are signals used by entitied collected in collections.
    # "object" is used to pass a reference to the collection where the entity is stored
    # the other argument is a list of uids, or a single uid, or a list of entities
    entities_added = pyqtSignal(list, object)  # seems OK
    entities_removed = pyqtSignal(list, object)  # seems OK
    geom_modified = pyqtSignal(list, object)  # seems OK
    data_keys_added = pyqtSignal(
        list, object
    )  # seems OK - CAN BE MERGED WITH "removed"?
    data_keys_removed = pyqtSignal(
        list, object
    )  # seems OK - CAN BE MERGED WITH "added"?
    data_val_modified = pyqtSignal(list, object)  # not used at the moment
    metadata_modified = pyqtSignal(list, object)  # seems OK
    legend_color_modified = pyqtSignal(list, object)  # seems OK
    legend_thick_modified = pyqtSignal(list, object)  # seems OK
    legend_point_size_modified = pyqtSignal(list, object)  # seems OK
    legend_opacity_modified = pyqtSignal(list, object)  # seems OK

    # selection_changed is used to update the set of selected entities on each collection = object
    selection_changed = pyqtSignal(object)


class ProjectWindow(QMainWindow, Ui_ProjectWindow):
    """Create project window and import UI created with Qt Designer by subclassing both"""

    # Signals defined here are meant to be broadcast TO ALL views. This is why we use signals
    # instead of functions that will act within a single view only. They all pass a list of uid's.

    """Add other signals above this line ----------------------------------------"""

    def __init__(self, *args, **kwargs):
        super(ProjectWindow, self).__init__(*args, **kwargs)
        """Import GUI from project_window_ui.py"""
        self.setupUi(self)
        self._install_import_table_action()
        self._install_import_xyz_action()
        self.TextTerminal.setReadOnly(True)

        """Connect actionQuit.triggered SIGNAL to self.close SLOT"""
        self.actionQuit.triggered.connect(self.close)

        """Welcome message"""
        self.print_terminal(
            "Welcome to PZero!\n3D modelling application by gecos-lab, © 2020 by Andrea Bistacchi.\n"
        )

        self.signals = ProjectSignals()

        # dictionary with table (key) vs. collection (value)
        self.tab_collection_dict = {
            "tabGeology": "geol_coll",
            "tabXSections": "xsect_coll",
            "tabDOMs": "dom_coll",
            "tabImages": "image_coll",
            "tabMeshes": "mesh3d_coll",
            "tabBoundaries": "boundary_coll",
            "tabWells": "well_coll",
            "tabFluids": "fluid_coll",
            "tabBackgrounds": "backgrnd_coll",
        }

        """Initialize empty project."""
        self.create_empty()

        """File>Project actions -> slots"""
        self.actionProjectNew.triggered.connect(self.new_project)
        self.actionProjectOpen.triggered.connect(self.open_project)
        self.actionProjectSave.triggered.connect(self.save_project)

        """File>Import actions -> slots"""
        self.actionImportGocad.triggered.connect(self.import_gocad)
        self.actionImportGocadXsection.triggered.connect(self.import_gocad_sections)
        self.actionImportBoundary.triggered.connect(self.import_gocad_boundary)
        self.actionImportTable.triggered.connect(self.import_tables)
        self.actionImportXYZ.triggered.connect(self.import_XYZ)
        self.actionImportPyVista.triggered.connect(lambda: pyvista2vtk(self=self))
        self.actionImportPC.triggered.connect(self.import_PC)
        self.actionImportSHP.triggered.connect(self.import_SHP)
        self.actionImportDEM.triggered.connect(self.import_DEM)
        self.actionImportMapImage.triggered.connect(self.import_mapimage)
        self.actionImportXSectionImage.triggered.connect(self.import_xsimage)
        self.actionImportWellData.triggered.connect(self.import_welldata)
        self.actionImportSEGY.triggered.connect(self.import_SEGY)

        """File>Export actions -> slots"""
        self.actionExportCAD.triggered.connect(self.export_cad)
        self.actionExportVTK.triggered.connect(self.export_vtk)
        self.actionExportCSV.triggered.connect(self.export_csv)

        """Edit actions -> slots"""
        self.actionRemoveEntity.triggered.connect(self.entity_remove)
        self.actionConnectedParts.triggered.connect(self.connected_parts)
        self.actionMergeEntities.triggered.connect(self.entities_merge)
        self.actionSplitMultipart.triggered.connect(self.split_multipart)
        self.actionDecimatePointCloud.triggered.connect(self.decimate_pc_dialog)
        """______________________________________ ADD TOOL TO PRINT VTK INFO self.print_terminal( -- vtk object as text -- )"""
        self.actionAddTexture.triggered.connect(self.texture_add)
        self.actionRemoveTexture.triggered.connect(self.texture_remove)
        self.actionAddProperty.triggered.connect(self.property_add)
        self.actionRemoveProperty.triggered.connect(self.property_remove)
        self.actionCalculateNormals.triggered.connect(self.normals_calculate)
        self.actionCalculateLineations.triggered.connect(self.lineations_calculate)

        self.actionBuildOctree.triggered.connect(self.build_octree)

        """Interpolation actions -> slots"""
        self.actionDelaunay2D.triggered.connect(lambda: interpolation_delaunay_2d(self))
        self.actionPoisson.triggered.connect(lambda: poisson_interpolation(self))
        self.actionLoopStructural.triggered.connect(
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
        self.actionEnhancedExtrusion = QAction("Enhanced Extrusion", self)
        self.actionEnhancedExtrusion.setObjectName("actionEnhancedExtrusion")
        self.actionEnhancedExtrusion.triggered.connect(
            lambda: enhanced_linear_extrusion(self)
        )
        self.menuProjection.addAction(self.actionEnhancedExtrusion)
        self.actionProject2DEM.triggered.connect(lambda: project_2_dem(self))
        self.actionXSectionIntersection.triggered.connect(lambda: intersection_xs(self))
        self.actionProject2XSection.triggered.connect(lambda: project_2_xs(self))
        self.actionSplitSurfaces.triggered.connect(lambda: split_surf(self))
        self.actionRetopologize.triggered.connect(self.retopologize_surface)

        """View actions -> slots"""
        self.action3DView.triggered.connect(
            lambda: DockWindow(parent=self, window_type="View3D")
        )
        self.actionMapView.triggered.connect(
            lambda: DockWindow(parent=self, window_type="ViewMap")
        )

        self.actionXSectionView.triggered.connect(
            lambda: DockWindow(parent=self, window_type="ViewXsection")
        )
        self.actionInterpretationView.triggered.connect(
            lambda: DockWindow(parent=self, window_type="ViewInterpretation")
        )
        self.actionStereoplotView.triggered.connect(
            lambda: DockWindow(parent=self, window_type="ViewStereoplot")
        )
        self.actionTableView = QAction("Table View", self)
        self.actionTableView.setObjectName("actionTableView")
        self.actionTableView.triggered.connect(
            lambda: DockWindow(parent=self, window_type="ViewTable")
        )
        self.menuWindows.insertAction(self.actionXYPlotView, self.actionTableView)

        """File>CRS actions -> slots"""
        self.actionTransformSelectedCRS.triggered.connect(
            lambda: CRS_transform_selected(self)
        )
        self.actionListCRS.triggered.connect(lambda: CRS_list(self))

        """Help actions -> slots"""
        self.actionHelp.triggered.connect(self.open_help_url)
        self.actionCheckForUpdates.triggered.connect(self.open_release_url)
        self.actionAbout.triggered.connect(self.show_about_dialog)

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
            self.signals.project_close.emit()  # this is used to delete open windows when the current project is closed
            event.accept()
        else:
            event.ignore()

    def disable_actions(self):
        """Freeze all actions while doing something."""
        # self.parent.findChildren(QAction) returns a list of all actions in the application.
        print("- disabling actions in project window")
        for action in self.findChildren(QAction):
            try:
                # try - except added to catch an inexplicable bug with an action with text=""
                action.setDisabled(True)
            except:
                pass

    def enable_actions(self):
        """Un-freeze all actions after having done something."""
        # self.parent.findChildren(QAction) returns a list of all actions in the application.
        print("o enabling actions in project window")
        for action in self.findChildren(QAction):
            try:
                # try - except added for symmetry with disable_actions (bug with an action with text="")
                action.setEnabled(True)
            except:
                pass

    def print_terminal(self, string=None):
        """Show string in terminal."""
        try:
            self.TextTerminal.appendPlainText(string)
        except:
            self.TextTerminal.appendPlainText("error printing in terminal")

    def show_about_dialog(self):

        dialog = QDialog(self)
        dialog.setWindowTitle("About PZero")
        dialog.setFixedWidth(420)

        layout = QVBoxLayout(dialog)

        # Logo
        image_path = QPixmap("images/Gecos_logo.jpg")
        logo_label = QLabel()
        pixmap = QPixmap(image_path)

        if not pixmap.isNull():
            logo_label.setPixmap(pixmap.scaledToWidth(220, Qt.SmoothTransformation))
            logo_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(logo_label)

        # Text
        text_label = QLabel(
            "<b>PZero</b> © 2020 Andrea Bistacchi<br><br>"
            "Released under the <b>GNU AGPLv3</b> license.<br><br>"
            "PZero is a Python open-source 3D geological modelling application "
            "supporting explicit surface interpolation, advanced implicit modelling, "
            "and standard geomodelling data management and analysis workflows."
        )
        text_label.setWordWrap(True)
        text_label.setAlignment(Qt.AlignCenter)

        layout.addWidget(text_label)

        dialog.setLayout(layout)
        dialog.exec()

    def open_help_url(self):
        QDesktopServices.openUrl(QUrl("https://github.com/gecos-lab/PZero/wiki"))

    def open_release_url(self):
        QDesktopServices.openUrl(QUrl("https://github.com/gecos-lab/PZero/releases"))

    """Methods used to manage the entities shown in tables."""

    @property
    def shown_table(self):
        """Returns which collection table tab is shown."""
        return self.tabWidgetTopLeft.currentWidget().objectName()

    @property
    def selected_collection(self):
        """Returns which collection is shown, based on shown_table."""
        return self.tab_collection_dict[self.shown_table]

    @property
    def table_view_collection_dict(self):
        """Map table view widgets to collection attribute names."""
        return {
            self.GeologyTableView: "geol_coll",
            self.XSectionsTableView: "xsect_coll",
            self.DOMsTableView: "dom_coll",
            self.ImagesTableView: "image_coll",
            self.Meshes3DTableView: "mesh3d_coll",
            self.BoundariesTableView: "boundary_coll",
            self.WellsTableView: "well_coll",
            self.FluidsTableView: "fluid_coll",
            self.BackgroundsTableView: "backgrnd_coll",
        }

    def collection_display_name(self, collection_name: str = None) -> str:
        """Return a user-facing collection name."""
        names = {
            "geol_coll": "Geology",
            "xsect_coll": "X Sections",
            "dom_coll": "DEMs and DOMs",
            "image_coll": "Images",
            "mesh3d_coll": "Meshes and Grids",
            "boundary_coll": "Boundaries",
            "well_coll": "Wells",
            "fluid_coll": "Fluids",
            "backgrnd_coll": "Background",
        }
        return names.get(collection_name, str(collection_name))

    def bind_collection_table_context_menus(self):
        """Bind right-click context menus for all entities table views."""
        for table_view, collection_name in self.table_view_collection_dict.items():
            old_handler = getattr(table_view, "_transfer_context_handler", None)
            if old_handler:
                try:
                    table_view.customContextMenuRequested.disconnect(old_handler)
                except Exception:
                    pass
            table_view.setContextMenuPolicy(Qt.CustomContextMenu)
            handler = (
                lambda pos, tv=table_view, src=collection_name: self.on_entities_table_context_menu(
                    table_view=tv, source_collection_name=src, position=pos
                )
            )
            table_view._transfer_context_handler = handler
            table_view.customContextMenuRequested.connect(handler)

    def get_selected_uids_from_table(self, table_view=None) -> list:
        """Get selected entity UIDs from a given table view."""
        if table_view is None or table_view.selectionModel() is None:
            return []
        selected_rows = table_view.selectionModel().selectedRows(column=0)
        return list(dict.fromkeys([idx.data() for idx in selected_rows if idx.data()]))

    def on_entities_table_context_menu(
        self, table_view=None, source_collection_name: str = None, position=None
    ):
        """Open table right-click menu with Copy to / Move to actions."""
        if table_view is None or not source_collection_name:
            return

        idx = table_view.indexAt(position)
        if idx.isValid():
            selected_rows = {
                selected_idx.row()
                for selected_idx in table_view.selectionModel().selectedRows()
            }
            if idx.row() not in selected_rows:
                table_view.clearSelection()
                table_view.selectRow(idx.row())

        selected_uids = self.get_selected_uids_from_table(table_view=table_view)
        if not selected_uids:
            return

        source_collection = getattr(self, source_collection_name, None)
        if source_collection is None:
            return

        menu = QMenu(table_view)
        copy_menu = menu.addMenu("Copy to")
        move_menu = menu.addMenu("Move to")

        action_map = {}
        for destination_collection_name in self.tab_collection_dict.values():
            destination_collection = getattr(self, destination_collection_name, None)
            if destination_collection is None:
                continue

            label = self.collection_display_name(destination_collection_name)
            copy_action = copy_menu.addAction(label)
            move_action = move_menu.addAction(label)
            action_map[copy_action] = (destination_collection_name, False)
            action_map[move_action] = (destination_collection_name, True)

            compatible = True
            for uid in selected_uids:
                can_transfer, _ = source_collection.can_transfer_uid_to_collection(
                    uid=uid, destination_collection=destination_collection
                )
                if not can_transfer:
                    compatible = False
                    break

            copy_action.setEnabled(compatible)
            move_action.setEnabled(
                compatible and destination_collection_name != source_collection_name
            )

        chosen_action = menu.exec(table_view.viewport().mapToGlobal(position))
        if chosen_action not in action_map:
            return

        destination_collection_name, move = action_map[chosen_action]
        self.transfer_entities_between_collections(
            source_collection_name=source_collection_name,
            destination_collection_name=destination_collection_name,
            selected_uids=selected_uids,
            move=move,
        )

    def transfer_entities_between_collections(
        self,
        source_collection_name: str = None,
        destination_collection_name: str = None,
        selected_uids: list = None,
        move: bool = False,
    ) -> dict:
        """Copy/move selected UIDs between collections and log the result."""
        source_collection = getattr(self, source_collection_name, None)
        destination_collection = getattr(self, destination_collection_name, None)
        if source_collection is None or destination_collection is None or not selected_uids:
            return {"added_uids": [], "removed_uids": [], "failed": []}

        if move and source_collection_name == destination_collection_name:
            self.print_terminal(
                "Move cancelled: source and destination collections are the same."
            )
            return {
                "added_uids": [],
                "removed_uids": [],
                "failed": [{"uid": None, "reason": "same source and destination"}],
            }

        report = source_collection.transfer_uids_to_collection(
            destination_collection=destination_collection,
            uids=selected_uids,
            move=move,
            keep_uid_on_move=False,
        )

        operation = "Moved" if move else "Copied"
        self.print_terminal(
            f"{operation} {len(report['added_uids'])} entities from "
            f"{self.collection_display_name(source_collection_name)} to "
            f"{self.collection_display_name(destination_collection_name)}."
        )
        for failed in report["failed"]:
            self.print_terminal(
                f"{operation} skipped for uid {failed['uid']}: {failed['reason']}"
            )
        return report

    @property
    def selected_uids(self):
        """Returns a list of uids selected in the table view. Just rows completely selected are returned."""
        selected_uids = []
        if self.shown_table == "tabGeology":
            # this will always give rows that have selected the column 0 (in this case uid). By changing
            # the column=0 to another index it will give the value in another column.
            selected_idxs_proxy = self.GeologyTableView.selectionModel().selectedRows(
                column=0
            )
            for idx_proxy in selected_idxs_proxy:
                selected_uids.append(idx_proxy.data())

        elif self.shown_table == "tabXSections":
            selected_idxs_proxy = self.XSectionsTableView.selectionModel().selectedRows(
                column=0
            )
            for idx_proxy in selected_idxs_proxy:
                selected_uids.append(idx_proxy.data())

        elif self.shown_table == "tabMeshes":
            selected_idxs_proxy = self.Meshes3DTableView.selectionModel().selectedRows(
                column=0
            )
            for idx_proxy in selected_idxs_proxy:
                selected_uids.append(idx_proxy.data())

        elif self.shown_table == "tabDOMs":
            selected_idxs_proxy = self.DOMsTableView.selectionModel().selectedRows(
                column=0
            )
            for idx_proxy in selected_idxs_proxy:
                selected_uids.append(idx_proxy.data())
        elif self.shown_table == "tabImages":
            selected_idxs_proxy = self.ImagesTableView.selectionModel().selectedRows(
                column=0
            )
            for idx_proxy in selected_idxs_proxy:
                selected_uids.append(idx_proxy.data())

        elif self.shown_table == "tabBoundaries":
            selected_idxs_proxy = (
                self.BoundariesTableView.selectionModel().selectedRows(column=0)
            )
            for idx_proxy in selected_idxs_proxy:
                selected_uids.append(idx_proxy.data())

        elif self.shown_table == "tabWells":
            selected_idxs_proxy = self.WellsTableView.selectionModel().selectedRows(
                column=0
            )
            for idx_proxy in selected_idxs_proxy:
                selected_uids.append(idx_proxy.data())

        elif self.shown_table == "tabFluids":
            selected_idxs_proxy = self.FluidsTableView.selectionModel().selectedRows(
                column=0
            )
            for idx_proxy in selected_idxs_proxy:
                selected_uids.append(idx_proxy.data())

        elif self.shown_table == "tabBackgrounds":
            selected_idxs_proxy = (
                self.BackgroundsTableView.selectionModel().selectedRows(column=0)
            )
            for idx_proxy in selected_idxs_proxy:
                selected_uids.append(idx_proxy.data())
        return selected_uids

    #  This is should be used for cross collection operations (e.g. cut surfaces in the geology table with the DEM).
    # We could use this instead of selected_uids but we should impose validity checks for the different functions
    # @property
    # def selected_uids_all(self):
    #     """Returns a list of all uids selected in every table view."""
    #     tab_list = ["tabDOMs","tabGeology","tabXSections","tabMeshes","tabImages","tabBoundaries","tabWells","tabFluids"]
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
    #         elif tab == "tabMeshes":
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
    #                 selected_uids_all.append(self.fluid_coll.data(index=idx, qt_role=Qt.DisplayRole))
    #         elif tab == "tabBackgrounds":
    #             selected_idxs_proxy = self.BackgroundsTableView.selectionModel().selectedRows()
    #             for idx_proxy in selected_idxs_proxy:
    #                 selected_idxs.append(self.proxy_well_coll.mapToSource(idx_proxy))
    #             for idx in selected_idxs:
    #                 selected_uids_all.append(self.backgrnd_coll.data(index=idx, qt_role=Qt.DisplayRole))
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
        for uid in self.selected_uids:
            if self.shown_table == "tabGeology":
                self.geol_coll.remove_entity(uid=uid)
            elif self.shown_table == "tabXSections":
                self.xsect_coll.remove_entity(uid=uid)
            elif self.shown_table == "tabMeshes":
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
                self.fluid_coll.remove_entity(uid=uid)
            elif self.shown_table == "tabBackgrounds":
                self.backgrnd_coll.remove_entity(uid=uid)

    def entities_merge(self):
        """Merge entities of the same topology - VertexSet, PolyLine, TriSurf, ..."""
        if not self.selected_uids:
            return
        if self.shown_table == "tabGeology":
            collection = self.geol_coll
        elif self.shown_table == "tabDOMs":
            collection = self.dom_coll
        else:
            return
        xsect_list = []

        for uid in self.selected_uids:
            xsect_value = collection.get_uid_x_section(uid)
            xsect_list.append(xsect_value)
        unique_xsect_uids = set(xsect_list)
        if len(unique_xsect_uids) == 1:
            self.print_terminal(
                "All selected entities share the same xsection_uid or have no xsection_uid assigned"
            )
        else:
            self.print_terminal(
                "Selected entities have mixed parent uids. Please select entities with the same parent_uid or that don't belong to any x-section or well."
            )
            return

        """Proceed with existing logic to collect properties and merge."""
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
                xsect_list.append(collection.get_uid_x_section(uid))
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
                "parent_uid": ["XSection: ", xsect_list],
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
                xsect_list.append(collection.get_uid_xsect(uid))
            name_list = list(set(name_list))
            topology_list = list(set(topology_list))
            xsect_list = list(set(xsect_list))
            input_dict = {
                "name": ["New name: ", name_list],
                "topology": ["Topology", topology_list],
                "parent_uid": ["XSection: ", xsect_list],
            }
        else:
            return
        updt_dict = multiple_input_dialog(
            title="Merge entities to multi-part", input_dict=input_dict
        )
        """Check if the output of the widget is empty or not. If the Cancel sender was clicked, the tool quits"""
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
        # Ask whether to keep or removed merged entities.
        remove_merged_option = options_dialog(
            title="Remove merged entities?",
            message="Do you want to keep or remove merged entities?",
            yes_role="Keep",
            no_role="Remove",
            reject_role="Quit merging",
        )
        if not (remove_merged_option == 0 or remove_merged_option == 1):
            return
        # Create a vtkAppendPolyData filter to merge all input vtk objects
        vtkappend = vtkAppendPolyData()
        # Loop that collects all selected items to create the merge. Only entities of the same
        # topology as chosen in the widget are merged, others are discarded.
        for uid in self.selected_uids:
            if new_dict["topology"] == collection.get_uid_topology(uid):
                vtkappend.AddInputData(collection.get_uid_vtk_obj(uid))
                if remove_merged_option == 1:
                    collection.remove_entity(uid=uid)
        vtkappend.Update()
        # ShallowCopy is the way to copy the new vtk object into the empty instance created above.
        new_dict["vtk_obj"].ShallowCopy(vtkappend.GetOutput())
        new_dict["vtk_obj"].Modified()
        # Test if the merged object is not empty.
        if new_dict["vtk_obj"].points_number == 0:
            return
        # Add new entity from surf_dict. Function add_entity_from_dict creates a new uid
        uid_new = collection.add_entity_from_dict(new_dict)

    def texture_add(self):
        """Add texture to selected DEMs. Just rows completely selected are considered."""
        if not self.shown_table == "tabDOMs":
            return
        if not self.selected_uids:
            return
        # Map Image selection dialog.
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
        # Add textures.
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
        # Map Image selection dialog.
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
        # Remove textures.
        if map_image_uid in self.image_coll.get_uids:
            dom_uids = self.selected_uids
            for dom_uid in dom_uids:
                self.dom_coll.remove_map_texture_from_dom(
                    dom_uid=dom_uid, map_image_uid=map_image_uid
                )

    @ freeze_gui_onoff
    def property_add(self):
        # ____________________________________________________ ADD IMAGES
        """Add empty property on geological entity"""
        if not self.shown_table in ["tabGeology", "tabMeshes", "tabDOMs"]:
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
                if not updt_dict[
                    "property_name"
                ] in self.geol_coll.get_uid_properties_names(uid):
                    self.geol_coll.append_uid_property(
                        uid=uid,
                        property_name=updt_dict["property_name"],
                        property_components=updt_dict["property_components"],
                    )
        elif self.shown_table == "tabMeshes":
            for uid in self.selected_uids:
                if not updt_dict[
                    "property_name"
                ] in self.mesh3d_coll.get_uid_properties_names(uid):
                    self.mesh3d_coll.append_uid_property(
                        uid=uid,
                        property_name=updt_dict["property_name"],
                        property_components=updt_dict["property_components"],
                    )
        elif self.shown_table == "tabDOMs":
            for uid in self.selected_uids:
                if not updt_dict[
                    "property_name"
                ] in self.dom_coll.get_uid_properties_names(uid):
                    self.dom_coll.append_uid_property(
                        uid=uid,
                        property_name=updt_dict["property_name"],
                        property_components=updt_dict["property_components"],
                    )
        # Finally update properties legend.
        self.prop_legend.update_widget(self)

    def property_remove(self):
        # ____________________________________________________ ADD IMAGES
        if not self.shown_table in ["tabGeology", "tabMeshes", "tabDOMs"]:
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
        elif self.shown_table == "tabMeshes":
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
        # Finally update properties legend.
        self.prop_legend.update_widget(self)

    def normals_calculate(self):
        # ____________________________________________________ ADD MORE CASES FOR POINT CLOUDS ETC.
        """Calculate Normals on geological entities (add point clouds and DOMS in the future)."""
        if self.shown_table in ["tabGeology", "tabMeshes", "tabDOMs"]:
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
                elif self.shown_table == "tabMeshes":
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
                    self.print_terminal("Only Point clouds are supported")
                    return
        else:
            self.print_terminal("No entity selected")

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
            self.print_terminal(
                "Multiple surfaces selected, only one will be previewed"
            )
        elif len(sel_uids) == 0:
            self.print_terminal("No selected objects")
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
            self.print_terminal(
                "Multiple surfaces selected, only one will be previewed"
            )
        elif len(sel_uids) == 0:
            self.print_terminal("No selected objects")
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
            self.print_terminal(
                "Multiple surfaces selected, only one will be previewed"
            )
        elif len(sel_uids) == 0:
            self.print_terminal("No selected objects")
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

    # Methods used to save/open/create new projects.

    def create_empty(self):
        """Create empty containers for a new empty project."""
        # this is used to delete open windows when the current project is closed (and a new one is opened)
        self.signals.project_close.emit()

        self.custom_tables = {}
        self.custom_table_types = {}
        self.custom_table_options = {}

        # Create the geol_coll GeologicalCollection (a Qt QAbstractTableModel with a Pandas dataframe as attribute)
        # and connect the model to GeologyTableView (a Qt QTableView created with QTDesigner and provided by
        # Ui_ProjectWindow). Setting the model also updates the view.
        self.geol_coll = GeologicalCollection(parent=self)
        self.GeologyTableView.setModel(self.geol_coll.proxy_table_model)

        # Create the xsect_coll XSectionCollection (a Qt QAbstractTableModel with a Pandas dataframe as attribute)
        # and connect the model to XSectionsTableView (a Qt QTableView created with QTDesigner and provided by
        # Ui_ProjectWindow). Setting the model also updates the view.
        self.xsect_coll = XSectionCollection(parent=self)
        self.XSectionsTableView.setModel(self.xsect_coll.proxy_table_model)

        # Create the dom_coll DomCollection (a Qt QAbstractTableModel with a Pandas dataframe as attribute)
        # and connect the model to DOMsTableView (a Qt QTableView created with QTDesigner and provided by
        # Ui_ProjectWindow). Setting the model also updates the view.
        self.dom_coll = DomCollection(parent=self)
        self.DOMsTableView.setModel(self.dom_coll.proxy_table_model)

        # Create the image_coll ImageCollection (a Qt QAbstractTableModel with a Pandas dataframe as attribute)
        # and connect the model to ImagesTableView (a Qt QTableView created with QTDesigner and provided by
        # Ui_ProjectWindow). Setting the model also updates the view.
        self.image_coll = ImageCollection(parent=self)
        self.ImagesTableView.setModel(self.image_coll.proxy_table_model)

        # Create the mesh3d_coll Mesh3DCollection (a Qt QAbstractTableModel with a Pandas dataframe as attribute)
        # and connect the model to Meshes3DTableView (a Qt QTableView created with QTDesigner and provided by
        # Ui_ProjectWindow). Setting the model also updates the view.
        self.mesh3d_coll = Mesh3DCollection(parent=self)
        self.Meshes3DTableView.setModel(self.mesh3d_coll.proxy_table_model)

        # Create the boundary_coll BoundaryCollection (a Qt QAbstractTableModel with a Pandas dataframe as attribute)
        # and connect the model to BoundaryTableView (a Qt QTableView created with QTDesigner and provided by
        # Ui_ProjectWindow). Setting the model also updates the view.
        self.boundary_coll = BoundaryCollection(parent=self)
        self.BoundariesTableView.setModel(self.boundary_coll.proxy_table_model)

        #   Create the weel_coll WellCollection (a Qt QAbstractTableModel with a Pandas dataframe as attribute)
        # and connect the model to WellTableView (a Qt QTableView created with QTDesigner and provided by
        # Ui_ProjectWindow). Setting the model also updates the view.
        self.well_coll = WellCollection(parent=self)
        self.WellsTableView.setModel(self.well_coll.proxy_table_model)

        #   Create the fluid_coll FluidCollection (a Qt QAbstractTableModel with a Pandas dataframe as attribute)
        # and connect the model to FluidTableView (a Qt QTableView created with QTDesigner and provided by
        # Ui_ProjectWindow). Setting the model also updates the view.
        self.fluid_coll = FluidCollection(parent=self)
        self.FluidsTableView.setModel(self.fluid_coll.proxy_table_model)

        #   Create the backgrnd_coll BackgroundCollection (a Qt QAbstractTableModel with a Pandas dataframe as attribute)
        # and connect the model to FluidTableView (a Qt QTableView created with QTDesigner and provided by
        # Ui_ProjectWindow). Setting the model also updates the view.
        self.backgrnd_coll = BackgroundCollection(parent=self)
        self.BackgroundsTableView.setModel(self.backgrnd_coll.proxy_table_model)
        for table_view, collection in [
            (self.GeologyTableView, self.geol_coll),
            (self.FluidsTableView, self.fluid_coll),
            (self.BackgroundsTableView, self.backgrnd_coll),
        ]:
            self.bind_role_click_editor(table_view=table_view, collection=collection)
        self.bind_collection_table_context_menus()

        # Create the geol_coll.legend_df legend table (a Pandas dataframe), create the corresponding QT
        # Legend self.legend (a Qt QTreeWidget that is internally connected to its data source),
        # and update the widget.
        self.geol_coll.legend_df = pd_DataFrame(
            columns=list(Legend.geol_legend_dict.keys())
        )
        self.fluid_coll.legend_df = pd_DataFrame(
            columns=list(Legend.fluids_legend_dict.keys())
        )
        self.backgrnd_coll.legend_df = pd_DataFrame(
            columns=list(Legend.backgrounds_legend_dict.keys())
        )

        self.others_legend_df = pd_DataFrame(deepcopy(Legend.others_legend_dict))
        self.legend = Legend()
        self.legend.update_widget(parent=self)

        # Create the prop_legend_df table (a Pandas dataframe), create the corresponding QT
        # PropertiesCMaps table widget self.prop_legend (a Qt QTableWidget that is internally connected to its data source),
        # and update the widget.
        # ____________________________________________________________________________________ UPDATE THIS TO ALLOW SORTING BY PROPERTY NAME
        self.prop_legend_df = pd_DataFrame(PropertiesCMaps.prop_cmap_dict)
        self.prop_legend = PropertiesCMaps()
        self.prop_legend.update_widget(parent=self)

    def bind_role_click_editor(self, table_view=None, collection=None):
        """Bind click-to-dropdown behavior for role cells using collection.valid_roles."""
        if table_view is None or collection is None:
            return
        if "role" not in collection.df.columns or not collection.valid_roles:
            return
        role_col = collection.df.columns.get_loc("role")

        old_handler = getattr(table_view, "_role_click_handler", None)
        if old_handler:
            try:
                table_view.clicked.disconnect(old_handler)
            except:
                pass

        handler = lambda idx, tv=table_view, coll=collection, rc=role_col: self.on_role_cell_clicked(
            table_view=tv, collection=coll, role_col=rc, index=idx
        )
        table_view._role_click_handler = handler
        table_view.clicked.connect(handler)

    def on_role_cell_clicked(self, table_view=None, collection=None, role_col=None, index=None):
        """Open an in-table combo editor for role values when clicking the role column."""
        if table_view is None or collection is None or index is None:
            return
        if not index.isValid():
            return
        if index.column() != role_col:
            self.clear_role_cell_editor(table_view=table_view)
            return

        valid_roles = [str(role) for role in collection.valid_roles]
        if not valid_roles:
            return

        self.clear_role_cell_editor(table_view=table_view)
        current_role = index.data(Qt.DisplayRole)
        current_role = "" if current_role is None else str(current_role)
        current_idx = (
            valid_roles.index(current_role) if current_role in valid_roles else 0
        )

        combo = QComboBox(table_view)
        combo.setEditable(False)
        combo.addItems(valid_roles)
        combo.setCurrentIndex(current_idx)

        table_view.setIndexWidget(index, combo)
        table_view._active_role_editor = (index, combo)

        combo.activated.connect(
            lambda _=None, tv=table_view, idx=index, cb=combo: self.commit_role_cell_editor(
                table_view=tv, index=idx, combo=cb
            )
        )
        QTimer.singleShot(0, combo.showPopup)

    def commit_role_cell_editor(self, table_view=None, index=None, combo=None):
        if table_view is None or index is None or combo is None:
            return
        if index.isValid():
            selected_role = str(combo.currentText())
            if selected_role:
                table_view.model().setData(index, selected_role, Qt.EditRole)
        self.clear_role_cell_editor(table_view=table_view)

    def clear_role_cell_editor(self, table_view=None):
        if table_view is None:
            return
        active_editor = getattr(table_view, "_active_role_editor", None)
        if not active_editor:
            return
        editor_index, editor_combo = active_editor
        try:
            table_view.setIndexWidget(editor_index, None)
        except:
            pass
        if editor_combo:
            editor_combo.deleteLater()
        table_view._active_role_editor = None


    def save_project(self):
        # ________________________________________WRITERS TO BE MOVED TO COLLECTIONS
        """Save project to file and folder"""
        # Get date and time, used to save incremental revisions.
        now = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        # Select and open output file and folder. Saving always performs a complete backup since the output folder
        # is named with the present date and time "rev_<now>".
        self.out_file_name = save_file_dialog(
            parent=self, caption="Save project.", filter="PZero (*.p0)"
        )
        if not self.out_file_name:
            return
        out_dir_name = self.out_file_name[:-3] + "_p0/rev_" + now
        self.print_terminal(
            f"Saving project as VTK files and csv tables with metada and legend.\nIn file/folder: {self.out_file_name}/{out_dir_name}\n"
        )
        # Create the folder if it does not exist already.
        if not os_path.isdir(self.out_file_name[:-3] + "_p0"):
            os_mkdir(self.out_file_name[:-3] + "_p0")
        os_mkdir(out_dir_name)
        # Save the root file pointing to the folder.
        fout = open(self.out_file_name, "w")
        fout.write(
            "PZero project file saved in folder with the same name, including VTK files and CSV tables.\n"
        )
        fout.write("Last saved revision:\n")
        fout.write(f"rev_{now}\n")
        fout.write("CRS EPSG:\n")
        test_epsg = 'test_epsg'
        fout.write(f"{test_epsg}\n")
        fout.close()

        # --------------------- SAVE LEGENDS ---------------------

        # Save geological legend table to JSON file. Keep old CSV table format here in comments, in case it might be useful in the future.
        self.geol_coll.legend_df.to_json(
            out_dir_name + "/geol_legend_table.json", orient="index"
        )
        # self.geol_coll.legend_df.to_csv(out_dir_name + '/geol_legend_table.csv', encoding='utf-8', index=False)
        # Save others legend table to JSON file.
        self.others_legend_df.to_json(
            out_dir_name + "/others_legend_table.json", orient="index"
        )
        # self.others_legend_df.to_csv(out_dir_name + '/others_legend_table.csv', encoding='utf-8', index=False)
        # Save properties legend table to JSON file.
        self.prop_legend_df.to_json(
            out_dir_name + "/prop_legend_df.json", orient="index"
        )
        # self.prop_legend_df.to_csv(out_dir_name + '/prop_legend_df.csv', encoding='utf-8', index=False)

        self.fluid_coll.legend_df.to_json(
            out_dir_name + "/fluids_legend_table.json", orient="index"
        )

        self.backgrnd_coll.legend_df.to_json(
            out_dir_name + "/backgrounds_legend_table.json", orient="index"
        )

        self.save_custom_tables(out_dir_name=out_dir_name)

        # --------------------- SAVE tables ---------------------

        # Save x-section table to JSON file.
        out_cols = list(self.xsect_coll.df.columns)
        out_cols.remove("vtk_plane")
        out_cols.remove("vtk_frame")
        self.xsect_coll.df[out_cols].to_json(
            out_dir_name + "/xsection_table.json", orient="index"
        )
        # self.xsect_coll.df[out_cols].to_csv(out_dir_name + '/xsection_table.csv', encoding='utf-8', index=False)

        # Save geological collection table to JSON file and entities as VTK.
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

        # Save DOM collection table to JSON file and entities as VTK.
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
                # Save PCDOm collection entities as VTK.
                pd_writer = vtkXMLPolyDataWriter()
                pd_writer.SetFileName(out_dir_name + "/" + uid + ".vtp")
                pd_writer.SetInputData(self.dom_coll.get_uid_vtk_obj(uid))
                pd_writer.Write()
                prgs_bar.add_one()

        # Save image collection table to JSON file and entities as VTK.
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
                source_file = None
                if "seismic_source_file" in self.image_coll.df.columns:
                    try:
                        source_file = self.image_coll.df.loc[
                            self.image_coll.df["uid"] == uid, "seismic_source_file"
                        ].values[0]
                    except Exception:
                        source_file = None

                source_file = source_file if isinstance(source_file, str) and source_file.strip() else None
                source_exists = bool(source_file and os_path.isfile(source_file))

                # Fast path: keep only a reference to the original SEG-Y source when it is available.
                # Fallback: persist a VTK copy only when the source cannot be reused on reopen.
                if not source_exists:
                    sg_writer = vtkXMLStructuredGridWriter()
                    sg_writer.SetFileName(out_dir_name + "/" + uid + ".vts")
                    sg_writer.SetInputData(self.image_coll.get_uid_vtk_obj(uid))
                    sg_writer.Write()

                seismic_metadata = {
                    "uid": uid,
                    "source_file": source_file,
                    "storage": "source_file" if source_exists else "embedded_vts",
                }
                with open(out_dir_name + "/" + uid + "_seismic_metadata.json", "w") as f:
                    json_dump(seismic_metadata, f, indent=2)
                prgs_bar.add_one()

        # Save mesh3d collection table to JSON file and entities as VTK.
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

        # Save boundaries collection table to CSV and JSON files.
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

        # Save wells collection table to CSV and JSON files.

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

        # Save fluids collection table to CSV and JSON files.
        out_cols = list(self.fluid_coll.df.columns)
        out_cols.remove("vtk_obj")
        self.fluid_coll.df[out_cols].to_json(
            out_dir_name + "/fluids_table.json", orient="index"
        )
        # self.geol_coll.df[out_cols].to_csv(out_dir_name + '/geological_table.csv', encoding='utf-8', index=False)
        prgs_bar = progress_dialog(
            max_value=self.fluid_coll.df.shape[0],
            title_txt="Save fluids",
            label_txt="Saving fluid objects...",
            cancel_txt=None,
            parent=self,
        )
        for uid in self.fluid_coll.df["uid"].to_list():
            pd_writer = vtkXMLPolyDataWriter()
            pd_writer.SetFileName(out_dir_name + "/" + uid + ".vtp")
            pd_writer.SetInputData(self.fluid_coll.get_uid_vtk_obj(uid))
            pd_writer.Write()
            prgs_bar.add_one()

        # Save Backgrounds collection table to CSV and JSON files.
        out_cols = list(self.backgrnd_coll.df.columns)
        out_cols.remove("vtk_obj")
        self.backgrnd_coll.df[out_cols].to_json(
            out_dir_name + "/backgrounds_table.json", orient="index"
        )
        # self.geol_coll.df[out_cols].to_csv(out_dir_name + '/geological_table.csv', encoding='utf-8', index=False)
        prgs_bar = progress_dialog(
            max_value=self.backgrnd_coll.df.shape[0],
            title_txt="Save Backgrounds",
            label_txt="Saving Backgrounds objects...",
            cancel_txt=None,
            parent=self,
        )
        for uid in self.backgrnd_coll.df["uid"].to_list():
            pd_writer = vtkXMLPolyDataWriter()
            pd_writer.SetFileName(out_dir_name + "/" + uid + ".vtp")
            pd_writer.SetInputData(self.backgrnd_coll.get_uid_vtk_obj(uid))
            pd_writer.Write()
            prgs_bar.add_one()

    def save_custom_tables(self, out_dir_name: str = None):
        """Persist user-defined tables alongside the project revision."""
        if not out_dir_name:
            return

        tables_payload = {"version": 1, "tables": []}
        for table_name, dataframe in self.custom_tables.items():
            exported_df = dataframe.copy()
            exported_df = exported_df.where(exported_df.notna(), "")
            exported_df = exported_df.astype(str)
            tables_payload["tables"].append(
                {
                    "name": table_name,
                    "table_type": self.custom_table_types.get(table_name, "manual"),
                    "options": self.custom_table_options.get(table_name, {}),
                    "dataframe": {
                        "columns": exported_df.columns.tolist(),
                        "data": exported_df.values.tolist(),
                    },
                }
            )

        with open(out_dir_name + "/custom_tables.json", "w", encoding="utf-8") as fout:
            json_dump(tables_payload, fout, indent=2)

    def load_custom_tables(self, in_dir_name: str = None):
        """Load user-defined project tables."""
        self.custom_tables = {}
        self.custom_table_types = {}
        self.custom_table_options = {}
        if not in_dir_name:
            return

        custom_tables_path = in_dir_name + "/custom_tables.json"
        if not os_path.isfile(custom_tables_path):
            return

        with open(custom_tables_path, "r", encoding="utf-8") as fin:
            tables_payload = json_load(fin)

        for table_payload in tables_payload.get("tables", []):
            table_name = str(table_payload.get("name", "")).strip()
            if not table_name:
                continue

            dataframe_payload = table_payload.get("dataframe", {})
            columns = [
                str(column_name)
                for column_name in dataframe_payload.get("columns", [])
            ]
            data = dataframe_payload.get("data", [])
            self.custom_tables[table_name] = pd_DataFrame(data=data, columns=columns)
            self.custom_table_types[table_name] = table_payload.get(
                "table_type", "manual"
            )
            self.custom_table_options[table_name] = table_payload.get("options", {})

        if self.custom_tables:
            self.print_terminal(
                f"Loaded {len(self.custom_tables)} custom table(s)."
            )
        self.sync_structural_topology_tables_from_legend()
        self.refresh_custom_colormaps()

    def new_project(self):
        """Creates a new empty project, after having cleared all variables."""
        # Ask confirmation if the project already contains entities in the geological collection.
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
        # Create empty containers.
        self.create_empty()
        # """Save a new empty project to file"""
        # self.save_project()

    def open_project(self):
        """Opens a project previously saved to disk."""
        # Create empty containers. This clears all previous objects and also allows for missing tables below.
        current_entities_n = (
            self.backgrnd_coll.get_number_of_entities
            + self.boundary_coll.get_number_of_entities
            + self.dom_coll.get_number_of_entities
            + self.fluid_coll.get_number_of_entities
            + self.geol_coll.get_number_of_entities
            + self.image_coll.get_number_of_entities
            + self.mesh3d_coll.get_number_of_entities
            + self.well_coll.get_number_of_entities
            + self.xsect_coll.get_number_of_entities
        )
        if current_entities_n > 0:
            confirm_new = options_dialog(
                title="Open project",
                message="Save current project and open a new one?",
                yes_role="Yes",
                no_role="Open without saving",
                reject_role="Abort",
            )
            if confirm_new == 0:
                self.save_project()
            elif confirm_new != 1:
                return

        self.create_empty()

        # Select and open project file.
        in_file_name = open_file_dialog(
            parent=self, caption="Open PZero project", filter=("PZero (*.p0)")
        )
        if not in_file_name:
            return
        self.out_file_name = in_file_name

        # use try - except to avoid crashing in case a corrupted project is opened
        try:
            # Read name of last revision in project file. This opens the last revision.
            # To open a different one, edit the project file.
            # ___________________________________ IN THE FUTURE an option to open a specific revision could be added
            fin = open(in_file_name, "rt")
            lines = fin.readlines()
            rev_name = lines[2].strip()
            try:
                test_epsg = lines[4].strip()
            except:
                test_epsg = 'no_epsg'
            fin.close()
            in_dir_name = in_file_name[:-3] + "_p0/" + rev_name
            self.print_terminal(
                f"Opening project/revision : {in_file_name}/{rev_name}\n"
            )
            self.print_terminal(
                f"Project CRS : {test_epsg}\n"
            )
            if not os_path.isdir(in_dir_name):
                self.print_terminal(in_dir_name)
                self.print_terminal("-- ERROR: missing folder --")
                return

            #  In the following it is still possible to open old projects with metadata stored
            #  as CSV tables, however JSON is used now because it leads to fewer problems and errors
            #  for numeric and list fields. In fact, reading Pandas dataframes from JSON, dtype
            #  from the class definitions specifies the type of each column.
            # ______ CONSIDER REMOVING THE POSSIBILITY TO OPEN OLD PROJECTS WITH CSV TABLES
            # ______ THAT WILL CAUSE ERRORS IN CASE OF LISTS

            # --------------------- READ LEGENDS ---------------------

            # Read geological legend tables.
            if os_path.isfile(
                (in_dir_name + "/geol_legend_table.csv")
            ) or os_path.isfile((in_dir_name + "/geol_legend_table.json")):
                if os_path.isfile((in_dir_name + "/geol_legend_table.json")):
                    new_geol_coll_legend_df = pd_read_json(
                        in_dir_name + "/geol_legend_table.json",
                        orient="index",
                        dtype=Legend.legend_dict_types,
                    )
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
                to_add = def_keys.difference(in_keys)
                to_remove = in_keys.difference(def_keys)
                if len(to_add) > 0:
                    for col in to_add:
                        self.geol_coll.legend_df[col] = Legend.geol_legend_dict[col]
                        self.print_terminal(f"column {col} added to geological legend")
                if len(to_remove) > 0:
                    for col in to_remove:
                        self.geol_coll.legend_df.drop(columns=col)
                        self.print_terminal(
                            f"column {col} removed from geological legend"
                        )

                self.geol_coll.legend_df.sort_values(
                    by="time", ascending=True, inplace=True
                )

            # Read fluids legend tables.
            if os_path.isfile(
                (in_dir_name + "/fluids_legend_table.csv")
            ) or os_path.isfile((in_dir_name + "/fluids_legend_table.json")):
                if os_path.isfile((in_dir_name + "/fluids_legend_table.json")):
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
                    self.fluid_coll.legend_df = new_fluids_legend_df
                in_keys = set(self.fluid_coll.legend_df.keys())
                def_keys = set(Legend.fluids_legend_dict.keys())

                diffs = def_keys.difference(in_keys)

                if len(diffs) > 0:
                    self.print_terminal(f"fluids_legend_table diffs: {diffs}")
                    for diff in diffs:
                        self.fluid_coll.legend_df[diff] = Legend.fluids_legend_dict[
                            diff
                        ]
                    self.fluid_coll.legend_df.sort_values(
                        by="time", ascending=True, inplace=True
                    )

            # Read Backgrounds legend tables.
            if os_path.isfile(
                (in_dir_name + "/backgrounds_legend_table.csv")
            ) or os_path.isfile((in_dir_name + "/backgrounds_legend_table.json")):
                if os_path.isfile((in_dir_name + "/backgrounds_legend_table.json")):
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
                    self.backgrnd_coll.legend_df = new_backgrounds_legend_df
                in_keys = set(self.backgrnd_coll.legend_df.keys())
                def_keys = set(Legend.backgrounds_legend_dict.keys())

                diffs = def_keys.difference(in_keys)

                if len(diffs) > 0:
                    self.print_terminal(f"backgrounds_legend_table diffs: {diffs}")
                    for diff in diffs:
                        self.backgrnd_coll.legend_df[diff] = (
                            Legend.backgrounds_legend_dict[diff]
                        )

            # Read other legend tables.
            if os_path.isfile(
                (in_dir_name + "/others_legend_table.csv")
            ) or os_path.isfile((in_dir_name + "/others_legend_table.json")):
                if os_path.isfile((in_dir_name + "/others_legend_table.json")):
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
                if not new_others_legend_df.empty:
                    self.others_legend_df = new_others_legend_df
                in_keys = set(self.others_legend_df.keys())
                def_keys = set(Legend.others_legend_dict.keys())

                diffs = def_keys.difference(in_keys)

                if len(diffs) > 0:
                    self.print_terminal(f"others_legend_table diffs: {diffs}")
                    for diff in diffs:
                        self.others_legend_df[diff] = Legend.others_legend_dict[diff]
                default_other_rows = []
                for idx, other_collection in enumerate(
                    Legend.others_legend_dict["other_collection"]
                ):
                    if other_collection in self.others_legend_df[
                        "other_collection"
                    ].tolist():
                        continue
                    default_other_rows.append(
                        {
                            key: Legend.others_legend_dict[key][idx]
                            for key in Legend.others_legend_dict.keys()
                        }
                    )
                if default_other_rows:
                    self.others_legend_df = pd_concat(
                        [
                            self.others_legend_df,
                            pd_DataFrame(default_other_rows),
                        ],
                        ignore_index=True,
                    )
                other_order = {
                    name: idx
                    for idx, name in enumerate(
                        Legend.others_legend_dict["other_collection"]
                    )
                }
                self.others_legend_df["legend_order"] = self.others_legend_df[
                    "other_collection"
                ].map(other_order)
                self.others_legend_df.sort_values(
                    by="legend_order", ascending=True, inplace=True
                )
                self.others_legend_df.drop(columns=["legend_order"], inplace=True)
                self.others_legend_df.reset_index(drop=True, inplace=True)

            if os_path.isfile((in_dir_name + "/prop_legend_df.csv")) or os_path.isfile(
                (in_dir_name + "/prop_legend_df.json")
            ):
                if os_path.isfile((in_dir_name + "/prop_legend_df.json")):
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

            # Read x-section table and build cross-sections. Note beginResetModel() and endResetModel().
            if os_path.isfile((in_dir_name + "/xsection_table.csv")) or os_path.isfile(
                (in_dir_name + "/xsection_table.json")
            ):
                self.xsect_coll.table_model.beginResetModel()
                if os_path.isfile((in_dir_name + "/xsection_table.json")):
                    # noinspection PyTypeChecker
                    new_xsect_coll_df = pd_read_json(
                        in_dir_name + "/xsection_table.json",
                        orient="index",
                        dtype=XSectionCollection.entity_dict_types,
                    )
                else:
                    # noinspection PyTypeChecker
                    new_xsect_coll_df = pd_read_csv(
                        in_dir_name + "/xsection_table.csv",
                        encoding="utf-8",
                        dtype=XSectionCollection.entity_dict_types,
                        keep_default_na=False,
                    )
                # reindex new_dom_coll_df to catch any problem with non-consecutive indices
                new_xsect_coll_df.reset_index(drop=True, inplace=True)
                if not new_xsect_coll_df.empty:
                    if not "height" in new_xsect_coll_df:
                        # case for old projects before simplification of cross-section collection columns
                        if "azimuth" in new_xsect_coll_df.columns:
                            new_xsect_coll_df.rename(
                                columns={"azimuth": "strike"}, inplace=True
                            )
                            self.print_terminal(
                                "column azimuth renamed as strike in x-section table"
                            )
                        if not "parent_uid" in new_xsect_coll_df.columns:
                            new_xsect_coll_df["parent_uid"] = new_xsect_coll_df["uid"]
                            self.print_terminal(
                                "column top renamed as origin_z in x-section table"
                            )

                        if not "width" in new_xsect_coll_df:
                            # case for very old projects, before the introduction of inclined cross-sections
                            # these sections have the base point on top
                            if "base_x" in new_xsect_coll_df.columns:
                                new_xsect_coll_df.rename(
                                    columns={"base_x": "origin_x"}, inplace=True
                                )
                                self.print_terminal(
                                    "column base_x renamed as origin_x in x-section table"
                                )
                            if "base_y" in new_xsect_coll_df.columns:
                                new_xsect_coll_df.rename(
                                    columns={"base_y": "origin_y"}, inplace=True
                                )
                                self.print_terminal(
                                    "column base_y renamed as origin_y in x-section table"
                                )
                            if "top" in new_xsect_coll_df.columns:
                                new_xsect_coll_df.insert(
                                    15,
                                    "height",
                                    abs(new_xsect_coll_df.top - new_xsect_coll_df.bottom),
                                )
                                self.print_terminal("column height added to xsect table")
                            if "top" in new_xsect_coll_df.columns:
                                if "bottom" in new_xsect_coll_df.columns:
                                    new_xsect_coll_df.loc[new_xsect_coll_df["bottom"] > new_xsect_coll_df["top"], "top"] = new_xsect_coll_df["bottom"]
                                new_xsect_coll_df.rename(
                                    columns={"top": "origin_z"}, inplace=True
                                )
                                self.print_terminal(
                                    "column top renamed as origin_z in x-section table"
                                )
                        else:
                            # case for intermediate age projects, after the introduction of inclined cross-sections,
                            # but before columns simplification,
                            # these sections have the base point on bottom, that must be projected to the
                            # top along dip, and width was ok, and must be renames to height
                            new_xsect_coll_df.rename(
                                columns={"width": "height"}, inplace=True
                            )
                            self.print_terminal(
                                "column width renamed as height in x-section table"
                            )
                            new_xsect_coll_df.rename(
                                columns={"base_x": "origin_x"}, inplace=True
                            )
                            self.print_terminal(
                                "column base_x renamed as origin_x in x-section table"
                            )
                            new_xsect_coll_df.rename(
                                columns={"base_y": "origin_y"}, inplace=True
                            )
                            self.print_terminal(
                                "column base_y renamed as origin_y in x-section table"
                            )
                            new_xsect_coll_df.rename(
                                columns={"base_z": "origin_z"}, inplace=True
                            )
                            self.print_terminal(
                                "column base_z renamed as origin_z in x-section table"
                            )
                            new_xsect_coll_df["origin_x"] += (
                                new_xsect_coll_df["height"]
                                * np_cos(new_xsect_coll_df["dip"] * np_pi / 180)
                                * np_cos((new_xsect_coll_df["strike"] + 180 % 360) * np_pi / 180)
                            )
                            new_xsect_coll_df["origin_y"] += (
                                new_xsect_coll_df["height"]
                                * np_cos(new_xsect_coll_df["dip"] * np_pi / 180)
                                * np_sin((new_xsect_coll_df["strike"] + 180 % 360) * np_pi / 180)
                            )
                            new_xsect_coll_df["origin_z"] += (
                                new_xsect_coll_df["height"]
                                * np_sin(new_xsect_coll_df["dip"] * np_pi / 180)
                            )

                    for new_column in new_xsect_coll_df.columns.values.tolist():
                        # drop columns not included in the standard dictionary
                        if new_column not in self.xsect_coll.df.columns.values.tolist():
                            new_xsect_coll_df.drop(new_column, axis=1, inplace=True)
                        self.print_terminal(
                            f"column {new_column} removed from xsect table"
                        )
                    for column in self.xsect_coll.df.columns.values.tolist():
                        # add missing columns with default values
                        if column not in new_xsect_coll_df.columns.values.tolist():
                            missing_column = pd_DataFrame(
                                [{column: self.xsect_coll.entity_dict[column]}]
                                * len(new_xsect_coll_df)
                            )
                            # concat with axis=1 to add the column, and ignore_index=False to keep
                            # the column names of the joined dataframes
                            new_xsect_coll_df = pd_concat(
                                [new_xsect_coll_df, missing_column],
                                ignore_index=False,
                                axis=1,
                            )
                            self.print_terminal(f"column {column} added to xsect table")

                    # Remove duplicate columns if any (can occur when loading old projects)
                    new_xsect_coll_df = new_xsect_coll_df.loc[:, ~new_xsect_coll_df.columns.duplicated()]

                    # reorder columns
                    new_xsect_coll_df = new_xsect_coll_df[self.xsect_coll.df.columns]

                    # finally, set the imported dataframe into the project dataframe
                    self.xsect_coll.df = new_xsect_coll_df

                for uid in self.xsect_coll.df["uid"].tolist():
                    self.xsect_coll.set_geometry(uid=uid)
                self.xsect_coll.table_model.endResetModel()

            # Read DOM table and files. Note beginResetModel() and endResetModel().
            if os_path.isfile((in_dir_name + "/dom_table.csv")) or os_path.isfile(
                (in_dir_name + "/dom_table.json")
            ):
                self.dom_coll.table_model.beginResetModel()
                if os_path.isfile((in_dir_name + "/dom_table.json")):
                    # noinspection PyTypeChecker
                    new_dom_coll_df = pd_read_json(
                        in_dir_name + "/dom_table.json",
                        orient="index",
                        dtype=DomCollection.entity_dict_types,
                    )
                else:
                    # noinspection PyTypeChecker
                    new_dom_coll_df = pd_read_csv(
                        in_dir_name + "/dom_table.csv",
                        encoding="utf-8",
                        dtype=DomCollection.entity_dict_types,
                        keep_default_na=False,
                    )

                # reindex new_dom_coll_df to catch any problem with non-consecutive indices
                new_dom_coll_df.reset_index(drop=True, inplace=True)

                if not new_dom_coll_df.empty:
                    # fix old projects with texture_uid column name
                    if "texture_uids" in new_dom_coll_df.columns:
                        new_dom_coll_df.rename(
                            columns={"texture_uids": "textures"}, inplace=True
                        )
                        self.print_terminal(
                            "column texture_uids renamed as textures in dom table"
                        )
                    if "texture_uid" in new_dom_coll_df.columns:
                        new_dom_coll_df.rename(
                            columns={"texture_uid": "textures"}, inplace=True
                        )
                        self.print_terminal(
                            "column texture_uid renamed as textures in dom table"
                        )
                    if "x_section" in new_dom_coll_df.columns:
                        new_dom_coll_df.rename(
                            columns={"x_section": "parent_uid"}, inplace=True
                        )
                        self.print_terminal(
                            "column x_section renamed as parent_uid in dom table"
                        )

                    if None in new_dom_coll_df["textures"].to_list():
                        new_dom_coll_df["textures"] = new_dom_coll_df["textures"].apply(
                            lambda x: [] if x is None else x
                        )
                        self.print_terminal(
                            "None value replaced with [] in textures column of dom table"
                        )

                    for new_column in new_dom_coll_df.columns.values.tolist():
                        if new_column not in self.dom_coll.df.columns.values.tolist():
                            new_dom_coll_df.drop(new_column, axis=1, inplace=True)
                            self.print_terminal(
                                f"column {new_column} removed from dom table"
                            )
                    for column in self.dom_coll.df.columns.values.tolist():
                        if column not in new_dom_coll_df.columns.values.tolist():
                            missing_column = pd_DataFrame(
                                [{column: self.dom_coll.entity_dict[column]}]
                                * len(new_dom_coll_df)
                            )
                            # concat with axis=1 to add the column, and ignore_index=False to keep
                            # the column names of the joined dataframes
                            new_dom_coll_df = pd_concat(
                                [new_dom_coll_df, missing_column],
                                ignore_index=False,
                                axis=1,
                            )
                            self.print_terminal(f"column {column} added to dom table")

                    # Remove duplicate columns if any (can occur when loading old projects)
                    new_dom_coll_df = new_dom_coll_df.loc[:, ~new_dom_coll_df.columns.duplicated()]

                    # reorder columns
                    new_dom_coll_df = new_dom_coll_df[self.dom_coll.df.columns]

                    self.dom_coll.df = new_dom_coll_df

                prgs_bar = progress_dialog(
                    max_value=self.dom_coll.df.shape[0],
                    title_txt="Open DOM",
                    label_txt="Opening DOM objects...",
                    cancel_txt=None,
                    parent=self,
                )
                for uid in self.dom_coll.df["uid"].to_list():
                    if self.dom_coll.get_uid_topology(uid) == "DEM":
                        if not os_path.isfile((in_dir_name + "/" + uid + ".vts")):
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
                        # Add code to read TSDOM here__________"""
                        vtk_object = TSDom()
                    elif (
                        self.dom_coll.df.loc[
                            self.dom_coll.df["uid"] == uid, "topology"
                        ].values[0]
                        == "PCDom"
                    ):
                        # Open saved PCDoms data
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
            if os_path.isfile((in_dir_name + "/image_table.csv")) or os_path.isfile(
                (in_dir_name + "/image_table.json")
            ):
                self.image_coll.table_model.beginResetModel()
                if os_path.isfile((in_dir_name + "/image_table.json")):
                    # noinspection PyTypeChecker
                    new_image_coll_df = pd_read_json(
                        in_dir_name + "/image_table.json",
                        orient="index",
                        dtype=ImageCollection.entity_dict_types,
                    )
                else:
                    # noinspection PyTypeChecker
                    new_image_coll_df = pd_read_csv(
                        in_dir_name + "/image_table.csv",
                        encoding="utf-8",
                        dtype=ImageCollection.entity_dict_types,
                        keep_default_na=False,
                    )

                # reindex new_dom_coll_df to catch any problem with non-consecutive indices
                new_image_coll_df.reset_index(drop=True, inplace=True)

                if not new_image_coll_df.empty:
                    if "x_section" in new_image_coll_df.columns:
                        new_image_coll_df.rename(
                            columns={"x_section": "parent_uid"}, inplace=True
                        )
                        self.print_terminal(
                            "column x_section renamed as parent_uid in image table"
                        )

                    for new_column in new_image_coll_df.columns.values.tolist():
                        if new_column not in self.image_coll.df.columns.values.tolist():
                            new_image_coll_df.drop(new_column, axis=1, inplace=True)
                            self.print_terminal(
                                f"column {new_column} removed from image table"
                            )
                    for column in self.image_coll.df.columns.values.tolist():
                        if column not in new_image_coll_df.columns.values.tolist():
                            missing_column = pd_DataFrame(
                                [{column: self.image_coll.entity_dict[column]}]
                                * len(new_image_coll_df)
                            )
                            # concat with axis=1 to add the column, and ignore_index=False to keep
                            # the column names of the joined dataframes
                            new_image_coll_df = pd_concat(
                                [new_image_coll_df, missing_column],
                                ignore_index=False,
                                axis=1,
                            )
                            self.print_terminal(f"column {column} added to image table")

                    # Remove duplicate columns if any (can occur when loading old projects)
                    new_image_coll_df = new_image_coll_df.loc[:, ~new_image_coll_df.columns.duplicated()]

                    # reorder columns
                    new_image_coll_df = new_image_coll_df[self.image_coll.df.columns]

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
                        if not os_path.isfile((in_dir_name + "/" + uid + ".vti")):
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
                        if not os_path.isfile((in_dir_name + "/" + uid + ".vti")):
                            print("error: missing image file")
                            return
                        vtk_object = XsImage(
                            parent=self,
                            x_section_uid=self.image_coll.df.loc[
                                self.image_coll.df["uid"] == uid, "parent_uid"
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
                        vtk_object = Seismics()
                        seismic_vts_path = in_dir_name + "/" + uid + ".vts"
                        seismic_metadata_path = (
                            in_dir_name + "/" + uid + "_seismic_metadata.json"
                        )

                        if os_path.isfile(seismic_vts_path):
                            sg_reader = vtkXMLStructuredGridReader()
                            sg_reader.SetFileName(seismic_vts_path)
                            sg_reader.Update()
                            vtk_object.ShallowCopy(sg_reader.GetOutput())
                        else:
                            source_file = None
                            if os_path.isfile(seismic_metadata_path):
                                try:
                                    with open(seismic_metadata_path, "r") as fin:
                                        seismic_metadata = json_load(fin)
                                    source_file = seismic_metadata.get("source_file")
                                except Exception:
                                    source_file = None
                            if not source_file:
                                try:
                                    source_file = self.image_coll.df.loc[
                                        self.image_coll.df["uid"] == uid,
                                        "seismic_source_file",
                                    ].values[0]
                                except Exception:
                                    source_file = None
                            if not source_file or not os_path.isfile(source_file):
                                print("error: missing seismic VTK file and source file")
                                return
                            vtk_object.ShallowCopy(read_segy_file(in_file_name=source_file))
                        vtk_object.Modified()
                    self.image_coll.set_uid_vtk_obj(uid=uid, vtk_obj=vtk_object)
                    prgs_bar.add_one()
                self.image_coll.table_model.endResetModel()

            # Read mesh3d collection and files.
            if os_path.isfile((in_dir_name + "/mesh3d_table.csv")) or os_path.isfile(
                (in_dir_name + "/mesh3d_table.json")
            ):
                self.mesh3d_coll.table_model.beginResetModel()
                if os_path.isfile((in_dir_name + "/mesh3d_table.json")):
                    # noinspection PyTypeChecker
                    new_mesh3d_coll_df = pd_read_json(
                        in_dir_name + "/mesh3d_table.json",
                        orient="index",
                        dtype=Mesh3DCollection.entity_dict_types,
                    )
                else:
                    # noinspection PyTypeChecker
                    new_mesh3d_coll_df = pd_read_csv(
                        in_dir_name + "/mesh3d_table.csv",
                        encoding="utf-8",
                        dtype=Mesh3DCollection.entity_dict_types,
                        keep_default_na=False,
                    )

                # reindex new_dom_coll_df to catch any problem with non-consecutive indices
                new_mesh3d_coll_df.reset_index(drop=True, inplace=True)

                if not new_mesh3d_coll_df.empty:
                    if "x_section" in new_mesh3d_coll_df.columns:
                        new_mesh3d_coll_df.rename(
                            columns={"x_section": "parent_uid"}, inplace=True
                        )
                        self.print_terminal(
                            "column x_section renamed as parent_uid in mesh3d table"
                        )

                    for new_column in new_mesh3d_coll_df.columns.values.tolist():
                        if (
                            new_column
                            not in self.mesh3d_coll.df.columns.values.tolist()
                        ):
                            new_mesh3d_coll_df.drop(new_column, axis=1, inplace=True)
                            self.print_terminal(
                                f"column {new_column} removed from mesh3d table"
                            )
                    for column in self.mesh3d_coll.df.columns.values.tolist():
                        if column not in new_mesh3d_coll_df.columns.values.tolist():
                            missing_column = pd_DataFrame(
                                [{column: self.mesh3d_coll.entity_dict[column]}]
                                * len(new_mesh3d_coll_df)
                            )
                            # concat with axis=1 to add the column, and ignore_index=False to keep
                            # the column names of the joined dataframes
                            new_mesh3d_coll_df = pd_concat(
                                [new_mesh3d_coll_df, missing_column],
                                ignore_index=False,
                                axis=1,
                            )
                            self.print_terminal(
                                f"column {column} added to mesh3d table"
                            )

                    # Remove duplicate columns if any (can occur when loading old projects)
                    new_mesh3d_coll_df = new_mesh3d_coll_df.loc[:, ~new_mesh3d_coll_df.columns.duplicated()]

                    # reorder columns
                    new_mesh3d_coll_df = new_mesh3d_coll_df[self.mesh3d_coll.df.columns]

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
                        if not os_path.isfile((in_dir_name + "/" + uid + ".vti")):
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
                        if not os_path.isfile((in_dir_name + "/" + uid + ".vti")):
                            print("error: missing .mesh3d file")
                            return
                        vtk_object = XsVoxet(
                            x_section_uid=self.mesh3d_coll.df.loc[
                                self.mesh3d_coll.df["uid"] == uid, "parent_uid"
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
            if os_path.isfile((in_dir_name + "/boundary_table.csv")) or os_path.isfile(
                (in_dir_name + "/boundary_table.json")
            ):
                self.boundary_coll.table_model.beginResetModel()
                if os_path.isfile((in_dir_name + "/boundary_table.json")):
                    # noinspection PyTypeChecker
                    new_boundary_coll_df = pd_read_json(
                        in_dir_name + "/boundary_table.json",
                        orient="index",
                        dtype=BoundaryCollection.entity_dict_types,
                    )
                else:
                    # noinspection PyTypeChecker
                    new_boundary_coll_df = pd_read_csv(
                        in_dir_name + "/boundary_table.csv",
                        encoding="utf-8",
                        dtype=BoundaryCollection.entity_dict_types,
                        keep_default_na=False,
                    )

                # reindex new_dom_coll_df to catch any problem with non-consecutive indices
                new_boundary_coll_df.reset_index(drop=True, inplace=True)

                if not new_boundary_coll_df.empty:
                    if "x_section" in new_boundary_coll_df.columns:
                        new_boundary_coll_df.rename(
                            columns={"x_section": "parent_uid"}, inplace=True
                        )
                        self.print_terminal(
                            "column x_section renamed as parent_uid in boundary table"
                        )

                    for new_column in new_boundary_coll_df.columns.values.tolist():
                        if (
                            new_column
                            not in self.boundary_coll.df.columns.values.tolist()
                        ):
                            new_boundary_coll_df.drop(new_column, axis=1, inplace=True)
                            self.print_terminal(
                                f"column {new_column} removed from boundary table"
                            )
                    for column in self.boundary_coll.df.columns.values.tolist():
                        if column not in new_boundary_coll_df.columns.values.tolist():
                            missing_column = pd_DataFrame(
                                [{column: self.boundary_coll.entity_dict[column]}]
                                * len(new_boundary_coll_df)
                            )
                            # concat with axis=1 to add the column, and ignore_index=False to keep
                            # the column names of the joined dataframes
                            new_boundary_coll_df = pd_concat(
                                [new_boundary_coll_df, missing_column],
                                ignore_index=False,
                                axis=1,
                            )
                            self.print_terminal(
                                f"column {column} added to boundary table"
                            )

                    # Remove duplicate columns if any (can occur when loading old projects)
                    new_boundary_coll_df = new_boundary_coll_df.loc[:, ~new_boundary_coll_df.columns.duplicated()]

                    # reorder columns
                    new_boundary_coll_df = new_boundary_coll_df[
                        self.boundary_coll.df.columns
                    ]

                    self.boundary_coll.df = new_boundary_coll_df

                prgs_bar = progress_dialog(
                    max_value=self.boundary_coll.df.shape[0],
                    title_txt="Open boundary",
                    label_txt="Opening boundary objects...",
                    cancel_txt=None,
                    parent=self,
                )
                for uid in self.boundary_coll.df["uid"].to_list():
                    if not os_path.isfile((in_dir_name + "/" + uid + ".vtp")):
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
            if os_path.isfile((in_dir_name + "/well_table.csv")) or os_path.isfile(
                (in_dir_name + "/well_table.json")
            ):
                self.well_coll.table_model.beginResetModel()
                if os_path.isfile((in_dir_name + "/well_table.json")):
                    # noinspection PyTypeChecker
                    new_well_coll_df = pd_read_json(
                        in_dir_name + "/well_table.json",
                        orient="index",
                        dtype=WellCollection.entity_dict_types,
                    )
                else:
                    # noinspection PyTypeChecker
                    new_well_coll_df = pd_read_csv(
                        in_dir_name + "/well_table.csv",
                        encoding="utf-8",
                        dtype=WellCollection.entity_dict_types,
                        keep_default_na=False,
                    )

                # reindex new_dom_coll_df to catch any problem with non-consecutive indices
                new_well_coll_df.reset_index(drop=True, inplace=True)

                if not new_well_coll_df.empty:
                    if "x_section" in new_well_coll_df.columns:
                        new_well_coll_df.rename(
                            columns={"x_section": "parent_uid"}, inplace=True
                        )
                        self.print_terminal(
                            "column x_section renamed as parent_uid in wells table"
                        )

                    for new_column in new_well_coll_df.columns.values.tolist():
                        if new_column not in self.well_coll.df.columns.values.tolist():
                            new_well_coll_df.drop(new_column, axis=1, inplace=True)
                            self.print_terminal(
                                f"column {new_column} removed from wells table"
                            )
                    for column in self.well_coll.df.columns.values.tolist():
                        if column not in new_well_coll_df.columns.values.tolist():
                            missing_column = pd_DataFrame(
                                [{column: self.well_coll.entity_dict[column]}]
                                * len(new_well_coll_df)
                            )
                            # concat with axis=1 to add the column, and ignore_index=False to keep
                            # the column names of the joined dataframes
                            new_well_coll_df = pd_concat(
                                [new_well_coll_df, missing_column],
                                ignore_index=False,
                                axis=1,
                            )
                            self.print_terminal(f"column {column} added to wells table")

                    # Remove duplicate columns if any (can occur when loading old projects)
                    new_well_coll_df = new_well_coll_df.loc[:, ~new_well_coll_df.columns.duplicated()]

                    # reorder columns
                    new_well_coll_df = new_well_coll_df[self.well_coll.df.columns]

                    self.well_coll.df = new_well_coll_df

                prgs_bar = progress_dialog(
                    max_value=self.well_coll.df.shape[0],
                    title_txt="Open wells",
                    label_txt="Opening well objects...",
                    cancel_txt=None,
                    parent=self,
                )
                for uid in self.well_coll.df["uid"].to_list():
                    if not os_path.isfile((in_dir_name + "/" + uid + ".vtp")):
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
            if os_path.isfile(
                (in_dir_name + "/geological_table.csv")
            ) or os_path.isfile((in_dir_name + "/geological_table.json")):
                self.geol_coll.table_model.beginResetModel()
                if os_path.isfile((in_dir_name + "/geological_table.json")):
                    # noinspection PyTypeChecker
                    new_geol_coll_df = pd_read_json(
                        in_dir_name + "/geological_table.json",
                        orient="index",
                        dtype=GeologicalCollection.entity_dict_types,
                    )
                else:
                    # noinspection PyTypeChecker
                    new_geol_coll_df = pd_read_csv(
                        in_dir_name + "/geological_table.csv",
                        encoding="utf-8",
                        dtype=GeologicalCollection.entity_dict_types,
                        keep_default_na=False,
                    )

                # reindex new_dom_coll_df to catch any problem with non-consecutive indices
                new_geol_coll_df.reset_index(drop=True, inplace=True)

                if not new_geol_coll_df.empty:
                    if "x_section" in new_geol_coll_df.columns:
                        new_geol_coll_df.rename(
                            columns={"x_section": "parent_uid"}, inplace=True
                        )
                        self.print_terminal(
                            "column x_section renamed as parent_uid in geology table"
                        )

                    for new_column in new_geol_coll_df.columns.values.tolist():
                        if new_column not in self.geol_coll.df.columns.values.tolist():
                            new_geol_coll_df.drop(new_column, axis=1, inplace=True)
                            self.print_terminal(
                                f"column {new_column} removed from geology table"
                            )
                    for column in self.geol_coll.df.columns.values.tolist():
                        if column not in new_geol_coll_df.columns.values.tolist():
                            missing_column = pd_DataFrame(
                                [{column: self.geol_coll.entity_dict[column]}]
                                * len(new_geol_coll_df)
                            )
                            # concat with axis=1 to add the column, and ignore_index=False to keep
                            # the column names of the joined dataframes
                            new_geol_coll_df = pd_concat(
                                [new_geol_coll_df, missing_column],
                                ignore_index=False,
                                axis=1,
                            )
                            self.print_terminal(
                                f"column {column} added to geology table"
                            )

                    # Remove duplicate columns if any (can occur when loading old projects)
                    new_geol_coll_df = new_geol_coll_df.loc[:, ~new_geol_coll_df.columns.duplicated()]

                    # reorder columns
                    new_geol_coll_df = new_geol_coll_df[self.geol_coll.df.columns]

                    self.geol_coll.df = new_geol_coll_df

                prgs_bar = progress_dialog(
                    max_value=self.geol_coll.df.shape[0],
                    title_txt="Open geology",
                    label_txt="Opening geological objects...",
                    cancel_txt=None,
                    parent=self,
                )
                for uid in self.geol_coll.df["uid"].to_list():
                    if not os_path.isfile((in_dir_name + "/" + uid + ".vtp")):
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
            if os_path.isfile((in_dir_name + "/fluids_table.csv")) or os_path.isfile(
                (in_dir_name + "/fluids_table.json")
            ):
                self.fluid_coll.table_model.beginResetModel()
                if os_path.isfile((in_dir_name + "/fluids_table.json")):
                    # noinspection PyTypeChecker
                    new_fluids_coll_df = pd_read_json(
                        in_dir_name + "/fluids_table.json",
                        orient="index",
                        dtype=FluidCollection.entity_dict_types,
                    )
                else:
                    # noinspection PyTypeChecker
                    new_fluids_coll_df = pd_read_csv(
                        in_dir_name + "/fluids_table.csv",
                        encoding="utf-8",
                        dtype=FluidCollection.entity_dict_types,
                        keep_default_na=False,
                    )

                # reindex new_dom_coll_df to catch any problem with non-consecutive indices
                new_fluids_coll_df.reset_index(drop=True, inplace=True)

                if not new_fluids_coll_df.empty:
                    if "x_section" in new_fluids_coll_df.columns:
                        new_fluids_coll_df.rename(
                            columns={"x_section": "parent_uid"}, inplace=True
                        )
                        self.print_terminal(
                            "column x_section renamed as parent_uid in fluids table"
                        )

                    for new_column in new_fluids_coll_df.columns.values.tolist():
                        if new_column not in self.fluid_coll.df.columns.values.tolist():
                            new_fluids_coll_df.drop(new_column, axis=1, inplace=True)
                            self.print_terminal(
                                f"column {new_column} removed from fluids table"
                            )
                    for column in self.fluid_coll.df.columns.values.tolist():
                        if column not in new_fluids_coll_df.columns.values.tolist():
                            missing_column = pd_DataFrame(
                                [{column: self.fluid_coll.entity_dict[column]}]
                                * len(new_fluids_coll_df)
                            )
                            # concat with axis=1 to add the column, and ignore_index=False to keep
                            # the column names of the joined dataframes
                            new_fluids_coll_df = pd_concat(
                                [new_fluids_coll_df, missing_column],
                                ignore_index=False,
                                axis=1,
                            )
                            self.print_terminal(
                                f"column {column} added to fluids table"
                            )

                    # Remove duplicate columns if any (can occur when loading old projects)
                    new_fluids_coll_df = new_fluids_coll_df.loc[:, ~new_fluids_coll_df.columns.duplicated()]

                    # reorder columns
                    new_fluids_coll_df = new_fluids_coll_df[self.fluid_coll.df.columns]

                    self.fluid_coll.df = new_fluids_coll_df

                prgs_bar = progress_dialog(
                    max_value=self.fluid_coll.df.shape[0],
                    title_txt="Open fluids",
                    label_txt="Opening fluid objects...",
                    cancel_txt=None,
                    parent=self,
                )
                for uid in self.fluid_coll.df["uid"].to_list():
                    if not os_path.isfile((in_dir_name + "/" + uid + ".vtp")):
                        print("error: missing VTK file")
                        return
                    if self.fluid_coll.get_uid_topology(uid) == "VertexSet":
                        vtk_object = VertexSet()
                    elif self.fluid_coll.get_uid_topology(uid) == "PolyLine":
                        vtk_object = PolyLine()
                    elif self.fluid_coll.get_uid_topology(uid) == "TriSurf":
                        vtk_object = TriSurf()
                    elif self.fluid_coll.get_uid_topology(uid) == "XsVertexSet":
                        vtk_object = XsVertexSet(
                            self.fluid_coll.get_uid_x_section(uid), parent=self
                        )
                    elif self.fluid_coll.get_uid_topology(uid) == "XsPolyLine":
                        vtk_object = XsPolyLine(
                            self.fluid_coll.get_uid_x_section(uid), parent=self
                        )
                    pd_reader = vtkXMLPolyDataReader()
                    pd_reader.SetFileName(in_dir_name + "/" + uid + ".vtp")
                    pd_reader.Update()
                    vtk_object.ShallowCopy(pd_reader.GetOutput())
                    vtk_object.Modified()
                    self.fluid_coll.set_uid_vtk_obj(uid=uid, vtk_obj=vtk_object)
                    prgs_bar.add_one()
                self.fluid_coll.table_model.endResetModel()
            # Update legend.
            self.prop_legend.update_widget(parent=self)

            # Read Backgrounds table and files."""
            if os_path.isfile(
                (in_dir_name + "/backgrounds_table.csv")
            ) or os_path.isfile((in_dir_name + "/backgrounds_table.json")):
                self.backgrnd_coll.table_model.beginResetModel()
                if os_path.isfile((in_dir_name + "/backgrounds_table.json")):
                    # noinspection PyTypeChecker
                    new_backgrounds_coll_df = pd_read_json(
                        in_dir_name + "/backgrounds_table.json",
                        orient="index",
                        dtype=FluidCollection.entity_dict_types,
                    )
                else:
                    # noinspection PyTypeChecker
                    new_backgrounds_coll_df = pd_read_csv(
                        in_dir_name + "/backgrounds_table.csv",
                        encoding="utf-8",
                        dtype=FluidCollection.entity_dict_types,
                        keep_default_na=False,
                    )

                # reindex new_dom_coll_df to catch any problem with non-consecutive indices
                new_backgrounds_coll_df.reset_index(drop=True, inplace=True)

                if not new_backgrounds_coll_df.empty:
                    if "x_section" in new_backgrounds_coll_df.columns:
                        new_backgrounds_coll_df.rename(
                            columns={"x_section": "parent_uid"}, inplace=True
                        )
                        self.print_terminal(
                            "column x_section renamed as parent_uid in background table"
                        )

                    for new_column in new_backgrounds_coll_df.columns.values.tolist():
                        if (
                            new_column
                            not in self.backgrnd_coll.df.columns.values.tolist()
                        ):
                            new_backgrounds_coll_df.drop(
                                new_column, axis=1, inplace=True
                            )
                            self.print_terminal(
                                f"column {new_column} removed from background table"
                            )
                    for column in self.backgrnd_coll.df.columns.values.tolist():
                        if (
                            column
                            not in new_backgrounds_coll_df.columns.values.tolist()
                        ):
                            missing_column = pd_DataFrame(
                                [{column: self.backgrnd_coll.entity_dict[column]}]
                                * len(new_backgrounds_coll_df)
                            )
                            # concat with axis=1 to add the column, and ignore_index=False to keep
                            # the column names of the joined dataframes
                            new_backgrounds_coll_df = pd_concat(
                                [new_backgrounds_coll_df, missing_column],
                                ignore_index=False,
                                axis=1,
                            )
                            self.print_terminal(
                                f"column {column} added to background table"
                            )

                    # Remove duplicate columns if any (can occur when loading old projects)
                    new_backgrounds_coll_df = new_backgrounds_coll_df.loc[:, ~new_backgrounds_coll_df.columns.duplicated()]

                    # reorder columns
                    new_backgrounds_coll_df = new_backgrounds_coll_df[
                        self.backgrnd_coll.df.columns
                    ]

                    self.backgrnd_coll.df = new_backgrounds_coll_df

                prgs_bar = progress_dialog(
                    max_value=self.backgrnd_coll.df.shape[0],
                    title_txt="Open fluids",
                    label_txt="Opening fluid objects...",
                    cancel_txt=None,
                    parent=self,
                )
                for uid in self.backgrnd_coll.df["uid"].to_list():
                    if not os_path.isfile((in_dir_name + "/" + uid + ".vtp")):
                        print("error: missing VTK file")
                        return
                    if self.backgrnd_coll.get_uid_topology(uid) == "VertexSet":
                        vtk_object = VertexSet()
                    elif self.backgrnd_coll.get_uid_topology(uid) == "PolyLine":
                        vtk_object = PolyLine()
                    elif self.backgrnd_coll.get_uid_topology(uid) == "TriSurf":
                        vtk_object = TriSurf()
                    elif self.backgrnd_coll.get_uid_topology(uid) == "XsVertexSet":
                        vtk_object = XsVertexSet(
                            self.backgrnd_coll.get_uid_x_section(uid), parent=self
                        )
                    elif self.backgrnd_coll.get_uid_topology(uid) == "XsPolyLine":
                        vtk_object = XsPolyLine(
                            self.backgrnd_coll.get_uid_x_section(uid), parent=self
                        )
                    pd_reader = vtkXMLPolyDataReader()
                    pd_reader.SetFileName(in_dir_name + "/" + uid + ".vtp")
                    pd_reader.Update()
                    vtk_object.ShallowCopy(pd_reader.GetOutput())
                    vtk_object.Modified()
                    self.backgrnd_coll.set_uid_vtk_obj(uid=uid, vtk_obj=vtk_object)
                    prgs_bar.add_one()
                self.backgrnd_coll.table_model.endResetModel()
            # Update legend.
            self.prop_legend.update_widget(parent=self)
            self.load_custom_tables(in_dir_name=in_dir_name)


        except BaseException as e:
            # Get current system exception
            import sys
            import traceback

            ex_type, ex_value, ex_traceback = sys.exc_info()

            # Extract unformatter stack traces as tuples
            trace_back = traceback.extract_tb(ex_traceback)

            # Format stacktrace
            stack_trace = list()

            for trace in trace_back:
                stack_trace.append(
                    "File : %s , Line : %d, Func.Name : %s, Message : %s" % (trace[0], trace[1], trace[2], trace[3]))

            print("Exception type : %s " % ex_type.__name__)
            print("Exception message : %s" % ex_value)
            print("Stack trace : %s" % stack_trace)

            self.print_terminal("Error - tried to open invalid project.")

    # ---- Methods used to import entities from other file formats. ----

    def import_gocad(self):
        """Import Gocad ASCII file and update geological collection."""
        self.print_terminal("Importing Gocad ASCII format")
        self.print_terminal(
            "Properties are discarded if they are not 1D, 2D, 3D, 4D, 6D or 9D (due to VTK limitations)"
        )
        # Select and open input file
        in_file_name = open_file_dialog(
            parent=self,
            caption="Import entities from Gocad ASCII file",
            filter="Gocad ASCII (*.*)",
        )
        if in_file_name:
            self.print_terminal("in_file_name: " + in_file_name)
            gocad2vtk(self=self, in_file_name=in_file_name, uid_from_name=False)
            self.prop_legend.update_widget(parent=self)

    def import_gocad_sections(self):
        """Import cross-section saved as Gocad ASCII file and update geological collection."""
        self.print_terminal("Importing Gocad ASCII format")
        self.print_terminal(
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
            parent=None,
            title="Scenario",
            label="Default scenario",
            default_text="undef",
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
            reject_role=None,
        )
        # Process files.
        for in_file_name in in_file_names:
            self.print_terminal("in_file_name: " + in_file_name)
            # Get x-section name from file.
            x_section_name = os_path.splitext(os_path.basename(in_file_name))[0]
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
                x_section_uid = self.xsect_coll.add_entity_from_dict(
                    entity_dict=section_dict
                )
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
        self.print_terminal("Importing Gocad ASCII format as boundary")
        self.print_terminal("Properties are discarded - only mesh imported.")
        # Select and open input file
        in_file_name = open_file_dialog(
            parent=self,
            caption="Import entities from Gocad ASCII file",
            filter="Gocad ASCII (*.*)",
        )
        if in_file_name:
            self.print_terminal("in_file_name: " + in_file_name)
            gocad2vtk_boundary(
                self=self,
                in_file_name=in_file_name,
                uid_from_name=False,
            )

    def import_sections(self):
        """Import section traces from different kinds of files."""
        # sections_from_file(self)
        pass

    def _install_import_xyz_action(self):
        """Add the generic XYZ import action to the File menu."""
        self.actionImportXYZ = QAction("Import XYZ", self)
        self.actionImportXYZ.setObjectName("actionImportXYZ")
        self.actionImportXYZ.setStatusTip(
            "Import multiple XYZ-like point files as VertexSet entities"
        )
        self.menuFile.insertAction(self.actionImportPC, self.actionImportXYZ)

    def _install_import_table_action(self):
        """Add the generic table import action to the File menu."""
        self.actionImportTable = QAction("Import Tables", self)
        self.actionImportTable.setObjectName("actionImportTable")
        self.actionImportTable.setStatusTip(
            "Import generic text tables into custom project tables"
        )
        self.menuFile.insertAction(self.actionImportPC, self.actionImportTable)

    def import_XYZ(self):
        """Import multiple generic XYZ point files into a selected collection."""
        self.print_terminal("Importing generic XYZ points")
        in_file_names = open_files_dialog(
            parent=self,
            caption="Import XYZ points from file(s)",
            filter=(
                "Supported XYZ files (*.csv *.dat *.txt *.xyz *.asc *.vtu *.vtk *.vtp);;"
                "Text files (*.csv *.dat *.txt *.xyz *.asc);;"
                "VTK files (*.vtu *.vtk *.vtp)"
            ),
        )
        if not in_file_names:
            return

        collection_name = input_combo_dialog(
            parent=self,
            title="Collection",
            label="Assign collection",
            choice_list=["Geology", "Fluid contacts", "Background data"],
        )
        if not collection_name:
            return

        xyz2vtk(
            self=self,
            in_file_names=in_file_names,
            collection_name=collection_name,
        )

    def import_tables(self):
        """Import generic tabular files into custom project tables."""
        self.print_terminal("Importing generic tables")
        import_tables(self=self)

    def refresh_table_views(self):
        """Refresh any open custom table views."""
        for child in self.findChildren(QWidget):
            if hasattr(child, "refresh_table_list") and callable(
                getattr(child, "refresh_table_list")
            ):
                try:
                    child.refresh_table_list()
                except Exception:
                    pass

    def get_structural_topology_legend_units(self):
        """Return STm-ready units derived from the geological legend."""
        legend_df = getattr(self.geol_coll, "legend_df", pd_DataFrame())
        if legend_df is None or legend_df.empty:
            return []

        units_map = {}
        for _, row in legend_df.iterrows():
            feature_name = str(row.get("feature", "")).strip()
            role_name = str(row.get("role", "")).strip()
            unit_name = f"{feature_name}_{role_name}".strip("_")
            if not unit_name or unit_name in units_map:
                continue
            units_map[unit_name] = {
                "Name": unit_name,
                "Unit": "NonVolumetric",
                "Representative Surfaces": "No",
                "Structural Polarity": row.get("time", 0.0),
                "Domain_1": "",
                "feature": feature_name,
                "role": role_name,
                "color_R": row.get("color_R", 255),
                "color_G": row.get("color_G", 255),
                "color_B": row.get("color_B", 255),
            }

        return sorted(
            units_map.values(),
            key=lambda unit_info: str(unit_info.get("Name", "")).casefold(),
        )

    def sync_structural_topology_table_to_legend(self, table_name=None):
        """Push structural polarity values from one STm table into the geology legend."""
        if not table_name:
            return
        if self.custom_table_types.get(table_name) != "stm":
            return

        legend_df = getattr(self.geol_coll, "legend_df", pd_DataFrame())
        table_df = self.custom_tables.get(table_name, pd_DataFrame())
        if (
            legend_df is None
            or legend_df.empty
            or table_df is None
            or table_df.empty
            or "Name" not in table_df.columns
            or "Structural Polarity" not in table_df.columns
        ):
            return

        legend_names = (
            legend_df["feature"].astype(str).str.strip()
            + "_"
            + legend_df["role"].astype(str).str.strip()
        )
        legend_updated = False
        for _, row in table_df.iterrows():
            stm_name = str(row.get("Name", "")).strip()
            if not stm_name:
                continue
            try:
                polarity_value = float(row.get("Structural Polarity", ""))
            except (TypeError, ValueError):
                continue

            mask = legend_names == stm_name
            if not mask.any():
                continue
            self.geol_coll.legend_df.loc[mask, "time"] = polarity_value
            legend_updated = True

        if legend_updated:
            self.geol_coll.legend_df.sort_values(
                by="time", ascending=True, inplace=True
            )
            if hasattr(self, "legend"):
                self.legend.update_widget(parent=self)

    def sync_structural_topology_tables_from_legend(self):
        """Refresh all STm table polarities from the geology legend."""
        legend_units = self.get_structural_topology_legend_units()
        if not legend_units:
            return

        polarity_map = {
            unit_info["Name"]: unit_info.get("Structural Polarity", "")
            for unit_info in legend_units
        }
        tables_updated = False

        for table_name, table_df in self.custom_tables.items():
            if self.custom_table_types.get(table_name) != "stm":
                continue
            if table_df is None:
                continue

            if "Domain" in table_df.columns and "Domain_1" not in table_df.columns:
                table_df.rename(columns={"Domain": "Domain_1"}, inplace=True)
            if "Name" not in table_df.columns:
                table_df["Name"] = ""
            if "Unit" not in table_df.columns:
                table_df["Unit"] = "NonVolumetric"
            if "Representative Surfaces" not in table_df.columns:
                table_df["Representative Surfaces"] = "No"
            if "Structural Polarity" not in table_df.columns:
                table_df["Structural Polarity"] = ""
            if not any(str(column).startswith("Domain") for column in table_df.columns):
                table_df["Domain_1"] = ""

            for row_idx in range(table_df.shape[0]):
                stm_name = str(table_df.at[row_idx, "Name"]).strip()
                if stm_name in polarity_map:
                    table_df.at[row_idx, "Structural Polarity"] = polarity_map[stm_name]
            tables_updated = True

        if tables_updated:
            self.refresh_table_views()

    def refresh_custom_colormaps(self):
        """Register project colormaps stored as advanced tables and refresh the legend widget."""
        if hasattr(self, "prop_legend"):
            PropertiesCMaps.register_custom_colormaps(parent=self)
            self.prop_legend.update_widget(parent=self)

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

        args = import_dialog(
            self,
            default_attr_list=default_attr_list,
            ext_filter=ext_filter,
            caption="Import point cloud data",
        ).args
        if args:
            in_file_name, col_names, row_range, index_list, delimiter, origin = args
            self.print_terminal("in_file_name: " + in_file_name)
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
        self.print_terminal("Importing SHP file")
        list = ["Geology", "Fluid contacts", "Background data"]
        # Select and open input file
        in_file_name = open_file_dialog(
            parent=self, caption="Import SHP file", filter="shp (*.shp)"
        )
        coll = input_combo_dialog(
            parent=self, title="Collection", label="Assign collection", choice_list=list
        )
        if in_file_name:
            self.print_terminal("in_file_name: " + in_file_name)
            shp2vtk(self=self, in_file_name=in_file_name, collection=coll)

    def import_DEM(self):
        """Import DEM file and update DEM collection."""
        self.print_terminal("Importing DEM in supported format (geotiff)")
        list = ["DEMs and DOMs", "Fluid contacts"]

        # Select and open input file
        in_file_name = open_file_dialog(
            parent=self, caption="Import DEM from file", filter="Geotiff (*.tif)"
        )
        coll = input_combo_dialog(
            parent=self, title="Collection", label="Assign collection", choice_list=list
        )
        if in_file_name:
            self.print_terminal("in_file_name: " + in_file_name)
            dem2vtk(self=self, in_file_name=in_file_name, collection="DEMs and DOMs")

    def import_mapimage(self):
        """Import map image and update image collection."""
        self.print_terminal("Importing image from supported format (GDAL)")
        # Select and open input file
        in_file_name = open_file_dialog(
            parent=self,
            caption="Import image from file",
            filter="Image (*.tif *.jpg *.png *.bmp)",
        )
        if in_file_name:
            self.print_terminal("in_file_name: " + in_file_name)
            geo_image2vtk(self=self, in_file_name=in_file_name)

    def import_xsimage(self):
        """Import XSimage and update image collection."""
        self.print_terminal("Importing image from supported format (GDAL)")
        # Select and open input file
        in_file_name = open_file_dialog(
            parent=self,
            caption="Import image from file",
            filter="Image (*.tif *.jpg *.png *.bmp)",
        )
        if in_file_name:
            self.print_terminal("in_file_name: " + in_file_name)
            # Select the Xsection
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
        paths = open_files_dialog(
            parent=self, caption="Import well data", filter="XLXS files (*.xlsx)"
        )

        if not paths:
            return

        imported_paths = []
        skipped_paths = []

        for path in paths:
            self.print_terminal("in_file_name: " + path)
            try:
                well2vtk(self, path=path)
                imported_paths.append(path)
            except Exception as exc:
                skipped_paths.append(path)

        if imported_paths:
            self.prop_legend.update_widget(parent=self)
            self.print_terminal(
                f"Imported {len(imported_paths)} well file(s) successfully."
            )

        if skipped_paths:
            self.print_terminal(
                f"Rejected {len(skipped_paths)} incompatible well file(s)."
            )

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
        #     # self.print_terminal('in_file_name: ' + in_file_name)
        #     well2vtk(in_file_name=in_file_name, col_names=col_names, usecols=index_list, delimiter=delimiter, self=self, header_row=0)

    def import_SEGY(self):
        # ___________________________________________________________ TO BE REVIEWED AND UPDATED IN MODULE segy2vtk
        """Import SEGY file and update Mesh3D collection."""
        self.print_terminal("Importing SEGY seismics file.")
        # Select and open input file
        in_file_name = open_file_dialog(
            parent=self, caption="Import SEGY from file", filter="SEGY (*.sgy *.segy)"
        )
        if in_file_name:
            self.print_terminal("in_file_name: " + in_file_name)
            segy2vtk(self=self, in_file_name=in_file_name)

    # Methods used to export entities to other file formats.

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
        self.print_terminal(("Saving CAD surfaces in folder: " + out_dir_name))
        # Create the folder if it does not exist already.
        if not os_path.isdir(out_dir_name):
            os_mkdir(out_dir_name)
        if cad_format == "DXF":
            print("is DXF")
            os_mkdir(f"{out_dir_name}/csv")
            os_mkdir(f"{out_dir_name}/dxf")
            vtk2dxf(self=self, out_dir_name=out_dir_name)
        elif cad_format == "GOCAD":
            if not self.selected_uids:
                return
            else:
                vtk2gocad(self=self, out_file_name=(out_dir_name + "/gocad_ascii.gp"))
        elif cad_format == "GLTF":
            vtk2gltf(self=self, out_dir_name=out_dir_name)
        elif cad_format == "CESIUM":
            vtk2cesium(self=self, out_dir_name=out_dir_name)
        elif cad_format == "OBJ":
            if not self.selected_uids:
                return
            else:
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
        # Save geological legend table to CSV and JSON files.
        self.geol_coll.legend_df.to_csv(
            out_dir_name + "/geol_legend_table.csv", encoding="utf-8", index=False
        )
        self.geol_coll.legend_df.to_json(
            out_dir_name + "/geol_legend_table.json", orient="index"
        )
        # Save others legend table to CSV and JSON files.
        self.others_legend_df.to_csv(
            out_dir_name + "/others_legend_table.csv", encoding="utf-8", index=False
        )
        self.others_legend_df.to_json(
            out_dir_name + "/others_legend_table.json", orient="index"
        )
        # Save x-section table to CSV and JSON files.
        out_cols = list(self.xsect_coll.df.columns)
        out_cols.remove("vtk_plane")
        out_cols.remove("vtk_frame")
        self.xsect_coll.df[out_cols].to_csv(
            out_dir_name + "/xsection_table.csv", encoding="utf-8", index=False
        )
        self.xsect_coll.df[out_cols].to_json(
            out_dir_name + "/xsection_table.json", orient="index"
        )
        # Save geological collection table to CSV and JSON files.
        out_cols = list(self.geol_coll.df.columns)
        out_cols.remove("vtk_obj")
        self.geol_coll.df[out_cols].to_csv(
            out_dir_name + "/geological_table.csv", encoding="utf-8", index=False
        )
        self.geol_coll.df[out_cols].to_json(
            out_dir_name + "/geological_table.json", orient="index"
        )
        # Save DOM collection table to CSV and JSON files.
        out_cols = list(self.dom_coll.df.columns)
        out_cols.remove("vtk_obj")
        self.dom_coll.df[out_cols].to_csv(
            out_dir_name + "/dom_table.csv", encoding="utf-8", index=False
        )
        self.dom_coll.df[out_cols].to_json(
            out_dir_name + "/dom_table.json", orient="index"
        )
        # Save image collection table to CSV and JSON files.
        out_cols = list(self.image_coll.df.columns)
        out_cols.remove("vtk_obj")
        self.image_coll.df[out_cols].to_csv(
            out_dir_name + "/image_table.csv", encoding="utf-8", index=False
        )
        self.image_coll.df[out_cols].to_json(
            out_dir_name + "/image_table.json", orient="index"
        )
        # Save mesh3d collection table to CSV and JSON files.
        out_cols = list(self.mesh3d_coll.df.columns)
        out_cols.remove("vtk_obj")
        self.mesh3d_coll.df[out_cols].to_csv(
            out_dir_name + "/mesh3d_table.csv", encoding="utf-8", index=False
        )
        self.mesh3d_coll.df[out_cols].to_json(
            out_dir_name + "/mesh3d_table.json", orient="index"
        )
        # Save boundary collection table to CSV and JSON files.
        out_cols = list(self.boundary_coll.df.columns)
        out_cols.remove("vtk_obj")
        self.boundary_coll.df[out_cols].to_csv(
            out_dir_name + "/boundary_table.csv", encoding="utf-8", index=False
        )
        self.boundary_coll.df[out_cols].to_json(
            out_dir_name + "/boundary_table.json", orient="index"
        )

        # Save well collection table to CSV and JSON files.
        out_cols = list(self.well_coll.df.columns)
        out_cols.remove("vtk_obj")
        self.well_coll.df[out_cols].to_json(
            out_dir_name + "/well_table.json", orient="index"
        )
        self.well_coll.df[out_cols].to_csv(
            out_dir_name + "/well_table.csv", encoding="utf-8", index=False
        )
        self.print_terminal("All files saved.")

    def export_vtk(self):
        """Function used to export selected objects as vtk files"""
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
            ):  #  this could be generalized with a helper function
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
                elif self.shown_table == "tabMeshes":
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
            ):  #  this could be generalized with a helper function
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
                                df["dip dir"] = entity.points_map_dip_direction
                                df["dip"] = entity.points_map_dip
                            if data.ndim == 1:
                                df[key] = data
                            else:
                                for i in range(data.ndim):
                                    df[f"{key}_{i}"] = data[:, i]

                    df.to_csv(f"{self.out_dir_name}/{uid}.csv")
                else:
                    print("Only geology objects are supported")
