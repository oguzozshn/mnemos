"""Ingest adapters: each turns one platform's export into `Message` objects."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

from mnemos.ingest import claude
from mnemos.models import Message

ADAPTERS: dict[str, Callable[[Path], Iterator[Message]]] = {
    "claude": claude.load,
    # "chatgpt": chatgpt.load,  # phase 1, next
    # "gemini": gemini.load,    # phase 1, after ChatGPT
}


def load(path: Path, source: str) -> Iterator[Message]:
    try:
        adapter = ADAPTERS[source]
    except KeyError:
        supported = ", ".join(sorted(ADAPTERS))
        raise ValueError(f"Unsupported source '{source}'. Supported: {supported}") from None
    return adapter(path)
