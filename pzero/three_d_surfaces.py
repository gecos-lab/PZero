"""three_d_surfaces.py
PZero© Andrea Bistacchi"""

from copy import deepcopy
from vtk.util import numpy_support
from scipy.interpolate import griddata
import vtk
import numpy as np
import pandas as pd
from .geological_collection import GeologicalCollection
from .mesh3d_collection import Mesh3DCollection
from .helper_dialogs import multiple_input_dialog, input_one_value_dialog, input_text_dialog, input_combo_dialog, input_checkbox_dialog, tic, toc
from .entities_factory import TriSurf, XsPolyLine, PolyLine, VertexSet, Voxet, XsVoxet, XsTSurf, XsVertexSet, MapImage, DEM

"""LoopStructural import(s)"""
import LoopStructural as loop3d  # which name?


def interpolation_delaunay_2d(self):
    """The vtkDelaunay2D object takes vtkPointSet (or any of its subclasses) as input and
    generates a vtkPolyData on output - tipically a triangle mesh if Alpha value is not defined.
    Select the whole line of two or more vtkPointSet entities and start the algorithm."""
    print("Delaunay2D: interpolation of Points, Lines and Surfaces")
    if self.shown_table != "tabGeology":
        print(" -- Only geological objects can be interpolated -- ")
        return
    """Check if some vtkPolyData is selected"""
    if not self.selected_uids:
        print(" -- No input data selected -- ")
        return
    else:
        """Deep copy list of selected uids needed otherwise problems can arise if the main geology table is deselected while the dataframe is being built"""
        input_uids = deepcopy(self.selected_uids)
    for uid in input_uids:
        if isinstance(self.geol_coll.get_uid_vtk_obj(uid), PolyLine) or isinstance(self.geol_coll.get_uid_vtk_obj(uid), XsPolyLine) or isinstance(self.geol_coll.get_uid_vtk_obj(uid), VertexSet) or isinstance(self.geol_coll.get_uid_vtk_obj(uid), XsVertexSet) or isinstance(self.geol_coll.get_uid_vtk_obj(uid), TriSurf):
            pass
        else:
            print(" -- Error input type -- ")
            return
    """Create deepcopy of the geological entity dictionary."""
    surf_dict = deepcopy(self.geol_coll.geological_entity_dict)
    input_dict = {'name': ['TriSurf name: ', self.geol_coll.get_uid_name(input_uids[0]) + '_delaunay2d'], 'geological_type': ['Geological type: ', GeologicalCollection.valid_geological_types], 'geological_feature': ['Geological feature: ', self.geol_coll.get_uid_geological_feature(input_uids[0])], 'scenario': ['Scenario: ', self.geol_coll.get_uid_scenario(input_uids[0])]}
    surf_dict_updt = multiple_input_dialog(title='New Delaunay 2D interpolation', input_dict=input_dict)
    """Check if the output of the widget is empty or not. If the Cancel button was clicked, the tool quits"""
    if surf_dict_updt is None:
        return
    """Ask for the Tolerance and Alpha values. Tolerance controls discarding of closely spaced points. 
    Alpha controls the 'size' of output primitivies - a 0 Alpha Value outputs a triangle mesh."""
    tolerance_value = input_one_value_dialog(title='Delaunay2D Parameters', label='Tolerance Value', default_value=0.001)
    if tolerance_value is None:
        tolerance_value = 0.001
    alpha_value = input_one_value_dialog(title='Delaunay2D Parameters', label='Alpha Value', default_value=0)
    if alpha_value is None:
        alpha_value = 0
    """Getting the values that have been typed by the user through the multiple input widget"""
    for key in surf_dict_updt:
        surf_dict[key] = surf_dict_updt[key]
    surf_dict['topological_type'] = 'TriSurf'
    surf_dict['vtk_obj'] = TriSurf()
    """Create a vtkAppendPolyData filter to merge all input vtk objects. Else, it does not seem possible to
    input multiple objects into vtkDelaunay2D"""
    vtkappend = vtk.vtkAppendPolyData()
    for uid in input_uids:
        vtkappend.AddInputData(self.geol_coll.get_uid_vtk_obj(uid))
    vtkappend.Update()
    """Create a new instance of the interpolation class"""
    delaunay_2d = vtk.vtkDelaunay2D()
    delaunay_2d.SetInputDataObject(vtkappend.GetOutput())
    delaunay_2d.SetTolerance(tolerance_value)
    delaunay_2d.SetAlpha(alpha_value)
    delaunay_2d.Update()  # executes the interpolation
    """ShallowCopy is the way to copy the new interpolated surface into the TriSurf instance created at the beginning"""
    surf_dict['vtk_obj'].ShallowCopy(delaunay_2d.GetOutput())
    surf_dict['vtk_obj'].Modified()
    """Add new entity from surf_dict. Function add_entity_from_dict creates a new uid"""
    if surf_dict['vtk_obj'].points_number > 0:
        self.geol_coll.add_entity_from_dict(surf_dict)
    else:
        print(" -- empty object -- ")


def poisson_interpolation(self):
    """vtkSurfaceReconstructionFilter can be used to reconstruct surfaces from point clouds. Input is a vtkDataSet
    defining points assumed to lie on the surface of a 3D object."""
    print("Interpolation from point cloud: build surface from interpolation")
    if self.shown_table != "tabGeology":
        print(" -- Only geological objects can be interpolated -- ")
        return
    """Check if some vtkPolyData is selected"""
    if not self.selected_uids:
        print("No input data selected.")
        return
    else:
        """Deep copy list of selected uids needed otherwise problems can arise if the main geology table is deseselcted while the dataframe is being built"""
        input_uids = deepcopy(self.selected_uids)
    for uid in input_uids:
        if isinstance(self.geol_coll.get_uid_vtk_obj(uid), PolyLine) or isinstance(self.geol_coll.get_uid_vtk_obj(uid), XsPolyLine) or isinstance(self.geol_coll.get_uid_vtk_obj(uid), VertexSet) or isinstance(self.geol_coll.get_uid_vtk_obj(uid), XsVertexSet) or isinstance(self.geol_coll.get_uid_vtk_obj(uid), TriSurf):
            pass
        else:
            print(" -- Error input type -- ")
            return
    """Create deepcopy of the geological entity dictionary."""
    surf_dict = deepcopy(self.geol_coll.geological_entity_dict)
    input_dict = {'name': ['TriSurf name: ', self.geol_coll.get_uid_name(input_uids[0]) + '_cloud'], 'geological_type': ['Geological type: ', GeologicalCollection.valid_geological_types], 'geological_feature': ['Geological feature: ', self.geol_coll.get_uid_geological_feature(input_uids[0])], 'scenario': ['Scenario: ', self.geol_coll.get_uid_scenario(input_uids[0])]}
    surf_dict_updt = multiple_input_dialog(title='Surface interpolation from point cloud', input_dict=input_dict)
    """Check if the output of the widget is empty or not. If the Cancel button was clicked, the tool quits"""
    if surf_dict_updt is None:
        return
    """Getting the values that have been typed by the user through the multiple input widget"""
    for key in surf_dict_updt:
        surf_dict[key] = surf_dict_updt[key]
    surf_dict['topological_type'] = 'TriSurf'
    surf_dict['vtk_obj'] = TriSurf()
    """Create a new instance of the interpolation class"""
    surf_from_points = vtk.vtkSurfaceReconstructionFilter()
    sample_spacing = input_one_value_dialog(title='Surface interpolation from point cloud', label='Sample Spacing', default_value=-1.0)
    if sample_spacing is None:
        pass
    else:
        surf_from_points.SetSampleSpacing(sample_spacing)
    neighborhood_size = input_one_value_dialog(title='Surface interpolation from point cloud', label='Neighborhood Size', default_value=20)
    if neighborhood_size is None:
        pass
    else:
        surf_from_points.SetNeighborhoodSize(int(neighborhood_size))
    """Create a vtkAppendPolyData filter to merge all input vtk objects."""
    vtkappend = vtk.vtkAppendPolyData()
    for uid in input_uids:
        if self.geol_coll.get_uid_topological_type(input_uids[0]) == 'XsPolyLine' or self.geol_coll.get_uid_topological_type(input_uids[0]) == 'PolyLine' or self.geol_coll.get_uid_topological_type(input_uids[0]) == 'TriSurf':
            """Extract points from vtkpolydata"""
            point_coord = self.geol_coll.get_uid_vtk_obj(uid).points
            points = vtk.vtkPoints()
            x = 0
            for row in point_coord:
                points.InsertPoint(x, point_coord[x, 0], point_coord[x, 1], point_coord[x, 2])
                x += 1
            polydata = vtk.vtkPolyData()
            polydata.SetPoints(points)
            vtkappend.AddInputData(polydata)
        elif self.geol_coll.get_uid_topological_type(input_uids[0]) == 'VertexSet':
            vtkappend.AddInputData(self.geol_coll.get_uid_vtk_obj(uid))
    vtkappend.Update()
    """The created vtkPolyData is used as the input for vtkSurfaceReconstructionFilter"""
    surf_from_points.SetInputDataObject(vtkappend.GetOutput())
    surf_from_points.Update()  # executes the interpolation. Output is vtkImageData
    """Contour the grid at zero to extract the surface"""
    contour_surface = vtk.vtkContourFilter()
    contour_surface.SetInputData(surf_from_points.GetOutput())
    contour_surface.SetValue(0, 0.0)
    contour_surface.Update()
    """ShallowCopy is the way to copy the new interpolated surface into the TriSurf instance created at the beginning"""
    surf_dict['vtk_obj'].ShallowCopy(contour_surface.GetOutput())
    surf_dict['vtk_obj'].Modified()
    """Add new entity from surf_dict. Function add_entity_from_dict creates a new uid"""
    if surf_dict['vtk_obj'].points_number > 0:
        self.geol_coll.add_entity_from_dict(surf_dict)
    else:
        print(" -- empty object -- ")


