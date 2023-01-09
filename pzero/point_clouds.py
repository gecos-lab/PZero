from vtk import vtkSelectionNode, vtkSelection, vtkExtractSelection, vtkIdTypeArray
import numpy as np

from .entities_factory import PCDom



def extract_id(entity, ids):

    selection_node = vtkSelectionNode()
    selection_node.SetFieldType(vtkSelectionNode.POINT)
    selection_node.SetContentType(vtkSelectionNode.INDICES)
    selection_node.SetSelectionList(ids)

    selection = vtkSelection()
    selection.AddNode(selection_node)

    extract_selection = vtkExtractSelection()
    extract_selection.SetInputData(0, entity)
    extract_selection.SetInputData(1, selection)
    extract_selection.Update()

    vtk_ps_subset = PCDom()
    vtk_ps_subset.ShallowCopy(extract_selection.GetOutput())
    vtk_ps_subset.remove_point_data('vtkOriginalPointIds')
    vtk_ps_subset.Modified()

    return vtk_ps_subset


def decimate_pc(entity,fac):
    dec_fac = int(entity.GetNumberOfPoints() * fac)
    random = np.random.choice(entity.GetNumberOfPoints(),dec_fac)

    ids = vtkIdTypeArray()

    for i in random:
        ids.InsertNextValue(i)

    selection = extract_id(entity,ids)

    return selection
