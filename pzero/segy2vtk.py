"""segy2vtk.py
PZero© Andrea Bistacchi"""

import os
from copy import deepcopy
import uuid
import vtk
from .entities_factory import Seismics
from .mesh3d_collection import Mesh3DCollection

"""Very basic SEG-Y importer. TO BE IMPROVED IN THE FUTURE."""

def segy2vtk(self=None, in_file_name=None):
    """Import and add a SEGY seismics cube to the mesh3d_coll of the project.
    <self> is the calling ProjectWindow() instance."""
    try:
        """Do not use the StructuredGridOff() option, this causes problems.
        https://vtk.org/doc/nightly/html/classvtkSegYReader.html#aa1e0a8e126958a91b3106159a2680041"""
        curr_object = Seismics()
        segy_reader = vtk.vtkSegYReader()
        segy_reader.SetFileName(in_file_name)
        segy_reader.Update()
        curr_object.ShallowCopy(segy_reader.GetOutput())
        curr_object.Modified()
        """Create dictionary."""
        curr_obj_attributes = deepcopy(Mesh3DCollection.mesh3d_entity_type_dict)
        curr_obj_attributes['uid'] = str(uuid.uuid4())
        curr_obj_attributes['name'] = os.path.basename(in_file_name)
        curr_obj_attributes['mesh3d_type'] = "Seismics"
        curr_obj_attributes['properties_names'] = curr_object.point_data_keys
        curr_obj_attributes['properties_components'] = curr_object.point_data_components
        curr_obj_attributes['vtk_obj'] = curr_object
        """Add to entity collection."""
        self.mesh3d_coll.add_entity_from_dict(entity_dict=curr_obj_attributes)
        """Cleaning."""
        del curr_object
        del curr_obj_attributes
    except:
        self.TextTerminal.appendPlainText("SEGY file not recognized ERROR.")
