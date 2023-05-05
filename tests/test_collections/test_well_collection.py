from pzero.collections.well_collection import WellCollection
from pzero.entities_factory import Well
from pzero.entities_factory import PolyLine
from pzero.legend_manager import Legend

from pandas import DataFrame as pd_DataFrame
from PyQt5.QtWidgets import QMainWindow



# Class used as a substitute of pyqt-signals/emit
class FakeSignal:
    def emit(self, uid):
        return


# Class used as a substitute of Legend
class FakeLegend:
    def update_widget(self, parent):
        return


# Class used for test the main window (project_window) as a parent
class FakeWindow(QMainWindow):
    def __init__(self):
        super(FakeWindow, self).__init__()

    legend = FakeLegend()
    prop_legend = FakeLegend()
    well_legend_df = pd_DataFrame(columns=list(Legend.well_legend_dict.keys()))
    well_added_signal = FakeSignal()
    well_removed_signal = FakeSignal()


class TestWellConnection:
    vtk_obj = PolyLine()
    vtk_obj2 = Well().trace
    well_istance = WellCollection(FakeWindow)

    well_entity_dict_1 = {'uid': "14",
                          'Loc ID': "3",
                          'properties_names': [],
                          'properties_components': [],
                          'properties_types': [],
                          'markers': [],
                          'vtk_obj': vtk_obj}

    def test_add_entity_from_dict(self):
        # add an entity
        self.well_istance.add_entity_from_dict(self.well_entity_dict_1)

        # check if the entities number is equal to the add_entity calls
        # and if the uid inserted is in the uids of the collection
        assert self.well_istance.get_number_of_entities() == 1 \
               and self.well_entity_dict_1['uid'] in self.well_istance.get_uids()

    def test_remove_entity(self):
        # add an entity
        self.well_istance.add_entity_from_dict(self.well_entity_dict_1)

        # remove an entity
        self.well_istance.remove_entity(self.well_entity_dict_1['uid'])

        # check if the entities number is equal to the add_entity calls minus the remove_entity calls
        # and if the uid inserted and then removed is not in the uids of the collection
        assert self.well_istance.get_number_of_entities() == 0 \
               and self.well_entity_dict_1['uid'] not in self.well_istance.get_uids()

    def test_replace_vtk(self):
        # add an entity
        self.well_istance.add_entity_from_dict(self.well_entity_dict_1)

        # replace the vtk obj of the entity added
        self.well_istance.replace_vtk(uid=self.well_entity_dict_1['uid'], vtk_object=self.vtk_obj2)

        # check if the entities number is equal to the add_entity calls
        # and if the vtk obj inserted is in the uids of the collection
        assert self.well_istance.get_number_of_entities() == 1 \
               and self.well_istance.get_uid_vtk_obj(self.well_entity_dict_1['uid']) == self.vtk_obj2
