"""obj2vtk.py
PZero© Andrea Bistacchi"""

from vtk import vtkOBJWriter
from .entities_factory import TriSurf


def vtk2obj(self=None, out_dir_name=None):
    """Exports all triangulated surfaces to a collection of OBJ surfaces.
    IN THE FUTURE extendo to other entity classes such as DEM, polyline, etc."""
    """Create STL writer."""
    obj_writer = vtkOBJWriter()
    """Loop for each entity."""
    for uid in self.geol_coll._df['uid']:
        if isinstance(self.geol_coll.get_uid_vtk_obj(uid), TriSurf):
            out_file_name = (str(out_dir_name) + "/" + uid + "_" + self.geol_coll._df.loc[self.geol_coll._df['uid'] == uid, 'name'].values[0] + ".obj")
            vtk_entity = self.geol_coll.get_uid_vtk_obj(uid)
            obj_writer.SetFileName(out_file_name)
            obj_writer.SetInputData(vtk_entity)
            obj_writer.Write()
    for uid in self.boundary_coll._df['uid']:
        if isinstance(self.boundary_coll.get_uid_vtk_obj(uid), TriSurf):
            out_file_name = (str(out_dir_name) + "/" + uid + "_" + self.boundary_coll._df.loc[self.boundary_coll._df['uid'] == uid, 'name'].values[0] + ".obj")
            vtk_entity = self.boundary_coll.get_uid_vtk_obj(uid)
            obj_writer.SetFileName(out_file_name)
            obj_writer.SetInputData(vtk_entity)
            obj_writer.Write()
    print("All TSurfs saved.")
