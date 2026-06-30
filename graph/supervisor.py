"""
Supervisor Agent.

Uses Groq (fast/free) for route classification, falling back to Gemini or
MockLLM. Gemini is reserved for quality-sensitive tasks (SOP, resume parsing).

Routes:
  program search  -> research -> eligibility
  SOP request     -> research -> eligibility -> sop
  deadline check  -> tracker
  scholarship     -> scholarship
  small talk      -> respond (finalize directly)
  missing profile -> respond (asks user for missing fields)
"""
from __future__ import annotations

from config.llm_provider import get_routing_model
from graph.state import IntelliAdmitState, RouteDecision

_ROUTER_PROMPT = """You are the supervisor of a university-admission multi-agent
system. Classify the user's request into EXACTLY ONE route label:

- "full_sop": user wants a Statement of Purpose / SOP / essay written
- "research_eligibility": user wants programs found and/or eligibility checked
- "tracker_only": user asks about deadlines, checklist, reminders, what's left
- "scholarship": user asks about scholarships, funding, financial aid, stipends, DAAD
- "respond": greeting/small talk needing no agents

User message: "{query}"

Reply with only the route label."""

_KEYWORDS = {
    "scholarship": ["scholarship", "scholarships", "funding", "financial aid", "stipend", "daad", "deutschlandstipendium", "fund my", "afford"],
    "full_sop": ["sop", "statement of purpose", "essay", "motivation letter", "write my"],
    "tracker_only": ["deadline", "checklist", "remind", "what's left", "todo", "track", "due"],
    "research_eligibility": ["eligible", "eligibility", "requirement", "can i get", "fit", "program", "university", "chance"],
}

# Fields needed before we can meaningfully run research or SOP
_REQUIRED_FOR_SEARCH = {
    "cgpa": "your CGPA / GPA (e.g. 8.2/10 or 3.5/4.0)",
    "degree": "your undergraduate degree subject (e.g. B.Tech Computer Science)",
    "target_field": "your target field of study in Germany (e.g. Computer Science, Data Science)",
}


def _keyword_route(query: str) -> RouteDecision:
    q = query.lower()
    for route, kws in _KEYWORDS.items():
        if any(k in q for k in kws):
            return route  # type: ignore[return-value]
    return "research_eligibility"


def _missing_profile_fields(profile: dict) -> list[str]:
    """Return human-readable labels for critical missing fields."""
    missing = []
    for field, label in _REQUIRED_FOR_SEARCH.items():
        val = profile.get(field)
        if not val or (isinstance(val, (int, float)) and float(val) <= 0.0):
            missing.append(label)
    # language_tests is optional — students often haven't taken IELTS yet
    return missing


def supervisor_node(state: IntelliAdmitState) -> dict:
    query = state["query"]
    profile = state.get("student_profile", {})

    # Use Groq for routing — fast, free, preserves Gemini quota
    llm = get_routing_model(temperature=0.0)

    route: RouteDecision = _keyword_route(query)
    # Only call the LLM when keyword matching didn't find a strong signal
    # (i.e. it fell through to the default "research_eligibility").
    q_lower = query.lower()
    keyword_matched = any(
        any(k in q_lower for k in kws) for kws in _KEYWORDS.values()
    )
    if not keyword_matched:
        try:
            resp = llm.invoke(_ROUTER_PROMPT.format(query=query)).content.strip().lower()
            for candidate in ["full_sop", "scholarship", "research_eligibility", "tracker_only", "respond"]:
                if candidate in resp:
                    route = candidate  # type: ignore[assignment]
                    break
        except Exception:
            pass

    # Before running research or SOP, check the profile is complete enough
    if route in ("research_eligibility", "full_sop"):
        missing = _missing_profile_fields(profile)
        if missing:
            clarify = (
                "I need a few more details before I can find matching programs:\n\n"
                + "\n".join(f"  • {m}" for m in missing)
                + "\n\nCould you share these? You can type them directly in the chat."
            )
            return {
                "route": "respond",
                "plan": [],
                "current_agent": "supervisor",
                "final_response": clarify,
                "conversation_history": [{"role": "assistant", "content": clarify}],
            }

    plan_map = {
        "full_sop": ["research", "eligibility", "sop", "tracker"],
        "research_eligibility": ["research", "eligibility"],
        "tracker_only": ["research", "tracker"],
        "scholarship": ["scholarship"],
        "respond": [],
    }
    return {
        "route": route,
        "plan": plan_map[route],
        "current_agent": "supervisor",
    }


