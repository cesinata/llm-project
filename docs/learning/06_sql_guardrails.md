# 6. SQL guardrails

The agent runs SQL written by a language model. Treat that SQL like input from a stranger: it may be wrong, slow, or harmful, by accident or because a question was crafted to make it so (prompt injection).

## Intuition

- The system prompt saying "only write SELECT" is not a control. Models ignore instructions under pressure.
- Keyword blocklists (`if "drop" in sql`) fail on comments, strings and creative spacing.
- Defence in depth: parse the statement, open the database read-only, disable file and URL reads, lock those settings, and cancel long queries.

## The math

Parsing beats string search because the database already has a grammar. Let $S$ be the list of statements DuckDB extracts from the input. The guard accepts the input only when:

$$|S| = 1 \quad \wedge \quad \mathrm{type}(S_1) = \mathrm{SELECT}$$

Including `WITH ... SELECT`. Anything else (`DROP`, `COPY`, `ATTACH`, multiple statements) is rejected before execution. Separately, the connection configuration forbids external access, so even a SELECT that calls `read_csv('/etc/passwd')` cannot leave the warehouse.

## Toy implementation

```python
import duckdb


def check_read_only(sql: str) -> str:
    statements = duckdb.extract_statements(sql)
    if len(statements) != 1:
        raise ValueError(f"Expected one statement, got {len(statements)}")
    if statements[0].type != duckdb.StatementType.SELECT:
        raise ValueError(f"Only SELECT allowed, got {statements[0].type.name}")
    return statements[0].query.strip().rstrip(";")


for sql in [
    "select count(*) from crashes",
    "drop table crashes",
    "select 1; select 2",
    "with x as (select 1 as a) select a from x",
]:
    try:
        print("OK ", check_read_only(sql)[:40])
    except ValueError as exc:
        print("NO ", sql, "->", exc)
```

## In this project

`check_read_only` in `src/crashsql/db.py` is the parser gate. `DuckDBDatabase.__init__` then opens the file with:

- `read_only=True`
- `enable_external_access=False`
- `autoload_known_extensions=False`
- `lock_configuration=true` so later SQL cannot turn those settings back on

Queries are cancelled after 20 seconds via `connection.interrupt()`. Preview results sent to the model are capped at 30 rows; the evaluator uses `run_query_all` for full gold comparisons.

`tests/test_db.py` tries writes (`DROP`, `DELETE`, `INSERT`), multi-statement input, `read_csv` on a local path, URL reads, and unlocking external access. Each path must fail.

## Failure modes

- Trusting the prompt alone.
- Keyword blocklists that look safe in demos and fail on real model output.
- A read-only connection that can still read arbitrary files through table functions.
- Unbounded queries that never finish without a timeout.
- Giving the agent a role that can write or see more schemas than it needs.
- Leaking secrets through rich database error messages (less of an issue on this public dataset, still a habit to watch).

## Self-test

1. Why is `"drop" in sql.lower()` a weak guard?
2. Why disable external access even on a read-only connection?
3. What does `lock_configuration` prevent?
4. Why cap preview rows returned to the model?

<details>
<summary>Answers</summary>

1. The word can sit inside a string or comment, or the harmful statement can avoid that token while still writing.
2. `SELECT` can still call `read_csv` / `read_parquet` on paths and URLs unless that capability is switched off.
3. The model issuing `SET enable_external_access = true` (or similar) mid-session.
4. To keep tool outputs small and avoid dumping huge results into later prompt turns.

</details>
