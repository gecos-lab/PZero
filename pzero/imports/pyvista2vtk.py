"""pyvista2vtk.py
PZero© Andrea Bistacchi"""

from uuid import uuid4

from pyvista import read as pv_read

from PySide6.QtWidgets import QFileDialog

from pzero.entities_factory import VertexSet, PolyLine, TriSurf, TetraSolid

"""TO BE COMPLETELY UPDATED - SEE DEM2VTK FOR INSTANCE _____________________________"""


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

    """Select and open input file"""
    in_file_name = QFileDialog.getOpenFileName(
        self, "Import entities from PyVista-supported file"
    )
    in_file_name = in_file_name[0]
    if in_file_name:
        self.TextTerminal.appendPlainText("in_file_name: " + in_file_name)
        """Initialize"""
        cell_type = -1

        """Read file with pv_read() function and detect topology of curr_obj - ASSUMES ALL CELLS ARE OF THE SAME TYPE"""
        try:
            curr_obj = pv_read(in_file_name)

            """ VTK cell topology from documentation at https://vtk.org/doc/nightly/html/vtkCellType_8h.html
            VTK_EMPTY_CELL = 0, VTK_VERTEX = 1, VTK_POLY_VERTEX = 2, VTK_LINE = 3,
            VTK_POLY_LINE = 4, VTK_TRIANGLE = 5, VTK_TRIANGLE_STRIP = 6, VTK_POLYGON = 7,
            VTK_PIXEL = 8, VTK_QUAD = 9, VTK_TETRA = 10, VTK_VOXEL = 11,
            VTK_HEXAHEDRON = 12, VTK_WEDGE = 13, VTK_PYRAMID = 14, VTK_PENTAGONAL_PRISM = 15,
            VTK_HEXAGONAL_PRISM = 16, VTK_QUADRATIC_EDGE = 21, VTK_QUADRATIC_TRIANGLE = 22, VTK_QUADRATIC_QUAD = 23,
            VTK_QUADRATIC_POLYGON = 36, VTK_QUADRATIC_TETRA = 24, VTK_QUADRATIC_HEXAHEDRON = 25, VTK_QUADRATIC_WEDGE = 26,
            VTK_QUADRATIC_PYRAMID = 27, VTK_BIQUADRATIC_QUAD = 28, VTK_TRIQUADRATIC_HEXAHEDRON = 29, VTK_QUADRATIC_LINEAR_QUAD = 30,
            VTK_QUADRATIC_LINEAR_WEDGE = 31, VTK_BIQUADRATIC_QUADRATIC_WEDGE = 32, VTK_BIQUADRATIC_QUADRATIC_HEXAHEDRON = 33, VTK_BIQUADRATIC_TRIANGLE = 34,
            VTK_CUBIC_LINE = 35, VTK_CONVEX_POINT_SET = 41, VTK_POLYHEDRON = 42, VTK_PARAMETRIC_CURVE = 51,
            VTK_PARAMETRIC_SURFACE = 52, VTK_PARAMETRIC_TRI_SURFACE = 53, VTK_PARAMETRIC_QUAD_SURFACE = 54, VTK_PARAMETRIC_TETRA_REGION = 55,
            VTK_PARAMETRIC_HEX_REGION = 56, VTK_HIGHER_ORDER_EDGE = 60, VTK_HIGHER_ORDER_TRIANGLE = 61, VTK_HIGHER_ORDER_QUAD = 62,
            VTK_HIGHER_ORDER_POLYGON = 63, VTK_HIGHER_ORDER_TETRAHEDRON = 64, VTK_HIGHER_ORDER_WEDGE = 65, VTK_HIGHER_ORDER_PYRAMID = 66,
            VTK_HIGHER_ORDER_HEXAHEDRON = 67, VTK_LAGRANGE_CURVE = 68, VTK_LAGRANGE_TRIANGLE = 69, VTK_LAGRANGE_QUADRILATERAL = 70,
            VTK_LAGRANGE_TETRAHEDRON = 71, VTK_LAGRANGE_HEXAHEDRON = 72, VTK_LAGRANGE_WEDGE = 73, VTK_LAGRANGE_PYRAMID = 74,
            VTK_BEZIER_CURVE = 75, VTK_BEZIER_TRIANGLE = 76, VTK_BEZIER_QUADRILATERAL = 77, VTK_BEZIER_TETRAHEDRON = 78,
            VTK_BEZIER_HEXAHEDRON = 79, VTK_BEZIER_WEDGE = 80, VTK_BEZIER_PYRAMID = 81, VTK_NUMBER_OF_CELL_TYPES
            """

            """Get topology (CellType) of first cell in object - THEN ASSUMES ALL CELLS ARE OF THE SAME TYPE"""
            cell_type = curr_obj.GetCellType(0)
        except:
            self.TextTerminal.appendPlainText(
                "pyvista2vtk - entity topology not recognized ERROR."
            )

        """If curr_obj is a recognized topology, assign to PZero class, and add to a collection"""
        if cell_type == 1:
            curr_obj.uid = str(uuid4())
            curr_obj.type = "VertexSet"
            curr_obj.__class__ = VertexSet
        elif cell_type == 3:
            curr_obj.uid = str(uuid4())
            curr_obj.type = "PolyLine"
            curr_obj.__class__ = PolyLine
        elif cell_type == 5:
            curr_obj.uid = str(uuid4())
            curr_obj.type = "TriSurf"
            curr_obj.__class__ = TriSurf
        elif cell_type == 10:
            curr_obj.uid = str(uuid4())
            curr_obj.type = "TetraSolid"
            curr_obj.__class__ = TetraSolid
        self.e_c.add_entity_from_dict(
            vtk_entity=curr_obj, entity_dict=deepcopy(GeologicalCollection.entity_dict)
        )  # to APPROPRIATE collection_________________

        """Clean"""
        del curr_obj
