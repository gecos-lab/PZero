"""well2vtk.py by Gabriele Benedetti
PZero© Andrea Bistacchi
--------
Convert well data (csv, ags ...) in vtk objects.

"""

import numpy as np
import os
from copy import deepcopy
import vtk
import pyvista as pv
from .entities_factory import Well,WellTrace,WellMarker
from uuid import uuid4
# from .entities_factory import WellData
from .helper_functions import auto_sep
from .well_collection import WellCollection
from .geological_collection import GeologicalCollection
from .fluid_collection import FluidsCollection
import pandas as pd
# import lasio as ls

def well2vtk(self,path=None):

    well_obj = Well()
    data = pd.read_excel(path,sheet_name=None)
    well_data = data['INFO']

    # Get and set well head data

    xyz_head = np.array([well_data['EASTING'].values,well_data['NORTHING'].values,well_data['ELEV'].values]).reshape(-1,3)
    well_obj.head = [xyz_head,well_data['WELL'].values[0]]

    # Get and set well trace data
    dir = os.path.dirname(path)
    trace_data = data['GEOMETRY']
    
    x = well_obj.head.points_X-trace_data['DX']
    y = well_obj.head.points_Y-trace_data['DY']
    z = well_obj.head.points_Z-trace_data['DZ']

    xyz_trace = np.vstack([x,y,z]).T.reshape(-1,3)
    well_obj.trace = xyz_trace

    #Get and set curve data

    prop_df = data.copy()

    del prop_df['INFO']
    del prop_df['GEOMETRY']

    arr = well_obj.trace.get_point_data(data_key='arc_length')
    # print(arr)
    points = well_obj.trace.points_number
    for key in prop_df:
        prop = prop_df[key]

        if 'START' in prop.columns:
            if key == 'LITHOLOGY' or key == 'GEOLOGY':
                tr_data = np.full(shape=(points,3),fill_value=np.nan)

                color_dict = {k: np.random.randint(255,size=3) for k in pd.unique(prop[key])}
                for row,(start,end,value) in prop.iterrows():

                        start_idx = np.argmin(np.abs(arr - start))
                        end_idx = np.argmin(np.abs(arr - end))
                        # print(key)
                        # print(len(curve_copy.points[start_idx:end_idx]))
                        color_val = color_dict[value]
                        tr_data[start_idx:end_idx] = color_val
            else:
                tr_data = np.full(shape=points,fill_value=np.nan)
                for row,(start,end,value) in prop.iterrows():
                    start_idx = np.argmin(np.abs(arr - start))
                    end_idx = np.argmin(np.abs(arr - end))
                    # print(key)
                    # print(len(curve_copy.points[start_idx:end_idx]))
                    tr_data[start_idx:end_idx] = value
            well_obj.add_trace_data(name=f'{key}',tr_data=tr_data)
        elif 'MD_point' in prop.columns:
                prop = prop.set_index('MD_point')
                for col in prop.columns:
                    mrk_pos = []
                    mrk_data = []
                    for row in prop.index:
                        idx = np.argmin(np.abs(arr - row))
                        value = prop.loc[row,col]
                        mrk_data.append(value)
                        mrk_pos.append(well_obj.trace.points[idx,:])
                    well_obj.add_marker_data(name=f'{col}',mrk_pos=mrk_pos,mrk_data=mrk_data)
        else:
                prop = prop.set_index('MD')
                for col in prop.columns:
                    tr_data = np.full(shape=points,fill_value=np.nan)
                    for row in prop.index:
                        idx = np.argmin(np.abs(arr - row))
                        value = prop.loc[row,col]
                        tr_data[idx] = value

                    well_obj.add_trace_data(name=f'{col}',tr_data=tr_data)


    keys = well_obj.trace.get_field_data_keys()
    keys = [key for key in keys if 'pmarker' not in key]
    components = []
    types = []
    for key in keys:
        components.append(well_obj.trace.get_field_data_shape(key)[1])
        types.append(well_obj.trace.get_field_data_type(key))
    curr_obj_attributes = deepcopy(WellCollection.well_entity_dict)
    curr_obj_attributes['uid'] = str(uuid4())
    curr_obj_attributes['Loc ID'] = well_obj.ID
    curr_obj_attributes['properties_names'] = keys
    curr_obj_attributes['properties_components'] = components
    curr_obj_attributes['properties_types'] = types
    curr_obj_attributes['vtk_head'] = well_obj.head
    curr_obj_attributes['vtk_trace'] = well_obj.trace
    self.well_coll.add_entity_from_dict(entity_dict=curr_obj_attributes)


    # paths = in_file_name

    # data_paths = paths[1]
    # #Read the Well location data file
    # loc = pd.read_csv(paths[0],sep=delimiter[0],usecols=usecols[0],names=col_names[0],header=header_row)

    # #Read the well data file(s)
    # for path in data_paths:

    #     data = pd.read_csv(path,sep=delimiter[1],usecols=usecols[1],names=col_names[1],header=header_row)

    #     if 'DepthPoint' in col_names[1]:
    #         punt_data_idx = data.columns.loc('DepthPoint')
    #         cont_data = data.loc[:,:punt_data_idx].set_index('LocationID')
    #         punt_data = data.loc[:,punt_data_idx:].set_index('LocationID')
    #     else:
    #         cont_data = data.set_index('LocationID')
    #         punt_data = None






    #     shape = cont_data.shape[0]

    #     # cont_data.loc[shape] = [data['LocationID'].values[0],loc['FinalDepth'].values[0],'END']

    #     print(cont_data)




    #     unique_id = pd.unique(data['LocationID'])
    #     location = loc.loc[loc['LocationID'].values==unique_id[0],['LocationID','Easting','Northing','GroundLevel']]

    #     top = np.array(location[['Easting','Northing','GroundLevel']].values[0])

    #     if ('Trend' or 'Plunge') not in list(loc.keys()) or (pd.isna(loc.loc[loc['LocationID'].values==unique_id[0],'Trend'].values) or pd.isna(loc.loc[loc['LocationID'].values==unique_id[0],'Plunge'].values)) :
    #         print('Trend or plunge value not specified. Assuming vertical borehole')
    #         trend = 0
    #         plunge = np.deg2rad(90)
    #     else:
    #         trend = np.deg2rad(loc.loc[loc['LocationID'].values==unique_id[0],'Trend'].values[0])
    #         plunge = np.deg2rad(loc.loc[loc['LocationID'].values==unique_id[0],'Plunge'].values[0])

    #     legs = [0]
    #     for i,v in enumerate(data['DepthTop'][1:]):
    #         legs.append(v-data['DepthTop'][i])
    #     color = dict()
    #     appender = vtk.vtkAppendPolyData()
    #     cont_data_filt  = cont_data[~cont_data.iloc[:,1:].isnull().all(1)]
    #     legs = cont_data_filt['DepthTop'].values
    #     appender = vtk.vtkAppendPolyData()
    #     cont_data_cols = cont_data_filt.columns
    #     for c in cont_data_cols:
    #             for i,l in enumerate(legs[:-1]):
    #                 cell_data = cont_data_filt.loc[cont_data_filt['DepthTop']==l,c]
    #                 print(cell_data)
    #                 if not cell_data.isnull().any():

    #                     length = legs[i+1]

    #                     # top[2] -= l
    #                     x_bottom = top[0]+(length*np.cos(plunge)*np.sin(trend))
    #                     y_bottom = top[1]+(length*np.cos(plunge)*np.cos(trend))
    #                     z_bottom = top[2]-(length*np.sin(plunge))

    #                     bottom = np.array([x_bottom,y_bottom,z_bottom])

    #                     points = np.array([top,bottom])

    #                     seg = pv.Spline(points)
    #                     seg.cell_data[c] = cell_data.values

    #                 #
    #                 #
    #                 # # marker_pv = pv.PolyData(top)
    #                 #
    #                 #

    #                 #
    #                 # well_marker = WellMarker()
    #                 #
    #                 # # well_marker.ShallowCopy(marker_pv)
    #                 #
    #                 #
    #                 #





    #                     appender.AddInputData(seg)
    #     appender.Update()
    #     well_line = Wells()
    #     well_line.ShallowCopy(appender.GetOutput())

    #     test = pv.PolyData()
    #     test.ShallowCopy(well_line)
    #     test.plot()
        
        
    #     # well_marker.points = np.array([top])
    #     # well_marker.auto_cells()
        
    #     # top = np.array([x_bottom,y_bottom,z_bottom])
        
    #     # geo_code = data.loc[i,"GeologyCode"]
        
    #     # curr_obj_attributes = deepcopy(WellCollection.well_entity_dict)
    #     # curr_obj_attributes['uid'] = str(uuid4())
    #     # curr_obj_attributes['Loc ID'] = f'{unique_id[0]}'
    #     # curr_obj_attributes['geological_feature'] = f'{geo_code}'
    #     # curr_obj_attributes['properties_names'] = []
    #     # curr_obj_attributes['properties_components'] = []
    #     # curr_obj_attributes['properties_types'] = []
    #     # curr_obj_attributes['vtk_obj'] = well_line
        
    #     # marker_obj_attributes = deepcopy(GeologicalCollection.geological_entity_dict)
    #     # marker_obj_attributes['uid'] = str(uuid4())
    #     # marker_obj_attributes['name'] = f'{data.loc[i,"GeologyCode"]}_marker'
    #     # marker_obj_attributes["topological_type"] = "VertexSet"
    #     # marker_obj_attributes['geological_type'] = 'top'
    #     # marker_obj_attributes['geological_feature'] = f'{geo_code}'
    #     # marker_obj_attributes['scenario'] = f'{unique_id[0]}'
    #     # marker_obj_attributes['properties_names'] = []
    #     # marker_obj_attributes['properties_components'] = []
    #     # marker_obj_attributes['properties_types'] = []
    #     # marker_obj_attributes['x_section'] = curr_obj_attributes['uid']
    #     # marker_obj_attributes['vtk_obj'] = well_marker
        
    #     # self.geol_coll.add_entity_from_dict(entity_dict=marker_obj_attributes)
        
        
        
    #     # self.well_coll.add_entity_from_dict(entity_dict=curr_obj_attributes)
        
    #     # del well_line
    #     # del well_marker
    
    # # basename = os.path.basename(in_file_name)
    # # _,ext = os.path.splitext(basename)
    # # if ext == '.csv':
    # #     sep = auto_sep(in_file_name)
    # #     data = pd.read_csv(in_file_name,sep=delimiter,usecols=usecols,names=col_names)
    # # elif ext == '.ags':
    # #     print('ags format not supported')
    # #
    # # print(data)
