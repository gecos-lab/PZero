"""image2vtk.py
PZero© Andrea Bistacchi"""

import os

from uuid import uuid4

from copy import deepcopy

from rasterio import open as rio_open
import rasterio.plot as rio_plt

from numpy import abs as np_abs
from numpy import cos as np_cos
from numpy import dstack as np_dstack
from numpy import pi as np_pi
from numpy import sin as np_sin
from numpy import nan_to_num as np_nan_to_num
from numpy import uint8 as np_uint8

from vtkmodules.util import numpy_support

from pzero.collections.image_collection import ImageCollection
from pzero.entities_factory import MapImage, XsImage
from pzero.helpers.helper_dialogs import multiple_input_dialog


def image_file_to_vtk(self=None, rio_image=None):
    """Generic function used to read an image from a rasterio image object and convert it to a VTK array."""
    # Deep copy used since the image is read now from file.
    # DO NOT specify the array type as e.g. in array_type=vtk.VTK_CHAR
    n_bands = rio_image.count

    if n_bands == 1 or n_bands == 2:
        # Greyscale or Greyscale with alpha channel
        vtk_array = numpy_support.numpy_to_vtk(rio_image.read(1).ravel(), deep=True)
        prop_name = "greyscale"
    elif n_bands == 3 or n_bands == 4:
        # RGB or RGBA (RGB with alpha channel)
        vtk_r_property = rio_image.read(1)
        vtk_g_property = rio_image.read(2)
        vtk_b_property = rio_image.read(3)
        numpy_array = np_dstack((vtk_r_property, vtk_g_property, vtk_b_property))
        vtk_array = numpy_support.numpy_to_vtk(
            numpy_array.swapaxes(0, 1).reshape((-1, 3), order="F"), deep=True
        )
        prop_name = "RGB"
    # elif n_bands == 4:
    #     # RGBA - not yet supported, so we just drop the alpha channel in the previous case --------------------------
    #     vtk_r_property = rio_image.read(1)
    #     vtk_g_property = rio_image.read(2)
    #     vtk_b_property = rio_image.read(3)
    #     vtk_a_property = rio_image.read(4)
    #     numpy_array = np_dstack(
    #         (vtk_r_property, vtk_g_property, vtk_b_property, vtk_a_property)
    #     )
    #     vtk_array = numpy_support.numpy_to_vtk(
    #         numpy_array.swapaxes(0, 1).reshape((-1, 4), order="F"), deep=True
    #     )
    #     vtk_array.SetName("RGBA")
    #     prop_name = "RGBA"
    else:
        # MULTIBAND - not yet supported, so we just return None -------------------------------------------------------
        self.print_terminal("Multiband not supported")
        vtk_array = None
        prop_name = None
    if vtk_array:
        vtk_array.SetName(prop_name)
        return vtk_array


def geo_image2vtk(self=None, in_file_name=None):
    """Import and add an image to the imaage collection
    <self> is the calling ProjectWindow() instance."""
    try:
        # Open a georeferenced raster file (geotiff or other accepted by GDAL) with rasterio.
        # The image is not read here but will be read afterward with rio_image.read()
        # http://xarray.pydata.org/en/stable/io.html#rasterio
        # http://www-2.unipv.it/compmech/seminars/group/VTK-VMTK.pdf
        rio_image = rio_open(in_file_name)

        # Image size as read by rasterio
        img_width_px = rio_image.width
        img_height_px = rio_image.height

        # Georeferencing variables as read by rasterio
        img_x_min = rio_plt.plotting_extent(rio_image)[0]
        img_x_max = rio_plt.plotting_extent(rio_image)[1]
        img_y_min = rio_plt.plotting_extent(rio_image)[2]
        img_y_max = rio_plt.plotting_extent(rio_image)[3]

        spacing_X = (img_x_max - img_x_min) / (img_width_px + 1)
        spacing_Y = (img_y_min - img_y_max) / (img_height_px + 1)

        # Read the image and convert to vtk array.
        vtk_array = image_file_to_vtk(self=self, rio_image=rio_image)

        # Create MapImage entity (inherits from vtk.vtkImageData) and then set all data.
        # Recall that image coords 0,0 are at upper-left and image coords grow along x and -y.
        map_image = MapImage()
        map_image.SetOrigin([img_x_min, img_y_max, 0])
        map_image.SetSpacing([spacing_X, spacing_Y, 1])  # 1 or 0.0 here?
        map_image.SetDimensions(img_width_px, img_height_px, 1)
        map_image.GetPointData().AddArray(vtk_array)
        map_image.GetPointData().SetActiveScalars(vtk_array.GetName())

        # Create dictionary
        curr_obj_dict = {
            "uid": str(uuid4()),
            "name": os.path.basename(in_file_name),
            "topology": "MapImage",
            "x_section": None,
            "vtk_obj": map_image,
            "properties_components": map_image.properties_components,
            "properties_types": map_image.properties_types,
            "properties_names": [vtk_array.GetName()],
        }

        # Add to entity collection.
        self.image_coll.add_entity_from_dict(entity_dict=curr_obj_dict)
        # Cleaning (probably not necessary).
        del curr_obj_dict
        del map_image
    except Exception as e:
        self.print_terminal(f"Image file {in_file_name} not recognized ERROR: {str(e)}")