def implicit_model_loop_structural(self):
    """Function to call LoopStructural's implicit modelling algorithms.
    Input Data is organized as the following columns:
    X - x component of the cartesian coordinates
    Y - y component of the cartesian coordinates
    Z - z component of the cartesian coordinates
    feature_name - unique name of the geological feature being modelled - this is not the geological_feature generally defined in geological_collection.py, but the geological_sequence defined in legend_manager.py
    val - value observations of the scalar field - this is the geological_time defined in legend_manager.py
    interface - unique identifier for an interface containing similar scalar field values
    nx - x component of the gradient norm
    ny - y component of the gradient norm
    nz - z component of the gradient norm
    gx - x component of a gradient constraint
    gy - y component of a gradient constraint
    gz - z component of a gradient constraint
    tx - x component of a gradient tangent constraint
    ty - y component of a gradient tangent constraint
    tz - z component of a gradient tangent constraint
    coord - coordinate of the structural frame data point is used for ???
    """
    print("LoopStructural implicit geomodeller\ngithub.com/Loop3D/LoopStructural")
    if self.shown_table != "tabGeology":
        print(" -- Only geological objects can be interpolated -- ")
        return
    """Check if some vtkPolyData is selected"""
    if not self.selected_uids:
        print("No input data selected.")
        return
    else:
        """Deep copy list of selected uids needed otherwise problems can arise if the main geology table is deseselcted while the dataframe is being built"""
        input_uids = deepcopy(self.selected_uids)
    "Dictionary used to define the fields of the Loop input data Pandas dataframe."
    loop_input_dict = {"X": None, "Y": None, "Z": None, "feature_name": None, "val": None, "interface": None, "nx": None, "ny": None, "nz": None, "gx": None, "gy": None, "gz": None, "tx": None, "ty": None, "tz": None, "coord": None}
    """Create empty dataframe to collect all input data."""
    print("-> creating input dataframe...")
    tic()
    all_input_data_df = pd.DataFrame(columns=list(loop_input_dict.keys()))
    """For every selected item extract interesting data: XYZ, feature_name, val, etc."""
    for uid in input_uids:
        """Create empty dataframe to collect input data for this object."""
        entity_input_data_df = pd.DataFrame(columns=list(loop_input_dict.keys()))
        """XYZ data for every selected entity.
        Adding all columns at once is about 10% faster than adding them separately, but still slow."""
        entity_input_data_df[['X', 'Y', 'Z']] = self.geol_coll.get_uid_vtk_obj(uid).points
        if 'Normals' in self.geol_coll.get_uid_properties_names(uid):
            entity_input_data_df[['nx', 'ny', 'nz']] = self.geol_coll.get_uid_property(uid=uid, property_name='Normals')
        """feature_name value"""
        featname_single = self.geol_legend_df.loc[(self.geol_legend_df['geological_type'] == self.geol_coll.get_uid_geological_type(uid)) & (self.geol_legend_df['geological_feature'] == self.geol_coll.get_uid_geological_feature(uid)) & (self.geol_legend_df['scenario'] == self.geol_coll.get_uid_scenario(uid)), 'geological_sequence'].values[0]
        entity_input_data_df['feature_name'] = featname_single
        """val value"""
        val_single = self.geol_legend_df.loc[(self.geol_legend_df['geological_type'] == self.geol_coll.get_uid_geological_type(uid)) & (self.geol_legend_df['geological_feature'] == self.geol_coll.get_uid_geological_feature(uid)) & (self.geol_legend_df['scenario'] == self.geol_coll.get_uid_scenario(uid)), 'geological_time'].values[0]
        if val_single == -999999.0:
            val_single = float('nan')
        entity_input_data_df['val'] = val_single
        """nx, ny and nz: TO BE IMPLEMENTED"""
        """gx, gy and gz: TO BE IMPLEMENTED"""
        """Append dataframe for this input entity to the general input dataframe."""
        all_input_data_df = all_input_data_df.append(entity_input_data_df, ignore_index=True)
    toc()
    """Drop columns with no valid value (i.e. all NaNs)."""
    print("-> drop empty columns...")
    tic()
    all_input_data_df.dropna(axis=1, how='all', inplace=True)
    toc()
    print("all_input_data_df:\n", all_input_data_df)
    """Get bounding box of input data to be used as input for the implicit model domain."""
    origin_x = all_input_data_df['X'].min()
    origin_y = all_input_data_df['Y'].min()
    origin_z = all_input_data_df['Z'].min()
    maximum_x = all_input_data_df['X'].max()
    maximum_y = all_input_data_df['Y'].max()
    maximum_z = all_input_data_df['Z'].max()
    edge_x = maximum_x - origin_x
    edge_y = maximum_y - origin_y
    edge_z = maximum_z - origin_z
    """Apply scale factor"""
    input_dict = {'scale_factor_x': ['Scale factor X: ', 0.6], 'scale_factor_y': ['Scale factor Y: ', 0.6], 'scale_factor_z': ['Scale factor Z: ', 0.9], 'method': ['Interpolation method: ', ['PLI', 'FDI', 'surfe']]}
    options_dict = multiple_input_dialog(title='Implicit Modelling - LoopStructural algorithms', input_dict=input_dict)
    if options_dict is None:
        options_dict['scale_factor_x'] = 0.6
        options_dict['scale_factor_y'] = 0.6
        options_dict['scale_factor_z'] = 0.9
        options_dict['method'] = 'PLI'
    delta_x = edge_x * (1.0 - options_dict['scale_factor_x']) / 2
    delta_y = edge_y * (1.0 - options_dict['scale_factor_y']) / 2
    delta_z = edge_z * (1.0 - options_dict['scale_factor_z']) / 2
    origin_x += delta_x
    origin_y += delta_y
    origin_z += delta_z
    maximum_x -= delta_x
    maximum_y -= delta_y
    maximum_z -= delta_z
    edge_x -= delta_x * 2
    edge_y -= delta_y * 2
    edge_z -= delta_z * 2
    """Define origin and maximum extension of modelling domain"""
    origin = [origin_x, origin_y, origin_z]
    maximum = [maximum_x, maximum_y, maximum_z]
    print("origin: ", origin)
    print("maximum: ", maximum)
    default_spacing = np.cbrt(edge_x * edge_y * edge_z / (50 * 50 * 25))  # default dimension in Loop is 50 x 50 x 25
    target_spacing = input_one_value_dialog(title='Implicit Modelling - LoopStructural algorithms', label='Grid target spacing in model units\n (yields a 62500 cells model)', default_value=default_spacing)
    if target_spacing is None or target_spacing <= 0:
        target_spacing = default_spacing
    dimension_x = int(np.around(edge_x / target_spacing))
    if dimension_x == 0:
        dimension_x = 1
    dimension_y = int(np.around(edge_y / target_spacing))
    if dimension_y == 0:
        dimension_y = 1
    dimension_z = int(np.around(edge_z / target_spacing))
    if dimension_z == 0:
        dimension_z = 1
    dimensions = [dimension_x, dimension_y, dimension_z]
    spacing_x = edge_x / dimension_x
    spacing_y = edge_y / dimension_y
    spacing_z = edge_z / dimension_z
    spacing = [spacing_x, spacing_y, spacing_z]
    print("dimensions: ", dimensions)
    print("spacing: ", spacing)
    """Create model as instance of Loop GeologicalModel with limits given by origin and maximum.
    Keep rescale=True (default) for performance and precision.
    THIS SHOULD BE CHANGED IN FUTURE TO BETTER DEAL WITH IRREGULARLY DISTRIBUTED INPUT DATA.
    * ``interpolatortype`` - we can either use a PiecewiseLinearInterpolator ``PLI``, a FiniteDifferenceInterpolator ``FDI`` or a radial basis interpolator ``surfe`` 
    * ``nelements - int`` is the how many elements are used to discretize the resulting solution
    * ``buffer - float`` buffer percentage around the model area
    * ``solver`` - the algorithm to solve the least squares problem e.g. ``lu`` for lower upper decomposition, ``cg`` for conjugate gradient, ``pyamg`` for an algorithmic multigrid solver 
    * ``damp - bool`` - whether to add a small number to the diagonal of the interpolation matrix for discrete interpolators - this can help speed up the solver and makes the solution more stable for some interpolators"""
    print("-> create model...")
    tic()
    model = loop3d.GeologicalModel(origin, maximum)
    toc()
    """Link the input data dataframe to the model."""
    print("-> set_model_data...")
    tic()
    model.set_model_data(all_input_data_df)
    toc()
    """Add a foliation to the model"""
    print("-> create_and_add_foliation...")
    tic()
    model.create_and_add_foliation("strati_0", interpolator_type=options_dict['method'], nelements=(dimensions[0] * dimensions[1] * dimensions[2]))  # interpolator_type can be 'PLI', 'FDI' or 'surfe'
    """In version 1.1+ the implicit function representing a geological feature does not have to be solved to generate the model object.
    The scalar field is solved on demand when the geological features are evaluated. This means that parts of the geological model
    can be modified and only the older (features lower in the feature list) are updated.
    All features in the model can be updated with model.update(verbose=True)."""
    # model.update(verbose=True)  # This will solve the implicit function for all features in the model and provide a progress bar -- causes crash
    """A GeologicalFeature can be extracted from the model either by name..."""
    # my_feature = model[feature_name_value]  # useful?
    """A regular grid inside the model bounding box can be retrieved in the following way:
    - nsteps defines how many points in x, y and z
    - shuffle defines whether the points should be ordered by axis x, y, z (False?) or random (True?).
    - rescale defines whether the returned points should be in model coordinates or real world coordinates."""
    """Set calculation grid resolution. Default resolution is set as to obtain a model close to 10000 cells.
    FOR THE FUTURE: anisotropic resolution?"""
    regular_grid = model.regular_grid(nsteps=dimensions, shuffle=False, rescale=False)  # rescale is True by default
    toc()
    """Evaluate scalar field."""
    print("-> evaluate_feature_value...")
    tic()
    scalar_field = model.evaluate_feature_value("strati_0", regular_grid, scale=False)
    scalar_field = scalar_field.reshape((dimension_x, dimension_y, dimension_z))
    """VTK image data is ordered (z,y,x) in memory, while the Loop Structural output
    Numpy array is ordered as regular_grid, so (x,y,-z). See explanations on VTK here:
    https://discourse.vtk.org/t/numpy-tensor-to-vtkimagedata/5154/3
    https://discourse.vtk.org/t/the-direction-of-vtkimagedata-make-something-wrong/4997"""
    # scalar_field = scalar_field[:, :, ::-1]
    scalar_field = np.flip(scalar_field, 2)
    scalar_field = scalar_field.transpose(2, 1, 0)
    scalar_field = scalar_field.ravel()  # flatten returns a copy
    # """Evaluate scalar field gradient."""
    # print("-> evaluate_feature_gradient...")
    # scalar_field_gradient = model.evaluate_feature_gradient("strati_0", regular_grid, scale=False)
    toc()
    """Create deepcopy of the Mesh3D entity dictionary."""
    print("-> create Voxet...")
    tic()
    voxet_dict = deepcopy(self.mesh3d_coll.mesh3d_entity_dict)
    """Get output Voxet name."""
    model_name = input_text_dialog(title='Implicit Modelling - LoopStructural algorithms', label='Name of the output Voxet', default_text='Loop_model')
    if model_name is None:
        model_name = 'Loop_model'
    voxet_dict['name'] = model_name
    voxet_dict['mesh3d_type'] = 'Voxet'
    voxet_dict['properties_names'] = ["strati_0"]
    voxet_dict['properties_components'] = [1]
    """Create new instance of Voxet() class"""
    voxet_dict['vtk_obj'] = Voxet()
    """Set origin, dimensions and spacing of the output Voxet."""
    voxet_dict['vtk_obj'].origin = [origin_x + spacing_x / 2, origin_y + spacing_y / 2, origin_z + spacing_z / 2]
    voxet_dict['vtk_obj'].dimensions = dimensions
    voxet_dict['vtk_obj'].spacing = spacing
    toc()
    """Pass calculated values of the LoopStructural model to the Voxet, as scalar fields"""
    print("-> populate Voxet...")
    tic()
    voxet_dict['vtk_obj'].set_point_data(data_key="strati_0", attribute_matrix=scalar_field)
    """Create new entity in mesh3d_coll from the populated voxet dictionary"""
    if voxet_dict['vtk_obj'].points_number > 0:
        self.mesh3d_coll.add_entity_from_dict(voxet_dict)
    else:
        print(" -- empty object -- ")
        return
    voxet_dict['vtk_obj'].Modified()
    toc()
    """Extract isosurfaces with vtkFlyingEdges3D. Documentation in:
    https://vtk.org/doc/nightly/html/classvtkFlyingEdges3D.html
    https://python.hotexamples.com/examples/vtk/-/vtkFlyingEdges3D/python-vtkflyingedges3d-function-examples.html"""
    print("-> extract isosurfaces...")
    tic()
    for value in all_input_data_df['val'].dropna().unique():
        value = float(value)
        voxet_dict['vtk_obj'].GetPointData().SetActiveScalars("strati_0")
        print("-> extract iso-surface at value = ", value)
        """Get metadata of first geological feature of this geological_time"""
        geological_type = self.geol_legend_df.loc[self.geol_legend_df['geological_time'] == value, 'geological_type'].values[0]
        geological_feature = self.geol_legend_df.loc[self.geol_legend_df['geological_time'] == value, 'geological_feature'].values[0]
        scenario = self.geol_legend_df.loc[self.geol_legend_df['geological_time'] == value, 'scenario'].values[0]
        """Iso-surface algorithm"""
        iso_surface = vtk.vtkContourFilter()
        # iso_surface = vtk.vtkFlyingEdges3D()
        # iso_surface = vtk.vtkMarchingCubes()
        iso_surface.SetInputData(voxet_dict['vtk_obj'])
        iso_surface.ComputeScalarsOn()
        iso_surface.ComputeGradientsOn()
        iso_surface.SetArrayComponent(0)
        iso_surface.GenerateTrianglesOn()
        iso_surface.UseScalarTreeOn()
        iso_surface.SetValue(0, value)
        iso_surface.Update()
        """Create new TriSurf and populate with iso-surface"""
        surf_dict = deepcopy(self.geol_coll.geological_entity_dict)
        surf_dict['name'] = geological_feature + "_from_" + model_name
        surf_dict['topological_type'] = "TriSurf"
        surf_dict['geological_type'] = geological_type
        surf_dict['geological_feature'] = geological_feature
        surf_dict['scenario'] = scenario
        surf_dict['vtk_obj'] = TriSurf()
        surf_dict['vtk_obj'].ShallowCopy(iso_surface.GetOutput())
        surf_dict['vtk_obj'].Modified()
        if isinstance(surf_dict['vtk_obj'].points, np.ndarray):
            if len(surf_dict['vtk_obj'].points) > 0:
                """Add entity to geological collection only if it is not empty"""
                self.geol_coll.add_entity_from_dict(surf_dict)
                print("-> iso-surface at value = ", value, " has been created")
            else:
                print(" -- empty object -- ")
    toc()
    print("Loop interpolation completed.")


