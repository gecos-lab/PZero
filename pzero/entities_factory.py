"""entities_factory.py
PZero© Andrea Bistacchi"""

from vtk import vtkPolyData, vtkPoints, vtkCellCenters, vtkIdFilter, vtkCleanPolyData, vtkPolyDataNormals, vtkPlane, vtkCellArray, vtkLine, vtkIdList, vtkTriangleFilter, vtkTriangle, vtkFeatureEdges, vtkCleanPolyData, vtkStripper, vtkPolygon, vtkUnstructuredGrid, vtkTetra, vtkImageData, vtkStructuredGrid, vtkPolyDataConnectivityFilter, vtkCylinderSource,vtkThreshold,vtkDataObject,vtkThresholdPoints,vtkDelaunay2D,vtkPolyDataMapper
from vtk.util.numpy_support import vtk_to_numpy
from vtk.numpy_interface.dataset_adapter import WrapDataObject, vtkDataArrayToVTKArray
from pyvista import PolyData as pv_PolyData
from pyvista import image_to_texture as pv_image_to_texture
from numpy import shape as np_shape
from numpy import arctan2 as np_arctan2
from numpy import arctan as np_arctan
from numpy import tan as np_tan
from numpy import cos as np_cos
from numpy import sin as np_sin
from numpy import arcsin as np_arcsin
from numpy import pi as np_pi
from numpy import empty as np_empty
from numpy import NaN as np_NaN
from numpy import squeeze as np_squeeze
from numpy import size as np_size
from numpy import asarray as np_asarray
from numpy.linalg import norm as np_linalg_norm
from numpy import cross as np_cross
from numpy import append as np_append
from numpy import array as np_array
from numpy import sign as np_sign
from numpy import sqrt as np_sqrt
from numpy import hstack as np_hstack
from numpy import column_stack as np_column_stack

"""
Some notes on the way we derive our classes from VTK.

In VTK the class vtkPolyData is implemented with four separate instances of vtkCellArray
to represent 0D vertices, 1D lines, 2D polygons, and 2D triangle strips, so it is possible to create
vtkPolyData instances that consist of a mixture of cell types. In vtkUnstructuredGrid any combination
of cells is valid, including 3D and non-linear cells. However, here we do not want to use
mixtures to be consistent with other geomodelling codes and libraries, hence we subclass vtkPolyData as PolyData
in order to obtain the standard classes VertexSet, PolyLine, and TriSurf, and vtkUnstructuredGrid as TetraSolid,
for 0D, 1D, 2D and 3D simplicial manifold objects respectively.

We also expose as much as possible VTK attributes and methods as Numpy arrays and property methods to make
the code more compact, readable and "Pythonic" (also thanks to vtk.numpy_interface.dataset_adapter = dsa).

We do not use vtkFieldData since metadata for each entity are recorded in the Pandas dataframe of the
collections for geological, cross-sections, DOMs, etc. entities. This is more flexible since field
data cannot store strings, for instance.

Non-geological objects, such as cross sections, DEMs, images, etc., are not defined in the geological classes,
even when they share the same underlying VTK topological class, due to the different modelling meaning.

Note that cell type in VTK is defined as follows (we use just a limited number of them):
// Linear cells
   VTK_EMPTY_CELL = 0,
   VTK_VERTEX = 1,
   VTK_POLY_VERTEX = 2,
   VTK_LINE = 3, __used in PZero__
   VTK_POLY_LINE = 4,
   VTK_TRIANGLE = 5, __used in PZero__
   VTK_TRIANGLE_STRIP = 6,
   VTK_POLYGON = 7,
   VTK_PIXEL = 8,
   VTK_QUAD = 9,
   VTK_TETRA = 10, __used in PZero__
   VTK_VOXEL = 11,
   VTK_HEXAHEDRON = 12,
   VTK_WEDGE = 13,
   VTK_PYRAMID = 14,
   VTK_PENTAGONAL_PRISM = 15,
   VTK_HEXAGONAL_PRISM = 16,

// Quadratic, isoparametric cells
   VTK_QUADRATIC_EDGE = 21,
   VTK_QUADRATIC_TRIANGLE = 22,
   VTK_QUADRATIC_QUAD = 23,
   VTK_QUADRATIC_POLYGON = 36,
   VTK_QUADRATIC_TETRA = 24,
   VTK_QUADRATIC_HEXAHEDRON = 25,
   VTK_QUADRATIC_WEDGE = 26,
   VTK_QUADRATIC_PYRAMID = 27,
   VTK_BIQUADRATIC_QUAD = 28,
   VTK_TRIQUADRATIC_HEXAHEDRON = 29,
   VTK_QUADRATIC_LINEAR_QUAD = 30,
   VTK_QUADRATIC_LINEAR_WEDGE = 31,
   VTK_BIQUADRATIC_QUADRATIC_WEDGE = 32,
   VTK_BIQUADRATIC_QUADRATIC_HEXAHEDRON = 33,
   VTK_BIQUADRATIC_TRIANGLE = 34,

// Cubic, isoparametric cell
   VTK_CUBIC_LINE = 35,

// Special class of cells formed by convex group of points
   VTK_CONVEX_POINT_SET = 41,

// Polyhedron cell (consisting of polygonal faces)
   VTK_POLYHEDRON = 42,

// Higher order cells in parametric form
   VTK_PARAMETRIC_CURVE = 51,
   VTK_PARAMETRIC_SURFACE = 52,
   VTK_PARAMETRIC_TRI_SURFACE = 53,
   VTK_PARAMETRIC_QUAD_SURFACE = 54,
   VTK_PARAMETRIC_TETRA_REGION = 55,
   VTK_PARAMETRIC_HEX_REGION = 56,

// Higher order cells
   VTK_HIGHER_ORDER_EDGE = 60,
   VTK_HIGHER_ORDER_TRIANGLE = 61,
   VTK_HIGHER_ORDER_QUAD = 62,
   VTK_HIGHER_ORDER_POLYGON = 63,
   VTK_HIGHER_ORDER_TETRAHEDRON = 64,
   VTK_HIGHER_ORDER_WEDGE = 65,
   VTK_HIGHER_ORDER_PYRAMID = 66,
   VTK_HIGHER_ORDER_HEXAHEDRON = 67,

// Arbitrary order Lagrange elements (formulated separated from generic higher order cells)
   VTK_LAGRANGE_CURVE = 68,
   VTK_LAGRANGE_TRIANGLE = 69,
   VTK_LAGRANGE_QUADRILATERAL = 70,
   VTK_LAGRANGE_TETRAHEDRON = 71,
   VTK_LAGRANGE_HEXAHEDRON = 72,
   VTK_LAGRANGE_WEDGE = 73,
   VTK_LAGRANGE_PYRAMID = 74,

// Arbitrary order Bezier elements (formulated separated from generic higher order cells)
   VTK_BEZIER_CURVE = 75,
   VTK_BEZIER_TRIANGLE = 76,
   VTK_BEZIER_QUADRILATERAL = 77,
   VTK_BEZIER_TETRAHEDRON = 78,
   VTK_BEZIER_HEXAHEDRON = 79,
   VTK_BEZIER_WEDGE = 80,
   VTK_BEZIER_PYRAMID = 81,
"""

"""List of valid topological types, corresponding to classes (abstract classes are not listed here)."""
valid_topological_types = ["VertexSet",
                           "PolyLine",
                           "TriSurf",
                           "TetraSolid",
                           "XsVertexSet",
                           "XsPolyLine",
                           "DEM",
                           "MapImage",
                           "XsImage",
                           "Voxet"]


