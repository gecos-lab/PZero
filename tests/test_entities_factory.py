import pytest
from pytest import raises
from pzero.entities_factory import VertexSet, PolyLine, TriSurf, PolyData, XsVertexSet, XsPolyLine, TetraSolid, \
    Voxet, XsVoxet

import numpy as np


# Class for testing VertexSet from entities_factory
class TestVertex:

    vertex_instance = VertexSet()
    np_array = np.array([1, 2, 3, 4, 5])

    # testing default values / initialization
    def test_bounds(self):
        assert self.vertex_instance.bounds == (1.0, -1.0, 1.0, -1.0, 1.0, -1.0)

    # testing VertexSet deep_copy
    def test_deep_copy(self):
        deep_copy = self.vertex_instance.deep_copy()
        deep_copy2 = self.vertex_instance.deep_copy()

        assert isinstance(deep_copy, VertexSet)
        assert isinstance(deep_copy2, VertexSet)
        assert deep_copy.cells_number == deep_copy2.cells_number
        assert self.vertex_instance.cells_number == deep_copy2.cells_number

    # testing auto_cells function
    def test_auto_cells(self):
        # missing set_cell_data method implementation
        # self.vertex_instance.set_cell_data(self.np_array)
        deep_copy = self.vertex_instance.deep_copy()

        # calling on both vertex autocells
        self.vertex_instance.auto_cells()
        deep_copy.auto_cells()

        assert self.vertex_instance.cells == deep_copy.cells
        assert self.vertex_instance.cells_number == 0


# Testing the class PolyLine from entities_factory
class TestPolyLine:

    poly_line_instance = PolyLine()
    np_array = np.array([1, 2])
    np_array2 = np.array([4, 5])

    # Testing default values / initialization
    def test_bounds(self):
        assert self.poly_line_instance.bounds == (1.0, -1.0, 1.0, -1.0, 1.0, -1.0)

    # Testing PolyLine deep_copy
    def test_deep_copy(self):
        deep_copy = self.poly_line_instance.deep_copy()
        deep_copy2 = self.poly_line_instance.deep_copy()

        assert isinstance(deep_copy, PolyLine)
        assert isinstance(deep_copy2, PolyLine)
        assert deep_copy.cells_number == deep_copy2.cells_number
        assert self.poly_line_instance.cells_number == deep_copy2.cells_number

    # Testing auto_cells function
    def test_auto_cells(self):
        deep_copy = self.poly_line_instance.deep_copy()

        # calling on both PolyLine autocells
        self.poly_line_instance.auto_cells()
        deep_copy.auto_cells()

        assert self.poly_line_instance.cells_number == deep_copy.cells_number
        assert self.poly_line_instance.cells_number == 0

    # Testing append_cell
    def test_append_cell(self):
        # this will store how much times we append a cell inside the poly_line
        test_number = 1000

        for i in range(test_number):
            self.poly_line_instance.append_cell(self.np_array)

        assert self.poly_line_instance.cells_number == test_number

    # Testing sort_nodes - skipping test because Windows fatal exception: access violation
    @pytest.mark.skip(reason="Windows fatal exception when calling sort_nodes()")
    def test_sort_nodes(self):
        self.poly_line_instance.append_cell(self.np_array)
        self.poly_line_instance.append_cell(self.np_array2)

        # THIS line will cause the fatal exception -> self.poly_line_instance.sort_nodes()
        # assert ...

    # Testing poly2lines method
    @pytest.mark.skip(reason="Windows fatal exception when calling sort_nodes()")
    def test_poly2lines(self):
        self.poly_line_instance.append_cell(self.np_array)
        #self.poly_line_instance.append_cell(self.np_array2)

        # THIS line will cause the fatal exception -> self.poly_line_instance.poly2lines()

        assert self.poly_line_instance.cells_number == 2


