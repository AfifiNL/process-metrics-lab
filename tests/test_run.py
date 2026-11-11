from __future__ import annotations

from pathlib import Path

import pytest

from process_metrics.cli import main
from process_metrics.run import RunError, load_checks, run


def _sql_dir(tmp_path: Path, name: str, text: str) -> Path:
    (tmp_path / "checks").mkdir()
    (tmp_path / "checks" / name).write_text(text, encoding="utf-8")
    return tmp_path


def test_a_check_needs_a_header(tmp_path: Path) -> None:
    with pytest.raises(RunError, match="effect"):
        load_checks(_sql_dir(tmp_path, "01_x.sql", "select 1"))


def test_a_check_needs_a_known_effect(tmp_path: Path) -> None:
    text = "-- effect: fix\n-- catches: something that should not happen at all\nselect 1"
    with pytest.raises(RunError, match="effect"):
        load_checks(_sql_dir(tmp_path, "01_x.sql", text))


def test_a_check_file_needs_a_plain_name(tmp_path: Path) -> None:
    with pytest.raises(RunError, match="named"):
        load_checks(_sql_dir(tmp_path, "check one.sql", "select 1"))


def test_no_event_log_is_a_clear_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(RunError, match="generate"):
        run(tmp_path / "events.csv")
    assert main(["report", "--build", str(tmp_path)]) == 2
    assert "generate" in capsys.readouterr().err


def test_report_prints_the_three_tables(build: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["report", "--build", str(build)]) == 0
    out = capsys.readouterr().out
    assert "Weekly KPIs" in out
    assert "repeated_event_id" in out
    assert "MISSED" not in out
    assert out.count("[ok]") == 13


def test_a_comment_in_the_body_is_not_the_header(tmp_path: Path) -> None:
    text = (
        "-- effect: exclude\n-- catches: something that should not happen at all\n"
        "select 1\n-- effect: report\n"
    )
    assert load_checks(_sql_dir(tmp_path, "01_x.sql", text))[0].effect == "exclude"


HEADER = (
    "event_id,ticket_id,event,occurred_at,loaded_at,source,language,category,queue,priority,"
    "drafted_by,flagged,actor"
)
ROW = "A-1,A,received,2026-08-04 08:00:00,2026-08-04 08:00:05,email,en,,,,,,"


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("", "wrong columns|cannot be read"),
        (HEADER.replace(",actor", "") + "\n", "wrong columns"),
        (HEADER + ",extra\n", "wrong columns"),
        (HEADER + "\n" + ROW.replace("08:00:00,", "08:00:00+02:00,") + "\n", "without an offset"),
        (HEADER + "\n" + ROW.replace("2026-08-04 08:00:00", "04/08/2026 08:00") + "\n", "offset"),
        (HEADER + "\n" + ROW[:-2] + "maybe,\n", "flagged"),
    ],
    ids=["empty file", "missing column", "extra column", "offset", "other format", "flagged"],
)
def test_a_log_that_cannot_be_trusted_is_refused(
    tmp_path: Path, content: str, message: str
) -> None:
    path = tmp_path / "events.csv"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(RunError, match=message):
        run(path)


def test_columns_are_read_by_name_not_position(tmp_path: Path) -> None:
    swapped = HEADER.replace("source,language", "language,source")
    row = ROW.replace("email,en", "en,email")
    path = tmp_path / "events.csv"
    path.write_text(f"{swapped}\n{row}\n", encoding="utf-8")
    con = run(path)
    assert con.execute("select source, language from fct_tickets").fetchone() == ("email", "en")
    con.close()


def test_report_without_a_truth_file_prints_the_kpis_only(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "events.csv").write_text(f"{HEADER}\n{ROW}\n", encoding="utf-8")
    assert main(["report", "--build", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "Weekly KPIs" in out
    assert "nothing planted to compare" in out