class PolyData(vtkPolyData):
    """PolyData is an abstract class used as a base for all entities with a geological meaning, such as
    triangulated surfaces, polylines (also in cross sections), pointsets, etc., and possibly in other
    cases (e.g. DOMs and boundaries). Basically this is the standard vtk.PolyData class, but exposes methods from
    vtk.numpy_interface.dataset_adapter (dsa) to access points, cells, etc. as Numpy arrays instead of
    VTK arrays. Numpy arrays are just a reference to the underlying VTK arrays, so modifying in Numpy
    also modifies the VTK array and vice-versa. Property methods are used where logical and possible."""
    def __init__(self, *args, **kwargs):
        super(PolyData, self).__init__(*args, **kwargs)

    @property
    def bounds(self):
        """Returns a list with xmin, xmax, ymin, ymax, zmin, zmax."""
        return self.GetBounds()

    @property
    def points_number(self):
        """Returns the number of points."""
        return WrapDataObject(self).GetNumberOfPoints()

    @property
    def points(self):
        """Returns point coordinates as a Numpy array with columns for x, y, z."""
        return WrapDataObject(self).Points

    @points.setter
    def points(self, points_matrix=None):
        """Sets point coordinates from a Numpy array with columns for x, y, z (sets a completely new point array)."""
        WrapDataObject(self).Points = points_matrix

    @property
    def points_X(self):
        """Returns X point coordinates as Numpy array."""
        return self.points[:, 0]

    @property
    def points_Y(self):
        """Returns Y point coordinates as Numpy array"""
        return self.points[:, 1]

    @property
    def points_Z(self):
        """Returns Z point coordinates as Numpy array"""
        return self.points[:, 2]

    def append_point(self, point_vector=None):
        """Appends a single point from Numpy point_vector at the end of the VTK point array."""
        """Check that point_vector is a row vector."""
        point_vector = point_vector.flat[:]
        """Then add the point, also in case the object is still empty."""
        if self.GetNumberOfPoints() == 0:
            points = vtkPoints()
            points.InsertPoint(0, point_vector[0], point_vector[1], point_vector[2])
            self.SetPoints(points)
        else:
            self.GetPoints().InsertNextPoint(point_vector[0], point_vector[1], point_vector[2])

    """Methods get_cells(self) and append_cell(self, cell_array=None) must be implemented in specific classes,
    depending on topology. In any case cells are returned as connectivity matrices with n_rows = n_cells
    and n_columns = n_points in cell (= topological dimension for simplicial cells). The first index indicating
    the cell dimension in VTK is omitted, e.g n_ columns = 2 for PolyLine, and 3 for TriSurf."""

    @property
    def cells_number(self):
        """Returns the number of points"""
        return WrapDataObject(self).GetNumberOfCells()

    @property
    def cells(self):
        """Returns cells as Numpy array. Reimplemented in subclasses."""
        pass

    @cells.setter
    def cells(self, cells_matrix=None):  # _______________________________________________________________ this does not work - see how to fix this that is very important - possibly use VEDO or PYVISTA or BETTER numpy_to_vtk.
        """Set all cells by applying append_cell recursively"""
        if self.GetNumberOfCells() != 0:
            self.DeleteCells()  # this marks the cells to be deleted
            self.RemoveDeletedCells()  # this deletes the cells, i.e. delete the cells from the cell array
            self.Reset()  # this resets the object and updates the cell array, resulting in an object with an empty cell array
        for row in range(np_shape(cells_matrix)[0]):
            self.append_cell(cell_array=cells_matrix[row, :])

    @property
    def cell_centers(self):  # ___________________________________________________ SEEMS USEFUL BUT NOT YET USED AND TESTED
        """Returns a 3xn array of n point coordinates at the parametric center of n cells.
        This is not necessarily the same as the geometric or bonding box center."""
        vtk_cell_ctrs = vtkCellCenters()
        vtk_cell_ctrs.SetInputConnection(self.outputPort)
        vtk_cell_ctrs.Update()
        point_ctrs = vtk_cell_ctrs.GetOutput()
        centers_array = np_array([point_ctrs.GetPoint(i) for i in range(point_ctrs.GetNumberOfPoints())])
        return centers_array

    def ids_to_scalar(self):
        """Store point and cell ids on scalars named "vtkIdFilter_Ids".
        vtkIdFilter is a filter that generates scalars or field data using cell and point ids.
        That is, the point attribute data scalars or field data are generated from the point ids,
        and the cell attribute data scalars or field data are generated from the cell ids.
        In theory one could decide to record only point or cell ids using PointIdsOn/Off and CellIdsOn/Off.
        Here we use the default name for the scalar storing the ids, that is "vtkIdFilter_Ids", but
        in theory this could be changed with SetPointIdsArrayName(<new_name>) and
        SetCellIdsArrayName(<new_name>). In this case also the last lines must be modified accordingly."""
        """Run the filter."""
        id_filter = vtkIdFilter()
        id_filter.SetInputData(self)
        id_filter.PointIdsOn()
        id_filter.CellIdsOn()
        id_filter.Update()
        """Update the input polydata "self" with the new scalars."""
        self.GetPointData().SetScalars(id_filter.GetOutput().GetPointData().GetArray("vtkIdFilter_Ids"))
        self.GetCellData().SetScalars(id_filter.GetOutput().GetCellData().GetArray("vtkIdFilter_Ids"))
        self.Modified()

    def clean_topology(self):
        """Clean topology with vtkCleanPolyData.
        The filter is set up in order to DO NOT transform degenerate cells into
        lower order ones (e.g. triangle into a line if two points are merged), and to
        use tolerance = 0.0 which is faster."""
        """Run the filter."""
        clean_filter = vtkCleanPolyData()
        clean_filter.SetInputData(self)
        clean_filter.ConvertLinesToPointsOff()
        clean_filter.ConvertPolysToLinesOff()
        clean_filter.ConvertStripsToPolysOff()
        clean_filter.PointMergingOn()
        clean_filter.SetTolerance(0.0)
        clean_filter.Update()
        """Replace the input polydata "self" with the clean one."""
        self = clean_filter.GetOutput()
        self.Squeeze()
        self.Modified()

    def vtk_set_normals(self):
        """Calculate point and cell normals with vtkPolyDataNormals.
        The name of the arrays is "Normals", so they can be retrieved either with
        normals_filter.GetOutput().GetPointData().GetNormals() or with
        normals_filter.GetOutput().GetPointData().GetArray("Normals")
        Point normals are computed by averaging neighbor polygon cell normals.
        Note that we use AutoOrientNormalsOff() since this would assume completely
        closed surfaces. Instead we use ConsistencyOn() and NonManifoldTraversalOff()
        to prevent problems where the consistency of polygonal ordering is corrupted
        due to topological loops. See details in Chapter 9 of VTK textbook."""
        """Run the filter."""
        normals_filter = vtkPolyDataNormals()
        normals_filter.SetInputData(self)
        normals_filter.ComputePointNormalsOn()
        normals_filter.ComputeCellNormalsOn()
        normals_filter.SplittingOff()
        normals_filter.ConsistencyOn()
        normals_filter.AutoOrientNormalsOff()
        normals_filter.NonManifoldTraversalOff()
        normals_filter.Update()
        """Update the input polydata "self" with the new normals."""
        self.GetPointData().SetNormals(normals_filter.GetOutput().GetPointData().GetNormals())
        self.GetCellData().SetNormals(normals_filter.GetOutput().GetCellData().GetNormals())
        self.Modified()

    @property
    def points_map_dip_azimuth(self):
        """Returns dip azimuth as Numpy array for map plotting if points have Normals property."""
        if "Normals" in self.point_data_keys:
            if len(np_shape(self.get_point_data("Normals")))>=2:
                map_dip_azimuth = np_arctan2(self.get_point_data("Normals")[:, 0], self.get_point_data("Normals")[:, 1]) * 180 / np_pi - 180
            else:
                map_dip_azimuth = np_arctan2(self.get_point_data("Normals")[0], self.get_point_data("Normals")[1]) * 180 / np_pi - 180
            return map_dip_azimuth
        else:
            return None

    @property
    def points_map_dip(self):
        """Returns dip as Numpy array for map plotting if points have Normals property."""
        if "Normals" in self.point_data_keys:
            #problem with one point objects -> np_squeeze (called in get_point_data) returns a (3, ) array instead of a (n,3) array.
            if len(np_shape(self.get_point_data("Normals")))>=2:

                map_dip = 90 - np_arcsin(-self.get_point_data("Normals")[:, 2]) * 180 / np_pi
            else:
                map_dip = 90 - np_arcsin(-self.get_point_data("Normals")[2]) * 180 / np_pi
            return map_dip
        else:
            return None

    @property
    def points_map_trend(self):
        """Returns trend as Numpy array for map plotting if points have Lineations property."""
        if "Lineations" in self.point_data_keys:
            map_trend = np_arctan2(self.get_point_data("Lineations")[:, 0], self.get_point_data("Lineations")[:, 1]) * 180 / np_pi
            return map_trend
        else:
            return None

    @property
    def points_map_plunge(self):
        """Returns plunge as Numpy array for map plotting if points have Lineations property."""
        if "Lineations" in self.point_data_keys:
            map_plunge = np_arcsin(-self.get_point_data("Lineations")[:, 2]) * 180 / np_pi
            return map_plunge
        else:
            return None

    @property
    def point_data_keys(self):
        """Lists point data keys, if present (except handles the case of objects with no properties)."""
        try:
            return WrapDataObject(self).PointData.keys()
        except:
            return []

    def init_point_data(self, data_key=None, dimension=None):
        """Creates a new point data attribute with name = data_key
        as an empty Numpy array with dimension = 1, 2, 3, 4, 6, or 9.
        These are the only dimensions accepted by VTK arrays."""
        if dimension not in [1, 2, 3, 4, 6, 9]:
            print("Error - dimension not in [1, 2, 3, 4, 6, 9]")
            return
        nan_array = np_empty((self.points_number, dimension))
        nan_array[:] = np_NaN
        WrapDataObject(self).PointData.append(nan_array, data_key)

    def remove_point_data(self, data_key=None):
        """Removes a point data attribute with name = data_key."""
        self.GetPointData().RemoveArray(data_key)

    def get_point_data(self, data_key=None):  # _________________________________________________________ CHECK THIS - PROBABLY reshape SHOULD APPLY TO ALL CASES
        """Returns a point data attribute as Numpy array. This cannot be converted to
        a property method since the key of the attribute must be specified."""
        # if isinstance(self, (VertexSet, PolyLine, TriSurf, XsVertexSet, XsPolyLine)):
        """For vector entities return a n-by-m-dimensional array where n is the
        number of points and m is the number of components of the attribute.
        Reshape is needed since the Numpy array returned by dsa is "flat" as a standard VTK array."""
        point_data = WrapDataObject(self).PointData[data_key].reshape((self.get_point_data_shape(data_key=data_key)[0], self.get_point_data_shape(data_key=data_key)[1]))
        # elif isinstance(self, PolyData):
        #     """For point entities we don't need to reshape"""
        #     point_data = WrapDataObject(self).PointData[data_key]
        """We use np_squeeze to remove axes with length 1, so a 1D array will be returned with shape (n, ) and not with shape (n, 1)."""
        #The np_array is sometimes necessary. Without it in some cases this error occures: ndarray subclass __array_wrap__ method returned an object which was not an instance of an ndarray subclass
        return np_squeeze(np_array(point_data))

    def get_point_data_shape(self, data_key=None):
        """Returns the shape of a point data attribute matrix."""
        # if isinstance(self, (VertexSet, PolyLine, TriSurf, XsVertexSet, XsPolyLine, PCDom)):
        """For vector entities we have attribute arrays of the same length as the number of points.
        This method yields the number of points and the number of components of the attribute."""
        n_points = np_shape(WrapDataObject(self).PointData[data_key])[0]
        """The following solves the problem of Numpy returning just the length for 1D arrays."""
        try:
            n_components = np_shape(WrapDataObject(self).PointData[data_key])[1]
        except:
            n_components = 1
        return [n_points, n_components]

    def get_point_data_type(self, data_key=None):
        """Get point data type."""
        return WrapDataObject(self).PointData[data_key].dtype.name

    def set_point_data(self, data_key=None, attribute_matrix=None):  # _____________________________________________ REVEL CITED HERE TO FLATTEN THE ARRAY AND THEN NOT USED?
        """Sets point data attribute from Numpy array (sets a completely new point attributes array)
        Applying ravel to the input n-d array is required to flatten the array as in VTK arrays
        (see also reshape in get_point_data)."""
        WrapDataObject(self).PointData.append(attribute_matrix, data_key)

    def edit_point_data(self, data_key=None, point_id=None, point_data_array=None):
        """Edits the data attribute of a single point from point_id and Numpy point_data_array"""
        point_data_array = point_data_array.flat[:]  # to be sure that point_vector is a row vector
        for col in range(np_size(point_data_array)):
            WrapDataObject(self).PointData[data_key][point_id, col] = point_data_array[col]

    def set_tag(self,tag_name):
        self.init_point_data(f'tag_{tag_name}',1)

    def list_cell_data(self):  # _______________________ TO BE IMPLEMENTED IF WE WANT TO WORK WITH CELL DATA
        """Lists cell attribute names"""
        pass

    def init_cell_data(self, parent=None, data_key=None, dimension=None):  # _______________________ TO BE IMPLEMENTED IF WE WANT TO WORK WITH CELL DATA
        """Creates a new cell attribute with name = data_key
        as an empty Numpy array with dimension = 1, 2, 3, 4, 6, or 9"""
        # print("cell data init:\n", self.get_cell_data(data_key))
        pass

    def remove_cell_data(self, parent=None, data_key=None):  # _______________________ TO BE IMPLEMENTED IF WE WANT TO WORK WITH CELL DATA
        """Remove a cell attribute"""
        pass

    def get_cell_data(self, parent=None, data_key=None):  # _______________________ TO BE IMPLEMENTED IF WE WANT TO WORK WITH CELL DATA
        """Returns cell attribute as Numpy array"""
        pass

    def set_cell_data(self, parent=None, data_key=None, attribute_matrix=None):  # _______________________ TO BE IMPLEMENTED IF WE WANT TO WORK WITH CELL DATA
        """Sets cell attribute from Numpy array"""
        pass

    def edit_cell_data(self, parent=None, data_key=None, cell_id=None, cell_data_array=None):  # _______________________ TO BE IMPLEMENTED IF WE WANT TO WORK WITH CELL DATA
        """Sets cell attribute from Numpy array"""
        pass

    @property
    def topological_type(self):
        for topological_type in valid_topological_types:
            """Here we use eval to convert a string with the class name to the class itself."""
            if isinstance(self, eval(topological_type)):
                return topological_type
            else:
                return None

    def connected_calc(self):
        """Adds a scalar property called RegionId with the connected region index, useful for processing and
        visualization (it will be automatically added to the properties legend).
        Also returns the number of connected regions.
        Returns None in case it is called for a VertexSet, so it works for PolyLine and TriSurf only."""
        if not isinstance(self, VertexSet):
            connectivity_filter = vtkPolyDataConnectivityFilter()
            connectivity_filter.SetInputData(self)
            connectivity_filter.SetExtractionModeToAllRegions()
            connectivity_filter.ColorRegionsOn()
            connectivity_filter.Update()
            num_regions = connectivity_filter.GetNumberOfExtractedRegions()
            self.GetPointData().SetScalars(connectivity_filter.GetOutput().GetPointData().GetScalars())
            return num_regions

    def split_parts(self):
        """Splits connected parts using RegionId from self.connected_calc().
        Also returns the number of connected regions.
        Returns None in case it is called for a VertexSet, so it works for PolyLine and TriSurf only."""
        if isinstance(self, (PolyLine, TriSurf)):
            connectivity_filter = vtkPolyDataConnectivityFilter()
            connectivity_filter.SetInputData(self)
            connectivity_filter.SetExtractionModeToAllRegions()
            connectivity_filter.ColorRegionsOn()
            connectivity_filter.Update()
            connectivity_filter.SetExtractionModeToSpecifiedRegions()
            num_regions = connectivity_filter.GetNumberOfExtractedRegions()
            vtk_out_list = []
            for rid in range(num_regions):
                connectivity_filter.InitializeSpecifiedRegionList()
                connectivity_filter.AddSpecifiedRegion(rid)
                connectivity_filter.Update()
                cleaner = vtkCleanPolyData()
                cleaner.SetInputConnection(connectivity_filter.GetOutputPort())
                cleaner.Update()
                if isinstance(self, PolyLine):
                    vtk_out_obj = PolyLine()
                elif isinstance(self, TriSurf):
                    vtk_out_obj = TriSurf()
                vtk_out_obj.DeepCopy(cleaner.GetOutput())
                vtk_out_list.append(vtk_out_obj)
            return vtk_out_list



