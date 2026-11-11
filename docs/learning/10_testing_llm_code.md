# 10. Testing LLM code

!!! note "Coming soon"
    This chapter is planned but not written yet. The outline below is what it will cover.

Language model output changes from run to run, and calling a real model in tests is slow, costs money and needs a key. Most of an agent can still be tested the normal way.

## What it will cover

- **Intuition:** separate what is deterministic (the database layer, the guardrails, the scorer, the agent's control flow) from what is not (the model). Test the first with ordinary unit tests, and test the second with the evaluation set.
- **The math:** none needed. A short note on why tests that call a real model are flaky.
- **Toy implementation:** a scripted fake model that returns a fixed sequence of tool calls, driving the agent through a full question.
- **In this project:**
    - The 36 pytest tests in `tests/`, which need no network or API key.
    - `tests/test_agent.py`: the fake model covers the normal path, SQL errors and retries, a model that stops without `final_answer`, answers typed as JSON, and malformed tool calls.
    - `tests/test_db.py`: the guardrails from chapter 6.
    - `tests/test_evaluate.py`: the matching rules from chapter 1 (extra columns, column order, rounding, row order), the question file, and `--resume`.
    - The GitHub Actions workflow in `.github/workflows/ci.yml`: lint with ruff, build the sample warehouse with dbt (models and data tests), check every gold query runs, then run pytest.
- **Failure modes:** tests that pass because the fake model is too polite, snapshot tests on model wording, CI that needs secrets, skipping data tests because the unit tests pass.
- **Self-test.**
