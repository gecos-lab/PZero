# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'import_windowqGaNVX.ui'
##
## Created by: Qt User Interface Compiler version 6.7.3
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QAction, QBrush, QColor, QConicalGradient,
    QCursor, QFont, QFontDatabase, QGradient,
    QIcon, QImage, QKeySequence, QLinearGradient,
    QPainter, QPalette, QPixmap, QRadialGradient,
    QTransform)
from PySide6.QtWidgets import (QAbstractButton, QApplication, QComboBox, QDialogButtonBox,
    QFormLayout, QFrame, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QLayout, QLineEdit,
    QMainWindow, QPushButton, QSizePolicy, QSpinBox,
    QTableView, QTableWidget, QTableWidgetItem, QToolButton,
    QVBoxLayout, QWidget)

class Ui_ImportOptionsWindow(object):
    def setupUi(self, ImportOptionsWindow):
        if not ImportOptionsWindow.objectName():
            ImportOptionsWindow.setObjectName(u"ImportOptionsWindow")
        ImportOptionsWindow.resize(1082, 894)
        sizePolicy = QSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.MinimumExpanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(ImportOptionsWindow.sizePolicy().hasHeightForWidth())
        ImportOptionsWindow.setSizePolicy(sizePolicy)
        ImportOptionsWindow.setMinimumSize(QSize(900, 690))
        ImportOptionsWindow.setMaximumSize(QSize(16777215, 16777215))
        ImportOptionsWindow.setBaseSize(QSize(900, 600))
        self.actionImport = QAction(ImportOptionsWindow)
        self.actionImport.setObjectName(u"actionImport")
        self.centralwidget = QWidget(ImportOptionsWindow)
        self.centralwidget.setObjectName(u"centralwidget")
        self.centralwidget.setEnabled(True)
        sizePolicy.setHeightForWidth(self.centralwidget.sizePolicy().hasHeightForWidth())
        self.centralwidget.setSizePolicy(sizePolicy)
        self.centralwidget.setMinimumSize(QSize(900, 600))
        self.centralwidget.setMaximumSize(QSize(16777215, 16777215))
        self.centralwidget.setBaseSize(QSize(900, 600))
        self.centralwidget.setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)
        self.horizontalLayout = QHBoxLayout(self.centralwidget)
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.prevDataWidget = QWidget(self.centralwidget)
        self.prevDataWidget.setObjectName(u"prevDataWidget")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.prevDataWidget.sizePolicy().hasHeightForWidth())
        self.prevDataWidget.setSizePolicy(sizePolicy1)
        self.verticalLayout = QVBoxLayout(self.prevDataWidget)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.verticalLayout.setContentsMargins(-1, 0, 0, -1)
        self.dataPreviewLabel = QLabel(self.prevDataWidget)
        self.dataPreviewLabel.setObjectName(u"dataPreviewLabel")
        self.dataPreviewLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.verticalLayout.addWidget(self.dataPreviewLabel)

        self.dataView = QTableView(self.prevDataWidget)
        self.dataView.setObjectName(u"dataView")

        self.verticalLayout.addWidget(self.dataView)


        self.horizontalLayout.addWidget(self.prevDataWidget)

        self.AssignImportWidget = QWidget(self.centralwidget)
        self.AssignImportWidget.setObjectName(u"AssignImportWidget")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.AssignImportWidget.sizePolicy().hasHeightForWidth())
        self.AssignImportWidget.setSizePolicy(sizePolicy2)
        self.AssignImportV = QVBoxLayout(self.AssignImportWidget)
        self.AssignImportV.setObjectName(u"AssignImportV")
        self.AssignImportV.setContentsMargins(0, 0, -1, -1)
        self.dataAssignLabel = QLabel(self.AssignImportWidget)
        self.dataAssignLabel.setObjectName(u"dataAssignLabel")
        self.dataAssignLabel.setFrameShape(QFrame.Shape.NoFrame)
        self.dataAssignLabel.setFrameShadow(QFrame.Shadow.Plain)
        self.dataAssignLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.AssignImportV.addWidget(self.dataAssignLabel)

        self.AssignTable = QTableWidget(self.AssignImportWidget)
        self.AssignTable.setObjectName(u"AssignTable")
        sizePolicy2.setHeightForWidth(self.AssignTable.sizePolicy().hasHeightForWidth())
        self.AssignTable.setSizePolicy(sizePolicy2)
        self.AssignTable.horizontalHeader().setProperty(u"showSortIndicator", True)
        self.AssignTable.verticalHeader().setVisible(True)

        self.AssignImportV.addWidget(self.AssignTable)

        self.OptionsFrame = QFrame(self.AssignImportWidget)
        self.OptionsFrame.setObjectName(u"OptionsFrame")
        sizePolicy3 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sizePolicy3.setHorizontalStretch(0)
        sizePolicy3.setVerticalStretch(0)
        sizePolicy3.setHeightForWidth(self.OptionsFrame.sizePolicy().hasHeightForWidth())
        self.OptionsFrame.setSizePolicy(sizePolicy3)
        self.OptionsFrame.setBaseSize(QSize(0, 0))
        self.OptionsFrame.setFrameShape(QFrame.Shape.Box)
        self.OptionsLayout = QVBoxLayout(self.OptionsFrame)
        self.OptionsLayout.setObjectName(u"OptionsLayout")
        self.OptionsLabel = QLabel(self.OptionsFrame)
        self.OptionsLabel.setObjectName(u"OptionsLabel")
        sizePolicy4 = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        sizePolicy4.setHorizontalStretch(0)
        sizePolicy4.setVerticalStretch(0)
        sizePolicy4.setHeightForWidth(self.OptionsLabel.sizePolicy().hasHeightForWidth())
        self.OptionsLabel.setSizePolicy(sizePolicy4)

        self.OptionsLayout.addWidget(self.OptionsLabel)

        self.ImportGroupBox = QGroupBox(self.OptionsFrame)
        self.ImportGroupBox.setObjectName(u"ImportGroupBox")
        sizePolicy2.setHeightForWidth(self.ImportGroupBox.sizePolicy().hasHeightForWidth())
        self.ImportGroupBox.setSizePolicy(sizePolicy2)
        self.ImportGroupBox.setFlat(False)
        self.ImportGroupBox.setCheckable(False)
        self.horizontalLayout_3 = QHBoxLayout(self.ImportGroupBox)
        self.horizontalLayout_3.setSpacing(8)
        self.horizontalLayout_3.setObjectName(u"horizontalLayout_3")
        self.PathlineEdit = QLineEdit(self.ImportGroupBox)
        self.PathlineEdit.setObjectName(u"PathlineEdit")
        sizePolicy3.setHeightForWidth(self.PathlineEdit.sizePolicy().hasHeightForWidth())
        self.PathlineEdit.setSizePolicy(sizePolicy3)
        self.PathlineEdit.setMaxLength(32767)
        self.PathlineEdit.setClearButtonEnabled(False)

        self.horizontalLayout_3.addWidget(self.PathlineEdit)

        self.PathtoolButton = QToolButton(self.ImportGroupBox)
        self.PathtoolButton.setObjectName(u"PathtoolButton")

        self.horizontalLayout_3.addWidget(self.PathtoolButton)


        self.OptionsLayout.addWidget(self.ImportGroupBox)

        self.formLayout = QFormLayout()
        self.formLayout.setObjectName(u"formLayout")
        self.formLayout.setSizeConstraint(QLayout.SizeConstraint.SetDefaultConstraint)
        self.formLayout.setHorizontalSpacing(6)
        self.formLayout.setVerticalSpacing(30)
        self.formLayout.setContentsMargins(14, -1, 21, 6)
        self.StartOnLabel = QLabel(self.OptionsFrame)
        self.StartOnLabel.setObjectName(u"StartOnLabel")

        self.formLayout.setWidget(0, QFormLayout.LabelRole, self.StartOnLabel)

        self.StartRowspinBox = QSpinBox(self.OptionsFrame)
        self.StartRowspinBox.setObjectName(u"StartRowspinBox")
        self.StartRowspinBox.setValue(0)

        self.formLayout.setWidget(0, QFormLayout.FieldRole, self.StartRowspinBox)

        self.EndOnLabel = QLabel(self.OptionsFrame)
        self.EndOnLabel.setObjectName(u"EndOnLabel")

        self.formLayout.setWidget(1, QFormLayout.LabelRole, self.EndOnLabel)

        self.EndRowspinBox = QSpinBox(self.OptionsFrame)
        self.EndRowspinBox.setObjectName(u"EndRowspinBox")
        self.EndRowspinBox.setMinimum(-1)
        self.EndRowspinBox.setMaximum(2147483647)
        self.EndRowspinBox.setValue(100)

        self.formLayout.setWidget(1, QFormLayout.FieldRole, self.EndRowspinBox)

        self.SeparatoLabel = QLabel(self.OptionsFrame)
        self.SeparatoLabel.setObjectName(u"SeparatoLabel")

        self.formLayout.setWidget(2, QFormLayout.LabelRole, self.SeparatoLabel)

        self.SeparatorcomboBox = QComboBox(self.OptionsFrame)
        self.SeparatorcomboBox.addItem("")
        self.SeparatorcomboBox.addItem("")
        self.SeparatorcomboBox.addItem("")
        self.SeparatorcomboBox.addItem("")
        self.SeparatorcomboBox.setObjectName(u"SeparatorcomboBox")
        self.SeparatorcomboBox.setEditable(True)
        self.SeparatorcomboBox.setPlaceholderText(u"")

        self.formLayout.setWidget(2, QFormLayout.FieldRole, self.SeparatorcomboBox)


        self.OptionsLayout.addLayout(self.formLayout)

        self.gridWidget = QWidget(self.OptionsFrame)
        self.gridWidget.setObjectName(u"gridWidget")
        sizePolicy5 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        sizePolicy5.setHorizontalStretch(0)
        sizePolicy5.setVerticalStretch(0)
        sizePolicy5.setHeightForWidth(self.gridWidget.sizePolicy().hasHeightForWidth())
        self.gridWidget.setSizePolicy(sizePolicy5)
        self.horizontalLayout_4 = QHBoxLayout(self.gridWidget)
        self.horizontalLayout_4.setObjectName(u"horizontalLayout_4")
        self.PreviewButton = QPushButton(self.gridWidget)
        self.PreviewButton.setObjectName(u"PreviewButton")

        self.horizontalLayout_4.addWidget(self.PreviewButton)

        self.ConfirmBox = QDialogButtonBox(self.gridWidget)
        self.ConfirmBox.setObjectName(u"ConfirmBox")
        self.ConfirmBox.setOrientation(Qt.Orientation.Horizontal)
        self.ConfirmBox.setStandardButtons(QDialogButtonBox.StandardButton.Close|QDialogButtonBox.StandardButton.Ok)
        self.ConfirmBox.setCenterButtons(True)

        self.horizontalLayout_4.addWidget(self.ConfirmBox)


        self.OptionsLayout.addWidget(self.gridWidget)


        self.AssignImportV.addWidget(self.OptionsFrame)


        self.horizontalLayout.addWidget(self.AssignImportWidget)

        ImportOptionsWindow.setCentralWidget(self.centralwidget)

        self.retranslateUi(ImportOptionsWindow)

        QMetaObject.connectSlotsByName(ImportOptionsWindow)
    # setupUi

    def retranslateUi(self, ImportOptionsWindow):
        ImportOptionsWindow.setWindowTitle(QCoreApplication.translate("ImportOptionsWindow", u"Import options", None))
        self.actionImport.setText(QCoreApplication.translate("ImportOptionsWindow", u"Import", None))
        self.dataPreviewLabel.setText(QCoreApplication.translate("ImportOptionsWindow", u"Preview data table", None))
        self.dataAssignLabel.setText(QCoreApplication.translate("ImportOptionsWindow", u"Assign data table", None))
        self.OptionsLabel.setText(QCoreApplication.translate("ImportOptionsWindow", u"Import options", None))
        self.PathlineEdit.setPlaceholderText(QCoreApplication.translate("ImportOptionsWindow", u"file path...", None))
        self.PathtoolButton.setText(QCoreApplication.translate("ImportOptionsWindow", u"...", None))
        self.StartOnLabel.setText(QCoreApplication.translate("ImportOptionsWindow", u"Start from line", None))
        self.EndOnLabel.setText(QCoreApplication.translate("ImportOptionsWindow", u"End on line", None))
        self.SeparatoLabel.setText(QCoreApplication.translate("ImportOptionsWindow", u"Separator", None))
        self.SeparatorcomboBox.setItemText(0, QCoreApplication.translate("ImportOptionsWindow", u"<space>", None))
        self.SeparatorcomboBox.setItemText(1, QCoreApplication.translate("ImportOptionsWindow", u"<comma>", None))
        self.SeparatorcomboBox.setItemText(2, QCoreApplication.translate("ImportOptionsWindow", u"<semi-col>", None))
        self.SeparatorcomboBox.setItemText(3, QCoreApplication.translate("ImportOptionsWindow", u"<tab>", None))

        self.SeparatorcomboBox.setCurrentText(QCoreApplication.translate("ImportOptionsWindow", u"<space>", None))
        self.PreviewButton.setText(QCoreApplication.translate("ImportOptionsWindow", u"Preview", None))
    # retranslateUi

