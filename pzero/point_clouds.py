from copy import deepcopy

from pyvista.core.filters import _update_alg
from vtkmodules.util import numpy_support
from vtkmodules.vtkCommonCore import vtkIdTypeArray
from vtkmodules.vtkCommonDataModel import vtkDataObject, vtkImplicitSelectionLoop, vtkPolyData, vtkSelectionNode, \
    vtkSelection, vtkPlane
from vtkmodules.vtkFiltersCore import vtkThreshold, vtkAppendPolyData, vtkThresholdPoints, vtkDelaunay2D, \
    vtkMassProperties
from vtkmodules.vtkFiltersExtraction import vtkExtractGeometry, vtkExtractSelection
from vtkmodules.vtkFiltersPoints import vtkEuclideanClusterExtraction, vtkRadiusOutlierRemoval, vtkProjectPointsToPlane

from .entities_factory import PCDom, TriSurf
from .helper_functions import best_fitting_plane
from .helper_widgets import Scissors

from numpy import max as np_max
from numpy import random as np_random
from numpy import repeat as np_repeat
from numpy import pi as np_pi
from numpy import arctan2 as np_arctan2
from numpy import arcsin as np_arcsin
from numpy import zeros_like as np_zeros_like
from numpy import std as np_std


def extract_id(vtk_obj, ids):

    selection_node = vtkSelectionNode()
    selection_node.SetFieldType(vtkSelectionNode.POINT)
    selection_node.SetContentType(vtkSelectionNode.INDICES)
    selection_node.SetSelectionList(ids)

    selection = vtkSelection()
    selection.AddNode(selection_node)

    extract_selection = vtkExtractSelection()
    extract_selection.SetInputData(0, vtk_obj)
    extract_selection.SetInputData(1, selection)
    extract_selection.Update()

    vtk_ps_subset = PCDom()
    vtk_ps_subset.ShallowCopy(extract_selection.GetOutput())
    vtk_ps_subset.remove_point_data('vtkOriginalPointIds')
    vtk_ps_subset.Modified()

    return vtk_ps_subset


def cut_pc(self):
    def end_digitize(event):
        self.plotter.untrack_click_position()
        uid = self.selected_uids[0]
        data = self.parent.dom_coll.get_uid_vtk_obj(uid)
        # Signal called to end the digitization of a trace. It returns a new polydata
        loop = vtkImplicitSelectionLoop()
        tem = vtkPolyData()
        scissors.GetContourRepresentation().GetNodePolyData(tem)
        loop.SetLoop(scissors.GetContourRepresentation().GetContourRepresentationAsPolyData().GetPoints())
        clip = vtkExtractGeometry()
        clip.SetInputData(data)
        clip.SetImplicitFunction(loop)
        clip.ExtractInsideOn()
        clip.Update()

        clip_in = PCDom()
        clip_in.ShallowCopy(clip.GetOutput())
        clip.ExtractInsideOff()
        clip.Modified()
        clip.Update()
        clip_out = PCDom()
        clip_out.ShallowCopy(clip.GetOutput())
        entity_dict = deepcopy(self.parent.dom_coll.dom_entity_dict)
        # print(entity_dict)
        entity_dict['name'] = self.parent.dom_coll.get_uid_name(uid) + '_cut_in'
        entity_dict['vtk_obj'] = clip_in
        entity_dict['dom_type'] = 'PCDom'
        entity_dict['properties_names'] = self.parent.dom_coll.get_uid_properties_names(uid)
        entity_dict['dom_type'] = 'PCDom'
        entity_dict['properties_components'] = self.parent.dom_coll.get_uid_properties_components(uid)
        entity_dict['vtk_obj'] = clip_in
        self.parent.dom_coll.add_entity_from_dict(entity_dict)

        entity_dict = deepcopy(self.parent.dom_coll.dom_entity_dict)
        # print(entity_dict)
        entity_dict['name'] = self.parent.dom_coll.get_uid_name(uid) + '_cut_out'
        entity_dict['vtk_obj'] = clip_out
        entity_dict['dom_type'] = 'PCDom'
        entity_dict['properties_names'] = self.parent.dom_coll.get_uid_properties_names(uid)
        entity_dict['dom_type'] = 'PCDom'
        entity_dict['properties_components'] = self.parent.dom_coll.get_uid_properties_components(uid)
        entity_dict['vtk_obj'] = clip_out

        self.parent.dom_coll.add_entity_from_dict(entity_dict)

        scissors.EnabledOff()
        self.enable_actions()
        self.clear_selection()

    if not self.selected_uids:
        print(" -- No input data selected -- ")
        return
    """Freeze QT interface"""
    self.disable_actions()

    """Getting the values that have been typed by the user through the widget"""

    scissors = Scissors(self)
    scissors.EnabledOn()
    self.plotter.track_click_position(side='right', callback= end_digitize)


