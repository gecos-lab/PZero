"""segy2vtk.py
PZero© Andrea Bistacchi"""

import os
from copy import deepcopy

from vtk import vtkSegYReader
from pzero.collections.image_collection import ImageCollection
from pzero.entities_factory import Seismics

def segy2vtk(self=None, in_file_name=None):
    """Import and add a SEGY seismics cube to the mesh3d_coll of the project.
    <self> is the calling ProjectWindow() instance."""
    try:
        curr_object = Seismics()  # Create a Seismics object
        segy_reader = vtkSegYReader()
        segy_reader.SetFileName(in_file_name)
        segy_reader.Update()
        curr_object.ShallowCopy(segy_reader.GetOutput())
        curr_object.Modified()

        # Create dictionary with uid instead of uuid
        curr_obj_attributes = {
            "uid": os.path.basename(in_file_name),  # Using file name as uid for simplicity
            "name": os.path.basename(in_file_name),
            "image_type": "Seismics",  # Updated to align with other parts of your code
            "properties_names": curr_object.point_data_keys,
            "properties_components": curr_object.point_data_components,
            "vtk_obj": curr_object,
            # Other attributes can be added as needed
        }

        # Add to image collection
        self.image_coll.add_entity_from_dict(entity_dict=curr_obj_attributes)

        # Cleaning up
        del curr_object
        del curr_obj_attributes
    except Exception as e:
        self.TextTerminal.appendPlainText(f"SEGY file not recognized ERROR: {str(e)}")
