from types import SimpleNamespace

from pandas import DataFrame
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QGraphicsLineItem
import pytest

from pzero.helpers.structural_topology import (
    stm_feature_col,
    stm_level_col,
    stm_unit_role_col,
)
from pzero.views.table_view_dialog import STmBuildDialog, ViewTable


@pytest.fixture
def builder(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    application = QApplication.instance() or QApplication([])
    old_color = {"color_R": 100, "color_G": 110, "color_B": 120}
    extra_color = {"color_R": 200, "color_G": 140, "color_B": 60}
    legend = [{stm_feature_col: "Contact", "role": "top", **old_color}]
    options = {
        "stm_color_codes": {"features": {"Contact": old_color, "Extra": extra_color}},
        "manual_units": [
            {
                "id": feature,
                "feature": feature,
                "unit_role": "SU",
                "structural_polarity": index + 0.5,
                "domains": [{"column": "Domain_1", "value": "Group"}],
                **color,
            }
            for index, (feature, color) in enumerate(
                [("Contact", old_color), ("Extra", extra_color)]
            )
        ],
        "locked_conformable_connections": [
            {"unit": "unit:manual:Contact", "surface": "surface:Contact"}
        ],
    }
    view = SimpleNamespace(
        parent=SimpleNamespace(get_structural_topology_legend_units=lambda: legend),
        current_table_options=options,
    )
    view._available_model_boundary_sources = (
        lambda: ViewTable._available_model_boundary_sources(view)
    )
    dataframe = DataFrame(
        [{stm_feature_col: "Contact", stm_unit_role_col: "Discontinuity", stm_level_col: 1}]
    )
    dialog = STmBuildDialog(
        dataframe_provider=lambda: dataframe,
        metadata_provider=lambda: ViewTable._available_stm_units(view),
        options_provider=lambda: options,
    )
    yield dialog, legend, options
    dialog.close()
    dialog.deleteLater()
    application.processEvents()


def test_refresh_updates_boundary_unit_and_link_colors(builder):
    dialog, legend, options = builder
    anchors = {
        key: node["right_anchor"] for key, node in dialog.node_items.items()
    }
    legend[0].update(color_R=40, color_G=190, color_B=80)

    dialog.refresh_button.click()

    expected_color = QColor(40, 190, 80)
    for key in ["surface:Contact", "unit:manual:Contact"]:
        assert dialog.node_items[key]["rect_item"].brush().color() == expected_color
    assert dialog.node_items["unit:manual:Extra"]["rect_item"].brush().color() == QColor(
        200, 140, 60
    )
    links = [item for item in dialog.scene.items() if isinstance(item, QGraphicsLineItem)]
    assert links
    assert all(link.pen().color() == expected_color.darker(150) for link in links)
    assert anchors == {
        key: node["right_anchor"] for key, node in dialog.node_items.items()
    }
    assert options["stm_color_codes"]["features"]["Contact"]["color_R"] == 100


def test_model_boundary_metadata_reads_collection_color():
    current_color = {"color_R": 40, "color_G": 80, "color_B": 120}
    view = SimpleNamespace(
        parent=SimpleNamespace(
            boundary_coll=SimpleNamespace(
                df=DataFrame([{"name": "Outer", "uid": "outer-uid"}]),
                get_uid_legend=lambda uid: current_color,
            )
        ),
        current_table_options={
            "stm_color_codes": {
                "features": {"Outer": {"color_R": 255, "color_G": 255, "color_B": 255}}
            }
        },
    )
    view._available_model_boundary_sources = (
        lambda: ViewTable._available_model_boundary_sources(view)
    )

    metadata = ViewTable._available_stm_units(view)

    assert len(metadata) == 1
    assert metadata[0]["role"] == "model_boundary"
    assert all(metadata[0][channel] == value for channel, value in current_color.items())
