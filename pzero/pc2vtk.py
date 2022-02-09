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

    '''[Gabriele] Filter the scalar values present in the input dataset. Put these entries in the properties name and components lists (columns and values)'''

    scalar_df =  input_df.filter(regex='scalar')

    scalar_names = list(scalar_df)
    scalar_values = scalar_df.values.T

    if not val_check.all():
        print('Invalid values in data set, not importing.')
    else:
        input_df = input_df.astype(float)

        n_cells = input_df.shape[0] # [Gabriele] the number of cells is = to the number of rows of the df.

        ''' [Gabriele] Correcting input data by subtracting an equal value approximated to the hundreds (53932.4325 -> 53932.4325 - 53900.0000 = 32.4325). Can be always applied since for numbers < 100 the approximation is always 0. The value corresponds to the first data point (start_row) for x and y (the same quantity needs to be subtracted to all x or y points)'''


        # if len(str(input_df.iloc[0,0]).replace('.','')) > 12:
        input_df['x'] -= input_df['x'][start_row].round(-2)
        input_df['y'] -= input_df['y'][start_row].round(-2)


        '''[Gabriele] Extract XYZ and RGB column values (if rgb present)'''


        XYZ = np.array([input_df['x'].values,input_df['y'].values,input_df['z'].values]).T

        try:
            red = input_df['r'].values
            green = input_df['g'].values
            blue = input_df['b'].values

            RGB = np.array([red,green,blue]).T

        except KeyError:

            # [Gabriele] If r,g or b columns are not present then use ones (white)
            RGB = np.ones_like(XYZ)

        """[Gabriele] Convert to PCDom() instance. Used https://docs.pyvista.org/examples/00-load/wrap-trimesh.html as reference"""

        point_cloud = PCDom() #[Gabriele] vtkPolyData object
        points = vtkPoints() #[Gabriele] points object
        vertices = vtkCellArray() #[Gabriele] vertices (cells)
        vertices.InsertNextCell(n_cells) #[Gabriele] set n cells with n= number of points in the dataset
        colors = vtkUnsignedCharArray() # [Gabriele] create colors as unsigned char array (int only)
        colors.SetNumberOfComponents(3) # [Gabriele] Set numbers of components (RGB = 3)
        colors.SetName("colors") # [Gabriele] give it a name

     #[Gabriele] insert the datasets points and assign each point to a cell
        for p,c in zip(XYZ,RGB):
            pid = points.InsertNextPoint(p)
            vertices.InsertCellPoint(pid)
             # [Gabriele] RGB must be in 0-255 range
            if all(i<=1 and i>0 for i in c):
                c = np.round(c*255,0)
            elif all(i>255 for i in c):
                c = np.round(c/255,0)
            colors.InsertNextTuple3(c[0],c[1],c[2]) # [Gabriele] Insert color values

        point_cloud.SetPoints(points) #[Gabriele] Assign the points to the point_cloud (vtkPolyData)
        point_cloud.SetVerts(vertices) #[Gabriele] Assign the vertices to the point_cloud (vtkPolyData)
        point_cloud.GetPointData().SetScalars(colors) # [Gabriele] Set color data

        point_cloud.Modified()
        """Create dictionary."""
        curr_obj_attributes = deepcopy(DomCollection.dom_entity_dict)
        curr_obj_attributes['uid'] = str(uuid.uuid4())
        curr_obj_attributes['name'] = os.path.basename(in_file_name)
        curr_obj_attributes['dom_type'] = "PCDom"
        curr_obj_attributes['texture_uids'] = []
        curr_obj_attributes['properties_names'] = scalar_names
        curr_obj_attributes['properties_components'] = scalar_values
        curr_obj_attributes['vtk_obj'] = point_cloud
        self.TextTerminal.appendPlainText(f'vtk_obj: {curr_obj_attributes["vtk_obj"]}')
        """Add to entity collection."""
        self.dom_coll.add_entity_from_dict(entity_dict=curr_obj_attributes)
        self.TextTerminal.appendPlainText(f'Successfully imported {in_file_name}')
        """Cleaning."""
        del points
        del point_cloud
