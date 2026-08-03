"""table_view_dialog.py
Dockable table view used to manage user-defined editable tables."""

import json
from os import path as os_path
from hashlib import md5
from functools import lru_cache

from pandas import DataFrame as pd_DataFrame
from pandas import concat as pd_concat
from pandas import isna as pd_isna
from pandas import to_numeric as pd_to_numeric

from PySide6.QtCore import QAbstractTableModel, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QAction,
    QColor,
    QBrush,
    QPen,
    QFont,
    QFontMetrics,
    QImage,
    QPainter,
    QTransform,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
    QHeaderView,
    QSizePolicy,
    QFileDialog,
    QMenu,
    QMenuBar,
    QComboBox,
    QFormLayout,
    QColorDialog,
    QStyledItemDelegate,
    QGraphicsView,
    QGraphicsScene,
)

from pzero.helpers.helper_dialogs import input_text_dialog
from pzero.helpers.structural_topology import build_stm_json
from pzero.properties_manager import PropertiesCMaps

STRUCTURAL_TOPOLOGY_TABLE_TYPE = "stm"
STRUCTURAL_TOPOLOGY_FEATURE_COLUMN = "Feature"
STRUCTURAL_TOPOLOGY_UNIT_ROLE_COLUMN = "Unit Role"
STRUCTURAL_TOPOLOGY_POLARITY_COLUMN = "Level"
STRUCTURAL_TOPOLOGY_BOUNDARY_ROLE_COLUMN = "Role"
STRUCTURAL_TOPOLOGY_BOUNDARY_POLARITY_COLUMN = "Level"
STRUCTURAL_TOPOLOGY_BOUNDARY_UNITS_COLUMN = "Units"
STRUCTURAL_TOPOLOGY_UNIT_BOUNDARIES_COLUMN = "Boundaries"
STRUCTURAL_TOPOLOGY_UNIT_POLARITY_COLUMN = "Level"
STRUCTURAL_TOPOLOGY_MODEL_BOUNDARY = "Model Boundary"
STRUCTURAL_TOPOLOGY_REPRESENTATIVE_BOUNDARY_FIELD = "Representative Boundary"
STRUCTURAL_TOPOLOGY_BOUNDARY_ROLE_VALUES = [
    "top",
    "base",
    "fault",
    "intrusive",
    "tectonic",
    "unconformity",
    "model_boundary",
]
STRUCTURAL_TOPOLOGY_BOUNDARY_COLUMNS = [
    STRUCTURAL_TOPOLOGY_FEATURE_COLUMN,
    STRUCTURAL_TOPOLOGY_BOUNDARY_ROLE_COLUMN,
    STRUCTURAL_TOPOLOGY_BOUNDARY_POLARITY_COLUMN,
    STRUCTURAL_TOPOLOGY_BOUNDARY_UNITS_COLUMN,
]
STRUCTURAL_TOPOLOGY_UNIT_COLUMNS = [
    STRUCTURAL_TOPOLOGY_FEATURE_COLUMN,
    STRUCTURAL_TOPOLOGY_UNIT_ROLE_COLUMN,
    STRUCTURAL_TOPOLOGY_UNIT_POLARITY_COLUMN,
    STRUCTURAL_TOPOLOGY_UNIT_BOUNDARIES_COLUMN,
    STRUCTURAL_TOPOLOGY_REPRESENTATIVE_BOUNDARY_FIELD,
    "Domain_1",
]
STRUCTURAL_TOPOLOGY_BASE_COLUMNS = [
    STRUCTURAL_TOPOLOGY_FEATURE_COLUMN,
    STRUCTURAL_TOPOLOGY_UNIT_ROLE_COLUMN,
    STRUCTURAL_TOPOLOGY_POLARITY_COLUMN,
    "Domain_1",
]
STRUCTURAL_TOPOLOGY_PROTECTED_COLUMNS = {
    STRUCTURAL_TOPOLOGY_FEATURE_COLUMN,
    STRUCTURAL_TOPOLOGY_UNIT_ROLE_COLUMN,
    STRUCTURAL_TOPOLOGY_POLARITY_COLUMN,
}
STRUCTURAL_TOPOLOGY_EXPORT_MARKER_BEGIN = "# PZERO_STM_EXPORT BEGIN"
STRUCTURAL_TOPOLOGY_EXPORT_MARKER_END = "# PZERO_STM_EXPORT END"
STRUCTURAL_TOPOLOGY_UNIT_VALUES = [
    "TU",
    "SU",
    "IU",
    "SD",
]
STRUCTURAL_TOPOLOGY_NON_BOUNDARY_ROLES = {"TU", "SU", "IU", "SD"}
STRUCTURAL_TOPOLOGY_GENERATED_UNIT_ROLES = {
    "top": "SU",
    "base": "SU",
    "bottom": "SU",
    "intrusive": "IU",
    "tectonic": "TU",
    "fault": "TU",
}

_STM_UNIT_ROLES_BY_CASE = {
    role.casefold(): role for role in STRUCTURAL_TOPOLOGY_UNIT_VALUES
}
_STM_BOUNDARY_ROLES_BY_CASE = {
    role.casefold(): role for role in STRUCTURAL_TOPOLOGY_BOUNDARY_ROLE_VALUES
}


def structural_topology_domain_column_name(order_value) -> str:
    """Return the canonical STm domain column name for an order value."""
    return f"Domain_{int(order_value)}"


def structural_topology_domain_order(column_name: str):
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


def normalise_structural_topology_unit_role(raw_value):
    """Return a valid canonical Unit Role value."""
    value = str(raw_value or "").strip()
    return _STM_UNIT_ROLES_BY_CASE.get(value.casefold(), value or "TU")


def normalise_structural_topology_boundary_role(raw_value):
    """Return a valid canonical boundary Role value."""
    value = str(raw_value or "").strip()
    value_key = value.casefold().replace(" ", "_")
    return _STM_BOUNDARY_ROLES_BY_CASE.get(value_key, value)


def is_structural_topology_model_boundary(row) -> bool:
    """Return whether a boundary row represents the unique model boundary."""
    if row is None:
        return False
    feature_name = str(row.get(STRUCTURAL_TOPOLOGY_FEATURE_COLUMN, "")).strip()
    role_name = normalise_structural_topology_boundary_role(
        row.get(STRUCTURAL_TOPOLOGY_BOUNDARY_ROLE_COLUMN, "")
    )
    return (
        role_name == "model_boundary"
        or feature_name.casefold() == STRUCTURAL_TOPOLOGY_MODEL_BOUNDARY.casefold()
    )


def _stm_names(raw_value):
    """Return a stable list of names from JSON, lists, or comma-separated cells."""
    if raw_value is None or (not isinstance(raw_value, (list, tuple, set)) and pd_isna(raw_value)):
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


def _stm_names_cell(raw_value):
    """Return the compact editable representation used by relation cells."""
    return ", ".join(_stm_names(raw_value))


def _stm_records(dataframe):
    """Return JSON-safe records, preserving relationship fields as real lists."""
    if dataframe is None:
        return []
    records = []
    for record in dataframe.where(dataframe.notna(), "").to_dict(orient="records"):
        out_record = {}
        for key, value in record.items():
            if key in (
                STRUCTURAL_TOPOLOGY_BOUNDARY_UNITS_COLUMN,
                STRUCTURAL_TOPOLOGY_UNIT_BOUNDARIES_COLUMN,
            ):
                out_record[str(key)] = _stm_names(value)
            else:
                out_record[str(key)] = value
        records.append(out_record)
    return records


def _stm_records_with_colors(
    dataframe, feature_colors=None, representative_boundaries=None
):
    """Return table records enriched with hidden RGB persistence fields."""
    feature_colors = feature_colors or {}
    records = _stm_records(dataframe)
    representative_boundaries = representative_boundaries or {}
    for record in records:
        feature_name = str(
            record.get(STRUCTURAL_TOPOLOGY_FEATURE_COLUMN, "")
        ).strip()
        if feature_name in feature_colors:
            record.update(_stm_color_to_dict(feature_colors[feature_name]))
        representative_boundary = str(
            representative_boundaries.get(feature_name, "")
        ).strip()
        if representative_boundary:
            record[STRUCTURAL_TOPOLOGY_REPRESENTATIVE_BOUNDARY_FIELD] = (
                representative_boundary
            )
    return records

def structural_topology_sort_key(raw_value):
    """Return a sortable numeric polarity value."""
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return float("inf")


def structural_topology_color(raw_key):
    """Return a stable pastel color for STm nodes/links."""
    key_text = str(raw_key or "").encode("utf-8", errors="ignore")
    digest = md5(key_text).hexdigest()
    hue = int(digest[:4], 16) % 360
    return QColor.fromHsv(hue, 80, 245)


def _stm_color_to_dict(color_value):
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


def _stm_write_export_footer(output_stream, export_payload):
    """Append a JSON footer that keeps STm metadata inside the CSV file."""
    output_stream.write("\n")
    output_stream.write(f"{STRUCTURAL_TOPOLOGY_EXPORT_MARKER_BEGIN}\n")
    json_text = json.dumps(export_payload, ensure_ascii=True, indent=2)
    for line in json_text.splitlines():
        output_stream.write(f"# {line}\n")
    output_stream.write(f"{STRUCTURAL_TOPOLOGY_EXPORT_MARKER_END}\n")


