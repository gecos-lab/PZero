# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'base_view_widgetGvdFXp.ui'
##
## Created by: Qt User Interface Compiler version 6.5.1
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor,
    QFont, QFontDatabase, QGradient, QIcon,
    QImage, QKeySequence, QLinearGradient, QPainter,
    QPalette, QPixmap, QRadialGradient, QTransform)
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QFrame, QHBoxLayout,
    QHeaderView, QLayout, QSizePolicy, QSpacerItem,
    QSplitter, QTableWidget, QTableWidgetItem, QToolBox,
    QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
    QWidget)

class Ui_View(object):
    def setupUi(self, View):
        if not View.objectName():
            View.setObjectName(u"View")
        View.resize(940, 662)
        self.horizontalLayout_2 = QHBoxLayout(View)
        self.horizontalLayout_2.setObjectName(u"horizontalLayout_2")
        self.ToolButtonsFrame = QFrame(View)
        self.ToolButtonsFrame.setObjectName(u"ToolButtonsFrame")
        sizePolicy = QSizePolicy(QSizePolicy.Minimum, QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.ToolButtonsFrame.sizePolicy().hasHeightForWidth())
        self.ToolButtonsFrame.setSizePolicy(sizePolicy)
        self.ToolButtonsFrame.setFrameShape(QFrame.StyledPanel)
        self.ToolButtonsFrame.setFrameShadow(QFrame.Plain)
        self.verticalLayout_2 = QVBoxLayout(self.ToolButtonsFrame)
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.SaveHomeButton = QToolButton(self.ToolButtonsFrame)
        self.SaveHomeButton.setObjectName(u"SaveHomeButton")
        self.SaveHomeButton.setAutoRaise(False)
        self.SaveHomeButton.setArrowType(Qt.NoArrow)

        self.verticalLayout_2.addWidget(self.SaveHomeButton)

        self.ZoomHomeButton = QToolButton(self.ToolButtonsFrame)
        self.ZoomHomeButton.setObjectName(u"ZoomHomeButton")
        self.ZoomHomeButton.setAutoRaise(False)
        self.ZoomHomeButton.setArrowType(Qt.NoArrow)

        self.verticalLayout_2.addWidget(self.ZoomHomeButton)

        self.ZoomActiveButton = QToolButton(self.ToolButtonsFrame)
        self.ZoomActiveButton.setObjectName(u"ZoomActiveButton")
        self.ZoomActiveButton.setAutoRaise(False)
        self.ZoomActiveButton.setArrowType(Qt.NoArrow)

        self.verticalLayout_2.addWidget(self.ZoomActiveButton)

        self.SelectEntityButton = QToolButton(self.ToolButtonsFrame)
        self.SelectEntityButton.setObjectName(u"SelectEntityButton")
        self.SelectEntityButton.setAutoRaise(False)
        self.SelectEntityButton.setArrowType(Qt.NoArrow)

        self.verticalLayout_2.addWidget(self.SelectEntityButton)

        self.ClearSelectionButton = QToolButton(self.ToolButtonsFrame)
        self.ClearSelectionButton.setObjectName(u"ClearSelectionButton")
        self.ClearSelectionButton.setAutoRaise(False)
        self.ClearSelectionButton.setArrowType(Qt.NoArrow)

        self.verticalLayout_2.addWidget(self.ClearSelectionButton)

        self.RemoveEntityButton = QToolButton(self.ToolButtonsFrame)
        self.RemoveEntityButton.setObjectName(u"RemoveEntityButton")
        sizePolicy1 = QSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.RemoveEntityButton.sizePolicy().hasHeightForWidth())
        self.RemoveEntityButton.setSizePolicy(sizePolicy1)
        self.RemoveEntityButton.setAutoRaise(False)
        self.RemoveEntityButton.setArrowType(Qt.NoArrow)

        self.verticalLayout_2.addWidget(self.RemoveEntityButton)

        self.verticalSpacer = QSpacerItem(20, 453, QSizePolicy.Minimum, QSizePolicy.Expanding)

        self.verticalLayout_2.addItem(self.verticalSpacer)


        self.horizontalLayout_2.addWidget(self.ToolButtonsFrame)

        self.splitter = QSplitter(View)
        self.splitter.setObjectName(u"splitter")
        self.splitter.setOrientation(Qt.Horizontal)
        self.ViewFrame = QFrame(self.splitter)
        self.ViewFrame.setObjectName(u"ViewFrame")
        self.ViewFrame.setEnabled(True)
        sizePolicy2 = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        sizePolicy2.setHorizontalStretch(1)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.ViewFrame.sizePolicy().hasHeightForWidth())
        self.ViewFrame.setSizePolicy(sizePolicy2)
        self.ViewFrame.setMinimumSize(QSize(0, 0))
        self.ViewFrame.setBaseSize(QSize(0, 0))
        self.ViewFrame.setFrameShape(QFrame.StyledPanel)
        self.ViewFrame.setFrameShadow(QFrame.Plain)
        self.ViewFrame.setLineWidth(0)
        self.horizontalLayout = QHBoxLayout(self.ViewFrame)
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.ViewFrameLayout = QVBoxLayout()
        self.ViewFrameLayout.setSpacing(8)
        self.ViewFrameLayout.setObjectName(u"ViewFrameLayout")
        self.ViewFrameLayout.setSizeConstraint(QLayout.SetDefaultConstraint)
        self.ViewFrameLayout.setContentsMargins(4, 4, 4, 4)

        self.horizontalLayout.addLayout(self.ViewFrameLayout)

        self.splitter.addWidget(self.ViewFrame)
        self.toolBox = QToolBox(self.splitter)
        self.toolBox.setObjectName(u"toolBox")
        sizePolicy3 = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        sizePolicy3.setHorizontalStretch(0)
        sizePolicy3.setVerticalStretch(0)
        sizePolicy3.setHeightForWidth(self.toolBox.sizePolicy().hasHeightForWidth())
        self.toolBox.setSizePolicy(sizePolicy3)
        self.toolBox.setMinimumSize(QSize(0, 0))
        self.toolBox.setBaseSize(QSize(0, 0))
        self.toolBox.setFrameShadow(QFrame.Raised)
        self.GeologyTreePage = QWidget()
        self.GeologyTreePage.setObjectName(u"GeologyTreePage")
        self.GeologyTreePage.setGeometry(QRect(0, 0, 274, 284))
        sizePolicy4 = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        sizePolicy4.setHorizontalStretch(1)
        sizePolicy4.setVerticalStretch(1)
        sizePolicy4.setHeightForWidth(self.GeologyTreePage.sizePolicy().hasHeightForWidth())
        self.GeologyTreePage.setSizePolicy(sizePolicy4)
        self.GeologyTreePage.setMinimumSize(QSize(0, 0))
        self.GeologyTreePage.setBaseSize(QSize(0, 0))
        self.verticalLayout_7 = QVBoxLayout(self.GeologyTreePage)
        self.verticalLayout_7.setObjectName(u"verticalLayout_7")
        self.GeologyTreeWidget = QTreeWidget(self.GeologyTreePage)
        __qtreewidgetitem = QTreeWidgetItem()
        __qtreewidgetitem.setText(0, u"1");
        self.GeologyTreeWidget.setHeaderItem(__qtreewidgetitem)
        self.GeologyTreeWidget.setObjectName(u"GeologyTreeWidget")
        sizePolicy4.setHeightForWidth(self.GeologyTreeWidget.sizePolicy().hasHeightForWidth())
        self.GeologyTreeWidget.setSizePolicy(sizePolicy4)
        self.GeologyTreeWidget.setMinimumSize(QSize(0, 0))
        self.GeologyTreeWidget.setMaximumSize(QSize(16777215, 16777215))
        self.GeologyTreeWidget.setBaseSize(QSize(0, 0))

        self.verticalLayout_7.addWidget(self.GeologyTreeWidget)

        self.toolBox.addItem(self.GeologyTreePage, u"Geology > Geology Tree")
        self.TopologyTreePage = QWidget()
        self.TopologyTreePage.setObjectName(u"TopologyTreePage")
        self.TopologyTreePage.setGeometry(QRect(0, 0, 98, 89))
        sizePolicy4.setHeightForWidth(self.TopologyTreePage.sizePolicy().hasHeightForWidth())
        self.TopologyTreePage.setSizePolicy(sizePolicy4)
        self.TopologyTreePage.setMinimumSize(QSize(0, 0))
        self.TopologyTreePage.setBaseSize(QSize(0, 0))
        self.verticalLayout_6 = QVBoxLayout(self.TopologyTreePage)
        self.verticalLayout_6.setObjectName(u"verticalLayout_6")
        self.TopologyTreeWidget = QTreeWidget(self.TopologyTreePage)
        __qtreewidgetitem1 = QTreeWidgetItem()
        __qtreewidgetitem1.setText(0, u"1");
        self.TopologyTreeWidget.setHeaderItem(__qtreewidgetitem1)
        self.TopologyTreeWidget.setObjectName(u"TopologyTreeWidget")
        sizePolicy4.setHeightForWidth(self.TopologyTreeWidget.sizePolicy().hasHeightForWidth())
        self.TopologyTreeWidget.setSizePolicy(sizePolicy4)
        self.TopologyTreeWidget.setMinimumSize(QSize(0, 0))
        self.TopologyTreeWidget.setBaseSize(QSize(0, 0))

        self.verticalLayout_6.addWidget(self.TopologyTreeWidget)

        self.toolBox.addItem(self.TopologyTreePage, u"Geology > Topology Tree")
        self.XSectionListPage = QWidget()
        self.XSectionListPage.setObjectName(u"XSectionListPage")
        self.XSectionListPage.setGeometry(QRect(0, 0, 98, 89))
        sizePolicy4.setHeightForWidth(self.XSectionListPage.sizePolicy().hasHeightForWidth())
        self.XSectionListPage.setSizePolicy(sizePolicy4)
        self.XSectionListPage.setMinimumSize(QSize(0, 0))
        self.XSectionListPage.setBaseSize(QSize(0, 0))
        self.verticalLayout_5 = QVBoxLayout(self.XSectionListPage)
        self.verticalLayout_5.setObjectName(u"verticalLayout_5")
        self.XSectionTreeWidget = QTreeWidget(self.XSectionListPage)
        __qtreewidgetitem2 = QTreeWidgetItem()
        __qtreewidgetitem2.setText(0, u"1");
        self.XSectionTreeWidget.setHeaderItem(__qtreewidgetitem2)
        self.XSectionTreeWidget.setObjectName(u"XSectionTreeWidget")
        sizePolicy4.setHeightForWidth(self.XSectionTreeWidget.sizePolicy().hasHeightForWidth())
        self.XSectionTreeWidget.setSizePolicy(sizePolicy4)
        self.XSectionTreeWidget.setMinimumSize(QSize(0, 0))
        self.XSectionTreeWidget.setBaseSize(QSize(0, 0))
        self.XSectionTreeWidget.setTabKeyNavigation(True)
        self.XSectionTreeWidget.setDragDropOverwriteMode(True)
        self.XSectionTreeWidget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.XSectionTreeWidget.setHorizontalScrollMode(QAbstractItemView.ScrollPerItem)
        self.XSectionTreeWidget.setAutoExpandDelay(-1)

        self.verticalLayout_5.addWidget(self.XSectionTreeWidget)

        self.toolBox.addItem(self.XSectionListPage, u"X Section")
        self.BoundariesPage = QWidget()
        self.BoundariesPage.setObjectName(u"BoundariesPage")
        self.BoundariesPage.setGeometry(QRect(0, 0, 98, 89))
        sizePolicy3.setHeightForWidth(self.BoundariesPage.sizePolicy().hasHeightForWidth())
        self.BoundariesPage.setSizePolicy(sizePolicy3)
        self.verticalLayout_8 = QVBoxLayout(self.BoundariesPage)
        self.verticalLayout_8.setObjectName(u"verticalLayout_8")
        self.BoundariesTableWidget = QTableWidget(self.BoundariesPage)
        self.BoundariesTableWidget.setObjectName(u"BoundariesTableWidget")
        sizePolicy4.setHeightForWidth(self.BoundariesTableWidget.sizePolicy().hasHeightForWidth())
        self.BoundariesTableWidget.setSizePolicy(sizePolicy4)
        self.BoundariesTableWidget.setMinimumSize(QSize(0, 0))
        self.BoundariesTableWidget.setBaseSize(QSize(0, 0))

        self.verticalLayout_8.addWidget(self.BoundariesTableWidget)

        self.toolBox.addItem(self.BoundariesPage, u"Boundaries")
        self.Mesh3DPage = QWidget()
        self.Mesh3DPage.setObjectName(u"Mesh3DPage")
        self.Mesh3DPage.setGeometry(QRect(0, 0, 98, 89))
        sizePolicy4.setHeightForWidth(self.Mesh3DPage.sizePolicy().hasHeightForWidth())
        self.Mesh3DPage.setSizePolicy(sizePolicy4)
        self.Mesh3DPage.setMinimumSize(QSize(0, 0))
        self.Mesh3DPage.setBaseSize(QSize(0, 0))
        self.verticalLayout_4 = QVBoxLayout(self.Mesh3DPage)
        self.verticalLayout_4.setObjectName(u"verticalLayout_4")
        self.Mesh3DTableWidget = QTableWidget(self.Mesh3DPage)
        self.Mesh3DTableWidget.setObjectName(u"Mesh3DTableWidget")
        sizePolicy4.setHeightForWidth(self.Mesh3DTableWidget.sizePolicy().hasHeightForWidth())
        self.Mesh3DTableWidget.setSizePolicy(sizePolicy4)
        self.Mesh3DTableWidget.setMinimumSize(QSize(0, 0))
        self.Mesh3DTableWidget.setBaseSize(QSize(0, 0))

        self.verticalLayout_4.addWidget(self.Mesh3DTableWidget)

        self.toolBox.addItem(self.Mesh3DPage, u"3D Meshes and Grids")
        self.DOMsPage = QWidget()
        self.DOMsPage.setObjectName(u"DOMsPage")
        self.DOMsPage.setGeometry(QRect(0, 0, 98, 89))
        sizePolicy4.setHeightForWidth(self.DOMsPage.sizePolicy().hasHeightForWidth())
        self.DOMsPage.setSizePolicy(sizePolicy4)
        self.DOMsPage.setMinimumSize(QSize(0, 0))
        self.DOMsPage.setBaseSize(QSize(0, 0))
        self.verticalLayout_3 = QVBoxLayout(self.DOMsPage)
        self.verticalLayout_3.setObjectName(u"verticalLayout_3")
        self.DOMsTableWidget = QTableWidget(self.DOMsPage)
        self.DOMsTableWidget.setObjectName(u"DOMsTableWidget")
        sizePolicy4.setHeightForWidth(self.DOMsTableWidget.sizePolicy().hasHeightForWidth())
        self.DOMsTableWidget.setSizePolicy(sizePolicy4)
        self.DOMsTableWidget.setMinimumSize(QSize(0, 0))
        self.DOMsTableWidget.setBaseSize(QSize(0, 0))

        self.verticalLayout_3.addWidget(self.DOMsTableWidget)

        self.toolBox.addItem(self.DOMsPage, u"DEMs and DOMs")
        self.WellsPage = QWidget()
        self.WellsPage.setObjectName(u"WellsPage")
        self.WellsPage.setGeometry(QRect(0, 0, 98, 89))
        self.verticalLayout_9 = QVBoxLayout(self.WellsPage)
        self.verticalLayout_9.setObjectName(u"verticalLayout_9")
        self.WellsTreeWidget = QTreeWidget(self.WellsPage)
        __qtreewidgetitem3 = QTreeWidgetItem()
        __qtreewidgetitem3.setText(0, u"1");
        self.WellsTreeWidget.setHeaderItem(__qtreewidgetitem3)
        self.WellsTreeWidget.setObjectName(u"WellsTreeWidget")

        self.verticalLayout_9.addWidget(self.WellsTreeWidget)

        self.toolBox.addItem(self.WellsPage, u"Wells")
        self.FluidsTreePage = QWidget()
        self.FluidsTreePage.setObjectName(u"FluidsTreePage")
        self.FluidsTreePage.setGeometry(QRect(0, 0, 98, 89))
        self.verticalLayout_10 = QVBoxLayout(self.FluidsTreePage)
        self.verticalLayout_10.setObjectName(u"verticalLayout_10")
        self.FluidsTreeWidget = QTreeWidget(self.FluidsTreePage)
        __qtreewidgetitem4 = QTreeWidgetItem()
        __qtreewidgetitem4.setText(0, u"1");
        self.FluidsTreeWidget.setHeaderItem(__qtreewidgetitem4)
        self.FluidsTreeWidget.setObjectName(u"FluidsTreeWidget")

        self.verticalLayout_10.addWidget(self.FluidsTreeWidget)

        self.toolBox.addItem(self.FluidsTreePage, u"Fluids > Fluids Tree")
        self.FluidsTopologyTree = QWidget()
        self.FluidsTopologyTree.setObjectName(u"FluidsTopologyTree")
        self.FluidsTopologyTree.setGeometry(QRect(0, 0, 98, 89))
        self.verticalLayout_11 = QVBoxLayout(self.FluidsTopologyTree)
        self.verticalLayout_11.setObjectName(u"verticalLayout_11")
        self.FluidsTopologyTreeWidget = QTreeWidget(self.FluidsTopologyTree)
        __qtreewidgetitem5 = QTreeWidgetItem()
        __qtreewidgetitem5.setText(0, u"1");
        self.FluidsTopologyTreeWidget.setHeaderItem(__qtreewidgetitem5)
        self.FluidsTopologyTreeWidget.setObjectName(u"FluidsTopologyTreeWidget")

        self.verticalLayout_11.addWidget(self.FluidsTopologyTreeWidget)

        self.toolBox.addItem(self.FluidsTopologyTree, u"Fluids > Topology Tree")
        self.BackgroundsTreePage = QWidget()
        self.BackgroundsTreePage.setObjectName(u"BackgroundsTreePage")
        self.BackgroundsTreePage.setGeometry(QRect(0, 0, 98, 89))
        self.verticalLayout_12 = QVBoxLayout(self.BackgroundsTreePage)
        self.verticalLayout_12.setObjectName(u"verticalLayout_12")
        self.BackgroundsTreeWidget = QTreeWidget(self.BackgroundsTreePage)
        __qtreewidgetitem6 = QTreeWidgetItem()
        __qtreewidgetitem6.setText(0, u"1");
        self.BackgroundsTreeWidget.setHeaderItem(__qtreewidgetitem6)
        self.BackgroundsTreeWidget.setObjectName(u"BackgroundsTreeWidget")

        self.verticalLayout_12.addWidget(self.BackgroundsTreeWidget)

        self.toolBox.addItem(self.BackgroundsTreePage, u"Background data > Backgrounds tree")
        self.BackgroundsTopologyTree = QWidget()
        self.BackgroundsTopologyTree.setObjectName(u"BackgroundsTopologyTree")
        self.BackgroundsTopologyTree.setGeometry(QRect(0, 0, 98, 89))
        self.verticalLayout_13 = QVBoxLayout(self.BackgroundsTopologyTree)
        self.verticalLayout_13.setObjectName(u"verticalLayout_13")
        self.BackgroundsTopologyTreeWidget = QTreeWidget(self.BackgroundsTopologyTree)
        __qtreewidgetitem7 = QTreeWidgetItem()
        __qtreewidgetitem7.setText(0, u"1");
        self.BackgroundsTopologyTreeWidget.setHeaderItem(__qtreewidgetitem7)
        self.BackgroundsTopologyTreeWidget.setObjectName(u"BackgroundsTopologyTreeWidget")

        self.verticalLayout_13.addWidget(self.BackgroundsTopologyTreeWidget)

        self.toolBox.addItem(self.BackgroundsTopologyTree, u"Background data > Topology tree")
        self.ImagesPage = QWidget()
        self.ImagesPage.setObjectName(u"ImagesPage")
        self.ImagesPage.setGeometry(QRect(0, 0, 98, 89))
        sizePolicy4.setHeightForWidth(self.ImagesPage.sizePolicy().hasHeightForWidth())
        self.ImagesPage.setSizePolicy(sizePolicy4)
        self.ImagesPage.setMinimumSize(QSize(0, 0))
        self.ImagesPage.setBaseSize(QSize(0, 0))
        self.verticalLayout = QVBoxLayout(self.ImagesPage)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.ImagesTableWidget = QTableWidget(self.ImagesPage)
        self.ImagesTableWidget.setObjectName(u"ImagesTableWidget")
        sizePolicy4.setHeightForWidth(self.ImagesTableWidget.sizePolicy().hasHeightForWidth())
        self.ImagesTableWidget.setSizePolicy(sizePolicy4)
        self.ImagesTableWidget.setMinimumSize(QSize(0, 0))
        self.ImagesTableWidget.setBaseSize(QSize(0, 0))

        self.verticalLayout.addWidget(self.ImagesTableWidget)

        self.toolBox.addItem(self.ImagesPage, u"Images")
        self.splitter.addWidget(self.toolBox)

        self.horizontalLayout_2.addWidget(self.splitter)


        self.retranslateUi(View)

        self.toolBox.setCurrentIndex(0)


        QMetaObject.connectSlotsByName(View)
    # setupUi

    def retranslateUi(self, View):
        View.setWindowTitle(QCoreApplication.translate("View", u"Form", None))
