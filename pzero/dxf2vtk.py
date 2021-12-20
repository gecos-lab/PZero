"""gocad2vtk.py
PZero© Andrea Bistacchi"""

from .entities_factory import TriSurf
import ezdxf
from vtk.util import numpy_support


def vtk2dxf(self=None, out_dir_name=None):
    """Exports all triangulated surfaces to a collection of DXF 3DFACE objects and border polyline3d."""
    """Create DXF container."""
    dxf_out = ezdxf.new()
    dxf_model = dxf_out.modelspace()
    """Add entities."""
    for uid in self.geol_coll.df['uid']:
        if isinstance(self.geol_coll.get_uid_vtk_obj(uid), TriSurf):
            layer = uid + "_" + self.geol_coll.df.loc[self.geol_coll.df['uid'] == uid, 'name'].values[0]
            vtk_entity = self.geol_coll.get_uid_vtk_obj(uid)
            """3D faces"""
            for i in range(vtk_entity.GetNumberOfCells()):
                face_points = numpy_support.vtk_to_numpy(vtk_entity.GetCell(i).GetPoints().GetData())
                dxf_model.add_3dface(face_points, dxfattribs={'layer': layer})
            """border -> https://lorensen.github.io/VTKExamples/site/Python/Meshes/BoundaryEdges/"""
            vtk_border = vtk_entity.get_clean_boundary()
            for cell in range(vtk_border.GetNumberOfCells()):
                border_points = numpy_support.vtk_to_numpy(vtk_border.GetCell(cell).GetPoints().GetData())
                dxf_model.add_polyline3d(border_points, dxfattribs={'layer': layer})
            print("entity exported\n")

            # """Exports a triangulated surface to a DXF polyface (a subclass of POLYLINE that on get_mode() returns 'AcDbPolyFaceMesh'."""
            # if isinstance(self.geol_coll.get_uid_vtk_obj(uid), TriSurf):
            #     dxf_out = ezdxf.new('R2000')  # MESH requires DXF R2000 or later
            #     dxf_model = dxf_out.modelspace()
            #     vtk_entity = self.geol_coll.get_uid_vtk_obj(uid)
            #     """polyface"""
            #     polyface = dxf_model.add_polyface({'layer': uid})
            #     for i in range(vtk_entity.GetNumberOfCells()):
            #         face_points = numpy_support.vtk_to_numpy(vtk_entity.GetCell(i).GetPoints().GetData())
            #         polyface.append_face(face_points)
            #     # polyface.optimize()
            #     """save file"""

            # """Exports a polyline to a DXF POLYLINE object."""
            # if isinstance(self.geol_coll.get_uid_vtk_obj(uid), PolyLine):
            #     dxf_out = ezdxf.new()
            #     dxf_model = dxf_out.modelspace()
            #     vtk_entity = self.geol_coll.get_uid_vtk_obj(uid)
            #     for i in range(vtk_entity.GetNumberOfCells()):
            #         dxf_model.add_polyline3d((vtk_entity.GetCell(i).GetPoints().GetPoint(0),
            #                                   vtk_entity.GetCell(i).GetPoints().GetPoint(1)))

    """Save DXF file."""
    # out_file_name = (str(out_dir_name) + "/3dface_border.dxf")
    out_file_name = (str(out_dir_name) + "/3dface_border_attributes.dxf")
    print("Writing DXF... please wait.")
    dxf_out.saveas(out_file_name)
    print("DXF file saved")
