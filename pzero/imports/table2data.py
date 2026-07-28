"""table2data.py
Generic importer for custom editable project tables."""

import json
from os import path as os_path

from pandas import read_csv as pd_read_csv
from pandas import DataFrame as pd_DataFrame

from PySide6.QtCore import QEventLoop
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QFormLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QTableWidgetItem,
)

from pzero.helpers.helper_dialogs import PCDataModel, open_files_dialog
from pzero.helpers.helper_functions import auto_sep
from pzero.helpers.structural_topology import (
    STM_JSON_SCHEMA,
    read_stm_json,
)
from pzero.properties_manager import PropertiesCMaps
from pzero.ui.import_window_ui import Ui_ImportOptionsWindow


TEXT_TABLE_FILTER = (
    "Supported table files (*.csv *.dat *.txt *.tsv *.asc *.xyz *.json);;"
    "STm JSON files (*.json);;"
    "CSV files (*.csv);;"
    "Delimited text files (*.dat *.txt *.tsv *.asc *.xyz)"
)
SPECIAL_ASSIGNMENTS = ["As is", "User defined", "N.a."]
COLORMAP_ASSIGNMENTS = ["value", "color_R", "color_G", "color_B"]
STRUCTURAL_TOPOLOGY_TABLE_TYPE = "stm"
STRUCTURAL_TOPOLOGY_FEATURE_COLUMN = "Feature"
STRUCTURAL_TOPOLOGY_UNIT_ROLE_COLUMN = "Unit Role"
STRUCTURAL_TOPOLOGY_POLARITY_COLUMN = "Structural Polarity"
STRUCTURAL_TOPOLOGY_REQUIRED_COLUMNS = [
    STRUCTURAL_TOPOLOGY_FEATURE_COLUMN,
    STRUCTURAL_TOPOLOGY_UNIT_ROLE_COLUMN,
    STRUCTURAL_TOPOLOGY_POLARITY_COLUMN,
]
STRUCTURAL_TOPOLOGY_EXPORT_MARKER_BEGIN = "# PZERO_STM_EXPORT BEGIN"
STRUCTURAL_TOPOLOGY_EXPORT_MARKER_END = "# PZERO_STM_EXPORT END"
STRUCTURAL_TOPOLOGY_UNIT_VALUES = [
    "TU",
    "SU",
    "IU",
    "SD",
    "Discontinuity",
]


def _normalise_stm_unit_role(raw_value):
    """Return a valid canonical Unit Role value."""
    value = str(raw_value or "").strip()
    valid_by_casefold = {
        str(valid_value).casefold(): str(valid_value)
        for valid_value in STRUCTURAL_TOPOLOGY_UNIT_VALUES
    }
    return valid_by_casefold.get(
        value.casefold(),
        value or "Discontinuity",
    )


def _count_file_lines(file_path):
    """Return the number of lines in a text file."""
    with open(file_path, "rb") as input_stream:
        return sum(1 for _line in input_stream)


def _resolve_pandas_separator(delimiter):
    """Return the separator/engine pair to use with pandas."""
    if delimiter == " ":
        return r"\s+", "python"
    return delimiter, "python"


def _finalise_field_name(raw_name, fallback_name):
    """Return the final custom field name."""
    final_name = str(raw_name or "").strip()
    if final_name:
        return final_name
    return str(fallback_name)


def _unique_table_name(existing_names, base_name):
    """Generate a unique table name preserving the original base name."""
    clean_base_name = str(base_name or "").strip() or "table"
    if clean_base_name not in existing_names:
        return clean_base_name

    suffix = 1
    while True:
        candidate = f"{clean_base_name}_{suffix}"
        if candidate not in existing_names:
            return candidate
        suffix += 1


def _stm_import_payload(payload):
    if not isinstance(payload, dict) or payload.get("schema") != STM_JSON_SCHEMA:
        return None
    decoded = read_stm_json(payload)
    return {
        "schema": STM_JSON_SCHEMA,
        "version": 3,
        "table_type": STRUCTURAL_TOPOLOGY_TABLE_TYPE,
        "table_name": decoded["name"],
        "options": {
            "stm_schema_version": 3,
            "stm_tables": {
                "boundaries": decoded["boundaries"],
                "units": decoded["units"],
            },
        },
    }


