# H6: Real LLM Quality Evaluation

H6 adds a real model-based quality gate instead of relying only on deterministic routing assertions.

The evaluation dataset contains representative specialist tasks, reference expectations, and explicit rubrics.

The live evaluator:

1. runs the real multi-agent system for each case
2. sends the resulting answer to a separate Groq judge
3. scores correctness, relevance, completeness, and safety
4. computes a deterministic weighted overall score
5. fails the evaluation when the case score is below its threshold

The judge prompt treats the query, reference, and candidate response as untrusted data so model-generated instructions are not executed as evaluation instructions.

Normal CI validates the dataset but does not consume a live LLM API budget.

The live workflow is manually triggered through GitHub Actions and requires the repository `GROQ_API_KEY` secret. It runs with an in-memory SQLite database and an ephemeral CI namespace so evaluation data is not persisted.

This separation keeps routine pull-request CI deterministic while retaining a real end-to-end LLM quality evaluation path.
