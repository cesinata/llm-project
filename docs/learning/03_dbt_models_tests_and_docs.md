# 3. dbt models, tests and docs

The agent never sees the raw CSV. It queries tables that dbt builds, tests and documents. This chapter explains how dbt works, the layering used here, and the data problem it caught: a council that changed its name.

## Intuition

- **ELT, not ETL.** Load the source data as-is first (**E**xtract, **L**oad), then clean and reshape it with SQL inside the warehouse (**T**ransform). dbt is the tool for the T.
- **A model is a SELECT statement in a file.** `models/marts/crashes.sql` contains a query; dbt runs it and saves the result as a table or view called `crashes`. You write the logic, and dbt handles the `create table`.
- **`ref()` builds the dependency graph.** Writing `{{ ref('stg_crashes') }}` instead of a table name tells dbt that `crashes` depends on `stg_crashes`. dbt builds models in dependency order and can swap schemas or warehouses without editing the SQL.
- **Layers keep each step simple.**
    - *Sources*: the raw data, exactly as loaded.
    - *Staging*: one model per source table, with types cast, names cleaned and labels fixed. No business logic.
    - *Marts*: tables shaped for the people (or agents) asking questions, with friendly column names and derived flags.
- **A test is a query that returns the bad rows.** If it returns zero rows, the test passes. Built-in tests (`unique`, `not_null`, `accepted_values`) cover the common cases; any other rule is a short SQL file.
- **Docs live next to the code.** Column descriptions in YAML become documentation, and with `persist_docs` they are also written into the database as column comments. That matters here, because the agent reads them.

## The math

dbt's core is a graph problem. Models are nodes, and each `ref()` adds an edge from the referenced model to the one using it. The graph must be a **DAG** (directed acyclic graph): if `a` refs `b` and `b` refs `a`, nothing can be built first, and dbt refuses to run.

dbt builds the models in a **topological order**: an order in which every model comes after all the models it refs. For this project the graph is a short chain:

$$\texttt{raw.crashes} \rightarrow \texttt{stg\_crashes} \rightarrow \texttt{crashes} \rightarrow \texttt{lga\_yearly\_summary}$$

so there is only one valid order. Models with no path between them can be built in parallel (the profile allows 4 threads).

**Tests as sets.** Write a test $t$ on model $m$ as a query returning the set of violating rows $V_t(m)$. Then

$$\text{pass}(t) \iff |V_t(m)| = 0$$

For example, `unique` on `accident_no` is the query `select accident_no from crashes group by 1 having count(*) > 1`, and passes when it returns nothing. `dbt build` runs each model, then its tests, and skips anything downstream of a failure, so a bad staging model never reaches the marts.

## Toy implementation

A miniature dbt in about 40 lines: models with `ref()`, a topological sort, and tests that pass when they return no rows. It uses four made-up crashes, including the council rename from this project.

```python
import re
from graphlib import TopologicalSorter

import duckdb

con = duckdb.connect()
con.execute("""
    create table raw_crashes as select * from (values
        ('A1', '2023-05-01', 'MORELAND', '0'),
        ('A2', '2024-02-11', 'MERRI-BEK', '1'),
        ('A3', '2024-07-30', 'MORELAND', '0'),
        ('A4', '2024-09-02', 'HUME', '2')
    ) as t(accident_no, accident_date, lga_name, fatality)
""")

models = {
    "stg_crashes": """
        select accident_no,
               cast(accident_date as date) as accident_date,
               case lga_name when 'MORELAND' then 'MERRI-BEK' else lga_name end as lga_name,
               cast(fatality as integer) as persons_killed
        from raw_crashes
    """,
    "lga_yearly": """
        select lga_name, year(accident_date) as accident_year, count(*) as crashes,
               sum(persons_killed) as persons_killed
        from {{ ref('stg_crashes') }}
        group by all
    """,
}

# A test is a query that returns the rows that break a rule. Zero rows means it passes.
tests = {
    "unique_accident_no": "select accident_no from stg_crashes group by 1 having count(*) > 1",
    "no_renamed_councils": "select * from stg_crashes where lga_name = 'MORELAND'",
    "one_row_per_lga_year": """select lga_name, accident_year from lga_yearly
                               group by all having count(*) > 1""",
}

REF = re.compile(r"\{\{\s*ref\('(\w+)'\)\s*\}\}")
graph = {name: set(REF.findall(sql)) for name, sql in models.items()}

for name in TopologicalSorter(graph).static_order():
    sql = REF.sub(lambda m: m.group(1), models[name])
    con.execute(f"create or replace table {name} as {sql}")
    print(f"built {name}")

for name, sql in tests.items():
    failures = con.execute(sql).fetchall()
    print(f"{'PASS' if not failures else 'FAIL'} {name}")

print(con.execute("select * from lga_yearly order by all").fetchall())
```

