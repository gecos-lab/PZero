from pzero.collections.fluid_collection import FluidCollection
from pzero.legend_manager import Legend
from pzero.entities_factory import DEM

from pandas import DataFrame as pd_DataFrame
from PySide6.QtWidgets import QMainWindow


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

    fluidss_coll.legend_df = pd_DataFrame(columns=list(Legend.fluids_legend_dict.keys()))
    legend = FakeLegend()
    prop_legend = FakeLegend()
    fluid_coll.signals.added = FakeSignal()
    fluid_coll.signals.removed = FakeSignal()
    fluid_coll = FluidCollection()


class TestFluidCollection:
    fluid_coll_istance = FluidCollection(FakeWindow)
    test_vtk_obj = DEM()
    test_vtk_obj2 = DEM()
    entity_dict = {'uid': "4",
                         'name': "fluid-test",
                         'topology': "undef",
                         'role': "undef",
                         'feature': "undef",
                         'scenario': "undef",
                         'properties_names': [],
                         'properties_components': [],
                         'x_section': "",
                         'vtk_obj': test_vtk_obj}

    def test_add_entity_from_dict(self):
        # add an entity
        self.fluid_coll_istance.add_entity_from_dict(self.entity_dict)

        # check if the entities number is equal to the add_entity calls
        # and if the uid inserted is in the uids of the collection
        assert self.fluid_coll_istance.get_number_of_entities() == 1 \
               and self.entity_dict['uid'] in self.fluid_coll_istance.get_uids()

