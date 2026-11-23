"""view_stereoplot.py
PZero© Andrea Bistacchi"""

# PySide6 imports____
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QSpinBox, QWidgetAction

# numpy import____
from numpy import all as np_all
from numpy import ndarray as np_ndarray
from numpy import pi as np_pi
from numpy import sin as np_sin
from numpy import cos as np_cos
from numpy.linalg import norm as np_linalg_norm
from numpy import asarray as np_asarray
from numpy import atleast_1d as np_atleast_1d
from numpy import concatenate as np_concatenate
from numpy import vstack as np_vstack
from numpy import where as np_where
from numpy import isfinite as np_isfinite

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
from pzero.helpers.helper_dialogs import multiple_input_dialog, save_file_dialog

# mplstereonet import____
import mplstereonet

# Moving the mouse over the figure far outside the stereonet circle (e.g. the corners), matplotlib
# converts the cursor position to stereonet coordinates, and the inverse projection of mplstereonet
# warns "invalid value encountered in arcsin" (the point has no stereonet coordinates: NaN, no
# coordinates are shown). Harmless: ignore only this warning of that module.
import warnings as _warnings

_warnings.filterwarnings(
    "ignore",
    message="invalid value encountered in arcsin",
    category=RuntimeWarning,
    module=r"mplstereonet\.stereonet_transforms",
)

# Matplotlib imports____
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.pyplot import close as plt_close
from matplotlib.widgets import RectangleSelector
from matplotlib.widgets import LassoSelector
from matplotlib.path import Path as mpl_Path
import matplotlib.cm as cm


class KSpinBoxAction(QWidgetAction):
    """Number of k-medoids clusters in the Analysis menu. A new spin box is created for each place
    the menu is shown (also a detached / torn-off copy of the menu, where a single default widget
    would disappear); all of them show the view's kmedoids_k."""

    def __init__(self, view):
        super().__init__(view)
        self.view = view

    def createWidget(self, parent):
        spinbox = QSpinBox(parent)
        spinbox.setMinimum(1)
        spinbox.setPrefix("k = ")
        spinbox.setValue(self.view.kmedoids_k)
        spinbox.valueChanged.connect(self.view.set_kmedoids_k)
        return spinbox

    def sync(self, value):
        for spinbox in self.createdWidgets():
            if spinbox.value() != value:
                spinbox.blockSignals(True)
                spinbox.setValue(value)
                spinbox.blockSignals(False)


class StereoActor:
    """The matplotlib artists of one entity in the stereoplot (markers of the two hemispheres,
    great circles, contours), shown, hidden and removed together. Duck-types the artist methods
    used by ViewMPL (set_visible, get_visible, remove, figure)."""

    def __init__(self, artists):
        self.artists = [artist for artist in artists if artist is not None]

    @property
    def figure(self):
        return self.artists[0].figure

    def get_visible(self):
        return any(artist.get_visible() for artist in self.artists)

    def set_visible(self, visible):
        for artist in self.artists:
            artist.set_visible(bool(visible))

    def remove(self):
        for artist in self.artists:
            try:
                artist.remove()
            except (ValueError, AttributeError, NotImplementedError):
                pass
        self.artists = []


