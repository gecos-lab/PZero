"""shp2vtk.py
PZero© Andrea Bistacchi"""

import os
from copy import deepcopy
import uuid
from .entities_factory import PolyLine, VertexSet
import pyvista as pv
import xarray as xr
import numpy as np
import geopandas as gpd
import pandas as pd
from .geological_collection import GeologicalCollection
from .two_d_lines import left_right
from shapely import affinity
from shapely.geometry import asLineString, LineString, Point, asPoint, MultiLineString
from shapely.ops import split, snap

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
    gdf = gpd.read_file(in_file_name)
    print("geometry type: ", gdf.geom_type[0])
    print("CRS:\n", gdf.crs)
    # if False in gdf.is_valid[:]:
    #     print("Not valid geometries found - aborting.")
    #     return
    # if True in gdf.is_empty[:]:
    #     print("Empty geometries found - aborting.")
    #     return
    column_names = list(gdf.columns)
    print("Column names of GeoDataframe: ", list(gdf.columns))
    print("GeoDataframe:\n", gdf)
    if gdf.geom_type[0] == "LineString":
        for row in range(gdf.shape[0]):
            print("____ROW: ", row)
            curr_obj_dict = deepcopy(GeologicalCollection.geological_entity_dict)
            # if gdf.is_valid[row] and not gdf.is_empty[row]:
            try:
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
                outXYZ = np.array(gdf.loc[row].geometry)
                print("outXYZ:\n", outXYZ)
                print("np.shape(outXYZ):\n", np.shape(outXYZ))
                if np.shape(outXYZ)[1] == 2:
                    outZ = np.zeros((np.shape(outXYZ)[0], 1))
                    print("outZ:\n", outZ)
                    outXYZ = np.column_stack((outXYZ, outZ))
                print("outXYZ:\n", outXYZ)
                curr_obj_dict["vtk_obj"].points = outXYZ
                curr_obj_dict["vtk_obj"].auto_cells()
                """Create entity from the dictionary and run left_right."""
                if curr_obj_dict["vtk_obj"].points_number > 0:
                    output_uid = self.geol_coll.add_entity_from_dict(curr_obj_dict)
                else:
                    print("Empty object")
            # else:
            except:
                print("Invalid object")
            del curr_obj_dict
    elif gdf.geom_type[0] == "Point":
        print("VertexSet not yet implemented.")
    else:
        print("Only Point and Line geometries can be imported - aborting.")
        return
    # except:
    #     self.TextTerminal.appendPlainText("SHP file not recognized ERROR.")
