"""One declared horizontal CRS per project, shared by storage and file imports."""

from dataclasses import dataclass
import json
from pathlib import Path

from pyproj import CRS
from pyproj.exceptions import CRSError
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)


UNSPECIFIED = {"", "none", "unspecified", "no_epsg", "test_epsg"}
METADATA_NAME = "pzero_crs.json"


def project_crs_code(value):
    """Accept projected EPSG systems in metres, matching PZero's depth geometry."""
    if value is None or str(value).strip().lower() in UNSPECIFIED:
        return None
    try:
        crs = CRS.from_user_input(value)
    except CRSError as error:
        raise ValueError("Enter a valid EPSG code, for example EPSG:32632.") from error
    if not crs.is_projected:
        raise ValueError(
            "The project CRS must be projected; longitude/latitude in degrees is not supported."
        )
    if len(crs.axis_info) < 2 or any(
        abs(axis.unit_conversion_factor - 1.0) > 1e-12 for axis in crs.axis_info[:2]
    ):
        raise ValueError(
            "The project CRS must use metres. Reproject feet-based data to a metre-based CRS."
        )
    epsg = crs.to_epsg()
    if epsg is None:
        raise ValueError("Choose a projected CRS with an EPSG code.")
    return f"EPSG:{epsg}"


@dataclass(frozen=True)
class ImportCRS:
    source: CRS | None = None
    target: CRS | None = None

    @property
    def needs_reprojection(self):
        return self.source is not None and not self.source.equals(
            self.target, ignore_axis_order=True
        )


def import_crs_plan(source, target, allow_reprojection=False):
    """Validate before any objects enter a collection; assigning never moves data."""
    target_code = project_crs_code(target)
    if target_code is None:
        if source:
            raise ValueError(
                "Choose the project's projected CRS before importing georeferenced data."
            )
        return ImportCRS()
    if not source:
        raise ValueError(
            "Declare the file CRS or confirm that it matches the project CRS."
        )
    source = CRS.from_user_input(source)
    if not (source.is_projected or source.is_geographic):
        raise ValueError("The file must have a projected or geographic horizontal CRS.")
    plan = ImportCRS(source, CRS.from_user_input(target_code))
    if plan.needs_reprojection and not allow_reprojection:
        raise ValueError(
            "The file CRS differs from the project CRS. This import does not yet support "
            "reprojection; convert the file to the project CRS before importing."
        )
    return plan


def read_import_crs(path):
    """Recognize CRS sidecars from exports and conventional .prj files."""
    path = Path(path)
    metadata = Path(str(path) + ".crs.json")
    if metadata.is_file():
        return _read_crs_metadata(metadata)
    projection = path.with_suffix(".prj")
    if projection.is_file():
        return projection.read_text(encoding="utf-8")
    metadata = path.parent / METADATA_NAME
    if metadata.is_file():
        return _read_crs_metadata(metadata)
    return None


