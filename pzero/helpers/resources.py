"""Locate application assets in source checkouts and PyInstaller bundles."""

from pathlib import Path


def resource_path(relative_path):
    return str(Path(__file__).resolve().parents[2] / relative_path)
