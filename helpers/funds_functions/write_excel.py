"""Write an Excel file, then move it into the destination folder."""

from __future__ import annotations

import errno
import os
import shutil
import tempfile
from pathlib import Path

import pandas as pd


def write_excel(
    frame: pd.DataFrame,
    path: Path,
    *,
    header: bool = True,
    sheet_name: str = "Sheet1",
) -> Path:
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
        frame.to_excel(
            temporary, index=False, header=header, sheet_name=sheet_name
        )
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


def write_excel_sheets(
    sheets: dict[str, pd.DataFrame],
    path: Path,
    *,
    no_header: tuple[str, ...] = (),
) -> Path:
    """Write several sheets to one workbook, replacing the file at ``path``.

    Sheets are written in dict order. Sheets named in ``no_header`` are written
    without a header row. Same temp-directory move as ``write_excel``.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_dir = tempfile.mkdtemp()
    temporary = Path(temporary_dir) / path.name
    try:
        with pd.ExcelWriter(temporary) as writer:
            for name, frame in sheets.items():
                frame.to_excel(
                    writer,
                    index=False,
                    header=name not in no_header,
                    sheet_name=name,
                )
        _move_into_place(temporary, path)
    finally:
        shutil.rmtree(temporary_dir, ignore_errors=True)
    return path
