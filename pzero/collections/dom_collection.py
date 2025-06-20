"""dom_collection.py
PZero© Andrea Bistacchi"""

from uuid import uuid4

from numpy import set_printoptions as np_set_printoptions

from pandas import set_option as pd_set_option

from .DIM_collection import DIMCollection

# Options to print Pandas dataframes in console for testing.
pd_desired_width = 800
pd_max_columns = 20
pd_show_precision = 4
pd_max_colwidth = 80
pd_set_option("display.width", pd_desired_width)
np_set_printoptions(linewidth=pd_desired_width)
pd_set_option("display.max_columns", pd_max_columns)
pd_set_option("display.precision", pd_show_precision)
pd_set_option("display.max_colwidth", pd_max_colwidth)


class DomCollection(DIMCollection):
    """Collection for all DOM entities and their metadata."""

    def __init__(self, parent=None, *args, **kwargs):
        super(DomCollection, self).__init__(parent, *args, **kwargs)
        # Initialize properties required by the abstract superclass.
        self.valid_topologies = ["DEM", "TSDom", "PCDom"]

        self.collection_name = "dom"

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
            self.signals.metadata_modified.emit([dom_uid])

    def remove_map_texture_from_dom(self, dom_uid=None, map_image_uid=None):
        """Remove a map texture from a DOM."""
        row = self.df[self.df["uid"] == dom_uid].index.values[0]
        if map_image_uid in self.df.at[row, "texture_uids"]:
            self.get_uid_vtk_obj(dom_uid).remove_texture(map_image_uid=map_image_uid)
            self.df.at[row, "texture_uids"].remove(map_image_uid)
            self.signals.data_keys_modified.emit([dom_uid])
            # self.signals.metadata_modified.emit([dom_uid])

    def set_active_texture_on_dom(self, dom_uid=None, map_image_uid=None):
        """Set active texture on a DOM."""
        self.get_uid_vtk_obj(dom_uid).set_active_texture(map_image_uid=map_image_uid)