def surface_smoothing(self):
    """Smoothing tools adjust the positions of points to reduce the noise content in the surface."""
    print("Surface Smoothing: reduce the noise of the surface")
    if self.shown_table != "tabGeology":
        print(" -- Only geological objects can be modified -- ")
        return
    """Check if some vtkPolyData is selected"""
    if not self.selected_uids:
        print("No input data selected.")
        return
    else:
        """Deep copy list of selected uids needed otherwise problems can arise if the main geology table is deseselcted while the dataframe is being built"""
        input_uids = deepcopy(self.selected_uids)
    for uid in input_uids:
        if isinstance(self.geol_coll.get_uid_vtk_obj(uid), TriSurf):
            pass
        else:
            print(" -- Error input type: only TriSurf type -- ")
            return
    """Create deepcopy of the geological entity dictionary."""
    surf_dict = deepcopy(self.geol_coll.geological_entity_dict)
    input_dict = {'name': ['TriSurf name: ', self.geol_coll.get_uid_name(input_uids[0]) + '_smooth'], 'geological_type': ['Geological type: ', GeologicalCollection.valid_geological_types], 'geological_feature': ['Geological feature: ', self.geol_coll.get_uid_geological_feature(input_uids[0])], 'scenario': ['Scenario: ', self.geol_coll.get_uid_scenario(input_uids[0])]}
    surf_dict_updt = multiple_input_dialog(title='Surface smoothing', input_dict=input_dict)
    """Check if the output of the widget is empty or not. If the Cancel button was clicked, the tool quits"""
    if surf_dict_updt is None:
        return
    """Getting the values that have been typed by the user through the multiple input widget"""
    for key in surf_dict_updt:
        surf_dict[key] = surf_dict_updt[key]
    surf_dict['topological_type'] = 'TriSurf'
    surf_dict['vtk_obj'] = TriSurf()
    """Create a new instance of the interpolation class"""
    smoother = vtk.vtkSmoothPolyDataFilter()
    smoother.SetInputData(self.geol_coll.get_uid_vtk_obj(input_uids[0]))
    """Ask for the Convergence value (smaller numbers result in more smoothing iterations)."""
    convergence_value = input_one_value_dialog(title='Surface smoothing parameters', label='Convergence Value (small values result in more smoothing)', default_value=1)
    if convergence_value is None:
        convergence_value = 1
    smoother.SetConvergence(convergence_value)
    """Ask for BoundarySmoothing (smoothing of vertices on the boundary of the mesh) and FeatureEdgeSmoothing 
    (smoothing along sharp interior edges)."""
    boundary_smoothing = input_text_dialog(title='Surface smoothing parameters', label='Boundary Smoothing (ON/OFF)', default_text='OFF')
    if boundary_smoothing is None:
        pass
    elif boundary_smoothing == 'ON' or boundary_smoothing == 'on':
        smoother.SetBoundarySmoothing(True)
    elif boundary_smoothing == 'OFF' or boundary_smoothing == 'off':
        smoother.SetBoundarySmoothing(False)
    edge_smooth_switch = input_text_dialog(title='Surface smoothing parameters', label='Feature Edge Smoothing (ON/OFF)', default_text='OFF')
    if edge_smooth_switch is None:
        pass
    elif edge_smooth_switch == 'ON' or edge_smooth_switch == 'on':
        smoother.SetBoundarySmoothing(True)
    elif edge_smooth_switch == 'OFF' or edge_smooth_switch == 'off':
        smoother.SetFeatureEdgeSmoothing(False)
    smoother.Update()
    """ShallowCopy is the way to copy the new interpolated surface into the TriSurf instance created at the beginning"""
    surf_dict['vtk_obj'].ShallowCopy(smoother.GetOutput())
    surf_dict['vtk_obj'].Modified()
    """Add new entity from surf_dict. Function add_entity_from_dict creates a new uid"""
    if surf_dict['vtk_obj'].points_number > 0:
        self.geol_coll.add_entity_from_dict(surf_dict)
    else:
        print(" -- empty object -- ")