def _read_stm_export_payload(file_path):
    """Read an STm v3 JSON file or a v3 footer embedded in a CSV file."""
    if str(file_path).lower().endswith(".json"):
        try:
            with open(file_path, "r", encoding="utf-8-sig") as input_stream:
                payload = json.load(input_stream)
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return None
        return _stm_import_payload(payload)
    try:
        with open(file_path, "r", encoding="utf-8") as input_stream:
            file_lines = input_stream.readlines()
    except OSError:
        return None

    end_index = None
    for line_index in range(len(file_lines) - 1, -1, -1):
        if file_lines[line_index].strip() == STRUCTURAL_TOPOLOGY_EXPORT_MARKER_END:
            end_index = line_index
            break
    if end_index is None:
        return None

    start_index = None
    for line_index in range(end_index - 1, -1, -1):
        if file_lines[line_index].strip() == STRUCTURAL_TOPOLOGY_EXPORT_MARKER_BEGIN:
            start_index = line_index + 1
            break
    if start_index is None:
        return None

    json_lines = []
    for line in file_lines[start_index:end_index]:
        stripped_line = line.lstrip()
        if not stripped_line.startswith("#"):
            continue
        json_lines.append(stripped_line[1:].lstrip())

    payload_text = "\n".join(json_lines).strip()
    if not payload_text:
        return None

    try:
        payload = json.loads(payload_text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None

    return _stm_import_payload(payload)


def _stm_boundary_dataframe(payload):
    """Return the compatibility boundary projection used by existing import UI."""
    rows = []
    stm_tables = (payload or {}).get("options", {}).get("stm_tables", {})
    for boundary in stm_tables.get("boundaries", []):
        if not isinstance(boundary, dict):
            continue
        rows.append(
            {
                STRUCTURAL_TOPOLOGY_FEATURE_COLUMN: boundary.get("Feature", ""),
                STRUCTURAL_TOPOLOGY_UNIT_ROLE_COLUMN: "Discontinuity",
                STRUCTURAL_TOPOLOGY_POLARITY_COLUMN: boundary.get("Polarity", ""),
                "Domain_1": "",
            }
        )
    return pd_DataFrame(rows) if rows else pd_DataFrame(
        columns=STRUCTURAL_TOPOLOGY_REQUIRED_COLUMNS + ["Domain_1"]
    )


class TableImportDialog(QMainWindow, Ui_ImportOptionsWindow):
    """Dialog used to preview and map generic tabular files into custom tables."""

    sep_dict = {"<space>": " ", "<comma>": ",", "<semi-col>": ";", "<tab>": "\t"}

    def __init__(self, parent=None, in_file_names=None, *args, **kwargs):
        self.loop = QEventLoop()
        super(TableImportDialog, self).__init__(parent, *args, **kwargs)
        self.setupUi(self)

        self.parent = parent
        self.in_file_names = list(in_file_names or [])
        self.result = None
        self.input_data_df = None
        self.rename_dict = {}
        self._is_populating_table = False
        self.preview_stm_payload = None
        self.preview_path = self._pick_preview_path()

        self.setWindowTitle("Import tables")
        self._setup_window()
        self._connect_signals()
        self._load_initial_preview()

    def _setup_window(self):
        """Configure static UI elements."""
        self.AssignTable.setColumnCount(3)
        self.AssignTable.setHorizontalHeaderLabels(
            ["Column name", "Assigned field", "Custom field name"]
        )
        self.AssignTable.setColumnWidth(1, 180)
        self.AssignTable.setColumnWidth(2, 240)

        self.PathlineEdit.hide()
        self.PathtoolButton.hide()
        self.ImportGroupBox.hide()
        self.OptionsFrame.setFrameShape(QFrame.Shape.NoFrame)
        self.OptionsLayout.setContentsMargins(0, 0, 0, 0)
        self.dataPreviewLabel.setText("Data preview")
        self.dataAssignLabel.setText("Field mapping")

        self.HasHeaderCheckBox = QCheckBox(self.OptionsFrame)
        self.HasHeaderCheckBox.setText("First row contains headers")
        self.HasHeaderCheckBox.setChecked(True)
        self.formLayout.setWidget(3, QFormLayout.ItemRole.LabelRole, QLabel("Headers"))
        self.formLayout.setWidget(
            3, QFormLayout.ItemRole.FieldRole, self.HasHeaderCheckBox
        )

        self.ImportAsColormapCheckBox = QCheckBox(self.OptionsFrame)
        self.ImportAsColormapCheckBox.setText("Import as colormap")
        self.ImportAsColormapCheckBox.setChecked(False)
        self.formLayout.setWidget(
            4, QFormLayout.ItemRole.LabelRole, QLabel("Advanced type")
        )
        self.formLayout.setWidget(
            4, QFormLayout.ItemRole.FieldRole, self.ImportAsColormapCheckBox
        )

        self.ImportAsSTmCheckBox = QCheckBox(self.OptionsFrame)
        self.ImportAsSTmCheckBox.setText("Import as STm")
        self.ImportAsSTmCheckBox.setChecked(False)
        self.formLayout.setWidget(
            5, QFormLayout.ItemRole.LabelRole, QLabel("STm type")
        )
        self.formLayout.setWidget(
            5, QFormLayout.ItemRole.FieldRole, self.ImportAsSTmCheckBox
        )

        self.ColormapModeComboBox = QComboBox(self.OptionsFrame)
        self.ColormapModeComboBox.addItems(["Continuous", "Exact intervals"])
        self.ColormapModeComboBox.setEnabled(False)
        self.formLayout.setWidget(
            6, QFormLayout.ItemRole.LabelRole, QLabel("Colormap mode")
        )
        self.formLayout.setWidget(
            6, QFormLayout.ItemRole.FieldRole, self.ColormapModeComboBox
        )

        self.StartRowspinBox.setValue(0)
        self._set_default_import_range()

    def _connect_signals(self):
        """Connect UI signals."""
        self.StartRowspinBox.valueChanged.connect(self._refresh_preview)
        self.EndRowspinBox.valueChanged.connect(self._refresh_preview)
        self.SeparatorcomboBox.currentTextChanged.connect(self._refresh_preview)
        self.HasHeaderCheckBox.toggled.connect(self._refresh_preview)
        self.ImportAsColormapCheckBox.toggled.connect(self._on_import_as_colormap_toggled)
        self.ImportAsSTmCheckBox.toggled.connect(self._on_import_as_stm_toggled)
        self.ColormapModeComboBox.currentTextChanged.connect(
            self._on_colormap_mode_changed
        )
        self.PreviewButton.clicked.connect(self._refresh_preview)
        self.ConfirmBox.accepted.connect(self._validate_and_accept)
        self.ConfirmBox.rejected.connect(self.reject)

    def _available_assignments(self):
        """Return the assignment options available in the current import mode."""
        if self.ImportAsColormapCheckBox.isChecked():
            return ["As is"] + COLORMAP_ASSIGNMENTS + ["User defined", "N.a."]
        if self.ImportAsSTmCheckBox.isChecked():
            return [
                "As is",
                STRUCTURAL_TOPOLOGY_FEATURE_COLUMN,
                STRUCTURAL_TOPOLOGY_UNIT_ROLE_COLUMN,
                STRUCTURAL_TOPOLOGY_POLARITY_COLUMN,
                "Domain",
                "User defined",
                "N.a.",
            ]
        return list(SPECIAL_ASSIGNMENTS)

    def _on_import_as_colormap_toggled(self, checked):
        """Switch between manual-table and colormap import modes."""
        if checked and self.ImportAsSTmCheckBox.isChecked():
            self.ImportAsSTmCheckBox.blockSignals(True)
            self.ImportAsSTmCheckBox.setChecked(False)
            self.ImportAsSTmCheckBox.blockSignals(False)
        self.ColormapModeComboBox.setEnabled(bool(checked))
        if self.input_data_df is None:
            return
        self._auto_assign_columns()
        self._assign_data_table()
        self._update_preview_model()

    def _on_import_as_stm_toggled(self, checked):
        """Switch between manual-table and STm import modes."""
        if checked and self.ImportAsColormapCheckBox.isChecked():
            self.ImportAsColormapCheckBox.blockSignals(True)
            self.ImportAsColormapCheckBox.setChecked(False)
            self.ImportAsColormapCheckBox.blockSignals(False)
        self.ColormapModeComboBox.setEnabled(self.ImportAsColormapCheckBox.isChecked())
        if self.input_data_df is None:
            return
        self._auto_assign_columns()
        self._assign_data_table()
        self._update_preview_model()

    def _on_colormap_mode_changed(self, _text):
        """Keep the dialog state up to date when the colormap mode changes."""
        if self.ImportAsColormapCheckBox.isChecked() and self.input_data_df is not None:
            self._update_preview_model()

    def _pick_preview_path(self):
        """Choose the first file used for preview."""
        return self.in_file_names[0] if self.in_file_names else ""

    def _load_initial_preview(self):
        """Load the first preview using auto-detected separator."""
        if not self.preview_path:
            return
        try:
            detected_sep = auto_sep(self.preview_path)
        except Exception:
            detected_sep = ","

        self.preview_stm_payload = _read_stm_export_payload(self.preview_path)
        if self.preview_stm_payload is not None and self.preview_stm_payload.get(
            "table_type"
        ) == STRUCTURAL_TOPOLOGY_TABLE_TYPE:
            self.ImportAsSTmCheckBox.setChecked(True)
            self.ImportAsColormapCheckBox.setChecked(False)

        detected_label = None
        for label, sep in self.sep_dict.items():
            if sep == detected_sep:
                detected_label = label
                break
        self.SeparatorcomboBox.setCurrentText(detected_label or detected_sep)
        self._set_default_import_range()
        self._refresh_preview()

    def _set_default_import_range(self):
        """Use the whole preview file as the default import interval."""
        if not self.preview_path:
            self.EndRowspinBox.setValue(self.EndRowspinBox.maximum())
            return

        try:
            line_count = _count_file_lines(self.preview_path)
        except OSError:
            self.EndRowspinBox.setValue(self.EndRowspinBox.maximum())
            return

        if line_count <= 0:
            self.EndRowspinBox.setValue(self.EndRowspinBox.maximum())
            return

        self.EndRowspinBox.setValue(max(line_count - 1, 1))

    def _current_separator(self):
        """Return the currently-selected separator."""
        return self.sep_dict.get(
            self.SeparatorcomboBox.currentText(),
            self.SeparatorcomboBox.currentText(),
        )

    def _read_preview_dataframe(self):
        """Read a preview dataframe from the current file/options."""
        if (
            self.preview_stm_payload is not None
            and self.preview_stm_payload.get("schema") == STM_JSON_SCHEMA
        ):
            return _stm_boundary_dataframe(self.preview_stm_payload)
        delimiter = self._current_separator()
        pandas_sep, engine = _resolve_pandas_separator(delimiter)
        has_header = self.HasHeaderCheckBox.isChecked()
        start_row = self.StartRowspinBox.value()
        end_row = self.EndRowspinBox.value()
        preview_nrows = max(min(end_row - start_row, 50), 1) if end_row > start_row else 50

        if has_header:
            skiprows = range(1, start_row + 1) if start_row > 0 else None
            input_df = pd_read_csv(
                self.preview_path,
                sep=pandas_sep,
                engine=engine,
                comment="#",
                header=0,
                skiprows=skiprows,
                nrows=preview_nrows,
                index_col=False,
                dtype=str,
                keep_default_na=False,
            )
        else:
            skiprows = start_row if start_row > 0 else None
            input_df = pd_read_csv(
                self.preview_path,
                sep=pandas_sep,
                engine=engine,
                comment="#",
                header=None,
                skiprows=skiprows,
                nrows=preview_nrows,
                index_col=False,
                dtype=str,
                keep_default_na=False,
            )
            input_df.columns = [f"field_{idx + 1}" for idx in range(input_df.shape[1])]

        if input_df.empty:
            raise ValueError("no tabular rows found with the current settings")

        return input_df

    def _refresh_preview(self):
        """Refresh preview/model/table assignment."""
        if not self.preview_path:
            self.AssignTable.setRowCount(0)
            self.dataView.setModel(None)
            return

        try:
            self.input_data_df = self._read_preview_dataframe()
        except Exception as exc:
            self.AssignTable.setRowCount(0)
            self.dataView.setModel(None)
            QMessageBox.warning(
                self,
                "Preview error",
                f"Could not preview the selected table file.\n\n{exc}",
            )
            return

        self._auto_assign_columns()
        self._assign_data_table()
        self._update_preview_model()

    def _auto_assign_columns(self):
        """Assign default mappings for the current import mode."""
        column_names = list(self.input_data_df.columns)

        if not self.ImportAsColormapCheckBox.isChecked() and not self.ImportAsSTmCheckBox.isChecked():
            self.rename_dict = {idx: "As is" for idx in range(len(column_names))}
            return

        if self.ImportAsColormapCheckBox.isChecked():
            target_assignments = COLORMAP_ASSIGNMENTS
        else:
            target_assignments = STRUCTURAL_TOPOLOGY_REQUIRED_COLUMNS

        self.rename_dict = {}
        remaining_targets = {
            target.casefold(): target for target in target_assignments
        }
        for idx, column_name in enumerate(column_names):
            column_name_txt = str(column_name)
            matched_target = remaining_targets.pop(column_name_txt.casefold(), None)
            if self.ImportAsSTmCheckBox.isChecked():
                if column_name_txt == "Domain":
                    self.rename_dict[idx] = "Domain_1"
                    continue
                if column_name_txt.startswith("Domain_"):
                    suffix = column_name_txt.split("_", 1)[1]
                    if suffix.isdigit() and int(suffix) > 0:
                        self.rename_dict[idx] = column_name_txt
                        continue
            self.rename_dict[idx] = matched_target if matched_target else (
                "As is" if self.ImportAsSTmCheckBox.isChecked() else "N.a."
            )

    def _assign_data_table(self):
        """Populate the assignment table."""
        column_names = list(self.input_data_df.columns)

        self._is_populating_table = True
        self.AssignTable.blockSignals(True)
        self.AssignTable.setRowCount(len(column_names))

        for row_idx, column_name in enumerate(column_names):
            col_item = QTableWidgetItem()
            col_item.setText(str(column_name))

            attr_combo = QComboBox(self)
            attr_combo.setObjectName(f"AttrcomboBox_{row_idx}")
            attr_combo.addItems(self._available_assignments())
            attr_combo.currentTextChanged.connect(
                lambda _text, idx=row_idx, combo=attr_combo: self._on_assignment_changed(
                    idx, combo
                )
            )

            custom_line = QLineEdit()
            custom_line.setObjectName(f"CustomFieldLine_{row_idx}")
            custom_line.setEnabled(False)
            custom_line.returnPressed.connect(
                lambda idx=row_idx: self._on_custom_name_changed(idx)
            )
            custom_line.editingFinished.connect(
                lambda idx=row_idx: self._on_custom_name_changed(idx)
            )

            self.AssignTable.setItem(row_idx, 0, col_item)
            self.AssignTable.setCellWidget(row_idx, 1, attr_combo)
            self.AssignTable.setCellWidget(row_idx, 2, custom_line)

            current_value = self.rename_dict.get(row_idx, "As is")
            if (
                self.ImportAsSTmCheckBox.isChecked()
                and str(current_value).startswith("Domain_")
            ):
                attr_combo.setCurrentText("Domain")
                custom_line.setEnabled(True)
                custom_line.setText(str(current_value).split("_", 1)[1])
            elif current_value in self._available_assignments():
                attr_combo.setCurrentText(current_value)
            else:
                attr_combo.setCurrentText("User defined")
                custom_line.setEnabled(True)
                custom_line.setText(str(current_value))

        self.AssignTable.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents
        )
        self.AssignTable.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeToContents
        )
        self.AssignTable.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.AssignTable.blockSignals(False)
        self._is_populating_table = False

    def _on_assignment_changed(self, row_idx, combo):
        """Handle combo-box updates for assignment rows."""
        if self._is_populating_table:
            return

        selected_value = combo.currentText()
        custom_line = self.AssignTable.cellWidget(row_idx, 2)
        source_column = str(self.input_data_df.columns[row_idx])

        if selected_value == "User defined":
            custom_line.setEnabled(True)
            if not custom_line.text().strip():
                custom_line.setText(source_column)
            self.rename_dict[row_idx] = custom_line.text().strip()
        elif selected_value == "Domain":
            custom_line.setEnabled(True)
            if not custom_line.text().strip():
                custom_line.setText("1")
            self.rename_dict[row_idx] = f"Domain_{custom_line.text().strip()}"
        else:
            custom_line.clear()
            custom_line.setEnabled(False)
            self.rename_dict[row_idx] = selected_value

        self._update_preview_model()

    def _on_custom_name_changed(self, row_idx):
        """Sync the custom field name back to the internal mapping."""
        if self._is_populating_table:
            return

        custom_line = self.AssignTable.cellWidget(row_idx, 2)
        combo = self.AssignTable.cellWidget(row_idx, 1)
        if combo.currentText() == "Domain":
            order_value = str(custom_line.text() or "").strip()
            try:
                order_number = int(order_value)
                if order_number <= 0:
                    raise ValueError()
            except ValueError:
                order_number = 1
            custom_line.setText(str(order_number))
            self.rename_dict[row_idx] = f"Domain_{order_number}"
            self._update_preview_model()
            return

        if combo.currentText() != "User defined":
            return

        source_column = str(self.input_data_df.columns[row_idx])
        field_name = _finalise_field_name(custom_line.text(), source_column)
        custom_line.setText(field_name)
        self.rename_dict[row_idx] = field_name
        self._update_preview_model()

    def _update_preview_model(self):
        """Update the preview model, highlighting imported columns."""
        selected_columns = []
        for row_idx in range(self.AssignTable.rowCount()):
            combo = self.AssignTable.cellWidget(row_idx, 1)
            if combo and combo.currentText() != "N.a.":
                selected_columns.append(row_idx)
        self.model = PCDataModel(self.input_data_df, selected_columns)
        self.dataView.setModel(self.model)

    def _collect_column_specs(self):
        """Return a list of selected column specs."""
        column_specs = []
        final_names = []

        for row_idx in range(self.AssignTable.rowCount()):
            combo = self.AssignTable.cellWidget(row_idx, 1)
            custom_line = self.AssignTable.cellWidget(row_idx, 2)
            source_name = str(self.input_data_df.columns[row_idx])
            selection = combo.currentText()

            if selection == "N.a.":
                continue

            if selection == "User defined":
                final_name = _finalise_field_name(
                    custom_line.text() if custom_line else "",
                    source_name,
                )
                if custom_line is not None:
                    custom_line.setText(final_name)
            elif selection == "Domain":
                order_value = _finalise_field_name(
                    custom_line.text() if custom_line else "",
                    "1",
                )
                try:
                    order_number = int(order_value)
                    if order_number <= 0:
                        raise ValueError()
                except ValueError:
                    raise ValueError("domain order must be a positive integer")
                final_name = f"Domain_{order_number}"
                if custom_line is not None:
                    custom_line.setText(str(order_number))
            elif selection == "As is":
                final_name = source_name
            else:
                final_name = selection

            if final_name in final_names:
                raise ValueError(f"duplicate mapped name '{final_name}'")

            final_names.append(final_name)
            column_specs.append(
                {
                    "source_index": row_idx,
                    "source_name": source_name,
                    "selection": selection,
                    "final_name": final_name,
                }
            )

        return column_specs

    def _validate_and_accept(self):
        """Validate the dialog and store the import configuration."""
        if not self.in_file_names:
            QMessageBox.warning(
                self,
                "Missing files",
                "Select at least one input file before importing.",
            )
            return

        try:
            column_specs = self._collect_column_specs()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid mapping", str(exc))
            return

        if not column_specs:
            QMessageBox.warning(
                self,
                "No fields selected",
                "Assign at least one field to import the table.",
            )
            return

        import_as_colormap = self.ImportAsColormapCheckBox.isChecked()
        import_as_stm = self.ImportAsSTmCheckBox.isChecked()
        if import_as_colormap:
            mapped_names = {spec["final_name"] for spec in column_specs}
            required_names = set(PropertiesCMaps.custom_colormap_columns)
            if mapped_names != required_names:
                QMessageBox.warning(
                    self,
                    "Invalid colormap mapping",
                    "A colormap import requires exactly these fields: "
                    "value, color_R, color_G, color_B.",
                )
                return
        if import_as_stm:
            mapped_names = {spec["final_name"] for spec in column_specs}
            required_names = set(STRUCTURAL_TOPOLOGY_REQUIRED_COLUMNS)
            if not required_names.issubset(mapped_names):
                QMessageBox.warning(
                    self,
                    "Invalid STm mapping",
                    "An STm import requires at least these fields: "
                    "Feature, Unit Role, Structural Polarity.",
                )
                return

        start_row = self.StartRowspinBox.value()
        end_row = self.EndRowspinBox.value()
        if end_row <= start_row:
            QMessageBox.warning(
                self,
                "Invalid row interval",
                "End row must be greater than start row.",
            )
            return

        self.result = {
            "in_file_names": list(self.in_file_names),
            "delimiter": self._current_separator(),
            "has_header": self.HasHeaderCheckBox.isChecked(),
            "start_row": start_row,
            "end_row": end_row,
            "column_specs": column_specs,
            "import_as_colormap": import_as_colormap,
            "import_as_stm": import_as_stm,
            "colormap_mode": (
                "discrete"
                if self.ColormapModeComboBox.currentText() == "Exact intervals"
                else "continuous"
            ),
        }

        self.close()
        self.loop.quit()

    def reject(self):
        """Reject the dialog."""
        self.result = None
        self.close()
        self.loop.quit()

    def exec(self):
        """Execute the dialog and return the resulting configuration."""
        self.show()
        self.loop.exec_()
        return self.result

    def closeEvent(self, event):
        """Ensure the custom loop is stopped if the window is closed directly."""
        if self.loop.isRunning():
            self.loop.quit()
        event.accept()


