from pandas import DataFrame as pd_DataFrame
from pandas import concat as pd_concat

from pzero.build_and_update.geology import *

# Methods used to add, remove, and update actors from the GEOLOGICAL collection.


def geology_added_update_views(self, updated_list=None):
    """This is called when an entity is added to the geological collection.
    Disconnect signals to geology and topology tree, if they are set, to avoid a nasty loop
    that disrupts the trees, then they are reconnected when the trees are rebuilt"""
    self.GeologyTreeWidget.itemChanged.disconnect()
    self.GeologyTopologyTreeWidget.itemChanged.disconnect()
    # remove from updated_list the uid's that are excluded from this view by self.view_filter
    # by removing from the list of all uid's that should appear in this view (from query)
    # the uid's that do not belong to the updated_list
    updated_list = list(
        set(self.parent.geol_coll.df.query(self.view_filter)["uid"].tolist())
        - (
            set(self.parent.geol_coll.df.query(self.view_filter)["uid"].tolist())
            - set(updated_list)
        )
    )
    for uid in updated_list:
        this_actor = self.show_actor_with_property(
            uid=uid, collection="geol_coll", show_property=None, visible=True
        )
        # Old Pandas <= 1.5.3
        # self.actors_df = self.actors_df.append(
        #     {
        #         "uid": uid,
        #         "actor": this_actor,
        #         "show": True,
        #         "collection": "geol_coll",
        #         "show_property": None,
        #     },
        #     ignore_index=True,
        # )
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
                            "collection": "geol_coll",
                            "show_property": None,
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )
    update_geology_tree_added(self, uid_list=updated_list)
    update_topology_tree_added(self, uid_list=updated_list)
    """Re-connect signals."""
    self.GeologyTreeWidget.itemChanged.connect(self.toggle_geology_visibility)
    self.GeologyTopologyTreeWidget.itemChanged.connect(self.toggle_geology_visibility)


def geology_removed_update_views(self, updated_list=None):
    """This is called when an entity is removed from the geological collection.
    Disconnect signals to geology and topology tree, if they are set, to avoid a nasty loop
    that disrupts the trees, then they are reconnected when the trees are rebuilt.
    No need to apply a filter, since if a uid is not found in the actors list,
    nothing happens."""
    self.GeologyTreeWidget.itemChanged.disconnect()
    self.GeologyTopologyTreeWidget.itemChanged.disconnect()
    for uid in updated_list:
        self.remove_actor_in_view(uid=uid, redraw=True)
    update_geology_tree_removed(self, removed_list=updated_list)
    update_topology_tree_removed(self, removed_list=updated_list)
    """Re-connect signals."""
    self.GeologyTreeWidget.itemChanged.connect(self.toggle_geology_visibility)
    self.GeologyTopologyTreeWidget.itemChanged.connect(self.toggle_geology_visibility)


def geology_geom_modified_update_views(self, updated_list=None):
    """This is called when an entity geometry or topology is modified (i.e. the vtk object is modified)."""
    # In a previous version of this method, signals have to be disconnected, but this is no longer required
    # since actors are replaced, not deleted and then re-created.
    # Remove from updated_list the uid's that are excluded from this view by self.view_filter
    # by removing from the list of all uid's that should appear in this view (from query)
    # the uid's that do not belong to the updated_list
    updated_list = list(
        set(self.parent.geol_coll.df.query(self.view_filter)["uid"].tolist())
        - (
            set(self.parent.geol_coll.df.query(self.view_filter)["uid"].tolist())
            - set(updated_list)
        )
    )
    for uid in updated_list:
        # This replaces the previous copy of the actor with the same uid, and updates the actors dataframe.
        # See issue #33 for a discussion on actors replacement by the PyVista add_mesh and add_volume methods.
        show = self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]
        show_property = self.actors_df.loc[
            self.actors_df["uid"] == uid, "show_property"
        ].values[0]
        this_actor = self.show_actor_with_property(
            uid=uid, collection="geol_coll", show_property=show_property, visible=show
        )


