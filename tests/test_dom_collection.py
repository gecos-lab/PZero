from pzero.dom_collection import DomCollection
from pzero.legend_manager import Legend
from pzero.entities_factory import DEM

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

    backgrounds_legend_df = pd_DataFrame(columns=list(Legend.backgrounds_legend_dict.keys()))
    legend = FakeLegend()
    prop_legend = FakeLegend()
    dom_added_signal = FakeSignal()
    dom_removed_signal = FakeSignal()


# Class for testing the dom_collection
class TestDomCollection:
    test_vtk_obj = DEM()
    test_vtk_obj2 = DEM()
    geological_entity_dict = {'uid': "0",
                              'name': "geoname",
                              'topological_type': "topol",
                              'geological_type': "undef",
                              'geological_feature': "undef",
                              'scenario': "sc1",
                              'properties_names': [],
                              'properties_components': [],
                              'x_section': "",
                              'vtk_obj': test_vtk_obj}

    dom_istance = DomCollection(FakeWindow)

    def test_add_entity_from_dict(self):
        # add an entity
        self.dom_istance.add_entity_from_dict(self.geological_entity_dict)

        # check if the entities number is equal to the add_entity calls
        # and if the uid inserted is in the uids of the collection
        assert self.dom_istance.get_number_of_entities() == 1 \
               and self.geological_entity_dict['uid'] in self.dom_istance.get_uids()

    def test_remove_entity(self):
        # add an entity
        self.dom_istance.add_entity_from_dict(self.geological_entity_dict)

        # remove an entity
        self.dom_istance.remove_entity(self.geological_entity_dict['uid'])
        print(self.dom_istance.df)

        # check if the entities number is equal to the add_entity calls minus the remove_entity calls
        # and if the uid inserted and then removed is not in the uids of the collection
        assert self.dom_istance.get_number_of_entities() == 0 \
            and self.geological_entity_dict['uid'] not in self.dom_istance.get_uids()

    def test_replace_vtk(self):
        # add an entity
        self.dom_istance.add_entity_from_dict(self.geological_entity_dict)

        # replace the vtk obj of the entity added
        self.dom_istance.replace_vtk(uid=self.geological_entity_dict['uid'], vtk_object=self.test_vtk_obj2)

        # check if the entities number is equal to the add_entity calls
        # and if the vtk obj inserted is in the uids of the collection
        assert self.dom_istance.get_number_of_entities() == 1 \
            and self.dom_istance.get_uid_vtk_obj(self.geological_entity_dict['uid']) == self.test_vtk_obj2
