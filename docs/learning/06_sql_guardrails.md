# 6. SQL guardrails

!!! note "Coming soon"
    This chapter is planned but not written yet. The outline below is what it will cover.

The agent runs SQL written by a language model. Treat that SQL like input from a stranger: it may be wrong, slow, or harmful, by accident or because a question was crafted to make it so (prompt injection).

## What it will cover

- **Intuition:** defence in depth. No single check is trusted alone; the database connection itself is the last line.
- **The math:** little. A short note on why string checks (`"DROP" in sql`) are unreliable, and why parsing is needed.
- **Toy implementation:** a guard that parses SQL and rejects anything that is not exactly one SELECT, then tries to bypass it.
- **In this project:**
    - `check_read_only` in `src/crashsql/db.py`: uses DuckDB's own parser (`duckdb.extract_statements`) to allow exactly one SELECT (or `WITH ... SELECT`).
    - The connection: `read_only=True`, `enable_external_access = false` so a SELECT cannot call `read_csv('/etc/passwd')` or fetch a URL, `autoload_known_extensions = false`, and `lock_configuration = true` so the model cannot switch them back on.
    - The 20-second timeout, enforced with `connection.interrupt()`.
    - Result limits: at most 30 rows go back to the model.
    - The tests in `tests/test_db.py` that try writes such as `DROP`, file and URL reads, and switching the locked settings back on, and check that each is blocked.
- **Failure modes:** keyword blocklists, trusting the prompt ("only write SELECT") as a control, leaking data through error messages, unbounded queries, giving the agent a connection with more rights than it needs.
- **Self-test.**
