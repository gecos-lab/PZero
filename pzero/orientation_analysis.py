"""orientation_analysis.py
PZero© Andrea Bistacchi"""

import numpy as np
import pandas as pd
from .helper_dialogs import multiple_input_dialog, input_one_value_dialog, input_text_dialog, input_combo_dialog
from .entities_factory import TriSurf, XsPolyLine, PolyLine, VertexSet, Voxet, XsTriSurf, XsVertexSet

"""IN THE FUTURE add functions for ortientation analysis."""


def strikes2dip_directions(strikes=None):
    """Convert Strike to Dip-Direction according to right-hand rule,
    all in degrees. Accepts single values, lists or Numpy arrays and
    returns the same types."""
    if isinstance(strikes, np.ndarray):
        strikes_array = strikes
        directions_array = (strikes_array + 90) * np.less_equal(strikes_array, 270) + (strikes_array - 270) * np.greater(strikes_array, 270)
        directions = directions_array
        return directions
    elif isinstance(strikes, list):
        strikes_array = np.asarray(strikes)
        directions_array = (strikes_array + 90) * np.less_equal(strikes_array, 270) + (strikes_array - 270) * np.greater(strikes_array, 270)
        directions = list(directions_array)
        return directions
    elif isinstance(strikes, (float, int)):
        if strikes <= 270:
            directions = strikes + 90
        else:
            directions = strikes - 270
        return directions
    else:
        print("Strike type not recognized")


def plunge_trends2lineations(plunges=None, trends=None):
    """Convert Plunge/Trend measurements in degrees (single or list)
    to lineation unit vectors pointing downwards if Plunge > 0.
    Accepts single values, lists or Numpy arrays and
    returns Numpy arrays."""
    if isinstance(plunges, (float, int, list,np.number)) and isinstance(trends, (float, int, list,np.number)):
        plunges_array = np.asarray(plunges)
        trends_array = np.asarray(trends)
    elif isinstance(plunges, np.ndarray) and isinstance(trends, np.ndarray):
        plunges_array = plunges
        trends_array = trends
    else:
        print("Plunge/Trend type not recognized.")
    plunges_array = np.deg2rad(plunges_array)
    trends_array = np.deg2rad(trends_array)
    lineations = np.asarray([np.sin(trends_array) * np.cos(plunges_array), np.cos(trends_array) * np.cos(plunges_array), -np.sin(plunges_array)])
    return lineations.T


def dip_directions2normals(dips=None, directions=None):
    """Convert Dip/Direction measurements in degrees (single or list)
    to normal unit vectors pointing downwards if Dip > 0.
    Accepts single values, lists or Numpy arrays and
    returns Numpy arrays. We use np.squeeze to avoid having multi-dimensional arrays"""
    if isinstance(dips, (float, int, list)) and isinstance(directions, (float, int, list)):
        dips_array = np.squeeze(np.asarray(dips))
        directions_array = np.squeeze(np.asarray(directions))
    elif isinstance(dips, np.ndarray) and isinstance(directions, np.ndarray):
        dips_array = np.squeeze(dips)
        directions_array = np.squeeze(directions)
    else:
        print("Dip/Direction type not recognized.")
    dips_array = np.squeeze(dips_array)
    directions_array = np.squeeze(directions_array)
    plunges_array = 90 - dips_array
    trends_array = (directions_array + 180) * np.less_equal(directions_array, 180) + (directions_array - 180) * np.greater(directions_array, 180)
    normals = plunge_trends2lineations(plunges=plunges_array, trends=trends_array)
    return normals


def vset_set_normals(VertexSet=None, dip_name=None, dir_name=None):
    dips_array = VertexSet.get_point_data(dip_name)
    dirs_array = VertexSet.get_point_data(dir_name)
    normals = dip_directions2normals(dips=dips_array, directions=dirs_array)
    VertexSet.init_point_data(data_key='Normals', dimension=3)
    VertexSet.set_point_data(data_key='Normals', attribute_matrix=normals)


def set_normals(self):
    """General function to set normals on different entities.
    It branches to other functions depending on the selected entity
    and aborts if the input entities are not homogeneous."""
    """Check if some vtkPolyData is selected"""
    if self.selected_uids:
        if self.shown_table == "tabGeology":
            if isinstance(self.geol_coll.get_uid_vtk_obj(self.selected_uids[0]), (VertexSet, XsVertexSet)):
                """Case for VertexSet and XsVertexSet.
                First make sure all entities are VertexSet or XsVertexSet."""
                for uid in self.selected_uids:
                    if not isinstance(self.geol_coll.get_uid_vtk_obj(uid), (VertexSet, XsVertexSet)):
                        print("All entities must be of the same type.")
                        return
                """Choose Dip/Direction property names. If list is empty return."""
                property_name_list = self.geol_coll.get_uid_properties_names(uid=self.selected_uids[0])
                if len(self.selected_uids) > 1:
                    for uid in self.selected_uids[1:]:
                        property_name_list = list(set(property_name_list) & set(self.geol_coll.get_uid_properties_names(uid=uid)))
                if property_name_list == []:
                    return
                input_dict = {'dip_name': ['Dip property: ', property_name_list], 'dir_name': ['Direction property: ', property_name_list]}
                updt_dict = multiple_input_dialog(title='Select Dip/Direction property names', input_dict=input_dict)
                if updt_dict is None:
                    return
                """Now calculate Normals on each VTK object and append Normals to properties_names list."""
                for uid in self.selected_uids:
                    self.geol_coll.append_uid_property(uid=uid, property_name="Normals", property_components=3)
                    vset_set_normals(VertexSet=self.geol_coll.get_uid_vtk_obj(uid), dip_name=updt_dict['dip_name'], dir_name=updt_dict['dir_name'])
                    self.prop_legend.update_widget(self)
                    print("Normals set on TriSurf ", uid)
                print("All Normals set.")
            elif isinstance(self.geol_coll.get_uid_vtk_obj(self.selected_uids[0]), TriSurf):
                """Case for TriSurf.
                First make sure all entities are TriSurf."""
                print("Normals on TriSurf.")
                for uid in self.selected_uids:
                    if not isinstance(self.geol_coll.get_uid_vtk_obj(uid), TriSurf):
                        print("All entities must be of the same type.")
                        return
                for uid in self.selected_uids:
                    self.geol_coll.append_uid_property(uid=uid, property_name="Normals", property_components=3)
                    self.geol_coll.get_uid_vtk_obj(uid).vtk_set_normals()
                    self.prop_legend.update_widget(self)
                    print("Normals set on TriSurf ", uid)
                print("All Normals set.")
            else:
                print("Only VertexSet, XsVertexSet and TriSurf entities can be processed.")

        elif self.shown_table == "tabDOMs":
            print('Calculating normals for Point Cloud')
            for uid in self.selected_uids:
                self.dom_coll.append_uid_property(uid=uid, property_name="Normals", property_components=3)
                self.dom_coll.get_uid_vtk_obj(uid).vtk_set_normals()
                self.prop_legend.update_widget(self)
                print(self.prop_legend_df)
            print('Done')
        else:
            print("Normals can be calculated only on geological entities and Point Clouds (at the moment).")
    else:
        print("No input data selected.")
