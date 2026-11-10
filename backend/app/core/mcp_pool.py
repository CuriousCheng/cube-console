"""MCP 池：按需启动 wren serve mcp，容量有限，最久没用的先停。

一个项目 = 一个 MCP 进程（Wren 的限制）。
池子容量来自 config.json 的 pool_size（默认 3）。
"""

from __future__ import annotations

import asyncio
import socket
import sys
import time
from pathlib import Path

from ..config import DEFAULT_TRINO_CATALOG
from . import wren_project

WREN_BIN = Path(sys.executable).parent / "wren"
PORT_START = 9100
PORT_END = 9199


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


class McpPool:
    def __init__(self) -> None:
        # name -> {"proc": Process, "port": int, "last_used": float, "started_at": float}
        self.items: dict[str, dict] = {}
        self._lock = asyncio.Lock()

    # ── 查询 ──────────────────────────────────────
    def status(self, name: str) -> dict:
        it = self.items.get(name)
        if not it:
            return {"running": False, "port": None, "uptime": None, "last_used": None}
        proc = it["proc"]
        alive = proc.returncode is None
        return {
            "running": alive,
            "port": it["port"] if alive else None,
            "uptime": int(time.time() - it["started_at"]) if alive else None,
            "last_used": int(time.time() - it["last_used"]),
        }

    def snapshot(self) -> dict:
        return {name: self.status(name) for name in self.items}

    # ── 启动 ──────────────────────────────────────
    def _alloc_port(self) -> int:
        used = {it["port"] for it in self.items.values()}
        for p in range(PORT_START, PORT_END + 1):
            if p not in used and _port_free(p):
                return p
        raise RuntimeError("没有空闲端口了")

    async def _spawn(self, name: str) -> dict:
        d = wren_project.project_dir(name)
        if not d.exists():
            raise FileNotFoundError(f"项目 {name} 不存在")

        # 启动前必须有一次成功编译（模型可能刚改过）
        rc, out = await wren_project._run(["context", "build"], d)
        if rc != 0:
            raise RuntimeError(f"编译失败，先修好模型：{out[-300:]}")

        port = self._alloc_port()
        proc = await asyncio.create_subprocess_exec(
            str(WREN_BIN),
            "serve",
            "mcp",
            "--transport",
            "http",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--allow-write",
            cwd=str(d),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )

        # 等端口起来（最多 20 秒）
        for _ in range(40):
            await asyncio.sleep(0.5)
            if proc.returncode is not None:
                raise RuntimeError(f"MCP 启动即退出（返回码 {proc.returncode}），先确认项目能 build")
            if not _port_free(port):
                break
        else:
            proc.terminate()
            raise RuntimeError("MCP 20 秒内没起来")

        now = time.time()
        self.items[name] = {
            "proc": proc,
            "port": port,
            "last_used": now,
            "started_at": now,
        }
        return {"name": name, "port": port}

    async def _stop(self, name: str) -> None:
        it = self.items.pop(name, None)
        if not it:
            return
        proc = it["proc"]
        try:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                proc.kill()
        except ProcessLookupError:
            pass

    # ── 对外 ──────────────────────────────────────
    async def ensure(self, name: str, capacity: int = 3) -> dict:
        """保证项目在跑，返回 {port, started}。池满时踢掉最久没用的。"""
        async with self._lock:
            it = self.items.get(name)
            if it and it["proc"].returncode is None:
                it["last_used"] = time.time()
                return {"port": it["port"], "started": False}

            # 清掉死掉的条目
            dead = [n for n, v in self.items.items() if v["proc"].returncode is not None]
            for n in dead:
                self.items.pop(n, None)

            # 池满 → 踢最久没用过的
            evicted = None
            while len(self.items) >= max(1, capacity):
                victim = min(self.items.items(), key=lambda kv: kv[1]["last_used"])[0]
                if victim == name:
                    break
                await self._stop(victim)
                evicted = victim

            started = await self._spawn(name)
            return {"port": started["port"], "started": True, "evicted": evicted}

    async def stop(self, name: str) -> None:
        async with self._lock:
            await self._stop(name)

    async def reap(self, idle_minutes: int) -> list[str]:
        """停掉长时间没人用的。"""
        if idle_minutes <= 0:
            return []
        cutoff = time.time() - idle_minutes * 60
        stopped = []
        async with self._lock:
            for name, it in list(self.items.items()):
                if it["last_used"] < cutoff:
                    await self._stop(name)
                    stopped.append(name)
        return stopped

    async def stop_all(self) -> None:
        async with self._lock:
            for name in list(self.items):
                await self._stop(name)


pool = McpPool()
