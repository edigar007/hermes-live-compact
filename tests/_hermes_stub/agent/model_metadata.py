"""Token estimators shaped like Hermes' (CJK ~1 token/char, else ~4 bytes/token)."""
from __future__ import annotations

import json
import math
from typing import Any, Dict, List


def estimate_tokens_rough(text: str) -> int:
    text = text or ""
    if not text:
        return 0
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    ascii_bytes = max(0, len(text.encode("utf-8")) - cjk * 3)
    return max(1, math.ceil(cjk + ascii_bytes / 4))


def _flatten(message: Any) -> str:
    if not isinstance(message, dict):
        return str(message or "")
    content = message.get("content")
    parts: List[str] = []
    if isinstance(content, str):
        parts.append(content)
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
    if message.get("tool_calls"):
        parts.append(json.dumps(message["tool_calls"], ensure_ascii=False))
    return "\n".join(parts)


def estimate_messages_tokens_rough(messages: List[Dict[str, Any]], **_: Any) -> int:
    return sum(estimate_tokens_rough(_flatten(m)) + 4 for m in (messages or []))
