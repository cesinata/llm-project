# 7. Designing the evaluation

!!! note "Coming soon"
    This chapter is planned but not written yet. The outline below is what it will cover.

Chapter 1 defined how one answer is scored. This chapter is about choosing the questions: a small evaluation set is only useful if each question tests something specific.

## What it will cover

- **Intuition:** an evaluation set is a set of hypotheses about where the agent might fail. Each question should be able to fail for one clear reason.
- **The math:** how many questions are needed to tell two models apart (standard error and the width of a confidence interval as $N$ grows), and why per-difficulty scores on 5 to 8 questions are very noisy.
- **Toy implementation:** simulate two models with known accuracy and see how often a 22-question set ranks them the wrong way round.
- **In this project:**
    - The 22 questions in `evals/questions.yaml`: 5 easy, 8 medium, 7 hard, 2 unanswerable.
    - Trap questions and what each one tests: q02 (people vs crashes), q05 and q13 (exact labels), q15 (the partial year), q18 (the renamed council), q21 and q22 (questions the data cannot answer).
    - How each gold query was checked by hand, and why gold queries return only the columns asked for.
    - `order_matters` and the q07 tie.
    - Recording every answer as it finishes, and keeping provider errors separate from model errors (`--resume`).
- **Failure modes:** questions that only have one wording, gold answers that drift when the data is refreshed, evaluating on the same questions used to tune the prompt, ambiguous questions.
- **Self-test.**
