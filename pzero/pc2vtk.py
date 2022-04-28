"""pc2vtk.py by Gabriele Benedetti
PZero© Andrea Bistacchi
--------

Convert point cloud data (txt, csv, xyz, las ...) in vtk objects.


"""


import numpy as np
import os
from copy import deepcopy
from vtk import vtkPoints,vtkCellArray, vtkPointSet
from uuid import uuid4
from .entities_factory import PCDom
from .dom_collection import DomCollection
from pyvista import PolyData as PlD
from pyvista import vtk_points
# import pyvista as pv
from pandas import DataFrame as pd_df
from pandas import to_numeric as pd_to_numeric
from pandas import read_csv as pd_read_csv

from laspy import read as lp_read
# from .helper_functions import profiler


def pc2vtk(in_file_name,col_names,row_range,header_row,usecols,delimiter,offset,self=None):


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
        input_df = pd_read_csv(in_file_name,skiprows=index+1+skiprows,usecols=usecols,delimiter=delimiter,names=col_names,index_col=False,nrows=nrows)

    elif ext == '.las' or ext == '.laz':
        las_data = lp_read(in_file_name)
        dim_names = las_data.point_format.dimension_names
        prop_dict = dict()
        for dim in dim_names:
            if dim == 'X' or dim == 'Y' or dim == 'Z':
                attr = dim.lower()
                prop_dict[attr] = np.c_[las_data[attr]].flatten()
            else:
                prop_dict[dim] = np.c_[las_data[dim]].flatten()
        if row_range:
            input_df = pd_df.from_dict(prop_dict).iloc[row_range,usecols]
        else:
            input_df = pd_df.from_dict(prop_dict).iloc[:,usecols]
        input_df.columns = col_names

    else:
        input_df = pd_read_csv(in_file_name,delimiter=delimiter,usecols=usecols,skiprows=skiprows,nrows=nrows,names=col_names)

    print('2. Checking the data')

    # [Gabriele] Check if in the whole dataset there are NaNs text and such
    val_check = input_df.apply(lambda c: pd_to_numeric(c, errors='coerce').notnull().all())



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
        input_df.drop(['X','Y','Z'],axis=1,inplace=True)

        if not input_df.empty:
            if 'Red' in input_df.columns:
                # print(properties_df)
                if self.check255Box.isChecked():
                    pv_PD['RGB'] = np.array([input_df['Red'],input_df['Green'],input_df['Blue']]).T.astype(np.uint8)
                else:
                    pv_PD['RGB'] = np.array([input_df['Red'],input_df['Green'],input_df['Blue']]).T


                input_df.drop(['Red','Green','Blue'],axis=1,inplace=True)

            for property in input_df.columns:
                pv_PD[property] = input_df[property].values
                # point_cloud.set_point_data(property,properties_value)

        print('4. Adding PC to project')
        point_cloud.ShallowCopy(pv_PD)
        point_cloud.Modified()
        properties_names = point_cloud.point_data_keys
        properties_components = [point_cloud.get_point_data_shape(i)[1] for i in properties_names]
        properties_types = [point_cloud.get_point_data_type(i) for i in properties_names]

        """Create dictionary."""
        curr_obj_attributes = deepcopy(DomCollection.dom_entity_dict)
        curr_obj_attributes['uid'] = str(uuid4())
        curr_obj_attributes['name'] = basename
        curr_obj_attributes['dom_type'] = "PCDom"
        curr_obj_attributes['texture_uids'] = []
        curr_obj_attributes['properties_names'] = properties_names
        curr_obj_attributes['properties_components'] = properties_components
        curr_obj_attributes['properties_types'] = properties_types
        curr_obj_attributes['vtk_obj'] = point_cloud
        """Add to entity collection."""
        self.parent.dom_coll.add_entity_from_dict(entity_dict=curr_obj_attributes)
        """Cleaning."""
        del input_df
        del pv_PD
        del point_cloud
        print('Done!')
