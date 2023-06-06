"""gltf2vtk.py
PZero© Andrea Bistacchi"""

from vtk import vtkGLTFWriter, vtkMultiBlockDataSet
from pzero.entities_factory import TriSurf


def vtk2gltf(self=None, out_dir_name=None):
    """Exports all triangulated surfaces to a collection of GLTF binary surfaces (extension .glb).
    Note that saving in binary format is automatically set by using the .glb extension.
    IN THE FUTURE extendo to other entity classes such as DEM, polyline, etc."""
    """File name"""
    out_file_name = (str(out_dir_name) + "/" + "multi_block_dataset" + ".glb")
    """Create GLTF writer."""
    multi_block = vtkMultiBlockDataSet()
    print("multi_block: ", multi_block)
    gltf_writer = vtkGLTFWriter()
    print("gltf_writer: ", gltf_writer)
    """Loop for each entity."""
    i = 0
    for uid in self.geol_coll.df['uid']:
        if isinstance(self.geol_coll.get_uid_vtk_obj(uid), TriSurf):
            print("i: ", i)
            vtk_entity = self.geol_coll.get_uid_vtk_obj(uid)
            multi_block.SetBlock(i, vtk_entity)
            print("multi_block: ", multi_block)
            i = i+1
    # for uid in self.boundary_coll.df['uid']:
    #     if isinstance(self.boundary_coll.get_uid_vtk_obj(uid), TriSurf):
    #         vtk_entity = self.boundary_coll.get_uid_vtk_obj(uid)
    #         multi_block.SetBlock(i, vtk_entity)
    #         i = i + 1
    gltf_writer.SetFileName(out_file_name)
    print("gltf_writer: ", gltf_writer)
    gltf_writer.SetInputDataObject(multi_block)
    print("gltf_writer: ", gltf_writer)
    gltf_writer.Write()
    print("gltf_writer: ", gltf_writer)

    print("All TSurfs saved.")

