"""项目接口：建/删/列表/启停 MCP。"""

from __future__ import annotations

import time

from fastapi import Depends, HTTPException
from pydantic import BaseModel

from .. import store
from ..core import mcp_pool, wren_project


class ProjectIn(BaseModel):
    name: str
    datasource_id: str | None = None  # 用哪个数据源做主 catalog


class RememberIn(BaseModel):
    question: str
    sql: str


def _metadata() -> dict:
    return store.read("projects", {"items": {}}).get("items", {})


async def _save_metadata(items: dict) -> None:
    await store.write("projects", {"items": items})


def register(app, current_user, require) -> None:
    @app.get("/api/projects")
    async def list_projects(user: dict = Depends(current_user)) -> dict:
        meta = _metadata()
        out = []
        for name in wren_project.list_projects():
            m = meta.get(name, {})
            st = mcp_pool.pool.status(name)
            out.append(
                {
                    "name": name,
                    "datasource": m.get("datasource"),
                    "catalog": m.get("catalog"),
                    "models": len(wren_project.models_of(name)),
                    "created_at": m.get("created_at"),
                    "mcp": st,
                }
            )
        return {"items": out}

    @app.post("/api/projects")
    async def create_project(body: ProjectIn, user: dict = Depends(require("editor"))) -> dict:
        name = body.name.strip()
        if not name:
            raise HTTPException(400, "项目名不能为空")

        catalog = None
        datasource = None
        schema = None
        if body.datasource_id:
            ds = store.read("datasources", {"items": []}).get("items", [])
            d = next((x for x in ds if x["id"] == body.datasource_id), None)
            if not d:
                raise HTTPException(404, "数据源不存在")
            catalog = d.get("catalog")
            datasource = d.get("name")
            schema = d.get("database") or None

        try:
            created = await wren_project.create(
                name, catalog or "mysql", schema or "public"
            )
        except FileExistsError as e:
            raise HTTPException(400, str(e)) from e
        except Exception as e:  # noqa: BLE001
            raise HTTPException(500, f"创建失败：{e}") from e

        meta = _metadata()
        meta[created["name"]] = {
            "datasource": datasource,
            "catalog": catalog,
            "created_at": int(time.time()),
            "created_by": user["name"],
        }
        await _save_metadata(meta)
        return {"ok": True, "project": created}

    @app.delete("/api/projects/{name}")
    async def delete_project(name: str, user: dict = Depends(require("admin"))) -> dict:
        if name not in wren_project.list_projects():
            raise HTTPException(404, "项目不存在")
        await mcp_pool.pool.stop(name)
        wren_project.delete(name)
        meta = _metadata()
        meta.pop(name, None)
        await _save_metadata(meta)
        return {"ok": True}

    @app.post("/api/projects/{name}/start")
    async def start_project(name: str, user: dict = Depends(require("editor"))) -> dict:
        if name not in wren_project.list_projects():
            raise HTTPException(404, "项目不存在")
        cfg = store.read("config", {})
        capacity = int(cfg.get("pool_size", 3))
        try:
            r = await mcp_pool.pool.ensure(name, capacity)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(500, f"启动失败：{e}") from e
        return {"ok": True, **r, "mcp": mcp_pool.pool.status(name)}

    @app.post("/api/projects/{name}/stop")
    async def stop_project(name: str, user: dict = Depends(require("editor"))) -> dict:
        await mcp_pool.pool.stop(name)
        return {"ok": True}

    @app.get("/api/projects/{name}/status")
    async def project_status(name: str, user: dict = Depends(current_user)) -> dict:
        return mcp_pool.pool.status(name)

    @app.get("/api/projects/{name}/schema")
    async def project_schema(name: str, user: dict = Depends(current_user)) -> dict:
        """返回项目的 MDL（给网关和建模页用）。"""
        if name not in wren_project.list_projects():
            raise HTTPException(404, "项目不存在")
        cfg = store.read("config", {})
        try:
            started = await mcp_pool.pool.ensure(name, int(cfg.get("pool_size", 3)))
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"启动项目失败：{e}"}

        from ..core.mcp_client import McpClient

        client = McpClient(started["port"])
        ok, text = await client.tool("get_mdl")
        return {"ok": ok, "mdl": text}

    # ── 记忆 ────────────────────────────────────────
    @app.get("/api/projects/{name}/memory")
    async def memory(name: str, user: dict = Depends(current_user)) -> dict:
        if name not in wren_project.list_projects():
            raise HTTPException(404, "业务不存在")
        items = wren_project.memory_files(name)
        return {"ok": True, "count": len(items), "items": items}

    @app.post("/api/projects/{name}/index")
    async def index_memory(name: str, user: dict = Depends(require("editor"))) -> dict:
        if name not in wren_project.list_projects():
            raise HTTPException(404, "业务不存在")
        return await wren_project.memory_index(name)

    @app.post("/api/projects/{name}/remember")
    async def remember(
        name: str, body: RememberIn, user: dict = Depends(require("editor"))
    ) -> dict:
        """把一条「问题 → SQL」存进这个业务的记忆。"""
        if name not in wren_project.list_projects():
            raise HTTPException(404, "业务不存在")
        cfg = store.read("config", {})
        try:
            started = await mcp_pool.pool.ensure(name, int(cfg.get("pool_size", 3)))
        except Exception as e:  # noqa: BLE001
            raise HTTPException(500, f"启动业务失败：{e}") from e

        from ..core.mcp_client import McpClient

        client = McpClient(started["port"])
        ok, text = await client.tool(
            "store_query", {"nl_query": body.question, "sql_query": body.sql}
        )
        return {"ok": ok, "detail": text[:400]}
