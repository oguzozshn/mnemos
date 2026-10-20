"""Locate and load a JSON file from a ZIP export, an extracted folder, or a direct path."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any


class ExportNotFound(FileNotFoundError):
    pass


def load_json(path: Path, member: str) -> Any:
    """Load `member` (e.g. `conversations.json`) from `path`.

    `path` may be the JSON file itself, a directory containing it (searched recursively),
    or a ZIP archive containing it (at any depth).
    """
    path = Path(path)
    if not path.exists():
        raise ExportNotFound(f"No such file or directory: {path}")

    if path.is_file() and path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as zf:
            candidates = [n for n in zf.namelist() if Path(n).name == member]
            if not candidates:
                raise ExportNotFound(f"{member} not found inside {path.name}")
            with zf.open(sorted(candidates, key=len)[0]) as fh:
                return json.load(fh)

    if path.is_dir():
        candidates = sorted(path.rglob(member), key=lambda p: len(p.parts))
        if not candidates:
            raise ExportNotFound(f"{member} not found under {path}")
        path = candidates[0]

    with path.open(encoding="utf-8") as fh:
        return json.load(fh)
