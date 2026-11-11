# 5. Tool calling and the agent loop

!!! note "Coming soon"
    This chapter is planned but not written yet. The outline below is what it will cover.

The agent does not answer in one shot. It works in a loop: the model **reasons** about what it needs, **acts** by calling a tool, **observes** the result, and repeats until it calls `final_answer`. This pattern is often called ReAct (reason + act).

## What it will cover

- **Intuition:** why letting the model inspect the schema and test its own queries beats pasting the whole schema into one prompt.
- **The math:** the loop as a sequence of states and actions with a step budget, and how tokens grow with each step (every call resends the conversation so far).
- **Toy implementation:** a 30-line agent loop with a scripted fake model, no API key needed.
- **In this project:**
    - The four tools in `src/crashsql/agent.py`: `list_tables`, `describe_table`, `run_sql`, `final_answer`, defined as JSON schemas in the OpenAI tool-calling format.
    - The system prompt and its rules (exact labels, crashes vs people, partial year, never invent numbers, decline when the data cannot answer).
    - Self-correction: SQL errors are sent back to the model as tool results so it can fix the query.
    - The step budget (`max_steps = 12`) and what happens when it runs out.
    - One OpenAI-compatible client (`src/crashsql/llm.py`) for Groq, Gemini, Anthropic and Ollama, with retries on rate limits.
    - Real traces from `crashsql ask -v`, with steps, tokens and latency.
- **Failure modes:** the model stops without calling `final_answer`, malformed tool calls, loops that repeat the same query, answers whose numbers do not match the query result.
- **Self-test.**
