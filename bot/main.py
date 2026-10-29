"""Entrypoint: python -m bot.main [--check]"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from logging.handlers import RotatingFileHandler

from .config import Config, ConfigError
from .deepseek import DeepSeekClient, DeepSeekError
from .handler import BotHandler
from .kev import KevClient, KevError
from .memory import Memory
from .onebot import OneBotClient, OneBotError

log = logging.getLogger("bot")


def setup_logging(cfg: Config) -> None:
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    cfg.log_path.parent.mkdir(parents=True, exist_ok=True)
    level = getattr(logging, cfg.log_level, logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    root.addHandler(console)

    file_handler = RotatingFileHandler(
        cfg.log_path,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)


async def run_check(cfg: Config) -> int:
    ok = True
    print(f"项目目录：{cfg.root}")
    print(f"人设文件：{cfg.persona_path} {'✓' if cfg.persona_path.exists() else '✗'}")
    if not cfg.persona_path.exists():
        ok = False

    if cfg.deepseek_api_key:
        client = DeepSeekClient(
            cfg.deepseek_api_key,
            cfg.deepseek_base_url,
            cfg.deepseek_model,
            temperature=cfg.deepseek_temperature,
            max_tokens=cfg.deepseek_max_tokens,
            timeout=cfg.deepseek_timeout,
            thinking=cfg.deepseek_thinking,
        )
        try:
            reply = await client.ping()
            print(f"DeepSeek：✓ {cfg.deepseek_model} 返回「{reply[:20]}」")
            print(
                f"视觉：{'启用' if cfg.vision_enabled else '关闭'}"
                f"（detail={cfg.vision_detail}，图片先描述给 Kev）"
                if cfg.vision_enabled
                else "视觉：关闭"
            )
        except DeepSeekError as exc:
            print(f"DeepSeek：✗ {exc}")
            ok = False
        finally:
            await client.close()
    elif cfg.dry_run:
        print("DeepSeek：跳过（DRY_RUN=true 且未填 key）")
    else:
        print("DeepSeek：✗ 未填写 DEEPSEEK_API_KEY")
        ok = False

    if cfg.kev_enabled:
        kev = KevClient(cfg.kev_base_url, cfg.kev_model, cfg.kev_api_key, cfg.kev_timeout)
        try:
            data = await kev.models()
            items = data.get("models") or data.get("data") or []
            models = [
                str(item.get("name") or item.get("id"))
                for item in items
                if isinstance(item, dict) and (item.get("name") or item.get("id"))
            ]
            print(f"Kev：✓ {cfg.kev_base_url} {', '.join(models[:5]) or '(未返回模型列表)'}")
        except KevError as exc:
            print(f"Kev：✗ {exc}")
            print("  提示：先运行 scripts/run_kev.sh，或运行 scripts/start_all.sh")
            ok = False
        finally:
            await kev.close()
    else:
        print("Kev：已禁用（KEV_ENABLED=false）")

    if cfg.sticker_enabled:
        if cfg.sticker_path.is_dir():
            count = sum(
                1
                for path in cfg.sticker_path.iterdir()
                if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".gif", ".webp"}
            )
            print(f"表情包：✓ {cfg.sticker_path}（{count} 张）")
        else:
            print(f"表情包：⚠ 目录不存在：{cfg.sticker_path}（不影响聊天）")
    else:
        print("表情包：关闭")

    print(f"NapCat WS：{cfg.napcat_ws_url}")
    print("配置检查通过。" if ok else "配置检查未通过。")
    return 0 if ok else 1


async def run_bot(cfg: Config) -> None:
    setup_logging(cfg)
    log.info(
        "启动 %s，NapCat=%s，Kev=%s，模型=%s，视觉=%s，表情包=%s",
        cfg.bot_name,
        cfg.napcat_ws_url,
        cfg.kev_base_url,
        cfg.deepseek_model,
        "on" if cfg.vision_enabled else "off",
        "on" if cfg.sticker_enabled else "off",
    )
    if cfg.dry_run:
        log.warning("DRY_RUN=true：不会真的发送消息，也不会调用 DeepSeek")

    memory = Memory(cfg.db_path)
    kev = KevClient(cfg.kev_base_url, cfg.kev_model, cfg.kev_api_key, cfg.kev_timeout) if cfg.kev_enabled else None
    deepseek = None if cfg.dry_run else DeepSeekClient(
        cfg.deepseek_api_key,
        cfg.deepseek_base_url,
        cfg.deepseek_model,
        temperature=cfg.deepseek_temperature,
        max_tokens=cfg.deepseek_max_tokens,
        timeout=cfg.deepseek_timeout,
        thinking=cfg.deepseek_thinking,
    )
    onebot = OneBotClient(cfg.napcat_ws_url, cfg.napcat_ws_token)
    handler = BotHandler(cfg, memory, onebot, kev, deepseek)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # pragma: no cover - Windows
            pass

    ws_task = asyncio.create_task(onebot.run(handler.handle_event))
    try:
        await onebot.wait_connected(timeout=45)
        try:
            info = await onebot.get_login_info()
            log.info("QQ 已登录：%s（%s）", info.get("nickname", "?"), info.get("user_id", "?"))
        except OneBotError as exc:
            log.warning("暂时拿不到登录信息（可能还没扫码）：%s", exc)
            log.warning("机器人会保持连接，扫码登录后即可接收消息。")
        log.info("机器人已就绪。Ctrl+C 停止。")
        await stop.wait()
    except OneBotError as exc:
        log.error("连接 NapCat 失败：%s", exc)
        log.error("请确认 NapCat 容器已启动，WebUI 已扫码登录，且 OneBot WS 服务监听 3001。")
    finally:
        log.info("正在停止 ...")
        await handler.close()
        await onebot.close()
        ws_task.cancel()
        await asyncio.gather(ws_task, return_exceptions=True)
        if kev is not None:
            await kev.close()
        if deepseek is not None:
            await deepseek.close()
        memory.close()
        log.info("已停止。")


def main() -> None:
    parser = argparse.ArgumentParser(description="DeepSeek QQ bot with Kev decision gate")
    parser.add_argument("--check", action="store_true", help="检查配置、Kev 和 DeepSeek 连通性")
    args = parser.parse_args()

    try:
        cfg = Config.load()
    except ConfigError as exc:
        print(f"配置错误：{exc}", file=sys.stderr)
        raise SystemExit(2)

    if args.check:
        raise SystemExit(asyncio.run(run_check(cfg)))
    try:
        asyncio.run(run_bot(cfg))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
