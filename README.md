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
| 2 | Noise filtering | — |
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