def _read_table_dataframe(file_path, import_config):
    """Read a mapped text table according to the dialog configuration."""
    stm_payload = _read_stm_export_payload(file_path)
    if stm_payload is not None and stm_payload.get("schema") == STM_JSON_SCHEMA:
        return _stm_boundary_dataframe(stm_payload)
    column_specs = import_config["column_specs"]
    usecols = [spec["source_index"] for spec in column_specs]
    source_names = [spec["source_name"] for spec in column_specs]
    rename_map = {spec["source_name"]: spec["final_name"] for spec in column_specs}

    delimiter = import_config["delimiter"]
    pandas_sep, engine = _resolve_pandas_separator(delimiter)
    has_header = import_config["has_header"]
    start_row = import_config["start_row"]
    end_row = import_config["end_row"]
    nrows = end_row - start_row

    if has_header:
        skiprows = range(1, start_row + 1) if start_row > 0 else None
        input_df = pd_read_csv(
            file_path,
            sep=pandas_sep,
            engine=engine,
            comment="#",
            header=0,
            skiprows=skiprows,
            nrows=nrows,
            index_col=False,
            usecols=usecols,
            dtype=str,
            keep_default_na=False,
        )
    else:
        skiprows = start_row if start_row > 0 else None
        input_df = pd_read_csv(
            file_path,
            sep=pandas_sep,
            engine=engine,
            comment="#",
            header=None,
            skiprows=skiprows,
            nrows=nrows,
            index_col=False,
            usecols=usecols,
            names=source_names,
            dtype=str,
            keep_default_na=False,
        )

    input_df.rename(columns=rename_map, inplace=True)
    return input_df


