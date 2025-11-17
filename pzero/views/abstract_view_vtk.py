"""abstract_view_vtk.py
PZero© Andrea Bistacchi"""

# PySide6 imports____
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QAbstractItemView

# numpy import____
from numpy import ndarray as np_ndarray

# VTK imports incl. VTK-Numpy interface____
from vtkmodules.vtkRenderingCore import vtkCellPicker
from vtk import vtkAppendPolyData

# PyVista imports____
from pyvista import global_theme as pv_global_theme
from pyvistaqt import QtInteractor as pvQtInteractor
from pyvista import Box as pv_Box
from pyvista import Line as pv_Line
from pyvista import Disc as pv_Disc
from pyvista import PointSet as pvPointSet

# PZero imports____
from .abstract_base_view import BaseView
from ..orientation_analysis import get_dip_dir_vectors
from ..helpers.helper_dialogs import input_one_value_dialog, save_file_dialog
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
    Seismics,
    XsImage,
    WellMarker,
    WellTrace,
    Attitude,
)


class ViewVTK(BaseView):
    """Abstract class used as a base for all classes using the VTK/PyVista plotting canvas."""

    def __init__(self, *args, **kwargs):
        super(ViewVTK, self).__init__(*args, **kwargs)

    # ================================  General methods shared by all views - built incrementally =====================

    def initialize_menu_tools(self):
        """This method collects menus and actions in superclasses and then adds custom ones, specific to this view."""
        # append code from superclass
        super().initialize_menu_tools()

        # then add new code specific to this class
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

    # ================================  Methods required by BaseView(), (re-)implemented here =========================

    def closeEvent(self, event):
        """Override the standard closeEvent method by (i) disconnecting all signals and,
        (ii) closing the plotter for vtk windows."""
        self.enable_actions()
        self.disconnect_all_signals()
        # To cleanly close the vtk plotter, the following line is needed. This is the only difference
        # with the closeEvent() method in the BaseView() class.
        self.plotter.renderer.Finalize()
        self.plotter.close()
        event.accept()

    def get_actor_by_uid(self, uid: str = None):
        """
        Get an actor by uid in a VTK/PyVista plotter. Here we use self.plotter.renderer.actors
        that is a dictionary with key = uid string and value = actor.
        """
        return self.plotter.renderer.actors[uid]

    def get_uid_from_actor(self, actor=None):
        """
        Get the uid of an actor in a VTK/PyVista plotter. Here we use self.plotter.renderer.actors
        that is a dictionary with key = uid string and value = actor.
        """
        uid = None
        for uid_i, actor_i in self.plotter.renderer.actors.items():
            if actor_i == actor:
                uid = uid_i
                break
        return uid

    def actor_shown(self, uid: str = None):
        """Method to check if an actor is shown in a VTK/PyVista plotter. Returns a boolean."""
        return self.plotter.renderer.actors[uid].GetVisibility()

    def show_actors(self, uids: list = None):
        """Method to show actors in uids list in a VTK/PyVista plotter."""
        actors = self.plotter.renderer.actors
        for uid, actor in actors.items():
            if uid in uids:
                actor.SetVisibility(True)

    def hide_actors(self, uids: list = None):
        """Method to show actors in uids list in a VTK/PyVista plotter."""
        actors = self.plotter.renderer.actors
        for uid, actor in actors.items():
            if uid in uids:
                actor.SetVisibility(False)

    def change_actor_color(self, updated_uids: list = None, collection=None):
        """Change color for VTK plots."""
        for uid in updated_uids:
            if uid in self.uids_in_view:
                # Get color from legend
                color_R = collection.get_uid_legend(uid=uid)["color_R"]
                color_G = collection.get_uid_legend(uid=uid)["color_G"]
                color_B = collection.get_uid_legend(uid=uid)["color_B"]
                color_RGB = [color_R / 255, color_G / 255, color_B / 255]
                # Now update color for actor uid
                self.get_actor_by_uid(uid).GetProperty().SetColor(color_RGB)
            else:
                continue

    def change_actor_opacity(self, updated_uids: list = None, collection=None):
        """Change opacity for actor uid"""
        for uid in updated_uids:
            if uid in self.uids_in_view:
                # Get color from legend
                opacity = collection.get_uid_legend(uid=uid)["opacity"] / 100
                # Now update color for actor uid
                self.get_actor_by_uid(uid).GetProperty().SetOpacity(opacity)
            else:
                continue

    def change_actor_line_thick(self, updated_uids: list = None, collection=None):
        """Change line thickness for actor uid"""
        for uid in updated_uids:
            if uid in self.uids_in_view:
                # Get color from legend
                line_thick = collection.get_uid_legend(uid=uid)["line_thick"]
                # Now update color for actor uid
                self.get_actor_by_uid(uid).GetProperty().SetLineWidth(line_thick)
            else:
                continue

    def change_actor_point_size(self, updated_uids: list = None, collection=None):
        """Change point size for actor uid"""
        for uid in updated_uids:
            if uid in self.uids_in_view:
                # Get color from legend
                point_size = collection.get_uid_legend(uid=uid)["point_size"]
                # Now update color for actor uid
                self.get_actor_by_uid(uid).GetProperty().SetPointSize(point_size)
            else:
                continue

    def set_actor_visible(self, uid=None, visible=None, name=None):
        """Set actor uid visible or invisible (visible = True or False)"""
        collection = self.actors_df.loc[
            self.actors_df["uid"] == uid, "collection"
        ].values[0]
        actors = self.plotter.renderer.actors
        this_actor = actors[uid]
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
            # self.print_terminal("case for ALL OTHER COLLECTIONS")
            this_actor.SetVisibility(visible)

    def remove_actor_in_view(self, uid=None, redraw=False):
        """ "Remove actor from plotter"""
        # plotter.remove_actor can remove a single entity or a list of entities as actors ->
        # here we remove a single entity
        if not self.actors_df.loc[self.actors_df["uid"] == uid].empty:
            this_actor = self.get_actor_by_uid(uid)
            success = self.plotter.remove_actor(this_actor)

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

        # # In an old version it was turned on after the qt canvas was shown, but this does not seem necessary
        # if isinstance(self, View3D):
        #     self.plotter.add_camera_orientation_widget()
        #     # self.cam_orient_widget = vtkCameraOrientationWidget()
        #     # self.cam_orient_widget.SetParentRenderer(self.plotter.renderer)
        #     # self.cam_orient_widget.On()
        # elif isinstance(self, ViewXsection):
        #     self.plotter.add_orientation_widget(
        #         pv_Arrow(direction=(0.0, 1.0, 0.0), scale=0.3),
        #         interactive=None,
        #         color="gold",
        #     )
        # elif isinstance(self, ViewMap):
        #     self.plotter.add_north_arrow_widget(interactive=None, color="gold")

        # Set default orientation horizontal because vertical colorbars interfere with the camera widget.
        pv_global_theme.colorbar_orientation = "horizontal"

        # Manage home view
        self.default_view = self.plotter.camera_position
        # self.plotter.track_click_position(
        #    lambda pos: self.plotter.camera.SetFocalPoint(pos), side="left", double=True
        # )

        self.set_orientation_widget()

    def show_actor_with_property(
        self, uid=None, coll_name=None, show_property=None, visible=None
    ):
        """
        Show actor with scalar property (default None). See details in:
        https://github.com/pyvista/pyvista/blob/140b15be1d4021b81ded46b1c212c70e86a98ee7/pyvista/plotting/plotting.py#L1045
        """

        # First get the vtk object from its collection.
        if show_property:
            show_property_title = show_property
        else:
            show_property_title = None
        this_coll = eval(f"self.parent.{coll_name}")
        if coll_name in ["geol_coll", "fluid_coll", "backgrnd_coll", "well_coll"]:
            color_R = this_coll.get_uid_legend(uid=uid)["color_R"]
            color_G = this_coll.get_uid_legend(uid=uid)["color_G"]
            color_B = this_coll.get_uid_legend(uid=uid)["color_B"]
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            line_thick = this_coll.get_uid_legend(uid=uid)["line_thick"]
            point_size = this_coll.get_uid_legend(uid=uid)["point_size"]
            opacity = this_coll.get_uid_legend(uid=uid)["opacity"] / 100
            plot_entity = this_coll.get_uid_vtk_obj(uid)
        elif coll_name in [
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
            self.print_terminal(f"no collection: {coll_name}")
            this_actor = None
        # Then plot the vtk object with proper options.
        if isinstance(plot_entity, (PolyLine, TriSurf, XsPolyLine)) and not isinstance(
            plot_entity, WellTrace
        ):
            plot_rgb_option = None
            if isinstance(plot_entity.points, np_ndarray):
                # This check is needed to avoid errors when trying to plot an empty
                # PolyData, just created at the beginning of a digitizing session.
                if show_property == "none":
                    show_property = None
                elif show_property == None:
                    show_property = None
                elif not show_property:
                    show_property = None
                elif show_property == "X":
                    show_property = plot_entity.points_X
                elif show_property == "Y":
                    show_property = plot_entity.points_Y
                elif show_property == "Z":
                    show_property = plot_entity.points_Z
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
                    show_property = plot_entity.get_point_data(original_prop)[:, index]
                else:
                    # Safely check for multicomponent scalar arrays
                    try:
                        shape = plot_entity.get_point_data_shape(show_property)
                        if shape and shape[-1] == 3:
                            plot_rgb_option = True
                    except Exception:
                        pass
                    else:
                        # last option to catch unexpected cases
                        if (
                            not show_property
                            in self.parent.prop_legend_df["property_name"].tolist()
                        ):
                            show_property = None
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
                # handle multicomponent properties like 'PropName[index]' and treat 'Normals[n]' as full-normal glyphs
                elif isinstance(show_property, str) and show_property.endswith("]"):
                    pos1 = show_property.index("[")
                    pos2 = show_property.index("]")
                    original_prop = show_property[:pos1]
                    comp_index = int(show_property[pos1 + 1 : pos2])
                    if original_prop == "Normals":
                        # draw discs for normals (same as plain 'Normals')
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
                    else:
                        # extract the specified component from the vector property
                        show_property = plot_entity.get_point_data(original_prop)[
                            :, comp_index
                        ]
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
                    # handle multicomponent properties like 'PropName[index]'
                    if isinstance(show_property, str) and show_property.endswith("]"):
                        pos1 = show_property.index("[")
                        pos2 = show_property.index("]")
                        original_prop = show_property[:pos1]
                        comp_index = int(show_property[pos1 + 1 : pos2])
                        show_property = plot_entity.get_point_data(original_prop)[
                            :, comp_index
                        ]
                    else:
                        # Safely check for multicomponent scalar arrays
                        try:
                            shape = plot_entity.get_point_data_shape(show_property)
                            if shape and shape[-1] == 3:
                                plot_rgb_option = True
                        except Exception:
                            pass
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
                    self.parent.dom_coll.df["uid"] == uid, "textures"
                ].values[0]
            ):
                plot_entity.set_active_texture(show_property)
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
            self.print_terminal("error - actor with no class")
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

    def show_labels(self, uid=None, coll_name=None, show_property=None):
        if coll_name == "geol_coll":
            plot_entity = self.parent.geol_coll.get_uid_vtk_obj(uid)
            point = plot_entity.GetCenter()
            name_value = self.parent.geol_coll.get_uid_name(uid)
        elif coll_name == "xsect_coll":
            plot_entity = self.parent.xsect_coll.get_uid_vtk_obj(uid)
            point = plot_entity.GetCenter()
            name_value = self.parent.xsect_coll.get_uid_name(uid)
        elif coll_name == "boundary_coll":
            plot_entity = self.parent.boundary_coll.get_uid_vtk_obj(uid)
            point = plot_entity.GetCenter()
            name_value = self.parent.boundary_coll.get_uid_name(uid)
        elif coll_name == "mesh3d_coll":
            plot_entity = self.parent.mesh3d_coll.get_uid_vtk_obj(uid)
            point = plot_entity.GetCenter()
            name_value = self.parent.mesh3d_coll.get_uid_name(uid)
        elif coll_name == "dom_coll":
            plot_entity = self.parent.dom_coll.get_uid_vtk_obj(uid)
            point = plot_entity.GetCenter()
            name_value = self.parent.dom_coll.get_uid_name(uid)
        elif coll_name == "image_coll":
            plot_entity = self.parent.image_coll.get_uid_vtk_obj(uid)
            point = plot_entity.GetCenter()
            name_value = self.parent.image_coll.get_uid_name(uid)
        elif coll_name == "well_coll":
            plot_entity = self.parent.well_coll.get_uid_vtk_obj(uid)
            point = plot_entity.points[0].reshape(-1, 3)
            name_value = [self.parent.well_coll.get_uid_well_locid(uid)]
        elif coll_name == "fluid_coll":
            plot_entity = self.parent.fluid_coll.get_uid_vtk_obj(uid)
            point = plot_entity.GetCenter()
            name_value = self.parent.fluid_coll.get_uid_name(uid)
        elif coll_name == "backgrnd_coll":
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

    def export_screen(self):
        out_file_name = save_file_dialog(
            parent=self,
            caption="Export 3D view as HTML.",
            filter="png (*.png);; jpeg (*.jpg)",
        )
        self.plotter.screenshot(
            out_file_name, transparent_background=True, window_size=(1920, 1080)
        )

    # ================================  Methods specific to VTK views =================================================

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
            collection = self.actors_df.loc[
                self.actors_df["uid"] == sel_uid[0], "collection"
            ].values[0]
            # Mapping collection name to (table, df, tab index)
            collection_to_table = {
                "geol_coll": (
                    self.parent.GeologyTableView,
                    self.parent.geol_coll.df,
                    0,
                ),
                "fluid_coll": (
                    self.parent.FluidsTableView,
                    self.parent.fluid_coll.df,
                    1,
                ),
                "backgrnd_coll": (
                    self.parent.BackgroundsTableView,
                    self.parent.backgrnd_coll.df,
                    2,
                ),
                "dom_coll": (self.parent.DOMsTableView, self.parent.dom_coll.df, 3),
                "image_coll": (
                    self.parent.ImagesTableView,
                    self.parent.image_coll.df,
                    4,
                ),
                "mesh3d_coll": (
                    self.parent.Meshes3DTableView,
                    self.parent.mesh3d_coll.df,
                    5,
                ),
                "boundary_coll": (
                    self.parent.BoundariesTableView,
                    self.parent.boundary_coll.df,
                    6,
                ),
                "xsect_coll": (
                    self.parent.XSectionsTableView,
                    self.parent.xsect_coll.df,
                    7,
                ),
                "well_coll": (self.parent.WellsTableView, self.parent.well_coll.df, 8),
            }
            if collection in collection_to_table:
                table, df, tab_idx = collection_to_table[collection]
                self.parent.tabWidgetTopLeft.setCurrentIndex(tab_idx)
            else:
                self.print_terminal(
                    "Selection not supported for entities that do not belong to a recognized collection."
                )
                return
            table.clearSelection()
            if len(sel_uid) > 1:
                table.setSelectionMode(QAbstractItemView.MultiSelection)
            for uid in sel_uid:
                uid_list = [
                    table.model().index(row, 0).data() for row in range(len(df.index))
                ]
                if uid in uid_list:
                    idx = uid_list.index(uid)
                    table.selectRow(idx)
                else:
                    print(f"uid {uid} not find")
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
        """Function used to disable actor picking. Due to some slight difference,
        must be reimplemented in subclasses."""
        pass

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
        if self.get_uid_from_actor(actor=actor):
            # Get uid of picked actor
            sel_uid = self.get_uid_from_actor(actor=actor)
            self.print_terminal(f"Picked uid: {sel_uid}")

            # Add uid of picked actor to selected_uids list, with SHIFT-SELECT option
            if shift:
                self.selected_uids.append(sel_uid)
            else:
                self.selected_uids = [sel_uid]
            self.print_terminal(f"Selected uids: {self.selected_uids}")

            # Show selected actors in yellow
            for sel_uid in self.selected_uids:
                sel_actor = self.get_actor_by_uid(sel_uid)
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

    # ================================  Placeholders for required methods, implemented in child classes ===============

    def set_orientation_widget(self):
        """Set the orientation widget to the correct orientation.
        To be implementyed in subclasses."""
        pass

    def show_qt_canvas(self):
        """Show the Qt Window. To be reimplemented in some subclass."""
        pass
