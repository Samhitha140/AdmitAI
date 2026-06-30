"""
Gmail MCP tool - lets the Tracker Agent draft deadline-reminder emails. Drafts
are always returned for the student to review before sending (human-in-the-loop;
never auto-sends).
"""
from __future__ import annotations

from mcp_tools.compat import tool

from config.settings import settings
from mcp_tools.base import MCPClient

_client = MCPClient("gmail", settings.GMAIL_MCP_URL)


@tool("gmail_draft_reminder")
def draft_reminder(to: str, subject: str, body: str) -> dict:
    """Create (not send) a Gmail draft reminding the student of an upcoming
    admission deadline. Returns the draft id and a preview."""
    if _client.live:
        return _client.call_tool(
            "create_draft", {"to": to, "subject": subject, "body": body}
        )
    return {
        "draft_id": "mock-draft-001",
        "status": "drafted (review before send)",
        "to": to,
        "subject": subject,
        "preview": body[:200],
    }
