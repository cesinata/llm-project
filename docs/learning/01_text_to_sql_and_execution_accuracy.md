# 1. Text-to-SQL and execution accuracy

Before building the agent, be able to say exactly when an answer counts as correct. Every number later in this project, from the results table to the error analysis, is built on the definition in this chapter.

## The task in one paragraph

Given a question in plain English, such as *"How many people were killed in road crashes in Victoria in 2024?"*, the agent writes one SQL query against the `marts` schema, runs it, and replies with the query and a one-sentence answer. Some questions cannot be answered from the data (there is no blood alcohol column, and there are no New South Wales crashes); for those, the right reply is no query at all. This task is called **text-to-SQL**, or semantic parsing into SQL. The public benchmarks for it are [Spider](https://yale-lily.github.io/spider) and [BIRD](https://bird-bench.github.io/).

## Intuition

- **The SQL text is the wrong thing to compare.** `select count(*) from crashes` and `SELECT COUNT(1) AS total FROM crashes;` are different strings that mean the same thing. Comparing strings (*exact match*) marks good answers wrong.
- **Compare what the query returns.** Run the gold query and the predicted query, and check that the results hold the same data. This is **execution accuracy**, the headline metric on Spider and BIRD.
- **Decide what "the same data" means.** Column names are the model's choice, so ignore them. Column order rarely matters. A model that adds a helpful extra column (the council *and* its crash count) should not be punished. Row order matters only when the question asks for it ("in year order", "most common first").
- **Numbers need a tolerance.** `22.06` and `22.1` should match when the question asks for one decimal place.
- **Refusing is an answer.** On an unanswerable question, any query is wrong, and so is answering "0".

## The math

Treat a query result as a list of rows, each row a tuple of values. Let $G$ be the gold result with $n$ rows and $k$ columns, and $P$ the predicted result with $n'$ rows and $k'$ columns.

**Normalise each value.** Numbers are rounded to one decimal place, dates become ISO strings, text is trimmed:

$$\nu(v) = \begin{cases} \text{round}(v, 1) & v \text{ is a number} \\ \text{isoformat}(v) & v \text{ is a date or time} \\ \text{trim}(v) & \text{otherwise} \end{cases}$$

**Pick predicted columns.** A column mapping $\sigma$ sends each gold column $i \in \{1..k\}$ to a *different* predicted column $\sigma(i) \in \{1..k'\}$. That requires $k' \ge k$; extra predicted columns are simply not picked. Projecting $P$ through $\sigma$ gives $P_\sigma$, which has the same shape as $G$.

**Compare.** When row order does not matter, compare *multisets* (bags) of rows, written $\{\!\{\cdot\}\!\}$, so duplicates count:

$$\text{match}(G, P) = \big[\, n = n' \,\big] \wedge \exists\, \sigma : \begin{cases} \nu(G) = \nu(P_\sigma) & \text{order matters (lists)} \\ \{\!\{\nu(G)\}\!\} = \{\!\{\nu(P_\sigma)\}\!\} & \text{otherwise (multisets)} \end{cases}$$

**Unanswerable questions** have no gold query. The answer is correct only when the model returns no query: $\text{match} = [\, P = \varnothing \,]$.

**Execution accuracy** over $N$ questions is the share that match:

$$\text{EA} = \frac{1}{N} \sum_{q=1}^{N} \text{match}(G_q, P_q)$$

**How much to trust it.** With $N = 22$ questions, EA is a proportion estimated from a small sample. Its standard error is about $\sqrt{\text{EA}(1-\text{EA})/N}$. At EA = 0.5 that is $\sqrt{0.25/22} \approx 0.107$, so a 95% interval is roughly $\pm 0.21$. Two models scoring 0.55 and 0.68 are not clearly different on this set. Chapter 8 covers comparing models properly.

Worked example: the gold result for "Which council area had the most crashes overall?" is one row, one column: `(MELBOURNE)`. A prediction of `(10456, MELBOURNE)` has $n' = 1 = n$ and $k' = 2 \ge 1$. The mapping $\sigma(1) = 2$ picks the council column, the projected bag is $\{\!\{(\text{MELBOURNE})\}\!\}$, and it matches.

## Toy implementation

A small version of the matcher. It tries every way of picking $k$ predicted columns (the project's version narrows the candidates first, which is faster).

```python
from collections import Counter
from itertools import permutations


def norm(v):
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return round(float(v), 1) + 0.0
    return v


def match(gold, pred, order_matters=False):
    gold = [tuple(norm(v) for v in r) for r in gold]
    pred = [tuple(norm(v) for v in r) for r in pred]
    if len(gold) != len(pred):
        return False
    if not gold:
        return True
    k = len(gold[0])
    # Try every way of picking k predicted columns, in some order.
    for cols in permutations(range(len(pred[0])), k):
        projected = [tuple(r[j] for j in cols) for r in pred]
        if order_matters and projected == gold:
            return True
        if not order_matters and Counter(projected) == Counter(gold):
            return True
    return False


gold = [("MELBOURNE",)]
print(match(gold, [("MELBOURNE",)]))                 # True: same answer
print(match(gold, [("MELBOURNE", 10456)]))           # True: extra column allowed
print(match(gold, [(10456, "MELBOURNE")]))           # True: column order ignored
print(match(gold, [("CASEY",)]))                     # False: wrong council
print(match([(22.1,)], [(22.06,)]))                  # True: rounded to 1 dp
print(match([(2015,), (2016,)], [(2016,), (2015,)], order_matters=True))  # False
```

The `+ 0.0` turns `-0.0` into `0.0`, which would otherwise print differently and confuse debugging (they already compare equal).

## In this project

- `results_match` in `src/crashsql/evaluate.py` implements the definition above. Instead of trying every permutation, it first lists, for each gold column, the predicted columns with the same values, then only tries mappings built from those candidates.
- Each question in `evals/questions.yaml` has a `gold_sql`, a `difficulty` and, where the question asks for an order, `order_matters: true`. The two unanswerable questions have `gold_sql: null`.
- Gold queries return only the columns the question asks for. That is what makes "extra columns are allowed" safe to apply.
- CI runs `crashsql eval --gold-only` on every push, which checks that every gold query still runs against the sample warehouse.

From the first partial run of `openai/gpt-oss-20b` (13 questions answered before the free-tier token limit), here is how the rules played out on real answers:

| Question | Model's query did | Scored | Why |
|---|---|---|---|
| q01 total crashes | `COUNT(*) AS total_crashes` | correct | Column names are ignored. |
| q04 council with most crashes | Used `lga_yearly_summary`, excluded the partial year, returned `MELBOURNE, 10449` | correct | Gold returns only the name; the extra count column was not compared. The count differs from the true total of 10,456 because of the partial-year filter. |
| q06, q10, q12 | Added `is_complete_year = true` though the question did not ask | correct | Dropping the 249 crashes of 2026 did not change the top day, the top hour, or the rounded averages. |
| q09 crashes per year, 2015 to 2025 | `BETWEEN 2015 AND 2024` | wrong | 10 rows instead of 11, so $n \ne n'$. |
| q11 freeway crashes with a heavy vehicle in 2025 | Filtered `road_type = 'FREEWAY'` instead of `road_class = 'Freeway'` | wrong | 108 instead of 184. A plausible but different column. |

On those 13 answers, 11 were correct. The q04 row is the important one: execution accuracy said "correct" while one of the numbers in the model's sentence was off. That is a known weakness of the metric, listed below.

## Failure modes

- **Lenient matches (false positives).** Allowing extra columns means a wrong extra number goes unchecked, as in q04. Filters that happen not to change the result (q06, q10, q12) also pass. The metric checks the result, not the reasoning.
- **Coincidental matches.** A wrong query can return the right value by chance, especially for single numbers or `LIMIT 1`. More questions, and questions whose answers are hard to hit by accident, reduce this.
- **Strict mismatches (false negatives).** Ties break arbitrarily under `ORDER BY ... LIMIT`. In q07, Shepparton and Yarra Ranges tie on 39 deaths, so that question does not check row order. Ambiguous wording ("from 2015 to 2025": inclusive or not?) also produces honest disagreements. Write questions so only one reading is reasonable.
- **Rounding rules.** Rounding to one decimal place lets `22.06` match `22.1`, but also lets `22.14` match `22.1`. The tolerance must fit what the questions ask for.
- **Gold query bugs.** If the gold SQL is wrong, every model is scored against the wrong answer. The Moreland/Merri-bek rename (chapter 3) changed the gold answer to q18, which is why gold queries are re-run in CI and checked by hand.
- **Counting provider errors as model errors.** A rate-limited request is not a wrong answer. The evaluator records `provider_error` separately and `--resume` reruns only those questions, so the score reflects the model rather than the free tier.
- **Over-reading small differences.** With 22 questions, the 95% interval is about $\pm 0.2$. Report the number of questions next to every score.

## Self-test

1. Why is exact string match on SQL a poor metric for this task?
2. Gold returns `(2020)`. The prediction returns `(2020, 12170)`. Does it match? What if the prediction returns `(12170)`?
3. Gold returns two rows, `(Metro, 1.1)` and `(Country, 3.2)`. The prediction returns `(Country, 3.2)` and `(Metro, 1.1)`, and `order_matters` is false. Does it match? What changes if `order_matters` is true?
4. The model answers the NSW question with `select count(*) from crashes where region = 'NSW'`, which returns 0. Is that correct?
5. Two models score 12/22 and 14/22. Can you say the second is better?
6. Give one way execution accuracy can mark a wrong answer correct.

<details>
<summary>Answers</summary>

1. Many different SQL strings return the same result: different aliases, letter case, `COUNT(*)` vs `COUNT(1)`, a CTE vs a subquery. Exact match marks these correct answers wrong.
2. Yes, an extra column is allowed and the mapping picks the year column. `(12170)` does not match: the only column has the value 12170, not 2020.
3. Yes, as multisets the two results are equal. With `order_matters` true, the rows are compared as lists, and the order differs, so it does not match.
4. No. The question is unanswerable from this dataset, so any query is wrong. Answering "0" tells the user something false (that NSW had no crashes).
5. No. That is 0.55 against 0.64, a gap of about 0.09, well inside the roughly $\pm 0.2$ interval for 22 questions. You would need more questions or a paired test on the same questions (chapter 8).
6. Any of: an extra column holding a wrong number (q04); a filter that happens not to change the result (q06); a wrong query that returns the right single value by coincidence.

</details>
