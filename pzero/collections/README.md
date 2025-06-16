# Collections

This folder contains classes for managing different types of collections and their metadata in PZero.

## Class Hierarchy

- `BaseCollection`
  _Abstract base class for all collection types. Defines the common interface and required methods using ABC._  
  _(Defined in `AbstractCollection.py`.)_

  - `WellCollection`  
    _Manages a collection of wells and their metadata._  
    _(Defined in `well_collection.py`.)_

  - `DIMCollection`  
    _Intermediate base class for collections of DOM, Image and Mesh3d entities._  
    _(Defined in `DIM_collection.py`.)_

    - `DomCollection`  
      _Manages a collection of DOM entities and their metadata._  
      _(Defined in `dom_collection.py`.)_

    - `ImageCollection`  
      _Manages a collection of image entities and their metadata._  
      _(Defined in `image_collection.py`.)_

    - `Mesh3DCollection`  
      _Manages a collection of 3D mesh entities and their metadata._  
      _(Defined in `mesh3d_collection.py`.)_

  - `GFBCollection`  
    _Intermediate abstract class used as a base for geological, fluid, and background collections._  
    _(Defined in `GFB_collection.py`.)_

    - `GeologicalCollection`  
      _Manages a collection of geological entities and their metadata._  
      _(Defined in `geological_collection.py`.)_

    - `FluidCollection`  
      _Manages a collection of fluid entities and their metadata._  
      _(Defined in `fluid_collection.py`.)_

    - `BackgroundCollection`
      _Manages a collection of background entities and their metadata._  
      _(Defined in `background_collection.py`.)_
