"""pzero.py
PZero© Andrea Bistacchi"""

"""Python imports"""
from sys import argv, exit

"""QT imports - we use PyQt5 and QtPy that in theory allows switching between different Qt versions"""
from os import environ
environ["QT_API"] = "pyqt5"
from qtpy.QtWidgets import QApplication

"""PZero imports"""
from pzero.project_window import ProjectWindow

app = QApplication(argv)
project_window = ProjectWindow()
project_window.show()
exit(app.exec_())
