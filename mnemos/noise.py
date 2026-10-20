"""Phase 2: separate what I actually wrote from what I pasted.

Each message gets:
- `clean_text`: the message with pasted blocks (code, logs, stack traces, markup, terminal
  output) removed. "What does this error mean?" + 40 lines of stack trace becomes just the
  question, which is what fact extraction and topic modeling should see.
- `pasted_chars`: how many characters were removed.
- `noise_reason`: dominant kind of pasted content, or `long_paste` / `empty`.
- `is_noise`: 1 when nothing of mine is left, or the message is a very long paste.

Pure heuristics, no model. Bump `CLEAN_VERSION` whenever the rules change so `mnemos clean`
re-processes earlier results.
"""

from __future__ import annotations

import re
import sqlite3
from collections import Counter
from dataclasses import dataclass

from mnemos.lang import detect_lang

CLEAN_VERSION = 4

MIN_BLOCK_LINES = 3  # consecutive non-prose lines needed to count as a pasted block
LONG_PASTE_CHARS = 4000  # leftover prose longer than this is almost always a pasted document

_FENCE = re.compile(r"```.*?(?:```|\Z)", re.S)

_STACK = re.compile(
    r"^\s*at [\w$.<>/]+\(.*\)\s*$"
    r"|^\s*File \".+\", line \d+"
    r"|^\s*Traceback \(most recent call last\)"
    r"|^\s*(Caused by|Exception in thread)\b"
    r"|^\s*[\w.$]+(Exception|Error)(:|\s*$)"
    r"|^\s*\.\.\. \d+ more"
)
_LOG = re.compile(
    r"^\s*\[?\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}"
    r"|^\s*\[?\d{2}:\d{2}:\d{2}"
    r"|^\s*\[?(INFO|WARN|WARNING|ERROR|DEBUG|TRACE|FATAL|SEVERE)\b"
)
_TERMINAL = re.compile(
    r"^\s*(\$ |# |>>> |PS [A-Za-z]:\\|[A-Za-z]:\\[^>\n]*>)"
    r"|^\s*(\+|-) [\w.-]+==[\w.]+\s*$"  # pip/uv install lines
    r"|^\s*(Windows PowerShell|Microsoft Windows \[|\(c\) Microsoft|Copyright \(C\) Microsoft"
    r"|Telif Hakkı \(C\) Microsoft|Tüm hakları saklıdır|Install the latest PowerShell)"
)
_TABLE = re.compile(r"\t.*\t|^\s*\|.*\|\s*$")  # tab-separated or markdown table rows
# Lines that start or end a pasted terminal/run session. Everything between two of them is
# program output. Includes IntelliJ run output ("...\bin\java.exe ..." ... "Process finished").
_PROMPT = re.compile(
    r"^\s*(\$ |PS [A-Za-z]:\\|[A-Za-z]:\\[^>\n]*>)"
    r"|\\bin\\javaw?\.exe\b"
    r"|^\s*Process finished with exit code"
)
_MARKUP = re.compile(r"^\s*</?[A-Za-z][\w:.-]*(\s[^<>]*)?/?>")
_CODE_START = re.compile(
    r"^\s*(import |from \S+ import |def |class |public |private |protected |static |"
    r"return\b|const |let |var |function\b|#include|package |@\w+|if \(|for \(|while \(|"
    r"elif |else:|try:|except\b|catch \(|SELECT |INSERT |UPDATE |CREATE TABLE|<\?xml|"
    r"\}|\]|\)|//|/\*|\*/)"
)
_CODE_SIGNAL = re.compile(r"[;{}()=<>\[\]]|:\s*$|^[})\]]")
_JSON_LINE = re.compile(r"^\s*\"[^\"]+\"\s*:")
_CODE_END = re.compile(r"[;{}]\s*$|\)\s*\{?\s*$|,\s*$")
_SYMBOLS = set("{}[]();=<>|&$\\")


@dataclass(frozen=True, slots=True)
class CleanResult:
    clean_text: str
    pasted_chars: int
    noise_reason: str | None
    is_noise: bool
    lang: str | None


def _line_kind(line: str) -> str:
    stripped = line.strip()
    if not stripped:
        return "blank"
    if _STACK.search(line):
        return "stacktrace"
    if _LOG.search(line):
        return "log"
    if _TERMINAL.search(line):
        return "terminal"
    if _MARKUP.search(line):
        return "markup"
    if _TABLE.search(line):
        return "table"
    if stripped.endswith("?"):
        return "prose"  # code almost never ends with a question mark; my questions do
    if _JSON_LINE.search(line) or (_CODE_START.search(line) and _CODE_SIGNAL.search(stripped)):
        return "code"  # keyword alone is not enough: "var", "public", "package" are Turkish too
    symbol_ratio = sum(c in _SYMBOLS for c in stripped) / len(stripped)
    if symbol_ratio >= 0.08 and len(stripped) >= 4:
        return "code"
    if _CODE_END.search(stripped) and (line[:1] in " \t" or symbol_ratio >= 0.04):
        return "code"
    if len(stripped) > 300 and " " not in stripped[:200]:
        return "code"  # minified JSON, base64, long URLs
    return "prose"


