from sys import argv, exit
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QIcon

from pzero.project_window import ProjectWindow

"""Paths"""
icon_path = "icons/dip.png"
style_path = "style/dark_teal.qss"

app = QApplication(argv)
project_window = ProjectWindow()

"""Set PZero icon"""
project_window.setWindowIcon(QIcon(icon_path))

"""Set styling"""
with open(style_path, "r") as style_file:
    project_window.setStyleSheet(style_file.read())

"""Show the project window"""
project_window.show()

exit(app.exec_())
