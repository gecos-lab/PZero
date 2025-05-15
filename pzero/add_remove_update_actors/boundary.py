from pandas import DataFrame as pd_DataFrame
from pandas import concat as pd_concat

from pzero.build_and_update.boundary import *


# Methods used to add, remove, and update actors from the BOUNDARY collection


def boundary_added_update_views(self, updated_list=None):
    """This is called when a boundary is added to the boundary collection.
    Disconnect signals to boundary list, if they are set, then they are
    reconnected when the list is rebuilt"""
    self.BoundariesTableWidget.itemChanged.disconnect()
    actors_df_new = pd_DataFrame(
        columns=["uid", "actor", "show", "collection", "show_property"]
    )
    for uid in updated_list:
        this_actor = self.show_actor_with_property(
            uid=uid, collection="boundary_coll", show_property=None, visible=False
        )
        # Old Pandas <= 1.5.3
        # self.actors_df = self.actors_df.append(
        #     {
        #         "uid": uid,
        #         "actor": this_actor,
        #         "show": False,
        #         "collection": "boundary_coll",
        #         "show_property": None,
        #     },
        #     ignore_index=True,
        # )
        # actors_df_new = actors_df_new.append(
        #     {
        #         "uid": uid,
        #         "actor": this_actor,
        #         "show": False,
        #         "collection": "boundary_coll",
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
                            "collection": "boundary_coll",
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
                            "collection": "boundary_coll",
                            "show_property": None,
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )
        update_boundary_list_added(self, actors_df_new)
    """Re-connect signals."""
    self.BoundariesTableWidget.itemChanged.connect(self.toggle_boundary_visibility)


def boundary_removed_update_views(self, updated_list=None):
    """This is called when a boundary is removed from the boundary collection.
    Disconnect signals to boundary list, if they are set, then they are
    reconnected when the list is rebuilt"""
    self.BoundariesTableWidget.itemChanged.disconnect()
    for uid in updated_list:
        self.remove_actor_in_view(uid=uid)
        update_boundary_list_removed(self, removed_list=updated_list)
    """Re-connect signals."""
    self.BoundariesTableWidget.itemChanged.connect(self.toggle_boundary_visibility)


def boundary_geom_modified_update_views(self, updated_list=None):
    """This is called when an entity geometry or topology is modified (i.e. the vtk object is modified)."""
    for uid in updated_list:
        show = self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]
        # This replaces the previous copy of the actor with the same uid, and updates the actors dataframe.
        # See issue #33 for a discussion on actors replacement by the PyVista add_mesh and add_volume methods.
        this_actor = self.show_actor_with_property(
            uid=uid, collection="boundary_coll", show_property=None, visible=show
        )


def boundary_metadata_modified_update_views(self, updated_list=None):
    """This is called when the boundary metadata are modified.
    Disconnect signals to boundary list, if they are set, then they are
    reconnected when the list is rebuilt"""
    self.BoundariesTableWidget.itemChanged.disconnect()
    for uid in updated_list:
        """Case for entities modified"""
        self.change_actor_color(uid=uid, collection="boundary_coll")
        self.change_actor_line_thick(uid=uid, collection="boundary_coll")
        create_boundary_list(self)
    """Re-connect signals."""
    self.BoundariesTableWidget.itemChanged.connect(self.toggle_boundary_visibility)


def boundary_legend_color_modified_update_views(self, updated_list=None):
    """This is called when the color in the boundary legend is modified.
    Disconnect signals to boundary list, if they are set, then they are
    reconnected when the list is rebuilt"""
    self.BoundariesTableWidget.itemChanged.disconnect()
    for uid in updated_list:
        """Case for color changed"""
        self.change_actor_color(uid=uid, collection="boundary_coll")
    """Re-connect signals."""
    self.BoundariesTableWidget.itemChanged.connect(self.toggle_boundary_visibility)


def boundary_legend_thick_modified_update_views(self, updated_list=None):
    """This is called when the line thickness in the boundary legend is modified.
    Disconnect signals to boundary list, if they are set, then they are
    reconnected when the list is rebuilt"""
    self.BoundariesTableWidget.itemChanged.disconnect()
    for uid in updated_list:
        """Case for line_thick changed"""
        self.change_actor_line_thick(uid=uid, collection="boundary_coll")
    """Re-connect signals."""
    self.BoundariesTableWidget.itemChanged.connect(self.toggle_boundary_visibility)


def boundary_legend_opacity_modified_update_views(self, updated_list=None):
    """This is called when the opacity in the image legend is modified.
    Disconnect signals to image tree, if they are set, to avoid a nasty loop
    that disrupts the trees, then they are reconnected when the trees are rebuilt"""
    self.BoundariesTableWidget.itemChanged.disconnect()
    for uid in updated_list:
        """Case for color changed"""
        self.change_actor_opacity(uid=uid, collection="boundary_coll")
    """Re-connect signals."""
    self.BoundariesTableWidget.itemChanged.connect(self.toggle_boundary_visibility)