class ViewStereoplot(ViewMPL):

    MARKER_SIZE = 4

    # Printed when k-medoids results of Normals are shown (see orientation_analysis.kmedoids_clusters).
    KMEDOIDS_NORMALS_NOTE = (
        "Note: k-medoids on Normals is biaxial: each normal is clustered together with its "
        "antipode (the data are doubled), so a cluster and its antipodal copy can both be found, "
        "giving two (nearly) identical centers; centers are shown on the lower hemisphere."
    )

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
        # Entities with more Normals + Lineations vectors than this are drawn as density contours
        # in their legend color instead of markers (View > Contours-only threshold).
        self.contours_only_threshold = 20000
        # View > Toggle poles (markers of Normals and Lineations) and Toggle great circles (planes
        # of the Normals of all entities, in addition to the "Planes" shown property).
        self.show_poles = True
        self.show_great_circles = False
        # Toggle contours: one density of all the shown entities together (pooled), updated after
        # entities are shown, hidden, added, removed or redrawn.
        self.pooled_contour_actor = None
        self._pooled_contours_pending = False
        self._contours_only_uids = set()  # entities already reported as drawn as contours only
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
        # Statistics are computed on the shown entities, only when needed (a checked overlay,
        # seed picking, saving clusters, exporting the summary); _stats_dirty marks them out of date.
        self._stats_dirty = True
        self.picking_seeds = False
        self.seed_pick_kind = None
        self.seed_pick_target = 0
        self.seed_pick_normals = []
        self.seed_pick_lineations = []
        self.seed_pick_actors = []
        self.seed_pick_cid = None
        self.rectangle_selector = None  # holds the active RectangleSelector widget
        self.selection_tool_active = False
        # Selection highlight: yellow rings on the poles of the selected entities shown in this view.
        self.selection_highlight_actor = None
        self.selection_highlight_uids = set()
        self._highlight_pending = False

        # In __init__:
        self.selection_press_cid = None
        self.selection_motion_cid = None
        self.selection_release_cid = None
        self.selection_start = None  # (lon, lat) in data coords
        self.selection_patch = None  # the drawn region patch

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

        self.actionTogglePoles = QAction("Toggle poles", self)
        self.actionTogglePoles.triggered.connect(self.toggle_poles)
        self.menuView.addAction(self.actionTogglePoles)

        self.actionToggleGreatCircles = QAction("Toggle great circles", self)
        self.actionToggleGreatCircles.triggered.connect(self.toggle_great_circles)
        self.menuView.addAction(self.actionToggleGreatCircles)

        self.actionContoursThreshold = QAction("Contours-only threshold...", self)
        self.actionContoursThreshold.triggered.connect(self.set_contours_only_threshold)
        self.menuView.addAction(self.actionContoursThreshold)

        self.actionSetPolar = QAction("Toggle grid", self)
        self.actionSetPolar.triggered.connect(self.toggle_grid)
        self.menuView.addAction(self.actionSetPolar)

        self.actionSavePng = QAction("Export as PNG", self)
        self.actionSavePng.triggered.connect(self.export_png)
        self.menuView.addAction(self.actionSavePng)

        # ---- Select Menu ----
        self.actionSelectionTool = QAction("By polygon", self)
        self.actionSelectionTool.triggered.connect(self.toggle_selection_tool)
        self.menuSelect.addAction(self.actionSelectionTool)

        # Same as the other views: deselect the entities of this view (Ctrl+Shift+A).
        self.actionClearSelection = QAction("Clear Selection", self)
        self.actionClearSelection.triggered.connect(self.deselect_all_in_view)
        self.menuSelect.addAction(self.actionClearSelection)

        # ---- Analysis Menu ----
        self.actionSaveClusters = QAction("Save clusters as a property", self)
        self.actionSaveClusters.triggered.connect(self.prompt_and_save_clusters)
        self.menuAnalysis.addAction(self.actionSaveClusters)

        self.menuAnalysis.addSection("Kmedoids clusters")

        self.kmedoids_k_widget_action = KSpinBoxAction(self)
        self.menuAnalysis.addAction(self.kmedoids_k_widget_action)

        self.actionExportStats = QAction("Export statistics summary", self)
        self.actionExportStats.triggered.connect(self.export_statistics_summary)
        self.menuAnalysis.addAction(self.actionExportStats)

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
        # Take the keyboard focus on click, so that the view shortcuts (Ctrl+A, Ctrl+Shift+A) work
        # in the graphics (the matplotlib canvas has no focus policy by default).
        self.canvas.setFocusPolicy(Qt.ClickFocus)

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

    # --- Entity drawing helpers ---
    @staticmethod
    def _entity_vectors(vtk_obj, key):
        """Unit vectors (N x 3) of the point property key ("Normals" or "Lineations") of vtk_obj,
        and the boolean mask (on the original points) of the valid ones (finite, non-zero).
        Returns (None, None) if the property is missing or empty."""
        if vtk_obj is None or key not in vtk_obj.point_data_keys:
            return None, None
        vectors = np_asarray(vtk_obj.get_point_data(key), dtype=float)
        if vectors.size == 0:
            return None, None
        vectors = vectors.reshape(-1, 3)
        norms = np_linalg_norm(vectors, axis=1)
        valid = np_isfinite(norms) & (norms > 0)
        if not valid.any():
            return None, None
        return vectors[valid] / norms[valid][:, None], valid

    @staticmethod
    def _vectors_to_lonlat(vectors):
        """Stereonet coordinates of unit vectors (x east, y north, z up), and the mask of the upward
        ones. Downward vectors are projected on the lower hemisphere. Upward vectors (poles of
        overturned planes, upward lineations, i.e. negative plunge) are projected on the upper
        hemisphere at their own trend, which is the position of (x, y, -z) on the lower one."""
        vectors = np_asarray(vectors, dtype=float).reshape(-1, 3)
        upward = vectors[:, 2] > 0
        folded = vectors.copy()
        folded[upward, 2] *= -1
        plunge, trend = mplstereonet.vector2plunge_bearing(
            folded[:, 0], folded[:, 1], folded[:, 2]
        )
        lon, lat = mplstereonet.line(plunge, trend)
        return np_atleast_1d(lon), np_atleast_1d(lat), upward

    def _entity_lonlat(self, vtk_obj, keys=("Normals", "Lineations")):
        """Stereonet coordinates of all the Normals and Lineations of an entity, concatenated
        (same positions as drawn by show_actor_with_property). Returns (lon, lat, vectors) or
        (None, None, None) if the entity has no valid vectors."""
        lons, lats, vecs = [], [], []
        for key in keys:
            vectors, _ = self._entity_vectors(vtk_obj, key)
            if vectors is None:
                continue
            lon, lat, _ = self._vectors_to_lonlat(vectors)
            lons.append(lon)
            lats.append(lat)
            vecs.append(vectors)
        if not lons:
            return None, None, None
        return np_concatenate(lons), np_concatenate(lats), np_vstack(vecs)

    def _entity_style(self, uid, collection):
        """(RGB color, opacity) of an entity from the legend of its collection (gray if none)."""
        try:
            legend = collection.get_uid_legend(uid=uid)
            color = [legend["color_R"] / 255, legend["color_G"] / 255, legend["color_B"] / 255]
            opacity = legend["opacity"] / 100
        except Exception:
            color, opacity = [0.5, 0.5, 0.5], 1.0
        return color, opacity

    def _property_colors(self, vtk_obj, show_property, valid, opacity):
        """RGBA colors (one per valid point) for a scalar property, with the colormap of the
        property legend, or None if the property cannot be read."""
        from matplotlib import colormaps
        from matplotlib.colors import Normalize

        try:
            show_property_title = show_property
            if show_property == "X":
                values = vtk_obj.points_X
            elif show_property == "Y":
                values = vtk_obj.points_Y
            elif show_property == "Z":
                values = vtk_obj.points_Z
            elif isinstance(show_property, str) and show_property.endswith("]"):
                pos1 = show_property.index("[")
                pos2 = show_property.index("]")
                show_property_title = show_property[:pos1]
                comp_index = int(show_property[pos1 + 1 : pos2])
                values = np_asarray(vtk_obj.get_point_data(show_property_title)).reshape(
                    vtk_obj.points_number, -1
                )[:, comp_index]
            else:
                values = vtk_obj.get_point_data(show_property)
            values = np_asarray(values, dtype=float).reshape(-1)[valid]
        except Exception:
            return None
        cmap_row = self.parent.prop_legend_df.loc[
            self.parent.prop_legend_df["property_name"] == show_property_title, "colormap"
        ]
        cmap_name = cmap_row.values[0] if len(cmap_row) else "rainbow"
        try:
            cmap = colormaps[cmap_name]
        except KeyError:
            cmap = colormaps["rainbow"]
        finite = values[np_isfinite(values)]
        vmin, vmax = (finite.min(), finite.max()) if finite.size else (0.0, 1.0)
        rgba = cmap(Normalize(vmin=vmin, vmax=vmax)(values))
        rgba[:, 3] = opacity
        return rgba

    def _draw_markers(self, lon, lat, upward, colors, opacity, marker):
        """One scatter artist: filled markers for the lower hemisphere, hollow markers (same color
        and size) for the upper hemisphere. colors is one RGB color or an N x 4 RGBA array."""
        from matplotlib.colors import to_rgba_array

        if np_asarray(colors).ndim == 1:
            edge = to_rgba_array([list(colors) + [opacity]] * lon.size)
        else:
            edge = np_asarray(colors, dtype=float)
        face = edge.copy()
        face[upward, 3] = 0.0
        return self.ax.scatter(
            lon,
            lat,
            s=self.MARKER_SIZE**2,
            marker=marker,
            facecolors=face,
            edgecolors=edge,
            linewidths=1.0,
            zorder=self.Z_ENTITIES,
        )

    def _draw_planes(self, normals, color, opacity):
        """Great circles of the planes with the given normals, as one line per hemisphere
        (NaN-separated segments): solid for upright planes, dashed for overturned ones."""
        from numpy import full as np_full
        from numpy import nan as np_nan

        artists = []
        upward = normals[:, 2] > 0
        for subset, style in ((~upward, "-"), (upward, "--")):
            these = normals[subset]
            if these.shape[0] == 0:
                continue
            down = these.copy()
            down[down[:, 2] > 0] *= -1
            plunge, trend = mplstereonet.vector2plunge_bearing(down[:, 0], down[:, 1], down[:, 2])
            strike, dip = mplstereonet.plunge_bearing2pole(plunge, trend)
            lon, lat = mplstereonet.plane(np_atleast_1d(strike), np_atleast_1d(dip))
            lon = np_vstack([lon, np_full((1, lon.shape[1]), np_nan)]).T.ravel()
            lat = np_vstack([lat, np_full((1, lat.shape[1]), np_nan)]).T.ravel()
            artists.append(
                self.ax.plot(
                    lon,
                    lat,
                    linestyle=style,
                    color=color,
                    alpha=opacity,
                    linewidth=1.0,
                    zorder=self.Z_ENTITIES,
                )[0]
            )
        return artists

    def _draw_density(self, lon, lat, color=None, filled=False):
        """Exponential Kamb contours of the given stereonet points (axial counting, so both
        hemispheres count together). With color, contour lines in that color (entities shown as
        contours only); otherwise the default colormap, filled or not (Toggle contours)."""
        from pzero.orientation_analysis import kamb_density_grid

        from matplotlib.ticker import MaxNLocator

        lon_grid, lat_grid, density = kamb_density_grid(lon, lat)
        levels = MaxNLocator(nbins=8).tick_values(0.0, float(density.max()))
        levels = levels[levels > 0]  # no level at 0: the empty background is not filled
        if levels.size < 2:
            return None
        if color is not None:
            return self.ax.contour(
                lon_grid, lat_grid, density, levels=levels, colors=[color], linewidths=1.0,
                zorder=self.Z_CONTOURS,
            )
        if filled:
            return self.ax.contourf(
                lon_grid, lat_grid, density, levels=levels, cmap="Blues", alpha=0.8,
                zorder=self.Z_CONTOURS,
            )
        return self.ax.contour(
            lon_grid, lat_grid, density, levels=levels, cmap="viridis", linewidths=1.0,
            zorder=self.Z_CONTOURS,
        )

    def show_actor_with_property(
        self,
        uid=None,
        coll_name=None,
        show_property=None,
        visible=None,
    ):
        """Draw an entity of any class and collection from its Normals (as poles, circles) and/or
        Lineations (triangles) point properties. Downward vectors are filled markers on the lower
        hemisphere, upward vectors (overturned planes, negative plunge) hollow markers on the
        upper hemisphere. Entities with more than contours_only_threshold vectors are drawn as
        density contours in their legend color. show_property: "Poles" (default), "Planes"
        (great circles of the Normals) or a scalar property used to color the markers.
        The artists of one entity are grouped in a single StereoActor (or None if nothing to draw)."""
        if show_property in [None, "none"]:
            show_property = "Poles"
        self.remove_actor_in_view(uid=uid, redraw=False)
        this_actor = None
        collection = getattr(self.parent, coll_name, None) if coll_name else None
        vtk_obj = collection.get_uid_vtk_obj(uid) if collection is not None else None
        if vtk_obj is not None:
            color, opacity = self._entity_style(uid, collection)
            artists = []
            all_lon, all_lat = [], []
            n_vectors = 0
            parts = []
            for key, marker in (("Normals", "o"), ("Lineations", "^")):
                vectors, valid = self._entity_vectors(vtk_obj, key)
                if vectors is None:
                    continue
                lon, lat, upward = self._vectors_to_lonlat(vectors)
                parts.append((key, marker, vectors, valid, lon, lat, upward))
                all_lon.append(lon)
                all_lat.append(lat)
                n_vectors += vectors.shape[0]
            if parts:
                all_lon = np_concatenate(all_lon)
                all_lat = np_concatenate(all_lat)
                contours_only = n_vectors > self.contours_only_threshold
                if contours_only and uid not in self._contours_only_uids:
                    # Say it once per entity (and again after the threshold changes).
                    self._contours_only_uids.add(uid)
                    self.print_terminal(
                        f"Stereoplot: {collection.get_uid_name(uid)} has {n_vectors} vectors "
                        f"(> {self.contours_only_threshold}), drawn as contours in its color "
                        f"instead of poles (View > Contours-only threshold)."
                    )
                elif not contours_only:
                    self._contours_only_uids.discard(uid)
                if contours_only:
                    # Too many vectors for markers: density lines in the entity color, shown and
                    # hidden as its poles (Toggle poles).
                    if self.show_poles:
                        artists.append(self._draw_density(all_lon, all_lat, color=color))
                else:
                    for key, marker, vectors, valid, lon, lat, upward in parts:
                        if key == "Normals" and (
                            self.show_great_circles or show_property == "Planes"
                        ):
                            artists.extend(self._draw_planes(vectors, color, opacity))
                        if show_property == "Planes" and key == "Normals":
                            continue
                        if not self.show_poles:
                            continue
                        colors = color
                        if show_property not in ["Poles", "Planes"]:
                            rgba = self._property_colors(vtk_obj, show_property, valid, opacity)
                            if rgba is not None:
                                colors = rgba
                        artists.append(
                            self._draw_markers(lon, lat, upward, colors, opacity, marker)
                        )
            if artists:
                this_actor = StereoActor(artists)
                if visible is False:
                    this_actor.set_visible(False)
                this_actor.figure.canvas.draw_idle()
        self.mpl_actors[uid] = this_actor
        self._schedule_pooled_contours()
        self._schedule_highlight()
        return this_actor

    def set_actor_visible(self, uid=None, visible=None):
        super().set_actor_visible(uid=uid, visible=visible)
        self._schedule_pooled_contours()
        self._schedule_highlight()

    def remove_actor_in_view(self, uid=None, redraw=False):
        super().remove_actor_in_view(uid=uid, redraw=redraw)
        self._schedule_pooled_contours()
        self._schedule_highlight()

    def _schedule_pooled_contours(self):
        """The shown entities (or their vectors) may have changed: update the pooled contours and
        the checked statistics overlays once, at the next event loop iteration (after the
        visibility and the list of the entities in this view have been updated)."""
        self._stats_dirty = True
        if (
            self.contours is None
            and self.pooled_contour_actor is None
            and not self._checked_analysis_keys()
        ):
            return
        if not self._pooled_contours_pending:
            self._pooled_contours_pending = True
            QTimer.singleShot(0, self._update_shown_dependent)

    def _update_shown_dependent(self):
        """Pooled contours and checked statistics overlays, from the shown entities."""
        self._update_pooled_contours()
        if self._checked_analysis_keys():
            self.recompute_values()

    def _shown_entities(self):
        """(uid, collection, vtk_obj) of the entities shown in this view, in tree order. Contours
        and statistics are computed on these."""
        for _, row in self.actors_df.drop_duplicates(subset="uid", keep="last").iterrows():
            if not row["show"]:
                continue
            collection = getattr(self.parent, row["collection"], None)
            vtk_obj = collection.get_uid_vtk_obj(row["uid"]) if collection is not None else None
            if vtk_obj is not None:
                yield row["uid"], collection, vtk_obj

    def _checked_analysis_keys(self):
        """Statistics overlays whose checkbox (Analysis menu) is checked."""
        return [
            key
            for key, action in getattr(self, "analysis_action_for_key", {}).items()
            if action.isChecked()
        ]

    def _ensure_stats(self):
        """Compute the statistics of the shown entities if they are out of date."""
        if self._stats_dirty or not hasattr(self, "last_normals_array"):
            self.recompute_values()

    def _update_pooled_contours(self):
        """Toggle contours: density contours (lines or filled) of the Normals and Lineations of
        all the shown entities together."""
        self._pooled_contours_pending = False
        if self.pooled_contour_actor is not None:
            try:
                self.pooled_contour_actor.remove()
            except Exception:
                pass  # it belonged to a figure that has been replaced
            self.pooled_contour_actor = None
        if self.contours is None or not hasattr(self, "ax"):
            if hasattr(self, "figure"):
                self.figure.canvas.draw_idle()
            return
        lons, lats = [], []
        for _, _, vtk_obj in self._shown_entities():
            lon, lat, _ = self._entity_lonlat(vtk_obj)
            if lon is not None:
                lons.append(lon)
                lats.append(lat)
        if lons:
            self.pooled_contour_actor = self._draw_density(
                np_concatenate(lons), np_concatenate(lats), filled=bool(self.contours)
            )
        self.figure.canvas.draw_idle()

    def _redraw_entities(self, updated_uids):
        """Redraw entities after a legend change (color, opacity), keeping their visibility and
        shown property."""
        rows = self.actors_df.drop_duplicates(subset="uid", keep="last").set_index("uid")
        for uid in updated_uids or []:
            if uid not in rows.index or self.mpl_actors.get(uid) is None:
                continue
            row = rows.loc[uid]
            self.show_actor_with_property(
                uid=uid,
                coll_name=row["collection"],
                show_property=row["show_property"],
                visible=bool(row["show"]),
            )

    def entities_data_val_modified_update_views(self, updated_uids=None, collection=None):
        """Normals / Lineations values changed (e.g. Invert polarity, Calculate Normals): the
        positions of the poles change whatever property is shown, so redraw (contours and the
        checked statistics follow)."""
        updated_uids = collection.filter_uids(query=self.view_filter, uids=updated_uids)
        self._redraw_entities(updated_uids)

    def change_actor_color(self, updated_uids: list = None, collection=None):
        """Markers use per-point face/edge colors (hollow upper hemisphere), so redraw."""
        self._redraw_entities(updated_uids)

    def change_actor_opacity(self, updated_uids: list = None, collection=None):
        """Markers use per-point face/edge colors (hollow upper hemisphere), so redraw."""
        self._redraw_entities(updated_uids)

    def toggle_poles(self):
        """Show or hide the poles and lineations of all entities (e.g. to see the contours)."""
        self.show_poles = not self.show_poles
        self.print_terminal("Poles shown" if self.show_poles else "Poles hidden")
        self._rebuild_all_entity_actors()

    def toggle_great_circles(self):
        """Show or hide the great circles of the Normals of all entities."""
        self.show_great_circles = not self.show_great_circles
        self.print_terminal(
            "Great circles shown" if self.show_great_circles else "Great circles hidden"
        )
        self._rebuild_all_entity_actors()

    def set_contours_only_threshold(self):
        """Ask the number of vectors above which an entity is drawn as contours only."""
        result = multiple_input_dialog(
            title="Contours-only threshold",
            input_dict={
                "threshold": [
                    "Entities with more vectors than this are drawn as contours: ",
                    str(self.contours_only_threshold),
                ]
            },
        )
        if result is None:
            return
        try:
            threshold = int(result["threshold"])
        except (TypeError, ValueError):
            self.print_terminal("Invalid threshold.")
            return
        self.contours_only_threshold = max(0, threshold)
        self._contours_only_uids = set()
        self.print_terminal(f"Contours-only threshold: {self.contours_only_threshold} vectors")
        self._rebuild_all_entity_actors()
        self.figure.canvas.draw()

    def change_actor_point_size(self, updated_uids: list = None, collection=None):
        """
        Override ViewMPL's change_actor_point_size to do nothing in the stereoplot.
        Point size is fixed here regardless of the legend value, since the legend
        point size is also tied to the 3D view and other views where scale is
        physically meaningful — changes there would make the stereonet unreadable.
        """
        pass

    def change_actor_line_thick(self, updated_uids: list = None, collection=None):
        """
        Override ViewMPL's change_actor_line_thick to do nothing in the stereoplot.
        Line thickness is fixed here regardless of the legend value, since the legend
        line thickness is also tied to the 3D view and other views where scale is
        physically meaningful — changes there would make the stereonet unreadable.
        """
        pass

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

            this_actor = self.show_actor_with_property(
                uid=uid,
                coll_name=collection_name,
                show_property=show_property,
                visible=bool(show),
            )

            new_rows.append(
                {
                    "uid": uid,
                    "actor": this_actor,
                    "show": show,
                    "collection": collection_name,
                    "show_property": show_property,
                }
            )

        self._deactivate_selection()

        self.actors_df = pd_DataFrame(new_rows)
        self.figure.canvas.draw()

    def _rebuild_analysis_actors(self):
        """Redraw every currently-active analysis visual on the current self.ax,
        for the same reason as _rebuild_all_entity_actors: the old artists belong
        to a now-destroyed figure."""
        self.analysis_actors = {}
        for key in self._checked_analysis_keys():
            self._show_analysis_actor(key, verbose=False)

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
        """Cycle the density contours of all the shown entities: lines, filled, none."""
        if self.contours == None:
            self.contours = False
            self.print_terminal("Contours enabled, unfilled")
        elif self.contours == False:
            self.contours = True
            self.print_terminal("Contours enabled, filled")
        else:
            self.contours = None
            self.print_terminal("Contours disabled")
        self._update_pooled_contours()

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

    def export_png(self):
        """
        Save the stereonet as a picutre (.png)
        """
        out_file_name = save_file_dialog(
            parent=self, caption="Export Stereoplot view as PNG.", filter="png (*.png)"
        ).removesuffix(".png")
        self.figure.savefig(out_file_name, dpi=300)
        self.print_terminal(f"Stereoplot view saved as {out_file_name}.")

    # --- Orientation analysis: data pipeline ---
    def get_normals_and_lineations_for_analysis(self):
        """
        Stack the Normals and Lineations vectors of the entities shown in this view (as the pooled
        contours), each into a DataFrame with columns ["uid", "x", "y", "z"]. Hidden entities and
        the tree selection do not matter.

        Returns:
            normals_df (DataFrame): one row per valid Normals vector. Empty if none.
            lineations_df (DataFrame): same shape, for Lineations vectors.
        """
        columns = ["uid", "x", "y", "z"]
        frames = {"Normals": [], "Lineations": []}
        for uid, _, vtk_obj in self._shown_entities():
            for key in frames:
                vectors, _ = self._entity_vectors(vtk_obj, key)
                if vectors is None:
                    continue
                frame = pd_DataFrame(vectors, columns=["x", "y", "z"])
                frame.insert(0, "uid", uid)
                frames[key].append(frame)

        normals_df, lineations_df = (
            pd_concat(frames[key], ignore_index=True)
            if frames[key]
            else pd_DataFrame(columns=columns)
            for key in ("Normals", "Lineations")
        )
        return normals_df, lineations_df

    def recompute_values(self):
        """
        Recompute all orientation statistics (Fisher, Kent, Bingham, k-medoids)
        for the entities shown in this view, then redraw the overlays whose checkbox
        is checked. Called automatically when needed (see _schedule_pooled_contours,
        _ensure_stats): there is no Recompute command.

        Any previously drawn analysis actors are removed from the canvas and
        self.analysis_actors is cleared, then self.analysis_results is rebuilt.

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

        self._stats_dirty = False
        for key in self._checked_analysis_keys():
            self._show_analysis_actor(key, verbose=False)
        if hasattr(self, "figure"):
            self.figure.canvas.draw_idle()

    def recompute_kmedoids_only(self):
        """
        Re-run k-medoids clustering only, using the same pooled vectors from the
        most recent full recompute_values() call , with the current self.kmedoids_k.
        Leaves fisher/kent/bingham results untouched.
        Does nothing if recompute_values has not yet run at least once.
        """
        if self._stats_dirty or not hasattr(self, "last_normals_array"):
            # Everything out of date: the full recompute also computes k-medoids with k.
            self.recompute_values()
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
        self.kmedoids_k = int(value)
        self.kmedoids_k_widget_action.sync(self.kmedoids_k)
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

        actor, pole = self._draw_pole(seed, axial=False, color="lime", marker="o", markersize=8)
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

        self._ensure_stats()

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
        self.kmedoids_k_widget_action.sync(k)
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

        key = "Normals" if kind == "normals" else "Lineations"
        for _, _, vtk_obj in self._shown_entities():
            lon, lat, vectors = self._entity_lonlat(vtk_obj, keys=(key,))
            if lon is None:
                continue
            projected_lons.append(lon)
            projected_lats.append(lat)
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

    # --- Selection highlight ---
    # Rings on at most this number of vectors per entity (entities drawn as contours can have
    # millions of vectors: a sample is enough to show that they are selected).
    HIGHLIGHT_MAX_POINTS_PER_ENTITY = 2000

    def on_selection_changed(self, collection):
        """Legacy selection signal: the highlight follows selection_modified (see
        selection_modified_update_actors). Statistics do not depend on the selection (they use the
        shown entities)."""

    def selection_modified_update_actors(self, added=None, removed=None, source=None):
        """The project selection changed: update the highlight (once per event loop iteration)."""
        self._schedule_highlight()

    def _schedule_highlight(self):
        if not self._highlight_pending:
            self._highlight_pending = True
            QTimer.singleShot(0, self._update_selection_highlight)

    def _update_selection_highlight(self):
        """Yellow rings on the poles / lineations of the selected entities that are shown in this
        view (one artist for all of them). Hidden entities are not highlighted (they stay
        selected), nor are entities while poles are hidden (Toggle poles)."""
        from numpy import linspace as np_linspace

        self._highlight_pending = False
        self._clear_selection_highlight(redraw=False)
        if not hasattr(self, "ax"):
            return
        selected = set(self.selected_uids)
        lons, lats, highlighted = [], [], set()
        if selected and self.show_poles:
            for uid, _, vtk_obj in self._shown_entities():
                if uid not in selected or self.mpl_actors.get(uid) is None:
                    continue
                lon, lat, _ = self._entity_lonlat(vtk_obj)
                if lon is None:
                    continue
                if lon.size > self.HIGHLIGHT_MAX_POINTS_PER_ENTITY:
                    sample = np_linspace(0, lon.size - 1, self.HIGHLIGHT_MAX_POINTS_PER_ENTITY).astype(int)
                    lon, lat = lon[sample], lat[sample]
                lons.append(lon)
                lats.append(lat)
                highlighted.add(uid)
        if lons:
            self.selection_highlight_actor = self.ax.plot(
                np_concatenate(lons),
                np_concatenate(lats),
                linestyle="none",
                marker="o",
                markersize=8,
                markerfacecolor="none",
                markeredgecolor="yellow",
                markeredgewidth=1.5,
                zorder=self.Z_STATS + 1,
            )[0]
            self.selection_highlight_uids = highlighted
        self.figure.canvas.draw_idle()

    # --- Orientation analysis: drawing and visibility ---
    def toggle_analysis_actor(self, key):
        """
        Show or hide one analysis visual (e.g. "bingham_major_pole") according to its checkbox in
        the Analysis menu (keys without a checkbox are toggled). The checkbox is never changed
        here: showing/hiding entities recomputes the statistics and redraws the checked visuals.
        """
        action = self.analysis_action_for_key.get(key)
        show = action.isChecked() if action is not None else self.analysis_actors.get(key) is None
        self._hide_analysis_actor(key)
        if show:
            self._ensure_stats()
            if self.analysis_actors.get(key) is not None:
                # _ensure_stats has just recomputed and redrawn the checked visuals quietly:
                # redraw this one printing its results.
                self._hide_analysis_actor(key)
            self._show_analysis_actor(key, verbose=True)

    def _show_analysis_actor(self, key, verbose=True):
        """
        Draw one analysis visual identified by key, reading whatever data it
        needs from self.analysis_results, and store the resulting artist(s)
        into self.analysis_actors. If the required data isn't available, the
        visual isn't drawn and the corresponding menu checkbox (if any) is
        not drawn (the checkbox stays checked: it is drawn again when data are
        available). verbose prints the results (when the user checks the box), not
        when the visuals are redrawn automatically.
        """
        say = self.print_terminal if verbose else (lambda *args, **kwargs: None)
        new_actor = None

        if key == "bingham_major_pole":
            new_actor = []
            for kind in ["normals", "lineations"]:
                bingham_result = self.analysis_results.get(kind, {}).get("bingham")
                if bingham_result is None:
                    say(f"No Bingham result available for {kind}.")
                    continue
                major_axis = bingham_result["axes"][0]
                marker = "s" if kind == "normals" else "o"
                actor, pole = self._draw_pole(major_axis, color="red", marker=marker, markersize=8)
                new_actor.append(actor)
                say(
                    f"Bingham major pole : {pole[0]:.2f}/{pole[1]:.2f}"
                )
            if not new_actor:
                new_actor = None

        elif key == "bingham_intermediate_pole":
            new_actor = []
            for kind in ["normals", "lineations"]:
                bingham_result = self.analysis_results.get(kind, {}).get("bingham")
                if bingham_result is None:
                    say(f"No Bingham result available for {kind}.")
                    continue
                intermediate_axis = bingham_result["axes"][1]
                marker = "s" if kind == "normals" else "o"
                actor, pole = self._draw_pole(intermediate_axis, color="green", marker=marker, markersize=8)
                new_actor.append(actor)
                say(f"Bingham intermediate pole : {pole[0]:.2f}/{pole[1]:.2f}")
            if not new_actor:
                new_actor = None

        elif key == "bingham_minor_pole":
            new_actor = []
            for kind in ["normals", "lineations"]:
                bingham_result = self.analysis_results.get(kind, {}).get("bingham")
                if bingham_result is None:
                    say(f"No Bingham result available for {kind}.")
                    continue
                minor_axis = bingham_result["axes"][2]
                marker = "s" if kind == "normals" else "o"
                actor, pole = self._draw_pole(minor_axis, color="blue", marker=marker, markersize=8)
                new_actor.append(actor)
                say(f"Bingham minor pole : {pole[0]:.2f}/{pole[1]:.2f}")
            if not new_actor:
                new_actor = None

        elif key == "bingham_minor_gc":
            new_actor = []
            for kind in ["normals", "lineations"]:
                bingham_result = self.analysis_results.get(kind, {}).get("bingham")
                if bingham_result is None:
                    say(f"No Bingham result available for {kind}.")
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
                    say(f"No clustering result available for {kind}.")
                    continue
                if kind == "normals":
                    say(self.KMEDOIDS_NORMALS_NOTE)
                say(f"Kmedoids centers :")
                for centroid in cluster_result["centroids"]:
                    norm = np_linalg_norm(centroid)
                    if norm == 0:
                        continue
                    unit_centroid = centroid / norm
                    actor, pole = self._draw_pole(
                        unit_centroid, axial=kind == "normals", color="black", marker="^", markersize=8
                    )
                    new_actor.append(actor)
                    say(f"   {pole[0]:.2f}/{pole[1]:.2f}")
            if not new_actor:
                new_actor = None

        elif key == "kmedoids_color":
            new_actor = []
            for kind in ["normals", "lineations"]:
                cluster_result = self.analysis_results.get(kind, {}).get("kmedoids")
                if cluster_result is None:
                    say(f"No clustering result available for {kind}.")
                    continue
                if kind == "normals":
                    say(self.KMEDOIDS_NORMALS_NOTE)
                df = (
                    self.last_normals_df
                    if kind == "normals"
                    else self.last_lineations_df
                )
                for (uid, cluster_id), group in df.groupby(["uid", "clusters"]):
                    vectors = group[["x", "y", "z"]].to_numpy()
                    palette = cm.get_cmap("tab10")
                    color = palette(cluster_id % 10)
                    # the data vectors, at the same positions as the entities
                    actor, pole = self._draw_pole(vectors, axial=False, color=color, markersize=6)
                    new_actor.append(actor)
            if not new_actor:
                new_actor = None

        elif key == "fisher_mean_pole":
            new_actor = []
            for kind in ["normals", "lineations"]:
                fisher_result = self.analysis_results.get(kind, {}).get("fisher")
                if fisher_result is None:
                    say(f"No fisher result available for {kind}.")
                    continue
                mean_direction = fisher_result["mean_direction"][0]
                marker = "s" if kind == "normals" else "o"
                actor, pole = self._draw_pole(
                    mean_direction, axial=kind == "normals", color="purple", marker=marker, markersize=8
                )
                new_actor.append(actor)
                say(f"Fisher pole and K : {pole[0]:.2f}/{pole[1]:.2f}, {fisher_result['kappa']:.2f}")
            if not new_actor:
                new_actor = None

        # elif key == "kent_mean_pole":
        #     new_actor = []
        #     for kind in ["normals", "lineations"]:
        #         kent_result = self.analysis_results.get(kind, {}).get("kent")
        #         if kent_result is None:
        #             say(f"No kent result available for {kind}.")
        #             continue
        #         mean_direction = kent_result["axes"][0]
        #         marker = "s" if kind == "normals" else "o"
        #         new_actor.append(self._draw_pole(mean_direction, color="lightsteelblue", marker=marker, markersize=10))
        #         say(f"Kent parameters : {kent_result["kappa"]}, {kent_result["beta"]}")
        #     if not new_actor:
        #         new_actor = None

        # elif key == "kent_mean_gc":
        #     new_actor = []
        #     for kind in ["normals", "lineations"]:
        #         kent_result = self.analysis_results.get(kind, {}).get("kent")
        #         if kent_result is None:
        #             say(f"No kent result available for {kind}.")
        #             continue
        #         mean_gc = kent_result["axes"][0]
        #         new_actor.append(self._draw_great_circle(mean_gc, color="lightsteelblue"))
        #         say(f"Kent parameters : {kent_result["kappa"]}, {kent_result["beta"]}")
        #     if not new_actor:
        #         new_actor = None

        else:
            self.print_terminal(f"Unknown analysis actor key: '{key}'")
            return

        if new_actor is not None:
            self.analysis_actors[key] = new_actor
            self.figure.canvas.draw_idle()

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

    def _draw_pole(self, vector, axial=True, **kwargs):
        """
        Plot one or more cartesian unit vectors (shape (3,) or (N, 3)) as points on self.ax, in a
        single call per hemisphere. Axial results (Bingham axes, normals) are folded to the lower
        hemisphere; directional ones (axial=False, e.g. the Fisher mean of lineations) keep their
        sign and are drawn hollow on the upper hemisphere when they point upwards, as entities.
        Returns (artist, pole) with pole = [trend, plunge] (or an N x 2 array), negative plunge for
        upward vectors.
        """
        from numpy import arcsin as np_arcsin
        from numpy import arctan2 as np_arctan2
        from numpy import clip as np_clip
        from numpy import degrees as np_degrees

        single = np_asarray(vector).ndim == 1
        vectors = np_asarray(vector, dtype=float).reshape(-1, 3)
        vectors = vectors / np_linalg_norm(vectors, axis=1)[:, None]
        if axial:
            vectors[vectors[:, 2] > 0] *= -1
        lon, lat, upward = self._vectors_to_lonlat(vectors)
        kwargs.setdefault("zorder", self.Z_STATS)
        kwargs.setdefault("marker", "o")
        color = kwargs.pop("color", None)
        artists = []
        for mask, face in ((~upward, color), (upward, "none")):
            if mask.any():
                artists.append(
                    self.ax.plot(
                        lon[mask], lat[mask], linestyle="none", color=color,
                        markerfacecolor=face, **kwargs,
                    )[0]
                )
        actor = artists[0] if len(artists) == 1 else StereoActor(artists)
        trend = np_degrees(np_arctan2(vectors[:, 0], vectors[:, 1])) % 360
        plunge = np_degrees(np_arcsin(np_clip(-vectors[:, 2], -1.0, 1.0)))
        pole = [trend[0], plunge[0]] if single else np_vstack([trend, plunge]).T
        return actor, pole

    def _draw_great_circle(self, vector, **kwargs):
        """
        Plot the planes whose poles are the given cartesian unit vectors (shape (3,) or (N, 3)) as
        great circles on self.ax, in a single matplotlib call. Returns the matplotlib artist.
        """
        vectors = np_asarray(vector, dtype=float).reshape(-1, 3).copy()
        vectors[vectors[:, 2] > 0] *= -1  # a plane is the same for both its normals
        kwargs.setdefault("zorder", self.Z_STATS)
        plunge, bearing = mplstereonet.vector2plunge_bearing(
            vectors[:, 0], vectors[:, 1], vectors[:, 2]
        )
        strike, dip = mplstereonet.plunge_bearing2pole(plunge, bearing)
        return self.ax.plane(strike, dip, **kwargs)[0]

    # --- Clusters saving: saving the clusters as property ---
    def save_clusters_as_property(self, property_name):
        """
        Write the most recently computed k-medoids cluster assignment (currently
        cached in self.last_normals_df / self.last_lineations_df) onto each
        contributing entity (any collection), as a new 1-component point-data
        property named property_name. Points without a valid vector get NaN.
        """
        from numpy import full as np_full
        from numpy import nan as np_nan
        from pzero.helpers.helper_functions import entity_collection

        self._ensure_stats()
        for df, kind in [
            (getattr(self, "last_normals_df", None), "Normals"),
            (getattr(self, "last_lineations_df", None), "Lineations"),
        ]:
            if df is None or "clusters" not in df.columns:
                continue
            if df["clusters"].isnull().all():
                continue

            for uid, group in df.groupby("uid"):
                collection = entity_collection(self, uid)
                vtk_obj = collection.get_uid_vtk_obj(uid) if collection is not None else None
                _, valid = self._entity_vectors(vtk_obj, kind)
                if vtk_obj is None or valid is None or valid.sum() != len(group):
                    self.print_terminal(
                        f"uid {uid}: not found or changed, skipped while saving clusters."
                    )
                    continue
                cluster_values = np_full((vtk_obj.points_number, 1), np_nan)
                cluster_values[valid, 0] = group["clusters"].to_numpy(dtype=float)
                if property_name not in collection.get_uid_properties_names(uid):
                    collection.append_uid_property(
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

    def toggle_selection_tool(self):
        """Select > By polygon: draw a region on the stereoplot (click and drag) to select the
        entities with poles inside it. One selection per command (the tool then deactivates)."""
        if self.selection_tool_active:
            return
        self.selection_tool_active = True
        self.selection_press_cid = self.canvas.mpl_connect(
            "button_press_event", self._on_selection_press
        )
        self.selection_motion_cid = self.canvas.mpl_connect(
            "motion_notify_event", self._on_selection_motion
        )
        self.selection_release_cid = self.canvas.mpl_connect(
            "button_release_event", self._on_selection_release
        )
        self.print_terminal("Select by polygon: click and drag on the stereoplot.")

    def _deactivate_selection(self, clear_highlight=True):
        """Disconnect selection events and clean up visual state."""
        for cid in [
            self.selection_press_cid,
            self.selection_motion_cid,
            self.selection_release_cid,
        ]:
            if cid is not None:
                self.canvas.mpl_disconnect(cid)
        self.selection_press_cid = None
        self.selection_motion_cid = None
        self.selection_release_cid = None
        self.selection_start = None
        self._remove_selection_patch()
        # (clear_highlight is kept for compatibility: the highlight follows the selection)
        self.selection_tool_active = False
        if hasattr(self, "figure"):
            self.figure.canvas.draw()

    def _remove_selection_patch(self):
        """Remove the drawn selection region from the axes."""
        if self.selection_patch is not None:
            try:
                self.selection_patch.remove()
            except Exception:
                pass
            self.selection_patch = None

    def _clear_selection_highlight(self, *args, redraw=True):
        """Remove the yellow selection rings (they are drawn again by _update_selection_highlight)."""
        if self.selection_highlight_actor is not None:
            try:
                self.selection_highlight_actor.remove()
            except Exception:
                pass  # it belonged to a figure that has been replaced
            self.selection_highlight_actor = None
            self.selection_highlight_uids = set()
            if redraw and hasattr(self, "figure"):
                self.figure.canvas.draw_idle()

    def _build_selection_path(self, lon0, lat0, lon1, lat1, n=50):
        """
        Build the boundary path of a stereonet region between two corners
        (lon0, lat0) and (lon1, lat1) in data coordinates. The boundary
        consists of:
        - top arc:   lat = lat0, lon from lon0 to lon1
        - right edge: lon = lon1, lat from lat0 to lat1
        - bottom arc: lat = lat1, lon from lon1 to lon0
        - left edge:  lon = lon0, lat from lat1 to lat0
        Returns an (M, 2) array of (x, y) vertices for use with Polygon.
        """
        from numpy import linspace as np_linspace

        if abs(lon1 - lon0) > np_pi:
            if lon0 < lon1:
                lon0 += 2 * np_pi
            else:
                lon1 += 2 * np_pi

        top = np_asarray([[l, lat0] for l in np_linspace(lon0, lon1, n)])
        right = np_asarray([[lon1, l] for l in np_linspace(lat0, lat1, n)])
        bottom = np_asarray([[l, lat1] for l in np_linspace(lon1, lon0, n)])
        left = np_asarray([[lon0, l] for l in np_linspace(lat1, lat0, n)])

        return np_vstack([top, right, bottom, left])

    def _on_selection_press(self, event):
        if event.button != 1:
            return
        if event.xdata is None or event.ydata is None:
            return
        self.selection_start = self._event_to_screen_polar(event)
        self._remove_selection_patch()

    def _on_selection_motion(self, event):
        if self.selection_start is None:
            return
        if event.xdata is None or event.ydata is None:
            return

        theta0, r0 = self.selection_start
        theta1, r1 = self._event_to_screen_polar(event)

        theta0 = theta0 % (2 * np_pi)
        theta1 = theta1 % (2 * np_pi)
        if abs(theta1 - theta0) > np_pi:
            if theta0 < theta1:
                theta0 += 2 * np_pi
            else:
                theta1 += 2 * np_pi
        theta_min, theta_max = min(theta0, theta1), max(theta0, theta1)
        r_min, r_max = min(r0, r1), max(r0, r1)

        self._remove_selection_patch()

        from numpy import linspace as np_linspace

        top_theta = np_linspace(theta_min, theta_max, 50)
        right_r = np_linspace(r_min, r_max, 50)
        bottom_theta = np_linspace(theta_max, theta_min, 50)
        left_r = np_linspace(r_max, r_min, 50)
        theta = np_concatenate(
            [
                top_theta,
                theta_max * np_asarray([1.0] * 50),
                bottom_theta,
                theta_min * np_asarray([1.0] * 50),
            ]
        )
        radius = np_concatenate(
            [
                r_min * np_asarray([1.0] * 50),
                right_r,
                r_max * np_asarray([1.0] * 50),
                left_r,
            ]
        )

        cx, cy = self.ax.transAxes.transform((0.5, 0.5))
        x0, y0 = self.ax.transAxes.transform((0.0, 0.0))
        x1, y1 = self.ax.transAxes.transform((1.0, 1.0))
        radius_px = min(abs(x1 - x0), abs(y1 - y0)) / 2.0
        display_xy = np_asarray(
            [
                cx + radius * radius_px * np_sin(theta),
                cy + radius * radius_px * np_cos(theta),
            ]
        ).T
        verts_data = self.ax.transData.inverted().transform(display_xy)

        self.selection_patch = self.ax.fill(
            verts_data[:, 0],
            verts_data[:, 1],
            facecolor="lightblue",
            edgecolor="blue",
            linewidth=1.5,
            linestyle="--",
            alpha=0.3,
            zorder=self.Z_STATS + 2,
        )[0]

        self.figure.canvas.draw()

    def _on_selection_release(self, event):
        if self.selection_start is None:
            return
        if event.xdata is None or event.ydata is None:
            self._remove_selection_patch()
            self.selection_start = None
            self.figure.canvas.draw()
            return

        theta0, radius0 = self.selection_start
        theta1, radius1 = self._event_to_screen_polar(event)
        self.selection_start = None

        # Build the path for containment testing
        # from matplotlib.path import Path as mpl_Path
        # verts = self._build_selection_path(theta0, radius0, theta1, radius1)
        # polygon = mpl_Path(verts)

        # Project all visible entity poles and test containment
        uid_lons = {}
        uid_lats = {}

        for _, row in self.actors_df.iterrows():
            uid = row["uid"]
            if not row["show"]:
                continue
            collection = getattr(self.parent, row["collection"], None)
            vtk_obj = collection.get_uid_vtk_obj(uid) if collection is not None else None
            lon, lat, _ = self._entity_lonlat(vtk_obj)
            if lon is None:
                continue
            uid_lons[uid] = lon
            uid_lats[uid] = lat

        selected_uids = []
        for uid in uid_lons:
            points_lonlat = np_asarray(list(zip(uid_lons[uid], uid_lats[uid])))

            points_px = self.ax.transData.transform(points_lonlat)
            cx, cy = self.ax.transAxes.transform((0.5, 0.5))
            x0, y0 = self.ax.transAxes.transform((0.0, 0.0))
            x1, y1 = self.ax.transAxes.transform((1.0, 1.0))
            radius_px = min(abs(x1 - x0), abs(y1 - y0)) / 2.0

            dx = points_px[:, 0] - cx
            dy = points_px[:, 1] - cy
            from numpy import arctan2 as np_arctan2
            from numpy import hypot as np_hypot

            theta = np_arctan2(dx, dy) % (2 * np_pi)
            radius = np_hypot(dx, dy) / radius_px

            theta0 = theta0 % (2 * np_pi)
            theta1 = theta1 % (2 * np_pi)
            if abs(theta1 - theta0) > np_pi:
                if theta0 < theta1:
                    theta0 += 2 * np_pi
                else:
                    theta1 += 2 * np_pi

            theta_min = min(theta0, theta1)
            theta_max = max(theta0, theta1)
            if theta_max > 2 * np_pi:
                theta = np_where(theta < theta_min, theta + 2 * np_pi, theta)
            radius_min = min(radius0, radius1)
            radius_max = max(radius0, radius1)

            inside = (
                (theta >= theta_min)
                & (theta <= theta_max)
                & (radius >= radius_min)
                & (radius <= radius_max)
            )

            if inside.any():
                selected_uids.append(uid)

        self._remove_selection_patch()

        if not selected_uids:
            self.print_terminal("No entities found inside the selection region.")
            self._deactivate_selection()
            return

        self.print_terminal(
            f"Selected {len(selected_uids)} entity/entities via region selection."
        )

        # Within this view, the entities inside the region become the selection; entities that are
        # not in this view keep their selection state (any collection).
        selected_set = set(selected_uids)
        outside = [uid for uid in self.selected_uids if uid not in selected_set]
        if outside:
            self.parent.set_selection(uids=outside, mode="remove", source=self)
        self.parent.set_selection(uids=selected_uids, mode="add", source=self)
        self._deactivate_selection(clear_highlight=False)

    def _event_to_screen_polar(self, event):
        cx, cy = self.ax.transAxes.transform((0.5, 0.5))
        x0, y0 = self.ax.transAxes.transform((0.0, 0.0))
        x1, y1 = self.ax.transAxes.transform((1.0, 1.0))

        radius_px = min(abs(x1 - x0), abs(y1 - y0)) / 2.0

        dx = event.x - cx
        dy = event.y - cy

        from numpy import arctan2 as np_arctan2
        from numpy import hypot as np_hypot

        theta = np_arctan2(dx, dy)  # 0 at north, clockwise-ish
        r = np_hypot(dx, dy) / radius_px

        return theta, r

    # --- Statistics summary functions ---
    def build_statistics_summary(self):
        """
        Build a human-readable statistics summary string from the most recently
        computed self.analysis_results. Covers Fisher, Bingham, and K-medoids
        for both Normals and Lineations. Returns an empty string if no results
        are available.

        Returns
        -------
        str
            Formatted multi-line summary ready for printing or file export.
        """
        if not self.analysis_results:
            return ""

        lines = []
        lines.append("=" * 60)
        lines.append("PZero Stereoplot — Orientation Statistics Summary")
        lines.append("=" * 60)

        # Number of data points used
        if hasattr(self, "last_normals_array") and self.last_normals_array is not None:
            lines.append(f"Normals:    {self.last_normals_array.shape[0]} points")
        if (
            hasattr(self, "last_lineations_array")
            and self.last_lineations_array is not None
        ):
            lines.append(f"Lineations: {self.last_lineations_array.shape[0]} points")
        lines.append("")

        for kind in ["normals", "lineations"]:
            kind_results = self.analysis_results.get(kind, {})
            if not kind_results:
                continue

            # Check if there is actually any non-None result to report
            if all(v is None for v in kind_results.values()):
                continue

            lines.append("-" * 60)
            lines.append(f"{kind.capitalize()} statistics")
            lines.append("-" * 60)

            # ---- Fisher ----
            fisher = kind_results.get("fisher")
            if fisher is not None:
                lines.append("")
                lines.append("Fisher distribution")
                mean = fisher["mean_direction"][0]
                kappa = fisher["kappa"]
                # Convert mean direction vector to plunge/bearing for readability
                plunge, bearing = mplstereonet.vector2plunge_bearing(
                    mean[0], mean[1], mean[2]
                )
                plunge = float(np_atleast_1d(plunge)[0])
                bearing = float(np_atleast_1d(bearing)[0]) % 360
                lines.append(
                    f"  Mean direction: bearing {bearing:.1f}°, plunge {plunge:.1f}°"
                )
                lines.append(f"  Concentration (kappa): {kappa:.4f}")

            # ---- Bingham ----
            bingham_result = kind_results.get("bingham")
            if bingham_result is not None:
                lines.append("")
                lines.append("Bingham distribution")
                eigenvalues = bingham_result["eigenvalues"]
                axes = bingham_result["axes"]

                axis_labels = [
                    "Major axis (e1)",
                    "Intermediate axis (e2)",
                    "Minor axis (e3)",
                ]
                for i, (label, axis, eigval) in enumerate(
                    zip(axis_labels, axes, eigenvalues)
                ):
                    plunge, bearing = mplstereonet.vector2plunge_bearing(
                        axis[0], axis[1], axis[2]
                    )
                    plunge = float(np_atleast_1d(plunge)[0])
                    bearing = float(np_atleast_1d(bearing)[0]) % 360
                    lines.append(
                        f"  {label}: bearing {bearing:.1f}°, plunge {plunge:.1f}°"
                        f"  (eigenvalue: {eigval:.4f})"
                    )

                # Fabric interpretation from eigenvalue ratios
                e1, e2, e3 = eigenvalues
                if e1 > 0 and e3 > 0:
                    lines.append(
                        f"  Eigenvalue ratios — e1/e3: {e1/e3:.2f},  e2/e3: {e2/e3:.2f}"
                    )
                    if e1 / e3 > 5 and (e1 - e2) < (e2 - e3):
                        lines.append("  Fabric interpretation: cluster (point maximum)")
                    elif e1 / e3 > 5 and (e1 - e2) > (e2 - e3):
                        lines.append(
                            "  Fabric interpretation: girdle (great circle distribution)"
                        )
                    else:
                        lines.append(
                            "  Fabric interpretation: intermediate / scattered"
                        )

            # ---- K-medoids ----
            kmeans = kind_results.get("kmeans")
            if kmeans is not None:
                labels = kmeans["labels"]
                centroids = kmeans["centroids"]
                k = centroids.shape[0]
                unique_labels = sorted(set(int(l) for l in labels))
                lines.append("")
                lines.append(f"K-medoids clustering  (k = {k})")
                for cluster_id in unique_labels:
                    count = int((labels == cluster_id).sum())
                    centroid = centroids[cluster_id]
                    norm = float(np_linalg_norm(centroid))
                    if norm > 0:
                        unit_centroid = centroid / norm
                        plunge, bearing = mplstereonet.vector2plunge_bearing(
                            unit_centroid[0], unit_centroid[1], unit_centroid[2]
                        )
                        plunge = float(np_atleast_1d(plunge)[0])
                        bearing = float(np_atleast_1d(bearing)[0]) % 360
                        lines.append(
                            f"  Cluster {cluster_id}: {count} points — "
                            f"medoid bearing {bearing:.1f}°, plunge {plunge:.1f}°"
                        )
                    else:
                        lines.append(
                            f"  Cluster {cluster_id}: {count} points — degenerate medoid"
                        )

            lines.append("")

        lines.append("=" * 60)
        return "\n".join(lines)

    def export_statistics_summary(self):
        """
        Build the statistics summary and offer the user a choice:
        print to the PZero terminal, save to a text file, or both.
        Uses multiple_input_dialog for the file path, consistent with the
        rest of the codebase. If no results exist yet, prints a message
        and returns.
        """
        self._ensure_stats()
        summary = self.build_statistics_summary()

        if not summary:
            self.print_terminal("No statistics: no shown entity with Normals or Lineations.")
            return

        # Print to terminal always
        self.print_terminal(summary)

        # Ask user if they also want to save to file
        input_dict = {"save_to_file": ["Save to file? (leave empty to skip): ", ""]}
        result = multiple_input_dialog(
            title="Export statistics summary", input_dict=input_dict
        )
        if result is None:
            return  # user cancelled

        filepath = result["save_to_file"].strip()
        if not filepath:
            return  # user left it blank — terminal-only was enough

        # Add .txt extension if the user didn't
        if not filepath.endswith(".txt"):
            filepath += ".txt"

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(summary)
                f.write("\n")
            self.print_terminal(f"Statistics saved to: {filepath}")
        except OSError as e:
            self.print_terminal(f"Could not save statistics file: {e}")
