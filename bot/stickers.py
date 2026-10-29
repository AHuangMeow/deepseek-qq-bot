"""Curated local sticker library.

Files are sent as OneBot image segments using base64, so NapCat does not need
a bind mount for the sticker directory.
"""

from __future__ import annotations

import base64
import logging
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_EXT_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
}

# Filename keywords -> words that may appear in a reply.  This is intentionally
# small: the filename itself is also matched directly.
_SYNONYMS: dict[str, tuple[str, ...]] = {
    "开心": ("哈哈", "笑", "开心", "好耶", "太棒"),
    "无语": ("无语", "服了", "离谱", "难绷", "绷不住"),
    "疑惑": ("疑惑", "为什么", "怎么", "问号", "?", "？"),
    "晚安": ("晚安", "睡了", "睡觉", "困"),
    "可爱": ("可爱", "萌", "猫猫", "好可爱"),
    "期待": ("期待", "等", "想要", "蹲"),
    "委屈": ("委屈", "难过", "哭", "呜呜"),
    "盯": ("盯", "看着", "看你", "看"),
    "偷看": ("偷看", "悄悄", "瞄"),
    "不赖": ("不赖", "不错", "可以啊", "厉害"),
    "难道说": ("难道", "不会吧", "真的假的"),
}


@dataclass(frozen=True)
class Sticker:
    path: Path
    name: str
    mime: str
    size: int

    def to_segment(self) -> dict[str, Any] | None:
        try:
            data = self.path.read_bytes()
        except OSError:
            log.warning("读取表情包失败：%s", self.path)
            return None
        encoded = base64.b64encode(data).decode("ascii")
        return {"type": "image", "data": {"file": f"base64://{encoded}"}}


class StickerLibrary:
    def __init__(
        self,
        directory: Path,
        *,
        chance: float = 0.2,
        max_bytes: int = 8 * 1024 * 1024,
        block_words: tuple[str, ...] = (),
    ):
        self.directory = directory
        self.chance = max(0.0, min(1.0, chance))
        self.max_bytes = max_bytes
        self.block_words = tuple(word.casefold() for word in block_words if word)
        self.stickers: list[Sticker] = []
        self.skipped = 0
        self.reload()

    def reload(self) -> None:
        self.stickers = []
        self.skipped = 0
        if not self.directory.is_dir():
            log.warning("表情包目录不存在：%s", self.directory)
            return
        for path in sorted(self.directory.iterdir()):
            if not path.is_file():
                continue
            mime = _EXT_MIME.get(path.suffix.lower())
            if mime is None:
                continue
            if self._blocked(path.stem):
                self.skipped += 1
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if size > self.max_bytes:
                self.skipped += 1
                continue
            self.stickers.append(Sticker(path=path, name=path.stem, mime=mime, size=size))
        log.info(
            "表情包库：%s（可用 %d 张，跳过 %d 张）",
            self.directory,
            len(self.stickers),
            self.skipped,
        )

    def _blocked(self, name: str) -> bool:
        folded = name.casefold()
        return any(word in folded for word in self.block_words)

    @property
    def names(self) -> list[str]:
        return [sticker.name for sticker in self.stickers]

    def pick(
        self,
        text: str,
        style: str,
        *,
        rng: random.Random | None = None,
    ) -> Sticker | None:
        if not self.stickers:
            return None
        rng = rng or random
        probability = self.chance * (1.3 if style == "playful" else 1.0)
        if rng.random() > min(1.0, probability):
            return None

        best: tuple[int, Sticker] | None = None
        for sticker in self.stickers:
            score = self._score(sticker.name, text)
            if score and (best is None or score > best[0]):
                best = (score, sticker)
        if best is not None:
            return best[1]
        return rng.choice(self.stickers)

    @staticmethod
    def _score(name: str, text: str) -> int:
        score = 0
        if len(name) >= 2 and name in text:
            score += 10
        for token in re.split(r"[\s_\-—·]+", name):
            if len(token) >= 2 and token in text:
                score += 5
        folded = name.casefold()
        for keyword, synonyms in _SYNONYMS.items():
            if keyword in name and any(word.casefold() in text.casefold() for word in synonyms):
                score += 3
        return score
