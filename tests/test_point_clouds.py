"""

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
from pzero.entities_factory import PCDom

from pzero.point_clouds import normals2dd, cut_pc, decimate_pc


# =============================================================================
# HELPERS
# =============================================================================

def _make_normals(n_points: int = 30, seed: int = 0) -> np.ndarray:
    """
    Return (N, 3) unit-normal vectors for a synthetic tilted plane.
    The plane is tilted ~17 degrees (dip) toward the East (~90 deg dip direction).
    All normals are identical because the plane is flat.
    """
    rng = np.random.default_rng(seed)
    xy  = rng.uniform(-5, 5, (n_points, 2))
    z   = 0.3 * xy[:, 0] + rng.normal(0, 0.02, n_points)
    points = np.column_stack([xy, z])

    centroid = points.mean(axis=0)
    _, _, Vt = np.linalg.svd(points - centroid)
    normal = Vt[-1]
    if normal[2] > 0:
        normal = -normal

    return np.tile(normal, (n_points, 1))


def _make_vtk_obj(with_points: bool = True, with_normals: bool = True, n_points: int = 30) -> MagicMock:
    """
    Build a MagicMock that behaves like a PCDom vtk object.

    with_normals=True  -> simulates a point cloud that already has normals
    with_normals=False -> simulates one that is missing normal data
    """
    vtk_obj = MagicMock()

    if with_points:
        vtk_obj.points = np.random.randint(0, 1000, size=(n_points, 3))

    if with_normals:
        normals = _make_normals(n_points)
        nz = np.clip(normals[:, 2], -1.0, 1.0)
        vtk_obj.points_map_dip           = 90 - np.degrees(np.arcsin(-nz))
        vtk_obj.points_map_dip_direction = (
            np.degrees(np.arctan2(normals[:, 0], normals[:, 1])) - 180
        ) % 360
        vtk_obj.point_data_keys = ["Normals"]
    else:
        vtk_obj.point_data_keys = []

    _written: dict = {}

    def _init(key, _components):
        _written[key] = None

    def _set(key, value):
        _written[key] = value

    vtk_obj.init_point_data.side_effect = _init
    vtk_obj.set_point_data.side_effect  = _set
    vtk_obj._written = _written
    vtk_obj.GetNumberOfPoints.return_value = n_points

    return vtk_obj


def _make_self(vtk_obj: MagicMock, uid: str = "uid_001") -> MagicMock:
    """
    Build a MagicMock that behaves like 'self' inside a PZero tool/widget.
    """
    self_mock = MagicMock()
    self_mock.selected_uids = [uid]
    self_mock.parent.dom_coll.get_uid_vtk_obj.return_value = vtk_obj
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
        vtk_obj   = _make_vtk_obj(with_points=False, with_normals=False)
        self_mock = _make_self(vtk_obj)

        normals2dd(self_mock)

        printed = capsys.readouterr().out
        assert "Normal data not present" in printed

        vtk_obj.set_point_data.assert_not_called()

    def test_dip_values_in_valid_range(self):
        """
        Dip is the angle between a plane and the horizontal.
        It must always be between 0 degrees (flat) and 90 degrees (vertical).
        """
        vtk_obj   = _make_vtk_obj()
        self_mock = _make_self(vtk_obj)
        normals2dd(self_mock)

        dip = vtk_obj._written.get("dip")
        assert dip is not None, "set_point_data('dip', ...) was never called"
        assert np.all(dip >= 0) and np.all(dip <= 90), (
            f"Dip out of [0, 90]: min={dip.min():.2f}  max={dip.max():.2f}"
        )

    def test_dip_direction_values_in_valid_range(self):
        """
        Dip direction is the compass bearing of the steepest descent.
        It must always be between 0 and 360 degrees.
        """
        vtk_obj   = _make_vtk_obj()
        self_mock = _make_self(vtk_obj)
        normals2dd(self_mock)

        dd = vtk_obj._written.get("dip direction")
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
        vtk_obj   = _make_vtk_obj()
        self_mock = _make_self(vtk_obj)
        normals2dd(self_mock)

        written  = vtk_obj._written.get("dip")
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
        vtk_obj   = _make_vtk_obj()
        self_mock = _make_self(vtk_obj)
        normals2dd(self_mock)

        written  = vtk_obj._written.get("dip direction")
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

        points = np.loadtxt(dat_path, dtype=np.float64)

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
        vtk_obj = _make_vtk_obj(with_points=True, with_normals=False, n_points=100)
        decimate_pc(vtk_obj, 2)

        printed = capsys.readouterr().out
        assert "Decimation factor to large, you can not decimate by a factor not in [0%:100%]" in printed

        vtk_obj.GetNumberOfPoints.assert_not_called()
        
    def test_decimated_pc_size(self):
        """
        Size of the decimated pc must be 
        size_orignial_pc * decimation_factor
        """        
        
        # vtk_obj = _make_vtk_obj(with_points=True, with_normals=False, n_points=100)
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
        
        # vtk_obj = _make_vtk_obj(with_points=True, with_normals=False, n_points=100)
        vtk_obj = PCDom()
        vtk_obj.points = np.random.choice(np.arange(0, 1000), size=(100, 3))
         
        decimated_pc = decimate_pc(vtk_obj, 0.5)
        
        assert set(decimated_pc.points[:, 0]).issubset(vtk_obj.points[:, 0])
        assert set(decimated_pc.points[:, 1]).issubset(vtk_obj.points[:, 1])

# class TestExtractPC: