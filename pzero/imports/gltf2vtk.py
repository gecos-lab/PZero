"""gltf2vtk.py
PZero© Andrea Bistacchi"""

from vtk import vtkGLTFWriter, vtkMultiBlockDataSet

from pzero.entities_factory import TriSurf


def vtk2gltf(self=None, out_dir_name=None):
    """Exports all triangulated surfaces to a collection of GLTF binary surfaces (extension .glb).
    Note that saving in binary format is automatically set by using the .glb extension.
    IN THE FUTURE extendo to other entity classes such as DEM, polyline, etc."""
    # File name
    out_file_name = str(out_dir_name) + "/" + "multi_block_dataset" + ".glb"
    # Create GLTF writer.
    multi_block = vtkMultiBlockDataSet()
    writer = vtkGLTFWriter()
    # Loop for each entity.
    i = 0
    for uid in self.geol_coll.df["uid"]:
        if isinstance(self.geol_coll.get_uid_vtk_obj(uid), TriSurf):
            vtk_entity = self.geol_coll.get_uid_vtk_obj(uid)
            multi_block.SetBlock(i, vtk_entity)
            i = i + 1
    # for uid in self.boundary_coll.df['uid']:
    #     if isinstance(self.boundary_coll.get_uid_vtk_obj(uid), TriSurf):
    #         vtk_entity = self.boundary_coll.get_uid_vtk_obj(uid)
    #         multi_block.SetBlock(i, vtk_entity)
    #         i = i + 1
    writer.InlineDataOff()
    # writer.SetTextureBaseDirectory(str(out_dir_name))
    # SetPropertyTextureFile(const char *)
    writer.SaveNormalOn()
    writer.SaveTexturesOn()
    # writer.CopyTexturesOn()  # AttributeError: 'vtkmodules.vtkIOGeometry.vtkGLTFWriter' object has no attribute 'CopyTexturesOn'
    # writer.SaveActivePointColorOn()  # saves RGB is an active 3 or 4 component scalar field is found
    # writer.RelativeCoordinatesOn()  # Save mesh point coordinates relative to the bounding box origin and add the corresponding translation to the root node - AttributeError: 'vtkmodules.vtkIOGeometry.vtkGLTFWriter' object has no attribute 'RelativeCoordinatesOn'
    # writer.SetRelativeCoordinates(True)  # AttributeError: 'vtkmodules.vtkIOGeometry.vtkGLTFWriter' object has no attribute 'SetRelativeCoordinates'
    writer.SetInputDataObject(multi_block)
    # writer.SetDirectoryName(out_dir_name)
    writer.SetFileName(out_file_name)
    print("test - writer: ", writer)
    writer.Write()

    print("All TSurfs saved.")
