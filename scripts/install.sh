#!/usr/bin/env bash
set -e
DIR="$(cd "$(dirname "$0")/.." && pwd)"
echo "安装目录: $DIR"

# ① Java 24+
command -v java >/dev/null 2>&1 || { echo "X 没找到 java，请先装 JDK 24+"; exit 1; }
JV=$(java -version 2>&1 | head -1 | sed 's/.*version "\([0-9]*\).*/\1/')
[ "$JV" -ge 24 ] 2>/dev/null || { echo "X Java $JV 太老，Trino 需要 24+"; exit 1; }
echo "OK Java $JV"

# ② Python 3.11+
PYBIN=""
check_py() {
  local c="$1"
  [ -x "$c" ] || command -v "$c" >/dev/null 2>&1 || return 1
  local v
  v=$("$c" -c 'import sys;print(sys.version_info[1])' 2>/dev/null || echo 0)
  [ "$v" -ge 11 ] 2>/dev/null || return 1
  PYBIN="$c"
  return 0
}
if [ -n "$PYTHON" ]; then check_py "$PYTHON" || true; fi
if [ -z "$PYBIN" ]; then
  for c in python3.13 python3.12 python3.11 python3; do check_py "$c" && break; done
fi
[ -n "$PYBIN" ] || { echo "X 需要 Python 3.11+（可 PYTHON=/path/to/python3.11 ./scripts/install.sh）"; exit 1; }
echo "OK $PYBIN"

# ③ Trino
bash "$DIR/scripts/fetch_trino.sh"

# ④ Python 依赖
if [ ! -x "$DIR/.venv/bin/python" ]; then
  echo "创建虚拟环境..."
  "$PYBIN" -m venv "$DIR/.venv"
fi
"$DIR/.venv/bin/pip" install -q --upgrade pip
echo "安装依赖（约 3-5 分钟）..."
"$DIR/.venv/bin/pip" install -q -r "$DIR/backend/requirements.txt"
echo "OK 依赖装好"

# ⑤ 前端（可选，有 node 就构建）
if [ -d "$DIR/frontend" ] && command -v npm >/dev/null 2>&1 && [ ! -d "$DIR/web" ]; then
  echo "构建前端..."
  ( cd "$DIR/frontend" && npm install --no-audit --no-fund && npm run build )
  rm -rf "$DIR/web"
  cp -r "$DIR/frontend/dist" "$DIR/web"
  echo "OK 前端构建完成"
elif [ -d "$DIR/web" ]; then
  echo "OK 前端已存在（web/）"
else
  echo "跳过前端：没有 npm，也没有 web/ 目录（只有 API 能用）"
fi

# ⑥ 密钥
if [ ! -f "$DIR/.env" ]; then
  MK=$(head -c 32 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 32)
  printf 'MASTER_KEY=%s\nADMIN_USER=admin\nADMIN_PASSWORD=admin123\n' "$MK" > "$DIR/.env"
  echo "OK 已生成 .env（管理员 admin / admin123）"
fi

mkdir -p "$DIR/data" "$DIR/businesses"
echo ""
echo "安装完成，执行： ./scripts/start.sh"