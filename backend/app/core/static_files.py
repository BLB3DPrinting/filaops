"""StaticFiles that serves one URL prefix from several directories."""
from __future__ import annotations

from pathlib import Path

from starlette.staticfiles import StaticFiles


class MultiDirStaticFiles(StaticFiles):
    """Serve files from the first of ``directories`` that has them.

    ``StaticFiles.lookup_path`` already walks ``all_directories`` in order
    (the same mechanism it uses for ``packages=``); this only supplies the
    list. The first directory must exist; later ones may be missing.
    """

    def __init__(self, *, directories: list[Path], **kwargs) -> None:
        unique: list[str] = []
        for directory in directories:
            path = str(directory)
            if path not in unique:
                unique.append(path)
        if not unique:
            raise ValueError("MultiDirStaticFiles needs at least one directory")
        self._directories = unique
        super().__init__(directory=unique[0], **kwargs)

    def get_directories(self, directory=None, packages=None):
        return list(self._directories)
