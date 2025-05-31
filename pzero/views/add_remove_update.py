"""add_remove_update.py
PZero© Andrea Bistacchi"""

from pandas import DataFrame as pd_DataFrame
from pandas import concat as pd_concat


# =================  Methods used when adding, removing, and updating actors from collections  ========================


def entities_added_update_views(self, collection=None, tree=None, updated_list=None):
    """This is called when an entity is added to a collection. Signals to the collection view tree, if they are set,
    are disconnected to avoid a nasty loop that would disrupt them."""
    tree.itemChanged.disconnect()
    # remove from updated_list the uid's that are excluded from this view by self.view_filter.collection,
    # by removing from the list of all uid's that should appear in this view (from query), the uid's that
    # do not belong to the updated_list. try/except needed for when the query is non-valid.
    try:
        updated_list = list(
            set(
                self.parent.collection.df.query(self.view_filter.collection)[
                    "uid"
                ].tolist()
            )
            - (
                set(
                    self.parent.collection.df.query(self.view_filter.collection)[
                        "uid"
                    ].tolist()
                )
                - set(updated_list)
            )
        )
    except KeyError:
        updated_list = []
    for uid in updated_list:
        this_actor = self.show_actor_with_property(
            uid=uid, collection=collection, show_property=None, visible=True
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
                            "collection": collection,
                            "show_property": None,
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )
    tree.update_tree_added(
        self, uid_list=updated_list
    )  # this should be a method of the tree
    tree.itemChanged.connect(self.toggle_visibility)


def entities_removed_update_views(self, collection=None, tree=None, updated_list=None):
    """This is called when an entity is removed from a collection. Signals to the collection view tree, if they are set,
    are disconnected to avoid a nasty loop that would disrupt them. No need to apply a filter, since if a uid is
    not found in the actors list, nothing happens."""
    tree.itemChanged.disconnect()
    for uid in updated_list:
        self.remove_actor_in_view(uid=uid, redraw=True)
    tree.update_tree_removed(
        self, removed_list=updated_list
    )  # this should be a method of the tree
    tree.itemChanged.connect(self.toggle_visibility)


def entities_geom_modified_update_views(
    self, collection=None, tree=None, updated_list=None
):
    """This is called when an entity geometry or topology is modified (i.e. the vtk object is modified).
    In a previous version of this method, signals were disconnected, but this is no longer required
    since actors are replaced, not deleted and then re-created."""
    # remove from updated_list the uid's that are excluded from this view by self.view_filter.collection,
    # by removing from the list of all uid's that should appear in this view (from query), the uid's that
    # do not belong to the updated_list. try/except needed for when the query is non-valid.
    try:
        updated_list = list(
            set(
                self.parent.collection.df.query(self.view_filter.collection)[
                    "uid"
                ].tolist()
            )
            - (
                set(
                    self.parent.collection.df.query(self.view_filter.collection)[
                        "uid"
                    ].tolist()
                )
                - set(updated_list)
            )
        )
    except KeyError:
        updated_list = []
    for uid in updated_list:
        # This replaces the previous copy of the actor with the same uid, and updates the actors dataframe.
        # See issue #33 for a discussion on actors replacement by the PyVista add_mesh and add_volume methods.
        show = self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]
        show_property = self.actors_df.loc[
            self.actors_df["uid"] == uid, "show_property"
        ].values[0]
        self.show_actor_with_property(
            uid=uid, collection=collection, show_property=show_property, visible=show
        )


def entities_data_keys_modified_update_views(
    self, collection=None, tree=None, updated_list=None
):
    """This is called when point or cell data (properties) are modified. Signals to the collection view tree,
    if they are set, are disconnected to avoid a nasty loop that would disrupt them."""
    self.tree.itemChanged.disconnect()
    # remove from updated_list the uid's that are excluded from this view by self.view_filter.collection,
    # by removing from the list of all uid's that should appear in this view (from query), the uid's that
    # do not belong to the updated_list. try/except needed for when the query is non-valid.
    try:
        updated_list = list(
            set(
                self.parent.collection.df.query(self.view_filter.collection)[
                    "uid"
                ].tolist()
            )
            - (
                set(
                    self.parent.collection.df.query(self.view_filter.collection)[
                        "uid"
                    ].tolist()
                )
                - set(updated_list)
            )
        )
    except KeyError:
        updated_list = []
    for uid in updated_list:
        # Replace the previous copy of the actor with the same uid, and update the actors dataframe, only if a
        # property that has been removed is shown at the moment. See issue #33 for a discussion on actors
        # replacement by the PyVista add_mesh and add_volume methods.
        if (
            not self.actors_df.loc[
                self.actors_df["uid"] == uid, "show_property"
            ].to_list()[0]
            is None
        ):
            if not self.actors_df.loc[
                self.actors_df["uid"] == uid, "show_property"
            ].values[0] in self.parent.collection.get_uid_properties_names(uid):
                show = self.actors_df.loc[
                    self.actors_df["uid"] == uid, "show"
                ].to_list()[0]
                self.show_actor_with_property(
                    uid=uid, collection=collection, show_property=None, visible=show
                )
                self.actors_df.loc[self.actors_df["uid"] == uid, ["show_property"]] = (
                    None
                )
    # Rebuild the trees to add/remove the properties that have been changed.
    tree.create_tree(self)  # this should be a method of the tree
    tree.itemChanged.connect(self.toggle_visibility)