class Plane(vtkPlane):  # _______________________ AT THE MOMENT THIS DOES NOT EXPOSE ANY OTHER METHOD - SEE IF IT IS USEFUL
    """Plane is a class used as a base for cross-section planes. Basically this is the standard vtkPlane
    class, but exposes methods from vtk.numpy_interface.dataset_adapter (dsa) to access data as Numpy
    arrays instead of VTK arrays. Numpy arrays are just a reference to the underlying VTK arrays, so
    modifying in Numpy also modifies the VTK array and vice-versa. Property methods are used where
    logical and possible."""
    def __init__(self, *args, **kwargs):
        super(Plane, self).__init__(*args, **kwargs)


class VertexSet(PolyData):
    """VertexSet is a set of points, e.g. a point cloud, derived from BaseEntity and vtkPolyData"""
    def __init__(self, *args, **kwargs):
        super(VertexSet, self).__init__(*args, **kwargs)

    def deep_copy(self):
        vset_copy = VertexSet()
        vset_copy.DeepCopy(self)
        return vset_copy

    def auto_cells(self):
        """Set cells automatically assuming that the vertexes are in the correct order,
        from first to last, and that the polyline is a single part."""
        if self.GetNumberOfCells() != 0:
            """Remove all cells. This is obtained calling DeleteCells without any
            argument and in this case RemoveDeletedCells() is not necessary."""
            self.DeleteCells()
            self.GetVerts().Modified()



        vertices = vtkCellArray() #[Gabriele] vertices (cells)
        npoints = self.points_number # [Gabriele] Points present in the object
        cellIds = [0]
        for pid in range(npoints):
            cellIds[0] = pid
            vertices.InsertNextCell(1,cellIds)
        self.SetVerts(vertices) #[Gabriele] Assign the vertices to the point_cloud (vtkPolyData)
        self.Modified()


class PolyLine(PolyData):
    """PolyLine is a polyline derived from BaseEntity and vtkPolyData"""
    def __init__(self, *args, **kwargs):
        super(PolyLine, self).__init__(*args, **kwargs)

    def deep_copy(self):
        pline_copy = PolyLine()
        pline_copy.DeepCopy(self)
        return pline_copy

    @property
    def cells(self):
        """Returns cells as Numpy array.
        In PolyLine the cells are instances of vtkLine identified by vtkCellType VTK_LINE = 3"""
        return (vtkDataArrayToVTKArray(self.GetLines().GetData())).reshape((self.GetNumberOfLines(), 3))[:, 1:3]

    def append_cell(self, cell_array=None):
        """Appends a single line cell from Numpy array with vertex ids."""
        cell_array = cell_array.flat[:]  # to be sure that point_vector is a row vector
        line = vtkLine()
        line.GetPointIds().SetId(0, cell_array[0])
        line.GetPointIds().SetId(1, cell_array[1])
        if self.GetNumberOfCells() == 0:
            pline_cells = vtkCellArray()
            pline_cells.InsertNextCell(line)
            self.SetLines(pline_cells)
        else:
            self.GetLines().InsertNextCell(line)
        self.GetLines().Modified()

    def auto_cells(self):
        """Set cells automatically assuming that the vertexes are in the correct order,
        from first to last, and that the polyline is a single part."""
        if self.GetNumberOfCells() != 0:
            """Remove all cells. This is obtained calling DeleteCells without any
            argument and in this case RemoveDeletedCells() is not necessary."""
            self.DeleteCells()
            self.GetLines().Modified()
        pline_cells = vtkCellArray()
        for point in range(self.points_number-1):
            line = vtkLine()
            line.GetPointIds().SetId(0, point)
            line.GetPointIds().SetId(1, point+1)
            pline_cells.InsertNextCell(line)
        self.SetLines(pline_cells)
        self.BuildLinks()
        self.GetLines().Modified()

    def sort_nodes(self):
        """Sort nodes from the first node in the first cell to the last node in the last cell."""
        if self.GetNumberOfCells() != 0:
            """First ensure cells are simple two-point-lines with poly2lines."""
            self.poly2lines()
            """Then do the sorting. This works defining an empty list of point ids,
            that is filled for every line, and then only the first point is used,
            except for the last step, after the end of the for loop."""
            new_points = vtkPoints()
            for line_id in range(self.cells_number):
                line_points_list = vtkIdList()
                self.GetCellPoints(line_id, line_points_list)
                point_0_id = line_points_list.GetId(0)
                point_0 = self.GetPoint(point_0_id)
                new_points.InsertNextPoint(point_0)
            point_1_id = line_points_list.GetId(1)
            point_1 = self.GetPoint(point_1_id)
            new_points.InsertNextPoint(point_1)
            self.SetPoints(new_points)
            self.auto_cells()

    def poly2lines(self):
        """Split polyline cells into single two-points lines
        with vtkTriangleFilter() that always outputs simplicial cells."""
        trgl_filter = vtkTriangleFilter()
        trgl_filter.SetInputData(self)
        trgl_filter.PassLinesOn()
        trgl_filter.Update()
        self.SetLines(trgl_filter.GetOutput().GetLines())
        self.BuildLinks()
        self.Modified()


