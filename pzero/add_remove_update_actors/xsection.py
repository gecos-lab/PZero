from pandas import DataFrame as pd_DataFrame
from pzero.build_and_update.xsections import *


def xsect_added_update_views(self, updated_list=None):
    """This is called when a cross-section is added to the xsect collection.
    Disconnect signals to xsect list, if they are set, then they are
    reconnected when the list is rebuilt"""
    self.XSectionTreeWidget.itemChanged.disconnect()
    actors_df_new = pd_DataFrame(
        columns=["uid", "actor", "show", "collection", "show_property"]
    )
    for uid in updated_list:
        this_actor = self.show_actor_with_property(
            uid=uid, collection="xsect_coll", show_property=None, visible=True
        )
        self.actors_df = self.actors_df.append(
            {
                "uid": uid,
                "actor": this_actor,
                "show": True,
                "collection": "xsect_coll",
                "show_property": None,
            },
            ignore_index=True,
        )
        actors_df_new = actors_df_new.append(
            {
                "uid": uid,
                "actor": this_actor,
                "show": True,
                "collection": "xsect_coll",
                "show_property": None,
            },
            ignore_index=True,
        )
        update_xsections_tree_added(self, actors_df_new)
    """Re-connect signals."""
    self.XSectionTreeWidget.itemChanged.connect(self.toggle_xsection_visibility)


def xsect_removed_update_views(self, updated_list=None):
    """This is called when a cross-section is removed from the xsect collection.
    Disconnect signals to xsect list, if they are set, then they are
    reconnected when the list is rebuilt"""
    self.XSectionTreeWidget.itemChanged.disconnect()
    for uid in updated_list:
        self.remove_actor_in_view(uid=uid)
        update_xsections_tree_removed(self, removed_list=updated_list)
    """Re-connect signals."""
    self.XSectionTreeWidget.itemChanged.connect(self.toggle_xsection_visibility)


def xsect_geom_modified_update_views(self, updated_list=None):
    """This is called when a cross-section geometry is modified (i.e. the frame is modified)."""
    for uid in updated_list:
        show = self.actors_df.loc[self.actors_df["uid"] == uid, "show"].values[0]
        # This replaces the previous copy of the actor with the same uid, and updates the actors dataframe.
        # See issue #33 for a discussion on actors replacement by the PyVista add_mesh and add_volume methods.
        this_actor = self.show_actor_with_property(uid=uid, collection="xsect_coll", show_property=None,
                                                   visible=show)


def xsect_metadata_modified_update_views(self, updated_list=None):
    """This is called when the cross-section metadata are modified.
    Disconnect signals to xsect list, if they are set, then they are
    reconnected when the list is rebuilt"""
    self.XSectionTreeWidget.itemChanged.disconnect()
    for uid in updated_list:
        """Case for entities modified"""
        self.change_actor_color(uid=uid, collection="xsect_coll")
        self.change_actor_line_thick(uid=uid, collection="xsect_coll")
        create_xsections_tree(self)
    """Re-connect signals."""
    self.XSectionTreeWidget.itemChanged.connect(self.toggle_xsection_visibility)


def xsect_legend_color_modified_update_views(self, updated_list=None):
    """This is called when the color in the cross-section legend is modified.
    Disconnect signals to xsect list, if they are set, then they are
    reconnected when the list is rebuilt"""
    self.XSectionTreeWidget.itemChanged.disconnect()
    for uid in updated_list:
        """Case for color changed"""
        self.change_actor_color(uid=uid, collection="xsect_coll")
    """Re-connect signals."""
    self.XSectionTreeWidget.itemChanged.connect(self.toggle_xsection_visibility)


def xsect_legend_thick_modified_update_views(self, updated_list=None):
    """This is called when the line thickness in the cross-section legend is modified.
    Disconnect signals to xsect list, if they are set, then they are
    reconnected when the list is rebuilt"""
    self.XSectionTreeWidget.itemChanged.disconnect()
    for uid in updated_list:
        """Case for line_thick changed"""
        self.change_actor_line_thick(uid=uid, collection="xsect_coll")
    """Re-connect signals."""
    self.XSectionTreeWidget.itemChanged.connect(self.toggle_xsection_visibility)


def xsect_legend_opacity_modified_update_views(self, updated_list=None):
    """This is called when the opacity in the image legend is modified.
    Disconnect signals to image tree, if they are set, to avoid a nasty loop
    that disrupts the trees, then they are reconnected when the trees are rebuilt"""
    self.XSectionTreeWidget.itemChanged.disconnect()
    for uid in updated_list:
        """Case for color changed"""
        self.change_actor_opacity(uid=uid, collection="xsect_coll")
    """Re-connect signals."""
    self.XSectionTreeWidget.itemChanged.connect(self.toggle_xsect_visibility)
