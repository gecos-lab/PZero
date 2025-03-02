"""obj2vtk.py
PZero© Andrea Bistacchi"""

from vtk import vtkOBJWriter
from pzero.entities_factory import TriSurf
from pzero.helpers.helper_dialogs import options_dialog


def vtk2obj(self=None, out_dir_name=None):
    """Exports all triangulated surfaces to a collection of OBJ surfaces.
    IN THE FUTURE extendo to other entity classes such as DEM, polyline, etc."""
    # At the moment only entities in the geological collection can be exported.
    if self.shown_table != "tabGeology":
        return
    append_name = options_dialog(
        title="Append name",
        message="Append entity name to output file name?",
        yes_role="Yes",
        no_role="No",
        reject_role=None,
    )
    if append_name == 0:
        append_name = True
    else:
        append_name = False
    # Create STL writer.
    obj_writer = vtkOBJWriter()
    # Loop for each entity.
    for uid in self.selected_uids:
        if isinstance(self.geol_coll.get_uid_vtk_obj(uid), TriSurf):
            if append_name:
                out_file_name = (
                    str(out_dir_name)
                    + "/"
                    + uid
                    + "_"
                    + self.geol_coll.df.loc[
                        self.geol_coll.df["uid"] == uid, "name"
                    ].values[0]
                    + ".obj"
                )
            else:
                out_file_name = str(out_dir_name) + "/" + uid + ".obj"
            vtk_entity = self.geol_coll.get_uid_vtk_obj(uid)
            obj_writer.SetFileName(out_file_name)
            obj_writer.SetInputData(vtk_entity)
            obj_writer.Write()
    # for uid in self.selected_uids:
    #     if isinstance(self.boundary_coll.get_uid_vtk_obj(uid), TriSurf):
    #         if append_name:
    #             out_file_name = (
    #                 str(out_dir_name)
    #                 + "/"
    #                 + uid
    #                 + "_"
    #                 + self.boundary_coll.df.loc[
    #                     self.boundary_coll.df["uid"] == uid, "name"
    #                 ].values[0]
    #                 + ".obj"
    #             )
    #         else:
    #             out_file_name = str(out_dir_name) + "/" + uid + ".obj"
    #         vtk_entity = self.boundary_coll.get_uid_vtk_obj(uid)
    #         obj_writer.SetFileName(out_file_name)
    #         obj_writer.SetInputData(vtk_entity)
    #         obj_writer.Write()
    # print("All TSurfs saved.")
