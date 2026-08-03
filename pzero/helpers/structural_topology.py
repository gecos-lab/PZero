"""Pandas-style JSON serialization for Structural Topology models."""

import json

from pandas import DataFrame


STM_COLOR_COLUMNS = ("color_R", "color_G", "color_B")
STM_REPRESENTATIVE_COLUMN = "Representative Boundary"


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
    split_payload = json.loads(
        dataframe.to_json(orient="split", force_ascii=False)
    )
    return {
        "columns": split_payload.get("columns", []),
        "data": split_payload.get("data", []),
    }


def _rgb(color):
    try:
        values = (
            [color[column] for column in STM_COLOR_COLUMNS]
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
    representative_boundaries=None,
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
    representatives = dict(representative_boundaries or {})

    for dataframe in (boundaries_df, units_df):
        if "Feature" not in dataframe.columns:
            continue
        for _, row in dataframe.iterrows():
            feature = str(row.get("Feature", "")).strip()
            if feature and all(column in dataframe.columns for column in STM_COLOR_COLUMNS):
                rgb = _rgb(row)
                if rgb is not None:
                    color_map.setdefault(feature, rgb)
    if STM_REPRESENTATIVE_COLUMN not in units_df.columns:
        units_df[STM_REPRESENTATIVE_COLUMN] = ""
    for row_label in units_df.index:
        unit = str(units_df.at[row_label, "Feature"] if "Feature" in units_df.columns else "").strip()
        existing_boundary = str(units_df.at[row_label, STM_REPRESENTATIVE_COLUMN] or "").strip()
        if existing_boundary:
            continue
        fallback_boundary = str(representatives.get(unit, "")).strip()
        if unit and fallback_boundary:
            units_df.at[row_label, STM_REPRESENTATIVE_COLUMN] = fallback_boundary

    boundaries_df.drop(
        columns=[column for column in STM_COLOR_COLUMNS if column in boundaries_df],
        inplace=True,
    )
    units_df.drop(
        columns=[
            column
            for column in STM_COLOR_COLUMNS
            if column in units_df
        ],
        inplace=True,
    )
    return {
        "name": str(name or ""),
        "boundaries": _split_payload(boundaries_df),
        "units": _split_payload(units_df),
        "colors": color_map,
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
        if "Feature" not in current_df.columns:
            continue
        for row_label in current_df.index:
            color = colors.get(str(current_df.at[row_label, "Feature"]).strip())
            if not isinstance(color, (list, tuple)) or len(color) < 3:
                continue
            for column, value in zip(STM_COLOR_COLUMNS, color[:3]):
                current_df.at[row_label, column] = value
    return {
        "name": str(payload.get("name", "")),
        "boundaries": boundaries_df.where(boundaries_df.notna(), "").to_dict(
            orient="records"
        ),
        "units": units_df.where(units_df.notna(), "").to_dict(orient="records"),
        "colors": colors,
    }
