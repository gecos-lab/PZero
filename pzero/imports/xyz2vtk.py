"""xyz2vtk.py
PZero generic tabular XYZ importer."""

from copy import deepcopy
from os import path as os_path
from uuid import uuid4

from PySide6.QtCore import QEventLoop
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QTableWidgetItem,
)
from numpy import array as np_array
from numpy import column_stack as np_column_stack
from numpy import where as np_where
from numpy import zeros as np_zeros
from pandas import read_csv as pd_read_csv
from pandas import to_numeric as pd_to_numeric
from pyvista import read as pv_read

from pzero.entities_factory import Attitude, VertexSet
from pzero.helpers.helper_dialogs import PCDataModel, open_files_dialog
from pzero.helpers.helper_functions import auto_sep
from pzero.imports.pc2vtk import COORDINATE_ALIASES, _sanitize_column_name
from pzero.imports.shp2vtk import (
    _get_point_group_columns,
    _get_valid_roles_for_collection,
    _validate_and_fix_roles,
)
from pzero.orientation_analysis import dip_directions2normals
from pzero.ui.import_window_ui import Ui_ImportOptionsWindow


TEXT_EXTENSIONS = {".txt", ".csv", ".xyz", ".asc", ".dat"}
VTK_EXTENSIONS = {".vtu", ".vtk", ".vtp"}
VALID_PROPERTY_COMPONENTS = {1, 2, 3, 4, 6, 9}
DEFAULT_SCENARIO = "undef"
DEFAULT_FEATURE = "undef"
FILE_DIALOG_FILTER = (
    "Supported XYZ files (*.csv *.dat *.txt *.xyz *.asc *.vtu *.vtk *.vtp);;"
    "Text files (*.csv *.dat *.txt *.xyz *.asc);;"
    "VTK files (*.vtu *.vtk *.vtp)"
)

SPECIAL_ASSIGNMENTS = [
    "As is",
    "X",
    "Y",
    "Z",
    "feature",
    "role",
    "name",
    "scenario",
    "dip",
    "dip_dir",
    "dir",
    "Nx",
    "Ny",
    "Nz",
    "User defined",
    "N.a.",
]
SPECIAL_POINT_COLUMNS = {
    "X",
    "Y",
    "Z",
    "feature",
    "role",
    "name",
    "scenario",
    "dip",
    "dip_dir",
    "dir",
    "Nx",
    "Ny",
    "Nz",
}
UNIQUE_ASSIGNMENTS = SPECIAL_POINT_COLUMNS.copy()
FIELD_ALIASES = {
    "X": ("x",) + COORDINATE_ALIASES["X"],
    "Y": ("y",) + COORDINATE_ALIASES["Y"],
    "Z": ("z",) + COORDINATE_ALIASES["Z"],
    "feature": ("feature", "formation", "unit"),
    "role": ("role",),
    "name": ("name", "label"),
    "scenario": ("scenario",),
    "dip": ("dip", "inclination"),
    "dip_dir": ("dipdir", "dipdirection", "dip_direction", "dip direction"),
    "dir": ("dir",),
    "Nx": ("nx", "normalx", "normal_x", "xnormal"),
    "Ny": ("ny", "normaly", "normal_y", "ynormal"),
    "Nz": ("nz", "normalz", "normal_z", "znormal"),
}


def _coerce_points_to_3d(points_matrix):
    """Return an n x 3 float array."""
    points_array = np_array(points_matrix, dtype=float)
    if points_array.ndim == 1:
        points_array = points_array.reshape(1, -1)
    if points_array.shape[1] == 2:
        out = np_zeros((points_array.shape[0], 3))
        out[:, :2] = points_array
        return out
    return points_array[:, :3]


def _extract_numeric_properties(input_df, excluded_columns=None):
    """Keep numeric properties only."""
    excluded_columns = set(excluded_columns or [])
    properties = {}
    for column_name in input_df.columns:
        if column_name in excluded_columns:
            continue
        numeric_values = pd_to_numeric(input_df[column_name], errors="coerce")
        if numeric_values.notna().all():
            properties[column_name] = numeric_values.to_numpy()
    return properties


