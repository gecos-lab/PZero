pzero.collections package
=========================
One of the most important groups of files comprises the "collections." Each collection encapsulates all entities of a specific type of geological or non-geological objects, such as images that indirectly assist in describing a geological model. These collections are always Pandas dataframes. Inside each "type_of_collection.py" file, we have a series of similar methods that serve to manage the entities, including:

add_entity(): Takes an entity as input and inserts it into the entity list of that collection.
remove_entity(): Removes a specific entity from a collection using its UID.
clone_entity(): Duplicates and adds the same input entity to a collection.
replace_vtk(): Given a UID, replaces the vtk instance of that entity with another input instance.
Many getter and setter methods for retrieving and setting UIDs, properties, metadata, etc.
Another group of files is used within "project_windows.py," comprising around fifteen small files that contain all the useful functions for converting, importing, and exporting various formats to be used in the View.

Submodules
----------

pzero.collections.background\_collection module
-----------------------------------------------

.. automodule:: pzero.collections.background_collection
   :members:
   :undoc-members:
   :show-inheritance:

pzero.collections.boundary\_collection module
---------------------------------------------

.. automodule:: pzero.collections.boundary_collection
   :members:
   :undoc-members:
   :show-inheritance:

pzero.collections.dom\_collection module
----------------------------------------

.. automodule:: pzero.collections.dom_collection
   :members:
   :undoc-members:
   :show-inheritance:

pzero.collections.fluid\_collection module
------------------------------------------

.. automodule:: pzero.collections.fluid_collection
   :members:
   :undoc-members:
   :show-inheritance:

pzero.collections.geological\_collection module
-----------------------------------------------

.. automodule:: pzero.collections.geological_collection
   :members:
   :undoc-members:
   :show-inheritance:

pzero.collections.image\_collection module
------------------------------------------

.. automodule:: pzero.collections.image_collection
   :members:
   :undoc-members:
   :show-inheritance:

pzero.collections.mesh3d\_collection module
-------------------------------------------

.. automodule:: pzero.collections.mesh3d_collection
   :members:
   :undoc-members:
   :show-inheritance:

pzero.collections.well\_collection module
-----------------------------------------

.. automodule:: pzero.collections.well_collection
   :members:
   :undoc-members:
   :show-inheritance:

pzero.collections.xsection\_collection module
---------------------------------------------

.. automodule:: pzero.collections.xsection_collection
   :members:
   :undoc-members:
   :show-inheritance:

Module contents
---------------

.. automodule:: pzero.collections
   :members:
   :undoc-members:
   :show-inheritance:
