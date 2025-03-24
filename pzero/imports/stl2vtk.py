"""stl2py
PZero© Andrea Bistacchi"""

from vtk import vtkSTLWriter

from pzero.entities_factory import TriSurf


def vtk2stl(self=None, out_dir_name=None):
    """Exports all triangulated surfaces to a collection of STL surfaces."""
    #Create STL writer.
    stl_writer = vtkSTLWriter()
    stl_writer.SetFileTypeToASCII()
    #Loop for each entity.
    for uid in self.geol_coll.df["uid"]:
        if isinstance(self.geol_coll.get_uid_vtk_obj(uid), TriSurf):
            header = (
                uid
                + "_"
                + self.geol_coll.df.loc[self.geol_coll.df["uid"] == uid, "name"].values[
                    0
                ]
            )
            out_file_name = (
                str(out_dir_name)
                + "/"
                + uid
                + "_"
                + self.geol_coll.df.loc[self.geol_coll.df["uid"] == uid, "name"].values[
                    0
                ]
                + ".stl"
            )
            stl_writer.SetFileName(out_file_name)
            vtk_entity = self.geol_coll.get_uid_vtk_obj(uid)
            stl_writer.SetInputData(vtk_entity)
            stl_writer.SetHeader(header)
            stl_writer.Write()
    for uid in self.boundary_coll.df["uid"]:
        if isinstance(self.boundary_coll.get_uid_vtk_obj(uid), TriSurf):
            header = (
                uid
                + "_"
                + self.boundary_coll.df.loc[
                    self.boundary_coll.df["uid"] == uid, "name"
                ].values[0]
            )
            out_file_name = (
                str(out_dir_name)
                + "/"
                + uid
                + "_"
                + self.boundary_coll.df.loc[
                    self.boundary_coll.df["uid"] == uid, "name"
                ].values[0]
                + ".stl"
            )
            stl_writer.SetFileName(out_file_name)
            vtk_entity = self.boundary_coll.get_uid_vtk_obj(uid)
            stl_writer.SetInputData(vtk_entity)
            stl_writer.SetHeader(header)
            stl_writer.Write()
    print("All TSurfs saved.")


def vtk2stl_dilation(self=None, out_dir_name=None, tol=1.0):
    """Apply dilation then exports all triangulated surfaces to a collection of STL surfaces."""
    #Create STL writer.
    stl_writer = vtkSTLWriter()
    stl_writer.SetFileTypeToASCII()
    #Loop for each entity.
    for uid in self.geol_coll.df["uid"]:
        if isinstance(self.geol_coll.get_uid_vtk_obj(uid), TriSurf):
            header = (
                uid
                + "_"
                + self.geol_coll.df.loc[self.geol_coll.df["uid"] == uid, "name"].values[
                    0
                ]
            )
            out_file_name = (
                str(out_dir_name)
                + "/"
                + uid
                + "_"
                + self.geol_coll.df.loc[self.geol_coll.df["uid"] == uid, "name"].values[
                    0
                ]
                + ".stl"
            )
            stl_writer.SetFileName(out_file_name)
            vtk_entity = self.geol_coll.get_uid_vtk_obj(uid)
            vtk_entity_dilated = vtk_entity.boundary_dilation(tol=tol)
            try:
                stl_writer.SetInputData(vtk_entity_dilated)
                stl_writer.SetHeader(header)
                stl_writer.Write()
            except:
                pass
    print("All TSurfs saved.")
