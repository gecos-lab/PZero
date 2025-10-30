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

from vtkmodules.util import numpy_support

from pzero.collections.image_collection import ImageCollection
from pzero.entities_factory import MapImage, XsImage
from pzero.helpers.helper_dialogs import multiple_input_dialog


def geo_image2vtk(self=None, in_file_name=None):
    """Import and add an image to the imaage collection
    <self> is the calling ProjectWindow() instance."""
    try:
        # Open raster file format (geotiff or other accepted by GDAL) with rasterio.
        # The image is not read here but will be read afterwards with geo_image.read()
        # http://xarray.pydata.org/en/stable/io.html#rasterio
        # http://www-2.unipv.it/compmech/seminars/group/VTK-VMTK.pdf
        geo_image = rio_open(in_file_name)
        # Georeferencing variables as read by rasterio.
        img_width_px = geo_image.width
        img_height_px = geo_image.height
        img_x_min = rio_plt.plotting_extent(geo_image)[0]
        img_x_max = rio_plt.plotting_extent(geo_image)[1]
        img_y_min = rio_plt.plotting_extent(geo_image)[2]
        img_y_max = rio_plt.plotting_extent(geo_image)[3]
        # Read the image and convert to vtk array.
        # Deep copy used since the image is read now from file.
        # DO NOT specify the array type as e.g. in array_type=vtk.VTK_CHAR
        if geo_image.count == 1:
            vtk_array = numpy_support.numpy_to_vtk(geo_image.read(1).ravel(), deep=True)
            vtk_array.SetName("greyscale")
        elif geo_image.count == 3:
            vtk_r_property = geo_image.read(1)
            vtk_g_property = geo_image.read(2)
            vtk_b_property = geo_image.read(3)
            numpy_array = np_dstack((vtk_r_property, vtk_g_property, vtk_b_property))
            # vtk_array = numpy_support.numpy_to_vtk(np.flip(numpy_array.swapaxes(0, 1), axis=1).reshape((-1, 3), order='F'), deep=True)
            vtk_array = numpy_support.numpy_to_vtk(
                numpy_array.swapaxes(0, 1).reshape((-1, 3), order="F"), deep=True
            )
            vtk_array.SetName("RGB")
        elif geo_image.count == 4:
            vtk_r_property = geo_image.read(1)
            vtk_g_property = geo_image.read(2)
            vtk_b_property = geo_image.read(3)
            vtk_a_property = geo_image.read(4)
            numpy_array = np_dstack(
                (vtk_r_property, vtk_g_property, vtk_b_property, vtk_a_property)
            )
            # vtk_array = numpy_support.numpy_to_vtk(np.flip(numpy_array.swapaxes(0, 1), axis=1).reshape((-1, 3), order='F'), deep=True)
            vtk_array = numpy_support.numpy_to_vtk(
                numpy_array.swapaxes(0, 1).reshape((-1, 4), order="F"), deep=True
            )
            vtk_array.SetName("RGB")
        else:
            # ADD OPTION FOR MULTIBAND IMAGES HERE_____________________________
            print("Multiband not supported")
            return
        # Create MapImage entity (inherits from vtk.vtkImageData) and then set all data.
        vtk_image = MapImage()
        # With the following dimensions, origin and spacing, image coords 0,0 are at upper-left and image coords grow along x and -y.
        vtk_image.SetDimensions(img_width_px, img_height_px, 1)
        vtk_image.SetSpacing(
            [
                (img_x_max - img_x_min) / (img_width_px + 1),
                (img_y_min - img_y_max) / (img_height_px + 1),
                1,
            ]
        )
        vtk_image.SetOrigin([img_x_min, img_y_max, 0])

        # Add the vtk array image data
        vtk_image.GetPointData().AddArray(vtk_array)
        if geo_image.count == 1:
            vtk_image.GetPointData().SetActiveScalars("greyscale")
        elif geo_image.count >= 3:
            vtk_image.GetPointData().SetActiveScalars("RGB")

        # Create dictionary
        curr_obj_dict = {}
        curr_obj_dict["uid"] = str(uuid4())
        curr_obj_dict["name"] = os.path.basename(in_file_name)
        curr_obj_dict["topology"] = "MapImage"
        if geo_image.count == 1:
            curr_obj_dict["properties_names"] = ["greyscale"]
        elif geo_image.count >= 3:
            curr_obj_dict["properties_names"] = ["RGB"]
        curr_obj_dict["properties_components"] = vtk_image.properties_components
        curr_obj_dict["properties_types"] = vtk_image.properties_types
        curr_obj_dict["vtk_obj"] = vtk_image
        # Add to entity collection.
        self.image_coll.add_entity_from_dict(entity_dict=curr_obj_dict)
        # Cleaning (probably not necessary).
        del curr_obj_dict
        del vtk_image
    except Exception as e:
        self.print_terminal(f"Image file not recognized ERROR: {str(e)}")
        import traceback

        self.print_terminal(traceback.format_exc())

