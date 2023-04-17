# import time
from pytest import raises

from pzero.project_window import ProjectWindow

from PyQt5.QtGui import QCloseEvent
from PyQt5.QtCore import Qt, QEvent
from PyQt5.QtWidgets import QWidget, QMessageBox, QApplication, QMainWindow


# Click yes on the dialog box
def handle_dialog_yes(qtbot, window):
    # Get the message box for saving the project and the no_button
    messagebox = window.findChild(QMessageBox)
    # messagebox = QApplication.activeWindow()
    print(messagebox)
    no_button = messagebox.button(QMessageBox.No)

    # Don't save the project
    qtbot.mouseClick(no_button, Qt.LeftButton)


# Click no on the dialog box
def handle_dialog_no(qtbot, window):
    # Get the message box for closing the project and the yes_button
    messagebox = window.findChild(QMessageBox)
    # messagebox = QApplication.activeWindow()
    yes_button = messagebox.button(QMessageBox.Yes)

    # Close PZero
    qtbot.mouseClick(yes_button, Qt.LeftButton)


# Class for testing the project window, qtbot part of a plugin of pytestQt
class TestProjectWindow:

    def ignore(self):
        return

    # Testing the close event
    def test_close_event(self, qtbot):

        # setting the projectWindow
        project_window = ProjectWindow()
        project_window.show()

        # adding the window to qtbot allows to close properly after the execution test
        qtbot.addWidget(project_window)

        # call the close event
        project_window.closeEvent(event=self)

        handle_dialog_no(qtbot, project_window)
        handle_dialog_yes(qtbot, project_window)

        assert project_window.closeEvent == QEvent.accept()


