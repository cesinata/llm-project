# 2. DuckDB and columnar analytics

The agent's SQL runs on DuckDB. This chapter explains what kind of database DuckDB is, why it suits this project, and the habits it shares with the warehouses used in industry (Snowflake, BigQuery, Redshift, Databricks SQL).

## Intuition

- **Two kinds of database work.** *Transactional* work (OLTP) reads and writes a few whole rows at a time: "update this order", "fetch this customer". *Analytical* work (OLAP) reads a few columns across very many rows: "deaths per council per year". Postgres and SQLite are built for the first; DuckDB and Snowflake for the second.
- **Row store vs column store.** A row store keeps each row's values together on disk, so reading one column means reading every column. A column store keeps each column together, so a query that uses 3 of 46 columns reads roughly 3/46 of the data.
- **Columns compress well.** A column holds one type of value, often with few distinct values (`light_condition` has 7). Storing a small code per row instead of the full text shrinks it a lot, and less data read means faster queries.
- **Vectorised execution.** DuckDB processes batches of about 2,048 values per operation rather than one row at a time, which suits modern CPUs.
- **In-process, like SQLite.** There is no server to install. The database is a single file, opened by a Python library, which makes it free, quick to set up and easy to run in CI.
- **Reads files directly.** `read_csv(...)` and `read_parquet(...)` query files without a separate import step. That is convenient for loading data, and a risk when the SQL comes from a model (chapter 6).

## The math

**Bytes read.** Suppose a table has $N$ rows and $C$ columns, column $j$ taking $w_j$ bytes per value, and a query uses the set of columns $U$.

$$\text{row store reads} \approx N \sum_{j=1}^{C} w_j \qquad \text{column store reads} \approx N \sum_{j \in U} w_j$$

If all columns are about the same width, the column store reads a fraction $|U| / C$ of the table. For a query using 3 of the 46 columns in `marts.crashes`, that is about 6.5%.

**Dictionary encoding.** A text column with $d$ distinct values can be stored as one dictionary of the $d$ strings plus a code of $\lceil \log_2 d \rceil$ bits per row.

Worked example with `light_condition`: $d = 7$, so each code needs $\lceil \log_2 7 \rceil = 3$ bits. For $N = 202{,}554$ rows that is $202{,}554 \times 3 / 8 \approx 76$ KB of codes. Stored as plain text, the values average 7.6 characters, about 1.54 MB. The encoded column is about 20 times smaller.

**Bit-packing** does the same for small integers. `accident_year` spans 2012 to 2026, so after subtracting 2012 each value fits in 4 bits instead of 64.

## Toy implementation

The same query on the same 202,554 rows, in SQLite (a row store) and DuckDB (a column store). Run it from the repo root after `crashsql load` and `crashsql build`.

```python
import sqlite3
import time

import duckdb

# Copy the crashes mart into both engines, in memory.
duck = duckdb.connect()
duck.execute("attach 'data/warehouse.duckdb' as w (read_only)")
duck.execute("create table crashes as select * from w.marts.crashes")

cursor = duck.execute("select * from crashes")
columns = [d[0] for d in cursor.description]
rows = [tuple(str(v) if hasattr(v, "isoformat") else v for v in r) for r in cursor.fetchall()]
lite = sqlite3.connect(":memory:")
lite.execute(f"create table crashes ({', '.join(columns)})")
lite.executemany(f"insert into crashes values ({', '.join('?' * len(columns))})", rows)

sql = """
    select lga_name, sum(persons_killed) as killed, avg(vehicles_involved) as avg_vehicles
    from crashes group by lga_name order by killed desc limit 5
"""


def timed(run, repeats=20):
    run()  # warm up
    start = time.perf_counter()
    for _ in range(repeats):
        result = run()
    return result, (time.perf_counter() - start) / repeats * 1000


lite_rows, lite_ms = timed(lambda: lite.execute(sql).fetchall())
duck_rows, duck_ms = timed(lambda: duck.execute(sql).fetchall())
print(f"{len(rows):,} rows x {len(columns)} columns")
print(f"SQLite (row store):    {lite_ms:6.1f} ms")
print(f"DuckDB (column store): {duck_ms:6.1f} ms")
print("Same answer:", [r[:2] for r in lite_rows] == [r[:2] for r in duck_rows])
```

On a 4-core cloud VM:

```text
202,554 rows x 46 columns
SQLite (row store):      98.9 ms
DuckDB (column store):    4.1 ms
Same answer: True
```

