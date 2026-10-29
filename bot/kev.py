"""Client for a local Kev System One server."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

log = logging.getLogger(__name__)


class KevError(RuntimeError):
    pass


class KevClient:
    def __init__(self, base_url: str, model: str = "kev-latest", api_key: str = "", timeout: float = 20.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=httpx.Timeout(timeout, connect=5.0),
        )

    async def models(self) -> dict[str, Any]:
        try:
            response = await self._client.get("/v1/models", timeout=min(self.timeout, 8.0))
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, dict) else {"raw": data}
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:500]
            raise KevError(f"Kev /v1/models 返回 {exc.response.status_code}: {body}") from exc
        except httpx.HTTPError as exc:
            raise KevError(f"无法连接 Kev：{exc}") from exc

    async def judge(self, state: str, questions: dict[str, Any]) -> dict[str, Any]:
        payload = {"state": state, "model": self.model, "questions": questions}
        started = time.perf_counter()
        try:
            response = await self._client.post("/v1/systemone", json=payload)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:800]
            raise KevError(f"Kev 判断失败 HTTP {exc.response.status_code}: {body}") from exc
        except httpx.HTTPError as exc:
            raise KevError(f"Kev 请求失败：{exc}") from exc
        except ValueError as exc:
            raise KevError(f"Kev 返回了非 JSON 内容：{exc}") from exc

        elapsed_ms = (time.perf_counter() - started) * 1000
        if not isinstance(data, dict) or not isinstance(data.get("answers"), dict):
            raise KevError(f"Kev 返回格式异常：{str(data)[:500]}")
        log.info(
            "Kev 判断完成 %.0fms (model_latency=%sms)",
            elapsed_ms,
            data.get("latency_ms", "?"),
        )
        return data

    async def close(self) -> None:
        await self._client.aclose()

    @staticmethod
    def noul(answers: dict[str, Any], key: str, default: float) -> float:
        answer = answers.get(key)
        if not isinstance(answer, dict):
            return default
        value = answer.get("noul")
        try:
            return min(1.0, max(0.0, float(value)))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def choice(answers: dict[str, Any], key: str, default: str) -> tuple[str, float]:
        answer = answers.get(key)
        if not isinstance(answer, dict):
            return default, 0.0
        value = answer.get("choice")
        if not isinstance(value, str):
            return default, 0.0
        try:
            confidence = float(answer.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        return value, confidence
