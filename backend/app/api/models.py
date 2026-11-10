"""建模接口：拉表、生成模型、改模型、读写关系。"""

from __future__ import annotations

from fastapi import Depends, HTTPException
from pydantic import BaseModel

from .. import store
from ..core import modeling, trino_sql, wren_project


class GenIn(BaseModel):
    datasource_id: str
    schema_name: str
    table: str
    model_name: str | None = None
    description: str = ""
    primary_key: str | None = None


class ModelTextIn(BaseModel):
    text: str


class ModelJsonIn(BaseModel):
    data: dict


class CubeNewIn(BaseModel):
    name: str
    base_object: str


CUBE_DIR = "cubes"


def _cube_path(project: str, cube: str):
    from ..core.wren_project import project_dir

    return project_dir(project) / CUBE_DIR / cube / "metadata.yml"


def _model_columns(project: str, model: str) -> list[str]:
    import yaml as _yaml

    p = modeling.models_dir(project) / model / "metadata.yml"
    if not p.exists():
        return []
    data = _yaml.safe_load(p.read_text("utf-8")) or {}
    return [c.get("name") for c in (data.get("columns") or []) if c.get("name")]


def _validate_cube(project: str, cube: str, data: dict) -> None:
    if not isinstance(data, dict):
        raise ValueError("数据格式不对")
    if data.get("name") != cube:
        raise ValueError(f"name 必须是 {cube}")

    base = data.get("base_object")
    if not base:
        raise ValueError("base_object 不能为空")
    cols = _model_columns(project, base)
    if not cols:
        raise ValueError(f"base_object {base} 不在这个业务里（或者没有列）")

    measures = data.get("measures") or []
    if not isinstance(measures, list) or not measures:
        raise ValueError("至少要有一个度量")

    names = set()
    for m in measures:
        n = str((m or {}).get("name") or "").strip()
        if not n:
            raise ValueError("有度量没有名字")
        if not str(m.get("expression") or "").strip():
            raise ValueError(f"度量 {n} 缺少 expression")
        if n in cols:
            raise ValueError(
                f"度量名 {n} 和 {base} 的列同名，Wren 会报 circular dependency。换个名字，比如 sales_{n}"
            )
        if n in names:
            raise ValueError(f"度量名重复：{n}")
        names.add(n)

    for key in ("dimensions", "time_dimensions"):
        arr = data.get(key) or []
        if not isinstance(arr, list):
            raise ValueError(f"{key} 必须是数组")
        local = set()
        for d in arr:
            n = str((d or {}).get("name") or "").strip()
            if not n:
                raise ValueError(f"{key} 里有没名字的项")
            if not str(d.get("expression") or "").strip():
                raise ValueError(f"{key} 的 {n} 缺少 expression")
            if n in local:
                raise ValueError(f"{key} 名称重复：{n}")
            local.add(n)
        overlap = local & names
        if overlap:
            raise ValueError(f"{key} 和度量重名：{', '.join(overlap)}")


def _ds(ds_id: str) -> dict:
    items = store.read("datasources", {"items": []}).get("items", [])
    d = next((x for x in items if x["id"] == ds_id), None)
    if not d:
        raise HTTPException(404, "数据源不存在")
    return d


