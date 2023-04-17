from pzero.xsection_collection import XSectionCollection
from PyQt5.QtWidgets import QMainWindow


# Class used as a substitute of pyqt-signals/emit
class TestSignal:
    def emit(self, uid):
        return


# Class used as a substitute of Legend
class TestLegend:
    def update_widget(self, parent):
        return


# Class used for test the main window (project_window) as a parent
class TestWindow(QMainWindow):
    def __init__(self):
        super(TestWindow, self).__init__()

    xsect_added_signal = TestSignal()
    xsect_removed_signal = TestSignal()


class TestXSectionCollection:
    geological_entity_dict = {'uid': "0",
                              'name': "geoname",
                              'topological_type': "topol",
                              'geological_type': "undef",
                              'geological_feature': "undef",
                              'scenario': "sc1",
                              'properties_names': [],
                              'properties_components': [],
                              'x_section': "",
                              'vtk_obj': None}

    x_section_coll_istance = XSectionCollection(TestWindow)

    def test_add_entity_from_dict(self):
        # add an entity
        self.x_section_coll_istance.add_entity_from_dict(self.geological_entity_dict)

        # check if the entities number is equal to the add_entity calls
        # and if the uid inserted is in the uids of the collection
        assert self.x_section_coll_istance.get_number_of_entities() == 1 \
               and self.geological_entity_dict['uid'] in self.x_section_coll_istance.get_uids()

    def test_remove_entity(self):
        # add an entity
        self.x_section_coll_istance.add_entity_from_dict(self.geological_entity_dict)

        # remove an entity
        self.x_section_coll_istance.remove_entity(self.geological_entity_dict['uid'])

        # check if the entities number is equal to the add_entity calls minus the remove_entity calls
        # and if the uid inserted and then removed is not in the uids of the collection
        assert self.x_section_coll_istance.get_number_of_entities() == 0 \
               and self.geological_entity_dict['uid'] not in self.x_section_coll_istance.get_uids()

    def test_set_parameters_in_table(self):
        # add an entity
        self.x_section_coll_istance.add_entity_from_dict(self.geological_entity_dict)

        self.x_section_coll_istance.set_parameters_in_table(uid="2", name="name-test", base_point=[0, 1, 10],
                                                            end_point=[0, 1, 2], normal=[0, 1, 2],
                                                            azimuth=None, length=None, top=None, bottom=None)

        assert self.x_section_coll_istance.get_number_of_entities() == 1 \
            and self.geological_entity_dict['uid'] in self.x_section_coll_istance.get_uids()
