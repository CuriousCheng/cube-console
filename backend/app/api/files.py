"""业务（= Wren 项目目录）里的文件读写。

一个业务长这样：

    data/projects/销售分析/
    ├── wren_project.yml
    ├── models/<表名>/metadata.yml
    ├── relationships.yml
    ├── cubes/*.yml
    ├── knowledge/
    │   ├── knowledge.yml
    │   ├── rules/*.md       业务规则
    │   └── sql/*.md         记忆（历史问答）
    └── views/*.yml

这里提供通用文本文件接口，让界面能编辑这些内容。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import Depends, HTTPException
from pydantic import BaseModel

from ..core.wren_project import project_dir

ALLOWED_SUFFIX = {".yml", ".yaml", ".md", ".txt", ".json"}


def _safe(project: str, rel: str) -> Path:
    base = project_dir(project).resolve()
    if not base.exists():
        raise HTTPException(404, "业务不存在")
    target = (base / rel).resolve()
    if not str(target).startswith(str(base)):
        raise HTTPException(400, "路径越界")
    if target.suffix not in ALLOWED_SUFFIX:
        raise HTTPException(400, f"只能编辑 {'/'.join(sorted(ALLOWED_SUFFIX))} 文件")
    return target


class FileIn(BaseModel):
    path: str
    text: str


def register(app, current_user, require) -> None:
    @app.get("/api/projects/{name}/files")
    async def list_files(name: str, user: dict = Depends(current_user)) -> dict:
        base = project_dir(name)
        if not base.exists():
            raise HTTPException(404, "业务不存在")
        items = []
        for p in sorted(base.rglob("*")):
            if p.is_file() and p.suffix in ALLOWED_SUFFIX:
                rel = str(p.relative_to(base))
                if rel.startswith("target/"):
                    continue
                items.append({"path": rel, "size": p.stat().st_size})
        return {"items": items}

    @app.get("/api/projects/{name}/file")
    async def read_file(
        name: str, path: str, user: dict = Depends(current_user)
    ) -> dict:
        p = _safe(name, path)
        if not p.exists():
            return {"ok": True, "exists": False, "text": ""}
        return {"ok": True, "exists": True, "text": p.read_text("utf-8")}

    @app.put("/api/projects/{name}/file")
    async def write_file(
        name: str, body: FileIn, user: dict = Depends(require("editor"))
    ) -> dict:
        p = _safe(name, body.path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body.text, "utf-8")
        return {"ok": True}

    @app.delete("/api/projects/{name}/file")
    async def delete_file(
        name: str, path: str, user: dict = Depends(require("editor"))
    ) -> dict:
        p = _safe(name, path)
        p.unlink(missing_ok=True)
        return {"ok": True}
