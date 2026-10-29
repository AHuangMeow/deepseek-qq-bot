#!/usr/bin/env bash
# 查看各组件状态。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PORT="${KEV_PORT:-8009}"
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
  PORT="${KEV_PORT:-8009}"
fi

echo "== Docker =="
docker compose ps || true

echo
echo "== 端口 =="
ss -lntp 2>/dev/null | grep -E ":(3001|6099|${PORT})\b" || echo "未监听"

echo
echo "== Kev =="
if curl -fsS "http://127.0.0.1:${PORT}/v1/models" 2>/dev/null; then
  echo
else
  echo "不可达（http://127.0.0.1:${PORT}）"
fi

echo
echo "== 进程 =="
for name in kev bot; do
  file="data/run/${name}.pid"
  if [ -f "$file" ] && kill -0 "$(cat "$file")" 2>/dev/null; then
    echo "$name: 运行中（PID $(cat "$file")）"
  else
    echo "$name: 未运行"
  fi
done

echo
echo "== 最近日志 =="
for name in kev bot; do
  echo "--- $name ---"
  tail -n 5 "data/logs/${name}.log" 2>/dev/null || echo "无日志"
done
