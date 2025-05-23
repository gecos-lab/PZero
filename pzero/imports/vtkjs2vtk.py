"""vtkjs2vtk.py
PZero© Andrea Bistacchi"""

from vtk import (
    vtkArchiver,
    vtkJSONDataSetWriter,
    vtkMultiBlockDataSet,
    vtkCompositeDataSet,
    vtkLookupTable,
)
from pandas import DataFrame as pd_DataFrame
from pandas import concat as pd_concat
import os
from ..entities_factory import TriSurf


def vtk2vtkjs(self=None, out_dir_name=None):
    """Exports all entities to vtk.js archives with colors and properties from active legend.
    This preliminary version supports TriSurf entities in the geological collection
    and can be extended to other entity types and collections."""

    # Crete dataframe to store colors
    colors_metadata = []

    # Loop through the geological collection and write one archive for each entity
    for uid in self.geol_coll.df["uid"]:
        if isinstance(self.geol_coll.get_uid_vtk_obj(uid), TriSurf):
            # Create an archiver and a writer
            archiver = vtkArchiver()
            archiver.SetArchiveName(out_dir_name + "/" + uid)
            archiver.OpenArchive()
            writer = vtkJSONDataSetWriter()
            writer.SetArchiver(archiver)
            # write this entity
            vtk_entity = self.geol_coll.get_uid_vtk_obj(uid)
            writer.Write(vtk_entity)
            archiver.CloseArchive()
            # get and write legend in dataframe
            legend = self.geol_coll.get_uid_legend(uid=uid)
            R = legend["color_R"]
            G = legend["color_G"]
            B = legend["color_B"]
            colors_metadata.append({"uid": uid, "color": [R, G, B]})

    # Save the color metadata to a single JSON file
    pd_DataFrame(colors_metadata).to_json(
        out_dir_name + "/colors_metadata.json", orient="records"
    )

    self.print_terminal("All entities exported to vtk.js archive.")
