# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'base_view_windowzJsVhk.ui'
##
## Created by: Qt User Interface Compiler version 6.9.0
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
from PySide6.QtWidgets import (QApplication, QFrame, QMainWindow, QMenu,
    QMenuBar, QSizePolicy, QSplitter, QStatusBar,
    QToolBox, QVBoxLayout, QWidget)

class Ui_BaseViewWindow(object):
    def setupUi(self, BaseViewWindow):
        if not BaseViewWindow.objectName():
            BaseViewWindow.setObjectName(u"BaseViewWindow")
        BaseViewWindow.resize(800, 600)
        self.centralwidget = QWidget(BaseViewWindow)
        self.centralwidget.setObjectName(u"centralwidget")
        self.verticalLayout = QVBoxLayout(self.centralwidget)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.splitter = QSplitter(self.centralwidget)
        self.splitter.setObjectName(u"splitter")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.splitter.sizePolicy().hasHeightForWidth())
        self.splitter.setSizePolicy(sizePolicy)
        self.splitter.setOrientation(Qt.Orientation.Horizontal)
        self.ViewFrame = QFrame(self.splitter)
        self.ViewFrame.setObjectName(u"ViewFrame")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        sizePolicy1.setHorizontalStretch(3)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.ViewFrame.sizePolicy().hasHeightForWidth())
        self.ViewFrame.setSizePolicy(sizePolicy1)
        self.ViewFrame.setFrameShape(QFrame.Shape.StyledPanel)
        self.ViewFrame.setFrameShadow(QFrame.Shadow.Raised)
        self.verticalLayout_15 = QVBoxLayout(self.ViewFrame)
        self.verticalLayout_15.setObjectName(u"verticalLayout_15")
        self.ViewFrameLayout = QVBoxLayout()
        self.ViewFrameLayout.setObjectName(u"ViewFrameLayout")

        self.verticalLayout_15.addLayout(self.ViewFrameLayout)

        self.splitter.addWidget(self.ViewFrame)
        self.toolBox = QToolBox(self.splitter)
        self.toolBox.setObjectName(u"toolBox")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        sizePolicy2.setHorizontalStretch(1)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.toolBox.sizePolicy().hasHeightForWidth())
        self.toolBox.setSizePolicy(sizePolicy2)
        self.GeologyTreePage = QWidget()
        self.GeologyTreePage.setObjectName(u"GeologyTreePage")
        self.GeologyTreePage.setGeometry(QRect(0, 0, 470, 258))
        self.GeologyTreeLayout = QVBoxLayout(self.GeologyTreePage)
        self.GeologyTreeLayout.setObjectName(u"GeologyTreeLayout")
        self.toolBox.addItem(self.GeologyTreePage, u"Geology")
        self.FluidsTreePage = QWidget()
        self.FluidsTreePage.setObjectName(u"FluidsTreePage")
        self.FluidsTreePage.setGeometry(QRect(0, 0, 470, 258))
        self.FluidsTreeLayout = QVBoxLayout(self.FluidsTreePage)
        self.FluidsTreeLayout.setObjectName(u"FluidsTreeLayout")
        self.toolBox.addItem(self.FluidsTreePage, u"Fluids")
        self.BackgroundsTreePage = QWidget()
        self.BackgroundsTreePage.setObjectName(u"BackgroundsTreePage")
        self.BackgroundsTreePage.setGeometry(QRect(0, 0, 470, 258))
        self.BackgroundsTreeLayout = QVBoxLayout(self.BackgroundsTreePage)
        self.BackgroundsTreeLayout.setObjectName(u"BackgroundsTreeLayout")
        self.toolBox.addItem(self.BackgroundsTreePage, u"Background")
        self.DOMsTreePage = QWidget()
        self.DOMsTreePage.setObjectName(u"DOMsTreePage")
        self.DOMsTreePage.setGeometry(QRect(0, 0, 470, 258))
        self.DOMsTreeLayout = QVBoxLayout(self.DOMsTreePage)
        self.DOMsTreeLayout.setObjectName(u"DOMsTreeLayout")
        self.toolBox.addItem(self.DOMsTreePage, u"DEMs and DOMs")
        self.ImagesTreePage = QWidget()
        self.ImagesTreePage.setObjectName(u"ImagesTreePage")
        self.ImagesTreePage.setGeometry(QRect(0, 0, 470, 258))
        self.ImagesTreeLayout = QVBoxLayout(self.ImagesTreePage)
        self.ImagesTreeLayout.setObjectName(u"ImagesTreeLayout")
        self.toolBox.addItem(self.ImagesTreePage, u"Images")
        self.Mesh3DTreePage = QWidget()
        self.Mesh3DTreePage.setObjectName(u"Mesh3DTreePage")
        self.Mesh3DTreePage.setGeometry(QRect(0, 0, 470, 258))
        self.Mesh3DTreeLayout = QVBoxLayout(self.Mesh3DTreePage)
        self.Mesh3DTreeLayout.setObjectName(u"Mesh3DTreeLayout")
        self.toolBox.addItem(self.Mesh3DTreePage, u"Meshes and Grids")
        self.BoundariesTreePage = QWidget()
        self.BoundariesTreePage.setObjectName(u"BoundariesTreePage")
        self.BoundariesTreePage.setGeometry(QRect(0, 0, 470, 258))
        self.BoundariesTreeLayout = QVBoxLayout(self.BoundariesTreePage)
        self.BoundariesTreeLayout.setObjectName(u"BoundariesTreeLayout")
        self.toolBox.addItem(self.BoundariesTreePage, u"Boundaries")
        self.XSectionTreePage = QWidget()
        self.XSectionTreePage.setObjectName(u"XSectionTreePage")
        self.XSectionTreePage.setGeometry(QRect(0, 0, 470, 258))
        self.XSectionTreeLayout = QVBoxLayout(self.XSectionTreePage)
        self.XSectionTreeLayout.setObjectName(u"XSectionTreeLayout")
        self.toolBox.addItem(self.XSectionTreePage, u"X Sections")
        self.WellsTreePage = QWidget()
        self.WellsTreePage.setObjectName(u"WellsTreePage")
        self.WellsTreePage.setGeometry(QRect(0, 0, 470, 258))
        self.WellsTreeLayout = QVBoxLayout(self.WellsTreePage)
        self.WellsTreeLayout.setObjectName(u"WellsTreeLayout")
        self.toolBox.addItem(self.WellsTreePage, u"Wells")
        self.splitter.addWidget(self.toolBox)

        self.verticalLayout.addWidget(self.splitter)

        BaseViewWindow.setCentralWidget(self.centralwidget)
        self.menubar = QMenuBar(BaseViewWindow)
        self.menubar.setObjectName(u"menubar")
        self.menubar.setGeometry(QRect(0, 0, 800, 33))
        self.menubar.setNativeMenuBar(False)
        self.menuView = QMenu(self.menubar)
        self.menuView.setObjectName(u"menuView")
        self.menuView.setTearOffEnabled(True)
        self.menuSelect = QMenu(self.menubar)
        self.menuSelect.setObjectName(u"menuSelect")
        self.menuSelect.setTearOffEnabled(True)
        self.menuCreate = QMenu(self.menubar)
        self.menuCreate.setObjectName(u"menuCreate")
        self.menuCreate.setTearOffEnabled(True)
        self.menuModify = QMenu(self.menubar)
        self.menuModify.setObjectName(u"menuModify")
        self.menuModify.setTearOffEnabled(True)
        self.menuAnalysis = QMenu(self.menubar)
        self.menuAnalysis.setObjectName(u"menuAnalysis")
        self.menuAnalysis.setTearOffEnabled(True)
        BaseViewWindow.setMenuBar(self.menubar)
        self.statusbar = QStatusBar(BaseViewWindow)
        self.statusbar.setObjectName(u"statusbar")
        BaseViewWindow.setStatusBar(self.statusbar)

        self.menubar.addAction(self.menuView.menuAction())
        self.menubar.addAction(self.menuSelect.menuAction())
        self.menubar.addAction(self.menuCreate.menuAction())
        self.menubar.addAction(self.menuModify.menuAction())
        self.menubar.addAction(self.menuAnalysis.menuAction())

        self.retranslateUi(BaseViewWindow)

        self.toolBox.setCurrentIndex(0)


        QMetaObject.connectSlotsByName(BaseViewWindow)
    # setupUi

    def retranslateUi(self, BaseViewWindow):
        BaseViewWindow.setWindowTitle(QCoreApplication.translate("BaseViewWindow", u"MainWindow", None))
        self.toolBox.setItemText(self.toolBox.indexOf(self.GeologyTreePage), QCoreApplication.translate("BaseViewWindow", u"Geology", None))
        self.toolBox.setItemText(self.toolBox.indexOf(self.FluidsTreePage), QCoreApplication.translate("BaseViewWindow", u"Fluids", None))
        self.toolBox.setItemText(self.toolBox.indexOf(self.BackgroundsTreePage), QCoreApplication.translate("BaseViewWindow", u"Background", None))
        self.toolBox.setItemText(self.toolBox.indexOf(self.DOMsTreePage), QCoreApplication.translate("BaseViewWindow", u"DEMs and DOMs", None))
        self.toolBox.setItemText(self.toolBox.indexOf(self.ImagesTreePage), QCoreApplication.translate("BaseViewWindow", u"Images", None))
        self.toolBox.setItemText(self.toolBox.indexOf(self.Mesh3DTreePage), QCoreApplication.translate("BaseViewWindow", u"Meshes and Grids", None))
        self.toolBox.setItemText(self.toolBox.indexOf(self.BoundariesTreePage), QCoreApplication.translate("BaseViewWindow", u"Boundaries", None))
        self.toolBox.setItemText(self.toolBox.indexOf(self.XSectionTreePage), QCoreApplication.translate("BaseViewWindow", u"X Sections", None))
        self.toolBox.setItemText(self.toolBox.indexOf(self.WellsTreePage), QCoreApplication.translate("BaseViewWindow", u"Wells", None))
        self.menuView.setTitle(QCoreApplication.translate("BaseViewWindow", u"View", None))
        self.menuSelect.setTitle(QCoreApplication.translate("BaseViewWindow", u"Select", None))
        self.menuCreate.setTitle(QCoreApplication.translate("BaseViewWindow", u"Create", None))
        self.menuModify.setTitle(QCoreApplication.translate("BaseViewWindow", u"Modify", None))
        self.menuAnalysis.setTitle(QCoreApplication.translate("BaseViewWindow", u"Analysis", None))
    # retranslateUi