def register(app, current_user, require) -> None:
    @app.get("/api/datasources/{ds_id}/schemas")
    async def list_schemas(ds_id: str, user: dict = Depends(require("editor"))) -> dict:
        d = _ds(ds_id)
        try:
            items = await trino_sql.schemas(d["catalog"])
        except Exception as e:  # noqa: BLE001
            raise HTTPException(500, f"读取 schema 失败：{e}") from e
        return {"items": items}

    @app.get("/api/datasources/{ds_id}/tables")
    async def list_tables(
        ds_id: str, schema_name: str, user: dict = Depends(require("editor"))
    ) -> dict:
        d = _ds(ds_id)
        try:
            items = await trino_sql.tables(d["catalog"], schema_name)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(500, f"读取表失败：{e}") from e
        return {"items": items}

    @app.get("/api/datasources/{ds_id}/columns")
    async def list_columns(
        ds_id: str, schema_name: str, table: str, user: dict = Depends(require("editor"))
    ) -> dict:
        d = _ds(ds_id)
        try:
            items = await trino_sql.columns(d["catalog"], schema_name, table)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(500, f"读取列失败：{e}") from e
        return {"items": items}

    # ── 模型 ────────────────────────────────────────
    @app.get("/api/projects/{name}/models")
    async def list_models(name: str, user: dict = Depends(current_user)) -> dict:
        if name not in wren_project.list_projects():
            raise HTTPException(404, "项目不存在")
        return {"items": modeling.list_models(name)}

    @app.post("/api/projects/{name}/models")
    async def add_model(name: str, body: GenIn, user: dict = Depends(require("editor"))) -> dict:
        if name not in wren_project.list_projects():
            raise HTTPException(404, "项目不存在")
        d = _ds(body.datasource_id)
        try:
            cols = await trino_sql.columns(d["catalog"], body.schema_name, body.table)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(500, f"读取列失败：{e}") from e

        model_name = body.model_name or body.table
        modeling.generate_model(
            name,
            model_name,
            d["catalog"],
            body.schema_name,
            body.table,
            cols,
            body.description,
            body.primary_key,
        )
        return {"ok": True, "model": model_name, "columns": len(cols)}

    @app.get("/api/projects/{name}/models/{model}")
    async def get_model(name: str, model: str, user: dict = Depends(current_user)) -> dict:
        try:
            return {"ok": True, "text": modeling.read_model(name, model)}
        except FileNotFoundError as e:
            raise HTTPException(404, str(e)) from e

    @app.put("/api/projects/{name}/models/{model}")
    async def put_model(
        name: str, model: str, body: ModelTextIn, user: dict = Depends(require("editor"))
    ) -> dict:
        try:
            modeling.write_model(name, model, body.text)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(400, f"保存失败：{e}") from e
        return {"ok": True}

    @app.delete("/api/projects/{name}/models/{model}")
    async def del_model(name: str, model: str, user: dict = Depends(require("editor"))) -> dict:
        modeling.delete_model(name, model)
        return {"ok": True}

    # ── 结构化读写（给表单编辑器用）──────────────────
    @app.get("/api/projects/{name}/models/{model}/json")
    async def get_model_json(
        name: str, model: str, user: dict = Depends(current_user)
    ) -> dict:
        import yaml as _yaml

        try:
            text = modeling.read_model(name, model)
        except FileNotFoundError as e:
            raise HTTPException(404, str(e)) from e
        try:
            return {"ok": True, "data": _yaml.safe_load(text)}
        except Exception as e:  # noqa: BLE001
            raise HTTPException(400, f"YAML 解析失败：{e}") from e

    @app.put("/api/projects/{name}/models/{model}/json")
    async def put_model_json(
        name: str, model: str, body: ModelJsonIn, user: dict = Depends(require("editor"))
    ) -> dict:
        import yaml as _yaml

        data = body.data
        if not isinstance(data, dict):
            raise HTTPException(400, "数据格式不对")
        if data.get("name") != model:
            raise HTTPException(400, f"name 字段必须是 {model}")
        cols = data.get("columns")
        if not isinstance(cols, list) or not cols:
            raise HTTPException(400, "至少要有一列")

        seen = set()
        for c in cols:
            cn = (c or {}).get("name")
            if not cn:
                raise HTTPException(400, "有列没有名字")
            if cn in seen:
                raise HTTPException(400, f"列名重复：{cn}")
            seen.add(cn)

        text = _yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
        d = modeling.models_dir(name) / model
        d.mkdir(parents=True, exist_ok=True)
        (d / "metadata.yml").write_text(text, "utf-8")
        return {"ok": True}

    # ── 关系 ────────────────────────────────────────
    @app.get("/api/projects/{name}/relationships")
    async def get_rel(name: str, user: dict = Depends(current_user)) -> dict:
        return {"ok": True, "text": modeling.read_relationships(name)}

    @app.get("/api/projects/{name}/relationships/json")
    async def get_rel_json(name: str, user: dict = Depends(current_user)) -> dict:
        import yaml as _yaml

        if name not in wren_project.list_projects():
            raise HTTPException(404, "业务不存在")
        try:
            data = _yaml.safe_load(modeling.read_relationships(name)) or {}
        except Exception as e:  # noqa: BLE001
            raise HTTPException(400, f"YAML 解析失败：{e}") from e
        if not isinstance(data, dict):
            data = {}
        data.setdefault("relationships", [])
        return {"ok": True, "data": data}

    @app.put("/api/projects/{name}/relationships/json")
    async def put_rel_json(
        name: str, body: ModelJsonIn, user: dict = Depends(require("editor"))
    ) -> dict:
        import yaml as _yaml

        data = body.data or {}
        rels = data.get("relationships")
        if not isinstance(rels, list):
            raise HTTPException(400, "relationships 必须是数组")

        names = set()
        for r in rels:
            if not isinstance(r, dict):
                raise HTTPException(400, "关系格式不对")
            rn = str(r.get("name") or "").strip()
            if not rn:
                raise HTTPException(400, "每条关系都要有 name")
            if rn in names:
                raise HTTPException(400, f"关系名重复：{rn}")
            names.add(rn)
            models = r.get("models") or []
            if not isinstance(models, list) or len(models) != 2:
                raise HTTPException(400, f"关系 {rn} 必须正好关联两张表")
            if not str(r.get("condition") or "").strip():
                raise HTTPException(400, f"关系 {rn} 缺少 condition")

        text = _yaml.safe_dump({"relationships": rels}, allow_unicode=True, sort_keys=False)
        (wren_project.project_dir(name) / "relationships.yml").write_text(text, "utf-8")
        return {"ok": True, "count": len(rels)}


    @app.put("/api/projects/{name}/relationships")
    async def put_rel(
        name: str, body: ModelTextIn, user: dict = Depends(require("editor"))
    ) -> dict:
        try:
            modeling.write_relationships(name, body.text)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(400, f"保存失败：{e}") from e
        return {"ok": True}

    # ── 指标（cube）──────────────────────────────────
    @app.get("/api/projects/{name}/cubes/{cube}/json")
    async def get_cube_json(
        name: str, cube: str, user: dict = Depends(current_user)
    ) -> dict:
        import yaml as _yaml

        p = _cube_path(name, cube)
        if not p.exists():
            raise HTTPException(404, f"指标 {cube} 不存在")
        try:
            return {"ok": True, "data": _yaml.safe_load(p.read_text("utf-8")) or {}}
        except Exception as e:  # noqa: BLE001
            raise HTTPException(400, f"YAML 解析失败：{e}") from e

    @app.post("/api/projects/{name}/cubes")
    async def create_cube(
        name: str, body: CubeNewIn, user: dict = Depends(require("editor"))
    ) -> dict:
        import re

        import yaml as _yaml

        if name not in wren_project.list_projects():
            raise HTTPException(404, "业务不存在")
        cube = body.name.strip()
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,40}", cube):
            raise HTTPException(400, "指标名只能小写字母开头，含小写字母/数字/下划线")
        if body.base_object not in [m["name"] for m in modeling.list_models(name)]:
            raise HTTPException(400, f"基础表 {body.base_object} 不在这个业务里")

        p = _cube_path(name, cube)
        if p.exists():
            raise HTTPException(400, f"指标 {cube} 已存在")

        data = {
            "name": cube,
            "base_object": body.base_object,
            "measures": [{"name": "row_count", "expression": "COUNT(*)", "type": "BIGINT"}],
            "dimensions": [],
            "time_dimensions": [],
            "properties": {"description": ""},
        }
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(_yaml.safe_dump(data, allow_unicode=True, sort_keys=False), "utf-8")
        return {"ok": True, "cube": cube}

    @app.put("/api/projects/{name}/cubes/{cube}/json")
    async def put_cube_json(
        name: str, cube: str, body: ModelJsonIn, user: dict = Depends(require("editor"))
    ) -> dict:
        import yaml as _yaml

        if _cube_path(name, cube).parent.exists() is False:
            raise HTTPException(404, f"指标 {cube} 不存在")
        try:
            _validate_cube(name, cube, body.data)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

        p = _cube_path(name, cube)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            _yaml.safe_dump(body.data, allow_unicode=True, sort_keys=False), "utf-8"
        )
        return {"ok": True}

    @app.delete("/api/projects/{name}/cubes/{cube}")
    async def del_cube(name: str, cube: str, user: dict = Depends(require("editor"))) -> dict:
        import shutil

        d = _cube_path(name, cube).parent
        if d.exists():
            shutil.rmtree(d)
        return {"ok": True}

    # ── 编译 ────────────────────────────────────────
    @app.post("/api/projects/{name}/build")
    async def build(name: str, user: dict = Depends(require("editor"))) -> dict:
        r = await wren_project.build(name)
        return r
