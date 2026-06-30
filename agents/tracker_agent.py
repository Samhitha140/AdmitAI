"""
Tracker Agent.

Maintains application state across sessions (LangGraph MemorySaver persists it),
builds a personalised checklist (APS appointment, blocked account, IELTS/TestDaF,
Uni-Assist submission), computes which deadlines are near, and drafts reminder
emails via the Gmail MCP tool.
"""
from __future__ import annotations

import re
from datetime import date, datetime

from graph.state import ChecklistItem, IntelliAdmitState
from mcp_tools.gmail_tool import draft_reminder

_STANDARD_TASKS = [
    "Book APS certificate appointment",
    "Open blocked account (~11,904 EUR)",
    "Take IELTS / TestDaF language test",
    "Prepare & notarise transcripts",
    "Submit Uni-Assist application",
    "Apply for student visa",
]


def _parse_deadline(text: str) -> date | None:
    m = re.search(r"(\d{1,2})\s+(\w+)\s+(\d{4})", text)
    if not m:
        return None
    try:
        return datetime.strptime(" ".join(m.groups()), "%d %B %Y").date()
    except ValueError:
        return None


def tracker_node(state: IntelliAdmitState) -> dict:
    profile = state.get("student_profile", {})
    programs = state.get("target_programs", [])
    intake = profile.get("target_intake", "winter")

    checklist = [ChecklistItem(task=t).model_dump() for t in _STANDARD_TASKS]

    # per-program deadline items, anchored to the chosen intake
    reminders: list[dict] = []
    skipped: list[str] = []
    for prog in programs:
        intakes_offered = prog.get("intakes_offered", ["winter"])
        if intake not in intakes_offered:
            skipped.append(prog["university"])
            continue

        # prefer the intake-specific deadline, fall back to the generic one
        deadline_str = prog.get("deadlines", {}).get(intake) or prog.get("deadline", "")
        dl = _parse_deadline(deadline_str)

        checklist.append(
            ChecklistItem(
                task=f"Submit {prog['university']} application ({intake} intake)",
                due_date=deadline_str,
            ).model_dump()
        )

        # private institutions need a funding line item
        if prog.get("funding_type") == "private":
            checklist.append(
                ChecklistItem(
                    task=f"Arrange tuition funding for {prog['university']} "
                    f"({prog.get('tuition_eur', 'tuition applies')})",
                ).model_dump()
            )

        if dl and (dl - date.today()).days <= 60:
            reminders.append(
                draft_reminder.invoke(
                    {
                        "to": profile.get("email", "student@example.com"),
                        "subject": f"Deadline approaching: {prog['university']} ({intake})",
                        "body": f"Your application for {prog['program']} at "
                        f"{prog['university']} is due {deadline_str} for the {intake} intake.",
                    }
                )
            )

    note = f"Built {len(checklist)}-item checklist for the {intake} intake"
    if reminders:
        note += f"; drafted {len(reminders)} Gmail reminders for near deadlines"
    if skipped:
        note += f"; skipped {', '.join(skipped)} (no {intake} intake)"

    return {
        "application_checklist": checklist,
        "current_agent": "tracker",
        "conversation_history": [{"role": "assistant", "content": note + "."}],
    }
