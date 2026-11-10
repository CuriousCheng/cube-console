"""把数据源写成 Trino 的 catalog，并让它生效。

Trino 的 catalog 只在启动时加载。Trino 484 虽然支持 catalog.management=dynamic，
但对应的 REST 接口实测不可用（/v1/catalog 一律 404），所以这里用**重启**
来让新 catalog 生效。

本地部署：后端和 Trino 同机，直接调 bin/launcher restart。
Docker 部署：需要挂 docker.sock 或改用别的机制（见 README）。
"""

from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path

import httpx

from .config import CATALOG_DIR, CONNECTORS, TRINO_URL

# 例如 /home/cc/trino484/bin/launcher；不设则只能手动重启
TRINO_LAUNCHER = os.getenv("TRINO_LAUNCHER", "")


def catalog_name(raw: str) -> str:
    """Trino 的 catalog 名只允许小写字母、数字、下划线。"""
    cleaned = "".join(c if c.isalnum() or c == "_" else "_" for c in raw.lower())
    if not cleaned or not cleaned[0].isalpha():
        cleaned = f"ds_{cleaned}"
    return cleaned[:60]


def write_catalog(
    name: str,
    type_: str,
    host: str,
    port: int,
    database: str,
    user: str,
    password: str,
) -> str:
    if type_ not in CONNECTORS:
        raise ValueError(f"不支持的数据库类型：{type_}")

    connector, url_tpl = CONNECTORS[type_]
    url = url_tpl.format(host=host, port=port, database=database)
    safe_name = catalog_name(name)

    lines = [
        f"connector.name={connector}",
        f"connection-url={url}",
        f"connection-user={user}",
        f"connection-password={password}",
    ]
    (CATALOG_DIR / f"{safe_name}.properties").write_text("\n".join(lines) + "\n", "utf-8")
    return safe_name


async def trino_alive(timeout: float = 3.0) -> dict:
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.get(f"{TRINO_URL}/v1/info")
            j = r.json()
            return {
                "ok": not j.get("starting", True),
                "version": j.get("nodeVersion", {}).get("version"),
            }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


async def restart_trino(wait_seconds: int = 150) -> dict:
    """重启本地 Trino 并等它可用。"""
    if not TRINO_LAUNCHER:
        return {
            "ok": False,
            "error": "未配置 TRINO_LAUNCHER，无法自动重启 Trino。请手动执行 bin/launcher restart",
        }

    launcher = Path(TRINO_LAUNCHER)
    if not launcher.exists():
        return {"ok": False, "error": f"找不到 launcher：{launcher}"}

    if shutil.which("bash") is None:
        return {"ok": False, "error": "系统里没有 bash"}

    proc = await asyncio.create_subprocess_exec(
        "bash",
        str(launcher),
        "restart",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()

    # 等 /v1/info 返回 starting=false
    waited = 0
    while waited < wait_seconds:
        await asyncio.sleep(3)
        waited += 3
        info = await trino_alive(timeout=3)
        if info.get("ok"):
            return {"ok": True, "waited": waited, "version": info.get("version")}

    return {"ok": False, "error": f"重启后 {wait_seconds}s 内 Trino 没就绪"}


async def drop_catalog(name: str) -> dict:
    (CATALOG_DIR / f"{name}.properties").unlink(missing_ok=True)
    return {"ok": True}