#if QT_CONFIG(tooltip)
        self.SaveHomeButton.setToolTip(QCoreApplication.translate("View", u"Save home view", None))
#endif // QT_CONFIG(tooltip)
        self.SaveHomeButton.setText(QCoreApplication.translate("View", u"SH", None))
#if QT_CONFIG(tooltip)
        self.ZoomHomeButton.setToolTip(QCoreApplication.translate("View", u"Zoom to home view", None))
#endif // QT_CONFIG(tooltip)
        self.ZoomHomeButton.setText(QCoreApplication.translate("View", u"ZH", None))
#if QT_CONFIG(tooltip)
        self.ZoomActiveButton.setToolTip(QCoreApplication.translate("View", u"Zoom to home view", None))
#endif // QT_CONFIG(tooltip)
        self.ZoomActiveButton.setText(QCoreApplication.translate("View", u"ZA", None))
#if QT_CONFIG(tooltip)
        self.SelectEntityButton.setToolTip(QCoreApplication.translate("View", u"Zoom to home view", None))
#endif // QT_CONFIG(tooltip)
        self.SelectEntityButton.setText(QCoreApplication.translate("View", u"SE", None))
#if QT_CONFIG(tooltip)
        self.ClearSelectionButton.setToolTip(QCoreApplication.translate("View", u"Zoom to home view", None))