class TriSurf(PolyData):
    """TriSurf is a triangulated surface, derived from BaseEntity and vtkPolyData"""
    def __init__(self, *args, **kwargs):
        super(TriSurf, self).__init__(*args, **kwargs)

    def deep_copy(self):
        trisurf_copy = TriSurf()
        trisurf_copy.DeepCopy(self)
        return trisurf_copy

    @property
    def cells(self):
        """Returns cells as Numpy array.
        In TriSurf the cells are instances of vtkTriangle identified by vtkCellType VTK_TRIANGLE = 5"""
        return (vtkDataArrayToVTKArray(self.GetPolys().GetData())).reshape((self.GetNumberOfPolys(), 4))[:, 1:4]

    def append_cell(self, cell_array=None):
        """Appends a single simplicial cell from Numpy. The element size is inferred from the array size:
        2 > line, 3 > triangle, 4 > tetrahedron."""
        cell_array = cell_array.flat[:]  # to be sure that point_vector is a row vector
        triangle = vtkTriangle()
        triangle.GetPointIds().SetId(0, cell_array[0])
        triangle.GetPointIds().SetId(1, cell_array[1])
        triangle.GetPointIds().SetId(2, cell_array[2])
        if self.GetNumberOfCells() == 0:
            surf_cells = vtkCellArray()
            surf_cells.InsertNextCell(triangle)
            self.SetPolys(surf_cells)
        else:
            self.GetPolys().InsertNextCell(triangle)

    def get_clean_boundary(self):
        """Gets the clean boundary both in case of single- and multi-part TriSurf's."""
        """Find edges"""
        edges = vtkFeatureEdges()
        edges.BoundaryEdgesOn()
        edges.NonManifoldEdgesOff()
        edges.FeatureEdgesOff()
        edges.ManifoldEdgesOff()
        edges.SetInputData(self)
        edges.Update()
        """Clean edges"""
        edges_clean = vtkCleanPolyData()
        edges_clean.ConvertLinesToPointsOff()
        edges_clean.ConvertPolysToLinesOff()
        edges_clean.ConvertStripsToPolysOff()
        edges_clean.SetTolerance(0.0)
        edges_clean.SetInputConnection(edges.GetOutputPort())
        edges_clean.Update()
        """Strips clean edges"""
        edges_clean_strips = vtkStripper()
        edges_clean_strips.JoinContiguousSegmentsOn()
        edges_clean_strips.SetInputConnection(edges_clean.GetOutputPort())
        edges_clean_strips.Update()
        """Double cleaning before and after stripper reduces errors and problems."""
        edges_clean_strips_clean = vtkCleanPolyData()
        edges_clean_strips_clean.ConvertLinesToPointsOff()
        edges_clean_strips_clean.ConvertPolysToLinesOff()
        edges_clean_strips_clean.ConvertStripsToPolysOff()
        edges_clean_strips_clean.SetTolerance(0.0)
        edges_clean_strips_clean.SetInputConnection(edges_clean_strips.GetOutputPort())
        edges_clean_strips_clean.Update()
        """Assemble borders."""
        border_polygons = vtkCellArray()
        border_polygons.SetNumberOfCells(edges_clean_strips_clean.GetOutput().GetNumberOfCells())
        border_points = vtkPoints()
        points_in_border = 0
        for cell in range(edges_clean_strips_clean.GetOutput().GetNumberOfCells()):
            if edges_clean_strips_clean.GetOutput().GetCell(cell).GetNumberOfPoints() >= 3:
                polygon = vtkPolygon()
                polygon.GetPointIds().SetNumberOfIds(edges_clean_strips_clean.GetOutput().GetCell(cell).GetNumberOfPoints())
                for point_in_cell in range(edges_clean_strips_clean.GetOutput().GetCell(cell).GetNumberOfPoints()):
                    point_in_border = point_in_cell + points_in_border
                    border_points.InsertNextPoint(edges_clean_strips_clean.GetOutput().GetCell(cell).GetPoints().GetPoint(point_in_cell))
                    polygon.GetPointIds().SetId(point_in_cell, point_in_border)
                border_polygons.InsertNextCell(polygon)
                points_in_polygon = polygon.GetNumberOfPoints()
                points_in_border += points_in_polygon
            else:
                print("cell: ", cell, " - degenerate cell with less than 3 points.")
        borders = vtkPolyData()
        borders.SetPoints(border_points)
        borders.SetPolys(border_polygons)
        borders.Modified()
        return borders

    def boundary_dilation(self, tol=1.0):
        """Returns a deep copy of the input TriSurf with the boundary edges translated
        outwards, parallel to the cell plane, by an amount equal to tol.
        This is similar to a dilation or a Minkowski sum."""
        """Deep copy the input TriSurf, in order not to permanently modify it."""
        trisurf_copy = self.deep_copy()
        """Clean topology, store point and cell ids on scalars named vtkIdFilter_Ids."""
        trisurf_copy.clean_topology()
        trisurf_copy.BuildCells()
        trisurf_copy.BuildLinks()
        trisurf_copy.ids_to_scalar()
        """Extract boundary cells from the trisurf_copy painted with vtkIdFilter_Ids"""
        edges_filter = vtkFeatureEdges()
        edges_filter.BoundaryEdgesOn()
        edges_filter.NonManifoldEdgesOff()
        edges_filter.FeatureEdgesOff()
        edges_filter.ManifoldEdgesOff()
        edges_filter.SetInputData(trisurf_copy)
        edges_filter.Update()
        edges = edges_filter.GetOutput()
        """Extract a Numpy array of boundary point ids, and use it to build a vtkIdList.
        Use the for loop to insert ids since the SetArray VTK method does not work."""
        bnd_pt_ids_narray = WrapDataObject(edges).PointData["vtkIdFilter_Ids"]
        edges_points_n = len(bnd_pt_ids_narray)
        bnd_pt_ids = vtkIdList()
        for bnd_pt_id in bnd_pt_ids_narray:
            bnd_pt_ids.InsertNextId(bnd_pt_id)
        """For each point, find the cells and edges, then calculate the dilation vector from each
        pair of edge and center-to-edge unit vectors, and normalize the dilation vector to have norm = tol.
        The transformation is applied at the end with displace_boundary_points_array in order not to alter
        point coordinates within the loop. In early attempts I used the VTK methods ComputeCentroid() and Normals()
        but the first does not return the true center of the triangle, and the second results in uncertainties
        if pointing upwards or downwards."""
        displace_boundary_points_array = np_empty((0, 4), dtype=float)
        for p_i in range(edges_points_n):
            """Loop over edge points."""
            point_id = bnd_pt_ids.GetId(p_i)
            point_displ = np_zeros(3)
            """Get list of cells that share the point as vtkIdList."""
            point_cells_ids = vtkIdList()
            trisurf_copy.GetPointCells(point_id, point_cells_ids)
            n_point_cells = point_cells_ids.GetNumberOfIds()
            for c_i in range(n_point_cells):
                """Loop over cells (triangles)."""
                cell_id = point_cells_ids.GetId(c_i)
                """Get the other two points in this triangle."""
                trgl_point_ids = vtkIdList()
                trisurf_copy.GetCellPoints(cell_id, trgl_point_ids)
                """Use the mean value of vertex coordinates to calculate the triangle center. The ComputeCentroid() VTK method yields incorrect centres not contained in the triangle plane."""
                trgl_ctr = (np_asarray(trisurf_copy.GetPoint(trgl_point_ids.GetId(0))) + np_asarray(trisurf_copy.GetPoint(trgl_point_ids.GetId(1))) + np_asarray(trisurf_copy.GetPoint(trgl_point_ids.GetId(2)))) / 3
                for e_i in range(3):
                    """Loop over edge points."""
                    edge_point_id = trgl_point_ids.GetId(e_i)
                    if edge_point_id != point_id:
                        """Exclude the cell points excluding the point to be displaced itself."""
                        edge_cells_ids = vtkIdList()
                        trisurf_copy.GetCellEdgeNeighbors(cell_id, point_id, edge_point_id, edge_cells_ids)
                        if edge_cells_ids.GetNumberOfIds() == 0:
                            """Process only points on a boundary edge."""
                            """Coordinates of the point to be displaced."""
                            point_xyz = np_asarray(trisurf_copy.GetPoint(point_id))
                            """Coordinates of the point at the other end of the edge."""
                            edge_point = np_asarray(trisurf_copy.GetPoint(edge_point_id))
                            """Unit vector oriented as the edge."""
                            edge_vector = edge_point - point_xyz
                            edge_vector = edge_vector / np_linalg_norm(edge_vector)
                            """Center of the edge."""
                            edge_ctr = (edge_point + point_xyz) / 2
                            """Vector connecting the center of the triangle with the center of the edge, normalized to unit vector."""
                            center2edge_vector = edge_ctr - trgl_ctr
                            center2edge_vector = center2edge_vector / np_linalg_norm(center2edge_vector)
                            """Unit vector perpendicular to the edge and the triangle plane."""
                            trgl_normal = np_cross(edge_vector, center2edge_vector)
                            trgl_normal = trgl_normal / np_linalg_norm(trgl_normal)
                            """Unit vector perpendicular to the edge and parallel to the triangle plane, pointing outwards."""
                            edge_displ = np_cross(trgl_normal, edge_vector)
                            edge_displ = edge_displ / np_linalg_norm(edge_displ)
                            """Add this vector to the total displacement to be applied to this point."""
                            point_displ = point_displ + edge_displ
            """Normalize the displacement, scale by tol, and record all in an array to be used later on."""
            point_displ = point_displ / np_linalg_norm(point_displ) * tol
            displace_boundary_points_array = np_append(displace_boundary_points_array, np_array([[point_id, point_displ[0], point_displ[1], point_displ[2]]]), axis=0)
        for row in displace_boundary_points_array:
            """Here we perform the dilation, on the points and with the vectors stored in displace_boundary_points_array.
            Converting the first column to integer is needed since Numpy arrays store homogeneous objects, hence the point
            indexes are stored in the array as floats."""
            point_idx = int(row[0])
            trisurf_copy.points_X[point_idx] = trisurf_copy.points_X[point_idx] + row[1]
            trisurf_copy.points_Y[point_idx] = trisurf_copy.points_Y[point_idx] + row[2]
            trisurf_copy.points_Z[point_idx] = trisurf_copy.points_Z[point_idx] + row[3]
        trisurf_copy.Modified()
        return trisurf_copy

class XSectionBaseEntity:
    """This abstract class is used just to implement the method to calculate the W coordinate for all geometrical/topological entities belonging to a XSection.
    We store a reference to parent - the project, and to the x_section_uid in order to be able to use property methods below."""
    def __init__(self, x_section_uid=None, parent=None, *args, **kwargs):
        self.x_section_uid = x_section_uid
        self.parent = parent

    @property
    def points_W(self):
        """Returns W coordinate (distance along the Xsection horizontal axis) from X and Y coordinates of the entity."""
        x_section_base_x = self.parent.xsect_coll.get_uid_base_x(self.x_section_uid)
        x_section_base_y = self.parent.xsect_coll.get_uid_base_y(self.x_section_uid)
        x_section_end_x = self.parent.xsect_coll.get_uid_end_x(self.x_section_uid)
        x_section_end_y = self.parent.xsect_coll.get_uid_end_y(self.x_section_uid)
        sense = np_sign((self.points_X - x_section_base_x) * (x_section_end_x - x_section_base_x) + (self.points_Y - x_section_base_y) * (x_section_end_y - x_section_base_y))
        return np_sqrt((self.points_X - x_section_base_x) ** 2 + (self.points_Y - x_section_base_y) ** 2) * sense

    @property
    def points_xs_app_dip(self):
        """Returns apparent dip as Numpy array for map plotting if points have Normals property."""
        if "Normals" in self.point_data_keys:
            xs_azimuth = self.parent.xsect_coll.get_uid_azimuth(self.x_section_uid)
            app_dip = np_arctan(np_tan(self.points_map_dip * np_pi/180) * np_cos((self.points_map_dip_azimuth - xs_azimuth) * np_pi/180)) * 180 / np_pi
            return app_dip
        else:
            return None

    @property
    def points_xs_app_plunge(self):
        """Returns apparent plunge as Numpy array for map plotting if points have Lineations property."""
        if "Lineations" in self.point_data_keys:
            xs_azimuth = self.parent.xsect_coll.get_uid_azimuth(self.x_section_uid)
            app_plunge = np_arctan(np_tan(self.points_map_plunge * np_pi/180) * np_cos((self.points_map_trend - xs_azimuth) * np_pi/180)) * 180 / np_pi
            return app_plunge
        else:
            return None


class XsVertexSet(VertexSet, XSectionBaseEntity):
    """XsVertexSet is a set of points, e.g. a point cloud, belonging to a unique XSection, derived from XSectionBaseEntity and VertexSet"""
    def __init__(self, *args, **kwargs):
        super(XsVertexSet, self).__init__(*args, **kwargs)

    def deep_copy(self):
        xvset_copy = XsVertexSet()
        xvset_copy.DeepCopy(self)
        return xvset_copy


class XsPolyLine(PolyLine, XSectionBaseEntity):
    """XsPolyLine is a polyline belonging to a unique XSection, derived from XSectionBaseEntity and PolyLine"""
    def __init__(self, *args, **kwargs):
        super(XsPolyLine, self).__init__(*args, **kwargs)

    def deep_copy(self):
        xpline_copy = XsPolyLine()
        xpline_copy.DeepCopy(self)
        return xpline_copy


