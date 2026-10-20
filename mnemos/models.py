"""Common data model shared by all ingest adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Role = Literal["user", "assistant"]
Source = Literal["claude", "chatgpt", "gemini"]


@dataclass(frozen=True, slots=True)
class Message:
    """One chat message, normalized across platforms.

    `id` is globally unique and stable across re-imports: `<source>:<platform message id>`.
    `created_at` is an ISO-8601 UTC timestamp string (e.g. `2026-10-20T16:31:00Z`).
    """

    id: str
    source: Source
    conversation_id: str
    conversation_title: str | None
    role: Role
    text: str
    created_at: str
    position: int  # order of the message inside its conversation