def decimate_pc(vtk_obj, fac):
    dec_fac = int(vtk_obj.GetNumberOfPoints() * fac)
    random = np_random.choice(vtk_obj.GetNumberOfPoints(),dec_fac)

    ids = vtkIdTypeArray()

    for i in random:
        ids.InsertNextValue(i)

    selection = extract_id(vtk_obj, ids)

    return selection


def thresh_pc(vtk_obj, prop, lt, ht):
    thresh = vtkThreshold()
    thresh.SetInputData(vtk_obj)
    thresh.SetInputArrayToProcess(0, 0, 0, vtkDataObject.FIELD_ASSOCIATION_POINTS, prop)
    thresh.SetLowerThreshold(float(lt))
    thresh.SetUpperThreshold(float(ht))
    thresh.Update()
    out = PCDom()
    out.ShallowCopy(thresh.GetOutput())
    out.generate_cells()
    return out


def rad_pc(vtk_obj, rad, nn):
    r = vtkRadiusOutlierRemoval()
    r.SetInputData(vtk_obj)
    r.SetRadius(rad)
    r.SetNumberOfNeighbors(nn)
    r.GenerateOutliersOff()

    _update_alg(r, True, 'Cleaning pc')
    pc_clean = r.GetOutput()
    return pc_clean


def extract_pc(vtk_obj, scissors):

    loop = vtkImplicitSelectionLoop()
    loop.SetLoop(scissors.GetContourRepresentation().GetContourRepresentationAsPolyData().GetPoints())
    clip_out = vtkExtractGeometry()
    clip_out.SetInputData(vtk_obj)
    clip_out.SetImplicitFunction(loop)
    clip_out.SetExtractInside(False)
    clip_out.Update()

    clip_in = vtkExtractGeometry()
    clip_in.SetInputData(vtk_obj)
    clip_in.SetImplicitFunction(loop)
    clip_in.SetExtractInside(True)
    clip_in.Update()

    clipped_out = clip_out.GetOutput()
    clipped_in = clip_in.GetOutput()

    out_ent = PCDom()
    in_ent = PCDom()
    out_ent.ShallowCopy(clipped_out)
    in_ent.ShallowCopy(clipped_in)

    return out_ent, in_ent


def segment_pc(vtk_obj, ldd, hdd, ld, hd, rad, nn):

    vtk_obj.GetPointData().SetActiveScalars('dip direction')
    connectivity_filter_dd = vtkEuclideanClusterExtraction()
    connectivity_filter_dd.SetInputData(vtk_obj)
    connectivity_filter_dd.SetRadius(rad)
    connectivity_filter_dd.SetExtractionModeToAllClusters()
    connectivity_filter_dd.ScalarConnectivityOn()
    connectivity_filter_dd.SetScalarRange(ldd, hdd)
    _update_alg(connectivity_filter_dd, True, 'Segmenting on dip directions')
    f1 = connectivity_filter_dd.GetOutput()
    # print(f1)
    f1.GetPointData().SetActiveScalars('dip')
    # print(f1.GetNumberOfPoints())
    #
    connectivity_filter_dip = vtkEuclideanClusterExtraction()
    connectivity_filter_dip.SetInputData(f1)
    connectivity_filter_dip.SetRadius(rad)
    connectivity_filter_dip.SetExtractionModeToAllClusters()
    connectivity_filter_dip.ColorClustersOn()
    connectivity_filter_dip.ScalarConnectivityOn()
    connectivity_filter_dip.SetScalarRange(ld, hd)

    _update_alg(connectivity_filter_dip, True, 'Segmenting dips')

    n_clusters = connectivity_filter_dip.GetNumberOfExtractedClusters()

    # print(n_clusters)

    pc = connectivity_filter_dip.GetOutput()
    pc.GetPointData().SetActiveScalars('ClusterId')
    appender_pc = vtkAppendPolyData()
    for i in range(n_clusters):
        print(f'{i}/{n_clusters}', end='\r')

        thresh = vtkThresholdPoints()

        thresh.SetInputData(pc)
        thresh.ThresholdBetween(i, i)

        thresh.Update()
        if thresh.GetOutput().GetNumberOfPoints() >= nn:
            appender_pc.AddInputData(thresh.GetOutput())
    appender_pc.Update()

    seg_pc = PCDom()
    seg_pc.ShallowCopy(appender_pc.GetOutput())
    seg_pc.generate_cells()
    return seg_pc


