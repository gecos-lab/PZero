"""well2vtk.py by Gabriele Benedetti
PZero© Andrea Bistacchi
--------
Convert well data (csv, ags ...) in vtk objects.

"""

from numpy import array as np_array
from numpy import deg2rad as np_deg2rad
from numpy import cos as np_cos
from numpy import sin as np_sin

from copy import deepcopy

from .entities_factory import Wells,WellMarker
from uuid import uuid4
# from .entities_factory import WellData

from .well_collection import WellCollection
from .geological_collection import GeologicalCollection

from pandas import read_csv as pd_read_csv
from pandas import unique as pd_unique
from pandas import isna as pd_isna

def well2vtk(in_file_name=None,col_names=None,row_range=None,header_row=None,usecols=None,delimiter=None,self=None):

    paths = in_file_name

    data_paths = paths[1]

    print(data_paths)

    loc = pd_read_csv(paths[0],sep=delimiter[0],usecols=usecols[0],names=col_names[0],header=header_row)

    for path in data_paths:

        data = pd_read_csv(path,sep=delimiter[1],usecols=usecols[1],names=col_names[1],header=header_row)

        shape = data.shape[0]

        data.loc[shape] = [data['LocationID'].values[0],loc['FinalDepth'].values[0],'END']

        unique_id = pd_unique(data['LocationID'])
        location = loc.loc[loc['LocationID'].values==unique_id[0],['LocationID','Easting','Northing','GroundLevel']]
        direction = np_array([0,0,-1])

        top = np_array(location[['Easting','Northing','GroundLevel']].values[0])

        if ('Trend' or 'Plunge') not in list(loc.keys()) or (pd_isna(loc.loc[loc['LocationID'].values==unique_id[0],'Trend'].values) or pd_isna(loc.loc[loc['LocationID'].values==unique_id[0],'Plunge'].values)) :
            print('Trend or plunge value not specified. Assuming vertical borehole')
            trend = 0
            plunge = np_deg2rad(90)
        else:
            trend = np_deg2rad(loc.loc[loc['LocationID'].values==unique_id[0],'Trend'].values[0])
            plunge = np_deg2rad(loc.loc[loc['LocationID'].values==unique_id[0],'Plunge'].values[0])
            print(trend,plunge)


        legs = [0]
        for i,v in enumerate(data['DepthTop'][1:]):
            legs.append(v-data['DepthTop'][i])
        color = dict()
        for i,l in enumerate(legs[:2]):

            length = legs[i+1]

            # top[2] -= l
            x_bottom = top[0]+(length*np_cos(plunge)*np_sin(trend))
            y_bottom = top[1]+(length*np_cos(plunge)*np_cos(trend))
            z_bottom = top[2]-(length*np_sin(plunge))

            bottom = np_array([x_bottom,y_bottom,z_bottom])

            points = np_array([top,bottom])


            # marker_pv = pv.PolyData(top)


            well_line = Wells()

            well_marker = WellMarker()

            # well_marker.ShallowCopy(marker_pv)



            well_line.points = points
            well_line.auto_cells()
            well_marker.points = np_array([top])
            well_marker.auto_cells()

            top = np_array([x_bottom,y_bottom,z_bottom])

            geo_code = data.loc[i,"GeologyCode"]

            curr_obj_attributes = deepcopy(WellCollection.well_entity_dict)
            curr_obj_attributes['uid'] = str(uuid4())
            curr_obj_attributes['Loc ID'] = f'{unique_id[0]}'
            curr_obj_attributes['geological_feature'] = f'{geo_code}'
            curr_obj_attributes['properties_names'] = []
            curr_obj_attributes['properties_components'] = []
            curr_obj_attributes['properties_types'] = []
            curr_obj_attributes['vtk_obj'] = well_line

            marker_obj_attributes = deepcopy(GeologicalCollection.geological_entity_dict)
            marker_obj_attributes['uid'] = str(uuid4())
            marker_obj_attributes['name'] = f'{data.loc[i,"GeologyCode"]}_marker'
            marker_obj_attributes["topological_type"] = "VertexSet"
            marker_obj_attributes['geological_type'] = 'top'
            marker_obj_attributes['geological_feature'] = f'{geo_code}'
            marker_obj_attributes['scenario'] = f'{unique_id[0]}'
            marker_obj_attributes['properties_names'] = []
            marker_obj_attributes['properties_components'] = []
            marker_obj_attributes['properties_types'] = []
            marker_obj_attributes['x_section'] = curr_obj_attributes['uid']
            marker_obj_attributes['vtk_obj'] = well_marker

            self.geol_coll.add_entity_from_dict(entity_dict=marker_obj_attributes)



            self.well_coll.add_entity_from_dict(entity_dict=curr_obj_attributes)





            del well_line
            del well_marker
        #
    # basename = os.path.basename(in_file_name)
    # _,ext = os.path.splitext(basename)
    # if ext == '.csv':
    #     sep = auto_sep(in_file_name)
    #     data = pd_read_csv(in_file_name,sep=delimiter,usecols=usecols,names=col_names)
    # elif ext == '.ags':
    #     print('ags format not supported')
    #
    # print(data)
