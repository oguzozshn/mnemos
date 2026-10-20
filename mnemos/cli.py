"""Command line interface: `mnemos ingest`, `mnemos clean`, `mnemos stats`."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Annotated

import typer

from mnemos import ingest as ingest_mod
from mnemos import noise as noise_mod
from mnemos import stats as stats_mod
from mnemos.ingest._io import ExportNotFound
from mnemos.store import DEFAULT_DB_PATH, connect, insert_messages

app = typer.Typer(add_completion=False, no_args_is_help=True, help=__doc__)

DbOption = Annotated[Path, typer.Option("--db", help="SQLite database file.")]


@app.command()
def ingest(
    path: Annotated[Path, typer.Argument(help="Export ZIP, extracted folder, or JSON file.")],
    source: Annotated[str, typer.Option("--source", "-s", help="claude | chatgpt | gemini")],
    db: DbOption = DEFAULT_DB_PATH,
) -> None:
    """Import a chat export. Safe to re-run: messages already stored are skipped."""
    try:
        messages = ingest_mod.load(path, source)
        conn = connect(db)
        added, skipped = insert_messages(conn, messages)
    except (ExportNotFound, ValueError) as exc:
        typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from None
    typer.echo(f"{source}: {added:,} messages added, {skipped:,} already present.")
    if added:
        n = noise_mod.run(conn)
        typer.echo(f"Noise filter applied to {n:,} new messages.")


@app.command()
def clean(
    db: DbOption = DEFAULT_DB_PATH,
    force: Annotated[bool, typer.Option(help="Re-process every message.")] = False,
    review: Annotated[
        int, typer.Option(help="Print N random filter decisions on my messages to check them.")
    ] = 0,
) -> None:
    """Separate my own words from pasted code/logs/stack traces (phase 2)."""
    conn = connect(db)
    n = noise_mod.run(conn, force=force)
    typer.echo(f"Processed {n:,} messages (filter v{noise_mod.CLEAN_VERSION}).")

    if review:
        rows = conn.execute(
            """
            SELECT text, clean_text, noise_reason, is_noise, pasted_chars, lang FROM messages
            WHERE role = 'user' AND (noise_reason IS NOT NULL OR LENGTH(text) > 300)
            ORDER BY RANDOM() LIMIT ?
            """,
            (review,),
        ).fetchall()
        for r in rows:
            status = "NOISE" if r["is_noise"] else "kept"
            typer.secho(
                f"\n[{status}] reason={r['noise_reason']} pasted={r['pasted_chars']:,} "
                f"of {len(r['text']):,} chars, lang={r['lang']}",
                bold=True,
            )
            typer.echo("  original: " + _preview(r["text"]))
            typer.echo("  kept    : " + (_preview(r["clean_text"]) or "(nothing)"))


def _preview(text: str | None, width: int = 160) -> str:
    flat = " ".join((text or "").split())
    return flat if len(flat) <= width else flat[: width - 1] + "…"


@app.command()
def stats(db: DbOption = DEFAULT_DB_PATH) -> None:
    """Overview of what is stored: counts, date range, activity per month, size."""
    if not Path(db).exists():
        typer.secho(f"No database at {db}. Run `mnemos ingest` first.", fg=typer.colors.YELLOW)
        raise typer.Exit(1)
    conn = connect(db)

    sources = stats_mod.by_source(conn)
    if not sources:
        typer.echo("Database is empty.")
        return

    typer.secho("\nBy source", bold=True)
    header = f"{'source':<9}{'convs':>7}{'my msgs':>9}{'AI msgs':>9}{'my ~tokens':>12}{'AI ~tokens':>12}  range"
    typer.echo(header)
    typer.echo("-" * len(header) + "-" * 24)
    for s in sources:
        typer.echo(
            f"{s.source:<9}{s.conversations:>7,}{s.user_messages:>9,}{s.assistant_messages:>9,}"
            f"{s.user_tokens_est:>12,}{s.assistant_tokens_est:>12,}  "
            f"{(s.first or '')[:10]} → {(s.last or '')[:10]}"
        )

    typer.secho("\nMy messages per month", bold=True)
    per_month: dict[str, dict[str, int]] = defaultdict(dict)
    for month, source, n in stats_mod.user_messages_per_month(conn):
        per_month[month][source] = n
    peak = max(sum(v.values()) for v in per_month.values())
    for month, by_src in per_month.items():
        total = sum(by_src.values())
        bar = "█" * max(1, round(30 * total / peak))
        detail = ", ".join(f"{k} {v}" for k, v in sorted(by_src.items()))
        typer.echo(f"{month}  {total:>5,}  {bar}  ({detail})")

    typer.secho("\nLength of my messages", bold=True)
    for bucket, n in stats_mod.user_message_length_buckets(conn):
        typer.echo(f"  {bucket[3:]:<36}{n:>7,}")

    ns = stats_mod.noise(conn)
    typer.secho("\nNoise filter (my messages)", bold=True)
    if not ns.classified:
        typer.echo("  Not run yet. Run `mnemos clean`.")
    else:
        if ns.unclassified:
            typer.echo(f"  {ns.unclassified:,} messages not classified yet: run `mnemos clean`.")
        typer.echo(f"  pure noise (nothing of mine left): {ns.noise_messages:>7,}")
        typer.echo(f"  pasted content removed           : {stats_mod.est_tokens(ns.pasted_chars):>7,} ~tokens")
        typer.echo(f"  my own words left                : {ns.clean_tokens_est:>7,} ~tokens")
        if ns.by_reason:
            typer.echo("  pasted content by kind: " + ", ".join(f"{k} {v}" for k, v in ns.by_reason))
        if ns.by_lang:
            typer.echo("  language of my messages: " + ", ".join(f"{k} {v}" for k, v in ns.by_lang))

    typer.echo("\n~tokens are a rough estimate (chars / 3.5).")


if __name__ == "__main__":
    app()
