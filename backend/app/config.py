"""全局配置：环境变量 + config.json 里的可调参数。"""

from __future__ import annotations

import os
from pathlib import Path

# 包根目录（解压到哪就是哪）。config.py 在 <root>/app/backend/app/config.py
_HOME_GUESS = Path(__file__).resolve().parents[3]
WREN_HOME = Path(os.getenv("WC_HOME", "") or _HOME_GUESS)

DATA_DIR = Path(os.getenv("DATA_DIR", "") or (WREN_HOME / "app" / "data"))
CATALOG_DIR = Path(os.getenv("CATALOG_DIR", "") or (WREN_HOME / "runtime" / "trino" / "etc" / "catalog"))
TRINO_URL = os.getenv("TRINO_URL", "http://127.0.0.1:8888").rstrip("/")

# 业务（Wren 项目）放哪 —— 可以跟程序目录分开
PROJECTS_DIR = Path(os.getenv("PROJECTS_DIR", "") or (WREN_HOME / "businesses"))

# Wren 的 trino profile 用这些连 Trino
TRINO_HOST = os.getenv("TRINO_HOST", "127.0.0.1")
TRINO_PORT = int(os.getenv("TRINO_PORT", "8888"))
# profile 里的默认 catalog（MDL 里每个模型都会显式写 catalog，这里只是占位）
DEFAULT_TRINO_CATALOG = os.getenv("DEFAULT_TRINO_CATALOG", "mysql")
# profile 里的默认 schema
TRINO_SCHEMA = os.getenv("DEFAULT_TRINO_SCHEMA", "public")

MASTER_KEY = os.getenv("MASTER_KEY", "")
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

# config.json 不存在时使用的默认值
DEFAULTS = {
    "pool_size": 3,            # 同时运行的 MCP 进程数
    "ask_concurrency": 1,      # 单项目并发提问数
    "viewer_can_see_sql": False,
    "idle_stop_minutes": 10,
    "ai": {
        "protocol": "openai",  # openai | anthropic
        "base_url": "",
        "model": "",
        "api_key_enc": "",     # Fernet 加密后存这里
    },
}

# 支持的数据源类型 → (Trino connector 名, JDBC URL 模板)
CONNECTORS = {
    "mysql": ("mysql", "jdbc:mysql://{host}:{port}?sslMode=DISABLED&connectionTimeZone=%2B08:00"),
    "postgresql": ("postgresql", "jdbc:postgresql://{host}:{port}/{database}"),
    "sqlserver": ("sqlserver", "jdbc:sqlserver://{host}:{port};databaseName={database}"),
    "mariadb": ("mariadb", "jdbc:mariadb://{host}:{port}/{database}"),
}

DATA_DIR.mkdir(parents=True, exist_ok=True)
CATALOG_DIR.mkdir(parents=True, exist_ok=True)
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
