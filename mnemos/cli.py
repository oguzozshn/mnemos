"""Command line interface: `mnemos ingest`, `mnemos stats`."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Annotated

import typer

from mnemos import ingest as ingest_mod
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

    typer.echo(
        "\n~tokens are a rough estimate (chars / 3.5). Long pasted content will be filtered "
        "out in phase 2, so the extraction cost will be lower than the 'my ~tokens' total."
    )


if __name__ == "__main__":
    app()
