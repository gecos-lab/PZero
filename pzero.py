from sys import argv, exit
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QIcon
from logging import exception
from pzero.project_window import ProjectWindow

"""Paths"""
icon_path = "icons/dip.png"
dark_style_path = "style/dark_teal.qss"
light_style_path = "style/light_teal.qss"

app = QApplication(argv)
project_window = ProjectWindow()

"""Set PZero icon"""
app.setWindowIcon(QIcon(icon_path))

try:
    """Set styling"""
    with open(dark_style_path, "r") as style_file:
        app.setStyleSheet(style_file.read())

except Exception as e:
    exception(e)

"""Show the project window"""
project_window.show()

exit(app.exec_())