# Testing TriSurf class
class TestTriSurf:

    tri_surf_instance = TriSurf()
    np_array = np.array([1, 2, 3])

    # Testing default values / initialization
    def test_bounds(self):
        assert self.tri_surf_instance.bounds == (1.0, -1.0, 1.0, -1.0, 1.0, -1.0)

    # Testing TriSurf deep_copy
    def test_deep_copy(self):
        deep_copy = self.tri_surf_instance.deep_copy()
        deep_copy2 = self.tri_surf_instance.deep_copy()

        assert isinstance(deep_copy, PolyData)
        assert isinstance(deep_copy2, PolyData)
        assert deep_copy.cells_number == deep_copy2.cells_number
        assert self.tri_surf_instance.cells_number == deep_copy2.cells_number

    # Testing append_cell
    def test_append_cell(self):
        # this will store how much times we append a cell inside the poly_line
        test_number = 1000

        for i in range(test_number):
            self.tri_surf_instance.append_cell(self.np_array)

        assert self.tri_surf_instance.cells_number == test_number

    # Testing get_clean_boundary and deep_copy
    def test_get_clean_boundary(self):
        borders = self.tri_surf_instance.get_clean_boundary()
        deep_copy = self.tri_surf_instance.deep_copy()

        assert borders.GetBounds() == deep_copy.GetBounds()

    # Testing boundary_dilation
    def test_boundary_dilation(self):
        with raises(TypeError):
            dilated_copy = self.tri_surf_instance.boundary_dilation()
            assert self.tri_surf_instance.bounds != dilated_copy.bounds


# Testing XsVertexSet
class TestXsVertexSet:

    xs_vertex_instance = XsVertexSet()

    # testing default values / initialization
    def test_bounds(self):
        assert self.xs_vertex_instance.bounds == (1.0, -1.0, 1.0, -1.0, 1.0, -1.0)

    # testing XSVertexSet deep_copy
    def test_deep_copy(self):
        deep_copy = self.xs_vertex_instance.deep_copy()
        deep_copy2 = self.xs_vertex_instance.deep_copy()

        assert isinstance(deep_copy, XsVertexSet)
        assert isinstance(deep_copy2, XsVertexSet)
        assert deep_copy.cells_number == deep_copy2.cells_number
        assert self.xs_vertex_instance.cells_number == deep_copy2.cells_number


# Testing XsPolyLine
class TestXsPolyLine:

    xs_polyline_instance = XsPolyLine()

    # testing default values / initialization
    def test_bounds(self):
        assert self.xs_polyline_instance.bounds == (1.0, -1.0, 1.0, -1.0, 1.0, -1.0)

    # testing XsPolyLine deep_copy
    def test_deep_copy(self):
        deep_copy = self.xs_polyline_instance.deep_copy()
        deep_copy2 = self.xs_polyline_instance.deep_copy()

        assert isinstance(deep_copy, XsPolyLine)
        assert isinstance(deep_copy2, XsPolyLine)
        assert deep_copy.cells_number == deep_copy2.cells_number
        assert self.xs_polyline_instance.cells_number == deep_copy2.cells_number


# Testing TetraSolid
class TestTetraSolid:

    np_array = np.array([1, 2, 3, 4])
    tetra_solid_instance = TetraSolid()

    # testing default values / initialization
    def test_bounds(self):
        assert self.tetra_solid_instance.GetBounds() == (1.0, -1.0, 1.0, -1.0, 1.0, -1.0)

    # testing TetraSolid deep_copy
    def test_deep_copy(self):
        deep_copy = self.tetra_solid_instance.deep_copy()
        deep_copy2 = self.tetra_solid_instance.deep_copy()

        assert isinstance(deep_copy, TetraSolid)
        assert isinstance(deep_copy2, TetraSolid)

    # Testing append_cell with a numpy array 4 * 1
    @pytest.mark.skip(reason="TypeError: no overloads of SetCells() take 1 argument")
    def test_append_cell(self):
        # this will store how much times we append a cell inside the poly_line
        test_number = 1000

        for i in range(test_number):
            # with raises(TypeError):
            self.tetra_solid_instance.append_cell(self.np_array)

        # assert self.tetra_solid_instance.cells == test_number

    # Testing get_clean_boundary and deep_copy
    def test_get_clean_boundary(self):
        deep_copy = self.tetra_solid_instance.deep_copy()
        deep_copy2 = self.tetra_solid_instance.deep_copy()

        assert deep_copy.GetBounds() == deep_copy2.GetBounds()