class XsTriSurf(TriSurf, XSectionBaseEntity):  # ______________________________________ NOT YET USED - SEE IF THIS IS USEFUL
    """XsTriSurf is a triangulated surface belonging to a unique XSection, derived from XSectionBaseEntity and TriSurf"""
    def __init__(self, *args, **kwargs):
        super(XsTriSurf, self).__init__(*args, **kwargs)

    def deep_copy(self):
        xtsurf_copy = XsTriSurf()
        xtsurf_copy.DeepCopy(self)
        return xtsurf_copy


class TetraSolid(vtkUnstructuredGrid):  # ______________________________________ NOT YET USED - EVERYTHING MUST BE CHECKED - ADD METHODS SIMILAR TO POLYDATA
    """TetraSolid is a tetrahedral mesh, derived from vtkUnstructuredGrid"""
    def __init__(self, *args, **kwargs):
        super(TetraSolid, self).__init__(*args, **kwargs)

    def deep_copy(self):
        tsolid_copy = TetraSolid()
        tsolid_copy.DeepCopy(self)
        return tsolid_copy

    @property
    def cells(self):
        """Returns cells as Numpy array
        In TetraSolid the cells are instances of vtkTetra identified by vtkCellType VTK_TETRA = 10"""
        return (vtkDataArrayToVTKArray(self.GetPolys().GetData())).reshape((self.GetNumberOfPolys(), 5))[:, 1:5]

    def append_cell(self, cell_array=None):
        """Appends a single tetrahedral cell from 4 x 1 Numpy array with node indexes of the four nodes of the tetrahedron."""
        cell_array = cell_array.flat[:]  # to be sure that point_vector is a row vector
        tetra = vtkTetra()
        tetra.GetPointIds().SetId(0, cell_array[0])
        tetra.GetPointIds().SetId(1, cell_array[1])
        tetra.GetPointIds().SetId(2, cell_array[2])
        tetra.GetPointIds().SetId(3, cell_array[3])
        if self.GetNumberOfCells() == 0:
            solid_cells = vtkCellArray()
            solid_cells.InsertNextCell(tetra)
            self.SetCells(solid_cells)
        else:
            self.GetCells().InsertNextCell(tetra)

    def get_clean_boundary(self):
        """Returns vtkPolydata polyline(s) with boundary edges."""
        edges = vtkFeatureEdges()
        edges.BoundaryEdgesOn()
        edges.NonManifoldEdgesOff()
        edges.FeatureEdgesOff()
        edges.ManifoldEdgesOff()
        edges.SetInputData(self)
        edges.Update()
        return edges.GetOutput()


class Voxet(vtkImageData):  # _______________________________________________ SEE IF POINT METHODS MAKE SENSE HERE - NOW COMMENTED
    """Voxet is a 3D image, derived from BaseEntity and vtkImageData"""
    """Add methods similar to PolyData for points."""
    def __init__(self, *args, **kwargs):
        super(Voxet, self).__init__(*args, **kwargs)

    def deep_copy(self):
        voxet_copy = Voxet()
        voxet_copy.DeepCopy(self)
        return voxet_copy

    @property
    def bounds(self):
        """Returns a list with xmin, xmax, ymin, ymax, zmin, zmax"""
        return self.GetBounds()

    @property
    def origin(self):
        """Set/Get the origin of the dataset. The origin is the position in world coordinates of the point of
        extent (0,0,0). This point does not have to be part of the dataset, in other words, the dataset extent
        does not have to start at (0,0,0) and the origin can be outside of the dataset bounding box. The origin
        plus spacing determine the position in space of the points."""
        return self.GetOrigin()

    @origin.setter
    def origin(self, vector=None):
        """Set/Get the origin of the dataset. The origin is the position in world coordinates of the point of
        extent (0,0,0). This point does not have to be part of the dataset, in other words, the dataset extent
        does not have to start at (0,0,0) and the origin can be outside of the dataset bounding box. The origin
        plus spacing determine the position in space of the points."""
        self.SetOrigin(vector)

    @property
    def direction_matrix(self):
        """Set/Get the direction transform of the dataset. The direction matrix is
        a 3x3 transformation matrix supporting scaling and rotation."""
        return self.GetDirectionMatrix()

    @direction_matrix.setter
    def direction_matrix(self, matrix=None):
        """Set/Get the direction transform of the dataset. The direction matrix is
        a 3x3 transformation matrix supporting scaling and rotation."""
        self.SetDirectionMatrix(matrix)

    @property
    def spacing(self):
        """Get/set the spacing (width,height,length) of the cubical cells that compose the data set."""
        return self.GetSpacing()

    @spacing.setter
    def spacing(self, array=None):
        """Get/set the spacing (width,height,length) of the cubical cells that compose the data set."""
        return self.SetSpacing(array)

    @property
    def dimensions(self):
        """Get/set dimensions of this structured points dataset. This is the number
        of points on each axis. Dimensions are computed from Extents during this call."""
        return self.GetDimensions()

    @dimensions.setter
    def dimensions(self, array=None):
        """Get/set dimensions of this structured points dataset. This is the number
        of points on each axis. Dimensions are computed from Extents during this call."""
        return self.SetDimensions(array)

    @property
    def U_n(self):
        return self.dimensions[0]

    @property
    def V_n(self):
        return self.dimensions[1]

    @property
    def W_n(self):
        return self.dimensions[2]

    @property
    def U_step(self):
        return self.spacing[0]

    @property
    def V_step(self):
        return self.spacing[1]

    @property
    def W_step(self):
        return self.spacing[2]

    @property
    def points_number(self):
        return self.GetNumberOfPoints()

    # @property
    # def points(self):
    #     """Returns point coordinates as a Numpy array
    #     NOT SURE IF THIS WORKS FOR IMAGE"""
    #     return WrapDataObject(self).Points
    #
    # @property
    # def points_X(self):
    #     """Returns X point coordinates as Numpy array
    #     NOT SURE IF THIS WORKS FOR IMAGE"""
    #     return self.points[:, 0]
    #
    # @property
    # def points_Y(self):
    #     """Returns Y point coordinates as Numpy array
    #     NOT SURE IF THIS WORKS FOR IMAGE"""
    #     return self.points[:, 1]
    #
    # @property
    # def points_Z(self):
    #     """Returns Z point coordinates as Numpy array
    #     NOT SURE IF THIS WORKS FOR IMAGE"""
    #     return self.points[:, 2]

    @property
    def cells_number(self):
        return self.GetNumberOfCells()

    @property
    def cells(self):
        """Returns cells as Numpy array.
        TO BE IMPLEMENTED"""
        pass

    @property
    def point_data_keys(self):
        """Lists point data keys"""
        try:
            return WrapDataObject(self).PointData.keys()
        except:
            return []

    @property
    def point_data_components(self):
        """Lists point data components.
        CHECK IF THIS DIFFERENT FROM scalars_n"""
        try:
            data_components = []
            for key in self.point_data_keys:
                data_components.append(self.get_point_data_shape(key)[2])
            return data_components
        except:
            return []

    @property  # ______________________________________ CHECK IF THIS DIFFERENT FROM point_data_components
    def scalars_n(self):
        """Get the number of scalar components for points."""
        return self.GetNumberOfScalarComponents()

    # @scalars_n.setter  # ________________________________________ CHECK THIS
    # def scalars_n(self, number):
    #     """Set/Get the number of scalar components for points."""
    #     return self.SetNumberOfScalarComponents(number)

    def init_point_data(self, data_key=None, dimension=None):
        """Creates a new point data attribute with name = data_key
        as an empty Numpy array with dimension = 1, 2, 3, 4, 6, or 9.
        These are the only dimensions accepted by VTK arrays."""
        if dimension not in [1, 2, 3, 4, 6, 9]:
            print("Error - dimension not in [1, 2, 3, 4, 6, 9]")
            return
        nan_array = np_empty((self.points_number, dimension))
        nan_array[:] = np_NaN
        WrapDataObject(self).PointData.append(nan_array, data_key)

    def remove_point_data(self, data_key=None):
        """Removes a point data attribute with name = data_key."""
        self.GetPointData().RemoveArray(data_key)

    def get_point_data(self, data_key=None):
        """Returns a point data attribute as Numpy array. This cannot be converted to
        a property method since the key of the attribute must be specified."""
        """For 2D raster entities return a n-by-m-by-o-dimensional array where n-by-m
        is the shape of the raster and o is the number of components of the attribute."""
        point_data = WrapDataObject(self).PointData[data_key].reshape((self.get_point_data_shape(data_key=data_key)[1], self.get_point_data_shape(data_key=data_key)[0], self.get_point_data_shape(data_key=data_key)[2]))
        """We use np_squeeze to remove axes with length 1, so a 1D array will be returned with shape (n, ) and not with shape (n, 1)."""
        return np_squeeze(point_data)

    def get_point_data_shape(self, data_key=None):
        """Returns the shape of a point data attribute matrix."""
        """For 2D matrices we get the shape of the matrix and the number of components of
        the attribute. The third shape parameter, that for 2D images is 1, is omitted."""
        extent = self.GetExtent()
        n_components = self.GetPointData().GetArray(data_key).GetNumberOfComponents()
        return [extent[1] + 1, extent[3] + 1, n_components]

    def get_point_data_range(self, data_key=None):
        """Returns the range [mon, max] of a point data attribute matrix."""
        return self.GetPointData().GetArray(data_key).GetRange()

    def set_point_data(self, data_key=None, attribute_matrix=None):
        """Sets point data attribute from Numpy array (sets a completely new point attributes array)."""
        WrapDataObject(self).PointData.append(attribute_matrix, data_key)

    def edit_point_data(self, data_key=None, point_id=None, point_data_array=None):
        """Edits the data attribute of a single point from point_id and Numpy point_data_array"""
        point_data_array = point_data_array.flat[:]  # to be sure that point_vector is a row vector
        for col in range(np_size(point_data_array)):
            WrapDataObject(self).PointData[data_key][point_id, col] = point_data_array[col]

    def list_cell_data(self):  # _______________________ TO BE IMPLEMENTED IF WE WANT TO WORK WITH CELL DATA
        """Lists cell attribute names."""
        pass

    def init_cell_data(self, parent=None, data_key=None, dimension=None):  # _______________________ TO BE IMPLEMENTED IF WE WANT TO WORK WITH CELL DATA
        """Creates a new cell attribute with name = data_key
        as an empty Numpy array with dimension = 1, 2, 3, 4, 6, or 9."""
        pass

    def remove_cell_data(self, parent=None, data_key=None):  # _______________________ TO BE IMPLEMENTED IF WE WANT TO WORK WITH CELL DATA
        """Remove a cell attribute."""
        pass

    def get_cell_data(self, parent=None, data_key=None):  # _______________________ TO BE IMPLEMENTED IF WE WANT TO WORK WITH CELL DATA
        """Returns cell attribute as Numpy array."""
        pass

    def set_cell_data(self, parent=None, data_key=None, attribute_matrix=None):  # _______________________ TO BE IMPLEMENTED IF WE WANT TO WORK WITH CELL DATA
        """Sets cell attribute from Numpy array."""
        pass

    def edit_cell_data(self, parent=None, data_key=None, cell_id=None, cell_data_array=None):  # _______________________ TO BE IMPLEMENTED IF WE WANT TO WORK WITH CELL DATA
        """Sets cell attribute from Numpy array."""
        pass

    @property
    def frame(self):
        """Create an hexahedral frame to be shown e.g. in maps.
        .bounds is a list with xmin, xmax, ymin, ymax, zmin, zmax."""
        points = np_array([[self.bounds[0], self.bounds[2], self.bounds[4]],
                           [self.bounds[1], self.bounds[2], self.bounds[4]],
                           [self.bounds[1], self.bounds[3], self.bounds[4]],
                           [self.bounds[0], self.bounds[3], self.bounds[4]],
                           [self.bounds[0], self.bounds[2], self.bounds[5]],
                           [self.bounds[1], self.bounds[2], self.bounds[5]],
                           [self.bounds[1], self.bounds[3], self.bounds[5]],
                           [self.bounds[0], self.bounds[3], self.bounds[5]]])
        """Create edges of frame."""
        lines = np_hstack([[2, 0, 1],
                           [2, 1, 2],
                           [2, 2, 3],
                           [2, 3, 0],
                           [2, 4, 5],
                           [2, 5, 6],
                           [2, 6, 7],
                           [2, 7, 4],
                           [2, 0, 4],
                           [2, 1, 5],
                           [2, 2, 6],
                           [2, 3, 7]])
        frame = pv_PolyData(points, lines)
        return frame


