# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'dock_viewXwsEXG.ui'
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
    QAbstractItemView,
    QApplication,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLayout,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QToolBox,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


class Ui_Form(object):
    def setupUi(self, Form):
        if not Form.objectName():
            Form.setObjectName("Form")
        Form.resize(1280, 803)
        self.verticalLayoutWidget = QWidget(Form)
        self.verticalLayoutWidget.setObjectName("verticalLayoutWidget")
        self.verticalLayoutWidget.setGeometry(QRect(10, 50, 1251, 741))
        self.centralWidget = QVBoxLayout(self.verticalLayoutWidget)
        self.centralWidget.setObjectName("centralWidget")
        self.centralWidget.setContentsMargins(11, 11, 11, 11)
        self.splitter = QSplitter(self.verticalLayoutWidget)
        self.splitter.setObjectName("splitter")
        sizePolicy = QSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        sizePolicy.setHorizontalStretch(1)
        sizePolicy.setVerticalStretch(1)
        sizePolicy.setHeightForWidth(self.splitter.sizePolicy().hasHeightForWidth())
        self.splitter.setSizePolicy(sizePolicy)
        self.splitter.setMinimumSize(QSize(0, 0))
        self.splitter.setBaseSize(QSize(0, 0))
        self.splitter.setLineWidth(0)
        self.splitter.setOrientation(Qt.Orientation.Horizontal)
        self.toolBox_2 = QToolBox(self.splitter)
        self.toolBox_2.setObjectName("toolBox_2")
        sizePolicy1 = QSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.toolBox_2.sizePolicy().hasHeightForWidth())
        self.toolBox_2.setSizePolicy(sizePolicy1)
        self.toolBox_2.setMinimumSize(QSize(0, 0))
        self.toolBox_2.setBaseSize(QSize(0, 0))
        self.toolBox_2.setFrameShadow(QFrame.Shadow.Raised)
        self.GeologyTreePage_2 = QWidget()
        self.GeologyTreePage_2.setObjectName("GeologyTreePage_2")
        self.GeologyTreePage_2.setGeometry(QRect(0, 0, 274, 359))
        sizePolicy.setHeightForWidth(
            self.GeologyTreePage_2.sizePolicy().hasHeightForWidth()
        )
        self.GeologyTreePage_2.setSizePolicy(sizePolicy)
        self.GeologyTreePage_2.setMinimumSize(QSize(0, 0))
        self.GeologyTreePage_2.setBaseSize(QSize(0, 0))
        self.verticalLayout_14 = QVBoxLayout(self.GeologyTreePage_2)
        self.verticalLayout_14.setObjectName("verticalLayout_14")
        self.GeologyTreeWidget_2 = QTreeWidget(self.GeologyTreePage_2)
        __qtreewidgetitem = QTreeWidgetItem()
        __qtreewidgetitem.setText(0, "1")
        self.GeologyTreeWidget_2.setHeaderItem(__qtreewidgetitem)
        self.GeologyTreeWidget_2.setObjectName("GeologyTreeWidget_2")
        sizePolicy.setHeightForWidth(
            self.GeologyTreeWidget_2.sizePolicy().hasHeightForWidth()
        )
        self.GeologyTreeWidget_2.setSizePolicy(sizePolicy)
        self.GeologyTreeWidget_2.setMinimumSize(QSize(0, 0))
        self.GeologyTreeWidget_2.setMaximumSize(QSize(16777215, 16777215))
        self.GeologyTreeWidget_2.setBaseSize(QSize(0, 0))

        self.verticalLayout_14.addWidget(self.GeologyTreeWidget_2)

        self.toolBox_2.addItem(self.GeologyTreePage_2, "Geology > Geology Tree")
        self.TopologyTreePage_2 = QWidget()
        self.TopologyTreePage_2.setObjectName("TopologyTreePage_2")
        self.TopologyTreePage_2.setGeometry(QRect(0, 0, 98, 74))
        sizePolicy.setHeightForWidth(
            self.TopologyTreePage_2.sizePolicy().hasHeightForWidth()
        )
        self.TopologyTreePage_2.setSizePolicy(sizePolicy)
        self.TopologyTreePage_2.setMinimumSize(QSize(0, 0))
        self.TopologyTreePage_2.setBaseSize(QSize(0, 0))
        self.verticalLayout_15 = QVBoxLayout(self.TopologyTreePage_2)
        self.verticalLayout_15.setObjectName("verticalLayout_15")
        self.TopologyTreeWidget_2 = QTreeWidget(self.TopologyTreePage_2)
        __qtreewidgetitem1 = QTreeWidgetItem()
        __qtreewidgetitem1.setText(0, "1")
        self.TopologyTreeWidget_2.setHeaderItem(__qtreewidgetitem1)
        self.TopologyTreeWidget_2.setObjectName("TopologyTreeWidget_2")
        sizePolicy.setHeightForWidth(
            self.TopologyTreeWidget_2.sizePolicy().hasHeightForWidth()
        )
        self.TopologyTreeWidget_2.setSizePolicy(sizePolicy)
        self.TopologyTreeWidget_2.setMinimumSize(QSize(0, 0))
        self.TopologyTreeWidget_2.setBaseSize(QSize(0, 0))

        self.verticalLayout_15.addWidget(self.TopologyTreeWidget_2)

        self.toolBox_2.addItem(self.TopologyTreePage_2, "Geology > Topology Tree")
        self.XSectionListPage_2 = QWidget()
        self.XSectionListPage_2.setObjectName("XSectionListPage_2")
        self.XSectionListPage_2.setGeometry(QRect(0, 0, 98, 74))
        sizePolicy.setHeightForWidth(
            self.XSectionListPage_2.sizePolicy().hasHeightForWidth()
        )
        self.XSectionListPage_2.setSizePolicy(sizePolicy)
        self.XSectionListPage_2.setMinimumSize(QSize(0, 0))
        self.XSectionListPage_2.setBaseSize(QSize(0, 0))
        self.verticalLayout_16 = QVBoxLayout(self.XSectionListPage_2)
        self.verticalLayout_16.setObjectName("verticalLayout_16")
        self.XSectionTreeWidget_2 = QTreeWidget(self.XSectionListPage_2)
        __qtreewidgetitem2 = QTreeWidgetItem()
        __qtreewidgetitem2.setText(0, "1")
        self.XSectionTreeWidget_2.setHeaderItem(__qtreewidgetitem2)
        self.XSectionTreeWidget_2.setObjectName("XSectionTreeWidget_2")
        sizePolicy.setHeightForWidth(
            self.XSectionTreeWidget_2.sizePolicy().hasHeightForWidth()
        )
        self.XSectionTreeWidget_2.setSizePolicy(sizePolicy)
        self.XSectionTreeWidget_2.setMinimumSize(QSize(0, 0))
        self.XSectionTreeWidget_2.setBaseSize(QSize(0, 0))
        self.XSectionTreeWidget_2.setTabKeyNavigation(True)
        self.XSectionTreeWidget_2.setDragDropOverwriteMode(True)
        self.XSectionTreeWidget_2.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.XSectionTreeWidget_2.setHorizontalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerItem
        )
        self.XSectionTreeWidget_2.setAutoExpandDelay(-1)

        self.verticalLayout_16.addWidget(self.XSectionTreeWidget_2)

        self.toolBox_2.addItem(self.XSectionListPage_2, "X Section")
        self.BoundariesPage_2 = QWidget()
        self.BoundariesPage_2.setObjectName("BoundariesPage_2")
        self.BoundariesPage_2.setGeometry(QRect(0, 0, 98, 74))
        sizePolicy1.setHeightForWidth(
            self.BoundariesPage_2.sizePolicy().hasHeightForWidth()
        )
        self.BoundariesPage_2.setSizePolicy(sizePolicy1)
        self.verticalLayout_17 = QVBoxLayout(self.BoundariesPage_2)
        self.verticalLayout_17.setObjectName("verticalLayout_17")
        self.BoundariesTableWidget_2 = QTableWidget(self.BoundariesPage_2)
        self.BoundariesTableWidget_2.setObjectName("BoundariesTableWidget_2")
        sizePolicy.setHeightForWidth(
            self.BoundariesTableWidget_2.sizePolicy().hasHeightForWidth()
        )
        self.BoundariesTableWidget_2.setSizePolicy(sizePolicy)
        self.BoundariesTableWidget_2.setMinimumSize(QSize(0, 0))
        self.BoundariesTableWidget_2.setBaseSize(QSize(0, 0))

        self.verticalLayout_17.addWidget(self.BoundariesTableWidget_2)

        self.toolBox_2.addItem(self.BoundariesPage_2, "Boundaries")
        self.Mesh3DPage_2 = QWidget()
        self.Mesh3DPage_2.setObjectName("Mesh3DPage_2")
        self.Mesh3DPage_2.setGeometry(QRect(0, 0, 98, 74))
        sizePolicy.setHeightForWidth(self.Mesh3DPage_2.sizePolicy().hasHeightForWidth())
        self.Mesh3DPage_2.setSizePolicy(sizePolicy)
        self.Mesh3DPage_2.setMinimumSize(QSize(0, 0))
        self.Mesh3DPage_2.setBaseSize(QSize(0, 0))
        self.verticalLayout_18 = QVBoxLayout(self.Mesh3DPage_2)
        self.verticalLayout_18.setObjectName("verticalLayout_18")
        self.Mesh3DTableWidget_2 = QTableWidget(self.Mesh3DPage_2)
        self.Mesh3DTableWidget_2.setObjectName("Mesh3DTableWidget_2")
        sizePolicy.setHeightForWidth(
            self.Mesh3DTableWidget_2.sizePolicy().hasHeightForWidth()
        )
        self.Mesh3DTableWidget_2.setSizePolicy(sizePolicy)
        self.Mesh3DTableWidget_2.setMinimumSize(QSize(0, 0))
        self.Mesh3DTableWidget_2.setBaseSize(QSize(0, 0))

        self.verticalLayout_18.addWidget(self.Mesh3DTableWidget_2)

        self.toolBox_2.addItem(self.Mesh3DPage_2, "3D Meshes and Grids")
        self.DOMsPage_2 = QWidget()
        self.DOMsPage_2.setObjectName("DOMsPage_2")
        self.DOMsPage_2.setGeometry(QRect(0, 0, 98, 74))
        sizePolicy.setHeightForWidth(self.DOMsPage_2.sizePolicy().hasHeightForWidth())
        self.DOMsPage_2.setSizePolicy(sizePolicy)
        self.DOMsPage_2.setMinimumSize(QSize(0, 0))
        self.DOMsPage_2.setBaseSize(QSize(0, 0))
        self.verticalLayout_19 = QVBoxLayout(self.DOMsPage_2)
        self.verticalLayout_19.setObjectName("verticalLayout_19")
        self.DOMsTableWidget_2 = QTableWidget(self.DOMsPage_2)
        self.DOMsTableWidget_2.setObjectName("DOMsTableWidget_2")
        sizePolicy.setHeightForWidth(
            self.DOMsTableWidget_2.sizePolicy().hasHeightForWidth()
        )
        self.DOMsTableWidget_2.setSizePolicy(sizePolicy)
        self.DOMsTableWidget_2.setMinimumSize(QSize(0, 0))
        self.DOMsTableWidget_2.setBaseSize(QSize(0, 0))

        self.verticalLayout_19.addWidget(self.DOMsTableWidget_2)

        self.toolBox_2.addItem(self.DOMsPage_2, "DEMs and DOMs")
        self.WellsPage_2 = QWidget()
        self.WellsPage_2.setObjectName("WellsPage_2")
        self.WellsPage_2.setGeometry(QRect(0, 0, 98, 74))
        self.verticalLayout_20 = QVBoxLayout(self.WellsPage_2)
        self.verticalLayout_20.setObjectName("verticalLayout_20")
        self.WellsTreeWidget_2 = QTreeWidget(self.WellsPage_2)
        __qtreewidgetitem3 = QTreeWidgetItem()
        __qtreewidgetitem3.setText(0, "1")
        self.WellsTreeWidget_2.setHeaderItem(__qtreewidgetitem3)
        self.WellsTreeWidget_2.setObjectName("WellsTreeWidget_2")

        self.verticalLayout_20.addWidget(self.WellsTreeWidget_2)

        self.toolBox_2.addItem(self.WellsPage_2, "Wells")
        self.FluidsTreePage_2 = QWidget()
        self.FluidsTreePage_2.setObjectName("FluidsTreePage_2")
        self.FluidsTreePage_2.setGeometry(QRect(0, 0, 98, 74))
        self.verticalLayout_21 = QVBoxLayout(self.FluidsTreePage_2)
        self.verticalLayout_21.setObjectName("verticalLayout_21")
        self.FluidsTreeWidget_2 = QTreeWidget(self.FluidsTreePage_2)
        __qtreewidgetitem4 = QTreeWidgetItem()
        __qtreewidgetitem4.setText(0, "1")
        self.FluidsTreeWidget_2.setHeaderItem(__qtreewidgetitem4)
        self.FluidsTreeWidget_2.setObjectName("FluidsTreeWidget_2")

        self.verticalLayout_21.addWidget(self.FluidsTreeWidget_2)

        self.toolBox_2.addItem(self.FluidsTreePage_2, "Fluids > Fluids Tree")
        self.FluidsTopologyTree_2 = QWidget()
        self.FluidsTopologyTree_2.setObjectName("FluidsTopologyTree_2")
        self.FluidsTopologyTree_2.setGeometry(QRect(0, 0, 98, 74))
        self.verticalLayout_22 = QVBoxLayout(self.FluidsTopologyTree_2)
        self.verticalLayout_22.setObjectName("verticalLayout_22")
        self.FluidsTopologyTreeWidget_2 = QTreeWidget(self.FluidsTopologyTree_2)
        __qtreewidgetitem5 = QTreeWidgetItem()
        __qtreewidgetitem5.setText(0, "1")
        self.FluidsTopologyTreeWidget_2.setHeaderItem(__qtreewidgetitem5)
        self.FluidsTopologyTreeWidget_2.setObjectName("FluidsTopologyTreeWidget_2")

        self.verticalLayout_22.addWidget(self.FluidsTopologyTreeWidget_2)

        self.toolBox_2.addItem(self.FluidsTopologyTree_2, "Fluids > Topology Tree")
        self.BackgroundsTreePage_2 = QWidget()
        self.BackgroundsTreePage_2.setObjectName("BackgroundsTreePage_2")
        self.BackgroundsTreePage_2.setGeometry(QRect(0, 0, 98, 74))
        self.verticalLayout_23 = QVBoxLayout(self.BackgroundsTreePage_2)
        self.verticalLayout_23.setObjectName("verticalLayout_23")
        self.BackgroundsTreeWidget_2 = QTreeWidget(self.BackgroundsTreePage_2)
        __qtreewidgetitem6 = QTreeWidgetItem()
        __qtreewidgetitem6.setText(0, "1")
        self.BackgroundsTreeWidget_2.setHeaderItem(__qtreewidgetitem6)
        self.BackgroundsTreeWidget_2.setObjectName("BackgroundsTreeWidget_2")

        self.verticalLayout_23.addWidget(self.BackgroundsTreeWidget_2)

        self.toolBox_2.addItem(
            self.BackgroundsTreePage_2, "Background data > Backgrounds tree"
        )
        self.BackgroundsTopologyTree_2 = QWidget()
        self.BackgroundsTopologyTree_2.setObjectName("BackgroundsTopologyTree_2")
        self.BackgroundsTopologyTree_2.setGeometry(QRect(0, 0, 98, 74))
        self.verticalLayout_24 = QVBoxLayout(self.BackgroundsTopologyTree_2)
        self.verticalLayout_24.setObjectName("verticalLayout_24")
        self.BackgroundsTopologyTreeWidget_2 = QTreeWidget(
            self.BackgroundsTopologyTree_2
        )
        __qtreewidgetitem7 = QTreeWidgetItem()
        __qtreewidgetitem7.setText(0, "1")
        self.BackgroundsTopologyTreeWidget_2.setHeaderItem(__qtreewidgetitem7)
        self.BackgroundsTopologyTreeWidget_2.setObjectName(
            "BackgroundsTopologyTreeWidget_2"
        )

        self.verticalLayout_24.addWidget(self.BackgroundsTopologyTreeWidget_2)

        self.toolBox_2.addItem(
            self.BackgroundsTopologyTree_2, "Background data > Topology tree"
        )
        self.ImagesPage_2 = QWidget()
        self.ImagesPage_2.setObjectName("ImagesPage_2")
        self.ImagesPage_2.setGeometry(QRect(0, 0, 98, 74))
        sizePolicy.setHeightForWidth(self.ImagesPage_2.sizePolicy().hasHeightForWidth())
        self.ImagesPage_2.setSizePolicy(sizePolicy)
        self.ImagesPage_2.setMinimumSize(QSize(0, 0))
        self.ImagesPage_2.setBaseSize(QSize(0, 0))
        self.verticalLayout_2 = QVBoxLayout(self.ImagesPage_2)
        self.verticalLayout_2.setObjectName("verticalLayout_2")
        self.ImagesTableWidget_2 = QTableWidget(self.ImagesPage_2)
        self.ImagesTableWidget_2.setObjectName("ImagesTableWidget_2")
        sizePolicy.setHeightForWidth(
            self.ImagesTableWidget_2.sizePolicy().hasHeightForWidth()
        )
        self.ImagesTableWidget_2.setSizePolicy(sizePolicy)
        self.ImagesTableWidget_2.setMinimumSize(QSize(0, 0))
        self.ImagesTableWidget_2.setBaseSize(QSize(0, 0))

        self.verticalLayout_2.addWidget(self.ImagesTableWidget_2)

        self.toolBox_2.addItem(self.ImagesPage_2, "Images")
        self.splitter.addWidget(self.toolBox_2)
        self.ViewFrame_2 = QFrame(self.splitter)
        self.ViewFrame_2.setObjectName("ViewFrame_2")
        self.ViewFrame_2.setEnabled(True)
        sizePolicy2 = QSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        sizePolicy2.setHorizontalStretch(1)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.ViewFrame_2.sizePolicy().hasHeightForWidth())
        self.ViewFrame_2.setSizePolicy(sizePolicy2)
        self.ViewFrame_2.setMinimumSize(QSize(0, 0))
        self.ViewFrame_2.setBaseSize(QSize(0, 0))
        self.ViewFrame_2.setFrameShape(QFrame.Shape.NoFrame)
        self.ViewFrame_2.setFrameShadow(QFrame.Shadow.Plain)
        self.ViewFrame_2.setLineWidth(0)
        self.horizontalLayout_2 = QHBoxLayout(self.ViewFrame_2)
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.horizontalLayout_2.setContentsMargins(0, 0, 0, 0)
        self.ViewFrameLayout_2 = QVBoxLayout()
        self.ViewFrameLayout_2.setSpacing(8)
        self.ViewFrameLayout_2.setObjectName("ViewFrameLayout_2")
        self.ViewFrameLayout_2.setSizeConstraint(
            QLayout.SizeConstraint.SetDefaultConstraint
        )
        self.ViewFrameLayout_2.setContentsMargins(4, 4, 4, 4)

        self.horizontalLayout_2.addLayout(self.ViewFrameLayout_2)

        self.splitter.addWidget(self.ViewFrame_2)

        self.centralWidget.addWidget(self.splitter)

        self.menuBar = QWidget(Form)
        self.menuBar.setObjectName("menuBar")
        self.menuBar.setGeometry(QRect(10, 10, 1251, 31))

        self.retranslateUi(Form)

        self.toolBox_2.setCurrentIndex(0)

        QMetaObject.connectSlotsByName(Form)

    # setupUi

    def retranslateUi(self, Form):
        Form.setWindowTitle(QCoreApplication.translate("Form", "Form", None))
        self.toolBox_2.setItemText(
            self.toolBox_2.indexOf(self.GeologyTreePage_2),
            QCoreApplication.translate("Form", "Geology > Geology Tree", None),
        )
        self.toolBox_2.setItemText(
            self.toolBox_2.indexOf(self.TopologyTreePage_2),
            QCoreApplication.translate("Form", "Geology > Topology Tree", None),
        )
        self.toolBox_2.setItemText(
            self.toolBox_2.indexOf(self.XSectionListPage_2),
            QCoreApplication.translate("Form", "X Section", None),
        )
        self.toolBox_2.setItemText(
            self.toolBox_2.indexOf(self.BoundariesPage_2),
            QCoreApplication.translate("Form", "Boundaries", None),
        )
        self.toolBox_2.setItemText(
            self.toolBox_2.indexOf(self.Mesh3DPage_2),
            QCoreApplication.translate("Form", "3D Meshes and Grids", None),
        )
        self.toolBox_2.setItemText(
            self.toolBox_2.indexOf(self.DOMsPage_2),
            QCoreApplication.translate("Form", "DEMs and DOMs", None),
        )
        self.toolBox_2.setItemText(
            self.toolBox_2.indexOf(self.WellsPage_2),
            QCoreApplication.translate("Form", "Wells", None),
        )
        self.toolBox_2.setItemText(
            self.toolBox_2.indexOf(self.FluidsTreePage_2),
            QCoreApplication.translate("Form", "Fluids > Fluids Tree", None),
        )
        self.toolBox_2.setItemText(
            self.toolBox_2.indexOf(self.FluidsTopologyTree_2),
            QCoreApplication.translate("Form", "Fluids > Topology Tree", None),
        )
        self.toolBox_2.setItemText(
            self.toolBox_2.indexOf(self.BackgroundsTreePage_2),
            QCoreApplication.translate(
                "Form", "Background data > Backgrounds tree", None
            ),
        )
        self.toolBox_2.setItemText(
            self.toolBox_2.indexOf(self.BackgroundsTopologyTree_2),
            QCoreApplication.translate("Form", "Background data > Topology tree", None),
        )
        self.toolBox_2.setItemText(
            self.toolBox_2.indexOf(self.ImagesPage_2),
            QCoreApplication.translate("Form", "Images", None),
        )

    # retranslateUi