def linear_extrusion(self):
    """vtkLinearExtrusionFilter sweeps the generating primitives along a straight line path. This tool is here
    used to create fault surfaces from faults traces."""
    print("Linear extrusion: create surface by projecting target linear object along a straight line path")
    if self.shown_table != "tabGeology":
        print(" -- Only geological objects can be projected -- ")
        return
    """Check if some vtkPolyData is selected"""
    if not self.selected_uids:
        print("No input data selected.")
        return
    else:
        """Deep copy list of selected uids needed otherwise problems can arise if the main geology table is deselected while the dataframe is being built"""
        input_uids = deepcopy(self.selected_uids)
    for uid in input_uids:
        if isinstance(self.geol_coll.get_uid_vtk_obj(uid), PolyLine) or isinstance(self.geol_coll.get_uid_vtk_obj(uid), XsPolyLine):
            pass
        else:
            print(" -- Error input type: only PolyLine and XsPolyLine type -- ")
            return
    """Create deepcopy of the geological entity dictionary."""
    surf_dict = deepcopy(self.geol_coll.geological_entity_dict)
    input_dict = {'name': ['TriSurf name: ', self.geol_coll.get_uid_name(input_uids[0]) + '_extruded'], 'geological_type': ['Geological type: ', GeologicalCollection.valid_geological_types], 'geological_feature': ['Geological feature: ', self.geol_coll.get_uid_geological_feature(input_uids[0])], 'scenario': ['Scenario: ', self.geol_coll.get_uid_scenario(input_uids[0])]}
    surf_dict_updt = multiple_input_dialog(title='Linear Extrusion', input_dict=input_dict)
    """Check if the output of the widget is empty or not. If the Cancel button was clicked, the tool quits"""
    if surf_dict_updt is None:
        return
    """Getting the values that have been typed by the user through the multiple input widget"""
    for key in surf_dict_updt:
        surf_dict[key] = surf_dict_updt[key]
    surf_dict['topological_type'] = 'TriSurf'
    surf_dict['vtk_obj'] = TriSurf()
    """Check if the output of the widget is empty or not. If the Cancel button was clicked, the tool quits"""
    if surf_dict_updt is None:
        return
    """Ask for trend/plunge of the vector to use for the linear extrusion"""
    trend = input_one_value_dialog(title='Linear Extrusion', label='Trend Value', default_value=90.0)
    if trend is None:
        trend = 90.00
    plunge = input_one_value_dialog(title='Linear Extrusion', label='Plunge Value', default_value=30.0)
    if plunge is None:
        plunge = 30.0
    if plunge > 90:
        while plunge > 90:
            plunge -= 90
    elif plunge < 0:
        while plunge < 0:
            plunge += 90
    if plunge == 90:
        plunge = 89
    """Ask for vertical extrusion: how extruded will the surface be?"""
    vertical_extrusion = input_one_value_dialog(title='Linear Extrusion', label='Vertical Extrusion', default_value=-1000)
    if vertical_extrusion is None:
        vertical_extrusion = -1000
    linear_extrusion = vtk.vtkLinearExtrusionFilter()
    linear_extrusion.CappingOn()  # yes or no?
    linear_extrusion.SetExtrusionTypeToVectorExtrusion()
    """Trigonometric formulas to calculate vector"""
    x_vector = np.sin(np.pi * (trend + 180) / 180)
    y_vector = np.cos(np.pi * (trend + 180) / 180)
    z_vector = np.tan(np.pi * (plunge + 180) / 180)
    linear_extrusion.SetVector(x_vector, y_vector, z_vector)  # double,double,double format
    linear_extrusion.SetScaleFactor(vertical_extrusion)  # double format
    linear_extrusion.SetInputData(self.geol_coll.get_uid_vtk_obj(input_uids[0]))
    linear_extrusion.Update()
    """ShallowCopy is the way to copy the new interpolated surface into the TriSurf instance created at the beginning"""
    surf_dict['vtk_obj'].ShallowCopy(linear_extrusion.GetOutput())
    surf_dict['vtk_obj'].Modified()
    """Add new entity from surf_dict. Function add_entity_from_dict creates a new uid"""
    if surf_dict['vtk_obj'].points_number > 0:
        self.geol_coll.add_entity_from_dict(surf_dict)
    else:
        print(" -- empty object -- ")


