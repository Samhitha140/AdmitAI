"""
Browser MCP tool - lets the Research Agent read official university admission
pages live at query time (solving the stale-data problem). Wrapped as a
LangChain @tool so it can be bound to the agent.
"""
from __future__ import annotations

from mcp_tools.compat import tool

from config.settings import settings
from mcp_tools.base import MCPClient

_client = MCPClient("browser", settings.BROWSER_MCP_URL)

# canned live data used when no Browser MCP server is connected
_MOCK_PAGES = {
    "tu munich": {
        "university": "TU Munich",
        "program": "MSc Informatics",
        "institution_type": "university",
        "funding_type": "public",
        "state_recognized": True,
        "deadline": "31 May 2026 (winter)",
        "intakes_offered": ["winter"],
        "deadlines": {"winter": "31 May 2026"},
        "tuition_eur": "0 (semester fee ~144 EUR)",
        "language_requirement": "IELTS 6.5 / TOEFL 88",
        "aps_required": True,
        "requirements": ["CGPA >= 7.5/10", "CS Bachelor", "APS certificate", "IELTS 6.5"],
        "source_url": "https://www.tum.de/en/studies",
    },
    "rwth aachen": {
        "university": "RWTH Aachen",
        "program": "MSc Data Science",
        "institution_type": "university",
        "funding_type": "public",
        "state_recognized": True,
        "deadline": "1 March 2026 (winter)",
        "intakes_offered": ["winter", "summer"],
        "deadlines": {"winter": "1 March 2026", "summer": "1 September 2026"},
        "tuition_eur": "0 (semester fee ~300 EUR)",
        "language_requirement": "IELTS 6.5",
        "aps_required": True,
        "requirements": ["CGPA >= 7.0/10", "Stats + programming coursework", "APS", "IELTS 6.5"],
        "source_url": "https://www.rwth-aachen.de/admission",
    },
    "munich university of applied sciences": {
        "university": "Munich University of Applied Sciences (HM)",
        "program": "MSc Applied Computer Science",
        "institution_type": "applied_sciences",
        "funding_type": "public",
        "state_recognized": True,
        "deadline": "15 June 2026 (winter)",
        "intakes_offered": ["winter", "summer"],
        "deadlines": {"winter": "15 June 2026", "summer": "15 December 2026"},
        "tuition_eur": "0 (semester fee ~130 EUR)",
        "language_requirement": "IELTS 6.0",
        "aps_required": True,
        # FH programmes often weigh practical experience / internships
        "requirements": [
            "CGPA >= 6.5/10",
            "Relevant Bachelor",
            "Pre-study internship (Vorpraktikum) preferred",
            "APS certificate",
            "IELTS 6.0",
        ],
        "source_url": "https://www.hm.edu/en/study",
    },
    "iu international": {
        "university": "IU International University",
        "program": "MSc Computer Science (English)",
        "institution_type": "applied_sciences",
        "funding_type": "private",
        "state_recognized": True,  # IU is state-recognised; always verify per institution
        "deadline": "Rolling (winter & summer)",
        "intakes_offered": ["winter", "summer"],
        "deadlines": {"winter": "Rolling - 1 Sep 2026", "summer": "Rolling - 1 Mar 2026"},
        "tuition_eur": "~13,000 EUR total (private)",
        "language_requirement": "IELTS 6.0 / proof of English-medium degree",
        "aps_required": True,
        "requirements": ["CGPA >= 6.0/10", "Relevant Bachelor", "APS certificate", "English proof"],
        "source_url": "https://www.iu.org/master/",
    },
}


@tool("browser_scrape_university")
def scrape_university(university: str, program: str = "") -> dict:
    """Read the live admission page for a German university program and return
    structured details (deadline, tuition, language requirement, APS, etc.)."""
    if _client.live:
        return _client.call_tool(
            "navigate_and_extract",
            {"university": university, "program": program},
        )
    key = university.strip().lower()
    return _MOCK_PAGES.get(
        key,
        {
            "university": university,
            "program": program or "MSc (program)",
            "institution_type": "university",
            "funding_type": "public",
            "state_recognized": True,
            "deadline": "15 March 2026 (winter)",
            "intakes_offered": ["winter"],
            "deadlines": {"winter": "15 March 2026"},
            "tuition_eur": "0 (public university)",
            "language_requirement": "IELTS 6.5",
            "aps_required": True,
            "requirements": ["CGPA >= 7.0/10", "Relevant Bachelor", "APS certificate"],
            "source_url": f"https://example.edu/{key.replace(' ', '-')}",
        },
    )
