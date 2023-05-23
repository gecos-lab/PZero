# PZero #

![Workflow Testing](https://img.shields.io/github/actions/workflow/status/andrea-bistacchi/PZero/testing.yml?event=push)
[![DOI](https://zenodo.org/badge/439080627.svg)](https://zenodo.org/badge/latestdoi/439080627)


***PZero*** is a Python open-source 3D geological modelling application, leveraging various libraries, with a user-friendly graphical user interface allowing to perform most standard geomodelling data management and analysis tasks, explicit surface interpolation, and advanced implicit interpolation.

To build ***PZero*** we use several open-source libraries. **[VTK](https://vtk.org/)** provides classes for all 3D objects, in addition to 3D visualization and basic analysis and modelling tools. The ***PZero*** graphical user interface is built with **[Qt](https://www.qt.io/qt-for-python)**. All objects in a ***PZero*** project and their metadata are collected and managed in **[pandas](https://pandas.pydata.org/)** dataframes. We use a **[VTK-Numpy interface](https://github.com/Kitware/VTK/tree/master/Wrapping/Python/vtkmodules/numpy_interface)** that allows performing most mathematical processing with simple **[NumPy](https://numpy.org/)** syntax, while 2D plotting is performed with **[Matplotlib](https://matplotlib.org/)**. **[PyVista](https://www.pyvista.org/)** and **[vedo](https://vedo.embl.es/)** provide simplified access to **[VTK](https://vtk.org/)** visualization and I/O tools. Various 2D graphical and topological editing tools in ***PZero*** are based on **[Shapely](https://shapely.readthedocs.io)**, while **[GeoPandas](https://geopandas.org/en/stable/)**, **[Rasterio](https://rasterio.readthedocs.io)**, **[Xarray](https://xarray.pydata.org)**, **[laspy](https://github.com/laspy/laspy)**, and **[EzDxf](https://ezdxf.readthedocs.io)** provide I/O tools for GIS, point cloud, and CAD data. **[LoopStructural](https://github.com/Loop3D/LoopStructural)** provides three different implicit surface interpolation algorithms. **[mplstereonet](https://github.com/joferkington/mplstereonet)** provides stereoplots for orientation analysis.

Developers of these libraries are warmly thanked!

The ***PZero*** project started in spring 2020 thanks to a research project funded by **[Pro Iter Tunnelling & Geotechnical Department](https://www.proiter.it/)** and lead by **Andrea Bistacchi** and **Luca Soldo**.

The ***PZero*** developers are:
* Andrea Bistacchi (since the beginning)
* Gloria Arienti (since December 2020)
* Gabriele Benedetti (since January 2022)
* Tommaso Comelli (since April 2023)
* Luca Penasa (since April 2023)

***PZero*** © 2020 by Andrea Bistacchi, released under [GNU AGPLv3 license](LICENSE.txt).

&nbsp;
<p align="center">
   <img src="images/mosaic.jpg" width="100%" height="100%"/>
</p>
&nbsp;
&nbsp;

The name of ***PZero*** was inspired by the zeroth element in Emile Argand's 3D model of the Pennine Alps nappe stack - possibly the first quantitative 3D geological model in the history of geological sciences (*Argand E., 1911. Les Nappes de recouvrement des Alpes pennines et leurs prolongements structuraux. Mat. Carte géol. Suisse, 31, 1-26*), and by Python.

If you want to know more about the project or want to contribute, our [GitHub Wiki](https://github.com/andrea-bistacchi/PZero/wiki) can help!

## Installing and running PZero ##

***PZero*** runs on **Linux**, **macOS** and **Windows**, provided that a suitable **Python 3.8** and **[required libraries](envs/std-environment.yml)** are available.

### Quick and easy installation with Anaconda ###

At the moment the easiest way to run and develop new code for ***PZero*** is to have a suitable **[Anaconda](https://www.anaconda.com/)** environment.

In the ```conda terminal```, navigate to the ***PZero*** folder that you have cloned with **Git** or simply downloaded, go in the **envs** folder and based on you OS import the right environment as follows.

For **Windows/Linux** run this command:
```
conda env create -n pzero -f std-environment.yml
conda activate pzero
```

Alternatively if you are a **MacOS** user, run this command:
```
conda env create -n pzero -f macos-environment.yml
conda activate pzero
```

Then you can start PZero with:

```
python pzero.py
```

To activate and deactivate the pzero environment, and in case you want to remove it completely, use respectively (in ```conda terminal```):

```
conda activate pzero

conda deactivate

conda remove -n pzero --all
```

### Almost quick and easy installation on **macOS** with PyPI using pip

It is also possible to install ***PZero*** on **macOS** without **[Anaconda](https://www.anaconda.com/)**. For this **[Homebrew](https://brew.sh)** is needed and, in order not to alter the base **Python** environment, we strongly suggest to create a dedicated virtual environment using **[virtualenvwrapper](https://virtualenvwrapper.readthedocs.io/)**.

All the following commands must be entered in the **macOS Terminal**. First **Homebrew**, **Python 3** (needed because the default Python on macOS is Python 2) and **virtualenvwrapper** are installed:

```
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install python3
brew install virtualenvwrapper
```

Then to be able to use **virtualenvwrapper**, some lines must be added to the options file of the **zsh shell** (the shell that runs in the **macOS Terminal**). The options file can be opened with:

```
nano ~/.zshrc
```

Then the following lines must be pasted and the file saved with *control+X*.

```
# lines needed by virtualenvwrapper
export WORKON_HOME=$HOME/.virtualenvs
export PROJECT_HOME=$HOME/Devel
source /usr/local/bin/virtualenvwrapper.sh
```

After restarting the Terminal, a virtual environment called ```pzero``` based on **Python 3.8** can be created and activated:

```
mkvirtualenv --python=3.8 pzero
workon pzero
```

When the ```pzero``` environment is active, it will be highlighted within brackets at the command prompt, as in:

```
(pzero) <user>@<machine> <directory> %
```

To activate and deactivate the ```pzero``` environment, and in case you want to remove it completely, use respectively:

```
workon pzero

deactivate

rmvirtualenv pzero
```

All the lines above, from ```brew install virtualenvwrapper```, can be skipped in case a virtual environment is not being created, or created using a different virtual environment manager.

Now the **Python** modules required by ***PZero*** can be automatically installed using ```pip3``` (not ```pip``` that will point to Python 2) within the ***PZero*** directory downloaded from **GitHub**.

```
pip3 install -r .envs/requirements.txt
```

And finally ***PZero*** can be run with:

```
python3 pzero.py
```

### Quick and easy installation on Linux (debian) using pip

### Pip installaton

For Debian based Linux distros pip can be installed using the apt package manager.

1. **Check if packages and dependencies need to be upgraded (routine check):**

```bash
sudo apt update
sudo apt upgrade
```

2. **Install pip3:**

```bash
sudo apt install python3-pip
```


### Install requirements with pip

To install the required python3 modules we can just run:

```bash
pip3 install -r ./envs/requirements.txt
```

After the required packages are installed **PZero** can be run with:

```bash
python3 pzero.py
```

### Conda installation (optional):

Conda can also be installed on Linux by following **[this quick guide](https://docs.conda.io/projects/conda/en/latest/user-guide/install/linux.html)**. After installing conda a *pzero* environment can be created and activated in the same way as in the other OSs. To install the required packages in a given environment follow the steps above after activating the environment.


---
## Test data ##

We have uploaded some test project on public repositories:

[PZero-test Simple-synthetic](https://github.com/andrea-bistacchi/PZero-test-Simple-synthetic)

[PZero-test Llyn-Padarn](https://github.com/andrea-bistacchi/PZero-test-Llyn-Padarn)


---
## IDE ##

To develop ***PZero*** we use the **[PyCharm IDE](https://www.jetbrains.com/pycharm/)**, but also **[Visual Studio Code](https://code.visualstudio.com/)** has been tested successfully.


