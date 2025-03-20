# PZero collections

Collections are set of Entities and metadata logically organized from
a geological modelling point of view.

They are Panda dataframes with a "line" (record?) for every object that
belongs to a Project (?) and columns representing various attributes
among which:

  - `uid`: object identifiers of type uuid
  - `vtk_obj`: reference to the Entity (see ARCHITECTURE.md)
  - various metadata related to the geological meaning of the object

Collections are all subclasses of an BaseCollection python class defined
in the AbstractCollection.py file, either direct child or child of some
intermediate class like DIMCollection (defined in `DIM_collection.py`)

