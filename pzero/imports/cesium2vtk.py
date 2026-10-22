"""cesium2vtk.py
PZero© Andrea Bistacchi"""

from vtk import vtkCesium3DTilesWriter, vtkMultiBlockDataSet

from pzero.entities_factory import TriSurf
from pzero.helpers.project_crs import project_crs_code


def vtk2cesium(self=None, out_dir_name=None):
    """Exports all triangulated surfaces to a collection of GLTF binary surfaces (extension .glb).
    Note that saving in binary format is automatically set by using the .glb extension.
    https://vtk.org/doc/nightly/html//classvtkCesium3DTilesWriter.html
    https://github.com/Kitware/VTK/blob/master/IO/Geometry/vtkGLTFWriter.cxx

    https://github.com/Kitware/Danesfield/blob/master/tools/tiler.py
    https://github.com/Kitware/Danesfield/blob/master/tools/tiler-test.sh

    IN THE FUTURE extend to other entity classes such as DEM, polyline, etc."""
    crs = project_crs_code(getattr(self, "project_crs", None))
    if crs is None:
        raise ValueError("Assign the project CRS before exporting Cesium tiles.")
    # File name
    out_file_name = str(out_dir_name) + "/" + "multi_block_dataset" + ".glb"
    # Create GLTF writer.
    multi_block = vtkMultiBlockDataSet()
    print("multi_block: ", multi_block)
    writer = vtkCesium3DTilesWriter()
    print("writer: ", writer)
    # Loop for each entity.
    i = 0
    for uid in self.geol_coll.df["uid"]:
        if isinstance(self.geol_coll.get_uid_vtk_obj(uid), TriSurf):
            print("i: ", i)
            vtk_entity = self.geol_coll.get_uid_vtk_obj(uid)
            multi_block.SetBlock(i, vtk_entity)
            print("multi_block: ", multi_block)
            i = i + 1

    writer.SetInputDataObject(multi_block)
    writer.SetDirectoryName(out_dir_name)
    writer.SetTextureBaseDirectory(out_dir_name)
    writer.SetInputType(2)
    writer.SetContentGLTF(True)
    writer.SetCRS(crs)
    print("writer: ", writer)
    writer.Write()

    print("All TSurfs saved.")
