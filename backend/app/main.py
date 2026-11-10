"""Wren Console 后端 v0.1

已实现：登录、数据源 CRUD、测试连接、写 Trino catalog。
下一步：项目 CRUD、建模向导、MCP 池、问答。
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import auth, crypto, dbcheck, llm, store, trino_admin, users_api
from .config import DEFAULTS, TRINO_URL

app = FastAPI(title="Wren Console", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 同源部署时无所谓；分开部署再收紧
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 依赖：当前用户 ──────────────────────────────────────


async def current_user(authorization: str = Header(default="")) -> dict:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "未登录")
    payload = auth.parse_token(authorization[7:])
    if not payload:
        raise HTTPException(401, "登录已过期")
    user = auth.find_user(payload["u"])
    if not user:
        raise HTTPException(401, "用户不存在")
    return user


def require(role: str):
    async def _dep(user: dict = Depends(current_user)) -> dict:
        if not auth.can(user["role"], role):
            raise HTTPException(403, f"需要 {role} 权限")
        return user

    return _dep


# ── 启动 ────────────────────────────────────────────────


@app.on_event("startup")
async def on_startup() -> None:
    await auth.bootstrap()
    # config.json 不存在就写默认值
    if not store.path_of("config").exists():
        await store.write("config", DEFAULTS)
    # 后台清理长时间没人用的 MCP
    # 启动 MCP 网关（对外给外部 AI 用）
# ── 健康 ────────────────────────────────────────────────


@app.get("/api/health")
async def health() -> dict:
    return {
        "ok": True,
        "version": "0.1.0",
        "trino": await trino_admin.trino_alive(),
    }


# ── 登录 ────────────────────────────────────────────────


class LoginIn(BaseModel):
    name: str
    password: str


@app.post("/api/login")
async def login(body: LoginIn) -> dict:
    user = auth.find_by_name(body.name)
    if not user or not auth.verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "账号或密码不对")
    return {
        "token": auth.make_token(user["id"], user["role"]),
        "user": {"id": user["id"], "name": user["name"], "role": user["role"]},
    }


@app.get("/api/me")
async def me(user: dict = Depends(current_user)) -> dict:
    return {"id": user["id"], "name": user["name"], "role": user["role"]}


# ── 全局配置 ────────────────────────────────────────────


class ConfigIn(BaseModel):
    pool_size: int | None = None
    ask_concurrency: int | None = None
    viewer_can_see_sql: bool | None = None
    idle_stop_minutes: int | None = None


@app.get("/api/config")
async def get_config(user: dict = Depends(require("admin"))) -> dict:
    cfg = store.read("config", DEFAULTS)
    ai = cfg.get("ai", {})
    return {
        **{k: cfg.get(k, DEFAULTS.get(k)) for k in ("pool_size", "ask_concurrency", "viewer_can_see_sql", "idle_stop_minutes")},
        "ai": {
            "protocol": ai.get("protocol"),
            "base_url": ai.get("base_url"),
            "model": ai.get("model"),
            "has_key": bool(ai.get("api_key_enc")),
        },
    }


@app.put("/api/config")
async def put_config(body: ConfigIn, user: dict = Depends(require("admin"))) -> dict:
    cfg = store.read("config", dict(DEFAULTS))
    for k, v in body.model_dump(exclude_none=True).items():
        cfg[k] = v
    await store.write("config", cfg)
    return {"ok": True}


# ── AI 配置 ─────────────────────────────────────────────


class AiIn(BaseModel):
    protocol: str | None = None  # openai | anthropic
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None  # 空字符串表示不改


@app.get("/api/ai")
async def get_ai(user: dict = Depends(require("admin"))) -> dict:
    cfg = store.read("config", DEFAULTS)
    ai = cfg.get("ai", {})
    return {
        "protocol": ai.get("protocol", "openai"),
        "base_url": ai.get("base_url", ""),
        "model": ai.get("model", ""),
        "has_key": bool(ai.get("api_key_enc")),
    }


@app.put("/api/ai")
async def put_ai(body: AiIn, user: dict = Depends(require("admin"))) -> dict:
    cfg = store.read("config", dict(DEFAULTS))
    ai = cfg.setdefault("ai", dict(DEFAULTS["ai"]))
    if body.protocol is not None:
        ai["protocol"] = body.protocol
    if body.base_url is not None:
        ai["base_url"] = body.base_url.strip().rstrip("/")
    if body.model is not None:
        ai["model"] = body.model.strip()
    if body.api_key:
        ai["api_key_enc"] = crypto.encrypt(body.api_key)
    await store.write("config", cfg)
    return {"ok": True}


class AiTestIn(BaseModel):
    protocol: str
    base_url: str
    api_key: str = ""


@app.post("/api/ai/test")
async def test_ai(body: AiTestIn, user: dict = Depends(require("editor"))) -> dict:
    key = body.api_key
    if not key:
        # 前端没重新输入 key，就用已存的
        cfg = store.read("config", DEFAULTS)
        key = crypto.decrypt(cfg.get("ai", {}).get("api_key_enc", ""))
    return await llm.probe(body.protocol, body.base_url, key)


@app.post("/api/ai/test-saved")
async def test_ai_saved(user: dict = Depends(require("editor"))) -> dict:
    cfg = store.read("config", DEFAULTS)
    ai = cfg.get("ai", {})
    key = crypto.decrypt(ai.get("api_key_enc", ""))
    return await llm.probe(ai.get("protocol", "openai"), ai.get("base_url", ""), key)


# ── 数据源 ──────────────────────────────────────────────


class DataSourceIn(BaseModel):
    name: str
    type: str  # mysql | postgresql | sqlserver | mariadb
    host: str
    port: int
    database: str = ""
    user: str
    password: str


def _public(ds: dict) -> dict:
    """返回给前端时不给明文密码。"""
    return {
        "id": ds["id"],
        "name": ds["name"],
        "type": ds["type"],
        "host": ds["host"],
        "port": ds["port"],
        "database": ds.get("database", ""),
        "user": ds["user"],
        "catalog": ds.get("catalog"),
        "password_mask": crypto.mask(crypto.decrypt(ds.get("password_enc", ""))),
        "created_at": ds.get("created_at"),
        "last_test": ds.get("last_test"),
    }


@app.get("/api/datasources")
async def list_datasources(user: dict = Depends(require("editor"))) -> dict:
    items = store.read("datasources", {"items": []}).get("items", [])
    return {"items": [_public(d) for d in items]}


@app.post("/api/datasources")
async def create_datasource(body: DataSourceIn, user: dict = Depends(require("admin"))) -> dict:
    data = store.read("datasources", {"items": []})
    items = data.get("items", [])

    if any(d["name"] == body.name for d in items):
        raise HTTPException(400, "同名数据源已存在")

    ds_id = store.next_id("ds", items)
    catalog = trino_admin.write_catalog(
        body.name, body.type, body.host, body.port, body.database, body.user, body.password
    )
    reload_result = await trino_admin.restart_trino()

    item = {
        "id": ds_id,
        "name": body.name,
        "type": body.type,
        "host": body.host,
        "port": body.port,
        "database": body.database,
        "user": body.user,
        "password_enc": crypto.encrypt(body.password),
        "catalog": catalog,
        "created_at": int(time.time()),
        "last_test": None,
    }
    items.append(item)
    data["items"] = items
    await store.write("datasources", data)

    # 数据源变了：自动重建 Cube 模型
    try:
        from .core import cube_models

        rebuild = await cube_models.rebuild(
            Path(os.getenv("CUBE_CONF", str(Path.home() / "cube" / "conf")))
            / "model"
            / "cubes"
            / "all.yml"
        )
    except Exception as e:  # noqa: BLE001
        rebuild = {"ok": False, "error": str(e)[:200]}

    return {"ok": True, "item": _public(item), "reload": reload_result, "rebuild": rebuild}


@app.put("/api/datasources/{ds_id}")
async def update_datasource(
    ds_id: str, body: DataSourceIn, user: dict = Depends(require("admin"))
) -> dict:
    data = store.read("datasources", {"items": []})
    items = data.get("items", [])
    item = next((d for d in items if d["id"] == ds_id), None)
    if not item:
        raise HTTPException(404, "数据源不存在")

    item.update(
        {
            "name": body.name,
            "type": body.type,
            "host": body.host,
            "port": body.port,
            "database": body.database,
            "user": body.user,
            "password_enc": crypto.encrypt(body.password),
        }
    )
    item["catalog"] = trino_admin.write_catalog(
        body.name, body.type, body.host, body.port, body.database, body.user, body.password
    )
    await trino_admin.restart_trino()
    await store.write("datasources", data)
    return {"ok": True, "item": _public(item)}


@app.delete("/api/datasources/{ds_id}")
async def delete_datasource(ds_id: str, user: dict = Depends(require("admin"))) -> dict:
    data = store.read("datasources", {"items": []})
    items = data.get("items", [])
    item = next((d for d in items if d["id"] == ds_id), None)
    if not item:
        raise HTTPException(404, "数据源不存在")

    if item.get("catalog"):
        await trino_admin.drop_catalog(item["catalog"])

    data["items"] = [d for d in items if d["id"] != ds_id]
    await store.write("datasources", data)

    # 删完要重启 Trino 让 catalog 下线，然后重建模型（消失的表会被移除）
    reload_result = await trino_admin.restart_trino()
    try:
        from .core import cube_models

        rebuild = await cube_models.rebuild(
            Path(os.getenv("CUBE_CONF", str(Path.home() / "cube" / "conf")))
            / "model"
            / "cubes"
            / "all.yml"
        )
    except Exception as e:  # noqa: BLE001
        rebuild = {"ok": False, "error": str(e)[:200]}

    return {"ok": True, "reload": reload_result, "rebuild": rebuild}


class TestIn(BaseModel):
    type: str
    host: str
    port: int
    database: str = ""
    user: str
    password: str


@app.post("/api/datasources/test")
async def test_datasource(body: TestIn, user: dict = Depends(require("editor"))) -> dict:
    return dbcheck.test_connection(
        body.type, body.host, body.port, body.database, body.user, body.password
    )


@app.post("/api/datasources/{ds_id}/test")
async def test_saved(ds_id: str, user: dict = Depends(require("editor"))) -> dict:
    data = store.read("datasources", {"items": []})
    item = next((d for d in data.get("items", []) if d["id"] == ds_id), None)
    if not item:
        raise HTTPException(404, "数据源不存在")

    result = dbcheck.test_connection(
        item["type"],
        item["host"],
        item["port"],
        item.get("database", ""),
        item["user"],
        crypto.decrypt(item.get("password_enc", "")),
    )
    item["last_test"] = {"at": int(time.time()), "ok": result.get("ok")}
    await store.write("datasources", data)
    return result


# ── 用户管理（实现在 users_api.py）──────────────────────

users_api.register(app, current_user, require)
# ── 项目 + MCP 池 ─────────────────────────────────────

from .api import cube_api as cube_api  # noqa: E402

cube_api.register(app, current_user, require)


# ── 托管前端静态文件（打包后不需要 node / vite）──────────
_WEB_DIR = Path(os.getenv("WEB_DIR", "") or (Path(__file__).resolve().parents[3] / "web"))
if _WEB_DIR.is_dir():
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=str(_WEB_DIR), html=True), name="web")
