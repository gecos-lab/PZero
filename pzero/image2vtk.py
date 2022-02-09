"""image2vtk.py
PZero© Andrea Bistacchi"""

from copy import deepcopy
import uuid
import os
from vtk.util import numpy_support
from .entities_factory import MapImage
from .image_collection import ImageCollection
import numpy as np
import rasterio as rio
import rasterio.plot as rio_plt


def geo_image2vtk(self=None, in_file_name=None):
    """Import and add an image to the imaage collection
    <self> is the calling ProjectWindow() instance."""
    try:
        """Open raster file format (geotiff or other accepted by GDAL) with rasterio.
        The image is not read here but will be read afterwards with geo_image.read()
        http://xarray.pydata.org/en/stable/io.html#rasterio
        http://www-2.unipv.it/compmech/seminars/group/VTK-VMTK.pdf"""
        geo_image = rio.open(in_file_name)
        """Georeferencing variables as read by rasterio."""
        img_width_px = geo_image.width
        img_height_px = geo_image.height
        img_x_min = rio_plt.plotting_extent(geo_image)[0]
        img_x_max = rio_plt.plotting_extent(geo_image)[1]
        img_y_min = rio_plt.plotting_extent(geo_image)[2]
        img_y_max = rio_plt.plotting_extent(geo_image)[3]
        """Read the image and convert to vtk array.
        Deep copy used since the image is read now from file.
        DO NOT specify the array type as e.g. in array_type=vtk.VTK_CHAR"""
        if geo_image.count == 1:
            vtk_array = numpy_support.numpy_to_vtk(geo_image.read(1).ravel(), deep=True)
            vtk_array.SetName('greyscale')
        elif geo_image.count == 3:
            vtk_r_band = geo_image.read(1)
            vtk_g_band = geo_image.read(2)
            vtk_b_band = geo_image.read(3)
            numpy_array = np.dstack((vtk_r_band, vtk_g_band, vtk_b_band))
            # vtk_array = numpy_support.numpy_to_vtk(np.flip(numpy_array.swapaxes(0, 1), axis=1).reshape((-1, 3), order='F'), deep=True)
            vtk_array = numpy_support.numpy_to_vtk(numpy_array.swapaxes(0, 1).reshape((-1, 3), order='F'), deep=True)
            vtk_array.SetName('RGB')
        else:
            return
        """Create MapImage entity (inherits from vtk.vtkImageData) and then set all data."""
        vtk_image = MapImage()
        """With the following dimensions, origin and spacing, image coords 0,0 are at upper-left and image coords grow along x and -y."""
        vtk_image.SetDimensions(img_width_px, img_height_px, 1)
        vtk_image.SetSpacing([(img_x_max - img_x_min) / (img_width_px + 1), (img_y_min - img_y_max) / (img_height_px + 1), 1])
        vtk_image.SetOrigin([img_x_min, img_y_max, 0])
        """Add the vtk array image data"""
        vtk_image.GetPointData().AddArray(vtk_array)
        if geo_image.count == 1:
            vtk_image.GetPointData().SetActiveScalars('greyscale')
        elif geo_image.count == 3:
            vtk_image.GetPointData().SetActiveScalars('RGB')
        """Create dictionary."""
        curr_obj_dict = deepcopy(ImageCollection.image_entity_dict)
        curr_obj_dict['uid'] = str(uuid.uuid4())
        curr_obj_dict['name'] = os.path.basename(in_file_name)
        curr_obj_dict['image_type'] = "MapImage"
        if geo_image.count == 1:
            curr_obj_dict['bands_n'] = int(1)
            curr_obj_dict['bands_types'] = [vtk_image.GetScalarType()]
        elif geo_image.count == 3:
            curr_obj_dict['bands_n'] = int(3)
            curr_obj_dict['bands_types'] = [vtk_image.GetScalarType(), vtk_image.GetScalarType(), vtk_image.GetScalarType()]
        curr_obj_dict['vtk_obj'] = vtk_image
        """Add to entity collection."""
        self.image_coll.add_entity_from_dict(entity_dict=curr_obj_dict)
        """Cleaning (probably not necessary)."""
        del curr_obj_dict
        del vtk_image
    except:
        self.TextTerminal.appendPlainText("Image file not recognized ERROR.")
