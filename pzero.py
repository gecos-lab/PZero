from sys import argv, exit
import os
os.environ["QT_API"] = "pyqt5"
from qtpy.QtWidgets import QApplication

from pzero.project_window import ProjectWindow

app = QApplication(argv)
project_window = ProjectWindow()
project_window.show()
exit(app.exec_())
