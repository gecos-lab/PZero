# import time
from pytest import raises

from pzero.project_window import ProjectWindow

from PyQt5.QtGui import QCloseEvent, QShowEvent
from PyQt5.QtCore import Qt, QEvent
from PyQt5.QtWidgets import QWidget, QMessageBox, QApplication, QMainWindow


# Click yes on the dialog box
def handle_dialog_yes(qtbot, window):
    # Get the message box for saving the project and the no_button
    messagebox = window.findChild(QMessageBox)
    # messagebox = QApplication.activeWindow()
    print(messagebox)
    yes_button = messagebox.button(QMessageBox.Yes)

    # Close PZero
    qtbot.mouseClick(yes_button, Qt.LeftButton)


# Click no on the dialog box
def handle_dialog_no(qtbot, window):
    # Get the message box for closing the project and the yes_button
    messagebox = window.findChild(QMessageBox)
    # messagebox = QApplication.activeWindow()
    print(messagebox)
    no_button = messagebox.button(QMessageBox.No)

    # Don't save the project
    qtbot.mouseClick(no_button, Qt.LeftButton)


# Class for testing the project window, qtbot part of a plugin of pytestQt
class TestProjectWindow:

    def ignore(self):
        return

    def test_is_window(self, qtbot):
        project_window = ProjectWindow()
        project_window.show()

        print(project_window.isWindow())

        assert project_window.isWindow() == True

    def test_window_name(self, qtbot):
        project_window = ProjectWindow()
        project_window.show()

        assert project_window.windowTitle() == "PZero"

    def test_shown_table(self, qtbot):
        project_window = ProjectWindow()
        project_window.show()

        shown_table = project_window.shown_table
        # print(shown_table)

        assert shown_table == 'tabGeology'

    def test_shown_table_change(self, qtbot):
        project_window = ProjectWindow()
        project_window.show()

        tabImg = 'tabImages'
        # tabGeol = 'tabGeology'

        pageImg = project_window.tabCentral.findChild(QWidget, tabImg)
        # pageGeol = project_window.tabCentral.findChild(QWidget, tabGeol)

        project_window.tabCentral.setCurrentWidget(pageImg)
        shown_table = project_window.shown_table
        # print(shown_table)

        assert shown_table == tabImg

    def test_shown_table_change(self, qtbot):
        project_window = ProjectWindow()
        project_window.show()

        tabImg = 'tabImages'
        # tabGeol = 'tabGeology'

        pageImg = project_window.tabCentral.findChild(QWidget, tabImg)
        # pageGeol = project_window.tabCentral.findChild(QWidget, tabGeol)

        project_window.tabCentral.setCurrentWidget(pageImg)
        shown_table = project_window.shown_table
        # print(shown_table)

        assert shown_table == tabImg

    def test_shown_table_change(self, qtbot):
        project_window = ProjectWindow()
        project_window.show()

        tab_img = 'tabImages'
        # tabGeol = 'tabGeology'

        page_img = project_window.tabCentral.findChild(QWidget, tab_img)
        # pageGeol = project_window.tabCentral.findChild(QWidget, tabGeol)

        project_window.tabCentral.setCurrentWidget(page_img)
        shown_table = project_window.shown_table
        # print(shown_table)

        assert shown_table == tab_img



        """
    # TO FIX
    # Testing the close event
    def test_close_event(self, qtbot):

        # setting the projectWindow
        project_window = ProjectWindow()
        project_window.show()

        # call the close event
        project_window.closeEvent(event=self)

        handle_dialog_no(qtbot, project_window)
        handle_dialog_yes(qtbot, project_window)

        #assert project_window.closeEvent == QEvent.accept()
    """
