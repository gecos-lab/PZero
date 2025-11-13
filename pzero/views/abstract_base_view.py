"""abstract_base_view.py
PZero© Andrea Bistacchi"""

# PySide6 imports____
from PySide6.QtCore import QObject, Qt
from PySide6.QtWidgets import QMainWindow
from PySide6.QtGui import QAction
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
    # signal for selection change, emits a list of UIDs
    # Create signal ===================================================================================================
    newSelection = pyqtSignal(list)


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
        # __________________________________________________________________________________________
        # THIS MUST BE REMOVED - USE self.collection.selected_uids  ================================
        # __________________________________________________________________________________________
        self.selected_uids = []
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

    # ================================  General methods shared by all views ===========================================

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
        # prop_legend_cmap_modified ---
        self.prop_legend_lambda = (
            lambda this_property: self.prop_legend_cmap_modified_update_views(
                this_property=this_property
            )
        )
        self.parent.signals.prop_legend_cmap_modified.connect(self.prop_legend_lambda)

        # entities_added ---
        self.sig_add_lmb = lambda upd_uids, coll: self.entities_added_update_views(
            updated_uids=upd_uids, collection=coll
        )
        self.parent.signals.entities_added.connect(self.sig_add_lmb)

        # entities_removed ---
        self.sig_rem_lmb = lambda upd_uids, coll: self.entities_removed_update_views(
            updated_uids=upd_uids, collection=coll
        )
        self.parent.signals.entities_removed.connect(self.sig_rem_lmb)

        # geom_modified ---
        self.sig_geom_lmb = (
            lambda upd_uids, coll: self.entities_geom_modified_update_views(
                updated_uids=upd_uids, collection=coll
            )
        )
        self.parent.signals.geom_modified.connect(self.sig_geom_lmb)

        # data_keys_added ---
        self.sig_k_add_lmb = (
            lambda upd_uids, coll: self.entities_data_keys_added_update_views(
                updated_uids=upd_uids, collection=coll
            )
        )
        self.parent.signals.data_keys_added.connect(self.sig_k_add_lmb)

        # data_keys_removed ---
        self.sig_k_rmv_lmb = (
            lambda upd_uids, coll: self.entities_data_keys_removed_update_views(
                updated_uids=upd_uids, collection=coll
            )
        )
        self.parent.signals.data_keys_removed.connect(self.sig_k_rmv_lmb)

        # data_val_modified ---
        self.sig_val_lmb = (
            lambda upd_uids, coll: self.entities_data_val_modified_update_views(
                updated_uids=upd_uids, collection=coll
            )
        )
        self.parent.signals.data_val_modified.connect(self.sig_val_lmb)

        # metadata_modified ---
        self.sig_meta_lmb = (
            lambda upd_uids, coll: self.entities_metadata_modified_update_views(
                updated_uids=upd_uids, collection=coll
            )
        )
        self.parent.signals.metadata_modified.connect(self.sig_meta_lmb)

        # legend_color_modified ---
        self.sig_clr_lmb = lambda upd_uids, coll: self.change_actor_color(
            updated_uids=upd_uids, collection=coll
        )
        self.parent.signals.legend_color_modified.connect(self.sig_clr_lmb)

        # legend_thick_modified ---
        self.sig_thk_lmb = lambda upd_uids, coll: self.change_actor_line_thick(
            updated_uids=upd_uids, collection=coll
        )
        self.parent.signals.legend_thick_modified.connect(self.sig_thk_lmb)

        # legend_point_size_modified ---
        self.sig_pnt_lmb = lambda upd_uids, coll: self.change_actor_point_size(
            updated_uids=upd_uids, collection=coll
        )
        self.parent.signals.legend_point_size_modified.connect(self.sig_pnt_lmb)

        # legend_opacity_modified ---
        self.sig_opct_lmb = lambda upd_uids, coll: self.change_actor_opacity(
            updated_uids=upd_uids, collection=coll
        )
        self.parent.signals.legend_opacity_modified.connect(self.sig_opct_lmb)

        # selection_changed

    def disconnect_all_signals(self):
        """
        Used to disconnect all windows signals correctly, when a window is closed.
        If this method is removed PZero will crash when closing a window.
        If new signals are added, they must be listed also here.
        It would be nicer to keep a list of signals and then disconnect all signals in
        the list, but we have not found a way to do this at the moment.
        """
        # view signals
        # # Disconnect signal ===========================================================================================
        # self.signals.checkboxToggled.disconnect(self.view_sig_check_lmb)
        # # Disconnect signal ===========================================================================================
        # self.signals.propertyToggled.disconnect(self.view_sig_prop_lmb)

        # prop_legend_cmap_modified ---
        self.parent.signals.prop_legend_cmap_modified.disconnect(
            self.prop_legend_lambda
        )
        # entities_added
        self.parent.signals.entities_added.disconnect(self.sig_add_lmb)
        # entities_removed
        self.parent.signals.entities_removed.disconnect(self.sig_rem_lmb)
        # geom_modified
        self.parent.signals.geom_modified.disconnect(self.sig_geom_lmb)
        # data_keys_added
        self.parent.signals.data_keys_added.disconnect(self.sig_k_add_lmb)
        # data_keys_removed
        self.parent.signals.data_keys_removed.disconnect(self.sig_k_rmv_lmb)
        # data_val_modified
        self.parent.signals.data_val_modified.disconnect(self.sig_val_lmb)
        # metadata_modified
        self.parent.signals.metadata_modified.disconnect(self.sig_meta_lmb)
        # legend_color_modified
        self.parent.signals.legend_color_modified.disconnect(self.sig_clr_lmb)
        # legend_thick_modified
        self.parent.signals.legend_thick_modified.disconnect(self.sig_thk_lmb)
        # legend_point_size_modified
        self.parent.signals.legend_point_size_modified.disconnect(self.sig_pnt_lmb)
        # legend_opacity_modified
        self.parent.signals.legend_opacity_modified.disconnect(self.sig_opct_lmb)
        # selection_changed

    def disable_actions(self):
        """Freeze all actions while doing something."""
        # self.parent.findChildren(QAction) returns a list of all actions in the application.
        for action in self.parent.findChildren(QAction):
            # try - except added to catch an inexplicable bug with an action with text=""
            try:
                action.setDisabled(True)
            except:
                pass

    def enable_actions(self):
        """Un-freeze all actions after having done something."""
        # self.parent.findChildren(QAction) returns a list of all actions in the application.
        for action in self.parent.findChildren(QAction):
            action.setEnabled(True)

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

    def entities_added_update_views(self, updated_uids=None, collection=None):
        """This is called when an entity is added to a collection."""
        # remove from updated_list the uid's that are excluded from this view by self.view_filter.
        updated_uids = collection.filter_uids(query=self.view_filter, uids=updated_uids)
        tree = self.tree_from_coll(coll=collection)
        for uid in updated_uids:
            this_actor = self.show_actor_with_property(
                uid=uid,
                coll_name=collection.collection_name,
                show_property=None,
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
                                "show_property": None,
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
        for uid in updated_uids:
            if uid in self.actors_df["uid"].to_list():
                self.remove_actor_in_view(uid=uid, redraw=True)
                self.actors_df.drop(
                    self.actors_df[self.actors_df["uid"] == uid].index, inplace=True
                )
        tree.remove_items_from_tree(uids_to_remove=updated_uids)

    def entities_geom_modified_update_views(self, updated_uids=None, collection=None):
        """This is called when an entity geometry or topology is modified (i.e. the vtk object is modified)."""
        # remove from updated_list the uid's that are excluded from this view by self.view_filter.
        updated_uids = collection.filter_uids(query=self.view_filter, uids=updated_uids)
        for uid in updated_uids:
            # This replaces the previous copy of the actor with the same uid, and updates the actors dataframe.
            # See issue #33 for a discussion on actors replacement by the PyVista add_mesh and add_volume methods.
            show = self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]
            show_property = self.actors_df.loc[
                self.actors_df["uid"] == uid, "show_property"
            ].values[0]
            self.show_actor_with_property(
                uid=uid,
                coll_name=collection.collection_name,
                show_property=show_property,
                visible=show,
            )

    def entities_data_keys_added_update_views(self, updated_uids=None, collection=None):
        """This is called when point or cell data (properties) are added."""
        # AT THE MOMENT THIS IS IDENTICAL TO entities_data_keys_removed_update_views
        # remove from updated_list the uid's that are excluded from this view by self.view_filter.
        updated_uids = collection.filter_uids(query=self.view_filter, uids=updated_uids)
        tree = self.tree_from_coll(coll=collection)

        def _base_prop_name(prop_text: str):
            if not isinstance(prop_text, str) or not prop_text:
                return prop_text
            # Convert virtual props like "Prop (tot)" or "Prop[0]" to base name "Prop"
            if prop_text.endswith(" (tot)"):
                return prop_text[: -len(" (tot)")]
            if "]" in prop_text and "[" in prop_text:
                try:
                    return prop_text[: prop_text.index("[")]
                except Exception:
                    return prop_text
            return prop_text

        for uid in updated_uids:
            # Replace the previous copy of the actor with the same uid, and update the actors dataframe, only if a
            # property that has been removed is shown at the moment. See issue #33 for a discussion on actors
            # replacement by the PyVista add_mesh and add_volume methods.
            shown_prop = self.actors_df.loc[
                self.actors_df["uid"] == uid, "show_property"
            ].to_list()[0]
            if shown_prop is not None:
                valid_names = collection.get_uid_properties_names(uid)
                # consider virtual props valid if base prop still exists
                base_name = _base_prop_name(shown_prop)
                if base_name not in valid_names:
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
        """This is called when entity point or cell data are modified. The actor is modified just if the
        modified property is currently shown. Trees do not need to be modified."""
        # remove from updated_list the uid's that are excluded from this view by self.view_filter.
        updated_uids = collection.filter_uids(query=self.view_filter, uids=updated_uids)

        def _base_prop_name(prop_text: str):
            if not isinstance(prop_text, str) or not prop_text:
                return prop_text
            # Convert virtual props like "Prop (tot)" or "Prop[0]" to base name "Prop"
            if prop_text.endswith(" (tot)"):
                return prop_text[: -len(" (tot)")]
            if "]" in prop_text and "[" in prop_text:
                try:
                    return prop_text[: prop_text.index("[")]
                except Exception:
                    return prop_text
            return prop_text

        for uid in updated_uids:
            # Replace the previous copy of the actor with the same uid, and update the actors dataframe, only if a
            # property that has been removed is shown at the moment. See issue #33 for a discussion on actors
            # replacement by the PyVista add_mesh and add_volume methods.
            shown_prop = self.actors_df.loc[
                self.actors_df["uid"] == uid, "show_property"
            ].to_list()[0]
            if shown_prop is not None:
                valid_names = collection.get_uid_properties_names(uid)
                base_name = _base_prop_name(shown_prop)
                if base_name not in valid_names:
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

    def entities_metadata_modified_update_views(
        self, collection=None, updated_uids=None
    ):
        """This is called when an entity metadata are modified, and the legend is automatically updated. Signals
        to the collection view tree, if they are set, are disconnected to avoid a nasty loop that would disrupt them.
        """
        # remove from updated_list the uid's that are excluded from this view by self.view_filter.
        updated_uids = collection.filter_uids(query=self.view_filter, uids=updated_uids)
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
        # print("show_uids: ", uids)
        for uid in uids:
            # self.print_terminal(f"showing uid: {uid}")
            if not self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
                self.set_actor_visible(uid=uid, visible=True)
                self.actors_df.loc[self.actors_df["uid"] == uid, "show"] = True
                # self.print_terminal(f"shown uid: {uid}")

    def hide_uids(self, uids: list = None):
        """Hide actors with the given uids."""
        # Maybe in th future this might be reimplemented in parallel or vectorized?
        # print("hide_uids: ", uids)
        for uid in uids:
            # self.print_terminal(f"hiding uid: {uid}")
            if self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]:
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
            try:
                prgs_bar = progress_dialog(
                    max_value=len(
                        eval(f"self.parent.{collection_name}")
                        .df.query(self.view_filter)["uid"]
                        .tolist()
                    ),
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
                    this_actor = self.show_actor_with_property(
                        uid=uid,
                        coll_name=collection_name,
                        show_property=None,
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
                                        "show_property": None,
                                    }
                                ]
                            ),
                        ],
                        ignore_index=True,
                    )
                    prgs_bar.add_one()
            except:
                self.print_terminal(f"ERROR in add_all_entities: {collection_name}")
                pass

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
