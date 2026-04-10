"""view_3d.py
PZero© Andrea Bistacchi"""

# General Python imports____
from copy import deepcopy
from shutil import make_archive, rmtree
from uuid import uuid4

# PySide6 imports____
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu

# Numpy imports____
from numpy import append as np_append
from numpy import array as np_array
from numpy import linspace as np_linspace
from numpy import argmin as np_argmin
from numpy import argmax as np_argmax
from numpy import mean as np_mean
from numpy import asarray as np_asarray
from numpy import linalg as np_linalg
from numpy import max as np_max
from numpy import min as np_min
from numpy import sum as np_sum
from numpy import diff as np_diff
from numpy import zeros as np_zeros
from numpy import vstack as np_vstack
from numpy import empty as np_empty
from numpy import ones as np_ones
from numpy import abs as np_abs
from numpy import count_nonzero as np_count_nonzero
from numpy import cross as np_cross
from numpy import dot as np_dot
from numpy import any as np_any

# VTK imports____
from vtkmodules.util import numpy_support
from vtkmodules.vtkCommonDataModel import vtkSphere
from vtkmodules.vtkFiltersPoints import vtkExtractPoints
from vtk import vtkJSONSceneExporter, vtkAppendPolyData, vtkFeatureEdges

from PySide6.QtWidgets import (
    QMainWindow,
    QMenu,
    QAbstractItemView,
    QDockWidget,
    QSizePolicy,
    QMessageBox,
    QDialog,
    QVBoxLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QCheckBox,
    QSlider,
    QLabel,
    QPushButton,
    QSpinBox,
    QInputDialog,
    QApplication,
    QLineEdit,
    QRadioButton,
    QStackedWidget,
    QWidget,
    QDoubleSpinBox,
)
import time
from PySide6.QtGui import QAction
from PySide6.QtCore import Qt
from PySide6.QtCore import Signal as pyqtSignal
from PySide6.QtWidgets import QWidget

# PyVista imports____
from pyvista import plot as pv_plot
import pyvista as pv

# PZero imports____
from .abstract_view_vtk import ViewVTK
from ..helpers.helper_dialogs import (
    save_file_dialog,
    multiple_input_dialog,
    progress_dialog,
)
from ..helpers.helper_functions import best_fitting_plane, gen_frame, freeze_gui_off
from ..collections.geological_collection import GeologicalCollection
from ..entities_factory import PolyData, Attitude, PolyLine, TriSurf
from ..two_d_lines import draw_line_3d


