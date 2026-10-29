#!/usr/bin/env bash
# 前台启动 QQ 机器人。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ ! -d .venv ]; then
  echo "缺少 .venv，请先运行 make install" >&2
  exit 1
fi

if [ -x "$ROOT/.venv/bin/python" ]; then
  exec "$ROOT/.venv/bin/python" -m bot.main "$@"
fi

exec uv run python -m bot.main "$@"