def finalize_node(state: IntelliAdmitState) -> dict:
    """Build the final chat response based on which route ran."""
    if state.get("final_response"):
        return {"final_response": state["final_response"]}

    route = state.get("route", "")
    sop_drafts = state.get("sop_drafts", [])

    # ── SOP route ────────────────────────────────────────────────────────────
    if route == "full_sop" and sop_drafts:
        draft = sop_drafts[-1]
        detection = draft.get("critique", "")
        header = f"Here is your Statement of Purpose for {draft['university']}:\n\n"
        footer = f"\n\n— {detection}" if detection else ""
        response = header + draft["text"] + footer
        return {
            "final_response": response,
            "conversation_history": [{"role": "assistant", "content": response}],
        }

    # ── Tracker / deadline route ──────────────────────────────────────────────
    if route == "tracker_only":
        checklist = state.get("application_checklist", [])
        intake = state.get("student_profile", {}).get("target_intake", "winter")
        parts = [f"Application deadlines & checklist ({intake} intake):\n"]

        # Show per-university deadlines first
        deadline_items = [c for c in checklist if c.get("due_date")]
        if deadline_items:
            for item in deadline_items:
                due = item.get("due_date", "")
                parts.append(f"  • {item['task']} — due {due}")
        else:
            parts.append(
                "  No intake-specific deadlines found for your programs yet.\n"
                "  German university deadlines are typically:\n"
                "    • Winter intake (Oct start): apply by 15 July\n"
                "    • Summer intake (Apr start): apply by 15 January\n"
                "  Tip: Run university matching first so I can show exact deadlines per program."
            )

        # Standard tasks summary
        standard = [c for c in checklist if not c.get("due_date")]
        if standard:
            parts.append(f"\nStandard tasks to complete ({len(standard)} items):")
            for item in standard[:6]:
                parts.append(f"  • {item['task']}")

        response = "\n".join(parts)
        return {
            "final_response": response,
            "conversation_history": [{"role": "assistant", "content": response}],
        }

    # ── Scholarship route ─────────────────────────────────────────────────────
    if route == "scholarship":
        scholarships = state.get("scholarship_matches", [])
        if scholarships:
            parts = ["Scholarship matches for your profile:\n"]
            for s in scholarships:
                mark = "✓" if s.get("eligible") else "✗"
                parts.append(
                    f"  {mark} {s['name']} ({s['provider']}) · "
                    f"€{s.get('amount_eur_month', '?')}/month · "
                    f"deadline {s.get('deadline', 'n/a')}"
                )
            response = "\n".join(parts)
        else:
            response = "No scholarship matches found. Complete your profile and run matching first."
        return {
            "final_response": response,
            "conversation_history": [{"role": "assistant", "content": response}],
        }

    # ── Research / eligibility route ──────────────────────────────────────────
    auto_scholarships: list = []
    if not state.get("scholarship_matches") and state.get("student_profile", {}).get("target_field"):
        try:
            from agents.scholarship_agent import scholarship_node
            schol = scholarship_node(state)
            auto_scholarships = schol.get("scholarship_matches", [])
            state = {**state, "scholarship_matches": auto_scholarships}
        except Exception as exc:
            print(f"[finalize] scholarship auto-run failed: {exc}")

    parts: list[str] = []
    _TYPE_LABEL = {"university": "University", "applied_sciences": "Applied Sciences (FH)"}

    for elig in state.get("eligibility_scores", []):
        if not elig.get("intake_available", True):
            parts.append(
                f"- {elig['university']} ({elig['program']}): not offered for "
                f"{elig.get('intake', '')} intake — {elig['recommendation']}"
            )
            continue
        type_lbl = _TYPE_LABEL.get(elig.get("institution_type", ""), elig.get("institution_type", ""))
        funding = elig.get("funding_type", "")
        tag = " · ".join(t for t in [type_lbl, funding] if t)
        line = (
            f"- {elig['university']} ({elig['program']}) [{tag}]: "
            f"fit {elig['fit_score']}/100 — {elig['recommendation']}"
        )
        if elig.get("cost_note"):
            line += f"\n    {elig['cost_note']}"
        parts.append(line)
    if parts:
        intake = state.get("student_profile", {}).get("target_intake", "winter")
        parts.insert(0, f"Eligibility summary ({intake} intake):")

    scholarships = state.get("scholarship_matches", [])
    if scholarships:
        parts.append("\nScholarship matches:")
        for s in scholarships:
            mark = "✓" if s.get("eligible") else "✗"
            parts.append(
                f"  {mark} {s['name']} ({s['provider']}) · {s.get('amount_eur_month', '')} "
                f"· deadline {s.get('deadline', 'n/a')}"
            )

    if not parts:
        parts.append(
            "Hello! Share your CGPA, degree subject, and target field and I'll find "
            "German programs you're eligible for, along with scholarships and deadlines."
        )

    response = "\n".join(parts)
    return {
        "final_response": response,
        "scholarship_matches": auto_scholarships,
        "conversation_history": [{"role": "assistant", "content": response}],
    }
