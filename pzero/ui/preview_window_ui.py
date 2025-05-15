# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'preview_windowpMftKg.ui'
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
    QAbstractButton,
    QApplication,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class Ui_PreviewWindow(object):
    def setupUi(self, PreviewWindow):
        if not PreviewWindow.objectName():
            PreviewWindow.setObjectName("PreviewWindow")
        PreviewWindow.resize(845, 538)
        self.centralwidget = QWidget(PreviewWindow)
        self.centralwidget.setObjectName("centralwidget")
        self.horizontalLayout_2 = QHBoxLayout(self.centralwidget)
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.OptionsWidget = QWidget(self.centralwidget)
        self.OptionsWidget.setObjectName("OptionsWidget")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(
            self.OptionsWidget.sizePolicy().hasHeightForWidth()
        )
        self.OptionsWidget.setSizePolicy(sizePolicy)
        self.verticalLayout = QVBoxLayout(self.OptionsWidget)
        self.verticalLayout.setObjectName("verticalLayout")
        self.OptionsLayout = QHBoxLayout()
        self.OptionsLayout.setSpacing(3)
        self.OptionsLayout.setObjectName("OptionsLayout")

        self.verticalLayout.addLayout(self.OptionsLayout)

        self.previewButton = QPushButton(self.OptionsWidget)
        self.previewButton.setObjectName("previewButton")

        self.verticalLayout.addWidget(self.previewButton)

        self.ConfirmButtonBox = QDialogButtonBox(self.OptionsWidget)
        self.ConfirmButtonBox.setObjectName("ConfirmButtonBox")
        sizePolicy.setHeightForWidth(
            self.ConfirmButtonBox.sizePolicy().hasHeightForWidth()
        )
        self.ConfirmButtonBox.setSizePolicy(sizePolicy)
        self.ConfirmButtonBox.setStandardButtons(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        self.ConfirmButtonBox.setCenterButtons(False)

        self.verticalLayout.addWidget(self.ConfirmButtonBox)

        self.horizontalLayout_2.addWidget(
            self.OptionsWidget, 0, Qt.AlignmentFlag.Qt.AlignmentFlag.AlignVCenter
        )

        self.PreviewVerticalFrame = QFrame(self.centralwidget)
        self.PreviewVerticalFrame.setObjectName("PreviewVerticalFrame")
        self.PreviewFrameLayout = QVBoxLayout(self.PreviewVerticalFrame)
        self.PreviewFrameLayout.setObjectName("PreviewFrameLayout")
        self.PreviewLayout = QHBoxLayout()
        self.PreviewLayout.setObjectName("PreviewLayout")

        self.PreviewFrameLayout.addLayout(self.PreviewLayout)

        self.horizontalLayout_2.addWidget(self.PreviewVerticalFrame)

        PreviewWindow.setCentralWidget(self.centralwidget)

        self.retranslateUi(PreviewWindow)

        QMetaObject.connectSlotsByName(PreviewWindow)

    # setupUi

    def retranslateUi(self, PreviewWindow):
        PreviewWindow.setWindowTitle(
            QCoreApplication.translate("PreviewWindow", "Preview Window", None)
        )
        self.previewButton.setText(
            QCoreApplication.translate("PreviewWindow", "Preview", None)
        )

    # retranslateUi
