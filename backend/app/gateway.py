"""MCP 网关：对外只暴露一个 MCP，内部按项目路由。

外部 AI（Claude / Cursor / 任何 MCP 客户端）只配这一个地址：

    http://<主机>:9300/mcp

它不需要知道底下有几个项目、几个数据库。

工具：
  list_projects()                 有哪些项目，各自绑哪个数据源、是否已启用
  get_project_schema(project)     某个项目的语义模型（MDL）
  ask(question, project="")       提问；不指定项目就报错并列出候选（让人来选）
"""

from __future__ import annotations

import json
import os

import httpx
from mcp.server.fastmcp import FastMCP

API = os.getenv("WC_API", "http://127.0.0.1:8000").rstrip("/")
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASSWORD", "")
PORT = int(os.getenv("GATEWAY_PORT", "9300"))

mcp = FastMCP(
    "wren-console",
    host="0.0.0.0",
    port=PORT,
    instructions=(
        "这是一个多项目的语义查询网关。"
        "先调用 list_projects 看有哪些项目，再调用 ask(question, project) 提问。"
        "不要猜项目名；如果 ask 报错说项目不存在，把候选项目告诉用户让他选。"
    ),
)

_token: str | None = None


async def _login(force: bool = False) -> str:
    global _token
    if _token and not force:
        return _token
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(f"{API}/api/login", json={"name": ADMIN_USER, "password": ADMIN_PASS})
        r.raise_for_status()
        _token = r.json()["token"]
    return _token


async def _call(method: str, path: str, body: dict | None = None) -> dict:
    for attempt in range(2):
        token = await _login(force=attempt > 0)
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=240) as c:
            r = await c.request(
                method, f"{API}{path}", json=body, headers=headers
            )
        if r.status_code == 401 and attempt == 0:
            continue
        try:
            return r.json()
        except Exception:  # noqa: BLE001
            return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:200]}"}
    return {"ok": False, "error": "网关登录失败"}


@mcp.tool()
async def list_projects() -> str:
    """列出所有可用的语义项目（项目 = 一套语义模型，被启用后才能被 AI 查询）。"""
    data = await _call("GET", "/api/projects")
    items = data.get("items", [])
    if not items:
        return "当前还没有任何项目。请先在 Wren Console 里创建项目。"
    lines = []
    for p in items:
        state = "已启用" if p.get("mcp", {}).get("running") else "未启用"
        lines.append(
            f"- {p['name']}｜数据源: {p.get('datasource') or '未绑定'}｜"
            f"模型数: {p.get('models', 0)}｜{state}"
        )
    return "可用项目：\n" + "\n".join(lines)


@mcp.tool()
async def get_project_schema(project: str) -> str:
    """读取某个项目的语义模型（表名、列名、关系、描述），用来写 SQL。"""
    data = await _call("GET", f"/api/projects/{project}/schema")
    if not data.get("ok"):
        return f"读取失败：{data.get('error') or data}"
    return data.get("mdl", "")


@mcp.tool()
async def ask(question: str, project: str = "") -> str:
    """在指定项目上提问，返回 SQL 和查询结果。

    project 必填。不知道选哪个就先调 list_projects。
    如果项目不存在，会返回候选列表，请让用户来选，不要自己换一个猜。
    """
    if not project:
        data = await _call("GET", "/api/projects")
        names = [p["name"] for p in data.get("items", [])]
        if not names:
            return "还没有任何项目，无法查询。"
        return (
            "必须指定 project 参数。可用项目：" + "、".join(names) + "。"
            "请让用户选择要查哪个项目。"
        )

    r = await _call("POST", "/api/ask", {"project": project, "question": question})
    if not r.get("ok"):
        err = r.get("error", "")
        if "项目不存在" in str(err) or "404" in str(err):
            data = await _call("GET", "/api/projects")
            names = [p["name"] for p in data.get("items", [])]
            return f"项目 {project} 不存在。候选：{'、'.join(names)}。请让用户重新选择。"
        return f"查询失败：{err}"

    out = []
    if r.get("sql"):
        out.append(f"SQL:\n{r['sql']}")
    data = r.get("data") or {}
    if data:
        cols = data.get("columns", [])
        rows = data.get("rows", [])
        out.append(f"结果（{data.get('row_count', len(rows))} 行）：")
        out.append(" | ".join(cols))
        for row in rows[:30]:
            out.append(" | ".join(str(row.get(c, "")) for c in cols))
        if len(rows) > 30:
            out.append(f"...（还有 {len(rows) - 30} 行）")
    return "\n".join(out) if out else json.dumps(r, ensure_ascii=False)[:1000]


if __name__ == "__main__":
    transport = os.getenv("GATEWAY_TRANSPORT", "streamable-http")
    mcp.run(transport=transport)