def _extract_non_numeric_property_names(input_df, excluded_columns=None):
    """Return non-numeric property names that were skipped."""
    excluded_columns = set(excluded_columns or [])
    skipped_names = []
    for column_name in input_df.columns:
        if column_name in excluded_columns:
            continue
        numeric_values = pd_to_numeric(input_df[column_name], errors="coerce")
        if not numeric_values.notna().all():
            skipped_names.append(column_name)
    return skipped_names


def _vtk_array_components(values):
    """Return the VTK-compatible component count for a property array."""
    shape = getattr(values, "shape", ())
    if len(shape) > 2:
        return None
    if len(shape) <= 1:
        return 1
    return shape[1]


def _extract_from_vtk(file_path):
    """Read points and supported point properties from a VTK/PyVista-readable file."""
    mesh = pv_read(file_path)
    if not hasattr(mesh, "points") or mesh.points is None or len(mesh.points) == 0:
        raise ValueError("no points found in VTK dataset")

    points = _coerce_points_to_3d(mesh.points)
    properties = {}
    for property_name in mesh.point_data.keys():
        values = np_array(mesh.point_data[property_name])
        if values.size == 0:
            continue
        if values.dtype.kind not in "biuf":
            continue
        components = _vtk_array_components(values)
        if components not in VALID_PROPERTY_COMPONENTS:
            continue
        properties[property_name] = values
    return points, properties


def _build_vertex_set(points, properties=None, topology_cls=VertexSet):
    """Create a point-based VTK object from points and optional properties."""
    vtk_obj = topology_cls()
    vtk_obj.points = _coerce_points_to_3d(points)
    vtk_obj.auto_cells()

    for property_name, values in (properties or {}).items():
        vtk_obj.set_point_data(data_key=property_name, attribute_matrix=values)

    return vtk_obj


def _resolve_collection(self, collection_name):
    """Map UI label to the destination collection."""
    collection_map = {
        "Geology": self.geol_coll,
        "Fluid contacts": self.fluid_coll,
        "Background data": self.backgrnd_coll,
    }
    return collection_map.get(collection_name)


def _build_entity_dict(collection, vtk_obj, file_path):
    """Build a default entity dictionary for VTK-based imports."""
    basename = os_path.basename(file_path)
    stem = os_path.splitext(basename)[0]
    entity_dict = deepcopy(collection.entity_dict)
    entity_dict["uid"] = str(uuid4())
    entity_dict["name"] = basename
    entity_dict["topology"] = "VertexSet"
    entity_dict["vtk_obj"] = vtk_obj
    entity_dict["properties_names"] = list(vtk_obj.point_data_keys)
    entity_dict["properties_components"] = [
        vtk_obj.get_point_data_shape(property_name)[1]
        for property_name in entity_dict["properties_names"]
    ]
    if "feature" in entity_dict:
        entity_dict["feature"] = stem
    if "role" in entity_dict:
        entity_dict["role"] = "undef"
    if "scenario" in entity_dict:
        entity_dict["scenario"] = DEFAULT_SCENARIO
    return entity_dict


def _resolve_pandas_separator(delimiter):
    """Return the separator/engine pair to use with pandas."""
    if delimiter == " ":
        return r"\s+", "python"
    return delimiter, "python"


def _normalise_text_value(value, fallback="undef"):
    """Return a clean string for entity-level metadata."""
    if value is None:
        return fallback
    text_value = str(value).strip()
    return text_value if text_value else fallback


def _finalise_user_property_name(raw_name, fallback_name):
    """Normalise a user-defined property name."""
    raw_name = str(raw_name or "").strip()
    if not raw_name:
        raw_name = fallback_name
    return raw_name if raw_name.startswith("user_") else f"user_{raw_name}"


def _first_match(columns, aliases, used_columns):
    """Return the first column that matches one of the aliases."""
    for alias in aliases:
        sanitized_alias = _sanitize_column_name(alias)
        for column_name in columns:
            if column_name in used_columns:
                continue
            if _sanitize_column_name(column_name) == sanitized_alias:
                return column_name
    return None


def _build_default_entity_name(file_path, feature_value, fallback_name=None):
    """Return a useful entity name when no explicit name column is assigned."""
    clean_name = _normalise_text_value(fallback_name, fallback="")
    if clean_name and clean_name != "undef":
        return clean_name
    basename = os_path.basename(file_path)
    stem = os_path.splitext(basename)[0]
    clean_feature = _normalise_text_value(feature_value, fallback="")
    if clean_feature and clean_feature != "undef":
        return f"{stem}_{clean_feature}"
    return basename


