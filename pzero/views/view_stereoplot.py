"""view_stereoplot.py
PZero© Andrea Bistacchi"""

# PySide6 imports____
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QSpinBox, QWidgetAction

# numpy import____
from numpy import all as np_all
from numpy import ndarray as np_ndarray
from numpy.linalg import norm as np_linalg_norm
from numpy import asarray as np_asarray
from numpy import atleast_1d as np_atleast_1d
from numpy import concatenate as np_concatenate
from numpy import vstack as np_vstack

# Pandas imports____
from pandas import DataFrame as pd_DataFrame
from pandas import concat as pd_concat

# PZero imports____
from .abstract_view_mpl import ViewMPL
from ..entities_factory import VertexSet, XsVertexSet, Attitude
from pzero.orientation_analysis import (
    fisherparams,
    bingham,
    kmeans_clusters,
    resolve_lower_hemisphere,
    kmedoids_clusters,
)  # kentparams,
from pzero.helpers.helper_dialogs import multiple_input_dialog

# mplstereonet import____
import mplstereonet

# Matplotlib imports____
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.pyplot import close as plt_close
import matplotlib.cm as cm


class ViewStereoplot(ViewMPL):

    Z_CONTOURS = 1
    Z_GRID = 2
    Z_ENTITIES = 3
    Z_STATS = 4

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

        self.analysis_results = {}
        self.analysis_actors = {}
        self.analysis_action_for_key = {}
        self.kmedoids_k = 1  # default value
        self.is_normals = None
        self.is_lineations = None
        self.auto_recompute = False
        self.picking_seeds = False
        self.seed_pick_kind = None
        self.seed_pick_target = 0
        self.seed_pick_normals = []
        self.seed_pick_lineations = []
        self.seed_pick_actors = []
        self.seed_pick_cid = None

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

        self.actionRecompute = QAction("Recompute statistics", self)
        self.actionRecompute.setEnabled(not self.auto_recompute)
        self.actionRecompute.triggered.connect(self.recompute_values)
        self.menuAnalysis.addAction(self.actionRecompute)

        self.actionAutoRecompute = QAction("Enable auto recomputation", self)
        self.actionAutoRecompute.setCheckable(True)
        self.actionAutoRecompute.setChecked(self.auto_recompute)
        self.actionAutoRecompute.triggered.connect(self.toggle_auto_recompute)
        self.menuAnalysis.addAction(self.actionAutoRecompute)

        self.actionSaveClusters = QAction("Save clusters as a property", self)
        self.actionSaveClusters.triggered.connect(self.prompt_and_save_clusters)
        self.menuAnalysis.addAction(self.actionSaveClusters)

        self.menuAnalysis.addSection("Kmedoids clusters")

        self.kmedoids_k_spinbox = QSpinBox()
        self.kmedoids_k_spinbox.setMinimum(1)
        self.kmedoids_k_spinbox.setValue(self.kmedoids_k)
        self.kmedoids_k_spinbox.valueChanged.connect(self.set_kmedoids_k)

        self.kmedoids_k_widget_action = QWidgetAction(self)
        self.kmedoids_k_widget_action.setDefaultWidget(self.kmedoids_k_spinbox)
        self.menuAnalysis.addAction(self.kmedoids_k_widget_action)

        # ---- Analysis actors ----
        self.menuAnalysis.addSection("Fisher")

        self.actionFisher = QAction("Mean direction as pole", self)
        self.actionFisher.setCheckable(True)
        self.actionFisher.triggered.connect(
            lambda: self.toggle_analysis_actor("fisher_mean_pole")
        )
        self.menuAnalysis.addAction(self.actionFisher)
        self.analysis_action_for_key["fisher_mean_pole"] = self.actionFisher

        self.menuAnalysis.addSection("Bingham")

        self.actionBinghamMajorPole = QAction("Major axis as pole", self)
        self.actionBinghamMajorPole.setCheckable(True)
        self.actionBinghamMajorPole.triggered.connect(
            lambda: self.toggle_analysis_actor("bingham_major_pole")
        )
        self.menuAnalysis.addAction(self.actionBinghamMajorPole)
        self.analysis_action_for_key["bingham_major_pole"] = self.actionBinghamMajorPole

        self.actionBinghamIntermediatePole = QAction("Intermediate axis as pole", self)
        self.actionBinghamIntermediatePole.setCheckable(True)
        self.actionBinghamIntermediatePole.triggered.connect(
            lambda: self.toggle_analysis_actor("bingham_intermediate_pole")
        )
        self.menuAnalysis.addAction(self.actionBinghamIntermediatePole)
        self.analysis_action_for_key["bingham_intermediate_pole"] = (
            self.actionBinghamIntermediatePole
        )

        self.actionBinghamMinorPole = QAction("Minor axis as pole", self)
        self.actionBinghamMinorPole.setCheckable(True)
        self.actionBinghamMinorPole.triggered.connect(
            lambda: self.toggle_analysis_actor("bingham_minor_pole")
        )
        self.menuAnalysis.addAction(self.actionBinghamMinorPole)
        self.analysis_action_for_key["bingham_minor_pole"] = self.actionBinghamMinorPole

        self.actionBinghamMinorGC = QAction("Great circle ⊥ minor axis", self)
        self.actionBinghamMinorGC.setCheckable(True)
        self.actionBinghamMinorGC.triggered.connect(
            lambda: self.toggle_analysis_actor("bingham_minor_gc")
        )
        self.menuAnalysis.addAction(self.actionBinghamMinorGC)
        self.analysis_action_for_key["bingham_minor_gc"] = self.actionBinghamMinorGC

        # self.menuAnalysis.addSection("Kent")

        # self.actionKentMeanDir = QAction("Mean direction as pole", self)
        # self.actionKentMeanDir.setCheckable(True)
        # self.actionKentMeanDir.triggered.connect(lambda: self.toggle_analysis_actor("kent_mean_pole"))
        # self.menuAnalysis.addAction(self.actionKentMeanDir)
        # self.analysis_action_for_key["kent_mean_pole"] = self.actionKentMeanDir

        # self.actionKentMeanGC = QAction("Great circle ⊥ mean direction", self)
        # self.actionKentMeanGC.setCheckable(True)
        # self.actionKentMeanGC.triggered.connect(lambda: self.toggle_analysis_actor("kent_mean_gc"))
        # self.menuAnalysis.addAction(self.actionKentMeanGC)
        # self.analysis_action_for_key["kent_mean_gc"] = self.actionKentMeanGC

        self.menuAnalysis.addSection("K-medoids")

        self.actionKmedoidsCenters = QAction("Cluster centers as poles", self)
        self.actionKmedoidsCenters.setCheckable(True)
        self.actionKmedoidsCenters.triggered.connect(
            lambda: self.toggle_analysis_actor("kmedoids_centers")
        )
        self.menuAnalysis.addAction(self.actionKmedoidsCenters)
        self.analysis_action_for_key["kmedoids_centers"] = self.actionKmedoidsCenters

        self.actionKmedoidsColor = QAction("Color Clusters", self)
        self.actionKmedoidsColor.setCheckable(True)
        self.actionKmedoidsColor.triggered.connect(
            lambda: self.toggle_analysis_actor("kmedoids_color")
        )
        self.menuAnalysis.addAction(self.actionKmedoidsColor)
        self.analysis_action_for_key["kmedoids_color"] = self.actionKmedoidsColor

        self.actionSeedPickingNormals = QAction(
            "Seed picking for clustering (Normals objects)", self
        )
        self.actionSeedPickingNormals.triggered.connect(
            lambda: self.seed_picking("normals")
        )
        self.menuAnalysis.addAction(self.actionSeedPickingNormals)

        self.actionSeedPickingLineations = QAction(
            "Seed picking for clustering (Lineations objects)", self
        )
        self.actionSeedPickingLineations.triggered.connect(
            lambda: self.seed_picking("lineations")
        )
        self.menuAnalysis.addAction(self.actionSeedPickingLineations)

    def connect_all_signals(self):
        super().connect_all_signals()
        self.sig_selection_lmb = lambda collection: self.on_selection_changed(
            collection
        )
        self.parent.signals.selection_changed.connect(self.sig_selection_lmb)

    def disconnect_all_signals(self):
        super().disconnect_all_signals()
        self.parent.signals.selection_changed.disconnect(self.sig_selection_lmb)

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
        if hasattr(self, "figure") and self.figure is not None:
            plt_close(self.figure)
            self.canvas.setParent(None)
            self.canvas.deleteLater()

        self.figure, self.ax = mplstereonet.subplots(projection=self.proj_type)

        # get a reference to the canvas that contains the figure
        self.canvas = FigureCanvas(self.figure)

        # Create Qt layout and add Matplotlib canvas (created above) as a widget to the Qt layout
        self.ViewFrameLayout.addWidget(self.canvas)
        if self.grid_kind == "hidden":
            self.ax.grid(False)
        elif self.grid_kind == "equatorial":
            self.ax.grid(True, kind="arbitrary", color="k", ls=":", zorder=self.Z_GRID)
        elif self.grid_kind == "polar":
            self.ax.grid(True, kind="polar", color="k", ls=":", zorder=self.Z_GRID)

        self.seed_pick_cid = self.canvas.mpl_connect(
            "button_press_event", self._on_seed_pick
        )

    def show_actor_with_property(
        self,
        uid=None,
        coll_name=None,
        show_property=None,
        visible=None,
    ):
        # self.print_terminal(f"DEBUG show_actor_with_property called for uid={uid}, visible={visible}")
        # self.print_terminal("".join(traceback.format_stack(limit=8)))
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
            point_size = this_coll.get_uid_legend(uid=uid)["point_size"]
            line_thick = this_coll.get_uid_legend(uid=uid)["line_thick"]
            opacity = this_coll.get_uid_legend(uid=uid)["opacity"] / 100
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
                    # Dip direction needs to be converted to strike (dz-90) to plot with mplstereonet
                    strike = (plot_entity.points_map_dip_direction - 90) % 360
                    dip = plot_entity.points_map_dip

                    if np_all(strike != None):
                        self.remove_actor_in_view(uid=uid, redraw=False)
                        if show_property == "Planes":
                            this_actor = self.ax.plane(
                                strike,
                                dip,
                                color=color_RGB,
                                linewidth=line_thick,
                                alpha=opacity,
                                zorder=self.Z_ENTITIES,
                            )[0]

                        elif show_property in ["none", "Poles", None]:
                            if self.contours is not None and visible is True:
                                if self.contours:
                                    self.ax.density_contourf(
                                        strike,
                                        dip,
                                        measurement="poles",
                                        zorder=self.Z_CONTOURS,
                                    )
                                else:
                                    self.ax.density_contour(
                                        strike,
                                        dip,
                                        measurement="poles",
                                        zorder=self.Z_CONTOURS,
                                    )

                            this_actor = self.ax.pole(
                                strike,
                                dip,
                                color=color_RGB,
                                markersize=point_size,
                                alpha=opacity,
                                zorder=self.Z_ENTITIES,
                            )[0]

                        else:
                            show_property_title = show_property

                            if show_property == "X":
                                prop_values = plot_entity.points_X
                            elif show_property == "Y":
                                prop_values = plot_entity.points_Y
                            elif show_property == "Z":
                                prop_values = plot_entity.points_Z
                            elif isinstance(
                                show_property, str
                            ) and show_property.endswith("]"):
                                pos1 = show_property.index("[")
                                pos2 = show_property.index("]")
                                original_prop = show_property[:pos1]
                                comp_index = int(show_property[pos1 + 1 : pos2])
                                prop_values = plot_entity.get_point_data(original_prop)[
                                    :, comp_index
                                ]
                                show_property_title = original_prop
                            else:
                                prop_values = plot_entity.get_point_data(show_property)

                            cmap_row = self.parent.prop_legend_df.loc[
                                self.parent.prop_legend_df["property_name"]
                                == show_property_title,
                                "colormap",
                            ]
                            show_property_cmap = (
                                cmap_row.values[0] if len(cmap_row) else "rainbow"
                            )

                            prop_values = np_asarray(prop_values).reshape(-1)
                            lon, lat = mplstereonet.pole(strike, dip)
                            this_actor = self.ax.scatter(
                                lon,
                                lat,
                                c=prop_values,
                                cmap=show_property_cmap,
                                s=point_size**2,
                                alpha=opacity,
                                zorder=self.Z_ENTITIES,
                            )
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

    # --- Helpers ---
    def _rebuild_all_entity_actors(self):
        """
        Redraw every entity actor currently known to this view (i.e. every uid
        in self.actors_df), on the current self.ax. Used after initialize_interactor()
        replaces the figure/axes, since every previously-drawn artist now belongs
        to a destroyed figure and must be recreated, not just have its visibility
        flipped.
        """
        existing_rows = self.actors_df.drop_duplicates(subset="uid", keep="last")
        new_rows = []

        for _, row in existing_rows.iterrows():
            uid = row["uid"]
            show = row["show"]
            collection_name = row["collection"]
            show_property = row["show_property"]

            if show:
                this_actor = self.show_actor_with_property(
                    uid=uid,
                    coll_name=collection_name,
                    show_property=show_property,
                    visible=True,
                )
            else:
                this_actor = None
                self.mpl_actors[uid] = None

            new_rows.append(
                {
                    "uid": uid,
                    "actor": this_actor,
                    "show": show,
                    "collection": collection_name,
                    "show_property": show_property,
                }
            )

        self.actors_df = pd_DataFrame(new_rows)
        self.figure.canvas.draw()

    def _rebuild_analysis_actors(self):
        """Redraw every currently-active analysis visual on the current self.ax,
        for the same reason as _rebuild_all_entity_actors: the old artists belong
        to a now-destroyed figure."""
        previously_active_keys = [
            key for key, actor in self.analysis_actors.items() if actor is not None
        ]
        self.analysis_actors = {}
        for key in previously_active_keys:
            self._show_analysis_actor(key)

    # --- View display toggles ---
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

        self._rebuild_all_entity_actors()
        self._rebuild_analysis_actors()

    def toggle_contours(self):
        """Display Kamb contours for visible poles in the stereoplot."""

        self.ViewFrameLayout.removeWidget(self.canvas)
        self.initialize_interactor()

        if self.contours == None:
            self.contours = False
            self.print_terminal("Contours enabled, unfilled")
        elif self.contours == False:
            self.contours = True
            self.print_terminal("Contours enabled, filled")
        else:
            self.contours = None
            self.print_terminal("Contours disabled")

        self._rebuild_all_entity_actors()
        self._rebuild_analysis_actors()

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

    # --- Orientation analysis: data pipeline ---
    def get_normals_and_lineations_for_analysis(self):
        """
        Walk through self.selected_uids and pull orientation data for statistical
        analysis. For each selected uid, look for a "Normals" point-data property
        and/or a "Lineations" point-data property, and stack whatever is found into
        two separate DataFrames, each with columns ["uid", "x", "y", "z"].

        A uid with neither property is skipped, and a message is printed to the
        terminal so the user knows it was excluded.

        Returns:
            normals_df (DataFrame): columns uid, x, y, z - one row per Normals vector
                found across all selected uids. Empty (0 rows) if none found.
            lineations_df (DataFrame): same shape, for Lineations vectors.
        """
        normals_rows = []
        lineations_rows = []

        if not self.parent.geol_coll.selected_uids:
            self.print_terminal("No entities selected for analysis.")
            return (
                pd_DataFrame(columns=["uid", "x", "y", "z"]),
                pd_DataFrame(columns=["uid", "x", "y", "z"]),
            )

        for uid in self.parent.geol_coll.selected_uids:
            vtk_obj = self.parent.geol_coll.get_uid_vtk_obj(uid)
            found_property = False

            if vtk_obj is None:
                self.print_terminal(f"uid {uid}: not found in geol_coll, skipped.")
                continue

            available_keys = vtk_obj.point_data_keys

            # ---- Normals ----
            if "Normals" in available_keys:
                normals_array = vtk_obj.get_point_data("Normals")
                # guard against a single-point entity, where reshape+squeeze
                # collapses (1, 3) down to (3,)
                if normals_array.ndim == 1:
                    normals_array = normals_array.reshape(1, -1)
                if normals_array.shape[0] > 0:
                    found_property = True
                    for row in normals_array:
                        normals_rows.append(
                            {"uid": uid, "x": row[0], "y": row[1], "z": row[2]}
                        )

            # ---- Lineations ----
            if "Lineations" in available_keys:
                lineations_array = vtk_obj.get_point_data("Lineations")
                if lineations_array.ndim == 1:
                    lineations_array = lineations_array.reshape(1, -1)
                if lineations_array.shape[0] > 0:
                    found_property = True
                    for row in lineations_array:
                        lineations_rows.append(
                            {"uid": uid, "x": row[0], "y": row[1], "z": row[2]}
                        )

            if not found_property:
                self.print_terminal(
                    f"uid {uid}: no Normals or Lineations property found, skipped."
                )

        normals_df = pd_DataFrame(normals_rows, columns=["uid", "x", "y", "z"])
        lineations_df = pd_DataFrame(lineations_rows, columns=["uid", "x", "y", "z"])

        return normals_df, lineations_df

    def recompute_values(self):
        """
        Recompute all orientation statistics (Fisher, Kent, Bingham, k-medoids)
        for the entities currently in self.selected_uids.

        This is a destructive recompute: any previously drawn analysis actors
        are removed from the canvas and self.analysis_actors is cleared, then
        self.analysis_results is rebuilt from scratch.

        Side effects
        ------------
        self.analysis_results : dict
            Rebuilt with keys "normals" and/or "lineations",
            each mapping to a dict with keys "fisher",
            "kent", "bingham", "kmedoids" - each value either the corresponding
            function's result dict, or None if that computation failed.
        self.analysis_actors : dict
            Cleared to {} after removing any live matplotlib artists it held.
        """
        previously_active_keys = [
            key for key, actor in self.analysis_actors.items() if actor is not None
        ]

        # Clear the old state
        # Remove any previously-drawn analysis artists from the canvas, then reset
        for key, actor in self.analysis_actors.items():
            if actor is not None:
                self._remove_analysis_actor(actor)

        self.analysis_actors = {}

        if hasattr(self, "figure"):
            self.figure.canvas.draw()

        self.analysis_results = {}

        # Get the objects
        normals_df, lineations_df = self.get_normals_and_lineations_for_analysis()
        normals_array = normals_df[["x", "y", "z"]].to_numpy()
        normals_array = resolve_lower_hemisphere(normals_array)
        lineations_array = lineations_df[["x", "y", "z"]].to_numpy()
        self.last_normals_array = normals_array
        self.last_lineations_array = lineations_array
        k = self.kmedoids_k  # The number of searched clusters

        # Statistics calculation block for the "Normals" objects
        if normals_array.shape[0] > 0:
            self.is_normals = True
            # Fisher parameters calculation
            try:
                fisher_result = fisherparams(normals_array, is_axial=True)
            except ValueError as e:
                self.print_terminal(f"Fisher stats failed: {e}")
                fisher_result = None

            # # Kent parameters calculation
            # try:
            #     kent_result = kentparams(normals_array, is_axial=True)
            # except ValueError as e:
            #     self.print_terminal(f"Kent stats failed: {e}")
            #     kent_result = None

            # Bingham parameters calculation
            try:
                bingham_result = bingham(normals_array, is_axial=True)
            except ValueError as e:
                self.print_terminal(f"Bingham stats failed: {e}")
                bingham_result = None

            # K-medoids clusters calculation
            try:
                # kmean_result = kmeans_clusters(normals_array, k, is_axial=True)
                kmean_result = kmedoids_clusters(normals_array, k, is_axial=True)
            except ValueError as e:
                self.print_terminal(f"K-medoids clusters failed: {e}")
                kmean_result = None
        else:
            self.is_normals = False
            fisher_result = None
            # kent_result = None
            bingham_result = None
            kmean_result = None

        df_temp = normals_df.copy()
        if kmean_result is not None:
            df_temp["clusters"] = kmean_result["labels"]
        else:
            df_temp["clusters"] = None
        self.last_normals_df = df_temp

        self.analysis_results["normals"] = {
            "fisher": fisher_result,
            # "kent": kent_result,
            "bingham": bingham_result,
            "kmedoids": kmean_result,
        }

        # Statistics calculation block for the "Lineation" objects
        if lineations_array.shape[0] > 0:
            self.is_lineations = True
            # Fisher parameters calculation
            try:
                fisher_result = fisherparams(lineations_array)
            except ValueError as e:
                self.print_terminal(f"Fisher stats failed: {e}")
                fisher_result = None

            # # Kent parameters calculation
            # try:
            #     kent_result = kentparams(lineations_array)
            # except ValueError as e:
            #     self.print_terminal(f"Kent stats failed: {e}")
            #     kent_result = None

            # Bingham parameters calculation
            try:
                bingham_result = bingham(lineations_array)
            except ValueError as e:
                self.print_terminal(f"Bingham stats failed: {e}")
                bingham_result = None

            # K-medoids clusters calculation
            try:
                # kmean_result = kmeans_clusters(lineations_array, k)
                kmean_result = kmedoids_clusters(lineations_array, k)
            except ValueError as e:
                self.print_terminal(f"K-medoids clusters failed: {e}")
                kmean_result = None
        else:
            self.is_lineations = False
            fisher_result = None
            kent_result = None
            bingham_result = None
            kmean_result = None

        df_temp = lineations_df.copy()
        if kmean_result is not None:
            df_temp["clusters"] = kmean_result["labels"]
        else:
            df_temp["clusters"] = None
        self.last_lineations_df = df_temp

        self.analysis_results["lineations"] = {
            "fisher": fisher_result,
            # "kent": kent_result,
            "bingham": bingham_result,
            "kmedoids": kmean_result,
        }

        for key in previously_active_keys:
            self.toggle_analysis_actor(key)

    def recompute_kmedoids_only(self):
        """
        Re-run k-medoids clustering only, using the same pooled vectors from the
        most recent full recompute_values() call , with the current self.kmedoids_k.
        Leaves fisher/kent/bingham results untouched.
        Does nothing if recompute_values has not yet run at least once.
        """
        if not hasattr(self, "last_normals_array"):
            self.print_terminal(
                "No data to recompute k-medoids on yet - run Recompute first."
            )
            return

        k = self.kmedoids_k

        if self.is_normals:
            if len(self.seed_pick_normals) == k:
                try:
                    # kmean_result = kmeans_clusters(self.last_normals_array, k,
                    #                                seeds=np_asarray(self.seed_pick_normals), is_axial=True)
                    kmean_result = kmedoids_clusters(
                        self.last_normals_array,
                        k,
                        seeds=np_asarray(self.seed_pick_normals),
                        is_axial=True,
                    )
                except ValueError as e:
                    self.print_terminal(f"K-medoids clusters failed: {e}")
                    kmean_result = None
            else:
                try:
                    # kmean_result = kmeans_clusters(self.last_normals_array, k, is_axial=True)
                    kmean_result = kmedoids_clusters(
                        self.last_normals_array, k, is_axial=True
                    )
                except ValueError as e:
                    self.print_terminal(f"K-medoids clusters failed: {e}")
                    kmean_result = None

            self.analysis_results["normals"]["kmedoids"] = kmean_result
            df_temp = self.last_normals_df.copy()
            if kmean_result is not None:
                df_temp["clusters"] = kmean_result["labels"]
            else:
                df_temp["clusters"] = None
            self.last_normals_df = df_temp
            for key in ["kmedoids_centers", "kmedoids_color"]:
                if self.analysis_actors.get(key) is not None:
                    self._hide_analysis_actor(key)
                    self._show_analysis_actor(key)

        if self.is_lineations:
            if len(self.seed_pick_lineations) == k:
                try:
                    # kmean_result = kmeans_clusters(self.last_lineations_array, k,
                    #                                seeds=np_asarray(self.seed_pick_lineations))
                    kmean_result = kmedoids_clusters(
                        self.last_lineations_array,
                        k,
                        seeds=np_asarray(self.seed_pick_lineations),
                    )
                except ValueError as e:
                    self.print_terminal(f"K-medoids clusters failed: {e}")
                    kmean_result = None
            else:
                try:
                    # kmean_result = kmeans_clusters(self.last_lineations_array, k)
                    kmean_result = kmedoids_clusters(self.last_lineations_array, k)
                except ValueError as e:
                    self.print_terminal(f"K-medoids clusters failed: {e}")
                    kmean_result = None

            self.analysis_results["lineations"]["kmedoids"] = kmean_result
            df_temp = self.last_lineations_df.copy()
            if kmean_result is not None:
                df_temp["clusters"] = kmean_result["labels"]
            else:
                df_temp["clusters"] = None
            self.last_lineations_df = df_temp
            for key in ["kmedoids_centers", "kmedoids_color"]:
                if self.analysis_actors.get(key) is not None:
                    self._hide_analysis_actor(key)
                    self._show_analysis_actor(key)

    def set_kmedoids_k(self, value):
        self.kmedoids_k = value
        self.recompute_kmedoids_only()

    def _on_seed_pick(self, event):
        """
        Function that create the concrete picking on the stereonet.
        """

        if not self.picking_seeds:
            return

        if event.xdata is None or event.ydata is None:
            return

        if self.seed_pick_kind == "normals":
            vectors = self.last_normals_array
            seeds = self.seed_pick_normals
        elif self.seed_pick_kind == "lineations":
            vectors = self.last_lineations_array
            seeds = self.seed_pick_lineations
        else:
            return

        if vectors is None or len(vectors) == 0:
            self.print_terminal("No vectors available for seed picking.")
            return

        points_xy = np_asarray(
            [self.seed_pick_projected_lon, self.seed_pick_projected_lat]
        ).T
        points_pixels = self.ax.transData.transform(points_xy)

        dx = points_pixels[:, 0] - event.x
        dy = points_pixels[:, 1] - event.y
        idx = int((dx * dx + dy * dy).argmin())

        seed = self.seed_pick_source_vectors[idx]

        # Avoid picking the same data point twice.
        for existing_seed in seeds:
            if np_all(existing_seed == seed):
                return

        seeds.append(seed)

        actor = self._draw_pole(seed, color="lime", marker="o", markersize=10)
        self.seed_pick_actors.append(actor)
        self.figure.canvas.draw()

        self.print_terminal(
            f"Picked {len(seeds)} / {self.seed_pick_target} {self.seed_pick_kind} seed(s)."
        )

        if len(seeds) >= self.seed_pick_target:
            self.picking_seeds = False
            self.print_terminal("Seed picking complete. Recomputing k-medoids.")
            self.recompute_kmedoids_only()
            self._clear_seed_pick_actors()

    def seed_picking(self, kind):
        """
        Function that launch the seed picking. The user select
        the number of cluster he want to calculate in a dialog
        window and then pick the seeds for the clustering.
        """
        self._clear_seed_pick_actors()

        if not hasattr(self, "last_normals_array") or not hasattr(
            self, "last_lineations_array"
        ):
            self.recompute_values()

        input_dict = {
            "number_of_clusters": ["Number of clusters: ", str(self.kmedoids_k)]
        }
        result = multiple_input_dialog(
            title="Number of clusters", input_dict=input_dict
        )
        if result is None:
            return

        try:
            k = int(result["number_of_clusters"])
        except (TypeError, ValueError):
            self.print_terminal("Invalid number of clusters.")
            return

        self.kmedoids_k = k
        self.seed_pick_kind = kind
        self.seed_pick_target = k
        self.picking_seeds = True

        if kind == "normals":
            self.seed_pick_normals = []
        elif kind == "lineations":
            self.seed_pick_lineations = []

        # Build projected points from the same source as show_actor_with_property
        # so click-matching lands on the actual drawn positions, not a re-derived position
        projected_lons = []
        projected_lats = []
        source_vectors = []

        for uid in self.parent.geol_coll.selected_uids:
            vtk_obj = self.parent.geol_coll.get_uid_vtk_obj(uid)
            if vtk_obj is None:
                continue
            if kind == "normals" and "Normals" not in vtk_obj.point_data_keys:
                continue
            if kind == "lineations" and "Lineations" not in vtk_obj.point_data_keys:
                continue
            strike = (vtk_obj.points_map_dip_direction - 90) % 360
            dip = vtk_obj.points_map_dip
            lon, lat = mplstereonet.pole(strike, dip)
            projected_lons.append(np_atleast_1d(lon))
            projected_lats.append(np_atleast_1d(lat))
            vectors = vtk_obj.get_point_data(
                "Normals" if kind == "normals" else "Lineations"
            )
            if vectors.ndim == 1:
                vectors = vectors.reshape(1, -1)
            source_vectors.append(vectors)

        if not projected_lons:
            self.print_terminal("No data available for seed picking.")
            self.picking_seeds = False
            return

        self.seed_pick_projected_lon = np_concatenate(projected_lons)
        self.seed_pick_projected_lat = np_concatenate(projected_lats)
        self.seed_pick_source_vectors = np_vstack(source_vectors)

        self.print_terminal(f"Pick {k} {kind} seed(s) on the stereonet.")

    def _project_vectors_to_stereonet(self, vectors):
        """
        Helper that project the existing vectors to the stereonet
        to find the closest point for seed picking.
        """

        vectors = np_asarray(vectors, dtype=float)
        plunge, bearing = mplstereonet.vector2plunge_bearing(
            vectors[:, 0],
            vectors[:, 1],
            vectors[:, 2],
        )
        strike, dip = mplstereonet.plunge_bearing2pole(plunge, bearing)
        lon, lat = mplstereonet.pole(strike, dip)
        return np_asarray(lon), np_asarray(lat)

    def _clear_seed_pick_actors(self):
        """ "
        Helper to erase the lime seeds once they are picked.
        """
        for actor in self.seed_pick_actors:
            self.remove_artist(actor)
        self.seed_pick_actors = []
        if hasattr(self, "figure") and self.figure is not None:
            self.figure.canvas.draw()

    # --- Orientation analysis: selection-driven auto-recompute ---
    def on_selection_changed(self, collection):
        """
        Detect the selection changes, if there is nothing
        selected anymore, it toggle off all the statitics
        in the Analysis menu.
        """

        if collection is not self.parent.geol_coll:
            return
        has_selection = bool(self.parent.geol_coll.selected_uids)
        self.actionRecompute.setEnabled(has_selection and not self.auto_recompute)
        if not self.auto_recompute:
            return
        self.recompute_values()

    def toggle_auto_recompute(self):
        """
        Toggle the auto recomputing of the statistics when
        the selection has changed. It also disable the manual
        recomputing.
        """
        self.auto_recompute = self.actionAutoRecompute.isChecked()
        self.actionRecompute.setEnabled(not self.auto_recompute)
        if self.auto_recompute:
            self.recompute_values()

    # --- Orientation analysis: drawing and visibility ---
    def toggle_analysis_actor(self, key):
        """
        Toggle visibility of one analysis visual, identified by key
        (e.g. "normals_bingham_major_pole"). If a live artist already exists
        for this key, it is hidden. Otherwise, it is shown.
        """
        if self.analysis_actors.get(key) is not None:
            self._hide_analysis_actor(key)
        else:
            self._show_analysis_actor(key)

    def _show_analysis_actor(self, key):
        """
        Draw one analysis visual identified by key, reading whatever data it
        needs from self.analysis_results, and store the resulting artist(s)
        into self.analysis_actors. If the required data isn't available, the
        visual isn't drawn and the corresponding menu checkbox (if any) is
        unchecked via self.analysis_action_for_key, so the checkbox state
        never claims something is shown when it isn't.
        """
        new_actor = None

        if key == "bingham_major_pole":
            new_actor = []
            for kind in ["normals", "lineations"]:
                bingham_result = self.analysis_results.get(kind, {}).get("bingham")
                if bingham_result is None:
                    self.print_terminal(f"No Bingham result available for {kind}.")
                    continue
                major_axis = bingham_result["axes"][0]
                marker = "s" if kind == "normals" else "o"
                new_actor.append(
                    self._draw_pole(
                        major_axis, color="red", marker=marker, markersize=10
                    )
                )
                self.print_terminal(f"Bingham major pole : {major_axis}")
            if not new_actor:
                new_actor = None

        elif key == "bingham_intermediate_pole":
            new_actor = []
            for kind in ["normals", "lineations"]:
                bingham_result = self.analysis_results.get(kind, {}).get("bingham")
                if bingham_result is None:
                    self.print_terminal(f"No Bingham result available for {kind}.")
                    continue
                intermediate_axis = bingham_result["axes"][1]
                marker = "s" if kind == "normals" else "o"
                new_actor.append(
                    self._draw_pole(
                        intermediate_axis, color="green", marker=marker, markersize=10
                    )
                )
                self.print_terminal(f"Bingham intermediate pole : {intermediate_axis}")
            if not new_actor:
                new_actor = None

        elif key == "bingham_minor_pole":
            new_actor = []
            for kind in ["normals", "lineations"]:
                bingham_result = self.analysis_results.get(kind, {}).get("bingham")
                if bingham_result is None:
                    self.print_terminal(f"No Bingham result available for {kind}.")
                    continue
                minor_axis = bingham_result["axes"][2]
                marker = "s" if kind == "normals" else "o"
                new_actor.append(
                    self._draw_pole(
                        minor_axis, color="blue", marker=marker, markersize=10
                    )
                )
                self.print_terminal(f"Bingham minor pole : {minor_axis}")
            if not new_actor:
                new_actor = None

        elif key == "bingham_minor_gc":
            new_actor = []
            for kind in ["normals", "lineations"]:
                bingham_result = self.analysis_results.get(kind, {}).get("bingham")
                if bingham_result is None:
                    self.print_terminal(f"No Bingham result available for {kind}.")
                    continue
                minor_axis = bingham_result["axes"][2]
                new_actor.append(self._draw_great_circle(minor_axis, color="blue"))
            if not new_actor:
                new_actor = None

        elif key == "kmedoids_centers":
            new_actor = []
            for kind in ["normals", "lineations"]:
                cluster_result = self.analysis_results.get(kind, {}).get("kmedoids")
                if cluster_result is None:
                    self.print_terminal(f"No clustering result available for {kind}.")
                    continue
                self.print_terminal(f"Kmedoids centers :")
                for centroid in cluster_result["centroids"]:
                    norm = np_linalg_norm(centroid)
                    if norm == 0:
                        continue
                    unit_centroid = centroid / norm
                    new_actor.append(
                        self._draw_pole(
                            unit_centroid, color="black", marker="^", markersize=10
                        )
                    )
                    self.print_terminal(f"   {unit_centroid}")
            if not new_actor:
                new_actor = None

        elif key == "kmedoids_color":
            new_actor = []
            for kind in ["normals", "lineations"]:
                cluster_result = self.analysis_results.get(kind, {}).get("kmedoids")
                if cluster_result is None:
                    self.print_terminal(f"No clustering result available for {kind}.")
                    continue
                df = (
                    self.last_normals_df
                    if kind == "normals"
                    else self.last_lineations_df
                )
                for (uid, cluster_id), group in df.groupby(["uid", "clusters"]):
                    vectors = group[["x", "y", "z"]].to_numpy()
                    palette = cm.get_cmap("tab10")
                    color = palette(cluster_id % 10)
                    new_actor.append(
                        self._draw_pole(vectors, color=color, markersize=8)
                    )
            if not new_actor:
                new_actor = None

        elif key == "fisher_mean_pole":
            new_actor = []
            for kind in ["normals", "lineations"]:
                fisher_result = self.analysis_results.get(kind, {}).get("fisher")
                if fisher_result is None:
                    self.print_terminal(f"No fisher result available for {kind}.")
                    continue
                mean_direction = fisher_result["mean_direction"][0]
                marker = "s" if kind == "normals" else "o"
                new_actor.append(
                    self._draw_pole(
                        mean_direction, color="purple", marker=marker, markersize=10
                    )
                )
                self.print_terminal(f"Fisher parameter : {fisher_result["kappa"]}")
            if not new_actor:
                new_actor = None

        # elif key == "kent_mean_pole":
        #     new_actor = []
        #     for kind in ["normals", "lineations"]:
        #         kent_result = self.analysis_results.get(kind, {}).get("kent")
        #         if kent_result is None:
        #             self.print_terminal(f"No kent result available for {kind}.")
        #             continue
        #         mean_direction = kent_result["axes"][0]
        #         marker = "s" if kind == "normals" else "o"
        #         new_actor.append(self._draw_pole(mean_direction, color="lightsteelblue", marker=marker, markersize=10))
        #         self.print_terminal(f"Kent parameters : {kent_result["kappa"]}, {kent_result["beta"]}")
        #     if not new_actor:
        #         new_actor = None

        # elif key == "kent_mean_gc":
        #     new_actor = []
        #     for kind in ["normals", "lineations"]:
        #         kent_result = self.analysis_results.get(kind, {}).get("kent")
        #         if kent_result is None:
        #             self.print_terminal(f"No kent result available for {kind}.")
        #             continue
        #         mean_gc = kent_result["axes"][0]
        #         new_actor.append(self._draw_great_circle(mean_gc, color="lightsteelblue"))
        #         self.print_terminal(f"Kent parameters : {kent_result["kappa"]}, {kent_result["beta"]}")
        #     if not new_actor:
        #         new_actor = None

        else:
            self.print_terminal(f"Unknown analysis actor key: '{key}'")
            return

        if new_actor is None:
            action = self.analysis_action_for_key.get(key)
            if action is not None:
                action.setChecked(False)
        else:
            self.analysis_actors[key] = new_actor
            self.figure.canvas.draw()

    def _hide_analysis_actor(self, key):
        """
        Remove the live artist(s) for one analysis visual, if any, and clear
        its entry in self.analysis_actors. Does nothing if nothing is shown
        for this key.
        """
        existing_actor = self.analysis_actors.get(key)
        if existing_actor is not None:
            self._remove_analysis_actor(existing_actor)
            self.analysis_actors[key] = None
            self.figure.canvas.draw()

    def _remove_analysis_actor(self, actor):
        """Remove one analysis actor, which may be a single matplotlib artist
        or a list of artists (e.g. k-medoids centers, one per cluster)."""

        actors_to_remove = actor if isinstance(actor, list) else [actor]
        for single_actor in actors_to_remove:
            self.remove_artist(single_actor)

    def _draw_pole(self, vector, **kwargs):
        """
        Convert one or more cartesian unit vectors into strike/dip and plot
        them as poles on self.ax. Accepts a single vector of shape (3,) or
        multiple vectors as an array of shape (N, 3) - in the array case,
        every point is drawn in a single matplotlib call, producing one
        artist rather than one artist per point.
        Returns the matplotlib artist created.
        """
        vector = np_asarray(vector, dtype=float)
        kwargs.setdefault("zorder", self.Z_STATS)

        if vector.ndim == 1:
            x, y, z = vector
        else:
            x, y, z = vector[:, 0], vector[:, 1], vector[:, 2]

        plunge, bearing = mplstereonet.vector2plunge_bearing(x, y, z)
        strike, dip = mplstereonet.plunge_bearing2pole(plunge, bearing)
        actor = self.ax.pole(strike, dip, **kwargs)[0]
        return actor

    def _draw_great_circle(self, vector, **kwargs):
        """
        Convert one or more cartesian unit vectors into strike/dip, treating
        each as the POLE of a plane, and plot those planes as great circles
        on self.ax. Accepts a single vector of shape (3,) or multiple vectors
        as an array of shape (N, 3), drawn in a single matplotlib call.
        Returns the matplotlib artist created.
        """
        vector = np_asarray(vector, dtype=float)
        kwargs.setdefault("zorder", self.Z_STATS)

        if vector.ndim == 1:
            x, y, z = vector
        else:
            x, y, z = vector[:, 0], vector[:, 1], vector[:, 2]

        plunge, bearing = mplstereonet.vector2plunge_bearing(x, y, z)
        strike, dip = mplstereonet.plunge_bearing2pole(plunge, bearing)
        actor = self.ax.plane(strike, dip, **kwargs)[0]
        return actor

    # --- Clusters saving: saving the clusters as property ---
    def save_clusters_as_property(self, property_name):
        """
        Write the most recently computed k-medoids cluster assignment (currently
        cached in self.last_normals_df / self.last_lineations_df) onto each
        contributing entity in geol_coll, as a new 1-component point-data
        property named property_name.
        """
        for df, kind in [
            (getattr(self, "last_normals_df", None), "Normals"),
            (getattr(self, "last_lineations_df", None), "Lineations"),
        ]:
            if df is None or "clusters" not in df.columns:
                continue
            if df["clusters"].isnull().all():
                continue

            for uid, group in df.groupby("uid"):
                cluster_values = group["clusters"].to_numpy().reshape(-1, 1)
                vtk_obj = self.parent.geol_coll.get_uid_vtk_obj(uid)
                if vtk_obj is None:
                    self.print_terminal(
                        f"uid {uid}: not found, skipped while saving clusters."
                    )
                    continue
                self.parent.geol_coll.append_uid_property(
                    uid=uid, property_name=property_name, property_components=1
                )
                vtk_obj.set_point_data(
                    data_key=property_name, attribute_matrix=cluster_values
                )
                self.print_terminal(f"Saved '{property_name}' on uid {uid} ({kind}).")
        self.parent.prop_legend.update_widget(self.parent)

    def prompt_and_save_clusters(self):
        """Ask the user for a property name, then save the current cluster
        assignment onto each contributing entity under that name."""
        input_dict = {"property_name": ["Property name: ", "clusters"]}
        updt_dict = multiple_input_dialog(
            title="Save clusters as property", input_dict=input_dict
        )
        if updt_dict is None:
            return
        property_name = updt_dict["property_name"]
        if not property_name:
            self.print_terminal("No property name entered - clusters not saved.")
            return
        self.save_clusters_as_property(property_name=property_name)
