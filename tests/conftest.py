import os
import subprocess
from pathlib import Path

import pytest

from crashsql.config import DBT_DIR, SAMPLE_CSV
from crashsql.data import load_raw
from crashsql.db import DuckDBDatabase


@pytest.fixture(scope="session")
def warehouse(tmp_path_factory) -> Path:
    """A real warehouse built from the 1,000-row sample with the same dbt project."""
    path = tmp_path_factory.mktemp("wh") / "warehouse.duckdb"
    load_raw(SAMPLE_CSV, path)
    subprocess.run(
        ["dbt", "build", "--project-dir", str(DBT_DIR), "--profiles-dir", str(DBT_DIR), "--quiet"],
        env={**os.environ, "CRASHSQL_DB": str(path)},
        check=True,
    )
    return path


@pytest.fixture()
def db(warehouse):
    database = DuckDBDatabase(warehouse)
    yield database
    database.close()
