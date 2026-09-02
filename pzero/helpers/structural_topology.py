"""Schema, serialization, and calculation helpers for Structural Topology models."""

import json
import math
from hashlib import md5

from pandas import DataFrame, concat as pd_concat, isna as pd_isna
from PySide6.QtGui import QColor


stm_table_type = "stm"
stm_feature_col = "Feature"
stm_unit_role_col = "Unit Role"
stm_level_col = "Level"
stm_boundary_role_col = "Role"
stm_boundary_level_col = "Level"
stm_boundary_units_col = "Units"
stm_unconformable_boundaries_col = "Unconformable Boundaries"
stm_conformable_boundaries_col = "Conformable Boundaries"
stm_unit_level_col = "Level"
stm_model_boundary = "Model Boundary"
stm_color_cols = ("color_R", "color_G", "color_B")

stm_boundary_roles = [
    "top",
    "base",
    "fault",
    "intrusive",
    "tectonic",
    "unconformity",
    "model_boundary",
]
stm_boundary_cols = [
    stm_feature_col,
    stm_boundary_role_col,
    stm_boundary_level_col,
    stm_boundary_units_col,
]
stm_unit_cols = [
    stm_feature_col,
    stm_unit_role_col,
    stm_unit_level_col,
    stm_unconformable_boundaries_col,
    stm_conformable_boundaries_col,
    "Domain_1",
]
stm_base_cols = [
    stm_feature_col,
    stm_unit_role_col,
    stm_level_col,
    "Domain_1",
]
stm_protected_cols = {
    stm_feature_col,
    stm_unit_role_col,
    stm_level_col,
}
stm_export_marker_begin = "# PZERO_STM_EXPORT BEGIN"
stm_export_marker_end = "# PZERO_STM_EXPORT END"
stm_unit_roles = [
    "TU",
    "SU",
    "IU",
    "SD",
]
stm_non_boundary_roles = {"TU", "SU", "IU", "SD"}
stm_generated_unit_roles = {
    "top": "SU",
    "base": "SU",
    "bottom": "SU",
    "intrusive": "IU",
    "tectonic": "TU",
    "fault": "TU",
}

_unit_roles_by_case = {role.casefold(): role for role in stm_unit_roles}
_boundary_roles_by_case = {role.casefold(): role for role in stm_boundary_roles}


def stm_domain_col(order_value) -> str:
    """Return the canonical STm domain column name for an order value."""
    return f"Domain_{int(order_value)}"


def stm_domain_order(column_name: str):
    """Return the numeric order of a domain column, if any."""
    text = str(column_name or "").strip()
    if text == "Domain":
        return 1
    if not text.startswith("Domain_"):
        return None
    try:
        return int(text.split("_", 1)[1])
    except (IndexError, ValueError):
        return None


def normalise_stm_unit_role(raw_value):
    """Return a valid canonical Unit Role value."""
    value = str(raw_value or "").strip()
    return _unit_roles_by_case.get(value.casefold(), value or "TU")


def normalise_stm_boundary_role(raw_value):
    """Return a valid canonical boundary Role value."""
    value = str(raw_value or "").strip()
    value_key = value.casefold().replace(" ", "_")
    return _boundary_roles_by_case.get(value_key, value)


def is_stm_model_boundary(row) -> bool:
    """Return whether a boundary row represents the unique model boundary."""
    if row is None:
        return False
    feature_name = str(row.get(stm_feature_col, "")).strip()
    role_name = normalise_stm_boundary_role(row.get(stm_boundary_role_col, ""))
    return (
        role_name == "model_boundary"
        or feature_name.casefold() == stm_model_boundary.casefold()
    )


def stm_names(raw_value):
    """Return a stable list of names from JSON, lists, or comma-separated cells."""
    if raw_value is None or (
        not isinstance(raw_value, (list, tuple, set)) and pd_isna(raw_value)
    ):
        return []
    if isinstance(raw_value, (list, tuple, set)):
        values = raw_value
    else:
        text = str(raw_value).strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                decoded = json.loads(text)
                values = decoded if isinstance(decoded, list) else [text]
            except (TypeError, ValueError, json.JSONDecodeError):
                values = text.split(",")
        else:
            values = text.split(",")
    output = []
    for value in values:
        name = str(value or "").strip()
        if name and name not in output:
            output.append(name)
    return output


def stm_names_cell(raw_value):
    """Return the compact editable representation used by relation cells."""
    return ", ".join(stm_names(raw_value))


def stm_links(raw_links):
    """Return a stable set of ``(unit, boundary)`` links from dicts or pairs."""
    links = set()
    for link_info in raw_links or []:
        if isinstance(link_info, dict):
            unit_name = str(link_info.get("unit", "")).strip()
            boundary_name = str(link_info.get("boundary", "")).strip()
        else:
            try:
                unit_name = str(link_info[0]).strip()
                boundary_name = str(link_info[1]).strip()
            except (IndexError, TypeError):
                continue
        if unit_name and boundary_name:
            links.add((unit_name, boundary_name))
    return links


def stm_records(dataframe):
    """Return JSON-safe records, preserving relationship fields as real lists."""
    if dataframe is None:
        return []
    records = []
    for record in dataframe.where(dataframe.notna(), "").to_dict(orient="records"):
        out_record = {}
        for key, value in record.items():
            if key in (
                stm_boundary_units_col,
                stm_unconformable_boundaries_col,
                stm_conformable_boundaries_col,
            ):
                out_record[str(key)] = stm_names(value)
            else:
                out_record[str(key)] = value
        records.append(out_record)
    return records


