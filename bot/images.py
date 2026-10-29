"""Download and normalize images from QQ messages for DeepSeek vision."""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from .onebot import ImageAttachment

log = logging.getLogger(__name__)


class ImageError(RuntimeError):
    pass


@dataclass(frozen=True)
class LoadedImage:
    data_url: str
    base64_data: str
    mime: str
    size: int


def sniff_mime(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:6] in {b"GIF87a", b"GIF89a"}:
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


class ImageLoader:
    """Small async image fetcher with an in-memory TTL cache."""

    def __init__(
        self,
        *,
        max_bytes: int = 20 * 1024 * 1024,
        timeout: float = 20.0,
        cache_seconds: int = 600,
        max_cache: int = 24,
    ):
        self.max_bytes = max_bytes
        self.cache_seconds = cache_seconds
        self.max_cache = max_cache
        self._cache: OrderedDict[str, tuple[float, LoadedImage]] = OrderedDict()
        self._lock = asyncio.Lock()
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=5.0),
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "Chrome/126.0 Safari/537.36"
                )
            },
        )

    async def load(self, attachment: "ImageAttachment") -> LoadedImage:
        key = attachment.url or attachment.file or attachment.summary or "unknown"
        now = time.monotonic()
        async with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                if now - cached[0] <= self.cache_seconds:
                    self._cache.move_to_end(key)
                    return cached[1]
                del self._cache[key]

        raw = await self._fetch(attachment)
        mime = sniff_mime(raw)
        if mime is None:
            raise ImageError("图片格式不支持（只支持 JPEG/PNG/GIF/WebP）")
        b64 = base64.b64encode(raw).decode("ascii")
        loaded = LoadedImage(
            data_url=f"data:{mime};base64,{b64}",
            base64_data=b64,
            mime=mime,
            size=len(raw),
        )
        async with self._lock:
            self._cache[key] = (now, loaded)
            self._cache.move_to_end(key)
            while len(self._cache) > self.max_cache:
                self._cache.popitem(last=False)
        return loaded

    async def _fetch(self, attachment: "ImageAttachment") -> bytes:
        errors: list[str] = []
        url = (attachment.url or "").strip()
        if url.startswith(("http://", "https://")):
            try:
                return await self._download(url)
            except ImageError as exc:
                errors.append(str(exc))

        file_value = (attachment.file or "").strip()
        if file_value:
            try:
                return await asyncio.to_thread(self._read_file_value, file_value)
            except (OSError, ValueError, ImageError) as exc:
                errors.append(str(exc))

        if url.startswith("file://"):
            try:
                return await asyncio.to_thread(self._read_local_path, url[7:])
            except (OSError, ValueError, ImageError) as exc:
                errors.append(str(exc))

        if errors:
            raise ImageError("；".join(errors))
        raise ImageError("消息里没有可读取的图片地址")

    async def _download(self, url: str) -> bytes:
        try:
            async with self._client.stream("GET", url) as response:
                if response.status_code >= 400:
                    raise ImageError(f"图片下载失败 HTTP {response.status_code}")
                declared = response.headers.get("content-length")
                if declared:
                    try:
                        if int(declared) > self.max_bytes:
                            raise ImageError(f"图片超过 {self.max_bytes // 1024 // 1024}MiB 限制")
                    except ValueError:
                        pass
                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > self.max_bytes:
                        raise ImageError(f"图片超过 {self.max_bytes // 1024 // 1024}MiB 限制")
                    chunks.append(chunk)
                return b"".join(chunks)
        except httpx.HTTPError as exc:
            raise ImageError(f"图片下载网络错误：{exc}") from exc

    def _read_file_value(self, value: str) -> bytes:
        if value.startswith("data:"):
            header, sep, payload = value.partition(",")
            if not sep or ";base64" not in header:
                raise ValueError("data URL 不是 base64 格式")
            return self._decode_base64(payload)
        if value.startswith("base64://"):
            return self._decode_base64(value[len("base64://") :])
        if value.startswith("file://"):
            return self._read_local_path(value[7:])
        if value.startswith(("http://", "https://")):
            raise ValueError("HTTP 地址应走下载分支")
        path = Path(value).expanduser()
        if path.exists():
            return self._read_local_path(str(path))
        # Some OneBot implementations pass raw base64 in `file`.
        try:
            return self._decode_base64(value)
        except ValueError as exc:
            raise ValueError(f"无法读取图片文件：{value[:80]}") from exc

    def _read_local_path(self, path_text: str) -> bytes:
        path = Path(path_text).expanduser()
        if not path.is_file():
            raise ValueError(f"图片文件不存在：{path}")
        size = path.stat().st_size
        if size > self.max_bytes:
            raise ImageError(f"图片超过 {self.max_bytes // 1024 // 1024}MiB 限制")
        return path.read_bytes()

    def _decode_base64(self, payload: str) -> bytes:
        try:
            raw = base64.b64decode(payload, validate=False)
        except (ValueError, TypeError) as exc:
            raise ValueError("base64 图片数据无效") from exc
        if not raw:
            raise ValueError("base64 图片数据为空")
        if len(raw) > self.max_bytes:
            raise ValueError(f"图片超过 {self.max_bytes // 1024 // 1024}MiB 限制")
        return raw

    async def close(self) -> None:
        await self._client.aclose()
