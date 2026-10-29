#!/usr/bin/env bash
# 安装/更新 Kev 的 Python 依赖。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KEV_DIR="$ROOT/vendor/kev"

if [ ! -d "$KEV_DIR/.git" ]; then
  echo "==> 克隆 Kev"
  mkdir -p "$ROOT/vendor"
  git clone --depth 1 https://github.com/jaredpalmer/kev.git "$KEV_DIR"
fi

cd "$KEV_DIR"
echo "==> uv sync --extra serve"
uv sync --extra serve

echo
echo "Kev 依赖安装完成。"
echo "可选：如果你有匹配的 CUDA 环境，可再安装加速内核："
echo "  cd vendor/kev && uv pip install flash-linear-attention==0.5.2"
