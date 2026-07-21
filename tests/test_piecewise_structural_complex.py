from types import SimpleNamespace

import numpy as np

from pzero.pymeshit_app.PiecewiseStructuralComplex import PiecewiseStructuralComplex


def _controller():
    return PiecewiseStructuralComplex(SimpleNamespace(tetra_surface_data={}))


def _unit(key, feature, boundaries, point=None, signature_entry=None, **extra):
    unit = {
        "key": key,
        "name": feature,
        "feature": feature,
        "unit_role": "TMU",
        "polarity": 1,
        "boundaries": list(boundaries),
        "seed_points": [list(point)] if point is not None else [],
        "seed_point": list(point) if point is not None else None,
        "seed_topology_signatures": (
            [signature_entry] if signature_entry is not None else []
        ),
    }
    unit.update(extra)
    return unit


def _model(*units, representative_role="TMU"):
    return {
        "units": {unit["key"]: unit for unit in units},
        "boundary_order": [
            {
                "feature": "Rep",
                "unit_role": representative_role,
                "polarity": 1,
            }
        ],
        "boundary_features": {"Boundary", "Rep", "Other"},
    }


def test_partial_observation_stays_anchored_to_intended_3d_signature():
    controller = _controller()
    source = _unit(
        "unit:A",
        "A",
        ["Boundary", "A"],
        point=[0, 0, 0],
        signature_entry={
            "boundaries": ["Boundary", "A"],
            "signature": {
                "target": ["Boundary", "A"],
                "closest": ["Boundary", "Other"],
                "exact": False,
            },
        },
    )
    unrelated = _unit("unit:Other", "Other", ["Boundary", "Other"])

    payload = controller._psc_classify_seed_assignments(
        [source, unrelated],
        _model(source, unrelated),
        max_missing_boundaries=1,
    )[0]

    assert payload["unit_key"] == "unit:A"
    assert payload["status"] == "LIKELY"
    assert payload["missing_labels"] == ["A"]
    assert payload["extra_labels"] == ["Other"]


def test_mixed_surface_and_boundary_signature_keeps_boundary_as_missing_label():
    controller = _controller()
    source = _unit(
        "unit:A",
        "A",
        ["Boundary", "Rep"],
        point=[0, 0, 0],
        signature_entry={
            "boundaries": ["Boundary", "Rep"],
            "signature": {
                "target": ["Boundary", "Rep"],
                "closest": ["Rep"],
                "exact": False,
            },
        },
    )

    payload = controller._psc_classify_seed_assignments(
        [source],
        _model(source),
        max_missing_boundaries=1,
    )[0]

    assert payload["unit_key"] == "unit:A"
    assert payload["status"] == "LIKELY"
    assert payload["missing_labels"] == ["Boundary"]


def test_explicit_seed_override_is_pinned_to_its_source_unit():
    controller = _controller()
    first = _unit(
        "unit:A",
        "A",
        ["Boundary", "Rep"],
        point=[1, 2, 3],
        seed_override=True,
    )
    second = _unit("unit:B", "B", ["Boundary", "Rep"])

    payload = controller._psc_classify_seed_assignments(
        [first, second],
        _model(first, second),
        max_missing_boundaries=1,
    )[0]

    assert payload["unit_key"] == "unit:A"
    assert payload["status"] == "CERTAIN"
    assert payload["candidate_names"] == ["A"]
    assert first["seed_points"] == [[1.0, 2.0, 3.0]]
    assert second["seed_points"] == []


def test_swap_preserves_every_seed_in_both_selected_rows():
    controller = _controller()
    first = {"seed_points": [[1, 2, 3], [4, 5, 6]]}
    second = {"seed_points": [[7, 8, 9], [10, 11, 12]]}

    swapped = controller._psc_swapped_seed_points(first, second)

    assert swapped == (
        [[7.0, 8.0, 9.0], [10.0, 11.0, 12.0]],
        [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]],
    )


