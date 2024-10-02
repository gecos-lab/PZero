"""pzero.py
PZero© Andrea Bistacchi"""

from sys import argv, exit

from PySide6.QtWidgets import QApplication

from PySide6.QtCore import Qt

if hasattr(Qt, 'AA_EnableHighDpiScaling'):
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)

if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)


from pzero.project_window import ProjectWindow

app = QApplication(argv)
project_window = ProjectWindow()
project_window.show()
exit(app.exec_())