```text
built stg_crashes
built lga_yearly
PASS unique_accident_no
PASS no_renamed_councils
PASS one_row_per_lga_year
[('HUME', 2024, 1, 2), ('MERRI-BEK', 2023, 1, 0), ('MERRI-BEK', 2024, 2, 1)]
```

Delete the `case lga_name ...` line and `no_renamed_councils` fails, and the summary splits one council into two. Real dbt adds much more on top (Jinja templating, materialisations, incremental models, packages, docs, selectors), but this is the core idea.

## In this project

**The layers.**

| Layer | Model | Materialised as | What it does |
|---|---|---|---|
| Source | `raw.crashes` | table, loaded by `crashsql load` | The CSV exactly as published: 202,554 rows, 52 text columns. Declared in `dbt/models/staging/_sources.yml`. |
| Staging | `staging.stg_crashes` | view | Casts dates, times and counts. Turns `'Unk.'` into `'Unknown'`. Parses `speed_zone` (`'60 km/hr'`, and the odd `'30km/hr'` without a space) into `speed_limit_kmh`, leaving `'Not known'` and `'Other speed limit'` as null. Merges Moreland into Merri-bek. |
| Mart | `marts.crashes` | table | One row per crash, 46 columns with readable names (`persons_killed`, not `fatality`), and derived flags: `is_fatal`, `is_weekend`, `is_complete_year`. |
| Mart | `marts.lga_yearly_summary` | table | Crash and casualty totals per council per year, for council-level questions. |

`dbt_project.yml` sets staging to views (cheap, always current) and marts to tables (fast for the agent). The `generate_schema_name` macro keeps the schema names as plain `staging` and `marts`; by default dbt would prefix them with the target schema (`main_marts`).

**The renamed council.** Moreland City Council was renamed Merri-bek in 2022. The source records both names, even within the same year:

| Year | `MORELAND` | `MERRI-BEK` |
|---|---|---|
| 2022 | 427 | 3 |
| 2023 | 444 | 14 |
| 2024 | 276 | 166 |
| 2025 | 208 | 232 |

On the raw data, "Which council had the largest increase in crashes from 2023 to 2024?" returns **MERRI-BEK, +152** (166 minus 14). That is not a real increase: the same council's crashes were moving from one label to the other, and merged it actually went *down* (458 to 442). The correct answer is **HUME, +59**. The fix is one `case` expression in `stg_crashes.sql`, and `dbt/tests/no_renamed_councils.sql` fails the build if `MORELAND` ever appears in the marts again. Evaluation question q18 exists to check that the agent gets the corrected answer.

**The partial year.** The data runs to 28 March 2026, so 2026 has only 249 crashes. "Which year had the fewest crashes?" naively returns 2026. The `is_complete_year` flag in `marts.crashes` lets the agent exclude it; the right answer is **2020**, with 12,170 crashes, the year of the COVID-19 lockdowns. Question q15 checks this.

**The tests.** `dbt build` runs 3 models and 11 tests, 14 steps in all:

