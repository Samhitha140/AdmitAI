"""
Scholarship MCP tool.

Scholarship data does NOT live on university admission pages, so it needs its own
source. This tool queries the DAAD scholarship database (the canonical source for
international students in Germany) plus a few other well-known providers. When no
live MCP server is connected it returns a bundled snapshot so the Scholarship Agent
still works offline.

Note on freshness: DAAD itself warns that funding information may be incomplete or
out of date, so every record keeps a source_url and the agent flags "verify with the
provider before applying" - the same live-not-frozen philosophy used for deadlines.
"""
from __future__ import annotations

from mcp_tools.compat import tool

from config.settings import settings
from mcp_tools.base import MCPClient

_client = MCPClient("scholarship", settings.SCHOLARSHIP_MCP_URL)

# Bundled DAAD-based snapshot (figures are indicative - verify before applying).
_MOCK_SCHOLARSHIPS = [
    {
        "name": "DAAD Study Scholarship - Master's (All Disciplines)",
        "provider": "DAAD",
        "levels": ["masters"],
        "fields": "all",
        "amount_eur_month": "~992 EUR/month",
        "covers": ["monthly stipend", "health insurance", "travel allowance"],
        "deadline": "varies by country (often Oct-Nov)",
        "min_cgpa": 7.5,
        "source_url": "https://www2.daad.de/deutschland/stipendium/datenbank/en/",
    },
    {
        "name": "DAAD Study Scholarship - STEM Disciplines",
        "provider": "DAAD",
        "levels": ["masters"],
        "fields": "STEM",
        "amount_eur_month": "~992 EUR/month",
        "covers": ["monthly stipend", "health insurance", "travel allowance"],
        "deadline": "varies by country",
        "min_cgpa": 7.5,
        "source_url": "https://www2.daad.de/deutschland/stipendium/datenbank/en/",
    },
    {
        "name": "DAAD EPOS - Development-Related Postgraduate Courses",
        "provider": "DAAD",
        "levels": ["masters"],
        "fields": "development-related",
        "amount_eur_month": "~992 EUR/month",
        "covers": ["monthly stipend", "health insurance", "travel", "study allowance"],
        "deadline": "varies by course (2026/27 list)",
        "min_cgpa": 7.0,
        "requires_work_experience": True,
        "source_url": "https://www2.daad.de/deutschland/stipendium/datenbank/en/",
    },
    {
        "name": "Deutschlandstipendium",
        "provider": "Participating German universities",
        "levels": ["bachelors", "masters"],
        "fields": "all",
        "amount_eur_month": "300 EUR/month",
        "covers": ["merit-based stipend (no needs test)"],
        "deadline": "set by each university",
        "min_cgpa": 8.0,
        "source_url": "https://www.deutschlandstipendium.de/",
    },
    {
        "name": "Erasmus+ (study mobility)",
        "provider": "EU / host university",
        "levels": ["bachelors", "masters"],
        "fields": "all",
        "amount_eur_month": "varies (mobility grant)",
        "covers": ["mobility grant", "travel support"],
        "deadline": "via host university",
        "min_cgpa": 0.0,
        "source_url": "https://erasmus-plus.ec.europa.eu/",
    },
    {
        "name": "DAAD University Summer Course Scholarship",
        "provider": "DAAD",
        "levels": ["bachelors"],
        "fields": "all (German language/short courses)",
        "amount_eur_month": "~850 EUR (one-off, short course)",
        "covers": ["course fee", "partial living costs"],
        "deadline": "01 Dec each year",
        "min_cgpa": 6.5,
        "source_url": "https://www2.daad.de/deutschland/stipendium/datenbank/en/",
    },
]


@tool("scholarship_search")
def search_scholarships(level: str = "masters", field: str = "") -> list[dict]:
    """Search German scholarship sources (DAAD database + others) for programmes
    matching the student's academic level and field. Returns raw scholarship records;
    eligibility is decided by the Scholarship Agent."""
    if _client.live:
        return _client.call_tool("search", {"level": level, "field": field})
    # offline: return the bundled snapshot, pre-filtered by level
    return [s for s in _MOCK_SCHOLARSHIPS if level in s["levels"]]
