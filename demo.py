"""
Interactive / scripted CLI demo for IntelliAdmit.

    python demo.py                # runs three scripted queries end-to-end
    python demo.py --interactive  # chat loop

Works with zero credentials (MOCK mode) so you can verify the full LangGraph
pipeline before wiring up Gemini, MCP servers, or the fine-tuned adapter.
"""
from __future__ import annotations

import sys

from config.settings import settings
from graph.builder import run_query

SAMPLE_PROFILE = {
    "name": "Samhitha",
    "degree": "B.Tech Computer Science",
    "cgpa": 8.1,
    "target_field": "Computer Science",
    "target_country": "Germany",
    "work_experience_years": 1.0,
    "language_tests": ["IELTS 7.0"],
    "interests": "machine learning, NLP",
    "email": "student@example.com",
    "target_intake": "winter",          # try "summer" to see programs get filtered
    "application_level": "masters",     # or "bachelors"
    "preferred_institution_type": None,  # or "university" / "applied_sciences"
    "preferred_funding": None,           # or "public" / "private"
}

SCRIPTED = [
    "Which German universities am I eligible for in computer science?",
    "What scholarships can I get to fund my master's?",
    "Write a Statement of Purpose for the best-fit program.",
    "What deadlines and checklist items are left?",
]


def _show(state: dict) -> None:
    print("\n" + "=" * 70)
    print(f"ROUTE: {state.get('route')}")
    print("-" * 70)
    print(state.get("final_response", ""))
    print("=" * 70)


def scripted() -> None:
    print(f"IntelliAdmit demo - running in {settings.mode} mode\n")
    for q in SCRIPTED:
        print(f"\n>>> {q}")
        state = run_query(q, SAMPLE_PROFILE, thread_id="demo-user")
        _show(state)


def interactive() -> None:
    print(f"IntelliAdmit ({settings.mode} mode). Type 'quit' to exit.\n")
    while True:
        q = input("you> ").strip()
        if q.lower() in {"quit", "exit"}:
            break
        state = run_query(q, SAMPLE_PROFILE, thread_id="cli-user")
        _show(state)


if __name__ == "__main__":
    if "--interactive" in sys.argv:
        interactive()
    else:
        scripted()
