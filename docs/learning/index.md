# Learning path

These chapters follow the project from the metric outwards: first what "correct" means, then the data layer, then the agent, then how it is evaluated and tested. Each one explains a concept, then shows where it appears in this repo with real numbers from the warehouse and the evaluation runs.

Every chapter uses the same layout:

1. **Intuition**: the idea in plain words.
2. **The math**: every symbol defined. Some chapters have little math; they keep the section short rather than invent some.
3. **Toy implementation**: small and runnable, using only the Python standard library and `duckdb`.
4. **In this project**: the code and the numbers.
5. **Failure modes**: how it goes wrong.
6. **Self-test**: questions, with answers hidden under a fold.

| # | Chapter | Where it lives in the repo | Status |
|---|---|---|---|
| 1 | [Text-to-SQL and execution accuracy](01_text_to_sql_and_execution_accuracy.md) | `src/crashsql/evaluate.py` | Written |
| 2 | [DuckDB and columnar analytics](02_duckdb_and_columnar_analytics.md) | `src/crashsql/data.py`, `src/crashsql/db.py` | Written |
| 3 | [dbt models, tests and docs](03_dbt_models_tests_and_docs.md) | `dbt/` | Written |
| 4 | [Schema linking](04_schema_linking.md) | `DuckDBDatabase.describe_table` | Coming soon |
| 5 | [Tool calling and the agent loop](05_tool_calling_and_the_agent_loop.md) | `src/crashsql/agent.py`, `src/crashsql/llm.py` | Coming soon |
| 6 | [SQL guardrails](06_sql_guardrails.md) | `check_read_only`, `DuckDBDatabase.__init__` | Coming soon |
| 7 | [Designing the evaluation](07_designing_the_evaluation.md) | `evals/questions.yaml` | Coming soon |
| 8 | [Comparing models](08_comparing_models.md) | `evals/results/`, README results table | Coming soon |
| 9 | [Error analysis](09_error_analysis.md) | evaluation records, `agent.py` fallbacks | Coming soon |
| 10 | [Testing LLM code](10_testing_llm_code.md) | `tests/`, `.github/workflows/ci.yml` | Coming soon |
| + | [Optional: Snowflake as a second warehouse](X1_optional_snowflake.md) | `dbt/profiles.yml` | Coming soon |

## Reading order

Read chapters 1 to 3 first. Chapter 1 defines what every later number means, and chapters 2 and 3 describe the data the agent works on. Chapters 4 to 6 cover the agent, chapters 7 to 10 cover evaluation and testing. The Snowflake page can be read at any point after chapter 3.
