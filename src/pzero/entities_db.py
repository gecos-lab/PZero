from PyQt5.QtCore import QObject, pyqtSignal, QSortFilterProxyModel

from pzero.collections.background_collection import BackgroundCollection
from pzero.collections.boundary_collection import BoundaryCollection
from pzero.collections.dom_collection import DomCollection
from pzero.collections.fluid_collection import FluidsCollection
from pzero.collections.geological_collection import GeologicalCollection
from pzero.collections.image_collection import ImageCollection
from pzero.collections.mesh3d_collection import Mesh3DCollection
from pzero.collections.well_collection import WellCollection
from pzero.collections.xsection_collection import XSectionCollection

import logging as log

collections_instantiate = dict(
    geol=GeologicalCollection,
    xsect=XSectionCollection,
    dom=DomCollection,
    image=ImageCollection,
    mesh3d=Mesh3DCollection,
    boundary=BoundaryCollection,
    well=WellCollection,
    fluids=FluidsCollection,
    backgrounds=BackgroundCollection)


class EntitiesDB(QObject):
    """
    Entities are grouped into collections
    """
    clearing_entities_db_signal = pyqtSignal(name="ClearingEntitiesDB")

    def __init__(self, parent=None):
        log.debug("Instantiating EntitiesDB")
        super().__init__(parent=parent)

        self.collections = {}
        self.collections_to_proxy = {}

    def clear(self):
        self.clearing_entities_db_signal.emit()

        self.collections.clear()
        self.collections_to_proxy.clear()

        for name, cls in collections_instantiate.items():
            self.instantiate_collection(name, cls)

    def collection_by_name(self, name):
        return self.collections[name]

    def proxy_by_name(self, name):
        return self.collections_to_proxy[name]

    def has_collection(self, name):
        return name in list(self.collections.keys())
    def instantiate_collection(self, name, cls_to_instantiate):
        self.collections[name] = cls_to_instantiate(parent=self)
        self.collections_to_proxy[name] = QSortFilterProxyModel(self)
        self.collections_to_proxy[name].setSourceModel(self.collections[name])


    def collections_with_properties(self):
        return [c for c in self.collections.values() if "properties_names" in c.df.columns]