def decimation_pro_resampling(self):
    """Decimation reduces the number of triangles in a triangle mesh while maintaining a faithful approximation to
    the original mesh."""
    print("Decimation Pro: resample target surface and reduce number of triangles of the mesh")
    if self.shown_table != "tabGeology":
        print(" -- Only geological objects can be resampled -- ")
        return
    """Check if some vtkPolyData is selected"""
    if not self.selected_uids:
        print("No input data selected.")
        return
    else:
        """Deep copy list of selected uids needed otherwise problems can arise if the main geology table is deseselcted while the dataframe is being built"""
        input_uids = deepcopy(self.selected_uids)
    for uid in input_uids:
        if isinstance(self.geol_coll.get_uid_vtk_obj(uid), TriSurf):
            pass
        else:
            print(" -- Error input type: only TriSurf type -- ")
            return
    """Create deepcopy of the geological entity dictionary."""
    surf_dict = deepcopy(self.geol_coll.geological_entity_dict)
    surf_dict['name'] = self.geol_coll.get_uid_name(input_uids[0]) + '_decimated'
    surf_dict['geological_feature'] = self.geol_coll.get_uid_geological_feature(input_uids[0])
    surf_dict['scenario'] = self.geol_coll.get_uid_scenario(input_uids[0])
    surf_dict['geological_type'] = self.geol_coll.get_uid_geological_type(input_uids[0])
    surf_dict['topological_type'] = 'TriSurf'
    surf_dict['vtk_obj'] = TriSurf()
    """Create a new instance of the decimation class"""
    deci = vtk.vtkDecimatePro()
    deci.SetInputData(self.geol_coll.get_uid_vtk_obj(input_uids[0]))
    """Target Reduction value. Specify the desired reduction in the total number of polygons (e.g., when
    Target Reduction is set to 0.9, this filter will try to reduce the data set to 10% of its original size)."""
    tar_reduct = input_one_value_dialog(title='Decimation Resampling parameters', label='Target Reduction Value', default_value=0.5)
    if tar_reduct is None:
        tar_reduct = 0.5
    deci.SetTargetReduction(tar_reduct)
    """Preserve Topology switch. Turn on/off whether to preserve the topology of the original mesh."""
    preserve_topology = input_text_dialog(title='Decimation Resampling parameters', label='Preserve Topology (ON/OFF)', default_text='ON')
    if preserve_topology is None:
        pass
    elif preserve_topology == 'ON' or preserve_topology == 'on':
        deci.PreserveTopologyOn()
    elif preserve_topology == 'OFF' or preserve_topology == 'off':
        deci.PreserveTopologyOff()
    """Boundary Vertex Deletion switch. Turn on/off the deletion of vertices on the boundary of a mesh."""
    bound_vert_del = input_text_dialog(title='Decimation Resampling parameters', label='Boundary Vertex Deletion (ON/OFF)', default_text='OFF')
    if bound_vert_del is None:
        pass
    elif bound_vert_del == 'ON' or bound_vert_del == 'on':
        deci.BoundaryVertexDeletionOn()
    elif bound_vert_del == 'OFF' or bound_vert_del == 'off':
        deci.BoundaryVertexDeletionOff()
    """Splitting switch. Turn on/off the splitting of the mesh at corners, along edges, at non-manifold points, or 
    anywhere else a split is required."""
    splitting = input_text_dialog(title='Decimation Resampling parameters', label='Splitting (ON to preserve original topology/OFF)', default_text='ON')
    if splitting is None:
        pass
    elif splitting == 'ON' or splitting == 'on':
        deci.SplittingOn()
    elif splitting == 'OFF' or splitting == 'off':
        deci.SplittingOff()
    deci.Update()
    """ShallowCopy is the way to copy the new interpolated surface into the TriSurf instance created at the beginning"""
    surf_dict['vtk_obj'].ShallowCopy(deci.GetOutput())
    surf_dict['vtk_obj'].Modified()
    """Add new entity from surf_dict. Function add_entity_from_dict creates a new uid"""
    if surf_dict['vtk_obj'].points_number > 0:
        self.geol_coll.add_entity_from_dict(surf_dict)
    else:
        print(" -- empty object -- ")


def decimation_quadric_resampling(self):
    """Decimation reduces the number of triangles in a triangle mesh while maintaining a faithful approximation to
    the original mesh."""
    print("Decimation Quadric: resample target surface and reduce number of triangles of the mesh")
    if self.shown_table != "tabGeology":
        print(" -- Only geological objects can be resampled -- ")
        return
    """Check if some vtkPolyData is selected"""
    if not self.selected_uids:
        print("No input data selected.")
        return
    else:
        """Deep copy list of selected uids needed otherwise problems can arise if the main geology table is deseselcted while the dataframe is being built"""
        input_uids = deepcopy(self.selected_uids)
    for uid in input_uids:
        if isinstance(self.geol_coll.get_uid_vtk_obj(uid), TriSurf):
            pass
        else:
            print(" -- Error input type: only TriSurf type -- ")
            return
    """Create deepcopy of the geological entity dictionary."""
    surf_dict = deepcopy(self.geol_coll.geological_entity_dict)
    surf_dict['name'] = self.geol_coll.get_uid_name(input_uids[0]) + '_decimated'
    surf_dict['geological_feature'] = self.geol_coll.get_uid_geological_feature(input_uids[0])
    surf_dict['scenario'] = self.geol_coll.get_uid_scenario(input_uids[0])
    surf_dict['geological_type'] = self.geol_coll.get_uid_geological_type(input_uids[0])
    surf_dict['topological_type'] = 'TriSurf'
    surf_dict['vtk_obj'] = TriSurf()
    """Create a new instance of the decimation class"""
    deci = vtk.vtkQuadricDecimation()
    deci.SetInputData(self.geol_coll.get_uid_vtk_obj(input_uids[0]))
    """Target Reduction value. Specify the desired reduction in the total number of polygons (e.g., when
    Target Reduction is set to 0.9, this filter will try to reduce the data set to 10% of its original size)."""
    tar_reduct = input_one_value_dialog(title='Decimation Resampling parameters', label='Target Reduction Value', default_value=0.5)
    if tar_reduct is None:
        tar_reduct = '0.5'
    deci.SetTargetReduction(tar_reduct)
    deci.Update()
    """ShallowCopy is the way to copy the new interpolated surface into the TriSurf instance created at the beginning"""
    surf_dict['vtk_obj'].ShallowCopy(deci.GetOutput())
    surf_dict['vtk_obj'].Modified()
    """Add new entity from surf_dict. Function add_entity_from_dict creates a new uid"""
    if surf_dict['vtk_obj'].points_number > 0:
        self.geol_coll.add_entity_from_dict(surf_dict)
    else:
        print(" -- empty object -- ")


def subdivision_resampling(self):
    """vtkButterflySubdivisionFilter subdivides a triangular, polygonal surface; four new triangles are created
     for each triangle of the polygonal surface."""
    print("Subdivision resampling: resample target surface and increase number of triangles of the mesh")
    if self.shown_table != "tabGeology":
        print(" -- Only geological objects can be resampled -- ")
        return
    """Check if some vtkPolyData is selected"""
    if not self.selected_uids:
        print("No input data selected.")
        return
    else:
        """Deep copy list of selected uids needed otherwise problems can arise if the main geology table is deseselcted while the dataframe is being built"""
        input_uids = deepcopy(self.selected_uids)
    for uid in input_uids:
        if isinstance(self.geol_coll.get_uid_vtk_obj(uid), TriSurf):
            pass
        else:
            print(" -- Error input type: only TriSurf type -- ")
            return
    """Create deepcopy of the geological entity dictionary."""
    surf_dict = deepcopy(self.geol_coll.geological_entity_dict)
    surf_dict['name'] = self.geol_coll.get_uid_name(input_uids[0]) + '_subdivided'
    surf_dict['geological_feature'] = self.geol_coll.get_uid_geological_feature(input_uids[0])
    surf_dict['scenario'] = self.geol_coll.get_uid_scenario(input_uids[0])
    surf_dict['geological_type'] = self.geol_coll.get_uid_geological_type(input_uids[0])
    surf_dict['topological_type'] = 'TriSurf'
    surf_dict['vtk_obj'] = TriSurf()
    """Create a new instance of the decimation class"""
    buttefly_subdiv = vtk.vtkButterflySubdivisionFilter()
    buttefly_subdiv.SetInputData(self.geol_coll.get_uid_vtk_obj(input_uids[0]))
    buttefly_subdiv.Update()
    """ShallowCopy is the way to copy the new interpolated surface into the TriSurf instance created at the beginning"""
    surf_dict['vtk_obj'].ShallowCopy(buttefly_subdiv.GetOutput())
    surf_dict['vtk_obj'].Modified()
    """Add new entity from surf_dict. Function add_entity_from_dict creates a new uid"""
    if surf_dict['vtk_obj'].points_number > 0:
        self.geol_coll.add_entity_from_dict(surf_dict)
    else:
        print(" -- empty object -- ")


