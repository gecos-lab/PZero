import pytest

from pzero.windows_factory import BaseView, View3D, ViewStereoplot, NavigationToolbar, NewView2D, \
    NewViewMap
from pzero.project_window import ProjectWindow


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

    @pytest.fixture
    # Testing if the windows is initialized and showed
    def test_show_canvas(self, qtbot):
        parent = ProjectWindow()
        base_view = BaseView(parent=parent)
        base_view.show_qt_canvas()

        assert base_view.isWindow() is True \
            and base_view.isVisible() is True

    @pytest.fixture
    # Testing create_geology_tree
    def test_create_geology_tree(self, qtbot):
        parent = ProjectWindow()
        base_view = BaseView(parent=parent)

        # create the geology list
        base_view.create_geology_tree()

        # check if it is a widget and if it's visible
        assert base_view.GeologyTreeWidget.isWidgetType() is True
        assert base_view.GeologyTreeWidget.isVisible()

    @pytest.fixture
    # Testing create_topology_tree
    def test_create_topology_tree(self, qtbot):
        parent = ProjectWindow()
        base_view = BaseView(parent=parent)

        # create the topology tree
        base_view.create_topology_tree()

        # check if it is a widget
        assert base_view.TopologyTreeWidget.isWidgetType() is True

    @pytest.fixture
    # Testing create_xsections_tree
    def test_create_xsections_tree(self, qtbot):
        parent = ProjectWindow()
        base_view = BaseView(parent=parent)

        # create the x sections tree
        base_view.create_xsections_tree()

        # check if it is a widget
        assert base_view.XSectionTreeWidget.isWidgetType() is True

    @pytest.fixture
    # Testing create_boundary_list
    def test_create_boundary_list(self, qtbot):
        parent = ProjectWindow()
        base_view = BaseView(parent=parent)

        # create the boundary list
        base_view.create_boundary_list()

        # check if it is a widget
        assert base_view.BoundariesTableWidget.isWidgetType() is True

    @pytest.fixture
    # Testing create_mesh3d_list
    def test_create_mesh3d_list(self, qtbot):
        parent = ProjectWindow()
        base_view = BaseView(parent=parent)

        # create the mesh3d list
        base_view.create_mesh3d_list()

        # check if it is a widget
        assert base_view.Mesh3DTableWidget.isWidgetType() is True

    @pytest.fixture
    # Testing create_dom_list
    def test_create_dom_list(self, qtbot):
        parent = ProjectWindow()
        base_view = BaseView(parent=parent)

        # create the dom_list
        base_view.create_dom_list()

        # check if it is a widget
        assert base_view.DOMsTableWidget.isWidgetType() is True

    @pytest.fixture
    # Testing create_image_list
    def test_create_image_list(self, qtbot):
        parent = ProjectWindow()
        base_view = BaseView(parent=parent)

        # create the image_list
        base_view.create_dom_list()

        # check if it is a widget
        assert base_view.ImagesTableWidget.isWidgetType() is True

    @pytest.fixture
    # Testing create_well_tree
    def test_create_well_tree(self, qtbot):
        parent = ProjectWindow()
        base_view = BaseView(parent=parent)

        # create the well_tree
        base_view.create_well_tree()

        # check if it is a widget
        assert base_view.WellsTreeWidget.isWidgetType() is True

    @pytest.fixture
    # Testing create_fluids_tree
    def test_create_fluids_tree(self, qtbot):
        parent = ProjectWindow()
        base_view = BaseView(parent=parent)

        # create the fluids tree
        base_view.create_fluids_tree()

        # check if it is a widget
        assert base_view.FluidsTreeWidget.isWidgetType() is True

    @pytest.fixture
    # Testing create_fluids_topology_tree
    def test_create_fluids_topology_tree(self, qtbot):
        parent = ProjectWindow()
        base_view = BaseView(parent=parent)

        # create the fluids_topology_tree
        base_view.create_fluids_topology_tree()

        # check if it is a widget
        assert base_view.FluidsTopologyTreeWidget.isWidgetType() is True

    @pytest.fixture
    # Testing create_backgrounds_tree
    def test_create_backgrounds_tree(self, qtbot):
        parent = ProjectWindow()
        base_view = BaseView(parent=parent)

        # create the backgrounds tree
        base_view.create_backgrounds_tree()

        # check if it is a widget
        assert base_view.BackgroundsTreeWidget.isWidgetType() is True

    @pytest.fixture
    # Testing create_backgrounds_topology_tree
    def test_create_backgrounds_topology_tree(self, qtbot):
        parent = ProjectWindow()
        base_view = BaseView(parent=parent)

        # create the backgrounds topology tree
        base_view.create_backgrounds_topology_tree()

        # check if it is a widget
        assert base_view.BackgroundsTopologyTreeWidget.isWidgetType() is True


