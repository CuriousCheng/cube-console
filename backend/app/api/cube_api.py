"""Cube 集成：读 cube 元数据、把选中的表组合成一个业务视图（view）。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time
from pathlib import Path

import httpx
from fastapi import Depends, HTTPException
from pydantic import BaseModel

CUBE_URL = os.getenv("CUBE_URL", "http://127.0.0.1:4000").rstrip("/")
CUBE_CONF = Path(os.getenv("CUBE_CONF", "") or (Path.home() / "cube" / "conf"))


def _secret() -> str:
    env = os.getenv("CUBE_API_SECRET")
    if env:
        return env
    f = CUBE_CONF / ".env"
    if f.exists():
        for line in f.read_text("utf-8").splitlines():
            if line.startswith("CUBEJS_API_SECRET="):
                return line.split("=", 1)[1].strip()
    return "devsecret"


def _token() -> str:
    secret = _secret().encode()

    def b64(d: bytes) -> str:
        return base64.urlsafe_b64encode(d).rstrip(b"=").decode()

    h = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    p = b64(json.dumps({"iat": int(time.time()), "exp": int(time.time()) + 3600}).encode())
    s = b64(hmac.new(secret, f"{h}.{p}".encode(), hashlib.sha256).digest())
    return f"{h}.{p}.{s}"


class ViewIn(BaseModel):
    name: str
    title: str = ""
    cubes: list[str]
    description: str = ""


class QueryIn(BaseModel):
    measures: list[str] = []
    dimensions: list[str] = []
    time_dimension: str = ""
    granularity: str = "month"
    limit: int = 500


def _hdr() -> dict:
    return {"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"}


def register(app, current_user, require) -> None:
    @app.get("/api/cube/meta")
    async def cube_meta(user: dict = Depends(current_user)) -> dict:
        try:
            async with httpx.AsyncClient(timeout=40) as c:
                r = await c.get(f"{CUBE_URL}/cubejs-api/v1/meta", headers=_hdr())
                r.raise_for_status()
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"连不上 Cube：{e}") from e

        cubes = []
        for c in r.json().get("cubes", []):
            cubes.append(
                {
                    "name": c.get("name"),
                    "type": c.get("type", "cube"),
                    "title": c.get("title"),
                    "public": c.get("public", True),
                    "isVisible": c.get("isVisible", True),
                    "measures": [
                        {"name": m.get("name"), "title": m.get("title"), "type": m.get("type")}
                        for m in c.get("measures", [])
                    ],
                    "dimensions": [
                        {
                            "name": d.get("name"),
                            "title": d.get("title"),
                            "type": d.get("type"),
                            "primaryKey": d.get("primaryKey", False),
                        }
                        for d in c.get("dimensions", [])
                    ],
                }
            )
        return {"ok": True, "cubes": cubes}

    @app.post("/api/cube/view")
    async def create_view(body: ViewIn, user: dict = Depends(require("editor"))) -> dict:
        name = body.name.strip()
        # Cube 的 name 必须是标识符：小写字母开头，只能字母数字下划线
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,40}", name):
            raise HTTPException(400, "标识名必须小写字母开头，只能用 a-z 0-9 _")
        if not body.cubes:
            raise HTTPException(400, "至少选一张表")

        d = CUBE_CONF / "model" / "views"
        d.mkdir(parents=True, exist_ok=True)

        lines = ["views:", f"  - name: {name}"]
        if body.title:
            lines.append(f"    title: {body.title}")
        if body.description:
            lines.append(f"    description: {body.description}")
        lines.append("    cubes:")
        for i, cb in enumerate(body.cubes):
            lines.append(f"      - join_path: {cb}")
            lines.append('        includes: "*"')
            if i > 0:
                # 非根表排除通用成员，避免 id/count 重名冲突
                lines.append("        excludes:")
                lines.append("          - id")
                lines.append("          - count")

        p = d / f"{name}.yml"
        p.write_text("\n".join(lines) + "\n", "utf-8")
        return {"ok": True, "file": str(p), "name": name}

    @app.get("/api/cube/views")
    async def list_views(user: dict = Depends(current_user)) -> dict:
        d = CUBE_CONF / "model" / "views"
        items = []
        if d.is_dir():
            for f in sorted(d.glob("*.yml")):
                items.append({"name": f.stem, "file": str(f), "size": f.stat().st_size})
        return {"ok": True, "items": items}

    @app.delete("/api/cube/views/{name}")
    async def del_view(name: str, user: dict = Depends(require("editor"))) -> dict:
        p = CUBE_CONF / "model" / "views" / f"{name}.yml"
        if p.exists():
            p.unlink()
        return {"ok": True}

    @app.post("/api/cube/query")
    async def cube_query(body: QueryIn, user: dict = Depends(current_user)) -> dict:
        query: dict = {"measures": body.measures, "dimensions": body.dimensions}
        if body.time_dimension:
            td = body.time_dimension
            if ":" in td:
                dim, gran = td.split(":", 1)
            else:
                dim, gran = td, body.granularity
            query["timeDimensions"] = [{"dimension": dim, "granularity": gran}]
        try:
            async with httpx.AsyncClient(timeout=180) as c:
                r = await c.post(
                    f"{CUBE_URL}/cubejs-api/v1/load",
                    headers=_hdr(),
                    json={"query": query, "queryType": "regular"},
                )
                data = r.json()
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"查询失败：{e}") from e

        if r.status_code >= 400:
            return {"ok": False, "error": data.get("error") or str(data)[:300]}

        rows = data.get("data") or []
        cols = list(rows[0].keys()) if rows else (body.measures + body.dimensions)
        sql = ""
        q = data.get("query") or {}
        s = q.get("sql") or {}
        if isinstance(s, dict):
            sql = ";\n".join(str(v) for v in s.values())
        return {"ok": True, "columns": cols, "rows": rows[: body.limit], "sql": sql}
