"""
Piecewise Structural Complex support for the PyMeshIt workflow GUI.

This module keeps the PSC/STm material-assignment workflow out of the main
PyMeshIt GUI file. The controller deliberately works with the GUI as its host
so the refactor is organizational: existing tetra-surface data, material state,
PZero bridge access, and visualization refresh methods remain owned by the GUI.
"""

import re
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pyvista as pv
from PySide6.QtCore import Qt
from vtk import vtkCellArray, vtkPoints, vtkTriangle
from vtkmodules.util.numpy_support import vtk_to_numpy
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)



class PSCSectionSeedSelectionDialog(QDialog):
    """Small selector for PZero section seeds used as PSC seed overrides."""

    COL_INCLUDE = 0
    COL_UID = 1
    COL_NAME = 2
    COL_TYPE = 3
    COL_FEATURE = 4
    COL_ROLE = 5
    COL_SCENARIO = 6
    COL_MATCH = 7
    COL_STATUS = 8

    def __init__(
        self,
        parent,
        seed_rows: List[Dict[str, Any]],
        merged_seed_rows: Optional[List[Dict[str, Any]]] = None,
        saved_source_keys: Optional[set] = None,
        merge_eroded: bool = False,
    ):
        super().__init__(parent)
        self._normal_seed_rows = list(seed_rows)
        self._merged_seed_rows = list(merged_seed_rows or seed_rows)
        self._saved_source_keys = saved_source_keys
        self._updating = False
        self._has_eroded_candidates = any(
            bool(row.get("can_merge_eroded")) for row in self._merged_seed_rows
        )
        self._merge_eroded_enabled = bool(merge_eroded and self._has_eroded_candidates)
        self._seed_rows = (
            list(self._merged_seed_rows)
            if self._merge_eroded_enabled
            else list(self._normal_seed_rows)
        )

        self.setWindowTitle("Section Seeds for PSC")
        self.resize(1040, 480)

        layout = QVBoxLayout(self)
        label = QLabel(
            "Select PZero XsVertex/XsVertexSet objects to use as PSC seed coordinates."
        )
        label.setWordWrap(True)
        layout.addWidget(label)

        controls = QHBoxLayout()
        select_all_btn = QPushButton("Select all")
        select_all_btn.clicked.connect(lambda: self._set_importable_checked(True))
        controls.addWidget(select_all_btn)
        matched_btn = QPushButton("Matched only")
        matched_btn.clicked.connect(self._select_matched_only)
        controls.addWidget(matched_btn)
        self.merge_eroded_btn = QPushButton("Merge eroded")
        self.merge_eroded_btn.setCheckable(True)
        self.merge_eroded_btn.setChecked(self._merge_eroded_enabled)
        self.merge_eroded_btn.setEnabled(self._has_eroded_candidates)
        self.merge_eroded_btn.setToolTip(
            "Match section seeds with feature suffix '_eroded' to the PSC material 'eroded'."
        )
        self.merge_eroded_btn.toggled.connect(self._set_merge_eroded)
        controls.addWidget(self.merge_eroded_btn)
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(lambda: self._set_importable_checked(False))
        controls.addWidget(clear_btn)
        controls.addStretch(1)
        layout.addLayout(controls)

        self.table = QTableWidget(0, 9, self)
        self.table.setHorizontalHeaderLabels(
            [
                "Include",
                "UID",
                "Name",
                "Type",
                "Feature",
                "Role",
                "Scenario",
                "Target material",
                "Status",
            ]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        layout.addWidget(self.table, 1)

        header = self.table.horizontalHeader()
        for col_idx in range(self.table.columnCount()):
            if col_idx in (self.COL_NAME, self.COL_UID):
                header.setSectionResizeMode(col_idx, QHeaderView.Stretch)
            else:
                header.setSectionResizeMode(col_idx, QHeaderView.ResizeToContents)

        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._populate_table()
        self.table.itemChanged.connect(self._update_summary)
        self._update_summary()

    def selected_seed_rows(self) -> List[Dict[str, Any]]:
        """Return checked, importable section seed rows."""
        selected = []
        for row_idx in range(self.table.rowCount()):
            item = self.table.item(row_idx, self.COL_INCLUDE)
            if item is None or item.checkState() != Qt.Checked:
                continue
            seed_row = item.data(Qt.UserRole)
            if isinstance(seed_row, dict) and seed_row.get("target_unit_key"):
                selected.append(seed_row)
        return selected

    def selected_source_keys(self) -> List[str]:
        """Return stable source keys for the current checked rows."""
        return [
            str(row.get("source_key", ""))
            for row in self.selected_seed_rows()
            if str(row.get("source_key", ""))
        ]

    def merge_eroded_enabled(self) -> bool:
        """Return True when the eroded merge toggle is active."""
        return self._merge_eroded_enabled

    def _populate_table(self) -> None:
        self._updating = True
        try:
            self.table.setRowCount(len(self._seed_rows))
            has_saved_selection = bool(self._saved_source_keys)
            for row_idx, seed_row in enumerate(self._seed_rows):
                importable = bool(seed_row.get("target_unit_key"))
                source_key = str(seed_row.get("source_key", ""))
                checked = importable and (
                    not has_saved_selection or source_key in self._saved_source_keys
                )

                include_item = QTableWidgetItem("")
                include_item.setData(Qt.UserRole, seed_row)
                flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
                if importable:
                    flags |= Qt.ItemIsUserCheckable
                include_item.setFlags(flags)
                include_item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
                self.table.setItem(row_idx, self.COL_INCLUDE, include_item)

                values = [
                    seed_row.get("uid", ""),
                    seed_row.get("name", ""),
                    seed_row.get("topology", ""),
                    seed_row.get("feature", ""),
                    seed_row.get("role", ""),
                    seed_row.get("scenario", ""),
                    seed_row.get("matched_unit", ""),
                    seed_row.get("status", ""),
                ]
                for offset, value in enumerate(values, start=1):
                    item = QTableWidgetItem(str(value) if value not in (None, "") else "-")
                    if offset == self.COL_UID:
                        item.setToolTip(str(value))
                    if offset == self.COL_STATUS and not importable:
                        item.setForeground(QColor(190, 95, 0))
                    elif offset == self.COL_STATUS:
                        item.setForeground(QColor(40, 95, 170))
                    self.table.setItem(row_idx, offset, item)
        finally:
            self._updating = False

    def _set_importable_checked(self, checked: bool) -> None:
        self._updating = True
        try:
            for row_idx in range(self.table.rowCount()):
                item = self.table.item(row_idx, self.COL_INCLUDE)
                seed_row = item.data(Qt.UserRole) if item is not None else None
                if isinstance(seed_row, dict) and seed_row.get("target_unit_key"):
                    item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        finally:
            self._updating = False
        self._update_summary()

    def _select_matched_only(self) -> None:
        self._updating = True
        try:
            for row_idx in range(self.table.rowCount()):
                item = self.table.item(row_idx, self.COL_INCLUDE)
                seed_row = item.data(Qt.UserRole) if item is not None else None
                checked = (
                    isinstance(seed_row, dict)
                    and seed_row.get("status_key")
                    in {"matched", "matched_feature", "eroded"}
                )
                if isinstance(seed_row, dict) and seed_row.get("target_unit_key"):
                    item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        finally:
            self._updating = False
        self._update_summary()

    def _set_merge_eroded(self, checked: bool) -> None:
        current_selection = set(self.selected_source_keys())
        if current_selection:
            self._saved_source_keys = current_selection
        self._merge_eroded_enabled = bool(checked and self._has_eroded_candidates)
        self._seed_rows = (
            list(self._merged_seed_rows)
            if self._merge_eroded_enabled
            else list(self._normal_seed_rows)
        )
        self._populate_table()
        self._update_summary()

    def _update_summary(self, *_args) -> None:
        if self._updating:
            return
        selected_rows = self.selected_seed_rows()
        importable = sum(1 for row in self._seed_rows if row.get("target_unit_key"))
        mode = " | Merge eroded: on" if self._merge_eroded_enabled else ""
        self.summary_label.setText(
            f"Selected: {len(selected_rows)} object(s). "
            f"Importable candidates: {importable}/{len(self._seed_rows)}.{mode}"
        )


class PiecewiseStructuralComplex:
    """Controller for PSC preview, seed placement, and material assignment."""

    UNIT_ROLES = ("TU", "SU", "IU", "SD")
    SECTION_SEED_ROLES = frozenset(UNIT_ROLES)
    MAX_RELAXED_MISSING_BOUNDARIES = 1

    def __init__(self, host):
        object.__setattr__(self, "host", host)

    def __getattr__(self, name: str):
        return getattr(self.host, name)

    def __setattr__(self, name: str, value) -> None:
        if name == "host" or name.startswith("_psc_"):
            object.__setattr__(self, name, value)
        else:
            setattr(self.host, name, value)

    def open_mapping_dialog(self) -> None:
        """Preview a Piecewise Structural Complex mapping from an STm table."""
        project = self._pzero_project()
        if project is None:
            return

        stm_tables = self._available_stm_tables()
        if not stm_tables:
            self.print_terminal(
                "No Structural Topology model tables are available in the current PZero project."
            )
            return
        if not getattr(self, "tetra_surface_data", None):
            self.print_terminal(
                "Load conforming surfaces in the Tetra Mesh tab before building a PSC mapping."
            )
            return
    
        dialog = QDialog(self.host)
        dialog.setWindowTitle("Piecewise Structural Complex")
        dialog.resize(920, 520)
        layout = QVBoxLayout(dialog)
    
        info_label = QLabel(
            "Select an STm table. PSC discovers the connected 3D volumes formed by "
            "the conforming surfaces, then matches each volume to an STm signature."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
    
        selector_layout = QHBoxLayout()
        selector_layout.addWidget(QLabel("STm table"))
        table_combo = QComboBox(dialog)
        table_combo.addItems(stm_tables)
        selector_layout.addWidget(table_combo, 1)
        selector_layout.addWidget(QLabel("Max missing"))
        max_missing_spin = QSpinBox(dialog)
        max_missing_spin.setRange(0, 10)
        max_missing_spin.setValue(self.MAX_RELAXED_MISSING_BOUNDARIES)
        max_missing_spin.setToolTip(
            "Maximum number of expected boundaries that may be absent in a LIKELY "
            "3D topology match. Observed extra boundaries are never accepted."
        )
        selector_layout.addWidget(max_missing_spin)
        swap_seed_button = QPushButton("Swap selected seeds", dialog)
        swap_seed_button.setToolTip(
            "Select two ambiguous units in the preview table and swap their seed coordinates."
        )
        selector_layout.addWidget(swap_seed_button)
        from_sections_button = QPushButton("From sections", dialog)
        from_sections_button.setToolTip(
            "Use XsVertex/XsVertexSet seeds from geol_coll with roles TU, SU, IU, or SD."
        )
        selector_layout.addWidget(from_sections_button)
        use_calculated_button = QPushButton("Use calculated", dialog)
        use_calculated_button.setToolTip(
            "Clear saved PSC seed overrides and return to automatically calculated "
            "3D volumetric seed locations."
        )
        selector_layout.addWidget(use_calculated_button)
        layout.addLayout(selector_layout)
    
        preview_table = QTableWidget(0, 7, dialog)
        preview_table.setHorizontalHeaderLabels(
            [
                "Unit",
                "Unit Role",
                "Boundaries",
                "Matched surfaces",
                "Seed point",
                "Signature differences",
                "Assignment",
            ]
        )
        preview_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        preview_table.verticalHeader().setVisible(False)
        preview_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        preview_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        preview_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        layout.addWidget(preview_table, 1)
    
        status_label = QLabel("")
        status_label.setWordWrap(True)
        layout.addWidget(status_label)
    
        ambiguity_label = QLabel("")
        ambiguity_label.setWordWrap(True)
        ambiguity_label.setStyleSheet("color: rgb(160, 95, 0);")
        layout.addWidget(ambiguity_label)
    
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        assign_button = buttons.button(QDialogButtonBox.Ok)
        if assign_button is not None:
            assign_button.setText("Assign")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
    
        preview_state = {"psc_model": None, "mapping": None, "rows": []}
        seed_overrides: Dict[str, List[List[float]]] = {}
        seed_override_metadata: Dict[str, Dict[str, Any]] = {}
    
        def unit_seed_key(unit_info: Dict[str, Any]) -> str:
            return str(
                unit_info.get("key")
                or unit_info.get("name")
                or unit_info.get("feature")
                or ""
            )
    
        def load_seed_overrides(table_name: str) -> None:
            seed_overrides.clear()
            seed_override_metadata.clear()
            project = self._pzero_project()
            options = {}
            if project is not None:
                options = getattr(project, "custom_table_options", {}).get(table_name, {}) or {}
            raw_overrides = options.get("psc_seed_overrides", {})
            if not isinstance(raw_overrides, dict):
                return
            for unit_key, seed_value in raw_overrides.items():
                seed_points = self._psc_normalize_seed_points(seed_value)
                if seed_points:
                    seed_overrides[str(unit_key)] = seed_points
            raw_metadata = options.get("psc_seed_override_metadata", {})
            if isinstance(raw_metadata, dict):
                for unit_key, metadata in raw_metadata.items():
                    if str(unit_key) in seed_overrides and isinstance(metadata, dict):
                        seed_override_metadata[str(unit_key)] = dict(metadata)
    
        def save_seed_overrides(table_name: str) -> None:
            project = self._pzero_project()
            if project is None:
                return
            table_options = getattr(project, "custom_table_options", None)
            if table_options is None:
                return
            options = dict(table_options.get(table_name, {}) or {})
            if seed_overrides:
                options["psc_seed_overrides"] = {
                    unit_key: self._psc_seed_override_storage(seed_points)
                    for unit_key, seed_points in seed_overrides.items()
                }
                metadata = {
                    unit_key: dict(seed_override_metadata.get(unit_key, {}))
                    for unit_key in seed_overrides
                    if seed_override_metadata.get(unit_key)
                }
                if metadata:
                    options["psc_seed_override_metadata"] = metadata
                else:
                    options.pop("psc_seed_override_metadata", None)
            else:
                options.pop("psc_seed_overrides", None)
                options.pop("psc_seed_override_metadata", None)
            table_options[table_name] = options

        def load_section_seed_selection(table_name: str) -> Optional[set]:
            project = self._pzero_project()
            if project is None:
                return None
            options = getattr(project, "custom_table_options", {}).get(table_name, {}) or {}
            source_keys = options.get("psc_section_seed_selection")
            if not isinstance(source_keys, (list, tuple, set)):
                return None
            return {str(source_key) for source_key in source_keys if str(source_key)}

        def load_section_seed_merge_eroded(table_name: str) -> bool:
            project = self._pzero_project()
            if project is None:
                return False
            options = getattr(project, "custom_table_options", {}).get(table_name, {}) or {}
            return bool(options.get("psc_section_seed_merge_eroded", False))

        def save_section_seed_selection(
            table_name: str,
            source_keys: List[str],
            merge_eroded: bool,
        ) -> None:
            project = self._pzero_project()
            if project is None:
                return
            table_options = getattr(project, "custom_table_options", None)
            if table_options is None:
                return
            options = dict(table_options.get(table_name, {}) or {})
            if source_keys:
                options["psc_section_seed_selection"] = sorted(
                    {str(source_key) for source_key in source_keys if str(source_key)}
                )
            else:
                options.pop("psc_section_seed_selection", None)
            if merge_eroded:
                options["psc_section_seed_merge_eroded"] = True
            else:
                options.pop("psc_section_seed_merge_eroded", None)
            table_options[table_name] = options

        def apply_seed_overrides(mapping: Dict[str, Any]) -> None:
            matched_keys = set()
            for unit_info in mapping.get("units", []) or []:
                unit_key = unit_seed_key(unit_info)
                matched_keys.add(unit_key)
                if unit_key in seed_overrides:
                    seed_points = [list(seed) for seed in seed_overrides[unit_key]]
                    unit_info["seed_points"] = seed_points
                    unit_info["seed_point"] = seed_points[0] if seed_points else None
                    unit_info["seed_override"] = True
            for unit_key, seed_points in seed_overrides.items():
                if unit_key in matched_keys:
                    continue
                metadata = dict(seed_override_metadata.get(unit_key, {}))
                feature = self._psc_text(metadata.get("feature", "")) or str(unit_key)
                name = self._psc_text(metadata.get("name", "")) or feature
                role = self._psc_unit_role(metadata.get("unit_role", "TU"))
                clean_points = [list(seed) for seed in seed_points]
                mapping.setdefault("units", []).append(
                    {
                        "key": unit_key,
                        "name": name,
                        "feature": feature,
                        "unit_role": role,
                        "boundaries": [],
                        "matched_surfaces": [],
                        "matched_surface_indices": [],
                        "model_boundary_indices": [],
                        "missing_boundaries": [],
                        "seed_points": clean_points,
                        "seed_point": clean_points[0] if clean_points else None,
                        "seed_override": True,
                        "psc_virtual_unit": True,
                        "psc_virtual_source": metadata.get("source", "section_seed"),
                    }
                )
    
        def refresh_preview():
            table_name = table_combo.currentText()
            psc_model = self._build_psc_model_from_stm(table_name)
            mapping = self._map_psc_boundaries_to_tetra_surfaces(psc_model)
            apply_seed_overrides(mapping)
            preview_state["psc_model"] = psc_model
            preview_state["mapping"] = mapping
    
            rows = list(mapping.get("units", []))
            preview_state["rows"] = rows
            previous_side_context = getattr(self, "_psc_side_context", {})
            self._psc_side_context = self._psc_prepare_topology_side_context(
                psc_model,
                rows,
            )
            preview_table.setRowCount(len(rows))
            missing_count = 0
            seed_location_count = 0
            try:
                assignment_payloads = self._psc_assign_volumetric_regions(
                    rows,
                    psc_model,
                    max_missing_boundaries=int(max_missing_spin.value()),
                )
                if assignment_payloads is None:
                    for unit_info in rows:
                        unit_key = unit_seed_key(unit_info)
                        if unit_key in seed_overrides:
                            seed_points = [list(seed) for seed in seed_overrides[unit_key]]
                            unit_info["seed_point"] = seed_points[0] if seed_points else None
                            unit_info["seed_points"] = seed_points
                            unit_info["seed_override"] = True
                            continue
                        seed_points = self._psc_seed_points_for_unit(
                            unit_info,
                            psc_model,
                            rows,
                            max_missing_boundaries=int(max_missing_spin.value()),
                        )
                        unit_info["seed_points"] = seed_points
                        unit_info["seed_point"] = seed_points[0] if seed_points else None
                    assignment_payloads = self._psc_classify_seed_assignments(
                        rows,
                        psc_model,
                        max_missing_boundaries=int(max_missing_spin.value()),
                    )
                status_counts = {}
                for payload in assignment_payloads:
                    status = str(payload.get("status", "UNASSIGNED"))
                    status_counts[status] = status_counts.get(status, 0) + 1

                for row_idx, unit_info in enumerate(rows):
                    boundaries = unit_info.get("boundaries", [])
                    matched_surfaces = unit_info.get("matched_surfaces", [])
                    missing_boundaries = list(unit_info.get("missing_boundaries", []) or [])
                    extra_boundaries = []
                    for assignment in unit_info.get("psc_assignments", []) or []:
                        missing_boundaries.extend(
                            assignment.get("missing_labels", []) or []
                        )
                        extra_boundaries.extend(
                            assignment.get("extra_labels", []) or []
                        )
                    missing_boundaries = sorted(
                        {self._psc_text(label) for label in missing_boundaries if self._psc_text(label)},
                        key=str.casefold,
                    )
                    extra_boundaries = sorted(
                        {self._psc_text(label) for label in extra_boundaries if self._psc_text(label)},
                        key=str.casefold,
                    )
                    missing_count += len(missing_boundaries) + len(extra_boundaries)
                    signature_differences = []
                    if missing_boundaries:
                        signature_differences.append(
                            "Missing: " + ", ".join(missing_boundaries)
                        )
                    if extra_boundaries:
                        signature_differences.append(
                            "Extra: " + ", ".join(extra_boundaries)
                        )
                    seed_points = list(unit_info.get("seed_points", []) or [])
                    seed_location_count += len(seed_points or [])
                    seed_text = self._psc_format_seed_list(seed_points)
                    if unit_info.get("seed_override") and seed_text:
                        seed_text += " *"
                    assignment_status = unit_info.get(
                        "psc_assignment_status",
                        "UNASSIGNED",
                    )
                    values = [
                        unit_info.get("feature", ""),
                        unit_info.get("unit_role", ""),
                        ", ".join(boundaries),
                        ", ".join(matched_surfaces),
                        seed_text,
                        "; ".join(signature_differences),
                        assignment_status,
                    ]
                    for col_idx, value in enumerate(values):
                        item = QTableWidgetItem(str(value))
                        if col_idx == 4 and unit_info.get("seed_override"):
                            item.setToolTip(
                                "Seed overridden in this PSC dialog "
                                "(manual swap or From sections)."
                            )
                            item.setForeground(QColor(40, 95, 170))
                        if col_idx == 5 and signature_differences:
                            item.setForeground(QColor(190, 40, 40))
                        if col_idx == 6 and assignment_status in {
                            "LIKELY",
                            "AMBIGUOUS",
                            "POSSIBLE_REPEAT",
                            "UNASSIGNED",
                        }:
                            item.setForeground(QColor(190, 95, 20))
                            blocked = sorted(
                                {
                                    label
                                    for assignment in unit_info.get(
                                        "psc_rejected_assignments", []
                                    )
                                    for label in assignment.get(
                                        "blocked_repeat_labels", []
                                    )
                                },
                                key=str.casefold,
                            )
                            if blocked:
                                item.setToolTip(
                                    "Blocked repeat across: " + ", ".join(blocked)
                                )
                        preview_table.setItem(row_idx, col_idx, item)
            finally:
                self._psc_side_context = previous_side_context
    
            status_label.setText(
                f"Units: {len(rows)} | "
                f"3D volumes: {getattr(self, '_psc_last_volumetric_region_count', 0)} | "
                f"Seed locations: {seed_location_count} | "
                f"Known boundaries: {len(psc_model.get('boundary_features', set()))} | "
                f"Signature differences: {missing_count} | "
                f"Saved seed overrides: {len(seed_overrides)} | "
                "Assignments: "
                f"CERTAIN={status_counts.get('CERTAIN', 0)}, "
                f"LIKELY={status_counts.get('LIKELY', 0)}, "
                f"AMBIGUOUS={status_counts.get('AMBIGUOUS', 0)}, "
                f"POSSIBLE_REPEAT={status_counts.get('POSSIBLE_REPEAT', 0)}, "
                f"UNASSIGNED={status_counts.get('UNASSIGNED', 0)}"
            )
            ambiguity_groups = self._psc_ambiguity_groups(rows)
            if ambiguity_groups:
                group_text = "; ".join(
                    ", ".join(unit.get("name") or unit.get("feature", "") for unit in group)
                    for group in ambiguity_groups
                )
                ambiguity_label.setText(
                    "Potential ambiguous PSC units: "
                    f"{group_text}. Select two rows and use Swap selected seeds if the "
                    "preview coordinates are inverted."
                )
            else:
                ambiguity_label.setText("")
    
        def swap_selected_seeds():
            selection_model = preview_table.selectionModel()
            selected_rows = []
            if selection_model is not None:
                selected_rows = sorted(
                    {index.row() for index in selection_model.selectedRows()}
                )
            if not selected_rows:
                selected_rows = sorted(
                    {item.row() for item in preview_table.selectedItems()}
                )
            if len(selected_rows) != 2:
                self.print_terminal("Select exactly two unit rows before swapping seeds.")
                return
    
            rows = list(preview_state.get("rows", []))
            if any(row_idx < 0 or row_idx >= len(rows) for row_idx in selected_rows):
                return
            first_unit = rows[selected_rows[0]]
            second_unit = rows[selected_rows[1]]
            swapped_points = self._psc_swapped_seed_points(first_unit, second_unit)
            if swapped_points is None:
                self.print_terminal(
                    "Both selected units need at least one valid seed before swapping."
                )
                return
            first_key = unit_seed_key(first_unit)
            second_key = unit_seed_key(second_unit)
            first_points, second_points = swapped_points
            seed_overrides[first_key] = first_points
            seed_overrides[second_key] = second_points
            save_seed_overrides(table_combo.currentText())
            refresh_preview()
    
        def import_section_seeds():
            rows = list(preview_state.get("rows", []))
            if not rows:
                refresh_preview()
                rows = list(preview_state.get("rows", []))
            table_name = table_combo.currentText()
            seed_rows = self._psc_section_seed_match_rows(
                rows,
                unit_seed_key,
            )
            if not seed_rows:
                self.print_terminal(
                    "No XsVertex/XsVertexSet section seeds with PSC roles were found in geol_coll."
                )
                return
            merged_seed_rows = self._psc_section_seed_match_rows(
                rows,
                unit_seed_key,
                merge_eroded=True,
            )
            selection_dialog = PSCSectionSeedSelectionDialog(
                dialog,
                seed_rows,
                merged_seed_rows,
                load_section_seed_selection(table_name),
                load_section_seed_merge_eroded(table_name),
            )
            if selection_dialog.exec() != QDialog.Accepted:
                return
            selected_seed_rows = selection_dialog.selected_seed_rows()
            imported = self._psc_section_seed_overrides_from_rows(selected_seed_rows)
            imported_metadata = self._psc_section_seed_metadata_from_rows(selected_seed_rows)
            if not imported:
                self.print_terminal(
                    "No matching section seed was selected for the current PSC units."
                )
                return
            save_section_seed_selection(
                table_name,
                selection_dialog.selected_source_keys(),
                selection_dialog.merge_eroded_enabled(),
            )
            seed_overrides.clear()
            seed_overrides.update(imported)
            seed_override_metadata.clear()
            seed_override_metadata.update(imported_metadata)
            save_seed_overrides(table_name)
            refresh_preview()
            seed_count = sum(len(points) for points in imported.values())
            unmatched = sum(
                1 for row in seed_rows
                if row.get("status_key") in {"no_match", "ambiguous"}
            )
            self.print_terminal(
                f"Imported {seed_count} section seed(s) for {len(imported)} PSC material(s) "
                f"from {len(selected_seed_rows)} selected PZero object(s) "
                f"(unmatched_or_ambiguous={unmatched})."
            )

        def clear_seed_overrides():
            if not seed_overrides:
                return
            seed_overrides.clear()
            seed_override_metadata.clear()
            save_seed_overrides(table_combo.currentText())
            refresh_preview()
    
        def on_table_changed():
            load_seed_overrides(table_combo.currentText())
            refresh_preview()
    
        swap_seed_button.clicked.connect(swap_selected_seeds)
        from_sections_button.clicked.connect(import_section_seeds)
        use_calculated_button.clicked.connect(clear_seed_overrides)
        table_combo.currentTextChanged.connect(lambda _text: on_table_changed())
        max_missing_spin.valueChanged.connect(lambda _value: refresh_preview())
        load_seed_overrides(table_combo.currentText())
        refresh_preview()
    
        if dialog.exec() != QDialog.Accepted:
            return
    
        table_name = table_combo.currentText()
        self.psc_model = self._build_psc_model_from_stm(table_name)
        self.psc_mapping = self._map_psc_boundaries_to_tetra_surfaces(self.psc_model)
        apply_seed_overrides(self.psc_mapping)
        assigned_count, skipped_count = self._assign_psc_materials(
            self.psc_model,
            self.psc_mapping,
            max_missing_boundaries=int(max_missing_spin.value()),
        )
        if assigned_count == 0:
            self.print_terminal(
                "No PSC unit could be assigned. Check that STm boundaries match the loaded tetra surfaces."
            )
            return
    
        seed_count = int(getattr(self, "_psc_last_seed_count", assigned_count))
        assignment_counts = getattr(self, "_psc_last_assignment_counts", {}) or {}
        self.print_terminal(
            f"Assigned {assigned_count} material(s) with "
            f"{seed_count} seed location(s) from STm table '{table_name}'."
            + (f" Skipped {skipped_count} unit(s) without a valid seed." if skipped_count else "")
            + " Assignments: "
            + ", ".join(
                f"{status}={assignment_counts.get(status, 0)}"
                for status in (
                    "CERTAIN",
                    "LIKELY",
                    "AMBIGUOUS",
                    "POSSIBLE_REPEAT",
                    "UNASSIGNED",
                )
            )
            + "."
        )

    def _psc_normalize_seed_points(self, value: Any) -> List[List[float]]:
        """Return a clean list of XYZ seed points from legacy or multi-seed values."""
        if value is None:
            return []

        def as_point(point_value: Any) -> Optional[List[float]]:
            try:
                coords = [float(coord) for coord in list(point_value)[:3]]
            except (TypeError, ValueError):
                return None
            if len(coords) == 3 and all(np.isfinite(coords)):
                return coords
            return None

        try:
            values = list(value)
        except TypeError:
            return []
        if not values:
            return []

        first = values[0]
        if np.isscalar(first):
            point = as_point(values)
            return [point] if point is not None else []

        seed_points = []
        for item in values:
            point = as_point(item)
            if point is not None:
                seed_points.append(point)
        return seed_points

    def _psc_seed_override_storage(self, seed_points: List[List[float]]) -> Any:
        """Store one seed as legacy XYZ, multiple seeds as a list of XYZ points."""
        clean_points = self._psc_normalize_seed_points(seed_points)
        if len(clean_points) == 1:
            return [float(value) for value in clean_points[0]]
        return [[float(value) for value in point] for point in clean_points]

    def _psc_swapped_seed_points(
        self,
        first_unit: Dict[str, Any],
        second_unit: Dict[str, Any],
    ) -> Optional[Tuple[List[List[float]], List[List[float]]]]:
        """Return complete seed lists swapped between two PSC units."""
        first_points = self._psc_normalize_seed_points(
            first_unit.get("seed_points") or first_unit.get("seed_point")
        )
        second_points = self._psc_normalize_seed_points(
            second_unit.get("seed_points") or second_unit.get("seed_point")
        )
        if not first_points or not second_points:
            return None
        return (
            [list(point) for point in second_points],
            [list(point) for point in first_points],
        )

    def _psc_unit_match_keys(self, unit_info: Dict[str, Any]) -> set:
        """Return normalized material keys accepted for a PSC mapped unit."""
        feature = self._psc_text(unit_info.get("feature", ""))
        role = self._psc_text(unit_info.get("unit_role", ""))
        name = self._psc_text(unit_info.get("name", ""))
        keys = {
            self._psc_key(feature),
            self._psc_key(name),
        }
        if feature and role:
            keys.add(self._psc_key(f"{feature}_{role}"))
            keys.add(self._psc_key(f"{feature} {role}"))
        return {key for key in keys if key}

    def _psc_section_seed_entries(self) -> List[Dict[str, Any]]:
        """Read PSC seed candidates from section XsVertexSet entities in geol_coll."""
        project = self._pzero_project()
        geol_coll = getattr(project, "geol_coll", None)
        if geol_coll is None:
            return []

        role_keys = {self._psc_key(role) for role in self.SECTION_SEED_ROLES}
        entries = []
        for uid in getattr(geol_coll, "get_uids", []) or []:
            try:
                topology = self._psc_text(geol_coll.get_uid_topology(uid))
                role = self._psc_text(geol_coll.get_uid_role(uid))
                feature = self._psc_text(geol_coll.get_uid_feature(uid))
            except Exception:
                continue
            if topology not in {"XsVertexSet", "XsVertex"}:
                continue
            if self._psc_key(role) not in role_keys:
                continue
            if not feature:
                continue
            try:
                vtk_obj = geol_coll.get_uid_vtk_obj(uid)
                points = np.asarray(getattr(vtk_obj, "points", []), dtype=float)
            except Exception:
                continue
            if points.ndim == 1:
                points = points.reshape(1, -1)
            if points.ndim != 2 or points.shape[1] < 3 or points.shape[0] == 0:
                continue
            seed_points = []
            for point in points[:, :3]:
                coords = [float(value) for value in point[:3]]
                if all(np.isfinite(coords)):
                    seed_points.append(coords)
            if not seed_points:
                continue
            try:
                name = self._psc_text(geol_coll.get_uid_name(uid))
            except Exception:
                name = ""
            try:
                scenario = self._psc_text(geol_coll.get_uid_scenario(uid))
            except Exception:
                scenario = ""
            entries.append(
                {
                    "uid": uid,
                    "name": name,
                    "topology": topology,
                    "role": role,
                    "feature": feature,
                    "scenario": scenario,
                    "source_key": str(uid),
                    "feature_key": self._psc_key(feature),
                    "role_key": self._psc_key(role),
                    "seed_points": seed_points,
                }
            )
        return entries

    def _psc_section_seed_overrides_for_units(
        self,
        mapped_units: List[Dict[str, Any]],
        unit_seed_key,
    ) -> Tuple[Dict[str, List[List[float]]], int, int]:
        """Match section XsVertexSet seeds to mapped PSC units."""
        seed_rows = self._psc_section_seed_match_rows(mapped_units, unit_seed_key)
        selected_rows = [
            row for row in seed_rows
            if row.get("target_unit_key")
            and row.get("status_key")
            in {"matched", "matched_feature", "eroded"}
        ]
        overrides = self._psc_section_seed_overrides_from_rows(selected_rows)
        skipped = 0
        unmatched = 0
        for row in seed_rows:
            if row.get("target_unit_key"):
                continue
            if row.get("status_key") in {"no_match", "ambiguous"}:
                unmatched += 1
            else:
                skipped += 1
        return overrides, skipped, unmatched

    def _psc_unit_match_rows(
        self,
        mapped_units: List[Dict[str, Any]],
        unit_seed_key,
    ) -> List[Dict[str, Any]]:
        """Return normalized PSC unit records used to match section seeds."""
        unit_matches = []
        for unit_info in mapped_units or []:
            unit_key = unit_seed_key(unit_info)
            unit_matches.append(
                {
                    "unit_info": unit_info,
                    "unit_key": unit_key,
                    "unit_name": self._psc_text(
                        unit_info.get("name")
                        or unit_info.get("feature")
                        or unit_key
                    ),
                    "material_keys": self._psc_unit_match_keys(unit_info),
                    "role_key": self._psc_key(unit_info.get("unit_role", "")),
                }
            )
        return unit_matches

    def _psc_section_seed_match_rows(
        self,
        mapped_units: List[Dict[str, Any]],
        unit_seed_key,
        merge_eroded: bool = False,
    ) -> List[Dict[str, Any]]:
        """Return section seed candidates annotated with PSC matching status."""
        unit_matches = self._psc_unit_match_rows(mapped_units, unit_seed_key)
        seed_rows = []
        for entry in self._psc_section_seed_entries():
            seed_row = dict(entry)
            feature_key = entry.get("feature_key", "")
            role_key = entry.get("role_key", "")
            is_eroded = self._psc_feature_is_eroded(entry.get("feature", ""))
            seed_row["can_merge_eroded"] = is_eroded
            if is_eroded:
                target_feature = "eroded" if merge_eroded else entry.get("feature", "")
                target_unit_key = (
                    "section_seed:eroded"
                    if merge_eroded
                    else f"section_seed:{feature_key}"
                )
                seed_row.update(
                    {
                        "target_unit_key": target_unit_key,
                        "matched_unit": target_feature,
                        "status_key": "eroded",
                        "status": "eroded",
                        "target_metadata": {
                            "name": target_feature,
                            "feature": target_feature,
                            "unit_role": "" if merge_eroded else entry.get("role", ""),
                            "source": "section_eroded_seed",
                            "source_feature": entry.get("feature", ""),
                        },
                    }
                )
                seed_rows.append(seed_row)
                continue
            target = None
            status_key = "no_match"
            status = "No PSC match"

            role_matches = [
                unit
                for unit in unit_matches
                if feature_key in unit["material_keys"] and role_key == unit["role_key"]
            ]
            if len(role_matches) == 1:
                target = role_matches[0]
                status_key = "matched"
                status = "Matched"
            elif len(role_matches) > 1:
                status_key = "ambiguous"
                status = "Ambiguous"
            else:
                material_matches = [
                    unit
                    for unit in unit_matches
                    if feature_key in unit["material_keys"]
                ]
                if len(material_matches) == 1:
                    target = material_matches[0]
                    status_key = "matched_feature"
                    status = "Matched by feature"
                elif len(material_matches) > 1:
                    status_key = "ambiguous"
                    status = "Ambiguous"

            if target is not None:
                seed_row["target_unit_key"] = target.get("unit_key", "")
                seed_row["matched_unit"] = target.get("unit_name", "")
            else:
                seed_row["target_unit_key"] = ""
                seed_row["matched_unit"] = ""
            seed_row["status_key"] = status_key
            seed_row["status"] = status
            seed_rows.append(seed_row)
        return seed_rows

    def _psc_section_seed_overrides_from_rows(
        self,
        seed_rows: List[Dict[str, Any]],
    ) -> Dict[str, List[List[float]]]:
        """Build PSC seed overrides from selected section seed rows."""
        overrides: Dict[str, List[List[float]]] = {}
        for seed_row in seed_rows or []:
            unit_key = str(seed_row.get("target_unit_key", ""))
            if not unit_key:
                continue
            overrides.setdefault(unit_key, []).extend(
                [list(point) for point in seed_row.get("seed_points", [])]
            )
        return overrides

    def _psc_section_seed_metadata_from_rows(
        self,
        seed_rows: List[Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        """Build metadata for section seed overrides that are not STm units."""
        metadata_by_key: Dict[str, Dict[str, Any]] = {}
        for seed_row in seed_rows or []:
            unit_key = str(seed_row.get("target_unit_key", ""))
            metadata = seed_row.get("target_metadata")
            if not unit_key or not isinstance(metadata, dict):
                continue
            metadata_by_key.setdefault(unit_key, dict(metadata))
        return metadata_by_key
    
    def _available_stm_tables(self) -> List[str]:
        """Return STm table names from the embedded PZero project."""
        project = self._pzero_project()
        if project is None:
            return []
        table_types = getattr(project, "custom_table_types", {}) or {}
        return sorted(
            [
                table_name
                for table_name, table_type in table_types.items()
                if table_type == "stm"
            ],
            key=lambda value: str(value).casefold(),
        )
    
    def _pzero_project(self):
        """Return the PZero project window, if PyMeshIt is embedded in PZero."""
        bridge = getattr(self, "pzero_bridge", None)
        return getattr(bridge, "_project", None)
    
    @staticmethod
    def _psc_format_point(point: Any) -> str:
        """Format a point for concise PSC diagnostics."""
        if point is None:
            return "None"
        try:
            coords = np.asarray(point, dtype=float).reshape(-1)
        except (TypeError, ValueError):
            return str(point)
        if coords.size < 3:
            return str(point)
        return f"({coords[0]:.3f}, {coords[1]:.3f}, {coords[2]:.3f})"
    
    def _psc_format_seed_list(self, seed_points: Any) -> str:
        """Format one or more PSC seed points for the preview table."""
        if not seed_points:
            return ""
        points = list(seed_points)
        if len(points) == 1:
            point = np.asarray(points[0], dtype=float).reshape(-1)
            if point.size >= 3:
                return f"{point[0]:.2f}, {point[1]:.2f}, {point[2]:.2f}"
            return str(points[0])
        formatted = []
        for point in points:
            coords = np.asarray(point, dtype=float).reshape(-1)
            if coords.size >= 3:
                formatted.append(f"{coords[0]:.2f}, {coords[1]:.2f}, {coords[2]:.2f}")
            else:
                formatted.append(str(point))
        return f"{len(points)} pts: " + "; ".join(formatted)
    
    def _psc_ambiguity_groups(
        self,
        mapped_units: List[Dict[str, Any]],
    ) -> List[List[Dict[str, Any]]]:
        """Return mapped PSC units that share the same boundary signature."""
        groups: Dict[Tuple[Tuple[str, ...], bool], List[Dict[str, Any]]] = {}
        boundary_key = self._psc_key("Boundary")
        for unit_info in mapped_units or []:
            keys = {
                self._psc_key(boundary)
                for boundary in unit_info.get("boundaries", []) or []
                if self._psc_key(boundary)
            }
            structural_keys = tuple(sorted(key for key in keys if key != boundary_key))
            if not structural_keys:
                continue
            signature = (structural_keys, boundary_key in keys)
            groups.setdefault(signature, []).append(unit_info)
        return [
            group
            for group in groups.values()
            if len(group) > 1
        ]
    
    def _psc_structural_boundary_keys_for_unit(
        self,
        unit_info: Dict[str, Any],
    ) -> set:
        """Return normalized non-Boundary STm boundary keys for one mapped unit."""
        boundary_key = self._psc_key("Boundary")
        return {
            self._psc_key(boundary)
            for boundary in unit_info.get("boundaries", []) or []
            if self._psc_key(boundary) and self._psc_key(boundary) != boundary_key
        }
    
    def _psc_boundary_labels_by_key(
        self,
        unit_info: Dict[str, Any],
    ) -> Dict[str, str]:
        """Return display labels keyed by normalized STm boundary key."""
        labels = {}
        for boundary in unit_info.get("boundaries", []) or []:
            boundary_text = self._psc_text(boundary)
            boundary_key = self._psc_key(boundary_text)
            if boundary_key and boundary_key not in labels:
                labels[boundary_key] = boundary_text
        return labels
    
    def _psc_local_boundary_sets_for_unit(
        self,
        unit_info: Dict[str, Any],
        mapped_units: List[Dict[str, Any]],
    ) -> List[List[str]]:
        """Infer local boundary subsets for a globally bounded PSC unit."""
        unit_keys = self._psc_structural_boundary_keys_for_unit(unit_info)
        if len(unit_keys) < 3:
            return []
    
        boundary_key = self._psc_key("Boundary")
        has_model_boundary = any(
            self._psc_key(boundary) == boundary_key
            for boundary in unit_info.get("boundaries", []) or []
        )
        unit_labels = self._psc_boundary_labels_by_key(unit_info)
        candidates: Dict[Tuple[str, ...], List[str]] = {}
    
        for other_info in mapped_units or []:
            if other_info is unit_info:
                continue
            other_keys = self._psc_structural_boundary_keys_for_unit(other_info)
            if len(other_keys) < 2 or not other_keys < unit_keys:
                continue
            other_labels = self._psc_boundary_labels_by_key(other_info)
            key_tuple = tuple(sorted(other_keys))
            labels = [
                unit_labels.get(key) or other_labels.get(key) or key
                for key in key_tuple
            ]
            if has_model_boundary:
                labels.append("Boundary")
            candidates.setdefault(key_tuple, labels)
    
        return [
            candidates[key_tuple]
            for key_tuple in sorted(candidates, key=lambda item: (-len(item), item))
        ]
    
    def _psc_unit_with_local_boundaries(
        self,
        unit_info: Dict[str, Any],
        local_boundaries: List[str],
        component_index: int,
    ) -> Dict[str, Any]:
        """Return a unit-info copy restricted to one local boundary subset."""
        local_info = dict(unit_info)
        local_info["boundaries"] = list(local_boundaries)
        base_name = unit_info.get("name") or unit_info.get("feature") or "PSC unit"
        structural_labels = [
            boundary
            for boundary in local_boundaries
            if self._psc_key(boundary) != self._psc_key("Boundary")
        ]
        local_info["name"] = (
            f"{base_name} component {component_index + 1}"
            f" ({', '.join(structural_labels)})"
        )
        local_info["component_name"] = base_name
        local_info["component_index"] = component_index
    
        source_indices = unit_info.get("boundary_surface_indices", {}) or {}
        source_by_key = {
            self._psc_key(boundary): (boundary, indices)
            for boundary, indices in source_indices.items()
        }
        filtered_indices = {}
        for boundary in local_boundaries:
            boundary_key = self._psc_key(boundary)
            source_entry = source_by_key.get(boundary_key)
            if source_entry is None:
                continue
            source_boundary, indices = source_entry
            filtered_indices[source_boundary] = list(indices or [])
        local_info["boundary_surface_indices"] = filtered_indices
    
        structural_indices = []
        model_boundary_indices = []
        for boundary, indices in filtered_indices.items():
            target = (
                model_boundary_indices
                if self._psc_key(boundary) == self._psc_key("Boundary")
                else structural_indices
            )
            for surface_idx in indices or []:
                try:
                    target.append(int(surface_idx))
                except (TypeError, ValueError):
                    continue
        local_info["matched_surface_indices"] = sorted(set(structural_indices))
        local_info["model_boundary_indices"] = sorted(set(model_boundary_indices))
        local_info.pop("seed_topology_signature", None)
        local_info.pop("seed_topology_signatures", None)
        local_info.pop("seed_point", None)
        local_info.pop("seed_points", None)
        return local_info

    def _psc_topology_components(
        self,
        mapped_units: List[Dict[str, Any]],
        include_inferred_local: bool = False,
    ) -> List[Dict[str, Any]]:
        """Return global and geometrically realized local topology signatures."""
        components = []
        for unit_info in mapped_units or []:
            unit_key = str(
                unit_info.get("key")
                or unit_info.get("feature")
                or unit_info.get("name")
                or ""
            )
            if not unit_key:
                continue

            global_boundaries = list(unit_info.get("boundaries", []) or [])
            boundary_sets = [
                {
                    "boundaries": global_boundaries,
                    "component_index": -1,
                    "is_local": False,
                }
            ]
            # A set-theoretic subset is only a possible local signature.  It
            # becomes a classification candidate after seed generation has
            # actually found a point for that signature.  This prevents, for
            # example, a valid global Int2 seed from becoming ambiguous merely
            # because another unit happens to contain Int2's boundary set.
            for entry_index, entry in enumerate(
                unit_info.get("seed_topology_signatures", []) or []
            ):
                if not isinstance(entry, dict):
                    continue
                entry_boundaries = list(entry.get("boundaries", []) or [])
                if not entry_boundaries:
                    continue
                boundary_sets.append(
                    {
                        "boundaries": entry_boundaries,
                        "component_index": int(
                            entry.get("component_index", entry_index)
                        ),
                        "is_local": {
                            self._psc_key(label)
                            for label in entry_boundaries
                            if self._psc_key(label)
                        }
                        != {
                            self._psc_key(label)
                            for label in global_boundaries
                            if self._psc_key(label)
                        },
                    }
                )
            if include_inferred_local:
                for component_index, boundaries in enumerate(
                    self._psc_local_boundary_sets_for_unit(unit_info, mapped_units)
                ):
                    boundary_sets.append(
                        {
                            "boundaries": list(boundaries),
                            "component_index": component_index,
                            "is_local": True,
                        }
                    )
            seen_signatures = set()
            for component in boundary_sets:
                boundaries = component["boundaries"]
                labels_by_key = {}
                for boundary in boundaries:
                    label = self._psc_text(boundary)
                    key = self._psc_key(label)
                    if key and key not in labels_by_key:
                        labels_by_key[key] = label
                signature_key = tuple(sorted(labels_by_key))
                if not signature_key or signature_key in seen_signatures:
                    continue
                seen_signatures.add(signature_key)
                components.append(
                    {
                        "unit_info": unit_info,
                        "unit_key": unit_key,
                        "component_index": int(component["component_index"]),
                        "is_local": bool(component["is_local"]),
                        "boundaries": [
                            labels_by_key[key] for key in sorted(labels_by_key)
                        ],
                        "signature_keys": set(labels_by_key),
                        "polarity": self._psc_sort_key(unit_info.get("polarity", "")),
                        "feature": self._psc_text(unit_info.get("feature", "")),
                    }
                )
        return components

    def _psc_candidate_observation_quality(
        self,
        candidate: Dict[str, Any],
        observed_labels: List[str],
    ) -> Dict[str, Any]:
        """Score one intended unit signature against the surfaces near its seed."""
        candidate = dict(candidate)
        labels_by_key = {}
        for label in candidate.get("boundaries", []) or []:
            label_text = self._psc_text(label)
            label_key = self._psc_key(label_text)
            if label_key and label_key not in labels_by_key:
                labels_by_key[label_key] = label_text
        signature_keys = set(candidate.get("signature_keys", set()) or set(labels_by_key))

        observed_by_key = {}
        for label in observed_labels or []:
            label_text = self._psc_text(label)
            label_key = self._psc_key(label_text)
            if label_key and label_key not in observed_by_key:
                observed_by_key[label_key] = label_text
        observed_keys = set(observed_by_key)
        missing_keys = signature_keys - observed_keys
        extra_keys = observed_keys - signature_keys
        candidate.update(
            {
                "exact": not missing_keys and not extra_keys,
                "missing_count": len(missing_keys),
                "missing_labels": [
                    labels_by_key.get(key, key) for key in sorted(missing_keys)
                ],
                "extra_count": len(extra_keys),
                "extra_labels": [
                    observed_by_key.get(key, key) for key in sorted(extra_keys)
                ],
                "observed_count": len(observed_keys),
            }
        )
        return candidate

    def _psc_unit_candidates_for_topology_signature(
        self,
        mapped_units: List[Dict[str, Any]],
        observed_labels: List[str],
        max_missing_boundaries: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Match an observed 3D signature to global and local unit signatures."""
        if max_missing_boundaries is None:
            max_missing_boundaries = self.MAX_RELAXED_MISSING_BOUNDARIES
        try:
            max_missing_boundaries = max(int(max_missing_boundaries), 0)
        except (TypeError, ValueError):
            max_missing_boundaries = self.MAX_RELAXED_MISSING_BOUNDARIES

        observed_labels_by_key = {}
        for label in observed_labels or []:
            label_text = self._psc_text(label)
            label_key = self._psc_key(label_text)
            if label_key and label_key not in observed_labels_by_key:
                observed_labels_by_key[label_key] = label_text
        observed_keys = set(observed_labels_by_key)
        if not observed_keys:
            return []

        best_by_unit = {}
        for component in self._psc_topology_components(mapped_units):
            unit_keys = set(component.get("signature_keys", set()) or set())
            extra_keys = observed_keys - unit_keys
            if extra_keys:
                continue
            missing_keys = unit_keys - observed_keys
            if len(missing_keys) > max_missing_boundaries:
                continue
            unit_info = component["unit_info"]
            labels_by_key = self._psc_boundary_labels_by_key(unit_info)
            candidate = {
                **component,
                "exact": not missing_keys,
                "missing_count": len(missing_keys),
                "missing_labels": [
                    labels_by_key.get(key, key) for key in sorted(missing_keys)
                ],
                "observed_count": len(observed_keys),
            }
            quality = (
                0 if candidate["exact"] else 1,
                candidate["missing_count"],
                -candidate["observed_count"],
                candidate["polarity"],
                candidate["feature"].casefold(),
                candidate["unit_key"].casefold(),
            )
            existing = best_by_unit.get(candidate["unit_key"])
            if existing is None or quality < existing[0]:
                best_by_unit[candidate["unit_key"]] = (quality, candidate)

        return [
            item[1]
            for item in sorted(best_by_unit.values(), key=lambda item: item[0])
        ]

    def _psc_repeat_conflict_labels(
        self,
        unit_key: str,
        seed_point: List[float],
        closest_surface_indices: Dict[str, int],
        assignments: List[Dict[str, Any]],
        psc_model: Dict[str, Any],
    ) -> List[str]:
        """Return representative surfaces across which a unit repeat is forbidden."""
        unit_key = str(unit_key or "")
        if not unit_key:
            return []
        try:
            seed = np.asarray(seed_point, dtype=float).reshape(3)
        except (TypeError, ValueError):
            return []

        boundary_key = self._psc_key("Boundary")
        representative_keys = self._psc_representative_boundary_keys(psc_model)
        bounds = self._psc_domain_bounds()
        tolerance = 1.0e-8
        if bounds is not None:
            tolerance = max(float(np.linalg.norm(bounds[1] - bounds[0])) * 0.002, tolerance)

        conflicts = []
        for assignment in assignments or []:
            if assignment.get("unit_key", "") != unit_key:
                continue
            other_indices = assignment.get("closest_surface_indices", {}) or {}
            shared_keys = set(closest_surface_indices).intersection(other_indices)
            for feature_key in sorted(shared_keys):
                if feature_key == boundary_key or feature_key not in representative_keys:
                    continue
                try:
                    surface_idx = int(closest_surface_indices[feature_key])
                    other_surface_idx = int(other_indices[feature_key])
                except (TypeError, ValueError):
                    continue
                if surface_idx != other_surface_idx:
                    continue
                other_point = assignment.get("seed_point")
                try:
                    other_seed = np.asarray(other_point, dtype=float).reshape(3)
                except (TypeError, ValueError):
                    continue
                sign = self._psc_sign(
                    self._psc_signed_distance_to_surface(seed, surface_idx),
                    tolerance,
                )
                other_sign = self._psc_sign(
                    self._psc_signed_distance_to_surface(other_seed, surface_idx),
                    tolerance,
                )
                if sign == 0 or other_sign == 0 or sign != other_sign:
                    conflicts.append(
                        self._psc_text(self._psc_surface_feature(surface_idx))
                        or feature_key
                    )
        return sorted(set(conflicts), key=str.casefold)

    def _psc_closest_surface_indices_for_point(
        self,
        point: List[float],
        boundary_labels: List[str],
    ) -> Dict[str, int]:
        """Return the closest concrete PLC surface for each observed feature."""
        try:
            point_array = np.asarray(point, dtype=float).reshape(1, 3)
        except (TypeError, ValueError):
            return {}
        closest = {}
        for boundary in boundary_labels or []:
            boundary_key = self._psc_key(boundary)
            if not boundary_key:
                continue
            best = None
            for surface_idx in self._psc_surface_indices_for_boundary(boundary):
                distances = self._psc_points_to_surface_distances(
                    point_array,
                    int(surface_idx),
                )
                if not distances.size or not np.isfinite(distances[0]):
                    continue
                candidate = (float(distances[0]), int(surface_idx))
                if best is None or candidate < best:
                    best = candidate
            if best is not None:
                closest[boundary_key] = best[1]
        return closest

    @staticmethod
    def _psc_tetra_incenter(tetra_points: np.ndarray) -> Tuple[np.ndarray, float]:
        """Return an interior point and its inscribed-sphere radius for a tetrahedron."""
        points = np.asarray(tetra_points, dtype=float)
        if points.shape != (4, 3):
            return np.zeros(3, dtype=float), 0.0

        opposite_areas = []
        for vertex_idx in range(4):
            face = np.delete(points, vertex_idx, axis=0)
            area = 0.5 * np.linalg.norm(
                np.cross(face[1] - face[0], face[2] - face[0])
            )
            opposite_areas.append(float(area))
        area_sum = float(sum(opposite_areas))
        volume = abs(
            float(
                np.linalg.det(
                    np.stack(
                        (
                            points[1] - points[0],
                            points[2] - points[0],
                            points[3] - points[0],
                        ),
                        axis=0,
                    )
                )
            )
        ) / 6.0
        if area_sum <= 1.0e-15 or volume <= 1.0e-18:
            return np.mean(points, axis=0), 0.0
        weights = np.asarray(opposite_areas, dtype=float)
        return np.sum(points * weights[:, None], axis=0) / area_sum, 3.0 * volume / area_sum

    def _psc_surface_info_for_index(self, surface_idx: int) -> Dict[str, Any]:
        """Return conforming-surface metadata for an integer dataset index."""
        surface_data = getattr(self, "tetra_surface_data", {}) or {}
        return surface_data.get(surface_idx, surface_data.get(str(surface_idx), {})) or {}

    def _psc_marker_surface(self, marker: Any) -> Optional[int]:
        """Map a TetGen PLC face marker to its source surface index."""
        try:
            marker = int(marker)
        except (TypeError, ValueError):
            return None
        if marker >= 1000:
            return marker - 1000
        if marker > 0:
            return marker - 1
        return None

    def _psc_region_surface_label(
        self,
        surface_idx: int,
        border_surface_indices: set,
    ) -> str:
        """Return the STM-facing label represented by one PLC surface."""
        if int(surface_idx) in border_surface_indices:
            return "Boundary"
        surface_info = self._psc_surface_info_for_index(int(surface_idx))
        return (
            self._psc_text(surface_info.get("feature", ""))
            or self._psc_text(surface_info.get("name", ""))
            or f"Surface_{surface_idx}"
        )

    def _psc_regions_from_tetrahedra(
        self,
        nodes: Any,
        elements: Any,
        trifaces: Any,
        triface_markers: Any,
        border_surface_indices: Optional[set] = None,
    ) -> Dict[str, Any]:
        """Split an unseeded tetrahedralization at every constrained PLC face."""
        nodes = np.asarray(nodes, dtype=float)
        elements = np.asarray(elements, dtype=int)
        trifaces = np.asarray(trifaces, dtype=int)
        markers = np.asarray(triface_markers, dtype=int).reshape(-1)
        border_surface_indices = {
            int(value) for value in (border_surface_indices or set())
        }
        if nodes.ndim != 2 or nodes.shape[1] < 3:
            raise ValueError("TetGen returned invalid PSC node coordinates.")
        if elements.ndim != 2 or elements.shape[1] < 4 or not len(elements):
            raise ValueError("TetGen returned no tetrahedra for PSC volume discovery.")
        if trifaces.ndim != 2 or trifaces.shape[1] < 3:
            raise ValueError("TetGen returned invalid PSC face connectivity.")
        if len(trifaces) != len(markers):
            raise ValueError("TetGen PSC faces and face markers have different lengths.")

        elements = elements[:, :4]
        trifaces = trifaces[:, :3]
        face_owners: Dict[Tuple[int, int, int], List[int]] = {}
        tetra_faces = ((1, 2, 3), (0, 2, 3), (0, 1, 3), (0, 1, 2))
        for tetra_idx, tetra in enumerate(elements):
            for face_vertices in tetra_faces:
                face_key = tuple(sorted(int(tetra[idx]) for idx in face_vertices))
                face_owners.setdefault(face_key, []).append(int(tetra_idx))

        marker_by_face: Dict[Tuple[int, int, int], int] = {}
        for face, marker in zip(trifaces, markers):
            face_key = tuple(sorted(int(value) for value in face[:3]))
            marker = int(marker)
            if marker or face_key not in marker_by_face:
                marker_by_face[face_key] = marker

        open_adjacency = [set() for _ in range(len(elements))]
        for face_key, owners in face_owners.items():
            if len(owners) != 2 or int(marker_by_face.get(face_key, 0)) != 0:
                continue
            first, second = owners
            open_adjacency[first].add(second)
            open_adjacency[second].add(first)

        tetra_to_region = np.full(len(elements), -1, dtype=int)
        component_tetrahedra: List[List[int]] = []
        for start_idx in range(len(elements)):
            if tetra_to_region[start_idx] >= 0:
                continue
            region_idx = len(component_tetrahedra)
            queue = [start_idx]
            tetra_to_region[start_idx] = region_idx
            component = []
            queue_idx = 0
            while queue_idx < len(queue):
                tetra_idx = queue[queue_idx]
                queue_idx += 1
                component.append(tetra_idx)
                for neighbour in open_adjacency[tetra_idx]:
                    if tetra_to_region[neighbour] >= 0:
                        continue
                    tetra_to_region[neighbour] = region_idx
                    queue.append(neighbour)
            component_tetrahedra.append(component)

        region_markers = [set() for _ in component_tetrahedra]
        region_interfaces: List[Dict[int, List[Dict[str, Any]]]] = [
            {} for _ in component_tetrahedra
        ]
        for face_key, owners in face_owners.items():
            marker = int(marker_by_face.get(face_key, 0))
            if marker <= 0:
                continue
            owner_regions = sorted({int(tetra_to_region[owner]) for owner in owners})
            for region_idx in owner_regions:
                region_markers[region_idx].add(marker)
            if len(owner_regions) != 2:
                continue
            first_region, second_region = owner_regions
            surface_idx = self._psc_marker_surface(marker)
            if surface_idx is None:
                continue
            label = self._psc_region_surface_label(
                surface_idx,
                border_surface_indices,
            )
            interface = {
                "marker": marker,
                "surface_index": int(surface_idx),
                "label": label,
            }
            for source_region, target_region in (
                (first_region, second_region),
                (second_region, first_region),
            ):
                interfaces = region_interfaces[source_region].setdefault(
                    target_region, []
                )
                interface_key = (marker, int(surface_idx), self._psc_key(label))
                if not any(
                    (
                        int(existing.get("marker", 0)),
                        int(existing.get("surface_index", -1)),
                        self._psc_key(existing.get("label", "")),
                    )
                    == interface_key
                    for existing in interfaces
                ):
                    interfaces.append(dict(interface))

        regions = []
        for region_idx, tetra_indices in enumerate(component_tetrahedra):
            best_point = None
            best_radius = -1.0
            for tetra_idx in tetra_indices:
                tetra_points = nodes[elements[tetra_idx], :3]
                point, radius = self._psc_tetra_incenter(tetra_points)
                if radius > best_radius:
                    best_point = point
                    best_radius = radius
            if best_point is None:
                best_point = np.mean(nodes[elements[tetra_indices[0]], :3], axis=0)
                best_radius = 0.0

            surface_indices = sorted(
                {
                    surface_idx
                    for marker in region_markers[region_idx]
                    for surface_idx in [self._psc_marker_surface(marker)]
                    if surface_idx is not None
                }
            )
            labels_by_key = {}
            label_surface_indices: Dict[str, List[int]] = {}
            for surface_idx in surface_indices:
                label = self._psc_region_surface_label(
                    surface_idx,
                    border_surface_indices,
                )
                label_key = self._psc_key(label)
                if not label_key:
                    continue
                labels_by_key.setdefault(label_key, label)
                label_surface_indices.setdefault(label_key, []).append(
                    int(surface_idx)
                )
            regions.append(
                {
                    "region_id": int(region_idx),
                    "tetra_indices": list(tetra_indices),
                    "tetra_count": len(tetra_indices),
                    "seed_point": [float(value) for value in best_point[:3]],
                    "clearance": max(float(best_radius), 0.0),
                    "boundary_labels": [
                        labels_by_key[key] for key in sorted(labels_by_key)
                    ],
                    "surface_indices": surface_indices,
                    "surface_markers": sorted(region_markers[region_idx]),
                    "label_surface_indices": {
                        key: sorted(set(indices))
                        for key, indices in label_surface_indices.items()
                    },
                    "adjacent_regions": {
                        int(target): sorted(
                            interfaces,
                            key=lambda item: (
                                self._psc_key(item.get("label", "")),
                                int(item.get("surface_index", -1)),
                            ),
                        )
                        for target, interfaces in region_interfaces[region_idx].items()
                    },
                }
            )

        return {
            "regions": regions,
            "tetra_to_region": tetra_to_region,
            "nodes": nodes,
            "elements": elements,
        }

    def _psc_volumetric_partition_signature(self) -> Tuple[Any, ...]:
        """Return a lightweight cache key for the current conforming PLC."""
        surface_data = getattr(self, "tetra_surface_data", {}) or {}
        descriptors = []
        for raw_idx, surface_info in sorted(
            surface_data.items(), key=lambda item: str(item[0])
        ):
            try:
                surface_idx = int(raw_idx)
            except (TypeError, ValueError):
                continue
            vertices = surface_info.get("vertices", [])
            triangles = surface_info.get("triangles", [])
            descriptors.append(
                (
                    surface_idx,
                    id(vertices),
                    tuple(np.shape(vertices)),
                    id(triangles),
                    tuple(np.shape(triangles)),
                    self._psc_key(surface_info.get("feature", "")),
                    self._psc_key(surface_info.get("name", "")),
                )
            )
        try:
            border_indices = tuple(sorted(int(i) for i in self._get_border_surface_indices()))
        except Exception:
            border_indices = ()
        try:
            fault_indices = tuple(sorted(int(i) for i in self._get_fault_surface_indices()))
        except Exception:
            fault_indices = ()
        return tuple(descriptors), border_indices, fault_indices

    def _psc_build_volumetric_regions(
        self,
        _psc_model: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Discover the closed 3D regions formed by the loaded conforming surfaces."""
        signature = self._psc_volumetric_partition_signature()
        cached = getattr(self, "_psc_volumetric_partition_cache", None)
        if isinstance(cached, tuple) and len(cached) == 2 and cached[0] == signature:
            return cached[1]

        surface_data = getattr(self, "tetra_surface_data", {}) or {}
        selected_surfaces = set()
        for surface_idx in surface_data:
            try:
                selected_surfaces.add(int(surface_idx))
            except (TypeError, ValueError):
                continue
        if not selected_surfaces:
            self._psc_volumetric_partition_cache = (signature, None)
            return None

        try:
            border_indices = {
                int(value) for value in self._get_border_surface_indices()
            }
        except Exception:
            border_indices = set()
        try:
            fault_indices = {
                int(value) for value in self._get_fault_surface_indices()
            }
        except Exception:
            fault_indices = set()
        unit_indices = selected_surfaces - border_indices - fault_indices

        raw_datasets = list(getattr(self, "datasets", []) or [])
        dataset_count = max(len(raw_datasets), max(selected_surfaces) + 1)
        datasets = []
        for dataset_idx in range(dataset_count):
            if dataset_idx < len(raw_datasets) and isinstance(
                raw_datasets[dataset_idx], dict
            ):
                dataset = dict(raw_datasets[dataset_idx])
            else:
                dataset = {}
            if dataset.get("type") == "WELL":
                dataset["type"] = "IGNORED_FOR_PSC_PARTITION"
            surface_info = self._psc_surface_info_for_index(dataset_idx)
            dataset.setdefault(
                "name", surface_info.get("name", f"Surface_{dataset_idx}")
            )
            datasets.append(dataset)

        try:
            try:
                from Pymeshit.tetra_mesh_utils import TetrahedralMeshGenerator
            except ImportError:
                from pzero.pymeshit_app.Pymeshit.tetra_mesh_utils import (
                    TetrahedralMeshGenerator,
                )

            holes = []
            collect_holes = getattr(self.host, "_collect_holes_from_constraint_tree", None)
            if callable(collect_holes):
                holes = collect_holes() or []
            terminal = getattr(self.host, "print_terminal", None)
            if callable(terminal):
                terminal("PSC: discovering connected 3D volumes from conforming surfaces...")
            generator = TetrahedralMeshGenerator(
                datasets=datasets,
                selected_surfaces=selected_surfaces,
                border_surface_indices=border_indices,
                unit_surface_indices=unit_indices,
                fault_surface_indices=fault_indices,
                materials=[],
                surface_data=surface_data,
                holes=holes,
                well_data={},
            )
            mesh = generator.generate_tetrahedral_mesh("pQ")
            tet = getattr(generator, "tetgen_object", None)
            if mesh is None or tet is None:
                raise RuntimeError("the provisional TetGen partition was not produced")
            partition = self._psc_regions_from_tetrahedra(
                tet.node,
                tet.elem,
                tet.trifaces,
                tet.triface_markers,
                border_indices,
            )
            partition["mesh"] = mesh
            partition["border_surface_indices"] = border_indices
            partition["fault_surface_indices"] = fault_indices
            self._psc_volumetric_partition_cache = (signature, partition)
            if callable(terminal):
                terminal(
                    f"PSC: discovered {len(partition.get('regions', []))} connected 3D volume(s)."
                )
            return partition
        except Exception as exc:
            self._psc_volumetric_partition_cache = (signature, None)
            terminal = getattr(self.host, "print_terminal", None)
            if callable(terminal):
                terminal(
                    "PSC 3D volume discovery failed; using the legacy geometric seed "
                    f"fallback. Reason: {exc}"
                )
            return None

    def _psc_volumetric_region_candidates(
        self,
        region: Dict[str, Any],
        mapped_units: List[Dict[str, Any]],
        max_missing_boundaries: int,
    ) -> List[Dict[str, Any]]:
        """Rank STM units against one physical 3D region boundary signature."""
        observed_labels = list(region.get("boundary_labels", []) or [])
        observed_by_key = {
            self._psc_key(label): self._psc_text(label)
            for label in observed_labels
            if self._psc_key(label)
        }
        observed_keys = set(observed_by_key)
        candidates = []
        for unit_info in mapped_units or []:
            if unit_info.get("psc_virtual_unit"):
                continue
            labels_by_key = self._psc_boundary_labels_by_key(unit_info)
            unit_keys = set(labels_by_key)
            if not unit_keys:
                continue
            missing_keys = unit_keys - observed_keys
            extra_keys = observed_keys - unit_keys
            if extra_keys or len(missing_keys) > max_missing_boundaries:
                continue
            mismatch_count = len(missing_keys)
            unit_key = str(
                unit_info.get("key")
                or unit_info.get("feature")
                or unit_info.get("name")
                or ""
            )
            if not unit_key:
                continue
            candidate = {
                "unit_info": unit_info,
                "unit_key": unit_key,
                "feature": self._psc_text(unit_info.get("feature", "")),
                "boundaries": [labels_by_key[key] for key in sorted(labels_by_key)],
                "signature_keys": unit_keys,
                "exact": mismatch_count == 0,
                "missing_count": len(missing_keys),
                "missing_labels": [
                    labels_by_key.get(key, key) for key in sorted(missing_keys)
                ],
                "extra_count": len(extra_keys),
                "extra_labels": [
                    observed_by_key.get(key, key) for key in sorted(extra_keys)
                ],
                "mismatch_count": mismatch_count,
                "observed_count": len(observed_keys),
                "polarity": self._psc_sort_key(unit_info.get("polarity", "")),
            }
            candidate["quality"] = (
                0 if candidate["exact"] else 1,
                mismatch_count,
                candidate["missing_count"],
                candidate["extra_count"],
                -candidate["observed_count"],
                candidate["polarity"],
            )
            candidates.append(candidate)
        return sorted(
            candidates,
            key=lambda candidate: (
                candidate["quality"],
                candidate["feature"].casefold(),
                candidate["unit_key"].casefold(),
            ),
        )

    def _psc_override_region_id(
        self,
        point: List[float],
        partition: Dict[str, Any],
    ) -> Optional[int]:
        """Locate an explicit/manual seed in the discovered volumetric partition."""
        try:
            coords = np.asarray(point, dtype=float).reshape(3)
        except (TypeError, ValueError):
            return None
        mesh = partition.get("mesh")
        if mesh is not None and hasattr(mesh, "find_containing_cell"):
            try:
                tetra_idx = int(mesh.find_containing_cell(coords))
                tetra_to_region = np.asarray(partition.get("tetra_to_region", []), dtype=int)
                if 0 <= tetra_idx < len(tetra_to_region):
                    return int(tetra_to_region[tetra_idx])
            except Exception:
                pass
        regions = list(partition.get("regions", []) or [])
        if not regions:
            return None
        return int(
            min(
                regions,
                key=lambda region: float(
                    np.linalg.norm(
                        coords - np.asarray(region.get("seed_point", coords), dtype=float)
                    )
                ),
            ).get("region_id", -1)
        )

    def _psc_volumetric_repeat_conflicts(
        self,
        unit_key: str,
        region: Dict[str, Any],
        assignments: List[Dict[str, Any]],
        psc_model: Dict[str, Any],
    ) -> List[str]:
        """Block equal adjacent units across explicit representative faces."""
        representative_keys = self._psc_representative_boundary_keys(psc_model)
        boundary_key = self._psc_key("Boundary")
        adjacency = region.get("adjacent_regions", {}) or {}
        conflicts = []
        for assignment in assignments or []:
            if assignment.get("unit_key") != unit_key:
                continue
            other_region_id = int(assignment.get("volumetric_region_id", -1))
            interfaces = adjacency.get(
                other_region_id, adjacency.get(str(other_region_id), [])
            )
            for interface in interfaces or []:
                label = self._psc_text(interface.get("label", ""))
                feature_key = self._psc_key(label)
                if (
                    not feature_key
                    or feature_key == boundary_key
                    or feature_key not in representative_keys
                ):
                    continue
                conflicts.append(label or feature_key)
        return sorted(set(conflicts), key=str.casefold)

    def _psc_assign_volumetric_regions(
        self,
        mapped_units: List[Dict[str, Any]],
        psc_model: Dict[str, Any],
        max_missing_boundaries: Optional[int] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        """Assign exactly one seed to each connected physical volume of the 3D PLC."""
        if max_missing_boundaries is None:
            max_missing_boundaries = self.MAX_RELAXED_MISSING_BOUNDARIES
        try:
            max_missing_boundaries = max(int(max_missing_boundaries), 0)
        except (TypeError, ValueError):
            max_missing_boundaries = self.MAX_RELAXED_MISSING_BOUNDARIES

        self._psc_last_volumetric_region_count = 0
        partition = self._psc_build_volumetric_regions(psc_model)
        if partition is None:
            return None
        regions = list(partition.get("regions", []) or [])
        self._psc_last_volumetric_region_count = len(regions)
        regions_by_id = {
            int(region.get("region_id", region_idx)): region
            for region_idx, region in enumerate(regions)
        }

        pinned_by_region: Dict[int, Dict[str, Any]] = {}
        for unit_info in mapped_units or []:
            if not unit_info.get("seed_override"):
                continue
            unit_key = str(
                unit_info.get("key")
                or unit_info.get("feature")
                or unit_info.get("name")
                or ""
            )
            for point in self._psc_normalize_seed_points(
                unit_info.get("seed_points") or unit_info.get("seed_point")
            ):
                region_id = self._psc_override_region_id(point, partition)
                if region_id is None or region_id not in regions_by_id:
                    continue
                pinned_by_region.setdefault(
                    region_id,
                    {
                        "unit_info": unit_info,
                        "unit_key": unit_key,
                        "seed_point": list(point),
                    },
                )

        records = []
        for region_id, region in sorted(regions_by_id.items()):
            pin = pinned_by_region.get(region_id)
            if pin is not None:
                unit_info = pin["unit_info"]
                labels_by_key = self._psc_boundary_labels_by_key(unit_info)
                candidates = [
                    {
                        "unit_info": unit_info,
                        "unit_key": pin["unit_key"],
                        "feature": self._psc_text(unit_info.get("feature", "")),
                        "boundaries": [
                            labels_by_key[key] for key in sorted(labels_by_key)
                        ],
                        "signature_keys": set(labels_by_key),
                        "exact": True,
                        "missing_count": 0,
                        "missing_labels": [],
                        "extra_count": 0,
                        "extra_labels": [],
                        "mismatch_count": 0,
                        "observed_count": len(
                            region.get("boundary_labels", []) or []
                        ),
                        "polarity": self._psc_sort_key(
                            unit_info.get("polarity", "")
                        ),
                        "quality": (0, 0, 0, 0, 0, 0.0),
                        "pinned": True,
                    }
                ]
                seed_point = list(pin["seed_point"])
            else:
                candidates = self._psc_volumetric_region_candidates(
                    region,
                    mapped_units,
                    max_missing_boundaries,
                )
                seed_point = list(region.get("seed_point", []) or [])
            best_quality = candidates[0]["quality"] if candidates else (9, 9, 9, 9, 9, 9)
            best_count = sum(
                1 for candidate in candidates if candidate["quality"] == best_quality
            )
            records.append(
                {
                    "region_id": region_id,
                    "region": region,
                    "seed_point": seed_point,
                    "candidates": candidates,
                    "best_quality": best_quality,
                    "best_count": best_count,
                    "pinned": pin is not None,
                }
            )
        records.sort(
            key=lambda record: (
                0 if record["pinned"] else 1,
                record["best_quality"],
                record["best_count"],
                record["region_id"],
            )
        )

        assigned_counts: Dict[str, int] = {}
        accepted = []
        rejected_by_unit: Dict[str, List[Dict[str, Any]]] = {}
        payloads = []
        for record in records:
            region = record["region"]
            filtered_candidates = []
            blocked_labels = []
            for candidate in record["candidates"]:
                conflicts = self._psc_volumetric_repeat_conflicts(
                    candidate["unit_key"],
                    region,
                    accepted,
                    psc_model,
                )
                if conflicts:
                    blocked_labels.extend(conflicts)
                    continue
                filtered_candidates.append(candidate)

            if not filtered_candidates:
                rejected_candidate = (
                    record["candidates"][0] if record["candidates"] else None
                )
                payload = {
                    "status": "UNASSIGNED",
                    "unit_key": "",
                    "source_unit_key": (
                        rejected_candidate.get("unit_key", "")
                        if rejected_candidate
                        else ""
                    ),
                    "seed_point": list(record["seed_point"]),
                    "boundaries": list(region.get("boundary_labels", []) or []),
                    "candidate_names": [
                        self._psc_text(candidate["unit_info"].get("name", ""))
                        or self._psc_text(candidate["feature"])
                        or candidate["unit_key"]
                        for candidate in record["candidates"]
                    ],
                    "missing_labels": (
                        list(rejected_candidate.get("missing_labels", []) or [])
                        if rejected_candidate
                        else []
                    ),
                    "extra_labels": (
                        list(rejected_candidate.get("extra_labels", []) or [])
                        if rejected_candidate
                        else []
                    ),
                    "blocked_repeat_labels": sorted(
                        set(blocked_labels), key=str.casefold
                    ),
                    "volumetric_region_id": record["region_id"],
                    "tetra_count": int(region.get("tetra_count", 0)),
                    "clearance": float(region.get("clearance", 0.0)),
                    "signature": {
                        "target": [],
                        "closest": list(region.get("boundary_labels", []) or []),
                        "exact": False,
                        "volumetric_region": True,
                    },
                }
                payloads.append(payload)
                source_key = payload["source_unit_key"]
                if source_key:
                    rejected_by_unit.setdefault(source_key, []).append(payload)
                continue

            best_quality = filtered_candidates[0]["quality"]
            best_candidates = [
                candidate
                for candidate in filtered_candidates
                if candidate["quality"] == best_quality
            ]
            chosen = min(
                best_candidates,
                key=lambda candidate: (
                    assigned_counts.get(candidate["unit_key"], 0),
                    candidate["polarity"],
                    candidate["feature"].casefold(),
                    candidate["unit_key"].casefold(),
                ),
            )
            assigned_before = assigned_counts.get(chosen["unit_key"], 0)
            topology_peers = [
                candidate
                for candidate in record["candidates"]
                if set(candidate.get("signature_keys", set()))
                == set(chosen.get("signature_keys", set()))
            ]
            ambiguity_group_peers = []
            ambiguity_group_size = int(
                chosen["unit_info"].get("ambiguity_group_size", 1) or 1
            )
            if ambiguity_group_size > 1:
                ambiguity_group = chosen["unit_info"].get("ambiguity_group")
                if ambiguity_group is not None:
                    ambiguity_group_peers = [
                        unit_info
                        for unit_info in mapped_units
                        if unit_info.get("ambiguity_group") == ambiguity_group
                    ]
            topology_is_ambiguous = len(ambiguity_group_peers) > 1 or len(
                {candidate["unit_key"] for candidate in topology_peers}
            ) > 1
            if assigned_before > 0:
                status = "POSSIBLE_REPEAT"
            elif topology_is_ambiguous or len(best_candidates) > 1:
                status = "AMBIGUOUS"
            elif record["pinned"]:
                status = "CERTAIN"
            elif chosen["exact"]:
                status = "CERTAIN"
            else:
                status = "LIKELY"

            candidate_names = []
            display_unit_infos = ambiguity_group_peers or [
                candidate["unit_info"]
                for candidate in (
                    topology_peers if topology_is_ambiguous else best_candidates
                )
            ]
            for unit_info in display_unit_infos:
                name = (
                    self._psc_text(unit_info.get("name", ""))
                    or self._psc_text(unit_info.get("feature", ""))
                    or str(unit_info.get("key", ""))
                )
                if name not in candidate_names:
                    candidate_names.append(name)
            closest_surface_indices = {
                key: int(indices[0])
                for key, indices in (
                    region.get("label_surface_indices", {}) or {}
                ).items()
                if indices
            }
            signature = {
                "target": list(chosen.get("boundaries", []) or []),
                "closest": list(region.get("boundary_labels", []) or []),
                "exact": bool(chosen["exact"]),
                "missing_count": int(chosen["missing_count"]),
                "extra_count": int(chosen["extra_count"]),
                "observed_count": int(chosen["observed_count"]),
                "closest_surface_indices": dict(closest_surface_indices),
                "volumetric_region": True,
                "volumetric_region_id": record["region_id"],
                "tetra_count": int(region.get("tetra_count", 0)),
                "clearance": float(region.get("clearance", 0.0)),
            }
            payload = {
                "status": status,
                "unit_key": chosen["unit_key"],
                "source_unit_key": chosen["unit_key"],
                "seed_point": list(record["seed_point"]),
                "boundaries": list(chosen.get("boundaries", []) or []),
                "candidate_names": candidate_names,
                "missing_labels": list(chosen.get("missing_labels", []) or []),
                "extra_labels": list(chosen.get("extra_labels", []) or []),
                "blocked_repeat_labels": sorted(
                    set(blocked_labels), key=str.casefold
                ),
                "assigned_before": int(assigned_before),
                "exact": bool(chosen["exact"]),
                "local_signature": False,
                "component_index": -1,
                "closest_surface_indices": closest_surface_indices,
                "volumetric_region_id": record["region_id"],
                "tetra_count": int(region.get("tetra_count", 0)),
                "clearance": float(region.get("clearance", 0.0)),
                "signature": signature,
            }
            accepted.append(payload)
            payloads.append(payload)
            assigned_counts[chosen["unit_key"]] = assigned_before + 1

        units_by_key = {
            str(
                unit_info.get("key")
                or unit_info.get("feature")
                or unit_info.get("name")
                or ""
            ): unit_info
            for unit_info in mapped_units or []
        }
        for unit_key, unit_info in units_by_key.items():
            unit_info["seed_points"] = []
            unit_info["seed_point"] = None
            unit_info["seed_topology_signature"] = {}
            unit_info["seed_topology_signatures"] = []
            unit_info["psc_assignments"] = []
            unit_info["psc_rejected_assignments"] = list(
                rejected_by_unit.get(unit_key, [])
            )
        for payload in accepted:
            unit_info = units_by_key.get(payload["unit_key"])
            if unit_info is None:
                continue
            point = list(payload["seed_point"])
            unit_info["seed_points"].append(point)
            unit_info["seed_point"] = unit_info["seed_points"][0]
            unit_info["seed_topology_signatures"].append(
                {
                    "boundaries": list(payload.get("boundaries", []) or []),
                    "signature": dict(payload.get("signature", {}) or {}),
                    "component_index": -1,
                    "assignment": dict(payload),
                }
            )
            unit_info["seed_topology_signature"] = dict(
                unit_info["seed_topology_signatures"][0]["signature"]
            )
            unit_info["psc_assignments"].append(dict(payload))

        status_priority = {
            "CERTAIN": 0,
            "LIKELY": 1,
            "POSSIBLE_REPEAT": 2,
            "AMBIGUOUS": 3,
            "UNASSIGNED": 4,
        }
        for unit_key, unit_info in units_by_key.items():
            statuses = [
                assignment.get("status", "UNASSIGNED")
                for assignment in unit_info.get("psc_assignments", [])
            ]
            if not statuses:
                statuses = ["UNASSIGNED"]
            unit_info["psc_assignment_status"] = max(
                statuses,
                key=lambda value: status_priority.get(value, 4),
            )
        return sorted(
            payloads,
            key=lambda payload: int(payload.get("volumetric_region_id", -1)),
        )

    def _psc_classify_seed_assignments(
        self,
        mapped_units: List[Dict[str, Any]],
        psc_model: Dict[str, Any],
        max_missing_boundaries: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Classify 3D seeds without losing their intended topology signature."""
        if max_missing_boundaries is None:
            max_missing_boundaries = self.MAX_RELAXED_MISSING_BOUNDARIES
        try:
            max_missing_boundaries = max(int(max_missing_boundaries), 0)
        except (TypeError, ValueError):
            max_missing_boundaries = self.MAX_RELAXED_MISSING_BOUNDARIES

        records = []
        for unit_info in mapped_units or []:
            source_unit_key = str(
                unit_info.get("key")
                or unit_info.get("feature")
                or unit_info.get("name")
                or ""
            )
            seed_points = self._psc_normalize_seed_points(
                unit_info.get("seed_points") or unit_info.get("seed_point")
            )
            signature_entries = list(unit_info.get("seed_topology_signatures", []) or [])
            for seed_index, seed_point in enumerate(seed_points):
                entry = signature_entries[seed_index] if seed_index < len(signature_entries) else {}
                signature = dict(entry.get("signature", {}) or {})
                boundaries = list(
                    entry.get("boundaries")
                    or signature.get("target")
                    or unit_info.get("boundaries", [])
                    or []
                )
                observed_labels = list(signature.get("closest", []) or [])
                is_override = bool(unit_info.get("seed_override"))
                if not observed_labels and (is_override or boundaries):
                    # Explicit overrides are authoritative.  The fallback for
                    # legacy generated seeds also keeps their STm signature
                    # instead of allowing a seed to migrate to an unrelated
                    # unit solely because nearest-surface data is absent.
                    observed_labels = list(boundaries)
                    signature.setdefault("target", list(boundaries))
                    signature.setdefault("closest", list(boundaries))
                    signature.setdefault("exact", True)
                closest_indices = {
                    self._psc_key(key): int(value)
                    for key, value in (
                        signature.get("closest_surface_indices", {}) or {}
                    ).items()
                    if self._psc_key(key)
                    and isinstance(value, (int, np.integer))
                }
                # Repeat-adjacency checks need all surfaces in the intended
                # signature, including a representative surface omitted from
                # a partial observed signature and Boundary in mixed
                # surface+Boundary signatures.
                required_closest_labels = list(observed_labels)
                required_closest_labels.extend(boundaries)
                required_indices = self._psc_closest_surface_indices_for_point(
                    seed_point,
                    required_closest_labels,
                )
                required_indices.update(closest_indices)
                closest_indices = required_indices

                source_candidate = {
                    "unit_info": unit_info,
                    "unit_key": source_unit_key,
                    "component_index": int(entry.get("component_index", -1)),
                    "is_local": {
                        self._psc_key(label)
                        for label in boundaries
                        if self._psc_key(label)
                    }
                    != {
                        self._psc_key(label)
                        for label in unit_info.get("boundaries", []) or []
                        if self._psc_key(label)
                    },
                    "boundaries": list(boundaries),
                    "signature_keys": {
                        self._psc_key(label)
                        for label in boundaries
                        if self._psc_key(label)
                    },
                    "polarity": self._psc_sort_key(unit_info.get("polarity", "")),
                    "feature": self._psc_text(unit_info.get("feature", "")),
                }

                if is_override or unit_info.get("psc_virtual_unit") or not boundaries:
                    candidates = [source_candidate]
                else:
                    # Candidate ownership comes from the intended global/local
                    # STm signature.  Nearest-surface observations only score
                    # that candidate pool; they must not redirect an Int1 seed,
                    # for example, to an unrelated Top unit.
                    candidates = self._psc_unit_candidates_for_topology_signature(
                        mapped_units,
                        boundaries,
                        max_missing_boundaries=0,
                    )
                    if not any(
                        candidate.get("unit_key") == source_unit_key
                        and set(candidate.get("signature_keys", set()))
                        == set(source_candidate["signature_keys"])
                        for candidate in candidates
                    ):
                        candidates.append(source_candidate)

                scored_candidates = []
                for candidate in candidates:
                    scored = self._psc_candidate_observation_quality(
                        candidate,
                        observed_labels,
                    )
                    if is_override:
                        scored.update(
                            {
                                "exact": True,
                                "missing_count": 0,
                                "missing_labels": [],
                                "extra_count": 0,
                                "extra_labels": [],
                            }
                        )
                    if (
                        int(scored.get("extra_count", 0)) > 0
                        or int(scored.get("missing_count", 0))
                        > max_missing_boundaries
                    ):
                        continue
                    scored_candidates.append(scored)
                candidates = sorted(
                    scored_candidates,
                    key=lambda candidate: (
                        0 if candidate.get("exact") else 1,
                        int(candidate.get("missing_count", 0)),
                        int(candidate.get("extra_count", 0)),
                        -int(candidate.get("observed_count", 0)),
                        float(candidate.get("polarity", float("inf"))),
                        str(candidate.get("feature", "")).casefold(),
                        str(candidate.get("unit_key", "")).casefold(),
                    ),
                )
                best_quality = (2, 10**9, 10**9, 0)
                if candidates:
                    best_quality = (
                        0 if candidates[0].get("exact") else 1,
                        int(candidates[0].get("missing_count", 0)),
                        int(candidates[0].get("extra_count", 0)),
                        -int(candidates[0].get("observed_count", 0)),
                    )
                records.append(
                    {
                        "source_unit_key": source_unit_key,
                        "seed_index": seed_index,
                        "seed_point": list(seed_point),
                        "signature": signature,
                        "boundaries": boundaries,
                        "observed_labels": observed_labels,
                        "closest_surface_indices": closest_indices,
                        "candidates": candidates,
                        "best_quality": best_quality,
                        "seed_override": is_override,
                    }
                )

        records.sort(
            key=lambda record: (
                record["best_quality"],
                tuple(round(float(value), 8) for value in record["seed_point"]),
                record["source_unit_key"].casefold(),
                int(record["seed_index"]),
            )
        )

        assigned_counts = {}
        accepted = []
        rejected_by_source = {}
        payloads = []
        for record in records:
            filtered_candidates = []
            blocked_labels = []
            for candidate in record["candidates"]:
                conflict_labels = self._psc_repeat_conflict_labels(
                    unit_key=candidate["unit_key"],
                    seed_point=record["seed_point"],
                    closest_surface_indices=record["closest_surface_indices"],
                    assignments=accepted,
                    psc_model=psc_model,
                )
                if conflict_labels:
                    blocked_labels.extend(conflict_labels)
                    continue
                filtered_candidates.append(candidate)

            if not filtered_candidates:
                payload = {
                    "status": "UNASSIGNED",
                    "unit_key": "",
                    "source_unit_key": record["source_unit_key"],
                    "seed_point": list(record["seed_point"]),
                    "candidate_names": [],
                    "missing_labels": [],
                    "blocked_repeat_labels": sorted(
                        set(blocked_labels), key=str.casefold
                    ),
                    "closest_surface_indices": dict(
                        record["closest_surface_indices"]
                    ),
                    "signature": dict(record["signature"]),
                }
                payloads.append(payload)
                rejected_by_source.setdefault(record["source_unit_key"], []).append(payload)
                continue

            best_candidate = filtered_candidates[0]
            best_quality = (
                0 if best_candidate.get("exact") else 1,
                int(best_candidate.get("missing_count", 0)),
                int(best_candidate.get("extra_count", 0)),
                -int(best_candidate.get("observed_count", 0)),
            )
            best_candidates = [
                candidate
                for candidate in filtered_candidates
                if (
                    0 if candidate.get("exact") else 1,
                    int(candidate.get("missing_count", 0)),
                    int(candidate.get("extra_count", 0)),
                    -int(candidate.get("observed_count", 0)),
                )
                == best_quality
            ]
            chosen = min(
                best_candidates,
                key=lambda candidate: (
                    assigned_counts.get(candidate["unit_key"], 0),
                    float(candidate.get("polarity", float("inf"))),
                    str(candidate.get("feature", "")).casefold(),
                    str(candidate.get("unit_key", "")).casefold(),
                ),
            )
            assigned_before = assigned_counts.get(chosen["unit_key"], 0)
            if record.get("seed_override") and assigned_before == 0:
                status = "CERTAIN"
            elif len(best_candidates) > 1 and assigned_before == 0:
                status = "AMBIGUOUS"
            elif assigned_before > 0:
                status = "POSSIBLE_REPEAT"
            elif chosen.get("exact"):
                status = "CERTAIN"
            else:
                status = "LIKELY"

            candidate_names = []
            for candidate in best_candidates:
                name = (
                    self._psc_text(candidate["unit_info"].get("name", ""))
                    or self._psc_text(candidate["unit_info"].get("feature", ""))
                    or candidate["unit_key"]
                )
                if candidate.get("is_local"):
                    name = f"{name} (local signature)"
                if name not in candidate_names:
                    candidate_names.append(name)

            payload = {
                "status": status,
                "unit_key": chosen["unit_key"],
                "source_unit_key": record["source_unit_key"],
                "seed_point": list(record["seed_point"]),
                "boundaries": list(chosen.get("boundaries", []) or []),
                "candidate_names": candidate_names,
                "missing_labels": list(chosen.get("missing_labels", []) or []),
                "extra_labels": list(chosen.get("extra_labels", []) or []),
                "blocked_repeat_labels": sorted(
                    set(blocked_labels), key=str.casefold
                ),
                "assigned_before": int(assigned_before),
                "exact": bool(chosen.get("exact")),
                "local_signature": bool(chosen.get("is_local")),
                "component_index": int(chosen.get("component_index", -1)),
                "closest_surface_indices": dict(record["closest_surface_indices"]),
                "signature": dict(record["signature"]),
            }
            accepted.append(payload)
            payloads.append(payload)
            assigned_counts[chosen["unit_key"]] = assigned_before + 1

        units_by_key = {
            str(
                unit_info.get("key")
                or unit_info.get("feature")
                or unit_info.get("name")
                or ""
            ): unit_info
            for unit_info in mapped_units or []
        }
        for unit_key, unit_info in units_by_key.items():
            unit_info["seed_points"] = []
            unit_info["seed_point"] = None
            unit_info["seed_topology_signature"] = {}
            unit_info["seed_topology_signatures"] = []
            unit_info["psc_assignments"] = []
            unit_info["psc_rejected_assignments"] = list(
                rejected_by_source.get(unit_key, [])
            )

        for payload in accepted:
            unit_info = units_by_key.get(payload["unit_key"])
            if unit_info is None:
                continue
            point = list(payload["seed_point"])
            unit_info["seed_points"].append(point)
            unit_info["seed_point"] = unit_info["seed_points"][0]
            unit_info["seed_topology_signatures"].append(
                {
                    "boundaries": list(payload.get("boundaries", []) or []),
                    "signature": dict(payload.get("signature", {}) or {}),
                    "assignment": dict(payload),
                }
            )
            unit_info["seed_topology_signature"] = dict(
                unit_info["seed_topology_signatures"][0].get("signature", {})
            )
            unit_info["psc_assignments"].append(dict(payload))

        status_priority = {
            "CERTAIN": 0,
            "LIKELY": 1,
            "POSSIBLE_REPEAT": 2,
            "AMBIGUOUS": 3,
            "UNASSIGNED": 4,
        }
        for unit_key, unit_info in units_by_key.items():
            statuses = [
                assignment.get("status", "UNASSIGNED")
                for assignment in unit_info.get("psc_assignments", [])
            ]
            statuses.extend(
                assignment.get("status", "UNASSIGNED")
                for assignment in unit_info.get("psc_rejected_assignments", [])
            )
            if not statuses:
                statuses = ["UNASSIGNED"]
            unit_info["psc_assignment_status"] = max(
                statuses,
                key=lambda status: status_priority.get(status, 4),
            )
        return payloads
    
    @staticmethod
    def _psc_key(value: Any) -> str:
        """Return a normalized key for STm/PyMeshIt feature matching."""
        if value is None:
            return ""
        try:
            if np.isscalar(value) and bool(np.isnan(value)):
                return ""
        except (TypeError, ValueError):
            pass
        text = str(value).strip()
        if text.casefold() in {"nan", "nat", "<na>", "none"}:
            return ""
        return re.sub(r"\s+", " ", text).casefold()
    
    @staticmethod
    def _psc_text(value: Any) -> str:
        """Return clean display text for STm values, treating NaN as empty."""
        if value is None:
            return ""
        try:
            if np.isscalar(value) and bool(np.isnan(value)):
                return ""
        except (TypeError, ValueError):
            pass
        text = str(value).strip()
        return "" if text.casefold() in {"nan", "nat", "<na>", "none"} else text

    def _psc_feature_is_eroded(self, value: Any) -> bool:
        """Return True when a feature name uses the PSC eroded suffix."""
        return self._psc_key(value).endswith("_eroded")

    def _psc_unit_role(self, value: Any, default: str = "TU") -> str:
        """Return a canonical STm unit role for PSC outputs."""
        role = self._psc_text(value).upper()
        return role if role in self.SECTION_SEED_ROLES else default

    @staticmethod
    def _psc_sort_key(value: Any) -> float:
        """Return a numeric STm polarity key."""
        try:
            return float(value)
        except (TypeError, ValueError):
            return float("inf")
    
    def _build_psc_model_from_stm(self, table_name: str) -> Dict[str, Any]:
        """Read the canonical Boundaries and Units tables from an STm model."""
        project = self._pzero_project()
        if project is None:
            return {"units": {}, "boundary_features": set(), "boundary_order": []}
        options = getattr(project, "custom_table_options", {}).get(table_name, {}) or {}
        stm_tables = options.get("stm_tables", {})
        if not isinstance(stm_tables, dict):
            return {"units": {}, "boundary_features": set(), "boundary_order": []}

        boundary_records = list(stm_tables.get("boundaries", []) or [])
        unit_records = list(stm_tables.get("units", []) or [])
        model_boundary_records = [
            boundary_info
            for boundary_info in boundary_records
            if isinstance(boundary_info, dict)
            and self._psc_key(boundary_info.get("Role", ""))
            == self._psc_key("model_boundary")
        ]
        model_boundary_feature = self._psc_text(
            model_boundary_records[0].get("Feature", "")
            if model_boundary_records
            else ""
        )
        model_boundary_keys = {
            self._psc_key(boundary_info.get("Feature", ""))
            for boundary_info in model_boundary_records
            if self._psc_key(boundary_info.get("Feature", ""))
        }
        model_boundary_source = options.get("stm_model_boundary_source", {}) or {}
        model_boundary_uid = self._psc_text(model_boundary_source.get("uid", ""))

        def boundary_name(value: Any) -> str:
            name = self._psc_text(value)
            if (
                self._psc_key(name) in model_boundary_keys
                or self._psc_key(name) == self._psc_key("Model Boundary")
            ):
                return "Boundary"
            return name

        representative_by_unit = {}
        for link in options.get("stm_representative_links", []) or []:
            if not isinstance(link, dict):
                continue
            unit_name = self._psc_text(link.get("unit", ""))
            representative = boundary_name(link.get("boundary", ""))
            if unit_name and representative:
                representative_by_unit[unit_name] = representative
        for unit_info in unit_records:
            if not isinstance(unit_info, dict):
                continue
            unit_name = self._psc_text(unit_info.get("Feature", ""))
            representative = boundary_name(
                unit_info.get("Representative Boundary", "")
            )
            if unit_name and representative:
                representative_by_unit[unit_name] = representative

        representative_boundary_keys = {
            self._psc_key(representative)
            for representative in representative_by_unit.values()
            if self._psc_key(representative)
            != self._psc_key("Boundary")
        }
        units: Dict[str, Dict[str, Any]] = {}
        boundary_features = set()
        boundary_order = []
        boundary_roles = {}

        for boundary_info in boundary_records:
            if not isinstance(boundary_info, dict):
                continue
            feature = boundary_name(boundary_info.get("Feature", ""))
            if not feature:
                continue
            feature_key = self._psc_key(feature)
            boundary_features.add(feature)
            boundary_roles.setdefault(
                feature_key,
                self._psc_text(boundary_info.get("Role", "")),
            )
            boundary_order.append(
                {
                    "feature": feature,
                    "role": self._psc_text(boundary_info.get("Role", "")),
                    "polarity": self._psc_sort_key(
                        boundary_info.get("Polarity", "")
                    ),
                    "row_index": len(boundary_order),
                    "is_representative": feature_key
                    in representative_boundary_keys,
                }
            )

        for unit_idx, unit_info in enumerate(unit_records):
            if not isinstance(unit_info, dict):
                continue
            feature = self._psc_text(unit_info.get("Feature", ""))
            if not feature:
                continue
            raw_boundaries = unit_info.get("Boundaries", [])
            if isinstance(raw_boundaries, str):
                raw_boundaries = raw_boundaries.split(",")
            boundaries = {
                boundary_name(value)
                for value in (raw_boundaries or [])
                if boundary_name(value)
            }
            representative = representative_by_unit.get(feature, "")
            if representative:
                boundaries.add(representative)
            domain_items = [
                (column_name, value)
                for column_name, value in unit_info.items()
                if re.fullmatch(r"Domain(?:_\d+)?", str(column_name))
            ]
            domains = [
                self._psc_text(value)
                for column_name, value in sorted(
                    domain_items,
                    key=lambda item: int(
                        str(item[0]).split("_", 1)[1]
                        if "_" in str(item[0])
                        else 1
                    ),
                )
                if self._psc_text(value)
            ]
            unit_key = f"unit:stm:{unit_idx}:{feature}"
            units[unit_key] = {
                "key": unit_key,
                "name": feature,
                "feature": feature,
                "unit_role": self._psc_unit_role(
                    unit_info.get("Unit Role", "TU")
                ),
                "polarity": self._psc_sort_key(unit_info.get("Polarity", "")),
                "domains": domains,
                "boundaries": boundaries,
                "representative_boundary": representative,
                "source": "stm",
            }
            for color_name in ("color_R", "color_G", "color_B"):
                if color_name in unit_info:
                    units[unit_key][color_name] = unit_info[color_name]
            boundary_features.update(boundaries)

        self._psc_active_boundary_roles = boundary_roles
        return {
            "table_name": table_name,
            "units": units,
            "boundary_features": boundary_features,
            "boundary_order": boundary_order,
            "boundary_roles": boundary_roles,
            "representative_boundary_keys": representative_boundary_keys,
            "model_boundary_feature": model_boundary_feature,
            "model_boundary_uid": model_boundary_uid,
        }
    
    def _map_psc_boundaries_to_tetra_surfaces(self, psc_model: Dict[str, Any]) -> Dict[str, Any]:
        """Map PSC boundary features to loaded tetra-surface metadata."""
        feature_to_surfaces: Dict[str, List[Dict[str, Any]]] = {}
        boundary_surface_entries = []
        boundary_roles = dict(psc_model.get("boundary_roles", {}) or {})
        self._psc_active_boundary_roles = boundary_roles
        self._psc_active_model_boundary_feature = self._psc_text(
            psc_model.get("model_boundary_feature", "")
        )
        self._psc_active_model_boundary_uid = self._psc_text(
            psc_model.get("model_boundary_uid", "")
        )
        try:
            border_indices = set(self._get_border_surface_indices())
        except Exception:
            border_indices = set()
    
        for surface_idx, surface_info in getattr(self, "tetra_surface_data", {}).items():
            try:
                surface_idx_value = int(surface_idx)
            except (TypeError, ValueError):
                surface_idx_value = surface_idx
            label = surface_info.get("name", f"Surface_{surface_idx}")
            entry = {
                "index": surface_idx_value,
                "label": label,
                "feature": str(surface_info.get("feature", "")).strip(),
                "name": str(surface_info.get("name", "")).strip(),
                "role": str(surface_info.get("role", "")).strip(),
                "uid": str(surface_info.get("uid", "")).strip(),
            }
            feature = str(surface_info.get("feature", "")).strip()
            if feature:
                feature_to_surfaces.setdefault(self._psc_key(feature), []).append(entry)
            fallback_name = str(surface_info.get("name", "")).strip()
            if fallback_name:
                feature_to_surfaces.setdefault(self._psc_key(fallback_name), []).append(entry)
            identity_text = " ".join(
                str(surface_info.get(field, "") or "").casefold()
                for field in ("name", "feature")
            )
            if surface_idx_value in border_indices or any(
                token in identity_text for token in ("border", "boundary", "outer")
            ):
                boundary_surface_entries.append(entry)

        preferred_model_entries = []
        if self._psc_active_model_boundary_uid:
            preferred_model_entries = [
                entry
                for entries in feature_to_surfaces.values()
                for entry in entries
                if self._psc_key(entry.get("uid", ""))
                == self._psc_key(self._psc_active_model_boundary_uid)
            ]
        if not preferred_model_entries and self._psc_active_model_boundary_feature:
            preferred_model_entries = feature_to_surfaces.get(
                self._psc_key(self._psc_active_model_boundary_feature), []
            )
        if preferred_model_entries:
            boundary_surface_entries = list(
                {
                    entry.get("index"): entry
                    for entry in preferred_model_entries
                    if entry.get("index") is not None
                }.values()
            )
    
        mapped_units = []
        for unit in psc_model.get("units", {}).values():
            boundaries = sorted(unit.get("boundaries", set()), key=lambda value: str(value).casefold())
            matched_surfaces = []
            matched_surface_indices = []
            model_boundary_indices = []
            boundary_surface_indices = {}
            missing_boundaries = []
            for boundary in boundaries:
                if self._psc_key(boundary) == self._psc_key("Boundary"):
                    matches = list(boundary_surface_entries)
                else:
                    matches = feature_to_surfaces.get(self._psc_key(boundary), [])
                    expected_role = self._psc_key(
                        boundary_roles.get(self._psc_key(boundary), "")
                    )
                    role_matches = [
                        entry
                        for entry in matches
                        if expected_role
                        and self._psc_key(entry.get("role", ""))
                        == expected_role
                    ]
                    if expected_role:
                        matches = role_matches or [
                            entry
                            for entry in matches
                            if not self._psc_key(entry.get("role", ""))
                        ]
                if matches:
                    boundary_surface_indices[boundary] = [
                        entry["index"] for entry in matches if entry.get("index") is not None
                    ]
                    matched_surfaces.extend([entry["label"] for entry in matches])
                    if self._psc_key(boundary) == self._psc_key("Boundary"):
                        model_boundary_indices.extend(boundary_surface_indices[boundary])
                    else:
                        matched_surface_indices.extend(boundary_surface_indices[boundary])
                else:
                    missing_boundaries.append(boundary)
            mapped_units.append(
                {
                    "key": unit.get("key", ""),
                    "name": unit.get("name", ""),
                    "feature": unit.get("feature", ""),
                    "unit_role": self._psc_unit_role(
                        unit.get("unit_role", "TU")
                    ),
                    "polarity": unit.get("polarity", float("inf")),
                    "domains": list(unit.get("domains", [])),
                    "boundaries": boundaries,
                    "representative_boundary": unit.get(
                        "representative_boundary", ""
                    ),
                    "matched_surfaces": sorted(set(matched_surfaces), key=str.casefold),
                    "matched_surface_indices": sorted(set(matched_surface_indices), key=lambda value: str(value)),
                    "model_boundary_indices": sorted(set(model_boundary_indices), key=lambda value: str(value)),
                    "boundary_surface_indices": boundary_surface_indices,
                    "missing_boundaries": missing_boundaries,
                    "source": unit.get("source", ""),
                }
            )
            for color_name in ("color_R", "color_G", "color_B"):
                if color_name in unit:
                    mapped_units[-1][color_name] = unit[color_name]
    
        mapped_units = sorted(
            mapped_units,
            key=lambda item: str(item.get("feature", "")).casefold(),
        )
        for group_idx, group in enumerate(self._psc_ambiguity_groups(mapped_units)):
            ordered_group = sorted(
                group,
                key=lambda item: (
                    str(item.get("name", "")).casefold(),
                    str(item.get("key", "")).casefold(),
                ),
            )
            for unit_idx, unit_info in enumerate(ordered_group):
                unit_info["ambiguity_group"] = group_idx
                unit_info["ambiguity_group_index"] = unit_idx
                unit_info["ambiguity_group_size"] = len(ordered_group)
    
        return {
            "table_name": psc_model.get("table_name", ""),
            "units": mapped_units,
        }
    
    def _psc_surface_indices_for_boundary(self, boundary_feature: str) -> List[int]:
        """Return surfaces matching an STm Feature and, when available, Role."""
        key = self._psc_key(boundary_feature)
        expected_role = self._psc_key(
            (getattr(self, "_psc_active_boundary_roles", {}) or {}).get(
                key, ""
            )
        )
        try:
            border_indices = set(self._get_border_surface_indices())
        except Exception:
            border_indices = set()
    
        matches = []
        role_matches = []
        roleless_matches = []
        model_uid = self._psc_key(
            getattr(self, "_psc_active_model_boundary_uid", "")
        )
        model_feature = self._psc_key(
            getattr(self, "_psc_active_model_boundary_feature", "")
        )
        model_uid_matches = []
        model_feature_matches = []
        for surface_idx, surface_info in getattr(self, "tetra_surface_data", {}).items():
            try:
                surface_idx_value = int(surface_idx)
            except (TypeError, ValueError):
                continue
    
            if key == self._psc_key("Boundary"):
                surface_uid = self._psc_key(surface_info.get("uid", ""))
                surface_keys = {
                    self._psc_key(surface_info.get("name", "")),
                    self._psc_key(surface_info.get("feature", "")),
                }
                if model_uid and surface_uid == model_uid:
                    model_uid_matches.append(surface_idx_value)
                if model_feature and model_feature in surface_keys:
                    model_feature_matches.append(surface_idx_value)
                identity_text = " ".join(
                    str(surface_info.get(field, "") or "").casefold()
                    for field in ("name", "feature")
                )
                if surface_idx_value in border_indices or any(
                    token in identity_text for token in ("border", "boundary", "outer")
                ):
                    matches.append(surface_idx_value)
                continue
    
            feature = surface_info.get("feature", "")
            name = surface_info.get("name", "")
            if key in {self._psc_key(feature), self._psc_key(name)}:
                matches.append(surface_idx_value)
                if (
                    expected_role
                    and self._psc_key(surface_info.get("role", ""))
                    == expected_role
                ):
                    role_matches.append(surface_idx_value)
                elif expected_role and not self._psc_key(
                    surface_info.get("role", "")
                ):
                    roleless_matches.append(surface_idx_value)
    
        if key == self._psc_key("Boundary"):
            preferred_matches = model_uid_matches or model_feature_matches
            if preferred_matches:
                return sorted(set(preferred_matches))
        selected = matches
        if expected_role:
            selected = role_matches or roleless_matches
        return sorted(set(selected))
    
    def _psc_adjacent_boundary_surface_indices(
        self,
        unit_info: Dict[str, Any],
        psc_model: Dict[str, Any],
        preferred_direction: int = 1,
    ) -> Tuple[List[int], str]:
        """Find the nearest non-owned STM boundary surface for a one-sided unit."""
        unit_key = self._psc_key(unit_info.get("feature", ""))
        current_indices = self._psc_structural_surface_indices_for_unit(unit_info)
        if not current_indices and unit_key:
            current_indices = self._psc_surface_indices_for_boundary(unit_info.get("feature", ""))
        current_centroids = [
            self._psc_surface_centroid(surface_idx)
            for surface_idx in current_indices
        ]
        current_centroids = [centroid for centroid in current_centroids if centroid is not None]
        if current_centroids:
            reference_point = np.mean(np.asarray(current_centroids, dtype=float), axis=0)
        else:
            bounds = self._psc_domain_bounds()
            reference_point = (
                (bounds[0] + bounds[1]) / 2.0
                if bounds is not None
                else np.zeros(3, dtype=float)
            )
    
        candidates = []
        for feature in psc_model.get("boundary_features", set()) or []:
            feature_key = self._psc_key(feature)
            if not feature_key or feature_key in {unit_key, self._psc_key("Boundary")}:
                continue
            indices = self._psc_surface_indices_for_boundary(feature)
            centroids = [
                self._psc_surface_centroid(surface_idx)
                for surface_idx in indices
            ]
            centroids = [centroid for centroid in centroids if centroid is not None]
            if not centroids:
                continue
            candidate_point = np.mean(np.asarray(centroids, dtype=float), axis=0)
            distance = float(np.linalg.norm(candidate_point - reference_point))
            candidates.append((distance, str(feature), indices))
    
        if not candidates:
            return [], ""
        candidates.sort(key=lambda item: (item[0], item[1].casefold()))
        _, feature, indices = candidates[0]
        return indices, feature
    
    def _psc_domain_bounds(self) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        """Return min/max XYZ bounds of the loaded PLC surfaces."""
        point_sets = []
        for surface_info in getattr(self, "tetra_surface_data", {}).values():
            vertices = np.asarray(surface_info.get("vertices", []), dtype=float)
            if vertices.ndim == 2 and vertices.shape[0] > 0 and vertices.shape[1] >= 3:
                point_sets.append(vertices[:, :3])
        if not point_sets:
            return None
        points = np.vstack(point_sets)
        return np.min(points, axis=0), np.max(points, axis=0)
    
    def _psc_domain_axis_bounds(
        self,
        axis: np.ndarray,
    ) -> Optional[Tuple[float, float]]:
        """Return min/max projection of loaded PLC points onto an axis."""
        point_sets = []
        for surface_info in getattr(self, "tetra_surface_data", {}).values():
            vertices = np.asarray(surface_info.get("vertices", []), dtype=float)
            if vertices.ndim == 2 and vertices.shape[0] > 0 and vertices.shape[1] >= 3:
                point_sets.append(vertices[:, :3])
        if not point_sets:
            return None
        projections = np.vstack(point_sets).dot(axis)
        return float(np.min(projections)), float(np.max(projections))
    
    def _psc_surface_vertices(self, surface_idx: int) -> np.ndarray:
        """Return loaded PLC vertices for one tetra surface."""
        surface_info = getattr(self, "tetra_surface_data", {}).get(surface_idx)
        if surface_info is None:
            return np.empty((0, 3), dtype=float)
        vertices = np.asarray(surface_info.get("vertices", []), dtype=float)
        if vertices.ndim != 2 or vertices.shape[0] == 0 or vertices.shape[1] < 3:
            return np.empty((0, 3), dtype=float)
        return vertices[:, :3]
    
    def _psc_surface_normal(self, surface_idx: int) -> Optional[np.ndarray]:
        """Estimate a stable normal for a loaded PLC surface."""
        vertices = self._psc_surface_vertices(surface_idx)
        if vertices.shape[0] < 3:
            return None
        centroid = np.mean(vertices, axis=0)
        try:
            _, _, vh = np.linalg.svd(vertices - centroid, full_matrices=False)
        except np.linalg.LinAlgError:
            return None
        if vh.shape[0] < 3:
            return None
        normal = np.asarray(vh[-1], dtype=float)
        norm = np.linalg.norm(normal)
        if norm <= 1e-12:
            return None
        return normal / norm
    
    def _psc_surface_centroid(self, surface_idx: int) -> Optional[np.ndarray]:
        """Return the centroid of one loaded PLC surface."""
        vertices = self._psc_surface_vertices(surface_idx)
        if vertices.shape[0] == 0:
            return None
        return np.mean(vertices, axis=0)
    
    def _psc_stacking_axis(self, psc_model: Dict[str, Any]) -> np.ndarray:
        """Estimate a geometric search axis without using STm structural polarity."""
        centroids = []
        normals = []
        for feature in psc_model.get("boundary_features", set()) or []:
            if self._psc_key(feature) == self._psc_key("Boundary"):
                continue
            surface_indices = self._psc_surface_indices_for_boundary(feature)
            feature_centroids = [
                self._psc_surface_centroid(surface_idx)
                for surface_idx in surface_indices
            ]
            feature_centroids = [
                centroid for centroid in feature_centroids if centroid is not None
            ]
            if feature_centroids:
                centroids.append(np.mean(np.asarray(feature_centroids), axis=0))
            for surface_idx in surface_indices:
                normal = self._psc_surface_normal(surface_idx)
                if normal is not None:
                    normals.append(normal)
    
        if len(centroids) >= 2:
            centered = np.asarray(centroids, dtype=float) - np.mean(centroids, axis=0)
            try:
                _, _, vh = np.linalg.svd(centered, full_matrices=False)
                axis = vh[0]
                norm = np.linalg.norm(axis)
                if norm > 1e-12:
                    return axis / norm
            except np.linalg.LinAlgError:
                pass
    
        if normals:
            reference = np.asarray(normals[0], dtype=float)
            aligned = []
            for normal in normals:
                normal = np.asarray(normal, dtype=float)
                aligned.append(normal if float(np.dot(normal, reference)) >= 0.0 else -normal)
            axis = np.mean(np.asarray(aligned), axis=0)
            norm = np.linalg.norm(axis)
            if norm > 1e-12:
                return axis / norm
    
        return np.array([0.0, 0.0, 1.0], dtype=float)
    
    def _psc_surface_point_on_axis(
        self,
        surface_idx: int,
        line_origin: np.ndarray,
        axis: np.ndarray,
    ) -> Optional[np.ndarray]:
        """Intersect the stacking-axis line with a surface best-fit plane."""
        vertices = self._psc_surface_vertices(surface_idx)
        if vertices.shape[0] == 0:
            return None
    
        centroid = np.mean(vertices, axis=0)
        normal = self._psc_surface_normal(surface_idx)
        if normal is not None:
            denominator = float(np.dot(normal, axis))
            if abs(denominator) > 1e-8:
                t_value = float(np.dot(centroid - line_origin, normal) / denominator)
                point = line_origin + axis * t_value
                if np.all(np.isfinite(point)):
                    return point
    
        if abs(float(axis[2])) > 0.5:
            return self._psc_surface_reference_point(surface_idx, sample_xy=line_origin[:2])
        return centroid
    
    def _psc_surface_reference_point(
        self,
        surface_idx: int,
        sample_xy: Optional[np.ndarray] = None,
    ) -> Optional[np.ndarray]:
        """Return a representative point on a PLC surface near the requested XY."""
        vertices = self._psc_surface_vertices(surface_idx)
        if vertices.shape[0] == 0:
            return None
    
        centroid = np.mean(vertices, axis=0)
        if sample_xy is None:
            return centroid
    
        normal = self._psc_surface_normal(surface_idx)
        if normal is not None and abs(float(normal[2])) > 1e-8:
            z_value = centroid[2] - (
                normal[0] * (sample_xy[0] - centroid[0])
                + normal[1] * (sample_xy[1] - centroid[1])
            ) / normal[2]
            z_min = float(np.min(vertices[:, 2]))
            z_max = float(np.max(vertices[:, 2]))
            pad = max((z_max - z_min) * 0.25, 1e-6)
            if np.isfinite(z_value) and z_min - pad <= z_value <= z_max + pad:
                return np.array([float(sample_xy[0]), float(sample_xy[1]), float(z_value)])
    
        xy_distances = np.linalg.norm(vertices[:, :2] - sample_xy[:2], axis=1)
        if xy_distances.size:
            return vertices[int(np.argmin(xy_distances))]
        return centroid
    
    @staticmethod
    def _psc_clamp_seed_to_bounds(
        point: np.ndarray,
        bounds: Optional[Tuple[np.ndarray, np.ndarray]],
    ) -> np.ndarray:
        """Keep a generated seed inside the loaded PLC bounding box."""
        if bounds is None:
            return point
        bounds_min, bounds_max = bounds
        span = bounds_max - bounds_min
        margin = np.maximum(span * 1e-4, 1e-6)
        lower = np.where(span > 0.0, bounds_min + margin, bounds_min)
        upper = np.where(span > 0.0, bounds_max - margin, bounds_max)
        return np.minimum(np.maximum(point, lower), upper)
    
    def _psc_move_seed_off_boundaries(
        self,
        seed: np.ndarray,
        surface_indices: List[int],
        bounds: Optional[Tuple[np.ndarray, np.ndarray]],
    ) -> np.ndarray:
        """Nudge a material seed away from the exact boundary surfaces."""
        if bounds is None:
            return seed
        bounds_min, bounds_max = bounds
        diagonal = float(np.linalg.norm(bounds_max - bounds_min))
        clearance = max(diagonal * 0.01, 1e-6)
        adjusted = np.asarray(seed, dtype=float).copy()
    
        for surface_idx in surface_indices:
            vertices = self._psc_surface_vertices(surface_idx)
            normal = self._psc_surface_normal(surface_idx)
            if vertices.shape[0] == 0 or normal is None:
                continue
            centroid = np.mean(vertices, axis=0)
            signed_distance = float(np.dot(adjusted - centroid, normal))
            if abs(signed_distance) >= clearance:
                continue
            direction = 1.0 if signed_distance >= 0.0 else -1.0
            if abs(signed_distance) < 1e-12:
                center_vector = adjusted - ((bounds_min + bounds_max) / 2.0)
                direction = 1.0 if np.dot(center_vector, normal) >= 0.0 else -1.0
            adjusted += normal * direction * (clearance - abs(signed_distance))
    
        return self._psc_clamp_seed_to_bounds(adjusted, bounds)
    
    def _psc_surface_label(self, surface_idx: int) -> str:
        """Return a concise label for a loaded tetra surface."""
        surface_info = getattr(self, "tetra_surface_data", {}).get(surface_idx, {}) or {}
        label = surface_info.get("name") or surface_info.get("feature") or f"Surface_{surface_idx}"
        return f"{surface_idx}:{label}"
    
    def _psc_surface_triangles(self, surface_idx: int) -> np.ndarray:
        """Return triangle indices for one loaded PLC surface."""
        surface_info = getattr(self, "tetra_surface_data", {}).get(surface_idx)
        if surface_info is None:
            return np.empty((0, 3), dtype=int)
        triangles = np.asarray(surface_info.get("triangles", []), dtype=int)
        if triangles.ndim != 2 or triangles.shape[0] == 0 or triangles.shape[1] < 3:
            return np.empty((0, 3), dtype=int)
        return triangles[:, :3]
    
    def _psc_surface_polydata(self, surface_idx: int):
        """Build/cache a PyVista mesh for distance queries against one PLC surface."""
        surface_info = getattr(self, "tetra_surface_data", {}).get(surface_idx)
        if surface_info is None:
            return None
        vertices = self._psc_surface_vertices(surface_idx)
        triangles = self._psc_surface_triangles(surface_idx)
        if vertices.shape[0] == 0:
            return None
    
        signature = (
            id(surface_info.get("vertices", None)),
            id(surface_info.get("triangles", None)),
            tuple(vertices.shape),
            tuple(triangles.shape),
        )
        cache = getattr(self, "_psc_surface_polydata_cache", {})
        cached = cache.get(surface_idx)
        if cached and cached[0] == signature:
            return cached[1]
    
        try:
            if triangles.shape[0] > 0:
                faces = np.empty((triangles.shape[0], 4), dtype=np.int64)
                faces[:, 0] = 3
                faces[:, 1:] = triangles[:, :3]
                mesh = pv.PolyData(vertices, faces.ravel())
            else:
                mesh = pv.PolyData(vertices)
        except Exception:
            return None
    
        cache[surface_idx] = (signature, mesh)
        self._psc_surface_polydata_cache = cache
        return mesh
    
    def _psc_model_boundary_polydata(self):
        """Build/cache a combined PolyData for the loaded model Boundary surfaces."""
        boundary_indices = [
            int(surface_idx)
            for surface_idx in self._psc_surface_indices_for_boundary("Boundary")
            if self._psc_surface_vertices(int(surface_idx)).shape[0] > 0
        ]
        if not boundary_indices:
            return None
    
        signature_parts = []
        for surface_idx in boundary_indices:
            surface_info = getattr(self, "tetra_surface_data", {}).get(surface_idx, {}) or {}
            vertices = self._psc_surface_vertices(surface_idx)
            triangles = self._psc_surface_triangles(surface_idx)
            signature_parts.append(
                (
                    surface_idx,
                    id(surface_info.get("vertices", None)),
                    id(surface_info.get("triangles", None)),
                    tuple(vertices.shape),
                    tuple(triangles.shape),
                )
            )
        signature = tuple(signature_parts)
        cached = getattr(self, "_psc_model_boundary_polydata_cache", None)
        if cached and cached[0] == signature:
            return cached[1]
    
        all_vertices = []
        all_faces = []
        vertex_offset = 0
        for surface_idx in boundary_indices:
            vertices = self._psc_surface_vertices(surface_idx)
            triangles = self._psc_surface_triangles(surface_idx)
            if vertices.shape[0] == 0 or triangles.shape[0] == 0:
                continue
            all_vertices.append(vertices)
            faces = np.empty((triangles.shape[0], 4), dtype=np.int64)
            faces[:, 0] = 3
            faces[:, 1:] = triangles[:, :3] + vertex_offset
            all_faces.append(faces)
            vertex_offset += vertices.shape[0]
    
        if not all_vertices or not all_faces:
            return None
        try:
            mesh = pv.PolyData(np.vstack(all_vertices), np.vstack(all_faces).ravel())
        except Exception:
            return None
    
        self._psc_model_boundary_polydata_cache = (signature, mesh)
        return mesh
    
    def _psc_points_inside_model_boundary(self, points: np.ndarray) -> Optional[np.ndarray]:
        """Return a boolean mask for candidate points inside the model Boundary shell."""
        points = np.asarray(points, dtype=float)
        if points.ndim == 1:
            points = points.reshape(1, 3)
        if points.shape[0] == 0:
            return np.asarray([], dtype=bool)
    
        boundary_mesh = self._psc_model_boundary_polydata()
        if boundary_mesh is None or getattr(boundary_mesh, "n_cells", 0) == 0:
            return None
        try:
            probe = pv.PolyData(points)
            enclosed = probe.select_enclosed_points(
                boundary_mesh,
                tolerance=1e-6,
                check_surface=False,
            )
            selected = np.asarray(enclosed.point_data["SelectedPoints"], dtype=bool)
            if selected.size == points.shape[0]:
                return selected
        except Exception:
            pass
        return None
    
    def _psc_points_to_surface_distances(
        self,
        points: np.ndarray,
        surface_idx: int,
    ) -> np.ndarray:
        """Return unsigned distances from candidate points to a PLC surface."""
        points = np.asarray(points, dtype=float)
        if points.ndim == 1:
            points = points.reshape(1, 3)
        if points.shape[0] == 0:
            return np.empty((0,), dtype=float)
    
        mesh = self._psc_surface_polydata(surface_idx)
        if mesh is not None and getattr(mesh, "n_points", 0) > 0 and getattr(mesh, "n_cells", 0) > 0:
            try:
                probe = pv.PolyData(points)
                result = probe.compute_implicit_distance(mesh, inplace=False)
                distances = (
                    np.asarray(result.point_data["implicit_distance"], dtype=float)
                    if "implicit_distance" in result.point_data
                    else np.empty((0,), dtype=float)
                )
                if distances.size == points.shape[0] and np.all(np.isfinite(distances)):
                    return np.abs(distances)
            except Exception:
                pass
    
        normal = self._psc_surface_normal(surface_idx)
        centroid = self._psc_surface_centroid(surface_idx)
        if normal is not None and centroid is not None:
            return np.abs((points - centroid).dot(normal))
    
        vertices = self._psc_surface_vertices(surface_idx)
        if vertices.shape[0] == 0:
            return np.full(points.shape[0], np.inf, dtype=float)
    
        distances = np.full(points.shape[0], np.inf, dtype=float)
        for start in range(0, points.shape[0], 64):
            stop = min(start + 64, points.shape[0])
            chunk_min = np.full(stop - start, np.inf, dtype=float)
            for vertex_start in range(0, vertices.shape[0], 5000):
                vertex_stop = min(vertex_start + 5000, vertices.shape[0])
                diff = points[start:stop, None, :] - vertices[None, vertex_start:vertex_stop, :]
                chunk_min = np.minimum(
                    chunk_min,
                    np.sqrt(np.min(np.sum(diff * diff, axis=2), axis=1)),
                )
            distances[start:stop] = chunk_min
        return distances
    
    def _psc_target_boundaries_for_unit(self, unit_info: Dict[str, Any]) -> List[str]:
        """Return the boundary feature list that defines one STM unit."""
        boundaries = list(unit_info.get("boundaries", []) or [])
        inferred_boundary = self._psc_text(unit_info.get("topology_inferred_boundary", ""))
        if inferred_boundary:
            boundaries.append(inferred_boundary)
    
        ordered = []
        seen = set()
        for boundary in boundaries:
            boundary_text = self._psc_text(boundary)
            boundary_key = self._psc_key(boundary_text)
            if not boundary_key or boundary_key in seen:
                continue
            seen.add(boundary_key)
            ordered.append(boundary_text)
        return ordered
    
    def _psc_surface_indices_for_boundaries(
        self,
        boundaries: List[str],
    ) -> Dict[str, Dict[str, Any]]:
        """Map boundary feature names to matched PLC surface indices."""
        mapping: Dict[str, Dict[str, Any]] = {}
        for boundary in boundaries:
            boundary_text = self._psc_text(boundary)
            boundary_key = self._psc_key(boundary_text)
            if not boundary_key:
                continue
            indices = [
                int(surface_idx)
                for surface_idx in self._psc_surface_indices_for_boundary(boundary_text)
                if self._psc_surface_vertices(int(surface_idx)).shape[0] > 0
            ]
            if indices:
                mapping[boundary_key] = {
                    "label": boundary_text,
                    "indices": sorted(set(indices)),
                }
        return mapping
    
    def _psc_seed_candidate_points(
        self,
        reference_seed: np.ndarray,
        target_surface_indices: List[int],
        bounds: Optional[Tuple[np.ndarray, np.ndarray]],
        side_constraints: Optional[List[Dict[str, Any]]] = None,
        broad_sampling: bool = False,
    ) -> np.ndarray:
        """Generate candidate seed points in and around the expected STM unit."""
        if bounds is None:
            return np.asarray([reference_seed], dtype=float)
    
        bounds_min, bounds_max = bounds
        domain_span = bounds_max - bounds_min
        domain_diagonal = float(np.linalg.norm(domain_span))
        points = []
    
        def add_point(point: Any) -> None:
            try:
                candidate = np.asarray(point, dtype=float).reshape(3)
            except (TypeError, ValueError):
                return
            if np.all(np.isfinite(candidate)):
                points.append(self._psc_clamp_seed_to_bounds(candidate, bounds))
    
        def add_box_grid(box_min: np.ndarray, box_max: np.ndarray, count: int) -> None:
            box_min = np.asarray(box_min, dtype=float)
            box_max = np.asarray(box_max, dtype=float)
            if not np.all(np.isfinite(box_min)) or not np.all(np.isfinite(box_max)):
                return
            raw_min = np.minimum(box_min, box_max)
            raw_max = np.maximum(box_min, box_max)
            box_min = np.minimum(np.maximum(raw_min, bounds_min), bounds_max)
            box_max = np.minimum(np.maximum(raw_max, bounds_min), bounds_max)
            box_span = box_max - box_min
            for axis_idx in range(3):
                if box_span[axis_idx] <= max(domain_diagonal * 1e-7, 1e-9):
                    half_width = max(domain_span[axis_idx] * 0.12, domain_diagonal * 0.005, 1e-6)
                    center_value = (box_min[axis_idx] + box_max[axis_idx]) / 2.0
                    box_min[axis_idx] = max(bounds_min[axis_idx], center_value - half_width)
                    box_max[axis_idx] = min(bounds_max[axis_idx], center_value + half_width)
            box_span = box_max - box_min
            margin = np.maximum(box_span * 0.03, domain_diagonal * 1e-6)
            lower = np.where(box_span > 0.0, box_min + margin, box_min)
            upper = np.where(box_span > 0.0, box_max - margin, box_max)
            axes = [
                np.linspace(lower[axis_idx], upper[axis_idx], count)
                if upper[axis_idx] > lower[axis_idx]
                else np.asarray([lower[axis_idx]])
                for axis_idx in range(3)
            ]
            for x_value in axes[0]:
                for y_value in axes[1]:
                    for z_value in axes[2]:
                        add_point([x_value, y_value, z_value])
    
        add_point(reference_seed)
    
        reference_clearances = []
        for surface_idx in sorted(set(target_surface_indices)):
            distances = self._psc_points_to_surface_distances(
                np.asarray([reference_seed], dtype=float),
                int(surface_idx),
            )
            if distances.size and np.isfinite(distances[0]):
                reference_clearances.append(float(distances[0]))
    
        if reference_clearances:
            local_radius = float(np.median(reference_clearances))
        else:
            local_radius = domain_diagonal * 0.03
        local_radius = max(local_radius * 3.0, domain_diagonal * 0.05, 1e-6)
        local_radius = min(local_radius, domain_diagonal * 0.12)
    
        local_box_min = reference_seed - local_radius
        local_box_max = reference_seed + local_radius
        add_box_grid(local_box_min, local_box_max, 5)
    
        side_clearance = max(local_radius * 0.25, domain_diagonal * 0.01, 1e-6)
        for _ in range(3):
            corrected = np.asarray(reference_seed, dtype=float).copy()
            changed = False
            for constraint in side_constraints or []:
                surface_idx = int(constraint.get("surface_idx"))
                desired_sign = int(constraint.get("sign", 0))
                normal = self._psc_oriented_surface_normal(surface_idx)
                signed_distance = self._psc_signed_distance_to_surface(corrected, surface_idx)
                if normal is None or signed_distance is None or desired_sign == 0:
                    continue
                desired_distance = desired_sign * side_clearance
                if signed_distance * desired_sign >= side_clearance:
                    continue
                corrected = corrected + normal * (desired_distance - signed_distance)
                changed = True
            if changed:
                add_point(corrected)
                reference_seed = corrected
    
        target_vertex_sets = [
            self._psc_surface_vertices(surface_idx)
            for surface_idx in sorted(set(target_surface_indices))
        ]
        target_vertex_sets = [vertices for vertices in target_vertex_sets if vertices.shape[0] > 0]
        if target_vertex_sets:
            target_vertices = np.vstack(target_vertex_sets)
            target_min = np.min(target_vertices, axis=0)
            target_max = np.max(target_vertices, axis=0)
            expanded_min = np.maximum(target_min, reference_seed - local_radius * 1.5)
            expanded_max = np.minimum(target_max, reference_seed + local_radius * 1.5)
            add_box_grid(expanded_min, expanded_max, 3)
            if broad_sampling:
                broad_min = np.maximum(
                    target_min - domain_span * 0.05,
                    bounds_min,
                )
                broad_max = np.minimum(
                    target_max + domain_span * 0.05,
                    bounds_max,
                )
                add_box_grid(broad_min, broad_max, 5)
    
        local_steps = [-0.08, -0.04, 0.0, 0.04, 0.08]
        for x_step in local_steps:
            for y_step in local_steps:
                for z_step in local_steps:
                    offset = local_radius * np.asarray([x_step, y_step, z_step], dtype=float)
                    add_point(reference_seed + offset)
    
        if not points:
            return np.asarray([reference_seed], dtype=float)
        point_array = np.vstack(points)
        rounded = np.round(point_array, decimals=8)
        _, unique_indices = np.unique(rounded, axis=0, return_index=True)
        return point_array[np.sort(unique_indices)]
    
    def _psc_feature_distance_arrays(
        self,
        candidate_points: np.ndarray,
        feature_surface_map: Dict[str, Dict[str, Any]],
    ) -> Dict[str, np.ndarray]:
        """Compute candidate distances to each boundary feature."""
        distances_by_feature: Dict[str, np.ndarray] = {}
        for feature_key, feature_info in feature_surface_map.items():
            surface_distances = []
            for surface_idx in feature_info.get("indices", []):
                distances = self._psc_points_to_surface_distances(candidate_points, int(surface_idx))
                if distances.size == candidate_points.shape[0] and np.any(np.isfinite(distances)):
                    surface_distances.append(distances)
            if surface_distances:
                distances_by_feature[feature_key] = np.min(
                    np.vstack(surface_distances),
                    axis=0,
                )
        return distances_by_feature
    
    def _psc_surface_feature(self, surface_idx: int) -> str:
        """Return the feature/name carried by a loaded representative surface."""
        surface_info = getattr(self, "tetra_surface_data", {}).get(surface_idx, {}) or {}
        return (
            self._psc_text(surface_info.get("feature", ""))
            or self._psc_text(surface_info.get("name", ""))
            or f"Surface_{surface_idx}"
        )
    
    def _psc_oriented_surface_normal(self, surface_idx: int) -> Optional[np.ndarray]:
        """Return a geometric normal without using geological role metadata."""
        return self._psc_surface_normal(surface_idx)
    
    def _psc_signed_distances_to_surface(
        self,
        points: np.ndarray,
        surface_idx: int,
    ) -> np.ndarray:
        """Return signed distances to a representative surface where available."""
        points = np.asarray(points, dtype=float)
        if points.ndim == 1:
            points = points.reshape(1, 3)
        if points.shape[0] == 0:
            return np.empty((0,), dtype=float)
    
        mesh = self._psc_surface_polydata(surface_idx)
        if mesh is not None and getattr(mesh, "n_points", 0) > 0 and getattr(mesh, "n_cells", 0) > 0:
            try:
                probe = pv.PolyData(points)
                result = probe.compute_implicit_distance(mesh, inplace=False)
                distances = (
                    np.asarray(result.point_data["implicit_distance"], dtype=float)
                    if "implicit_distance" in result.point_data
                    else np.empty((0,), dtype=float)
                )
                if distances.size == points.shape[0] and np.all(np.isfinite(distances)):
                    return distances
            except Exception:
                pass
    
        centroid = self._psc_surface_centroid(surface_idx)
        normal = self._psc_oriented_surface_normal(surface_idx)
        if centroid is None or normal is None:
            return np.full(points.shape[0], np.nan, dtype=float)
        return (points - centroid).dot(normal)
    
    def _psc_signed_distance_to_surface(
        self,
        point: np.ndarray,
        surface_idx: int,
    ) -> Optional[float]:
        """Return signed distance to a representative surface."""
        try:
            point_array = np.asarray(point, dtype=float).reshape(3)
        except (TypeError, ValueError):
            return None
        distances = self._psc_signed_distances_to_surface(point_array, surface_idx)
        if distances.size and np.isfinite(distances[0]):
            return float(distances[0])
        centroid = self._psc_surface_centroid(surface_idx)
        normal = self._psc_oriented_surface_normal(surface_idx)
        if centroid is None or normal is None:
            return None
        return float(np.dot(point_array - centroid, normal))
    
    @staticmethod
    def _psc_sign(value: Optional[float], tolerance: float = 1e-8) -> int:
        """Return -1/0/+1 for a signed distance."""
        if value is None or not np.isfinite(value):
            return 0
        if value > tolerance:
            return 1
        if value < -tolerance:
            return -1
        return 0
    
    def _psc_representative_boundary_keys(
        self, psc_model: Dict[str, Any]
    ) -> set:
        """Return boundary keys explicitly linked as unit representatives."""
        keys = {
            self._psc_key(value)
            for value in psc_model.get("representative_boundary_keys", set())
            if self._psc_key(value)
        }
        if keys:
            return keys
        return {
            self._psc_key(boundary_info.get("feature", ""))
            for boundary_info in psc_model.get("boundary_order", []) or []
            if isinstance(boundary_info, dict)
            and boundary_info.get("is_representative")
            and self._psc_key(boundary_info.get("feature", ""))
        }
    
    def _psc_prepare_topology_side_context(
        self,
        psc_model: Dict[str, Any],
        mapped_units: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Infer owner/opposite sides for representative surfaces from STm topology."""
        context: Dict[str, Any] = {"representative_unit_signs": {}}
        bounds = self._psc_domain_bounds()
        diagonal = 1.0
        if bounds is not None:
            diagonal = max(float(np.linalg.norm(bounds[1] - bounds[0])), 1e-9)
        tolerance = max(diagonal * 0.002, 1e-8)
    
        representative_boundary_keys = self._psc_representative_boundary_keys(
            psc_model
        )
        representative_surfaces: Dict[Tuple[str, int], Dict[str, Any]] = {}
        for unit_info in mapped_units:
            boundary_indices = unit_info.get("boundary_surface_indices", {}) or {}
            for boundary, surface_indices in boundary_indices.items():
                boundary_key = self._psc_key(boundary)
                if not boundary_key or boundary_key == self._psc_key("Boundary"):
                    continue
                if boundary_key not in representative_boundary_keys:
                    continue
                for surface_idx in surface_indices or []:
                    try:
                        surface_idx = int(surface_idx)
                    except (TypeError, ValueError):
                        continue
                    representative_surfaces[(boundary_key, surface_idx)] = {
                        "boundary": self._psc_text(boundary),
                        "surface_idx": surface_idx,
                    }
    
        for (boundary_key, surface_idx), surface_info in representative_surfaces.items():
            matching_signs = []
            non_matching_signs = []
            for unit_info in mapped_units:
                unit_boundaries = {
                    self._psc_key(boundary)
                    for boundary in unit_info.get("boundaries", []) or []
                }
                if boundary_key not in unit_boundaries:
                    continue
                reference_seed = self._psc_reference_seed_point_for_unit(dict(unit_info), psc_model)
                signed_distance = self._psc_signed_distance_to_surface(reference_seed, surface_idx)
                sign_value = self._psc_sign(signed_distance, tolerance)
                if sign_value == 0:
                    continue
                if (
                    self._psc_key(
                        unit_info.get("representative_boundary", "")
                    )
                    == boundary_key
                ):
                    matching_signs.append(sign_value)
                else:
                    non_matching_signs.append(sign_value)
    
            owner_sign = 0
            if matching_signs:
                matching_sum = sum(matching_signs)
                if matching_sum != 0:
                    owner_sign = 1 if matching_sum > 0 else -1
            if owner_sign == 0 and non_matching_signs:
                non_matching_sum = sum(non_matching_signs)
                if non_matching_sum != 0:
                    owner_sign = -1 if non_matching_sum > 0 else 1
    
            if owner_sign:
                context["representative_unit_signs"][(boundary_key, surface_idx)] = owner_sign
    
        return context
    
    def _psc_unit_side_constraints(
        self,
        unit_info: Dict[str, Any],
        psc_model: Dict[str, Any],
        reference_seed: np.ndarray,
        target_surface_map: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Return signed side constraints implied by STm representative surfaces."""
        constraints = []
        unit_representative_key = self._psc_key(
            unit_info.get("representative_boundary", "")
        )
        side_context = getattr(self, "_psc_side_context", {}) or {}
        representative_signs = side_context.get("representative_unit_signs", {}) or {}
        representative_boundary_keys = self._psc_representative_boundary_keys(
            psc_model
        )
    
        for boundary_key, boundary_info in target_surface_map.items():
            if boundary_key == self._psc_key("Boundary"):
                continue
            if boundary_key not in representative_boundary_keys:
                continue
            for surface_idx in boundary_info.get("indices", []):
                try:
                    surface_idx = int(surface_idx)
                except (TypeError, ValueError):
                    continue
                centroid = self._psc_surface_centroid(surface_idx)
                if centroid is None:
                    continue
                owner_sign = representative_signs.get((boundary_key, surface_idx))
                if owner_sign is None:
                    owner_sign = self._psc_sign(
                        self._psc_signed_distance_to_surface(reference_seed, surface_idx)
                    )
                if owner_sign == 0:
                    continue
                owns_boundary = unit_representative_key == boundary_key
                desired_sign = owner_sign if owns_boundary else -owner_sign
                constraints.append(
                    {
                        "surface_idx": surface_idx,
                        "sign": desired_sign,
                        "label": boundary_info.get("label", boundary_key),
                        "reason": "representative-own-side"
                        if owns_boundary
                        else "representative-opposite-side",
                    }
                )
    
        return constraints
    
    def _psc_target_side_mismatch_count(
        self,
        candidate_seed: np.ndarray,
        constraints: List[Dict[str, Any]],
        tolerance: float,
    ) -> Tuple[int, int]:
        """Count side constraints violated by a candidate seed."""
        mismatches = 0
        checked = 0
        for constraint in constraints:
            signed_distance = self._psc_signed_distance_to_surface(
                candidate_seed,
                int(constraint.get("surface_idx")),
            )
            sign_value = self._psc_sign(signed_distance, tolerance)
            if sign_value == 0:
                mismatches += 1
                checked += 1
                continue
            checked += 1
            if sign_value != int(constraint.get("sign", 0)):
                mismatches += 1
        return mismatches, checked
    
    def _psc_side_mismatch_count(
        self,
        reference_seed: np.ndarray,
        candidate_seed: np.ndarray,
        surface_indices: List[int],
        tolerance: float,
    ) -> Tuple[int, int]:
        """Count target surfaces for which a candidate crosses the reference half-space."""
        mismatches = 0
        checked = 0
        for surface_idx in sorted(set(surface_indices)):
            centroid = self._psc_surface_centroid(surface_idx)
            normal = self._psc_surface_normal(surface_idx)
            if centroid is None or normal is None:
                continue
            reference_distance = float(np.dot(reference_seed - centroid, normal))
            candidate_distance = float(np.dot(candidate_seed - centroid, normal))
            if abs(reference_distance) <= tolerance or abs(candidate_distance) <= tolerance:
                continue
            checked += 1
            if reference_distance * candidate_distance < 0.0:
                mismatches += 1
        return mismatches, checked
    
    def _psc_refine_seed_by_topology_signature(
        self,
        unit_info: Dict[str, Any],
        psc_model: Dict[str, Any],
        reference_seed: np.ndarray,
        require_side_match: bool = False,
        broad_sampling: Optional[bool] = None,
    ) -> np.ndarray:
        """Choose a seed whose nearest-boundary signature matches the STM unit topology."""
        bounds = self._psc_domain_bounds()
        if bounds is None:
            return reference_seed
    
        unit_boundaries = self._psc_target_boundaries_for_unit(unit_info)
        target_boundaries = list(unit_boundaries)
        expected_labels_by_key = {
            self._psc_key(boundary): self._psc_text(boundary)
            for boundary in target_boundaries
            if self._psc_key(boundary)
        }
        expected_set = set(expected_labels_by_key)
        target_surface_map = self._psc_surface_indices_for_boundaries(target_boundaries)
        if not target_surface_map:
            unit_info["seed_topology_signature"] = {
                "target": [
                    expected_labels_by_key[key] for key in sorted(expected_labels_by_key)
                ],
                "closest": [],
                "exact": False,
                "missing_count": len(expected_set),
                "missing_labels": [
                    expected_labels_by_key[key] for key in sorted(expected_set)
                ],
                "extra_count": 0,
                "extra_labels": [],
                "candidate_count": 0,
                "inside_model": True,
            }
            return reference_seed
    
        feature_candidates = list(psc_model.get("boundary_features", set()) or [])
        feature_candidates.extend(target_boundaries)
        feature_surface_map: Dict[str, Dict[str, Any]] = {}
        for boundary in feature_candidates:
            boundary_text = self._psc_text(boundary)
            boundary_key = self._psc_key(boundary_text)
            if not boundary_key:
                continue
            boundary_map = self._psc_surface_indices_for_boundaries([boundary_text])
            if boundary_key in boundary_map:
                feature_surface_map[boundary_key] = boundary_map[boundary_key]
    
        target_keys = [key for key in target_surface_map if key in feature_surface_map]
        if not target_keys:
            return reference_seed
    
        target_surface_indices = [
            int(surface_idx)
            for key in target_keys
            for surface_idx in target_surface_map[key].get("indices", [])
        ]
        side_constraints = self._psc_unit_side_constraints(
            unit_info,
            psc_model,
            reference_seed,
            target_surface_map,
        )
        if broad_sampling is None:
            broad_sampling = (
                int(unit_info.get("ambiguity_group_size", 1) or 1) > 1
            )
        candidate_points = self._psc_seed_candidate_points(
            reference_seed,
            target_surface_indices,
            bounds,
            side_constraints,
            broad_sampling=bool(broad_sampling),
        )
        if candidate_points.shape[0] == 0:
            return reference_seed
    
        distance_arrays = self._psc_feature_distance_arrays(candidate_points, feature_surface_map)
        if not distance_arrays:
            return reference_seed
    
        target_set = set(expected_set)
        all_keys = [key for key in feature_surface_map.keys() if key in distance_arrays]
        if not all_keys:
            return reference_seed
    
        bounds_min, bounds_max = bounds
        diagonal = max(float(np.linalg.norm(bounds_max - bounds_min)), 1e-9)
        min_clearance = max(diagonal * 0.004, 1e-6)
        side_tolerance = max(diagonal * 0.002, 1e-8)
        non_target_keys = [key for key in all_keys if key not in target_set]
        inside_model_mask = self._psc_points_inside_model_boundary(candidate_points)
        has_inside_candidates = (
            inside_model_mask is not None
            and inside_model_mask.size == candidate_points.shape[0]
            and bool(np.any(inside_model_mask))
        )
        best_index = None
        best_score = -float("inf")
        best_details: Dict[str, Any] = {}
        for candidate_idx, candidate in enumerate(candidate_points):
            inside_model = True
            if inside_model_mask is not None and inside_model_mask.size == candidate_points.shape[0]:
                inside_model = bool(inside_model_mask[candidate_idx])
            if has_inside_candidates and not inside_model:
                continue
    
            target_distances = [
                float(distance_arrays[key][candidate_idx])
                for key in target_keys
                if key in distance_arrays
            ]
            if not target_distances or not np.all(np.isfinite(target_distances)):
                continue
    
            ranked_keys = sorted(
                all_keys,
                key=lambda key: float(distance_arrays[key][candidate_idx]),
            )
            # Only mapped expected features determine the observed signature
            # cardinality. Unmapped expected features remain explicit missing
            # labels instead of being replaced by unrelated surfaces.
            closest_count = min(len(target_keys), len(ranked_keys))
            closest_keys = ranked_keys[:closest_count]
            closest_set = set(closest_keys)
            missing_count = len(target_set - closest_set)
            extra_count = len(closest_set - target_set)
            exact_signature = missing_count == 0 and extra_count == 0
    
            min_target_distance = min(target_distances)
            max_target_distance = max(target_distances)
            non_target_distances = [
                float(distance_arrays[key][candidate_idx])
                for key in non_target_keys
                if key in distance_arrays and np.isfinite(distance_arrays[key][candidate_idx])
            ]
            nearest_non_target = min(non_target_distances) if non_target_distances else diagonal * 10.0
            intrusion_count = sum(distance <= max_target_distance for distance in non_target_distances)
            reference_distance = float(np.linalg.norm(candidate - reference_seed))
            side_mismatches, side_checked = self._psc_target_side_mismatch_count(
                candidate,
                side_constraints,
                side_tolerance,
            )
            if require_side_match and side_checked > 0 and side_mismatches > 0:
                continue
    
            clearance_term = min(min_target_distance / diagonal, 0.25)
            separation_term = min((nearest_non_target - max_target_distance) / diagonal, 1.0)
            close_penalty = max(0.0, (min_clearance - min_target_distance) / diagonal)
            score = 0.0
            if exact_signature:
                score += 1000.0
            score -= 120.0 * (missing_count + extra_count)
            score -= 30.0 * intrusion_count
            score -= 800.0 * side_mismatches
            score += 40.0 * clearance_term
            score += 15.0 * separation_term
            score -= 20.0 * (reference_distance / diagonal)
            score -= 100.0 * close_penalty
            if inside_model_mask is not None and not inside_model:
                score -= 5000.0
    
            if score > best_score:
                best_score = score
                best_index = candidate_idx
                best_details = {
                    "closest_keys": closest_keys,
                    "exact_signature": exact_signature,
                    "missing_count": missing_count,
                    "extra_count": extra_count,
                    "intrusion_count": intrusion_count,
                    "side_mismatches": side_mismatches,
                    "side_checked": side_checked,
                    "min_target_distance": min_target_distance,
                    "nearest_non_target": nearest_non_target,
                    "candidate_count": int(candidate_points.shape[0]),
                    "inside_model": bool(inside_model),
                }
    
        if best_index is None:
            return reference_seed
    
        best_seed = self._psc_clamp_seed_to_bounds(candidate_points[best_index], bounds)
        label_by_key = {
            key: feature_surface_map.get(key, {}).get("label", key)
            for key in feature_surface_map
        }
        target_labels = [
            expected_labels_by_key.get(key, label_by_key.get(key, key))
            for key in sorted(expected_set)
        ]
        closest_labels = [
            label_by_key.get(key, key)
            for key in best_details.get("closest_keys", [])
        ]
        missing_labels = [
            expected_labels_by_key.get(key, label_by_key.get(key, key))
            for key in sorted(
                expected_set - set(best_details.get("closest_keys", []))
            )
        ]
        extra_labels = [
            label_by_key.get(key, key)
            for key in sorted(
                set(best_details.get("closest_keys", [])) - expected_set
            )
        ]
        closest_surface_indices = self._psc_closest_surface_indices_for_point(
            best_seed,
            closest_labels,
        )
        unit_info["seed_topology_signature"] = {
            "target": target_labels,
            "closest": closest_labels,
            "exact": bool(best_details.get("exact_signature", False)),
            "missing_count": int(best_details.get("missing_count", 0)),
            "missing_labels": missing_labels,
            "extra_count": int(best_details.get("extra_count", 0)),
            "extra_labels": extra_labels,
            "observed_count": len(closest_labels),
            "closest_surface_indices": closest_surface_indices,
            "score": float(best_score),
            "candidate_count": int(best_details.get("candidate_count", 0)),
            "min_target_distance": float(best_details.get("min_target_distance", 0.0)),
            "nearest_non_target": float(best_details.get("nearest_non_target", 0.0)),
            "intrusion_count": int(best_details.get("intrusion_count", 0)),
            "side_mismatches": int(best_details.get("side_mismatches", 0)),
            "side_checked": int(best_details.get("side_checked", 0)),
            "inside_model": bool(best_details.get("inside_model", True)),
            "side_constraints": [
                {
                    "surface": self._psc_surface_label(int(item.get("surface_idx"))),
                    "label": item.get("label", ""),
                    "sign": int(item.get("sign", 0)),
                    "reason": item.get("reason", ""),
                }
                for item in side_constraints
            ],
        }
        return best_seed
    
    def _psc_structural_surface_indices_for_unit(self, unit_info: Dict[str, Any]) -> List[int]:
        """Return only STM structural boundary surfaces, excluding model Boundary faces."""
        indices = []
        boundary_surface_indices = unit_info.get("boundary_surface_indices", {}) or {}
        for boundary, boundary_indices in boundary_surface_indices.items():
            if self._psc_key(boundary) == self._psc_key("Boundary"):
                continue
            for surface_idx in boundary_indices or []:
                try:
                    indices.append(int(surface_idx))
                except (TypeError, ValueError):
                    continue
    
        if not indices:
            for surface_idx in unit_info.get("matched_surface_indices", []) or []:
                try:
                    indices.append(int(surface_idx))
                except (TypeError, ValueError):
                    continue
    
        return sorted(set(indices))
    
    def _psc_seed_between_structural_surfaces(
        self,
        surface_indices: List[int],
        psc_model: Dict[str, Any],
    ) -> Optional[np.ndarray]:
        """Place a seed inside the volume bounded by structural PLC surfaces."""
        axis = self._psc_stacking_axis(psc_model)
        bounds = self._psc_domain_bounds()
        if bounds is not None:
            line_origin = (bounds[0] + bounds[1]) / 2.0
        else:
            centroids = [
                self._psc_surface_centroid(surface_idx)
                for surface_idx in surface_indices
            ]
            centroids = [centroid for centroid in centroids if centroid is not None]
            if not centroids:
                return None
            line_origin = np.mean(np.asarray(centroids), axis=0)
    
        points = [
            self._psc_surface_point_on_axis(surface_idx, line_origin, axis)
            for surface_idx in surface_indices
        ]
        points = [point for point in points if point is not None]
        if not points:
            return None
    
        seed = np.mean(np.asarray(points, dtype=float), axis=0)
        seed = self._psc_clamp_seed_to_bounds(seed, bounds)
        return self._psc_move_seed_off_boundaries(seed, surface_indices, bounds)

    def _psc_seed_between_structural_surfaces_and_model_boundary(
        self,
        surface_indices: List[int],
        unit_info: Dict[str, Any],
        psc_model: Dict[str, Any],
    ) -> Optional[np.ndarray]:
        """Place a seed between structural surfaces and the closest Boundary face."""
        structural_seed = self._psc_seed_between_structural_surfaces(
            surface_indices,
            psc_model,
        )
        if structural_seed is None:
            return None

        boundary_indices = list(unit_info.get("model_boundary_indices", []) or [])
        if not boundary_indices:
            boundary_indices = self._psc_surface_indices_for_boundary("Boundary")
        boundary_points = []
        for surface_idx in boundary_indices:
            vertices = self._psc_surface_vertices(int(surface_idx))
            if vertices.shape[0] == 0:
                continue
            distances = np.linalg.norm(vertices - structural_seed, axis=1)
            if distances.size:
                boundary_points.append(
                    (
                        float(np.min(distances)),
                        np.asarray(vertices[int(np.argmin(distances))], dtype=float),
                    )
                )
        if not boundary_points:
            return structural_seed

        _, boundary_point = min(boundary_points, key=lambda item: item[0])
        seed = (np.asarray(structural_seed, dtype=float) + boundary_point) / 2.0
        bounds = self._psc_domain_bounds()
        seed = self._psc_clamp_seed_to_bounds(seed, bounds)
        return self._psc_move_seed_off_boundaries(
            seed,
            list(surface_indices) + [int(value) for value in boundary_indices],
            bounds,
        )
    
    def _psc_seed_between_surface_and_model_boundary(
        self,
        surface_idx: int,
        unit_info: Dict[str, Any],
        psc_model: Dict[str, Any],
        record_inferred_boundary: bool = True,
    ) -> Optional[np.ndarray]:
        """Place an exterior-unit seed between one STM surface and the model boundary."""
        axis = self._psc_stacking_axis(psc_model)
        bounds = self._psc_domain_bounds()
        axis_bounds = self._psc_domain_axis_bounds(axis)
        if bounds is not None:
            line_origin = (bounds[0] + bounds[1]) / 2.0
        else:
            line_origin = self._psc_surface_centroid(surface_idx)
        if line_origin is None or axis_bounds is None:
            return None
    
        surface_point = self._psc_surface_point_on_axis(surface_idx, line_origin, axis)
        if surface_point is None:
            return None
        surface_t = float(np.dot(surface_point, axis))
    
        adjacent_indices, adjacent_feature = self._psc_adjacent_boundary_surface_indices(
            unit_info,
            psc_model,
            preferred_direction=1,
        )
        adjacent_points = [
            self._psc_surface_point_on_axis(adjacent_idx, line_origin, axis)
            for adjacent_idx in adjacent_indices
        ]
        adjacent_points = [point for point in adjacent_points if point is not None]
        if adjacent_points:
            adjacent_t = float(np.mean([np.dot(point, axis) for point in adjacent_points]))
            cap_t = axis_bounds[0] if adjacent_t > surface_t else axis_bounds[1]
            if record_inferred_boundary:
                unit_info["topology_inferred_boundary"] = adjacent_feature
            else:
                unit_info["topology_direction_reference_boundary"] = adjacent_feature
        else:
            lower_space = abs(surface_t - axis_bounds[0])
            upper_space = abs(axis_bounds[1] - surface_t)
            cap_t = axis_bounds[1] if upper_space >= lower_space else axis_bounds[0]
    
        if abs(cap_t - surface_t) < 1e-9:
            diagonal = 0.0
            if bounds is not None:
                diagonal = float(np.linalg.norm(bounds[1] - bounds[0]))
            offset = max(diagonal * 0.05, 1e-3)
            cap_t = surface_t + (offset if cap_t >= surface_t else -offset)
    
        seed_t = (surface_t + cap_t) / 2.0
        seed = surface_point + axis * (seed_t - surface_t)
        seed = self._psc_clamp_seed_to_bounds(seed, bounds)
        return self._psc_move_seed_off_boundaries(seed, [surface_idx], bounds)
    
    def _psc_reference_seed_point_for_unit(
        self,
        unit_info: Dict[str, Any],
        psc_model: Dict[str, Any],
    ) -> Optional[np.ndarray]:
        """Compute the initial seed from STM topology before signature refinement."""
        unit_info.pop("topology_inferred_boundary", None)
        unit_info.pop("topology_direction_reference_boundary", None)
        surface_indices = self._psc_structural_surface_indices_for_unit(unit_info)
        has_model_boundary = any(
            self._psc_key(boundary) == self._psc_key("Boundary")
            for boundary in unit_info.get("boundaries", [])
        )
    
        if len(surface_indices) >= 2:
            if has_model_boundary:
                seed = self._psc_seed_between_structural_surfaces_and_model_boundary(
                    surface_indices,
                    unit_info,
                    psc_model,
                )
            else:
                seed = self._psc_seed_between_structural_surfaces(
                    surface_indices,
                    psc_model,
                )
            return seed
    
        if len(surface_indices) == 1 and has_model_boundary:
            seed = self._psc_seed_between_surface_and_model_boundary(
                surface_indices[0],
                unit_info,
                psc_model,
                record_inferred_boundary=False,
            )
            return seed
    
        if len(surface_indices) < 2:
            adjacent_indices, adjacent_feature = self._psc_adjacent_boundary_surface_indices(
                unit_info,
                psc_model,
            )
            if adjacent_indices:
                surface_indices.extend(adjacent_indices)
                unit_info["topology_inferred_boundary"] = adjacent_feature
    
        surface_indices = [
            int(surface_idx)
            for surface_idx in sorted(set(surface_indices), key=lambda value: str(value))
            if self._psc_surface_vertices(int(surface_idx)).shape[0] > 0
        ]
    
        if len(surface_indices) == 1:
            seed = self._psc_seed_between_surface_and_model_boundary(
                surface_indices[0],
                unit_info,
                psc_model,
            )
        elif len(surface_indices) >= 2:
            seed = self._psc_seed_between_structural_surfaces(surface_indices, psc_model)
        else:
            seed = None
    
        if seed is None:
            return None
        return np.asarray(seed, dtype=float)

    def _psc_seed_point_for_unit(
        self,
        unit_info: Dict[str, Any],
        psc_model: Dict[str, Any],
        require_side_match: bool = False,
    ) -> Optional[List[float]]:
        """Compute a material seed point from STM topology and loaded PLC surfaces."""
        surface_indices = self._psc_structural_surface_indices_for_unit(unit_info)
        has_model_boundary = any(
            self._psc_key(boundary) == self._psc_key("Boundary")
            for boundary in unit_info.get("boundaries", [])
        )
    
        reference_seed = self._psc_reference_seed_point_for_unit(unit_info, psc_model)
        if reference_seed is None or not np.all(np.isfinite(reference_seed)):
            return None
    
        initial_broad_sampling = (
            int(unit_info.get("ambiguity_group_size", 1) or 1) > 1
        )
        refined_seed = self._psc_refine_seed_by_topology_signature(
            unit_info,
            psc_model,
            np.asarray(reference_seed, dtype=float),
            require_side_match=require_side_match,
            broad_sampling=initial_broad_sampling,
        )
        first_signature = dict(unit_info.get("seed_topology_signature", {}) or {})

        # The inexpensive local search is normally enough.  If it cannot find
        # an exact signature, retry over the wider PLC extent.  This recovers
        # valid or one-boundary-partial 3D seeds without importing any of the
        # polygon/area machinery used by the section workflow.
        if not initial_broad_sampling and not first_signature.get("exact", False):
            unit_info.pop("seed_topology_signature", None)
            broad_seed = self._psc_refine_seed_by_topology_signature(
                unit_info,
                psc_model,
                np.asarray(reference_seed, dtype=float),
                require_side_match=require_side_match,
                broad_sampling=True,
            )
            broad_signature = dict(
                unit_info.get("seed_topology_signature", {}) or {}
            )

            def signature_quality(signature: Dict[str, Any]) -> Tuple[Any, ...]:
                if not signature:
                    return (2, 10**9, 10**9, 10**9, 0, float("inf"))
                return (
                    0 if signature.get("exact") else 1,
                    int(signature.get("missing_count", 0)),
                    int(signature.get("extra_count", 0)),
                    int(signature.get("side_mismatches", 0)),
                    -int(signature.get("observed_count", 0)),
                    -float(signature.get("score", -float("inf"))),
                )

            if signature_quality(first_signature) <= signature_quality(broad_signature):
                refined_seed = np.asarray(refined_seed, dtype=float)
                if first_signature:
                    unit_info["seed_topology_signature"] = first_signature
                else:
                    unit_info.pop("seed_topology_signature", None)
            else:
                refined_seed = np.asarray(broad_seed, dtype=float)
        if require_side_match and not unit_info.get("seed_topology_signature"):
            return None
        return [float(refined_seed[0]), float(refined_seed[1]), float(refined_seed[2])]
    
    def _psc_seed_points_for_unit(
        self,
        unit_info: Dict[str, Any],
        psc_model: Dict[str, Any],
        mapped_units: Optional[List[Dict[str, Any]]] = None,
        max_missing_boundaries: Optional[int] = None,
    ) -> List[List[float]]:
        """Compute one or more PSC seed points for a mapped STm unit."""
        if max_missing_boundaries is None:
            max_missing_boundaries = self.MAX_RELAXED_MISSING_BOUNDARIES
        try:
            max_missing_boundaries = max(int(max_missing_boundaries), 0)
        except (TypeError, ValueError):
            max_missing_boundaries = self.MAX_RELAXED_MISSING_BOUNDARIES

        if unit_info.get("seed_override"):
            seed_points = self._psc_normalize_seed_points(
                unit_info.get("seed_points") or unit_info.get("seed_point")
            )
            if seed_points:
                unit_info["seed_points"] = seed_points
                unit_info["seed_point"] = seed_points[0]
                return seed_points
            return []
    
        local_boundary_sets = self._psc_local_boundary_sets_for_unit(
            unit_info,
            mapped_units or [],
        )
        seed_candidates = []
        bounds = self._psc_domain_bounds()
        duplicate_tolerance = 1e-6
        if bounds is not None:
            duplicate_tolerance = max(
                float(np.linalg.norm(bounds[1] - bounds[0])) * 1e-6,
                1e-6,
            )
    
        def add_candidate(
            seed_point: Optional[List[float]],
            signature: Dict[str, Any],
            boundaries: List[str],
            component_index: int,
        ) -> None:
            if seed_point is None:
                return
            try:
                coords = [float(value) for value in list(seed_point)[:3]]
            except (TypeError, ValueError):
                return
            if len(coords) != 3 or not all(np.isfinite(coords)):
                return
            signature = dict(signature or {})
            if not signature:
                return
            if int(signature.get("missing_count", 0)) > max_missing_boundaries:
                return
            seed_candidates.append(
                {
                    "seed_point": coords,
                    "boundaries": list(boundaries),
                    "signature": signature,
                    "component_index": int(component_index),
                    "is_local": component_index >= 0,
                }
            )

        global_seed = self._psc_seed_point_for_unit(unit_info, psc_model)
        add_candidate(
            global_seed,
            unit_info.get("seed_topology_signature", {}) or {},
            list(unit_info.get("boundaries", []) or []),
            -1,
        )

        for component_idx, local_boundaries in enumerate(local_boundary_sets):
            local_info = self._psc_unit_with_local_boundaries(
                unit_info,
                local_boundaries,
                component_idx,
            )
            local_seed = self._psc_seed_point_for_unit(
                local_info,
                psc_model,
                require_side_match=True,
            )
            add_candidate(
                local_seed,
                local_info.get("seed_topology_signature", {}) or {},
                local_boundaries,
                component_idx,
            )

        # Prefer the best topology realization when global and local searches
        # converge to the same physical point.  Distinct valid local components
        # remain separate seeds and will pass through repeat-adjacency checks.
        seed_candidates.sort(
            key=lambda candidate: (
                0 if candidate["signature"].get("exact") else 1,
                int(candidate["signature"].get("missing_count", 0)),
                int(candidate["signature"].get("extra_count", 0)),
                int(candidate["signature"].get("side_mismatches", 0)),
                0 if not candidate.get("is_local") else 1,
                -int(candidate["signature"].get("observed_count", 0)),
                tuple(round(value, 8) for value in candidate["seed_point"]),
            )
        )
        selected_candidates = []
        for candidate in seed_candidates:
            candidate_point = np.asarray(candidate["seed_point"], dtype=float)
            if any(
                np.linalg.norm(
                    candidate_point - np.asarray(existing["seed_point"], dtype=float)
                )
                <= duplicate_tolerance
                for existing in selected_candidates
            ):
                continue
            selected_candidates.append(candidate)

        seed_points = [
            list(candidate["seed_point"]) for candidate in selected_candidates
        ]
        seed_signatures = [
            {
                "boundaries": list(candidate["boundaries"]),
                "signature": dict(candidate["signature"]),
                "component_index": int(candidate["component_index"]),
            }
            for candidate in selected_candidates
        ]
        unit_info["seed_points"] = seed_points
        unit_info["seed_point"] = seed_points[0] if seed_points else None
        unit_info["seed_topology_signatures"] = seed_signatures
        unit_info["seed_topology_signature"] = (
            dict(seed_signatures[0]["signature"]) if seed_signatures else {}
        )
        return seed_points
    
    def _assign_psc_materials(
        self,
        psc_model: Dict[str, Any],
        psc_mapping: Dict[str, Any],
        max_missing_boundaries: Optional[int] = None,
    ) -> Tuple[int, int]:
        """Replace formation materials with PSC-derived unit materials."""
        if max_missing_boundaries is None:
            max_missing_boundaries = self.MAX_RELAXED_MISSING_BOUNDARIES
        try:
            max_missing_boundaries = max(int(max_missing_boundaries), 0)
        except (TypeError, ValueError):
            max_missing_boundaries = self.MAX_RELAXED_MISSING_BOUNDARIES
        assigned_materials = []
        skipped_count = 0
        mapped_units = list(psc_mapping.get("units", []))
        self._psc_side_context = self._psc_prepare_topology_side_context(
            psc_model,
            mapped_units,
        )

        assignment_payloads = self._psc_assign_volumetric_regions(
            mapped_units,
            psc_model,
            max_missing_boundaries=max_missing_boundaries,
        )
        if assignment_payloads is None:
            for unit_info in mapped_units:
                seed_points = self._psc_seed_points_for_unit(
                    unit_info,
                    psc_model,
                    mapped_units,
                    max_missing_boundaries=max_missing_boundaries,
                )
                unit_info["seed_points"] = seed_points
                unit_info["seed_point"] = seed_points[0] if seed_points else None
            assignment_payloads = self._psc_classify_seed_assignments(
                mapped_units,
                psc_model,
                max_missing_boundaries=max_missing_boundaries,
            )
        assignment_counts = {}
        for payload in assignment_payloads:
            status = str(payload.get("status", "UNASSIGNED"))
            assignment_counts[status] = assignment_counts.get(status, 0) + 1
        self._psc_last_assignment_counts = assignment_counts

        for unit_info in mapped_units:
            seed_points = list(unit_info.get("seed_points", []) or [])
            if not seed_points:
                skipped_count += 1
                continue
    
            material_id = len(assigned_materials)
            assigned_materials.append(
                {
                    "name": unit_info.get("name") or unit_info.get("feature") or f"PSC_Unit_{material_id}",
                    "locations": [list(seed) for seed in seed_points],
                    "attribute": material_id,
                    "type": "FORMATION",
                    "source": "PSC",
                    "psc_table": psc_model.get("table_name", ""),
                    "psc_max_missing_boundaries": max_missing_boundaries,
                    "feature": unit_info.get("feature", ""),
                    "unit_role": self._psc_unit_role(
                        unit_info.get("unit_role", "TU")
                    ),
                    "domains": list(unit_info.get("domains", [])),
                    "boundaries": list(unit_info.get("boundaries", [])),
                    "representative_boundary": unit_info.get(
                        "representative_boundary", ""
                    ),
                    **{
                        color_name: unit_info[color_name]
                        for color_name in ("color_R", "color_G", "color_B")
                        if color_name in unit_info
                    },
                    "matched_surface_indices": list(unit_info.get("matched_surface_indices", [])),
                    "missing_boundaries": list(unit_info.get("missing_boundaries", [])),
                    "seed_override": bool(unit_info.get("seed_override", False)),
                    "psc_virtual_unit": bool(unit_info.get("psc_virtual_unit", False)),
                    "psc_virtual_source": unit_info.get("psc_virtual_source", ""),
                    "psc_seed_count": len(seed_points),
                    "psc_assignment_status": unit_info.get(
                        "psc_assignment_status", "UNASSIGNED"
                    ),
                    "psc_assignments": list(
                        unit_info.get("psc_assignments", []) or []
                    ),
                    "psc_rejected_assignments": list(
                        unit_info.get("psc_rejected_assignments", []) or []
                    ),
                    "seed_topology_signatures": list(
                        unit_info.get("seed_topology_signatures", []) or []
                    ),
                }
            )
    
        if not assigned_materials:
            self._psc_last_seed_count = 0
            return 0, skipped_count
    
        self._psc_last_seed_count = sum(
            len(material.get("locations", []) or [])
            for material in assigned_materials
        )
        fault_materials = [
            dict(material)
            for material in getattr(self, "tetra_materials", [])
            if str(material.get("type", "FORMATION")).upper() == "FAULT"
        ]
        for offset, material in enumerate(fault_materials):
            material["attribute"] = len(assigned_materials) + offset
    
        self.tetra_materials = assigned_materials + fault_materials
        self._refresh_material_list()
        if self.tetra_materials and hasattr(self, "material_list"):
            self.material_list.setCurrentRow(0)
        if hasattr(self, "_update_material_visualisation"):
            self._update_material_visualisation()
        if hasattr(self, "_update_material_dropdown"):
            self._update_material_dropdown()
    
        return len(assigned_materials), skipped_count


class TwoDPiecewiseStructuralComplex(PiecewiseStructuralComplex):
    """Build PSC-derived editable seeds and section fill polygons in Xsection views."""

    FRAME_BOUNDARY_KEY = "__xsection_frame__"
    MAX_RELAXED_MISSING_BOUNDARIES = 1

    def _pzero_project(self):
        """Return the owning PZero project window for a 2D Xsection view."""
        return getattr(self.host, "parent", None)

    def open_section_areas_dialog(self) -> None:
        """Open the Build PSC section areas dialog for the active Xsection."""
        project = self._pzero_project()
        if project is None:
            return

        stm_tables = self._available_stm_tables()
        if not stm_tables:
            self.print_terminal(
                "No Structural Topology model tables are available in the current project."
            )
            return

        section_uid = getattr(self.host, "this_x_section_uid", "")
        if not section_uid:
            self.print_terminal("No active Xsection is available.")
            return

        section_line_uids = self._section_polyline_uids(use_selected=False)
        selected_line_uids = self._section_polyline_uids(use_selected=True)
        if not section_line_uids:
            self.print_terminal(
                "No XsPolyLine entities are available in the active Xsection."
            )
            return

        dialog = QDialog(self.host)
        dialog.setWindowTitle("Build PSC section areas")
        dialog.resize(520, 220)
        layout = QVBoxLayout(dialog)

        info_label = QLabel(
            "Build PSC seeds and filled section areas from a watertight Xsection line network."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        form_layout = QFormLayout()
        table_combo = QComboBox(dialog)
        table_combo.addItems(stm_tables)
        form_layout.addRow("STm table", table_combo)

        boundary_combo = QComboBox(dialog)
        for label, uid in self._available_boundary_options():
            boundary_combo.addItem(label, uid)
        form_layout.addRow("Boundary", boundary_combo)

        max_missing_spin = QSpinBox(dialog)
        max_missing_spin.setRange(0, 10)
        max_missing_spin.setValue(self.MAX_RELAXED_MISSING_BOUNDARIES)
        max_missing_spin.setToolTip(
            "Maximum number of STm boundaries that may be absent from the local section signature."
        )
        form_layout.addRow("Max missing boundaries", max_missing_spin)

        domxs_cut_options = self._available_domxs_cut_options()
        domxs_cut_uid = self._default_domxs_cut_uid(
            [uid for _label, uid in domxs_cut_options]
        )
        domxs_cut_widget = QWidget(dialog)
        domxs_cut_layout = QHBoxLayout(domxs_cut_widget)
        domxs_cut_layout.setContentsMargins(0, 0, 0, 0)
        use_domxs_cut_check = QCheckBox("Use DomXs for dividing areas")
        use_domxs_cut_check.setChecked(False)
        use_domxs_cut_check.setEnabled(bool(domxs_cut_options))
        domxs_cut_layout.addWidget(use_domxs_cut_check)
        domxs_cut_combo = QComboBox(dialog)
        for label, uid in domxs_cut_options:
            domxs_cut_combo.addItem(label, uid)
        if domxs_cut_uid:
            selected_index = domxs_cut_combo.findData(domxs_cut_uid)
            if selected_index >= 0:
                domxs_cut_combo.setCurrentIndex(selected_index)
        domxs_cut_combo.setEnabled(False)
        domxs_cut_layout.addWidget(domxs_cut_combo, 1)
        use_domxs_cut_check.toggled.connect(domxs_cut_combo.setEnabled)
        use_domxs_cut_check.setToolTip(
            "Use the selected DomXs to split PSC areas and seeds. "
            "The DomXs is not used as an STm topology boundary."
            if domxs_cut_options
            else "No DomXs is available in the active Xsection."
        )
        domxs_cut_combo.setToolTip(use_domxs_cut_check.toolTip())
        form_layout.addRow("DomXs", domxs_cut_widget)

        use_selected_check = QCheckBox("Use selected XsPolyLine entities only")
        use_selected_check.setChecked(bool(selected_line_uids))
        use_selected_check.setEnabled(bool(selected_line_uids))
        use_selected_check.setToolTip(
            "When unchecked, all XsPolyLine entities in the active Xsection are used."
        )
        form_layout.addRow("Lines", use_selected_check)

        # Advanced numeric safeguard for non-perfect linework. Hidden for now
        # because section networks are expected to be watertight.
        # tolerance_spin = QDoubleSpinBox(dialog)
        # tolerance_spin.setDecimals(4)
        # tolerance_spin.setRange(0.0, 1.0e9)
        # tolerance_spin.setSingleStep(0.1)
        # tolerance_spin.setValue(self._default_section_tolerance(section_uid))
        # form_layout.addRow("Tolerance", tolerance_spin)

        layout.addLayout(form_layout)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        ok_button = buttons.button(QDialogButtonBox.Ok)
        if ok_button is not None:
            ok_button.setText("Build")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.Accepted:
            return

        self.build_section_areas(
            table_name=table_combo.currentText(),
            boundary_uid=boundary_combo.currentData(),
            dom_cut_uid=(
                domxs_cut_combo.currentData()
                if use_domxs_cut_check.isChecked()
                else None
            ),
            use_selected=use_selected_check.isChecked(),
            tolerance=self._default_section_tolerance(section_uid),
            max_missing_boundaries=int(max_missing_spin.value()),
            # tolerance=float(tolerance_spin.value()),
        )

    def build_section_areas(
        self,
        table_name: str,
        boundary_uid: str = FRAME_BOUNDARY_KEY,
        dom_cut_uid: Optional[str] = None,
        use_selected: bool = False,
        tolerance: float = 0.0,
        max_missing_boundaries: Optional[int] = None,
    ) -> None:
        """Build PSC section-area seeds and triangulated fills."""
        try:
            from shapely.geometry import LineString, Polygon
            from shapely.ops import polygonize_full, triangulate, unary_union
        except Exception as exc:
            project = self._pzero_project()
            if project is not None:
                self.print_terminal(f"Build PSC section areas requires Shapely: {exc}")
            return

        project = self._pzero_project()
        if project is None:
            return
        section_uid = getattr(self.host, "this_x_section_uid", "")
        tolerance = max(float(tolerance or 0.0), 0.0)
        if max_missing_boundaries is None:
            max_missing_boundaries = self.MAX_RELAXED_MISSING_BOUNDARIES
        try:
            max_missing_boundaries = max(int(max_missing_boundaries), 0)
        except (TypeError, ValueError):
            max_missing_boundaries = self.MAX_RELAXED_MISSING_BOUNDARIES

        line_uids = self._section_polyline_uids(use_selected=use_selected)
        if not line_uids:
            self.print_terminal("No section XsPolyLine entities selected or available.")
            return

        boundary_polygon = self._boundary_polygon_2d(
            boundary_uid=boundary_uid,
            polygon_cls=Polygon,
            line_cls=LineString,
            polygonize_full=polygonize_full,
            unary_union=unary_union,
        )
        if boundary_polygon is None or boundary_polygon.is_empty:
            self.print_terminal("Could not build a valid section boundary polygon.")
            return

        line_entries = self._section_line_entries(
            line_uids=line_uids,
            boundary_polygon=boundary_polygon,
            line_cls=LineString,
        )
        if not line_entries:
            self.print_terminal(
                "No usable XsPolyLine segment falls inside the selected boundary."
            )
            return

        dom_cut_entries = self._dom_cut_line_entries(
            dom_cut_uid=dom_cut_uid,
            boundary_polygon=boundary_polygon,
            line_cls=LineString,
            tolerance=tolerance,
        )
        if dom_cut_uid and not dom_cut_entries:
            self.print_terminal(
                "Selected DomXs produced no usable section line."
            )
            return

        geologic_network_geometries = [boundary_polygon.boundary] + [
            entry["geometry"] for entry in line_entries
        ]
        match_polygons = []
        if dom_cut_entries:
            (
                match_polygons,
                match_dangle_count,
                match_cut_count,
                match_invalid_count,
                match_coverage_ok,
            ) = self._polygonize_section_network(
                boundary_polygon=boundary_polygon,
                network_geometries=geologic_network_geometries,
                polygonize_full=polygonize_full,
                unary_union=unary_union,
                tolerance=tolerance,
            )
            if (
                match_dangle_count
                or match_cut_count
                or match_invalid_count
                or not match_coverage_ok
            ):
                self.print_terminal(
                    "Section lines are not watertight before DomXs cut "
                    f"(dangles={match_dangle_count}, cuts={match_cut_count}, "
                    f"invalid rings={match_invalid_count}). "
                    "Clean the section with Snap to intersection and retry."
                )
                return

        network_geometries = geologic_network_geometries + [
            entry["geometry"] for entry in dom_cut_entries
        ]
        (
            section_polygons,
            dangle_count,
            cut_count,
            invalid_count,
            coverage_ok,
        ) = self._polygonize_section_network(
            boundary_polygon=boundary_polygon,
            network_geometries=network_geometries,
            polygonize_full=polygonize_full,
            unary_union=unary_union,
            tolerance=tolerance,
        )
        if dom_cut_entries:
            self.print_terminal(
                f"Using DomXs cut with {len(dom_cut_entries)} line part(s). "
                "The cut splits PSC areas/seeds but is not used in STm matching."
            )

        if dangle_count or cut_count or invalid_count or not coverage_ok:
            self.print_terminal(
                "Section lines are not watertight "
                f"(dangles={dangle_count}, cuts={cut_count}, invalid rings={invalid_count}). "
                "Clean the section with Snap to intersection and retry."
            )
            return

        psc_model = self._build_psc_model_from_stm(table_name)
        representative_boundary_keys = self._psc_representative_boundary_keys(
            psc_model
        )
        created_seed_count = 0
        created_area_count = 0
        status_counts = {
            "CERTAIN": 0,
            "LIKELY": 0,
            "AMBIGUOUS": 0,
            "POSSIBLE_REPEAT": 0,
            "UNASSIGNED": 0,
        }
        assigned_counts: Dict[str, int] = {}
        area_infos = []
        match_area_infos = []
        if dom_cut_entries:
            for match_idx, match_polygon in enumerate(match_polygons, start=1):
                match_boundary_labels = self._polygon_boundary_labels(
                    polygon=match_polygon,
                    boundary_polygon=boundary_polygon,
                    line_entries=line_entries,
                    tolerance=tolerance,
                )
                match_area_infos.append(
                    {
                        "area_idx": match_idx,
                        "polygon": match_polygon,
                        "boundary_labels": match_boundary_labels,
                        "candidates": self._section_unit_candidates_for_boundary_labels(
                            psc_model=psc_model,
                            labels=match_boundary_labels,
                            max_missing_boundaries=max_missing_boundaries,
                        ),
                    }
                )

        for area_idx, polygon in enumerate(section_polygons, start=1):
            match_area_info = self._dom_cut_parent_area_info(
                polygon=polygon,
                parent_area_infos=match_area_infos,
            )
            if match_area_info:
                boundary_labels = list(match_area_info.get("boundary_labels", []))
                candidates = list(match_area_info.get("candidates", []) or [])
                dom_cut_parent_area_idx = int(match_area_info.get("area_idx", 0) or 0)
            else:
                boundary_labels = self._polygon_boundary_labels(
                    polygon=polygon,
                    boundary_polygon=boundary_polygon,
                    line_entries=line_entries,
                    tolerance=tolerance,
                )
                candidates = self._section_unit_candidates_for_boundary_labels(
                    psc_model=psc_model,
                    labels=boundary_labels,
                    max_missing_boundaries=max_missing_boundaries,
                )
                dom_cut_parent_area_idx = 0
            area_infos.append(
                {
                    "area_idx": area_idx,
                    "polygon": polygon,
                    "boundary_labels": boundary_labels,
                    "dom_cut_parent_area_idx": dom_cut_parent_area_idx,
                    "dom_cut_side": self._dom_cut_area_side(
                        polygon=polygon,
                        dom_cut_entries=dom_cut_entries,
                        tolerance=tolerance,
                    ),
                    "candidates": candidates,
                }
            )

        assignment_area_infos = match_area_infos if match_area_infos else area_infos
        assignment_results = [None for _area_info in assignment_area_infos]
        for info_idx, area_info in enumerate(assignment_area_infos):
            exact_candidates = [
                candidate
                for candidate in area_info.get("candidates", [])
                if candidate.get("exact")
            ]
            if len(exact_candidates) != 1:
                continue
            candidate = exact_candidates[0]
            if self._section_candidate_repeat_conflict_labels(
                candidate=candidate,
                area_info=area_info,
                area_infos=assignment_area_infos,
                assignments=assignment_results,
                line_entries=line_entries,
                representative_boundary_keys=representative_boundary_keys,
                tolerance=tolerance,
            ):
                continue
            status = (
                "POSSIBLE_REPEAT"
                if assigned_counts.get(candidate["unit_key"], 0)
                else "CERTAIN"
            )
            assignment_results[info_idx] = self._section_assignment_payload(
                candidate=candidate,
                status=status,
                candidate_pool=exact_candidates,
                assigned_counts=assigned_counts,
            )
            assigned_counts[candidate["unit_key"]] = (
                assigned_counts.get(candidate["unit_key"], 0) + 1
            )

        for info_idx, area_info in enumerate(assignment_area_infos):
            if assignment_results[info_idx] is not None:
                continue
            assignment = self._section_best_area_assignment(
                area_info=area_info,
                assigned_counts=assigned_counts,
                area_infos=assignment_area_infos,
                assignments=assignment_results,
                line_entries=line_entries,
                representative_boundary_keys=representative_boundary_keys,
                tolerance=tolerance,
            )
            assignment_results[info_idx] = assignment
            unit_key = assignment.get("unit_key", "")
            if unit_key:
                assigned_counts[unit_key] = assigned_counts.get(unit_key, 0) + 1

        if match_area_infos:
            assignment_by_parent_idx = {
                int(area_info.get("area_idx", 0) or 0): assignment
                for area_info, assignment in zip(match_area_infos, assignment_results)
            }
            assignments = [
                deepcopy(
                    assignment_by_parent_idx.get(
                        int(area_info.get("dom_cut_parent_area_idx", 0) or 0)
                    )
                )
                for area_info in area_infos
            ]
        else:
            assignments = assignment_results

        for area_info, assignment in zip(area_infos, assignments):
            polygon = area_info["polygon"]
            area_idx = int(area_info["area_idx"])
            boundary_labels = area_info.get("boundary_labels", [])
            assignment = assignment or {"status": "UNASSIGNED"}
            dom_cut_side = self._psc_text(area_info.get("dom_cut_side", ""))
            if dom_cut_side:
                assignment = dict(assignment)
                assignment["dom_cut_side"] = dom_cut_side
                assignment["dom_cut_parent_area_idx"] = area_info.get(
                    "dom_cut_parent_area_idx", 0
                )
            status = str(assignment.get("status", "UNASSIGNED"))
            status_counts[status] = status_counts.get(status, 0) + 1
            self._print_section_area_assignment(
                area_idx=area_idx,
                boundary_labels=boundary_labels,
                assignment=assignment,
            )

            unit_info = assignment.get("unit_info")
            if unit_info is None:
                role = "undef"
                feature = "PSC_unassigned"
                unit_name = f"Area_{area_idx}"
            else:
                role = self._psc_unit_role(unit_info.get("unit_role", "TU"))
                feature = self._psc_text(unit_info.get("feature", "")) or "PSC_unit"
                unit_name = self._psc_text(unit_info.get("name", "")) or feature

            color = self._color_for_psc_unit(unit_info, feature)
            if dom_cut_side == "eroded":
                feature = f"{feature}_eroded"
                unit_name = f"{unit_name}_eroded"
                color = self._lighten_rgb_color(color)
            seed_point = polygon.representative_point()
            seed_xyz = project.xsect_coll.plane2world(
                section_uid=section_uid,
                U=float(seed_point.x),
                V=float(seed_point.y),
                as_arr=True,
            )

            area_uid = None
            trisurf = self._triangulated_polygon_surface(
                polygon=polygon,
                triangulate_func=triangulate,
            )
            if trisurf is not None and trisurf.points_number > 0:
                area_uid = self._create_area_surface(
                    name=f"PSC_area_{unit_name}",
                    role=role,
                    feature=feature,
                    vtk_obj=trisurf,
                    color=color,
                )
                if area_uid:
                    created_area_count += 1

            seed_parent_uid = section_uid
            if area_uid:
                seed_parent_uid = self._psc_linked_parent_uid(section_uid, area_uid)
            seed_uid = self._create_seed_vertex(
                name=f"PSC_seed_{unit_name}",
                role=role,
                feature=feature,
                xyz=np.asarray(seed_xyz, dtype=float).reshape(3),
                color=color,
                parent_uid=seed_parent_uid,
            )
            if seed_uid:
                created_seed_count += 1

        self.print_terminal(
            f"Build PSC section areas completed: created {created_seed_count} seed(s), "
            f"{created_area_count} filled area(s), "
            f"unmatched areas={status_counts.get('UNASSIGNED', 0)}. "
            "Assignments: "
            f"CERTAIN={status_counts.get('CERTAIN', 0)}, "
            f"LIKELY={status_counts.get('LIKELY', 0)}, "
            f"AMBIGUOUS={status_counts.get('AMBIGUOUS', 0)}, "
            f"POSSIBLE_REPEAT={status_counts.get('POSSIBLE_REPEAT', 0)}, "
            f"UNASSIGNED={status_counts.get('UNASSIGNED', 0)}."
        )
        self.print_terminal(
            "If ambiguous PSC areas are assigned to the wrong unit, select the "
            "affected polygons and use Modify > Switch PSC areas."
        )
        if dom_cut_entries:
            self.print_terminal(
                "DomXs-divided ambiguous areas should be switched separately for "
                "subsurface and eroded polygons."
            )

    def _default_section_tolerance(self, section_uid: str) -> float:
        "Calculates a geometric tolerance for the active Xsection based on its diagonal length."
        "logic is section diagonal = sqrt(length^2 + height^2), tolerance = max(diagonal * 1e-6, 0.001)"
        project = self._pzero_project()
        try:
            length = float(project.xsect_coll.get_uid_length(section_uid))
            height = float(project.xsect_coll.get_uid_width(section_uid))
            diagonal = float(np.linalg.norm([length, height]))
        except Exception:
            diagonal = 1.0
        return max(diagonal * 1.0e-6, 0.001)

    def _available_boundary_options(self) -> List[Tuple[str, str]]:
        "Returns a list of available boundary options for the active Xsection."
        project = self._pzero_project()
        options = [("Xsection frame", self.FRAME_BOUNDARY_KEY)]
        boundary_coll = getattr(project, "boundary_coll", None)
        if boundary_coll is None:
            return options
        for uid in getattr(boundary_coll, "get_uids", []) or []:
            try:
                name = boundary_coll.get_uid_name(uid)
                topology = boundary_coll.get_uid_topology(uid)
            except Exception:
                continue
            if topology in {"TriSurf", "PolyLine", "XsPolyLine"}:
                options.append((f"{name} ({topology})", uid))
        return options

    def _available_domxs_cut_options(self) -> List[Tuple[str, str]]:
        "Returns a list of available DomXs options for the active Xsection."
        project = self._pzero_project()
        section_uid = getattr(self.host, "this_x_section_uid", "")
        dom_coll = getattr(project, "dom_coll", None)
        if dom_coll is None:
            return []
        options = []
        for uid in getattr(dom_coll, "get_uids", []) or []:
            try:
                name = self._psc_text(dom_coll.get_uid_name(uid)) or uid
                topology = self._psc_text(dom_coll.get_uid_topology(uid))
                parent_uid = self._psc_text(dom_coll.get_uid_x_section(uid))
            except Exception:
                continue
            if topology == "DomXs" and parent_uid == section_uid:
                options.append((name, uid))
        return options

    def _default_domxs_cut_uid(self, domxs_uids: List[str]) -> Optional[str]:
        """Returns the default DomXs cut UID for the active Xsection, preferring any selected DomXs if available."""
        if not domxs_uids:
            return None
        project = self._pzero_project()

        selected_uids = list(getattr(self.host, "selected_uids", []) or [])
        selected_uids.extend(getattr(project, "selected_uids", []) or [])
        for uid in selected_uids:
            if uid in domxs_uids:
                return uid
        return domxs_uids[0]

    def _section_polyline_uids(self, use_selected: bool = False) -> List[str]:
        """Returns a list of XsPolyLine UIDs in the active Xsection, optionally filtered by selection."""
        project = self._pzero_project()
        section_uid = getattr(self.host, "this_x_section_uid", "")
        geol_coll = getattr(project, "geol_coll", None)
        if geol_coll is None or not section_uid:
            return []
        section_uids = []
        for uid in getattr(geol_coll, "get_uids", []) or []:
            try:
                if (
                    geol_coll.get_uid_topology(uid) == "XsPolyLine"
                    and geol_coll.get_uid_x_section(uid) == section_uid
                ):
                    section_uids.append(uid)
            except Exception:
                continue
        if not use_selected:
            return section_uids

        selected = set(getattr(self.host, "selected_uids", []) or [])
        selected.update(getattr(project, "selected_uids", []) or [])
        return [uid for uid in section_uids if uid in selected]

    def _boundary_polygon_2d(
        self,
        boundary_uid: str,
        polygon_cls,
        line_cls,
        polygonize_full,
        unary_union,
    ):
        "Returns a Shapely Polygon representing the section boundary for the given boundary UID."
        project = self._pzero_project()
        section_uid = getattr(self.host, "this_x_section_uid", "")
        if boundary_uid == self.FRAME_BOUNDARY_KEY:
            length = float(project.xsect_coll.get_uid_length(section_uid))
            height = float(project.xsect_coll.get_uid_width(section_uid))
            if abs(length) <= 1.0e-12 or abs(height) <= 1.0e-12:
                self.print_terminal(
                    "Xsection frame boundary is invalid: "
                    f"length={length:.6g}, height={height:.6g}."
                )
                return None
            return polygon_cls(
                [
                    (0.0, 0.0),
                    (length, 0.0),
                    (length, height),
                    (0.0, height),
                    (0.0, 0.0),
                ]
            )

        boundary_coll = getattr(project, "boundary_coll", None)
        if boundary_coll is None or boundary_uid not in boundary_coll.get_uids:
            self.print_terminal("Selected boundary is not available in boundary_coll.")
            return None
        vtk_obj = boundary_coll.get_uid_vtk_obj(boundary_uid)
        topology = boundary_coll.get_uid_topology(boundary_uid)
        boundary_name = self._psc_text(boundary_coll.get_uid_name(boundary_uid))
        self.print_terminal(
            f"Building section boundary from '{boundary_name}' ({topology})."
        )

        if topology == "TriSurf":
            try:
                from pzero.three_d_surfaces import xsection_intersection_polyline_parts

                line_parts = xsection_intersection_polyline_parts(
                    vtk_obj=vtk_obj,
                    vtk_plane=project.xsect_coll.get_uid_vtk_plane(section_uid),
                )
                if not line_parts:
                    self.print_terminal(
                        "Selected TriSurf boundary does not intersect the active Xsection "
                        "as a closed polyline."
                    )
                    return None
                line_strings = []
                for line_part in line_parts:
                    line_strings.extend(
                        self._line_strings_from_polydata(line_part, line_cls)
                    )
            except Exception as exc:
                self.print_terminal(f"Boundary slice failed: {exc}")
                return None
        else:
            line_strings = self._line_strings_from_polydata(vtk_obj, line_cls)

        if not line_strings:
            self.print_terminal(
                "Selected boundary produced no usable projected line strings. "
                "Use the Xsection frame or a boundary that intersects the active section."
            )
            return None
        if len(line_strings) == 1:
            coords = list(line_strings[0].coords)
            if len(coords) >= 4 and np.linalg.norm(np.asarray(coords[0]) - np.asarray(coords[-1])) <= 1.0e-9:
                candidate = polygon_cls(coords)
                if candidate.is_valid and candidate.area > 0.0:
                    return candidate
            self.print_terminal(
                "Selected boundary produced one line, but it is not a valid closed polygon."
            )

        polygons_geom, _dangles, _cuts, _invalids = polygonize_full(unary_union(line_strings))
        polygons = [
            polygon
            for polygon in self._iter_geometries(polygons_geom)
            if polygon.geom_type == "Polygon" and polygon.area > 0.0
        ]
        if not polygons:
            self.print_terminal(
                f"Selected boundary produced {len(line_strings)} line part(s), "
                "but polygonize found no closed boundary loop."
            )
            return None
        return max(polygons, key=lambda polygon: polygon.area)

    def _line_strings_from_polydata(self, vtk_obj, line_cls) -> List[Any]:
        "Returns a list of Shapely LineString objects from the given VTK polydata object, projected into the Xsection plane."
        project = self._pzero_project()
        section_uid = getattr(self.host, "this_x_section_uid", "")
        if vtk_obj is None:
            return []
        try:
            if hasattr(vtk_obj, "points"):
                points = np.asarray(vtk_obj.points, dtype=float)
            elif hasattr(vtk_obj, "GetPoints") and vtk_obj.GetPoints() is not None:
                points = vtk_to_numpy(vtk_obj.GetPoints().GetData()).astype(
                    float, copy=False
                )
            else:
                return []
        except Exception:
            return []
        if points.ndim != 2 or points.shape[0] < 2 or points.shape[1] < 3:
            return []

        try:
            uv_points = project.xsect_coll.world2plane(
                section_uid=section_uid,
                X=points[:, 0],
                Y=points[:, 1],
                Z=points[:, 2],
                as_arr=True,
            )
        except Exception:
            return []
        uv_points = np.asarray(uv_points, dtype=float)

        line_ids = []
        try:
            vtk_lines = vtk_obj.GetLines() if hasattr(vtk_obj, "GetLines") else None
            if (
                vtk_lines is None
                or vtk_lines.GetNumberOfCells() <= 0
                or vtk_lines.GetData() is None
            ):
                flat_lines = np.asarray([], dtype=int)
            else:
                flat_lines = vtk_to_numpy(vtk_lines.GetData()).astype(int, copy=False)
            cursor = 0
            while cursor < flat_lines.size:
                n_ids = int(flat_lines[cursor])
                cursor += 1
                ids = flat_lines[cursor : cursor + n_ids]
                cursor += n_ids
                ids = ids[(ids >= 0) & (ids < uv_points.shape[0])]
                if ids.size >= 2:
                    line_ids.append(ids)
        except Exception:
            line_ids = []
        if not line_ids:
            line_ids = [np.arange(uv_points.shape[0], dtype=int)]

        line_strings = []
        for ids in line_ids:
            coords = uv_points[np.asarray(ids, dtype=int)]
            coords = self._drop_consecutive_duplicate_coords(coords)
            if coords.shape[0] < 2:
                continue
            try:
                line = line_cls(coords[:, :2])
            except Exception:
                continue
            if not line.is_empty and line.length > 0.0:
                line_strings.append(line)
        return line_strings

    @staticmethod
    def _drop_consecutive_duplicate_coords(coords: np.ndarray) -> np.ndarray:
        "Returns a new array of coordinates with consecutive duplicates removed."
        coords = np.asarray(coords, dtype=float)
        if coords.shape[0] <= 1:
            return coords
        keep = [coords[0]]
        for coord in coords[1:]:
            if np.linalg.norm(coord[:2] - keep[-1][:2]) > 1.0e-9:
                keep.append(coord)
        return np.asarray(keep, dtype=float)

    def _section_line_entries(self, line_uids, boundary_polygon, line_cls) -> List[Dict[str, Any]]:
        "Returns a list of line entries for the given XsPolyLine UIDs, clipped to the boundary polygon."
        project = self._pzero_project()
        geol_coll = project.geol_coll
        entries = []
        for uid in line_uids:
            vtk_obj = geol_coll.get_uid_vtk_obj(uid)
            feature = self._psc_text(geol_coll.get_uid_feature(uid))
            if not feature or self._psc_key(feature) == self._psc_key("undef"):
                feature = self._psc_text(geol_coll.get_uid_name(uid))
            if not feature:
                continue
            for line in self._line_strings_from_polydata(vtk_obj, line_cls):
                try:
                    clipped = line.intersection(boundary_polygon)
                except Exception:
                    continue
                for clipped_line in self._iter_line_geometries(clipped):
                    if clipped_line.length > 0.0:
                        entries.append(
                            {
                                "uid": uid,
                                "feature": feature,
                                "geometry": clipped_line,
                            }
                        )
        return entries

    def _dom_cut_line_entries(
        self,
        dom_cut_uid: Optional[str],
        boundary_polygon,
        line_cls,
        tolerance: float,
    ) -> List[Dict[str, Any]]:
        "Returns a list of line entries for the given DomXs cut UID, clipped to the boundary polygon."
        if not dom_cut_uid:
            return []
        project = self._pzero_project()
        dom_coll = getattr(project, "dom_coll", None)
        if dom_coll is None or dom_cut_uid not in getattr(dom_coll, "get_uids", []):
            return []
        try:
            vtk_obj = dom_coll.get_uid_vtk_obj(dom_cut_uid)
            topology = self._psc_text(dom_coll.get_uid_topology(dom_cut_uid))
            name = self._psc_text(dom_coll.get_uid_name(dom_cut_uid))
        except Exception:
            return []

        if topology != "DomXs":
            return []

        entries = []
        min_length = max(float(tolerance or 0.0), 1.0e-9)
        for line in self._line_strings_from_polydata(vtk_obj, line_cls):
            try:
                clipped = line.intersection(boundary_polygon)
            except Exception:
                continue
            for clipped_line in self._iter_line_geometries(clipped):
                if clipped_line.length > min_length:
                    entries.append(
                        {
                            "uid": dom_cut_uid,
                            "feature": name or topology or "DomXs",
                            "geometry": clipped_line,
                        }
                    )
        return entries

    def _dom_cut_area_side(
        self,
        polygon,
        dom_cut_entries: List[Dict[str, Any]],
        tolerance: float,
    ) -> str:
        "Returns 'subsurface' if the polygon is below the DomXs cut, 'eroded' if above, or '' if within tolerance."
        if polygon is None or not dom_cut_entries:
            return ""
        try:
            point = polygon.representative_point()
        except Exception:
            return ""

        nearest_cut_v = None
        nearest_distance = None
        for entry in dom_cut_entries:
            geometry = entry.get("geometry")
            if geometry is None:
                continue
            try:
                projected = geometry.interpolate(geometry.project(point))
                distance = float(point.distance(projected))
            except Exception:
                continue
            if nearest_distance is None or distance < nearest_distance:
                nearest_distance = distance
                nearest_cut_v = float(projected.y)
        if nearest_cut_v is None:
            return ""

        delta_v = float(point.y) - nearest_cut_v
        if abs(delta_v) <= max(float(tolerance or 0.0), 1.0e-9):
            return ""
        # Cross-section V increases down-dip, so larger V is below the DomXs trace.
        return "subsurface" if delta_v > 0.0 else "eroded"

    def _dom_cut_parent_area_info(
        self,
        polygon,
        parent_area_infos: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        "Returns the parent area info that contains the polygon, or the one with the largest overlap, or None."
        if polygon is None or not parent_area_infos:
            return None
        try:
            point = polygon.representative_point()
        except Exception:
            point = None

        best_info = None
        best_overlap = 0.0
        for area_info in parent_area_infos:
            parent_polygon = area_info.get("polygon")
            if parent_polygon is None:
                continue
            try:
                if point is not None and parent_polygon.covers(point):
                    return area_info
                overlap = float(parent_polygon.intersection(polygon).area)
            except Exception:
                continue
            if overlap > best_overlap:
                best_overlap = overlap
                best_info = area_info
        return best_info

    def _polygonize_section_network(
        self,
        boundary_polygon,
        network_geometries: List[Any],
        polygonize_full,
        unary_union,
        tolerance: float,
    ) -> Tuple[List[Any], int, int, int, bool]:
        "Polygonizes the given network geometries and returns the resulting polygons and problem counts."
        noded_network = unary_union(network_geometries)
        polygons_geom, dangles_geom, cuts_geom, invalids_geom = polygonize_full(
            noded_network
        )

        dangle_count = self._problem_edge_count(dangles_geom, tolerance)
        cut_count = self._problem_edge_count(cuts_geom, tolerance)
        invalid_count = len(self._iter_geometries(invalids_geom))
        raw_polygons = [
            polygon
            for polygon in self._iter_geometries(polygons_geom)
            if polygon.geom_type == "Polygon" and polygon.area > 0.0
        ]
        section_polygons = [
            polygon
            for polygon in raw_polygons
            if boundary_polygon.covers(polygon.representative_point())
        ]
        section_polygons = self._unique_polygons(section_polygons)

        coverage_ok = False
        if section_polygons:
            try:
                covered = unary_union(section_polygons)
                area_tolerance = max(
                    boundary_polygon.area * 1.0e-6,
                    float(tolerance or 0.0) * float(tolerance or 0.0),
                )
                coverage_ok = (
                    float(boundary_polygon.difference(covered).area)
                    <= area_tolerance
                    and float(covered.difference(boundary_polygon).area)
                    <= area_tolerance
                )
            except Exception:
                coverage_ok = False
        return section_polygons, dangle_count, cut_count, invalid_count, coverage_ok

    def _polygon_boundary_labels(
        self,
        polygon,
        boundary_polygon,
        line_entries: List[Dict[str, Any]],
        tolerance: float,
    ) -> List[str]:
        "Returns a list of boundary labels for the given polygon, based on its intersection with the boundary polygon and line entries."
        min_length = max(float(tolerance or 0.0), 1.0e-9)
        labels = []
        if self._geometry_length(polygon.boundary.intersection(boundary_polygon.boundary)) > min_length:
            labels.append("Boundary")
        seen = {self._psc_key(label) for label in labels}
        for entry in line_entries:
            feature = self._psc_text(entry.get("feature", ""))
            feature_key = self._psc_key(feature)
            if not feature_key or feature_key in seen:
                continue
            if self._geometry_length(polygon.boundary.intersection(entry["geometry"])) > min_length:
                labels.append(feature)
                seen.add(feature_key)
        return labels

    def _unit_for_boundary_labels(self, psc_model: Dict[str, Any], labels: List[str]):
        "Returns the unit info from the PSC model that matches the given boundary labels, or None if no match is found."
        target_keys = {
            self._psc_key(label)
            for label in labels
            if self._psc_key(label)
        }
        if not target_keys:
            return None
        for unit_info in (psc_model.get("units", {}) or {}).values():
            unit_keys = {
                self._psc_key(boundary)
                for boundary in unit_info.get("boundaries", set()) or set()
                if self._psc_key(boundary)
            }
            if unit_keys == target_keys:
                return unit_info
        return None

    def _section_unit_candidates_for_boundary_labels(
        self,
        psc_model: Dict[str, Any],
        labels: List[str],
        max_missing_boundaries: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        "Returns a list of candidate units from the PSC model that match the given boundary labels, allowing for some missing boundaries."
        if max_missing_boundaries is None:
            max_missing_boundaries = self.MAX_RELAXED_MISSING_BOUNDARIES
        try:
            max_missing_boundaries = max(int(max_missing_boundaries), 0)
        except (TypeError, ValueError):
            max_missing_boundaries = self.MAX_RELAXED_MISSING_BOUNDARIES

        target_labels_by_key: Dict[str, str] = {}
        for label in labels or []:
            label_text = self._psc_text(label)
            label_key = self._psc_key(label_text)
            if label_key and label_key not in target_labels_by_key:
                target_labels_by_key[label_key] = label_text
        target_keys = set(target_labels_by_key)
        if not target_keys:
            return []

        candidates = []
        for unit_info in (psc_model.get("units", {}) or {}).values():
            unit_labels_by_key: Dict[str, str] = {}
            for boundary in unit_info.get("boundaries", set()) or set():
                boundary_text = self._psc_text(boundary)
                boundary_key = self._psc_key(boundary_text)
                if boundary_key and boundary_key not in unit_labels_by_key:
                    unit_labels_by_key[boundary_key] = boundary_text
            unit_keys = set(unit_labels_by_key)
            if not unit_keys:
                continue

            extra_keys = target_keys - unit_keys
            if extra_keys:
                continue
            missing_keys = unit_keys - target_keys
            if len(missing_keys) > max_missing_boundaries:
                continue

            unit_key = str(
                unit_info.get("key")
                or unit_info.get("feature")
                or unit_info.get("name")
                or ""
            )
            if not unit_key:
                continue
            candidates.append(
                {
                    "unit_info": unit_info,
                    "unit_key": unit_key,
                    "exact": not missing_keys,
                    "missing_count": len(missing_keys),
                    "missing_labels": [
                        unit_labels_by_key.get(key, key)
                        for key in sorted(missing_keys)
                    ],
                    "observed_count": len(target_keys),
                    "polarity": self._psc_sort_key(unit_info.get("polarity", "")),
                    "feature": self._psc_text(unit_info.get("feature", "")),
                    "name": self._psc_text(unit_info.get("name", "")),
                }
            )

        return sorted(
            candidates,
            key=lambda candidate: (
                0 if candidate.get("exact") else 1,
                int(candidate.get("missing_count", 0)),
                -int(candidate.get("observed_count", 0)),
                float(candidate.get("polarity", float("inf"))),
                str(candidate.get("feature", "")).casefold(),
                str(candidate.get("unit_key", "")).casefold(),
            ),
        )

    def _section_best_area_assignment(
        self,
        area_info: Dict[str, Any],
        assigned_counts: Dict[str, int],
        area_infos: List[Dict[str, Any]],
        assignments: List[Optional[Dict[str, Any]]],
        line_entries: List[Dict[str, Any]],
        representative_boundary_keys: set,
        tolerance: float,
    ) -> Dict[str, Any]:
        "Returns the best assignment for the given area_info based on candidates and conflict checks."
        candidates = list(area_info.get("candidates", []) or [])
        if not candidates:
            return {"status": "UNASSIGNED"}

        filtered_candidates = []
        blocked_labels = []
        for candidate in candidates:
            conflict_labels = self._section_candidate_repeat_conflict_labels(
                candidate=candidate,
                area_info=area_info,
                area_infos=area_infos,
                assignments=assignments,
                line_entries=line_entries,
                representative_boundary_keys=representative_boundary_keys,
                tolerance=tolerance,
            )
            if conflict_labels:
                blocked_labels.extend(conflict_labels)
                continue
            filtered_candidates.append(candidate)
        candidates = filtered_candidates
        if not candidates:
            return {
                "status": "UNASSIGNED",
                "blocked_repeat_labels": sorted(set(blocked_labels), key=str.casefold),
            }

        best_candidate = candidates[0]
        best_quality = (
            0 if best_candidate.get("exact") else 1,
            int(best_candidate.get("missing_count", 0)),
        )
        best_candidates = [
            candidate
            for candidate in candidates
            if (
                0 if candidate.get("exact") else 1,
                int(candidate.get("missing_count", 0)),
            )
            == best_quality
        ]
        chosen = self._section_choose_candidate(best_candidates, assigned_counts)
        assigned_before = assigned_counts.get(chosen["unit_key"], 0)
        if len(best_candidates) > 1 and assigned_before == 0:
            status = "AMBIGUOUS"
        elif assigned_before > 0:
            status = "POSSIBLE_REPEAT"
        elif chosen.get("exact"):
            status = "CERTAIN"
        else:
            status = "LIKELY"
        return self._section_assignment_payload(
            candidate=chosen,
            status=status,
            candidate_pool=best_candidates,
            assigned_counts=assigned_counts,
        )

    def _section_choose_candidate(
        self,
        candidates: List[Dict[str, Any]],
        assigned_counts: Dict[str, int],
    ) -> Dict[str, Any]:
        "Chooses the best candidate from the list based on assigned counts, polarity, feature, and unit_key."
        return min(
            candidates,
            key=lambda candidate: (
                assigned_counts.get(candidate.get("unit_key", ""), 0),
                float(candidate.get("polarity", float("inf"))),
                str(candidate.get("feature", "")).casefold(),
                str(candidate.get("unit_key", "")).casefold(),
            ),
        )

    def _section_assignment_payload(
        self,
        candidate: Dict[str, Any],
        status: str,
        candidate_pool: List[Dict[str, Any]],
        assigned_counts: Dict[str, int],
    ) -> Dict[str, Any]:
        "Returns a dictionary containing the assignment payload for the given candidate, status, and candidate pool."
        candidate_pool = list(candidate_pool or [candidate])
        return {
            "status": status,
            "unit_info": candidate.get("unit_info"),
            "unit_key": candidate.get("unit_key", ""),
            "missing_labels": list(candidate.get("missing_labels", []) or []),
            "candidate_names": [
                self._section_unit_display_name(item.get("unit_info", {}))
                for item in candidate_pool
            ],
            "assigned_before": int(
                assigned_counts.get(candidate.get("unit_key", ""), 0)
            ),
            "exact": bool(candidate.get("exact")),
        }

    def _section_candidate_repeat_conflict_labels(
        self,
        candidate: Dict[str, Any],
        area_info: Dict[str, Any],
        area_infos: List[Dict[str, Any]],
        assignments: List[Optional[Dict[str, Any]]],
        line_entries: List[Dict[str, Any]],
        representative_boundary_keys: set,
        tolerance: float,
    ) -> List[str]:
        "Returns a list of boundary labels that conflict with the candidate's unit assignment across adjacent areas."
        unit_key = str(candidate.get("unit_key", ""))
        if not unit_key:
            return []

        conflict_labels = []
        for other_area_info, assignment in zip(area_infos, assignments):
            if not assignment or assignment.get("unit_key", "") != unit_key:
                continue
            shared_labels = self._section_shared_boundary_labels(
                polygon=area_info.get("polygon"),
                other_polygon=other_area_info.get("polygon"),
                line_entries=line_entries,
                tolerance=tolerance,
            )
            for label in shared_labels:
                label_key = self._psc_key(label)
                if not label_key:
                    continue
                # Only the immutable, colored representative links separate
                # repeated unit assignments. Manually linked boundaries do not.
                if label_key in representative_boundary_keys:
                    conflict_labels.append(self._psc_text(label))

        return sorted(set(conflict_labels), key=str.casefold)

    def _section_shared_boundary_labels(
        self,
        polygon,
        other_polygon,
        line_entries: List[Dict[str, Any]],
        tolerance: float,
    ) -> List[str]:
        "Returns a list of boundary labels that are shared between the two polygons, based on their intersection with line entries."
        if polygon is None or other_polygon is None:
            return []
        min_length = max(float(tolerance or 0.0), 1.0e-9)
        try:
            shared_boundary = polygon.boundary.intersection(other_polygon.boundary)
        except Exception:
            return []
        if self._geometry_length(shared_boundary) <= min_length:
            return []

        labels = []
        seen = set()
        for entry in line_entries:
            feature = self._psc_text(entry.get("feature", ""))
            feature_key = self._psc_key(feature)
            if not feature_key or feature_key in seen:
                continue
            try:
                shared_length = self._geometry_length(
                    shared_boundary.intersection(entry["geometry"])
                )
            except Exception:
                continue
            if shared_length > min_length:
                labels.append(feature)
                seen.add(feature_key)
        return labels

    def _section_unit_display_name(self, unit_info: Dict[str, Any]) -> str:
        return (
            self._psc_text(unit_info.get("name", ""))
            or self._psc_text(unit_info.get("feature", ""))
            or "PSC_unit"
        )

    def _format_section_labels(self, labels: List[str]) -> str:
        return ", ".join(self._psc_text(label) for label in labels or []) or "-"

    def _print_section_area_assignment(
        self,
        area_idx: int,
        boundary_labels: List[str],
        assignment: Dict[str, Any],
    ) -> None:
        "Prints the assignment status and details for a given area in the section."
        status = str(assignment.get("status", "UNASSIGNED"))
        details = [f"boundaries={self._format_section_labels(boundary_labels)}"]
        missing_labels = assignment.get("missing_labels", []) or []
        if missing_labels:
            details.append(f"missing={self._format_section_labels(missing_labels)}")
        dom_cut_side = self._psc_text(assignment.get("dom_cut_side", ""))
        if dom_cut_side:
            details.append(f"DomXs={dom_cut_side}")
        dom_cut_parent_area_idx = int(
            assignment.get("dom_cut_parent_area_idx", 0) or 0
        )
        if dom_cut_parent_area_idx:
            details.append(f"STm match area={dom_cut_parent_area_idx}")
        candidate_names = assignment.get("candidate_names", []) or []
        if len(candidate_names) > 1:
            details.append(f"candidates={', '.join(candidate_names)}")
        assigned_before = int(assignment.get("assigned_before", 0) or 0)
        if assigned_before:
            details.append(f"already assigned={assigned_before}")
        blocked_repeat_labels = assignment.get("blocked_repeat_labels", []) or []
        if blocked_repeat_labels:
            details.append(
                "blocked repeat across="
                f"{self._format_section_labels(blocked_repeat_labels)}"
            )

        unit_info = assignment.get("unit_info")
        if unit_info is None:
            self.print_terminal(
                f"Area {area_idx}: {status} | " + " | ".join(details)
            )
            return

        self.print_terminal(
            f"Area {area_idx}: {status} -> "
            f"{self._section_unit_display_name(unit_info)} | "
            + " | ".join(details)
        )

    def _color_for_psc_unit(
        self,
        unit_info: Optional[Dict[str, Any]],
        feature: str,
    ) -> Optional[List[float]]:
        "Returns the RGB color for the given PSC unit info, or falls back to the legend color for the feature."
        if unit_info is not None:
            try:
                return [
                    max(0.0, min(255.0, float(unit_info.get("color_R")))),
                    max(0.0, min(255.0, float(unit_info.get("color_G")))),
                    max(0.0, min(255.0, float(unit_info.get("color_B")))),
                ]
            except (TypeError, ValueError):
                pass
        return self._legend_color_for_feature(feature)

    @staticmethod
    def _lighten_rgb_color(
        color: Optional[List[float]],
        factor: float = 0.45,
    ) -> Optional[List[float]]:
        "Returns a lightened version of the given RGB color by the specified factor."
        if color is None:
            return None
        try:
            rgb = [max(0.0, min(255.0, float(value))) for value in color[:3]]
        except (TypeError, ValueError):
            return None
        factor = max(0.0, min(1.0, float(factor)))
        return [value + (255.0 - value) * factor for value in rgb]

    def _legend_color_for_feature(self, feature: str) -> Optional[List[float]]:
        "Returns the RGB color for the given feature from the legend DataFrame, or None if not found."
        project = self._pzero_project()
        legend_df = getattr(project.geol_coll, "legend_df", None)
        if legend_df is None or legend_df.empty:
            return None
        feature_key = self._psc_key(feature)
        for _, row in legend_df.iterrows():
            if self._psc_key(row.get("feature", "")) != feature_key:
                continue
            try:
                return [
                    float(row.get("color_R", 255)),
                    float(row.get("color_G", 255)),
                    float(row.get("color_B", 255)),
                ]
            except (TypeError, ValueError):
                return None
        return None

    def _create_seed_vertex(
        self,
        name: str,
        role: str,
        feature: str,
        xyz: np.ndarray,
        color: Optional[List[float]] = None,
        parent_uid: Optional[str] = None,
    ) -> Optional[str]:
        "Creates a seed vertex entity in the project with the given name, role, feature, and coordinates."
        from pzero.entities_factory import XsVertexSet

        project = self._pzero_project()
        section_uid = getattr(self.host, "this_x_section_uid", "")
        seed_dict = deepcopy(project.geol_coll.entity_dict)
        seed_dict["name"] = name
        seed_dict["parent_uid"] = parent_uid or section_uid
        seed_dict["topology"] = "XsVertexSet"
        seed_dict["role"] = (
            "undef" if self._psc_key(role) == "undef" else self._psc_unit_role(role)
        )
        seed_dict["feature"] = feature
        seed_dict["vtk_obj"] = XsVertexSet(x_section_uid=section_uid, parent=project)
        seed_dict["vtk_obj"].points = np.asarray([xyz], dtype=float)
        seed_dict["vtk_obj"].auto_cells()
        return project.geol_coll.add_entity_from_dict(entity_dict=seed_dict, color=color)

    def _create_area_surface(
        self,
        name: str,
        role: str,
        feature: str,
        vtk_obj,
        color: Optional[List[float]] = None,
    ) -> Optional[str]:
        "Creates an area surface entity in the project with the given name, role, feature, and VTK object."
        project = self._pzero_project()
        section_uid = getattr(self.host, "this_x_section_uid", "")
        area_dict = deepcopy(project.geol_coll.entity_dict)
        area_dict["name"] = name
        area_dict["parent_uid"] = section_uid
        area_dict["topology"] = "TriSurf"
        area_dict["role"] = (
            "undef" if self._psc_key(role) == "undef" else self._psc_unit_role(role)
        )
        area_dict["feature"] = feature
        area_dict["vtk_obj"] = vtk_obj
        area_dict["properties_names"] = list(getattr(vtk_obj, "point_data_keys", []) or [])
        area_dict["properties_components"] = [
            vtk_obj.get_point_data_shape(key)[1] for key in area_dict["properties_names"]
        ]
        return project.geol_coll.add_entity_from_dict(entity_dict=area_dict, color=color)

    @staticmethod
    def _psc_linked_parent_uid(section_uid: str, linked_uid: str) -> str:
        "Returns a combined UID string for the section and linked parent, or just the section UID if linked is empty."
        return ";".join(
            str(uid).strip()
            for uid in (section_uid, linked_uid)
            if str(uid).strip()
        )

    def _triangulated_polygon_surface(self, polygon, triangulate_func):
        "Returns a TriSurf object representing the triangulated surface of the given polygon, or None if triangulation fails."
        from pzero.entities_factory import TriSurf

        project = self._pzero_project()
        section_uid = getattr(self.host, "this_x_section_uid", "")
        triangles_uv = []
        for triangle in triangulate_func(polygon):
            if triangle.is_empty:
                continue
            if not polygon.covers(triangle.representative_point()):
                continue
            coords = np.asarray(list(triangle.exterior.coords)[:3], dtype=float)
            if coords.shape == (3, 2):
                triangles_uv.append(coords)
        if not triangles_uv:
            return None

        vertex_keys: Dict[Tuple[float, float], int] = {}
        vertices_uv = []
        triangles = []
        for coords in triangles_uv:
            tri_ids = []
            for coord in coords:
                key = (round(float(coord[0]), 8), round(float(coord[1]), 8))
                if key not in vertex_keys:
                    vertex_keys[key] = len(vertices_uv)
                    vertices_uv.append([float(coord[0]), float(coord[1])])
                tri_ids.append(vertex_keys[key])
            if len(set(tri_ids)) == 3:
                triangles.append(tri_ids)
        if not vertices_uv or not triangles:
            return None

        vertices_uv = np.asarray(vertices_uv, dtype=float)
        vertices_xyz = project.xsect_coll.plane2world(
            section_uid=section_uid,
            U=vertices_uv[:, 0],
            V=vertices_uv[:, 1],
            as_arr=True,
        )
        vertices_xyz = np.asarray(vertices_xyz, dtype=float)

        trisurf = TriSurf()
        vtk_points = vtkPoints()
        for point in vertices_xyz:
            vtk_points.InsertNextPoint(float(point[0]), float(point[1]), float(point[2]))
        vtk_cells = vtkCellArray()
        for tri_ids in triangles:
            vtk_triangle = vtkTriangle()
            vtk_triangle.GetPointIds().SetId(0, int(tri_ids[0]))
            vtk_triangle.GetPointIds().SetId(1, int(tri_ids[1]))
            vtk_triangle.GetPointIds().SetId(2, int(tri_ids[2]))
            vtk_cells.InsertNextCell(vtk_triangle)
        trisurf.SetPoints(vtk_points)
        trisurf.SetPolys(vtk_cells)
        try:
            trisurf.vtk_set_normals()
        except Exception:
            pass
        return trisurf

    def _problem_edge_count(self, geometry, tolerance: float) -> int:
        "Returns the count of line geometries in the given geometry that have a length greater than the specified tolerance."
        min_length = max(float(tolerance or 0.0), 1.0e-9)
        return sum(
            1
            for line in self._iter_line_geometries(geometry)
            if getattr(line, "length", 0.0) > min_length
        )

    def _iter_geometries(self, geometry) -> List[Any]:
        "Recursively iterates through the given geometry and returns a flat list of all contained geometries."
        if geometry is None or getattr(geometry, "is_empty", True):
            return []
        if hasattr(geometry, "geoms"):
            out = []
            for child in geometry.geoms:
                out.extend(self._iter_geometries(child))
            return out
        return [geometry]

    def _iter_line_geometries(self, geometry) -> List[Any]:
        "Returns a list of all line geometries contained in the given geometry."
        return [
            geom
            for geom in self._iter_geometries(geometry)
            if geom.geom_type in {"LineString", "LinearRing"}
        ]

    def _geometry_length(self, geometry) -> float:
        "Returns the total length of the given geometry, summing lengths of all contained line geometries."
        if geometry is None or getattr(geometry, "is_empty", True):
            return 0.0
        try:
            return float(geometry.length)
        except Exception:
            return sum(float(getattr(geom, "length", 0.0)) for geom in self._iter_geometries(geometry))

    def _unique_polygons(self, polygons: List[Any]) -> List[Any]:
        "Returns a list of unique polygons from the given list, sorted by area and bounds."
        seen = set()
        unique = []
        for polygon in polygons:
            try:
                key = polygon.wkb
            except Exception:
                key = repr(polygon)
            if key in seen:
                continue
            seen.add(key)
            unique.append(polygon)
        return sorted(unique, key=lambda poly: (-poly.area, poly.bounds))
