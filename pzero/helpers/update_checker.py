"""Check packaged releases for updates without blocking application startup."""

import json
import sys

from packaging.version import InvalidVersion, Version
from PySide6.QtCore import QObject, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import QMessageBox

from pzero._version import __version__

LATEST_RELEASE_API = "https://api.github.com/repos/gecos-lab/PZero/releases/latest"
DOWNLOAD_PAGE = "https://github.com/gecos-lab/PZero/releases/latest"


class UpdateChecker(QObject):
    """Make one asynchronous request with a five-second deadline."""

    def __init__(self, parent, current_version):
        super().__init__(parent)
        self.current_version = Version(str(current_version))
        self.manager = QNetworkAccessManager(self)
        self.manager.finished.connect(self._finished)
        self.timeout = QTimer(self)
        self.timeout.setSingleShot(True)
        self._message = None

    def start(self):
        request = QNetworkRequest(QUrl(LATEST_RELEASE_API))
        request.setRawHeader(b"Accept", b"application/vnd.github+json")
        request.setRawHeader(b"User-Agent", b"PZero-Update-Checker")
        reply = self.manager.get(request)
        self.timeout.timeout.connect(reply.abort)
        self.timeout.start(5000)

    def _finished(self, reply):
        self.timeout.stop()
        latest = None
        try:
            if reply.error() == QNetworkReply.NetworkError.NoError:
                release = json.loads(bytes(reply.readAll()))
                if isinstance(release, dict) and not (
                    release.get("draft") or release.get("prerelease")
                ):
                    candidate = Version(release.get("tag_name", ""))
                    if not candidate.is_prerelease and candidate > self.current_version:
                        latest = candidate
        except (ValueError, TypeError):
            pass
        finally:
            reply.deleteLater()

        if latest is not None:
            self._message = QMessageBox(self.parent())
            self._message.setIcon(QMessageBox.Icon.Information)
            self._message.setWindowTitle("PZero update available")
            self._message.setText(
                f"PZero {latest} is available. You are using {self.current_version}."
            )
            download = self._message.addButton(
                "Open download page", QMessageBox.ButtonRole.AcceptRole
            )
            later = self._message.addButton("Later", QMessageBox.ButtonRole.RejectRole)
            self._message.setDefaultButton(later)
            self._message.buttonClicked.connect(
                lambda button: (
                    QDesktopServices.openUrl(QUrl(DOWNLOAD_PAGE))
                    if button == download
                    else None
                )
            )
            self._message.open()


def check_for_updates(parent):
    """Schedule a check only for an executable with a known stable version."""
    if not getattr(sys, "frozen", False):
        return None
    try:
        current_version = Version(__version__)
    except InvalidVersion:
        return None
    if current_version.is_devrelease or current_version.is_prerelease:
        return None
    checker = UpdateChecker(parent, current_version)
    QTimer.singleShot(0, checker.start)
    return checker
