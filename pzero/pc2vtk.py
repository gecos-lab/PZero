"""pc2vtk.py by Gabriele Benedetti
PZero© Andrea Bistacchi
--------

Convert point cloud data (txt, csv, xyz, las ...) in vtk objects.


"""


import numpy as np
import os
from copy import deepcopy
from vtk import vtkPoints,vtkCellArray, vtkPointSet
import uuid
from .entities_factory import PCDom
from .dom_collection import DomCollection
from pyvista import PolyData as PlD
from pyvista import vtk_points
# import pyvista as pv
import pandas as pd
import laspy as lp
from .helper_functions import profiler


def pc2vtk(in_file_name,col_names,row_range,header_row,usecols,delimiter,offset,self=None):

    # # @profiler('../pz_pers/reports/importfile.csv',200)
    # def old_method(XYZ):
    #     n_cells = XYZ.shape[0]
    #     point_cloud = PCDom() #[Gabriele] vtkpointSet object
    #     points = vtkPoints() #[Gabriele] points object
    #     vertices = vtkCellArray() #[Gabriele] vertices (cells)
    #     vertices.InsertNextCell(n_cells) #[Gabriele] set n cells with n= number of points in the dataset
    #
    #  #[Gabriele] insert the datasets points and assign each point to a cell
    #     for p in XYZ:
    #         pid = points.InsertNextPoint(p)
    #         vertices.InsertCellPoint(pid)
    #
    #
    #
    #     point_cloud.SetPoints(points) #[Gabriele] Assign the points to the point_cloud (vtkPolyData)
    #     point_cloud.SetVerts(vertices) #[Gabriele] Assign the vertices to the point_cloud (vtkPolyData)
    #     return point_cloud
    #
    # @profiler('../pz_pers/reports/importfile.csv',200)
    # def new_method(XYZ):
    #     point_cloud = PCDom()
    #     pv_PD = PlD(XYZ)
    #     point_cloud.ShallowCopy(pv_PD)
    #     point_cloud.Modified()
    #     return point_cloud

    def ps_method(XYZ):
        point_cloud = vtkPointSet()
        points = vtk_points(XYZ)
        point_cloud.SetPoints(points)
        return point_cloud


    # chunk_size = 10**6
    # @profiler('../pz_pers/reports/other_method.csv',200)

    print('1. Reading and importing file')

    basename = os.path.basename(in_file_name)
    _,ext = os.path.splitext(basename)
    point_cloud = PCDom() #[Gabriele] vtkpointSet object

    skip_range = range(1,row_range.start)
    if skip_range:
        skiprows = skip_range.stop-skip_range.start
    else:
        skiprows = header_row+1

    if row_range:
        nrows = row_range.stop-row_range.start
    else:
        nrows = None

    # [Gabriele] Read in different ways depending on the input file type
    if ext == '.ply':
        with open(in_file_name,'r') as f:
            for i,line in enumerate(f):
                if 'end_header' in line:
                    index = i
                    break
        input_df = pd.read_csv(in_file_name,skiprows=index+1+skiprows,usecols=usecols,delimiter=delimiter,names=col_names,index_col=False,nrows=nrows)

    elif ext == '.las' or ext == '.laz':
        las_data = lp.read(in_file_name)
        dim_names = las_data.point_format.dimension_names
        prop_dict = dict()
        for dim in dim_names:
            if dim == 'X' or dim == 'Y' or dim == 'Z':
                attr = dim.lower()
                prop_dict[attr] = np.c_[las_data[attr]].flatten()
            else:
                prop_dict[dim] = np.c_[las_data[dim]].flatten()
        if row_range:
            input_df = pd.DataFrame.from_dict(prop_dict).iloc[row_range,usecols]
        else:
            input_df = pd.DataFrame.from_dict(prop_dict).iloc[:,usecols]
        input_df.columns = col_names

    else:
        input_df = pd.read_csv(in_file_name,delimiter=delimiter,usecols=usecols,skiprows=skiprows,nrows=nrows,names=col_names)

    print('2. Checking the data')

    # [Gabriele] Check if in the whole dataset there are NaNs text and such
    val_check = input_df.apply(lambda c: pd.to_numeric(c, errors='coerce').notnull().all())



    if not val_check.all():
        print('Invalid values in data set, not importing.')
    else:



        print('3. Creating PointCloud')

        ''' [Gabriele] Correcting input data by subtracting an equal value approximated to the hundreds (53932.4325 -> 53932.4325 - 53900.0000 = 32.4325). Can be always applied since for numbers < 100 the approximation is always 0.'''

        input_df['X'] -= offset[0]
        input_df['Y'] -= offset[1]

        XYZ = np.array([input_df['X'].values,input_df['Y'].values,input_df['Z'].values]).T

        # [Gabriele] Create pyvista PolyData using XYZ data

        pv_PD = PlD(XYZ)

        ''' [Gabriele] Set properties (exclude XYZ data) and add properties names and components in the appropriate lists (properties_names and properties_components).'''
        properties_df = input_df.drop(['X','Y','Z'],axis=1)


        properties_components= []
        if not properties_df.empty:
            if 'Red' in properties_df.columns:
                pv_PD['RGB'] = np.array([input_df['Red'],input_df['Green'],input_df['Blue']]).T
                ''' [Gabriele] [PROBLEM] if the array is recasted to int8 the following error occurs vtkScalarsToColors.cxx:1487 ERR| vtkLookupTable (0x558e44fcfb30): char type does not have enough values to hold a color
                '''

                properties_df.drop(['Red','Green','Blue'],axis=1,inplace=True)
            print(pv_PD['RGB'])

            properties_names = list(properties_df.columns)

            for property in properties_names:
                properties_value = properties_df[property].values
                component_length = np.array(properties_value[0]).flatten().size
                properties_components.append(component_length)
                pv_PD[property] = properties_value
                # point_cloud.set_point_data(property,properties_value)
        else:
            properties_names = []

        print('4. Adding PC to project')
        point_cloud.ShallowCopy(pv_PD)
        point_cloud.Modified()

        """Create dictionary."""
        curr_obj_attributes = deepcopy(DomCollection.dom_entity_dict)
        curr_obj_attributes['uid'] = str(uuid.uuid4())
        curr_obj_attributes['name'] = basename
        curr_obj_attributes['dom_type'] = "PCDom"
        curr_obj_attributes['texture_uids'] = []
        curr_obj_attributes['properties_names'] = properties_names
        curr_obj_attributes['properties_components'] = properties_components
        curr_obj_attributes['vtk_obj'] = point_cloud
        self.TextTerminal.appendPlainText(f'vtk_obj: {curr_obj_attributes["vtk_obj"]}')
        """Add to entity collection."""
        self.dom_coll.add_entity_from_dict(entity_dict=curr_obj_attributes)
        self.TextTerminal.appendPlainText(f'Successfully imported {in_file_name}')
        """Cleaning."""
        del input_df
        del pv_PD
        del point_cloud
        print('Done!')