def xs_image2vtk(self=None, in_file_name=None, x_section_uid=None):
    """Import and add an image to the image collection
    <self> is the calling ProjectWindow() instance."""

    # Open raster file (e.g., TIFF or other supported by GDAL)
    xs_image = rio_open(in_file_name)

    # Image size as read by rasterio
    dim_W = xs_image.width
    dim_Z = xs_image.height

    # Cross-section geometry
    azimuth = self.xsect_coll.get_uid_azimuth(x_section_uid)
    origin_z = self.xsect_coll.get_uid_bottom(x_section_uid)
    width = self.xsect_coll.get_uid_length(x_section_uid)
    height = np_abs(self.xsect_coll.get_uid_top(x_section_uid)) - np_abs(origin_z)

    # Ask user for georeferencing parameters
    in_dict = {
        "origin_W": ["Origin W", "0.0"],
        "origin_Z": ["Origin Z", f"{origin_z}"],
        "width": ["width", f"{width}"],
        "height": ["height", f"{height}"],
    }
    out_dict = multiple_input_dialog(
        title="XSection image georeferencing\n(in XSection reference frame)",
        input_dict=in_dict,
    )
    if out_dict is None:
        return

    origin_W = float(out_dict["origin_W"])
    origin_Z = float(out_dict["origin_Z"])
    width = float(out_dict["width"])
    height = float(out_dict["height"])

    origin_X, origin_Y = self.xsect_coll.get_XY_from_W(
        section_uid=x_section_uid, W=origin_W
    )
    origin = [origin_X, origin_Y, origin_Z]

    spacing_W = width / dim_W
    spacing_Z = height / dim_Z

    # Direction matrix (original, senza rotazioni aggiuntive)
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
    bands = xs_image.count
    self.print_terminal(f"Number of bands: {bands}")

    if bands == 1:
        # Greyscale
        arr = xs_image.read(1)
        from numpy import nan_to_num, uint8
        arr = nan_to_num(arr, nan=0.0)
        if arr.dtype != uint8:
            arr_min, arr_max = arr.min(), arr.max()
            if arr_max > arr_min:
                arr = ((arr - arr_min) / (arr_max - arr_min) * 255).astype(uint8)
            else:
                arr = arr.astype(uint8)
        vtk_array = numpy_support.numpy_to_vtk(arr.ravel(), deep=True)
        vtk_array.SetName("greyscale")
        prop_name = "greyscale"

    elif bands == 3:
        # RGB
        arr_list = [xs_image.read(i + 1) for i in range(3)]
        numpy_array = np_dstack(arr_list)
        vtk_array = numpy_support.numpy_to_vtk(
            numpy_array.swapaxes(0, 1).reshape((-1, 3), order="F"), deep=True
        )
        vtk_array.SetName("RGB")
        prop_name = "RGB"

    else:
        # Multibanda generica (2 o più)
        arr_list = [xs_image.read(i + 1) for i in range(bands)]
        numpy_array = np_dstack(arr_list)
        vtk_array = numpy_support.numpy_to_vtk(
            numpy_array.swapaxes(0, 1).reshape((-1, bands), order="F"), deep=True
        )
        vtk_array.SetName(f"{bands}-band")
        prop_name = f"{bands}-band"

    # --- CREATE VTK IMAGE DATA ---
    vtk_image = XsImage(x_section_uid=x_section_uid, parent=self)
    vtk_image.SetOrigin(origin)
    vtk_image.SetSpacing([spacing_W, spacing_Z, 0.0])
    vtk_image.SetDimensions([dim_W, dim_Z, 1])
    vtk_image.SetDirectionMatrix(direction_matrix)
    vtk_image.GetPointData().AddArray(vtk_array)
    vtk_image.GetPointData().SetActiveScalars(vtk_array.GetName())

    # --- BUILD ENTITY DICTIONARY ---
    curr_obj_dict = {
        "uid": str(uuid4()),
        "name": os.path.basename(in_file_name),
        "topology": "XsImage",
        "x_section": x_section_uid,
        "vtk_obj": vtk_image,
        "properties_components": vtk_image.properties_components,
        "properties_types": vtk_image.properties_types,
        "properties_names": [prop_name],
    }
    # --- ADD TO COLLECTION ---
    self.image_coll.add_entity_from_dict(entity_dict=curr_obj_dict)
