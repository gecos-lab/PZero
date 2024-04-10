# PZero #

![Workflow Testing](https://img.shields.io/github/actions/workflow/status/andrea-bistacchi/PZero/testing.yml?event=push)
[![DOI](https://zenodo.org/badge/439080627.svg)](https://zenodo.org/badge/latestdoi/439080627)


***PZero*** is a Python open-source 3D geological modelling application, leveraging various libraries, with a user-friendly graphical user interface allowing to perform most standard geomodelling data management and analysis tasks, explicit surface interpolation, and advanced implicit interpolation.

To build ***PZero*** we use several open-source libraries. **[VTK](https://vtk.org/)** provides classes for all 3D objects, in addition to 3D visualization and basic analysis and modelling tools. The ***PZero*** graphical user interface is built with **[Qt](https://www.qt.io/qt-for-python)**. All objects in a ***PZero*** project and their metadata are collected and managed in **[pandas](https://pandas.pydata.org/)** dataframes. We use a **[VTK-Numpy interface](https://github.com/Kitware/VTK/tree/master/Wrapping/Python/vtkmodules/numpy_interface)** that allows performing most mathematical processing with simple **[NumPy](https://numpy.org/)** syntax, while 2D plotting is performed with **[Matplotlib](https://matplotlib.org/)**. **[PyVista](https://www.pyvista.org/)** and **[vedo](https://vedo.embl.es/)** provide simplified access to **[VTK](https://vtk.org/)** visualization and I/O tools. Various 2D graphical and topological editing tools in ***PZero*** are based on **[Shapely](https://shapely.readthedocs.io)**, while **[GeoPandas](https://geopandas.org/en/stable/)**, **[Rasterio](https://rasterio.readthedocs.io)**, **[Xarray](https://xarray.pydata.org)**, **[laspy](https://github.com/laspy/laspy)**, and **[EzDxf](https://ezdxf.readthedocs.io)** provide I/O tools for GIS, point cloud, and CAD data. **[LoopStructural](https://github.com/Loop3D/LoopStructural)** provides three different implicit surface interpolation algorithms. **[mplstereonet](https://github.com/joferkington/mplstereonet)** provides stereoplots for orientation analysis.

Developers of these libraries are warmly thanked!

The ***PZero*** project started in spring 2020 thanks to a research project funded by **[Pro Iter Tunnelling & Geotechnical Department](https://www.proiter.it/)** and lead by **Andrea Bistacchi** and **Luca Soldo**. ***PZero*** is now supported by the **[Geosciences IR](https://geosciences-ir.it/)** project lead by **[ISPRA - Servizio Geologico d'Italia](https://www.isprambiente.gov.it/it/servizi/il-servizio-geologico-ditalia)** and funded by **[PNRR](https://www.mur.gov.it/it/pnrr/missione-istruzione-e-ricerca)**.

The ***PZero*** developers are (or have been):
* Andrea Bistacchi (since the beginning)
* Gloria Arienti (since December 2020)
* Gabriele Benedetti (since January 2022)
* Ivano Brunet (since March 2024)
* Tommaso Comelli (April 2023 - July 2023)
* Luca Penasa (since April 2023)
* Francesco Visentin (since March 2024)
* Waqas Hussain (since November 2023)

***PZero*** © 2020 by Andrea Bistacchi, released under [GNU AGPLv3 license](LICENSE.txt).

&nbsp;
<p align="center">
   <img src="images/mosaic.jpg" width="100%" height="100%"/>
</p>
&nbsp;
&nbsp;

The name of ***PZero*** was inspired by the zeroth element in Emile Argand's 3D model of the Pennine Alps nappe stack - possibly the first quantitative 3D geological model in the history of geological sciences (*Argand E., 1911. Les Nappes de recouvrement des Alpes pennines et leurs prolongements structuraux. Mat. Carte géol. Suisse, 31, 1-26*), and by Python.

If you want to know more about the project or want to contribute, our [GitHub Wiki](https://github.com/andrea-bistacchi/PZero/wiki) can help!

## Installing PZero executables ##

***PZero*** runs on **Linux**, **macOS** and **Windows**. Executable files can be [downloaded from the releases section of this repository](https://github.com/andrea-bistacchi/PZero/releases).

Alternatively, you can download the most recent source code and test it, provided that a suitable **Python** and **[required libraries](envs/std-environment.yml)** are available.

### Installing PZero source code with Anaconda ###

At the moment the easiest way to run and develop new code for ***PZero*** is to clone this repository locally as [discussed here](https://github.com/andrea-bistacchi/PZero/wiki/How-to-use-GIT-(for-beginners)), and install a suitable **[Anaconda](https://www.anaconda.com/)** environment as [explained here](https://github.com/andrea-bistacchi/PZero/wiki/How-to-install-and-manage-CONDA-environments-(for-beginners)). Alternatively PyPi could be used in macOS and Linux as [discussed here](https://github.com/andrea-bistacchi/PZero/wiki/Installation-on-macOS-and-Linux-with-PyPI-using-pip).

Then you can start PZero from PyCharm, or from the terminal with:

```
python pzero.py
```


---
## Test data ##

We have uploaded some test project on public repositories:

[PZero-test Simple-synthetic](https://github.com/andrea-bistacchi/PZero-test-Simple-synthetic)

[PZero-test Llyn-Padarn](https://github.com/andrea-bistacchi/PZero-test-Llyn-Padarn)
\
\
\
<img src='https://github.com/gecos-lab/PZero/images/pzero_QR.png' width='200'>


