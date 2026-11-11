# 4. Schema linking

!!! note "Coming soon"
    This chapter is planned but not written yet. The outline below is what it will cover.

**Schema linking** is the step where the model connects words in the question to tables, columns and values in the database: "council" to `lga_name`, "killed" to `persons_killed`, "pedestrians being struck" to `accident_type = 'Struck Pedestrian'`. Most text-to-SQL errors are linking errors, not SQL syntax errors.

## What it will cover

- **Intuition:** why a model that writes perfect SQL still gets answers wrong, and the three things it has to link (tables, columns, exact values).
- **The math:** linking as a retrieval problem, and a simple measure of schema size against the model's context window (tokens per column description).
- **Toy implementation:** a keyword-overlap linker that ranks columns for a question, and where it breaks.
- **In this project:**
    - `describe_table` in `src/crashsql/db.py` returns each column's type and its dbt description, plus the exact distinct values of text columns with 30 values or fewer.
    - Why the sample values matter: `'Struck Pedestrian'` (capital P), `'MELBOURNE'` (upper case), `'Dark Street lights on'`.
    - The q11 mistake from chapter 1: `road_type = 'FREEWAY'` instead of `road_class = 'Freeway'`, and how better column descriptions could prevent it.
    - Crashes vs people: the `persons_*` description and the system prompt rule.
- **Failure modes:** near-duplicate columns, case-sensitive labels, high-cardinality columns that cannot be listed (`road_name`), stale descriptions.
- **Self-test.**
