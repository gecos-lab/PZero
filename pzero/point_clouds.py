import vtk
from vtk.util import numpy_support
import pyvista as pv
import numpy as np

from .entities_factory import PCDom



def extract_id(entity, ids):

    if isinstance(ids,vtk.vtkIdList):
        id_list = vtk.vtkIdTypeArray()
        for i in range(idlist.GetNumberOfIds()):
            id_list.InsertNextValue(ids.GetId(i))

    else:
        id_list = ids
    selection_node = vtk.vtkSelectionNode()
    selection_node.SetFieldType(vtk.vtkSelectionNode.POINT)
    selection_node.SetContentType(vtk.vtkSelectionNode.INDICES)
    selection_node.SetSelectionList(id_list)

    selection = vtk.vtkSelection()
    selection.AddNode(selection_node)

    extract_selection = vtk.vtkExtractSelection()
    extract_selection.SetInputData(0, entity)
    extract_selection.SetInputData(1, selection)
    extract_selection.Update()
    # print(extract_selection.GetOutput())

    vtk_ps_subset = PCDom()
    vtk_ps_subset.ShallowCopy(extract_selection.GetOutput())
    vtk_ps_subset.remove_point_data('vtkOriginalPointIds')
    vtk_ps_subset.Modified()

    return vtk_ps_subset


def decimate_pc(entity,fac):
    dec_fac = int(entity.GetNumberOfPoints() * fac)
    random = np.random.choice(entity.GetNumberOfPoints(),dec_fac)

    ids = vtk.vtkIdTypeArray()

    for i in random:
        ids.InsertNextValue(i)

    selection = extract_id(entity,ids)

    return selection


# def segm_pc(entity,rad,dd1,dd2,d1,d2,nn):
#
#     vtk_obj.GetPointData().SetActiveScalars('dip direction')
#     connectivity_filter_dd = vtk.vtkEuclideanClusterExtraction()
#     connectivity_filter_dd.SetInputData(vtk_ps)
#     connectivity_filter_dd.SetRadius(rad)
#     connectivity_filter_dd.SetExtractionModeToAllClusters()
#     connectivity_filter_dd.ScalarConnectivityOn()
#     connectivity_filter_dd.SetScalarRange(dd1,dd2)
#     _update_alg(connectivity_filter_dd,True,'Segmenting on dip directions')
#     f1 = connectivity_filter_dd.GetOutput()
#     # print(f1)
#     f1.GetPointData().SetActiveScalars('dip')
#     # print(f1.GetNumberOfPoints())
#     #
#     connectivity_filter_dip = vtk.vtkEuclideanClusterExtraction()
#     connectivity_filter_dip.SetInputData(f1)
#     connectivity_filter_dip.SetRadius(rad])
#     connectivity_filter_dip.SetExtractionModeToAllClusters()
#     connectivity_filter_dip.ColorClustersOn()
#     connectivity_filter_dip.ScalarConnectivityOn()
#     connectivity_filter_dip.SetScalarRange(d1,d2)
#
#     _update_alg(connectivity_filter_dip,True,'Segmenting dips')
#
#     n_clusters = connectivity_filter_dip.GetNumberOfExtractedClusters()
#
#     # print(n_clusters)
#
#     r = vtk.vtkRadiusOutlierRemoval()
#     r.SetInputData(connectivity_filter_dip.GetOutput())
#     r.SetRadius(rad)
#     r.SetNumberOfNeighbors(nn)
#     r.GenerateOutliersOff()
#
#     r.Update()
#     appender = vtk.vtkAppendPolyData()
#
#     for i in range(n_clusters):
#
#         thresh = vtk.vtkThresholdPoints()
#
#         thresh.SetInputConnection(r.GetOutputPort())
#         thresh.ThresholdBetween(i,i)
#
#         thresh.Update()
#
#         points = numpy_support.vtk_to_numpy(thresh.GetOutput().GetPoints().GetData())
#         c,n,_ = best_fitting_plane(points)
#         if n[0] >= 0:
#             n *= -1
#         plane = pv.Plane(center = c, direction= n)
#
#         appender.AddInputData(plane)
#             # appender_arrows.AddInputData(normal)
#
#     appender.Update()
