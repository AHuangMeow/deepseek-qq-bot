from __future__ import annotations

import asyncio
import base64
import random
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from bot.config import Config
from bot.handler import BotHandler, sanitize_reply
from bot.images import LoadedImage
from bot.kev import KevError
from bot.memory import Memory
from bot.onebot import ImageAttachment, MessageEvent, parse_message_event
from bot.stickers import StickerLibrary


@pytest.fixture
def cfg(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Config:
    values = {
        "DEEPSEEK_API_KEY": "test-key",
        "DEEPSEEK_BASE_URL": "https://example.invalid",
        "BOT_NAME": "小深",
        "BOT_ALIASES": "小深,deepseek",
        "PERSONA_FILE": "persona.md",
        "KEV_ENABLED": "true",
        "KEV_REPLY_THRESHOLD_AT": "0.20",
        "KEV_REPLY_THRESHOLD_PRIVATE": "0.20",
        "KEV_REPLY_THRESHOLD_GROUP": "0.72",
        "KEV_RISK_THRESHOLD": "0.60",
        "KEV_FAIL_OPEN": "false",
        "ENABLE_AMBIENT": "true",
        "DEBOUNCE_SECONDS": "0",
        "DECISION_LOG": "false",
        "GROUP_COOLDOWN_SECONDS": "0",
        "USER_COOLDOWN_SECONDS": "0",
        "MAX_REPLIES_PER_MINUTE": "100",
        "MAX_BOT_MESSAGES_IN_ROW": "2",
        "MAX_CONTEXT_MESSAGES": "14",
        "VISION_ENABLED": "false",
        "STICKER_ENABLED": "false",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    return Config.load(env_file=tmp_path / "missing.env")


def make_event(text: str = "小深你好", *, addressed: bool = True) -> MessageEvent:
    segments: list[dict[str, Any]] = []
    if addressed:
        segments.append({"type": "at", "data": {"qq": "999"}})
    segments.append({"type": "text", "data": {"text": text}})
    event = parse_message_event(
        {
            "post_type": "message",
            "message_type": "group",
            "self_id": 999,
            "user_id": 123,
            "group_id": 456,
            "message_id": "m1",
            "message": segments,
            "sender": {"nickname": "阿明"},
            "time": 0,
        }
    )
    assert event is not None
    return event


class FakeOneBot:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def send_group_text(self, group_id: int, text: str, **kwargs: Any) -> str:
        self.sent.append({"group_id": group_id, "text": text, **kwargs})
        return "bot-message-1"

    async def send_group_segments(self, group_id: int, segments: list[dict[str, Any]], **kwargs: Any) -> str:
        self.sent.append({"group_id": group_id, "segments": segments, **kwargs})
        return "bot-message-1"

    async def send_private_text(self, user_id: int, text: str, **kwargs: Any) -> str:
        self.sent.append({"user_id": user_id, "text": text, **kwargs})
        return "bot-message-1"

    async def send_private_segments(self, user_id: int, segments: list[dict[str, Any]], **kwargs: Any) -> str:
        self.sent.append({"user_id": user_id, "segments": segments, **kwargs})
        return "bot-message-1"

    async def get_group_info(self, group_id: int) -> dict[str, Any]:
        return {"group_name": "测试群"}

    async def get_msg(self, message_id: str) -> dict[str, Any] | None:
        return None


class FakeKev:
    def __init__(
        self,
        should: float = 0.9,
        risk: float = 0.01,
        style: str = "friendly",
        error: Exception | None = None,
    ) -> None:
        self.should = should
        self.risk = risk
        self.style = style
        self.error = error
        self.calls = 0
        self.state = ""

    async def judge(self, state: str, questions: dict[str, Any]) -> dict[str, Any]:
        self.calls += 1
        self.state = state
        if self.error is not None:
            raise self.error
        return {
            "answers": {
                "should_reply": {"type": "noul", "noul": self.should},
                "risk": {"type": "noul", "noul": self.risk},
                "style": {
                    "type": "choice",
                    "choice": self.style,
                    "confidence": 0.8,
                },
            }
        }

    async def models(self) -> dict[str, Any]:
        return {"data": [{"id": "kev-latest"}]}

    async def close(self) -> None:
        pass


class FakeDeepSeek:
    def __init__(self) -> None:
        self.calls = 0
        self.caption_calls = 0
        self.messages: list[dict[str, Any]] = []

    async def chat(self, messages: list[dict[str, Any]], **kwargs: Any) -> str:
        self.calls += 1
        self.messages = messages
        return "在呢，怎么啦？"

    async def describe_image(self, data_url: str, **kwargs: Any) -> str:
        self.caption_calls += 1
        return "一只猫在笑"

    async def close(self) -> None:
        pass


class FakeImageLoader:
    def __init__(self) -> None:
        self.calls = 0

    async def load(self, attachment: ImageAttachment) -> LoadedImage:
        self.calls += 1
        payload = base64.b64encode(
            base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
            )
        ).decode("ascii")
        data_url = f"data:image/png;base64,{payload}"
        return LoadedImage(data_url=data_url, base64_data=payload, mime="image/png", size=68)

    async def close(self) -> None:
        pass


def build_handler(
    cfg: Config,
    tmp_path,
    *,
    kev: FakeKev | None = None,
    onebot: FakeOneBot | None = None,
    deepseek: FakeDeepSeek | None = None,
    image_loader: FakeImageLoader | None = None,
    stickers: StickerLibrary | None = None,
) -> tuple[BotHandler, FakeOneBot, FakeKev, FakeDeepSeek]:
    memory = Memory(tmp_path / "bot.sqlite3")
    fake_onebot = onebot or FakeOneBot()
    fake_kev = kev or FakeKev()
    fake_deepseek = deepseek or FakeDeepSeek()
    handler = BotHandler(
        cfg,
        memory,
        fake_onebot,  # type: ignore[arg-type]
        fake_kev,  # type: ignore[arg-type]
        fake_deepseek,  # type: ignore[arg-type]
        image_loader=image_loader,  # type: ignore[arg-type]
        stickers=stickers,
    )
    return handler, fake_onebot, fake_kev, fake_deepseek


async def settle() -> None:
    await asyncio.sleep(0.05)


async def test_addressed_group_message_gets_reply(cfg: Config, tmp_path) -> None:
    handler, onebot, kev, deepseek = build_handler(cfg, tmp_path)
    event = make_event("小深你好", addressed=True)

    await handler.handle_event(event)
    await settle()

    assert kev.calls == 1
    assert deepseek.calls == 1
    assert len(onebot.sent) == 1
    assert onebot.sent[0]["text"] == "在呢，怎么啦？"
    assert onebot.sent[0]["mention"] is True
    assert handler.stats.replied == 1
    await handler.close()


async def test_ambient_group_message_below_threshold_stays_silent(cfg: Config, tmp_path) -> None:
    handler, onebot, kev, _ = build_handler(cfg, tmp_path, kev=FakeKev(should=0.5))
    event = make_event("今天食堂的饭好难吃", addressed=False)

    await handler.handle_event(event)
    await settle()

    assert kev.calls == 1
    assert onebot.sent == []
    assert handler.stats.skipped == 1
    await handler.close()


async def test_ambient_message_calling_bot_name_uses_at_threshold(cfg: Config, tmp_path) -> None:
    handler, onebot, kev, _ = build_handler(cfg, tmp_path, kev=FakeKev(should=0.5))
    event = make_event("小深你觉得呢", addressed=False)

    await handler.handle_event(event)
    await settle()

    assert kev.calls == 1
    assert len(onebot.sent) == 1
    assert onebot.sent[0]["mention"] is False
    await handler.close()


async def test_risk_blocks_even_when_addressed(cfg: Config, tmp_path) -> None:
    handler, onebot, _, _ = build_handler(cfg, tmp_path, kev=FakeKev(should=0.99, risk=0.95))
    event = make_event("帮我做点危险的事", addressed=True)

    await handler.handle_event(event)
    await settle()

    assert onebot.sent == []
    await handler.close()


async def test_kev_failure_is_silent_by_default(cfg: Config, tmp_path) -> None:
    handler, onebot, kev, deepseek = build_handler(
        cfg, tmp_path, kev=FakeKev(error=KevError("down"))
    )
    event = make_event("小深在吗", addressed=True)

    await handler.handle_event(event)
    await settle()

    assert onebot.sent == []
    assert deepseek.calls == 0
    assert handler.stats.kev_failures == 1
    await handler.close()


async def test_command_bypasses_kev(cfg: Config, tmp_path) -> None:
    handler, onebot, kev, _ = build_handler(cfg, tmp_path)
    event = make_event("!ping", addressed=True)

    await handler.handle_event(event)
    await settle()

    assert onebot.sent and onebot.sent[0]["text"].startswith("pong")
    assert kev.calls == 0
    await handler.close()


def test_sanitize_reply_strips_markdown_and_prefix() -> None:
    assert sanitize_reply('**小深**：`你好`', 100, "小深") == "你好"
    assert sanitize_reply("第一句。第二句。" + "很长" * 100, 20, "小深").endswith(("。", "…"))


def test_parse_cq_string() -> None:
    event = parse_message_event(
        {
            "post_type": "message",
            "message_type": "group",
            "self_id": 999,
            "user_id": 123,
            "group_id": 456,
            "message_id": "m2",
            "message": "[CQ:at,qq=999] [CQ:reply,id=88] 你好[CQ:face,id=1]",
            "sender": {"card": "群名片", "nickname": "昵称"},
        }
    )
    assert event is not None
    assert event.addressed is True
    assert event.reply_id == "88"
    assert "你好" in event.text
    assert event.sender_name == "群名片"


def test_parse_image_segments() -> None:
    event = parse_message_event(
        {
            "post_type": "message",
            "message_type": "group",
            "self_id": 999,
            "user_id": 123,
            "group_id": 456,
            "message_id": "m3",
            "message": [
                {"type": "at", "data": {"qq": "999"}},
                {"type": "text", "data": {"text": "看看这个"}},
                {"type": "image", "data": {"url": "https://example.com/a.jpg", "file": "a.jpg"}},
                {"type": "mface", "data": {"summary": "[动画表情]", "url": "https://example.com/b.gif"}},
            ],
            "sender": {"nickname": "阿明"},
        }
    )
    assert event is not None
    assert len(event.images) == 2
    assert event.images[0].url == "https://example.com/a.jpg"
    assert event.images[0].file == "a.jpg"
    assert event.images[1].segment_type == "mface"
    assert "[图片]" in event.text
    assert "[动画表情]" in event.text


def make_image_event(text: str = "看看这个") -> MessageEvent:
    event = parse_message_event(
        {
            "post_type": "message",
            "message_type": "group",
            "self_id": 999,
            "user_id": 123,
            "group_id": 456,
            "message_id": "m-image",
            "message": [
                {"type": "at", "data": {"qq": "999"}},
                {"type": "text", "data": {"text": text}},
                {"type": "image", "data": {"url": "https://example.com/cat.png", "file": "cat.png"}},
            ],
            "sender": {"nickname": "阿明"},
        }
    )
    assert event is not None
    return event


async def test_image_caption_reaches_kev_and_vision_prompt(cfg: Config, tmp_path) -> None:
    vision_cfg = replace(cfg, vision_enabled=True, sticker_enabled=False)
    handler, onebot, kev, deepseek = build_handler(
        vision_cfg,
        tmp_path,
        image_loader=FakeImageLoader(),
    )
    event = make_image_event()

    await handler.handle_event(event)
    await settle()

    assert deepseek.caption_calls == 1
    assert "一只猫在笑" in kev.state
    assert "[图片内容 1：一只猫在笑]" in event.text
    last_content = deepseek.messages[-1]["content"]
    assert isinstance(last_content, list)
    assert any(
        part.get("type") == "image_url" and part["image_url"]["url"].startswith("data:image/png;base64,")
        for part in last_content
        if isinstance(part, dict)
    )
    assert onebot.sent and onebot.sent[0]["text"] == "在呢，怎么啦？"
    await handler.close()


async def test_sticker_library_blocks_unsafe_and_matches(tmp_path) -> None:
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    (tmp_path / "开心.png").write_bytes(png)
    (tmp_path / "杀了你妈.png").write_bytes(png)
    library = StickerLibrary(tmp_path, chance=1.0, block_words=("杀", "妈"))

    assert library.names == ["开心"]
    picked = library.pick("哈哈，开心", "playful", rng=random.Random(0))
    assert picked is not None
    assert picked.name == "开心"
    segment = picked.to_segment()
    assert segment is not None
    assert segment["type"] == "image"
    assert segment["data"]["file"].startswith("base64://")


def test_sticker_library_allows_all_styles(tmp_path) -> None:
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    (tmp_path / "无语.png").write_bytes(png)
    library = StickerLibrary(tmp_path, chance=1.0)

    for style in ("brief", "serious", "comfort", "playful"):
        assert library.pick("今天有点累", style, rng=random.Random(1)) is not None


async def test_sticker_attached_for_playful_reply(cfg: Config, tmp_path) -> None:
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    (tmp_path / "开心.png").write_bytes(png)
    sticker_cfg = replace(
        cfg,
        vision_enabled=False,
        sticker_enabled=True,
        sticker_dir=str(tmp_path),
        sticker_chance=1.0,
    )
    library = StickerLibrary(tmp_path, chance=1.0, block_words=("杀",))
    handler, onebot, _, _ = build_handler(
        sticker_cfg,
        tmp_path,
        kev=FakeKev(style="playful"),
        stickers=library,
    )
    event = make_event("开心吗", addressed=True)

    await handler.handle_event(event)
    await settle()

    assert onebot.sent
    sent = onebot.sent[0]
    assert "segments" in sent
    assert sent["segments"][0]["type"] == "text"
    assert sent["segments"][1]["type"] == "image"
    assert handler.stats.stickers_sent == 1
    await handler.close()
