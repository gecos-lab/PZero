"""abstract_base_view.py
PZero© Andrea Bistacchi"""

# PySide6 imports____
from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import QMainWindow
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtCore import Signal as pyqtSignal

# Pandas imports____
from pandas import DataFrame as pd_DataFrame
from pandas import concat as pd_concat

# PZero imports____
from .view_tree import CustomTreeWidget
from ..collections.AbstractCollection import BaseCollection
from ..ui.base_view_window_ui import Ui_BaseViewWindow
from ..helpers.helper_dialogs import progress_dialog


class BaseViewSignals(QObject):
    """
    This class is necessary since non-Qt classes cannot emit Qt signals. Therefore, we create a generic
    BaseViewSignals() Qt object that will include all signals used by collections. These will be used according
    to the following pattern:

    self.signals = BaseViewSignals()
    self.signals.specific_signal.emit(some_message)

    Basically, in this way, instead of using inheritance, we add all signals with a quick move by composition.
    """

    # signal broadcast on checkbox toggled, with the collection and lists of uids to be turned on or off as arguments
    # # Create signal ===================================================================================================
    # checkboxToggled = pyqtSignal(str, list, list)
    # signal broadcast on property combobox changed, with the collection, uid and property as arguments
    # # Create signal ===================================================================================================
    # propertyToggled = pyqtSignal(str, str, str)


