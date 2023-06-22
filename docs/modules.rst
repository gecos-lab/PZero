PZero Architecture Introduction
=====

.. toctree::
   :maxdepth: 4

   PZero

Within this section, we will examine the architecture of the project. The first file we consider is "pzero.py," which is responsible for launching the program and initializing "project_window.py," representing the main window of PZero. Most of the fundamental operations of the project, such as project management, data modification within tabs, and file import and export, take place in the "project_window." The "project_window" also acts as an orchestrator as it generates and manages secondary windows. Visually, at the top of the window, we have a MenuBar that contains various dropdown menus for different operations, including file management, entity editing within tabs, interpolations, creating secondary windows, and a help section.
Inside the "init" method, which initializes the window, we have a call to setUpUi(). This operation is very common in all files that have a graphical interface. In fact, most visual settings of the windows are managed through this method, which calls a setup file containing all the parameters to be set (and each setup file will have a reference to the corresponding graphical file in its name, in this case, the file is called "project_window_ui.py").

One commonly used method is "create_empty()," which is called on PZero startup or when opening a new project. Its purpose is to initialize all the components of our main window, creating empty containers for different collections of geological data (e.g., Geological Collection, XSectionCollection, etc.). Each collection is represented by a Qt QAbstractTableModel linked to a Pandas dataframe as an attribute. The collections are filtered and sorted using a QSortFilterProxyModel(). On the other hand, legends and other less complex elements are implemented solely through dataframes.
Another category of methods, still within "project_window.py," is responsible for importing and exporting files in specific formats. For example, we have "import_gocad()" and "export_gocad()" that work with the GOCAD format and the data within the program.

Finally, we also have methods for managing data and entities within the tabs. We can modify, delete, or create them.

When in the main window a secondary window is requested, it is initialized from the "windows_factory.py" file. This is the longest file in the project, with approximately ~8500 lines, and it contains multiple classes, each related to an element or a window of the user interface (UI) that can be opened independently from the main window.

An example of a class is View3D(), which is generated from a button present in the "Windows" menu of the main window and is overlaid on top of the rest of the interface. However, this is an aspect that could be modified in the future, as currently each secondary window is always positioned above the main window, preventing its visibility in certain situations.

Both the main window and the secondary windows have been implemented as QMainWindow, which is a default window type in Qt that organizes space with a _MenuBar at the top, a _centralWidget in the center, and dockable areas around the _centralWidget that allow attaching and detaching windows called QDockWidget. However, this aspect could also be modified in the future, as the goal is to have a single QMainWindow representing the main window and the secondary windows as dockable QDockWidget attached to the main window.

Within "windows_factory.py", there is an abstract class called BaseView, common to all secondary windows. Its main purpose is to define shared standard methods for all classes that extend it. During the initialization of a secondary window, the setUpUi() function is always called, which sets up a common layout for all secondary windows, including a _MenuBar or a _ToolBar with commands inside it.


Within "windows_factory.py," we will have an abstract class common to all secondary windows called BaseView. Its main task is to define common standard methods for all windows that extend it. Furthermore, during its initialization, we will always have a setUpUi() that sets a common layout for all secondary windows that will be generated. This layout consists of a menu bar or toolbar with commands at the top, a chart with a type of geological model on the right, and a series of trees on the left that display the components of the geological model, which can be modified here. Other elements such as buttons, item lists, etc., will also be initialized.

Each of these entities we just mentioned will have its own "create_entity" method within the initialization and a continuously used method called "update_entity."

The most important generated windows are:

-3DView and 3DViewNew , representing a 3D geological model of the terrain. It can be rotated, zoomed in and out, and performs other standard operations.

-MapView, which generates a top-down 3D map of a geological model.

-PlaneXSectionView, which generates a vertical cross-section of a specific plane selected by the user.

-WellLogView, which shows a view of geological wells.

-StereoplotView, displaying a window that locates geological wells within a stereographic projection.

-HistogramView, generating a histogram containing

-XYPlotView, which displays a point plot on two X and Y axes.


