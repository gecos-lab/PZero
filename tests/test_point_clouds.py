"""
test_point_clouds.py
PZero© Andrea Bistacchi

How to run
----------
    pytest test_point_clouds.py -v

OR

    pytest test_point_clouds.py -v --dat-file=/path/to/PC (to try with real PC)

Or together with all other tests:

    pytest -v
    
"""

import pytest
import numpy as np
from unittest.mock import MagicMock
from unittest.mock import patch
from pzero.entities_factory import PCDom
from pzero.point_clouds import normals2dd, cut_pc, decimate_pc, segment_pc, facets_pc, calibration_pc, auto_pick, thresh_filt


# =============================================================================
# HELPERS
# =============================================================================

def _make_real_pc(with_points: bool=True, with_normals: bool=True, with_dip: bool=True, with_dip_dir: bool=True, with_clusters=False) -> PCDom:
    """
    Return a synthetic PCDom to run properly the tests below.
    """
    pc = PCDom()
    
    if with_points:
        if with_clusters:
            # --- Three tight, well-separated clusters ---
            # Each cluster is a small flat patch of 200 points
            # placed far apart so the search radius won't bridge them.
            rng = np.random.default_rng(42)

            # Cluster A: around (0, 0, 0), dip=10°, dip_dir=10°
            pts_a = rng.uniform(0, 5, (200, 3))
            dip_a = np.full(200, 10.0)
            dd_a  = np.full(200, 10.0)

            # Cluster B: around (100, 0, 0), dip=45°, dip_dir=90°
            pts_b = rng.uniform(0, 5, (200, 3)) + np.array([100, 0, 0])
            dip_b = np.full(200, 45.0)
            dd_b  = np.full(200, 90.0)

            # Cluster C: around (0, 100, 0), dip=70°, dip_dir=270°
            pts_c = rng.uniform(0, 5, (200, 3)) + np.array([0, 100, 0])
            dip_c = np.full(200, 70.0)
            dd_c  = np.full(200, 270.0)

            all_pts = np.vstack([pts_a, pts_b, pts_c])
            all_dip = np.concatenate([dip_a, dip_b, dip_c])
            all_dd  = np.concatenate([dd_a,  dd_b,  dd_c])

            pc.points = all_pts

            pc.init_point_data("dip", 1)
            pc.set_point_data("dip", all_dip)
            pc.init_point_data("dip direction", 1)
            pc.set_point_data("dip direction", all_dd)
            return pc
        
        #Create the points
        pc.points = np.random.uniform(0, 50, size=(10000, 3))
        
        if with_normals:
            #Create and add the normals
            pc.vtk_set_normals()
            
            if with_dip:
                #Create and add the dip and dip direction
                dip = pc.points_map_dip
                pc.init_point_data("dip", 1)
                pc.set_point_data("dip", dip)
            if with_dip_dir:
                dip_dir = pc.points_map_dip_direction
                pc.init_point_data("dip direction", 1)
                pc.set_point_data("dip direction", dip_dir)
    
    return pc

def _make_self(vtk_obj, uid: str = "uid_001", dip_data: bool = True, name: str = "Pc") -> MagicMock:
    """
    Build a MagicMock that behaves like 'self' inside a PZero tool/widget.
    """
    self_mock = MagicMock()
    self_mock.selected_uids = [uid]
    self_mock.parent.dom_coll.get_uid_name.return_value = name
    self_mock.parent.dom_coll.get_uid_vtk_obj.return_value = vtk_obj  
    
    if dip_data:
        self_mock.parent.dom_coll.get_uid_properties_names.return_value = ["dip", "dip direction"]
        self_mock.parent.dom_coll.get_uid_properties_components.return_value = [1, 1]
    else:
        self_mock.parent.dom_coll.get_uid_properties_names.return_value = ["Normals"]
        self_mock.parent.dom_coll.get_uid_properties_components.return_value = [3]
        
    self_mock.parent.dom_coll.entity_dict = {
    "uid": "",
    "name": "",
    "topology": "",
    "properties_names": [],
    "properties_components": [],
    "vtk_obj": None,
    }
    
    self_mock.parent.geol_coll.entity_dict = {
    "uid": "",
    "name": "",
    "role" : "",
    "topology": "",
    "features" : "",
    "properties_names": [],
    "properties_components": [],
    "vtk_obj": None,
    }
    
    return self_mock

def _make_self_multi(vtk_objs: list, uids: list) -> MagicMock:
    """
    Version of _make_self for functions that loop over multiple selected UIDs.
    vtk_objs[i] is returned when get_uid_vtk_obj(uids[i]) is called.
    """
    self_mock = MagicMock()
    self_mock.selected_uids = uids
    self_mock.parent.dom_coll.get_uid_vtk_obj.side_effect = lambda uid: vtk_objs[uids.index(uid)]
    self_mock.parent.dom_coll.get_uid_properties_names.return_value = ["Normals"]
    return self_mock


# =============================================================================
# TEST CLASS
# =============================================================================

class TestNormals2dd:
    """
    Tests for normals2dd() defined in point_clouds.py.

    normals2dd reads the normal vectors already stored on a point cloud and
    converts them into dip and dip-direction angles, then writes those angles
    back onto the same point cloud.

    Because normals2dd() needs a running PZero application to work normally,
    we replace all of those parts with MagicMocks. That way we can test the
    logic of the function in isolation, without starting the whole application.
    """

    def test_no_selection_prints_warning(self, capsys):
        """
        If the user forgot to select a point cloud in the GUI,
        selected_uids is empty. The function should print a clear warning
        and return immediately without touching anything else.
        """
        self_mock = MagicMock()
        self_mock.selected_uids = []
        normals2dd(self_mock)

        printed = capsys.readouterr().out
        assert "No entities selected" in printed

        self_mock.parent.dom_coll.get_uid_vtk_obj.assert_not_called()

    def test_missing_normals_prints_warning(self, capsys):
        """
        If the selected point cloud has no normal vectors yet,
        the function should print a warning and NOT write any data.
        """
        vtk_obj   = _make_real_pc(with_points=True, with_normals=False)
        self_mock = _make_self(vtk_obj)
        normals2dd(self_mock)

        printed = capsys.readouterr().out
        assert "Normal data not present" in printed

    def test_dip_values_in_valid_range(self):
        """
        Dip is the angle between a plane and the horizontal.
        It must always be between 0 degrees (flat) and 90 degrees (vertical).
        """
        vtk_obj   = _make_real_pc()
        self_mock = _make_self(vtk_obj)
        normals2dd(self_mock)

        dip = vtk_obj.get_point_data("dip")
        assert dip is not None, "set_point_data('dip', ...) was never called"
        assert np.all(dip >= 0) and np.all(dip <= 90), (
            f"Dip out of [0, 90]: min={dip.min():.2f}  max={dip.max():.2f}"
        )

    def test_dip_direction_values_in_valid_range(self):
        """
        Dip direction is the compass bearing of the steepest descent.
        It must always be between 0 and 360 degrees.
        """
        vtk_obj   = _make_real_pc()
        self_mock = _make_self(vtk_obj)
        normals2dd(self_mock)

        dd = vtk_obj.get_point_data("dip direction")
        assert dd is not None, "set_point_data('dip direction', ...) was never called"
        assert np.all(dd >= 0) and np.all(dd < 360), (
            f"Dip direction out of [0, 360): min={dd.min():.2f}  max={dd.max():.2f}"
        )

    def test_dip_values_match_points_map_dip(self):
        """
        The written dip values must match exactly what points_map_dip
        (the PCDom property) returned. This confirms that normals2dd is
        reading from the right property and not transforming it incorrectly.
        """
        vtk_obj   = _make_real_pc()
        self_mock = _make_self(vtk_obj)
        normals2dd(self_mock)

        written  = vtk_obj.get_point_data("dip")
        expected = vtk_obj.points_map_dip
        np.testing.assert_allclose(
            written, expected, atol=1e-6,
            err_msg="Written dip values differ from points_map_dip"
        )

    def test_dip_direction_values_match_points_map_dip_direction(self):
        """
        Same check for dip direction: values written must match exactly
        what points_map_dip_direction returned.
        """
        vtk_obj   = _make_real_pc()
        self_mock = _make_self(vtk_obj)
        normals2dd(self_mock)

        written  = vtk_obj.get_point_data("dip direction")
        expected = vtk_obj.points_map_dip_direction
        np.testing.assert_allclose(
            written, expected, atol=1e-6,
            err_msg="Written dip direction values differ from points_map_dip_direction"
        )
        
    def test_with_real_dat_file(self, request):
        """
        Optional integration test using a real .dat point cloud file.

        The file must contain one point per row: x y z (space-separated).
        """
        dat_path = request.config.getoption("--dat-file", default=None)
        if dat_path is None:
            pytest.skip("No .dat file provided - use --dat-file=<path> to enable")

        points = np.loadtxt(dat_path, dtype=np.float64, skiprows=1)

        # Subsample up to 5000 points for plane fitting.
        # SVD on the full cloud would require enormous memory for large files.
        rng = np.random.default_rng(42)
        sample_size = min(5000, len(points))
        sample = points[rng.choice(len(points), sample_size, replace=False)]

        centroid = sample.mean(axis=0)
        _, _, Vt = np.linalg.svd(sample - centroid, full_matrices=False)
        normal = Vt[-1]
        if normal[2] > 0:
            normal = -normal
        normals = np.tile(normal, (len(points), 1))

        vtk_obj = MagicMock()
        vtk_obj.point_data_keys = ["Normals"]
        nz = np.clip(normals[:, 2], -1.0, 1.0)
        vtk_obj.points_map_dip           = 90 - np.degrees(np.arcsin(-nz))
        vtk_obj.points_map_dip_direction = (
            np.degrees(np.arctan2(normals[:, 0], normals[:, 1])) - 180
        ) % 360
        _written: dict = {}
        vtk_obj.init_point_data.side_effect = lambda k, _: _written.update({k: None})
        vtk_obj.set_point_data.side_effect  = lambda k, v: _written.update({k: v})
        vtk_obj._written = _written

        self_mock = _make_self(vtk_obj)
        normals2dd(self_mock)

        dip = _written.get("dip")
        dd  = _written.get("dip direction")

        assert dip is not None and dd is not None
        print(f"\n[.dat] dip:           mean={dip.mean():.1f}  std={dip.std():.1f}")
        print(f"[.dat] dip direction: mean={dd.mean():.1f}  std={dd.std():.1f}")


class TestCutPC:
   """
   Tests for cut_pc() defined in point_clouds.py.

   cut_pc add a new entry to the pc's dictionnary with 3 different methods.
   "Inner" and "Outer" add entries for the inside and outside of the selection
   of the scissors helper. "Both" do both at the same time. And these methods then
   write the cropped data in the corresponding propreties_components

   Because cut_pc() needs a running PZero application to work normally and is using
   an internal function as a callback of the scissors helper, we can only test 
   the warning if no data are selected.
   Note that the callback function (end_digitize()) should work properly if the
   scissor helper and the function extract_pc() in point_clouds.py are working well.
   """
   
   def test_no_selection_prints_warning(self, capsys):
       """
       If the user forgot to select a point cloud in the GUI,
       selected_uids is empty. The function should print a clear warning
       and return immediately without touching anything else.
       """
       self_mock = MagicMock()
       self_mock.selected_uids = []
       cut_pc(self_mock)

       printed = capsys.readouterr().out
       assert " -- No input data selected -- " in printed

       self_mock.plotter.track_click_position.assert_not_called()


class TestDecimatePC:
    """
    Tests for decimate_pc() defined in point_clouds.py.

    decimate_pc returns a randomly decimate PCDom by a decimation factor defined
    in argument of the function.
    """
    
    def test_wrong_factor_prints_warning(self, capsys):
        """
        If the user used a wrong decimation factor (ie not in [0:1]). 
        The function should print a clear warning and return
        immediately without touching anything else.
        """
        vtk_obj = _make_real_pc(with_points=True, with_normals=False)
        decimate_pc(vtk_obj, 2)

        printed = capsys.readouterr().out
        assert "Decimation factor to large, you can not decimate by a factor not in [0%:100%]" in printed
        
    def test_decimated_pc_size(self):
        """
        Size of the decimated pc must be 
        size_orignial_pc * decimation_factor
        """        
        
        vtk_obj = PCDom()
        vtk_obj.points = np.random.choice(np.arange(0, 1000), size=(100, 3))
         
        decimated_pc = decimate_pc(vtk_obj, 0.5)
        
        assert decimated_pc.GetNumberOfPoints() != 0 and decimated_pc.GetNumberOfPoints() is not None, "Problem, size is 0"
        np.testing.assert_allclose(decimated_pc.GetNumberOfPoints(),
            vtk_obj.GetNumberOfPoints()*0.5 , atol=1,
            err_msg="Decimated pc size not correct")
        
    def test_decimation(self):
        """
        Decimated_pc should be contain in original_pc.
        If all the points of decimate_pc are in original_pc, means
        extract_id is working well.
        """
        
        vtk_obj = _make_real_pc()
         
        decimated_pc = decimate_pc(vtk_obj, 0.5)
        
        assert set(decimated_pc.points[:, 0]).issubset(vtk_obj.points[:, 0])
        assert set(decimated_pc.points[:, 1]).issubset(vtk_obj.points[:, 1])


