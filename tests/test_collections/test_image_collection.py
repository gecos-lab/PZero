from pzero.collections.image_collection import ImageCollection
from pzero.collections.dom_collection import DomCollection

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

    image_added_signal = FakeSignal()
    image_removed_signal = FakeSignal()
    dom_coll = DomCollection()
    prop_legend = FakeLegend()


class TestXSectionCollection:
    image_coll_istance = ImageCollection(FakeWindow)

    image_entity_dict = {'uid': "22",
                         'name': "image-test",
                         'image_type': "undef",
                         'properties_names': [],
                         'properties_components': [],
                         'properties_types': [],
                         'x_section': "",
                         'vtk_obj': None}

    def test_add_entity_from_dict(self):
        # add an entity
        self.image_coll_istance.add_entity_from_dict(self.image_entity_dict)

        # print check
        print(self.image_coll_istance.df)

        # check if the entities number is equal to the add_entity calls
        # and if the uid inserted is in the uids of the collection
        assert self.image_coll_istance.get_number_of_entities() == 1 \
               and self.image_entity_dict['uid'] in self.image_coll_istance.get_uids()

    def test_remove_entity(self):
        # add an entity
        self.image_coll_istance.add_entity_from_dict(self.image_entity_dict)

        # remove an entity
        self.image_coll_istance.remove_entity(self.image_entity_dict['uid'])
        # print(self.image_coll_istance.df)

        # check if the entities number is equal to the add_entity calls minus the remove_entity calls
        # and if the uid inserted and then removed is not in the uids of the collection
        assert [self.image_entity_dict['uid']] not in self.image_coll_istance.get_uids() \
            and self.image_coll_istance.get_number_of_entities() == 0