class BaseView(QMainWindow, Ui_BaseViewWindow):
    """
    Create base view - abstract class providing common methods for all views. This includes all side tree and list
    views, but not the main plotting canvas, that must be managed by subclasses.
    parent is the QT object that is launching this one, hence the ProjectWindow() instance.
    """

    def __init__(self, parent=None, *args, **kwargs):
        super(BaseView, self).__init__(parent, *args, **kwargs)
        self.setupUi(self)
        # Qt.WA_DeleteOnClose DELETES ANY REFERENCE TO CLOSED WINDOWS, HENCE FREEING
        # MEMORY, BUT COULD CREATE PROBLEMS WITH SIGNALS THAT ARE STILL ACTIVE
        # SEE DISCUSSIONS ON QPointer AND WA_DeleteOnClose ON THE INTERNET
        # For this we collect all signals and particularly connections to functions and
        # delete them before closing the view.
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        # Ensure the window acts as a widget so it can be properly embedded in a DockWidget
        # without fighting for top-level window status.
        self.setWindowFlags(Qt.Widget)
        self.parent = parent
        self.signals = BaseViewSignals()
        self.print_terminal = self.parent.print_terminal
        self.tree_collection_dict = {
            "GeologyTreeWidget": "geol_coll",
            "FluidsTreeWidget": "fluid_coll",
            "BackgroundsTreeWidget": "backgrnd_coll",
            "DOMsTreeWidget": "dom_coll",
            "ImagesTreeWidget": "image_coll",
            "Mesh3DTreeWidget": "mesh3d_coll",
            "BoundariesTreeWidget": "boundary_coll",
            "XSectionTreeWidget": "xsect_coll",
            "WellsTreeWidget": "well_coll",
        }
        self.collection_tree_dict = dict(
            zip(self.tree_collection_dict.values(), self.tree_collection_dict.keys())
        )
        self.actors_df = pd_DataFrame(
            {
                "uid": str,
                "actor": str,
                "show": bool,
                "collection": str,
                "show_property": str,
            },
            index=[],
        )
        # The selection is stored at project level, see the selected_uids property below.
        # Set view_filter attribute to a string indicating that all entities must be selected (i.e. no filtering).
        # Somebody says 'ilevel_0 in ilevel_0' is more robust than 'index == index', but it seems OK.
        if not hasattr(self, "view_filter"):
            self.view_filter = "index == index"
            self.this_x_section_uid = []
        # Initialize menus and tools, canvas, add actors and show it. These methods must be defined in subclasses.
        self.initialize_menu_tools()
        self.initialize_interactor()
        self.add_all_entities()
        self.create_trees()
        self.connect_all_signals()
        # Show what is already selected in the project.
        self.selection_modified_update_actors(
            added=self.parent.selection_uids(), removed=[], source=None
        )
        self._install_selection_shortcuts()

    # ================================  General methods shared by all views ===========================================

    @property
    def selected_uids(self) -> list:
        """UIDs selected in the project (see ProjectWindow.set_selection) that are shown in this
        view, in pick order. Read-only: change the selection with self.parent.set_selection()."""
        view_uids = set(self.actors_df["uid"])
        return [uid for uid in self.parent.selection_uids() if uid in view_uids]

    def connect_all_signals(self):
        """
        Connect signals to update functions. Use lambda functions where we need to pass additional
        arguments such as parent in addition to the signal itself, e.g. the updated_list
        Note that it could be possible to connect the (lambda) functions directly, without naming them, as in:
        self.signals.checkboxToggled.connect(
            lambda collection_name, turn_on_uids, turn_off_uids: self.toggle_visibility(
                collection_name, turn_on_uids, turn_off_uids
            )
        )
        But in this way it would be impossible to disconnect them in a clean way in disconnect_all_signals, so
        we name every lambda function explicitly as follows.

        It is IMPORTANT to check that all signals connected here are in the list of signals to be disconnected.
        """
        self._signals_disconnected = False
        # prop_legend_cmap_modified ---
        self.prop_legend_lambda = (
            lambda this_property: self.prop_legend_cmap_modified_update_views(
                this_property=this_property
            )
        )
        self.parent.signals.prop_legend_cmap_modified.connect(self.prop_legend_lambda)

        # entities_added ---
        self.sig_add_lmb = lambda upd_uids, coll: self._queue_entity_update(
            "added", upd_uids, coll
        )
        self.parent.signals.entities_added.connect(self.sig_add_lmb)

        # entities_removed ---
        self.sig_rem_lmb = lambda upd_uids, coll: self._queue_entity_update(
            "removed", upd_uids, coll
        )
        self.parent.signals.entities_removed.connect(self.sig_rem_lmb)

        # geom_modified ---
        self.sig_geom_lmb = lambda upd_uids, coll: self._queue_entity_update(
            "geom_modified", upd_uids, coll
        )
        self.parent.signals.geom_modified.connect(self.sig_geom_lmb)

        # data_keys_added ---
        self.sig_k_add_lmb = lambda upd_uids, coll: self._queue_entity_update(
            "data_keys_added", upd_uids, coll
        )
        self.parent.signals.data_keys_added.connect(self.sig_k_add_lmb)

        # data_keys_removed ---
        self.sig_k_rmv_lmb = lambda upd_uids, coll: self._queue_entity_update(
            "data_keys_removed", upd_uids, coll
        )
        self.parent.signals.data_keys_removed.connect(self.sig_k_rmv_lmb)

        # data_val_modified ---
        self.sig_val_lmb = lambda upd_uids, coll: self._queue_entity_update(
            "data_val_modified", upd_uids, coll
        )
        self.parent.signals.data_val_modified.connect(self.sig_val_lmb)

        # metadata_modified ---
        self.sig_meta_lmb = lambda upd_uids, coll: self._queue_entity_update(
            "metadata_modified", upd_uids, coll
        )
        self.parent.signals.metadata_modified.connect(self.sig_meta_lmb)

        # legend_color_modified ---
        self.sig_clr_lmb = lambda upd_uids, coll: self._queue_entity_update(
            "legend_color", upd_uids, coll
        )
        self.parent.signals.legend_color_modified.connect(self.sig_clr_lmb)

        # legend_thick_modified ---
        self.sig_thk_lmb = lambda upd_uids, coll: self._queue_entity_update(
            "legend_thick", upd_uids, coll
        )
        self.parent.signals.legend_thick_modified.connect(self.sig_thk_lmb)

        # legend_point_size_modified ---
        self.sig_pnt_lmb = lambda upd_uids, coll: self._queue_entity_update(
            "legend_point_size", upd_uids, coll
        )
        self.parent.signals.legend_point_size_modified.connect(self.sig_pnt_lmb)

        # legend_opacity_modified ---
        self.sig_opct_lmb = lambda upd_uids, coll: self._queue_entity_update(
            "legend_opacity", upd_uids, coll
        )
        self.parent.signals.legend_opacity_modified.connect(self.sig_opct_lmb)

        # selection_modified --- trees and graphics of this view mirror the project selection store
        self.sig_sel_lmb = lambda added, removed, colls, source: (
            self.selection_modified_update_trees(collections=colls, source=source),
            self.selection_modified_update_actors(
                added=added, removed=removed, source=source
            ),
        )
        self.parent.signals.selection_modified.connect(self.sig_sel_lmb)

    def showEvent(self, event):
        """The first time the view is shown, split it 3:1 between graphics and side panel (trees).
        The splitter would otherwise share the width according to the size hints of the canvases,
        which differ (e.g. the matplotlib canvas of the stereoplot asks for very little width, so its
        side panel was much wider than in VTK views). The 3:1 split is kept when the view is resized
        (e.g. a view opened as a new tab is shown before its dock has its final width) until the
        user moves the divider."""
        super().showEvent(event)
        if not getattr(self, "_initial_split_done", False):
            self._initial_split_done = True
            splitter = getattr(self, "splitter", None)
            if splitter is not None:
                self._user_moved_split = False
                splitter.splitterMoved.connect(self._on_split_moved_by_user)
                splitter.installEventFilter(self)
            QTimer.singleShot(0, self._apply_initial_split)

    def _on_split_moved_by_user(self, *args):
        """The user moved the divider: keep their split from now on."""
        self._user_moved_split = True

    def eventFilter(self, watched, event):
        if (
            event.type() == QEvent.Resize
            and watched is getattr(self, "splitter", None)
            and not getattr(self, "_user_moved_split", True)
        ):
            QTimer.singleShot(0, self._apply_initial_split)
        return super().eventFilter(watched, event)

    def _apply_initial_split(self):
        splitter = getattr(self, "splitter", None)
        if splitter is None or getattr(self, "_user_moved_split", False):
            return
        total = sum(splitter.sizes()) or splitter.width()
        if total > 0:
            graphics = total * 3 // 4
            if splitter.sizes() != [graphics, total - graphics]:
                splitter.setSizes([graphics, total - graphics])

    def _install_selection_shortcuts(self):
        """Ctrl+A selects all the entities shown in this view, Ctrl+Shift+A deselects all the entities
        of this view (Cmd instead of Ctrl on macOS). Active when the focus is in the graphics frame,
        so that Ctrl+A in the trees of the view keeps selecting the tree items."""
        frame = getattr(self, "ViewFrame", None) or self
        self._selection_shortcuts = []
        for keys, slot in (
            ("Ctrl+A", self.select_all_in_view),
            ("Ctrl+Shift+A", self.deselect_all_in_view),
        ):
            shortcut = QShortcut(QKeySequence(keys), frame)
            shortcut.setContext(Qt.WidgetWithChildrenShortcut)
            shortcut.activated.connect(slot)
            self._selection_shortcuts.append(shortcut)

    def select_all_in_view(self):
        """Ctrl+A in the graphics: within this view, the entities shown (checked) become selected and
        the hidden ones are deselected; entities that are not in this view keep their selection state.
        (Hiding an entity does not deselect it: only this command does.)"""
        if self.parent.selection_frozen:
            return
        self.flush_pending_updates()  # act on the current content of the view
        shown = list(self.shown_uids)
        shown_set = set(shown)
        hidden_selected = [uid for uid in self.selected_uids if uid not in shown_set]
        if hidden_selected:
            self.parent.set_selection(uids=hidden_selected, mode="remove", source=self)
        if shown:
            self.parent.set_selection(uids=shown, mode="add", source=self)

    def deselect_all_in_view(self):
        """Remove all the entities of this view from the project selection."""
        if self.parent.selection_frozen:
            return
        self.flush_pending_updates()  # act on the current content of the view
        uids = self.selected_uids
        if uids:
            self.parent.set_selection(uids=uids, mode="remove", source=self)

    # Entity signals (added, removed, geometry, properties, metadata, legend) are not processed
    # one by one: they are queued, merged per kind and collection, and processed once at the next
    # event loop iteration, after pending legend rebuilds and before the selection highlight. An
    # operation on many entities then updates each view once per kind instead of once per entity.
    # Kinds are processed in a fixed order: removed before added (an entity removed and added
    # again in the same pass ends up present; one added and removed is skipped since it no longer
    # exists), then the other kinds, skipping entities just added (their actors are already new).

    _ENTITY_UPDATE_HANDLERS = {
        "removed": "entities_removed_update_views",  # processed first (see above)
        "added": "entities_added_update_views",
        "geom_modified": "entities_geom_modified_update_views",
        "data_keys_added": "entities_data_keys_added_update_views",
        "data_keys_removed": "entities_data_keys_removed_update_views",
        "data_val_modified": "entities_data_val_modified_update_views",
        "metadata_modified": "entities_metadata_modified_update_views",
        "legend_color": "change_actor_color",
        "legend_thick": "change_actor_line_thick",
        "legend_point_size": "change_actor_point_size",
        "legend_opacity": "change_actor_opacity",
    }

    def _queue_entity_update(self, kind=None, uids=None, collection=None):
        """Queue an entity update, merged with the other updates of the same kind and collection."""
        if isinstance(uids, str):
            uids = [uids]
        queue = self.__dict__.setdefault("_entity_update_queue", {})
        merged = queue.setdefault((kind, id(collection)), (collection, {}))[1]
        for uid in uids or []:
            merged[uid] = None  # ordered set
        self._schedule_deferred()

    def _schedule_deferred(self):
        """Run _run_deferred once at the next event loop iteration."""
        timer = self.__dict__.get("_deferred_timer")
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.setInterval(0)
            timer.timeout.connect(self._run_deferred)
            self._deferred_timer = timer
        if not timer.isActive():
            timer.start()

    def flush_pending_updates(self):
        """Process queued updates now (e.g. before reading the view state in the same operation)."""
        timer = self.__dict__.get("_deferred_timer")
        if timer is not None:
            timer.stop()
        self._run_deferred()

    def _run_deferred(self):
        """Pending legend rebuilds, then queued entity updates in order, then the highlight."""
        if getattr(self, "_signals_disconnected", False):
            self._entity_update_queue = {}
            return
        flush_legends = getattr(self.parent, "flush_legend_updates", None)
        if flush_legends is not None:
            flush_legends()
        queue = self.__dict__.get("_entity_update_queue", {})
        self._entity_update_queue = {}
        just_added = {}
        for kind in self._ENTITY_UPDATE_HANDLERS:  # fixed processing order
            for (queued_kind, _), (collection, merged) in list(queue.items()):
                if queued_kind != kind:
                    continue
                uids = list(merged)
                if kind != "removed":
                    # Entities may have been removed after the update was queued.
                    existing = set(collection.df["uid"]) if "uid" in collection.df.columns else set()
                    uids = [uid for uid in uids if uid in existing]
                if kind not in ("removed", "added"):
                    fresh = just_added.get(id(collection), set())
                    uids = [uid for uid in uids if uid not in fresh]
                if not uids:
                    continue
                if kind == "added":
                    just_added.setdefault(id(collection), set()).update(uids)
                try:
                    getattr(self, self._ENTITY_UPDATE_HANDLERS[kind])(
                        updated_uids=uids, collection=collection
                    )
                except Exception:
                    import traceback

                    traceback.print_exc()
        self._apply_pending_highlight()

    def _apply_pending_highlight(self):
        """Apply queued selection highlight changes. Implemented in subclasses."""
        pass

    def selection_modified_update_actors(self, added=None, removed=None, source=None):
        """Update the highlight of selected entities in the graphics. To be implemented in
        subclasses (ViewVTK, and ViewMPL-based views)."""
        pass

    def selection_modified_update_trees(self, collections=None, source=None):
        """Re-apply the project selection to the trees of the collections whose selection
        changed, except the tree that made the change (it already mirrors the store)."""
        for collection_name in collections or []:
            tree = getattr(self, self.collection_tree_dict.get(collection_name, ""), None)
            if (
                tree is not None
                and tree is not source
                and hasattr(tree, "set_selection_from_collection")
            ):
                tree.set_selection_from_collection()

    def disconnect_all_signals(self):
        """Disconnect each subscription independently before a view is deleted."""
        if getattr(self, "_signals_disconnected", False):
            return
        self._signals_disconnected = True
        if hasattr(self, "_cancel_pending_horizon_scan"):
            self._cancel_pending_horizon_scan()
        subscriptions = (
            ("prop_legend_cmap_modified", "prop_legend_lambda"),
            ("entities_added", "sig_add_lmb"),
            ("entities_removed", "sig_rem_lmb"),
            ("geom_modified", "sig_geom_lmb"),
            ("data_keys_added", "sig_k_add_lmb"),
            ("data_keys_removed", "sig_k_rmv_lmb"),
            ("data_val_modified", "sig_val_lmb"),
            ("metadata_modified", "sig_meta_lmb"),
            ("legend_color_modified", "sig_clr_lmb"),
            ("legend_thick_modified", "sig_thk_lmb"),
            ("legend_point_size_modified", "sig_pnt_lmb"),
            ("legend_opacity_modified", "sig_opct_lmb"),
            ("selection_modified", "sig_sel_lmb"),
            ("prop_legend_cmap_modified", "update_slices_for_property_change"),
            ("entities_added", "on_entities_added"),
            ("entities_removed", "on_entities_removed"),
            ("prop_legend_cmap_modified", "on_colormap_changed"),
            ("legend_color_modified", "on_geology_legend_style_changed"),
            ("legend_thick_modified", "on_geology_legend_style_changed"),
            ("legend_opacity_modified", "on_geology_legend_style_changed"),
        )
        for signal_name, slot_name in subscriptions:
            slot = getattr(self, slot_name, None)
            signal = getattr(self.parent.signals, signal_name, None)
            if signal is not None and slot is not None:
                try:
                    signal.disconnect(slot)
                except (RuntimeError, TypeError):
                    # A prior close or partial initialization may have already
                    # disconnected this slot; still clean up the remaining ones.
                    pass

    def disable_actions(self):
        """Freeze all actions while doing something."""
        # self.parent.findChildren(QAction) returns a list of all actions in the application.
        print("- disabling actions in ", self.windowTitle())
        for action in self.parent.findChildren(QAction):
            # try - except added to catch an inexplicable bug with an action with text=""
            try:
                action.setDisabled(True)
            except:
                pass
        # Selection by the user in tables and trees is frozen as well.
        self.parent.set_selection_frozen(True)

    def enable_actions(self):
        """Un-freeze all actions after having done something."""
        # self.parent.findChildren(QAction) returns a list of all actions in the application.
        print("o enabling actions in ", self.windowTitle())
        for action in self.parent.findChildren(QAction):
            action.setEnabled(True)
        self.parent.set_selection_frozen(False)

    def create_trees(self):
        for tree_name, coll_name in self.tree_collection_dict.items():
            show_name = tree_name.removesuffix("Widget")
            page_name = show_name + "Page"
            layout_name = show_name + "Layout"
            collection = eval(f"self.parent.{coll_name}")
            tree_labels = ["role", "topology", "feature", "scenario"]
            if not "role" in eval(f"self.parent.{coll_name}.entity_dict.keys()"):
                tree_labels.remove("role")
            if not "topology" in eval(f"self.parent.{coll_name}.entity_dict.keys()"):
                tree_labels.remove("topology")
            if not "feature" in eval(f"self.parent.{coll_name}.entity_dict.keys()"):
                tree_labels.remove("feature")
            if "properties_names" in eval(
                f"self.parent.{coll_name}.entity_dict.keys()"
            ):
                prop_label = "properties_names"
                prop_comp_label = "properties_components"
            else:
                prop_label = None
                prop_comp_label = None
            default_labels = ["none", "X", "Y", "Z"]
            setattr(
                self,
                f"{tree_name}",
                CustomTreeWidget(
                    parent=eval(f"self.{page_name}"),
                    view=self,
                    collection=collection,
                    tree_labels=tree_labels,
                    name_label="name",
                    uid_label="uid",
                    prop_label=prop_label,
                    prop_comp_label=prop_comp_label,
                    default_labels=default_labels,
                ),
            )
            eval(f"self.{tree_name}").setObjectName(tree_name)
            eval(f"self.{layout_name}").addWidget(
                eval(f"self.{tree_name}.header_widget")
            )
            eval(f"self.{layout_name}").addWidget(eval(f"self.{tree_name}"))
            eval(f"self.{layout_name}.setContentsMargins(0,0,0,0)")

    def coll_from_tree(self, tree=None):
        try:
            if isinstance(tree, CustomTreeWidget):
                tree = tree.tree_name
            coll_name = self.tree_collection_dict[tree]
            collection = eval(f"self.parent.{coll_name}")
            return collection
        except:
            self.print_terminal("Error in coll_from_tree")
            return None

    def tree_from_coll(self, coll=None):
        try:
            if isinstance(coll, BaseCollection):
                coll = coll.collection_name
            tree_name = self.collection_tree_dict[coll]
            tree = eval(f"self.{tree_name}")
            return tree
        except:
            self.print_terminal("Error in tree_from_coll")
            return None

    # Collections whose entities open showing a property (their active one) instead of "none".
    INITIAL_PROPERTY_COLLECTIONS = ("mesh3d_coll", "image_coll")

    def initial_show_property(self, collection_name=None, uid=None):
        """Property shown when an entity is added to this view (and selected in the tree drop-down).
        Meshes and images open showing their active property (the active scalars of the VTK
        object, which PyVista would draw anyway), or their first property if none is active; other
        entities open with none (legend color)."""
        if collection_name not in self.INITIAL_PROPERTY_COLLECTIONS:
            return None
        collection = getattr(self.parent, collection_name, None)
        try:
            names = list(collection.get_uid_properties_names(uid) or [])
            vtk_obj = collection.get_uid_vtk_obj(uid)
        except Exception:
            return None
        if not names or vtk_obj is None:
            return None
        for data in (vtk_obj.GetPointData(), vtk_obj.GetCellData()):
            scalars = data.GetScalars() if data is not None else None
            if scalars is not None and scalars.GetName() in names:
                return scalars.GetName()
        return names[0]

    def entities_added_update_views(self, updated_uids=None, collection=None):
        """This is called when an entity is added to a collection."""
        # remove from updated_list the uid's that are excluded from this view by self.view_filter.
        updated_uids = collection.filter_uids(query=self.view_filter, uids=updated_uids)
        tree = self.tree_from_coll(coll=collection)
        for uid in updated_uids:
            initial_property = self.initial_show_property(collection.collection_name, uid)
            this_actor = self.show_actor_with_property(
                uid=uid,
                coll_name=collection.collection_name,
                show_property=initial_property,
                visible=True,
            )

            self.actors_df = pd_concat(
                [
                    self.actors_df,
                    pd_DataFrame(
                        [
                            {
                                "uid": uid,
                                "actor": this_actor,
                                "show": True,
                                "collection": collection.collection_name,
                                "show_property": initial_property,
                            }
                        ]
                    ),
                ],
                ignore_index=True,
            )
        tree.add_items_to_tree(uids_to_add=updated_uids)

    def entities_removed_update_views(self, updated_uids=None, collection=None):
        """This is called when an entity is removed from a collection."""
        tree = self.tree_from_coll(coll=collection)
        has_plotter = hasattr(self, "plotter") and hasattr(self.plotter, "renderer")
        actor_uids = set(self.actors_df["uid"])
        for uid in updated_uids:
            if uid in actor_uids:
                self.remove_actor_in_view(uid=uid, redraw=False)
            if has_plotter:
                self.plotter.remove_actor(f"{uid}_silh", render=False)
        self.actors_df.drop(
            self.actors_df[self.actors_df["uid"].isin(updated_uids)].index, inplace=True
        )
        # Removed entities are pruned from the project selection by the project itself.
        tree.remove_items_from_tree(uids_to_remove=updated_uids)
        if has_plotter:
            self.plotter.render()
        elif hasattr(self, "figure"):
            self.figure.canvas.draw_idle()

    def entities_geom_modified_update_views(self, updated_uids=None, collection=None):
        """This is called when an entity geometry or topology is modified (i.e. the vtk object is modified)."""
        # remove from updated_list the uid's that are excluded from this view by self.view_filter.
        updated_uids = collection.filter_uids(query=self.view_filter, uids=updated_uids)
        for uid in updated_uids:
            # This replaces the previous copy of the actor with the same uid, and updates the actors dataframe.
            # See issue #33 for a discussion on actors replacement by the PyVista add_mesh and add_volume methods.
            actor_rows = self.actors_df.loc[self.actors_df["uid"] == uid]
            if actor_rows.empty:
                # Interpretation views intentionally defer some full actors.
                continue
            show = actor_rows["show"].values[0]
            show_property = actor_rows["show_property"].values[0]
            self.show_actor_with_property(
                uid=uid,
                coll_name=collection.collection_name,
                show_property=show_property,
                visible=show,
            )

    def sync_view_filter(self, updated_uids=None, collection=None):
        """Apply self.view_filter after a change that can affect it (metadata such as parent_uid for
        cross-section views, properties_names for the stereoplot): entities that start matching the
        filter are added to the view, those that stop matching it are removed. Returns the updated
        uids that were already in the view and still match it, to be updated by the caller."""
        updated_uids = list(updated_uids or [])
        matching = set(collection.filter_uids(query=self.view_filter, uids=updated_uids))
        in_view = set(self.actors_df["uid"])
        leaving = [uid for uid in updated_uids if uid in in_view and uid not in matching]
        entering = [uid for uid in updated_uids if uid in matching and uid not in in_view]
        if leaving:
            self.entities_removed_update_views(updated_uids=leaving, collection=collection)
        if entering:
            self.entities_added_update_views(updated_uids=entering, collection=collection)
        return [uid for uid in updated_uids if uid in matching and uid in in_view]

    # Items of the property drop-down that are not entity properties and are always available.
    ALWAYS_AVAILABLE_PROPERTIES = ("none", "X", "Y", "Z", "RGB total", "Marker", "Annotations")

    def shown_property_available(self, collection=None, uid=None, shown_property=None):
        """True if the item shown from the property drop-down still exists for uid: a default item
        (none, X, Y, Z, ...), a property, a component "Name[i]" of a multi-component property
        (e.g. Normals[2], listed as "Normals" in properties_names), or a texture of the entity."""
        if shown_property is None:
            return False
        if shown_property in self.ALWAYS_AVAILABLE_PROPERTIES:
            return True
        names = list(collection.get_uid_properties_names(uid) or [])
        if shown_property in names:
            return True
        if isinstance(shown_property, str) and shown_property.endswith("]") and "[" in shown_property:
            if shown_property[: shown_property.index("[")] in names:
                return True
        if "textures" in collection.df.columns:
            textures = collection.df.loc[collection.df["uid"] == uid, "textures"].values
            if len(textures) and shown_property in list(textures[0] or []):
                return True
        return False

    def entities_data_keys_added_update_views(self, updated_uids=None, collection=None):
        """This is called when point or cell data (properties) are added."""
        # AT THE MOMENT THIS IS IDENTICAL TO entities_data_keys_removed_update_views
        # Entities entering/leaving the view filter are added/removed; the others are updated below.
        updated_uids = self.sync_view_filter(updated_uids=updated_uids, collection=collection)
        tree = self.tree_from_coll(coll=collection)
        for uid in updated_uids:
            # Replace the previous copy of the actor with the same uid, and update the actors dataframe, only if a
            # property that has been removed is shown at the moment. See issue #33 for a discussion on actors
            # replacement by the PyVista add_mesh and add_volume methods.
            if (
                not self.actors_df.loc[
                    self.actors_df["uid"] == uid, "show_property"
                ].to_list()[0]
                is None
            ):
                if not self.shown_property_available(
                    collection,
                    uid,
                    self.actors_df.loc[self.actors_df["uid"] == uid, "show_property"].values[0],
                ):
                    show = self.actors_df.loc[
                        self.actors_df["uid"] == uid, "show"
                    ].to_list()[0]
                    self.show_actor_with_property(
                        uid=uid,
                        coll_name=collection.collection_name,
                        show_property=None,
                        visible=show,
                    )
                    self.actors_df.loc[
                        self.actors_df["uid"] == uid, ["show_property"]
                    ] = None
        # Rebuild the trees to add/remove the properties that have been changed.
        tree.update_properties_for_uids(
            updated_uids
        )  # this should be a method of the tree

    def entities_data_keys_removed_update_views(
        self, updated_uids=None, collection=None
    ):
        """This is called when point or cell data (properties) are removed."""
        # AT THE MOMENT THIS IS IDENTICAL TO entities_data_keys_added_update_views
        self.entities_data_keys_added_update_views(
            updated_uids=updated_uids, collection=collection
        )

    def entities_data_val_modified_update_views(
        self, updated_uids=None, collection=None
    ):
        """This is called when entity point or cell data are modified. The actor is redrawn if it shows a
        property (its values may have changed). Trees do not need to be modified."""
        # remove from updated_list the uid's that are excluded from this view by self.view_filter.
        updated_uids = collection.filter_uids(query=self.view_filter, uids=updated_uids)
        for uid in updated_uids:
            actor_rows = self.actors_df.loc[self.actors_df["uid"] == uid]
            if actor_rows.empty:
                continue
            shown_property = actor_rows["show_property"].values[0]
            # Redraw with the shown item (values changed). Properties cannot disappear here: removals
            # are handled by entities_data_keys_removed_update_views.
            if self.shown_property_available(collection, uid, shown_property) and shown_property != "none":
                self.show_actor_with_property(
                    uid=uid,
                    coll_name=collection.collection_name,
                    show_property=shown_property,
                    visible=actor_rows["show"].values[0],
                )

    def entities_metadata_modified_update_views(
        self, collection=None, updated_uids=None
    ):
        """This is called when an entity metadata are modified, and the legend is automatically updated. Signals
        to the collection view tree, if they are set, are disconnected to avoid a nasty loop that would disrupt them.
        """
        # Entities entering/leaving the view filter (e.g. parent_uid changed for a cross-section view)
        # are added/removed; the others are updated below.
        updated_uids = self.sync_view_filter(updated_uids=updated_uids, collection=collection)
        tree = self.tree_from_coll(coll=collection)
        self.change_actor_color(collection=collection, updated_uids=updated_uids)
        self.change_actor_point_size(collection=collection, updated_uids=updated_uids)
        self.change_actor_line_thick(collection=collection, updated_uids=updated_uids)
        self.change_actor_opacity(collection=collection, updated_uids=updated_uids)
        total_items = len(collection.df)
        if len(updated_uids) > total_items * 0.2:
            # print("Rebuilding the entire tree")
            tree.populate_tree()
        else:
            tree.remove_items_from_tree(uids_to_remove=updated_uids)
            tree.add_items_to_tree(uids_to_add=updated_uids)

    # def entities_legend_modified_update_views(self, collection=None, updated_uids=None):
    #     """This is called when changing any property in the legend. Updating trees not
    #     needed since metadata do not change and entities are neither added or removed.
    #     """
    #     # remove from updated_list the uid's that are excluded from this view by self.view_filter.
    #     updated_uids = collection.filter_uids(query=self.view_filter, uids=updated_uids)
    #     for uid in updated_uids:
    #         show = self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]
    #         show_property = self.actors_df.loc[
    #             self.actors_df["uid"] == uid, "show_property"
    #         ].values[0]
    #         self.show_actor_with_property(
    #             uid=uid,
    #             coll_name=collection.collection_name,
    #             show_property=show_property,
    #             visible=show,
    #         )

    def show_all(self):
        """Show all actors."""
        for uid in self.actors_df["uid"].to_list():
            if not self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                self.set_actor_visible(uid=uid, visible=True)
        self.actors_df["show"] = True

    def hide_all(self):
        """Hide all actors."""
        for uid in self.actors_df["uid"].to_list():
            if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                self.set_actor_visible(uid=uid, visible=False)
        self.actors_df["show"] = False

    def show_uids(self, uids: list = None):
        """Show actors with the given uids."""
        # Maybe in the future this might be reimplemented in parallel or vectorized?
        for uid in uids:
            # if not self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
            self.set_actor_visible(uid=uid, visible=True)
            self.actors_df.loc[self.actors_df["uid"] == uid, "show"] = True

    def hide_uids(self, uids: list = None):
        """Hide actors with the given uids."""
        # Maybe in th future this might be reimplemented in parallel or vectorized?
        for uid in uids:
            # if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
            self.set_actor_visible(uid=uid, visible=False)
            self.actors_df.loc[self.actors_df["uid"] == uid, "show"] = False

    @property
    def uids_in_view(self):
        return self.actors_df["uid"].to_list()

    @property
    def shown_uids(self):
        return self.actors_df.loc[self.actors_df["show"] == True, "uid"].to_list()

    @property
    def hidden_uids(self):
        return self.actors_df.loc[self.actors_df["show"] == False, "uid"].to_list()

    def toggle_visibility(
        self, collection_name=None, turn_on_uids=None, turn_off_uids=None
    ):
        # print(f"toggle_visibility: {collection_name}, turn_on_uids: {turn_on_uids}, turn_off_uids: {turn_off_uids}")
        self.show_uids(turn_on_uids)
        self.hide_uids(turn_off_uids)

    def toggle_property(self, collection_name=None, uid=None, prop_text=None):
        """Generic method to toggle the property shown by an actor that is already present in the view."""
        # store shown/hidden state
        show = self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]
        # case for Marker
        if prop_text == "Marker":
            self.show_markers(uid=uid, show_property=prop_text)
        # case for Annotations
        elif prop_text == "Annotations":
            self.show_labels(
                uid=uid, show_property=prop_text, coll_name=collection_name
            )
        # case for all other properties
        else:
            this_actor = self.show_actor_with_property(
                uid=uid,
                coll_name=collection_name,
                show_property=prop_text,
                visible=show,
            )
        # replace the property shown in the actors dataframe
        self.actors_df.loc[self.actors_df["uid"] == uid, "show_property"] = prop_text

    # def data_keys_modified_update_views(self, collection_name=None, updated_uids=None):
    #     # __________________________________________________________________ ?????
    #     collection = eval(f"self.parent.{collection_name}")
    #     tree = eval(f"self.{self.collection_tree_dict[collection_name]}")
    #     # Remove from updated_uids the uid's that are excluded from this view by self.view_filter
    #     # by removing from the list of all uid's that should appear in this view (from query)
    #     # the uid's that do not belong to the updated_list
    #     updated_uids = collection.filter_uids(query=self.view_filter, uids=updated_uids)
    #     # Deal with removed properties that are currently shown (do nothing in view otherwise)
    #     # for uid in updated_uids:
    #     #     shown_prop = self.actors_df.loc[self.actors_df["uid"] == uid, "show_property"].values[0]
    #     #     valid_props = collection.df.loc[self.actors_df["uid"] == uid, "properties_names"].tolist()
    #     #     if not shown_prop in valid_props:
    #     #         self.toggle_property(collection_name=collection_name, uid=uid, prop_text=None)
    #     # Deal with combo boxes in tree
    #     tree.update_properties_for_uids(uids=updated_uids)

    def prop_legend_cmap_modified_update_views(self, this_property=None):
        """Redraw all actors that are currently shown with a property whose colormap has been changed."""
        for uid in self.actors_df["uid"].to_list():
            if (
                self.actors_df.loc[
                    self.actors_df["uid"] == uid, "show_property"
                ].to_list()[0]
                == this_property
            ):
                show = self.actors_df.loc[
                    self.actors_df["uid"] == uid, "show"
                ].to_list()[0]
                collection_name = self.actors_df.loc[
                    self.actors_df["uid"] == uid, "collection"
                ].to_list()[0]
                # This replaces the previous copy of the actor with the same uid, and updates the actors dataframe.
                # See issue #33 for a discussion on actors replacement by the PyVista add_mesh and add_volume methods.
                this_actor = self.show_actor_with_property(
                    uid=uid,
                    coll_name=collection_name,
                    show_property=this_property,
                    visible=show,
                )
                self.actors_df.loc[self.actors_df["uid"] == uid, ["show_property"]] = (
                    this_property
                )

    def add_all_entities(self):
        """
        Add all entities in project collections.
        All objects are visible by default -> show = True.
        """
        for collection_name in self.tree_collection_dict.values():
            coll_df = eval(f"self.parent.{collection_name}").df
            try:
                filtered_uids = coll_df.query(self.view_filter)["uid"].tolist()
            except Exception as e:
                # This collection's DataFrame doesn't have the columns this
                # view's filter depends on (e.g. xsect_coll has no
                # "properties_names" column) - nothing to add from it for this view.
                continue
            prgs_bar = progress_dialog(
                max_value=len(filtered_uids),
                title_txt="Opening view",
                label_txt=f"Adding objects from {collection_name}...",
                cancel_txt=None,
                parent=self,
            )
            for uid in (
                eval(f"self.parent.{collection_name}")
                .df.query(self.view_filter)["uid"]
                .tolist()
            ):
                initial_property = self.initial_show_property(collection_name, uid)
                this_actor = self.show_actor_with_property(
                    uid=uid,
                    coll_name=collection_name,
                    show_property=initial_property,
                    visible=True,
                )
                # New Pandas >= 2.0.0
                self.actors_df = pd_concat(
                    [
                        self.actors_df,
                        pd_DataFrame(
                            [
                                {
                                    "uid": uid,
                                    "actor": this_actor,
                                    "show": True,
                                    "collection": collection_name,
                                    "show_property": initial_property,
                                }
                            ]
                        ),
                    ],
                    ignore_index=True,
                )
                prgs_bar.add_one()

    # ================================  General methods shared by all views - built incrementally =====================

    def initialize_menu_tools(self):
        """This is the base method of the abstract BaseView() class, used to add menu tools used by all windows.
        The code appearing here is appended in subclasses using super().initialize_menu_tools() in their first line.
        Do not use "pass" that would be appended to child classes.
        """

    # ================================  Placeholders for required methods, implemented in child classes ===============

    def closeEvent(self, event):
        """Dummy method to override the standard closeEvent method by (i) disconnecting all signals."""
        pass

    def get_actor_by_uid(self, uid: str = None):
        """Dummy method to get an actor by uid. Must be implemented in subclasses."""
        return None

    def get_uid_from_actor(self):
        """Dummy method to get the uid of an actor, e.g. selected with mouse or in other ways.
        Must be implemented in subclasses."""
        return None

    def actor_shown(self, uid: str = None):
        """Dummy method to check if an actor is shown. Returns a boolean.
        Must be implemented in subclasses."""
        return False

    def show_actors(self, uids: list = None):
        """Dummy method to show actors in uids list. Must be implemented in subclasses."""
        return

    def hide_actors(self, uids: list = None):
        """Dummy method to hide actors in uids list. Must be implemented in subclasses."""
        return

    def change_actor_color(self, updated_uids: list = None, collection=None):
        """Dummy method to update color for actor uid. Must be implemented in subclasses."""
        return

    def change_actor_opacity(self, updated_uids: list = None, collection=None):
        """Dummy method to update opacity for actor uid. Must be implemented in subclasses."""
        return

    def change_actor_line_thick(self, updated_uids: list = None, collection=None):
        """Dummy method to update line thickness for actor uid. Must be implemented in subclasses."""
        return

    def change_actor_point_size(self, updated_uids: list = None, collection=None):
        """Dummy method to update point size for actor uid. Must be implemented in subclasses."""
        return

    def set_actor_visible(self, uid=None, visible=None, name=None):
        """Dummy method to Set actor uid visible or invisible (visible = True or False).
        Must be implemented in subclasses."""
        return

    def remove_actor_in_view(self, uid=None, redraw=False):
        """Dummy method to remove actor with uid. Must be implemented in subclasses."""
        return

    def show_actor_with_property(
        self, uid=None, coll_name=None, show_property=None, visible=None
    ):
        """Dummy method to show actor with uid and property. Must be implemented in subclasses."""
        return

    def show_markers(self, uid=None, show_property=None):
        """Dummy method to show markers for uid and property. Must be implemented in subclasses."""
        return

    def show_labels(self, uid=None, coll_name=None, show_property=None):
        """Dummy method to show labels for uid and property. Must be implemented in subclasses."""
        return

    def initialize_interactor(self):
        """Dummy method to initialize the plotting canvas. Must be implemented in subclasses."""
        return

    def show_qt_canvas(self):
        """Dummy method to show the plotting canvas. Must be implemented in subclasses."""
        return
