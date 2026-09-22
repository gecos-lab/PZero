from pandas import DataFrame

from pzero.helpers.structural_topology import (
    calculate_stm_unit_levels,
    stm_boundary_level_col,
    stm_boundary_role_col,
    stm_conformable_boundaries_col,
    stm_feature_col,
    stm_level_col,
    stm_unconformable_boundaries_col,
    stm_unit_role_col,
)


def _boundary(feature, role, level):
    return {
        stm_feature_col: feature,
        stm_boundary_role_col: role,
        stm_boundary_level_col: level,
    }


def _unit(feature, conformable=None, unconformable=None, role="TU"):
    return {
        stm_feature_col: feature,
        stm_unit_role_col: role,
        stm_level_col: "",
        stm_unconformable_boundaries_col: list(unconformable or []),
        stm_conformable_boundaries_col: list(conformable or []),
    }


def test_unit_levels_use_full_topology_without_conformable_links():
    boundaries = DataFrame(
        [
            _boundary("combinf", "fault", 1),
            _boundary("mr-zs", "tectonic", 2),
            _boundary("mb-serp", "tectonic", 3),
            _boundary("Model Boundary", "model_boundary", "-inf"),
        ]
    )
    units = DataFrame(
        [
            _unit(
                "COMBIN",
                unconformable=["Model Boundary", "combinf"],
            ),
            _unit(
                "MR",
                conformable=["mr-zs"],
                unconformable=["Model Boundary"],
            ),
            _unit(
                "BM",
                conformable=["mb-serp"],
                unconformable=[
                    "Model Boundary",
                    "combinf",
                    "mr-zs",
                ],
            ),
            _unit(
                "SERP",
                conformable=["mb-serp"],
                unconformable=[
                    "Model Boundary",
                    "combinf",
                    "mr-zs",
                ],
            ),
        ]
    )

    result = calculate_stm_unit_levels(boundaries, units)

    assert result["unresolved_rows"] == {}
    assert result["levels_by_unit"]["COMBIN"] == 0.5
    assert result["levels_by_unit"]["MR"] == 1.5
    assert {
        result["levels_by_unit"]["BM"],
        result["levels_by_unit"]["SERP"],
    } == {2.5, 3.5}

    assert len(result["ambiguity_solutions"]) == 2
    assert all(
        set(solution) == {"BM", "SERP"} for solution in result["ambiguity_solutions"]
    )
    assert {solution["BM"]["value"] for solution in result["ambiguity_solutions"]} == {
        2.5,
        3.5,
    }


def test_locked_top_link_keeps_its_strong_side_constraint():
    boundaries = DataFrame(
        [
            _boundary("lower", "fault", 1),
            _boundary("unit-top", "top", 2),
            _boundary("upper", "fault", 3),
        ]
    )
    units = DataFrame([_unit("A", conformable=["unit-top"], role="SU")])

    result = calculate_stm_unit_levels(
        boundaries,
        units,
        locked_conformable_links=[("A", "unit-top")],
    )

    assert result["levels_by_unit"] == {"A": 2.5}
    assert result["ambiguity_solutions"] == []


def test_two_conformable_boundaries_define_the_unit_interval():
    boundaries = DataFrame(
        [
            _boundary("base", "base", 1),
            _boundary("top", "top", 3),
        ]
    )
    units = DataFrame([_unit("A", conformable=["base", "top"], role="SU")])

    result = calculate_stm_unit_levels(boundaries, units)

    assert result["levels_by_unit"] == {"A": 2.0}
    assert result["unresolved_rows"] == {}


def test_unit_without_any_numeric_link_remains_unresolved():
    boundaries = DataFrame([_boundary("Model Boundary", "model_boundary", "-inf")])
    units = DataFrame([_unit("A", unconformable=["Model Boundary"])])

    result = calculate_stm_unit_levels(boundaries, units)

    assert result["levels_by_unit"] == {}
    assert result["unresolved_rows"] == {0: "no_numeric_linked_boundary"}
