from sys import argv, exit
from PyQt5.QtWidgets import QApplication

from pzero.project_window import ProjectWindow


def run_pzero():
    app = QApplication(argv)
    project_window = ProjectWindow()
    project_window.show()
    exit(app.exec_())


if __name__ =="__main__":
    run_pzero()