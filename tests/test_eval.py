"""Tests for the evaluation layer."""
from __future__ import annotations

from eval.llm_judge import judge_sop
from eval.ragas_eval import TARGETS, run_ragas


def test_llm_judge_returns_rubric():
    scores = judge_sop(
        "My motivation to study machine learning at TU Munich began during my "
        "undergraduate research. This program's focus on systems aligns with my "
        "career goal of building reliable ML. I chose Germany for its research depth.",
        "TU Munich MSc Informatics",
    )
    assert set(scores) == {"motivation", "tone", "fit", "structure"}
    assert all(1 <= v <= 5 for v in scores.values())


def test_ragas_reports_all_metrics():
    scores = run_ragas()
    for metric in TARGETS:
        assert metric in scores
        assert 0.0 <= scores[metric] <= 1.0
