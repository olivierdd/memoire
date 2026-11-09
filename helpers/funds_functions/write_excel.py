"""Write an Excel file, then move it into the destination folder."""

from __future__ import annotations

import errno
import os
import shutil
import tempfile
from pathlib import Path

import pandas as pd


def write_excel(frame: pd.DataFrame, path: Path, *, header: bool = True) -> Path:
    """Write ``frame`` to ``path`` and return that path.

    xlsxwriter seeks inside the workbook while the file is still open. On the
    iCloud copy of Documents that seek raises ``TimeoutError`` (Errno 60). The
    workbook is built in the local temp directory and moved into place after
    it has been closed.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_dir = tempfile.mkdtemp()
    temporary = Path(temporary_dir) / path.name
    try:
        frame.to_excel(temporary, index=False, header=header)
        _move_into_place(temporary, path)
    finally:
        shutil.rmtree(temporary_dir, ignore_errors=True)
    return path


def _move_into_place(source: Path, destination: Path) -> None:
    try:
        os.replace(source, destination)
    except OSError as error:
        if error.errno != errno.EXDEV:
            raise
        shutil.copy2(source, destination)
