"""table2data.py
Generic importer for custom editable project tables."""

from os import path as os_path

from pandas import read_csv as pd_read_csv

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
from pzero.properties_manager import PropertiesCMaps
from pzero.ui.import_window_ui import Ui_ImportOptionsWindow


TEXT_TABLE_FILTER = (
    "Supported table files (*.csv *.dat *.txt *.tsv *.asc *.xyz);;"
    "CSV files (*.csv);;"
    "Delimited text files (*.dat *.txt *.tsv *.asc *.xyz)"
)
SPECIAL_ASSIGNMENTS = ["As is", "User defined", "N.a."]
COLORMAP_ASSIGNMENTS = ["value", "color_R", "color_G", "color_B"]


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

        self.ColormapModeComboBox = QComboBox(self.OptionsFrame)
        self.ColormapModeComboBox.addItems(["Continuous", "Exact intervals"])
        self.ColormapModeComboBox.setEnabled(False)
        self.formLayout.setWidget(
            5, QFormLayout.ItemRole.LabelRole, QLabel("Colormap mode")
        )
        self.formLayout.setWidget(
            5, QFormLayout.ItemRole.FieldRole, self.ColormapModeComboBox
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
        return list(SPECIAL_ASSIGNMENTS)

    def _on_import_as_colormap_toggled(self, checked):
        """Switch between manual-table and colormap import modes."""
        self.ColormapModeComboBox.setEnabled(bool(checked))
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

        if not self.ImportAsColormapCheckBox.isChecked():
            self.rename_dict = {idx: "As is" for idx in range(len(column_names))}
            return

        self.rename_dict = {}
        remaining_targets = {target.casefold(): target for target in COLORMAP_ASSIGNMENTS}
        for idx, column_name in enumerate(column_names):
            matched_target = remaining_targets.pop(str(column_name).casefold(), None)
            self.rename_dict[idx] = matched_target if matched_target else "N.a."

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
            if current_value in self._available_assignments():
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
            else:
                final_name = source_name

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
            imported_df = _read_table_dataframe(
                file_path=in_file_name,
                import_config=import_config,
            )
            base_name = os_path.splitext(os_path.basename(in_file_name))[0]
            table_name = _unique_table_name(
                existing_names=set(self.custom_tables.keys()),
                base_name=base_name,
            )
            self.custom_tables[table_name] = imported_df
            if import_config.get("import_as_colormap", False):
                self.custom_table_types[table_name] = (
                    PropertiesCMaps.custom_colormap_table_type
                )
                self.custom_table_options[table_name] = {
                    "mode": import_config.get("colormap_mode", "continuous")
                }
            else:
                self.custom_table_types[table_name] = "manual"
                self.custom_table_options[table_name] = {}
            imported_count += 1
        except Exception as exc:
            failed_files.append((os_path.basename(in_file_name), str(exc)))

    if hasattr(self, "refresh_table_views"):
        self.refresh_table_views()
    if hasattr(self, "refresh_custom_colormaps"):
        self.refresh_custom_colormaps()

    if imported_count:
        self.print_terminal(f"Imported {imported_count} table(s).")
    for file_name, reason in failed_files:
        self.print_terminal(f"Failed to import {file_name}: {reason}")
