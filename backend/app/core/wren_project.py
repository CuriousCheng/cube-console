"""Wren 项目的创建/删除/编译。

一个项目 = data/projects/<名字>/ 下的标准 Wren 目录。
每个项目配一个独立的 Wren profile（console-<项目名>），
带默认 catalog / schema，避免多项目互相覆盖。
"""

from __future__ import annotations

import asyncio
import re
import shutil
import sys
from pathlib import Path

import yaml

from ..config import PROJECTS_DIR, TRINO_HOST, TRINO_PORT, TRINO_SCHEMA

WREN_BIN = Path(sys.executable).parent / "wren"
PROFILES_FILE = Path.home() / ".wren" / "profiles.yml"


def safe_name(name: str) -> str:
    s = "".join(c if c.isalnum() or c in "-_" else "_" for c in name).strip("_")
    if not s:
        raise ValueError("项目名不能全是特殊字符")
    return s[:50]


def profile_name(project: str) -> str:
    # profile 名也要干净，中文会被 wren 接受但 shell 里麻烦
    base = safe_name(project)
    if re.search(r"[^\x00-\x7F]", base):
        base = "p" + str(abs(hash(project)) % 10**8)
    return f"console-{base}"


def _check_bin() -> None:
    if not WREN_BIN.exists():
        raise RuntimeError(f"找不到 wren 命令：{WREN_BIN}")


async def _run(args: list[str], cwd: Path) -> tuple[int, str]:
    _check_bin()
    proc = await asyncio.create_subprocess_exec(
        str(WREN_BIN),
        *args,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    out, _ = await proc.communicate()
    return proc.returncode, out.decode(errors="replace")


def write_profile(name: str, catalog: str, schema: str) -> None:
    PROFILES_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    if PROFILES_FILE.exists():
        data = yaml.safe_load(PROFILES_FILE.read_text("utf-8")) or {}
    data.setdefault("profiles", {})
    data["profiles"][name] = {
        "datasource": "trino",
        "host": TRINO_HOST,
        "port": TRINO_PORT,
        "user": "console",
        "catalog": catalog,
        "schema": schema,
    }
    data.setdefault("active", name)
    PROFILES_FILE.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), "utf-8")


def project_dir(name: str) -> Path:
    return PROJECTS_DIR / safe_name(name)


def list_projects() -> list[str]:
    if not PROJECTS_DIR.exists():
        return []
    return sorted(p.name for p in PROJECTS_DIR.iterdir() if p.is_dir())


async def create(name: str, catalog: str, schema: str = TRINO_SCHEMA) -> dict:
    d = project_dir(name)
    if d.exists():
        raise FileExistsError(f"项目 {d.name} 已存在")

    d.mkdir(parents=True)
    rc, out = await _run(["context", "init"], d)
    if rc != 0:
        shutil.rmtree(d, ignore_errors=True)
        raise RuntimeError(f"wren context init 失败：{out[-400:]}")

    pname = profile_name(name)
    write_profile(pname, catalog, schema)

    rc, out = await _run(["context", "set-profile", pname], d)
    if rc != 0:
        shutil.rmtree(d, ignore_errors=True)
        raise RuntimeError(f"绑定 profile 失败：{out[-400:]}")

    # 删掉模板自带的示例
    shutil.rmtree(d / "models" / "example", ignore_errors=True)
    shutil.rmtree(d / "views" / "example_view", ignore_errors=True)

    rc, out = await _run(["context", "build"], d)
    if rc != 0:
        raise RuntimeError(f"首次编译失败：{out[-400:]}")

    return {"name": d.name, "path": str(d), "profile": pname}


def delete(name: str) -> None:
    d = project_dir(name)
    if d.exists():
        shutil.rmtree(d)

    # 顺手清掉 profile
    if PROFILES_FILE.exists():
        data = yaml.safe_load(PROFILES_FILE.read_text("utf-8")) or {}
        profs = data.get("profiles", {})
        profs.pop(profile_name(name), None)
        PROFILES_FILE.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), "utf-8")


async def build(name: str) -> dict:
    rc, out = await _run(["context", "build"], project_dir(name))
    return {"ok": rc == 0, "output": out[-600:]}


async def memory_index(name: str) -> dict:
    """给业务建向量索引（表结构 + 历史问答）。"""
    rc, out = await _run(["memory", "index"], project_dir(name))
    return {"ok": rc == 0, "output": out[-800:]}


def memory_files(name: str) -> list[dict]:
    """knowledge/sql 下存的历史问答。"""
    d = project_dir(name) / "knowledge" / "sql"
    if not d.exists():
        return []
    out = []
    for p in sorted(d.glob("*.md")):
        text = p.read_text("utf-8", errors="replace")
        title = next((ln.lstrip("# -").strip() for ln in text.splitlines() if ln.strip()), p.name)
        out.append({"file": p.name, "title": title[:90], "size": p.stat().st_size})
    return out


def models_of(name: str) -> list[str]:
    d = project_dir(name) / "models"
    if not d.exists():
        return []
    return sorted(p.name for p in d.iterdir() if p.is_dir())
