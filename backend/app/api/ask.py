"""查询业务：把自然语言变成「模型层 SQL」，交给 Wren → Trino 执行。"""

from __future__ import annotations

import json

from fastapi import Depends, HTTPException
from pydantic import BaseModel

from .. import crypto, llm, store
from ..config import DEFAULTS
from ..core import mcp_pool, wren_project
from ..core.mcp_client import McpClient

DIALECT = {
    "trino": "Trino",
    "mysql": "MySQL",
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "duckdb": "DuckDB",
    "sqlserver": "SQL Server",
}


class AskIn(BaseModel):
    project: str
    question: str
    remember: bool = False  # 成功后是否把这条问答存进记忆


class CubeIn(BaseModel):
    cube: str
    measures: list[str]
    dimensions: list[str] = []
    time_dimension: str | None = None  # 形如 "order_date:month"
    limit: int = 200


def build_prompt(
    mdl_text: str, question: str, dialect: str, examples: list[dict] | None = None
) -> str:
    shots = ""
    if examples:
        lines = []
        for i, m in enumerate(examples, 1):
            nl = m.get("nl_query") or m.get("text") or ""
            sql = m.get("sql_query") or ""
            if nl and sql:
                lines.append(f"{i}. 问题：{nl}\n   SQL：{sql}")
        if lines:
            shots = "\n下面是这个业务里问过的相似问题，写法优先参考：\n" + "\n".join(lines) + "\n"

    return f"""你是一个只输出 SQL 的助手。下面是可用的语义模型（MDL）：

{mdl_text}
{shots}
规则：
- 只输出一条 SELECT 语句，不要解释，不要 markdown 代码块，不要结尾分号
- FROM / JOIN 后面只能用 MDL 里 models[].name 的表名
- cubes 里的是「指标定义」（度量口径），**不是表**，绝对不能写成 FROM <cube名>
- 如果问题正好是某个 cube 的指标，就用它的 base_object 当表，照抄 measure 的 expression
- 使用 {dialect} 方言
- 中文列名必须用双引号，例如 AS "国家"

问题：{question}
SQL:"""


async def _ai_config() -> dict:
    cfg = store.read("config", DEFAULTS)
    ai = cfg.get("ai", {})
    key = crypto.decrypt(ai.get("api_key_enc", ""))
    if not ai.get("base_url"):
        raise HTTPException(400, "还没配置 AI 接口，请先到「设置 → 系统设置」填写")
    return {
        "protocol": ai.get("protocol", "openai"),
        "base_url": ai.get("base_url", ""),
        "model": ai.get("model", ""),
        "api_key": key,
    }


