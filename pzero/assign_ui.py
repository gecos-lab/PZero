# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'assign_data.ui'
#
# Created by: PyQt5 UI code generator 5.9.2
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_AssignWindow(object):
    def setupUi(self, AssignWindow):
        AssignWindow.setObjectName("AssignWindow")
        AssignWindow.resize(450, 620)
        self.AssignLayout = QtWidgets.QWidget(AssignWindow)
        self.AssignLayout.setObjectName("AssignLayout")
        self.verticalLayout_2 = QtWidgets.QVBoxLayout(self.AssignLayout)
        self.verticalLayout_2.setObjectName("verticalLayout_2")
        self.AssignTable = QtWidgets.QTableWidget(self.AssignLayout)
        self.AssignTable.setObjectName("AssignTable")
        self.AssignTable.setColumnCount(0)
        self.AssignTable.setRowCount(0)
        self.AssignTable.verticalHeader().setVisible(False)
        self.verticalLayout_2.addWidget(self.AssignTable)
        self.ConfirmButton = QtWidgets.QDialogButtonBox(self.AssignLayout)
        self.ConfirmButton.setStandardButtons(QtWidgets.QDialogButtonBox.Close|QtWidgets.QDialogButtonBox.Ok)
        self.ConfirmButton.setCenterButtons(True)
        self.ConfirmButton.setObjectName("ConfirmButton")
        self.verticalLayout_2.addWidget(self.ConfirmButton)
        AssignWindow.setCentralWidget(self.AssignLayout)

        self.retranslateUi(AssignWindow)
        QtCore.QMetaObject.connectSlotsByName(AssignWindow)

    def retranslateUi(self, AssignWindow):
        _translate = QtCore.QCoreApplication.translate
        AssignWindow.setWindowTitle(_translate("AssignWindow", "Assign data"))
