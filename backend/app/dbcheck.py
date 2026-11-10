"""测试到目标数据库的连通性。

注意：这里是「后端直连目标库」做探测，不经过 Trino。
目的只是告诉用户「地址/账号/密码对不对」，探完就断开。
"""

from __future__ import annotations

from typing import Any


def test_connection(
    type_: str,
    host: str,
    port: int,
    database: str,
    user: str,
    password: str,
    timeout: int = 6,
) -> dict[str, Any]:
    try:
        if type_ in ("mysql", "mariadb"):
            import pymysql

            conn = pymysql.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                database=database or None,
                connect_timeout=timeout,
                charset="utf8mb4",
            )
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT VERSION()")
                    version = cur.fetchone()[0]
                    cur.execute("SHOW DATABASES")
                    dbs = [r[0] for r in cur.fetchall()]
            finally:
                conn.close()
            return {"ok": True, "version": str(version), "databases": dbs}

        if type_ == "postgresql":
            import psycopg2

            conn = psycopg2.connect(
                host=host,
                port=port,
                dbname=database or "postgres",
                user=user,
                password=password,
                connect_timeout=timeout,
            )
            try:
                with conn.cursor() as cur:
                    cur.execute("SHOW server_version")
                    version = cur.fetchone()[0]
                    cur.execute("SELECT datname FROM pg_database WHERE datistemplate = false")
                    dbs = [r[0] for r in cur.fetchall()]
            finally:
                conn.close()
            return {"ok": True, "version": str(version), "databases": dbs}

        return {"ok": False, "error": f"类型 {type_} 暂不支持测试连接"}

    except Exception as e:  # noqa: BLE001 - 要把原始错误原样给用户看
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
