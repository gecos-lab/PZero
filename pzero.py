"""pzero.py
PZero© Andrea Bistacchi"""

from sys import argv, exit

from PySide6.QtWidgets import QApplication, QSplashScreen
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt

# if hasattr(Qt, 'AA_EnableHighDpiScaling'):
#     QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
#
# if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
#     QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

# Start Qt application
app = QApplication(argv)

# Display splash screen before doing anything else
splash_image = QPixmap("./images/splash_image.jpg")
splash = QSplashScreen(splash_image)
splash.show()

# Load all libraries
from pzero.project_window import ProjectWindow

# Create project window and project
project_window = ProjectWindow()

# Show project window and close splash screen
project_window.show()
splash.finish(project_window)

# This is to clean everything when exiting
exit(app.exec_())