class ZoomableGraphicsView(QGraphicsView):
    """Graphics view with bounded zoom support."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._zoom_factor = 1.15
        self._min_scale = 0.2
        self._max_scale = 8.0
        self._current_scale = 1.0
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)

    def _apply_zoom(self, factor: float):
        new_scale = self._current_scale * factor
        if new_scale < self._min_scale or new_scale > self._max_scale:
            return
        self.scale(factor, factor)
        self._current_scale = new_scale

    def zoom_in(self):
        self._apply_zoom(self._zoom_factor)

    def zoom_out(self):
        self._apply_zoom(1.0 / self._zoom_factor)

    def fit_scene(self, scene_rect):
        self.resetTransform()
        self._current_scale = 1.0
        self.fitInView(scene_rect, Qt.KeepAspectRatio)
        scale_from_transform = float(self.transform().m11())
        if scale_from_transform > 0:
            self._current_scale = scale_from_transform

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            if event.angleDelta().y() > 0:
                self.zoom_in()
            else:
                self.zoom_out()
            event.accept()
            return
        super().wheelEvent(event)


class STmGraphicsScene(QGraphicsScene):
    """Graphics scene that forwards graph-item clicks back to the STm dialog."""

    def __init__(self, dialog=None, parent=None):
        super().__init__(parent)
        self.dialog = dialog

    def mousePressEvent(self, event):
        clicked_item = self.itemAt(event.scenePos(), QTransform())
        while clicked_item is not None:
            item_key = clicked_item.data(0)
            if item_key and self.dialog is not None:
                item_key = str(item_key)
                if item_key.startswith("domain:"):
                    self.dialog.on_domain_clicked(item_key)
                else:
                    self.dialog.on_node_clicked(item_key)
                event.accept()
                return
            clicked_item = clicked_item.parentItem()
        if self.dialog is not None:
            self.dialog.clear_selection()
        super().mousePressEvent(event)


class ManualSTmUnitDialog(QDialog):
    """Dialog used to add an extra STm unit node."""

    def __init__(self, parent=None, domain_columns=None, unit_info=None):
        super().__init__(parent)
        unit_info = dict(unit_info or {})
        self.setWindowTitle("Edit extra unit" if unit_info else "Add extra unit")
        self.resize(420, 320)
        self.selected_color = structural_topology_color("extra_unit")
        self.domain_edits = {}
        try:
            self.selected_color = QColor(
                int(float(unit_info.get("color_R", self.selected_color.red()))),
                int(float(unit_info.get("color_G", self.selected_color.green()))),
                int(float(unit_info.get("color_B", self.selected_color.blue()))),
            )
        except (TypeError, ValueError):
            pass

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        self.feature_edit = QLineEdit()
        self.feature_edit.setPlaceholderText("Unit feature/name")
        self.feature_edit.setText(str(unit_info.get("feature", "")).strip())
        form_layout.addRow("Feature", self.feature_edit)

        self.unit_role_combo = QComboBox()
        self.unit_role_combo.addItems(
            [
                value
                for value in STRUCTURAL_TOPOLOGY_UNIT_VALUES
                if value != "Discontinuity"
            ]
        )
        unit_role = normalise_structural_topology_unit_role(
            unit_info.get("unit_role", "SU")
        )
        role_idx = self.unit_role_combo.findText(unit_role)
        if role_idx >= 0:
            self.unit_role_combo.setCurrentIndex(role_idx)
        form_layout.addRow("Unit Role", self.unit_role_combo)

        color_layout = QHBoxLayout()
        self.color_button = QPushButton("")
        self.color_button.setFixedSize(54, 24)
        self.color_button.setToolTip("Choose color")
        self.color_button.clicked.connect(self.choose_color)
        color_layout.addWidget(self.color_button)
        color_layout.addStretch(1)
        form_layout.addRow("Color", color_layout)

        domains_by_column = {
            str(domain_info.get("column", "")).strip(): str(
                domain_info.get("value", "")
            ).strip()
            for domain_info in unit_info.get("domains", [])
            if isinstance(domain_info, dict)
        }
        for domain_column in domain_columns or ["Domain_1"]:
            domain_edit = QLineEdit()
            domain_edit.setPlaceholderText(str(domain_column))
            domain_edit.setText(domains_by_column.get(str(domain_column), ""))
            self.domain_edits[str(domain_column)] = domain_edit
            form_layout.addRow(str(domain_column), domain_edit)

        layout.addLayout(form_layout)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._update_color_button()

    def choose_color(self):
        """Open the Qt color picker for the extra unit color."""
        color_out = QColorDialog.getColor(self.selected_color, self)
        if not color_out.isValid():
            return
        self.selected_color = color_out
        self._update_color_button()

    def _update_color_button(self):
        """Refresh the button preview for the selected color."""
        self.color_button.setStyleSheet(
            "QPushButton { "
            f"background-color: rgb({self.selected_color.red()}, "
            f"{self.selected_color.green()}, {self.selected_color.blue()}); "
            "}"
        )

    def validate_and_accept(self):
        """Validate required extra unit fields."""
        if not self.feature_edit.text().strip():
            QMessageBox.warning(self, "Missing feature", "Insert a feature name.")
            return
        self.accept()

    @property
    def structural_polarity(self):
        return ""

    @property
    def unit_info(self):
        domains = []
        for domain_column, domain_edit in self.domain_edits.items():
            domain_value = domain_edit.text().strip()
            if domain_value:
                domains.append({"column": domain_column, "value": domain_value})
        return {
            "feature": self.feature_edit.text().strip(),
            "unit_role": self.unit_role_combo.currentText(),
            "structural_polarity": self.structural_polarity,
            "domains": domains,
            "color_R": self.selected_color.red(),
            "color_G": self.selected_color.green(),
            "color_B": self.selected_color.blue(),
        }


class STmBuildDialog(QDialog):
    """Preview dialog that builds an STm graph from the current table."""

    LEFT_X = 180
    RIGHT_X = 760
    TOP_Y = 120
    Y_STEP = 125
    NODE_HEIGHT = 74
    NODE_MIN_WIDTH = 220
    NODE_PADDING_X = 28
    DOMAIN_MARGIN = 32

    def __init__(
        self,
        parent=None,
        table_name=None,
        dataframe_provider=None,
        metadata_provider=None,
        options_provider=None,
        options_updater=None,
        polarity_calculator=None,
    ):
        super().__init__(parent)
        self.table_name = str(table_name or "").strip() or "STm"
        self.dataframe_provider = dataframe_provider
        self.metadata_provider = metadata_provider
        self.options_provider = options_provider
        self.options_updater = options_updater
        self.polarity_calculator = polarity_calculator
        self.selected_node_key = None
        self.selected_domain_key = None
        self.manual_connections = self._load_manual_connections()
        self.representative_connections = (
            self._load_representative_connections()
        )
        self.manual_connections.update(self.representative_connections)
        self.manual_units = self._load_manual_units()
        self.unit_renames = self._load_unit_renames()
        self.node_items = {}
        self.domain_items = {}
        self.editing_enabled = False
        self.setWindowTitle(f"Build STm - {self.table_name}")
        self.resize(1120, 860)
        self._fit_on_next_rebuild = True
        self._fit_after_show_pending = True

        layout = QVBoxLayout(self)
        info_label = QLabel(
            "Units are shown on the left and boundaries on the right. "
            "Colored links identify immutable representative surfaces; "
            "black links are manual and can be edited here."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        self.graphics_view = ZoomableGraphicsView(self)
        self.graphics_view.setRenderHint(QPainter.Antialiasing, True)
        self.graphics_view.setRenderHint(QPainter.TextAntialiasing, True)
        self.graphics_view.setDragMode(QGraphicsView.ScrollHandDrag)
        self.graphics_view.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.scene = STmGraphicsScene(dialog=self, parent=self)
        self.graphics_view.setScene(self.scene)
        layout.addWidget(self.graphics_view, 1)

        buttons_layout = QHBoxLayout()
        self.editing_toggle_button = QPushButton("Enable editing")
        self.editing_toggle_button.setCheckable(True)
        self.editing_toggle_button.toggled.connect(self.on_editing_toggled)
        buttons_layout.addWidget(self.editing_toggle_button)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.rebuild_scene)
        buttons_layout.addWidget(self.refresh_button)
        self.clear_selection_button = QPushButton("Clear selection")
        self.clear_selection_button.clicked.connect(self.clear_selection)
        buttons_layout.addWidget(self.clear_selection_button)
        self.rename_unit_button = QPushButton("Rename unit")
        self.rename_unit_button.clicked.connect(self.rename_selected_generated_unit)
        buttons_layout.addWidget(self.rename_unit_button)
        self.clear_manual_button = QPushButton("Clear manual links")
        self.clear_manual_button.clicked.connect(self.clear_manual_connections)
        buttons_layout.addWidget(self.clear_manual_button)
        self.calculate_polarity_button = QPushButton("Calculate unit level")
        self.calculate_polarity_button.clicked.connect(self.calculate_unit_polarity)
        buttons_layout.addWidget(self.calculate_polarity_button)
        self.add_manual_unit_button = QPushButton("Add extra unit")
        self.add_manual_unit_button.clicked.connect(self.add_manual_unit)
        buttons_layout.addWidget(self.add_manual_unit_button)
        self.edit_manual_unit_button = QPushButton("Edit extra unit")
        self.edit_manual_unit_button.clicked.connect(self.edit_selected_manual_unit)
        buttons_layout.addWidget(self.edit_manual_unit_button)
        self.remove_manual_unit_button = QPushButton("Remove extra unit")
        self.remove_manual_unit_button.clicked.connect(self.remove_selected_manual_unit)
        buttons_layout.addWidget(self.remove_manual_unit_button)
        self.rename_unit_button.setVisible(False)
        self.add_manual_unit_button.setVisible(False)
        self.edit_manual_unit_button.setVisible(False)
        self.remove_manual_unit_button.setVisible(False)
        zoom_out_button = QPushButton("-")
        zoom_out_button.setToolTip("Zoom out")
        zoom_out_button.clicked.connect(self.graphics_view.zoom_out)
        buttons_layout.addWidget(zoom_out_button)
        zoom_in_button = QPushButton("+")
        zoom_in_button.setToolTip("Zoom in")
        zoom_in_button.clicked.connect(self.graphics_view.zoom_in)
        buttons_layout.addWidget(zoom_in_button)
        reset_zoom_button = QPushButton("Reset zoom")
        reset_zoom_button.setToolTip("Fit scene to view")
        reset_zoom_button.clicked.connect(self.reset_zoom_to_fit)
        buttons_layout.addWidget(reset_zoom_button)
        export_image_button = QPushButton("Export image")
        export_image_button.setToolTip("Save the STm graph as an image")
        export_image_button.clicked.connect(self.export_scene_image)
        buttons_layout.addWidget(export_image_button)
        zoom_hint_label = QLabel("Ctrl + mouse wheel to zoom")
        buttons_layout.addWidget(zoom_hint_label)
        buttons_layout.addStretch(1)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        buttons_layout.addWidget(close_button)
        layout.addLayout(buttons_layout)

        self.rebuild_scene()
        self.update_editing_ui()

    def calculate_unit_polarity(self):
        """Delegate table-backed polarity calculation and refresh the graph."""
        if callable(self.polarity_calculator):
            self.polarity_calculator()
            self.manual_connections = self._load_manual_connections()
            self.representative_connections = (
                self._load_representative_connections()
            )
            self.manual_connections.update(self.representative_connections)
            self.manual_units = self._load_manual_units()
            self.rebuild_scene()

    def showEvent(self, event):
        super().showEvent(event)
        if self._fit_after_show_pending:
            self._fit_after_show_pending = False
            QTimer.singleShot(0, self.reset_zoom_to_fit)
            QTimer.singleShot(80, self.reset_zoom_to_fit)

    def on_editing_toggled(self, checked):
        """Enable/disable editing actions for manual STm links."""
        self.editing_enabled = bool(checked)
        if not self.editing_enabled:
            self.selected_node_key = None
            self.selected_domain_key = None
        self.update_editing_ui()
        self._update_node_highlight()

    def update_editing_ui(self):
        """Refresh editing controls in the STm builder."""
        self.editing_toggle_button.setText(
            "Disable editing" if self.editing_enabled else "Enable editing"
        )
        self.clear_selection_button.setEnabled(self.editing_enabled)
        self.rename_unit_button.setEnabled(
            self.editing_enabled and self._selected_generated_unit_key() is not None
        )
        self.clear_manual_button.setEnabled(
            self.editing_enabled
            and bool(
                self.manual_connections - self.representative_connections
            )
        )
        self.add_manual_unit_button.setEnabled(self.editing_enabled)
        self.edit_manual_unit_button.setEnabled(
            self.editing_enabled and self._selected_manual_unit_id() is not None
        )
        self.remove_manual_unit_button.setEnabled(
            self.editing_enabled and self._selected_manual_unit_id() is not None
        )

    def rebuild_scene(self):
        """Rebuild the graphics scene from the current STm table."""
        self.scene.clear()
        self.node_items = {}
        self.domain_items = {}
        dataframe = pd_DataFrame()
        if callable(self.dataframe_provider):
            current_df = self.dataframe_provider()
            if current_df is not None:
                dataframe = current_df.copy()

        self._draw_scene(dataframe)
        scene_rect = self.scene.itemsBoundingRect().adjusted(-80, -80, 80, 80)
        self.scene.setSceneRect(scene_rect)
        if self._fit_on_next_rebuild:
            self.graphics_view.fit_scene(scene_rect)
            self._fit_on_next_rebuild = False

    def reset_zoom_to_fit(self):
        """Reset user zoom and fit the full scene in view."""
        scene_rect = self.scene.itemsBoundingRect().adjusted(-80, -80, 80, 80)
        self.scene.setSceneRect(scene_rect)
        self.graphics_view.fit_scene(scene_rect)

    def export_scene_image(self):
        """Save the current STm graph scene to a raster image."""
        scene_rect = self.scene.itemsBoundingRect().adjusted(-40, -40, 40, 40)
        if scene_rect.isEmpty():
            QMessageBox.information(self, "Export image", "There is no STm graph to export.")
            return

        safe_table_name = "".join(
            char if char.isalnum() or char in "._-" else "_"
            for char in self.table_name
        ).strip("_")
        default_name = f"{safe_table_name or 'STm'}_graph.png"
        file_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export STm graph image",
            default_name,
            "PNG image (*.png);;JPEG image (*.jpg);;BMP image (*.bmp);;All files (*.*)",
        )
        if not file_path:
            return

        if not os_path.splitext(file_path)[1]:
            extension_by_filter = {
                "PNG image (*.png)": ".png",
                "JPEG image (*.jpg)": ".jpg",
                "BMP image (*.bmp)": ".bmp",
            }
            file_path = f"{file_path}{extension_by_filter.get(selected_filter, '.png')}"

        width = max(1, int(scene_rect.width()) + 1)
        height = max(1, int(scene_rect.height()) + 1)
        image = QImage(width, height, QImage.Format_ARGB32_Premultiplied)
        image.fill(Qt.transparent)

        painter = QPainter(image)
        try:
            self.scene.render(
                painter,
                QRectF(0, 0, width, height),
                scene_rect,
            )
        finally:
            painter.end()

        if not image.save(file_path):
            QMessageBox.warning(
                self,
                "Export image",
                f'Could not save image "{file_path}".',
            )

    def _draw_scene(self, dataframe):
        """Populate the scene with STm nodes and the automatically-derived links."""
        header_font = QFont()
        header_font.setPointSize(16)
        header_font.setBold(True)
        self.scene.addText("Units", header_font).setPos(self.LEFT_X - 70, 35)
        self.scene.addText("Boundaries", header_font).setPos(self.RIGHT_X - 90, 35)

        if (dataframe is None or dataframe.empty) and not self.manual_units:
            empty_text = self.scene.addText("The STm table is empty.")
            empty_text.setPos(260, 220)
            return

        metadata_by_feature = {}
        if callable(self.metadata_provider):
            for unit_info in self.metadata_provider() or []:
                feature_name = str(
                    unit_info.get(STRUCTURAL_TOPOLOGY_FEATURE_COLUMN, "")
                ).strip()
                if feature_name:
                    metadata_by_feature[feature_name] = dict(unit_info)

        rows = self._build_rows_payload(dataframe)
        rows.extend(self._build_manual_rows_payload())
        rows.sort(
            key=lambda row_info: (
                row_info[STRUCTURAL_TOPOLOGY_POLARITY_COLUMN],
                str(row_info[STRUCTURAL_TOPOLOGY_FEATURE_COLUMN]).casefold(),
            )
        )
        unit_nodes = []
        surface_nodes = []
        paired_links = []
        domain_groups = {}

        for row_idx, row_info in enumerate(rows):
            metadata = metadata_by_feature.get(
                row_info[STRUCTURAL_TOPOLOGY_FEATURE_COLUMN], {}
            )
            row_color = self._legend_color_for_row(row_info=row_info, metadata=metadata)
            row_color_dark = row_color.darker(150)
            row_nodes = []
            has_unit = (
                row_info[STRUCTURAL_TOPOLOGY_UNIT_ROLE_COLUMN] != "Discontinuity"
            )

            if has_unit:
                if row_info.get("Manual"):
                    unit_key = f'unit:manual:{row_info["Manual Unit ID"]}'
                else:
                    unit_key = f'unit:{row_info[STRUCTURAL_TOPOLOGY_FEATURE_COLUMN]}'
                default_unit_label = (
                    f'{row_info[STRUCTURAL_TOPOLOGY_FEATURE_COLUMN]}_'
                    f'{row_info[STRUCTURAL_TOPOLOGY_UNIT_ROLE_COLUMN]}'
                )
                unit_label = str(
                    row_info.get("Unit Label", default_unit_label)
                ).strip() or default_unit_label
                if not row_info.get("Manual"):
                    unit_label = self.unit_renames.get(unit_key, default_unit_label)
                unit_nodes.append(
                    {
                        "key": unit_key,
                        "label": unit_label,
                        "default_label": default_unit_label,
                        "polarity": row_info[STRUCTURAL_TOPOLOGY_POLARITY_COLUMN],
                        "brush": row_color,
                        "pen": row_color_dark,
                        "row_idx": row_idx,
                        "manual": bool(row_info.get("Manual")),
                    }
                )
                row_nodes.append(unit_key)

            if not row_info.get("Manual"):
                is_model_boundary = (
                    normalise_structural_topology_boundary_role(
                        metadata.get("role", "")
                    )
                    == "model_boundary"
                    or str(
                        row_info[STRUCTURAL_TOPOLOGY_FEATURE_COLUMN]
                    ).casefold()
                    == STRUCTURAL_TOPOLOGY_MODEL_BOUNDARY.casefold()
                )
                surface_key = (
                    "surface:boundary"
                    if is_model_boundary
                    else f'surface:{row_info[STRUCTURAL_TOPOLOGY_FEATURE_COLUMN]}'
                )
                surface_nodes.append(
                    {
                        "key": surface_key,
                        "label": row_info[STRUCTURAL_TOPOLOGY_FEATURE_COLUMN],
                        "polarity": row_info[STRUCTURAL_TOPOLOGY_POLARITY_COLUMN],
                        "brush": row_color,
                        "pen": row_color_dark,
                        "row_idx": row_idx,
                    }
                )
                row_nodes.append(surface_key)

            if has_unit and len(row_nodes) == 2:
                paired_links.append(
                    {
                        "source": row_nodes[0],
                        "target": row_nodes[1],
                        "color": row_color_dark,
                    }
                )

            for domain_column, domain_value in row_info["Domains"]:
                if not domain_value:
                    continue
                group_key = (domain_column, domain_value)
                domain_group = domain_groups.setdefault(
                    group_key, {"nodes": set(), "rows": set()}
                )
                domain_group["nodes"].update(row_nodes)
                domain_group["rows"].add(row_idx)

        for node_info in unit_nodes:
            item_info = self._add_node(
                center_x=self.LEFT_X,
                center_y=self.TOP_Y
                + (node_info["row_idx"] + 1) * self.Y_STEP,
                label=node_info["label"],
                fill_color=node_info["brush"],
                outline_color=node_info["pen"],
                node_key=node_info["key"],
                node_side="unit",
            )
            item_info["default_label"] = node_info.get("default_label", "")
            item_info["manual"] = bool(node_info.get("manual"))
            self.node_items[node_info["key"]] = item_info

        for node_info in surface_nodes:
            row_idx = node_info["row_idx"]
            node_y = (
                self.TOP_Y
                if row_idx < 0
                else self.TOP_Y + (row_idx + 1) * self.Y_STEP
            )
            self.node_items[node_info["key"]] = self._add_node(
                center_x=self.RIGHT_X,
                center_y=node_y,
                label=node_info["label"],
                fill_color=node_info["brush"],
                outline_color=node_info["pen"],
                node_key=node_info["key"],
                node_side="surface",
            )

        self._add_domain_boxes(domain_groups=domain_groups, node_items=self.node_items)

        for link_info in paired_links:
            source_item = self.node_items.get(link_info["source"])
            target_item = self.node_items.get(link_info["target"])
            if source_item is None or target_item is None:
                continue
            line_pen = QPen(link_info["color"])
            line_pen.setWidth(5)
            self.scene.addLine(
                source_item["right_anchor"][0],
                source_item["right_anchor"][1],
                target_item["left_anchor"][0],
                target_item["left_anchor"][1],
                line_pen,
            ).setZValue(-10)

        self._draw_manual_connections()
        self._update_node_highlight()

    def _build_rows_payload(self, dataframe):
        """Convert the dataframe into normalized STm rows."""
        rows = []
        if dataframe is None or dataframe.empty:
            return rows
        ordered_df = dataframe.copy()
        if STRUCTURAL_TOPOLOGY_POLARITY_COLUMN in ordered_df.columns:
            ordered_df["_sort_polarity"] = ordered_df[
                STRUCTURAL_TOPOLOGY_POLARITY_COLUMN
            ].apply(
                structural_topology_sort_key
            )
            sort_columns = ["_sort_polarity"]
            sort_ascending = [True]
            if STRUCTURAL_TOPOLOGY_FEATURE_COLUMN in ordered_df.columns:
                sort_columns.append(STRUCTURAL_TOPOLOGY_FEATURE_COLUMN)
                sort_ascending.append(True)
            ordered_df.sort_values(
                by=sort_columns,
                ascending=sort_ascending,
                inplace=True,
            )
        for _, row in ordered_df.iterrows():
            feature_name = str(row.get(STRUCTURAL_TOPOLOGY_FEATURE_COLUMN, "")).strip()
            if not feature_name:
                continue
            unit_role = normalise_structural_topology_unit_role(
                row.get(
                    STRUCTURAL_TOPOLOGY_UNIT_ROLE_COLUMN, "Discontinuity"
                )
            )
            domains = []
            for column_name in ordered_df.columns.tolist():
                if structural_topology_domain_order(column_name) is None:
                    continue
                domain_value = str(row.get(column_name, "")).strip()
                if domain_value:
                    domains.append((column_name, domain_value))
            rows.append(
                {
                    STRUCTURAL_TOPOLOGY_FEATURE_COLUMN: feature_name,
                    STRUCTURAL_TOPOLOGY_UNIT_ROLE_COLUMN: unit_role,
                    STRUCTURAL_TOPOLOGY_POLARITY_COLUMN: structural_topology_sort_key(
                        row.get(STRUCTURAL_TOPOLOGY_POLARITY_COLUMN, "")
                    ),
                    "Domains": domains,
                    "Manual": False,
                }
            )
        return rows

    def _build_manual_rows_payload(self):
        """Convert persisted manual unit options into graph rows."""
        rows = []
        for unit_info in self.manual_units:
            feature_name = str(unit_info.get("feature", "")).strip()
            unit_role = normalise_structural_topology_unit_role(
                unit_info.get("unit_role", "SU")
            )
            unit_id = str(unit_info.get("id", "")).strip()
            if not feature_name or not unit_id or unit_role == "Discontinuity":
               continue
        
            domains = []
            for domain_info in unit_info.get("domains", []):
                if not isinstance(domain_info, dict):
                    continue
                domain_column = str(domain_info.get("column", "")).strip()
                domain_value = str(domain_info.get("value", "")).strip()
                if domain_column and domain_value:
                    domains.append((domain_column, domain_value))
            rows.append(
                {
                    STRUCTURAL_TOPOLOGY_FEATURE_COLUMN: feature_name,
                    STRUCTURAL_TOPOLOGY_UNIT_ROLE_COLUMN: unit_role,
                    STRUCTURAL_TOPOLOGY_POLARITY_COLUMN: structural_topology_sort_key(
                        unit_info.get("structural_polarity")
                        if str(unit_info.get("structural_polarity", "")).strip()
                        else unit_info.get("plot_polarity", "")
                    ),
                    "Domains": domains,
                    "Manual": True,
                    "Manual Unit ID": unit_id,
                    "Unit Label": str(
                        unit_info.get("display_name", feature_name)
                    ).strip() or feature_name,
                    "color_R": unit_info.get("color_R", 255),
                    "color_G": unit_info.get("color_G", 255),
                    "color_B": unit_info.get("color_B", 255),
                }
            )
        return rows

    def _legend_color_for_row(self, row_info=None, metadata=None):
        """Return the legend color for a row, falling back to a stable generated color."""
        metadata = metadata or {}
        color_source = row_info if row_info and row_info.get("Manual") else metadata
        try:
            red = int(float(color_source.get("color_R")))
            green = int(float(color_source.get("color_G")))
            blue = int(float(color_source.get("color_B")))
            return QColor(
                max(0, min(255, red)),
                max(0, min(255, green)),
                max(0, min(255, blue)),
            )
        except (TypeError, ValueError):
            return structural_topology_color(
                (row_info or {}).get(STRUCTURAL_TOPOLOGY_FEATURE_COLUMN, "")
            )

    def _load_manual_connections(self):
        """Load persisted manual connections from the table options."""
        options = {}
        if callable(self.options_provider):
            options = self.options_provider() or {}

        connections = set()
        for connection_info in options.get("manual_connections", []):
            if not isinstance(connection_info, dict):
                continue
            unit_key = str(connection_info.get("unit", "")).strip()
            surface_key = str(connection_info.get("surface", "")).strip()
            if not unit_key or not surface_key:
                continue
            if not unit_key.startswith("unit:") or not surface_key.startswith("surface:"):
                continue
            connections.add((unit_key, surface_key))
        return connections

    def _load_representative_connections(self):
        """Load immutable unit-to-representative-surface connections."""
        options = {}
        if callable(self.options_provider):
            options = self.options_provider() or {}
        connections = set()
        for connection_info in options.get("representative_connections", []):
            if not isinstance(connection_info, dict):
                continue
            unit_key = str(connection_info.get("unit", "")).strip()
            surface_key = str(connection_info.get("surface", "")).strip()
            if unit_key.startswith("unit:") and surface_key.startswith("surface:"):
                connections.add((unit_key, surface_key))
        return connections

    def _save_manual_connections(self):
        """Persist the current set of manual connections."""
        if not callable(self.options_updater):
            return
        serialised_connections = [
            {"unit": unit_key, "surface": surface_key}
            for unit_key, surface_key in sorted(self.manual_connections)
        ]
        self.options_updater({"manual_connections": serialised_connections})

    def _load_manual_units(self):
        """Load manual STm unit nodes from the table options."""
        options = {}
        if callable(self.options_provider):
            options = self.options_provider() or {}

        manual_units = []
        for unit_info in options.get("manual_units", []):
            if not isinstance(unit_info, dict):
                continue
            feature_name = str(unit_info.get("feature", "")).strip()
            unit_role = normalise_structural_topology_unit_role(
                unit_info.get("unit_role", "SU")
            )
            if not feature_name or unit_role == "Discontinuity":
                continue
            unit_id = str(unit_info.get("id", "")).strip()
            if not unit_id:
                unit_id = md5(
                    f"{feature_name}:{len(manual_units)}".encode("utf-8")
                ).hexdigest()[:10]
            domains = []
            for domain_info in unit_info.get("domains", []):
                if not isinstance(domain_info, dict):
                    continue
                domain_column = str(domain_info.get("column", "")).strip()
                domain_value = str(domain_info.get("value", "")).strip()
                if domain_column and domain_value:
                    domains.append({"column": domain_column, "value": domain_value})
            manual_units.append(
                {
                    "id": unit_id,
                    "feature": feature_name,
                    "unit_role": unit_role,
                    "structural_polarity": unit_info.get("structural_polarity", 0.0),
                    "plot_polarity": unit_info.get("plot_polarity", ""),
                    "display_name": str(
                        unit_info.get("display_name", feature_name)
                    ).strip() or feature_name,
                    "domains": domains,
                    "color_R": unit_info.get("color_R", 255),
                    "color_G": unit_info.get("color_G", 255),
                    "color_B": unit_info.get("color_B", 255),
                }
            )
        return manual_units

    def _save_manual_units(self):
        """Persist manual STm unit nodes."""
        if not callable(self.options_updater):
            return
        self.options_updater({"manual_units": list(self.manual_units)})

    def _load_unit_renames(self):
        """Load display-name overrides for automatically generated STm units."""
        options = {}
        if callable(self.options_provider):
            options = self.options_provider() or {}

        unit_renames = {}
        raw_renames = options.get("unit_renames", {})
        if not isinstance(raw_renames, dict):
            return unit_renames
        for unit_key, unit_name in raw_renames.items():
            key_text = str(unit_key or "").strip()
            name_text = str(unit_name or "").strip()
            if (
                not key_text.startswith("unit:")
                or key_text.startswith("unit:manual:")
                or not name_text
            ):
                continue
            unit_renames[key_text] = name_text
        return unit_renames

    def _save_unit_renames(self):
        """Persist display-name overrides for automatically generated STm units."""
        if not callable(self.options_updater):
            return
        self.options_updater({"unit_renames": dict(self.unit_renames)})

    def _make_manual_unit_id(self, feature_name):
        """Return a stable-ish unique id for a manual unit."""
        base_id = md5(str(feature_name or "").encode("utf-8")).hexdigest()[:10]
        existing_ids = {str(unit_info.get("id", "")) for unit_info in self.manual_units}
        if base_id not in existing_ids:
            return base_id
        suffix = 1
        while f"{base_id}_{suffix}" in existing_ids:
            suffix += 1
        return f"{base_id}_{suffix}"

    def _current_domain_columns(self):
        """Return currently available STm domain columns for manual unit input."""
        dataframe = pd_DataFrame()
        if callable(self.dataframe_provider):
            current_df = self.dataframe_provider()
            if current_df is not None:
                dataframe = current_df.copy()
        domain_columns = []
        for column_name in dataframe.columns.tolist():
            if structural_topology_domain_order(column_name) is not None:
                domain_columns.append(str(column_name))
        return sorted(
            domain_columns or ["Domain_1"],
            key=lambda column_name: structural_topology_domain_order(column_name) or 1,
        )

    def _manual_unit_domain_columns(self, unit_info=None):
        """Return domain columns needed to edit one extra unit."""
        domain_columns = list(self._current_domain_columns())
        for domain_info in (unit_info or {}).get("domains", []):
            if not isinstance(domain_info, dict):
                continue
            domain_column = str(domain_info.get("column", "")).strip()
            if domain_column and domain_column not in domain_columns:
                domain_columns.append(domain_column)
        return sorted(
            domain_columns or ["Domain_1"],
            key=lambda column_name: (
                structural_topology_domain_order(column_name) or 1,
                str(column_name),
            ),
        )

    def add_manual_unit(self):
        """Add a persisted unit node that is not generated by the STm table."""
        if not self.editing_enabled:
            return
        dialog = ManualSTmUnitDialog(
            parent=self,
            domain_columns=self._manual_unit_domain_columns(),
        )
        if dialog.exec() != QDialog.Accepted:
            return
        unit_info = dialog.unit_info
        unit_info["id"] = self._make_manual_unit_id(unit_info["feature"])
        self.manual_units.append(unit_info)
        self._save_manual_units()
        self.rebuild_scene()
        self.update_editing_ui()

    def edit_selected_manual_unit(self):
        """Edit the selected persisted extra unit without changing its id."""
        if not self.editing_enabled:
            return
        unit_id = self._selected_manual_unit_id()
        if not unit_id:
            return
        unit_idx = None
        current_unit = None
        for idx, unit_info in enumerate(self.manual_units):
            if str(unit_info.get("id", "")) == unit_id:
                unit_idx = idx
                current_unit = dict(unit_info)
                break
        if current_unit is None:
            return

        dialog = ManualSTmUnitDialog(
            parent=self,
            domain_columns=self._manual_unit_domain_columns(current_unit),
            unit_info=current_unit,
        )
        if dialog.exec() != QDialog.Accepted:
            return
        updated_unit = dialog.unit_info
        updated_unit["id"] = unit_id
        self.manual_units[unit_idx] = updated_unit
        self._save_manual_units()
        self.rebuild_scene()
        self.update_editing_ui()

    def _selected_manual_unit_id(self):
        """Return the selected extra unit id, if an extra unit is selected."""
        node_key = str(self.selected_node_key or "")
        prefix = "unit:manual:"
        if not node_key.startswith(prefix):
            return None
        return node_key[len(prefix) :].strip() or None

    def _selected_generated_unit_key(self):
        """Return the selected generated unit key, if one is selected."""
        node_key = str(self.selected_node_key or "").strip()
        if (
            not node_key.startswith("unit:")
            or node_key.startswith("unit:manual:")
            or node_key not in self.node_items
        ):
            return None
        if self.node_items[node_key].get("side") != "unit":
            return None
        return node_key

    def rename_selected_generated_unit(self):
        """Rename only the selected automatically generated unit node."""
        if not self.editing_enabled:
            return
        unit_key = self._selected_generated_unit_key()
        if not unit_key:
            return
        node_info = self.node_items.get(unit_key, {})
        default_name = str(node_info.get("default_label", "")).strip()
        current_name = str(
            self.unit_renames.get(unit_key, node_info.get("label", default_name))
        ).strip()
        new_name = input_text_dialog(
            parent=self,
            title="Rename unit",
            label="Unit name",
            default_text=current_name or default_name,
        )
        if not new_name:
            return
        new_name = str(new_name).strip()
        if not new_name:
            return
        if default_name and new_name == default_name:
            self.unit_renames.pop(unit_key, None)
        else:
            self.unit_renames[unit_key] = new_name
        self._save_unit_renames()
        self.rebuild_scene()
        if unit_key in self.node_items:
            self.selected_node_key = unit_key
        else:
            self.selected_node_key = None
        self._update_node_highlight()
        self.update_editing_ui()

    def remove_selected_manual_unit(self):
        """Remove the selected extra unit and any links attached to it."""
        if not self.editing_enabled:
            return
        unit_id = self._selected_manual_unit_id()
        if not unit_id:
            return
        unit_key = f"unit:manual:{unit_id}"
        self.manual_units = [
            unit_info
            for unit_info in self.manual_units
            if str(unit_info.get("id", "")) != unit_id
        ]
        self.manual_connections = {
            connection
            for connection in self.manual_connections
            if connection[0] != unit_key
        }
        self._save_manual_units()
        self._save_manual_connections()
        self.clear_selection()
        self.rebuild_scene()
        self.update_editing_ui()

    def _draw_manual_connections(self):
        """Draw persisted manual links between unit and surface nodes."""
        valid_connections = set()
        for unit_key, surface_key in self.manual_connections:
            source_item = self.node_items.get(unit_key)
            target_item = self.node_items.get(surface_key)
            if source_item is None or target_item is None:
                continue
            valid_connections.add((unit_key, surface_key))
            if (unit_key, surface_key) in self.representative_connections:
                line_color = QColor(
                    source_item.get(
                        "base_pen_color", QColor(15, 15, 15)
                    )
                )
            else:
                line_color = QColor(15, 15, 15)
            line_pen = QPen(line_color)
            line_pen.setWidth(5)
            self.scene.addLine(
                source_item["right_anchor"][0],
                source_item["right_anchor"][1],
                target_item["left_anchor"][0],
                target_item["left_anchor"][1],
                line_pen,
            ).setZValue(-8)
        if valid_connections != self.manual_connections:
            self.manual_connections = valid_connections
            self._save_manual_connections()

    def clear_selection(self):
        """Clear the active node selection."""
        self.selected_node_key = None
        self.selected_domain_key = None
        self._update_node_highlight()
        self.update_editing_ui()

    def clear_manual_connections(self):
        """Remove all persisted manual links."""
        if not self.editing_enabled:
            return
        removable_connections = (
            self.manual_connections - self.representative_connections
        )
        if not removable_connections:
            return
        self.manual_connections.difference_update(removable_connections)
        self._save_manual_connections()
        self.clear_selection()
        self.rebuild_scene()
        self.update_editing_ui()

    def on_node_clicked(self, node_key=None):
        """Handle clicks on graph nodes to build/remove manual links."""
        if not self.editing_enabled:
            return
        node_key = str(node_key or "").strip()
        if node_key not in self.node_items:
            self.clear_selection()
            return

        if self.selected_domain_key is not None:
            if self._connect_domain_to_surface(self.selected_domain_key, node_key):
                return
            self.selected_domain_key = None
            self.selected_node_key = node_key
            self._update_node_highlight()
            self.update_editing_ui()
            return

        if self.selected_node_key is None:
            self.selected_node_key = node_key
            self.selected_domain_key = None
            self._update_node_highlight()
            self.update_editing_ui()
            return

        if self.selected_node_key == node_key:
            self.clear_selection()
            return

        source_info = self.node_items.get(self.selected_node_key)
        target_info = self.node_items.get(node_key)
        if source_info is None or target_info is None:
            self.clear_selection()
            return

        if source_info["side"] == target_info["side"]:
            self.selected_node_key = node_key
            self.selected_domain_key = None
            self._update_node_highlight()
            self.update_editing_ui()
            return

        if source_info["side"] == "unit":
            connection_key = (self.selected_node_key, node_key)
        else:
            connection_key = (node_key, self.selected_node_key)

        if connection_key in self.representative_connections:
            # Generated unit/representative-surface links are structural and
            # cannot be toggled from the graph.
            self.clear_selection()
            return
        if connection_key in self.manual_connections:
            self.manual_connections.remove(connection_key)
        else:
            self.manual_connections.add(connection_key)

        self._save_manual_connections()
        self.selected_node_key = None
        self.selected_domain_key = None
        self.rebuild_scene()
        self.update_editing_ui()

    def on_domain_clicked(self, domain_key=None):
        """Select a domain box or connect it to a selected external surface."""
        if not self.editing_enabled:
            return
        domain_key = str(domain_key or "").strip()
        if domain_key not in self.domain_items:
            self.clear_selection()
            return

        if self.selected_node_key is not None:
            if self._connect_domain_to_surface(domain_key, self.selected_node_key):
                return
            self.selected_node_key = None

        if self.selected_domain_key == domain_key:
            self.clear_selection()
            return

        self.selected_domain_key = domain_key
        self.selected_node_key = None
        self._update_node_highlight()
        self.update_editing_ui()

    def _connect_domain_to_surface(self, domain_key, surface_key) -> bool:
        """Toggle manual links from all domain units to an external surface."""
        domain_info = self.domain_items.get(str(domain_key or ""))
        surface_info = self.node_items.get(str(surface_key or ""))
        if domain_info is None or surface_info is None:
            return False
        if surface_info.get("side") != "surface":
            return False

        surface_key = str(surface_key)
        if surface_key in set(domain_info.get("surface_keys", [])):
            return False

        unit_keys = [
            unit_key
            for unit_key in domain_info.get("unit_keys", [])
            if unit_key in self.node_items
        ]
        if not unit_keys:
            return False

        connection_keys = {(unit_key, surface_key) for unit_key in unit_keys}
        # Bulk-toggle domain links: if every domain unit is already linked to the
        # selected surface, remove all those links; if none or only some are linked,
        # add the missing links so the whole domain becomes connected.
        if connection_keys.issubset(self.manual_connections):
            self.manual_connections.difference_update(
                connection_keys - self.representative_connections
            )
        else:
            self.manual_connections.update(connection_keys)

        self._save_manual_connections()
        self.selected_node_key = None
        self.selected_domain_key = None
        self.rebuild_scene()
        self.update_editing_ui()
        return True

    def _update_node_highlight(self):
        """Refresh node highlight based on the current selection."""
        for node_key, node_info in self.node_items.items():
            outline_pen = QPen(node_info["base_pen_color"])
            outline_pen.setWidth(6 if node_key == self.selected_node_key else 3)
            if node_key == self.selected_node_key:
                outline_pen.setColor(QColor(0, 140, 255))
            node_info["rect_item"].setPen(outline_pen)
        for domain_key, domain_info in self.domain_items.items():
            outline_pen = QPen(domain_info["base_pen_color"])
            outline_pen.setWidth(5 if domain_key == self.selected_domain_key else 3)
            outline_pen.setStyle(Qt.DashLine)
            if domain_key == self.selected_domain_key:
                outline_pen.setColor(QColor(0, 140, 255))
            domain_info["rect_item"].setPen(outline_pen)

    def _add_node(
        self,
        center_x=None,
        center_y=None,
        label=None,
        fill_color=None,
        outline_color=None,
        node_key=None,
        node_side=None,
    ):
        """Add a rounded graph node and return its geometry metadata."""
        font = QFont()
        font.setPointSize(20)
        font_metrics = QFontMetrics(font)
        text_width = font_metrics.horizontalAdvance(str(label))
        text_height = font_metrics.height()
        rect_width = max(self.NODE_MIN_WIDTH, text_width + 2 * self.NODE_PADDING_X)
        rect_height = self.NODE_HEIGHT
        rect_x = center_x - rect_width / 2
        rect_y = center_y - rect_height / 2

        rect_pen = QPen(outline_color or QColor(30, 30, 30))
        rect_pen.setWidth(3)
        rect_item = self.scene.addRect(
            rect_x, rect_y, rect_width, rect_height, rect_pen, QBrush(fill_color)
        )
        rect_item.setZValue(0)
        rect_item.setData(0, node_key)

        text_item = self.scene.addText(str(label), font)
        text_rect = text_item.boundingRect()
        text_item.setPos(
            center_x - text_rect.width() / 2,
            center_y - text_rect.height() / 2 - 4,
        )
        text_item.setDefaultTextColor(QColor(20, 20, 20))
        text_item.setZValue(1)
        text_item.setData(0, node_key)

        return {
            "rect": (rect_x, rect_y, rect_width, rect_height),
            "left_anchor": (rect_x, center_y),
            "right_anchor": (rect_x + rect_width, center_y),
            "top": rect_y,
            "bottom": rect_y + rect_height,
            "left": rect_x,
            "right": rect_x + rect_width,
            "rect_item": rect_item,
            "text_item": text_item,
            "label": str(label),
            "side": str(node_side or ""),
            "base_pen_color": outline_color or QColor(30, 30, 30),
        }

    def _add_domain_boxes(self, domain_groups=None, node_items=None):
        """Draw domain boxes around nodes sharing the same domain value."""
        domain_groups = domain_groups or {}
        node_items = node_items or {}

        for (domain_column, domain_value), group_info in domain_groups.items():
            if len(group_info.get("rows", set())) < 2:
                continue
            node_keys = group_info.get("nodes", set())
            available_nodes = [
                node_items[node_key]
                for node_key in node_keys
                if node_key in node_items
                and node_items[node_key].get("side") == "unit"
            ]
            if len(available_nodes) < 2:
                continue

            unit_keys = sorted(
                [
                    node_key
                    for node_key in node_keys
                    if node_key in node_items
                    and node_items[node_key].get("side") == "unit"
                ],
                key=str.casefold,
            )
            surface_keys = sorted(
                [
                    node_key
                    for node_key in node_keys
                    if node_key in node_items
                    and node_items[node_key].get("side") == "surface"
                ],
                key=str.casefold,
            )
            order_value = structural_topology_domain_order(domain_column) or 1
            margin = self.DOMAIN_MARGIN + (order_value - 1) * 14
            left = min(node_info["left"] for node_info in available_nodes) - margin
            right = max(node_info["right"] for node_info in available_nodes) + margin
            top = min(node_info["top"] for node_info in available_nodes) - margin
            bottom = max(node_info["bottom"] for node_info in available_nodes) + margin

            domain_color = structural_topology_color(f"{domain_column}:{domain_value}").darker(135)
            domain_pen = QPen(domain_color)
            domain_pen.setWidth(3)
            domain_pen.setStyle(Qt.DashLine)
            domain_key = f"domain:{domain_column}:{domain_value}"
            domain_brush_color = QColor(domain_color)
            domain_brush_color.setAlpha(1)
            domain_rect = self.scene.addRect(
                left,
                top,
                right - left,
                bottom - top,
                domain_pen,
                QBrush(domain_brush_color),
            )
            domain_rect.setZValue(-25 - order_value)
            domain_rect.setData(0, domain_key)

            domain_label = self.scene.addText(f"D{order_value}: {domain_value}")
            domain_label.setDefaultTextColor(domain_color)
            domain_label.setPos(left + 12, top - 30)
            domain_label.setZValue(-24 - order_value)
            domain_label.setData(0, domain_key)
            self.domain_items[domain_key] = {
                "rect_item": domain_rect,
                "label_item": domain_label,
                "unit_keys": unit_keys,
                "surface_keys": surface_keys,
                "base_pen_color": domain_color,
            }


class ComboBoxItemDelegate(QStyledItemDelegate):
    """Simple combo-box delegate for inline enumerated values."""

    def __init__(self, values=None, parent=None):
        super().__init__(parent)
        self.values = [str(value) for value in (values or [])]

    def createEditor(self, parent, option, index):
        del option, index
        combo = QComboBox(parent)
        combo.addItems(self.values)
        combo.activated.connect(lambda *_: self.commitData.emit(combo))
        combo.activated.connect(lambda *_: self.closeEditor.emit(combo))
        QTimer.singleShot(0, combo.showPopup)
        return combo

    def setEditorData(self, editor, index):
        current_value = "" if index.data(Qt.EditRole) is None else str(index.data(Qt.EditRole))
        found_index = editor.findText(current_value)
        editor.setCurrentIndex(found_index if found_index >= 0 else 0)

    def setModelData(self, editor, model, index):
        model.setData(index, editor.currentText(), Qt.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        del index
        editor.setGeometry(option.rect)


class EditableDataFrameModel(QAbstractTableModel):
    """Expose a pandas dataframe as a simple editable Qt table model."""

    def __init__(self, dataframe=None, parent=None, model_kind="main"):
        super().__init__(parent)
        self._dataframe = dataframe if dataframe is not None else pd_DataFrame()
        self._editable = False
        self._show_colormap_preview = False
        self.model_kind = str(model_kind or "main")

    @property
    def dataframe(self):
        return self._dataframe

    def set_dataframe(self, dataframe=None):
        self.beginResetModel()
        self._dataframe = dataframe if dataframe is not None else pd_DataFrame()
        self.endResetModel()

    @property
    def editable(self) -> bool:
        return self._editable

    def set_editable(self, editable: bool):
        self._editable = bool(editable)
        if self.rowCount() > 0 and self.columnCount() > 0:
            top_left = self.index(0, 0)
            bottom_right = self.index(
                self.rowCount() - 1, self.columnCount() - 1
            )
            self.dataChanged.emit(top_left, bottom_right, [Qt.DisplayRole, Qt.EditRole])
        self.layoutChanged.emit()

    def set_show_colormap_preview(self, show_preview: bool):
        """Enable/disable a virtual preview color column."""
        self.beginResetModel()
        self._show_colormap_preview = bool(show_preview)
        self.endResetModel()

    @property
    def show_colormap_preview(self) -> bool:
        return self._show_colormap_preview

    @property
    def preview_column_index(self) -> int:
        return self._dataframe.shape[1]

    def is_preview_column(self, column_index: int) -> bool:
        return self._show_colormap_preview and column_index == self.preview_column_index

    def _row_preview_color(self, row_index: int):
        """Return the preview QColor for a given row, if available."""
        required_columns = ["color_R", "color_G", "color_B"]
        if any(column not in self._dataframe.columns for column in required_columns):
            return None
        if row_index < 0 or row_index >= self._dataframe.shape[0]:
            return None

        try:
            red = int(float(self._dataframe.iloc[row_index][required_columns[0]]))
            green = int(float(self._dataframe.iloc[row_index][required_columns[1]]))
            blue = int(float(self._dataframe.iloc[row_index][required_columns[2]]))
        except Exception:
            return None

        red = max(0, min(255, red))
        green = max(0, min(255, green))
        blue = max(0, min(255, blue))
        return QColor(red, green, blue)

    def rowCount(self, parent=None):
        return 0 if parent and parent.isValid() else self._dataframe.shape[0]

    def columnCount(self, parent=None):
        if parent and parent.isValid():
            return 0
        return self._dataframe.shape[1] + (1 if self._show_colormap_preview else 0)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        if self.is_preview_column(index.column()):
            preview_color = self._row_preview_color(index.row())
            if role == Qt.DisplayRole:
                return ""
            if role == Qt.BackgroundRole and preview_color is not None:
                return QBrush(preview_color)
            return None
        if role not in (Qt.DisplayRole, Qt.EditRole):
            return None
        if (
            role == Qt.DisplayRole
            and self.model_kind == "boundaries"
            and str(self._dataframe.columns[index.column()])
            == STRUCTURAL_TOPOLOGY_BOUNDARY_POLARITY_COLUMN
            and is_structural_topology_model_boundary(
                self._dataframe.iloc[index.row()]
            )
        ):
            return ""
        value = self._dataframe.iloc[index.row(), index.column()]
        if pd_isna(value):
            return ""
        return str(value)

    def setData(self, index, value, role=Qt.EditRole):
        if (
            not index.isValid()
            or role != Qt.EditRole
            or self.is_preview_column(index.column())
        ):
            return False
        if self.parent() and hasattr(self.parent(), "is_table_model_column_editable"):
            if not self.parent().is_table_model_column_editable(
                self, index.column(), index.row()
            ):
                return False
        self._dataframe.iloc[index.row(), index.column()] = (
            "" if value is None else str(value)
        )
        self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.EditRole])
        preview_index = self.index(index.row(), self.preview_column_index)
        if self._show_colormap_preview:
            self.dataChanged.emit(preview_index, preview_index, [Qt.BackgroundRole])
        if self.parent() and hasattr(self.parent(), "on_table_model_edited"):
            self.parent().on_table_model_edited(
                row_index=index.row(),
                column_index=index.column(),
                table_model=self,
            )
        return True

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemIsEnabled
        flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        is_column_editable = True
        if self.parent() and hasattr(self.parent(), "is_table_model_column_editable"):
            is_column_editable = self.parent().is_table_model_column_editable(
                self, index.column(), index.row()
            )
        if (
            self._editable
            and not self.is_preview_column(index.column())
            and is_column_editable
        ):
            flags |= Qt.ItemIsEditable
        return flags

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            if self.is_preview_column(section):
                return "Color"
            try:
                return str(self._dataframe.columns[section])
            except Exception:
                return None
        return str(section + 1)

    def update_row_color(self, row_index: int, color=None):
        """Update the RGB values of a row and refresh the preview column."""
        if color is None or not isinstance(color, QColor):
            return
        required_columns = ["color_R", "color_G", "color_B"]
        if any(column not in self._dataframe.columns for column in required_columns):
            return
        if row_index < 0 or row_index >= self._dataframe.shape[0]:
            return

        self._dataframe.at[row_index, "color_R"] = color.red()
        self._dataframe.at[row_index, "color_G"] = color.green()
        self._dataframe.at[row_index, "color_B"] = color.blue()

        left_col = min(self._dataframe.columns.get_loc("color_R"), self.preview_column_index)
        right_col = max(self._dataframe.columns.get_loc("color_B"), self.preview_column_index)
        top_left = self.index(row_index, left_col)
        bottom_right = self.index(row_index, right_col)
        self.dataChanged.emit(
            top_left,
            bottom_right,
            [Qt.DisplayRole, Qt.EditRole, Qt.BackgroundRole],
        )
        if self.parent() and hasattr(self.parent(), "on_table_model_edited"):
            self.parent().on_table_model_edited(table_model=self)

    def add_empty_row(self):
        row_data = {column: "" for column in self._dataframe.columns.tolist()}
        self.beginResetModel()
        self._dataframe.loc[len(self._dataframe.index)] = row_data
        self.endResetModel()

    def add_row_data(self, row_data=None):
        """Append a row using a partial/full dictionary of column values."""
        row_data = row_data or {}
        out_row = {
            column_name: row_data.get(column_name, "")
            for column_name in self._dataframe.columns.tolist()
        }
        self.beginResetModel()
        self._dataframe.loc[len(self._dataframe.index)] = out_row
        self.endResetModel()

    def remove_rows(self, row_indexes=None):
        if not row_indexes:
            return
        self.beginResetModel()
        self._dataframe.drop(index=row_indexes, inplace=True)
        self._dataframe.reset_index(drop=True, inplace=True)
        self.endResetModel()

    def add_column(self, column_name: str):
        self.beginResetModel()
        self._dataframe[column_name] = ""
        self.endResetModel()

    def remove_column(self, column_name: str):
        self.beginResetModel()
        self._dataframe.drop(columns=[column_name], inplace=True)
        self.endResetModel()


class NewTableDialog(QDialog):
    """Dialog used to create a new custom table and its initial fields."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Table")
        self.resize(420, 360)

        layout = QVBoxLayout(self)

        name_label = QLabel("Table name")
        self.table_name_edit = QLineEdit()
        self.table_name_edit.setPlaceholderText("table_name")
        layout.addWidget(name_label)
        layout.addWidget(self.table_name_edit)

        fields_label = QLabel("Attribute fields")
        layout.addWidget(fields_label)

        field_row = QHBoxLayout()
        self.field_name_edit = QLineEdit()
        self.field_name_edit.setPlaceholderText("field_name")
        add_field_button = QPushButton("Add field")
        add_field_button.clicked.connect(self.add_field)
        field_row.addWidget(self.field_name_edit)
        field_row.addWidget(add_field_button)
        layout.addLayout(field_row)

        self.fields_list = QListWidget()
        layout.addWidget(self.fields_list)

        remove_field_button = QPushButton("Remove selected field")
        remove_field_button.clicked.connect(self.remove_selected_field)
        layout.addWidget(remove_field_button)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def table_name(self) -> str:
        return self.table_name_edit.text().strip()

    @property
    def field_names(self) -> list:
        return [
            self.fields_list.item(index).text().strip()
            for index in range(self.fields_list.count())
        ]

    def add_field(self):
        field_name = self.field_name_edit.text().strip()
        if not field_name:
            return
        if field_name in self.field_names:
            QMessageBox.warning(
                self,
                "Duplicate field",
                f'The field "{field_name}" already exists.',
            )
            return
        self.fields_list.addItem(field_name)
        self.field_name_edit.clear()
        self.field_name_edit.setFocus()

    def remove_selected_field(self):
        current_row = self.fields_list.currentRow()
        if current_row >= 0:
            self.fields_list.takeItem(current_row)

    def validate_and_accept(self):
        if not self.table_name:
            QMessageBox.warning(self, "Missing name", "Insert a table name.")
            return
        self.accept()