# Testing View3D class
class TestView3D:
    @pytest.fixture
    # Testing if view 3d is initialized and showed
    def test_show_canvas(self, qtbot):
        parent = ProjectWindow()
        view_3d = View3D(parent=parent)
        view_3d.show_qt_canvas()

        assert view_3d.isWindow() is True \
               and view_3d.isVisible() is True

    @pytest.fixture
    # Testing view 3d initialize_menu_tools
    def test_initialize_menu_tools(self, qtbot):
        parent = ProjectWindow()
        view_3d = View3D(parent=parent)

        view_3d.initialize_menu_tools()

        assert view_3d.menuBoreTraceVis.isWidgetType() is True
        assert view_3d.menuBoreTraceVis.isVisible() is True
        assert view_3d.actionBoreTrace.isVisible() is True

# Testing ViewStereoplot class
class TestViewStereoplot:
    @pytest.fixture
    # Testing if ViewStereoplot is initialized and showed
    def test_show_canvas(self, qtbot):
        parent = ProjectWindow()
        view_stereoplot = ViewStereoplot(parent=parent)
        view_stereoplot.show_qt_canvas()

        assert view_stereoplot.isWindow() is True \
               and view_stereoplot.isVisible() is True

    @pytest.fixture
    # Testing ViewStereoplot initialize_menu_tools
    def test_initialize_menu_tools(self, qtbot):
        parent = ProjectWindow()
        view_stereoplot = ViewStereoplot(parent=parent)

        view_stereoplot.initialize_menu_tools()

        assert view_stereoplot.actionContours.isVisible() is True
        assert view_stereoplot.actionSetPolar.isVisible() is True
        assert view_stereoplot.actionSetEq.isVisible() is True
        assert view_stereoplot.actionSetEquiare.isVisible() is True
        assert view_stereoplot.actionSetEquiang.isVisible() is True

    @pytest.fixture
    # Testing ViewStereoplot initialize_interactor
    def test_initialize_interactor(self, qtbot):
        parent = ProjectWindow()
        view_stereoplot = ViewStereoplot(parent=parent)

        view_stereoplot.initialize_interactor()

        assert isinstance(view_stereoplot.navi_toolbar, NavigationToolbar)


# Testing NewView2D class
class TestNewView2D:

    @pytest.fixture
    # Testing if NewView2D is initialized and showed
    def test_show_canvas(self, qtbot):
        parent = ProjectWindow()
        new_view_2d = NewView2D(parent=parent)
        new_view_2d.show_qt_canvas()

        assert new_view_2d.isWindow() is True \
               and new_view_2d.isVisible() is True

    @pytest.fixture
    # Testing NewView2D initialize_menu_tools
    def test_initialize_menu_tools(self, qtbot):
        parent = ProjectWindow()
        new_view_2d = NewView2D(parent=parent)

        # Start initialize_menu_tools
        new_view_2d.initialize_menu_tools()

        assert new_view_2d.drawLineButton.isVisible() is True
        assert new_view_2d.editLineButton.isVisible() is True
        assert new_view_2d.sortLineButton.isVisible() is True
        assert new_view_2d.moveLineButton.isVisible() is True
        assert new_view_2d.rotateLineButton.isVisible() is True
        assert new_view_2d.extendButton.isVisible() is True
        assert new_view_2d.splitLineByLineButton.isVisible() is True
        assert new_view_2d.splitLineByPointButton.isVisible() is True
        assert new_view_2d.mergeLineButton.isVisible() is True
        assert new_view_2d.snapLineButton.isVisible() is True
        assert new_view_2d.resampleDistanceButton.isVisible() is True
        assert new_view_2d.resampleNumberButton.isVisible() is True
        assert new_view_2d.simplifyButton.isVisible() is True
        assert new_view_2d.copyParallelButton.isVisible() is True
        assert new_view_2d.copyKinkButton.isVisible() is True
        assert new_view_2d.copySimilarButton.isVisible() is True
        assert new_view_2d.measureDistanceButton.isVisible() is True
        assert new_view_2d.cleanSectionButton.isVisible() is True


# Testing NewViewMap class
class TestNewViewMap:
    @pytest.fixture
    # Testing if NewViewMap is initialized and showed
    def test_show_canvas(self, qtbot):
        parent = ProjectWindow()
        new_view_map = NewViewMap(parent=parent)
        new_view_map.show_qt_canvas()

        assert new_view_map.isWindow() is True \
               and new_view_map.isVisible() is True

    # @pytest.fixture
    # Testing NewViewMap initialize_menu_tools
    @pytest.mark.skipif(reason="NewView2D object has no attribute sectionFromAzimuthButton")
    def test_initialize_menu_tools(self, qtbot):
        parent = ProjectWindow()
        new_view_map = NewView2D(parent=parent)

        # Start initialize_menu_tools
        new_view_map.initialize_menu_tools()

        assert new_view_map.sectionFromAzimuthButton.isVisible() is True
        assert new_view_map.sectionFromFileButton.isVisible() is True
        assert new_view_map.boundaryFromPointsButton.isVisible() is True