def _normalise_stm_dataframe(input_df):
    """Ensure imported STm tables always expose the expected core columns."""
    def domain_sort_key(column_name):
        text = str(column_name)
        if text == "Domain":
            return 1
        if text.startswith("Domain_"):
            try:
                return int(text.split("_", 1)[1])
            except ValueError:
                return 9999
        return 9999

    output_df = input_df.copy()
    if "Domain" in output_df.columns and "Domain_1" not in output_df.columns:
        output_df.rename(columns={"Domain": "Domain_1"}, inplace=True)
    for required_column in STRUCTURAL_TOPOLOGY_REQUIRED_COLUMNS:
        if required_column not in output_df.columns:
            output_df[required_column] = ""
    for row_label in output_df.index.tolist():
        unit_role = _normalise_stm_unit_role(
            output_df.at[row_label, STRUCTURAL_TOPOLOGY_UNIT_ROLE_COLUMN]
        )
        output_df.at[row_label, STRUCTURAL_TOPOLOGY_UNIT_ROLE_COLUMN] = unit_role
    if not any(str(column).startswith("Domain") for column in output_df.columns):
        output_df["Domain_1"] = ""

    ordered_columns = [
        column_name
        for column_name in [
            STRUCTURAL_TOPOLOGY_FEATURE_COLUMN,
            STRUCTURAL_TOPOLOGY_UNIT_ROLE_COLUMN,
            STRUCTURAL_TOPOLOGY_POLARITY_COLUMN,
        ]
        if column_name in output_df.columns
    ]
    ordered_columns.extend(
        sorted(
            [
                column_name
                for column_name in output_df.columns
                if str(column_name).startswith("Domain")
                and column_name not in ordered_columns
            ],
            key=domain_sort_key,
        )
    )
    ordered_columns.extend(
        [
            column_name
            for column_name in output_df.columns
            if column_name not in ordered_columns
        ]
    )
    return output_df[ordered_columns]


