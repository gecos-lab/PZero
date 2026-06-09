"""geological_collection.py
PZero© Andrea Bistacchi"""

from .GFB_collection import GFBCollection


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
            "TMU",
            "TSU",
            "SU",
            "IU",
            "SZ",
            "formation",
        ]

        self.collection_name = "geol_coll"

        self.default_sequence = "strati_0"

        self.initialize_df()
