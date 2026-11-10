"""文件存储：原子写 + 一把锁。

产品没有数据库，所有状态都是 data/ 下的 JSON。
单进程 + asyncio 锁 + os.replace 的原子替换，够 3-4 人用。
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .config import DATA_DIR

_lock = asyncio.Lock()


def path_of(name: str) -> Path:
    return DATA_DIR / f"{name}.json"


def read(name: str, default: Any = None) -> Any:
    p = path_of(name)
    if not p.exists():
        return default if default is not None else {}
    try:
        return json.loads(p.read_text("utf-8"))
    except json.JSONDecodeError:
        # 文件坏了不要让整个服务起不来
        return default if default is not None else {}


async def write(name: str, data: Any) -> None:
    async with _lock:
        p = path_of(name)
        p.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=p.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, p)  # 原子替换，不会写坏
        except Exception:
            Path(tmp).unlink(missing_ok=True)
            raise


def next_id(prefix: str, items: list[dict]) -> str:
    n = 1
    used = {i.get("id") for i in items}
    while f"{prefix}{n}" in used:
        n += 1
    return f"{prefix}{n}"