class TestSegmentPC:
    """
    Tests for segment_pc() defined in point_clouds.py.

    segment_pc is using a graph-based approach to segment a point cloud into
    multiple clusters corresponding to the different facets orientations within
    the object. It filters in a user specified range points depending on their
    dip direction, then it cluster depending on points dips and finally
    it filter the outlier values.

    Because segment_pc() needs a running PZero application to work normally,
    we replace all of those parts with MagicMocks. That way we can test the
    logic of the function in isolation, without starting the whole application.
    """
    
    @pytest.fixture(autouse=False)
    def mock_dialog(self): 
        """
        Small helper to mimic the dialog box in the segment_pc script
        """  
        with patch("pzero.point_clouds.multiple_input_dialog") as m:
            yield m
             
    def test_no_selection_prints_warning(self, capsys):
        """
        If the user forgot to select a point cloud in the GUI,
        selected_uids is empty. The function should print a clear warning
        and return immediately without touching anything else.
        """
        self_mock = MagicMock()
        self_mock.selected_uids = []
        segment_pc(self_mock)

        printed = capsys.readouterr().out
        assert "No entities selected, make sure to have the right tab open" in printed

        self_mock.parent.dom_coll.get_uid_vtk_obj.assert_not_called() 
        
    def test_missing_dip_dir_prints_warning(self, capsys):
        """
        If the user selected a point cloud that has no dip direction,
        the function should print a clear warning and return immediatly 
        whitout touching anything else.
        """
        
        vtk_obj = _make_real_pc(with_dip=False, with_dip_dir=False)
        self_mock = _make_self(vtk_obj, dip_data=False)
        segment_pc(self_mock)

        printed = capsys.readouterr().out
        assert "dip direction/dip data not present in the dataset. Calculate from Normals using the specific function." in printed

        self_mock.parent.dom_coll.add_entity_from_dict.assert_not_called() 
        
    def test_vtk_not_PD_Dom(self, capsys):
        """
        If the user selected an object that is not a PCDom,
        the function should print a clear warning and return immediatly 
        whitout touching anything else.
        """
        
        vtk_obj = MagicMock()
        self_mock = _make_self(vtk_obj)
        segment_pc(self_mock)

        printed = capsys.readouterr().out
        assert "Entity not point cloud or multiple entities visible" in printed

        self_mock.parent.dom_coll.add_entity_from_dict.assert_not_called()                  
        
    def test_data_outside_threshold(self, mock_dialog):
        """
        If there are selected cluster that are outside the thresholds,
        they should not be taken in account 
        """
        mock_dialog.return_value = {
            "name": "test_result",
            "dd1": 0,
            "dd2": 100,    # to keep the cluster A and B
            "d1":  0,
            "d2":  20,     # to keep only cluster A
            "rad": 10.0,
            "nn":  5,
            }
        vtk_obj = _make_real_pc(with_clusters=True)
        self_mock = _make_self(vtk_obj)
        segment_pc(self_mock)
        
        # To get back the data from segment_pc because since it is using a 
        # MagicMock object, it is not returning anything
        call_args = self_mock.parent.dom_coll.add_entity_from_dict.call_args
        entity_dict = call_args.kwargs["entity_dict"]
        seg_pc = entity_dict["vtk_obj"] 

        assert seg_pc.GetNumberOfPoints() != 0 and seg_pc.GetNumberOfPoints() is not None, "Problem, size is 0"
        # The pc size should be 200 since there is only one cluster left
        assert 180 <= seg_pc.GetNumberOfPoints() <= 200, "Problem, there is no one cluster left"
        
    def test_neighbor_cleaning(self, mock_dialog, capsys):
        """
        If there are cluster smaller than "nn",
        they should not be taken in account 
        """
        mock_dialog.return_value = {
            "name": "test_result",
            "dd1": 0,
            "dd2": 360,  
            "d1":  0,
            "d2":  90,     
            "rad": 10.0,
            "nn":  250,    # the cluster are 200 points so the result should be empty
            }
        vtk_obj = _make_real_pc(with_clusters=True)
        self_mock = _make_self(vtk_obj)
        segment_pc(self_mock)
        
        printed = capsys.readouterr().out
        assert "No clusters found after filtering" in printed
        self_mock.parent.dom_coll.add_entity_from_dict.assert_not_called()
        
    def test_clusters_in_pc(self, mock_dialog):
        """
        All the created cluster should be part of the original
        point cloud. If it's true, means the segmentation is working well
        """
        mock_dialog.return_value = {
            "name": "test_result",
            "dd1": 0,
            "dd2": 360,    
            "d1":  0,
            "d2":  90,    
            "rad": 10.0,
            "nn":  5,
            }
        vtk_obj = _make_real_pc(with_clusters=True)
        self_mock = _make_self(vtk_obj)
        segment_pc(self_mock)
        
        # To get back the data from segment_pc because since it is using a 
        # MagicMock object, it is not returning anything
        call_args = self_mock.parent.dom_coll.add_entity_from_dict.call_args
        entity_dict = call_args.kwargs["entity_dict"]
        seg_pc = entity_dict["vtk_obj"] 

        assert set(seg_pc.points[:, 0]).issubset(vtk_obj.points[:, 0])
        assert set(seg_pc.points[:, 1]).issubset(vtk_obj.points[:, 1])
        assert set(seg_pc.points[:, 2]).issubset(vtk_obj.points[:, 2])
 
    def test_clusters_id(self, mock_dialog):
        """
        All the created cluster should have different id.
        """
        mock_dialog.return_value = {
            "name": "test_result",
            "dd1": 0,
            "dd2": 360,    
            "d1":  0,
            "d2":  90,    
            "rad": 10.0,
            "nn":  5,
            }
        vtk_obj = _make_real_pc(with_clusters=True)
        self_mock = _make_self(vtk_obj)
        segment_pc(self_mock)
        
        # To get back the data from segment_pc because since it is using a 
        # MagicMock object, it is not returning anything
        call_args = self_mock.parent.dom_coll.add_entity_from_dict.call_args
        entity_dict = call_args.kwargs["entity_dict"]
        seg_pc = entity_dict["vtk_obj"]
        cluster_ids = seg_pc.get_point_data("ClusterId")
        unique_ids  = set(cluster_ids)

        assert len(unique_ids) == 3, "Some clusters have the same id"  
   
    def test_with_real_dat_file(self, request, mock_dialog):
        """
        Optional integration test using a real .dat point cloud file.

        The file must contain one point per row: x y z (space-separated).
        
        If you want to see the prints and run only this function, run :
        pytest test_point_clouds.py::TestSegmentPC::test_with_real_dat_file -v -s 
            --dat-file=/path/to/your/data
        """
        dat_path = request.config.getoption("--dat-file", default=None)
        if dat_path is None:
            pytest.skip("No .dat file provided - use --dat-file=<path> to enable")

        mock_dialog.return_value = {
            "name": "test_result",
            "dd1": 0,
            "dd2": 360,    
            "d1":  0,
            "d2":  90,    
            "rad": 1.0,
            "nn":  1,   # accept almost all the clusters
            }

        points = np.loadtxt(dat_path, dtype=np.float64, skiprows=1)

        # Subsample up to 10000 points for plane fitting.
        # SVD on the full cloud would require enormous memory for large files.
        rng = np.random.default_rng(42)
        sample_size = min(100000, len(points))
        sample = points[rng.choice(len(points), sample_size, replace=False)]

        pc = PCDom()
        pc.points = sample[:, :3]
        #Create and add the normals
        pc.vtk_set_normals()
        #Create and add the dip and dip direction
        dip = pc.points_map_dip
        pc.init_point_data("dip", 1)
        pc.set_point_data("dip", dip)
        dip_dir = pc.points_map_dip_direction
        pc.init_point_data("dip direction", 1)
        pc.set_point_data("dip direction", dip_dir)

        self_mock = _make_self(pc)
        segment_pc(self_mock)
        
        call_args   = self_mock.parent.dom_coll.add_entity_from_dict.call_args
        entity_dict = call_args.kwargs["entity_dict"]
        seg_pc      = entity_dict["vtk_obj"]

        # Properties that must always hold regardless of the data
        assert seg_pc.GetNumberOfPoints() <= pc.GetNumberOfPoints()
        assert seg_pc.GetNumberOfPoints()  > 0
        cluster_ids = seg_pc.get_point_data("ClusterId")
        assert np.all(cluster_ids >= 0)
        dip    = seg_pc.get_point_data("dip")
        dip_dir = seg_pc.get_point_data("dip direction")
        assert np.all(dip     >= mock_dialog.return_value["d1"])  and np.all(dip     <= mock_dialog.return_value["d2"])
        assert np.all(dip_dir >= mock_dialog.return_value["dd1"]) and np.all(dip_dir <= mock_dialog.return_value["dd2"])
        for uid in np.unique(cluster_ids):
            cluster_size = np.sum(cluster_ids == uid)
            assert cluster_size > mock_dialog.return_value["nn"], \
                f"Cluster {uid} has only {cluster_size} points, below nn={mock_dialog.return_value['nn']}"

        print(f"\n[.dat] original points : {pc.GetNumberOfPoints()}")
        print(f"[.dat] segmented points: {seg_pc.GetNumberOfPoints()}")
        print(f"[.dat] clusters found  : {len(np.unique(cluster_ids))}")
   
    