- Generic tests in YAML: `unique` and `not_null` on `accident_no`, `not_null` on `accident_date` (in both staging and marts), `accepted_values` on `severity`, `not_null` on `lga_name`.
- `unique_combination` on (`lga_name`, `accident_year`) in the summary table. It is a custom generic test in `dbt/macros/test_unique_combination.sql`, equivalent to `dbt_utils.unique_combination_of_columns` without adding a package.
- Two singular tests in `dbt/tests/`: `no_renamed_councils.sql` and `fatal_crashes_have_deaths.sql`. The second checks that a crash is fatal exactly when at least one person was killed, which ties the `severity` label to the counts.

**Docs the agent reads.** `+persist_docs` in `dbt_project.yml` writes every description in `_marts.yml` into DuckDB as a table or column comment. For example, the comment on `is_complete_year` reads *"False for the latest year in the data, which is only partly reported."* The agent's `describe_table` tool returns these comments, so writing good dbt docs directly improves the agent's answers (chapter 4).

**Same models, other warehouses.** `dbt/profiles.yml` has a `duckdb` target (the default) and a `snowflake` target. CI runs `dbt build` on a 1,000-row sample on every push, so a broken model or failing test blocks the merge.

## Failure modes

- **Cleaning in the loader.** Fixes made in Python before loading are invisible to anyone reading the dbt project, and untested. Load raw, clean in staging.
- **Silent label changes.** Renamed councils, new category labels, changed spellings. Nothing errors; the numbers just drift. `accepted_values` and targeted singular tests catch the cases you know about. Profiling categorical columns by year catches the ones you don't.
- **Tests only check what you wrote.** Passing tests mean the rules you thought of hold, not that the data is right. The Moreland problem was found by a surprising query result, and only then turned into a test.
- **Logic in the marts that belongs in staging.** If two marts each fix the same label, they will eventually disagree. Fix things once, as early as possible.
- **Hard-coded table names.** Writing `from staging.stg_crashes` instead of `{{ ref('stg_crashes') }}` hides the dependency from dbt. Models build in the wrong order, and switching targets breaks.
- **Undocumented columns.** For a human, a missing description is an inconvenience. For an agent, it is a guess: without the `is_complete_year` description, a model has no reason to exclude 2026.
- **Views over heavy logic.** A view re-runs its query every time it is used. That is fine for a light staging step; marts that the agent queries repeatedly should be tables.

## Self-test

1. What is the difference between ETL and ELT, and which one does this project use?
2. Why write `{{ ref('stg_crashes') }}` instead of `staging.stg_crashes`?
3. A test query returns 3 rows. Did the test pass?
4. On the raw data, Merri-bek shows +152 crashes from 2023 to 2024. What is the real change for that council, and why did the raw data mislead?
5. Why is `is_complete_year` a column in the mart instead of something the agent works out?
6. What does `persist_docs` do, and why does it matter for this agent?
7. Write a singular test that fails if any crash has `persons_killed` greater than `persons_involved`.

<details>
<summary>Answers</summary>

1. ETL transforms data before loading it; ELT loads it raw and transforms it inside the warehouse with SQL. This project uses ELT: `crashsql load` copies the CSV into `raw.crashes` unchanged, and dbt does all the cleaning.
2. `ref()` tells dbt about the dependency, so models are built in the right order and the same SQL works when dbt changes the schema or the warehouse (for example, the Snowflake target).
3. No. A test returns the rows that break the rule, so 3 rows means 3 violations.
4. Merged, the council went from 458 crashes (444 + 14) to 442 (276 + 166), a fall of 16. The raw data recorded the council under two names, and most of its crashes moved from `MORELAND` to `MERRI-BEK` during 2024, which looked like a jump.
5. The latest year being partial is a fact about the data, not about any one question. Computing it once in the mart, with a description, makes every query (from the agent or a person) consistent, and the agent can read the description.
6. It writes the model and column descriptions from the YAML files into the database as comments. The agent's `describe_table` tool reads those comments, so the documentation is part of what the agent knows about each column.
7. For example, `dbt/tests/killed_within_involved.sql`:

    ```sql
    select accident_no, persons_killed, persons_involved
    from {{ ref('crashes') }}
    where persons_killed > persons_involved
    ```

</details>
