"""table_view_dialog.py
Dockable table view used to manage user-defined editable tables."""

from os import path as os_path

from pandas import DataFrame as pd_DataFrame
from pandas import isna as pd_isna
from pandas import to_numeric as pd_to_numeric

from PySide6.QtCore import QAbstractTableModel, Qt
from PySide6.QtGui import QAction, QColor, QBrush
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
)

from pzero.helpers.helper_dialogs import input_text_dialog
from pzero.properties_manager import PropertiesCMaps


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
        if self._editable and not self.is_preview_column(index.column()):
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
        self.table_model.set_dataframe(dataframe)
        current_type = self.parent.custom_table_types.get(table_name, "manual")
        current_options = self.parent.custom_table_options.get(table_name, {})
        if current_type == PropertiesCMaps.custom_colormap_table_type:
            mode_label = (
                "exact intervals"
                if current_options.get("mode") == "discrete"
                else "continuous"
            )
            self.current_table_label.setText(
                f"Table: {table_name} [Colormap, {mode_label}]"
            )
        else:
            self.current_table_label.setText(f"Table: {table_name}")
        self.update_editing_ui()

    def on_editing_toggled(self, checked):
        self.editing_enabled = bool(checked)
        self.update_editing_ui()

    def on_table_model_edited(self):
        """React to cell edits coming from the table model."""
        self._notify_custom_table_metadata_changed()

    def on_table_view_clicked(self, index):
        """Handle clicks on the virtual color preview cells for colormap tables."""
        if (
            not index.isValid()
            or not self.editing_enabled
            or self.current_table_type != PropertiesCMaps.custom_colormap_table_type
            or not self.table_model.is_preview_column(index.column())
        ):
            return

        current_color = self.table_model._row_preview_color(index.row())
        if current_color is None:
            current_color = QColor(255, 255, 255)

        color_out = QColorDialog.getColor(current_color, self)
        if not color_out.isValid():
            return

        self.table_model.update_row_color(index.row(), color_out)

    def update_editing_ui(self):
        is_colormap_table = (
            self.current_table_type == PropertiesCMaps.custom_colormap_table_type
        )
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

        self.editing_toggle_button.setText(
            "Disable editing" if self.editing_enabled else "Enable editing"
        )
        self.new_table_button.setEnabled(True)
        self.delete_table_button.setEnabled(has_table)
        self.export_table_button.setEnabled(has_table)
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

    def add_row(self):
        table_name = self.current_table_name
        if not table_name:
            QMessageBox.information(
                self,
                "No table",
                "Create or select a table first.",
            )
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
        self.update_editing_ui()
        self._notify_custom_table_metadata_changed()

    def rename_field(self):
        table_name = self.current_table_name
        if not table_name or self.table_model.columnCount() == 0:
            return

        current_index = self.table_view.currentIndex()
        if current_index.isValid():
            column_index = current_index.column()
        else:
            column_index = self.table_model.columnCount() - 1

        old_field_name = self.table_model.dataframe.columns[column_index]
        new_field_name = input_text_dialog(
            parent=self,
            title="Rename field",
            label="New field name",
            default_text=str(old_field_name),
        )
        if not new_field_name:
            return

        new_field_name = new_field_name.strip()
        if not new_field_name:
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
        self.parent.custom_tables[table_name] = renamed_df
        self.table_model.set_dataframe(renamed_df)
        self.update_editing_ui()
        self._notify_custom_table_metadata_changed()

    def delete_field(self):
        table_name = self.current_table_name
        if not table_name or self.table_model.columnCount() == 0:
            return

        current_index = self.table_view.currentIndex()
        if current_index.isValid():
            field_name = self.table_model.dataframe.columns[current_index.column()]
        else:
            field_name = self.table_model.dataframe.columns[-1]

        confirm = QMessageBox.question(
            self,
            "Delete field",
            f'Delete field "{field_name}"?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        self.table_model.remove_column(field_name)
        self.update_editing_ui()
        self._notify_custom_table_metadata_changed()
