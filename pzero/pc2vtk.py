"""pc2vtk.py
PZero© Gabriele Benedetti
--------

Convert point cloud data (txt, csv,xyz, las ...) in vtk objects

"""


import numpy as np
import os
from copy import deepcopy
import uuid
from .entities_factory import PCDom
from .dom_collection import DomCollection
import pyvista as pv
import xarray as xr



def pc2vtk(self, in_file_name, header_ind = 1, delimiter = ','):

    self.TextTerminal.appendPlainText(f'Reading file {in_file_name}')

    input_data = np.loadtxt(fname = in_file_name, delimiter = delimiter, skiprows = header_ind)
    data_dict = {'x': input_data[:,0], 'y': input_data[:,1], 'z':input_data[:,2]}
    self.TextTerminal.appendPlainText(f'{data_dict}')
    values = np.asarray(input_data)
    xx, yy, zz = np.meshgrid(data_dict['x'], data_dict['y'],data_dict['z'])
    #print(xx,yy,zz)
    """Convert to PCDom() instance."""
    curr_obj = PCDom()
    temp_obj = pv.StructuredGrid(xx, yy, zz)
    temp_obj['elevation'] = zz.ravel(order='F')
    #print(temp_obj)
    curr_obj.ShallowCopy(temp_obj)
    curr_obj.Modified()
    print(curr_obj)
    """Create dictionary."""
    curr_obj_attributes = deepcopy(DomCollection.dom_entity_dict)
    curr_obj_attributes['uid'] = str(uuid.uuid4())
    curr_obj_attributes['name'] = os.path.basename(in_file_name)
    curr_obj_attributes['dom_type'] = "PCDom"
    curr_obj_attributes['texture_uids'] = []
    curr_obj_attributes['properties_names'] = ["elevation"]
    curr_obj_attributes['properties_components'] = [1]
    curr_obj_attributes['vtk_obj'] = curr_obj
    #print(curr_obj_attributes)
    """Add to entity collection."""
    self.dom_coll.add_entity_from_dict(entity_dict=curr_obj_attributes)
    self.TextTerminal.appendPlainText(f'Successfully imported {in_file_name}')
    """Cleaning."""
    del curr_obj
    del curr_obj_attributes
