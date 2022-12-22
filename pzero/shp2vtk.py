"""shp2vtk.py
PZero© Andrea Bistacchi"""

from copy import deepcopy
from .entities_factory import PolyLine, VertexSet, Attitude
from numpy import array as np_array
from numpy import shape as np_shape
from numpy import zeros as np_zeros
from numpy import column_stack as np_column_stack
from geopandas import read_file as gpd_read_file
from vtk import vtkAppendPolyData
from .geological_collection import GeologicalCollection
from shapely.ops import split

from .orientation_analysis import dip_directions2normals
"""Importer for SHP files and other GIS formats, to be improved IN THE FUTURE.
Known bugs for multi-part polylines.
Points not handled correctly."""


# 'name': "undef"  ###
# 'topological_type': "undef"  ###
# 'geological_type': "undef"  ###
# 'geological_feature': "undef"  ###
# 'scenario': "undef"
# 'properties_names': []
# 'properties_components': []
# 'x_section': ""
# 'vtk_obj': None

def shp2vtk(self=None, in_file_name=None):
    """Import and add a points and polylines from shape files as VertexSet and PolyLine entities.
    <self> is the calling ProjectWindow() instance."""
    # try:
    """Read shape file into a GeoPandas dataframe. Each row is an entity with geometry stored in the geometry column in shapely format."""
    gdf = gpd_read_file(in_file_name)
    # print("geometry type: ", gdf.geom_type[0])
    # print("CRS:\n", gdf.crs)
    # if False in gdf.is_valid[:]:
    #     print("Not valid geometries found - aborting.")
    #     return
    # if True in gdf.is_empty[:]:
    #     print("Empty geometries found - aborting.")
    #     return
    column_names = list(gdf.columns)
    # print("Column names of GeoDataframe: ", list(gdf.columns))
    # print("GeoDataframe:\n", gdf)
    if (gdf.geom_type[0] == "LineString") or (gdf.geom_type[0] == "MultiLineString"):
        for row in range(gdf.shape[0]):
            # print("____ROW: ", row)
            # print("geometry type: ", gdf.geom_type[row])
            curr_obj_dict = deepcopy(GeologicalCollection.geological_entity_dict)
            # if gdf.is_valid[row] and not gdf.is_empty[row]:
            # try:
            if "name" in column_names:
                curr_obj_dict["name"] = gdf.loc[row, "name"]
            if "geological_type" in column_names:
                curr_obj_dict["geological_type"] = gdf.loc[row, "geological_type"]
            if "geo_type" in column_names:
                curr_obj_dict["geological_type"] = gdf.loc[row, "geo_type"]
            if "geological_feature" in column_names:
                curr_obj_dict["geological_feature"] = gdf.loc[row, "geological_feature"]
            if "geo_feat" in column_names:
                curr_obj_dict["geological_feature"] = gdf.loc[row, "geo_feat"]
            if "scenario" in column_names:
                curr_obj_dict["scenario"] = gdf.loc[row, "scenario"]
            curr_obj_dict["topological_type"] = "PolyLine"
            curr_obj_dict["vtk_obj"] = PolyLine()
            if gdf.geom_type[row] == "LineString":
                outXYZ = np_array(gdf.loc[row].geometry)
                # print("outXYZ:\n", outXYZ)
                print("np_shape(outXYZ):\n", np_shape(outXYZ))
                if np_shape(outXYZ)[1] == 2:
                    outZ = np_zeros((np_shape(outXYZ)[0], 1))
                    # print("outZ:\n", outZ)
                    outXYZ = np_column_stack((outXYZ, outZ))
                # print("outXYZ:\n", outXYZ)
                curr_obj_dict["vtk_obj"].points = outXYZ
                curr_obj_dict["vtk_obj"].auto_cells()
            elif gdf.geom_type[row] == "MultiLineString":
                outXYZ_list = np_array(gdf.loc[row].geometry)
                vtkappend = vtkAppendPolyData()
                for outXYZ in outXYZ_list:
                    temp_vtk = PolyLine()
                    # print("outXYZ:\n", outXYZ)
                    # print("np_shape(outXYZ):\n", np_shape(outXYZ))
                    if np_shape(outXYZ)[1] == 2:
                        outZ = np_zeros((np_shape(outXYZ)[0], 1))
                        # print("outZ:\n", outZ)
                        outXYZ = np_column_stack((outXYZ, outZ))
                    # print("outXYZ:\n", outXYZ)
                    temp_vtk.points = outXYZ
                    temp_vtk.auto_cells()
                    vtkappend.AddInputData(temp_vtk)
                vtkappend.Update()
                curr_obj_dict["vtk_obj"].ShallowCopy(vtkappend.GetOutput())
            """Create entity from the dictionary and run left_right."""
            if curr_obj_dict["vtk_obj"].points_number > 0:
                output_uid = self.geol_coll.add_entity_from_dict(curr_obj_dict)
            else:
                print("Empty object")
            # else:
            # except:
            #     print("Invalid object")
            del curr_obj_dict
    elif gdf.geom_type[0] == "Point":
        if "geo_feat" in column_names:
            gdf_index = gdf.set_index("geo_feat")
            feat_list = set(gdf_index.index)



            for i in feat_list:
                curr_obj_dict = deepcopy(GeologicalCollection.geological_entity_dict)

                if 'dip' in gdf.columns:
                    vtk_obj = Attitude()
                else:
                    vtk_obj = VertexSet()

                if "name" in column_names:
                    curr_obj_dict["name"] = gdf_index.loc[i, "name"][0]
                if "geological_type" in column_names:
                    curr_obj_dict["geological_type"] = gdf_index.loc[i, "geological_type"][0]
                if "geo_type" in column_names:
                    curr_obj_dict["geological_type"] = gdf_index.loc[i, "geo_type"][0]
                if "geological_feature" in column_names:
                    curr_obj_dict["geological_feature"] = i
                if "geo_feat" in column_names:
                    curr_obj_dict["geological_feature"] = i
                if "scenario" in column_names:
                    curr_obj_dict["scenario"] = gdf_index.loc[row, "scenario"]

                curr_obj_dict["topological_type"] = "VertexSet"
                curr_obj_dict["vtk_obj"] = vtk_obj

                gdf_index['coords'] = gdf_index.geometry.apply(lambda x: np_array(x)) # [Gabriele] add a coordinate column in the gdf_index dataframe
                outXYZ = np_array([p for p in gdf_index.loc[i, 'coords']])

                if np_shape(outXYZ)[1] == 2:
                    outZ = np_zeros((np_shape(outXYZ)[0], 1))
                    # print("outZ:\n", outZ)
                    outXYZ = np_column_stack((outXYZ, outZ))
                # print(np_shape(outXYZ))
                curr_obj_dict["vtk_obj"].points = outXYZ

                if 'dip_dir' in column_names:
                    dir = (gdf_index.loc[i, "dip_dir"]-90)%360
                    curr_obj_dict["vtk_obj"].set_point_data('dir', dir.values)
                if 'dir' in column_names:
                    curr_obj_dict["vtk_obj"].set_point_data('dir', gdf_index.loc[i, "dir"].values)
                if 'dip':
                    curr_obj_dict["vtk_obj"].set_point_data('dip', gdf_index.loc[i, "dip"].values)
                if 'dip' in column_names and ('dir' in column_names or 'dip_dir' in column_names):
                    normals = dip_directions2normals(curr_obj_dict["vtk_obj"].get_point_data('dip'), curr_obj_dict["vtk_obj"].get_point_data('dir'))
                    curr_obj_dict["vtk_obj"].set_point_data('Normals',normals)




                if curr_obj_dict["vtk_obj"].points_number > 0:
                    curr_obj_dict["vtk_obj"].auto_cells()
                    # print(curr_obj_dict["vtk_obj"].point_data_keys)
                    properties_names = curr_obj_dict["vtk_obj"].point_data_keys
                    properties_components = [curr_obj_dict["vtk_obj"].get_point_data_shape(key)[1] for key in properties_names]
                    curr_obj_dict['properties_names'] = properties_names
                    curr_obj_dict['properties_components'] = properties_components
                    output_uid = self.geol_coll.add_entity_from_dict(curr_obj_dict)
                    del curr_obj_dict
        else:
            print('Incomplete data. At least the geological_feature property must be present')
    else:
        print("Only Point and Line geometries can be imported - aborting.")
        return  # except:  #     self.TextTerminal.appendPlainText("SHP file not recognized ERROR.")