class TestFacetsPC:
    """
    Tests for facets_pc() defined in point_clouds.py.

    facets_pc is using a 2D Delaunay approach to convert a point cloud
    that has clusters into a TriSurf that has polygons. Each cluster
    is transformed into a polygon along the best fitting plane.

    Because facets_pc() needs a running PZero application to work normally,
    we replace all of those parts with MagicMocks. That way we can test the
    logic of the function in isolation, without starting the whole application.
    """
    
    @pytest.fixture(autouse=False)
    def mock_dialog(self): 
        """
        Small helper to mimic the dialog box in the segment_pc script
        """  
        with patch("pzero.point_clouds.multiple_input_dialog") as m:
            yield m
            
    def test_no_selection_prints_warning(self, capsys):
        """
        If the user forgot to select a point cloud in the GUI,
        selected_uids is empty. The function should print a clear warning
        and return immediately without touching anything else.
        """
        self_mock = MagicMock()
        self_mock.selected_uids = []
        facets_pc(self_mock)

        printed = capsys.readouterr().out
        assert "No entities selected, make sure to have the right tab open" in printed

        self_mock.parent.dom_coll.get_uid_vtk_obj.assert_not_called() 
        
    def test_missing_clusters_prints_warning(self, capsys):
        """
        If the user selected a point cloud that has no clusters,
        the function should print a clear warning and return immediatly 
        whitout touching anything else.
        """
        
        vtk_obj = _make_real_pc()
        self_mock = _make_self(vtk_obj)
        facets_pc(self_mock)

        printed = capsys.readouterr().out
        assert "Selected entity has no clusters, please choose an other or make them with the proper function" in printed

        self_mock.parent.geol_coll.add_entity_from_dict.assert_not_called()
        
    def test_n_poly(self, mock_dialog):
        """
        The number of polygons should be equal to the number of cluster.
        if it is true, the field array outputed should be the same size
        as n_clust.
        """
        
        mock_dialog.return_value = {
            "name": "test_result",
            "dd1": 0,
            "dd2": 360,   
            "d1":  0,
            "d2":  90,    
            "rad": 10.0,
            "nn":  5,
            }
        vtk_obj = _make_real_pc(with_clusters=True)
        self_mock = _make_self(vtk_obj)
        segment_pc(self_mock)
        # To get back the data from segment_pc because since it is using a 
        # MagicMock object, it is not returning anything
        call_args = self_mock.parent.dom_coll.add_entity_from_dict.call_args
        entity_dict_clust = call_args.kwargs["entity_dict"]
        clust = entity_dict_clust["vtk_obj"]
        n_clust = len(set(clust.get_point_data("ClusterId")))
        
        self_mock_facets = _make_self(clust)
        facets_pc(self_mock_facets)
        # To get back the data from facets_pc because since it is using a 
        # MagicMock object, it is not returning anything
        call_args = self_mock_facets.parent.geol_coll.add_entity_from_dict.call_args
        entity_dict_facets = call_args.kwargs["entity_dict"]
        facets = entity_dict_facets["vtk_obj"]
        assert len(facets.get_field_data("Normals")) // 3      == n_clust, "There is a wrong number of normals"
        assert len(facets.get_field_data("Centers"))  // 3     == n_clust, "There is a wrong number of centers"
        assert len(facets.get_field_data("dip"))           == n_clust, "There is a wrong number of dip"
        assert len(facets.get_field_data("dip direction")) == n_clust, "There is a wrong number of dir"
        assert len(facets.get_field_data("area"))          == n_clust, "There is a wrong number of area"
        assert len(facets.get_field_data("width"))         == n_clust, "There is a wrong number of width"
        assert len(facets.get_field_data("length"))        == n_clust, "There is a wrong number of length"
        
    def test_positive_area(self, mock_dialog):
        """
        The area of the facets should be positive,
        otherwise there is a problem with triangulation
        or colinear points.
        """
        
        mock_dialog.return_value = {
            "name": "test_result",
            "dd1": 0,
            "dd2": 360,   
            "d1":  0,
            "d2":  90,    
            "rad": 10.0,
            "nn":  5,
            }
        vtk_obj = _make_real_pc(with_clusters=True)
        self_mock = _make_self(vtk_obj)
        segment_pc(self_mock)
        # To get back the data from segment_pc because since it is using a 
        # MagicMock object, it is not returning anything
        call_args = self_mock.parent.dom_coll.add_entity_from_dict.call_args
        entity_dict_clust = call_args.kwargs["entity_dict"]
        clust = entity_dict_clust["vtk_obj"]
        
        self_mock_facets = _make_self(clust)
        facets_pc(self_mock_facets)
        # To get back the data from facets_pc because since it is using a 
        # MagicMock object, it is not returning anything
        call_args = self_mock_facets.parent.geol_coll.add_entity_from_dict.call_args
        entity_dict_facets = call_args.kwargs["entity_dict"]
        facets = entity_dict_facets["vtk_obj"]
        area = facets.get_field_data("area")
        assert np.all(area > 0), "Some areas are null or negatives"
        
    def test_positive_width_length(self, mock_dialog):
        """
        The width and length of the facets should non zero
        or negative, otherwise there is a problem with geometry.
        """
        
        mock_dialog.return_value = {
            "name": "test_result",
            "dd1": 0,
            "dd2": 360,   
            "d1":  0,
            "d2":  90,    
            "rad": 10.0,
            "nn":  5,
            }
        vtk_obj = _make_real_pc(with_clusters=True)
        self_mock = _make_self(vtk_obj)
        segment_pc(self_mock)
        # To get back the data from segment_pc because since it is using a 
        # MagicMock object, it is not returning anything
        call_args = self_mock.parent.dom_coll.add_entity_from_dict.call_args
        entity_dict_clust = call_args.kwargs["entity_dict"]
        clust = entity_dict_clust["vtk_obj"]
        
        self_mock_facets = _make_self(clust)
        facets_pc(self_mock_facets)
        # To get back the data from facets_pc because since it is using a 
        # MagicMock object, it is not returning anything
        call_args = self_mock_facets.parent.geol_coll.add_entity_from_dict.call_args
        entity_dict_facets = call_args.kwargs["entity_dict"]
        facets = entity_dict_facets["vtk_obj"]
        assert np.all(facets.get_field_data("width")  > 0), "Some width are non positives"
        assert np.all(facets.get_field_data("length") > 0), "Some length are non positives"
        
    def test_normals_unit(self, mock_dialog):
        """
        The normals should be unit vectors, otherwise
        all the dip and dip directions are wrong and there
        is a problem with best_fitting_plane.
        """
        
        mock_dialog.return_value = {
            "name": "test_result",
            "dd1": 0,
            "dd2": 360,   
            "d1":  0,
            "d2":  90,    
            "rad": 10.0,
            "nn":  5,
            }
        vtk_obj = _make_real_pc(with_clusters=True)
        self_mock = _make_self(vtk_obj)
        segment_pc(self_mock)
        # To get back the data from segment_pc because since it is using a 
        # MagicMock object, it is not returning anything
        call_args = self_mock.parent.dom_coll.add_entity_from_dict.call_args
        entity_dict_clust = call_args.kwargs["entity_dict"]
        clust = entity_dict_clust["vtk_obj"]
        
        self_mock_facets = _make_self(clust)
        facets_pc(self_mock_facets)
        # To get back the data from facets_pc because since it is using a 
        # MagicMock object, it is not returning anything
        call_args = self_mock_facets.parent.geol_coll.add_entity_from_dict.call_args
        entity_dict_facets = call_args.kwargs["entity_dict"]
        facets = entity_dict_facets["vtk_obj"]
        normals = facets.get_field_data("Normals").reshape(-1, 3)
        norms   = np.linalg.norm(normals, axis=1)
        np.testing.assert_allclose(norms, 1.0, atol=1e-5), "Some Normals are not unit"
        
    def test_normals_downward(self, mock_dialog):
        """
        The normals should be downward, otherwise
        all the dip are wrong and the convention
        is not respected.
        """
        
        mock_dialog.return_value = {
            "name": "test_result",
            "dd1": 0,
            "dd2": 360,   
            "d1":  0,
            "d2":  90,    
            "rad": 10.0,
            "nn":  5,
            }
        vtk_obj = _make_real_pc(with_clusters=True)
        self_mock = _make_self(vtk_obj)
        segment_pc(self_mock)
        # To get back the data from segment_pc because since it is using a 
        # MagicMock object, it is not returning anything
        call_args = self_mock.parent.dom_coll.add_entity_from_dict.call_args
        entity_dict_clust = call_args.kwargs["entity_dict"]
        clust = entity_dict_clust["vtk_obj"]
        
        self_mock_facets = _make_self(clust)
        facets_pc(self_mock_facets)
        # To get back the data from facets_pc because since it is using a 
        # MagicMock object, it is not returning anything
        call_args = self_mock_facets.parent.geol_coll.add_entity_from_dict.call_args
        entity_dict_facets = call_args.kwargs["entity_dict"]
        facets = entity_dict_facets["vtk_obj"]
        normals = facets.get_field_data("Normals").reshape(-1, 3)
        assert np.all(normals[:, 2] < 0), "Some Normals doesn't point downward"
        
    def test_topology_is_tri_surf(self, mock_dialog):
        """
        The topology should be a TriSurf object otherwise, 
        there is a problem with the dictionnary saving.
        """
        
        mock_dialog.return_value = {
            "name": "test_result",
            "dd1": 0,
            "dd2": 360,   
            "d1":  0,
            "d2":  90,    
            "rad": 10.0,
            "nn":  5,
            }
        vtk_obj = _make_real_pc(with_clusters=True)
        self_mock = _make_self(vtk_obj)
        segment_pc(self_mock)
        # To get back the data from segment_pc because since it is using a 
        # MagicMock object, it is not returning anything
        call_args = self_mock.parent.dom_coll.add_entity_from_dict.call_args
        entity_dict_clust = call_args.kwargs["entity_dict"]
        clust = entity_dict_clust["vtk_obj"]
        
        self_mock_facets = _make_self(clust)
        facets_pc(self_mock_facets)
        # To get back the data from facets_pc because since it is using a 
        # MagicMock object, it is not returning anything
        call_args = self_mock_facets.parent.geol_coll.add_entity_from_dict.call_args
        entity_dict_facets = call_args.kwargs["entity_dict"]
        assert entity_dict_facets["topology"] == "TriSurf"
        
    def test_with_real_dat_file(self, request, mock_dialog):
        """
        Optional integration test using a real .dat point cloud file.

        The file must contain one point per row: x y z (space-separated).
        
        If you want to see the prints and run only this function, run :
        pytest test_point_clouds.py::TestFacetsPC::test_with_real_dat_file -v -s 
            --dat-file=/path/to/your/data
        """
        dat_path = request.config.getoption("--dat-file", default=None)
        if dat_path is None:
            pytest.skip("No .dat file provided - use --dat-file=<path> to enable")

        mock_dialog.return_value = {
            "name": "test_result",
            "dd1": 0,
            "dd2": 360,    
            "d1":  0,
            "d2":  90,    
            "rad": 10.0,
            "nn":  1,   # accept almost all the clusters
            }

        points = np.loadtxt(dat_path, dtype=np.float64, skiprows=1)

        # Subsample up to 10000 points for plane fitting.
        # SVD on the full cloud would require enormous memory for large files.
        rng = np.random.default_rng(42)
        sample_size = min(100000, len(points))
        sample = points[rng.choice(len(points), sample_size, replace=False)]

        pc = PCDom()
        pc.points = sample[:, :3]
        #Create and add the normals
        pc.vtk_set_normals()
        #Create and add the dip and dip direction
        dip = pc.points_map_dip
        pc.init_point_data("dip", 1)
        pc.set_point_data("dip", dip)
        dip_dir = pc.points_map_dip_direction
        pc.init_point_data("dip direction", 1)
        pc.set_point_data("dip direction", dip_dir)

        self_mock = _make_self(pc)
        segment_pc(self_mock)
        
        call_args   = self_mock.parent.dom_coll.add_entity_from_dict.call_args
        entity_dict = call_args.kwargs["entity_dict"]
        clust     = entity_dict["vtk_obj"]
        n_clusters = len(set(clust.get_point_data("ClusterId")))

        self_mock_facets = _make_self(clust)
        facets_pc(self_mock_facets)
        # To get back the data from facets_pc because since it is using a 
        # MagicMock object, it is not returning anything
        call_args = self_mock_facets.parent.geol_coll.add_entity_from_dict.call_args
        entity_dict_facets = call_args.kwargs["entity_dict"]
        facets = entity_dict_facets["vtk_obj"]
        
        #### TEST ####
        # Dip values in valid geological range
        dip = facets.get_field_data("dip")
        assert np.all(dip >= 0) and np.all(dip <= 90), \
            f"Dip out of [0, 90]: min={dip.min():.1f}  max={dip.max():.1f}"

        # Dip direction values in valid range
        dip_dir = facets.get_field_data("dip direction")
        assert np.all(dip_dir >= 0) and np.all(dip_dir < 360), \
            f"Dip direction out of [0, 360): min={dip_dir.min():.1f}  max={dip_dir.max():.1f}"

        # Area is positive for every facet
        area = facets.get_field_data("area")
        assert np.all(area > 0), \
            f"Some facets have zero or negative area: {area}"

        # Width and length are positive
        assert np.all(facets.get_field_data("width")  > 0)
        assert np.all(facets.get_field_data("length") > 0)

        # Normals are unit vectors
        normals = facets.get_field_data("Normals").reshape(-1, 3)
        norms   = np.linalg.norm(normals, axis=1)
        np.testing.assert_allclose(norms, 1.0, atol=1e-5,
            err_msg="Normals are not unit vectors")

        # Normals point downward (geological convention)
        assert np.all(normals[:, 2] < 0), \
            "Some normals point upward — convention violated"

        # Print a summary so you can visually inspect the results
        print(f"[.dat] clusters        : {n_clusters}")
        print(f"[.dat] dip             : {dip}")
        print(f"[.dat] dip direction   : {dip_dir}")
        print(f"[.dat] area            : {area}")
        print(f"[.dat] width           : {facets.get_field_data('width')}")
        print(f"[.dat] length          : {facets.get_field_data('length')}")
  
        
