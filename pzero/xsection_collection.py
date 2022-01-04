"""xsection_collection.py
PZero© Andrea Bistacchi"""

import vtk
# import vtk.numpy_interface.dataset_adapter as dsa
# import vtk.numpy_interface.algorithms as algs
from copy import deepcopy
import uuid
import numpy as np
import pandas as pd
from qtpy.QtCore import QAbstractTableModel, Qt, Signal, QObject, QVariant, QAbstractItemModel
# from PyQt5.QtGui import QStandardItem, QImage
from .entities_factory import PolyData, Plane, VertexSet, PolyLine, TriSurf, TetraSolid, XsVertexSet, XsPolyLine, DEM, MapImage, Voxet
from .helper_dialogs import multiple_input_dialog, general_input_dialog
from .windows_factory import NavigationToolbar
from qtpy.QtWidgets import QAction

"""Options to print Pandas dataframes in console"""
pd_desired_width = 800
pd_max_columns = 20
pd_show_precision = 4
pd_max_colwidth = 80
pd.set_option('display.width', pd_desired_width)
np.set_printoptions(linewidth=pd_desired_width)
pd.set_option('display.max_columns', pd_max_columns)
pd.set_option('display.precision', pd_show_precision)
pd.set_option('display.max_colwidth', pd_max_colwidth)

""""Methods used to create cross sections."""


def section_from_azimuth(self):
    """Create a new cross section from origin and azimuth"""
    """Freeze QT interface"""
    for action in self.findChildren(QAction):
        if isinstance(action.parentWidget(), NavigationToolbar) is False:
            action.setDisabled(True)
    self.text_msg.set_text("Draw a vector with mouse to represent the new XSection")
    section_dict = deepcopy(self.parent.xsect_coll.section_dict)
    """multiple_input_dialog widget is built to check the default value associated to each feature in 
    section_dict_in: this value defines the type (str-int-float) of the output that is passed to section_dict_updt.
    It is therefore necessary in section_dict_in to implement the right type for each variable."""
    while True:
        self.vector_by_mouse(verbose=True)
        section_dict_in = {'warning': ['XSection from azimuth', 'Build new XSection from a user-drawn line.\nOnce drawn, values can be modified from keyboard\nor by drawing another vector.', 'QLabel'],
                                   'name': ['Insert Xsection name', 'new_section', 'QLineEdit'],
                                   'base_x': ['Insert origin X coord', self.vbm_U0, 'QLineEdit'],
                                   'base_y': ['Insert origin Y coord', self.vbm_V0, 'QLineEdit'],
                                   'azimuth': ['Insert azimuth', self.vector_by_mouse_azimuth, 'QLineEdit'],
                                   'length': ['Insert length', self.vector_by_mouse_length, 'QLineEdit'],
                                   'top': ['Insert top', 0.0, 'QLineEdit'],
                                   'bottom': ['Insert bottom', 0.0, 'QLineEdit']}
        section_dict_updt = general_input_dialog(title='XSection from Azimuth', input_dict=section_dict_in)
        if section_dict_updt is not None:
            break
    while True:
        if section_dict_updt['name'] in self.parent.xsect_coll.get_names():
            section_dict_updt['name'] = section_dict_updt['name'] + '_0'
        else:
            break
    for key in section_dict_updt:
        section_dict[key] = section_dict_updt[key]
    section_dict['base_z'] = 0.0
    section_dict['end_z'] = 0.0
    section_dict['end_x'] = section_dict['base_x'] + section_dict['length'] * np.sin(section_dict['azimuth'] * np.pi / 180)
    section_dict['end_y'] = section_dict['base_y'] + section_dict['length'] * np.cos(section_dict['azimuth'] * np.pi / 180)
    section_dict['normal_x'] = np.sin((section_dict['azimuth'] + 90) * np.pi / 180)
    section_dict['normal_y'] = np.cos((section_dict['azimuth'] + 90) * np.pi / 180)
    section_dict['normal_z'] = 0.0
    uid = self.parent.xsect_coll.add_entity_from_dict(entity_dict=section_dict)
    """Once the original XSection has been drawn, ask if a set of XSections is needed."""
    # section_dict_in_set = {'activate': ['Multiple XSections', 'To draw a set of XSections fill in the fields. Else, exit the dialog.', 'QLabel'],
    #                        'spacing': ['Spacing', 1000.0, 'QLineEdit'],
    #                        'num_xs': ['Number of XSections', 5, 'QLineEdit']}
    section_dict_in_set = {'activate': ['Multiple XSections', 'Draw a set of parallel XSections', 'QCheckBox'],
                           'spacing': ['Spacing', 1000.0, 'QLineEdit'],
                           'num_xs': ['Number of XSections', 5, 'QLineEdit']}
    section_dict_updt_set = general_input_dialog(title='XSection from Azimuth', input_dict=section_dict_in_set)
    if section_dict_updt_set is None:
        """Un-Freeze QT interface"""
        for action in self.findChildren(QAction):
            action.setEnabled(True)
        return
    if section_dict_updt_set['activate'] == "uncheck":
        """Un-Freeze QT interface"""
        for action in self.findChildren(QAction):
            action.setEnabled(True)
        return
    name_original_xs = section_dict['name']
    for xsect in range(section_dict_updt_set['num_xs'] - 1):
        section_dict['name'] = name_original_xs + '_' + str(xsect)
        while True:
            if section_dict['name'] in self.parent.xsect_coll.get_names():
                section_dict['name'] = section_dict['name'] + '_0'
            else:
                break
        section_dict['base_x'] = section_dict['base_x'] - (section_dict_updt_set['spacing'] * np.cos(section_dict_updt['azimuth'] * np.pi / 180))
        section_dict['base_y'] = section_dict['base_y'] + (section_dict_updt_set['spacing'] * np.sin(section_dict_updt['azimuth'] * np.pi / 180))
        section_dict['end_x'] = section_dict['base_x'] + section_dict['length'] * np.sin(section_dict['azimuth'] * np.pi / 180)
        section_dict['end_y'] = section_dict['base_y'] + section_dict['length'] * np.cos(section_dict['azimuth'] * np.pi / 180)
        section_dict['uid'] = None
        uid = self.parent.xsect_coll.add_entity_from_dict(entity_dict=section_dict)
    """Un-Freeze QT interface"""
    for action in self.findChildren(QAction):
        action.setEnabled(True)

