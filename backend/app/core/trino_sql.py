"""在 Trino 上跑一条 SQL（走 REST /v1/statement），返回列名和行。"""

from __future__ import annotations

import asyncio

import httpx

from ..config import TRINO_URL


async def query(sql: str, user: str = "console", timeout: float = 60.0) -> dict:
    headers = {
        "X-Trino-User": user,
        "Content-Type": "text/plain; charset=utf-8",
    }
    async with httpx.AsyncClient(timeout=timeout) as c:
        r = await c.post(f"{TRINO_URL}/v1/statement", content=sql, headers=headers)
        if r.status_code >= 400:
            return {"ok": False, "error": f"Trino {r.status_code}: {r.text[:300]}"}

        data = r.json()
        columns: list[str] = []
        rows: list[dict] = []

        for _ in range(120):
            if data.get("error"):
                err = data["error"]
                return {"ok": False, "error": f"{err.get('errorName')}: {err.get('message')}"}

            if not columns and data.get("columns"):
                columns = [c["name"] for c in data["columns"]]

            for row in data.get("data") or []:
                rows.append(dict(zip(columns, row)))

            nxt = data.get("nextUri")
            if not nxt:
                break
            await asyncio.sleep(0.05)
            r2 = await c.get(nxt)
            data = r2.json()

        return {"ok": True, "columns": columns, "rows": rows}


async def schemas(catalog: str) -> list[str]:
    r = await query(f'SHOW SCHEMAS FROM "{catalog}"')
    if not r["ok"]:
        raise RuntimeError(r["error"])
    return [row["Schema"] for row in r["rows"]]


async def tables(catalog: str, schema: str) -> list[str]:
    r = await query(f'SHOW TABLES FROM "{catalog}"."{schema}"')
    if not r["ok"]:
        raise RuntimeError(r["error"])
    return [row["Table"] for row in r["rows"]]


async def columns(catalog: str, schema: str, table: str) -> list[dict]:
    r = await query(f'DESCRIBE "{catalog}"."{schema}"."{table}"')
    if not r["ok"]:
        raise RuntimeError(r["error"])
    out = []
    for row in r["rows"]:
        out.append(
            {
                "name": row.get("Column", ""),
                "type": row.get("Type", ""),
                "extra": row.get("Extra", ""),
                "comment": row.get("Comment", ""),
            }
        )
    return out
