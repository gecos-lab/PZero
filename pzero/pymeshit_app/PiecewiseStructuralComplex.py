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
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)



class PiecewiseStructuralComplex:
    """Controller for PSC preview, seed placement, and material assignment."""

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
            "Select an STm table. The preview maps STm unit-boundary connections "
            "to the conforming surfaces loaded in the Tetra Mesh tab."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
    
        selector_layout = QHBoxLayout()
        selector_layout.addWidget(QLabel("STm table"))
        table_combo = QComboBox(dialog)
        table_combo.addItems(stm_tables)
        selector_layout.addWidget(table_combo, 1)
        swap_seed_button = QPushButton("Swap selected seeds", dialog)
        swap_seed_button.setToolTip(
            "Select two ambiguous units in the preview table and swap their seed coordinates."
        )
        selector_layout.addWidget(swap_seed_button)
        clear_seed_swaps_button = QPushButton("Clear swaps", dialog)
        clear_seed_swaps_button.setToolTip(
            "Remove saved PSC seed swaps for the selected STm table."
        )
        selector_layout.addWidget(clear_seed_swaps_button)
        layout.addLayout(selector_layout)
    
        preview_table = QTableWidget(0, 6, dialog)
        preview_table.setHorizontalHeaderLabels(
            ["Unit", "Unit Role", "Boundaries", "Matched surfaces", "Seed point", "Missing"]
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
        seed_overrides: Dict[str, List[float]] = {}
    
        def unit_seed_key(unit_info: Dict[str, Any]) -> str:
            return str(
                unit_info.get("key")
                or unit_info.get("name")
                or unit_info.get("feature")
                or ""
            )
    
        def load_seed_overrides(table_name: str) -> None:
            seed_overrides.clear()
            project = self._pzero_project()
            options = {}
            if project is not None:
                options = getattr(project, "custom_table_options", {}).get(table_name, {}) or {}
            raw_overrides = options.get("psc_seed_overrides", {})
            if not isinstance(raw_overrides, dict):
                return
            for unit_key, seed_point in raw_overrides.items():
                try:
                    coords = [float(value) for value in list(seed_point)[:3]]
                except (TypeError, ValueError):
                    continue
                if len(coords) == 3 and all(np.isfinite(coords)):
                    seed_overrides[str(unit_key)] = coords
    
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
                    unit_key: [float(value) for value in seed_point[:3]]
                    for unit_key, seed_point in seed_overrides.items()
                }
            else:
                options.pop("psc_seed_overrides", None)
            table_options[table_name] = options
    
        def apply_seed_overrides(mapping: Dict[str, Any]) -> None:
            for unit_info in mapping.get("units", []) or []:
                unit_key = unit_seed_key(unit_info)
                if unit_key in seed_overrides:
                    unit_info["seed_point"] = list(seed_overrides[unit_key])
                    unit_info["seed_override"] = True
    
        def refresh_preview():
            table_name = table_combo.currentText()
            psc_model = self._build_psc_model_from_stm(table_name)
            mapping = self._map_psc_boundaries_to_tetra_surfaces(psc_model)
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
                for row_idx, unit_info in enumerate(rows):
                    boundaries = unit_info.get("boundaries", [])
                    matched_surfaces = unit_info.get("matched_surfaces", [])
                    missing_boundaries = unit_info.get("missing_boundaries", [])
                    missing_count += len(missing_boundaries)
                    unit_key = unit_seed_key(unit_info)
                    if unit_key in seed_overrides:
                        seed_points = [list(seed_overrides[unit_key])]
                        unit_info["seed_point"] = seed_points[0]
                        unit_info["seed_points"] = seed_points
                        unit_info["seed_override"] = True
                    else:
                        seed_points = self._psc_seed_points_for_unit(
                            unit_info,
                            psc_model,
                            rows,
                        )
                        unit_info["seed_points"] = seed_points
                        unit_info["seed_point"] = seed_points[0] if seed_points else None
                    seed_location_count += len(seed_points or [])
                    seed_text = self._psc_format_seed_list(seed_points)
                    if unit_info.get("seed_override") and seed_text:
                        seed_text += " *"
                    values = [
                        unit_info.get("feature", ""),
                        unit_info.get("unit_role", ""),
                        ", ".join(boundaries),
                        ", ".join(matched_surfaces),
                        seed_text,
                        ", ".join(missing_boundaries),
                    ]
                    for col_idx, value in enumerate(values):
                        item = QTableWidgetItem(str(value))
                        if col_idx == 4 and unit_info.get("seed_override"):
                            item.setToolTip("Seed swapped manually in this PSC dialog.")
                            item.setForeground(QColor(40, 95, 170))
                        if col_idx == 5 and missing_boundaries:
                            item.setForeground(QColor(190, 40, 40))
                        preview_table.setItem(row_idx, col_idx, item)
            finally:
                self._psc_side_context = previous_side_context
    
            status_label.setText(
                f"Units: {len(rows)} | "
                f"Seed locations: {seed_location_count} | "
                f"Known boundaries: {len(psc_model.get('boundary_features', set()))} | "
                f"Missing matches: {missing_count} | "
                f"Saved seed swaps: {len(seed_overrides)}"
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
            first_seed = first_unit.get("seed_point")
            second_seed = second_unit.get("seed_point")
            if first_seed is None or second_seed is None:
                self.print_terminal("Both selected units need a valid seed before swapping.")
                return
            first_key = unit_seed_key(first_unit)
            second_key = unit_seed_key(second_unit)
            seed_overrides[first_key] = [float(value) for value in second_seed[:3]]
            seed_overrides[second_key] = [float(value) for value in first_seed[:3]]
            save_seed_overrides(table_combo.currentText())
            refresh_preview()
    
        def clear_seed_overrides():
            if not seed_overrides:
                return
            seed_overrides.clear()
            save_seed_overrides(table_combo.currentText())
            refresh_preview()
    
        def on_table_changed():
            load_seed_overrides(table_combo.currentText())
            refresh_preview()
    
        swap_seed_button.clicked.connect(swap_selected_seeds)
        clear_seed_swaps_button.clicked.connect(clear_seed_overrides)
        table_combo.currentTextChanged.connect(lambda _text: on_table_changed())
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
        )
        if assigned_count == 0:
            self.print_terminal(
                "No PSC unit could be assigned. Check that STm boundaries match the loaded tetra surfaces."
            )
            return
    
        seed_count = int(getattr(self, "_psc_last_seed_count", assigned_count))
        self.print_terminal(
            f"Assigned {assigned_count} material(s) with "
            f"{seed_count} seed location(s) from STm table '{table_name}'."
            + (f" Skipped {skipped_count} unit(s) without a valid seed." if skipped_count else "")
        )
    
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
    
    @staticmethod
    def _psc_sort_key(value: Any) -> float:
        """Return a numeric STm polarity key."""
        try:
            return float(value)
        except (TypeError, ValueError):
            return float("inf")
    
    @staticmethod
    def _psc_domain_columns(dataframe) -> List[str]:
        """Return STm domain columns ordered by their numeric suffix."""
        if dataframe is None:
            return []
    
        def domain_order(column_name: str) -> Optional[int]:
            text = str(column_name or "").strip()
            if text == "Domain":
                return 1
            if not text.startswith("Domain_"):
                return None
            try:
                return int(text.split("_", 1)[1])
            except (IndexError, ValueError):
                return None
    
        return sorted(
            [
                str(column_name)
                for column_name in dataframe.columns.tolist()
                if domain_order(column_name) is not None
            ],
            key=lambda column_name: domain_order(column_name) or 1,
        )
    
    def _build_psc_model_from_stm(self, table_name: str) -> Dict[str, Any]:
        """Read units, boundaries, and generated connections from an STm table."""
        project = self._pzero_project()
        if project is None:
            return {"units": {}, "boundary_features": set(), "boundary_order": []}
    
        table_df = getattr(project, "custom_tables", {}).get(table_name)
        options = getattr(project, "custom_table_options", {}).get(table_name, {}) or {}
        units: Dict[str, Dict[str, Any]] = {}
        boundary_features = set()
        boundary_order = []
    
        if table_df is not None:
            domain_columns = self._psc_domain_columns(table_df)
            for row_idx, row in table_df.iterrows():
                feature = self._psc_text(row.get("Feature", ""))
                unit_role = self._psc_text(row.get("Unit Role", "NonVolumetric")) or "NonVolumetric"
                polarity = self._psc_sort_key(row.get("Structural Polarity", ""))
                domains = [
                    self._psc_text(row.get(column_name, ""))
                    for column_name in domain_columns
                    if self._psc_text(row.get(column_name, ""))
                ]
                if not feature:
                    continue
                boundary_features.add(feature)
                boundary_order.append(
                    {
                        "feature": feature,
                        "polarity": polarity,
                        "row_index": len(boundary_order),
                        "unit_role": unit_role,
                        "domains": domains,
                    }
                )
                if unit_role == "NonVolumetric":
                    continue
                unit_key = f"unit:{feature}"
                unit_name = f"{feature}_{unit_role}"
                units[unit_key] = {
                    "key": unit_key,
                    "name": unit_name,
                    "feature": feature,
                    "unit_role": unit_role,
                    "polarity": polarity,
                    "domains": domains,
                    "boundaries": {feature},
                    "source": "table",
                }
    
        for unit_info in options.get("manual_units", []):
            if not isinstance(unit_info, dict):
                continue
            unit_id = str(unit_info.get("id", "")).strip()
            feature = self._psc_text(unit_info.get("feature", ""))
            unit_role = self._psc_text(unit_info.get("unit_role", "SU")) or "SU"
            if not unit_id or not feature:
                continue
            domains = [
                self._psc_text(domain_info.get("value", ""))
                for domain_info in unit_info.get("domains", [])
                if isinstance(domain_info, dict) and self._psc_text(domain_info.get("value", ""))
            ]
            unit_key = f"unit:manual:{unit_id}"
            units[unit_key] = {
                "key": unit_key,
                "name": f"{feature}_{unit_role}",
                "feature": feature,
                "unit_role": unit_role,
                "polarity": self._psc_sort_key(unit_info.get("structural_polarity", "")),
                "domains": domains,
                "boundaries": set(),
                "source": "extra",
            }
    
        for connection in options.get("manual_connections", []):
            if not isinstance(connection, dict):
                continue
            unit_key = str(connection.get("unit", "")).strip()
            surface_key = str(connection.get("surface", "")).strip()
            if unit_key not in units:
                continue
            boundary_feature = self._boundary_feature_from_psc_surface_key(surface_key)
            if not boundary_feature:
                continue
            units[unit_key]["boundaries"].add(boundary_feature)
            boundary_features.add(boundary_feature)
    
        model = {
            "table_name": table_name,
            "units": units,
            "boundary_features": boundary_features,
            "boundary_order": list(boundary_order),
        }
        return model
    
    @staticmethod
    def _boundary_feature_from_psc_surface_key(surface_key: str) -> str:
        """Convert an STm builder surface key into a boundary feature name."""
        surface_key = str(surface_key or "").strip()
        if surface_key == "surface:boundary":
            return "Boundary"
        prefix = "surface:"
        if surface_key.startswith(prefix):
            return surface_key[len(prefix):].strip()
        return ""
    
    def _map_psc_boundaries_to_tetra_surfaces(self, psc_model: Dict[str, Any]) -> Dict[str, Any]:
        """Map PSC boundary features to loaded tetra-surface metadata."""
        feature_to_surfaces: Dict[str, List[Dict[str, Any]]] = {}
        boundary_surface_entries = []
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
                    "unit_role": unit.get("unit_role", ""),
                    "polarity": unit.get("polarity", float("inf")),
                    "domains": list(unit.get("domains", [])),
                    "boundaries": boundaries,
                    "matched_surfaces": sorted(set(matched_surfaces), key=str.casefold),
                    "matched_surface_indices": sorted(set(matched_surface_indices), key=lambda value: str(value)),
                    "model_boundary_indices": sorted(set(model_boundary_indices), key=lambda value: str(value)),
                    "boundary_surface_indices": boundary_surface_indices,
                    "missing_boundaries": missing_boundaries,
                    "source": unit.get("source", ""),
                }
            )
    
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
        """Return loaded tetra surface indices that match one STm boundary feature."""
        key = self._psc_key(boundary_feature)
        try:
            border_indices = set(self._get_border_surface_indices())
        except Exception:
            border_indices = set()
    
        matches = []
        for surface_idx, surface_info in getattr(self, "tetra_surface_data", {}).items():
            try:
                surface_idx_value = int(surface_idx)
            except (TypeError, ValueError):
                continue
    
            if key == self._psc_key("Boundary"):
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
    
        return sorted(set(matches))
    
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
    
    def _psc_volumetric_feature_keys(self, psc_model: Dict[str, Any]) -> set:
        """Return feature keys that own a volumetric STm unit."""
        units = psc_model.get("units", {}) or {}
        unit_values = units.values() if isinstance(units, dict) else units
        boundary_key = self._psc_key("Boundary")
        return {
            self._psc_key(unit_info.get("feature", ""))
            for unit_info in unit_values
            if isinstance(unit_info, dict)
            and self._psc_key(unit_info.get("feature", ""))
            and self._psc_key(unit_info.get("feature", "")) != boundary_key
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
    
        volumetric_feature_keys = self._psc_volumetric_feature_keys(psc_model)
        representative_surfaces: Dict[Tuple[str, int], Dict[str, Any]] = {}
        for unit_info in mapped_units:
            boundary_indices = unit_info.get("boundary_surface_indices", {}) or {}
            for boundary, surface_indices in boundary_indices.items():
                boundary_key = self._psc_key(boundary)
                if not boundary_key or boundary_key == self._psc_key("Boundary"):
                    continue
                if boundary_key not in volumetric_feature_keys:
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
                if self._psc_key(unit_info.get("feature", "")) == boundary_key:
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
        unit_feature_key = self._psc_key(unit_info.get("feature", ""))
        side_context = getattr(self, "_psc_side_context", {}) or {}
        representative_signs = side_context.get("representative_unit_signs", {}) or {}
        volumetric_feature_keys = self._psc_volumetric_feature_keys(psc_model)
    
        for boundary_key, boundary_info in target_surface_map.items():
            if boundary_key == self._psc_key("Boundary"):
                continue
            if boundary_key not in volumetric_feature_keys:
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
                desired_sign = owner_sign if unit_feature_key == boundary_key else -owner_sign
                constraints.append(
                    {
                        "surface_idx": surface_idx,
                        "sign": desired_sign,
                        "label": boundary_info.get("label", boundary_key),
                        "reason": "representative-own-side"
                        if unit_feature_key == boundary_key
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
    ) -> np.ndarray:
        """Choose a seed whose nearest-boundary signature matches the STM unit topology."""
        bounds = self._psc_domain_bounds()
        if bounds is None:
            return reference_seed
    
        unit_boundaries = self._psc_target_boundaries_for_unit(unit_info)
        structural_boundaries = [
            boundary
            for boundary in unit_boundaries
            if self._psc_key(boundary) != self._psc_key("Boundary")
        ]
        if len(structural_boundaries) >= 2:
            target_boundaries = structural_boundaries
        else:
            target_boundaries = unit_boundaries
        boundary_as_context_only = (
            len(structural_boundaries) >= 2
            and any(
                self._psc_key(boundary) == self._psc_key("Boundary")
                for boundary in unit_boundaries
            )
        )
        target_surface_map = self._psc_surface_indices_for_boundaries(target_boundaries)
        if not target_surface_map:
            return reference_seed
    
        feature_candidates = list(psc_model.get("boundary_features", set()) or [])
        feature_candidates.extend(target_boundaries)
        feature_surface_map: Dict[str, Dict[str, Any]] = {}
        for boundary in feature_candidates:
            boundary_text = self._psc_text(boundary)
            boundary_key = self._psc_key(boundary_text)
            if not boundary_key:
                continue
            if boundary_as_context_only and boundary_key == self._psc_key("Boundary"):
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
        candidate_points = self._psc_seed_candidate_points(
            reference_seed,
            target_surface_indices,
            bounds,
            side_constraints,
            broad_sampling=int(unit_info.get("ambiguity_group_size", 1) or 1) > 1,
        )
        if candidate_points.shape[0] == 0:
            return reference_seed
    
        distance_arrays = self._psc_feature_distance_arrays(candidate_points, feature_surface_map)
        if not distance_arrays:
            return reference_seed
    
        target_set = set(target_keys)
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
            closest_count = min(len(target_set), len(ranked_keys))
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
        target_labels = [label_by_key.get(key, key) for key in target_keys]
        closest_labels = [
            label_by_key.get(key, key)
            for key in best_details.get("closest_keys", [])
        ]
        unit_info["seed_topology_signature"] = {
            "target": target_labels,
            "closest": closest_labels,
            "exact": bool(best_details.get("exact_signature", False)),
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
            seed = self._psc_seed_between_structural_surfaces(surface_indices, psc_model)
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
    
        refined_seed = self._psc_refine_seed_by_topology_signature(
            unit_info,
            psc_model,
            np.asarray(reference_seed, dtype=float),
            require_side_match=require_side_match,
        )
        if require_side_match and not unit_info.get("seed_topology_signature"):
            return None
        return [float(refined_seed[0]), float(refined_seed[1]), float(refined_seed[2])]
    
    def _psc_seed_points_for_unit(
        self,
        unit_info: Dict[str, Any],
        psc_model: Dict[str, Any],
        mapped_units: Optional[List[Dict[str, Any]]] = None,
    ) -> List[List[float]]:
        """Compute one or more PSC seed points for a mapped STm unit."""
        if unit_info.get("seed_override") and unit_info.get("seed_point") is not None:
            try:
                seed_point = [
                    float(value)
                    for value in list(unit_info.get("seed_point", []))[:3]
                ]
            except (TypeError, ValueError):
                return []
            if len(seed_point) == 3 and all(np.isfinite(seed_point)):
                unit_info["seed_points"] = [seed_point]
                return [seed_point]
            return []
    
        local_boundary_sets = self._psc_local_boundary_sets_for_unit(
            unit_info,
            mapped_units or [],
        )
        seed_points: List[List[float]] = []
        seed_signatures = []
        bounds = self._psc_domain_bounds()
        duplicate_tolerance = 1e-6
        if bounds is not None:
            duplicate_tolerance = max(
                float(np.linalg.norm(bounds[1] - bounds[0])) * 1e-6,
                1e-6,
            )
    
        def add_seed(
            seed_point: Optional[List[float]],
            signature: Dict[str, Any],
            local_boundaries: List[str],
        ) -> None:
            if seed_point is None:
                return
            try:
                coords = [float(value) for value in list(seed_point)[:3]]
            except (TypeError, ValueError):
                return
            if len(coords) != 3 or not all(np.isfinite(coords)):
                return
            candidate = np.asarray(coords, dtype=float)
            for existing in seed_points:
                if np.linalg.norm(candidate - np.asarray(existing, dtype=float)) <= duplicate_tolerance:
                    return
            seed_points.append(coords)
            seed_signatures.append(
                {
                    "boundaries": list(local_boundaries),
                    "signature": dict(signature or {}),
                }
            )
    
        if local_boundary_sets:
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
                add_seed(
                    local_seed,
                    local_info.get("seed_topology_signature", {}) or {},
                    local_boundaries,
                )
    
            if seed_points:
                unit_info["seed_points"] = seed_points
                unit_info["seed_point"] = seed_points[0]
                unit_info["seed_topology_signatures"] = seed_signatures
                unit_info["seed_topology_signature"] = seed_signatures[0].get("signature", {})
                return seed_points
    
            unit_info["seed_points"] = []
            unit_info["seed_topology_signatures"] = []
            return []
    
        seed_point = self._psc_seed_point_for_unit(unit_info, psc_model)
        if seed_point is None:
            unit_info["seed_points"] = []
            return []
        unit_info["seed_points"] = [seed_point]
        unit_info["seed_point"] = seed_point
        unit_info["seed_topology_signatures"] = [
            {
                "boundaries": list(unit_info.get("boundaries", []) or []),
                "signature": dict(unit_info.get("seed_topology_signature", {}) or {}),
            }
        ]
        return [seed_point]
    
    def _assign_psc_materials(
        self,
        psc_model: Dict[str, Any],
        psc_mapping: Dict[str, Any],
    ) -> Tuple[int, int]:
        """Replace formation materials with PSC-derived unit materials."""
        assigned_materials = []
        skipped_count = 0
        self._psc_side_context = self._psc_prepare_topology_side_context(
            psc_model,
            list(psc_mapping.get("units", [])),
        )
    
        mapped_units = list(psc_mapping.get("units", []))
        for unit_info in psc_mapping.get("units", []):
            if unit_info.get("seed_override") and unit_info.get("seed_point") is not None:
                seed_points = self._psc_seed_points_for_unit(
                    unit_info,
                    psc_model,
                    mapped_units,
                )
                seed_point = seed_points[0] if seed_points else None
            else:
                seed_points = self._psc_seed_points_for_unit(
                    unit_info,
                    psc_model,
                    mapped_units,
                )
                seed_point = seed_points[0] if seed_points else None
            unit_info["seed_points"] = seed_points
            unit_info["seed_point"] = seed_point
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
                    "feature": unit_info.get("feature", ""),
                    "unit_role": unit_info.get("unit_role", ""),
                    "boundaries": list(unit_info.get("boundaries", [])),
                    "matched_surface_indices": list(unit_info.get("matched_surface_indices", [])),
                    "missing_boundaries": list(unit_info.get("missing_boundaries", [])),
                    "seed_override": bool(unit_info.get("seed_override", False)),
                    "psc_seed_count": len(seed_points),
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
        dialog.resize(520, 190)
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
            use_selected=use_selected_check.isChecked(),
            tolerance=self._default_section_tolerance(section_uid),
            # tolerance=float(tolerance_spin.value()),
        )

    def build_section_areas(
        self,
        table_name: str,
        boundary_uid: str = FRAME_BOUNDARY_KEY,
        use_selected: bool = False,
        tolerance: float = 0.0,
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

        network_geometries = [boundary_polygon.boundary] + [
            entry["geometry"] for entry in line_entries
        ]
        noded_network = unary_union(network_geometries)
        polygons_geom, dangles_geom, cuts_geom, invalids_geom = polygonize_full(noded_network)

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
                area_tolerance = max(boundary_polygon.area * 1.0e-6, tolerance * tolerance)
                coverage_ok = (
                    boundary_polygon.difference(covered).area <= area_tolerance
                    and covered.difference(boundary_polygon).area <= area_tolerance
                )
            except Exception:
                coverage_ok = False

        if dangle_count or cut_count or invalid_count or not coverage_ok:
            self.print_terminal(
                "Section lines are not watertight "
                f"(dangles={dangle_count}, cuts={cut_count}, invalid rings={invalid_count}). "
                "Clean the section with Snap to intersection and retry."
            )
            return

        psc_model = self._build_psc_model_from_stm(table_name)
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

        for area_idx, polygon in enumerate(section_polygons, start=1):
            boundary_labels = self._polygon_boundary_labels(
                polygon=polygon,
                boundary_polygon=boundary_polygon,
                line_entries=line_entries,
                tolerance=tolerance,
            )
            area_infos.append(
                {
                    "area_idx": area_idx,
                    "polygon": polygon,
                    "boundary_labels": boundary_labels,
                    "candidates": self._section_unit_candidates_for_boundary_labels(
                        psc_model=psc_model,
                        labels=boundary_labels,
                    ),
                }
            )

        assignments = [None for _area_info in area_infos]
        for info_idx, area_info in enumerate(area_infos):
            exact_candidates = [
                candidate
                for candidate in area_info.get("candidates", [])
                if candidate.get("exact")
            ]
            if len(exact_candidates) != 1:
                continue
            candidate = exact_candidates[0]
            status = (
                "POSSIBLE_REPEAT"
                if assigned_counts.get(candidate["unit_key"], 0)
                else "CERTAIN"
            )
            assignments[info_idx] = self._section_assignment_payload(
                candidate=candidate,
                status=status,
                candidate_pool=exact_candidates,
                assigned_counts=assigned_counts,
            )
            assigned_counts[candidate["unit_key"]] = (
                assigned_counts.get(candidate["unit_key"], 0) + 1
            )

        for info_idx, area_info in enumerate(area_infos):
            if assignments[info_idx] is not None:
                continue
            assignment = self._section_best_area_assignment(
                area_info=area_info,
                assigned_counts=assigned_counts,
            )
            assignments[info_idx] = assignment
            unit_key = assignment.get("unit_key", "")
            if unit_key:
                assigned_counts[unit_key] = assigned_counts.get(unit_key, 0) + 1

        for area_info, assignment in zip(area_infos, assignments):
            polygon = area_info["polygon"]
            area_idx = int(area_info["area_idx"])
            boundary_labels = area_info.get("boundary_labels", [])
            assignment = assignment or {"status": "UNASSIGNED"}
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
                role = self._psc_text(unit_info.get("unit_role", "")) or "undef"
                feature = self._psc_text(unit_info.get("feature", "")) or "PSC_unit"
                unit_name = self._psc_text(unit_info.get("name", "")) or feature

            color = self._legend_color_for_feature(feature)
            seed_point = polygon.representative_point()
            seed_xyz = project.xsect_coll.plane2world(
                section_uid=section_uid,
                U=float(seed_point.x),
                V=float(seed_point.y),
                as_arr=True,
            )

            seed_uid = self._create_seed_vertex(
                name=f"PSC_seed_{unit_name}",
                role=role,
                feature=feature,
                xyz=np.asarray(seed_xyz, dtype=float).reshape(3),
                color=color,
            )
            if seed_uid:
                created_seed_count += 1

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

    def _default_section_tolerance(self, section_uid: str) -> float:
        project = self._pzero_project()
        try:
            length = float(project.xsect_coll.get_uid_length(section_uid))
            height = float(project.xsect_coll.get_uid_width(section_uid))
            diagonal = float(np.linalg.norm([length, height]))
        except Exception:
            diagonal = 1.0
        return max(diagonal * 1.0e-6, 0.001)

    def _available_boundary_options(self) -> List[Tuple[str, str]]:
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

    def _section_polyline_uids(self, use_selected: bool = False) -> List[str]:
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
        coords = np.asarray(coords, dtype=float)
        if coords.shape[0] <= 1:
            return coords
        keep = [coords[0]]
        for coord in coords[1:]:
            if np.linalg.norm(coord[:2] - keep[-1][:2]) > 1.0e-9:
                keep.append(coord)
        return np.asarray(keep, dtype=float)

    def _section_line_entries(self, line_uids, boundary_polygon, line_cls) -> List[Dict[str, Any]]:
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

    def _polygon_boundary_labels(
        self,
        polygon,
        boundary_polygon,
        line_entries: List[Dict[str, Any]],
        tolerance: float,
    ) -> List[str]:
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
    ) -> List[Dict[str, Any]]:
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
            if len(missing_keys) > self.MAX_RELAXED_MISSING_BOUNDARIES:
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
    ) -> Dict[str, Any]:
        candidates = list(area_info.get("candidates", []) or [])
        if not candidates:
            return {"status": "UNASSIGNED"}

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
        status = str(assignment.get("status", "UNASSIGNED"))
        details = [f"boundaries={self._format_section_labels(boundary_labels)}"]
        missing_labels = assignment.get("missing_labels", []) or []
        if missing_labels:
            details.append(f"missing={self._format_section_labels(missing_labels)}")
        candidate_names = assignment.get("candidate_names", []) or []
        if len(candidate_names) > 1:
            details.append(f"candidates={', '.join(candidate_names)}")
        assigned_before = int(assignment.get("assigned_before", 0) or 0)
        if assigned_before:
            details.append(f"already assigned={assigned_before}")

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

    def _legend_color_for_feature(self, feature: str) -> Optional[List[float]]:
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
    ) -> Optional[str]:
        from pzero.entities_factory import XsVertexSet

        project = self._pzero_project()
        section_uid = getattr(self.host, "this_x_section_uid", "")
        seed_dict = deepcopy(project.geol_coll.entity_dict)
        seed_dict["name"] = name
        seed_dict["parent_uid"] = section_uid
        seed_dict["topology"] = "XsVertexSet"
        seed_dict["role"] = role
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
        project = self._pzero_project()
        section_uid = getattr(self.host, "this_x_section_uid", "")
        area_dict = deepcopy(project.geol_coll.entity_dict)
        area_dict["name"] = name
        area_dict["parent_uid"] = section_uid
        area_dict["topology"] = "TriSurf"
        area_dict["role"] = role
        area_dict["feature"] = feature
        area_dict["vtk_obj"] = vtk_obj
        area_dict["properties_names"] = list(getattr(vtk_obj, "point_data_keys", []) or [])
        area_dict["properties_components"] = [
            vtk_obj.get_point_data_shape(key)[1] for key in area_dict["properties_names"]
        ]
        return project.geol_coll.add_entity_from_dict(entity_dict=area_dict, color=color)

    def _triangulated_polygon_surface(self, polygon, triangulate_func):
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
        min_length = max(float(tolerance or 0.0), 1.0e-9)
        return sum(
            1
            for line in self._iter_line_geometries(geometry)
            if getattr(line, "length", 0.0) > min_length
        )

    def _iter_geometries(self, geometry) -> List[Any]:
        if geometry is None or getattr(geometry, "is_empty", True):
            return []
        if hasattr(geometry, "geoms"):
            out = []
            for child in geometry.geoms:
                out.extend(self._iter_geometries(child))
            return out
        return [geometry]

    def _iter_line_geometries(self, geometry) -> List[Any]:
        return [
            geom
            for geom in self._iter_geometries(geometry)
            if geom.geom_type in {"LineString", "LinearRing"}
        ]

    def _geometry_length(self, geometry) -> float:
        if geometry is None or getattr(geometry, "is_empty", True):
            return 0.0
        try:
            return float(geometry.length)
        except Exception:
            return sum(float(getattr(geom, "length", 0.0)) for geom in self._iter_geometries(geometry))

    def _unique_polygons(self, polygons: List[Any]) -> List[Any]:
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
