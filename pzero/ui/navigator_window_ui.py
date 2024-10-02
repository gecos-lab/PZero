# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'navigator_windowTAXyBZ.ui'
##
## Created by: Qt User Interface Compiler version 6.7.3
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
from PySide6.QtWidgets import (QApplication, QGridLayout, QLabel, QMainWindow,
    QPushButton, QSizePolicy, QVBoxLayout, QWidget)

class Ui_NavWindow(object):
    def setupUi(self, NavWindow):
        if not NavWindow.objectName():
            NavWindow.setObjectName(u"NavWindow")
        NavWindow.resize(540, 95)
        NavWindow.setMinimumSize(QSize(540, 90))
        NavWindow.setMaximumSize(QSize(562, 95))
        self.centralwidget = QWidget(NavWindow)
        self.centralwidget.setObjectName(u"centralwidget")
        self.verticalLayout = QVBoxLayout(self.centralwidget)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.NavGrid = QWidget(self.centralwidget)
        self.NavGrid.setObjectName(u"NavGrid")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.NavGrid.sizePolicy().hasHeightForWidth())
        self.NavGrid.setSizePolicy(sizePolicy)
        self.NavGrid.setMinimumSize(QSize(540, 45))
        self.NavGrid.setMaximumSize(QSize(815, 65))
        self.gridLayout = QGridLayout(self.NavGrid)
        self.gridLayout.setObjectName(u"gridLayout")
        self.ForwardButton = QPushButton(self.NavGrid)
        self.ForwardButton.setObjectName(u"ForwardButton")

        self.gridLayout.addWidget(self.ForwardButton, 0, 2, 1, 1)

        self.BackButton = QPushButton(self.NavGrid)
        self.BackButton.setObjectName(u"BackButton")

        self.gridLayout.addWidget(self.BackButton, 0, 0, 1, 1)

        self.SectionLabel = QLabel(self.NavGrid)
        self.SectionLabel.setObjectName(u"SectionLabel")
        self.SectionLabel.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.SectionLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.gridLayout.addWidget(self.SectionLabel, 0, 1, 1, 1)


        self.verticalLayout.addWidget(self.NavGrid)

        NavWindow.setCentralWidget(self.centralwidget)

        self.retranslateUi(NavWindow)

        QMetaObject.connectSlotsByName(NavWindow)
    # setupUi

    def retranslateUi(self, NavWindow):
        NavWindow.setWindowTitle(QCoreApplication.translate("NavWindow", u"Navigator", None))
        self.ForwardButton.setText(QCoreApplication.translate("NavWindow", u">>", None))
        self.BackButton.setText(QCoreApplication.translate("NavWindow", u"<<", None))
        self.SectionLabel.setText("")
    # retranslateUi

