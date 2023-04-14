from sys import argv, exit
from PyQt5.QtWidgets import QApplication
import traceback
from pzero.project_window import ProjectWindow
import sys

import logging as log

def excepthook(exc_type, exc_value, exc_tb):
    """ Catch exceptions raised in QApplication.exec_()
    https: // stackoverflow.com / questions / 55819330 / catching - exceptions - raised - in -qapplication
    """

    tb = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    log.error("error catched!:")
    log.error("error message:\n", tb)
    raise Exception(tb)
    QApplication.quit()
    # or QtWidgets.QApplication.exit(0)


sys.excepthook = excepthook

def run_pzero():
    app = QApplication(argv)
    project_window = ProjectWindow()
    project_window.show()
    exit(app.exec_())


if __name__ =="__main__":
    run_pzero()