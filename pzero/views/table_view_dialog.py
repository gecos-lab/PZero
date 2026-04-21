"""table_view_dialog.py
Dockable table view used to manage user-defined editable tables."""

from os import path as os_path
from hashlib import md5

from pandas import DataFrame as pd_DataFrame
from pandas import isna as pd_isna
from pandas import to_numeric as pd_to_numeric

from PySide6.QtCore import QAbstractTableModel, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QBrush, QPen, QFont, QFontMetrics, QPainter
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
    QComboBox,
    QFormLayout,
    QColorDialog,
    QStyledItemDelegate,
    QGraphicsView,
    QGraphicsScene,
)

from pzero.helpers.helper_dialogs import input_text_dialog
from pzero.properties_manager import PropertiesCMaps

STRUCTURAL_TOPOLOGY_TABLE_TYPE = "stm"
STRUCTURAL_TOPOLOGY_BASE_COLUMNS = [
    "Name",
    "Unit",
    "Representative Surfaces",
    "Structural Polarity",
    "Domain_1",
]
STRUCTURAL_TOPOLOGY_PROTECTED_COLUMNS = {
    "Name",
    "Unit",
    "Representative Surfaces",
    "Structural Polarity",
}
STRUCTURAL_TOPOLOGY_UNIT_VALUES = [
    "TMU",
    "TSU",
    "SU",
    "IU",
    "SZ",
    "NonVolumetric",
]
STRUCTURAL_TOPOLOGY_REPRESENTATIVE_VALUES = ["No", "Yes"]


def structural_topology_name(feature_name=None, role_name=None):
    """Return the display name used by STm rows."""
    feature_name = "" if feature_name is None else str(feature_name).strip()
    role_name = "" if role_name is None else str(role_name).strip()
    return f"{feature_name}_{role_name}".strip("_")


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


