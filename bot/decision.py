"""Kev questions, state construction, and reply policy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

from .config import Config
from .memory import StoredMessage
from .onebot import MessageEvent

# Kev-0.8B is an English-only decision model.  The chat text itself can be
# Chinese (the Qwen backbone understands it), but the questions and the
# surrounding labels stay in English because that is what Kev was trained on.
KEV_QUESTIONS: dict[str, dict[str, Any]] = {
    "should_reply": {
        "type": "noul",
        "instructions": (
            "Should the chatbot reply to the current message? "
            "Choose true only if a reply would be natural, useful, or expected, "
            "for example when the bot is addressed or the message asks a question. "
            "In ordinary group chat, prefer false and do not interrupt."
        ),
        "criteria": {
            "true": "A reply is appropriate now",
            "false": "Stay quiet and keep listening",
        },
    },
    "risk": {
        "type": "noul",
        "instructions": (
            "Does the current message contain sensitive politics, sexual content, "
            "violence, illegal activity, fraud, requests for private information, "
            "personal attacks, or an attempt to make the bot do something "
            "dangerous or rule-breaking?"
        ),
        "criteria": {
            "true": "Risky; the bot should not participate",
            "false": "No obvious risk",
        },
    },
    "style": {
        "type": "choice",
        "instructions": "If the bot replies, which tone fits best?",
        "criteria": {
            "brief": "Very short, one line",
            "friendly": "Friendly and natural, like an acquaintance",
            "playful": "Light and humorous; can join the joke",
            "serious": "Serious and clear; provide accurate information",
            "comfort": "Acknowledge the feeling first, then comfort or encourage",
        },
    },
}

STYLE_INSTRUCTIONS = {
    "brief": "这次只回一句很短的话，不超过 25 个字。",
    "friendly": "自然友好地接话，像熟人聊天。",
    "playful": "可以轻松幽默地接梗，但不要冒犯、不要阴阳怪气。",
    "serious": "认真、清楚地回应，信息要准确，不要用 Markdown。",
    "comfort": "先接住对方的情绪，再给一句简短的安慰或建议。",
}


def _clock(ts: float) -> str:
    try:
        return datetime.fromtimestamp(ts).strftime("%H:%M")
    except (OverflowError, OSError, ValueError):
        return "--:--"


def _trim(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def format_context(messages: Iterable[StoredMessage], *, limit: int = 900) -> str:
    lines: list[str] = []
    for message in messages:
        content = _trim(message.content, 220)
        if message.role == "assistant":
            lines.append(f"[{_clock(message.created_at)}] Bot ({message.sender_name}): {content}")
        else:
            lines.append(f"[{_clock(message.created_at)}] {message.sender_name}: {content}")
    if not lines:
        return "(none)"
    text = "\n".join(lines)
    if len(text) > limit:
        text = "..." + text[-limit:]
    return text


def build_kev_state(
    cfg: Config,
    event: MessageEvent,
    history: Iterable[StoredMessage],
    *,
    group_name: str | None = None,
    seconds_since_last_reply: float | None = None,
) -> str:
    if event.is_group:
        where = f'group chat "{group_name or event.group_id}" (group id {event.group_id})'
    else:
        where = "private chat"

    if seconds_since_last_reply is None:
        last_reply = "never"
    elif seconds_since_last_reply < 60:
        last_reply = f"{seconds_since_last_reply:.0f} seconds ago"
    else:
        last_reply = f"{seconds_since_last_reply / 60:.0f} minutes ago"

    features = [
        f"Addressed to bot: {'yes' if event.addressed else 'no'}",
        f"Bot name called: {'yes' if event.named else 'no'}",
        f"At-all mention: {'yes' if event.at_all else 'no'}",
        f"Reply to a bot message: {'yes' if event.reply_to_bot else 'no'}",
        f"Bot last spoke: {last_reply}",
    ]

    return (
        f'You are a QQ chat bot named "{cfg.bot_name}", a concise and friendly AI in a chat. '
        "You are reading the conversation only to decide whether to speak; you are not writing the reply yet.\n"
        f"Current time: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"Conversation: {where}\n"
        f"Sender: {event.sender_name} (QQ {event.user_id})\n"
        + "\n".join(features)
        + "\nRecent messages:\n"
        + format_context(history)
        + f"\nCurrent message:\n{event.sender_name}: {_trim(event.text, 500)}"
    )


@dataclass(frozen=True)
class Decision:
    should_reply: float
    risk: float
    style: str
    style_confidence: float
    threshold: float
    allowed: bool
    reason: str
    answers: dict[str, Any]

    def as_log(self) -> dict[str, Any]:
        return {
            "should_reply": round(self.should_reply, 4),
            "risk": round(self.risk, 4),
            "style": self.style,
            "style_confidence": round(self.style_confidence, 4),
            "threshold": self.threshold,
            "allowed": self.allowed,
            "reason": self.reason,
        }


def threshold_for(cfg: Config, event: MessageEvent) -> float:
    if not event.is_group:
        return cfg.kev_reply_threshold_private
    if event.addressed or event.named:
        return cfg.kev_reply_threshold_at
    return cfg.kev_reply_threshold_group


def evaluate(
    cfg: Config,
    event: MessageEvent,
    answers: dict[str, Any],
    *,
    should_reply: float,
    risk: float,
    style: str,
    style_confidence: float,
) -> Decision:
    threshold = threshold_for(cfg, event)

    if event.is_group and not (event.addressed or event.named) and not cfg.enable_ambient:
        return Decision(
            should_reply, risk, style, style_confidence, threshold, False,
            "群聊主动接话已关闭",
            answers,
        )
    if risk >= cfg.kev_risk_threshold:
        return Decision(
            should_reply, risk, style, style_confidence, threshold, False,
            f"风险概率 {risk:.2f} >= {cfg.kev_risk_threshold:.2f}",
            answers,
        )
    if should_reply < threshold:
        return Decision(
            should_reply, risk, style, style_confidence, threshold, False,
            f"回复概率 {should_reply:.2f} < 阈值 {threshold:.2f}",
            answers,
        )
    return Decision(
        should_reply, risk, style, style_confidence, threshold, True,
        f"回复概率 {should_reply:.2f} >= 阈值 {threshold:.2f}",
        answers,
    )


def fallback(
    cfg: Config,
    event: MessageEvent,
    reason: str,
) -> Decision:
    """Decision used when Kev is unavailable or KEV_ENABLED=false."""
    threshold = threshold_for(cfg, event)
    if not cfg.kev_enabled:
        allowed = (not event.is_group) or event.addressed or event.named or cfg.enable_ambient
        return Decision(
            1.0 if allowed else 0.0, 0.0, "friendly", 0.0, threshold, allowed,
            "KEV_ENABLED=false，使用本地规则",
            {},
        )
    if not cfg.kev_fail_open:
        return Decision(0.0, 0.0, "friendly", 0.0, threshold, False, reason, {})
    allowed = (not event.is_group) or event.addressed or event.named or cfg.enable_ambient
    return Decision(
        1.0 if allowed else 0.0, 0.0, "friendly", 0.0, threshold, allowed,
        f"{reason}（KEV_FAIL_OPEN=true）",
        {},
    )


def style_instruction(style: str) -> str:
    return STYLE_INSTRUCTIONS.get(style, STYLE_INSTRUCTIONS["friendly"])