def stm_records_with_colors(dataframe, feature_colors=None):
    """Return table records enriched with hidden RGB persistence fields."""
    feature_colors = feature_colors or {}
    records = stm_records(dataframe)
    for record in records:
        feature_name = str(record.get(stm_feature_col, "")).strip()
        if feature_name in feature_colors:
            record.update(stm_color_to_dict(feature_colors[feature_name]))
    return records


def normalise_stm_boundaries(dataframe=None):
    """Return the canonical STm Boundaries dataframe."""
    out_df = (
        dataframe.copy()
        if dataframe is not None
        else DataFrame(columns=stm_boundary_cols)
    )
    for column_name in stm_boundary_cols:
        if column_name not in out_df.columns:
            out_df[column_name] = ""
    out_df = out_df[stm_boundary_cols].copy()
    for row_label in out_df.index.tolist():
        out_df.at[row_label, stm_boundary_role_col] = normalise_stm_boundary_role(
            out_df.at[row_label, stm_boundary_role_col]
        )
        out_df.at[row_label, stm_boundary_units_col] = stm_names_cell(
            out_df.at[row_label, stm_boundary_units_col]
        )
    model_mask = out_df.apply(is_stm_model_boundary, axis=1)
    if model_mask.any():
        first_model_row = out_df.loc[model_mask].iloc[0].to_dict()
        model_units = []
        for raw_units in out_df.loc[model_mask, stm_boundary_units_col]:
            model_units.extend(stm_names(raw_units))
        out_df = out_df.loc[~model_mask].copy()
        feature_name = str(first_model_row.get(stm_feature_col, "")).strip()
        if not feature_name or feature_name.casefold() == stm_model_boundary.casefold():
            feature_name = stm_model_boundary
        first_model_row[stm_feature_col] = feature_name
        first_model_row[stm_boundary_role_col] = "model_boundary"
        first_model_row[stm_boundary_level_col] = "-inf"
        first_model_row[stm_boundary_units_col] = stm_names_cell(model_units)
        out_df = pd_concat(
            [DataFrame([first_model_row], columns=out_df.columns), out_df],
            ignore_index=True,
        )
    return out_df.reset_index(drop=True)


def normalise_stm_units(dataframe=None):
    """Return the canonical STm Units dataframe."""
    out_df = (
        dataframe.copy()
        if dataframe is not None
        else DataFrame(columns=stm_unit_cols)
    )
    if "Domain" in out_df.columns and "Domain_1" not in out_df.columns:
        out_df.rename(columns={"Domain": "Domain_1"}, inplace=True)
    out_df.drop(
        columns=[
            column_name
            for column_name in stm_color_cols
            if column_name in out_df.columns
        ],
        inplace=True,
    )
    for column_name in stm_unit_cols:
        if column_name not in out_df.columns:
            out_df[column_name] = ""
    for row_label in out_df.index.tolist():
        out_df.at[row_label, stm_unit_role_col] = normalise_stm_unit_role(
            out_df.at[row_label, stm_unit_role_col]
        )
        out_df.at[row_label, stm_unconformable_boundaries_col] = stm_names_cell(
            out_df.at[row_label, stm_unconformable_boundaries_col]
        )
        out_df.at[row_label, stm_conformable_boundaries_col] = stm_names_cell(
            out_df.at[row_label, stm_conformable_boundaries_col]
        )
    domain_columns = sorted(
        [
            column_name
            for column_name in out_df.columns
            if stm_domain_order(column_name) is not None
        ],
        key=stm_domain_order,
    )
    if not domain_columns:
        out_df["Domain_1"] = ""
        domain_columns = ["Domain_1"]
    extra_columns = [
        column_name
        for column_name in out_df.columns
        if column_name
        not in (
            [
                stm_feature_col,
                stm_unit_role_col,
                stm_unit_level_col,
                stm_unconformable_boundaries_col,
                stm_conformable_boundaries_col,
            ]
            + domain_columns
        )
    ]
    ordered_columns = [
        stm_feature_col,
        stm_unit_role_col,
        stm_unit_level_col,
        stm_unconformable_boundaries_col,
        stm_conformable_boundaries_col,
    ] + domain_columns + extra_columns
    return out_df[ordered_columns].reset_index(drop=True)


def stm_model_boundary_name(boundaries=None):
    """Return the feature name of the optional model boundary."""
    if boundaries is None:
        return ""
    for _, row in boundaries.iterrows():
        if is_stm_model_boundary(row):
            return str(row.get(stm_feature_col, "")).strip()
    return ""


def reconcile_stm_relationships(
    boundaries,
    units,
    conformable_links=None,
    unconformable_links=None,
    locked_conformable_links=None,
):
    """Refresh reciprocal relation columns from typed STm links."""
    boundaries = normalise_stm_boundaries(boundaries)
    units = normalise_stm_units(units)
    boundary_names = {
        str(value).strip()
        for value in boundaries[stm_feature_col]
        if str(value).strip()
    }
    unit_names = {
        str(value).strip()
        for value in units[stm_feature_col]
        if str(value).strip()
    }
    conformable_links = {
        link
        for link in stm_links(conformable_links)
        if link[0] in unit_names and link[1] in boundary_names
    }
    locked_conformable_links = {
        link
        for link in stm_links(locked_conformable_links)
        if link in conformable_links
    }
    unconformable_links = {
        link
        for link in stm_links(unconformable_links)
        if link[0] in unit_names
        and link[1] in boundary_names
        and link not in conformable_links
    }
    links = conformable_links | unconformable_links
    for row_label in boundaries.index:
        boundary_name = str(boundaries.at[row_label, stm_feature_col]).strip()
        boundaries.at[row_label, stm_boundary_units_col] = stm_names_cell(
            [
                unit_name
                for unit_name, linked_boundary in sorted(links)
                if linked_boundary == boundary_name
            ]
        )
    for row_label in units.index:
        unit_name = str(units.at[row_label, stm_feature_col]).strip()
        units.at[row_label, stm_unconformable_boundaries_col] = stm_names_cell(
            [
                boundary_name
                for linked_unit, boundary_name in sorted(unconformable_links)
                if linked_unit == unit_name
            ]
        )
        units.at[row_label, stm_conformable_boundaries_col] = stm_names_cell(
            [
                boundary_name
                for linked_unit, boundary_name in sorted(conformable_links)
                if linked_unit == unit_name
            ]
        )
    return (
        boundaries,
        units,
        conformable_links,
        unconformable_links,
        locked_conformable_links,
    )


