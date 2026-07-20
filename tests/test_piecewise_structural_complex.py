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


def test_section_normal_candidates_preserve_section_coordinates():
    section_uid = "section-1"

    class Sections:
        get_uids = [section_uid]

        @staticmethod
        def get_uid_origin(uid=None):
            return [0, 0, 0]

        @staticmethod
        def get_uid_strike_vect(section_uid=None):
            return [0, 1, 0]

        @staticmethod
        def get_uid_dip_vect(section_uid=None):
            return [0, 0, 1]

        @staticmethod
        def get_uid_normal_vect(section_uid=None):
            return [1, 0, 0]

    project = SimpleNamespace(xsect_coll=Sections())
    host = SimpleNamespace(
        pzero_bridge=SimpleNamespace(_project=project),
        tetra_surface_data={
            0: {
                "vertices": np.asarray(
                    [[-10, -10, -10], [10, 10, 10]],
                    dtype=float,
                )
            }
        },
    )
    controller = PiecewiseStructuralComplex(host)

    points = controller._psc_section_normal_candidate_points(
        section_uid,
        section_seed_point=[0, 3, 4],
        calculated_seed=[7, -8, -9],
    )

    assert points.shape[0] > 2
    assert np.allclose(points[:, 1], 3)
    assert np.allclose(points[:, 2], 4)
    assert np.any(np.isclose(points[:, 0], 7))
    assert np.all(points[:, 0] >= -10)
    assert np.all(points[:, 0] <= 10)


def test_linked_seed_parent_resolves_to_real_section_uid():
    project = SimpleNamespace(
        xsect_coll=SimpleNamespace(get_uids=["section-1", "section-2"])
    )
    controller = PiecewiseStructuralComplex(
        SimpleNamespace(pzero_bridge=SimpleNamespace(_project=project))
    )

    section_uid = controller._psc_section_uid_from_candidates(
        ["section-1;linked-area", "invalid"]
    )

    assert section_uid == "section-1"


def test_section_guidance_keeps_only_one_seed_for_a_mapped_volume():
    controller = _controller()
    unit = _unit("unit:A", "A", ["Boundary", "Rep"])
    unit["section_seed_guides"] = [
        {
            "section_uid": "section-1",
            "seed_point": [0, 3, 4],
            "source_uid": "seed-1",
        }
    ]
    controller._psc_local_boundary_sets_for_unit = (
        lambda unit_info, mapped_units: [["Rep"]]
    )

    def calculated_seed(unit_info, model, require_side_match=False):
        is_local = unit_info.get("component_index") == 0
        unit_info["seed_topology_signature"] = {
            "target": list(unit_info["boundaries"]),
            "closest": list(unit_info["boundaries"]),
            "exact": True,
            "missing_count": 0,
            "extra_count": 0,
            "observed_count": len(unit_info["boundaries"]),
        }
        return [2 if is_local else 1, 9, 9]

    def guided_seed(unit_info, model, seed, require_side_match=False):
        signature = dict(unit_info["seed_topology_signature"])
        if unit_info.get("component_index") != 0:
            signature["section_guided"] = True
            unit_info["seed_topology_signature"] = signature
            return [1, 3, 4]
        return seed

    controller._psc_seed_point_for_unit = calculated_seed
    controller._psc_section_guided_seed_point_for_unit = guided_seed

    points = controller._psc_seed_points_for_unit(
        unit,
        {"units": {unit["key"]: unit}},
        [unit],
        max_missing_boundaries=1,
    )

    assert points == [[1.0, 3.0, 4.0]]
    assert len(unit["seed_topology_signatures"]) == 1
    assert unit["seed_topology_signatures"][0]["signature"]["section_guided"]
