"""boundary.py
PZero© Andrea Bistacchi"""

from pzero.collections.collection_base import Collection

"""Import as much as possible as from <module> import <class> or <class as ...>"""
from vtk import vtkPoints
from numpy import array as np_array
from numpy import set_printoptions as np_set_printoptions
from pandas import set_option as pd_set_option
from uuid import uuid4 as uuid_uuid4
from copy import deepcopy
from PyQt5.QtCore import Qt, QVariant
from pzero.helper_dialogs import general_input_dialog
from pzero.entities.entities_factory import PolyLine, TriSurf

"""Options to print Pandas dataframes in console for testing."""
pd_desired_width = 800
pd_max_columns = 20
pd_show_precision = 4
pd_max_colwidth = 80
pd_set_option('display.width', pd_desired_width)
np_set_printoptions(linewidth=pd_desired_width)
pd_set_option('display.max_columns', pd_max_columns)
pd_set_option('display.precision', pd_show_precision)
pd_set_option('display.max_colwidth', pd_max_colwidth)

""""Methods used to create boundaries. TO BE MOVED IN ANOTHER MODULE - WORKS IN MAP VIEW?? ________________________________"""


def boundary_from_points(self, vector):
    """Create a new Boundary from a vector"""
    boundary_dict = deepcopy(self.main_window.boundary_coll.entity_dict)
    """multiple_input_dialog widget is built to check the default value associated to each feature in
    section_dict_in: this value defines the type (str-int-float) of the output that is passed to section_dict_updt.
    It is therefore necessary in section_dict_in to implement the right type for each variable."""
    """Freeze QT interface"""
    self.disable_actions()
    """Draw the diagonal of the Boundary by drawing a vector with vector_by_mouse. "while True" lets the user 
    draw the vector multiple times if modifications are necessary"""
    self.plotter.untrack_click_position(side='left')

    boundary_dict_in = {'warning': ['Boundary from points',
                                    'Build new Boundary from a user-drawn line that represents the horizontal diagonal\nof the Bounding box.\nOnce drawn, values can be modified from keyboard or by drawing another vector.',
                                    'QLabel'],
                        'name': ['Insert Boundary name', 'new_boundary', 'QLineEdit'],
                        'origin_x': ['Insert origin X coord', vector.p1[0], 'QLineEdit'],
                        'origin_y': ['Insert origin Y coord', vector.p1[1], 'QLineEdit'],
                        'end_x': ['Insert end-point X coord', vector.p2[0], 'QLineEdit'],
                        'end_y': ['Insert end-point Y coord', vector.p2[1], 'QLineEdit'],
                        'top': ['Insert top', 1000.0, 'QLineEdit'],
                        'bottom': ['Insert bottom', -1000.0, 'QLineEdit'],
                        'activatevolume': ['volumeyn',
                                           'Do not create volume. Create horizontal parallelogram at Z=0 meters',
                                           'QCheckBox']}
    boundary_dict_updt = general_input_dialog(title='New Boundary from points', input_dict=boundary_dict_in)
    if boundary_dict_updt is None:
        self.enable_actions()
        return
    """Check if other Boundaries with the same name exist. If so, add suffix to make the name unique"""
    while True:
        if boundary_dict_updt['name'] in self.main_window.boundary_coll.get_names():
            boundary_dict_updt['name'] = boundary_dict_updt['name'] + '_0'
        else:
            break
    """Check if top and bottom fields are empty"""
    if boundary_dict_updt['top'] is None:
        boundary_dict_updt['top'] = 1000.0
    if boundary_dict_updt['bottom'] is None:
        boundary_dict_updt['bottom'] = -1000.0
    if boundary_dict_updt['top'] == boundary_dict_updt['bottom']:
        boundary_dict_updt['top'] = boundary_dict_updt['top'] + 1.0
    boundary_dict['name'] = boundary_dict_updt['name']
    if boundary_dict_updt['activatevolume'] == 'check':
        """Build rectangular polyline at Z=0 meters"""
        boundary_dict['topological_type'] = 'PolyLine'
        boundary_dict['vtk_obj'] = PolyLine()
        boundary_dict['vtk_obj'].points = [(boundary_dict_updt['origin_x'], boundary_dict_updt['origin_y'], 0.0),
                                           (boundary_dict_updt['end_x'], boundary_dict_updt['origin_y'], 0.0),
                                           (boundary_dict_updt['end_x'], boundary_dict_updt['end_y'], 0.0),
                                           (boundary_dict_updt['origin_x'], boundary_dict_updt['end_y'], 0.0),
                                           (boundary_dict_updt['origin_x'], boundary_dict_updt['origin_y'], 0.0)]
        boundary_dict['vtk_obj'].auto_cells()
    else:
        """Build Boundary as volume"""
        boundary_dict['topological_type'] = 'TriSurf'
        boundary_dict['vtk_obj'] = TriSurf()
        nodes = vtkPoints()
        nodes.InsertPoint(0, boundary_dict_updt['origin_x'], boundary_dict_updt['origin_y'],
                          boundary_dict_updt['bottom'])
        nodes.InsertPoint(1, boundary_dict_updt['end_x'], boundary_dict_updt['origin_y'], boundary_dict_updt['bottom'])
        nodes.InsertPoint(2, boundary_dict_updt['end_x'], boundary_dict_updt['end_y'], boundary_dict_updt['bottom'])
        nodes.InsertPoint(3, boundary_dict_updt['origin_x'], boundary_dict_updt['end_y'], boundary_dict_updt['bottom'])
        nodes.InsertPoint(4, boundary_dict_updt['origin_x'], boundary_dict_updt['origin_y'], boundary_dict_updt['top'])
        nodes.InsertPoint(5, boundary_dict_updt['end_x'], boundary_dict_updt['origin_y'], boundary_dict_updt['top'])
        nodes.InsertPoint(6, boundary_dict_updt['end_x'], boundary_dict_updt['end_y'], boundary_dict_updt['top'])
        nodes.InsertPoint(7, boundary_dict_updt['origin_x'], boundary_dict_updt['end_y'], boundary_dict_updt['top'])
        boundary_dict['vtk_obj'].SetPoints(nodes)
        boundary_dict['vtk_obj'].append_cell(np_array([0, 1, 4]))
        boundary_dict['vtk_obj'].append_cell(np_array([1, 4, 5]))
        boundary_dict['vtk_obj'].append_cell(np_array([1, 2, 5]))
        boundary_dict['vtk_obj'].append_cell(np_array([2, 5, 6]))
        boundary_dict['vtk_obj'].append_cell(np_array([2, 3, 6]))
        boundary_dict['vtk_obj'].append_cell(np_array([3, 6, 7]))
        boundary_dict['vtk_obj'].append_cell(np_array([0, 4, 7]))
        boundary_dict['vtk_obj'].append_cell(np_array([0, 3, 7]))
        boundary_dict['vtk_obj'].append_cell(np_array([4, 6, 7]))
        boundary_dict['vtk_obj'].append_cell(np_array([4, 5, 6]))
        boundary_dict['vtk_obj'].append_cell(np_array([0, 1, 3]))
        boundary_dict['vtk_obj'].append_cell(np_array([1, 2, 3]))
    uid = self.main_window.boundary_coll.add_entity_from_dict(entity_dict=boundary_dict)
    """Un-Freeze QT interface"""
    self.enable_actions()


