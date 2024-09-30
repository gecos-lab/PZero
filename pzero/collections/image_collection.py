"""image_collection.py
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

        self.collection_name = 'image'

        self.default_colormap = 'gray'

        self.initialize_df()

    # =================================== Obligatory methods ===========================================

    def get_uid_legend(self, uid: str = None) -> dict:
        """Get legend for a particular uid."""
        legend_dict = self.parent.others_legend_df.loc[
            self.parent.others_legend_df["other_collection"] == "Image"
        ].to_dict("records")
        return legend_dict[0]