class NewColormapTableDialog(QDialog):
    """Dialog used to create a new advanced colormap table."""

    mode_options = {
        "Continuous": "continuous",
        "Exact intervals": "discrete",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Colormap Table")
        self.resize(420, 180)

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        self.table_name_edit = QLineEdit()
        self.table_name_edit.setPlaceholderText("colormap_name")
        form_layout.addRow("Table name", self.table_name_edit)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(list(self.mode_options.keys()))
        form_layout.addRow("Color mode", self.mode_combo)

        layout.addLayout(form_layout)

        info_label = QLabel(
            "A colormap table stores value-color stops and will be available in the project legend."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def table_name(self) -> str:
        return self.table_name_edit.text().strip()

    @property
    def mode(self) -> str:
        return self.mode_options[self.mode_combo.currentText()]

    def validate_and_accept(self):
        if not self.table_name:
            QMessageBox.warning(self, "Missing name", "Insert a table name.")
            return
        self.accept()


class NewStructuralTopologyTableDialog(QDialog):
    """Dialog used to create a new STm table."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Structural Topology Model")
        self.resize(440, 170)

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        self.table_name_edit = QLineEdit()
        self.table_name_edit.setPlaceholderText("stm_name")
        form_layout.addRow("Table name", self.table_name_edit)
        layout.addLayout(form_layout)

        info_label = QLabel(
            "The Structural Topology model starts from geology legend units and keeps their level linked to the legend."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def table_name(self) -> str:
        return self.table_name_edit.text().strip()

    def validate_and_accept(self):
        if not self.table_name:
            QMessageBox.warning(self, "Missing name", "Insert a table name.")
            return
        self.accept()


class ImportStructuralTopologyUnitsDialog(QDialog):
    """Dialog used to import legend boundaries into an STm table."""

    def __init__(
        self, parent=None, units_provider=None, existing_boundaries=None
    ):
        super().__init__(parent)
        self.setWindowTitle("Import boundaries")
        self.resize(460, 420)
        self.units_provider = units_provider
        self.existing_boundaries = dict(existing_boundaries or {})

        layout = QVBoxLayout(self)
        info_label = QLabel(
            "Select geological legend boundaries to add to the Structural Topology model."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        refresh_button = QPushButton("Refresh boundaries")
        refresh_button.clicked.connect(self.populate_units)
        layout.addWidget(refresh_button)

        self.units_list = QListWidget()
        layout.addWidget(self.units_list)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.populate_units()

    @property
    def selected_units(self):
        selected_units = []
        for row_idx in range(self.units_list.count()):
            item = self.units_list.item(row_idx)
            if (
                item.flags() & Qt.ItemIsEnabled
                and item.checkState() == Qt.Checked
            ):
                selected_units.append(item.data(Qt.UserRole))
        return selected_units

    def populate_units(self):
        self.units_list.clear()
        units = []
        if callable(self.units_provider):
            units = list(self.units_provider() or [])

        if not units:
            self.units_list.addItem(
                QListWidgetItem("No geological legend boundaries available.")
            )
            self.units_list.item(0).setFlags(Qt.NoItemFlags)
            return

        for unit_info in units:
            unit_name = str(
                unit_info.get(STRUCTURAL_TOPOLOGY_FEATURE_COLUMN, "")
            ).strip()
            role_name = str(unit_info.get("role", "")).strip()
            if role_name.upper() in STRUCTURAL_TOPOLOGY_NON_BOUNDARY_ROLES:
                continue
            role_name = normalise_structural_topology_boundary_role(role_name)
            if role_name not in STRUCTURAL_TOPOLOGY_BOUNDARY_ROLE_VALUES:
                continue
            if role_name == "model_boundary":
                continue
            polarity_value = str(
                unit_info.get(STRUCTURAL_TOPOLOGY_POLARITY_COLUMN, "")
            ).strip()
            item = QListWidgetItem(
                f"{unit_name} — {role_name}" if role_name else unit_name
            )
            item.setData(Qt.UserRole, dict(unit_info))
            tooltip_txt = f"Level: {polarity_value}"
            if role_name:
                tooltip_txt += f"\nRole: {role_name}"
            item.setToolTip(tooltip_txt)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            if unit_name in self.existing_boundaries:
                item.setCheckState(
                    Qt.Checked
                    if self.existing_boundaries[unit_name].casefold()
                    == role_name.casefold()
                    else Qt.Unchecked
                )
                item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
            else:
                item.setCheckState(Qt.Unchecked)
            self.units_list.addItem(item)

        if self.units_list.count() == 0:
            item = QListWidgetItem(
                "No boundaries available after filtering unit roles."
            )
            item.setFlags(Qt.NoItemFlags)
            self.units_list.addItem(item)

    def validate_and_accept(self):
        if not self.selected_units:
            QMessageBox.warning(
                self,
                "No boundaries selected",
                "Select at least one boundary to import.",
            )
            return
        self.accept()


class AddModelBoundaryDialog(QDialog):
    """Select one project boundary or create a theoretical model boundary."""

    def __init__(self, parent=None, boundary_sources=None):
        super().__init__(parent)
        self.setWindowTitle("Add model boundary")
        self.resize(460, 180)

        layout = QVBoxLayout(self)
        info_label = QLabel(
            "Select one boundary from the Boundary collection, or add a "
            "theoretical model boundary. Only one model boundary can belong "
            "to an STm."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        form = QFormLayout()
        self.boundary_combo = QComboBox()
        self.boundary_combo.addItem(
            "Add extra theoretical boundary",
            {
                "kind": "extra",
                "name": STRUCTURAL_TOPOLOGY_MODEL_BOUNDARY,
                "color_R": 255,
                "color_G": 255,
                "color_B": 255,
            },
        )
        for source_info in boundary_sources or []:
            if not isinstance(source_info, dict):
                continue
            source_name = str(source_info.get("name", "")).strip()
            if not source_name:
                continue
            source_payload = dict(source_info)
            source_payload["kind"] = "collection"
            source_payload["name"] = source_name
            self.boundary_combo.addItem(source_name, source_payload)
        form.addRow("Model boundary", self.boundary_combo)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def source_info(self):
        return dict(self.boundary_combo.currentData() or {})

    @property
    def boundary_info(self):
        source_info = self.source_info
        return {
            STRUCTURAL_TOPOLOGY_FEATURE_COLUMN: str(
                source_info.get("name", STRUCTURAL_TOPOLOGY_MODEL_BOUNDARY)
            ).strip()
            or STRUCTURAL_TOPOLOGY_MODEL_BOUNDARY,
            STRUCTURAL_TOPOLOGY_BOUNDARY_ROLE_COLUMN: "model_boundary",
            STRUCTURAL_TOPOLOGY_BOUNDARY_POLARITY_COLUMN: "-inf",
            STRUCTURAL_TOPOLOGY_BOUNDARY_UNITS_COLUMN: "",
            "color_R": source_info.get("color_R", 255),
            "color_G": source_info.get("color_G", 255),
            "color_B": source_info.get("color_B", 255),
        }


class ExtraSTmBoundaryDialog(QDialog):
    """Collect the values needed for a boundary absent from the project."""

    def __init__(self, parent=None, boundary_info=None):
        super().__init__(parent)
        boundary_info = boundary_info or {}
        self.selected_color = structural_topology_color(
            boundary_info.get(STRUCTURAL_TOPOLOGY_FEATURE_COLUMN, "extra_boundary")
        )
        try:
            self.selected_color = QColor(
                int(float(boundary_info.get("color_R", self.selected_color.red()))),
                int(float(boundary_info.get("color_G", self.selected_color.green()))),
                int(float(boundary_info.get("color_B", self.selected_color.blue()))),
            )
        except (TypeError, ValueError):
            pass
        self.setWindowTitle("Add extra boundary")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.feature_edit = QLineEdit(
            str(boundary_info.get(STRUCTURAL_TOPOLOGY_FEATURE_COLUMN, ""))
        )
        self.role_edit = QComboBox()
        self.role_edit.addItems(
            [
                role_name
                for role_name in STRUCTURAL_TOPOLOGY_BOUNDARY_ROLE_VALUES
                if role_name != "model_boundary"
            ]
        )
        self.role_edit.setCurrentText(
            normalise_structural_topology_boundary_role(
                boundary_info.get(STRUCTURAL_TOPOLOGY_BOUNDARY_ROLE_COLUMN, "")
            )
        )
        self.polarity_edit = QLineEdit(
            str(boundary_info.get(STRUCTURAL_TOPOLOGY_BOUNDARY_POLARITY_COLUMN, ""))
        )
        self.role_edit.currentTextChanged.connect(self._update_role_controls)
        form.addRow("Feature", self.feature_edit)
        form.addRow("Role", self.role_edit)
        form.addRow("Level", self.polarity_edit)
        color_layout = QHBoxLayout()
        self.color_button = QPushButton("")
        self.color_button.setFixedSize(54, 24)
        self.color_button.setToolTip("Choose boundary color")
        self.color_button.clicked.connect(self.choose_color)
        color_layout.addWidget(self.color_button)
        color_layout.addStretch(1)
        form.addRow("Color", color_layout)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._update_role_controls(self.role_edit.currentText())
        self._update_color_button()

    def choose_color(self):
        color_out = QColorDialog.getColor(self.selected_color, self)
        if not color_out.isValid():
            return
        self.selected_color = color_out
        self._update_color_button()

    def _update_color_button(self):
        self.color_button.setStyleSheet(
            "QPushButton { "
            f"background-color: rgb({self.selected_color.red()}, "
            f"{self.selected_color.green()}, {self.selected_color.blue()}); "
            "}"
        )

    def _update_role_controls(self, role_name):
        role_text = normalise_structural_topology_boundary_role(role_name)
        is_model_boundary = role_text == "model_boundary"
        self.polarity_edit.setEnabled(not is_model_boundary)
        if is_model_boundary:
            self.polarity_edit.setPlaceholderText("Managed by the model boundary")
        else:
            self.polarity_edit.setPlaceholderText("")

    @property
    def boundary_info(self):
        return {
            STRUCTURAL_TOPOLOGY_FEATURE_COLUMN: self.feature_edit.text().strip(),
            STRUCTURAL_TOPOLOGY_BOUNDARY_ROLE_COLUMN: self.role_edit.currentText().strip(),
            STRUCTURAL_TOPOLOGY_BOUNDARY_POLARITY_COLUMN: self.polarity_edit.text().strip(),
            STRUCTURAL_TOPOLOGY_BOUNDARY_UNITS_COLUMN: "",
            "color_R": self.selected_color.red(),
            "color_G": self.selected_color.green(),
            "color_B": self.selected_color.blue(),
        }

    def validate_and_accept(self):
        if not self.feature_edit.text().strip():
            QMessageBox.warning(self, "Missing feature", "Insert a boundary feature.")
            return
        role = self.role_edit.currentText().strip()
        if role not in STRUCTURAL_TOPOLOGY_BOUNDARY_ROLE_VALUES:
            QMessageBox.warning(
                self,
                "Invalid role",
                "Select a valid boundary role from the list.",
            )
            return
        polarity = self.polarity_edit.text().strip()
        if polarity:
            try:
                float(polarity)
            except ValueError:
                QMessageBox.warning(
                    self, "Invalid level", "Level must be numeric or empty."
                )
                return
        self.accept()


class UnitPolarityAmbiguityDialog(QDialog):
    """Resolve a permutation between existing discrete level gaps."""

    def __init__(self, parent, solutions, slots):
        super().__init__(parent)
        self.setWindowTitle("Resolve unit level")
        self.solutions = solutions
        self.solution_index = 0
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "These units have equivalent topological solutions.\n"
                "Use Switch to exchange their level."
            )
        )
        self.assignment_label = QLabel()
        layout.addWidget(self.assignment_label)
        switch_button = QPushButton("Switch")
        switch_button.clicked.connect(self.switch_assignment)
        layout.addWidget(switch_button)
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.slots = slots
        self.update_assignment_label()

    @property
    def assignments(self):
        return self.solutions[self.solution_index]

    def switch_assignment(self):
        self.solution_index = (self.solution_index + 1) % len(self.solutions)
        self.update_assignment_label()
        #debug
        print(
            "[STm polarity] switched ambiguity:",
            {
                unit_name: self.slots[slot_key]["value"]
                for unit_name, slot_key in self.assignments.items()
            },
        )

    def update_assignment_label(self):
        self.assignment_label.setText(
            "\n".join(
                f"{unit_name}: {self.slots[slot_key]['value']:g}"
                for unit_name, slot_key in sorted(self.assignments.items())
            )
        )


class ViewTable(QWidget):
    """Dockable view that lists and edits user-defined project tables."""

    EXPORT_FILTER = (
        "STm JSON files (*.json);;"
        "CSV files (*.csv);;"
        "Tab-separated text (*.tsv);;"
        "Text files (*.txt);;"
        "DAT files (*.dat);;"
        "All files (*.*)"
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setWindowTitle("Table View")
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.editing_enabled = False

        main_layout = QHBoxLayout(self)
        self.setLayout(main_layout)

        left_panel = QWidget(self)
        left_layout = QVBoxLayout(left_panel)
        left_layout.addWidget(QLabel("Existing tables"))
        self.tables_list = QListWidget()
        self.tables_list.currentItemChanged.connect(self.on_table_selection_changed)
        left_layout.addWidget(self.tables_list)

        self.new_table_button = QPushButton("New table", self)
        self.new_table_button.setText("New table")
        self.new_table_menu = QMenu(self.new_table_button)
        self._populate_new_table_menu()
        self.new_table_button.setMenu(self.new_table_menu)
        self.new_table_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        left_layout.addWidget(self.new_table_button)

        self.delete_table_button = QPushButton("Delete table")
        self.delete_table_button.clicked.connect(self.delete_current_table)
        self.delete_table_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        left_layout.addWidget(self.delete_table_button)

        self.export_table_button = QPushButton("Export table")
        self.export_table_button.clicked.connect(self.export_current_table)
        self.export_table_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        left_layout.addWidget(self.export_table_button)

        right_panel = QWidget(self)
        right_layout = QVBoxLayout(right_panel)
        self.current_table_label = QLabel("No table selected")
        right_layout.addWidget(self.current_table_label)

        toolbar_layout = QHBoxLayout()
        self.editing_toggle_button = QPushButton("Enable editing")
        self.editing_toggle_button.setCheckable(True)
        self.editing_toggle_button.toggled.connect(self.on_editing_toggled)
        toolbar_layout.addWidget(self.editing_toggle_button)

        self.action_menu_bar = QMenuBar(self)
        self.action_menu_bar.setNativeMenuBar(False)
        self.action_menu_bar.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)

        self.add_menu = QMenu("Add", self.action_menu_bar)
        self.add_row_action = self.add_menu.addAction("Add row")
        self.add_row_action.triggered.connect(self.add_row)
        self.add_model_boundary_action = self.add_menu.addAction(
            "Add model boundary"
        )
        self.add_model_boundary_action.triggered.connect(self.add_model_boundary)
        self.add_extra_boundary_action = self.add_menu.addAction(
            "Add extra boundary"
        )
        self.add_extra_boundary_action.triggered.connect(self.add_extra_boundary)
        self.add_boundary_separator = self.add_menu.addSeparator()
        self.generate_units_action = self.add_menu.addAction(
            "Generate units from boundaries"
        )
        self.generate_units_action.triggered.connect(
            self.generate_units_from_boundaries
        )
        self.add_extra_unit_action = self.add_menu.addAction("Add extra unit")
        self.add_extra_unit_action.triggered.connect(self.add_extra_unit)
        self.add_unit_separator = self.add_menu.addSeparator()
        self.add_field_action = self.add_menu.addAction("Add field")
        self.add_field_action.triggered.connect(self.add_field)
        self.action_menu_bar.addMenu(self.add_menu)

        self.edit_menu = QMenu("Edit", self.action_menu_bar)
        self.delete_row_action = self.edit_menu.addAction("Delete row")
        self.delete_row_action.triggered.connect(self.delete_selected_rows)
        self.edit_field_separator = self.edit_menu.addSeparator()
        self.rename_field_action = self.edit_menu.addAction("Rename field")
        self.rename_field_action.triggered.connect(self.rename_field)
        self.delete_field_action = self.edit_menu.addAction("Delete field")
        self.delete_field_action.triggered.connect(self.delete_field)
        self.action_menu_bar.addMenu(self.edit_menu)
        toolbar_layout.addWidget(self.action_menu_bar)

        toolbar_layout.addStretch(1)
        self.build_stm_button = QPushButton("Open STm builder")
        self.build_stm_button.clicked.connect(self.build_structural_topology_model)
        toolbar_layout.addWidget(self.build_stm_button)
        right_layout.addLayout(toolbar_layout)

        self.boundaries_label = QLabel("Boundaries")
        right_layout.addWidget(self.boundaries_label)
        self.boundaries_table_view = QTableView()
        self.boundaries_table_view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.boundaries_table_view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.boundaries_table_view.setAlternatingRowColors(True)
        self.boundaries_table_view.horizontalHeader().setStretchLastSection(True)
        self.boundaries_table_view.horizontalHeader().setSectionResizeMode(
            QHeaderView.Interactive
        )
        self.boundaries_table_model = EditableDataFrameModel(
            parent=self, model_kind="boundaries"
        )
        self.boundaries_table_view.setModel(self.boundaries_table_model)
        right_layout.addWidget(self.boundaries_table_view, 1)

        self.units_label = QLabel("Units")
        right_layout.addWidget(self.units_label)
        self.table_view = QTableView()
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.table_view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table_view.setAlternatingRowColors(True)
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table_view.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.table_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_model = EditableDataFrameModel(parent=self, model_kind="units")
        self.table_view.setModel(self.table_model)
        self.table_view.clicked.connect(self.on_table_view_clicked)
        right_layout.addWidget(self.table_view, 1)

        left_panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        right_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        main_layout.addWidget(left_panel, 1)
        main_layout.addWidget(right_panel, 3)
        left_layout.addStretch(1)

        self.refresh_table_list()
        self.update_editing_ui()

    def showEvent(self, event):
        self.refresh_table_list(select_name=self.current_table_name)
        super().showEvent(event)

    def disconnect_all_signals(self):
        """Compatibility method required by DockWindow."""
        return

    def enable_actions(self):
        """Compatibility method required by DockWindow."""
        return

    @property
    def current_table_name(self):
        current_item = self.tables_list.currentItem()
        return current_item.text() if current_item else None

    @property
    def current_table_type(self):
        return self.parent.custom_table_types.get(self.current_table_name, "manual")

    @property
    def current_table_options(self):
        return self.parent.custom_table_options.get(self.current_table_name, {})

    def _normalise_stm_boundaries(self, dataframe=None):
        out_df = (
            dataframe.copy()
            if dataframe is not None
            else pd_DataFrame(columns=STRUCTURAL_TOPOLOGY_BOUNDARY_COLUMNS)
        )
        for column_name in STRUCTURAL_TOPOLOGY_BOUNDARY_COLUMNS:
            if column_name not in out_df.columns:
                out_df[column_name] = ""
        out_df = out_df[STRUCTURAL_TOPOLOGY_BOUNDARY_COLUMNS].copy()
        for row_label in out_df.index.tolist():
            out_df.at[row_label, STRUCTURAL_TOPOLOGY_BOUNDARY_ROLE_COLUMN] = (
                normalise_structural_topology_boundary_role(
                    out_df.at[
                        row_label, STRUCTURAL_TOPOLOGY_BOUNDARY_ROLE_COLUMN
                    ]
                )
            )
            out_df.at[row_label, STRUCTURAL_TOPOLOGY_BOUNDARY_UNITS_COLUMN] = (
                _stm_names_cell(
                    out_df.at[row_label, STRUCTURAL_TOPOLOGY_BOUNDARY_UNITS_COLUMN]
                )
            )
        model_mask = out_df.apply(
            is_structural_topology_model_boundary, axis=1
        )
        if model_mask.any():
            first_model_row = out_df.loc[model_mask].iloc[0].to_dict()
            model_units = []
            for raw_units in out_df.loc[
                model_mask, STRUCTURAL_TOPOLOGY_BOUNDARY_UNITS_COLUMN
            ]:
                model_units.extend(_stm_names(raw_units))
            out_df = out_df.loc[~model_mask].copy()
            feature_name = str(
                first_model_row.get(STRUCTURAL_TOPOLOGY_FEATURE_COLUMN, "")
            ).strip()
            if (
                not feature_name
                or feature_name.casefold()
                == STRUCTURAL_TOPOLOGY_MODEL_BOUNDARY.casefold()
            ):
                feature_name = STRUCTURAL_TOPOLOGY_MODEL_BOUNDARY
            first_model_row[STRUCTURAL_TOPOLOGY_FEATURE_COLUMN] = feature_name
            first_model_row[STRUCTURAL_TOPOLOGY_BOUNDARY_ROLE_COLUMN] = (
                "model_boundary"
            )
            first_model_row[STRUCTURAL_TOPOLOGY_BOUNDARY_POLARITY_COLUMN] = "-inf"
            first_model_row[STRUCTURAL_TOPOLOGY_BOUNDARY_UNITS_COLUMN] = (
                _stm_names_cell(model_units)
            )
            out_df = pd_concat(
                [pd_DataFrame([first_model_row], columns=out_df.columns), out_df],
                ignore_index=True,
            )
        return out_df.reset_index(drop=True)

    def _set_stm_feature_color(self, feature_name, color_info):
        """Persist one boundary/unit colour without exposing RGB table columns."""
        table_name = self.current_table_name
        feature_name = str(feature_name or "").strip()
        if not table_name or not feature_name:
            return
        options = dict(self.parent.custom_table_options.get(table_name, {}) or {})
        color_codes = dict(options.get("stm_color_codes", {}) or {})
        feature_colors = dict(color_codes.get("features", {}) or {})
        feature_colors[feature_name] = _stm_color_to_dict(color_info)
        color_codes["features"] = feature_colors
        options["stm_color_codes"] = color_codes
        self.parent.custom_table_options[table_name] = options

    def _stm_feature_colors(self):
        options = dict(self.current_table_options or {})
        color_codes = options.get("stm_color_codes", {})
        if not isinstance(color_codes, dict):
            return {}
        return {
            str(feature_name).strip(): _stm_color_to_dict(color_info)
            for feature_name, color_info in color_codes.get("features", {}).items()
            if str(feature_name).strip()
        }

    def _normalise_stm_units(self, dataframe=None):
        out_df = (
            dataframe.copy()
            if dataframe is not None
            else pd_DataFrame(columns=STRUCTURAL_TOPOLOGY_UNIT_COLUMNS)
        )
        if "Domain" in out_df.columns and "Domain_1" not in out_df.columns:
            out_df.rename(columns={"Domain": "Domain_1"}, inplace=True)
        out_df.drop(
            columns=[
                column_name
                for column_name in (
                    "color_R",
                    "color_G",
                    "color_B",
                )
                if column_name in out_df.columns
            ],
            inplace=True,
        )
        for column_name in STRUCTURAL_TOPOLOGY_UNIT_COLUMNS:
            if column_name not in out_df.columns:
                out_df[column_name] = ""
        for row_label in out_df.index.tolist():
            out_df.at[row_label, STRUCTURAL_TOPOLOGY_UNIT_ROLE_COLUMN] = (
                normalise_structural_topology_unit_role(
                    out_df.at[row_label, STRUCTURAL_TOPOLOGY_UNIT_ROLE_COLUMN]
                )
            )
            out_df.at[row_label, STRUCTURAL_TOPOLOGY_UNIT_BOUNDARIES_COLUMN] = (
                _stm_names_cell(
                    out_df.at[row_label, STRUCTURAL_TOPOLOGY_UNIT_BOUNDARIES_COLUMN]
                )
            )
            out_df.at[row_label, STRUCTURAL_TOPOLOGY_REPRESENTATIVE_BOUNDARY_FIELD] = (
                str(
                    out_df.at[
                        row_label,
                        STRUCTURAL_TOPOLOGY_REPRESENTATIVE_BOUNDARY_FIELD,
                    ]
                    or ""
                ).strip()
            )
        domain_columns = sorted(
            [
                column_name
                for column_name in out_df.columns
                if structural_topology_domain_order(column_name) is not None
            ],
            key=structural_topology_domain_order,
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
                    STRUCTURAL_TOPOLOGY_FEATURE_COLUMN,
                    STRUCTURAL_TOPOLOGY_UNIT_ROLE_COLUMN,
                    STRUCTURAL_TOPOLOGY_UNIT_POLARITY_COLUMN,
                    STRUCTURAL_TOPOLOGY_UNIT_BOUNDARIES_COLUMN,
                    STRUCTURAL_TOPOLOGY_REPRESENTATIVE_BOUNDARY_FIELD,
                ]
                + domain_columns
            )
        ]
        ordered_columns = [
            STRUCTURAL_TOPOLOGY_FEATURE_COLUMN,
            STRUCTURAL_TOPOLOGY_UNIT_ROLE_COLUMN,
            STRUCTURAL_TOPOLOGY_UNIT_POLARITY_COLUMN,
            STRUCTURAL_TOPOLOGY_UNIT_BOUNDARIES_COLUMN,
            STRUCTURAL_TOPOLOGY_REPRESENTATIVE_BOUNDARY_FIELD,
        ] + domain_columns + extra_columns
        return out_df[ordered_columns].reset_index(drop=True)

    def _load_stm_composite(self, table_name):
        options = dict(self.parent.custom_table_options.get(table_name, {}) or {})
        tables = options.get("stm_tables", {})
        if isinstance(tables, dict) and (
            "boundaries" in tables or "units" in tables
        ):
            boundary_records = list(tables.get("boundaries", []))
            unit_records = list(tables.get("units", []))
            recovered_colors = self._stm_feature_colors()
            representative_links = set()
            all_links = set()
            for record in boundary_records + unit_records:
                if not isinstance(record, dict):
                    continue
                feature_name = str(
                    record.get(STRUCTURAL_TOPOLOGY_FEATURE_COLUMN, "")
                ).strip()
                if feature_name and all(
                    channel in record
                    for channel in ("color_R", "color_G", "color_B")
                ):
                    recovered_colors[feature_name] = _stm_color_to_dict(record)
            for record in unit_records:
                if not isinstance(record, dict):
                    continue
                unit_name = str(
                    record.get(STRUCTURAL_TOPOLOGY_FEATURE_COLUMN, "")
                ).strip()
                if not unit_name:
                    continue
                for boundary_name in _stm_names(
                    record.get(STRUCTURAL_TOPOLOGY_UNIT_BOUNDARIES_COLUMN, "")
                ):
                    all_links.add((unit_name, boundary_name))
                representative_boundary = str(
                    record.get(
                        STRUCTURAL_TOPOLOGY_REPRESENTATIVE_BOUNDARY_FIELD, ""
                    )
                ).strip()
                if representative_boundary:
                    representative_links.add(
                        (unit_name, representative_boundary)
                    )
            if recovered_colors:
                color_codes = dict(options.get("stm_color_codes", {}) or {})
                color_codes["features"] = recovered_colors
                options["stm_color_codes"] = color_codes
            options["stm_representative_links"] = [
                {"unit": unit_name, "boundary": boundary_name}
                for unit_name, boundary_name in sorted(representative_links)
            ]
            options["stm_manual_links"] = [
                {"unit": unit_name, "boundary": boundary_name}
                for unit_name, boundary_name in sorted(
                    all_links - representative_links
                )
            ]
            self.parent.custom_table_options[table_name] = options
            boundaries = pd_DataFrame(boundary_records)
            units = pd_DataFrame(unit_records)
            return (
                self._normalise_stm_boundaries(boundaries),
                self._normalise_stm_units(units),
            )
        return (
            self._normalise_stm_boundaries(),
            self._normalise_stm_units(),
        )

    def _stm_option_links(self, option_name):
        links = set()
        for link_info in (self.current_table_options or {}).get(option_name, []):
            if not isinstance(link_info, dict):
                continue
            unit_name = str(link_info.get("unit", "")).strip()
            boundary_name = str(link_info.get("boundary", "")).strip()
            if unit_name and boundary_name:
                links.add((unit_name, boundary_name))
        return links

    def _stm_model_boundary_name(self, boundaries=None):
        """Return the feature name of the optional model boundary."""
        boundaries = (
            self.boundaries_table_model.dataframe
            if boundaries is None
            else boundaries
        )
        if boundaries is None:
            return ""
        for _, row in boundaries.iterrows():
            if is_structural_topology_model_boundary(row):
                return str(
                    row.get(STRUCTURAL_TOPOLOGY_FEATURE_COLUMN, "")
                ).strip()
        return ""

    def _reconcile_stm_relationships(self, edited_side=None):
        """Refresh the read-only reciprocal columns from stored link types."""
        del edited_side
        boundaries = self._normalise_stm_boundaries(
            self.boundaries_table_model.dataframe
        )
        units = self._normalise_stm_units(self.table_model.dataframe)
        if STRUCTURAL_TOPOLOGY_REPRESENTATIVE_BOUNDARY_FIELD not in units.columns:
            units[STRUCTURAL_TOPOLOGY_REPRESENTATIVE_BOUNDARY_FIELD] = ""
        boundary_names = {
            str(value).strip()
            for value in boundaries[STRUCTURAL_TOPOLOGY_FEATURE_COLUMN]
            if str(value).strip()
        }
        unit_names = {
            str(value).strip()
            for value in units[STRUCTURAL_TOPOLOGY_FEATURE_COLUMN]
            if str(value).strip()
        }
        representative_links = self._stm_option_links(
            "stm_representative_links"
        )
        manual_links = self._stm_option_links("stm_manual_links")
        representative_links = {
            link
            for link in representative_links
            if link[0] in unit_names and link[1] in boundary_names
        }
        manual_links = {
            link
            for link in manual_links
            if link[0] in unit_names
            and link[1] in boundary_names
            and link not in representative_links
        }
        links = representative_links | manual_links
        for row_label in boundaries.index:
            boundary_name = str(
                boundaries.at[row_label, STRUCTURAL_TOPOLOGY_FEATURE_COLUMN]
            ).strip()
            boundaries.at[
                row_label, STRUCTURAL_TOPOLOGY_BOUNDARY_UNITS_COLUMN
            ] = _stm_names_cell(
                [
                unit_name
                for unit_name, linked_boundary in sorted(links)
                if linked_boundary == boundary_name
                ]
            )
        for row_label in units.index:
            unit_name = str(
                units.at[row_label, STRUCTURAL_TOPOLOGY_FEATURE_COLUMN]
            ).strip()
            units.at[
                row_label, STRUCTURAL_TOPOLOGY_UNIT_BOUNDARIES_COLUMN
            ] = _stm_names_cell(
                [
                boundary_name
                for linked_unit, boundary_name in sorted(links)
                if linked_unit == unit_name
                ]
            )
            representative_name = next(
                (
                    boundary_name
                    for linked_unit, boundary_name in sorted(representative_links)
                    if linked_unit == unit_name
                ),
                "",
            )
            units.at[
                row_label,
                STRUCTURAL_TOPOLOGY_REPRESENTATIVE_BOUNDARY_FIELD,
            ] = representative_name
        return boundaries, units, representative_links, manual_links

    def _persist_stm_composite(self, edited_side=None, reset_models=False):
        table_name = self.current_table_name
        if not table_name:
            return
        boundaries, units, representative_links, manual_links = (
            self._reconcile_stm_relationships(edited_side)
        )
        links = representative_links | manual_links
        options = dict(self.parent.custom_table_options.get(table_name, {}) or {})
        color_codes = dict(options.get("stm_color_codes", {}) or {})
        feature_colors = {
            str(feature_name).strip(): _stm_color_to_dict(color_info)
            for feature_name, color_info in dict(
                color_codes.get("features", {}) or {}
            ).items()
            if str(feature_name).strip()
        }
        color_codes["features"] = feature_colors
        options["stm_color_codes"] = color_codes
        options["stm_tables"] = {
            "boundaries": _stm_records(boundaries),
            "units": _stm_records(units),
        }

        manual_units = []
        unit_key_by_name = {}
        boundary_polarities = {}
        model_boundary_names = set()
        for _, boundary_row in boundaries.iterrows():
            boundary_name = str(
                boundary_row.get(STRUCTURAL_TOPOLOGY_FEATURE_COLUMN, "")
            ).strip()
            if is_structural_topology_model_boundary(boundary_row):
                model_boundary_names.add(boundary_name)
            try:
                boundary_polarities[boundary_name] = float(
                    boundary_row.get(
                        STRUCTURAL_TOPOLOGY_BOUNDARY_POLARITY_COLUMN, ""
                    )
                )
            except (TypeError, ValueError):
                continue
        for _, row in units.iterrows():
            unit_name = str(row.get(STRUCTURAL_TOPOLOGY_FEATURE_COLUMN, "")).strip()
            if not unit_name:
                continue
            unit_id = md5(unit_name.encode("utf-8")).hexdigest()[:10]
            unit_key_by_name[unit_name] = f"unit:manual:{unit_id}"
            linked_polarities = [
                boundary_polarities[boundary_name]
                for linked_unit, boundary_name in links
                if linked_unit == unit_name and boundary_name in boundary_polarities
            ]
            plot_polarity = (
                sum(linked_polarities) / len(linked_polarities)
                if linked_polarities
                else ""
            )
            linked_boundary_names = sorted(
                boundary_name
                for linked_unit, boundary_name in links
                if linked_unit == unit_name
            )
            unit_color = feature_colors.get(unit_name)
            if unit_color is None:
                for boundary_name in linked_boundary_names:
                    if boundary_name in feature_colors:
                        unit_color = feature_colors[boundary_name]
                        break
            if unit_color is None:
                unit_color = _stm_color_to_dict(
                    structural_topology_color(unit_name)
                )
            # A generated unit has the same Feature as its source boundary.
            # Store that shared colour explicitly so its node and every link
            # remain visually identical to the boundary.
            if unit_name in boundary_polarities or any(
                boundary_name == unit_name
                for boundary_name in linked_boundary_names
            ):
                unit_color = feature_colors.get(unit_name, unit_color)
            feature_colors[unit_name] = _stm_color_to_dict(unit_color)
            domains = [
                {"column": column_name, "value": str(row.get(column_name, "")).strip()}
                for column_name in units.columns
                if structural_topology_domain_order(column_name) is not None
                and str(row.get(column_name, "")).strip()
            ]
            manual_units.append(
                {
                    "id": unit_id,
                    "feature": unit_name,
                    "display_name": unit_name,
                    "unit_role": normalise_structural_topology_unit_role(
                        row.get(STRUCTURAL_TOPOLOGY_UNIT_ROLE_COLUMN, "TU")
                    ),
                    "structural_polarity": row.get(
                        STRUCTURAL_TOPOLOGY_UNIT_POLARITY_COLUMN, ""
                    ),
                    "plot_polarity": plot_polarity,
                    "domains": domains,
                    "color_R": unit_color.get("color_R", 255),
                    "color_G": unit_color.get("color_G", 255),
                    "color_B": unit_color.get("color_B", 255),
                }
            )
        options["manual_units"] = manual_units
        options["stm_representative_links"] = [
            {"unit": unit_name, "boundary": boundary_name}
            for unit_name, boundary_name in sorted(representative_links)
        ]
        options["stm_manual_links"] = [
            {"unit": unit_name, "boundary": boundary_name}
            for unit_name, boundary_name in sorted(manual_links)
        ]
        options["manual_connections"] = [
            {
                "unit": unit_key_by_name[unit_name],
                "surface": (
                    "surface:boundary"
                    if boundary_name in model_boundary_names
                    else f"surface:{boundary_name}"
                ),
            }
            for unit_name, boundary_name in sorted(links)
            if unit_name in unit_key_by_name
        ]
        options["representative_connections"] = [
            {
                "unit": unit_key_by_name[unit_name],
                "surface": (
                    "surface:boundary"
                    if boundary_name in model_boundary_names
                    else f"surface:{boundary_name}"
                ),
            }
            for unit_name, boundary_name in sorted(representative_links)
            if unit_name in unit_key_by_name
        ]
        representative_by_unit = {
            unit_name: boundary_name
            for unit_name, boundary_name in representative_links
        }
        options["stm_tables"] = {
            "boundaries": _stm_records_with_colors(boundaries, feature_colors),
            "units": _stm_records_with_colors(
                units, feature_colors, representative_by_unit
            ),
        }
        options.pop("unit_renames", None)
        self.parent.custom_table_options[table_name] = options

        legacy_rows = []
        for _, row in boundaries.iterrows():
            legacy_rows.append(
                {
                    STRUCTURAL_TOPOLOGY_FEATURE_COLUMN: row.get(
                        STRUCTURAL_TOPOLOGY_FEATURE_COLUMN, ""
                    ),
                    STRUCTURAL_TOPOLOGY_UNIT_ROLE_COLUMN: "Discontinuity",
                    STRUCTURAL_TOPOLOGY_POLARITY_COLUMN: row.get(
                        STRUCTURAL_TOPOLOGY_BOUNDARY_POLARITY_COLUMN, ""
                    ),
                    "Domain_1": "",
                }
            )
        self.parent.custom_tables[table_name] = pd_DataFrame(
            legacy_rows, columns=STRUCTURAL_TOPOLOGY_BASE_COLUMNS
        )
        if reset_models:
            self.boundaries_table_model.set_dataframe(boundaries)
            self.table_model.set_dataframe(units)

    def current_dataframe_column_name(self, column_index: int):
        if (
            column_index < 0
            or column_index >= self.table_model.dataframe.shape[1]
        ):
            return None
        return str(self.table_model.dataframe.columns[column_index])

    @property
    def current_domain_columns(self):
        domain_columns = []
        for column_name in self.table_model.dataframe.columns.tolist():
            if structural_topology_domain_order(column_name) is not None:
                domain_columns.append(column_name)
        return sorted(
            domain_columns,
            key=lambda column_name: structural_topology_domain_order(column_name),
        )

    def is_table_model_column_editable(
        self, table_model, column_index: int, row_index: int = None
    ) -> bool:
        if column_index < 0 or column_index >= table_model.dataframe.shape[1]:
            return False
        column_name = str(table_model.dataframe.columns[column_index])
        if column_name is None:
            return False
        if self.current_table_type != STRUCTURAL_TOPOLOGY_TABLE_TYPE:
            return True
        if table_model is self.boundaries_table_model:
            if (
                row_index is not None
                and 0 <= row_index < len(table_model.dataframe.index)
                and is_structural_topology_model_boundary(
                    table_model.dataframe.iloc[row_index]
                )
            ):
                return False
            return column_name not in {
                STRUCTURAL_TOPOLOGY_FEATURE_COLUMN,
                STRUCTURAL_TOPOLOGY_BOUNDARY_UNITS_COLUMN,
            }
        return column_name not in {
            STRUCTURAL_TOPOLOGY_UNIT_POLARITY_COLUMN,
            STRUCTURAL_TOPOLOGY_UNIT_BOUNDARIES_COLUMN,
            STRUCTURAL_TOPOLOGY_REPRESENTATIVE_BOUNDARY_FIELD,
        }

    def is_table_column_editable(self, column_index: int) -> bool:
        """Backward-compatible wrapper for code using the primary model."""
        return self.is_table_model_column_editable(
            self.table_model, column_index
        )

    def _current_domain_column_name(self):
        current_index = self.table_view.currentIndex()
        if current_index.isValid():
            column_name = self.current_dataframe_column_name(current_index.column())
            if column_name in self.current_domain_columns:
                return column_name
        return self.current_domain_columns[-1] if self.current_domain_columns else None

    def _current_stm_special_column(self, index):
        if not index.isValid():
            return None
        column_name = self.current_dataframe_column_name(index.column())
        if column_name == STRUCTURAL_TOPOLOGY_UNIT_ROLE_COLUMN:
            return column_name
        return None

    def _normalise_stm_dataframe_columns(self, dataframe):
        """Return an STm dataframe with ordered core/domain columns."""
        if dataframe is None:
            return pd_DataFrame(columns=STRUCTURAL_TOPOLOGY_BASE_COLUMNS)

        out_df = dataframe.copy()
        if "Domain" in out_df.columns and "Domain_1" not in out_df.columns:
            out_df = out_df.rename(columns={"Domain": "Domain_1"})
        if STRUCTURAL_TOPOLOGY_FEATURE_COLUMN not in out_df.columns:
            out_df[STRUCTURAL_TOPOLOGY_FEATURE_COLUMN] = ""
        if STRUCTURAL_TOPOLOGY_UNIT_ROLE_COLUMN not in out_df.columns:
            out_df[STRUCTURAL_TOPOLOGY_UNIT_ROLE_COLUMN] = (
                "Discontinuity"
            )
        if STRUCTURAL_TOPOLOGY_POLARITY_COLUMN not in out_df.columns:
            out_df[STRUCTURAL_TOPOLOGY_POLARITY_COLUMN] = ""
        for row_label in out_df.index.tolist():
            unit_role = normalise_structural_topology_unit_role(
                out_df.at[row_label, STRUCTURAL_TOPOLOGY_UNIT_ROLE_COLUMN]
            )
            out_df.at[row_label, STRUCTURAL_TOPOLOGY_UNIT_ROLE_COLUMN] = unit_role
        if not any(
            structural_topology_domain_order(column_name) is not None
            for column_name in out_df.columns.tolist()
        ):
            out_df["Domain_1"] = ""

        ordered_columns = [
            column_name
            for column_name in [
                STRUCTURAL_TOPOLOGY_FEATURE_COLUMN,
                STRUCTURAL_TOPOLOGY_UNIT_ROLE_COLUMN,
                STRUCTURAL_TOPOLOGY_POLARITY_COLUMN,
            ]
            if column_name in out_df.columns
        ]
        ordered_columns.extend(
            sorted(
                [
                    column_name
                    for column_name in out_df.columns.tolist()
                    if structural_topology_domain_order(column_name) is not None
                    and column_name not in ordered_columns
                ],
                key=lambda column_name: structural_topology_domain_order(column_name),
            )
        )
        ordered_columns.extend(
            [
                column_name
                for column_name in out_df.columns.tolist()
                if column_name not in ordered_columns
            ]
        )
        return out_df[ordered_columns]

    def _apply_stm_dataframe(self, dataframe):
        """Assign a normalised Units dataframe and refresh the legacy view."""
        table_name = self.current_table_name
        if not table_name:
            return
        normalised_df = self._normalise_stm_units(dataframe)
        self.table_model.set_dataframe(normalised_df)
        self._persist_stm_composite(edited_side="units", reset_models=True)

    def _reset_table_delegates(self):
        """Reset per-column delegates to the default delegate."""
        for column_idx in range(self.table_model.dataframe.shape[1]):
            self.table_view.setItemDelegateForColumn(
                column_idx, QStyledItemDelegate(self.table_view)
            )

    def _install_stm_delegates(self):
        """Install inline combo delegates for STm enumerated columns."""
        self._reset_table_delegates()
        dataframe_columns = self.table_model.dataframe.columns.tolist()
        if STRUCTURAL_TOPOLOGY_UNIT_ROLE_COLUMN in dataframe_columns:
            self.table_view.setItemDelegateForColumn(
                dataframe_columns.index(STRUCTURAL_TOPOLOGY_UNIT_ROLE_COLUMN),
                ComboBoxItemDelegate(
                    values=STRUCTURAL_TOPOLOGY_UNIT_VALUES,
                    parent=self.table_view,
                ),
            )
    def _available_stm_units(self):
        if hasattr(self.parent, "get_structural_topology_legend_units"):
            units = list(self.parent.get_structural_topology_legend_units() or [])
        else:
            units = []

        boundary_coll = getattr(self.parent, "boundary_coll", None)
        if boundary_coll is not None:
            for boundary_name in getattr(boundary_coll, "get_names", []) or []:
                boundary_text = str(boundary_name or "").strip()
                if not boundary_text or boundary_text == STRUCTURAL_TOPOLOGY_MODEL_BOUNDARY:
                    continue
                units.append(
                    {
                        STRUCTURAL_TOPOLOGY_FEATURE_COLUMN: boundary_text,
                        STRUCTURAL_TOPOLOGY_UNIT_ROLE_COLUMN: "Discontinuity",
                        STRUCTURAL_TOPOLOGY_POLARITY_COLUMN: "",
                        "Domain_1": "",
                        "feature": boundary_text,
                        "role": "model_boundary",
                        "color_R": 255,
                        "color_G": 255,
                        "color_B": 255,
                    }
                )

        legend_df = getattr(getattr(self.parent, "geol_coll", None), "legend_df", None)
        if not units and legend_df is not None and not legend_df.empty:
            units = [
                {
                    STRUCTURAL_TOPOLOGY_FEATURE_COLUMN: str(
                        row.get("feature", "")
                    ).strip(),
                    STRUCTURAL_TOPOLOGY_UNIT_ROLE_COLUMN: "Discontinuity",
                    STRUCTURAL_TOPOLOGY_POLARITY_COLUMN: row.get("time", 0.0),
                    "Domain_1": "",
                    "feature": str(row.get("feature", "")).strip(),
                    "role": normalise_structural_topology_boundary_role(
                        row.get("role", "")
                    ),
                    "color_R": row.get("color_R", 255),
                    "color_G": row.get("color_G", 255),
                    "color_B": row.get("color_B", 255),
                }
                for _, row in legend_df.iterrows()
                if str(row.get("feature", "")).strip()
                and str(row.get("feature", "")).strip() != STRUCTURAL_TOPOLOGY_MODEL_BOUNDARY
            ]
        current_options = dict(self.current_table_options or {})
        stored_boundaries = (
            current_options.get("stm_tables", {}).get("boundaries", [])
            if isinstance(current_options.get("stm_tables", {}), dict)
            else []
        )
        stored_roles = {
            str(boundary_info.get(STRUCTURAL_TOPOLOGY_FEATURE_COLUMN, "")).strip(): (
                normalise_structural_topology_boundary_role(
                    boundary_info.get(STRUCTURAL_TOPOLOGY_BOUNDARY_ROLE_COLUMN, "")
                )
            )
            for boundary_info in stored_boundaries
            if isinstance(boundary_info, dict)
            and str(
                boundary_info.get(STRUCTURAL_TOPOLOGY_FEATURE_COLUMN, "")
            ).strip()
        }
        stored_color_codes = current_options.get("stm_color_codes", {})
        feature_color_map = {}
        if isinstance(stored_color_codes, dict):
            feature_color_map = {
                str(feature_name).strip(): _stm_color_to_dict(color_info)
                for feature_name, color_info in stored_color_codes.get("features", {}).items()
                if str(feature_name).strip()
            }

        available_units = []
        available_keys = set()
        for unit_info in units:
            feature_name = str(unit_info.get(STRUCTURAL_TOPOLOGY_FEATURE_COLUMN, "")).strip()
            if not feature_name:
                continue
            role_name = str(unit_info.get("role", "")).strip()
            unit_key = (feature_name, role_name)
            if unit_key in available_keys:
                continue
            unit_payload = dict(unit_info)
            unit_payload.update(feature_color_map.get(feature_name, {}))
            available_units.append(unit_payload)
            available_keys.add(unit_key)
        if feature_color_map:
            for feature_name, color_info in feature_color_map.items():
                if any(key[0] == feature_name for key in available_keys):
                    continue
                available_units.append({
                    STRUCTURAL_TOPOLOGY_FEATURE_COLUMN: feature_name,
                    STRUCTURAL_TOPOLOGY_UNIT_ROLE_COLUMN: "Discontinuity",
                    STRUCTURAL_TOPOLOGY_POLARITY_COLUMN: 0.0,
                    "Domain_1": "",
                    "feature": feature_name,
                    "role": stored_roles.get(feature_name, ""),
                    "color_R": color_info.get("color_R", 255),
                    "color_G": color_info.get("color_G", 255),
                    "color_B": color_info.get("color_B", 255),
                })

        return sorted(
            available_units,
            key=lambda unit_info: (
                str(
                    unit_info.get(STRUCTURAL_TOPOLOGY_FEATURE_COLUMN, "")
                ).casefold(),
                str(unit_info.get("role", "")).casefold(),
            ),
        )

    def _available_model_boundary_sources(self):
        """Return selectable objects from the project Boundary collection."""
        boundary_coll = getattr(self.parent, "boundary_coll", None)
        if boundary_coll is None:
            return []

        sources = []
        dataframe = getattr(boundary_coll, "df", None)
        if dataframe is not None and not dataframe.empty:
            for _, row in dataframe.iterrows():
                source_name = str(row.get("name", "")).strip()
                if not source_name:
                    continue
                source_info = {
                    "name": source_name,
                    "uid": str(row.get("uid", "")).strip(),
                    "color_R": 255,
                    "color_G": 255,
                    "color_B": 255,
                }
                source_uid = source_info["uid"]
                if source_uid and hasattr(boundary_coll, "get_uid_legend"):
                    try:
                        source_info.update(
                            _stm_color_to_dict(
                                boundary_coll.get_uid_legend(uid=source_uid)
                            )
                        )
                    except Exception:
                        pass
                sources.append(source_info)
        else:
            sources = [
                {"name": str(boundary_name).strip()}
                for boundary_name in getattr(boundary_coll, "get_names", []) or []
                if str(boundary_name).strip()
            ]
        return sources

    def refresh_table_list(self, select_name: str = None):
        current_name = select_name or self.current_table_name
        self.tables_list.blockSignals(True)
        self.tables_list.clear()
        for table_name in self.parent.custom_tables.keys():
            self.tables_list.addItem(QListWidgetItem(table_name))
        self.tables_list.blockSignals(False)

        if self.tables_list.count() == 0:
            self.table_model.set_dataframe(pd_DataFrame())
            self.current_table_label.setText("No table selected")
            self.update_editing_ui()
            return

        if not current_name or current_name not in self.parent.custom_tables:
            current_name = next(iter(self.parent.custom_tables.keys()))

        matching_items = self.tables_list.findItems(current_name, Qt.MatchExactly)
        if matching_items:
            self.tables_list.setCurrentItem(matching_items[0])
            self.on_table_selection_changed(matching_items[0], None)

    def on_table_selection_changed(self, current, previous):
        del previous
        if current is None:
            self.table_model.set_dataframe(pd_DataFrame())
            self.current_table_label.setText("No table selected")
            self.update_editing_ui()
            return

        table_name = current.text()
        dataframe = self.parent.custom_tables.get(table_name, pd_DataFrame())
        current_type = self.parent.custom_table_types.get(table_name, "manual")
        current_options = self.parent.custom_table_options.get(table_name, {})
        if current_type == STRUCTURAL_TOPOLOGY_TABLE_TYPE:
            boundaries, units = self._load_stm_composite(table_name)
            self.boundaries_table_model.set_dataframe(boundaries)
            self.table_model.set_dataframe(units)
            self._persist_stm_composite(reset_models=True)
        else:
            self.boundaries_table_model.set_dataframe(pd_DataFrame())
            self.table_model.set_dataframe(dataframe)
        if current_type == PropertiesCMaps.custom_colormap_table_type:
            mode_label = (
                "exact intervals"
                if current_options.get("mode") == "discrete"
                else "continuous"
            )
            self.current_table_label.setText(
                f"Table: {table_name} [Colormap, {mode_label}]"
            )
        elif current_type == STRUCTURAL_TOPOLOGY_TABLE_TYPE:
            self.current_table_label.setText(
                f"Table: {table_name} [Structural Topology model]"
            )
        else:
            self.current_table_label.setText(f"Table: {table_name}")
        self.update_editing_ui()

    def on_editing_toggled(self, checked):
        self.editing_enabled = bool(checked)
        self.update_editing_ui()

    def on_table_model_edited(
        self, row_index=None, column_index=None, table_model=None
    ):
        """React to cell edits coming from the table model."""
        if self.current_table_type == STRUCTURAL_TOPOLOGY_TABLE_TYPE:
            edited_side = (
                "boundaries"
                if table_model is self.boundaries_table_model
                else "units"
            )
            self._persist_stm_composite(
                edited_side=edited_side,
                reset_models=True,
            )
        if (
            self.current_table_type == STRUCTURAL_TOPOLOGY_TABLE_TYPE
            and hasattr(self.parent, "sync_structural_topology_table_to_legend")
        ):
            self.parent.sync_structural_topology_table_to_legend(self.current_table_name)
        self._notify_custom_table_metadata_changed()

    def _enforce_current_stm_constraints(
        self,
        edited_row_index=None,
        edited_column_name=None,
    ):
        """Keep the edited STm dataframe internally coherent."""
        dataframe = self.table_model.dataframe
        if (
            dataframe is None
            or dataframe.empty
            or STRUCTURAL_TOPOLOGY_UNIT_ROLE_COLUMN not in dataframe.columns
        ):
            return

        changed = False
        del edited_row_index, edited_column_name
        for row_label in dataframe.index.tolist():
            unit_role = normalise_structural_topology_unit_role(
                dataframe.at[row_label, STRUCTURAL_TOPOLOGY_UNIT_ROLE_COLUMN]
            )
            if dataframe.at[row_label, STRUCTURAL_TOPOLOGY_UNIT_ROLE_COLUMN] != unit_role:
                dataframe.at[row_label, STRUCTURAL_TOPOLOGY_UNIT_ROLE_COLUMN] = unit_role
                changed = True

        if changed and self.table_model.rowCount() > 0 and self.table_model.columnCount() > 0:
            top_left = self.table_model.index(0, 0)
            bottom_right = self.table_model.index(
                self.table_model.rowCount() - 1,
                self.table_model.columnCount() - 1,
            )
            self.table_model.dataChanged.emit(
                top_left, bottom_right, [Qt.DisplayRole, Qt.EditRole]
            )

    def on_table_view_clicked(self, index):
        """Handle clicks on the virtual color preview cells for colormap tables."""
        if not index.isValid() or not self.editing_enabled:
            return

        if (
            self.current_table_type == PropertiesCMaps.custom_colormap_table_type
            and self.table_model.is_preview_column(index.column())
        ):
            current_color = self.table_model._row_preview_color(index.row())
            if current_color is None:
                current_color = QColor(255, 255, 255)

            color_out = QColorDialog.getColor(current_color, self)
            if not color_out.isValid():
                return

            self.table_model.update_row_color(index.row(), color_out)
            return

        if self.current_table_type != STRUCTURAL_TOPOLOGY_TABLE_TYPE:
            return

        if self._current_stm_special_column(index):
            self.table_view.edit(index)

    def update_editing_ui(self):
        is_colormap_table = (
            self.current_table_type == PropertiesCMaps.custom_colormap_table_type
        )
        is_stm_table = self.current_table_type == STRUCTURAL_TOPOLOGY_TABLE_TYPE
        self._reset_table_delegates()
        if is_stm_table:
            self._install_stm_delegates()
        self.table_model.set_show_colormap_preview(is_colormap_table)
        self.table_model.set_editable(self.editing_enabled)
        self.boundaries_table_model.set_editable(
            self.editing_enabled and is_stm_table
        )
        edit_triggers = (
            QAbstractItemView.DoubleClicked
            | QAbstractItemView.EditKeyPressed
            | QAbstractItemView.AnyKeyPressed
        )
        self.table_view.setEditTriggers(
            edit_triggers if self.editing_enabled else QAbstractItemView.NoEditTriggers
        )
        self.boundaries_table_view.setEditTriggers(
            edit_triggers
            if self.editing_enabled and is_stm_table
            else QAbstractItemView.NoEditTriggers
        )
        self.boundaries_label.setVisible(is_stm_table)
        self.boundaries_table_view.setVisible(is_stm_table)
        self.units_label.setVisible(is_stm_table)

        has_table = bool(self.current_table_name)
        has_columns = self.table_model.columnCount() > 0
        has_rows = self.table_model.rowCount() > 0
        has_boundaries = self.boundaries_table_model.rowCount() > 0
        has_model_boundary = any(
            is_structural_topology_model_boundary(row)
            for _, row in self.boundaries_table_model.dataframe.iterrows()
        )
        allow_structure_edit = self.editing_enabled and has_table
        allow_row_edit = allow_structure_edit and has_columns
        allow_column_edit = allow_structure_edit and has_columns and not is_colormap_table
        selected_domain_column = self._current_domain_column_name()

        self.editing_toggle_button.setText(
            "Disable editing" if self.editing_enabled else "Enable editing"
        )
        if is_stm_table:
            self.add_row_action.setText("Import boundaries")
            self.delete_row_action.setText("Remove selected")
            self.add_field_action.setText("Add domain")
            self.rename_field_action.setText("Rename domain")
            self.delete_field_action.setText("Delete domain")
        else:
            self.add_row_action.setText("Add row")
            self.delete_row_action.setText("Delete row")
            self.add_field_action.setText("Add field")
            self.rename_field_action.setText("Rename field")
            self.delete_field_action.setText("Delete field")
        self.new_table_button.setEnabled(True)
        self.delete_table_button.setEnabled(has_table)
        self.export_table_button.setEnabled(has_table)
        self.add_menu.menuAction().setEnabled(has_table)
        self.edit_menu.menuAction().setEnabled(has_table)
        self.build_stm_button.setVisible(is_stm_table)
        self.build_stm_button.setEnabled(
            is_stm_table and (has_boundaries or has_rows)
        )
        self.generate_units_action.setVisible(is_stm_table)
        self.add_model_boundary_action.setVisible(is_stm_table)
        self.add_extra_boundary_action.setVisible(is_stm_table)
        self.add_extra_unit_action.setVisible(is_stm_table)
        self.add_boundary_separator.setVisible(is_stm_table)
        self.add_unit_separator.setVisible(is_stm_table)
        if is_stm_table:
            self.add_row_action.setEnabled(allow_structure_edit)
            self.delete_row_action.setEnabled(
                allow_structure_edit and (has_boundaries or has_rows)
            )
            self.generate_units_action.setEnabled(
                allow_structure_edit and has_boundaries
            )
            self.add_model_boundary_action.setEnabled(
                allow_structure_edit and not has_model_boundary
            )
            self.add_extra_boundary_action.setEnabled(allow_structure_edit)
            self.add_extra_unit_action.setEnabled(allow_structure_edit)
            self.add_field_action.setEnabled(allow_structure_edit)
            self.rename_field_action.setEnabled(
                allow_structure_edit and bool(selected_domain_column)
            )
            self.delete_field_action.setEnabled(
                allow_structure_edit and bool(selected_domain_column)
            )
        else:
            self.add_row_action.setEnabled(allow_row_edit)
            self.delete_row_action.setEnabled(allow_row_edit and has_rows)
            self.add_field_action.setEnabled(allow_structure_edit)
            self.rename_field_action.setEnabled(allow_column_edit)
            self.delete_field_action.setEnabled(allow_column_edit)
        self.table_view.horizontalHeader().setStretchLastSection(not is_colormap_table)
        if is_colormap_table:
            self.table_view.horizontalHeader().setSectionResizeMode(
                self.table_model.preview_column_index, QHeaderView.Fixed
            )
            self.table_view.setColumnWidth(self.table_model.preview_column_index, 80)

    def _populate_new_table_menu(self):
        """Populate the new-table menu with manual and advanced creation paths."""
        self.new_table_menu.clear()

        manual_action = QAction("Manual table", self)
        manual_action.triggered.connect(self.create_table)
        self.new_table_menu.addAction(manual_action)

        advanced_menu = self.new_table_menu.addMenu("Advanced table")
        colormap_action = QAction("Colormap", self)
        colormap_action.triggered.connect(self.create_colormap_table)
        advanced_menu.addAction(colormap_action)
        stm_action = QAction("Structural Topology model", self)
        stm_action.triggered.connect(self.create_structural_topology_table)
        advanced_menu.addAction(stm_action)

    def _notify_custom_table_metadata_changed(self):
        """Refresh dependent UI when custom table metadata or contents change."""
        if hasattr(self.parent, "refresh_table_views"):
            self.parent.refresh_table_views()
        if hasattr(self.parent, "refresh_custom_colormaps"):
            self.parent.refresh_custom_colormaps()

    def _build_default_colormap_dataframe(self):
        """Return a default colormap table with two editable endpoints."""
        return pd_DataFrame(
            [
                {"value": 0.0, "color_R": 0, "color_G": 0, "color_B": 255},
                {"value": 1.0, "color_R": 255, "color_G": 255, "color_B": 0},
            ],
            columns=PropertiesCMaps.custom_colormap_columns,
        )

    def _build_default_structural_topology_dataframe(self):
        """Return the default empty STm dataframe."""
        return pd_DataFrame(columns=STRUCTURAL_TOPOLOGY_BASE_COLUMNS)

    def _normalise_export_path(self, file_path: str, selected_filter: str) -> tuple[str, str]:
        """Return a normalized output path and delimiter for textual table export."""
        delimiter_map = {
            "STm JSON files (*.json)": (".json", ","),
            "CSV files (*.csv)": (".csv", ","),
            "Tab-separated text (*.tsv)": (".tsv", "\t"),
            "Text files (*.txt)": (".txt", "\t"),
            "DAT files (*.dat)": (".dat", ";"),
            "All files (*.*)": ("", ","),
        }
        default_extension, delimiter = delimiter_map.get(
            selected_filter, (".csv", ",")
        )

        current_extension = os_path.splitext(file_path)[1].lower()
        if current_extension:
            extension_delimiter_map = {
                ".csv": ",",
                ".tsv": "\t",
                ".txt": "\t",
                ".dat": ";",
            }
            delimiter = extension_delimiter_map.get(current_extension, delimiter)
            return file_path, delimiter

        return f"{file_path}{default_extension}", delimiter

    def create_table(self):
        dialog = NewTableDialog(parent=self)
        if dialog.exec() != QDialog.Accepted:
            return

        table_name = dialog.table_name
        if table_name in self.parent.custom_tables:
            QMessageBox.warning(
                self,
                "Duplicate table",
                f'The table "{table_name}" already exists.',
            )
            return

        self.parent.custom_tables[table_name] = pd_DataFrame(columns=dialog.field_names)
        self.parent.custom_table_types[table_name] = "manual"
        self.parent.custom_table_options[table_name] = {}
        self.refresh_table_list(select_name=table_name)
        self._notify_custom_table_metadata_changed()

    def create_colormap_table(self):
        """Create a new advanced colormap table."""
        dialog = NewColormapTableDialog(parent=self)
        if dialog.exec() != QDialog.Accepted:
            return

        table_name = dialog.table_name
        if table_name in self.parent.custom_tables:
            QMessageBox.warning(
                self,
                "Duplicate table",
                f'The table "{table_name}" already exists.',
            )
            return

        self.parent.custom_tables[table_name] = self._build_default_colormap_dataframe()
        self.parent.custom_table_types[table_name] = (
            PropertiesCMaps.custom_colormap_table_type
        )
        self.parent.custom_table_options[table_name] = {"mode": dialog.mode}
        self.refresh_table_list(select_name=table_name)
        self._notify_custom_table_metadata_changed()

    def create_structural_topology_table(self):
        """Create a new Structural Topology model table."""
        dialog = NewStructuralTopologyTableDialog(parent=self)
        if dialog.exec() != QDialog.Accepted:
            return

        table_name = dialog.table_name
        if table_name in self.parent.custom_tables:
            QMessageBox.warning(
                self,
                "Duplicate table",
                f'The table "{table_name}" already exists.',
            )
            return

        self.parent.custom_tables[table_name] = (
            self._build_default_structural_topology_dataframe()
        )
        self.parent.custom_table_types[table_name] = STRUCTURAL_TOPOLOGY_TABLE_TYPE
        self.parent.custom_table_options[table_name] = {}
        self.refresh_table_list(select_name=table_name)
        self._notify_custom_table_metadata_changed()

    def delete_current_table(self):
        table_name = self.current_table_name
        if not table_name:
            return

        confirm = QMessageBox.question(
            self,
            "Delete table",
            f'Delete table "{table_name}"?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        self.parent.custom_tables.pop(table_name, None)
        self.parent.custom_table_types.pop(table_name, None)
        self.parent.custom_table_options.pop(table_name, None)
        self.refresh_table_list()
        self._notify_custom_table_metadata_changed()

    def export_current_table(self):
        """Export the selected custom table to a text-delimited file."""
        table_name = self.current_table_name
        if not table_name:
            QMessageBox.information(
                self,
                "No table",
                "Select a table to export.",
            )
            return

        export_filter = (
            self.EXPORT_FILTER
            if self.current_table_type == STRUCTURAL_TOPOLOGY_TABLE_TYPE
            else self.EXPORT_FILTER.split(";;", 1)[1]
        )
        output_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            f"Export table {table_name}",
            table_name,
            export_filter,
            (
                "STm JSON files (*.json)"
                if self.current_table_type == STRUCTURAL_TOPOLOGY_TABLE_TYPE
                else "CSV files (*.csv)"
            ),
        )
        if not output_path:
            return

        output_path, delimiter = self._normalise_export_path(
            file_path=output_path,
            selected_filter=selected_filter,
        )

        try:
            dataframe = self.parent.custom_tables[table_name]
            if self.current_table_type == STRUCTURAL_TOPOLOGY_TABLE_TYPE:
                export_options = dict(self.parent.custom_table_options.get(table_name, {}))
                if output_path.lower().endswith(".json"):
                    boundaries, units, representative_links, _ = (
                        self._reconcile_stm_relationships()
                    )
                    feature_colors = self._stm_feature_colors()
                    representative_by_unit = {
                        unit_name: boundary_name
                        for unit_name, boundary_name in representative_links
                    }
                    with open(output_path, "w", encoding="utf-8") as output_stream:
                        json.dump(
                            build_stm_json(
                                name=table_name,
                                boundaries=_stm_records(boundaries),
                                units=_stm_records(units),
                                colors=feature_colors,
                                representative_boundaries=representative_by_unit,
                                boundary_columns=boundaries.columns,
                                unit_columns=units.columns,
                            ),
                            output_stream,
                            ensure_ascii=False,
                            indent=2,
                        )
                    self.parent.print_terminal(
                        f'Exported table "{table_name}" to {output_path}'
                    )
                    return
                feature_colors = {}
                stored_color_codes = export_options.get("stm_color_codes", {})
                if isinstance(stored_color_codes, dict):
                    feature_colors.update(
                        {
                            str(feature_name).strip(): _stm_color_to_dict(color_info)
                            for feature_name, color_info in stored_color_codes.get("features", {}).items()
                            if str(feature_name).strip()
                        }
                    )
                if STRUCTURAL_TOPOLOGY_FEATURE_COLUMN in dataframe.columns:
                    for feature_name in dataframe[STRUCTURAL_TOPOLOGY_FEATURE_COLUMN].tolist():
                        feature_text = str(feature_name or "").strip()
                        if not feature_text or feature_text in feature_colors:
                            continue
                        feature_colors[feature_text] = _stm_color_to_dict(
                            structural_topology_color(feature_text)
                        )
                for unit_info in self._available_stm_units():
                    feature_text = str(
                        unit_info.get(STRUCTURAL_TOPOLOGY_FEATURE_COLUMN, "")
                    ).strip()
                    if feature_text:
                        feature_colors[feature_text] = _stm_color_to_dict(unit_info)
                export_options["stm_color_codes"] = {"features": feature_colors}

                with open(output_path, "w", encoding="utf-8", newline="") as output_stream:
                    dataframe.to_csv(
                        output_stream,
                        sep=delimiter,
                        index=False,
                    )
                    boundaries, units, representative_links, _ = (
                        self._reconcile_stm_relationships()
                    )
                    _stm_write_export_footer(
                        output_stream,
                        build_stm_json(
                            name=table_name,
                            boundaries=_stm_records(boundaries),
                            units=_stm_records(units),
                            colors=feature_colors,
                            representative_boundaries={
                                unit_name: boundary_name
                                for unit_name, boundary_name
                                in representative_links
                            },
                            boundary_columns=boundaries.columns,
                            unit_columns=units.columns,
                        ),
                    )
            else:
                dataframe.to_csv(
                    output_path,
                    sep=delimiter,
                    index=False,
                    encoding="utf-8",
                )
            self.parent.print_terminal(
                f'Exported table "{table_name}" to {output_path}'
            )
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Export error",
                f'Could not export table "{table_name}".\n\n{exc}',
            )

    def build_structural_topology_model(self):
        """Open the STm builder dialog for the current table."""
        table_name = self.current_table_name
        if not table_name or self.current_table_type != STRUCTURAL_TOPOLOGY_TABLE_TYPE:
            return

        dialog = STmBuildDialog(
            parent=self,
            table_name=table_name,
            dataframe_provider=lambda tn=table_name: self.parent.custom_tables.get(
                tn, pd_DataFrame()
            ).copy(),
            metadata_provider=lambda: list(self._available_stm_units()),
            options_provider=lambda tn=table_name: dict(
                self.parent.custom_table_options.get(tn, {})
            ),
            options_updater=lambda updates, tn=table_name: self._update_stm_build_options(
                table_name=tn,
                updates=updates,
            ),
            polarity_calculator=self.calculate_unit_polarities,
        )
        dialog.exec()
        boundaries, units = self._load_stm_composite(table_name)
        self.boundaries_table_model.set_dataframe(boundaries)
        self.table_model.set_dataframe(units)
        self.update_editing_ui()

    def _update_stm_build_options(self, table_name=None, updates=None):
        """Persist STm builder options without discarding existing table options."""
        if not table_name:
            return
        merged_options = dict(self.parent.custom_table_options.get(table_name, {}))
        merged_options.update(dict(updates or {}))
        self.parent.custom_table_options[table_name] = merged_options
        if "manual_connections" in (updates or {}):
            unit_names_by_key = {}
            for unit_info in merged_options.get("manual_units", []):
                if not isinstance(unit_info, dict):
                    continue
                unit_id = str(unit_info.get("id", "")).strip()
                unit_name = str(unit_info.get("feature", "")).strip()
                if unit_id and unit_name:
                    unit_names_by_key[f"unit:manual:{unit_id}"] = unit_name
            graph_links = set()
            model_boundary_name = self._stm_model_boundary_name()
            for connection in merged_options.get("manual_connections", []):
                if not isinstance(connection, dict):
                    continue
                unit_name = unit_names_by_key.get(
                    str(connection.get("unit", "")).strip()
                )
                surface_key = str(connection.get("surface", "")).strip()
                if (
                    unit_name
                    and surface_key.startswith("surface:")
                ):
                    boundary_name = (
                        model_boundary_name
                        if surface_key == "surface:boundary"
                        else surface_key[len("surface:") :]
                    )
                    if boundary_name:
                        graph_links.add((unit_name, boundary_name))
            representative_links = self._stm_option_links(
                "stm_representative_links"
            )
            # The graph may only change black/manual links. Representative
            # links remain present even if a malformed update omits them.
            manual_links = graph_links - representative_links
            merged_options["stm_manual_links"] = [
                {"unit": unit_name, "boundary": boundary_name}
                for unit_name, boundary_name in sorted(manual_links)
            ]
            self.parent.custom_table_options[table_name] = merged_options
            self._persist_stm_composite(reset_models=True)

    def add_row(self):
        table_name = self.current_table_name
        if not table_name:
            QMessageBox.information(
                self,
                "No table",
                "Create or select a table first.",
            )
            return
        if self.current_table_type == STRUCTURAL_TOPOLOGY_TABLE_TYPE:
            self.import_structural_topology_units()
            return
        if self.table_model.columnCount() == 0:
            QMessageBox.information(
                self,
                "No fields",
                "Add at least one field before inserting rows.",
            )
            return
        if self.current_table_type == PropertiesCMaps.custom_colormap_table_type:
            dataframe = self.table_model.dataframe
            numeric_values = pd_to_numeric(dataframe["value"], errors="coerce").dropna()
            next_value = 0.0 if numeric_values.empty else float(numeric_values.max()) + 1.0
            self.table_model.add_row_data(
                {
                    "value": next_value,
                    "color_R": 255,
                    "color_G": 255,
                    "color_B": 255,
                }
            )
        else:
            self.table_model.add_empty_row()
        self._notify_custom_table_metadata_changed()

    def delete_selected_rows(self):
        table_name = self.current_table_name
        if not table_name:
            return

        target_view = self.table_view
        target_model = self.table_model
        edited_side = "units"
        if self.current_table_type == STRUCTURAL_TOPOLOGY_TABLE_TYPE:
            boundary_rows = self.boundaries_table_view.selectionModel().selectedRows()
            unit_rows = self.table_view.selectionModel().selectedRows()
            if boundary_rows and not unit_rows:
                target_view = self.boundaries_table_view
                target_model = self.boundaries_table_model
                edited_side = "boundaries"
        selection_model = target_view.selectionModel()
        if selection_model is None:
            return

        selected_rows = sorted(
            {index.row() for index in selection_model.selectedRows()},
            reverse=True,
        )
        if not selected_rows and target_view.currentIndex().isValid():
            selected_rows = [target_view.currentIndex().row()]
        if not selected_rows:
            return
        removed_model_boundary = (
            target_model is self.boundaries_table_model
            and any(
                is_structural_topology_model_boundary(
                    target_model.dataframe.iloc[row_index]
                )
                for row_index in selected_rows
            )
        )
        target_model.remove_rows(selected_rows)
        if self.current_table_type == STRUCTURAL_TOPOLOGY_TABLE_TYPE:
            if removed_model_boundary:
                options = dict(self.current_table_options or {})
                options.pop("stm_model_boundary_source", None)
                self.parent.custom_table_options[self.current_table_name] = options
            self._persist_stm_composite(
                edited_side=edited_side, reset_models=True
            )
        self.update_editing_ui()
        if (
            self.current_table_type == STRUCTURAL_TOPOLOGY_TABLE_TYPE
            and hasattr(self.parent, "sync_structural_topology_table_to_legend")
        ):
            self.parent.sync_structural_topology_table_to_legend(self.current_table_name)
        self._notify_custom_table_metadata_changed()

    def import_structural_topology_units(self):
        """Append selected geological boundaries to the Boundaries table."""
        table_name = self.current_table_name
        if not table_name:
            return

        existing_boundaries = {
            str(row.get(STRUCTURAL_TOPOLOGY_FEATURE_COLUMN, "")).strip():
            str(row.get(STRUCTURAL_TOPOLOGY_BOUNDARY_ROLE_COLUMN, "")).strip()
            for _, row in self.boundaries_table_model.dataframe.iterrows()
            if str(
                row.get(STRUCTURAL_TOPOLOGY_FEATURE_COLUMN, "")
            ).strip()
        }

        dialog = ImportStructuralTopologyUnitsDialog(
            parent=self,
            units_provider=self._available_stm_units,
            existing_boundaries=existing_boundaries,
        )
        if dialog.exec() != QDialog.Accepted:
            return

        for unit_info in dialog.selected_units:
            selected_name = str(
                unit_info.get(STRUCTURAL_TOPOLOGY_FEATURE_COLUMN, "")
            ).strip()
            if not selected_name or selected_name in existing_boundaries:
                continue
            self._set_stm_feature_color(selected_name, unit_info)
            self.boundaries_table_model.add_row_data(
                {
                    STRUCTURAL_TOPOLOGY_FEATURE_COLUMN: selected_name,
                    STRUCTURAL_TOPOLOGY_BOUNDARY_ROLE_COLUMN: unit_info.get(
                        "role", ""
                    ),
                    STRUCTURAL_TOPOLOGY_BOUNDARY_POLARITY_COLUMN: unit_info.get(
                        STRUCTURAL_TOPOLOGY_POLARITY_COLUMN, ""
                    ),
                    STRUCTURAL_TOPOLOGY_BOUNDARY_UNITS_COLUMN: "",
                }
            )

        self._persist_stm_composite(
            edited_side="boundaries", reset_models=True
        )
        self.update_editing_ui()
        self._notify_custom_table_metadata_changed()

    def add_model_boundary(self):
        """Add the single explicit model boundary to the current STm."""
        if self.current_table_type != STRUCTURAL_TOPOLOGY_TABLE_TYPE:
            return
        boundaries = self.boundaries_table_model.dataframe
        if any(
            is_structural_topology_model_boundary(row)
            for _, row in boundaries.iterrows()
        ):
            QMessageBox.information(
                self,
                "Model boundary already present",
                "This STm already contains a model boundary.",
            )
            return

        dialog = AddModelBoundaryDialog(
            parent=self,
            boundary_sources=self._available_model_boundary_sources(),
        )
        if dialog.exec() != QDialog.Accepted:
            return

        boundary_info = dialog.boundary_info
        feature_name = boundary_info[STRUCTURAL_TOPOLOGY_FEATURE_COLUMN]
        existing_features = {
            str(value).strip()
            for value in boundaries.get(STRUCTURAL_TOPOLOGY_FEATURE_COLUMN, [])
            if str(value).strip()
        }
        if feature_name in existing_features:
            QMessageBox.warning(
                self,
                "Duplicate boundary",
                f'A boundary named "{feature_name}" already exists in this STm.',
            )
            return

        self.boundaries_table_model.add_row_data(boundary_info)
        self._set_stm_feature_color(feature_name, boundary_info)
        options = dict(self.current_table_options or {})
        options["stm_model_boundary_source"] = dialog.source_info
        self.parent.custom_table_options[self.current_table_name] = options
        self._persist_stm_composite(
            edited_side="boundaries", reset_models=True
        )
        self.update_editing_ui()
        self._notify_custom_table_metadata_changed()

    def _selected_boundary_rows(self):
        selection_model = self.boundaries_table_view.selectionModel()
        if selection_model is None:
            return []
        selected = sorted({index.row() for index in selection_model.selectedRows()})
        if not selected:
            selected = sorted({index.row() for index in selection_model.selectedIndexes()})
        return selected

    def generate_units_from_boundaries(self):
        """Generate TU units from selected boundaries and create reciprocal links."""
        if self.current_table_type != STRUCTURAL_TOPOLOGY_TABLE_TYPE:
            return
        selected_rows = self._selected_boundary_rows()
        if not selected_rows:
            QMessageBox.information(
                self,
                "Generate units",
                "Select one or more boundary rows first.",
            )
            return
        boundaries = self.boundaries_table_model.dataframe
        selected_rows = [
            row_index
            for row_index in selected_rows
            if 0 <= row_index < len(boundaries.index)
            and not is_structural_topology_model_boundary(
                boundaries.iloc[row_index]
            )
        ]
        if not selected_rows:
            QMessageBox.information(
                self,
                "Generate units",
                "A model boundary does not represent a geological boundary "
                "and cannot generate a reference unit.",
            )
            return
        existing_units = {
            str(value).strip()
            for value in self.table_model.dataframe.get(
                STRUCTURAL_TOPOLOGY_FEATURE_COLUMN, []
            )
            if str(value).strip()
        }
        representative_links = self._stm_option_links(
            "stm_representative_links"
        )
        for row_index in selected_rows:
            if row_index < 0 or row_index >= len(boundaries.index):
                continue
            boundary_name = str(
                boundaries.iloc[row_index].get(
                    STRUCTURAL_TOPOLOGY_FEATURE_COLUMN, ""
                )
            ).strip()
            if not boundary_name:
                continue
            if boundary_name not in existing_units:
                boundary_role = str(
                    boundaries.iloc[row_index].get(
                        STRUCTURAL_TOPOLOGY_BOUNDARY_ROLE_COLUMN, ""
                    )
                ).strip().casefold()
                row_data = {
                    column_name: ""
                    for column_name in self.table_model.dataframe.columns
                }
                row_data.update(
                    {
                        STRUCTURAL_TOPOLOGY_FEATURE_COLUMN: boundary_name,
                        STRUCTURAL_TOPOLOGY_UNIT_ROLE_COLUMN: (
                            STRUCTURAL_TOPOLOGY_GENERATED_UNIT_ROLES.get(
                                boundary_role, "TU"
                            )
                        ),
                        STRUCTURAL_TOPOLOGY_UNIT_POLARITY_COLUMN: "",
                        STRUCTURAL_TOPOLOGY_UNIT_BOUNDARIES_COLUMN: boundary_name,
                    }
                )
                self.table_model.add_row_data(row_data)
                existing_units.add(boundary_name)
            linked_units = _stm_names(
                boundaries.iloc[row_index].get(
                    STRUCTURAL_TOPOLOGY_BOUNDARY_UNITS_COLUMN, ""
                )
            )
            boundaries.at[
                boundaries.index[row_index],
                STRUCTURAL_TOPOLOGY_BOUNDARY_UNITS_COLUMN,
            ] = _stm_names_cell(linked_units + [boundary_name])
            representative_links = {
                link
                for link in representative_links
                if link[0] != boundary_name
            }
            representative_links.add((boundary_name, boundary_name))
        options = dict(self.current_table_options or {})
        options["stm_representative_links"] = [
            {"unit": unit_name, "boundary": boundary_name}
            for unit_name, boundary_name in sorted(representative_links)
        ]
        self.parent.custom_table_options[self.current_table_name] = options
        self._persist_stm_composite(reset_models=True)
        self.update_editing_ui()
        self._notify_custom_table_metadata_changed()

    def add_extra_boundary(self):
        """Add a boundary that does not yet exist in the PZero project."""
        if self.current_table_type != STRUCTURAL_TOPOLOGY_TABLE_TYPE:
            return
        dialog = ExtraSTmBoundaryDialog(parent=self)
        if dialog.exec() != QDialog.Accepted:
            return
        feature = dialog.boundary_info[STRUCTURAL_TOPOLOGY_FEATURE_COLUMN]
        existing = {
            str(value).strip()
            for value in self.boundaries_table_model.dataframe.get(
                STRUCTURAL_TOPOLOGY_FEATURE_COLUMN, []
            )
        }
        if feature in existing:
            QMessageBox.warning(
                self, "Duplicate boundary", f'Boundary "{feature}" already exists.'
            )
            return
        self.boundaries_table_model.add_row_data(dialog.boundary_info)
        self._set_stm_feature_color(feature, dialog.boundary_info)
        self._persist_stm_composite(
            edited_side="boundaries", reset_models=True
        )
        self.update_editing_ui()
        self._notify_custom_table_metadata_changed()

    def add_extra_unit(self):
        """Add an editable unit directly to the Units table."""
        if self.current_table_type != STRUCTURAL_TOPOLOGY_TABLE_TYPE:
            return
        dialog = ManualSTmUnitDialog(
            parent=self, domain_columns=self.current_domain_columns
        )
        if dialog.exec() != QDialog.Accepted:
            return
        unit_info = dialog.unit_info
        feature = str(unit_info.get("feature", "")).strip()
        existing = {
            str(value).strip()
            for value in self.table_model.dataframe.get(
                STRUCTURAL_TOPOLOGY_FEATURE_COLUMN, []
            )
        }
        if feature in existing:
            QMessageBox.warning(
                self, "Duplicate unit", f'Unit "{feature}" already exists.'
            )
            return
        boundary_features = {
            str(value).strip()
            for value in self.boundaries_table_model.dataframe.get(
                STRUCTURAL_TOPOLOGY_FEATURE_COLUMN, []
            )
            if str(value).strip()
        }
        if feature not in boundary_features:
            self._set_stm_feature_color(feature, unit_info)
        row_data = {
            column_name: ""
            for column_name in self.table_model.dataframe.columns
        }
        row_data.update(
            {
                STRUCTURAL_TOPOLOGY_FEATURE_COLUMN: feature,
                STRUCTURAL_TOPOLOGY_UNIT_ROLE_COLUMN: unit_info.get(
                    "unit_role", "TU"
                ),
                STRUCTURAL_TOPOLOGY_UNIT_POLARITY_COLUMN: "",
                STRUCTURAL_TOPOLOGY_UNIT_BOUNDARIES_COLUMN: "",
            }
        )
        for domain_info in unit_info.get("domains", []):
            row_data[str(domain_info.get("column", "Domain_1"))] = (
                domain_info.get("value", "")
            )
        self.table_model.add_row_data(row_data)
        self._persist_stm_composite(edited_side="units", reset_models=True)
        self.update_editing_ui()
        self._notify_custom_table_metadata_changed()

    @staticmethod
    def _best_polarity_assignments(
        unit_names, candidates, slots, candidate_scores=None
    ):
        """Return at most two oldest injective assignments."""
        candidate_scores = candidate_scores or {}
        unit_names = tuple(
            sorted(unit_names, key=lambda name: (len(candidates[name]), name))
        )

        @lru_cache(None)
        def solve(index, used):
            if index == len(unit_names):
                return (0, 0.0), ((),)
            best_score, best = None, []
            unit_name = unit_names[index]
            for slot_key in candidates[unit_name] - used:
                tail_score, tails = solve(index + 1, used | {slot_key})
                if tail_score is None:
                    continue
                score = (
                    candidate_scores.get((unit_name, slot_key), 0)
                    + tail_score[0],
                    slots[slot_key]["value"] + tail_score[1],
                )
                assignments = ((slot_key,) + tail for tail in tails)
                if best_score is None or score > best_score:
                    best_score, best = score, list(assignments)
                elif score == best_score:
                    best.extend(assignments)
                best = best[:2]
            return best_score, tuple(best)

        _, solutions = solve(0, frozenset())
        return [
            dict(zip(unit_names, solution)) for solution in solutions
        ]

    def _unit_polarity_candidates(self):
        boundaries = self.boundaries_table_model.dataframe
        polarities = {}
        boundary_roles = {}
        for _, row in boundaries.iterrows():
            name = str(row.get(STRUCTURAL_TOPOLOGY_FEATURE_COLUMN, "")).strip()
            if not name or is_structural_topology_model_boundary(row):
                continue
            boundary_roles[name] = str(
                row.get(STRUCTURAL_TOPOLOGY_BOUNDARY_ROLE_COLUMN, "")
            ).strip().casefold()
            try:
                polarities[name] = float(
                    row.get(STRUCTURAL_TOPOLOGY_BOUNDARY_POLARITY_COLUMN, "")
                )
            except (TypeError, ValueError):
                pass

        representatives = dict(
            self._stm_option_links("stm_representative_links")
        )
        #debug
        print("[STm polarity] boundary polarities:", polarities)
        #debug
        print("[STm polarity] representative links:", representatives)
        candidates, slots = {}, {}

        def add_slot(unit_name, key, value, label):
            slots.setdefault(key, {"value": value, "label": label})
            candidates[unit_name].add(key)

        units = self.table_model.dataframe
        #debug
        print(
            f"[STm polarity] expected units={len(boundaries.index)}, "
            f"actual units={len(units.index)}"
        )
        representative_boundaries = set(representatives.values())
        for _, row in units.iterrows():
            unit_name = str(
                row.get(STRUCTURAL_TOPOLOGY_FEATURE_COLUMN, "")
            ).strip()
            if not unit_name:
                continue
            unit_role = str(
                row.get(STRUCTURAL_TOPOLOGY_UNIT_ROLE_COLUMN, "")
            ).strip().casefold()
            candidates[unit_name] = set()
            linked = set(
                _stm_names(
                    row.get(STRUCTURAL_TOPOLOGY_UNIT_BOUNDARIES_COLUMN, "")
                )
            )
            representative = representatives.get(unit_name)
            if representative and representative not in polarities:
                #debug
                print(
                    f"[STm polarity] {unit_name}: no candidates; "
                    f"representative {representative!r} has no polarity"
                )
                continue
            values = sorted(
                {polarities[name] for name in linked if name in polarities}
            )
            representative_value = polarities.get(representative)
            anchors = (
                [representative_value]
                if representative_value is not None
                else sorted(
                    {
                        polarities[name]
                        for name in linked & representative_boundaries
                        if name in polarities
                    }
                )
            )
            preferred_side = None
            if unit_role == "su" and representative:
                representative_role = boundary_roles.get(representative, "")
                if representative_role == "top":
                    preferred_side = "above"
                elif representative_role == "base":
                    preferred_side = "below"
            for anchor in anchors:
                candidate_values = (
                    (anchor + 0.5,)
                    if preferred_side == "above"
                    else (
                        (anchor - 0.5,)
                        if preferred_side == "below"
                        else (anchor - 0.5, anchor + 0.5)
                    )
                )
                for value in candidate_values:
                    side = "below" if value < anchor else "above"
                    add_slot(
                        unit_name,
                        ("polarity", value),
                        value,
                        f"{side} {anchor:g}",
                    )
            #debug
            print(
                f"[STm polarity] {unit_name}: representative="
                f"{representative!r}, linked={sorted(linked)}, "
                f"linked polarities={values}, candidates="
                f"{sorted(slots[key]['value'] for key in candidates[unit_name])}"
            )
        return candidates, slots

    def calculate_unit_polarities(self):
        """Place units in discrete level gaps allowed by their topology."""
        if self.current_table_type != STRUCTURAL_TOPOLOGY_TABLE_TYPE:
            return
        candidates, slots = self._unit_polarity_candidates()
        units = self.table_model.dataframe
        units[STRUCTURAL_TOPOLOGY_UNIT_POLARITY_COLUMN] = ""
        row_by_name = {
            str(row.get(STRUCTURAL_TOPOLOGY_FEATURE_COLUMN, "")).strip(): index
            for index, row in units.iterrows()
        }
        representatives = dict(
            self._stm_option_links("stm_representative_links")
        )
        boundary_polarities = {}
        for _, row in self.boundaries_table_model.dataframe.iterrows():
            name = str(row.get(STRUCTURAL_TOPOLOGY_FEATURE_COLUMN, "")).strip()
            try:
                boundary_polarities[name] = float(
                    row.get(STRUCTURAL_TOPOLOGY_BOUNDARY_POLARITY_COLUMN, "")
                )
            except (TypeError, ValueError):
                pass
        signatures = {
            unit_name: frozenset(
                _stm_names(
                    units.at[
                        row_index,
                        STRUCTURAL_TOPOLOGY_UNIT_BOUNDARIES_COLUMN,
                    ]
                )
            )
            for unit_name, row_index in row_by_name.items()
        }
        repeated_signatures = {
            signature
            for signature in signatures.values()
            if sum(value == signature for value in signatures.values()) > 1
        }
        candidate_scores = {}
        for unit_name, representative in representatives.items():
            if signatures.get(unit_name) in repeated_signatures:
                continue
            representative_value = boundary_polarities.get(representative)
            linked_values = {
                boundary_polarities[name]
                for name in signatures.get(unit_name, ())
                if name in boundary_polarities
            }
            for slot_key in candidates.get(unit_name, ()):
                opposite_surface = (
                    2 * slots[slot_key]["value"] - representative_value
                )
                candidate_scores[(unit_name, slot_key)] = int(
                    opposite_surface in linked_values
                )
        #debug
        print(
            "[STm polarity] topology scores:",
            {
                unit_name: {
                    slots[slot_key]["value"]: candidate_scores.get(
                        (unit_name, slot_key), 0
                    )
                    for slot_key in candidates[unit_name]
                }
                for unit_name in candidates
            },
        )

        remaining = set(candidates)
        groups = []
        while remaining:
            group = {remaining.pop()}
            group_slots = set().union(
                *(candidates[name] for name in group)
            )
            changed = True
            while changed:
                linked = {
                    name
                    for name in remaining
                    if candidates[name] & group_slots
                }
                changed = bool(linked)
                group.update(linked)
                remaining.difference_update(linked)
                group_slots.update(
                    *(candidates[name] for name in linked)
                )
            groups.append(sorted(group))

        #debug
        print(
            "[STm polarity] competing groups:",
            [
                {
                    unit_name: sorted(
                        slots[key]["value"]
                        for key in candidates[unit_name]
                    )
                    for unit_name in group
                }
                for group in groups
            ],
        )
        calculated = unresolved = 0
        for group in groups:
            solutions = self._best_polarity_assignments(
                group, candidates, slots, candidate_scores
            )
            #debug
            print(
                f"[STm polarity] solutions for {group}:",
                [
                    {
                        unit_name: slots[slot_key]["value"]
                        for unit_name, slot_key in solution.items()
                    }
                    for solution in solutions
                ],
            )
            if not solutions:
                #debug
                print(
                    f"[STm polarity] unresolved {group}: no one-to-one "
                    "assignment is available"
                )
                unresolved += len(group)
                continue
            assignment = solutions[0]
            if len(solutions) > 1:
                dialog = UnitPolarityAmbiguityDialog(
                    self, solutions, slots
                )
                if dialog.exec() != QDialog.Accepted:
                    #debug
                    print(
                        f"[STm polarity] unresolved {group}: ambiguity "
                        "dialog cancelled"
                    )
                    unresolved += len(group)
                    continue
                assignment = dialog.assignments
            for unit_name, slot_key in assignment.items():
                units.at[
                    row_by_name[unit_name],
                    STRUCTURAL_TOPOLOGY_UNIT_POLARITY_COLUMN,
                ] = slots[slot_key]["value"]
                #debug
                print(
                    f"[STm polarity] assigned {unit_name} -> "
                    f"{slots[slot_key]['value']:g} "
                    f"({slots[slot_key]['label']})"
                )
                calculated += 1

        #debug
        print(
            f"[STm polarity] completed: calculated={calculated}, "
            f"unresolved={unresolved}"
        )
        self._persist_stm_composite(reset_models=True)
        message = f"Calculated {calculated} unit levels."
        if unresolved:
            message += (
                f"\nLeft {unresolved} unresolved: the topology is ambiguous "
                "or there are fewer level gaps than units."
            )
        QMessageBox.information(self, "Unit level", message)
        self._notify_custom_table_metadata_changed()

    def add_field(self):
        table_name = self.current_table_name
        if not table_name:
            QMessageBox.information(
                self,
                "No table",
                "Create or select a table first.",
            )
            return

        if self.current_table_type == STRUCTURAL_TOPOLOGY_TABLE_TYPE:
            existing_orders = [
                structural_topology_domain_order(column_name)
                for column_name in self.current_domain_columns
            ]
            next_order = 1 if not existing_orders else max(existing_orders) + 1
            domain_order = input_text_dialog(
                parent=self,
                title="Add domain",
                label="Domain order",
                default_text=str(next_order),
            )
            if not domain_order:
                return
            try:
                domain_order_value = int(domain_order)
                if domain_order_value <= 0:
                    raise ValueError()
                field_name = structural_topology_domain_column_name(domain_order_value)
            except ValueError:
                QMessageBox.warning(
                    self,
                    "Invalid order",
                    "Insert a positive integer domain order.",
                )
                return
        else:
            field_name = input_text_dialog(
                parent=self,
                title="Add field",
                label="Field name",
                default_text="field_1",
            )

        if not field_name:
            return
        field_name = field_name.strip()
        if field_name in self.table_model.dataframe.columns.tolist():
            QMessageBox.warning(
                self,
                "Duplicate field",
                f'The field "{field_name}" already exists.',
            )
            return
        self.table_model.add_column(field_name)
        if self.current_table_type == STRUCTURAL_TOPOLOGY_TABLE_TYPE:
            self._apply_stm_dataframe(self.table_model.dataframe)
        self.update_editing_ui()
        self._notify_custom_table_metadata_changed()

    def rename_field(self):
        table_name = self.current_table_name
        if not table_name or self.table_model.columnCount() == 0:
            return

        if self.current_table_type == STRUCTURAL_TOPOLOGY_TABLE_TYPE:
            old_field_name = self._current_domain_column_name()
            if not old_field_name:
                QMessageBox.information(
                    self,
                    "No domain",
                    "Select a domain column to rename.",
                )
                return
        else:
            current_index = self.table_view.currentIndex()
            if current_index.isValid():
                column_index = current_index.column()
            else:
                column_index = self.table_model.columnCount() - 1

            old_field_name = self.table_model.dataframe.columns[column_index]

        new_field_name = input_text_dialog(
            parent=self,
            title="Rename domain"
            if self.current_table_type == STRUCTURAL_TOPOLOGY_TABLE_TYPE
            else "Rename field",
            label="New domain order"
            if self.current_table_type == STRUCTURAL_TOPOLOGY_TABLE_TYPE
            else "New field name",
            default_text=(
                str(structural_topology_domain_order(old_field_name))
                if self.current_table_type == STRUCTURAL_TOPOLOGY_TABLE_TYPE
                else str(old_field_name)
            ),
        )
        if not new_field_name:
            return

        new_field_name = new_field_name.strip()
        if not new_field_name:
            return
        if self.current_table_type == STRUCTURAL_TOPOLOGY_TABLE_TYPE:
            try:
                domain_order_value = int(new_field_name)
                if domain_order_value <= 0:
                    raise ValueError()
                new_field_name = structural_topology_domain_column_name(
                    domain_order_value
                )
            except ValueError:
                QMessageBox.warning(
                    self,
                    "Invalid order",
                    "Insert a positive integer domain order.",
                )
                return
        if (
            new_field_name != old_field_name
            and new_field_name in self.table_model.dataframe.columns.tolist()
        ):
            QMessageBox.warning(
                self,
                "Duplicate field",
                f'The field "{new_field_name}" already exists.',
            )
            return

        renamed_df = self.table_model.dataframe.rename(
            columns={old_field_name: new_field_name}
        )
        if self.current_table_type == STRUCTURAL_TOPOLOGY_TABLE_TYPE:
            self._apply_stm_dataframe(renamed_df)
        else:
            self.parent.custom_tables[table_name] = renamed_df
            self.table_model.set_dataframe(renamed_df)
        self.update_editing_ui()
        self._notify_custom_table_metadata_changed()

    def delete_field(self):
        table_name = self.current_table_name
        if not table_name or self.table_model.columnCount() == 0:
            return
        if self.current_table_type == STRUCTURAL_TOPOLOGY_TABLE_TYPE:
            field_name = self._current_domain_column_name()
            if not field_name:
                QMessageBox.information(
                    self,
                    "No domain",
                    "Select a domain column to delete.",
                )
                return
        else:
            current_index = self.table_view.currentIndex()
            if current_index.isValid():
                field_name = self.table_model.dataframe.columns[current_index.column()]
            else:
                field_name = self.table_model.dataframe.columns[-1]

        confirm = QMessageBox.question(
            self,
            "Delete domain"
            if self.current_table_type == STRUCTURAL_TOPOLOGY_TABLE_TYPE
            else "Delete field",
            (
                f'Delete domain "{field_name}"?'
                if self.current_table_type == STRUCTURAL_TOPOLOGY_TABLE_TYPE
                else f'Delete field "{field_name}"?'
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        self.table_model.remove_column(field_name)
        if self.current_table_type == STRUCTURAL_TOPOLOGY_TABLE_TYPE:
            self._apply_stm_dataframe(self.table_model.dataframe)
        self.update_editing_ui()
        self._notify_custom_table_metadata_changed()
