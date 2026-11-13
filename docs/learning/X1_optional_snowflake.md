# Optional: Snowflake as a second warehouse

The same dbt models can run on Snowflake instead of DuckDB. This page is optional: the agent demo and local evaluation use DuckDB. Snowflake shows that the transform layer is not tied to one engine.

## Intuition

- DuckDB is in-process: one file, one writer, great for a laptop and CI.
- Snowflake separates storage and compute. Many users can query shared tables; warehouses start and stop independently.
- For a portfolio, the point is not to host the demo on Snowflake. The point is to prove the models and tests can target a cloud warehouse with credentials kept in environment variables.

## The math

Trial and paid accounts bill compute in credits. A simple planning model is:

$$\text{cost} \approx \text{credits per hour} \times \text{hours the warehouse is running}$$

Auto-suspend cuts the second term when nobody is querying. Leaving an X-Small warehouse awake overnight is how a free trial disappears without useful work. Load and build jobs should suspend the warehouse when finished.

## Toy implementation

Conceptually the port is three steps (details in `snowflake/setup.sql` and `dbt/profiles.yml`):

```text
1. Create CRASHSQL.RAW.CRASHES with all columns as text (same as DuckDB raw).
2. Load the DataVic CSV through an internal stage + COPY INTO.
3. crashsql build --target snowflake
   → staging view, marts tables, same 11 data tests.
```

No Snowflake account is required to read those files in the repo. The raw load in this project already reports **202,554** rows in Snowsight; staging and marts on Snowflake are the remaining build step.

## In this project

| Piece | Role |
|---|---|
| `dbt/profiles.yml` `snowflake` output | Account, host, user, key path or password, warehouse, database via env vars |
| `pip install -e ".[snowflake]"` | Adds `dbt-snowflake` |
| `snowflake/setup.sql` | Raw table, file format, stage, copy |
| `Database` protocol in `src/crashsql/db.py` | Agent talks to a protocol; a Snowflake client class can be added later without rewriting the loop |

Dialect differences still matter (identifier quoting, types). Keeping casts in staging SQL, with tests, is what makes the second target realistic.

## Failure modes

- Leaving a warehouse running.
- Putting account identifiers or keys in the README or in git.
- Password auth against MFA-enforced accounts without a key pair.
- Assuming every DuckDB-only function exists on Snowflake.
- Giving an agent role broader rights than SELECT on marts.

## Self-test

1. Why load raw columns as text on Snowflake too?
2. What does auto-suspend save?
3. Why are Snowflake credentials only in environment variables?
4. What still has to happen after the raw table shows 202,554 rows?

<details>
<summary>Answers</summary>

1. So casting stays visible in dbt and matches the DuckDB path.
2. Compute credits while idle.
3. So they are not committed or published with the portfolio.
4. `crashsql build --target snowflake` to create staging and marts and run the data tests.

</details>
