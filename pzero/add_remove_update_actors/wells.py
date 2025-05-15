from pandas import DataFrame as pd_DataFrame
from pandas import concat as pd_concat

from pzero.build_and_update.wells import *

# Methods used to add, remove, and update actors from the WELLS collection


def well_added_update_views(self, updated_list=None):
    """This is called when an entity is added to the well collection.
    Disconnect signals to well tree, if they are set, to avoid a nasty loop
    that disrupts the trees, then they are reconnected when the trees are rebuilt"""
    self.WellsTreeWidget.itemChanged.disconnect()
    """Create pandas dataframe as list of "new" actors"""
    actors_df_new = pd_DataFrame(
        columns=["uid", "actor", "show", "collection", "show_property"]
    )
    for uid in updated_list:
        this_actor = self.show_actor_with_property(
            uid=uid, collection="well_coll", show_property=None, visible=True
        )
        # Old Pandas <= 1.5.3
        # self.actors_df = self.actors_df.append(
        #     {
        #         "uid": uid,
        #         "actor": this_actor,
        #         "show": True,
        #         "collection": "well_coll",
        #         "show_property": None,
        #     },
        #     ignore_index=True,
        # )
        # actors_df_new = actors_df_new.append(
        #     {
        #         "uid": uid,
        #         "actor": this_actor,
        #         "show": True,
        #         "collection": "well_coll",
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
                            "collection": "well_coll",
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
                            "collection": "well_coll",
                            "show_property": None,
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )
        update_well_tree_added(self, actors_df_new)
    """Re-connect signals."""
    self.WellsTreeWidget.itemChanged.connect(self.toggle_well_visibility)


def well_removed_update_views(self, updated_list=None):
    """This is called when a well is removed from the wells collection.
    Disconnect signals to well tree, if they are set, to avoid a nasty loop
    that disrupts the trees, then they are reconnected when the trees are rebuilt"""
    self.WellsTreeWidget.itemChanged.disconnect()
    for uid in updated_list:
        self.remove_actor_in_view(uid=uid, redraw=True)
    update_well_tree_removed(self, removed_list=updated_list)
    """Re-connect signals."""
    self.WellsTreeWidget.itemChanged.connect(self.toggle_well_visibility)


def well_data_keys_modified_update_views(self, updated_list=None):
    """This is called when point or cell data (properties) are modified.
    Disconnect signals to geology and topology tree, if they are set, to avoid a nasty loop
    that disrupts the trees, then they are reconnected when the trees are rebuilt"""
    self.WellsTreeWidget.itemChanged.disconnect()
    for uid in updated_list:
        if (
            not self.actors_df.loc[
                self.actors_df["uid"] == uid, "show_property"
            ].to_list()
            == []
        ):
            if not self.actors_df.loc[
                self.actors_df["uid"] == uid, "show_property"
            ].values[0] in self.parent.geol_coll.get_uid_properties_names(uid):
                show = self.actors_df.loc[
                    self.actors_df["uid"] == uid, "show"
                ].to_list()[0]
                # This replaces the previous copy of the actor with the same uid, and updates the actors dataframe.
                # See issue #33 for a discussion on actors replacement by the PyVista add_mesh and add_volume methods.
                this_actor = self.show_actor_with_property(
                    uid=uid, collection="geol_coll", show_property=None, visible=show
                )
                create_well_tree(self)
    """Re-connect signals."""
    self.WellsTreeWidget.itemChanged.connect(self.toggle_well_visibility)


def well_data_val_modified_update_views(self, updated_list=None): ...


def well_metadata_modified_update_views(self, updated_list=None):
    """This is called when entity metadata are modified, and the legend is automatically updated.
    Disconnect signals to geology and topology tree, if they are set, to avoid a nasty loop
    that disrupts the trees, then they are reconnected when the trees are rebuilt"""
    self.WellsTreeWidget.itemChanged.disconnect()
    for uid in updated_list:
        """Case for entities modified"""
        self.change_actor_color(uid=uid, collection="well_coll")
        self.change_actor_line_thick(uid=uid, collection="well_coll")
        create_well_tree(self)
    """Re-connect signals."""
    self.WellsTreeWidget.itemChanged.connect(self.toggle_well_visibility)


def well_legend_color_modified_update_views(self, updated_list=None):
    """This is called when the color in the geological legend is modified.
    Disconnect signals to geology and topology tree, if they are set, to avoid a nasty loop
    that disrupts the trees, then they are reconnected when the trees are rebuilt"""
    self.WellsTreeWidget.itemChanged.disconnect()
    for uid in updated_list:
        """Case for color changed"""
        self.change_actor_color(uid=uid, collection="well_coll")
    """Re-connect signals."""
    self.WellsTreeWidget.itemChanged.connect(self.toggle_well_visibility)


def well_legend_thick_modified_update_views(self, updated_list=None):
    """This is called when the line thickness in the geological legend is modified.
    Disconnect signals to geology and topology tree, if they are set, to avoid a nasty loop
    that disrupts the trees, then they are reconnected when the trees are rebuilt"""
    self.WellsTreeWidget.itemChanged.disconnect()
    for uid in updated_list:
        """Case for line_thick changed"""
        self.change_actor_line_thick(uid=uid, collection="well_coll")
    """Re-connect signals."""
    self.WellsTreeWidget.itemChanged.connect(self.toggle_well_visibility)


def well_legend_opacity_modified_update_views(self, updated_list=None):
    """This is called when the opacity in the well legend is modified.
    Disconnect signals to geology and topology tree, if they are set, to avoid a nasty loop
    that disrupts the trees, then they are reconnected when the trees are rebuilt"""
    self.WellsTreeWidget.itemChanged.disconnect()
    for uid in updated_list:
        """Case for line_thick changed"""
        self.change_actor_opacity(uid=uid, collection="well_coll")
    """Re-connect signals."""
    self.WellsTreeWidget.itemChanged.connect(self.toggle_well_visibility)
