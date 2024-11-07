# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'base_view_windowynxPCC.ui'
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
from PySide6.QtWidgets import (QApplication, QFrame, QHeaderView, QMainWindow,
    QMenu, QMenuBar, QSizePolicy, QSplitter,
    QStatusBar, QTableWidget, QTableWidgetItem, QToolBox,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

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
        self.GeologyTreePage.setGeometry(QRect(0, 0, 431, 168))
        self.verticalLayout_2 = QVBoxLayout(self.GeologyTreePage)
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.GeologyTreeWidget = QTreeWidget(self.GeologyTreePage)
        __qtreewidgetitem = QTreeWidgetItem()
        __qtreewidgetitem.setText(0, u"1");
        self.GeologyTreeWidget.setHeaderItem(__qtreewidgetitem)
        self.GeologyTreeWidget.setObjectName(u"GeologyTreeWidget")

        self.verticalLayout_2.addWidget(self.GeologyTreeWidget)

        self.toolBox.addItem(self.GeologyTreePage, u"Geology > Geology")
        self.GeologyTopologyTreePage = QWidget()
        self.GeologyTopologyTreePage.setObjectName(u"GeologyTopologyTreePage")
        self.GeologyTopologyTreePage.setGeometry(QRect(0, 0, 431, 168))
        self.verticalLayout_3 = QVBoxLayout(self.GeologyTopologyTreePage)
        self.verticalLayout_3.setObjectName(u"verticalLayout_3")
        self.GeologyTopologyTreeWidget = QTreeWidget(self.GeologyTopologyTreePage)
        __qtreewidgetitem1 = QTreeWidgetItem()
        __qtreewidgetitem1.setText(0, u"1");
        self.GeologyTopologyTreeWidget.setHeaderItem(__qtreewidgetitem1)
        self.GeologyTopologyTreeWidget.setObjectName(u"GeologyTopologyTreeWidget")

        self.verticalLayout_3.addWidget(self.GeologyTopologyTreeWidget)

        self.toolBox.addItem(self.GeologyTopologyTreePage, u"Geology > Topology")
        self.FluidsTreePage = QWidget()
        self.FluidsTreePage.setObjectName(u"FluidsTreePage")
        self.FluidsTreePage.setGeometry(QRect(0, 0, 431, 168))
        self.verticalLayout_4 = QVBoxLayout(self.FluidsTreePage)
        self.verticalLayout_4.setObjectName(u"verticalLayout_4")
        self.FluidsTreeWidget = QTreeWidget(self.FluidsTreePage)
        __qtreewidgetitem2 = QTreeWidgetItem()
        __qtreewidgetitem2.setText(0, u"1");
        self.FluidsTreeWidget.setHeaderItem(__qtreewidgetitem2)
        self.FluidsTreeWidget.setObjectName(u"FluidsTreeWidget")

        self.verticalLayout_4.addWidget(self.FluidsTreeWidget)

        self.toolBox.addItem(self.FluidsTreePage, u"Fluids > Fluids")
        self.FluidsTopologyTreePage = QWidget()
        self.FluidsTopologyTreePage.setObjectName(u"FluidsTopologyTreePage")
        self.FluidsTopologyTreePage.setGeometry(QRect(0, 0, 431, 168))
        self.verticalLayout_5 = QVBoxLayout(self.FluidsTopologyTreePage)
        self.verticalLayout_5.setObjectName(u"verticalLayout_5")
        self.FluidsTopologyTreeWidget = QTreeWidget(self.FluidsTopologyTreePage)
        __qtreewidgetitem3 = QTreeWidgetItem()
        __qtreewidgetitem3.setText(0, u"1");
        self.FluidsTopologyTreeWidget.setHeaderItem(__qtreewidgetitem3)
        self.FluidsTopologyTreeWidget.setObjectName(u"FluidsTopologyTreeWidget")

        self.verticalLayout_5.addWidget(self.FluidsTopologyTreeWidget)

        self.toolBox.addItem(self.FluidsTopologyTreePage, u"Fluids > Topology")
        self.BackgroundsTreePage = QWidget()
        self.BackgroundsTreePage.setObjectName(u"BackgroundsTreePage")
        self.BackgroundsTreePage.setGeometry(QRect(0, 0, 431, 168))
        self.verticalLayout_6 = QVBoxLayout(self.BackgroundsTreePage)
        self.verticalLayout_6.setObjectName(u"verticalLayout_6")
        self.BackgroundsTreeWidget = QTreeWidget(self.BackgroundsTreePage)
        __qtreewidgetitem4 = QTreeWidgetItem()
        __qtreewidgetitem4.setText(0, u"1");
        self.BackgroundsTreeWidget.setHeaderItem(__qtreewidgetitem4)
        self.BackgroundsTreeWidget.setObjectName(u"BackgroundsTreeWidget")

        self.verticalLayout_6.addWidget(self.BackgroundsTreeWidget)

        self.toolBox.addItem(self.BackgroundsTreePage, u"Background > Background")
        self.BackgroundsTopologyTreePage = QWidget()
        self.BackgroundsTopologyTreePage.setObjectName(u"BackgroundsTopologyTreePage")
        self.BackgroundsTopologyTreePage.setGeometry(QRect(0, 0, 431, 168))
        self.verticalLayout_7 = QVBoxLayout(self.BackgroundsTopologyTreePage)
        self.verticalLayout_7.setObjectName(u"verticalLayout_7")
        self.BackgroundsTopologyTreeWidget = QTreeWidget(self.BackgroundsTopologyTreePage)
        __qtreewidgetitem5 = QTreeWidgetItem()
        __qtreewidgetitem5.setText(0, u"1");
        self.BackgroundsTopologyTreeWidget.setHeaderItem(__qtreewidgetitem5)
        self.BackgroundsTopologyTreeWidget.setObjectName(u"BackgroundsTopologyTreeWidget")

        self.verticalLayout_7.addWidget(self.BackgroundsTopologyTreeWidget)

        self.toolBox.addItem(self.BackgroundsTopologyTreePage, u"Background > Topology")
        self.DOMsTablePage = QWidget()
        self.DOMsTablePage.setObjectName(u"DOMsTablePage")
        self.DOMsTablePage.setGeometry(QRect(0, 0, 431, 168))
        self.verticalLayout_8 = QVBoxLayout(self.DOMsTablePage)
        self.verticalLayout_8.setObjectName(u"verticalLayout_8")
        self.DOMsTableWidget = QTableWidget(self.DOMsTablePage)
        self.DOMsTableWidget.setObjectName(u"DOMsTableWidget")

        self.verticalLayout_8.addWidget(self.DOMsTableWidget)

        self.toolBox.addItem(self.DOMsTablePage, u"DEMs and DOMs")
        self.ImagesTablePage = QWidget()
        self.ImagesTablePage.setObjectName(u"ImagesTablePage")
        self.ImagesTablePage.setGeometry(QRect(0, 0, 431, 168))
        self.verticalLayout_9 = QVBoxLayout(self.ImagesTablePage)
        self.verticalLayout_9.setObjectName(u"verticalLayout_9")
        self.ImagesTableWidget = QTableWidget(self.ImagesTablePage)
        self.ImagesTableWidget.setObjectName(u"ImagesTableWidget")

        self.verticalLayout_9.addWidget(self.ImagesTableWidget)

        self.toolBox.addItem(self.ImagesTablePage, u"Images")
        self.Mesh3DTablePage = QWidget()
        self.Mesh3DTablePage.setObjectName(u"Mesh3DTablePage")
        self.Mesh3DTablePage.setGeometry(QRect(0, 0, 431, 168))
        self.verticalLayout_10 = QVBoxLayout(self.Mesh3DTablePage)
        self.verticalLayout_10.setObjectName(u"verticalLayout_10")
        self.Mesh3DTableWidget = QTableWidget(self.Mesh3DTablePage)
        self.Mesh3DTableWidget.setObjectName(u"Mesh3DTableWidget")

        self.verticalLayout_10.addWidget(self.Mesh3DTableWidget)

        self.toolBox.addItem(self.Mesh3DTablePage, u"Meshes and Grids")
        self.BoundariesTablePage = QWidget()
        self.BoundariesTablePage.setObjectName(u"BoundariesTablePage")
        self.BoundariesTablePage.setGeometry(QRect(0, 0, 431, 168))
        self.verticalLayout_11 = QVBoxLayout(self.BoundariesTablePage)
        self.verticalLayout_11.setObjectName(u"verticalLayout_11")
        self.BoundariesTableWidget = QTableWidget(self.BoundariesTablePage)
        self.BoundariesTableWidget.setObjectName(u"BoundariesTableWidget")

        self.verticalLayout_11.addWidget(self.BoundariesTableWidget)

        self.toolBox.addItem(self.BoundariesTablePage, u"Boundaries")
        self.XSectionTreePage = QWidget()
        self.XSectionTreePage.setObjectName(u"XSectionTreePage")
        self.XSectionTreePage.setGeometry(QRect(0, 0, 431, 168))
        self.verticalLayout_12 = QVBoxLayout(self.XSectionTreePage)
        self.verticalLayout_12.setObjectName(u"verticalLayout_12")
        self.XSectionTreeWidget = QTreeWidget(self.XSectionTreePage)
        __qtreewidgetitem6 = QTreeWidgetItem()
        __qtreewidgetitem6.setText(0, u"1");
        self.XSectionTreeWidget.setHeaderItem(__qtreewidgetitem6)
        self.XSectionTreeWidget.setObjectName(u"XSectionTreeWidget")

        self.verticalLayout_12.addWidget(self.XSectionTreeWidget)

        self.toolBox.addItem(self.XSectionTreePage, u"X Sections")
        self.WellsTreePage = QWidget()
        self.WellsTreePage.setObjectName(u"WellsTreePage")
        self.WellsTreePage.setGeometry(QRect(0, 0, 431, 168))
        self.verticalLayout_13 = QVBoxLayout(self.WellsTreePage)
        self.verticalLayout_13.setObjectName(u"verticalLayout_13")
        self.WellsTreeWidget = QTreeWidget(self.WellsTreePage)
        __qtreewidgetitem7 = QTreeWidgetItem()
        __qtreewidgetitem7.setText(0, u"1");
        self.WellsTreeWidget.setHeaderItem(__qtreewidgetitem7)
        self.WellsTreeWidget.setObjectName(u"WellsTreeWidget")

        self.verticalLayout_13.addWidget(self.WellsTreeWidget)

        self.toolBox.addItem(self.WellsTreePage, u"Wells")
        self.splitter.addWidget(self.toolBox)

        self.verticalLayout.addWidget(self.splitter)

        BaseViewWindow.setCentralWidget(self.centralwidget)
        self.menubar = QMenuBar(BaseViewWindow)
        self.menubar.setObjectName(u"menubar")
        self.menubar.setGeometry(QRect(0, 0, 800, 33))
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
        self.toolBox.setItemText(self.toolBox.indexOf(self.GeologyTreePage), QCoreApplication.translate("BaseViewWindow", u"Geology > Geology", None))
        self.toolBox.setItemText(self.toolBox.indexOf(self.GeologyTopologyTreePage), QCoreApplication.translate("BaseViewWindow", u"Geology > Topology", None))
        self.toolBox.setItemText(self.toolBox.indexOf(self.FluidsTreePage), QCoreApplication.translate("BaseViewWindow", u"Fluids > Fluids", None))
        self.toolBox.setItemText(self.toolBox.indexOf(self.FluidsTopologyTreePage), QCoreApplication.translate("BaseViewWindow", u"Fluids > Topology", None))
        self.toolBox.setItemText(self.toolBox.indexOf(self.BackgroundsTreePage), QCoreApplication.translate("BaseViewWindow", u"Background > Background", None))
        self.toolBox.setItemText(self.toolBox.indexOf(self.BackgroundsTopologyTreePage), QCoreApplication.translate("BaseViewWindow", u"Background > Topology", None))
        self.toolBox.setItemText(self.toolBox.indexOf(self.DOMsTablePage), QCoreApplication.translate("BaseViewWindow", u"DEMs and DOMs", None))
        self.toolBox.setItemText(self.toolBox.indexOf(self.ImagesTablePage), QCoreApplication.translate("BaseViewWindow", u"Images", None))
        self.toolBox.setItemText(self.toolBox.indexOf(self.Mesh3DTablePage), QCoreApplication.translate("BaseViewWindow", u"Meshes and Grids", None))
        self.toolBox.setItemText(self.toolBox.indexOf(self.BoundariesTablePage), QCoreApplication.translate("BaseViewWindow", u"Boundaries", None))
        self.toolBox.setItemText(self.toolBox.indexOf(self.XSectionTreePage), QCoreApplication.translate("BaseViewWindow", u"X Sections", None))
        self.toolBox.setItemText(self.toolBox.indexOf(self.WellsTreePage), QCoreApplication.translate("BaseViewWindow", u"Wells", None))
        self.menuView.setTitle(QCoreApplication.translate("BaseViewWindow", u"View", None))
        self.menuSelect.setTitle(QCoreApplication.translate("BaseViewWindow", u"Select", None))
        self.menuCreate.setTitle(QCoreApplication.translate("BaseViewWindow", u"Create", None))
        self.menuModify.setTitle(QCoreApplication.translate("BaseViewWindow", u"Modify", None))
        self.menuAnalysis.setTitle(QCoreApplication.translate("BaseViewWindow", u"Analysis", None))
    # retranslateUi

