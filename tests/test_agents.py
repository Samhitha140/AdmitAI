"""End-to-end tests for the graph and individual agents (run in MOCK mode)."""
from __future__ import annotations

from agents.eligibility_agent import eligibility_node
from agents.research_agent import research_node
from agents.tracker_agent import tracker_node
from graph.builder import run_query
from graph.state import initial_state

PROFILE = {
    "name": "Test",
    "degree": "B.Tech CSE",
    "cgpa": 8.0,
    "target_field": "Computer Science",
    "language_tests": ["IELTS 7.0"],
    "email": "t@example.com",
    "target_intake": "winter",
    "application_level": "masters",
}


def test_research_agent_returns_programs():
    state = initial_state("find CS programs", PROFILE)
    out = research_node(state)
    assert out["target_programs"], "research agent should return programs"
    assert "university" in out["target_programs"][0]


def test_eligibility_agent_scores():
    state = initial_state("am i eligible", PROFILE)
    state.update(research_node(state))
    state["target_programs"] = state.get("target_programs", [])
    out = eligibility_node(state)
    assert out["eligibility_scores"]
    score = out["eligibility_scores"][0]["fit_score"]
    assert 0 <= score <= 100


def test_tracker_builds_checklist():
    state = initial_state("what's left", PROFILE)
    state.update(research_node(state))
    state["target_programs"] = research_node(state)["target_programs"]
    out = tracker_node(state)
    assert len(out["application_checklist"]) >= 6


def test_full_graph_eligibility_route():
    state = run_query("which universities am I eligible for?", PROFILE, "test-thread")
    assert state.get("eligibility_scores")
    assert state.get("final_response")


def test_full_graph_sop_route():
    state = run_query("write me a statement of purpose", PROFILE, "test-thread-2",
                      selected_university="RWTH Aachen", resume_enriched={})
    assert state.get("sop_drafts"), "SOP route should produce a draft"
    assert state["sop_drafts"][0]["text"]


def test_full_graph_tracker_route():
    state = run_query("what deadlines do I have left?", PROFILE, "test-thread-3")
    assert state.get("application_checklist")


def test_eligibility_tags_institution_type_and_funding():
    state = initial_state("am i eligible", PROFILE)
    state["target_programs"] = research_node(state)["target_programs"]
    out = eligibility_node(state)
    types = {r["institution_type"] for r in out["eligibility_scores"] if r.get("intake_available")}
    fundings = {r["funding_type"] for r in out["eligibility_scores"] if r.get("intake_available")}
    assert "university" in types and "applied_sciences" in types
    assert "public" in fundings and "private" in fundings


def test_summer_intake_filters_winter_only_programs():
    summer_profile = {**PROFILE, "target_intake": "summer"}
    state = initial_state("am i eligible", summer_profile)
    state["target_programs"] = research_node(state)["target_programs"]
    out = eligibility_node(state)
    tum = [r for r in out["eligibility_scores"]
           if "Munich" in r["university"] and r["institution_type"] == "university"]
    assert tum and tum[0]["intake_available"] is False


def test_institution_preference_filter():
    fh_profile = {**PROFILE, "preferred_institution_type": "applied_sciences"}
    state = initial_state("am i eligible", fh_profile)
    state["target_programs"] = research_node(state)["target_programs"]
    out = eligibility_node(state)
    assert out["eligibility_scores"]
    assert all(r["institution_type"] == "applied_sciences" for r in out["eligibility_scores"])


def test_scholarship_agent_matches_masters():
    from agents.scholarship_agent import scholarship_node
    state = initial_state("what scholarships can I get?", PROFILE)
    out = scholarship_node(state)
    assert out["scholarship_matches"]
    names = " ".join(m["name"] for m in out["scholarship_matches"]).lower()
    assert "daad" in names
    assert any(m["eligible"] for m in out["scholarship_matches"])


def test_scholarship_level_gating_bachelors():
    from agents.scholarship_agent import scholarship_node
    ug_profile = {**PROFILE, "application_level": "bachelors"}
    state = initial_state("scholarships?", ug_profile)
    out = scholarship_node(state)
    for m in out["scholarship_matches"]:
        assert "bachelors" in m["levels"]


def test_full_graph_scholarship_route():
    state = run_query("what funding or scholarships can I get?", PROFILE, "schol-thread")
    assert state.get("route") == "scholarship"
    assert state.get("scholarship_matches")


def test_resume_parser_mock():
    from agents.resume_parser import parse_resume
    ep = parse_resume("/nonexistent/file.pdf")
    assert ep.thesis_title
    assert len(ep.top_projects) > 0
    assert len(ep.skills) > 0


def test_sop_uses_resume_context():
    from agents.resume_parser import _MOCK_ENRICHED
    state = run_query("write me a statement of purpose", PROFILE, "sop-resume-thread",
                      resume_enriched=_MOCK_ENRICHED.model_dump())
    assert state.get("sop_drafts")


def test_database_register_login():
    from api.database import login, logout, register, get_user_by_token
    import time
    email = f"test_{int(time.time())}@example.com"
    r = register(email, "testpass123", "Test User")
    assert r["ok"]
    l = login(email, "testpass123")
    assert l["ok"]
    assert l["token"]
    user = get_user_by_token(l["token"])
    assert user and user["email"] == email
    logout(l["token"])
    assert get_user_by_token(l["token"]) is None


def test_database_duplicate_register():
    from api.database import register
    import time
    email = f"dup_{int(time.time())}@example.com"
    register(email, "pass", "User")
    r2 = register(email, "pass2", "User2")
    assert not r2["ok"]
    assert "already" in r2["error"].lower()
