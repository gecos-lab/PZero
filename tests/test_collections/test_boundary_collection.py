from PyQt5.QtWidgets import QMainWindow
from pzero.collections.boundary_collection import BoundaryCollection
from pzero.entities_factory import DEM, VertexSet, TetraSolid


# Class used for test signals
class FakeSignal:
    def emit(self, uid):
        return


# Class used for test the main window (project_window) as a parent
class FakeWindow(QMainWindow):

    boundary_added_signal = FakeSignal()
    boundary_removed_signal = FakeSignal()


# Class for testing the boundary collection
class TestBoundaryCollection:
    boundary_coll_istance = BoundaryCollection(parent=FakeWindow)
    boundary_coll_istance2 = BoundaryCollection(parent=FakeWindow)

    test_vtk_obj = DEM()
    test_vtk_obj2 = DEM()
    test_vtk_obj3 = VertexSet()
    test_vtk_obj4 = TetraSolid()


    boundary_entity_dict = {'uid': "9",
                            'name': "boundary-test",
                            'topological_type': "test_topological_type",
                            'x_section': "[2, 0]",
                            'vtk_obj': test_vtk_obj}
    boundary_entity_dict2 = {'uid': "10",
                            'name': "boundary-test2",
                            'topological_type': "Polyline",
                            'x_section': "[4, 3]",
                            'vtk_obj': test_vtk_obj2}
    boundary_entity_dict3 = {'uid': "213a",
                        'name': "boundary-test3",
                        'topological_type': "VertexSet",
                        'x_section': "[-3, -5]",
                        'vtk_obj': test_vtk_obj3}
    boundary_entity_dict4 = {'uid': "81f3a",
                    'name': "boundary-test4",
                    'topological_type': "VertexSet",
                    'x_section': "[5, 9]",
                    'vtk_obj': test_vtk_obj4}


    def test_add_entity_from_dict(self):
        # add an entity
        self.boundary_coll_istance.add_entity_from_dict(self.boundary_entity_dict)

        # print check
        # print(self.boundary_coll_istance.df)

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


    def test_get_entities(self):
        # check if the collection is empty
        assert self.boundary_coll_istance2.get_number_of_entities() == 0

        # add three entities
        self.boundary_coll_istance2.add_entity_from_dict(self.boundary_entity_dict)
        self.boundary_coll_istance2.add_entity_from_dict(self.boundary_entity_dict2)
        self.boundary_coll_istance2.add_entity_from_dict(self.boundary_entity_dict3)
        
        assert self.boundary_coll_istance2.get_number_of_entities() == 3

    def test_get_uids(self):
        boundary_coll_istance = BoundaryCollection(parent=FakeWindow)

        # add three entities
        boundary_coll_istance.add_entity_from_dict(self.boundary_entity_dict)
        boundary_coll_istance.add_entity_from_dict(self.boundary_entity_dict2)
        boundary_coll_istance.add_entity_from_dict(self.boundary_entity_dict3)

        assert len(boundary_coll_istance.get_uids()) == 3
        assert self.boundary_entity_dict['uid'] in boundary_coll_istance.get_uids()
        assert self.boundary_entity_dict2['uid'] in boundary_coll_istance.get_uids()
        assert self.boundary_entity_dict3['uid'] in boundary_coll_istance.get_uids()

    def test_get_name(self):
        boundary_coll_istance = BoundaryCollection(parent=FakeWindow)

        # add three entities
        boundary_coll_istance.add_entity_from_dict(self.boundary_entity_dict)
        boundary_coll_istance.add_entity_from_dict(self.boundary_entity_dict2)
        boundary_coll_istance.add_entity_from_dict(self.boundary_entity_dict3)

        assert self.boundary_entity_dict['name'] in boundary_coll_istance.get_names()
        assert self.boundary_entity_dict2['name'] in boundary_coll_istance.get_names()
        assert self.boundary_entity_dict3['name'] in boundary_coll_istance.get_names()

    def test_get_topological_type_uids(self):
        boundary_coll_istance = BoundaryCollection(parent=FakeWindow)

        # add three entities
        boundary_coll_istance.add_entity_from_dict(self.boundary_entity_dict)
        boundary_coll_istance.add_entity_from_dict(self.boundary_entity_dict2)
        boundary_coll_istance.add_entity_from_dict(self.boundary_entity_dict3)

        assert [self.boundary_entity_dict['uid']] == boundary_coll_istance.get_topological_type_uids(self.boundary_entity_dict['topological_type'])
        assert [self.boundary_entity_dict2['uid']] == boundary_coll_istance.get_topological_type_uids(self.boundary_entity_dict2['topological_type'])
        assert [self.boundary_entity_dict3['uid']] == boundary_coll_istance.get_topological_type_uids(self.boundary_entity_dict3['topological_type'])
    
    def test_get_same_topological_type_uids(self):
        boundary_coll_istance = BoundaryCollection(parent=FakeWindow)

        # add three entities
        boundary_coll_istance.add_entity_from_dict(self.boundary_entity_dict)
        boundary_coll_istance.add_entity_from_dict(self.boundary_entity_dict2)
        boundary_coll_istance.add_entity_from_dict(self.boundary_entity_dict3)
        boundary_coll_istance.add_entity_from_dict(self.boundary_entity_dict4)

        assert boundary_coll_istance.get_number_of_entities() == 4
        assert [self.boundary_entity_dict3['uid'], self.boundary_entity_dict4['uid']] == boundary_coll_istance.get_topological_type_uids(self.boundary_entity_dict3['topological_type'])

    def test_get_uid_names(self):
        boundary_coll_istance = BoundaryCollection(parent=FakeWindow)

        # add three entities
        boundary_coll_istance.add_entity_from_dict(self.boundary_entity_dict)
        boundary_coll_istance.add_entity_from_dict(self.boundary_entity_dict2)
        boundary_coll_istance.add_entity_from_dict(self.boundary_entity_dict3)

        assert self.boundary_entity_dict['name'] == boundary_coll_istance.get_uid_name(self.boundary_entity_dict['uid'])
        assert self.boundary_entity_dict2['name'] == boundary_coll_istance.get_uid_name(self.boundary_entity_dict2['uid'])
        assert self.boundary_entity_dict3['name'] == boundary_coll_istance.get_uid_name(self.boundary_entity_dict3['uid'])
    
    def test_set_uid_names(self):
        boundary_coll_istance = BoundaryCollection(parent=FakeWindow)
        new_name = "new_name_entity"
        new_name2 = "new_name_entity2"
        new_name3 = "new_name_entity3"


        # add three entities
        boundary_coll_istance.add_entity_from_dict(self.boundary_entity_dict)
        boundary_coll_istance.add_entity_from_dict(self.boundary_entity_dict2)
        boundary_coll_istance.add_entity_from_dict(self.boundary_entity_dict3)

        # set the new names
        boundary_coll_istance.set_uid_name(self.boundary_entity_dict['uid'], new_name)
        boundary_coll_istance.set_uid_name(self.boundary_entity_dict2['uid'], new_name2)
        boundary_coll_istance.set_uid_name(self.boundary_entity_dict3['uid'], new_name3)


        assert new_name == boundary_coll_istance.get_uid_name(self.boundary_entity_dict['uid'])
        assert new_name2 == boundary_coll_istance.get_uid_name(self.boundary_entity_dict2['uid'])
        assert new_name3 == boundary_coll_istance.get_uid_name(self.boundary_entity_dict3['uid'])
    
    def test_get_uid_topological_type(self):
        boundary_coll_istance = BoundaryCollection(parent=FakeWindow)

        # add three entities
        boundary_coll_istance.add_entity_from_dict(self.boundary_entity_dict)
        boundary_coll_istance.add_entity_from_dict(self.boundary_entity_dict2)
        boundary_coll_istance.add_entity_from_dict(self.boundary_entity_dict3)

        assert self.boundary_entity_dict['topological_type'] == boundary_coll_istance.get_uid_topological_type(self.boundary_entity_dict['uid'])
        assert self.boundary_entity_dict2['topological_type'] == boundary_coll_istance.get_uid_topological_type(self.boundary_entity_dict2['uid'])
        assert self.boundary_entity_dict3['topological_type'] == boundary_coll_istance.get_uid_topological_type(self.boundary_entity_dict3['uid'])

    def test_set_uid_topological_type(self):
        boundary_coll_istance = BoundaryCollection(parent=FakeWindow)

        new_top_type = "TetraSolid"
        new_top_type2 = "XsPolyLine"
        new_top_type3 = "DEM"

        # add three entities
        boundary_coll_istance.add_entity_from_dict(self.boundary_entity_dict)
        boundary_coll_istance.add_entity_from_dict(self.boundary_entity_dict2)
        boundary_coll_istance.add_entity_from_dict(self.boundary_entity_dict3)

        # set the new topological types
        boundary_coll_istance.set_uid_topological_type(self.boundary_entity_dict['uid'], new_top_type)
        boundary_coll_istance.set_uid_topological_type(self.boundary_entity_dict2['uid'], new_top_type2)
        boundary_coll_istance.set_uid_topological_type(self.boundary_entity_dict3['uid'], new_top_type3)

        assert new_top_type == boundary_coll_istance.get_uid_topological_type(self.boundary_entity_dict['uid'])
        assert new_top_type2 == boundary_coll_istance.get_uid_topological_type(self.boundary_entity_dict2['uid'])
        assert new_top_type3 == boundary_coll_istance.get_uid_topological_type(self.boundary_entity_dict3['uid'])

    def test_get_uid_x_section(self):
        boundary_coll_istance = BoundaryCollection(parent=FakeWindow)

        # add three entities
        boundary_coll_istance.add_entity_from_dict(self.boundary_entity_dict)
        boundary_coll_istance.add_entity_from_dict(self.boundary_entity_dict2)
        boundary_coll_istance.add_entity_from_dict(self.boundary_entity_dict3)

        assert self.boundary_entity_dict['x_section'] == boundary_coll_istance.get_uid_x_section(self.boundary_entity_dict['uid'])
        assert self.boundary_entity_dict2['x_section'] == boundary_coll_istance.get_uid_x_section(self.boundary_entity_dict2['uid'])
        assert self.boundary_entity_dict3['x_section'] == boundary_coll_istance.get_uid_x_section(self.boundary_entity_dict3['uid'])

    def test_set_uid_x_section(self):
        boundary_coll_istance = BoundaryCollection(parent=FakeWindow)

        new_x_sect = "[1, 4]"
        new_x_sect2 = "[3, 43]"
        new_x_sect3 = "[4, 6]"

        # add three entities
        boundary_coll_istance.add_entity_from_dict(self.boundary_entity_dict)
        boundary_coll_istance.add_entity_from_dict(self.boundary_entity_dict2)
        boundary_coll_istance.add_entity_from_dict(self.boundary_entity_dict3)

        # set the new x section types
        boundary_coll_istance.set_uid_x_section(self.boundary_entity_dict['uid'], new_x_sect)
        boundary_coll_istance.set_uid_x_section(self.boundary_entity_dict2['uid'], new_x_sect2)
        boundary_coll_istance.set_uid_x_section(self.boundary_entity_dict3['uid'], new_x_sect3)

        assert new_x_sect== boundary_coll_istance.get_uid_x_section(self.boundary_entity_dict['uid'])
        assert new_x_sect2 == boundary_coll_istance.get_uid_x_section(self.boundary_entity_dict2['uid'])
        assert new_x_sect3 == boundary_coll_istance.get_uid_x_section(self.boundary_entity_dict3['uid'])

    def test_get_uid_vtk_obj(self):
        boundary_coll_istance = BoundaryCollection(parent=FakeWindow)

        # add three entities
        boundary_coll_istance.add_entity_from_dict(self.boundary_entity_dict)
        boundary_coll_istance.add_entity_from_dict(self.boundary_entity_dict2)
        boundary_coll_istance.add_entity_from_dict(self.boundary_entity_dict3)

        assert self.boundary_entity_dict['vtk_obj'] == boundary_coll_istance.get_uid_vtk_obj(self.boundary_entity_dict['uid'])
        assert self.boundary_entity_dict2['vtk_obj'] == boundary_coll_istance.get_uid_vtk_obj(self.boundary_entity_dict2['uid'])
        assert self.boundary_entity_dict3['vtk_obj'] == boundary_coll_istance.get_uid_vtk_obj(self.boundary_entity_dict3['uid'])

    def test_set_uid_vtk_obj(self):
            boundary_coll_istance = BoundaryCollection(parent=FakeWindow)

            new_vtk_obj = VertexSet()
            new_vtk_obj2 = TetraSolid()
            new_vtk_obj3 = DEM()

            # add three entities
            boundary_coll_istance.add_entity_from_dict(self.boundary_entity_dict)
            boundary_coll_istance.add_entity_from_dict(self.boundary_entity_dict2)
            boundary_coll_istance.add_entity_from_dict(self.boundary_entity_dict3)

            # set the new vtk object
            boundary_coll_istance.set_uid_vtk_obj(self.boundary_entity_dict['uid'], new_vtk_obj)
            boundary_coll_istance.set_uid_vtk_obj(self.boundary_entity_dict2['uid'], new_vtk_obj2)
            boundary_coll_istance.set_uid_vtk_obj(self.boundary_entity_dict3['uid'], new_vtk_obj3)

            assert new_vtk_obj == boundary_coll_istance.get_uid_vtk_obj(self.boundary_entity_dict['uid'])
            assert new_vtk_obj2 == boundary_coll_istance.get_uid_vtk_obj(self.boundary_entity_dict2['uid'])
            assert new_vtk_obj3 == boundary_coll_istance.get_uid_vtk_obj(self.boundary_entity_dict3['uid'])