class TestCalibrationPC:
    """
    Tests for calibration_pc() defined in point_clouds.py.

    calibration_pc is creating a new entry to the vtk object for the distances
    between each points and the best fitting plane and it is plotting
    some statistics on the object.

    Because calibration_pc() needs a running PZero application to work normally,
    we replace all of those parts with MagicMocks. That way we can test the
    logic of the function in isolation, without starting the whole application.
    """
    
    @pytest.fixture(autouse=True)
    def mock_plot(self):
        """
        Small patch to avoid the crash when calling the plotting functions.
        The plot will not be returned.
        """ 
        with patch("pzero.point_clouds.plt_subplot") as mock_subplot, \
            patch("pzero.point_clouds.sns") as mock_sns:
            mock_fig = MagicMock()
            mock_subplot.return_value = (mock_fig, (MagicMock(), MagicMock()))
            mock_sns.histplot.return_value = MagicMock()
            yield
            
    def test_no_selection_prints_warning(self, capsys):
        """
        If the user forgot to select a point cloud in the GUI,
        selected_uids is empty. The function should print a clear warning
        and return immediately without touching anything else.
        """
        self_mock = MagicMock()
        self_mock.selected_uids = []
        calibration_pc(self_mock)

        printed = capsys.readouterr().out
        assert "No entities selected, make sure to have the right tab open" in printed

        self_mock.parent.dom_coll.replace_vtk.assert_not_called() 
        
    def test_missing_normals_prints_warning(self, capsys):
        """
        If the user selected a point cloud that has no Normals,
        the function should print a clear warning and return immediatly 
        whitout touching anything else.
        """
        
        vtk_obj = _make_real_pc(with_normals=False)
        self_mock = _make_self(vtk_obj)
        calibration_pc(self_mock)

        printed = capsys.readouterr().out
        assert "Selected entity has no Normals, please choose an other or make them with the proper function" in printed

        self_mock.parent.dom_coll.replace_vtk.assert_not_called() 
        
    def test_distance(self):
        """
        Each point cloud should have a "Distance" entry and
        all the distances should be positives otherwise,
        best_fitting_plane is not working. 
        """
        
        pc1 = _make_real_pc()
        pc2 = _make_real_pc()
        pc3 = _make_real_pc()
        pcs = [pc1, pc2, pc3]
        self_mock = _make_self_multi(pcs, ["uid_001", "uid_002", "uid_003"])
        calibration_pc(self_mock)
        
        distances1 = pc1.get_point_data("Distance")
        distances2 = pc2.get_point_data("Distance")
        distances3 = pc3.get_point_data("Distance")
        assert (distances1 is not None and
                distances2 is not None and
                distances3 is not None), "One of the distances is None"
        
        assert (np.all(distances1 >= 0) and
                np.all(distances2 >= 0) and
                np.all(distances3 >= 0)), "One of the distances is not positives"
        
        assert not np.array_equal(distances1, distances2), "pc1 and pc2 have identical distances"
        assert not np.array_equal(distances1, distances3), "pc1 and pc3 have identical distances"
        
        assert self_mock.parent.dom_coll.replace_vtk.call_count == 3, "All the vtk did not got updated"
        
        
