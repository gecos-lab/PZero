"""dom_collection.py
PZero© Andrea Bistacchi"""

from .DIM_collection import DIMCollection


class DomCollection(DIMCollection):
    """Collection for all DOM entities and their metadata."""

    def __init__(self, parent=None, *args, **kwargs):
        super(DomCollection, self).__init__(parent, *args, **kwargs)
        # Initialize properties required by the abstract superclass.
        self.valid_topologies = ["DEM", "TSDom", "PCDom"]

        self.collection_name = "dom_coll"

        self.default_colormap = "terrain"

        self.initialize_df()

    # =================================== Obligatory methods ===========================================

    def get_uid_legend(self, uid: str = None) -> dict:
        """Get legend for a particular uid."""
        legend_dict = self.parent.others_legend_df.loc[
            self.parent.others_legend_df["other_collection"] == "DOM"
        ].to_dict("records")
        return legend_dict[0]

    # =================================== Additional methods ===========================================

    def get_uid_texture_uids(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df["uid"] == uid, "texture_uids"].values[0]

    def set_uid_texture_uids(self, uid=None, texture_uids=None):
        """Set value(s) stored in dataframe (as pointer) from uid.."""
        self.df.loc[self.df["uid"] == uid, "texture_uids"] = texture_uids

    def add_map_texture_to_dom(self, dom_uid=None, map_image_uid=None):
        """Add a map texture to a DOM."""
        row = self.df[self.df["uid"] == dom_uid].index.values[0]
        if map_image_uid not in self.df.at[row, "texture_uids"]:
            self.get_uid_vtk_obj(dom_uid).add_texture(
                map_image=self.parent.image_coll.get_uid_vtk_obj(map_image_uid),
                map_image_uid=map_image_uid,
            )
            self.df.at[row, "texture_uids"].append(map_image_uid)
            self.parent.signals.metadata_modified.emit([dom_uid], self)

    def remove_map_texture_from_dom(self, dom_uid=None, map_image_uid=None):
        """Remove a map texture from a DOM."""
        row = self.df[self.df["uid"] == dom_uid].index.values[0]
        if map_image_uid in self.df.at[row, "texture_uids"]:
            self.get_uid_vtk_obj(dom_uid).remove_texture(map_image_uid=map_image_uid)
            self.df.at[row, "texture_uids"].remove(map_image_uid)
            self.parent.signals.data_keys_removed.emit([dom_uid], self)
            # self.parent.signals.metadata_modified.emit([dom_uid], self)

    def set_active_texture_on_dom(self, dom_uid=None, map_image_uid=None):
        """Set active texture on a DOM."""
        self.get_uid_vtk_obj(dom_uid).set_active_texture(map_image_uid=map_image_uid)
