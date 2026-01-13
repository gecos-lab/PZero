"""segy2vtk.py
PZero© Andrea Bistacchi"""

# imports
from os import path as os_path
from os import remove as os_remove
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
            standardized_file = os_path.join(
                os_path.dirname(in_file_name),
                "standardized_" + os_path.basename(in_file_name),
            )

            try:
                success = convert_to_standard_segy(
                    in_file_name, standardized_file, print_fn=self.print_terminal
                )

                if not success:
                    self.print_terminal("Failed to standardize SEG-Y file.")
                    return

                self.print_terminal("Standardization successful, importing file...")

                # Read the standardized file using the same function
                pv_seismic_grid = read_segy_file(in_file_name=standardized_file)

            finally:
                # Clean up temporary file
                if os_path.exists(standardized_file):
                    os_remove(standardized_file)

        # Create entity dictionary and add to collection
        curr_obj_dict = deepcopy(self.image_coll.entity_dict)
        curr_obj_dict["uid"] = this_uid
        curr_obj_dict["name"] = os_path.basename(in_file_name)
        curr_obj_dict["topology"] = "Seismics"
        # Use ShallowCopy instead of DeepCopy for much faster performance
        # The pv_seismic_grid is created fresh each time so no data sharing issues
        curr_obj_dict["vtk_obj"] = Seismics()
        curr_obj_dict["vtk_obj"].ShallowCopy(pv_seismic_grid)
        curr_obj_dict["properties_names"] = curr_obj_dict["vtk_obj"].point_data_keys
        curr_obj_dict["properties_components"] = curr_obj_dict[
            "vtk_obj"
        ].point_data_components
        curr_obj_dict["properties_types"] = curr_obj_dict["vtk_obj"].point_data_types

        # Store source file path for fast save/load
        curr_obj_dict["seismic_source_file"] = os_path.abspath(in_file_name)

        self.image_coll.add_entity_from_dict(entity_dict=curr_obj_dict)
        self.print_terminal("Import successful.")

    except Exception as e:
        self.print_terminal(f"Error during import: {str(e)}")


def read_segy_file(in_file_name=None):
    """Read SEG-Y data from file with SegyIo.
    
    Optimized version: minimizes attribute calls, uses vectorized operations,
    and avoids redundant memory allocations.
    """
    with segyio_open(in_file_name, "r", strict=False) as segyfile:
        inlines = segyfile.ilines
        crosslines = segyfile.xlines
        times = segyfile.samples
        num_samples = len(times)
        sample_interval = segyfile.bin[segyio_BinField.Interval]

        # Read all trace attributes once and cache them
        xcoords = np_array(segyfile.attributes(segyio_TraceField.CDP_X)[:], dtype=float)
        ycoords = np_array(segyfile.attributes(segyio_TraceField.CDP_Y)[:], dtype=float)
        inlines_index = np_array(segyfile.attributes(segyio_TraceField.INLINE_3D)[:])
        crosslines_index = np_array(segyfile.attributes(segyio_TraceField.CROSSLINE_3D)[:])

        try:
            inline_index_list = np_where(inlines_index == inlines[0])[0]
        except TypeError:
            raise Exception("The SEGYFILE is non-standard, PZero closing.")
        
        inline_dim = len(inline_index_list)
        crossline_index_list = np_where(crosslines_index == crosslines[0])[0]
        crossline_dim = len(crossline_index_list)

        # Compute depth range
        depth = num_samples * sample_interval
        slices = np_linspace(-depth, 0, num_samples) / 8.0  # Pre-divide by 8
        
        # Vectorized point construction - build all z-layers at once
        num_traces = len(xcoords)
        # Create z-coordinates for each sample level (num_samples x num_traces)
        z_all = np_repeat(slices[:, None], num_traces, axis=1)  # shape: (num_samples, num_traces)
        
        # Build volume_points using broadcasting
        volume_points = np_empty((num_samples, num_traces, 3), dtype=float)
        volume_points[:, :, 0] = xcoords  # broadcast xcoords to all z-levels
        volume_points[:, :, 1] = ycoords  # broadcast ycoords to all z-levels
        volume_points[:, :, 2] = z_all
        volume_points = volume_points.reshape(-1, 3)

        # Read seismic data efficiently using segyio's trace array
        # segyfile.trace gives direct numpy array access per trace
        num_crosslines = len(crosslines)
        num_inlines = len(inlines)
        data = np_empty((num_crosslines, num_inlines, num_samples), dtype=float)
        
        # Use segyio's xline iterator which is optimized for crossline access
        for i, xline_data in enumerate(segyfile.xline[:]):
            data[i, :, :] = xline_data

        flip_data = np_flip(data, axis=2)

        pv_seismic_grid = pv_StructuredGrid()
        pv_seismic_grid.points = volume_points
        pv_seismic_grid.dimensions = (inline_dim, crossline_dim, num_samples)
        pv_seismic_grid["intensity"] = flip_data.ravel(order="F")

        return pv_seismic_grid