def intersection_xs(self):
    """vtkCutter is a filter to cut through data using any subclass of vtkImplicitFunction.
    HOW TO USE: select one or more Geological objects, DOMs or 3D Meshes (Source data), then function asks for XSection
    (input data) for the filter."""
    print("Intersection with XSection: intersect Geological entities, 3D Meshes and DEM & DOMs")
    """Check if some vtkPolyData is selected"""
    if not self.selected_uids:
        print("No input data selected.")
        return
    else:
        """Deep copy list of selected uids needed otherwise problems can arise if the main geology table is deseselcted while the dataframe is being built"""
        input_uids = deepcopy(self.selected_uids)
    """Input selection dialog"""
    xsect_names = input_checkbox_dialog(title="Intersection XSection", label="Choose XSections to intersect", choice_list=self.xsect_coll.get_names())
    if xsect_names is None:
        return
    xsect_uids = []
    for name in xsect_names:
        xsect_uids.append(self.xsect_coll.df.loc[self.xsect_coll.df['name'] == name, 'uid'].values[0])
    for xsect_uid in xsect_uids:
        if self.shown_table == "tabGeology":
            for uid in input_uids:
                if self.geol_coll.get_uid_topological_type(uid) in ["PolyLine", "XsPolyLine"]:
                    """Intersection for PolyLine and XsPolyLine."""
                    if self.geol_coll.get_uid_x_section(uid) != xsect_uid:
                        """cutter"""
                        cutter = vtk.vtkCutter()
                        cutter.SetCutFunction(self.xsect_coll.get_uid_vtk_plane(xsect_uid))
                        cutter.SetInputData(self.geol_coll.get_uid_vtk_obj(uid))
                        cutter.Update()
                        if cutter.GetOutput().GetNumberOfPoints() > 0:
                            """Create new dict for the new XsVertexSet"""
                            obj_dict = deepcopy(self.geol_coll.geological_entity_dict)
                            obj_dict['x_section'] = xsect_uid
                            obj_dict['topological_type'] = 'XsVertexSet'
                            obj_dict['vtk_obj'] = XsVertexSet(x_section_uid=xsect_uid, parent=self)
                            obj_dict['name'] = self.geol_coll.get_uid_name(uid) + '_intersect'
                            obj_dict['geological_type'] = self.geol_coll.get_uid_geological_type(uid)
                            obj_dict['geological_feature'] = self.geol_coll.get_uid_geological_feature(uid)
                            obj_dict['scenario'] = self.geol_coll.get_uid_scenario(uid)
                            obj_dict['properties_names'] = self.geol_coll.get_uid_properties_names(uid)
                            obj_dict['properties_components'] = self.geol_coll.get_uid_properties_components(uid)
                            obj_dict['vtk_obj'].DeepCopy(cutter.GetOutput())
                            for data_key in obj_dict['vtk_obj'].point_data_keys:
                                if not data_key in obj_dict['properties_names']:
                                    obj_dict['vtk_obj'].remove_point_data(data_key)
                            self.geol_coll.add_entity_from_dict(obj_dict)
                        else:
                            print(" -- empty object from cutter -- ")
                    else:
                        print(" -- no intersection of XsPolyLine with its own XSection -- ")
                elif self.geol_coll.get_uid_topological_type(uid) == "TriSurf":
                    """cutter"""
                    cutter = vtk.vtkCutter()
                    cutter.SetCutFunction(self.xsect_coll.get_uid_vtk_plane(xsect_uid))
                    cutter.SetInputData(self.geol_coll.get_uid_vtk_obj(uid))
                    cutter.Update()
                    """cutter_clean"""
                    cutter_clean = vtk.vtkCleanPolyData()
                    cutter_clean.ConvertLinesToPointsOff()
                    cutter_clean.ConvertPolysToLinesOff()
                    cutter_clean.ConvertStripsToPolysOff()
                    cutter_clean.SetTolerance(0.0)
                    cutter_clean.SetInputConnection(cutter.GetOutputPort())
                    cutter_clean.Update()
                    """cutter_clean_strips"""
                    cutter_clean_strips = vtk.vtkStripper()
                    cutter_clean_strips.JoinContiguousSegmentsOn()
                    cutter_clean_strips.SetInputConnection(cutter_clean.GetOutputPort())
                    cutter_clean_strips.Update()
                    """cutter_clean_strips_clean, needed to sort the nodes and cells in the right order"""
                    cutter_clean_strips_clean = vtk.vtkCleanPolyData()
                    cutter_clean_strips_clean.ConvertLinesToPointsOff()
                    cutter_clean_strips_clean.ConvertPolysToLinesOff()
                    cutter_clean_strips_clean.ConvertStripsToPolysOff()
                    cutter_clean_strips_clean.SetTolerance(0.0)
                    cutter_clean_strips_clean.SetInputConnection(cutter_clean_strips.GetOutputPort())
                    cutter_clean_strips_clean.Update()
                    """cutter_clean_strips_clean_triangle, used to convert polyline cells back to lines"""
                    cutter_clean_strips_clean_triangle = vtk.vtkTriangleFilter()
                    cutter_clean_strips_clean_triangle.SetInputConnection(cutter_clean_strips_clean.GetOutputPort())
                    cutter_clean_strips_clean_triangle.Update()
                    """connectivity, split multiple part polylines, first using .SetExtractionModeToAllRegions()
                    to get the number of parts/regions, then switching to .SetExtractionModeToSpecifiedRegions()
                    to extract the parts/regions sequentially"""
                    if cutter_clean_strips_clean_triangle.GetOutput().GetNumberOfPoints() > 0:
                        connectivity = vtk.vtkPolyDataConnectivityFilter()
                        connectivity.SetInputConnection(cutter_clean_strips_clean_triangle.GetOutputPort())
                        connectivity.SetExtractionModeToAllRegions()
                        connectivity.Update()
                        n_regions = connectivity.GetNumberOfExtractedRegions()
                        connectivity.SetExtractionModeToSpecifiedRegions()
                        connectivity.Update()
                        for region in range(n_regions):
                            connectivity.InitializeSpecifiedRegionList()
                            connectivity.AddSpecifiedRegion(region)
                            connectivity.Update()
                            """connectivity_clean, used to remove orphan points left behind by connectivity"""
                            connectivity_clean = vtk.vtkCleanPolyData()
                            connectivity_clean.SetInputConnection(connectivity.GetOutputPort())
                            connectivity_clean.Update()
                            """Check if polyline really exists then create entity"""
                            if connectivity_clean.GetOutput().GetNumberOfPoints() > 0:
                                """Create new dict for the new XsPolyLine"""
                                obj_dict = deepcopy(self.geol_coll.geological_entity_dict)
                                obj_dict['x_section'] = xsect_uid
                                obj_dict['topological_type'] = 'XsPolyLine'
                                obj_dict['vtk_obj'] = XsPolyLine(x_section_uid=xsect_uid, parent=self)
                                obj_dict['name'] = self.geol_coll.get_uid_name(uid) + '_intersect'
                                obj_dict['geological_type'] = self.geol_coll.get_uid_geological_type(uid)
                                obj_dict['geological_feature'] = self.geol_coll.get_uid_geological_feature(uid)
                                obj_dict['scenario'] = self.geol_coll.get_uid_scenario(uid)
                                obj_dict['properties_names'] = self.geol_coll.get_uid_properties_names(uid)
                                obj_dict['properties_components'] = self.geol_coll.get_uid_properties_components(uid)
                                obj_dict['vtk_obj'].DeepCopy(connectivity_clean.GetOutput())
                                for data_key in obj_dict['vtk_obj'].point_data_keys:
                                    if not data_key in obj_dict['properties_names']:
                                        obj_dict['vtk_obj'].remove_point_data(data_key)
                                self.geol_coll.add_entity_from_dict(obj_dict)
                            else:
                                print(" -- empty object from connectivity_clean-- ")
                    else:
                        print(" -- empty object from cutter_clean_strips_clean_triangle -- ")
        elif self.shown_table == "tabMeshes3D":
            for uid in input_uids:
                if self.mesh3d_coll.get_uid_mesh3d_type(uid) == "Voxet":
                    """Get cutter - a polydata slice cut across the voxet."""
                    cutter = vtk.vtkCutter()
                    cutter.SetCutFunction(self.xsect_coll.get_uid_vtk_plane(xsect_uid))
                    cutter.SetInputData(self.mesh3d_coll.get_uid_vtk_obj(uid))
                    cutter.Update()
                    if cutter.GetOutput().GetNumberOfPoints() > 0:
                        cutter.GetOutput().GetPointData().SetActiveScalars(self.mesh3d_coll.get_uid_properties_names(uid)[0])
                        cutter_bounds = np.float64(cutter.GetOutput().GetBounds())
                        dim_Z = self.mesh3d_coll.get_uid_vtk_obj(uid).W_n
                        spacing_Z = self.mesh3d_coll.get_uid_vtk_obj(uid).W_step
                        if spacing_Z < 0:
                            spacing_Z *= -1
                        cutter_n_points = cutter.GetOutput().GetNumberOfPoints()
                        dim_W = int(cutter_n_points / dim_Z)
                        spacing_W = np.sqrt((cutter_bounds[1] - cutter_bounds[0])**2 + (cutter_bounds[3] - cutter_bounds[2])**2) / (dim_W - 1)
                        azimuth = self.xsect_coll.get_uid_azimuth(xsect_uid)
                        """The direction matrix is a 3x3 transformation matrix supporting scaling and rotation.
                        (double  	e00,
                        double  	e01,
                        double  	e02,
                        double  	e10,
                        double  	e11,
                        double  	e12,
                        double  	e20,
                        double  	e21,
                        double  	e22)"""
                        if azimuth <= 90:
                            origin = [cutter_bounds[0], cutter_bounds[2], cutter_bounds[4]]
                            direction_matrix = [np.sin(azimuth * np.pi / 180), 0, -(np.cos(azimuth * np.pi / 180)), np.cos(azimuth * np.pi / 180), 0, np.sin(azimuth * np.pi / 180), 0, 1, 0]
                        elif azimuth <= 180:
                            origin = [cutter_bounds[1], cutter_bounds[2], cutter_bounds[4]]
                            direction_matrix = [-(np.sin(azimuth * np.pi / 180)), 0, -(np.cos(azimuth * np.pi / 180)), -(np.cos(azimuth * np.pi / 180)), 0, np.sin(azimuth * np.pi / 180), 0, 1, 0]
                        elif azimuth <= 270:
                            origin = [cutter_bounds[0], cutter_bounds[2], cutter_bounds[4]]
                            direction_matrix = [-(np.sin(azimuth * np.pi / 180)), 0, -(np.cos(azimuth * np.pi / 180)), -(np.cos(azimuth * np.pi / 180)), 0, np.sin(azimuth * np.pi / 180), 0, 1, 0]
                        else:
                            origin = [cutter_bounds[1], cutter_bounds[2], cutter_bounds[4]]
                            direction_matrix = [np.sin(azimuth * np.pi / 180), 0, -(np.cos(azimuth * np.pi / 180)), np.cos(azimuth * np.pi / 180), 0, np.sin(azimuth * np.pi / 180), 0, 1, 0]
                        """Create vtkImageData with the geometry to fit data from cutter"""
                        probe_image = vtk.vtkImageData()
                        probe_image.SetOrigin(origin)
                        probe_image.SetSpacing([spacing_W, spacing_Z, 0.0])
                        probe_image.SetDimensions([dim_W, dim_Z, 1])
                        probe_image.SetDirectionMatrix(direction_matrix)
                        probe_n_points = probe_image.GetNumberOfPoints()
                        """scipy.interpolate.griddata: get point coordinates from cutter.GetOutput() + strati_0 values +
                        calculate point coordinates for probe_image, the final regular grid. Then, execute griddata"""
                        XYZ_cutter = numpy_support.vtk_to_numpy(cutter.GetOutput().GetPoints().GetData())
                        values = numpy_support.vtk_to_numpy(cutter.GetOutput().GetPointData().GetArray(0)).reshape((dim_Z*dim_W, ))
                        XYZ_probe = np.zeros((probe_n_points, 3))
                        for point in range(probe_n_points):
                            XYZ_probe[point, :] = probe_image.GetPoint(point)
                        regular_values = griddata(points=XYZ_cutter, values=values, xi=XYZ_probe, method='nearest')
                        # regular_values = griddata(points=XYZ_cutter, values=values, xi=XYZ_probe, method='linear')
                        # regular_values = griddata(points=XYZ_cutter, values=values, xi=XYZ_probe, method='linear', rescale=True)
                        """Pass values from griddata interpolation to probe_image"""
                        probe_image.GetPointData().AddArray(numpy_support.numpy_to_vtk(regular_values))
                        probe_image.GetPointData().GetArray(0).SetName(self.mesh3d_coll.get_uid_properties_names(uid)[0])
                        """Create new dict for the new XsVoxet"""
                        obj_dict = deepcopy(self.mesh3d_coll.mesh3d_entity_dict)
                        obj_dict['name'] = self.mesh3d_coll.get_uid_name(uid) + '_intersect_' + self.xsect_coll.get_uid_name(xsect_uid)
                        obj_dict['mesh3d_type'] = 'XsVoxet'
                        obj_dict['properties_names'] = self.mesh3d_coll.get_uid_properties_names(uid)
                        obj_dict['properties_components'] = self.mesh3d_coll.get_uid_properties_components(uid)
                        obj_dict['x_section'] = xsect_uid
                        obj_dict['vtk_obj'] = XsVoxet(x_section_uid=xsect_uid, parent=self)
                        obj_dict['vtk_obj'].ShallowCopy(probe_image)
                        if obj_dict['vtk_obj'].points_number > 0:
                            self.mesh3d_coll.add_entity_from_dict(obj_dict)
                        else:
                            print(" -- empty object -- ")
                    else:
                        print(" -- empty object -- ")
        elif self.shown_table == "tabDOMs":
            for uid in input_uids:
                if self.dom_coll.get_uid_dom_type(uid) == "DEM":
                    """Create cutter"""
                    cutter = vtk.vtkCutter()
                    cutter.SetCutFunction(self.xsect_coll.get_uid_vtk_plane(xsect_uid))
                    cutter.SetInputData(self.dom_coll.get_uid_vtk_obj(uid))
                    cutter.Update()
                    """Create new dict for the new DomXs"""
                    obj_dict = deepcopy(self.dom_coll.dom_entity_dict)
                    obj_dict['name'] = self.dom_coll.get_uid_name(uid) + '_trace'
                    obj_dict['dom_type'] = 'DomXs'
                    obj_dict['properties_names'] = self.dom_coll.get_uid_properties_names(uid)
                    obj_dict['properties_components'] = self.dom_coll.get_uid_properties_components(uid)
                    obj_dict['x_section'] = xsect_uid
                    obj_dict['vtk_obj'] = XsPolyLine(x_section_uid=xsect_uid, parent=self)
                    obj_dict['vtk_obj'].DeepCopy(cutter.GetOutput())
                    print("obj_dict['vtk_obj']:\n", obj_dict['vtk_obj'])
                    if obj_dict['vtk_obj'].points_number > 0:
                        for data_key in obj_dict['vtk_obj'].point_data_keys:
                            if not data_key in obj_dict['properties_names']:
                                obj_dict['vtk_obj'].remove_point_data(data_key)
                        self.dom_coll.add_entity_from_dict(obj_dict)
                    else:
                        print(" -- empty object -- ")
        else:
            print(" -- Only Geological objects, 3D Meshes and DEM & DOMs can be intersected with XSection -- ")
            return


