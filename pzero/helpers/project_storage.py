"""Checked VTK snapshots and atomic publication of completed project revisions."""
import os
from pathlib import Path
from uuid import uuid4

from vtk import vtkXMLStructuredGridWriter


def write_checked(writer):
    """VTK can report an error event even when Write returns success."""
    errors = []
    observer = writer.AddObserver("ErrorEvent", lambda *_: errors.append(True))
    try:
        success = writer.Write()
        if not success or errors or writer.GetErrorCode():
            raise OSError(f"Could not save VTK object: {writer.GetFileName()}")
    finally:
        writer.RemoveObserver(observer)


def write_seismic_snapshot(grid, destination, progress=None):
    """Lossless, self-contained VTS using fast LZ4 and raw appended arrays.

    UInt64 headers support coordinate arrays larger than 4 GiB. No source-file
    reconstruction or coordinate rounding is used, including for edited grids.
    """
    destination = Path(destination)
    temporary = destination.with_name(destination.name + f".{uuid4().hex}.tmp")
    writer = vtkXMLStructuredGridWriter()
    writer.SetFileName(str(temporary))
    writer.SetInputData(grid)
    writer.SetDataModeToAppended()
    writer.EncodeAppendedDataOff()
    writer.SetCompressorTypeToLZ4()
    writer.SetHeaderTypeToUInt64()
    writer.SetBlockSize(1024 * 1024)
    if progress is not None:
        writer.AddObserver("ProgressEvent", lambda obj, _: progress(obj.GetProgress()))
    try:
        write_checked(writer)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def publish_project_revision(project_file, revision, crs="test_epsg"):
    """Replace the project pointer only after every revision payload is saved."""
    destination = Path(project_file)
    temporary = destination.with_name(destination.name + f".{uuid4().hex}.tmp")
    text = ("PZero project file saved in folder with the same name, including VTK files and CSV tables.\n"
            f"Last saved revision:\n{revision}\nCRS EPSG:\n{crs}\n")
    try:
        with temporary.open("w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
