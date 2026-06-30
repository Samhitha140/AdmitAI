"""
Conditional edge functions for the LangGraph.

These pure functions inspect the state and return the name of the next node (or
a list, for parallel fan-out). They are registered with
`graph.add_conditional_edges(...)` in graph builder.
"""
from __future__ import annotations

from graph.state import IntelliAdmitState


def route_from_supervisor(state: IntelliAdmitState) -> str:
    """First hop after the supervisor decides the route."""
    route = state.get("route", "research_eligibility")
    if route == "respond":
        return "finalize"
    if route == "scholarship":
        # funding queries don't need program research; go straight to scholarships
        return "scholarship"
    # every other non-trivial route starts by researching programs
    return "research"


def route_after_eligibility(state: IntelliAdmitState) -> str:
    """After eligibility, branch to SOP, tracker, or finish."""
    route = state.get("route")
    if route == "full_sop":
        return "sop"
    if route == "tracker_only":
        return "tracker"
    return "finalize"


def route_after_research(state: IntelliAdmitState) -> str:
    """tracker_only skips eligibility scoring and goes straight to tracker."""
    if state.get("route") == "tracker_only":
        return "tracker"
    return "eligibility"
