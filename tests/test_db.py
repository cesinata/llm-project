import duckdb
import pytest

from crashsql.db import UnsafeQueryError, check_read_only


@pytest.mark.parametrize(
    "sql",
    [
        "drop table crashes",
        "delete from crashes",
        "insert into crashes select * from crashes",
        "select 1; select 2",
        "copy crashes to 'out.csv'",
        "attach 'other.duckdb'",
        "install httpfs",
        "pragma version",
    ],
)
def test_rejects_non_select(sql):
    with pytest.raises(UnsafeQueryError):
        check_read_only(sql)


def test_accepts_cte():
    assert check_read_only("with x as (select 1 as a) select a from x;").startswith("with")


@pytest.mark.parametrize(
    "sql",
    [
        "select * from read_csv('/etc/passwd')",
        "select * from 'data/sample/crashes_sample.csv'",
        "select * from read_text('https://example.com')",
    ],
)
def test_select_cannot_touch_files_or_network(db, sql):
    with pytest.raises(duckdb.PermissionException):
        db.run_query(sql)


def test_settings_are_locked(db):
    with pytest.raises(duckdb.Error):
        db.con.execute("set enable_external_access = true")


def test_only_marts_tables_are_listed(db):
    assert {t.name for t in db.list_tables()} == {"crashes", "lga_yearly_summary"}


def test_describe_includes_docs_and_labels(db):
    columns = {c.name: c for c in db.describe_table("crashes")}
    assert "people killed" in columns["persons_killed"].description
    assert "Fatal accident" in columns["severity"].sample_values
    # High-cardinality columns get no value list.
    assert columns["accident_no"].sample_values == []


def test_unknown_table_lists_alternatives(db):
    with pytest.raises(KeyError, match="crashes"):
        db.describe_table("accidents")


def test_run_query_truncates(db):
    result = db.run_query("select accident_no from crashes", max_rows=5)
    assert len(result.rows) == 5
    assert result.truncated


def test_council_rename_is_merged(db):
    rows = db.run_query("select count(*) from crashes where lga_name = 'MORELAND'").rows
    assert rows == [(0,)]