def stm_feature_colors_from_options(options):
    """Return persistent STm feature colours from table options."""
    color_codes = dict(options or {}).get("stm_color_codes", {})
    if not isinstance(color_codes, dict):
        return {}
    return {
        str(feature_name).strip(): stm_color_to_dict(color_info)
        for feature_name, color_info in color_codes.get("features", {}).items()
        if str(feature_name).strip()
    }


def stm_unit_feature_counts(units):
    """Return unit Feature occurrence counts."""
    units_df = _as_dataframe(units)
    counts = {}
    for value in units_df.get(stm_feature_col, []):
        unit_name = _stm_text(value)
        if unit_name:
            counts[unit_name] = counts.get(unit_name, 0) + 1
    return counts


def normalise_stm_level_overrides(options, units):
    """Return numeric user-defined unit-level overrides still matching units."""
    unit_names = {
        _stm_text(value)
        for value in _as_dataframe(units).get(stm_feature_col, [])
        if _stm_text(value)
    }
    overrides = {}
    for unit_name, value in dict(
        dict(options or {}).get("stm_unit_level_overrides", {}) or {}
    ).items():
        unit_name = _stm_text(unit_name)
        if unit_name not in unit_names:
            continue
        level_value = _stm_numeric_level(value)
        if level_value is not None:
            overrides[unit_name] = level_value
    return overrides


def apply_stm_level_overrides(units, overrides, row_labels=None):
    """Apply user-defined unit-level overrides to selected rows."""
    units_df = units.copy()
    row_labels = set(units_df.index) if row_labels is None else set(row_labels)
    applied_rows = set()
    for row_label in row_labels:
        if row_label not in units_df.index:
            continue
        unit_name = _stm_text(units_df.at[row_label, stm_feature_col])
        if unit_name in overrides:
            units_df.at[row_label, stm_unit_level_col] = overrides[unit_name]
            applied_rows.add(row_label)
    return units_df, applied_rows


def stm_level_overrides_for_rows(options, units, row_labels):
    """Keep stored overrides only for the requested unit rows."""
    units_df = _as_dataframe(units)
    row_labels = set(row_labels or [])
    keep_names = {
        _stm_text(units_df.at[row_label, stm_feature_col])
        for row_label in row_labels
        if row_label in units_df.index
        and _stm_text(units_df.at[row_label, stm_feature_col])
    }
    return {
        unit_name: level_value
        for unit_name, level_value in normalise_stm_level_overrides(
            options, units_df
        ).items()
        if unit_name in keep_names
    }


def stm_level_diagnostic_messages(diagnostics, severities=None, limit=8):
    """Return compact user-facing diagnostic messages."""
    severities = set(severities or [])
    messages = []
    for diagnostic in diagnostics or []:
        if severities and diagnostic.get("severity") not in severities:
            continue
        message = str(diagnostic.get("message", "")).strip()
        if message and message not in messages:
            messages.append(message)
    if len(messages) > limit:
        omitted = len(messages) - limit
        messages = messages[:limit] + [f"...and {omitted} more."]
    return messages


def stm_sort_key(raw_value):
    """Return a sortable numeric level value."""
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return float("inf")


def _stm_text(raw_value):
    """Return a compact string, treating pandas null-like values as empty."""
    if raw_value is None:
        return ""
    if not isinstance(raw_value, (list, tuple, set, dict)):
        try:
            if pd_isna(raw_value):
                return ""
        except (TypeError, ValueError):
            pass
    text = str(raw_value).strip()
    return "" if text.casefold() in {"nan", "nat", "<na>", "none"} else text


def _stm_numeric_level(raw_value):
    """Return a finite or infinite numeric level, or None when not numeric."""
    text = _stm_text(raw_value)
    if not text:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _stm_relation_links_from_units(units_df, column_name):
    links = set()
    if column_name not in units_df.columns:
        return links
    for _, row in units_df.iterrows():
        unit_name = _stm_text(row.get(stm_feature_col, ""))
        if not unit_name:
            continue
        for boundary_name in stm_names(row.get(column_name, "")):
            links.add((unit_name, boundary_name))
    return links