def xs_image2vtk(self=None, in_file_name=None, x_section_uid=None):
    """Import and add an image to the image collection
    <self> is the calling ProjectWindow() instance."""
    try:
        # Open a raster file with rasterio.
        # The image is not read here but will be read afterward with rio_image.read()
        # http://xarray.pydata.org/en/stable/io.html#rasterio
        # http://www-2.unipv.it/compmech/seminars/group/VTK-VMTK.pdf
        rio_image = rio_open(in_file_name)

        # Image size as read by rasterio
        img_width_px = rio_image.width
        img_height_px = rio_image.height

        # Cross-section geometry
        azimuth = self.xsect_coll.get_uid_azimuth(x_section_uid)
        #origin_z = self.xsect_coll.get_uid_top(x_section_uid)
        length = self.xsect_coll.get_uid_length(x_section_uid)
        width = self.xsect_coll.get_uid_width(x_section_uid)
        bottom = self.xsect_coll.get_uid_bottom(x_section_uid)
        origin_z = bottom + width

        # Ask user for georeferencing parameters
        # NOTE that "width" will be renamed to "height" that is more intuitive
        in_dict = {
            "origin_W": ["Image origin (left) in X-section coords W", "0.0"],
            "origin_Z": ["Image origin (top) in Z coords", f"{origin_z}"],
            "length": ["Image length along X-section coords W", f"{length}"],
            "width": ["Image height along X-section coords Z", f"{width}"],
        }
        out_dict = multiple_input_dialog(
            title="XSection image georeferencing\n(in XSection reference frame)",
            input_dict=in_dict,
        )
        if out_dict is None:
            return

        origin_W = float(out_dict["origin_W"])
        origin_Z = float(out_dict["origin_Z"])
        length = float(out_dict["length"])
        width = float(out_dict["width"])

        # Image origin in in VTK coords, so lower left corner is at (0,0,0), hence origin_Z must be corrected
        origin_X, origin_Y = self.xsect_coll.get_XY_from_W(
            section_uid=x_section_uid, W=origin_W
        )
        origin_Z = origin_Z - width
        origin = [origin_X, origin_Y, origin_Z]

        spacing_W = length / img_width_px
        spacing_Z = width / img_height_px

        # Direction matrix
        direction_matrix = [
            np_sin(azimuth * np_pi / 180),
            0,
            -(np_cos(azimuth * np_pi / 180)),
            np_cos(azimuth * np_pi / 180),
            0,
            np_sin(azimuth * np_pi / 180),
            0,
            1,
            0,
        ]

        # Read the image and convert to vtk array.
        vtk_array = image_file_to_vtk(self=self, rio_image=rio_image)

        # Create XsImage entity (inherits from vtk.vtkImageData) and then set all data.
        # Recall that image coords 0,0 are at upper-left and image coords grow along length and -height.
        xs_image = XsImage(x_section_uid=x_section_uid, parent=self)
        xs_image.SetOrigin(origin)
        xs_image.SetSpacing([spacing_W, spacing_Z, 1])  # 1 or 0.0 here?
        xs_image.SetDimensions([img_width_px, img_height_px, 1])
        xs_image.SetDirectionMatrix(direction_matrix)
        xs_image.GetPointData().AddArray(vtk_array)
        xs_image.GetPointData().SetActiveScalars(vtk_array.GetName())

        # Create dictionary
        curr_obj_dict = {
            "uid": str(uuid4()),
            "name": os.path.basename(in_file_name),
            "topology": "XsImage",
            "x_section": x_section_uid,
            "vtk_obj": xs_image,
            "properties_components": xs_image.properties_components,
            "properties_types": xs_image.properties_types,
            "properties_names": [vtk_array.GetName()],
        }

        # Add to entity collection.
        self.image_coll.add_entity_from_dict(entity_dict=curr_obj_dict)
        # Cleaning (probably not necessary).
        del curr_obj_dict
        del xs_image
    except Exception as e:
        self.print_terminal(f"Image file {in_file_name} not recognized ERROR: {str(e)}")
