"""segy2vtk.py
PZero© Andrea Bistacchi"""

# imports
from os import path as os_path
from copy import deepcopy
from uuid import uuid4 as uuid_uuid4
from numpy import array as np_array
from numpy import column_stack as np_column_stack
from numpy import empty as np_empty
from numpy import flip as np_flip
from numpy import linalg as np_linalg
from numpy import linspace as np_linspace
from numpy import repeat as np_repeat
from numpy import shape as np_shape
from numpy import where as np_where
from numpy import zeros_like as np_zeros_like
from pyvista import StructuredGrid as pv_StructuredGrid
from segyio import open as segyio_open
from segyio import BinField as segyio_BinField
from segyio import TraceField as segyio_TraceField

from pzero.entities_factory import Seismics
from pzero.helpers.helper_functions import freeze_gui
from pzero.processing.segy_standardizer import convert_to_standard_segy
import os
import numpy as np
@freeze_gui
def segy2vtk(self, in_file_name):
    """Import SEG-Y data from file and add it to the image collection."""
    this_uid = str(uuid_uuid4())
    
    try:
        # First try direct reading
        try:
            pv_seismic_grid = read_segy_file(in_file_name=in_file_name)
        except Exception as e:
            self.print_terminal("Standard reading failed, attempting conversion...")
            
            # Create a standardized version of the file
            standardized_file = os_path.join(os_path.dirname(in_file_name), 
                                           "standardized_" + os_path.basename(in_file_name))
            
            try:
                success = convert_to_standard_segy(in_file_name, standardized_file)
                
                if not success:
                    self.print_terminal("Failed to standardize SEG-Y file.")
                    return
                    
                self.print_terminal("Standardization successful, importing file...")
                
                # Read the standardized file using segyio
                with segyio_open(standardized_file, "r", strict=False) as segyfile:
                    # Get dimensions
                    num_traces = len(segyfile.trace)
                    num_samples = len(segyfile.samples)
                    grid_size = int(np.sqrt(num_traces))
                    
                    # Initialize arrays
                    data = np_empty((grid_size, grid_size, num_samples))
                    xcoords = np_empty(grid_size * grid_size)
                    ycoords = np_empty(grid_size * grid_size)
                    
                    # Read trace data
                    for i in range(grid_size * grid_size):
                        inline = i // grid_size
                        xline = i % grid_size
                        data[inline, xline, :] = segyfile.trace[i]
                        xcoords[i] = inline   # Use generated coordinates
                        ycoords[i] = xline 
                    
                    # Create volume points
                    slices = np_linspace(-num_samples, 0, num_samples)
                    volume_points = np_empty((num_samples, grid_size * grid_size, 3))
                    
                    for i, z in enumerate(slices):
                        zcoords = np_repeat(z/6, grid_size * grid_size)
                        points = np_column_stack((xcoords, ycoords, zcoords))
                        volume_points[i, :, :] = points
                    
                    # Create VTK grid
                    pv_seismic_grid = pv_StructuredGrid()
                    pv_seismic_grid.points = volume_points.reshape(-1, 3)
                    pv_seismic_grid.dimensions = (grid_size, grid_size, num_samples)
                    pv_seismic_grid['intensity'] = np_flip(data, axis=2).ravel(order='F')
                
            finally:
                # Clean up temporary file
                if os_path.exists(standardized_file):
                    os.remove(standardized_file)
        
        # Create entity dictionary and add to collection
        curr_obj_dict = deepcopy(self.image_coll.entity_dict)
        curr_obj_dict["uid"] = this_uid
        curr_obj_dict["name"] = os_path.basename(in_file_name)
        curr_obj_dict["topology"] = "Seismics"
        curr_obj_dict["vtk_obj"] = Seismics()
        curr_obj_dict["vtk_obj"].DeepCopy(pv_seismic_grid)
        curr_obj_dict["properties_names"] = curr_obj_dict["vtk_obj"].point_data_keys
        curr_obj_dict["properties_components"] = curr_obj_dict["vtk_obj"].point_data_components
        curr_obj_dict["properties_types"] = curr_obj_dict["vtk_obj"].point_data_types
        
        self.image_coll.add_entity_from_dict(entity_dict=curr_obj_dict)
        self.print_terminal("Import successful.")
        
    except Exception as e:
        self.print_terminal(f"Error during import: {str(e)}")


def read_segy_file(in_file_name=None):
    """Read SEG-Y data from file with SegyIo."""
    with segyio_open(in_file_name, "r", strict= False) as segyfile:
        inlines = segyfile.ilines
        crosslines = segyfile.xlines
        times = segyfile.samples
        num_samples = len(times)
        sample_interval = segyfile.bin[segyio_BinField.Interval]

        xcoords = segyfile.attributes(segyio_TraceField.CDP_X)[:]
        ycoords = segyfile.attributes(segyio_TraceField.CDP_Y)[:]

        inlines_index = segyfile.attributes(segyio_TraceField.INLINE_3D)[:]
        try:
            # Code that might raise the TypeError
            inline_index_list = np_where(inlines_index == inlines[0])[0]
        except TypeError:
            # Raise custom error message when TypeError is caught
            raise Exception("The SEGYFILE is non-standard, PZero closing.")
        inline_index_list = np_where(inlines_index == inlines[0])[0]
        inline_dim = len(segyfile.attributes(segyio_TraceField.CDP_X)[inline_index_list])

        crosslines_index = segyfile.attributes(segyio_TraceField.CROSSLINE_3D)[:]
        crossline_index_list = np_where(crosslines_index == crosslines[0])[0]
        crossline_dim = len(segyfile.attributes(segyio_TraceField.CDP_X)[crossline_index_list])

        i_xcoords = segyfile.attributes(segyio_TraceField.CDP_X)[inline_index_list]
        i_ycoords = segyfile.attributes(segyio_TraceField.CDP_Y)[inline_index_list]
        i_zcoords = np_zeros_like(i_xcoords)

        i_xyz = np_column_stack((i_xcoords, i_ycoords, i_zcoords)).reshape(-1, 3)

        i_length = np_linalg.norm(i_xyz[0] - i_xyz[-1])
        depth = num_samples * sample_interval

        slices = np_linspace(-depth, 0, num_samples)
        volume_points = np_empty((num_samples, inline_dim * crossline_dim, 3))

        data_shape = np_shape(np_array(list(segyfile.xline[:])))
        data = np_empty(data_shape)

        for i, index in enumerate(crosslines):
            data[i, :, :] = np_array(list(segyfile.xline[index]))

        flip_data = np_flip(data, axis=2)

        for i, value in enumerate(slices):
            zcoords = np_repeat(value/6, len(xcoords))
            points = np_column_stack((xcoords, ycoords, zcoords)).astype(float)
            volume_points[i, :, :] = points

        volume_points = volume_points.reshape(-1, 3)

        pv_seismic_grid = pv_StructuredGrid()
        pv_seismic_grid.points = volume_points
        pv_seismic_grid.dimensions = (inline_dim, crossline_dim, num_samples)
        pv_seismic_grid['intensity'] = flip_data.ravel(order='F')

        return pv_seismic_grid