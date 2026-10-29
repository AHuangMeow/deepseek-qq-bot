"""DeepSeek chat-completions client (OpenAI-compatible)."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

log = logging.getLogger(__name__)


class DeepSeekError(RuntimeError):
    pass


class DeepSeekClient:
    # deepseek-flash enables thinking by default.  Thinking tokens count toward
    # max_tokens, so too small a budget can leave `content` empty.
    MIN_THINKING_TOKENS = 2048

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-flash",
        *,
        temperature: float = 1.1,
        max_tokens: int = 320,
        timeout: float = 60.0,
        thinking: bool = False,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.thinking = thinking
        if self.thinking and self.max_tokens < self.MIN_THINKING_TOKENS:
            log.warning(
                "DEEPSEEK_THINKING=true，max_tokens=%s 太小；运行时至少按 %s 发送",
                self.max_tokens,
                self.MIN_THINKING_TOKENS,
            )
        self._client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(timeout, connect=10.0),
        )

    @property
    def endpoint(self) -> str:
        return f"{self.base_url}/chat/completions"

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        requested_tokens = max_tokens or self.max_tokens
        if self.thinking:
            requested_tokens = max(requested_tokens, self.MIN_THINKING_TOKENS)
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature if temperature is None else temperature,
            "max_tokens": requested_tokens,
            "stream": False,
            # deepseek-flash enables thinking by default.  QQ chat needs short
            # latency, so use non-thinking mode unless explicitly configured.
            "thinking": {"type": "enabled" if self.thinking else "disabled"},
        }
        if self.thinking:
            payload["reasoning_effort"] = "low"
        started = time.perf_counter()
        last_error: Exception | None = None
        for attempt in range(1, 4):
            try:
                response = await self._client.post(self.endpoint, json=payload)
                if response.status_code == 429 or response.status_code >= 500:
                    body = response.text[:500]
                    last_error = DeepSeekError(f"DeepSeek HTTP {response.status_code}: {body}")
                    if attempt < 3:
                        delay = 1.5 * attempt
                        log.warning("DeepSeek 返回 %s，%.1fs 后重试 (%d/3)", response.status_code, delay, attempt)
                        await asyncio.sleep(delay)
                        continue
                    raise last_error
                if response.status_code >= 400:
                    body = response.text[:800]
                    raise DeepSeekError(f"DeepSeek HTTP {response.status_code}: {body}")
                data = response.json()
                break
            except httpx.TransportError as exc:
                last_error = DeepSeekError(f"DeepSeek 网络错误：{exc}")
                if attempt < 3:
                    delay = 1.5 * attempt
                    log.warning("DeepSeek 网络错误，%.1fs 后重试 (%d/3)：%s", delay, attempt, exc)
                    await asyncio.sleep(delay)
                    continue
                raise last_error
            except ValueError as exc:
                raise DeepSeekError(f"DeepSeek 返回了非 JSON 内容：{exc}") from exc
        else:  # pragma: no cover - loop always returns or raises
            raise last_error or DeepSeekError("DeepSeek 请求失败")

        try:
            choice = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise DeepSeekError(f"DeepSeek 响应格式异常：{str(data)[:500]}") from exc

        content = choice.get("content")
        if isinstance(content, list):
            content = "".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )
        if not isinstance(content, str) or not content.strip():
            try:
                finish_reason = data["choices"][0].get("finish_reason")
            except (KeyError, IndexError, TypeError):
                finish_reason = None
            if finish_reason == "length":
                raise DeepSeekError(
                    "DeepSeek 回复被 max_tokens 截断；"
                    "DEEPSEEK_THINKING=true 时建议 DEEPSEEK_MAX_TOKENS>=2048"
                )
            raise DeepSeekError(f"DeepSeek 返回了空回复：{str(data)[:500]}")

        usage = data.get("usage") or {}
        elapsed = time.perf_counter() - started
        log.info(
            "DeepSeek 回复 %.2fs tokens=%s/%s",
            elapsed,
            usage.get("prompt_tokens", "?"),
            usage.get("completion_tokens", "?"),
        )
        return content.strip()

    async def describe_image(
        self,
        data_url: str,
        *,
        detail: str = "low",
        max_tokens: int = 90,
    ) -> str:
        """Caption an image for Kev.  Images are only valid in user messages."""
        messages: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "请用简体中文一句话描述这张图片或表情包的内容和情绪，"
                            "最多 50 个字。图中有文字就一并转写。只输出描述，不要加引号。"
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": data_url, "detail": detail},
                    },
                ],
            }
        ]
        return await self.chat(messages, max_tokens=max_tokens, temperature=0.2)

    async def ping(self) -> str:
        return await self.chat(
            [{"role": "user", "content": "只回复两个字：正常"}],
            max_tokens=32,
        )

    async def close(self) -> None:
        await self._client.aclose()
