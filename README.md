# Mnemos

A local-first personal memory engine. It ingests my chat exports from Claude, ChatGPT and
Gemini, turns them into a queryable fact base about me, and produces evidence-backed
self-insight reports.

See [CLAUDE.md](CLAUDE.md) for goals, rules, architecture and the phase plan.

> **Privacy:** all personal data lives in `data/`, which is git-ignored. Nothing personal is
> ever committed. Tests use synthetic fixtures only.

## Status

| Phase | Scope | State |
|---|---|---|
| 1 | Ingest (Claude ✅, ChatGPT, Gemini) + `stats` | in progress |
| 2 | Noise filtering + language detection | ✅ |
| 3 | Fact extraction | — |
| 4 | Ask (CLI + MCP server) | — |
| 5 | Insights report | — |
| 6 | Self-portrait | — |

## Setup

```powershell
# Windows (PowerShell)
winget install astral-sh.uv
uv sync
```

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync
```

## Usage

Put your export somewhere under `data/raw/` (the ZIP itself, the extracted folder, or just
`conversations.json` all work).

```bash
# Ingest a Claude export (safe to run again: duplicates are skipped)
uv run mnemos ingest data/raw/claude/my-export.zip --source claude

# Overview: counts, date range, messages per month, rough token size of my messages
uv run mnemos stats
```

### Noise filter (phase 2)

`ingest` runs it automatically on new messages. It removes pasted code, logs, stack traces,
terminal sessions (incl. IntelliJ run output) and tables from each message and keeps my own
words in `clean_text`, so "why does this fail?" + 40 lines of stack trace becomes just the
question. It also tags each message `tr`, `en` or `mixed`.

```bash
uv run mnemos clean              # re-run after the rules change (only outdated rows)
uv run mnemos clean --force      # re-run everything
uv run mnemos clean --review 10  # print 10 random decisions to check the filter
```

Known limit: pasted *prose* (an article, an AI answer, a course list) can't be told apart
from my own writing by rules; phase 3's extraction prompt handles that.

The database is created at `data/mnemos.db` (override with `--db`).

### Inspecting a new export format without exposing content

```bash
uv run python scripts/dump_schema.py data/raw/chatgpt/conversations.json
```

Prints only the structure (key paths, value types, list lengths, string length ranges),
never any values. Safe to paste into a chat with an AI to build a new adapter.

## Development

```bash
uv run pytest
```
