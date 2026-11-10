#!/usr/bin/env bash
DIR="$(cd "$(dirname "$0")/.." && pwd)"
set -a; [ -f "$DIR/.env" ] && . "$DIR/.env"; set +a

export DATA_DIR="$DIR/data"
export PROJECTS_DIR="$DIR/businesses"
export CATALOG_DIR="$DIR/runtime/trino/etc/catalog"
export TRINO_LAUNCHER="$DIR/runtime/trino/bin/launcher"
export TRINO_URL="http://127.0.0.1:8888"
export TRINO_HOST="127.0.0.1"
export TRINO_PORT="8888"
export WEB_DIR="$DIR/web"
export ENABLE_GATEWAY="${ENABLE_GATEWAY:-1}"
export GATEWAY_PORT="${GATEWAY_PORT:-9300}"
export GATEWAY_SSE_PORT="${GATEWAY_SSE_PORT:-9301}"

if ! (exec 3<>/dev/tcp/127.0.0.1/8888) 2>/dev/null; then
  echo "启动 Trino..."
  "$TRINO_LAUNCHER" start >/dev/null 2>&1 || true
  for i in $(seq 1 40); do sleep 1; (exec 3<>/dev/tcp/127.0.0.1/8888) 2>/dev/null && break; done
fi

pkill -f "uvicorn app.main:app" 2>/dev/null
sleep 1
cd "$DIR" || exit 1
nohup "$DIR/.venv/bin/python" -m uvicorn app.main:app \
  --host 0.0.0.0 --port 8000 --app-dir "$DIR/backend" > "$DIR/backend.log" 2>&1 &
sleep 4
echo "已启动 → http://localhost:8000"
echo "MCP 网关 → http://localhost:9301/sse（SSE） / http://localhost:9300/mcp（HTTP）"