Both are in memory, so this measures the engines, not the disk. The gap grows with the number of rows: SQLite is a good database doing a job it was not designed for.

To see the compression DuckDB chose for each column:

```sql
select column_name, compression
from pragma_storage_info('marts.crashes')
where segment_type <> 'VALIDITY'
group by all;
```

In this warehouse, `light_condition` and `lga_name` use `DICT_FSST` (a dictionary plus compressed strings) and `accident_year` uses `BitPacking`.

## In this project

| What | Where | Detail |
|---|---|---|
| Loading | `load_raw` in `src/crashsql/data.py` | `read_csv(..., all_varchar = true)` loads the 70.9 MB CSV as-is into `raw.crashes`: 52 columns, all text. Types are cast later in dbt (chapter 3), so the loader can never silently guess a type wrong. |
| The warehouse | `data/warehouse.duckdb` | One 28 MB file holding `raw.crashes`, the `staging.stg_crashes` view and the two `marts` tables. It is smaller than the CSV even though it stores the data twice (raw and marts), because of compression. |
| Agent connection | `DuckDBDatabase.__init__` in `src/crashsql/db.py` | Opened `read_only=True`, with external file and URL access disabled and the settings locked. See chapter 6. |
| Swapping engines | the `Database` protocol in `src/crashsql/db.py` | The agent only calls `list_tables`, `describe_table` and `run_query`, so supporting Snowflake or Postgres means one new class, not a new agent. |
| Speed | the agent's queries | Typical grouped queries on `marts.crashes` take 1 to 5 ms, so almost all of an answer's latency is the language model, not the database. |

For comparison, exporting `marts.crashes` to Parquet (the column-store file format most warehouses read) gives an 8.3 MB file, an eighth of the CSV.

**Why DuckDB rather than Postgres or straight to Snowflake?** It is free, needs no server, runs the same in CI as on a laptop, and has a first-class dbt adapter. Its SQL is close to Postgres and Snowflake, so the skills and most queries transfer. Snowflake is wired up as a second dbt target for that reason (see the optional chapter).

## Failure modes

- **One writer at a time.** A DuckDB file can be opened read-write by one process only. Running `crashsql build` while another process holds the file open fails with `Could not set lock on file ... Conflicting lock is held`. Close `crashsql ask` sessions or notebooks before rebuilding.
- **Not a shared server.** DuckDB is great for one analyst or one app instance. Many concurrent writers or users is what Snowflake, BigQuery or Postgres are for.
- **Dialect differences.** In DuckDB, `1/2` returns `0.5`, and integer division is `7 // 2 = 3`. In Postgres and SQL Server, `1/2` is `0`. Snowflake also returns `0.5`. A model trained mostly on Postgres examples can write SQL that runs everywhere but gives different numbers. The agent is told the dialect for this reason.
- **Guessing types on load.** Letting `read_csv` infer types can read a postcode column as numbers (dropping leading zeros) or fail halfway through on one odd value. This project loads everything as text and casts in dbt, where the casts are visible and tested.
- **File access from SQL.** `select * from read_csv('/etc/passwd')` is a valid SELECT. Any database that can read files needs that switched off before running model-written SQL.

## Self-test

1. A query uses 5 of the 46 columns in `marts.crashes`. Roughly what fraction of the table does a column store read, assuming similar column widths?
2. `road_class` has 6 distinct values. How many bits per row does a dictionary code need, and roughly how many KB for all 202,554 rows?
3. Why does this project load the CSV with `all_varchar = true` instead of letting DuckDB infer types?
4. `crashsql build` fails with "Could not set lock on file". What is the likely cause?
5. What does `select 3 / 4` return in DuckDB, and in Postgres?
6. Why is the agent's connection opened with external access disabled, even though it is read-only?

<details>
<summary>Answers</summary>

1. About $5/46 \approx 11\%$.
2. $\lceil \log_2 6 \rceil = 3$ bits, so $202{,}554 \times 3 / 8 \approx 76$ KB (plus a tiny dictionary).
3. So loading never fails or silently mis-types a column. All casting happens in the dbt staging model, where every cast is visible in SQL and covered by tests.
4. Another process (an open `crashsql ask`, a notebook, a database viewer) has the warehouse file open, so dbt cannot get the write lock.
5. DuckDB returns `0.75`. Postgres returns `0` because both operands are integers.
6. Read-only stops writes to the warehouse, but a SELECT can still call `read_csv` or `read_parquet` on any local path or URL. Disabling external access (and locking the setting) blocks that.

</details>
