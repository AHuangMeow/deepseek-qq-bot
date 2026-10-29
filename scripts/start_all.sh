#!/usr/bin/env bash
# 一键启动：NapCat 容器 + Kev 服务 + 机器人。
# NapCat 首次仍需要在 WebUI 扫码登录。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

"$ROOT/scripts/init_env.sh"
mkdir -p data/logs data/run

if ! grep -q '^DEEPSEEK_API_KEY=.\+' .env && ! grep -q '^DRY_RUN=true' .env; then
  echo "警告：.env 里的 DEEPSEEK_API_KEY 还是空的，机器人会拒绝启动。" >&2
  echo "请先填入 key，或设置 DRY_RUN=true 调试流程。" >&2
  exit 1
fi

echo "==> 启动 NapCat 容器"
docker compose up -d

if [ -f data/run/kev.pid ] && kill -0 "$(cat data/run/kev.pid)" 2>/dev/null; then
  echo "Kev 已在运行（PID $(cat data/run/kev.pid)）"
else
  echo "==> 启动 Kev（日志 data/logs/kev.log）"
  nohup "$ROOT/scripts/run_kev.sh" > data/logs/kev.log 2>&1 &
  echo $! > data/run/kev.pid
fi

PORT="${KEV_PORT:-8009}"
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
  PORT="${KEV_PORT:-8009}"
fi

echo "==> 等待 Kev 就绪（首次需要下载模型，可能要几分钟）"
for _ in $(seq 1 300); do
  if curl -fsS "http://127.0.0.1:${PORT}/v1/models" >/dev/null 2>&1; then
    echo "Kev 已就绪。"
    break
  fi
  sleep 2
done
if ! curl -fsS "http://127.0.0.1:${PORT}/v1/models" >/dev/null 2>&1; then
  echo "Kev 未就绪，请查看 data/logs/kev.log" >&2
  exit 1
fi

if [ -f data/run/bot.pid ] && kill -0 "$(cat data/run/bot.pid)" 2>/dev/null; then
  echo "机器人已在运行（PID $(cat data/run/bot.pid)）"
else
  echo "==> 启动机器人（日志 data/logs/bot.log，控制台输出 data/logs/bot.stdout.log）"
  nohup "$ROOT/scripts/run_bot.sh" > data/logs/bot.stdout.log 2>&1 &
  echo $! > data/run/bot.pid
fi

echo
echo "启动完成。"
echo "NapCat WebUI: http://127.0.0.1:6099/webui  （token 见 .env 的 WEBUI_TOKEN）"
echo "查看状态: make status"
echo "查看日志: tail -f data/logs/bot.log"
