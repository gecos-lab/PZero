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
from vtk import vtkCellArray, vtkPoints,vtkUnsignedCharArray
import os
from copy import deepcopy
import uuid
from .entities_factory import PCDom
from .dom_collection import DomCollection
import pyvista as pv
import xarray as xr



def pc2vtk(in_file_name,input_df,self=None):

    _,extension = os.path.splitext(in_file_name)



    n_cells = input_df.shape[0] # [Gabriele] the number of cells is = to the number of rows of the df.

    ''' [Gabriele] Correcting input data by subtracting an equal value approximated to the hundreds (53932.4325 -> 53932.4325 - 53900.0000 = 32.4325). Can be always applied since for numbers < 100 the approximation is always 0'''


    # if len(str(input_df.iloc[0,0]).replace('.','')) > 12:
    x_name,y_name,z_name = input_df.iloc[:,:3].columns
    input_df[x_name] -= input_df.iloc[0,0].round(-2)
    input_df[y_name] -= input_df.iloc[0,1].round(-2)

    '''[Gabriele] Extract RGB column values [TODO] make it dynamic (RGB values are not always after xyz values)'''

    if extension == '.las' or extension == '.laz':
        RGB = input_df.loc[:,'red':'blue'].values
    else:
        RGB = input_df.iloc[:,3:6].values
        # scalars = input_df.iloc[:,6].values
        # print(RGB)

    """[Gabriele] Convert to PCDom() instance. Used https://docs.pyvista.org/examples/00-load/wrap-trimesh.html as reference"""
    point_cloud = PCDom() #[Gabriele] vtkPolyData object
    points = vtkPoints() #[Gabriele] points object
    vertices = vtkCellArray() #[Gabriele] vertices (cells)
    vertices.InsertNextCell(n_cells) #[Gabriele] set n cells with n= number of points in the dataset
    colors = vtkUnsignedCharArray() # [Gabriele] create colors as unsigned char array (int only)
    colors.SetNumberOfComponents(3) # [Gabriele] Set numbers of components (RGB = 3)
    colors.SetName("colors") # [Gabriele] give it a name

 #[Gabriele] insert the datasets points and assign each point to a cell
    for p,c in zip(input_df.iloc[:,:3].values,RGB):
        pid = points.InsertNextPoint(p)
        vertices.InsertCellPoint(pid)
        if c.dtype == 'float64': # [Gabriele] RGB must be in 0-255 range
            c = np.round(c*255,0)
        colors.InsertNextTuple3(c[0],c[1],c[2]) # [Gabriele] Insert color values
    point_cloud.SetPoints(points) #[Gabriele] Assign the points to the point_cloud (vtkPolyData)
    point_cloud.SetVerts(vertices) #[Gabriele] Assign the vertices to the point_cloud (vtkPolyData)
    point_cloud.GetPointData().SetScalars(colors) # [Gabriele]Set color data

    point_cloud.Modified()
    """Create dictionary."""
    curr_obj_attributes = deepcopy(DomCollection.dom_entity_dict)
    curr_obj_attributes['uid'] = str(uuid.uuid4())
    curr_obj_attributes['name'] = os.path.basename(in_file_name)
    curr_obj_attributes['dom_type'] = "PCDom"
    curr_obj_attributes['texture_uids'] = []
    curr_obj_attributes['properties_names'] = ['RGB']
    curr_obj_attributes['properties_components'] = []
    curr_obj_attributes['vtk_obj'] = point_cloud
    self.TextTerminal.appendPlainText(f'vtk_obj: {curr_obj_attributes["vtk_obj"]}')
    """Add to entity collection."""
    self.dom_coll.add_entity_from_dict(entity_dict=curr_obj_attributes)
    self.TextTerminal.appendPlainText(f'Successfully imported {in_file_name}')
    """Cleaning."""
    del points
    del point_cloud
