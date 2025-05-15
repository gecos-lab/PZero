from pandas import DataFrame as pd_DataFrame
from pandas import concat as pd_concat

from pzero.build_and_update.image import *

# Methods used to add, remove, and update actors from the IMAGE collection


def image_added_update_views(self, updated_list=None):
    """This is called when an image is added to the image collection.
    Disconnect signals to image list, if they are set, then they are
    reconnected when the list is rebuilt""" """________________________________________________________________________"""
    self.ImagesTableWidget.itemChanged.disconnect()
    actors_df_new = pd_DataFrame(
        columns=["uid", "actor", "show", "collection", "show_property"]
    )
    for uid in updated_list:
        this_actor = self.show_actor_with_property(
            uid=uid, collection="image_coll", show_property=None, visible=False
        )
        # Old Pandas <= 1.5.3
        # self.actors_df = self.actors_df.append(
        #     {
        #         "uid": uid,
        #         "actor": this_actor,
        #         "show": False,
        #         "collection": "image_coll",
        #         "show_property": None,
        #     },
        #     ignore_index=True,
        # )
        # actors_df_new = actors_df_new.append(
        #     {
        #         "uid": uid,
        #         "actor": this_actor,
        #         "show": False,
        #         "collection": "image_coll",
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
                            "collection": "image_coll",
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
                            "collection": "image_coll",
                            "show_property": None,
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )
        update_image_list_added(self, actors_df_new)
    """Re-connect signals."""
    self.ImagesTableWidget.itemChanged.connect(self.toggle_image_visibility)


def image_removed_update_views(self, updated_list=None):
    """This is called when an image is removed from the image collection.
    Disconnect signals to image list, if they are set, then they are
    reconnected when the list is rebuilt""" """________________________________________________________________________"""
    self.ImagesTableWidget.itemChanged.disconnect()
    for uid in updated_list:
        self.remove_actor_in_view(uid=uid)
        update_image_list_removed(self, removed_list=updated_list)
    """Re-connect signals."""
    self.ImagesTableWidget.itemChanged.connect(self.toggle_image_visibility)


def image_metadata_modified_update_views(self, updated_list=None):
    """This is called when the image metadata are modified.
    Disconnect signals to image list, if they are set, then they are
    reconnected when the list is rebuilt""" """________________________________________________________________________"""
    self.ImagesTableWidget.itemChanged.disconnect()
    for uid in updated_list:
        """Case for entities modified"""
        create_image_list(self)
    """Re-connect signals."""
    self.ImagesTableWidget.itemChanged.connect(self.toggle_image_visibility)


def image_legend_opacity_modified_update_views(self, updated_list=None):
    """This is called when the opacity in the image legend is modified.
    Disconnect signals to image tree, if they are set, to avoid a nasty loop
    that disrupts the trees, then they are reconnected when the trees are rebuilt"""
    self.ImagesTableWidget.itemChanged.disconnect()
    for uid in updated_list:
        """Case for color changed"""
        self.change_actor_opacity(uid=uid, collection="image_coll")
    """Re-connect signals."""
    self.ImagesTableWidget.itemChanged.connect(self.toggle_image_visibility)