def entities_data_val_modified_update_views(
    self, collection=None, tree=None, updated_list=None
):
    """This is called when entity point or cell data are modified. The actor is modified just if the
    modified property is currently shown. Trees do not need to be modified."""
    # remove from updated_list the uid's that are excluded from this view by self.view_filter.collection,
    # by removing from the list of all uid's that should appear in this view (from query), the uid's that
    # do not belong to the updated_list. try/except needed for when the query is non-valid.
    try:
        updated_list = list(
            set(
                self.parent.collection.df.query(self.view_filter.collection)[
                    "uid"
                ].tolist()
            )
            - (
                set(
                    self.parent.collection.df.query(self.view_filter.collection)[
                        "uid"
                    ].tolist()
                )
                - set(updated_list)
            )
        )
    except KeyError:
        updated_list = []
    for uid in updated_list:
        # Replace the previous copy of the actor with the same uid, and update the actors dataframe, only if a
        # property that has been removed is shown at the moment. See issue #33 for a discussion on actors
        # replacement by the PyVista add_mesh and add_volume methods.
        if (
            not self.actors_df.loc[
                self.actors_df["uid"] == uid, "show_property"
            ].to_list()[0]
            is None
        ):
            if not self.actors_df.loc[
                self.actors_df["uid"] == uid, "show_property"
            ].values[0] in self.parent.geol_coll.get_uid_properties_names(uid):
                show = self.actors_df.loc[
                    self.actors_df["uid"] == uid, "show"
                ].to_list()[0]
                self.show_actor_with_property(
                    uid=uid, collection="geol_coll", show_property=None, visible=show
                )
                self.actors_df.loc[self.actors_df["uid"] == uid, ["show_property"]] = (
                    None
                )


def entities_metadata_modified_update_views(
    self, collection=None, tree=None, updated_list=None
):
    """This is called when an entity metadata are modified, and the legend is automatically updated. Signals
    to the collection view tree, if they are set, are disconnected to avoid a nasty loop that would disrupt them.
    """
    tree.itemChanged.disconnect()
    tree.legend_modified_update_views(
        self, updated_list=updated_list
    )  # is this a method of the tree or of the collection (already existing)?
    tree.create_tree(self)  # this should be a method of the tree
    tree.itemChanged.connect(self.toggle_visibility)


def entities_legend_modified_update_views(
    self, collection=None, tree=None, updated_list=None
):
    """This is called when changing any property in the legend. Updating trees not
    needed since metadata do not change and entities are neither added or removed.
    """
    # remove from updated_list the uid's that are excluded from this view by self.view_filter.collection,
    # by removing from the list of all uid's that should appear in this view (from query), the uid's that
    # do not belong to the updated_list. try/except needed for when the query is non-valid.
    try:
        updated_list = list(
            set(
                self.parent.collection.df.query(self.view_filter.collection)[
                    "uid"
                ].tolist()
            )
            - (
                set(
                    self.parent.collection.df.query(self.view_filter.collection)[
                        "uid"
                    ].tolist()
                )
                - set(updated_list)
            )
        )
    except KeyError:
        updated_list = []
    for uid in updated_list:
        show = self.actors_df.loc[self.actors_df["uid"] == uid, "show"].to_list()[0]
        show_property = self.actors_df.loc[
            self.actors_df["uid"] == uid, "show_property"
        ].to_list()[0]
        self.show_actor_with_property(
            uid=uid, collection=collection, show_property=show_property, visible=show
        )