def _stm_structural_level_context(boundaries, units):
    boundaries_df = _as_dataframe(boundaries)
    units_df = _as_dataframe(units)
    diagnostics = []
    boundary_names = set()
    boundary_levels = {}
    boundary_roles = {}
    finite_level_boundaries = {}
    for _, row in boundaries_df.iterrows():
        boundary_name = _stm_text(row.get(stm_feature_col, ""))
        if not boundary_name:
            continue
        boundary_names.add(boundary_name)
        boundary_roles[boundary_name] = normalise_stm_boundary_role(
            row.get(stm_boundary_role_col, "")
        )
        if is_stm_model_boundary(row):
            continue
        level = _stm_numeric_level(row.get(stm_boundary_level_col, ""))
        if level is None:
            continue
        boundary_levels[boundary_name] = level
        if math.isfinite(level):
            finite_level_boundaries.setdefault(level, []).append(boundary_name)

    # Duplicate finite boundary levels are blocked during calculation for now.
    # A stricter validation step could later prevent them at edit/import time.
    for level, names in sorted(finite_level_boundaries.items()):
        if len(names) > 1:
            diagnostics.append(
                {
                    "severity": "error",
                    "code": "duplicate_boundary_levels",
                    "level": level,
                    "boundaries": sorted(names),
                    "message": (
                        f"Boundary Level {level:g} is used by "
                        f"{', '.join(sorted(names))}."
                    ),
                }
            )

    unit_rows = []
    unit_name_counts = {}
    for row_order, (row_label, row) in enumerate(units_df.iterrows()):
        unit_name = _stm_text(row.get(stm_feature_col, ""))
        if not unit_name:
            continue
        unit_rows.append(
            {
                "row_label": row_label,
                "row_order": row_order,
                "name": unit_name,
                "role": normalise_stm_unit_role(
                    row.get(stm_unit_role_col, "TU")
                ).upper(),
            }
        )
        unit_name_counts[unit_name] = unit_name_counts.get(unit_name, 0) + 1

    duplicate_unit_names = {
        name for name, count in unit_name_counts.items() if count > 1
    }
    for unit_name in sorted(duplicate_unit_names):
        diagnostics.append(
            {
                "severity": "warning",
                "code": "duplicate_unit_feature",
                "unit": unit_name,
                "message": (
                    f'Unit Feature "{unit_name}" is used by '
                    f"{unit_name_counts[unit_name]} rows."
                ),
            }
        )

    unit_names = {item["name"] for item in unit_rows}
    conformable_links = (
        stm_links([])
        | _stm_relation_links_from_units(units_df, stm_conformable_boundaries_col)
    )
    unconformable_links = (
        stm_links([])
        | _stm_relation_links_from_units(units_df, stm_unconformable_boundaries_col)
    )
    return {
        "boundaries_df": boundaries_df,
        "units_df": units_df,
        "diagnostics": diagnostics,
        "boundary_names": boundary_names,
        "boundary_levels": boundary_levels,
        "boundary_roles": boundary_roles,
        "unit_rows": unit_rows,
        "unit_names": unit_names,
        "duplicate_unit_names": duplicate_unit_names,
        "conformable_links": conformable_links,
        "unconformable_links": unconformable_links,
    }


def stm_structural_level_preflight(boundaries, units):
    """Return diagnostics that should be shown before calculating unit levels."""
    return list(
        _stm_structural_level_context(boundaries, units).get("diagnostics", [])
    )


def _stm_preferred_side(unit_role, boundary_role):
    """Return a weak side hint from role names when topology cannot decide."""
    if str(unit_role).upper() != "SU":
        return None
    role_key = str(boundary_role or "").strip().casefold()
    if role_key == "top":
        return "above"
    if role_key in {"base", "bottom"}:
        return "below"
    return None


def _stm_interval_from_anchor_side(anchor_level, side, finite_levels):
    """Return a finite interval on one side of an anchor level."""
    if side == "above":
        upper_candidates = [
            level for level in finite_levels if level > anchor_level
        ]
        upper = min(upper_candidates) if upper_candidates else anchor_level + 1.0
        return anchor_level, upper
    lower_candidates = [
        level for level in finite_levels if level < anchor_level
    ]
    lower = max(lower_candidates) if lower_candidates else anchor_level - 1.0
    return lower, anchor_level


def _stm_candidate(lower, upper, source, score, **metadata):
    value = metadata.pop("value", (lower + upper) / 2.0)
    candidate = {
        "lower": lower,
        "upper": upper,
        "value": value,
        "source": source,
        "score": score,
    }
    candidate.update(metadata)
    return candidate


def _stm_intrusive_anchor_candidate(
    unit_name,
    intrusive_links,
    conformable_intrusive_links,
    boundary_levels,
    finite_levels,
):
    """Return the IU candidate implied by one main intrusive contact."""
    main_contacts = (
        conformable_intrusive_links
        if conformable_intrusive_links
        else intrusive_links
    )
    numeric_contacts = [
        (boundary_name, boundary_levels[boundary_name])
        for boundary_name in sorted(main_contacts)
        if boundary_name in boundary_levels
        and math.isfinite(boundary_levels[boundary_name])
    ]
    if len(numeric_contacts) != 1:
        return None
    anchor_name, anchor_level = numeric_contacts[0]
    lower, upper = _stm_interval_from_anchor_side(
        anchor_level, "below", finite_levels
    )
    gap = upper - lower
    value = anchor_level - gap * 0.1
    if not lower < value < upper:
        value = (lower + upper) / 2.0
    return _stm_candidate(
        lower,
        upper,
        "intrusive-anchor",
        120,
        value=value,
        unit=unit_name,
        side="below",
        anchor=anchor_name,
        endpoint_boundaries={anchor_name},
    )