def register(app, current_user, require) -> None:
    @app.post("/api/ask")
    async def ask(body: AskIn, user: dict = Depends(current_user)) -> dict:
        name = body.project.strip()
        question = body.question.strip()
        if not name or not question:
            raise HTTPException(400, "项目和问题都不能为空")
        if name not in wren_project.list_projects():
            raise HTTPException(404, "项目不存在")

        cfg = store.read("config", DEFAULTS)
        try:
            started = await mcp_pool.pool.ensure(name, int(cfg.get("pool_size", 3)))
        except Exception as e:  # noqa: BLE001
            raise HTTPException(500, f"启动项目失败：{e}") from e

        client = McpClient(started["port"])

        ok, mdl_text = await client.tool("get_mdl")
        if not ok:
            raise HTTPException(500, f"读取语义模型失败：{mdl_text[:300]}")

        dialect = "Trino"
        try:
            md = json.loads(mdl_text)
            dialect = DIALECT.get(str(md.get("dataSource", "")).lower(), "Trino")
            mdl_for_prompt = json.dumps(md, ensure_ascii=False)
        except Exception:  # noqa: BLE001
            mdl_for_prompt = mdl_text

        ai = await _ai_config()

        # ① 先召回这个业务里问过的相似问题
        examples: list[dict] = []
        try:
            r_ok, r_text = await client.tool(
                "recall_queries", {"question": question, "limit": 3}
            )
            if r_ok:
                parsed = json.loads(r_text)
                matches = parsed.get("matches") if isinstance(parsed, dict) else parsed
                examples = [
                    m for m in (matches or [])
                    if isinstance(m, dict) and (m.get("sql_query") or m.get("sql"))
                ][:3]
                examples = [
                    {"nl_query": m.get("nl_query") or m.get("text") or "",
                     "sql_query": m.get("sql_query") or m.get("sql") or ""}
                    for m in examples
                ]
        except Exception:  # noqa: BLE001
            examples = []

        sql = await llm.chat(
            ai["protocol"], ai["base_url"], ai["api_key"], ai["model"],
            build_prompt(mdl_for_prompt, question, dialect, examples),
        )
        if not sql:
            return {"ok": False, "stage": "llm", "error": "模型返回空内容，换个问法"}

        check_ok, check_text = await client.tool("dry_run", {"sql": sql})
        if not check_ok:
            return {
                "ok": False,
                "stage": "dry_run",
                "sql": sql,
                "error": check_text[:800],
            }

        run_ok, run_text = await client.tool("run_sql", {"sql": sql})
        if not run_ok:
            return {"ok": False, "stage": "run_sql", "sql": sql, "error": run_text[:800]}

        # ② 成功了，按需把这条问答存进记忆
        remembered = False
        if body.remember:
            try:
                w_ok, _ = await client.tool(
                    "store_query", {"nl_query": question, "sql_query": sql}
                )
                remembered = w_ok
            except Exception:  # noqa: BLE001
                remembered = False

        try:
            data = json.loads(run_text)
        except Exception:  # noqa: BLE001
            return {"ok": True, "sql": sql, "raw": run_text,
                    "recalled": len(examples), "remembered": remembered}

        result = {
            "ok": True,
            "sql": sql,
            "data": data,
            "project": name,
            "recalled": len(examples),
            "remembered": remembered,
        }
        if user["role"] == "viewer" and not cfg.get("viewer_can_see_sql", False):
            result.pop("sql", None)
        return result

    @app.get("/api/projects/{name}/cubes")
    async def list_cubes(name: str, user: dict = Depends(current_user)) -> dict:
        if name not in wren_project.list_projects():
            raise HTTPException(404, "业务不存在")
        cfg = store.read("config", DEFAULTS)
        try:
            started = await mcp_pool.pool.ensure(name, int(cfg.get("pool_size", 3)))
        except Exception as e:  # noqa: BLE001
            raise HTTPException(500, f"启动业务失败：{e}") from e

        client = McpClient(started["port"])
        ok, text = await client.tool("list_cubes")
        if not ok:
            return {"ok": False, "error": text[:400], "cubes": []}
        try:
            return {"ok": True, "cubes": json.loads(text).get("cubes", [])}
        except Exception:  # noqa: BLE001
            return {"ok": False, "error": text[:400], "cubes": []}

    @app.post("/api/projects/{name}/cube")
    async def cube_query(
        name: str, body: CubeIn, user: dict = Depends(current_user)
    ) -> dict:
        if name not in wren_project.list_projects():
            raise HTTPException(404, "业务不存在")
        if not body.cube or not body.measures:
            raise HTTPException(400, "指标和度量都不能为空")

        cfg = store.read("config", DEFAULTS)
        try:
            started = await mcp_pool.pool.ensure(name, int(cfg.get("pool_size", 3)))
        except Exception as e:  # noqa: BLE001
            raise HTTPException(500, f"启动业务失败：{e}") from e

        client = McpClient(started["port"])
        base = {"cube": body.cube, "measures": body.measures}
        if body.dimensions:
            base["dimensions"] = body.dimensions
        if body.time_dimension:
            base["time_dimension"] = body.time_dimension

        # 先生成 SQL（只看不跑）
        sql = ""
        ok, text = await client.tool("query_cube", {**base, "sql_only": True})
        if ok:
            try:
                sql = json.loads(text).get("sql", "")
            except Exception:  # noqa: BLE001
                sql = ""

        ok, text = await client.tool("query_cube", {**base, "limit": body.limit})
        if not ok:
            return {"ok": False, "sql": sql, "error": text[:800]}

        try:
            data = json.loads(text)
        except Exception:  # noqa: BLE001
            return {"ok": True, "sql": sql, "raw": text}

        result = {"ok": True, "sql": sql, "data": data, "cube": body.cube}
        if user["role"] == "viewer" and not cfg.get("viewer_can_see_sql", False):
            result.pop("sql", None)
        return result

    @app.get("/api/projects/{name}/tables")
    async def project_tables(name: str, user: dict = Depends(require("editor"))) -> dict:
        """给建模用：列出 Trino 里所有 catalog/schema/table。"""
        import httpx

        from ..config import TRINO_URL
        from ..core.mcp_client import McpClient as _M  # noqa: F401

        try:
            async with httpx.AsyncClient(timeout=20) as c:
                r = await c.post(
                    f"{TRINO_URL}/v1/statement",
                    content="SHOW CATALOGS",
                    headers={"X-Trino-User": "console", "Content-Type": "text/plain"},
                )
                return {"ok": True, "note": "tables 接口待完善", "raw": r.text[:400]}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}
