from pathlib import Path

from typer.testing import CliRunner

from mnemos.cli import app
from mnemos.lang import detect_lang
from mnemos.noise import clean, run
from mnemos.ingest import claude
from mnemos.store import connect, insert_messages


def test_plain_prose_is_untouched() -> None:
    text = "Bugün işten sonra oyun projesine devam etmek istiyorum. Sence nereden başlamalıyım?"
    r = clean(text)
    assert r.clean_text == text
    assert (r.pasted_chars, r.noise_reason, r.is_noise, r.lang) == (0, None, False, "tr")


def test_question_kept_stack_trace_removed() -> None:
    text = """Bu hata neden geliyor?

Exception in thread "main" java.lang.NullPointerException: name is null
    at com.example.App.greet(App.java:12)
    at com.example.App.main(App.java:5)
"""
    r = clean(text)
    assert r.clean_text == "Bu hata neden geliyor?"
    assert r.noise_reason == "stacktrace"
    assert not r.is_noise
    assert r.pasted_chars > 50


def test_python_traceback() -> None:
    text = """Traceback (most recent call last):
  File "app.py", line 3, in <module>
    main()
  File "app.py", line 2, in main
    1 / 0
ZeroDivisionError: division by zero
how do I fix this"""
    r = clean(text)
    assert r.clean_text == "how do I fix this"
    assert r.noise_reason == "stacktrace"
    assert r.lang == "en"


def test_fenced_code_removed() -> None:
    text = "Şu fonksiyonu düzeltir misin?\n```python\ndef f(x):\n    return x * 2\n```\nTeşekkürler"
    r = clean(text)
    assert r.clean_text == "Şu fonksiyonu düzeltir misin?\n\nTeşekkürler"
    assert r.noise_reason == "code"


def test_unfenced_java_block_removed() -> None:
    text = """Bu class'ı refactor edelim mi?
public class User {
    private String name;
    public String getName() {
        return name;
    }
}"""
    r = clean(text)
    assert r.clean_text == "Bu class'ı refactor edelim mi?"
    assert r.noise_reason == "code"


def test_logs_removed() -> None:
    text = """2026-10-20 19:01:02 INFO Starting app
2026-10-20 19:01:03 WARN Slow query
2026-10-20 19:01:04 ERROR Connection refused
Sunucu neden düşüyor?"""
    r = clean(text)
    assert r.clean_text == "Sunucu neden düşüyor?"
    assert r.noise_reason == "log"


def test_terminal_session_between_prompts_removed() -> None:
    text = r"""C:\Users\me\project>   git push -u origin main
Enumerating objects: 31, done.
Counting objects: 100% (31/31), done.
Writing objects: 100% (31/31), 20.99 KiB, done.

C:\Users\me\project>   uv sync
Resolved 13 packages in 22ms
 + pytest==9.1.1
 + typer==0.27.3

C:\Users\me\project>"""
    r = clean(text)
    assert r.is_noise
    assert r.clean_text == ""
    assert r.noise_reason == "terminal"


def test_single_pasted_error_line_only_is_noise() -> None:
    r = clean("java.lang.IllegalStateException: boom")
    assert r.is_noise and r.noise_reason == "stacktrace"


def test_short_code_like_lines_inside_prose_are_kept() -> None:
    text = "Bence en iyi yol (en azından şimdilik) SQLite kullanmak.\nSonra Postgres'e geçeriz."
    assert clean(text).clean_text == text


def test_turkish_words_that_look_like_keywords_are_kept() -> None:
    for text in (
        "public olunca collaboration yapabiliyor musun?",
        "var nasıl yok",
        "package neden görmüyor stddraw'ı",
        "new ArrayList<>() yapsam hata alır mıyım?",
    ):
        r = clean(text)
        assert r.clean_text == text and not r.is_noise, text


def test_my_words_inside_a_fence_are_kept() -> None:
    r = clean("```\nfindHighestPriorityPatient'ı search metodu olarak BST class'ına alsak.\n```")
    assert r.clean_text == "findHighestPriorityPatient'ı search metodu olarak BST class'ına alsak."
    assert not r.is_noise


def test_question_inside_untagged_fence_with_code_is_kept() -> None:
    text = """```
Bu nasıl çalışıyor anlat şimdi:
private List<Integer> dijkstra(int start, int end) {
    int[] dist = new int[n];
    return path;
}
```"""
    r = clean(text)
    assert r.clean_text == "Bu nasıl çalışıyor anlat şimdi:"
    assert r.noise_reason == "code"


def test_intellij_run_output_removed() -> None:
    text = r"""Tamam şimdi oldu mu:  C:\Users\me\.jdks\openjdk-25\bin\java.exe "-javaagent:idea_rt.jar" Main
Simulation started
Patient Ali assigned to doctor 3
All patients treated

Process finished with exit code 0"""
    r = clean(text)
    assert r.clean_text == "Tamam şimdi oldu mu:"
    assert r.noise_reason == "terminal"


def test_single_prompt_session_removed_until_my_question() -> None:
    text = r"""Windows PowerShell
Telif Hakkı (C) Microsoft Corporation. Tüm hakları saklıdır.

PS C:\WINDOWS\System32> Get-NetConnectionProfile
Name             : Ev Ağı
NetworkCategory  : Public

Bunu private yapmam lazım mı?"""
    r = clean(text)
    assert r.clean_text == "Bunu private yapmam lazım mı?"
    assert r.noise_reason == "terminal"


def test_pasted_table_removed() -> None:
    text = "Bu tabloyu açıklar mısın?\n#\tDay\tDate\n1\tMon\t2026-10-19\n2\tTue\t2026-10-20"
    r = clean(text)
    assert r.clean_text == "Bu tabloyu açıklar mısın?"
    assert r.noise_reason == "table"


def test_long_paste_flagged() -> None:
    article = ("This is a long pasted article sentence about something general. " * 80).strip()
    r = clean(article)
    assert r.is_noise and r.noise_reason == "long_paste"


def test_lang() -> None:
    assert detect_lang("Bu projeyi nasıl yapabilirim sence?") == "tr"
    assert detect_lang("How can I export my data from this app?") == "en"
    assert detect_lang("Bence bu approach is better for the project ama emin değilim") == "mixed"
    assert detect_lang("ok") is None


def test_run_is_incremental(claude_export: Path, tmp_path: Path) -> None:
    conn = connect(tmp_path / "t.db")
    insert_messages(conn, claude.load(claude_export))
    assert run(conn) == 5
    assert run(conn) == 0
    assert run(conn, force=True) == 5
    assert conn.execute("SELECT COUNT(*) FROM messages WHERE clean_version IS NULL").fetchone()[0] == 0


def test_ingest_runs_filter_and_stats_show_it(claude_export: Path, tmp_path: Path) -> None:
    db = str(tmp_path / "t.db")
    runner = CliRunner()
    result = runner.invoke(app, ["ingest", str(claude_export), "-s", "claude", "--db", db])
    assert "Noise filter applied to 5 new messages" in result.output

    result = runner.invoke(app, ["stats", "--db", db])
    assert result.exit_code == 0, result.output
    assert "my own words left" in result.output

    result = runner.invoke(app, ["clean", "--db", db, "--review", "3"])
    assert result.exit_code == 0, result.output
