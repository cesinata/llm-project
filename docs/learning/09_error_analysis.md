# 9. Error analysis

!!! note "Coming soon"
    This chapter is planned but not written yet. The outline below is what it will cover.

A score says how often the agent is wrong. Error analysis says why, and which fix is worth making next.

## What it will cover

- **Intuition:** read every wrong answer, sort the mistakes into categories, and fix the biggest category first.
- **The math:** a simple error taxonomy with counts, and the expected gain from fixing one category.
- **Toy implementation:** load an evaluation results file and group the wrong answers by cause.
- **In this project:** the real problems found while building it, and what each fix was.

    | Problem | How it showed up | Fix |
    |---|---|---|
    | Moreland renamed Merri-bek | q18 answered MERRI-BEK +152 instead of HUME +59 | Merge in `stg_crashes`, plus a dbt test |
    | `gpt-oss-120b` stopped after `run_sql` with an empty reply | Near-zero score though most of its SQL was right | One follow-up request without tools, asking for `{"sql", "answer"}` as JSON |
    | Forcing `final_answer` with `tool_choice` | Groq rejected requests: "tool call validation failed" | Send that error back to the model instead of ending the question |
    | `qwen2.5-coder:7b` wrote tool calls as plain text | No tools were ever called | Use `qwen2.5:7b` (the instruct model) |
    | Free-tier token limit hit mid-run | Questions failed with rate-limit errors | Record provider errors separately and add `eval --resume` |
    | Wrong column with a similar meaning | q11 used `road_type` instead of `road_class` | To be decided after the full runs (chapter 4) |

- **Failure modes:** fixing the prompt for one question and breaking others, labelling errors from the final answer only (read the whole trace), treating a provider error as a model error.
- **Self-test.**
