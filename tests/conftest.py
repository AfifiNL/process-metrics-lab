from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import duckdb
import pytest

from process_metrics import reference
from process_metrics.generate import generate
from process_metrics.run import run


@pytest.fixture(scope="session")
def build(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The full generated data set, from the fixed seed."""
    out = tmp_path_factory.mktemp("build")
    generate(out)
    return out


@pytest.fixture(scope="session")
def con(build: Path) -> Iterator[duckdb.DuckDBPyConnection]:
    connection = run(build / "events.csv")
    yield connection
    connection.close()


@pytest.fixture(scope="session")
def ref(build: Path) -> dict[str, Any]:
    return reference.compute(build)


@pytest.fixture(scope="session")
def truth(build: Path) -> dict[str, Any]:
    return reference.load(build)[1]
