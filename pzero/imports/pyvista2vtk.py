from uuid import uuid4
from pyvista import read as pv_read
from PyQt5.QtWidgets import QFileDialog
from copy import deepcopy
import os

from pzero.entities_factory import VertexSet, PolyLine, TriSurf, TetraSolid

def pyvista2vtk(self):
    """
    Read various file formats handled by PyVista and add, to the appropriate collection, all the pointset, polyline, triangulated
    surface and tetrahedral meshes as VTK polydata entities.
    <self> is the calling ProjectWindow() instance.
    """
    self.TextTerminal.appendPlainText("Importing PyVista-supported format")
    self.TextTerminal.appendPlainText(
        "Properties are discarded if they are not 1D, 2D, 3D, 4D, 6D or 9D (due to VTK limitations)"
    )

    # Select and open input file
    in_file_name = QFileDialog.getOpenFileName(
        self, "Import entities from PyVista-supported file"
    )[0]
    if in_file_name:
        self.TextTerminal.appendPlainText("in_file_name: " + in_file_name)
        # Initialize
        cell_type = -1

        # Read file with pv_read() function and detect topology
        try:
            curr_obj = pv_read(in_file_name)

            # Get topology (CellType) of first cell in object
            cell_type = curr_obj.GetCellType(0)
        except Exception as e:
            self.TextTerminal.appendPlainText(
                f"pyvista2vtk - entity topology not recognized ERROR: {e}"
            )
            return  # Exit the function if reading fails

        # If curr_obj is a recognized topology, assign to PZero class
        if cell_type == 1:
            curr_obj.__class__ = VertexSet
            topology = "VertexSet"
        elif cell_type == 3:
            curr_obj.__class__ = PolyLine
            topology = "PolyLine"
        elif cell_type == 5:
            curr_obj.__class__ = TriSurf
            topology = "TriSurf"
        elif cell_type == 10:
            curr_obj.__class__ = TetraSolid
            topology = "TetraSolid"
        else:
            self.TextTerminal.appendPlainText(
                "pyvista2vtk - unrecognized cell type."
            )
            return  # Exit if cell type is not recognized

        # Create the entity dictionary similar to dem2vtk.py
        curr_obj_attributes = deepcopy(self.geol_coll.entity_dict)
        curr_obj_attributes["uid"] = str(uuid4())
        curr_obj_attributes["name"] = os.path.basename(in_file_name)
        curr_obj_attributes["topology"] = topology
        curr_obj_attributes["vtk_obj"] = curr_obj
        curr_obj_attributes["properties_names"] = []  # Add if there are any properties
        curr_obj_attributes["properties_components"] = []

        # Add the entity to the geological collection
        self.geol_coll.add_entity_from_dict(entity_dict=curr_obj_attributes)

        # Clean up
        del curr_obj
        del curr_obj_attributes
