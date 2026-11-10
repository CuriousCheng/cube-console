"""建模：从 Trino 拉表 → 生成 MDL → 读写关系。

一个 model = 项目里 models/<名字>/metadata.yml。
"""

from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from ..core.wren_project import project_dir

TYPE_MAP = {
    "boolean": "BOOLEAN",
    "tinyint": "TINYINT",
    "smallint": "SMALLINT",
    "integer": "INTEGER",
    "int": "INTEGER",
    "bigint": "BIGINT",
    "real": "FLOAT",
    "double": "DOUBLE",
    "decimal": "DECIMAL",
    "varchar": "VARCHAR",
    "char": "CHAR",
    "varbinary": "VARBINARY",
    "date": "DATE",
    "time": "TIME",
    "timestamp": "TIMESTAMP",
    "json": "JSON",
    "uuid": "UUID",
    "ipaddress": "IPADDRESS",
}


def trino_type_to_wren(t: str) -> str:
    base = (t or "").strip().lower().split("(")[0]
    if base.startswith("array"):
        return "VARCHAR"
    if base.startswith("map") or base.startswith("row"):
        return "VARCHAR"
    if base.startswith("decimal"):
        return "DECIMAL"
    return TYPE_MAP.get(base, "VARCHAR")


def models_dir(project: str) -> Path:
    return project_dir(project) / "models"


def list_models(project: str) -> list[dict]:
    d = models_dir(project)
    if not d.exists():
        return []
    out = []
    for p in sorted(d.iterdir()):
        if not p.is_dir():
            continue
        meta = p / "metadata.yml"
        info = {"name": p.name, "description": "", "columns": 0}
        if meta.exists():
            try:
                data = yaml.safe_load(meta.read_text("utf-8")) or {}
                info["description"] = (data.get("properties") or {}).get("description", "")
                info["columns"] = len(data.get("columns") or [])
                info["catalog"] = (data.get("table_reference") or {}).get("catalog")
                info["schema"] = (data.get("table_reference") or {}).get("schema")
                info["table"] = (data.get("table_reference") or {}).get("table")
            except Exception:  # noqa: BLE001
                pass
        out.append(info)
    return out


def read_model(project: str, name: str) -> str:
    p = models_dir(project) / name / "metadata.yml"
    if not p.exists():
        raise FileNotFoundError(f"模型 {name} 不存在")
    return p.read_text("utf-8")


def write_model(project: str, name: str, yml_text: str) -> None:
    data = yaml.safe_load(yml_text)
    if not isinstance(data, dict) or "name" not in data:
        raise ValueError("YAML 里必须有 name 字段")
    d = models_dir(project) / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "metadata.yml").write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), "utf-8"
    )


def generate_model(
    project: str,
    name: str,
    catalog: str,
    schema: str,
    table: str,
    columns: list[dict],
    description: str = "",
    primary_key: str | None = None,
) -> str:
    """按 Trino 的类型生成一个 metadata.yml 并落盘。返回 yml 文本。"""
    cols = []
    for c in columns:
        col = {
            "name": c["name"],
            "type": trino_type_to_wren(c.get("type", "")),
            "is_calculated": False,
            "not_null": False,
            "properties": {},
        }
        if c.get("comment"):
            col["properties"]["description"] = c["comment"]
        cols.append(col)

    pk = primary_key or next((c["name"] for c in cols if c["name"] == "id"), None)
    if pk:
        cols = [dict(c, is_primary_key=True, not_null=True) if c["name"] == pk else c for c in cols]

    data = {
        "name": name,
        "properties": {"description": description or f"{table} 表"},
        "table_reference": {"catalog": catalog, "schema": schema, "table": table},
        "columns": cols,
        "cached": False,
    }
    if pk:
        data["primary_key"] = pk

    text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    d = models_dir(project) / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "metadata.yml").write_text(text, "utf-8")
    return text


def delete_model(project: str, name: str) -> None:
    shutil.rmtree(models_dir(project) / name, ignore_errors=True)


def read_relationships(project: str) -> str:
    p = project_dir(project) / "relationships.yml"
    return p.read_text("utf-8") if p.exists() else "relationships: []\n"


def write_relationships(project: str, text: str) -> None:
    data = yaml.safe_load(text)
    if not isinstance(data, dict) or "relationships" not in data:
        raise ValueError("必须是 {relationships: [...]} 结构")
    (project_dir(project) / "relationships.yml").write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), "utf-8"
    )
