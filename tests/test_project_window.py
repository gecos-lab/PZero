import pytest

from pzero.entities_factory import VertexSet
from pzero.project_window import ProjectWindow

from PyQt5.QtWidgets import QWidget, QFileDialog
from PyQt5.QtCore import QSize

# Global Var to set if the test are automatic or not
automatic_test = True


# Class for testing the ProjectWindow, qtbot part of a plugin of pytestQt
class TestProjectWindow:
    test_vtk_obj = VertexSet()
    test_vtk_obj2 = VertexSet()

    geological_entity_dict = {'uid': "0",
                              'name': "geoname",
                              'topology': "VertexSet",
                              'role': "undef",
                              'feature': "undef",
                              'scenario': "sc1",
                              'properties_names': [],
                              'properties_components': [],
                              'x_section': "",
                              'vtk_obj': test_vtk_obj}

    geological_entity_dict2 = {'uid': "2",
                               'name': "geoname2",
                               'topology': "VertexSet",
                               'role': "undef",
                               'feature': "undef",
                               'scenario': "sc2",
                               'properties_names': [],
                               'properties_components': [],
                               'x_section': "",
                               'vtk_obj': test_vtk_obj2}

    def ignore(self):
        return

    def fake_open_file_dialog(self):
        q_file_dialog = QFileDialog()
        q_file_dialog.show()
        return q_file_dialog

    @pytest.fixture
    def test_is_window(self, qtbot):
        project_window = ProjectWindow()

        print(project_window.isWindow())

        assert project_window.isWindow() is True

    @pytest.fixture
    def test_window_name(self, qtbot):
        project_window = ProjectWindow()

        assert project_window.windowTitle() == "PZero" \
            and project_window.size() == QSize(1418, 800)

    @pytest.fixture
    def test_shown_table(self, qtbot):
        project_window = ProjectWindow()

        shown_table = project_window.shown_table
        # print(shown_table)

        assert shown_table == 'tabGeology'

    @pytest.fixture
    def test_shown_table_change(self, qtbot):
        project_window = ProjectWindow()

        tab_img = 'tabImages'

        page_img = project_window.tabCentral.findChild(QWidget, tab_img)

        project_window.tabCentral.setCurrentWidget(page_img)
        shown_table = project_window.shown_table

        assert shown_table == tab_img

    @pytest.fixture
    def test_none_selected_uids(self, qtbot):
        project_window = ProjectWindow()

        assert project_window.selected_uids == []

    @pytest.fixture
    def test_selected_uids(self, qtbot):
        project_window = ProjectWindow()

        # add an entity and then select all the entities on the geology View
        project_window.geol_coll.add_entity_from_dict(self.geological_entity_dict)
        project_window.GeologyTableView.selectAll()

        # check that the length of the selected uids is equal to the added entity inside the geol coll
        assert len(project_window.selected_uids) == 1

    @pytest.fixture
    def test_entity_remove(self, qtbot, monkeypatch):
        # monkeypatch/mock function
        def mock_entity_remove():
            self.update_actors = False
            for uid in project_window.selected_uids:
                if project_window.shown_table == "tabGeology":
                    project_window.geol_coll.remove_entity(uid=uid)
            self.update_actors = True

        project_window = ProjectWindow()

        # add an entity and then select all the entities on the geology View
        project_window.geol_coll.add_entity_from_dict(self.geological_entity_dict)
        project_window.GeologyTableView.selectAll()

        # remove the entity through the mock function 'entity_remove'
        mock_entity_remove()

        assert len(project_window.selected_uids) == 0

    # @pytest.fixture
    # Testing the entities merge - running only manually, to try change the var automatic_test to false
    # or comment the next @pytest line
    @pytest.mark.skipif(automatic_test, reason="Button-clicks not implemented yet")
    def test_entities_merge(self, qtbot):
        # These next two ints are needed in the two case: the first one is used when we remove the entities merged,
        # the second one is when we decide to keep the merged entities
        remove_merge_int = 0
        keep_merge_int = 2

        project_window = ProjectWindow()

        # add an entity and then select all the entities on the geology View
        project_window.geol_coll.add_entity_from_dict(self.geological_entity_dict)
        project_window.geol_coll.add_entity_from_dict(self.geological_entity_dict2)

        # select all the entities (which are two in this case) on the geology table and merge them
        project_window.GeologyTableView.selectAll()
        project_window.entities_merge()

        # reselect all the rows inside the Geology table
        project_window.GeologyTableView.selectAll()

        assert len(project_window.selected_uids) == remove_merge_int

    @pytest.fixture
    # Testing adding, selecting and getting geological entities
    def test_getting_entitites(self, qtbot):
        project_window = ProjectWindow()

        project_window.geol_coll.add_entity_from_dict(self.geological_entity_dict)
        project_window.geol_coll.add_entity_from_dict(self.geological_entity_dict2)

        project_window.GeologyTableView.selectAll()

        assert self.geological_entity_dict['uid'] in project_window.selected_uids
        assert self.geological_entity_dict2['uid'] in project_window.selected_uids

    # @pytest.fixture
    # Testing the add property event - running only manually, to try change the var automatic_test to false
    # or comment the next @pytest line
    @pytest.mark.skipif(automatic_test, reason="Button-clicks not implemented yet")
    def test_property_add(self, qtbot):
        project_window = ProjectWindow()

        project_window.geol_coll.add_entity_from_dict(self.geological_entity_dict)
        project_window.GeologyTableView.selectAll()

        project_window.property_add()

        assert project_window.geol_coll.get_uid_properties_names(uid="0") == ["new_property"]

    # @pytest.fixture
    # Testing the add and remove property event - running only manually, to try change the var automatic_test to false
    # or comment @pytest line
    @pytest.mark.skipif(automatic_test, reason="Button-clicks not implemented yet")
    def test_property_remove(self, qtbot):
        project_window = ProjectWindow()

        project_window.geol_coll.add_entity_from_dict(self.geological_entity_dict)
        project_window.GeologyTableView.selectAll()

        project_window.property_add()
        project_window.property_remove()

        assert project_window.geol_coll.get_uid_properties_names(uid="0") == []

    # @pytest.fixture
    # Testing lineations calculate
    @pytest.mark.skip(reason="lineations_calculate not implemented yet")
    def test_lineations_calculate(self):
        assert ...

    @pytest.fixture
    # Testing create_empty
    def test_create_empty(self, qtbot):
        project_window = ProjectWindow()

        # Add to the empty project two entities and selecting them
        project_window.geol_coll.add_entity_from_dict(self.geological_entity_dict)
        project_window.geol_coll.add_entity_from_dict(self.geological_entity_dict2)
        project_window.GeologyTableView.selectAll()

        # Create empty, so the selected_uids should be empty
        project_window.create_empty()

        assert project_window.selected_uids == []

    # @pytest.fixture
    # Testing save_project
    @pytest.mark.skipif(automatic_test, reason="Button-clicks not implemented yet")
    def test_save_project(self, qtbot):
        project_window = ProjectWindow()

        # Add to the empty project two entities and selecting them
        project_window.geol_coll.add_entity_from_dict(self.geological_entity_dict)
        project_window.geol_coll.add_entity_from_dict(self.geological_entity_dict2)
        project_window.GeologyTableView.selectAll()

        project_window.save_project()
        
        assert project_window.selected_uids == []

    @pytest.fixture
    # Testing dialog inside import_gocad
    def test_import_gocad(self, qtbot):
        qt_file_dialog = self.fake_open_file_dialog()

        assert qt_file_dialog.isVisible() is True
