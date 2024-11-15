"""CRS.py
PZero© Andrea Bistacchi"""

from numpy import column_stack as np_column_stack
from pyproj import Transformer

from pzero.entities_factory import (VertexSet,
                                    PolyLine,
                                    TriSurf,
                                    Frame,
                                    XsVertexSet,
                                    XsPolyLine,
                                    XsTriSurf,
                                    TetraSolid,
                                    Voxet,
                                    XsVoxet,
                                    Seismics,
                                    DEM,
                                    PCDom,
                                    TSDom,
                                    MapImage,
                                    XsImage,
                                    Image3D,
                                    Well,
                                    Attitude
                                    )
from pzero.helpers.helper_dialogs import general_input_dialog
from pzero.helpers.helper_functions import freeze_gui

EPSG_dict = {
    "EPSG:6707": "RDN2008 / UTM zone 32N (N-E) / Nord, Est",
    "EPSG:6708": "RDN2008 / UTM zone 33N (N-E) / Nord, Est",
    "EPSG:6709": "RDN2008 / UTM zone 34N (N-E) / Nord, Est",
    "EPSG:6875": "RDN2008 / Italy zone (N-E) / Nord, Est",
    "EPSG:6876": "RDN2008 / Zone 12 (N-E) / Est, Nord",
    "EPSG:7791": "RDN2008 / UTM zone 32N / Est, Nord",
    "EPSG:7792": "RDN2008 / UTM zone 33N / Est, Nord",
    "EPSG:7793": "RDN2008 / UTM zone 34N / Est, Nord",
    "EPSG:7794": "RDN2008 / Italy zone / Est, Nord",
    "EPSG:7795": "RDN2008 / Zone 12 / Est, Nord",
    "EPSG:32632": "WGS84 / UTM zone 32N / Est, Nord",
    "EPSG:32633": "WGS84 / UTM zone 33N / Est, Nord",
    "EPSG:32634": "WGS84 / UTM zone 34N / Est, Nord",
    "EPSG:23032": "ED50 / UTM zone 32N / Est, Nord",
    "EPSG:23033": "ED50 / UTM zone 33N / Est, Nord",
    "EPSG:23034": "ED50 / UTM zone 34N / Est, Nord",
    "EPSG:3003": "Monte Mario / Italy zone 1 / Est, Nord",
    "EPSG:3004": "Monte Mario / Italy zone 2 / Est, Nord",
    "EPSG:2056": "CH1903+/LV95 / Swiss Grid / Est, Nord",
}


def CRS_list(self):
    """Function used to print the description of all valid CRSs."""
    for key, value in EPSG_dict.items():
        self.print_terminal(f"{key}: {value}")


def CRS_transform_uid_accurate(self, uid=None, collection=None, from_CRS=None, to_CRS=None):
    """Function used to transform CRS of a single entity."""
    self.print_terminal(f"Transforming entity {uid} from {from_CRS} to {to_CRS}")
    in_entity = collection.get_uid_vtk_obj(uid)
    self.print_terminal(f"from in_entity.bounds = {in_entity.bounds}")
    # create transformer with always_xy option ensuring that coordinate order is always easting, northing.
    transformer = Transformer.from_crs(from_CRS, to_CRS, always_xy=True)
    points_X, points_Y = transformer.transform(in_entity.points_X, in_entity.points_Y)
    in_entity.points = np_column_stack((points_X, points_Y, in_entity.points_Z))
    in_entity.Modified()
    collection.signals.geom_modified.emit([uid])
    self.print_terminal(f"to in_entity.bounds = {in_entity.bounds}")

@freeze_gui
def CRS_transform_selected(self):
    """Function used to transform CRS of selected entities.
    Only the transformation of entities exposing the .points property is accurate.
    Objects with a regular grid, such as images, are transformed with a simple rototranslation best-fit on corners."""
    if not self.selected_uids:
        self.print_terminal("No input data selected.")
        return
    self.print_terminal("Transform CRS of selected entities.\nOnly the transformation of entities exposing the .points property is accurate.\nObjects with a regular grid, such as images, are transformed with a simple rototranslation best-fit on corners.")
    # select CRSs
    CRS_select = general_input_dialog(
        title="Select CRSs",
        input_dict={
            "from_CRS": ["From CRS", EPSG_dict.keys(), "QComboBox"],
            "to_CRS": ["To CRS", EPSG_dict.keys(), "QComboBox"],
        },
    )
    if CRS_select is None:
        return
    from_CRS = CRS_select["from_CRS"]
    to_CRS = CRS_select["to_CRS"]
    # run different methods based on collection and entity
    collection = eval(f"self.{self.selected_collection}")
    for uid in self.selected_uids:
        if self.selected_collection == "xsect_coll":
            # affine transformation of the frame
            pass
        elif isinstance(self.geol_coll.get_uid_vtk_obj(uid), (Voxet, XsVoxet, MapImage, XsImage, Image3D)):
            # affine transformation of the regular grid
            pass
        else:
            CRS_transform_uid_accurate(self=self, uid=uid, collection=collection, from_CRS=from_CRS, to_CRS=to_CRS)