class TestAutoPick:
    """
    Tests for auto_pick() defined in point_clouds.py.

    auto_pick is creating an Attitude at the centroid of each clusters and
    put it as a Vertex. Each Attitude is has a Normal vector wich is calculated
    with the best fitting plan.

    Because auto_pick() needs a running PZero application to work normally,
    we replace all of those parts with MagicMocks. That way we can test the
    logic of the function in isolation, without starting the whole application.
    """
    
    @pytest.fixture(autouse=False)
    def mock_dialog(self): 
        """
        Small helper to mimic the dialog box in the segment_pc script
        """  
        with patch("pzero.point_clouds.multiple_input_dialog") as m:
            yield m
            
    def test_no_selection_prints_warning(self, capsys):
        """
        If the user forgot to select a point cloud in the GUI,
        selected_uids is empty. The function should print a clear warning
        and return immediately without touching anything else.
        """
        self_mock = MagicMock()
        self_mock.selected_uids = []
        auto_pick(self_mock)

        printed = capsys.readouterr().out
        assert "No entities selected, make sure to have the right tab open" in printed

        self_mock.parent.dom_coll.get_uid_vtk_obj.assert_not_called() 
        
    def test_missing_clusters_prints_warning(self, capsys):
        """
        If the user selected a point cloud that has no clusters,
        the function should print a clear warning and return immediatly 
        whitout touching anything else.
        """
        
        vtk_obj = _make_real_pc()
        self_mock = _make_self(vtk_obj)
        auto_pick(self_mock)

        printed = capsys.readouterr().out
        assert "Selected entity has no Clusters, please choose an other or make them with the proper function" in printed

        self_mock.parent.geol_coll.add_entity_from_dict.assert_not_called()
        
    def test_Normals_present(self, mock_dialog):
        """
        The result should have Normals attached to it.
        Each cluster should have his normal.
        """
        
        mock_dialog.return_value = {
            "name": "test_result",
            "dd1": 0,
            "dd2": 360,   
            "d1":  0,
            "d2":  90,    
            "rad": 10.0,
            "nn":  1,
            }
        vtk_obj = _make_real_pc(with_clusters=True)
        self_mock = _make_self(vtk_obj)
        segment_pc(self_mock)
        # To get back the data from segment_pc because since it is using a 
        # MagicMock object, it is not returning anything
        call_args = self_mock.parent.dom_coll.add_entity_from_dict.call_args
        entity_dict_clust = call_args.kwargs["entity_dict"]
        clust = entity_dict_clust["vtk_obj"]
        
        self_mock_pick = _make_self(clust)
        auto_pick(self_mock_pick)
        # To get back the data from auto_pick because since it is using a 
        # MagicMock object, it is not returning anything
        call_args = self_mock_pick.parent.geol_coll.add_entity_from_dict.call_args
        entity_dict_pick = call_args.kwargs["entity_dict"]
        pick = entity_dict_pick["vtk_obj"]
        assert "Normals" in pick.point_data_keys, "There are missing Normals."  
        
    def test_Normals_are_right(self, mock_dialog):
        """
        The normals should be unit vectors and they should
        be pointing downward.
        """
        
        mock_dialog.return_value = {
            "name": "test_result",
            "dd1": 0,
            "dd2": 360,   
            "d1":  0,
            "d2":  90,    
            "rad": 10.0,
            "nn":  1,
            }
        vtk_obj = _make_real_pc(with_clusters=True)
        self_mock = _make_self(vtk_obj)
        segment_pc(self_mock)
        # To get back the data from segment_pc because since it is using a 
        # MagicMock object, it is not returning anything
        call_args = self_mock.parent.dom_coll.add_entity_from_dict.call_args
        entity_dict_clust = call_args.kwargs["entity_dict"]
        clust = entity_dict_clust["vtk_obj"]
        
        self_mock_pick = _make_self(clust)
        auto_pick(self_mock_pick)
        # To get back the data from auto_pick because since it is using a 
        # MagicMock object, it is not returning anything
        call_args = self_mock_pick.parent.geol_coll.add_entity_from_dict.call_args
        entity_dict_pick = call_args.kwargs["entity_dict"]
        pick = entity_dict_pick["vtk_obj"]
        normals = pick.get_point_data("Normals").reshape(-1, 3)
        
        norms   = np.linalg.norm(normals, axis=1)
        np.testing.assert_allclose(norms, 1.0, atol=1e-5), "Some Normals are not unit"
        assert np.all(normals[:, 2] < 0), "Some Normals doesn't point downward"
        
    def test_topology_is_vertex(self, mock_dialog):
        """
        The "Topology" field should be a "VertexSet". Otherwise,
        the function that add the dictionnary is not working.
        """
        
        mock_dialog.return_value = {
            "name": "test_result",
            "dd1": 0,
            "dd2": 360,   
            "d1":  0,
            "d2":  90,    
            "rad": 10.0,
            "nn":  1,
            }
        vtk_obj = _make_real_pc(with_clusters=True)
        self_mock = _make_self(vtk_obj)
        segment_pc(self_mock)
        # To get back the data from segment_pc because since it is using a 
        # MagicMock object, it is not returning anything
        call_args = self_mock.parent.dom_coll.add_entity_from_dict.call_args
        entity_dict_clust = call_args.kwargs["entity_dict"]
        clust = entity_dict_clust["vtk_obj"]
        
        self_mock_pick = _make_self(clust)
        auto_pick(self_mock_pick)
        # To get back the data from auto_pick because since it is using a 
        # MagicMock object, it is not returning anything
        call_args = self_mock_pick.parent.geol_coll.add_entity_from_dict.call_args
        entity_dict_pick = call_args.kwargs["entity_dict"]
        topo = entity_dict_pick["topology"]
        
        assert topo is "VertexSet", "The topology is not a Vertex"
        
    def test_feature_name_is_right(self, mock_dialog):
        """
        The "feature" field should return the name of the object.
        Here the name is "Pc".
        """
        
        mock_dialog.return_value = {
            "name": "test_result",
            "dd1": 0,
            "dd2": 360,   
            "d1":  0,
            "d2":  90,    
            "rad": 10.0,
            "nn":  1,
            }
        vtk_obj = _make_real_pc(with_clusters=True)
        self_mock = _make_self(vtk_obj)
        segment_pc(self_mock)
        # To get back the data from segment_pc because since it is using a 
        # MagicMock object, it is not returning anything
        call_args = self_mock.parent.dom_coll.add_entity_from_dict.call_args
        entity_dict_clust = call_args.kwargs["entity_dict"]
        clust = entity_dict_clust["vtk_obj"]
        
        self_mock_pick = _make_self(clust)
        auto_pick(self_mock_pick)
        # To get back the data from auto_pick because since it is using a 
        # MagicMock object, it is not returning anything
        call_args = self_mock_pick.parent.geol_coll.add_entity_from_dict.call_args
        entity_dict_pick = call_args.kwargs["entity_dict"]
        name = entity_dict_pick["feature"]
        
        assert name == self_mock_pick.parent.dom_coll.get_uid_name.return_value, "The feature name does not corresponding."
        
    def test_Attitude_has_right_number_of_points(self, mock_dialog):
        """
        The Attitude object that is returned should have 
        the same amount of point than the number of clusters.
        Otherwise, the loop on the clusters is not working.
        """
        
        mock_dialog.return_value = {
            "name": "test_result",
            "dd1": 0,
            "dd2": 360,   
            "d1":  0,
            "d2":  90,    
            "rad": 10.0,
            "nn":  1,
            }
        vtk_obj = _make_real_pc(with_clusters=True)
        self_mock = _make_self(vtk_obj)
        segment_pc(self_mock)
        # To get back the data from segment_pc because since it is using a 
        # MagicMock object, it is not returning anything
        call_args = self_mock.parent.dom_coll.add_entity_from_dict.call_args
        entity_dict_clust = call_args.kwargs["entity_dict"]
        clust = entity_dict_clust["vtk_obj"]
        n_clust = len(set(clust.get_point_data("ClusterId")))
        
        self_mock_pick = _make_self(clust)
        auto_pick(self_mock_pick)
        # To get back the data from auto_pick because since it is using a 
        # MagicMock object, it is not returning anything
        call_args = self_mock_pick.parent.geol_coll.add_entity_from_dict.call_args
        entity_dict_pick = call_args.kwargs["entity_dict"]
        pick = entity_dict_pick["vtk_obj"]
        n_attitude_points = pick.GetNumberOfPoints()
        
        assert 0 < n_attitude_points <= n_clust, "There is not the right number of pick points."
        
    def test_with_real_dat_file(self, request, mock_dialog):
        """
        Optional integration test using a real .dat point cloud file.

        The file must contain one point per row: x y z (space-separated).
        
        If you want to see the prints and run only this function, run :
        pytest test_point_clouds.py::TestAutoPick::test_with_real_dat_file -v -s --dat-file=/path/to/your/data
        """
        dat_path = request.config.getoption("--dat-file", default=None)
        if dat_path is None:
            pytest.skip("No .dat file provided - use --dat-file=<path> to enable")

        mock_dialog.return_value = {
            "name": "test_result",
            "dd1": 0,
            "dd2": 360,    
            "d1":  0,
            "d2":  90,    
            "rad": 10.0,
            "nn":  1,   # accept almost all the clusters
            }

        points = np.loadtxt(dat_path, dtype=np.float64, skiprows=1)

        # Subsample up to 10000 points for plane fitting.
        # SVD on the full cloud would require enormous memory for large files.
        rng = np.random.default_rng(42)
        sample_size = min(10000, len(points))
        sample = points[rng.choice(len(points), sample_size, replace=False)]

        pc = PCDom()
        pc.points = sample[:, :3]
        #Create and add the normals
        pc.vtk_set_normals()
        #Create and add the dip and dip direction
        dip = pc.points_map_dip
        pc.init_point_data("dip", 1)
        pc.set_point_data("dip", dip)
        dip_dir = pc.points_map_dip_direction
        pc.init_point_data("dip direction", 1)
        pc.set_point_data("dip direction", dip_dir)

        self_mock = _make_self(pc)
        segment_pc(self_mock)
        
        call_args   = self_mock.parent.dom_coll.add_entity_from_dict.call_args
        entity_dict = call_args.kwargs["entity_dict"]
        clust     = entity_dict["vtk_obj"]
        n_clusters = len(set(clust.get_point_data("ClusterId")))

        print(f"\n[.dat] original points : {pc.GetNumberOfPoints()}")
        print(f"[.dat] clusters found  : {n_clusters}")

        # --- Run auto_pick on the segmented cloud ---
        self_mock_ap = _make_self(clust)
        auto_pick(self_mock_ap)

        call_args   = self_mock_ap.parent.geol_coll.add_entity_from_dict.call_args
        entity_dict = call_args.kwargs["entity_dict"]
        result      = entity_dict["vtk_obj"]

        # 1 - Saved to geol_coll not dom_coll
        self_mock_ap.parent.geol_coll.add_entity_from_dict.assert_called_once()
        self_mock_ap.parent.dom_coll.add_entity_from_dict.assert_not_called()

        # 2 - Topology is VertexSet
        assert entity_dict["topology"] == "VertexSet", \
            f"Wrong topology: {entity_dict['topology']}"

        # 3 - Feature links back to the source object name
        assert entity_dict["feature"] == self_mock_ap.parent.dom_coll.get_uid_name.return_value, \
            "Feature field does not match the source object name"

        # 4 - One attitude point per cluster
        # auto_pick uses range(max_region) so result may have fewer points
        # than n_clusters if some IDs were non-contiguous — so we use <=
        n_attitude_points = result.GetNumberOfPoints()
        assert 0 < n_attitude_points <= n_clusters, \
            f"Expected <= {n_clusters} attitude points, got {n_attitude_points}"

        # 5 - Normals are present on the result
        assert "Normals" in result.point_data_keys, \
            "No Normals found on the Attitude result"

        # 6 - Normals are unit vectors
        normals = result.get_point_data("Normals").reshape(-1, 3)
        norms   = np.linalg.norm(normals, axis=1)
        np.testing.assert_allclose(norms, 1.0, atol=1e-5,
            err_msg="Normals are not unit vectors")

        # 7 - Normals point downward (geological convention)
        assert np.all(normals[:, 2] < 0), \
            "Some normals point upward — convention violated"

        # 8 - clear_selection was called
        self_mock_ap.clear_selection.assert_called_once()

        # 9 - Print summary for visual inspection
        print(f"[.dat] attitude points : {n_attitude_points}")
        print(f"[.dat] normals sample  : {normals[:3]}")
        
        
