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
import pandas as pd


def pc2vtk(in_file_name,raw_input_df,start_col,end_col,start_row,end_row,self=None):

    _,extension = os.path.splitext(in_file_name)

    if end_row == -1:
        input_df = raw_input_df.iloc[start_row:, start_col:end_col]
    else:
        input_df = raw_input_df.iloc[start_row:end_row, start_col:end_col]

    '''[Gabriele] Check if there is invalid data (Text, NaN, etc)'''
    val_check = input_df.apply(lambda c: pd.to_numeric(c, errors='coerce').notnull().all())



    if not val_check.all():
        print('Invalid values in data set, not importing.')
    else:

        n_cells = input_df.shape[0] # [Gabriele] the number of cells is = to the number of rows of the df.

        ''' [Gabriele] Correcting input data by subtracting an equal value approximated to the hundreds (53932.4325 -> 53932.4325 - 53900.0000 = 32.4325). Can be always applied since for numbers < 100 the approximation is always 0. The value corresponds to the first data point (start_row) for x and y (the same quantity needs to be subtracted to all x or y points)'''


        # if len(str(input_df.iloc[0,0]).replace('.','')) > 12:
        input_df['X'] -= input_df['X'][start_row].round(-2)
        input_df['Y'] -= input_df['Y'][start_row].round(-2)


        '''[Gabriele] Extract XYZ and RGB column values (if rgb present)'''


        XYZ = np.array([input_df['X'].values,input_df['Y'].values,input_df['Z'].values]).T



        """[Gabriele] Convert to PCDom() instance. Used https://docs.pyvista.org/examples/00-load/wrap-trimesh.html as reference"""

        point_cloud = PCDom() #[Gabriele] vtkPolyData object
        points = vtkPoints() #[Gabriele] points object
        vertices = vtkCellArray() #[Gabriele] vertices (cells)
        vertices.InsertNextCell(n_cells) #[Gabriele] set n cells with n= number of points in the dataset

     #[Gabriele] insert the datasets points and assign each point to a cell
        for p in XYZ:
            pid = points.InsertNextPoint(p)
            vertices.InsertCellPoint(pid)




        point_cloud.SetPoints(points) #[Gabriele] Assign the points to the point_cloud (vtkPolyData)
        point_cloud.SetVerts(vertices) #[Gabriele] Assign the vertices to the point_cloud (vtkPolyData)

        # [Gabriele] Pedefined scalars

        properties_df = input_df.drop(['X','Y','Z'],axis=1)

        if not properties_df.filter(regex='N.a.').empty:
            properties_df = properties_df.drop(['N.a.'],axis=1)

        scalar_components = []
        if not properties_df.empty:
            scalar_names = list(properties_df.columns)

            for scalar in scalar_names:
                scalar_value = properties_df[scalar].values
                scalar_components.append(1)
                point_cloud.set_point_data(scalar,scalar_value)
        else:
            scalar_names = []


        point_cloud.Modified()
        """Create dictionary."""
        curr_obj_attributes = deepcopy(DomCollection.dom_entity_dict)
        curr_obj_attributes['uid'] = str(uuid.uuid4())
        curr_obj_attributes['name'] = os.path.basename(in_file_name)
        curr_obj_attributes['dom_type'] = "PCDom"
        curr_obj_attributes['texture_uids'] = []
        curr_obj_attributes['properties_names'] = scalar_names
        curr_obj_attributes['properties_components'] = scalar_components
        curr_obj_attributes['vtk_obj'] = point_cloud
        self.TextTerminal.appendPlainText(f'vtk_obj: {curr_obj_attributes["vtk_obj"]}')
        """Add to entity collection."""
        self.dom_coll.add_entity_from_dict(entity_dict=curr_obj_attributes)
        self.TextTerminal.appendPlainText(f'Successfully imported {in_file_name}')
        """Cleaning."""
        del points
        del point_cloud
