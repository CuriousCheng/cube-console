#!/usr/bin/env bash
DIR="$(cd "$(dirname "$0")/.." && pwd)"
pkill -f "uvicorn app.main:app" 2>/dev/null
pkill -f "app.gateway" 2>/dev/null
pkill -f "wren serve mcp" 2>/dev/null
[ -x "$DIR/runtime/trino/bin/launcher" ] && "$DIR/runtime/trino/bin/launcher" stop >/dev/null 2>&1
echo "已停止"