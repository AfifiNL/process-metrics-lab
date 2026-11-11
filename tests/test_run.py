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
