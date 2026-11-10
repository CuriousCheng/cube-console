"""从 Trino 自动生成 / 更新 Cube 模型文件。

规则：
- 扫描 Trino 里所有 catalog.schema.table（跳过 system / information_schema）
- 已存在的 cube：保留用户改过的 title / description / measures / joins，
  只补上新列、去掉已删除的列
- 新表：生成 `row_count` 度量 + 每列一个维度
- Trino 里已经不存在的表：从模型里移除
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from . import trino_sql

SKIP_CATALOGS = {"system", "tpch", "memory", "blackhole"}
SKIP_SCHEMAS = {"information_schema", "sys", "pg_catalog"}


def _allowed_catalogs() -> set[str]:
    """只扫「数据源」里配置过的 catalog，避免把 tpch 之类也算进来。"""
    from .. import store

    try:
        items = store.read("datasources", {"items": []}).get("items", [])
    except Exception:  # noqa: BLE001
        return set()
    return {d.get("catalog") for d in items if d.get("catalog")}


def _cube_type(trino_type: str) -> str:
    t = (trino_type or "").lower()
    if re.match(r"^(int|integer|bigint|smallint|tinyint|decimal|numeric|double|real|float)", t):
        return "number"
    if re.match(r"^(timestamp|date)", t):
        return "time"
    if t.startswith("boolean"):
        return "boolean"
    return "string"


def _ident(name: str) -> bool:
    return bool(re.fullmatch(r"[a-z][a-z0-9_]{0,40}", name or ""))


async def scan_trino() -> tuple[list[dict], list[str]]:
    """返回 [{catalog, schema, table, columns:[(name,type)]}] 和错误列表。"""
    tables: list[dict] = []
    errors: list[str] = []
    allowed = _allowed_catalogs()

    cats = await trino_sql.query("SHOW CATALOGS")
    if not cats.get("ok"):
        return [], [f"连不上 Trino：{cats.get('error')}"]

    for row in cats.get("rows", []):
        cat = row.get("Catalog") or list(row.values())[0]
        if cat in SKIP_CATALOGS:
            continue
        if allowed and cat not in allowed:
            continue
        try:
            schemas = await trino_sql.query(f"SHOW SCHEMAS FROM {cat}")
        except Exception as e:  # noqa: BLE001
            errors.append(f"{cat}: {e}")
            continue
        if not schemas.get("ok"):
            continue

        for srow in schemas.get("rows", []):
            sch = srow.get("Schema") or list(srow.values())[0]
            if sch in SKIP_SCHEMAS:
                continue
            try:
                tres = await trino_sql.query(f"SHOW TABLES FROM {cat}.{sch}")
            except Exception:  # noqa: BLE001
                continue
            if not tres.get("ok"):
                continue

            for trow in tres.get("rows", []):
                tbl = trow.get("Table") or list(trow.values())[0]
                cols = await trino_sql.columns(cat, sch, tbl)
                if not cols:
                    continue
                tables.append(
                    {
                        "catalog": cat,
                        "schema": sch,
                        "table": tbl,
                        "columns": [(c.get("name") or c.get("column"), c.get("type")) for c in cols],
                    }
                )
    return tables, errors


def _new_cube(name: str, t: dict) -> dict:
    dims = []
    for cname, ctype in t["columns"]:
        d = {"name": cname, "sql": cname, "type": _cube_type(ctype)}
        if cname == "id" and d["type"] == "number":
            d["primary_key"] = True
        dims.append(d)
    return {
        "name": name,
        "sql_table": f"{t['catalog']}.{t['schema']}.{t['table']}",
        "measures": [{"name": "row_count", "type": "count", "title": "行数"}],
        "dimensions": dims,
    }


def _merge_cube(old: dict, t: dict) -> dict:
    """保留用户编辑过的内容，只同步列。"""
    old_cols = {d.get("name"): d for d in (old.get("dimensions") or [])}
    dims = []
    for cname, ctype in t["columns"]:
        if cname in old_cols:
            dims.append(old_cols[cname])  # 原样保留 title / description / primary_key
        else:
            d = {"name": cname, "sql": cname, "type": _cube_type(ctype)}
            if cname == "id" and d["type"] == "number":
                d["primary_key"] = True
            dims.append(d)

    out = dict(old)
    out["sql_table"] = f"{t['catalog']}.{t['schema']}.{t['table']}"
    out["dimensions"] = dims
    if not out.get("measures"):
        out["measures"] = [{"name": "row_count", "type": "count", "title": "行数"}]
    return out


async def rebuild(models_file: Path) -> dict:
    """扫描 Trino 并重写模型文件。返回统计信息。"""
    scanned, errors = await scan_trino()
    if not scanned and errors:
        return {"ok": False, "error": "; ".join(errors[:3]), "cubes": 0}

    existing: dict[str, dict] = {}
    if models_file.exists():
        loaded = yaml.safe_load(models_file.read_text("utf-8")) or {}
        for c in loaded.get("cubes") or []:
            if isinstance(c, dict) and c.get("name"):
                existing[c["name"]] = c

    # 先按表名生成名字，冲突时加 schema 前缀
    used: set[str] = set()
    out: list[dict] = []
    added = kept = 0
    for t in scanned:
        name = t["table"]
        if not _ident(name):
            name = re.sub(r"[^a-z0-9_]", "_", name.lower())
        if name in used:
            name = f"{t['schema']}_{t['table']}"
        used.add(name)

        old = existing.get(name)
        if old and old.get("sql_table") in (
            f"{t['catalog']}.{t['schema']}.{t['table']}",
            None,
        ):
            out.append(_merge_cube(old, t))
            kept += 1
        elif old:
            out.append(_merge_cube(old, t))
            kept += 1
        else:
            out.append(_new_cube(name, t))
            added += 1

    removed = len([n for n in existing if n not in used])
    models_file.parent.mkdir(parents=True, exist_ok=True)
    models_file.write_text(
        yaml.safe_dump({"cubes": out}, allow_unicode=True, sort_keys=False), "utf-8"
    )

    return {
        "ok": True,
        "cubes": len(out),
        "added": added,
        "kept": kept,
        "removed": removed,
        "errors": errors[:5],
    }
