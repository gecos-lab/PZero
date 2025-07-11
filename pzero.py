"""pzero.py
PZero© Andrea Bistacchi"""

from sys import argv, exit, platform

from PySide6.QtWidgets import QApplication, QSplashScreen
from PySide6.QtGui import QPixmap

# from PySide6.QtCore import Qt

# if hasattr(Qt, 'AA_EnableHighDpiScaling'):
#     QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
#
# if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
#     QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

# Start Qt application
app = QApplication(argv)

# Use Fusion style: this is a uniform style for all platforms, but the
# real reason to use it is that the standard Windows 11 style has some bug
# in Qt 6.7.2, including one related to tear-off submenus.
# if platform == 'darwin':
# elif platform == 'win32':
# elif platform == 'linux':
app.setStyle("Fusion")
# app.setStyle('windows11')
# app.setStyle('windowsvista')
# app.setStyle('windows')

# Display splash screen before doing anything else
splash_image = QPixmap("./images/pzero_splash.jpg")
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