def _stm_single_conformable_candidates(
    unit_name,
    unit_role,
    anchor_name,
    anchor_level,
    linked_boundaries,
    boundary_levels,
    boundary_roles,
    finite_levels,
):
    side_candidates = {}
    for boundary_name in linked_boundaries:
        if boundary_name == anchor_name or boundary_name not in boundary_levels:
            continue
        linked_level = boundary_levels[boundary_name]
        if linked_level == anchor_level or not math.isfinite(linked_level):
            continue
        side = "above" if linked_level > anchor_level else "below"
        lower, upper = sorted((anchor_level, linked_level))
        existing = side_candidates.get(side)
        is_nearer = (
            existing is None
            or (
                side == "above"
                and linked_level < existing["opposite_level"]
            )
            or (
                side == "below"
                and linked_level > existing["opposite_level"]
            )
        )
        if is_nearer:
            side_candidates[side] = _stm_candidate(
                lower,
                upper,
                "topological-signature",
                20,
                unit=unit_name,
                side=side,
                anchor=anchor_name,
                opposite=boundary_name,
                opposite_level=linked_level,
                endpoint_boundaries={anchor_name, boundary_name},
            )

    preferred_side = _stm_preferred_side(
        unit_role, boundary_roles.get(anchor_name, "")
    )
    if preferred_side:
        if preferred_side in side_candidates:
            side_candidates[preferred_side]["score"] += 5
            side_candidates[preferred_side]["source"] = (
                f"{side_candidates[preferred_side]['source']}+role"
            )
        else:
            lower, upper = _stm_interval_from_anchor_side(
                anchor_level, preferred_side, finite_levels
            )
            side_candidates[preferred_side] = _stm_candidate(
                lower,
                upper,
                "role-hint",
                5,
                unit=unit_name,
                side=preferred_side,
                anchor=anchor_name,
                endpoint_boundaries={anchor_name},
            )

    if not side_candidates:
        for side in ("below", "above"):
            lower, upper = _stm_interval_from_anchor_side(
                anchor_level, side, finite_levels
            )
            side_candidates[side] = _stm_candidate(
                lower,
                upper,
                "ambiguous-side",
                0,
                unit=unit_name,
                side=side,
                anchor=anchor_name,
                endpoint_boundaries={anchor_name},
            )
    return list(side_candidates.values())


def _stm_interval_split_allowed(
    interval_units,
    candidates,
    unit_info_by_name,
    links_by_unit,
    boundary_levels,
):
    has_intrusive = any(
        unit_info_by_name[unit_name]["role"] == "IU"
        for unit_name in interval_units
    )
    return has_intrusive


def _stm_interval_conflict_count(
    assignment,
    unit_info_by_name,
    links_by_unit,
    boundary_levels,
):
    conflicts = 0
    units_by_interval = {}
    for unit_name, candidate in assignment.items():
        units_by_interval.setdefault(
            (candidate["lower"], candidate["upper"]), []
        ).append(unit_name)
    for interval_units in units_by_interval.values():
        if len(interval_units) <= 1:
            continue
        if not _stm_interval_split_allowed(
            interval_units,
            assignment,
            unit_info_by_name,
            links_by_unit,
            boundary_levels,
        ):
            conflicts += len(interval_units)
    return conflicts


def _stm_resolve_candidate_options(
    candidate_options_by_unit,
    unit_info_by_name,
    links_by_unit,
    boundary_levels,
):
    """Return the best side/interval combinations for calculable units."""
    unit_names = tuple(
        sorted(
            candidate_options_by_unit,
            key=lambda name: (
                len(candidate_options_by_unit[name]),
                unit_info_by_name[name]["row_order"],
                name,
            ),
        )
    )
    if not unit_names:
        return []
    combination_count = 1
    for unit_name in unit_names:
        combination_count *= max(1, len(candidate_options_by_unit[unit_name]))
        if combination_count > 200000:
            return [
                {
                    name: dict(
                        sorted(
                            candidate_options_by_unit[name],
                            key=lambda item: (item["score"], item["value"]),
                            reverse=True,
                        )[0]
                    )
                    for name in unit_names
                }
            ]
    best_score = None
    best_assignments = []

    def visit(index, assignment):
        nonlocal best_score, best_assignments
        if index == len(unit_names):
            conflict_count = _stm_interval_conflict_count(
                assignment,
                unit_info_by_name,
                links_by_unit,
                boundary_levels,
            )
            score = (
                -conflict_count,
                sum(candidate["score"] for candidate in assignment.values()),
                sum(candidate["value"] for candidate in assignment.values()),
            )
            if best_score is None or score > best_score:
                best_score = score
                best_assignments = [
                    {
                        unit_name: dict(candidate)
                        for unit_name, candidate in assignment.items()
                    }
                ]
            elif score == best_score and len(best_assignments) < 2:
                best_assignments.append(
                    {
                        unit_name: dict(candidate)
                        for unit_name, candidate in assignment.items()
                    }
                )
            return
        unit_name = unit_names[index]
        for candidate in sorted(
            candidate_options_by_unit[unit_name],
            key=lambda item: (item["score"], item["value"]),
            reverse=True,
        ):
            assignment[unit_name] = candidate
            visit(index + 1, assignment)
            assignment.pop(unit_name, None)

    visit(0, {})
    return best_assignments


def _stm_has_internal_separator(
    unit_names,
    candidates,
    links_by_unit,
    boundary_levels,
):
    if not unit_names:
        return False
    lower = candidates[unit_names[0]]["lower"]
    upper = candidates[unit_names[0]]["upper"]
    endpoint_boundaries = set()
    for unit_name in unit_names:
        endpoint_boundaries.update(
            candidates[unit_name].get("endpoint_boundaries", set())
        )
    internal_units_by_boundary = {}
    for unit_name in unit_names:
        for boundary_name in links_by_unit.get(unit_name, set()):
            if boundary_name in endpoint_boundaries:
                continue
            level = boundary_levels.get(boundary_name)
            if level is not None and math.isfinite(level):
                if not lower < level < upper:
                    continue
            internal_units_by_boundary.setdefault(boundary_name, set()).add(
                unit_name
            )
    shared_internal = [
        boundary_name
        for boundary_name, linked_units in internal_units_by_boundary.items()
        if len(linked_units) >= 2
    ]
    return len(shared_internal) >= max(1, len(unit_names) - 1)