def section_from_points(self):
    """Create a new cross section from origin and azimuth"""
    section_dict = deepcopy(self.parent.xsect_coll.section_dict)
    """multiple_input_dialog widget is built to check the default value associated to each feature in 
    section_dict_in: this value defines the type (str-int-float) of the output that is passed to section_dict_updt.
    It is therefore necessary in section_dict_in to implement the right type for each variable."""
    """Freeze QT interface"""
    for action in self.findChildren(QAction):
        if isinstance(action.parentWidget(), NavigationToolbar) is False:
            action.setDisabled(True)
    self.text_msg.set_text("Draw a vector with mouse to represent the new XSection")
    while True:
        self.vector_by_mouse(verbose=True)
        section_dict_in = {'warning': ['XSection from points', 'Build new XSection from a user-drawn line.\nOnce drawn, values can be modified from keyboard\nor by drawing another vector.', 'QLabel'],
                                   'name': ['Insert Xsection name', 'new_section', 'QLineEdit'],
                                   'base_x': ['Insert origin X coord', self.vbm_U0, 'QLineEdit'],
                                   'base_y': ['Insert origin Y coord', self.vbm_V0, 'QLineEdit'],
                                   'end_x': ['Insert end-point X coord', self.vbm_Uf, 'QLineEdit'],
                                   'end_y': ['Insert end-point Y coord', self.vbm_Vf, 'QLineEdit'],
                                   'top': ['Insert top', 0.0, 'QLineEdit'],
                                   'bottom': ['Insert bottom', 0.0, 'QLineEdit']}
        section_dict_updt = general_input_dialog(title='New XSection from points', input_dict=section_dict_in)
        if section_dict_updt is not None:
            break
    while True:
        if section_dict_updt['name'] in self.parent.xsect_coll.get_names():
            section_dict_updt['name'] = section_dict_updt['name'] + '_0'
        else:
            break
    for key in section_dict_updt:
        section_dict[key] = section_dict_updt[key]
    section_dict['base_z'] = 0.0
    section_dict['end_z'] = 0.0
    section_dict['azimuth'] = np.arctan2((section_dict['end_x'] - section_dict['base_x']), (section_dict['end_y'] - section_dict['base_y'])) * 180 / np.pi
    if section_dict['azimuth'] < 0:
        section_dict['azimuth'] += 360
    section_dict['length'] = np.sqrt((section_dict['end_x'] - section_dict['base_x']) ** 2 + (section_dict['end_y'] - section_dict['base_y']) ** 2)
    section_dict['normal_x'] = np.sin((section_dict['azimuth'] + 90) * np.pi / 180)
    section_dict['normal_y'] = np.cos((section_dict['azimuth'] + 90) * np.pi / 180)
    section_dict['normal_z'] = 0.0
    uid = self.parent.xsect_coll.add_entity_from_dict(entity_dict=section_dict)
    """Once the original XSection has been drawn, ask if a set of XSections is needed."""
    section_dict_in_set = {'activate': ['Multiple XSections', 'Draw a set of parallel XSections', 'QCheckBox'],
                           'spacing': ['Spacing', 1000.0, 'QLineEdit'],
                           'num_xs': ['Number of XSections', 5, 'QLineEdit']}
    section_dict_updt_set = general_input_dialog(title='XSection from Azimuth', input_dict=section_dict_in_set)
    if section_dict_updt_set is None:
        """Un-Freeze QT interface"""
        for action in self.findChildren(QAction):
            action.setEnabled(True)
        return
    if section_dict_updt_set['activate'] == "uncheck":
        """Un-Freeze QT interface"""
        for action in self.findChildren(QAction):
            action.setEnabled(True)
        return
    name_original_xs = section_dict['name']
    for xsect in range(section_dict_updt_set['num_xs'] - 1):
        section_dict['name'] = name_original_xs + '_' + str(xsect)
        while True:
            if section_dict['name'] in self.parent.xsect_coll.get_names():
                section_dict['name'] = section_dict['name'] + '_0'
            else:
                break
        section_dict['base_x'] = section_dict['base_x'] - (section_dict_updt_set['spacing'] * np.cos(section_dict['azimuth'] * np.pi / 180))
        section_dict['base_y'] = section_dict['base_y'] + (section_dict_updt_set['spacing'] * np.sin(section_dict['azimuth'] * np.pi / 180))
        section_dict['end_x'] = section_dict['end_x'] - (section_dict_updt_set['spacing'] * np.cos(section_dict['azimuth'] * np.pi / 180))
        section_dict['end_y'] = section_dict['end_y'] + (section_dict_updt_set['spacing'] * np.sin(section_dict['azimuth'] * np.pi / 180))
        section_dict['normal_x'] = np.sin((section_dict['azimuth'] + 90) * np.pi / 180)
        section_dict['normal_y'] = np.cos((section_dict['azimuth'] + 90) * np.pi / 180)
        section_dict['uid'] = None
        uid = self.parent.xsect_coll.add_entity_from_dict(entity_dict=section_dict)
    """Un-Freeze QT interface"""
    for action in self.findChildren(QAction):
        action.setEnabled(True)


