"""dem2vtk.py
PZero© Andrea Bistacchi"""

import os
from copy import deepcopy
import uuid
from .entities_factory import DEM
from .dom_collection import DomCollection
from .fluid_collection import FluidsCollection
import pyvista as pv
import xarray as xr
import numpy as np


def dem2vtk(self=None, in_file_name=None,collection=None):
    """Import and add a DEM structured grid to the dom_coll of the project.
    <self> is the calling ProjectWindow() instance."""
    """Read raster file format (geotiff) with xarray and rasterio and create DEM structured grid.
    Helpful: http://xarray.pydata.org/en/stable/auto_gallery/plot_rasterio.html
    https://github.com/pyvista/pyvista-support/issues/205, thanks to Bane Sullivan"""
    data = xr.open_rasterio(in_file_name)
    values = np.asarray(data)
    nans = values == data.nodatavals
    if np.any(nans):
        values[nans] = np.nan
    xx, yy = np.meshgrid(data['x'], data['y'])
    zz = values.reshape(xx.shape)
    print(zz)
    """Convert to DEM() instance."""
    curr_obj = DEM()
    temp_obj = pv.StructuredGrid(xx, yy, zz)
    temp_obj['elevation'] = zz.ravel(order='F')
    curr_obj.ShallowCopy(temp_obj)
    curr_obj.Modified()
    """Create dictionary."""
    if collection == 'DEMs and DOMs':
        curr_obj_attributes = deepcopy(DomCollection.dom_entity_dict)
        curr_obj_attributes['uid'] = str(uuid.uuid4())
        curr_obj_attributes['name'] = os.path.basename(in_file_name)
        curr_obj_attributes['dom_type'] = "DEM"
        curr_obj_attributes['texture_uids'] = []
        curr_obj_attributes['properties_names'] = ["elevation"]
        curr_obj_attributes['properties_components'] = [1]
        curr_obj_attributes['vtk_obj'] = curr_obj
        """Add to entity collection."""
        self.dom_coll.add_entity_from_dict(entity_dict=curr_obj_attributes)
    elif collection == 'Fluid contacts':
        curr_obj_attributes = deepcopy(FluidsCollection.fluid_entity_dict)
        curr_obj_attributes['uid'] = str(uuid.uuid4())
        curr_obj_attributes['name'] = os.path.basename(in_file_name)
        curr_obj_attributes['fluid_type'] = "raster"
        curr_obj_attributes['texture_uids'] = []
        curr_obj_attributes['properties_names'] = ["elevation"]
        curr_obj_attributes['properties_components'] = [1]
        curr_obj_attributes['vtk_obj'] = curr_obj
        """Add to entity collection."""
        self.fluids_coll.add_entity_from_dict(entity_dict=curr_obj_attributes)
    """Cleaning."""
    del curr_obj
    del curr_obj_attributes

