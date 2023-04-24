import pytest
from pytest import raises
from pzero.entities_factory import VertexSet, PolyLine, TriSurf, PolyData, XsVertexSet, XsPolyLine, TetraSolid

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

    # Testing VertexSet deep_copy
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

        # calling on both vertex autocells
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

    # Testing VertexSet deep_copy
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

    # testing XSVertexSet deep_copy
    def test_deep_copy(self):
        deep_copy = self.xs_polyline_instance.deep_copy()
        deep_copy2 = self.xs_polyline_instance.deep_copy()

        assert isinstance(deep_copy, XsPolyLine)
        assert isinstance(deep_copy2, XsPolyLine)
        assert deep_copy.cells_number == deep_copy2.cells_number
        assert self.xs_polyline_instance.cells_number == deep_copy2.cells_number