def clean(text: str) -> CleanResult:
    removed: Counter[str] = Counter()

    def _drop_fence(m: re.Match[str]) -> str:
        block = m.group(0)
        inner = re.sub(r"^```[^\n]*\n?|```$", "", block).strip("\n")
        if re.match(r"```[ \t]*[\w+#.-]+[ \t]*\n", block):  # ```python etc.: surely code
            removed["code"] += len(block)
            return "\n"
        # Untagged fence: I sometimes put my own question in it together with the code,
        # so unwrap it and let the line rules below decide line by line.
        return "\n" + inner + "\n"

    text_wo_fences = _FENCE.sub(_drop_fence, text)
    lines = text_wo_fences.splitlines()
    kinds = [_line_kind(line) for line in lines]

    # Indented lines continue the block above them ("    1 / 0" in a traceback, "    pass").
    prev = "blank"
    for n, line in enumerate(lines):
        if kinds[n] == "prose" and line[:1] in " \t" and prev not in ("prose", "blank"):
            kinds[n] = prev
        if kinds[n] != "blank":
            prev = kinds[n]

    # A terminal session pasted between two prompts: the output lines in between are
    # terminal output even when they read like prose ("Enumerating objects: 31, done.").
    prompts = [n for n, line in enumerate(lines) if _PROMPT.search(line)]
    for n in prompts:  # a marker line may start with my words: "oldu mu: C:\...\java.exe ..."
        m = re.search(r"[A-Za-z]:\\", lines[n])
        if m and m.start() > 0 and kinds[n] == "prose":
            head, tail = lines[n][: m.start()], lines[n][m.start():]
            lines[n] = tail
            lines.insert(n, head)  # keep my words on their own line
            kinds.insert(n, "prose")
            prompts = [p + 1 if p >= n else p for p in prompts]
            break
    if prompts:
        # Between the first and last prompt; with a single prompt, until my next question.
        end = prompts[-1] + 1 if len(prompts) >= 2 else len(lines)
        for n in range(prompts[0], end):
            if len(prompts) == 1 and n > prompts[0] and lines[n].rstrip().endswith("?"):
                break
            if kinds[n] != "blank":
                kinds[n] = "terminal"

    keep = [True] * len(lines)
    i = 0
    while i < len(lines):
        if kinds[i] in ("prose", "blank"):
            i += 1
            continue
        j = i  # extend the run over non-prose lines; blank lines don't break it
        while j < len(lines) and kinds[j] != "prose":
            j += 1
        while j > i and kinds[j - 1] == "blank":
            j -= 1
        run = [k for k in kinds[i:j] if k != "blank"]
        if len(run) >= MIN_BLOCK_LINES:
            kind = Counter(run).most_common(1)[0][0]
            for n in range(i, j):
                keep[n] = False
                removed[kind] += len(lines[n]) + 1
        i = j

    kept = "\n".join(line for line, k in zip(lines, keep) if k)
    clean_text = re.sub(r"\n{3,}", "\n\n", kept).strip()

    # Nothing but 1-2 pasted lines left (e.g. a single error line): still a paste. Code is
    # excluded unless it clearly is a statement, since short code-ish lines are often mine.
    left = [_line_kind(l) for l in clean_text.splitlines() if l.strip()]
    if left and all(
        k in ("stacktrace", "log", "terminal", "markup")
        or (k == "code" and re.search(r"[;{}]\s*$", l.strip()))
        for k, l in zip(left, [l for l in clean_text.splitlines() if l.strip()])
    ):
        removed[Counter(left).most_common(1)[0][0]] += len(clean_text)
        clean_text = ""

    pasted = sum(removed.values())
    reason = removed.most_common(1)[0][0] if removed else None
    is_noise = False
    if not re.search(r"\w", clean_text):
        clean_text = ""
        is_noise = True
        reason = reason or "empty"
    elif len(clean_text) > LONG_PASTE_CHARS:
        is_noise = True
        reason = "long_paste"

    return CleanResult(
        clean_text=clean_text,
        pasted_chars=min(pasted, len(text)),
        noise_reason=reason,
        is_noise=is_noise,
        lang=detect_lang(clean_text) if clean_text else None,
    )


def run(conn: sqlite3.Connection, force: bool = False) -> int:
    """Classify messages not yet processed by the current CLEAN_VERSION. Returns count."""
    where = "" if force else "WHERE clean_version IS NULL OR clean_version < ?"
    params: tuple = () if force else (CLEAN_VERSION,)
    rows = conn.execute(f"SELECT id, text FROM messages {where}", params).fetchall()
    with conn:
        for row in rows:
            r = clean(row["text"])
            conn.execute(
                """
                UPDATE messages
                SET clean_text = ?, pasted_chars = ?, noise_reason = ?, is_noise = ?,
                    lang = ?, clean_version = ?
                WHERE id = ?
                """,
                (r.clean_text, r.pasted_chars, r.noise_reason, int(r.is_noise), r.lang,
                 CLEAN_VERSION, row["id"]),
            )
    return len(rows)
