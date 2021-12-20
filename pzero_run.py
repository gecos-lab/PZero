import sys
from PyQt5.QtWidgets import QApplication

from pzero.project_window import ProjectWindow

app = QApplication(sys.argv)
project_window = ProjectWindow()
project_window.show()
sys.exit(app.exec_())
