"""Print the structure of a JSON export without printing any of its content.

Output lists every key path with the value types seen there, how often the path occurs,
list length ranges and string length ranges. No string, number or key *value* that could
carry personal content is printed: dictionaries with many keys or id-like keys (e.g. the
ChatGPT `mapping` object keyed by message UUIDs) are collapsed to `<*>`.

Usage:
    python scripts/dump_schema.py path/to/export.json
    python scripts/dump_schema.py path/to/export.zip --member conversations.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Keys that look like ids/dates/hashes are collapsed so no data leaks through key names.
_ID_LIKE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"  # UUID
    r"|^[0-9a-f]{16,}$"  # hex hash
    r"|^\d+$"  # numeric
    r"|^\d{4}-\d{2}-\d{2}",  # date
    re.IGNORECASE,
)
_SAFE_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_\-]{0,40}$")
MAX_NAMED_KEYS = 50


@dataclass
class PathStats:
    count: int = 0
    types: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    list_len: list[int] = field(default_factory=list)  # [min, max]
    str_len: list[int] = field(default_factory=list)  # [min, max]
    enum_values: set[str] | None = field(default_factory=set)  # short, low-cardinality strings

    def track_range(self, bucket: list[int], value: int) -> None:
        if not bucket:
            bucket.extend([value, value])
        else:
            bucket[0] = min(bucket[0], value)
            bucket[1] = max(bucket[1], value)


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _should_collapse(obj: dict) -> bool:
    if len(obj) > MAX_NAMED_KEYS:
        return True
    return any(_ID_LIKE.match(k) or not _SAFE_KEY.match(k) for k in obj)


# Only these well-known schema fields may show their (enum-like) values, e.g. sender roles.
ENUM_KEYS = {"sender", "role", "type", "author_role", "content_type", "status", "header"}
MAX_ENUM = 12


def walk(value: Any, path: str, stats: dict[str, PathStats], key: str | None = None) -> None:
    s = stats[path]
    s.count += 1
    t = _type_name(value)
    s.types[t] += 1

    if t == "str":
        s.track_range(s.str_len, len(value))
        if key in ENUM_KEYS and s.enum_values is not None and len(value) <= 40:
            s.enum_values.add(value)
            if len(s.enum_values) > MAX_ENUM:
                s.enum_values = None  # too many distinct values: not an enum, hide all
    elif t == "list":
        s.track_range(s.list_len, len(value))
        for item in value:
            walk(item, f"{path}[]", stats, key)
    elif t == "object":
        if _should_collapse(value):
            for v in value.values():
                walk(v, f"{path}.<*>", stats, None)
        else:
            for k, v in value.items():
                walk(v, f"{path}.{k}", stats, k)


def load(path: Path, member: str | None) -> Any:
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as zf:
            names = [n for n in zf.namelist() if n.endswith(".json")]
            if member is None:
                print("JSON files in archive:", file=sys.stderr)
                for n in names:
                    print(f"  {n}  ({zf.getinfo(n).file_size:,} bytes)", file=sys.stderr)
                raise SystemExit("Pass --member <name> to choose one.")
            with zf.open(member) as fh:
                return json.load(fh)
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def render(stats: dict[str, PathStats]) -> str:
    lines = []
    for path in sorted(stats, key=lambda p: (p.count("."), p)):
        s = stats[path]
        types = ", ".join(f"{t}×{n}" for t, n in sorted(s.types.items()))
        extra = []
        if s.list_len:
            extra.append(f"len {s.list_len[0]}..{s.list_len[1]}")
        if s.str_len:
            extra.append(f"strlen {s.str_len[0]}..{s.str_len[1]}")
        if s.enum_values:
            extra.append("values {" + ", ".join(sorted(s.enum_values)) + "}")
        suffix = f"  [{'; '.join(extra)}]" if extra else ""
        lines.append(f"{path or '$'}  ({s.count}×)  {types}{suffix}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("path", type=Path)
    parser.add_argument("--member", help="JSON file inside a ZIP archive")
    args = parser.parse_args(argv)

    data = load(args.path, args.member)
    stats: dict[str, PathStats] = defaultdict(PathStats)
    walk(data, "$", stats)
    print(render(stats))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
