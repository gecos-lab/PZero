from sys import argv, exit
from PyQt5.QtWidgets import QApplication

from pzero.project_window import ProjectWindow

app = QApplication(argv)
project_window = ProjectWindow()
project_window.show()
exit(app.exec_())
