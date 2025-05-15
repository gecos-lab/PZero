from pandas import DataFrame as pd_DataFrame
from pandas import concat as pd_concat

from pzero.build_and_update.mesh3d import *

# Methods used to add, remove, and update actors from the MESH3D collection


def mesh3d_added_update_views(self, updated_list=None):
    """This is called when a mesh3d is added to the mesh3d collection.
    Disconnect signals to mesh3d list, if they are set, then they are
    reconnected when the list is rebuilt"""
    self.Mesh3DTableWidget.itemChanged.disconnect()
    actors_df_new = pd_DataFrame(
        columns=["uid", "actor", "show", "collection", "show_property"]
    )
    for uid in updated_list:
        this_actor = self.show_actor_with_property(
            uid=uid, collection="mesh3d_coll", show_property=None, visible=False
        )
        # Old Pandas <= 1.5.3
        # self.actors_df = self.actors_df.append(
        #     {
        #         "uid": uid,
        #         "actor": this_actor,
        #         "show": False,
        #         "collection": "mesh3d_coll",
        #         "show_property": None,
        #     },
        #     ignore_index=True,
        # )
        # actors_df_new = actors_df_new.append(
        #     {
        #         "uid": uid,
        #         "actor": this_actor,
        #         "show": False,
        #         "collection": "mesh3d_coll",
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
                            "show": False,
                            "collection": "mesh3d_coll",
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
                            "show": False,
                            "collection": "mesh3d_coll",
                            "show_property": None,
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )
        update_mesh3d_list_added(self, actors_df_new)
    """Re-connect signals."""
    self.Mesh3DTableWidget.itemChanged.connect(self.toggle_mesh3d_visibility)


def mesh3d_removed_update_views(self, updated_list=None):
    """This is called when a mesh3d is removed from the mesh3d collection.
    Disconnect signals to mesh3d list, if they are set, then they are
    reconnected when the list is rebuilt"""
    self.Mesh3DTableWidget.itemChanged.disconnect()
    for uid in updated_list:
        self.remove_actor_in_view(uid=uid)
        update_mesh3d_list_removed(self, removed_list=updated_list)
    """Re-connect signals."""
    self.Mesh3DTableWidget.itemChanged.connect(self.toggle_mesh3d_visibility)


def mesh3d_data_keys_modified_update_views(self, updated_list=None):
    """This is called when point or cell data (properties) are modified.
    Disconnect signals to the mesh 3d tree, if they are set, to avoid a nasty loop
    that disrupts the tree, then they are reconnected when the trees are rebuilt"""
    self.Mesh3DTableWidget.itemChanged.disconnect()
    for uid in updated_list:
        if (
            not self.actors_df.loc[
                self.actors_df["uid"] == uid, "show_property"
            ].to_list()
            == []
        ):
            if not self.actors_df.loc[
                self.actors_df["uid"] == uid, "show_property"
            ].values[0] in self.parent.mesh3d_coll.get_uid_properties_names(uid):
                show = self.actors_df.loc[
                    self.actors_df["uid"] == uid, "show"
                ].to_list()[0]
                # This replaces the previous copy of the actor with the same uid, and updates the actors dataframe.
                # See issue #33 for a discussion on actors replacement by the PyVista add_mesh and add_volume methods.
                this_actor = self.show_actor_with_property(
                    uid=uid, collection="mesh3d_coll", show_property=None, visible=show
                )
                create_mesh3d_list(self)
    """Re-connect signals."""
    self.Mesh3DTableWidget.itemChanged.connect(self.toggle_dom_visibility)


def mesh3d_data_val_modified_update_views(self, updated_list=None):
    """This is called when entity point or cell data are modified.
    Disconnect signals to geology and topology tree, if they are set, to avoid a nasty loop
    that disrupts the trees, then they are reconnected when the trees are rebuilt"""
    self.Mesh3DTableWidget.itemChanged.disconnect()
    """IN THE FUTURE - generally just update the properties list - more complicate if we modify or delete the property that is shown_____________________"""
    """Re-connect signals."""
    self.Mesh3DTableWidget.itemChanged.connect(self.toggle_dom_visibility)


def mesh3d_metadata_modified_update_views(self, updated_list=None):
    """This is called when the mesh3d metadata are modified.
    Disconnect signals to mesh3d list, if they are set, then they are
    reconnected when the list is rebuilt"""
    self.Mesh3DTableWidget.itemChanged.disconnect()
    for uid in updated_list:
        """Case for entities modified"""
        self.change_actor_color(uid=uid, collection="mesh3d_coll")
        self.change_actor_line_thick(uid=uid, collection="mesh3d_coll")
        create_mesh3d_list(self)
    """Re-connect signals."""
    self.Mesh3DTableWidget.itemChanged.connect(self.toggle_mesh3d_visibility)


def mesh3d_legend_color_modified_update_views(self, updated_list=None):
    """This is called when the color in the cross-section legend is modified.
    Disconnect signals to mesh3d list, if they are set, then they are
    reconnected when the list is rebuilt"""
    self.Mesh3DTableWidget.itemChanged.disconnect()
    for uid in updated_list:
        """Case for color changed"""
        self.change_actor_color(uid=uid, collection="mesh3d_coll")
    """Re-connect signals."""
    self.Mesh3DTableWidget.itemChanged.connect(self.toggle_mesh3d_visibility)


def mesh3d_legend_thick_modified_update_views(self, updated_list=None):
    """This is called when the line thickness in the cross-section legend is modified.
    Disconnect signals to mesh3d list, if they are set, then they are
    reconnected when the list is rebuilt"""
    self.Mesh3DTableWidget.itemChanged.disconnect()
    for uid in updated_list:
        """Case for line_thick changed"""
        self.change_actor_line_thick(uid=uid, collection="mesh3d_coll")
    """Re-connect signals."""
    self.Mesh3DTableWidget.itemChanged.connect(self.toggle_mesh3d_visibility)


def mesh3d_legend_opacity_modified_update_views(self, updated_list=None):
    """This is called when the opacity in the image legend is modified.
    Disconnect signals to image tree, if they are set, to avoid a nasty loop
    that disrupts the trees, then they are reconnected when the trees are rebuilt"""
    self.Mesh3DTableWidget.itemChanged.disconnect()
    for uid in updated_list:
        """Case for color changed"""
        self.change_actor_opacity(uid=uid, collection="mesh3d_coll")
    """Re-connect signals."""
    self.Mesh3DTableWidget.itemChanged.connect(self.toggle_mesh3d_visibility)