class XsVoxet(Voxet):  # _____________________________________________________________ use frame and texture as in XSImage?
    """XsVoxet is a slice of a Voxet performed along a XSection."""
    def __init__(self, x_section_uid=None, parent=None, *args, **kwargs):
        self.x_section_uid = x_section_uid
        self.parent = parent  # we store a reference to parent - the project - in order to be able to use property methods below
        super(XsVoxet, self).__init__(*args, **kwargs)

    def deep_copy(self):
        voxet_copy = XsVoxet()
        voxet_copy.DeepCopy(self)
        return voxet_copy

    @property
    def columns_n(self):
        return self.GetDimensions()[0]

    @property
    def rows_n(self):
        return self.GetDimensions()[1]

    @property
    def xs_bounds(self):
        """Returns a list with W_min, W_max, Z_min, Z_max in the cross section reference frame"""
        x_section_base_x = self.parent.xsect_coll.get_uid_base_x(self.x_section_uid)
        x_section_base_y = self.parent.xsect_coll.get_uid_base_y(self.x_section_uid)
        x_section_end_x = self.parent.xsect_coll.get_uid_end_x(self.x_section_uid)
        x_section_end_y = self.parent.xsect_coll.get_uid_end_y(self.x_section_uid)
        x_section_azimuth = self.parent.xsect_coll.get_uid_azimuth(self.x_section_uid)
        if (0 <= x_section_azimuth <= 90) or (180 < x_section_azimuth <= 270):
            sense_min = np_sign((self.bounds[0] - x_section_base_x) * (x_section_end_x - x_section_base_x) + (self.bounds[2] - x_section_base_y) * (x_section_end_y - x_section_base_y))
            sense_max = np_sign((self.bounds[1] - x_section_base_x) * (x_section_end_x - x_section_base_x) + (self.bounds[3] - x_section_base_y) * (x_section_end_y - x_section_base_y))
            W_min = np_sqrt((self.bounds[0] - x_section_base_x) ** 2 + (self.bounds[2] - x_section_base_y) ** 2) * sense_min
            W_max = np_sqrt((self.bounds[1] - x_section_base_x) ** 2 + (self.bounds[3] - x_section_base_y) ** 2) * sense_max
        else:
            sense_min = np_sign((self.bounds[0] - x_section_base_x) * (x_section_end_x - x_section_base_x) + (self.bounds[3] - x_section_base_y) * (x_section_end_y - x_section_base_y))
            sense_max = np_sign((self.bounds[1] - x_section_base_x) * (x_section_end_x - x_section_base_x) + (self.bounds[2] - x_section_base_y) * (x_section_end_y - x_section_base_y))
            W_min = np_sqrt((self.bounds[0] - x_section_base_x) ** 2 + (self.bounds[3] - x_section_base_y) ** 2) * sense_min
            W_max = np_sqrt((self.bounds[1] - x_section_base_x) ** 2 + (self.bounds[2] - x_section_base_y) ** 2) * sense_max
        Z_min = self.bounds[4]
        Z_max = self.bounds[5]
        if W_min > W_max:
            W_tmp = W_max
            W_max = W_min
            W_min = W_tmp
        if Z_min > Z_max:
            Z_tmp = Z_max
            Z_max = Z_min
            Z_min = Z_tmp
        return [W_min, W_max, Z_min, Z_max]

    def image_data(self, show_property=None):  # _____________________ THERE WAS A NOTE SAYING "CHECK THIS" BUT IT IS PROBABLY OK
        """Returns a rows_n x columns_n x properties_components numpy array with image data.
        Inspired by vtkimagedata_to_array in vtkplotlib:
        https://github.com/bwoodsend/vtkplotlib/blob/master/vtkplotlib/_image_io.py"""
        self.GetPointData().SetActiveScalars(show_property)
        point_data = vtk_to_numpy(self.GetPointData().GetScalars())
        image_data = point_data.reshape((self.rows_n, self.columns_n))[::-1, ::-1]
        return image_data


class Seismics(vtkStructuredGrid):  # ___________________________________ MUST BE UPDATED AS 2D AND 3D SEISMICS, AND TO WORK AS OTHER CLASSES OF THE IMAGE COLLECTION
    """Seismics is a 3D structured grid, derived from BaseEntity and vtkStructuredGrid.
    NOT ALL SEISMICS MUST BE UNSTRUCTURED."""
    def __init__(self, *args, **kwargs):
        super(Seismics, self).__init__(*args, **kwargs)

    def deep_copy(self):
        seismics_copy = Seismics()
        seismics_copy.DeepCopy(self)
        return seismics_copy

    @property
    def bounds(self):
        """Returns a list with xmin, xmax, ymin, ymax, zmin, zmax"""
        return self.GetBounds()

    @property
    def points_number(self):
        """Returns the number of points"""
        return WrapDataObject(self).GetNumberOfPoints()

    @property
    def points(self):
        """Returns point coordinates as a Numpy array"""
        return WrapDataObject(self).Points

    @points.setter
    def points(self, points_matrix=None):
        """Sets point coordinates from a Numpy array (sets a completely new point array)"""
        WrapDataObject(self).Points = points_matrix

    @property
    def points_X(self):
        """Returns X point coordinates as Numpy array"""
        return self.points[:, 0]

    @property
    def points_Y(self):
        """Returns Y point coordinates as Numpy array"""
        return self.points[:, 1]

    @property
    def points_Z(self):
        """Returns Z point coordinates as Numpy array"""
        return self.points[:, 2]

    @property
    def cells_number(self):
        """Returns the number of points"""
        return WrapDataObject(self).GetNumberOfCells()

    @property
    def cells(self):
        """Returns cells as Numpy array. Reimplemented in subclasses."""
        pass

    @property  # ________________________________________________ properties names
    def point_data_keys(self):
        """Lists point data keys"""
        try:
            return WrapDataObject(self).PointData.keys()
        except:
            return []

    @property  # _________________________________________________ properties components
    def point_data_components(self):
        """Lists point data components"""
        try:
            data_components = []
            for key in self.point_data_keys:
                data_components.append(self.get_point_data_shape(key)[2])
            return data_components
        except:
            return []

    def init_point_data(self, data_key=None, dimension=None):
        """Creates a new point data attribute with name = data_key
        as an empty Numpy array with dimension = 1, 2, 3, 4, 6, or 9.
        These are the only dimensions accepted by VTK arrays."""
        if dimension not in [1, 2, 3, 4, 6, 9]:
            print("Error - dimension not in [1, 2, 3, 4, 6, 9]")
            return
        nan_array = np_empty((self.points_number, dimension))
        nan_array[:] = np_NaN
        WrapDataObject(self).PointData.append(nan_array, data_key)

    def remove_point_data(self, data_key=None):
        """Removes a point data attribute with name = data_key."""
        self.GetPointData().RemoveArray(data_key)

    def get_point_data(self, data_key=None):
        """Returns a point data attribute as Numpy array. This cannot be converted to
        a property method since the key of the attribute must be specified."""
        """For 2D raster entities return a n-by-m-by-o-dimensional array where n-by-m
        is the shape of the raster and o is the number of components of the attribute."""
        point_data = WrapDataObject(self).PointData[data_key].reshape((self.get_point_data_shape(data_key=data_key)[1], self.get_point_data_shape(data_key=data_key)[0], self.get_point_data_shape(data_key=data_key)[2]))
        """We use np_squeeze to remove axes with length 1, so a 1D array will be returned with shape (n, ) and not with shape (n, 1)."""
        return np_squeeze(point_data)

    def get_point_data_shape(self, data_key=None):
        """Returns the shape of a point data attribute matrix."""
        """For 2D matrices we get the shape of the matrix and the number of components of
        the attribute. The third shape parameter, that for 2D images is 1, is omitted."""
        extent = self.GetExtent()
        n_components = self.GetPointData().GetArray(data_key).GetNumberOfComponents()
        return [extent[1] + 1, extent[3] + 1, n_components]

    def set_point_data(self, data_key=None, attribute_matrix=None):
        """Sets point data attribute from Numpy array (sets a completely new point attributes array)"""
        WrapDataObject(self).PointData.append(attribute_matrix, data_key)

    def edit_point_data(self, data_key=None, point_id=None, point_data_array=None):
        """Edits the data attribute of a single point from point_id and Numpy point_data_array"""
        point_data_array = point_data_array.flat[:]  # to be sure that point_vector is a row vector
        for col in range(np_size(point_data_array)):
            WrapDataObject(self).PointData[data_key][point_id, col] = point_data_array[col]

    def list_cell_data(self):  # _______________________ TO BE IMPLEMENTED IF WE WANT TO WORK WITH CELL DATA
        """Lists cell attribute names"""
        pass

    def init_cell_data(self, parent=None, data_key=None, dimension=None):  # _______________________ TO BE IMPLEMENTED IF WE WANT TO WORK WITH CELL DATA
        """Creates a new cell attribute with name = data_key
        as an empty Numpy array with dimension = 1, 2, 3, 4, 6, or 9"""
        pass

    def remove_cell_data(self, parent=None, data_key=None):  # _______________________ TO BE IMPLEMENTED IF WE WANT TO WORK WITH CELL DATA
        """Remove a cell attribute"""
        pass

    def get_cell_data(self, parent=None, data_key=None):  # _______________________ TO BE IMPLEMENTED IF WE WANT TO WORK WITH CELL DATA
        """Returns cell attribute as Numpy array"""
        pass

    def set_cell_data(self, parent=None, data_key=None, attribute_matrix=None):  # _______________________ TO BE IMPLEMENTED IF WE WANT TO WORK WITH CELL DATA
        """Sets cell attribute from Numpy array"""
        pass

    def edit_cell_data(self, parent=None, data_key=None, cell_id=None, cell_data_array=None):  # _______________________ TO BE IMPLEMENTED IF WE WANT TO WORK WITH CELL DATA
        """Sets cell attribute from Numpy array"""
        pass

    @property
    def frame(self):
        """Create an hexahedral frame to be shown e.g. in maps.
        .bounds is a list with xmin, xmax, ymin, ymax, zmin, zmax."""
        points = np_array([[self.bounds[0], self.bounds[2], self.bounds[4]],
                           [self.bounds[1], self.bounds[2], self.bounds[4]],
                           [self.bounds[1], self.bounds[3], self.bounds[4]],
                           [self.bounds[0], self.bounds[3], self.bounds[4]],
                           [self.bounds[0], self.bounds[2], self.bounds[5]],
                           [self.bounds[1], self.bounds[2], self.bounds[5]],
                           [self.bounds[1], self.bounds[3], self.bounds[5]],
                           [self.bounds[0], self.bounds[3], self.bounds[5]]])
        """Create edges of frame."""
        lines = np_hstack([[2, 0, 1],
                           [2, 1, 2],
                           [2, 2, 3],
                           [2, 3, 0],
                           [2, 4, 5],
                           [2, 5, 6],
                           [2, 6, 7],
                           [2, 7, 4],
                           [2, 0, 4],
                           [2, 1, 5],
                           [2, 2, 6],
                           [2, 3, 7]])
        frame = pv_PolyData(points, lines)
        return frame


