"""shp2vtk.py
PZero© Andrea Bistacchi"""

from copy import deepcopy

from geopandas import read_file as gpd_read_file
from numpy import array as np_array
from numpy import asarray as np_asarray
from numpy import column_stack as np_column_stack
from numpy import shape as np_shape
from numpy import zeros as np_zeros
from pandas import Series as pd_series
from vtk import vtkAppendPolyData

from pzero.collections.background_collection import BackgroundCollection
from pzero.collections.fluid_collection import FluidsCollection
from pzero.collections.geological_collection import GeologicalCollection
from pzero.entities_factory import PolyLine, VertexSet, Attitude
from pzero.orientation_analysis import dip_directions2normals

"""Importer for SHP files and other GIS formats, to be improved IN THE FUTURE.
Known bugs for multi-part polylines.
Points not handled correctly."""


# 'name': "undef"  ###
# 'topology': "undef"  ###
# 'geological_type': "undef"  ###
# 'feature': "undef"  ###
# 'scenario': "undef"
# 'properties_names': []
# 'properties_components': []
# 'x_section': ""
# 'vtk_obj': None


def shp2vtk(self=None, in_file_name=None, collection=None):
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
    # [Gabriele] This is horroble, we should rewrite to accept
    # different types of collection without repeating the code
    if collection == "Geology":
        if (gdf.geom_type[0] == "LineString") or (
            gdf.geom_type[0] == "MultiLineString"
        ):
            for row in range(gdf.shape[0]):
                # print("____ROW: ", row)
                # print("geometry type: ", gdf.geom_type[row])
                curr_obj_dict = deepcopy(GeologicalCollection.entity_dict)
                # if gdf.is_valid[row] and not gdf.is_empty[row]:
                # try:
                if "name" in column_names:
                    curr_obj_dict["name"] = gdf.loc[row, "name"]
                if "geological_type" in column_names:
                    curr_obj_dict["geological_type"] = gdf.loc[row, "geological_type"]
                if "geo_type" in column_names:
                    curr_obj_dict["geological_type"] = gdf.loc[row, "geo_type"]
                if "feature" in column_names:
                    curr_obj_dict["feature"] = gdf.loc[
                        row, "feature"
                    ]
                if "geo_feat" in column_names:
                    curr_obj_dict["feature"] = gdf.loc[row, "geo_feat"]
                if "scenario" in column_names:
                    curr_obj_dict["scenario"] = gdf.loc[row, "scenario"]
                curr_obj_dict["topology"] = "PolyLine"
                curr_obj_dict["vtk_obj"] = PolyLine()
                if gdf.geom_type[row] == "LineString":
                    outXYZ = np_array(
                        gdf.loc[row].geometry
                    )  # !!This does not work with shapely 2.0!!
                    # print("outXYZ:\n", outXYZ)
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
                    curr_obj_dict = deepcopy(
                        GeologicalCollection.entity_dict
                    )
                    if "dip" in gdf.columns:
                        vtk_obj = Attitude()
                    else:
                        vtk_obj = VertexSet()

                    if "name" in column_names:
                        curr_obj_dict["name"] = pd_series(gdf_index.loc[i, "name"])[0]
                    if "geological_type" in column_names:
                        curr_obj_dict["geological_type"] = pd_series(
                            gdf_index.loc[i, "geological_type"]
                        )[0]
                    if "geo_type" in column_names:
                        curr_obj_dict["geological_type"] = pd_series(
                            gdf_index.loc[i, "geo_type"]
                        )[0]
                    if "feature" in column_names:
                        curr_obj_dict["feature"] = i
                    if "geo_feat" in column_names:
                        curr_obj_dict["feature"] = i
                    if "scenario" in column_names:
                        curr_obj_dict["scenario"] = pd_series(
                            gdf_index.loc[i, "scenario"]
                        )[0]

                    curr_obj_dict["topology"] = "VertexSet"
                    curr_obj_dict["vtk_obj"] = vtk_obj

                    gdf_index["coords"] = gdf_index.geometry.apply(
                        lambda x: np_array(x)
                    )  # [Gabriele] add a coordinate column in the gdf_index dataframe
                    outXYZ = np_array([p for p in gdf_index.loc[i, "coords"]])

                    if outXYZ.ndim == 1:
                        outXYZ = outXYZ.reshape(-1, np_shape(outXYZ)[0])

                    if np_shape(outXYZ)[1] == 2:
                        outZ = np_zeros((np_shape(outXYZ)[0], 1))
                        # print("outZ:\n", outZ)
                        outXYZ = np_column_stack((outXYZ, outZ))

                    # print(np_shape(outXYZ))
                    curr_obj_dict["vtk_obj"].points = outXYZ

                    if "dir" in column_names:
                        direction = pd_series((gdf_index.loc[i, "dir"] + 90) % 360)
                        curr_obj_dict["vtk_obj"].set_point_data(
                            "dip_dir", direction.values
                        )
                    if "dip_dir" in column_names:
                        curr_obj_dict["vtk_obj"].set_point_data(
                            "dip_dir", pd_series(gdf_index.loc[i, "dip_dir"]).values
                        )
                    if "dip":
                        curr_obj_dict["vtk_obj"].set_point_data(
                            "dip", pd_series(gdf_index.loc[i, "dip"]).values
                        )

                    if "dip" in column_names and (
                        "dir" in column_names or "dip_dir" in column_names
                    ):
                        # print(type(curr_obj_dict["vtk_obj"].get_point_data('dip')))
                        normals = dip_directions2normals(
                            curr_obj_dict["vtk_obj"].get_point_data("dip"),
                            curr_obj_dict["vtk_obj"].get_point_data("dip_dir"),
                        )
                        curr_obj_dict["vtk_obj"].set_point_data("Normals", normals)

                    if curr_obj_dict["vtk_obj"].points_number > 1:
                        curr_obj_dict["vtk_obj"].auto_cells()
                        # print(curr_obj_dict["vtk_obj"].point_data_keys)
                        properties_names = curr_obj_dict["vtk_obj"].point_data_keys
                        properties_components = [
                            curr_obj_dict["vtk_obj"].get_point_data_shape(key)[1]
                            for key in properties_names
                        ]
                        curr_obj_dict["properties_names"] = properties_names
                        curr_obj_dict["properties_components"] = properties_components
                        self.geol_coll.add_entity_from_dict(curr_obj_dict)
                        del curr_obj_dict
                    elif curr_obj_dict["vtk_obj"].points_number > 0:
                        curr_obj_dict["vtk_obj"].auto_cells()
                        # print(curr_obj_dict["vtk_obj"].point_data_keys)
                        properties_names = curr_obj_dict["vtk_obj"].point_data_keys
                        properties_components = [
                            curr_obj_dict["vtk_obj"].get_point_data_shape(key)[1]
                            for key in properties_names
                        ]
                        curr_obj_dict["properties_names"] = properties_names
                        curr_obj_dict["properties_components"] = properties_components
                        self.geol_coll.add_entity_from_dict(curr_obj_dict)
                        del curr_obj_dict
            else:
                print(
                    "Incomplete data. At least the feature property must be present"
                )
        else:
            print("Only Point and Line geometries can be imported - aborting.")
            return  # except:  #     self.TextTerminal.appendPlainText("SHP file not recognized ERROR.")
    elif collection == "Fluid contacts":
        print(gdf.geom_type[0])
        if (gdf.geom_type[0] == "LineString") or (
            gdf.geom_type[0] == "MultiLineString"
        ):
            for row in range(gdf.shape[0]):
                # print("____ROW: ", row)
                # print("geometry type: ", gdf.geom_type[row])
                curr_obj_dict = deepcopy(FluidsCollection.entity_dict)
                # if gdf.is_valid[row] and not gdf.is_empty[row]:
                # try:
                if "name" in column_names:
                    curr_obj_dict["name"] = gdf.loc[row, "name"]
                if "fluid_type" in column_names:
                    curr_obj_dict["fluid_type"] = gdf.loc[row, "fluid_type"]
                if "feature" in column_names:
                    curr_obj_dict["feature"] = gdf.loc[row, "feature"]
                if "fluid_feat" in column_names:
                    curr_obj_dict["feature"] = gdf.loc[row, "fluid_feat"]
                if "scenario" in column_names:
                    curr_obj_dict["scenario"] = gdf.loc[row, "scenario"]
                curr_obj_dict["topology"] = "PolyLine"
                curr_obj_dict["vtk_obj"] = PolyLine()

                if gdf.geom_type[row] == "LineString":
                    outXYZ = np_array(gdf.loc[row].geometry)

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
                    output_uid = self.fluids_coll.add_entity_from_dict(curr_obj_dict)
                else:
                    print("Empty object")
                # else:
                # except:
                #     print("Invalid object")
                del curr_obj_dict
        elif gdf.geom_type[0] == "Point":
            if "fluid_feat" in column_names:
                gdf_index = gdf.set_index("fluid_feat")
                feat_list = set(gdf_index.index)

                for i in feat_list:
                    curr_obj_dict = deepcopy(FluidsCollection.entity_dict)
                    if "dip" in gdf.columns:
                        vtk_obj = Attitude()
                    else:
                        vtk_obj = VertexSet()

                    if "name" in column_names:
                        curr_obj_dict["name"] = pd_series(gdf_index.loc[i, "name"])[0]
                    if "fluid_type" in column_names:
                        curr_obj_dict["fluid_type"] = pd_series(
                            gdf_index.loc[i, "fluid_type"]
                        )[0]
                    if "fluid_type" in column_names:
                        curr_obj_dict["fluid_type"] = pd_series(
                            gdf_index.loc[i, "fluid_type"]
                        )[0]
                    if "feature" in column_names:
                        curr_obj_dict["feature"] = i
                    if "fluid_feat" in column_names:
                        curr_obj_dict["feature"] = i
                    if "scenario" in column_names:
                        curr_obj_dict["scenario"] = pd_series(
                            gdf_index.loc[i, "scenario"]
                        )[0]

                    curr_obj_dict["topology"] = "VertexSet"
                    curr_obj_dict["vtk_obj"] = vtk_obj

                    gdf_index["coords"] = gdf_index.geometry.apply(
                        lambda x: np_array(x)
                    )  # [Gabriele] add a coordinate column in the gdf_index dataframe
                    outXYZ = np_array([p for p in gdf_index.loc[i, "coords"]])

                    if outXYZ.ndim == 1:
                        outXYZ = outXYZ.reshape(-1, np_shape(outXYZ)[0])

                    if np_shape(outXYZ)[1] == 2:
                        outZ = np_zeros((np_shape(outXYZ)[0], 1))
                        # print("outZ:\n", outZ)
                        outXYZ = np_column_stack((outXYZ, outZ))

                    # print(np_shape(outXYZ))
                    curr_obj_dict["vtk_obj"].points = outXYZ

                    if curr_obj_dict["vtk_obj"].points_number > 1:
                        curr_obj_dict["vtk_obj"].auto_cells()
                        # print(curr_obj_dict["vtk_obj"].point_data_keys)
                        properties_names = curr_obj_dict["vtk_obj"].point_data_keys
                        properties_components = [
                            curr_obj_dict["vtk_obj"].get_point_data_shape(key)[1]
                            for key in properties_names
                        ]
                        curr_obj_dict["properties_names"] = properties_names
                        curr_obj_dict["properties_components"] = properties_components
                        self.fluids_coll.add_entity_from_dict(curr_obj_dict)
                        del curr_obj_dict
                    elif curr_obj_dict["vtk_obj"].points_number > 0:
                        curr_obj_dict["vtk_obj"].auto_cells()
                        # print(curr_obj_dict["vtk_obj"].point_data_keys)
                        properties_names = curr_obj_dict["vtk_obj"].point_data_keys
                        properties_components = [
                            curr_obj_dict["vtk_obj"].get_point_data_shape(key)[1]
                            for key in properties_names
                        ]
                        curr_obj_dict["properties_names"] = properties_names
                        curr_obj_dict["properties_components"] = properties_components
                        self.fluids_coll.add_entity_from_dict(curr_obj_dict)
                        del curr_obj_dict
            else:
                print(
                    "Incomplete data. At least the feature property must be present"
                )
        else:
            print("Only Point and Line geometries can be imported - aborting.")
            return  # except:  #     self.TextTerminal.appendPlainText("SHP file not recognized ERROR.")
    elif collection == "Background data":
        if (gdf.geom_type[0] == "LineString") or (
            gdf.geom_type[0] == "MultiLineString"
        ):
            for row in range(gdf.shape[0]):
                # print("____ROW: ", row)
                # print("geometry type: ", gdf.geom_type[row])
                curr_obj_dict = deepcopy(BackgroundCollection.entity_dict)
                # if gdf.is_valid[row] and not gdf.is_empty[row]:
                # try:
                if "name" in column_names:
                    curr_obj_dict["name"] = gdf.loc[row, "name"]
                if "bkg_type" in column_names:
                    curr_obj_dict["background_type"] = gdf.loc[row, "bkg_type"]
                if "feature" in column_names:
                    curr_obj_dict["feature"] = gdf.loc[
                        row, "feature"
                    ]
                if "bkg_feat" in column_names:
                    curr_obj_dict["feature"] = gdf.loc[row, "bkg_feat"]

                curr_obj_dict["topology"] = "PolyLine"
                curr_obj_dict["vtk_obj"] = PolyLine()
                if gdf.geom_type[row] == "LineString":
                    outXYZ = np_array(gdf.loc[row].geometry)
                    # print("outXYZ:\n", outXYZ)
                    if np_shape(outXYZ)[1] == 2:
                        outZ = np_zeros((np_shape(outXYZ)[0], 1))
                        # print("outZ:\n", outZ)
                        outXYZ = np_column_stack((outXYZ, outZ))
                    # print("outXYZ:\n", outXYZ)
                    curr_obj_dict["vtk_obj"].points = outXYZ
                    curr_obj_dict["vtk_obj"].auto_cells()
                    curr_obj_dict["vtk_obj"].set_field_data(
                        name="name", data=gdf["label"].values
                    )

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

                    if "label" in column_names:
                        out_vtk = PolyLine()
                        out_vtk.ShallowCopy(vtkappend.GetOutput())
                        out_vtk.set_field_data(name="name", data=gdf["label"].values)
                        curr_obj_dict["vtk_obj"].ShallowCopy(out_vtk)
                    else:
                        curr_obj_dict["vtk_obj"].ShallowCopy(vtkappend.GetOutput())
                """Create entity from the dictionary and run left_right."""

                if curr_obj_dict["vtk_obj"].points_number > 0:
                    self.backgrounds_coll.add_entity_from_dict(curr_obj_dict)
                else:
                    print("Empty object")
                # else:
                # except:
                #     print("Invalid object")
                del curr_obj_dict
        elif gdf.geom_type[0] == "Point":
            if "bkg_feat" in column_names:
                gdf_index = gdf.set_index("bkg_feat")
                feat_list = set(gdf_index.index)

                for i in feat_list:
                    curr_obj_dict = deepcopy(
                        BackgroundCollection.entity_dict
                    )

                    vtk_obj = VertexSet()

                    if "name" in column_names:
                        curr_obj_dict["name"] = pd_series(gdf_index.loc[i, "name"])[0]
                    if "bkg_type" in column_names:
                        curr_obj_dict["background_type"] = pd_series(
                            gdf_index.loc[i, "bkg_type"]
                        )[0]
                    if "feature" in column_names:
                        curr_obj_dict["feature"] = i
                    if "bkg_feat" in column_names:
                        curr_obj_dict["feature"] = i

                    curr_obj_dict["topology"] = "VertexSet"
                    curr_obj_dict["vtk_obj"] = vtk_obj

                    gdf_index["coords"] = gdf_index.geometry.apply(
                        lambda x: np_array(x)
                    )  # [Gabriele] add a coordinate column in the gdf_index dataframe
                    outXYZ = np_array([p for p in gdf_index.loc[i, "coords"]])

                    if outXYZ.ndim == 1:
                        outXYZ = outXYZ.reshape(-1, np_shape(outXYZ)[0])

                    if np_shape(outXYZ)[1] == 2:
                        outZ = np_zeros((np_shape(outXYZ)[0], 1))
                        # print("outZ:\n", outZ)
                        outXYZ = np_column_stack((outXYZ, outZ))

                    curr_obj_dict["vtk_obj"].points = outXYZ
                    curr_obj_dict["vtk_obj"].auto_cells()

                    if "label" in column_names:
                        curr_obj_dict["vtk_obj"].set_field_data(
                            name="name", data=np_asarray(gdf_index.loc[i, "label"])
                        )
                    else:
                        curr_obj_dict["vtk_obj"].set_field_data(name="name")

                    if curr_obj_dict["vtk_obj"].points_number > 1:
                        # curr_obj_dict["vtk_obj"].auto_cells()
                        # print(curr_obj_dict["vtk_obj"].point_data_keys)
                        properties_names = curr_obj_dict["vtk_obj"].point_data_keys
                        properties_components = [
                            curr_obj_dict["vtk_obj"].get_point_data_shape(key)[1]
                            for key in properties_names
                        ]
                        curr_obj_dict["properties_names"] = properties_names
                        curr_obj_dict["properties_components"] = properties_components

                        self.backgrounds_coll.add_entity_from_dict(curr_obj_dict)
                        del curr_obj_dict
                    elif curr_obj_dict["vtk_obj"].points_number > 0:
                        # curr_obj_dict["vtk_obj"].auto_cells()
                        # print(curr_obj_dict["vtk_obj"].point_data_keys)
                        properties_names = curr_obj_dict["vtk_obj"].point_data_keys
                        properties_components = [
                            curr_obj_dict["vtk_obj"].get_point_data_shape(key)[1]
                            for key in properties_names
                        ]
                        curr_obj_dict["properties_names"] = properties_names
                        curr_obj_dict["properties_components"] = properties_components
                        self.backgrounds_coll.add_entity_from_dict(curr_obj_dict)
                        del curr_obj_dict
            else:
                print(
                    "Incomplete data. At least the bkg_feature property must be present"
                )
        else:
            print("Only Point and Line geometries can be imported - aborting.")
            return  # except:  #     self.TextTerminal.appendPlainText("SHP file not recognized ERROR.")
