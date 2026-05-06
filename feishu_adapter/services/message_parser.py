from __future__ import annotations

import json
import re

from ..schemas.feishu_message import ParsedMessage


_MENTION_PATTERN = re.compile(r"@_user_\d+")


def extract_text_from_message_content(content: str | None) -> str:
    if not content:
        return ""
    try:
        payload = json.loads(content)
        text = str(payload.get("text") or "").strip()
    except Exception:
        text = str(content).strip()
    text = _MENTION_PATTERN.sub("", text)
    return " ".join(text.split())


def parse_command(raw_text: str) -> ParsedMessage:
    text = str(raw_text or "").strip()
    lowered = text.lower()

    if not text:
        return ParsedMessage(command="empty", text="", raw_text=raw_text)

    if lowered in {"/help", "help", "帮助"}:
        return ParsedMessage(command="help", text="", raw_text=raw_text)

    if lowered.startswith("深度分析") or lowered.startswith("分析：") or lowered.startswith("分析:"):
        normalized = text.replace("深度分析", "", 1).lstrip("：: ").strip()
        if text.startswith("分析"):
            normalized = text[2:].lstrip("：: ").strip()
        return ParsedMessage(command="analysis", text=normalized or text, raw_text=raw_text)

    if lowered.startswith("生成报告") or lowered.startswith("报告：") or lowered.startswith("报告:"):
        normalized = text.replace("生成报告", "", 1).lstrip("：: ").strip()
        if text.startswith("报告"):
            normalized = text[2:].lstrip("：: ").strip()
        return ParsedMessage(command="report", text=normalized, raw_text=raw_text)

    return ParsedMessage(command="chat", text=text, raw_text=raw_text)