class DEM(vtkStructuredGrid):
    """DEM is a Digital Elevation Model derived from vtkStructuredGrid,
    saved in the project folder as .vts. Many methods are similar to PolyData."""
    def __init__(self, *args, **kwargs):
        super(DEM, self).__init__(*args, **kwargs)

    def deep_copy(self):
        dem_copy = DEM()
        dem_copy.DeepCopy(self)
        return dem_copy

    @property
    def bounds(self):
        """Returns a list with xmin, xmax, ymin, ymax, zmin, zmax"""
        return self.GetBounds()

    @property
    def points_number(self):
        """Returns the number of points"""
        return WrapDataObject(self).GetNumberOfPoints()

    @property
    def points(self):
        """Returns point coordinates as a Numpy array"""
        return WrapDataObject(self).Points

    @points.setter
    def points(self, points_matrix=None):
        """Sets point coordinates from a Numpy array (sets a completely new point array)"""
        WrapDataObject(self).Points = points_matrix

    @property
    def points_X(self):
        """Returns X point coordinates as Numpy array"""
        return self.points[:, 0]

    @property
    def points_Y(self):
        """Returns Y point coordinates as Numpy array"""
        return self.points[:, 1]

    @property
    def points_Z(self):
        """Returns Z point coordinates as Numpy array"""
        return self.points[:, 2]

    @property
    def cells_number(self):
        """Returns the number of points"""
        return WrapDataObject(self).GetNumberOfCells()

    @property
    def cells(self):
        """Returns cells as Numpy array. Reimplemented in subclasses."""
        pass

    @property
    def point_data_keys(self):
        """Lists point data keys"""
        try:
            return WrapDataObject(self).PointData.keys()
        except:
            return []

    def init_point_data(self, data_key=None, dimension=None):
        """Creates a new point data attribute with name = data_key
        as an empty Numpy array with dimension = 1, 2, 3, 4, 6, or 9.
        These are the only dimensions accepted by VTK arrays."""
        if dimension not in [1, 2, 3, 4, 6, 9]:
            print("Error - dimension not in [1, 2, 3, 4, 6, 9]")
            return
        nan_array = np_empty((self.points_number, dimension))
        nan_array[:] = np_NaN
        WrapDataObject(self).PointData.append(nan_array, data_key)

    def remove_point_data(self, data_key=None):
        """Removes a point data attribute with name = data_key."""
        self.GetPointData().RemoveArray(data_key)

    def get_point_data(self, data_key=None):
        """Returns a point data attribute as Numpy array. This cannot be converted to
        a property method since the key of the attribute must be specified."""
        """For 2D raster entities return a n-by-m-by-o-dimensional array where n-by-m
        is the shape of the raster and o is the number of components of the attribute."""
        point_data = WrapDataObject(self).PointData[data_key].reshape((self.get_point_data_shape(data_key=data_key)[1], self.get_point_data_shape(data_key=data_key)[0], self.get_point_data_shape(data_key=data_key)[2]))
        """We use np_squeeze to remove axes with length 1, so a 1D array will be returned with shape (n, ) and not with shape (n, 1)."""
        return np_squeeze(point_data)

    def get_point_data_shape(self, data_key=None):
        """Returns the shape of a point data attribute matrix."""
        """For 2D matrices we get the shape of the matrix and the number of components of
        the attribute. The third shape parameter, that for 2D images is 1, is omitted."""
        extent = self.GetExtent()
        n_components = self.GetPointData().GetArray(data_key).GetNumberOfComponents()
        return [extent[1] + 1, extent[3] + 1, n_components]

    def set_point_data(self, data_key=None, attribute_matrix=None):
        """Sets point data attribute from Numpy array (sets a completely new point attributes array)"""
        WrapDataObject(self).PointData.append(attribute_matrix, data_key)

    def edit_point_data(self, data_key=None, point_id=None, point_data_array=None):
        """Edits the data attribute of a single point from point_id and Numpy point_data_array"""
        point_data_array = point_data_array.flat[:]  # to be sure that point_vector is a row vector
        for col in range(np_size(point_data_array)):
            WrapDataObject(self).PointData[data_key][point_id, col] = point_data_array[col]

    def list_cell_data(self):  # _______________________ TO BE IMPLEMENTED IF WE WANT TO WORK WITH CELL DATA
        """Lists cell attribute names"""
        pass

    def init_cell_data(self, parent=None, data_key=None, dimension=None):  # _______________________ TO BE IMPLEMENTED IF WE WANT TO WORK WITH CELL DATA
        """Creates a new cell attribute with name = data_key
        as an empty Numpy array with dimension = 1, 2, 3, 4, 6, or 9"""
        pass

    def remove_cell_data(self, parent=None, data_key=None):  # _______________________ TO BE IMPLEMENTED IF WE WANT TO WORK WITH CELL DATA
        """Remove a cell attribute"""
        pass

    def get_cell_data(self, parent=None, data_key=None):  # _______________________ TO BE IMPLEMENTED IF WE WANT TO WORK WITH CELL DATA
        """Returns cell attribute as Numpy array"""
        pass

    def set_cell_data(self, parent=None, data_key=None, attribute_matrix=None):  # _______________________ TO BE IMPLEMENTED IF WE WANT TO WORK WITH CELL DATA
        """Sets cell attribute from Numpy array"""
        pass

    def edit_cell_data(self, parent=None, data_key=None, cell_id=None, cell_data_array=None):  # _______________________ TO BE IMPLEMENTED IF WE WANT TO WORK WITH CELL DATA
        """Sets cell attribute from Numpy array"""
        pass

    def add_texture(self, map_image=None, map_image_uid=None):
        """Calculate texture coordinates for a MapImage."""
        X0 = map_image.origin[0]
        Y0 = map_image.origin[1]
        if map_image.bounds[1] != X0:
            X1 = map_image.bounds[1]
        else:
            X1 = map_image.bounds[0]
        if map_image.bounds[3] != Y0:
            Y1 = map_image.bounds[3]
        else:
            Y1 = map_image.bounds[2]
        U = (self.points_X - X0)/(X1 - X0)
        V = (self.points_Y - Y0) / (Y1 - Y0)
        UV = np_column_stack((U, V))
        """Set point data on object. Do not initialize the array before this line."""
        self.set_point_data(data_key=map_image_uid, attribute_matrix=UV)

    def remove_texture(self, map_image_uid=None):
        self.remove_point_data(data_key=map_image_uid)

    def set_active_texture(self, map_image_uid=None):
        self.GetPointData().SetActiveTCoords(map_image_uid)


class PCDom(PolyData):  # _______________________ DO WE NEED ADDITIONAL METHODS WITH RESPECT TO POLYDATA?
    """Point Cloud DOM.
    See discussion at https://discourse.vtk.org/t/proposal-adding-a-vtkpointcloud-data-structure/3872/3 """
    def __init__(self, *args, **kwargs):
        super(PCDom, self).__init__(*args, **kwargs)

    def deep_copy(self):
        pcdom_copy = PCDom()
        pcdom_copy.DeepCopy(self)
        return pcdom_copy

    # @property
    # def points(self):
    #     """Returns point coordinates as a Numpy array"""
    #     return WrapDataObject(self).Points
    #
    # @points.setter
    # def points(self, points_matrix=None):
    #     """Sets point coordinates from a Numpy array (sets a completely new point array)"""
    #     WrapDataObject(self).Points = points_matrix
    #
    #
    # def cast_to_polydata(self):
    #
    #     # NEW METHOD
    #     pv_PD = pv_PolyData(self.points)
    #     vtk_points = pv_PD.GetPoints()
    #     vtk_cells = pv_PD.GetVerts()
    #     cast = PolyData()
    #     cast.SetPoints(vtk_points)
    #     cast.SetVerts(vtk_cells)
    #     del pv_PD
    #     del vtk_points
    #     del vtk_cells
    #
    #     return cast


class TSDom(PolyData):  # __________________________________ TO BE IMPLEMENTED - could also be derived from TriSurf()
    """Textured Surface DOM"""
    def __init__(self, *args, **kwargs):
        super(TSDom, self).__init__(*args, **kwargs)

    def deep_copy(self):
        tsdom_copy = TSDom()
        tsdom_copy.DeepCopy(self)
        return tsdom_copy