class XYZImportDialog(QMainWindow, Ui_ImportOptionsWindow):
    """Dialog used to preview tabular files and assign XYZ/entity attributes."""

    sep_dict = {"<space>": " ", "<comma>": ",", "<semi-col>": ";", "<tab>": "\t"}

    def __init__(
        self,
        parent=None,
        in_file_names=None,
        collection_name="Geology",
        *args,
        **kwargs,
    ):
        self.loop = QEventLoop()
        super(XYZImportDialog, self).__init__(parent, *args, **kwargs)
        self.setupUi(self)

        self.parent = parent
        self.in_file_names = list(in_file_names or [])
        self.collection_name = collection_name
        self.valid_roles = _get_valid_roles_for_collection(collection_name)
        self.result = None
        self.input_data_df = None
        self.rename_dict = {}
        self._is_populating_table = False
        self.preview_path = self._pick_preview_path()

        self.setWindowTitle(f"Import tabular XYZ data - {collection_name}")
        self._setup_window()
        self._connect_signals()
        self._load_initial_preview()

    def _setup_window(self):
        """Configure static UI elements."""
        self.PathlineEdit.setReadOnly(True)
        self.PathtoolButton.setEnabled(True)
        self.AssignTable.setColumnCount(3)
        self.AssignTable.setHorizontalHeaderLabels(
            ["Column name", "Assigned attribute", "Custom property name"]
        )
        self.AssignTable.setColumnWidth(1, 200)
        self.AssignTable.setColumnWidth(2, 240)

        self._update_selected_files_text()

        self.HasHeaderCheckBox = QCheckBox(self.OptionsFrame)
        self.HasHeaderCheckBox.setText("First row contains headers")
        self.HasHeaderCheckBox.setChecked(True)

        self.FeatureLineEdit = QLineEdit(self.OptionsFrame)
        self.FeatureLineEdit.setPlaceholderText("Required if no feature column is mapped")
        self.FeatureLineEdit.setText(DEFAULT_FEATURE)

        self.RoleComboBox = QComboBox(self.OptionsFrame)
        self.RoleComboBox.addItems(self.valid_roles)
        self.RoleComboBox.setCurrentText("undef")

        self.NameLineEdit = QLineEdit(self.OptionsFrame)
        self.NameLineEdit.setPlaceholderText("Optional fixed name (blank = derive from file)")

        self.ScenarioLineEdit = QLineEdit(self.OptionsFrame)
        self.ScenarioLineEdit.setPlaceholderText("Optional fixed scenario")
        self.ScenarioLineEdit.setText(DEFAULT_SCENARIO)

        self.formLayout.setWidget(3, QFormLayout.ItemRole.LabelRole, QLabel("Headers"))
        self.formLayout.setWidget(3, QFormLayout.ItemRole.FieldRole, self.HasHeaderCheckBox)
        self.formLayout.setWidget(4, QFormLayout.ItemRole.LabelRole, QLabel("Feature"))
        self.formLayout.setWidget(4, QFormLayout.ItemRole.FieldRole, self.FeatureLineEdit)
        self.formLayout.setWidget(5, QFormLayout.ItemRole.LabelRole, QLabel("Role"))
        self.formLayout.setWidget(5, QFormLayout.ItemRole.FieldRole, self.RoleComboBox)
        self.formLayout.setWidget(6, QFormLayout.ItemRole.LabelRole, QLabel("Name"))
        self.formLayout.setWidget(6, QFormLayout.ItemRole.FieldRole, self.NameLineEdit)
        self.formLayout.setWidget(7, QFormLayout.ItemRole.LabelRole, QLabel("Scenario"))
        self.formLayout.setWidget(7, QFormLayout.ItemRole.FieldRole, self.ScenarioLineEdit)

    def _connect_signals(self):
        """Connect UI signals."""
        self.PathtoolButton.clicked.connect(self._select_input_files)
        self.StartRowspinBox.valueChanged.connect(self._refresh_preview)
        self.EndRowspinBox.valueChanged.connect(self._refresh_preview)
        self.SeparatorcomboBox.currentTextChanged.connect(self._refresh_preview)
        self.HasHeaderCheckBox.toggled.connect(self._refresh_preview)
        self.PreviewButton.clicked.connect(self._refresh_preview)
        self.ConfirmBox.accepted.connect(self._validate_and_accept)
        self.ConfirmBox.rejected.connect(self.reject)

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
        if detected_label:
            self.SeparatorcomboBox.setCurrentText(detected_label)
        else:
            self.SeparatorcomboBox.setCurrentText(detected_sep)

        self._refresh_preview()

    def _pick_preview_path(self):
        """Choose the text file to preview from the selected input files."""
        for file_path in self.in_file_names:
            _, extension = os_path.splitext(file_path)
            if extension.lower() in TEXT_EXTENSIONS:
                return file_path
        return ""

    def _update_selected_files_text(self):
        """Show selected files summary in the path line edit."""
        if not self.in_file_names:
            self.PathlineEdit.setText("No file selected")
            return
        if self.preview_path and len(self.in_file_names) > 1:
            self.PathlineEdit.setText(
                f"Previewing {os_path.basename(self.preview_path)} "
                f"({len(self.in_file_names)} files selected)"
            )
            return
        if len(self.in_file_names) == 1:
            self.PathlineEdit.setText(self.in_file_names[0])
        else:
            self.PathlineEdit.setText(f"{len(self.in_file_names)} files selected")

    def _select_input_files(self):
        """Open the file picker from inside the import dialog."""
        selected_files = open_files_dialog(
            parent=self,
            caption="Import XYZ points from file(s)",
            filter=FILE_DIALOG_FILTER,
        )
        if not selected_files:
            return

        self.in_file_names = list(selected_files)
        self.preview_path = self._pick_preview_path()
        self._update_selected_files_text()

        if not self.preview_path:
            self.AssignTable.setRowCount(0)
            self.dataView.setModel(None)
            return

        self._load_initial_preview()

    def _current_separator(self):
        """Return the currently-selected separator."""
        return self.sep_dict.get(
            self.SeparatorcomboBox.currentText(),
            self.SeparatorcomboBox.currentText(),
        )

    def _read_preview_dataframe(self):
        """Read a preview DataFrame from the current file/options."""
        delimiter = self._current_separator()
        pandas_sep, engine = _resolve_pandas_separator(delimiter)
        has_header = self.HasHeaderCheckBox.isChecked()
        start_row = self.StartRowspinBox.value()
        end_row = self.EndRowspinBox.value()
        preview_nrows = None

        if end_row > start_row:
            preview_nrows = max(min(end_row - start_row, 50), 1)
        else:
            preview_nrows = 50

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
            )
            input_df.columns = [f"col_{idx + 1}" for idx in range(input_df.shape[1])]

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
                f"Could not preview the selected tabular file.\n\n{exc}",
            )
            return

        self._auto_assign_columns()
        self._assign_data_table()
        self._update_preview_model()

    def _auto_assign_columns(self):
        """Auto-assign well-known attributes using exact sanitised matching."""
        column_names = list(self.input_data_df.columns)
        used_columns = set()
        auto_map = {idx: "As is" for idx in range(len(column_names))}

        for field_name in (
            "X",
            "Y",
            "Z",
            "feature",
            "role",
            "name",
            "scenario",
            "dip",
            "dip_dir",
            "dir",
            "Nx",
            "Ny",
            "Nz",
        ):
            match = _first_match(column_names, FIELD_ALIASES[field_name], used_columns)
            if match is None:
                continue
            match_idx = column_names.index(match)
            auto_map[match_idx] = field_name
            used_columns.add(match)

        self.rename_dict = auto_map

    def _assign_data_table(self):
        """Populate the assignment table."""
        df = self.input_data_df
        column_names = list(df.columns)

        self._is_populating_table = True
        self.AssignTable.blockSignals(True)
        self.AssignTable.setRowCount(len(column_names))

        for row_idx, column_name in enumerate(column_names):
            col_item = QTableWidgetItem()
            col_item.setText(str(column_name))

            attr_combo = QComboBox(self)
            attr_combo.setObjectName(f"AttrcomboBox_{row_idx}")
            attr_combo.addItems(SPECIAL_ASSIGNMENTS)
            attr_combo.currentTextChanged.connect(
                lambda _text, idx=row_idx, combo=attr_combo: self._on_assignment_changed(idx, combo)
            )

            custom_line = QLineEdit()
            custom_line.setObjectName(f"CustomPropertyLine_{row_idx}")
            custom_line.setEnabled(False)
            custom_line.returnPressed.connect(lambda idx=row_idx: self._on_custom_name_changed(idx))
            custom_line.editingFinished.connect(lambda idx=row_idx: self._on_custom_name_changed(idx))

            self.AssignTable.setItem(row_idx, 0, col_item)
            self.AssignTable.setCellWidget(row_idx, 1, attr_combo)
            self.AssignTable.setCellWidget(row_idx, 2, custom_line)

            current_value = self.rename_dict.get(row_idx, "As is")
            if current_value in SPECIAL_ASSIGNMENTS:
                attr_combo.setCurrentText(current_value)
            elif isinstance(current_value, str) and current_value.startswith("user_"):
                attr_combo.setCurrentText("User defined")
                custom_line.setEnabled(True)
                custom_line.setText(current_value)
            else:
                attr_combo.setCurrentText("As is")

        self.AssignTable.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.AssignTable.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.AssignTable.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.AssignTable.blockSignals(False)
        self._is_populating_table = False

    def _on_assignment_changed(self, row_idx, combo):
        """Handle combo-box updates for assignment rows."""
        if self._is_populating_table:
            return
        selected_value = combo.currentText()
        if selected_value in UNIQUE_ASSIGNMENTS:
            for other_row in range(self.AssignTable.rowCount()):
                if other_row == row_idx:
                    continue
                other_combo = self.AssignTable.cellWidget(other_row, 1)
                if other_combo and other_combo.currentText() == selected_value:
                    other_combo.setCurrentText("As is")

        if selected_value == "dir":
            for other_row in range(self.AssignTable.rowCount()):
                if other_row == row_idx:
                    continue
                other_combo = self.AssignTable.cellWidget(other_row, 1)
                if other_combo and other_combo.currentText() == "dip_dir":
                    other_combo.setCurrentText("As is")
        elif selected_value == "dip_dir":
            for other_row in range(self.AssignTable.rowCount()):
                if other_row == row_idx:
                    continue
                other_combo = self.AssignTable.cellWidget(other_row, 1)
                if other_combo and other_combo.currentText() == "dir":
                    other_combo.setCurrentText("As is")

        custom_line = self.AssignTable.cellWidget(row_idx, 2)
        source_column = str(self.input_data_df.columns[row_idx])

        if selected_value == "User defined":
            custom_line.setEnabled(True)
            if not custom_line.text().strip():
                custom_line.setText(_finalise_user_property_name("", source_column))
            self.rename_dict[row_idx] = custom_line.text().strip()
        else:
            custom_line.setEnabled(False)
            if selected_value == "As is":
                self.rename_dict[row_idx] = source_column
            else:
                self.rename_dict[row_idx] = selected_value

        self._update_preview_model()

    def _on_custom_name_changed(self, row_idx):
        """Sync the custom property name back to the internal mapping."""
        if self._is_populating_table:
            return
        custom_line = self.AssignTable.cellWidget(row_idx, 2)
        combo = self.AssignTable.cellWidget(row_idx, 1)
        if combo.currentText() != "User defined":
            return
        source_column = str(self.input_data_df.columns[row_idx])
        property_name = _finalise_user_property_name(custom_line.text(), source_column)
        custom_line.setText(property_name)
        self.rename_dict[row_idx] = property_name
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
                final_name = _finalise_user_property_name(
                    custom_line.text() if custom_line else "",
                    source_name,
                )
                if custom_line is not None:
                    custom_line.setText(final_name)
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

        text_files = []
        for in_file_name in self.in_file_names:
            _, extension = os_path.splitext(in_file_name)
            if extension.lower() in TEXT_EXTENSIONS:
                text_files.append(in_file_name)

        if not text_files:
            self.result = {
                "in_file_names": list(self.in_file_names),
                "collection_name": self.collection_name,
                "delimiter": self._current_separator(),
                "has_header": self.HasHeaderCheckBox.isChecked(),
                "start_row": self.StartRowspinBox.value(),
                "end_row": self.EndRowspinBox.value(),
                "column_specs": [],
                "feature_value": _normalise_text_value(self.FeatureLineEdit.text(), DEFAULT_FEATURE),
                "role_value": _normalise_text_value(self.RoleComboBox.currentText(), "undef"),
                "name_value": str(self.NameLineEdit.text()).strip(),
                "scenario_value": _normalise_text_value(self.ScenarioLineEdit.text(), DEFAULT_SCENARIO),
            }
            self.close()
            self.loop.quit()
            return

        try:
            column_specs = self._collect_column_specs()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid mapping", str(exc))
            return

        mapped_names = {spec["final_name"] for spec in column_specs}

        if "X" not in mapped_names or "Y" not in mapped_names:
            QMessageBox.warning(
                self,
                "Missing coordinates",
                "X and Y must be assigned to import tabular point data.",
            )
            return

        normal_components = [name for name in ("Nx", "Ny", "Nz") if name in mapped_names]
        if normal_components and len(normal_components) != 3:
            QMessageBox.warning(
                self,
                "Incomplete normals",
                "Normals require all three components: Nx, Ny and Nz.",
            )
            return

        has_dip = "dip" in mapped_names
        has_dip_dir = "dip_dir" in mapped_names
        has_dir = "dir" in mapped_names
        if has_dip != (has_dip_dir or has_dir):
            QMessageBox.warning(
                self,
                "Incomplete orientation",
                "Dip requires either dip_dir or dir, and vice versa.",
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

        feature_value = _normalise_text_value(self.FeatureLineEdit.text(), DEFAULT_FEATURE)
        role_value = _normalise_text_value(self.RoleComboBox.currentText(), "undef")
        name_value = str(self.NameLineEdit.text()).strip()
        scenario_value = _normalise_text_value(
            self.ScenarioLineEdit.text(),
            DEFAULT_SCENARIO,
        )

        self.result = {
            "in_file_names": list(self.in_file_names),
            "collection_name": self.collection_name,
            "delimiter": self._current_separator(),
            "has_header": self.HasHeaderCheckBox.isChecked(),
            "start_row": start_row,
            "end_row": end_row,
            "column_specs": column_specs,
            "feature_value": feature_value,
            "role_value": role_value,
            "name_value": name_value,
            "scenario_value": scenario_value,
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


def _read_tabular_dataframe(file_path, import_config):
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
            usecols=usecols,
            skiprows=skiprows,
            nrows=nrows,
            index_col=False,
        )
    else:
        skiprows = start_row if start_row > 0 else None
        input_df = pd_read_csv(
            file_path,
            sep=pandas_sep,
            engine=engine,
            comment="#",
            header=None,
            usecols=usecols,
            skiprows=skiprows,
            nrows=nrows,
            index_col=False,
        )

    if input_df.empty:
        raise ValueError("no rows found with the current import settings")

    input_df.columns = source_names
    input_df.rename(columns=rename_map, inplace=True)

    for numeric_column in ("X", "Y", "Z", "dip", "dip_dir", "dir", "Nx", "Ny", "Nz"):
        if numeric_column in input_df.columns:
            input_df[numeric_column] = pd_to_numeric(input_df[numeric_column], errors="raise")

    if "Z" not in input_df.columns:
        input_df["Z"] = 0.0

    if "feature" not in input_df.columns:
        input_df["feature"] = import_config["feature_value"]
    if "role" not in input_df.columns:
        input_df["role"] = import_config["role_value"]
    if "scenario" not in input_df.columns:
        input_df["scenario"] = import_config["scenario_value"]
    fixed_name = import_config["name_value"]
    if "name" not in input_df.columns and fixed_name:
        input_df["name"] = fixed_name

    for text_column, fallback in (
        ("feature", DEFAULT_FEATURE),
        ("role", "undef"),
        ("scenario", DEFAULT_SCENARIO),
        ("name", "undef"),
    ):
        if text_column in input_df.columns:
            input_df[text_column] = input_df[text_column].apply(
                lambda value, fb=fallback: _normalise_text_value(value, fb)
            )

    return input_df


def _build_text_entity_dict(collection, vtk_obj, file_path, metadata):
    """Build the collection entity dictionary for tabular imports."""
    entity_dict = deepcopy(collection.entity_dict)
    entity_dict["uid"] = str(uuid4())
    entity_dict["name"] = _build_default_entity_name(
        file_path=file_path,
        feature_value=metadata.get("feature", DEFAULT_FEATURE),
        fallback_name=metadata.get("name"),
    )
    entity_dict["scenario"] = metadata.get("scenario", DEFAULT_SCENARIO)
    entity_dict["topology"] = "VertexSet"
    entity_dict["vtk_obj"] = vtk_obj
    entity_dict["role"] = metadata.get("role", "undef")
    entity_dict["feature"] = metadata.get("feature", DEFAULT_FEATURE)
    entity_dict["properties_names"] = list(vtk_obj.point_data_keys)
    entity_dict["properties_components"] = [
        vtk_obj.get_point_data_shape(property_name)[1]
        for property_name in entity_dict["properties_names"]
    ]
    return entity_dict


def _build_tabular_vtk_object(group_df):
    """Create a VertexSet/Attitude object from a grouped DataFrame."""
    has_direct_normals = all(axis in group_df.columns for axis in ("Nx", "Ny", "Nz"))
    has_dip = "dip" in group_df.columns
    has_dip_dir = "dip_dir" in group_df.columns
    has_dir = "dir" in group_df.columns
    needs_attitude = has_direct_normals or has_dip or has_dip_dir or has_dir
    vtk_class = Attitude if needs_attitude else VertexSet

    points = _coerce_points_to_3d(group_df[["X", "Y", "Z"]].to_numpy())
    vtk_obj = _build_vertex_set(points=points, topology_cls=vtk_class)

    if has_direct_normals:
        normals = np_column_stack(
            (group_df["Nx"].to_numpy(), group_df["Ny"].to_numpy(), group_df["Nz"].to_numpy())
        )
        normals_flipped = np_where(normals[:, 2:] > 0, normals * -1, normals)
        vtk_obj.set_point_data("Normals", normals_flipped)

    if has_dip:
        vtk_obj.set_point_data("dip", group_df["dip"].to_numpy())

    if has_dir:
        direction = (group_df["dir"].to_numpy() + 90.0) % 360.0
        vtk_obj.set_point_data("dip_dir", direction)
    elif has_dip_dir:
        vtk_obj.set_point_data("dip_dir", group_df["dip_dir"].to_numpy())

    if has_dip and ("dip_dir" in vtk_obj.point_data_keys) and "Normals" not in vtk_obj.point_data_keys:
        normals = dip_directions2normals(
            vtk_obj.get_point_data("dip"),
            vtk_obj.get_point_data("dip_dir"),
        )
        vtk_obj.set_point_data("Normals", normals)

    point_properties = _extract_numeric_properties(
        group_df,
        excluded_columns=SPECIAL_POINT_COLUMNS,
    )
    for property_name, values in point_properties.items():
        vtk_obj.set_point_data(property_name, values)

    return vtk_obj


def _import_tabular_file(self, collection, file_path, import_config):
    """Import a single tabular file into the selected collection."""
    input_df = _read_tabular_dataframe(file_path=file_path, import_config=import_config)

    props_map = {
        prop_name: prop_name
        for prop_name in ("feature", "role", "scenario")
        if prop_name in input_df.columns
    }
    column_names = list(input_df.columns)
    valid_roles = _get_valid_roles_for_collection(import_config["collection_name"])
    total_entities, invalid_role_count = _validate_and_fix_roles(
        input_df,
        "Point",
        props_map,
        column_names,
        valid_roles,
    )
    if invalid_role_count > 0:
        self.print_terminal(
            f"{os_path.basename(file_path)}: {invalid_role_count}/{total_entities} "
            "entities had invalid roles and were set to 'undef'."
        )

    skipped_properties = _extract_non_numeric_property_names(
        input_df,
        excluded_columns=SPECIAL_POINT_COLUMNS,
    )
    if skipped_properties:
        self.print_terminal(
            f"{os_path.basename(file_path)}: skipped non-numeric properties "
            + ", ".join(skipped_properties)
        )

    group_columns = _get_point_group_columns(props_map, column_names)
    grouped_iterable = (
        input_df.groupby(group_columns, dropna=False, sort=False)
        if group_columns
        else [(None, input_df)]
    )

    imported_count = 0
    for _group_key, group_df in grouped_iterable:
        vtk_obj = _build_tabular_vtk_object(group_df)
        metadata = {
            "name": _normalise_text_value(group_df.iloc[0]["name"], fallback="undef")
            if "name" in group_df.columns
            else import_config["name_value"],
            "feature": _normalise_text_value(
                group_df.iloc[0]["feature"],
                fallback=import_config["feature_value"],
            ),
            "role": _normalise_text_value(
                group_df.iloc[0]["role"],
                fallback=import_config["role_value"],
            ),
            "scenario": _normalise_text_value(
                group_df.iloc[0]["scenario"],
                fallback=import_config["scenario_value"],
            ),
        }
        entity_dict = _build_text_entity_dict(
            collection=collection,
            vtk_obj=vtk_obj,
            file_path=file_path,
            metadata=metadata,
        )
        collection.add_entity_from_dict(entity_dict=entity_dict)
        imported_count += 1

    return imported_count


def xyz2vtk(self=None, in_file_names=None, collection_name="Geology"):
    """
    Import generic tabular/VTK point files as VertexSet/Attitude entities.

    Supported formats:
    - Text-based: .txt, .csv, .xyz, .asc, .dat
    - VTK-based: .vtu, .vtk, .vtp
    """
    if self is None:
        return

    collection = _resolve_collection(self, collection_name)
    if collection is None:
        self.print_terminal(f"Unsupported destination collection: {collection_name}")
        return

    selected_files = list(in_file_names or [])
    text_files = []
    vtk_files = []
    failed_files = []
    imported_count = 0

    for in_file_name in selected_files:
        _, extension = os_path.splitext(in_file_name)
        extension = extension.lower()
        if extension in TEXT_EXTENSIONS:
            text_files.append(in_file_name)
        elif extension in VTK_EXTENSIONS:
            vtk_files.append(in_file_name)
        else:
            failed_files.append(
                (os_path.basename(in_file_name), f"unsupported extension {extension}")
            )

    import_config = None
    if not selected_files or text_files:
        dialog = XYZImportDialog(
            parent=self,
            in_file_names=selected_files,
            collection_name=collection_name,
        )
        import_config = dialog.exec()
        if import_config is None:
            self.print_terminal("XYZ import cancelled by user.")
            return

        selected_files = list(import_config.get("in_file_names", []))
        text_files = []
        vtk_files = []
        for in_file_name in selected_files:
            _, extension = os_path.splitext(in_file_name)
            extension = extension.lower()
            if extension in TEXT_EXTENSIONS:
                text_files.append(in_file_name)
            elif extension in VTK_EXTENSIONS:
                vtk_files.append(in_file_name)
            else:
                failed_files.append(
                    (os_path.basename(in_file_name), f"unsupported extension {extension}")
                )

        if not selected_files:
            self.print_terminal("XYZ import cancelled by user.")
            return

    for in_file_name in text_files:
        try:
            entities_added = _import_tabular_file(
                self=self,
                collection=collection,
                file_path=in_file_name,
                import_config=import_config,
            )
            imported_count += entities_added
            self.print_terminal(
                f"Imported tabular XYZ data: {os_path.basename(in_file_name)} "
                f"({entities_added} entity/ies created)"
            )
        except Exception as exc:
            failed_files.append((os_path.basename(in_file_name), str(exc)))
            self.print_terminal(
                f"Failed to import tabular XYZ data from {os_path.basename(in_file_name)}: {exc}"
            )

    for in_file_name in vtk_files:
        try:
            points, properties = _extract_from_vtk(in_file_name)
            vtk_obj = _build_vertex_set(points=points, properties=properties)
            entity_dict = _build_entity_dict(
                collection=collection,
                vtk_obj=vtk_obj,
                file_path=in_file_name,
            )
            collection.add_entity_from_dict(entity_dict=entity_dict)
            imported_count += 1
            self.print_terminal(
                f"Imported VTK points: {os_path.basename(in_file_name)} "
                f"({vtk_obj.points_number} points)"
            )
        except Exception as exc:
            failed_files.append((os_path.basename(in_file_name), str(exc)))
            self.print_terminal(
                f"Failed to import VTK points from {os_path.basename(in_file_name)}: {exc}"
            )

    if imported_count:
        self.print_terminal(
            f"XYZ import completed: {imported_count} entity/ies added to {collection_name}."
        )
    if failed_files:
        failed_summary = "; ".join(
            f"{file_name}: {error_message}" for file_name, error_message in failed_files
        )
        self.print_terminal(f"XYZ import skipped/failed files: {failed_summary}")
