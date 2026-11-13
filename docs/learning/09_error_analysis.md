# 9. Error analysis

A score says how often the agent is wrong. Error analysis says why, and which fix is worth making next.

## Intuition

- Read the wrong answers, including the SQL and the tool trace, not only the final sentence.
- Group mistakes into a short taxonomy. Fix the largest group first.
- Separate data bugs, agent-loop bugs, linking bugs and provider limits. They need different fixes.

## The math

Suppose category $i$ causes $k_i$ of the $K$ wrong answers on a set of size $N$. If a fix removes that category completely, accuracy rises by about $k_i / N$. That is an upper bound: fixes are rarely perfect, and a prompt change can create new errors. Still, ranking categories by $k_i$ beats fixing whichever failure you looked at last.

## Toy implementation

Group failures from a results JSONL by a few hand rules:

```python
import json
from collections import Counter
from pathlib import Path


def category(row: dict) -> str:
    if row.get("provider_error"):
        return "provider"
    sql = (row.get("sql") or "").lower()
    if row.get("correct"):
        return "ok"
    if "road_type" in sql and "freeway" in sql:
        return "schema_link_freeway"
    if "is_complete_year" in sql:
        return "partial_year_overapplied"
    if sql.strip().startswith("select null"):
        return "refusal_as_select"
    if not sql:
        return "no_sql"
    return "other"


path = Path("evals/results")  # point at one .jsonl when you have it
counts = Counter()
for file in path.glob("*.jsonl"):
    for line in file.read_text().splitlines():
        counts[category(json.loads(line))] += 1
print(counts.most_common())
```

## In this project

Problems found while building and evaluating, and what changed:

| Problem | How it showed up | Fix |
|---|---|---|
| Moreland renamed Merri-bek | q18 answered MERRI-BEK +152 instead of HUME +59 | Merge in `stg_crashes`, plus `no_renamed_councils` |
| `gpt-oss` stopped after `run_sql` | Near-zero score though SQL was often right | JSON `{"sql","answer"}` follow-up without tools |
| Forcing `final_answer` with `tool_choice` | Groq: tool call validation failed | Return the error to the model |
| `qwen2.5-coder:7b` wrote tools as text | No structured tool calls | Default to `qwen2.5:7b` instruct |
| Free-tier limits mid-run | Rate limit / request too large | `provider_error` + `eval --resume` |
| Freeway column mix-up | q11: 108 vs 184 | Documented; prompt/schema-doc follow-up |
| Partial-year rule over-applied | Totals and year lists dropped valid years | Documented; prompt tightening planned |
| Motorcycle riders vs motorcycles | Third DCA count 180 vs 182 | Documented linking trap |
| Refusal wrapped as `SELECT NULL` | Unanswerable marked wrong | Documented; scorer/agent follow-up |

The first five rows are already fixed in code or process. The linking and refusal rows are the main open product improvements after the baseline table.

## Failure modes

- Labelling from the final sentence only, without reading the SQL.
- Treating a 429 as "the model cannot refuse".
- Changing the prompt for one question and breaking five others.
- Mixing warehouse bugs with model bugs in the same bucket.

## Self-test

1. Why did a Moreland/Merri-bek bug look like a model error at first?
2. Why record provider errors separately?
3. If 5 of 22 failures are the same linking mistake, how many accuracy points might fixing it be worth?
4. Why is "read the trace" part of error analysis?

<details>
<summary>Answers</summary>

1. The gold answer was wrong until the staging model merged the council names; models were scored against a bad target.
2. So resume and reporting do not punish the model for quota or HTTP failures.
3. About $5/22 \approx 23$ points in the ideal case, before side effects.
4. Because the failure often happens earlier (wrong describe, wrong repair, never calling `final_answer`) than the final sentence shows.

</details>
