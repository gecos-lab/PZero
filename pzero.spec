# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, collect_all
import pkgutil
import rasterio
import platform
import os
import shutil

system = platform.system()

cwd = os.getcwd()

path = os.path.join(cwd,f'installers/PZero_{system}')

if os.path.isdir(path):
	shutil.rmtree(path)

# list all rasterio and fiona submodules, to include them in the package
additional_packages = list()
for package in pkgutil.iter_modules(rasterio.__path__, prefix="rasterio."):
    additional_packages.append(package.name)

additional_packages.append('vtkmodules.all')


datas, binaries, hiddenimports = collect_all('pzero')

datas = []
datas += collect_data_files('vedo')
datas += collect_data_files('cmocean')
#datas += collect_data_files('PyQt5')

hiddenimports.append(additional_packages)

block_cipher = None


a = Analysis(
    ['pzero.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='pzero',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

shutil.move('dist/',path)
shutil.move('build/',path)