class View3D(ViewVTK):
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

        # Track singleton Mesh Slicer dialog instance
        self.mesh_slicer_dialog = None

        # Small epsilon to keep slice planes inside bounds when clamping
        self._slice_edge_epsilon = 1e-6

        # Ensure mesh-slice visuals react to property colormap changes
        try:
            if hasattr(self.parent, "signals") and hasattr(
                self.parent.signals, "prop_legend_cmap_modified"
            ):
                self.parent.signals.prop_legend_cmap_modified.connect(
                    self.update_slices_for_property_change
                )
        except Exception:
            pass

    # ================================  General methods shared by all views - built incrementally =====================

    def initialize_menu_tools(self):
        """This method collects menus and actions in superclasses and then adds custom ones, specific to this view."""
        # append code from superclass
        super().initialize_menu_tools()

        # Remove 2D line drawing from 3D view (use "Draw line (3D mode)" instead)
        if hasattr(self, "drawLineButton"):
            self.drawLineButton.setEnabled(False)
            self.drawLineButton.setVisible(False)
            if hasattr(self, "menuCreate"):
                self.menuCreate.removeAction(self.drawLineButton)

        # Ensure any inherited 3D line action is removed before re-adding it here
        if hasattr(self, "drawLine3DButton") and hasattr(self, "menuCreate"):
            self.menuCreate.removeAction(self.drawLine3DButton)

        # then add new code specific to this class
        self.saveHomeView = QAction("Save home view", self)
        self.saveHomeView.triggered.connect(self.save_home_view)
        self.menuView.insertAction(self.zoomActive, self.saveHomeView)

        self.zoomHomeView = QAction("Zoom to home", self)
        self.zoomHomeView.triggered.connect(self.zoom_home_view)
        self.menuView.insertAction(self.zoomActive, self.zoomHomeView)

        # Add 3D-specific line drawing tool that uses point picking
        # proper connection to the action
        self.drawLine3DButton = QAction("Draw line (3D mode)", self)
        self.drawLine3DButton.triggered.connect(lambda: draw_line_3d(self))
        self.menuCreate.addAction(self.drawLine3DButton)
        

        self.menuBoreTraceVis = QMenu("Borehole visualization methods", self)

        self.actionBoreTrace = QAction("Trace", self)
        self.actionBoreTrace.triggered.connect(lambda: self.change_bore_vis("trace"))

        self.actionBoreCylinder = QAction("Cylinder", self)
        self.actionBoreCylinder.triggered.connect(
            lambda: self.change_bore_vis("cylinder")
        )

        self.actionToggleLithology = QAction("Toggle lithology", self)
        self.actionToggleLithology.triggered.connect(
            lambda: self.change_bore_vis("litho")
        )

        self.actionToggleGeology = QAction("Toggle geology", self)
        self.actionToggleGeology.triggered.connect(lambda: self.change_bore_vis("geo"))

        self.menuBoreTraceVis.addAction(self.actionBoreTrace)
        self.menuBoreTraceVis.addAction(self.actionBoreCylinder)
        self.menuBoreTraceVis.addAction(self.actionToggleLithology)
        self.menuBoreTraceVis.addAction(self.actionToggleGeology)

        self.menuView.addMenu(self.menuBoreTraceVis)

        self.actionExportGltf = QAction("Export as GLTF", self)
        self.actionExportGltf.triggered.connect(self.export_gltf)
        self.menuView.addAction(self.actionExportGltf)

        self.actionExportHtml = QAction("Export as HTML", self)
        self.actionExportHtml.triggered.connect(self.export_html)
        self.menuView.addAction(self.actionExportHtml)

        self.actionExportObj = QAction("Export as OBJ", self)
        self.actionExportObj.triggered.connect(self.export_obj)
        self.menuView.addAction(self.actionExportObj)

        self.actionExportVtkJSON = QAction("Export as vtkJSON scene", self)
        self.actionExportVtkJSON.triggered.connect(self.export_vtkJS)
        self.menuView.addAction(self.actionExportVtkJSON)

        # self.menuOrbit = QMenu("Orbit around", self)
        # self.actionOrbitEntity = QAction("Entity", self)
        # self.actionOrbitEntity.triggered.connect(lambda: self.orbit_entity())
        # self.menuOrbit.addAction(self.actionOrbitEntity)
        # self.menuWindow.addMenu(self.menuOrbit)
        #
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
        #
        # self.showOct = QAction("Show octree structure", self)
        # self.showOct.triggered.connect(self.show_octree)
        # self.menuBaseView.addAction(self.showOct)
        # self.toolBarBase.addAction(self.showOct)

    # Called by BaseView.toggle_property after main actor's property changes via tree combo
    def on_property_toggled(self, collection_name=None, uid=None, prop_text=None):
        try:
            # Find the entity label used in the slicer combo for this uid
            collection = getattr(self.parent, collection_name)
            entity_name = collection.get_uid_name(uid)
            # Prepend prefix as used in the slicer (e.g., "Image: <name>")
            prefix_map = {
                "mesh3d_coll": "Mesh",
                "geol_coll": "Geological",
                "xsect_coll": "Cross-section",
                "boundary_coll": "Boundary",
                "dom_coll": "DOM",
                "image_coll": "Image",
                "well_coll": "Well",
                "fluid_coll": "Fluid",
                "backgrnd_coll": "Background",
            }
            prefix = prefix_map.get(collection_name, None)
            labeled_name = f"{prefix}: {entity_name}" if prefix else entity_name

            # Persist property for this entity (used by slice updates)
            if not hasattr(self, "slice_prop_by_entity"):
                self.slice_prop_by_entity = {}
            self.slice_prop_by_entity[labeled_name] = prop_text

            # Update any existing slices for this entity immediately (single-slice axes)
            for axis in ["X", "Y", "Z"]:
                slice_uid = f"{labeled_name}_{axis}"
                if hasattr(self, "slice_actors") and slice_uid in self.slice_actors:
                    self._rebuild_slice_actor(
                        labeled_name, axis, enforced_prop=prop_text
                    )
            # Update any existing grid slices for this entity (multi-slice)
            if hasattr(self, "slice_actors"):
                for sid in [
                    uid_
                    for uid_ in list(self.slice_actors.keys())
                    if uid_.startswith(f"{labeled_name}_") and "_grid_" in uid_
                ]:
                    self._rebuild_grid_slice_actor(sid, enforced_prop=prop_text)
            # Render once after updates
            if hasattr(self, "plotter"):
                self.plotter.render()
        except Exception:
            pass

    def _rebuild_slice_actor(self, labeled_name, axis, enforced_prop=None):
        try:
            if not hasattr(self, "slice_actors"):
                return
            slice_uid = f"{labeled_name}_{axis}"
            if slice_uid not in self.slice_actors:
                return
            actor = self.slice_actors[slice_uid]
            entity = self.get_entity_by_name(labeled_name)
            if entity is None:
                return
            pv_entity = pv.wrap(entity)
            b = pv_entity.bounds
            origin = actor.GetCenter()
            if axis == "X" and b[1] > b[0]:
                norm = (origin[0] - b[0]) / (b[1] - b[0])
            elif axis == "Y" and b[3] > b[2]:
                norm = (origin[1] - b[2]) / (b[3] - b[2])
            elif axis == "Z" and b[5] > b[4]:
                norm = (origin[2] - b[4]) / (b[5] - b[4])
            else:
                norm = 0.5
            position = {
                "X": b[0] + norm * (b[1] - b[0]),
                "Y": b[2] + norm * (b[3] - b[2]),
                "Z": b[4] + norm * (b[5] - b[4]),
            }[axis]
            normal = {"X": [1, 0, 0], "Y": [0, 1, 0], "Z": [0, 0, 1]}[axis]
            origin_vec = {
                "X": [position, 0, 0],
                "Y": [0, position, 0],
                "Z": [0, 0, position],
            }[axis]
            slice_data = pv_entity.slice(normal=normal, origin=origin_vec)
            if slice_data.n_points <= 0:
                return
            # Resolve property
            main_uid = self.get_entity_uid_by_name(labeled_name)
            prop_text = enforced_prop
            if prop_text is None:
                if (
                    hasattr(self, "slice_prop_by_entity")
                    and labeled_name in self.slice_prop_by_entity
                ):
                    prop_text = self.slice_prop_by_entity[labeled_name]
                elif main_uid is not None:
                    prop_text = self.actors_df.loc[
                        self.actors_df["uid"] == main_uid, "show_property"
                    ].values[0]
            # Style
            scalar_array = None
            cmap = None
            color_RGB = None
            if not prop_text or prop_text == "none":
                color_RGB = self._legend_color_for_uid(main_uid)
            elif prop_text in ["X", "Y", "Z"]:
                idx = {"X": 0, "Y": 1, "Z": 2}[prop_text]
                scalar_array = slice_data.points[:, idx]
                if (
                    hasattr(self.parent, "prop_legend_df")
                    and self.parent.prop_legend_df is not None
                ):
                    row = self.parent.prop_legend_df[
                        self.parent.prop_legend_df["property_name"] == prop_text
                    ]
                    if not row.empty:
                        cmap = row["colormap"].iloc[0]
            else:
                if prop_text in slice_data.array_names:
                    scalar_array = prop_text
                    if (
                        hasattr(self.parent, "prop_legend_df")
                        and self.parent.prop_legend_df is not None
                    ):
                        row = self.parent.prop_legend_df[
                            self.parent.prop_legend_df["property_name"] == prop_text
                        ]
                        if not row.empty:
                            cmap = row["colormap"].iloc[0]
            vis = actor.GetVisibility()
            self.plotter.remove_actor(actor)
            self.slice_actors[slice_uid] = self.plotter.add_mesh(
                slice_data,
                name=slice_uid,
                scalars=scalar_array,
                cmap=cmap,
                clim=pv_entity.get_data_range(scalar_array) if scalar_array else None,
                show_scalar_bar=False,
                opacity=1.0,
                interpolate_before_map=True,
                color=color_RGB,
            )
            self.slice_actors[slice_uid].SetVisibility(vis)
        except Exception:
            pass

    def _rebuild_grid_slice_actor(self, slice_uid, enforced_prop=None):
        try:
            if not hasattr(self, "slice_actors") or slice_uid not in self.slice_actors:
                return
            # Parse entity and axis from uid pattern: <entity_name>_<X|Y|Z>_grid_<n>
            if "_grid_" not in slice_uid:
                return
            before, _, _ = slice_uid.rpartition("_grid_")
            entity_name, _, axis = before.rpartition("_")
            actor = self.slice_actors[slice_uid]
            entity = self.get_entity_by_name(entity_name)
            if entity is None:
                return
            pv_entity = pv.wrap(entity)
            # Compute origin position from actor
            origin = actor.GetCenter()
            b = pv_entity.bounds
            if axis == "X":
                position = origin[0]
                normal = [1, 0, 0]
                origin_vec = [position, 0, 0]
            elif axis == "Y":
                position = origin[1]
                normal = [0, 1, 0]
                origin_vec = [0, position, 0]
            else:
                position = origin[2]
                normal = [0, 0, 1]
                origin_vec = [0, 0, position]
            slice_data = pv_entity.slice(normal=normal, origin=origin_vec)
            if slice_data.n_points <= 0:
                return
            # Determine prop
            main_uid = self.get_entity_uid_by_name(entity_name)
            prop_text = enforced_prop
            if prop_text is None:
                if (
                    hasattr(self, "slice_prop_by_entity")
                    and entity_name in self.slice_prop_by_entity
                ):
                    prop_text = self.slice_prop_by_entity[entity_name]
                elif main_uid is not None:
                    prop_text = self.actors_df.loc[
                        self.actors_df["uid"] == main_uid, "show_property"
                    ].values[0]
            scalar_array = None
            cmap = None
            color_RGB = None
            if not prop_text or prop_text == "none":
                color_RGB = self._legend_color_for_uid(main_uid)
            elif prop_text in ["X", "Y", "Z"]:
                idx = {"X": 0, "Y": 1, "Z": 2}[prop_text]
                scalar_array = slice_data.points[:, idx]
                if (
                    hasattr(self.parent, "prop_legend_df")
                    and self.parent.prop_legend_df is not None
                ):
                    row = self.parent.prop_legend_df[
                        self.parent.prop_legend_df["property_name"] == prop_text
                    ]
                    if not row.empty:
                        cmap = row["colormap"].iloc[0]
            else:
                if prop_text in slice_data.array_names:
                    scalar_array = prop_text
                    if (
                        hasattr(self.parent, "prop_legend_df")
                        and self.parent.prop_legend_df is not None
                    ):
                        row = self.parent.prop_legend_df[
                            self.parent.prop_legend_df["property_name"] == prop_text
                        ]
                        if not row.empty:
                            cmap = row["colormap"].iloc[0]
            vis = actor.GetVisibility()
            self.plotter.remove_actor(actor)
            self.slice_actors[slice_uid] = self.plotter.add_mesh(
                slice_data,
                name=slice_uid,
                scalars=scalar_array,
                cmap=cmap,
                clim=pv_entity.get_data_range(scalar_array) if scalar_array else None,
                show_scalar_bar=False,
                opacity=1.0,
                interpolate_before_map=True,
                color=color_RGB,
            )
            self.slice_actors[slice_uid].SetVisibility(vis)
        except Exception:
            pass

    # ================================  Methods required by ViewVTK(), (re-)implemented here ==========================

    def set_orientation_widget(self):
        # The oreintation widget can be turned off and on again, e.g. to export a scene, with:
        # self.plotter.clear_camera_widgets()
        # self.plotter.add_camera_orientation_widget()
        self.plotter.add_camera_orientation_widget()

    def show_qt_canvas(self):
        """Show the Qt Window. Reimplements the base method in ViewVTK()."""
        self.show()
        self.init_zoom = self.plotter.camera.distance
        # self.picker = self.plotter.enable_mesh_picking(callback= self.pkd_mesh,show_message=False)

    # ================================  Methods specific to 3D views ==================================================

    def end_pick(self, pos):
        """Function used to disable actor picking. Due to some slight difference,
        must be reimplemented in subclasses.
        Do not use @freeze_gui_onoff here, that is used at a higher level."""
        # Remove the selector observer
        self.plotter.iren.interactor.RemoveObservers("LeftButtonPressEvent")
        # Remove the right click observer
        self.plotter.untrack_click_position(side="right")
        # Remove the left click observer
        self.plotter.untrack_click_position(side="left")

        # Specific to View3D() implementation.
        self.plotter.enable_trackball_style()
        # Closing settings
        self.plotter.reset_key_events()
        self.selected_uids = self.parent.selected_uids
        # self.enable_actions()
        freeze_gui_off(self)

    def orbit_entity(self):
        uid_list = self.actors_df["uid"].to_list()

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
        # entity = self.actors_df.loc[self.actors_df["uid"] == uid, "actor"].values[0]
        entity = self.get_actor_by_uid(uid)

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

        # visible_actors = self.actors_df.loc[
        #     self.actors_df["show"] == True, "actor"
        # ].values
        # for actor in visible_actors:
        #     off_screen_plot.add_actor(actor)
        for uid in self.shown_uids:
            off_screen_plot.add_actor(self.get_actor_by_uid(uid))

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
            self.print_terminal("Picking enabled")
        else:
            self.plotter.disable_picking()
            self.tog_att *= -1
            self.print_terminal("Picking disabled")

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
        #  We could try to do this with vtkPCANormalEstimation
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
        # vis_uids = self.actors_df.loc[self.actors_df["show"] == True, "uid"]
        # for uid in vis_uids:
        for uid in self.shown_uids:
            vtk_obj = self.parent.dom_coll.get_uid_vtk_obj(uid)
            octree = PolyData()  #  possible recursion problem
            # print(vtk_obj.locator)
            vtk_obj.locator.GenerateRepresentation(3, octree)

            self.plotter.add_mesh(octree, style="wireframe", color="red")

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

    def _refresh_well_trace_properties(self):
        """
        Re-render all well property actors so they reflect the current trace visualization method.
        """
        if not hasattr(self, "actors_df") or self.actors_df.empty:
            return
        try:
            well_rows = self.actors_df[(self.actors_df["collection"] == "well_coll")]
        except Exception:
            return

        if well_rows.empty:
            return

        for _, row in well_rows.iterrows():
            prop = row.get("show_property")
            if prop in (None, "none", "Marker", "Annotations"):
                continue
            try:
                self.toggle_property(
                    collection_name="well_coll", uid=row["uid"], prop_text=prop
                )
            except Exception:
                continue

    def change_bore_vis(self, method):
        actors = set(self.plotter.renderer.actors.copy())
        wells = set(self.parent.well_coll.get_uids)

        well_actors = actors.intersection(wells)
        if method == "trace":
            self.trace_method = method
            self._refresh_well_trace_properties()
        elif method == "cylinder":
            self.trace_method = method
            self._refresh_well_trace_properties()
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

    def export_gltf(self):
        out_file_name = save_file_dialog(
            parent=self, caption="Export 3D view as GLTF.", filter="gltf (*.gltf)"
        ).removesuffix(".gltf")
        self.plotter.export_gltf(f"{out_file_name}.gltf")

    def export_html(self):
        out_file_name = save_file_dialog(
            parent=self, caption="Export 3D view as HTML.", filter="html (*.html)"
        ).removesuffix(".html")
        self.plotter.export_html(f"{out_file_name}.html")

    def export_vtksz(self):
        out_file_name = save_file_dialog(
            parent=self, caption="Export 3D view as VTKsz.", filter="zip (*.zip)"
        ).removesuffix(".zip")
        self.plotter.export_vtksz(f"{out_file_name}.zip", format="zip")

    def export_vtkJS(self):
        out_file_name = save_file_dialog(
            parent=self, caption="Export 3D view as VTKsz.", filter="zip (*.zip)"
        ).removesuffix(".zip")

        self.plotter.clear_camera_widgets()
        exporter = vtkJSONSceneExporter()
        exporter.SetFileName(out_file_name)
        exporter.SetInput(self.plotter.renderer.GetRenderWindow())
        exporter.SetActiveRenderer(self.plotter.renderer)
        exporter.Write()
        make_archive(out_file_name, "zip", out_file_name)
        rmtree(out_file_name)
        self.plotter.add_camera_orientation_widget()

    def export_obj(self):
        out_file_name = save_file_dialog(
            parent=self, caption="Export 3D view as OBJ.", filter="obj (*.obj)"
        ).removesuffix(".obj")
        self.plotter.export_obj(f"{out_file_name}.obj")

    def show_mesh_slicer_dialog(self):
        """Create and show a unified control panel for mesh slicing in both single and multi-slice modes."""
        # Reuse existing dialog if already open
        try:
            if (
                getattr(self, "mesh_slicer_dialog", None) is not None
                and self.mesh_slicer_dialog.isVisible()
            ):
                # Bring to front and inform the user
                try:
                    self.mesh_slicer_dialog.raise_()
                    self.mesh_slicer_dialog.activateWindow()
                except Exception:
                    pass
                QMessageBox.information(
                    self, "Mesh Slicer", "Mesh Slicer is already open."
                )
                return self.mesh_slicer_dialog
        except Exception:
            # If anything goes wrong, reset the reference and continue to create a new dialog
            self.mesh_slicer_dialog = None
        # Create the control panel window
        control_panel = QDialog(self)
        control_panel.setWindowTitle("Mesh Slicer")
        # Ensure the widget is deleted on close so we can recreate later
        try:
            control_panel.setAttribute(Qt.WA_DeleteOnClose, True)
        except Exception:
            pass
        # Set dialog flags to prevent default Enter key behavior
        control_panel.setWindowFlags(
            control_panel.windowFlags() | Qt.WindowType.CustomizeWindowHint
        )
        # Disable default button behavior
        control_panel.setModal(False)
        layout = QVBoxLayout()

        # Add mode selection at the top
        mode_group = QGroupBox("Slice Mode")
        mode_layout = QHBoxLayout()

        single_mode_radio = QRadioButton("Single Slice Mode")
        multi_mode_radio = QRadioButton("Multi Slice Mode")
        single_mode_radio.setChecked(True)  # Default to single mode

        mode_layout.addWidget(single_mode_radio)
        mode_layout.addWidget(multi_mode_radio)
        mode_group.setLayout(mode_layout)
        layout.addWidget(mode_group)

        # Create stacked widget to hold both UIs
        stack = QStackedWidget()
        single_slice_widget = QWidget()
        multi_slice_widget = QWidget()

        # Initialize containers for UI groups
        single_slice_layout = QVBoxLayout(single_slice_widget)
        multi_slice_layout = QVBoxLayout(multi_slice_widget)

        # Add widgets to stack
        stack.addWidget(single_slice_widget)
        stack.addWidget(multi_slice_widget)
        layout.addWidget(stack)

        # Connect mode selection to stack switching
        single_mode_radio.toggled.connect(
            lambda checked: stack.setCurrentIndex(0) if checked else None
        )
        multi_mode_radio.toggled.connect(
            lambda checked: stack.setCurrentIndex(1) if checked else None
        )

        # Create custom line edit class to handle Enter key properly
        class SlicerLineEdit(QLineEdit):
            def keyPressEvent(self, event):
                if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
                    # Handle Enter key internally - don't propagate to dialog
                    self.editingFinished.emit()
                    event.accept()
                else:
                    # Handle other keys normally
                    super().keyPressEvent(event)

        # Initialize slice actors dictionary if it doesn't exist
        if not hasattr(self, "slice_actors"):
            self.slice_actors = {}
        # Track metadata for each slice to avoid parsing names later
        if not hasattr(self, "slice_meta"):
            self.slice_meta = {}

        # Initialize plane widgets list if it doesn't exist
        if not hasattr(self, "plane_widgets"):
            self.plane_widgets = []

        # Initialize throttle time for UI updates
        self.last_slider_update = time.time()
        slider_throttle = 1 / 30.0

        # Create entity selection group (shared between modes)
        entity_group = QGroupBox("Entity Selection")
        entity_layout = QVBoxLayout()

        entity_label = QLabel("Select Entity:")
        entity_combo = QComboBox()
        entity_combo.addItems(self.getSliceableEntities())
        entity_combo.setObjectName("mesh_slicer_entity_combo")

        entity_layout.addWidget(entity_label)
        entity_layout.addWidget(entity_combo)
        entity_group.setLayout(entity_layout)

        # Add to both layouts
        single_slice_layout.addWidget(entity_group)

        # Clone entity selection for multi-slice mode
        multi_entity_group = QGroupBox("Entity Selection")
        multi_entity_layout = QVBoxLayout()

        multi_entity_label = QLabel("Select Entity:")
        multi_entity_combo = QComboBox()
        multi_entity_combo.addItems(self.getSliceableEntities())
        multi_entity_combo.setObjectName("mesh_slicer_multi_entity_combo")

        multi_entity_layout.addWidget(multi_entity_label)
        multi_entity_layout.addWidget(multi_entity_combo)
        multi_entity_group.setLayout(multi_entity_layout)

        # Add to multi-slice layout
        multi_slice_layout.addWidget(multi_entity_group)

        # Keep entity combos in sync
        def sync_entity_selection(text):
            if entity_combo.currentText() != text:
                entity_combo.setCurrentText(text)
            if multi_entity_combo.currentText() != text:
                multi_entity_combo.setCurrentText(text)

        entity_combo.currentTextChanged.connect(sync_entity_selection)
        multi_entity_combo.currentTextChanged.connect(sync_entity_selection)

        # Single slice mode components
        # ----------------------------

        # Slice toggle group
        slice_toggle_group = QGroupBox("Slice Visibility")
        slice_toggle_layout = QVBoxLayout()

        u_slice_check = QCheckBox("U Slice")
        v_slice_check = QCheckBox("V Slice")
        w_slice_check = QCheckBox("W Slice")

        slice_toggle_layout.addWidget(u_slice_check)
        slice_toggle_layout.addWidget(v_slice_check)
        slice_toggle_layout.addWidget(w_slice_check)
        slice_toggle_group.setLayout(slice_toggle_layout)

        single_slice_layout.addWidget(slice_toggle_group)

        # Position control group - create sliders, labels and values
        position_group = QGroupBox("Position Control")
        position_layout = QVBoxLayout()

        # Create UI components using a more compact approach
        sliders = {}
        value_labels = {}
        value_inputs = {}

        for label_text, slice_type in [
            ("U Position:", "X"),
            ("V Position:", "Y"),
            ("W Position:", "Z"),
        ]:
            slider = QSlider(Qt.Horizontal)
            slider.setMinimum(0)
            slider.setMaximum(100)
            slider.setValue(50)

            label = QLabel(label_text)
            value_label = QLabel("0.50")
            value_input = SlicerLineEdit()  # Use our custom line edit class
            value_input.setFixedWidth(80)
            value_input.setText(
                "50"
            )  # Default value (normalized percentage or slice number will be updated later)

            # Store references
            sliders[slice_type] = slider
            value_labels[slice_type] = value_label
            value_inputs[slice_type] = value_input

            # Create layout
            slider_layout = QHBoxLayout()
            slider_layout.addWidget(label)
            slider_layout.addWidget(slider)
            slider_layout.addWidget(value_label)
            slider_layout.addWidget(value_input)
            position_layout.addLayout(slider_layout)

        position_group.setLayout(position_layout)
        single_slice_layout.addWidget(position_group)

        # Assign variables for easier reference
        u_slider, v_slider, w_slider = sliders["X"], sliders["Y"], sliders["Z"]
        u_value, v_value, w_value = (
            value_labels["X"],
            value_labels["Y"],
            value_labels["Z"],
        )
        u_input, v_input, w_input = (
            value_inputs["X"],
            value_inputs["Y"],
            value_inputs["Z"],
        )

        # Add manipulation control group
        # manipulation_group = QGroupBox("Manipulation Control")
        # manipulation_layout = QVBoxLayout()

        # enable_manipulation = QCheckBox("Enable Direct Manipulation")
        # enable_manipulation.setChecked(False)  # Default to disabled

        # manipulation_layout.addWidget(enable_manipulation)
        # manipulation_group.setLayout(manipulation_layout)
        #   single_slice_layout.addWidget(manipulation_group)

        # Multi-slice mode components (taken from grid section manager)
        # ------------------------------

        # Direction selection
        direction_layout = QHBoxLayout()
        direction_layout.addWidget(QLabel("Direction:"))
        direction_combo = QComboBox()
        direction_combo.addItems(["U Direction", "V Direction", "W Direction"])
        direction_layout.addWidget(direction_combo)
        multi_slice_layout.addLayout(direction_layout)

        # Add position slider for multi-slice mode
        multi_position_group = QGroupBox("Position Range")
        multi_position_layout = QVBoxLayout()

        # Start position slider
        start_layout = QHBoxLayout()
        start_layout.addWidget(QLabel("Start:"))
        start_slider = QSlider(Qt.Horizontal)
        start_slider.setMinimum(0)
        start_slider.setMaximum(100)
        start_slider.setValue(0)  # Default to start (0%)
        start_label = QLabel("0.00")
        start_layout.addWidget(start_slider)
        start_layout.addWidget(start_label)
        multi_position_layout.addLayout(start_layout)

        # End position slider
        end_layout = QHBoxLayout()
        end_layout.addWidget(QLabel("End:"))
        end_slider = QSlider(Qt.Horizontal)
        end_slider.setMinimum(0)
        end_slider.setMaximum(100)
        end_slider.setValue(100)  # Default to end (100%)
        end_label = QLabel("1.00")
        end_layout.addWidget(end_slider)
        end_layout.addWidget(end_label)
        multi_position_layout.addLayout(end_layout)

        # Connect slider events
        def update_start_label():
            normalized_pos = start_slider.value() / 100.0
            start_label.setText(f"{normalized_pos:.2f}")

        def update_end_label():
            normalized_pos = end_slider.value() / 100.0
            end_label.setText(f"{normalized_pos:.2f}")

        start_slider.valueChanged.connect(update_start_label)
        end_slider.valueChanged.connect(update_end_label)

        # Make sure start doesn't exceed end
        def enforce_slider_limits():
            if start_slider.value() > end_slider.value():
                start_slider.setValue(end_slider.value())

        start_slider.valueChanged.connect(enforce_slider_limits)

        multi_position_group.setLayout(multi_position_layout)
        multi_slice_layout.addWidget(multi_position_group)

        # Number of slices
        slices_layout = QHBoxLayout()
        slices_layout.addWidget(QLabel("Number of slices:"))
        slices_spin = QSpinBox()
        slices_spin.setRange(2, 50)
        slices_spin.setValue(7)
        slices_layout.addWidget(slices_spin)
        multi_slice_layout.addLayout(slices_layout)

        # Create buttons
        create_btn = QPushButton("Create Slices")
        remove_btn = QPushButton("Remove Slices")

        # Add buttons to layout
        buttons_layout = QHBoxLayout()
        buttons_layout.addWidget(create_btn)
        buttons_layout.addWidget(remove_btn)
        multi_slice_layout.addLayout(buttons_layout)

        # Add direct manipulation option for multi-slice grid
        multi_manipulation_group = QGroupBox("Grid Visualization")
        multi_manipulation_layout = QVBoxLayout()

        # show_grid_box = QCheckBox("Show Grid Lines")
        # show_grid_box.setChecked(False)  # Default to not showing grid

        # Add direct manipulation option for multi-slice view
        multi_direct_manip = QCheckBox("Enable Direct Manipulation")
        multi_direct_manip.setChecked(False)  # Default to disabled

        # multi_manipulation_layout.addWidget(show_grid_box)
        multi_manipulation_layout.addWidget(multi_direct_manip)
        multi_manipulation_group.setLayout(multi_manipulation_layout)
        multi_slice_layout.addWidget(multi_manipulation_group)

        # Connect multi-slice direct manipulation toggle
        def toggle_multi_manipulation(state):
            is_checked = state == Qt.CheckState.Checked.value
            print(f"Multi-slice direct manipulation: {is_checked}")

            # Get the current entity
            entity_name = multi_entity_combo.currentText()
            if not entity_name:
                print("No entity selected for multi-slice manipulation")
                return

            # Get entity
            entity = self.get_entity_by_name(entity_name)
            if not entity:
                print(f"Entity {entity_name} not found")
                return

            # Get direction and slice type
            direction = direction_combo.currentText()
            slice_type = direction_to_slice_type(direction)

            # --- Start Modification ---
            # Always clean up existing widgets first
            if hasattr(self, "multi_plane_widgets"):
                for widget in self.multi_plane_widgets:
                    try:
                        if hasattr(widget, "SetEnabled"):
                            widget.SetEnabled(0)
                        if hasattr(self.plotter, "remove_widget"):
                            self.plotter.remove_widget(widget)
                        elif hasattr(self.plotter.iren, "remove_widget"):
                            self.plotter.iren.remove_widget(widget)
                    except Exception as e:
                        print(f"Warning: Error removing widget: {e}")
                self.multi_plane_widgets = []
                self.plotter.render()  # Render after removing old widgets

            if is_checked:
                # Enable manipulation: Create a widget for EACH existing grid slice
                print(
                    f"Enabling manipulation for existing grid slices ({entity_name}, {direction})..."
                )
                try:
                    # Convert to PyVista object if needed
                    if not isinstance(entity, pv.DataSet):
                        pv_entity = pv.wrap(entity)
                    else:
                        pv_entity = entity
                    bounds = pv_entity.bounds

                    # Initialize widget list
                    if not hasattr(self, "multi_plane_widgets"):
                        self.multi_plane_widgets = []

                    # Find existing grid slices for this entity and direction
                    slice_prefix = f"{entity_name}_{slice_type}_grid_"
                    existing_slice_ids = [
                        uid
                        for uid in self.slice_actors.keys()
                        if uid.startswith(slice_prefix)
                    ]

                    if not existing_slice_ids:
                        print(
                            "No existing grid slices found to manipulate. Create slices first."
                        )
                        # Uncheck the box if no slices exist
                        multi_direct_manip.setChecked(False)
                        return

                    # Create a widget for each slice
                    for slice_id in existing_slice_ids:
                        actor = self.slice_actors.get(slice_id)
                        if not actor:
                            continue

                        # Calculate normalized position from actor's current position
                        origin = actor.GetCenter()  # Get the center of the slice actor
                        normalized_pos = 0.5  # Default fallback

                        if slice_type == "X" and bounds[1] > bounds[0]:
                            normalized_pos = (origin[0] - bounds[0]) / (
                                bounds[1] - bounds[0]
                            )
                        elif slice_type == "Y" and bounds[3] > bounds[2]:
                            # Assuming Y corresponds to index 1 in VTK origin/center
                            # Check VTK documentation if this is incorrect for Y slices
                            normalized_pos = (origin[1] - bounds[2]) / (
                                bounds[3] - bounds[2]
                            )
                        elif slice_type == "Z" and bounds[5] > bounds[4]:
                            # Assuming Z corresponds to index 2
                            normalized_pos = (origin[2] - bounds[4]) / (
                                bounds[5] - bounds[4]
                            )

                        normalized_pos = max(0, min(1, normalized_pos))  # Clamp 0-1

                        print(
                            f"  Creating widget for {slice_id} at norm_pos={normalized_pos:.3f}"
                        )

                        # --- Define NEW callback for individual slice widgets ---
                        def create_slice_update_callback(
                            target_slice_id, target_entity_name, target_slice_type
                        ):
                            def slice_update_callback(normal, widget_origin):
                                # Calculate normalized position from widget interaction
                                current_bounds = self.get_entity_by_name(
                                    target_entity_name
                                ).bounds
                                new_normalized_pos = 0.5  # Default fallback
                                if (
                                    target_slice_type == "X"
                                    and current_bounds[1] > current_bounds[0]
                                ):
                                    new_normalized_pos = (
                                        widget_origin[0] - current_bounds[0]
                                    ) / (current_bounds[1] - current_bounds[0])
                                elif (
                                    target_slice_type == "Y"
                                    and current_bounds[3] > current_bounds[2]
                                ):
                                    new_normalized_pos = (
                                        widget_origin[1] - current_bounds[2]
                                    ) / (current_bounds[3] - current_bounds[2])
                                elif (
                                    target_slice_type == "Z"
                                    and current_bounds[5] > current_bounds[4]
                                ):
                                    new_normalized_pos = (
                                        widget_origin[2] - current_bounds[4]
                                    ) / (current_bounds[5] - current_bounds[4])

                                # Clamp slightly inside [0,1] to prevent disappearing at exact bounds
                                eps = getattr(self, "_slice_edge_epsilon", 1e-6)
                                if new_normalized_pos <= 0.0:
                                    new_normalized_pos = eps
                                elif new_normalized_pos >= 1.0:
                                    new_normalized_pos = 1.0 - eps

                                # Update the specific slice visualization using the main function
                                update_slice_visualization(
                                    target_entity_name,
                                    target_slice_type,
                                    new_normalized_pos,
                                    fast_update=True,
                                    specific_slice_id=target_slice_id,
                                )

                            return slice_update_callback

                        # --- End NEW callback ---

                        # Create the widget with the specific callback for this slice_id
                        widget = self.create_single_plane_widget(
                            slice_type,
                            normalized_pos,
                            bounds,
                            create_slice_update_callback(
                                slice_id, entity_name, slice_type
                            ),  # Pass slice_id to callback context
                        )

                        if widget:
                            self.multi_plane_widgets.append(widget)
                        else:
                            print(f"  Failed to create widget for {slice_id}")

                    if self.multi_plane_widgets:
                        # Render the changes once after adding all widgets
                        self.plotter.render()
                        print(
                            f"Multi-slice direct manipulation enabled for {len(self.multi_plane_widgets)} slices."
                        )
                    else:
                        print("Failed to create any manipulation widgets.")
                        multi_direct_manip.setChecked(False)  # Uncheck if failed

                except Exception as e:
                    print(f"Error setting up multi-slice manipulation: {e}")
                    import traceback

                    traceback.print_exc()
                    multi_direct_manip.setChecked(False)  # Uncheck on error
            else:
                # Manipulation disabled - cleanup already happened at the start
                print("Multi-slice direct manipulation disabled")
            # --- End Modification ---

            # Enforce property sync on all grid slices of current entity+direction
            try:
                entity_name_sync = multi_entity_combo.currentText()
                direction_sync = direction_combo.currentText()
                slice_type_sync = direction_to_slice_type(direction_sync)
                main_uid_sync = self.get_entity_uid_by_name(entity_name_sync)
                prop_text_sync = None
                if (
                    hasattr(self, "slice_prop_by_entity")
                    and entity_name_sync in self.slice_prop_by_entity
                ):
                    prop_text_sync = self.slice_prop_by_entity[entity_name_sync]
                elif main_uid_sync is not None:
                    prop_text_sync = self.actors_df.loc[
                        self.actors_df["uid"] == main_uid_sync, "show_property"
                    ].values[0]
                for sid in [
                    uid
                    for uid in list(self.slice_actors.keys())
                    if uid.startswith(f"{entity_name_sync}_{slice_type_sync}_grid_")
                ]:
                    self._rebuild_grid_slice_actor(sid, enforced_prop=prop_text_sync)
                self.plotter.render()
            except Exception:
                pass

        # NOTE: update_multi_slice_position is no longer needed for direct manipulation,
        # but keep it for the start/end sliders if they are still used elsewhere.
        # Remove or comment out if the sliders only define the *range* for creation.
        def update_multi_slice_position(widget_type, normalized_pos, slider, label):
            """Update the position of a multi-slice boundary based on widget movement"""
            try:
                # Update slider value
                slider_value = int(normalized_pos * 100)
                slider.setValue(slider_value)

                # Update label
                label.setText(f"{normalized_pos:.2f}")

                # Enforce limits (start <= end)
                if widget_type == "start" and start_slider.value() > end_slider.value():
                    end_slider.setValue(start_slider.value())
                    end_label.setText(f"{normalized_pos:.2f}")
                elif widget_type == "end" and end_slider.value() < start_slider.value():
                    start_slider.setValue(end_slider.value())
                    start_label.setText(f"{normalized_pos:.2f}")

                # Update the visualization if slices are already created
                print(f"Updated {widget_type} position to {normalized_pos:.2f}")

            except Exception as e:
                print(f"Error updating multi-slice position: {e}")

        multi_direct_manip.stateChanged.connect(toggle_multi_manipulation)

        # Connect show grid checkbox
        def toggle_grid_lines(state):
            # This function would implement showing grid lines for the multi-slice view
            is_checked = state == Qt.CheckState.Checked.value
            print(f"Grid lines visibility: {is_checked}")
            # Future implementation: Show/hide grid lines

        # show_grid_box.stateChanged.connect(toggle_grid_lines)

        # Helper method to convert direction name to slice type
        def direction_to_slice_type(direction):
            mapping = {"U Direction": "X", "V Direction": "Y", "W Direction": "Z"}
            return mapping.get(direction, "X")

        # Multi-slice implementation functions
        def create_grid_slices():
            """Create multiple slices along the selected direction"""
            entity_name = multi_entity_combo.currentText()
            direction = direction_combo.currentText()
            n_slices = slices_spin.value()

            if not entity_name:
                print("No entity selected for grid slices")
                return

            # Get entity
            entity = self.get_entity_by_name(entity_name)
            if not entity:
                print(f"Entity {entity_name} not found")
                return

            # Convert to PyVista dataset
            if not isinstance(entity, pv.DataSet):
                entity = pv.wrap(entity)

            # Get bounds and slice type
            bounds = entity.bounds
            slice_type = direction_to_slice_type(direction)

            # Calculate positions along the axis
            if slice_type == "X":  # U direction
                min_val, max_val = bounds[0], bounds[1]
            elif slice_type == "Y":  # V direction
                min_val, max_val = bounds[2], bounds[3]
            else:  # Z (W direction)
                min_val, max_val = bounds[4], bounds[5]

            # Get the start and end positions from sliders
            start_norm = start_slider.value() / 100.0
            end_norm = end_slider.value() / 100.0

            # Generate evenly spaced positions between start and end position
            import numpy as np

            positions = np_linspace(
                start_norm, end_norm, n_slices
            )  # Normalized positions

            print(
                f"Creating {n_slices} slices for {entity_name} along {direction} from {start_norm:.2f} to {end_norm:.2f}"
            )

            # Create slices
            for i, normalized_pos in enumerate(positions):
                slice_id = f"{entity_name}_{slice_type}_grid_{i}"

                # Skip if already exists
                if slice_id in self.slice_actors:
                    print(f"Slice {slice_id} already exists, skipping")
                    continue

                try:
                    # Calculate actual position
                    if slice_type == "X":  # U direction
                        pos = min_val + normalized_pos * (max_val - min_val)
                        slice_data = entity.slice(normal="x", origin=[pos, 0, 0])
                    elif slice_type == "Y":  # V direction
                        pos = min_val + normalized_pos * (max_val - min_val)
                        slice_data = entity.slice(normal="y", origin=[0, pos, 0])
                    else:  # Z (W direction)
                        pos = min_val + normalized_pos * (max_val - min_val)
                        slice_data = entity.slice(normal="z", origin=[0, 0, pos])

                    # Skip empty slices
                    if slice_data.n_points <= 0:
                        print(f"Skipping empty slice at position {normalized_pos}")
                        continue

                    # Determine scalars/color based on main entity property for full sync
                    scalar_array = None
                    cmap = None
                    color_RGB = None
                    try:
                        main_uid = self.get_entity_uid_by_name(entity_name)
                        prop_text = None
                        if (
                            hasattr(self, "slice_prop_by_entity")
                            and entity_name in self.slice_prop_by_entity
                        ):
                            prop_text = self.slice_prop_by_entity[entity_name]
                        elif main_uid is not None:
                            prop_text = self.actors_df.loc[
                                self.actors_df["uid"] == main_uid, "show_property"
                            ].values[0]
                        if not prop_text or prop_text == "none":
                            color_RGB = self._legend_color_for_uid(main_uid)
                        elif prop_text in ["X", "Y", "Z"]:
                            idx = {"X": 0, "Y": 1, "Z": 2}[prop_text]
                            scalar_array = slice_data.points[:, idx]
                            if (
                                hasattr(self.parent, "prop_legend_df")
                                and self.parent.prop_legend_df is not None
                            ):
                                row = self.parent.prop_legend_df[
                                    self.parent.prop_legend_df["property_name"]
                                    == prop_text
                                ]
                                if not row.empty:
                                    cmap = row["colormap"].iloc[0]
                        else:
                            if prop_text in slice_data.array_names:
                                scalar_array = prop_text
                                if (
                                    hasattr(self.parent, "prop_legend_df")
                                    and self.parent.prop_legend_df is not None
                                ):
                                    row = self.parent.prop_legend_df[
                                        self.parent.prop_legend_df["property_name"]
                                        == prop_text
                                    ]
                                    if not row.empty:
                                        cmap = row["colormap"].iloc[0]
                    except Exception:
                        pass

                    # Add slice to visualization
                    actor = self.plotter.add_mesh(
                        slice_data,
                        name=slice_id,
                        scalars=scalar_array,
                        cmap=cmap,
                        clim=(
                            entity.get_data_range(scalar_array)
                            if scalar_array
                            else None
                        ),
                        show_scalar_bar=False,
                        opacity=1.0,
                        interpolate_before_map=True,
                        color=color_RGB,
                    )

                    self.slice_actors[slice_id] = actor
                    try:
                        if hasattr(self, "slice_meta"):
                            self.slice_meta[slice_id] = (entity_name, slice_type)
                    except Exception:
                        pass
                    print(f"Created slice {slice_id}")

                except Exception as e:
                    print(f"Error creating grid slice: {e}")
                    import traceback

                    traceback.print_exc()
                    continue

            self.plotter.render()

        def remove_grid_slices():
            """Remove all grid slices for the selected direction"""
            entity_name = multi_entity_combo.currentText()
            direction = direction_combo.currentText()
            slice_type = direction_to_slice_type(direction)

            if not entity_name:
                print("No entity selected for removing grid slices")
                return

            print(f"Removing grid slices for {entity_name} along {direction}")

            # Get all grid slices for this direction and entity
            grid_slices = [
                uid
                for uid in list(self.slice_actors.keys())
                if f"{entity_name}_{slice_type}_grid_" in uid
            ]

            for uid in grid_slices:
                if uid in self.slice_actors:
                    actor = self.slice_actors[uid]
                    self.plotter.remove_actor(actor)
                    del self.slice_actors[uid]
                    try:
                        if hasattr(self, "slice_meta") and uid in self.slice_meta:
                            del self.slice_meta[uid]
                    except Exception:
                        pass
                    print(f"Removed slice {uid}")

            self.plotter.render()

        # Connect buttons for multi-slice mode (single-pass creation with property sync)
        def create_grid_slices_sync():
            entity_name = multi_entity_combo.currentText()
            direction = direction_combo.currentText()
            if not entity_name:
                print("No entity selected for grid slices")
                return
            entity = self.get_entity_by_name(entity_name)
            if not entity:
                print(f"Entity {entity_name} not found")
                return
            if not isinstance(entity, pv.DataSet):
                entity = pv.wrap(entity)
            bounds = entity.bounds
            slice_type = direction_to_slice_type(direction)
            if slice_type == "X":
                min_val, max_val = bounds[0], bounds[1]
            elif slice_type == "Y":
                min_val, max_val = bounds[2], bounds[3]
            else:
                min_val, max_val = bounds[4], bounds[5]
            start_norm = start_slider.value() / 100.0
            end_norm = end_slider.value() / 100.0
            import numpy as np

            positions = np_linspace(start_norm, end_norm, slices_spin.value())
            # Resolve property once
            main_uid = self.get_entity_uid_by_name(entity_name)
            prop_text = None
            if (
                hasattr(self, "slice_prop_by_entity")
                and entity_name in self.slice_prop_by_entity
            ):
                prop_text = self.slice_prop_by_entity[entity_name]
            elif main_uid is not None:
                prop_text = self.actors_df.loc[
                    self.actors_df["uid"] == main_uid, "show_property"
                ].values[0]
            for i, normalized_pos in enumerate(positions):
                slice_id = f"{entity_name}_{slice_type}_grid_{i}"
                if slice_id in self.slice_actors:
                    print(f"Slice {slice_id} already exists, skipping")
                    continue
                try:
                    if slice_type == "X":
                        pos = min_val + normalized_pos * (max_val - min_val)
                        slice_data = entity.slice(normal="x", origin=[pos, 0, 0])
                    elif slice_type == "Y":
                        pos = min_val + normalized_pos * (max_val - min_val)
                        slice_data = entity.slice(normal="y", origin=[0, pos, 0])
                    else:
                        pos = min_val + normalized_pos * (max_val - min_val)
                        slice_data = entity.slice(normal="z", origin=[0, 0, pos])
                    if slice_data.n_points <= 0:
                        print(f"Skipping empty slice at position {normalized_pos}")
                        continue
                    scalar_array = None
                    cmap = None
                    color_RGB = None
                    if not prop_text or prop_text == "none":
                        color_RGB = self._legend_color_for_uid(main_uid)
                    elif prop_text in ["X", "Y", "Z"]:
                        idx = {"X": 0, "Y": 1, "Z": 2}[prop_text]
                        scalar_array = slice_data.points[:, idx]
                        if (
                            hasattr(self.parent, "prop_legend_df")
                            and self.parent.prop_legend_df is not None
                        ):
                            row = self.parent.prop_legend_df[
                                self.parent.prop_legend_df["property_name"] == prop_text
                            ]
                            if not row.empty:
                                cmap = row["colormap"].iloc[0]
                    else:
                        if prop_text in slice_data.array_names:
                            scalar_array = prop_text
                            if (
                                hasattr(self.parent, "prop_legend_df")
                                and self.parent.prop_legend_df is not None
                            ):
                                row = self.parent.prop_legend_df[
                                    self.parent.prop_legend_df["property_name"]
                                    == prop_text
                                ]
                                if not row.empty:
                                    cmap = row["colormap"].iloc[0]
                    actor = self.plotter.add_mesh(
                        slice_data,
                        name=slice_id,
                        scalars=scalar_array,
                        cmap=cmap,
                        clim=(
                            entity.get_data_range(scalar_array)
                            if scalar_array
                            else None
                        ),
                        show_scalar_bar=False,
                        opacity=1.0,
                        interpolate_before_map=True,
                        color=color_RGB,
                    )
                    self.slice_actors[slice_id] = actor
                    try:
                        if hasattr(self, "slice_meta"):
                            self.slice_meta[slice_id] = (entity_name, slice_type)
                    except Exception:
                        pass
                    print(f"Created slice {slice_id}")
                except Exception as e:
                    print(f"Error creating grid slice: {e}")
                    import traceback

                    traceback.print_exc()
                    continue
            self.plotter.render()

        create_btn.clicked.connect(create_grid_slices_sync)
        remove_btn.clicked.connect(remove_grid_slices)

        # Helper functions (shared between both modes)
        # ------------------------------------

        def cleanup_on_close():
            """Clean up all slices and plane widgets when dialog closes"""
            print("Cleaning up mesh slicer resources...")

            # Disable single-slice manipulation to remove plane widgets
            if enable_manipulation.isChecked():
                enable_manipulation.setChecked(False)
                self.toggle_mesh_manipulation(
                    False,
                    u_slider,
                    v_slider,
                    w_slider,
                    u_value,
                    v_value,
                    w_value,
                    entity_combo,
                    u_slice_check,
                    v_slice_check,
                    w_slice_check,
                    update_slice_visualization,
                )

            # Disable multi-slice manipulation to remove plane widgets
            if multi_direct_manip.isChecked():
                multi_direct_manip.setChecked(False)
                # Clean up multi-slice manipulation widgets
                if hasattr(self, "multi_plane_widgets"):
                    for widget in self.multi_plane_widgets:
                        try:
                            if hasattr(widget, "SetEnabled"):
                                widget.SetEnabled(0)
                            if hasattr(self.plotter, "remove_widget"):
                                self.plotter.remove_widget(widget)
                            elif hasattr(self.plotter.iren, "remove_widget"):
                                self.plotter.iren.remove_widget(widget)
                        except Exception as e:
                            print(f"Warning: Error removing widget: {e}")
                    self.multi_plane_widgets = []

            # Remove all slice actors
            for slice_uid, actor in list(self.slice_actors.items()):
                try:
                    print(f"Removing slice {slice_uid}")
                    self.plotter.remove_actor(actor)
                except Exception as e:
                    print(f"Error removing slice {slice_uid}: {e}")
            self.slice_actors = {}
            if hasattr(self, "slice_meta"):
                self.slice_meta = {}

            # Force a final render
            self.plotter.render()

        def get_scalar_and_cmap(pv_object):
            """Get the scalar array and colormap for a PyVista object."""
            scalar_array = None
            cmap = None

            # Try to find a scalar array
            if hasattr(pv_object, "point_data") and len(pv_object.point_data) > 0:
                for name in pv_object.point_data.keys():
                    scalar_array = name
                    break

            # Try to find a colormap
            if (
                scalar_array
                and hasattr(self, "parent")
                and hasattr(self.parent, "prop_legend_df")
            ):
                if self.parent.prop_legend_df is not None:
                    try:
                        prop_row = self.parent.prop_legend_df[
                            self.parent.prop_legend_df["property_name"] == scalar_array
                        ]
                        if not prop_row.empty:
                            cmap = prop_row["colormap"].iloc[0]
                    except Exception as e:
                        print(f"Error getting colormap: {e}")

            return scalar_array, cmap

        def get_dimension_info(entity, slice_type):
            """Get dimension information like real inline/xline numbers if available"""
            try:
                # Convert to PyVista object if needed
                pv_entity = pv.wrap(entity)
                bounds = pv_entity.bounds

                # Get dimensions based on entity type
                dim_size = None
                step_size = None

                # Check if it's a seismic mesh with dimensions property
                if hasattr(pv_entity, "dimensions"):
                    dims = pv_entity.dimensions

                    # For seismic data, use dimension sizes directly
                    if slice_type == "X":
                        min_val, max_val = bounds[0], bounds[1]
                        dim_size = dims[0]  # inline dimension
                        step_size = (
                            (max_val - min_val) / (dim_size - 1) if dim_size > 1 else 1
                        )
                    elif slice_type == "Y":
                        min_val, max_val = bounds[2], bounds[3]
                        dim_size = dims[1]  # crossline dimension
                        step_size = (
                            (max_val - min_val) / (dim_size - 1) if dim_size > 1 else 1
                        )
                    else:  # Z
                        min_val, max_val = bounds[4], bounds[5]
                        dim_size = dims[2]  # z/time/depth dimension
                        step_size = (
                            (max_val - min_val) / (dim_size - 1) if dim_size > 1 else 1
                        )
                else:
                    # Handle different slice types for non-seismic entities
                    if slice_type == "X":
                        min_val, max_val = bounds[0], bounds[1]

                        # Try to get real dimensions if available
                        if hasattr(entity, "U_n") and hasattr(entity, "U_step"):
                            dim_size = entity.U_n
                            step_size = entity.U_step
                    elif slice_type == "Y":
                        min_val, max_val = bounds[2], bounds[3]

                        # Try to get real dimensions if available
                        if hasattr(entity, "V_n") and hasattr(entity, "V_step"):
                            dim_size = entity.V_n
                            step_size = entity.V_step
                    else:  # Z
                        min_val, max_val = bounds[4], bounds[5]

                        # Try to get real dimensions if available
                        if hasattr(entity, "W_n") and hasattr(entity, "W_step"):
                            dim_size = entity.W_n
                            step_size = entity.W_step

                return {
                    "min_val": min_val,
                    "max_val": max_val,
                    "dim_size": dim_size,
                    "step_size": step_size,
                }
            except Exception as e:
                print(f"Error getting dimension info: {e}")
                return {"min_val": 0, "max_val": 1, "dim_size": None, "step_size": None}

        def calculate_real_position(entity, slice_type, normalized_pos):
            """Calculate real position (inline/xline/zslice) from normalized position"""
            info = get_dimension_info(entity, slice_type)

            if info["dim_size"] is not None:
                # For seismic data or mesh with dimensions, calculate real slice number
                # For seismic data, slice numbers typically start from 1
                if hasattr(entity, "dimensions"):
                    # Calculate real inline/xline/zslice number starting from 1
                    real_pos = int(1 + normalized_pos * (info["dim_size"] - 1))
                else:
                    # For non-seismic data with dimensions
                    real_pos = int(normalized_pos * (info["dim_size"] - 1))
                return real_pos
            else:
                # Fall back to showing percentage
                return normalized_pos

        def calculate_normalized_from_real(entity, slice_type, real_pos):
            """Calculate normalized position from real slice number"""
            info = get_dimension_info(entity, slice_type)

            if info["dim_size"] is not None:
                try:
                    # Convert to float instead of int to preserve precision
                    real_pos = float(real_pos)

                    # For seismic data, adjust calculation since slice numbers typically start from 1
                    if hasattr(entity, "dimensions"):
                        # Ensure it's within valid range (1 to dim_size)
                        real_pos = max(1, min(info["dim_size"], real_pos))
                        # Calculate normalized position (accounting for 1-based indexing)
                        normalized_pos = (real_pos - 1) / (info["dim_size"] - 1)
                    else:
                        # For regular data (0-based indexing)
                        real_pos = max(0, min(info["dim_size"] - 1, real_pos))
                        normalized_pos = real_pos / (info["dim_size"] - 1)

                    return normalized_pos
                except ValueError:
                    return 0.5
            else:
                # Try to interpret as a float between 0-1
                try:
                    normalized_pos = float(real_pos)
                    return max(0, min(1, normalized_pos))
                except ValueError:
                    return 0.5

        def update_value_displays(entity_name, slice_type, normalized_pos):
            """Update both the normalized value label and the real position input"""
            if not entity_name:
                return

            entity = self.get_entity_by_name(entity_name)
            if not entity:
                return

            # Get the right input field and value label
            input_field = None
            value_label = None
            if slice_type == "X":
                input_field = u_input
                value_label = u_value
                if hasattr(self, "_updating_u_input") and self._updating_u_input:
                    return
            elif slice_type == "Y":
                input_field = v_input
                value_label = v_value
                if hasattr(self, "_updating_v_input") and self._updating_v_input:
                    return
            else:  # Z
                input_field = w_input
                value_label = w_value
                if hasattr(self, "_updating_w_input") and self._updating_w_input:
                    return

            # Update the normalized value label
            value_label.setText(f"{normalized_pos:.2f}")

            # Calculate real position
            real_pos = calculate_real_position(entity, slice_type, normalized_pos)

            # Only update the input field if it doesn't have focus
            if not input_field.hasFocus():
                if isinstance(real_pos, int):
                    input_field.setText(str(real_pos))
                else:
                    input_field.setText(f"{real_pos:.2f}")

        # Create separate handlers for each input field for more explicit connections
        def on_u_input_entered():
            entity_name = entity_combo.currentText()
            if not entity_name or not u_slice_check.isChecked():
                return

            entity = self.get_entity_by_name(entity_name)
            if not entity:
                return

            try:
                # Store the original user input to preserve it
                original_input = u_input.text()

                # Set flag to prevent recursive updates
                if hasattr(self, "_updating_u_input") and self._updating_u_input:
                    return
                self._updating_u_input = True

                try:
                    normalized_pos = calculate_normalized_from_real(
                        entity, "X", original_input
                    )
                    u_slider.setValue(int(normalized_pos * 100))
                    update_slice_visualization(entity_name, "X", normalized_pos)
                    u_value.setText(f"{normalized_pos:.2f}")

                    # Keep the original user input in the text field
                    u_input.setText(original_input)
                finally:
                    self._updating_u_input = False
            except Exception as e:
                print(f"Error processing U input: {e}")

        def on_v_input_entered():
            entity_name = entity_combo.currentText()
            if not entity_name or not v_slice_check.isChecked():
                return

            entity = self.get_entity_by_name(entity_name)
            if not entity:
                return

            try:
                # Store the original user input to preserve it
                original_input = v_input.text()

                # Set flag to prevent recursive updates
                if hasattr(self, "_updating_v_input") and self._updating_v_input:
                    return
                self._updating_v_input = True

                try:
                    normalized_pos = calculate_normalized_from_real(
                        entity, "Y", original_input
                    )
                    v_slider.setValue(int(normalized_pos * 100))
                    update_slice_visualization(entity_name, "Y", normalized_pos)
                    v_value.setText(f"{normalized_pos:.2f}")

                    # Keep the original user input in the text field
                    v_input.setText(original_input)
                finally:
                    self._updating_v_input = False
            except Exception as e:
                print(f"Error processing V input: {e}")

        def on_w_input_entered():
            entity_name = entity_combo.currentText()
            if not entity_name or not w_slice_check.isChecked():
                return

            entity = self.get_entity_by_name(entity_name)
            if not entity:
                return

            try:
                # Store the original user input to preserve it
                original_input = w_input.text()

                # Set flag to prevent recursive updates
                if hasattr(self, "_updating_w_input") and self._updating_w_input:
                    return
                self._updating_w_input = True

                try:
                    normalized_pos = calculate_normalized_from_real(
                        entity, "Z", original_input
                    )
                    w_slider.setValue(int(normalized_pos * 100))
                    update_slice_visualization(entity_name, "Z", normalized_pos)
                    w_value.setText(f"{normalized_pos:.2f}")

                    # Keep the original user input in the text field
                    w_input.setText(original_input)
                finally:
                    self._updating_w_input = False
            except Exception as e:
                print(f"Error processing W input: {e}")

        # Event handlers
        def update_slice_visualization(
            entity_name,
            slice_type,
            normalized_position,
            fast_update=False,
            specific_slice_id=None,
        ):
            """Update the slice visualization. Can update a specific slice if specific_slice_id is provided."""
            if not entity_name:
                return

            # Use the specific ID if provided, otherwise construct the standard single-slice ID
            slice_uid = (
                specific_slice_id
                if specific_slice_id
                else f"{entity_name}_{slice_type}"
            )

            # ... (rest of the existing update_slice_visualization logic remains the same) ...
            # Get the entity
            entity = self.get_entity_by_name(entity_name)
            if not entity:
                print(f"Entity {entity_name} not found")
                return

            # Determine and persist the current main-mesh property for this entity
            try:
                main_uid = self.get_entity_uid_by_name(entity_name)
                if main_uid is not None:
                    current_prop = self.actors_df.loc[
                        self.actors_df["uid"] == main_uid, "show_property"
                    ].values[0]
                    if not hasattr(self, "slice_prop_by_entity"):
                        self.slice_prop_by_entity = {}
                    self.slice_prop_by_entity[entity_name] = current_prop
            except Exception:
                pass

            try:
                # Convert to PyVista object
                pv_entity = pv.wrap(entity)
                bounds = pv_entity.bounds

                # Calculate the position in world coordinates
                if slice_type == "X":
                    position = bounds[0] + normalized_position * (bounds[1] - bounds[0])
                    slice_data = pv_entity.slice(
                        normal=[1, 0, 0], origin=[position, 0, 0]
                    )
                elif slice_type == "Y":
                    position = bounds[2] + normalized_position * (bounds[3] - bounds[2])
                    slice_data = pv_entity.slice(
                        normal=[0, 1, 0], origin=[0, position, 0]
                    )
                else:  # Z
                    position = bounds[4] + normalized_position * (bounds[5] - bounds[4])
                    slice_data = pv_entity.slice(
                        normal=[0, 0, 1], origin=[0, 0, position]
                    )

                # If slice is empty at extremes, nudge inside bounds slightly to keep it visible
                if slice_data.n_points <= 0:
                    eps = getattr(self, "_slice_edge_epsilon", 1e-6)
                    try:
                        if slice_type == "X":
                            if normalized_position <= 0.0:
                                normalized_position = eps
                            elif normalized_position >= 1.0:
                                normalized_position = 1.0 - eps
                            position = bounds[0] + normalized_position * (
                                bounds[1] - bounds[0]
                            )
                            slice_data = pv_entity.slice(
                                normal=[1, 0, 0], origin=[position, 0, 0]
                            )
                        elif slice_type == "Y":
                            if normalized_position <= 0.0:
                                normalized_position = eps
                            elif normalized_position >= 1.0:
                                normalized_position = 1.0 - eps
                            position = bounds[2] + normalized_position * (
                                bounds[3] - bounds[2]
                            )
                            slice_data = pv_entity.slice(
                                normal=[0, 1, 0], origin=[0, position, 0]
                            )
                        else:
                            if normalized_position <= 0.0:
                                normalized_position = eps
                            elif normalized_position >= 1.0:
                                normalized_position = 1.0 - eps
                            position = bounds[4] + normalized_position * (
                                bounds[5] - bounds[4]
                            )
                            slice_data = pv_entity.slice(
                                normal=[0, 0, 1], origin=[0, 0, position]
                            )
                    except Exception:
                        pass
                    # If still empty, do not hide; keep current actor visible and return
                    if slice_data.n_points <= 0:
                        if slice_uid in self.slice_actors:
                            self.slice_actors[slice_uid].SetVisibility(True)
                        return

                # Store current visibility if the slice exists
                current_visibility = True
                if slice_uid in self.slice_actors:
                    # If updating a specific slice, ensure it remains visible if it was already
                    # Otherwise (single slice mode), visibility is handled by on_check_changed
                    if specific_slice_id:
                        current_visibility = self.slice_actors[
                            slice_uid
                        ].GetVisibility()

                if fast_update and slice_uid in self.slice_actors:
                    # For fast updates (like slider dragging or direct manipulation), just update the existing actor's geometry
                    try:
                        mapper = self.slice_actors[slice_uid].GetMapper()
                        if mapper:
                            # Update the mapper's input data directly
                            mapper.SetInputData(slice_data)
                            mapper.Update()
                        # Ensure visibility is maintained during fast update
                        self.slice_actors[slice_uid].SetVisibility(current_visibility)
                    except Exception as e:
                        print(
                            f"Error in fast update: {e}. Falling back to full update."
                        )
                        fast_update = False  # Fallback

                if not fast_update or slice_uid not in self.slice_actors:
                    # For non-fast updates or when the actor doesn't exist yet,
                    # get fresh scalar and colormap based on the main entity property
                    scalar_array = None
                    cmap = None
                    color_RGB = None
                    try:
                        main_uid = self.get_entity_uid_by_name(entity_name)
                        # Prefer persisted property (in case the UI reverts briefly)
                        current_prop = None
                        if (
                            hasattr(self, "slice_prop_by_entity")
                            and entity_name in self.slice_prop_by_entity
                        ):
                            current_prop = self.slice_prop_by_entity[entity_name]
                        if current_prop is None and main_uid is not None:
                            current_prop = self.actors_df.loc[
                                self.actors_df["uid"] == main_uid, "show_property"
                            ].values[0]
                            # If 'none' or None, keep scalars None
                            if not current_prop or current_prop == "none":
                                color_RGB = self._legend_color_for_uid(main_uid)
                            elif current_prop in ["X", "Y", "Z"]:
                                # derive from slice geometry
                                idx = {"X": 0, "Y": 1, "Z": 2}[current_prop]
                                scalar_array = slice_data.points[:, idx]
                                if (
                                    hasattr(self.parent, "prop_legend_df")
                                    and self.parent.prop_legend_df is not None
                                ):
                                    row = self.parent.prop_legend_df[
                                        self.parent.prop_legend_df["property_name"]
                                        == current_prop
                                    ]
                                    if not row.empty:
                                        cmap = row["colormap"].iloc[0]
                            else:
                                # named data property, rely on dataset arrays
                                if current_prop in slice_data.array_names:
                                    scalar_array = current_prop
                                    if (
                                        hasattr(self.parent, "prop_legend_df")
                                        and self.parent.prop_legend_df is not None
                                    ):
                                        row = self.parent.prop_legend_df[
                                            self.parent.prop_legend_df["property_name"]
                                            == current_prop
                                        ]
                                        if not row.empty:
                                            cmap = row["colormap"].iloc[0]
                    except Exception:
                        pass

                    # Remove existing actor if it exists
                    if slice_uid in self.slice_actors:
                        self.plotter.remove_actor(self.slice_actors[slice_uid])

                    # Create a new actor with the latest scalar properties
                    self.slice_actors[slice_uid] = self.plotter.add_mesh(
                        slice_data,
                        name=slice_uid,
                        scalars=scalar_array,
                        cmap=cmap,
                        clim=(
                            pv_entity.get_data_range(scalar_array)
                            if scalar_array
                            else None
                        ),
                        show_scalar_bar=False,
                        opacity=1.0,
                        interpolate_before_map=True,
                        color=color_RGB,
                    )

                    # Restore visibility
                    self.slice_actors[slice_uid].SetVisibility(current_visibility)

                    # Record/update slice metadata
                    try:
                        if hasattr(self, "slice_meta"):
                            self.slice_meta[slice_uid] = (entity_name, slice_type)
                    except Exception:
                        pass

                # Render only if NOT doing a fast update from manipulation callback
                # Manipulation callbacks often trigger many updates quickly; render once at the end.
                # Let the calling function (toggle_multi_manipulation or slider change) handle final render.
                if not fast_update or not specific_slice_id:
                    self.plotter.render()

            except Exception as e:
                print(f"Error updating slice {slice_uid}: {e}")
                import traceback

                traceback.print_exc()

        # Event handler functions
        def on_manipulation_toggled(state):
            """Handle manipulation toggle state changes"""
            print(f"Manipulation toggle state changed: {state}")
            is_checked = state == 2  # Qt.Checked equals 2
            print(f"Enabling direct manipulation: {is_checked}")

            # Toggle manipulation
            self.toggle_mesh_manipulation(
                is_checked,
                u_slider,
                v_slider,
                w_slider,
                u_value,
                v_value,
                w_value,
                entity_combo,
                u_slice_check,
                v_slice_check,
                w_slice_check,
                update_slice_visualization,
                u_input,
                v_input,
                w_input,
                calculate_real_position=calculate_real_position,
            )

            # When manipulation is turned on for any slice, hide/uncheck main entity
            try:
                if is_checked:
                    entity_name = entity_combo.currentText()
                    # Persist the main-mesh property at toggle time to avoid transient UI races
                    try:
                        if not hasattr(self, "slice_prop_by_entity"):
                            self.slice_prop_by_entity = {}
                        main_uid_tmp = self.get_entity_uid_by_name(entity_name)
                        if main_uid_tmp is not None:
                            self.slice_prop_by_entity[entity_name] = self.actors_df.loc[
                                self.actors_df["uid"] == main_uid_tmp, "show_property"
                            ].values[0]
                    except Exception:
                        pass
                    main_uid = self.get_entity_uid_by_name(entity_name)
                    if main_uid:
                        self.hide_uids([main_uid])
                        coll_name = self.actors_df.loc[
                            self.actors_df["uid"] == main_uid, "collection"
                        ].values[0]
                        self._set_tree_checked_for_uid(coll_name, main_uid, False)
            except Exception:
                pass

        def on_check_changed(check_box, slice_type):
            """Handle slice visibility checkbox changes"""
            entity_name = entity_combo.currentText()
            if not entity_name:
                return

            checked = check_box.isChecked()

            # Update slice visibility
            slice_uid = f"{entity_name}_{slice_type}"
            if slice_uid in self.slice_actors:
                # Update existing slice
                self.slice_actors[slice_uid].SetVisibility(checked)
            elif checked:
                # Create new slice
                norm_pos = None
                if slice_type == "X":
                    norm_pos = u_slider.value() / 100.0
                elif slice_type == "Y":
                    norm_pos = v_slider.value() / 100.0
                else:  # Z
                    norm_pos = w_slider.value() / 100.0

                update_slice_visualization(entity_name, slice_type, norm_pos)
                # After creation, enforce the current main property so all slices sync (no default viridis)
                try:
                    # Build labeled name and reuse helper
                    main_uid = self.get_entity_uid_by_name(entity_name)
                    if main_uid is not None:
                        collection = getattr(
                            self.parent,
                            self.actors_df.loc[
                                self.actors_df["uid"] == main_uid, "collection"
                            ].values[0],
                        )
                        labeled_name = None
                        # Rebuild labeled name using same logic as in on_property_toggled
                        for coll_name, prefix in [
                            ("mesh3d_coll", "Mesh"),
                            ("geol_coll", "Geological"),
                            ("xsect_coll", "Cross-section"),
                            ("boundary_coll", "Boundary"),
                            ("dom_coll", "DOM"),
                            ("image_coll", "Image"),
                            ("well_coll", "Well"),
                            ("fluid_coll", "Fluid"),
                            ("backgrnd_coll", "Background"),
                        ]:
                            if collection.collection_name == coll_name:
                                labeled_name = (
                                    f"{prefix}: {collection.get_uid_name(main_uid)}"
                                )
                                break
                        if labeled_name:
                            # Use persisted property if available, else current actors_df value
                            prop_text = None
                            if (
                                hasattr(self, "slice_prop_by_entity")
                                and labeled_name in self.slice_prop_by_entity
                            ):
                                prop_text = self.slice_prop_by_entity[labeled_name]
                            else:
                                prop_text = self.actors_df.loc[
                                    self.actors_df["uid"] == main_uid, "show_property"
                                ].values[0]
                            self._rebuild_slice_actor(
                                labeled_name, slice_type, enforced_prop=prop_text
                            )
                except Exception:
                    pass

                # Hide/uncheck main entity in collection when slicer is turned on for this entity
                try:
                    main_uid = self.get_entity_uid_by_name(entity_name)
                    if main_uid:
                        # Hide actor and update actors_df
                        self.hide_uids([main_uid])
                        # Reflect in the associated tree checkbox
                        coll_name = self.actors_df.loc[
                            self.actors_df["uid"] == main_uid, "collection"
                        ].values[0]
                        self._set_tree_checked_for_uid(coll_name, main_uid, False)
                except Exception:
                    pass

            # If direct manipulation is enabled, update plane widgets to match currently checked slices
            if enable_manipulation.isChecked():
                # Toggle manipulation on to refresh the widgets with all currently checked slices
                self.toggle_mesh_manipulation(
                    True,
                    u_slider,
                    v_slider,
                    w_slider,
                    u_value,
                    v_value,
                    w_value,
                    entity_combo,
                    u_slice_check,
                    v_slice_check,
                    w_slice_check,
                    update_slice_visualization,
                    u_input,
                    v_input,
                    w_input,
                    is_refresh=True,
                    calculate_real_position=calculate_real_position,
                )

            self.plotter.render()

        def on_slider_changed(slider_type):
            """Handle slider value changes."""
            if (
                hasattr(self, "_updating_visualization")
                and self._updating_visualization
            ):
                return

            entity_name = entity_combo.currentText()
            if not entity_name:
                return

            # Throttle updates for smoother performance
            current_time = time.time()
            if current_time - self.last_slider_update < slider_throttle:
                return

            try:
                self._updating_visualization = True

                normalized_pos = slider_type.value() / 100.0

                # Update the value displays (both normalized and real)
                if slider_type == u_slider:
                    update_value_displays(entity_name, "X", normalized_pos)
                    if u_slice_check.isChecked():
                        update_slice_visualization(
                            entity_name, "X", normalized_pos, fast_update=True
                        )
                elif slider_type == v_slider:
                    update_value_displays(entity_name, "Y", normalized_pos)
                    if v_slice_check.isChecked():
                        update_slice_visualization(
                            entity_name, "Y", normalized_pos, fast_update=True
                        )
                else:  # w_slider
                    update_value_displays(entity_name, "Z", normalized_pos)
                    if w_slice_check.isChecked():
                        update_slice_visualization(
                            entity_name, "Z", normalized_pos, fast_update=True
                        )

                self.last_slider_update = current_time

            finally:
                self._updating_visualization = False

        def initialize_entity_controls(entity_name):
            """Initialize controls when a new entity is selected."""
            if not entity_name:
                return

            entity = self.get_entity_by_name(entity_name)
            if not entity:
                return

            # Uncheck all checkboxes
            u_slice_check.setChecked(False)
            v_slice_check.setChecked(False)
            w_slice_check.setChecked(False)

            # Hide existing slices (still using X, Y, Z for internal identifiers)
            for slice_type in ["X", "Y", "Z"]:
                slice_uid = f"{entity_name}_{slice_type}"
                if slice_uid in self.slice_actors:
                    self.slice_actors[slice_uid].SetVisibility(False)

            # Set default slider positions (middle)
            u_slider.setValue(50)
            v_slider.setValue(50)
            w_slider.setValue(50)

            # Update value displays with default positions
            # Note: using X, Y, Z for internal mapping to U, V, W
            update_value_displays(entity_name, "X", 0.5)  # U direction
            update_value_displays(entity_name, "Y", 0.5)  # V direction
            update_value_displays(entity_name, "Z", 0.5)  # W direction

            # Reset manipulation
            if enable_manipulation.isChecked():
                enable_manipulation.setChecked(False)
                self.toggle_mesh_manipulation(
                    False,
                    u_slider,
                    v_slider,
                    w_slider,
                    u_value,
                    v_value,
                    w_value,
                    entity_combo,
                    u_slice_check,
                    v_slice_check,
                    w_slice_check,
                    update_slice_visualization,
                    u_input,
                    v_input,
                    w_input,
                    is_refresh=True,
                    calculate_real_position=calculate_real_position,
                )

            self.plotter.render()

        # Add manipulation control group
        manipulation_group = QGroupBox("Manipulation Control")
        manipulation_layout = QVBoxLayout()

        enable_manipulation = QCheckBox("Enable Direct Manipulation")
        enable_manipulation.setChecked(False)  # Default to disabled

        # Connect the manipulation toggle
        enable_manipulation.stateChanged.connect(on_manipulation_toggled)

        manipulation_layout.addWidget(enable_manipulation)
        manipulation_group.setLayout(manipulation_layout)
        single_slice_layout.addWidget(manipulation_group)

        # No need to add these groups to the main layout again - they're already in the stacked layout
        # layout.addWidget(entity_group)
        # layout.addWidget(slice_toggle_group)
        # layout.addWidget(position_group)
        # layout.addWidget(manipulation_group)

        # Connect signals
        u_slider.valueChanged.connect(lambda: on_slider_changed(u_slider))
        v_slider.valueChanged.connect(lambda: on_slider_changed(v_slider))
        w_slider.valueChanged.connect(lambda: on_slider_changed(w_slider))

        # Connect text input events to their specific handlers
        u_input.editingFinished.connect(on_u_input_entered)

        v_input.editingFinished.connect(on_v_input_entered)

        w_input.editingFinished.connect(on_w_input_entered)

        u_slice_check.toggled.connect(
            lambda checked: on_check_changed(u_slice_check, "X")
        )
        v_slice_check.toggled.connect(
            lambda checked: on_check_changed(v_slice_check, "Y")
        )
        w_slice_check.toggled.connect(
            lambda checked: on_check_changed(w_slice_check, "Z")
        )

        entity_combo.currentTextChanged.connect(initialize_entity_controls)

        # Mode switching
        # --------------

        def on_mode_switch(mode_index):
            """Handle switching between single and multi slice modes."""
            if mode_index == 0:  # Single slice mode
                # Disable multi-slice manipulation if enabled
                if multi_direct_manip.isChecked():
                    multi_direct_manip.setChecked(False)
                    # Clean up manipulation widgets for multi-slice
                    if hasattr(self, "multi_plane_widgets"):
                        for widget in self.multi_plane_widgets:
                            try:
                                if hasattr(widget, "SetEnabled"):
                                    widget.SetEnabled(0)
                                if hasattr(self.plotter, "remove_widget"):
                                    self.plotter.remove_widget(widget)
                                elif hasattr(self.plotter.iren, "remove_widget"):
                                    self.plotter.iren.remove_widget(widget)
                            except Exception as e:
                                print(f"Warning: Error removing widget: {e}")
                        self.multi_plane_widgets = []
                        self.plotter.render()

                # Hide all multi-slice actors when switching back to single mode
                if hasattr(self, "slice_actors"):
                    for uid, actor in list(self.slice_actors.items()):
                        if "_grid_" in uid:
                            actor.SetVisibility(False)

                # Update the single slice visibility instead
                entity_name = entity_combo.currentText()
                if entity_name:
                    for slice_type, check_box in [
                        ("X", u_slice_check),
                        ("Y", v_slice_check),
                        ("Z", w_slice_check),
                    ]:
                        slice_uid = f"{entity_name}_{slice_type}"
                        if slice_uid in self.slice_actors and check_box.isChecked():
                            self.slice_actors[slice_uid].SetVisibility(True)

            else:  # Multi-slice mode
                # Disable single-slice manipulation if enabled
                if enable_manipulation.isChecked():
                    enable_manipulation.setChecked(False)
                    self.toggle_mesh_manipulation(
                        False,
                        u_slider,
                        v_slider,
                        w_slider,
                        u_value,
                        v_value,
                        w_value,
                        entity_combo,
                        u_slice_check,
                        v_slice_check,
                        w_slice_check,
                        update_slice_visualization,
                        u_input,
                        v_input,
                        w_input,
                        calculate_real_position=calculate_real_position,
                    )

                # Hide all single slice actors when switching to multi-slice mode
                entity_name = entity_combo.currentText()
                if entity_name and hasattr(self, "slice_actors"):
                    for slice_type in ["X", "Y", "Z"]:
                        slice_uid = f"{entity_name}_{slice_type}"
                        if slice_uid in self.slice_actors:
                            self.slice_actors[slice_uid].SetVisibility(False)

            self.plotter.render()

        # Connect mode switch signals
        single_mode_radio.toggled.connect(
            lambda checked: on_mode_switch(0) if checked else None
        )
        multi_mode_radio.toggled.connect(
            lambda checked: on_mode_switch(1) if checked else None
        )

        # Set up dialog
        control_panel.setLayout(layout)
        control_panel.show()

        # Expose key widgets and helpers for external callers (e.g., tree context menus)
        control_panel.single_entity_combo = entity_combo
        control_panel.multi_entity_combo = multi_entity_combo
        control_panel.initialize_entity_controls = initialize_entity_controls

        # Add this after creating the control_panel
        control_panel.finished.connect(cleanup_on_close)
        # Maintain singleton reference and clean it up on close/destroy
        try:
            self.mesh_slicer_dialog = control_panel
            control_panel.finished.connect(
                lambda _result: setattr(self, "mesh_slicer_dialog", None)
            )
            control_panel.destroyed.connect(
                lambda _obj=None: setattr(self, "mesh_slicer_dialog", None)
            )
        except Exception:
            pass

        # Initialize controls for the current entity
        if entity_combo.count() > 0:
            initialize_entity_controls(entity_combo.currentText())

        return control_panel

    def getSliceableEntities(self):
        """Get list of entities that can be sliced from all collections."""
        sliceable_entities = []

        # Define sliceable topologies
        sliceable_topologies = [
            "Seismics",  # For seismic data
            "TetraSolid",  # For volumetric meshes
            "Voxet",  # For voxel data
            "XsVoxet",  # For cross-section voxel data
            "Image3D",  # For 3D image data
        ]

        # Directly access parent's collections if they exist
        try:
            # Try image collection first - most likely to have Seismics
            if hasattr(self.parent, "image_coll"):
                for _, row in self.parent.image_coll.df.iterrows():
                    if row["topology"] in sliceable_topologies:
                        sliceable_entities.append(f"Image: {row['name']}")

            # Try mesh3d collection
            if hasattr(self.parent, "mesh3d_coll"):
                for _, row in self.parent.mesh3d_coll.df.iterrows():
                    if row["topology"] in sliceable_topologies:
                        sliceable_entities.append(f"Mesh: {row['name']}")

            # Try other collections
            for coll_name, prefix in [
                ("geol_coll", "Geological"),
                ("dom_coll", "DOM"),
                ("xsect_coll", "Cross-section"),
                ("boundary_coll", "Boundary"),
                ("fluid_coll", "Fluid"),
                ("well_coll", "Well"),
                ("backgrnd_coll", "Background"),
            ]:
                if hasattr(self.parent, coll_name):
                    collection = getattr(self.parent, coll_name)
                    if hasattr(collection, "df"):
                        for _, row in collection.df.iterrows():
                            if (
                                "topology" in row
                                and row["topology"] in sliceable_topologies
                            ):
                                sliceable_entities.append(f"{prefix}: {row['name']}")

        except Exception as e:
            self.print_terminal(f"Error getting sliceable entities: {str(e)}")
            print(f"Error getting sliceable entities: {str(e)}")

        return sliceable_entities

    def get_entity_by_name(self, name):
        """Get entity object by name from any collection."""
        try:
            # Split the prefix and actual name
            if ":" not in name:
                print("Error: Name doesn't contain a prefix")
                return None

            prefix, entity_name = name.split(": ", 1)
            print(f"Looking for entity: {entity_name} in {prefix} collection")

            # Map prefix to collection attribute name
            collection_map = {
                "Mesh": "mesh3d_coll",
                "Geological": "geol_coll",
                "Cross-section": "xsect_coll",
                "Boundary": "boundary_coll",
                "DOM": "dom_coll",
                "Image": "image_coll",
                "Well": "well_coll",
                "Fluid": "fluid_coll",
                "Background": "backgrnd_coll",
            }

            coll_name = collection_map.get(prefix)
            if not coll_name:
                print(f"Error: Unknown prefix '{prefix}'")
                return None

            # Get the collection and entity
            if hasattr(self.parent, coll_name):
                collection = getattr(self.parent, coll_name)

                # Handle different method names in different collections
                if hasattr(collection, "get_uid_by_name"):
                    uid = collection.get_uid_by_name(entity_name)
                elif hasattr(collection, "get_name_uid"):
                    uid_list = collection.get_name_uid(entity_name)
                    uid = uid_list[0] if uid_list else None
                else:
                    # Try direct lookup in the dataframe
                    matching_rows = collection.df[collection.df["name"] == entity_name]
                    if not matching_rows.empty:
                        uid = matching_rows.iloc[0]["uid"]
                    else:
                        uid = None

                if uid:
                    vtk_obj = collection.get_uid_vtk_obj(uid)
                    return vtk_obj
        except Exception as e:
            self.print_terminal(f"Error getting entity: {str(e)}")
            print(f"Error getting entity: {str(e)}")

        return None

    def get_entity_uid_by_name(self, name):
        """Return the uid for an entity label like 'Mesh: Name'."""
        try:
            if ":" not in name:
                return None
            prefix, entity_name = name.split(": ", 1)
            collection_map = {
                "Mesh": "mesh3d_coll",
                "Geological": "geol_coll",
                "Cross-section": "xsect_coll",
                "Boundary": "boundary_coll",
                "DOM": "dom_coll",
                "Image": "image_coll",
                "Well": "well_coll",
                "Fluid": "fluid_coll",
                "Background": "backgrnd_coll",
            }
            coll_name = collection_map.get(prefix)
            if not coll_name or not hasattr(self.parent, coll_name):
                return None
            collection = getattr(self.parent, coll_name)
            if hasattr(collection, "get_uid_by_name"):
                return collection.get_uid_by_name(entity_name)
            if hasattr(collection, "get_name_uid"):
                uid_list = collection.get_name_uid(entity_name)
                return uid_list[0] if uid_list else None
            matching_rows = collection.df[collection.df["name"] == entity_name]
            if not matching_rows.empty:
                return matching_rows.iloc[0]["uid"]
        except Exception:
            return None
        return None

    def _set_tree_checked_for_uid(self, coll_name, uid, checked: bool):
        """Programmatically set the checkbox state in the collection tree for a given uid."""
        try:
            # Resolve the tree widget from the collection name
            tree_name = self.collection_tree_dict.get(coll_name)
            if not tree_name:
                return
            tree = getattr(self, tree_name, None)
            if not tree:
                return
            # Block signals to avoid feedback loops
            tree.blockSignals(True)
            for item in tree.findItems("", Qt.MatchContains | Qt.MatchRecursive):
                if tree.get_item_uid(item) == uid:
                    item.setCheckState(0, Qt.Checked if checked else Qt.Unchecked)
                    break
            tree.blockSignals(False)
            # Emit consolidated state to keep view in sync
            tree.emit_checkbox_toggled()
        except Exception:
            pass

    def _legend_color_for_uid(self, uid):
        """Return normalized RGB color for an entity uid based on its collection legend."""
        try:
            coll_name = self.actors_df.loc[
                self.actors_df["uid"] == uid, "collection"
            ].values[0]
            collection = getattr(self.parent, coll_name)
            if coll_name in ["geol_coll", "fluid_coll", "backgrnd_coll", "well_coll"]:
                leg = collection.get_uid_legend(uid=uid)
            else:
                leg = collection.get_legend()
            r = leg["color_R"] / 255
            g = leg["color_G"] / 255
            b = leg["color_B"] / 255
            return [r, g, b]
        except Exception:
            return None

    def initialize_menu_tools(self):
        """Add 3D-specific menu tools."""
        # Call parent's initialize_menu_tools first to ensure menus and toolbars are created
        super().initialize_menu_tools()

        # Remove 2D line drawing from 3D view (use "Draw line (3D mode)" instead)
        if hasattr(self, "drawLineButton"):
            self.drawLineButton.setEnabled(False)
            self.drawLineButton.setVisible(False)
            if hasattr(self, "menuCreate"):
                self.menuCreate.removeAction(self.drawLineButton)

        # Re-add 3D line drawing with point-picking (ensure proper connection)
        if hasattr(self, "drawLine3DButton") and hasattr(self, "menuCreate"):
            self.menuCreate.removeAction(self.drawLine3DButton)
        from ..two_d_lines import draw_line_3d

        self.drawLine3DButton = QAction("Draw line (3D mode)", self)
        self.drawLine3DButton.triggered.connect(lambda: draw_line_3d(self))
        self.menuCreate.addAction(self.drawLine3DButton)

        self.actionExtendSurface = QAction("Extend surface", self)
        self.actionExtendSurface.triggered.connect(self.open_extend_surface_dialog)
        self.menuModify.addAction(self.actionExtendSurface)

        # Create Mesh Tools menu if it doesn't exist
        if not hasattr(self, "menuMeshTools"):
            self.menuMeshTools = QMenu("Mesh Tools", self)
            self.menuBar().addMenu(self.menuMeshTools)

        # Add unified mesh slicer action
        self.actionMeshSlicer = QAction("Mesh Slicer", self)
        self.actionMeshSlicer.triggered.connect(self.show_mesh_slicer_dialog)

        # Add to menu
        self.menuMeshTools.addAction(self.actionMeshSlicer)

    def open_extend_surface_dialog(self):
        """Open a live-preview tool to extend the selected geological surface/line."""
        uid = self._resolve_extend_surface_selection()
        if not uid:
            return
        vtk_obj = self.parent.geol_coll.get_uid_vtk_obj(uid)
        topology = self.parent.geol_coll.get_uid_topology(uid)
        role = self.parent.geol_coll.get_uid_role(uid)
        name = self.parent.geol_coll.get_uid_name(uid)

        if topology not in ["TriSurf", "PolyLine"]:
            self.print_terminal(
                "Extend surface currently supports geological TriSurf and PolyLine objects only."
            )
            return

        if hasattr(self, "extend_surface_dialog") and self.extend_surface_dialog:
            try:
                self.extend_surface_dialog.close()
            except Exception:
                pass

        default_distance = self._default_extension_distance(vtk_obj=vtk_obj)
        default_vector = (
            self._default_extension_vector(
                vtk_obj=vtk_obj, topology=topology, role=role
            )
            * default_distance
        )
        vector_limit = max(default_distance * 20.0, 10.0)

        dialog = QDialog(self)
        dialog.setModal(False)
        dialog.setWindowTitle("Extend surface")
        dialog.resize(460, 280)
        layout = QVBoxLayout(dialog)

        info_group = QGroupBox("Selection", dialog)
        info_layout = QVBoxLayout(info_group)
        role_txt = role if role else "undef"
        info_layout.addWidget(QLabel(f"{name} [{topology}]"))
        info_layout.addWidget(
            QLabel(
                "Enter real X/Y/Z extension values. Faults default to Z growth; horizons/polylines default to XY growth."
            )
        )
        info_layout.addWidget(QLabel(f"Role: {role_txt}"))
        layout.addWidget(info_group)

        direction_group = QGroupBox("Extension Vector", dialog)
        direction_layout = QVBoxLayout(direction_group)

        spin_layout = QHBoxLayout()
        x_spin = QDoubleSpinBox(direction_group)
        y_spin = QDoubleSpinBox(direction_group)
        z_spin = QDoubleSpinBox(direction_group)
        for label_txt, spin, value in [
            ("X", x_spin, default_vector[0]),
            ("Y", y_spin, default_vector[1]),
            ("Z", z_spin, default_vector[2]),
        ]:
            spin.setRange(-vector_limit, vector_limit)
            spin.setDecimals(3)
            spin.setSingleStep(max(default_distance / 10.0, 0.1))
            spin.setValue(float(value))
            col = QVBoxLayout()
            col.addWidget(QLabel(label_txt))
            col.addWidget(spin)
            spin_layout.addLayout(col)
        direction_layout.addLayout(spin_layout)

        preset_layout = QHBoxLayout()
        role_button = QPushButton("Role default", direction_group)
        x_button = QPushButton("+X", direction_group)
        y_button = QPushButton("+Y", direction_group)
        z_button = QPushButton("+Z", direction_group)
        preset_layout.addWidget(role_button)
        preset_layout.addWidget(x_button)
        preset_layout.addWidget(y_button)
        preset_layout.addWidget(z_button)
        direction_layout.addLayout(preset_layout)
        layout.addWidget(direction_group)

        options_group = QGroupBox("Extension", dialog)
        options_layout = QVBoxLayout(options_group)

        distance_layout = QHBoxLayout()
        distance_layout.addWidget(QLabel("Scale"))
        distance_spin = QDoubleSpinBox(options_group)
        distance_spin.setDecimals(3)
        distance_spin.setRange(0.0, 1_000.0)
        distance_spin.setSingleStep(0.25)
        distance_spin.setValue(1.0)
        distance_layout.addWidget(distance_spin)
        options_layout.addLayout(distance_layout)

        side_layout = QHBoxLayout()
        side_layout.addWidget(QLabel("Side"))
        side_combo = QComboBox(options_group)
        if topology == "TriSurf":
            side_combo.addItem("Positive boundary", "positive")
            side_combo.addItem("Negative boundary", "negative")
            side_combo.addItem("Both boundaries", "both")
            side_combo.setCurrentIndex(2)
        else:
            side_combo.addItem("End", "positive")
            side_combo.addItem("Start", "negative")
            side_combo.addItem("Both ends", "both")
            side_combo.setCurrentIndex(2)
        side_layout.addWidget(side_combo)
        options_layout.addLayout(side_layout)

        live_preview_check = QCheckBox("Live preview", options_group)
        live_preview_check.setChecked(True)
        options_layout.addWidget(live_preview_check)
        layout.addWidget(options_group)

        buttons_layout = QHBoxLayout()
        apply_button = QPushButton("Apply", dialog)
        close_button = QPushButton("Close", dialog)
        buttons_layout.addWidget(apply_button)
        buttons_layout.addWidget(close_button)
        layout.addLayout(buttons_layout)

        def set_vector(vector):
            x_spin.blockSignals(True)
            y_spin.blockSignals(True)
            z_spin.blockSignals(True)
            x_spin.setValue(float(vector[0]))
            y_spin.setValue(float(vector[1]))
            z_spin.setValue(float(vector[2]))
            x_spin.blockSignals(False)
            y_spin.blockSignals(False)
            z_spin.blockSignals(False)
            update_preview()

        def get_vector():
            return np_array(
                [x_spin.value(), y_spin.value(), z_spin.value()],
                dtype=float,
            )

        def update_preview():
            if not live_preview_check.isChecked():
                self._cleanup_extend_surface_preview()
                return
            preview_obj = self._build_extension_preview_geometry(
                vtk_obj=vtk_obj,
                topology=topology,
                direction=get_vector(),
                distance=float(distance_spin.value()),
                side=side_combo.currentData(),
            )
            self._show_extend_surface_preview(uid=uid, vtk_obj=preview_obj)

        role_button.clicked.connect(
            lambda: set_vector(
                self._default_extension_vector(
                    vtk_obj=vtk_obj, topology=topology, role=role
                )
                * default_distance
            )
        )
        x_button.clicked.connect(
            lambda: set_vector(np_array([default_distance, 0.0, 0.0]))
        )
        y_button.clicked.connect(
            lambda: set_vector(np_array([0.0, default_distance, 0.0]))
        )
        z_button.clicked.connect(
            lambda: set_vector(np_array([0.0, 0.0, default_distance]))
        )

        for spin in [x_spin, y_spin, z_spin, distance_spin]:
            spin.valueChanged.connect(update_preview)
        side_combo.currentIndexChanged.connect(update_preview)
        live_preview_check.toggled.connect(update_preview)

        def apply_extension():
            out_obj = self._build_extended_geology_entity(
                vtk_obj=vtk_obj,
                topology=topology,
                direction=get_vector(),
                distance=float(distance_spin.value()),
                side=side_combo.currentData(),
            )
            if out_obj is None:
                return
            self._cleanup_extend_surface_preview()
            self.parent.geol_coll.replace_vtk(uid=uid, vtk_object=out_obj)
            dialog.close()

        def close_dialog():
            self._cleanup_extend_surface_preview()
            dialog.close()

        def dialog_finished(*_args):
            self._cleanup_extend_surface_preview()
            if getattr(self, "extend_surface_dialog", None) is dialog:
                self.extend_surface_dialog = None

        apply_button.clicked.connect(apply_extension)
        close_button.clicked.connect(close_dialog)
        dialog.finished.connect(dialog_finished)

        self.extend_surface_dialog = dialog
        update_preview()
        dialog.show()

    def _resolve_extend_surface_selection(self):
        """Resolve a single selected geology uid from the view, tree, or geology table."""
        candidate_uids = []

        try:
            for uid in self.selected_uids:
                rows = self.actors_df.loc[self.actors_df["uid"] == uid, "collection"].values
                if len(rows) > 0 and rows[0] == "geol_coll":
                    candidate_uids.append(uid)
        except Exception:
            pass

        try:
            candidate_uids.extend(list(self.parent.geol_coll.selected_uids))
        except Exception:
            pass

        try:
            selection_model = self.parent.GeologyTableView.selectionModel()
            if selection_model is not None:
                selected_rows = selection_model.selectedRows(column=0)
                candidate_uids.extend(
                    [idx.data() for idx in selected_rows if idx and idx.data()]
                )
        except Exception:
            pass

        candidate_uids = [uid for uid in candidate_uids if uid in self.parent.geol_coll.get_uids]
        unique_uids = list(dict.fromkeys(candidate_uids))

        if len(unique_uids) == 1:
            return unique_uids[0]

        if len(unique_uids) == 0:
            self.print_terminal(
                "Select one geological TriSurf or PolyLine in the 3D view, geology tree, or Geology table."
            )
            return None

        self.print_terminal(
            "Extend surface needs exactly one geological entity selected."
        )
        return None

    def _make_unit_vector(self, vector):
        """Return a normalized direction vector or None for zero-length input."""
        vector = np_asarray(vector, dtype=float).reshape(3)
        magnitude = np_linalg.norm(vector)
        if magnitude <= 1e-9:
            return None
        return vector / magnitude

    def _resolve_extension_displacement(self, direction=None, distance=1.0):
        """Convert UI values into a displacement vector and its normalized direction."""
        base_vector = np_asarray(direction, dtype=float).reshape(3)
        scale = float(distance)
        displacement_vector = base_vector * scale
        magnitude = float(np_linalg.norm(displacement_vector))
        if magnitude <= 1e-9:
            return None, None, 0.0
        return displacement_vector / magnitude, displacement_vector, magnitude

    def _default_extension_distance(self, vtk_obj):
        """Choose a moderate default extension distance from object size."""
        try:
            bounds = vtk_obj.bounds
            extents = np_array(
                [
                    bounds[1] - bounds[0],
                    bounds[3] - bounds[2],
                    bounds[5] - bounds[4],
                ],
                dtype=float,
            )
            scale = float(np_max(extents))
            if scale <= 0.0:
                return 1.0
            return max(scale * 0.15, 1.0)
        except Exception:
            return 1.0

    def _default_extension_vector(self, vtk_obj=None, topology=None, role=None):
        """Return a role-aware initial direction for the extension tool."""
        role = (role or "undef").lower()
        fault_roles = {"fault", "tectonic", "intrusive", "unconformity"}
        horizon_roles = {
            "top",
            "base",
            "bedding",
            "tm_unit",
            "ts_unit",
            "int_unit",
            "formation",
        }

        if topology == "TriSurf" and role in fault_roles:
            return np_array([0.0, 0.0, 1.0], dtype=float)

        if topology == "PolyLine":
            try:
                parts = vtk_obj.split_parts()
            except Exception:
                parts = None
            if not parts:
                parts = [vtk_obj]
            longest_part = None
            longest_length = -1.0
            for part in parts:
                try:
                    ordered = part.deep_copy()
                    ordered.poly2lines()
                    ordered.sort_nodes()
                    points = np_asarray(ordered.points, dtype=float)
                except Exception:
                    points = np_asarray(part.points, dtype=float)
                if points.shape[0] < 2:
                    continue
                segment_lengths = np_linalg.norm(
                    np_diff(points[:, :2], axis=0), axis=1
                )
                part_length = float(np_sum(segment_lengths))
                if part_length > longest_length:
                    longest_length = part_length
                    longest_part = points
            if longest_part is not None:
                vector = longest_part[-1] - longest_part[0]
                if role in horizon_roles:
                    vector[2] = 0.0
                unit_vector = self._make_unit_vector(vector)
                if unit_vector is not None:
                    return unit_vector

        try:
            bounds = vtk_obj.bounds
            extents = np_array(
                [
                    bounds[1] - bounds[0],
                    bounds[3] - bounds[2],
                    bounds[5] - bounds[4],
                ],
                dtype=float,
            )
            if topology == "TriSurf" and role not in fault_roles:
                axis = 0 if extents[0] >= extents[1] else 1
            else:
                axis = int(np_argmax(extents))
            vector = np_zeros(3, dtype=float)
            vector[axis] = 1.0
            return vector
        except Exception:
            return np_array([1.0, 0.0, 0.0], dtype=float)

    def _show_extend_surface_preview(self, uid=None, vtk_obj=None):
        """Render the preview geometry for the extend tool."""
        self._cleanup_extend_surface_preview()
        if vtk_obj is None or vtk_obj.GetNumberOfPoints() <= 0:
            return

        preview_name = "__extend_surface_preview__"
        color = self._legend_color_for_uid(uid) or [1.0, 0.85, 0.15]
        kwargs = {
            "name": preview_name,
            "color": color,
            "pickable": False,
        }
        if isinstance(vtk_obj, TriSurf):
            kwargs["opacity"] = 0.45
            kwargs["show_edges"] = True
        else:
            kwargs["line_width"] = 8
            kwargs["render_lines_as_tubes"] = True
        self.plotter.add_mesh(vtk_obj, **kwargs)
        self.plotter.render()

    def _cleanup_extend_surface_preview(self):
        """Remove any temporary extension preview actor."""
        preview_name = "__extend_surface_preview__"
        try:
            if preview_name in self.plotter.renderer.actors:
                self.plotter.remove_actor(preview_name)
                self.plotter.render()
        except Exception:
            pass

    def _build_extension_preview_geometry(
        self, vtk_obj=None, topology=None, direction=None, distance=0.0, side=None
    ):
        """Build preview-only geometry for the extension tool."""
        if topology == "TriSurf":
            return self._build_extended_trisurf(
                vtk_obj=vtk_obj,
                direction=direction,
                distance=distance,
                side=side,
                preview_only=True,
            )
        if topology == "PolyLine":
            return self._build_extended_polyline(
                vtk_obj=vtk_obj,
                direction=direction,
                distance=distance,
                side=side,
                preview_only=True,
            )
        return None

    def _build_extended_geology_entity(
        self, vtk_obj=None, topology=None, direction=None, distance=0.0, side=None
    ):
        """Build the final geometry to replace the selected entity."""
        _, displacement_vector, magnitude = self._resolve_extension_displacement(
            direction=direction, distance=distance
        )
        if displacement_vector is None or magnitude <= 0.0:
            self.print_terminal("Set a non-zero extension vector or scale.")
            return None
        if topology == "TriSurf":
            return self._build_extended_trisurf(
                vtk_obj=vtk_obj,
                direction=direction,
                distance=distance,
                side=side,
                preview_only=False,
            )
        if topology == "PolyLine":
            return self._build_extended_polyline(
                vtk_obj=vtk_obj,
                direction=direction,
                distance=distance,
                side=side,
                preview_only=False,
            )
        return None

    def _append_polydata_parts(self, parts=None, topology=None):
        """Append multiple polydata parts while preserving the target topology class."""
        parts = [part for part in (parts or []) if part is not None]
        if not parts:
            return None
        if len(parts) == 1:
            return parts[0]

        append_filter = vtkAppendPolyData()
        for part in parts:
            append_filter.AddInputData(part)
        append_filter.Update()

        if topology == "TriSurf":
            out_obj = TriSurf()
        else:
            out_obj = PolyLine()
        out_obj.DeepCopy(append_filter.GetOutput())
        return out_obj

    def _build_extended_polyline(
        self, vtk_obj=None, direction=None, distance=0.0, side=None, preview_only=False
    ):
        """Extend the selected polyline at its ends."""
        _, displacement_vector, _ = self._resolve_extension_displacement(
            direction=direction, distance=distance
        )
        if displacement_vector is None:
            self.print_terminal("Set a non-zero extension vector.")
            return None

        try:
            parts = vtk_obj.split_parts()
        except Exception:
            parts = None
        if not parts:
            parts = [vtk_obj.deep_copy()]

        output_parts = []
        preview_parts = []

        for raw_part in parts:
            try:
                part = raw_part.deep_copy()
            except Exception:
                part = raw_part

            try:
                part.poly2lines()
                part.sort_nodes()
            except Exception:
                pass

            points = np_asarray(part.points, dtype=float)
            if points.shape[0] < 2:
                continue

            new_points = points.copy()
            point_data = {}
            for key in part.point_data_keys:
                components = part.get_point_data_shape(key)[1]
                array = np_asarray(part.get_point_data(key))
                point_data[key] = array.reshape(points.shape[0], components).copy()

            if side in ["negative", "both"]:
                start_point = points[0] - displacement_vector
                new_points = np_vstack((start_point, new_points))
                for key in point_data:
                    point_data[key] = np_vstack((point_data[key][0:1], point_data[key]))
                preview = PolyLine()
                preview.points = np_vstack((points[0], start_point))
                preview.auto_cells()
                preview_parts.append(preview)

            if side in ["positive", "both"]:
                end_point = points[-1] + displacement_vector
                new_points = np_vstack((new_points, end_point))
                for key in point_data:
                    point_data[key] = np_vstack((point_data[key], point_data[key][-1:]))
                preview = PolyLine()
                preview.points = np_vstack((points[-1], end_point))
                preview.auto_cells()
                preview_parts.append(preview)

            new_part = PolyLine()
            new_part.points = new_points
            new_part.auto_cells()
            for key, array in point_data.items():
                if array.shape[1] == 1:
                    new_part.set_point_data(key, array.reshape(-1))
                else:
                    new_part.set_point_data(key, array)
            output_parts.append(new_part)

        if preview_only:
            return self._append_polydata_parts(preview_parts, topology="PolyLine")
        return self._append_polydata_parts(output_parts, topology="PolyLine")

    def _collect_trisurf_boundary_edges(self, vtk_obj=None):
        """Return boundary edges as pairs of point ids on the cleaned TriSurf."""
        id_obj = TriSurf()
        id_obj.DeepCopy(vtk_obj)
        id_obj.ids_to_scalar()

        boundary_filter = vtkFeatureEdges()
        boundary_filter.BoundaryEdgesOn()
        boundary_filter.NonManifoldEdgesOff()
        boundary_filter.FeatureEdgesOff()
        boundary_filter.ManifoldEdgesOff()
        boundary_filter.SetInputData(id_obj)
        boundary_filter.Update()

        boundary = pv.wrap(boundary_filter.GetOutput())
        if boundary.n_points <= 0 or boundary.n_lines <= 0:
            return np_empty((0, 2), dtype=int)

        line_cells = np_asarray(boundary.lines).reshape((-1, 3))[:, 1:3]
        original_ids = np_asarray(boundary.point_data["vtkIdFilter_Ids"], dtype=int)
        return original_ids[line_cells]

    def _order_trisurf_boundary_components(self, boundary_edges=None):
        """Return ordered boundary point-id sequences for each connected edge component."""
        if boundary_edges is None or boundary_edges.shape[0] == 0:
            return []

        adjacency = {}
        edge_keys = []
        for edge in boundary_edges:
            p0 = int(edge[0])
            p1 = int(edge[1])
            edge_key = (p0, p1) if p0 <= p1 else (p1, p0)
            edge_keys.append(edge_key)
            adjacency.setdefault(p0, []).append(p1)
            adjacency.setdefault(p1, []).append(p0)

        edge_to_component = {}
        components = []
        visited_edges = set()
        for edge_key in edge_keys:
            if edge_key in visited_edges:
                continue

            stack = [edge_key]
            component_edges = set()
            component_points = set()
            while stack:
                current_edge = stack.pop()
                if current_edge in visited_edges:
                    continue
                visited_edges.add(current_edge)
                component_edges.add(current_edge)
                p0, p1 = current_edge
                component_points.update([p0, p1])
                for point_id in current_edge:
                    for neighbor in adjacency.get(point_id, []):
                        next_edge = (
                            (point_id, neighbor)
                            if point_id <= neighbor
                            else (neighbor, point_id)
                        )
                        if next_edge not in visited_edges:
                            stack.append(next_edge)

            endpoints = [
                point_id
                for point_id in component_points
                if len(adjacency.get(point_id, [])) == 1
            ]
            start_point = endpoints[0] if endpoints else min(component_points)

            ordered_points = [start_point]
            previous_point = None
            current_point = start_point
            remaining_edges = set(component_edges)
            while remaining_edges:
                next_point = None
                for neighbor in adjacency.get(current_point, []):
                    edge_key = (
                        (current_point, neighbor)
                        if current_point <= neighbor
                        else (neighbor, current_point)
                    )
                    if edge_key in remaining_edges and neighbor != previous_point:
                        next_point = neighbor
                        break
                if next_point is None:
                    for neighbor in adjacency.get(current_point, []):
                        edge_key = (
                            (current_point, neighbor)
                            if current_point <= neighbor
                            else (neighbor, current_point)
                        )
                        if edge_key in remaining_edges:
                            next_point = neighbor
                            break
                if next_point is None:
                    break

                edge_key = (
                    (current_point, next_point)
                    if current_point <= next_point
                    else (next_point, current_point)
                )
                remaining_edges.remove(edge_key)
                ordered_points.append(next_point)
                previous_point, current_point = current_point, next_point
                if current_point == start_point:
                    break

            if len(ordered_points) >= 2:
                components.append(ordered_points)

        return components

    def _build_trisurf_selection_frame(
        self, points=None, selection_unit=None, surface_normal=None
    ):
        """Build a 2D frame on the surface with U aligned to extension direction in-plane."""
        if points is None or selection_unit is None:
            return None, None, None, None

        selection_unit = self._make_unit_vector(selection_unit)
        if selection_unit is None:
            return None, None, None, None

        if surface_normal is None:
            _, surface_normal = best_fitting_plane(points)
        surface_normal = self._make_unit_vector(surface_normal)
        if surface_normal is None:
            return None, None, None, None

        axis_u = selection_unit - np_dot(selection_unit, surface_normal) * surface_normal
        axis_u = self._make_unit_vector(axis_u)
        if axis_u is None:
            for candidate in [
                np_array([1.0, 0.0, 0.0], dtype=float),
                np_array([0.0, 1.0, 0.0], dtype=float),
                np_array([0.0, 0.0, 1.0], dtype=float),
            ]:
                projected = candidate - np_dot(candidate, surface_normal) * surface_normal
                axis_u = self._make_unit_vector(projected)
                if axis_u is not None:
                    break
        if axis_u is None:
            return None, None, None, None

        axis_v = self._make_unit_vector(np_cross(surface_normal, axis_u))
        if axis_v is None:
            return None, None, None, None

        origin = np_mean(points, axis=0)
        return origin, axis_u, axis_v, surface_normal

    def _select_trisurf_boundary_edge_sets(
        self,
        points=None,
        boundary_edges=None,
        selection_unit=None,
        side=None,
        surface_normal=None,
    ):
        """Select top/bottom boundary edge chains from a 2D projected boundary."""
        if (
            points is None
            or boundary_edges is None
            or boundary_edges.shape[0] == 0
            or selection_unit is None
        ):
            return []

        origin, axis_u, axis_v, _ = self._build_trisurf_selection_frame(
            points=points,
            selection_unit=selection_unit,
            surface_normal=surface_normal,
        )
        if origin is None or axis_u is None or axis_v is None:
            return []

        point_vectors = np_asarray(points, dtype=float) - origin
        point_u = np_asarray(point_vectors @ axis_u, dtype=float)
        point_v = np_asarray(point_vectors @ axis_v, dtype=float)
        ordered_components = self._order_trisurf_boundary_components(boundary_edges)
        if not ordered_components:
            return []

        edge_key_set = {
            (int(edge[0]), int(edge[1])) if int(edge[0]) <= int(edge[1]) else (int(edge[1]), int(edge[0]))
            for edge in boundary_edges
        }

        def ensure_closed_loop(component_point_ids=None):
            if component_point_ids is None or len(component_point_ids) < 3:
                return component_point_ids
            if component_point_ids[0] == component_point_ids[-1]:
                return component_point_ids
            edge_key = (
                (int(component_point_ids[0]), int(component_point_ids[-1]))
                if int(component_point_ids[0]) <= int(component_point_ids[-1])
                else (int(component_point_ids[-1]), int(component_point_ids[0]))
            )
            if edge_key in edge_key_set:
                return component_point_ids + [component_point_ids[0]]
            return component_point_ids

        def chain_edges(loop_point_ids=None, start_idx=None, end_idx=None, forward=True):
            if loop_point_ids is None or len(loop_point_ids) < 2:
                return None
            n_points = len(loop_point_ids) - 1
            if n_points < 2:
                return None
            edges = []
            idx = int(start_idx)
            step = 1 if forward else -1
            while idx != int(end_idx):
                next_idx = (idx + step) % n_points
                p0 = int(loop_point_ids[idx])
                p1 = int(loop_point_ids[next_idx])
                edges.append((p0, p1))
                idx = next_idx
            if not edges:
                return None
            return np_array(edges, dtype=int)

        def score_chain(chain=None):
            if chain is None or chain.shape[0] == 0:
                return None
            mid_u = (point_u[chain[:, 0]] + point_u[chain[:, 1]]) / 2.0
            return float(np_mean(mid_u))

        selected_edge_sets = []
        positive_candidates = []
        negative_candidates = []
        for component_point_ids in ordered_components:
            loop_point_ids = ensure_closed_loop(component_point_ids)
            if loop_point_ids is None or len(loop_point_ids) < 4:
                continue

            loop_v = np_asarray([point_v[int(point_id)] for point_id in loop_point_ids[:-1]])
            top_idx = int(np_argmax(loop_v))
            bottom_idx = int(np_argmin(loop_v))
            if top_idx == bottom_idx:
                continue

            forward_chain = chain_edges(
                loop_point_ids=loop_point_ids,
                start_idx=top_idx,
                end_idx=bottom_idx,
                forward=True,
            )
            backward_chain = chain_edges(
                loop_point_ids=loop_point_ids,
                start_idx=top_idx,
                end_idx=bottom_idx,
                forward=False,
            )
            if forward_chain is None or backward_chain is None:
                continue

            forward_score = score_chain(forward_chain)
            backward_score = score_chain(backward_chain)
            if forward_score is None or backward_score is None:
                continue

            if forward_score >= backward_score:
                positive_candidates.append((forward_chain, forward_score))
                negative_candidates.append((backward_chain, backward_score))
            else:
                positive_candidates.append((backward_chain, backward_score))
                negative_candidates.append((forward_chain, forward_score))

        if side in ["positive", "both"]:
            if positive_candidates:
                selected_edge_sets.append(
                    (max(positive_candidates, key=lambda item: item[1])[0], 1.0)
                )
        if side in ["negative", "both"]:
            if negative_candidates:
                selected_edge_sets.append(
                    (min(negative_candidates, key=lambda item: item[1])[0], -1.0)
                )
        return selected_edge_sets

    def _build_extended_trisurf(
        self, vtk_obj=None, direction=None, distance=0.0, side=None, preview_only=False
    ):
        """Extend a TriSurf by adding ribbons along the selected boundary side(s)."""
        clean_output = vtk_obj.clean_topology()
        clean_trisurf = TriSurf()
        clean_trisurf.DeepCopy(clean_output)

        points = np_asarray(clean_trisurf.points, dtype=float)
        cells = np_asarray(clean_trisurf.cells, dtype=int)
        if points.shape[0] < 3 or cells.shape[0] < 1:
            return None

        unit_vector, displacement_vector, magnitude = self._resolve_extension_displacement(
            direction=direction, distance=distance
        )
        if unit_vector is None or displacement_vector is None or magnitude <= 0.0:
            self.print_terminal("Set a non-zero extension vector.")
            return None

        tri_vectors_1 = points[cells[:, 1]] - points[cells[:, 0]]
        tri_vectors_2 = points[cells[:, 2]] - points[cells[:, 0]]
        tri_normals = np_cross(tri_vectors_1, tri_vectors_2)
        tri_norm_lengths = np_linalg.norm(tri_normals, axis=1)
        valid_normals = tri_normals[tri_norm_lengths > 1e-9]
        if valid_normals.size == 0:
            return None
        average_normal = self._make_unit_vector(np_mean(valid_normals, axis=0))
        if average_normal is None:
            average_normal = np_array([0.0, 0.0, 1.0], dtype=float)

        boundary_edges = self._collect_trisurf_boundary_edges(clean_trisurf)
        if boundary_edges.shape[0] == 0:
            self.print_terminal("The selected TriSurf has no open boundary to extend.")
            return None

        selected_edge_sets = self._select_trisurf_boundary_edge_sets(
            points=points,
            boundary_edges=boundary_edges,
            selection_unit=unit_vector,
            side=side,
            surface_normal=average_normal,
        )

        base_cells = cells.tolist()
        new_cells = list(base_cells)
        point_list = points.tolist()
        preview_points = []
        preview_cells = []
        point_data_lists = {}
        point_data_components = {}
        for key in clean_trisurf.point_data_keys:
            components = clean_trisurf.get_point_data_shape(key)[1]
            point_data_components[key] = components
            array = np_asarray(clean_trisurf.get_point_data(key)).reshape(
                points.shape[0], components
            )
            point_data_lists[key] = array.tolist()

        shifted_point_cache = {}

        def add_shifted_point(point_id, offset_key, offset_vector):
            cache_key = (int(point_id), float(offset_key))
            if cache_key in shifted_point_cache:
                return shifted_point_cache[cache_key]
            new_point = (points[point_id] + offset_vector).tolist()
            point_list.append(new_point)
            new_id = len(point_list) - 1
            for key in point_data_lists:
                point_data_lists[key].append(list(point_data_lists[key][point_id]))
            shifted_point_cache[cache_key] = new_id
            return new_id

        def quad_triangles(idx0, idx1, idx2, idx3, point_source):
            normal_test = np_cross(
                np_asarray(point_source[idx1]) - np_asarray(point_source[idx0]),
                np_asarray(point_source[idx2]) - np_asarray(point_source[idx0]),
            )
            if np_dot(normal_test, average_normal) >= 0.0:
                return [[idx0, idx1, idx2], [idx0, idx2, idx3]]
            return [[idx0, idx2, idx1], [idx0, idx3, idx2]]

        for selected_edges, sign in selected_edge_sets:
            if selected_edges.shape[0] == 0:
                continue
            displacement = displacement_vector * sign
            for edge in selected_edges:
                p0 = int(edge[0])
                p1 = int(edge[1])
                p2 = add_shifted_point(p1, sign, displacement)
                p3 = add_shifted_point(p0, sign, displacement)
                triangles = quad_triangles(p0, p1, p2, p3, point_list)
                new_cells.extend(triangles)

                preview_base = len(preview_points)
                preview_quad = [
                    points[p0],
                    points[p1],
                    points[p1] + displacement,
                    points[p0] + displacement,
                ]
                preview_points.extend([point.tolist() for point in preview_quad])
                preview_cells.extend(
                    quad_triangles(
                        preview_base,
                        preview_base + 1,
                        preview_base + 2,
                        preview_base + 3,
                        preview_points,
                    )
                )

        if preview_only:
            if not preview_points or not preview_cells:
                return None
            preview_obj = TriSurf()
            preview_obj.points = np_asarray(preview_points, dtype=float)
            for cell in preview_cells:
                preview_obj.append_cell(np_asarray(cell, dtype=int))
            preview_obj.Modified()
            return preview_obj

        out_obj = TriSurf()
        out_obj.points = np_asarray(point_list, dtype=float)
        for cell in new_cells:
            out_obj.append_cell(np_asarray(cell, dtype=int))
        for key, values in point_data_lists.items():
            array = np_asarray(values)
            if point_data_components[key] == 1:
                out_obj.set_point_data(key, array.reshape(-1))
            else:
                out_obj.set_point_data(key, array)
        try:
            out_obj.vtk_set_normals()
        except Exception:
            pass
        out_obj.Modified()
        return out_obj

    def toggle_mesh_manipulation(
        self,
        enabled,
        u_slider,
        v_slider,
        w_slider,
        u_value,
        v_value,
        w_value,
        entity_combo,
        u_slice_check,
        v_slice_check,
        w_slice_check,
        update_slice_func=None,
        u_input=None,
        v_input=None,
        w_input=None,
        is_refresh=False,
        calculate_real_position=None,
    ):
        """Toggle mesh manipulation mode."""
        print(
            f"Toggle mesh manipulation called with enabled={enabled}, is_refresh={is_refresh}"
        )

        # Initialize plane_widgets as a list if it doesn't exist
        if not hasattr(self, "plane_widgets"):
            self.plane_widgets = []

        # Define the callback creator function FIRST (before using it)
        def create_callback(slice_type, slider, value_label, value_input):
            def callback(normal, origin):
                # Get entity bounds
                entity_name = entity_combo.currentText()
                entity = self.get_entity_by_name(entity_name)
                if not entity:
                    return

                pv_entity = pv.wrap(entity)
                bounds = pv_entity.bounds

                # Calculate normalized position based on current origin
                normalized_pos = 0
                if slice_type == "X":  # U direction
                    normalized_pos = (
                        (origin[0] - bounds[0]) / (bounds[1] - bounds[0])
                        if bounds[1] > bounds[0]
                        else 0.5
                    )
                elif slice_type == "Y":  # V direction
                    normalized_pos = (
                        (origin[1] - bounds[2]) / (bounds[3] - bounds[2])
                        if bounds[3] > bounds[2]
                        else 0.5
                    )
                elif slice_type == "Z":  # W direction
                    # For W slices with vertical exaggeration, adjust calculation
                    if hasattr(self, "v_exaggeration") and self.v_exaggeration != 1.0:
                        z_mid = (bounds[4] + bounds[5]) / 2
                        # Adjust for vertical exaggeration
                        adjusted_pos = z_mid + (origin[2] - z_mid) / self.v_exaggeration
                        normalized_pos = (adjusted_pos - bounds[4]) / (
                            bounds[5] - bounds[4]
                        )
                    else:
                        normalized_pos = (
                            (origin[2] - bounds[4]) / (bounds[5] - bounds[4])
                            if bounds[5] > bounds[4]
                            else 0.5
                        )

                # Clamp slightly inside [0,1] to prevent disappearing at exact bounds
                eps = getattr(self, "_slice_edge_epsilon", 1e-6)
                if normalized_pos <= 0.0:
                    normalized_pos = eps
                elif normalized_pos >= 1.0:
                    normalized_pos = 1.0 - eps

                # Update slider and label with new position without triggering value changed events
                # This prevents double rendering
                slider.blockSignals(True)
                slider_value = int(normalized_pos * 100)
                slider.setValue(slider_value)
                slider.blockSignals(False)
                value_label.setText(f"{normalized_pos:.2f}")

                # Update the text input with real position if available
                if value_input:
                    # Try to get real position (inline/xline/zslice)
                    try:
                        # Calculate and display real position based on entity type
                        if calculate_real_position:
                            real_pos = calculate_real_position(
                                entity, slice_type, normalized_pos
                            )
                            if isinstance(real_pos, int):
                                value_input.setText(str(real_pos))
                            else:
                                value_input.setText(f"{real_pos:.2f}")
                        else:
                            # Fallback if function not found
                            value_input.setText(f"{normalized_pos:.2f}")
                    except Exception as e:
                        print(
                            f"Error updating text input for {slice_type_to_uvw(slice_type)} direction: {e}"
                        )
                        value_input.setText(f"{normalized_pos:.2f}")

                # Update the slice visualization (always use fast_update for direct manipulation)
                if update_slice_func:
                    update_slice_func(entity_name, slice_type, normalized_pos, True)

            return callback

        # Helper to convert slice type to UVW label
        def slice_type_to_uvw(slice_type):
            if slice_type == "X":
                return "U"
            elif slice_type == "Y":
                return "V"
            else:  # Z
                return "W"

        # Update slider and input states based on manipulation mode
        if not is_refresh:
            self.update_slider_states(
                enabled, u_slider, v_slider, w_slider, u_input, v_input, w_input
            )

        # Clean up existing plane widgets when disabling
        if not enabled:
            self.cleanup_plane_widgets()
            return

        # Get the selected entity
        entity_name = entity_combo.currentText() if entity_combo.currentText() else None
        if not entity_name:
            print("No entity selected")
            return

        # Get the entity object
        entity = self.get_entity_by_name(entity_name)
        if not entity:
            print(f"Entity {entity_name} not found")
            return

        try:
            # Convert to PyVista object and get bounds
            pv_entity = pv.wrap(entity)
            bounds = pv_entity.bounds

            # Get current slider values as normalized positions
            normalized_positions = {
                "X": u_slider.value() / 100.0,
                "Y": v_slider.value() / 100.0,
                "Z": w_slider.value() / 100.0,
            }

            # Clean up any existing plane widgets
            self.cleanup_plane_widgets()

            # Create plane widgets for each checked slice direction
            if u_slice_check.isChecked():
                # Update the real position value for U direction before creating widget
                try:
                    real_pos = calculate_real_position(
                        entity, "X", normalized_positions["X"]
                    )
                    if isinstance(real_pos, int):
                        u_input.setText(str(real_pos))
                    else:
                        u_input.setText(f"{real_pos:.2f}")
                except Exception as e:
                    print(f"Error updating U input: {e}")

                # Use the local create_callback function with text input field
                callback_func = create_callback("X", u_slider, u_value, u_input)

                # Create plane widget for U slice
                widget = self.create_single_plane_widget(
                    "X", normalized_positions["X"], bounds, callback_func
                )
                if widget:
                    self.plane_widgets.append(widget)
                    print(
                        f"Added U plane widget, total widgets: {len(self.plane_widgets)}"
                    )

            if v_slice_check.isChecked():
                # Update the real position value for V direction before creating widget
                try:
                    real_pos = calculate_real_position(
                        entity, "Y", normalized_positions["Y"]
                    )
                    if isinstance(real_pos, int):
                        v_input.setText(str(real_pos))
                    else:
                        v_input.setText(f"{real_pos:.2f}")
                except Exception as e:
                    print(f"Error updating V input: {e}")

                # Use the local create_callback function with text input field
                callback_func = create_callback("Y", v_slider, v_value, v_input)

                # Create plane widget for V slice
                widget = self.create_single_plane_widget(
                    "Y", normalized_positions["Y"], bounds, callback_func
                )
                if widget:
                    self.plane_widgets.append(widget)
                    print(
                        f"Added V plane widget, total widgets: {len(self.plane_widgets)}"
                    )

            if w_slice_check.isChecked():
                # Update the real position value for W direction before creating widget
                try:
                    real_pos = calculate_real_position(
                        entity, "Z", normalized_positions["Z"]
                    )
                    if isinstance(real_pos, int):
                        w_input.setText(str(real_pos))
                    else:
                        w_input.setText(f"{real_pos:.2f}")
                except Exception as e:
                    print(f"Error updating W input: {e}")

                # Use the local create_callback function with text input field
                callback_func = create_callback("Z", w_slider, w_value, w_input)

                # Create plane widget for W slice
                widget = self.create_single_plane_widget(
                    "Z", normalized_positions["Z"], bounds, callback_func
                )
                if widget:
                    self.plane_widgets.append(widget)
                    print(
                        f"Added W plane widget, total widgets: {len(self.plane_widgets)}"
                    )

            # Render the scene to show the widgets
            self.plotter.render()

        except Exception as e:
            print(f"Error toggling mesh manipulation: {e}")
            import traceback

            traceback.print_exc()

    def update_slider_states(
        self,
        enabled,
        u_slider,
        v_slider,
        w_slider,
        u_input=None,
        v_input=None,
        w_input=None,
    ):
        """Update slider and input field states based on manipulation mode"""
        print(f"Updating slider states: enabled={enabled}")
        u_slider.setEnabled(not enabled)
        v_slider.setEnabled(not enabled)
        w_slider.setEnabled(not enabled)

        # Also disable text input fields when in manipulation mode
        if u_input:
            u_input.setEnabled(not enabled)
        if v_input:
            v_input.setEnabled(not enabled)
        if w_input:
            w_input.setEnabled(not enabled)

        # Apply visual indication of disabled state
        style = (
            "QSlider::groove:horizontal {background-color: #cccccc;}" if enabled else ""
        )
        u_slider.setStyleSheet(style)
        v_slider.setStyleSheet(style)
        w_slider.setStyleSheet(style)

    def cleanup_plane_widgets(self):
        """Clean up all plane widgets"""
        if not hasattr(self, "plane_widgets"):
            self.plane_widgets = []
            return

        num_widgets = len(self.plane_widgets)
        if num_widgets > 0:
            print(f"Cleaning up {num_widgets} plane widgets")

        # Remove each plane widget - plane_widgets is a list, not a dict
        for widget in list(self.plane_widgets):
            try:
                if widget is not None:
                    # Try to disable the widget
                    if hasattr(widget, "SetEnabled"):
                        widget.SetEnabled(0)
                    # Try to remove from plotter
                    if hasattr(self.plotter, "remove_widget"):
                        self.plotter.remove_widget(widget)
                    elif hasattr(self.plotter, "clear_widgets"):
                        self.plotter.clear_widgets()
            except Exception as e:
                print(f"Error cleaning up widget: {e}")

        # Clear the list
        self.plane_widgets = []

        # Force render to update display
        self.plotter.render()

    def get_world_positions(self, normalized_positions, bounds):
        """Remove this method as it's now redundant"""
        # This method is redundant as we calculate positions directly in toggle_mesh_manipulation
        pass

        # Add this method to the View3D class

    def update_slices_for_property_change(self, property_name):
        """Update all slices when a property's colormap changes"""
        if not hasattr(self, "slice_actors") or not self.slice_actors:
            return

        print(f"Updating slice visualizations for property '{property_name}'")

        # Update all slices
        for slice_uid, actor in list(self.slice_actors.items()):
            # Retrieve metadata if available, otherwise fallback-parse
            entity_name, slice_type = (None, None)
            if hasattr(self, "slice_meta") and slice_uid in self.slice_meta:
                entity_name, slice_type = self.slice_meta[slice_uid]
            else:
                if "_grid_" in slice_uid:
                    try:
                        before, _, _ = slice_uid.rpartition("_grid_")
                        entity_name, _, slice_type = before.rpartition("_")
                    except Exception:
                        continue
                else:
                    parts = slice_uid.rsplit("_", 1)
                    if len(parts) == 2:
                        entity_name, slice_type = parts[0], parts[1]
                    else:
                        continue

            entity = self.get_entity_by_name(entity_name)
            if not entity:
                continue
            pv_entity = pv.wrap(entity)
            if property_name not in pv_entity.array_names:
                continue

            print(f"Updating slice {slice_uid} for property {property_name}")
            visible = actor.GetVisibility()
            bounds = pv_entity.bounds
            origin = actor.GetCenter()
            if slice_type == "X":
                normalized_pos = (
                    (origin[0] - bounds[0]) / (bounds[1] - bounds[0])
                    if bounds[1] > bounds[0]
                    else 0.5
                )
                slice_data = pv_entity.slice(
                    normal=[1, 0, 0],
                    origin=[bounds[0] + normalized_pos * (bounds[1] - bounds[0]), 0, 0],
                )
            elif slice_type == "Y":
                normalized_pos = (
                    (origin[1] - bounds[2]) / (bounds[3] - bounds[2])
                    if bounds[3] > bounds[2]
                    else 0.5
                )
                slice_data = pv_entity.slice(
                    normal=[0, 1, 0],
                    origin=[0, bounds[2] + normalized_pos * (bounds[3] - bounds[2]), 0],
                )
            else:
                normalized_pos = (
                    (origin[2] - bounds[4]) / (bounds[5] - bounds[4])
                    if bounds[5] > bounds[4]
                    else 0.5
                )
                slice_data = pv_entity.slice(
                    normal=[0, 0, 1],
                    origin=[0, 0, bounds[4] + normalized_pos * (bounds[5] - bounds[4])],
                )

            scalar_array = property_name
            cmap = None
            try:
                prop_row = self.parent.prop_legend_df[
                    self.parent.prop_legend_df["property_name"] == property_name
                ]
                if not prop_row.empty:
                    cmap = prop_row["colormap"].iloc[0]
            except Exception:
                pass

            self.plotter.remove_actor(actor)
            self.slice_actors[slice_uid] = self.plotter.add_mesh(
                slice_data,
                name=slice_uid,
                scalars=scalar_array,
                cmap=cmap,
                clim=pv_entity.get_data_range(scalar_array) if scalar_array else None,
                show_scalar_bar=False,
                opacity=1.0,
                interpolate_before_map=True,
            )
            self.slice_actors[slice_uid].SetVisibility(visible)

        # Force render
        self.plotter.render()

    def create_single_plane_widget(
        self, slice_type, normalized_position, bounds, update_callback
    ):
        """Create a single plane widget for the given slice type and position."""
        try:
            # Get current vertical exaggeration value
            v_exag = 1.0
            if hasattr(self, "v_exaggeration"):
                v_exag = self.v_exaggeration

            print(
                f"Creating plane widget for {slice_type} slice with vertical exaggeration: {v_exag}"
            )

            # Calculate world position
            if slice_type == "X":
                position = bounds[0] + normalized_position * (bounds[1] - bounds[0])
                normal = [1, 0, 0]
                origin = [position, 0, 0]
            elif slice_type == "Y":
                position = bounds[2] + normalized_position * (bounds[3] - bounds[2])
                normal = [0, 1, 0]
                origin = [0, position, 0]
            else:  # Z
                position = bounds[4] + normalized_position * (bounds[5] - bounds[4])
                normal = [0, 0, 1]

                # For Z planes, adjust the origin position for vertical exaggeration
                if v_exag != 1.0:
                    z_mid = (bounds[4] + bounds[5]) / 2
                    # Apply vertical exaggeration from the middle
                    adjusted_pos = z_mid + (position - z_mid) * v_exag
                    origin = [0, 0, adjusted_pos]
                else:
                    origin = [0, 0, position]

            # Constrain widget within bounds (account for vertical exaggeration on Z)
            widget_bounds = list(bounds)
            if slice_type == "Z" and v_exag != 1.0:
                z_mid = (bounds[4] + bounds[5]) / 2
                widget_bounds[4] = z_mid + (bounds[4] - z_mid) * v_exag
                widget_bounds[5] = z_mid + (bounds[5] - z_mid) * v_exag

            # Create the plane widget with minimal required parameters
            try:
                plane_widget = self.plotter.add_plane_widget(
                    update_callback,
                    normal=normal,
                    origin=origin,
                    bounds=widget_bounds,
                    normal_rotation=False,  # Disable normal rotation on manipulator
                )
                return plane_widget
            except Exception as e:
                print(f"Error creating plane widget with PyVista: {e}")
                # Try one more approach with different parameters
                try:
                    plane_widget = self.plotter.add_plane_widget(
                        update_callback,
                        normal=normal,
                        origin=origin,
                        bounds=widget_bounds,
                        normal_rotation=False,  # Disable normal rotation on manipulator
                    )
                    return plane_widget
                except:
                    print("Failed with alternate parameters too")
                    return None

        except Exception as e:
            print(f"Error creating plane widget for {slice_type} slice: {e}")
            import traceback

            traceback.print_exc()
            return None

    def update_slices_for_vertical_exaggeration(self):
        """Update all slices and plane widgets when vertical exaggeration changes"""
        if not hasattr(self, "slice_actors") or not self.slice_actors:
            return

        print("Updating slices for vertical exaggeration...")

        # Remember which slices have manipulation enabled
        has_manipulation = False
        entity_name = None
        u_checked = False
        v_checked = False
        w_checked = False

        # Find the mesh slicer dialog if it's openss
        for child in self.findChildren(QDialog):
            if hasattr(child, "windowTitle") and child.windowTitle() == "Mesh Slicer":
                # Find the manipulation checkbox
                enable_manipulation = child.findChild(QCheckBox, "enable_manipulation")
                if enable_manipulation and enable_manipulation.isChecked():
                    has_manipulation = True

                    # Get entity and which slices are checked
                    entity_combo = child.findChild(QComboBox, "entity_combo")
                    if entity_combo:
                        entity_name = entity_combo.currentText()

                    u_check = child.findChild(QCheckBox, "u_slice_check")
                    v_check = child.findChild(QCheckBox, "v_slice_check")
                    w_check = child.findChild(QCheckBox, "w_slice_check")

                    if u_check:
                        u_checked = u_check.isChecked()
                    if v_check:
                        v_checked = v_check.isChecked()
                    if w_check:
                        w_checked = w_check.isChecked()

                    # Temporarily disable manipulation
                    enable_manipulation.setChecked(False)
                    QApplication.processEvents()  # Process UI events
                    break

        # Clean up existing plane widgets
        self.cleanup_plane_widgets()

        # Update all slice positions with the new exaggeration
        for slice_uid in list(self.slice_actors.keys()):
            parts = slice_uid.split("_")
            if len(parts) >= 2:
                entity_name_from_slice = "_".join(parts[:-1])
                slice_type = parts[-1]

                # Get the entity
                entity = self.get_entity_by_name(entity_name_from_slice)
                if entity:
                    # Get current slider positions
                    normalized_position = 0.5  # Default position

                    # Force update the visualization (recompute actor with current cmap)
                    try:
                        pv_entity = pv.wrap(entity)
                        bounds = pv_entity.bounds
                        if slice_type == "X":
                            position = bounds[0] + normalized_position * (
                                bounds[1] - bounds[0]
                            )
                            slice_data = pv_entity.slice(
                                normal=[1, 0, 0], origin=[position, 0, 0]
                            )
                        elif slice_type == "Y":
                            position = bounds[2] + normalized_position * (
                                bounds[3] - bounds[2]
                            )
                            slice_data = pv_entity.slice(
                                normal=[0, 1, 0], origin=[0, position, 0]
                            )
                        else:
                            position = bounds[4] + normalized_position * (
                                bounds[5] - bounds[4]
                            )
                            slice_data = pv_entity.slice(
                                normal=[0, 0, 1], origin=[0, 0, position]
                            )

                        if slice_data.n_points > 0:
                            # Mirror the main entity's current property choice for re-sliced view
                            scalar_array = None
                            cmap = None
                            color_RGB = None
                            try:
                                main_uid = self.get_entity_uid_by_name(
                                    entity_name_from_slice
                                )
                                current_prop = None
                                if main_uid is not None:
                                    current_prop = self.actors_df.loc[
                                        self.actors_df["uid"] == main_uid,
                                        "show_property",
                                    ].values[0]
                                if not current_prop or current_prop == "none":
                                    color_RGB = (
                                        self._legend_color_for_uid(main_uid)
                                        if main_uid
                                        else None
                                    )
                                elif current_prop in ["X", "Y", "Z"]:
                                    idx = {"X": 0, "Y": 1, "Z": 2}[current_prop]
                                    scalar_array = slice_data.points[:, idx]
                                    if (
                                        hasattr(self.parent, "prop_legend_df")
                                        and self.parent.prop_legend_df is not None
                                    ):
                                        row = self.parent.prop_legend_df[
                                            self.parent.prop_legend_df["property_name"]
                                            == current_prop
                                        ]
                                        if not row.empty:
                                            cmap = row["colormap"].iloc[0]
                                else:
                                    if current_prop in slice_data.array_names:
                                        scalar_array = current_prop
                                        if (
                                            hasattr(self.parent, "prop_legend_df")
                                            and self.parent.prop_legend_df is not None
                                        ):
                                            row = self.parent.prop_legend_df[
                                                self.parent.prop_legend_df[
                                                    "property_name"
                                                ]
                                                == current_prop
                                            ]
                                            if not row.empty:
                                                cmap = row["colormap"].iloc[0]
                            except Exception:
                                pass
                            # Build uid consistently
                            slice_uid = f"{entity_name_from_slice}_{slice_type}"
                            if slice_uid in self.slice_actors:
                                vis = self.slice_actors[slice_uid].GetVisibility()
                                self.plotter.remove_actor(self.slice_actors[slice_uid])
                            else:
                                vis = True
                            self.slice_actors[slice_uid] = self.plotter.add_mesh(
                                slice_data,
                                name=slice_uid,
                                scalars=scalar_array,
                                cmap=cmap,
                                clim=(
                                    pv_entity.get_data_range(scalar_array)
                                    if scalar_array
                                    else None
                                ),
                                show_scalar_bar=False,
                                opacity=1.0,
                                interpolate_before_map=True,
                                color=color_RGB,
                            )
                            self.slice_actors[slice_uid].SetVisibility(vis)
                    except Exception:
                        pass

        # Re-enable manipulation if it was on before
        if has_manipulation and entity_name:
            # Find the dialog again to ensure it's still open
            for child in self.findChildren(QDialog):
                if (
                    hasattr(child, "windowTitle")
                    and child.windowTitle() == "Mesh Slicer"
                ):
                    enable_manipulation = child.findChild(
                        QCheckBox, "enable_manipulation"
                    )
                    if enable_manipulation:
                        print("Re-enabling manipulation with new vertical exaggeration")
                        enable_manipulation.setChecked(True)
                    break

        # Force a final render
        self.plotter.render()

    def create_grid_section_manager(self):
        """Redirects to the unified mesh slicer dialog with multi-slice mode activated."""
        # Create the unified dialog
        dialog = self.show_mesh_slicer_dialog()

        # Find the multi-slice radio button and set it to checked
        # This assumes the dialog follows the layout we created
        for child in dialog.findChildren(QRadioButton):
            if child.text() == "Multi Slice Mode":
                child.setChecked(True)
                break
        return dialog


