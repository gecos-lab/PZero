"""pc2vtk.py by Gabriele Benedetti
PZero© Andrea Bistacchi
--------

Convert point cloud data (txt, csv,xyz, las ...) in vtk objects.

The process is as follows:

            Import the data as a pandas df (read from file)
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



def pc2vtk(in_file_name,input_df,self=None):


    n_cells = input_df.shape[0] # [Gabriele] the number of cells is = to the number of rows of the df.


    """[Gabriele] Convert to PCDom() instance. Used https://docs.pyvista.org/examples/00-load/wrap-trimesh.html as reference"""

    point_cloud = PCDom() #[Gabriele] vtkPolyData object
    points = vtkPoints() #[Gabriele] points object
    vertices = vtkCellArray() #[Gabriele] vertices (cells)
    vertices.InsertNextCell(n_cells) #[Gabriele] set n cells with n= number of points in the dataset

 #[Gabriele] insert the datasets points and assign each point to a cell
    for p in input_df.iloc[:].values:
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
    curr_obj_attributes['properties_names'] = []
    curr_obj_attributes['properties_components'] = []
    curr_obj_attributes['vtk_obj'] = point_cloud
    self.TextTerminal.appendPlainText(f'vtk_obj: {curr_obj_attributes["vtk_obj"]}')
    """Add to entity collection."""
    self.dom_coll.add_entity_from_dict(entity_dict=curr_obj_attributes)
    self.TextTerminal.appendPlainText(f'Successfully imported {in_file_name}')
    """Cleaning."""
    del points
    del point_cloud
