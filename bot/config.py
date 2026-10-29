"""Configuration loaded from .env / environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


class ConfigError(RuntimeError):
    pass


def _str(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} 必须是整数，当前值：{raw!r}") from exc


def _float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} 必须是数字，当前值：{raw!r}") from exc


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "y"}


def _id_set(name: str) -> frozenset[int]:
    raw = os.getenv(name, "")
    result: set[int] = set()
    for part in raw.replace("，", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            result.add(int(part))
        except ValueError as exc:
            raise ConfigError(f"{name} 里包含非数字 QQ/群号：{part!r}") from exc
    return frozenset(result)


def _aliases(name: str) -> tuple[str, ...]:
    raw = os.getenv(name, "")
    return tuple(
        part.strip()
        for part in raw.replace("，", ",").split(",")
        if part.strip()
    )


@dataclass(frozen=True)
class Config:
    root: Path

    deepseek_api_key: str
    deepseek_base_url: str
    deepseek_model: str
    deepseek_temperature: float
    deepseek_max_tokens: int
    deepseek_timeout: float
    deepseek_thinking: bool

    vision_enabled: bool
    vision_caption_for_kev: bool
    vision_detail: str
    max_images_per_message: int
    max_image_bytes: int
    image_download_timeout: float
    image_cache_seconds: int
    max_context_images: int

    napcat_ws_url: str
    napcat_ws_token: str

    kev_enabled: bool
    kev_base_url: str
    kev_api_key: str
    kev_model: str
    kev_timeout: float
    kev_reply_threshold_at: float
    kev_reply_threshold_private: float
    kev_reply_threshold_group: float
    kev_risk_threshold: float
    kev_fail_open: bool

    bot_name: str
    bot_aliases: tuple[str, ...]
    persona_file: str
    admin_qqs: frozenset[int]

    group_whitelist: frozenset[int]
    private_whitelist: frozenset[int]
    group_blacklist: frozenset[int]
    private_blacklist: frozenset[int]

    enable_ambient: bool
    group_cooldown_seconds: int
    user_cooldown_seconds: int
    max_replies_per_minute: int
    max_bot_messages_in_row: int

    debounce_seconds: float
    max_context_messages: int
    max_reply_chars: int
    mention_on_reply: bool
    quote_reply: bool

    sticker_enabled: bool
    sticker_dir: str
    sticker_chance: float
    sticker_max_bytes: int
    sticker_block_words: tuple[str, ...]

    dry_run: bool
    decision_log: bool
    log_level: str

    @property
    def persona_path(self) -> Path:
        path = Path(self.persona_file)
        return path if path.is_absolute() else self.root / path

    @property
    def sticker_path(self) -> Path:
        path = Path(self.sticker_dir).expanduser()
        return path if path.is_absolute() else self.root / path

    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "bot.sqlite3"

    @property
    def log_path(self) -> Path:
        return self.data_dir / "logs" / "bot.log"

    @property
    def decision_log_path(self) -> Path:
        return self.data_dir / "decisions.jsonl"

    @classmethod
    def load(cls, env_file: Path | None = None) -> "Config":
        env_path = env_file or (ROOT / ".env")
        if env_path.exists():
            load_dotenv(env_path, override=False)

        cfg = cls(
            root=ROOT,
            deepseek_api_key=_str("DEEPSEEK_API_KEY"),
            deepseek_base_url=_str("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/"),
            deepseek_model=_str("DEEPSEEK_MODEL", "deepseek-flash"),
            deepseek_temperature=_float("DEEPSEEK_TEMPERATURE", 1.1),
            deepseek_max_tokens=_int("DEEPSEEK_MAX_TOKENS", 320),
            deepseek_timeout=_float("DEEPSEEK_TIMEOUT", 60.0),
            deepseek_thinking=_bool("DEEPSEEK_THINKING", False),
            vision_enabled=_bool("VISION_ENABLED", True),
            vision_caption_for_kev=_bool("VISION_CAPTION_FOR_KEV", True),
            vision_detail=_str("VISION_DETAIL", "low"),
            max_images_per_message=_int("MAX_IMAGES_PER_MESSAGE", 3),
            max_image_bytes=_int("MAX_IMAGE_BYTES", 20 * 1024 * 1024),
            image_download_timeout=_float("IMAGE_DOWNLOAD_TIMEOUT", 20.0),
            image_cache_seconds=_int("IMAGE_CACHE_SECONDS", 600),
            max_context_images=_int("MAX_CONTEXT_IMAGES", 2),
            napcat_ws_url=_str("NAPCAT_WS_URL", "ws://127.0.0.1:3001"),
            napcat_ws_token=_str("NAPCAT_WS_TOKEN"),
            kev_enabled=_bool("KEV_ENABLED", True),
            kev_base_url=_str("KEV_BASE_URL", "http://127.0.0.1:8009").rstrip("/"),
            kev_api_key=_str("KEV_API_KEY"),
            kev_model=_str("KEV_MODEL", "kev-latest"),
            kev_timeout=_float("KEV_TIMEOUT", 20.0),
            kev_reply_threshold_at=_float("KEV_REPLY_THRESHOLD_AT", 0.20),
            kev_reply_threshold_private=_float("KEV_REPLY_THRESHOLD_PRIVATE", 0.20),
            kev_reply_threshold_group=_float("KEV_REPLY_THRESHOLD_GROUP", 0.72),
            kev_risk_threshold=_float("KEV_RISK_THRESHOLD", 0.60),
            kev_fail_open=_bool("KEV_FAIL_OPEN", False),
            bot_name=_str("BOT_NAME", "小深"),
            bot_aliases=_aliases("BOT_ALIASES") or (_str("BOT_NAME", "小深"),),
            persona_file=_str("PERSONA_FILE", "persona.md"),
            admin_qqs=_id_set("ADMIN_QQS"),
            group_whitelist=_id_set("GROUP_WHITELIST"),
            private_whitelist=_id_set("PRIVATE_WHITELIST"),
            group_blacklist=_id_set("GROUP_BLACKLIST"),
            private_blacklist=_id_set("PRIVATE_BLACKLIST"),
            enable_ambient=_bool("ENABLE_AMBIENT", True),
            group_cooldown_seconds=_int("GROUP_COOLDOWN_SECONDS", 25),
            user_cooldown_seconds=_int("USER_COOLDOWN_SECONDS", 90),
            max_replies_per_minute=_int("MAX_REPLIES_PER_MINUTE", 8),
            max_bot_messages_in_row=_int("MAX_BOT_MESSAGES_IN_ROW", 2),
            debounce_seconds=_float("DEBOUNCE_SECONDS", 0.8),
            max_context_messages=_int("MAX_CONTEXT_MESSAGES", 10),
            max_reply_chars=_int("MAX_REPLY_CHARS", 320),
            mention_on_reply=_bool("MENTION_ON_REPLY", True),
            quote_reply=_bool("QUOTE_REPLY", False),
            sticker_enabled=_bool("STICKER_ENABLED", True),
            sticker_dir=_str("STICKER_DIR", "~/Downloads/表情包"),
            sticker_chance=_float("STICKER_CHANCE", 0.2),
            sticker_max_bytes=_int("STICKER_MAX_BYTES", 8 * 1024 * 1024),
            sticker_block_words=_aliases("STICKER_BLOCK_WORDS") or (
                "杀", "死", "妈", "草", "怒", "笨蛋", "傻", "滚", "屎", "尿",
                "裸", "色", "性", "黄", "毒", "枪", "刀", "普信",
            ),
            dry_run=_bool("DRY_RUN", False),
            decision_log=_bool("DECISION_LOG", True),
            log_level=_str("LOG_LEVEL", "INFO").upper(),
        )
        cfg.validate()
        return cfg

    def validate(self) -> None:
        for name, value in (
            ("KEV_REPLY_THRESHOLD_AT", self.kev_reply_threshold_at),
            ("KEV_REPLY_THRESHOLD_PRIVATE", self.kev_reply_threshold_private),
            ("KEV_REPLY_THRESHOLD_GROUP", self.kev_reply_threshold_group),
            ("KEV_RISK_THRESHOLD", self.kev_risk_threshold),
        ):
            if not 0.0 <= value <= 1.0:
                raise ConfigError(f"{name} 必须在 0~1 之间，当前值：{value}")
        if self.vision_detail not in {"low", "high", "original", "auto"}:
            raise ConfigError("VISION_DETAIL 只能是 low / high / original / auto")
        if self.max_images_per_message < 0:
            raise ConfigError("MAX_IMAGES_PER_MESSAGE 不能为负数")
        if self.max_image_bytes < 1024:
            raise ConfigError("MAX_IMAGE_BYTES 至少为 1024")
        if self.image_cache_seconds < 0:
            raise ConfigError("IMAGE_CACHE_SECONDS 不能为负数")
        if self.max_context_images < 0:
            raise ConfigError("MAX_CONTEXT_IMAGES 不能为负数")
        if not 0.0 <= self.sticker_chance <= 1.0:
            raise ConfigError(f"STICKER_CHANCE 必须在 0~1 之间，当前值：{self.sticker_chance}")
        if self.sticker_max_bytes < 1024:
            raise ConfigError("STICKER_MAX_BYTES 至少为 1024")
        if self.sticker_enabled and not self.sticker_dir:
            raise ConfigError("STICKER_ENABLED=true 时 STICKER_DIR 不能为空")
        if not self.deepseek_api_key and not self.dry_run:
            raise ConfigError(
                "DEEPSEEK_API_KEY 为空。请编辑 .env 填入 key；"
                "只想调试流程可设置 DRY_RUN=true。"
            )
        if not self.napcat_ws_url.startswith(("ws://", "wss://")):
            raise ConfigError(f"NAPCAT_WS_URL 必须以 ws:// 或 wss:// 开头：{self.napcat_ws_url}")
        if self.max_context_messages < 2:
            raise ConfigError("MAX_CONTEXT_MESSAGES 至少为 2")
        if self.max_reply_chars < 20:
            raise ConfigError("MAX_REPLY_CHARS 至少为 20")
