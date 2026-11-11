# 8. Comparing models

!!! note "Coming soon"
    This chapter will be written once the full evaluation runs are finished. The outline below is what it will cover.

The same agent and the same questions, run with different language models: free hosted open models, a model running on a laptop, and a paid commercial model.

## What it will cover

- **Intuition:** accuracy is one axis. Cost, latency, tokens used, privacy (where the data goes) and reliability (provider errors, malformed tool calls) all matter when choosing a model for a real team.
- **The math:** a paired comparison. Both models answer the same 22 questions, so compare them question by question (McNemar's test) rather than comparing two percentages. Cost per correct answer.
- **Toy implementation:** McNemar's test on two lists of right/wrong results, in a few lines of Python.
- **In this project:**
    - The results table from the README, for the models run: `openai/gpt-oss-120b` and `openai/gpt-oss-20b` on Groq, `gemini-2.5-flash`, `claude-haiku-4-5`, and `qwen2.5:7b` (and possibly `qwen2.5:14b`) on Ollama.
    - Accuracy by difficulty, average steps, tokens, latency and self-corrections for each.
    - Free-tier limits in practice: Groq's 200k tokens per model per day, and what one full run uses.
    - What a small local model gets right and wrong compared with a large hosted one.
- **Failure modes:** comparing runs made with different prompts or data, reading too much into a few questions, ignoring provider errors, picking the model with the best score on the set you tuned on.
- **Self-test.**