#endif // QT_CONFIG(tooltip)
        self.ClearSelectionButton.setText(QCoreApplication.translate("View", u"CS", None))
#if QT_CONFIG(tooltip)
        self.RemoveEntityButton.setToolTip(QCoreApplication.translate("View", u"Zoom to home view", None))
#endif // QT_CONFIG(tooltip)
        self.RemoveEntityButton.setText(QCoreApplication.translate("View", u"RE", None))
        self.toolBox.setItemText(self.toolBox.indexOf(self.GeologyTreePage), QCoreApplication.translate("View", u"Geology > Geology Tree", None))
        self.toolBox.setItemText(self.toolBox.indexOf(self.TopologyTreePage), QCoreApplication.translate("View", u"Geology > Topology Tree", None))
        self.toolBox.setItemText(self.toolBox.indexOf(self.XSectionListPage), QCoreApplication.translate("View", u"X Section", None))
        self.toolBox.setItemText(self.toolBox.indexOf(self.BoundariesPage), QCoreApplication.translate("View", u"Boundaries", None))
        self.toolBox.setItemText(self.toolBox.indexOf(self.Mesh3DPage), QCoreApplication.translate("View", u"3D Meshes and Grids", None))
        self.toolBox.setItemText(self.toolBox.indexOf(self.DOMsPage), QCoreApplication.translate("View", u"DEMs and DOMs", None))
        self.toolBox.setItemText(self.toolBox.indexOf(self.WellsPage), QCoreApplication.translate("View", u"Wells", None))
        self.toolBox.setItemText(self.toolBox.indexOf(self.FluidsTreePage), QCoreApplication.translate("View", u"Fluids > Fluids Tree", None))
        self.toolBox.setItemText(self.toolBox.indexOf(self.FluidsTopologyTree), QCoreApplication.translate("View", u"Fluids > Topology Tree", None))
        self.toolBox.setItemText(self.toolBox.indexOf(self.BackgroundsTreePage), QCoreApplication.translate("View", u"Background data > Backgrounds tree", None))
        self.toolBox.setItemText(self.toolBox.indexOf(self.BackgroundsTopologyTree), QCoreApplication.translate("View", u"Background data > Topology tree", None))
        self.toolBox.setItemText(self.toolBox.indexOf(self.ImagesPage), QCoreApplication.translate("View", u"Images", None))
    # retranslateUi

