from pzero.collections.background_collection import BackgroundCollection
from pzero.legend_manager import Legend

from pandas import DataFrame as pd_DataFrame
from PyQt5.QtWidgets import QMainWindow

# Global Variable
background_entity_dict = {'uid': "53",
                          'name': "background-test",
                          'topological_type': "undef",
                          'background_type': "undef",
                          'background_feature': "undef",
                          'properties_names': [],
                          'properties_components': [],
                          'x_section': "",
                          'borehole': "",
                          'vtk_obj': None}


# Class used as a substitute of pyqt-signals/emit
class TestSignal:
    def emit(self, uid):
        return


# Class used as a substitute of Legend
class TestLegend:
    def update_widget(self, parent):
        return


# Class used as a substitute of BackgroundCollection
class TestBGCollection:
    df = pd_DataFrame(columns=list(background_entity_dict.keys()))


# Class used for test the main window (project_window) as a parent
class TestWindow(QMainWindow):
    def __init__(self):
        super(TestWindow, self).__init__()

    backgrounds_legend_df = pd_DataFrame(columns=list(Legend.backgrounds_legend_dict.keys()))
    backgrounds_coll = TestBGCollection()

    legend = TestLegend()
    prop_legend = TestLegend()

    background_added_signal = TestSignal()
    background_removed_signal = TestSignal()


class TestBackgroundCollection:
    background_coll_istance = BackgroundCollection(TestWindow)

    def test_add_entity_from_dict(self):
        # add an entity
        self.background_coll_istance.add_entity_from_dict(background_entity_dict)

        # print check
        print(self.background_coll_istance.df)

        # check if the entities number is equal to the add_entity calls
        # and if the uid inserted is in the uids of the collection
        assert self.background_coll_istance.get_number_of_entities() == 1 \
               and background_entity_dict['uid'] in self.background_coll_istance.get_uids()

