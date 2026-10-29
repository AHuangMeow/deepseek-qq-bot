#!/usr/bin/env bash
# 从 .env.example 生成 .env，并写入随机 WebUI token 与当前用户 UID/GID。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ -f .env ]; then
  echo ".env 已存在，保持不动。"
  exit 0
fi

cp .env.example .env
TOKEN="$(python3 -c 'import secrets; print(secrets.token_hex(24))')"
UID_NOW="$(id -u)"
GID_NOW="$(id -g)"

sed -i "s|^WEBUI_TOKEN=.*|WEBUI_TOKEN=${TOKEN}|" .env
sed -i "s|^NAPCAT_UID=.*|NAPCAT_UID=${UID_NOW}|" .env
sed -i "s|^NAPCAT_GID=.*|NAPCAT_GID=${GID_NOW}|" .env

echo "已生成 .env（WEBUI_TOKEN 为随机值，NAPCAT_UID/GID=${UID_NOW}/${GID_NOW}）。"
echo "请编辑 .env 填入 DEEPSEEK_API_KEY。"
