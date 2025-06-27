"""background_collection.py
PZero© Andrea Bistacchi"""

from .GFB_collection import GFBCollection


class BackgroundCollection(GFBCollection):
    """Collection for all background entities and their metadata."""

    def __init__(self, parent=None, *args, **kwargs):
        super(BackgroundCollection, self).__init__(parent, *args, **kwargs)
        # Initialize properties required by the abstract superclass.
        self.valid_roles = [
            "undef",
            "annotations",
            "imported",
        ]

        self.collection_name = "backgrnd_coll"

        self.default_sequence = "back_0"

        self.initialize_df()
