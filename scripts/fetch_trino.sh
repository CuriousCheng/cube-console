#!/usr/bin/env bash
# 下载 Trino 并裁剪到我们需要的 5 个连接器
set -e
DIR="$(cd "$(dirname "$0")/.." && pwd)"
TR="$DIR/runtime/trino"
V="${TRINO_VERSION:-476}"

if [ -x "$TR/bin/launcher" ]; then
  echo "Trino 已存在: $TR"
  exit 0
fi

mkdir -p "$DIR/runtime"
cd "$DIR/runtime"

URL="${TRINO_URL:-https://maven.aliyun.com/repository/central/io/trino/trino-server/$V/trino-server-$V.tar.gz}"
echo "下载 Trino $V ..."
echo "  $URL"
curl -fL --retry 3 -o trino.tar.gz "$URL"
tar -xzf trino.tar.gz
rm -f trino.tar.gz
rm -rf "$TR"
mv "trino-server-$V" "$TR"

echo "裁剪连接器（只留 mysql/mariadb/postgresql/sqlserver/tpch）..."
KEEP="mysql mariadb postgresql sqlserver tpch"
cd "$TR/plugin"
for d in *; do
  keep=0
  for k in $KEEP; do [ "$d" = "$k" ] && keep=1; done
  [ $keep -eq 0 ] && rm -rf "$d"
done

mkdir -p "$TR/etc/catalog" "$TR/data"
NODE_ID="$(cat /proc/sys/kernel/random/uuid 2>/dev/null || echo 00000000-0000-0000-0000-000000000001)"
printf 'node.environment=production\nnode.id=%s\nnode.data-dir=%s/data\n' "$NODE_ID" "$TR" > "$TR/etc/node.properties"
printf -- '-server\n-Xmx2G\n-XX:+ExitOnOutOfMemoryError\n' > "$TR/etc/jvm.config"
printf 'coordinator=true\nnode-scheduler.include-coordinator=true\nhttp-server.http.port=8888\ndiscovery.uri=http://127.0.0.1:8888\n' > "$TR/etc/config.properties"

echo "完成: $TR ($(du -sh "$TR" | cut -f1))"