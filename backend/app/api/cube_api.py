"""Cube 集成：读 cube 元数据、把选中的表组合成一个业务视图（view）。"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import re
import time
from pathlib import Path

import httpx
import yaml
from fastapi import Depends, HTTPException
from pydantic import BaseModel

from .. import crypto, llm, store
from ..config import DEFAULTS

CUBE_URL = os.getenv("CUBE_URL", "http://127.0.0.1:4000").rstrip("/")
CUBE_CONF = Path(os.getenv("CUBE_CONF", "") or (Path.home() / "cube" / "conf"))
CUBES_FILE = CUBE_CONF / "model" / "cubes" / "all.yml"


def _load_cubes() -> dict:
    if not CUBES_FILE.exists():
        raise HTTPException(404, f"找不到模型文件：{CUBES_FILE}")
    data = yaml.safe_load(CUBES_FILE.read_text("utf-8")) or {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("cubes", [])
    return data


def _save_cubes(data: dict) -> None:
    CUBES_FILE.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), "utf-8"
    )


def _find_cube(data: dict, name: str) -> dict:
    for c in data.get("cubes", []):
        if c.get("name") == name:
            return c
    raise HTTPException(404, f"没有这个 cube：{name}")


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


class JoinIn(BaseModel):
    """在 cube `cube` 里定义一条指向 `target` 的 join。"""
    cube: str
    target: str
    from_column: str
    to_column: str
    relationship: str = "many_to_one"


class MemberIn(BaseModel):
    name: str
    title: str = ""
    description: str = ""
    type: str = ""
    sql: str = ""
    primary_key: bool = False
    deleted: bool = False


class FieldsIn(BaseModel):
    description: str = ""
    measures: list[MemberIn] = []
    dimensions: list[MemberIn] = []


def _hdr() -> dict:
    return {"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"}


def _build_query(body: "QueryIn") -> dict:
    query: dict = {"measures": body.measures, "dimensions": body.dimensions}
    if body.time_dimension:
        td = body.time_dimension
        if ":" in td:
            dim, gran = td.split(":", 1)
        else:
            dim, gran = td, body.granularity
        query["timeDimensions"] = [{"dimension": dim, "granularity": gran}]
    return query


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
        # 视图里成员名不能重复：先到先得，后面的表排除已被占用的
        try:
            data = _load_cubes()
            members = {
                c.get("name"): [
                    m.get("name")
                    for m in (c.get("measures") or []) + (c.get("dimensions") or [])
                ]
                for c in data.get("cubes", [])
            }
        except Exception:  # noqa: BLE001
            members = {}

        claimed: set = set()
        for cb in body.cubes:
            names = members.get(cb) or []
            lines.append(f"      - join_path: {cb}")
            lines.append('        includes: "*"')
            dup = [n for n in names if n in claimed]
            if dup:
                lines.append("        excludes:")
                for n in dup:
                    lines.append(f"          - {n}")
            elif not names:
                # 拿不到成员清单时，兜底排除最常见的冲突项
                lines.append("        excludes:")
                for n in ("id", "count"):
                    lines.append(f"          - {n}")
            claimed.update(names)

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
        query = _build_query(body)
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
        return {"ok": True, "columns": cols, "rows": rows[: body.limit]}

    @app.post("/api/cube/sql")
    async def cube_sql(body: QueryIn, user: dict = Depends(current_user)) -> dict:
        query = _build_query(body)
        try:
            async with httpx.AsyncClient(timeout=120) as c:
                r = await c.post(
                    f"{CUBE_URL}/cubejs-api/v1/sql", headers=_hdr(), json={"query": query}
                )
                data = r.json()
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"生成 SQL 失败：{e}") from e

        if r.status_code >= 400:
            return {"ok": False, "error": data.get("error") or str(data)[:300]}

        # Cube 返回 {"sql": {"sql": ["SELECT ...", [参数]], ...}}
        s = data.get("sql") or {}
        arr = s.get("sql") if isinstance(s, dict) else None
        text = ""
        if isinstance(arr, list) and arr:
            text = str(arr[0])
        elif isinstance(arr, str):
            text = arr
        return {"ok": True, "sql": text}

    # ── 表关系（joins）──────────────────────────────
    @app.get("/api/cube/joins")
    async def list_joins(user: dict = Depends(current_user)) -> dict:
        data = _load_cubes()
        items = []
        for c in data.get("cubes", []):
            for j in c.get("joins") or []:
                items.append(
                    {
                        "cube": c.get("name"),
                        "name": j.get("name"),
                        "sql": j.get("sql"),
                        "relationship": j.get("relationship"),
                    }
                )
        return {"ok": True, "items": items}

    @app.post("/api/cube/join")
    async def add_join(body: JoinIn, user: dict = Depends(require("editor"))) -> dict:
        if body.cube == body.target:
            raise HTTPException(400, "不能和自己关联")
        data = _load_cubes()
        cube = _find_cube(data, body.cube)
        _find_cube(data, body.target)

        joins = cube.get("joins") or []
        if any(j.get("name") == body.target for j in joins):
            raise HTTPException(400, f"{body.cube} 里已经有指向 {body.target} 的关系")

        joins.append(
            {
                "name": body.target,
                "sql": f"{{CUBE}}.{body.from_column} = {{{body.target}}}.{body.to_column}",
                "relationship": body.relationship,
            }
        )
        cube["joins"] = joins
        _save_cubes(data)
        return {"ok": True, "cube": body.cube, "joins": len(joins)}

    @app.delete("/api/cube/join")
    async def del_join(
        cube: str, name: str, user: dict = Depends(require("editor"))
    ) -> dict:
        data = _load_cubes()
        c = _find_cube(data, cube)
        joins = [j for j in (c.get("joins") or []) if j.get("name") != name]
        if joins:
            c["joins"] = joins
        else:
            c.pop("joins", None)
        _save_cubes(data)
        return {"ok": True}

    # ── 字段定义（表说明 / 显示名 / 说明 / 类型）────────
    @app.get("/api/cube/cube/{name}/fields")
    async def get_fields(name: str, user: dict = Depends(current_user)) -> dict:
        data = _load_cubes()
        c = _find_cube(data, name)
        return {
            "ok": True,
            "data": {
                "name": c.get("name"),
                "sql_table": c.get("sql_table"),
                "description": c.get("description") or "",
                "measures": [
                    {
                        "name": m.get("name"),
                        "title": m.get("title") or "",
                        "description": m.get("description") or "",
                        "type": m.get("type") or "",
                        "sql": m.get("sql") or "",
                    }
                    for m in (c.get("measures") or [])
                ],
                "dimensions": [
                    {
                        "name": d.get("name"),
                        "title": d.get("title") or "",
                        "description": d.get("description") or "",
                        "type": d.get("type") or "",
                        "primary_key": bool(d.get("primary_key")),
                    }
                    for d in (c.get("dimensions") or [])
                ],
            },
        }

    @app.put("/api/cube/cube/{name}/fields")
    async def put_fields(
        name: str, body: FieldsIn, user: dict = Depends(require("editor"))
    ) -> dict:
        data = _load_cubes()
        c = _find_cube(data, name)

        if body.description:
            c["description"] = body.description
        else:
            c.pop("description", None)

        def apply(m: dict, upd: MemberIn) -> None:
            if upd.title:
                m["title"] = upd.title
            else:
                m.pop("title", None)
            if upd.description:
                m["description"] = upd.description
            else:
                m.pop("description", None)
            if upd.type:
                m["type"] = upd.type
            if upd.sql:
                m["sql"] = upd.sql

        def merge(key: str, incoming: list, with_pk: bool) -> None:
            existing = c.get(key) or []
            known = {m.get("name") for m in existing}
            out = []
            for src in existing:
                upd = next((u for u in incoming if u.name == src.get("name")), None)
                if upd is not None and upd.deleted:
                    continue
                m = dict(src)
                if upd is not None:
                    apply(m, upd)
                    if with_pk:
                        if upd.primary_key:
                            m["primary_key"] = True
                        else:
                            m.pop("primary_key", None)
                out.append(m)

            # 新增的成员
            for upd in incoming:
                if upd.deleted or upd.name in known:
                    continue
                if not re.fullmatch(r"[a-z][a-z0-9_]{0,40}", upd.name):
                    raise HTTPException(400, f"名字不合法：{upd.name}（小写字母开头）")
                m: dict = {"name": upd.name}
                mtype = upd.type or "number"
                if mtype == "count":
                    m["type"] = "count"
                else:
                    if not upd.sql:
                        raise HTTPException(400, f"{upd.name} 需要写表达式，例如 SUM(total_amount)")
                    m["sql"] = upd.sql
                    m["type"] = mtype
                apply(m, upd)
                out.append(m)

            c[key] = out

        merge("measures", body.measures, False)
        merge("dimensions", body.dimensions, True)

        _save_cubes(data)
        return {"ok": True}

    # ── 看 YAML 文件 ────────────────────────────────
    @app.get("/api/cube/files")
    async def list_files(user: dict = Depends(current_user)) -> dict:
        base = CUBE_CONF / "model"
        items = []
        if base.is_dir():
            for f in sorted(base.rglob("*.yml")):
                rel = f.relative_to(CUBE_CONF).as_posix()
                items.append({"path": rel, "size": f.stat().st_size})
        return {"ok": True, "items": items}

    @app.get("/api/cube/file")
    async def read_file(path: str, user: dict = Depends(current_user)) -> dict:
        target = (CUBE_CONF / path).resolve()
        if not str(target).startswith(str(CUBE_CONF.resolve())):
            raise HTTPException(400, "路径不合法")
        if not target.is_file():
            raise HTTPException(404, "文件不存在")
        return {"ok": True, "path": path, "text": target.read_text("utf-8")}

    # ── AI 提问：自然语言 → Cube 查询 ────────────────
    @app.post("/api/cube/ask")
    async def cube_ask(body: dict, user: dict = Depends(current_user)) -> dict:
        question = (body.get("question") or "").strip()
        if not question:
            raise HTTPException(400, "问题不能为空")

        cfg = store.read("config", DEFAULTS)
        ai = cfg.get("ai", {}) or {}
        key = crypto.decrypt(ai.get("api_key_enc", ""))
        if not ai.get("base_url") or not ai.get("model"):
            return {"ok": False, "stage": "config", "error": "还没配置 AI（设置 → 系统设置）"}

        data = _load_cubes()
        view_name = (body.get("view") or "").strip()
        scope: list[str] = []
        view_title = ""
        if view_name:
            scope, view_title = _cubes_of_view(view_name)
            if not scope:
                return {"ok": False, "stage": "view", "error": f"业务 {view_name} 里没有表"}

        head = f"当前业务：{view_title or view_name}。" if view_name else ""
        lines = [
            head,
            "可用的表和字段（格式：cube.字段 | 显示名 | 说明）：",
            "",
        ]
        for c in data.get("cubes", []):
            if c.get("public") is False:
                continue
            if scope and c.get("name") not in scope:
                continue
            nm = c.get("name")
            desc = c.get("description") or ""
            lines.append(f"[{nm}] {c.get('title') or ''} {desc}".rstrip())
            for m in (c.get("measures") or []):
                lines.append(
                    f"  度量 {nm}.{m.get('name')} | {m.get('title') or ''} | {m.get('description') or ''}"
                )
            for d in (c.get("dimensions") or []):
                lines.append(
                    f"  维度 {nm}.{d.get('name')} ({d.get('type')}) | {d.get('title') or ''} | {d.get('description') or ''}"
                )
            for j in (c.get("joins") or []):
                lines.append(f"  关联 {nm} → {j.get('name')}")
            lines.append("")

        rules = _rules_text()
        memories = _recall_memory(question)
        extra: list[str] = []
        if rules:
            extra.append("业务规则（必须遵守）：\n" + rules)
        if memories:
            mrows = []
            for m in memories:
                mrows.append(
                    "- 问："
                    + (m.get("nl") or "")
                    + " → 查询："
                    + json.dumps(m.get("query") or {}, ensure_ascii=False)
                )
            extra.append("历史相似问答（可参考字段选择）：\n" + "\n".join(mrows))

        prompt = "\n".join(lines) + "\n" + (("\n".join(extra) + "\n\n") if extra else "") + (
            "你是 Cube 查询助手。根据问题输出一个 JSON，不要解释、不要代码块。\n"
            '格式：{"measures":["cube.度量"],"dimensions":["cube.维度"],'
            '"timeDimensions":[{"dimension":"cube.时间字段","granularity":"month"}]}\n'
            "规则：\n"
            "- 字段名必须来自上面的清单，不能自己编\n"
            "- 只要数字就用 measures；要分组才加 dimensions\n"
            "- 问每月/趋势用 timeDimensions，granularity 取 day/week/month/quarter/year\n"
            "- 跨表时确认两表之间有关联，否则只用一张表\n"
            f"\n问题：{question}\nJSON:"
        )

        try:
            raw = await llm.chat(
                ai.get("protocol", "openai"),
                ai.get("base_url", ""),
                key,
                ai.get("model", ""),
                prompt,
                max_tokens=600,
            )
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "stage": "llm", "error": f"模型调用失败：{e}"}

        text = (raw or "").strip()
        text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
        found = re.search(r"\{.*\}", text, re.S)
        if not found:
            return {"ok": False, "stage": "parse", "error": "模型没返回 JSON", "raw": raw[:400]}
        try:
            q = json.loads(found.group(0))
        except Exception:  # noqa: BLE001
            return {"ok": False, "stage": "parse", "error": "JSON 解析失败", "raw": raw[:400]}

        query: dict = {
            "measures": q.get("measures") or [],
            "dimensions": q.get("dimensions") or [],
        }
        if q.get("timeDimensions"):
            query["timeDimensions"] = q["timeDimensions"]
        if not query["measures"] and not query["dimensions"]:
            return {"ok": False, "stage": "parse", "error": "模型没给出字段", "raw": raw[:400]}

        try:
            async with httpx.AsyncClient(timeout=180) as c:
                r = await c.post(
                    f"{CUBE_URL}/cubejs-api/v1/load",
                    headers=_hdr(),
                    json={"query": query, "queryType": "regular"},
                )
                res = r.json()
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "stage": "query", "error": f"查询失败：{e}"}

        if r.status_code >= 400:
            return {
                "ok": False,
                "stage": "query",
                "error": res.get("error") or str(res)[:300],
                "query": query,
            }

        rows = res.get("data") or []
        cols = list(rows[0].keys()) if rows else (query["measures"] + query["dimensions"])
        return {"ok": True, "query": query, "columns": cols, "rows": rows[:500]}

    # ── 单个 cube / view 的 YAML（可编辑）────────────
    @app.get("/api/cube/cube/{name}/yaml")
    async def get_cube_yaml(name: str, user: dict = Depends(current_user)) -> dict:
        data = _load_cubes()
        c = _find_cube(data, name)
        return {"ok": True, "text": yaml.safe_dump(c, allow_unicode=True, sort_keys=False)}

    @app.put("/api/cube/cube/{name}/yaml")
    async def put_cube_yaml(
        name: str, body: dict, user: dict = Depends(require("editor"))
    ) -> dict:
        text = (body or {}).get("text") or ""
        try:
            new = yaml.safe_load(text)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(400, f"YAML 解析失败：{e}") from e
        if not isinstance(new, dict):
            raise HTTPException(400, "内容必须是一个 cube 对象")
        if new.get("name") != name:
            raise HTTPException(400, f"name 必须是 {name}")

        data = _load_cubes()
        cubes = data.get("cubes", [])
        for i, c in enumerate(cubes):
            if c.get("name") == name:
                cubes[i] = new
                break
        else:
            raise HTTPException(404, f"没有这个 cube：{name}")
        _save_cubes(data)
        return {"ok": True}

    @app.get("/api/cube/view/{name}/yaml")
    async def get_view_yaml(name: str, user: dict = Depends(current_user)) -> dict:
        p = CUBE_CONF / "model" / "views" / f"{name}.yml"
        if not p.exists():
            raise HTTPException(404, "视图不存在")
        return {"ok": True, "text": p.read_text("utf-8")}

    @app.put("/api/cube/view/{name}/yaml")
    async def put_view_yaml(
        name: str, body: dict, user: dict = Depends(require("editor"))
    ) -> dict:
        text = (body or {}).get("text") or ""
        try:
            loaded = yaml.safe_load(text)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(400, f"YAML 解析失败：{e}") from e
        if not isinstance(loaded, dict) or not loaded.get("views"):
            raise HTTPException(400, "内容必须是 views: [...] 结构")
        p = CUBE_CONF / "model" / "views" / f"{name}.yml"
        p.write_text(text, "utf-8")
        return {"ok": True}

    # ── 只编辑 joins 的 YAML（关系专用）──────────────
    @app.get("/api/cube/joins/{cube}/yaml")
    async def get_joins_yaml(cube: str, user: dict = Depends(current_user)) -> dict:
        data = _load_cubes()
        c = _find_cube(data, cube)
        return {
            "ok": True,
            "text": yaml.safe_dump(
                {"joins": c.get("joins") or []}, allow_unicode=True, sort_keys=False
            ),
        }

    @app.put("/api/cube/joins/{cube}/yaml")
    async def put_joins_yaml(
        cube: str, body: dict, user: dict = Depends(require("editor"))
    ) -> dict:
        text = (body or {}).get("text") or ""
        try:
            loaded = yaml.safe_load(text)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(400, f"YAML 解析失败：{e}") from e

        if loaded in (None, {}):
            joins = []
        elif isinstance(loaded, dict) and isinstance(loaded.get("joins"), list):
            joins = loaded["joins"]
        else:
            raise HTTPException(400, "内容必须是 joins: [...] 结构")

        for j in joins:
            if not isinstance(j, dict) or not j.get("name"):
                raise HTTPException(400, "每条关系都要有 name")
            if not j.get("sql"):
                raise HTTPException(400, f"关系 {j.get('name')} 缺少 sql")

        data = _load_cubes()
        c = _find_cube(data, cube)
        if joins:
            c["joins"] = joins
        else:
            c.pop("joins", None)
        _save_cubes(data)
        return {"ok": True, "count": len(joins)}

    # ── 全部关系一份 YAML（跟 Wren 的 relationships.yml 一样）──
    @app.get("/api/cube/all-joins/yaml")
    async def get_all_joins_yaml(user: dict = Depends(current_user)) -> dict:
        data = _load_cubes()
        items = []
        for c in data.get("cubes", []):
            for j in c.get("joins") or []:
                items.append(
                    {
                        "cube": c.get("name"),
                        "name": j.get("name"),
                        "sql": j.get("sql"),
                        "relationship": j.get("relationship"),
                    }
                )
        return {
            "ok": True,
            "text": yaml.safe_dump({"joins": items}, allow_unicode=True, sort_keys=False),
        }

    @app.put("/api/cube/all-joins/yaml")
    async def put_all_joins_yaml(
        body: dict, user: dict = Depends(require("editor"))
    ) -> dict:
        text = (body or {}).get("text") or ""
        try:
            loaded = yaml.safe_load(text)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(400, f"YAML 解析失败：{e}") from e

        if loaded in (None, {}):
            items: list = []
        elif isinstance(loaded, dict) and isinstance(loaded.get("joins"), list):
            items = loaded["joins"]
        else:
            raise HTTPException(400, "内容必须是 joins: [...] 结构")

        data = _load_cubes()
        names = {c.get("name") for c in data.get("cubes", [])}

        grouped: dict[str, list] = {}
        for it in items:
            if not isinstance(it, dict):
                raise HTTPException(400, "每条关系必须是对象")
            cube = it.get("cube")
            if cube not in names:
                raise HTTPException(400, f"没有这个 cube：{cube}")
            if not it.get("name"):
                raise HTTPException(400, "每条关系都要有 name")
            if not it.get("sql"):
                raise HTTPException(400, f"关系 {it.get('name')} 缺少 sql")
            grouped.setdefault(cube, []).append(
                {
                    "name": it["name"],
                    "sql": it["sql"],
                    "relationship": it.get("relationship") or "many_to_one",
                }
            )

        for c in data.get("cubes", []):
            js = grouped.get(c.get("name"))
            if js:
                c["joins"] = js
            else:
                c.pop("joins", None)

        _save_cubes(data)
        return {"ok": True, "count": len(items)}

    # ── 从 Trino 重建模型（数据源变动后自动调用）──────
    @app.post("/api/cube/rebuild")
    async def rebuild_models(user: dict = Depends(require("editor"))) -> dict:
        from ..core import cube_models

        res = await cube_models.rebuild(CUBES_FILE)
        return res

    # ── 业务（view）明细：包含哪些表 ─────────────────
    @app.get("/api/cube/views/detail")
    async def views_detail(user: dict = Depends(current_user)) -> dict:
        d = CUBE_CONF / "model" / "views"
        items = []
        if d.is_dir():
            for f in sorted(d.glob("*.yml")):
                try:
                    loaded = yaml.safe_load(f.read_text("utf-8")) or {}
                except Exception:  # noqa: BLE001
                    continue
                for v in loaded.get("views") or []:
                    cubes = [
                        c.get("join_path")
                        for c in (v.get("cubes") or [])
                        if isinstance(c, dict) and c.get("join_path")
                    ]
                    items.append(
                        {
                            "name": v.get("name") or f.stem,
                            "title": v.get("title") or "",
                            "cubes": cubes,
                        }
                    )
        return {"ok": True, "items": items}


    def _cubes_of_view(view: str) -> tuple[list[str], str]:
        d = CUBE_CONF / "model" / "views"
        if d.is_dir():
            for f in d.glob("*.yml"):
                try:
                    loaded = yaml.safe_load(f.read_text("utf-8")) or {}
                except Exception:  # noqa: BLE001
                    continue
                for v in loaded.get("views") or []:
                    if (v.get("name") or f.stem) == view:
                        cubes = [
                            c.get("join_path")
                            for c in (v.get("cubes") or [])
                            if isinstance(c, dict) and c.get("join_path")
                        ]
                        return cubes, (v.get("title") or "")
        return [], ""

    # ── 编译 / 重载 ─────────────────────────────────
    @app.post("/api/cube/compile")
    async def compile_models(user: dict = Depends(require("editor"))) -> dict:
        """重建模型文件 + 重启 Cube 容器（生产模式靠它生效）。"""
        from ..core import cube_models

        rebuild = await cube_models.rebuild(CUBES_FILE)
        restarted = False
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "restart", "cube",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
            restarted = proc.returncode == 0
        except Exception:  # noqa: BLE001
            restarted = False

        # 等 Cube 恢复
        ready = False
        for _ in range(30):
            await asyncio.sleep(2)
            try:
                async with httpx.AsyncClient(timeout=5) as c:
                    r = await c.get(f"{CUBE_URL}/cubejs-api/v1/meta", headers=_hdr())
                    if r.status_code == 200:
                        ready = True
                        break
            except Exception:  # noqa: BLE001
                continue
        return {"ok": True, "rebuild": rebuild, "restarted": restarted, "ready": ready}

    # ── 知识（规则）与记忆（问答沉淀）──────────────────
    def _kdir(kind: str) -> Path:
        sub = "rules" if kind == "rules" else "sql"
        d = CUBE_CONF / "knowledge" / sub
        d.mkdir(parents=True, exist_ok=True)
        return d

    @app.get("/api/cube/knowledge")
    async def list_knowledge(user: dict = Depends(current_user)) -> dict:
        out = []
        for kind in ("rules", "sql"):
            d = _kdir(kind)
            for f in sorted(d.glob("*.md")):
                out.append(
                    {
                        "kind": kind,
                        "name": f.stem,
                        "file": f.name,
                        "size": f.stat().st_size,
                    }
                )
        return {"ok": True, "items": out}

    @app.get("/api/cube/knowledge/{kind}/{name}")
    async def read_knowledge(
        kind: str, name: str, user: dict = Depends(current_user)
    ) -> dict:
        if kind not in ("rules", "sql"):
            raise HTTPException(400, "kind 只能是 rules 或 sql")
        f = _kdir(kind) / f"{name}.md"
        if not f.exists():
            raise HTTPException(404, "文件不存在")
        return {"ok": True, "text": f.read_text("utf-8")}

    @app.put("/api/cube/knowledge/{kind}/{name}")
    async def write_knowledge(
        kind: str, name: str, body: dict, user: dict = Depends(require("editor"))
    ) -> dict:
        if kind not in ("rules", "sql"):
            raise HTTPException(400, "kind 只能是 rules 或 sql")
        if not re.fullmatch(r"[\w\u4e00-\u9fa5-]{1,40}", name):
            raise HTTPException(400, "文件名不合法")
        text = (body or {}).get("text") or ""
        (_kdir(kind) / f"{name}.md").write_text(text, "utf-8")
        return {"ok": True}

    @app.delete("/api/cube/knowledge/{kind}/{name}")
    async def del_knowledge(
        kind: str, name: str, user: dict = Depends(require("editor"))
    ) -> dict:
        if kind not in ("rules", "sql"):
            raise HTTPException(400, "kind 只能是 rules 或 sql")
        f = _kdir(kind) / f"{name}.md"
        if f.exists():
            f.unlink()
        return {"ok": True}

    @app.post("/api/cube/memory")
    async def store_memory(body: dict, user: dict = Depends(require("editor"))) -> dict:
        """把一次成功的问答存成记忆。"""
        question = (body.get("question") or "").strip()
        query = body.get("query") or {}
        if not question or not query:
            raise HTTPException(400, "需要 question 和 query")
        name = "m" + str(int(time.time() * 1000))
        d = _kdir("sql")
        front = {
            "nl": question,
            "query": query,
            "created_at": int(time.time()),
        }
        text = (
            "---\n"
            + yaml.safe_dump(front, allow_unicode=True, sort_keys=False)
            + "---\n\n"
            + question
            + "\n"
        )
        (d / f"{name}.md").write_text(text, "utf-8")
        return {"ok": True, "name": name}

    def _recall_memory(question: str, limit: int = 3) -> list[dict]:
        """简单关键词召回：按字符重叠打分，够用且不引入向量库。"""
        d = CUBE_CONF / "knowledge" / "sql"
        if not d.is_dir():
            return []
        q = set(question)
        scored = []
        for f in d.glob("*.md"):
            try:
                raw = f.read_text("utf-8")
            except Exception:  # noqa: BLE001
                continue
            meta = {}
            if raw.startswith("---"):
                parts = raw.split("---", 2)
                if len(parts) >= 3:
                    try:
                        meta = yaml.safe_load(parts[1]) or {}
                    except Exception:  # noqa: BLE001
                        meta = {}
            nl = (meta.get("nl") or "").strip()
            if not nl:
                continue
            score = len(q & set(nl)) / max(1, len(set(nl)))
            if score > 0.15:
                scored.append((score, meta))
        scored.sort(key=lambda x: -x[0])
        return [m for _, m in scored[:limit]]

    def _rules_text() -> str:
        d = CUBE_CONF / "knowledge" / "rules"
        if not d.is_dir():
            return ""
        chunks = []
        for f in sorted(d.glob("*.md")):
            try:
                chunks.append(f.read_text("utf-8").strip())
            except Exception:  # noqa: BLE001
                continue
        return "\n\n".join(c for c in chunks if c)[:2000]

    # ── 预聚合（pre_aggregations）────────────────────
    @app.get("/api/cube/preagg/{cube}")
    async def get_preagg(cube: str, user: dict = Depends(current_user)) -> dict:
        data = _load_cubes()
        c = _find_cube(data, cube)
        return {
            "ok": True,
            "text": yaml.safe_dump(
                {"pre_aggregations": c.get("pre_aggregations") or []},
                allow_unicode=True,
                sort_keys=False,
            ),
        }

    @app.put("/api/cube/preagg/{cube}")
    async def put_preagg(
        cube: str, body: dict, user: dict = Depends(require("editor"))
    ) -> dict:
        text = (body or {}).get("text") or ""
        try:
            loaded = yaml.safe_load(text)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(400, f"YAML 解析失败：{e}") from e

        if loaded in (None, {}):
            items: list = []
        elif isinstance(loaded, dict) and isinstance(loaded.get("pre_aggregations"), list):
            items = loaded["pre_aggregations"]
        else:
            raise HTTPException(400, "内容必须是 pre_aggregations: [...] 结构")

        for p in items:
            if not isinstance(p, dict) or not p.get("name"):
                raise HTTPException(400, "每个预聚合都要有 name")
            if not p.get("measures"):
                raise HTTPException(400, f"预聚合 {p.get('name')} 缺少 measures")
            if not p.get("time_dimension"):
                raise HTTPException(400, f"预聚合 {p.get('name')} 缺少 time_dimension")

        data = _load_cubes()
        c = _find_cube(data, cube)
        if items:
            c["pre_aggregations"] = items
        else:
            c.pop("pre_aggregations", None)
        _save_cubes(data)
        return {"ok": True, "count": len(items)}
