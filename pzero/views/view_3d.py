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

# VTK imports____
from vtkmodules.util import numpy_support
from vtkmodules.vtkCommonDataModel import vtkSphere
from vtkmodules.vtkFiltersPoints import vtkExtractPoints
from vtk import vtkJSONSceneExporter

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
from ..helpers.helper_functions import best_fitting_plane, gen_frame
from ..collections.geological_collection import GeologicalCollection
from ..entities_factory import PolyData, Attitude


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

        # then add new code specific to this class
        self.saveHomeView = QAction("Save home view", self)
        self.saveHomeView.triggered.connect(self.save_home_view)
        self.menuView.insertAction(self.zoomActive, self.saveHomeView)

        self.zoomHomeView = QAction("Zoom to home", self)
        self.zoomHomeView.triggered.connect(self.zoom_home_view)
        self.menuView.insertAction(self.zoomActive, self.zoomHomeView)

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
        must be reimplemented in subclasses."""
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
        self.enable_actions()

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

            positions = np.linspace(
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

            positions = np.linspace(start_norm, end_norm, slices_spin.value())
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
        """Add mesh slicer to the menu tools."""
        # Call parent's initialize_menu_tools first to ensure menus and toolbars are created
        super().initialize_menu_tools()

        # Create Mesh Tools menu if it doesn't exist
        if not hasattr(self, "menuMeshTools"):
            self.menuMeshTools = QMenu("Mesh Tools", self)
            self.menuBar().addMenu(self.menuMeshTools)

        # Add unified mesh slicer action
        self.actionMeshSlicer = QAction("Mesh Slicer", self)
        self.actionMeshSlicer.triggered.connect(self.show_mesh_slicer_dialog)

        # Add to menu
        self.menuMeshTools.addAction(self.actionMeshSlicer)

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