def test_local_signature_repeat_is_blocked_across_representative_surface():
    controller = _controller()
    controller._psc_closest_surface_indices_for_point = (
        lambda point, labels: {"rep": 5}
    )
    controller._psc_signed_distance_to_surface = (
        lambda point, surface_idx: float(point[0])
    )
    controller.host.tetra_surface_data = {
        5: {"feature": "Rep", "name": "Representative"}
    }
    local_signature = {
        "boundaries": ["Rep"],
        "component_index": 0,
        "signature": {
            "target": ["Rep"],
            "closest": ["Rep"],
            "exact": True,
            "closest_surface_indices": {"rep": 5},
        },
    }
    repeated = _unit(
        "unit:Repeated",
        "Repeated",
        ["Rep", "Other"],
        point=[-1, 0, 0],
    )
    repeated["seed_points"] = [[-1, 0, 0], [1, 0, 0]]
    repeated["seed_topology_signatures"] = [
        dict(local_signature),
        dict(local_signature),
    ]
    representative = _unit("unit:Rep", "Rep", ["Rep"])

    payloads = controller._psc_classify_seed_assignments(
        [repeated],
        _model(repeated, representative, representative_role="TMU"),
        max_missing_boundaries=1,
    )

    assert [payload["status"] for payload in payloads] == ["CERTAIN", "UNASSIGNED"]
    assert payloads[1]["blocked_repeat_labels"] == ["Rep"]


def test_local_signature_repeat_is_allowed_across_discontinuity():
    controller = _controller()
    controller._psc_closest_surface_indices_for_point = (
        lambda point, labels: {"rep": 5}
    )
    controller._psc_signed_distance_to_surface = (
        lambda point, surface_idx: float(point[0])
    )
    controller.host.tetra_surface_data = {
        5: {"feature": "Rep", "name": "Representative"}
    }
    local_signature = {
        "boundaries": ["Rep"],
        "component_index": 0,
        "signature": {
            "target": ["Rep"],
            "closest": ["Rep"],
            "exact": True,
            "closest_surface_indices": {"rep": 5},
        },
    }
    repeated = _unit(
        "unit:Repeated",
        "Repeated",
        ["Rep", "Other"],
        point=[-1, 0, 0],
    )
    repeated["seed_points"] = [[-1, 0, 0], [1, 0, 0]]
    repeated["seed_topology_signatures"] = [
        dict(local_signature),
        dict(local_signature),
    ]
    representative = _unit("unit:Rep", "Rep", ["Rep"])

    payloads = controller._psc_classify_seed_assignments(
        [repeated],
        _model(repeated, representative, representative_role="Discontinuity"),
        max_missing_boundaries=1,
    )

    assert [payload["status"] for payload in payloads] == [
        "CERTAIN",
        "POSSIBLE_REPEAT",
    ]


def _two_tetra_partition(controller, shared_marker=1):
    nodes = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [0.0, 0.0, -1.0],
        ]
    )
    elements = np.asarray([[0, 1, 2, 3], [0, 2, 1, 4]])
    trifaces = np.asarray(
        [
            [0, 1, 2],
            [1, 2, 3],
            [0, 2, 3],
            [0, 1, 3],
            [2, 1, 4],
            [0, 1, 4],
            [0, 2, 4],
        ]
    )
    markers = np.asarray([shared_marker, 2, 2, 2, 2, 2, 2])
    return controller._psc_regions_from_tetrahedra(
        nodes,
        elements,
        trifaces,
        markers,
        border_surface_indices={1},
    )


def test_volumetric_partition_splits_only_at_constrained_faces():
    controller = PiecewiseStructuralComplex(
        SimpleNamespace(
            tetra_surface_data={
                0: {"feature": "Rep"},
                1: {"feature": "Outer"},
            }
        )
    )

    split = _two_tetra_partition(controller, shared_marker=1)
    joined = _two_tetra_partition(controller, shared_marker=0)

    assert len(split["regions"]) == 2
    assert len(joined["regions"]) == 1
    assert split["regions"][0]["boundary_labels"] == ["Boundary", "Rep"]
    assert split["regions"][0]["adjacent_regions"][1][0]["label"] == "Rep"
    assert split["regions"][0]["seed_point"][2] > 0
    assert split["regions"][1]["seed_point"][2] < 0


