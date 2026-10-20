import json
import shutil
import zipfile
from pathlib import Path

from typer.testing import CliRunner

from mnemos import stats
from mnemos.cli import app
from mnemos.ingest import claude
from mnemos.store import connect, insert_messages


def test_parse_roles_text_and_ids(claude_export: Path) -> None:
    messages = list(claude.load(claude_export))

    # 2 + 3 (the whitespace-only/thinking-only message is dropped); empty conversation adds none
    assert len(messages) == 5
    assert [m.role for m in messages] == ["user", "assistant", "user", "assistant", "user"]
    assert all(m.id.startswith("claude:") for m in messages)
    assert len({m.id for m in messages}) == 5


def test_content_blocks_preferred_and_non_text_blocks_skipped(claude_export: Path) -> None:
    msg = next(m for m in claude.load(claude_export) if m.id.endswith("bbbbbbbb-0000-4000-8000-000000000001"))
    assert msg.text == "Bu hafta sonu yürüyüşe başlayacağım, galiba.\n\nHangi ekipman lazım?"


def test_timestamps_normalized_to_utc(claude_export: Path) -> None:
    msg = next(m for m in claude.load(claude_export) if m.id.endswith("bbbbbbbb-0000-4000-8000-000000000001"))
    assert msg.created_at == "2025-04-12T15:30:00Z"


def test_missing_uuid_gets_stable_id(claude_export: Path) -> None:
    first = [m.id for m in claude.load(claude_export)]
    second = [m.id for m in claude.load(claude_export)]
    assert first == second


def test_ingest_is_idempotent(claude_export: Path, tmp_path: Path) -> None:
    conn = connect(tmp_path / "t.db")
    assert insert_messages(conn, claude.load(claude_export)) == (5, 0)
    assert insert_messages(conn, claude.load(claude_export)) == (0, 5)
    assert conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 5
    assert conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0] == 2


def test_loads_from_zip_and_directory(claude_export: Path, tmp_path: Path) -> None:
    folder = tmp_path / "export" / "nested"
    folder.mkdir(parents=True)
    shutil.copy(claude_export, folder / "conversations.json")
    archive = tmp_path / "export.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.write(claude_export, "data-2026/conversations.json")

    from_dir = [m.id for m in claude.load(tmp_path / "export")]
    from_zip = [m.id for m in claude.load(archive)]
    assert from_dir == from_zip == [m.id for m in claude.load(claude_export)]


def test_stats(claude_export: Path, tmp_path: Path) -> None:
    conn = connect(tmp_path / "t.db")
    insert_messages(conn, claude.load(claude_export))

    [s] = stats.by_source(conn)
    assert (s.source, s.conversations, s.user_messages, s.assistant_messages) == ("claude", 2, 3, 2)
    assert s.first.startswith("2025-03-01") and s.last.startswith("2025-04-12")
    assert stats.user_messages_per_month(conn) == [("2025-03", "claude", 1), ("2025-04", "claude", 2)]


def test_cli_end_to_end(claude_export: Path, tmp_path: Path) -> None:
    db = tmp_path / "t.db"
    runner = CliRunner()

    result = runner.invoke(app, ["ingest", str(claude_export), "--source", "claude", "--db", str(db)])
    assert result.exit_code == 0, result.output
    assert "5 messages added, 0 already present" in result.output

    result = runner.invoke(app, ["ingest", str(claude_export), "-s", "claude", "--db", str(db)])
    assert "0 messages added, 5 already present" in result.output

    result = runner.invoke(app, ["stats", "--db", str(db)])
    assert result.exit_code == 0, result.output
    assert "2025-03" in result.output and "claude" in result.output


def test_cli_rejects_unknown_source(claude_export: Path, tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["ingest", str(claude_export), "-s", "myspace", "--db", str(tmp_path / "t.db")])
    assert result.exit_code == 1


def test_rejects_non_array(tmp_path: Path) -> None:
    bad = tmp_path / "conversations.json"
    bad.write_text(json.dumps({"not": "a list"}))
    try:
        list(claude.load(bad))
    except ValueError:
        return
    raise AssertionError("expected ValueError")
