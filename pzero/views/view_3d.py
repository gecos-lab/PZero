"""view_3d.py
PZero© Andrea Bistacchi"""

# General Python imports____
from copy import deepcopy
from uuid import uuid4

# PySide6 imports____
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QMainWindow,
    QMenu,
    QAbstractItemView,
    QDockWidget,
    QSizePolicy,
    QMessageBox,
)

# Numpy imports____
from numpy import append as np_append

# VTK imports____
from vtkmodules.util import numpy_support
from vtkmodules.vtkCommonDataModel import vtkSphere
from vtkmodules.vtkFiltersPoints import vtkExtractPoints

# PyVista imports____
from pyvista import plot as pv_plot

# PZero imports____
from .abstract_view_vtk import ViewVTK
from ..entities_factory import Attitude
from ..entities_factory import PolyData
from ..helpers.helper_dialogs import save_file_dialog, multiple_input_dialog, progress_dialog
from ..helpers.helper_functions import best_fitting_plane, gen_frame
from ..collections.geological_collection import GeologicalCollection
from ..entities_factory import (
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

    def initialize_menu_tools(self):
        """Customize menus and tools for this view"""
        from ..point_clouds import (
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

    def set_orientation_widget(self):
        self.plotter.add_camera_orientation_widget()

    def show_qt_canvas(self):
        """Show the Qt Window. Reimplements the base method in ViewVTK()."""
        self.show()
        self.init_zoom = self.plotter.camera.distance
        # self.picker = self.plotter.enable_mesh_picking(callback= self.pkd_mesh,show_message=False)

    def end_pick(self, pos):
        """Function used to disable actor picking. Due to some slight difference,
        must be reimplemented in subclasses."""
        # Remove the selector observer
        self.plotter.iren.interactor.RemoveObservers(
            "LeftButtonPressEvent"
        )
        # Remove the right click observer
        self.plotter.untrack_click_position(
            side="right"
        )
        # Remove the left click observer
        self.plotter.untrack_click_position(
            side="left"
        )
        # self.plotter.track_click_position(
        #    lambda pos: self.plotter.camera.SetFocalPoint(pos), side="left", double=True
        # )
        # Specific to View3D() implementation.
        self.plotter.enable_trackball_style()
        # Closing settings
        self.plotter.reset_key_events()
        self.selected_uids = self.parent.selected_uids
        self.enable_actions()

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
            octree = PolyData()  #  possible recursion problem
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