def facets_pc(vtk_obj):

    appender = vtkAppendPolyData()
    max_region = np_max(vtk_obj.get_point_data('ClusterId'))
    vtk_obj.GetPointData().SetActiveScalars('ClusterId')
    for i in range(max_region):
        print(f'{i}/{max_region}', end='\r')

        thresh = vtkThresholdPoints()

        thresh.SetInputData(vtk_obj)
        thresh.ThresholdBetween(i, i)

        thresh.Update()
        points = numpy_support.vtk_to_numpy(thresh.GetOutput().GetPoints().GetData())
        n_points = thresh.GetOutput().GetNumberOfPoints()
        if n_points > 0:
            c, n = best_fitting_plane(points)
            if n[2] >= 0:
                n *= -1
            dd = np_repeat((np_arctan2(n[0], n[1]) * 180 / np_pi - 180) % 360, n_points)
            d = np_repeat(90 - np_arcsin(-n[2]) * 180 / np_pi, n_points)

            facet = TriSurf()
            plane_proj = vtkProjectPointsToPlane()
            plane_proj.SetInputData(thresh.GetOutput())
            plane_proj.SetProjectionTypeToBestFitPlane()

            delaunay = vtkDelaunay2D()
            delaunay.SetInputConnection(plane_proj.GetOutputPort())
            delaunay.SetProjectionPlaneMode(2)
            delaunay.Update()
            facet.ShallowCopy(delaunay.GetOutput())
            facet.remove_point_data('Normals')
            facet.set_point_data('dip direction', dd)
            facet.set_point_data('dip', d)
            mass = vtkMassProperties()
            mass.SetInputData(facet)
            mass.Update()
            area = np_repeat(mass.GetSurfaceArea(), n_points)
            facet.set_point_data('surf_area', area)
            appender.AddInputData(facet)

    appender.Update()

    facets = TriSurf()
    facets.ShallowCopy(appender.GetOutput())

    return facets


def calibration_pc(vtk_objs):

    n_points = np_zeros_like(len(vtk_objs))

    normals_var = np_zeros_like(len(vtk_objs))
    for i, vtk_obj in enumerate(vtk_objs):
        points = vtk_obj.points
        normals = numpy_support.vtk_to_numpy(vtk_obj.GetPointData().GetScalars('Normals'))
        n_points[i] = vtk_obj.GetNumberOfPoints()
        normals_var[i] = np_std(normals, axis=0)

        c, n = best_fitting_plane(points)
        if n[2] >= 0:
            n *= -1

        plane2 = vtkPlane()
        plane2.SetOrigin(c)
        plane2.SetNormal(n)

        distances = []

        for point in points:
            distances.append(plane2.DistanceToPlane(point))

        # Calculate distance from fitted plane -> estimate of roughness
        # Calculate mean distance from fitted plane
        # Calculate vector normal direction variation (over the 3 components) ->SRF
        # Calculate surface density for given facet and volume density (how?)
        # Calculate loading scores.
        # Calculate N of neighbours