def import_tables(self=None, in_file_names=None):
    """Import one or more text tables into project custom tables."""
    if self is None:
        return

    selected_files = list(in_file_names or [])
    if not selected_files:
        selected_files = open_files_dialog(
            parent=self,
            caption="Import table(s) from file(s)",
            filter=TEXT_TABLE_FILTER,
        )
        if not selected_files:
            return

    dialog = TableImportDialog(parent=self, in_file_names=selected_files)
    import_config = dialog.exec()
    if import_config is None:
        self.print_terminal("Table import cancelled by user.")
        return

    imported_count = 0
    failed_files = []

    for in_file_name in import_config.get("in_file_names", []):
        try:
            stm_payload = _read_stm_export_payload(in_file_name)
            import_as_colormap = bool(import_config.get("import_as_colormap", False))
            import_as_stm = bool(import_config.get("import_as_stm", False))
            stm_options = {}
            if stm_payload is not None and stm_payload.get("table_type") == STRUCTURAL_TOPOLOGY_TABLE_TYPE:
                import_as_stm = True
                import_as_colormap = False
                stm_options = dict(stm_payload.get("options", {}))
            imported_df = _read_table_dataframe(
                file_path=in_file_name,
                import_config=import_config,
            )
            base_name = os_path.splitext(os_path.basename(in_file_name))[0]
            table_name = _unique_table_name(
                existing_names=set(self.custom_tables.keys()),
                base_name=base_name,
            )
            if import_as_stm:
                imported_df = _normalise_stm_dataframe(imported_df)
            self.custom_tables[table_name] = imported_df
            if import_as_colormap:
                self.custom_table_types[table_name] = (
                    PropertiesCMaps.custom_colormap_table_type
                )
                self.custom_table_options[table_name] = {
                    "mode": import_config.get("colormap_mode", "continuous")
                }
            elif import_as_stm:
                self.custom_table_types[table_name] = STRUCTURAL_TOPOLOGY_TABLE_TYPE
                self.custom_table_options[table_name] = stm_options
            else:
                self.custom_table_types[table_name] = "manual"
                self.custom_table_options[table_name] = {}
            imported_count += 1
        except Exception as exc:
            failed_files.append((os_path.basename(in_file_name), str(exc)))

    if hasattr(self, "refresh_table_views"):
        self.refresh_table_views()
    if hasattr(self, "sync_structural_topology_tables_from_legend"):
        self.sync_structural_topology_tables_from_legend()
    if hasattr(self, "refresh_custom_colormaps"):
        self.refresh_custom_colormaps()

    if imported_count:
        self.print_terminal(f"Imported {imported_count} table(s).")
    for file_name, reason in failed_files:
        self.print_terminal(f"Failed to import {file_name}: {reason}")
