"""
Google Drive MCP tool - lets the SOP Drafting Agent save each SOP iteration as a
versioned Google Doc inside a per-university application folder.
"""
from __future__ import annotations

from mcp_tools.compat import tool

from config.settings import settings
from mcp_tools.base import MCPClient

_client = MCPClient("drive", settings.DRIVE_MCP_URL)


@tool("drive_save_sop")
def save_sop(university: str, program: str, version: int, text: str) -> dict:
    """Save an SOP draft as a versioned Google Doc and return its shareable URL."""
    if _client.live:
        return _client.call_tool(
            "create_doc",
            {
                "folder": f"IntelliAdmit/{university}",
                "title": f"SOP_{program}_v{version}",
                "content": text,
            },
        )
    slug = f"{university}-{program}-v{version}".lower().replace(" ", "-")
    return {
        "drive_url": f"https://docs.google.com/document/d/mock-{slug}",
        "version": version,
        "status": "saved (mock)",
    }
