#!/usr/bin/env bash
# 停止机器人和 Kev；默认保留 NapCat 容器与登录数据。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

stop_pid() {
  local name="$1" file="$2"
  if [ ! -f "$file" ]; then
    echo "$name 未运行"
    return
  fi
  local pid
  pid="$(cat "$file")"
  if kill -0 "$pid" 2>/dev/null; then
    echo "停止 $name（PID $pid）"
    kill "$pid" 2>/dev/null || true
    for _ in $(seq 1 20); do
      if ! kill -0 "$pid" 2>/dev/null; then
        break
      fi
      sleep 0.5
    done
    if kill -0 "$pid" 2>/dev/null; then
      kill -9 "$pid" 2>/dev/null || true
    fi
  fi
  rm -f "$file"
}

stop_pid "机器人" data/run/bot.pid
stop_pid "Kev" data/run/kev.pid

if [ "${1:-}" = "--down" ]; then
  echo "停止并删除 NapCat 容器（登录数据仍保留在 data/napcat）"
  docker compose down
else
  echo "NapCat 容器保持运行；如需停止请运行 make down"
fi
