from pandas import DataFrame as pd_DataFrame
from pandas import concat as pd_concat

from pzero.build_and_update.fluids import *


# Methods used to add, remove, and update actors from the FLUID collection


def fluid_added_update_views(self, updated_list=None):
    """This is called when an entity is added to the fluid collection.
    Disconnect signals to fluid and topology tree, if they are set, to avoid a nasty loop
    that disrupts the trees, then they are reconnected when the trees are rebuilt"""
    self.FluidsTreeWidget.itemChanged.disconnect()
    self.FluidsTopologyTreeWidget.itemChanged.disconnect()
    """Create pandas dataframe as list of "new" actors"""
    actors_df_new = pd_DataFrame(
        columns=["uid", "actor", "show", "collection", "show_property"]
    )
    for uid in updated_list:
        this_actor = self.show_actor_with_property(
            uid=uid, collection="fluid_coll", show_property=None, visible=True
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
                            "collection": "fluid_coll",
                            "show_property": None,
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )
        actors_df_new = pd_concat(
            [
                actors_df_new,
                pd_DataFrame(
                    [
                        {
                            "uid": uid,
                            "actor": this_actor,
                            "show": True,
                            "collection": "fluid_coll",
                            "show_property": None,
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )
        update_fluids_tree_added(self, actors_df_new)
        update_fluids_topology_tree_added(self, actors_df_new)
    """Re-connect signals."""
    self.FluidsTreeWidget.itemChanged.connect(self.toggle_fluids_visibility)
    self.FluidsTopologyTreeWidget.itemChanged.connect(self.toggle_fluids_visibility)


def fluid_removed_update_views(self, updated_list=None):
    """This is called when an entity is removed from the fluid collection.
    Disconnect signals to fluid and topology tree, if they are set, to avoid a nasty loop
    that disrupts the trees, then they are reconnected when the trees are rebuilt"""
    self.FluidsTreeWidget.itemChanged.disconnect()
    self.FluidsTopologyTreeWidget.itemChanged.disconnect()
    for uid in updated_list:
        self.remove_actor_in_view(uid=uid, redraw=True)
    update_fluids_tree_removed(self, removed_list=updated_list)
    update_fluids_topology_tree_removed(self, removed_list=updated_list)
    """Re-connect signals."""
    self.FluidsTreeWidget.itemChanged.connect(self.toggle_fluids_visibility)
    self.FluidsTopologyTreeWidget.itemChanged.connect(self.toggle_fluids_visibility)


def fluid_geom_modified_update_views(self, updated_list=None):
    """This is called when an entity geometry or topology is modified (i.e. the vtk object is modified)."""
    for uid in updated_list:
        show = self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]
        show_property = self.actors_df.loc[
            self.actors_df["uid"] == uid, "show_property"
        ].values[0]
        # This replaces the previous copy of the actor with the same uid, and updates the actors dataframe.
        # See issue #33 for a discussion on actors replacement by the PyVista add_mesh and add_volume methods.
        this_actor = self.show_actor_with_property(
            uid=uid, collection="fluid_coll", show_property=show_property, visible=show
        )


def fluid_data_keys_modified_update_views(self, updated_list=None):
    """This is called when point or cell data (properties) are modified.
    Disconnect signals to fluid and topology tree, if they are set, to avoid a nasty loop
    that disrupts the trees, then they are reconnected when the trees are rebuilt"""
    self.FluidsTreeWidget.itemChanged.disconnect()
    self.FluidsTopologyTreeWidget.itemChanged.disconnect()
    for uid in updated_list:
        if (
            not self.actors_df.loc[
                self.actors_df["uid"] == uid, "show_property"
            ].to_list()
            == []
        ):
            if not self.actors_df.loc[
                self.actors_df["uid"] == uid, "show_property"
            ].values[0] in self.parent.fluid_coll.get_uid_properties_names(uid):
                show = self.actors_df.loc[
                    self.actors_df["uid"] == uid, "show"
                ].to_list()[0]
                # This replaces the previous copy of the actor with the same uid, and updates the actors dataframe.
                # See issue #33 for a discussion on actors replacement by the PyVista add_mesh and add_volume methods.
                this_actor = self.show_actor_with_property(
                    uid=uid, collection="fluid_coll", show_property=None, visible=show
                )
                create_fluids_tree(self)
                create_fluids_topology_tree(self)
    """Re-connect signals."""
    self.FluidsTreeWidget.itemChanged.connect(self.toggle_fluids_visibility)
    self.FluidsTopologyTreeWidget.itemChanged.connect(self.toggle_fluids_visibility)


def fluid_data_val_modified_update_views(self, updated_list=None):
    """This is called when entity point or cell data are modified.
    Disconnect signals to fluid and topology tree, if they are set, to avoid a nasty loop
    that disrupts the trees, then they are reconnected when the trees are rebuilt"""
    self.FluidsTreeWidget.itemChanged.disconnect()
    self.FluidsTopologyTreeWidget.itemChanged.disconnect()
    """IN THE FUTURE - generally just update the properties list - more complicate if we modify or delete the property that is shown_____________________"""
    """Re-connect signals."""
    self.FluidsTreeWidget.itemChanged.connect(self.toggle_fluids_visibility)
    self.FluidsTopologyTreeWidget.itemChanged.connect(self.toggle_fluids_visibility)


def fluid_metadata_modified_update_views(self, updated_list=None):
    """This is called when entity metadata are modified, and the legend is automatically updated.
    Disconnect signals to fluid and topology tree, if they are set, to avoid a nasty loop
    that disrupts the trees, then they are reconnected when the trees are rebuilt"""
    self.FluidsTreeWidget.itemChanged.disconnect()
    self.FluidsTopologyTreeWidget.itemChanged.disconnect()
    for uid in updated_list:
        """Case for entities modified"""
        self.change_actor_color(uid=uid, collection="fluid_coll")
        self.change_actor_line_thick(uid=uid, collection="fluid_coll")
        create_fluids_tree(self)
        create_fluids_topology_tree(self)
    """Re-connect signals."""
    self.FluidsTreeWidget.itemChanged.connect(self.toggle_fluids_visibility)
    self.FluidsTopologyTreeWidget.itemChanged.connect(self.toggle_fluids_visibility)


def fluid_legend_color_modified_update_views(self, updated_list=None):
    # print(updated_list)
    """This is called when the color in the fluid legend is modified.
    Disconnect signals to fluid and topology tree, if they are set, to avoid a nasty loop
    that disrupts the trees, then they are reconnected when the trees are rebuilt"""
    self.FluidsTreeWidget.itemChanged.disconnect()
    self.FluidsTopologyTreeWidget.itemChanged.disconnect()
    for uid in updated_list:
        """Case for color changed"""
        fluids_list = self.parent.fluid_coll.get_uids
        if self.parent.fluid_coll.get_uid_x_section(uid) in fluids_list:
            self.change_actor_color(
                uid=self.parent.fluid_coll.get_uid_x_section(uid),
                collection="fluid_coll",
            )
        self.change_actor_color(uid=uid, collection="fluid_coll")

    """Re-connect signals."""
    self.FluidsTreeWidget.itemChanged.connect(self.toggle_fluids_visibility)
    self.FluidsTopologyTreeWidget.itemChanged.connect(self.toggle_fluids_visibility)


def fluid_legend_thick_modified_update_views(self, updated_list=None):
    """This is called when the line thickness in the fluid legend is modified.
    Disconnect signals to fluid and topology tree, if they are set, to avoid a nasty loop
    that disrupts the trees, then they are reconnected when the trees are rebuilt"""
    self.FluidsTreeWidget.itemChanged.disconnect()
    self.FluidsTopologyTreeWidget.itemChanged.disconnect()
    for uid in updated_list:
        """Case for line_thick changed"""
        self.change_actor_line_thick(uid=uid, collection="fluid_coll")
    """Re-connect signals."""
    self.FluidsTreeWidget.itemChanged.connect(self.toggle_fluids_visibility)
    self.FluidsTopologyTreeWidget.itemChanged.connect(self.toggle_fluids_visibility)


def fluid_legend_point_size_modified_update_views(self, updated_list=None):
    """This is called when the line thickness in the fluid legend is modified.
    Disconnect signals to fluid and topology tree, if they are set, to avoid a nasty loop
    that disrupts the trees, then they are reconnected when the trees are rebuilt"""
    self.FluidsTreeWidget.itemChanged.disconnect()
    self.FluidsTopologyTreeWidget.itemChanged.disconnect()
    for uid in updated_list:
        """Case for line_thick changed"""
        self.change_actor_line_point_size(uid=uid, collection="fluid_coll")
    """Re-connect signals."""
    self.FluidsTreeWidget.itemChanged.connect(self.toggle_fluids_visibility)
    self.FluidsTopologyTreeWidget.itemChanged.connect(self.toggle_fluids_visibility)


def fluid_legend_opacity_modified_update_views(self, updated_list=None):
    """This is called when the opacity in the fluid legend is modified.
    Disconnect signals to fluid and topology tree, if they are set, to avoid a nasty loop
    that disrupts the trees, then they are reconnected when the trees are rebuilt"""
    self.FluidsTreeWidget.itemChanged.disconnect()
    self.FluidsTopologyTreeWidget.itemChanged.disconnect()
    for uid in updated_list:
        """Case for line_thick changed"""
        self.change_actor_opacity(uid=uid, collection="fluid_coll")
    """Re-connect signals."""
    self.FluidsTreeWidget.itemChanged.connect(self.toggle_fluids_visibility)
    self.FluidsTopologyTreeWidget.itemChanged.connect(self.toggle_fluids_visibility)