class BoundaryCollection(Collection):
    """
    Initialize BoundaryCollection table.
    Column headers are taken from BoundaryCollection.boundary_entity_dict.keys()
    parent is supposed to be the project_window

    boundary_entity_dict is a dictionary of entity attributes used throughout the project.
    Always use deepcopy(BoundaryCollection.image_entity_dict) to copy this dictionary without altering the original.
    """

    @property
    def entity_dict(self):
        return {'uid': "",
                'name': "undef",
                'topological_type': "undef",
                'x_section': "",
                # this is the uid of the cross section for "XsVertexSet", "XsPolyLine", and "XsImage", empty for all others
                'vtk_obj': None}

    @property
    def type_dict(self):
        return {'uid': str,
                'name': str,
                'topological_type': str,
                'x_section': str,
                'vtk_obj': object}

    @property
    def valid_topological_type(self):
        return ["PolyLine", "TriSurf", "XsPolyLine"]

    @property
    def valid_types(self):
        return []

    @property
    def editable_columns(self):
        return self._df.columns.get_indexer(["name"])

    @property
    def default_save_table_filename(self):
        return "boundary"

    def add_entity_from_dict(self, entity_dict=None):
        """Add entity to collection from dictionary.
        Create a new uid if it is not included in the dictionary."""
        if not entity_dict['uid']:
            entity_dict['uid'] = str(uuid_uuid4())
        """"Append new row to dataframe. Note that the 'append()' method for Pandas dataframes DOES NOT
        work in place, hence a NEW dataframe is created every time and then substituted to the old one."""
        self._df = self._df.append(entity_dict, ignore_index=True)
        """Reset data model"""
        self.modelReset.emit()
        """Then emit signal to update the views."""
        self.main_window.boundary_added_signal.emit(
            [entity_dict['uid']])  # a list of uids is emitted, even if the entity is just one
        return entity_dict['uid']

    def remove_entity(self, uid=None):
        """Remove entity from collection. Remove row from dataframe and reset data model."""
        self._df.drop(self._df[self._df['uid'] == uid].index, inplace=True)
        self.modelReset.emit()  # is this really necessary?
        """When done, send a signal over to the views."""
        self.main_window.boundary_removed_signal.emit([uid])  # a list of uids is emitted, even if the entity is just one
        return uid

    def replace_vtk(self, uid=None, vtk_object=None):
        if isinstance(vtk_object, type(self._df.loc[self._df['uid'] == uid, 'vtk_obj'].values[0])):
            new_dict = deepcopy(self._df.loc[self._df['uid'] == uid, self._df.columns != 'vtk_obj'].to_dict('records')[0])
            new_dict['vtk_obj'] = vtk_object
            self.remove_entity(uid)
            self.add_entity_from_dict(entity_dict=new_dict)
        else:
            print("ERROR - replace_vtk with vtk of a different type.")

    def get_legend(self):
        """Get legend."""
        legend_dict = self.main_window.others_legend_df.loc[
            self.main_window.others_legend_df['other_type'] == 'Boundary'].to_dict('records')
        return legend_dict[0]

    def get_uid_x_section(self, uid=None):
        """Get value(s) stored in dataframe (as pointer) from uid."""
        return self._df.loc[self._df['uid'] == uid, 'x_section'].values[0]

    def set_uid_x_section(self, uid=None, x_section=None):
        """Set value(s) stored in dataframe (as pointer) from uid."""
        self._df.loc[self._df['uid'] == uid, 'x_section'] = x_section

    """Standard QT methods slightly adapted to the data source."""

    def setData(self, index, value, role=Qt.EditRole):
        """This is the method allowing to edit the table and the underlying dataframe.
        "self.main_window is" is used to point to parent, because the standard Qt setData
        method does not allow for extra variables to be passed into this method."""
        if index.isValid():
            self._df.iloc[index.row(), index.column()] = value
            if self.data(index, Qt.DisplayRole) == value:
                self.dataChanged.emit(index, index)
                uid = self._df.iloc[index.row(), 0]
                self.main_window.boundary_metadata_modified_signal.emit(
                    [uid])  # a list of uids is emitted, even if the entity is just one
                return True
        return QVariant()
