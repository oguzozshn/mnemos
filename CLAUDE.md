# Mnemos — Personal Memory Engine

## Goal
Build a local-first personal memory system from my AI chat exports (Claude, ChatGPT, Gemini).
Two outputs:
1. **A memory any AI can query** — a fact base about me, exposed via CLI and an MCP server,
   so assistants (Claude Code, Claude Desktop, my Argos app) can answer questions about me from it.
2. **Self-insight** — reports that show me patterns in what I think about, start, abandon, and repeat.

## Hard rules
- **Privacy first.** Raw exports, the database, and all derived data live in `data/` which is
  git-ignored. Never commit personal data, never print large chunks of it in logs.
- **Only my messages are facts.** Assistant replies are context only. A suggestion the assistant
  made is never stored as something I said.
- **Every fact has provenance:** source platform, conversation id, message id, timestamp.
- **Never delete facts on contradiction.** Mark the older one `superseded_by` the newer one.
- **Evidence over interpretation.** Every observation in a report cites the messages it is
  based on. Descriptive observations are fine ("you framed 7 of 9 career decisions in terms of
  freedom"); clinical diagnoses and type labels (MBTI etc.) are not.
- **Absence of evidence is not evidence of absence.** Chats only show what I told an AI.
  "Mentioned a plan, never mentioned it again" must be reported as exactly that, never as
  "didn't do it".
- **Keep Claude Code out of real data.** `.claude/settings.json` denies `Read(./data/**)`;
  development uses synthetic fixtures only.
- All code, comments, README and commit messages in English.

## Stack
- Python 3.12, `uv` for env/deps
- SQLite + `sqlite-vec` (single file at `data/mnemos.db`)
- Embeddings: `sentence-transformers` (multilingual model — my chats are Turkish + English)
- LLM extraction: Anthropic API (Haiku for bulk extraction, batch API where possible)
- Topic modeling: BERTopic
- CLI: Typer. MCP server: official `mcp` Python SDK.
- Tests: pytest, with small synthetic fixture exports (never real data)

## Architecture
```
mnemos/
  ingest/        # one adapter per platform -> common Message schema
    claude.py    # conversations.json from Claude export
    chatgpt.py   # conversations.json (tree structure, follow `mapping`/`parent`)
    gemini.py    # Google Takeout My Activity JSON (flat prompt/response records,
                 # group into threads by time proximity)
  store/         # SQLite schema, migrations, vector index
  extract/       # LLM fact extraction + dedup + supersession
  retrieve/      # profile summary + semantic search + structured queries
  insights/      # topic timeline, project lifecycle, repeated questions, idea evolution
  mcp_server.py
  cli.py
data/            # git-ignored: raw/, mnemos.db, reports/
tests/fixtures/  # synthetic exports only
```

## Common schema
`messages(id, source, conversation_id, conversation_title, role, text, created_at, lang, is_noise)`
`facts(id, subject, category, statement, valid_from, superseded_by, source_message_ids, confidence)`
Categories: identity, work, education, project, preference, person, decision, idea, goal.

## Phases (do them in order, each must be usable before the next)
1. **Ingest** — Claude adapter first, then ChatGPT, then Gemini. `mnemos ingest <path>` is
   idempotent (re-importing the same export adds nothing). `mnemos stats` prints counts,
   date range, messages per month, per source.
2. **Noise filtering** — flag pasted code, logs, stack traces, large file dumps so they are
   excluded from extraction and topic modeling.
3. **Extract** — batch my messages through the LLM, write facts with provenance, dedup
   near-identical facts, handle supersession. Show cost estimate before running.
4. **Ask** — `mnemos ask "..."` and an MCP server exposing `get_profile`, `search_memory`,
   `query_facts`. Answers cite fact ids.
5. **Insights** — HTML report: topic timeline, projects (first/last mention, status),
   repeated questions, how my views on a topic changed over time.
6. **Self-portrait** — see section below.

## Retrieval & grouping
- **Hybrid search:** vector (sqlite-vec) + BM25 (SQLite FTS5), fused with reciprocal rank
  fusion, then a local cross-encoder reranker (e.g. bge-reranker). BM25 matters for project
  names, people and technical terms.
- **Topics:** BERTopic locally; the LLM only writes short labels for each cluster.
- **Summary tree (RAPTOR-style):** cluster -> summarize -> cluster the summaries -> summarize,
  up to a top-level "main themes" node. Every node links down to its source messages.
  Used both for the report and for answering broad questions at the right level of detail.
- **Graph:** entities (person, project, company, topic) and relations stored as an edge table
  in SQLite with `valid_from` / `valid_to`. Migrate to Graphiti only if SQLite gets in the way.
- **Later experiment:** LightRAG on the same data, compare answers. No full GraphRAG (cost).

## Self-portrait (phase 6)
Evidence-backed report, regenerated periodically so versions can be compared over time.
Each section lists observations with linked message excerpts and dates.
- **How I talk:** language mix (TR/EN), message length, question vs statement ratio,
  hedging and certainty words, how I phrase requests. Mostly computed, not LLM-judged.
- **What I want:** goals and wishes over time; which ones persist, which faded.
- **What I did:** projects and milestones with first/last mention and any completion signal.
- **How I approach things:** how I frame decisions, risks and problems; recurring reasoning
  patterns, each with examples.
- **Skills:** topics where I explain or decide vs. topics where I ask basics; how question
  depth in a topic changes over time (learning curve).
- **Said vs. later:** "I used to say X, later said Y" (contradiction/supersession pairs).
- **Repeated intentions:** intentions ("I will start / build / learn ...") clustered by
  meaning, with how many times and over what span they recurred, and whether any later
  message shows progress.
- **What next:** clearly separated and labeled as suggestions, each tied to observations above.
- Caveat shown at the top: people bring problems to AI more than wins, so the data skews
  toward worries and unfinished things.

## Working style
- Small, reviewable steps. When changing code, show only the changed file or function.
- Ask before running anything that calls the paid API on the full dataset.
