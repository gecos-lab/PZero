"""geological_collection.py
PZero© Andrea Bistacchi"""

from numpy import set_printoptions as np_set_printoptions

from pandas import set_option as pd_set_option

from .GFB_collection import GFBCollection

# Options to print Pandas dataframes in console when testing.
pd_desired_width = 800
pd_max_columns = 20
pd_show_precision = 4
pd_max_colwidth = 80
pd_set_option("display.width", pd_desired_width)
np_set_printoptions(linewidth=pd_desired_width)
pd_set_option("display.max_columns", pd_max_columns)
pd_set_option("display.precision", pd_show_precision)
pd_set_option("display.max_colwidth", pd_max_colwidth)


class GeologicalCollection(GFBCollection):
    """Collection for all geological entities and their metadata."""

    def __init__(self, parent=None, *args, **kwargs):
        super(GeologicalCollection, self).__init__(parent, *args, **kwargs)
        # Initialize properties required by the abstract superclass.
        self.valid_roles = [
            "undef",
            "fault",
            "tectonic",
            "intrusive",
            "unconformity",
            "top",
            "base",
            "bedding",
            "foliation",
            "lineation",
            "axial_surface",
            "fold_axis",
            "TM_unit",
            "TS_unit",
            "INT_unit",
            "formation",
        ]

        self.collection_name = "geological"

        self.default_sequence = "strati_0"

        self.initialize_df()
