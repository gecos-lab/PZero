from pzero.collections.geological_collection import GeologicalCollection
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

    geol_legend_df = pd_DataFrame(columns=list(Legend.geol_legend_dict.keys()))
    legend = FakeLegend()
    prop_legend = FakeLegend()
    geology_added_signal = FakeSignal()
    geology_removed_signal = FakeSignal()


# Class for testing geological_collection.py
class TestGeologicalCollection:
    geo_coll_istance = GeologicalCollection(FakeWindow)

    geological_entity_dict1 = {'uid': "0",
                               'name': "geoname",
                               'topology': "topol",
                               'type': "undef",
                               'feature': "undef",
                               'scenario': "sc1",
                               'properties_names': [],
                               'properties_components': [],
                               'x_section': "",
                               'vtk_obj': None}

    geological_entity_dict2 = {'uid': "2",
                               'name': "geoname2",
                               'topology': "topol2",
                               'type': "undef",
                               'feature': "undef",
                               'scenario': "sc2",
                               'properties_names': [],
                               'properties_components': [],
                               'x_section': "",
                               'vtk_obj': None}

    # Test the add_entity_from_dict() method from geological_collection.py
    def test_add_entity_from_dict(self):
        # Add two entities
        self.geo_coll_istance.add_entity_from_dict(entity_dict=self.geological_entity_dict1)
        self.geo_coll_istance.add_entity_from_dict(entity_dict=self.geological_entity_dict2)

        # This print should be the same as the geological_entity_dict
        # print(geo_coll_istance.df)

        assert self.geo_coll_istance.get_number_of_entities() == 2 \
               and (self.geological_entity_dict1['uid'] in self.geo_coll_istance.get_uids()) \
               and (self.geological_entity_dict2['uid'] in self.geo_coll_istance.get_uids())


