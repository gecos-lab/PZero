from pzero.collections.background_collection import BackgroundCollection
from pzero.legend_manager import Legend

from pandas import DataFrame as pd_DataFrame
from PySide6.QtWidgets import QMainWindow

# Global Variable
entity_dict = {
    "uid": "53",
    "name": "background-test",
    "topology": "undef",
    "role": "undef",
    "feature": "undef",
    "properties_names": [],
    "properties_components": [],
    "x_section": "",
    "borehole": "",
    "vtk_obj": None,
}


# Class used as a substitute of pyqt-signals/emit
class FakeSignal:
    def emit(self, uid):
        return


# Class used as a substitute of Legend
class FakeLegend:
    def update_widget(self, parent):
        return


# Class used as a substitute of BackgroundCollection
class FakeBGCollection:
    df = pd_DataFrame(columns=list(entity_dict.keys()))


# Class used for test the main window (project_window) as a parent
class FakeWindow(QMainWindow):
    def __init__(self):
        super(FakeWindow, self).__init__()

    backgrnd_coll.legend_df = pd_DataFrame(
        columns=list(Legend.backgrounds_legend_dict.keys())
    )
    backgrnd_coll = FakeBGCollection()

    legend = FakeLegend()
    prop_legend = FakeLegend()

    backgrnd_coll.signals.added = FakeSignal()
    backgrnd_coll.signals.removed = FakeSignal()


class TestBackgroundCollection:
    background_coll_istance = BackgroundCollection(FakeWindow)

    def test_add_entity_from_dict(self):
        # add an entity
        self.background_coll_istance.add_entity_from_dict(entity_dict)

        # check if the entities number is equal to the add_entity calls
        # and if the uid inserted is in the uids of the collection
        assert (
            self.background_coll_istance.get_number_of_entities() == 1
            and entity_dict["uid"] in self.background_coll_istance.get_uids()
        )
