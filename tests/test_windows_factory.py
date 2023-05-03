import pytest

from pzero.windows_factory import BaseView
from pzero.project_window import ProjectWindow

from PyQt5.QtWidgets import QWidget, QMessageBox, QFileDialog, QMainWindow
from PyQt5.QtCore import Qt, QSize, QObject


# Class for testing the BaseView, qtbot is part of a plugin of pytestQt
class TestBaseView:
    geological_entity_dict1 = {'uid': "0",
                               'name': "geoname",
                               'topological_type': "topol",
                               'geological_type': "undef",
                               'geological_feature': "undef",
                               'scenario': "sc1",
                               'properties_names': [],
                               'properties_components': [],
                               'x_section': "",
                               'vtk_obj': None}

    geological_entity_dict2 = {'uid': "2",
                               'name': "geoname2",
                               'topological_type': "topol2",
                               'geological_type': "undef",
                               'geological_feature': "undef",
                               'scenario': "sc2",
                               'properties_names': [],
                               'properties_components': [],
                               'x_section': "",
                               'vtk_obj': None}

    # Testing if the windows is initialized and showed
    def test_show_canvas(self, qtbot):
        parent = ProjectWindow()
        base_view = BaseView(parent=parent)
        base_view.show_qt_canvas()

        assert base_view.isWindow() is True \
            and base_view.isVisible() is True

    # Testing create_geology_tree
    def test_create_geology_tree(self, qtbot):
        parent = ProjectWindow()
        base_view = BaseView(parent=parent)

        # create the geology list
        base_view.create_geology_tree()

        # check if it is a widget and if it's visible
        assert base_view.GeologyTreeWidget.isWidgetType() is True
        assert base_view.GeologyTreeWidget.isVisible()

    # Testing create_topology_tree
    def test_create_topology_tree(self, qtbot):
        parent = ProjectWindow()
        base_view = BaseView(parent=parent)

        # create the topology tree
        base_view.create_topology_tree()

        # check if it is a widget
        assert base_view.TopologyTreeWidget.isWidgetType() is True

    # Testing create_xsections_tree
    def test_create_xsections_tree(self, qtbot):
        parent = ProjectWindow()
        base_view = BaseView(parent=parent)

        # create the x sections tree
        base_view.create_xsections_tree()

        # check if it is a widget
        assert base_view.XSectionTreeWidget.isWidgetType() is True

    # Testing create_boundary_list
    def test_create_boundary_list(self, qtbot):
        parent = ProjectWindow()
        base_view = BaseView(parent=parent)

        # create the boundary list
        base_view.create_boundary_list()

        # check if it is a widget
        assert base_view.BoundariesTableWidget.isWidgetType() is True

    # Testing create_mesh3d_list
    def test_create_mesh3d_list(self, qtbot):
        parent = ProjectWindow()
        base_view = BaseView(parent=parent)

        # create the mesh3d list
        base_view.create_mesh3d_list()

        # check if it is a widget
        assert base_view.Mesh3DTableWidget.isWidgetType() is True

    # Testing create_dom_list
    def test_create_dom_list(self, qtbot):
        parent = ProjectWindow()
        base_view = BaseView(parent=parent)

        # create the dom_list
        base_view.create_dom_list()

        # check if it is a widget
        assert base_view.DOMsTableWidget.isWidgetType() is True

    # Testing create_image_list
    def test_create_image_list(self, qtbot):
        parent = ProjectWindow()
        base_view = BaseView(parent=parent)

        # create the image_list
        base_view.create_dom_list()

        # check if it is a widget
        assert base_view.ImagesTableWidget.isWidgetType() is True

    # Testing create_well_tree
    def test_create_well_tree(self, qtbot):
        parent = ProjectWindow()
        base_view = BaseView(parent=parent)

        # create the well_tree
        base_view.create_well_tree()

        # check if it is a widget
        assert base_view.WellsTreeWidget.isWidgetType() is True

    # Testing create_fluids_tree
    def test_create_fluids_tree(self, qtbot):
        parent = ProjectWindow()
        base_view = BaseView(parent=parent)

        # create the fluids tree
        base_view.create_fluids_tree()

        # check if it is a widget
        assert base_view.FluidsTreeWidget.isWidgetType() is True

    # Testing create_fluids_topology_tree
    def test_create_fluids_topology_tree(self, qtbot):
        parent = ProjectWindow()
        base_view = BaseView(parent=parent)

        # create the fluids_topology_tree
        base_view.create_fluids_topology_tree()

        # check if it is a widget
        assert base_view.FluidsTopologyTreeWidget.isWidgetType() is True

    # Testing create_backgrounds_tree
    def test_create_backgrounds_tree(self, qtbot):
        parent = ProjectWindow()
        base_view = BaseView(parent=parent)

        # create the backgrounds tree
        base_view.create_backgrounds_tree()

        # check if it is a widget
        assert base_view.BackgroundsTreeWidget.isWidgetType() is True

    # Testing create_backgrounds_topology_tree
    def test_create_backgrounds_topology_tree(self, qtbot):
        parent = ProjectWindow()
        base_view = BaseView(parent=parent)

        # create the backgrounds topology tree
        base_view.create_backgrounds_topology_tree()

        # check if it is a widget
        assert base_view.BackgroundsTopologyTreeWidget.isWidgetType() is True

