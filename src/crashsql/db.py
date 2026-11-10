"""Read-only database access for the agent.

The agent only talks to the `Database` protocol, so moving from DuckDB to Snowflake or
Postgres means adding one class here, not changing the agent.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import duckdb

from .config import AGENT_SCHEMA


class UnsafeQueryError(ValueError):
    pass


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[tuple[Any, ...]]
    truncated: bool = False


@dataclass
class Column:
    name: str
    type: str
    description: str | None = None
    sample_values: list[str] = field(default_factory=list)


@dataclass
class Table:
    name: str
    description: str | None
    row_count: int


class Database(Protocol):
    dialect: str

    def list_tables(self) -> list[Table]: ...
    def describe_table(self, table: str) -> list[Column]: ...
    def run_query(self, sql: str, max_rows: int = 50) -> QueryResult: ...


def check_read_only(sql: str) -> str:
    """Allow exactly one SELECT (or WITH ... SELECT) statement."""
    statements = duckdb.extract_statements(sql)
    if len(statements) != 1:
        raise UnsafeQueryError(f"Expected exactly one statement, got {len(statements)}.")
    if statements[0].type != duckdb.StatementType.SELECT:
        raise UnsafeQueryError(f"Only SELECT queries are allowed, got {statements[0].type.name}.")
    return statements[0].query.strip().rstrip(";")


class DuckDBDatabase:
    dialect = "duckdb"

    def __init__(
        self,
        path: Path | str,
        schema: str = AGENT_SCHEMA,
        timeout_s: float = 20.0,
        sample_value_limit: int = 30,
    ):
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(
                f"No warehouse at {self.path}. Run `crashsql load` and `crashsql build` first."
            )
        # A SELECT can still call read_csv()/read_parquet() on arbitrary paths or URLs,
        # so external access is disabled and the setting locked for this connection.
        self.con = duckdb.connect(
            str(self.path),
            read_only=True,
            config={"enable_external_access": False, "autoload_known_extensions": False},
        )
        self.con.execute(f"set schema = '{schema}'")
        self.con.execute("set lock_configuration = true")
        self.schema = schema
        self.timeout_s = timeout_s
        self.sample_value_limit = sample_value_limit

    def close(self) -> None:
        self.con.close()

    def list_tables(self) -> list[Table]:
        rows = self.con.execute(
            "select table_name, comment, estimated_size from duckdb_tables() "
            "where schema_name = ? order by table_name",
            [self.schema],
        ).fetchall()
        return [Table(name, comment, int(size or 0)) for name, comment, size in rows]

    def describe_table(self, table: str) -> list[Column]:
        rows = self.con.execute(
            "select column_name, data_type, comment from duckdb_columns() "
            "where schema_name = ? and table_name = ? order by column_index",
            [self.schema, table],
        ).fetchall()
        if not rows:
            known = ", ".join(t.name for t in self.list_tables())
            raise KeyError(f"Unknown table {table!r}. Available tables: {known}")
        columns = [Column(name, dtype, comment) for name, dtype, comment in rows]
        for col in columns:
            if col.type == "VARCHAR":
                col.sample_values = self._distinct_values(table, col.name)
        return columns

    def _distinct_values(self, table: str, column: str) -> list[str]:
        """Exact labels of a low-cardinality text column, so the model can filter on them."""
        values = self.con.execute(
            f'select distinct "{column}" from "{self.schema}"."{table}" '
            f'where "{column}" is not null limit {self.sample_value_limit + 1}'
        ).fetchall()
        if len(values) > self.sample_value_limit:
            return []
        return sorted(str(v[0]) for v in values)

    def run_query(self, sql: str, max_rows: int = 50) -> QueryResult:
        query = check_read_only(sql)
        timer = threading.Timer(self.timeout_s, self.con.interrupt)
        timer.start()
        try:
            cursor = self.con.execute(query)
            columns = [d[0] for d in cursor.description]
            rows = cursor.fetchmany(max_rows + 1)
        except duckdb.InterruptException as exc:
            raise TimeoutError(f"Query exceeded {self.timeout_s:.0f}s and was cancelled.") from exc
        finally:
            timer.cancel()
        return QueryResult(columns, rows[:max_rows], truncated=len(rows) > max_rows)

    def run_query_all(self, sql: str) -> QueryResult:
        """Full result set, used by the evaluator to compare against gold answers."""
        query = check_read_only(sql)
        cursor = self.con.execute(query)
        return QueryResult([d[0] for d in cursor.description], cursor.fetchall())
