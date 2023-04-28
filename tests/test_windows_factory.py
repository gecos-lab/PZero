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