def project_2_dem(self):
    """vtkProjectedTerrainPath projects an input polyline onto a terrain image.
    HOW TO USE: at the moment, as vtkProjectedTerrainPath takes vtkImageData as input, we need to import
    DEM file also as OrthoImage (--> as vtkImageData) and to use this entity as source data for the
    projection"""
    print("Vertical Projection: project target lines onto a terrain image")
    if self.shown_table != "tabGeology":
        print(" -- Only geological objects can be interpolated -- ")
        return
    """Check if some vtkPolyData is selected"""
    if not self.selected_uids:
        print("No input data selected.")
        return
    else:
        input_uids = deepcopy(self.selected_uids)
    for uid in input_uids:
        if isinstance(self.geol_coll.get_uid_vtk_obj(uid), PolyLine):
            pass
        else:
            print(" -- Error input type: only PolyLine type -- ")
            return
    """Ask if the tool replaces the input entities, or if they shall be preserved"""
    replace_on_off = input_text_dialog(title='Project to Surface', label='Replace Original Entities? (YES/NO)', default_text='YES')
    if replace_on_off is None:
        return
    if replace_on_off != 'YES' and replace_on_off != 'yes' and replace_on_off != 'y' and replace_on_off != 'Y' and replace_on_off != 'NO' and replace_on_off != 'no' and replace_on_off != 'n' and replace_on_off != 'N':
        return
#     """Ask for the DOM (/DEM), source of the projection"""
#     dom_list_uids = self.dom_coll.get_uids()
#     dom_list_names = []
#     for uid in dom_list_uids:
#         dom_list_names.append(self.dom_coll.get_uid_name(uid))
#     dom_name = input_combo_dialog(title='Project to Surface', label='Input surface for projection', choice_list=dom_list_names)
#     if dom_name is None:
#         return
#     dom_uid = self.dom_coll.df.loc[self.dom_coll.df['name'] == dom_name, 'uid'].values[0]
#     print("dom_uid ", dom_uid)
#     """Convert DEM (vtkStructuredGrid) in vtkImageData to perform the projection with vtkProjectedTerrainPath"""
#     dem_to_image = vtk.vtkDEMReader()
#     dem_to_image.SetInputData(self.dom_coll.get_uid_vtk_obj(dom_uid))
#     dem_to_image.Update()
#     print("dem_to_image ", dem_to_image)
#     print("dem_to_image.GetOutput() ", dem_to_image.GetOutput())
    """Ask for the Orthoimage, source of the projection"""
    image_list_uids = self.image_coll.get_uids()
    image_list_names = []
    for uid in image_list_uids:
        image_list_names.append(self.image_coll.get_uid_name(uid))
    img_name = input_combo_dialog(title='Project to Surface', label='Input surface for projection', choice_list=image_list_names)
    if img_name is None:
        return
    img_uid = self.image_coll.df.loc[self.image_coll.df['name'] == img_name, 'uid'].values[0]
    """----- some check is needed here. Check if the chosen image is a 2D map with elevation values -----"""
    for uid in input_uids:
        """Create a new instance of vtkProjectedTerrainPath"""
        projection = vtk.vtkProjectedTerrainPath()
        projection.SetInputData(self.geol_coll.get_uid_vtk_obj(uid))
        projection.SetProjectionModeToSimple()  # projects the original polyline points
        projection.SetSourceData(self.image_coll.get_uid_vtk_obj(img_uid))  # this must be vtkImageData
        projection.SetHeightOffset(0)
        projection.Update()
        """Create deepcopy of the geological entity dictionary."""
        obj_dict = deepcopy(self.geol_coll.geological_entity_dict)
        if replace_on_off == 'YES' or replace_on_off == 'yes' or replace_on_off == 'y':
            obj_dict['uid'] = uid
        elif replace_on_off == 'NO' or replace_on_off == 'no' or replace_on_off == 'n':
            obj_dict['uid'] = None
        obj_dict['name'] = self.geol_coll.get_uid_name(uid) + '_projected'
        obj_dict['geological_feature'] = self.geol_coll.get_uid_geological_feature(uid)
        obj_dict['scenario'] = self.geol_coll.get_uid_scenario(uid)
        obj_dict['geological_type'] = self.geol_coll.get_uid_geological_type(uid)
        obj_dict['topological_type'] = self.geol_coll.get_uid_topological_type(uid)
        obj_dict['vtk_obj'] = PolyLine()
        """ShallowCopy is the way to copy the new entity into the instance created at the beginning"""
        obj_dict['vtk_obj'].ShallowCopy(projection.GetOutput())
        obj_dict['vtk_obj'].Modified()
        if obj_dict['vtk_obj'] is None:
            return
        if replace_on_off == 'NO' or replace_on_off == 'no' or replace_on_off == 'n':
            if obj_dict['vtk_obj'].points_number > 0:
                self.geol_coll.add_entity_from_dict(obj_dict)
            else:
                print(" -- empty object -- ")
        else:
            self.geol_coll.replace_vtk(uid=uid, vtk_object=obj_dict['vtk_obj'])
            self.geol_coll.set_uid_name(uid=uid, name=obj_dict['name'])
            self.geology_geom_modified_signal.emit([uid])  # emit uid as list to force redraw
        self.geology_metadata_modified_signal.emit([uid])


