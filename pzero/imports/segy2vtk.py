"""segy2vtk.py
PZero© Andrea Bistacchi"""

import os
from copy import deepcopy

import pyvista as pv

from vtk import vtkSegYReader
from pzero.collections.mesh3d_collection import Mesh3DCollection
from pzero.entities_factory import Seismics
import uuid

def segy2vtk(self, in_file_name):
    # Create an instance of the Seismics class
    seismic = Seismics()

    # Process the SEG-Y file and load the data into the Seismics instance
    seismic.process_segy_file(in_file_name)

    # Create a temporary Mesh3DCollection instance to get the entity dictionary
    temp_collection = Mesh3DCollection()
    curr_obj_attributes = deepcopy(temp_collection.entity_dict)
    
    # Set the attributes
    curr_obj_attributes["uid"] = str(uuid.uuid4())
    curr_obj_attributes["name"] = os.path.basename(in_file_name)
    curr_obj_attributes["topology"] = "Voxet"  # Changed from mesh3d_type to topology to match entity_dict
    curr_obj_attributes["properties_names"] = seismic.point_data_keys
    curr_obj_attributes["properties_components"] = seismic.point_data_components
    curr_obj_attributes["vtk_obj"] = seismic

    # Add to entity collection
    self.mesh3d_coll.add_entity_from_dict(entity_dict=curr_obj_attributes)


    # mesh3d_coll = Mesh3DCollection()  # Or get it from the project context

    # Prepare attributes dictionary (similar to old code)
    # curr_obj_attributes = {
    #     "uid": os.path.basename(in_file_name),
    #     "name": os.path.basename(in_file_name),
    #     "image_type": "Seismics",
    #     "properties_names": seismic.point_data_keys,
    #     "properties_components": seismic.point_data_components,
    #     "vtk_obj": seismic,
    #     # Add other necessary attributes
    # }

    # Add the seismic data to the mesh3d_collection
    # mesh3d_coll.add_entity_from_dict(entity_dict=curr_obj_attributes)