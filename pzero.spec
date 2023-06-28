# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, collect_all
import pkgutil
import rasterio
import rasterio.sample
import platform
import os
import shutil
import shapely
import sys
import glob


system = platform.system()

cwd = os.getcwd()

path = os.path.join(cwd,f'installers/PZero_{system}')

if os.path.isdir(path):
	shutil.rmtree(path)

# list all rasterio and fiona submodules, to include them in the package
additional_packages = list()
for package in pkgutil.iter_modules(rasterio.__path__, prefix="rasterio."):
    additional_packages.append(package.name)

for package in pkgutil.iter_modules(rasterio.__path__, prefix="rasterio.sample"):
    additional_packages.append(package.name)

for package in pkgutil.iter_modules(rasterio.__path__, prefix="rasterio.io"):
    additional_packages.append(package.name)

for package in pkgutil.iter_modules(rasterio.__path__, prefix="rasterio._io"):
    additional_packages.append(package.name)


rasterio_imports_paths = glob.glob(r'C:\ProgramData\Anaconda2\envs\wps_env36\Lib\site-packages\rasterio\*.py')
rasterio_imports = ['rasterio._shim']

for item in rasterio_imports_paths:
    current_module_filename = os.path.split(item)[-1]
    current_module_filename = 'rasterio.'+current_module_filename.replace('.py', '')
    additional_packages.append(current_module_filename)



additional_packages.append('vtkmodules.all')

datas, binaries, hiddenimports = collect_all('pzero')
datas += collect_data_files('vedo')
datas += collect_data_files('cmocean')
datas += collect_data_files('shapely')
datas += collect_data_files('rasterio')

if os.getenv('CONDA_PREFIX', ''):
	# path to general lib directory
	LIB_DIR = os.path.join(sys.prefix, 'lib')

	# check if geos frozen lib name is existent
	# at least with PyInstaller==3.4 it otherwise does not get created
	if not glob.glob(os.path.join(LIB_DIR, 'libgeos_c-*.so.*')):
		# otherwise create a new symlink to be copied to the frozen target
		# conda package. (from shapely.geos source code)
		LIB_FILE_NAME = 'libgeos_c.so'

		# create symlink that shapely package can locate when in frozen state
		LIB_SYM_PATH = os.path.join(LIB_DIR, 'libgeos_c-1.so.1')
		command = f'ln -sf {LIB_FILE_NAME} {LIB_SYM_PATH}'
		print(f"Created symlink {LIB_SYM_PATH} -> {LIB_FILE_NAME} and added to target.")

		os.system(command)
	else:
		# if the library can already be found make sure it still gets included
		# when bundling
		LIB_SYM_PATH = glob.glob(os.path.join(LIB_DIR, 'libgeos_c-*.so.*'))[0]

	# pass path of library to pyinstaller variable binaries [(source,target)]
	binaries += [(LIB_SYM_PATH, '.')]

block_cipher = None


a = Analysis(
    ['pzero.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=['pzero/project_window.py'],
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
    debug=True,
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
