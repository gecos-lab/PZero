# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'base_view_windowuOSSnC.ui'
##
## Created by: Qt User Interface Compiler version 6.7.3
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (
    QCoreApplication,
    QDate,
    QDateTime,
    QLocale,
    QMetaObject,
    QObject,
    QPoint,
    QRect,
    QSize,
    QTime,
    QUrl,
    Qt,
)
from PySide6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QConicalGradient,
    QCursor,
    QFont,
    QFontDatabase,
    QGradient,
    QIcon,
    QImage,
    QKeySequence,
    QLinearGradient,
    QPainter,
    QPalette,
    QPixmap,
    QRadialGradient,
    QTransform,
)
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHeaderView,
    QMainWindow,
    QMenu,
    QMenuBar,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QToolBox,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


class Ui_BaseViewWindow(object):
    def setupUi(self, BaseViewWindow):
        if not BaseViewWindow.objectName():
            BaseViewWindow.setObjectName("BaseViewWindow")
        BaseViewWindow.resize(800, 600)
        self.centralwidget = QWidget(BaseViewWindow)
        self.centralwidget.setObjectName("centralwidget")
        self.verticalLayout = QVBoxLayout(self.centralwidget)
        self.verticalLayout.setObjectName("verticalLayout")
        self.splitter = QSplitter(self.centralwidget)
        self.splitter.setObjectName("splitter")
        sizePolicy = QSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.splitter.sizePolicy().hasHeightForWidth())
        self.splitter.setSizePolicy(sizePolicy)
        self.splitter.setOrientation(Qt.Orientation.Horizontal)
        self.ViewFrame = QFrame(self.splitter)
        self.ViewFrame.setObjectName("ViewFrame")
        sizePolicy1 = QSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred
        )
        sizePolicy1.setHorizontalStretch(3)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.ViewFrame.sizePolicy().hasHeightForWidth())
        self.ViewFrame.setSizePolicy(sizePolicy1)
        self.ViewFrame.setFrameShape(QFrame.Shape.StyledPanel)
        self.ViewFrame.setFrameShadow(QFrame.Shadow.Raised)
        self.verticalLayout_15 = QVBoxLayout(self.ViewFrame)
        self.verticalLayout_15.setObjectName("verticalLayout_15")
        self.ViewFrameLayout = QVBoxLayout()
        self.ViewFrameLayout.setObjectName("ViewFrameLayout")

        self.verticalLayout_15.addLayout(self.ViewFrameLayout)

        self.splitter.addWidget(self.ViewFrame)
        self.toolBox = QToolBox(self.splitter)
        self.toolBox.setObjectName("toolBox")
        sizePolicy2 = QSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred
        )
        sizePolicy2.setHorizontalStretch(1)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.toolBox.sizePolicy().hasHeightForWidth())
        self.toolBox.setSizePolicy(sizePolicy2)
        self.GeologyTreePage = QWidget()
        self.GeologyTreePage.setObjectName("GeologyTreePage")
        self.GeologyTreePage.setGeometry(QRect(0, 0, 626, 168))
        self.verticalLayout_2 = QVBoxLayout(self.GeologyTreePage)
        self.verticalLayout_2.setObjectName("verticalLayout_2")
        self.GeologyTreeWidget = QTreeWidget(self.GeologyTreePage)
        __qtreewidgetitem = QTreeWidgetItem()
        __qtreewidgetitem.setText(0, "1")
        self.GeologyTreeWidget.setHeaderItem(__qtreewidgetitem)
        self.GeologyTreeWidget.setObjectName("GeologyTreeWidget")

        self.verticalLayout_2.addWidget(self.GeologyTreeWidget)

        self.toolBox.addItem(self.GeologyTreePage, "Geology > Geology")
        self.GeologyTopologyTreePage = QWidget()
        self.GeologyTopologyTreePage.setObjectName("GeologyTopologyTreePage")
        self.GeologyTopologyTreePage.setGeometry(QRect(0, 0, 626, 168))
        self.verticalLayout_3 = QVBoxLayout(self.GeologyTopologyTreePage)
        self.verticalLayout_3.setObjectName("verticalLayout_3")
        self.GeologyTopologyTreeWidget = QTreeWidget(self.GeologyTopologyTreePage)
        __qtreewidgetitem1 = QTreeWidgetItem()
        __qtreewidgetitem1.setText(0, "1")
        self.GeologyTopologyTreeWidget.setHeaderItem(__qtreewidgetitem1)
        self.GeologyTopologyTreeWidget.setObjectName("GeologyTopologyTreeWidget")

        self.verticalLayout_3.addWidget(self.GeologyTopologyTreeWidget)

        self.toolBox.addItem(self.GeologyTopologyTreePage, "Geology > Topology")
        self.FluidsTreePage = QWidget()
        self.FluidsTreePage.setObjectName("FluidsTreePage")
        self.FluidsTreePage.setGeometry(QRect(0, 0, 626, 168))
        self.verticalLayout_4 = QVBoxLayout(self.FluidsTreePage)
        self.verticalLayout_4.setObjectName("verticalLayout_4")
        self.FluidsTreeWidget = QTreeWidget(self.FluidsTreePage)
        __qtreewidgetitem2 = QTreeWidgetItem()
        __qtreewidgetitem2.setText(0, "1")
        self.FluidsTreeWidget.setHeaderItem(__qtreewidgetitem2)
        self.FluidsTreeWidget.setObjectName("FluidsTreeWidget")

        self.verticalLayout_4.addWidget(self.FluidsTreeWidget)

        self.toolBox.addItem(self.FluidsTreePage, "Fluids > Fluids")
        self.FluidsTopologyTreePage = QWidget()
        self.FluidsTopologyTreePage.setObjectName("FluidsTopologyTreePage")
        self.FluidsTopologyTreePage.setGeometry(QRect(0, 0, 626, 168))
        self.verticalLayout_5 = QVBoxLayout(self.FluidsTopologyTreePage)
        self.verticalLayout_5.setObjectName("verticalLayout_5")
        self.FluidsTopologyTreeWidget = QTreeWidget(self.FluidsTopologyTreePage)
        __qtreewidgetitem3 = QTreeWidgetItem()
        __qtreewidgetitem3.setText(0, "1")
        self.FluidsTopologyTreeWidget.setHeaderItem(__qtreewidgetitem3)
        self.FluidsTopologyTreeWidget.setObjectName("FluidsTopologyTreeWidget")

        self.verticalLayout_5.addWidget(self.FluidsTopologyTreeWidget)

        self.toolBox.addItem(self.FluidsTopologyTreePage, "Fluids > Topology")
        self.BackgroundsTreePage = QWidget()
        self.BackgroundsTreePage.setObjectName("BackgroundsTreePage")
        self.BackgroundsTreePage.setGeometry(QRect(0, 0, 626, 168))
        self.verticalLayout_6 = QVBoxLayout(self.BackgroundsTreePage)
        self.verticalLayout_6.setObjectName("verticalLayout_6")
        self.BackgroundsTreeWidget = QTreeWidget(self.BackgroundsTreePage)
        __qtreewidgetitem4 = QTreeWidgetItem()
        __qtreewidgetitem4.setText(0, "1")
        self.BackgroundsTreeWidget.setHeaderItem(__qtreewidgetitem4)
        self.BackgroundsTreeWidget.setObjectName("BackgroundsTreeWidget")

        self.verticalLayout_6.addWidget(self.BackgroundsTreeWidget)

        self.toolBox.addItem(self.BackgroundsTreePage, "Background > Background")
        self.BackgroundsTopologyTreePage = QWidget()
        self.BackgroundsTopologyTreePage.setObjectName("BackgroundsTopologyTreePage")
        self.BackgroundsTopologyTreePage.setGeometry(QRect(0, 0, 626, 168))
        self.verticalLayout_7 = QVBoxLayout(self.BackgroundsTopologyTreePage)
        self.verticalLayout_7.setObjectName("verticalLayout_7")
        self.BackgroundsTopologyTreeWidget = QTreeWidget(
            self.BackgroundsTopologyTreePage
        )
        __qtreewidgetitem5 = QTreeWidgetItem()
        __qtreewidgetitem5.setText(0, "1")
        self.BackgroundsTopologyTreeWidget.setHeaderItem(__qtreewidgetitem5)
        self.BackgroundsTopologyTreeWidget.setObjectName(
            "BackgroundsTopologyTreeWidget"
        )

        self.verticalLayout_7.addWidget(self.BackgroundsTopologyTreeWidget)

        self.toolBox.addItem(self.BackgroundsTopologyTreePage, "Background > Topology")
        self.DOMsTablePage = QWidget()
        self.DOMsTablePage.setObjectName("DOMsTablePage")
        self.DOMsTablePage.setGeometry(QRect(0, 0, 626, 168))
        self.verticalLayout_8 = QVBoxLayout(self.DOMsTablePage)
        self.verticalLayout_8.setObjectName("verticalLayout_8")
        self.DOMsTableWidget = QTableWidget(self.DOMsTablePage)
        self.DOMsTableWidget.setObjectName("DOMsTableWidget")

        self.verticalLayout_8.addWidget(self.DOMsTableWidget)

        self.toolBox.addItem(self.DOMsTablePage, "DEMs and DOMs")
        self.ImagesTablePage = QWidget()
        self.ImagesTablePage.setObjectName("ImagesTablePage")
        self.ImagesTablePage.setGeometry(QRect(0, 0, 626, 168))
        self.verticalLayout_9 = QVBoxLayout(self.ImagesTablePage)
        self.verticalLayout_9.setObjectName("verticalLayout_9")
        self.ImagesTableWidget = QTableWidget(self.ImagesTablePage)
        self.ImagesTableWidget.setObjectName("ImagesTableWidget")

        self.verticalLayout_9.addWidget(self.ImagesTableWidget)

        self.toolBox.addItem(self.ImagesTablePage, "Images")
        self.Mesh3DTablePage = QWidget()
        self.Mesh3DTablePage.setObjectName("Mesh3DTablePage")
        self.Mesh3DTablePage.setGeometry(QRect(0, 0, 626, 168))
        self.verticalLayout_10 = QVBoxLayout(self.Mesh3DTablePage)
        self.verticalLayout_10.setObjectName("verticalLayout_10")
        self.Mesh3DTableWidget = QTableWidget(self.Mesh3DTablePage)
        self.Mesh3DTableWidget.setObjectName("Mesh3DTableWidget")

        self.verticalLayout_10.addWidget(self.Mesh3DTableWidget)

        self.toolBox.addItem(self.Mesh3DTablePage, "Meshes and Grids")
        self.BoundariesTablePage = QWidget()
        self.BoundariesTablePage.setObjectName("BoundariesTablePage")
        self.BoundariesTablePage.setGeometry(QRect(0, 0, 626, 168))
        self.verticalLayout_11 = QVBoxLayout(self.BoundariesTablePage)
        self.verticalLayout_11.setObjectName("verticalLayout_11")
        self.BoundariesTableWidget = QTableWidget(self.BoundariesTablePage)
        self.BoundariesTableWidget.setObjectName("BoundariesTableWidget")

        self.verticalLayout_11.addWidget(self.BoundariesTableWidget)

        self.toolBox.addItem(self.BoundariesTablePage, "Boundaries")
        self.XSectionTreePage = QWidget()
        self.XSectionTreePage.setObjectName("XSectionTreePage")
        self.XSectionTreePage.setGeometry(QRect(0, 0, 626, 168))
        self.verticalLayout_12 = QVBoxLayout(self.XSectionTreePage)
        self.verticalLayout_12.setObjectName("verticalLayout_12")
        self.XSectionTreeWidget = QTreeWidget(self.XSectionTreePage)
        __qtreewidgetitem6 = QTreeWidgetItem()
        __qtreewidgetitem6.setText(0, "1")
        self.XSectionTreeWidget.setHeaderItem(__qtreewidgetitem6)
        self.XSectionTreeWidget.setObjectName("XSectionTreeWidget")

        self.verticalLayout_12.addWidget(self.XSectionTreeWidget)

        self.toolBox.addItem(self.XSectionTreePage, "X Sections")
        self.WellsTreePage = QWidget()
        self.WellsTreePage.setObjectName("WellsTreePage")
        self.WellsTreePage.setGeometry(QRect(0, 0, 626, 168))
        self.verticalLayout_13 = QVBoxLayout(self.WellsTreePage)
        self.verticalLayout_13.setObjectName("verticalLayout_13")
        self.WellsTreeWidget = QTreeWidget(self.WellsTreePage)
        __qtreewidgetitem7 = QTreeWidgetItem()
        __qtreewidgetitem7.setText(0, "1")
        self.WellsTreeWidget.setHeaderItem(__qtreewidgetitem7)
        self.WellsTreeWidget.setObjectName("WellsTreeWidget")

        self.verticalLayout_13.addWidget(self.WellsTreeWidget)

        self.toolBox.addItem(self.WellsTreePage, "Wells")
        self.splitter.addWidget(self.toolBox)

        self.verticalLayout.addWidget(self.splitter)

        BaseViewWindow.setCentralWidget(self.centralwidget)
        self.menubar = QMenuBar(BaseViewWindow)
        self.menubar.setObjectName("menubar")
        self.menubar.setGeometry(QRect(0, 0, 800, 33))
        self.menubar.setNativeMenuBar(False)
        self.menuView = QMenu(self.menubar)
        self.menuView.setObjectName("menuView")
        self.menuView.setTearOffEnabled(True)
        self.menuSelect = QMenu(self.menubar)
        self.menuSelect.setObjectName("menuSelect")
        self.menuSelect.setTearOffEnabled(True)
        self.menuCreate = QMenu(self.menubar)
        self.menuCreate.setObjectName("menuCreate")
        self.menuCreate.setTearOffEnabled(True)
        self.menuModify = QMenu(self.menubar)
        self.menuModify.setObjectName("menuModify")
        self.menuModify.setTearOffEnabled(True)
        self.menuAnalysis = QMenu(self.menubar)
        self.menuAnalysis.setObjectName("menuAnalysis")
        self.menuAnalysis.setTearOffEnabled(True)
        BaseViewWindow.setMenuBar(self.menubar)
        self.statusbar = QStatusBar(BaseViewWindow)
        self.statusbar.setObjectName("statusbar")
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
        BaseViewWindow.setWindowTitle(
            QCoreApplication.translate("BaseViewWindow", "MainWindow", None)
        )
        self.toolBox.setItemText(
            self.toolBox.indexOf(self.GeologyTreePage),
            QCoreApplication.translate("BaseViewWindow", "Geology > Geology", None),
        )
        self.toolBox.setItemText(
            self.toolBox.indexOf(self.GeologyTopologyTreePage),
            QCoreApplication.translate("BaseViewWindow", "Geology > Topology", None),
        )
        self.toolBox.setItemText(
            self.toolBox.indexOf(self.FluidsTreePage),
            QCoreApplication.translate("BaseViewWindow", "Fluids > Fluids", None),
        )
        self.toolBox.setItemText(
            self.toolBox.indexOf(self.FluidsTopologyTreePage),
            QCoreApplication.translate("BaseViewWindow", "Fluids > Topology", None),
        )
        self.toolBox.setItemText(
            self.toolBox.indexOf(self.BackgroundsTreePage),
            QCoreApplication.translate(
                "BaseViewWindow", "Background > Background", None
            ),
        )
        self.toolBox.setItemText(
            self.toolBox.indexOf(self.BackgroundsTopologyTreePage),
            QCoreApplication.translate("BaseViewWindow", "Background > Topology", None),
        )
        self.toolBox.setItemText(
            self.toolBox.indexOf(self.DOMsTablePage),
            QCoreApplication.translate("BaseViewWindow", "DEMs and DOMs", None),
        )
        self.toolBox.setItemText(
            self.toolBox.indexOf(self.ImagesTablePage),
            QCoreApplication.translate("BaseViewWindow", "Images", None),
        )
        self.toolBox.setItemText(
            self.toolBox.indexOf(self.Mesh3DTablePage),
            QCoreApplication.translate("BaseViewWindow", "Meshes and Grids", None),
        )
        self.toolBox.setItemText(
            self.toolBox.indexOf(self.BoundariesTablePage),
            QCoreApplication.translate("BaseViewWindow", "Boundaries", None),
        )
        self.toolBox.setItemText(
            self.toolBox.indexOf(self.XSectionTreePage),
            QCoreApplication.translate("BaseViewWindow", "X Sections", None),
        )
        self.toolBox.setItemText(
            self.toolBox.indexOf(self.WellsTreePage),
            QCoreApplication.translate("BaseViewWindow", "Wells", None),
        )
        self.menuView.setTitle(
            QCoreApplication.translate("BaseViewWindow", "View", None)
        )
        self.menuSelect.setTitle(
            QCoreApplication.translate("BaseViewWindow", "Select", None)
        )
        self.menuCreate.setTitle(
            QCoreApplication.translate("BaseViewWindow", "Create", None)
        )
        self.menuModify.setTitle(
            QCoreApplication.translate("BaseViewWindow", "Modify", None)
        )
        self.menuAnalysis.setTitle(
            QCoreApplication.translate("BaseViewWindow", "Analysis", None)
        )

    # retranslateUi