# Testing Voxet vtkImageData
class TestVoxet:

    np_array = np.array([1, 2, 3, 4])
    voxet_instance = Voxet()

    # testing default values / initialization
    def test_bounds(self):
        assert self.voxet_instance.GetBounds() == (1.0, -1.0, 1.0, -1.0, 1.0, -1.0)

    # testing Voxet deep_copy
    def test_deep_copy(self):
        deep_copy = self.voxet_instance.deep_copy()
        deep_copy2 = self.voxet_instance.deep_copy()

        assert isinstance(deep_copy, Voxet)
        assert isinstance(deep_copy2, Voxet)
        assert deep_copy.cells_number == deep_copy2.cells_number
        assert self.voxet_instance.cells_number == deep_copy2.cells_number

    # Test standard origin point
    def test_origin(self):
        assert self.voxet_instance.origin == (0, 0, 0)

    # Testing setting origin point
    def test_setting_origin(self):
        three_d_point = (10, 10, 10)
        self.voxet_instance.origin = three_d_point

        assert self.voxet_instance.origin == three_d_point

    # Testing std spacing
    def test_spacing(self):
        std_spacing = (1.0, 1.0, 1.0)
        assert self.voxet_instance.spacing == std_spacing

    # Testing setting spacing
    def test_setting_spacing(self):
        spacing = (12, 140, 3)
        self.voxet_instance.spacing = spacing
        assert self.voxet_instance.spacing == spacing

    # Testing standard Voxel dimensions
    def test_dimensions(self):
        std_dimensions = (0, 0, 0)
        assert self.voxet_instance.dimensions == std_dimensions

    # Testing setting Voxel dimensions
    def test_setting_dimensions(self):
        dimensions = (132, 12, -1)
        self.voxet_instance.dimensions = dimensions
        assert self.voxet_instance.dimensions == dimensions

    # Testing first dimension
    def test_u_n(self):
        std_dimensions = (0, 0, 0)
        assert self.voxet_instance.U_n == std_dimensions[0]

    # Test first dimension combined with changing all the dimensions
    def test_setting_u_n(self):
        changing_dimensions = (-2, 1, 1)
        self.voxet_instance.dimensions = changing_dimensions

        assert self.voxet_instance.U_n == changing_dimensions[0]

    # Testing second dimension
    def test_v_n(self):
        std_dimensions = (0, 0, 0)
        assert self.voxet_instance.V_n == std_dimensions[1]

    # Test second dimension combined with changing all the dimensions
    def test_setting_v_n(self):
        changing_dimensions = (-2, 5612, 1)
        self.voxet_instance.dimensions = changing_dimensions

        assert self.voxet_instance.V_n == changing_dimensions[1]

    # Testing second dimension
    def test_w_n(self):
        std_dimensions = (0, 0, 0)
        assert self.voxet_instance.W_n == std_dimensions[2]

    # Test second dimension combined with changing all the dimensions
    def test_setting_w_n(self):
        changing_dimensions = (-2, 1, -4554)
        self.voxet_instance.dimensions = changing_dimensions

        assert self.voxet_instance.W_n == changing_dimensions[2]

    # Testing first dimension spacing
    def test_u_step(self):
        std_spacing = (1.0, 1.0, 1.0)
        assert self.voxet_instance.U_step == std_spacing[0]

    # Testing setting first dimension spacing
    def test_setting_u_step(self):
        spacing = (122, 140, 3)
        self.voxet_instance.spacing = spacing
        assert self.voxet_instance.U_step == spacing[0]

    # Testing second dimension spacing
    def test_v_step(self):
        std_spacing = (1.0, 1.0, 1.0)
        assert self.voxet_instance.V_step == std_spacing[1]

    # Testing setting second dimension spacing
    def test_setting_v_step(self):
        spacing = (122, -343, 3)
        self.voxet_instance.spacing = spacing
        assert self.voxet_instance.V_step == spacing[1]

    # Testing third dimension spacing
    def test_w_step(self):
        std_spacing = (1.0, 1.0, 1.0)
        assert self.voxet_instance.W_step == std_spacing[2]

    # Testing setting third dimension spacing
    def test_setting_w_step(self):
        spacing = (122, -343, -1231233)
        self.voxet_instance.spacing = spacing
        assert self.voxet_instance.W_step == spacing[2]

    # Testing standard points_number
    def test_points_number(self):
        assert self.voxet_instance.points_number == 0

    # Testing standard cells_number
    def test_cells_number(self):
        assert self.voxet_instance.cells_number == 0

    # Testing cells
    @pytest.mark.skip(reason="Cells not implemented yet")
    def test_cells_number(self):
        assert ...

    # Testing standard point_data_keys
    def test_point_data_keys(self):
        assert self.voxet_instance.point_data_keys == []

    # Testing standard point_data_components
    def test_point_data_components(self):
        assert self.voxet_instance.point_data_components == []

    # Testing setting point data name and dimensions
    def test_init_point_data(self):
        test_name = "Test_Name"
        test_dimensions = 9
        self.voxet_instance.init_point_data(data_key=test_name,  dimension=test_dimensions)

        assert self.voxet_instance.point_data_components == [test_dimensions]
        assert self.voxet_instance.point_data_keys == [test_name]

    # Testing removing point data by name
    def test_remove_point_data(self):
        test_name = "Test_Name_Bis"
        test_dimensions = 123

        # Adding an empty array with a given name and given dimensions
        self.voxet_instance.init_point_data(data_key=test_name,  dimension=test_dimensions)
        self.voxet_instance.remove_point_data(test_name)

        assert self.voxet_instance.point_data_components == []
        assert self.voxet_instance.point_data_keys == []

    # Testing get point data/shape of the vtkarray
    def test_get_point_data(self):
        test_name = "Test_Name"
        test_dimensions = 4
        shape = (0, 0, 4)
        self.voxet_instance.init_point_data(data_key=test_name,  dimension=test_dimensions)

        assert self.voxet_instance.get_point_data(test_name).shape == shape

    # Testing range of a point data
    def test_get_point_data_range(self):
        test_name = "Test_Name"
        test_dimensions = 6
        min_max = (1e+299, -1e+299)

        self.voxet_instance.init_point_data(data_key=test_name, dimension=test_dimensions)

        assert self.voxet_instance.get_point_data_range(test_name) == min_max

    # Testing cell data
    @pytest.mark.skip(reason="Cell data not implemented yet")
    def test_list_cell_data(self):
        assert ...


# Testing class XsVoxets
class TestXsVoxet:

    xs_voxet_instance = XsVoxet()

    # testing default values / initialization
    def test_bounds(self):
        assert self.xs_voxet_instance.bounds == (1.0, -1.0, 1.0, -1.0, 1.0, -1.0)

    # testing XsVoxet deep_copy
    def test_deep_copy(self):
        deep_copy = self.xs_voxet_instance.deep_copy()
        deep_copy2 = self.xs_voxet_instance.deep_copy()

        assert isinstance(deep_copy, XsVoxet)
        assert isinstance(deep_copy2, XsVoxet)
        assert deep_copy.cells_number == deep_copy2.cells_number
        assert self.xs_voxet_instance.cells_number == deep_copy2.cells_number

    # Testing standard columns_n
    def test_columns_n(self):
        assert self.xs_voxet_instance.columns_n == 0

    # Testing standard rows_n
    def test_rows_n(self):
        assert self.xs_voxet_instance.rows_n == 0
