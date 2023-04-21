"""image2vtk.py
PZero© Andrea Bistacchi"""

from copy import deepcopy
import uuid
import os
from vtkmodules.util import numpy_support
from .entities_factory import MapImage, XsImage
from .image_collection import ImageCollection
from .helper_dialogs import multiple_input_dialog

from numpy import pi as np_pi
from numpy import sin as np_sin
from numpy import cos as np_cos
from numpy import dstack as np_dstack
from numpy import abs as np_abs

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
            vtk_r_property = geo_image.read(1)
            vtk_g_property = geo_image.read(2)
            vtk_b_property = geo_image.read(3)
            numpy_array = np_dstack((vtk_r_property, vtk_g_property, vtk_b_property))
            # vtk_array = numpy_support.numpy_to_vtk(np.flip(numpy_array.swapaxes(0, 1), axis=1).reshape((-1, 3), order='F'), deep=True)
            vtk_array = numpy_support.numpy_to_vtk(numpy_array.swapaxes(0, 1).reshape((-1, 3), order='F'), deep=True)
            vtk_array.SetName('RGB')
        elif geo_image.count == 4:
            vtk_r_property = geo_image.read(1)
            vtk_g_property = geo_image.read(2)
            vtk_b_property = geo_image.read(3)
            vtk_a_property = geo_image.read(4)
            numpy_array = np_dstack((vtk_r_property, vtk_g_property, vtk_b_property,vtk_a_property))
            # vtk_array = numpy_support.numpy_to_vtk(np.flip(numpy_array.swapaxes(0, 1), axis=1).reshape((-1, 3), order='F'), deep=True)
            vtk_array = numpy_support.numpy_to_vtk(numpy_array.swapaxes(0, 1).reshape((-1, 4), order='F'), deep=True)
            vtk_array.SetName('RGB')
        else:
            """ADD OPTION FOR MULTIBAND IMAGES HERE_____________________________"""
            print('Multiband not supported')
            return
        """Create MapImage entity (inherits from vtk.vtkImageData) and then set all data."""
        vtk_image = MapImage()
        """With the following dimensions, origin and spacing, image coords 0,0 are at upper-left and image coords grow along x and -y."""
        vtk_image.SetDimensions(img_width_px, img_height_px, 1)
        vtk_image.SetSpacing([(img_x_max - img_x_min) / (img_width_px + 1),
                              (img_y_min - img_y_max) / (img_height_px + 1),
                              1])
        # vtk_image.SetOrigin([img_x_min, img_y_max, 0])

        vtk_image.SetOrigin([img_x_min-round(img_x_min, -2), img_y_max-round(img_y_min, -2), 0])
        # Re-centering the image. Maybe not the best solution, we should add an option to add re-centering every object
        # using the same translation vector.
        """Add the vtk array image data"""
        vtk_image.GetPointData().AddArray(vtk_array)
        if geo_image.count == 1:
            vtk_image.GetPointData().SetActiveScalars('greyscale')
        elif geo_image.count >= 3:
            vtk_image.GetPointData().SetActiveScalars('RGB')

        """Create dictionary."""
        curr_obj_dict = deepcopy(ImageCollection.image_entity_dict)
        curr_obj_dict['uid'] = str(uuid.uuid4())
        curr_obj_dict['name'] = os.path.basename(in_file_name)
        curr_obj_dict['image_type'] = "MapImage"
        curr_obj_dict['properties_components'] = vtk_image.properties_components
        curr_obj_dict['properties_types'] = vtk_image.properties_types
        if geo_image.count == 1:
            curr_obj_dict['properties_names'] = ['greyscale']
        elif geo_image.count >= 3:
            curr_obj_dict['properties_names'] = ['RGB']
        curr_obj_dict['vtk_obj'] = vtk_image
        """Add to entity collection."""
        self.image_coll.add_entity_from_dict(entity_dict=curr_obj_dict)
        """Cleaning (probably not necessary)."""
        del curr_obj_dict
        del vtk_image
    except:
        self.TextTerminal.appendPlainText("Image file not recognized ERROR.")


