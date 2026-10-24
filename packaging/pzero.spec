"""Shared release recipe; build with helper_scripts/build_release.py."""

import os
from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

root = Path(SPECPATH).resolve().parent
sources = root / "pzero" / "pymeshit_app"
sys.path.insert(0, str(sources))
name = os.environ["PZERO_BUILD_NAME"]
arch = os.environ.get("PZERO_BUILD_ARCH") or None

datas = [
    (str(root / "_internal" / "pzero.ico"), "_internal"),
    (str(root / "_internal" / "pzero_splash.png"), "_internal"),
    (str(root / "images" / "Gecos_logo.jpg"), "images"),
    (str(root / "LICENSE.txt"), "."),
]
# The GUI locator and spec_from_file_location require actual source files.
datas += [
    (str(path), str(path.parent.relative_to(root))) for path in sources.rglob("*.py")
]
rio_data, rio_binaries, rio_hidden = collect_all("rasterio")
datas += rio_data + collect_data_files("pyogrio") + collect_data_files("triangle")
hidden = rio_hidden + [
    "Pymeshit_workflow_gui",
    "PiecewiseStructuralComplex",
    "project_storage",
    "pyogrio._geometry",
    "tetgen",
    "triangle",
]
hidden += collect_submodules("Pymeshit")
hidden += collect_submodules(
    "scipy.special",
    filter=lambda name: ".tests" not in name and "._precompute" not in name,
)

a = Analysis(
    [str(root / "pzero.py")],
    pathex=[str(root), str(sources)],
    binaries=rio_binaries,
    datas=datas,
    hiddenimports=hidden,
    hooksconfig={"matplotlib": {"backends": ["QtAgg", "Agg"]}},
    excludes=["PyQt5", "PyQt6", "PySide2", "pytest", "sphinx", "black", "tkinter"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=name,
    console=False,
    upx=False,
    target_arch=arch,
    icon=str(root / "_internal" / "pzero.ico") if sys.platform == "win32" else None,
)
coll = COLLECT(exe, a.binaries, a.datas, name=name, upx=False)
if sys.platform == "darwin":
    app = BUNDLE(coll, name=f"{name}.app", bundle_identifier="org.gecos-lab.pzero")
