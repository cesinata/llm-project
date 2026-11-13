# 8. Comparing models

The same agent and the same 22 questions, run with different language models: free hosted open models on Groq, a model on a laptop, and a paid commercial model.

## Intuition

- Accuracy is one axis. Cost, latency, tokens, privacy and reliability matter for a real team.
- Compare models on the same questions. A model that is two points ahead on 22 items is not "better" in any strong sense.
- Free tiers shape what you can measure. A run that dies on the last unanswerable question because of a daily token cap is not the same as a wrong refusal.

## The math

For paired yes/no outcomes on the same items, McNemar's test looks at disagreements only. Let $b$ be the number of questions A got right and B wrong, and $c$ the reverse. With a continuity correction:

$$\chi^2 = \frac{(|b - c| - 1)^2}{b + c}$$

If $b + c$ is small, do not over-read the result. Cost per correct answer is another simple summary:

$$\text{cost per correct} = \frac{\text{total \$ (or tokens)}}{\text{number correct}}$$

## Toy implementation

```python
def mcnemar(a_right: list[bool], b_right: list[bool]) -> tuple[int, int, float]:
    b = sum(1 for a, b_ in zip(a_right, b_right) if a and not b_)
    c = sum(1 for a, b_ in zip(a_right, b_right) if b_ and not a)
    if b + c == 0:
        return b, c, 0.0
    chi = (abs(b - c) - 1) ** 2 / (b + c)
    return b, c, chi


# Tiny demo: A beats B on 3 items, B beats A on 1.
a = [True, True, True, False, True]
b = [True, False, False, True, False]
print(mcnemar(a, b))
```

## In this project

Results from the README (execution accuracy on 22 questions):

| Model | Where | Accuracy | Avg tokens | Avg seconds |
|---|---|---|---|---|
| `claude-haiku-4-5` | Anthropic (paid) | 18/22 (82%) | 12,324 | 7.0 |
| `openai/gpt-oss-120b` | Groq free | 18/22 (82%) | 10,258 | 66.3 |
| `openai/gpt-oss-20b` | Groq free | 17/22 (77%) | 11,138 | 74.2 |
| `qwen2.5:7b` | Ollama on a MacBook | 11/22 (50%) | 7,881 | 101.5 |
| Gemini Flash | Google free tier | dropped | | |

Claude and `gpt-oss-120b` tie on the headline score; Claude is much faster and was the only model that cleared both unanswerable questions. Qwen is free and private (local) but slower and weaker on traps. Gemini was dropped: free Flash quotas are about 20 requests a day, and Gemini 3 tool calls need a `thought_signature` this OpenAI-shaped agent does not replay.

Groq's free tier allows about 200k tokens per model per day. A full run sits near or above that, which is why resume support and separate `provider_error` flags matter when comparing.

## Failure modes

- Comparing runs made with different prompts or warehouse builds.
- Treating provider limits as model quality.
- Picking the winner on the same set used to tune prompts.
- Ignoring latency and cost when the headline scores match.

## Self-test

1. Two models score 18/22 and 17/22. What should you say?
2. Why report average tokens and seconds next to accuracy?
3. Why was Gemini not left as "0%" in the table?
4. What does a paired test use that two separate percentages ignore?

<details>
<summary>Answers</summary>

1. They are not clearly different on 22 questions; report both and the margin.
2. Because a tied accuracy can still hide a 10× latency or cost gap.
3. The run never completed fairly: quota and protocol issues, not a measured execution accuracy of zero.
4. Which specific questions each model got right or wrong (the discordant pairs).

</details>
