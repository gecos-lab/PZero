from PyQt5.QtWidgets import QMainWindow
from pzero.boundary_collection import BoundaryCollection
from pzero.entities_factory import DEM


# Class used for test signals
class TestSignal:
    def emit(self, uid):
        return


# Class used for test the main window (project_window) as a parent
class TestWindow(QMainWindow):
    boundary_added_signal = TestSignal()
    boundary_removed_signal = TestSignal()

    def __init__(self):
        super(TestWindow, self).__init__()


# Class for testing the boundary collection
class TestBoundaryCollection:
    boundary_coll_istance = BoundaryCollection(parent=TestWindow)
    test_vtk_obj = DEM()
    test_vtk_obj2 = DEM()

    boundary_entity_dict = {'uid': "9",
                            'name': "boundary-test",
                            'topological_type': "undef",
                            'x_section': "",
                            'vtk_obj': test_vtk_obj}
    boundary_entity_dict2 = {'uid': "9",
                            'name': "boundary-test",
                            'topological_type': "undef",
                            'x_section': "",
                            'vtk_obj': test_vtk_obj2}

    def test_add_entity_from_dict(self):
        # add an entity
        self.boundary_coll_istance.add_entity_from_dict(self.boundary_entity_dict)

        # print check
        print(self.boundary_coll_istance.df)

        # check if the entities number is equal to the add_entity calls
        # and if the uid inserted is in the uids of the collection
        assert self.boundary_coll_istance.get_number_of_entities() == 1 \
               and self.boundary_entity_dict['uid'] in self.boundary_coll_istance.get_uids()

    def test_remove_entity(self):
        # add an entity
        self.boundary_coll_istance.add_entity_from_dict(self.boundary_entity_dict)

        # remove an entity
        self.boundary_coll_istance.remove_entity(self.boundary_entity_dict['uid'])

        # check if the entities number is equal to the add_entity calls minus the remove_entity calls
        # and if the uid inserted and then removed is not in the uids of the collection
        assert self.boundary_coll_istance.get_number_of_entities() == 0 \
               and self.boundary_entity_dict['uid'] not in self.boundary_coll_istance.get_uids()

    def test_replace_vtk(self):
        # add an entity
        self.boundary_coll_istance.add_entity_from_dict(self.boundary_entity_dict)

        # remove an entity
        self.boundary_coll_istance.replace_vtk(uid="9", vtk_object=self.test_vtk_obj2)

        assert self.boundary_coll_istance.get_number_of_entities() == 1 \
            and self.boundary_coll_istance.get_uid_vtk_obj(self.boundary_entity_dict['uid']) == self.test_vtk_obj2