def _stm_distribute_interval(lower, upper, count):
    step = (upper - lower) / (count + 1)
    return [lower + step * (index + 1) for index in range(count)]


def calculate_stm_unit_levels(
    boundaries,
    units,
    conformable_links=None,
    unconformable_links=None,
):
    """Calculate STm unit levels from conformable topology.

    Unit features are still the graph keys. If duplicated unit Feature values
    become first-class objects, this helper should move to stable row/object IDs.
    """
    context = _stm_structural_level_context(boundaries, units)
    diagnostics = list(context["diagnostics"])
    result = {
        "levels_by_row": {},
        "levels_by_unit": {},
        "unresolved_rows": {},
        "diagnostics": diagnostics,
        "candidates_by_unit": {},
        "ambiguity_solutions": [],
    }
    if any(
        diagnostic.get("severity") == "error"
        for diagnostic in diagnostics
    ):
        return result

    boundary_names = context["boundary_names"]
    boundary_levels = context["boundary_levels"]
    boundary_roles = context["boundary_roles"]
    unit_names = context["unit_names"]
    duplicate_unit_names = context["duplicate_unit_names"]
    finite_levels = sorted(
        level for level in boundary_levels.values() if math.isfinite(level)
    )
    conformable = (
        context["conformable_links"] | stm_links(conformable_links)
    )
    unconformable = (
        context["unconformable_links"] | stm_links(unconformable_links)
    )
    conformable = {
        link
        for link in conformable
        if link[0] in unit_names and link[1] in boundary_names
    }
    unconformable = {
        link
        for link in unconformable
        if link[0] in unit_names
        and link[1] in boundary_names
        and link not in conformable
    }
    conformable_by_unit = {}
    links_by_unit = {}
    for unit_name, boundary_name in conformable:
        conformable_by_unit.setdefault(unit_name, set()).add(boundary_name)
        links_by_unit.setdefault(unit_name, set()).add(boundary_name)
    for unit_name, boundary_name in unconformable:
        links_by_unit.setdefault(unit_name, set()).add(boundary_name)

    unit_info_by_name = {
        item["name"]: item
        for item in context["unit_rows"]
        if item["name"] not in duplicate_unit_names
    }
    candidate_options_by_unit = {}
    for unit_name, unit_info in unit_info_by_name.items():
        conformable_boundaries = sorted(conformable_by_unit.get(unit_name, set()))
        linked_boundaries = set(links_by_unit.get(unit_name, set()))
        intrusive_links = {
            boundary_name
            for boundary_name in linked_boundaries
            if str(boundary_roles.get(boundary_name, "")).casefold()
            == "intrusive"
        }
        conformable_intrusive_links = intrusive_links & set(conformable_boundaries)
        if unit_info["role"] == "IU" and intrusive_links:
            intrusive_candidate = _stm_intrusive_anchor_candidate(
                unit_name,
                intrusive_links,
                conformable_intrusive_links,
                boundary_levels,
                finite_levels,
            )
            if intrusive_candidate is not None:
                result["candidates_by_unit"][unit_name] = [intrusive_candidate]
                candidate_options_by_unit[unit_name] = [intrusive_candidate]
                continue
            main_contacts = (
                conformable_intrusive_links
                if conformable_intrusive_links
                else intrusive_links
            )
            intrusive_candidates = []
            for anchor_name in sorted(main_contacts):
                anchor_level = boundary_levels.get(anchor_name)
                if anchor_level is None or not math.isfinite(anchor_level):
                    continue
                intrusive_candidates.extend(
                    _stm_single_conformable_candidates(
                        unit_name,
                        unit_info["role"],
                        anchor_name,
                        anchor_level,
                        linked_boundaries,
                        boundary_levels,
                        boundary_roles,
                        finite_levels,
                    )
                )
            if intrusive_candidates:
                max_score = max(
                    candidate["score"] for candidate in intrusive_candidates
                )
                best_candidates = [
                    candidate
                    for candidate in intrusive_candidates
                    if candidate["score"] == max_score
                ]
                best_intervals = {
                    (candidate["lower"], candidate["upper"])
                    for candidate in best_candidates
                }
                best_anchors = {
                    candidate.get("anchor")
                    for candidate in best_candidates
                    if candidate.get("anchor")
                }
                if (
                    max_score <= 0
                    or len(best_intervals) > 1
                    or len(best_anchors) > 1
                ):
                    result["unresolved_rows"][unit_info["row_label"]] = (
                        "ambiguous_intrusive_contacts"
                    )
                    diagnostics.append(
                        {
                            "severity": "warning",
                            "code": "ambiguous_intrusive_contacts",
                            "unit": unit_name,
                            "message": (
                                f'Intrusive unit "{unit_name}" has no unique '
                                "main intrusive contact."
                            ),
                        }
                    )
                    continue
                result["candidates_by_unit"][unit_name] = intrusive_candidates
                candidate_options_by_unit[unit_name] = intrusive_candidates
                continue
        numeric_conformables = [
            (boundary_name, boundary_levels[boundary_name])
            for boundary_name in conformable_boundaries
            if boundary_name in boundary_levels
            and math.isfinite(boundary_levels[boundary_name])
        ]
        if not conformable_boundaries:
            result["unresolved_rows"][unit_info["row_label"]] = (
                "no_conformable_boundary"
            )
            diagnostics.append(
                {
                    "severity": "info",
                    "code": "no_conformable_boundary",
                    "unit": unit_name,
                    "message": (
                        f'Unit "{unit_name}" has no conformable boundary.'
                    ),
                }
            )
            continue
        if not numeric_conformables:
            result["unresolved_rows"][unit_info["row_label"]] = (
                "no_numeric_conformable_boundary"
            )
            diagnostics.append(
                {
                    "severity": "warning",
                    "code": "no_numeric_conformable_boundary",
                    "unit": unit_name,
                    "message": (
                        f'Unit "{unit_name}" has conformable boundaries '
                        "without numeric Level values."
                    ),
                }
            )
            continue
        if len(numeric_conformables) < len(conformable_boundaries):
            diagnostics.append(
                {
                    "severity": "warning",
                    "code": "partial_numeric_conformable_boundaries",
                    "unit": unit_name,
                    "message": (
                        f'Unit "{unit_name}" has conformable boundaries '
                        "without numeric Level values; they were ignored."
                    ),
                }
            )

        if len(numeric_conformables) >= 2:
            numeric_conformables = sorted(
                numeric_conformables, key=lambda item: item[1]
            )
            if len(numeric_conformables) > 2:
                diagnostics.append(
                    {
                        "severity": "warning",
                        "code": "multiple_conformable_boundaries",
                        "unit": unit_name,
                        "message": (
                            f'Unit "{unit_name}" has more than two '
                            "numeric conformable boundaries; the outer span "
                            "was used."
                        ),
                    }
                )
            lower_name, lower = numeric_conformables[0]
            upper_name, upper = numeric_conformables[-1]
            candidate = _stm_candidate(
                lower,
                upper,
                "conformable-span",
                100,
                unit=unit_name,
                endpoint_boundaries={lower_name, upper_name},
            )
            result["candidates_by_unit"][unit_name] = [candidate]
            candidate_options_by_unit[unit_name] = [candidate]
            continue

        anchor_name, anchor_level = numeric_conformables[0]
        candidates = _stm_single_conformable_candidates(
            unit_name,
            unit_info["role"],
            anchor_name,
            anchor_level,
            linked_boundaries,
            boundary_levels,
            boundary_roles,
            finite_levels,
        )
        result["candidates_by_unit"][unit_name] = candidates
        candidate_options_by_unit[unit_name] = candidates

    for item in context["unit_rows"]:
        if item["name"] in duplicate_unit_names:
            result["unresolved_rows"][item["row_label"]] = (
                "duplicate_unit_feature"
            )

    best_solutions = _stm_resolve_candidate_options(
        candidate_options_by_unit,
        unit_info_by_name,
        links_by_unit,
        boundary_levels,
    )
    selected_candidates = best_solutions[0] if best_solutions else {}
    if len(best_solutions) > 1:
        result["ambiguity_solutions"] = [
            {
                unit_name: {
                    "row_label": unit_info_by_name[unit_name]["row_label"],
                    "value": candidate["value"],
                    "source": candidate.get("source", ""),
                    "lower": candidate.get("lower"),
                    "upper": candidate.get("upper"),
                }
                for unit_name, candidate in solution.items()
            }
            for solution in best_solutions[:2]
        ]
        diagnostics.append(
            {
                "severity": "warning",
                "code": "ambiguous_topological_assignment",
                "units": sorted(best_solutions[0]),
                "message": (
                    "Equivalent STm level assignments are available; "
                    "choose one before applying the result."
                ),
            }
        )

    units_by_interval = {}
    for unit_name, candidate in selected_candidates.items():
        units_by_interval.setdefault(
            (candidate["lower"], candidate["upper"]), []
        ).append(unit_name)

    for interval, interval_units in units_by_interval.items():
        if len(interval_units) <= 1:
            continue
        lower, upper = interval
        has_intrusive = any(
            unit_info_by_name[unit_name]["role"] == "IU"
            for unit_name in interval_units
        )
        has_separator = _stm_has_internal_separator(
            interval_units,
            selected_candidates,
            links_by_unit,
            boundary_levels,
        )
        if has_intrusive or has_separator:
            ordered_units = sorted(
                interval_units,
                key=lambda name: (
                    unit_info_by_name[name]["row_order"],
                    name,
                ),
            )
            existing_values = [
                selected_candidates[unit_name]["value"]
                for unit_name in ordered_units
            ]
            if len({round(value, 9) for value in existing_values}) != len(
                existing_values
            ):
                split_values = _stm_distribute_interval(
                    lower, upper, len(ordered_units)
                )
                for unit_name, value in zip(ordered_units, split_values):
                    selected_candidates[unit_name]["value"] = value
                    selected_candidates[unit_name]["source"] = (
                        f"{selected_candidates[unit_name]['source']}+split"
                    )
            diagnostics.append(
                {
                    "severity": "warning",
                    "code": (
                        "intrusive_interval_split"
                        if has_intrusive
                        else "internal_separator_interval_split"
                    ),
                    "units": ordered_units,
                    "message": (
                        "Multiple units fall in the same structural interval; "
                        "partial levels were assigned by table order."
                    ),
                }
            )
            continue

        for unit_name in interval_units:
            unit_info = unit_info_by_name[unit_name]
            result["unresolved_rows"][unit_info["row_label"]] = (
                "shared_interval_without_separator"
            )
            selected_candidates.pop(unit_name, None)
        diagnostics.append(
            {
                "severity": "warning",
                "code": "shared_interval_without_separator",
                "units": sorted(interval_units),
                "message": (
                    "Multiple non-intrusive units fall in the same structural "
                    "interval without an internal separator."
                ),
            }
        )

    for unit_name, candidate in selected_candidates.items():
        unit_info = unit_info_by_name[unit_name]
        value = candidate["value"]
        result["levels_by_row"][unit_info["row_label"]] = value
        result["levels_by_unit"][unit_name] = value
    return result


