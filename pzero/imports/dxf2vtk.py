"""gocad2vtk.py
PZero© Andrea Bistacchi"""

from ezdxf import new as ezdxf_new

from pandas import DataFrame as pd_DataFrame

from vtkmodules.util import numpy_support

from pzero.entities_factory import TriSurf


def vtk2dxf(self=None, out_dir_name=None):
    """Exports all triangulated surfaces to a collection of DXF 3DFACE objects and border polyline3d."""
    """Create DXF container."""
    """Add entities."""
    list_uids = []
    list_names = []
    for uid in self.geol_coll.df["uid"]:
        if isinstance(self.geol_coll.get_uid_vtk_obj(uid), TriSurf):
            legend = self.geol_coll.get_uid_legend(uid=uid)
            R = legend["color_R"]
            G = legend["color_G"]
            B = legend["color_B"]
            parts = self.geol_coll.get_uid_vtk_obj(uid).split_parts()
            # print(len(parts))
            for i, part in enumerate(parts):
                dxf_out = ezdxf_new()
                dxf_model = dxf_out.modelspace()
                # print(part)
                df = pd_DataFrame()
                dfb = pd_DataFrame()
                vtk_entity = part
                # test_pc = pv.PolyData()
                #
                # test_pc.ShallowCopy(vtk_entity)
                # test_pc.plot()

                layer = f'{self.geol_coll.df.loc[self.geol_coll.df["uid"] == uid, "feature"].values[0]}'

                layer_b = f"{layer}_boundary"

                xyz = numpy_support.vtk_to_numpy(vtk_entity.GetPoints().GetData())

                df["x"] = xyz[:, 0]
                df["y"] = xyz[:, 1]
                df["z"] = xyz[:, 2]

                dxf_out.layers.add(name=layer)
                dxf_out.layers.add(name=layer_b)

                surf_layer = dxf_out.layers.get(layer)
                surf_layer.rgb = (R, G, B)

                boun_layer = dxf_out.layers.get(layer_b)
                boun_layer.rgb = (R, G, B)

                """3D faces"""
                for c in range(vtk_entity.GetNumberOfCells()):
                    face_points = numpy_support.vtk_to_numpy(
                        vtk_entity.GetCell(c).GetPoints().GetData()
                    )
                    if len(face_points) < 3:
                        print(f"problem with cell {c} in {layer}, skipping cell")
                    else:
                        dxf_model.add_3dface(
                            face_points, dxfattribs={"layer": layer, "color": 256}
                        )

                """border -> https://lorensen.github.io/VTKExamples/site/Python/Meshes/BoundaryEdges/"""
                vtk_border = vtk_entity.get_clean_boundary()

                xyz_b = numpy_support.vtk_to_numpy(vtk_border.GetPoints().GetData())
                dfb["x"] = xyz_b[:, 0]
                dfb["y"] = xyz_b[:, 1]
                dfb["z"] = xyz_b[:, 2]

                for cell in range(vtk_border.GetNumberOfCells()):
                    border_points = numpy_support.vtk_to_numpy(
                        vtk_border.GetCell(cell).GetPoints().GetData()
                    )
                    dxf_model.add_polyline3d(
                        border_points, dxfattribs={"layer": layer_b, "color": 256}
                    )
                # print("entity exported\n")
                if len(parts) > 1:
                    out_file_name = f"{uid}_{layer}_part{i}"
                    list_uids.append(uid)
                    list_names.append(f"{layer}_part{i}")
                else:
                    out_file_name = f"{uid}_{layer}"
                    list_uids.append(uid)
                    list_names.append(layer)

                # print("Writing DXF... please wait.")
                df.to_csv(f"{out_dir_name}/csv/{out_file_name}.csv", index=False)
                dfb.to_csv(
                    f"{out_dir_name}/csv/{out_file_name}_border.csv", index=False
                )

                dxf_out.saveas(f"{out_dir_name}/dxf/{out_file_name}.dxf")

            # """Exports a triangulated surface to a DXF polyface (a subclass of POLYLINE that on get_mode() returns 'AcDbPolyFaceMesh'."""
            # if isinstance(self.geol_coll.get_uid_vtk_obj(uid), TriSurf):
            #     dxf_out = ezdxf_new('R2000')  # MESH requires DXF R2000 or later
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
            #     dxf_out = ezdxf_new()
            #     dxf_model = dxf_out.modelspace()
            #     vtk_entity = self.geol_coll.get_uid_vtk_obj(uid)
            #     for i in range(vtk_entity.GetNumberOfCells()):
            #         dxf_model.add_polyline3d((vtk_entity.GetCell(i).GetPoints().GetPoint(0),
            #                                   vtk_entity.GetCell(i).GetPoints().GetPoint(1)))
    for uid in self.boundary_coll.df["uid"]:
        if isinstance(self.boundary_coll.get_uid_vtk_obj(uid), TriSurf):
            layer = (
                uid
                + "_"
                + self.boundary_coll.df.loc[
                    self.boundary_coll.df["uid"] == uid, "name"
                ].values[0]
            )
            vtk_entity = self.boundary_coll.get_uid_vtk_obj(uid)
            """3D faces"""
            for i in range(vtk_entity.GetNumberOfCells()):
                face_points = numpy_support.vtk_to_numpy(
                    vtk_entity.GetCell(i).GetPoints().GetData()
                )
                dxf_model.add_3dface(face_points, dxfattribs={"layer": layer})
            # """border -> https://lorensen.github.io/VTKExamples/site/Python/Meshes/BoundaryEdges/"""
            # vtk_border = vtk_entity.get_clean_boundary()
            # for cell in range(vtk_border.GetNumberOfCells()):
            #     border_points = numpy_support.vtk_to_numpy(vtk_border.GetCell(cell).GetPoints().GetData())
            #     dxf_model.add_polyline3d(border_points, dxfattribs={'layer': layer})
            print("entity exported\n")
    for uid in self.well_coll.df["uid"]:
        legend = self.well_coll.get_uid_legend(uid=uid)
        vtk_entity = self.well_coll.get_uid_vtk_obj(uid)
        R = legend["color_R"]
        G = legend["color_G"]
        B = legend["color_B"]
        dxf_out = ezdxf_new()
        dxf_model = dxf_out.modelspace()
        # print(part)
        df = pd_DataFrame()
        layer = f'{self.well_coll.df.loc[self.well_coll.df["uid"] == uid, "feature"].values[0]}'

        xyz = numpy_support.vtk_to_numpy(vtk_entity.GetPoints().GetData())

        df["x"] = xyz[:, 0]
        df["y"] = xyz[:, 1]
        df["z"] = xyz[:, 2]

        dxf_out.layers.add(name=layer)

        line_layer = dxf_out.layers.get(layer)
        line_layer.rgb = (R, G, B)

        for cell in range(vtk_entity.GetNumberOfCells()):
            line_points = numpy_support.vtk_to_numpy(
                vtk_entity.GetCell(cell).GetPoints().GetData()
            )
            dxf_model.add_polyline3d(
                line_points, dxfattribs={"layer": layer, "color": 256}
            )
        # print("entity exported\n")

        out_file_name = f"{uid}_{layer}"
        list_uids.append(uid)
        list_names.append(layer)

        # print("Writing DXF... please wait.")
        df.to_csv(f"{out_dir_name}/csv/{out_file_name}.csv", index=False)

        dxf_out.saveas(f"{out_dir_name}/dxf/{out_file_name}.dxf")

    complete_list = pd_DataFrame({"uids": list_uids, "features": list_names})
    complete_list.to_csv(f"{out_dir_name}/exported_object_list.csv", index=False)
    """Save DXF file."""
    # out_file_name = (str(out_dir_name) + "/3dface_border.dxf")
    # out_file_name = (str(out_dir_name) + "/3dface_border_attributes.dxf")
    # print("Writing DXF... please wait.")
    # dxf_out.saveas(out_file_name)
    # print("DXF file saved")
