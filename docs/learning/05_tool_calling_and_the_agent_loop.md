# 5. Tool calling and the agent loop

The agent does not answer in one shot. It works in a loop: the model **reasons** about what it needs, **acts** by calling a tool, **observes** the result, and repeats until it calls `final_answer`. That pattern is often called ReAct (reason + act).

## Intuition

- Pasting the whole schema into one prompt wastes tokens and still leaves the model guessing labels.
- Letting it call `list_tables` and `describe_table` means it only pays for the tables it needs.
- Letting it call `run_sql` means a wrong query can be fixed from the error message, instead of ending the turn.
- The loop must stop. Without a step budget and a required final tool, a model can wander forever.

## The math

Write one question as a sequence of turns $t = 1, 2, \ldots$ with a hard budget $T$ (here $T = 12$). At turn $t$ the client sends the full conversation so far, so prompt size grows roughly with the sum of earlier tool outputs. If turn $i$ adds $m_i$ tokens, turn $t$ pays about $\sum_{i \le t} m_i$ input tokens. That is why average tokens per question in the evaluation sit around 8k to 12k even though the final SQL is short.

The action space is the four tools. A successful run ends when `final_answer` is called with either a SELECT or `sql = null` for an unanswerable question.

## Toy implementation

A tiny loop with a scripted model, no API key:

```python
from dataclasses import dataclass


@dataclass
class FakeModel:
    turns: list

    def chat(self, messages, tools):
        return self.turns.pop(0)


def run(question, model, tools_fn, max_steps=6):
    messages = [{"role": "user", "content": question}]
    for step in range(1, max_steps + 1):
        reply = model.chat(messages, tools=True)
        if reply["type"] == "final":
            return step, reply["answer"]
        name, args = reply["tool"], reply["args"]
        output = tools_fn(name, args)
        messages.append({"role": "assistant", "content": str(reply)})
        messages.append({"role": "tool", "content": output})
    return max_steps, "gave up"


def tools(name, args):
    if name == "run_sql":
        if "crash" == args.get("sql"):
            return "Catalog Error: table crash not found"
        return "rows: [(202554,)]"
    return "ok"


model = FakeModel(
    [
        {"type": "tool", "tool": "run_sql", "args": {"sql": "crash"}},
        {"type": "tool", "tool": "run_sql", "args": {"sql": "select count(*) from crashes"}},
        {"type": "final", "answer": "There are 202,554 crashes."},
    ]
)
print(run("How many crashes?", model, tools))
```

The first SQL fails, the error comes back as a tool result, and the scripted model repairs it. That is the same control flow as `tests/test_agent.py`.

## In this project

`src/crashsql/agent.py` defines four tools in the OpenAI tool-calling schema:

| Tool | Role |
|---|---|
| `list_tables` | Names, descriptions and row counts in `marts` |
| `describe_table` | Columns, docs and sample labels |
| `run_sql` | One SELECT, up to 30 preview rows |
| `final_answer` | The SQL to keep, plus a short English answer |

The system prompt sets the dialect, requires exact labels, distinguishes crashes from people, tells the model to exclude the partial latest year when comparing years, forbids invented numbers, and requires `sql = null` when the data cannot answer.

`src/crashsql/llm.py` is one OpenAI-compatible client used for Groq, Gemini, Anthropic and Ollama, with retries on rate limits. When a model stops without `final_answer`, the agent asks once or twice for a JSON `{"sql", "answer"}` with tools disabled. When Groq rejects a malformed tool call, that error is sent back as a message instead of ending the question.

Typical evaluation runs used about 4 to 6 steps and 7 to 12 seconds (Claude) up to about 100 seconds (local Qwen) per question.

## Failure modes

- Stopping after `run_sql` with an empty reply (seen on `gpt-oss` before the JSON fallback).
- Emitting tool calls as plain text (seen on `qwen2.5-coder`; the instruct model behaves better).
- Burning the step budget without calling `final_answer` (seen on one hard question for `gpt-oss-20b`).
- Answering with numbers that never appeared in a tool result.
- Provider-specific history fields (Gemini 3 `thought_signature`) that a plain OpenAI-shaped replay drops.

## Self-test

1. Why does prompt size grow on every tool turn?
2. What happens when `run_sql` returns a catalog error?
3. Why is `final_answer` a tool instead of free-form text only?
4. Why disable tools on the JSON nudge after an empty reply?

<details>
<summary>Answers</summary>

1. The client resends the whole conversation, including earlier tool outputs.
2. The error string is returned as the tool result so the model can rewrite the SQL.
3. So the program gets a structured SQL field it can re-run and score, not only a sentence.
4. Forcing a tool call on some models produced invalid tool names; a tool-free JSON answer was more reliable.

</details>
