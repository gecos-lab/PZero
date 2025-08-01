"""dem2vtk.py
PZero© Andrea Bistacchi"""

import os

from uuid import uuid4

from copy import deepcopy

from rioxarray import open_rasterio as rx_open_rasterio

from numpy import meshgrid as np_meshgrid

from pyvista import StructuredGrid as pv_StructuredGrid

from pzero.collections.dom_collection import DomCollection
from pzero.collections.fluid_collection import FluidCollection
from pzero.entities_factory import DEM


def dem2vtk(self=None, in_file_name=None, collection=None):
    """Import and add a DEM structured grid to the dom_coll of the project.
    <self> is the calling ProjectWindow() instance."""
    # Read raster file format (geotiff) with xarray and rasterio and create DEM structured grid.
    # Helpful: http://xarray.pydata.org/en/stable/auto_gallery/plot_rasterio.html
    # https://github.com/pyvista/pyvista-support/issues/205, thanks to Bane Sullivan
    data = rx_open_rasterio(in_file_name)
    values = data.values[0]
    # nans = values == data.nodatavals
    # if np_any(nans):
    #     values[nans] = np_nan
    xx, yy = np_meshgrid(data["x"], data["y"])
    zz = values.reshape(xx.shape)
    # Convert to DEM() instance.
    curr_obj = DEM()
    temp_obj = pv_StructuredGrid(xx, yy, zz)
    temp_obj["elevation"] = zz.ravel(order="F")
    curr_obj.ShallowCopy(temp_obj)
    curr_obj.Modified()
    # Create dictionary.
    if collection == "DEMs and DOMs":
        curr_obj_attributes = deepcopy(DomCollection().entity_dict)
        curr_obj_attributes["uid"] = str(uuid4())
        curr_obj_attributes["name"] = os.path.basename(in_file_name)
        curr_obj_attributes["topology"] = "DEM"
        curr_obj_attributes["texture_uids"] = []
        curr_obj_attributes["properties_names"] = ["elevation"]
        curr_obj_attributes["properties_components"] = [1]
        curr_obj_attributes["vtk_obj"] = curr_obj
        # Add to entity collection.
        self.dom_coll.add_entity_from_dict(entity_dict=curr_obj_attributes)
    elif collection == "Fluid contacts":
        curr_obj_attributes = deepcopy(FluidCollection.entity_dict)
        curr_obj_attributes["uid"] = str(uuid4())
        curr_obj_attributes["name"] = os.path.basename(in_file_name)
        curr_obj_attributes["role"] = "raster"
        curr_obj_attributes["texture_uids"] = []
        curr_obj_attributes["properties_names"] = ["elevation"]
        curr_obj_attributes["properties_components"] = [1]
        curr_obj_attributes["vtk_obj"] = curr_obj
        # Add to entity collection.
        self.fluid_coll.add_entity_from_dict(entity_dict=curr_obj_attributes)
    # Cleaning.
    del curr_obj
    del curr_obj_attributes
