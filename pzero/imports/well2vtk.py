"""well2vtk.py by Gabriele Benedetti
PZero© Andrea Bistacchi
--------
Convert well data (csv, ags ...) to vtk objects.

"""

from copy import deepcopy

from uuid import uuid4

from pandas import read_excel as pd_read_excel
from pandas import unique as pd_unique

from numpy import abs as np_abs
from numpy import append as np_append
from numpy import argmin as np_argmin
from numpy import array as np_array
from numpy import full as np_full
from numpy import nan as np_nan
from numpy import random as np_random
from numpy import vstack as np_vstack
from numpy import zeros as np_zeros

from pzero.collections.background_collection import BackgroundCollection
from pzero.collections.geological_collection import GeologicalCollection
from pzero.collections.well_collection import WellCollection
from pzero.entities_factory import Well, VertexSet


def well2vtk(self, path=None):
    data = pd_read_excel(path, sheet_name=None)
    well_data = data["INFO"]
    well_id = well_data["WELL"].values[0]

    # Get and set well head data

    xyz_head = np_array(
        [
            well_data["EASTING"].values,
            well_data["NORTHING"].values,
            well_data["ELEV"].values,
        ]
    ).reshape(-1, 3)
    well_head = xyz_head

    # Get and set well trace data
    trace_data = data["GEOMETRY"]

    x = xyz_head[0, 0] - trace_data["DX"]
    y = xyz_head[0, 1] - trace_data["DY"]
    z = xyz_head[0, 2] - trace_data["DZ"]

    xyz_trace = np_vstack([x, y, z]).T.reshape(-1, 3)

    well_obj = Well(ID=well_id, trace_xyz=xyz_trace, head_xyz=xyz_head)

    # Get and set curve data

    prop_df = data.copy()

    del prop_df["INFO"]
    del prop_df["GEOMETRY"]

    arr = well_obj.trace.get_point_data(data_key="MD")
    points = well_obj.trace.points_number
    ann_list = []
    well_uid = str(uuid4())
    for key in prop_df:
        prop = prop_df[key]
        if "START" in prop.columns:
            if key in ("LITHOLOGY", "GEOLOGY"):
                tr_data = np_full(shape=(points, 3), fill_value=np_nan)

                try:
                    color_dict = {
                        k: np_random.rand(3) for k in pd_unique(prop[key])
                    }
                except Exception:
                    print("No key found")
                else:
                    for row, (start, end, value) in prop.iterrows():
                        start_idx = np_argmin(np_abs(arr - start))
                        end_idx = np_argmin(np_abs(arr - end))

                        if key == "GEOLOGY":
                            marker_pos = well_obj.trace.points[
                                start_idx, :
                            ].reshape(-1, 3)
                            marker_obj = VertexSet()
                            marker_obj.points = marker_pos
                            marker_obj.auto_cells()

                            marker_obj_dict = deepcopy(
                                GeologicalCollection().entity_dict
                            )
                            marker_obj_dict["topology"] = "VertexSet"
                            marker_obj_dict["uid"] = str(uuid4())
                            marker_obj_dict["name"] = f"marker_{value}"
                            marker_obj_dict["role"] = "top"
                            marker_obj_dict["feature"] = value
                            marker_obj_dict["x_section"] = well_uid
                            marker_obj_dict["vtk_obj"] = marker_obj
                            self.geol_coll.add_entity_from_dict(marker_obj_dict)
                            color_R = (
                                self.geol_coll.get_uid_legend(
                                    uid=marker_obj_dict["uid"]
                                )["color_R"]
                                / 255
                            )
                            color_G = (
                                self.geol_coll.get_uid_legend(
                                    uid=marker_obj_dict["uid"]
                                )["color_G"]
                                / 255
                            )
                            color_B = (
                                self.geol_coll.get_uid_legend(
                                    uid=marker_obj_dict["uid"]
                                )["color_B"]
                                / 255
                            )
                            color_dict[value] = np_array(
                                [color_R, color_G, color_B]
                            )
                            del marker_obj_dict
                        color_val = color_dict[value]

                        tr_data[start_idx:end_idx] = color_val
            else:
                tr_data = np_zeros(shape=points)
                for row, (start, end, value) in prop.iterrows():
                    start_idx = np_argmin(np_abs(arr - start))
                    end_idx = np_argmin(np_abs(arr - end))
                    tr_data[start_idx:end_idx] = value
                    # tr_data.insert(0,0)
            well_obj.add_trace_data(
                name=f"{key}", tr_data=tr_data, xyz=well_obj.trace.points
            )
        elif "MD_point" in prop.columns:
            prop = prop.set_index("MD_point")
            for col in prop.columns:
                annotation_obj = VertexSet()
                mrk_pos = np_array([])
                mrk_data = np_array([])
                for row in prop.index:
                    idx = np_argmin(np_abs(arr - row))
                    value = prop.loc[row, col]
                    mrk_data = np_append(mrk_data, value)
                    mrk_pos = np_append(mrk_pos, well_obj.trace.points[idx, :])
                annotation_obj.points = mrk_pos.reshape(-1, 3)
                annotation_obj.auto_cells()
                annotation_obj.set_field_data(name=col, data=mrk_data)
                ann_list.append(annotation_obj)
        else:
            prop = prop.set_index("MD")
            for col in prop.columns:
                prop_clean = prop[col].dropna()

                points_arr = well_obj.trace.points
                tr_data = prop_clean.values
                xyz = np_zeros(shape=(len(prop_clean), 3))

                for i, row in enumerate(prop_clean.index):
                    idx = np_argmin(np_abs(arr - row))
                    # value = prop_clean.loc[row]
                    xyz[i, :] = points_arr[idx, :]
                well_obj.add_trace_data(name=f"{col}", tr_data=tr_data, xyz=xyz)

    trace_keys = well_obj.get_trace_names()
    components = []
    types = []
    for key in trace_keys:
        components.append(well_obj.trace.get_field_data_shape(key)[1])
        types.append(well_obj.trace.get_field_data_type(key))

    bore_obj_attributes = deepcopy(WellCollection().entity_dict)
    bore_obj_attributes["uid"] = well_uid
    # Ensure proper identification in WellCollection
    bore_obj_attributes["name"] = well_obj.ID
    bore_obj_attributes["topology"] = "PolyLine"
    bore_obj_attributes["Loc ID"] = well_obj.ID
    bore_obj_attributes["properties_names"] = trace_keys
    bore_obj_attributes["properties_components"] = components
    bore_obj_attributes["properties_types"] = types
    bore_obj_attributes["vtk_obj"] = well_obj.trace
    self.well_coll.add_entity_from_dict(entity_dict=bore_obj_attributes)

    for annotation in ann_list:
        ann_keys = annotation.point_data_keys
        name = annotation.get_field_data_keys()[0]
        components = []
        types = []
        for key in ann_keys:
            components.append(annotation.trace.get_point_data_shape(key)[1])
            types.append(annotation.trace.get_point_data_type(key))

        annotation_obj_attributes = deepcopy(BackgroundCollection().entity_dict)
        annotation_obj_attributes["uid"] = str(uuid4())
        annotation_obj_attributes["name"] = name
        annotation_obj_attributes["topology"] = "VertexSet"
        annotation_obj_attributes["role"] = "Annotations"
        annotation_obj_attributes["feature"] = well_obj.ID

        annotation_obj_attributes["properties_names"] = ann_keys
        annotation_obj_attributes["properties_components"] = components
        annotation_obj_attributes["properties_types"] = types
        annotation_obj_attributes["borehole"] = bore_obj_attributes["uid"]

        annotation_obj_attributes["vtk_obj"] = annotation
        self.backgrnd_coll.add_entity_from_dict(entity_dict=annotation_obj_attributes)
    # paths = in_file_name

    # data_paths = paths[1]
    # #Read the Well location data file
    # loc = pd_read_csv(paths[0],sep=delimiter[0],usecols=usecols[0],names=col_names[0],header=header_row)

    # #Read the well data file(s)
    # for path in data_paths:

    #     data = pd_read_csv(path,sep=delimiter[1],usecols=usecols[1],names=col_names[1],header=header_row)

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

    #     unique_id = pd_unique(data['LocationID'])
    #     location = loc.loc[loc['LocationID'].values==unique_id[0],['LocationID','Easting','Northing','GroundLevel']]

    #     top = np_array(location[['Easting','Northing','GroundLevel']].values[0])

    #     if ('Trend' or 'Plunge') not in list(loc.keys()) or (pd_isna(loc.loc[loc['LocationID'].values==unique_id[0],'Trend'].values) or pd_isna(loc.loc[loc['LocationID'].values==unique_id[0],'Plunge'].values)) :
    #         print('Trend or plunge value not specified. Assuming vertical borehole')
    #         trend = 0
    #         plunge = np_deg2rad(90)
    #     else:
    #         trend = np_deg2rad(loc.loc[loc['LocationID'].values==unique_id[0],'Trend'].values[0])
    #         plunge = np_deg2rad(loc.loc[loc['LocationID'].values==unique_id[0],'Plunge'].values[0])

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
    #                     x_bottom = top[0]+(length*np_cos(plunge)*np_sin(trend))
    #                     y_bottom = top[1]+(length*np_cos(plunge)*np_cos(trend))
    #                     z_bottom = top[2]-(length*np_sin(plunge))

    #                     bottom = np_array([x_bottom,y_bottom,z_bottom])

    #                     points = np_array([top,bottom])

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

    #     # well_marker.points = np_array([top])
    #     # well_marker.auto_cells()

    #     # top = np_array([x_bottom,y_bottom,z_bottom])

    #     # geo_code = data.loc[i,"GeologyCode"]

    #     # curr_obj_attributes = deepcopy(WellCollection.entity_dict)
    #     # curr_obj_attributes['uid'] = str(uuid4())
    #     # curr_obj_attributes['Loc ID'] = f'{unique_id[0]}'
    #     # curr_obj_attributes['feature'] = f'{geo_code}'
    #     # curr_obj_attributes['properties_names'] = []
    #     # curr_obj_attributes['properties_components'] = []
    #     # curr_obj_attributes['properties_types'] = []
    #     # curr_obj_attributes['vtk_obj'] = well_line

    #     # marker_obj_attributes = deepcopy(GeologicalCollection.entity_dict)
    #     # marker_obj_attributes['uid'] = str(uuid4())
    #     # marker_obj_attributes['name'] = f'{data.loc[i,"GeologyCode"]}_marker'
    #     # marker_obj_attributes["topology"] = "VertexSet"
    #     # marker_obj_attributes['role'] = 'top'
    #     # marker_obj_attributes['feature'] = f'{geo_code}'
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
    # #     data = pd_read_csv(in_file_name,sep=delimiter,usecols=usecols,names=col_names)
    # # elif ext == '.ags':
    # #     print('ags format not supported')
    # #
    # # print(data)
