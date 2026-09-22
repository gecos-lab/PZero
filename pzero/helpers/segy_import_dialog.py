"""Native Qt input-data review for SEG-Y seismic volumes."""

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFormLayout, QGroupBox, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QScrollArea, QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)

from pzero.imports.segy_reader import (
    DEFAULT_HEADERS, SegyImportOptions, inspect_segy, prepare_geometry,
)


class SegyImportDialog(QDialog):
    """Inspect headers first; only load the amplitude volume after Import."""

    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.path = str(path)
        self.survey = None
        self.import_options = None
        self._updating = False
        self._last_unit = "ms"
        self.setWindowTitle("PZero — Import seismic data")
        self.resize(620, 720)
        root = QVBoxLayout(self)
        filename = QLabel(Path(path).name)
        filename.setToolTip(str(path))
        filename.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(filename)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs)

        general = QWidget()
        layout = QVBoxLayout(general)
        general_scroll = QScrollArea()
        general_scroll.setWidgetResizable(True)
        general_scroll.setFrameShape(QScrollArea.NoFrame)
        general_scroll.setWidget(general)
        self.tabs.addTab(general_scroll, "Input data")
        form = self._group(layout, "General")
        self.name_edit = QLineEdit(Path(path).stem)
        form.addRow("Name", self.name_edit)
        self.type_label = QLabel("3D post-stack seismic")
        form.addRow("Type", self.type_label)
        self.domain_combo = self._combo([
            ("Two-way time (TWT)", "twt"), ("One-way time (OWT)", "owt"),
            ("Depth / elevation", "depth"),
        ])
        self.domain_combo.setPlaceholderText("Select the file's vertical domain…")
        self.domain_combo.setCurrentIndex(-1)
        form.addRow("Domain", self.domain_combo)
        self.datum_edit = QLineEdit()
        self.datum_edit.setPlaceholderText("Unspecified — e.g. seismic datum or mean sea level")
        form.addRow("Vertical datum", self.datum_edit)

        form = self._group(layout, "Coordinates and units")
        self.xy_combo = self._combo([
            ("Use SEG-Y measurement units", "header"),
            ("Metres", "m"), ("International feet → metres", "ft"),
        ])
        form.addRow("File XY units", self.xy_combo)
        self.file_crs_edit = QLineEdit()
        self.file_crs_edit.setPlaceholderText("Unspecified / local coordinates, or EPSG:32632")
        form.addRow("File CRS", self.file_crs_edit)
        self.target_crs_edit = QLineEdit()
        self.target_crs_edit.setPlaceholderText("Same as file CRS, or a projected EPSG code")
        form.addRow("Output CRS", self.target_crs_edit)
        note = QLabel("XY is stored in metres. CRS fields describe projected coordinates; "
                      "leaving them blank preserves an unspecified local system.")
        note.setWordWrap(True)
        form.addRow(note)

        form = self._group(layout, "Vertical sampling")
        self.unit_combo = self._combo([("Milliseconds", "ms"), ("Seconds", "s")])
        form.addRow("Sample units", self.unit_combo)
        self.override_check = QCheckBox("Specify first sample and interval")
        form.addRow(self.override_check)
        self.origin_spin = self._number(-1e9, 1e9, 0)
        self.step_spin = self._number(0.000001, 1e9, 1)
        form.addRow("First sample", self.origin_spin)
        form.addRow("Sample interval", self.step_spin)
        self.depth_confirm = QCheckBox("I have verified the first depth and interval against the source documentation")
        self.depth_confirm.setVisible(False)
        form.addRow(self.depth_confirm)
        self.depth_confirm.toggled.connect(self.update_preview)
        self.negate_check = QCheckBox("Input samples increase downward (negate Z)")
        self.negate_check.setChecked(True)
        form.addRow(self.negate_check)
        self.domain_note = QLabel("Keep time sampling, or supply a model on the Depth conversion tab.")
        self.domain_note.setWordWrap(True)
        form.addRow(self.domain_note)
        layout.addStretch()

        advanced = QWidget()
        advanced_layout = QVBoxLayout(advanced)
        self.tabs.addTab(advanced, "SEG-Y headers")
        form = self._group(advanced_layout, "Header mapping")
        self.endian_combo = self._combo([
            ("Detect byte order", "auto"), ("Big endian", "big"), ("Little endian", "little"),
        ])
        form.addRow("Byte order", self.endian_combo)
        self.auto_headers = QCheckBox("Detect header layout automatically")
        self.auto_headers.setChecked(True)
        form.addRow(self.auto_headers)
        self.auto_headers.toggled.connect(self._mapping_changed)
        self.header_spins = {}
        self.header_widths = {}
        for key, label in (("inline", "Inline"), ("crossline", "Crossline"), ("x", "X coordinate"), ("y", "Y coordinate")):
            spin = QSpinBox()
            spin.setRange(1, 239)
            spin.setValue(DEFAULT_HEADERS[key])
            self.header_spins[key] = spin
            form.addRow(label + " byte", spin)
            spin.valueChanged.connect(self._manual_mapping_changed)
            width = self._combo([("4-byte integer", 4), ("2-byte integer", 2)])
            self.header_widths[key] = width
            form.addRow(label + " width", width)
            width.currentIndexChanged.connect(self._manual_mapping_changed)
        hint = QLabel("One-based start bytes of signed trace-header fields. Automatic detection uses textual declarations and spatial consistency. "
                      "CDP X/Y: 181/185; source X/Y: 73/77. Coordinate scalars are always applied.")
        hint.setWordWrap(True)
        form.addRow(hint)
        self.scan_button = QPushButton("Read headers and preview")
        self.scan_button.clicked.connect(self.scan_headers)
        form.addRow(self.scan_button)
        self.header_text = QPlainTextEdit()
        self.header_text.setReadOnly(True)
        self.header_text.setLineWrapMode(QPlainTextEdit.NoWrap)
        advanced_layout.addWidget(self.header_text)

        conversion = QWidget()
        conversion_layout = QVBoxLayout(conversion)
        self.tabs.addTab(conversion, "Depth conversion")
        form = self._group(conversion_layout, "Time-to-depth model")
        self.model_combo = self._combo([("Keep source domain", "none"),
                                       ("Constant velocity", "constant"), ("Time-depth table / checkshots", "table")])
        form.addRow("Model", self.model_combo)
        self.velocity_spin = self._number(0, 100000, 0)
        self.velocity_spin.setSpecialValueText("Enter velocity")
        form.addRow("Velocity (m/s)", self.velocity_spin)
        self.model_time_spin = self._number(-1e6, 1e6, 0)
        self.model_datum_spin = self._number(-1e7, 1e7, 0)
        form.addRow("Reference travel time (s)", self.model_time_spin)
        form.addRow("Reference elevation (m)", self.model_datum_spin)
        self.table_edit = QPlainTextEdit()
        self.table_edit.setPlaceholderText("One time, depth pair per line, for example:\n0, 0\n1, 1200\n2, 2700")
        form.addRow("Table: time (s), depth (m)", self.table_edit)
        note = QLabel("Use a model appropriate to this survey. Table times must use the selected TWT or OWT convention, "
                      "relative to the reference travel time; depths increase below the reference elevation. "
                      "Constant velocity uses depth = velocity * time / 2 for TWT, or velocity * time for OWT. "
                      "Tables must cover the full time range. A single table is applied to every trace; "
                      "lateral velocity variation is not modelled. No velocity is inferred from reflection amplitudes.")
        note.setWordWrap(True)
        form.addRow(note)
        conversion_layout.addStretch()
        self.model_combo.currentIndexChanged.connect(self._model_changed)
        for spin in (self.velocity_spin, self.model_time_spin, self.model_datum_spin):
            spin.valueChanged.connect(self.update_preview)
        self.table_edit.textChanged.connect(self.update_preview)

        form = self._group(root, "Resulting data range")
        self.summary_label = QLabel("Reading SEG-Y headers…")
        self.summary_label.setWordWrap(True)
        form.addRow(self.summary_label)
        self.range_labels = {}
        for axis in "XYZ":
            label = QLabel("—")
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.range_labels[axis] = label
            form.addRow(axis + " range", label)
        self.status_label = QLabel("Select the vertical domain to review the import.")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.import_button = self.buttons.button(QDialogButtonBox.Ok)
        self.import_button.setText("Import")
        self.import_button.setEnabled(False)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)

        self.domain_combo.currentIndexChanged.connect(self._domain_changed)
        self.unit_combo.currentIndexChanged.connect(self._units_changed)
        self.override_check.toggled.connect(self._sampling_changed)
        self.endian_combo.currentIndexChanged.connect(self._mapping_changed)
        for combo in (self.xy_combo,):
            combo.currentIndexChanged.connect(self.update_preview)
        for edit in (self.name_edit, self.file_crs_edit, self.target_crs_edit, self.datum_edit):
            edit.textChanged.connect(self.update_preview)
        for spin in (self.origin_spin, self.step_spin):
            spin.valueChanged.connect(self.update_preview)
        self.negate_check.toggled.connect(self.update_preview)
        self._model_changed()
        self._sampling_changed()
        QTimer.singleShot(0, self.scan_headers)

    @staticmethod
    def _group(layout, title):
        group = QGroupBox(title)
        form = QFormLayout(group)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        layout.addWidget(group)
        return form

    @staticmethod
    def _combo(items):
        combo = QComboBox()
        for label, value in items:
            combo.addItem(label, value)
        return combo

    @staticmethod
    def _number(minimum, maximum, value):
        spin = QDoubleSpinBox()
        spin.setDecimals(6)
        spin.setRange(minimum, maximum)
        spin.setValue(value)
        return spin

    def _manual_mapping_changed(self, *_):
        if self._updating:
            return
        self.auto_headers.setChecked(False)
        self._mapping_changed()

    def _model_changed(self, *_):
        mode = self.model_combo.currentData()
        self.velocity_spin.setEnabled(mode == "constant")
        self.table_edit.setEnabled(mode == "table")
        self.model_time_spin.setEnabled(mode != "none")
        self.model_datum_spin.setEnabled(mode != "none")
        self.update_preview()

    def _mapping_changed(self, *_):
        if self._updating:
            return
        self.survey = None
        self.update_preview()

    def scan_headers(self):
        self.import_button.setEnabled(False)
        self.scan_button.setEnabled(False)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.survey = inspect_segy(
                self.path, self.endian_combo.currentData(),
                None if self.auto_headers.isChecked() else {key: spin.value() for key, spin in self.header_spins.items()},
                None if self.auto_headers.isChecked() else {key: combo.currentData() for key, combo in self.header_widths.items()},
            )
            survey = self.survey
            self._updating = True
            for key in self.header_spins:
                self.header_spins[key].setValue(survey["headers"][key])
                self.header_widths[key].setCurrentIndex(self.header_widths[key].findData(survey["header_widths"][key]))
            self._updating = False
            hints = survey.get("hints", {})
            if self.domain_combo.currentIndex() < 0 and hints.get("domain"):
                self.domain_combo.setCurrentIndex(self.domain_combo.findData(hints["domain"]))
                if hints["domain"] == "depth":
                    self.unit_combo.setCurrentIndex(self.unit_combo.findData(hints["vertical_units"]))
                    self.step_spin.setValue(hints["sample_step"])
                    self.origin_spin.setValue(hints.get("sample_origin") or 0)
            self.depth_confirm.setVisible(self.domain_combo.currentData() == "depth" and hints.get("sample_origin") is None)
            if not self.file_crs_edit.text() and hints.get("file_crs"):
                self.file_crs_edit.setText(hints["file_crs"])
            self.domain_note.setText(" ".join(hints.get("notes", [])) or
                                    "The file does not declare its vertical domain. Select it from the data provider's documentation.")
            self.type_label.setText("3D interval-velocity volume" if hints.get("data_kind") == "interval_velocity"
                                    else "3D velocity volume" if hints.get("data_kind") == "velocity"
                                    else "3D post-stack seismic")
            self.header_text.setPlainText(survey["text_header"])
            measurement = {1: "metres", 2: "feet"}.get(survey["measurement_system"], "unspecified")
            sampling = (f"Declared depth interval: {hints['sample_step']:g} {hints['vertical_units']}"
                        if hints.get("domain") == "depth" else
                        f"Sample interval: {survey['sample_interval_us']:g} us; recording delay: {survey['delay_ms']:g} ms")
            self.summary_label.setText(
                f"{survey['trace_count']:,} traces x {survey['num_samples']:,} samples; "
                f"{survey['format_name']}; {survey['endian']} endian\n"
                f"XY header units: {measurement}. {sampling}.\n"
                f"{survey['detection_evidence']}. "
                + ("A standard copy will be generated automatically." if survey["requires_standardization"] else "")
            )
            self.summary_label.setMinimumHeight(self.summary_label.heightForWidth(max(self.width() - 50, 200)))
            self._sampling_changed()
        except Exception as error:
            self.survey = None
            self.summary_label.setText("SEG-Y could not be inspected.")
            self._show_error(str(error))
        finally:
            self.scan_button.setEnabled(True)
            QApplication.restoreOverrideCursor()

    def _domain_changed(self, *_):
        depth = self.domain_combo.currentData() == "depth"
        self._updating = True
        self.unit_combo.clear()
        for label, value in ([('Metres', 'm'), ('International feet → metres', 'ft')] if depth
                             else [('Milliseconds', 'ms'), ('Seconds', 's')]):
            self.unit_combo.addItem(label, value)
        self._last_unit = self.unit_combo.currentData()
        self.override_check.setChecked(depth)
        self.override_check.setEnabled(not depth)
        if depth:
            hints = self.survey.get("hints", {}) if self.survey is not None else {}
            self.origin_spin.setValue(hints.get("sample_origin") or 0)
            self.step_spin.setValue(hints.get("sample_step") or 1)
        self.domain_note.setText(
            "Enter the actual depth sampling from the data provider. Depth is stored in metres; "
            "SEG-Y time-header values are not used as depth." if depth else
            "Keep time sampling, or supply a model on the Depth conversion tab."
        )
        self._updating = False
        hints = self.survey.get("hints", {}) if self.survey is not None else {}
        self.depth_confirm.setVisible(depth and hints.get("sample_origin") is None)
        if depth:
            self.model_combo.setCurrentIndex(0)
        self.model_combo.setEnabled(not depth)
        self._sampling_changed()

    def _units_changed(self, *_):
        if self._updating:
            return
        unit = self.unit_combo.currentData()
        if self.override_check.isChecked():
            factors = {"s": 1.0, "ms": 0.001, "m": 1.0, "ft": 0.3048}
            factor = factors[self._last_unit] / factors[unit]
            self._updating = True
            self.origin_spin.setValue(self.origin_spin.value() * factor)
            self.step_spin.setValue(self.step_spin.value() * factor)
            self._updating = False
        self._last_unit = unit
        self._sampling_changed()

    def _sampling_changed(self, *_):
        if self._updating:
            return
        override = self.override_check.isChecked()
        self.origin_spin.setEnabled(override)
        self.step_spin.setEnabled(override)
        if not override and self.survey is not None:
            factor = 0.001 if self.unit_combo.currentData() == "s" else 1.0
            self._updating = True
            self.origin_spin.setValue(self.survey["delay_ms"] * factor)
            self.step_spin.setValue(self.survey["sample_interval_us"] / 1000 * factor)
            self._updating = False
        self.update_preview()

    def options(self):
        override = self.override_check.isChecked()
        table = []
        if self.model_combo.currentData() == "table":
            for line in self.table_edit.toPlainText().splitlines():
                if line.strip():
                    try:
                        row = [float(value) for value in line.replace(",", " ").split()]
                    except ValueError:
                        raise ValueError("Table rows must contain numeric time (seconds) and depth (metres).")
                    if len(row) != 2:
                        raise ValueError("Each table row must have exactly two values: time (s), depth (m).")
                    table.append(row)
        return SegyImportOptions(
            name=self.name_edit.text().strip(), domain=self.domain_combo.currentData(),
            xy_units=self.xy_combo.currentData(), vertical_units=self.unit_combo.currentData(),
            negate_z=self.negate_check.isChecked(),
            sample_origin=self.origin_spin.value() if override else None,
            sample_step=self.step_spin.value() if override else None,
            vertical_datum=self.datum_edit.text().strip() or "Unspecified",
            file_crs=self.file_crs_edit.text().strip(), target_crs=self.target_crs_edit.text().strip(),
            endian=self.endian_combo.currentData(),
            headers=None if self.auto_headers.isChecked() else {key: spin.value() for key, spin in self.header_spins.items()},
            header_widths=None if self.auto_headers.isChecked() else {key: combo.currentData() for key, combo in self.header_widths.items()},
            depth_model=self.model_combo.currentData(), velocity_m_s=self.velocity_spin.value(),
            time_depth_table=table, depth_datum_m=self.model_datum_spin.value(),
            model_time_datum_s=self.model_time_spin.value(),
        )

    def _show_error(self, message):
        self.import_button.setEnabled(False)
        self.status_label.setStyleSheet("color: #b3261e;")
        self.status_label.setText(message)
        for label in self.range_labels.values():
            label.setText("—")

    def update_preview(self, *_):
        if self._updating:
            return False
        try:
            if self.survey is None:
                raise ValueError("Read the SEG-Y headers to preview these settings.")
            options = self.options()
            if not options.name:
                raise ValueError("Enter a name for the seismic volume.")
            geometry = prepare_geometry(self.survey, options)
            hints = self.survey.get("hints", {})
            if options.domain == "depth" and hints.get("sample_origin") is None and not self.depth_confirm.isChecked():
                raise ValueError("First depth is not declared in this file. Enter and confirm the depth sampling from the data provider.")
            for index, axis in enumerate("XY"):
                values = geometry["xy"][:, index]
                self.range_labels[axis].setText(f"{values.min():,.3f} to {values.max():,.3f} m")
            z = geometry["z"]
            self.range_labels["Z"].setText(f"{z.min():,.6g} to {z.max():,.6g} {geometry['z_units']} (positive up)")
            ni, nx, ns = geometry["dimensions"]
            crs = geometry["output_crs"] or "unspecified local CRS"
            self.status_label.setStyleSheet("")
            self.status_label.setText(
                f"Ready: {ni} inlines x {nx} crosslines x {ns} samples. Output: {crs}.\n"
                f"Navigation adjustment: up to {geometry['max_grid_residual_m']:.3g} m; "
                f"{geometry['recovered_coordinates']} coordinates recovered; {geometry['missing_bins']} bins masked.")
            self.status_label.setMinimumHeight(self.status_label.heightForWidth(max(self.width() - 30, 200)))
            self.import_button.setEnabled(True)
            return True
        except Exception as error:
            self._show_error(str(error))
            return False

    def accept(self):
        if self.update_preview():
            self.import_options = self.options()
            super().accept()
