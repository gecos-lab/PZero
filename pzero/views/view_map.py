"""view_map.py
PZero© Andrea Bistacchi"""

# PySide6 imports____
from PySide6.QtGui import QAction

# Numpy imports____
from numpy import ndarray as np_ndarray

# VTK imports____
from vtkmodules.vtkFiltersCore import vtkAppendPolyData

# PyVista imports____
from pyvista import Line as pv_Line
from pyvista import PointSet as pv_PointSet

# PZero imports____
from .abstract_view_2d import View2D
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
from ..orientation_analysis import get_dip_dir_vectors
from ..collections.xsection_collection import section_from_azimuth
from ..collections.boundary_collection import boundary_from_points


class ViewMap(View2D):
    def __init__(self, *args, **kwargs):
        super(ViewMap, self).__init__(*args, **kwargs)
        self.setWindowTitle("Map View")
        self.plotter.view_xy()

    # ================================  General methods shared by all views - built incrementally =====================

    def initialize_menu_tools(self):
        """This method collects menus and actions in superclasses and then adds custom ones, specific to this view."""
        # append code from superclass
        super().initialize_menu_tools()

        # then add new code specific to this class
        self.sectionFromAzimuthButton = QAction("Section from azimuth", self)
        self.sectionFromAzimuthButton.triggered.connect(
            lambda: self.vector_by_mouse(section_from_azimuth)
        )
        self.menuCreate.addAction(self.sectionFromAzimuthButton)

        self.boundaryFromPointsButton = QAction("Boundary from 2 points", self)
        self.boundaryFromPointsButton.triggered.connect(
            lambda: self.vector_by_mouse(boundary_from_points)
        )
        self.menuCreate.addAction(self.boundaryFromPointsButton)

    # ================================  Methods required by BaseView(), (re-)implemented here =========================

    def show_actor_with_property(
        self, uid=None, coll_name=None, show_property=None, visible=None
    ):
        """Show actor with scalar property (default None)
        https://github.com/pyvista/pyvista/blob/140b15be1d4021b81ded46b1c212c70e86a98ee7/pyvista/plotting/plotting.py#L1045
        """
        # ___________________________________________________see if this reimplementation from VTKView can be avoided
        # First get the vtk object from its collection.
        show_property_title = show_property
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
            print("no collection", coll_name)
            this_actor = None
        # Then plot the vtk object with proper options.
        if isinstance(plot_entity, (PolyLine, TriSurf, XsPolyLine)) and not isinstance(
            plot_entity, WellTrace
        ):
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
                elif show_property == "Normals":
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
            # Show texture specified in show_property
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
            new_plot = pv_PointSet()
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
                    #  we can identify multicomponent properties such as RGB[0] or Normals[0] by
                    # taking the last character of the property name ("]").
                    #  Get the start and end index of the [n_component]
                    pos1 = show_property.index("[")
                    pos2 = show_property.index("]")
                    #  Get the original property (e.g. RGB[0] -> RGB)
                    original_prop = show_property[:pos1]
                    #  Get the column index (the n_component value)
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
                    # Get the n of components for the given property. If it's > 1 then do stuff depending on the type of property (e.g. show_rgb_option -> True if the property is RGB)
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
            print("[Windows factory]: actor with no class")
            this_actor = None
        return this_actor

    # ================================  Methods required by ViewVTK(), (re-)implemented here ==========================

    def set_orientation_widget(self):
        self.plotter.add_north_arrow_widget(interactive=None, color="gold")