Another crucial file within PZero is "entities_factory.py," which represents and creates a series of complex objects derived from the VTK library, used for managing and processing 3D objects. One of the most commonly used classes is the abstract class "PolyData," which inherits from "vtkPolyData" in the VTK library and provides useful tools and algorithms.

PolyData is used as the base entity for all entities that have geological significance, such as triangular surfaces, polylines, cross sections, point sets, as well as other cases like boundaries and DOMS. "PolyData" is inherited by other specific classes like VertexSet, PolyLine, and TriSurf, while the class "vtkUnstructuredGrid" is inherited by TetraSolid. In order from VertexSet to TetraSolid, these classes represent manifolds in 0D, 1D, 2D, and 3D, which are topological spaces resembling Euclidean spaces. These manifolds will be used or modified to generate 3D structures. All subclasses that extend PolyData are always within "entities_factory.py," although in the future, this structure may be modified by distributing these classes across multiple modules.

Another feature of our PolyData class is that it combines methods from the inherited VTK class with methods from vtk.numpyInterface.datasetAdapter, allowing the use of VTK objects with NumPy mathematical calculations. Instead of directly modifying VTK arrays, we modify NumPy arrays within our software. NumPy arrays serve as references through which 3D or 2D objects can be mathematically processed. Conversely, modifying a VTK object from the View will affect the NumPy arrays. One advantage of using NumPy is the availability of many mathematical algorithms, which also make the code more concise.

We do not use vtkFieldData since metadata for each entity is stored in Pandas dataframes for each geological type collection, such as sections, DOMs, wells, faults, etc. This choice is crucial because the Pandas library allows us to have memory-saving dataframe fields that are highly flexible (we can store any type of object within them: strings, integers, decimals, and many others). Non-geological objects like cross-sections, DEMs, and images are not defined within geological classes, even if they share the same topological class, because they have different modeling meanings. Other classes within this module also inherit from vtkPolyData or other VTK classes (e.g., vtkImageData).



Another file present in many windows is "legend_manager.py," which, as the name suggests, controls the different types of legends for all entities in PZero. For each entity, we have a dictionary with a string defining a property as the dictionary key, and a parameter or a list of parameters as the value. An example could be a list of integer parameters representing the "RGB" color palette. The class called "Legend" is imported from the "project_window.py" file and inherits from the GUI element "QObject." This means that we can use properties like signals and slots within this class, which can be useful for triggering events. When we modify an element of the legend, the connected signal will activate and launch a function that will accordingly modify another element displayed in the GUI, such as the color of a polyline. A "QObject" can also provide meta-information about its instance.

One of the initial methods within "legend_manager.py" is "update_widget()," which updates all the values within the legend that are often managed with Pandas dataframes.

Another group of modules includes "three_d_surfaces.py," "two_d_lines.py," and "orientation_analysis.py." This group aims to provide useful algorithms for modeling, such as interpolations, smoothings, intersections, and so on. The most commonly used libraries in this case are NumPy, which we mentioned earlier, and LoopStructural, which offers various advanced interpolation techniques for 3D objects. These modules are typically called by our main window and by all windows that utilize these interpolation algorithms. Additionally, these modules will be expanded further in the future, increasing the number of algorithms and features available for modeling geological surfaces.

One of the most important groups of files comprises the "collections." Each collection encapsulates all entities of a specific type of geological or non-geological objects, such as images that indirectly assist in describing a geological model. These collections are always Pandas dataframes. Inside each "type_of_collection.py" file, we have a series of similar methods that serve to manage the entities, including:

add_entity(): Takes an entity as input and inserts it into the entity list of that collection.
remove_entity(): Removes a specific entity from a collection using its UID.
clone_entity(): Duplicates and adds the same input entity to a collection.
replace_vtk(): Given a UID, replaces the vtk instance of that entity with another input instance.
Many getter and setter methods for retrieving and setting UIDs, properties, metadata, etc.
Another group of files is used within "project_windows.py," comprising around fifteen small files that contain all the useful functions for converting, importing, and exporting various formats to be used in the View.

Finally, the last group of modules that we will mention is represented by "helper_dialog.py," which contains a series of functions useful for the graphical interface to set up dialog messages.

