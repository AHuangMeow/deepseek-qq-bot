SHELL := /bin/bash

.PHONY: help init install up down stop start status check test smoke kev bot logs clean

help:
	@echo "make init     生成 .env（随机 WebUI token）"
	@echo "make install  安装 bot 与 Kev 依赖"
	@echo "make up       启动 NapCat 容器"
	@echo "make kev      前台启动 Kev（首次会下载模型）"
	@echo "make bot      前台启动机器人"
	@echo "make start    一键后台启动 NapCat + Kev + 机器人"
	@echo "make stop     停止机器人和 Kev（保留 NapCat）"
	@echo "make down     停止并删除所有容器"
	@echo "make status   查看状态"
	@echo "make check    检查配置 / Kev / DeepSeek 连通性"
	@echo "make smoke    用中文样例测试 Kev 判断"
	@echo "make test     运行单元测试"
	@echo "make logs     跟踪机器人日志"

init:
	./scripts/init_env.sh

install:
	./scripts/setup.sh

up:
	docker compose up -d
	@echo "NapCat WebUI: http://127.0.0.1:6099/webui"

down:
	./scripts/stop_all.sh --down

stop:
	./scripts/stop_all.sh

start:
	./scripts/start_all.sh

status:
	./scripts/status.sh

check:
	uv run python -m bot.main --check

test:
	uv run pytest -q

smoke:
	uv run python scripts/smoke_kev.py

kev:
	./scripts/run_kev.sh

bot:
	./scripts/run_bot.sh

logs:
	tail -f data/logs/bot.log

clean:
	rm -rf .pytest_cache .ruff_cache
