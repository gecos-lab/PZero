"""pzero.py
PZero© Andrea Bistacchi"""

from sys import argv, exit, platform

from PySide6.QtWidgets import QApplication, QSplashScreen
from PySide6.QtGui import QIcon, QPixmap

# Resolve images relative to the source checkout or packaged application.
from pzero.helpers.resources import resource_path

# from PySide6.QtCore import Qt

# if hasattr(Qt, 'AA_EnableHighDpiScaling'):
#     QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
#
# if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
#     QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

# Start Qt application
app = QApplication(argv)
# set application icon for ico if available
icon_path = resource_path("_internal/pzero.ico")
app.setWindowIcon(QIcon(icon_path))

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
splash_image = QPixmap(resource_path("_internal/pzero_splash.png"))
splash = QSplashScreen(splash_image)
splash.show()

# Load all libraries
from pzero.project_window import ProjectWindow
from pzero.helpers.update_checker import check_for_updates

# Create project window and project
project_window = ProjectWindow()

# Show project window and close splash screen
project_window.show()
splash.finish(project_window)

# Check packaged releases for updates after startup, without blocking the UI.
# Keep the checker alive for its asynchronous network request and update dialog.
project_window.update_checker = check_for_updates(project_window)

# This is to clean everything when exiting
exit(app.exec_())
