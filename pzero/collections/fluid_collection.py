"""fluid_collection.py
PZero© Andrea Bistacchi"""

from .GFB_collection import GFBCollection


class FluidCollection(GFBCollection):
    """Collection for all fluid entities and their metadata."""

    def __init__(self, parent=None, *args, **kwargs):
        super(FluidCollection, self).__init__(parent, *args, **kwargs)
        # Initialize properties required by the abstract superclass.
        self.valid_roles = [
            "undef",
            "top",
            "base",
            "seal",
        ]

        self.collection_name = "fluid_coll"

        self.default_sequence = "fluid_0"

        self.initialize_df()