class Image(vtkImageData):  # _________________________________________________see if it is a good idea to use this also as a superclass to Voxet()
    """Image is an abstract class for image data, used as a base for subclasses, derived from
    vtkImageData() that is saved in the project folder as .vti"""
    def __init__(self, *args, **kwargs):
        super(Image, self).__init__(*args, **kwargs)

    @property
    def origin(self):
        return self.GetOrigin()

    @origin.setter
    def origin(self, vector=None):
        self.SetOrigin(vector)

    @property
    def properties_n(self):
        """This is not exposed in collection but used internally in the class."""
        return self.GetPointData().GetNumberOfArrays()

    @property
    def properties_names(self):
        properties_names = []
        for prop in range(self.properties_n):
            property_name = self.GetPointData().GetArray(prop).GetName()
            properties_names.append(property_name)
        return properties_names

    @property
    def properties_components(self):
        properties_components = []
        for prop in range(self.properties_n):
            property_components = self.GetPointData().GetArray(prop).GetNumberOfComponents()
            properties_components.append(property_components)
        return properties_components

    def get_property_components(self, property_name=None):
        for i in range(len(self.properties_names)):
            if self.properties_names[i] == property_name:
                return self.properties_components[i]

    @property
    def properties_types(self):
        properties_types = []
        for prop in range(self.properties_n):
            property_type = self.GetPointData().GetArray(prop).GetDataTypeAsString()
            properties_types.append(property_type)
        return properties_types

    def get_property_type(self, property_name=None):
        for i in range(len(self.properties_names)):
            if self.properties_names[i] == property_name:
                return self.properties_types[i]

    @property
    def spacing(self):
        return self.GetSpacing()

    @property
    def dimensions(self):
        return self.GetDimensions()

    @property
    def U_n(self):
        return self.GetDimensions()[0]

    @property
    def V_n(self):
        return self.GetDimensions()[1]

    @property
    def W_n(self):
        return self.GetDimensions()[2]

    @property
    def bounds(self):
        """Returns a list with xmin, xmax, ymin, ymax, zmin, zmax"""
        return self.GetBounds()

    def image_data(self, property_name=None):
        """Returns image data stored as Numpy array. This cannot be converted to
        a property method since the property_name of the attribute must be specified.
        We use np_squeeze to remove axes with length 1, so a 1D array will be returned
        with shape (n, ) and not with shape (n, 1), and 2D raster entities will return a
        n-by-m-by-o-dimensional array where n-by-m is the shape of the raster and o is the
        number of components of the attribute. 3D raster will result in n-by-m-by-p-by-o."""
        image_data = WrapDataObject(self).PointData[property_name].reshape((self.V_n, self.U_n, self.W_n, self.get_property_components(property_name)))
        return np_squeeze(image_data)


class MapImage(Image):
    """MapImage is a georeferenced (possibly multi-property) 2D image, derived from
    vtkImageData() that is saved in the project folder as .vti"""
    def __init__(self, *args, **kwargs):
        super(MapImage, self).__init__(*args, **kwargs)

    def deep_copy(self):
        image_copy = MapImage()
        image_copy.DeepCopy(self)
        return image_copy

    @property
    def columns_n(self):
        return self.U_n

    @property
    def rows_n(self):
        return self.V_n

    @property
    def frame(self):
        """Create rectangular frame to be textured.
        .bounds is a list with xmin, xmax, ymin, ymax, zmin, zmax."""
        points = np_array([[self.bounds[0], self.bounds[3], self.bounds[4]],
                           [self.bounds[1], self.bounds[3], self.bounds[4]],
                           [self.bounds[1], self.bounds[2], self.bounds[4]],
                           [self.bounds[0], self.bounds[2], self.bounds[4]]])
        """Rectangular face and frame."""
        face = np_hstack([[4, 0, 1, 2, 3]])
        frame = pv_PolyData(points, face)
        """Apply texture coordinates."""
        frame.t_coords = np_array([[0.0, 0.0],
                                   [1.0, 0.0],
                                   [1.0, 1.0],
                                   [0.0, 1.0]])
        return frame

    @property
    def texture(self):
        return pv_image_to_texture(self)


class XsImage(Image):
    """XsImage is a (possibly multi-property) 2D image, vertically georeferenced in a cross-section,
    derived from vtkImageData(), and is saved in the project folder as .vti"""
    def __init__(self, x_section_uid=None, parent=None, *args, **kwargs):
        self.x_section_uid = x_section_uid
        self.parent = parent  # we store a reference to parent - the project - in order to be able to use property methods below
        super(XsImage, self).__init__(*args, **kwargs)

    def deep_copy(self):
        image_copy = XsImage()
        image_copy.DeepCopy(self)
        return image_copy

    @property
    def columns_n(self):
        return self.U_n

    @property
    def rows_n(self):
        return self.V_n

    @property
    def xs_bounds(self):
        """Returns a list with W_min, W_max, Z_min, Z_max in the cross section reference frame"""
        x_section_base_x = self.parent.xsect_coll.get_uid_base_x(self.x_section_uid)
        x_section_base_y = self.parent.xsect_coll.get_uid_base_y(self.x_section_uid)
        x_section_end_x = self.parent.xsect_coll.get_uid_end_x(self.x_section_uid)
        x_section_end_y = self.parent.xsect_coll.get_uid_end_y(self.x_section_uid)
        x_section_azimuth = self.parent.xsect_coll.get_uid_azimuth(self.x_section_uid)
        if (0 <= x_section_azimuth <= 90) or (180 < x_section_azimuth <= 270):
            sense_min = np_sign((self.bounds[0] - x_section_base_x) * (x_section_end_x - x_section_base_x) + (self.bounds[2] - x_section_base_y) * (x_section_end_y - x_section_base_y))
            sense_max = np_sign((self.bounds[1] - x_section_base_x) * (x_section_end_x - x_section_base_x) + (self.bounds[3] - x_section_base_y) * (x_section_end_y - x_section_base_y))
            W_min = np_sqrt((self.bounds[0] - x_section_base_x) ** 2 + (self.bounds[2] - x_section_base_y) ** 2) * sense_min
            W_max = np_sqrt((self.bounds[1] - x_section_base_x) ** 2 + (self.bounds[3] - x_section_base_y) ** 2) * sense_max
        else:
            sense_min = np_sign((self.bounds[0] - x_section_base_x) * (x_section_end_x - x_section_base_x) + (self.bounds[3] - x_section_base_y) * (x_section_end_y - x_section_base_y))
            sense_max = np_sign((self.bounds[1] - x_section_base_x) * (x_section_end_x - x_section_base_x) + (self.bounds[2] - x_section_base_y) * (x_section_end_y - x_section_base_y))
            W_min = np_sqrt((self.bounds[0] - x_section_base_x) ** 2 + (self.bounds[3] - x_section_base_y) ** 2) * sense_min
            W_max = np_sqrt((self.bounds[1] - x_section_base_x) ** 2 + (self.bounds[2] - x_section_base_y) ** 2) * sense_max
        Z_min = self.bounds[4]
        Z_max = self.bounds[5]
        if W_min > W_max:
            W_tmp = W_max
            W_max = W_min
            W_min = W_tmp
        if Z_min > Z_max:
            Z_tmp = Z_max
            Z_max = Z_min
            Z_min = Z_tmp
        return [W_min, W_max, Z_min, Z_max]

    @property
    def frame(self):
        """Create rectangular frame to be textured."""
        x_section_azimuth = self.parent.xsect_coll.get_uid_azimuth(self.x_section_uid)
        if 0 <= x_section_azimuth <= 90:
            left_x = self.bounds[0]
            left_y = self.bounds[2]
            right_x = self.bounds[1]
            right_y = self.bounds[3]
        elif 90 < x_section_azimuth <= 180:
            left_x = self.bounds[0]
            left_y = self.bounds[3]
            right_x = self.bounds[1]
            right_y = self.bounds[2]
        elif 180 < x_section_azimuth <= 270:
            left_x = self.bounds[1]
            left_y = self.bounds[3]
            right_x = self.bounds[0]
            right_y = self.bounds[2]
        else:
            left_x = self.bounds[1]
            left_y = self.bounds[2]
            right_x = self.bounds[0]
            right_y = self.bounds[3]
        bottom = self.bounds[4]
        top = self.bounds[5]
        """Points"""
        points = np_array([[left_x, left_y, bottom],
                           [left_x, left_y, top],
                           [right_x, right_y, top],
                           [right_x, right_y, bottom]])
        """Rectangular face and frame."""
        face = np_hstack([[4, 0, 1, 2, 3]])
        frame = pv_PolyData(points, face)
        """Apply texture coordinates."""
        frame.t_coords = np_array([[0.0, 1.0],
                                   [0.0, 0.0],
                                   [1.0, 0.0],
                                   [1.0, 1.0]])
        return frame

    @property
    def texture(self):
        return pv_image_to_texture(self)


class Image3D(Image):  # ________________________________________________________________ TO BE IMPLEMENTED - JUST COPY AND PASTE AT THE MOMENT
    """Image3D is a georeferenced (possibly multi-property) 3D image, derived from
    vtkImageData() that is saved in the project folder as .vti"""
    def __init__(self, *args, **kwargs):
        super(Image3D, self).__init__(*args, **kwargs)

    def deep_copy(self):
        image_copy = Image3D()
        image_copy.DeepCopy(self)
        return image_copy

    @property
    def frame(self):
        """Create hexahedral frame to be textured. _________________________________________MODIFY THIS TO GET A HEXAHEDRAL BOX
        .bounds is a list with xmin, xmax, ymin, ymax, zmin, zmax."""
        points = np_array([[self.bounds[0], self.bounds[3], self.bounds[4]],
                           [self.bounds[1], self.bounds[3], self.bounds[4]],
                           [self.bounds[1], self.bounds[2], self.bounds[4]],
                           [self.bounds[0], self.bounds[2], self.bounds[4]]])
        """Rectangular face and frame."""
        face = np_hstack([[4, 0, 1, 2, 3]])
        frame = pv_PolyData(points, face)
        """Apply texture coordinates."""
        frame.t_coords = np_array([[0.0, 0.0],
                                   [1.0, 0.0],
                                   [1.0, 1.0],
                                   [0.0, 1.0]])
        return frame


class Wells(PolyLine):
    # [Gabriele] vtkCylinderSource could be used but it is not supported by pyvista

    def __init__(self, *args, **kwargs):
        super(Wells, self).__init__(*args, **kwargs)
    #
    def deep_copy(self):
        well_copy = Wells()
        well_copy.DeepCopy(self)
        return well_copy

class WellMarker(VertexSet):
    def __init__(self, *args, **kwargs):
        super(WellMarker, self).__init__(*args, **kwargs)
    #
    def deep_copy(self):
        well_copy = WellMarker()
        well_copy.DeepCopy(self)
        return well_copy

class Attitude(VertexSet):
    def __init__(self, *args, **kwargs):
        super(Attitude, self).__init__(*args, **kwargs)
    #
    def deep_copy(self):
        att_copy = Attitude()
        att_copy.DeepCopy(self)
        return att_copy
