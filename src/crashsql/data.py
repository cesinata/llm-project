from __future__ import annotations

import shutil
import urllib.request
from pathlib import Path

import duckdb

from .config import CRASH_DATA_URL, RAW_CSV


def download(dest: Path = RAW_CSV, url: str = CRASH_DATA_URL, force: bool = False) -> Path:
    if dest.exists() and not force:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    with urllib.request.urlopen(url, timeout=120) as resp, open(tmp, "wb") as out:
        shutil.copyfileobj(resp, out)
    tmp.replace(dest)
    return dest


def load_raw(csv_path: Path, db_path: Path) -> int:
    """Load the CSV as-is into raw.crashes. All cleaning happens in dbt, not here."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(db_path)) as con:
        con.execute("create schema if not exists raw")
        con.execute(
            "create or replace table raw.crashes as "
            "select * from read_csv(?, header = true, all_varchar = true)",
            [str(csv_path)],
        )
        return con.execute("select count(*) from raw.crashes").fetchone()[0]
