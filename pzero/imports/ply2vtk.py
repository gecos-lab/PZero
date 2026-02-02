"""ply2vtk.py
PZero© Andrea Bistacchi"""

from vtk import vtkPLYWriter

from pzero.entities_factory import TriSurf


def vtk2ply(self=None, out_dir_name=None):
    """Exports all triangulated surfaces to a collection of PLY surfaces.
    IN THE FUTURE extend to other entity classes such as DEM, polyline, etc."""
    # Create PLY writer.
    ply_writer = vtkPLYWriter()
    ply_writer.SetFileTypeToBinary()
    ply_writer.SetColorModeToUniformCellColor()
    # Loop for each entity.
    for uid in self.geol_coll.df["uid"]:
        if isinstance(self.geol_coll.get_uid_vtk_obj(uid), TriSurf):
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
            vtk_entity = self.geol_coll.get_uid_vtk_obj(uid)
            color_R = self.geol_coll.get_uid_legend(uid=uid)["color_R"]
            color_G = self.geol_coll.get_uid_legend(uid=uid)["color_G"]
            color_B = self.geol_coll.get_uid_legend(uid=uid)["color_B"]
            print("RGB: ", color_R, color_G, color_B)
            ply_writer.SetFileName(out_file_name)
            ply_writer.SetInputData(vtk_entity)
            ply_writer.SetColor(color_R, color_G, color_B)
            ply_writer.Write()
    for uid in self.boundary_coll.df["uid"]:
        if isinstance(self.boundary_coll.get_uid_vtk_obj(uid), TriSurf):
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
            vtk_entity = self.boundary_coll.get_uid_vtk_obj(uid)
            color_R = self.boundary_coll.get_uid_legend(uid=uid)["color_R"]
            color_G = self.boundary_coll.get_uid_legend(uid=uid)["color_G"]
            color_B = self.boundary_coll.get_uid_legend(uid=uid)["color_B"]
            print("RGB: ", color_R, color_G, color_B)
            ply_writer.SetFileName(out_file_name)
            ply_writer.SetInputData(vtk_entity)
            ply_writer.SetColor(color_R, color_G, color_B)
            ply_writer.Write()
    print("All TSurfs saved.")