class XSectionCollection(QAbstractTableModel):
    """
    Initialize XSectionCollection table.
    Column headers are taken from XSectionCollection.section_dict.keys()
    parent is supposed to be the project_window
    """

    """IN THE FUTURE we can use a trace PolyLine, with just a segment connecting base to end points?"""

    """section_dict is a dictionary of attributes used to define Xsections.
    Always use deepcopy(GeologicalCollection.geological_entity_dict) to copy
    this dictioary without altering the original."""
    section_dict = {'uid': '', 'name': 'undef', 'base_x': 0.0, 'base_y': 0.0, 'base_z': 0.0, 'end_x': 0.0, 'end_y': 0.0, 'end_z': 0.0, 'normal_x': 0.0, 'normal_y': 0.0, 'normal_z': 0.0, 'azimuth': 0.0, 'length': 0.0, 'top': 0.0, 'bottom': 0.0, 'vtk_plane': None,  # None to avoid errors with deepcopy
                    'vtk_frame': None}  # None to avoid errors with deepcopy

    section_type_dict = {'uid': str, 'name': str, 'base_x': float, 'base_y': float, 'base_z': float, 'end_x': float, 'end_y': float, 'end_z': float, 'normal_x': float, 'normal_y': float, 'normal_z': float, 'azimuth': float, 'length': float, 'top': float, 'bottom': float, 'vtk_plane': object, 'vtk_frame': object}

    """The edit dialog will be able to edit attributes of multiple entities (and selecting "None" will not change them)______"""

    def __init__(self, parent=None, *args, **kwargs):
        super(XSectionCollection, self).__init__(*args, **kwargs)
        """Import reference to parent, otherwise it is difficult to reference them in SetData() that has a standard list of inputs."""
        self.parent = parent

        """Initialize Pandas dataframe."""
        self.df = pd.DataFrame(columns=list(self.section_dict.keys()))

        """Here we use .columns.get_indexer to get indexes of the columns that we would like to be editable in the QTableView"""
        """IN THE FUTURE think about editing top, bottom (just modify frame). To modify end-point and base-point we need to
        ensure that they lie in the cross section, then just modify frame since W coords of objects are always calculated on-the-fly."""
        self.editable_columns = self.df.columns.get_indexer(["name"])

    """Custom methods used to add or remove entities, query the dataframe, etc."""

    def add_entity_from_dict(self, entity_dict=None):
        """Add entity to collection from dictionary."""
        """Create a new uid if it is not included in the dictionary."""
        if not entity_dict['uid']:
            entity_dict['uid'] = str(uuid.uuid4())
        """Append new row to dataframe. Note that the 'append()' method for Pandas dataframes DOES NOT
        work in place, hence a NEW dataframe is created every time and then substituted to the old one."""
        self.df = self.df.append(entity_dict, ignore_index=True)
        self.set_geometry(uid=entity_dict['uid'])
        """Reset data model"""
        self.modelReset.emit()
        self.parent.xsect_added_signal.emit([entity_dict['uid']])  # a list of uids is emitted, even if the entity is just one
        return entity_dict['uid']

    def remove_entity(self, uid=None):
        """Remove entity from collection."""
        """Remove row from dataframe and reset data model."""
        """NOTE THAT AT THE MOMENT REMOVING A SECTION DOES NOT REMOVE THE ASSOCIATED OBJECTS."""
        if not uid in self.get_uids():
            return
        self.df.drop(self.df[self.df['uid'] == uid].index, inplace=True)
        self.modelReset.emit()  # is this really necessary?
        self.parent.xsect_removed_signal.emit([uid])  # a list of uids is emitted, even if the entity is just one
        return uid

    def get_number_of_entities(self):
        """Get number of entities stored in Pandas dataframe."""
        return self.df.shape[0]

    def get_uids(self):
        """Get list of uids."""
        return self.df['uid'].to_list()

    def get_names(self):
        """Get list of names."""
        return self.df['name'].to_list()

    def get_legend(self):
        legend_dict = self.parent.others_legend_df.loc[self.parent.others_legend_df['other_type'] == 'XSection'].to_dict('records')
        return legend_dict[0]

    def get_uid_name(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df['uid'] == uid, 'name'].values[0]

    def set_uid_name(self, uid=None, name=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df['uid'] == uid, 'name'] = name

    def get_uid_base_x(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df['uid'] == uid, 'base_x'].values[0]

    def set_uid_base_x(self, uid=None, base_x=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df['uid'] == uid, 'base_x'] = base_x

    def get_uid_base_y(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df['uid'] == uid, 'base_y'].values[0]

    def set_uid_base_y(self, uid=None, base_y=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df['uid'] == uid, 'base_y'] = base_y

    def get_uid_base_z(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df['uid'] == uid, 'base_z'].values[0]

    def set_uid_base_z(self, uid=None, base_z=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df['uid'] == uid, 'base_z'] = base_z

    def get_uid_end_x(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df['uid'] == uid, 'end_x'].values[0]

    def set_uid_end_x(self, uid=None, end_x=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df['uid'] == uid, 'end_x'] = end_x

    def get_uid_end_y(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df['uid'] == uid, 'end_y'].values[0]

    def set_uid_end_y(self, uid=None, end_y=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df['uid'] == uid, 'end_y'] = end_y

    def get_uid_end_z(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df['uid'] == uid, 'end_z'].values[0]

    def set_uid_end_z(self, uid=None, end_z=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df['uid'] == uid, 'end_z'] = end_z

    def get_uid_normal_x(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df['uid'] == uid, 'normal_x'].values[0]

    def set_uid_normal_x(self, uid=None, normal_x=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df['uid'] == uid, 'normal_x'] = normal_x

    def get_uid_normal_y(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df['uid'] == uid, 'normal_y'].values[0]

    def set_uid_normal_y(self, uid=None, normal_y=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df['uid'] == uid, 'normal_y'] = normal_y

    def get_uid_normal_z(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df['uid'] == uid, 'normal_z'].values[0]

    def set_uid_normal_z(self, uid=None, normal_z=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df['uid'] == uid, 'normal_z'] = normal_z

    def get_uid_azimuth(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df['uid'] == uid, 'azimuth'].values[0]

    def set_uid_azimuth(self, uid=None, azimuth=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df['uid'] == uid, 'azimuth'] = azimuth

    def get_uid_length(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df['uid'] == uid, 'length'].values[0]

    def set_uid_length(self, uid=None, length=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df['uid'] == uid, 'length'] = length

    def get_uid_top(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df['uid'] == uid, 'top'].values[0]

    def set_uid_top(self, uid=None, top=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df['uid'] == uid, 'top'] = top

    def get_uid_bottom(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df['uid'] == uid, 'bottom'].values[0]

    def set_uid_bottom(self, uid=None, bottom=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df['uid'] == uid, 'bottom'] = bottom

    def get_uid_vtk_plane(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df['uid'] == uid, 'vtk_plane'].values[0]

    def set_uid_vtk_plane(self, uid=None, vtk_plane=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df['uid'] == uid, 'vtk_plane'] = vtk_plane

    def get_uid_vtk_frame(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self.df.loc[self.df['uid'] == uid, 'vtk_frame'].values[0]

    def set_uid_vtk_frame(self, uid=None, vtk_frame=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self.df.loc[self.df['uid'] == uid, 'vtk_frame'] = vtk_frame

    """Methods used to set parameters and the geometry of a single cross section."""

    def set_parameters_in_table(self, uid=None, name=None, base_point=None, end_point=None, normal=None, azimuth=None, length=None, top=None, bottom=None):
        """Write parameters in Xsections Pandas dataframe"""
        self.df.loc[self.df['uid'] == uid, 'name'] = name
        self.df.loc[self.df['uid'] == uid, 'base_x'] = base_point[0]
        self.df.loc[self.df['uid'] == uid, 'base_y'] = base_point[1]
        self.df.loc[self.df['uid'] == uid, 'base_z'] = base_point[2]
        self.df.loc[self.df['uid'] == uid, 'end_x'] = end_point[0]
        self.df.loc[self.df['uid'] == uid, 'end_y'] = end_point[1]
        self.df.loc[self.df['uid'] == uid, 'end_z'] = end_point[2]
        self.df.loc[self.df['uid'] == uid, 'normal_x'] = normal[0]
        self.df.loc[self.df['uid'] == uid, 'normal_y'] = normal[1]
        self.df.loc[self.df['uid'] == uid, 'normal_z'] = normal[2]
        self.df.loc[self.df['uid'] == uid, 'azimuth'] = azimuth
        self.df.loc[self.df['uid'] == uid, 'length'] = length
        self.df.loc[self.df['uid'] == uid, 'top'] = top
        self.df.loc[self.df['uid'] == uid, 'bottom'] = bottom

    def set_from_table(self, uid=None):
        """Get parameters from x_section table and set them on x_section"""
        self.set_geometry(uid=uid)

    def get_XY_from_W(self, section_uid=None, W=None):
        """Gets X, Y coordinates from W coordinate (distance along the Xsection horizontal axis)"""
        azimuth = self.df.loc[self.df['uid'] == section_uid, 'azimuth'].values[0]
        base_x = self.df.loc[self.df['uid'] == section_uid, 'base_x'].values[0]
        base_y = self.df.loc[self.df['uid'] == section_uid, 'base_y'].values[0]
        X = W * np.sin(azimuth * np.pi / 180) + base_x
        Y = W * np.cos(azimuth * np.pi / 180) + base_y
        return X, Y

    def get_deltaXY_from_deltaW(self, section_uid=None, deltaW=None):
        """Gets X, Y coordinates from W coordinate (distance along the Xsection horizontal axis)"""
        azimuth = self.df.loc[self.df['uid'] == section_uid, 'azimuth'].values[0]
        deltaX = deltaW * np.sin(azimuth * np.pi / 180)
        deltaY = deltaW * np.cos(azimuth * np.pi / 180)
        return deltaX, deltaY

    def set_geometry(self, uid=None):
        """"Given all parameters, sets the vtkPlane origin and normal properties, and builds the frame used for visualization"""
        base_point = [self.df.loc[self.df['uid'] == uid, 'base_x'], self.df.loc[self.df['uid'] == uid, 'base_y'], self.df.loc[self.df['uid'] == uid, 'base_z']]
        end_point = [self.df.loc[self.df['uid'] == uid, 'end_x'], self.df.loc[self.df['uid'] == uid, 'end_y'], self.df.loc[self.df['uid'] == uid, 'end_z']]
        normal = [self.df.loc[self.df['uid'] == uid, 'normal_x'], self.df.loc[self.df['uid'] == uid, 'normal_y'], self.df.loc[self.df['uid'] == uid, 'normal_z']]
        top = self.df.loc[self.df['uid'] == uid, 'top']
        bottom = self.df.loc[self.df['uid'] == uid, 'bottom']
        vtk_plane = Plane()
        vtk_frame = XsPolyLine(x_section_uid=uid, parent=self.parent)
        vtk_plane.SetOrigin(base_point)
        vtk_plane.SetNormal(normal)
        frame_points = vtk.vtkPoints()
        frame_cells = vtk.vtkCellArray()
        frame_points.InsertPoint(0, base_point[0], base_point[1], bottom)
        frame_points.InsertPoint(1, base_point[0], base_point[1], top)
        frame_points.InsertPoint(2, end_point[0], end_point[1], top)
        frame_points.InsertPoint(3, end_point[0], end_point[1], bottom)
        line = vtk.vtkLine()
        line.GetPointIds().SetId(0, 0)
        line.GetPointIds().SetId(1, 1)
        frame_cells.InsertNextCell(line)
        line.GetPointIds().SetId(0, 1)
        line.GetPointIds().SetId(1, 2)
        frame_cells.InsertNextCell(line)
        line.GetPointIds().SetId(0, 2)
        line.GetPointIds().SetId(1, 3)
        frame_cells.InsertNextCell(line)
        line.GetPointIds().SetId(0, 3)
        line.GetPointIds().SetId(1, 0)
        frame_cells.InsertNextCell(line)
        vtk_frame.SetPoints(frame_points)
        vtk_frame.SetLines(frame_cells)
        self.df.loc[self.df['uid'] == uid, 'vtk_plane'] = vtk_plane
        self.df.loc[self.df['uid'] == uid, 'vtk_frame'] = vtk_frame

    """Standard QT methods slightly adapted to the data source."""

    def data(self, index, role):
        """Data is updated on the fly:
        .row() index points to an entity in the vtkCollection
        .column() index points to an element in the list created on the fly
        based on the column headers stored in the dictionary."""
        if role == Qt.DisplayRole:
            value = self.df.iloc[index.row(), index.column()]
            return str(value)

    def headerData(self, section, orientation, role):
        """Set header from pandas dataframe. "section" is a standard Qt variable."""
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                return str(self.df.columns[section])
            if orientation == Qt.Vertical:
                return str(self.df.index[section])

    def rowCount(self, index):
        """Set row count from pandas dataframe"""
        return self.df.shape[0]

    def columnCount(self, index):
        """Set column count from pandas dataframe"""
        return self.df.shape[1]

    def flags(self, index):
        """Set editable columns."""
        if index.column() in self.editable_columns:
            return Qt.ItemFlags(QAbstractTableModel.flags(self, index) | Qt.ItemIsEditable)
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def setData(self, index, value, role=Qt.EditRole):
        """This is the method allowing to edit the table and the underlying dataframe.
        "self.parent is" is used to point to parent, because the standard Qt setData
        method does not allow for extra variables to be passed into this method."""
        uid = self.df.iloc[index.row(), 0]
        if index.isValid():
            self.df.iloc[index.row(), index.column()] = value
            if self.data(index, Qt.DisplayRole) == value:
                """The following check is needed to avoid duplicate names that are not allowed for cross sections."""
                if self.df["name"].duplicated().sum() > 0:
                    self.df.iloc[index.row(), index.column()] = value + "_" + uid
                self.dataChanged.emit(index, index)
                self.parent.xsect_metadata_modified_signal.emit([uid])  # a list of uids is emitted, even if the entity is just one
                return True
            return QVariant()