def project_2_xs(self):
    """Projection of a copy of point and polyline geological entities to a planar cross section, along an axis specified with plunge/trend."""
    print("Projection to cross section")
    """Get input objects - points and polylines at the moment."""
    if self.shown_table != "tabGeology":
        print(" -- Only geological objects can be projected -- ")
        return
    """Check if some vtkPolyData is selected"""
    if not self.selected_uids:
        print("No input data selected.")
        return
    else:
        """Deep copy list of selected uids needed otherwise problems can arise if the main geology table is deseselcted while the dataframe is being built"""
        input_uids = deepcopy(self.selected_uids)
    """Select points and polylines only."""
    input_uids_clean = deepcopy(input_uids)
    for uid in input_uids:
        if self.geol_coll.get_uid_topological_type(uid) not in ["VertexSet", "PolyLine", "XsVertexSet", "XsPolyLine"]:
            input_uids_clean.remove(uid)
    input_uids = deepcopy(input_uids_clean)
    del input_uids_clean
    if not input_uids:
        print("No valid input data selected.")
        return
    """Define projection parameters (float64 needed for "t" afterwards)"""
    xs_names = self.xsect_coll.get_names()
    input_dict = {'xs_name': ['XSection: ', xs_names], 'proj_plunge': ['Projection axis plunge: ', 0.0], 'proj_trend': ['Projection axis trend: ', 0.0]}
    options_dict = multiple_input_dialog(title='Projection to XSection', input_dict=input_dict)
    if options_dict is None:
        return
    xs_name = options_dict['xs_name']
    xs_uid = self.xsect_coll.df.loc[self.xsect_coll.df['name'] == xs_name, 'uid'].values[0]
    proj_plunge = np.float64(options_dict['proj_plunge'])
    proj_trend = np.float64(options_dict['proj_trend'])
    """Constrain to 0-180."""
    if proj_trend > 180.0:
        proj_trend -= 180.0
        proj_plunge = -proj_plunge
    """Check for projection trend parallel to cross section."""
    if abs(self.xsect_coll.get_uid_azimuth(xs_uid) - proj_trend) < 10.0 or abs(self.xsect_coll.get_uid_azimuth(xs_uid) - 180.0 - proj_trend) < 10.0:
        print("Plunge too close to being parallel to XSection (angle < 10°)")
        return
    """Get cross section start and end points (float64 needed for "t" afterwards)."""
    xa = np.float64(self.xsect_coll.get_uid_base_x(xs_uid))
    ya = np.float64(self.xsect_coll.get_uid_base_y(xs_uid))
    xb = np.float64(self.xsect_coll.get_uid_end_x(xs_uid))
    yb = np.float64(self.xsect_coll.get_uid_end_y(xs_uid))
    """Calculate projection direction cosines (float64 needed for "t" afterwards)."""
    alpha = np.float64(np.sin(proj_trend * np.pi / 180.0) * np.cos(proj_plunge * np.pi / 180.0))
    beta = np.float64(np.cos(proj_trend * np.pi / 180.0) * np.cos(proj_plunge * np.pi / 180.0))
    gamma = np.float64(-np.sin(proj_plunge * np.pi / 180.0))
    """Project each entity."""
    for uid in input_uids:
        """Clone entity."""
        entity_dict = deepcopy(self.geol_coll.geological_entity_dict)
        entity_dict['name'] = self.geol_coll.get_uid_name(uid) + "_prj_" + xs_name
        entity_dict['geological_type'] = self.geol_coll.get_uid_geological_type(uid)
        entity_dict['geological_feature'] = self.geol_coll.get_uid_geological_feature(uid)
        entity_dict['scenario'] = self.geol_coll.get_uid_scenario(uid)
        entity_dict['properties_names'] = self.geol_coll.get_uid_properties_names(uid)
        entity_dict['properties_components'] = self.geol_coll.get_uid_properties_components(uid)
        entity_dict['x_section'] = xs_uid
        if self.geol_coll.get_uid_topological_type(uid) == "VertexSet":
            entity_dict['topological_type'] = "XsVertexSet"
            out_vtk = XsVertexSet(x_section_uid=xs_uid, parent=self)
            out_vtk.DeepCopy(self.geol_coll.get_uid_vtk_obj(uid))
        elif self.geol_coll.get_uid_topological_type(uid) == "PolyLine":
            entity_dict['topological_type'] = "XsPolyLine"
            out_vtk = XsPolyLine(x_section_uid=xs_uid, parent=self)
            out_vtk.DeepCopy(self.geol_coll.get_uid_vtk_obj(uid))
        else:
            entity_dict['topological_type'] = self.geol_coll.get_uid_topological_type(uid)
            out_vtk = self.geol_coll.get_uid_vtk_obj(uid).deep_copy()
        """Perform projection on clone (the last two steps could be merged).
         np.float64 is needed to calculate "t" with a good precision
         when X and Y are in UTM coordinates with very large values,
         then the result is cast to float32 that is the VTK standard."""
        xo = out_vtk.points_X.astype(np.float64)
        yo = out_vtk.points_Y.astype(np.float64)
        zo = out_vtk.points_Z.astype(np.float64)
        t = (-xo*(yb-ya) - yo*(xa-xb) - ya*xb + yb*xa) / (alpha*(yb-ya) + beta*(xa-xb))
        out_vtk.points_X[:] = (xo + alpha * t).astype(np.float32)
        out_vtk.points_Y[:] = (yo + beta * t).astype(np.float32)
        out_vtk.points_Z[:] = (zo + gamma * t).astype(np.float32)
        """Output, checking for multipart for polylines."""
        if entity_dict['topological_type'] == "XsVertexSet":
            entity_dict['vtk_obj'] = out_vtk
            out_uid = self.geol_coll.add_entity_from_dict(entity_dict=entity_dict)
        elif entity_dict['topological_type'] == "XsPolyLine":
            connectivity = vtk.vtkPolyDataConnectivityFilter()
            connectivity.SetInputData(out_vtk)
            connectivity.SetExtractionModeToAllRegions()
            connectivity.Update()
            n_regions = connectivity.GetNumberOfExtractedRegions()
            connectivity.SetExtractionModeToSpecifiedRegions()
            connectivity.Update()
            for region in range(n_regions):
                connectivity.InitializeSpecifiedRegionList()
                connectivity.AddSpecifiedRegion(region)
                connectivity.Update()
                """connectivity_clean, used to remove orphan points left behind by connectivity"""
                connectivity_clean = vtk.vtkCleanPolyData()
                connectivity_clean.SetInputConnection(connectivity.GetOutputPort())
                connectivity_clean.Update()
                """Check if polyline really exists then create entity"""
                if connectivity_clean.GetOutput().GetNumberOfPoints() > 0:
                    entity_dict['vtk_obj'] = XsPolyLine(x_section_uid=xs_uid, parent=self)
                    entity_dict['vtk_obj'].DeepCopy(connectivity_clean.GetOutput())
                    for data_key in entity_dict['vtk_obj'].point_data_keys:
                        if not data_key in entity_dict['properties_names']:
                            entity_dict['vtk_obj'].remove_point_data(data_key)
                    out_uid = self.geol_coll.add_entity_from_dict(entity_dict=entity_dict)
                else:
                    print(" -- empty object -- ")