def stm_color(raw_key):
    """Return a stable pastel color for STm nodes/links."""
    key_text = str(raw_key or "").encode("utf-8", errors="ignore")
    digest = md5(key_text).hexdigest()
    hue = int(digest[:4], 16) % 360
    return QColor.fromHsv(hue, 80, 245)


def stm_color_to_dict(color_value):
    """Return a serialisable RGB payload for a QColor-like value."""
    if isinstance(color_value, QColor):
        return {
            "color_R": int(color_value.red()),
            "color_G": int(color_value.green()),
            "color_B": int(color_value.blue()),
        }
    if isinstance(color_value, dict):
        try:
            return {
                "color_R": int(float(color_value.get("color_R", 255))),
                "color_G": int(float(color_value.get("color_G", 255))),
                "color_B": int(float(color_value.get("color_B", 255))),
            }
        except (TypeError, ValueError):
            return {"color_R": 255, "color_G": 255, "color_B": 255}
    return {"color_R": 255, "color_G": 255, "color_B": 255}


def write_stm_export_footer(output_stream, export_payload):
    """Append a JSON footer that keeps STm metadata inside the CSV file."""
    output_stream.write("\n")
    output_stream.write(f"{stm_export_marker_begin}\n")
    json_text = json.dumps(export_payload, ensure_ascii=True, indent=2)
    for line in json_text.splitlines():
        output_stream.write(f"# {line}\n")
    output_stream.write(f"{stm_export_marker_end}\n")


