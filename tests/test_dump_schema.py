import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("dump_schema", ROOT / "scripts" / "dump_schema.py")
dump_schema = importlib.util.module_from_spec(spec)
sys.modules["dump_schema"] = dump_schema  # dataclasses look the module up by name
spec.loader.exec_module(dump_schema)


def test_prints_structure_but_no_content(claude_export: Path, capsys) -> None:
    dump_schema.main([str(claude_export)])
    out = capsys.readouterr().out

    assert "$[].chat_messages[].sender" in out
    assert "values {assistant, human}" in out
    # No message text, titles or ids may leak
    for secret in ("hiking", "yürüyüş", "Hafta sonu", "11111111-1111", "bbbbbbbb"):
        assert secret not in out


def test_id_keyed_objects_are_collapsed(tmp_path: Path, capsys) -> None:
    data = {
        "mapping": {
            "9f0c1c4e-1111-4222-8333-444455556666": {"message": {"author": {"role": "user"}}},
            "aa0c1c4e-1111-4222-8333-444455556666": {"message": {"author": {"role": "assistant"}}},
        }
    }
    f = tmp_path / "x.json"
    f.write_text(json.dumps(data))
    dump_schema.main([str(f)])
    out = capsys.readouterr().out

    assert "$.mapping.<*>.message.author.role" in out
    assert "9f0c1c4e" not in out
