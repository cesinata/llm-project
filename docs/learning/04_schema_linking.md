# 4. Schema linking

**Schema linking** is the step where the model connects words in the question to tables, columns and values in the database: "council" to `lga_name`, "killed" to `persons_killed`, "pedestrians being struck" to `accident_type = 'Struck Pedestrian'`. Most text-to-SQL mistakes in this project are linking mistakes, not SQL syntax errors.

## Intuition

- A model can write perfect SQL against the wrong column. `road_type = 'FREEWAY'` is valid SQL. It is still the wrong answer to "crashes on freeways" if the gold meaning is `road_class = 'Freeway'`.
- Linking has three layers: which table, which column, and which exact value. Text filters are case-sensitive in this warehouse (`'Struck Pedestrian'`, `'MELBOURNE'`).
- Putting the whole schema in one prompt does not scale well and still leaves the value problem. Better: let the agent ask for tables and columns, and show the exact labels of low-cardinality text columns.

## The math

Treat linking as retrieval over a small catalogue of columns. Each column $c$ has a text bag $D_c$ made from its name, type and description. A question $q$ has token bag $T_q$. A simple score is overlap:

$$\mathrm{score}(q, c) = |T_q \cap D_c|$$

That score is only a toy. Real models use embeddings or the full prompt. What matters for cost is schema size. If each column description is about $t$ tokens and there are $C$ columns, dumping every description into every turn costs about $C \cdot t$ tokens before the question is even asked. This warehouse's `marts.crashes` has 46 columns; listing every distinct `road_name` (about 14,500 values) would blow the context. That is why sample values are only returned for low-cardinality text columns.

## Toy implementation

A keyword-overlap linker over a few of this project's columns:

```python
import re

docs = {
    "road_class": "Road management class, e.g. Freeway, Arterial Highway, Local Road.",
    "road_type": "Road type, upper case, e.g. ROAD, STREET, HIGHWAY, FREEWAY.",
    "persons_killed": "Number of people killed.",
    "motorcycles": "Number of motorcycles involved.",
    "motorcyclists": "Number of motorcycle riders involved.",
}


def tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


question = "How many crashes on freeways in 2025 involved at least one heavy vehicle?"
q = tokens(question)
ranked = sorted(
    ((len(q & tokens(f"{name} {doc}")), name) for name, doc in docs.items()),
    reverse=True,
)
print(ranked[:3])
```

On this question both `road_class` and `road_type` score highly because each description contains a freeway-like word. Overlap cannot decide between them. That is exactly the ambiguity behind evaluation question q11.

## In this project

`DuckDBDatabase.describe_table` in `src/crashsql/db.py` returns each column's name, type and dbt description (written into DuckDB comments by `+persist_docs`). For `VARCHAR` columns it also returns up to 30 distinct values; if there are more than 30 it returns none, so high-cardinality fields such as `road_name` are not dumped into the prompt.

| Column | Distinct values | Why it matters |
|---|---|---|
| `accident_type` | 9 | Exact label is `'Struck Pedestrian'` (capital P). |
| `day_of_week` | 7 | Safe to list in full. |
| `lga_name` | 86 | Too many for the sample-value path (limit 30), so the model must rely on the description and common names such as `'MELBOURNE'`. |
| `road_name` | ~14,500 | Never listed; filters need care. |
| `road_class` vs `road_type` | 6 vs many | Both look like "freeway". Gold for q11 uses `road_class = 'Freeway'` (184 crashes with a heavy vehicle in 2025). `road_type = 'FREEWAY'` returns 108. |
| `motorcycles` vs `motorcyclists` | counts | Vehicles vs people. Same trap as crashes vs `persons_killed`. |

The system prompt tells the model to use the exact labels from `describe_table`, to count rows for crashes and `persons_*` for people, and to decline when the data cannot answer.

## Failure modes

- **Near-duplicate columns.** Freeway, motorcycle, injury severity: two columns, one question word.
- **Case and spelling.** `'Struck Pedestrian'` vs `'struck pedestrian'`; `'Unk.'` was normalised in staging to `'Unknown'`.
- **High-cardinality text.** Values cannot be listed; the model invents a plausible label.
- **Stale docs.** If a description says the wrong thing, the agent learns the wrong thing. Persisted dbt docs are part of the product.
- **Over-trusting the prompt.** Rules help, but the schema the tools return is what the model actually sees each turn.

## Self-test

1. Why can valid SQL still be a wrong answer for this task?
2. Why does `describe_table` refuse to list values when a text column has more than 30 distinct entries?
3. For "people killed", which column should be used, and what goes wrong if you count fatal crash rows instead?
4. Why did some models score 108 freeway crashes with a heavy vehicle in 2025 instead of 184?

<details>
<summary>Answers</summary>

1. Because the query can target the wrong table, column or literal while still running.
2. Those lists would flood the context and are usually not useful as a complete enum (for example road names).
3. `persons_killed` (or a sum of it). Counting fatal rows under-counts when one crash kills several people.
4. They filtered `road_type = 'FREEWAY'` instead of `road_class = 'Freeway'`.

</details>