def xs_image2vtk(self=None, in_file_name=None, x_section_uid=None):
    """Import and add an image to the imaage collection
    <self> is the calling ProjectWindow() instance."""
    #try:
    """Open raster file format (tiff or other accepted by GDAL) with rasterio.
    The image is not read here but will be read afterwards with xs_image.read()
    http://xarray.pydata.org/en/stable/io.html#rasterio
    http://www-2.unipv.it/compmech/seminars/group/VTK-VMTK.pdf"""
    xs_image = rio.open(in_file_name)
    """Image size as read by rasterio."""
    dim_W = xs_image.width
    dim_Z = xs_image.height
    """Cross-section azimuth"""
    azimuth = self.xsect_coll.get_uid_azimuth(x_section_uid)
    origin_z = self.xsect_coll.get_uid_bottom(x_section_uid)
    width = self.xsect_coll.get_uid_length(x_section_uid)
    height = np_abs(self.xsect_coll.get_uid_top(x_section_uid))-np_abs(self.xsect_coll.get_uid_bottom(x_section_uid))

    """x-section georeferencing dialog"""
    in_dict = {'origin_W': ['Origin W', '0.0'],
               'origin_Z': ['Origin Z', f'{origin_z}'],
               'width': ['width', f'{width}'],
               'height': ['height', f'{height}']}
    out_dict = multiple_input_dialog(title='XSection image georeferencing\n(in XSection reference frame)', input_dict=in_dict)
    if out_dict is None:
        return
    origin_W = float(out_dict['origin_W'])
    origin_Z = float(out_dict['origin_Z'])
    width = float(out_dict['width'])
    height = float(out_dict['height'])
    origin_X, origin_Y = self.xsect_coll.get_XY_from_W(section_uid=x_section_uid, W=origin_W)
    origin = [origin_X, origin_Y, origin_Z]
    print('origin: ', origin)
    spacing_W = width/dim_W
    spacing_Z = height/dim_Z
    print('spacing_W: ', spacing_W)
    print('spacing_Z: ', spacing_Z)
    """The direction matrix is a 3x3 transformation matrix supporting scaling and rotation.
    (double  	e00,
    double  	e01,
    double  	e02,
    double  	e10,
    double  	e11,
    double  	e12,
    double  	e20,
    double  	e21,
    double  	e22)"""
    """CHECK THIS FOR VARIOUS SECTION ORIENTATIONS______________________________________________________________"""
    direction_matrix = [np_sin(azimuth * np_pi / 180), 0, -(np_cos(azimuth * np_pi / 180)),
                        np_cos(azimuth * np_pi / 180), 0, np_sin(azimuth * np_pi / 180),
                        0, 1, 0]
    """Read the image and convert to vtk array.
    Deep copy used since the image is read now from file.
    DO NOT specify the array type as e.g. in array_type=vtk.VTK_CHAR"""
    if xs_image.count == 1:
        vtk_array = numpy_support.numpy_to_vtk(xs_image.read(1).ravel(), deep=True)
        vtk_array.SetName('greyscale')
    elif xs_image.count == 3:
        vtk_r_property = xs_image.read(1)
        vtk_g_property = xs_image.read(2)
        vtk_b_property = xs_image.read(3)
        numpy_array = np_dstack((vtk_r_property, vtk_g_property, vtk_b_property))
        # vtk_array = numpy_support.numpy_to_vtk(np.flip(numpy_array.swapaxes(0, 1), axis=1).reshape((-1, 3), order='F'), deep=True)
        vtk_array = numpy_support.numpy_to_vtk(numpy_array.swapaxes(0, 1).reshape((-1, 3), order='F'), deep=True)
        vtk_array.SetName('RGB')
    else:
        """ADD OPTION FOR MULTIBAND IMAGES HERE_____________________________"""
        return
    """Create vtkImageData with the geometry to fit data"""
    vtk_image = XsImage(x_section_uid=x_section_uid, parent=self)
    vtk_image.SetOrigin(origin)
    vtk_image.SetSpacing([spacing_W, spacing_Z, 0.0])
    vtk_image.SetDimensions([dim_W, dim_Z, 1])
    vtk_image.SetDirectionMatrix(direction_matrix)
    vtk_image.GetPointData().AddArray(vtk_array)
    if xs_image.count == 1:
        vtk_image.GetPointData().SetActiveScalars('greyscale')
    elif xs_image.count == 3:
        vtk_image.GetPointData().SetActiveScalars('RGB')
    print('vtk_image:\n', vtk_image)
    """Create dictionary."""
    curr_obj_dict = deepcopy(ImageCollection.image_entity_dict)
    curr_obj_dict['uid'] = str(uuid.uuid4())
    curr_obj_dict['name'] = os.path.basename(in_file_name)
    curr_obj_dict['image_type'] = "XsImage"
    curr_obj_dict['properties_components'] = vtk_image.properties_components
    curr_obj_dict['properties_types'] = vtk_image.properties_types
    curr_obj_dict['x_section'] = x_section_uid
    if xs_image.count == 1:
        curr_obj_dict['properties_names'] = ['greyscale']
    elif xs_image.count == 3:
        curr_obj_dict['properties_names'] = ['RGB']
    curr_obj_dict['vtk_obj'] = vtk_image
    """Add to entity collection."""
    self.image_coll.add_entity_from_dict(entity_dict=curr_obj_dict)
    """Cleaning (probably not necessary)."""
    del curr_obj_dict
    del vtk_image
    # except:
    #     self.TextTerminal.appendPlainText("Image file not recognized ERROR.")
