"""Adapter for Claude data exports (`conversations.json`).

Expected shape (fields not listed are ignored):

    [
      {
        "uuid": str, "name": str, "created_at": iso,
        "chat_messages": [
          {
            "uuid": str, "sender": "human" | "assistant", "created_at": iso,
            "text": str,                                   # may be empty in newer exports
            "content": [{"type": "text", "text": str}, ...] # preferred when present
          }
        ]
      }
    ]

The adapter is deliberately tolerant: unknown content block types (tool use, thinking,
attachments) are skipped, and messages with no text are dropped.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from mnemos.ingest._io import load_json
from mnemos.ingest._time import to_utc_iso
from mnemos.models import Message

SOURCE = "claude"
MEMBER = "conversations.json"
_ROLES = {"human": "user", "user": "user", "assistant": "assistant"}


def _message_text(msg: dict[str, Any]) -> str:
    blocks = msg.get("content")
    if isinstance(blocks, list):
        parts = [
            b.get("text", "")
            for b in blocks
            if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str)
        ]
        joined = "\n\n".join(p for p in parts if p.strip())
        if joined.strip():
            return joined.strip()
    text = msg.get("text")
    return text.strip() if isinstance(text, str) else ""


def _fallback_id(conv_id: str, position: int, created_at: str | None) -> str:
    raw = f"{conv_id}|{position}|{created_at}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def parse(data: Any) -> Iterator[Message]:
    if not isinstance(data, list):
        raise ValueError("Claude conversations.json must be a JSON array of conversations")

    for conv in data:
        if not isinstance(conv, dict):
            continue
        conv_id = conv.get("uuid")
        if not conv_id:
            continue
        title = conv.get("name") or None
        conv_created = to_utc_iso(conv.get("created_at"))

        for position, msg in enumerate(conv.get("chat_messages") or []):
            if not isinstance(msg, dict):
                continue
            role = _ROLES.get(str(msg.get("sender", "")).lower())
            if role is None:
                continue
            text = _message_text(msg)
            if not text:
                continue
            created = to_utc_iso(msg.get("created_at")) or conv_created
            if created is None:
                continue
            msg_id = msg.get("uuid") or _fallback_id(conv_id, position, created)
            yield Message(
                id=f"{SOURCE}:{msg_id}",
                source=SOURCE,
                conversation_id=f"{SOURCE}:{conv_id}",
                conversation_title=title,
                role=role,
                text=text,
                created_at=created,
                position=position,
            )


def load(path: Path) -> Iterator[Message]:
    return parse(load_json(path, MEMBER))
