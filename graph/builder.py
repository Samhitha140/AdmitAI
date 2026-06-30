"""
Graph assembly.

Wires the supervisor + four agent nodes + finalize node into a LangGraph
StateGraph with conditional edges, a MemorySaver checkpointer (persistent
per-student state via thread_id), and an interrupt before the SOP node for
human-in-the-loop approval.

Falls back to a hand-rolled sequential executor if langgraph is not installed,
so the project always runs.
"""
from __future__ import annotations

from agents.eligibility_agent import eligibility_node
from agents.research_agent import research_node
from agents.scholarship_agent import scholarship_node
from agents.sop_agent import sop_node
from agents.tracker_agent import tracker_node
from graph.edges import (
    route_after_eligibility,
    route_after_research,
    route_from_supervisor,
)
from graph.state import IntelliAdmitState, initial_state
from graph.supervisor import finalize_node, supervisor_node


# --------------------------------------------------------------------------- #
# Real LangGraph build
# --------------------------------------------------------------------------- #
def build_graph(checkpointer=None, with_hitl: bool = False):
    from langgraph.graph import END, StateGraph
    from langgraph.checkpoint.memory import MemorySaver

    workflow = StateGraph(IntelliAdmitState)

    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("research", research_node)
    workflow.add_node("eligibility", eligibility_node)
    workflow.add_node("sop", sop_node)
    workflow.add_node("tracker", tracker_node)
    workflow.add_node("scholarship", scholarship_node)
    workflow.add_node("finalize", finalize_node)

    workflow.set_entry_point("supervisor")
    workflow.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {"research": "research", "scholarship": "scholarship", "finalize": "finalize"},
    )
    workflow.add_conditional_edges(
        "research",
        route_after_research,
        {"eligibility": "eligibility", "tracker": "tracker"},
    )
    workflow.add_conditional_edges(
        "eligibility",
        route_after_eligibility,
        {"sop": "sop", "tracker": "tracker", "finalize": "finalize"},
    )
    workflow.add_edge("sop", "tracker")
    workflow.add_edge("tracker", "finalize")
    workflow.add_edge("scholarship", "finalize")
    workflow.add_edge("finalize", END)

    checkpointer = checkpointer or MemorySaver()
    interrupt = ["sop"] if with_hitl else []
    return workflow.compile(checkpointer=checkpointer, interrupt_before=interrupt)


# --------------------------------------------------------------------------- #
# Fallback sequential executor (no langgraph dependency)
# --------------------------------------------------------------------------- #
class _FallbackGraph:
    """Mimics graph.invoke(state, config) without langgraph installed."""

    def invoke(self, state: IntelliAdmitState, config: dict | None = None) -> IntelliAdmitState:
        state.update(supervisor_node(state))
        route = state.get("route")
        if route == "respond":
            state.update(finalize_node(state))
            return state
        if route == "scholarship":
            state = _merge(state, scholarship_node(state))
            state.update(finalize_node(state))
            return state

        state = _merge(state, research_node(state))
        if route != "tracker_only":
            state = _merge(state, eligibility_node(state))
        if route == "full_sop":
            state = _merge(state, sop_node(state))
        state.update(tracker_node(state))
        state.update(finalize_node(state))
        return state


def _merge(state: dict, update: dict) -> dict:
    """Apply add-reducer semantics for the fallback path."""
    list_keys = {
        "target_programs", "retrieved_docs", "eligibility_scores",
        "sop_drafts", "scholarship_matches", "conversation_history",
    }
    for k, v in update.items():
        if k in list_keys and isinstance(v, list):
            state[k] = state.get(k, []) + v
        else:
            state[k] = v
    return state


def get_app(with_hitl: bool = False):
    """Return a compiled graph, or the fallback if langgraph is unavailable."""
    try:
        return build_graph(with_hitl=with_hitl)
    except Exception as exc:  # pragma: no cover
        print(f"[graph] langgraph unavailable ({exc}); using sequential fallback")
        return _FallbackGraph()


def run_query(
    query: str,
    profile: dict,
    thread_id: str = "default",
    selected_university: str = "",
    resume_enriched: dict | None = None,
) -> IntelliAdmitState:
    app = get_app()
    state = initial_state(query, profile, thread_id)
    state["selected_university"] = selected_university
    state["resume_enriched"] = resume_enriched or {}
    config = {"configurable": {"thread_id": thread_id}}
    return app.invoke(state, config)