def test_volumetric_assignment_blocks_equal_adjacent_units_on_representative_face():
    controller = PiecewiseStructuralComplex(
        SimpleNamespace(
            tetra_surface_data={
                0: {"feature": "Rep"},
                1: {"feature": "Outer"},
            }
        )
    )
    partition = _two_tetra_partition(controller, shared_marker=1)
    controller._psc_build_volumetric_regions = lambda model: partition
    unit = _unit("unit:A", "A", ["Boundary", "Rep"])
    representative = _unit("unit:Rep", "Rep", ["Rep"])

    payloads = controller._psc_assign_volumetric_regions(
        [unit],
        _model(unit, representative, representative_role="TMU"),
        max_missing_boundaries=1,
    )

    assert [payload["status"] for payload in payloads] == ["CERTAIN", "UNASSIGNED"]
    assert payloads[1]["blocked_repeat_labels"] == ["Rep"]
    assert len(unit["seed_points"]) == 1


def test_volumetric_assignment_allows_repeat_across_discontinuity():
    controller = PiecewiseStructuralComplex(
        SimpleNamespace(
            tetra_surface_data={
                0: {"feature": "Rep"},
                1: {"feature": "Outer"},
            }
        )
    )
    partition = _two_tetra_partition(controller, shared_marker=1)
    controller._psc_build_volumetric_regions = lambda model: partition
    unit = _unit("unit:A", "A", ["Boundary", "Rep"])
    representative = _unit("unit:Rep", "Rep", ["Rep"])

    payloads = controller._psc_assign_volumetric_regions(
        [unit],
        _model(unit, representative, representative_role="Discontinuity"),
        max_missing_boundaries=1,
    )

    assert [payload["status"] for payload in payloads] == [
        "CERTAIN",
        "POSSIBLE_REPEAT",
    ]
    assert len(unit["seed_points"]) == 2


def test_volumetric_assignment_accepts_one_extra_boundary_as_likely():
    controller = _controller()
    unit = _unit("unit:A", "A", ["Boundary", "Rep"])
    partition = {
        "regions": [
            {
                "region_id": 0,
                "seed_point": [0.0, 0.0, 0.0],
                "boundary_labels": ["Boundary", "Rep", "Extra"],
                "label_surface_indices": {},
                "adjacent_regions": {},
                "tetra_count": 1,
                "clearance": 1.0,
            }
        ],
        "tetra_to_region": np.asarray([0]),
    }
    controller._psc_build_volumetric_regions = lambda model: partition

    payload = controller._psc_assign_volumetric_regions(
        [unit],
        _model(unit),
        max_missing_boundaries=1,
    )[0]

    assert payload["status"] == "LIKELY"
    assert payload["extra_labels"] == ["Extra"]
    assert unit["seed_points"] == [[0.0, 0.0, 0.0]]


def test_volumetric_assignment_honours_swapped_seed_overrides():
    controller = PiecewiseStructuralComplex(
        SimpleNamespace(
            tetra_surface_data={
                0: {"feature": "Rep"},
                1: {"feature": "Outer"},
            }
        )
    )
    partition = _two_tetra_partition(controller, shared_marker=1)

    class RegionMesh:
        @staticmethod
        def find_containing_cell(point):
            return 0 if float(point[2]) > 0 else 1

    partition["mesh"] = RegionMesh()
    controller._psc_build_volumetric_regions = lambda model: partition
    first = _unit(
        "unit:A",
        "A",
        ["Boundary", "Rep"],
        point=[0.1, 0.1, -0.2],
        seed_override=True,
    )
    second = _unit(
        "unit:B",
        "B",
        ["Boundary", "Rep"],
        point=[0.1, 0.1, 0.2],
        seed_override=True,
    )
    representative = _unit("unit:Rep", "Rep", ["Rep"])

    payloads = controller._psc_assign_volumetric_regions(
        [first, second],
        _model(first, second, representative),
        max_missing_boundaries=1,
    )

    assert [payload["unit_key"] for payload in payloads] == ["unit:B", "unit:A"]
    assert first["seed_points"] == [[0.1, 0.1, -0.2]]
    assert second["seed_points"] == [[0.1, 0.1, 0.2]]