def normalise_structural_topology_representative_value(raw_value):
    """Return the canonical Representative Surfaces value."""
    value = str(raw_value or "").strip().casefold()
    if value in {"yes", "1"}:
        return "Yes"
    return "No"


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

    def __init__(self, parent=None, table_name=None, dataframe_provider=None):
        super().__init__(parent)
        self.table_name = str(table_name or "").strip() or "STm"
        self.dataframe_provider = dataframe_provider
        self.setWindowTitle(f"Build STm - {self.table_name}")
        self.resize(1120, 860)
        self._fit_on_next_rebuild = True

        layout = QVBoxLayout(self)
        info_label = QLabel(
            "Units are shown on the left, representative surfaces on the right, ordered by increasing structural polarity."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        self.graphics_view = ZoomableGraphicsView(self)
        self.graphics_view.setRenderHint(QPainter.Antialiasing, True)
        self.graphics_view.setRenderHint(QPainter.TextAntialiasing, True)
        self.graphics_view.setDragMode(QGraphicsView.ScrollHandDrag)
        self.graphics_view.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.scene = QGraphicsScene(self)
        self.graphics_view.setScene(self.scene)
        layout.addWidget(self.graphics_view, 1)

        buttons_layout = QHBoxLayout()
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.rebuild_scene)
        buttons_layout.addWidget(self.refresh_button)
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
        zoom_hint_label = QLabel("Ctrl + mouse wheel to zoom")
        buttons_layout.addWidget(zoom_hint_label)
        buttons_layout.addStretch(1)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        buttons_layout.addWidget(close_button)
        layout.addLayout(buttons_layout)

        self.rebuild_scene()

    def rebuild_scene(self):
        """Rebuild the graphics scene from the current STm table."""
        self.scene.clear()
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

    def _draw_scene(self, dataframe):
        """Populate the scene with STm nodes and the automatically-derived links."""
        header_font = QFont()
        header_font.setPointSize(16)
        header_font.setBold(True)
        self.scene.addText("Units", header_font).setPos(self.LEFT_X - 70, 35)
        self.scene.addText("Representative Surfaces", header_font).setPos(
            self.RIGHT_X - 140, 35
        )

        if dataframe is None or dataframe.empty:
            empty_text = self.scene.addText("The STm table is empty.")
            empty_text.setPos(260, 220)
            return

        rows = self._build_rows_payload(dataframe)
        unit_nodes = []
        surface_nodes = []
        paired_links = []
        domain_groups = {}

        for row_idx, row_info in enumerate(rows):
            row_color = structural_topology_color(row_info["Name"])
            row_color_dark = row_color.darker(150)
            row_nodes = []

            if row_info["Unit"] != "NonVolumetric":
                unit_nodes.append(
                    {
                        "key": f"unit:{row_idx}",
                        "label": f'{row_info["Unit"]}_{row_info["Name"]}',
                        "polarity": row_info["Structural Polarity"],
                        "brush": row_color,
                        "pen": row_color_dark,
                        "row_idx": row_idx,
                    }
                )
                row_nodes.append(f"unit:{row_idx}")

            if row_info["Representative Surfaces"] == "Yes":
                surface_nodes.append(
                    {
                        "key": f"surface:{row_idx}",
                        "label": f'Sur_{row_info["Name"]}',
                        "polarity": row_info["Structural Polarity"],
                        "brush": row_color,
                        "pen": row_color_dark,
                        "row_idx": row_idx,
                    }
                )
                row_nodes.append(f"surface:{row_idx}")

            if len(row_nodes) == 2:
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

        surface_nodes.append(
            {
                "key": "surface:boundary",
                "label": "Boundary",
                "polarity": float("inf"),
                "brush": QColor(255, 255, 255),
                "pen": QColor(30, 30, 30),
                "row_idx": None,
            }
        )

        unit_nodes.sort(key=lambda node: (node["polarity"], str(node["label"]).casefold()))
        surface_nodes.sort(
            key=lambda node: (
                node["polarity"],
                1 if node["key"] == "surface:boundary" else 0,
                str(node["label"]).casefold(),
            )
        )

        node_items = {}
        for node_idx, node_info in enumerate(unit_nodes):
            node_items[node_info["key"]] = self._add_node(
                center_x=self.LEFT_X,
                center_y=self.TOP_Y + node_idx * self.Y_STEP,
                label=node_info["label"],
                fill_color=node_info["brush"],
                outline_color=node_info["pen"],
            )

        for node_idx, node_info in enumerate(surface_nodes):
            node_items[node_info["key"]] = self._add_node(
                center_x=self.RIGHT_X,
                center_y=self.TOP_Y + node_idx * self.Y_STEP,
                label=node_info["label"],
                fill_color=node_info["brush"],
                outline_color=node_info["pen"],
            )

        self._add_domain_boxes(domain_groups=domain_groups, node_items=node_items)

        for link_info in paired_links:
            source_item = node_items.get(link_info["source"])
            target_item = node_items.get(link_info["target"])
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

    def _build_rows_payload(self, dataframe):
        """Convert the dataframe into normalized STm rows."""
        rows = []
        ordered_df = dataframe.copy()
        if "Structural Polarity" in ordered_df.columns:
            ordered_df["_sort_polarity"] = ordered_df["Structural Polarity"].apply(
                structural_topology_sort_key
            )
            ordered_df.sort_values(
                by=["_sort_polarity", "Name"], ascending=[True, True], inplace=True
            )
        for _, row in ordered_df.iterrows():
            row_name = str(row.get("Name", "")).strip()
            if not row_name:
                continue
            domains = []
            for column_name in ordered_df.columns.tolist():
                if structural_topology_domain_order(column_name) is None:
                    continue
                domain_value = str(row.get(column_name, "")).strip()
                if domain_value:
                    domains.append((column_name, domain_value))
            rows.append(
                {
                    "Name": row_name,
                    "Unit": str(row.get("Unit", "NonVolumetric")).strip() or "NonVolumetric",
                    "Representative Surfaces": normalise_structural_topology_representative_value(
                        row.get("Representative Surfaces", "No")
                    ),
                    "Structural Polarity": structural_topology_sort_key(
                        row.get("Structural Polarity", "")
                    ),
                    "Domains": domains,
                }
            )
        return rows

    def _add_node(self, center_x=None, center_y=None, label=None, fill_color=None, outline_color=None):
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

        text_item = self.scene.addText(str(label), font)
        text_rect = text_item.boundingRect()
        text_item.setPos(
            center_x - text_rect.width() / 2,
            center_y - text_rect.height() / 2 - 4,
        )
        text_item.setDefaultTextColor(QColor(20, 20, 20))
        text_item.setZValue(1)

        return {
            "rect": (rect_x, rect_y, rect_width, rect_height),
            "left_anchor": (rect_x, center_y),
            "right_anchor": (rect_x + rect_width, center_y),
            "top": rect_y,
            "bottom": rect_y + rect_height,
            "left": rect_x,
            "right": rect_x + rect_width,
        }

    def _add_domain_boxes(self, domain_groups=None, node_items=None):
        """Draw domain boxes around nodes sharing the same domain value."""
        domain_groups = domain_groups or {}
        node_items = node_items or {}

        for (domain_column, domain_value), group_info in domain_groups.items():
            if len(group_info.get("rows", set())) < 2:
                continue
            node_keys = group_info.get("nodes", set())
            available_nodes = [node_items[node_key] for node_key in node_keys if node_key in node_items]
            if len(available_nodes) < 2:
                continue

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
            domain_rect = self.scene.addRect(
                left,
                top,
                right - left,
                bottom - top,
                domain_pen,
                QBrush(Qt.NoBrush),
            )
            domain_rect.setZValue(-25 - order_value)

            domain_label = self.scene.addText(f"D{order_value}: {domain_value}")
            domain_label.setDefaultTextColor(domain_color)
            domain_label.setPos(left + 12, top - 30)
            domain_label.setZValue(-24 - order_value)


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

    def __init__(self, dataframe=None, parent=None):
        super().__init__(parent)
        self._dataframe = dataframe if dataframe is not None else pd_DataFrame()
        self._editable = False
        self._show_colormap_preview = False

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
        if self.parent() and hasattr(self.parent(), "is_table_column_editable"):
            if not self.parent().is_table_column_editable(index.column()):
                return False
        self._dataframe.iloc[index.row(), index.column()] = (
            "" if value is None else str(value)
        )
        self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.EditRole])
        preview_index = self.index(index.row(), self.preview_column_index)
        if self._show_colormap_preview:
            self.dataChanged.emit(preview_index, preview_index, [Qt.BackgroundRole])
        if self.parent() and hasattr(self.parent(), "on_table_model_edited"):
            self.parent().on_table_model_edited()
        return True

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemIsEnabled
        flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        is_column_editable = True
        if self.parent() and hasattr(self.parent(), "is_table_column_editable"):
            is_column_editable = self.parent().is_table_column_editable(index.column())
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
            self.parent().on_table_model_edited()

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
            "The Structural Topology model starts from geology legend units and keeps structural polarity linked to the legend."
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
    """Dialog used to import legend units into an STm table."""

    def __init__(self, parent=None, units_provider=None, existing_names=None):
        super().__init__(parent)
        self.setWindowTitle("Import Units")
        self.resize(460, 420)
        self.units_provider = units_provider
        self.existing_names = set(existing_names or [])

        layout = QVBoxLayout(self)
        info_label = QLabel(
            "Select the geological legend units to add to the Structural Topology model."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        refresh_button = QPushButton("Refresh units from legend")
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
    def selected_unit_names(self):
        selected_names = []
        for row_idx in range(self.units_list.count()):
            item = self.units_list.item(row_idx)
            if (
                item.flags() & Qt.ItemIsEnabled
                and item.checkState() == Qt.Checked
            ):
                selected_names.append(item.data(Qt.UserRole))
        return selected_names

    def populate_units(self):
        self.units_list.clear()
        units = []
        if callable(self.units_provider):
            units = list(self.units_provider() or [])

        if not units:
            self.units_list.addItem(
                QListWidgetItem("No geological legend units available.")
            )
            self.units_list.item(0).setFlags(Qt.NoItemFlags)
            return

        for unit_info in units:
            unit_name = str(unit_info.get("Name", "")).strip()
            role_name = str(unit_info.get("role", "")).strip()
            polarity_value = str(unit_info.get("Structural Polarity", "")).strip()
            item = QListWidgetItem(unit_name)
            item.setData(Qt.UserRole, unit_name)
            tooltip_txt = f"Structural polarity: {polarity_value}"
            if role_name:
                tooltip_txt += f"\nRole: {role_name}"
            item.setToolTip(tooltip_txt)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            if unit_name in self.existing_names:
                item.setCheckState(Qt.Checked)
                item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
            else:
                item.setCheckState(Qt.Unchecked)
            self.units_list.addItem(item)

    def validate_and_accept(self):
        if not self.selected_unit_names:
            QMessageBox.warning(
                self,
                "No units selected",
                "Select at least one unit to import.",
            )
            return
        self.accept()


class ViewTable(QWidget):
    """Dockable view that lists and edits user-defined project tables."""

    EXPORT_FILTER = (
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

        self.build_stm_button = QPushButton("Build STm")
        self.build_stm_button.clicked.connect(self.build_structural_topology_model)
        self.build_stm_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        left_layout.addWidget(self.build_stm_button)

        right_panel = QWidget(self)
        right_layout = QVBoxLayout(right_panel)
        self.current_table_label = QLabel("No table selected")
        right_layout.addWidget(self.current_table_label)

        toolbar_layout = QHBoxLayout()
        self.editing_toggle_button = QPushButton("Enable editing")
        self.editing_toggle_button.setCheckable(True)
        self.editing_toggle_button.toggled.connect(self.on_editing_toggled)
        self.add_row_button = QPushButton("Add row")
        self.add_row_button.clicked.connect(self.add_row)
        self.delete_row_button = QPushButton("Delete row")
        self.delete_row_button.clicked.connect(self.delete_selected_rows)
        self.add_field_button = QPushButton("Add field")
        self.add_field_button.clicked.connect(self.add_field)
        self.rename_field_button = QPushButton("Rename field")
        self.rename_field_button.clicked.connect(self.rename_field)
        self.delete_field_button = QPushButton("Delete field")
        self.delete_field_button.clicked.connect(self.delete_field)
        toolbar_layout.addWidget(self.editing_toggle_button)
        toolbar_layout.addWidget(self.add_row_button)
        toolbar_layout.addWidget(self.delete_row_button)
        toolbar_layout.addWidget(self.add_field_button)
        toolbar_layout.addWidget(self.rename_field_button)
        toolbar_layout.addWidget(self.delete_field_button)
        right_layout.addLayout(toolbar_layout)

        self.table_view = QTableView()
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.table_view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table_view.setAlternatingRowColors(True)
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table_view.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.table_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_model = EditableDataFrameModel(parent=self)
        self.table_view.setModel(self.table_model)
        self.table_view.clicked.connect(self.on_table_view_clicked)
        right_layout.addWidget(self.table_view)

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

    def is_table_column_editable(self, column_index: int) -> bool:
        column_name = self.current_dataframe_column_name(column_index)
        if column_name is None:
            return False
        if self.current_table_type != STRUCTURAL_TOPOLOGY_TABLE_TYPE:
            return True
        return column_name != "Name"

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
        if column_name in {"Unit", "Representative Surfaces"}:
            return column_name
        return None

    def _normalise_stm_dataframe_columns(self, dataframe):
        """Return an STm dataframe with ordered core/domain columns."""
        if dataframe is None:
            return pd_DataFrame(columns=STRUCTURAL_TOPOLOGY_BASE_COLUMNS)

        out_df = dataframe.copy()
        if "Domain" in out_df.columns and "Domain_1" not in out_df.columns:
            out_df = out_df.rename(columns={"Domain": "Domain_1"})
        if "Representative Surfaces" not in out_df.columns:
            out_df["Representative Surfaces"] = "No"
        else:
            out_df["Representative Surfaces"] = out_df["Representative Surfaces"].apply(
                normalise_structural_topology_representative_value
            )
        if not any(
            structural_topology_domain_order(column_name) is not None
            for column_name in out_df.columns.tolist()
        ):
            out_df["Domain_1"] = ""

        ordered_columns = [
            column_name
            for column_name in [
                "Name",
                "Unit",
                "Representative Surfaces",
                "Structural Polarity",
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
        """Assign a normalised STm dataframe to the current table/model."""
        table_name = self.current_table_name
        if not table_name:
            return
        normalised_df = self._normalise_stm_dataframe_columns(dataframe)
        self.parent.custom_tables[table_name] = normalised_df
        self.table_model.set_dataframe(normalised_df)

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
        if "Unit" in dataframe_columns:
            self.table_view.setItemDelegateForColumn(
                dataframe_columns.index("Unit"),
                ComboBoxItemDelegate(
                    values=STRUCTURAL_TOPOLOGY_UNIT_VALUES,
                    parent=self.table_view,
                ),
            )
        if "Representative Surfaces" in dataframe_columns:
            self.table_view.setItemDelegateForColumn(
                dataframe_columns.index("Representative Surfaces"),
                ComboBoxItemDelegate(
                    values=STRUCTURAL_TOPOLOGY_REPRESENTATIVE_VALUES,
                    parent=self.table_view,
                ),
            )

    def _available_stm_units(self):
        if hasattr(self.parent, "get_structural_topology_legend_units"):
            return self.parent.get_structural_topology_legend_units()

        legend_df = getattr(getattr(self.parent, "geol_coll", None), "legend_df", None)
        if legend_df is None or legend_df.empty:
            return []

        units_map = {}
        for _, row in legend_df.iterrows():
            unit_name = structural_topology_name(
                feature_name=row.get("feature", ""),
                role_name=row.get("role", ""),
            )
            if not unit_name or unit_name in units_map:
                continue
            units_map[unit_name] = {
                "Name": unit_name,
                "Unit": "NonVolumetric",
                "Representative Surfaces": "No",
                "Structural Polarity": row.get("time", 0.0),
                "Domain_1": "",
                "feature": str(row.get("feature", "")).strip(),
                "role": str(row.get("role", "")).strip(),
            }

        return sorted(
            units_map.values(),
            key=lambda unit_info: str(unit_info.get("Name", "")).casefold(),
        )

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
            self._apply_stm_dataframe(dataframe)
        else:
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

    def on_table_model_edited(self):
        """React to cell edits coming from the table model."""
        if (
            self.current_table_type == STRUCTURAL_TOPOLOGY_TABLE_TYPE
            and hasattr(self.parent, "sync_structural_topology_table_to_legend")
        ):
            self.parent.sync_structural_topology_table_to_legend(self.current_table_name)
        self._notify_custom_table_metadata_changed()

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
        edit_triggers = (
            QAbstractItemView.DoubleClicked
            | QAbstractItemView.EditKeyPressed
            | QAbstractItemView.AnyKeyPressed
        )
        self.table_view.setEditTriggers(
            edit_triggers if self.editing_enabled else QAbstractItemView.NoEditTriggers
        )

        has_table = bool(self.current_table_name)
        has_columns = self.table_model.columnCount() > 0
        has_rows = self.table_model.rowCount() > 0
        allow_structure_edit = self.editing_enabled and has_table
        allow_row_edit = allow_structure_edit and has_columns
        allow_column_edit = allow_structure_edit and has_columns and not is_colormap_table
        selected_domain_column = self._current_domain_column_name()

        self.editing_toggle_button.setText(
            "Disable editing" if self.editing_enabled else "Enable editing"
        )
        if is_stm_table:
            self.add_row_button.setText("Import Units")
            self.delete_row_button.setText("Remove unit")
            self.add_field_button.setText("Add domain")
            self.rename_field_button.setText("Rename domain")
            self.delete_field_button.setText("Delete domain")
        else:
            self.add_row_button.setText("Add row")
            self.delete_row_button.setText("Delete row")
            self.add_field_button.setText("Add field")
            self.rename_field_button.setText("Rename field")
            self.delete_field_button.setText("Delete field")
        self.new_table_button.setEnabled(True)
        self.delete_table_button.setEnabled(has_table)
        self.export_table_button.setEnabled(has_table)
        self.build_stm_button.setVisible(is_stm_table)
        self.build_stm_button.setEnabled(is_stm_table and has_rows)
        if is_stm_table:
            self.add_row_button.setEnabled(allow_structure_edit)
            self.delete_row_button.setEnabled(allow_structure_edit and has_rows)
            self.add_field_button.setEnabled(allow_structure_edit)
            self.rename_field_button.setEnabled(
                allow_structure_edit and bool(selected_domain_column)
            )
            self.delete_field_button.setEnabled(
                allow_structure_edit and bool(selected_domain_column)
            )
        else:
            self.add_row_button.setEnabled(allow_row_edit)
            self.delete_row_button.setEnabled(allow_row_edit and has_rows)
            self.add_field_button.setEnabled(allow_structure_edit)
            self.rename_field_button.setEnabled(allow_column_edit)
            self.delete_field_button.setEnabled(allow_column_edit)
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

        output_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            f"Export table {table_name}",
            table_name,
            self.EXPORT_FILTER,
            "CSV files (*.csv)",
        )
        if not output_path:
            return

        output_path, delimiter = self._normalise_export_path(
            file_path=output_path,
            selected_filter=selected_filter,
        )

        try:
            self.parent.custom_tables[table_name].to_csv(
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
        )
        dialog.exec()

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

        selection_model = self.table_view.selectionModel()
        if selection_model is None:
            return

        selected_rows = sorted(
            {index.row() for index in selection_model.selectedRows()},
            reverse=True,
        )
        if not selected_rows and self.table_view.currentIndex().isValid():
            selected_rows = [self.table_view.currentIndex().row()]
        if not selected_rows:
            return
        self.table_model.remove_rows(selected_rows)
        self.update_editing_ui()
        if (
            self.current_table_type == STRUCTURAL_TOPOLOGY_TABLE_TYPE
            and hasattr(self.parent, "sync_structural_topology_table_to_legend")
        ):
            self.parent.sync_structural_topology_table_to_legend(self.current_table_name)
        self._notify_custom_table_metadata_changed()

    def import_structural_topology_units(self):
        """Append selected geology legend units to the current STm table."""
        table_name = self.current_table_name
        if not table_name:
            return

        existing_names = set()
        if "Name" in self.table_model.dataframe.columns:
            existing_names = {
                str(value).strip()
                for value in self.table_model.dataframe["Name"].tolist()
                if str(value).strip()
            }

        dialog = ImportStructuralTopologyUnitsDialog(
            parent=self,
            units_provider=self._available_stm_units,
            existing_names=existing_names,
        )
        if dialog.exec() != QDialog.Accepted:
            return

        units_by_name = {
            unit_info["Name"]: unit_info for unit_info in self._available_stm_units()
        }
        for selected_name in dialog.selected_unit_names:
            unit_info = units_by_name.get(selected_name)
            if not unit_info:
                continue
            row_data = {}
            for column_name in self.table_model.dataframe.columns.tolist():
                row_data[column_name] = unit_info.get(column_name, "")
            self.table_model.add_row_data(row_data)

        if hasattr(self.parent, "sync_structural_topology_table_to_legend"):
            self.parent.sync_structural_topology_table_to_legend(table_name)
        self.update_editing_ui()
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