class TestThreshFilter:
    """
    Tests for thresh_filt() defined in point_clouds.py.

    thresh_filt is filtering the point cloud using threshold on a property.
    Both property and thresholds are selected by the user within a dialog box.

    Because thresh_filt() needs a running PZero application to work normally,
    we replace all of those parts with MagicMocks. That way we can test the
    logic of the function in isolation, without starting the whole application.
    """
    
    @pytest.fixture(autouse=False)
    def mock_dialog(self): 
        """
        Small helper to mimic the dialog box in the segment_pc script
        """  
        with patch("pzero.point_clouds.multiple_input_dialog") as m:
            yield m
    
    def test_no_selection_prints_warning(self, capsys):
        """
        If the user forgot to select a point cloud in the GUI,
        selected_uids is empty. The function should print a clear warning
        and return immediately without touching anything else.
        """
        self_mock = MagicMock()
        self_mock.selected_uids = []
        thresh_filt(self_mock)

        printed = capsys.readouterr().out
        assert "No entities selected, make sure to have the right tab open" in printed

        self_mock.parent.dom_coll.get_uid_vtk_obj.assert_not_called()
        
    def test_no_pc_selected(self, capsys):
        """
        If the user selected an object that is not a point cloud,
        the function should print a clear warning
        and return immediately without touching anything else.
        """
        self_mock = MagicMock()
        self_mock.selected_uids = ["uid_001"]
        thresh_filt(self_mock)

        printed = capsys.readouterr().out
        assert "Entity not point cloud or multiple entities visible" in printed

        self_mock.parent.dom_coll.add_entity_from_dict.assert_not_called()  
        
    def test_data_out_thresh(self, mock_dialog):
        """
        If there are data that are outside the thresholds,
        means the function is not working.
        """
        mock_dialog.return_value = {
            "prop_name": "dip direction",
            "l_t": 0,
            "u_t": 150,
                }
        
        vtk_obj = _make_real_pc(with_clusters=True)
        print(set(vtk_obj.get_point_data("dip direction")))
        vtk_obj.generate_cells()
        self_mock = _make_self(vtk_obj)
        thresh_filt(self_mock)
        # To get back the data from thresh_filt because since it is using a 
        # MagicMock object, it is not returning anything
        call_args = self_mock.parent.dom_coll.add_entity_from_dict.call_args
        entity_dict_filt = call_args.kwargs["entity_dict"]
        pc_filt = entity_dict_filt["vtk_obj"]
        
        assert pc_filt.GetNumberOfPoints() != 0 and pc_filt.GetNumberOfPoints() is not None, "Problem, size is 0"
        # The pc size should be 400 since there is only two cluster left
        assert 380 <= pc_filt.GetNumberOfPoints() <= 400, "Problem, there is no two clusters left"
        
    def test_topo_is_pc(self, mock_dialog):
        """
        The "Topology" field should be a "PCDom". Otherwise,
        the function that add the dictionnary is not working.
        """
        mock_dialog.return_value = {
            "prop_name": "dip direction",
            "l_t": 0,
            "u_t": 100,
                }
        
        vtk_obj = _make_real_pc(with_clusters=True)
        self_mock = _make_self(vtk_obj)
        thresh_filt(self_mock)
        # To get back the data from thresh_filt because since it is using a 
        # MagicMock object, it is not returning anything
        call_args = self_mock.parent.dom_coll.add_entity_from_dict.call_args
        entity_dict_filt = call_args.kwargs["entity_dict"]
        topo = entity_dict_filt["topology"]
        
        assert topo is "PCDom", "The topology is not a PointCloud"  
        
    def test_new_name_right(self, mock_dialog):
        """
        The "name" field should be a "Pc" + "_thresh_" + "l_t" + "_" + "u_t". 
        Otherwise, the function that create the name is not working.
        """
        mock_dialog.return_value = {
            "prop_name": "dip direction",
            "l_t": 0,
            "u_t": 100,
                }
        
        vtk_obj = _make_real_pc(with_clusters=True)
        self_mock = _make_self(vtk_obj)
        thresh_filt(self_mock)
        # To get back the data from thresh_filt because since it is using a 
        # MagicMock object, it is not returning anything
        call_args = self_mock.parent.dom_coll.add_entity_from_dict.call_args
        entity_dict_filt = call_args.kwargs["entity_dict"]
        name = entity_dict_filt["name"]
        
        assert name == "Pc_thresh_0_100", "The naming is not working."  
        
    def test_new_arrays_right(self, mock_dialog):
        """
        The other arrays than "name" and "vtk_obj" should not change.
        Otherwise, the function that add in the dictionnary is not working.
        """
        mock_dialog.return_value = {
            "prop_name": "dip direction",
            "l_t": 0,
            "u_t": 100,
                }
        
        vtk_obj = _make_real_pc(with_clusters=True)
        self_mock = _make_self(vtk_obj)
        thresh_filt(self_mock)
        # To get back the data from thresh_filt because since it is using a 
        # MagicMock object, it is not returning anything
        call_args = self_mock.parent.dom_coll.add_entity_from_dict.call_args
        entity_dict_filt = call_args.kwargs["entity_dict"]
        pc_filt = entity_dict_filt["vtk_obj"]
        
        # Check all properties are still present on the result
        for key in vtk_obj.point_data_keys:
            assert key in pc_filt.point_data_keys, f"Property '{key}' missing from result"
            
        original_dip = vtk_obj.get_point_data("dip")
        result_dip   = pc_filt.get_point_data("dip")

        # Every value in the result must have existed in the original
        assert set(result_dip).issubset(set(original_dip))
                