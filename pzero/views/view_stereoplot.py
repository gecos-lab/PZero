"""view_stereoplot.py
PZero© Andrea Bistacchi"""

# PySide6 imports____
from PySide6.QtGui import QAction

# numpy import____
from numpy import all as np_all
from numpy import ndarray as np_ndarray

# Pandas imports____
from pandas import DataFrame as pd_DataFrame
from pandas import concat as pd_concat

# PZero imports____
from .abstract_view_mpl import ViewMPL
from ..entities_factory import VertexSet, XsVertexSet, Attitude

# mplstereonet import____
import mplstereonet

# Matplotlib imports____
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas


class ViewStereoplot(ViewMPL):
    def __init__(self, *args, **kwargs):
        # Some properties need to be set before calling super.__init__ to import the parent class.
        # self.proj_type can be 'equal_area_stereonet' or  ‘equal_angle_stereonet’
        self.proj_type = "equal_area_stereonet"
        # self.contours can be True (filled), False (non filled) or None (no contours)
        self.contours = None
        # self.grid_kind can be 'polar', None (equatorial grid), or False (no grid at all)
        self.grid_kind = "polar"

        # Set filter for entities belonging to this cross section.
        # properties_names.astype("str") converts the list of strings in properties_names into a single
        # concatenated string, then .str.contains("Normals") searches for the (sub-)string "Normals".
        self.view_filter = 'properties_names.astype("str").str.contains("Normals", na=False) or properties_names.astype("str").str.contains("Lineations", na=False)'

        super(ViewStereoplot, self).__init__(*args, **kwargs)
        self.setWindowTitle("Stereoplot View")

    # ================================  General methods shared by all views - built incrementally =====================

    def initialize_menu_tools(self):
        """This is the method of the ViewStereoplot() class, used to add menu tools in addition to those inherited from
        superclasses, that are appended here using super().initialize_menu_tools()."""
        # append code from MPLView()
        super().initialize_menu_tools()

        # then add new code specific to MPLView()
        self.actionContours = QAction("Toggle projection", self)
        self.actionContours.triggered.connect(self.toggle_projection)
        self.menuView.addAction(self.actionContours)

        self.actionContours = QAction("Toggle contours", self)
        self.actionContours.triggered.connect(self.toggle_contours)
        self.menuView.addAction(self.actionContours)

        self.actionSetPolar = QAction("Toggle grid", self)
        self.actionSetPolar.triggered.connect(self.toggle_grid)
        self.menuView.addAction(self.actionSetPolar)

    # ================================  Methods required by BaseView(), (re-)implemented here =========================

    def initialize_interactor(self):
        """
        Initializes the interactor for the application.

        This method creates the Matplotlib canvas, figure, and navigation toolbar.
        It also integrates the canvas into a Qt layout for seamless embedding.

        Attributes:
            figure (Figure): The Matplotlib figure created using the specified projection type.
            ax (Axes): The axis object corresponding to the created figure.
            canvas (FigureCanvas): The canvas widget containing the Matplotlib figure.

        Raises:
            None
        """
        # Create Matplotlib canvas, figure and navi_toolbar. this implicitly
        # creates also the canvas to contain the figure.
        # refactor allowing to change background color with:
        # mplstyle.use("default")
        # mplstyle.use("dark_background")
        self.figure, self.ax = mplstereonet.subplots(projection=self.proj_type)

        # get a reference to the canvas that contains the figure
        self.canvas = FigureCanvas(self.figure)

        # Create Qt layout and add Matplotlib canvas (created above) as a widget to the Qt layout
        self.ViewFrameLayout.addWidget(self.canvas)
        if self.grid_kind == "hidden":
            self.ax.grid(False)
        elif self.grid_kind == "equatorial":
            self.ax.grid(True, kind="arbitrary", color="k", ls=":")
        elif self.grid_kind == "polar":
            self.ax.grid(True, kind="polar", color="k", ls=":")

    def show_actor_with_property(
        self,
        uid=None,
        coll_name=None,
        show_property=None,
        visible=None,
    ):
        # Show actor with scalar property (default None)
        if show_property is None:
            show_property = "Poles"

        # First get the vtk object from its collection.
        show_property_title = show_property
        this_coll = eval(f"self.parent.{coll_name}")
        if coll_name == "geol_coll":
            color_R = this_coll.get_uid_legend(uid=uid)["color_R"]
            color_G = this_coll.get_uid_legend(uid=uid)["color_G"]
            color_B = this_coll.get_uid_legend(uid=uid)["color_B"]
            color_RGB = [color_R / 255, color_G / 255, color_B / 255]
            line_thick = this_coll.get_uid_legend(uid=uid)["line_thick"]
            plot_entity = this_coll.get_uid_vtk_obj(uid)
        else:
            # catch errors
            self.print_terminal("no collection: " + coll_name)
            plot_entity = None

        # Then plot.
        if isinstance(plot_entity, (VertexSet, XsVertexSet, Attitude)):
            if isinstance(plot_entity.points, np_ndarray):
                if plot_entity.points_number > 0:
                    # This check is needed to avoid errors when trying to plot an empty
                    # PolyData, just created at the beginning of a digitizing session.
                    # Check if both these conditions are necessary_________________
                    #  Dip az needs to be converted to strike (dz-90) to plot with mplstereonet
                    strike = (plot_entity.points_map_dip_azimuth - 90) % 360
                    dip = plot_entity.points_map_dip

                    if np_all(strike != None):
                        if uid in self.selected_uids:
                            if show_property == "Planes":
                                this_actor = self.ax.plane(
                                    strike, dip, color=color_RGB
                                )[0]
                            else:
                                this_actor = self.ax.pole(strike, dip, color=color_RGB)[
                                    0
                                ]

                            this_actor.set_visible(visible)
                            self.print_terminal(f"uid: {uid} - agent: {this_actor}")
                        else:
                            if show_property == "Planes":
                                this_actor = self.ax.plane(
                                    strike, dip, color=color_RGB
                                )[0]
                            else:
                                if self.contours is not None and visible is True:
                                    if self.contours:
                                        self.ax.density_contourf(
                                            strike, dip, measurement="poles"
                                        )
                                    else:
                                        self.ax.density_contour(
                                            strike, dip, measurement="poles"
                                        )
                                this_actor = self.ax.pole(strike, dip, color=color_RGB)[
                                    0
                                ]
                            if this_actor:
                                this_actor.set_visible(visible)
                    else:
                        this_actor = None
                else:
                    this_actor = None
            else:
                this_actor = None
        else:
            this_actor = None
        if this_actor:
            this_actor.figure.canvas.draw()
        self.mpl_actors[uid] = this_actor
        return this_actor

    # ================================  Methods specific to Stereoplot views ==========================================

    def toggle_projection(self):
        """
        Switches the projection type between 'equal_area_stereonet' and 'equal_angle_stereonet'.
        This method updates the visual representation of the stereonet in the view frame based
        on the selected projection type. It also re-initializes the interactor and updates
        the actors related to geological data.
        """
        # Switch projection
        if self.proj_type == "equal_area_stereonet":
            self.proj_type = "equal_angle_stereonet"
        elif self.proj_type == "equal_angle_stereonet":
            self.proj_type = "equal_area_stereonet"

        self.ViewFrameLayout.removeWidget(self.canvas)
        self.initialize_interactor()
        uids = self.parent.geol_coll.df.loc[
            self.parent.geol_coll.df["topology"] == "VertexSet", "uid"
        ]
        for uid in uids:
            # show = self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]
            show = self.actor_shown(uid=uid)
            self.remove_actor_in_view(uid, redraw=False)
            this_actor = self.show_actor_with_property(
                uid=uid, coll_name="geol_coll", show_property=None, visible=show
            )
            self.actors_df = pd_concat(
                [
                    self.actors_df,
                    pd_DataFrame(
                        [
                            {
                                "uid": uid,
                                "actor": this_actor,
                                "show": show,
                                "collection": "geol_coll",
                                "show_property": "poles",
                            }
                        ]
                    ),
                ],
                ignore_index=True,
            )

    def toggle_contours(self):
        """Display Kamb contours for visible poles in the stereoplot."""

        self.ViewFrameLayout.removeWidget(self.canvas)
        self.initialize_interactor()

        uids = self.parent.geol_coll.df.loc[
            (self.parent.geol_coll.df["topology"] == "VertexSet")
            | (self.parent.geol_coll.df["topology"] == "XsVertexSet"),
            "uid",
        ]

        if self.contours == None:
            self.contours = False
            self.print_terminal("Contours enabled, unfilled")
        elif self.contours == False:
            self.contours = True
            self.print_terminal("Contours enabled, filled")
        else:
            self.contours = None
            self.print_terminal("Contours disabled")

        for uid in uids:
            show = self.actor_shown(uid=uid)

            self.remove_actor_in_view(uid, redraw=False)

            this_actor = self.show_actor_with_property(
                uid=uid, coll_name="geol_coll", show_property=None, visible=show
            )
            self.actors_df = pd_concat(
                [
                    self.actors_df,
                    pd_DataFrame(
                        [
                            {
                                "uid": uid,
                                "actor": this_actor,
                                "show": show,
                                "collection": "geol_coll",
                                "show_property": "poles",
                            }
                        ]
                    ),
                ],
                ignore_index=True,
            )

    def toggle_grid(self):
        """
        Toggles the grid display on a plot between polar, equatorial, and hidden states.

        This method cycles through three states for the grid on a plot: 'polar' mode,
        'equatorial' mode, and hidden. It modifies the grid display of the plot
        accordingly and updates the parent container's terminal with a
        message indicating the current state of the grid.
        """
        if self.grid_kind == "polar":
            self.ax.grid(False)
            self.grid_kind = "hidden"
            self.print_terminal("Grid hidden")
        elif self.grid_kind == "hidden":
            self.ax.grid(True, kind="arbitrary", color="k", ls=":")
            self.grid_kind = "equatorial"
            self.print_terminal("Grid equatorial")
        elif self.grid_kind == "equatorial":
            self.ax.grid(True, kind="polar", color="k", ls=":")
            self.grid_kind = "polar"
            self.print_terminal("Grid polar")
        self.figure.canvas.draw()

    def stop_event_loops(self):
        """Terminate running event loops. It looks like we do not use this method."""
        self.figure.canvas.stop_event_loop()
