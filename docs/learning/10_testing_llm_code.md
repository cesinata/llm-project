# 10. Testing LLM code

Language model output changes from run to run, and calling a real model in tests is slow, costs money and needs a key. Most of an agent can still be tested the normal way.

## Intuition

- Split the system into deterministic pieces and a non-deterministic piece.
- Deterministic: SQL guardrails, result matching, dbt tests, the agent's control flow with a fake model.
- Non-deterministic: the live model. Measure that with the evaluation set, not with flaky unit tests.
- CI should run without secrets and without the network.

## The math

None required. The practical point is variance: if a test calls a live model, the same assertion can pass on Tuesday and fail on Wednesday with no code change. That makes the suite a poor regression signal. Keep live calls in evaluation jobs you choose to run, not in the default PR check.

## Toy implementation

A scripted model driving the agent loop (same idea as `tests/test_agent.py`):

```python
from types import SimpleNamespace
import json


def tool_call(name, i, **args):
    return SimpleNamespace(
        id=f"call_{i}",
        function=SimpleNamespace(name=name, arguments=json.dumps(args)),
    )


class ScriptedLLM:
    model = "scripted"

    def __init__(self, turns):
        self.turns = list(turns)

    def chat(self, messages, tools):
        content, calls = self.turns.pop(0)
        return SimpleNamespace(
            message=SimpleNamespace(content=content, tool_calls=calls),
            prompt_tokens=10,
            completion_tokens=5,
        )


# Sequence: bad SQL, then repaired SQL, then final_answer.
turns = [
    (None, [tool_call("run_sql", 1, sql="select count(*) from crash")]),
    (None, [tool_call("run_sql", 2, sql="select count(*) from crashes")]),
    (None, [tool_call("final_answer", 3, sql="select count(*) from crashes", answer="202554")]),
]
```

Wire that object in place of `LLMClient.from_env()` and assert on `result.ok`, `result.sql_errors`, and the tool messages the fake model saw.

## In this project

The suite collects **39** tests with no API key:

| File | What it covers |
|---|---|
| `tests/test_db.py` | Guardrails, locked settings, docs/labels on describe, council rename |
| `tests/test_evaluate.py` | Matcher rules, question file, gold SQL, `--resume` |
| `tests/test_agent.py` | Happy path, unsafe SQL, empty reply → JSON nudge, malformed tools, max steps, provider errors |
| `tests/test_streamlit_app.py` | Demo UI with the scripted model: answer, example button, session limit |

`.github/workflows/ci.yml` runs ruff, `crashsql load --sample`, `crashsql build`, `crashsql eval --gold-only`, then pytest. The sample warehouse keeps CI fast and offline.

## Failure modes

- A fake model that always behaves; real models will not.
- Snapshot tests on English wording from a live model.
- CI that needs provider secrets to go green.
- Skipping dbt data tests because unit tests passed.
- Asserting on exact SQL strings instead of behaviour (result rows, error types, control flow).

## Self-test

1. What belongs in pytest here, and what belongs in `crashsql eval`?
2. Why does CI use `--sample`?
3. How do you test "the agent retries after a SQL error" without Groq?
4. Why is gold-only evaluation part of CI?

<details>
<summary>Answers</summary>

1. Pytest: deterministic code and scripted control flow. Eval: live model quality on the gold set.
2. So the warehouse builds quickly without downloading the full CSV or needing network access in the critical path beyond what the workflow already allows.
3. Script a fake model that returns a bad `run_sql`, then a good one, then `final_answer`, and assert `sql_errors >= 1` and a correct final result.
4. To catch broken or drifting gold SQL before a model run wastes time or looks unfairly bad.

</details>
