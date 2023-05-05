from pzero.collections.mesh3d_collection import Mesh3DCollection

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

    mesh3d_added_signal = FakeSignal()
    mesh3d_removed_signal = FakeSignal()
    prop_legend = FakeLegend()


class TestMesh3dCollection:
    mesh_3d_coll_istance = Mesh3DCollection(FakeWindow)

    mesh3d_entity_dict = {'uid': "0",
                          'name': "meshtest",
                          'mesh3d_type': "undef",
                          'properties_names': [],
                          'properties_components': [],
                          'x_section': "",
                          'vtk_obj': None}

    def test_add_entity_from_dict(self):
        # add an entity
        self.mesh_3d_coll_istance.add_entity_from_dict(self.mesh3d_entity_dict)

        # check if the entities number is equal to the add_entity calls
        # and if the uid inserted is in the uids of the collection
        assert self.mesh_3d_coll_istance.get_number_of_entities() == 1 \
               and self.mesh3d_entity_dict['uid'] in self.mesh_3d_coll_istance.get_uids()

    def test_remove_entity(self):
        # add an entity
        self.mesh_3d_coll_istance.add_entity_from_dict(self.mesh3d_entity_dict)

        # remove an entity
        self.mesh_3d_coll_istance.remove_entity(self.mesh3d_entity_dict['uid'])

        # check if the entities number is equal to the add_entity calls minus the remove_entity calls
        # and if the uid inserted and then removed is not in the uids of the collection
        assert self.mesh_3d_coll_istance.get_number_of_entities() == 0 \
               and self.mesh3d_entity_dict['uid'] not in self.mesh_3d_coll_istance.get_uids()
