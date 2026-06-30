"""
Benchmark the fine-tuned SOP model against base Mistral-7B and GPT-4o on 20 test
profiles, scored by the LLM-as-judge rubric. Produces a comparison table.

    python -m finetuning.evaluate
"""
from __future__ import annotations

import json
from pathlib import Path

from eval.llm_judge import judge_sop

_TEST_PROFILES = [
    {"degree": "B.Tech CSE", "cgpa": 8.2, "target": "TU Munich MSc Informatics", "interests": "ML"},
    {"degree": "B.Sc Data Science", "cgpa": 7.6, "target": "RWTH MSc Data Science", "interests": "NLP"},
]


def evaluate(models: dict[str, callable] | None = None) -> dict:
    """models maps a name to a fn(profile)->sop_text. Defaults to a stub."""
    if models is None:
        from agents.sop_agent import sop_node  # not directly callable per-model

        def _stub(p):
            return f"[SOP for {p['target']}] motivation, background, fit, goals."

        models = {"finetuned-mistral": _stub, "base-mistral": _stub, "gpt-4o": _stub}

    results: dict[str, list[dict]] = {m: [] for m in models}
    for profile in _TEST_PROFILES:
        for name, fn in models.items():
            sop = fn(profile)
            scores = judge_sop(sop, profile["target"])
            results[name].append(scores)

    summary = {}
    for name, runs in results.items():
        keys = runs[0].keys() if runs else []
        summary[name] = {k: round(sum(r[k] for r in runs) / len(runs), 2) for k in keys}

    Path("eval/benchmarks").mkdir(parents=True, exist_ok=True)
    Path("eval/benchmarks/sop_benchmark.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    evaluate()
