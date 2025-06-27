"""image_collection.py
PZero© Andrea Bistacchi"""

from .DIM_collection import DIMCollection


class ImageCollection(DIMCollection):
    """Collection for all image entities and their metadata."""

    def __init__(self, parent=None, *args, **kwargs):
        super(ImageCollection, self).__init__(parent, *args, **kwargs)
        # Initialize properties required by the abstract superclass.
        self.valid_topologies = [
            "MapImage",
            "XsImage",
            "Seismics",
            "Image3D",
        ]

        self.collection_name = "image_coll"

        self.default_colormap = "gray"

        self.initialize_df()

    # =================================== Obligatory methods ===========================================

    def get_uid_legend(self, uid: str = None) -> dict:
        """Get legend for a particular uid."""
        legend_dict = self.parent.others_legend_df.loc[
            self.parent.others_legend_df["other_collection"] == "Image"
        ].to_dict("records")
        return legend_dict[0]
