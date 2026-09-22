"""SEG-Y import entry point and isolated compatibility reader for old projects."""

from os import path as os_path
from copy import deepcopy
from uuid import uuid4
from numpy import array as np_array, where as np_where, linspace as np_linspace
from numpy import repeat as np_repeat, empty as np_empty, flip as np_flip
from pyvista import StructuredGrid as pv_StructuredGrid
from segyio import open as segyio_open, BinField as segyio_BinField, TraceField as segyio_TraceField
from PySide6.QtWidgets import QDialog, QMessageBox

from pzero.entities_factory import Seismics
from pzero.imports.segy_reader import read_grid, set_seismic_metadata


def segy2vtk(self, in_file_name):
    """Review input settings before importing a volume into the image collection."""
    from pzero.helpers.segy_import_dialog import SegyImportDialog

    dialog = SegyImportDialog(in_file_name, parent=self)
    if dialog.exec() != QDialog.Accepted:
        dialog.survey = None
        dialog.deleteLater()
        return None
    self.disable_actions()
    try:
        grid = read_segy_file(in_file_name, dialog.import_options, survey=dialog.survey)
        entity = deepcopy(self.image_coll.entity_dict)
        entity["uid"] = str(uuid4())
        entity["name"] = dialog.import_options.name
        entity["topology"] = "Seismics"
        entity["vtk_obj"] = Seismics()
        entity["vtk_obj"].ShallowCopy(grid)
        entity["properties_names"] = entity["vtk_obj"].point_data_keys
        entity["properties_components"] = entity["vtk_obj"].point_data_components
        entity["properties_types"] = entity["vtk_obj"].point_data_types
        entity["seismic_source_file"] = os_path.abspath(in_file_name)
        self.image_coll.add_entity_from_dict(entity_dict=entity)
        self.print_terminal(f"Imported {entity['name']} with validated coordinates and {dialog.import_options.domain} sampling.")
        return entity["uid"]
    except Exception as error:
        self.print_terminal(f"SEG-Y import failed: {error}")
        QMessageBox.warning(self, "SEG-Y import failed", str(error))
        return None
    finally:
        dialog.survey = None
        dialog.deleteLater()
        self.enable_actions()


def read_segy_file(in_file_name=None, options=None, survey=None):
    """Automatically standardize recoverable layouts after the import review."""
    from dataclasses import replace
    from pathlib import Path
    from tempfile import TemporaryDirectory
    from pzero.imports.segy_reader import (
        DEFAULT_HEADERS, SegyImportOptions, inspect_segy, prepare_geometry, get_seismic_metadata,
    )
    from pzero.processing.segy_standardizer import standardize_segy_for_pzero

    if isinstance(options, dict):
        options = SegyImportOptions(**options)
    if not isinstance(options, SegyImportOptions):
        raise ValueError("SEG-Y import options are required; review the input data first.")
    survey = survey or inspect_segy(in_file_name, options.endian, options.headers, options.header_widths)
    if ((options.headers is not None and options.headers != survey["headers"])
            or (options.header_widths is not None and options.header_widths != survey["header_widths"])
            or options.endian not in ("auto", survey["endian"])):
        raise ValueError("Header settings changed after inspection. Preview the survey again.")
    # Fail before conversion for invalid domains, mappings or prestack geometry.
    prepare_geometry(survey, options)
    if not survey["requires_standardization"]:
        return read_grid(in_file_name, options, survey=survey)
    with TemporaryDirectory(prefix="pzero-segy-") as folder:
        normalized = Path(folder) / "standardized.sgy"
        standardize_segy_for_pzero(in_file_name, normalized, print_fn=lambda _: None, survey=survey)
        canonical = replace(options, headers=DEFAULT_HEADERS.copy(), header_widths=dict.fromkeys(DEFAULT_HEADERS, 4))
        grid = read_grid(normalized, canonical)
    metadata = get_seismic_metadata(grid)
    metadata.update(source_file=survey["path"], source_identity=survey["identity"],
                    import_options=options.to_dict(), standardized=True,
                    detected_headers=survey["headers"], header_widths=survey["header_widths"],
                    detection_evidence=survey["detection_evidence"], repairs=survey["repairs"])
    set_seismic_metadata(grid, metadata)
    return grid


def read_legacy_segy_file(in_file_name=None):
    """Reproduce pre-domain-metadata project geometry ONLY when reopening old projects.

    Never use this reader for a new import: legacy coordinates are intentionally
    retained here so saved interpretations do not move during a software update.
    """
    with segyio_open(in_file_name, "r", strict=False) as segyfile:
        inlines = segyfile.ilines
        crosslines = segyfile.xlines
        times = segyfile.samples
        num_samples = len(times)
        sample_interval = segyfile.bin[segyio_BinField.Interval]

        # Read all trace attributes once and cache them
        xcoords = np_array(segyfile.attributes(segyio_TraceField.CDP_X)[:], dtype=float)
        ycoords = np_array(segyfile.attributes(segyio_TraceField.CDP_Y)[:], dtype=float)
        inlines_index = np_array(segyfile.attributes(segyio_TraceField.INLINE_3D)[:])
        crosslines_index = np_array(segyfile.attributes(segyio_TraceField.CROSSLINE_3D)[:])

        try:
            inline_index_list = np_where(inlines_index == inlines[0])[0]
        except TypeError:
            raise Exception("The SEGYFILE is non-standard, PZero closing.")
        
        inline_dim = len(inline_index_list)
        crossline_index_list = np_where(crosslines_index == crosslines[0])[0]
        crossline_dim = len(crossline_index_list)

        # Compute depth range
        depth = num_samples * sample_interval
        slices = np_linspace(-depth, 0, num_samples) / 8.0  # Pre-divide by 8
        
        # Vectorized point construction - build all z-layers at once
        num_traces = len(xcoords)
        # Create z-coordinates for each sample level (num_samples x num_traces)
        z_all = np_repeat(slices[:, None], num_traces, axis=1)  # shape: (num_samples, num_traces)
        
        # Build volume_points using broadcasting
        volume_points = np_empty((num_samples, num_traces, 3), dtype=float)
        volume_points[:, :, 0] = xcoords  # broadcast xcoords to all z-levels
        volume_points[:, :, 1] = ycoords  # broadcast ycoords to all z-levels
        volume_points[:, :, 2] = z_all
        volume_points = volume_points.reshape(-1, 3)

        # Read seismic data efficiently using segyio's trace array
        # segyfile.trace gives direct numpy array access per trace
        num_crosslines = len(crosslines)
        num_inlines = len(inlines)
        data = np_empty((num_crosslines, num_inlines, num_samples), dtype=float)
        
        # Use segyio's xline iterator which is optimized for crossline access
        for i, xline_data in enumerate(segyfile.xline[:]):
            data[i, :, :] = xline_data

        flip_data = np_flip(data, axis=2)

        pv_seismic_grid = pv_StructuredGrid()
        pv_seismic_grid.points = volume_points
        pv_seismic_grid.dimensions = (inline_dim, crossline_dim, num_samples)
        pv_seismic_grid["intensity"] = flip_data.ravel(order="F")

        set_seismic_metadata(pv_seismic_grid, {
            "schema_version": 0, "vertical_domain": "legacy_unknown",
            "vertical_units": "unknown", "xy_units": "unknown",
            "source_file": os_path.abspath(in_file_name),
            "geometry_status": "Legacy project coordinates preserved; reimport for physical units.",
        })
        return pv_seismic_grid
