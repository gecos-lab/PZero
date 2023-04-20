# import time
import pytest
from pzero.entities_factory import DEM

from pzero.project_window import ProjectWindow

from PyQt5.QtWidgets import QWidget

# Global Var to set if the test are automatic or not
automatic_test = True


# Class for testing the project window, qtbot part of a plugin of pytestQt
class TestProjectWindow:
    test_vtk_obj = DEM()

    geological_entity_dict = {'uid': "0",
                              'name': "geoname",
                              'topological_type': "topol",
                              'geological_type': "undef",
                              'geological_feature': "undef",
                              'scenario': "sc1",
                              'properties_names': [],
                              'properties_components': [],
                              'x_section': "",
                              'vtk_obj': test_vtk_obj}

    def ignore(self):
        return

    def test_is_window(self, qtbot):
        project_window = ProjectWindow()

        print(project_window.isWindow())

        assert project_window.isWindow() is True

    def test_window_name(self, qtbot):
        project_window = ProjectWindow()

        assert project_window.windowTitle() == "PZero"

    def test_shown_table(self, qtbot):
        project_window = ProjectWindow()

        shown_table = project_window.shown_table
        # print(shown_table)

        assert shown_table == 'tabGeology'

    def test_shown_table_change(self, qtbot):
        project_window = ProjectWindow()

        tab_img = 'tabImages'

        page_img = project_window.tabCentral.findChild(QWidget, tab_img)

        project_window.tabCentral.setCurrentWidget(page_img)
        shown_table = project_window.shown_table

        assert shown_table == tab_img

    def test_none_selected_uids(self, qtbot):
        project_window = ProjectWindow()

        assert project_window.selected_uids == []

    def test_selected_uids(self, qtbot):
        project_window = ProjectWindow()

        # add an entity and then select all the entities on the geology View
        project_window.geol_coll.add_entity_from_dict(self.geological_entity_dict)
        project_window.GeologyTableView.selectAll()

        # check that the length of the selected uids is equal to the added entity inside the geol coll
        assert len(project_window.selected_uids) == 1

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

    # Testing the add property event - running only manually, to try change the var automatic_test to false
    # or comment the next @pytest line
    @pytest.mark.skipif(automatic_test, reason="Button-clicks not implemented yet")
    def test_property_add(self, qtbot):
        project_window = ProjectWindow()

        project_window.geol_coll.add_entity_from_dict(self.geological_entity_dict)
        project_window.GeologyTableView.selectAll()

        project_window.property_add()

        assert project_window.geol_coll.get_uid_properties_names(uid="0") == ["new_property"]

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

