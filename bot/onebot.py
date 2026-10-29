"""Minimal OneBot v11 client for NapCat's forward WebSocket server."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import websockets
from websockets.exceptions import ConnectionClosed

log = logging.getLogger(__name__)

_CQ_AT = re.compile(r"\[CQ:at,qq=([^,\]]+)(?:,[^\]]*)?\]")
_CQ_REPLY = re.compile(r"\[CQ:reply,id=([^,\]]+)(?:,[^\]]*)?\]")
_CQ_IMAGE = re.compile(r"\[CQ:(image|mface),([^\]]*)\]")
_CQ_ANY = re.compile(r"\[CQ:[^\]]+\]")


class OneBotError(RuntimeError):
    pass


@dataclass(frozen=True)
class ImageAttachment:
    """Image reference from a OneBot message segment."""

    url: str = ""
    file: str = ""
    summary: str = ""
    sub_type: str = ""
    segment_type: str = "image"


@dataclass
class MessageEvent:
    message_id: str
    message_type: str  # "group" | "private"
    user_id: int
    self_id: int
    sender_name: str
    text: str
    segments: list[dict[str, Any]] = field(default_factory=list)
    images: list[ImageAttachment] = field(default_factory=list)
    image_captions: list[str] = field(default_factory=list)
    image_data_urls: list[str] = field(default_factory=list)
    group_id: int | None = None
    addressed: bool = False
    named: bool = False
    at_all: bool = False
    reply_id: str | None = None
    reply_to_bot: bool = False
    time: int = 0
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def is_group(self) -> bool:
        return self.message_type == "group"

    @property
    def conversation_id(self) -> str:
        if self.is_group:
            return f"group:{self.group_id}"
        return f"private:{self.user_id}"


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _cq_params(raw: str) -> dict[str, str]:
    params: dict[str, str] = {}
    for part in raw.split(","):
        key, sep, value = part.partition("=")
        if sep:
            params[key.strip()] = value.strip()
    return params


def _segments_from_string(
    raw: str, self_id: int
) -> tuple[str, list[dict[str, Any]], list[ImageAttachment], bool, bool, str | None]:
    addressed = False
    at_all = False
    reply_id: str | None = None
    images: list[ImageAttachment] = []

    def at_repl(match: re.Match[str]) -> str:
        nonlocal addressed, at_all
        token = match.group(1)
        if token == "all":
            at_all = True
        elif _as_int(token) == self_id:
            addressed = True
        return ""

    def reply_repl(match: re.Match[str]) -> str:
        nonlocal reply_id
        reply_id = str(match.group(1))
        return ""

    def image_repl(match: re.Match[str]) -> str:
        seg_type = match.group(1)
        params = _cq_params(match.group(2))
        images.append(
            ImageAttachment(
                url=params.get("url", ""),
                file=params.get("file", ""),
                summary=params.get("summary", ""),
                sub_type=params.get("sub_type", ""),
                segment_type=seg_type,
            )
        )
        return "[动画表情]" if seg_type == "mface" else "[图片]"

    text = _CQ_AT.sub(at_repl, raw)
    text = _CQ_REPLY.sub(reply_repl, text)
    text = _CQ_IMAGE.sub(image_repl, text)
    text = _CQ_ANY.sub("", text)
    return text.strip(), [], images, addressed, at_all, reply_id


def parse_message_event(raw: dict[str, Any]) -> MessageEvent | None:
    """Turn a OneBot message event into a MessageEvent.

    Handles both array-format and string-format messages.  Returns None for
    events that are not ordinary messages.
    """
    if raw.get("post_type") != "message":
        return None
    message_type = raw.get("message_type")
    if message_type not in {"group", "private"}:
        return None

    self_id = _as_int(raw.get("self_id"))
    user_id = _as_int(raw.get("user_id"))
    group_id = _as_int(raw.get("group_id")) or None
    sender = raw.get("sender") or {}
    sender_name = str(sender.get("card") or sender.get("nickname") or user_id)

    message = raw.get("message")
    addressed = False
    at_all = False
    reply_id: str | None = None
    segments: list[dict[str, Any]] = []
    images: list[ImageAttachment] = []

    if isinstance(message, str):
        text, segments, images, addressed, at_all, reply_id = _segments_from_string(message, self_id)
    elif isinstance(message, list):
        parts: list[str] = []
        for seg in message:
            if not isinstance(seg, dict):
                continue
            seg_type = seg.get("type")
            data = seg.get("data") or {}
            segments.append(seg)
            if seg_type == "text":
                parts.append(str(data.get("text", "")))
            elif seg_type == "at":
                qq = str(data.get("qq", ""))
                name = data.get("name")
                if qq == "all":
                    at_all = True
                elif _as_int(qq) == self_id:
                    addressed = True
                elif name:
                    parts.append(f"@{name}")
            elif seg_type == "reply":
                reply_id = str(data.get("id") or data.get("message_id") or "") or None
            elif seg_type in {"image", "mface"}:
                images.append(
                    ImageAttachment(
                        url=str(data.get("url") or ""),
                        file=str(data.get("file") or data.get("path") or ""),
                        summary=str(data.get("summary") or ""),
                        sub_type=str(data.get("sub_type") or ""),
                        segment_type=seg_type,
                    )
                )
                parts.append("[动画表情]" if seg_type == "mface" else "[图片]")
            elif seg_type == "face":
                parts.append("[表情]")
            elif seg_type == "record":
                parts.append("[语音]")
            elif seg_type == "video":
                parts.append("[视频]")
            elif seg_type == "file":
                parts.append("[文件]")
            elif seg_type == "forward":
                parts.append("[合并转发]")
            elif seg_type in {"json", "xml"}:
                parts.append("[卡片]")
            elif seg_type == "markdown":
                parts.append(str(data.get("content", "")))
        text = "".join(parts).strip()
    else:
        return None

    if not text and not addressed and not reply_id and not at_all:
        return None

    return MessageEvent(
        message_id=str(raw.get("message_id", "")),
        message_type=str(message_type),
        user_id=user_id,
        self_id=self_id,
        sender_name=sender_name,
        text=text,
        segments=segments,
        images=images,
        group_id=group_id,
        addressed=addressed,
        at_all=at_all,
        reply_id=reply_id,
        time=_as_int(raw.get("time")),
        raw=raw,
    )


class OneBotClient:
    """Forward-WS client with request/response correlation and auto-reconnect."""

    def __init__(self, url: str, token: str = "", *, max_message_size: int = 16 * 1024 * 1024):
        self.url = url
        self.token = token
        self.max_message_size = max_message_size
        self.ws: Any = None
        self._connected = asyncio.Event()
        self._stop = asyncio.Event()
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._tasks: set[asyncio.Task[Any]] = set()
        self.self_id: int = 0
        self.nickname: str = ""

    async def run(self, on_event: Callable[[MessageEvent], Awaitable[None]]) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            try:
                headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
                async with websockets.connect(
                    self.url,
                    additional_headers=headers,
                    ping_interval=20,
                    ping_timeout=20,
                    max_size=self.max_message_size,
                    close_timeout=5,
                ) as ws:
                    self.ws = ws
                    self._connected.set()
                    backoff = 1.0
                    log.info("已连接 NapCat OneBot WS: %s", self.url)
                    async for raw_text in ws:
                        try:
                            payload = json.loads(raw_text)
                        except json.JSONDecodeError:
                            log.warning("收到非法 JSON：%.200s", raw_text)
                            continue
                        await self._dispatch(payload, on_event)
            except asyncio.CancelledError:
                raise
            except ConnectionClosed as exc:
                log.warning("OneBot WS 断开：%s", exc)
            except OSError as exc:
                log.warning("OneBot WS 连接失败：%s", exc)
            except Exception:
                log.exception("OneBot WS 循环异常")
            finally:
                self.ws = None
                self._connected.clear()
                self._fail_pending(OneBotError("OneBot WS 已断开"))
            if self._stop.is_set():
                break
            log.info("%.1f 秒后重连 NapCat ...", backoff)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=backoff)
            except asyncio.TimeoutError:
                pass
            backoff = min(backoff * 2, 30.0)

    async def _dispatch(
        self,
        payload: dict[str, Any],
        on_event: Callable[[MessageEvent], Awaitable[None]],
    ) -> None:
        echo = payload.get("echo")
        if echo is not None:
            future = self._pending.pop(str(echo), None)
            if future and not future.done():
                future.set_result(payload)
            return

        if payload.get("post_type") == "meta_event":
            meta = payload.get("meta_event_type")
            if meta == "lifecycle":
                log.info("OneBot 生命周期事件：%s", payload.get("sub_type", ""))
            return

        event = parse_message_event(payload)
        if event is None:
            return

        task = asyncio.create_task(self._safe_event(on_event, event))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    @staticmethod
    async def _safe_event(on_event: Callable[[MessageEvent], Awaitable[None]], event: MessageEvent) -> None:
        try:
            await on_event(event)
        except Exception:
            log.exception("处理消息事件失败 message_id=%s", event.message_id)

    async def _fail_pending(self, exc: Exception) -> None:
        pending, self._pending = self._pending, {}
        for future in pending.values():
            if not future.done():
                future.set_exception(exc)

    async def wait_connected(self, timeout: float = 30.0) -> None:
        try:
            await asyncio.wait_for(self._connected.wait(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise OneBotError("等待 NapCat 连接超时") from exc

    async def call(self, action: str, params: dict[str, Any] | None = None, timeout: float = 30.0) -> Any:
        try:
            await asyncio.wait_for(self._connected.wait(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise OneBotError("NapCat 尚未连接") from exc

        ws = self.ws
        if ws is None:
            raise OneBotError("NapCat 尚未连接")

        echo = uuid.uuid4().hex
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[echo] = future
        try:
            await ws.send(json.dumps({"action": action, "params": params or {}, "echo": echo}, ensure_ascii=False))
            payload = await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise OneBotError(f"OneBot 调用超时：{action}") from exc
        finally:
            self._pending.pop(echo, None)

        if payload.get("status") == "failed" or _as_int(payload.get("retcode"), -1) != 0:
            raise OneBotError(f"OneBot 调用失败：{action} retcode={payload.get('retcode')} data={payload.get('data')!r}")
        return payload.get("data")

    async def get_login_info(self) -> dict[str, Any]:
        data = await self.call("get_login_info", timeout=10)
        if isinstance(data, dict):
            self.self_id = _as_int(data.get("user_id"))
            self.nickname = str(data.get("nickname", ""))
        return data or {}

    async def get_msg(self, message_id: str) -> dict[str, Any] | None:
        try:
            data = await self.call("get_msg", {"message_id": message_id}, timeout=10)
            return data if isinstance(data, dict) else None
        except OneBotError:
            return None

    async def get_group_info(self, group_id: int) -> dict[str, Any] | None:
        try:
            data = await self.call("get_group_info", {"group_id": group_id}, timeout=10)
            return data if isinstance(data, dict) else None
        except OneBotError:
            return None

    async def send_group_segments(
        self,
        group_id: int,
        segments: list[dict[str, Any]],
        *,
        user_id: int | None = None,
        mention: bool = False,
        reply_id: str | None = None,
    ) -> str | None:
        message: list[dict[str, Any]] = []
        if reply_id:
            message.append({"type": "reply", "data": {"id": str(reply_id)}})
        if mention and user_id is not None:
            message.append({"type": "at", "data": {"qq": str(user_id)}})
            message.append({"type": "text", "data": {"text": " "}})
        message.extend(segments)
        data = await self.call("send_group_msg", {"group_id": group_id, "message": message})
        if isinstance(data, dict):
            return str(data.get("message_id")) if data.get("message_id") is not None else None
        return None

    async def send_group_text(
        self,
        group_id: int,
        text: str,
        *,
        user_id: int | None = None,
        mention: bool = False,
        reply_id: str | None = None,
    ) -> str | None:
        return await self.send_group_segments(
            group_id,
            [{"type": "text", "data": {"text": text}}],
            user_id=user_id,
            mention=mention,
            reply_id=reply_id,
        )

    async def send_private_segments(
        self,
        user_id: int,
        segments: list[dict[str, Any]],
        *,
        reply_id: str | None = None,
    ) -> str | None:
        message: list[dict[str, Any]] = []
        if reply_id:
            message.append({"type": "reply", "data": {"id": str(reply_id)}})
        message.extend(segments)
        data = await self.call("send_private_msg", {"user_id": user_id, "message": message})
        if isinstance(data, dict):
            return str(data.get("message_id")) if data.get("message_id") is not None else None
        return None

    async def send_private_text(self, user_id: int, text: str, *, reply_id: str | None = None) -> str | None:
        return await self.send_private_segments(
            user_id,
            [{"type": "text", "data": {"text": text}}],
            reply_id=reply_id,
        )

    async def close(self) -> None:
        self._stop.set()
        ws = self.ws
        if ws is not None:
            try:
                await ws.close()
            except Exception:
                log.debug("关闭 OneBot WS 时出错", exc_info=True)
        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