def _as_dataframe(data, columns=None):
    dataframe = data.copy() if isinstance(data, DataFrame) else DataFrame(data or [])
    ordered_columns = list(columns) if columns is not None else []
    for column in ordered_columns:
        if column not in dataframe.columns:
            dataframe[column] = ""
    if ordered_columns:
        dataframe = dataframe[
            ordered_columns
            + [
                column
                for column in dataframe.columns
                if column not in ordered_columns
            ]
        ]
    return dataframe.astype(object).where(dataframe.notna(), "")


def _split_payload(dataframe):
    split_payload = json.loads(dataframe.to_json(orient="split", force_ascii=False))
    return {
        "columns": split_payload.get("columns", []),
        "data": split_payload.get("data", []),
    }


def _rgb(color):
    try:
        values = (
            [color[column] for column in stm_color_cols]
            if hasattr(color, "keys")
            else color
        )
        return [int(float(value)) for value in values[:3]]
    except (KeyError, TypeError, ValueError):
        return None


def build_stm_json(
    name,
    boundaries,
    units,
    colors=None,
    locked_conformable_links=None,
    boundary_columns=None,
    unit_columns=None,
):
    """Return an STm payload containing two dataframe-style tables."""
    boundaries_df = _as_dataframe(boundaries, boundary_columns)
    units_df = _as_dataframe(units, unit_columns)
    color_map = {
        str(feature): rgb
        for feature, color in dict(colors or {}).items()
        if (rgb := _rgb(color)) is not None
    }
    locked_links = [
        {"unit": str(unit_name), "boundary": str(boundary_name)}
        for unit_name, boundary_name in sorted(stm_links(locked_conformable_links))
        if str(unit_name).strip() and str(boundary_name).strip()
    ]

    for dataframe in (boundaries_df, units_df):
        if stm_feature_col not in dataframe.columns:
            continue
        for _, row in dataframe.iterrows():
            feature = str(row.get(stm_feature_col, "")).strip()
            if feature and all(column in dataframe.columns for column in stm_color_cols):
                rgb = _rgb(row)
                if rgb is not None:
                    color_map.setdefault(feature, rgb)
    boundaries_df.drop(
        columns=[column for column in stm_color_cols if column in boundaries_df],
        inplace=True,
    )
    units_df.drop(
        columns=[column for column in stm_color_cols if column in units_df],
        inplace=True,
    )
    return {
        "name": str(name or ""),
        "boundaries": _split_payload(boundaries_df),
        "units": _split_payload(units_df),
        "colors": color_map,
        "locked_conformable_links": locked_links,
    }


def is_stm_json(payload):
    """Return whether a payload contains the two required STm tables."""
    return (
        isinstance(payload, dict)
        and isinstance(payload.get("boundaries"), dict)
        and isinstance(payload.get("units"), dict)
    )


def read_stm_json(payload):
    """Return enriched boundary/unit records from an STm payload."""
    if not is_stm_json(payload):
        raise ValueError("Not a PZero STm payload")

    def dataframe(table_name):
        table = payload.get(table_name, {})
        return DataFrame(
            data=table.get("data", []),
            columns=table.get("columns", []),
        )

    boundaries_df = dataframe("boundaries")
    units_df = dataframe("units")
    colors = payload.get("colors", {}) or {}
    for current_df in (boundaries_df, units_df):
        if stm_feature_col not in current_df.columns:
            continue
        for row_label in current_df.index:
            color = colors.get(str(current_df.at[row_label, stm_feature_col]).strip())
            if not isinstance(color, (list, tuple)) or len(color) < 3:
                continue
            for column, value in zip(stm_color_cols, color[:3]):
                current_df.at[row_label, column] = value
    return {
        "name": str(payload.get("name", "")),
        "boundaries": boundaries_df.where(boundaries_df.notna(), "").to_dict(
            orient="records"
        ),
        "units": units_df.where(units_df.notna(), "").to_dict(orient="records"),
        "colors": colors,
        "locked_conformable_links": [
            {"unit": unit_name, "boundary": boundary_name}
            for unit_name, boundary_name in sorted(
                stm_links(payload.get("locked_conformable_links", []))
            )
        ],
    }
