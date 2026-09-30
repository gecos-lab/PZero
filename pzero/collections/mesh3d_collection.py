"""mesh3d_collection.py
PZero© Andrea Bistacchi"""

from .DIM_collection import DIMCollection
from pandas import DataFrame as pd_DataFrame
from pandas import concat as pd_concat


class Mesh3DCollection(DIMCollection):
    """Collection for all mesh entities and their metadata."""

    def __init__(self, parent=None, *args, **kwargs):
        super(Mesh3DCollection, self).__init__(parent, *args, **kwargs)
        # Initialize properties required by the abstract superclass.
        self.entity_dict = {
            "uid": "",
            "name": "undef",
            "scenario": "undef",
            "parent_uid": "",  # this is the uid of the cross section for "XsVertexSet", "XsPolyLine", and "XsImage", empty for all others
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
            "parent_uid": str,
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

    def add_entity_from_dict(self, entity_dict=None, color=None):
        uid = super().add_entity_from_dict(entity_dict=entity_dict, color=color)
        self.parent.legend.update_widget(self.parent)
        return uid

    def remove_entity(self, uid: str = None) -> str:
        removed_uid = super().remove_entity(uid=uid)
        if removed_uid is not None:
            legend_df = self.parent.others_legend_df
            legend_df.drop(legend_df[legend_df["uid"] == removed_uid].index, inplace=True)
            self.parent.legend.update_widget(self.parent)
        return removed_uid

    def attr_modified_update_legend_table(self):
        """Keep mesh names in the legend in step with edits in the mesh table."""
        self.parent.legend.update_widget(self.parent)

    def get_uid_legend(self, uid: str = None) -> dict:
        """Get legend for a particular uid."""
        legend_df = self.parent.others_legend_df
        mesh_rows = legend_df[legend_df["other_collection"] == "Mesh3D"]
        uid_rows = mesh_rows[mesh_rows["uid"] == uid]
        if not uid_rows.empty:
            return uid_rows.iloc[0].to_dict()
        return mesh_rows[mesh_rows["uid"] == ""].iloc[0].to_dict()

    def set_uid_legend(
        self,
        uid: str = None,
        color_R: float = None,
        color_G: float = None,
        color_B: float = None,
        line_thick: float = None,
        point_size: float = None,
        opacity: float = None,
    ):
        """Store an independent legend for one mesh, based on the default row."""
        if uid not in self.get_uids:
            return
        legend_df = self.parent.others_legend_df
        mask = (legend_df["other_collection"] == "Mesh3D") & (legend_df["uid"] == uid)
        if not mask.any():
            row = self.get_uid_legend(uid).copy()
            row["uid"] = uid
            self.parent.others_legend_df = pd_concat(
                [legend_df, pd_DataFrame([row])], ignore_index=True
            )
            legend_df = self.parent.others_legend_df
            mask = (legend_df["other_collection"] == "Mesh3D") & (legend_df["uid"] == uid)
        for field, value in (
            ("color_R", color_R),
            ("color_G", color_G),
            ("color_B", color_B),
            ("line_thick", line_thick),
            ("point_size", point_size),
            ("opacity", opacity),
        ):
            if value is not None:
                legend_df.loc[mask, field] = value
