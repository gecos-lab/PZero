# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'project_windowswFJil.ui'
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
    QHBoxLayout,
    QHeaderView,
    QMainWindow,
    QMenu,
    QMenuBar,
    QPlainTextEdit,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)


class Ui_ProjectWindow(object):
    def setupUi(self, ProjectWindow):
        if not ProjectWindow.objectName():
            ProjectWindow.setObjectName("ProjectWindow")
        ProjectWindow.resize(900, 600)
        self.actionProjectNew = QAction(ProjectWindow)
        self.actionProjectNew.setObjectName("actionProjectNew")
        self.actionProjectOpen = QAction(ProjectWindow)
        self.actionProjectOpen.setObjectName("actionProjectOpen")
        self.actionProjectSave = QAction(ProjectWindow)
        self.actionProjectSave.setObjectName("actionProjectSave")
        self.actionImportGocad = QAction(ProjectWindow)
        self.actionImportGocad.setObjectName("actionImportGocad")
        self.actionImportGocadXsection = QAction(ProjectWindow)
        self.actionImportGocadXsection.setObjectName("actionImportGocadXsection")
        self.actionImportBoundary = QAction(ProjectWindow)
        self.actionImportBoundary.setObjectName("actionImportBoundary")
        self.actionImportPC = QAction(ProjectWindow)
        self.actionImportPC.setObjectName("actionImportPC")
        self.actionImportPyVista = QAction(ProjectWindow)
        self.actionImportPyVista.setObjectName("actionImportPyVista")
        self.actionImportSHP = QAction(ProjectWindow)
        self.actionImportSHP.setObjectName("actionImportSHP")
        self.actionImportDEM = QAction(ProjectWindow)
        self.actionImportDEM.setObjectName("actionImportDEM")
        self.actionImportOrthoImage = QAction(ProjectWindow)
        self.actionImportOrthoImage.setObjectName("actionImportOrthoImage")
        self.actionImportXSectionImage = QAction(ProjectWindow)
        self.actionImportXSectionImage.setObjectName("actionImportXSectionImage")
        self.actionImportWellData = QAction(ProjectWindow)
        self.actionImportWellData.setObjectName("actionImportWellData")
        self.actionImportSEGY = QAction(ProjectWindow)
        self.actionImportSEGY.setObjectName("actionImportSEGY")
        self.actionExportCAD = QAction(ProjectWindow)
        self.actionExportCAD.setObjectName("actionExportCAD")
        self.actionExportVTK = QAction(ProjectWindow)
        self.actionExportVTK.setObjectName("actionExportVTK")
        self.actionExportCSV = QAction(ProjectWindow)
        self.actionExportCSV.setObjectName("actionExportCSV")
        self.actionQuit = QAction(ProjectWindow)
        self.actionQuit.setObjectName("actionQuit")
        self.actionCloneEntity = QAction(ProjectWindow)
        self.actionCloneEntity.setObjectName("actionCloneEntity")
        self.actionRemoveEntity = QAction(ProjectWindow)
        self.actionRemoveEntity.setObjectName("actionRemoveEntity")
        self.actionConnectedParts = QAction(ProjectWindow)
        self.actionConnectedParts.setObjectName("actionConnectedParts")
        self.actionMergeEntities = QAction(ProjectWindow)
        self.actionMergeEntities.setObjectName("actionMergeEntities")
        self.actionSplitMultipart = QAction(ProjectWindow)
        self.actionSplitMultipart.setObjectName("actionSplitMultipart")
        self.actionDecimatePointCloud = QAction(ProjectWindow)
        self.actionDecimatePointCloud.setObjectName("actionDecimatePointCloud")
        self.actionAddTexture = QAction(ProjectWindow)
        self.actionAddTexture.setObjectName("actionAddTexture")
        self.actionRemoveTexture = QAction(ProjectWindow)
        self.actionRemoveTexture.setObjectName("actionRemoveTexture")
        self.actionAddProperty = QAction(ProjectWindow)
        self.actionAddProperty.setObjectName("actionAddProperty")
        self.actionRemoveProperty = QAction(ProjectWindow)
        self.actionRemoveProperty.setObjectName("actionRemoveProperty")
        self.actionCalculateNormals = QAction(ProjectWindow)
        self.actionCalculateNormals.setObjectName("actionCalculateNormals")
        self.actionCalculateLineations = QAction(ProjectWindow)
        self.actionCalculateLineations.setObjectName("actionCalculateLineations")
        self.actionBuildOctree = QAction(ProjectWindow)
        self.actionBuildOctree.setObjectName("actionBuildOctree")
        self.actionDelaunay2D = QAction(ProjectWindow)
        self.actionDelaunay2D.setObjectName("actionDelaunay2D")
        self.actionPoisson = QAction(ProjectWindow)
        self.actionPoisson.setObjectName("actionPoisson")
        self.actionLoopStructural = QAction(ProjectWindow)
        self.actionLoopStructural.setObjectName("actionLoopStructural")
        self.actionSurfaceSmoothing = QAction(ProjectWindow)
        self.actionSurfaceSmoothing.setObjectName("actionSurfaceSmoothing")
        self.actionSubdivisionResampling = QAction(ProjectWindow)
        self.actionSubdivisionResampling.setObjectName("actionSubdivisionResampling")
        self.actionDecimationPro = QAction(ProjectWindow)
        self.actionDecimationPro.setObjectName("actionDecimationPro")
        self.actionDecimationQuadric = QAction(ProjectWindow)
        self.actionDecimationQuadric.setObjectName("actionDecimationQuadric")
        self.actionRetopologize = QAction(ProjectWindow)
        self.actionRetopologize.setObjectName("actionRetopologize")
        self.actionExtrusion = QAction(ProjectWindow)
        self.actionExtrusion.setObjectName("actionExtrusion")
        self.actionXSectionIntersection = QAction(ProjectWindow)
        self.actionXSectionIntersection.setObjectName("actionXSectionIntersection")
        self.actionProject2XSection = QAction(ProjectWindow)
        self.actionProject2XSection.setObjectName("actionProject2XSection")
        self.actionProject2DEM = QAction(ProjectWindow)
        self.actionProject2DEM.setObjectName("actionProject2DEM")
        self.actionSplitSurfaces = QAction(ProjectWindow)
        self.actionSplitSurfaces.setObjectName("actionSplitSurfaces")
        self.action3DView = QAction(ProjectWindow)
        self.action3DView.setObjectName("action3DView")
        self.actionMapView = QAction(ProjectWindow)
        self.actionMapView.setObjectName("actionMapView")
        self.actionXSectionView = QAction(ProjectWindow)
        self.actionXSectionView.setObjectName("actionXSectionView")
        self.actionWellLogView = QAction(ProjectWindow)
        self.actionWellLogView.setObjectName("actionWellLogView")
        self.actionStereoplotView = QAction(ProjectWindow)
        self.actionStereoplotView.setObjectName("actionStereoplotView")
        self.actionXYPlotView = QAction(ProjectWindow)
        self.actionXYPlotView.setObjectName("actionXYPlotView")
        self.actionHistogramView = QAction(ProjectWindow)
        self.actionHistogramView.setObjectName("actionHistogramView")
        self.actionHelp = QAction(ProjectWindow)
        self.actionHelp.setObjectName("actionHelp")
        self.actionAbout = QAction(ProjectWindow)
        self.actionAbout.setObjectName("actionAbout")
        self.actionShowInfoOnEntities = QAction(ProjectWindow)
        self.actionShowInfoOnEntities.setObjectName("actionShowInfoOnEntities")
        self.actionSurface_Density = QAction(ProjectWindow)
        self.actionSurface_Density.setObjectName("actionSurface_Density")
        self.actionRoughness = QAction(ProjectWindow)
        self.actionRoughness.setObjectName("actionRoughness")
        self.actionCurvature = QAction(ProjectWindow)
        self.actionCurvature.setObjectName("actionCurvature")
        self.actionThreshold = QAction(ProjectWindow)
        self.actionThreshold.setObjectName("actionThreshold")
        self.actionCalculate_Dip_Direction = QAction(ProjectWindow)
        self.actionCalculate_Dip_Direction.setObjectName(
            "actionCalculate_Dip_Direction"
        )
        self.actionCalculate_Plunge_Trend = QAction(ProjectWindow)
        self.actionCalculate_Plunge_Trend.setObjectName("actionCalculate_Plunge_Trend")
        self.actionTransformSelectedCRS = QAction(ProjectWindow)
        self.actionTransformSelectedCRS.setObjectName("actionTransformSelectedCRS")
        self.actionListCRS = QAction(ProjectWindow)
        self.actionListCRS.setObjectName("actionListCRS")
        self.centralwidget = QWidget(ProjectWindow)
        self.centralwidget.setObjectName("centralwidget")
        self.horizontalLayout = QHBoxLayout(self.centralwidget)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.splitter = QSplitter(self.centralwidget)
        self.splitter.setObjectName("splitter")
        self.splitter.setOrientation(Qt.Orientation.Vertical)
        self.tabWidgetTopLeft = QTabWidget(self.splitter)
        self.tabWidgetTopLeft.setObjectName("tabWidgetTopLeft")
        self.tabGeology = QWidget()
        self.tabGeology.setObjectName("tabGeology")
        self.horizontalLayout_2 = QHBoxLayout(self.tabGeology)
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.GeologyTableView = QTableView(self.tabGeology)
        self.GeologyTableView.setObjectName("GeologyTableView")
        self.GeologyTableView.setSortingEnabled(True)

        self.horizontalLayout_2.addWidget(self.GeologyTableView)

        self.tabWidgetTopLeft.addTab(self.tabGeology, "")
        self.tabFluids = QWidget()
        self.tabFluids.setObjectName("tabFluids")
        self.horizontalLayout_3 = QHBoxLayout(self.tabFluids)
        self.horizontalLayout_3.setObjectName("horizontalLayout_3")
        self.FluidsTableView = QTableView(self.tabFluids)
        self.FluidsTableView.setObjectName("FluidsTableView")
        self.FluidsTableView.setSortingEnabled(True)

        self.horizontalLayout_3.addWidget(self.FluidsTableView)

        self.tabWidgetTopLeft.addTab(self.tabFluids, "")
        self.tabBackgrounds = QWidget()
        self.tabBackgrounds.setObjectName("tabBackgrounds")
        self.horizontalLayout_4 = QHBoxLayout(self.tabBackgrounds)
        self.horizontalLayout_4.setObjectName("horizontalLayout_4")
        self.BackgroundsTableView = QTableView(self.tabBackgrounds)
        self.BackgroundsTableView.setObjectName("BackgroundsTableView")
        self.BackgroundsTableView.setSortingEnabled(True)

        self.horizontalLayout_4.addWidget(self.BackgroundsTableView)

        self.tabWidgetTopLeft.addTab(self.tabBackgrounds, "")
        self.tabDOMs = QWidget()
        self.tabDOMs.setObjectName("tabDOMs")
        self.horizontalLayout_5 = QHBoxLayout(self.tabDOMs)
        self.horizontalLayout_5.setObjectName("horizontalLayout_5")
        self.DOMsTableView = QTableView(self.tabDOMs)
        self.DOMsTableView.setObjectName("DOMsTableView")
        self.DOMsTableView.setSortingEnabled(True)

        self.horizontalLayout_5.addWidget(self.DOMsTableView)

        self.tabWidgetTopLeft.addTab(self.tabDOMs, "")
        self.tabImages = QWidget()
        self.tabImages.setObjectName("tabImages")
        self.horizontalLayout_6 = QHBoxLayout(self.tabImages)
        self.horizontalLayout_6.setObjectName("horizontalLayout_6")
        self.ImagesTableView = QTableView(self.tabImages)
        self.ImagesTableView.setObjectName("ImagesTableView")
        self.ImagesTableView.setSortingEnabled(True)

        self.horizontalLayout_6.addWidget(self.ImagesTableView)

        self.tabWidgetTopLeft.addTab(self.tabImages, "")
        self.tabMeshes = QWidget()
        self.tabMeshes.setObjectName("tabMeshes")
        self.horizontalLayout_7 = QHBoxLayout(self.tabMeshes)
        self.horizontalLayout_7.setObjectName("horizontalLayout_7")
        self.Meshes3DTableView = QTableView(self.tabMeshes)
        self.Meshes3DTableView.setObjectName("Meshes3DTableView")
        self.Meshes3DTableView.setSortingEnabled(True)

        self.horizontalLayout_7.addWidget(self.Meshes3DTableView)

        self.tabWidgetTopLeft.addTab(self.tabMeshes, "")
        self.tabBoundaries = QWidget()
        self.tabBoundaries.setObjectName("tabBoundaries")
        self.horizontalLayout_8 = QHBoxLayout(self.tabBoundaries)
        self.horizontalLayout_8.setObjectName("horizontalLayout_8")
        self.BoundariesTableView = QTableView(self.tabBoundaries)
        self.BoundariesTableView.setObjectName("BoundariesTableView")
        self.BoundariesTableView.setSortingEnabled(True)

        self.horizontalLayout_8.addWidget(self.BoundariesTableView)

        self.tabWidgetTopLeft.addTab(self.tabBoundaries, "")
        self.tabXSections = QWidget()
        self.tabXSections.setObjectName("tabXSections")
        self.horizontalLayout_9 = QHBoxLayout(self.tabXSections)
        self.horizontalLayout_9.setObjectName("horizontalLayout_9")
        self.XSectionsTableView = QTableView(self.tabXSections)
        self.XSectionsTableView.setObjectName("XSectionsTableView")
        self.XSectionsTableView.setSortingEnabled(True)

        self.horizontalLayout_9.addWidget(self.XSectionsTableView)

        self.tabWidgetTopLeft.addTab(self.tabXSections, "")
        self.tabWells = QWidget()
        self.tabWells.setObjectName("tabWells")
        self.horizontalLayout_10 = QHBoxLayout(self.tabWells)
        self.horizontalLayout_10.setObjectName("horizontalLayout_10")
        self.WellsTableView = QTableView(self.tabWells)
        self.WellsTableView.setObjectName("WellsTableView")
        self.WellsTableView.setSortingEnabled(True)

        self.horizontalLayout_10.addWidget(self.WellsTableView)

        self.tabWidgetTopLeft.addTab(self.tabWells, "")
        self.splitter.addWidget(self.tabWidgetTopLeft)
        self.tabWidgetBottomLeft = QTabWidget(self.splitter)
        self.tabWidgetBottomLeft.setObjectName("tabWidgetBottomLeft")
        self.tabLegend = QWidget()
        self.tabLegend.setObjectName("tabLegend")
        self.horizontalLayout_11 = QHBoxLayout(self.tabLegend)
        self.horizontalLayout_11.setObjectName("horizontalLayout_11")
        self.LegendTreeWidget = QTreeWidget(self.tabLegend)
        __qtreewidgetitem = QTreeWidgetItem()
        __qtreewidgetitem.setText(0, "1")
        self.LegendTreeWidget.setHeaderItem(__qtreewidgetitem)
        self.LegendTreeWidget.setObjectName("LegendTreeWidget")

        self.horizontalLayout_11.addWidget(self.LegendTreeWidget)

        self.tabWidgetBottomLeft.addTab(self.tabLegend, "")
        self.tabProperties = QWidget()
        self.tabProperties.setObjectName("tabProperties")
        self.horizontalLayout_12 = QHBoxLayout(self.tabProperties)
        self.horizontalLayout_12.setObjectName("horizontalLayout_12")
        self.PropertiesTableWidget = QTableWidget(self.tabProperties)
        self.PropertiesTableWidget.setObjectName("PropertiesTableWidget")

        self.horizontalLayout_12.addWidget(self.PropertiesTableWidget)

        self.tabWidgetBottomLeft.addTab(self.tabProperties, "")
        self.tabTerminal = QWidget()
        self.tabTerminal.setObjectName("tabTerminal")
        self.horizontalLayout_13 = QHBoxLayout(self.tabTerminal)
        self.horizontalLayout_13.setObjectName("horizontalLayout_13")
        self.TextTerminal = QPlainTextEdit(self.tabTerminal)
        self.TextTerminal.setObjectName("TextTerminal")

        self.horizontalLayout_13.addWidget(self.TextTerminal)

        self.tabWidgetBottomLeft.addTab(self.tabTerminal, "")
        self.splitter.addWidget(self.tabWidgetBottomLeft)

        self.horizontalLayout.addWidget(self.splitter)

        ProjectWindow.setCentralWidget(self.centralwidget)
        self.menubar = QMenuBar(ProjectWindow)
        self.menubar.setObjectName("menubar")
        self.menubar.setGeometry(QRect(0, 0, 900, 33))
        self.menubar.setNativeMenuBar(False)
        self.menuFile = QMenu(self.menubar)
        self.menuFile.setObjectName("menuFile")
        self.menuFile.setTearOffEnabled(True)
        self.menuEntities = QMenu(self.menubar)
        self.menuEntities.setObjectName("menuEntities")
        self.menuEntities.setTearOffEnabled(True)
        self.menuInterpolation = QMenu(self.menubar)
        self.menuInterpolation.setObjectName("menuInterpolation")
        self.menuInterpolation.setTearOffEnabled(True)
        self.menuWindows = QMenu(self.menubar)
        self.menuWindows.setObjectName("menuWindows")
        self.menuWindows.setTearOffEnabled(True)
        self.menuHelp = QMenu(self.menubar)
        self.menuHelp.setObjectName("menuHelp")
        self.menuHelp.setTearOffEnabled(True)
        self.menuPointClouds = QMenu(self.menubar)
        self.menuPointClouds.setObjectName("menuPointClouds")
        self.menuPointClouds.setTearOffEnabled(True)
        self.menuSurfaces = QMenu(self.menubar)
        self.menuSurfaces.setObjectName("menuSurfaces")
        self.menuSurfaces.setTearOffEnabled(True)
        self.menuLines = QMenu(self.menubar)
        self.menuLines.setObjectName("menuLines")
        self.menuLines.setTearOffEnabled(True)
        self.menuProjection = QMenu(self.menubar)
        self.menuProjection.setObjectName("menuProjection")
        self.menuProjection.setTearOffEnabled(True)
        self.menuProperties = QMenu(self.menubar)
        self.menuProperties.setObjectName("menuProperties")
        self.menuProperties.setTearOffEnabled(True)
        self.menuCRS = QMenu(self.menubar)
        self.menuCRS.setObjectName("menuCRS")
        ProjectWindow.setMenuBar(self.menubar)
        self.statusbar = QStatusBar(ProjectWindow)
        self.statusbar.setObjectName("statusbar")
        ProjectWindow.setStatusBar(self.statusbar)

        self.menubar.addAction(self.menuFile.menuAction())
        self.menubar.addAction(self.menuEntities.menuAction())
        self.menubar.addAction(self.menuPointClouds.menuAction())
        self.menubar.addAction(self.menuLines.menuAction())
        self.menubar.addAction(self.menuSurfaces.menuAction())
        self.menubar.addAction(self.menuProjection.menuAction())
        self.menubar.addAction(self.menuInterpolation.menuAction())
        self.menubar.addAction(self.menuProperties.menuAction())
        self.menubar.addAction(self.menuCRS.menuAction())
        self.menubar.addAction(self.menuWindows.menuAction())
        self.menubar.addAction(self.menuHelp.menuAction())
        self.menuFile.addAction(self.actionProjectNew)
        self.menuFile.addAction(self.actionProjectOpen)
        self.menuFile.addAction(self.actionProjectSave)
        self.menuFile.addSeparator()
        self.menuFile.addAction(self.actionImportGocad)
        self.menuFile.addAction(self.actionImportGocadXsection)
        self.menuFile.addAction(self.actionImportBoundary)
        self.menuFile.addAction(self.actionImportPC)
        self.menuFile.addAction(self.actionImportPyVista)
        self.menuFile.addAction(self.actionImportSHP)
        self.menuFile.addAction(self.actionImportDEM)
        self.menuFile.addAction(self.actionImportOrthoImage)
        self.menuFile.addAction(self.actionImportXSectionImage)
        self.menuFile.addAction(self.actionImportWellData)
        self.menuFile.addAction(self.actionImportSEGY)
        self.menuFile.addSeparator()
        self.menuFile.addAction(self.actionExportCAD)
        self.menuFile.addAction(self.actionExportVTK)
        self.menuFile.addAction(self.actionExportCSV)
        self.menuFile.addSeparator()
        self.menuFile.addAction(self.actionQuit)
        self.menuEntities.addAction(self.actionCloneEntity)
        self.menuEntities.addAction(self.actionRemoveEntity)
        self.menuEntities.addSeparator()
        self.menuEntities.addAction(self.actionConnectedParts)
        self.menuEntities.addAction(self.actionMergeEntities)
        self.menuEntities.addAction(self.actionSplitMultipart)
        self.menuEntities.addSeparator()
        self.menuEntities.addAction(self.actionShowInfoOnEntities)
        self.menuInterpolation.addAction(self.actionDelaunay2D)
        self.menuInterpolation.addAction(self.actionPoisson)
        self.menuInterpolation.addAction(self.actionLoopStructural)
        self.menuInterpolation.addSeparator()
        self.menuInterpolation.addAction(self.actionDecimationPro)
        self.menuInterpolation.addAction(self.actionDecimationQuadric)
        self.menuInterpolation.addAction(self.actionSubdivisionResampling)
        self.menuInterpolation.addAction(self.actionSurfaceSmoothing)
        self.menuInterpolation.addAction(self.actionRetopologize)
        self.menuWindows.addAction(self.action3DView)
        self.menuWindows.addAction(self.actionMapView)
        self.menuWindows.addAction(self.actionXSectionView)
        self.menuWindows.addAction(self.actionWellLogView)
        self.menuWindows.addSeparator()
        self.menuWindows.addAction(self.actionStereoplotView)
        self.menuWindows.addAction(self.actionXYPlotView)
        self.menuWindows.addAction(self.actionHistogramView)
        self.menuHelp.addAction(self.actionHelp)
        self.menuHelp.addAction(self.actionAbout)
        self.menuPointClouds.addAction(self.actionBuildOctree)
        self.menuPointClouds.addAction(self.actionDecimatePointCloud)
        self.menuPointClouds.addAction(self.actionSurface_Density)
        self.menuPointClouds.addAction(self.actionRoughness)
        self.menuPointClouds.addAction(self.actionCurvature)
        self.menuPointClouds.addAction(self.actionThreshold)
        self.menuSurfaces.addAction(self.actionSplitSurfaces)
        self.menuProjection.addAction(self.actionProject2XSection)
        self.menuProjection.addAction(self.actionXSectionIntersection)
        self.menuProjection.addAction(self.actionProject2DEM)
        self.menuProjection.addAction(self.actionExtrusion)
        self.menuProperties.addAction(self.actionAddProperty)
        self.menuProperties.addAction(self.actionRemoveProperty)
        self.menuProperties.addSeparator()
        self.menuProperties.addAction(self.actionCalculateNormals)
        self.menuProperties.addAction(self.actionCalculate_Dip_Direction)
        self.menuProperties.addAction(self.actionCalculateLineations)
        self.menuProperties.addAction(self.actionCalculate_Plunge_Trend)
        self.menuProperties.addSeparator()
        self.menuProperties.addAction(self.actionAddTexture)
        self.menuProperties.addAction(self.actionRemoveTexture)
        self.menuCRS.addAction(self.actionTransformSelectedCRS)
        self.menuCRS.addAction(self.actionListCRS)

        self.retranslateUi(ProjectWindow)

        self.tabWidgetTopLeft.setCurrentIndex(0)
        self.tabWidgetBottomLeft.setCurrentIndex(0)

        QMetaObject.connectSlotsByName(ProjectWindow)

    # setupUi

    def retranslateUi(self, ProjectWindow):
        ProjectWindow.setWindowTitle(
            QCoreApplication.translate("ProjectWindow", "MainWindow", None)
        )
        self.actionProjectNew.setText(
            QCoreApplication.translate("ProjectWindow", "New Project", None)
        )
        self.actionProjectOpen.setText(
            QCoreApplication.translate("ProjectWindow", "Open Project", None)
        )
        self.actionProjectSave.setText(
            QCoreApplication.translate("ProjectWindow", "Save Project", None)
        )
        self.actionImportGocad.setText(
            QCoreApplication.translate("ProjectWindow", "Import Gocad", None)
        )
        self.actionImportGocadXsection.setText(
            QCoreApplication.translate("ProjectWindow", "Import Gocad X-section", None)
        )
        self.actionImportBoundary.setText(
            QCoreApplication.translate("ProjectWindow", "Import Gocad Boundary", None)
        )
        self.actionImportPC.setText(
            QCoreApplication.translate("ProjectWindow", "Import Point Cloud", None)
        )
        self.actionImportPyVista.setText(
            QCoreApplication.translate("ProjectWindow", "Import PyVista", None)
        )
        self.actionImportSHP.setText(
            QCoreApplication.translate("ProjectWindow", "Import SHP-file", None)
        )
        self.actionImportDEM.setText(
            QCoreApplication.translate("ProjectWindow", "Import DEM", None)
        )
        self.actionImportOrthoImage.setText(
            QCoreApplication.translate("ProjectWindow", "Import OrthoImage", None)
        )
        self.actionImportXSectionImage.setText(
            QCoreApplication.translate("ProjectWindow", "Import X-section Image", None)
        )
        self.actionImportWellData.setText(
            QCoreApplication.translate("ProjectWindow", "Import Well Data", None)
        )
        self.actionImportSEGY.setText(
            QCoreApplication.translate("ProjectWindow", "Import SEGY", None)
        )
        self.actionExportCAD.setText(
            QCoreApplication.translate("ProjectWindow", "Export CAD", None)
        )
        self.actionExportVTK.setText(
            QCoreApplication.translate("ProjectWindow", "Export VTK", None)
        )
        self.actionExportCSV.setText(
            QCoreApplication.translate("ProjectWindow", "Export CSV", None)
        )
        self.actionQuit.setText(
            QCoreApplication.translate("ProjectWindow", "Quit", None)
        )
        self.actionCloneEntity.setText(
            QCoreApplication.translate("ProjectWindow", "Clone Entity", None)
        )
        self.actionRemoveEntity.setText(
            QCoreApplication.translate("ProjectWindow", "Remove Entity", None)
        )
        self.actionConnectedParts.setText(
            QCoreApplication.translate("ProjectWindow", "Connected Parts", None)
        )
        self.actionMergeEntities.setText(
            QCoreApplication.translate("ProjectWindow", "Merge Entities", None)
        )
        self.actionSplitMultipart.setText(
            QCoreApplication.translate(
                "ProjectWindow", "Split Multipart Entities", None
            )
        )
        self.actionDecimatePointCloud.setText(
            QCoreApplication.translate("ProjectWindow", "Decimate PC", None)
        )
        self.actionAddTexture.setText(
            QCoreApplication.translate("ProjectWindow", "Add Texture", None)
        )
        self.actionRemoveTexture.setText(
            QCoreApplication.translate("ProjectWindow", "Remove Texture", None)
        )
        self.actionAddProperty.setText(
            QCoreApplication.translate("ProjectWindow", "Add Property", None)
        )
        self.actionRemoveProperty.setText(
            QCoreApplication.translate("ProjectWindow", "Remove Property", None)
        )
        self.actionCalculateNormals.setText(
            QCoreApplication.translate("ProjectWindow", "Calculate Normals", None)
        )
        self.actionCalculateLineations.setText(
            QCoreApplication.translate("ProjectWindow", "Calculate Lineations", None)
        )
        self.actionBuildOctree.setText(
            QCoreApplication.translate("ProjectWindow", "Build Octree", None)
        )
        self.actionDelaunay2D.setText(
            QCoreApplication.translate("ProjectWindow", "Delaunay 2D", None)
        )
        self.actionPoisson.setText(
            QCoreApplication.translate("ProjectWindow", "Poisson", None)
        )
        self.actionLoopStructural.setText(
            QCoreApplication.translate("ProjectWindow", "LoopStructural Implicit", None)
        )
        self.actionSurfaceSmoothing.setText(
            QCoreApplication.translate("ProjectWindow", "Surface Smoothing", None)
        )
        self.actionSubdivisionResampling.setText(
            QCoreApplication.translate("ProjectWindow", "Subdivision Resampling", None)
        )
        self.actionDecimationPro.setText(
            QCoreApplication.translate("ProjectWindow", "Decimation Pro", None)
        )
        self.actionDecimationQuadric.setText(
            QCoreApplication.translate("ProjectWindow", "Decimation Quadric", None)
        )
        self.actionRetopologize.setText(
            QCoreApplication.translate("ProjectWindow", "Retopologize", None)
        )
        self.actionExtrusion.setText(
            QCoreApplication.translate("ProjectWindow", "Extrusion", None)
        )
        self.actionXSectionIntersection.setText(
            QCoreApplication.translate("ProjectWindow", "X-section Intersection", None)
        )
        self.actionProject2XSection.setText(
            QCoreApplication.translate("ProjectWindow", "Project to X-section", None)
        )
        self.actionProject2DEM.setText(
            QCoreApplication.translate("ProjectWindow", "Project to DEM", None)
        )
        self.actionSplitSurfaces.setText(
            QCoreApplication.translate("ProjectWindow", "Split Surfaces", None)
        )
        self.action3DView.setText(
            QCoreApplication.translate("ProjectWindow", "3D View", None)
        )
        self.actionMapView.setText(
            QCoreApplication.translate("ProjectWindow", "Map View", None)
        )
        self.actionXSectionView.setText(
            QCoreApplication.translate("ProjectWindow", "X-section View", None)
        )
        self.actionWellLogView.setText(
            QCoreApplication.translate("ProjectWindow", "Well Log View", None)
        )
        self.actionStereoplotView.setText(
            QCoreApplication.translate("ProjectWindow", "Stereoplot View", None)
        )
        self.actionXYPlotView.setText(
            QCoreApplication.translate("ProjectWindow", "XY Plot View", None)
        )
        self.actionHistogramView.setText(
            QCoreApplication.translate("ProjectWindow", "Histogram View", None)
        )
        self.actionHelp.setText(
            QCoreApplication.translate("ProjectWindow", "PZero Help", None)
        )
        self.actionAbout.setText(
            QCoreApplication.translate("ProjectWindow", "About PZero", None)
        )
        self.actionShowInfoOnEntities.setText(
            QCoreApplication.translate("ProjectWindow", "Show Info on Entities", None)
        )
        self.actionSurface_Density.setText(
            QCoreApplication.translate("ProjectWindow", "Surface Density", None)
        )
        self.actionRoughness.setText(
            QCoreApplication.translate("ProjectWindow", "Roughness", None)
        )
        self.actionCurvature.setText(
            QCoreApplication.translate("ProjectWindow", "Curvature", None)
        )
        self.actionThreshold.setText(
            QCoreApplication.translate("ProjectWindow", "Threshold", None)
        )
        self.actionCalculate_Dip_Direction.setText(
            QCoreApplication.translate("ProjectWindow", "Calculate Dip/Direction", None)
        )
        self.actionCalculate_Plunge_Trend.setText(
            QCoreApplication.translate("ProjectWindow", "Calculate Plunge/Trend", None)
        )
        self.actionTransformSelectedCRS.setText(
            QCoreApplication.translate("ProjectWindow", "Transform Entities CRS", None)
        )
        self.actionListCRS.setText(
            QCoreApplication.translate("ProjectWindow", "List CRS", None)
        )
        self.tabWidgetTopLeft.setTabText(
            self.tabWidgetTopLeft.indexOf(self.tabGeology),
            QCoreApplication.translate("ProjectWindow", "Geology", None),
        )
        self.tabWidgetTopLeft.setTabText(
            self.tabWidgetTopLeft.indexOf(self.tabFluids),
            QCoreApplication.translate("ProjectWindow", "Fluids", None),
        )
        self.tabWidgetTopLeft.setTabText(
            self.tabWidgetTopLeft.indexOf(self.tabBackgrounds),
            QCoreApplication.translate("ProjectWindow", "Background", None),
        )
        self.tabWidgetTopLeft.setTabText(
            self.tabWidgetTopLeft.indexOf(self.tabDOMs),
            QCoreApplication.translate("ProjectWindow", "DEMs and DOMs", None),
        )
        self.tabWidgetTopLeft.setTabText(
            self.tabWidgetTopLeft.indexOf(self.tabImages),
            QCoreApplication.translate("ProjectWindow", "Images", None),
        )
        self.tabWidgetTopLeft.setTabText(
            self.tabWidgetTopLeft.indexOf(self.tabMeshes),
            QCoreApplication.translate("ProjectWindow", "Meshes and Grids", None),
        )
        self.tabWidgetTopLeft.setTabText(
            self.tabWidgetTopLeft.indexOf(self.tabBoundaries),
            QCoreApplication.translate("ProjectWindow", "Boundaries", None),
        )
        self.tabWidgetTopLeft.setTabText(
            self.tabWidgetTopLeft.indexOf(self.tabXSections),
            QCoreApplication.translate("ProjectWindow", "X Sections", None),
        )
        self.tabWidgetTopLeft.setTabText(
            self.tabWidgetTopLeft.indexOf(self.tabWells),
            QCoreApplication.translate("ProjectWindow", "Wells", None),
        )
        self.tabWidgetBottomLeft.setTabText(
            self.tabWidgetBottomLeft.indexOf(self.tabLegend),
            QCoreApplication.translate("ProjectWindow", "Legend", None),
        )
        self.tabWidgetBottomLeft.setTabText(
            self.tabWidgetBottomLeft.indexOf(self.tabProperties),
            QCoreApplication.translate("ProjectWindow", "Properties", None),
        )
        self.tabWidgetBottomLeft.setTabText(
            self.tabWidgetBottomLeft.indexOf(self.tabTerminal),
            QCoreApplication.translate("ProjectWindow", "Terminal", None),
        )
        self.menuFile.setTitle(
            QCoreApplication.translate("ProjectWindow", "File", None)
        )
        self.menuEntities.setTitle(
            QCoreApplication.translate("ProjectWindow", "Entities", None)
        )
        self.menuInterpolation.setTitle(
            QCoreApplication.translate("ProjectWindow", "Interpolation", None)
        )
        self.menuWindows.setTitle(
            QCoreApplication.translate("ProjectWindow", "Windows", None)
        )
        self.menuHelp.setTitle(
            QCoreApplication.translate("ProjectWindow", "Help", None)
        )
        self.menuPointClouds.setTitle(
            QCoreApplication.translate("ProjectWindow", "Point Clouds", None)
        )
        self.menuSurfaces.setTitle(
            QCoreApplication.translate("ProjectWindow", "Surfaces", None)
        )
        self.menuLines.setTitle(
            QCoreApplication.translate("ProjectWindow", "Lines", None)
        )
        self.menuProjection.setTitle(
            QCoreApplication.translate("ProjectWindow", "Projection", None)
        )
        self.menuProperties.setTitle(
            QCoreApplication.translate("ProjectWindow", "Properties", None)
        )
        self.menuCRS.setTitle(QCoreApplication.translate("ProjectWindow", "CRS", None))

    # retranslateUi
