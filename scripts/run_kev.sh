#!/usr/bin/env bash
# 前台启动 Kev 判断服务（默认 http://127.0.0.1:8009）。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

KEV_DIR="$ROOT/vendor/kev"
if [ ! -d "$KEV_DIR" ]; then
  echo "找不到 vendor/kev，请先运行 scripts/install_kev.sh" >&2
  exit 1
fi

cd "$KEV_DIR"
SERVE_ARGS=(
  --run "${KEV_MODEL_REPO:-jaredpalmer/kev-0.8b}"
  --port "${KEV_PORT:-8009}"
  --device "${KEV_DEVICE:-auto}"
)

# 优先直接用 Kev 的虚拟环境启动：PID 就是真正的服务进程，
# 便于 scripts/stop_all.sh 准确停止，也省掉 uv 包一层。
if [ -x "$KEV_DIR/.venv/bin/python" ]; then
  exec "$KEV_DIR/.venv/bin/python" -m kev.serve "${SERVE_ARGS[@]}" "$@"
fi

exec uv run --extra serve python -m kev.serve "${SERVE_ARGS[@]}" "$@"
