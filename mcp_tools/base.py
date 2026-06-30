"""
Thin MCP (Model Context Protocol) client base.

MCP is Anthropic's open standard for exposing tools to any MCP-compatible LLM.
In production each tool below connects to a real MCP server URL (set via env);
when no URL is configured the wrapper returns deterministic mock data so the
agents still execute end-to-end.

Real wiring uses the `mcp` python package:

    from mcp import ClientSession
    from mcp.client.sse import sse_client
    async with sse_client(url) as (r, w):
        async with ClientSession(r, w) as session:
            await session.initialize()
            result = await session.call_tool(name, arguments)
"""
from __future__ import annotations

import asyncio
from typing import Any


class MCPClient:
    """Connects to one MCP server; falls back to mock if no URL configured."""

    def __init__(self, name: str, url: str | None) -> None:
        self.name = name
        self.url = url

    @property
    def live(self) -> bool:
        return bool(self.url)

    def call_tool(self, tool: str, arguments: dict[str, Any]) -> dict:
        if not self.live:
            return {"_mock": True, "tool": tool, "arguments": arguments}
        return asyncio.run(self._call_async(tool, arguments))

    async def _call_async(self, tool: str, arguments: dict[str, Any]) -> dict:
        from mcp import ClientSession
        from mcp.client.sse import sse_client

        async with sse_client(self.url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool, arguments)
                return {"content": [c.text for c in result.content]}
