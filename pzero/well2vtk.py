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
from .entities_factory import Wells
from uuid import uuid4
# from .entities_factory import WellData
from .helper_functions import auto_sep
from .well_collection import WellCollection
import pandas as pd

def well2vtk(in_file_name=None,col_names=None,row_range=None,header_row=None,usecols=None,delimiter=None,self=None):

    temp_path = "~/STORAGE/Unibro/Libri-e-dispense/Anno-5/Secondo-Semestre/Stage/Dati/villad/GIS"

    loc = pd.read_csv(f'{temp_path}/sondaggi_loc.csv',sep=',')
    data = pd.read_csv(f'{temp_path}/sondaggi.csv',sep=',')

    shape = data.shape[0]

    data.loc[shape] = [data['ID'].values[0],loc['PROFONDITA'].values[0],'END']

    print(data)

    unique_id = pd.unique(data['ID'])
    location = loc.loc[loc['Nome_indag'].values==unique_id[0],['Nome_indag','E','N','QUOTA']]
    direction = np.array([0,0,-1])

    center = location[['E','N','QUOTA']].values[0]

    legs = [0]
    for i,v in enumerate(data['prof_top'][1:]):
        legs.append(v-data['prof_top'][i])

    for i,l in enumerate(legs[:2]):
        center[2] -= l/2+legs[i+1]/2

        vtk_cyl = Wells()

        cylinder = pv.Cylinder(center=center,direction=direction,height=legs[i+1],radius=5,resolution=20)
        # cylinder = pv.Disc(center=center,normal=direction,outer=5,inner=0,c_res=100)

        vtk_cyl.ShallowCopy(cylinder)

        # print(vtk_cyl)

        curr_obj_attributes = deepcopy(WellCollection.well_entity_dict)
        curr_obj_attributes['uid'] = str(uuid4())
        curr_obj_attributes['Loc ID'] = f'{unique_id[0]}'
        curr_obj_attributes['geological_feature'] = f'{data.loc[i,"unit"]}'
        curr_obj_attributes['properties_names'] = []
        curr_obj_attributes['properties_components'] = []
        curr_obj_attributes['properties_types'] = []
        curr_obj_attributes['vtk_obj'] = vtk_cyl
        self.well_coll.add_entity_from_dict(entity_dict=curr_obj_attributes)
        del cylinder
        #
    # basename = os.path.basename(in_file_name)
    # _,ext = os.path.splitext(basename)
    # if ext == '.csv':
    #     sep = auto_sep(in_file_name)
    #     data = pd.read_csv(in_file_name,sep=delimiter,usecols=usecols,names=col_names)
    # elif ext == '.ags':
    #     print('ags format not supported')
    #
    # print(data)
