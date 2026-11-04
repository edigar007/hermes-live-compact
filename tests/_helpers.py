"""Shared message fixtures."""
from __future__ import annotations

import json

BIG = "\n".join(
    f"2026-11-04 09:{(i // 60) % 60:02d}:{i % 60:02d} INFO settle worker=w{i % 5} "
    f"order=ORD-{1000 + i} amount={i * 7} region=cn-north-1 status=ok stage=settle"
    for i in range(1200)
)
CODE = "\n".join(
    f"def handler_{i}(request, ctx):\n    value = request.get('field_{i}')\n    return {{'field_{i}': value}}"
    for i in range(200)
)
SMALL = "ok"


def turn(i, body, note=None):
    """One full agent turn: user -> assistant(tool_call) -> tool -> assistant."""
    note = note or f"第 {i} 轮：共 {len(body.splitlines())} 行，必须保留 settle_ledger 顺序。"
    return [
        {"role": "user", "content": f"第 {i} 轮：读文件并回答。"},
        {"role": "assistant", "content": None,
         "tool_calls": [{"id": f"call_{i}", "type": "function",
                         "function": {"name": "read_file", "arguments": json.dumps({"path": f"f{i}.log"})}}]},
        {"role": "tool", "tool_call_id": f"call_{i}", "content": body},
        {"role": "assistant", "content": note},
    ]


def system(tokens_hint=6000):
    """A roughly tokens_hint-token system prompt (ASCII, ~4 bytes/token)."""
    return {"role": "system", "content": "sys " * tokens_hint}


def conversation(turns, incoming="继续。"):
    msgs = [system()]
    for i, body in enumerate(turns, 1):
        msgs += turn(i, body)
    msgs.append({"role": "user", "content": incoming})
    return msgs