def geology_data_keys_modified_update_views(self, updated_list=None):
    """This is called when point or cell data (properties) are modified.
    Disconnect signals to geology and topology tree, if they are set, to avoid a nasty loop
    that disrupts the trees, then they are reconnected when the trees are rebuilt"""
    # Remove from updated_list the uid's that are excluded from this view by self.view_filter
    # by removing from the list of all uid's that should appear in this view (from query)
    # the uid's that do not belong to the updated_list
    updated_list = list(
        set(self.parent.geol_coll.df.query(self.view_filter)["uid"].tolist())
        - (
            set(self.parent.geol_coll.df.query(self.view_filter)["uid"].tolist())
            - set(updated_list)
        )
    )
    self.GeologyTreeWidget.itemChanged.disconnect()
    self.GeologyTopologyTreeWidget.itemChanged.disconnect()
    for uid in updated_list:
        # Replace the previous copy of the actor with the same uid, and update the actors dataframe, only if a
        # property that has been removed is shown at the moment. See issue #33 for a discussion on actors
        # replacement by the PyVista add_mesh and add_volume methods.
        if (
            not self.actors_df.loc[
                self.actors_df["uid"] == uid, "show_property"
            ].to_list()[0]
            == None
        ):
            if not self.actors_df.loc[
                self.actors_df["uid"] == uid, "show_property"
            ].values[0] in self.parent.geol_coll.get_uid_properties_names(uid):
                show = self.actors_df.loc[
                    self.actors_df["uid"] == uid, "show"
                ].to_list()[0]
                this_actor = self.show_actor_with_property(
                    uid=uid, collection="geol_coll", show_property=None, visible=show
                )
                self.actors_df.loc[self.actors_df["uid"] == uid, ["show_property"]] = (
                    None
                )
    # Rebuild the trees to add/remove the properties that have been changed.
    create_geology_tree(self)
    create_topology_tree(self)
    """Re-connect signals."""
    self.GeologyTreeWidget.itemChanged.connect(self.toggle_geology_visibility)
    self.GeologyTopologyTreeWidget.itemChanged.connect(self.toggle_geology_visibility)


def geology_data_val_modified_update_views(self, updated_list=None):
    """This is called when entity point or cell data are modified. The actor is modified just if the
    modified property is currently shown. Trees do not need to be modified."""
    # Remove from updated_list the uid's that are excluded from this view by self.view_filter
    # by removing from the list of all uid's that should appear in this view (from query)
    # the uid's that do not belong to the updated_list
    updated_list = list(
        set(self.parent.geol_coll.df.query(self.view_filter)["uid"].tolist())
        - (
            set(self.parent.geol_coll.df.query(self.view_filter)["uid"].tolist())
            - set(updated_list)
        )
    )
    for uid in updated_list:
        # Replace the previous copy of the actor with the same uid, and update the actors dataframe, only if a
        # property that has been removed is shown at the moment. See issue #33 for a discussion on actors
        # replacement by the PyVista add_mesh and add_volume methods.
        if (
            not self.actors_df.loc[
                self.actors_df["uid"] == uid, "show_property"
            ].to_list()[0]
            == None
        ):
            if not self.actors_df.loc[
                self.actors_df["uid"] == uid, "show_property"
            ].values[0] in self.parent.geol_coll.get_uid_properties_names(uid):
                show = self.actors_df.loc[
                    self.actors_df["uid"] == uid, "show"
                ].to_list()[0]
                this_actor = self.show_actor_with_property(
                    uid=uid, collection="geol_coll", show_property=None, visible=show
                )
                self.actors_df.loc[self.actors_df["uid"] == uid, ["show_property"]] = (
                    None
                )


def geology_metadata_modified_update_views(self, updated_list=None):
    """This is called when an entity metadata are modified, and the legend is automatically updated.
    Disconnect signals to geology and topology tree, if they are set, to avoid a nasty loop
    that disrupts the trees, then they are reconnected when the trees are rebuilt"""
    self.GeologyTreeWidget.itemChanged.disconnect()
    self.GeologyTopologyTreeWidget.itemChanged.disconnect()
    geology_legend_modified_update_views(self, updated_list=updated_list)
    create_geology_tree(self)
    create_topology_tree(self)
    """Re-connect signals."""
    self.GeologyTreeWidget.itemChanged.connect(self.toggle_geology_visibility)
    self.GeologyTopologyTreeWidget.itemChanged.connect(self.toggle_geology_visibility)


def geology_legend_modified_update_views(self, updated_list=None):
    """This is called when changing any property in the legend.
    Updating trees not needed since metadata do not change and entities are neither added or removed.
    """
    # Remove from updated_list the uid's that are excluded from this view by self.view_filter
    # by removing from the list of all uid's that should appear in this view (from query)
    # the uid's that do not belong to the updated_list
    updated_list = list(
        set(self.parent.geol_coll.df.query(self.view_filter)["uid"].tolist())
        - (
            set(self.parent.geol_coll.df.query(self.view_filter)["uid"].tolist())
            - set(updated_list)
        )
    )
    for uid in updated_list:
        show = self.actors_df.loc[self.actors_df["uid"] == uid, "show"].to_list()[0]
        show_property = self.actors_df.loc[
            self.actors_df["uid"] == uid, "show_property"
        ].to_list()[0]
        this_actor = self.show_actor_with_property(
            uid=uid, collection="geol_coll", show_property=show_property, visible=show
        )
