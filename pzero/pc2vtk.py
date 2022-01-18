"""pc2vtk.py by Gabriele Benedetti
PZero© Andrea Bistacchi
--------

Convert point cloud data (txt, csv,xyz, las ...) in vtk objects.

The process is as follows:

            Import the data as a numpy array (read from file)
                                |
                                |
            Insert n cells with n = number of points in
                            the data file
                                |
                                |
                Insert the single point for each cell
                                |
                                |
            Assign points and verts to a vtkPolyData object (PCDom)


For now the import function is not very flexible. The input file must have:
    1. The data start on the second line of the file
    2. The delimiter for the columns set as , (comma)

In the near feature
"""


import numpy as np
from vtk import vtkPointSet, vtkCellArray, vtkPoints, vtkPolyData
import os
from copy import deepcopy
import uuid
from .entities_factory import PCDom
from .dom_collection import DomCollection
import pyvista as pv
import xarray as xr



def pc2vtk(self, in_file_name, header_ind = 1, delimiter = ','):

    self.TextTerminal.appendPlainText(f'Reading file {in_file_name}')

    input_data = np.loadtxt(fname = in_file_name, delimiter = delimiter, skiprows = header_ind)
    n_cells = len(input_data)


    """[Gabriele] Convert to PCDom() instance. Used https://docs.pyvista.org/examples/00-load/wrap-trimesh.html for reference"""

    point_cloud = PCDom() #[Gabriele] vtkPolyData object
    points = vtkPoints() #[Gabriele] points object
    vertices = vtkCellArray() #[Gabriele] vertices (cells)
    vertices.InsertNextCell(n_cells) #[Gabriele] set n cells with n= number of points in the dataset

 #[Gabriele] insert the datasets points and assign each point to a cell
    for p in input_data:
        pid = points.InsertNextPoint(p)
        vertices.InsertCellPoint(pid)
    point_cloud.SetPoints(points) #[Gabriele] Assign the points to the point_cloud (vtkPolyData)
    point_cloud.SetVerts(vertices) #[Gabriele] Assign the vertices to the point_cloud (vtkPolyData)

    point_cloud.Modified()

    """Create dictionary."""
    curr_obj_attributes = deepcopy(DomCollection.dom_entity_dict)
    curr_obj_attributes['uid'] = str(uuid.uuid4())
    curr_obj_attributes['name'] = os.path.basename(in_file_name)
    curr_obj_attributes['dom_type'] = "PCDom"
    curr_obj_attributes['texture_uids'] = []
    curr_obj_attributes['properties_names'] = ["elevation"]
    curr_obj_attributes['properties_components'] = [1]
    curr_obj_attributes['vtk_obj'] = point_cloud
    self.TextTerminal.appendPlainText(f'vtk_obj: {curr_obj_attributes["vtk_obj"]}')
    """Add to entity collection."""
    self.dom_coll.add_entity_from_dict(entity_dict=curr_obj_attributes)
    self.TextTerminal.appendPlainText(f'Successfully imported {in_file_name}')
    """Cleaning."""
    del points
    del point_cloud
