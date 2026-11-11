# Optional: Snowflake as a second warehouse

!!! note "Coming soon"
    This page is planned but not written yet. The outline below is what it will cover.

The same dbt models, run on Snowflake instead of DuckDB, using Snowflake's free 30-day trial. This page is optional: nothing else in the project depends on it.

## What it will cover

- **Intuition:** what changes when moving from an in-process database to a cloud warehouse: separate storage and compute, virtual warehouses billed by the second, roles and access control, many users at once.
- **The math:** a rough cost model, credits per hour times hours a warehouse is running, and why auto-suspend matters.
- **Toy implementation:** loading `raw.crashes` into Snowflake and running `crashsql build --target snowflake`.
- **In this project:**
    - The `snowflake` target in `dbt/profiles.yml`, configured through environment variables, and the optional `pip install -e ".[snowflake]"` dependency.
    - Which models and tests ran unchanged, and which needed changes for Snowflake's SQL dialect.
    - Adding a `SnowflakeDatabase` class behind the `Database` protocol so the agent can query Snowflake too.
- **Failure modes:** leaving a warehouse running, upper-case identifiers, roles with too many rights for an agent, trial expiry.
- **Self-test.**
