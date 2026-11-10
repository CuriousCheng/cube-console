"""一个极简的 MCP 客户端（JSON-RPC over HTTP）。

Wren 的 MCP 用 streamable HTTP：POST 一次，响应可能是 SSE 的 data: 行。
"""

from __future__ import annotations

import json

import httpx


class McpClient:
    def __init__(self, port: int) -> None:
        self.url = f"http://127.0.0.1:{port}/mcp"
        self.sid: str | None = None
        self._id = 0

    def _headers(self) -> dict:
        h = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.sid:
            h["mcp-session-id"] = self.sid
        return h

    async def _post(self, payload: dict) -> dict:
        async with httpx.AsyncClient(timeout=90) as c:
            r = await c.post(self.url, json=payload, headers=self._headers())
        sid = r.headers.get("mcp-session-id")
        if sid:
            self.sid = sid
        if r.status_code >= 400:
            raise RuntimeError(f"MCP {r.status_code}: {r.text[:200]}")

        text = r.text
        lines = [ln for ln in text.splitlines() if ln.startswith("data:")]
        body = lines[-1][5:].strip() if lines else text.strip()
        msg = json.loads(body)
        if msg.get("error"):
            raise RuntimeError(msg["error"].get("message") or str(msg["error"]))
        return msg.get("result") or {}

    async def init(self) -> None:
        if self.sid:
            return
        self._id += 1
        await self._post(
            {
                "jsonrpc": "2.0",
                "id": self._id,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "wren-console", "version": "0.1.0"},
                },
            }
        )
        try:
            await self._post(
                {"jsonrpc": "2.0", "method": "notifications/initialized"}
            )
        except Exception:  # noqa: BLE001
            pass

    async def tool(self, name: str, args: dict | None = None) -> tuple[bool, str]:
        await self.init()
        self._id += 1
        res = await self._post(
            {
                "jsonrpc": "2.0",
                "id": self._id,
                "method": "tools/call",
                "params": {"name": name, "arguments": args or {}},
            }
        )
        text = "\n".join(c.get("text", "") for c in res.get("content", []))
        return (not res.get("isError")), text