def _read_crs_metadata(path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or "crs" not in payload:
        raise ValueError(f"Invalid CRS metadata: {path.name}")
    value = payload["crs"]
    if value is not None and not isinstance(value, (str, int)):
        raise ValueError(f"Invalid CRS declaration: {path.name}")
    return value


class ImportCRSDialog(QDialog):
    def __init__(self, parent, path, source, target, allow_reprojection):
        super().__init__(parent)
        self.setWindowTitle("Import coordinate system")
        self.plan = None
        self.allow_reprojection = allow_reprojection
        layout = QVBoxLayout(self)
        note = QLabel(
            f"File: {Path(path).name}\n"
            "Confirm the coordinate system before importing. Assigning a CRS describes "
            "existing coordinates; it does not move them.\n"
            "Elevation/depth coordinates must already be in metres. Seismic time keeps its own units."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        self.source_edit = QLineEdit(str(source or target or ""))
        self.source_edit.setReadOnly(source is not None)
        self.source_edit.setPlaceholderText("EPSG:32632")
        self.target_edit = QLineEdit(str(target or ""))
        self.target_edit.setReadOnly(target is not None)
        self.target_edit.setPlaceholderText("Projected EPSG code in metres")
        if not target and source:
            try:
                self.target_edit.setText(project_crs_code(source) or "")
            except ValueError:
                pass
        form.addRow("File CRS", self.source_edit)
        form.addRow("Project CRS", self.target_edit)
        layout.addLayout(form)
        self.local = QCheckBox("Keep unspecified local coordinates (no EPSG)")
        self.local.setVisible(source is None and target is None)
        self.local.toggled.connect(
            lambda checked: self.source_edit.setDisabled(checked)
        )
        self.local.toggled.connect(
            lambda checked: self.target_edit.setDisabled(checked)
        )
        layout.addWidget(self.local)
        explanation = QLabel(
            "Different systems will be reprojected on import; Z values are preserved."
            if allow_reprojection
            else "The file CRS must match the project. Reproject other files before importing."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Continue")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self):
        try:
            if not self.local.isHidden() and self.local.isChecked():
                self.plan = ImportCRS()
            else:
                if not self.target_edit.text().strip():
                    raise ValueError(
                        "Choose a project EPSG code or explicitly keep local coordinates."
                    )
                self.plan = import_crs_plan(
                    self.source_edit.text().strip(),
                    self.target_edit.text().strip(),
                    self.allow_reprojection,
                )
        except (ValueError, CRSError) as error:
            QMessageBox.warning(self, "Coordinate system", str(error))
            return
        super().accept()


def check_import_crs(parent, path, source_crs=None, allow_reprojection=False):
    """Return a checked plan, or None on cancellation; never guess an EPSG."""
    try:
        source = source_crs if source_crs is not None else read_import_crs(path)
        if source is not None and str(source).strip().lower() in UNSPECIFIED:
            source = None
        target = getattr(parent, "project_crs", None)
        if source is not None and target is not None:
            plan = import_crs_plan(source, target, allow_reprojection)
            if not plan.needs_reprojection:
                return plan
        dialog = ImportCRSDialog(parent, path, source, target, allow_reprojection)
        if dialog.exec() != QDialog.Accepted:
            return None
        plan = dialog.plan
        if target is None and plan.target is not None:
            answer = QMessageBox.question(
                parent,
                "Assign project CRS",
                f"Assign {plan.target.to_string()} to this project?\n"
                "Existing coordinates will stay unchanged. Confirm that existing data uses this CRS.",
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if answer != QMessageBox.Yes:
                return None
            parent.set_project_crs(plan.target)
        return plan
    except (ValueError, CRSError, OSError, KeyError) as error:
        QMessageBox.warning(parent, "Import coordinate system", str(error))
        return None


def write_crs_metadata(directory, crs, check_existing=False):
    """Write portable metadata for formats without a native CRS field."""
    code = project_crs_code(crs)
    directory = Path(directory)
    metadata = directory / METADATA_NAME
    if check_existing and metadata.is_file():
        previous = project_crs_code(_read_crs_metadata(metadata))
        if previous != code:
            raise ValueError(
                "This folder contains exports in another CRS. Choose a different folder."
            )
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "crs": code,
        "xy_units": "m" if code else None,
        "vertical_note": "Horizontal CRS only. Vertical domain, units and datum are entity-specific.",
    }
    metadata.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    label = code.replace(":", "_") if code else "unspecified"
    (directory / f"CRS_{label}.txt").write_text(
        f"Horizontal CRS: {code or 'unspecified'}\n" f"{payload['vertical_note']}\n",
        encoding="utf-8",
    )


def read_project_crs(lines, revision_directory):
    """Revision metadata keeps older snapshots independent of the project pointer."""
    metadata = Path(revision_directory) / METADATA_NAME
    if metadata.is_file():
        return project_crs_code(_read_crs_metadata(metadata))
    return project_crs_code(lines[4].strip() if len(lines) > 4 else None)
