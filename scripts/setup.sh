#!/usr/bin/env bash
# 首次安装：生成 .env、安装 bot 依赖、安装 Kev 依赖。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

"$ROOT/scripts/init_env.sh"
echo
echo "==> 安装 bot 依赖（Python 3.13）"
uv sync --all-groups
echo
echo "==> 安装 Kev 依赖（包含 serve 额外依赖，首次会下载 PyTorch，体积较大）"
"$ROOT/scripts/install_kev.sh"
echo
echo "安装完成。下一步："
echo "  1. 编辑 .env，填入 DEEPSEEK_API_KEY"
echo "  2. 运行 make up 启动 NapCat"
echo "  3. 打开 http://127.0.0.1:6099/webui 扫码登录（token 在 .env 的 WEBUI_TOKEN）"
