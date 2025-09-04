"""mesh3d_collection.py
PZero© Andrea Bistacchi"""

from .DIM_collection import DIMCollection


class Mesh3DCollection(DIMCollection):
    """Collection for all mesh entities and their metadata."""

    def __init__(self, parent=None, *args, **kwargs):
        super(Mesh3DCollection, self).__init__(parent, *args, **kwargs)
        # Initialize properties required by the abstract superclass.
        self.entity_dict = {
            "uid": "",
            "name": "undef",
            "scenario": "undef",
            "x_section": "",  # this is the uid of the cross section for "XsVertexSet", "XsPolyLine", and "XsImage", empty for all others
            "topology": "undef",
            "vtk_obj": None,
            "properties_names": [],
            "properties_components": [],
            "properties_types": [],
        }

        self.entity_dict_types = {
            "uid": str,
            "name": str,
            "scenario": str,
            "x_section": str,
            "topology": str,
            "vtk_obj": object,
            "properties_names": list,
            "properties_components": list,
            "properties_types": list,
        }

        self.valid_topologies = ["TetraSolid", "Voxet", "XsVoxet"]

        self.collection_name = "mesh3d_coll"

        self.default_colormap = "rainbow"

        self.initialize_df()

    # =================================== Obligatory methods ===========================================

    def get_uid_legend(self, uid: str = None) -> dict:
        """Get legend for a particular uid."""
        legend_dict = self.parent.others_legend_df.loc[
            self.parent.others_legend_df["other_collection"] == "Mesh3D"
        ].to_dict("records")
        return legend_dict[0]
