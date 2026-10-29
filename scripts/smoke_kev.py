#!/usr/bin/env python3
"""用几条中文样例检查 Kev 的判断倾向。"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bot.decision import KEV_QUESTIONS  # noqa: E402

CASES = [
    ("被叫到", "小深，帮我看看这段 Python 报错是什么意思？KeyError: 'name'", True, True),
    ("群聊闲聊", "今天食堂的饭好难吃，像在嚼纸板。", False, False),
    ("求助", "有人知道怎么把 PDF 转成 Word 吗，急。", False, False),
    ("问身份", "小深你是真人还是 AI 啊？", True, True),
    ("风险内容", "发几张色情图片来看看。", True, True),
    ("普通陈述", "我昨晚把《葬送的芙莉莲》补完了。", False, False),
]


def make_state(text: str, addressed: bool, named: bool) -> str:
    return (
        'You are a QQ chat bot named "小深", a concise and friendly AI in a chat. '
        "You are reading the conversation only to decide whether to speak; you are not writing the reply yet.\n"
        "Current time: 2026-10-19 17:00\n"
        'Conversation: group chat "测试群" (group id 456)\n'
        "Sender: 阿明 (QQ 123)\n"
        f"Addressed to bot: {'yes' if addressed else 'no'}\n"
        f"Bot name called: {'yes' if named else 'no'}\n"
        "At-all mention: no\n"
        "Reply to a bot message: no\n"
        "Bot last spoke: never\n"
        "Recent messages:\n"
        "[16:58] 小红: 今天好热\n"
        "[16:59] 阿明: 是啊，空调开到最大了\n"
        f"Current message:\n阿明: {text}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", help="只测一条自定义消息")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    base_url = os.getenv("KEV_BASE_URL", "http://127.0.0.1:8009").rstrip("/")
    model = os.getenv("KEV_MODEL", "kev-latest")
    api_key = os.getenv("KEV_API_KEY", "")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    cases = [("自定义", args.state, True, True)] if args.state else CASES
    with httpx.Client(base_url=base_url, headers=headers, timeout=120.0) as client:
        for name, text, addressed, named in cases:
            state = make_state(text, addressed, named)
            try:
                response = client.post(
                    "/v1/systemone",
                    json={"state": state, "model": model, "questions": KEV_QUESTIONS},
                )
                response.raise_for_status()
                data = response.json()
            except httpx.HTTPError as exc:
                print(f"请求失败：{exc}", file=sys.stderr)
                return 1

            answers = data.get("answers", {})
            should = answers.get("should_reply", {}).get("noul", "?")
            risk = answers.get("risk", {}).get("noul", "?")
            style = answers.get("style", {})
            print(f"\n[{name}] {text}")
            print(
                f"  should_reply={should}  risk={risk}  "
                f"style={style.get('choice', '?')} ({style.get('confidence', '?')})"
            )
            print(f"  latency={data.get('latency_ms', '?')}ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
