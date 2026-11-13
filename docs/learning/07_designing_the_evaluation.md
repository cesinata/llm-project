# 7. Designing the evaluation

Chapter 1 defined how one answer is scored. This chapter is about choosing the questions. A small evaluation set only helps if each question can fail for a clear reason.

## Intuition

- An evaluation set is a list of hypotheses: "the model will confuse people with crashes", "it will miss the council rename", "it will invent a blood-alcohol column".
- Easy questions check that the plumbing works. Hard questions check the traps. Unanswerable questions check that the agent can refuse.
- If every question is a plain `COUNT(*)`, a weak model looks strong.

## The math

Execution accuracy on $N$ questions is a proportion $\hat p$. A rough standard error is:

$$\mathrm{SE}(\hat p) \approx \sqrt{\hat p(1-\hat p)/N}$$

For $\hat p = 0.82$ and $N = 22$, $\mathrm{SE} \approx 0.08$, so a 95% interval is about $\pm 0.16$. For $\hat p = 0.5$, it is about $\pm 0.21$. Gaps of a few points between models are noise on this set. Per-difficulty scores on 5 to 8 questions are even noisier; treat them as diagnostics, not league tables.

## Toy implementation

How often a 22-question set ranks two models the wrong way round when their true accuracies differ by 10 points:

```python
import random


def run(p, n=22):
    return sum(random.random() < p for _ in range(n))


wrong = 0
trials = 20_000
for _ in range(trials):
    a, b = run(0.80), run(0.70)
    if a < b:
        wrong += 1
print(f"P(weaker model looks better) ≈ {wrong / trials:.3f}")
```

The exact printout varies with the seed, but the probability is not small. That is why the README warns about the margin on 22 questions.

## In this project

`evals/questions.yaml` holds 22 gold items: 5 easy, 8 medium, 7 hard, 2 unanswerable.

| Id | Trap | What it tests |
|---|---|---|
| q02 | "people killed" | Sum `persons_killed`, do not count fatal rows |
| q05, q13 | Exact labels | `'Struck Pedestrian'`, `'MELBOURNE'` |
| q07 | Tie on deaths | Row order not checked when ranks tie |
| q09 | Year list | Inclusive years; `order_matters` |
| q15 | Fewest crashes | Exclude the partial latest year |
| q18 | Council rename | Moreland / Merri-bek merge |
| q21, q22 | Out of scope | Blood alcohol; New South Wales |

Gold SQL returns only the columns the question asks for, so extra predicted columns can be ignored by the matcher. Every gold query is re-run in CI with `crashsql eval --gold-only`. Per-question records are written as each question finishes. Provider errors (rate limits, overloaded APIs) are flagged separately, and `--resume` reruns only those.

## Failure modes

- Ambiguous questions with two fair SQL readings (freeway as `road_type` vs `road_class`).
- Gold answers that drift when the public CSV is refreshed.
- Tuning the prompt on the same 22 questions you report.
- Counting provider failures as model failures.
- Only one wording per skill, so a single unlucky parse sinks the score.

## Self-test

1. Why are unanswerable questions part of the set?
2. Roughly how wide is a 95% interval for 18/22?
3. Why does q07 turn off row-order checking?
4. What is the difference between a wrong answer and a `provider_error`?

<details>
<summary>Answers</summary>

1. To check that the agent can refuse instead of inventing a filter that returns 0.
2. About $\pm 0.16$ using the normal approximation above.
3. Two councils tie on deaths, so `ORDER BY ... LIMIT 5` row order is not unique.
4. A wrong answer is scored against gold. A provider error means the model never got a fair turn (quota, HTTP 429/503, and similar).

</details>
